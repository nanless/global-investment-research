"""Unit tests for M2 portal upgrades: K-line terminal, global multi-index priority,
3-slot (0730/1130/1800) site builder support, Wallet Calculator Gold-lock,
27-pair A/H after-tax matrix, QDII channel comparison, and Gate S7 linter.
"""

from __future__ import annotations

from collections import Counter
import html
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


class TestSixMarketCockpitAndOrthogonalEtfUpgrades(unittest.TestCase):
    def _load_live_ssots(self) -> tuple[dict, dict, dict, dict, dict | None]:
        gold_snap = json.loads((ROOT / "gold" / "data_snapshot.json").read_text(encoding="utf-8"))
        eq_state = json.loads((ROOT / "equity" / "state" / "market_state.json").read_text(encoding="utf-8"))
        ch_data = json.loads((ROOT / "equity" / "state" / "multi_asset_channels.json").read_text(encoding="utf-8"))
        etf_data = json.loads((ROOT / "equity" / "state" / "etf_universe.json").read_text(encoding="utf-8"))
        mf_path = ROOT / "equity" / "state" / "klines" / "manifest.json"
        kline_manifest = json.loads(mf_path.read_text(encoding="utf-8")) if mf_path.is_file() else None
        return gold_snap, eq_state, ch_data, etf_data, kline_manifest

    def test_live_etf_universe_orthogonal_asset_class_and_region_ssot(self):
        etf_data = json.loads((ROOT / "equity" / "state" / "etf_universe.json").read_text(encoding="utf-8"))
        etfs = etf_data.get("etfs")
        self.assertIsInstance(etfs, list)
        self.assertGreaterEqual(len(etfs), 140)
        self.assertEqual(len(etfs), etf_data.get("total_etfs"))

        ac_counter: Counter[str] = Counter()
        rg_counter: Counter[str] = Counter()
        for item in etfs:
            code = item.get("code")
            ac = str(item.get("asset_class", "")).strip()
            rg = str(item.get("region", "")).strip()
            self.assertIn(ac, lint_site.ETF_ALLOWED_ASSET_CLASSES, f"Invalid asset_class on ETF {code}: {ac!r}")
            self.assertIn(rg, lint_site.ETF_ALLOWED_REGIONS, f"Invalid region on ETF {code}: {rg!r}")
            ac_counter[ac] += 1
            rg_counter[rg] += 1
            if etf_data.get("gold_tier0_locked") is True and ac == "gold":
                self.assertTrue(item.get("gold_locked"), f"Gold-class ETF {code} missing gold_locked=True")

        self.assertEqual(etf_data.get("counts_by_asset_class"), dict(ac_counter))
        self.assertEqual(etf_data.get("counts_by_region"), dict(rg_counter))

    def test_six_market_cockpit_hk_role_btc_guard_qdii_ctas_and_six_tab_kline(self):
        gold_snap, eq_state, ch_data, etf_data, kline_manifest = self._load_live_ssots()
        stock_counts = {
            "a-share": int(eq_state["markets"]["a_share"]["stock_pool_count"]),
            "hk-stock": int(eq_state["markets"]["hk_stock"]["stock_pool_count"]),
            "us-stock": int(eq_state["markets"]["us_stock"]["stock_pool_count"]),
        }
        cockpit = build_site.build_cockpit_page(
            gold_snap,
            eq_state,
            {},
            stock_counts,
            channels_data=ch_data,
            etf_data=etf_data,
            kline_manifest=kline_manifest,
        )
        doc = lint_site.parse_html_file("index.html", Path("index.html"), f"<!doctype html><html><body>{cockpit}</body></html>")

        # 1. All 6 cockpit cards
        for req_card in ("card-a-share", "card-hk-stock", "card-us-stock", "card-rates", "card-gold", "card-nonus"):
            self.assertIn(req_card, doc.ids, f"Missing 6-market cockpit card #{req_card}")

        # 1b. #card-nonus renders real live benchmark values (zero empty .m-sub-val, zero "境内 — · 离岸 —")
        nonus_elem = lint_site._inspect_element_by_id(cockpit, "card-nonus")
        self.assertIsNotNone(nonus_elem)
        self.assertEqual(
            nonus_elem.empty_m_sub_val_count,
            0,
            "#card-nonus must NOT render any empty <span class=\"m-sub-val\"></span> tile",
        )
        self.assertNotIn("境内 — · 离岸 —", nonus_elem.inner_text)
        self.assertGreaterEqual(len(nonus_elem.m_sub_val_texts), 4)
        self.assertTrue(
            all(bool(v) and any(ch.isdigit() for ch in v) for v in nonus_elem.m_sub_val_texts),
            f"#card-nonus .m-sub-val tiles must render live numeric benchmarks, got {nonus_elem.m_sub_val_texts!r}",
        )

        # 1c. #card-rates Tile #4 jumps to fx_USDCNH (not idx_932047)
        m_rates_art = re.search(
            r'<article\b[^>]*id="card-rates"[^>]*>.*?</article>',
            cockpit,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(m_rates_art)
        rates_tiles = [
            btn_html
            for btn_html in re.findall(r"<button\b[^>]*>.*?</button>", m_rates_art.group(0), flags=re.DOTALL)
            if (m_cls := re.match(r'<button\b[^>]*\bclass="([^"]+)"', btn_html))
            and "m-sub-tile" in m_cls.group(1).split()
        ]
        self.assertGreaterEqual(len(rates_tiles), 4)
        self.assertIn('data-kline-jump="fx_USDCNH"', rates_tiles[3])
        self.assertNotIn('data-kline-jump="idx_932047"', rates_tiles[3])

        # 1d. ETF Showcase Card #5 links to etfs.html#asset_class=fixed_income_plus
        etf_card_tags = [
            tag
            for tag in re.findall(r"<a\b[^>]*>", cockpit)
            if (m_cls := re.search(r'\bclass="([^"]+)"', tag))
            and "home-etf-card" in m_cls.group(1).split()
        ]
        self.assertGreaterEqual(len(etf_card_tags), 5)
        m_card5_href = re.search(r'\bhref="([^"]+)"', etf_card_tags[4])
        self.assertIsNotNone(m_card5_href)
        self.assertEqual(
            html.unescape(m_card5_href.group(1)),
            "etfs.html#asset_class=fixed_income_plus",
        )

        # 2. HK offshore discount-leg role
        self.assertIn("中国离岸折价腿", doc.visible_text)

        # 3. BTC read-only compliance guard
        if "BTC" in doc.visible_text or "比特币" in doc.visible_text:
            self.assertTrue(
                "境内禁交易" in doc.visible_text or "仅作流动风向" in doc.visible_text,
                "BTC/比特币 mentioned on cockpit without required onshore read-only compliance guard",
            )

        # 4. Prominent QDII jump/hero/card CTAs
        a_hrefs = {lk.value for lk in doc.links if lk.tag == "a"}
        self.assertTrue(
            "channels/qdii_mrf.html#sec-qdii-compare" in a_hrefs or "etfs.html#preset=qdii" in a_hrefs,
            f"Missing prominent QDII CTA link in cockpit (found QDII links: {[h for h in a_hrefs if 'qdii' in h]})",
        )
        self.assertIn("channels/qdii_mrf.html", a_hrefs)

        # 5. 6-tab K-line deck
        self.assertIn("日欧台韩印非美", doc.visible_text)
        self.assertIn("中美债市与REITs", doc.visible_text)
        self.assertEqual(len(re.findall(r'data-deck-tab="[^"]+"', cockpit)), 6)

        # 6. Graceful fallback when minimal fixture lacks rates_bonds_core & non_us_global_satellite
        min_gold = {"new_buy_allowed": False, "tier_code": "Tier 0", "as_of_short": "2026-11-27 07:30"}
        min_eq = {
            "as_of_cst": "2026-11-27T07:30:00+08:00",
            "markets": {"a_share": {"benchmark_sse": 3910.0, "benchmark_csi300": 4570.0}},
        }
        min_cockpit = build_site.build_cockpit_page(
            min_gold, min_eq, {}, {"a-share": 76}, kline_manifest=None, kline_core=None,
        )
        min_doc = lint_site.parse_html_file(
            "index.html", Path("index.html"), f"<!doctype html><html><body>{min_cockpit}</body></html>"
        )
        for req_card in ("card-a-share", "card-hk-stock", "card-us-stock", "card-rates", "card-gold", "card-nonus"):
            self.assertIn(req_card, min_doc.ids, f"Minimal fallback missing cockpit card #{req_card}")
        self.assertIn("中国离岸折价腿", min_doc.visible_text)
        self.assertIn("日欧台韩印非美", min_doc.visible_text)
        self.assertIn("中美债市与REITs", min_doc.visible_text)
        self.assertEqual(len(re.findall(r'data-deck-tab="[^"]+"', min_cockpit)), 6)
        self.assertNotIn("NaN", min_doc.visible_text)

    def test_layer3_channel_role_groups_preserve_all_12_cards_and_qdii_name(self):
        gold_snap, eq_state, ch_data, etf_data, kline_manifest = self._load_live_ssots()
        ch08 = next((c for c in ch_data["channels"] if c.get("id") == "qdii_mrf"), None)
        self.assertIsNotNone(ch08)
        self.assertTrue(
            str(ch08.get("name", "")).startswith("QDII"),
            f"Channel 08 (qdii_mrf) name must start with 'QDII', got {ch08.get('name')!r}",
        )

        cockpit = build_site.build_cockpit_page(
            gold_snap,
            eq_state,
            {},
            {"a-share": 76, "hk-stock": 75, "us-stock": 80},
            channels_data=ch_data,
            etf_data=etf_data,
            kline_manifest=kline_manifest,
        )
        self.assertIn("ch-role-group", cockpit)
        doc = lint_site.parse_html_file("index.html", Path("index.html"), f"<!doctype html><html><body>{cockpit}</body></html>")
        for cid in lint_site.REQUIRED_MULTI_ASSET_CHANNELS:
            self.assertIn(f"ch-{cid}", doc.ids, f"Missing Layer 3 channel card #ch-{cid} inside .ch-role-group")

        # Channel 08 (qdii_mrf) must NOT be misclassified as HNW 300万 on index.html, channels.html, or channels/qdii_mrf.html
        qdii_home = lint_site._inspect_element_by_id(cockpit, "ch-qdii_mrf")
        self.assertIsNotNone(qdii_home)
        self.assertNotIn("ch-hnw", qdii_home.classes)
        self.assertNotIn("300万门槛", qdii_home.inner_text)

        channels_html = build_site.build_channels_page(ch_data, etf_data=etf_data, eq_state=eq_state)
        qdii_ch_page = lint_site._inspect_element_by_id(channels_html, "ch-qdii_mrf")
        self.assertIsNotNone(qdii_ch_page)
        self.assertNotIn("ch-hnw", qdii_ch_page.classes)
        self.assertNotIn("300万门槛", qdii_ch_page.inner_text)

        qdii_detail = build_site.build_channel_detail_page(ch08, ch_data["channels"], ch_data, etf_data=etf_data)
        self.assertNotIn("300万门槛", qdii_detail)
        self.assertNotIn("300万合格投资者专享", qdii_detail)

        # Sanity-check private_funds_trust STILL carries HNW classification
        pft_home = lint_site._inspect_element_by_id(cockpit, "ch-private_funds_trust")
        self.assertIsNotNone(pft_home)
        self.assertIn("ch-hnw", pft_home.classes)
        self.assertIn("300万门槛", pft_home.inner_text)

    def test_etfs_orthogonal_filters_and_charts_expanded_groups(self):
        gold_snap, eq_state, ch_data, etf_data, kline_manifest = self._load_live_ssots()
        etfs_html = build_site.build_etfs_page(
            etf_data, channel_count=len(ch_data["channels"]), channels_data=ch_data,
        )
        self.assertIn('data-etf-preset="qdii"', etfs_html)

        # Top .stat-tile cards on etfs.html use orthogonal data-etf-stat-ortho
        stat_tile_tags = [
            tag
            for tag in re.findall(r"<div\b[^>]*>", etfs_html)
            if (m_cls := re.search(r'\bclass="([^"]+)"', tag))
            and "stat-tile" in m_cls.group(1).split()
        ]
        self.assertGreaterEqual(len(stat_tile_tags), 5)
        self.assertTrue(
            all("data-etf-stat-ortho=" in tag for tag in stat_tile_tags),
            f"All top .stat-tile cards on etfs.html must use data-etf-stat-ortho: {stat_tile_tags}",
        )

        # Row 1: Orthogonal asset_class filter pills (all 7 canonical values + fixed_income_plus composite pill)
        ac_vals = set(re.findall(r'data-etf-asset-class="([^"]+)"', etfs_html))
        self.assertTrue(
            lint_site.ETF_ALLOWED_ASSET_CLASSES.issubset(ac_vals),
            f"etfs.html missing asset_class filters: {sorted(lint_site.ETF_ALLOWED_ASSET_CLASSES - ac_vals)}",
        )
        self.assertIn("fixed_income_plus", ac_vals)

        # kline.js enforces crypto read-only onshore compliance guard
        kline_js = (ROOT / "scripts" / "web_assets" / "kline.js").read_text(encoding="utf-8")
        self.assertTrue(
            "CRYPTO_ASSET_RE" in kline_js or "crypto_" in kline_js,
            "kline.js missing CRYPTO_ASSET_RE / crypto_ identifier for read-only crypto guard",
        )
        self.assertIn("境内严禁虚拟货币交易", kline_js)

        # Row 2: Orthogonal region filter pills (all 7 canonical values)
        rg_vals = set(re.findall(r'data-etf-region="([^"]+)"', etfs_html))
        self.assertTrue(
            lint_site.ETF_ALLOWED_REGIONS.issubset(rg_vals),
            f"etfs.html missing region filters: {sorted(lint_site.ETF_ALLOWED_REGIONS - rg_vals)}",
        )

        # Row 3: Trading channel filter pills (all 6 channels)
        ch_vals = set(re.findall(r'data-etf-channel="([^"]+)"', etfs_html))
        for req_ch in ("境内场内", "境内非QDII港股通", "境内QDII", "离岸港交所", "离岸美股", "爱尔兰UCITS"):
            self.assertIn(req_ch, ch_vals, f"etfs.html missing channel filter {req_ch!r}")

        # charts.html renders non_us_global & bonds_reits group filters
        multi_idx = build_site._resolve_multi_index_groups(gold_snap, eq_state, kline_manifest)
        charts_html = build_site.build_charts_page(gold_snap, eq_state, multi_idx, [], etf_data, kline_manifest)
        self.assertIn('data-chart-group="non_us_global"', charts_html)
        self.assertIn('data-chart-group="bonds_reits"', charts_html)

    def test_gate_s6_and_s7_catch_six_market_btc_qdii_ortho_and_benchmark_regressions(self):
        # 1. Gate S6 catches missing 6-market cards, missing HK role, unguarded BTC, missing QDII link & bad ETF orthogonal fields
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_etfs = [
                {
                    "code": f"51{i:04d}",
                    "name": f"测试宽基ETF{i}",
                    "market": "a-share",
                    "channel": "境内场内",
                    "asset_class": "equity" if i > 0 else "crypto_bad",
                    "region": "cn" if i > 1 else "mars_bad",
                    "action_role": "核心观察",
                    "gold_locked": False,
                }
                for i in range(140)
            ]
            # Add an ETF whose asset_class == "gold" without gold_locked=True -> must trigger Tier 0 mutex error
            bad_etfs[2].update(code="599999", name="特殊贵金属载体", asset_class="gold", action_role="逢低配置", gold_locked=False)
            eu_path = root / "etf_universe.json"
            eu_path.write_text(
                json.dumps(
                    {
                        "total_etfs": len(bad_etfs),
                        "counts_by_asset_class": {"equity": 138},
                        "counts_by_region": {"cn": 139},
                        "etfs": bad_etfs,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            ma_path = root / "multi_asset_channels.json"
            ma_path.write_text(
                json.dumps(
                    {
                        "channels": [
                            {
                                "id": cid,
                                "name": "场内外跨境基金" if cid == "qdii_mrf" else f"渠道 {cid}",
                                "products": [{"code": "P01", "name": "示例"}],
                                "rules_and_redlines": ["风控红线"],
                            }
                            for cid in lint_site.REQUIRED_MULTI_ASSET_CHANNELS
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            bad_index = (
                "<!doctype html><html><body><h1>驾驶舱</h1>"
                '<div id="card-a-share">A股</div><div id="card-hk-stock">港股</div>'
                "<p>比特币 BTC 报 $61,428</p>"
                "</body></html>"
            )
            etf_rows = "".join("<tr><td>x</td></tr>" for _ in bad_etfs)
            bad_etfs_html = (
                "<!doctype html><html><body><h1>ETF雷达</h1>"
                f'<table><tbody id="etf-tbody">{etf_rows}</tbody></table>'
                f'<script id="etf-data" type="application/json">{json.dumps(bad_etfs, ensure_ascii=False)}</script>'
                "</body></html>"
            )
            parsed = {
                "index.html": lint_site.parse_html_file("index.html", Path("index.html"), bad_index),
                "etfs.html": lint_site.parse_html_file("etfs.html", Path("etfs.html"), bad_etfs_html),
            }
            errors, warnings = [], []
            with patch.multiple(lint_site, ETF_UNIVERSE_PATH=eu_path, MULTI_ASSET_CHANNELS_PATH=ma_path):
                lint_site.run_gate_s6(
                    parsed,
                    {"tier_code": "Tier 0", "new_buy_allowed": False},
                    {"markets": {"a_share": {}, "hk_stock": {}, "us_stock": {}}},
                    errors,
                    warnings,
                    already_checked_json_gold=True,
                )
            joined = "\n".join(errors)
            self.assertIn("#card-nonus", joined)
            self.assertIn("#card-rates", joined)
            self.assertIn("中国离岸折价腿", joined)
            self.assertIn("境内禁交易", joined)
            self.assertIn("qdii_mrf.html#sec-qdii-compare", joined)
            self.assertIn("must start with 'QDII'", joined)
            self.assertIn("invalid/missing asset_class 'crypto_bad'", joined)
            self.assertIn("invalid/missing region 'mars_bad'", joined)
            self.assertIn("counts_by_asset_class", joined)
            self.assertIn("Gold Tier 0 mutex violation on ETF 599999", joined)

        # 2. Gate S7 full-site check (len(catalog) >= 100) catches missing 6-tab labels, charts groups & new benchmarks
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets" / "klines").mkdir(parents=True)
            idx_html = (
                '<html><body><nav><a href="charts.html">K线</a></nav>'
                "<h1>驾驶舱</h1><div>上证指数 沪深300 创业板指 科创50</div></body></html>"
            )
            ch_html = '<html><body><h1>K线终端</h1><button data-chart-group="a_index">A</button></body></html>'
            (root / "index.html").write_text(idx_html, encoding="utf-8")
            (root / "charts.html").write_text(ch_html, encoding="utf-8")
            shard_obj = {
                "shard": "core",
                "series": {
                    "idx_sh000001": {
                        "id": "idx_sh000001",
                        "bars": [["2026-11-26", 3880.0, 3910.0, 3870.0, 3900.0, 100.0]],
                    }
                },
            }
            (root / "assets" / "klines" / "core.json").write_text(json.dumps(shard_obj), encoding="utf-8")
            catalog = [{"id": "idx_sh000001", "name": "上证指数", "group": "a_index", "shard": "core", "priority": 1}]
            catalog.extend(
                {"id": f"stk_{i:06d}", "name": f"样本{i}", "group": "stocks", "shard": "core"}
                for i in range(105)
            )
            manifest = {"schema_version": "1.0", "shards": {"core": "core.json"}, "catalog": catalog}
            (root / "assets" / "klines" / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            docs = {
                "index.html": lint_site.parse_html_file("index.html", root / "index.html", idx_html),
                "charts.html": lint_site.parse_html_file("charts.html", root / "charts.html", ch_html),
            }
            s7_errs, s7_warns = [], []
            lint_site.run_gate_s7(root, docs, s7_errs, s7_warns)
            s7_joined = "\n".join(s7_errs)
            for expected_tok in (
                "日欧台韩印非美",
                "中美债市与REITs",
                'data-chart-group="non_us_global"',
                'data-chart-group="bonds_reits"',
                *lint_site.S7_REQUIRED_GLOBAL_BENCHMARKS,
            ):
                self.assertIn(expected_tok, s7_joined, f"Gate S7 failed to catch missing {expected_tok!r}")

    def test_gate_s6_and_s7_catch_round1_nonus_qdii_hnw_and_kline_crypto_regressions(self):
        # 1. Gate S6 catches #card-nonus empty .m-sub-val & "境内 — · 离岸 —",
        #    plus #ch-qdii_mrf HNW misclassification on index.html, channels.html & channels/qdii_mrf.html
        bad_index = (
            "<!doctype html><html><body><h1>驾驶舱</h1>"
            '<article class="m-card m-nonus" id="card-nonus">'
            '<button class="m-sub-tile"><span class="m-sub-val"></span>'
            '<span class="m-sub-meta">境内 — · 离岸 —</span></button></article>'
            '<article class="ch-overview-card ch-hnw" id="ch-qdii_mrf">'
            '<span class="ch-hnw-badge">300万门槛</span></article>'
            "</body></html>"
        )
        bad_channels = (
            "<!doctype html><html><body><h1>多元渠道</h1>"
            '<article class="ch-overview-card ch-hnw" id="ch-qdii_mrf">'
            '<span class="ch-hnw-badge">300万门槛</span></article>'
            "</body></html>"
        )
        bad_qdii_detail = (
            "<!doctype html><html><body><h1>QDII 跨境基金</h1>"
            '<span class="ch-hnw-badge">300万合格投资者专享</span>'
            "</body></html>"
        )
        parsed = {
            "index.html": lint_site.parse_html_file("index.html", Path("index.html"), bad_index),
            "channels.html": lint_site.parse_html_file("channels.html", Path("channels.html"), bad_channels),
            "channels/qdii_mrf.html": lint_site.parse_html_file(
                "channels/qdii_mrf.html", Path("channels/qdii_mrf.html"), bad_qdii_detail
            ),
        }
        s6_errs, s6_warns = [], []
        lint_site.run_gate_s6(parsed, {}, {}, s6_errs, s6_warns, already_checked_json_gold=True)
        s6_joined = "\n".join(s6_errs)
        self.assertIn("境内 — · 离岸 —", s6_joined)
        self.assertIn('empty <span class="m-sub-val"></span>', s6_joined)
        self.assertTrue(any("index.html" in e and "#ch-qdii_mrf" in e for e in s6_errs), s6_errs)
        self.assertTrue(any("channels.html" in e and "#ch-qdii_mrf" in e for e in s6_errs), s6_errs)
        self.assertTrue(
            any("channels/qdii_mrf.html" in e and "300万合格投资者专享" in e for e in s6_errs),
            s6_errs,
        )

        # 2. Gate S7 catches assets/kline.js missing crypto read-only compliance guard, and passes when present
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets" / "klines").mkdir(parents=True)
            idx_html = (
                '<html><body><nav><a href="charts.html">K线</a></nav>'
                "<h1>驾驶舱</h1><div>上证指数 沪深300 创业板指 科创50 日欧台韩印非美 中美债市与REITs</div></body></html>"
            )
            ch_html = (
                '<html><body><h1>K线终端</h1>'
                '<button data-chart-group="non_us_global">非美</button>'
                '<button data-chart-group="bonds_reits">债</button></body></html>'
            )
            (root / "index.html").write_text(idx_html, encoding="utf-8")
            (root / "charts.html").write_text(ch_html, encoding="utf-8")
            (root / "assets" / "kline.js").write_text("/* missing crypto guard */\n", encoding="utf-8")
            shard_obj = {
                "shard": "core",
                "series": {
                    "idx_sh000001": {
                        "id": "idx_sh000001",
                        "bars": [["2026-11-26", 3880.0, 3910.0, 3870.0, 3900.0, 100.0]],
                    }
                },
            }
            (root / "assets" / "klines" / "core.json").write_text(json.dumps(shard_obj), encoding="utf-8")
            catalog = [{"id": "idx_sh000001", "name": "上证指数", "group": "a_index", "shard": "core", "priority": 1}]
            catalog.extend(
                {"id": sym_id, "name": sym_id, "group": "global_index", "shard": "core"}
                for sym_id in lint_site.S7_REQUIRED_GLOBAL_BENCHMARKS
            )
            catalog.extend(
                {"id": f"stk_{i:06d}", "name": f"样本{i}", "group": "stocks", "shard": "core"}
                for i in range(90)
            )
            manifest = {"schema_version": "1.0", "shards": {"core": "core.json"}, "catalog": catalog}
            (root / "assets" / "klines" / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            docs = {
                "index.html": lint_site.parse_html_file("index.html", root / "index.html", idx_html),
                "charts.html": lint_site.parse_html_file("charts.html", root / "charts.html", ch_html),
            }
            bad_errs, bad_warns = [], []
            lint_site.run_gate_s7(root, docs, bad_errs, bad_warns)
            self.assertTrue(any("assets/kline.js" in e and "境内严禁虚拟货币交易" in e for e in bad_errs), bad_errs)

            # Adding CRYPTO_ASSET_RE + 境内严禁虚拟货币交易 clears Gate S7 cleanly
            (root / "assets" / "kline.js").write_text(
                'const CRYPTO_ASSET_RE = /^crypto_/i; const MSG = "境内严禁虚拟货币交易";\n',
                encoding="utf-8",
            )
            ok_errs, ok_warns = [], []
            lint_site.run_gate_s7(root, docs, ok_errs, ok_warns)
            self.assertEqual(ok_errs, [])
            self.assertEqual(ok_warns, [])


class TestPolicyCalendarSectionAndGates(unittest.TestCase):
    def _sample_policy_cal(self) -> dict:
        return {
            "schema_version": "1.0",
            "edition_id": "2026-11-27_1130",
            "as_of_cst": "2026-11-27T12:28:00+08:00",
            "policy_briefs": [
                {
                    "id": "brief_cn_1",
                    "region": "CN",
                    "impact_tier": "P0",
                    "authority": "中国央行 / 国家统计局",
                    "timestamp_cst": "2026-11-27 09:30 CST",
                    "headline": "央行单日净投放 2,225 亿元叠加 10 月工企利润同比高增",
                    "plain_takeaway": "短期资金面偏暖、企业盈利环比改善，但红灯防守纪律未改。",
                    "cross_market_transmission": "利好 A 股科技与红利承接，同时缓解港股中资权重估值压力。",
                    "action_guardrail": "严守 A 股股票上限 40%，不追高情绪脉冲，黄金新仓维持 0%。",
                },
                {
                    "id": "brief_us_1",
                    "region": "US",
                    "impact_tier": "P1",
                    "authority": "美国财政部 / 美联储",
                    "timestamp_cst": "2026-11-27 06:00 CST",
                    "headline": "2,180 亿美元国债集中交割临近，10Y 美债重返 4.91%",
                    "plain_takeaway": "发债抽水推升长债收益率，压制高估值科技股。",
                    "cross_market_transmission": "美债利率走高同时施压港股联汇拆息与黄金真实利率。",
                    "action_guardrail": "新钱优先超短美债防弹衣，暂不加仓高估值美股科技。",
                },
                {
                    "id": "brief_gl_1",
                    "region": "GLOBAL",
                    "impact_tier": "P2",
                    "authority": "OPEC+ 秘书处",
                    "timestamp_cst": "2026-11-27 10:00 CST",
                    "headline": "第 42 届部长级会议临近，市场观察增产配额表态",
                    "plain_takeaway": "能源供需节奏牵动全球通胀预期。",
                    "cross_market_transmission": "油价若急涨会再度推高美债收益率。",
                    "action_guardrail": "远离高溢价场内商品 LOF，仅做宏观景气观察。",
                },
            ],
            "upcoming_events": [
                {
                    "id": "ev_today",
                    "region": "HK",
                    "impact_tier": "P1",
                    "date_cst": "2026-11-27",
                    "time_cst": "16:00 CST",
                    "date_precision": "exact",
                    "title": "港股 11 月期指结算与美团三季报披露",
                    "expected_consensus": "关注盘后业绩指引与核心本地商业利润率",
                    "cross_market_transmission": "牵动恒生科技权重与南向资金风偏。",
                    "upside_trigger": "业绩超预期且指引积极，带动恒科放量企稳。",
                    "downside_trigger": "竞争加剧压制利润率引发科技权重回踩。",
                    "pre_event_discipline": "盘中不赌财报方向，等正式公告落地再评估。",
                },
                {
                    "id": "ev_tomorrow",
                    "region": "US",
                    "impact_tier": "P0",
                    "date_cst": "2026-11-28",
                    "time_cst": "13:00 CST",
                    "date_precision": "exact",
                    "title": "美联储进入 12 月议息前缄默期",
                    "expected_consensus": "市场押注高利率维持更久，关注最后官员表态",
                    "cross_market_transmission": "影响美债 10Y 与美元指数波动区间。",
                    "upside_trigger": "鸽派信号带动美债收益率回落至 4.70% 下方。",
                    "downside_trigger": "鹰派表态令 10Y 美债逼近 5.0% 警戒区。",
                    "pre_event_discipline": "保持美股防弹衣与超短债组合，严禁杠杆。",
                },
                {
                    "id": "ev_eu_14d",
                    "region": "EU",
                    "impact_tier": "P1",
                    "date_cst": "2026-12-03",
                    "time_cst": "18:00 CST",
                    "date_precision": "exact",
                    "title": "欧元区 11 月调和 CPI 初值公布",
                    "expected_consensus": "核心通胀环比温和回落",
                    "cross_market_transmission": "影响欧央行降息节奏与德股 DAX 估值。",
                    "upside_trigger": "通胀温和回落利好欧股低费直投工具。",
                    "downside_trigger": "服务业通胀黏性超预期推高欧债收益率。",
                    "pre_event_discipline": "境内跨境工具买前必核参考净值溢价。",
                },
                {
                    "id": "ev_tbd_30d",
                    "region": "CN",
                    "impact_tier": "P0",
                    "date_cst": "2026-12-15",
                    "time_cst": "",
                    "date_precision": "window_tbd",
                    "title": "中央经济工作会议定调 2027 年宏观政策",
                    "expected_consensus": "关注赤字率、扩内需与科技自主可控定调",
                    "cross_market_transmission": "直接定调 A 股与港股跨年主线及中债久期。",
                    "upside_trigger": "财政发力与消费托举力度超预期。",
                    "downside_trigger": "总量刺激克制导致高弹性题材获利回吐。",
                    "pre_event_discipline": "会议窗口前严控追高，保留红利与债券压舱石。",
                },
                {
                    "id": "ev_jp_30d",
                    "region": "JP",
                    "impact_tier": "P0",
                    "date_cst": "2026-12-18",
                    "time_cst": "11:00 CST",
                    "date_precision": "exact",
                    "title": "日本央行 12 月议息决议与美股四巫日",
                    "expected_consensus": "市场高度警惕日元 160 关口附近政策加息与汇市干预",
                    "cross_market_transmission": "日元若急升易触发套息平仓波及全球科技股。",
                    "upside_trigger": "节奏渐进透明，汇市平稳过渡。",
                    "downside_trigger": "超预期鹰派引发美元兑日元 3 日急跌触发危机熔断观察。",
                    "pre_event_discipline": "提前核查组合波动承受力，严守现金缓冲。",
                },
            ],
        }

    def test_policy_calendar_renders_live_state_and_fallback_cleanly(self):
        gold_snap = json.loads((ROOT / "gold" / "data_snapshot.json").read_text(encoding="utf-8"))
        eq_state = json.loads((ROOT / "equity" / "state" / "market_state.json").read_text(encoding="utf-8"))
        sample_pcal = self._sample_policy_cal()

        cockpit_live = build_site.build_cockpit_page(
            gold_snap,
            eq_state,
            {},
            {"a-share": 76, "hk-stock": 75, "us-stock": 80},
            policy_calendar=sample_pcal,
        )
        # Placed right above #sec-risk-radar & jump-bar pill present
        pos_pcal = cockpit_live.find('id="sec-policy-calendar"')
        pos_risk = cockpit_live.find('id="sec-risk-radar"')
        self.assertGreater(pos_pcal, 0)
        self.assertGreater(pos_risk, pos_pcal)
        self.assertIn('<a class="home-jump-pill" href="#sec-policy-calendar">🧭 时政深解与日历</a>', cockpit_live)
        self.assertIn("🧭 核心时政政策深解 · 未来 14–30 天金融时政日历", cockpit_live)
        self.assertIn("上证指数（000001.SH · 大盘总舵）", cockpit_live)

        # Pure-Chinese badges & zero raw P0/P1/P2 in .pcal-tier-pill
        snap = lint_site._inspect_policy_calendar_section(cockpit_live)
        self.assertIsNotNone(snap)
        self.assertIn("核心时政", snap.inner_text)
        self.assertGreaterEqual(len(snap.tier_pill_texts), 6)
        self.assertTrue(any("🔴 一级关键" in t for t in snap.tier_pill_texts))
        self.assertTrue(any("🟠 二级重点" in t for t in snap.tier_pill_texts))
        self.assertTrue(any("⚪ 三级常规" in t for t in snap.tier_pill_texts))
        for t in snap.tier_pill_texts:
            self.assertIsNone(lint_site.PCAL_RAW_TIER_RE.search(t), f"Raw tier leaked in pill: {t!r}")

        # Countdown labels, window_tbd, filter bar & 15-30d toggle button
        self.assertIn(">今日<", cockpit_live)
        self.assertIn(">明日<", cockpit_live)
        self.assertIn("T+6 天", cockpit_live)
        self.assertIn("窗口待定", cockpit_live)
        self.assertIn('id="pcal-toggle-30d"', cockpit_live)
        self.assertIn('data-pcal-region="GLOBAL_EX"', cockpit_live)
        self.assertIn('data-pcal-tier="P0"', cockpit_live)

        # cmd-nav-data includes policy calendar entry & 48 glossary terms preserved
        cmd_items = build_site._build_cmd_nav_items("", 231)
        self.assertTrue(
            any(
                it.get("title") == "🧭 核心时政深解与未来 30 天金融日历"
                and it.get("href") == "index.html#sec-policy-calendar"
                for it in cmd_items
            )
        )
        self.assertEqual(len(build_site.GLOSSARY_TERMS), 48)

        # Verify real live equity/state/policy_calendar.json fields (watch_triggers/market_transmission/pre_event_stance) render cleanly
        live_pcal_path = ROOT / "equity" / "state" / "policy_calendar.json"
        if live_pcal_path.is_file():
            live_pcal = json.loads(live_pcal_path.read_text(encoding="utf-8"))
            self.assertTrue(live_pcal.get("as_of_cst"))
            self.assertGreaterEqual(len(live_pcal.get("events") or []), 1)
            live_gold_blocked = lint_site._is_gold_new_buy_blocked(gold_snap, eq_state)
            live_html = build_site._render_policy_calendar_section(
                live_pcal, eq_state, gold_blocked=live_gold_blocked
            )
            live_snap = lint_site._inspect_policy_calendar_section(live_html)
            self.assertIsNotNone(live_snap)
            self.assertIn("核心时政", live_snap.inner_text)
            for t in live_snap.tier_pill_texts:
                self.assertIsNone(lint_site.PCAL_RAW_TIER_RE.search(t), f"Raw tier leaked on live policy_calendar: {t!r}")
            self.assertIsNone(
                lint_site.PCAL_RAW_TIER_RE.search(live_snap.inner_text),
                "Raw P0/P1/P2 leaked inside live #sec-policy-calendar inner_text",
            )
            # 实操边界 never starts with awkward 但/但是/不过
            self.assertNotIn("<strong>实操边界：</strong>但", live_html)
            self.assertNotIn("<strong>实操边界：</strong>不过", live_html)
            first_ev = (live_pcal.get("events") or live_pcal.get("upcoming_events") or [{}])[0]
            if isinstance(first_ev.get("watch_triggers"), dict) and first_ev["watch_triggers"].get("upside_bull"):
                self.assertIn(html.escape(first_ev["watch_triggers"]["upside_bull"][:16], quote=True), live_html)
            if first_ev.get("pre_event_stance"):
                self.assertIn(html.escape(first_ev["pre_event_stance"][:16], quote=True), live_html)

        # HTML-escaped <= / >= operators in pre_event_stance & watch_triggers (P0-4 Monday rollover guard)
        esc_pcal = {
            "as_of_cst": "2026-11-30T07:30:00+08:00",
            "policy_briefs": sample_pcal["policy_briefs"],
            "events": [
                {
                    "event_id": "cn_nov_pmi_html_escape_test",
                    "date_cst": "2026-11-30",
                    "end_date_cst": "2026-11-30",
                    "date_precision": "exact",
                    "time_cst": "09:30",
                    "region": "CN",
                    "category": "macro_data",
                    "impact_tier": "P0",
                    "title": "中国 11 月官方 PMI 发布",
                    "expected_consensus": "预期 50.1",
                    "market_transmission": "景气读数影响顺周期",
                    "watch_triggers": {"upside_bull": "PMI >=50.5 提振内需", "downside_bear": "PMI <49.5 承压"},
                    "pre_event_stance": "A 股严守 <=40% 上限与红利底座。",
                    "affected_markets": ["a_share"],
                    "source_url": "https://www.stats.gov.cn/",
                }
            ],
        }
        esc_html = build_site._render_policy_calendar_section(esc_pcal, eq_state, gold_blocked=True)
        self.assertIn(html.escape("A 股严守 <=40% 上限与红", quote=True), esc_html)
        self.assertIn(html.escape("PMI >=50.5 提振内需", quote=True), esc_html)

        # Exact multi-day span renders end_date_cst cleanly (self-contained fixture immune to calendar rollover)
        span_pcal = {
            "as_of_cst": "2026-11-27T18:00:00+08:00",
            "policy_briefs": sample_pcal["policy_briefs"],
            "events": [
                {
                    "event_id": "span_test_20261130",
                    "date_cst": "2026-11-30",
                    "end_date_cst": "2026-12-01",
                    "date_precision": "exact",
                    "time_cst": "21:30",
                    "region": "US",
                    "category": "liquidity_treasury",
                    "impact_tier": "P1",
                    "title": "跨月美债结算窗口测试",
                    "expected_consensus": "测试预期",
                    "market_transmission": "测试传导",
                    "pre_event_stance": "严守防守仓位。",
                    "affected_markets": ["us_stock"],
                    "source_url": "https://home.treasury.gov/",
                }
            ],
        }
        span_html = build_site._render_policy_calendar_section(span_pcal, eq_state, gold_blocked=True)
        self.assertIn("2026-11-30–12-01 21:30", span_html)

        # Leading 但/但是/不过 is stripped cleanly when market_impact splits into 实操边界
        conj_pcal = {
            "as_of_cst": "2026-11-27T12:28:00+08:00",
            "policy_briefs": [
                {
                    "id": "b_conj",
                    "region": "CN",
                    "impact_tier": "P1",
                    "authority": "央行",
                    "headline": "测试转折词剥离",
                    "summary": "摘要。",
                    "affected_markets": ["a_share"],
                    "market_impact": "短线情绪回暖；但是，沪深 300 仍在年线下严守仓位上限。",
                }
            ],
            "events": sample_pcal.get("events") or sample_pcal.get("upcoming_events") or [],
        }
        conj_html = build_site._render_policy_calendar_section(conj_pcal, eq_state, gold_blocked=True)
        self.assertIn("<strong>实操边界：</strong>沪深 300 仍在年线下严守仓位上限。", conj_html)

        # Sticky desktop left column CSS & smart 15-30d toggle hiding in app.js
        app_css = (ROOT / "scripts" / "web_assets" / "app.css").read_text(encoding="utf-8")
        app_js = (ROOT / "scripts" / "web_assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("@media (min-width: 961px)", app_css)
        self.assertIn(".pcal-col:first-child", app_css)
        self.assertIn("const hideToggle = !show30d && hidden30d === 0;", app_js)

        # Graceful fallback when policy_calendar is None (live market_state.policy_radars & minimal fixture)
        cockpit_fb = build_site.build_cockpit_page(
            gold_snap,
            eq_state,
            {},
            {"a-share": 76, "hk-stock": 75, "us-stock": 80},
            policy_calendar=None,
        )
        fb_snap = lint_site._inspect_policy_calendar_section(cockpit_fb)
        self.assertIsNotNone(fb_snap)
        self.assertIn("核心时政", fb_snap.inner_text)
        self.assertNotIn("NaN", fb_snap.inner_text)
        for t in fb_snap.tier_pill_texts:
            self.assertIsNone(lint_site.PCAL_RAW_TIER_RE.search(t))

        min_cockpit = build_site.build_cockpit_page(
            {"new_buy_allowed": False, "tier_code": "Tier 0", "as_of_short": "2026-11-27 07:30"},
            {"as_of_cst": "2026-11-27T07:30:00+08:00", "markets": {"a_share": {"benchmark_sse": 3486.0}}},
            {},
            {"a-share": 76},
            policy_calendar=None,
        )
        min_snap = lint_site._inspect_policy_calendar_section(min_cockpit)
        self.assertIsNotNone(min_snap)
        self.assertIn("核心时政", min_snap.inner_text)
        self.assertNotIn("NaN", min_snap.inner_text)

    def test_gate_s3_and_s6_policy_calendar_guards(self):
        # Gate S3 blocks policy_calendar.json, realtime_monitor.py, wechat_notify.py, sqlite & notify config leaks
        for leak_tok in (
            "policy_calendar.json",
            "realtime_monitor.py",
            "wechat_notify.py",
            "realtime-monitor.sqlite3",
            "notify.example.json",
            "notify.json",
        ):
            self.assertIsNotNone(
                lint_site.S3_INTERNAL_ENG_LEAK_RE.search(f"请检查 {leak_tok} 输出"),
                f"Gate S3 missed leak token: {leak_tok}",
            )
            self.assertIsNotNone(
                build_site._HARD_INFRA_RE.search(f"请检查 {leak_tok} 输出"),
                f"build_site._HARD_INFRA_RE missed leak token: {leak_tok}",
            )

        # Aligned GOLD_ACTIVE_BUY_RE catches 低吸/布局/上车 while preserving negation guards
        for bad_line in ("会前可低吸黄金防通胀", "建议布局黄金ETF 518880", "趁回调上车 518880"):
            m = lint_site.GOLD_ACTIVE_BUY_RE.search(bad_line)
            self.assertIsNotNone(m, f"Missed gold active buy phrase: {bad_line}")
            self.assertFalse(lint_site._gold_action_is_guarded(bad_line, m), bad_line)
        for safe_line in ("红灯停期暂不布局黄金", "严禁低吸黄金ETF 518880", "不要上车 518880"):
            for m in lint_site.GOLD_ACTIVE_BUY_RE.finditer(safe_line):
                self.assertTrue(lint_site._gold_action_is_guarded(safe_line, m), safe_line)

        # Gate S6 enforces #sec-policy-calendar checks when POLICY_CALENDAR_PATH exists
        with tempfile.TemporaryDirectory() as tmp:
            pcal_file = Path(tmp) / "policy_calendar.json"
            pcal_file.write_text(json.dumps(self._sample_policy_cal(), ensure_ascii=False), encoding="utf-8")

            bad_index = (
                "<!doctype html><html><body><h1>驾驶舱</h1>"
                '<section id="sec-policy-calendar">'
                '<h2>普通日程表</h2>'
                '<span class="pcal-tier-pill pcal-tier-p0">P0 关键</span>'
                "<p>政策落地后可立即买入黄金ETF 518880 抢反弹。</p>"
                "</section></body></html>"
            )
            parsed = {
                "index.html": lint_site.parse_html_file("index.html", Path("index.html"), bad_index),
            }
            errs, warns = [], []
            with patch.object(lint_site, "POLICY_CALENDAR_PATH", pcal_file):
                lint_site.run_gate_s6(
                    parsed,
                    {"tier_code": "Tier 0", "new_buy_allowed": False},
                    {"markets": {"a_share": {}, "hk_stock": {}, "us_stock": {}}},
                    errs,
                    warns,
                    already_checked_json_gold=True,
                )
            joined = "\n".join(errs)
            self.assertIn("missing required heading/text '核心时政'", joined)
            self.assertIn("leaked raw tier code", joined)
            self.assertIn("#sec-policy-calendar Gold Tier 0 mutex violation", joined)

            # Gate S6 full inner_text scan catches raw P0/P1/P2 leaked OUTSIDE .pcal-tier-pill!
            prose_tier_leak_index = (
                "<!doctype html><html><body><h1>驾驶舱</h1>"
                '<section id="sec-policy-calendar">'
                "<h2>🧭 核心时政政策深解</h2>"
                '<span class="pcal-tier-pill pcal-tier-p0">🔴 一级关键</span>'
                "<p>本周重点盯紧 P1 级别财政会议与 P0 联储决议。</p>"
                "</section></body></html>"
            )
            errs_prose, warns_prose = [], []
            with patch.object(lint_site, "POLICY_CALENDAR_PATH", pcal_file):
                lint_site.run_gate_s6(
                    {"index.html": lint_site.parse_html_file("index.html", Path("index.html"), prose_tier_leak_index)},
                    {"tier_code": "Tier 0", "new_buy_allowed": False},
                    {"markets": {"a_share": {}, "hk_stock": {}, "us_stock": {}}},
                    errs_prose,
                    warns_prose,
                    already_checked_json_gold=True,
                )
            self.assertTrue(
                any("visible text leaked raw tier code(s)" in e and "P0" in e and "P1" in e for e in errs_prose),
                errs_prose,
            )

            # Missing #sec-policy-calendar completely is also caught
            missing_index = "<!doctype html><html><body><h1>驾驶舱</h1></body></html>"
            errs2, warns2 = [], []
            with patch.object(lint_site, "POLICY_CALENDAR_PATH", pcal_file):
                lint_site.run_gate_s6(
                    {"index.html": lint_site.parse_html_file("index.html", Path("index.html"), missing_index)},
                    {"tier_code": "Tier 0", "new_buy_allowed": False},
                    {"markets": {"a_share": {}, "hk_stock": {}, "us_stock": {}}},
                    errs2,
                    warns2,
                    already_checked_json_gold=True,
                )
            self.assertTrue(any("missing #sec-policy-calendar" in e for e in errs2), errs2)


class TestFullSiteRedesignBugFixesAndIA(unittest.TestCase):
    def test_parse_scorecard_stats_ignores_at_least_partial_percentage(self):
        gold_md = (
            "| 统计口径 | 项数 | 兑现 | 部分兑现 | 证伪 | 未触发 | 完全兑现率 | 至少部分兑现（已评分） |\n"
            "| --- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |\n"
            "| 已到期（投资项） | 14（投资计分 12） | 7 | 5 | 0 | 2 | 58.3% | 100.0% |\n"
            "| 持续追踪 | 4 | — | — | — | — | — | — |\n"
        )
        stats = build_site.parse_scorecard_stats(gold_md, "")
        self.assertEqual(stats["gold"]["hit"], 7)
        self.assertEqual(stats["gold"]["partial"], 5)
        self.assertEqual(stats["gold"]["miss"], 0)
        self.assertAlmostEqual(stats["gold"]["at_least_partial_pct"], 100.0)
        # Also confirm real live SCORECARD.md never confuses 100% rate with partial count
        live_gold = (ROOT / "gold" / "daily" / "SCORECARD.md").read_text(encoding="utf-8")
        live_eq = (ROOT / "equity" / "daily" / "SCORECARD.md").read_text(encoding="utf-8")
        live_stats = build_site.parse_scorecard_stats(live_gold, live_eq)
        self.assertGreaterEqual(live_stats["gold"]["partial"], 0)
        self.assertLessEqual(live_stats["gold"]["partial"], live_stats["gold"]["settled"])

    def test_inject_glossary_tips_skips_badge_and_pill_classes(self):
        html = (
            '<div class="ch-card">'
            '<span class="ch-badge">34只LOF退市线</span>'
            '<p>购买跨境基金时必须避开场内溢价与 LOF 退市陷阱。</p>'
            "</div>"
        )
        out = build_site.inject_glossary_tips(html)
        self.assertIn('<span class="ch-badge">34只LOF退市线</span>', out)
        self.assertIn('data-term="lof_delist"', out)
        self.assertIn('data-term="premium_discount"', out)

    def test_redesign_assets_prevent_provider_leak_and_mobile_overflow(self):
        kline_js = (ROOT / "scripts" / "web_assets" / "kline.js").read_text(encoding="utf-8")
        app_css = (ROOT / "scripts" / "web_assets" / "app.css").read_text(encoding="utf-8")
        app_js = (ROOT / "scripts" / "web_assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn("PROVIDER_LABELS", kline_js)
        self.assertIn("tencent_newfqkline", kline_js)
        self.assertIn("function fmtProviderLabel(", kline_js)

        self.assertIn(".compact-alert-pill", app_css)
        self.assertIn("white-space: normal;", app_css)
        self.assertIn(".mobile-tabbar", app_css)
        self.assertIn(".nav-drop-item", app_css)
        self.assertIn("justify-content: flex-start;", app_css)
        self.assertIn(".watch-drawer", app_css)

        self.assertIn("formatCount: formatCount", app_js)
        self.assertIn("goToIndex: goToIndex", app_js)
        self.assertIn(".lamp-defend", app_css)
        self.assertIn(".ah-mcards", app_css)
        self.assertIn("align-items: stretch;", app_css)
        # Ensure .ah-mcards mobile display:flex appears AFTER base .ah-mcards display:none
        base_ah_pos = app_css.find(".ah-mcards {\n  display: none;")
        mob_ah_pos = app_css.rfind(".ah-mcards {\n    display: flex;")
        self.assertGreater(base_ah_pos, 0)
        self.assertGreater(mob_ah_pos, base_ah_pos)
        # Ensure equity/pdf_common classify_callout treats 极简方案 as calm guard, not danger
        import equity.pdf_common as pdf_common
        cls = pdf_common.classify_callout(
            ["极简“低费 ETF + 门控黄金”默认方案", "下单前务必避坑高溢价场内产品。"]
        )
        self.assertNotIn("callout-danger", cls)


class TestVisualWidgetsAndUncappedMarketNews(unittest.TestCase):
    def test_all_four_visual_widget_types_render_collision_free_svgs(self):
        import visual_widgets
        import svg_geometry

        specs = [
            {
                "type": "waterfall",
                "title": "现金流与利润桥拆解（亿元）",
                "subtitle": "从核心主业到最终净利分项瀑布",
                "unit": "亿",
                "takeaway": "新业务扩张带来阶段性拖累，但主业现金流底盘稳健。",
                "bars": [
                    {"label": "核心主业", "value": 43.9, "kind": "start", "val_label": "+43.9亿"},
                    {"label": "海外投入", "value": -20.9, "kind": "sub", "val_label": "-20.9亿"},
                    {"label": "税费财务", "value": -4.5, "kind": "sub"},
                    {"label": "归母净利", "value": 18.5, "kind": "total", "val_label": "净剩18.5亿"},
                    {"label": "去年同期", "value": 21.0, "kind": "compare", "val_label": "同比21.0亿"},
                ],
                "benchmark": {"value": 22.0, "label": "市场一致预期 22.0 亿"},
            },
            {
                "type": "bar_compare",
                "title": "国内渠道单克价格横向对比（元/克）",
                "subtitle": "越短越省钱",
                "max_val": 1100,
                "unit": "元/克",
                "threshold": {"val": 850, "label": "合理参考线", "color": "#15803d"},
                "items": [
                    {"label": "上金所基准", "value": 784.4, "val_label": "784.4 元/克", "tag": "无溢价", "color": "#15803d", "highlight": True},
                    {"label": "四大行金条", "value": 814.0, "val_label": "814.0 元/克", "tag": "+29.6 元", "color": "#1d4ed8"},
                    {"label": "品牌首饰", "value": 1068.0, "val_label": "1,068 元/克", "tag": "含工费", "color": "#dc2626"},
                ],
            },
            {
                "type": "anchor_range",
                "title": "焦点股现价 vs 安全买点锚对比（元）",
                "subtitle": "实心点为现价，绿色带为安全买点锚",
                "items": [
                    {
                        "name": "招商银行",
                        "code": "600036",
                        "current": 43.5,
                        "anchor_low": 40.5,
                        "anchor_high": 42.0,
                        "unit": "元",
                        "stance": "base",
                        "stance_label": "高息底座",
                        "gap_label": "高出锚顶 +3.6%",
                        "hint": "回踩锚区再分批",
                    },
                    {
                        "name": "中微公司",
                        "code": "688012",
                        "current": 236.0,
                        "anchor_low": 195.0,
                        "anchor_high": 210.0,
                        "unit": "元",
                        "stance": "wait",
                        "stance_label": "静待回踩",
                        "gap_label": "高出锚顶 +12.4%",
                        "hint": "不追高等待回踩",
                    },
                ],
            },
            {
                "type": "flow_chain",
                "title": "政策落地到仓位风控四步传导链",
                "subtitle": "一步看懂因果路径",
                "steps": [
                    {"step": "第 1 环", "title": "国常会定调", "metric": "增量政策落地", "desc": "定向支持内需与设备更新", "tone": "blue"},
                    {"step": "第 2 环", "title": "资金回流", "metric": "成交 >2万亿", "desc": "两市成交放量确认情绪", "tone": "amber"},
                    {"step": "第 3 环", "title": "基差验证", "metric": "IF 升水收敛", "desc": "正套对冲非单边看空", "tone": "teal"},
                    {"step": "第 4 环", "title": "仓位纪律", "metric": "上限 <=40%", "desc": "维持红灯总仓位上限不变", "tone": "red"},
                ],
            },
        ]
        rendered_by_type: dict[str, str] = {}
        for spec in specs:
            self.assertEqual(visual_widgets.validate_visual_spec(spec), [], spec["type"])
            rendered = visual_widgets.render_visual_chart(spec)
            rendered_by_type[spec["type"]] = rendered
            self.assertIn("<svg ", rendered)
            self.assertIn('class="chart-box visual-chart-box"', rendered)
            issues = svg_geometry.check_svg_text_geometry(rendered, label=f"test:{spec['type']}")
            self.assertEqual(issues, [], f"SVG geometry collision on {spec['type']}: {issues}")
        # Verify real renderer fields actually appear in output SVGs
        self.assertIn("+43.9亿", rendered_by_type["waterfall"])
        self.assertIn("净剩18.5亿", rendered_by_type["waterfall"])
        self.assertIn("同比21.0亿", rendered_by_type["waterfall"])
        self.assertIn("高息底座", rendered_by_type["anchor_range"])
        self.assertIn("高出锚顶 +3.6%", rendered_by_type["anchor_range"])
        self.assertIn("回踩锚区再分批", rendered_by_type["anchor_range"])
        self.assertIn("增量政策落地", rendered_by_type["flow_chain"])
        self.assertIn("定向支持内需与设备更新", rendered_by_type["flow_chain"])

    def test_home_caps_featured_briefs_at_9_while_single_market_news_is_uncapped(self):
        eq_state = json.loads((ROOT / "equity" / "state" / "market_state.json").read_text(encoding="utf-8"))
        # Build 14 synthetic briefs all targeting a_share, with 11 marked home_featured=True
        many_briefs = [
            {
                "id": f"b_ashare_{i:02d}",
                "date_cst": "2026-11-27",
                "time_cst": f"{8 + (i % 10):02d}:30",
                "region": "CN",
                "category": "policy_regulation",
                "impact_tier": "P0" if i < 4 else "P1",
                "home_featured": i < 11,
                "authority": "央行与证监会联合公告",
                "headline": f"A股重磅新闻第 {i + 1} 条测试标题",
                "summary": f"第 {i + 1} 条重要新闻详尽摘要内容。",
                "affected_markets": ["a_share", "hk_stock"] if i % 2 == 0 else ["a_share"],
                "market_impact": "影响板块估值节奏；严守红灯仓位上限，暂不新买黄金。",
                "source_url": "https://www.gov.cn/",
            }
            for i in range(14)
        ]
        synth_pcal = {
            "edition_id": "2026-11-27_1800_r2",
            "as_of_cst": "2026-11-27T23:55:00+08:00",
            "horizon_days": 30,
            "policy_briefs": many_briefs,
            "events": [],
        }

        # Home page MUST clamp featured briefs to <= 9 and render quick-jump uncapped count (14)
        home_html = build_site._render_policy_calendar_section(synth_pcal, eq_state, gold_blocked=True)
        self.assertEqual(home_html.count("pcal-brief-card"), 9)
        self.assertIn('id="pcal-brief-filters"', home_html)
        self.assertIn("a-share-latest.html#sec-market-news", home_html)
        self.assertIn("14 条", home_html)

        # Single-market news radar MUST display ALL 14 A-share briefs with ZERO upper cap!
        mnews_html, mnews_cnt = build_site._render_market_news_radar(
            "a-share", synth_pcal, eq_state, gold_blocked=True
        )
        self.assertEqual(mnews_cnt, 14)
        self.assertEqual(mnews_html.count("mnews-card"), 14)
        self.assertIn('id="sec-market-news"', mnews_html)
        self.assertIn("A股重磅新闻第 14 条测试标题", mnews_html)
        # No raw P0/P1/P2 leaked in visible inner text
        m_parser = lint_site._PolicyCalendarSectionParser("sec-market-news")
        m_parser.feed(mnews_html)
        m_parser.close()
        m_snap = m_parser.result()
        self.assertIsNotNone(m_snap)
        self.assertIsNone(lint_site.PCAL_RAW_TIER_RE.search(m_snap.inner_text))

        # Verify both locked & unlocked gold_blocked paths render cleanly on synthetic fixture
        home_unlocked = build_site._render_policy_calendar_section(synth_pcal, eq_state, gold_blocked=False)
        self.assertEqual(home_unlocked.count("pcal-brief-card"), 9)

        # Live repo policy_calendar.json matches live Gold lock & uncapped counts per market without brittle floors
        gold_snap = json.loads((ROOT / "gold" / "data_snapshot.json").read_text(encoding="utf-8"))
        live_gold_blocked = lint_site._is_gold_new_buy_blocked(gold_snap, eq_state)
        live_pcal = json.loads((ROOT / "equity" / "state" / "policy_calendar.json").read_text(encoding="utf-8"))
        live_home = build_site._render_policy_calendar_section(live_pcal, eq_state, gold_blocked=live_gold_blocked)
        home_card_cnt = live_home.count("pcal-brief-card")
        self.assertTrue(1 <= home_card_cnt <= 9, f"Expected 1-9 featured home briefs, got {home_card_cnt}")
        live_briefs = live_pcal.get("policy_briefs") or []
        for mslug, mk_key in (("a-share", "a_share"), ("hk-stock", "hk_stock"), ("us-stock", "us_stock"), ("gold", "gold")):
            expected_cnt = sum(1 for b in live_briefs if mk_key in (b.get("affected_markets") or []))
            mh, mcnt = build_site._render_market_news_radar(mslug, live_pcal, eq_state, gold_blocked=live_gold_blocked)
            self.assertEqual(mcnt, expected_cnt, f"Market {mslug} count diverged from policy_calendar.json")
            self.assertGreaterEqual(mcnt, 1, f"Expected >=1 uncapped brief for {mslug}, got {mcnt}")
            self.assertEqual(mh.count("mnews-card"), mcnt)

    def test_auto_visual_cockpit_stacked_probability_ribbon_and_flow_chain(self):
        gold_snap = json.loads((ROOT / "gold" / "data_snapshot.json").read_text(encoding="utf-8"))
        eq_state = json.loads((ROOT / "equity" / "state" / "market_state.json").read_text(encoding="utf-8"))

        # Top visual cockpit renders cleanly for both equity and gold
        eq_cockpit = build_site._render_daily_visual_cockpit("a-share", eq_state, gold_snap, "")
        self.assertIn("daily-visual-cockpit", eq_cockpit)
        self.assertIn("dvc-alloc-bar", eq_cockpit)
        self.assertIn("dvc-brake-grid", eq_cockpit)
        gold_cockpit = build_site._render_daily_visual_cockpit("gold", eq_state, gold_snap, "")
        self.assertIn("daily-visual-cockpit", gold_cockpit)
        self.assertIn("买金四步红绿灯进度仪", gold_cockpit)

        # Auto-upgrades <ul> 4-scenario probability block AND inline flow chain
        sample_body = (
            "<p><strong>跨资产传导链（一句话）</strong>：「中东油价高位 → 10年期美债逼近 5% → 美元走强 → 股票估值承压」。</p>"
            "<ul>"
            "<li><strong>情景一：震荡修复</strong>：●●●●○○○○○○（40%）—— 核心理由。</li>"
            "<li><strong>情景二：缓步回踩</strong>：●●●○○○○○○○（30%）—— 次要理由。</li>"
            "<li><strong>情景三：政策强刺激</strong>：●●○○○○○○○○（20%）—— 上行催化。</li>"
            "<li><strong>情景四：外部冲击</strong>：●○○○○○○○○○（10%）—— 尾部风控。</li>"
            "</ul>"
        )
        enhanced = build_site._enhance_daily_body_visuals(sample_body)
        self.assertIn("prob-ribbon-card", enhanced)
        self.assertIn("prob-seg", enhanced)
        self.assertIn("pdot-on", enhanced)
        self.assertIn("inline-flow-wrap", enhanced)
        self.assertIn("ifc-node", enhanced)


class TestWave2VisualWidgetsCockpitAndSiteLinters(unittest.TestCase):
    def test_waterfall_custom_val_label_and_sub_positive_minus_sign(self):
        import visual_widgets
        import svg_geometry

        spec = {
            "type": "waterfall",
            "title": "财政发债净流动性瀑布（亿美元）",
            "unit": "亿",
            "bars": [
                {"label": "期初准备金", "value": 2180.0, "kind": "start", "val_label": "+2,180亿"},
                {"label": "国债抽水", "value": 815.1, "kind": "sub"},  # positive value with kind="sub" MUST render "-"
                {"label": "净剩缓冲", "value": 3.0, "kind": "total", "val_label": "仅剩3.0亿"},
                {"label": "警戒对照", "value": 500.0, "kind": "compare", "val_label": "安全线500亿"},
            ],
        }
        self.assertEqual(visual_widgets.validate_visual_spec(spec), [])
        rendered = visual_widgets.render_visual_chart(spec)
        self.assertIn("+2,180亿", rendered)
        self.assertIn("-815.10亿", rendered)
        self.assertNotIn("+815.10亿", rendered)
        self.assertIn("仅剩3.0亿", rendered)
        self.assertIn("安全线500亿", rendered)
        self.assertEqual(svg_geometry.check_svg_text_geometry(rendered, label="wf_p0_1"), [])

    def test_validate_visual_spec_rejects_bool_nan_inf_inverted_anchor_and_over_8_bars(self):
        import visual_widgets

        # 1. Bool rejected
        bad_bool = {
            "type": "waterfall",
            "title": "布尔值校验",
            "bars": [{"label": "A", "value": True}, {"label": "B", "value": 10}],
        }
        self.assertTrue(visual_widgets.validate_visual_spec(bad_bool))

        # 2. NaN / Inf rejected
        for bad_num in (float("nan"), float("inf"), float("-inf")):
            bad_bar = {
                "type": "bar_compare",
                "title": "非有限数校验",
                "items": [{"label": "A", "value": bad_num}, {"label": "B", "value": 5}],
            }
            self.assertTrue(visual_widgets.validate_visual_spec(bad_bar), f"Failed to reject {bad_num!r}")

        # 3. anchor_low > anchor_high rejected
        bad_anchor = {
            "type": "anchor_range",
            "title": "锚区倒挂校验",
            "items": [{"name": "测试股", "current": 50, "anchor_low": 60, "anchor_high": 40}],
        }
        errs_a = visual_widgets.validate_visual_spec(bad_anchor)
        self.assertTrue(any("anchor_low" in e and "anchor_high" in e for e in errs_a), errs_a)

        # 4. >8 waterfall bars rejected (9 bars)
        too_many = {
            "type": "waterfall",
            "title": "超量柱体校验",
            "bars": [{"label": f"项{i}", "value": i + 1} for i in range(9)],
        }
        errs_wf = visual_widgets.validate_visual_spec(too_many)
        self.assertTrue(any("2–8" in e for e in errs_wf), errs_wf)

    def test_anchor_range_col_left_label_default_and_extract_skips_fenced_code(self):
        import visual_widgets

        base_spec = {
            "type": "anchor_range",
            "title": "标的现价 vs 安全锚",
            "items": [
                {"name": "短融ETF", "code": "511360", "current": 110.2, "anchor_low": 109.8, "anchor_high": 110.5}
            ],
        }
        default_svg = visual_widgets.render_visual_chart(base_spec)
        self.assertIn(">标的与阵营</text>", default_svg)

        custom_svg = visual_widgets.render_visual_chart({**base_spec, "col_left_label": "重点债券与通道"})
        self.assertIn(">重点债券与通道</text>", custom_svg)
        self.assertNotIn(">标的与阵营</text>", custom_svg)

        payload_s = json.dumps(base_spec, ensure_ascii=False)
        md = (
            "示例文档：\n\n"
            "```markdown\n"
            f"<!-- DAILY_VISUAL {payload_s} -->\n"
            "```\n\n"
            f"行内代码 `<!-- DAILY_VISUAL {payload_s} -->` 也跳过。\n\n"
            f"<!-- DAILY_VISUAL {payload_s} -->\n"
        )
        cleaned, charts = visual_widgets.extract_visual_directives(md)
        self.assertEqual(len(charts), 1)
        self.assertIn(f"```markdown\n<!-- DAILY_VISUAL {payload_s} -->\n```", cleaned)
        self.assertIn(f"`<!-- DAILY_VISUAL {payload_s} -->`", cleaned)

    def test_all_four_visual_widgets_zero_svg_collisions_under_stress(self):
        import visual_widgets
        import svg_geometry

        stress_specs = [
            {
                "type": "waterfall",
                "title": "极限八柱含负值与基准重叠压力测试",
                "unit": "亿",
                "bars": [
                    {"label": "初始净流动池", "value": 1200, "kind": "start", "val_label": "+1,200亿", "tag": "期初"},
                    {"label": "财政部发债抽水", "value": 450, "kind": "sub", "tag": "QRA"},
                    {"label": "税收季缴款流出", "value": 900, "kind": "sub", "tag": "税期"},
                    {"label": "隔夜逆回购释放", "value": 260, "kind": "add", "tag": "缓冲"},
                    {"label": "央行公开市场投放", "value": 180, "kind": "add", "tag": "净投放"},
                    {"label": "外部汇市扰动", "value": 340, "kind": "sub", "tag": "利差"},
                    {"label": "期末净剩余", "value": -50, "kind": "total", "val_label": "净缺口50亿", "tag": "汇总"},
                    {"label": "历史警戒基准", "value": 150, "kind": "compare", "val_label": "参考150亿", "tag": "对照"},
                ],
                "benchmark": {"value": 140, "label": "极近红线基准140亿"},
            },
            {
                "type": "bar_compare",
                "title": "正负分化与超长标签压力测试",
                "callout_badge": "正负分化警戒：重点关注溢价磨损",
                "unit": "%",
                "threshold": {"val": 0.0, "label": "零轴与风险分界参考线", "color": "#dc2626"},
                "items": [
                    {"label": "超长名称测试标的跨境纳指溢价率", "value": 12.85, "val_label": "+12.85%溢价", "tag": "严防追高高溢价停牌", "highlight": True},
                    {"label": "中资高息银行股息率差值", "value": -4.60, "val_label": "-4.60%折价", "tag": "显著折价具备安全边际"},
                    {"label": "日本东证跨境工具参考", "value": 2.35, "val_label": "+2.35%", "tag": "轻度溢价需核净值"},
                ],
            },
            {
                "type": "anchor_range",
                "title": "极端现价偏离与超长中英文字段压力测试",
                "items": [
                    {
                        "name": "超长名称芯片龙头股份有限公司",
                        "code": "688981.SH / 00981.HK",
                        "current": 9850.5,
                        "anchor_low": 120.0,
                        "anchor_high": 145.0,
                        "unit": "元/股",
                        "stance": "avoid",
                        "stance_label": "严禁追高",
                        "gap_label": "远超锚顶 +6693% 极度过热",
                        "hint": "严守左侧安全边际等待充分回踩确认",
                    },
                    {
                        "name": "超低价测试标的",
                        "code": "000001",
                        "current": 1.2,
                        "anchor_low": 100.0,
                        "anchor_high": 120.0,
                        "unit": "港元",
                        "stance": "base",
                        "stance_label": "深度破锚",
                        "gap_label": "低于锚底 -98.8%",
                        "hint": "核验基本面是否出现永久性损毁",
                    },
                ],
            },
            {
                "type": "flow_chain",
                "title": "六环超长中文传导链零碰撞压力测试",
                "steps": [
                    {"step": "第一环超长步骤标签", "title": "全球能源供给突发冲击事件", "metric": "布伦特原油突破$95/桶", "desc": "霍尔木兹海峡运力受阻推升再通胀交易与运价", "tone": "red"},
                    {"step": "第二环", "title": "十年期美债收益率陡升", "metric": "US10Y 逼近 5.25%", "desc": "名义与实际利率同步抬升挤压全球长久期资产估值", "tone": "amber"},
                    {"step": "第三环", "title": "美元兑日元逼近干预线", "metric": "USD/JPY 160.5", "desc": "套息交易拥挤度处于极值区间谨防反向平仓冲击", "tone": "purple"},
                    {"step": "第四环", "title": "港股联汇流动收紧", "metric": "总结余 541 亿港元", "desc": "一个月拆息走高直接压制离岸科技与地产弹性", "tone": "blue"},
                    {"step": "第五环", "title": "跨境场内基金溢价飙升", "metric": "高溢价 >8% 停牌", "desc": "场内追买面临溢价回落与限购退市双重磨损风险", "tone": "teal"},
                    {"step": "第六环", "title": "家庭钱包总闸防守纪律", "metric": "黄金红灯新仓 0%", "desc": "优先配置短融债券与国债逆回购严控权益仓位上限", "tone": "green"},
                ],
            },
        ]
        for sp in stress_specs:
            self.assertEqual(visual_widgets.validate_visual_spec(sp), [], sp["type"])
            svg_html = visual_widgets.render_visual_chart(sp)
            issues = svg_geometry.check_svg_text_geometry(svg_html, label=f"stress:{sp['type']}")
            self.assertEqual(issues, [], f"Stress collision in {sp['type']}: {issues}")

    def test_cockpit_no_485_fallback_official_us10y_clamped_widths_and_redlines(self):
        # 1. All live & official fields missing/null -> NEVER falls back to 4.85; renders "—" with 0% width & neutral tone
        empty_eq = {
            "markets": {"a_share": {"equity_cap_pct": 40}},
            "rates_bonds_core": {"us_rates": {"us10y_asia_live_pct": None}},
            "cross_market_linkages": {"crisis_correlation_brake": {}, "rates_fx_chain": {}},
        }
        empty_gold = {"tier_code": "Tier 0", "new_buy_allowed": False, "us10y_live_pct": None}
        html_missing = build_site._render_daily_visual_cockpit("a-share", empty_eq, empty_gold, "")
        self.assertNotIn("4.85", html_missing)
        self.assertIn(">—</strong>", html_missing)
        self.assertIn("width:0%", html_missing)
        self.assertIn("dvc-fill-neutral", html_missing)

        # 2. Live fields null, official gold_snap["us10y_pct"] = 4.94 -> reads 4.94%; usdjpy=135 clamped to width:0% (never negative)
        eq_off = {
            "markets": {"a_share": {"equity_cap_pct": 40}},
            "rates_bonds_core": {"us_rates": {"us10y_asia_live_pct": None}},
            "cross_market_linkages": {
                "crisis_correlation_brake": {"vix_live": None, "vix_close": 21.5, "usdjpy_level": 135.0},
                "rates_fx_chain": {"hkma_agg_bal_hkd_100m": 620.0},
            },
        }
        gold_off = {"tier_code": "Tier 0", "new_buy_allowed": False, "us10y_live_pct": None, "us10y_pct": 4.94}
        html_off = build_site._render_daily_visual_cockpit("a-share", eq_off, gold_off, "")
        self.assertIn("4.94%", html_off)
        self.assertNotIn("4.85", html_off)
        for m_w in re.finditer(r'class="dvc-bar-fill[^"]*"\s+style="width:(-?\d+)%"', html_off):
            w_val = int(m_w.group(1))
            self.assertTrue(0 <= w_val <= 100, f"Unclamped gauge width: {w_val}%")

        # 3. Redline breaches (us10y >= 5.25, vix >= 30, usdjpy >= 160, hkma <= 400) -> all 4 red tone!
        eq_red = {
            "markets": {"a_share": {"equity_cap_pct": 30}},
            "rates_bonds_core": {"us_rates": {"us10y_pct": 5.30}},
            "cross_market_linkages": {
                "crisis_correlation_brake": {"vix_close": 32.5, "usdjpy_level": 161.2},
                "rates_fx_chain": {"hkma_agg_bal_hkd_100m": 390.0},
            },
        }
        html_red = build_site._render_daily_visual_cockpit("a-share", eq_red, gold_off, "")
        self.assertEqual(html_red.count("dvc-fill-red"), 4)

    def test_cockpit_dynamic_gold_gate_count_locked_and_unlocked(self):
        eq_base = {"markets": {"a_share": {"equity_cap_pct": 40}}, "cross_market_linkages": {}}
        gold_locked_2of4 = {
            "tier_code": "Tier 0",
            "new_buy_allowed": False,
            "tier1_passed": 2,
            "tier1_total": 4,
            "tier_label": "红灯停（暂不新买 · 新仓 0%）",
            "tier1_gates": [
                {"name": "第 1 关", "passed": False, "reading": "2.79%"},
                {"name": "第 2 关", "passed": False, "reading": "+81bp"},
                {"name": "第 3 关", "passed": True, "reading": "23.81"},
                {"name": "第 4 关", "passed": True, "reading": "$3,652"},
            ],
        }
        locked_html = build_site._render_daily_visual_cockpit("gold", eq_base, gold_locked_2of4, "")
        self.assertIn("当前红灯 2/4 关，新仓严格 0%", locked_html)
        self.assertNotIn("1/4 关", locked_html)

        gold_unlocked_4of4 = {
            "tier_code": "Tier 1",
            "new_buy_allowed": True,
            "tier1_passed": 4,
            "tier1_total": 4,
            "tier_label": "黄灯试仓（允许首笔）",
            "tier1_gates": [
                {"name": f"第 {i} 关", "passed": True, "reading": "通过"} for i in range(1, 5)
            ],
        }
        unlocked_html = build_site._render_daily_visual_cockpit("gold", eq_base, gold_unlocked_4of4, "")
        self.assertIn("已解锁 4/4 关", unlocked_html)
        self.assertIn("按档位上限控制新仓", unlocked_html)
        self.assertNotIn("当前红灯", unlocked_html)
        self.assertNotIn("新仓严格 0%", unlocked_html)

    def test_cockpit_us_6dim_pts_and_single_card_grid(self):
        eq_base = {"markets": {"us_stock": {"equity_cap_pct": 28, "cash_cap_pct": 62, "gold_cap_pct": 10}}, "cross_market_linkages": {}}
        gold_base = {"tier_code": "Tier 0", "new_buy_allowed": False}

        # US 6-dim table with "X 分" scores renders .dvc-score-row bars & 2-col .dvc-grid (NOT single)
        us_body = (
            "<table><tbody>"
            "<tr><td>1. 宏观利率</td><td>0.5 分</td><td>偏紧</td></tr>"
            "<tr><td>2. 盈利预期</td><td>1.0 分</td><td>稳健</td></tr>"
            "<tr><td>3. 市场广度</td><td>0.5 分</td><td>分化</td></tr>"
            "<tr><td>4. 流动估值</td><td>0.0 分</td><td>偏贵</td></tr>"
            "<tr><td>5. 波动情绪</td><td>1.0 分</td><td>回落</td></tr>"
            "<tr><td>6. 政策地缘</td><td>0.5 分</td><td>谨慎</td></tr>"
            "<tr><td>综合总分</td><td>3.5 分</td><td>防守</td></tr>"
            "</tbody></table>"
        )
        us_html = build_site._render_daily_visual_cockpit("us-stock", eq_base, gold_base, us_body)
        self.assertEqual(us_html.count("dvc-score-row"), 6)
        self.assertNotIn("dvc-grid-single", us_html)

        # Empty body with no 6-dim table emits single-card layout .dvc-grid-single
        single_html = build_site._render_daily_visual_cockpit("us-stock", eq_base, gold_base, "<p>简报正文</p>")
        self.assertIn("dvc-grid-single", single_html)
        self.assertEqual(single_html.count("dvc-score-row"), 0)

    def test_reused_weekend_report_does_not_pollute_dated_friday_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fri_md = tmp_path / "2026-11-27_1800_a_share.md"
            fri_meta = {
                "edition_id": "2026-11-27_1800",
                "edition_type": "main",
                "title": "A 股周五收盘深度研报",
                "subtitle": "周五官收复盘测试",
                "as_of": "2026-11-27 18:00 CST",
            }
            fri_md.write_text(
                "# A 股周五收盘深度研报\n\n周五正文内容。\n\n"
                f"<!-- DAILY_META_JSON {json.dumps(fri_meta, ensure_ascii=False)} -->\n",
                encoding="utf-8",
            )
            fri_item = build_site.DailyItem(
                market="a-share",
                date_str="2026-11-27",
                hhmm="1800",
                rev=1,
                session_key="evening",
                session_label="晚报 18:00",
                slug="a-share-2026-11-27-1800",
                source_path=fri_md,
            )
            # Mirror equity/ into a temp dir with Saturday edition_id="2026-11-28_1130" reusing Friday's report
            real_eq_dir = ROOT / "equity"
            tmp_eq_dir = tmp_path / "equity"
            tmp_state_dir = tmp_eq_dir / "state"
            tmp_state_dir.mkdir(parents=True)
            for child in real_eq_dir.iterdir():
                if child.name == "state":
                    continue
                (tmp_eq_dir / child.name).symlink_to(child)
            for st_child in (real_eq_dir / "state").iterdir():
                if st_child.name in ("market_state.json", "policy_calendar.json"):
                    data = json.loads(st_child.read_text(encoding="utf-8"))
                    data["edition_id"] = "2026-11-28_1130"
                    (tmp_state_dir / st_child.name).write_text(
                        json.dumps(data, ensure_ascii=False), encoding="utf-8"
                    )
                else:
                    (tmp_state_dir / st_child.name).symlink_to(st_child)

            out_dir = tmp_path / "_site"
            with (
                patch.object(build_site, "EQUITY_DIR", tmp_eq_dir),
                patch.object(build_site, "discover_dailies", return_value=([fri_item], {})),
            ):
                build_site.build_site(out_dir)

            latest_html = (out_dir / "daily" / "a-share-latest.html").read_text(encoding="utf-8")
            dated_html = (out_dir / "daily" / "a-share-2026-11-27-1800.html").read_text(encoding="utf-8")
            self.assertIn("daily-visual-cockpit", latest_html)
            self.assertIn('id="sec-market-news"', latest_html)
            self.assertNotIn("daily-visual-cockpit", dated_html)
            self.assertNotIn('id="sec-market-news"', dated_html)

    def test_lint_site_s3_s6_s7_bare_tier_wrapped_svg_gold_crypto_cockpit_and_dfii10(self):
        # 1. Gate S3: bare P0/P1/P2 caught in visible HTML & SVG <text>, while data-priority="P0" & P10 pass
        doc_ok = lint_site.parse_html_file(
            "daily/a-share-latest.html",
            Path("daily/a-share-latest.html"),
            '<!doctype html><html><body><div data-priority="P0">华为 P10 机型与一级关键政策落地</div></body></html>',
        )
        errs_ok: list[str] = []
        lint_site.run_gate_s3(Path("."), [], {"daily/a-share-latest.html": doc_ok}, errs_ok, [])
        self.assertEqual(errs_ok, [])

        doc_bad_p0 = lint_site.parse_html_file(
            "daily/a-share-latest.html",
            Path("daily/a-share-latest.html"),
            "<!doctype html><html><body><p>这是 P0 重磅事件提醒</p></body></html>",
        )
        errs_p0: list[str] = []
        lint_site.run_gate_s3(Path("."), [], {"daily/a-share-latest.html": doc_bad_p0}, errs_p0, [])
        self.assertTrue(any("P0" in e for e in errs_p0), errs_p0)

        doc_svg_p1 = lint_site.parse_html_file(
            "daily/a-share-latest.html",
            Path("daily/a-share-latest.html"),
            '<!doctype html><html><body><svg viewBox="0 0 200 60">'
            '<text x="10" y="20">重点 P</text><text x="10" y="34">1 关注</text></svg></body></html>',
        )
        errs_svg_p1: list[str] = []
        lint_site.run_gate_s3(Path("."), [], {"daily/a-share-latest.html": doc_svg_p1}, errs_svg_p1, [])
        self.assertTrue(any("P1" in e for e in errs_svg_p1), errs_svg_p1)

        # 2. Gate S6: bare 买入黄金 / 配置黄金 in HTML & wrapped SVG <text> caught; 严禁买入黄金 passes
        doc_gold_wrap = lint_site.parse_html_file(
            "daily/a-share-latest.html",
            Path("daily/a-share-latest.html"),
            '<!doctype html><html><body>'
            '<p>严禁买入黄金与配置黄金 518880。</p>'
            '<svg viewBox="0 0 200 60"><text x="20" y="20">逢低买入</text><text x="20" y="34">黄金 518880</text></svg>'
            "</body></html>",
        )
        errs_gw: list[str] = []
        lint_site._check_gold_tier0_mutex(doc_gold_wrap, errs_gw)
        self.assertTrue(any("wrapped SVG text" in e for e in errs_gw), errs_gw)

        doc_gold_bare = lint_site.parse_html_file(
            "daily/a-share-latest.html",
            Path("daily/a-share-latest.html"),
            "<!doctype html><html><body><p>今日配置黄金应对通胀。</p></body></html>",
        )
        errs_gb: list[str] = []
        lint_site._check_gold_tier0_mutex(doc_gold_bare, errs_gb)
        self.assertTrue(any("Gold Tier 0 mutex" in e for e in errs_gb), errs_gb)

        doc_gold_safe = lint_site.parse_html_file(
            "daily/a-share-latest.html",
            Path("daily/a-share-latest.html"),
            "<!doctype html><html><body><p>红灯停期严禁买入黄金，暂不配置黄金 518880。</p></body></html>",
        )
        errs_gs: list[str] = []
        lint_site._check_gold_tier0_mutex(doc_gold_safe, errs_gs)
        self.assertEqual(errs_gs, [])

        # 3. Gate S6: Crypto Doc-42 firewall catches active buy & passes 0% 严禁配仓 thermometer
        doc_cryp_bad = lint_site.parse_html_file(
            "daily/us-stock-latest.html",
            Path("daily/us-stock-latest.html"),
            "<!doctype html><html><body><p>建议买入 BTC 与配置比特币对冲风险。</p></body></html>",
        )
        errs_cb: list[str] = []
        lint_site._check_crypto_firewall(doc_cryp_bad, errs_cb, gate_tag="S6")
        self.assertTrue(any("银发〔2026〕42号" in e for e in errs_cb), errs_cb)

        doc_cryp_ok = lint_site.parse_html_file(
            "daily/us-stock-latest.html",
            Path("daily/us-stock-latest.html"),
            "<!doctype html><html><body><p>BTC 仅作流动性温度计，遵照央行银发〔2026〕42号 0% 严禁配仓比特币。</p></body></html>",
        )
        errs_co: list[str] = []
        lint_site._check_crypto_firewall(doc_cryp_ok, errs_co, gate_tag="S6")
        self.assertEqual(errs_co, [])

        # 4. Gate S6: catches mismatched cockpit 1/4 关 vs snapshot 2/4 关 on daily/gold-latest.html
        stale_gold_page = lint_site.parse_html_file(
            "daily/gold-latest.html",
            Path("daily/gold-latest.html"),
            '<!doctype html><html><body><section class="daily-visual-cockpit">'
            '<div class="dvc-alloc-note">当前红灯 1/4 关，新仓严格 0%</div>'
            "</section></body></html>",
        )
        errs_gc: list[str] = []
        lint_site.run_gate_s6(
            {"daily/gold-latest.html": stale_gold_page},
            {"tier_code": "Tier 0", "new_buy_allowed": False, "tier1_passed": 2, "tier1_total": 4},
            None,
            errs_gc,
            [],
            already_checked_json_gold=True,
        )
        self.assertTrue(any("1/4 关" in e and "2/4 关" in e for e in errs_gc), errs_gc)

        # 5. Gate S7: accepts negative close on rate_DFII10 while rejecting <= 0 on stock/ETF shards
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp)
            kdir = site_dir / "assets" / "klines"
            kdir.mkdir(parents=True)
            (site_dir / "assets" / "kline.js").write_text("/* stub */", encoding="utf-8")
            charts_doc = lint_site.parse_html_file(
                "charts.html",
                site_dir / "charts.html",
                '<!doctype html><html><body><div id="kline-terminal-root"></div>'
                '<div id="kline-symbol-list"></div><div id="kline-main-chart"></div>'
                '<div id="kline-tech-banner"></div><script src="assets/kline.js"></script></body></html>',
            )
            good_bars = [[f"2026-11-{d:02d}", -0.45, -0.40, -0.50, -0.45, 0] for d in range(1, 21)]
            stk_bars_ok = [[f"2026-11-{d:02d}", 10.0, 10.5, 9.8, 10.2, 100] for d in range(1, 21)]
            manifest = {
                "edition_id": "2026-11-28_1130",
                "total_symbols": 2,
                "shards": {"core": "core.json", "stocks_a": "stocks_a.json"},
                "catalog": [
                    {"id": "rate_DFII10", "code": "DFII10", "name": "10Y TIPS实际利率", "shard": "core", "group": "rates_reits"},
                    {"id": "stk_600036", "code": "600036", "name": "招商银行", "shard": "stocks_a", "group": "a_stock"},
                ],
            }
            (kdir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (kdir / "core.json").write_text(
                json.dumps({"series": {"rate_DFII10": {"bars": good_bars}}}), encoding="utf-8"
            )
            (kdir / "stocks_a.json").write_text(
                json.dumps({"series": {"stk_600036": {"bars": stk_bars_ok}}}), encoding="utf-8"
            )
            errs_s7_ok: list[str] = []
            lint_site.run_gate_s7(site_dir, {"charts.html": charts_doc}, errs_s7_ok, [])
            self.assertFalse(any("invalid OHLC invariant" in e for e in errs_s7_ok), errs_s7_ok)

            # Now inject <= 0 close into stock shard -> MUST fail Gate S7!
            stk_bars_bad = list(stk_bars_ok)
            stk_bars_bad[-1] = ["2026-11-20", 10.0, 10.5, 0.0, 0.0, 100]
            (kdir / "stocks_a.json").write_text(
                json.dumps({"series": {"stk_600036": {"bars": stk_bars_bad}}}), encoding="utf-8"
            )
            errs_s7_bad: list[str] = []
            lint_site.run_gate_s7(site_dir, {"charts.html": charts_doc}, errs_s7_bad, [])
            self.assertTrue(any("stk_600036" in e and "invalid OHLC invariant" in e for e in errs_s7_bad), errs_s7_bad)

    def test_visual_widgets_filename_leak_blocked_across_all_linters(self):
        import patch_state_dbs as psd
        sys.path.insert(0, str(ROOT / "equity"))
        sys.path.insert(0, str(ROOT / "gold"))
        import lint_equity as eq_lint
        import pdf_common
        import lint_readability as gold_lint

        sample = "请勿在公开页面泄露 visual_widgets.py 引擎文件名"
        for label, rx in (
            ("lint_site.S3_INTERNAL_ENG_LEAK_RE", lint_site.S3_INTERNAL_ENG_LEAK_RE),
            ("build_site._HARD_INFRA_RE", build_site._HARD_INFRA_RE),
            ("patch_state_dbs.BANNED_INTERNAL_RE", psd.BANNED_INTERNAL_RE),
            ("pdf_common._BANNED_INTERNAL_RE", pdf_common._BANNED_INTERNAL_RE),
            ("gold_lint.SCORECARD_BANNED_RE", gold_lint.SCORECARD_BANNED_RE),
            ("gold_lint._INTERNAL_FILENAME_LEAK_RE", gold_lint._INTERNAL_FILENAME_LEAK_RE),
            ("eq_lint._VISUAL_WIDGETS_LEAK_RE", eq_lint._VISUAL_WIDGETS_LEAK_RE),
        ):
            with self.subTest(regex=label):
                self.assertIsNotNone(rx.search(sample), f"{label} missed visual_widgets.py")

    def test_lint_site_s6_currency_lock_and_full_action_etf_urgent_warning(self):
        # P1-6: HK & US screener prices reject RMB 元 / ¥ while allowing HK$ / 港元 / $ / 美元
        for bad_hk in ("23.30 元", "¥23.30", "人民币 23.30", "$23.30"):
            self.assertIsNotNone(lint_site.S6_HK_FORBID_CURR_RE.search(bad_hk), bad_hk)
        for ok_hk in ("HK$23.30", "23.30 港元"):
            self.assertIsNone(lint_site.S6_HK_FORBID_CURR_RE.search(ok_hk), ok_hk)

        for bad_us in ("52.93 元", "¥52.93", "HK$52.93", "52.93 港元"):
            self.assertIsNotNone(lint_site.S6_US_FORBID_CURR_RE.search(bad_us), bad_us)
        for ok_us in ("$52.93", "52.93 美元"):
            self.assertIsNone(lint_site.S6_US_FORBID_CURR_RE.search(ok_us), ok_us)

        # P2-5: Urgent placement/chase-buy warning beyond first 60 chars of action_etf is still caught on green card
        long_action = (
            "高息底座核心持有标的，长期股息覆盖稳健，基本面自由现金流极其充裕且估值具备历史中枢支撑与低波动优势，"
            "但短期因大股东折价配售放量且筹码尚未充分消化，提示暂勿立即加仓。"
        )
        self.assertGreater(long_action.index("暂勿立即加仓"), 60)
        payload = json.dumps(
            [
                {
                    "market": "hk-stock",
                    "code": "00941.HK",
                    "name": "测试高息股",
                    "price": "HK$75.20",
                    "color": "g",
                    "summary": "高息稳健底座标的。",
                    "dossier": {"action_etf": long_action},
                }
            ],
            ensure_ascii=False,
        )
        scr_doc = lint_site.parse_html_file(
            "screener.html",
            Path("screener.html"),
            f'<!doctype html><html><body><script id="screener-data" type="application/json">{payload}</script></body></html>',
        )
        errs_sc: list[str] = []
        lint_site._validate_screener_json(scr_doc, {"hk-stock": 1}, errs_sc, gold_new_buy_blocked=False)
        self.assertTrue(any("badge contradiction" in e and "暂勿立即加仓" in e for e in errs_sc), errs_sc)


if __name__ == "__main__":
    unittest.main()
