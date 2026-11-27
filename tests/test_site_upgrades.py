"""Unit tests for M2 portal upgrades: K-line terminal, global multi-index priority,
3-slot (0730/1130/1800) site builder support, Wallet Calculator Gold-lock,
27-pair A/H after-tax matrix, QDII channel comparison, and Gate S7 linter.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_site  # noqa: E402
import lint_site  # noqa: E402


class TestThreeSlotSiteSupport(unittest.TestCase):
    def test_session_label_and_due_edition_support_midday_1130(self):
        self.assertEqual(build_site.session_label_from_hhmm("0730"), ("morning", "早报 07:30"))
        self.assertEqual(build_site.session_label_from_hhmm("1130"), ("midday", "午报 11:30"))
        self.assertEqual(build_site.session_label_from_hhmm("1800"), ("evening", "晚报 18:00"))
        self.assertIn("早报核销", build_site._fmt_due_edition("2026-11-27_0730"))
        self.assertIn("午报核销", build_site._fmt_due_edition("2026-11-27_1130"))
        self.assertIn("晚报核销", build_site._fmt_due_edition("2026-11-27_1800"))
        self.assertIn("ed-midday", build_site._edition_pill_html("midday"))
        self.assertIn("午刊", build_site._edition_pill_html("midday"))

    def test_discover_dailies_accepts_1130_and_excludes_retired_1630(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eq_arch = root / "equity" / "daily" / "archive" / "2026-11"
            eq_arch.mkdir(parents=True)
            (eq_arch / "2026-11-27_0730_a_share.md").write_text("# m", encoding="utf-8")
            (eq_arch / "2026-11-27_1130_a_share.md").write_text("# mid", encoding="utf-8")
            (eq_arch / "2026-11-27_1630_us_stock.md").write_text("# retired", encoding="utf-8")
            (eq_arch / "2026-11-27_1800_a_share.md").write_text("# eve", encoding="utf-8")
            gd_arch = root / "gold" / "daily" / "archive" / "2026-11"
            gd_arch.mkdir(parents=True)
            (gd_arch / "2026-11-27_1130_午报.md").write_text("# gmid", encoding="utf-8")
            with patch.multiple(build_site, GOLD_DIR=root / "gold", EQUITY_DIR=root / "equity"):
                items, _ = build_site.discover_dailies()
            slugs = [it.slug for it in items]
            self.assertIn("a-share-2026-11-27-1130", slugs)
            self.assertIn("gold-2026-11-27-1130", slugs)
            self.assertNotIn("us-stock-2026-11-27-1630", slugs)
            mid_item = next(it for it in items if it.slug == "a-share-2026-11-27-1130")
            self.assertEqual(mid_item.session_key, "midday")
            self.assertEqual(mid_item.session_label, "午报 11:30")

    def test_archive_page_preserves_midday_session_filter(self):
        sample_items = [
            build_site.DailyItem(
                market="a-share",
                date_str="2026-11-27",
                hhmm="0730",
                rev=1,
                session_key="morning",
                session_label="早报 07:30",
                slug="a-share-2026-11-27-0730",
                source_path=Path("a1.md"),
                title="A股早报",
                edition_type="main",
            ),
            build_site.DailyItem(
                market="a-share",
                date_str="2026-11-27",
                hhmm="1130",
                rev=1,
                session_key="midday",
                session_label="午报 11:30",
                slug="a-share-2026-11-27-1130",
                source_path=Path("a2.md"),
                title="A股午报",
                edition_type="midday",
            ),
            build_site.DailyItem(
                market="a-share",
                date_str="2026-11-27",
                hhmm="1800",
                rev=1,
                session_key="evening",
                session_label="晚报 18:00",
                slug="a-share-2026-11-27-1800",
                source_path=Path("a3.md"),
                title="A股晚报",
                edition_type="main",
            ),
        ]
        html = build_site.build_archive_page(sample_items, [], {"a-share": 76}, 231, 28)
        self.assertIn('data-arc-session="midday"', html)
        self.assertIn("午报 (11:30)", html)
        self.assertIn('data-session="midday"', html)
        self.assertIn('data-session="morning"', html)
        self.assertIn('data-session="evening"', html)

        app_js = (ROOT / "scripts" / "web_assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn('arcState.session === "all" || s === arcState.session', app_js)
        self.assertNotIn('s === "midday" ? "evening"', app_js)


class TestMultiIndexPriorityAndCharts(unittest.TestCase):
    def test_a_share_priority_leads_with_sse_composite(self):
        fake_manifest = {
            "catalog": [
                {"id": "idx_sh000001", "latest_close": 3890.12, "change_pct": 0.45, "latest_date": "2026-11-26"},
                {"id": "idx_sh000300", "latest_close": 4560.88, "change_pct": -0.18, "latest_date": "2026-11-26"},
                {"id": "idx_sz399001", "latest_close": 12450.00, "change_pct": 0.31, "latest_date": "2026-11-26"},
                {"id": "idx_sh000510", "latest_close": 4910.20, "change_pct": 0.12, "latest_date": "2026-11-26"},
                {"id": "idx_sz399006", "latest_close": 2380.50, "change_pct": 1.05, "latest_date": "2026-11-26"},
                {"id": "idx_sh000688", "latest_close": 1020.40, "change_pct": 0.88, "latest_date": "2026-11-26"},
                {"id": "idx_hkHSI", "latest_close": 25410.00, "change_pct": -0.52, "latest_date": "2026-11-26"},
                {"id": "idx_SPX", "latest_close": 6592.30, "change_pct": 0.64, "latest_date": "2026-11-26"},
                {"id": "cmd_XAU", "latest_close": 4555.00, "change_pct": -0.30, "latest_date": "2026-11-26"},
            ]
        }
        eq_state = {
            "markets": {
                "a_share": {
                    # Structured index_matrix overrides manifest value cleanly
                    "index_matrix": [
                        {"id": "idx_sh000001", "value": 3912.34, "change_pct": 0.77},
                    ],
                    "benchmark_sse": 3800.00,
                    "benchmark_csi300": 4500.00,
                }
            }
        }
        groups = build_site._resolve_multi_index_groups({}, eq_state, fake_manifest)
        a_ids = [r["id"] for r in groups["a_share"]]
        self.assertEqual(a_ids[:6], [
            "idx_sh000001",
            "idx_sh000300",
            "idx_sz399001",
            "idx_sh000510",
            "idx_sz399006",
            "idx_sh000688",
        ])
        self.assertEqual(len(a_ids), 12)
        self.assertEqual(groups["a_share"][0]["value_disp"], "3,912.34")
        self.assertEqual(groups["a_share"][1]["value_disp"], "4,560.88")
        self.assertEqual([r["id"] for r in groups["hk_stock"][:3]], ["idx_hkHSI", "idx_hkHSTECH", "idx_hkHSCEI"])
        self.assertEqual(len(groups["us_stock"]), 8)
        self.assertEqual(groups["us_stock"][0]["id"], "idx_SPX")
        self.assertEqual(groups["us_stock"][-1]["id"], "idx_VIX")

    def test_cockpit_and_charts_handle_missing_manifest_gracefully(self):
        gold = {"new_buy_allowed": False, "tier_code": "Tier 0", "as_of_short": "2026-11-27 07:30"}
        eq = {"as_of_cst": "2026-11-27T07:30:00+08:00", "markets": {"a_share": {"benchmark_sse": 3910.0, "benchmark_csi300": 4570.0}}}
        cockpit = build_site.build_cockpit_page(gold, eq, {}, {"a-share": 76}, kline_manifest=None, kline_core=None)
        self.assertIn("crisis-ribbon", cockpit)
        self.assertIn("vix-spark-svg", cockpit)
        self.assertIn("sec-kline-deck", cockpit)
        self.assertIn("wcalc-card", cockpit)
        # SSE must appear before CSI 300 inside the A-share card matrix
        m_pos = cockpit.find("上证指数（000001.SH · 大盘总舵）")
        self.assertGreater(m_pos, 0)
        sub = cockpit[m_pos:m_pos + 3500]
        self.assertLess(sub.find("上证指数"), sub.find("沪深300"))
        self.assertLess(sub.find("沪深300"), sub.find("深证成指"))
        self.assertLess(sub.find("深证成指"), sub.find("中证A500"))

        multi_idx = build_site._resolve_multi_index_groups(gold, eq, None)
        charts_body = build_site.build_charts_page(gold, eq, multi_idx, [], None, None)
        self.assertIn("kline-terminal-mount", charts_body)
        self.assertIn("kline-meta-bridge", charts_body)
        self.assertIn("红灯观察期", charts_body)
        self.assertGreater(len(charts_body), 3000)


class TestWalletCalculatorAhMatrixAndQdii(unittest.TestCase):
    def test_wallet_calculator_gold_lock_and_unlock(self):
        locked_html = build_site._render_wallet_calculator(
            {"new_buy_allowed": False, "tier_code": "Tier 0"},
            {"markets": {"a_share": {"equity_cap_pct": 35}}},
        )
        m1 = re.search(r'<script id="wallet-calc-data" type="application/json">(.*?)</script>', locked_html, re.S)
        self.assertIsNotNone(m1)
        cfg1 = json.loads(m1.group(1))
        self.assertFalse(cfg1["gold_new_buy_allowed"])
        self.assertEqual(cfg1["eq_cap_pct"], 35)
        self.assertIn("新仓严格 0 元", locked_html)

        unlocked_html = build_site._render_wallet_calculator(
            {"new_buy_allowed": True, "tier_code": "Tier 1"},
            {"markets": {"a_share": {"equity_cap_pct": 55}}},
        )
        m2 = re.search(r'<script id="wallet-calc-data" type="application/json">(.*?)</script>', unlocked_html, re.S)
        self.assertIsNotNone(m2)
        cfg2 = json.loads(m2.group(1))
        self.assertTrue(cfg2["gold_new_buy_allowed"])
        self.assertEqual(cfg2["eq_cap_pct"], 55)
        self.assertIn("黄金允许按档分批", unlocked_html)

    def test_ah_after_tax_dividend_matrix_distinguishes_20_vs_28_red_chip(self):
        benchmarks = [
            {"name": "中国海油", "a": "600938", "h": "00883.HK", "ah_premium_pct": 69.2, "preferred_channel": "offshore_hk_check_withholding"},
            {"name": "中国石油", "a": "601857", "h": "00857.HK", "ah_premium_pct": 51.0, "preferred_channel": "offshore_hk"},
            {"name": "宁德时代", "a": "300750", "h": "03750.HK", "ah_premium_pct": -19.7, "preferred_channel": "onshore_a_inverted"},
        ]
        stocks = [
            {"market": "a-share", "code": "600938", "price": "26.00元", "div_pct": 5.0, "color": "g"},
            {"market": "hk-stock", "code": "00883.HK", "price": "17.00港元", "div_pct": 8.0, "color": "g"},
            {"market": "a-share", "code": "601857", "price": "9.00元", "div_pct": 5.0, "color": "g"},
            {"market": "hk-stock", "code": "00857.HK", "price": "6.50港元", "div_pct": 7.5, "color": "g"},
            {"market": "a-share", "code": "300750", "price": "260.00元", "div_pct": 2.0, "color": "b"},
            {"market": "hk-stock", "code": "03750.HK", "price": "350.00港元", "div_pct": 1.6, "color": "b"},
        ]
        rows = build_site._build_ah_matrix_payload(benchmarks, stocks)
        by_h = {r["h_code"]: r for r in rows}
        # CNOOC is red-chip -> 28% tax: 8.0 * 0.72 = 5.76%
        self.assertEqual(by_h["00883.HK"]["h_tax_rate_pct"], 28)
        self.assertAlmostEqual(by_h["00883.HK"]["h_connect_after_tax_div"], 5.76, places=2)
        self.assertAlmostEqual(by_h["00883.HK"]["net_div_spread"], 0.76, places=2)
        # PetroChina is H-share -> 20% tax: 7.5 * 0.80 = 6.00%
        self.assertEqual(by_h["00857.HK"]["h_tax_rate_pct"], 20)
        self.assertAlmostEqual(by_h["00857.HK"]["h_connect_after_tax_div"], 6.00, places=2)
        # CATL inverted -> A-share cheaper verdict
        self.assertEqual(by_h["03750.HK"]["verdict_label"], "A 股倒挂占优")

    def test_qdii_comparison_section_supports_default_and_custom_payload(self):
        default_html = build_site._render_qdii_comparison_section(None, compact=False)
        self.assertIn("sec-qdii-compare", default_html)
        self.assertIn("data-qdii-calc", default_html)
        self.assertIn("纳斯达克 100", default_html)

        custom = {
            "channels": [
                {
                    "id": "qdii_mrf",
                    "qdii_channel_comparison": [
                        {
                            "track": "测试纳指100",
                            "fund_company": "示例基金",
                            "on_exchange_code": "513100",
                            "on_exchange_fee": "0.60%",
                            "on_exchange_premium_pct": 4.25,
                            "otc_codes": "270042(A)",
                            "direct_app_limit_rmb": 1000,
                            "alipay_limit_rmb": 100,
                            "direct_vs_alipay_ratio": "10x",
                            "risk_note": "优先官方直销按净值申购",
                        }
                    ],
                }
            ]
        }
        custom_html = build_site._render_qdii_comparison_section(custom, compact=False)
        self.assertIn("测试纳指100", custom_html)
        self.assertIn("+4.25%", custom_html)
        self.assertIn("¥1,000/日", custom_html)
        self.assertIn("¥100/日", custom_html)


class TestGateS7AndBundling(unittest.TestCase):
    def _make_minimal_s7_site(self, root: Path, *, dict_shards: bool = True) -> dict[str, lint_site.ParsedHtml]:
        (root / "assets" / "klines").mkdir(parents=True, exist_ok=True)
        index_html = (
            '<html><body><nav><a href="charts.html">K线图表</a></nav>'
            '<h1>驾驶舱</h1><div>上证指数 沪深300 深证成指 创业板指 科创50 恒生指数 标普500</div></body></html>'
        )
        charts_html = (
            '<html><body><nav><a href="charts.html">K线图表</a></nav>'
            '<h1>全市场 K 线终端</h1><div id="kline-terminal-mount"></div>'
            + ("<!-- pad -->" * 300)
            + "</body></html>"
        )
        (root / "index.html").write_text(index_html, encoding="utf-8")
        (root / "charts.html").write_text(charts_html, encoding="utf-8")

        shard_obj = {
            "shard": "core",
            "series": {
                "idx_sh000001": {
                    "id": "idx_sh000001",
                    "bars": [["2026-11-26", 3880.0, 3910.0, 3870.0, 3900.0, 123456.0]],
                }
            },
        }
        (root / "assets" / "klines" / "core.json").write_text(json.dumps(shard_obj), encoding="utf-8")
        manifest = {
            "schema_version": "1.0",
            "shards": {"core": {"file": "core.json", "count": 1, "bytes": 120}} if dict_shards else {"core": "core.json"},
            "catalog": [
                {"id": "idx_sh000001", "code": "000001", "name": "上证指数", "group": "a_index", "shard": "core"},
                {"id": "idx_sh000300", "code": "000300", "name": "沪深300", "group": "a_index", "shard": "core"},
            ],
        }
        (root / "assets" / "klines" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return {
            "index.html": lint_site.parse_html_file("index.html", root / "index.html", index_html),
            "charts.html": lint_site.parse_html_file("charts.html", root / "charts.html", charts_html),
        }

    def test_gate_s7_passes_with_both_dict_and_string_shards(self):
        for dict_shards in (True, False):
            with self.subTest(dict_shards=dict_shards), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                docs = self._make_minimal_s7_site(root, dict_shards=dict_shards)
                errors, warnings = [], []
                lint_site.run_gate_s7(root, docs, errors, warnings)
                self.assertEqual(errors, [])
                self.assertEqual(warnings, [])

    def test_gate_s7_catches_bad_priority_missing_shard_bad_ohlc_and_leaks(self):
        # 1. Wrong A-share priority (CSI 300 before SSE)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = self._make_minimal_s7_site(root)
            mf_path = root / "assets" / "klines" / "manifest.json"
            mf = json.loads(mf_path.read_text(encoding="utf-8"))
            mf["catalog"].reverse()
            mf_path.write_text(json.dumps(mf, ensure_ascii=False), encoding="utf-8")
            errors, warnings = [], []
            lint_site.run_gate_s7(root, docs, errors, warnings)
            self.assertTrue(any("idx_sh000001" in e for e in errors), errors)

        # 2. Missing shard file
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = self._make_minimal_s7_site(root)
            (root / "assets" / "klines" / "core.json").unlink()
            errors, warnings = [], []
            lint_site.run_gate_s7(root, docs, errors, warnings)
            self.assertTrue(any("Missing K-line shard file" in e for e in errors), errors)

        # 3. Corrupted OHLC bar (high < low)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = self._make_minimal_s7_site(root)
            bad_shard = {
                "shard": "core",
                "series": {
                    "idx_sh000001": {
                        "id": "idx_sh000001",
                        "bars": [["2026-11-26", 3880.0, 3800.0, 3900.0, 3850.0, 100.0]],
                    }
                },
            }
            (root / "assets" / "klines" / "core.json").write_text(json.dumps(bad_shard), encoding="utf-8")
            errors, warnings = [], []
            lint_site.run_gate_s7(root, docs, errors, warnings)
            self.assertTrue(any("invalid ohlc" in e.lower() for e in errors), errors)

        # 4. Forbidden raw leak (/Users/) inside K-line JSON
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = self._make_minimal_s7_site(root)
            mf_path = root / "assets" / "klines" / "manifest.json"
            mf = json.loads(mf_path.read_text(encoding="utf-8"))
            mf["debug_path"] = "/Users/leak/test"
            mf_path.write_text(json.dumps(mf, ensure_ascii=False), encoding="utf-8")
            errors, warnings = [], []
            lint_site.run_gate_s7(root, docs, errors, warnings)
            self.assertTrue(any("forbidden" in e.lower() for e in errors), errors)

    def test_gate_s3_blocks_fetch_kline_data_py_leak(self):
        self.assertIsNotNone(lint_site.S3_INTERNAL_ENG_LEAK_RE.search("请运行 fetch_kline_data.py 刷新"))
        self.assertIsNotNone(build_site._HARD_INFRA_RE.search("脚本 fetch_kline_data.py"))

    def test_live_build_bundles_klines_and_passes_all_7_strict_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "site"
            summary = build_site.build_site(out_dir)
            self.assertTrue((out_dir / "charts.html").is_file())
            self.assertTrue((out_dir / "assets" / "kline.js").is_file())
            if (ROOT / "equity" / "state" / "klines" / "manifest.json").is_file():
                self.assertTrue((out_dir / "assets" / "klines" / "manifest.json").is_file())
                self.assertTrue((out_dir / "assets" / "klines" / "core.json").is_file())
            self.assertGreaterEqual(summary["html_files"], 10)
            rc = lint_site.main([str(out_dir), "--strict"])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
