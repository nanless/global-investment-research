"""Unit tests for editorial depth, quantitative math, SVG color/geometry, and heading gates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "equity"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_a_share_pdf as a_pdf
import lint_equity as eq_lint
import pdf_common
from svg_geometry import check_svg_text_geometry

if str(ROOT / "gold") not in sys.path:
    sys.path.insert(0, str(ROOT / "gold"))
import lint_readability as gold_lint

gold_daily = gold_lint._load_gold_module("build_daily", ROOT / "gold" / "build_daily.py")
gold_master = gold_lint._load_gold_module("build_report", ROOT / "gold" / "build_report.py")


class ChartA2AndGoldHtmlTests(unittest.TestCase):
    def test_chart_a2_semantic_color_normalization_and_defaults(self):
        # DEFAULT_A_INDICES must align with A-share semantic colors (#c2410c up, #0f766e down)
        for name, pct, col in a_pdf.DEFAULT_A_INDICES:
            if pct > 0:
                self.assertEqual(col.lower(), "#c2410c", f"{name} positive default should be #c2410c")
            elif pct < 0:
                self.assertEqual(col.lower(), "#0f766e", f"{name} negative default should be #0f766e")

        meta = {
            "chart_live": {
                "as_of_full": "2026-11-27 07:55 北京时间",
                "a2": {
                    "title": "语义配色测试",
                    "sub": "左：宽基涨跌 ｜ 右：期货",
                    "indices": [
                        ["中证红利", 1.04, "#0f766e"],      # teal on positive -> forced #c2410c
                        ["上证50", 0.07, "#0072b2"],        # blue on positive -> forced #c2410c
                        ["平盘指数", 0.0, "#0f766e"],       # zero -> #64748b
                        ["科创50", -1.36, "#c2410c"],       # red on negative -> forced #0f766e
                        ["中证500", -0.46, "#dc2626"],      # crimson on negative -> forced #0f766e
                    ],
                    "futures": [
                        ["超大盘期货 (上证50 · IH)", 14.5, "收 2,716（基差 -37.7）", "测试", "#0f766e", "#f0fdfa"],
                    ],
                },
            }
        }
        svg = a_pdf.svg_chart_a2_split_and_futures(meta)
        self.assertIn('fill="#c2410c" font-weight="700">▲+1.04%</text>', svg)
        self.assertIn('fill="#c2410c" font-weight="700">▲+0.07%</text>', svg)
        self.assertIn('fill="#64748b" font-weight="700">0.00%</text>', svg)
        self.assertIn('fill="#0f766e" font-weight="700">▼-1.36%</text>', svg)
        self.assertIn('fill="#0f766e" font-weight="700">▼-0.46%</text>', svg)
        self.assertEqual(check_svg_text_geometry(svg, label="CHART_A2_TEST"), [])

    def test_gold_heading_hierarchy_single_h1(self):
        cover_html = gold_daily.build_cover_html("2026年11月27日 黄金早报", {"kpis": []})
        self.assertIn('<h1 class="cover-title">', cover_html)
        self.assertNotIn('<div class="cover-title">', cover_html)

        md = "# 2026年11月27日 黄金早报\n\n# 第一部分｜速读\n\n正文。\n\n# 第二部分｜深读\n\n正文。\n"
        _, _, body_html, _ = gold_daily.parse_markdown_to_html(md)
        self.assertIn('<h2 class="vol-header">第一部分｜速读</h2>', body_html)
        self.assertIn('<h2 class="vol-header">第二部分｜深读</h2>', body_html)
        self.assertNotIn("<h1", body_html)

        combined = cover_html + "\n" + body_html
        self.assertEqual(len(re.findall(r"<h1\b", combined)), 1)

        master_snap = json.loads((ROOT / "gold" / "master_snapshot.json").read_text(encoding="utf-8"))
        with patch.object(gold_master, "SNAP", master_snap):
            master_cover = gold_master.build_cover_html()
        self.assertIn('<h1 class="cover-title">', master_cover)
        self.assertNotIn('<div class="cover-title">', master_cover)

    def test_gold_chart1_opaque_ref_pills_and_chart3_drawdown_micro_labels(self):
        tl_cfg = {
            "title": "图 1 测试",
            "y_min": 3405,
            "y_max": 3635,
            "y_ticks": [3420, 3470, 3520, 3570, 3620],
            "ref_lines": [
                {"val": 3590, "label": "今晚黑五第4关 $3,590", "color": "#0f766e", "align": "start", "dy": -6},
                {"val": 3526, "label": "主报告-3%警戒 $3,526", "color": "#b91c1c", "align": "start", "dy": 12},
            ],
            "points": [
                {"time": "25日低", "val": 3427, "val_label": "$3,427"},
                {"time": "25日收", "val": 3589, "val_label": "$3,589"},
                {"time": "26亚高", "val": 3607, "val_label": "$3,607"},
                {"time": "07:55", "val": 3567, "val_label": "$3,567"},
            ],
        }
        svg1 = gold_daily.render_chart_timeline(tl_cfg)
        self.assertIn('fill="#ffffff" fill-opacity="0.96"', svg1)
        self.assertEqual(check_svg_text_geometry(svg1, label="GOLD_CHART_1"), [])

        sw_cfg = {
            "title": "图 3 测试",
            "status_line": "当前判定：红灯停（1/4 关）",
            "status_color": "#dc2626",
            "gauges": [
                {"label": "真实利息压迫水位", "value_text": "2.73%（98% 高位）", "pct": 98, "threshold_pct": 95, "color": "#b91c1c"},
                {"label": "金价较年初大顶回调进度（满格按 -45.5%）", "value_text": "已跌 35.9%（进度 79%）", "pct": 79, "threshold_pct": 65, "color": "#b45309"},
            ],
            "checks": [
                {"id": "real_yield", "name": "第 1 关", "passed": False, "line1": "2.73%", "line2": "≤2.72%"},
                {"id": "rate_spread", "name": "第 2 关", "passed": False, "line1": "+73bp", "line2": "≤+55bp"},
                {"id": "vix", "name": "第 3 关", "passed": True, "line1": "28.29", "line2": "<30"},
                {"id": "ny_close", "name": "第 4 关", "passed": False, "line1": "$3,589", "line2": ">$3,678"},
            ],
        }
        svg3 = gold_daily.render_chart_switch(sw_cfg)
        for token in ("-20%", "-30%", "-45.5%"):
            self.assertIn(token, svg3)
        self.assertEqual(check_svg_text_geometry(svg3, label="GOLD_CHART_3"), [])


class ActionableDiagnosticsAndRetractedGuardTests(unittest.TestCase):
    def test_pdf_common_actionable_line_numbers_and_snippets(self):
        long_p = "这是一段用于测试超过一百八十字的长段落内容" * 10
        md = (
            "# 标题\n\n"
            f"{long_p}\n\n"
            "| A | B | C | D | E | F |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| 1 | 2 | 3 | 4 | 5 | 6 |\n\n"
            "**这里是极密集的加粗第一行测试文本用于拉高全篇加粗密度超过阈值上限**\n"
            "**这里是极密集的加粗第二行用于确保加粗占比稳稳超过十三点五的红线**\n"
        )
        errs, warns = pdf_common.lint_markdown_report(md, "2026-11-27_0730_a_share.md", is_flagship=False)
        self.assertEqual(errs, [])
        joined = "\n".join(warns)
        self.assertIn("[L3:", joined)
        self.assertIn('字 "这是一段用于测试', joined)
        self.assertIn("[L5:6列]", joined)
        self.assertRegex(joined, r"\[L9:\d+字\]")

    def test_159513_ephemeral_guard_removed_while_permanent_guards_remain(self):
        self.assertEqual(
            eq_lint._check_retracted_facts("test.md", "大成纳指 159513 今日 09:30–10:30 停牌 1 小时。"),
            [],
        )
        # Permanent retracted guards still catch known errors
        self.assertTrue(eq_lint._check_retracted_facts("test.md", "工银 008143 满 7 天免赎回。"))
        self.assertTrue(eq_lint._check_retracted_facts("test.md", "海波转债 123080 将于 12/02 到期兑付。"))

    def test_focus_table_col1_extraction_catches_row_with_secondary_stock_in_col3(self):
        fake_dossiers = {
            "dossiers": {
                "hk-stock:00883.HK": {
                    "updated_at": "2026-11-27",
                    "baseline_note": "11/26 官收 21.32 港元；PE 6.2x / AH 溢价 +69.2%。",
                    "valuation_anchor": "H 股 PE-TTM 6.2x，股息率 7.2%。",
                    "action_etf": "回踩 19.5–20.2 港元分批低吸（备 00857.HK）。",
                },
                "hk-stock:00857.HK": {
                    "updated_at": "2026-11-26",
                    "baseline_note": "11/26 官收 6.10 港元；PE 7.5x。",
                    "valuation_anchor": "PE-TTM 7.5x。",
                    "action_etf": "稳健底仓。",
                },
            }
        }
        with TemporaryDirectory() as tmp:
            dd_path = Path(tmp) / "deep_dossiers.json"
            dd_path.write_text(json.dumps(fake_dossiers, ensure_ascii=False), encoding="utf-8")
            with patch.object(eq_lint, "DEEP_DOSSIERS_PATH", dd_path):
                # Row mentions 00857.HK in col 3 -> must STILL check 00883.HK from col 1!
                bad_table = (
                    "| 标的 | 估值 | 动作 |\n"
                    "| :--- | :--- | :--- |\n"
                    "| 🟢 海油 `00883.HK`<br>收 29.99（+1.0%） | 市盈率 9.5 倍 | 回踩 12.0–13.0 港元（备 `00857.HK`） |\n"
                )
                errs = eq_lint._check_daily_focus_table_vs_dossiers(
                    bad_table, "2026-11-27_0730_hk_stock.md", "hk_stock", edition_date="2026-11-27"
                )
                joined = "\n".join(errs)
                self.assertIn("市盈率 9.5 倍", joined)
                self.assertIn("收盘价 29.99", joined)
                self.assertIn("买入/观察锚区间 12–13", joined)


class DeterministicMathEditorialAndTenseGateTests(unittest.TestCase):
    def test_shfe_night_close_guard_equity_and_gold(self):
        bad_copper = "国内 02:30 夜盘沪铝反弹，沪铜收 89,270 元/吨。"
        good_copper = "国内 02:30 沪金夜盘收 766 元/克，01:00 沪铜夜盘收 89,270 元/吨。"
        good_copper_first = "国内夜盘分 01:00 沪铜（对官结）与 02:30 金银（沪金对日收）。"
        good_ferrous = "国内 02:30 沪金夜盘收 766 元/克，23:00 螺纹钢夜盘收 3,200 元/吨。"

        self.assertTrue(eq_lint._check_shfe_night_close("a.md", bad_copper))
        self.assertEqual(eq_lint._check_shfe_night_close("a.md", good_copper), [])
        self.assertEqual(eq_lint._check_shfe_night_close("a.md", good_copper_first), [])
        self.assertEqual(eq_lint._check_shfe_night_close("a.md", good_ferrous), [])

        self.assertTrue(gold_lint._check_shfe_night_close("g.md", bad_copper))
        self.assertEqual(gold_lint._check_shfe_night_close("g.md", good_copper), [])
        self.assertEqual(gold_lint._check_shfe_night_close("g.md", good_copper_first), [])
        self.assertEqual(gold_lint._check_shfe_night_close("g.md", good_ferrous), [])

    def test_10pt_scenario_sum_and_dot_parity_equity_and_gold(self):
        bad_sum = "- 四情景拆分（合计 10 点）：震荡占 5 点（●●●●●○○○○○）；修复占 3 点；回踩占 2 点；突破占 1 点。"
        bad_dots = "- 三情景拆分（合计 10 点）：震荡占 4 点（●●●●●○○○○○）；上行占 3 点；下行占 3 点。"
        good_line = "- 四情景拆分（合计 10 点）：震荡占 5 点（●●●●●○○○○○）；修复占 2 点；回踩占 2 点；突破仅占 1 点。"

        self.assertTrue(eq_lint._check_scenario_10pt_and_dots("a.md", bad_sum))
        self.assertTrue(eq_lint._check_scenario_10pt_and_dots("a.md", bad_dots))
        self.assertEqual(eq_lint._check_scenario_10pt_and_dots("a.md", good_line), [])

        self.assertTrue(gold_lint._check_scenario_10pt_and_dots("g.md", bad_sum))
        self.assertTrue(gold_lint._check_scenario_10pt_and_dots("g.md", bad_dots))
        self.assertEqual(gold_lint._check_scenario_10pt_and_dots("g.md", good_line), [])

    def test_as_of_year_float_drift_caught(self):
        path = Path("2026-11-27_0730_a_share.md")
        meta = {
            "edition_id": "2026-11-27_0730",
            "edition_type": "main",
            "tag": "早刊",
            "title": "测试标题",
            "benchmark_time": "2026-11-27 07:55",
            "methodology": "测试",
            "page_footer": "页脚",
            "footer_note": "注记",
            "kpis": [{"label": "a", "val": "1", "sub": "b"} for _ in range(4)],
            "chart_live": {
                "as_of_full": "2026-11-27 07:55 北京时间",
                "as_of_year_float": 2026.915,  # true value for 2026-11-27 is ~2026.9055 (drift ~0.0095 > 0.004)
            },
        }
        errs = eq_lint.check_daily_contract(path, meta, "# 标题\n正文")
        self.assertTrue(any("as_of_year_float" in e for e in errs), errs)

        meta["chart_live"]["as_of_year_float"] = 2026.905
        errs_ok = eq_lint.check_daily_contract(path, meta, "# 标题\n正文")
        self.assertFalse(any("as_of_year_float" in e for e in errs_ok), errs_ok)

    def test_tense_drift_and_countdown_equity_and_gold(self):
        self.assertTrue(eq_lint._check_tense_drift("a.md", "明日 11/27 迎来期指结算。", "2026-11-27"))
        self.assertTrue(eq_lint._check_tense_drift("a.md", "今日（11/26）感恩节休市。", "2026-11-27"))
        self.assertTrue(eq_lint._check_tense_drift("a.md", "昨日 11/25 数据披露。", "2026-11-27"))
        self.assertEqual(eq_lint._check_tense_drift("a.md", "今日 11/27 迎来期指结算，明日 11/28 生效。", "2026-11-27"), [])

        self.assertTrue(gold_lint._check_tense_drift("g.md", "明日 11/27 盘前关注油价。", "2026-11-27"))
        self.assertEqual(gold_lint._check_tense_drift("g.md", "今日 11/27 盘前关注油价。", "2026-11-27"), [])

        self.assertTrue(eq_lint._check_year_end_countdown("a.md", "距 2026-12-31 仅剩 35 天。", "2026-11-27"))
        self.assertEqual(eq_lint._check_year_end_countdown("a.md", "距 2026-12-31 仅剩 34 天。", "2026-11-27"), [])

    def test_phase_d_editorial_gates_r8(self):
        long_quote = "> " + ("开篇导语测试" * 42) + "\n"
        body = (
            "# 标题：核销成绩单出炉\n\n"
            f"{long_quote}\n---\n\n"
            "总分 1.0/6 分 = 盈利 1.0 + 其余均 0。\n\n"
            + ("这是一段完全没有加粗的普通正文内容用于触发加粗密度下限检查。" * 45)
        )
        errs, warns = eq_lint._check_phase_d_editorial(body, "2026-11-27_0730_a_share.md", {"edition_type": "main", "title": "旧缺口清零"})
        err_str = "\n".join(errs)
        warn_str = "\n".join(warns)
        self.assertIn("其余均 0", err_str)
        self.assertIn("内部审计术语", err_str)
        self.assertIn("开篇导语引用块偏长", warn_str)
        self.assertIn("主刊加粗文字占比过低", warn_str)

    def test_market_state_math_checks(self):
        base = {
            "markets": {
                "a_share": {"pe_ttm": 13.24, "pe_fwd": 12.30, "cgb10y_pct": 1.5865, "erp_ttm_pct": 5.97, "erp_fwd_pct": 6.54},
                "hk_stock": {
                    "pe_ttm": 10.30, "pe_fwd": 9.70,
                    "erp_usd_anchor_ttm_pct": 4.86, "erp_cny_anchor_ttm_pct": 8.12,
                    "erp_usd_anchor_fwd_pct": 5.46, "erp_cny_anchor_fwd_pct": 8.72,
                },
                "us_stock": {
                    "pe_ttm": 24.24, "pe_fwd": 17.26, "us10y_pct": 4.85,
                    "erp_ttm_pct": -0.72, "erp_fwd_pct": 0.94,
                    "equity_cap_pct": 28, "cash_tbill_pct": 62, "gold_hold_pct": 10,
                },
            },
            "cross_market_linkages": {
                "rates_fx_chain": {
                    "cgb10y_pct": 1.5865, "us10y_pct": 4.85, "cn_us_10y_spread_bp": -326,
                    "sofr_pct": 3.94, "hibor_1m_pct": 2.935, "sofr_hibor1m_carry_bp": 100.5,
                },
                "erp_ruler": {
                    "csi300_erp_ttm_pct": 5.97, "csi300_erp_fwd_pct": 6.54,
                    "hsi_erp_usd_ttm_pct": 4.86, "hsi_erp_cny_ttm_pct": 8.12,
                    "hsi_erp_usd_fwd_pct": 5.46, "hsi_erp_cny_fwd_pct": 8.72,
                    "sp500_erp_ttm_pct": -0.72, "sp500_erp_fwd_pct": 0.94,
                },
                "ah_premium_radar": {
                    "pe_physics_locks": [
                        {"name": "招商银行", "a_pe_ttm": 7.3, "h_pe_ttm": 7.7, "ah_premium_pct": -5.2},
                    ]
                },
            },
        }
        self.assertEqual(eq_lint._check_market_state_math(base), [])

        bad = deepcopy(base)
        bad["markets"]["a_share"]["erp_ttm_pct"] = 6.20
        bad["cross_market_linkages"]["rates_fx_chain"]["cn_us_10y_spread_bp"] = -310
        bad["cross_market_linkages"]["rates_fx_chain"]["sofr_hibor1m_carry_bp"] = 90.0
        bad["markets"]["us_stock"]["gold_hold_pct"] = 12
        bad["cross_market_linkages"]["ah_premium_radar"]["pe_physics_locks"][0]["ah_premium_pct"] = 10.0
        errs = "\n".join(eq_lint._check_market_state_math(bad))
        self.assertIn("a_share.erp_ttm_pct", errs)
        self.assertIn("cn_us_10y_spread_bp", errs)
        self.assertIn("sofr_hibor1m_carry_bp", errs)
        self.assertIn("us_stock 配置闭环合计", errs)
        self.assertIn("pe_physics_locks", errs)

    def test_gold_snapshot_math_and_wallet_grams(self):
        # Wallet anchor gram check: 100000 / 766 = 130.548 -> 130.5 passes, 131.0 fails
        # Partial tranche (e.g. 3 万元 / 37.5 克) must NEVER falsely trigger!
        good_wallet = (
            "## 三、10 万元与 1 万元双刻度钱包账\n"
            "以 766 元/克为起跑线，若首笔试仓 3 万元（持约 39.2 克，按 800 元/克持约 37.5 克）：\n"
            "| 未来情景 | 10 万元钱包盈亏 | 1 万元钱包盈亏 |\n"
            "| :--- | :---: | :---: |\n"
            "| 起跑线 | 0 元（持约 130.5 克） | 0 元（持约 13.1 克） |\n"
        )
        bad_wallet = (
            "## 三、10 万元钱包账\n"
            "以 766 元/克为起跑线：\n"
            "| 未来情景 | 10 万元钱包盈亏 |\n"
            "| :--- | :---: |\n"
            "| 起跑线 | 0 元（持约 131.0 克） |\n"
        )
        prose_good = "## 三、钱包账\n锚定 800 元/克：10 万元持约 125.0 克，1 万元持约 12.5 克，首批 3 万元持约 37.5 克。\n"
        prose_bad = "## 三、钱包账\n锚定 800 元/克：10 万元持约 126.0 克。\n"
        self.assertEqual(gold_lint._check_wallet_anchor_grams(good_wallet), [])
        self.assertTrue(gold_lint._check_wallet_anchor_grams(bad_wallet))
        self.assertEqual(gold_lint._check_wallet_anchor_grams(prose_good), [])
        self.assertTrue(gold_lint._check_wallet_anchor_grams(prose_bad))

        # Gold snapshot fair_value_rmb & math checks (incl. widened 0.08 TIPS tolerance)
        snap = json.loads((ROOT / "gold" / "data_snapshot.json").read_text(encoding="utf-8"))
        snap["fair_value_usd"] = 3790
        snap["usd_cny_1630"] = 6.66
        snap["fair_value_rmb"] = 811  # round(3790 * 6.66 / 31.1034768) == 812 -> diff 1.0 > 0.6
        with TemporaryDirectory() as tmp:
            sp = Path(tmp) / "master_snapshot.json"
            sp.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            errs, warns = [], []
            gold_lint.validate_snapshot_file(sp, errs, warns)
            self.assertTrue(any("fair_value_rmb" in e for e in errs), errs)

            # Intraday volatile TIPS lag of 0.05 (<= 0.08) passes cleanly
            snap["fair_value_rmb"] = 812
            snap["us10y_pct"] = 4.85
            snap["t10yie_fred_pct"] = 2.12
            snap["dfii10_live_pct"] = 2.78  # 2.78 + 2.12 = 4.90 -> diff 0.05 <= 0.08
            sp.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            errs_tol, warns_tol = [], []
            gold_lint.validate_snapshot_file(sp, errs_tol, warns_tol)
            self.assertFalse(any("利率恒等式冲突" in e for e in errs_tol), errs_tol)

            snap["dfii10_live_pct"] = 2.90  # 2.90 + 2.12 = 5.02 -> diff 0.17 > 0.08
            snap["gdx_close_usd"] = 73.89
            snap["gld_close_usd"] = 327.45
            snap["gdx_gld_ratio"] = 0.2500  # != 73.89 / 327.45
            snap["spot_gold_ny_close_usd"] = 3588.78
            snap["spot_gold_live_usd"] = 3567.32
            snap["spot_gold_live_change_pct"] = -1.50  # != ((3567.32/3588.78)-1)*100
            sp.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            errs2, warns2 = [], []
            gold_lint.validate_snapshot_file(sp, errs2, warns2)
            j2 = "\n".join(errs2)
            self.assertNotIn("fair_value_rmb", j2)
            self.assertIn("利率恒等式冲突", j2)
            self.assertIn("gdx_gld_ratio", j2)
            self.assertIn("spot_gold_live_change_pct", j2)

    def test_etf_iopv_and_high_risk_restore_guards(self):
        fake_etfs = {
            "edition_id": "2026-11-27_0730",
            "total_etfs": 1,
            "counts_by_market": {"us-stock": 1},
            "counts_by_channel": {"境内QDII": 1},
            "etfs": [
                {
                    "code": "513500",
                    "name": "博时标普500ETF",
                    "market": "us-stock",
                    "channel": "境内QDII",
                    "fee_total_pct": "0.60%",
                    "fee_num": 0.60,
                    "premium_status": "high_risk",
                    "premium_note": "溢价+9%，11/27恢复申赎，买前核对实时IOPV。",
                    "thesis_deep": "标普通道",
                    "risk_boundary": "溢价>3%禁追",
                    "action_role": "高溢价警示",
                }
            ],
        }
        fake_state = {
            "edition_id": "2026-11-27_0730",
            "markets": {"a_share": {"stock_pool_count": 1}, "hk_stock": {"stock_pool_count": 1}, "us_stock": {"stock_pool_count": 1}},
        }
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            eu_p = t / "etf_universe.json"
            eu_p.write_text(json.dumps(fake_etfs, ensure_ascii=False), encoding="utf-8")
            with patch.multiple(
                eq_lint,
                MULTI_ASSET_PATH=t / "missing_ma.json",
                ETF_UNIVERSE_PATH=eu_p,
                DEEP_DOSSIERS_PATH=t / "missing_dd.json",
            ):
                errs = "\n".join(eq_lint._check_ssot_databases(fake_state))
                self.assertIn("裸 IOPV", errs)
                self.assertIn("恢复申赎", errs)
                self.assertIn("Gate S4 失败", errs)

                fake_etfs["etfs"][0]["action_role"] = "高危回避"
                fake_etfs["etfs"][0]["premium_note"] = "溢价+9%，11/27仅恢复赎回，买前核对盘中净值（IOPV）。"
                eu_p.write_text(json.dumps(fake_etfs, ensure_ascii=False), encoding="utf-8")
                errs_ok = "\n".join(eq_lint._check_ssot_databases(fake_state))
                self.assertNotIn("裸 IOPV", errs_ok)
                self.assertNotIn("恢复申赎", errs_ok)
                self.assertNotIn("Gate S4 失败", errs_ok)

    def test_scorecard_past_due_detection_equity_and_gold(self):
        eq_sc = (
            "## 一、台账\n\n"
            "| 锁定 | 市场 | 判断 | 验真节点 | 结果 | 复盘 |\n"
            "| :--- | :---: | :--- | :--- | :---: | :--- |\n"
            "| 2026-11-26 | A 股 | 过期测试 | 2026-11-26 18:00 | ⏳ 待验真 | 待补 |\n"
        )
        errs_eq = eq_lint._reconcile_equity_scorecard(eq_sc, as_of_dt=datetime(2026, 11, 27, 7, 55))
        self.assertTrue(any("逾期未结案" in e for e in errs_eq), errs_eq)

        gold_sc = (
            "## 三、表二\n\n"
            "| 锁定 | 判断 | 预定验真节点 | 状态 | 重点 |\n"
            "| :--- | :--- | :---: | :---: | :--- |\n"
            "| 2026-11-26 | 过期测试 | 2026-11-26 18:00<br>（晚报） | ⏳ 持续追踪 | 复核 |\n"
        )
        errs_g = gold_lint._check_gold_scorecard_past_due(gold_sc, datetime(2026, 11, 27, 7, 55))
        self.assertTrue(any("逾期未结案" in e for e in errs_g), errs_g)

    def test_dossiers_ah_benchmark_and_dividend_drift(self):
        state = {
            "cross_market_linkages": {
                "ah_premium_radar": {
                    "benchmarks": [
                        {"name": "工商银行", "a": "601398", "h": "01398.HK", "ah_premium_pct": 37.6},
                        {"name": "招商银行", "a": "600036", "h": "03968.HK", "ah_premium_pct": -13.0},
                    ]
                }
            }
        }
        dossiers = {
            "a-share:601398": {
                "baseline_note": "PE 8.5x / 当前股息率 3.5% / AH 溢价 +39.0%。",
                "valuation_anchor": "过去五年历史中枢 AH 溢价 +25.0%，当前 AH 溢价 +38.0%。",
                "shareholder_flow": "A 股股息率 3.9%，中期股息率 1.9%，原股息率 4.5%。",
            },
            "a-share:600036": {
                "baseline_note": "A折H 13%，当前股息率 5.2%。",
                "valuation_anchor": "AH 倒挂 13%，历史均值 AH 溢价 +8.0%；特别股息率 1.0%。",
                "shareholder_flow": "AH 折价 13%，此前股息率 4.1%，半年股息率 2.5%。",
                "financials": "全年股息率 5.2%。",
            },
        }
        errs = "\n".join(eq_lint._check_dossiers_ah_and_dividends(dossiers, state))
        self.assertIn("a-share:601398", errs)
        self.assertIn("AH 溢价", errs)
        self.assertIn("A 股内部股息率口径漂移", errs)
        self.assertNotIn("a-share:600036", errs)
        self.assertNotIn("+25.0%", errs)


class RolloverContrastAndGeometryRegressionTests(unittest.TestCase):
    def test_dec1_and_jan_rollover_etf_sibling_date_and_dedup_and_fee_strip(self):
        fake_state = {
            "edition_id": "2026-12-01_0730",
            "markets": {"a_share": {"stock_pool_count": 1}, "hk_stock": {"stock_pool_count": 1}, "us_stock": {"stock_pool_count": 1}},
        }
        fake_etfs = {
            "edition_id": "2026-12-01_0730",
            "total_etfs": 3,
            "counts_by_market": {"a-share": 1, "hk-stock": 2},
            "counts_by_channel": {"境内场内": 1, "离岸港交所": 2},
            "etfs": [
                {
                    "code": "511380",
                    "name": "博时可转债ETF",
                    "market": "a-share",
                    "channel": "境内场内",
                    "fee_total_pct": "0.20%",
                    "fee_num": 0.20,
                    "premium_status": "normal",
                    "premium_note": "12/01 收盘折价 -0.05%",
                    "yield_or_pe": "11/30 到期收益率 1.2%",
                    "thesis_deep": "全市场可转债代表",
                    "risk_boundary": "注意强赎与信用波动",
                    "action_role": "防御观察",
                },
                {
                    "code": "02840.HK",
                    "name": "SPDR金ETF",
                    "market": "hk-stock",
                    "channel": "离岸港交所",
                    "fee_total_pct": "0.40%",
                    "fee_num": 0.40,
                    "premium_status": "normal",
                    "premium_note": "01/02 收盘平价",
                    "yield_or_pe": "12/31 跟踪现货金",
                    "thesis_deep": "港交所黄金标的",
                    "risk_boundary": "受美遗产税规则约束",
                    "action_role": "红灯观望",
                },
                {
                    "code": "2840",
                    "name": "重复代码测试ETF",
                    "market": "hk-stock",
                    "channel": "离岸港交所",
                    "fee_total_pct": "0.40%",
                    "fee_num": 0.40,
                    "premium_status": "normal",
                    "premium_note": "11/30 收盘平价",
                    "yield_or_pe": "12/01 已同步",
                    "thesis_deep": "测试重复归一化代码",
                    "risk_boundary": "无",
                    "action_role": "观察",
                },
            ],
        }
        fake_ma = {
            "edition_id": "2026-12-01_0730",
            "channels": [
                {
                    "id": cid,
                    "name": cid,
                    "key_metrics": [{"label": "指标", "value": "1%"}],
                    "products": [
                        {
                            "code": "511380" if cid == "convertible_bonds" else f"P{i}",
                            "name": "可转债ETF" if cid == "convertible_bonds" else f"产品{i}",
                            "metric": "流动充裕",
                            "fee": "申购费 0.30%（1折 0.03%）｜年费 0.20%/年｜赎回费 0.50%" if cid == "convertible_bonds" else "0.10%/年",
                            "note": "场内工具",
                        }
                    ],
                    "rules_and_redlines": ["严守仓位纪律"],
                }
                for i, cid in enumerate(eq_lint._SYNTHETIC_LEGACY_MULTI_ASSET_CHANNELS)
            ],
        }
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            ma_p = t / "ma.json"
            eu_p = t / "eu.json"
            ma_p.write_text(json.dumps(fake_ma, ensure_ascii=False), encoding="utf-8")
            eu_p.write_text(json.dumps(fake_etfs, ensure_ascii=False), encoding="utf-8")
            with patch.multiple(
                eq_lint,
                MULTI_ASSET_PATH=ma_p,
                ETF_UNIVERSE_PATH=eu_p,
                DEEP_DOSSIERS_PATH=t / "missing_dd.json",
            ):
                errs = "\n".join(eq_lint._check_ssot_databases(fake_state))
                self.assertIn("premium_note 已更新至 12/1，但 yield_or_pe 仍停留 11/30", errs)
                self.assertIn("premium_note 已更新至 1/2，但 yield_or_pe 仍停留 12/31", errs)
                self.assertNotIn("2840) 字段日期未同步", errs)
                self.assertIn("存在重复代码 02840", errs)
                self.assertNotIn("费率", errs)

    def test_shfe_0230_before_qualified_copper_and_expanded_metals(self):
        good_after = "上期所夜盘金银 02:30 收盘；沪铜（01:00 收盘）上涨，热卷（23:00 收盘）微跌。"
        bad_tin = "国内 02:30 夜盘沪锡反弹 +1.2%。"
        bad_al = "国内 02:30 夜盘 al2701 小幅收涨。"
        bad_rb = "国内 02:30 夜盘 rb2701 回落。"
        safe_english = "02:30 金银夜盘收盘，annual2026 统计口径不变。"

        for checker in (eq_lint._check_shfe_night_close, gold_lint._check_shfe_night_close):
            self.assertEqual(checker("t.md", good_after), [])
            self.assertTrue(checker("t.md", bad_tin))
            self.assertTrue(checker("t.md", bad_al))
            self.assertTrue(checker("t.md", bad_rb))
            self.assertEqual(checker("t.md", safe_english), [])

    def test_multiline_and_delta_scenario_weights_equity_and_gold(self):
        delta_line = "- 情景权重调整：基准震荡由 4/10 调至占 5 点（较上期原占 4 点上调 1 点）。"
        good_multi = (
            "### 未来两周三情景推演（合计 10 点）\n"
            "- **基准震荡**：占 5 点（●●●●●○○○○○，较上期原占 4 点上调）\n"
            "- **向上修复**：占 3 点（●●●○○○○○○○）\n"
            "- **向下回踩**：占 2 点（●●○○○○○○○○）\n"
        )
        bad_multi_bullets = (
            "### 未来两周三情景推演\n"
            "- 震荡（5/10）：区间拉锯\n"
            "- 修复（3/10）：反弹承压\n"
            "- 回踩（1/10）：深挖黄金坑\n"
        )
        bad_multi_table = (
            "### 四情景路径\n"
            "| 情景 | 权重 | 区间 |\n"
            "| :--- | :---: | :--- |\n"
            "| 情景一 | 占 5 点 | 3500 |\n"
            "| 情景二 | 占 3 点 | 3600 |\n"
            "| 情景三 | 占 3 点 | 3400 |\n"
        )
        non_scenario = (
            "### 财报打分清单\n"
            "- 盈利质量（8/10）：现金流充沛\n"
            "- 护城河（7/10）：龙头稳固\n"
        )

        for checker in (eq_lint._check_scenario_10pt_and_dots, gold_lint._check_scenario_10pt_and_dots):
            self.assertEqual(checker("t.md", delta_line), [])
            self.assertEqual(checker("t.md", good_multi), [])
            self.assertTrue(checker("t.md", bad_multi_bullets))
            self.assertTrue(checker("t.md", bad_multi_table))
            self.assertEqual(checker("t.md", non_scenario), [])

    def test_iopv_gloss_parity_and_internal_leak_sync(self):
        for gloss in ("参考净值（IOPV）", "实时净值（IOPV）", "盘中净值（IOPV）"):
            _, warns = pdf_common.lint_markdown_report(f"# 标题\n\n买前核对{gloss}。\n", "2026-11-27_0730_a_share.md")
            self.assertFalse(any("IOPV" in w for w in warns), (gloss, warns))
        _, warns_bare = pdf_common.lint_markdown_report("# 标题\n\n买前核对 IOPV 折溢价。\n", "2026-11-27_0730_a_share.md")
        self.assertTrue(any("IOPV" in w for w in warns_bare), warns_bare)

        for leak_tok in ("svg_geometry.py", "_rsi_patch.json", "_audit_patch.json", "_rollover_patch.json", "_archive_patch.json"):
            errs_eq, _ = pdf_common.lint_markdown_report(f"# 标题\n\n内部文件 {leak_tok}。\n", "2026-11-27_0730_a_share.md")
            self.assertTrue(any(leak_tok in e for e in errs_eq), (leak_tok, errs_eq))
            self.assertTrue(gold_lint.SCORECARD_BANNED_RE.search(leak_tok), leak_tok)
            self.assertTrue(gold_lint._INTERNAL_FILENAME_LEAK_RE.search(leak_tok), leak_tok)

    def test_scorecard_year_rollover_chinese_tense_and_generalized_countdown(self):
        # 2027-01-02 vs 12/29 16:00 -> overdue!
        eq_dec29 = (
            "## 一、台账\n\n"
            "| 锁定 | 市场 | 判断 | 验真节点 | 结果 | 复盘 |\n"
            "| :--- | :---: | :--- | :--- | :---: | :--- |\n"
            "| 2026-12-28 | A 股 | 跨年逾期 | 12/29 16:00 | ⏳ 待验真 | 待补 |\n"
        )
        self.assertTrue(
            any("逾期未结案" in e for e in eq_lint._reconcile_equity_scorecard(eq_dec29, as_of_dt=datetime(2027, 1, 2, 7, 55)))
        )
        # 2026-11-27 vs 1/15 16:00 -> next year (2027-01-15), NOT overdue!
        eq_jan15 = eq_dec29.replace("12/29 16:00", "1/15 16:00")
        self.assertEqual(
            eq_lint._reconcile_equity_scorecard(eq_jan15, as_of_dt=datetime(2026, 11, 27, 7, 55)),
            [],
        )
        # Date-only MM/DD support
        eq_md_only_due = eq_dec29.replace("12/29 16:00", "12/29")
        self.assertTrue(
            any("逾期未结案" in e for e in eq_lint._reconcile_equity_scorecard(eq_md_only_due, as_of_dt=datetime(2027, 1, 2, 7, 55)))
        )

        # Same year-rollover checks on Gold scorecard
        gold_dec29 = (
            "## 三、表二\n\n"
            "| 锁定 | 判断 | 预定验真节点 | 状态 | 重点 |\n"
            "| :--- | :--- | :---: | :---: | :--- |\n"
            "| 2026-12-28 | 跨年逾期 | 12/29 16:00 | ⏳ 持续追踪 | 复核 |\n"
        )
        self.assertTrue(
            any("逾期未结案" in e for e in gold_lint._check_gold_scorecard_past_due(gold_dec29, datetime(2027, 1, 2, 7, 55)))
        )
        gold_jan15 = gold_dec29.replace("12/29 16:00", "1/15 16:00")
        self.assertEqual(gold_lint._check_gold_scorecard_past_due(gold_jan15, datetime(2026, 11, 27, 7, 55)), [])
        gold_md_only = gold_dec29.replace("12/29 16:00", "12/29")
        self.assertTrue(
            any("逾期未结案" in e for e in gold_lint._check_gold_scorecard_past_due(gold_md_only, datetime(2027, 1, 2, 7, 55)))
        )

        # Chinese MM月DD日 tense-drift
        for checker in (eq_lint._check_tense_drift, gold_lint._check_tense_drift):
            self.assertTrue(checker("t.md", "明日（12月1日）月度切换。", "2026-12-01"))
            self.assertTrue(checker("t.md", "今日（11月30日）收盘。", "2026-12-01"))
            self.assertTrue(checker("t.md", "昨日 11月29日数据披露。", "2026-12-01"))
            self.assertEqual(checker("t.md", "今日（12月1日）月度切换，明日（12月2日）观察。", "2026-12-01"), [])

        # Generalized 20xx year-end countdown
        self.assertEqual(eq_lint._check_year_end_countdown("t.md", "距 2027 年底仅剩 363 天。", "2027-01-02"), [])
        self.assertTrue(eq_lint._check_year_end_countdown("t.md", "距 2027 年底仅剩 360 天。", "2027-01-02"))

    def test_credit_spread_ccc_guard_equity_and_gold(self):
        bad1 = "美债 4.85% 叠加垃圾债利差 1,405 基点压制风险资产。"
        bad2 = "受休市影响，11/25 美国高收益与垃圾债信用利差顺延披露。"
        good1 = "美债 4.85% 叠加 CCC 级垃圾债利差 1,405 基点（全口径高收益债 372 基点）。"
        good2 = "受休市影响，11/25 美国高收益与 CCC 级垃圾债信用利差顺延披露。"

        for checker in (eq_lint._check_credit_spread_ccc, gold_lint._check_credit_spread_ccc):
            self.assertTrue(checker("t.md", bad1))
            self.assertTrue(checker("t.md", bad2))
            self.assertEqual(checker("t.md", good1), [])
            self.assertEqual(checker("t.md", good2), [])

    def test_gold_archive_ledgers_and_non_investment_scorecard_exclusion(self):
        # 1. Archived November CHANGELOG & AUDIT_LOG satisfy _check_edition_ledgers after rollover
        edition = "2026-11-27_0730"
        as_of = "2026-11-27 07:55"
        review_obj = {
            "edition_id": edition,
            "as_of_short": as_of,
            "note": "月度归档后仍可核验。",
            "sources": {k: ["https://example.com/evidence"] for k in gold_lint.ENTRY_GATE_IDS},
            "forecast_review": {"status": "none_due", "note": "无到期", "sources": []},
        }
        with TemporaryDirectory() as tmp:
            t = Path(tmp)
            cl = t / "CHANGELOG.md"
            al = t / "AUDIT_LOG.md"
            sc = t / "SCORECARD.md"
            cl.write_text("# 12 月新卷\n<!-- GOLD_EDITION_CHANGELOG 2026-12-01_0730 -->\n", encoding="utf-8")
            al.write_text("# 12 月核验卷\n", encoding="utf-8")
            sc.write_text("<!-- GOLD_EDITION_SCORECARD 2026-12-01_0730 -->\n", encoding="utf-8")
            arch = t / "archive" / "2026-11"
            arch.mkdir(parents=True)
            (arch / "CHANGELOG_2026_11.md").write_text(f"<!-- GOLD_EDITION_CHANGELOG {edition} -->\n", encoding="utf-8")
            (arch / "AUDIT_LOG_2026_11.md").write_text(
                f"<!-- GOLD_EDITION_REVIEW {json.dumps(review_obj, ensure_ascii=False)} -->\n",
                encoding="utf-8",
            )
            with patch.multiple(gold_lint, CHANGELOG_PATH=cl, AUDIT_LOG_PATH=al, SCORECARD_PATH=sc):
                errs: list[str] = []
                gold_lint._check_edition_ledgers(edition, as_of, errs, is_current=False)
                self.assertEqual(errs, [])

        # 2. SCORECARD non-investment rows (⚪ 运维记录 / 不计入投资胜率) excluded cleanly from scored denominator
        def _build_sc(summary_row: str, ops_verdict: str) -> str:
            return (
                "## 一、总览\n\n"
                "| 统计口径 | 累计条目数 | ✅ 兑现 | ⚠️ 部分兑现 | ❌ 证伪 | ⚪ 条件未触发 | 兑现率 | 至少部分 |\n"
                "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n"
                f"{summary_row}\n\n"
                "## 二、表一\n\n"
                "| 刊期 | 判断 | 节点 | 结果 | 判定 | 复盘 |\n"
                "| :--- | :--- | :---: | :--- | :---: | :--- |\n"
                "| 11-24 | 预测一 | 11-25 | 达标 | **✅ 兑现** | 准确 |\n"
                f"| 11-24 | 补录计划（不计入投资胜率） | 11-25 | 完成 | {ops_verdict} | 运维 |\n"
                "| 11-25 | 触发线 | 11-26 | 未触 | **⚪ 条件未触发** | 保持 |\n"
            )

        # Case 1: ops folded into ⚪ column (tot=3, scored=1, pass=1, partial=0, fail=0, ⚪=2)
        errs_folded: list[str] = []
        gold_lint._reconcile_gold_scorecard(
            _build_sc("| **已到期公开回验** | **3 项**（计分 1 项） | **1 项** | **0 项** | **0 项** | **2 项** | 100% | 100% |", "**⚪ 运维记录**"),
            errs_folded,
        )
        self.assertEqual(errs_folded, [])

        # Case 2: ops tracked separately from ⚪ 条件未触发 (tot=3, scored=1, pass=1, ⚪=1, ops=1)
        errs_sep: list[str] = []
        gold_lint._reconcile_gold_scorecard(
            _build_sc("| **已到期公开回验** | **3 项**（计分 1 项，含运维 1 项） | **1 项** | **0 项** | **0 项** | **1 项** | 100% | 100% |", "**⚪ 运维记录**"),
            errs_sep,
        )
        self.assertEqual(errs_sep, [])

        # Case 3: contradiction — ops row erroneously counted inside 计分 2 项 / ⚠️ 1 项 -> FAILS!
        errs_bad: list[str] = []
        gold_lint._reconcile_gold_scorecard(
            _build_sc("| **已到期公开回验** | **3 项**（计分 2 项） | **1 项** | **1 项** | **0 项** | **1 项** | 50% | 100% |", "**⚠️ 部分兑现**"),
            errs_bad,
        )
        self.assertTrue(any("表一对账错" in e for e in errs_bad), errs_bad)

    def test_gold_build_daily_persona_badge_wcag_aa_contrast(self):
        html_out = gold_daily.render_persona_cards({
            "title": "对号入座",
            "cards": [
                {"group": "A", "heading": "空仓观望", "actions": ["等四关全亮"]},
                {"group": "C", "heading": "刚需买金", "actions": ["按需分批"]},
            ],
        })
        self.assertIn('<span class="grp-badge" style="background:#0369a1;">A</span>', html_out)
        self.assertIn('<span class="grp-badge" style="background:#047857;">C</span>', html_out)
        self.assertNotIn("#0284c7", html_out)
        self.assertNotIn("#059669", html_out)

    def test_svg_geometry_translate_without_xy_and_inline_tspan(self):
        # 1. <text> omitting x/y but positioned via transform="translate(tx, ty)" MUST be checked for OOB & overlap
        svg_oob = (
            '<svg viewBox="0 0 640 200">'
            '<text transform="translate(625, 50)" font-size="12">OutOfBoundsLabel</text>'
            '</svg>'
        )
        issues_oob = check_svg_text_geometry(svg_oob, label="TR_OOB")
        self.assertTrue(any("SVG 文字越界" in x for x in issues_oob), issues_oob)

        svg_group_overlap = (
            '<svg viewBox="0 0 640 200">'
            '<g transform="translate(100, 80)"><text font-size="12">OverlapA</text></g>'
            '<text x="102" y="80" font-size="12">OverlapB</text>'
            '</svg>'
        )
        issues_ov = check_svg_text_geometry(svg_group_overlap, label="TR_OV")
        self.assertTrue(any("SVG 文字重叠" in x for x in issues_ov), issues_ov)

        # 2. Inline <tspan> following <tspan dy="14"> advances cur_x and must NOT false-collide
        svg_inline_ok = (
            '<svg viewBox="0 0 640 200">'
            '<text x="40" y="40" font-size="12"><tspan dy="14">LabelA</tspan><tspan font-weight="700">LabelB</tspan></text>'
            '<text x="320" y="100" text-anchor="middle" font-size="12">'
            '<tspan dy="14">CenterPart1 </tspan><tspan font-weight="700">CenterPart2</tspan></text>'
            '</svg>'
        )
        self.assertEqual(check_svg_text_geometry(svg_inline_ok, label="TSPAN_INLINE"), [])

        # 3. Explicit same-x overlapping <tspan> STILL caught
        svg_tspan_collide = (
            '<svg viewBox="0 0 640 200">'
            '<text x="40" y="40" font-size="12"><tspan dy="14">SameLineA</tspan><tspan x="40">SameLineB</tspan></text>'
            '</svg>'
        )
        issues_ts = check_svg_text_geometry(svg_tspan_collide, label="TSPAN_COLLIDE")
        self.assertTrue(any("SVG 文字重叠" in x for x in issues_ts), issues_ts)


if __name__ == "__main__":
    unittest.main()
