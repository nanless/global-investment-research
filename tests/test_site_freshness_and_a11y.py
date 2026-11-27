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

    def test_glossary_48_terms_exact_parity_ex_div_guard_and_collapsed_details_quota(self):
        py_keys = [t["key"] for t in build_site.GLOSSARY_TERMS]
        spec_keys = [k for k, _ in build_site._GLOSSARY_PHRASE_SPECS]
        self.assertEqual(len(py_keys), 48)
        self.assertEqual(set(py_keys), set(spec_keys))

        app_js = (REPO_ROOT / "scripts" / "web_assets" / "app.js").read_text(encoding="utf-8")
        m_dict = re.search(r"const GLOSSARY_DICT\s*=\s*\{(.*?)\n  \};", app_js, re.DOTALL)
        self.assertIsNotNone(m_dict)
        js_keys = re.findall(r"^\s{4}([a-z0-9_]+)\s*:\s*\{", m_dict.group(1), re.MULTILINE)
        self.assertEqual(len(js_keys), 48)
        self.assertEqual(set(py_keys), set(js_keys))

        # ex_div regex must NOT false-match "零剔除净增"
        no_ex_div = build_site.inject_glossary_tips("<p>本季份额零剔除净增 1.2 亿份。</p>")
        self.assertNotIn('data-term="ex_div"', no_ex_div)

        # Collapsed <details> must NOT steal first-occurrence quota from later visible prose
        details_html = (
            "<details><summary>展开</summary><p>内部提到 ERP 与 折价配售。</p></details>"
            "<p>正文出现 ERP 与 折价配售。</p>"
        )
        injected = build_site.inject_glossary_tips(details_html)
        head_details, tail_prose = injected.split("</details>", 1)
        self.assertNotIn('data-term="erp"', head_details)
        self.assertNotIn('data-term="discount_placement"', head_details)
        self.assertIn('data-term="erp"', tail_prose)
        self.assertIn('data-term="discount_placement"', tail_prose)

    def test_dark_cover_tag_wcag_and_p2_contrast_tokens_and_cmd_palette_jumps(self):
        css = (REPO_ROOT / "scripts" / "web_assets" / "app.css").read_text(encoding="utf-8")
        self.assertIn('[data-theme="dark"] .cover-tag { color: #0f131a; }', css)
        self.assertRegex(css, r"\.holiday-date\s*\{[^}]*color:\s*#854d0e;")
        self.assertRegex(css, r"\.ch-risk-stars\s*\{[^}]*color:\s*#92400e;")
        self.assertRegex(css, r"\.sector-cnt\s*\{[^}]*opacity:\s*0\.85;")
        self.assertIn(".vm-g { color: #047857; }", css)
        self.assertIn(".vm-y { color: #9a5504; }", css)
        self.assertIn(".vm-r { color: #b94a00; }", css)

        app_js = (REPO_ROOT / "scripts" / "web_assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn('screener.html#q=', app_js)
        self.assertIn('etfs.html#q=', app_js)
        self.assertIn('guide.html#q=', app_js)
        self.assertIn("applyGuideHash", app_js)


class TestScreenerCurrencyPeAhAnchorAndSanitizer(unittest.TestCase):
    """Tests for P0-1 currency lock & arrow/slash parsing, P0-2 PE/AH/Div/Anchor sync,
    guide Pitfall #8 invariant, _HARD_INFRA_RE sanitizer, and extended Gate S6 checks."""

    def test_a_share_600938_rejects_brent_usd_quote_and_preserves_rmb_price(self):
        brent_note = (
            "基线参考价：11/26 随油价走强上涨（隔夜沙特炼厂遇袭推布油 1 月官结至 $96.57/+2.07%）；"
            "PE-TTM 10.54x / AH 溢价 +69.2%（按 11/26 央行中间价 0.85582 核算）。"
        )
        self.assertIsNone(build_site._extract_fresh_price_from_baseline(brent_note, "a-share"))
        # Also verify strict cross-market currency locks
        self.assertIsNone(build_site._extract_fresh_price_from_baseline("11/26 官收 23.30 元", "hk-stock"))
        self.assertIsNone(build_site._extract_fresh_price_from_baseline("11/26 官收 $96.57", "hk-stock"))
        self.assertIsNone(build_site._extract_fresh_price_from_baseline("11/26 官收 41.28 港元", "us-stock"))
        self.assertIsNone(build_site._extract_fresh_price_from_baseline("11/26 官收 52.93 元", "us-stock"))

        stock = {
            "market": "a-share",
            "code": "600938",
            "name": "中国海油",
            "price": "38.20 元",
            "price_num": 38.20,
            "valuation": "10.1x / 1.80x / 4.2% / +65.0%",
            "color": "g",
            "action_label": "当下底座",
            "summary": "能源高息底座；锚 25.5–27.0 元",
        }
        dossier = {
            "baseline_note": brent_note,
            "action_etf": "IF 回调至 25.5–27.0 元 THEN 分批配能源底座。",
            "updated_at": "2026-11-27",
        }
        updated = build_site._overlay_fresher_dossier_on_stock(
            stock, dossier, "2026-11-25", gold_tier0_locked=True, ah_lookup={"600938": 69.2}
        )
        self.assertEqual(updated["price"], "38.20 元")
        self.assertNotIn("$", updated["price"])
        self.assertEqual(updated["ah_pct"], 69.2)
        self.assertIn("+69.2%", updated["valuation"])

    def test_arrow_and_slash_rightmost_price_extraction_and_adr_pct_guard(self):
        # META arrow progression
        self.assertEqual(
            build_site._extract_fresh_price_from_baseline(
                "基线价格：11/24 $589.82 (-1.30%) → 11/25 更新 $609.89 (+3.40%)；前瞻 PE 17.1–20.4x。",
                "us-stock",
            ),
            "11/25 $609.89 (+3.40%)",
        )
        # 00700.HK arrow progression
        self.assertEqual(
            build_site._extract_fresh_price_from_baseline(
                "基线价格与一手：11/24 收 341.60 → 11/26 官收 341.00 港元（+1.07%）；每手 100 股 ≈ 3.41 万港元。",
                "hk-stock",
            ),
            "11/26 官收 341.00 港元 (+1.07%)",
        )
        # 00005.HK arrow progression
        self.assertEqual(
            build_site._extract_fresh_price_from_baseline(
                "基线价格与一手：11/25 官收 128.60 港元（-1.53%）→ 11/26 官收 128.40 港元（-0.16%，伦敦盘 HSBA.L 平盘 +0.02%）；每手 400 股。",
                "hk-stock",
            ),
            "11/26 官收 128.40 港元 (-0.16%)",
        )
        # Dual-date slash progression (01810.HK / 09626.HK / 09992.HK)
        self.assertEqual(
            build_site._extract_fresh_price_from_baseline(
                "基线价格与一手：11/24 收 26.50 / 11/25 午逼空 27.58（官收 +0.23%）；每手 200 股。",
                "hk-stock",
            ),
            "11/25 27.58 港元 (+0.23%)",
        )
        # 09618.HK must NEVER stitch overnight ADR +3.1% onto 11/24 HK close
        jd_price = build_site._extract_fresh_price_from_baseline(
            "基线价格与一手：11/24 收 97.05 港元（11/25 午大涨、隔夜美股 ADR +3.1%）；每手 50 股。",
            "hk-stock",
        )
        self.assertEqual(jd_price, "11/24 官收 97.05 港元")
        self.assertNotIn("+3.1%", jd_price)

    def test_parse_pe_ignores_4_digit_year_and_ah_prefers_live_lookup(self):
        # us-stock:LLY must parse 28.0, never 2027.0
        self.assertEqual(
            build_site._parse_pe_num("基线价格：11/25 官收 $1,392.22；前瞻 PE 2027 预期 ~28x（2026 预期 ~40x）。", "us-stock"),
            28.0,
        )
        # _parse_ah_pct prefers live ah_lookup over stale valuation text
        self.assertEqual(
            build_site._parse_ah_pct("PE 15.2x / AH 倒挂 -16%", "", "hk-stock", "03750.HK", {"03750.HK": -19.7}),
            -19.7,
        )
        # Unsigned 倒挂 / 折价 / A折H must be negated
        self.assertEqual(build_site._parse_ah_pct("AH 倒挂 15.4%", "", "hk-stock", "99999.HK", {}), -15.4)
        self.assertEqual(build_site._parse_ah_pct("A折H 2.4%", "", "a-share", "300308", {}), -2.4)

    def test_anchor_preservation_us_div_sync_and_placement_warning_surface(self):
        # 03750.HK preserves prior anchor (285) even after summary switches to red-avoid prose
        catl_hk = {
            "market": "hk-stock",
            "code": "03750.HK",
            "name": "宁德时代",
            "price": "336.80",
            "price_num": 336.80,
            "valuation": "PE 15.2x / AH 倒挂 -16%",
            "color": "b",
            "action_label": "未来主攻",
            "summary": "倒挂创 52 周新低；锚 285 下",
        }
        catl_dos = {
            "baseline_note": "基线价格与一手：11/26 官收 297.00 港元（+0.47%）；PE 13.4x / 深度 AH 倒挂 -19.7%。",
            "action_etf": "🔴 高危回避（AH 严重倒挂）：有 A 股账户者严禁在港股追高接盘，只观察便宜近两成的 A 股 300750。",
            "updated_at": "2026-11-27",
        }
        res_catl = build_site._overlay_fresher_dossier_on_stock(
            catl_hk, catl_dos, "2026-11-25", gold_tier0_locked=True, ah_lookup={"03750.HK": -19.7}
        )
        self.assertEqual(res_catl["anchor_low"], 285.0)
        self.assertEqual(res_catl["anchor_high"], 285.0)
        self.assertEqual(res_catl["pe_num"], 13.4)
        self.assertEqual(res_catl["ah_pct"], -19.7)
        self.assertIn("-19.7%", res_catl["valuation"])

        # 02015.HK extracts anchor from full baseline_note/action_etf even when truncated summary omits it
        li_hk = {
            "market": "hk-stock",
            "code": "02015.HK",
            "name": "理想汽车",
            "price": "42.00",
            "price_num": 42.00,
            "valuation": "亏损 / 无 A 股",
            "color": "r",
            "action_label": "高危回避",
            "summary": "旧摘要无锚",
        }
        li_dos = {
            "baseline_note": "基线参考价 11/26 官收 45.80 港元（+8.02%）；扭亏拐点期 / 纯港股（安全锚 38.0–40.0 港元）。",
            "action_etf": "当前 🟡 分歧观察（基本面显著改善但忌追绩后 +8% 脉冲）：882 亿现金与 FCF 转正夯实底部，IF 回踩 38.0–40.0 港元再右侧跟踪。",
            "updated_at": "2026-11-26",
        }
        res_li = build_site._overlay_fresher_dossier_on_stock(li_hk, li_dos, "2026-11-25", gold_tier0_locked=True)
        self.assertEqual(res_li["anchor_low"], 38.0)
        self.assertEqual(res_li["anchor_high"], 40.0)
        self.assertIsNotNone(res_li["anchor_gap_pct"])

        # US stock extracts div_pct from fresher baseline_note when div_pct is None
        jpm = {
            "market": "us-stock",
            "code": "JPM",
            "name": "摩根大通",
            "price": "$310.00",
            "price_num": 310.0,
            "valuation": "13.0x",
            "div_pct": None,
            "color": "g",
            "action_label": "当下底座",
            "summary": "银行底座",
        }
        jpm_dos = {
            "baseline_note": "基线价格：11/25 官收 $316.74；前瞻 PE 12.1–12.7x + 股息率 2.1%。",
            "action_etf": "银行底座稳健持有。",
            "updated_at": "2026-11-26",
        }
        res_jpm = build_site._overlay_fresher_dossier_on_stock(jpm, jpm_dos, "2026-11-25", gold_tier0_locked=True)
        self.assertEqual(res_jpm["div_pct"], 2.1)
        self.assertEqual(res_jpm["pe_num"], 12.1)

        # 01088.HK placement warning immediately surfaces on summary
        sh_hk = {
            "market": "hk-stock",
            "code": "01088.HK",
            "name": "中国神华",
            "price": "39.98",
            "price_num": 39.98,
            "valuation": "12.2x / 6.2% / AH +45%",
            "color": "g",
            "action_label": "当下底座",
            "summary": "11/23 派中期息、煤电长协锁息",
        }
        sh_dos = {
            "baseline_note": "基线价格与一手：11/26 官收 41.28 港元（+3.25%）；PE 12.7x / AH 溢价 +49.8%。",
            "action_etf": "短期先避配售抛压，切勿在 41 港元附近立即追买！11/27 盘前按 38.10 港元折价配售 1.77 亿股。",
            "updated_at": "2026-11-27",
        }
        res_sh = build_site._overlay_fresher_dossier_on_stock(
            sh_hk, sh_dos, "2026-11-25", gold_tier0_locked=True, ah_lookup={"01088.HK": 49.8}
        )
        self.assertIn("配售", res_sh["summary"])
        self.assertIn("切勿", res_sh["summary"])

    def test_hard_infra_re_strips_patch_state_dbs_and_guide_pitfall8_cd_invariant(self):
        for tok in (
            "patch_state_dbs.py",
            "svg_geometry.py",
            "_edition_patch.json",
            "_ledger_patch.json",
            "_rsi_patch.json",
            "_audit_patch.json",
            "_rollover_patch.json",
            "_archive_patch.json",
            "multi_asset_channels.json",
            "etf_universe.json",
            "deep_dossiers.json",
        ):
            self.assertIsNotNone(build_site._HARD_INFRA_RE.search(tok), f"_HARD_INFRA_RE missed {tok}")
            self.assertIsNotNone(lint_site.S3_INTERNAL_ENG_LEAK_RE.search(tok), f"S3_INTERNAL_ENG_LEAK_RE missed {tok}")
            sanitized = build_site._sanitize_caveat_text(f"已完成 `{tok}` 更新")
            self.assertNotIn(tok, sanitized, f"_sanitize_caveat_text leaked {tok}")

        guide_html = build_site.build_guide_page({"tier_code": "Tier 0", "new_buy_allowed": False}, {}, None, None)
        self.assertNotIn("二手存单变现只能再次挂单转让", guide_html)
        self.assertIn("多数国有大行禁止二次转让", guide_html)
        self.assertIn("channels/large_cds.html", guide_html)

    def test_lint_site_s6_currency_ah_parity_bidirectional_badge_and_invariants(self):
        benchmarks = {}
        for mk in ("a-share", "hk-stock", "us-stock"):
            meta_p = REPO_ROOT / "equity" / f"report_meta_{mk.replace('-', '_')}.json"
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            benchmarks[mk] = str(meta.get("benchmark_time") or "").split("（", 1)[0]

        def _dos(act: str) -> dict[str, str]:
            return {
                "moat": "护城河",
                "financials": "现金流",
                "valuation_anchor": "估值锚",
                "shareholder_flow": "回报",
                "catalysts": "催化",
                "bear_case": "风险",
                "action_etf": act,
            }

        payload = [
            {
                "market": "a-share",
                "sector": "石油",
                "name": "中国海油",
                "code": "600938",
                "price": "11/26 $96.57",
                "valuation": "10.5x",
                "ah_pct": 50.0,
                "color": "r",
                "action_label": "高危回避",
                "summary": "测试",
                "benchmark_time": benchmarks["a-share"],
                "dossier": _dos("🟢 当下底座：测试反向冲突。"),
            },
            {
                "market": "hk-stock",
                "sector": "煤炭",
                "name": "中国神华",
                "code": "01088.HK",
                "price": "41.28 港元",
                "valuation": "12.7x",
                "ah_pct": 49.8,
                "color": "g",
                "action_label": "当下底座",
                "summary": "旧摘要未提示风险",
                "benchmark_time": benchmarks["hk-stock"],
                "dossier": _dos("短期先避配售抛压，切勿在 41 港元附近立即追买！"),
            },
        ]
        html = (
            "<!doctype html><html><body><h1>筛选器</h1>"
            f"<p>{benchmarks['a-share']} {benchmarks['hk-stock']} {benchmarks['us-stock']}</p>"
            f'<script id="screener-data" type="application/json">{json.dumps(payload, ensure_ascii=False)}</script>'
            "</body></html>"
        )
        doc = lint_site.parse_html_file("screener.html", Path("screener.html"), html)
        errs: list[str] = []
        ms = {
            "cross_market_linkages": {
                "ah_premium_radar": {
                    "benchmarks": [{"a": "600938", "h": "00883.HK", "ah_premium_pct": 69.2}]
                }
            }
        }
        lint_site._validate_screener_json(
            doc, {"a-share": 1, "hk-stock": 1, "us-stock": 0}, errs, gold_new_buy_blocked=True, market_state=ms
        )
        self.assertTrue(any("currency violation" in e and "600938" in e for e in errs), errs)
        self.assertTrue(any("ah_pct parity mismatch" in e and "600938" in e for e in errs), errs)
        self.assertTrue(any("badge contradiction" in e and "600938" in e for e in errs), errs)
        self.assertTrue(any("omits urgent placement/chase-buy warning" in e and "01088.HK" in e for e in errs), errs)

        # Duplicate caveat check on daily/*-latest.html + permanent invariant scan on guide.html & reports/*.html
        daily_dup = (
            "<!doctype html><html><body><h1>早报</h1>"
            '<div class="caveat-item"><div class="caveat-title">美东休市顺延</div></div>'
            '<div class="caveat-item"><div class="caveat-title">美东休市顺延！</div></div>'
            "</body></html>"
        )
        bad_guide = "<!doctype html><html><body><h1>指南</h1><p>二手存单变现只能再次挂单转让。</p></body></html>"
        bad_rep = "<!doctype html><html><body><h1>手册</h1><p>买 3081.HK 或借道债券 ETF 合法避税。</p></body></html>"
        parsed = {
            "daily/gold-latest.html": lint_site.parse_html_file("daily/gold-latest.html", Path("daily/gold-latest.html"), daily_dup),
            "guide.html": lint_site.parse_html_file("guide.html", Path("guide.html"), bad_guide),
            "reports/gold.html": lint_site.parse_html_file("reports/gold.html", Path("reports/gold.html"), bad_rep),
        }
        s6_errs: list[str] = []
        s6_warns: list[str] = []
        lint_site.run_gate_s6(parsed, {}, {}, s6_errs, s6_warns, already_checked_json_gold=True)
        self.assertTrue(any("daily/gold-latest.html" in e and "duplicate data_caveats title" in e for e in s6_errs), s6_errs)
        self.assertTrue(any("guide.html" in e and "permanent invariant violation" in e for e in s6_errs), s6_errs)
        self.assertTrue(any("reports/gold.html" in e and "4-digit .HK" in e for e in s6_errs), s6_errs)
        self.assertTrue(any("reports/gold.html" in e and "tax-avoidance" in e for e in s6_errs), s6_errs)


if __name__ == "__main__":
    unittest.main()
