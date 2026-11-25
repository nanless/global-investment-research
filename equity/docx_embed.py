#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pure-Python Native ECMA-376 OOXML DOCX Generator + PIL-Cropped 2x Retina PNG Chart Rasterizer
for the A-Share / HK-Stock / US-Stock Global Equity Publishing Pipeline.

Replaces macOS `textutil` completely:
  - Strict ECMA-376 schema element ordering (tblW -> tblBorders -> tblLayout -> tblCellMar;
    keepNext -> keepLines -> pageBreakBefore -> pBdr -> shd -> spacing -> ind -> jc).
  - Real <w:tbl> with <w:tblHeader/> and positive two-pass <w:tblGrid> summing strictly <= 9638 dxa.
  - Themed 1x1 cards for cover banner, KPI strip, callouts (verdict/danger/guard), volume headers.
  - Chrome Headless 2x Retina rasterization (874px wrap, 45s timeout, isolated temp profile,
    PIL auto-crop with 20px uniform padding, auto-retry 4800px viewport for tall charts).
  - word/settings.xml (<w:updateFields w:val="true"/>) + w:dirty="true" PAGE/NUMPAGES footer.
  - Validates all 7 XML parts with xml.etree.ElementTree before atomic os.replace write.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from bs4 import BeautifulSoup, NavigableString, Tag
from PIL import Image, ImageChops

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# A4 portrait: 11906 x 16838 dxa; margins T/B=1000, L/R=1134 -> usable width = 9638 dxa (~6.69 in)
PAGE_W_DXA = 11906
PAGE_H_DXA = 16838
MARGIN_TB_DXA = 1000
MARGIN_LR_DXA = 1134
CONTENT_W_DXA = PAGE_W_DXA - 2 * MARGIN_LR_DXA  # 9638 dxa

_XML_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_THEMES: dict[str, dict[str, str]] = {
    "a_share": {
        "cover_fill": "1F2937",
        "accent": "DC2626",
        "vol_fill": "FEF2F2",
        "vol_txt": "7F1D1D",
        "h3_col": "991B1B",
        "kpi_val": "FBBF24",
    },
    "hk_stock": {
        "cover_fill": "115E59",
        "accent": "0D9488",
        "vol_fill": "F0FDFA",
        "vol_txt": "115E59",
        "h3_col": "0F766E",
        "kpi_val": "FBBF24",
    },
    "us_stock": {
        "cover_fill": "0F172A",
        "accent": "1D4ED8",
        "vol_fill": "EFF6FF",
        "vol_txt": "1E3A8A",
        "h3_col": "1E40AF",
        "kpi_val": "38BDF8",
    },
}

CHART_WRAPPER_CSS = """
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0; background: #ffffff;
  font-family: "PingFang SC", "Hiragino Sans GB", -apple-system, "Microsoft YaHei", sans-serif;
  color: #1f2937;
}
.wrap { width: 874px; padding: 10px 12px; background: #ffffff; }
.chart-box {
  background: #ffffff; border: 1px solid #e2e8f0; border-radius: 7px;
  padding: 10px 12px 8px 12px;
}
.chart-title { font-size: 13.5px; font-weight: 800; color: #0f172a; margin-bottom: 3px; line-height: 1.35; }
.chart-sub { font-size: 10.5px; color: #64748b; margin-bottom: 6px; line-height: 1.38; }
.chart-takeaway {
  background: #f0f9ff; border-left: 3.5px solid #0072B2; border-radius: 0 5px 5px 0;
  padding: 6px 10px; margin-top: 6px; font-size: 11px; line-height: 1.48; color: #0c4a6e;
}
.chart-note { font-size: 10px; color: #64748b; line-height: 1.4; margin-top: 4px; }
.vmark { display: inline-block; font-size: 11px; font-weight: 900; line-height: 1; margin: 0 3px 0 1px; }
.vm-g { color: #009E73; }
.vm-b { color: #0072B2; }
.vm-y { color: #D97706; }
.vm-r { color: #D55E00; }
.vtag {
  display: inline-block; font-size: 9.5px; font-weight: 800; line-height: 1.15;
  padding: 1px 4px; border-radius: 3px; margin: 0 4px 1px 0;
  background: #e0f2fe; color: #075985; border: 0.7px solid #7dd3fc;
}
.vt-shield, .vt-stop { background: #fee2e2; color: #991b1b; border-color: #fca5a5; }
.vt-ok { background: #dcfce7; color: #166534; border-color: #86efac; }
.vt-go { background: #dbeafe; color: #1e40af; border-color: #93c5fd; }
.vt-lock { background: #e0e7ff; color: #3730a3; border-color: #a5b4fc; }
.vt-warn { background: #fef3c7; color: #92400e; border-color: #fcd34d; }
.vt-tip { background: #e0f2fe; color: #075985; border-color: #7dd3fc; }
.vt-money { background: #fef3c7; color: #78350f; border-color: #fbbf24; }
.vt-key { background: #f3e8ff; color: #6b21a8; border-color: #d8b4fe; }
.vt-wait { background: #f1f5f9; color: #475569; border-color: #cbd5e1; }
.vt-hot { background: #ffedd5; color: #9a3412; border-color: #fdba74; }
.svg-hint { display: none; }
svg { display: block; width: 100%; height: auto; }
"""


def _xe(text: str) -> str:
    return xml_escape(_XML_CTRL_RE.sub("", str(text)))


def _vis_len(text: str) -> float:
    total = 0.0
    for ch in text:
        total += 1.0 if ord(ch) > 127 else 0.55
    return total


def _make_rpr(
    *,
    bold: bool = False,
    italic: bool = False,
    color: str = "1F2937",
    sz_halfpt: int = 20,
    mono: bool = False,
    underline: bool = False,
) -> str:
    parts = ["<w:rPr>"]
    if mono:
        parts.append('<w:rFonts w:ascii="Menlo" w:hAnsi="Menlo" w:eastAsia="PingFang SC" w:cs="Menlo"/>')
    else:
        parts.append('<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="PingFang SC" w:cs="Calibri" w:hint="eastAsia"/>')
    if bold:
        parts.append("<w:b/><w:bCs/>")
    if italic:
        parts.append("<w:i/><w:iCs/>")
    parts.append(f'<w:color w:val="{color}"/>')
    parts.append(f'<w:sz w:val="{sz_halfpt}"/><w:szCs w:val="{sz_halfpt}"/>')
    if underline:
        parts.append('<w:u w:val="single"/>')
    parts.append("</w:rPr>")
    return "".join(parts)


def _make_run(text: str, **kwargs) -> str:
    if not text:
        return ""
    rpr = _make_rpr(**kwargs)
    return f'<w:r>{rpr}<w:t xml:space="preserve">{_xe(text)}</w:t></w:r>'


def _make_ppr(
    *,
    keep_next: bool = False,
    keep_lines: bool = False,
    page_break_before: bool = False,
    p_bdr: str = "",
    shd_fill: str = "",
    before: int = 0,
    after: int = 90,
    line: int = 310,
    ind_left: int = 0,
    ind_hanging: int = 0,
    jc: str = "",
) -> str:
    # Strict ECMA-376 CT_PPr order:
    # keepNext -> keepLines -> pageBreakBefore -> pBdr -> shd -> spacing -> ind -> jc
    parts = ["<w:pPr>"]
    if keep_next:
        parts.append("<w:keepNext/>")
    if keep_lines:
        parts.append("<w:keepLines/>")
    if page_break_before:
        parts.append("<w:pageBreakBefore/>")
    if p_bdr:
        parts.append(f"<w:pBdr>{p_bdr}</w:pBdr>")
    if shd_fill:
        parts.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shd_fill}"/>')
    parts.append(f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>')
    if ind_left or ind_hanging:
        hang_attr = f' w:hanging="{ind_hanging}"' if ind_hanging else ""
        parts.append(f'<w:ind w:left="{ind_left}"{hang_attr}/>')
    if jc:
        parts.append(f'<w:jc w:val="{jc}"/>')
    parts.append("</w:pPr>")
    return "".join(parts)


def _png_dimensions(png_path: Path) -> tuple[int, int]:
    data = png_path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"Invalid PNG header: {png_path}")
    w, h = struct.unpack(">II", data[16:24])
    return int(w), int(h)


def _trim_png_whitespace(png_path: Path, pad_px: int = 20) -> bool:
    with Image.open(png_path) as im:
        rgb = im.convert("RGB")
        bg_px = rgb.getpixel((rgb.width - 1, rgb.height - 1))
        bg = Image.new("RGB", rgb.size, bg_px)
        diff = ImageChops.difference(rgb, bg)
        bbox = diff.point(lambda p: 255 if p > 3 else 0).getbbox()
        if not bbox:
            raise RuntimeError(f"Rendered chart PNG is completely blank: {png_path}")
        left, top, right, bottom = bbox
        touched_bottom = bottom >= rgb.height - 4
        out_w = (right - left) + 2 * pad_px
        out_h = (bottom - top) + 2 * pad_px
        canvas = Image.new("RGB", (out_w, out_h), (255, 255, 255))
        tight = rgb.crop((left, top, right, bottom))
        canvas.paste(tight, (pad_px, pad_px))
        canvas.save(png_path, format="PNG", optimize=True)
        return touched_bottom


def render_chart_to_png(chart_html: str, out_png: Path, tmp_dir: Path, idx: int) -> Path:
    win_w = 874
    tmp_html = tmp_dir / f"_eq_chart_{idx}.html"
    per_call_profile = tmp_dir / f"_eq_prof_{idx}"
    doc = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<style>{CHART_WRAPPER_CSS}</style></head>"
        f'<body><div class="wrap">{chart_html}</div></body></html>'
    )
    tmp_html.write_text(doc, encoding="utf-8")
    try:
        for win_h in (2400, 4800):
            shutil.rmtree(per_call_profile, ignore_errors=True)
            per_call_profile.mkdir(parents=True, exist_ok=True)
            out_png.unlink(missing_ok=True)
            proc = subprocess.run(
                [
                    CHROME_BIN,
                    "--headless",
                    "--disable-gpu",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--hide-scrollbars",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--force-device-scale-factor=2",
                    f"--user-data-dir={per_call_profile}",
                    f"--window-size={win_w},{win_h}",
                    f"--screenshot={out_png}",
                    str(tmp_html),
                ],
                capture_output=True,
                timeout=45,
            )
            if proc.returncode != 0 or not out_png.exists() or out_png.stat().st_size < 2048:
                raise RuntimeError(f"Chrome chart PNG render failed (idx={idx}, rc={proc.returncode})")
            touched_bottom = _trim_png_whitespace(out_png, pad_px=20)
            if not touched_bottom:
                break
        w, h = _png_dimensions(out_png)
        if out_png.stat().st_size < 2048 or w < 200 or h < 80:
            raise RuntimeError(f"Rendered chart PNG invalid size ({w}x{h}): {out_png}")
        return out_png
    finally:
        tmp_html.unlink(missing_ok=True)
        shutil.rmtree(per_call_profile, ignore_errors=True)


class _EquityDocxWriter:
    def __init__(self, chart_png_map: dict[str, Path], market: str, footer_title: str) -> None:
        self.chart_png_map = chart_png_map
        self.consumed_charts: set[str] = set()
        self.theme = _THEMES.get(market, _THEMES["a_share"])
        self.footer_title = footer_title
        self.body_blocks: list[str] = []
        self.rels: list[tuple[str, str, str, bool]] = []
        self.media: dict[str, bytes] = {}
        self._rid_seq = 1
        self._docpr_seq = 100
        self._cnvpr_seq = 500

    def _next_rid(self) -> str:
        rid = f"rId{self._rid_seq}"
        self._rid_seq += 1
        return rid

    def _add_rel(self, rtype: str, target: str, external: bool = False) -> str:
        rid = self._next_rid()
        self.rels.append((rid, rtype, target, external))
        return rid

    def _add_hyperlink_rel(self, href: str) -> str:
        parsed = urllib.parse.urlsplit(href)
        safe_path = urllib.parse.quote(parsed.path, safe="/:@!$&'()*+,;=-._~")
        safe_query = urllib.parse.quote(parsed.query, safe="=&:@!$'()*+,;/-._~")
        safe_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, safe_path, safe_query, parsed.fragment))
        return self._add_rel(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
            safe_url,
            external=True,
        )

    def _inline_runs(
        self,
        node,
        *,
        bold: bool = False,
        italic: bool = False,
        color: str = "1F2937",
        sz_halfpt: int = 20,
    ) -> list[str]:
        runs: list[str] = []
        if isinstance(node, NavigableString):
            txt = str(node)
            if txt:
                runs.append(_make_run(txt, bold=bold, italic=italic, color=color, sz_halfpt=sz_halfpt))
            return runs
        if not isinstance(node, Tag):
            return runs

        name = node.name.lower()
        cls = set(node.get("class") or [])
        if name == "br":
            runs.append("<w:r><w:br/></w:r>")
            return runs
        if name in ("strong", "b"):
            for ch in node.children:
                runs.extend(self._inline_runs(ch, bold=True, italic=italic, color=color, sz_halfpt=sz_halfpt))
            return runs
        if name in ("em", "i"):
            for ch in node.children:
                runs.extend(self._inline_runs(ch, bold=bold, italic=True, color=color, sz_halfpt=sz_halfpt))
            return runs
        if name == "code":
            runs.append(_make_run(node.get_text(), bold=True, color="1E293B", sz_halfpt=max(16, sz_halfpt - 2), mono=True))
            return runs
        if name == "a":
            href = str(node.get("href", "")).strip()
            txt = node.get_text()
            if href.startswith(("http://", "https://")):
                rid = self._add_hyperlink_rel(href)
                inner = _make_run(txt, bold=True, color="0072B2", sz_halfpt=sz_halfpt, underline=True)
                runs.append(f'<w:hyperlink r:id="{rid}">{inner}</w:hyperlink>')
            else:
                runs.append(_make_run(txt, bold=True, color="0072B2", sz_halfpt=sz_halfpt))
            return runs
        if name == "span":
            if "vmark" in cls:
                c = "009E73" if "vm-g" in cls else ("0072B2" if "vm-b" in cls else ("D97706" if "vm-y" in cls else "D55E00"))
                runs.append(_make_run(node.get_text() + " ", bold=True, color=c, sz_halfpt=sz_halfpt))
                return runs
            if "vtag" in cls:
                c = "991B1B" if ("vt-shield" in cls or "vt-stop" in cls) else (
                    "166534" if "vt-ok" in cls else (
                        "1E40AF" if ("vt-go" in cls or "vt-lock" in cls) else (
                            "92400E" if ("vt-warn" in cls or "vt-money" in cls or "vt-hot" in cls) else "075985"
                        )
                    )
                )
                runs.append(_make_run(f"[{node.get_text()}] ", bold=True, color=c, sz_halfpt=max(16, sz_halfpt - 2)))
                return runs
            if "chk-box" in cls:
                runs.append(_make_run("☐ ", bold=True, color="DC2626", sz_halfpt=sz_halfpt))
                return runs
        if name == "input":
            return runs

        for ch in node.children:
            runs.extend(self._inline_runs(ch, bold=bold, italic=italic, color=color, sz_halfpt=sz_halfpt))
        return runs

    def _make_card_table(
        self,
        inner_paragraphs: list[str],
        *,
        fill: str = "F8FAFC",
        border_left: str = "1E3A8A",
        border_left_sz: int = 24,
        border_all: str = "E2E8F0",
        pad_tb: int = 120,
        pad_lr: int = 160,
        cant_split: bool = True,
    ) -> str:
        tbl_pr = (
            "<w:tblPr>"
            f'<w:tblW w:w="{CONTENT_W_DXA}" w:type="dxa"/>'
            "<w:tblBorders>"
            f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{border_all}"/>'
            f'<w:left w:val="single" w:sz="{border_left_sz}" w:space="0" w:color="{border_left}"/>'
            f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="{border_all}"/>'
            f'<w:right w:val="single" w:sz="4" w:space="0" w:color="{border_all}"/>'
            "</w:tblBorders>"
            '<w:tblLayout w:type="fixed"/>'
            f'<w:tblCellMar><w:top w:w="{pad_tb}" w:type="dxa"/><w:left w:w="{pad_lr}" w:type="dxa"/>'
            f'<w:bottom w:w="{pad_tb}" w:type="dxa"/><w:right w:w="{pad_lr}" w:type="dxa"/></w:tblCellMar>'
            "</w:tblPr>"
        )
        grid = f'<w:tblGrid><w:gridCol w:w="{CONTENT_W_DXA}"/></w:tblGrid>'
        tr_pr = "<w:trPr><w:cantSplit/></w:trPr>" if cant_split else ""
        tc_pr = (
            "<w:tcPr>"
            f'<w:tcW w:w="{CONTENT_W_DXA}" w:type="dxa"/>'
            f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
            "</w:tcPr>"
        )
        body = "".join(inner_paragraphs) if inner_paragraphs else "<w:p/>"
        return f"<w:tbl>{tbl_pr}{grid}<w:tr>{tr_pr}<w:tc>{tc_pr}{body}</w:tc></w:tr></w:tbl>"

    def _render_cover_banner(self, div: Tag) -> None:
        tag_el = div.find(class_="cover-tag")
        title_el = div.find(class_="cover-title")
        meta_el = div.find(class_="cover-meta")
        paras: list[str] = []
        if tag_el:
            tag_runs = self._inline_runs(tag_el, bold=True, color=self.theme["kpi_val"], sz_halfpt=17)
            paras.append(f'<w:p>{_make_ppr(after=50, line=260)}{"".join(tag_runs)}</w:p>')
        if title_el:
            title_runs = self._inline_runs(title_el, bold=True, color="FFFFFF", sz_halfpt=28)
            paras.append(f'<w:p>{_make_ppr(after=70, line=300)}{"".join(title_runs)}</w:p>')
        if meta_el:
            meta_runs = self._inline_runs(meta_el, bold=False, color="E2E8F0", sz_halfpt=16)
            paras.append(f'<w:p>{_make_ppr(after=30, line=270)}{"".join(meta_runs)}</w:p>')
        self.body_blocks.append(
            self._make_card_table(
                paras,
                fill=self.theme["cover_fill"],
                border_left=self.theme["accent"],
                border_left_sz=30,
                border_all=self.theme["cover_fill"],
                pad_tb=140,
                pad_lr=180,
                cant_split=True,
            )
        )
        # Render KPI cards in a clean 2-column native grid table
        cards = div.find_all(class_="kpi-card")
        if cards:
            self._render_kpi_grid(cards)
        self.body_blocks.append(f'<w:p>{_make_ppr(before=0, after=60, line=180)}</w:p>')

    def _render_kpi_grid(self, cards: list[Tag]) -> None:
        ncols = 2
        col_w = CONTENT_W_DXA // ncols
        rem = CONTENT_W_DXA - col_w * ncols
        widths = [col_w + (1 if i < rem else 0) for i in range(ncols)]
        tbl_pr = (
            "<w:tblPr>"
            f'<w:tblW w:w="{CONTENT_W_DXA}" w:type="dxa"/>'
            "<w:tblBorders>"
            '<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            '<w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            '<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            "</w:tblBorders>"
            '<w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="110" w:type="dxa"/>'
            '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="110" w:type="dxa"/></w:tblCellMar>'
            "</w:tblPr>"
        )
        grid = "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>"
        rows_xml: list[str] = []
        for r_idx in range(0, len(cards), ncols):
            row_cards = cards[r_idx : r_idx + ncols]
            tcs: list[str] = []
            for c_idx in range(ncols):
                w = widths[c_idx]
                tc_pr = f'<w:tcPr><w:tcW w:w="{w}" w:type="dxa"/><w:shd w:val="clear" w:color="auto" w:fill="F8FAFC"/></w:tcPr>'
                if c_idx < len(row_cards):
                    c = row_cards[c_idx]
                    lbl = c.find(class_="kpi-label")
                    val = c.find(class_="kpi-val")
                    sub = c.find(class_="kpi-sub")
                    ps = []
                    if lbl:
                        lbl_runs = self._inline_runs(lbl, bold=True, color="475569", sz_halfpt=16)
                        ps.append(f'<w:p>{_make_ppr(after=20, line=240)}{"".join(lbl_runs)}</w:p>')
                    if val:
                        val_runs = self._inline_runs(val, bold=True, color=self.theme["accent"], sz_halfpt=21)
                        ps.append(f'<w:p>{_make_ppr(after=20, line=260)}{"".join(val_runs)}</w:p>')
                    if sub:
                        sub_runs = self._inline_runs(sub, bold=False, color="334155", sz_halfpt=16)
                        ps.append(f'<w:p>{_make_ppr(after=10, line=240)}{"".join(sub_runs)}</w:p>')
                    tcs.append(f"<w:tc>{tc_pr}{''.join(ps) or '<w:p/>'}</w:tc>")
                else:
                    tcs.append(f"<w:tc>{tc_pr}<w:p/></w:tc>")
            rows_xml.append(f'<w:tr><w:trPr><w:cantSplit/></w:trPr>{"".join(tcs)}</w:tr>')
        self.body_blocks.append(f"<w:tbl>{tbl_pr}{grid}{''.join(rows_xml)}</w:tbl>")

    def _render_callout(self, div: Tag) -> None:
        cls = set(div.get("class") or [])
        if "callout-danger" in cls:
            fill, left_c, txt_c = "FEF2F2", "DC2626", "7F1D1D"
        elif "callout-verdict" in cls:
            fill, left_c, txt_c = "F8F7F3", self.theme["accent"], "1E293B"
        elif "callout-guard" in cls:
            fill, left_c, txt_c = "F8FAFC", self.theme["vol_txt"], "1E293B"
        else:
            fill, left_c, txt_c = "FFFBEB", "D97706", "451A03"

        paras: list[str] = []
        for ch in div.children:
            if not isinstance(ch, Tag):
                continue
            ch_cls = set(ch.get("class") or [])
            if "callout-title" in ch_cls:
                runs = self._inline_runs(ch, bold=True, color="991B1B" if "callout-danger" in cls else "0F172A", sz_halfpt=19)
                paras.append(f'<w:p>{_make_ppr(keep_next=True, after=50, line=280)}{"".join(runs)}</w:p>')
            else:
                runs = self._inline_runs(ch, color=txt_c, sz_halfpt=18)
                if runs:
                    paras.append(f'<w:p>{_make_ppr(after=45, line=280)}{"".join(runs)}</w:p>')
        cant_split = "callout-flow" not in cls and len(paras) <= 6
        self.body_blocks.append(
            self._make_card_table(
                paras,
                fill=fill,
                border_left=left_c,
                border_left_sz=24,
                border_all="E2E8F0",
                pad_tb=90,
                pad_lr=135,
                cant_split=cant_split,
            )
        )
        self.body_blocks.append(f'<w:p>{_make_ppr(before=0, after=55, line=160)}</w:p>')

    def _render_table(self, tbl: Tag) -> None:
        thead_rows = tbl.find("thead").find_all("tr") if tbl.find("thead") else []
        tbody = tbl.find("tbody") or tbl
        body_rows = [r for r in tbody.find_all("tr", recursive=False) if r not in thead_rows]
        all_rows = thead_rows + body_rows
        if not all_rows:
            return
        ncols = max(len(r.find_all(["th", "td"], recursive=False)) for r in all_rows)
        if ncols <= 0:
            return

        # Two-pass positive safe column width calculation summing strictly == CONTENT_W_DXA
        col_scores = [4.0] * ncols
        for r in all_rows:
            cells = r.find_all(["th", "td"], recursive=False)
            for idx, c in enumerate(cells[:ncols]):
                vl = max(3.5, min(42.0, _vis_len(c.get_text(" ", strip=True))))
                if vl > col_scores[idx]:
                    col_scores[idx] = vl
        # Dampen extreme skew so narrow columns stay readable
        damped = [s ** 0.72 for s in col_scores]
        total_s = sum(damped) or 1.0
        min_w = max(720, min(1100, CONTENT_W_DXA // max(ncols + 1, 2)))
        raw_w = [max(min_w, int(CONTENT_W_DXA * (d / total_s))) for d in damped]
        scale = CONTENT_W_DXA / sum(raw_w)
        widths = [max(480, int(w * scale)) for w in raw_w]
        diff = CONTENT_W_DXA - sum(widths)
        if diff >= 0:
            widths[-1] += diff
        else:
            excess = -diff
            for idx in sorted(range(ncols), key=lambda i: widths[i], reverse=True):
                if excess <= 0:
                    break
                take = min(excess, max(0, widths[idx] - 480))
                widths[idx] -= take
                excess -= take
            if excess > 0:
                widths[-1] = max(240, widths[-1] - excess)

        tbl_pr = (
            "<w:tblPr>"
            f'<w:tblW w:w="{CONTENT_W_DXA}" w:type="dxa"/>'
            "<w:tblBorders>"
            '<w:top w:val="single" w:sz="10" w:space="0" w:color="0F172A"/>'
            '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="475569"/>'
            '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
            '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            "</w:tblBorders>"
            '<w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:top w:w="55" w:type="dxa"/><w:left w:w="75" w:type="dxa"/>'
            '<w:bottom w:w="55" w:type="dxa"/><w:right w:w="75" w:type="dxa"/></w:tblCellMar>'
            "</w:tblPr>"
        )
        grid = "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>"

        rows_xml: list[str] = []
        for r_idx, r in enumerate(all_rows):
            is_hdr = r in thead_rows
            r_cls = set(r.get("class") or [])
            left_stripe = ""
            if "row-g" in r_cls:
                left_stripe = "009E73"
            elif "row-b" in r_cls:
                left_stripe = "0072B2"
            elif "row-y" in r_cls:
                left_stripe = "D97706"
            elif "row-r" in r_cls:
                left_stripe = "D55E00"

            fill = "F1F5F9" if is_hdr else ("F8FAFC" if (r_idx - len(thead_rows)) % 2 == 1 else "FFFFFF")
            cells = r.find_all(["th", "td"], recursive=False)
            row_chars = sum(len(c.get_text()) for c in cells)
            tr_pr_items = []
            if is_hdr:
                tr_pr_items.append("<w:tblHeader/>")
            if is_hdr or row_chars <= 420:
                tr_pr_items.append("<w:cantSplit/>")
            tr_pr = f'<w:trPr>{"".join(tr_pr_items)}</w:trPr>' if tr_pr_items else ""

            tcs: list[str] = []
            for c_idx in range(ncols):
                w = widths[c_idx]
                c_tag = cells[c_idx] if c_idx < len(cells) else None
                bdr_xml = ""
                if c_idx == 0 and left_stripe:
                    bdr_xml = f'<w:tcBorders><w:left w:val="single" w:sz="18" w:space="0" w:color="{left_stripe}"/></w:tcBorders>'
                elif is_hdr:
                    bdr_xml = '<w:tcBorders><w:bottom w:val="single" w:sz="8" w:space="0" w:color="475569"/></w:tcBorders>'
                tc_pr = (
                    f'<w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{bdr_xml}'
                    f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/></w:tcPr>'
                )
                if c_tag is not None:
                    style = str(c_tag.get("style", ""))
                    jc = "right" if "text-align:right" in style else ("center" if "text-align:center" in style else "")
                    runs = self._inline_runs(
                        c_tag,
                        bold=is_hdr,
                        color="0F172A" if is_hdr else "1F2937",
                        sz_halfpt=16,
                    )
                    p_xml = f'<w:p>{_make_ppr(after=20, line=250, jc=jc)}{"".join(runs)}</w:p>'
                else:
                    p_xml = "<w:p/>"
                tcs.append(f"<w:tc>{tc_pr}{p_xml}</w:tc>")
            rows_xml.append(f"<w:tr>{tr_pr}{''.join(tcs)}</w:tr>")

        self.body_blocks.append(f"<w:tbl>{tbl_pr}{grid}{''.join(rows_xml)}</w:tbl>")
        self.body_blocks.append(f'<w:p>{_make_ppr(before=0, after=60, line=160)}</w:p>')

    def _render_chart_image(self, marker: str) -> None:
        png_path = self.chart_png_map.get(marker)
        if png_path is None:
            raise RuntimeError(f"Unresolved DOCX chart marker: {marker}")
        self.consumed_charts.add(marker)
        w_px, h_px = _png_dimensions(png_path)
        img_name = f"chart_{len(self.media)+1}.png"
        self.media[f"word/media/{img_name}"] = png_path.read_bytes()
        rid = self._add_rel(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
            f"media/{img_name}",
            external=False,
        )
        max_w_in = 6.45
        max_h_in = 8.20
        aspect = h_px / max(1, w_px)
        w_in = max_w_in
        h_in = w_in * aspect
        if h_in > max_h_in:
            h_in = max_h_in
            w_in = h_in / aspect
        cx = int(round(w_in * 914400))
        cy = int(round(h_in * 914400))
        docpr_id = self._docpr_seq
        cnvpr_id = self._cnvpr_seq
        self._docpr_seq += 1
        self._cnvpr_seq += 1
        drawing = (
            f'<w:p>{_make_ppr(before=60, after=80, line=240, jc="center")}<w:r><w:drawing>'
            '<wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/>'
            '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{docpr_id}" name="Chart {docpr_id}"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic>'
            f'<pic:nvPicPr><pic:cNvPr id="{cnvpr_id}" name="{img_name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
        )
        self.body_blocks.append(drawing)

    def _render_list(self, list_tag: Tag, *, ordered: bool, level: int = 0) -> None:
        idx = 1
        for li in list_tag.find_all("li", recursive=False):
            nested_uls = []
            runs: list[str] = []
            for ch in li.children:
                if isinstance(ch, Tag) and ch.name.lower() in ("ul", "ol"):
                    nested_uls.append(ch)
                elif isinstance(ch, Tag) and "ol-sub" in (ch.get("class") or []):
                    runs.append("<w:r><w:br/></w:r>")
                    runs.extend(self._inline_runs(ch, color="334155", sz_halfpt=19))
                else:
                    runs.extend(self._inline_runs(ch, color="1F2937", sz_halfpt=19))
            prefix = f"{idx}. " if ordered else ("• " if level == 0 else "◦ ")
            idx += 1
            ind_left = 360 + level * 320
            self.body_blocks.append(
                f'<w:p>{_make_ppr(after=55, line=300, ind_left=ind_left, ind_hanging=220)}'
                f'{_make_run(prefix, bold=True, color=self.theme["accent"], sz_halfpt=19)}'
                f'{"".join(runs)}</w:p>'
            )
            for sub in nested_uls:
                self._render_list(sub, ordered=(sub.name.lower() == "ol"), level=level + 1)

    def _walk_body(self, body: Tag) -> None:
        for ch in body.children:
            if not isinstance(ch, Tag):
                continue
            name = ch.name.lower()
            cls = set(ch.get("class") or [])
            if name == "nav":
                continue
            if name == "div" and "cover-banner" in cls:
                self._render_cover_banner(ch)
            elif name == "div" and "callout" in cls:
                self._render_callout(ch)
            elif name == "div" and "table-wrap" in cls:
                t = ch.find("table")
                if t:
                    self._render_table(t)
            elif name == "div" and "footer-note" in cls:
                top_bdr = '<w:top w:val="single" w:sz="4" w:space="4" w:color="CBD5E1"/>'
                self.body_blocks.append(
                    f'<w:p>{_make_ppr(before=120, after=40, line=260, p_bdr=top_bdr, jc="center")}'
                    f'{_make_run(ch.get_text(" ", strip=True), color="64748B", sz_halfpt=15)}</w:p>'
                )
            elif name == "h1":
                runs = self._inline_runs(ch, bold=True, color=self.theme["vol_txt"], sz_halfpt=24)
                p = f'<w:p>{_make_ppr(keep_next=True, after=20, line=280)}{"".join(runs)}</w:p>'
                self.body_blocks.append(
                    self._make_card_table(
                        [p],
                        fill=self.theme["vol_fill"],
                        border_left=self.theme["accent"],
                        border_left_sz=28,
                        border_all=self.theme["vol_fill"],
                        pad_tb=85,
                        pad_lr=130,
                        cant_split=True,
                    )
                )
                self.body_blocks.append(f'<w:p>{_make_ppr(keep_next=True, before=0, after=50, line=160)}</w:p>')
            elif name == "h2":
                runs = self._inline_runs(ch, bold=True, color="0F172A", sz_halfpt=22)
                bdr = f'<w:bottom w:val="single" w:sz="8" w:space="3" w:color="{self.theme["accent"]}"/>'
                self.body_blocks.append(f'<w:p>{_make_ppr(keep_next=True, before=160, after=80, line=280, p_bdr=bdr)}{"".join(runs)}</w:p>')
            elif name == "h3":
                runs = self._inline_runs(ch, bold=True, color=self.theme["h3_col"], sz_halfpt=20)
                self.body_blocks.append(f'<w:p>{_make_ppr(keep_next=True, before=120, after=60, line=280)}{"".join(runs)}</w:p>')
            elif name == "h4":
                runs = self._inline_runs(ch, bold=True, color="334155", sz_halfpt=19)
                self.body_blocks.append(f'<w:p>{_make_ppr(keep_next=True, before=100, after=50, line=280, shd_fill="F8FAFC")}{"".join(runs)}</w:p>')
            elif name == "p":
                txt = ch.get_text(strip=True)
                if txt in self.chart_png_map:
                    self._render_chart_image(txt)
                else:
                    runs = self._inline_runs(ch, color="1F2937", sz_halfpt=19)
                    if runs:
                        self.body_blocks.append(f'<w:p>{_make_ppr(after=85, line=305)}{"".join(runs)}</w:p>')
            elif name == "ul":
                self._render_list(ch, ordered=False)
            elif name == "ol":
                self._render_list(ch, ordered=True)
            elif name == "pre":
                pre_lines = ch.get_text().splitlines() or [""]
                pre_runs = []
                for li_i, pln in enumerate(pre_lines):
                    if li_i > 0:
                        pre_runs.append("<w:r><w:br/></w:r>")
                    pre_runs.append(_make_run(pln, color="1E293B", sz_halfpt=16, mono=True))
                p = f'<w:p>{_make_ppr(after=20, line=240)}{"".join(pre_runs)}</w:p>'
                self.body_blocks.append(
                    self._make_card_table([p], fill="F8FAFC", border_left="94A3B8", border_left_sz=12, cant_split=False)
                )
            elif name == "table":
                self._render_table(ch)

    def build_zip_bytes(self, body_soup: Tag) -> dict[str, bytes]:
        self._walk_body(body_soup)
        missing = set(self.chart_png_map.keys()) - self.consumed_charts
        if missing:
            raise RuntimeError(f"Unconsumed DOCX chart markers: {sorted(missing)}")

        self._add_rel(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
            "styles.xml",
        )
        self._add_rel(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings",
            "settings.xml",
        )
        ftr_rid = self._add_rel(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer",
            "footer1.xml",
        )

        ct_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
            '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
            "</Types>"
        )
        pkg_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        )
        rel_items = [
            f'<Relationship Id="{rid}" Type="{rtype}" Target="{_xe(target)}"'
            + (' TargetMode="External"' if ext else "")
            + "/>"
            for rid, rtype, target, ext in self.rels
        ]
        doc_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(rel_items)}</Relationships>'
        )
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:docDefaults><w:rPrDefault><w:rPr>"
            '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="PingFang SC" w:cs="Calibri" w:hint="eastAsia"/>'
            '<w:color w:val="1F2937"/><w:sz w:val="20"/><w:szCs w:val="20"/>'
            "</w:rPr></w:rPrDefault>"
            '<w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="90" w:line="305" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
            '</w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
            "</w:styles>"
        )
        settings_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:updateFields w:val="true"/>'
            "</w:settings>"
        )
        ftr_rpr = _make_rpr(color="64748B", sz_halfpt=16)
        footer_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:p><w:pPr>"
            '<w:pBdr><w:top w:val="single" w:sz="4" w:space="4" w:color="CBD5E1"/></w:pBdr>'
            '<w:jc w:val="center"/>'
            "</w:pPr>"
            f'<w:r>{ftr_rpr}<w:t xml:space="preserve">{_xe(self.footer_title)}  ·  第 </w:t></w:r>'
            f'<w:r>{ftr_rpr}<w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
            f'<w:r>{ftr_rpr}<w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
            f'<w:r>{ftr_rpr}<w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r>{ftr_rpr}<w:t>1</w:t></w:r>'
            f'<w:r>{ftr_rpr}<w:fldChar w:fldCharType="end"/></w:r>'
            f'<w:r>{ftr_rpr}<w:t xml:space="preserve"> / </w:t></w:r>'
            f'<w:r>{ftr_rpr}<w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
            f'<w:r>{ftr_rpr}<w:instrText xml:space="preserve"> NUMPAGES </w:instrText></w:r>'
            f'<w:r>{ftr_rpr}<w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r>{ftr_rpr}<w:t>1</w:t></w:r>'
            f'<w:r>{ftr_rpr}<w:fldChar w:fldCharType="end"/></w:r>'
            f'<w:r>{ftr_rpr}<w:t xml:space="preserve"> 页</w:t></w:r>'
            "</w:p></w:ftr>"
        )
        sect_pr = (
            "<w:sectPr>"
            f'<w:footerReference w:type="default" r:id="{ftr_rid}"/>'
            f'<w:pgSz w:w="{PAGE_W_DXA}" w:h="{PAGE_H_DXA}"/>'
            f'<w:pgMar w:top="{MARGIN_TB_DXA}" w:right="{MARGIN_LR_DXA}" '
            f'w:bottom="{MARGIN_TB_DXA}" w:left="{MARGIN_LR_DXA}" w:header="540" w:footer="540" w:gutter="0"/>'
            "</w:sectPr>"
        )
        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document '
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<w:body>{"".join(self.body_blocks)}{sect_pr}</w:body></w:document>'
        )

        xml_parts = {
            "[Content_Types].xml": ct_xml,
            "_rels/.rels": pkg_rels,
            "word/_rels/document.xml.rels": doc_rels,
            "word/styles.xml": styles_xml,
            "word/settings.xml": settings_xml,
            "word/footer1.xml": footer_xml,
            "word/document.xml": doc_xml,
        }
        for part_name, xml_str in xml_parts.items():
            try:
                ET.fromstring(xml_str.encode("utf-8"))
            except ET.ParseError as exc:
                raise RuntimeError(f"Generated invalid OOXML in {part_name}: {exc}") from exc

        out = {k: v.encode("utf-8") for k, v in xml_parts.items()}
        out.update(self.media)
        return out


def build_native_docx_from_html(
    full_html: str,
    docx_path: Path,
    *,
    market: str = "a_share",
    footer_title: str = "全球股市深度投研报告",
) -> None:
    """Parse full report HTML, rasterize every .chart-box SVG to 2x Retina PNG, and write native ECMA-376 .docx."""
    soup = BeautifulSoup(full_html, "html.parser")
    body = soup.find("body")
    if body is None:
        raise RuntimeError("Missing <body> in report HTML")

    tmp_dir = Path(tempfile.mkdtemp(prefix="eq_ooxml_"))
    tmp_zip = docx_path.with_suffix(".docx.tmp")
    tmp_zip.unlink(missing_ok=True)
    try:
        chart_png_map: dict[str, Path] = {}
        chart_divs = body.find_all("div", class_="chart-box")
        for idx, cdiv in enumerate(chart_divs):
            marker = f"___DOCX_CHART_{idx}___"
            png_path = tmp_dir / f"chart_{idx}.png"
            render_chart_to_png(str(cdiv), png_path, tmp_dir, idx)
            chart_png_map[marker] = png_path
            placeholder = soup.new_tag("p")
            placeholder.string = marker
            cdiv.replace_with(placeholder)

        writer = _EquityDocxWriter(chart_png_map, market=market, footer_title=footer_title)
        parts = writer.build_zip_bytes(body)
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name, data in parts.items():
                zout.writestr(name, data)
        os.replace(tmp_zip, docx_path)
    except Exception:
        tmp_zip.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
