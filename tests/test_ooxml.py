"""Headless-free ECMA-376 OOXML regression tests for gold & equity native DOCX builders."""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]

# Minimal valid 1x1 transparent PNG (67 bytes; zero Chrome dependency)
TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

REQUIRED_OOXML_PARTS = (
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/_rels/document.xml.rels",
    "word/styles.xml",
    "word/settings.xml",
    "word/footer1.xml",
)

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP_NS = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
PIC_NS = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gold_docx = _load_module("gold_docx_embed_testmod", ROOT / "gold" / "docx_embed.py")
equity_docx = _load_module("equity_docx_embed_testmod", ROOT / "equity" / "docx_embed.py")


class NativeOoxmlDocxTests(unittest.TestCase):
    def _assert_valid_ooxml_docx(self, docx_path: Path, *, expected_link_url: str) -> ET.Element:
        self.assertTrue(docx_path.is_file(), f"Missing generated DOCX: {docx_path}")
        with zipfile.ZipFile(docx_path, "r") as zf:
            names = set(zf.namelist())
            for part in REQUIRED_OOXML_PARTS:
                self.assertIn(part, names, f"Missing required OOXML part: {part}")

            xml_roots: dict[str, ET.Element] = {}
            for name in names:
                if name.endswith((".xml", ".rels")):
                    xml_roots[name] = ET.fromstring(zf.read(name))

            # 1. [Content_Types].xml: all <Default> strictly before all <Override>, and no dangling Override
            ct_root = xml_roots["[Content_Types].xml"]
            seen_override = False
            for child in ct_root:
                tag_local = child.tag.split("}")[-1]
                if tag_local == "Override":
                    seen_override = True
                    part_name = child.attrib.get("PartName", "").lstrip("/")
                    self.assertIn(part_name, names, f"Dangling Override PartName: {part_name}")
                elif tag_local == "Default":
                    self.assertFalse(seen_override, "<Default> appeared after <Override> in [Content_Types].xml")

            # 2. Zero invalid Word 2003 <w:sz-cs> and zero unconsumed ___DOCX_CHART_ placeholders
            doc_text = zf.read("word/document.xml").decode("utf-8")
            styles_text = zf.read("word/styles.xml").decode("utf-8")
            self.assertNotIn("<w:sz-cs", doc_text)
            self.assertNotIn("<w:sz-cs", styles_text)
            self.assertNotIn("___DOCX_CHART_", doc_text)

            # 3. <w:sectPr> is strictly the LAST child of <w:body>
            doc_root = xml_roots["word/document.xml"]
            body = doc_root.find(f"{W_NS}body")
            self.assertIsNotNone(body)
            body_children = list(body)
            self.assertGreater(len(body_children), 0)
            self.assertEqual(body_children[-1].tag, f"{W_NS}sectPr")

            # 4. Real <w:tbl> >= 2, positive <w:tblGrid> summing <= 9638, tblBorders before tblLayout
            tbls = doc_root.findall(f".//{W_NS}tbl")
            self.assertGreaterEqual(len(tbls), 2)
            for idx, tbl in enumerate(tbls):
                tbl_pr = tbl.find(f"{W_NS}tblPr")
                if tbl_pr is not None:
                    tags = [c.tag.split("}")[-1] for c in tbl_pr]
                    if "tblBorders" in tags and "tblLayout" in tags:
                        self.assertLess(
                            tags.index("tblBorders"),
                            tags.index("tblLayout"),
                            f"Table {idx + 1} has tblBorders after tblLayout",
                        )
                grid = tbl.find(f"{W_NS}tblGrid")
                self.assertIsNotNone(grid, f"Table {idx + 1} missing <w:tblGrid>")
                col_ws = [int(gc.attrib.get(f"{W_NS}w", "0")) for gc in grid.findall(f"{W_NS}gridCol")]
                self.assertTrue(col_ws, f"Table {idx + 1} has empty <w:tblGrid>")
                self.assertTrue(all(w > 0 for w in col_ws), f"Table {idx + 1} has non-positive width: {col_ws}")
                self.assertLessEqual(sum(col_ws), 9638, f"Table {idx + 1} width exceeds 9638 dxa: {col_ws}")

            # 5. Footer ECMA-376 ordering: <w:pBdr> strictly before <w:jc>
            ftr_root = xml_roots["word/footer1.xml"]
            for ppr in ftr_root.findall(f".//{W_NS}pPr"):
                ftags = [c.tag.split("}")[-1] for c in ppr]
                if "pBdr" in ftags and "jc" in ftags:
                    self.assertLess(ftags.index("pBdr"), ftags.index("jc"))

            # 6. Unique wp:docPr/@id and pic:cNvPr/@id
            docpr_ids = [el.attrib.get("id") for el in doc_root.findall(f".//{WP_NS}docPr")]
            cnvpr_ids = [el.attrib.get("id") for el in doc_root.findall(f".//{PIC_NS}cNvPr")]
            self.assertGreaterEqual(len(docpr_ids), 1)
            self.assertGreaterEqual(len(cnvpr_ids), 1)
            self.assertEqual(len(docpr_ids), len(set(docpr_ids)))
            self.assertEqual(len(cnvpr_ids), len(set(cnvpr_ids)))

            # 7. Relationships resolve: external hyperlink, footer, and embedded PNG in word/media/
            rels_root = xml_roots["word/_rels/document.xml.rels"]
            rel_map = {el.attrib.get("Id"): el.attrib for el in rels_root}

            hyperlinks = doc_root.findall(f".//{W_NS}hyperlink")
            self.assertGreaterEqual(len(hyperlinks), 1)
            link_targets = []
            for hl in hyperlinks:
                rid = hl.attrib.get(f"{R_NS}id")
                self.assertIn(rid, rel_map)
                self.assertEqual(rel_map[rid].get("TargetMode"), "External")
                link_targets.append(rel_map[rid].get("Target"))
            self.assertIn(expected_link_url, link_targets)

            footer_refs = doc_root.findall(f".//{W_NS}footerReference")
            self.assertGreaterEqual(len(footer_refs), 1)
            for fr in footer_refs:
                self.assertIn(fr.attrib.get(f"{R_NS}id"), rel_map)

            blips = doc_root.findall(f".//{A_NS}blip")
            self.assertGreaterEqual(len(blips), 1)
            media_pngs = [n for n in names if n.startswith("word/media/") and n.endswith(".png")]
            self.assertGreaterEqual(len(media_pngs), 1)
            for blip in blips:
                rid = blip.attrib.get(f"{R_NS}embed")
                self.assertIn(rid, rel_map)
                media_path = f"word/{rel_map[rid]['Target']}"
                self.assertIn(media_path, names)
                self.assertTrue(zf.read(media_path).startswith(b"\x89PNG\r\n\x1a\n"))

            return doc_root

    def test_gold_build_native_docx_strict_ooxml(self):
        html = """<!DOCTYPE html>
        <html lang="zh-CN"><body>
          <div class="cover-banner" style="border-bottom: 4px solid #b45309;">
            <div class="cover-tag">每日黄金深度研报</div>
            <div class="cover-title">2026年11月26日 黄金晚报</div>
            <div class="cover-meta">截至 2026-11-26 18:00 北京时间</div>
            <div class="kpi-strip cols-4">
              <div class="kpi-card"><div class="kpi-label">现货金</div><div class="kpi-val">$3,589</div><div class="kpi-sub">纽约官收</div></div>
              <div class="kpi-card"><div class="kpi-label">紧迫度</div><div class="kpi-val">L1 临近</div><div class="kpi-sub">防薄量</div></div>
              <div class="kpi-card"><div class="kpi-label">买金红绿灯</div><div class="kpi-val">红灯 1/4</div><div class="kpi-sub">新仓 0%</div></div>
              <div class="kpi-card"><div class="kpi-label">婚庆差价</div><div class="kpi-val">省 272 元</div><div class="kpi-sub">克价对比</div></div>
            </div>
          </div>
          <div class="verdict-card" style="border-left: 4px solid #d97706; background: #fffbeb;">
            <div class="verdict-top"><span class="verdict-badge">L1 关键节点</span><span class="verdict-light">红灯停（1/4 关）</span></div>
            <div class="verdict-headline" style="color: #0f172a;">维持红灯等待四关齐备</div>
            <ul><li><strong>事实</strong>：现货收 3,589 美元。</li></ul>
            <div class="verdict-risk">严守家庭资产上限。</div>
          </div>
          <div class="sn-grid">
            <div class="sn-col-sig">
              <div class="sn-col-head">真信号</div>
              <div class="sn-col-body"><ul><li><strong>利率</strong>：10Y 真实利率 2.73%。</li></ul></div>
            </div>
            <div class="sn-col-noi">
              <div class="sn-col-head">可划走噪音</div>
              <div class="sn-col-body"><ul><li><strong>传闻</strong>：无证据抛售谣言。</li></ul></div>
            </div>
          </div>
          <div class="glossary-box">
            <div class="glossary-title">关键术语速查</div>
            <table class="glossary-table">
              <tbody>
                <tr><td><span class="gloss-pill">VIX</span></td><td>衡量美股波动预期的恐慌指标。</td></tr>
              </tbody>
            </table>
          </div>
          <table class="data-table">
            <thead><tr><th class="col-nowrap">指标</th><th class="ta-c">读数</th><th>说明</th></tr></thead>
            <tbody>
              <tr><td class="col-nowrap">伦敦现货金</td><td class="ta-c">$3,589</td><td>来源见 <a href="https://example.com/gold">官方收盘</a></td></tr>
            </tbody>
          </table>
          <p>___DOCX_CHART_1___</p>
        </body></html>
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            png_path = root / "chart_1.png"
            png_path.write_bytes(TINY_PNG_BYTES)
            out_docx = root / "gold_test.docx"

            gold_docx.build_native_docx(
                html,
                out_docx,
                [("___DOCX_CHART_1___", png_path)],
                footer_title="黄金深度研报测试",
            )
            doc_root = self._assert_valid_ooxml_docx(out_docx, expected_link_url="https://example.com/gold")

            # Verify 4-column KPI strip (.kpi-strip.cols-4), 2-column .sn-grid, and .glossary-title rendered
            grid_col_counts = [
                len(grid.findall(f"{W_NS}gridCol"))
                for grid in doc_root.findall(f".//{W_NS}tblGrid")
            ]
            self.assertIn(4, grid_col_counts, f"Expected 4-column .kpi-strip.cols-4 table, got {grid_col_counts}")
            self.assertIn(2, grid_col_counts, f"Expected 2-column .sn-grid table, got {grid_col_counts}")
            full_text = "".join(doc_root.itertext())
            self.assertIn("关键术语速查", full_text)
            self.assertIn("真信号", full_text)
            self.assertIn("可划走噪音", full_text)

    def test_equity_docx_writer_with_placeholder_and_entrypoint_strict_ooxml(self):
        placeholder_html = """<!DOCTYPE html>
        <html lang="zh-CN"><body>
          <div class="cover-banner">
            <div class="cover-tag">港股每日深度研报</div>
            <div class="cover-title">2026年11月26日 港股晚报</div>
            <div class="cover-meta">截至 2026-11-26 18:00 北京时间</div>
            <div class="kpi-strip">
              <div class="kpi-card"><div class="kpi-label">恒生指数</div><div class="kpi-val">22,300</div><div class="kpi-sub">红灯防守</div></div>
              <div class="kpi-card"><div class="kpi-label">总结余</div><div class="kpi-val">541 亿</div><div class="kpi-sub">联汇薄缓冲</div></div>
            </div>
          </div>
          <div class="callout callout-verdict">
            <div class="callout-title">一句话总判断</div>
            <div class="callout-line">守红利底座，参考 <a href="https://example.com/equity">官方披露</a>。</div>
          </div>
          <table>
            <thead><tr><th>指数</th><th style="text-align:right;">点位</th><th>评级</th></tr></thead>
            <tbody>
              <tr class="row-g"><td>恒生指数</td><td style="text-align:right;">22,300</td><td>当下底座</td></tr>
            </tbody>
          </table>
          <p>___DOCX_CHART_1___</p>
        </body></html>
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            png_path = root / "chart_1.png"
            png_path.write_bytes(TINY_PNG_BYTES)

            # 1. Direct _EquityDocxWriter path with ___DOCX_CHART_1___ placeholder (zero Chrome)
            soup = BeautifulSoup(placeholder_html, "html.parser")
            writer = equity_docx._EquityDocxWriter(
                {"___DOCX_CHART_1___": png_path},
                market="hk_stock",
                footer_title="港股深度研报测试",
            )
            parts = writer.build_zip_bytes(soup.body)
            out_direct = root / "equity_direct.docx"
            with zipfile.ZipFile(out_direct, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for name, data in parts.items():
                    zout.writestr(name, data)
            self._assert_valid_ooxml_docx(out_direct, expected_link_url="https://example.com/equity")

            # 2. Full build_native_docx_from_html entrypoint with mocked chart rasterizer (zero Chrome)
            chart_box_html = placeholder_html.replace(
                "<p>___DOCX_CHART_1___</p>",
                '<div class="chart-box"><svg viewBox="0 0 850 280"></svg></div>',
            )
            out_entry = root / "equity_entry.docx"

            def fake_rasterize(_chart_html, out_png, _tmp_dir, _idx):
                out_png.write_bytes(TINY_PNG_BYTES)
                return out_png

            with patch.object(equity_docx, "render_chart_to_png", side_effect=fake_rasterize):
                equity_docx.build_native_docx_from_html(
                    chart_box_html,
                    out_entry,
                    market="us_stock",
                    footer_title="美股深度研报测试",
                )
            self._assert_valid_ooxml_docx(out_entry, expected_link_url="https://example.com/equity")


if __name__ == "__main__":
    unittest.main()
