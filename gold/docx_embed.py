#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Native ECMA-376 OOXML DOCX Generator + PIL-Cropped Retina PNG Chart Rasterizer (V2.2).
Completely replaces macOS `textutil` (which silently stripped all HTML tables and card borders):
  - Generates 100% valid WordprocessingML (.docx) with strict ECMA-376 schema element order
    (tblW -> tblBorders -> tblLayout -> tblCellMar; pBdr -> jc; standalone hard page breaks),
    real <w:tbl>, <w:tblHeader/>, safe positive two-pass <w:tblGrid>, cross-platform 1x1 cards,
    word/settings.xml (<w:updateFields/>) + w:dirty="true" PAGE/NUMPAGES, RFC-3986 hyperlinks,
    semantic persona/pill/dot rendering, and clean 10pt Chinese/English typography (zero <w:sz-cs>).
  - Rasterizes every SVG chart via Chrome Headless (45s timeout, per-call profile, dynamic trim,
    auto-retry on tall charts) to PIL-cropped 2x Retina PNGs.
  - Validates every XML part with xml.etree.ElementTree before atomic write.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from bs4 import BeautifulSoup, NavigableString, Tag
from PIL import Image, ImageChops

_DEFAULT_MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def resolve_chrome_bin() -> str:
    """Resolve Chrome/Chromium binary via CHROME_BIN env var, macOS bundle, or PATH."""
    env_bin = os.environ.get("CHROME_BIN", "").strip()
    if env_bin:
        return env_bin
    if Path(_DEFAULT_MAC_CHROME).exists():
        return _DEFAULT_MAC_CHROME
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return _DEFAULT_MAC_CHROME


CHROME_BIN = resolve_chrome_bin()

CHART_WRAPPER_CSS = """
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: #ffffff;
  font-family: "PingFang SC", "Hiragino Sans GB", -apple-system, "Microsoft YaHei", sans-serif;
  color: #1f2937;
}
.wrap { width: 664px; padding: 10px 12px 10px 12px; background: #ffffff; }
.chart-box {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-top: 2.5px solid #1e3a8a;
  border-radius: 8px;
  padding: 10px 12px 8px 12px;
}
.chart-title { font-size: 13px; font-weight: 800; color: #0f172a; line-height: 1.38; margin-bottom: 3px; text-align: left; }
.chart-sub { font-size: 10.5px; color: #64748b; line-height: 1.35; margin-bottom: 7px; text-align: left; }
.chart-note { font-size: 10px; color: #64748b; line-height: 1.45; margin-top: 6px; }
svg { display: block; width: 100%; height: auto; }
"""

# A4 portrait: 11906 x 16838 dxa; margins T/B=1000, L/R=1134 -> usable width = 9638 dxa (~6.69 in)
PAGE_W_DXA = 11906
PAGE_H_DXA = 16838
MARGIN_TB_DXA = 1000
MARGIN_LR_DXA = 1134
CONTENT_W_DXA = PAGE_W_DXA - 2 * MARGIN_LR_DXA  # 9638 dxa
_XML_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_EMOJI_RUN_SPLIT_RE = re.compile(r"(🔴|🟡|🟢|⚪️?|🚨|⚠️?|✅|❌|🚀)")


def png_dimensions(png_path: Path) -> tuple[int, int]:
    data = png_path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"Invalid PNG header: {png_path}")
    w, h = struct.unpack(">II", data[16:24])
    return int(w), int(h)


def _trim_png_whitespace(png_path: Path, pad_px: int = 20) -> bool:
    """Auto-crop Chrome screenshot to exact non-background bbox plus uniform white padding.
    Returns True if content touched the bottom viewport edge."""
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


def render_chart_to_png(
    chart_html: str,
    out_png: Path,
    tmp_dir: Path,
    chrome_profile: Path,
    idx: int,
) -> Path:
    """Render an HTML/SVG chart box to 2x Retina PNG with 60s timeout, fresh profile & 1 retry."""
    win_w = 664
    tmp_html = tmp_dir / f"_chart_render_{idx}.html"
    chrome_bin = os.environ.get("CHROME_BIN", "").strip() or CHROME_BIN
    doc = (
        f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<style>{CHART_WRAPPER_CSS}</style></head>"
        f'<body><div class="wrap">{chart_html}</div></body></html>'
    )
    tmp_html.write_text(doc, encoding="utf-8")
    try:
        for win_h in (2400, 4800):
            for attempt in range(1, 3):
                attempt_profile = tmp_dir / f"_chrome_prof_{idx}_{win_h}_{attempt}"
                shutil.rmtree(attempt_profile, ignore_errors=True)
                attempt_profile.mkdir(parents=True, exist_ok=True)
                out_png.unlink(missing_ok=True)
                try:
                    proc = subprocess.run(
                        [
                            chrome_bin,
                            "--headless",
                            "--disable-gpu",
                            "--disable-extensions",
                            "--disable-background-networking",
                            "--hide-scrollbars",
                            "--no-first-run",
                            "--no-default-browser-check",
                            "--force-device-scale-factor=2",
                            f"--user-data-dir={attempt_profile}",
                            f"--window-size={win_w},{win_h}",
                            f"--screenshot={out_png}",
                            tmp_html.resolve().as_uri(),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if proc.returncode != 0 or not out_png.exists() or out_png.stat().st_size < 2048:
                        raise RuntimeError(
                            f"Chrome chart PNG screenshot failed (idx={idx}, attempt={attempt}/2, rc={proc.returncode}): "
                            f"{proc.stderr.strip()[:400]}"
                        )
                    break
                except (subprocess.TimeoutExpired, RuntimeError) as exc:
                    if attempt == 2:
                        if isinstance(exc, subprocess.TimeoutExpired):
                            raise RuntimeError(
                                f"Chrome chart PNG screenshot timed out after 60s (idx={idx}, attempt 2/2)"
                            ) from exc
                        raise
                finally:
                    shutil.rmtree(attempt_profile, ignore_errors=True)
            if not _trim_png_whitespace(out_png, pad_px=20):
                break
            if win_h == 4800:
                raise RuntimeError(f"Chart PNG exceeded 4800px height (idx={idx}): {out_png}")
    finally:
        tmp_html.unlink(missing_ok=True)

    pw, ph = png_dimensions(out_png)
    if out_png.stat().st_size < 2048 or ph < 100 or pw < 200:
        raise RuntimeError(f"Cropped chart PNG looks invalid ({pw}x{ph}, {out_png.stat().st_size}B): {out_png}")
    return out_png


# ==============================================================================
# PURE-PYTHON ECMA-376 NATIVE OOXML DOCX BUILDER
# ==============================================================================

def _xe(s: str) -> str:
    cleaned = _XML_CTRL_RE.sub("", str(s)).replace("\ufe0f", "")
    return xml_escape(cleaned, {'"': "&quot;", "'": "&apos;"})


def _hex_from_style(style_str: str, prop: str, default: str = "") -> str:
    prop_pat = "background(?:-color)?" if prop.lower() == "background" else re.escape(prop)
    m = re.search(rf"(?:^|;)\s*{prop_pat}\s*:\s*([^;]+)", style_str or "", re.IGNORECASE)
    if not m:
        return default
    val = m.group(1).strip()
    hx6 = re.search(r"#([0-9a-fA-F]{6})\b", val)
    if hx6:
        return hx6.group(1).upper()
    hx3 = re.search(r"#([0-9a-fA-F]{3})\b", val)
    if hx3:
        h = hx3.group(1).upper()
        return f"{h[0]*2}{h[1]*2}{h[2]*2}"
    return default


def _vis_width(text: str) -> float:
    total = 0.0
    for ch in text:
        if ord(ch) > 127:
            total += 1.0
        else:
            total += 0.55
    return total


def _make_rpr(
    bold: bool = False,
    italic: bool = False,
    color: str | None = None,
    sz_halfpt: int | None = None,
    code: bool = False,
    underline: bool = False,
    font_east: str = "PingFang SC",
    font_ascii: str = "Calibri",
) -> str:
    """Emit strictly valid CT_RPr in ECMA-376 schema element order (never <w:sz-cs>!)."""
    parts = []
    if code:
        parts.append('<w:rFonts w:ascii="Menlo" w:hAnsi="Menlo" w:eastAsia="PingFang SC" w:cs="Menlo"/>')
    else:
        parts.append(
            f'<w:rFonts w:ascii="{font_ascii}" w:hAnsi="{font_ascii}" '
            f'w:eastAsia="{font_east}" w:cs="{font_ascii}" w:hint="eastAsia"/>'
        )
    if bold:
        parts.append("<w:b/><w:bCs/>")
    if italic:
        parts.append("<w:i/><w:iCs/>")
    if color:
        parts.append(f'<w:color w:val="{color.lstrip("#").upper()}"/>')
    if sz_halfpt is not None:
        parts.append(f'<w:sz w:val="{sz_halfpt}"/><w:szCs w:val="{sz_halfpt}"/>')
    if underline:
        parts.append('<w:u w:val="single"/>')
    if code:
        parts.append('<w:shd w:val="clear" w:color="auto" w:fill="EEF2FF"/>')
    return f"<w:rPr>{''.join(parts)}</w:rPr>"


class _NativeDocxWriter:
    def __init__(self, chart_png_map: dict[str, Path], footer_title: str = "黄金深度研报"):
        self.chart_png_map = chart_png_map
        self.footer_title = footer_title
        self.body_blocks: list[str] = []
        self.rels: list[tuple[str, str, str, bool]] = []  # (rId, type, target, external)
        self.media: dict[str, bytes] = {}
        self._rid_seq = 10
        self._docpr_seq = 1
        self._img_seq = 0
        self._used_charts: set[str] = set()

    def _next_rid(self, prefix: str = "rId") -> str:
        self._rid_seq += 1
        return f"{prefix}{self._rid_seq}"

    def _next_docpr(self) -> int:
        val = self._docpr_seq
        self._docpr_seq += 1
        return val

    def _register_hyperlink(self, url: str) -> str:
        encoded = urllib.parse.quote(url.strip(), safe=":/?#[]@!$&'()*+,;=%-._~")
        rid = self._next_rid("rIdLink")
        self.rels.append((
            rid,
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
            encoded,
            True,
        ))
        return rid

    def _register_image(self, png_path: Path) -> tuple[str, int, int]:
        self._img_seq += 1
        rid = self._next_rid("rIdImg")
        media_rel = f"media/chart_{self._img_seq}.png"
        self.media[f"word/{media_rel}"] = png_path.read_bytes()
        self.rels.append((
            rid,
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
            media_rel,
            False,
        ))
        pw, ph = png_dimensions(png_path)
        return rid, pw, ph

    def _make_run(
        self,
        text: str,
        bold: bool = False,
        italic: bool = False,
        color: str | None = None,
        sz: int | None = None,
        code: bool = False,
        underline: bool = False,
    ) -> str:
        if not text:
            return ""
        rpr = _make_rpr(bold=bold, italic=italic, color=color, sz_halfpt=sz, code=code, underline=underline)
        return f'<w:r>{rpr}<w:t xml:space="preserve">{_xe(text)}</w:t></w:r>'

    def _text_with_vector_symbols(
        self,
        txt: str,
        bold: bool = False,
        italic: bool = False,
        color: str | None = None,
        sz: int | None = None,
        code: bool = False,
        underline: bool = False,
    ) -> str:
        if not txt:
            return ""
        sym_map = {
            "🔴": ("●", "DC2626"),
            "🟡": ("●", "D97706"),
            "🟢": ("●", "16A34A"),
            "⚪": ("●", "64748B"),
            "⚪️": ("●", "64748B"),
            "🚨": ("▲", "DC2626"),
            "⚠": ("▲", "D97706"),
            "⚠️": ("▲", "D97706"),
            "✅": ("✓", "15803D"),
            "❌": ("✕", "B91C1C"),
            "🚀": ("●", "16A34A"),
        }
        parts = _EMOJI_RUN_SPLIT_RE.split(txt)
        out = []
        for part in parts:
            if not part:
                continue
            if part in sym_map:
                sym, col = sym_map[part]
                out.append(self._make_run(sym, bold=True, color=col, sz=sz))
            else:
                out.append(
                    self._make_run(part, bold=bold, italic=italic, color=color, sz=sz, code=code, underline=underline)
                )
        return "".join(out)

    def _inline_to_runs(
        self,
        node,
        bold: bool = False,
        italic: bool = False,
        color: str | None = None,
        sz: int | None = None,
        code: bool = False,
        underline: bool = False,
    ) -> str:
        if isinstance(node, NavigableString):
            txt = str(node)
            txt = re.sub(r"[ \t]*[\r\n]+[ \t]*", " ", txt).replace("\t", " ")
            if not txt:
                return ""
            if code:
                return self._make_run(txt, bold=bold, italic=italic, color=color, sz=sz, code=True, underline=underline)
            return self._text_with_vector_symbols(
                txt, bold=bold, italic=italic, color=color, sz=sz, code=False, underline=underline
            )
        if not isinstance(node, Tag):
            return ""

        name = node.name.lower()
        if name == "br":
            return "<w:r><w:br/></w:r>"

        classes = set(node.get("class") or [])
        style_str = node.get("style", "")
        cur_bold = bold or name in ("strong", "b") or ("font-weight:bold" in style_str.replace(" ", "").lower())
        cur_italic = italic or name in ("em", "i")
        cur_code = code or name == "code"
        cur_color = _hex_from_style(style_str, "color", "") or color
        cur_sz = sz
        cur_ul = underline

        if "dot" in classes:
            sym = "◆ " if "dot-diamond" in classes else "● "
            if "dot-red" in classes:
                return self._make_run(sym, bold=True, color="DC2626", sz=cur_sz)
            if "dot-amber" in classes or "dot-diamond" in classes:
                return self._make_run(sym, bold=True, color="D97706", sz=cur_sz)
            if "dot-green" in classes:
                return self._make_run(sym, bold=True, color="16A34A", sz=cur_sz)
            return self._make_run(sym, bold=True, color="64748B", sz=cur_sz)
        if "st-fail" in classes:
            cur_bold = True
            cur_color = "B91C1C"
        elif "st-pass" in classes:
            cur_bold = True
            cur_color = "15803D"
        elif "st-warn" in classes:
            cur_bold = True
            cur_color = "B45309"
        elif "grp-badge" in classes:
            txt = node.get_text(strip=True)
            badge_col = _hex_from_style(style_str, "background", "") or "1E3A8A"
            return self._make_run(f"[{txt}] ", bold=True, color=badge_col, sz=cur_sz)
        elif "gloss-pill" in classes:
            return self._make_run(f"【{node.get_text(strip=True)}】", bold=True, color="B45309", sz=cur_sz)
        elif "lb-pill-deep" in classes:
            return self._make_run(f"【{node.get_text(strip=True)}】", bold=True, color="1D4ED8", sz=cur_sz)
        elif "lb-pill-pro" in classes:
            return self._make_run(f"【{node.get_text(strip=True)}】", bold=True, color="475569", sz=cur_sz)

        if name == "a":
            href = (node.get("href") or "").strip()
            is_ext = href.startswith(("http://", "https://"))
            inner_runs = "".join(
                self._inline_to_runs(
                    child, bold=cur_bold, italic=cur_italic, color="1D4ED8", sz=cur_sz, code=cur_code, underline=is_ext
                )
                for child in node.children
            ) or self._make_run(node.get_text(), bold=cur_bold, italic=cur_italic, color="1D4ED8", sz=cur_sz, underline=is_ext)
            if is_ext:
                rid = self._register_hyperlink(href)
                return f'<w:hyperlink r:id="{rid}" w:history="1">{inner_runs}</w:hyperlink>'
            return inner_runs

        if name == "code":
            cur_color = _hex_from_style(style_str, "color", "") or "1E3A8A"
            cur_sz = max(14, cur_sz - 2) if cur_sz else 18

        return "".join(
            self._inline_to_runs(
                child, bold=cur_bold, italic=cur_italic, color=cur_color, sz=cur_sz, code=cur_code, underline=cur_ul
            )
            for child in node.children
        )

    def _make_p(
        self,
        runs_xml: str,
        before: int = 40,
        after: int = 100,
        line: int = 330,
        align: str | None = None,
        keep_next: bool = False,
        keep_lines: bool = False,
        page_break_before: bool = False,
        left_indent: int = 0,
        hanging: int = 0,
        bottom_border_color: str | None = None,
        shading_fill: str | None = None,
    ) -> str:
        ppr_parts = []
        if keep_next:
            ppr_parts.append("<w:keepNext/>")
        if keep_lines:
            ppr_parts.append("<w:keepLines/>")
        if page_break_before:
            ppr_parts.append("<w:pageBreakBefore/>")
        if bottom_border_color:
            ppr_parts.append(
                f'<w:pBdr><w:bottom w:val="single" w:sz="10" w:space="4" w:color="{bottom_border_color}"/></w:pBdr>'
            )
        if shading_fill:
            ppr_parts.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shading_fill}"/>')
        ppr_parts.append(f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>')
        if left_indent or hanging:
            ind_attrs = []
            if left_indent:
                ind_attrs.append(f'w:left="{left_indent}"')
            if hanging:
                ind_attrs.append(f'w:hanging="{hanging}"')
            ppr_parts.append(f'<w:ind {" ".join(ind_attrs)}/>')
        if align in ("left", "center", "right", "both"):
            ppr_parts.append(f'<w:jc w:val="{align}"/>')
        return f"<w:p><w:pPr>{''.join(ppr_parts)}</w:pPr>{runs_xml}</w:p>"

    def _make_drawing_p(self, marker: str, png_path: Path, page_break_before: bool = False) -> str:
        rid, pw, ph = self._register_image(png_path)
        self._used_charts.add(marker)
        # Max usable width = 6.10in, max height = 8.20in (preserves exact aspect ratio on A4!)
        max_w_emu = int(6.10 * 914400)
        max_h_emu = int(8.20 * 914400)
        cx = max_w_emu
        cy = int(round(cx * (ph / max(pw, 1))))
        if cy > max_h_emu:
            scale = max_h_emu / float(cy)
            cy = max_h_emu
            cx = int(round(cx * scale))
        docpr_id = self._next_docpr()
        cnvpr_id = self._next_docpr()
        name = _xe(f"Chart_{self._img_seq}.png")
        pb_tag = "<w:pageBreakBefore/>" if page_break_before else ""
        return (
            '<w:p>'
            f'<w:pPr><w:keepLines/>{pb_tag}<w:spacing w:before="100" w:after="120"/><w:jc w:val="center"/></w:pPr>'
            '<w:r><w:drawing>'
            '<wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/>'
            '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{docpr_id}" name="{name}"/>'
            '<wp:cNvGraphicFramePr>'
            '<a:graphicFrameLocks noChangeAspect="1"/>'
            '</wp:cNvGraphicFramePr>'
            '<a:graphic>'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<pic:pic>'
            '<pic:nvPicPr>'
            f'<pic:cNvPr id="{cnvpr_id}" name="{name}"/>'
            '<pic:cNvPicPr><a:picLocks noChangeAspect="1"/></pic:cNvPicPr>'
            '</pic:nvPicPr>'
            '<pic:blipFill>'
            f'<a:blip r:embed="{rid}" cstate="print"/>'
            '<a:stretch><a:fillRect/></a:stretch>'
            '</pic:blipFill>'
            '<pic:spPr>'
            f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            '</pic:spPr>'
            '</pic:pic>'
            '</a:graphicData>'
            '</a:graphic>'
            '</wp:inline>'
            '</w:drawing></w:r>'
            '</w:p>'
        )

    def _make_card_table(
        self,
        inner_paragraphs: list[str],
        left_color: str = "0284C7",
        fill_color: str = "F0F9FF",
        outer_border: str = "E2E8F0",
        bottom_color: str | None = None,
        pad_tb: int = 110,
        pad_lr: int = 160,
        cant_split: bool = True,
        page_break_before: bool = False,
        keep_with_next: bool = False,
    ) -> str:
        """Cross-platform 1x1 card table in strict ECMA-376 order + standalone hard page break."""
        pb_xml = (
            '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="40" w:lineRule="auto"/></w:pPr>'
            '<w:r><w:br w:type="page"/></w:r></w:p>'
            if page_break_before
            else ""
        )
        b_top = f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{outer_border}"/>' if outer_border else '<w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        b_right = f'<w:right w:val="single" w:sz="4" w:space="0" w:color="{outer_border}"/>' if outer_border else '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        b_bot = (
            f'<w:bottom w:val="single" w:sz="18" w:space="0" w:color="{bottom_color}"/>'
            if bottom_color
            else (f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="{outer_border}"/>' if outer_border else '<w:bottom w:val="none" w:sz="0" w:space="0" w:color="auto"/>')
        )
        b_left = f'<w:left w:val="single" w:sz="24" w:space="0" w:color="{left_color}"/>' if left_color else '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        trpr = "<w:trPr><w:cantSplit/></w:trPr>" if cant_split else ""
        content = "".join(inner_paragraphs) or "<w:p/>"
        spacer_kn = "<w:keepNext/>" if keep_with_next else ""
        return (
            f"{pb_xml}"
            '<w:tbl>'
            '<w:tblPr>'
            f'<w:tblW w:w="{CONTENT_W_DXA}" w:type="dxa"/>'
            '<w:tblLayout w:type="fixed"/>'
            f'<w:tblCellMar><w:top w:w="{pad_tb}" w:type="dxa"/><w:left w:w="{pad_lr}" w:type="dxa"/>'
            f'<w:bottom w:w="{pad_tb}" w:type="dxa"/><w:right w:w="{pad_lr}" w:type="dxa"/></w:tblCellMar>'
            '</w:tblPr>'
            f'<w:tblGrid><w:gridCol w:w="{CONTENT_W_DXA}"/></w:tblGrid>'
            f'<w:tr>{trpr}<w:tc>'
            f'<w:tcPr><w:tcW w:w="{CONTENT_W_DXA}" w:type="dxa"/>'
            f'<w:tcBorders>{b_top}{b_left}{b_bot}{b_right}</w:tcBorders>'
            f'<w:shd w:val="clear" w:color="auto" w:fill="{fill_color}"/></w:tcPr>'
            f'{content}</w:tc></w:tr>'
            '</w:tbl>'
            f'<w:p><w:pPr>{spacer_kn}<w:spacing w:before="0" w:after="80" w:line="120" w:lineRule="auto"/></w:pPr></w:p>'
        )

    def _render_list(
        self,
        list_tag: Tag,
        level: int = 0,
        ordered: bool = False,
        base_sz: int = 20,
        text_color: str = "1F2937",
        page_break_first: bool = False,
    ) -> list[str]:
        out: list[str] = []
        try:
            idx = int(list_tag.get("start", 1))
        except (TypeError, ValueError):
            idx = 1
        first = True
        for li in list_tag.find_all("li", recursive=False):
            sub_lists = [c for c in li.children if isinstance(c, Tag) and c.name in ("ul", "ol")]
            inline_nodes = [c for c in li.children if not (isinstance(c, Tag) and c.name in ("ul", "ol"))]
            prefix = f"{idx}. " if ordered else ("• " if level == 0 else "◦ ")
            idx += 1
            runs = self._make_run(prefix, bold=True, color="1E3A8A" if ordered else "475569", sz=base_sz)
            for node in inline_nodes:
                runs += self._inline_to_runs(node, color=text_color, sz=base_sz)
            indent = 360 + level * 280
            out.append(
                self._make_p(
                    runs,
                    before=20,
                    after=55,
                    line=320,
                    left_indent=indent,
                    hanging=220,
                    page_break_before=(page_break_first and first),
                )
            )
            first = False
            for sl in sub_lists:
                out.extend(
                    self._render_list(
                        sl,
                        level=level + 1,
                        ordered=(sl.name == "ol"),
                        base_sz=max(16, base_sz - 1),
                        text_color=text_color,
                    )
                )
        return out

    def _render_html_table(self, tbl: Tag, compact: bool = False, page_break_before: bool = False) -> str:
        """Convert an HTML <table> into a strict ECMA-376 <w:tbl> with safe two-pass column widths."""
        classes = set(tbl.get("class") or [])
        is_sn = "sn-table" in classes
        is_gloss = "glossary-table" in classes
        is_kpi = "kpi-table" in classes

        rows_tags: list[tuple[bool, Tag]] = []
        thead = tbl.find("thead", recursive=False)
        if thead:
            for tr in thead.find_all("tr", recursive=False):
                rows_tags.append((True, tr))
        tbody = tbl.find("tbody", recursive=False)
        if tbody:
            for tr in tbody.find_all("tr", recursive=False):
                rows_tags.append((False, tr))
        if not rows_tags:
            for i, tr in enumerate(tbl.find_all("tr", recursive=False)):
                is_hdr = bool(tr.find("th", recursive=False)) and i == 0
                rows_tags.append((is_hdr, tr))
        if not rows_tags:
            return ""

        ncols = max(len(tr.find_all(["th", "td"], recursive=False)) for _, tr in rows_tags)
        if ncols <= 0:
            return ""

        pad_lr = 100 if ncols <= 5 else 70
        pad_tb = 75 if not is_kpi else 95
        font_pt = 8.5 if (compact or ncols >= 6) else 9.0

        # Two-pass safe column width allocation (never negative, reserves physical width for col-nowrap)
        if is_kpi:
            col_widths = [CONTENT_W_DXA // ncols] * ncols
            flex_idxs = list(range(ncols))
        elif is_sn and ncols == 2:
            col_widths = [int(CONTENT_W_DXA * 0.46), CONTENT_W_DXA - int(CONTENT_W_DXA * 0.46)]
            flex_idxs = [0, 1]
        elif is_gloss and ncols == 2:
            col_widths = [int(CONTENT_W_DXA * 0.27), CONTENT_W_DXA - int(CONTENT_W_DXA * 0.27)]
            flex_idxs = [0, 1]
        else:
            col_scores = [4.0] * ncols
            col_nowrap = [False] * ncols
            for _, tr in rows_tags:
                cells = tr.find_all(["th", "td"], recursive=False)
                for ci, cell in enumerate(cells[:ncols]):
                    if "col-nowrap" in (cell.get("class") or []):
                        col_nowrap[ci] = True
                    txt = cell.get_text(" ", strip=True)
                    w = _vis_width(txt)
                    eff = min(w, 34.0) if not col_nowrap[ci] else max(w + 1.0, 5.5)
                    col_scores[ci] = max(col_scores[ci], eff)

            col_widths = [0] * ncols
            nw_req: dict[int, int] = {}
            for ci in range(ncols):
                if col_nowrap[ci]:
                    nw_req[ci] = max(920, int(round(col_scores[ci] * font_pt * 20 + 2 * pad_lr + 160)))
            nw_budget = int(CONTENT_W_DXA * 0.58)
            if sum(nw_req.values()) > nw_budget and nw_req:
                scale = nw_budget / float(sum(nw_req.values()))
                nw_req = {ci: max(640, int(round(w * scale))) for ci, w in nw_req.items()}
            for ci, w in nw_req.items():
                col_widths[ci] = w

            flex_idxs = [ci for ci in range(ncols) if ci not in nw_req]
            rem = CONTENT_W_DXA - sum(col_widths)
            if flex_idxs:
                min_flex = min(780, max(360, rem // max(len(flex_idxs) * 2, 1)))
                flex_total = sum(col_scores[ci] for ci in flex_idxs) or 1.0
                for ci in flex_idxs:
                    col_widths[ci] = max(min_flex, int(round(rem * (col_scores[ci] / flex_total))))
            if sum(col_widths) > CONTENT_W_DXA:
                scale = CONTENT_W_DXA / float(sum(col_widths))
                col_widths = [max(300, int(w * scale)) for w in col_widths]

        delta = CONTENT_W_DXA - sum(col_widths)
        target_pool = flex_idxs or list(range(ncols))
        widest_idx = max(target_pool, key=lambda i: col_widths[i])
        col_widths[widest_idx] += delta
        if any(w <= 0 for w in col_widths):
            base_w = CONTENT_W_DXA // ncols
            col_widths = [base_w] * ncols
            col_widths[-1] += CONTENT_W_DXA - sum(col_widths)

        grid_xml = "".join(f'<w:gridCol w:w="{w}"/>' for w in col_widths)
        rows_xml = []
        body_row_idx = 0
        for is_hdr, tr in rows_tags:
            cells = tr.find_all(["th", "td"], recursive=False)
            row_chars = sum(len(c.get_text(" ", strip=True)) for c in cells)
            allow_split = (not is_hdr) and (is_sn or row_chars > 450)
            trpr_parts = []
            if not allow_split:
                trpr_parts.append("<w:cantSplit/>")
            if is_hdr:
                trpr_parts.append("<w:tblHeader/>")
            tr_cells_xml = []
            for ci in range(ncols):
                cw = col_widths[ci]
                cell = cells[ci] if ci < len(cells) else None
                cell_cls = set(cell.get("class") or []) if cell else set()
                cell_style = (cell.get("style") or "") if cell else ""
                align = "center" if "ta-c" in cell_cls else ("right" if "ta-r" in cell_cls else "left")

                # Cell fill & text color
                if is_hdr:
                    fill = _hex_from_style(cell_style, "background", "1E293B")
                    txt_col = _hex_from_style(cell_style, "color", "FFFFFF")
                    sz = 17
                    bold_def = True
                elif is_kpi:
                    fill = "F8FAFC"
                    txt_col = "1F2937"
                    sz = 17
                    bold_def = False
                elif is_sn:
                    fill = _hex_from_style(cell_style, "background", "F8FAFC")
                    txt_col = "1F2937"
                    sz = 18
                    bold_def = False
                elif is_gloss:
                    fill = "FFFBEB"
                    txt_col = "78350F" if ci == 0 else "374151"
                    sz = 17
                    bold_def = (ci == 0)
                else:
                    fill = "F8FAFC" if (body_row_idx % 2 == 1) else "FFFFFF"
                    txt_col = "1F2937"
                    sz = 17 if (compact or ncols >= 6) else 18
                    bold_def = False

                # Cell borders
                if is_kpi:
                    borders = (
                        '<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                        '<w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                        '<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                    )
                elif is_hdr:
                    borders = (
                        '<w:top w:val="single" w:sz="12" w:space="0" w:color="0F172A"/>'
                        '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                        '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="334155"/>'
                        '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                    )
                elif is_gloss:
                    borders = (
                        '<w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                        '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                        '<w:bottom w:val="dashed" w:sz="4" w:space="0" w:color="FCD34D"/>'
                        '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                    )
                else:
                    borders = (
                        '<w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                        '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
                        '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                    )

                # Render cell body (supports mixed inline + inner <ul>/<ol>)
                cell_ps: list[str] = []
                if cell:
                    direct_lists = cell.find_all(["ul", "ol"], recursive=False)
                    if direct_lists:
                        inline_buf = ""
                        for child in cell.children:
                            if isinstance(child, Tag) and child.name in ("ul", "ol"):
                                if inline_buf.strip():
                                    cell_ps.append(self._make_p(inline_buf, before=20, after=30, line=280, align=align))
                                    inline_buf = ""
                                cell_ps.extend(self._render_list(child, ordered=(child.name == "ol"), base_sz=sz, text_color=txt_col))
                            elif isinstance(child, Tag) and child.name in ("p", "div"):
                                if inline_buf.strip():
                                    cell_ps.append(self._make_p(inline_buf, before=20, after=30, line=280, align=align))
                                    inline_buf = ""
                                r = self._inline_to_runs(child, bold=bold_def, color=txt_col, sz=sz)
                                if r:
                                    cell_ps.append(self._make_p(r, before=20, after=40, line=280, align=align))
                            else:
                                inline_buf += self._inline_to_runs(child, bold=bold_def, color=txt_col, sz=sz)
                        if inline_buf.strip():
                            cell_ps.append(self._make_p(inline_buf, before=20, after=30, line=280, align=align))
                    else:
                        r = "".join(
                            self._inline_to_runs(ch, bold=bold_def, color=txt_col, sz=sz)
                            for ch in cell.children
                        )
                        cell_ps.append(self._make_p(r, before=30, after=30, line=280, align=align))
                if not cell_ps:
                    cell_ps = [self._make_p("", before=20, after=20, line=260)]

                tr_cells_xml.append(
                    f'<w:tc><w:tcPr><w:tcW w:w="{cw}" w:type="dxa"/>'
                    f'<w:tcBorders>{borders}</w:tcBorders>'
                    f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
                    '<w:vAlign w:val="top"/></w:tcPr>'
                    f'{"".join(cell_ps)}</w:tc>'
                )
            if not is_hdr:
                body_row_idx += 1
            trpr_xml = f'<w:trPr>{"".join(trpr_parts)}</w:trPr>' if trpr_parts else ""
            rows_xml.append(f'<w:tr>{trpr_xml}{"".join(tr_cells_xml)}</w:tr>')

        if is_gloss:
            tbl_borders = (
                '<w:tblBorders>'
                '<w:top w:val="single" w:sz="6" w:space="0" w:color="FDE68A"/>'
                '<w:left w:val="single" w:sz="20" w:space="0" w:color="D97706"/>'
                '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="FDE68A"/>'
                '<w:right w:val="single" w:sz="6" w:space="0" w:color="FDE68A"/>'
                '<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                '</w:tblBorders>'
            )
        elif is_kpi:
            tbl_borders = (
                '<w:tblBorders>'
                '<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '<w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '</w:tblBorders>'
            )
        else:
            tbl_borders = (
                '<w:tblBorders>'
                '<w:top w:val="single" w:sz="10" w:space="0" w:color="0F172A"/>'
                '<w:bottom w:val="single" w:sz="10" w:space="0" w:color="0F172A"/>'
                '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                '<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
                '</w:tblBorders>'
            )
        pb_xml = (
            '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="40" w:lineRule="auto"/></w:pPr>'
            '<w:r><w:br w:type="page"/></w:r></w:p>'
            if page_break_before
            else ""
        )
        # Strict ECMA-376 CT_TblPrBase order: tblW -> tblBorders -> tblLayout -> tblCellMar!
        return (
            f"{pb_xml}"
            '<w:tbl>'
            '<w:tblPr>'
            f'<w:tblW w:w="{CONTENT_W_DXA}" w:type="dxa"/>'
            f'{tbl_borders}'
            '<w:tblLayout w:type="fixed"/>'
            f'<w:tblCellMar><w:top w:w="{pad_tb}" w:type="dxa"/><w:left w:w="{pad_lr}" w:type="dxa"/>'
            f'<w:bottom w:w="{pad_tb}" w:type="dxa"/><w:right w:w="{pad_lr}" w:type="dxa"/></w:tblCellMar>'
            '</w:tblPr>'
            f'<w:tblGrid>{grid_xml}</w:tblGrid>'
            f'{"".join(rows_xml)}'
            '</w:tbl>'
            '<w:p><w:pPr><w:spacing w:before="0" w:after="90" w:line="120" w:lineRule="auto"/></w:pPr></w:p>'
        )

    def _render_cover_banner(self, div: Tag, page_break_before: bool = False) -> list[str]:
        """Render dark-slate magazine cover banner + crisp native 2x3 KPI table preserving colored vector dots."""
        blocks: list[str] = []
        inner: list[str] = []
        accent = _hex_from_style(div.get("style", ""), "border-bottom", "B45309")
        tag_el = div.find(class_="cover-tag")
        if tag_el:
            inner.append(
                self._make_p(
                    self._inline_to_runs(tag_el, bold=True, color="FBBF24", sz=17),
                    before=20,
                    after=60,
                    line=260,
                )
            )
        title_el = div.find(class_="cover-title")
        if title_el:
            inner.append(self._make_p(self._inline_to_runs(title_el, bold=True, color="FFFFFF", sz=30), before=20, after=80, line=340))
        meta_el = div.find(class_="cover-meta")
        if meta_el:
            inner.append(self._make_p(self._inline_to_runs(meta_el, color="CBD5E1", sz=17), before=10, after=30, line=270))
        blocks.append(
            self._make_card_table(
                inner,
                left_color="",
                fill_color="0F172A",
                outer_border="0F172A",
                bottom_color=accent,
                pad_tb=150,
                pad_lr=190,
                page_break_before=page_break_before,
            )
        )
        # Render KPI cards directly as a native OOXML table (supports 3-col 2x3 and 4-col .cols-4 strips)
        kpi_strip = div.find(class_="kpi-strip")
        strip_classes = set(kpi_strip.get("class") or []) if kpi_strip else set()
        cards = div.find_all(class_="kpi-card")
        if cards:
            ncols = 4 if ("cols-4" in strip_classes or len(cards) == 4) else (2 if len(cards) == 2 else 3)
            w_base = CONTENT_W_DXA // ncols
            col_ws = [w_base] * (ncols - 1) + [CONTENT_W_DXA - w_base * (ncols - 1)]
            val_sz = 19 if ncols == 4 else 21
            pad_lr = 80 if ncols == 4 else 100
            grid_xml = "".join(f'<w:gridCol w:w="{cw}"/>' for cw in col_ws)
            rows_xml: list[str] = []
            for i in range(0, len(cards), ncols):
                chunk = cards[i : i + ncols]
                tcs: list[str] = []
                for c_idx in range(ncols):
                    cw = col_ws[c_idx]
                    if c_idx < len(chunk):
                        c = chunk[c_idx]
                        lbl = c.find(class_="kpi-label")
                        val = c.find(class_="kpi-val")
                        sub = c.find(class_="kpi-sub")
                        cell_ps: list[str] = []
                        if lbl:
                            cell_ps.append(
                                self._make_p(
                                    self._inline_to_runs(lbl, color="475569", sz=15),
                                    before=0,
                                    after=20,
                                    line=230,
                                )
                            )
                        if val:
                            cell_ps.append(
                                self._make_p(
                                    self._inline_to_runs(val, bold=True, color="B45309", sz=val_sz),
                                    before=0,
                                    after=25,
                                    line=260,
                                )
                            )
                        if sub:
                            cell_ps.append(
                                self._make_p(
                                    self._inline_to_runs(sub, color="475569", sz=15),
                                    before=0,
                                    after=0,
                                    line=230,
                                )
                            )
                        if not cell_ps:
                            cell_ps = ["<w:p/>"]
                        fill = "F8FAFC"
                    else:
                        cell_ps = ["<w:p/>"]
                        fill = "FFFFFF"
                    tcs.append(
                        f'<w:tc><w:tcPr><w:tcW w:w="{cw}" w:type="dxa"/>'
                        f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>'
                        '<w:vAlign w:val="top"/></w:tcPr>'
                        f'{"".join(cell_ps)}</w:tc>'
                    )
                rows_xml.append(f'<w:tr><w:trPr><w:cantSplit/></w:trPr>{"".join(tcs)}</w:tr>')
            kpi_tbl = (
                '<w:tbl>'
                '<w:tblPr>'
                f'<w:tblW w:w="{CONTENT_W_DXA}" w:type="dxa"/>'
                '<w:tblBorders>'
                '<w:top w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '<w:left w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '<w:right w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
                '</w:tblBorders>'
                '<w:tblLayout w:type="fixed"/>'
                f'<w:tblCellMar><w:top w:w="85" w:type="dxa"/><w:left w:w="{pad_lr}" w:type="dxa"/>'
                f'<w:bottom w:w="85" w:type="dxa"/><w:right w:w="{pad_lr}" w:type="dxa"/></w:tblCellMar>'
                '</w:tblPr>'
                f'<w:tblGrid>{grid_xml}</w:tblGrid>'
                f'{"".join(rows_xml)}'
                '</w:tbl>'
                '<w:p><w:pPr><w:spacing w:before="0" w:after="90" w:line="120" w:lineRule="auto"/></w:pPr></w:p>'
            )
            blocks.append(kpi_tbl)
        return blocks

    def _render_sn_grid(self, grid: Tag, page_break_before: bool = False) -> str:
        """Render 2-column .sn-grid (.sn-col-sig / .sn-col-noi) as a native 2-column ECMA-376 <w:tbl>."""
        sig_col = grid.find(class_="sn-col-sig")
        noi_col = grid.find(class_="sn-col-noi")
        if not sig_col or not noi_col:
            direct_cols = [c for c in grid.find_all("div", recursive=False)]
            if len(direct_cols) >= 2:
                sig_col = sig_col or direct_cols[0]
                noi_col = noi_col or direct_cols[1]
        col_specs = [
            (sig_col, "0F3D2E", "F0FDF4"),
            (noi_col, "475569", "F8FAFC"),
        ]
        w_left = int(CONTENT_W_DXA * 0.46)
        col_widths = [w_left, CONTENT_W_DXA - w_left]
        grid_xml = "".join(f'<w:gridCol w:w="{cw}"/>' for cw in col_widths)

        hdr_borders = (
            '<w:top w:val="single" w:sz="12" w:space="0" w:color="0F172A"/>'
            '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:bottom w:val="single" w:sz="8" w:space="0" w:color="334155"/>'
            '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        )
        body_borders = (
            '<w:top w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>'
            '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        )

        hdr_tcs: list[str] = []
        body_tcs: list[str] = []
        for idx, (col_el, hdr_bg, body_bg) in enumerate(col_specs):
            cw = col_widths[idx]
            head_el = col_el.find(class_="sn-col-head") if col_el else None
            head_runs = self._inline_to_runs(head_el, bold=True, color="FFFFFF", sz=17) if head_el else ""
            hdr_tcs.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{cw}" w:type="dxa"/>'
                f'<w:tcBorders>{hdr_borders}</w:tcBorders>'
                f'<w:shd w:val="clear" w:color="auto" w:fill="{hdr_bg}"/>'
                '<w:vAlign w:val="top"/></w:tcPr>'
                f'{self._make_p(head_runs, before=30, after=30, line=280)}</w:tc>'
            )

            body_el = (col_el.find(class_="sn-col-body") if col_el else None) or col_el
            cell_ps: list[str] = []
            if body_el:
                lists = body_el.find_all(["ul", "ol"], recursive=False)
                if lists:
                    for lst in lists:
                        cell_ps.extend(
                            self._render_list(lst, ordered=(lst.name == "ol"), base_sz=18, text_color="1F2937")
                        )
                else:
                    for sub_el in body_el.children:
                        if isinstance(sub_el, NavigableString) and not str(sub_el).strip():
                            continue
                        if isinstance(sub_el, Tag) and "sn-col-head" in (sub_el.get("class") or []):
                            continue
                        if isinstance(sub_el, Tag) and sub_el.name in ("ul", "ol"):
                            cell_ps.extend(
                                self._render_list(sub_el, ordered=(sub_el.name == "ol"), base_sz=18, text_color="1F2937")
                            )
                        else:
                            runs = self._inline_to_runs(sub_el, color="1F2937", sz=18)
                            if runs:
                                cell_ps.append(self._make_p(runs, before=20, after=35, line=280))
            if not cell_ps:
                cell_ps = [self._make_p("", before=20, after=20, line=260)]
            body_tcs.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{cw}" w:type="dxa"/>'
                f'<w:tcBorders>{body_borders}</w:tcBorders>'
                f'<w:shd w:val="clear" w:color="auto" w:fill="{body_bg}"/>'
                '<w:vAlign w:val="top"/></w:tcPr>'
                f'{"".join(cell_ps)}</w:tc>'
            )

        tbl_borders = (
            '<w:tblBorders>'
            '<w:top w:val="single" w:sz="10" w:space="0" w:color="0F172A"/>'
            '<w:bottom w:val="single" w:sz="10" w:space="0" w:color="0F172A"/>'
            '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
            '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
            '</w:tblBorders>'
        )
        pb_xml = (
            '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="40" w:lineRule="auto"/></w:pPr>'
            '<w:r><w:br w:type="page"/></w:r></w:p>'
            if page_break_before
            else ""
        )
        return (
            f"{pb_xml}"
            '<w:tbl>'
            '<w:tblPr>'
            f'<w:tblW w:w="{CONTENT_W_DXA}" w:type="dxa"/>'
            f'{tbl_borders}'
            '<w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:top w:w="75" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
            '<w:bottom w:w="75" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
            '</w:tblPr>'
            f'<w:tblGrid>{grid_xml}</w:tblGrid>'
            f'<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>{"".join(hdr_tcs)}</w:tr>'
            f'<w:tr>{"".join(body_tcs)}</w:tr>'
            '</w:tbl>'
            '<w:p><w:pPr><w:spacing w:before="0" w:after="90" w:line="120" w:lineRule="auto"/></w:pPr></w:p>'
        )

    def _render_verdict_card(self, div: Tag, page_break_before: bool = False) -> str:
        style_str = div.get("style", "")
        brd = _hex_from_style(style_str, "border-left", "475569")
        bg = _hex_from_style(style_str, "background", "F8FAFC")
        inner: list[str] = []
        badge = div.find(class_="verdict-badge")
        light = div.find(class_="verdict-light")
        top_runs = ""
        if badge:
            top_runs += (
                self._make_run("【", bold=True, color=brd, sz=18)
                + self._inline_to_runs(badge, bold=True, color=brd, sz=18)
                + self._make_run("】  ", bold=True, color=brd, sz=18)
            )
        if light:
            top_runs += self._inline_to_runs(light, bold=True, color="0F172A", sz=18)
        if top_runs:
            inner.append(self._make_p(top_runs, before=20, after=60, line=280))
        hl = div.find(class_="verdict-headline")
        if hl:
            hl_col = _hex_from_style(hl.get("style", ""), "color", "0F172A")
            inner.append(self._make_p(self._inline_to_runs(hl, bold=True, color=hl_col, sz=22), before=20, after=70, line=320))
        ul = div.find("ul")
        if ul:
            inner.extend(self._render_list(ul, base_sz=19, text_color="1F2937"))
        risk = div.find(class_="verdict-risk")
        if risk:
            inner.append(self._make_p(self._inline_to_runs(risk, color="7F1D1D", sz=18), before=50, after=20, line=280, shading_fill="FEE2E2"))
        return self._make_card_table(
            inner,
            left_color=brd,
            fill_color=bg,
            outer_border="CBD5E1",
            page_break_before=page_break_before,
        )

    def _render_persona_wrap(self, div: Tag, page_break_before: bool = False) -> list[str]:
        out: list[str] = []
        t_el = div.find(class_="persona-title")
        pb_used = False
        if t_el:
            out.append(
                self._make_p(
                    self._inline_to_runs(t_el, bold=True, color="0F172A", sz=21),
                    before=100,
                    after=80,
                    keep_next=True,
                    page_break_before=page_break_before,
                )
            )
            pb_used = True
        for card in div.find_all(class_="persona-card"):
            st = card.get("style", "")
            brd = _hex_from_style(st, "border-left", "0284C7")
            bg = _hex_from_style(st, "background", "F8FAFC")
            inner: list[str] = []
            head = card.find(class_="persona-head")
            if head:
                inner.append(self._make_p(self._inline_to_runs(head, bold=True, color="0F172A", sz=20), before=10, after=30, line=290))
            sub = card.find(class_="persona-sub")
            if sub:
                inner.append(self._make_p(self._inline_to_runs(sub, color="475569", sz=17), before=0, after=45, line=260))
            ul = card.find("ul")
            if ul:
                inner.extend(self._render_list(ul, base_sz=18, text_color="1F2937"))
            av = card.find(class_="persona-avoid")
            if av:
                inner.append(self._make_p(self._inline_to_runs(av, color="991B1B", sz=17), before=40, after=10, line=260, shading_fill="FEE2E2"))
            out.append(
                self._make_card_table(
                    inner,
                    left_color=brd,
                    fill_color=bg,
                    outer_border="E2E8F0",
                    pad_tb=90,
                    pad_lr=140,
                    page_break_before=(page_break_before and not pb_used),
                )
            )
            pb_used = True
        return out

    def _walk(self, container: Tag, pending_break: bool = False) -> bool:
        for child in container.children:
            if not isinstance(child, Tag):
                continue
            name = child.name.lower()
            classes = set(child.get("class") or [])

            if "volume-break" in classes:
                pending_break = True
                continue

            if "cover-banner" in classes:
                self.body_blocks.extend(self._render_cover_banner(child, page_break_before=pending_break))
                pending_break = False
                continue

            if "verdict-card" in classes:
                self.body_blocks.append(self._render_verdict_card(child, page_break_before=pending_break))
                pending_break = False
                continue

            if "sn-box" in classes:
                t_el = child.find(class_="sn-title")
                pb_tbl = pending_break
                if t_el:
                    self.body_blocks.append(
                        self._make_p(
                            self._inline_to_runs(t_el, bold=True, color="0F172A", sz=20),
                            before=90,
                            after=60,
                            keep_next=True,
                            page_break_before=pending_break,
                        )
                    )
                    pb_tbl = False
                tbl = child.find("table")
                if tbl:
                    self.body_blocks.append(self._render_html_table(tbl, page_break_before=pb_tbl))
                else:
                    grid = child.find(class_="sn-grid")
                    if grid:
                        self.body_blocks.append(self._render_sn_grid(grid, page_break_before=pb_tbl))
                pending_break = False
                continue

            if "sn-grid" in classes:
                self.body_blocks.append(self._render_sn_grid(child, page_break_before=pending_break))
                pending_break = False
                continue

            if "persona-wrap" in classes:
                self.body_blocks.extend(self._render_persona_wrap(child, page_break_before=pending_break))
                pending_break = False
                continue

            if "glossary-box" in classes:
                t_el = child.find(class_="glossary-title")
                pb_tbl = pending_break
                if t_el:
                    self.body_blocks.append(
                        self._make_p(
                            self._inline_to_runs(t_el, bold=True, color="92400E", sz=19),
                            before=90,
                            after=30,
                            keep_next=True,
                            page_break_before=pending_break,
                            bottom_border_color="FDE68A",
                            shading_fill="FFFBEB",
                        )
                    )
                    pb_tbl = False
                tbl = child.find("table")
                if tbl:
                    self.body_blocks.append(self._render_html_table(tbl, page_break_before=pb_tbl))
                pending_break = False
                continue

            if "glossary-title" in classes:
                self.body_blocks.append(
                    self._make_p(
                        self._inline_to_runs(child, bold=True, color="92400E", sz=19),
                        before=90,
                        after=30,
                        keep_next=True,
                        page_break_before=pending_break,
                        bottom_border_color="FDE68A",
                        shading_fill="FFFBEB",
                    )
                )
                pending_break = False
                continue

            if "trust-box" in classes:
                inner: list[str] = []
                t_el = child.find(class_="trust-title")
                if t_el:
                    inner.append(self._make_p(self._inline_to_runs(t_el, bold=True, color="0F172A", sz=19), before=10, after=45))
                ul = child.find("ul")
                if ul:
                    inner.extend(self._render_list(ul, base_sz=18, text_color="334155"))
                note = child.find(class_="trust-note")
                if note:
                    inner.append(self._make_p(self._inline_to_runs(note, color="64748B", sz=17), before=40, after=10))
                self.body_blocks.append(
                    self._make_card_table(
                        inner,
                        left_color="475569",
                        fill_color="F8FAFC",
                        outer_border="CBD5E1",
                        page_break_before=pending_break,
                    )
                )
                pending_break = False
                continue

            if "layer-badge-pro" in classes or "layer-badge-deep" in classes:
                col = "475569" if "layer-badge-pro" in classes else "1D4ED8"
                bg = "F8FAFC" if "layer-badge-pro" in classes else "EFF6FF"
                p = self._make_p(self._inline_to_runs(child, bold=True, color=col, sz=18), before=20, after=20, line=270, keep_next=True)
                self.body_blocks.append(
                    self._make_card_table(
                        [p],
                        left_color=col,
                        fill_color=bg,
                        outer_border="",
                        pad_tb=65,
                        pad_lr=120,
                        page_break_before=pending_break,
                        keep_with_next=True,
                    )
                )
                pending_break = False
                continue

            if "callout" in classes or name == "blockquote":
                p = self._make_p(self._inline_to_runs(child, color="0C4A6E", sz=19), before=20, after=20, line=310)
                self.body_blocks.append(
                    self._make_card_table(
                        [p],
                        left_color="0284C7",
                        fill_color="F0F9FF",
                        outer_border="BAE6FD",
                        pad_tb=90,
                        pad_lr=140,
                        page_break_before=pending_break,
                    )
                )
                pending_break = False
                continue

            if "footer-note" in classes:
                p = self._make_p(
                    self._inline_to_runs(child, color="64748B", sz=16),
                    before=160,
                    after=40,
                    align="center",
                    bottom_border_color=None,
                    page_break_before=pending_break,
                )
                self.body_blocks.append(p)
                pending_break = False
                continue

            if "table-wrap" in classes:
                tbl = child.find("table")
                if tbl:
                    self.body_blocks.append(self._render_html_table(tbl, page_break_before=pending_break))
                pending_break = False
                continue

            if name == "h1":
                p = self._make_p(self._inline_to_runs(child, bold=True, color="1E3A8A", sz=26), before=30, after=30, line=320, keep_next=True)
                self.body_blocks.append(
                    self._make_card_table(
                        [p],
                        left_color="1D4ED8",
                        fill_color="EFF6FF",
                        outer_border="",
                        pad_tb=95,
                        pad_lr=140,
                        page_break_before=pending_break,
                        keep_with_next=True,
                    )
                )
                pending_break = False
                continue

            if name == "h2":
                self.body_blocks.append(
                    self._make_p(
                        self._inline_to_runs(child, bold=True, color="0F172A", sz=23),
                        before=200,
                        after=90,
                        line=310,
                        keep_next=True,
                        page_break_before=pending_break,
                        bottom_border_color="CBD5E1",
                    )
                )
                pending_break = False
                continue

            if name == "h3":
                self.body_blocks.append(
                    self._make_p(
                        self._inline_to_runs(child, bold=True, color="1E40AF", sz=21),
                        before=150,
                        after=60,
                        line=300,
                        keep_next=True,
                        page_break_before=pending_break,
                    )
                )
                pending_break = False
                continue

            if name in ("h4", "h5", "h6"):
                self.body_blocks.append(
                    self._make_p(
                        self._inline_to_runs(child, bold=True, color="334155", sz=20),
                        before=110,
                        after=45,
                        line=290,
                        keep_next=True,
                        page_break_before=pending_break,
                    )
                )
                pending_break = False
                continue

            if name == "hr":
                self.body_blocks.append(
                    self._make_p(
                        "",
                        before=60,
                        after=100,
                        line=120,
                        bottom_border_color="CBD5E1",
                        page_break_before=pending_break,
                    )
                )
                pending_break = False
                continue

            if name == "p":
                txt_strip = child.get_text(strip=True)
                if txt_strip in self.chart_png_map:
                    self.body_blocks.append(
                        self._make_drawing_p(txt_strip, self.chart_png_map[txt_strip], page_break_before=pending_break)
                    )
                    pending_break = False
                else:
                    runs = self._inline_to_runs(child, color="1F2937", sz=20)
                    if runs:
                        self.body_blocks.append(
                            self._make_p(runs, before=40, after=100, line=330, page_break_before=pending_break)
                        )
                        pending_break = False
                continue

            if name in ("ul", "ol"):
                list_blocks = self._render_list(
                    child,
                    ordered=(name == "ol"),
                    base_sz=20,
                    text_color="1F2937",
                    page_break_first=pending_break,
                )
                if list_blocks:
                    self.body_blocks.extend(list_blocks)
                    pending_break = False
                continue

            if name == "table":
                self.body_blocks.append(self._render_html_table(child, page_break_before=pending_break))
                pending_break = False
                continue

            if name == "pre":
                code_lines = child.get_text().splitlines() or [""]
                code_ps = [
                    self._make_p(self._make_run(ln if ln else " ", code=True, color="1E293B", sz=17), before=10, after=10, line=240)
                    for ln in code_lines
                ]
                self.body_blocks.append(
                    self._make_card_table(
                        code_ps,
                        left_color="94A3B8",
                        fill_color="F8FAFC",
                        outer_border="E2E8F0",
                        cant_split=(len(code_ps) <= 18),
                        page_break_before=pending_break,
                    )
                )
                pending_break = False
                continue

            # Generic wrapper div
            if name == "div":
                pending_break = self._walk(child, pending_break=pending_break)
        return pending_break

    def build_zip_bytes(self, body_html: str) -> dict[str, bytes]:
        soup = BeautifulSoup(body_html, "html.parser")
        root = soup.body if soup.body else soup
        self._walk(root)

        missing = [m for m in self.chart_png_map if m not in self._used_charts]
        if missing:
            raise RuntimeError(f"DOCX chart markers were NOT embedded in document body: {missing}")

        # Footer, Settings & Styles relationships
        ftr_rid = "rIdFooter1"
        self.rels.insert(
            0,
            (
                ftr_rid,
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer",
                "footer1.xml",
                False,
            ),
        )
        self.rels.insert(
            0,
            (
                "rIdSettings",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings",
                "settings.xml",
                False,
            ),
        )
        self.rels.insert(
            0,
            (
                "rIdStyles",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
                "styles.xml",
                False,
            ),
        )

        # 1. [Content_Types].xml — ALL <Default> strictly BEFORE ALL <Override> (ECMA-376)
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
            '</Types>'
        )

        # 2. _rels/.rels
        pkg_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>'
        )

        # 3. word/_rels/document.xml.rels
        rel_items = []
        for rid, rtype, target, external in self.rels:
            mode = ' TargetMode="External"' if external else ""
            rel_items.append(f'<Relationship Id="{rid}" Type="{rtype}" Target="{_xe(target)}"{mode}/>')
        doc_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(rel_items)}'
            '</Relationships>'
        )

        # 4. word/styles.xml (clean 10pt Normal, eastAsia hint, zero <w:sz-cs>!)
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:docDefaults>'
            '<w:rPrDefault><w:rPr>'
            '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="PingFang SC" w:cs="Calibri" w:hint="eastAsia"/>'
            '<w:color w:val="1F2937"/><w:sz w:val="20"/><w:szCs w:val="20"/>'
            '</w:rPr></w:rPrDefault>'
            '<w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="100" w:line="330" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
            '</w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
            '<w:name w:val="Normal"/>'
            '</w:style>'
            '</w:styles>'
        )

        # 4b. word/settings.xml (auto-recompute PAGE / NUMPAGES fields on open in Word & WPS)
        settings_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:updateFields w:val="true"/>'
            '</w:settings>'
        )

        # 5. word/footer1.xml — strict CT_PPr order (<w:pBdr> BEFORE <w:jc>) + w:dirty="true" fields
        ftr_rpr = _make_rpr(color="64748B", sz_halfpt=16)
        footer_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:p><w:pPr>'
            '<w:pBdr><w:top w:val="single" w:sz="4" w:space="4" w:color="CBD5E1"/></w:pBdr>'
            '<w:jc w:val="center"/>'
            '</w:pPr>'
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
            '</w:p></w:ftr>'
        )

        # 6. word/document.xml — ALL namespaces declared cleanly on <w:document>, <w:sectPr> ALWAYS last!
        sect_pr = (
            '<w:sectPr>'
            f'<w:footerReference w:type="default" r:id="{ftr_rid}"/>'
            f'<w:pgSz w:w="{PAGE_W_DXA}" w:h="{PAGE_H_DXA}"/>'
            f'<w:pgMar w:top="{MARGIN_TB_DXA}" w:right="{MARGIN_LR_DXA}" '
            f'w:bottom="{MARGIN_TB_DXA}" w:left="{MARGIN_LR_DXA}" w:header="540" w:footer="540" w:gutter="0"/>'
            '</w:sectPr>'
        )
        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document '
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            '<w:body>'
            f'{"".join(self.body_blocks)}'
            f'{sect_pr}'
            '</w:body></w:document>'
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
        # Strict XML well-formedness validation before creating ZIP
        for part_name, xml_str in xml_parts.items():
            try:
                ET.fromstring(xml_str.encode("utf-8"))
            except ET.ParseError as exc:
                raise RuntimeError(f"Generated invalid OOXML in {part_name}: {exc}") from exc

        out: dict[str, bytes] = {k: v.encode("utf-8") for k, v in xml_parts.items()}
        out.update(self.media)
        return out


def build_native_docx(
    full_html: str,
    docx_path: Path,
    chart_specs: list[tuple[str, Path]],
    footer_title: str = "黄金深度研报",
) -> None:
    """Build a 100% native, ECMA-376 compliant .docx with real tables, cards, and Retina PNG charts."""
    chart_map = {marker: png_path for marker, png_path in chart_specs}
    writer = _NativeDocxWriter(chart_map, footer_title=footer_title)
    parts = writer.build_zip_bytes(full_html)
    tmp_zip = docx_path.with_suffix(".docx.tmp")
    tmp_zip.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name, data in parts.items():
                zout.writestr(name, data)
        os.replace(tmp_zip, docx_path)
    except Exception:
        tmp_zip.unlink(missing_ok=True)
        raise
