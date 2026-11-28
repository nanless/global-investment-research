#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprehensive unit tests for patch_state_dbs, edition_run telemetry, publish_site guards, and permissions."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta
from io import StringIO
import copy
import json
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import edition_run, install_sidecars, inventory_evidence, patch_state_dbs as psd, publish_site, review_evidence, state_transaction


class InventoryEvidenceTests(unittest.TestCase):
    def test_citation_is_limited_to_a_populated_field_and_the_edition(self):
        citation = {"field": "fee_total_pct", "source_url": "https://www.sse.com.cn/funds/example.pdf",
                    "as_of": "2026-11-27", "note": "基金产品概要第二节的费率表"}
        inventory = {"fee_total_pct": "0.20%", "evidence": [citation]}
        cutoff = date(2026, 11, 28)
        self.assertEqual(inventory_evidence.inventory_evidence(inventory, inventory_evidence.ETF_FIELDS, cutoff), [citation])
        for bad in (
            dict(citation, source_url="https://example.com/prospectus"),
            dict(citation, as_of="2026-11-29"), dict(citation, field="aum"), dict(citation, note="核验"),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                inventory_evidence.inventory_evidence(dict(inventory, evidence=[bad]), inventory_evidence.ETF_FIELDS, cutoff)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            inventory_evidence.inventory_evidence(dict(inventory, evidence=[citation, citation]), inventory_evidence.ETF_FIELDS, cutoff)
        revised = dict(inventory, fee_total_pct="0.60%")
        inventory_evidence.retain_inventory_evidence(inventory, revised, {"fee_total_pct": "0.60%"})
        self.assertEqual(revised["evidence"], [])
        same_fee = dict(inventory, aum="规模待核")
        inventory_evidence.retain_inventory_evidence(inventory, same_fee, {"aum": "规模待核"})
        self.assertEqual(same_fee["evidence"], [citation])

    def test_research_json_rejects_duplicate_and_nonfinite_values(self):
        for payload in ('{"price": 13, "price": 12}', '{"price": NaN}', '{"price": 1e1000}'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                inventory_evidence.load_research_json(payload)

    def test_sse_quote_feed_is_limited_to_matching_stock_and_baseline(self):
        citation = {
            "field": "baseline_note",
            "source_url": "https://yunhq.sse.com.cn:32042/v1/sh1/dayk/600919?select=date,close&begin=2499&end=2500",
            "as_of": "2026-11-27",
            "note": "上交所记录列明该交易日收盘。",
        }
        stock = {
            "market": "a-share", "code": "600919", "baseline_note": "收盘 13.46 元",
            "financials": "营业收入待查", "evidence": [citation],
        }
        fields = inventory_evidence.STOCK_FIELDS
        self.assertEqual(inventory_evidence.inventory_evidence(stock, fields), [citation])
        for invalid in (
            dict(stock, code="600001"),
            dict(stock, market="hk-stock"),
            dict(stock, evidence=[dict(citation, field="financials")]),
            dict(stock, evidence=[dict(citation, source_url=citation["source_url"].replace(":32042", ":32043"))]),
            dict(stock, evidence=[dict(citation, source_url=citation["source_url"].split("?")[0])]),
            dict(stock, evidence=[dict(citation, source_url=citation["source_url"].replace("2499", "-2"))]),
            dict(stock, evidence=[dict(citation, source_url=citation["source_url"] + "&begin=2499")]),
            dict(stock, evidence=[dict(citation, source_url=citation["source_url"].replace("date,close", "close"))]),
        ):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "specific HTTPS"):
                inventory_evidence.inventory_evidence(invalid, fields)


def _make_channel(cid: str, order: int) -> dict:
    return {
        "id": cid,
        "order": order,
        "name": f"渠道 {cid}",
        "short_name": cid,
        "badge": "测试标签",
        "category": "cash",
        "category_label": "活钱与存款",
        "money_bucket": "liquid",
        "high_net_worth_only": False,
        "min_amount_tier": "1w",
        "risk_stars": 1,
        "status_tone": "green",
        "beginner_one_liner": f"{cid} 简洁白话说明",
        "today_alert": f"{cid} 今日提醒",
        "summary": f"{cid} 摘要说明",
        "key_metrics": [{"label": "基准指标", "value": "1.50%"}],
        "products": [
            {
                "code": "511360" if cid == "reverse_repo" else f"P{order:03d}",
                "name": f"{cid} 示例产品",
                "metric": "1.50%",
                "fee": "0.20%/年",
                "note": "示例产品备注",
            }
        ],
        "rules_and_redlines": ["严格风控红线"],
    }


def _make_etf(code: str, *, market: str = "a-share", channel: str = "境内场内", gold_locked: bool = False) -> dict:
    return {
        "code": code,
        "name": f"测试指数基金 {code}",
        "market": market,
        "market_label": "中国 A 股",
        "channel": channel,
        "category": "宽基核心",
        "tracking_index": "测试指数",
        "aum": "100 亿元",
        "fee_total_pct": "0.20%",
        "fee_num": 0.2,
        "liquidity": "S 级",
        "yield_or_pe": "PE 12.0x",
        "top_holdings": "测试持仓",
        "premium_status": "normal",
        "premium_note": "折溢价平稳，买前核对盘中参考净值（IOPV）",
        "tax_and_rules": "免印花税",
        "thesis_deep": "核心宽基配置工具",
        "risk_boundary": "红灯防守严控仓位",
        "action_role": "红灯暂停新买" if gold_locked else "红灯稳健底座",
        "otc_feeder": "无",
        "gold_locked": gold_locked,
    }


def _make_dossier(
    market: str,
    code: str,
    name: str,
    *,
    baseline_note: str = "基线参考价 10.00 元；PE 12.0x / 股息率 3.5%。",
    valuation_anchor: str = "PE-TTM 12.0x，股息率 3.5%。",
    shareholder_flow: str = "分红稳健，股息率 3.5%。",
    action_etf: str = "回调分批观察。",
    moat: str = "护城河稳固。",
    updated_at: str = "2026-11-26",
) -> dict:
    return {
        "depth_tier": "core_deep",
        "baseline_note": baseline_note,
        "moat": moat,
        "financials": f"{name} 财务质量稳健。",
        "valuation_anchor": valuation_anchor,
        "shareholder_flow": shareholder_flow,
        "catalysts": f"{name} 年度业绩催化观察。",
        "bear_case": f"{name} 业绩低于预期下行风险。",
        "action_etf": action_etf,
        "market": market,
        "code": code,
        "name": name,
        "updated_at": updated_at,
    }


def _build_clean_fixture(
    root: Path,
    *,
    edition_id: str = "2026-11-27_0730",
    as_of_date: str = "2026-11-27",
) -> None:
    (root / "gold" / "daily").mkdir(parents=True, exist_ok=True)
    (root / "equity" / "state").mkdir(parents=True, exist_ok=True)

    gold_snap = {
        "edition_id": edition_id,
        "as_of_short": f"{as_of_date} 07:55",
        "tier_code": "Tier 0",
        "new_buy_allowed": False,
    }
    (root / "gold" / "data_snapshot.json").write_text(json.dumps(gold_snap, ensure_ascii=False), encoding="utf-8")

    market_state = {
        "edition_id": edition_id,
        "as_of_cst": f"{as_of_date}T07:55:00+08:00",
        "markets": {
            "a_share": {"stock_pool_count": 3},
            "hk_stock": {"stock_pool_count": 2},
            "us_stock": {"stock_pool_count": 1},
        },
        "cross_market_linkages": {
            "ah_premium_radar": {
                "hsahp_index": 138.4,
                "as_of_date": "2026-11-26",
                "benchmarks": [
                    {
                        "name": "中国神华",
                        "a": "601088",
                        "h": "01088.HK",
                        "ah_premium_pct": 50.0,
                        "preferred_channel": "offshore_hk",
                    }
                ],
            }
        },
    }
    (root / "equity" / "state" / "market_state.json").write_text(
        json.dumps(market_state, ensure_ascii=False), encoding="utf-8"
    )

    ma = {
        "edition_id": edition_id,
        "as_of_date": as_of_date,
        "channels": [_make_channel(cid, idx + 1) for idx, cid in enumerate(psd.REQUIRED_MULTI_ASSET_CHANNELS)],
    }
    (root / "equity" / "state" / "multi_asset_channels.json").write_text(
        json.dumps(ma, ensure_ascii=False), encoding="utf-8"
    )

    etfs = [_make_etf("511360"), _make_etf("510300"), _make_etf("02830.HK", market="hk-stock", channel="离岸港交所")]
    etfs.extend(_make_etf(f"51{1000 + i:04d}") for i in range(138))
    eu = {
        "edition_id": edition_id,
        "as_of_date": as_of_date,
        "updated_at": as_of_date,
        "total_etfs": len(etfs),
        "counts_by_market": {"a-share": len(etfs) - 1, "hk-stock": 1},
        "counts_by_channel": {"境内场内": len(etfs) - 1, "离岸港交所": 1},
        "gold_tier0_locked": True,
        "etfs": etfs,
    }
    (root / "equity" / "state" / "etf_universe.json").write_text(
        json.dumps(eu, ensure_ascii=False), encoding="utf-8"
    )

    dossiers = {
        "a-share:601088": _make_dossier(
            "a-share",
            "601088",
            "中国神华",
            baseline_note="基线参考价 53.00 元；PE 19.0x / 股息率 4.0% / AH 溢价 +50.0%。",
            valuation_anchor="PE-TTM 19.0x；AH 溢价 +50.0%（H 股 01088.HK 12.7x）。",
            shareholder_flow="高派息央企标杆，A 股股息率 4.0%。",
            updated_at=as_of_date,
        ),
        "a-share:000333": _make_dossier(
            "a-share",
            "000333",
            "美的集团",
            baseline_note="基线参考价 94.51 元；PE 15.2x / 股息率 4.55%。",
            valuation_anchor="PE-TTM 15.2x，现价实算股息率 4.55%。",
            shareholder_flow="全年分红稳健，股息率 4.55%。",
            updated_at="2026-11-26",
        ),
        "a-share:600547": _make_dossier(
            "a-share",
            "600547",
            "山东黄金",
            baseline_note="黄金红灯停新仓严格 0%。",
            valuation_anchor="总归母市盈率 27.1x，股息率 1.20%。",
            shareholder_flow="股息率 1.20%。",
            action_etf="🔴 高危回避：严禁新买或列为当下底座。",
            updated_at=as_of_date,
        ),
        "hk-stock:01088.HK": _make_dossier(
            "hk-stock",
            "01088.HK",
            "中国神华 H",
            baseline_note="H 股 01088.HK 对应 AH 溢价 +50.0%。",
            valuation_anchor="PE-TTM 12.7x，AH 溢价 +50.0%。",
            shareholder_flow="H 股高息配置参考。",
            updated_at=as_of_date,
        ),
        "hk-stock:06181.HK": _make_dossier(
            "hk-stock",
            "06181.HK",
            "老铺黄金",
            baseline_note="黄金红灯停新仓 0%。",
            valuation_anchor="除权参考价 245.75 港元。",
            shareholder_flow="沽空占比抬升。",
            action_etf="🔴 高危回避：暂不新买、不列为当下底座。",
            updated_at=as_of_date,
        ),
        "us-stock:MSTR": _make_dossier(
            "us-stock",
            "MSTR",
            "微策略",
            baseline_note="截至11/27比特币报 $60,575，浮亏显著。",
            moat="按币价 $60,575 测算持仓浮亏显著。",
            valuation_anchor="mNAV 跌破 1.0x。",
            shareholder_flow="普通股零回购。",
            updated_at="2026-11-26",
        ),
    }
    dd = {
        "edition_id": edition_id,
        "as_of_date": as_of_date,
        "updated_at": as_of_date,
        "total_stocks": len(dossiers),
        "core_deep_count": len(dossiers),
        "standard_deep_count": 0,
        "dossiers": dossiers,
    }
    (root / "equity" / "state" / "deep_dossiers.json").write_text(
        json.dumps(dd, ensure_ascii=False), encoding="utf-8"
    )


class PatchStateDbsGuardsTests(unittest.TestCase):
    def test_live_library_label_distinguishes_cutoff_date_from_weekend_edition(self):
        self.assertEqual(
            psd._live_edition_as_of_label("2026-11-28_1800", "2026-11-28T22:25:00+08:00"),
            "2026年11月28日（周六）22:25 周末晚刊",
        )
        self.assertEqual(
            psd._live_edition_as_of_label("2026-11-28_1800", "2026-11-29T00:00:00+08:00"),
            "2026年11月29日（周日）00:00 周末晚刊",
        )

    def test_live_production_etf_floor_preserves_historical_and_small_pools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)
            state_dir = root / "equity/state"
            ma = json.loads((state_dir / "multi_asset_channels.json").read_text(encoding="utf-8"))
            eu = json.loads((state_dir / "etf_universe.json").read_text(encoding="utf-8"))
            dd = json.loads((state_dir / "deep_dossiers.json").read_text(encoding="utf-8"))

            for edition, pool, should_fail in (
                ("2026-11-28_0730", 231, False),
                ("2026-11-28_1130", 231, True),
                ("2026-12-01_0730", 231, True),
                ("2026-12-01_0730", 6, False),
            ):
                with self.subTest(edition=edition, pool=pool):
                    errors = psd._validate_merged_equity_dbs(
                        ma, eu, dd, edition_id=edition, gold_tier0_active=True, expected_pool=pool,
                        as_of_date=edition[:10],
                    )
                    self.assertEqual(any("ETF count 141 < 181" in error for error in errors), should_fail)

    def test_gold_base_negation_regex_handles_compound_negations_and_rejects_positive(self):
        for negated in (
            "严禁新买或列为",
            "暂不新买、不列为",
            "严禁买入或标为",
            "严禁新买、加仓或列为",
            "禁止列为",
            "不可标为",
        ):
            with self.subTest(negated=negated):
                self.assertIsNotNone(psd.GOLD_BASE_NEGATION_RE.search(negated))

        for positive in (
            "建议列为",
            "作为",
            "推荐标为",
            "暂不新买但可列为",
            "优先配置并列为",
        ):
            with self.subTest(positive=positive):
                self.assertIsNone(psd.GOLD_BASE_NEGATION_RE.search(positive))

        # End-to-end validation through _validate_merged_equity_dbs
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)
            ma = json.loads((root / "equity/state/multi_asset_channels.json").read_text("utf-8"))
            eu = json.loads((root / "equity/state/etf_universe.json").read_text("utf-8"))
            dd = json.loads((root / "equity/state/deep_dossiers.json").read_text("utf-8"))
            ms = json.loads((root / "equity/state/market_state.json").read_text("utf-8"))

            # Fixture uses "严禁新买或列为当下底座" and "暂不新买、不列为当下底座" -> 0 errors
            dd["dossiers"]["a-share:600547"]["action_etf"] = "🔴 高危回避：严禁买入或标为绿色底座。"
            errs = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(errs, [])

            # Positive base endorsement must still be rejected
            dd["dossiers"]["a-share:600547"]["action_etf"] = "严禁追高，但可列为当下底座。"
            errs_bad = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertTrue(any("Gold Tier-0 互斥冲突" in e for e in errs_bad))

    def test_actionable_unknown_key_errors_include_sorted_allowed_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)

            # 1. apply_equity_patch top-level unknown key
            patch_path = root / "equity/state/_edition_patch.json"
            patch_path.write_text(json.dumps({"edition_id": "2026-11-27_0730", "bogus": 1}), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                psd.apply_equity_patch(root, dry_run=True)
            self.assertIn("allowed:", str(ctx.exception))
            self.assertIn("'multi_asset_channels'", str(ctx.exception))

            # 2. _merge_multi_asset unknown key
            patch_path.write_text(
                json.dumps({"edition_id": "2026-11-27_0730", "multi_asset_channels": {"channels": {}}}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                psd.apply_equity_patch(root, dry_run=True)
            self.assertIn("allowed: ['channels_patch', 'top_level_updates']", str(ctx.exception))

            # 3. _merge_etf_universe unknown key
            patch_path.write_text(
                json.dumps({"edition_id": "2026-11-27_0730", "etf_universe": {"etfs": []}}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                psd.apply_equity_patch(root, dry_run=True)
            self.assertIn("allowed: ['etfs_remove', 'etfs_upsert', 'top_level_updates']", str(ctx.exception))

            # 4. _merge_deep_dossiers unknown key
            patch_path.write_text(
                json.dumps({"edition_id": "2026-11-27_0730", "deep_dossiers": {"dossiers": {}}}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx:
                psd.apply_equity_patch(root, dry_run=True)
            self.assertIn("allowed: ['dossiers_patch', 'top_level_updates']", str(ctx.exception))

            # 5. prepend_gold_ledgers unknown key
            gold_patch = root / "gold/daily/_ledger_patch.json"
            gold_patch.write_text(json.dumps({"edition_id": "2026-11-27_0730", "wrong_key": "x"}), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                psd.prepend_gold_ledgers(root, dry_run=True)
            self.assertIn("allowed:", str(ctx.exception))
            self.assertIn("'changelog_entry_md'", str(ctx.exception))

            # 6. prepend_equity_audit unknown key
            audit_patch = root / "equity/state/_audit_patch.json"
            audit_patch.write_text(json.dumps({"edition_id": "2026-11-27_0730", "wrong": "x"}), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                psd.prepend_equity_audit(root, dry_run=True)
            self.assertIn("allowed: ['edition_id', 'entry_md', 'note']", str(ctx.exception))

    def test_relative_date_tense_drift_and_4digit_hk_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)
            ma = json.loads((root / "equity/state/multi_asset_channels.json").read_text("utf-8"))
            eu = json.loads((root / "equity/state/etf_universe.json").read_text("utf-8"))
            dd = json.loads((root / "equity/state/deep_dossiers.json").read_text("utf-8"))
            ms = json.loads((root / "equity/state/market_state.json").read_text("utf-8"))

            # Valid tense & 5-digit HK passes
            ma["channels"][0]["today_alert"] = "今日（11/27）操作，明日11/28复核，昨日11/26已封账，参考 00700.HK。"
            errs_ok = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(errs_ok, [])

            # Stale 明日 11/27, 今日(11/26), 昨日11/25, and bare 4-digit 2830.HK all fail
            ma["channels"][0]["today_alert"] = "明日 11/27 除净"
            eu["etfs"][0]["premium_note"] = "今日(11/26)跟踪 2830.HK 盘中参考净值（IOPV）"
            dd["dossiers"]["a-share:000333"]["catalysts"] = "昨日11/25 公告回顾"
            errs = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            joined = "\n".join(errs)
            self.assertIn("明日 11/27", joined)
            self.assertIn("今日(11/26)", joined)
            self.assertIn("昨日11/25", joined)
            self.assertIn("2830.HK", joined)

    def test_high_risk_qdii_creation_redemption_and_bare_iopv_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)
            ma = json.loads((root / "equity/state/multi_asset_channels.json").read_text("utf-8"))
            eu = json.loads((root / "equity/state/etf_universe.json").read_text("utf-8"))
            dd = json.loads((root / "equity/state/deep_dossiers.json").read_text("utf-8"))
            ms = json.loads((root / "equity/state/market_state.json").read_text("utf-8"))

            # High-risk QDII claiming 恢复申赎 without 仅恢复赎回 -> reject
            eu["etfs"][1]["premium_status"] = "high_risk"
            eu["etfs"][1]["premium_note"] = "溢价约 +9%，11/27恢复申赎，溢价超 2% 禁追。"
            # Bare IOPV -> reject
            eu["etfs"][2]["premium_note"] = "买前必核实时 IOPV，溢价超 2% 不追。"

            errs = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            joined = "\n".join(errs)
            self.assertIn("恢复申赎", joined)
            self.assertIn("仅恢复赎回", joined)
            self.assertIn("bare 'IOPV'", joined)

            # Restricted note (暂停申购) with 恢复申赎 also rejected even when watch
            eu["etfs"][1]["premium_status"] = "watch"
            eu["etfs"][1]["premium_note"] = "暂停申购期间勿误读为恢复申赎"
            eu["etfs"][2]["premium_note"] = "买前核对盘中参考净值（IOPV），溢价超 2% 不追。"
            errs_watch = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(len(errs_watch), 1)
            self.assertIn("恢复申赎", errs_watch[0])

            # Clarifying 仅恢复赎回 passes when action_role == 高危回避!
            eu["etfs"][1]["premium_status"] = "high_risk"
            eu["etfs"][1]["action_role"] = "高危回避"
            eu["etfs"][1]["premium_note"] = "暂停申购仅恢复赎回（不开放申购，勿误读为恢复申赎）"
            errs_pass = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(errs_pass, [])

            # high_risk with action_role != 高危回避 must be rejected!
            eu["etfs"][1]["action_role"] = "分歧观察"
            errs_role = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertTrue(any("高危回避" in e and "510300" in e for e in errs_role))

            # 盘中净值 is an accepted IOPV gloss
            eu["etfs"][1]["action_role"] = "高危回避"
            eu["etfs"][2]["premium_note"] = "买前核对盘中净值（IOPV），溢价超 2% 不追。"
            errs_iopv_ok = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(errs_iopv_ok, [])

            # OTC suspended note forbids unqualified 零溢价场外联接 unless 限购|暂停 disclosed (both word orders)
            for susp_note in (
                "溢价偏高且场外联接暂停申购，切忌追高。",
                "自 2026-11-04 起持续暂停申购（场外/一级申购仍暂停）。",
            ):
                with self.subTest(susp_note=susp_note):
                    eu["etfs"][1]["premium_note"] = susp_note
                    eu["etfs"][1]["otc_feeder"] = "零溢价场外联接：050025(A) / 006075(C)"
                    errs_otc = psd._validate_merged_equity_dbs(
                        ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                        as_of_date="2026-11-27", market_state=ms,
                    )
                    self.assertTrue(any("零溢价场外联接" in e and "510300" in e for e in errs_otc))

            eu["etfs"][1]["otc_feeder"] = "零溢价场外联接：050025(A)（当前暂停申购）"
            errs_otc_ok = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(errs_otc_ok, [])

    def test_ah_benchmark_0_6pp_and_intra_dossier_dividend_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)
            ma = json.loads((root / "equity/state/multi_asset_channels.json").read_text("utf-8"))
            eu = json.loads((root / "equity/state/etf_universe.json").read_text("utf-8"))
            dd = json.loads((root / "equity/state/deep_dossiers.json").read_text("utf-8"))
            ms = json.loads((root / "equity/state/market_state.json").read_text("utf-8"))

            # Within ±0.6pp (50.5% vs 50.0%) passes
            dd["dossiers"]["a-share:601088"]["baseline_note"] = "基线 53.00 元；股息率 4.0% / AH 溢价 +50.5%。"
            errs_ok = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(errs_ok, [])

            # Drift 0.8pp (50.8% vs 50.0%) fails global check
            dd["dossiers"]["a-share:601088"]["baseline_note"] = "基线 53.00 元；股息率 4.0% / AH 溢价 +50.8%。"
            errs_ah = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertTrue(any("0.6pp" in e and "601088" in e for e in errs_ah))

            # Reset AH to exact +50.0%, test intra-dossier dividend guard (> 0.15 fails)
            dd["dossiers"]["a-share:601088"]["baseline_note"] = "基线 53.00 元；股息率约 3.8% / AH 溢价 +50.0%。"
            errs_div = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertTrue(any("dividend yield mismatch" in e and "601088" in e for e in errs_div))

            # Tax-qualified / interim / historical dividend mentions within ±10 chars are ignored
            dd["dossiers"]["a-share:601088"]["baseline_note"] = (
                "基线 53.00 元；股息率 4.0%（税后股息率 3.2%、中期股息率 2.1%、原股息率 3.6%）/ AH 溢价 +50.0%。"
            )
            errs_qual = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(errs_qual, [])

            # Twin check inside _merge_deep_dossiers also enforces ±0.6pp
            dd["dossiers"]["hk-stock:01088.HK"]["baseline_note"] = "H 股对应 AH 溢价 +50.8%。"
            with self.assertRaisesRegex(ValueError, "0.6pp"):
                psd._merge_deep_dossiers(
                    dd,
                    {"deep_dossiers": {"dossiers_patch": {"a-share:601088": {"baseline_note": "更新 AH 溢价 +50.0%。"}}}},
                    "2026-11-27_0730",
                    "2026-11-27",
                    market_state=ms,
                )

    def test_btc_usd_sibling_token_drift_on_dossier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)
            dd = json.loads((root / "equity/state/deep_dossiers.json").read_text("utf-8"))

            # Patch baseline_note from $60,575 -> $60,357 while leaving moat at $60,575 -> rejected!
            with self.assertRaisesRegex(ValueError, r"\$60,575"):
                psd._merge_deep_dossiers(
                    dd,
                    {
                        "deep_dossiers": {
                            "dossiers_patch": {
                                "us-stock:MSTR": {
                                    "baseline_note": "截至11/27比特币报 $60,357，浮亏加深。",
                                }
                            }
                        }
                    },
                    "2026-11-27_0730",
                    "2026-11-27",
                )

            # Updating both baseline_note and moat together passes!
            merged, stats = psd._merge_deep_dossiers(
                dd,
                {
                    "deep_dossiers": {
                        "dossiers_patch": {
                            "us-stock:MSTR": {
                                "baseline_note": "截至11/27比特币报 $60,357，浮亏加深。",
                                "moat": "按币价 $60,357 测算持仓浮亏加深。",
                            }
                        }
                    }
                },
                "2026-11-27_0730",
                "2026-11-27",
            )
            self.assertEqual(stats["stocks_patched"], 1)
            self.assertIn("$60,357", merged["dossiers"]["us-stock:MSTR"]["moat"])

            # 6-digit BTC ($100,000+) sibling token drift is also caught!
            dd["dossiers"]["us-stock:MSTR"]["baseline_note"] = "比特币突破 $105,400。"
            dd["dossiers"]["us-stock:MSTR"]["moat"] = "按币价 $105,400 测算浮盈扩大。"
            with self.assertRaisesRegex(ValueError, r"\$105,400"):
                psd._merge_deep_dossiers(
                    dd,
                    {
                        "deep_dossiers": {
                            "dossiers_patch": {
                                "us-stock:MSTR": {
                                    "baseline_note": "比特币回落至 $102,800。",
                                }
                            }
                        }
                    },
                    "2026-11-27_0730",
                    "2026-11-27",
                )

    def test_ah_sign_flip_historical_context_and_financials_dividend_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)
            ma = json.loads((root / "equity/state/multi_asset_channels.json").read_text("utf-8"))
            eu = json.loads((root / "equity/state/etf_universe.json").read_text("utf-8"))
            dd = json.loads((root / "equity/state/deep_dossiers.json").read_text("utf-8"))
            ms = json.loads((root / "equity/state/market_state.json").read_text("utf-8"))

            # Negative AH benchmark (-21.1%): unsigned 倒挂 / A折H / AH 折价 negate cleanly to -21.1%
            ms["cross_market_linkages"]["ah_premium_radar"]["benchmarks"][0]["ah_premium_pct"] = -21.1
            dd["dossiers"]["a-share:601088"]["baseline_note"] = (
                "AH 倒挂 21.1%，A折H 21.1%，历史中枢 AH 溢价 +35.0%，过去五年 AH 溢价 30.0%。股息率 4.0%。"
            )
            dd["dossiers"]["a-share:601088"]["valuation_anchor"] = "AH 折价 21.1%（历史均值 AH 溢价 +25.0%）。"
            dd["dossiers"]["hk-stock:01088.HK"]["baseline_note"] = "H 股相对 A 股呈 AH 倒挂 21.1%。"
            dd["dossiers"]["hk-stock:01088.HK"]["valuation_anchor"] = "当前 A折H 21.1%。"

            errs_ok = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(errs_ok, [])

            # Unsigned 倒挂 with drifted magnitude (18.0% -> -18.0% vs -21.1%) MUST fail!
            dd["dossiers"]["a-share:601088"]["baseline_note"] = "AH 倒挂 18.0%，股息率 4.0%。"
            errs_drift = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertTrue(any("AH premium" in e and "601088" in e for e in errs_drift))

            # Reset AH; verify financials dividend mismatch IS caught, while expanded qualifiers are excluded
            dd["dossiers"]["a-share:601088"]["baseline_note"] = "AH 倒挂 21.1%，股息率 4.0%。"
            dd["dossiers"]["a-share:601088"]["financials"] = "财务稳健，股息率 3.2%。"
            errs_fin = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertTrue(any("dividend yield mismatch" in e and "financials" in e for e in errs_fin))

            # Expanded qualifiers (行业/均值/中证红利/H股/净股息/同业/目标) are excluded
            dd["dossiers"]["a-share:601088"]["financials"] = (
                "财务稳健，低于中证红利股息率 5.2%、高于行业均值股息率 2.5%，H股股息率 6.0%，净股息率 3.2%。"
            )
            errs_fin_ok = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(errs_fin_ok, [])

    def test_dec1_historical_ctx_cross_db_fee_products_scoping_and_etf_updated_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root, edition_id="2026-12-01_0730", as_of_date="2026-12-01")
            ma = json.loads((root / "equity/state/multi_asset_channels.json").read_text("utf-8"))
            eu = json.loads((root / "equity/state/etf_universe.json").read_text("utf-8"))
            dd = json.loads((root / "equity/state/deep_dossiers.json").read_text("utf-8"))
            ms = json.loads((root / "equity/state/market_state.json").read_text("utf-8"))

            # 1. Dec 1 HISTORICAL_CTX_RE: 12/01 and 1/5 recognized as historical context (no false sibling drift)
            self.assertIsNotNone(psd.HISTORICAL_CTX_RE.search("12/01收+2.50%"))
            self.assertIsNotNone(psd.HISTORICAL_CTX_RE.search("1/5报-1.20%"))
            self.assertIsNotNone(psd.HISTORICAL_CTX_RE.search("01/05报-1.20%"))
            self.assertIsNone(psd.HISTORICAL_CTX_RE.search("13/01非法月份"))

            ma["channels"][0]["summary"] = "12/01测算收益率 +2.50%，稳健运作。"
            ma["channels"][0]["today_alert"] = "当前收益率 +2.50%。"
            # Add two products sharing +3.50% to verify products_upsert scoping avoids unrelated product FP
            ma["channels"][0]["products"] = [
                {
                    "code": "511360",
                    "name": "短融ETF",
                    "metric": "+3.50%",
                    "fee": "管理费0.15%+托管0.05%=综合0.20%",
                    "note": "产品A当前+3.50%",
                },
                {
                    "code": "510300",
                    "name": "沪深300ETF",
                    "metric": "+3.50%",
                    "fee": "0.20%/年",
                    "note": "无关产品B仍为+3.50%",
                },
            ]
            # Updating today_alert +2.50% -> +2.10% passes because summary has 12/01 historical context!
            # Updating product 511360 (both metric & note) from +3.50% -> +2.80% MUST NOT flag unrelated product 510300!
            merged_ma, _ = psd._merge_multi_asset(
                ma,
                {
                    "multi_asset_channels": {
                        "channels_patch": {
                            "reverse_repo": {
                                "today_alert": "当前收益率 +2.10%。",
                                "products_upsert": [
                                    {"code": "511360", "metric": "+2.80%", "note": "产品A更新至+2.80%"},
                                ],
                            }
                        }
                    }
                },
                "2026-12-01_0730",
                "2026-12-01",
            )
            # Cross-DB fee check: "管理费0.15%+托管0.05%=综合0.20%" matches parsed_fees[-1]==0.20% cleanly!
            errs_fee = psd._validate_merged_equity_dbs(
                merged_ma, eu, dd, edition_id="2026-12-01_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-12-01", market_state=ms,
            )
            self.assertEqual(errs_fee, [])

            # However, updating 511360's metric without updating 511360's own stale note STILL fails!
            with self.assertRaisesRegex(ValueError, r"products\[0\]\.note"):
                psd._merge_multi_asset(
                    ma,
                    {
                        "multi_asset_channels": {
                            "channels_patch": {
                                "reverse_repo": {
                                    "products_upsert": [{"code": "511360", "metric": "+2.80%"}],
                                }
                            }
                        }
                    },
                    "2026-12-01_0730",
                    "2026-12-01",
                )

            # 2. Per-ETF updated_at set ONLY on touched ETFs + --inspect etf-freshness
            merged_eu, eu_stats = psd._merge_etf_universe(
                eu,
                {
                    "etf_universe": {
                        "etfs_upsert": [
                            {"code": "510300", "aum": "2,300 亿元"},
                        ]
                    }
                },
                "2026-12-01_0730",
                "2026-12-01",
            )
            self.assertEqual(eu_stats["etfs_updated"], 1)
            by_code = {e["code"]: e for e in merged_eu["etfs"]}
            self.assertEqual(by_code["510300"].get("updated_at"), "2026-12-01")
            self.assertNotIn("updated_at", by_code["511360"])

            (root / "equity/state/etf_universe.json").write_text(
                json.dumps(merged_eu, ensure_ascii=False), encoding="utf-8"
            )
            freshness = psd.inspect_state_dbs(root, "etf-freshness")
            self.assertEqual(freshness["latest_updated_at"], "2026-12-01")
            self.assertEqual(freshness["recently_updated_codes"], ["510300"])
            self.assertEqual(freshness["updated_at_histogram"]["2026-12-01"], 1)
            self.assertEqual(freshness["updated_at_histogram"]["unset"], len(merged_eu["etfs"]) - 1)

            # 3. BANNED_INTERNAL_RE catches svg_geometry.py, _rollover_patch.json, _archive_patch.json
            for banned in ("svg_geometry.py", "_rollover_patch.json", "_archive_patch.json"):
                with self.subTest(banned=banned):
                    self.assertTrue(psd.BANNED_INTERNAL_RE.search(f"禁止提及 {banned}"))

    def test_etf_orthogonal_asset_class_and_region_apply_and_reject_invalid_enums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)

            # Populate valid orthogonal asset_class & region on all fixture ETFs while keeping _make_etf() legacy-compat
            eu_path = root / "equity/state/etf_universe.json"
            eu = json.loads(eu_path.read_text(encoding="utf-8"))
            for item in eu["etfs"]:
                if item["code"] == "511360":
                    item["asset_class"] = "cash_mmf"
                    item["region"] = "cn"
                elif item["code"] == "02830.HK":
                    item["asset_class"] = "equity"
                    item["region"] = "hk"
                else:
                    item["asset_class"] = "equity"
                    item["region"] = "cn"
            eu["counts_by_asset_class"] = {"cash_mmf": 1, "equity": len(eu["etfs"]) - 1}
            eu["counts_by_region"] = {"cn": len(eu["etfs"]) - 1, "hk": 1}
            eu_path.write_text(json.dumps(eu, ensure_ascii=False), encoding="utf-8")

            patch_path = root / "equity/state/_edition_patch.json"
            good_patch = {
                "edition_id": "2026-11-27_0730",
                "as_of_date": "2026-11-27",
                "gold_tier0_locked": True,
                "etf_universe": {
                    "etfs_upsert": [
                        {"code": "510300", "asset_class": "fixed_income", "region": "us"},
                        {"code": "02830.HK", "asset_class": "reits", "region": "jp"},
                    ]
                },
            }
            patch_path.write_text(json.dumps(good_patch, ensure_ascii=False), encoding="utf-8")
            out_ok, err_ok = StringIO(), StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(out_ok), redirect_stderr(err_ok):
                rc_ok = psd.main(["--apply"])
            self.assertEqual(rc_ok, 0, err_ok.getvalue())
            self.assertFalse(patch_path.exists())

            eu_after = json.loads(eu_path.read_text(encoding="utf-8"))
            by_code = {e["code"]: e for e in eu_after["etfs"]}
            self.assertEqual(by_code["510300"]["asset_class"], "fixed_income")
            self.assertEqual(by_code["510300"]["region"], "us")
            self.assertEqual(by_code["02830.HK"]["asset_class"], "reits")
            self.assertEqual(by_code["02830.HK"]["region"], "jp")
            self.assertEqual(
                eu_after["counts_by_asset_class"],
                {"cash_mmf": 1, "fixed_income": 1, "reits": 1, "equity": len(eu_after["etfs"]) - 3},
            )
            self.assertEqual(
                eu_after["counts_by_region"],
                {"cn": len(eu_after["etfs"]) - 2, "us": 1, "jp": 1},
            )

            # Invalid asset_class & invalid region must both be rejected atomically with zero file mutation
            before_bytes = eu_path.read_bytes()
            for field_name, bad_val in (("asset_class", "crypto"), ("region", "mars")):
                with self.subTest(field_name=field_name, bad_val=bad_val):
                    bad_patch = {
                        "edition_id": "2026-11-27_0730",
                        "as_of_date": "2026-11-27",
                        "gold_tier0_locked": True,
                        "etf_universe": {
                            "etfs_upsert": [{"code": "510300", field_name: bad_val}]
                        },
                    }
                    patch_path.write_text(json.dumps(bad_patch, ensure_ascii=False), encoding="utf-8")
                    out_bad, err_bad = StringIO(), StringIO()
                    with patch.object(psd, "REPO_ROOT", root), redirect_stdout(out_bad), redirect_stderr(err_bad):
                        rc_bad = psd.main(["--apply"])
                    self.assertNotEqual(rc_bad, 0)
                    self.assertIn(field_name, err_bad.getvalue())
                    self.assertEqual(eu_path.read_bytes(), before_bytes)
                    patch_path.unlink()

    def test_apply_rejects_qdii_name_prefix_strip_and_gold_class_unlocked_under_tier0(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)

            # Seed canonical QDII-prefixed name on Channel 08 & orthogonal ETF fields
            ma_path = root / "equity/state/multi_asset_channels.json"
            ma = json.loads(ma_path.read_text(encoding="utf-8"))
            for ch in ma["channels"]:
                if ch["id"] == "qdii_mrf":
                    ch["name"] = "QDII 跨境基金、香港互认与理财通"
            ma_path.write_text(json.dumps(ma, ensure_ascii=False), encoding="utf-8")

            eu_path = root / "equity/state/etf_universe.json"
            eu = json.loads(eu_path.read_text(encoding="utf-8"))
            for item in eu["etfs"]:
                if item["code"] == "511360":
                    item["asset_class"] = "cash_mmf"
                    item["region"] = "cn"
                elif item["code"] == "02830.HK":
                    item["asset_class"] = "equity"
                    item["region"] = "hk"
                else:
                    item["asset_class"] = "equity"
                    item["region"] = "cn"
            eu["counts_by_asset_class"] = {"cash_mmf": 1, "equity": len(eu["etfs"]) - 1}
            eu["counts_by_region"] = {"cn": len(eu["etfs"]) - 1, "hk": 1}
            eu_path.write_text(json.dumps(eu, ensure_ascii=False), encoding="utf-8")

            patch_path = root / "equity/state/_edition_patch.json"
            ma_before = ma_path.read_bytes()
            eu_before = eu_path.read_bytes()

            # (a) Stripping "QDII" prefix from Channel qdii_mrf.name must be rejected atomically
            strip_qdii_patch = {
                "edition_id": "2026-11-27_0730",
                "as_of_date": "2026-11-27",
                "gold_tier0_locked": True,
                "multi_asset_channels": {
                    "channels_patch": {
                        "qdii_mrf": {
                            "name": "场内外跨境基金、香港互认与理财通",
                        }
                    }
                },
            }
            patch_path.write_text(json.dumps(strip_qdii_patch, ensure_ascii=False), encoding="utf-8")
            out_a, err_a = StringIO(), StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(out_a), redirect_stderr(err_a):
                rc_a = psd.main(["--apply"])
            self.assertNotEqual(rc_a, 0)
            self.assertIn("qdii_mrf", err_a.getvalue())
            self.assertIn("QDII", err_a.getvalue())
            self.assertEqual(ma_path.read_bytes(), ma_before)
            patch_path.unlink()

            # (b) Setting asset_class="gold" with gold_locked=False under Gold Tier-0 lock must be rejected atomically
            gold_unlocked_patch = {
                "edition_id": "2026-11-27_0730",
                "as_of_date": "2026-11-27",
                "gold_tier0_locked": True,
                "etf_universe": {
                    "etfs_upsert": [
                        {
                            "code": "510300",
                            "asset_class": "gold",
                            "gold_locked": False,
                            "action_role": "红灯暂停新买",
                        }
                    ]
                },
            }
            patch_path.write_text(json.dumps(gold_unlocked_patch, ensure_ascii=False), encoding="utf-8")
            out_b, err_b = StringIO(), StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(out_b), redirect_stderr(err_b):
                rc_b = psd.main(["--apply"])
            self.assertNotEqual(rc_b, 0)
            self.assertIn("gold_locked", err_b.getvalue())
            self.assertIn("510300", err_b.getvalue())
            self.assertEqual(eu_path.read_bytes(), eu_before)
            patch_path.unlink()

            # (c) Positive control: QDII-prefixed name + asset_class="gold" paired with gold_locked=True passes cleanly
            valid_patch = {
                "edition_id": "2026-11-27_0730",
                "as_of_date": "2026-11-27",
                "gold_tier0_locked": True,
                "multi_asset_channels": {
                    "channels_patch": {
                        "qdii_mrf": {
                            "name": "QDII 跨境基金（更新版）、香港互认与理财通",
                        }
                    }
                },
                "etf_universe": {
                    "etfs_upsert": [
                        {
                            "code": "510300",
                            "asset_class": "gold",
                            "gold_locked": True,
                            "action_role": "红灯暂停新买",
                        }
                    ]
                },
            }
            patch_path.write_text(json.dumps(valid_patch, ensure_ascii=False), encoding="utf-8")
            out_ok, err_ok = StringIO(), StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(out_ok), redirect_stderr(err_ok):
                rc_ok = psd.main(["--apply"])
            self.assertEqual(rc_ok, 0, err_ok.getvalue())
            self.assertFalse(patch_path.exists())


class AtomicRsiAuditAndInspectTests(unittest.TestCase):
    def test_interrupted_multi_file_write_restores_all_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            existing = root / "first.json"
            created = root / "second.json"
            last = root / "last.json"
            existing.write_bytes(b"first old")
            last.write_bytes(b"last old")
            real_replace = psd.os.replace

            def interrupt_after_creating(src, dest):
                real_replace(src, dest)
                if dest == created:
                    raise KeyboardInterrupt

            with patch.object(psd.os, "replace", side_effect=interrupt_after_creating):
                with self.assertRaises(KeyboardInterrupt):
                    psd._atomic_write_transaction(
                        [(existing, b"first new"), (created, b"second new"), (last, b"last new")]
                    )

            self.assertEqual(existing.read_bytes(), b"first old")
            self.assertFalse(created.exists())
            self.assertEqual(last.read_bytes(), b"last old")
            self.assertEqual(set(root.iterdir()), {existing, last})

    def test_killed_archive_transaction_recovers_before_retry_reads_the_patch(self):
        child = """
import os
from pathlib import Path
import signal
import sys
from scripts import patch_state_dbs as patcher

root, mode = Path(sys.argv[1]), sys.argv[2]
real_replace, real_unlink = os.replace, Path.unlink

def replace(source, target):
    real_replace(source, target)
    if mode == "rename" and target.name == "CHANGELOG_2026_11.md":
        os.kill(os.getpid(), signal.SIGKILL)

def unlink(target, *args, **kwargs):
    real_unlink(target, *args, **kwargs)
    if mode == "unlink" and target.name == "_archive_patch.json":
        os.kill(os.getpid(), signal.SIGKILL)

os.replace, Path.unlink = replace, unlink
patcher.archive_gold_ledgers(root)
"""
        for crash_point in ("rename", "unlink"):
            with self.subTest(crash_point=crash_point), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp).resolve()
                subprocess.run(["git", "init", "-q", str(root)], check=True)
                daily = root / "gold" / "daily"
                daily.mkdir(parents=True)
                original = {
                    "CHANGELOG.md": b'# Changes\n\n---\n\n<!-- GOLD_EDITION_CHANGELOG {"edition_id":"2026-11-27_0730"} -->\n',
                    "AUDIT_LOG.md": b'# Audit\n\n---\n\n<!-- GOLD_EDITION_REVIEW {"edition_id":"2026-11-27_0730"} -->\n',
                }
                for name, data in original.items():
                    (daily / name).write_bytes(data)
                    (daily / name).chmod(0o600)
                patch_file = daily / "_archive_patch.json"
                patch_file.write_text('{"archive_period":"2026_11"}', encoding="utf-8")
                patch_file.chmod(0o600)

                result = subprocess.run(
                    [sys.executable, "-B", "-c", child, str(root), crash_point],
                    check=False, capture_output=True, timeout=10,
                )
                self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr.decode())
                journal = root / ".git" / state_transaction.JOURNAL_NAME
                self.assertEqual(stat.S_IMODE(journal.stat().st_mode), 0o600)
                with self.assertRaisesRegex(RuntimeError, "needs recovery"):
                    psd.archive_gold_ledgers(root, dry_run=True)
                self.assertTrue(journal.exists())

                if crash_point == "rename":
                    partially_created = daily / "archive" / "CHANGELOG_2026_11.md"
                    self.assertTrue(partially_created.exists())
                    self.assertFalse((daily / "archive" / "AUDIT_LOG_2026_11.md").exists())
                    self.assertTrue(patch_file.exists())
                    partially_created.write_bytes(b"Manual edit after interruption")
                    with self.assertRaisesRegex(ValueError, "bytes differ from the recorded transaction"):
                        psd.archive_gold_ledgers(root)
                    self.assertEqual(partially_created.read_bytes(), b"Manual edit after interruption")
                    self.assertTrue(journal.exists())
                    partially_created.write_bytes(original["CHANGELOG.md"])
                else:
                    self.assertFalse(patch_file.exists())
                    with state_transaction.state_write_lock(root):
                        self.assertEqual(patch_file.read_text(encoding="utf-8"), '{"archive_period":"2026_11"}')
                        self.assertEqual(stat.S_IMODE(patch_file.stat().st_mode), 0o600)
                        self.assertEqual((daily / "CHANGELOG.md").read_bytes(), original["CHANGELOG.md"])
                        self.assertFalse(any((daily / "archive").iterdir()))

                self.assertTrue(psd.archive_gold_ledgers(root)["patch_deleted"])
                self.assertFalse(patch_file.exists())
                self.assertFalse(journal.exists())
                self.assertFalse(list(daily.rglob("*.tmp")))
                for name, contents in original.items():
                    archived = daily / "archive" / f"{Path(name).stem}_2026_11.md"
                    self.assertEqual(archived.read_bytes(), contents)
                    self.assertEqual(stat.S_IMODE((daily / name).stat().st_mode), 0o600)

    def test_concurrent_writers_hold_the_lock_from_read_until_patch_consumption(self):
        child = """
from pathlib import Path
import sys
from scripts import patch_state_dbs as patcher

root, pause = Path(sys.argv[1]), sys.argv[2] == "pause"
if pause:
    read = patcher._read_json_obj
    def wait_before_read(path, label):
        print("LOCKED", flush=True)
        sys.stdin.readline()
        return read(path, label)
    patcher._read_json_obj = wait_before_read
else:
    print("STARTED", flush=True)
try:
    patcher.prepend_equity_audit(root)
except ValueError as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            state = root / "equity" / "state"
            state.mkdir(parents=True)
            ledger = state / "audit_ledger.md"
            ledger.write_text("# Audit\n\n---\n\n## Existing entry\n", encoding="utf-8")
            (state / "_audit_patch.json").write_text(json.dumps({
                "edition_id": "2026-11-27_1800",
                "entry_md": "## 2026-11-27 18:10 CST · `2026-11-27_1800`\n\n- Added entry",
            }), encoding="utf-8")
            command = [sys.executable, "-B", "-c", child, str(root)]
            with subprocess.Popen(
                [*command, "pause"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            ) as first:
                try:
                    self.assertEqual(first.stdout.readline().strip(), "LOCKED")
                    with subprocess.Popen(
                        [*command, "go"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    ) as second:
                        try:
                            self.assertEqual(second.stdout.readline().strip(), "STARTED")
                            with self.assertRaises(subprocess.TimeoutExpired):
                                second.wait(timeout=0.15)
                            _, error = first.communicate("\n", timeout=10)
                            self.assertEqual(first.returncode, 0, error)
                            _, error = second.communicate(timeout=10)
                            self.assertEqual(second.returncode, 1)
                            self.assertIn("Missing required JSON file", error)
                        finally:
                            if second.poll() is None:
                                second.kill()
                finally:
                    if first.poll() is None:
                        first.kill()
            self.assertEqual(ledger.read_text(encoding="utf-8").count("Added entry"), 1)
            self.assertEqual(set(root.iterdir()), {root / "equity"})

    def test_live_policy_calendar_validates_publication_and_schedule_times(self):
        as_of = "2026-12-31T23:59:00+08:00"
        edition = "2026-12-31_1800"
        brief = {
            "date_cst": "2026-12-31",
            "time_cst": "23:59",
            "region": "US",
            "category": "macro_data",
            "impact_tier": "P1",
            "authority": "美国劳工统计局",
            "headline": "公布就业数据",
            "summary": "初值较上期改善。",
            "market_impact": "关注债券利率。",
            "affected_markets": ["us_stock"],
            "source_url": "https://www.bls.gov/news.release/empsit.htm",
            "home_featured": True,
        }
        event = {
            "event_id": "employment",
            "date_cst": "2027-01-15",
            "end_date_cst": "2027-01-15",
            "date_precision": "exact",
            "time_cst": "21:30",
            "region": "US",
            "category": "macro_data",
            "impact_tier": "P1",
            "title": "公布就业数据",
            "affected_markets": ["us_stock"],
            "expected_consensus": "增速保持稳定。",
            "market_transmission": "就业影响债券利率。",
            "watch_triggers": {"upside_bull": "就业改善。", "downside_bear": "就业回落。"},
            "pre_event_stance": "保持当前风险上限。",
            "source_url": "https://www.bls.gov/schedule/news_release/empsit.htm",
            "monitor_window_min": 60,
        }
        calendar = {
            "schema_version": "1.0",
            "edition_id": edition,
            "as_of_cst": as_of,
            "horizon_days": 30,
            "policy_briefs": [dict(brief, id=f"brief_{idx}") for idx in range(6)],
            "events": [event],
        }

        def validate(data, market_as_of=as_of, *, live=True):
            return psd._validate_policy_calendar(
                data,
                edition_id=edition,
                as_of_date="2026-12-31",
                gold_tier0_active=True,
                market_as_of_cst=market_as_of,
                enforce_live_contract=live,
            )

        self.assertEqual(validate(calendar, "2026-12-31T23:59+08:00"), [])
        self.assertIn("as_of_cst must match", "\n".join(validate(calendar, "2026-12-31T23:58:00+08:00")))
        before_brief_time = copy.deepcopy(calendar)
        before_brief_time["as_of_cst"] = "2026-12-31T23:58:00+08:00"
        self.assertIn("is later than as_of_cst", "\n".join(validate(before_brief_time, before_brief_time["as_of_cst"])))

        bad_calendar = copy.deepcopy(calendar)
        first, second, third = bad_calendar["policy_briefs"][:3]
        first.pop("source_url")
        first["home_featured"] = False
        second.update(source_url="https://example.invalid/official", date_cst="2027-01-01")
        third["time_cst"] = "明日"
        bad_calendar["events"][0].update(end_date_cst="2027-01-16", time_cst="25:08")
        errors = "\n".join(validate(bad_calendar))
        for detail in ("6–9 home_featured", "invalid https source_url None", "example.invalid",
                       "is later than as_of_cst", "time_cst must use HH:MM", "exact requires one date"):
            self.assertIn(detail, errors)
        self.assertEqual(validate(bad_calendar, live=False), [])

        bad_calendar = copy.deepcopy(calendar)
        bad_calendar["events"][0]["date_precision"] = "window_tbd"
        self.assertIn("window_tbd requires a time window", "\n".join(validate(bad_calendar)))

    def _valid_rsi_entry(self, run_id: str) -> dict:
        return {
            "run_id": run_id,
            "edition_type": "weekday_evening_unified",
            "scores": {
                "data_freshness_and_zero_hallucination": 5,
                "prior_forecast_calibration": 5,
                "plain_language_and_strict_readability": 5,
                "visual_layout_and_pagination": 4,
                "research_efficiency_and_source_quality": 4,
                "engine_and_guardrail_reliability": 5,
            },
            "total_score": 28,
            "max_score": 30,
            "review_closure": {
                "reviewer_completed": True,
                "findings": [
                    {
                        "description": "G-01 [LOW]: 术语微调",
                        "status": "resolved",
                        "evidence": "已补全白话括注并复过严格门禁",
                    },
                    {
                        "description": "休市日无常规读数",
                        "status": "disclosed_caveat",
                        "evidence": {
                            "source": "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
                            "due_edition": "2099-12-31_1800_r99",
                            "disposition": "已纯中文披露于 data_caveats",
                        },
                    },
                    {
                        "description": "联邦滞后统计待披露",
                        "status": "deferred_data",
                        "evidence": {
                            "source": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
                            "due_edition": "2099-12-31_1800_r99",
                            "disposition": "已挂账至下班次核销",
                        },
                    },
                ],
            },
        }

    def test_append_gold_and_equity_rsi_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gold" / "daily").mkdir(parents=True)
            (root / "equity" / "state").mkdir(parents=True)

            gold_rsi = root / "gold/daily/rsi_metrics.json"
            eq_rsi = root / "equity/state/rsi_metrics.json"
            seed = {
                "schema_version": "1.0",
                "score_dimensions": list(psd.RSI_REQUIRED_SCORE_KEYS),
                "runs": [{"run_id": "2026-11-27_0730"}],
            }
            gold_rsi.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            eq_rsi.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            gold_patch = root / "gold/daily/_rsi_patch.json"
            eq_patch = root / "equity/state/_rsi_patch.json"
            entry = self._valid_rsi_entry("2026-11-27_1800")

            # Reject list-root rsi_metrics.json!
            gold_rsi.write_text("[]\n", encoding="utf-8")
            gold_patch.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "list-root"):
                psd.append_gold_rsi(root)
            gold_rsi.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            # Reject invalid scores: missing dim, bool value, out-of-range, wrong total_score, wrong max_score
            bad_dims = json.loads(json.dumps(entry))
            del bad_dims["scores"]["visual_layout_and_pagination"]
            gold_patch.write_text(json.dumps(bad_dims, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "score_dimensions"):
                psd.append_gold_rsi(root)

            bad_bool = json.loads(json.dumps(entry))
            bad_bool["scores"]["visual_layout_and_pagination"] = True
            gold_patch.write_text(json.dumps(bad_bool, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not bool"):
                psd.append_gold_rsi(root)

            bad_range = json.loads(json.dumps(entry))
            bad_range["scores"]["visual_layout_and_pagination"] = 6
            bad_range["total_score"] = 30
            gold_patch.write_text(json.dumps(bad_range, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"1\.\.5"):
                psd.append_gold_rsi(root)

            bad_total = json.loads(json.dumps(entry))
            bad_total["total_score"] = 29
            gold_patch.write_text(json.dumps(bad_total, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "total_score"):
                psd.append_gold_rsi(root)

            bad_max = json.loads(json.dumps(entry))
            bad_max["max_score"] = 25
            gold_patch.write_text(json.dumps(bad_max, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "max_score"):
                psd.append_gold_rsi(root)

            # Reject open finding status
            bad_entry = json.loads(json.dumps(entry))
            bad_entry["review_closure"]["findings"][0]["status"] = "open"
            gold_patch.write_text(json.dumps(bad_entry, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid status"):
                psd.append_gold_rsi(root)

            # Reject local path leak
            leak_entry = json.loads(json.dumps(entry))
            leak_entry["review_closure"]["findings"][0]["evidence"] = "see /Users/alice/secret.md"
            gold_patch.write_text(json.dumps(leak_entry, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "local filesystem path"):
                psd.append_gold_rsi(root)

            # Dry-run & real append for gold RSI via CLI
            gold_patch.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(StringIO()):
                self.assertEqual(psd.main(["--append-gold-rsi", "--dry-run"]), 0)
                self.assertTrue(gold_patch.exists())
                self.assertEqual(len(json.loads(gold_rsi.read_text("utf-8"))["runs"]), 1)

                self.assertEqual(psd.main(["--append-gold-rsi"]), 0)
                self.assertFalse(gold_patch.exists())

            self.assertEqual(stat.S_IMODE(gold_rsi.stat().st_mode), 0o644)
            gold_after = json.loads(gold_rsi.read_text("utf-8"))
            self.assertEqual([r["run_id"] for r in gold_after["runs"]], ["2026-11-27_0730", "2026-11-27_1800"])

            # Duplicate run_id rejected
            gold_patch.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already contains run_id"):
                psd.append_gold_rsi(root)
            gold_patch.unlink()

            # Equity RSI append with --keep-patch
            eq_patch.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(StringIO()):
                self.assertEqual(psd.main(["--append-equity-rsi", "--keep-patch"]), 0)
            self.assertTrue(eq_patch.exists())
            self.assertEqual(stat.S_IMODE(eq_rsi.stat().st_mode), 0o644)
            eq_after = json.loads(eq_rsi.read_text("utf-8"))
            self.assertEqual([r["run_id"] for r in eq_after["runs"]], ["2026-11-27_0730", "2026-11-27_1800"])

    def test_prepend_equity_audit_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "equity" / "state").mkdir(parents=True)
            audit_path = root / "equity/state/audit_ledger.md"
            orig_md = (
                "# 内部后台审计账本\n\n"
                "> 内部留痕说明。\n\n"
                "---\n\n"
                "## 2026-11-27 07:55 CST · `2026-11-27_0730` 一体化早刊\n\n"
                "- 原有审计记录 1。\n"
            )
            audit_path.write_text(orig_md, encoding="utf-8")

            patch_path = root / "equity/state/_audit_patch.json"
            payload = {
                "edition_id": "2026-11-27_1800",
                "entry_md": "## 2026-11-27 18:10 CST · `2026-11-27_1800` 一体化晚刊\n\n- 晚刊红队核验闭环。",
                "note": "晚刊审计头插",
            }

            # Local path leak rejected
            bad_leak = dict(payload, entry_md="检查 /Users/bob/file.md")
            patch_path.write_text(json.dumps(bad_leak, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "local filesystem path"):
                psd.prepend_equity_audit(root)

            # Duplicate existing heading rejected
            dup_existing = dict(payload, edition_id="2026-11-27_0730")
            patch_path.write_text(json.dumps(dup_existing, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already contains"):
                psd.prepend_equity_audit(root)

            # Revision suffix (2026-11-27_0730_r2) is NOT falsely blocked by 2026-11-27_0730
            rev_payload = dict(
                payload,
                edition_id="2026-11-27_0730_r2",
                entry_md="## 2026-11-27 10:00 CST · `2026-11-27_0730_r2` 修订刊\n\n- 修订核验。",
            )
            patch_path.write_text(json.dumps(rev_payload, ensure_ascii=False), encoding="utf-8")
            summary_dry = psd.prepend_equity_audit(root, dry_run=True)
            self.assertTrue(summary_dry["order_proof_verified"])
            self.assertEqual(audit_path.read_text("utf-8"), orig_md)

            # Real prepend via CLI
            patch_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(StringIO()):
                self.assertEqual(psd.main(["--prepend-equity-audit"]), 0)
            self.assertFalse(patch_path.exists())
            self.assertEqual(stat.S_IMODE(audit_path.stat().st_mode), 0o644)

            updated = audit_path.read_text("utf-8")
            self.assertLess(updated.index("2026-11-27_1800"), updated.index("2026-11-27_0730"))
            self.assertTrue(
                psd._preserves_order(
                    psd._nonblank_lines(orig_md.encode("utf-8")),
                    psd._nonblank_lines(updated.encode("utf-8")),
                )
            )

            # Second identical prepend rejected idempotently
            patch_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already contains"):
                psd.prepend_equity_audit(root)

            # Reject entry_md missing a '## ' heading referencing edition_id
            missing_hdr = {
                "edition_id": "2026-11-28_0730",
                "entry_md": "### 错误标题级别 `2026-11-28_0730`\n\n- 缺少二级标题。",
            }
            patch_path.write_text(json.dumps(missing_hdr, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must contain a '## ' heading"):
                psd.prepend_equity_audit(root)

            # Rollover fallback: header-only audit_ledger.md without '---' still prepends cleanly!
            header_only = "# 内部后台审计账本\n\n> 月度归档后新月账本说明。\n> 第二行引用。\n"
            audit_path.write_text(header_only, encoding="utf-8")
            dec_payload = {
                "edition_id": "2026-12-01_0730",
                "entry_md": "## 2026-12-01 07:55 CST · `2026-12-01_0730` 十二月首刊\n\n- 新月首条审计记录。",
            }
            patch_path.write_text(json.dumps(dec_payload, ensure_ascii=False), encoding="utf-8")
            res_roll = psd.prepend_equity_audit(root)
            self.assertTrue(res_roll["order_proof_verified"])
            rolled_txt = audit_path.read_text("utf-8")
            self.assertIn("> 第二行引用。\n\n---\n\n## 2026-12-01 07:55 CST", rolled_txt)
            self.assertTrue(
                psd._preserves_order(
                    psd._nonblank_lines(header_only.encode("utf-8")),
                    psd._nonblank_lines(rolled_txt.encode("utf-8")),
                )
            )

    def test_rollover_equity_month_and_atomic_new_file_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "equity" / "state").mkdir(parents=True)

            sample_md = {
                "a_share": (
                    "# 中国 A 股跨周期全景手册\n\n"
                    "## 阅读导航（基准时点：2026 年 11 月 25 日 13:30 北京时间）\n\n"
                    "## 附录二：全量龙头总表\n\n"
                    "| 序号 | 代码 | 名称 |\n| :---: | :---: | :--- |\n"
                    "| 1 | `600036` | 招商银行 |\n"
                    "| 2 | `601088` | 中国神华 |\n"
                ),
                "hk_stock": (
                    "# 香港股市跨周期全景手册\n\n"
                    "## 阅读导航（基准时点：2026 年 11 月 25 日 13:30 北京时间）\n\n"
                    "## 附表二：港股龙头总表\n\n"
                    "| 序号 | 代码 | 名称 |\n| :---: | :---: | :--- |\n"
                    "| 1 | `00700.HK` | 腾讯控股 |\n"
                ),
                "us_stock": (
                    "# 美国股市跨周期全景手册\n\n"
                    "## 一、底层逻辑（基准时点：2026 年 11 月 25 日 13:30 北京时间）\n\n"
                    "## 附录二：美股龙头总表\n\n"
                    "| 序号 | 代码 | 名称 |\n| :---: | :---: | :--- |\n"
                    "| 1 | `MSFT` | 微软 |\n"
                ),
            }
            for mkt, md in sample_md.items():
                (root / "equity" / f"{mkt}_market_report_2026_11.md").write_text(md, encoding="utf-8")
                (root / "equity" / f"{mkt}_market_report_latest.md").write_text(md, encoding="utf-8")
                meta = {
                    "period_slug": "2026_11",
                    "version": "2026年11月刊",
                    "title": f"{mkt} 标题",
                    "benchmark_time": "2026-11-25 13:30 北京时间",
                    "page_footer": f"{mkt} 手册（2026年11月）",
                    "chart_live": {
                        "as_of_full": "2026-11-25 13:30 北京时间",
                        "as_of_year_float": 2026.908,
                    },
                }
                (root / "equity" / f"report_meta_{mkt}.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )

            patch_path = root / "equity/state/_rollover_patch.json"
            valid_patch = {
                "prev_period_slug": "2026_11",
                "new_period_slug": "2026_12",
                "as_of_full": "2026-12-01 07:55 北京时间",
                "as_of_year_float": 2026.916,
                "benchmark_time": "2026-12-01 07:55 北京时间",
                "markets": {
                    "a_share": {
                        "header_replacements": [
                            ["2026 年 11 月 25 日 13:30 北京时间", "2026 年 12 月 01 日 07:55 北京时间"]
                        ],
                        "subtitle": "十二月策略基线",
                    },
                    "us_stock": {
                        "page_footer": "美股全景手册（2026-12 定制页脚）",
                    },
                },
                "note": "十二月首日自动月度滚动",
            }

            # Unknown top key lists allowed keys
            patch_path.write_text(json.dumps({**valid_patch, "bad_key": 1}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "allowed:"):
                psd.rollover_equity_month(root, dry_run=True)

            # Reject non-later period slug
            patch_path.write_text(json.dumps({**valid_patch, "new_period_slug": "2026_11"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "strictly later"):
                psd.rollover_equity_month(root, dry_run=True)

            # Reject as_of_full not matching new_period_slug month prefix
            patch_path.write_text(
                json.dumps({**valid_patch, "as_of_full": "2026-11-30 18:00 北京时间"}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "must start with '2026-12'"):
                psd.rollover_equity_month(root, dry_run=True)

            # Reject header_replacements that alters Appendix 2 stock rows!
            bad_app2 = json.loads(json.dumps(valid_patch))
            bad_app2["markets"]["a_share"]["header_replacements"] = [["招商银行", "改写龙头"]]
            patch_path.write_text(json.dumps(bad_app2, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Appendix 2"):
                psd.rollover_equity_month(root, dry_run=True)

            # Reject header_replacements introducing banned internal term or local path
            bad_leak = json.loads(json.dumps(valid_patch))
            bad_leak["markets"]["a_share"]["header_replacements"] = [
                ["2026 年 11 月 25 日 13:30 北京时间", "见 /Users/bob/secret.md"]
            ]
            patch_path.write_text(json.dumps(bad_leak, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "local filesystem path"):
                psd.rollover_equity_month(root, dry_run=True)

            # Atomic rollback test: fail os.replace on the 5th file -> brand-new 2026_12 files unlinked & existing restored!
            patch_path.write_text(json.dumps(valid_patch, ensure_ascii=False), encoding="utf-8")
            real_replace = psd.os.replace
            call_count = {"n": 0}

            def flaky_replace(src, dst):
                call_count["n"] += 1
                if call_count["n"] == 5:
                    raise OSError("simulated disk error mid-rollover")
                return real_replace(src, dst)

            with patch.object(psd.os, "replace", side_effect=flaky_replace):
                with self.assertRaisesRegex(OSError, "simulated disk error"):
                    psd.rollover_equity_month(root)

            # Brand-new 2026_12 files must be completely rolled back (deleted), existing files intact!
            for mkt in psd.ROLLOVER_MARKETS:
                self.assertFalse((root / "equity" / f"{mkt}_market_report_2026_12.md").exists())
                self.assertEqual(
                    (root / "equity" / f"{mkt}_market_report_latest.md").read_text("utf-8"),
                    sample_md[mkt],
                )
                meta_rb = json.loads((root / "equity" / f"report_meta_{mkt}.json").read_text("utf-8"))
                self.assertEqual(meta_rb["period_slug"], "2026_11")
            self.assertTrue(patch_path.exists())

            # Dry-run leaves disk untouched and retains patch
            res_dry = psd.rollover_equity_month(root, dry_run=True)
            self.assertEqual(res_dry["files_staged"], 9)
            self.assertFalse((root / "equity/a_share_market_report_2026_12.md").exists())
            self.assertTrue(patch_path.exists())

            # Real rollover via CLI succeeds, writes 9 files atomically, deletes patch
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(StringIO()):
                self.assertEqual(psd.main(["--rollover-equity-month"]), 0)
            self.assertFalse(patch_path.exists())

            for mkt in psd.ROLLOVER_MARKETS:
                p_new = root / "equity" / f"{mkt}_market_report_2026_12.md"
                p_lat = root / "equity" / f"{mkt}_market_report_latest.md"
                self.assertTrue(p_new.is_file())
                self.assertEqual(p_new.read_bytes(), p_lat.read_bytes())
                self.assertEqual(stat.S_IMODE(p_new.stat().st_mode), 0o644)
                meta_new = json.loads((root / "equity" / f"report_meta_{mkt}.json").read_text("utf-8"))
                self.assertEqual(meta_new["period_slug"], "2026_12")
                self.assertEqual(meta_new["version"], "2026年12月刊")
                self.assertEqual(meta_new["benchmark_time"], "2026-12-01 07:55 北京时间")
                self.assertEqual(meta_new["chart_live"]["as_of_full"], "2026-12-01 07:55 北京时间")
                self.assertEqual(meta_new["chart_live"]["as_of_year_float"], 2026.916)
            self.assertIn("2026 年 12 月 01 日", (root / "equity/a_share_market_report_2026_12.md").read_text("utf-8"))
            self.assertEqual(
                json.loads((root / "equity/report_meta_a_share.json").read_text("utf-8"))["subtitle"],
                "十二月策略基线",
            )
            self.assertEqual(
                json.loads((root / "equity/report_meta_a_share.json").read_text("utf-8"))["page_footer"],
                "a_share 手册（2026年12月）",
            )
            self.assertEqual(
                json.loads((root / "equity/report_meta_us_stock.json").read_text("utf-8"))["page_footer"],
                "美股全景手册（2026-12 定制页脚）",
            )

            # Second identical rollover refuses to overwrite existing 2026_12 flagship!
            patch_path.write_text(json.dumps(valid_patch, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                psd.rollover_equity_month(root)

    def test_archive_gold_ledgers_with_order_proof_and_subsequent_prepend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = root / "gold" / "daily"
            daily.mkdir(parents=True)

            orig_cl = (
                "# 黄金每日深度研报演化日志\n\n"
                "> 公开演化日志导语第一行。\n"
                "> 公开演化日志导语第二行。\n\n"
                "---\n\n"
                "<!-- GOLD_EDITION_CHANGELOG 2026-11-27_0730 -->\n\n"
                "## 2026-11-27 早报演化记录\n"
                "- 历史记录条目 A。\n"
            )
            orig_au = (
                "# 黄金研报体系·审计账本（AUDIT_LOG）\n\n"
                "> **档案定位**：内部法证审计说明。\n\n"
                "---\n\n"
                '<!-- GOLD_EDITION_REVIEW {"edition_id": "2026-11-27_0730"} -->\n\n'
                "## 2026-11-27 审计条目\n"
                "- 审计详录 B。\n"
            )
            cl_path = daily / "CHANGELOG.md"
            au_path = daily / "AUDIT_LOG.md"
            cl_path.write_text(orig_cl, encoding="utf-8")
            au_path.write_text(orig_au, encoding="utf-8")

            patch_path = daily / "_archive_patch.json"
            # Unknown key error lists allowed keys
            patch_path.write_text(json.dumps({"archive_period": "2026_11", "extra": 1}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"allowed: \['archive_period', 'note'\]"):
                psd.archive_gold_ledgers(root, dry_run=True)

            # Dry-run verifies proof without mutating files
            patch_path.write_text(
                json.dumps({"archive_period": "2026_11", "note": "十一月月度归档"}, ensure_ascii=False),
                encoding="utf-8",
            )
            res_dry = psd.archive_gold_ledgers(root, dry_run=True)
            self.assertTrue(res_dry["order_proof_verified"])
            self.assertFalse((daily / "archive" / "CHANGELOG_2026_11.md").exists())
            self.assertTrue(patch_path.exists())

            # Real archive via CLI
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(StringIO()):
                self.assertEqual(psd.main(["--archive-gold-ledgers"]), 0)
            self.assertFalse(patch_path.exists())

            arc_cl = daily / "archive" / "CHANGELOG_2026_11.md"
            arc_au = daily / "archive" / "AUDIT_LOG_2026_11.md"
            self.assertEqual(arc_cl.read_bytes(), orig_cl.encode("utf-8"))
            self.assertEqual(arc_au.read_bytes(), orig_au.encode("utf-8"))
            for p in (arc_cl, arc_au, cl_path, au_path):
                self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o644)

            active_cl = cl_path.read_text("utf-8")
            active_au = au_path.read_text("utf-8")
            self.assertIn("archive/CHANGELOG_2026_11.md", active_cl)
            self.assertIn("archive/AUDIT_LOG_2026_11.md", active_au)
            self.assertNotIn("2026-11-27_0730", active_cl)
            self.assertNotIn("2026-11-27_0730", active_au)

            # Mathematical order preservation proof: archive_bytes + active_bytes preserves 100% of prior nonblank lines!
            self.assertTrue(
                psd._preserves_order(
                    psd._nonblank_lines(orig_cl.encode("utf-8")),
                    psd._nonblank_lines(arc_cl.read_bytes() + b"\n" + cl_path.read_bytes()),
                )
            )
            self.assertTrue(
                psd._preserves_order(
                    psd._nonblank_lines(orig_au.encode("utf-8")),
                    psd._nonblank_lines(arc_au.read_bytes() + b"\n" + au_path.read_bytes()),
                )
            )

            # Refuses overwrite if archive already exists
            patch_path.write_text(json.dumps({"archive_period": "2026_11"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                psd.archive_gold_ledgers(root)
            patch_path.unlink()

            # Subsequent --prepend-gold-ledgers works seamlessly on the newly reset active ledgers!
            (root / "gold" / "data_snapshot.json").write_text(
                json.dumps({"edition_id": "2026-12-01_0730", "as_of_short": "2026-12-01 07:55"}),
                encoding="utf-8",
            )
            review_json = json.dumps(
                {
                    "edition_id": "2026-12-01_0730",
                    "as_of_short": "2026-12-01 07:55",
                    "note": "十二月首刊核验",
                    "sources": {
                        "real_yield": ["https://home.treasury.gov/test"],
                        "rate_spread": ["https://markets.newyorkfed.org/test"],
                        "vix": ["https://cdn-api.cboe.com/test"],
                        "ny_close": ["https://www.lbma.org.uk/test"],
                    },
                    "forecast_review": {
                        "status": "none_due",
                        "note": "本班次无到期项",
                        "sources": [],
                    },
                },
                ensure_ascii=False,
            )
            (daily / "_ledger_patch.json").write_text(
                json.dumps(
                    {
                        "edition_id": "2026-12-01_0730",
                        "changelog_entry_md": "## 2026-12-01 早报\n- 十二月首刊记录。",
                        "audit_review_block_md": f"<!-- GOLD_EDITION_REVIEW {review_json} -->\n\n## 2026-12-01 审计\n- 通过。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            res_prep = psd.prepend_gold_ledgers(root)
            self.assertTrue(res_prep["order_proof_verified"])
            self.assertIn("GOLD_EDITION_CHANGELOG 2026-12-01_0730", cl_path.read_text("utf-8"))
            self.assertIn("archive/CHANGELOG_2026_11.md", cl_path.read_text("utf-8"))

    def test_inspect_mode_all_six_targets_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root)

            targets_and_checks = [
                ("channels", lambda d: self.assertEqual(d["total_channels"], 12)),
                ("channel:reverse_repo", lambda d: self.assertEqual(d["id"], "reverse_repo")),
                ("etf:2830.HK", lambda d: self.assertEqual(d["code"], "02830.HK")),
                ("etf:510300", lambda d: self.assertEqual(d["code"], "510300")),
                ("stock:a-share:601088", lambda d: self.assertEqual(d["name"], "中国神华")),
                (
                    "stale-dossiers",
                    lambda d: (
                        self.assertEqual(d["total_stocks"], 6),
                        self.assertEqual(d["latest_updated_at"], "2026-11-27"),
                        self.assertIn("a-share:601088", d["recently_updated_keys"]),
                    ),
                ),
                (
                    "ah-benchmarks",
                    lambda d: (
                        self.assertEqual(d["total_benchmarks"], 1),
                        self.assertEqual(d["benchmarks"][0]["a_dossier"]["key"], "a-share:601088"),
                        self.assertEqual(d["benchmarks"][0]["h_dossier"]["key"], "hk-stock:01088.HK"),
                    ),
                ),
            ]
            for target, check_fn in targets_and_checks:
                with self.subTest(target=target):
                    buf = StringIO()
                    with patch.object(psd, "REPO_ROOT", root), redirect_stdout(buf):
                        rc = psd.main(["--inspect", target])
                    self.assertEqual(rc, 0)
                    parsed = json.loads(buf.getvalue())
                    check_fn(parsed)

            # Unknown inspect target returns 1
            err_buf = StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stderr(err_buf):
                self.assertEqual(psd.main(["--inspect", "nonexistent"]), 1)
            self.assertIn("Unknown --inspect target", err_buf.getvalue())

    def test_policy_calendar_apply_upsert_prune_guards_and_inspect(self):
        def _make_event(eid: str, start: str, end: str, *, region: str = "US", category: str = "central_bank", tier: str = "P0", precision: str = "exact", stance: str = "黄金维持红灯停新仓 0%，静待官方落地。") -> dict:
            return {
                "event_id": eid,
                "date_cst": start,
                "end_date_cst": end,
                "date_precision": precision,
                "time_cst": "03:00" if precision == "exact" else "全天窗口",
                "region": region,
                "category": category,
                "impact_tier": tier,
                "title": f"测试宏观政策事件 {eid}",
                "affected_markets": ["us_stock", "rates_bonds_core", "gold"],
                "expected_consensus": "市场关注政策节奏与利率路径。",
                "market_transmission": "经美债收益率传导至股债与避险资产。",
                "watch_triggers": {
                    "upside_bull": "利率回落缓解估值压制。",
                    "downside_bear": "鹰派指引推高美债压制风险资产。",
                },
                "pre_event_stance": stance,
                "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                "monitor_window_min": 60,
            }

        def _make_brief(bid: str, *, date_cst: str = "2026-11-27", region: str = "CN", category: str = "macro_data", tier: str = "P1") -> dict:
            return {
                "id": bid,
                "date_cst": date_cst,
                "region": region,
                "category": category,
                "impact_tier": tier,
                "authority": "国家统计局",
                "headline": "工业企业利润同比改善",
                "summary": "10 月规上工业企业利润同比改善，提振午盘风偏。",
                "affected_markets": ["a_share", "hk_stock"],
                "market_impact": "红灯防守期严守股票上限，不追早盘脉冲。",
                "source_url": "https://www.stats.gov.cn/",
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root, edition_id="2026-11-27_1130", as_of_date="2026-11-27")
            pc_path = root / "equity/state/policy_calendar.json"
            base_pc = {
                "schema_version": "1.0",
                "edition_id": "2026-11-27_0730",
                "as_of_cst": "2026-11-27T07:55:00+08:00",
                "horizon_days": 30,
                "policy_briefs": [_make_brief("old_brief_1")],
                "events": [
                    _make_event("expired_ev_1", "2026-11-24", "2026-11-24", region="CN", tier="P2"),
                    _make_event("boundary_ev_keep", "2026-11-25", "2026-11-25", region="CN", tier="P1"),
                    _make_event("remove_me_ev", "2026-12-01", "2026-12-01", region="HK", category="market_structure", tier="P1"),
                    _make_event("update_me_ev", "2026-12-10", "2026-12-10", region="US", tier="P0"),
                    _make_event("far_ev_1", "2026-12-18", "2026-12-18", region="JP", tier="P0"),
                ],
            }
            pc_path.write_text(json.dumps(base_pc, ensure_ascii=False), encoding="utf-8")

            # 1. Clean --apply: upsert existing + add new + remove + replace briefs + auto-prune < 2026-11-25
            patch_path = root / "equity/state/_edition_patch.json"
            good_patch = {
                "edition_id": "2026-11-27_1130",
                "as_of_date": "2026-11-27",
                "policy_calendar": {
                    "top_level_updates": {"horizon_days": 30, "as_of_cst": "2026-11-27T12:30:00+08:00"},
                    "policy_briefs_replace": [_make_brief("new_brief_1"), _make_brief("new_brief_2", region="US", tier="P0")],
                    "events_remove": ["remove_me_ev"],
                    "events_upsert": [
                        {"event_id": "update_me_ev", "title": "美联储 12 月议息决议（更新版）", "monitor_window_min": 120},
                        _make_event("added_ev_lpr", "2026-12-21", "2026-12-21", region="CN", tier="P1"),
                    ],
                },
            }
            patch_path.write_text(json.dumps(good_patch, ensure_ascii=False), encoding="utf-8")
            out_ok, err_ok = StringIO(), StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(out_ok), redirect_stderr(err_ok):
                rc_ok = psd.main(["--apply"])
            self.assertEqual(rc_ok, 0, err_ok.getvalue())
            self.assertFalse(patch_path.exists())

            pc_after = json.loads(pc_path.read_text(encoding="utf-8"))
            self.assertEqual(pc_after["edition_id"], "2026-11-27_1130")
            self.assertEqual(pc_after["as_of_cst"], "2026-11-27T12:30:00+08:00")
            self.assertEqual([b["id"] for b in pc_after["policy_briefs"]], ["new_brief_1", "new_brief_2"])
            eids_after = [ev["event_id"] for ev in pc_after["events"]]
            self.assertNotIn("expired_ev_1", eids_after)
            self.assertNotIn("remove_me_ev", eids_after)
            self.assertIn("boundary_ev_keep", eids_after)
            self.assertIn("added_ev_lpr", eids_after)
            upd_ev = next(ev for ev in pc_after["events"] if ev["event_id"] == "update_me_ev")
            self.assertEqual(upd_ev["title"], "美联储 12 月议息决议（更新版）")
            self.assertEqual(upd_ev["monitor_window_min"], 120)

            # 2. --inspect policy-calendar returns compact summary by tier & region
            insp_buf = StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(insp_buf):
                rc_insp = psd.main(["--inspect", "policy-calendar"])
            self.assertEqual(rc_insp, 0)
            insp_data = json.loads(insp_buf.getvalue())
            self.assertEqual(insp_data["edition_id"], "2026-11-27_1130")
            self.assertEqual(insp_data["total_briefs"], 2)
            self.assertEqual(insp_data["total_events"], 4)
            self.assertEqual(insp_data["horizon_end_cst"], "2026-12-21")
            self.assertEqual(insp_data["counts_by_tier"], {"P0": 2, "P1": 2})
            self.assertEqual(insp_data["counts_by_region"], {"CN": 2, "JP": 1, "US": 1})

            # 3. Reject bad enum, Gold buy verb under Tier-0 lock, <14-day horizon, and internal filename leaks atomically
            snap_before = pc_path.read_bytes()
            reject_cases = [
                (
                    "bad_region_enum",
                    {"events_upsert": [{"event_id": "update_me_ev", "region": "MARS"}]},
                    "invalid region",
                ),
                (
                    "bad_category_enum",
                    {"events_upsert": [{"event_id": "update_me_ev", "category": "crypto_pump"}]},
                    "invalid category",
                ),
                (
                    "bad_tier_enum",
                    {"events_upsert": [{"event_id": "update_me_ev", "impact_tier": "P9"}]},
                    "invalid impact_tier",
                ),
                (
                    "bad_precision_enum",
                    {"events_upsert": [{"event_id": "update_me_ev", "date_precision": "approx"}]},
                    "invalid date_precision",
                ),
                (
                    "bad_affected_markets_enum",
                    {"events_upsert": [{"event_id": "update_me_ev", "affected_markets": ["us_stock", "crypto_mars"]}]},
                    "invalid affected_markets",
                ),
                (
                    "unknown_top_level_key",
                    {"top_level_updates": {"rogue_field": "nope"}},
                    "Unknown key(s) in policy_calendar.top_level_updates",
                ),
                (
                    "pboc_crypto_buy_violation",
                    {"events_upsert": [{"event_id": "update_me_ev", "pre_event_stance": "建议会前逢低买入 BTC 或配置比特币避险。"}]},
                    "银发〔2026〕42号",
                ),
                (
                    "gold_buy_under_tier0",
                    {"events_upsert": [{"event_id": "update_me_ev", "pre_event_stance": "建议会前逢低买入黄金 518880 避险。"}]},
                    "Gold Tier-0 互斥冲突",
                ),
                (
                    "gold_buy_aligned_verb_under_tier0",
                    {"events_upsert": [{"event_id": "update_me_ev", "pre_event_stance": "可趁震荡布局黄金或上车 518880。"}]},
                    "Gold Tier-0 互斥冲突",
                ),
                (
                    "horizon_under_14d",
                    {"events_remove": ["far_ev_1", "added_ev_lpr"]},
                    "forward horizon coverage",
                ),
                (
                    "internal_filename_leak",
                    {"events_upsert": [{"event_id": "update_me_ev", "pre_event_stance": "详见 realtime_monitor.py 与 policy_calendar.json。"}]},
                    "leaked internal term",
                ),
            ]
            for label, pc_patch_body, expected_err in reject_cases:
                with self.subTest(case=label):
                    patch_path.write_text(
                        json.dumps({"edition_id": "2026-11-27_1130", "as_of_date": "2026-11-27", "policy_calendar": pc_patch_body}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    out_b, err_b = StringIO(), StringIO()
                    with patch.object(psd, "REPO_ROOT", root), redirect_stdout(out_b), redirect_stderr(err_b):
                        rc_b = psd.main(["--apply"])
                    self.assertEqual(rc_b, 1, label)
                    self.assertIn(expected_err, err_b.getvalue())
                    self.assertEqual(pc_path.read_bytes(), snap_before)

            # Negated PBOC Doc 42 & Gold red-light phrasing passes cleanly
            neg_ok_patch = {
                "edition_id": "2026-11-27_1130",
                "as_of_date": "2026-11-27",
                "policy_calendar": {
                    "events_upsert": [
                        {
                            "event_id": "update_me_ev",
                            "pre_event_stance": "遵照央行银发〔2026〕42号严禁配置比特币与买入 BTC；黄金红灯停期暂不布局黄金、不要上车 518880。",
                        }
                    ]
                },
            }
            patch_path.write_text(json.dumps(neg_ok_patch, ensure_ascii=False), encoding="utf-8")
            out_n, err_n = StringIO(), StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(out_n), redirect_stderr(err_n):
                rc_n = psd.main(["--apply"])
            self.assertEqual(rc_n, 0, err_n.getvalue())

            # 4. BANNED_INTERNAL_RE explicitly catches new filenames
            for banned_fn in (
                "policy_calendar.json",
                "realtime_monitor.py",
                "wechat_notify.py",
                "realtime-monitor.sqlite3",
                "notify.example.json",
                "notify.json",
            ):
                with self.subTest(banned_fn=banned_fn):
                    self.assertIsNotNone(psd.BANNED_INTERNAL_RE.search(f"禁止输出 {banned_fn}"))

            # 5. Bounded size on synthetic fixture + structural integrity check on live --inspect policy-calendar
            synth_buf = StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stdout(synth_buf):
                rc_synth = psd.main(["--inspect", "policy-calendar"])
            self.assertEqual(rc_synth, 0)
            self.assertLess(len(synth_buf.getvalue().encode("utf-8")), 15000)

            real_root = Path(__file__).resolve().parent.parent
            live_buf = StringIO()
            with patch.object(psd, "REPO_ROOT", real_root), redirect_stdout(live_buf):
                rc_live = psd.main(["--inspect", "policy-calendar"])
            self.assertEqual(rc_live, 0)
            live_summary = json.loads(live_buf.getvalue())
            self.assertGreaterEqual(live_summary["total_briefs"], 1)
            self.assertEqual(live_summary["total_briefs"], len(live_summary["policy_briefs"]))
            self.assertTrue(0 <= live_summary["home_featured_briefs"] <= live_summary["total_briefs"])
            self.assertGreaterEqual(live_summary["total_events"], 1)
            self.assertEqual(live_summary["total_events"], len(live_summary["events"]))


class EditionRunTelemetryAndPublishGuardTests(unittest.TestCase):
    def test_edition_run_records_phase_timestamps_and_durations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def _git(*args):
                return subprocess.run(
                    ["git", "-c", "user.name=Test", "-c", "user.email=t@example.invalid", *args],
                    cwd=root, capture_output=True, text=True, check=True,
                ).stdout.strip()

            with patch.object(edition_run, "ROOT", root):
                _git("init", "-q")
                for rel in edition_run.GOLD_HISTORY_LEDGERS:
                    p = root / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("## Prev\n\n- Keep\n", encoding="utf-8")
                _git("add", "gold")
                _git("commit", "-qm", "init")

                runs = edition_run.open_runs()
                try:
                    ed = "2026-11-27_1800"
                    ts_seq = iter([
                        "2026-11-27T18:00:00+08:00",
                        "2026-11-27T18:10:00+08:00",
                        "2026-11-27T18:18:00+08:00",
                        "2026-11-27T18:30:00+08:00",
                        "2026-11-27T18:32:00+08:00",
                        "2026-11-27T18:35:00+08:00",
                    ])
                    with patch.object(edition_run, "cst_now", side_effect=lambda: next(ts_seq)):
                        token = edition_run.begin(runs, ed)
                        with runs:
                            edition_run.advance(runs, token, "gold")
                        for name in ("gold/data_snapshot.json", "equity/state/market_state.json"):
                            f = root / name
                            f.parent.mkdir(parents=True, exist_ok=True)
                            f.write_text(json.dumps({"edition_id": ed}), encoding="utf-8")
                        with runs:
                            edition_run.advance(runs, token, "equity")
                        for name in ("gold/daily/rsi_metrics.json", "equity/state/rsi_metrics.json"):
                            f = root / name
                            f.parent.mkdir(parents=True, exist_ok=True)
                            f.write_text(
                                json.dumps({"runs": [{"run_id": ed, "review_closure": {"reviewer_completed": True, "findings": []}}]}),
                                encoding="utf-8",
                            )
                        with runs:
                            edition_run.advance(runs, token, "publish")
                        _git("add", "gold", "equity")
                        _git("commit", "-qm", "edition")
                        sha = _git("rev-parse", "HEAD")
                        edition_run.record_push(token, sha=sha, repository="org/repo")
                        with patch.object(edition_run, "verify_pages", return_value="https://example.invalid/ok"), runs:
                            edition_run.complete(runs, token, wait=0)

                    st = edition_run.status(runs)[0]
                    self.assertEqual(st["deployed_commit"], sha)
                    self.assertEqual(st["pushed_commit"], sha)
                    self.assertEqual(st["phase_timestamps"]["begin"], "2026-11-27T18:00:00+08:00")
                    self.assertEqual(st["phase_timestamps"]["gold"], "2026-11-27T18:10:00+08:00")
                    self.assertEqual(st["phase_timestamps"]["equity"], "2026-11-27T18:18:00+08:00")
                    self.assertEqual(st["phase_timestamps"]["publish"], "2026-11-27T18:30:00+08:00")
                    self.assertEqual(st["phase_timestamps"]["pushed"], "2026-11-27T18:32:00+08:00")
                    self.assertEqual(st["phase_timestamps"]["complete"], "2026-11-27T18:35:00+08:00")
                    self.assertEqual(
                        st["phase_durations_sec"],
                        {"research": 600.0, "gold": 480.0, "equity": 720.0, "publish": 300.0, "total": 2100.0},
                    )

                    # Test fail timestamp recording too
                    ed2 = "2026-11-28_0730"
                    fail_seq = iter(["2026-11-28T07:30:00+08:00", "2026-11-28T07:42:30+08:00"])
                    with patch.object(edition_run, "cst_now", side_effect=lambda: next(fail_seq)):
                        tok2 = edition_run.begin(runs, ed2)
                        edition_run.fail(runs, tok2, "network failure")
                    st2 = edition_run.status(runs)[0]
                    self.assertEqual(st2["phase_timestamps"]["fail"], "2026-11-28T07:42:30+08:00")
                    self.assertEqual(st2["phase_durations_sec"], {"research": 750.0, "total": 750.0})
                finally:
                    runs.close()

    def test_publish_site_transient_patch_guards_and_stale_quote_warning(self):
        for rel in (
            "equity/state/_edition_patch.json",
            "gold/daily/_ledger_patch.json",
            "gold/daily/_rsi_patch.json",
            "equity/state/_rsi_patch.json",
            "equity/state/_audit_patch.json",
            "equity/state/_rollover_patch.json",
            "gold/daily/_archive_patch.json",
        ):
            with self.subTest(rel=rel):
                self.assertTrue(publish_site._is_forbidden_stage_path(rel))
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    p = root / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("{}", encoding="utf-8")
                    with self.assertRaisesRegex(RuntimeError, "Transient patch file"):
                        publish_site._check_no_transient_patch_files(root)

        # Stale >45m warning (non-blocking) vs fresh <=45m (silent)
        now = datetime(2026, 11, 27, 9, 0, tzinfo=publish_site.CST)
        err_stale = StringIO()
        with redirect_stderr(err_stale):
            warns = publish_site._warn_stale_as_of(
                {"as_of_short": "2026-11-27 07:55"},
                {"as_of_cst": "2026-11-27T08:00:00+08:00"},
                now=now,
            )
        self.assertEqual(len(warns), 2)
        self.assertIn("[WARN] Gold snapshot", err_stale.getvalue())
        self.assertIn("[WARN] Equity market_state", err_stale.getvalue())

        err_fresh = StringIO()
        with redirect_stderr(err_fresh):
            warns_fresh = publish_site._warn_stale_as_of(
                {"as_of_short": "2026-11-27 08:30"},
                {"as_of_cst": "2026-11-27T08:30:00+08:00"},
                now=now,
            )
        self.assertEqual(warns_fresh, [])
        self.assertEqual(err_fresh.getvalue(), "")

    def test_permissions_json_includes_new_patch_state_dbs_commands_safely(self):
        repo = Path(__file__).resolve().parent.parent
        perms = json.loads((repo / "automations" / "permissions.json").read_text("utf-8"))
        self.assertEqual(len(perms), 56)
        self.assertIn("command(python3 __REPO_ROOT__/scripts/fetch_kline_data.py)", perms)
        self.assertIn("command(__PYTHON_BIN__ __REPO_ROOT__/scripts/fetch_kline_data.py)", perms)
        for verb in (
            "--append-gold-rsi",
            "--append-equity-rsi",
            "--prepend-equity-audit",
            "--rollover-equity-month",
            "--archive-gold-ledgers",
            "--inspect",
        ):
            self.assertIn(f"command(python3 __REPO_ROOT__/scripts/patch_state_dbs.py {verb})", perms)
            self.assertIn(f"command(__PYTHON_BIN__ __REPO_ROOT__/scripts/patch_state_dbs.py {verb})", perms)
        for entry in perms:
            self.assertNotIn("*", entry)
            self.assertIsNone(install_sidecars.SHELL_INJECTION_RE.search(entry))
            for forbidden in ("complete-superseded", "close-superseded", "edition_run.py recover", "edition_run.py resume"):
                self.assertNotIn(forbidden, entry)
        for _, tpl_path in install_sidecars.discover_templates(repo / "automations" / "sidecars"):
            install_sidecars.render_template(tpl_path, repo, sys.executable)

    def test_midday_1130_edition_id_supported_across_patch_verbs(self):
        self.assertEqual(psd._validate_edition_id("2026-11-27_1130"), "2026-11-27_1130")
        self.assertEqual(psd._validate_edition_id("2026-11-27_1130_r2"), "2026-11-27_1130_r2")
        with self.assertRaises(ValueError):
            psd._validate_edition_id("2026-11-27_1630")
        self.assertLess(psd._edition_sort_key("2026-11-27_0730"), psd._edition_sort_key("2026-11-27_1130"))
        self.assertLess(psd._edition_sort_key("2026-11-27_1130"), psd._edition_sort_key("2026-11-27_1800"))
        self.assertIsNotNone(psd.BANNED_INTERNAL_RE.search("请勿在正文泄露 fetch_kline_data.py"))

        real_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            (sandbox / "gold" / "daily").mkdir(parents=True)
            (sandbox / "equity" / "state").mkdir(parents=True)
            for rel in (
                "gold/data_snapshot.json",
                "gold/daily/CHANGELOG.md",
                "gold/daily/AUDIT_LOG.md",
                "gold/daily/rsi_metrics.json",
                "equity/state/market_state.json",
                "equity/state/multi_asset_channels.json",
                "equity/state/etf_universe.json",
                "equity/state/deep_dossiers.json",
                "equity/state/audit_ledger.md",
                "equity/state/rsi_metrics.json",
            ):
                shutil.copy2(real_root / rel, sandbox / rel)

            mid_ed = "2099-12-31_1130"
            gold_obj = json.loads((sandbox / "gold/data_snapshot.json").read_text(encoding="utf-8"))
            live_gold_locked = (
                gold_obj.get("tier_code") == "Tier 0" or gold_obj.get("new_buy_allowed") is False
            )
            gold_obj.update(edition_id=mid_ed, as_of_short="2099-12-31 11:30")
            (sandbox / "gold/data_snapshot.json").write_text(json.dumps(gold_obj, ensure_ascii=False), encoding="utf-8")
            ms_obj = json.loads((sandbox / "equity/state/market_state.json").read_text(encoding="utf-8"))
            ms_obj.update(edition_id=mid_ed, as_of_cst="2099-12-31T11:30:00+08:00")
            (sandbox / "equity/state/market_state.json").write_text(json.dumps(ms_obj, ensure_ascii=False), encoding="utf-8")

            # 1. --apply with 1130 (preserves live Gold lock state so Gold unlock never breaks CI)
            (sandbox / "equity/state/_edition_patch.json").write_text(
                json.dumps({"edition_id": mid_ed, "as_of_date": "2099-12-31", "gold_tier0_locked": live_gold_locked}),
                encoding="utf-8",
            )
            # 2. --prepend-gold-ledgers with 1130
            review = {
                "edition_id": mid_ed,
                "as_of_short": "2099-12-31 11:30",
                "note": "午报四关核验完成",
                "sources": {
                    "real_yield": ["https://home.treasury.gov/resource-center/data-chart-center"],
                    "rate_spread": ["https://www.newyorkfed.org/markets/reference-rates/effr"],
                    "vix": ["https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"],
                    "ny_close": ["https://www.lbma.org.uk/prices-and-data/precious-metal-prices"],
                },
                "forecast_review": {"status": "none_due", "note": "午报无到期项", "sources": []},
            }
            (sandbox / "gold/daily/_ledger_patch.json").write_text(
                json.dumps({
                    "edition_id": mid_ed,
                    "changelog_entry_md": f"<!-- GOLD_EDITION_CHANGELOG {mid_ed} -->\n\n### {mid_ed} 午报\n\n- 午报记录。\n",
                    "audit_review_block_md": (
                        f"<!-- GOLD_EDITION_REVIEW {json.dumps(review, ensure_ascii=False)} -->\n"
                        f"### {mid_ed} 午报核验\n\n- 核验通过。\n"
                    ),
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            # 3. --prepend-equity-audit with 1130
            (sandbox / "equity/state/_audit_patch.json").write_text(
                json.dumps({"edition_id": mid_ed, "entry_md": f"## {mid_ed} 午报审计\n\n- 午报审计完成。\n"}, ensure_ascii=False),
                encoding="utf-8",
            )
            # 4. --append-gold-rsi & --append-equity-rsi with 1130
            rsi_run = {
                "run_id": mid_ed,
                "date": "2099-12-31",
                "edition_type": "midday",
                "scores": dict.fromkeys(psd.RSI_REQUIRED_SCORE_KEYS, 5),
                "total_score": 30,
                "max_score": 30,
                "review_closure": {"reviewer_completed": True, "findings": []},
            }
            gold_daily = f"gold/daily/{mid_ed}_午报_黄金深度研报.md"
            with patch.object(psd, "REPO_ROOT", sandbox):
                for flag in (
                    "--apply",
                    "--prepend-gold-ledgers",
                    "--prepend-equity-audit",
                ):
                    with self.subTest(flag=flag):
                        self.assertEqual(psd.main([flag]), 0)
                for rel in (
                    *review_evidence.FIXED_PATHS, gold_daily,
                    *(f"equity/{ms_obj['markets'][market]['latest_daily']}" for market in review_evidence.MARKETS),
                ):
                    target = sandbox / rel
                    if not target.is_file():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text("Fixture manuscript or source data\n", encoding="utf-8")
                source = review["sources"]["real_yield"][0]
                fact = "财政部发布的实际利率按当日交易口径核验。"
                calculation = "同口径利率相差 0.07 个百分点，即 7 个基点。"
                inference = "如果实际利率继续上行，久期风险可能扩大。"
                (sandbox / gold_daily).write_text(
                    f"{fact} [实际利率原始数据]({source})\n{calculation}\n{inference}\n", encoding="utf-8",
                )
                policy_path = review_evidence.POLICY_CALENDAR_PATH
                brief = {
                    "id": "treasury-rates", "headline": "美国财政部公布实际利率表。", "summary": fact,
                    "source_url": source, "home_featured": True,
                }
                (sandbox / policy_path).write_text(json.dumps({"policy_briefs": [brief]}), encoding="utf-8")
                candidate = psd.inspect_state_dbs(sandbox, "review-candidate")
                rsi_run["review_closure"].update(
                    candidate_sha256=candidate["candidate_sha256"],
                    checks={
                        check_id: {"evidence": f"Fixture verified {check_id}", "files": [gold_daily]}
                        for check_id in review_evidence.CHECK_IDS
                    },
                )
                checks = rsi_run["review_closure"]["checks"]
                checks["cross_track"]["files"] = ["gold/data_snapshot.json", review_evidence.STATE_PATH]
                checks["primary_sources"]["files"].append(policy_path)
                checks["primary_sources"]["source_urls"] = review["sources"]["real_yield"]
                checks["primary_sources"]["claims"] = [{
                    "file": gold_daily, "excerpt": excerpt, "kind": kind, "source_file": gold_daily,
                    "source_url": source, "verification": "核查实际利率表的当日数据。",
                } for excerpt, kind in ((fact, "fact"), (calculation, "calculation"), (inference, "inference"))]
                checks["primary_sources"]["claims"].append({
                    "file": policy_path, "source_file": policy_path, "policy_brief_id": brief["id"],
                    "excerpt": fact, "kind": "fact", "source_url": source, "verification": "核查实际利率表的当日数据。",
                })
                for track, patch_path in (
                    ("gold", "gold/daily/_rsi_patch.json"), ("equity", "equity/state/_rsi_patch.json"),
                ):
                    (sandbox / patch_path).write_text(json.dumps(rsi_run, ensure_ascii=False), encoding="utf-8")
                    with self.subTest(track=track):
                        self.assertEqual(psd.main([f"--append-{track}-rsi"]), 0)

            for rel in (
                "equity/state/multi_asset_channels.json",
                "equity/state/etf_universe.json",
                "equity/state/deep_dossiers.json",
            ):
                self.assertEqual(json.loads((sandbox / rel).read_text(encoding="utf-8"))["edition_id"], mid_ed)

    def test_multi_error_accumulation_inspect_hint_uk_region_and_line1_marker(self):
        real_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            (sandbox / "gold" / "daily").mkdir(parents=True)
            (sandbox / "equity" / "state").mkdir(parents=True)
            for rel in (
                "gold/data_snapshot.json",
                "gold/daily/CHANGELOG.md",
                "gold/daily/AUDIT_LOG.md",
                "equity/state/market_state.json",
                "equity/state/multi_asset_channels.json",
                "equity/state/etf_universe.json",
                "equity/state/deep_dossiers.json",
                "equity/state/policy_calendar.json",
            ):
                shutil.copy2(real_root / rel, sandbox / rel)

            ed = json.loads((sandbox / "equity/state/market_state.json").read_text(encoding="utf-8"))["edition_id"]
            before_mac = (sandbox / "equity/state/multi_asset_channels.json").read_text(encoding="utf-8")

            # 1. Inspect policy-calendar returns real key 'events' + patch_schema_hint with UK
            out_buf = StringIO()
            with patch.object(psd, "REPO_ROOT", sandbox), redirect_stdout(out_buf):
                rc_insp = psd.main(["--inspect", "policy-calendar"])
            self.assertEqual(rc_insp, 0)
            insp = json.loads(out_buf.getvalue())
            self.assertIn("events", insp)
            self.assertNotIn("upcoming_events", insp)
            self.assertIn("patch_schema_hint", insp)
            self.assertIn("UK", insp["patch_schema_hint"]["valid_regions"])
            self.assertIn("UK", psd.POLICY_CAL_REGIONS)

            # 2. Multi-error accumulation across multiple DBs fails once with ALL errors and writes ZERO files
            future_ev_date = (date.fromisoformat(ed[:10]) + timedelta(days=5)).isoformat()
            bad_patch = {
                "edition_id": ed,
                "multi_asset_channels": {
                    "channels_patch": {
                        "qdii_mrf": {"today_alert": "建议立即买入 BTC 与以太坊避险"}
                    }
                },
                "etf_universe": {
                    "etfs_upsert": [{"code": "999999", "name": "缺字段新基"}]
                },
                "policy_calendar": {
                    "events_upsert": [{
                        "event_id": f"uk_bad_prose_{future_ev_date.replace('-', '')}",
                        "date_cst": future_ev_date,
                        "end_date_cst": future_ev_date,
                        "date_precision": "exact",
                        "time_cst": "20:00",
                        "region": "UK",
                        "category": "central_bank",
                        "impact_tier": "P0",
                        "title": "英国央行议息（这是 P0 重磅事件）",
                        "affected_markets": ["non_us_global_satellite"],
                        "expected_consensus": "维持利率不变",
                        "market_transmission": "英债波动",
                        "watch_triggers": {"upside_bull": "温和降息", "downside_bear": "通胀偏热"},
                        "pre_event_stance": "保持防守",
                        "source_url": "https://www.bankofengland.co.uk/",
                        "monitor_window_min": 60,
                    }]
                },
            }
            (sandbox / "equity/state/_edition_patch.json").write_text(
                json.dumps(bad_patch, ensure_ascii=False), encoding="utf-8"
            )
            with patch.object(psd, "REPO_ROOT", sandbox):
                err_buf = StringIO()
                with redirect_stderr(err_buf):
                    rc = psd.main(["--apply"])
            self.assertNotEqual(rc, 0)
            err_txt = err_buf.getvalue()
            self.assertIn("银发〔2026〕42号", err_txt)
            self.assertIn("asset_class", err_txt)
            self.assertIn("region", err_txt)
            self.assertIn("P0", err_txt)
            # Zero partial writes on failure
            self.assertEqual((sandbox / "equity/state/multi_asset_channels.json").read_text(encoding="utf-8"), before_mac)

            # 3. --prepend-gold-ledgers rejects heading before <!-- GOLD_EDITION_* --> marker (using fresh sentinel edition!)
            sentinel_ed = "2099-12-31_1800"
            gold_snap_s = json.loads((sandbox / "gold/data_snapshot.json").read_text(encoding="utf-8"))
            gold_snap_s.update(edition_id=sentinel_ed, as_of_short="2099-12-31 18:00")
            (sandbox / "gold/data_snapshot.json").write_text(json.dumps(gold_snap_s, ensure_ascii=False), encoding="utf-8")
            bad_ledger = {
                "edition_id": sentinel_ed,
                "changelog_entry_md": f"## {sentinel_ed} 错误顺序标题\n<!-- GOLD_EDITION_CHANGELOG {sentinel_ed} -->\n- 记录。\n",
                "audit_review_block_md": f"### {sentinel_ed} 错误顺序\n<!-- GOLD_EDITION_REVIEW {{\"edition_id\": \"{sentinel_ed}\"}} -->\n",
            }
            (sandbox / "gold/daily/_ledger_patch.json").write_text(
                json.dumps(bad_ledger, ensure_ascii=False), encoding="utf-8"
            )
            with patch.object(psd, "REPO_ROOT", sandbox):
                err_buf2 = StringIO()
                with redirect_stderr(err_buf2):
                    rc2 = psd.main(["--prepend-gold-ledgers"])
            self.assertNotEqual(rc2, 0)
            self.assertIn("first non-empty line", err_buf2.getvalue())

    def test_rollover_equity_month_flagship_cutoff_re_tag_and_as_of_short(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "equity" / "state").mkdir(parents=True)
            for mkt in psd.ROLLOVER_MARKETS:
                md = (
                    f"# {mkt} 手册\n\n"
                    "## 附录二：龙头总表\n\n"
                    "| 序号 | 代码 | 名称 |\n| :---: | :---: | :--- |\n"
                    "| 1 | `600036` | 招商银行 |\n"
                )
                (root / "equity" / f"{mkt}_market_report_2026_11.md").write_text(md, encoding="utf-8")
                (root / "equity" / f"{mkt}_market_report_latest.md").write_text(md, encoding="utf-8")
                meta = {
                    "period_slug": "2026_11",
                    "version": "2026年11月刊",
                    "tag": "2026年11月旗舰深度手册",
                    "title": f"{mkt} 标题",
                    "benchmark_time": "2026-11-28 18:00 北京时间",
                    "page_footer": f"{mkt} 手册（2026年11月）",
                    "chart_live": {
                        "as_of_full": "2026-11-28 18:00 北京时间",
                        "as_of_short": "2026-11-28",
                        "as_of_year_float": 2026.91,
                    },
                }
                (root / "equity" / f"report_meta_{mkt}.json").write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )

            patch_path = root / "equity/state/_rollover_patch.json"
            base_patch = {
                "prev_period_slug": "2026_11",
                "new_period_slug": "2026_12",
                "as_of_full": "2026-12-01 07:55 北京时间",
                "as_of_year_float": 2026.916,
                "benchmark_time": "2026-12-01 07:55 北京时间",
                "markets": {
                    "a_share": {"tag": "2026-12 A股定制标签", "as_of_short": "2026-12-01"},
                },
            }

            # 1. Rejects as_of_full missing HH:MM
            patch_path.write_text(
                json.dumps({**base_patch, "as_of_full": "2026-12-01 北京时间"}, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "YYYY-MM-DD HH:MM"):
                psd.rollover_equity_month(root, dry_run=True)

            # 2. Accepts Chinese date format YYYY年MM月DD日 HH:MM
            patch_path.write_text(
                json.dumps({**base_patch, "as_of_full": "2026年12月01日 07:55 北京时间"}, ensure_ascii=False),
                encoding="utf-8",
            )
            res_cn = psd.rollover_equity_month(root, dry_run=True)
            self.assertEqual(res_cn["files_staged"], 9)

            # 3. Accepts ISO YYYY-MM-DD HH:MM, applies tag/as_of_short overrides, and auto-updates period in tag
            patch_path.write_text(json.dumps(base_patch, ensure_ascii=False), encoding="utf-8")
            psd.rollover_equity_month(root, dry_run=False)
            meta_a = json.loads((root / "equity/report_meta_a_share.json").read_text(encoding="utf-8"))
            meta_hk = json.loads((root / "equity/report_meta_hk_stock.json").read_text(encoding="utf-8"))
            self.assertEqual(meta_a["tag"], "2026-12 A股定制标签")
            self.assertEqual(meta_a["chart_live"]["as_of_short"], "2026-12-01")
            self.assertEqual(meta_hk["tag"], "2026年12月旗舰深度手册")

    def test_policy_calendar_rejects_empty_briefs_replace_and_non_string_dict_event_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_clean_fixture(root, edition_id="2026-11-28_1800", as_of_date="2026-11-28")
            pcal = {
                "edition_id": "2026-11-28_1800",
                "as_of_cst": "2026-11-28T18:00:00+08:00",
                "horizon_days": 30,
                "policy_briefs": [
                    {
                        "id": "b_keep_1",
                        "date_cst": "2026-11-28",
                        "time_cst": "10:00",
                        "region": "CN",
                        "category": "policy_regulation",
                        "impact_tier": "P1",
                        "authority": "央行",
                        "headline": "央行保持流动性合理充裕",
                        "summary": "平稳投放。",
                        "affected_markets": ["a_share"],
                        "market_impact": "维持稳健底座。",
                        "source_url": "https://www.pbc.gov.cn/",
                    }
                ],
                "events": [],
            }
            (root / "equity/state/policy_calendar.json").write_text(
                json.dumps(pcal, ensure_ascii=False), encoding="utf-8"
            )
            patch_path = root / "equity/state/_edition_patch.json"

            # 1. Empty policy_briefs_replace: [] rejected
            patch_path.write_text(
                json.dumps(
                    {"edition_id": "2026-11-28_1800", "policy_calendar": {"policy_briefs_replace": []}},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            err1 = StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stderr(err1):
                rc1 = psd.main(["--apply"])
            self.assertNotEqual(rc1, 0)
            self.assertIn("non-empty list", err1.getvalue())

            # 2. Non-string event_id in dict events_upsert rejected cleanly
            patch_path.write_text(
                json.dumps(
                    {
                        "edition_id": "2026-11-28_1800",
                        "policy_calendar": {
                            "events_upsert": {
                                "ev_bad": {
                                    "event_id": 12345,
                                    "date_cst": "2026-12-05",
                                    "end_date_cst": "2026-12-05",
                                    "date_precision": "exact",
                                    "time_cst": "21:30",
                                    "region": "US",
                                    "category": "macro_data",
                                    "impact_tier": "P1",
                                    "title": "非字符串编号事件",
                                    "affected_markets": ["us_stock"],
                                    "expected_consensus": "测试",
                                    "market_transmission": "测试",
                                    "pre_event_stance": "防守",
                                    "source_url": "https://www.bls.gov/",
                                }
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            err2 = StringIO()
            with patch.object(psd, "REPO_ROOT", root), redirect_stderr(err2):
                rc2 = psd.main(["--apply"])
            self.assertNotEqual(rc2, 0)
            self.assertIn("non-empty string 'event_id'", err2.getvalue())


if __name__ == "__main__":
    unittest.main()
