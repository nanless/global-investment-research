#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprehensive unit tests for patch_state_dbs, edition_run telemetry, publish_site guards, and permissions."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import edition_run, install_sidecars, patch_state_dbs as psd, publish_site


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

            # Clarifying 仅恢复赎回 passes!
            eu["etfs"][1]["premium_status"] = "high_risk"
            eu["etfs"][1]["premium_note"] = "暂停申购仅恢复赎回（不开放申购，勿误读为恢复申赎）"
            errs_pass = psd._validate_merged_equity_dbs(
                ma, eu, dd, edition_id="2026-11-27_0730", gold_tier0_active=True, expected_pool=6,
                as_of_date="2026-11-27", market_state=ms,
            )
            self.assertEqual(errs_pass, [])

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


class AtomicRsiAuditAndInspectTests(unittest.TestCase):
    def _valid_rsi_entry(self, run_id: str) -> dict:
        return {
            "run_id": run_id,
            "edition_type": "weekday_evening_unified",
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
            seed = {"schema_version": "1.0", "runs": [{"run_id": "2026-11-27_0730"}]}
            gold_rsi.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            eq_rsi.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            gold_patch = root / "gold/daily/_rsi_patch.json"
            eq_patch = root / "equity/state/_rsi_patch.json"
            entry = self._valid_rsi_entry("2026-11-27_1800")

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
                    self.assertEqual(st["phase_timestamps"]["begin"], "2026-11-27T18:00:00+08:00")
                    self.assertEqual(st["phase_timestamps"]["gold"], "2026-11-27T18:10:00+08:00")
                    self.assertEqual(st["phase_timestamps"]["equity"], "2026-11-27T18:18:00+08:00")
                    self.assertEqual(st["phase_timestamps"]["publish"], "2026-11-27T18:30:00+08:00")
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
        for verb in ("--append-gold-rsi", "--append-equity-rsi", "--prepend-equity-audit", "--inspect"):
            self.assertIn(f"command(python3 __REPO_ROOT__/scripts/patch_state_dbs.py {verb})", perms)
            self.assertIn(f"command(__PYTHON_BIN__ __REPO_ROOT__/scripts/patch_state_dbs.py {verb})", perms)
        for entry in perms:
            self.assertNotIn("*", entry)
            self.assertIsNone(install_sidecars.SHELL_INJECTION_RE.search(entry))
            for forbidden in ("complete-superseded", "close-superseded", "edition_run.py recover", "edition_run.py resume"):
                self.assertNotIn(forbidden, entry)
        for _, tpl_path in install_sidecars.discover_templates(repo / "automations" / "sidecars"):
            install_sidecars.render_template(tpl_path, repo, sys.executable)


if __name__ == "__main__":
    unittest.main()
