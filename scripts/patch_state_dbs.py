#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-dependency atomic incremental merge & lossless ledger prepender.

Prevents 300s streaming write timeouts during automated editions by applying
compact patch files with full pre-write forensic validation and all-or-nothing
transactional rollback.

Fixed safe commands (no arbitrary external path arguments accepted):
  python3 scripts/patch_state_dbs.py --apply [--dry-run] [--keep-patch] [--skip-edition-lock]
  python3 scripts/patch_state_dbs.py --prepend-gold-ledgers [--dry-run] [--keep-patch]
  python3 scripts/patch_state_dbs.py --append-gold-rsi [--dry-run] [--keep-patch]
  python3 scripts/patch_state_dbs.py --append-equity-rsi [--dry-run] [--keep-patch]
  python3 scripts/patch_state_dbs.py --prepend-equity-audit [--dry-run] [--keep-patch]
  python3 scripts/patch_state_dbs.py --rollover-equity-month [--dry-run] [--keep-patch]
  python3 scripts/patch_state_dbs.py --archive-gold-ledgers [--dry-run] [--keep-patch]
  python3 scripts/patch_state_dbs.py --inspect <target>
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import date, datetime, timedelta
from functools import wraps
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit

if __package__:
    from . import review_evidence
    from .inventory_evidence import ETF_FIELDS, STOCK_FIELDS, inventory_evidence, load_research_json, retain_inventory_evidence
    from .source_links import is_https_source as _is_strict_https_url, policy_extra_source_error
    from .state_transaction import install_locked, state_read_lock, state_write_lock
else:
    import review_evidence
    from inventory_evidence import ETF_FIELDS, STOCK_FIELDS, inventory_evidence, load_research_json, retain_inventory_evidence
    from source_links import is_https_source as _is_strict_https_url, policy_extra_source_error
    from state_transaction import install_locked, state_read_lock, state_write_lock

REPO_ROOT = Path(__file__).resolve().parent.parent
EQUITY_STATE_DIR = REPO_ROOT / "equity" / "state"
POLICY_CALENDAR_PATH = EQUITY_STATE_DIR / "policy_calendar.json"

EDITION_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(0730|1130|1800)(?:_r([2-9]|[1-9]\d+))?")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
POLICY_CLOCK_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
DATA_CONTRACT_CUTOVER = "2026-11-28_1130"
PERIOD_SLUG_RE = re.compile(r"^\d{4}_(0[1-9]|1[0-2])$")
FLAGSHIP_CUTOFF_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{4}年\d{1,2}月\d{1,2}日) +(\d{2}:\d{2})(?!\d)")
ROLLOVER_MARKETS = ("a_share", "hk_stock", "us_stock")

REQUIRED_MULTI_ASSET_CHANNELS = (
    "reverse_repo",
    "large_cds",
    "fx_deposits_wm",
    "bonds",
    "funds_wm",
    "savings_insurance",
    "tax_advantaged_accounts",
    "qdii_mrf",
    "convertible_bonds",
    "c_reits",
    "commodity_etfs",
    "private_funds_trust",
)
REQUIRED_CHANNEL_SET = frozenset(REQUIRED_MULTI_ASSET_CHANNELS)
ALLOWED_STATUS_TONES = frozenset({"green", "blue", "amber", "red"})

ETF_REQUIRED_STR_FIELDS = (
    "code",
    "name",
    "market",
    "channel",
    "fee_total_pct",
    "thesis_deep",
    "risk_boundary",
    "action_role",
)
ETF_ALL_21_KEYS = frozenset({
    "code",
    "name",
    "market",
    "market_label",
    "channel",
    "category",
    "tracking_index",
    "aum",
    "fee_total_pct",
    "fee_num",
    "liquidity",
    "yield_or_pe",
    "top_holdings",
    "premium_status",
    "premium_note",
    "tax_and_rules",
    "thesis_deep",
    "risk_boundary",
    "action_role",
    "otc_feeder",
    "gold_locked",
})
ETF_OPTIONAL_KEYS = frozenset({"updated_at", "asset_class", "region", "evidence"})
ETF_NEW_REQUIRED_KEYS = ETF_ALL_21_KEYS | frozenset({"asset_class", "region"})
ETF_ALLOWED_KEYS = ETF_ALL_21_KEYS | ETF_OPTIONAL_KEYS
ETF_ALLOWED_MARKETS = frozenset({"a-share", "hk-stock", "us-stock", "global", "multi-asset"})
ETF_ALLOWED_CHANNELS = frozenset({
    "境内场内",
    "境内场外",
    "离岸港交所",
    "境内非QDII港股通",
    "境内QDII",
    "离岸美股",
    "爱尔兰UCITS",
})
ETF_ALLOWED_PREMIUM_STATUSES = frozenset({"normal", "watch", "high_risk"})
ETF_ALLOWED_ASSET_CLASSES = frozenset({
    "equity",
    "fixed_income",
    "gold",
    "commodity",
    "cash_mmf",
    "convertible_bond",
    "reits",
})
ETF_ALLOWED_REGIONS = frozenset({
    "cn",
    "hk",
    "us",
    "jp",
    "eu",
    "apac_em",
    "global",
})
MIN_ETF_COUNT = 140
LIVE_MIN_ETF_COUNT = 181
MAX_ETF_DELTA = 10

DOSSIER_DIMENSIONS = (
    "moat",
    "financials",
    "valuation_anchor",
    "shareholder_flow",
    "catalysts",
    "bear_case",
    "action_etf",
)

POLICY_CAL_ALLOWED_REGIONS = frozenset({"CN", "HK", "US", "EU", "UK", "JP", "GLOBAL"})
POLICY_CAL_REGIONS = POLICY_CAL_ALLOWED_REGIONS
BARE_IMPACT_TIER_RE = re.compile(r"(?<![A-Za-z0-9])P[0-2](?![A-Za-z0-9])")
POLICY_CAL_PROSE_SKIP_KEYS = frozenset({"impact_tier", "event_id", "brief_id", "id", "source_url", "source_urls"})
POLICY_CAL_ALLOWED_CATEGORIES = frozenset({
    "top_politics",
    "central_bank",
    "macro_data",
    "fiscal_policy",
    "regulation_trade",
    "geopolitics_energy",
    "liquidity_treasury",
    "market_structure",
    "holiday_schedule",
})
POLICY_CAL_ALLOWED_TIERS = frozenset({"P0", "P1", "P2"})
POLICY_CAL_ALLOWED_PRECISIONS = frozenset({"exact", "window_tbd"})
POLICY_CAL_ALLOWED_MARKETS = frozenset({
    "a_share",
    "hk_stock",
    "us_stock",
    "rates_bonds_core",
    "gold",
    "non_us_global_satellite",
})
ALLOWED_POLICY_CALENDAR_TOP_KEYS = frozenset({"as_of_cst", "horizon_days", "schema_version"})
POLICY_CAL_MIN_HORIZON_DAYS = 14
POLICY_CAL_REQUIRED_BRIEF_STR_FIELDS = (
    "id",
    "date_cst",
    "region",
    "category",
    "impact_tier",
    "authority",
    "headline",
    "summary",
    "market_impact",
)
POLICY_CAL_REQUIRED_EVENT_STR_FIELDS = (
    "event_id",
    "date_cst",
    "end_date_cst",
    "date_precision",
    "time_cst",
    "region",
    "category",
    "impact_tier",
    "title",
    "expected_consensus",
    "market_transmission",
    "pre_event_stance",
    "source_url",
)
POLICY_CAL_EVENT_REQUIRED_KEYS = frozenset(POLICY_CAL_REQUIRED_EVENT_STR_FIELDS) | frozenset({
    "affected_markets",
    "watch_triggers",
    "monitor_window_min",
})

RAW_MARKUP_RE = re.compile(r"\*\*|<br\s*/?>|`", flags=re.IGNORECASE)
EXACT_PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
RANGE_PCT_RE = re.compile(r"\d+(?:\.\d+)?%\s*[–\-~至]\s*\d+(?:\.\d+)?%")
RESTRICTED_CODES_RE = re.compile(r"(?<![0-9])(?:968118|968001|00011)(?![0-9])")
RESTRICTED_WARN_RE = re.compile(
    r"(?:暂停|停申|停购|封盘|已停|停售|限购|退市|私有化|勿买|勿选|勿误配|"
    r"严禁|禁止|严避|禁买|禁推|禁配|禁碰|切忌|避坑|避开|绕开|远离|回避|"
    r"不可|不买|不推|莫买|别买|别碰|慎碰|高危|雷区|警示|清盘|剔除|弃用|改以|替代)"
)

ENTRY_GATE_IDS = ("real_yield", "rate_spread", "vix", "ny_close")
AS_OF_SHORT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
ALLOWED_FORECAST_REVIEW_STATUSES = frozenset({"settled", "none_due", "pending_evidence"})
DEPRECATED_BINARY_LINK_RE = re.compile(
    r"(?:\[[^\]]+\]\((?!https?://)[^)\s]+\.(?:pdf|docx)(?:#[^)\s]*)?\)"
    r"|/releases/download/"
    r"|\{md,pdf,docx\}"
    r"|(?:daily/|archive/|\.\.?/)[^\s`\"'()<>]+\.(?:pdf|docx))",
    flags=re.IGNORECASE,
)
FEE_EXCLUDE_SPAN_RE = re.compile(
    r"(?:申购费?|赎回费?|1折|一折|佣金|销服(?:优惠至|费)?|销售服务费)"
    r"[^\s｜|，,；;）)。”\"·]{0,12}?"
    r"\d+(?:\.\d+)?%(?:\s*[–\-~至]\s*\d+(?:\.\d+)?%)?"
)
DYNAMIC_SIGNED_PCT_RE = re.compile(r"(?<![0-9A-Za-z%])[+\-]\d+(?:\.\d+)?%")
DYNAMIC_COUNT_RE = re.compile(r"\d+\s*只(?:跨境|纳指|美股|停牌)")
DYNAMIC_USD_5DIGIT_RE = re.compile(r"\$[0-9]{2,3},[0-9]{3}(?!\d)")
HISTORICAL_CTX_RE = re.compile(
    r"(?:对\d+/\d+|较|原|前日|昨日|自.{0,8}降至|由.{0,8}升至|历史|(?<!\d)(?:0?[1-9]|1[0-2])/\d{1,2}(?!\d))"
)
BTC_HISTORICAL_CTX_RE = re.compile(
    r"(?:对\d+/\d+|较|原|前日|昨日|自.{0,8}降至|由.{0,8}升至|历史|均价|成本|此前)"
)
AH_PREMIUM_MENTION_RE = re.compile(
    r"(?:(?:AH|A/H)\s*(?:罕见|深度|仍呈)?(?:溢价|倒挂|折价)|"
    r"A\s*股较\s*H\s*股[^，。；]{0,24}?溢价|"
    r"A\s*折\s*H(?:\s*倒挂)?)"
    r"[^0-9+\-，。；（）]{0,14}([+\-]?\d+(?:\.\d+)?)%"
    r"(?:\s*[–\-~～至]\s*([+\-]?\d+(?:\.\d+)?)%)?"
)
AH_NEGATIVE_WORD_RE = re.compile(r"(?:倒挂|A\s*折\s*H|折价)")
AH_HISTORICAL_CTX_RE = re.compile(r"(?:历史中枢|历史均值|过去)")
AH_PREMIUM_TOLERANCE_PP = 0.6
HK_4DIGIT_RE = re.compile(r"(?<![0-9])\d{4}\.HK(?![A-Za-z0-9])")
A_SHARE_DIVIDEND_RE = re.compile(
    r"股息率\s*(?:约|近|逾|高达|达|为|仅|在|~|超|不足|低于|高于)?\s*(\d+(?:\.\d+)?)%"
    r"(?:\s*[–\-~～至]\s*(\d+(?:\.\d+)?)%)?"
)
DIVIDEND_QUALIFIER_RE = re.compile(
    r"(?:税后|港股通|中期|半年|特别|历史|原|旧|前|目标|门槛|行业|均值|中证红利|同业|对比|较|H\s*股|离岸|扣税|净股息)"
)
A_SHARE_DIVIDEND_TOLERANCE_PP = 0.15
QDII_RESTRICTED_NOTE_RE = re.compile(r"(?:暂停申购|限购|封盘)")
OTC_SUSPENDED_NOTE_RE = re.compile(r"(?:场外.{0,8}暂停申购|场外.{0,8}申购.{0,4}暂停)")
OTC_DISCLOSURE_RE = re.compile(r"(?:限购|暂停)")
IOPV_RE = re.compile(r"(?<![A-Za-z])IOPV(?![A-Za-z])", flags=re.IGNORECASE)
IOPV_GLOSS_RE = re.compile(r"(?:参考净值|实时净值|盘中净值)")
CHANNEL_META_KEYS = frozenset({
    "id", "order", "category", "category_label", "money_bucket",
    "high_net_worth_only", "min_amount_tier", "risk_stars", "status_tone",
    "related_etf_codes",
})
DOSSIER_META_KEYS = frozenset({"market", "code", "name", "depth_tier", "updated_at", "evidence"})

GOLD_ETF_CODES = frozenset({
    "518660", "518880", "518850", "159934", "159937", "518800",
    "517520", "159562", "02840", "03081",
    "GLD", "IAU", "IAUM", "GLDM", "IGLN", "GDX", "GDXJ",
})
GOLD_ETF_NAME_RE = re.compile(
    r"(?<!非)(?:黄金|金矿|实物金|沪金|金股|SPDR\s*金(?!融)|SPDR\s*Gold|iShares\s*Gold|Physical\s*Gold|Gold\s*Miners)",
    flags=re.IGNORECASE,
)
GOLD_ETF_FORBIDDEN_ROLE_RE = re.compile(r"(?:底座|买入|推荐|定投|配置|建仓|吸纳|加仓)")
GOLD_DOSSIER_KEYS = frozenset({
    "a-share:601899", "a-share:600547", "a-share:600489", "a-share:600988", "a-share:000975",
    "hk-stock:02899.HK", "hk-stock:06181.HK", "hk-stock:01929.HK", "hk-stock:01818.HK",
    "hk-stock:01787.HK", "hk-stock:02099.HK",
    "us-stock:NEM", "us-stock:B", "us-stock:AEM", "us-stock:WPM", "us-stock:FNV",
})
GOLD_BASE_ROLE_RE = re.compile(r"(?:当下底座|绿色底座|🟢)")
GOLD_BASE_NEGATION_RE = re.compile(
    r"(?:严禁|禁止|切忌|不可|不得|暂不|不宜|绝不|决不|不要|不能|不|非|不是|勿)"
    r"(?:(?:新买|买入|买进|加仓|建仓|定投|配置|补仓|补齐|购买|追买|抢权|抄底|推荐|纳入|视为|作为|当成|列为|标为)"
    r"(?:[/／、及与和或]|且|亦|也|更)?(?:严禁|禁止|切忌|不可|不得|暂不|不宜|绝不|不|勿)?){0,4}"
    r"(?:列为|标为|作为|当成|视为|纳入|归为|定为)?[\s“‘「\x22*_]*$"
)
GOLD_ACTIVE_BUY_RE = re.compile(
    r"(?:补齐|补足|买入|买进|加仓|加配|抄底|逢低买|低吸|布局|上车|新买|买|定投|配置|建仓|吸纳)"
    r"\s*(?:[0-9一二两三半成%–\-~约近超]*\s*)?"
    r"(?:(?:现货|实物|纸|积存)?(?:黄金|金仓|金矿股?|黄金股)|"
    r"(?:518660|518880|518850|159934|159937|518800|517520|159562|02840|03081|"
    r"(?<![A-Za-z])(?:GLD|IAU|IAUM|GLDM|IGLN|GDX|GDXJ)(?![A-Za-z])))",
    flags=re.IGNORECASE,
)
GOLD_DEFER_GUARD_RE = re.compile(
    r"(?:暂不|严禁|禁止|切忌|勿|停止|暂停|先别|不能|不宜|不要|别急着|拒绝|不考虑|不允许|不应|不会|未在黄金红灯停期|不)"
    r"(?:追高芯片[与或])?(?:现在|今天|今日|当下|任何|立即|马上|急于|立刻|再|去|主动|新|分批|小批|继续|同步|直接|冲动|抢跑)*"
    r"(?:(?:新买|买入|加仓|抄底|定投|配置|建仓|补齐|低吸|布局|上车)[/／、与或])?[\s“‘「\x22*_]*$"
    r"|(?:等到?|待).{0,14}(?:黄灯|绿灯|解锁)(?:亮起|确认)?(?:后)?(?:再|才)?(?:分批|择机|恢复|重启|再)*[\s“‘「\x22]*$"
    r"|(?:黄灯|绿灯|解锁|过四关|全部过关)(?:亮起|确认)?后(?:再|才)?(?:分批|择机|恢复|重启|再)*[\s“‘「\x22]*$"
    r"|(?:原稿曾建议|原稿曾考虑|过去曾建议|曾建议)[\s“‘「\x22]*$"
)
GOLD_MINER_TICKERS_RE = re.compile(
    r"(?:NEM|纽蒙特|山东黄金|中金黄金|赤峰黄金|山金国际|紫金黄金|紫金矿业|招金|老铺黄金|周大福|"
    r"GLD|GLDM|IAU|IAUM|IGLN|GDX|GDXJ|518660|518880|518850|518800|517520|159934|159937|159562|02840|03081|02899|06181|01929)",
    flags=re.IGNORECASE,
)
CRYPTO_ACTIVE_BUY_RE = re.compile(
    r"(?:补齐|补足|买入|买进|加仓|加配|抄底|逢低买|低吸|布局|上车|新买|买|定投|配置|配仓|建仓|吸纳|购入|做多)"
    r"\s*(?:[0-9一二两三半成%–\-~约近超少量小批分批]*\s*)?"
    r"(?:(?:现货|数字|虚拟|加密)?(?:比特币|以太坊|虚拟货币|加密货币|加密资产|稳定币)|"
    r"(?<![A-Za-z0-9])(?:BTC|ETH|USDT|USDC|IBIT|FBTC)(?![A-Za-z0-9]))"
    r"|\b(?:buy|add|accumulate|allocate(?:\s+to)?|dca\s+into)\s+(?:btc|bitcoin|eth|ethereum|crypto(?:currency)?)\b",
    flags=re.IGNORECASE,
)
CRYPTO_NEGATION_GUARD_RE = re.compile(
    r"(?:严禁|禁止|切忌|勿|不得|不可|不能|不宜|不要|绝不|决不|暂不|停止|拒绝|不允许|不应|不会|0%\s*(?:严禁|禁止)?|零配|不)"
    r"(?:现在|今天|今日|当下|任何|立即|马上|急于|立刻|再|去|主动|新|分批|小批|继续|参与|涉及|尝试|建议|允许|新增|直接|盲目|变相)*"
    r"(?:(?:新买|买入|买进|加仓|抄底|定投|配置|配仓|建仓|低吸|布局|上车|交易|炒作|买卖|持有)[/／、与及和或])?[\s“‘「\x22*_]*$"
    r"|(?:严禁|禁止|不得|切忌|不可|绝不)(?:[^。！？；，,|但可应须宜]{0,14})(?:与|及|和|或|、|/|／)[\s“‘「\x22*_]*$"
    r"|\b(?:do\s+not|never|must\s+not|should\s+not|prohibit(?:ed|s)?|ban(?:ned|s)?)\s+(?:from\s+)?(?:buy|add|accumulat|allocat|dca|trad)[\w\s]{0,16}$",
    flags=re.IGNORECASE,
)

BANNED_INTERNAL_RE = re.compile(
    r"(?:\bV\d+\.\d+\b|Subagent|红队|法证|\bTier\s*[0-3]\b|\bSSOT\b|"
    r"build_(?:a_share_pdf|hk_stock_pdf|us_stock_pdf|daily|report|site|pdf)\.py|"
    r"publish_site\.py|pdf_common\.py|docx_embed\.py|lint_(?:equity|readability|site)\.py|"
    r"edition_(?:run|plan|validation)\.py|patch_state_dbs\.py|fetch_kline_data\.py|realtime_monitor\.py|wechat_notify\.py|artifact_receipt\.py|chart_input\.py|install_sidecars\.py|svg_geometry\.py|visual_widgets\.py|"
    r"DAILY_REPORT_SPEC\.md|DAILY_FORMAT_SPEC\.md|audit_ledger\.md|market_state\.json|"
    r"multi_asset_channels\.json|etf_universe\.json|deep_dossiers\.json|policy_calendar\.json|market_calendar\.json|"
    r"edition-runs\.sqlite3|realtime-monitor\.sqlite3|notify\.example\.json|notify\.json|"
    r"master_snapshot\.json|data_snapshot\.json|_edition_patch\.json|_ledger_patch\.json|_rsi_patch\.json|_audit_patch\.json|_rollover_patch\.json|_archive_patch\.json|"
    r"unified-edition\.prompt\.md|permissions\.json|"
    r"AGENTS\.md|GEMINI\.md|SKILL\.md|sidecar\.json|"
    r"RSI_PLAYBOOK(?:\.md)?|rsi_metrics\.json|Meta-RSI|Recursive\s+Self-Improvement|"
    r"next_run_watch|rsi_self_review_protocol|"
    r"RSI\s*(?:自(?:我|优|评|检|进)|盲审|复盘|闭环|体检|遥测|打分|简报|手册|进化|迭代|协议)|"
    r"\bTier\s*[ABC](?:/[ABC])+\b|"
    r"\bTier\s*[ABC]\s*(?:自|提案|补丁|改进|优化|经验|规则|落盘|落地|架构|锁定|权限|边界|评估|升级)|"
    r"20\d{6}_1\.csv|适配手机端免横滑)",
    flags=re.IGNORECASE,
)
LOCAL_PATH_RE = re.compile(r"(?:file:///|/Users/|/home/|[A-Za-z]:\\Users\\|/opt/homebrew/)")

GOLD_REVIEW_BLOCK_RE = re.compile(r"<!--\s*GOLD_EDITION_REVIEW\s+(\{.*?\})\s*-->", re.DOTALL)
GOLD_CHANGELOG_MARKER_RE = re.compile(r"<!--\s*GOLD_EDITION_CHANGELOG\s+([^\s]+)\s*-->")

ALLOWED_EQUITY_PATCH_TOP_KEYS = frozenset({
    "edition_id",
    "as_of_date",
    "as_of_label",
    "gold_tier0_locked",
    "gold_mutex_note",
    "gold_lock_notice",
    "multi_asset_channels",
    "etf_universe",
    "deep_dossiers",
    "policy_calendar",
    "note",
    "summary",
})
ALLOWED_MULTI_ASSET_PATCH_KEYS = frozenset({"top_level_updates", "channels_patch"})
ALLOWED_ETF_PATCH_KEYS = frozenset({"top_level_updates", "etfs_upsert", "etfs_remove"})
ALLOWED_DOSSIERS_PATCH_KEYS = frozenset({"top_level_updates", "dossiers_patch"})
ALLOWED_POLICY_CALENDAR_PATCH_KEYS = frozenset({
    "top_level_updates",
    "policy_briefs_replace",
    "events_upsert",
    "events_remove",
})
ALLOWED_LEDGER_PATCH_KEYS = frozenset({
    "edition_id",
    "changelog_entry_md",
    "audit_review_block_md",
    "audit_source_index_md",
    "note",
})
ALLOWED_EQUITY_AUDIT_PATCH_KEYS = frozenset({
    "edition_id",
    "entry_md",
    "note",
})
ALLOWED_ROLLOVER_PATCH_KEYS = frozenset({
    "prev_period_slug",
    "new_period_slug",
    "as_of_full",
    "as_of_year_float",
    "benchmark_time",
    "markets",
    "note",
})
ALLOWED_ROLLOVER_MARKET_KEYS = frozenset({
    "version",
    "page_footer",
    "benchmark_time",
    "title",
    "subtitle",
    "tag",
    "as_of_short",
    "header_replacements",
})
ALLOWED_ARCHIVE_PATCH_KEYS = frozenset({
    "archive_period",
    "note",
})
ALLOWED_RSI_FINDING_STATUSES = frozenset({"resolved", "deferred_data", "disclosed_caveat"})
RSI_REQUIRED_SCORE_KEYS = (
    "data_freshness_and_zero_hallucination",
    "prior_forecast_calibration",
    "plain_language_and_strict_readability",
    "visual_layout_and_pagination",
    "research_efficiency_and_source_quality",
    "engine_and_guardrail_reliability",
)


def _safe_repo_path(repo_root: Path, *parts: str) -> Path:
    root = repo_root.resolve()
    target = (root.joinpath(*parts)).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Path escapes repository root: {parts!r}")
    return target


def _validate_edition_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("edition_id must be a string (YYYY-MM-DD_0730, YYYY-MM-DD_1130 or YYYY-MM-DD_1800[_rN]).")
    m = EDITION_RE.fullmatch(value.strip())
    if m is None:
        raise ValueError(f"Invalid edition_id format: {value!r}")
    try:
        datetime.strptime(m.group(1), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid calendar date in edition_id {value!r}: {exc}") from exc
    return value.strip()


def _validate_date(value: object, label: str) -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value.strip()):
        raise ValueError(f"{label} must be YYYY-MM-DD, got {value!r}")
    val = value.strip()
    try:
        datetime.strptime(val, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid {label} date {val!r}: {exc}") from exc
    return val


def _validate_iso_cst_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an ISO-8601 +08:00 timestamp string, got {value!r}")
    val = value.strip()
    try:
        dt = datetime.fromisoformat(val)
    except ValueError as exc:
        raise ValueError(f"Invalid {label} ISO-8601 timestamp {val!r}: {exc}") from exc
    if dt.utcoffset() != timedelta(hours=8):
        raise ValueError(f"{label} must specify +08:00 timezone offset, got {val!r}")
    return val


def _live_edition_as_of_label(edition_id: str, value: object) -> str:
    as_of = datetime.fromisoformat(_validate_iso_cst_timestamp(value, "market_state.json.as_of_cst"))
    scheduled = datetime.strptime(f"{edition_id[:15]}+0800", "%Y-%m-%d_%H%M%z")
    if not -timedelta(minutes=5) <= as_of - scheduled <= timedelta(hours=6):
        raise ValueError("market_state.json.as_of_cst must fall inside the Beijing window for the current edition.")
    day_label = "一二三四五六日"[as_of.weekday()]
    slot_label = {"0730": "早刊", "1130": "午刊", "1800": "晚刊"}[edition_id[11:15]]
    weekend = "周末" if scheduled.weekday() >= 5 else ""
    return f"{as_of.year}年{as_of.month}月{as_of.day}日（周{day_label}）{as_of:%H:%M} {weekend}{slot_label}"


def _normalize_etf_code(code: object) -> str:
    raw = str(code or "").strip().upper()
    base = re.sub(r"\.(?:HK|L|SS|SZ|US)$", "", raw)
    if base.isdigit() and len(base) == 4:
        return base.zfill(5)
    return base


def _walk_json_strings(
    obj: object,
    path: str = "",
    *,
    skip_keys: frozenset[str] = frozenset({
        "schema_version", "id", "edition_id", "as_of_date", "updated_at",
        "category", "status_tone", "asset_class", "region",
    }),
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(obj, str):
        out.append((path, obj))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            out.extend(_walk_json_strings(item, f"{path}[{i}]", skip_keys=skip_keys))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in skip_keys:
                continue
            child = f"{path}.{k}" if path else str(k)
            out.extend(_walk_json_strings(v, child, skip_keys=skip_keys))
    return out


def _scan_text_for_gold_buy(label: str, text: str) -> list[str]:
    found: list[str] = []
    for idx, ln in enumerate(text.splitlines(), 1):
        if any(
            not GOLD_DEFER_GUARD_RE.search(re.split(r"[。！？；，,、|]", ln[: action.start()])[-1])
            for action in GOLD_ACTIVE_BUY_RE.finditer(ln)
        ):
            found.append(
                f"Gold Tier-0 互斥冲突 ({label}:L{idx})：黄金红灯停期严禁下达新买/补齐黄金指令 -> {ln.strip()[:72]}"
            )
    return found


def _scan_text_for_crypto_buy(label: str, text: str) -> list[str]:
    found: list[str] = []
    for idx, ln in enumerate(text.splitlines(), 1):
        for action in CRYPTO_ACTIVE_BUY_RE.finditer(ln):
            prefix = re.split(r"[。！？；，,|]", ln[: action.start()])[-1]
            if not CRYPTO_NEGATION_GUARD_RE.search(prefix):
                found.append(
                    f"银发〔2026〕42号虚拟货币合规冲突 ({label}:L{idx})：中国大陆严禁个人配仓/买入虚拟货币 -> {ln.strip()[:72]}"
                )
                break
    return found


def _read_json_obj(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Missing required JSON file: {label}")
    try:
        obj = load_research_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot parse {label}: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError(f"{label} root must be a JSON object.")
    return obj


def _serialize_json(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _extract_annual_fee_pcts(fee_text: str) -> list[float]:
    cleaned = FEE_EXCLUDE_SPAN_RE.sub("", fee_text)
    return [float(m.group(1)) for m in re.finditer(r"(\d+(?:\.\d+)?)%", cleaned)]


def _extract_dynamic_tokens(obj: object) -> set[str]:
    tokens: set[str] = set()
    for _, sval in _walk_json_strings(obj, ""):
        for m in DYNAMIC_SIGNED_PCT_RE.finditer(sval):
            tokens.add(m.group(0))
        for m in DYNAMIC_COUNT_RE.finditer(sval):
            tokens.add(re.sub(r"\s+", "", m.group(0)))
        for m in DYNAMIC_USD_5DIGIT_RE.finditer(sval):
            tokens.add(m.group(0))
    return tokens


def _check_sibling_token_drift(
    obj_label: str,
    replaced_tokens: set[str],
    untouched_items: list[tuple[str, str]],
    *,
    errors: list[str] | None = None,
) -> None:
    if not replaced_tokens:
        return
    local_errors: list[str] = errors if errors is not None else []
    for field_path, sval in untouched_items:
        for tok in sorted(replaced_tokens):
            if tok.endswith("%"):
                pat = re.compile(rf"(?<![0-9A-Za-z%]){re.escape(tok)}")
                hist_re = HISTORICAL_CTX_RE
            elif tok.startswith("$"):
                pat = re.compile(rf"{re.escape(tok)}(?![0-9])")
                hist_re = BTC_HISTORICAL_CTX_RE
            else:
                # Allow optional spaces between digits and 只
                m_cnt = re.fullmatch(r"(\d+)(.+)", tok)
                pat = re.compile(rf"(?<![0-9]){m_cnt.group(1)}\s*{re.escape(m_cnt.group(2))}") if m_cnt else re.compile(re.escape(tok))
                hist_re = HISTORICAL_CTX_RE
            for m in pat.finditer(sval):
                win = sval[max(0, m.start() - 20) : min(len(sval), m.end() + 20)]
                if not hist_re.search(win):
                    local_errors.append(
                        f"Stale sibling token drift in {obj_label}.{field_path}: "
                        f"replaced token {tok!r} still appears without historical context -> {win!r}"
                    )
                    break
    if errors is None and local_errors:
        raise ValueError("\n".join(local_errors))


def _atomic_write_transaction(writes: list[tuple[Path, bytes | None]], *, repo_root: Path | None = None) -> None:
    """Run a standalone transaction for callers that already have their output bytes."""
    if not writes:
        return
    if repo_root is None:
        common = Path(os.path.commonpath([path.resolve().parent for path, _ in writes]))
        ancestors = (common, *common.parents)
        repo_root = next((path for path in ancestors if (path / ".git").exists()), None)
        if repo_root is None:
            repo_root = next(path for path in ancestors if path.is_dir())
    with state_write_lock(repo_root):
        install_locked(repo_root, writes)


def _serialize_patch_operation(operation):
    @wraps(operation)
    def wrapped(repo_root: Path = REPO_ROOT, *, dry_run: bool = False, **kwargs):
        lock = state_read_lock if dry_run else state_write_lock
        with lock(repo_root):
            return operation(repo_root, dry_run=dry_run, **kwargs)
    return wrapped


def _commit_patch(
    repo_root: Path, writes: list[tuple[Path, bytes]], patch_path: Path, *, keep_patch: bool,
) -> bool:
    changes: list[tuple[Path, bytes | None]] = list(writes)
    if not keep_patch:
        changes.append((patch_path, None))
    install_locked(repo_root, changes)
    return not keep_patch


def _merge_multi_asset(
    orig: dict[str, Any],
    patch_root: dict[str, Any],
    edition_id: str,
    as_of_date: str,
    *,
    errors: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    local_errors: list[str] = errors if errors is not None else []
    ma = copy.deepcopy(orig)
    ma["edition_id"] = edition_id
    ma["as_of_date"] = as_of_date
    if "as_of_label" in patch_root and patch_root["as_of_label"] is not None:
        if not isinstance(patch_root["as_of_label"], str) or not patch_root["as_of_label"].strip():
            local_errors.append("patch.as_of_label must be a non-empty string.")
        else:
            ma["as_of_label"] = patch_root["as_of_label"].strip()
    if "gold_mutex_note" in patch_root and patch_root["gold_mutex_note"] is not None:
        if not isinstance(patch_root["gold_mutex_note"], str) or not patch_root["gold_mutex_note"].strip():
            local_errors.append("patch.gold_mutex_note must be a non-empty string.")
        else:
            ma["gold_mutex_note"] = patch_root["gold_mutex_note"].strip()

    sec = patch_root.get("multi_asset_channels")
    stats: dict[str, Any] = {
        "top_keys_updated": 0,
        "channels_patched": 0,
        "products_upserted": 0,
        "untouched_channel_siblings": {},
    }
    if sec is None:
        if errors is None and local_errors:
            raise ValueError("\n".join(local_errors))
        return ma, stats
    if not isinstance(sec, dict):
        local_errors.append("patch.multi_asset_channels must be an object.")
        if errors is None and local_errors:
            raise ValueError("\n".join(local_errors))
        return ma, stats
    unknown_sec = set(sec.keys()) - ALLOWED_MULTI_ASSET_PATCH_KEYS
    if unknown_sec:
        local_errors.append(
            f"Unknown key(s) in multi_asset_channels patch: {sorted(unknown_sec)} "
            f"(allowed: {sorted(ALLOWED_MULTI_ASSET_PATCH_KEYS)})"
        )

    top_upd = sec.get("top_level_updates")
    if top_upd is not None:
        if not isinstance(top_upd, dict):
            local_errors.append("multi_asset_channels.top_level_updates must be an object.")
        else:
            if "channels" in top_upd:
                local_errors.append("Use multi_asset_channels.channels_patch instead of replacing top-level 'channels'.")
            for k, v in top_upd.items():
                if k == "channels":
                    continue
                ma[k] = copy.deepcopy(v)
                stats["top_keys_updated"] += 1

    ch_patch = sec.get("channels_patch")
    if ch_patch is not None:
        if not isinstance(ch_patch, dict):
            local_errors.append("multi_asset_channels.channels_patch must be an object keyed by channel id.")
        else:
            channels = ma.get("channels")
            if not isinstance(channels, list):
                local_errors.append("multi_asset_channels.json missing 'channels' list.")
            else:
                by_id = {ch.get("id"): ch for ch in channels if isinstance(ch, dict) and isinstance(ch.get("id"), str)}
                for cid, upd in ch_patch.items():
                    if cid not in REQUIRED_CHANNEL_SET:
                        local_errors.append(
                            f"Unknown channel id in channels_patch: {cid!r} (must be one of 12 standard IDs)."
                        )
                        continue
                    if cid not in by_id:
                        local_errors.append(f"Channel {cid!r} not found in existing multi_asset_channels.json.")
                        continue
                    if not isinstance(upd, dict):
                        local_errors.append(f"channels_patch[{cid!r}] must be an object.")
                        continue
                    target_ch = by_id[cid]
                    orig_ch = copy.deepcopy(target_ch)
                    ch_old_tokens: set[str] = set()
                    ch_new_tokens: set[str] = set()
                    touched_top_keys: set[str] = set()
                    touched_product_fields: dict[str, set[str]] = {}
                    product_token_diffs: list[tuple[str, set[str], set[str]]] = []
                    stats["channels_patched"] += 1
                    for k, v in upd.items():
                        if k == "id":
                            if v != cid:
                                local_errors.append(f"Cannot change channel id {cid!r} -> {v!r}.")
                            continue
                        if k == "products_upsert":
                            touched_top_keys.add("products")
                            if not isinstance(v, list):
                                local_errors.append(f"channels_patch[{cid!r}].products_upsert must be a list.")
                                continue
                            prods = target_ch.setdefault("products", [])
                            if not isinstance(prods, list):
                                local_errors.append(f"Existing channel {cid!r}.products is not a list.")
                                continue
                            for pi, p_upd in enumerate(v):
                                if not isinstance(p_upd, dict) or not isinstance(p_upd.get("code"), str) or not p_upd["code"].strip():
                                    local_errors.append(
                                        f"channels_patch[{cid!r}].products_upsert[{pi}] must be an object with non-empty 'code'."
                                    )
                                    continue
                                p_key = p_upd["code"].strip().upper()
                                existing = next(
                                    (p for p in prods if isinstance(p, dict) and str(p.get("code", "")).strip().upper() == p_key),
                                    None,
                                )
                                if existing is not None:
                                    p_touched = touched_product_fields.setdefault(p_key, set())
                                    p_old: set[str] = set()
                                    p_new: set[str] = set()
                                    for pk, pv in p_upd.items():
                                        if pk != "code":
                                            p_old |= _extract_dynamic_tokens(existing.get(pk))
                                            p_new |= _extract_dynamic_tokens(pv)
                                            p_touched.add(pk)
                                        existing[pk] = copy.deepcopy(pv)
                                    product_token_diffs.append((p_key, p_old, p_new))
                                else:
                                    missing_req = [
                                        req_f for req_f in ("code", "name", "metric", "fee", "note")
                                        if not isinstance(p_upd.get(req_f), str) or not p_upd[req_f].strip()
                                    ]
                                    if missing_req:
                                        for req_f in missing_req:
                                            local_errors.append(
                                                f"New product in channels_patch[{cid!r}].products_upsert[{pi}] missing non-empty {req_f!r}."
                                            )
                                        continue
                                    prods.append(copy.deepcopy(p_upd))
                                stats["products_upserted"] += 1
                        elif k == "products_remove":
                            touched_top_keys.add("products")
                            if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
                                local_errors.append(f"channels_patch[{cid!r}].products_remove must be a list of product codes.")
                                continue
                            rem_keys = {x.strip().upper() for x in v}
                            prods = target_ch.get("products", [])
                            for p in prods:
                                if isinstance(p, dict) and str(p.get("code", "")).strip().upper() in rem_keys:
                                    ch_old_tokens |= _extract_dynamic_tokens(p)
                            target_ch["products"] = [
                                p for p in prods if not (isinstance(p, dict) and str(p.get("code", "")).strip().upper() in rem_keys)
                            ]
                        else:
                            touched_top_keys.add(k)
                            ch_old_tokens |= _extract_dynamic_tokens(orig_ch.get(k))
                            ch_new_tokens |= _extract_dynamic_tokens(v)
                            target_ch[k] = copy.deepcopy(v)

                    replaced_tokens = ch_old_tokens - ch_new_tokens
                    untouched_strings: list[tuple[str, str]] = []
                    for sk, sv in target_ch.items():
                        if sk in CHANNEL_META_KEYS:
                            continue
                        if sk not in touched_top_keys:
                            untouched_strings.extend(_walk_json_strings(sv, sk))
                        elif sk == "products" and "products" not in upd and isinstance(sv, list):
                            for pi, prod in enumerate(sv):
                                if not isinstance(prod, dict):
                                    continue
                                pk_norm = str(prod.get("code", "")).strip().upper()
                                t_fields = touched_product_fields.get(pk_norm)
                                if t_fields is None:
                                    untouched_strings.extend(_walk_json_strings(prod, f"products[{pi}]"))
                                else:
                                    for pf, pval in prod.items():
                                        if pf != "code" and pf not in t_fields:
                                            untouched_strings.extend(_walk_json_strings(pval, f"products[{pi}].{pf}"))
                    _check_sibling_token_drift(
                        f"multi_asset_channels[{cid}]", replaced_tokens, untouched_strings, errors=local_errors
                    )

                    if product_token_diffs and isinstance(target_ch.get("products"), list):
                        merged_prod_old: dict[str, set[str]] = {}
                        merged_prod_new: dict[str, set[str]] = {}
                        for p_key, p_old, p_new in product_token_diffs:
                            merged_prod_old.setdefault(p_key, set()).update(p_old)
                            merged_prod_new.setdefault(p_key, set()).update(p_new)
                        for pi, prod in enumerate(target_ch["products"]):
                            if not isinstance(prod, dict):
                                continue
                            pk_norm = str(prod.get("code", "")).strip().upper()
                            if pk_norm not in merged_prod_old:
                                continue
                            p_replaced = merged_prod_old[pk_norm] - merged_prod_new[pk_norm]
                            if not p_replaced:
                                continue
                            t_fields = touched_product_fields.get(pk_norm, set())
                            prod_untouched: list[tuple[str, str]] = []
                            for pf, pval in prod.items():
                                if pf != "code" and pf not in t_fields:
                                    prod_untouched.extend(_walk_json_strings(pval, f"products[{pi}].{pf}"))
                            _check_sibling_token_drift(
                                f"multi_asset_channels[{cid}]", p_replaced, prod_untouched, errors=local_errors
                            )
                    untouched_sibs = sorted(
                        sk for sk in target_ch.keys() if sk not in touched_top_keys and sk not in CHANNEL_META_KEYS
                    )
                    stats["untouched_channel_siblings"][cid] = untouched_sibs

    if errors is None and local_errors:
        raise ValueError("\n".join(local_errors))
    return ma, stats


def _merge_etf_universe(
    orig: dict[str, Any],
    patch_root: dict[str, Any],
    edition_id: str,
    as_of_date: str,
    *,
    errors: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    local_errors: list[str] = errors if errors is not None else []
    eu = copy.deepcopy(orig)
    eu["edition_id"] = edition_id
    eu["as_of_date"] = as_of_date
    eu["updated_at"] = as_of_date
    if "as_of_label" in patch_root and patch_root["as_of_label"] is not None:
        if not isinstance(patch_root["as_of_label"], str) or not patch_root["as_of_label"].strip():
            local_errors.append("patch.as_of_label must be a non-empty string.")
        else:
            eu["as_of_label"] = patch_root["as_of_label"].strip()
    if "gold_tier0_locked" in patch_root and patch_root["gold_tier0_locked"] is not None:
        if not isinstance(patch_root["gold_tier0_locked"], bool):
            local_errors.append("patch.gold_tier0_locked must be a boolean.")
        else:
            eu["gold_tier0_locked"] = patch_root["gold_tier0_locked"]
    if "gold_lock_notice" in patch_root and patch_root["gold_lock_notice"] is not None:
        if not isinstance(patch_root["gold_lock_notice"], str) or not patch_root["gold_lock_notice"].strip():
            local_errors.append("patch.gold_lock_notice must be a non-empty string.")
        else:
            eu["gold_lock_notice"] = patch_root["gold_lock_notice"].strip()

    stats = {"top_keys_updated": 0, "etfs_updated": 0, "etfs_added": 0, "etfs_removed": 0}
    etfs = eu.get("etfs")
    if not isinstance(etfs, list):
        local_errors.append("etf_universe.json missing 'etfs' list.")
        if errors is None and local_errors:
            raise ValueError("\n".join(local_errors))
        return eu, stats
    orig_count = len(etfs)

    sec = patch_root.get("etf_universe")
    if sec is not None:
        if not isinstance(sec, dict):
            local_errors.append("patch.etf_universe must be an object.")
        else:
            unknown_sec = set(sec.keys()) - ALLOWED_ETF_PATCH_KEYS
            if unknown_sec:
                local_errors.append(
                    f"Unknown key(s) in etf_universe patch: {sorted(unknown_sec)} "
                    f"(allowed: {sorted(ALLOWED_ETF_PATCH_KEYS)})"
                )

            top_upd = sec.get("top_level_updates")
            if top_upd is not None:
                if not isinstance(top_upd, dict):
                    local_errors.append("etf_universe.top_level_updates must be an object.")
                else:
                    forbidden_top = {
                        "etfs", "total_etfs", "counts_by_market", "counts_by_channel",
                        "counts_by_asset_class", "counts_by_region",
                    }
                    overlap = forbidden_top & set(top_upd.keys())
                    if overlap:
                        local_errors.append(
                            f"Cannot override auto-managed etf_universe keys via top_level_updates: {sorted(overlap)}"
                        )
                    for k, v in top_upd.items():
                        if k in forbidden_top:
                            continue
                        eu[k] = copy.deepcopy(v)
                        stats["top_keys_updated"] += 1

            # Process etfs_remove first
            rem_raw = sec.get("etfs_remove")
            if rem_raw is not None:
                if not isinstance(rem_raw, list) or not all(isinstance(c, str) and c.strip() for c in rem_raw):
                    local_errors.append("etf_universe.etfs_remove must be a list of non-empty ETF code strings.")
                else:
                    rem_norms = {_normalize_etf_code(c) for c in rem_raw}
                    if len(rem_norms) > MAX_ETF_DELTA:
                        local_errors.append(
                            f"etfs_remove attempts to remove {len(rem_norms)} ETFs (> safety limit {MAX_ETF_DELTA})."
                        )
                    existing_norms = {_normalize_etf_code(e.get("code")) for e in etfs if isinstance(e, dict)}
                    missing_rem = sorted(rem_norms - existing_norms)
                    if missing_rem:
                        local_errors.append(f"etfs_remove references unknown ETF code(s): {missing_rem}")
                    new_etfs: list[dict[str, Any]] = []
                    for item in etfs:
                        if isinstance(item, dict) and _normalize_etf_code(item.get("code")) in rem_norms:
                            stats["etfs_removed"] += 1
                            continue
                        new_etfs.append(item)
                    etfs = new_etfs
                    eu["etfs"] = etfs

            # Process etfs_upsert (list of dicts, or dict keyed by code)
            ups_raw = sec.get("etfs_upsert")
            if ups_raw is not None:
                ups_list: list[dict[str, Any]] = []
                if isinstance(ups_raw, list):
                    for idx, entry in enumerate(ups_raw):
                        if not isinstance(entry, dict) or not isinstance(entry.get("code"), str) or not entry["code"].strip():
                            local_errors.append(
                                f"etf_universe.etfs_upsert[{idx}] must be an object with non-empty 'code'."
                            )
                            continue
                        ups_list.append(entry)
                elif isinstance(ups_raw, dict):
                    for code_k, entry in ups_raw.items():
                        if not isinstance(entry, dict):
                            local_errors.append(f"etf_universe.etfs_upsert[{code_k!r}] must be an object.")
                            continue
                        merged_e = dict(entry)
                        merged_e.setdefault("code", str(code_k))
                        ups_list.append(merged_e)
                else:
                    local_errors.append(
                        "etf_universe.etfs_upsert must be a list of ETF objects (or object keyed by code)."
                    )

                index_by_norm: dict[str, dict[str, Any]] = {}
                for item in etfs:
                    if isinstance(item, dict) and item.get("code"):
                        index_by_norm[_normalize_etf_code(item["code"])] = item

                for entry in ups_list:
                    norm_code = _normalize_etf_code(entry["code"])
                    if not norm_code:
                        local_errors.append(f"Invalid ETF code in etfs_upsert: {entry.get('code')!r}")
                        continue
                    if norm_code in index_by_norm:
                        extra_keys = sorted(set(entry.keys()) - ETF_ALLOWED_KEYS)
                        if extra_keys:
                            local_errors.append(
                                f"ETF {norm_code!r} in etfs_upsert has unknown key(s): {extra_keys} "
                                f"(allowed: {sorted(ETF_ALLOWED_KEYS)})"
                            )
                        target = index_by_norm[norm_code]
                        canonical_code = target["code"]
                        if entry.get("updated_at") is not None:
                            try:
                                _validate_date(entry["updated_at"], f"etf_universe[{canonical_code}].updated_at")
                            except ValueError as exc:
                                local_errors.append(str(exc))
                        orig_etf = copy.deepcopy(target)
                        old_tokens: set[str] = set()
                        new_tokens: set[str] = set()
                        touched_keys: set[str] = set()
                        for k, v in entry.items():
                            if k == "code" or k not in ETF_ALLOWED_KEYS:
                                continue  # Preserve existing canonical code format & skip invalid keys
                            touched_keys.add(k)
                            if k not in ("updated_at", "evidence"):
                                old_tokens |= _extract_dynamic_tokens(orig_etf.get(k))
                                new_tokens |= _extract_dynamic_tokens(v)
                            target[k] = copy.deepcopy(v)
                        target["code"] = canonical_code
                        target["updated_at"] = as_of_date
                        retain_inventory_evidence(orig_etf, target, entry)
                        replaced_tokens = old_tokens - new_tokens
                        untouched_strings: list[tuple[str, str]] = []
                        for sk, sv in target.items():
                            if sk in ("code", "updated_at", "evidence") or sk in touched_keys:
                                continue
                            untouched_strings.extend(_walk_json_strings(sv, sk))
                        _check_sibling_token_drift(
                            f"etf_universe[{canonical_code}]", replaced_tokens, untouched_strings, errors=local_errors
                        )
                        stats["etfs_updated"] += 1
                    else:
                        missing_keys = sorted(ETF_NEW_REQUIRED_KEYS - set(entry.keys()))
                        extra_keys = sorted(set(entry.keys()) - ETF_ALLOWED_KEYS)
                        if missing_keys:
                            local_errors.append(
                                f"New ETF {norm_code!r} in etfs_upsert must provide all 21 standard keys "
                                f"plus required orthogonal fields 'asset_class' and 'region'; missing: {missing_keys}"
                            )
                        if extra_keys:
                            local_errors.append(
                                f"New ETF {norm_code!r} has unknown key(s): {extra_keys} "
                                f"(allowed: {sorted(ETF_ALLOWED_KEYS)})"
                            )
                        if entry.get("updated_at") is not None:
                            try:
                                _validate_date(entry["updated_at"], f"etf_universe[{norm_code}].updated_at")
                            except ValueError as exc:
                                local_errors.append(str(exc))
                        if missing_keys:
                            continue
                        new_item = {k: copy.deepcopy(v) for k, v in entry.items() if k in ETF_ALLOWED_KEYS}
                        new_item["code"] = norm_code
                        new_item["updated_at"] = as_of_date
                        etfs.append(new_item)
                        index_by_norm[norm_code] = new_item
                        stats["etfs_added"] += 1

    delta = len(etfs) - orig_count
    if abs(delta) > MAX_ETF_DELTA:
        local_errors.append(
            f"ETF universe net count change |{delta:+d}| exceeds safety limit ({MAX_ETF_DELTA}); "
            f"orig={orig_count}, new={len(etfs)}."
        )

    # Recompute exact summary counters preserving existing key order
    mkt_counter: Counter[str] = Counter()
    ch_counter: Counter[str] = Counter()
    ac_counter: Counter[str] = Counter()
    reg_counter: Counter[str] = Counter()
    for item in etfs:
        if isinstance(item, dict):
            mv = str(item.get("market", "")).strip()
            cv = str(item.get("channel", "")).strip()
            av = str(item.get("asset_class", "")).strip() if item.get("asset_class") is not None else ""
            rv = str(item.get("region", "")).strip() if item.get("region") is not None else ""
            if mv:
                mkt_counter[mv] += 1
            if cv:
                ch_counter[cv] += 1
            if av:
                ac_counter[av] += 1
            if rv:
                reg_counter[rv] += 1

    orig_mkt_order = list((orig.get("counts_by_market") or {}).keys())
    orig_ch_order = list((orig.get("counts_by_channel") or {}).keys())
    orig_ac_order = list((orig.get("counts_by_asset_class") or {}).keys())
    orig_reg_order = list((orig.get("counts_by_region") or {}).keys())
    eu["total_etfs"] = len(etfs)
    eu["counts_by_market"] = {
        k: mkt_counter[k] for k in dict.fromkeys([*orig_mkt_order, *mkt_counter.keys()]) if mkt_counter.get(k, 0) > 0
    }
    eu["counts_by_channel"] = {
        k: ch_counter[k] for k in dict.fromkeys([*orig_ch_order, *ch_counter.keys()]) if ch_counter.get(k, 0) > 0
    }
    if ac_counter or "counts_by_asset_class" in orig:
        eu["counts_by_asset_class"] = {
            k: ac_counter[k] for k in dict.fromkeys([*orig_ac_order, *ac_counter.keys()]) if ac_counter.get(k, 0) > 0
        }
    if reg_counter or "counts_by_region" in orig:
        eu["counts_by_region"] = {
            k: reg_counter[k] for k in dict.fromkeys([*orig_reg_order, *reg_counter.keys()]) if reg_counter.get(k, 0) > 0
        }
    if errors is None and local_errors:
        raise ValueError("\n".join(local_errors))
    return eu, stats


def _iter_ah_premium_mentions(text: str) -> list[tuple[str, float, float]]:
    """Return (matched_text, lo_pct, hi_pct) for current AH premium mentions, negating unsigned inversions."""
    out: list[tuple[str, float, float]] = []
    for m_ah in AH_PREMIUM_MENTION_RE.finditer(text):
        pre_seg = re.split(r"[。！？；;，,]", text[max(0, m_ah.start() - 20) : m_ah.start()])[-1]
        if AH_HISTORICAL_CTX_RE.search(pre_seg + m_ah.group(0)):
            continue
        raw1 = m_ah.group(1)
        raw2 = m_ah.group(2)
        v1 = float(raw1)
        v2 = float(raw2) if raw2 is not None else v1
        if AH_NEGATIVE_WORD_RE.search(m_ah.group(0)):
            if not raw1.startswith(("+", "-")):
                v1 = -abs(v1)
            if raw2 is not None:
                if not raw2.startswith(("+", "-")):
                    v2 = -abs(v2)
            else:
                v2 = v1
        lo, hi = min(v1, v2), max(v1, v2)
        out.append((m_ah.group(0), lo, hi))
    return out


def _build_ah_twin_map(
    market_state: dict[str, Any] | None,
    dossiers: dict[str, Any],
) -> dict[str, tuple[str, float]]:
    twin_map: dict[str, tuple[str, float]] = {}
    if not isinstance(market_state, dict):
        return twin_map
    benchmarks = (
        market_state.get("cross_market_linkages", {})
        .get("ah_premium_radar", {})
        .get("benchmarks")
    )
    if not isinstance(benchmarks, list):
        return twin_map
    for b in benchmarks:
        if not isinstance(b, dict):
            continue
        a_code = b.get("a")
        h_code = b.get("h")
        ah_pct = b.get("ah_premium_pct")
        if (
            not isinstance(a_code, str) or not a_code.strip()
            or not isinstance(h_code, str) or not h_code.strip()
            or not isinstance(ah_pct, (int, float)) or isinstance(ah_pct, bool)
        ):
            continue
        ak = f"a-share:{a_code.strip()}"
        hk = f"hk-stock:{h_code.strip()}"
        if ak in dossiers and hk in dossiers:
            pct = float(ah_pct)
            twin_map[ak] = (hk, pct)
            twin_map[hk] = (ak, pct)
    return twin_map


def _merge_deep_dossiers(
    orig: dict[str, Any],
    patch_root: dict[str, Any],
    edition_id: str,
    as_of_date: str,
    *,
    market_state: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    local_errors: list[str] = errors if errors is not None else []
    dd = copy.deepcopy(orig)
    dd["edition_id"] = edition_id
    dd["as_of_date"] = as_of_date
    dd["updated_at"] = as_of_date

    stats: dict[str, Any] = {
        "top_keys_updated": 0,
        "stocks_patched": 0,
        "unpatched_ah_twins": {},
    }
    dossiers = dd.get("dossiers")
    if not isinstance(dossiers, dict):
        local_errors.append("deep_dossiers.json missing 'dossiers' object.")
        if errors is None and local_errors:
            raise ValueError("\n".join(local_errors))
        return dd, stats

    twin_map = _build_ah_twin_map(market_state, dossiers)
    sec = patch_root.get("deep_dossiers")
    if sec is not None:
        if not isinstance(sec, dict):
            local_errors.append("patch.deep_dossiers must be an object.")
        else:
            unknown_sec = set(sec.keys()) - ALLOWED_DOSSIERS_PATCH_KEYS
            if unknown_sec:
                local_errors.append(
                    f"Unknown key(s) in deep_dossiers patch: {sorted(unknown_sec)} "
                    f"(allowed: {sorted(ALLOWED_DOSSIERS_PATCH_KEYS)})"
                )

            top_upd = sec.get("top_level_updates")
            if top_upd is not None:
                if not isinstance(top_upd, dict):
                    local_errors.append("deep_dossiers.top_level_updates must be an object.")
                else:
                    forbidden_top = {"dossiers", "total_stocks", "core_deep_count", "standard_deep_count"}
                    overlap = forbidden_top & set(top_upd.keys())
                    if overlap:
                        local_errors.append(
                            f"Cannot override auto-managed deep_dossiers keys via top_level_updates: {sorted(overlap)}"
                        )
                    for k, v in top_upd.items():
                        if k in forbidden_top:
                            continue
                        dd[k] = copy.deepcopy(v)
                        stats["top_keys_updated"] += 1

            dp = sec.get("dossiers_patch")
            if dp is not None:
                if not isinstance(dp, dict):
                    local_errors.append("deep_dossiers.dossiers_patch must be an object keyed by stock key.")
                else:
                    for stock_key, upd in dp.items():
                        if stock_key not in dossiers:
                            local_errors.append(
                                f"dossiers_patch key {stock_key!r} is not in the existing stock pool (strictly forbidden to add/rename pool keys)."
                            )
                            continue
                        if not isinstance(upd, dict) or not upd:
                            local_errors.append(f"dossiers_patch[{stock_key!r}] must be a non-empty object.")
                            continue
                        target = dossiers[stock_key]
                        orig_entry = copy.deepcopy(target)
                        old_tokens: set[str] = set()
                        new_tokens: set[str] = set()
                        touched_keys: set[str] = set()
                        for k, v in upd.items():
                            if k in ("market", "code") and v != target.get(k):
                                local_errors.append(f"Cannot mutate immutable {k!r} on dossier {stock_key!r}.")
                                continue
                            touched_keys.add(k)
                            if k != "evidence":
                                old_tokens |= _extract_dynamic_tokens(orig_entry.get(k))
                                new_tokens |= _extract_dynamic_tokens(v)
                            target[k] = copy.deepcopy(v)
                        target["updated_at"] = as_of_date
                        retain_inventory_evidence(orig_entry, target, upd)
                        replaced_tokens = old_tokens - new_tokens
                        untouched_strings: list[tuple[str, str]] = []
                        for sk, sv in target.items():
                            if sk in DOSSIER_META_KEYS or sk in touched_keys:
                                continue
                            untouched_strings.extend(_walk_json_strings(sv, sk))
                        _check_sibling_token_drift(
                            f"deep_dossiers[{stock_key}]", replaced_tokens, untouched_strings, errors=local_errors
                        )
                        stats["stocks_patched"] += 1

                    # A/H Twin Sync Guard: if baseline_note or valuation_anchor changed on one side,
                    # ensure its unpatched A/H twin does not drift >0.6pp from market_state benchmark.
                    for stock_key, upd in dp.items():
                        if not isinstance(upd, dict):
                            continue
                        if "baseline_note" not in upd and "valuation_anchor" not in upd:
                            continue
                        twin_info = twin_map.get(stock_key)
                        if twin_info is None:
                            continue
                        twin_key, bench_pct = twin_info
                        if twin_key in dp:
                            continue
                        stats["unpatched_ah_twins"][stock_key] = twin_key
                        twin_entry = dossiers.get(twin_key)
                        if not isinstance(twin_entry, dict):
                            continue
                        for field in ("baseline_note", "valuation_anchor"):
                            fval = str(twin_entry.get(field, ""))
                            for raw_match, lo, hi in _iter_ah_premium_mentions(fval):
                                if bench_pct < lo - AH_PREMIUM_TOLERANCE_PP or bench_pct > hi + AH_PREMIUM_TOLERANCE_PP:
                                    local_errors.append(
                                        f"A/H twin sync required: patched {stock_key!r} without twin {twin_key!r}, "
                                        f"whose {field} still states {raw_match!r} vs market_state benchmark "
                                        f"{bench_pct:+.1f}% (drift > {AH_PREMIUM_TOLERANCE_PP:.1f}pp)."
                                    )

    dd["total_stocks"] = len(dossiers)
    dd["core_deep_count"] = sum(
        1 for entry in dossiers.values() if isinstance(entry, dict) and entry.get("depth_tier") == "core_deep"
    )
    dd["standard_deep_count"] = dd["total_stocks"] - dd["core_deep_count"]
    if errors is None and local_errors:
        raise ValueError("\n".join(local_errors))
    return dd, stats


def _merge_policy_calendar(
    orig: dict[str, Any],
    patch_root: dict[str, Any],
    edition_id: str,
    as_of_date: str,
    *,
    market_state: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    local_errors: list[str] = errors if errors is not None else []
    pc = copy.deepcopy(orig)
    pc["edition_id"] = edition_id

    fallback_ts = (
        f"{as_of_date}T{edition_id[11:13]}:{edition_id[13:15]}:00+08:00"
        if DATE_RE.fullmatch(as_of_date) and len(edition_id) >= 15 and edition_id[11:15].isdigit()
        else None
    )
    ms_as_of = market_state.get("as_of_cst") if isinstance(market_state, dict) else None
    if isinstance(ms_as_of, str):
        try:
            pc["as_of_cst"] = _validate_iso_cst_timestamp(ms_as_of, "market_state.as_of_cst")
        except ValueError:
            if fallback_ts is not None:
                pc["as_of_cst"] = fallback_ts
    elif fallback_ts is not None:
        pc["as_of_cst"] = fallback_ts

    stats: dict[str, Any] = {
        "top_keys_updated": 0,
        "briefs_replaced": 0,
        "events_updated": 0,
        "events_added": 0,
        "events_removed": 0,
        "events_pruned": 0,
        "pruned_event_ids": [],
    }
    briefs = pc.get("policy_briefs")
    if not isinstance(briefs, list):
        local_errors.append("policy_calendar.json missing 'policy_briefs' list.")
    events = pc.get("events")
    if not isinstance(events, list):
        local_errors.append("policy_calendar.json missing 'events' list.")
    if not isinstance(briefs, list) or not isinstance(events, list):
        if errors is None and local_errors:
            raise ValueError("\n".join(local_errors))
        return pc, stats

    sec = patch_root.get("policy_calendar")
    if sec is not None:
        if not isinstance(sec, dict):
            local_errors.append("patch.policy_calendar must be an object.")
        else:
            unknown_sec = set(sec.keys()) - ALLOWED_POLICY_CALENDAR_PATCH_KEYS
            if unknown_sec:
                local_errors.append(
                    f"Unknown key(s) in policy_calendar patch: {sorted(unknown_sec)} "
                    f"(allowed: {sorted(ALLOWED_POLICY_CALENDAR_PATCH_KEYS)})"
                )

            top_upd = sec.get("top_level_updates")
            if top_upd is not None:
                if not isinstance(top_upd, dict):
                    local_errors.append("policy_calendar.top_level_updates must be an object.")
                else:
                    forbidden_top = {"policy_briefs", "events", "edition_id"}
                    overlap = forbidden_top & set(top_upd.keys())
                    if overlap:
                        local_errors.append(
                            f"Cannot override auto-managed policy_calendar keys via top_level_updates: {sorted(overlap)}"
                        )
                    unknown_top = set(top_upd.keys()) - ALLOWED_POLICY_CALENDAR_TOP_KEYS - forbidden_top
                    if unknown_top:
                        local_errors.append(
                            f"Unknown key(s) in policy_calendar.top_level_updates: {sorted(unknown_top)} "
                            f"(allowed: {sorted(ALLOWED_POLICY_CALENDAR_TOP_KEYS)})"
                        )
                    for k, v in top_upd.items():
                        if k not in ALLOWED_POLICY_CALENDAR_TOP_KEYS:
                            continue
                        if k == "as_of_cst":
                            try:
                                pc[k] = _validate_iso_cst_timestamp(v, "policy_calendar.top_level_updates.as_of_cst")
                            except ValueError as exc:
                                local_errors.append(str(exc))
                                continue
                        else:
                            pc[k] = copy.deepcopy(v)
                        stats["top_keys_updated"] += 1

            briefs_rep = sec.get("policy_briefs_replace")
            if briefs_rep is not None:
                if not isinstance(briefs_rep, list) or not briefs_rep or not all(isinstance(b, dict) for b in briefs_rep):
                    local_errors.append("policy_calendar.policy_briefs_replace must be a non-empty list of brief objects.")
                else:
                    pc["policy_briefs"] = copy.deepcopy(briefs_rep)
                    stats["briefs_replaced"] = len(briefs_rep)

            rem_raw = sec.get("events_remove")
            if rem_raw is not None:
                if not isinstance(rem_raw, list) or not all(isinstance(eid, str) and eid.strip() for eid in rem_raw):
                    local_errors.append("policy_calendar.events_remove must be a list of non-empty event_id strings.")
                else:
                    rem_set = {eid.strip() for eid in rem_raw}
                    kept: list[Any] = []
                    for ev in events:
                        if isinstance(ev, dict) and str(ev.get("event_id", "")).strip() in rem_set:
                            stats["events_removed"] += 1
                            continue
                        kept.append(ev)
                    events = kept
                    pc["events"] = events

            ups_raw = sec.get("events_upsert")
            if ups_raw is not None:
                ups_list: list[dict[str, Any]] = []
                if isinstance(ups_raw, list):
                    for idx, entry in enumerate(ups_raw):
                        if not isinstance(entry, dict) or not isinstance(entry.get("event_id"), str) or not entry["event_id"].strip():
                            local_errors.append(
                                f"policy_calendar.events_upsert[{idx}] must be an object with non-empty 'event_id'."
                            )
                            continue
                        ups_list.append(entry)
                elif isinstance(ups_raw, dict):
                    for eid_k, entry in ups_raw.items():
                        if not isinstance(entry, dict):
                            local_errors.append(f"policy_calendar.events_upsert[{eid_k!r}] must be an object.")
                            continue
                        merged_e = dict(entry)
                        if "event_id" not in merged_e:
                            merged_e["event_id"] = str(eid_k)
                        if not isinstance(merged_e.get("event_id"), str) or not merged_e["event_id"].strip():
                            local_errors.append(
                                f"policy_calendar.events_upsert[{eid_k!r}] must have a non-empty string 'event_id'."
                            )
                            continue
                        ups_list.append(merged_e)
                else:
                    local_errors.append(
                        "policy_calendar.events_upsert must be a list of event objects (or object keyed by event_id)."
                    )

                by_eid: dict[str, dict[str, Any]] = {}
                for ev in events:
                    if isinstance(ev, dict) and isinstance(ev.get("event_id"), str) and ev["event_id"].strip():
                        by_eid[ev["event_id"].strip()] = ev

                for entry in ups_list:
                    eid = entry["event_id"].strip()
                    if eid in by_eid:
                        target = by_eid[eid]
                        for k, v in entry.items():
                            if k == "event_id":
                                continue
                            if k == "watch_triggers" and isinstance(v, dict) and isinstance(target.get("watch_triggers"), dict):
                                merged_wt = copy.deepcopy(target["watch_triggers"])
                                merged_wt.update(copy.deepcopy(v))
                                target["watch_triggers"] = merged_wt
                            else:
                                target[k] = copy.deepcopy(v)
                        stats["events_updated"] += 1
                    else:
                        missing = sorted(POLICY_CAL_EVENT_REQUIRED_KEYS - set(entry.keys()))
                        if missing:
                            local_errors.append(
                                f"New event {eid!r} in policy_calendar.events_upsert missing required key(s): {missing}"
                            )
                            continue
                        new_ev = copy.deepcopy(entry)
                        new_ev["event_id"] = eid
                        events.append(new_ev)
                        by_eid[eid] = new_ev
                        stats["events_added"] += 1

    # Auto-prune expired events whose end_date_cst < edition_date - 2d
    ed_dt = None
    if DATE_RE.fullmatch(as_of_date):
        try:
            ed_dt = datetime.strptime(as_of_date, "%Y-%m-%d").date()
        except ValueError:
            ed_dt = None
    if ed_dt is not None:
        prune_cutoff = (ed_dt - timedelta(days=2)).isoformat()
        active_events: list[Any] = []
        for ev in events:
            if isinstance(ev, dict):
                end_raw = ev.get("end_date_cst") or ev.get("date_cst")
                if isinstance(end_raw, str) and DATE_RE.fullmatch(end_raw.strip()):
                    try:
                        datetime.strptime(end_raw.strip(), "%Y-%m-%d")
                    except ValueError:
                        pass
                    else:
                        if end_raw.strip() < prune_cutoff:
                            stats["events_pruned"] += 1
                            stats["pruned_event_ids"].append(str(ev.get("event_id", "")).strip())
                            continue
            active_events.append(ev)
    else:
        active_events = list(events)

    active_events.sort(
        key=lambda ev: (
            str(ev.get("date_cst", "")) if isinstance(ev, dict) else "",
            str(ev.get("time_cst", "")) if isinstance(ev, dict) else "",
            str(ev.get("event_id", "")) if isinstance(ev, dict) else "",
        )
    )
    pc["events"] = active_events
    if errors is None and local_errors:
        raise ValueError("\n".join(local_errors))
    return pc, stats


def _validate_policy_calendar(
    pc: dict[str, Any],
    *,
    edition_id: str,
    as_of_date: str,
    gold_tier0_active: bool,
    market_as_of_cst: object = None,
    enforce_live_contract: bool = False,
) -> list[str]:
    errs: list[str] = []
    if not isinstance(pc.get("schema_version"), str) or not pc["schema_version"].strip():
        errs.append("policy_calendar.json: missing non-empty schema_version.")
    if pc.get("edition_id") != edition_id:
        errs.append(f"policy_calendar.json: edition_id ({pc.get('edition_id')!r}) != {edition_id!r}")
    as_of = None
    try:
        as_of = datetime.fromisoformat(_validate_iso_cst_timestamp(pc.get("as_of_cst"), "policy_calendar.json.as_of_cst"))
    except ValueError as exc:
        errs.append(f"policy_calendar.json: {exc}")
    if enforce_live_contract:
        try:
            market_as_of = datetime.fromisoformat(_validate_iso_cst_timestamp(market_as_of_cst, "market_state.json.as_of_cst"))
        except ValueError as exc:
            errs.append(f"policy_calendar.json: {exc}")
        else:
            if as_of is not None and as_of != market_as_of:
                errs.append("policy_calendar.json: as_of_cst must match market_state.json.as_of_cst.")
    hdays = pc.get("horizon_days")
    if type(hdays) is not int or hdays < POLICY_CAL_MIN_HORIZON_DAYS:
        errs.append(
            f"policy_calendar.json: horizon_days must be an int >= {POLICY_CAL_MIN_HORIZON_DAYS} (got {hdays!r})."
        )

    briefs = pc.get("policy_briefs")
    if not isinstance(briefs, list) or not briefs:
        errs.append("policy_calendar.json: policy_briefs must be a non-empty list.")
    else:
        featured = sum(isinstance(brief, dict) and brief.get("home_featured") is True for brief in briefs)
        if enforce_live_contract and not 6 <= featured <= 9:
            errs.append(f"policy_calendar.json: expected 6–9 home_featured policy_briefs, found {featured}.")
        seen_bids: set[str] = set()
        for idx, b in enumerate(briefs):
            if not isinstance(b, dict):
                errs.append(f"policy_calendar.json: policy_briefs[{idx}] must be an object.")
                continue
            bid = str(b.get("id", "")).strip()
            if not bid:
                errs.append(f"policy_calendar.json: policy_briefs[{idx}] missing non-empty id.")
            elif bid in seen_bids:
                errs.append(f"policy_calendar.json: duplicate policy_brief id {bid!r}.")
            else:
                seen_bids.add(bid)
            for field in POLICY_CAL_REQUIRED_BRIEF_STR_FIELDS:
                val = b.get(field)
                if not isinstance(val, str) or not val.strip():
                    errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) missing non-empty {field}.")
            if isinstance(b.get("date_cst"), str) and b["date_cst"].strip():
                try:
                    brief_day = datetime.fromisoformat(_validate_date(b["date_cst"], f"policy_briefs[{idx}]({bid}).date_cst"))
                except ValueError as exc:
                    errs.append(f"policy_calendar.json: {exc}")
                else:
                    if enforce_live_contract and as_of is not None:
                        brief_time = b.get("time_cst")
                        if isinstance(brief_time, str) and POLICY_CLOCK_RE.fullmatch(brief_time):
                            brief_day = datetime.fromisoformat(f"{b['date_cst'].strip()}T{brief_time}")
                        if brief_day > as_of.replace(tzinfo=None):
                            errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) is later than as_of_cst.")
            reg = str(b.get("region", "")).strip()
            if reg and reg not in POLICY_CAL_ALLOWED_REGIONS:
                errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) invalid region {reg!r}.")
            cat = str(b.get("category", "")).strip()
            if cat and cat not in POLICY_CAL_ALLOWED_CATEGORIES:
                errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) invalid category {cat!r}.")
            tier = str(b.get("impact_tier", "")).strip()
            if tier and tier not in POLICY_CAL_ALLOWED_TIERS:
                errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) invalid impact_tier {tier!r}.")
            aff = b.get("affected_markets")
            if not isinstance(aff, list) or not aff or any(not isinstance(m, str) or not m.strip() for m in aff):
                errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) missing non-empty affected_markets list.")
            else:
                bad_mkts = sorted({m.strip() for m in aff if m.strip() not in POLICY_CAL_ALLOWED_MARKETS})
                if bad_mkts:
                    errs.append(
                        f"policy_calendar.json: policy_briefs[{idx}]({bid}) invalid affected_markets {bad_mkts} "
                        f"(allowed: {sorted(POLICY_CAL_ALLOWED_MARKETS)})."
                    )
            source = b.get("source_url")
            if (enforce_live_contract or source is not None) and not _is_strict_https_url(source, published_source=enforce_live_contract):
                errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) invalid https source_url {source!r}.")
            elif enforce_live_contract and not _is_strict_https_url(source, published_source=True, direct=True):
                errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) source_url must point to specific evidence.")
            if source_error := policy_extra_source_error(b):
                errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) {source_error} HTTPS source_urls.")
            if "home_featured" in b and b["home_featured"] is not None and type(b["home_featured"]) is not bool:
                errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) home_featured must be boolean.")
            if "time_cst" in b and b["time_cst"] is not None and (not isinstance(b["time_cst"], str) or not b["time_cst"].strip()):
                errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) time_cst must be non-empty string.")
            elif enforce_live_contract and b.get("time_cst") is not None and not POLICY_CLOCK_RE.fullmatch(b["time_cst"]):
                errs.append(f"policy_calendar.json: policy_briefs[{idx}]({bid}) time_cst must use HH:MM when supplied.")

    events = pc.get("events")
    max_end_date = None
    if not isinstance(events, list) or not events:
        errs.append("policy_calendar.json: events must be a non-empty list.")
    else:
        seen_eids: set[str] = set()
        for idx, ev in enumerate(events):
            if not isinstance(ev, dict):
                errs.append(f"policy_calendar.json: events[{idx}] must be an object.")
                continue
            eid = str(ev.get("event_id", "")).strip()
            if not eid:
                errs.append(f"policy_calendar.json: events[{idx}] missing non-empty event_id.")
            elif eid in seen_eids:
                errs.append(f"policy_calendar.json: duplicate event_id {eid!r}.")
            else:
                seen_eids.add(eid)
            for field in POLICY_CAL_REQUIRED_EVENT_STR_FIELDS:
                val = ev.get(field)
                if not isinstance(val, str) or not val.strip():
                    errs.append(f"policy_calendar.json: events[{idx}]({eid}) missing non-empty {field}.")
            start_d = end_d = None
            if isinstance(ev.get("date_cst"), str) and ev["date_cst"].strip():
                try:
                    start_d = datetime.strptime(_validate_date(ev["date_cst"], f"events[{idx}]({eid}).date_cst"), "%Y-%m-%d").date()
                except ValueError as exc:
                    errs.append(f"policy_calendar.json: {exc}")
            if isinstance(ev.get("end_date_cst"), str) and ev["end_date_cst"].strip():
                try:
                    end_d = datetime.strptime(_validate_date(ev["end_date_cst"], f"events[{idx}]({eid}).end_date_cst"), "%Y-%m-%d").date()
                except ValueError as exc:
                    errs.append(f"policy_calendar.json: {exc}")
            if start_d is not None and end_d is not None:
                if end_d < start_d:
                    errs.append(
                        f"policy_calendar.json: events[{idx}]({eid}) end_date_cst ({end_d}) < date_cst ({start_d})."
                    )
                if max_end_date is None or end_d > max_end_date:
                    max_end_date = end_d
            prec = str(ev.get("date_precision", "")).strip()
            if prec and prec not in POLICY_CAL_ALLOWED_PRECISIONS:
                errs.append(f"policy_calendar.json: events[{idx}]({eid}) invalid date_precision {prec!r}.")
            if enforce_live_contract and prec in POLICY_CAL_ALLOWED_PRECISIONS:
                event_time = ev.get("time_cst")
                has_exact_time = isinstance(event_time, str) and POLICY_CLOCK_RE.fullmatch(event_time)
                if prec == "exact" and (not has_exact_time or start_d != end_d):
                    errs.append(f"policy_calendar.json: events[{idx}]({eid}) exact requires one date and an HH:MM time_cst.")
                elif prec == "window_tbd" and has_exact_time:
                    errs.append(f"policy_calendar.json: events[{idx}]({eid}) window_tbd requires a time window or an unknown time.")
            reg = str(ev.get("region", "")).strip()
            if reg and reg not in POLICY_CAL_ALLOWED_REGIONS:
                errs.append(f"policy_calendar.json: events[{idx}]({eid}) invalid region {reg!r}.")
            cat = str(ev.get("category", "")).strip()
            if cat and cat not in POLICY_CAL_ALLOWED_CATEGORIES:
                errs.append(f"policy_calendar.json: events[{idx}]({eid}) invalid category {cat!r}.")
            tier = str(ev.get("impact_tier", "")).strip()
            if tier and tier not in POLICY_CAL_ALLOWED_TIERS:
                errs.append(f"policy_calendar.json: events[{idx}]({eid}) invalid impact_tier {tier!r}.")
            aff = ev.get("affected_markets")
            if not isinstance(aff, list) or not aff or any(not isinstance(m, str) or not m.strip() for m in aff):
                errs.append(f"policy_calendar.json: events[{idx}]({eid}) missing non-empty affected_markets list.")
            else:
                bad_mkts = sorted({m.strip() for m in aff if m.strip() not in POLICY_CAL_ALLOWED_MARKETS})
                if bad_mkts:
                    errs.append(
                        f"policy_calendar.json: events[{idx}]({eid}) invalid affected_markets {bad_mkts} "
                        f"(allowed: {sorted(POLICY_CAL_ALLOWED_MARKETS)})."
                    )
            wt = ev.get("watch_triggers")
            if (
                not isinstance(wt, dict)
                or not isinstance(wt.get("upside_bull"), str) or not wt["upside_bull"].strip()
                or not isinstance(wt.get("downside_bear"), str) or not wt["downside_bear"].strip()
            ):
                errs.append(
                    f"policy_calendar.json: events[{idx}]({eid}).watch_triggers requires non-empty upside_bull and downside_bear."
                )
            if not _is_strict_https_url(ev.get("source_url"), published_source=enforce_live_contract):
                errs.append(f"policy_calendar.json: events[{idx}]({eid}) invalid https source_url {ev.get('source_url')!r}.")
            mwin = ev.get("monitor_window_min")
            if type(mwin) is not int or mwin < 0:
                errs.append(
                    f"policy_calendar.json: events[{idx}]({eid}).monitor_window_min must be a non-negative integer (got {mwin!r})."
                )

    # 14-day forward coverage requirement
    if max_end_date is not None and DATE_RE.fullmatch(as_of_date):
        ed_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
        covered_days = (max_end_date - ed_date).days
        if covered_days < POLICY_CAL_MIN_HORIZON_DAYS:
            errs.append(
                f"policy_calendar.json: forward horizon coverage is only {covered_days} day(s) "
                f"(latest event {max_end_date} vs edition_date {ed_date}; requires >= {POLICY_CAL_MIN_HORIZON_DAYS} days)."
            )

    # Global string hygiene + Gold Tier-0 red-light scan across ALL strings in policy_calendar.json
    rel_date_patterns: list[tuple[str, re.Pattern[str]]] = []
    if DATE_RE.fullmatch(as_of_date):
        try:
            dt_cur = datetime.strptime(as_of_date, "%Y-%m-%d")
            dt_prev1 = dt_cur - timedelta(days=1)
            dt_prev2 = dt_cur - timedelta(days=2)
            rel_date_patterns = [
                ("stale '明日' matching as_of_date", re.compile(rf"明日\s*[（(]?\s*0?{dt_cur.month}/0?{dt_cur.day}(?!\d)[）)]?")),
                ("stale '今日' matching yesterday", re.compile(rf"今日\s*[（(]?\s*0?{dt_prev1.month}/0?{dt_prev1.day}(?!\d)[）)]?")),
                ("stale '昨日' matching 2 days ago", re.compile(rf"昨日\s*[（(]?\s*0?{dt_prev2.month}/0?{dt_prev2.day}(?!\d)[）)]?")),
            ]
        except ValueError:
            rel_date_patterns = []

    for jpath, sval in _walk_json_strings(pc, "policy_calendar.json", skip_keys=frozenset()):
        if RAW_MARKUP_RE.search(sval):
            errs.append(f"{jpath}: contains raw Markdown/HTML markup.")
        hits = BANNED_INTERNAL_RE.findall(sval)
        if hits:
            errs.append(f"{jpath}: leaked internal term(s): {sorted(set(hits))}")
        if LOCAL_PATH_RE.search(sval):
            errs.append(f"{jpath}: leaked local filesystem path.")
        leaf_key = jpath.rsplit(".", 1)[-1].split("[", 1)[0]
        if leaf_key not in POLICY_CAL_PROSE_SKIP_KEYS:
            m_tier = BARE_IMPACT_TIER_RE.search(sval)
            if m_tier:
                errs.append(
                    f"{jpath}: reader-visible bare priority token {m_tier.group(0)!r} forbidden in prose "
                    f"(use plain Chinese '重磅/重要/关注')."
                )
        for rel_label, rel_re in rel_date_patterns:
            m_rel = rel_re.search(sval)
            if m_rel:
                errs.append(
                    f"{jpath}: relative-date tense drift ({rel_label} on {as_of_date}) -> {m_rel.group(0)!r}"
                )
        m_hk4 = HK_4DIGIT_RE.search(sval)
        if m_hk4:
            errs.append(
                f"{jpath}: bare 4-digit HK ticker {m_hk4.group(0)!r} must use canonical 5-digit format (e.g. 0{m_hk4.group(0)})."
            )
        for m_iopv in IOPV_RE.finditer(sval):
            win = sval[max(0, m_iopv.start() - 20) : min(len(sval), m_iopv.end() + 20)]
            if not IOPV_GLOSS_RE.search(win):
                errs.append(
                    f"{jpath}: bare 'IOPV' without '参考净值'/'实时净值'/'盘中净值' within ±20 chars -> {win!r}"
                )
                break
        for m_rc in RESTRICTED_CODES_RE.finditer(sval):
            win = sval[max(0, m_rc.start() - 40) : min(len(sval), m_rc.end() + 40)]
            if not RESTRICTED_WARN_RE.search(win):
                errs.append(
                    f"{jpath}: restricted code {m_rc.group(0)} mentioned without warning within ±40 chars -> {win!r}"
                )
                break
        errs.extend(_scan_text_for_crypto_buy(jpath, sval))
        if gold_tier0_active:
            errs.extend(_scan_text_for_gold_buy(jpath, sval))

    return errs


def _validate_merged_equity_dbs(
    ma: dict[str, Any],
    eu: dict[str, Any],
    dd: dict[str, Any],
    *,
    edition_id: str,
    gold_tier0_active: bool,
    expected_pool: int,
    as_of_date: str | None = None,
    market_state: dict[str, Any] | None = None,
) -> list[str]:
    errs: list[str] = []
    cutoff = date.fromisoformat(edition_id.split("_", 1)[0])

    # 1. Edition ID alignment
    for name, doc in (
        ("multi_asset_channels.json", ma),
        ("etf_universe.json", eu),
        ("deep_dossiers.json", dd),
    ):
        if doc.get("edition_id") != edition_id:
            errs.append(f"{name}: edition_id ({doc.get('edition_id')!r}) != {edition_id!r}")

    # 2. Validate multi_asset_channels (12 channels, products, rules, template weights=100%, restricted codes, leaks)
    channels = ma.get("channels")
    if not isinstance(channels, list):
        errs.append("multi_asset_channels.json: channels must be a list.")
    else:
        seen_cids: set[str] = set()
        for idx, ch in enumerate(channels):
            if not isinstance(ch, dict):
                errs.append(f"multi_asset_channels.json: channels[{idx}] must be an object.")
                continue
            cid = str(ch.get("id", "")).strip()
            if not cid:
                errs.append(f"multi_asset_channels.json: channels[{idx}] missing non-empty id.")
                continue
            if cid in seen_cids:
                errs.append(f"multi_asset_channels.json: duplicate channel id {cid!r}.")
            seen_cids.add(cid)
            for req_s in ("name", "beginner_one_liner", "today_alert"):
                if not isinstance(ch.get(req_s), str) or not ch[req_s].strip():
                    errs.append(f"multi_asset_channels.json: channel {cid} missing non-empty {req_s}.")
            if cid == "qdii_mrf" and isinstance(ch.get("name"), str) and ch["name"].strip():
                qdii_name = ch["name"].strip()
                if (expected_pool >= 100 or qdii_name != "渠道 qdii_mrf") and not qdii_name.startswith("QDII"):
                    errs.append(
                        f"multi_asset_channels.json: channel 'qdii_mrf' name must start with 'QDII' (got {qdii_name!r})."
                    )
            if ch.get("status_tone") not in ALLOWED_STATUS_TONES:
                errs.append(f"multi_asset_channels.json: channel {cid} invalid status_tone {ch.get('status_tone')!r}.")
            kms = ch.get("key_metrics")
            if not isinstance(kms, list) or not kms:
                errs.append(f"multi_asset_channels.json: channel {cid} missing non-empty key_metrics.")
            else:
                for ki, km in enumerate(kms):
                    if (
                        not isinstance(km, dict)
                        or not isinstance(km.get("label"), str) or not km["label"].strip()
                        or not isinstance(km.get("value"), str) or not km["value"].strip()
                    ):
                        errs.append(f"multi_asset_channels.json: channel {cid}.key_metrics[{ki}] missing label/value.")
            prods = ch.get("products")
            if not isinstance(prods, list) or not prods:
                errs.append(f"multi_asset_channels.json: channel {cid} missing non-empty products.")
            else:
                for pi, prod in enumerate(prods):
                    if not isinstance(prod, dict):
                        errs.append(f"multi_asset_channels.json: channel {cid}.products[{pi}] must be an object.")
                        continue
                    for pf in ("code", "name", "metric", "fee", "note"):
                        if not isinstance(prod.get(pf), str) or not prod[pf].strip():
                            errs.append(f"multi_asset_channels.json: channel {cid}.products[{pi}] missing non-empty {pf}.")
                    pcode = str(prod.get("code", ""))
                    if RESTRICTED_CODES_RE.search(pcode):
                        ctx = f"{prod.get('name', '')} {prod.get('note', '')}"
                        if not RESTRICTED_WARN_RE.search(ctx):
                            errs.append(
                                f"multi_asset_channels.json: channel {cid}.products[{pi}] restricted code {pcode!r} lacks warning."
                            )
                    if gold_tier0_active:
                        pnorm = _normalize_etf_code(pcode)
                        pname = str(prod.get("name", ""))
                        pnote = str(prod.get("note", ""))
                        if pnorm in GOLD_ETF_CODES or GOLD_ETF_NAME_RE.search(pname):
                            if not re.search(r"(?:红灯|暂不|暂停|严禁|禁止|锁)", pnote + pname):
                                errs.append(
                                    f"Gold Tier-0 互斥冲突 (multi_asset_channels:{pnorm or pname})：涉金产品须显式注明红灯暂停新买锁"
                                )
            rules = ch.get("rules_and_redlines")
            if not isinstance(rules, list) or not rules or any(not isinstance(r, str) or not r.strip() for r in rules):
                errs.append(f"multi_asset_channels.json: channel {cid} missing non-empty rules_and_redlines.")

        missing_ch = [c for c in REQUIRED_MULTI_ASSET_CHANNELS if c not in seen_cids]
        if missing_ch:
            errs.append(f"multi_asset_channels.json: missing required channels {missing_ch}.")

    templates = ma.get("allocation_templates")
    if templates is not None:
        if not isinstance(templates, list):
            errs.append("multi_asset_channels.json: allocation_templates must be a list.")
        else:
            for ti, tpl in enumerate(templates):
                if not isinstance(tpl, dict) or not isinstance(tpl.get("slices"), list) or not tpl["slices"]:
                    errs.append(f"multi_asset_channels.json: allocation_templates[{ti}] missing non-empty slices.")
                    continue
                exact_pcts: list[float] = []
                has_range = False
                for sl in tpl["slices"]:
                    if not isinstance(sl, dict):
                        continue
                    w = str(sl.get("weight", "")).strip()
                    m_ex = EXACT_PCT_RE.fullmatch(w)
                    if m_ex:
                        exact_pcts.append(float(m_ex.group(1)))
                    elif RANGE_PCT_RE.search(w):
                        has_range = True
                if len(exact_pcts) >= 2 and not has_range and abs(sum(exact_pcts) - 100.0) > 0.01:
                    errs.append(
                        f"multi_asset_channels.json: allocation_templates[{ti}]({tpl.get('id')}) "
                        f"exact weights sum={sum(exact_pcts):.2f}% != 100%."
                    )

    # 3. Validate ETF coverage, unique codes, enums, and Gold Tier-0 lock.
    if gold_tier0_active and eu.get("gold_tier0_locked") is not True:
        errs.append("etf_universe.json: gold_tier0_locked must be true while Gold is Tier 0 / new_buy_allowed=false.")
    etfs = eu.get("etfs")
    if not isinstance(etfs, list):
        errs.append("etf_universe.json: etfs must be a list.")
    else:
        live_coverage = expected_pool >= 100 and edition_id[:15] >= DATA_CONTRACT_CUTOVER
        min_etfs = LIVE_MIN_ETF_COUNT if live_coverage else MIN_ETF_COUNT
        if len(etfs) < min_etfs:
            errs.append(f"etf_universe.json: ETF count {len(etfs)} < {min_etfs}.")
        if eu.get("total_etfs") != len(etfs):
            errs.append(f"etf_universe.json: total_etfs ({eu.get('total_etfs')}) != len(etfs) ({len(etfs)}).")
        seen_etf_codes: set[str] = set()
        etf_fee_map: dict[str, float] = {}
        ac_counter: Counter[str] = Counter()
        reg_counter: Counter[str] = Counter()
        require_ortho_etf = expected_pool >= 140
        for idx, item in enumerate(etfs):
            if not isinstance(item, dict):
                errs.append(f"etf_universe.json: etfs[{idx}] must be an object.")
                continue
            code = str(item.get("code", "")).strip()
            norm = _normalize_etf_code(code)
            if not norm:
                errs.append(f"etf_universe.json: etfs[{idx}] missing non-empty code.")
            elif norm in seen_etf_codes:
                errs.append(f"etf_universe.json: duplicate normalized ETF code {norm!r}.")
            else:
                seen_etf_codes.add(norm)
            for field in ETF_REQUIRED_STR_FIELDS:
                val = item.get(field)
                if not isinstance(val, str) or not val.strip():
                    errs.append(f"etf_universe.json: etfs[{idx}]({code}) missing non-empty {field}.")
                elif RAW_MARKUP_RE.search(val):
                    errs.append(f"etf_universe.json: etfs[{idx}]({code}).{field} contains raw Markdown/HTML markup.")
            fee_num = item.get("fee_num")
            if isinstance(fee_num, (int, float)) and not isinstance(fee_num, bool):
                fee_num_f = float(fee_num)
                if norm:
                    etf_fee_map[norm] = fee_num_f
                fee_total = str(item.get("fee_total_pct", "")).strip()
                m_ft = re.match(r"^(\d+(?:\.\d+)?)%", fee_total)
                if m_ft and abs(float(m_ft.group(1)) - fee_num_f) > 0.005:
                    errs.append(
                        f"etf_universe.json: etfs[{idx}]({code}) fee_total_pct ({fee_total!r}) != fee_num ({fee_num})."
                    )
            mkt = str(item.get("market", "")).strip()
            if mkt not in ETF_ALLOWED_MARKETS:
                errs.append(f"etf_universe.json: etfs[{idx}]({code}) invalid market {mkt!r}.")
            ch = str(item.get("channel", "")).strip()
            if ch not in ETF_ALLOWED_CHANNELS:
                errs.append(f"etf_universe.json: etfs[{idx}]({code}) invalid channel {ch!r}.")
            ac_raw = item.get("asset_class")
            if "asset_class" in item and ac_raw is not None:
                ac_v = ac_raw.strip() if isinstance(ac_raw, str) else ""
                if ac_v not in ETF_ALLOWED_ASSET_CLASSES:
                    errs.append(f"etf_universe.json: etfs[{idx}]({code}) invalid asset_class {ac_raw!r}.")
                else:
                    ac_counter[ac_v] += 1
            elif require_ortho_etf:
                errs.append(f"etf_universe.json: etfs[{idx}]({code}) missing required asset_class.")
            reg_raw = item.get("region")
            if "region" in item and reg_raw is not None:
                reg_v = reg_raw.strip() if isinstance(reg_raw, str) else ""
                if reg_v not in ETF_ALLOWED_REGIONS:
                    errs.append(f"etf_universe.json: etfs[{idx}]({code}) invalid region {reg_raw!r}.")
                else:
                    reg_counter[reg_v] += 1
            elif require_ortho_etf:
                errs.append(f"etf_universe.json: etfs[{idx}]({code}) missing required region.")
            if "updated_at" in item and item["updated_at"] is not None:
                try:
                    _validate_date(item["updated_at"], f"etfs[{idx}]({code}).updated_at")
                except ValueError as exc:
                    errs.append(f"etf_universe.json: {exc}")
            try:
                inventory_evidence(item, ETF_FIELDS, cutoff)
            except ValueError as exc:
                errs.append(f"etf_universe.json: etfs[{idx}]({code}) {exc}.")
            if "premium_status" in item and item["premium_status"] not in ETF_ALLOWED_PREMIUM_STATUSES:
                errs.append(f"etf_universe.json: etfs[{idx}]({code}) invalid premium_status {item['premium_status']!r}.")
            pstatus = str(item.get("premium_status", "")).strip()
            pnote = str(item.get("premium_note", ""))
            role_str = str(item.get("action_role", "")).strip()
            if pstatus == "high_risk" and role_str != "高危回避":
                errs.append(
                    f"etf_universe.json: etfs[{idx}]({code}) has premium_status='high_risk' "
                    f"so action_role must be '高危回避' (got {role_str!r})."
                )
            otc_str = str(item.get("otc_feeder", ""))
            if (
                OTC_SUSPENDED_NOTE_RE.search(pnote)
                and "零溢价场外联接" in otc_str
                and not OTC_DISCLOSURE_RE.search(otc_str)
            ):
                errs.append(
                    f"etf_universe.json: etfs[{idx}]({code}).otc_feeder claims unqualified '零溢价场外联接' "
                    f"while premium_note states OTC subscription is suspended ({pnote[:80]!r})."
                )
            if pstatus == "high_risk" or QDII_RESTRICTED_NOTE_RE.search(pnote):
                if "恢复申赎" in pnote and "仅恢复赎回" not in pnote:
                    errs.append(
                        f"etf_universe.json: etfs[{idx}]({code}).premium_note claims '恢复申赎' on a high_risk/restricted ETF "
                        f"without clarifying '仅恢复赎回' -> {pnote[:80]!r}"
                    )
            if gold_tier0_active:
                name = str(item.get("name", "")).strip()
                has_ac = "asset_class" in item and item.get("asset_class") is not None
                ac_str = str(item.get("asset_class", "")).strip() if has_ac else ""
                is_gold = (
                    item.get("gold_locked") is True
                    or ac_str == "gold"
                    or norm in GOLD_ETF_CODES
                    or bool(GOLD_ETF_NAME_RE.search(name))
                )
                if is_gold:
                    role = str(item.get("action_role", "")).strip()
                    if not role or GOLD_ETF_FORBIDDEN_ROLE_RE.search(role):
                        errs.append(
                            f"Gold Tier-0 互斥冲突 (etf_universe:{code})：黄金/金矿 ETF 严禁标为底座/买入/推荐/定投/配置 -> {role!r}"
                        )
                if ac_str == "gold" and item.get("gold_locked") is not True:
                    errs.append(
                        f"Gold Tier-0 互斥冲突 (etf_universe:{code})：asset_class='gold' 须配 gold_locked=true"
                    )
                elif item.get("gold_locked") is True and has_ac and ac_str != "gold":
                    errs.append(
                        f"Gold Tier-0 互斥冲突 (etf_universe:{code})：gold_locked=true 须配 asset_class='gold'（当前为 {ac_str!r}）"
                    )

        if require_ortho_etf or "counts_by_asset_class" in eu or ac_counter:
            cbac = eu.get("counts_by_asset_class")
            if not isinstance(cbac, dict) or cbac != dict(ac_counter):
                errs.append(
                    f"etf_universe.json: counts_by_asset_class ({cbac}) != computed ({dict(ac_counter)})."
                )
        if require_ortho_etf or "counts_by_region" in eu or reg_counter:
            cbr = eu.get("counts_by_region")
            if not isinstance(cbr, dict) or cbr != dict(reg_counter):
                errs.append(
                    f"etf_universe.json: counts_by_region ({cbr}) != computed ({dict(reg_counter)})."
                )

        # Cross-DB ETF Fee Consistency: multi_asset_channels.json x etf_universe.json
        if isinstance(channels, list) and etf_fee_map:
            for ch_obj in channels:
                if not isinstance(ch_obj, dict):
                    continue
                cid = str(ch_obj.get("id", "")).strip()
                prods = ch_obj.get("products")
                if not isinstance(prods, list):
                    continue
                for pi, prod in enumerate(prods):
                    if not isinstance(prod, dict):
                        continue
                    pcode = str(prod.get("code", ""))
                    pfee = str(prod.get("fee", ""))
                    matched: dict[str, float] = {}
                    for tok in re.findall(r"[A-Za-z0-9.]+", pcode):
                        nt = _normalize_etf_code(tok)
                        if nt in etf_fee_map:
                            matched[nt] = etf_fee_map[nt]
                    if not matched:
                        continue
                    parsed_fees = _extract_annual_fee_pcts(pfee)
                    if len(matched) == 1:
                        only_code, ssot_fee = next(iter(matched.items()))
                        if (
                            parsed_fees
                            and abs(parsed_fees[0] - ssot_fee) > 0.005
                            and abs(parsed_fees[-1] - ssot_fee) > 0.005
                        ):
                            errs.append(
                                f"multi_asset_channels.json: channel {cid}.products[{pi}]({pcode}) "
                                f"fee {pfee!r} ({parsed_fees[0]:.2f}% / {parsed_fees[-1]:.2f}%) != etf_universe {only_code} ({ssot_fee:.2f}%)."
                            )
                    else:
                        lo_fee = min(matched.values())
                        hi_fee = max(matched.values())
                        if hi_fee - lo_fee > 0.05:
                            if len(parsed_fees) < 2 or min(parsed_fees) > lo_fee + 0.005 or max(parsed_fees) < hi_fee - 0.005:
                                errs.append(
                                    f"multi_asset_channels.json: channel {cid}.products[{pi}]({pcode}) "
                                    f"lists ETFs with distinct fees {matched} ({lo_fee:.2f}%..{hi_fee:.2f}%), "
                                    f"but fee {pfee!r} does not disclose both or a covering range."
                                )
                        elif parsed_fees and (
                            (parsed_fees[0] < lo_fee - 0.005 or parsed_fees[0] > hi_fee + 0.005)
                            and (parsed_fees[-1] < lo_fee - 0.005 or parsed_fees[-1] > hi_fee + 0.005)
                        ):
                            errs.append(
                                f"multi_asset_channels.json: channel {cid}.products[{pi}]({pcode}) "
                                f"fee {pfee!r} ({parsed_fees[0]:.2f}% / {parsed_fees[-1]:.2f}%) != etf_universe {matched}."
                            )

    # 4. Validate deep_dossiers (expected_pool stocks, all 7 dims non-empty, zero markup, anti-template, Gold Tier-0)
    dossiers = dd.get("dossiers")
    if not isinstance(dossiers, dict):
        errs.append("deep_dossiers.json: dossiers must be an object.")
    else:
        if len(dossiers) != expected_pool:
            errs.append(f"deep_dossiers.json: stock count {len(dossiers)} != expected pool {expected_pool}.")
        if dd.get("total_stocks") != len(dossiers):
            errs.append(f"deep_dossiers.json: total_stocks ({dd.get('total_stocks')}) != len(dossiers) ({len(dossiers)}).")
        tpl_counts: dict[tuple[str, str], Counter[str]] = {}
        for dkey, entry in dossiers.items():
            if not isinstance(entry, dict):
                errs.append(f"deep_dossiers.json[{dkey}] must be an object.")
                continue
            try:
                inventory_evidence(entry, STOCK_FIELDS, cutoff)
            except ValueError as exc:
                errs.append(f"deep_dossiers.json[{dkey}] {exc}.")
            mkt_prefix = str(dkey).split(":", 1)[0]
            for dim in DOSSIER_DIMENSIONS:
                val = entry.get(dim)
                if not isinstance(val, str) or not val.strip():
                    errs.append(f"deep_dossiers.json[{dkey}] missing non-empty {dim}.")
                    continue
                if RAW_MARKUP_RE.search(val):
                    errs.append(f"deep_dossiers.json[{dkey}].{dim} contains raw Markdown/HTML markup.")
                if dim in ("catalysts", "bear_case"):
                    norm_txt = re.sub(r"\s+", " ", val.strip())
                    tpl_counts.setdefault((mkt_prefix, dim), Counter())[norm_txt] += 1
            if gold_tier0_active:
                is_gold_stock = dkey in GOLD_DOSSIER_KEYS or bool(GOLD_MINER_TICKERS_RE.search(dkey))
                if is_gold_stock:
                    act = str(entry.get("action_etf", ""))
                    for m_base in GOLD_BASE_ROLE_RE.finditer(act):
                        prefix = re.split(r"[。！？；，,|]", act[: m_base.start()])[-1]
                        if not GOLD_BASE_NEGATION_RE.search(prefix):
                            errs.append(
                                f"Gold Tier-0 互斥冲突 (deep_dossiers:{dkey}.action_etf)：涉金标的严禁标为绿色/当下底座 -> {act[:72]}"
                            )
                            break
            if str(dkey).startswith("a-share:"):
                div_intervals: list[tuple[str, float, float, str]] = []
                for field in ("baseline_note", "valuation_anchor", "shareholder_flow", "financials"):
                    fval = str(entry.get(field, ""))
                    for m_div in A_SHARE_DIVIDEND_RE.finditer(fval):
                        pre = fval[max(0, m_div.start() - 10) : m_div.start() + 2]
                        post = fval[m_div.end() : min(len(fval), m_div.end() + 10)]
                        if DIVIDEND_QUALIFIER_RE.search(pre) or DIVIDEND_QUALIFIER_RE.search(post):
                            continue
                        v1 = float(m_div.group(1))
                        v2 = float(m_div.group(2)) if m_div.group(2) is not None else v1
                        div_intervals.append((field, min(v1, v2), max(v1, v2), m_div.group(0)))
                if len(div_intervals) >= 2:
                    max_lo = max(item[1] for item in div_intervals)
                    min_hi = min(item[2] for item in div_intervals)
                    if max_lo - min_hi > A_SHARE_DIVIDEND_TOLERANCE_PP + 1e-9:
                        detail = ", ".join(f"{fld}={txt}" for fld, _, _, txt in div_intervals)
                        errs.append(
                            f"deep_dossiers.json[{dkey}]: intra-dossier A-share dividend yield mismatch "
                            f"(spread {max_lo - min_hi:.2f}pp > {A_SHARE_DIVIDEND_TOLERANCE_PP:.2f}pp): {detail}"
                        )
        for (mkt_prefix, dim), counter in sorted(tpl_counts.items()):
            for sample, cnt in counter.items():
                if cnt > 10:
                    errs.append(
                        f"deep_dossiers.json ({mkt_prefix}): {cnt} stocks duplicate identical {dim} template (>10) -> {sample[:40]!r}"
                    )

        # Global A/H Benchmark Consistency Guard (all benchmark dossiers vs market_state ±0.6pp)
        if isinstance(market_state, dict):
            benchmarks = (
                market_state.get("cross_market_linkages", {})
                .get("ah_premium_radar", {})
                .get("benchmarks")
            )
            if isinstance(benchmarks, list):
                for bench in benchmarks:
                    if not isinstance(bench, dict):
                        continue
                    a_code = bench.get("a")
                    h_code = bench.get("h")
                    ah_pct = bench.get("ah_premium_pct")
                    if (
                        not isinstance(a_code, str) or not a_code.strip()
                        or not isinstance(h_code, str) or not h_code.strip()
                        or not isinstance(ah_pct, (int, float)) or isinstance(ah_pct, bool)
                    ):
                        continue
                    bench_pct = float(ah_pct)
                    for bkey in (f"a-share:{a_code.strip()}", f"hk-stock:{h_code.strip()}"):
                        bentry = dossiers.get(bkey)
                        if not isinstance(bentry, dict):
                            continue
                        for field in ("baseline_note", "valuation_anchor"):
                            fval = str(bentry.get(field, ""))
                            for raw_match, lo, hi in _iter_ah_premium_mentions(fval):
                                if bench_pct < lo - AH_PREMIUM_TOLERANCE_PP or bench_pct > hi + AH_PREMIUM_TOLERANCE_PP:
                                    errs.append(
                                        f"deep_dossiers.json[{bkey}].{field}: AH premium {raw_match!r} "
                                        f"drifts >{AH_PREMIUM_TOLERANCE_PP:.1f}pp from market_state benchmark {bench_pct:+.1f}%."
                                    )

    # 5. Global string scan across all 3 DBs: raw markup, banned internal words, local paths,
    # restricted codes, gold buy, relative-date tense drift, 4-digit .HK, and bare IOPV
    effective_date = as_of_date or str(ma.get("as_of_date") or eu.get("as_of_date") or dd.get("as_of_date") or "").strip()
    rel_date_patterns: list[tuple[str, re.Pattern[str]]] = []
    if effective_date and DATE_RE.fullmatch(effective_date):
        try:
            dt_cur = datetime.strptime(effective_date, "%Y-%m-%d")
            dt_prev1 = dt_cur - timedelta(days=1)
            dt_prev2 = dt_cur - timedelta(days=2)
            rel_date_patterns = [
                ("stale '明日' matching as_of_date", re.compile(rf"明日\s*[（(]?\s*0?{dt_cur.month}/0?{dt_cur.day}(?!\d)[）)]?")),
                ("stale '今日' matching yesterday", re.compile(rf"今日\s*[（(]?\s*0?{dt_prev1.month}/0?{dt_prev1.day}(?!\d)[）)]?")),
                ("stale '昨日' matching 2 days ago", re.compile(rf"昨日\s*[（(]?\s*0?{dt_prev2.month}/0?{dt_prev2.day}(?!\d)[）)]?")),
            ]
        except ValueError:
            rel_date_patterns = []

    for doc_name, doc_obj in (
        ("multi_asset_channels.json", ma),
        ("etf_universe.json", eu),
        ("deep_dossiers.json", dd),
    ):
        for jpath, sval in _walk_json_strings(doc_obj, doc_name):
            if RAW_MARKUP_RE.search(sval):
                errs.append(f"{jpath}: contains raw Markdown/HTML markup.")
            hits = BANNED_INTERNAL_RE.findall(sval)
            if hits:
                errs.append(f"{jpath}: leaked internal term(s): {sorted(set(hits))}")
            if LOCAL_PATH_RE.search(sval):
                errs.append(f"{jpath}: leaked local filesystem path.")
            for rel_label, rel_re in rel_date_patterns:
                m_rel = rel_re.search(sval)
                if m_rel:
                    errs.append(
                        f"{jpath}: relative-date tense drift ({rel_label} on {effective_date}) -> {m_rel.group(0)!r}"
                    )
            m_hk4 = HK_4DIGIT_RE.search(sval)
            if m_hk4:
                errs.append(
                    f"{jpath}: bare 4-digit HK ticker {m_hk4.group(0)!r} must use canonical 5-digit format (e.g. 0{m_hk4.group(0)})."
                )
            if doc_name == "etf_universe.json":
                for m_iopv in IOPV_RE.finditer(sval):
                    win = sval[max(0, m_iopv.start() - 20) : min(len(sval), m_iopv.end() + 20)]
                    if not IOPV_GLOSS_RE.search(win):
                        errs.append(
                            f"{jpath}: bare 'IOPV' without '参考净值'/'实时净值'/'盘中净值' within ±20 chars -> {win!r}"
                        )
                        break
            if not jpath.endswith(".code"):
                for m_rc in RESTRICTED_CODES_RE.finditer(sval):
                    win = sval[max(0, m_rc.start() - 40) : min(len(sval), m_rc.end() + 40)]
                    if not RESTRICTED_WARN_RE.search(win):
                        errs.append(
                            f"{jpath}: restricted code {m_rc.group(0)} mentioned without warning within ±40 chars -> {win!r}"
                        )
                        break
            errs.extend(_scan_text_for_crypto_buy(jpath, sval))
            if gold_tier0_active:
                errs.extend(_scan_text_for_gold_buy(jpath, sval))

    return errs


@_serialize_patch_operation
def apply_equity_patch(
    repo_root: Path = REPO_ROOT,
    *,
    dry_run: bool = False,
    keep_patch: bool = False,
    skip_edition_lock: bool = False,
) -> dict[str, Any]:
    patch_path = _safe_repo_path(repo_root, "equity", "state", "_edition_patch.json")
    ma_path = _safe_repo_path(repo_root, "equity", "state", "multi_asset_channels.json")
    eu_path = _safe_repo_path(repo_root, "equity", "state", "etf_universe.json")
    dd_path = _safe_repo_path(repo_root, "equity", "state", "deep_dossiers.json")
    pc_path = _safe_repo_path(repo_root, "equity", "state", "policy_calendar.json")
    gold_path = _safe_repo_path(repo_root, "gold", "data_snapshot.json")
    state_path = _safe_repo_path(repo_root, "equity", "state", "market_state.json")

    patch_root = _read_json_obj(patch_path, "equity/state/_edition_patch.json")
    errors: list[str] = []

    unknown_top = set(patch_root.keys()) - ALLOWED_EQUITY_PATCH_TOP_KEYS
    if unknown_top:
        errors.append(
            f"Unknown top-level key(s) in _edition_patch.json: {sorted(unknown_top)} "
            f"(allowed: {sorted(ALLOWED_EQUITY_PATCH_TOP_KEYS)})"
        )

    try:
        edition_id = _validate_edition_id(patch_root.get("edition_id"))
        edition_id_valid = True
    except ValueError as exc:
        errors.append(str(exc))
        edition_id = str(patch_root.get("edition_id") or "").strip()
        edition_id_valid = False

    if patch_root.get("as_of_date") is not None:
        try:
            as_of_date = _validate_date(patch_root["as_of_date"], "as_of_date")
        except ValueError as exc:
            errors.append(str(exc))
            as_of_date = edition_id[:10] if edition_id_valid else ""
    else:
        as_of_date = edition_id[:10] if edition_id_valid else ""

    gold_snap: dict[str, Any] | None = None
    if gold_path.is_file():
        try:
            gold_snap = _read_json_obj(gold_path, "gold/data_snapshot.json")
        except ValueError as exc:
            errors.append(str(exc))
    elif not skip_edition_lock:
        errors.append("Missing gold/data_snapshot.json for edition lock and Gold Tier-0 mirror verification.")

    market_state: dict[str, Any] | None = None
    if state_path.is_file():
        try:
            market_state = _read_json_obj(state_path, "equity/state/market_state.json")
        except ValueError as exc:
            errors.append(str(exc))
    elif not skip_edition_lock:
        errors.append("Missing equity/state/market_state.json for edition lock verification.")

    if not skip_edition_lock and edition_id_valid:
        if gold_snap is not None and gold_snap.get("edition_id") != edition_id:
            errors.append(
                f"Edition lock mismatch: patch edition_id ({edition_id!r}) != gold/data_snapshot.json ({gold_snap.get('edition_id')!r})."
            )
        if market_state is not None and market_state.get("edition_id") != edition_id:
            errors.append(
                f"Edition lock mismatch: patch edition_id ({edition_id!r}) != equity/state/market_state.json ({market_state.get('edition_id')!r})."
            )

    orig_ma: dict[str, Any] | None = None
    orig_eu: dict[str, Any] | None = None
    orig_dd: dict[str, Any] | None = None
    for attr_label, p_obj in (
        ("ma", (ma_path, "equity/state/multi_asset_channels.json")),
        ("eu", (eu_path, "equity/state/etf_universe.json")),
        ("dd", (dd_path, "equity/state/deep_dossiers.json")),
    ):
        try:
            loaded = _read_json_obj(p_obj[0], p_obj[1])
        except ValueError as exc:
            errors.append(str(exc))
            loaded = None
        if attr_label == "ma":
            orig_ma = loaded
        elif attr_label == "eu":
            orig_eu = loaded
        else:
            orig_dd = loaded

    if gold_snap is not None:
        gold_tier0_active = (
            str(gold_snap.get("tier_code", "")).strip() == "Tier 0" or gold_snap.get("new_buy_allowed") is False
        )
    else:
        default_lock = orig_eu.get("gold_tier0_locked", True) if isinstance(orig_eu, dict) else True
        gold_tier0_active = bool(patch_root.get("gold_tier0_locked", default_lock))

    expected_pool = 231
    if isinstance(market_state, dict) and isinstance(market_state.get("markets"), dict):
        counts = [
            market_state["markets"][m].get("stock_pool_count")
            for m in ("a_share", "hk_stock", "us_stock")
            if isinstance(market_state["markets"].get(m), dict)
        ]
        if len(counts) == 3 and all(type(c) is int and c > 0 for c in counts):
            expected_pool = sum(counts)
    enforce_live_contract = (
        expected_pool >= 100 and edition_id_valid and edition_id[:15] >= DATA_CONTRACT_CUTOVER
    )

    merged_ma: dict[str, Any] | None = None
    ma_stats: dict[str, Any] = {}
    if orig_ma is not None:
        merged_ma, ma_stats = _merge_multi_asset(orig_ma, patch_root, edition_id, as_of_date, errors=errors)

    merged_eu: dict[str, Any] | None = None
    eu_stats: dict[str, Any] = {}
    if orig_eu is not None:
        merged_eu, eu_stats = _merge_etf_universe(orig_eu, patch_root, edition_id, as_of_date, errors=errors)

    if enforce_live_contract:
        market_as_of = market_state.get("as_of_cst") if market_state is not None else None
        try:
            as_of_label = _live_edition_as_of_label(edition_id, market_as_of)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            for library in (merged_ma, merged_eu):
                if library is not None:
                    library["as_of_label"] = as_of_label

    merged_dd: dict[str, Any] | None = None
    dd_stats: dict[str, Any] = {}
    if orig_dd is not None:
        merged_dd, dd_stats = _merge_deep_dossiers(
            orig_dd,
            patch_root,
            edition_id,
            as_of_date,
            market_state=market_state,
            errors=errors,
        )

    merged_pc: dict[str, Any] | None = None
    pc_stats: dict[str, Any] | None = None
    if patch_root.get("policy_calendar") is not None or pc_path.is_file():
        try:
            orig_pc = _read_json_obj(pc_path, "equity/state/policy_calendar.json")
        except ValueError as exc:
            errors.append(str(exc))
            orig_pc = None
        if orig_pc is not None:
            merged_pc, pc_stats = _merge_policy_calendar(
                orig_pc,
                patch_root,
                edition_id,
                as_of_date,
                market_state=market_state,
                errors=errors,
            )

    untouched_channel_siblings = ma_stats.pop("untouched_channel_siblings", {})
    unpatched_ah_twins = dd_stats.pop("unpatched_ah_twins", {})

    # Mirror live Gold Tier-0 status if patch did not explicitly override
    if merged_eu is not None and gold_snap is not None and "gold_tier0_locked" not in patch_root:
        merged_eu["gold_tier0_locked"] = gold_tier0_active

    if merged_ma is not None and merged_eu is not None and merged_dd is not None:
        errors.extend(
            _validate_merged_equity_dbs(
                merged_ma,
                merged_eu,
                merged_dd,
                edition_id=edition_id,
                gold_tier0_active=gold_tier0_active,
                expected_pool=expected_pool,
                as_of_date=as_of_date,
                market_state=market_state,
            )
        )
    if merged_pc is not None:
        errors.extend(
            _validate_policy_calendar(
                merged_pc,
                edition_id=edition_id,
                as_of_date=as_of_date,
                gold_tier0_active=gold_tier0_active,
                market_as_of_cst=market_state.get("as_of_cst") if isinstance(market_state, dict) else None,
                enforce_live_contract=enforce_live_contract,
            )
        )
    if errors:
        formatted = "\n  - ".join(errors)
        raise ValueError(f"Pre-write validation failed ({len(errors)} error(s)):\n  - {formatted}")

    assert merged_ma is not None and merged_eu is not None and merged_dd is not None
    writes = [
        (ma_path, _serialize_json(merged_ma)),
        (eu_path, _serialize_json(merged_eu)),
        (dd_path, _serialize_json(merged_dd)),
    ]
    if merged_pc is not None:
        writes.append((pc_path, _serialize_json(merged_pc)))

    summary = {
        "mode": "apply",
        "dry_run": dry_run,
        "edition_id": edition_id,
        "as_of_date": as_of_date,
        "gold_tier0_active": gold_tier0_active,
        "multi_asset_channels": {**ma_stats, "total_channels": len(merged_ma["channels"])},
        "etf_universe": {**eu_stats, "total_etfs": merged_eu["total_etfs"]},
        "deep_dossiers": {
            **dd_stats,
            "total_stocks": merged_dd["total_stocks"],
            "core_deep_count": merged_dd["core_deep_count"],
        },
        "review_hints": {
            "untouched_channel_siblings": untouched_channel_siblings,
            "unpatched_ah_twins": unpatched_ah_twins,
        },
        "patch_deleted": False,
    }
    if merged_pc is not None and pc_stats is not None:
        summary["policy_calendar"] = {
            **pc_stats,
            "total_briefs": len(merged_pc["policy_briefs"]),
            "total_events": len(merged_pc["events"]),
        }

    if not dry_run:
        summary["patch_deleted"] = _commit_patch(repo_root, writes, patch_path, keep_patch=keep_patch)

    return summary


def _nonblank_lines(raw: bytes) -> list[bytes]:
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return [line for line in normalized.split(b"\n") if line.strip()]


def _preserves_order(prior: list[bytes], candidate: list[bytes]) -> bool:
    remaining = iter(candidate)
    return all(line in remaining for line in prior)


def _insert_before_anchor(
    text: str,
    anchor: str,
    block: str,
    *,
    file_label: str,
    allow_rollover_fallback: bool = False,
) -> str:
    clean_block = block.strip()
    if not clean_block:
        raise ValueError(f"{file_label}: insertion block must be non-empty.")
    lines = clean_block.splitlines()
    ends_with_hr = bool(lines and lines[-1].strip() == "---")
    sep = "\n\n" if ends_with_hr else "\n\n---\n\n"

    idx = text.find(anchor)
    if idx >= 0:
        prefix = text[:idx]
        suffix = text[idx:]
        if prefix and not prefix.endswith("\n\n"):
            prefix = prefix.rstrip("\n") + "\n\n"
        return f"{prefix}{clean_block}{sep}{suffix}"

    if not allow_rollover_fallback:
        raise ValueError(f"{file_label}: anchor {anchor!r} not found; cannot safely prepend.")

    # Monthly-rollover fallback: insert after first '---' separator, or after the first '# ...' heading block.
    m_hr = re.search(r"(?:^|\n)[ \t]*---[ \t]*(?:\n|$)", text)
    if m_hr is not None:
        prefix = text[: m_hr.end()].rstrip("\n") + "\n\n"
        suffix = text[m_hr.end() :]
        if suffix.strip():
            return f"{prefix}{clean_block}{sep}{suffix.lstrip(chr(10))}"
        return f"{prefix}{clean_block}\n"

    m_h1 = re.search(r"(?:^|\n)#+ [^\n]*(?:\n|$)", text)
    if m_h1 is not None:
        pos = m_h1.end()
        tail = text[pos:]
        # Keep any immediately contiguous intro blockquote / blank lines attached to the H1 header.
        offset = 0
        for raw_ln in tail.splitlines(keepends=True):
            stripped = raw_ln.strip()
            if stripped == "" or stripped.startswith(">"):
                offset += len(raw_ln)
            else:
                break
        split_at = pos + offset
        prefix = text[:split_at].rstrip("\n") + "\n\n---\n\n"
        suffix = text[split_at:]
        if suffix.strip():
            return f"{prefix}{clean_block}{sep}{suffix.lstrip(chr(10))}"
        return f"{prefix}{clean_block}\n"

    raise ValueError(
        f"{file_label}: anchor {anchor!r} not found and no '---' or heading block available for monthly-rollover fallback."
    )


def _validate_gold_edition_review(
    review_obj: object,
    edition_id: str,
    gold_snap: dict[str, Any] | None,
) -> None:
    if not isinstance(review_obj, dict):
        raise ValueError("audit_review_block_md GOLD_EDITION_REVIEW must be a JSON object.")
    if review_obj.get("edition_id") != edition_id:
        raise ValueError(
            f"audit_review_block_md GOLD_EDITION_REVIEW.edition_id ({review_obj.get('edition_id')!r}) != {edition_id!r}."
        )
    as_of_short = review_obj.get("as_of_short")
    if not isinstance(as_of_short, str) or not AS_OF_SHORT_RE.fullmatch(as_of_short):
        raise ValueError(
            f"GOLD_EDITION_REVIEW.as_of_short must match YYYY-MM-DD HH:MM, got {as_of_short!r}."
        )
    try:
        datetime.strptime(as_of_short, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ValueError(f"GOLD_EDITION_REVIEW.as_of_short invalid timestamp {as_of_short!r}: {exc}") from exc
    if isinstance(gold_snap, dict) and gold_snap.get("edition_id") == edition_id:
        snap_as_of = gold_snap.get("as_of_short")
        if snap_as_of != as_of_short:
            raise ValueError(
                f"GOLD_EDITION_REVIEW.as_of_short ({as_of_short!r}) != gold/data_snapshot.json as_of_short ({snap_as_of!r})."
            )

    note = review_obj.get("note")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("GOLD_EDITION_REVIEW.note must be a non-empty string.")

    sources = review_obj.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("GOLD_EDITION_REVIEW.sources must be an object containing all 4 entry gates.")
    for gate_id in ENTRY_GATE_IDS:
        links = sources.get(gate_id)
        if not isinstance(links, list) or not links or not all(_is_strict_https_url(link) for link in links):
            raise ValueError(
                f"GOLD_EDITION_REVIEW.sources[{gate_id!r}] must be a non-empty list of strict https:// URLs."
            )

    forecast = review_obj.get("forecast_review")
    if not isinstance(forecast, dict):
        raise ValueError("GOLD_EDITION_REVIEW.forecast_review must be a JSON object.")
    fc_status = forecast.get("status")
    if fc_status not in ALLOWED_FORECAST_REVIEW_STATUSES:
        raise ValueError(
            f"GOLD_EDITION_REVIEW.forecast_review.status must be one of {sorted(ALLOWED_FORECAST_REVIEW_STATUSES)}, got {fc_status!r}."
        )
    fc_note = forecast.get("note")
    if not isinstance(fc_note, str) or not fc_note.strip():
        raise ValueError("GOLD_EDITION_REVIEW.forecast_review.note must be a non-empty string.")
    fc_sources = forecast.get("sources")
    if not isinstance(fc_sources, list) or not all(_is_strict_https_url(link) for link in fc_sources):
        raise ValueError("GOLD_EDITION_REVIEW.forecast_review.sources must be a list of strict https:// URLs.")
    if fc_status == "settled" and not fc_sources:
        raise ValueError("GOLD_EDITION_REVIEW.forecast_review.sources must be non-empty when status == 'settled'.")


@_serialize_patch_operation
def prepend_gold_ledgers(
    repo_root: Path = REPO_ROOT,
    *,
    dry_run: bool = False,
    keep_patch: bool = False,
) -> dict[str, Any]:
    patch_path = _safe_repo_path(repo_root, "gold", "daily", "_ledger_patch.json")
    changelog_path = _safe_repo_path(repo_root, "gold", "daily", "CHANGELOG.md")
    audit_path = _safe_repo_path(repo_root, "gold", "daily", "AUDIT_LOG.md")
    gold_snap_path = _safe_repo_path(repo_root, "gold", "data_snapshot.json")

    patch = _read_json_obj(patch_path, "gold/daily/_ledger_patch.json")
    unknown = set(patch.keys()) - ALLOWED_LEDGER_PATCH_KEYS
    if unknown:
        raise ValueError(
            f"Unknown key(s) in _ledger_patch.json: {sorted(unknown)} "
            f"(allowed: {sorted(ALLOWED_LEDGER_PATCH_KEYS)})"
        )

    edition_id = _validate_edition_id(patch.get("edition_id"))
    changelog_entry = patch.get("changelog_entry_md")
    audit_review_block = patch.get("audit_review_block_md")
    audit_source_index = patch.get("audit_source_index_md")

    if not isinstance(changelog_entry, str) or not changelog_entry.strip():
        raise ValueError("_ledger_patch.json requires non-empty 'changelog_entry_md'.")
    if not isinstance(audit_review_block, str) or not audit_review_block.strip():
        raise ValueError("_ledger_patch.json requires non-empty 'audit_review_block_md'.")
    if audit_source_index is not None and (not isinstance(audit_source_index, str) or not audit_source_index.strip()):
        raise ValueError("_ledger_patch.json 'audit_source_index_md' must be null or a non-empty string.")

    for label, sval in (
        ("changelog_entry_md", changelog_entry),
        ("audit_review_block_md", audit_review_block),
        ("audit_source_index_md", audit_source_index or ""),
    ):
        if LOCAL_PATH_RE.search(sval):
            raise ValueError(f"_ledger_patch.json.{label} leaks a local filesystem path.")

    # Pre-write check on public changelog_entry_md: zero internal leaks & zero deprecated binary links
    visible_cl = _strip_html_comments(changelog_entry)
    cl_leaks = BANNED_INTERNAL_RE.findall(visible_cl)
    if cl_leaks:
        raise ValueError(
            f"_ledger_patch.json.changelog_entry_md leaks banned internal term(s): {sorted(set(cl_leaks))}"
        )
    cl_bin_links = DEPRECATED_BINARY_LINK_RE.findall(visible_cl)
    if cl_bin_links:
        raise ValueError(
            f"_ledger_patch.json.changelog_entry_md contains deprecated local binary/release link(s): {sorted(set(cl_bin_links))[:5]}"
        )

    # Ensure CHANGELOG entry carries the canonical edition marker on line 1 (strictly before any heading)
    first_cl_line = next((ln.strip() for ln in changelog_entry.splitlines() if ln.strip()), "")
    cl_markers = GOLD_CHANGELOG_MARKER_RE.findall(changelog_entry)
    if cl_markers or "GOLD_EDITION_CHANGELOG" in changelog_entry:
        if cl_markers != [edition_id]:
            raise ValueError(
                f"changelog_entry_md GOLD_EDITION_CHANGELOG marker(s) {cl_markers!r} do not match edition_id {edition_id!r}."
            )
        if not re.match(r"^<!--\s*GOLD_EDITION_CHANGELOG\b", first_cl_line):
            raise ValueError(
                "changelog_entry_md must place <!-- GOLD_EDITION_CHANGELOG ... --> on the first non-empty line "
                "(strictly before any #/##/### heading) to prevent orphan headings."
            )
        normalized_changelog_entry = changelog_entry.strip()
    else:
        normalized_changelog_entry = f"<!-- GOLD_EDITION_CHANGELOG {edition_id} -->\n\n{changelog_entry.strip()}"

    # Validate GOLD_EDITION_REVIEW JSON inside audit_review_block_md (must be on line 1 before any heading)
    first_au_line = next((ln.strip() for ln in audit_review_block.splitlines() if ln.strip()), "")
    if not re.match(r"^<!--\s*GOLD_EDITION_REVIEW\b", first_au_line):
        raise ValueError(
            "audit_review_block_md must place <!-- GOLD_EDITION_REVIEW {...} --> on the first non-empty line "
            "(strictly before any #/##/### heading) to prevent orphan headings."
        )
    review_matches = GOLD_REVIEW_BLOCK_RE.findall(audit_review_block)
    if len(review_matches) != 1:
        raise ValueError(
            f"audit_review_block_md must contain exactly one <!-- GOLD_EDITION_REVIEW {{...}} --> JSON block (found {len(review_matches)})."
        )
    try:
        review_obj = json.loads(review_matches[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"audit_review_block_md GOLD_EDITION_REVIEW JSON syntax error: {exc}") from exc

    gold_snap: dict[str, Any] | None = None
    if gold_snap_path.is_file():
        gold_snap = _read_json_obj(gold_snap_path, "gold/data_snapshot.json")
    _validate_gold_edition_review(review_obj, edition_id, gold_snap)

    if not changelog_path.is_file():
        raise ValueError("Missing gold/daily/CHANGELOG.md.")
    if not audit_path.is_file():
        raise ValueError("Missing gold/daily/AUDIT_LOG.md.")

    orig_changelog_bytes = changelog_path.read_bytes()
    orig_audit_bytes = audit_path.read_bytes()
    orig_changelog = orig_changelog_bytes.decode("utf-8")
    orig_audit = orig_audit_bytes.decode("utf-8")

    # Idempotency guard: reject duplicate edition_id across active AND archived gold ledgers
    archive_dir = _safe_repo_path(repo_root, "gold", "daily", "archive")
    cl_sources: list[tuple[str, str]] = [("gold/daily/CHANGELOG.md", orig_changelog)]
    au_sources: list[tuple[str, str]] = [("gold/daily/AUDIT_LOG.md", orig_audit)]
    if archive_dir.is_dir():
        for arc_cl in sorted(archive_dir.glob("CHANGELOG_*.md")):
            cl_sources.append((f"gold/daily/archive/{arc_cl.name}", arc_cl.read_text(encoding="utf-8")))
        for arc_au in sorted(archive_dir.glob("AUDIT_LOG_*.md")):
            au_sources.append((f"gold/daily/archive/{arc_au.name}", arc_au.read_text(encoding="utf-8")))
    for src_label, src_text in cl_sources:
        existing_cl_ids = set(GOLD_CHANGELOG_MARKER_RE.findall(src_text))
        if edition_id in existing_cl_ids:
            raise ValueError(f"{src_label} already contains GOLD_EDITION_CHANGELOG {edition_id}; refusing duplicate prepend.")
    for src_label, src_text in au_sources:
        for raw_block in GOLD_REVIEW_BLOCK_RE.findall(src_text):
            try:
                obj = json.loads(raw_block)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("edition_id") == edition_id:
                raise ValueError(f"{src_label} already contains GOLD_EDITION_REVIEW for {edition_id}; refusing duplicate prepend.")

    new_changelog = _insert_before_anchor(
        orig_changelog,
        "<!-- GOLD_EDITION_CHANGELOG",
        normalized_changelog_entry,
        file_label="gold/daily/CHANGELOG.md",
        allow_rollover_fallback=True,
    )
    new_audit = _insert_before_anchor(
        orig_audit,
        "<!-- GOLD_EDITION_REVIEW",
        audit_review_block,
        file_label="gold/daily/AUDIT_LOG.md",
        allow_rollover_fallback=True,
    )
    source_index_inserted = False
    if audit_source_index is not None:
        if "### 📌 最新 8 大类" in new_audit:
            new_audit = _insert_before_anchor(
                new_audit,
                "### 📌 最新 8 大类",
                audit_source_index,
                file_label="gold/daily/AUDIT_LOG.md",
            )
        else:
            new_audit = f"{new_audit.rstrip()}\n\n---\n\n{audit_source_index.strip()}\n"
        source_index_inserted = True

    new_changelog_bytes = new_changelog.encode("utf-8")
    new_audit_bytes = new_audit.encode("utf-8")

    # Mathematical order-preservation proof before writing any byte
    orig_cl_lines = _nonblank_lines(orig_changelog_bytes)
    new_cl_lines = _nonblank_lines(new_changelog_bytes)
    if not _preserves_order(orig_cl_lines, new_cl_lines):
        raise ValueError("Mathematical proof failed: gold/daily/CHANGELOG.md lost or reordered prior nonblank lines.")

    orig_au_lines = _nonblank_lines(orig_audit_bytes)
    new_au_lines = _nonblank_lines(new_audit_bytes)
    if not _preserves_order(orig_au_lines, new_au_lines):
        raise ValueError("Mathematical proof failed: gold/daily/AUDIT_LOG.md lost or reordered prior nonblank lines.")

    summary = {
        "mode": "prepend-gold-ledgers",
        "dry_run": dry_run,
        "edition_id": edition_id,
        "changelog_prior_lines": len(orig_cl_lines),
        "changelog_new_lines": len(new_cl_lines),
        "audit_prior_lines": len(orig_au_lines),
        "audit_new_lines": len(new_au_lines),
        "audit_source_index_inserted": source_index_inserted,
        "order_proof_verified": True,
        "patch_deleted": False,
    }

    if not dry_run:
        summary["patch_deleted"] = _commit_patch(repo_root, [
            (changelog_path, new_changelog_bytes),
            (audit_path, new_audit_bytes),
        ], patch_path, keep_patch=keep_patch)

    return summary


def _edition_sort_key(edition_id: str) -> tuple[str, int, int]:
    validated = _validate_edition_id(edition_id)
    match = EDITION_RE.fullmatch(validated)
    assert match is not None
    return match.group(1), int(match.group(2)), int(match.group(3) or 1)


def _is_http_or_https_url(value: object) -> bool:
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        return parsed.scheme in {"http", "https"} and bool(host)
    except ValueError:
        return False


def _validate_rsi_patch_entry(
    entry: dict[str, Any],
    patch_label: str,
    *,
    expected_dims: list[str] | None = None,
    require_six_dims: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    run_id = _validate_edition_id(entry.get("run_id"))
    current_key = _edition_sort_key(run_id)

    for jpath, sval in _walk_json_strings(entry, patch_label, skip_keys=frozenset()):
        if LOCAL_PATH_RE.search(sval):
            raise ValueError(f"{jpath}: leaked local filesystem path.")

    scores = entry.get("scores")
    if not isinstance(scores, dict) or not scores:
        raise ValueError(f"{patch_label} requires a non-empty 'scores' object.")
    if expected_dims is not None:
        if (
            not isinstance(expected_dims, list)
            or not expected_dims
            or any(not isinstance(d, str) or not d.strip() for d in expected_dims)
            or len(set(expected_dims)) != len(expected_dims)
        ):
            raise ValueError(f"{patch_label}: target score_dimensions must be a list of unique non-empty strings.")
        if require_six_dims and len(expected_dims) != 6:
            raise ValueError(f"{patch_label}: target score_dimensions must have exactly 6 unique dimensions.")
        expected_set = set(expected_dims)
        if set(scores.keys()) != expected_set:
            raise ValueError(
                f"{patch_label}.scores keys {sorted(scores.keys())} do not match target score_dimensions {sorted(expected_set)}."
            )
    elif require_six_dims:
        if len(scores) != 6 or any(not isinstance(k, str) or not k.strip() for k in scores):
            raise ValueError(
                f"{patch_label}.scores must contain exactly 6 dimension keys (got {len(scores)})."
            )
    else:
        if any(not isinstance(k, str) or not k.strip() for k in scores):
            raise ValueError(f"{patch_label}.scores keys must be non-empty strings.")

    score_sum = 0
    for dim_k, dim_v in scores.items():
        if type(dim_v) is not int or not (1 <= dim_v <= 5):
            raise ValueError(
                f"{patch_label}.scores[{dim_k!r}] must be an int (not bool) in 1..5, got {dim_v!r}."
            )
        score_sum += dim_v

    total_score = entry.get("total_score")
    if type(total_score) is not int or total_score != score_sum:
        raise ValueError(
            f"{patch_label}.total_score ({total_score!r}) must equal sum(scores.values()) ({score_sum})."
        )
    max_score = entry.get("max_score")
    if type(max_score) is not int or max_score != 30:
        raise ValueError(f"{patch_label}.max_score must be integer 30, got {max_score!r}.")

    closure = entry.get("review_closure")
    if not isinstance(closure, dict) or closure.get("reviewer_completed") is not True:
        raise ValueError(f"{patch_label} requires review_closure.reviewer_completed == true.")
    findings = closure.get("findings")
    if not isinstance(findings, list):
        raise ValueError(f"{patch_label} requires review_closure.findings to be a list.")

    for idx, finding in enumerate(findings, start=1):
        flabel = f"{patch_label}.review_closure.findings[{idx}]"
        if not isinstance(finding, dict):
            raise ValueError(f"{flabel} must be a JSON object.")
        desc = finding.get("description")
        if not isinstance(desc, str) or not desc.strip():
            raise ValueError(f"{flabel} requires a non-empty 'description'.")
        status = finding.get("status")
        if status not in ALLOWED_RSI_FINDING_STATUSES:
            raise ValueError(
                f"{flabel} has invalid status {status!r} (allowed: {sorted(ALLOWED_RSI_FINDING_STATUSES)})."
            )
        evidence = finding.get("evidence")
        if status == "resolved":
            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError(f"{flabel} requires non-empty string 'evidence' when status == 'resolved'.")
        elif status == "deferred_data":
            if not isinstance(evidence, dict):
                raise ValueError(f"{flabel} requires an 'evidence' object when status == 'deferred_data'.")
            disp = evidence.get("disposition")
            if not isinstance(disp, str) or not disp.strip():
                raise ValueError(f"{flabel}.evidence requires a non-empty 'disposition'.")
            if not _is_http_or_https_url(evidence.get("source")):
                raise ValueError(f"{flabel}.evidence requires a valid http(s) 'source' URL.")
            due_raw = evidence.get("due_edition")
            try:
                due_key = _edition_sort_key(due_raw) if isinstance(due_raw, str) else None
            except ValueError:
                due_key = None
            if due_key is None or due_key <= current_key:
                raise ValueError(f"{flabel}.evidence.due_edition ({due_raw!r}) must be a valid edition later than {run_id!r}.")
        elif status == "disclosed_caveat":
            if not isinstance(evidence, dict):
                raise ValueError(f"{flabel} requires an 'evidence' object when status == 'disclosed_caveat'.")
            disp = evidence.get("disposition")
            if not isinstance(disp, str) or not disp.strip():
                raise ValueError(f"{flabel}.evidence requires a non-empty 'disposition'.")
            if "source" in evidence and evidence["source"] is not None:
                if not _is_http_or_https_url(evidence["source"]):
                    raise ValueError(f"{flabel}.evidence.source must be a valid http(s) URL when provided.")
            if "due_edition" in evidence and evidence["due_edition"] is not None:
                due_raw = evidence["due_edition"]
                try:
                    due_key = _edition_sort_key(due_raw) if isinstance(due_raw, str) else None
                except ValueError:
                    due_key = None
                if due_key is None or due_key <= current_key:
                    raise ValueError(
                        f"{flabel}.evidence.due_edition ({due_raw!r}) must be a valid edition later than {run_id!r}."
                    )

    return run_id, findings


@_serialize_patch_operation
def append_rsi_metrics(
    repo_root: Path = REPO_ROOT,
    *,
    track: str,
    dry_run: bool = False,
    keep_patch: bool = False,
) -> dict[str, Any]:
    if track == "gold":
        patch_parts = ("gold", "daily", "_rsi_patch.json")
        target_parts = ("gold", "daily", "rsi_metrics.json")
        mode_name = "append-gold-rsi"
    elif track == "equity":
        patch_parts = ("equity", "state", "_rsi_patch.json")
        target_parts = ("equity", "state", "rsi_metrics.json")
        mode_name = "append-equity-rsi"
    else:
        raise ValueError(f"Unknown RSI track: {track!r} (allowed: ['equity', 'gold'])")

    patch_label = "/".join(patch_parts)
    target_label = "/".join(target_parts)
    patch_path = _safe_repo_path(repo_root, *patch_parts)
    target_path = _safe_repo_path(repo_root, *target_parts)

    entry = _read_json_obj(patch_path, patch_label)

    if not target_path.is_file():
        raise ValueError(f"Missing required JSON file: {target_label}")
    try:
        target_raw = json.loads(target_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot parse {target_label}: {exc}") from exc

    if not isinstance(target_raw, dict):
        raise ValueError(f"{target_label} root must be a JSON object with a 'runs' list (list-root is forbidden).")
    runs = target_raw.get("runs")
    if not isinstance(runs, list):
        raise ValueError(f"{target_label} must contain a 'runs' list.")

    target_dims = target_raw.get("score_dimensions")
    run_id, findings = _validate_rsi_patch_entry(
        entry,
        patch_label,
        expected_dims=target_dims,
        require_six_dims=(track == "gold"),
    )
    requires_receipt = _edition_sort_key(run_id) > review_evidence.LAST_LEGACY_EDITION
    if requires_receipt:
        candidate = review_evidence.working_snapshot(repo_root, run_id)
        review_evidence.validate_receipt(
            entry["review_closure"], candidate, patch_label,
            read=lambda path: review_evidence.read_working_file(repo_root, path),
        )
        baseline = review_evidence.read_working_backfill_baseline(repo_root, run_id, track)
        if baseline is not None:
            review_evidence.validate_backfill_rechecks(
                entry["review_closure"], run_id, track, baseline,
                review_evidence.read_working_file(repo_root, review_evidence.BACKFILL_STATE_PATHS[track]),
            )
        if "superseded_reviews" in entry:
            raise ValueError(f"{patch_label} cannot supply its own superseded review history.")

    target_obj: dict[str, Any] = copy.deepcopy(target_raw)
    target_runs = target_obj["runs"]

    prior_runs = len(target_runs)
    matches = [
        index for index, existing in enumerate(target_runs)
        if isinstance(existing, dict) and existing.get("run_id") == run_id
    ]
    if len(matches) > 1 or (matches and not requires_receipt):
        raise ValueError(f"{target_label} already contains run_id {run_id!r}; refusing duplicate append.")
    if matches:
        index = matches[0]
        existing = target_runs[index]
        history = existing.pop("superseded_reviews", [])
        if not isinstance(history, list):
            raise ValueError(f"{target_label} has invalid superseded review history for {run_id!r}.")
        if existing != entry:
            prior_closure = existing.get("review_closure") or {}
            if prior_closure.get("candidate_sha256") == candidate["candidate_sha256"]:
                raise ValueError(f"{target_label} already has a different receipt for this review candidate.")
            history = [*history, existing]
        target_runs[index] = {**entry, **({"superseded_reviews": history} if history else {})}
    else:
        target_runs.append(copy.deepcopy(entry))
    new_bytes = (json.dumps(target_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    summary = {
        "mode": mode_name,
        "dry_run": dry_run,
        "run_id": run_id,
        "prior_runs": prior_runs,
        "new_runs": len(target_runs),
        "findings_count": len(findings),
        "patch_deleted": False,
    }

    if not dry_run:
        summary["patch_deleted"] = _commit_patch(repo_root, [(target_path, new_bytes)], patch_path, keep_patch=keep_patch)

    return summary


def append_gold_rsi(
    repo_root: Path = REPO_ROOT,
    *,
    dry_run: bool = False,
    keep_patch: bool = False,
) -> dict[str, Any]:
    return append_rsi_metrics(repo_root, track="gold", dry_run=dry_run, keep_patch=keep_patch)


def append_equity_rsi(
    repo_root: Path = REPO_ROOT,
    *,
    dry_run: bool = False,
    keep_patch: bool = False,
) -> dict[str, Any]:
    return append_rsi_metrics(repo_root, track="equity", dry_run=dry_run, keep_patch=keep_patch)


def _insert_after_first_hr(text: str, block: str, *, file_label: str) -> str:
    clean_block = block.strip()
    if not clean_block:
        raise ValueError(f"{file_label}: insertion block must be non-empty.")
    lines = clean_block.splitlines()
    ends_with_hr = bool(lines and lines[-1].strip() == "---")
    sep = "\n\n" if ends_with_hr else "\n\n---\n\n"
    m_hr = re.search(r"(?:^|\n)[ \t]*---[ \t]*(?:\n|$)", text)
    if m_hr is not None:
        prefix = text[: m_hr.end()].rstrip("\n") + "\n\n"
        suffix = text[m_hr.end() :]
        if suffix.strip():
            return f"{prefix}{clean_block}{sep}{suffix.lstrip(chr(10))}"
        return f"{prefix}{clean_block}\n"

    # Monthly-rollover fallback when '---' is absent: insert after top H1 + contiguous intro blockquote.
    m_h1 = re.search(r"(?:^|\n)#+ [^\n]*(?:\n|$)", text)
    if m_h1 is not None:
        pos = m_h1.end()
        tail = text[pos:]
        offset = 0
        for raw_ln in tail.splitlines(keepends=True):
            stripped = raw_ln.strip()
            if stripped == "" or stripped.startswith(">"):
                offset += len(raw_ln)
            else:
                break
        split_at = pos + offset
        prefix = text[:split_at].rstrip("\n") + "\n\n---\n\n"
        suffix = text[split_at:]
        if suffix.strip():
            return f"{prefix}{clean_block}{sep}{suffix.lstrip(chr(10))}"
        return f"{prefix}{clean_block}\n"

    raise ValueError(f"{file_label}: no '---' separator or heading block found; cannot safely prepend.")


@_serialize_patch_operation
def prepend_equity_audit(
    repo_root: Path = REPO_ROOT,
    *,
    dry_run: bool = False,
    keep_patch: bool = False,
) -> dict[str, Any]:
    patch_path = _safe_repo_path(repo_root, "equity", "state", "_audit_patch.json")
    audit_path = _safe_repo_path(repo_root, "equity", "state", "audit_ledger.md")

    patch = _read_json_obj(patch_path, "equity/state/_audit_patch.json")
    unknown = set(patch.keys()) - ALLOWED_EQUITY_AUDIT_PATCH_KEYS
    if unknown:
        raise ValueError(
            f"Unknown key(s) in _audit_patch.json: {sorted(unknown)} "
            f"(allowed: {sorted(ALLOWED_EQUITY_AUDIT_PATCH_KEYS)})"
        )

    edition_id = _validate_edition_id(patch.get("edition_id"))
    entry_md = patch.get("entry_md")
    note = patch.get("note")
    if not isinstance(entry_md, str) or not entry_md.strip():
        raise ValueError("_audit_patch.json requires non-empty 'entry_md'.")
    if note is not None and not isinstance(note, str):
        raise ValueError("_audit_patch.json 'note' must be a string or null.")

    for label, sval in (("entry_md", entry_md), ("note", note or "")):
        if LOCAL_PATH_RE.search(sval):
            raise ValueError(f"_audit_patch.json.{label} leaks a local filesystem path.")

    if not audit_path.is_file():
        raise ValueError("Missing equity/state/audit_ledger.md.")

    orig_bytes = audit_path.read_bytes()
    orig_text = orig_bytes.decode("utf-8")

    heading_ed_re = re.compile(
        rf"^##\s+.*(?<![A-Za-z0-9_]){re.escape(edition_id)}(?![A-Za-z0-9_])",
        re.MULTILINE,
    )
    if heading_ed_re.search(orig_text):
        raise ValueError(
            f"equity/state/audit_ledger.md already contains a '## ' heading for {edition_id}; refusing duplicate prepend."
        )
    if not heading_ed_re.search(entry_md):
        raise ValueError(
            f"_audit_patch.json.entry_md must contain a '## ' heading referencing edition_id {edition_id!r}."
        )

    new_text = _insert_after_first_hr(orig_text, entry_md, file_label="equity/state/audit_ledger.md")
    new_bytes = new_text.encode("utf-8")

    orig_lines = _nonblank_lines(orig_bytes)
    new_lines = _nonblank_lines(new_bytes)
    if not _preserves_order(orig_lines, new_lines):
        raise ValueError("Mathematical proof failed: equity/state/audit_ledger.md lost or reordered prior nonblank lines.")

    summary = {
        "mode": "prepend-equity-audit",
        "dry_run": dry_run,
        "edition_id": edition_id,
        "audit_prior_lines": len(orig_lines),
        "audit_new_lines": len(new_lines),
        "order_proof_verified": True,
        "patch_deleted": False,
    }

    if not dry_run:
        summary["patch_deleted"] = _commit_patch(repo_root, [(audit_path, new_bytes)], patch_path, keep_patch=keep_patch)

    return summary


def _validate_period_slug(value: object, label: str) -> str:
    if not isinstance(value, str) or not PERIOD_SLUG_RE.fullmatch(value.strip()):
        raise ValueError(f"{label} must match YYYY_MM (01..12), got {value!r}.")
    return value.strip()


def _replace_period_in_text(text: str, prev_slug: str, new_slug: str) -> str:
    prev_y, prev_m = int(prev_slug[:4]), int(prev_slug[5:7])
    new_y, new_m = int(new_slug[:4]), int(new_slug[5:7])
    out = text.replace(prev_slug, new_slug)
    out = out.replace(f"{prev_y:04d}-{prev_m:02d}", f"{new_y:04d}-{new_m:02d}")
    out = out.replace(f"{prev_y:04d}年{prev_m:02d}月", f"{new_y:04d}年{new_m:02d}月")
    if prev_m < 10:
        out = out.replace(f"{prev_y:04d}年{prev_m}月", f"{new_y:04d}年{new_m}月")
    return out


def _extract_appendix2_raw_rows(md_text: str) -> list[str] | None:
    """Return raw data rows from the largest Markdown table inside Appendix 2 (附[录表]二)."""
    m = re.search(
        r"(?:^|\n)#{1,3}\s*附[录表]二[^\n]*\n(.*?)(?=\n#{1,2}\s*(?:附[录表]三|免责声明)|$)",
        md_text,
        flags=re.DOTALL,
    )
    if not m:
        return None
    sec = m.group(1)
    tables: list[list[str]] = []
    cur: list[str] = []
    for ln in sec.splitlines():
        st = ln.strip()
        if st.startswith("|") and st.endswith("|"):
            cur.append(st)
        elif cur:
            tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    best_rows: list[str] = []
    for tbl in tables:
        data_rows: list[str] = []
        for r in tbl[1:]:
            cells = [c.strip() for c in r.strip("|").split("|")]
            if not all(re.match(r"^:?-{2,}:?$", c) for c in cells):
                data_rows.append(r)
        if len(data_rows) > len(best_rows):
            best_rows = data_rows
    return best_rows if best_rows else None


@_serialize_patch_operation
def rollover_equity_month(
    repo_root: Path = REPO_ROOT,
    *,
    dry_run: bool = False,
    keep_patch: bool = False,
) -> dict[str, Any]:
    patch_path = _safe_repo_path(repo_root, "equity", "state", "_rollover_patch.json")
    patch = _read_json_obj(patch_path, "equity/state/_rollover_patch.json")

    unknown_top = set(patch.keys()) - ALLOWED_ROLLOVER_PATCH_KEYS
    if unknown_top:
        raise ValueError(
            f"Unknown key(s) in _rollover_patch.json: {sorted(unknown_top)} "
            f"(allowed: {sorted(ALLOWED_ROLLOVER_PATCH_KEYS)})"
        )

    prev_slug = _validate_period_slug(patch.get("prev_period_slug"), "prev_period_slug")
    new_slug = _validate_period_slug(patch.get("new_period_slug"), "new_period_slug")
    if new_slug <= prev_slug:
        raise ValueError(
            f"new_period_slug ({new_slug!r}) must be strictly later than prev_period_slug ({prev_slug!r})."
        )

    as_of_full_raw = patch.get("as_of_full")
    if not isinstance(as_of_full_raw, str) or not as_of_full_raw.strip():
        raise ValueError("_rollover_patch.json requires a non-empty string 'as_of_full'.")
    as_of_full = as_of_full_raw.strip()
    expected_prefix = new_slug.replace("_", "-")
    new_year, new_month = int(new_slug[:4]), int(new_slug[5:7])
    m_cutoff = FLAGSHIP_CUTOFF_RE.match(as_of_full)
    cutoff_dt: datetime | None = None
    if m_cutoff is not None:
        try:
            cutoff_dt = datetime.strptime(
                f"{m_cutoff.group(1)} {m_cutoff.group(2)}",
                "%Y年%m月%d日 %H:%M" if "年" in m_cutoff.group(1) else "%Y-%m-%d %H:%M",
            )
        except ValueError:
            cutoff_dt = None
    if cutoff_dt is None:
        raise ValueError(
            f"_rollover_patch.json.as_of_full ({as_of_full!r}) must match 'YYYY-MM-DD HH:MM' or "
            f"'YYYY年MM月DD日 HH:MM' and start with {expected_prefix!r} (or '{new_year:04d}年{new_month:02d}月')."
        )
    if cutoff_dt.strftime("%Y_%m") != new_slug:
        raise ValueError(
            f"_rollover_patch.json.as_of_full ({as_of_full!r}) must start with {expected_prefix!r} "
            f"(or '{new_year:04d}年{new_month:02d}月') matching new_period_slug {new_slug!r}."
        )
    if LOCAL_PATH_RE.search(as_of_full):
        raise ValueError("_rollover_patch.json.as_of_full leaks a local filesystem path.")
    as_of_leaks = BANNED_INTERNAL_RE.findall(as_of_full)
    if as_of_leaks:
        raise ValueError(f"_rollover_patch.json.as_of_full leaks banned internal term(s): {sorted(set(as_of_leaks))}")

    yf_raw = patch.get("as_of_year_float")
    if type(yf_raw) not in (int, float) or not math.isfinite(yf_raw):
        raise ValueError(f"_rollover_patch.json.as_of_year_float must be a finite float, got {yf_raw!r}.")
    as_of_year_float = float(yf_raw)
    if not (new_year <= as_of_year_float < new_year + 1.0):
        raise ValueError(
            f"_rollover_patch.json.as_of_year_float ({as_of_year_float}) does not match year {new_year}."
        )

    top_benchmark_time: str | None = None
    if patch.get("benchmark_time") is not None:
        bt_raw = patch["benchmark_time"]
        if not isinstance(bt_raw, str) or not bt_raw.strip():
            raise ValueError("_rollover_patch.json.benchmark_time must be a non-empty string or null.")
        top_benchmark_time = bt_raw.strip()
        if LOCAL_PATH_RE.search(top_benchmark_time):
            raise ValueError("_rollover_patch.json.benchmark_time leaks a local filesystem path.")
        bt_leaks = BANNED_INTERNAL_RE.findall(top_benchmark_time)
        if bt_leaks:
            raise ValueError(f"_rollover_patch.json.benchmark_time leaks banned internal term(s): {sorted(set(bt_leaks))}")

    note = patch.get("note")
    if note is not None:
        if not isinstance(note, str):
            raise ValueError("_rollover_patch.json.note must be a string or null.")
        if LOCAL_PATH_RE.search(note):
            raise ValueError("_rollover_patch.json.note leaks a local filesystem path.")

    markets_cfg = patch.get("markets")
    if markets_cfg is None:
        markets_cfg = {}
    elif not isinstance(markets_cfg, dict):
        raise ValueError("_rollover_patch.json.markets must be an object keyed by market name.")
    else:
        unknown_mkts = set(markets_cfg.keys()) - set(ROLLOVER_MARKETS)
        if unknown_mkts:
            raise ValueError(
                f"Unknown market(s) in _rollover_patch.json.markets: {sorted(unknown_mkts)} "
                f"(allowed: {list(ROLLOVER_MARKETS)})"
            )

    writes: list[tuple[Path, bytes]] = []
    market_summaries: dict[str, Any] = {}

    for mkt in ROLLOVER_MARKETS:
        m_cfg = markets_cfg.get(mkt)
        if m_cfg is None:
            m_cfg = {}
        elif not isinstance(m_cfg, dict):
            raise ValueError(f"_rollover_patch.json.markets[{mkt!r}] must be an object.")
        else:
            unknown_mkeys = set(m_cfg.keys()) - ALLOWED_ROLLOVER_MARKET_KEYS
            if unknown_mkeys:
                raise ValueError(
                    f"Unknown key(s) in _rollover_patch.json.markets[{mkt!r}]: {sorted(unknown_mkeys)} "
                    f"(allowed: {sorted(ALLOWED_ROLLOVER_MARKET_KEYS)})"
                )

        prev_md_path = _safe_repo_path(repo_root, "equity", f"{mkt}_market_report_{prev_slug}.md")
        new_md_path = _safe_repo_path(repo_root, "equity", f"{mkt}_market_report_{new_slug}.md")
        latest_md_path = _safe_repo_path(repo_root, "equity", f"{mkt}_market_report_latest.md")
        meta_path = _safe_repo_path(repo_root, "equity", f"report_meta_{mkt}.json")

        if not prev_md_path.is_file():
            raise ValueError(f"Missing previous flagship markdown: equity/{prev_md_path.name}")
        if new_md_path.exists():
            raise ValueError(
                f"Refusing to overwrite existing flagship markdown: equity/{new_md_path.name}"
            )
        orig_meta = _read_json_obj(meta_path, f"equity/{meta_path.name}")
        if orig_meta.get("period_slug") != prev_slug:
            raise ValueError(
                f"equity/{meta_path.name} period_slug ({orig_meta.get('period_slug')!r}) != prev_period_slug ({prev_slug!r})."
            )
        if not isinstance(orig_meta.get("chart_live"), dict):
            raise ValueError(f"equity/{meta_path.name} missing 'chart_live' object.")

        orig_md_text = prev_md_path.read_text(encoding="utf-8")
        orig_app2_rows = _extract_appendix2_raw_rows(orig_md_text)
        new_md_text = orig_md_text
        replacements_applied = 0

        hdr_reps = m_cfg.get("header_replacements")
        if hdr_reps is not None:
            if not isinstance(hdr_reps, list):
                raise ValueError(f"_rollover_patch.json.markets[{mkt!r}].header_replacements must be a list of [old, new] pairs.")
            for ri, pair in enumerate(hdr_reps):
                if (
                    not isinstance(pair, (list, tuple))
                    or len(pair) != 2
                    or not isinstance(pair[0], str)
                    or not pair[0]
                    or not isinstance(pair[1], str)
                ):
                    raise ValueError(
                        f"_rollover_patch.json.markets[{mkt!r}].header_replacements[{ri}] must be [non-empty old_str, new_str]."
                    )
                old_s, new_s = pair[0], pair[1]
                if LOCAL_PATH_RE.search(new_s):
                    raise ValueError(
                        f"_rollover_patch.json.markets[{mkt!r}].header_replacements[{ri}] introduces a local filesystem path."
                    )
                rep_leaks = BANNED_INTERNAL_RE.findall(new_s)
                if rep_leaks:
                    raise ValueError(
                        f"_rollover_patch.json.markets[{mkt!r}].header_replacements[{ri}] introduces banned internal term(s): {sorted(set(rep_leaks))}"
                    )
                if old_s not in new_md_text:
                    raise ValueError(
                        f"_rollover_patch.json.markets[{mkt!r}].header_replacements[{ri}] target not found in {prev_md_path.name}: {old_s[:60]!r}"
                    )
                new_md_text = new_md_text.replace(old_s, new_s)
                replacements_applied += 1

        if LOCAL_PATH_RE.search(new_md_text):
            raise ValueError(f"{new_md_path.name}: local filesystem path detected after rollover replacements.")
        new_leaks = set(BANNED_INTERNAL_RE.findall(new_md_text)) - set(BANNED_INTERNAL_RE.findall(orig_md_text))
        if new_leaks:
            raise ValueError(f"{new_md_path.name}: rollover introduced banned internal term(s): {sorted(new_leaks)}")

        if orig_app2_rows is not None:
            new_app2_rows = _extract_appendix2_raw_rows(new_md_text)
            if new_app2_rows != orig_app2_rows:
                raise ValueError(
                    f"{mkt}: header_replacements altered Appendix 2 stock rows "
                    f"(before={len(orig_app2_rows)}, after={len(new_app2_rows) if new_app2_rows else 0}); "
                    "all Appendix 2 stock rows must remain intact."
                )

        new_meta = copy.deepcopy(orig_meta)
        new_meta["period_slug"] = new_slug
        new_meta["chart_live"]["as_of_full"] = as_of_full
        new_meta["chart_live"]["as_of_year_float"] = as_of_year_float

        if top_benchmark_time is not None:
            new_meta["benchmark_time"] = top_benchmark_time
        for auto_k in ("page_footer", "version", "tag"):
            if isinstance(new_meta.get(auto_k), str):
                new_meta[auto_k] = _replace_period_in_text(new_meta[auto_k], prev_slug, new_slug)

        for ov_k in ("version", "page_footer", "benchmark_time", "title", "subtitle", "tag", "as_of_short"):
            if ov_k in m_cfg and m_cfg[ov_k] is not None:
                ov_val = m_cfg[ov_k]
                if not isinstance(ov_val, str) or not ov_val.strip():
                    raise ValueError(
                        f"_rollover_patch.json.markets[{mkt!r}].{ov_k} must be a non-empty string or null."
                    )
                ov_clean = ov_val.strip()
                if LOCAL_PATH_RE.search(ov_clean):
                    raise ValueError(
                        f"_rollover_patch.json.markets[{mkt!r}].{ov_k} leaks a local filesystem path."
                    )
                ov_leaks = BANNED_INTERNAL_RE.findall(ov_clean)
                if ov_leaks:
                    raise ValueError(
                        f"_rollover_patch.json.markets[{mkt!r}].{ov_k} leaks banned internal term(s): {sorted(set(ov_leaks))}"
                    )
                if ov_k == "as_of_short":
                    new_meta["chart_live"]["as_of_short"] = ov_clean
                else:
                    new_meta[ov_k] = ov_clean

        new_md_bytes = new_md_text.encode("utf-8")
        new_meta_bytes = _serialize_json(new_meta)
        writes.extend([
            (new_md_path, new_md_bytes),
            (latest_md_path, new_md_bytes),
            (meta_path, new_meta_bytes),
        ])
        market_summaries[mkt] = {
            "new_report": f"equity/{new_md_path.name}",
            "latest_mirror": f"equity/{latest_md_path.name}",
            "meta_file": f"equity/{meta_path.name}",
            "bytes": len(new_md_bytes),
            "replacements_applied": replacements_applied,
            "appendix2_rows": len(orig_app2_rows) if orig_app2_rows is not None else 0,
        }

    summary = {
        "mode": "rollover-equity-month",
        "dry_run": dry_run,
        "prev_period_slug": prev_slug,
        "new_period_slug": new_slug,
        "as_of_full": as_of_full,
        "as_of_year_float": as_of_year_float,
        "files_staged": len(writes),
        "markets": market_summaries,
        "patch_deleted": False,
    }

    if not dry_run:
        summary["patch_deleted"] = _commit_patch(repo_root, writes, patch_path, keep_patch=keep_patch)

    return summary


def _extract_ledger_header(text: str, file_label: str) -> str:
    """Extract ONLY the top '# ...' H1 heading plus contiguous intro '>' blockquote lines."""
    m_h1 = re.search(r"(?:^|\n)(# [^\n]*)(?:\n|$)", text)
    if m_h1 is None:
        raise ValueError(f"{file_label}: missing top '# ' heading; cannot safely archive.")
    pos = m_h1.end()
    tail = text[pos:]
    offset = 0
    for raw_ln in tail.splitlines(keepends=True):
        stripped = raw_ln.strip()
        if stripped == "" or stripped.startswith(">"):
            offset += len(raw_ln)
        else:
            break
    return text[m_h1.start() : pos + offset].lstrip("\n").rstrip("\n")


@_serialize_patch_operation
def archive_gold_ledgers(
    repo_root: Path = REPO_ROOT,
    *,
    dry_run: bool = False,
    keep_patch: bool = False,
) -> dict[str, Any]:
    patch_path = _safe_repo_path(repo_root, "gold", "daily", "_archive_patch.json")
    changelog_path = _safe_repo_path(repo_root, "gold", "daily", "CHANGELOG.md")
    audit_path = _safe_repo_path(repo_root, "gold", "daily", "AUDIT_LOG.md")

    patch = _read_json_obj(patch_path, "gold/daily/_archive_patch.json")
    unknown = set(patch.keys()) - ALLOWED_ARCHIVE_PATCH_KEYS
    if unknown:
        raise ValueError(
            f"Unknown key(s) in _archive_patch.json: {sorted(unknown)} "
            f"(allowed: {sorted(ALLOWED_ARCHIVE_PATCH_KEYS)})"
        )

    period = _validate_period_slug(patch.get("archive_period"), "archive_period")
    note = patch.get("note")
    if note is not None:
        if not isinstance(note, str):
            raise ValueError("_archive_patch.json.note must be a string or null.")
        if LOCAL_PATH_RE.search(note):
            raise ValueError("_archive_patch.json.note leaks a local filesystem path.")

    if not changelog_path.is_file():
        raise ValueError("Missing gold/daily/CHANGELOG.md.")
    if not audit_path.is_file():
        raise ValueError("Missing gold/daily/AUDIT_LOG.md.")

    archive_cl_path = _safe_repo_path(repo_root, "gold", "daily", "archive", f"CHANGELOG_{period}.md")
    archive_au_path = _safe_repo_path(repo_root, "gold", "daily", "archive", f"AUDIT_LOG_{period}.md")
    if archive_cl_path.exists():
        raise ValueError(
            f"Refusing to overwrite existing Gold archive: gold/daily/archive/{archive_cl_path.name}"
        )
    if archive_au_path.exists():
        raise ValueError(
            f"Refusing to overwrite existing Gold archive: gold/daily/archive/{archive_au_path.name}"
        )

    orig_cl_bytes = changelog_path.read_bytes()
    orig_au_bytes = audit_path.read_bytes()
    orig_cl_text = orig_cl_bytes.decode("utf-8")
    orig_au_text = orig_au_bytes.decode("utf-8")

    if not GOLD_CHANGELOG_MARKER_RE.search(orig_cl_text):
        raise ValueError("gold/daily/CHANGELOG.md has no GOLD_EDITION_CHANGELOG entries to archive.")
    if not GOLD_REVIEW_BLOCK_RE.search(orig_au_text):
        raise ValueError("gold/daily/AUDIT_LOG.md has no GOLD_EDITION_REVIEW entries to archive.")

    cl_header = _extract_ledger_header(orig_cl_text, "gold/daily/CHANGELOG.md")
    au_header = _extract_ledger_header(orig_au_text, "gold/daily/AUDIT_LOG.md")

    prior_cl_links = [
        ln.strip() for ln in orig_cl_text.splitlines()
        if ln.strip().startswith("历史月度归档：") and f"archive/CHANGELOG_{period}.md" not in ln
    ]
    prior_au_links = [
        ln.strip() for ln in orig_au_text.splitlines()
        if ln.strip().startswith("历史月度归档：") and f"archive/AUDIT_LOG_{period}.md" not in ln
    ]
    cl_archive_lines = [f"历史月度归档：[{period} 演化日志归档](archive/CHANGELOG_{period}.md)"] + prior_cl_links
    au_archive_lines = [f"历史月度归档：[{period} 审计账本归档](archive/AUDIT_LOG_{period}.md)"] + prior_au_links

    active_cl_text = f"{cl_header}\n\n---\n\n" + "\n".join(cl_archive_lines) + "\n"
    active_au_text = f"{au_header}\n\n---\n\n" + "\n".join(au_archive_lines) + "\n"
    active_cl_bytes = active_cl_text.encode("utf-8")
    active_au_bytes = active_au_text.encode("utf-8")

    orig_cl_lines = _nonblank_lines(orig_cl_bytes)
    combined_cl_lines = _nonblank_lines(orig_cl_bytes + b"\n" + active_cl_bytes)
    if not _preserves_order(orig_cl_lines, combined_cl_lines):
        raise ValueError(
            "Mathematical proof failed: archived + active gold/daily/CHANGELOG.md lost or reordered prior nonblank lines."
        )

    orig_au_lines = _nonblank_lines(orig_au_bytes)
    combined_au_lines = _nonblank_lines(orig_au_bytes + b"\n" + active_au_bytes)
    if not _preserves_order(orig_au_lines, combined_au_lines):
        raise ValueError(
            "Mathematical proof failed: archived + active gold/daily/AUDIT_LOG.md lost or reordered prior nonblank lines."
        )

    summary = {
        "mode": "archive-gold-ledgers",
        "dry_run": dry_run,
        "archive_period": period,
        "changelog_archive": f"gold/daily/archive/{archive_cl_path.name}",
        "audit_archive": f"gold/daily/archive/{archive_au_path.name}",
        "changelog_prior_lines": len(orig_cl_lines),
        "changelog_active_lines": len(_nonblank_lines(active_cl_bytes)),
        "audit_prior_lines": len(orig_au_lines),
        "audit_active_lines": len(_nonblank_lines(active_au_bytes)),
        "order_proof_verified": True,
        "patch_deleted": False,
    }

    if not dry_run:
        summary["patch_deleted"] = _commit_patch(repo_root, [
            (archive_cl_path, orig_cl_bytes),
            (archive_au_path, orig_au_bytes),
            (changelog_path, active_cl_bytes),
            (audit_path, active_au_bytes),
        ], patch_path, keep_patch=keep_patch)

    return summary


def inspect_state_dbs(repo_root: Path = REPO_ROOT, target: str = "") -> dict[str, Any]:
    with state_read_lock(repo_root):
        return _inspect_state_dbs(repo_root, target)


def _inspect_state_dbs(repo_root: Path, target: str) -> dict[str, Any]:
    raw_target = str(target or "").strip()
    if not raw_target:
        raise ValueError(
            "Empty --inspect target (allowed: channels, channel:<id>, etf:<code>, etf-freshness, stock:<key>, stale-dossiers, ah-benchmarks, policy-calendar, review-candidate)."
        )

    if raw_target == "review-candidate":
        candidate = review_evidence.working_snapshot(repo_root)
        candidate["previous_backfills"] = review_evidence.inspect_previous_backfills(repo_root, candidate["edition_id"])
        return candidate

    if raw_target == "channels":
        ma = _read_json_obj(_safe_repo_path(repo_root, "equity", "state", "multi_asset_channels.json"), "multi_asset_channels.json")
        channels = ma.get("channels") if isinstance(ma.get("channels"), list) else []
        return {
            "edition_id": ma.get("edition_id"),
            "as_of_date": ma.get("as_of_date"),
            "total_channels": len(channels),
            "channels": [
                {
                    "id": ch.get("id"),
                    "name": ch.get("name"),
                    "status_tone": ch.get("status_tone"),
                    "beginner_one_liner": ch.get("beginner_one_liner"),
                    "today_alert": ch.get("today_alert"),
                }
                for ch in channels
                if isinstance(ch, dict)
            ],
        }

    if raw_target.startswith("channel:"):
        cid = raw_target.split(":", 1)[1].strip()
        ma = _read_json_obj(_safe_repo_path(repo_root, "equity", "state", "multi_asset_channels.json"), "multi_asset_channels.json")
        channels = ma.get("channels") if isinstance(ma.get("channels"), list) else []
        for ch in channels:
            if isinstance(ch, dict) and ch.get("id") == cid:
                return ch
        raise ValueError(f"Channel not found: {cid!r} (allowed: {sorted(REQUIRED_CHANNEL_SET)})")

    if raw_target.startswith("etf:"):
        code_raw = raw_target.split(":", 1)[1].strip()
        norm_code = _normalize_etf_code(code_raw)
        eu = _read_json_obj(_safe_repo_path(repo_root, "equity", "state", "etf_universe.json"), "etf_universe.json")
        etfs = eu.get("etfs") if isinstance(eu.get("etfs"), list) else []
        for item in etfs:
            if isinstance(item, dict) and _normalize_etf_code(item.get("code")) == norm_code:
                return item
        raise ValueError(f"ETF not found: {code_raw!r} (normalized: {norm_code!r})")

    if raw_target == "etf-freshness":
        eu = _read_json_obj(_safe_repo_path(repo_root, "equity", "state", "etf_universe.json"), "etf_universe.json")
        etfs = eu.get("etfs") if isinstance(eu.get("etfs"), list) else []
        hist: Counter[str] = Counter()
        for item in etfs:
            if isinstance(item, dict):
                hist[str(item.get("updated_at") or "unset")] += 1
        valid_dates = sorted(d for d in hist if DATE_RE.fullmatch(d))
        latest_date = valid_dates[-1] if valid_dates else None
        recent_codes = sorted(
            str(item.get("code", "")).strip()
            for item in etfs
            if isinstance(item, dict) and latest_date is not None and item.get("updated_at") == latest_date
        )
        return {
            "edition_id": eu.get("edition_id"),
            "as_of_date": eu.get("as_of_date"),
            "total_etfs": len(etfs),
            "updated_at_histogram": dict(sorted(hist.items(), reverse=True)),
            "latest_updated_at": latest_date,
            "recently_updated_codes": recent_codes,
        }

    if raw_target.startswith("stock:"):
        stock_key = raw_target.split(":", 1)[1].strip()
        dd = _read_json_obj(_safe_repo_path(repo_root, "equity", "state", "deep_dossiers.json"), "deep_dossiers.json")
        dossiers = dd.get("dossiers") if isinstance(dd.get("dossiers"), dict) else {}
        if stock_key in dossiers and isinstance(dossiers[stock_key], dict):
            return dossiers[stock_key]
        raise ValueError(f"Stock dossier not found: {stock_key!r}")

    if raw_target == "stale-dossiers":
        dd = _read_json_obj(_safe_repo_path(repo_root, "equity", "state", "deep_dossiers.json"), "deep_dossiers.json")
        dossiers = dd.get("dossiers") if isinstance(dd.get("dossiers"), dict) else {}
        hist: Counter[str] = Counter()
        for entry in dossiers.values():
            if isinstance(entry, dict):
                hist[str(entry.get("updated_at") or "unknown")] += 1
        valid_dates = sorted(d for d in hist if DATE_RE.fullmatch(d))
        latest_date = valid_dates[-1] if valid_dates else None
        recent_keys = sorted(
            k for k, v in dossiers.items()
            if isinstance(v, dict) and latest_date is not None and v.get("updated_at") == latest_date
        )
        return {
            "edition_id": dd.get("edition_id"),
            "as_of_date": dd.get("as_of_date"),
            "total_stocks": len(dossiers),
            "updated_at_histogram": dict(sorted(hist.items(), reverse=True)),
            "latest_updated_at": latest_date,
            "recently_updated_keys": recent_keys,
        }

    if raw_target == "ah-benchmarks":
        ms = _read_json_obj(_safe_repo_path(repo_root, "equity", "state", "market_state.json"), "market_state.json")
        dd = _read_json_obj(_safe_repo_path(repo_root, "equity", "state", "deep_dossiers.json"), "deep_dossiers.json")
        dossiers = dd.get("dossiers") if isinstance(dd.get("dossiers"), dict) else {}
        radar = ms.get("cross_market_linkages", {}).get("ah_premium_radar", {})
        benchmarks = radar.get("benchmarks") if isinstance(radar, dict) and isinstance(radar.get("benchmarks"), list) else []
        rows: list[dict[str, Any]] = []
        for bench in benchmarks:
            if not isinstance(bench, dict):
                continue
            a_code = str(bench.get("a", "")).strip()
            h_code = str(bench.get("h", "")).strip()
            ak = f"a-share:{a_code}"
            hk = f"hk-stock:{h_code}"
            a_dos = dossiers.get(ak) if isinstance(dossiers.get(ak), dict) else None
            h_dos = dossiers.get(hk) if isinstance(dossiers.get(hk), dict) else None
            rows.append({
                "name": bench.get("name"),
                "a": a_code,
                "h": h_code,
                "ah_premium_pct": bench.get("ah_premium_pct"),
                "preferred_channel": bench.get("preferred_channel"),
                "a_dossier": {
                    "key": ak,
                    "updated_at": a_dos.get("updated_at") if a_dos else None,
                    "baseline_note": a_dos.get("baseline_note") if a_dos else None,
                },
                "h_dossier": {
                    "key": hk,
                    "updated_at": h_dos.get("updated_at") if h_dos else None,
                    "baseline_note": h_dos.get("baseline_note") if h_dos else None,
                },
            })
        return {
            "edition_id": ms.get("edition_id"),
            "as_of_date": radar.get("as_of_date") if isinstance(radar, dict) else None,
            "hsahp_index": radar.get("hsahp_index") if isinstance(radar, dict) else None,
            "total_benchmarks": len(rows),
            "benchmarks": rows,
        }

    if raw_target == "policy-calendar":
        pc = _read_json_obj(_safe_repo_path(repo_root, "equity", "state", "policy_calendar.json"), "policy_calendar.json")
        briefs = pc.get("policy_briefs") if isinstance(pc.get("policy_briefs"), list) else []
        events = pc.get("events") if isinstance(pc.get("events"), list) else []
        tier_counter: Counter[str] = Counter()
        region_counter: Counter[str] = Counter()
        end_dates: list[str] = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            tier = str(ev.get("impact_tier", "")).strip()
            reg = str(ev.get("region", "")).strip()
            if tier:
                tier_counter[tier] += 1
            if reg:
                region_counter[reg] += 1
            end_d = str(ev.get("end_date_cst") or ev.get("date_cst") or "").strip()
            if DATE_RE.fullmatch(end_d):
                end_dates.append(end_d)
        return {
            "schema_version": pc.get("schema_version"),
            "edition_id": pc.get("edition_id"),
            "as_of_cst": pc.get("as_of_cst"),
            "horizon_days": pc.get("horizon_days"),
            "horizon_end_cst": max(end_dates) if end_dates else None,
            "policy_briefs_count": len(briefs),
            "events_count": len(events),
            "total_briefs": len(briefs),
            "home_featured_briefs": sum(1 for b in briefs if isinstance(b, dict) and b.get("home_featured") is True),
            "total_events": len(events),
            "counts_by_tier": {k: tier_counter[k] for k in ("P0", "P1", "P2") if tier_counter.get(k, 0) > 0},
            "counts_by_region": dict(sorted(region_counter.items())),
            "patch_schema_hint": {
                "allowed_patch_keys": sorted(ALLOWED_POLICY_CALENDAR_PATCH_KEYS),
                "top_level_updates_allowed_keys": sorted(ALLOWED_POLICY_CALENDAR_TOP_KEYS),
                "valid_affected_markets": [
                    "a_share",
                    "hk_stock",
                    "us_stock",
                    "rates_bonds_core",
                    "gold",
                    "non_us_global_satellite",
                ],
                "valid_regions": sorted(POLICY_CAL_ALLOWED_REGIONS),
            },
            "policy_briefs": [
                {
                    "id": b.get("id"),
                    "date_cst": b.get("date_cst"),
                    "region": b.get("region"),
                    "impact_tier": b.get("impact_tier"),
                    "home_featured": bool(b.get("home_featured", False)),
                    "affected_markets": b.get("affected_markets"),
                    "headline": b.get("headline"),
                }
                for b in briefs
                if isinstance(b, dict)
            ],
            "events": [
                {
                    "event_id": ev.get("event_id"),
                    "date_cst": ev.get("date_cst"),
                    "end_date_cst": ev.get("end_date_cst"),
                    "date_precision": ev.get("date_precision"),
                    "time_cst": ev.get("time_cst"),
                    "region": ev.get("region"),
                    "category": ev.get("category"),
                    "impact_tier": ev.get("impact_tier"),
                    "title": ev.get("title"),
                    "affected_markets": ev.get("affected_markets"),
                }
                for ev in events
                if isinstance(ev, dict)
            ],
        }

    raise ValueError(
        f"Unknown --inspect target {raw_target!r} "
        "(allowed: channels, channel:<id>, etf:<code>, etf-freshness, stock:<key>, stale-dossiers, ah-benchmarks, policy-calendar, review-candidate)."
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Validate and atomically merge equity/state/_edition_patch.json into the 3 equity state databases and policy_calendar.json.",
    )
    mode.add_argument(
        "--prepend-gold-ledgers",
        action="store_true",
        help="Losslessly prepend gold/daily/_ledger_patch.json into CHANGELOG.md and AUDIT_LOG.md.",
    )
    mode.add_argument(
        "--append-gold-rsi",
        action="store_true",
        help="Validate and atomically append gold/daily/_rsi_patch.json to gold/daily/rsi_metrics.json.",
    )
    mode.add_argument(
        "--append-equity-rsi",
        action="store_true",
        help="Validate and atomically append equity/state/_rsi_patch.json to equity/state/rsi_metrics.json.",
    )
    mode.add_argument(
        "--prepend-equity-audit",
        action="store_true",
        help="Losslessly prepend equity/state/_audit_patch.json into equity/state/audit_ledger.md.",
    )
    mode.add_argument(
        "--rollover-equity-month",
        action="store_true",
        help="Atomically roll over the 3 equity flagship reports, _latest mirrors, and report_meta JSONs from equity/state/_rollover_patch.json.",
    )
    mode.add_argument(
        "--archive-gold-ledgers",
        action="store_true",
        help="Atomically archive gold/daily/CHANGELOG.md and AUDIT_LOG.md into gold/daily/archive/ from gold/daily/_archive_patch.json.",
    )
    mode.add_argument(
        "--inspect",
        metavar="TARGET",
        help="Read-only JSON summary: channels, channel:<id>, etf:<code>, etf-freshness, stock:<key>, stale-dossiers, ah-benchmarks, policy-calendar, review-candidate.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all validations and print summary without modifying target files or deleting the patch.",
    )
    parser.add_argument(
        "--keep-patch",
        action="store_true",
        help="Retain the temporary patch file after successful apply/prepend/append/rollover/archive.",
    )
    parser.add_argument(
        "--skip-edition-lock",
        action="store_true",
        help="Testing-only flag for --apply: skip matching edition_id against gold/data_snapshot.json and market_state.json.",
    )
    args = parser.parse_args(argv)
    if args.skip_edition_lock and not args.apply:
        parser.error("--skip-edition-lock can only be combined with --apply.")
    if args.inspect is not None and (args.dry_run or args.keep_patch):
        parser.error("--inspect is read-only and cannot be combined with --dry-run or --keep-patch.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.inspect is not None:
            result = inspect_state_dbs(REPO_ROOT, args.inspect)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.apply:
            summary = apply_equity_patch(
                REPO_ROOT,
                dry_run=args.dry_run,
                keep_patch=args.keep_patch,
                skip_edition_lock=args.skip_edition_lock,
            )
        elif args.prepend_gold_ledgers:
            summary = prepend_gold_ledgers(
                REPO_ROOT,
                dry_run=args.dry_run,
                keep_patch=args.keep_patch,
            )
        elif args.append_gold_rsi:
            summary = append_gold_rsi(
                REPO_ROOT,
                dry_run=args.dry_run,
                keep_patch=args.keep_patch,
            )
        elif args.append_equity_rsi:
            summary = append_equity_rsi(
                REPO_ROOT,
                dry_run=args.dry_run,
                keep_patch=args.keep_patch,
            )
        elif args.rollover_equity_month:
            summary = rollover_equity_month(
                REPO_ROOT,
                dry_run=args.dry_run,
                keep_patch=args.keep_patch,
            )
        elif args.archive_gold_ledgers:
            summary = archive_gold_ledgers(
                REPO_ROOT,
                dry_run=args.dry_run,
                keep_patch=args.keep_patch,
            )
        else:
            summary = prepend_equity_audit(
                REPO_ROOT,
                dry_run=args.dry_run,
                keep_patch=args.keep_patch,
            )
        prefix = "[DRY-RUN]" if args.dry_run else "[OK]"
        print(f"{prefix} {json.dumps(summary, ensure_ascii=False)}")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
