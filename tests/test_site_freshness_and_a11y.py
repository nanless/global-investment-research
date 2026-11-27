#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprehensive unit tests for Website UX, Screener Freshness Sync, Caveat Dedup,
Accessibility (h1 == 1), Gold TOC Compatibility, Masthead Timestamp Symmetry,
Mobile Overflow CSS Guards, and Expanded Glossary Terms."""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_site  # noqa: E402
import lint_site  # noqa: E402


class TestScreenerFreshnessOverlay(unittest.TestCase):
    """Tests for _overlay_fresher_dossier_on_stock and merge_stock_dossiers."""

    def test_updates_03750_hk_badge_price_and_summary_from_fresher_dossier(self):
        stock = {
            "market": "hk-stock",
            "market_label": "港股",
            "sector": "新能源",
            "name": "宁德时代",
            "code": "03750.HK",
            "price": "336.80 / 午跌超 6%（100 股/3.2 万）",
            "price_num": 336.80,
            "valuation": "PE 15.2x / AH 倒挂 -16%",
            "color": "b",
            "action_label": "未来主攻",
            "summary": "倒挂创 52 周新低！买 A 股 300750；H股·通20%/离核公告；锚 285 下",
            "is_gold_locked": False,
            "report_url": "reports/hk-stock.html",
        }
        dossier = {
            "depth_tier": "core_deep",
            "baseline_note": "基线价格与一手：11/26 官收 297.00 港元（+0.47%）；每手 100 股 ≈ 2.97 万港元；PE 13.4x / 深度 AH 倒挂 -19.7%。",
            "action_etf": "🔴 高危回避（AH 严重倒挂）：有 A 股账户者严禁在港股追高接盘，只观察便宜近两成的 A 股 300750。",
            "updated_at": "2026-11-27",
        }

        updated = build_site._overlay_fresher_dossier_on_stock(
            stock, dossier, "2026-11-25", gold_tier0_locked=True
        )
        self.assertEqual(updated["color"], "r")
        self.assertEqual(updated["action_label"], "高危回避")
        self.assertIn("297.00", updated["price"])
        self.assertIn("+0.47%", updated["price"])
        self.assertLessEqual(len(updated["price"]), 42)
        self.assertEqual(updated["price_num"], 297.0)
        self.assertEqual(updated["price_updated_at"], "2026-11-27")
        self.assertLessEqual(len(updated["summary"]), 78)
        self.assertNotIn("<br", updated["summary"])
        self.assertNotIn("**", updated["summary"])
        self.assertIn("严禁", updated["summary"])

    def test_updates_us_stock_nvda_dollar_price_cleanly(self):
        stock = {
            "market": "us-stock",
            "code": "NVDA",
            "name": "英伟达",
            "price": "$155.38 (-5.86%) / 盘后 $153.96",
            "price_num": 155.38,
            "color": "y",
            "action_label": "分歧观察",
            "summary": "4 调查 + 12/01–03 听证 + 12/04 季报死线；锚 $130–$140",
            "is_gold_locked": False,
        }
        dossier = {
            "baseline_note": "基线价格：11/25 官收 $149.30 (-3.91%，日低 $141.17)；现价市盈率 16.04x。",
            "action_etf": "🟡 分歧观察（听证前科技新仓锁死 0%）：估值虽回落至 16 倍，严禁听证前抢跑，回踩观察锚 130–140 美元；替身 SMH。",
            "updated_at": "2026-11-27",
        }
        updated = build_site._overlay_fresher_dossier_on_stock(
            stock, dossier, "2026-11-25", gold_tier0_locked=True
        )
        self.assertEqual(updated["color"], "y")
        self.assertEqual(updated["price"], "11/25 官收 $149.30 (-3.91%)")
        self.assertEqual(updated["price_num"], 149.30)
        self.assertEqual(updated["price_updated_at"], "2026-11-27")

    def test_gold_locked_stock_never_becomes_green_under_tier0_lock(self):
        # Case 1: Negated wording "严禁列为当下底座" on 02899.HK
        zijin_hk = {
            "market": "hk-stock",
            "code": "02899.HK",
            "name": "紫金矿业",
            "price": "23.38",
            "price_num": 23.38,
            "color": "b",
            "action_label": "未来主攻",
            "summary": "受铜熊金红灯压制；锚 21 下",
            "is_gold_locked": True,
        }
        dossier_negated = {
            "baseline_note": "基线价格与一手：11/26 港交所官收校准为 23.22 港元（+2.74%）；受黄金红灯停严锁。",
            "action_etf": "严禁列为当下底座或此刻新买！严格受黄金红灯停（新仓严格 0%）约束。",
            "updated_at": "2026-11-26",
        }
        res1 = build_site._overlay_fresher_dossier_on_stock(
            zijin_hk, dossier_negated, "2026-11-25", gold_tier0_locked=True
        )
        self.assertNotEqual(res1["color"], "g")
        self.assertEqual(res1["color"], "b")
        self.assertEqual(res1["price_num"], 23.22)

        # Case 2: Even if a gold-locked dossier explicitly says 🟢 当下底座, Tier-0 lock blocks 'g'
        nem = {
            "market": "us-stock",
            "code": "NEM",
            "name": "纽蒙特",
            "price": "$42.00",
            "price_num": 42.0,
            "color": "y",
            "action_label": "分歧观察",
            "summary": "黄金矿业龙头",
            "is_gold_locked": True,
        }
        dossier_green_attempt = {
            "baseline_note": "基线价格：11/26 官收 $43.10 (+1.20%)。",
            "action_etf": "🟢 当下底座（测试误标尝试）",
            "updated_at": "2026-11-27",
        }
        res2 = build_site._overlay_fresher_dossier_on_stock(
            nem, dossier_green_attempt, "2026-11-25", gold_tier0_locked=True
        )
        self.assertNotEqual(res2["color"], "g")
        self.assertEqual(res2["color"], "y")

        # Case 3: Stale stock card already mistakenly 'g' gets downgraded off 'g' under Tier-0 lock
        nem_bad = {**nem, "color": "g", "action_label": "当下底座"}
        res3 = build_site._overlay_fresher_dossier_on_stock(
            nem_bad, dossier_green_attempt, "2026-11-25", gold_tier0_locked=True
        )
        self.assertNotEqual(res3["color"], "g")

    def test_explicit_red_dossier_overrides_even_if_date_not_fresher(self):
        stock = {
            "market": "hk-stock",
            "code": "06181.HK",
            "name": "老铺黄金",
            "price": "272.60",
            "price_num": 272.60,
            "color": "b",
            "action_label": "未来主攻",
            "summary": "旧摘要",
            "is_gold_locked": True,
        }
        dossier = {
            "baseline_note": "基线价格：11/24 官收 272.60 港元。",
            "action_etf": "🔴 高危回避：严禁新买或抢权。",
            "updated_at": "2026-11-24",
        }
        res = build_site._overlay_fresher_dossier_on_stock(
            stock, dossier, "2026-11-25", gold_tier0_locked=True
        )
        self.assertEqual(res["color"], "r")
        self.assertEqual(res["action_label"], "高危回避")
        # Not strictly fresher than 2026-11-25, so price_updated_at is not set
        self.assertNotIn("price_updated_at", res)


class TestCaveatDeduplication(unittest.TestCase):
    """Tests for cross-track deduplication in collect_data_caveats."""

    def test_deduplicates_identical_and_near_identical_cross_track_caveats(self):
        gold_snap = {
            "data_caveats": [
                {
                    "id": "us_1125_credit_holiday_delayed",
                    "market": "gold",
                    "category": "delayed_official",
                    "severity": "info",
                    "item": "美国 11/25 信用利差、隔夜利率与财政部账户受感恩节顺延至美东周五发布",
                    "detail": "简短说明：受美国感恩节休假影响顺延发布。",
                    "impact": "四关核心硬门槛均已锁定，上述联邦滞后统计不影响当前红灯停裁决。",
                    "next_review": "2026-11-28_0730",
                }
            ]
        }
        eq_state = {
            "data_caveats": [
                {
                    "id": "us_1125_federal_stats_delayed",
                    "market": "us_stock",
                    "category": "delayed_official",
                    "severity": "warn",
                    "item": "美国 11/25 信用利差、隔夜基准利率与财政部账户受感恩节顺延至美东周五发布",
                    "detail": "受美国感恩节联邦休假顺延影响，11/25 美国高收益与垃圾债信用利差、隔夜基准利率及财政部一般账户均顺延至美东周五发布，本期合法沿用 11/24 官方终值。",
                    "impact": "不影响红灯防守。",
                    "next_review": "2026-11-28_0730",
                }
            ]
        }

        merged = build_site.collect_data_caveats(gold_snap, eq_state)
        self.assertEqual(len(merged), 1)
        c = merged[0]
        self.assertEqual(c["market_label"], "黄金 / 美股")
        # Keeps higher severity (warn > info)
        self.assertEqual(c["severity"], "warn")
        # Keeps richer detail and richer impact across both records
        self.assertIn("高收益与垃圾债信用利差", c["detail"])
        self.assertIn("四关核心硬门槛均已锁定", c["impact"])

    def test_deduplicates_exact_title_with_critical_severity_precedence(self):
        gold_snap = {
            "data_caveats": [
                {
                    "id": "c1",
                    "market": "gold",
                    "severity": "warn",
                    "item": "官方接口临时维护（测试）！",
                    "detail": "短描述",
                    "impact": "短影响",
                }
            ]
        }
        eq_state = {
            "data_caveats": [
                {
                    "id": "c2",
                    "market": "cross",
                    "severity": "critical",
                    "item": "官方接口临时维护测试",
                    "detail": "更完整的官方接口临时维护说明，涵盖恢复预期与受影响维度。",
                    "impact": "更完整的裁决影响评估说明，核心仓位红线保持锁定不变。",
                }
            ]
        }
        merged = build_site.collect_data_caveats(gold_snap, eq_state)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["severity"], "critical")
        self.assertEqual(merged[0]["market_label"], "黄金")
        html = build_site._render_caveat_items_html(merged, "empty")
        # Maps critical safely to declared sev-high CSS class
        self.assertIn("sev-high", html)
        self.assertNotIn("sev-critical", html)


class TestGoldTocAndMastheadSymmetry(unittest.TestCase):
    """Tests for Gold TOC compatibility with <h2 class='vol-header'> and symmetric timestamps."""

    def test_sanitize_and_extract_toc_promotes_h2_vol_header_to_lvl1(self):
        gold_body = (
            '<h2 class="vol-header">上篇：30 秒红绿灯结论</h2>'
            '<h2>1. 隔夜实盘复盘</h2>'
            '<h3>1.1 伦敦与纽约价差</h3>'
            '<h2 class="vol-header">下篇：四关硬门槛核验</h2>'
            '<h2>2. 真实利率与汇率</h2>'
        )
        cleaned, toc, _ = build_site.sanitize_and_extract_toc(
            gold_body, base_prefix="../", slug_map={}, ctx_market="gold"
        )
        self.assertEqual(len(toc), 5)
        self.assertEqual([lvl for lvl, _, _ in toc], [1, 2, 3, 1, 2])
        self.assertEqual(toc[0][2], "上篇：30 秒红绿灯结论")
        self.assertEqual(toc[3][2], "下篇：四关硬门槛核验")
        # Ensures deterministic IDs injected for sidebar anchors
        for _, hid, _ in toc:
            self.assertIn(f'id="{hid}"', cleaned)

    def test_fmt_cst_compact_produces_symmetric_cst_timestamps(self):
        self.assertEqual(
            build_site.fmt_cst_compact("2026年11月27日（周五）07:55"),
            "2026-11-27 07:55 CST",
        )
        self.assertEqual(
            build_site.fmt_cst_compact("2026-11-27 07:55"),
            "2026-11-27 07:55 CST",
        )
        self.assertEqual(
            build_site.fmt_cst_compact("2026-11-27T07:55:00+08:00"),
            "2026-11-27 07:55 CST",
        )


class TestLintSiteFreshnessAndA11yGates(unittest.TestCase):
    """Tests that lint_site.py Gate S6 catches badge mismatch, duplicate caveats, and h1 != 1."""

    def _valid_dossier(self, action_etf: str) -> dict[str, str]:
        return {
            "moat": "行业龙头护城河深厚",
            "financials": "自由现金流稳健",
            "valuation_anchor": "估值锚定清晰",
            "shareholder_flow": "分红回购扎实",
            "catalysts": "财报节点临近",
            "bear_case": "周期下行风险",
            "action_etf": action_etf,
        }

    def test_lint_catches_screener_vs_dossier_red_mismatch(self):
        # Load real flagship benchmarks so only the badge contradiction triggers
        benchmarks = {}
        for mk in ("a-share", "hk-stock", "us-stock"):
            meta_p = REPO_ROOT / "equity" / f"report_meta_{mk.replace('-', '_')}.json"
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            benchmarks[mk] = str(meta.get("benchmark_time") or "").split("（", 1)[0]

        payload = [
            {
                "market": "hk-stock",
                "sector": "新能源",
                "name": "宁德时代",
                "code": "03750.HK",
                "price": "336.80",
                "valuation": "13.4x",
                "color": "b",
                "action_label": "未来主攻",
                "summary": "测试冲突项",
                "benchmark_time": benchmarks["hk-stock"],
                "dossier": self._valid_dossier("🔴 高危回避（AH 严重倒挂）：严禁港股追高接盘。"),
            }
        ]
        html = (
            "<!doctype html><html><body><h1>筛选器</h1>"
            f"<p>{benchmarks['a-share']} {benchmarks['hk-stock']} {benchmarks['us-stock']}</p>"
            f'<script id="screener-data" type="application/json">{json.dumps(payload, ensure_ascii=False)}</script>'
            "</body></html>"
        )
        doc = lint_site.parse_html_file("screener.html", Path("screener.html"), html)
        errors: list[str] = []
        lint_site._validate_screener_json(
            doc, {"a-share": 0, "hk-stock": 1, "us-stock": 0}, errors, gold_new_buy_blocked=True
        )
        self.assertTrue(
            any("badge contradiction" in e and "03750.HK" in e for e in errors),
            errors,
        )

        # Once aligned to 'r', no badge contradiction error is raised
        payload[0]["color"] = "r"
        payload[0]["action_label"] = "高危回避"
        html_ok = (
            "<!doctype html><html><body><h1>筛选器</h1>"
            f"<p>{benchmarks['a-share']} {benchmarks['hk-stock']} {benchmarks['us-stock']}</p>"
            f'<script id="screener-data" type="application/json">{json.dumps(payload, ensure_ascii=False)}</script>'
            "</body></html>"
        )
        doc_ok = lint_site.parse_html_file("screener.html", Path("screener.html"), html_ok)
        errors_ok: list[str] = []
        lint_site._validate_screener_json(
            doc_ok, {"a-share": 0, "hk-stock": 1, "us-stock": 0}, errors_ok, gold_new_buy_blocked=True
        )
        self.assertFalse(any("badge contradiction" in e for e in errors_ok), errors_ok)

    def test_lint_catches_duplicate_caveat_titles_and_h1_violations(self):
        idx_html = (
            "<!doctype html><html><body>"
            "<h1>驾驶舱</h1>"
            '<div class="caveat-item"><div class="caveat-title">美国 11/25 信用利差顺延发布</div></div>'
            '<div class="caveat-item"><div class="caveat-title">美国 11/25 信用利差顺延发布！</div></div>'
            "</body></html>"
        )
        etfs_zero_h1 = "<!doctype html><html><body><h2>缺少 H1 的 ETF 页面</h2></body></html>"
        gold_multi_h1 = (
            "<!doctype html><html><body>"
            "<h1>标题1</h1><h1>标题2</h1><h1>标题3</h1>"
            "</body></html>"
        )
        parsed = {
            "index.html": lint_site.parse_html_file("index.html", Path("index.html"), idx_html),
            "etfs.html": lint_site.parse_html_file("etfs.html", Path("etfs.html"), etfs_zero_h1),
            "daily/gold-latest.html": lint_site.parse_html_file(
                "daily/gold-latest.html", Path("daily/gold-latest.html"), gold_multi_h1
            ),
        }
        errors: list[str] = []
        warnings: list[str] = []
        lint_site.run_gate_s6(parsed, {}, {}, errors, warnings, already_checked_json_gold=True)
        self.assertTrue(
            any("duplicate data_caveats title" in e for e in errors),
            errors,
        )
        self.assertTrue(
            any("etfs.html" in e and "expected exactly 1 <h1>" in e and "found 0" in e for e in errors),
            errors,
        )
        self.assertTrue(
            any("daily/gold-latest.html" in e and "expected exactly 1 <h1>" in e and "found 3" in e for e in errors),
            errors,
        )


class TestCssAndGlossarySync(unittest.TestCase):
    """Tests for CSS overflow/contrast/heading rules and synced glossary expansion."""

    def test_app_css_contains_mobile_overflow_contrast_heading_and_table_fixes(self):
        css = (REPO_ROOT / "scripts" / "web_assets" / "app.css").read_text(encoding="utf-8")
        # 1. .ch-rules li overflow-wrap: anywhere
        self.assertRegex(
            css,
            r"\.ch-rules\s+li\s*\{[^}]*overflow-wrap:\s*anywhere",
        )
        for sel in (r"\.ch-meta-item\s*\{", r"\.ch-fit-box\s*\{", r"\.ch-avoid-box\s*\{", r"\.article-body\s+li\s*\{"):
            self.assertRegex(css, sel + r"[^}]*overflow-wrap:\s*anywhere")
        # 2. Gold light-mode active TOC contrast #854d0e (and dark mode #fbbf24 retained)
        self.assertIn('body[data-market="gold"] .toc-link.active { color: #854d0e;', css)
        self.assertIn('[data-theme="dark"] body[data-market="gold"] .toc-link.active { color: #fbbf24;', css)
        # 3. .sec-head h1 parity with .sec-head h2, plus h1.cover-title and h2.vol-header
        self.assertIn(".sec-head h1,", css)
        self.assertIn("h1.cover-title", css)
        self.assertIn("h2.vol-header", css)
        # 4. Desktop table first-column min-width protection
        self.assertRegex(
            css,
            r"@media\s*\(min-width:\s*769px\)\s*\{[^}]*\.article-body\s+table\s+th:first-child\s*\{[^}]*min-width:\s*96px",
        )

    def test_expanded_glossary_terms_synced_between_build_site_and_app_js(self):
        required_keys = ("w8ben", "crs", "low_water", "high_water", "ex_div", "discount_ex_div", "margin_hk")
        by_key = {t["key"]: t for t in build_site.GLOSSARY_TERMS}
        app_js = (REPO_ROOT / "scripts" / "web_assets" / "app.js").read_text(encoding="utf-8")

        for k in required_keys:
            self.assertIn(k, by_key, f"Missing {k} in build_site.GLOSSARY_TERMS")
            self.assertRegex(app_js, rf"\b{re.escape(k)}\s*:\s*\{{", f"Missing {k} in app.js GLOSSARY_DICT")

        # Non-intrusive injection: 低水/高水 must NOT fire inside 低水位 / 高水位 / 高水平
        guarded = build_site.inject_glossary_tips("<p>金管局总结余处于低水位，宏观维持高水平。</p>")
        self.assertNotIn('data-term="low_water"', guarded)
        self.assertNotIn('data-term="high_water"', guarded)

        # Positive match: W-8BEN, CRS, 除净, 贴权, 孖展, 期指低水 all inject cleanly
        matched = build_site.inject_glossary_tips(
            "<p>填写 W-8BEN 并留意 CRS 申报；港股期指低水，今日除净防贴权，切勿开孖展。</p>"
        )
        for k in ("w8ben", "crs", "low_water", "ex_div", "discount_ex_div", "margin_hk"):
            self.assertIn(f'data-term="{k}"', matched)


if __name__ == "__main__":
    unittest.main()
