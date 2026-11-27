#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent Pre-Flight & Pure-Web Forensic Quality Linter for Global Equity Research
(A-Share × HK-Stock × US-Stock + 12 Multi-Asset Channels + 181+ ETF Universe + 231-Stock Deep Dossiers
+ Cross-Project Gold SSOT Consistency Gate).

Usage:
  python3 lint_equity.py --plan YYYY-MM-DD_HHMM[_rN]          # Compute required reports before refreshing snapshots
  python3 lint_equity.py --precheck --strict [file1.md ...]   # Fast Gates 0-5 + SVG Gold-Lock scan
  python3 lint_equity.py --strict [file1.md ...]              # Full Pure-Web Gates 0-5 + SVG + SSOT + Cross-Project
  python3 lint_equity.py --strict                             # Auto-check all 3 flagships + latest 3 dailies + workspace state
"""

from __future__ import annotations

from collections import Counter
import importlib.util
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from pathlib import Path
from urllib.parse import urlsplit

import edition_plan as _edition_plan_mod
from edition_plan import MARKETS, calendar_rules, edition_plan, parse_edition_id
from pdf_common import BASE_DIR, DAILY_DIR, _BANNED_INTERNAL_RE, _split_md_row, lint_markdown_report

GOLD_SNAPSHOT_PATH = BASE_DIR.parent / "gold" / "data_snapshot.json"
GOLD_CALENDAR_PATH = GOLD_SNAPSHOT_PATH.with_name("market_calendar.json")
STATE_PATH = BASE_DIR / "state" / "market_state.json"
MULTI_ASSET_PATH = BASE_DIR / "state" / "multi_asset_channels.json"
ETF_UNIVERSE_PATH = BASE_DIR / "state" / "etf_universe.json"
DEEP_DOSSIERS_PATH = BASE_DIR / "state" / "deep_dossiers.json"
POLICY_CALENDAR_PATH = BASE_DIR / "state" / "policy_calendar.json"
KLINES_MANIFEST_PATH = BASE_DIR / "state" / "klines" / "manifest.json"
BEIJING = timezone(timedelta(hours=8))
MAX_EDITION_EARLY = timedelta(minutes=5)
MAX_EDITION_LAG = timedelta(hours=6)
EDITION_CUTOVER = ("2026-11-25", 1800, 2)
ALL_MAIN_CUTOVER = getattr(_edition_plan_mod, "ALL_MAIN_CUTOVER", ("2026-11-26", 1800, 1))
EDITORIAL_DEPTH_CUTOVER = ("2026-11-27", 730, 1)
_REQUIRED_MULTI_ASSET_CHANNELS = (
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
_SYNTHETIC_LEGACY_MULTI_ASSET_CHANNELS = (
    "bonds",
    "funds_wm",
    "reverse_repo",
    "qdii_mrf",
    "large_cds",
    "convertible_bonds",
    "c_reits",
    "commodity_etfs",
)
_ETF_REQUIRED_STR_FIELDS = (
    "code",
    "name",
    "market",
    "channel",
    "fee_total_pct",
    "thesis_deep",
    "risk_boundary",
    "action_role",
)
_ETF_ALLOWED_MARKETS = frozenset({"a-share", "hk-stock", "us-stock", "global", "multi-asset"})
_ETF_ALLOWED_CHANNELS = frozenset({
    "境内场内", "境内场外", "离岸港交所", "境内非QDII港股通", "境内QDII", "离岸美股", "爱尔兰UCITS",
})
_ETF_ALLOWED_PREMIUM_STATUSES = frozenset({"normal", "watch", "high_risk"})
_ETF_ALLOWED_ASSET_CLASSES = frozenset({
    "equity",
    "fixed_income",
    "gold",
    "commodity",
    "cash_mmf",
    "convertible_bond",
    "reits",
})
_ETF_ALLOWED_REGIONS = frozenset({
    "cn",
    "hk",
    "us",
    "jp",
    "eu",
    "apac_em",
    "global",
})
_COCKPIT_ALLOWED_LAMPS = frozenset({"red", "yellow", "green"})
_POLICY_CAL_ALLOWED_REGIONS = frozenset({"CN", "HK", "US", "EU", "UK", "JP", "GLOBAL"})
POLICY_CAL_REGIONS = _POLICY_CAL_ALLOWED_REGIONS
_BARE_IMPACT_TIER_RE = re.compile(r"(?<![A-Za-z0-9])P[0-2](?![A-Za-z0-9])")
_POLICY_CAL_PROSE_SKIP_KEYS = frozenset({"impact_tier", "event_id", "brief_id", "id", "source_url"})
_BARE_TENOR_RE = re.compile(r"(?<![A-Za-z0-9_.$€£¥￥])(?:1M|9M|2Y|3Y|5Y|10Y)(?![A-Za-z0-9_])")
_POLICY_CAL_ALLOWED_CATEGORIES = frozenset({
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
_POLICY_CAL_ALLOWED_TIERS = frozenset({"P0", "P1", "P2"})
_POLICY_CAL_ALLOWED_PRECISIONS = frozenset({"exact", "window_tbd"})
_POLICY_CAL_ALLOWED_MARKETS = frozenset({
    "a_share",
    "hk_stock",
    "us_stock",
    "rates_bonds_core",
    "gold",
    "non_us_global_satellite",
})
_POLICY_CAL_MIN_HORIZON_DAYS = 14
_DATE_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HK_4DIGIT_RE = re.compile(r"(?<![0-9])\d{4}\.HK(?![A-Za-z0-9])")
_DOSSIER_DIMENSIONS = (
    "moat",
    "financials",
    "valuation_anchor",
    "shareholder_flow",
    "catalysts",
    "bear_case",
    "action_etf",
)
_DOSSIER_RAW_MARKUP_RE = re.compile(r"\*\*|<br\s*/?>|`", flags=re.IGNORECASE)
_CAVEAT_ALLOWED_CATEGORIES = frozenset({
    "holiday_thin", "provisional_close", "delayed_official", "source_conflict", "partial_data", "single_source", "publication_exception", "other",
})
_CAVEAT_ALLOWED_SEVERITIES = frozenset({"info", "warn", "critical"})
_CAVEAT_ALLOWED_MARKETS = frozenset({*MARKETS, "global", "multi_asset", "all"})
_RSI_ALLOWED_FINDING_STATUSES = frozenset({"resolved", "deferred_data", "disclosed_caveat"})
_DEPRECATED_BINARY_LINK_RE = re.compile(
    r"(?:\[[^\]]+\]\((?!https?://)[^)\s]+\.(?:pdf|docx)(?:#[^)\s]*)?\)"
    r"|/releases/download/"
    r"|\{md,pdf,docx\}"
    r"|(?:daily/|archive/|\.\.?/)[^\s`\"'()<>]+\.(?:pdf|docx))",
    flags=re.IGNORECASE,
)
_MA_RESTRICTED_CODES_RE = re.compile(r"(?<![0-9])(?:968118|968001|00011)(?![0-9])")
RESTRICTED_CODES_RE = _MA_RESTRICTED_CODES_RE
RESTRICTED_WARN_RE = re.compile(
    r"(?:暂停|停申|停购|封盘|已停|停售|限购|退市|私有化|勿买|勿选|勿误配|"
    r"严禁|禁止|严避|禁买|禁推|禁配|禁碰|切忌|避坑|避开|绕开|远离|回避|"
    r"不可|不买|不推|莫买|别买|别碰|慎碰|高危|雷区|警示|清盘|剔除|弃用|改以|替代)"
)
_MA_RESTRICTED_WARN_RE = RESTRICTED_WARN_RE
_LOCAL_PATH_RE = re.compile(r"(?:file:///|/Users/|/home/|[A-Za-z]:\\Users\\|/opt/homebrew/)")
EQUITY_RETRACTED_FACT_GUARDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Blue Owl 误写为新增 5% 赎回", re.compile(r"Blue\s*Owl[^。\n]{0,20}新增\s*5%\s*赎回", re.IGNORECASE)),
    ("工银黄金联接 008143 误写为 7 天免赎回", re.compile(r"008143[^。\n]{0,25}7\s*天免赎回")),
    ("海波转债 123080 误写为 12/02 到期", re.compile(r"123080[^。\n]{0,25}12/02\s*到期")),
)
_EQUITY_RETRACTED_NEG_RE = re.compile(
    r"(?:已区隔|更正|修正|原稿|驳回|不含|未停牌|非硬停|仅第三方折价要约|误标|误写|并非|不是|辟谣|严禁|纠偏)"
)
_SHFE_0230_RE = re.compile(r"(?<!\d)02:30(?!\d)")
_SHFE_NON_GOLD_METAL_RE = re.compile(
    r"(?:沪铜|沪铝|沪锌|沪镍|沪锡|沪铅|氧化铝|螺纹钢|热卷|不锈钢|纯碱|(?<![A-Za-z])(?:cu|al|zn|ni|rb)\d{4}(?!\d))",
    re.IGNORECASE,
)
_SHFE_EARLY_CLOSE_QUAL_RE = re.compile(r"(?<!\d)(?:01:00|23:00)(?!\d)")
_SCENARIO_LINE_TRIGGER_RE = re.compile(r"(?:情景|合计\s*10\s*点|(?<![0-9./])(?:[0-9]|10)\s*/\s*10(?![0-9]))")
_SCENARIO_WEIGHT_RE = re.compile(
    r"(?:占\s*(\d+)\s*点|[（(]\s*(?:占\s*)?([0-9]|10)\s*/\s*10(?:\s*点)?\s*[)）]|(?<![0-9./])(?:占|权重|概率)\s*([0-9]|10)\s*/\s*10(?![0-9]))"
)
_SCENARIO_DELTA_RE = re.compile(r"(?:原占|由.{0,6}调至|较上期)")
_MULTILINE_SCENARIO_WEIGHT_RE = re.compile(
    r"(?:占\s*(\d+)\s*点|[（(]\s*(?:占\s*)?([0-9]|10)\s*/\s*10(?:\s*点)?\s*[)）])"
)
_SCENARIO_CONTEXT_RE = re.compile(
    r"(?:情景|场景|路径|推演|概率|权重|合计\s*10\s*点|10\s*点(?:分配|拆分|分布|概率))"
)
_SCENARIO_SINGLE_RATIO_RE = re.compile(r"(?<![0-9./])([0-9]|10)\s*/\s*10(?![0-9])")
_LAZY_ZERO_SCORE_RE = re.compile(r"其余(?:均|均为|全|皆)\s*[0零]")
_AUDIT_JARGON_LEAD_RE = re.compile(r"(?:旧缺口|核销成绩单|台账补核|清零旧账)")
_COUNTDOWN_YEAR_END_RE = re.compile(
    r"距\s*(20\d{2})\s*(?:[-年/]\s*12\s*[-月/]\s*31\s*[日]?|年底)\D{0,10}剩\s*(\d+)\s*天"
)
_COUNTDOWN_2026_RE = _COUNTDOWN_YEAR_END_RE
_BARE_IOPV_RE = re.compile(r"(?<![A-Za-z0-9_])IOPV(?![A-Za-z0-9_])", re.IGNORECASE)
_IOPV_GLOSS_RE = re.compile(r"(?:参考净值|实时净值|盘中净值)")
_CREDIT_SPREAD_CCC_RE = re.compile(r"(?:垃圾债利差\s*1,\d{3}|高收益与垃圾债)")
_CCC_QUAL_RE = re.compile(r"CCC", re.IGNORECASE)
_FEE_EXCLUDE_SPAN_RE = re.compile(
    r"(?:申购费?|赎回费?|1折|一折|佣金|销服(?:优惠至|费)?|销售服务费)"
    r"[^\s｜|，,；;）)。”\"·]{0,12}?"
    r"\d+(?:\.\d+)?%(?:\s*[–\-~至]\s*\d+(?:\.\d+)?%)?"
)
_RESTORE_SUB_REDEEM_RE = re.compile(r"恢复申赎")
_RESTORE_SAFE_QUAL_RE = re.compile(r"(?:仅恢复赎回|只恢复赎回|未恢复申赎|并非恢复申赎|不恢复申购)")
_DOSSIER_AH_RE = re.compile(
    r"(?:(?:AH|A/H)\s*(?:(?:罕见|深度|仍呈)?(?:溢价|倒挂|折价))|A\s*折\s*H\s*(?:倒挂)?)"
    r"[^0-9+\-，。；（）]{0,12}([+\-]?\d+(?:\.\d+)?)%(?:\s*[–\-~～至]\s*([+\-]?\d+(?:\.\d+)?)%)?"
)
_DOSSIER_AH_NEG_WORD_RE = re.compile(r"(?:倒挂|A\s*折\s*H|折价)")
_DOSSIER_AH_HIST_CTX_RE = re.compile(r"(?:历史中枢|历史均值|过去)")
_DOSSIER_DIV_STRICT_RE = re.compile(
    r"股息率\s*(?:约|近|逾|高达|达|为|仅|稳定在|~)?\s*(\d+(?:\.\d+)?)%(?:\s*[–\-~～至]\s*(\d+(?:\.\d+)?)%)?"
)
_DOSSIER_DIV_QUAL_RE = re.compile(
    r"(?:税后|扣税|港股通|中期|半年|特别|历史|原|旧|(?<![当目])前|目标|门槛|行业|均值|中证红利|同业|对比|较|H\s*股|离岸|扣\s*20%|净股息|贵于|低于|高于)"
)
_ETF_CODE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(?:\d{6}|\d{5}(?:\.HK)?|[A-Z]{2,5}(?:\.L)?)(?![A-Za-z0-9])")
_PCT_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)%")
_ETF_PREM_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)\s*(?:收|日终|收盘|涨|跌|净值|溢价|折价|复牌|停牌)"
)
_ETF_YOP_LEAD_DATE_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})(?!\d)")
_EXACT_PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
_RANGE_PCT_RE = re.compile(r"\d+(?:\.\d+)?%\s*[–\-~至]\s*\d+(?:\.\d+)?%")
_GOLD_ETF_CODES = frozenset({
    "518660", "518880", "518850", "159934", "159937", "518800",
    "517520", "159562", "02840", "03081",
    "GLD", "IAU", "IAUM", "GLDM", "IGLN", "GDX", "GDXJ",
})
_GOLD_ETF_NAME_RE = re.compile(
    r"(?<!非)(?:黄金|金矿|实物金|沪金|金股|SPDR\s*金(?!融)|SPDR\s*Gold|iShares\s*Gold|Physical\s*Gold|Gold\s*Miners)",
    flags=re.IGNORECASE,
)
_GOLD_ETF_FORBIDDEN_ROLE_RE = re.compile(r"(?:底座|买入|推荐|定投|配置|建仓|吸纳|加仓)")
_GOLD_DOSSIER_KEYS = frozenset({
    "a-share:601899", "a-share:600547", "a-share:600489", "a-share:600988", "a-share:000975",
    "hk-stock:02899.HK", "hk-stock:06181.HK", "hk-stock:01929.HK", "hk-stock:01818.HK",
    "hk-stock:01787.HK", "hk-stock:02099.HK",
    "us-stock:NEM", "us-stock:B", "us-stock:AEM", "us-stock:WPM", "us-stock:FNV",
})
_GOLD_BASE_ROLE_RE = re.compile(r"(?:当下底座|绿色底座|🟢)")
_GOLD_BASE_NEGATION_RE = re.compile(
    r"(?:严禁|禁止|切忌|不可|不得|暂不|不|非|不是|勿)(?:列为|标为|作为|当成|视为)?[\s“‘「\x22*_]*$"
)
_PERIOD_RE = re.compile(r"\d{4}_(?:0[1-9]|1[0-2])")
_DAILY_NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{4})_(a_share|hk_stock|us_stock)(?:_r([2-9]|[1-9]\d+))?\.md")
_REPORT_CUTOFF_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?:\s|$)")
_FLAGSHIP_CUTOFF_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{4}年\d{1,2}月\d{1,2}日) +(\d{2}:\d{2})(?!\d)")

_CHART_PLACEHOLDER_RE = re.compile(r"<!--\s*CHART_[AHU]\d+\s*-->")
_GOLD_ACTIVE_BUY_RE = re.compile(
    r"(?:补齐|补足|买入|买进|加仓|加配|抄底|逢低买|低吸|布局|上车|新买|买|定投|配置|建仓|吸纳)"
    r"\s*(?:[0-9一二两三半成%–\-~约近超]*\s*)?"
    r"(?:(?:现货|实物|纸|积存)?(?:黄金|金仓|金矿股?|黄金股)|"
    r"(?:518660|518880|518850|159934|159937|518800|517520|159562|02840|03081|"
    r"(?<![A-Za-z])(?:GLD|IAU|IAUM|GLDM|IGLN|GDX|GDXJ)(?![A-Za-z])))",
    flags=re.IGNORECASE,
)
_GOLD_DEFER_GUARD_RE = re.compile(
    r"(?:暂不|严禁|禁止|切忌|勿|停止|暂停|先别|不能|不宜|不要|别急着|拒绝|不考虑|不允许|不应|不会|未在黄金红灯停期|不)"
    r"(?:追高芯片[与或])?(?:现在|今天|今日|当下|任何|立即|马上|急于|立刻|再|去|主动|新|分批|小批|继续|同步|直接|冲动|抢跑)*"
    r"(?:(?:新买|买入|加仓|抄底|定投|配置|建仓|补齐|低吸|布局|上车)[/／、与或])?[\s“‘「\x22*_]*$"
    r"|(?:等到?|待).{0,14}(?:黄灯|绿灯|解锁)(?:亮起|确认)?(?:后)?(?:再|才)?(?:分批|择机|恢复|重启|再)*[\s“‘「\x22]*$"
    r"|(?:黄灯|绿灯|解锁|过四关|全部过关)(?:亮起|确认)?后(?:再|才)?(?:分批|择机|恢复|重启|再)*[\s“‘「\x22]*$"
    r"|(?:原稿曾建议|原稿曾考虑|过去曾建议|曾建议)[\s“‘「\x22]*$"
)
_GOLD_MINER_TICKERS_RE = re.compile(
    r"(?:NEM|纽蒙特|山东黄金|中金黄金|赤峰黄金|山金国际|紫金黄金|紫金矿业|招金|老铺黄金|周大福|"
    r"GLD|GLDM|IAU|IAUM|IGLN|GDX|GDXJ|518660|518880|518850|518800|517520|159934|159937|159562|02840|03081|02899|06181|01929)",
    flags=re.IGNORECASE,
)
_CRYPTO_ACTIVE_BUY_RE = re.compile(
    r"(?:补齐|补足|买入|买进|加仓|加配|抄底|逢低买|低吸|布局|上车|新买|买|定投|配置|配仓|建仓|吸纳|购入|做多)"
    r"\s*(?:[0-9一二两三半成%–\-~约近超少量小批分批]*\s*)?"
    r"(?:(?:现货|数字|虚拟|加密)?(?:比特币|以太坊|虚拟货币|加密货币|加密资产|稳定币)|"
    r"(?<![A-Za-z0-9])(?:BTC|ETH|USDT|USDC|IBIT|FBTC)(?![A-Za-z0-9]))"
    r"|\b(?:buy|add|accumulate|allocate(?:\s+to)?|dca\s+into)\s+(?:btc|bitcoin|eth|ethereum|crypto(?:currency)?)\b",
    flags=re.IGNORECASE,
)
_CRYPTO_NEGATION_GUARD_RE = re.compile(
    r"(?:严禁|禁止|切忌|勿|不得|不可|不能|不宜|不要|绝不|决不|暂不|停止|拒绝|不允许|不应|不会|0%\s*(?:严禁|禁止)?|零配|不)"
    r"(?:现在|今天|今日|当下|任何|立即|马上|急于|立刻|再|去|主动|新|分批|小批|继续|参与|涉及|尝试|建议|允许|新增|直接|盲目|变相)*"
    r"(?:(?:新买|买入|买进|加仓|抄底|定投|配置|配仓|建仓|低吸|布局|上车|交易|炒作|买卖|持有)[/／、与及和或])?[\s“‘「\x22*_]*$"
    r"|(?:严禁|禁止|不得|切忌|不可|绝不)(?:[^。！？；，,|但可应须宜]{0,14})(?:与|及|和|或|、|/|／)[\s“‘「\x22*_]*$"
    r"|\b(?:do\s+not|never|must\s+not|should\s+not|prohibit(?:ed|s)?|ban(?:ned|s)?)\s+(?:from\s+)?(?:buy|add|accumulat|allocat|dca|trad)[\w\s]{0,16}$",
    flags=re.IGNORECASE,
)
_TEN_DOT_RE = re.compile(r"[●○]{10}")
_PLAYBOOK_RETRACTED_RULES = (
    (
        "159545/159792 零溢价已撤回旧口径",
        re.compile(
            r"(?:(?:159545|159792)[^；;。\n]{0,24}[零无]溢价|[零无]溢价[^；;。\n]{0,24}(?:159545|159792))"
        ),
    ),
    (
        "红筹股一刀切 28% 税已撤回旧口径",
        re.compile(
            r"(?:港股通红筹[^；;。\n]{0,28}(?:税\s*28%|28%\s*税)|"
            r"红筹[^；;。\n]{0,16}(?:统一|一律|均为|均扣|税)\s*28%|"
            r"红筹\s*28%\s*税|"
            r"01378[^；;。\n]{0,16}28%)"
        ),
    ),
    (
        "可转债末日二级卖出免 20% 个人税已撤回旧口径",
        re.compile(r"(?:末日)?二级(?:市场)?卖出\s*免\s*20%\s*(?:个人)?税"),
    ),
)
_PLAYBOOK_NEGATION_PREFIX_RE = re.compile(
    r"(?:(?:严禁|禁止|不得|不可(?:直接)?|切忌|勿|不要|切勿|已撤回|已纠偏|误写为?|误称为?)"
    r"[：:\s“‘「\x22`*]*(?:笼统)?(?:写|称|标|提|用|说|将|统称)?[\s“‘「\x22`*_]*$"
    r"|(?:并非|不是|不等同于?)[：:\s“‘「\x22`*_]*$)"
)
_PLAYBOOK_NEGATION_INSIDE_RE = re.compile(r"(?:并非|不是|不等同|非一律|不免|非\s*28%)")


def _check_playbook_retracted_claims(pb_text: str) -> list[str]:
    """Ensure state/RSI_PLAYBOOK.md does not carry over the 3 retracted tax/ETF claims."""
    errs: list[str] = []
    for line_no, ln in enumerate(pb_text.splitlines(), 1):
        for label, pat in _PLAYBOOK_RETRACTED_RULES:
            for m in pat.finditer(ln):
                prefix = re.split(r"[。！？；;,，]", ln[:m.start()])[-1]
                if _PLAYBOOK_NEGATION_PREFIX_RE.search(prefix) or _PLAYBOOK_NEGATION_INSIDE_RE.search(m.group(0)):
                    continue
                errs.append(f"Gate 4 失败：state/RSI_PLAYBOOK.md (L{line_no}) 残留{label} -> {m.group(0)}")
                break
    return errs


def parse_daily_sort_key(p: Path) -> tuple[str, int, int, str]:
    """Deterministic sort key (YYYY-MM-DD, HHMM, rev_int, name) — immune to file mtime drift."""
    match = _DAILY_NAME_RE.fullmatch(p.name)
    if match:
        try:
            datetime.strptime(f"{match[1]}_{match[2]}", "%Y-%m-%d_%H%M")
        except ValueError:
            pass
        else:
            return match[1], int(match[2]), int(match[4] or 1), p.name
    return "0000-00-00", 0, 0, p.name


def check_daily_contract(
    path: Path,
    meta: dict | None,
    md_text: str,
    *,
    as_of_cst: datetime | None = None,
    warnings: list[str] | None = None,
) -> list[str]:
    """Check publication metadata while allowing immutable reports predating the contract."""
    sort_key = parse_daily_sort_key(path)[:3]
    if sort_key[0] == "0000-00-00":
        return [f"{path.name}: 日报文件名包含无效市场、日期、时刻或修订号"]
    requires_edition = sort_key >= EDITION_CUTOVER
    if meta is None:
        return [f"{path.name}: 当前体例须有文末 DAILY_META_JSON"] if requires_edition else []
    errors: list[str] = []
    edition = meta.get("edition_id")
    if (requires_edition or edition is not None) and parse_edition_id(edition) != sort_key:
        errors.append(f"{path.name}: edition_id 必须与文件名的日期、班次和修订号一致")
    if (requires_edition or "edition_type" in meta) and meta.get("edition_type") not in ("main", "light", "holiday_watch"):
        errors.append(f"{path.name}: edition_type 必须为 main、light 或 holiday_watch")
    chart = meta.get("chart_live")
    if isinstance(chart, dict) and "hkma_agg_bal_hkd_b" in chart and (requires_edition or "hkma_agg_bal_hkd_100m" in chart):
        errors.append(f"{path.name}: 金管局总结余须使用唯一的 hkma_agg_bal_hkd_100m（亿港元）")
    if requires_edition:
        cover_fields = ("tag", "title", "benchmark_time", "methodology", "page_footer", "footer_note")
        if any(not isinstance(meta.get(k), str) or not meta[k].strip() for k in cover_fields):
            errors.append(f"{path.name}: 当前体例缺少必填封面字段")
        if not isinstance(meta.get("kpis"), list) or len(meta["kpis"]) != 4:
            errors.append(f"{path.name}: 当前体例须提供四张 KPI 卡片")
        if not isinstance(chart, dict) or not chart:
            errors.append(f"{path.name}: 当前体例须有自身 chart_live 元数据")
        else:
            market_prefix = {"a_share": "A", "hk_stock": "H", "us_stock": "U"}[_detect_market(path)]
            chart_keys = re.findall(r"<!--\s*CHART_([AHU]\d+)\s*-->", md_text)
            for key in chart_keys:
                if key not in {f"{market_prefix}{n}" for n in range(1, 8)}:
                    errors.append(f"{path.name}: 图 {key} 不属于该市场")
                elif key not in ("A1", "A5") and not (isinstance(chart.get(key.lower()), dict) and chart[key.lower()]):
                    errors.append(f"{path.name}: 图 {key} 缺少本期 chart_live.{key.lower()} 数据")
                elif key == "H6" and sort_key > EDITION_CUTOVER:
                    h6 = chart["h6"]
                    items = h6.get("items")
                    if not isinstance(items, list) or not items or any(
                        not isinstance(row, list) or len(row) != 3
                        or not isinstance(row[0], str) or not row[0].strip()
                        or type(row[1]) not in (int, float) or not -sys.float_info.max <= row[1] <= sys.float_info.max
                        or not isinstance(row[2], str) or not row[2].strip()
                        for row in items
                    ):
                        errors.append(f"{path.name}: 图 H6 的 chart_live.h6.items 须提供本期非空的 [名称, 有限百分比, 说明] 行")
                    sector_strip = h6.get("sector_strip")
                    if not isinstance(sector_strip, str) or not sector_strip.strip():
                        errors.append(f"{path.name}: 图 H6 的 chart_live.h6.sector_strip 须提供本期板块说明")
            if warnings is not None and sort_key >= ALL_MAIN_CUTOVER and len(md_text) > 1000:
                ed_type = str(meta.get("edition_type", "")).strip().lower()
                unique_charts = len(set(chart_keys))
                if ed_type == "main" and unique_charts < 2:
                    warnings.append(
                        f"{path.name}: 融合后常规主刊建议内嵌至少 2 张矢量图（当前仅检测到 {unique_charts} 张）"
                    )
                elif ed_type == "holiday_watch" and unique_charts < 1:
                    warnings.append(
                        f"{path.name}: 升级版休市守望简报建议内嵌至少 1 张矢量图（当前检测到 0 张）"
                    )
            raw = chart.get("as_of_full")
            cutoff = _REPORT_CUTOFF_RE.match(raw) if isinstance(raw, str) else None
            try:
                local_cutoff = datetime.strptime(cutoff[1], "%Y-%m-%d %H:%M").replace(tzinfo=BEIJING) if cutoff else None
                edition_time = datetime.strptime(f"{sort_key[0]}_{sort_key[1]:04}", "%Y-%m-%d_%H%M").replace(tzinfo=BEIJING)
                if local_cutoff is None or not (-MAX_EDITION_EARLY <= local_cutoff - edition_time <= MAX_EDITION_LAG):
                    raise ValueError
                if as_of_cst is not None and local_cutoff.replace(second=0, microsecond=0) != as_of_cst.replace(second=0, microsecond=0):
                    errors.append(f"{path.name}: 图表数据截点与市场状态时间戳不一致")
            except ValueError:
                errors.append(f"{path.name}: chart_live.as_of_full 须在班次前 5 分钟至班次后 6 小时内的有效北京时间")
            if sort_key[:2] >= EDITORIAL_DEPTH_CUTOVER[:2] and "as_of_year_float" in chart and chart["as_of_year_float"] is not None:
                yf_val = chart["as_of_year_float"]
                try:
                    ed_d = date.fromisoformat(sort_key[0])
                    days_in_year = 366 if ((ed_d.year % 4 == 0 and ed_d.year % 100 != 0) or ed_d.year % 400 == 0) else 365
                    expected_yf = ed_d.year + (ed_d.timetuple().tm_yday - 0.5) / days_in_year
                    if type(yf_val) not in (int, float) or not isfinite(yf_val) or abs(float(yf_val) - expected_yf) > 0.004:
                        errors.append(
                            f"{path.name}: Gate G6 chart_live.as_of_year_float ({yf_val}) "
                            f"与日期 {sort_key[0]} 理论值 {expected_yf:.4f} 偏离 > 0.004"
                        )
                except ValueError:
                    pass
    return errors


def _extract_meta(md_text: str, path: Path) -> tuple[dict | None, str | None]:
    m = re.search(r"<!--\s*DAILY_META_JSON\s*(\{.*?\})\s*-->", md_text, flags=re.DOTALL)
    if not m:
        return None, None
    try:
        return json.loads(m.group(1)), None
    except json.JSONDecodeError as exc:
        return None, f"DAILY_META_JSON 语法错误: {exc}"


def _detect_is_flagship(p: Path) -> bool:
    return p.parent.resolve() == BASE_DIR.resolve() and "_market_report_" in p.name


def _detect_market(p: Path) -> str:
    n = p.name.lower()
    if "hk_stock" in n:
        return "hk_stock"
    if "us_stock" in n:
        return "us_stock"
    return "a_share"


def _extract_appendix2_stock_rows(md_text: str) -> list[list[str]] | None:
    """Return parsed cell lists for every stock row in the flagship Appendix 2 full stock pool table."""
    m = re.search(r"(?:^|\n)#{1,3}\s*附[录表]二[^\n]*\n(.*?)(?=\n#{1,2}\s*(?:附[录表]三|免责声明)|$)", md_text, flags=re.DOTALL)
    if not m:
        return None
    sec = m.group(1)
    tables: list[list[str]] = []
    cur: list[str] = []
    for ln in sec.splitlines():
        st = ln.strip()
        if st.startswith("|") and st.endswith("|"):
            cur.append(st)
        else:
            if cur:
                tables.append(cur)
                cur = []
    if cur:
        tables.append(cur)
    best_rows: list[list[str]] = []
    for tbl in tables:
        data_rows: list[list[str]] = []
        for r in tbl[1:]:
            cells = _split_md_row(r)
            if not all(re.match(r"^:?-{2,}:?$", c.strip()) for c in cells):
                data_rows.append(cells)
        if len(data_rows) > len(best_rows):
            best_rows = data_rows
    return best_rows if best_rows else None


def _count_appendix2_stock_rows(md_text: str) -> int | None:
    """Count stock rows in the flagship Appendix 2 (附表二 / 附录二) full stock pool table."""
    rows = _extract_appendix2_stock_rows(md_text)
    return len(rows) if rows else None


def _extract_appendix2_stock_keys(md_text: str, market: str) -> set[str] | None:
    """Extract canonical deep_dossiers keys (a-share:XXXXXX / hk-stock:XXXXX.HK / us-stock:TICKER) from Appendix 2."""
    rows = _extract_appendix2_stock_rows(md_text)
    if not rows:
        return None
    keys: set[str] = set()
    for cells in rows:
        c1 = cells[1] if len(cells) > 1 else cells[0]
        joined = " ".join(cells[:2])
        if market == "a_share":
            mc = re.search(r"`(\d{6})`", joined) or re.search(r"(?<![0-9])(\d{6})(?![0-9])", joined)
            if mc:
                keys.add(f"a-share:{mc.group(1)}")
        elif market == "hk_stock":
            mc = re.search(r"`(\d{4,5})(?:\.HK)?`", joined, re.I) or re.search(
                r"(?<![0-9])(\d{4,5})(?:\.HK)?(?![0-9])", joined, re.I
            )
            if mc:
                keys.add(f"hk-stock:{mc.group(1).zfill(5)}.HK")
        else:
            mc = (
                re.search(r"`([A-Z][A-Z0-9.\-]{0,6})`", c1)
                or re.search(r"[（(]([A-Z][A-Z0-9.\-]{0,6})[)）]", c1)
                or re.search(r"\b([A-Z]{1,5}(?:\.[AB])?)\b", c1)
            )
            if mc:
                keys.add(f"us-stock:{mc.group(1)}")
    return keys if keys else None


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


def _check_gate_3b(md_text: str, path: Path, *, is_flagship: bool, meta: dict | None, market: str, state: dict | None) -> tuple[list[str], list[str]]:
    """Gate 3B: verdict length, cover title length, 10-dot probability sum, Appendix 2 count & delisted guard."""
    errs: list[str] = []
    warns: list[str] = []
    body = re.sub(r"<!--\s*DAILY_META_JSON\s*\{.*?\}\s*-->", "", md_text, flags=re.DOTALL)

    # 1. Cover title length check
    if meta and meta.get("title"):
        t_clean = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", str(meta["title"])).strip()
        cap = 38 if is_flagship else 32
        if len(t_clean) > cap:
            warns.append(f"{path.name}: Gate 3B 封面主标题偏长 ({len(t_clean)} 字 > {cap} 字)")

    # 2. Opening verdict length check (一句话 / 3 分钟速读结论 / 30 秒结论)
    verdict_re = re.compile(r"(?:一句话[^：:]*|3\s*分钟速读结论[^：:]*|30\s*秒[^：:]*)[：:]\s*(.+)$")
    for ln in body.splitlines():
        st = ln.strip()
        if st.startswith(">"):
            m_v = verdict_re.search(st)
            if m_v:
                v_plain = re.sub(r"[*`]", "", m_v.group(1)).strip()
                if len(v_plain) > 60:
                    warns.append(f"{path.name}: Gate 3B 开篇总判断偏长 ({len(v_plain)} 字，建议 ≤50 字 / 硬上限 60 字)")
                break

    # 3. Gigerenzer 10-dot probability bar sum check per table
    cur_table: list[str] = []
    tables: list[list[str]] = []
    for ln in body.splitlines():
        st = ln.strip()
        if st.startswith("|") and st.endswith("|"):
            cur_table.append(st)
        elif cur_table:
            tables.append(cur_table)
            cur_table = []
    if cur_table:
        tables.append(cur_table)
    for tbl in tables:
        dot_rows = []
        for r in tbl:
            bars = _TEN_DOT_RE.findall(r)
            if bars:
                dot_rows.append(bars[0].count("●"))
        if len(dot_rows) >= 3 and sum(dot_rows) != 10:
            errs.append(f"{path.name}: Gate 3B 情景表 10 点概率条合计={sum(dot_rows)} ≠ 10 ({dot_rows})")

    # 4. Flagship Appendix 2 row count vs stock_pool_count + HK delisted 00011 guard
    if is_flagship:
        app_rows = _count_appendix2_stock_rows(body)
        meta_cnt = None
        if meta and isinstance(meta.get("chart_live"), dict) and meta["chart_live"].get("stock_pool_count") is not None:
            meta_cnt = int(meta["chart_live"]["stock_pool_count"])
        state_cnt = None
        if state and isinstance(state.get("markets", {}).get(market), dict):
            sc = state["markets"][market].get("stock_pool_count")
            if sc is not None:
                state_cnt = int(sc)
        if app_rows is None:
            errs.append(f"{path.name}: Gate 3B 未检测到附表二个股总表")
        elif meta_cnt is not None and app_rows != meta_cnt:
            errs.append(f"{path.name}: Gate 3B 附表二实表行数 ({app_rows}) ≠ report_meta.stock_pool_count ({meta_cnt})")
        if meta_cnt is not None and state_cnt is not None and meta_cnt != state_cnt:
            errs.append(f"{path.name}: Gate 3B report_meta.stock_pool_count ({meta_cnt}) ≠ market_state ({state_cnt})")

    # 5. Guard against listing delisted Hang Seng Bank 00011 as an active pool/focus row (both flagship & daily)
    if market == "hk_stock":
        for ln in body.splitlines():
            if ln.strip().startswith("|") and ("00011" in ln or "恒生银行" in ln) and "退市" not in ln and "私有化" not in ln:
                errs.append(f"{path.name}: Gate 3B 港股严禁将已于 2026-01-27 退市的恒生银行 00011 列为活跃标的 -> {ln[:50]}")
                break

    # 6. CHART_A2 futures sign-inversion guard (ann > 0 => discount/折价, ann < 0 => premium/升水)
    if market == "a_share" and isinstance(meta, dict):
        cl = meta.get("chart_live")
        if isinstance(cl, dict):
            a2_obj = cl.get("a2") if isinstance(cl.get("a2"), dict) else {}
            futs = a2_obj.get("futures") or cl.get("futures")
            if isinstance(futs, list):
                for item in futs:
                    if not isinstance(item, (list, tuple)) or len(item) < 4:
                        continue
                    nm, ann, headline, sub = item[0], item[1], item[2], item[3]
                    if ann is None:
                        continue
                    try:
                        ann_f = float(ann)
                    except (TypeError, ValueError):
                        continue
                    card_txt = f"{headline} {sub}"
                    has_neg_basis = bool(re.search(r"基差\s*-\s*\d|贴水|折价", card_txt))
                    has_pos_basis = bool(re.search(r"基差\s*\+\s*\d|升水", card_txt))
                    if has_neg_basis and not has_pos_basis and ann_f < 0:
                        errs.append(
                            f"{path.name}: Gate 3B CHART_A2 正负号反转 ({nm})：卡片写负基差/贴水，"
                            f"但 ann={ann_f} < 0 会渲染为「升水」（贴水/折价须为正数）"
                        )
                    elif has_pos_basis and not has_neg_basis and ann_f > 0:
                        errs.append(
                            f"{path.name}: Gate 3B CHART_A2 正负号反转 ({nm})：卡片写正基差/升水，"
                            f"但 ann={ann_f} > 0 会渲染为「折价」（升水须为负数）"
                        )

    # 7. Daily focus-stock table PE / dividend-yield / closing-price cross-check against deep_dossiers.json (post-cutover dailies)
    sort_key = parse_daily_sort_key(path)[:3]
    if not is_flagship and sort_key >= ALL_MAIN_CUTOVER and DEEP_DOSSIERS_PATH.is_file():
        errs.extend(_check_daily_focus_table_vs_dossiers(body, path.name, market, edition_date=sort_key[0]))

    # 8. Retracted-fact guard on flagship & post-cutover dailies + PBOC Doc 42 crypto firewall on dailies
    if is_flagship or sort_key >= ALL_MAIN_CUTOVER:
        errs.extend(_check_retracted_facts(path.name, body))
    if not is_flagship:
        errs.extend(_scan_text_for_crypto_buy(path.name, md_text))

    # 9. Deterministic G2 / G3 / G5 / G7 / S2 & Phase D editorial depth gates (>= 2026-11-27_0730 dailies)
    if not is_flagship and sort_key[:2] >= EDITORIAL_DEPTH_CUTOVER[:2]:
        errs.extend(_check_shfe_night_close(path.name, body))
        errs.extend(_check_scenario_10pt_and_dots(path.name, body))
        errs.extend(_check_tense_drift(path.name, body, sort_key[0]))
        errs.extend(_check_year_end_countdown(path.name, body, sort_key[0]))
        errs.extend(_check_credit_spread_ccc(path.name, body))
        ed_errs, ed_warns = _check_phase_d_editorial(body, path.name, meta)
        errs.extend(ed_errs)
        warns.extend(ed_warns)

    return errs, warns


def _check_shfe_night_close(label: str, text: str) -> list[str]:
    """Gate G2: Reject 02:30 attached to SHFE base-metal/ferrous night closes without 01:00/23:00 qualifier."""
    errs: list[str] = []
    for line_no, ln in enumerate(text.splitlines(), 1):
        if not _SHFE_0230_RE.search(ln) or not _SHFE_NON_GOLD_METAL_RE.search(ln):
            continue
        flagged = False
        for m_time in _SHFE_0230_RE.finditer(ln):
            for m_metal in _SHFE_NON_GOLD_METAL_RE.finditer(ln):
                if m_time.end() <= m_metal.start():
                    between = ln[m_time.end() : m_metal.start()]
                elif m_metal.end() <= m_time.start():
                    between = ln[m_metal.end() : m_time.start()]
                else:
                    between = ""
                same_clause = not bool(re.search(r"[。！？；]", between))
                within_45 = len(between) <= 45
                if (same_clause or within_45) and not _SHFE_EARLY_CLOSE_QUAL_RE.search(between):
                    metal_local = ln[max(0, m_metal.start() - 14) : min(len(ln), m_metal.end() + 14)]
                    if _SHFE_EARLY_CLOSE_QUAL_RE.search(metal_local):
                        continue
                    errs.append(
                        f"Gate G2 失败：{label} (L{line_no}) 将 02:30 误关联至非金银夜盘标的 "
                        f"({m_metal.group(0)}，有色夜盘 01:00 / 黑色 23:00 收盘)"
                    )
                    flagged = True
                    break
            if flagged:
                break
    return errs


def _extract_scenario_weight_matches(line: str) -> list[tuple[int, int, int]]:
    """Return list of (start, end, weight_int) from scenario weight mentions on a line."""
    found: list[tuple[int, int, int]] = []
    for m in _SCENARIO_WEIGHT_RE.finditer(line):
        raw_num = next(g for g in m.groups() if g is not None)
        found.append((m.start(), m.end(), int(raw_num)))
    return found


def _check_scenario_10pt_and_dots(label: str, text: str) -> list[str]:
    """Gate G3: Check 10-point scenario sum (single-line & multi-line blocks) and [●○]{10} dot-bar parity."""
    errs: list[str] = []
    lines = text.splitlines()
    for line_no, ln in enumerate(lines, 1):
        has_bar = bool(_TEN_DOT_RE.search(ln))
        if not has_bar and not _SCENARIO_LINE_TRIGGER_RE.search(ln):
            continue
        weights = _extract_scenario_weight_matches(ln)
        if len(weights) >= 2 and not _SCENARIO_DELTA_RE.search(ln):
            total = sum(w for _, _, w in weights)
            if total != 10:
                errs.append(
                    f"Gate G3 失败：{label} (L{line_no}) 情景 10 点拆分权重之和={total} ≠ 10 ({[w for _, _, w in weights]})"
                )
        if has_bar:
            # Build candidate (pos, weight) pairs for dot-bar parity
            weight_anchors = list(weights)
            if not weight_anchors:
                for m_r in _SCENARIO_SINGLE_RATIO_RE.finditer(ln):
                    weight_anchors.append((m_r.start(), m_r.end(), int(m_r.group(1))))
            for m_bar in _TEN_DOT_RE.finditer(ln):
                filled = m_bar.group(0).count("●")
                if not weight_anchors:
                    continue
                # Prefer the nearest preceding weight on the same line, else nearest following weight
                before = [w for w in weight_anchors if w[1] <= m_bar.start()]
                chosen = before[-1] if before else min(weight_anchors, key=lambda w: abs(w[0] - m_bar.end()))
                if filled != chosen[2]:
                    errs.append(
                        f"Gate G3 失败：{label} (L{line_no}) 10 点概率条实心数 ({filled}) 与对应权重 ({chosen[2]}) 不一致"
                    )

    # Scan consecutive multi-line scenario bullet/table blocks (2–6 adjacent lines) under a scenario context
    def _extract_block_line_weight(line: str) -> int | None:
        st = line.strip()
        is_bullet = bool(re.match(r"^(?:[-•*]|\d+\.)\s+", st))
        is_table_row = st.startswith("|") and st.endswith("|")
        if not (is_bullet or is_table_row):
            return None
        if is_table_row:
            cells = _split_md_row(st)
            if not cells or all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                return None
        matches: list[tuple[int, int, int]] = []
        for m in _MULTILINE_SCENARIO_WEIGHT_RE.finditer(line):
            raw_num = next(g for g in m.groups() if g is not None)
            matches.append((m.start(), m.end(), int(raw_num)))
        if len(matches) == 1:
            return matches[0][2]
        if len(matches) >= 2 and _SCENARIO_DELTA_RE.search(line):
            cur_matches = [
                w for s, _, w in matches
                if not re.search(r"(?:原|由|较上期)[^，。；（）]{0,4}$", line[max(0, s - 8) : s])
            ]
            if len(cur_matches) == 1:
                return cur_matches[0]
        return None

    def _has_scenario_context(start_idx: int, end_idx: int) -> bool:
        for k in range(start_idx, end_idx):
            if _SCENARIO_CONTEXT_RE.search(lines[k]):
                return True
        for k in range(max(0, start_idx - 5), start_idx):
            if _SCENARIO_CONTEXT_RE.search(lines[k]):
                return True
        for k in range(start_idx - 1, -1, -1):
            st_k = lines[k].strip()
            if st_k.startswith("#"):
                return bool(_SCENARIO_CONTEXT_RE.search(st_k))
        return False

    idx = 0
    while idx < len(lines):
        w0 = _extract_block_line_weight(lines[idx])
        if w0 is None:
            idx += 1
            continue
        is_tbl0 = lines[idx].strip().startswith("|")
        block_weights = [w0]
        end_idx = idx + 1
        while end_idx < len(lines):
            if lines[end_idx].strip().startswith("|") != is_tbl0:
                break
            wk = _extract_block_line_weight(lines[end_idx])
            if wk is None:
                break
            block_weights.append(wk)
            end_idx += 1
        if 2 <= len(block_weights) <= 6 and _has_scenario_context(idx, end_idx):
            total = sum(block_weights)
            if total != 10:
                errs.append(
                    f"Gate G3 失败：{label} (L{idx + 1}-L{end_idx}) 多行情景 10 点拆分权重之和={total} ≠ 10 ({block_weights})"
                )
        idx = end_idx
    return errs


def _check_tense_drift(label: str, text: str, edition_date: str) -> list[str]:
    """Gate G7: Catch stale relative-day tense drift (明日=今日 / 今日=昨日 / 昨日=前日, MM/DD & MM月DD日)."""
    try:
        ed = date.fromisoformat(edition_date)
    except ValueError:
        return []
    prev = ed - timedelta(days=1)
    prev2 = ed - timedelta(days=2)

    def _md_pat(d: date) -> str:
        return rf"(?:0?{d.month}/0?{d.day}(?!\d)|0?{d.month}\s*月\s*0?{d.day}\s*[日号])"

    pats = (
        (f"明日误标今日({ed.month}/{ed.day})", re.compile(rf"明日\s*[（(]?\s*{_md_pat(ed)}")),
        (f"今日误标昨日({prev.month}/{prev.day})", re.compile(rf"今日\s*[（(]?\s*{_md_pat(prev)}")),
        (f"昨日误标前日({prev2.month}/{prev2.day})", re.compile(rf"昨日\s*[（(]?\s*{_md_pat(prev2)}")),
    )
    errs: list[str] = []
    for line_no, ln in enumerate(text.splitlines(), 1):
        for desc, pat in pats:
            m = pat.search(ln)
            if m:
                errs.append(f"Gate G7 失败：{label} (L{line_no}) 相对时态错位（{desc}）-> {m.group(0)!r}")
    return errs


def _check_year_end_countdown(label: str, text: str, edition_date: str) -> list[str]:
    """Gate G7: Verify YYYY-12-31 countdown days match (date(year,12,31) - edition_date).days."""
    try:
        ed = date.fromisoformat(edition_date)
    except ValueError:
        return []
    errs: list[str] = []
    for line_no, ln in enumerate(text.splitlines(), 1):
        for m in _COUNTDOWN_YEAR_END_RE.finditer(ln):
            target_yr = int(m.group(1))
            stated = int(m.group(2))
            expected_days = (date(target_yr, 12, 31) - ed).days
            if stated != expected_days:
                errs.append(
                    f"Gate G7 失败：{label} (L{line_no}) 年底倒计时算错"
                    f"（写距 {target_yr}-12-31 剩 {stated} 天，按 {edition_date} 实为 {expected_days} 天）"
                )
    return errs


def _check_credit_spread_ccc(label: str, text: str) -> list[str]:
    """Gate S2: Require explicit CCC qualifier within ±20 chars of CCC-tier junk spread mentions."""
    errs: list[str] = []
    for line_no, ln in enumerate(text.splitlines(), 1):
        for m in _CREDIT_SPREAD_CCC_RE.finditer(ln):
            win = ln[max(0, m.start() - 20) : min(len(ln), m.end() + 20)]
            if not _CCC_QUAL_RE.search(win):
                errs.append(
                    f"Gate S2 失败：{label} (L{line_no}) 信用利差表述缺少 CCC 分级限定"
                    f"（防止混淆全口径高收益债与 CCC 级垃圾债利差）-> {win!r}"
                )
                break
    return errs


def _check_phase_d_editorial(body: str, filename: str, meta: dict | None) -> tuple[list[str], list[str]]:
    """Phase D (R8) editorial depth gates for >= 2026-11-27_0730 dailies."""
    errs: list[str] = []
    warns: list[str] = []

    head_block = body.split("\n---", 1)[0]
    lead_quotes: list[str] = []
    lead_h1_and_quotes: list[tuple[int, str]] = []
    for ln_no, ln in enumerate(head_block.splitlines(), 1):
        st = ln.strip()
        if st.startswith(">"):
            qtxt = st.lstrip(">").strip()
            lead_quotes.append(qtxt)
            lead_h1_and_quotes.append((ln_no, qtxt))
        elif st.startswith("# "):
            lead_h1_and_quotes.append((ln_no, st[2:].strip()))

    if lead_quotes:
        q_joined = "".join(lead_quotes)
        q_vis = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", q_joined)
        q_vis = re.sub(r"[*`]", "", q_vis).strip()
        if len(q_vis) > 230:
            warns.append(
                f"{filename}: Gate R8 开篇导语引用块偏长 ({len(q_vis)} 字 > 230 字，目标 ≤200 字)"
            )

    for ln_no, seg in lead_h1_and_quotes:
        hits = _AUDIT_JARGON_LEAD_RE.findall(seg)
        if hits:
            errs.append(
                f"{filename}: Gate R8 (L{ln_no}) 标题/导语出现内部审计术语 -> {sorted(set(hits))}"
            )
    if isinstance(meta, dict) and isinstance(meta.get("title"), str):
        thits = _AUDIT_JARGON_LEAD_RE.findall(meta["title"])
        if thits:
            errs.append(
                f"{filename}: Gate R8 封面标题出现内部审计术语 -> {sorted(set(thits))}"
            )

    for ln_no, ln in enumerate(body.splitlines(), 1):
        m_lazy = _LAZY_ZERO_SCORE_RE.search(ln)
        if m_lazy:
            errs.append(
                f"{filename}: Gate R8 (L{ln_no}) 6 维评分拆解严禁使用「{m_lazy.group(0)}」笼统省略，须逐维列明 0 分项"
            )

    ed_type = str(meta.get("edition_type", "")).strip().lower() if isinstance(meta, dict) else ""
    if ed_type == "main" and len(body) > 1000:
        bold_chars = sum(len(x) for x in re.findall(r"\*\*([^*]+)\*\*", body))
        plain_chars = max(1, len(re.sub(r"\s+", "", body)))
        bold_pct = (bold_chars / plain_chars) * 100.0
        if bold_pct < 4.5:
            warns.append(
                f"{filename}: Gate R8 主刊加粗文字占比过低 ({bold_pct:.1f}% < 4.5%，避免过度删粗削弱层级)"
            )

    tenor_scan = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    tenor_scan = re.sub(r"https?://[^\s)\]>]+", "", tenor_scan)
    bare_tenors = _BARE_TENOR_RE.findall(tenor_scan)
    if bare_tenors:
        warns.append(
            f"{filename}: Gate R8 存在未转译裸期限缩写 ({len(bare_tenors)} 处): "
            f"{sorted(set(bare_tenors))}（请改用中文如「前三季度/1月期/2年/10年」）"
        )

    return errs, warns


def _check_retracted_facts(label: str, text: str, *, skip_scorecard_col3: bool = False) -> list[str]:
    """Block retracted claims unless guarded by explicit negation/correction wording (skipping SCORECARD col 3)."""
    errs: list[str] = []
    for line_no, ln in enumerate(text.splitlines(), 1):
        scan_ln = ln
        if skip_scorecard_col3 and ln.strip().startswith("|") and ln.strip().endswith("|"):
            cells = _split_md_row(ln)
            if len(cells) >= 4:
                cells[2] = ""
                scan_ln = " | ".join(cells)
        for guard_lbl, pat in EQUITY_RETRACTED_FACT_GUARDS:
            for m in pat.finditer(scan_ln):
                win = scan_ln[max(0, m.start() - 40) : min(len(scan_ln), m.end() + 40)]
                if _EQUITY_RETRACTED_NEG_RE.search(win):
                    continue
                errs.append(
                    f"Gate 4 失败：{label} (L{line_no}) 残留已撤回错误口径（{guard_lbl}）-> {m.group(0)!r}"
                )
                break
    return errs


def _extract_dossier_pe_ranges(entry: dict) -> list[tuple[float, float]]:
    txt = str(entry.get("valuation_anchor", ""))
    ranges: list[tuple[float, float]] = []
    for m in re.finditer(
        r"(?:PE(?:-TTM)?|P/E|市盈率)\s*(?:仅|约|为|近|高达|达)?\s*(\d+(?:\.\d+)?)\s*(?:[x倍]\s*)?(?:[–\-~～至]\s*(\d+(?:\.\d+)?)\s*[x倍]?)?",
        txt,
        re.IGNORECASE,
    ):
        lo = float(m.group(1))
        hi = float(m.group(2)) if m.group(2) else lo
        ranges.append((min(lo, hi), max(lo, hi)))
    for m in re.finditer(
        r"(?:前瞻|滚动|静态|动态|盈利约|估值约)\s*(\d+(?:\.\d+)?)\s*(?:x\s*)?(?:[–\-~～至]\s*(\d+(?:\.\d+)?))?\s*[x倍]",
        txt,
        re.IGNORECASE,
    ):
        lo = float(m.group(1))
        hi = float(m.group(2)) if m.group(2) else lo
        ranges.append((min(lo, hi), max(lo, hi)))
    return ranges


def _extract_dossier_div_ranges(entry: dict) -> list[tuple[float, float]]:
    txt = " ".join(
        str(entry.get(k, "")) for k in ("valuation_anchor", "shareholder_flow", "financials")
    )
    ranges: list[tuple[float, float]] = []
    for m in re.finditer(
        r"股息率?\s*(?:逾|约|近|高达|达|为|仅|~)?\s*(\d+(?:\.\d+)?)%(?:\s*[–\-~～至]\s*(\d+(?:\.\d+)?)%)?",
        txt,
    ):
        lo = float(m.group(1))
        hi = float(m.group(2)) if m.group(2) else lo
        ranges.append((min(lo, hi), max(lo, hi)))
    return ranges


def _extract_numeric_ranges(text: str) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for m in re.finditer(
        r"(?<![\d.])(\d[\d,]*(?:\.\d+)?)\s*[–—\-~～至到]\s*(?:(?:HK|US|CN)?[$￥¥]\s*)?(\d[\d,]*(?:\.\d+)?)(?![\d.]|\s*[xX倍])",
        text,
    ):
        lo = float(m.group(1).replace(",", ""))
        hi = float(m.group(2).replace(",", ""))
        ranges.append((min(lo, hi), max(lo, hi)))
    return ranges


def _check_daily_focus_table_vs_dossiers(
    body: str,
    filename: str,
    market: str,
    *,
    edition_date: str | None = None,
) -> list[str]:
    """Compare explicit PE / dividend yield / closing price / buy anchor in daily focus-stock table rows against deep_dossiers.json."""
    try:
        dd_obj = json.loads(DEEP_DOSSIERS_PATH.read_text(encoding="utf-8"))
        dossiers = dd_obj.get("dossiers", {}) if isinstance(dd_obj, dict) else {}
    except (OSError, ValueError):
        return []
    if not isinstance(dossiers, dict) or not dossiers:
        return []

    errs: list[str] = []
    mkt_slug = {"a_share": "a-share", "hk_stock": "hk-stock", "us_stock": "us-stock"}[market]
    for line_no, ln in enumerate(body.splitlines(), 1):
        st = ln.strip()
        if not (st.startswith("|") and st.endswith("|")):
            continue
        cells = _split_md_row(st)
        if len(cells) < 2 or all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells):
            continue
        col0 = cells[0]
        if market == "a_share":
            cands = [f"{mkt_slug}:{m}" for m in re.findall(r"(?<![0-9])(\d{6})(?![0-9])", col0)]
        elif market == "hk_stock":
            cands = [f"{mkt_slug}:{m.zfill(5)}.HK" for m in re.findall(r"(?<![0-9])(\d{4,5})(?:\.HK)?(?![0-9])", col0)]
        else:
            cands = [f"{mkt_slug}:{m}" for m in re.findall(r"`([A-Z]{1,5}(?:\.[AB])?)`", col0)]
            if not cands:
                cands = [f"{mkt_slug}:{m}" for m in re.findall(r"[（(]([A-Z]{1,5}(?:\.[AB])?)[)）]", col0)]
            if not cands:
                cands = [f"{mkt_slug}:{m}" for m in re.findall(r"\b([A-Z]{1,5}(?:\.[AB])?)\b", col0)]
        matched_keys = [k for k in dict.fromkeys(cands) if k in dossiers]
        if len(matched_keys) != 1:
            continue
        dk = matched_keys[0]
        entry = dossiers[dk]
        if not isinstance(entry, dict):
            continue

        row_pes = [float(x) for x in re.findall(r"市盈率\s*(?:约)?\s*(\d+(?:\.\d+)?)\s*倍", st)]
        if row_pes:
            d_pes = _extract_dossier_pe_ranges(entry)
            if d_pes:
                for rp in row_pes:
                    best_dist = min(
                        0.0 if lo <= rp <= hi else min(abs(rp - lo), abs(rp - hi))
                        for lo, hi in d_pes
                    )
                    if best_dist > 1.0:
                        errs.append(
                            f"{filename}: Gate 3B 焦点股表 (L{line_no}) {dk} 市盈率 {rp:g} 倍 "
                            f"与深研档案估值锚 ({d_pes}) 偏离 {best_dist:.1f} 倍 (> 1.0x)"
                        )

        row_divs = [float(x) for x in re.findall(r"股息率?\s*(?:逾|约|近)?\s*(\d+(?:\.\d+)?)%", st)]
        if row_divs:
            d_divs = _extract_dossier_div_ranges(entry)
            if d_divs:
                for rd in row_divs:
                    best_dist = min(
                        0.0 if lo <= rd <= hi else abs(rd - (lo + hi) / 2.0)
                        for lo, hi in d_divs
                    )
                    if best_dist > 0.5:
                        errs.append(
                            f"{filename}: Gate 3B 焦点股表 (L{line_no}) {dk} 股息率 {rd:g}% "
                            f"与深研档案 ({d_divs}) 偏离 {best_dist:.2f} 百分点 (> 0.5pct)"
                        )

        # When dossier was updated on edition_date, verify explicit closing price & buy-anchor range consistency
        if edition_date and str(entry.get("updated_at", "")).strip() == edition_date:
            base_note = str(entry.get("baseline_note", ""))
            m_px = (
                re.search(r"收\s*[$¥HK]*\s*(\d[\d,]*(?:\.\d+)?)", col0)
                or re.search(r"<br\s*/?>\s*[$¥HK]*\s*(\d[\d,]*(?:\.\d+)?)\s*[（(][+\-]", col0, re.IGNORECASE)
            )
            if m_px and base_note:
                row_px = float(m_px.group(1).replace(",", ""))
                base_nums = [
                    float(x.replace(",", ""))
                    for x in re.findall(r"\d[\d,]*(?:\.\d+)?", base_note)
                ]
                tol = max(0.05, row_px * 0.005)
                if base_nums and not any(abs(bn - row_px) <= tol for bn in base_nums):
                    errs.append(
                        f"{filename}: Gate 3B 焦点股表 (L{line_no}) {dk} 收盘价 {row_px:g} "
                        f"未在当日已更新的 deep_dossiers.baseline_note 中出现"
                    )

            m_anchor = re.search(
                r"(?:回踩|回调|慢吸|低吸|分批配|观察锚|安全锚|锚)\s*(?:(?:HK|US|CN)?[$￥¥]\s*)?(\d[\d,]*(?:\.\d+)?)\s*[–—\-~～至到]\s*(?:(?:HK|US|CN)?[$￥¥]\s*)?(\d[\d,]*(?:\.\d+)?)(?![\d.]|\s*[xX倍])",
                st,
            )
            if m_anchor:
                r_lo = float(m_anchor.group(1).replace(",", ""))
                r_hi = float(m_anchor.group(2).replace(",", ""))
                r_lo, r_hi = min(r_lo, r_hi), max(r_lo, r_hi)
                d_anchor_ranges = _extract_numeric_ranges(
                    f"{entry.get('action_etf', '')} {base_note}"
                )
                if d_anchor_ranges:
                    def _rel_gap(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> float:
                        if a_hi >= b_lo and b_hi >= a_lo:
                            return 0.0
                        gap = min(abs(a_lo - b_hi), abs(b_lo - a_hi))
                        scale = max(1.0, (a_lo + a_hi) / 2.0)
                        return gap / scale

                    best_rel = min(_rel_gap(r_lo, r_hi, d_lo, d_hi) for d_lo, d_hi in d_anchor_ranges)
                    if best_rel > 0.05:
                        errs.append(
                            f"{filename}: Gate 3B 焦点股表 (L{line_no}) {dk} 买入/观察锚区间 {r_lo:g}–{r_hi:g} "
                            f"与深研档案区间 ({d_anchor_ranges}) 脱节超过 5%"
                        )
    return errs


def _scan_text_for_gold_buy(label: str, text: str) -> list[str]:
    found: list[str] = []
    for idx, ln in enumerate(text.splitlines(), 1):
        if any(
            not _GOLD_DEFER_GUARD_RE.search(re.split(r"[。！？；，,、|]", ln[:action.start()])[-1])
            for action in _GOLD_ACTIVE_BUY_RE.finditer(ln)
        ):
            found.append(
                f"Gate C2 跨项目硬冲突 ({label}:L{idx})：黄金当前为红灯停（new_buy_allowed=false），"
                f"权益侧严禁下达新买/补足黄金指令 -> {ln.strip()[:72]}"
            )
    return found


def _scan_text_for_crypto_buy(label: str, text: str) -> list[str]:
    found: list[str] = []
    for idx, ln in enumerate(text.splitlines(), 1):
        for action in _CRYPTO_ACTIVE_BUY_RE.finditer(ln):
            prefix = re.split(r"[。！？；，,|]", ln[:action.start()])[-1]
            if not _CRYPTO_NEGATION_GUARD_RE.search(prefix):
                found.append(
                    f"Gate 4 失败 ({label}:L{idx})：违反央行银发〔2026〕42号合规红线，"
                    f"中国大陆严禁个人配仓/买入虚拟货币 -> {ln.strip()[:72]}"
                )
                break
    return found


def _check_release_snapshot(gold: dict, state: dict, targets: list[Path]) -> list[str]:
    errors: list[str] = []
    edition_id = state.get("edition_id")
    edition_key = parse_edition_id(edition_id)
    if edition_key is None or parse_edition_id(gold.get("edition_id")) != edition_key:
        return ["Gate C1 失败：黄金与权益须声明同一有效 edition_id"]
    if any(parse_daily_sort_key(p)[:3] > edition_key for p in targets if not _detect_is_flagship(p)):
        errors.append("Gate C1 失败：日报场次晚于共享快照场次")
    try:
        g_ts = datetime.strptime(gold["as_of_short"], "%Y-%m-%d %H:%M").replace(tzinfo=BEIJING)
        e_ts = datetime.fromisoformat(state["as_of_cst"])
        edition_time = datetime.strptime(f"{edition_key[0]}_{edition_key[1]:04}", "%Y-%m-%d_%H%M").replace(tzinfo=BEIJING)
        if e_ts.utcoffset() != BEIJING.utcoffset(e_ts):
            raise ValueError("权益状态须明确使用 +08:00")
        if not timedelta(0) <= e_ts - g_ts <= MAX_EDITION_LAG:
            errors.append("Gate C1 失败：黄金须先于或同分钟于权益落盘，且数据时间差须在六小时内")
        if any(not (-MAX_EDITION_EARLY <= ts - edition_time <= MAX_EDITION_LAG) for ts in (g_ts, e_ts)):
            errors.append("Gate C1 失败：快照数据时间须在班次前 5 分钟至班次后 6 小时内")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"Gate C1 失败：跨项目时间戳非法：{exc}")

    try:
        mirror = state["markets"]["gold_mirror_readonly"]
        rates = state["cross_market_linkages"]["rates_fx_chain"]
        comm = state["cross_market_linkages"]["commodity_mirror"]
        brake = state["cross_market_linkages"]["crisis_correlation_brake"]
        if not all(isinstance(obj, dict) for obj in (mirror, rates, comm, brake)):
            raise TypeError("镜像字段须为对象")
    except (KeyError, TypeError) as exc:
        return errors + [f"Gate C1 失败：黄金跨市场镜像结构不完整：{exc}"]

    if mirror.get("edition_id") != edition_id or mirror.get("as_of_short") != gold.get("as_of_short"):
        errors.append("Gate C1 失败：黄金镜像场次或数据截点与权威快照不一致")
    if not gold.get("tier_code") or mirror.get("tier_code") != gold["tier_code"]:
        errors.append("Gate C1 失败：黄金档位与镜像不一致")
    if not isinstance(gold.get("new_buy_allowed"), bool) or mirror.get("new_buy_allowed") is not gold["new_buy_allowed"]:
        errors.append("Gate C1 失败：黄金新仓开关与镜像不一致或类型非法")
    if mirror.get("gates_passed") != f"{gold.get('tier1_passed')}/{gold.get('tier1_total')}":
        errors.append("Gate C1 失败：黄金过关计数与镜像不一致")
    values = (
        ("spot_gold_ny_close_usd", mirror, "spot_ny_close_usd"),
        ("us10y_pct", rates, "us10y_pct"),
        ("dfii10_live_pct", rates, "dfii10_pct"),
        ("dxy", rates, "dxy"),
        ("brent_settle_usd", comm, "brent_usd"),
        ("brent_live_usd", comm, "brent_live_usd"),
        ("cfets_cny_fixing", rates, "cfets_cny_fixing"),
        ("vix_close", brake, "vix_close"),
        ("on_rrp_usd_m", brake, "on_rrp_usd_m"),
        ("comex_copper_usd_lb", comm, "comex_copper_usd_lb"),
        ("comex_copper_change_pct", comm, "comex_copper_chg_pct"),
    )
    for gold_key, mirror_group, equity_key in values:
        gold_value, equity_value = gold.get(gold_key), mirror_group.get(equity_key)
        if gold_key == "brent_live_usd" and gold_value is None and equity_value is None:
            continue
        if (any(type(v) not in (int, float) or not isfinite(v) for v in (gold_value, equity_value))
                or gold_value != equity_value or (gold_key == "vix_close" and gold_value <= 0)):
            errors.append(f"Gate C1 失败：{gold_key} 跨轨数值缺失、非法或漂移 gold={gold_value} equity={equity_value}")
    gold_live, equity_live = gold.get("vix_live"), brake.get("vix_live")
    if gold_live is None and equity_live is None and edition_key > EDITION_CUTOVER:
        if gold.get("vix_live_as_of") is not None:
            errors.append("Gate C1 失败：VIX 无盘中观测时不得保留 vix_live_as_of")
        if brake.get("vix_intraday_high") is not None:
            errors.append("Gate C1 失败：VIX 无盘中观测时不得保留 vix_intraday_high")
    elif (any(type(v) not in (int, float) or not isfinite(v) or v <= 0 for v in (gold_live, equity_live))
          or gold_live != equity_live):
        errors.append(f"Gate C1 失败：vix_live 跨轨数值缺失、非法或漂移 gold={gold_live} equity={equity_live}")
    fixing_date = gold.get("cfets_fixing_date")
    try:
        if fixing_date != rates.get("cfets_fixing_date") or datetime.strptime(fixing_date, "%Y-%m-%d").date().isoformat() != fixing_date or fixing_date > edition_key[0]:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Gate C1 失败：CFETS 中间价日期须有效、跨轨一致且不晚于班次日期")

    # Expanded Gold<->Equity SSOT mirror check for all shared numeric fields present in both JSONs
    us_mkt = state.get("markets", {}).get("us_stock") if isinstance(state.get("markets"), dict) else {}
    us_mkt = us_mkt if isinstance(us_mkt, dict) else {}
    optional_shared = (
        ("us2y_pct", rates, "us2y_pct"),
        ("us30y_pct", rates, "us30y_pct"),
        ("usd_cny_1630", rates, "usd_cny_1630"),
        ("usd_cny_night", rates, "usd_cny_night"),
        ("usd_cnh_live", rates, "usd_cnh"),
        ("usd_jpy", rates, "usd_jpy"),
        ("usd_jpy", brake, "usdjpy_level"),
        ("sofr_pct", rates, "sofr_pct"),
        ("wti_settle_usd", comm, "wti_usd"),
        ("wti_live_usd", comm, "wti_live_usd"),
        ("brent_change_pct", comm, "brent_chg_pct"),
        ("brent_live_chg_pct", comm, "brent_live_chg_pct"),
        ("shfe_copper_day_rmb", comm, "shfe_copper_day_rmb"),
        ("shfe_copper_day_change_pct", comm, "shfe_copper_day_chg_pct"),
        ("shfe_copper_night_rmb", comm, "shfe_copper_night_rmb"),
        ("shfe_copper_night_change_pct", comm, "shfe_copper_night_chg_pct"),
        ("btc_usd", comm, "btc_usd"),
        ("btc_change_pct", comm, "btc_chg_pct"),
        ("spx_close", us_mkt, "benchmark_sp500"),
        ("spot_gold_live_usd", mirror, "spot_live_usd"),
        ("spot_gold_live_usd", comm, "gold_live_usd"),
        ("spot_gold_ny_close_usd", comm, "gold_ny_close_usd"),
        ("spot_gold_ny_change_pct", mirror, "spot_change_pct"),
        ("comex_front_settle_usd", mirror, "comex_front_settle_usd"),
        ("comex_gcz26_settle_usd", mirror, "comex_gcz26_settle_usd"),
        ("sge_au9999_day_rmb", mirror, "sge_au9999_day_rmb"),
        ("sge_autd_day_rmb", mirror, "sge_autd_day_rmb"),
        ("sge_autd_night_rmb", mirror, "sge_autd_night_rmb"),
        ("sge_same_ts_premium_rmb", mirror, "sge_same_ts_premium_rmb"),
    )
    for g_key, eq_group, eq_key in optional_shared:
        g_val = gold.get(g_key)
        e_val = eq_group.get(eq_key)
        if g_val is None or e_val is None:
            continue
        if (
            type(g_val) not in (int, float)
            or type(e_val) not in (int, float)
            or not (isfinite(g_val) and isfinite(e_val))
            or abs(float(g_val) - float(e_val)) > 1e-6
        ):
            errors.append(
                f"Gate C1 失败：共享字段 {g_key}↔{eq_key} 跨轨数值漂移 gold={g_val} equity={e_val}"
            )
    return errors


def _check_cross_project_gold(targets: list[Path], *, precheck: bool) -> tuple[list[str], list[str]]:
    """Cross-Project Consistency Gates C1-C3 against ../gold/data_snapshot.json."""
    errs: list[str] = []
    warns: list[str] = []
    if not GOLD_SNAPSHOT_PATH.exists():
        warns.append(f"Gate C1 跳过：未找到黄金快照 {GOLD_SNAPSHOT_PATH}")
        return errs, warns

    try:
        gold = json.loads(GOLD_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Gate C1 失败：无法解析黄金快照: {exc}"], warns

    if not isinstance(gold, dict):
        return ["Gate C1 失败：黄金快照须为 JSON 对象"], warns

    st: dict = {}
    if STATE_PATH.exists():
        try:
            st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return [f"Gate C1 失败：无法解析权益状态：{exc}"], warns
    if not isinstance(st, dict):
        return ["Gate C1 失败：权益状态须为 JSON 对象"], warns
    release = gold.get("edition_id") is not None or st.get("edition_id") is not None or any(
        parse_daily_sort_key(p)[:3] >= EDITION_CUTOVER for p in targets if not _detect_is_flagship(p)
    )
    if release:
        errs.extend(_check_release_snapshot(gold, st, targets))

    req_gold_keys = ("tier_code", "spot_gold_ny_close_usd", "us10y_pct", "brent_settle_usd", "vix_close")
    for rk in req_gold_keys:
        if gold.get(rk) is None:
            errs.append(f"Gate C1 失败：黄金快照缺少必填核心键 {rk}")

    gold_tier = str(gold.get("tier_code", "")).strip()
    gold_new_buy = gold.get("new_buy_allowed", gold_tier != "Tier 0")
    try:
        gold_copper_chg = float(gold.get("comex_copper_change_pct", 0) or 0)
    except (TypeError, ValueError):
        return errs + ["Gate C3 失败：COMEX 铜异动数值非法"], warns

    # Gate C1: market_state.json mirror & freshness consistency
    if st and not release:
        try:
            gold_spot, gold_us10y, gold_brent, gold_vix, gold_dfii10, gold_dxy, gold_on_rrp = (
                float(gold.get(key, 0) or 0) for key in (
                    "spot_gold_ny_close_usd", "us10y_pct", "brent_settle_usd", "vix_close", "dfii10_live_pct", "dxy", "on_rrp_usd_m"
                )
            )
        except (TypeError, ValueError):
            return errs + ["Gate C1 失败：黄金快照的历史宏观字段含非数值"], warns
        mirror = st.get("markets", {}).get("gold_mirror_readonly", {})
        if not mirror:
            errs.append("Gate C1 失败：state/market_state.json 缺少 markets.gold_mirror_readonly 镜像锁")
        else:
            if mirror.get("tier_code") != gold_tier:
                errs.append(f"Gate C1 失败：黄金档位漂移 market_state={mirror.get('tier_code')} vs gold={gold_tier}")
            if bool(mirror.get("new_buy_allowed")) != bool(gold_new_buy):
                errs.append(f"Gate C1 失败：黄金 new_buy_allowed 漂移 equity={mirror.get('new_buy_allowed')} vs gold={gold_new_buy}")
            if gold_spot and abs(float(mirror.get("spot_ny_close_usd", 0) or 0) - gold_spot) > 1.5:
                errs.append(f"Gate C1 失败：现货金漂移 market_state={mirror.get('spot_ny_close_usd')} vs gold={gold_spot}")
            link_rates = st.get("cross_market_linkages", {}).get("rates_fx_chain", {})
            if gold_us10y and link_rates.get("us10y_pct") is not None:
                if abs(float(link_rates["us10y_pct"]) - gold_us10y) > 0.03:
                    errs.append(f"Gate C1 失败：10Y美债漂移 equity={link_rates['us10y_pct']} vs gold={gold_us10y}")
            if gold_dfii10 and link_rates.get("dfii10_pct") is not None:
                if abs(float(link_rates["dfii10_pct"]) - gold_dfii10) > 0.04:
                    errs.append(f"Gate C1 失败：10Y实际利率漂移 equity={link_rates['dfii10_pct']} vs gold={gold_dfii10}")
            if gold_dxy and link_rates.get("dxy") is not None:
                if abs(float(link_rates["dxy"]) - gold_dxy) > 0.4:
                    errs.append(f"Gate C1 失败：美元指数漂移 equity={link_rates['dxy']} vs gold={gold_dxy}")
            comm = st.get("cross_market_linkages", {}).get("commodity_mirror", {})
            if gold_brent and comm.get("brent_usd") is not None:
                if abs(float(comm["brent_usd"]) - gold_brent) > 0.5:
                    errs.append(f"Gate C1 失败：布油漂移 equity={comm['brent_usd']} vs gold={gold_brent}")
            brake = st.get("cross_market_linkages", {}).get("crisis_correlation_brake", {})
            if gold_vix and brake.get("vix_close") is not None:
                if abs(float(brake["vix_close"]) - gold_vix) > 0.5:
                    errs.append(f"Gate C1 失败：VIX 漂移 equity={brake['vix_close']} vs gold={gold_vix}")
            if gold_on_rrp and brake.get("on_rrp_usd_m") is not None:
                if abs(float(brake["on_rrp_usd_m"]) - gold_on_rrp) > 20.0:
                    errs.append(f"Gate C1 失败：ON RRP 漂移 equity={brake['on_rrp_usd_m']} vs gold={gold_on_rrp}")

            # CFETS CNY fixing cross-check when both snapshots share the same fixing date
            gold_cfets = float(gold.get("cfets_cny_fixing", 0) or 0)
            gold_cfets_dt = str(gold.get("cfets_fixing_date", "")).strip()
            eq_cfets = link_rates.get("cfets_cny_fixing")
            eq_cfets_dt = str(link_rates.get("cfets_fixing_date", "")).strip()
            if gold_cfets and eq_cfets is not None and gold_cfets_dt and eq_cfets_dt == gold_cfets_dt:
                try:
                    if abs(float(eq_cfets) - gold_cfets) > 0.002:
                        errs.append(
                            f"Gate C1 失败：CFETS 中间价漂移 ({gold_cfets_dt}) equity={eq_cfets} vs gold={gold_cfets}"
                        )
                except (TypeError, ValueError):
                    errs.append(f"Gate C1 失败：cfets_cny_fixing 数值格式非法 ({eq_cfets})")

            # Window-aware Gold snapshot freshness check (fail loudly on malformed timestamps)
            g_ts_s = str(gold.get("as_of_short", "")).strip()
            e_ts_s = str(st.get("as_of_cst", "")).strip()
            try:
                g_dt = datetime.strptime(g_ts_s, "%Y-%m-%d %H:%M")
                e_dt = datetime.fromisoformat(e_ts_s).replace(tzinfo=None)
                delta_h = (e_dt - g_dt).total_seconds() / 3600.0
                # Unified sequential run windows (07:25–13:30 / 11:25–17:30 / 17:55–次日 00:00 CST, Gold SSOT first -> Equity second) allow <= 6.0h freshness; off-window manual <= 10.5h
                in_slot_window = (
                    e_dt.hour in range(7, 24)
                    or (e_dt.hour == 0 and e_dt.minute == 0)
                )
                max_h = 6.0 if in_slot_window else 10.5
                if delta_h > max_h:
                    warns.append(
                        f"Gate C1 新鲜度提醒：黄金快照 ({g_ts_s}) 早于股研状态 ({e_ts_s[:16]}) {delta_h:.1f} 小时 (> {max_h:.1f}h 阈值)"
                    )
                elif delta_h < -6.0:
                    warns.append(
                        f"Gate C1 反向滞后提醒：股研状态 ({e_ts_s[:16]}) 落后黄金快照 ({g_ts_s}) {abs(delta_h):.1f} 小时 (> 6.0h 阈值)"
                    )
            except Exception as exc:
                errs.append(f"Gate C1 失败：跨项目时间戳解析异常 gold={g_ts_s!r} equity={e_ts_s!r} ({exc})")

    # Gate C2: P0 Action Mutex Lock — when Gold is Tier 0 or new_buy_allowed is False, scan MD + INDEX + Daily JSON + Flagship JSON + SSOT DBs + ALL SVGs!
    if gold_tier == "Tier 0" or gold_new_buy is False:
        for p in targets:
            txt = p.read_text(encoding="utf-8")
            # Scan FULL file including DAILY_META_JSON so daily chart/KPI strings cannot bypass C2
            errs.extend(_scan_text_for_gold_buy(p.name, txt))
        idx_path = DAILY_DIR / "INDEX.md"
        if idx_path.exists():
            errs.extend(_scan_text_for_gold_buy(idx_path.name, idx_path.read_text(encoding="utf-8")))
        if st:
            for jpath, sval in _walk_json_strings(st, STATE_PATH.name):
                errs.extend(_scan_text_for_gold_buy(jpath, sval))
        if MULTI_ASSET_PATH.exists():
            try:
                ma_obj = json.loads(MULTI_ASSET_PATH.read_text(encoding="utf-8"))
                for jpath, sval in _walk_json_strings(ma_obj, MULTI_ASSET_PATH.name):
                    errs.extend(_scan_text_for_gold_buy(jpath, sval))
                for ch in ma_obj.get("channels", []) if isinstance(ma_obj, dict) else []:
                    if not isinstance(ch, dict):
                        continue
                    for prod in ch.get("products", []) if isinstance(ch.get("products"), list) else []:
                        if not isinstance(prod, dict):
                            continue
                        pcode = _normalize_etf_code(prod.get("code"))
                        pname = str(prod.get("name", ""))
                        pnote = str(prod.get("note", ""))
                        if pcode in _GOLD_ETF_CODES or _GOLD_ETF_NAME_RE.search(pname):
                            if not re.search(r"(?:红灯|暂不|暂停|严禁|禁止|锁)", pnote + pname):
                                errs.append(
                                    f"Gate C2 跨项目硬冲突 ({MULTI_ASSET_PATH.name}:{pcode or pname})："
                                    f"黄金红灯停期收录黄金/金矿产品必须显式注明红灯暂停新买锁"
                                )
            except (OSError, ValueError) as exc:
                errs.append(f"Gate C2 失败：{MULTI_ASSET_PATH.name} 解析异常: {exc}")
        if ETF_UNIVERSE_PATH.exists():
            try:
                etf_raw = ETF_UNIVERSE_PATH.read_text(encoding="utf-8")
                errs.extend(_scan_text_for_gold_buy(ETF_UNIVERSE_PATH.name, etf_raw))
                etf_obj = json.loads(etf_raw)
                for etf in etf_obj.get("etfs", []) if isinstance(etf_obj, dict) else []:
                    if not isinstance(etf, dict):
                        continue
                    code = str(etf.get("code", "")).strip()
                    code_norm = _normalize_etf_code(code)
                    name = str(etf.get("name", "")).strip()
                    has_ac = "asset_class" in etf and etf.get("asset_class") is not None
                    ac_str = str(etf.get("asset_class", "")).strip() if has_ac else ""
                    is_gold_etf = (
                        etf.get("gold_locked") is True
                        or ac_str == "gold"
                        or code_norm in _GOLD_ETF_CODES
                        or bool(_GOLD_ETF_NAME_RE.search(name))
                    )
                    if is_gold_etf:
                        role = str(etf.get("action_role", "")).strip()
                        if not role or _GOLD_ETF_FORBIDDEN_ROLE_RE.search(role):
                            errs.append(
                                f"Gate C2 跨项目硬冲突 ({ETF_UNIVERSE_PATH.name}:{code})："
                                f"黄金红灯停期严禁将黄金/金矿 ETF action_role 标为底座/买入/推荐/定投/配置 -> {role!r}"
                            )
                    if has_ac:
                        if ac_str == "gold" and etf.get("gold_locked") is not True:
                            errs.append(
                                f"Gate C2 跨项目硬冲突 ({ETF_UNIVERSE_PATH.name}:{code})："
                                f"黄金红灯停期 asset_class='gold' 须配 gold_locked=true"
                            )
                        elif etf.get("gold_locked") is True and ac_str != "gold":
                            errs.append(
                                f"Gate C2 跨项目硬冲突 ({ETF_UNIVERSE_PATH.name}:{code})："
                                f"黄金红灯停期 gold_locked=true 须配 asset_class='gold'（当前为 {ac_str!r}）"
                            )
            except (OSError, ValueError) as exc:
                errs.append(f"Gate C2 失败：{ETF_UNIVERSE_PATH.name} 解析异常: {exc}")
        if DEEP_DOSSIERS_PATH.exists():
            try:
                dd_obj = json.loads(DEEP_DOSSIERS_PATH.read_text(encoding="utf-8"))
                dossiers_map = dd_obj.get("dossiers", {}) if isinstance(dd_obj, dict) else {}
                for dkey, dval in dossiers_map.items() if isinstance(dossiers_map, dict) else []:
                    if not isinstance(dval, dict):
                        continue
                    for dim, txt_val in dval.items():
                        if isinstance(txt_val, str):
                            errs.extend(_scan_text_for_gold_buy(f"{DEEP_DOSSIERS_PATH.name}:{dkey}.{dim}", txt_val))
                    is_gold_stock = dkey in _GOLD_DOSSIER_KEYS or bool(_GOLD_MINER_TICKERS_RE.search(dkey))
                    if is_gold_stock:
                        act = str(dval.get("action_etf", ""))
                        for m_base in _GOLD_BASE_ROLE_RE.finditer(act):
                            prefix = re.split(r"[。！？；，,、|]", act[:m_base.start()])[-1]
                            if not _GOLD_BASE_NEGATION_RE.search(prefix):
                                errs.append(
                                    f"Gate C2 跨项目硬冲突 ({DEEP_DOSSIERS_PATH.name}:{dkey}.action_etf)："
                                    f"黄金红灯停期严禁将涉金标的列为绿色/当下底座 -> {act[:72]}"
                                )
                                break
            except (OSError, ValueError) as exc:
                errs.append(f"Gate C2 失败：{DEEP_DOSSIERS_PATH.name} 解析异常: {exc}")
        if POLICY_CALENDAR_PATH.exists():
            try:
                pc_obj = json.loads(POLICY_CALENDAR_PATH.read_text(encoding="utf-8"))
                for jpath, sval in _walk_json_strings(pc_obj, POLICY_CALENDAR_PATH.name, skip_keys=frozenset()):
                    errs.extend(_scan_text_for_gold_buy(jpath, sval))
            except (OSError, ValueError) as exc:
                errs.append(f"Gate C2 失败：{POLICY_CALENDAR_PATH.name} 解析异常: {exc}")
        for mkt_k, chart_k, mf in (
            ("a_share", "a7", BASE_DIR / "report_meta_a_share.json"),
            ("hk_stock", "h7", BASE_DIR / "report_meta_hk_stock.json"),
            ("us_stock", "u7", BASE_DIR / "report_meta_us_stock.json"),
        ):
            if mf.exists():
                m_raw = mf.read_text(encoding="utf-8")
                errs.extend(_scan_text_for_gold_buy(mf.name, m_raw))
                try:
                    m_obj = json.loads(m_raw)
                    pts = m_obj.get("chart_live", {}).get(chart_k, {}).get("points", [])
                    for pt in pts:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 5:
                            plbl, pcls, pcol = str(pt[0]), str(pt[3]).lower(), str(pt[4]).upper()
                            if _GOLD_MINER_TICKERS_RE.search(plbl) and (pcls == "g" or pcol == "#009E73"):
                                errs.append(
                                    f"Gate C2 跨项目硬冲突 ({mf.name}:{chart_k})：黄金红灯停期严禁将金矿/黄金标的标为绿色底座 -> {plbl}"
                                )
                except Exception as exc:
                    errs.append(f"Gate C2 失败：{mf.name} 解析异常: {exc}")
        # Also scan rendered flagship & daily SVGs directly so hardcoded SVG cards can never bypass C2!
        svg_checks, svg_warns = _collect_rendered_svgs(targets)
        warns.extend(svg_warns)
        for lbl, svg_html in svg_checks:
            plain_svg = re.sub(r"<[^>]+>", "\n", svg_html)
            errs.extend(_scan_text_for_gold_buy(lbl, plain_svg))

    # Gate C3: Commodity shock propagation check (Copper >= 3.5% shock must be noted in A/HK dailies & flagships)
    if abs(gold_copper_chg) >= 3.5:
        for p in targets:
            if "_a_share" in p.name or "_hk_stock" in p.name or "a_share_market_report" in p.name or "hk_stock_market_report" in p.name:
                txt = p.read_text(encoding="utf-8")
                if "铜" not in txt:
                    warns.append(
                        f"Gate C3 大宗跨市联动提醒 ({p.name})：COMEX 铜异动 {gold_copper_chg:+.2f}%，"
                        "A股/港股报告须评估对有色/紫金/洛钼的传导"
                    )
    return errs, warns


def _load_equity_build_daily():
    target_path = (BASE_DIR / "build_daily.py").resolve()
    existing = sys.modules.get("build_daily")
    existing_file = getattr(existing, "__file__", None)
    if existing is not None and existing_file and Path(existing_file).resolve() == target_path:
        return existing
    spec = importlib.util.spec_from_file_location("_equity_lint_build_daily", target_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {target_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _collect_rendered_svgs(targets: list[Path]) -> tuple[list[tuple[str, str]], list[str]]:
    """Render all 21 flagship vector SVGs plus embedded charts for non-flagship daily targets."""
    svg_checks: list[tuple[str, str]] = []
    warns: list[str] = []
    try:
        if str(BASE_DIR) not in sys.path:
            sys.path.insert(0, str(BASE_DIR))
        import build_a_share_pdf as mod_a
        import build_hk_stock_pdf as mod_h
        import build_us_stock_pdf as mod_u
        mod_d = _load_equity_build_daily()
        svg_checks = [
            ("SVG:A1", mod_a.svg_chart_a1_cycles()),
            ("SVG:A2", mod_a.svg_chart_a2_split_and_futures()),
            ("SVG:A3", mod_a.svg_chart_a3_macro_k_split()),
            ("SVG:A4", mod_a.svg_chart_a4_clock()),
            ("SVG:A5", mod_a.svg_chart_a5_targets_and_math()),
            ("SVG:A6", mod_a.svg_chart_a6_sector_heatmap()),
            ("SVG:A7", mod_a.svg_chart_a7_stock_quadrant()),
            ("SVG:H1", mod_h.svg_chart_h1_cycles()),
            ("SVG:H2", mod_h.svg_chart_h2_flow_and_rebalance()),
            ("SVG:H3", mod_h.svg_chart_h3_peg_and_erp()),
            ("SVG:H4", mod_h.svg_chart_h4_clock()),
            ("SVG:H5", mod_h.svg_chart_h5_targets_and_scenarios()),
            ("SVG:H6", mod_h.svg_chart_h6_ah_arbitrage_and_sectors()),
            ("SVG:H7", mod_h.svg_chart_h7_stock_quadrant()),
            ("SVG:U1", mod_u.svg_chart_u1_crises_and_mas()),
            ("SVG:U2", mod_u.svg_chart_u2_storm_timeline()),
            ("SVG:U3", mod_u.svg_chart_u3_credit_split()),
            ("SVG:U4", mod_u.svg_chart_u4_clock()),
            ("SVG:U5", mod_u.svg_chart_u5_wall_street_forensic()),
            ("SVG:U6", mod_u.svg_chart_u6_sector_heatmap()),
            ("SVG:U7", mod_u.svg_chart_u7_stock_quadrant()),
        ]
        for p in targets:
            if not _detect_is_flagship(p) and p.exists():
                p_txt = p.read_text(encoding="utf-8")
                d_meta, _ = _extract_meta(p_txt, p)
                if d_meta:
                    d_charts = mod_d.load_optional_charts(_detect_market(p), meta_override=d_meta)
                    for ck, c_html in d_charts.items():
                        tok_m = re.search(r"CHART_[A-Z0-9_]+", ck)
                        if tok_m and re.search(rf"<!--\s*{re.escape(tok_m.group(0))}\s*-->", p_txt):
                            svg_checks.append((f"{p.name}:{ck}", c_html))
                if "DAILY_VISUAL" in p_txt:
                    scripts_dir = str(BASE_DIR.parent / "scripts")
                    if scripts_dir not in sys.path:
                        sys.path.insert(0, scripts_dir)
                    import visual_widgets  # type: ignore[import-not-found]
                    _, visuals = visual_widgets.extract_visual_directives(p_txt)
                    for idx, (_, v_html) in enumerate(visuals.items(), 1):
                        svg_checks.append((f"{p.name}:DAILY_VISUAL#{idx}", v_html))
    except Exception as exc:
        warns.append(f"SVG 渲染预扫跳过: {exc}")
    return svg_checks, warns


def _check_svg_geometry_all(targets: list[Path]) -> tuple[list[str], list[str]]:
    """Run scripts/svg_geometry.py text OOB & collision checks across all 21 flagship & embedded daily SVGs."""
    errs: list[str] = []
    scripts_path = BASE_DIR.parent / "scripts"
    if not scripts_path.is_dir():
        return [], []
    scripts_dir = str(scripts_path)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        from svg_geometry import check_svg_text_geometry
        import visual_widgets  # type: ignore[import-not-found]
    except Exception as exc:
        return [f"Gate 3B SVG 几何检失败：无法导入 scripts/svg_geometry.py ({exc})"], []

    # Validate DAILY_VISUAL directive JSON schema strictly on every daily markdown target
    for p in targets:
        if not _detect_is_flagship(p) and p.exists():
            p_txt = p.read_text(encoding="utf-8")
            for idx, m_vis in enumerate(visual_widgets.DAILY_VISUAL_RE.finditer(p_txt), 1):
                try:
                    spec = json.loads(m_vis.group(1))
                except json.JSONDecodeError as exc:
                    errs.append(f"Gate 3B 视觉图 JSON 解析失败 ({p.name}#DAILY_VISUAL#{idx}): {exc}")
                    continue
                for v_err in visual_widgets.validate_visual_spec(spec):
                    errs.append(f"Gate 3B 视觉图结构错 ({p.name}#DAILY_VISUAL#{idx}): {v_err}")

    svg_checks, warns = _collect_rendered_svgs(targets)
    for lbl, svg_html in svg_checks:
        for issue in check_svg_text_geometry(svg_html, label=lbl):
            errs.append(f"Gate 3B SVG 几何碰撞: {issue}")
    return errs, warns


def _check_state_schedule(state: dict) -> list[str]:
    errors: list[str] = []
    current = parse_edition_id(state.get("edition_id"))
    queue = state.get("pending_backfills")
    if not isinstance(queue, list):
        errors.append("Gate 4 失败：pending_backfills 须为数组")
    else:
        for index, item in enumerate(queue):
            if not isinstance(item, dict) or item.get("market") not in MARKETS or not isinstance(item.get("item"), str) or not item["item"].strip():
                errors.append(f"Gate 4 失败：pending_backfills[{index}] 须有有效市场和待补事项")
                continue
            due = parse_edition_id(item.get("due_session"))
            if due is None or due[2] != 1:
                errors.append(f"Gate 4 失败：pending_backfills[{index}].due_session 须为有效计划班次")
            elif current and due[:2] < current[:2]:
                errors.append(f"Gate 4 失败：pending_backfills[{index}] 已逾期，须结清或指定下次核验班次")

    try:
        calendar = json.loads(GOLD_CALENDAR_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return errors + [f"Gate 4 失败：无法读取黄金交易日历：{exc}"]
    if not current:
        _, calendar_errors = calendar_rules(state, calendar)
        if "edition_id" in state:
            errors.append("Gate 4 失败：market_state.json.edition_id 非法")
        return errors + [f"Gate 4 失败：{error}" for error in calendar_errors]

    plan, plan_errors = edition_plan(state["edition_id"], state, calendar)
    errors.extend(f"Gate 4 失败：{error}" for error in plan_errors)
    if not plan_errors:
        errors.extend(_check_edition_delivery(state, current, plan))
    return errors


def _check_edition_delivery(state: dict, current: tuple[str, int, int], plan: dict) -> list[str]:
    errors = []
    if state.get("period_slug") != plan["period_slug"]:
        errors.append(f"Gate 4 失败：市场状态 period_slug 须更新为 {plan['period_slug']}")
    exceptions = state.get("publication_exceptions")
    if exceptions and exceptions.get("edition_id") != plan["edition_id"]:
        errors.append("Gate 4 失败：publication_exceptions 须标记当前 edition_id，旧班次的例外应移除")
    markets = state.get("markets")
    if not isinstance(markets, dict):
        return errors

    for market, expected in plan["markets"].items():
        per_market = markets.get(market)
        if not isinstance(per_market, dict):
            continue
        try:
            meta = _read_flagship_meta(market)
            if meta["period_slug"] != plan["period_slug"]:
                errors.append(f"Gate 4 失败：report_meta_{market}.json.period_slug 须为 {plan['period_slug']}")
            else:
                month = plan["period_slug"]
                if not (BASE_DIR / f"{market}_market_report_{month}.md").is_file():
                    errors.append(f"Gate 4 失败：{market} 缺少 {month} 旗舰 Markdown")
                chart = meta.get("chart_live")
                stamp = chart.get("as_of_full") if isinstance(chart, dict) else None
                match = _FLAGSHIP_CUTOFF_RE.match(stamp) if isinstance(stamp, str) else None
                try:
                    cutoff = datetime.strptime(
                        f"{match[1]} {match[2]}", "%Y年%m月%d日 %H:%M" if "年" in match[1] else "%Y-%m-%d %H:%M"
                    ) if match else None
                except ValueError:
                    cutoff = None
                if cutoff is None or cutoff.strftime("%Y_%m") != month or cutoff.date().isoformat() > current[0]:
                    errors.append(f"Gate 4 失败：report_meta_{market}.json.chart_live.as_of_full 须为当期且不超出班次日期的有效截点")
        except (OSError, ValueError) as exc:
            errors.append(f"Gate 4 失败：report_meta_{market}.json：{exc}")

        reports = _market_daily_files(market)
        seen = {}
        for report in reports:
            key = parse_daily_sort_key(report)[:3]
            if key in seen:
                errors.append(f"Gate 4 失败：重复的 {market} 日报 {seen[key].relative_to(BASE_DIR)} 与 {report.relative_to(BASE_DIR)}")
            else:
                seen[key] = report
        latest = max(reports, key=parse_daily_sort_key, default=None)
        pointer = per_market.get("latest_daily")
        if latest is None or pointer != latest.relative_to(BASE_DIR).as_posix():
            errors.append(f"Gate 4 失败：{market} 的 latest_daily 须指向该市场最近的实际日报")
        if latest and parse_daily_sort_key(latest)[:3] > current:
            errors.append(f"Gate 4 失败：{latest.name} 晚于当前刊期 {plan['edition_id']}")
        if expected["action"] == "publish":
            report = BASE_DIR / expected["required_file"]
            if not report.is_file():
                errors.append(f"Gate 4 失败：{plan['edition_id']} 缺当班 {market} {expected['edition_type']}：{report.name}")
                continue
            data, err = _extract_meta(report.read_text(encoding="utf-8"), report)
            if err or not data or data.get("edition_id") != plan["edition_id"]:
                errors.append(f"Gate 4 失败：{report.name} 须绑定当班 edition_id")
            if not data or data.get("edition_type") != expected["edition_type"]:
                errors.append(f"Gate 4 失败：{report.name} 刊型应为 {expected['edition_type']}")
            continue
        if latest and parse_daily_sort_key(latest)[:3] == current:
            errors.append(f"Gate 4 失败：{latest.name} 当班应复用旧刊，不应生成新刊")
        if expected["reason"] == "revision_reuse" and (
            latest is None or parse_daily_sort_key(latest)[:2] != current[:2]
        ):
            errors.append(f"Gate 4 失败：{market} 修订复用须有同班更早版本")
        if expected["reason"] == "source_outage":
            next_review = exceptions["markets"][market]["next_review_session"]
            queue = state.get("pending_backfills")
            if not isinstance(queue, list) or not any(
                isinstance(entry, dict) and entry.get("market") == market and entry.get("due_session") == next_review
                for entry in queue
            ):
                errors.append(f"Gate 4 失败：{market} 数据故障须在 pending_backfills 登记相同核验班次")
    return errors


def _read_flagship_meta(market: str) -> dict:
    meta_file = BASE_DIR / f"report_meta_{market}.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    slug = meta.get("period_slug") if isinstance(meta, dict) else None
    if not isinstance(slug, str) or not _PERIOD_RE.fullmatch(slug):
        raise ValueError("period_slug 须为有效 YYYY_MM")
    return meta


def _market_daily_files(market: str, *, keep_invalid: bool = False) -> list[Path]:
    pattern = f"????-??-??_*_{market}*.md"
    paths = (*DAILY_DIR.glob(pattern), *(DAILY_DIR / "archive").rglob(pattern))
    return sorted(
        (path for path in paths if keep_invalid or parse_daily_sort_key(path)[0] != "0000-00-00"),
        key=parse_daily_sort_key,
    )


def load_current_edition_plan() -> dict | None:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("权益状态须为 JSON 对象")
    if "edition_id" not in state:
        return None
    calendar = json.loads(GOLD_CALENDAR_PATH.read_text(encoding="utf-8"))
    edition_id = state["edition_id"]
    plan, errors = edition_plan(edition_id, state, calendar)
    if errors:
        raise ValueError("\n".join(errors))
    current = parse_edition_id(edition_id)
    assert current is not None
    delivery_errors = _check_edition_delivery(state, current, plan)
    if delivery_errors:
        raise ValueError("\n".join(delivery_errors))
    return plan


def _check_rsi_metrics(data: dict) -> list[str]:
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        return ["rsi_metrics.json 须为包含 runs 数组的对象"]
    dims = data.get("score_dimensions")
    if (not isinstance(dims, list) or len(dims) != 6
            or any(not isinstance(dim, str) or not dim.strip() for dim in dims) or len(set(dims)) != 6):
        return ["rsi_metrics.json score_dimensions 须为 6 个唯一维度"]
    errors = []
    seen = set()
    for index, run in enumerate(data["runs"]):
        if not isinstance(run, dict):
            errors.append(f"rsi_metrics.json runs[{index}] 须为对象")
            continue
        identifier = run.get("run_id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            errors.append(f"rsi_metrics.json ({index}) run_id 重复或缺失")
            continue
        seen.add(identifier)
        scores = run.get("scores")
        if not isinstance(scores, dict) or scores.keys() != set(dims):
            errors.append(f"rsi_metrics.json ({identifier}) scores 维度不匹配")
        elif any(type(score) is not int or not 1 <= score <= 5 for score in scores.values()):
            errors.append(f"rsi_metrics.json ({identifier}) 各维度分数须为 1–5 的整数")
        elif type(run.get("total_score")) is not int or sum(scores.values()) != run["total_score"] or type(run.get("max_score")) is not int or run["max_score"] != 30:
            errors.append(f"rsi_metrics.json ({identifier}) 分数合计不一致")

    if data["runs"] and isinstance(data["runs"][-1], dict):
        latest_run = data["runs"][-1]
        latest_id = latest_run.get("run_id", "latest")
        findings_sources: list[tuple[str, object]] = []
        if "review_closure" in latest_run:
            rc = latest_run["review_closure"]
            if not isinstance(rc, dict):
                errors.append(f"rsi_metrics.json ({latest_id}) review_closure 须为对象")
            else:
                if rc.get("reviewer_completed") is False:
                    errors.append(f"rsi_metrics.json ({latest_id}) review_closure.reviewer_completed 不可为 false")
                if "findings" in rc:
                    findings_sources.append(("review_closure.findings", rc["findings"]))
        if "findings" in latest_run:
            findings_sources.append(("findings", latest_run["findings"]))
        for field_lbl, flist in findings_sources:
            if not isinstance(flist, list):
                errors.append(f"rsi_metrics.json ({latest_id}) {field_lbl} 须为数组")
                continue
            for fidx, fitem in enumerate(flist):
                if not isinstance(fitem, dict):
                    errors.append(f"rsi_metrics.json ({latest_id}) {field_lbl}[{fidx}] 须为对象")
                    continue
                fstatus = str(fitem.get("status", "")).strip()
                if fstatus == "open":
                    desc = str(fitem.get("description", ""))[:60]
                    errors.append(f"rsi_metrics.json ({latest_id}) 存在未闭环 finding (status=open): {desc}")
                elif fstatus not in _RSI_ALLOWED_FINDING_STATUSES:
                    errors.append(
                        f"rsi_metrics.json ({latest_id}) {field_lbl}[{fidx}].status 非法 ({fstatus!r}，"
                        f"须为 {sorted(_RSI_ALLOWED_FINDING_STATUSES)})"
                    )
    return errors


def _check_index_links(index: Path, *, precheck: bool) -> list[str]:
    errors = []
    for href in re.findall(r"\[[^\]]+\]\(([^)\s]+)\)", index.read_text(encoding="utf-8")):
        if "/releases/download/" in href.lower():
            errors.append(f"Gate 4 失败：INDEX.md 含已弃用的离线附件链接 {href}")
            continue
        if href.startswith(("http://", "https://", "#")):
            continue
        target = Path(href[len("file://") :]) if href.startswith("file://") else (index.parent / href).resolve()
        suffix = target.suffix.lower()
        if suffix in (".pdf", ".docx"):
            errors.append(f"Gate 4 失败：INDEX.md 含已弃用的 PDF/Word 链接 {href}")
            continue
        if target.is_file():
            continue
        errors.append(f"Gate 4 失败：INDEX.md 死链 {href}")
    return errors


def _check_data_caveats(state: dict | None, *, require_presence: bool) -> list[str]:
    errs: list[str] = []
    if not isinstance(state, dict):
        return errs
    if "data_caveats" not in state:
        if require_presence:
            errs.append("Gate 4 失败：market_state.json 缺少 data_caveats 数组")
        return errs
    caveats = state.get("data_caveats")
    if not isinstance(caveats, list):
        return ["Gate 4 失败：market_state.json.data_caveats 须为数组"]
    for idx, item in enumerate(caveats):
        if not isinstance(item, dict):
            errs.append(f"Gate 4 失败：market_state.json data_caveats[{idx}] 须为对象")
            continue
        for req_k in ("id", "item", "detail", "impact"):
            val = item.get(req_k)
            if not isinstance(val, str) or not val.strip():
                errs.append(f"Gate 4 失败：market_state.json data_caveats[{idx}] 缺少非空 {req_k}")
        if "market" in item and item["market"] not in _CAVEAT_ALLOWED_MARKETS:
            errs.append(f"Gate 4 失败：market_state.json data_caveats[{idx}].market 非法 ({item['market']!r})")
        if item.get("category") not in _CAVEAT_ALLOWED_CATEGORIES:
            errs.append(f"Gate 4 失败：market_state.json data_caveats[{idx}].category 非法 ({item.get('category')!r})")
        if item.get("severity") not in _CAVEAT_ALLOWED_SEVERITIES:
            errs.append(f"Gate 4 失败：market_state.json data_caveats[{idx}].severity 非法 ({item.get('severity')!r})")
        for scan_k in ("item", "detail", "impact", "next_review"):
            sval = item.get(scan_k)
            if isinstance(sval, str):
                hits = _BANNED_INTERNAL_RE.findall(sval)
                if hits:
                    errs.append(
                        f"Gate 4 失败：market_state.json data_caveats[{idx}].{scan_k} 泄露内部词: {sorted(set(hits))}"
                    )
    return errs


def _check_ssot_databases(state: dict | None) -> list[str]:
    """Validate required multi_asset_channels.json, etf_universe.json, and deep_dossiers.json SSOTs."""
    errs: list[str] = []
    expected_pool = 231
    require_presence = False
    is_synthetic_small_pool = False
    state_edition_id: str | None = None
    state_edition_key: tuple[str, int, int] | None = None
    if isinstance(state, dict):
        ed = state.get("edition_id")
        if isinstance(ed, str):
            parsed_ed = parse_edition_id(ed)
            if parsed_ed is not None:
                state_edition_id = ed
                state_edition_key = parsed_ed
        if isinstance(state.get("markets"), dict):
            counts = [
                state["markets"][m].get("stock_pool_count")
                for m in MARKETS
                if isinstance(state["markets"].get(m), dict)
            ]
            if len(counts) == len(MARKETS) and all(type(c) is int and c > 0 for c in counts):
                expected_pool = sum(counts)
                require_presence = expected_pool >= 100
                is_synthetic_small_pool = expected_pool < 100
    enforce_g5_g7 = state_edition_key is not None and state_edition_key[:2] >= EDITORIAL_DEPTH_CUTOVER[:2]
    state_ed_date = state_edition_key[0] if state_edition_key else None

    req_channels = _SYNTHETIC_LEGACY_MULTI_ASSET_CHANNELS if is_synthetic_small_pool else _REQUIRED_MULTI_ASSET_CHANNELS
    min_etf_count = 100 if is_synthetic_small_pool else 140
    ma_loaded: dict | None = None
    etf_fee_ssot: dict[str, tuple[str, float]] = {}

    # 1. multi_asset_channels.json (12 MECE standard channels in production; 8-channel legacy fixture compat for small synthetic pools)
    if not MULTI_ASSET_PATH.exists():
        if require_presence:
            errs.append("Gate 4 失败：缺少 state/multi_asset_channels.json")
    else:
        try:
            ma = json.loads(MULTI_ASSET_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errs.append(f"Gate 4 失败：multi_asset_channels.json 解析失败: {exc}")
        else:
            if not isinstance(ma, dict):
                errs.append("Gate 4 失败：multi_asset_channels.json 根元素须为对象")
            else:
                ma_loaded = ma
                if state_edition_id and ma.get("edition_id") != state_edition_id:
                    errs.append(
                        f"Gate 4 失败：multi_asset_channels.json edition_id ({ma.get('edition_id')!r}) "
                        f"≠ market_state.json ({state_edition_id!r})"
                    )
                channels = ma.get("channels")
                if not isinstance(channels, list):
                    errs.append("Gate 4 失败：multi_asset_channels.json 须包含 channels 数组")
                else:
                    if len(channels) < len(req_channels):
                        errs.append(
                            f"Gate 4 失败：multi_asset_channels.json 渠道数不足 ({len(channels)} < {len(req_channels)})"
                        )
                    seen_ids: set[str] = set()
                    for idx, ch in enumerate(channels):
                        if not isinstance(ch, dict):
                            errs.append(f"Gate 4 失败：multi_asset_channels.json channels[{idx}] 须为对象")
                            continue
                        cid_raw = ch.get("id")
                        if not isinstance(cid_raw, str) or not cid_raw.strip():
                            errs.append(f"Gate 4 失败：multi_asset_channels.json channels[{idx}] 缺少非空 id")
                            cid = f"#{idx}"
                        else:
                            cid = cid_raw.strip()
                            if cid in seen_ids:
                                errs.append(f"Gate 4 失败：multi_asset_channels.json 存在重复渠道 id: {cid}")
                            seen_ids.add(cid)
                        if not isinstance(ch.get("name"), str) or not ch["name"].strip():
                            errs.append(f"Gate 4 失败：multi_asset_channels.json channels[{idx}]({cid}) 缺少非空 name")
                        elif not is_synthetic_small_pool and cid == "qdii_mrf" and not ch["name"].strip().startswith("QDII"):
                            errs.append(
                                f"Gate 4 失败：multi_asset_channels.json 渠道 qdii_mrf 名称须以 'QDII' 开头（当前为 {ch['name'].strip()!r}）"
                            )
                        kms = ch.get("key_metrics")
                        if not isinstance(kms, list) or not kms:
                            errs.append(f"Gate 4 失败：multi_asset_channels.json channels[{idx}]({cid}) 缺少非空 key_metrics")
                        else:
                            for ki, km in enumerate(kms):
                                if (
                                    not isinstance(km, dict)
                                    or not isinstance(km.get("label"), str) or not km["label"].strip()
                                    or not isinstance(km.get("value"), str) or not km["value"].strip()
                                ):
                                    errs.append(
                                        f"Gate 4 失败：multi_asset_channels.json channels[{idx}]({cid}).key_metrics[{ki}] 缺少非空 label/value"
                                    )
                        prods = ch.get("products")
                        if not isinstance(prods, list) or not prods:
                            errs.append(f"Gate 4 失败：multi_asset_channels.json channels[{idx}]({cid}) 缺少非空 products")
                        else:
                            for pi, prod in enumerate(prods):
                                if not isinstance(prod, dict):
                                    errs.append(f"Gate 4 失败：multi_asset_channels.json channels[{idx}]({cid}).products[{pi}] 须为对象")
                                    continue
                                for pf in ("code", "name", "metric", "fee", "note"):
                                    pv = prod.get(pf)
                                    if not isinstance(pv, str) or not pv.strip():
                                        errs.append(
                                            f"Gate 4 失败：multi_asset_channels.json channels[{idx}]({cid}).products[{pi}] 缺少非空 {pf}"
                                        )
                                pcode = str(prod.get("code", ""))
                                if _MA_RESTRICTED_CODES_RE.search(pcode):
                                    ctx = f"{prod.get('name', '')} {prod.get('note', '')}"
                                    if not _MA_RESTRICTED_WARN_RE.search(ctx):
                                        errs.append(
                                            f"Gate 4 失败：multi_asset_channels.json channels[{idx}]({cid}).products[{pi}] "
                                            f"未带暂停/退市/避坑警示直接推荐受限代码 {pcode!r}"
                                        )
                        rules = ch.get("rules_and_redlines")
                        if not isinstance(rules, list) or not rules or any(
                            not isinstance(r, str) or not r.strip() for r in rules
                        ):
                            errs.append(f"Gate 4 失败：multi_asset_channels.json channels[{idx}]({cid}) 缺少非空 rules_and_redlines")
                    missing_ch = [cid for cid in req_channels if cid not in seen_ids]
                    if missing_ch:
                        errs.append(f"Gate 4 失败：multi_asset_channels.json 缺少必填核心渠道 ID: {missing_ch}")

                templates = ma.get("allocation_templates")
                if templates is not None:
                    if not isinstance(templates, list):
                        errs.append("Gate 4 失败：multi_asset_channels.json allocation_templates 须为数组")
                    else:
                        for ti, tpl in enumerate(templates):
                            if not isinstance(tpl, dict) or not isinstance(tpl.get("slices"), list) or not tpl["slices"]:
                                errs.append(f"Gate 4 失败：multi_asset_channels.json allocation_templates[{ti}] 缺少非空 slices")
                                continue
                            exact_pcts: list[float] = []
                            has_range_pct = False
                            for sl in tpl["slices"]:
                                if not isinstance(sl, dict):
                                    continue
                                w_str = str(sl.get("weight", "")).strip()
                                m_exact = _EXACT_PCT_RE.fullmatch(w_str)
                                if m_exact:
                                    exact_pcts.append(float(m_exact.group(1)))
                                elif _RANGE_PCT_RE.search(w_str):
                                    has_range_pct = True
                            if len(exact_pcts) >= 2 and not has_range_pct and abs(sum(exact_pcts) - 100.0) > 0.01:
                                errs.append(
                                    f"Gate 4 失败：multi_asset_channels.json allocation_templates[{ti}]({tpl.get('id')}) "
                                    f"精确权重之和={sum(exact_pcts):.2f}% ≠ 100%"
                                )

                for jpath, sval in _walk_json_strings(ma, "multi_asset_channels.json"):
                    hits = _BANNED_INTERNAL_RE.findall(sval)
                    if hits:
                        errs.append(f"Gate 4 失败：{jpath} 泄露内部词: {sorted(set(hits))}")
                    errs.extend(_scan_text_for_crypto_buy(jpath, sval))
                    if not jpath.endswith(".code"):
                        for m_rc in _MA_RESTRICTED_CODES_RE.finditer(sval):
                            win = sval[max(0, m_rc.start() - 40) : min(len(sval), m_rc.end() + 40)]
                            if not _MA_RESTRICTED_WARN_RE.search(win):
                                errs.append(
                                    f"Gate 4 失败：{jpath} 未带暂停/退市/避坑警示提及受限代码 {m_rc.group(0)} -> {win!r}"
                                )
                                break

    # 2. etf_universe.json (>= 140 ETFs in production; >= 100 in small synthetic test pools, self-consistent counters, valid enums, zero markup/internal leaks)
    if not ETF_UNIVERSE_PATH.exists():
        if require_presence:
            errs.append("Gate 4 失败：缺少 state/etf_universe.json")
    else:
        try:
            eu = json.loads(ETF_UNIVERSE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errs.append(f"Gate 4 失败：etf_universe.json 解析失败: {exc}")
        else:
            if not isinstance(eu, dict):
                errs.append("Gate 4 失败：etf_universe.json 根元素须为对象")
            else:
                if state_edition_id and eu.get("edition_id") != state_edition_id:
                    errs.append(
                        f"Gate 4 失败：etf_universe.json edition_id ({eu.get('edition_id')!r}) "
                        f"≠ market_state.json ({state_edition_id!r})"
                    )
                etfs = eu.get("etfs")
                if not isinstance(etfs, list):
                    errs.append("Gate 4 失败：etf_universe.json 须包含 etfs 数组")
                else:
                    if len(etfs) < min_etf_count:
                        errs.append(f"Gate 4 失败：etf_universe.json 收录数量不足 ({len(etfs)} < {min_etf_count})")
                    if type(eu.get("total_etfs")) is not int or eu.get("total_etfs") != len(etfs):
                        errs.append(
                            f"Gate 4 失败：etf_universe.json total_etfs ({eu.get('total_etfs')!r}) ≠ len(etfs) ({len(etfs)})"
                        )
                    seen_codes: set[str] = set()
                    mkt_counter: Counter[str] = Counter()
                    ch_counter: Counter[str] = Counter()
                    ac_counter: Counter[str] = Counter()
                    reg_counter: Counter[str] = Counter()
                    for idx, item in enumerate(etfs):
                        if not isinstance(item, dict):
                            errs.append(f"Gate 4 失败：etf_universe.json etfs[{idx}] 须为对象")
                            continue
                        for field in _ETF_REQUIRED_STR_FIELDS:
                            val = item.get(field)
                            if not isinstance(val, str) or not val.strip():
                                errs.append(f"Gate 4 失败：etf_universe.json etfs[{idx}]({item.get('code')}) 缺少非空 {field}")
                            elif _DOSSIER_RAW_MARKUP_RE.search(val):
                                errs.append(f"Gate 4 失败：etf_universe.json etfs[{idx}]({item.get('code')}).{field} 残留原始 Markdown/HTML 标记")
                        code = item.get("code")
                        if isinstance(code, str) and code.strip():
                            ck = _normalize_etf_code(code)
                            if ck in seen_codes:
                                errs.append(f"Gate 4 失败：etf_universe.json 存在重复代码 {ck} ({code.strip()})")
                            seen_codes.add(ck)
                        mkt_v = str(item.get("market", "")).strip()
                        if mkt_v:
                            mkt_counter[mkt_v] += 1
                            if mkt_v not in _ETF_ALLOWED_MARKETS:
                                errs.append(f"Gate 4 失败：etf_universe.json etfs[{idx}]({code}).market 非法枚举 ({mkt_v!r})")
                        ch_v = str(item.get("channel", "")).strip()
                        if ch_v:
                            ch_counter[ch_v] += 1
                            if ch_v not in _ETF_ALLOWED_CHANNELS:
                                errs.append(f"Gate 4 失败：etf_universe.json etfs[{idx}]({code}).channel 非法枚举 ({ch_v!r})")
                        ac_raw = item.get("asset_class")
                        if "asset_class" in item and ac_raw is not None:
                            ac_v = ac_raw.strip() if isinstance(ac_raw, str) else ""
                            if ac_v not in _ETF_ALLOWED_ASSET_CLASSES:
                                errs.append(
                                    f"Gate 4 失败：etf_universe.json etfs[{idx}]({code}).asset_class 非法枚举 ({ac_raw!r})"
                                )
                            else:
                                ac_counter[ac_v] += 1
                        elif not is_synthetic_small_pool:
                            errs.append(f"Gate 4 失败：etf_universe.json etfs[{idx}]({code}) 缺少必填 asset_class")
                        reg_raw = item.get("region")
                        if "region" in item and reg_raw is not None:
                            reg_v = reg_raw.strip() if isinstance(reg_raw, str) else ""
                            if reg_v not in _ETF_ALLOWED_REGIONS:
                                errs.append(
                                    f"Gate 4 失败：etf_universe.json etfs[{idx}]({code}).region 非法枚举 ({reg_raw!r})"
                                )
                            else:
                                reg_counter[reg_v] += 1
                        elif not is_synthetic_small_pool:
                            errs.append(f"Gate 4 失败：etf_universe.json etfs[{idx}]({code}) 缺少必填 region")
                        if "premium_status" in item and item["premium_status"] not in _ETF_ALLOWED_PREMIUM_STATUSES:
                            errs.append(
                                f"Gate 4 失败：etf_universe.json etfs[{idx}]({code}).premium_status 非法枚举 ({item['premium_status']!r})"
                            )
                        elif item.get("premium_status") == "high_risk" and str(item.get("action_role", "")).strip() != "高危回避":
                            errs.append(
                                f"Gate S4 失败：etf_universe.json etfs[{idx}]({code}) premium_status='high_risk' "
                                f"须配 action_role='高危回避'（当前为 {item.get('action_role')!r}）"
                            )
                        # Internal fee_total_pct vs fee_num consistency (abs <= 0.005)
                        ft_str = str(item.get("fee_total_pct", ""))
                        m_ft = _PCT_NUM_RE.search(ft_str)
                        f_num_raw = item.get("fee_num")
                        if f_num_raw is not None:
                            if type(f_num_raw) not in (int, float) or not isfinite(f_num_raw):
                                errs.append(f"Gate 4 失败：etf_universe.json etfs[{idx}]({code}).fee_num 非法数值 ({f_num_raw!r})")
                            elif m_ft is not None and abs(float(m_ft.group(1)) - float(f_num_raw)) > 0.005:
                                errs.append(
                                    f"Gate 4 失败：etf_universe.json ({code}) fee_total_pct ({ft_str!r}) "
                                    f"与 fee_num ({f_num_raw}) 偏离超过 0.005%"
                                )
                            if isinstance(code, str) and code.strip() and type(f_num_raw) in (int, float) and isfinite(f_num_raw):
                                cu = code.strip().upper()
                                base_c = _normalize_etf_code(cu)
                                etf_fee_ssot[cu] = (cu, float(f_num_raw))
                                etf_fee_ssot.setdefault(base_c, (cu, float(f_num_raw)))
                        elif m_ft is not None and isinstance(code, str) and code.strip():
                            cu = code.strip().upper()
                            base_c = _normalize_etf_code(cu)
                            etf_fee_ssot[cu] = (cu, float(m_ft.group(1)))
                            etf_fee_ssot.setdefault(base_c, (cu, float(m_ft.group(1))))

                        # Intra-record sibling date consistency: premium_note MM/DD close/change vs earlier yield_or_pe MM/DD
                        pn_str = str(item.get("premium_note", ""))
                        yop_str = str(item.get("yield_or_pe", ""))
                        m_pn_dt = _ETF_PREM_DATE_RE.search(pn_str)
                        m_yop_dt = _ETF_YOP_LEAD_DATE_RE.match(yop_str)
                        if m_pn_dt and m_yop_dt:
                            pm, pd = int(m_pn_dt.group(1)), int(m_pn_dt.group(2))
                            ym, yd = int(m_yop_dt.group(1)), int(m_yop_dt.group(2))
                            if (
                                1 <= pm <= 12
                                and 1 <= ym <= 12
                                and 1 <= pd <= 31
                                and 1 <= yd <= 31
                                and ((pm == ym and yd < pd) or ((pm - ym) % 12 in (1, 2)))
                            ):
                                errs.append(
                                    f"Gate 4 失败：etf_universe.json ({code}) 字段日期未同步："
                                    f"premium_note 已更新至 {pm}/{pd}，但 yield_or_pe 仍停留 {ym}/{yd}"
                                )
                    cbm = eu.get("counts_by_market")
                    if not isinstance(cbm, dict) or cbm != dict(mkt_counter):
                        errs.append(
                            f"Gate 4 失败：etf_universe.json counts_by_market ({cbm}) 与实表汇总 ({dict(mkt_counter)}) 不一致"
                        )
                    cbc = eu.get("counts_by_channel")
                    if not isinstance(cbc, dict) or cbc != dict(ch_counter):
                        errs.append(
                            f"Gate 4 失败：etf_universe.json counts_by_channel ({cbc}) 与实表汇总 ({dict(ch_counter)}) 不一致"
                        )
                    if "counts_by_asset_class" in eu or not is_synthetic_small_pool:
                        cbac = eu.get("counts_by_asset_class")
                        if not isinstance(cbac, dict) or cbac != dict(ac_counter):
                            errs.append(
                                f"Gate 4 失败：etf_universe.json counts_by_asset_class ({cbac}) 与实表汇总 ({dict(ac_counter)}) 不一致"
                            )
                    if "counts_by_region" in eu or not is_synthetic_small_pool:
                        cbr = eu.get("counts_by_region")
                        if not isinstance(cbr, dict) or cbr != dict(reg_counter):
                            errs.append(
                                f"Gate 4 失败：etf_universe.json counts_by_region ({cbr}) 与实表汇总 ({dict(reg_counter)}) 不一致"
                            )
                for jpath, sval in _walk_json_strings(eu, "etf_universe.json"):
                    hits = _BANNED_INTERNAL_RE.findall(sval)
                    if hits:
                        errs.append(f"Gate 4 失败：{jpath} 泄露内部词: {sorted(set(hits))}")
                    errs.extend(_scan_text_for_crypto_buy(jpath, sval))
                    errs.extend(_check_retracted_facts(jpath, sval))
                    if enforce_g5_g7 and state_ed_date:
                        errs.extend(_check_shfe_night_close(jpath, sval))
                        errs.extend(_check_tense_drift(jpath, sval, state_ed_date))
                        errs.extend(_check_year_end_countdown(jpath, sval, state_ed_date))
                        for m_iopv in _BARE_IOPV_RE.finditer(sval):
                            win = sval[max(0, m_iopv.start() - 20) : min(len(sval), m_iopv.end() + 20)]
                            if not _IOPV_GLOSS_RE.search(win):
                                errs.append(
                                    f"Gate G5 失败：{jpath} 出现未配白话释义（参考净值/实时净值/盘中净值）的裸 IOPV -> {win!r}"
                                )
                                break
                if enforce_g5_g7 and isinstance(etfs, list):
                    for idx, item in enumerate(etfs):
                        if not isinstance(item, dict):
                            continue
                        code = item.get("code", f"#{idx}")
                        all_txt = " ".join(v for v in item.values() if isinstance(v, str))
                        is_high_risk_or_halted = item.get("premium_status") == "high_risk" or ("暂停申购" in all_txt)
                        if is_high_risk_or_halted:
                            for m_rs in _RESTORE_SUB_REDEEM_RE.finditer(all_txt):
                                win = all_txt[max(0, m_rs.start() - 24) : min(len(all_txt), m_rs.end() + 24)]
                                if not _RESTORE_SAFE_QUAL_RE.search(win):
                                    errs.append(
                                        f"Gate G5 失败：etf_universe.json ({code}) 为高风险/暂停申购标的，"
                                        f"严禁笼统写「恢复申赎」（若仅开赎回须注明「仅恢复赎回」）-> {win!r}"
                                    )
                                    break

    # Cross-DB check: multi_asset_channels.json products[].fee vs etf_universe.json SSOT
    if isinstance(ma_loaded, dict) and etf_fee_ssot:
        for ch in ma_loaded.get("channels", []) if isinstance(ma_loaded.get("channels"), list) else []:
            if not isinstance(ch, dict):
                continue
            cid = str(ch.get("id", "?"))
            for prod in ch.get("products", []) if isinstance(ch.get("products"), list) else []:
                if not isinstance(prod, dict):
                    continue
                pcode = str(prod.get("code", ""))
                pfee = str(prod.get("fee", ""))
                pfee_cleaned = _FEE_EXCLUDE_SPAN_RE.sub("", pfee)
                pfee_nums = [float(x) for x in _PCT_NUM_RE.findall(pfee_cleaned)]
                if not pfee_nums:
                    continue
                matched_etfs: list[tuple[str, float]] = []
                seen_norm: set[str] = set()
                for tok in _ETF_CODE_TOKEN_RE.findall(pcode):
                    tu = tok.upper()
                    tn = _normalize_etf_code(tu)
                    if tn in seen_norm:
                        continue
                    if tu in etf_fee_ssot:
                        matched_etfs.append(etf_fee_ssot[tu])
                        seen_norm.add(tn)
                    elif tn in etf_fee_ssot:
                        matched_etfs.append(etf_fee_ssot[tn])
                        seen_norm.add(tn)
                if not matched_etfs:
                    continue
                distinct_fees = sorted({round(f, 4) for _, f in matched_etfs})
                if len(distinct_fees) == 1 or (distinct_fees[-1] - distinct_fees[0]) <= 0.005:
                    target_fee = distinct_fees[0]
                    if not any(abs(x - target_fee) <= 0.005 for x in pfee_nums):
                        errs.append(
                            f"Gate 4 失败：multi_asset_channels.json ({cid}:{pcode}) 费率 {pfee!r} "
                            f"与 etf_universe.json ({matched_etfs[0][0]}={target_fee:.2f}%) 漂移"
                        )
                else:
                    lo_f, hi_f = distinct_fees[0], distinct_fees[-1]
                    has_lo = any(abs(x - lo_f) <= 0.005 for x in pfee_nums)
                    has_hi = any(abs(x - hi_f) <= 0.005 for x in pfee_nums)
                    if not (has_lo and has_hi):
                        detail_str = "/".join(f"{c}={f:.2f}%" for c, f in matched_etfs)
                        errs.append(
                            f"Gate 4 失败：multi_asset_channels.json ({cid}:{pcode}) 多只 ETF 混合费率行 "
                            f"{pfee!r} 须同时列明区间或各自费率（SSOT: {detail_str}）"
                        )

    if isinstance(ma_loaded, dict):
        for jpath, sval in _walk_json_strings(ma_loaded, "multi_asset_channels.json"):
            errs.extend(_check_retracted_facts(jpath, sval))
            if enforce_g5_g7 and state_ed_date:
                errs.extend(_check_shfe_night_close(jpath, sval))
                errs.extend(_check_tense_drift(jpath, sval, state_ed_date))
                errs.extend(_check_year_end_countdown(jpath, sval, state_ed_date))

    # 3. deep_dossiers.json (1:1 alignment with 3 flagship Appendix 2 tables + anti-template-copy guard)
    if not DEEP_DOSSIERS_PATH.exists():
        if require_presence:
            errs.append("Gate 4 失败：缺少 state/deep_dossiers.json")
    else:
        try:
            dd = json.loads(DEEP_DOSSIERS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errs.append(f"Gate 4 失败：deep_dossiers.json 解析失败: {exc}")
        else:
            if not isinstance(dd, dict):
                errs.append("Gate 4 失败：deep_dossiers.json 根元素须为对象")
            else:
                if state_edition_id and dd.get("edition_id") != state_edition_id:
                    errs.append(
                        f"Gate 4 失败：deep_dossiers.json edition_id ({dd.get('edition_id')!r}) "
                        f"≠ market_state.json ({state_edition_id!r})"
                    )
                dossiers = dd.get("dossiers")
                if not isinstance(dossiers, dict):
                    errs.append("Gate 4 失败：deep_dossiers.json 须包含 dossiers 对象")
                else:
                    if type(dd.get("total_stocks")) is not int or dd.get("total_stocks") != len(dossiers):
                        errs.append(
                            f"Gate 4 失败：deep_dossiers.json total_stocks ({dd.get('total_stocks')!r}) ≠ len(dossiers) ({len(dossiers)})"
                        )
                    if len(dossiers) != expected_pool:
                        errs.append(f"Gate 4 失败：deep_dossiers.json 条目数 ({len(dossiers)}) ≠ 三市股票池总数 ({expected_pool})")

                    # 1:1 key alignment against the 3 flagship Appendix 2 tables
                    flagship_keys: set[str] = set()
                    all_flagships_parsed = True
                    for mkt in MARKETS:
                        try:
                            slug = _read_flagship_meta(mkt)["period_slug"]
                            fp = BASE_DIR / f"{mkt}_market_report_{slug}.md"
                            if not fp.is_file():
                                all_flagships_parsed = False
                                break
                            mkt_keys = _extract_appendix2_stock_keys(fp.read_text(encoding="utf-8"), mkt)
                            if not mkt_keys:
                                all_flagships_parsed = False
                                break
                            flagship_keys |= mkt_keys
                        except (OSError, ValueError):
                            all_flagships_parsed = False
                            break
                    if all_flagships_parsed and flagship_keys:
                        dossier_keys = set(dossiers.keys())
                        missing_keys = sorted(flagship_keys - dossier_keys)
                        extra_keys = sorted(dossier_keys - flagship_keys)
                        if missing_keys:
                            errs.append(
                                f"Gate 4 失败：deep_dossiers.json 缺失旗舰附表二标的 ({len(missing_keys)} 只): {missing_keys[:8]}"
                            )
                        if extra_keys:
                            errs.append(
                                f"Gate 4 失败：deep_dossiers.json 含旗舰附表二之外的多余键 ({len(extra_keys)} 只): {extra_keys[:8]}"
                            )

                    template_counts: dict[tuple[str, str], Counter[str]] = {}
                    for key, entry in dossiers.items():
                        if not isinstance(entry, dict):
                            errs.append(f"Gate 4 失败：deep_dossiers.json[{key}] 须为对象")
                            continue
                        mkt_prefix = str(key).split(":", 1)[0]
                        if enforce_g5_g7 and state_ed_date:
                            bn = entry.get("baseline_note")
                            if isinstance(bn, str):
                                errs.extend(_check_shfe_night_close(f"deep_dossiers.json[{key}].baseline_note", bn))
                                errs.extend(_check_tense_drift(f"deep_dossiers.json[{key}].baseline_note", bn, state_ed_date))
                                errs.extend(_check_year_end_countdown(f"deep_dossiers.json[{key}].baseline_note", bn, state_ed_date))
                        for dim in _DOSSIER_DIMENSIONS:
                            val = entry.get(dim)
                            if not isinstance(val, str) or not val.strip():
                                errs.append(f"Gate 4 失败：deep_dossiers.json[{key}] 缺少非空维度 {dim}")
                                continue
                            if _DOSSIER_RAW_MARKUP_RE.search(val):
                                errs.append(f"Gate 4 失败：deep_dossiers.json[{key}].{dim} 残留原始 Markdown/HTML 标记")
                            hits = _BANNED_INTERNAL_RE.findall(val)
                            if hits:
                                errs.append(f"Gate 4 失败：deep_dossiers.json[{key}].{dim} 泄露内部词: {sorted(set(hits))}")
                            errs.extend(_check_retracted_facts(f"deep_dossiers.json[{key}].{dim}", val))
                            if enforce_g5_g7 and state_ed_date:
                                errs.extend(_check_shfe_night_close(f"deep_dossiers.json[{key}].{dim}", val))
                                errs.extend(_check_tense_drift(f"deep_dossiers.json[{key}].{dim}", val, state_ed_date))
                                errs.extend(_check_year_end_countdown(f"deep_dossiers.json[{key}].{dim}", val, state_ed_date))
                            if dim in ("catalysts", "bear_case"):
                                norm_txt = re.sub(r"\s+", " ", val.strip())
                                bucket = template_counts.setdefault((mkt_prefix, dim), Counter())
                                bucket[norm_txt] += 1
                    for (mkt_prefix, dim), counter in sorted(template_counts.items()):
                        for text_sample, cnt in counter.items():
                            if cnt > 10:
                                errs.append(
                                    f"Gate 4 失败：deep_dossiers.json ({mkt_prefix}) 存在 {cnt} 只股票完全复制粘贴相同 "
                                    f"{dim} 模板（上限 10 只）-> {text_sample[:42]!r}"
                                )

                    if enforce_g5_g7:
                        errs.extend(_check_dossiers_ah_and_dividends(dossiers, state))
                for jpath, sval in _walk_json_strings(dd, "deep_dossiers.json"):
                    errs.extend(_scan_text_for_crypto_buy(jpath, sval))

    # 4. policy_calendar.json (validated whenever present; >=14-day horizon enforced on live production state)
    if POLICY_CALENDAR_PATH.exists():
        errs.extend(
            _check_policy_calendar(
                state_edition_id,
                state_ed_date,
                require_horizon=require_presence,
                enforce_g5_g7=enforce_g5_g7,
            )
        )
    return errs


def _is_strict_https_url(value: object) -> bool:
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        return (
            parsed.scheme == "https"
            and bool(host)
            and "." in host
            and not host.startswith(".")
            and not host.endswith(".")
            and parsed.username is None
        )
    except ValueError:
        return False


def _check_policy_calendar(
    state_edition_id: str | None,
    state_ed_date: str | None,
    *,
    require_horizon: bool,
    enforce_g5_g7: bool,
) -> list[str]:
    """Validate equity/state/policy_calendar.json schema, enums, edition_id parity, horizon, and hygiene."""
    errs: list[str] = []
    try:
        pc = json.loads(POLICY_CALENDAR_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"Gate 4 失败：policy_calendar.json 解析失败: {exc}"]
    if not isinstance(pc, dict):
        return ["Gate 4 失败：policy_calendar.json 根元素须为对象"]

    if not isinstance(pc.get("schema_version"), str) or not pc["schema_version"].strip():
        errs.append("Gate 4 失败：policy_calendar.json 缺少非空 schema_version")
    if state_edition_id and pc.get("edition_id") != state_edition_id:
        errs.append(
            f"Gate 4 失败：policy_calendar.json edition_id ({pc.get('edition_id')!r}) "
            f"≠ market_state.json ({state_edition_id!r})"
        )
    as_of_raw = pc.get("as_of_cst")
    try:
        if not isinstance(as_of_raw, str) or not as_of_raw.strip():
            raise ValueError("missing")
        as_of_dt = datetime.fromisoformat(as_of_raw.strip())
        if as_of_dt.utcoffset() != BEIJING.utcoffset(as_of_dt):
            raise ValueError("offset != +08:00")
    except ValueError:
        errs.append(f"Gate 4 失败：policy_calendar.json as_of_cst 须为有效 +08:00 时间戳 ({as_of_raw!r})")
    hdays = pc.get("horizon_days")
    if type(hdays) is not int or hdays < _POLICY_CAL_MIN_HORIZON_DAYS:
        errs.append(f"Gate 4 失败：policy_calendar.json horizon_days 须为 >= {_POLICY_CAL_MIN_HORIZON_DAYS} 的整数 ({hdays!r})")

    briefs = pc.get("policy_briefs")
    if not isinstance(briefs, list):
        errs.append("Gate 4 失败：policy_calendar.json 须包含 policy_briefs 数组")
    else:
        seen_bids: set[str] = set()
        for idx, b in enumerate(briefs):
            if not isinstance(b, dict):
                errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}] 须为对象")
                continue
            bid = str(b.get("id", "")).strip()
            if not bid:
                errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}] 缺少非空 id")
            elif bid in seen_bids:
                errs.append(f"Gate 4 失败：policy_calendar.json 存在重复 policy_brief id: {bid}")
            else:
                seen_bids.add(bid)
            for fk in ("date_cst", "region", "category", "impact_tier", "authority", "headline", "summary", "market_impact"):
                val = b.get(fk)
                if not isinstance(val, str) or not val.strip():
                    errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}]({bid}) 缺少非空 {fk}")
            bd_raw = b.get("date_cst")
            if isinstance(bd_raw, str) and bd_raw.strip():
                try:
                    if not _DATE_ISO_RE.fullmatch(bd_raw.strip()):
                        raise ValueError
                    date.fromisoformat(bd_raw.strip())
                except ValueError:
                    errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}]({bid}).date_cst 日期非法 ({bd_raw!r})")
            if isinstance(b.get("region"), str) and b["region"].strip() and b["region"].strip() not in _POLICY_CAL_ALLOWED_REGIONS:
                errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}]({bid}).region 非法枚举 ({b['region']!r})")
            if isinstance(b.get("category"), str) and b["category"].strip() and b["category"].strip() not in _POLICY_CAL_ALLOWED_CATEGORIES:
                errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}]({bid}).category 非法枚举 ({b['category']!r})")
            if isinstance(b.get("impact_tier"), str) and b["impact_tier"].strip() and b["impact_tier"].strip() not in _POLICY_CAL_ALLOWED_TIERS:
                errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}]({bid}).impact_tier 非法枚举 ({b['impact_tier']!r})")
            aff = b.get("affected_markets")
            if not isinstance(aff, list) or not aff or any(not isinstance(m, str) or not m.strip() for m in aff):
                errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}]({bid}) 缺少非空 affected_markets 数组")
            else:
                bad_mkts = sorted({m.strip() for m in aff if m.strip() not in _POLICY_CAL_ALLOWED_MARKETS})
                if bad_mkts:
                    errs.append(
                        f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}]({bid}).affected_markets 非法枚举 ({bad_mkts})"
                    )
            if "source_url" in b and b["source_url"] is not None and not _is_strict_https_url(b["source_url"]):
                errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}]({bid}).source_url 须为有效 HTTPS 链接")
            if "home_featured" in b and b["home_featured"] is not None and type(b["home_featured"]) is not bool:
                errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}]({bid}).home_featured 须为布尔值")
            if "time_cst" in b and b["time_cst"] is not None and (not isinstance(b["time_cst"], str) or not b["time_cst"].strip()):
                errs.append(f"Gate 4 失败：policy_calendar.json policy_briefs[{idx}]({bid}).time_cst 须为非空字符串")

    events = pc.get("events")
    max_end_d: date | None = None
    if not isinstance(events, list) or not events:
        errs.append("Gate 4 失败：policy_calendar.json 须包含非空 events 数组")
    else:
        seen_eids: set[str] = set()
        for idx, ev in enumerate(events):
            if not isinstance(ev, dict):
                errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}] 须为对象")
                continue
            eid = str(ev.get("event_id", "")).strip()
            if not eid:
                errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}] 缺少非空 event_id")
            elif eid in seen_eids:
                errs.append(f"Gate 4 失败：policy_calendar.json 存在重复 event_id: {eid}")
            else:
                seen_eids.add(eid)
            for fk in (
                "date_cst", "end_date_cst", "date_precision", "time_cst",
                "region", "category", "impact_tier", "title",
                "expected_consensus", "market_transmission", "pre_event_stance", "source_url",
            ):
                val = ev.get(fk)
                if not isinstance(val, str) or not val.strip():
                    errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}) 缺少非空 {fk}")
            start_d = end_d = None
            sd_raw = ev.get("date_cst")
            if isinstance(sd_raw, str) and sd_raw.strip():
                try:
                    if not _DATE_ISO_RE.fullmatch(sd_raw.strip()):
                        raise ValueError
                    start_d = date.fromisoformat(sd_raw.strip())
                except ValueError:
                    errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}).date_cst 日期非法 ({sd_raw!r})")
            ed_raw = ev.get("end_date_cst")
            if isinstance(ed_raw, str) and ed_raw.strip():
                try:
                    if not _DATE_ISO_RE.fullmatch(ed_raw.strip()):
                        raise ValueError
                    end_d = date.fromisoformat(ed_raw.strip())
                except ValueError:
                    errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}).end_date_cst 日期非法 ({ed_raw!r})")
            if start_d is not None and end_d is not None:
                if end_d < start_d:
                    errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}) end_date_cst 早于 date_cst")
                if max_end_d is None or end_d > max_end_d:
                    max_end_d = end_d
            if isinstance(ev.get("date_precision"), str) and ev["date_precision"].strip() and ev["date_precision"].strip() not in _POLICY_CAL_ALLOWED_PRECISIONS:
                errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}).date_precision 非法枚举 ({ev['date_precision']!r})")
            if isinstance(ev.get("region"), str) and ev["region"].strip() and ev["region"].strip() not in _POLICY_CAL_ALLOWED_REGIONS:
                errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}).region 非法枚举 ({ev['region']!r})")
            if isinstance(ev.get("category"), str) and ev["category"].strip() and ev["category"].strip() not in _POLICY_CAL_ALLOWED_CATEGORIES:
                errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}).category 非法枚举 ({ev['category']!r})")
            if isinstance(ev.get("impact_tier"), str) and ev["impact_tier"].strip() and ev["impact_tier"].strip() not in _POLICY_CAL_ALLOWED_TIERS:
                errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}).impact_tier 非法枚举 ({ev['impact_tier']!r})")
            aff = ev.get("affected_markets")
            if not isinstance(aff, list) or not aff or any(not isinstance(m, str) or not m.strip() for m in aff):
                errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}) 缺少非空 affected_markets 数组")
            else:
                bad_mkts = sorted({m.strip() for m in aff if m.strip() not in _POLICY_CAL_ALLOWED_MARKETS})
                if bad_mkts:
                    errs.append(
                        f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}).affected_markets 非法枚举 ({bad_mkts})"
                    )
            wt = ev.get("watch_triggers")
            if (
                not isinstance(wt, dict)
                or not isinstance(wt.get("upside_bull"), str) or not wt["upside_bull"].strip()
                or not isinstance(wt.get("downside_bear"), str) or not wt["downside_bear"].strip()
            ):
                errs.append(
                    f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}).watch_triggers 须含非空 upside_bull 与 downside_bear"
                )
            if not _is_strict_https_url(ev.get("source_url")):
                errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}).source_url 须为有效 HTTPS 链接")
            mwin = ev.get("monitor_window_min")
            if type(mwin) is not int or mwin < 0:
                errs.append(f"Gate 4 失败：policy_calendar.json events[{idx}]({eid}).monitor_window_min 须为非负整数 ({mwin!r})")

    if require_horizon and max_end_d is not None and state_ed_date:
        try:
            ref_d = date.fromisoformat(state_ed_date)
            covered_days = (max_end_d - ref_d).days
            if covered_days < _POLICY_CAL_MIN_HORIZON_DAYS:
                errs.append(
                    f"Gate 4 失败：policy_calendar.json 前瞻覆盖仅 {covered_days} 天（最远事件 {max_end_d}，须 ≥ {_POLICY_CAL_MIN_HORIZON_DAYS} 天）"
                )
        except ValueError:
            pass

    for jpath, sval in _walk_json_strings(pc, "policy_calendar.json", skip_keys=frozenset()):
        if _DOSSIER_RAW_MARKUP_RE.search(sval):
            errs.append(f"Gate 4 失败：{jpath} 残留原始 Markdown/HTML 标记")
        hits = _BANNED_INTERNAL_RE.findall(sval)
        if hits:
            errs.append(f"Gate 4 失败：{jpath} 泄露内部词: {sorted(set(hits))}")
        if _LOCAL_PATH_RE.search(sval):
            errs.append(f"Gate 4 失败：{jpath} 泄露本机文件系统路径")
        leaf_key = jpath.rsplit(".", 1)[-1].split("[", 1)[0]
        if leaf_key not in _POLICY_CAL_PROSE_SKIP_KEYS:
            m_tier = _BARE_IMPACT_TIER_RE.search(sval)
            if m_tier:
                errs.append(
                    f"Gate 4 失败：{jpath} 正文禁止裸露内部优先级代号 {m_tier.group(0)!r}（请改用纯中文「重磅/重要/关注」）"
                )
        for m_rc in RESTRICTED_CODES_RE.finditer(sval):
            win = sval[max(0, m_rc.start() - 40) : min(len(sval), m_rc.end() + 40)]
            if not RESTRICTED_WARN_RE.search(win):
                errs.append(
                    f"Gate 4 失败：{jpath} 提及受限代码 {m_rc.group(0)} 但 ±40 字内缺少暂停/限购/警示说明 -> {win!r}"
                )
                break
        errs.extend(_scan_text_for_crypto_buy(jpath, sval))
        errs.extend(_check_retracted_facts(jpath, sval))
        hk4 = _HK_4DIGIT_RE.findall(sval)
        if hk4:
            errs.append(f"Gate 4 失败：{jpath} 出现非法 4 位港股代码: {sorted(set(hk4))}")
        for m_iopv in _BARE_IOPV_RE.finditer(sval):
            win = sval[max(0, m_iopv.start() - 20) : min(len(sval), m_iopv.end() + 20)]
            if not _IOPV_GLOSS_RE.search(win):
                errs.append(
                    f"Gate G5 失败：{jpath} 出现未配白话释义（参考净值/实时净值/盘中净值）的裸 IOPV -> {win!r}"
                )
                break
        if enforce_g5_g7 and state_ed_date:
            errs.extend(_check_shfe_night_close(jpath, sval))
            errs.extend(_check_tense_drift(jpath, sval, state_ed_date))
            errs.extend(_check_year_end_countdown(jpath, sval, state_ed_date))
    return errs


def _check_dossiers_ah_and_dividends(dossiers: dict, state: dict | None) -> list[str]:
    """Gate G5: Global A/H benchmark check (±0.6pp) & A-share intra-dossier dividend drift (<= 0.15pp)."""
    errs: list[str] = []
    benchmarks = (
        state.get("cross_market_linkages", {}).get("ah_premium_radar", {}).get("benchmarks", [])
        if isinstance(state, dict) and isinstance(state.get("cross_market_linkages"), dict)
        and isinstance(state["cross_market_linkages"].get("ah_premium_radar"), dict)
        else []
    )
    if isinstance(benchmarks, list):
        for bm in benchmarks:
            if not isinstance(bm, dict):
                continue
            bm_ah = bm.get("ah_premium_pct")
            if type(bm_ah) not in (int, float) or not isfinite(bm_ah):
                continue
            a_code = str(bm.get("a", "")).strip()
            h_code = str(bm.get("h", "")).strip()
            for dk in (f"a-share:{a_code}", f"hk-stock:{h_code}"):
                entry = dossiers.get(dk)
                if not isinstance(entry, dict):
                    continue
                for fld in ("baseline_note", "valuation_anchor"):
                    txt = str(entry.get(fld, ""))
                    for m in _DOSSIER_AH_RE.finditer(txt):
                        pre_clause = re.split(r"[。！？；;，,]", txt[: m.start()])[-1]
                        post_head = txt[m.end() : m.end() + 14]
                        if _DOSSIER_AH_HIST_CTX_RE.search(pre_clause) or re.match(
                            r"\s*(?:为|系|属)?\s*[（(]?\s*(?:历史中枢|历史均值|过去)", post_head
                        ):
                            continue
                        raw_lo, raw_hi = m.group(1), m.group(2)
                        lo = float(raw_lo)
                        hi = float(raw_hi) if raw_hi else lo
                        if _DOSSIER_AH_NEG_WORD_RE.search(m.group(0)):
                            if not raw_lo.startswith(("+", "-")):
                                lo = -abs(lo)
                            if raw_hi is None:
                                hi = lo
                            elif not raw_hi.startswith(("+", "-")):
                                hi = -abs(hi)
                        lo, hi = min(lo, hi), max(lo, hi)
                        dist = 0.0 if lo <= bm_ah <= hi else min(abs(bm_ah - lo), abs(bm_ah - hi))
                        if dist > 0.6:
                            errs.append(
                                f"Gate G5 失败：deep_dossiers.json[{dk}].{fld} AH 溢价 ({m.group(0)}) "
                                f"与 market_state 基准 ({bm_ah:+.1f}%) 偏离 {dist:.2f}pp (> 0.6pp)"
                            )

    for dk, entry in dossiers.items():
        if not str(dk).startswith("a-share:") or not isinstance(entry, dict):
            continue
        divs: list[tuple[str, float, float]] = []
        for fld in ("baseline_note", "valuation_anchor", "shareholder_flow", "financials"):
            txt = str(entry.get(fld, ""))
            for m in _DOSSIER_DIV_STRICT_RE.finditer(txt):
                clause_pre = re.split(r"[。！？；;，,（(]", txt[: m.start()])[-1]
                post_clause = re.split(r"[。！？；;，,]", txt[m.end() : m.end() + 12])[0]
                if _DOSSIER_DIV_QUAL_RE.search(clause_pre) or re.search(
                    r"(?:税后|扣税|港股通|H\s*股|离岸|中期|半年|特别|历史|净股息)", post_clause
                ):
                    continue
                lo = float(m.group(1))
                hi = float(m.group(2)) if m.group(2) else lo
                divs.append((fld, min(lo, hi), max(lo, hi)))
        if len(divs) >= 2:
            max_gap = max(
                max(0.0, divs[j][1] - divs[i][2], divs[i][1] - divs[j][2])
                for i in range(len(divs))
                for j in range(i + 1, len(divs))
            )
            if max_gap > 0.15:
                summary = ", ".join(f"{f}:{lo:g}%-{hi:g}%" if lo != hi else f"{f}:{lo:g}%" for f, lo, hi in divs)
                errs.append(
                    f"Gate G5 失败：deep_dossiers.json[{dk}] A 股内部股息率口径漂移 {max_gap:.2f}pp (> 0.15pp): {summary}"
                )
    return errs


def _is_num(val: object) -> bool:
    return type(val) in (int, float) and isfinite(val)


def _check_market_state_math(state: dict) -> list[str]:
    """Gate G6: Deterministic quantitative math checks on equity/state/market_state.json."""
    errs: list[str] = []
    mkts = state.get("markets") if isinstance(state.get("markets"), dict) else {}
    links = state.get("cross_market_linkages") if isinstance(state.get("cross_market_linkages"), dict) else {}
    rates = links.get("rates_fx_chain") if isinstance(links.get("rates_fx_chain"), dict) else {}
    erp_ruler = links.get("erp_ruler") if isinstance(links.get("erp_ruler"), dict) else {}
    a_m = mkts.get("a_share") if isinstance(mkts.get("a_share"), dict) else {}
    h_m = mkts.get("hk_stock") if isinstance(mkts.get("hk_stock"), dict) else {}
    u_m = mkts.get("us_stock") if isinstance(mkts.get("us_stock"), dict) else {}

    cgb10y = rates.get("cgb10y_pct") if _is_num(rates.get("cgb10y_pct")) else a_m.get("cgb10y_pct")
    us10y = rates.get("us10y_pct") if _is_num(rates.get("us10y_pct")) else u_m.get("us10y_pct")

    erp_specs = (
        ("a_share.erp_ttm_pct", a_m.get("erp_ttm_pct"), a_m.get("pe_ttm"), a_m.get("cgb10y_pct"), "csi300_erp_ttm_pct"),
        ("a_share.erp_fwd_pct", a_m.get("erp_fwd_pct"), a_m.get("pe_fwd"), a_m.get("cgb10y_pct"), "csi300_erp_fwd_pct"),
        ("hk_stock.erp_usd_anchor_ttm_pct", h_m.get("erp_usd_anchor_ttm_pct"), h_m.get("pe_ttm"), us10y, "hsi_erp_usd_ttm_pct"),
        ("hk_stock.erp_cny_anchor_ttm_pct", h_m.get("erp_cny_anchor_ttm_pct"), h_m.get("pe_ttm"), cgb10y, "hsi_erp_cny_ttm_pct"),
        ("hk_stock.erp_usd_anchor_fwd_pct", h_m.get("erp_usd_anchor_fwd_pct"), h_m.get("pe_fwd"), us10y, "hsi_erp_usd_fwd_pct"),
        ("hk_stock.erp_cny_anchor_fwd_pct", h_m.get("erp_cny_anchor_fwd_pct"), h_m.get("pe_fwd"), cgb10y, "hsi_erp_cny_fwd_pct"),
        ("us_stock.erp_ttm_pct", u_m.get("erp_ttm_pct"), u_m.get("pe_ttm"), u_m.get("us10y_pct"), "sp500_erp_ttm_pct"),
        ("us_stock.erp_fwd_pct", u_m.get("erp_fwd_pct"), u_m.get("pe_fwd"), u_m.get("us10y_pct"), "sp500_erp_fwd_pct"),
    )
    for lbl, erp_v, pe_v, yld_v, ruler_k in erp_specs:
        if _is_num(erp_v) and _is_num(pe_v) and pe_v > 0 and _is_num(yld_v):
            calc = (100.0 / float(pe_v)) - float(yld_v)
            if abs(float(erp_v) - calc) > 0.02:
                errs.append(
                    f"Gate G6 失败：market_state {lbl}={erp_v} 与 100/{pe_v}-{yld_v}={calc:.2f} 偏离 > 0.02pp"
                )
        ruler_v = erp_ruler.get(ruler_k)
        if _is_num(erp_v) and _is_num(ruler_v) and abs(float(erp_v) - float(ruler_v)) > 0.01:
            errs.append(
                f"Gate G6 失败：market_state {lbl}={erp_v} 与 erp_ruler.{ruler_k}={ruler_v} 不一致"
            )

    if _is_num(rates.get("cn_us_10y_spread_bp")) and _is_num(rates.get("cgb10y_pct")) and _is_num(rates.get("us10y_pct")):
        exp_sp = round((float(rates["cgb10y_pct"]) - float(rates["us10y_pct"])) * 100.0)
        if abs(float(rates["cn_us_10y_spread_bp"]) - exp_sp) > 1.0:
            errs.append(
                f"Gate G6 失败：market_state cn_us_10y_spread_bp={rates['cn_us_10y_spread_bp']} "
                f"与 round(({rates['cgb10y_pct']}-{rates['us10y_pct']})*100)={exp_sp} 偏离 > 1bp"
            )

    if _is_num(rates.get("sofr_hibor1m_carry_bp")) and _is_num(rates.get("sofr_pct")) and _is_num(rates.get("hibor_1m_pct")):
        exp_carry = (float(rates["sofr_pct"]) - float(rates["hibor_1m_pct"])) * 100.0
        if abs(float(rates["sofr_hibor1m_carry_bp"]) - exp_carry) > 0.5:
            errs.append(
                f"Gate G6 失败：market_state sofr_hibor1m_carry_bp={rates['sofr_hibor1m_carry_bp']} "
                f"与 ({rates['sofr_pct']}-{rates['hibor_1m_pct']})*100={exp_carry:.1f} 偏离 > 0.5bp"
            )

    if all(_is_num(u_m.get(k)) for k in ("equity_cap_pct", "cash_tbill_pct", "gold_hold_pct")):
        us_sum = float(u_m["equity_cap_pct"]) + float(u_m["cash_tbill_pct"]) + float(u_m["gold_hold_pct"])
        if abs(us_sum - 100.0) > 0.01:
            errs.append(
                f"Gate G6 失败：market_state us_stock 配置闭环合计={us_sum:g}% ≠ 100% "
                f"({u_m['equity_cap_pct']}+{u_m['cash_tbill_pct']}+{u_m['gold_hold_pct']})"
            )

    ah_radar = links.get("ah_premium_radar") if isinstance(links.get("ah_premium_radar"), dict) else {}
    locks = ah_radar.get("pe_physics_locks")
    if isinstance(locks, list):
        for lk in locks:
            if not isinstance(lk, dict):
                continue
            pa, ph, ahp = lk.get("a_pe_ttm"), lk.get("h_pe_ttm"), lk.get("ah_premium_pct")
            if _is_num(pa) and _is_num(ph) and ph > 0 and _is_num(ahp):
                diff = abs((float(pa) / float(ph)) - 1.0 - (float(ahp) / 100.0))
                if diff > 0.02:
                    errs.append(
                        f"Gate G6 失败：market_state pe_physics_locks ({lk.get('name')}) "
                        f"|{pa}/{ph}-1-{ahp}/100|={diff:.4f} > 0.02"
                    )
    return errs


def _closest_md_dt(mo: int, d: int, hh: int, mm: int, ref_dt: datetime) -> datetime | None:
    cands: list[datetime] = []
    for yr in (ref_dt.year - 1, ref_dt.year, ref_dt.year + 1):
        try:
            cands.append(datetime(yr, mo, d, hh, mm))
        except ValueError:
            continue
    if not cands:
        return None
    return min(cands, key=lambda dt: (abs((dt - ref_dt).days), abs((dt - ref_dt).total_seconds())))


def _parse_scorecard_due_dt(cell_text: str, ref_dt: datetime) -> datetime | None:
    plain = re.sub(r"<br\s*/?>", " ", cell_text, flags=re.IGNORECASE)
    plain = re.sub(r"[*`]", "", plain).strip()
    m_full = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2})", plain)
    if m_full:
        try:
            return datetime(*(int(g) for g in m_full.groups()))
        except ValueError:
            return None
    m_date = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)", plain)
    if m_date:
        try:
            y, mo, d = (int(g) for g in m_date.groups())
            return datetime(y, mo, d, 23, 59)
        except ValueError:
            return None
    m_md = re.search(r"(?<![0-9/])(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})", plain)
    if m_md:
        mo, d, hh, mm = (int(g) for g in m_md.groups())
        if 1 <= mo <= 12 and 1 <= d <= 31 and 0 <= hh <= 23 and 0 <= mm <= 59:
            return _closest_md_dt(mo, d, hh, mm, ref_dt)
        return None
    m_md_only = re.search(r"(?<![0-9/])(\d{1,2})/(\d{1,2})(?![0-9/]|(?:\s*(?:关|分|项|点|家|只)))", plain)
    if m_md_only:
        mo, d = int(m_md_only.group(1)), int(m_md_only.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return _closest_md_dt(mo, d, 23, 59, ref_dt)
    return None


def _reconcile_equity_scorecard(sc_text: str, *, as_of_dt: datetime | None = None) -> list[str]:
    """Reconcile equity/daily/SCORECARD.md header summary counts and check past-due ⏳ rows."""
    errs: list[str] = []
    if as_of_dt is None:
        m_asof = re.search(r"截至\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", sc_text)
        if m_asof:
            try:
                as_of_dt = datetime.strptime(m_asof.group(1), "%Y-%m-%d %H:%M")
            except ValueError:
                as_of_dt = None
    ref_naive = as_of_dt.replace(tzinfo=None) if as_of_dt is not None else None

    m_hdr = re.search(
        r"已到期\s*(\d+)\s*项（\s*✅\s*兑现\s*(\d+)\s*[｜|]\s*⚠️\s*部分兑现\s*(\d+)\s*[｜|]\s*"
        r"❌\s*证伪\s*(\d+)\s*[｜|]\s*条件未触发\s*(\d+)\s*）\s*[，,]\s*持续追踪\s*(\d+)\s*项",
        sc_text,
    )
    sec1_m = re.search(r"^##\s*一、[^\n]*\n(.*?)(?=^##\s*二、|\Z)", sc_text, flags=re.MULTILINE | re.DOTALL)
    tbl_lines = (
        [
            ln.strip()
            for ln in sec1_m.group(1).splitlines()
            if ln.strip().startswith("|") and ln.strip().endswith("|")
        ]
        if sec1_m
        else []
    )
    if ref_naive is not None and len(tbl_lines) >= 3:
        for ln in tbl_lines[1:]:
            cells = _split_md_row(ln)
            if not cells or all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            res = cells[4] if len(cells) >= 5 else ""
            if "⏳" in res:
                due_cell = cells[3] if len(cells) >= 4 else ""
                due_dt = _parse_scorecard_due_dt(due_cell, ref_naive)
                if due_dt is not None and due_dt <= ref_naive - timedelta(hours=1):
                    summary = re.sub(r"[*`]", "", cells[2] if len(cells) >= 3 else "")[:36]
                    errs.append(
                        f"Gate G7 失败：SCORECARD.md 存在已逾期未结案的 ⏳ 条目 "
                        f"(到期 {due_cell.strip()} <= 截点-1h {ref_naive:%Y-%m-%d %H:%M}) -> {summary}"
                    )

    if not m_hdr:
        return errs
    exp_settled, exp_pass, exp_partial, exp_fail, exp_untrig, exp_track = (int(x) for x in m_hdr.groups())
    if exp_settled != exp_pass + exp_partial + exp_fail + exp_untrig:
        errs.append(
            f"Gate 4 失败：SCORECARD.md 头部汇总已到期 {exp_settled} 项 "
            f"≠ ✅{exp_pass}+⚠️{exp_partial}+❌{exp_fail}+未触发{exp_untrig}"
        )

    if len(tbl_lines) < 3:
        return errs
    act_pass = act_partial = act_fail = act_untrig = act_track = 0
    for ln in tbl_lines[1:]:
        cells = _split_md_row(ln)
        if cells and all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        res = cells[4] if len(cells) >= 5 else ""
        if "✅" in res:
            act_pass += 1
        elif "⚠️" in res or "部分兑现" in res:
            act_partial += 1
        elif "❌" in res or "证伪" in res:
            act_fail += 1
        elif "条件未触发" in res or "⚪" in res:
            act_untrig += 1
        elif "⏳" in res or "待验真" in res or "持续追踪" in res:
            act_track += 1
    act_settled = act_pass + act_partial + act_fail + act_untrig
    if (act_settled, act_pass, act_partial, act_fail, act_untrig, act_track) != (
        exp_settled, exp_pass, exp_partial, exp_fail, exp_untrig, exp_track
    ):
        errs.append(
            f"Gate 4 失败：SCORECARD.md 头部汇总=(已到期{exp_settled}: ✅{exp_pass}/⚠️{exp_partial}/❌{exp_fail}/未触发{exp_untrig}, 追踪{exp_track}) "
            f"≠ 实表行=(已到期{act_settled}: ✅{act_pass}/⚠️{act_partial}/❌{act_fail}/未触发{act_untrig}, 追踪{act_track})"
        )
    return errs


def _check_extended_cockpit_markets(state: dict | None, *, require_presence: bool = False) -> list[str]:
    """Validate rates_bonds_core and non_us_global_satellite structure, lamp enums, intra-file rate parity, and text hygiene."""
    errs: list[str] = []
    if not isinstance(state, dict):
        return errs

    links = state.get("cross_market_linkages") if isinstance(state.get("cross_market_linkages"), dict) else {}
    rates = links.get("rates_fx_chain") if isinstance(links.get("rates_fx_chain"), dict) else {}

    kline_catalog_ids: set[str] | None = None
    if KLINES_MANIFEST_PATH.is_file():
        try:
            kmanifest = json.loads(KLINES_MANIFEST_PATH.read_text(encoding="utf-8"))
            if isinstance(kmanifest, dict) and isinstance(kmanifest.get("catalog"), list):
                kline_catalog_ids = {
                    str(entry.get("id", "")).strip()
                    for entry in kmanifest["catalog"]
                    if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"].strip()
                }
            else:
                errs.append("Gate 4 失败：state/klines/manifest.json 缺少有效的 catalog 数组")
        except (OSError, ValueError) as exc:
            errs.append(f"Gate 4 失败：state/klines/manifest.json 解析失败: {exc}")

    def _scan_hygiene(obj: object, root_label: str) -> None:
        for jpath, sval in _walk_json_strings(obj, root_label):
            hits = _BANNED_INTERNAL_RE.findall(sval)
            if hits:
                errs.append(f"Gate 4 失败：{jpath} 泄露内部词: {sorted(set(hits))}")
            errs.extend(_check_retracted_facts(jpath, sval))
            hk4 = _HK_4DIGIT_RE.findall(sval)
            if hk4:
                errs.append(f"Gate 4 失败：{jpath} 出现非法 4 位港股代码: {sorted(set(hk4))}")
            for m_iopv in _BARE_IOPV_RE.finditer(sval):
                win = sval[max(0, m_iopv.start() - 20) : min(len(sval), m_iopv.end() + 20)]
                if not _IOPV_GLOSS_RE.search(win):
                    errs.append(
                        f"Gate G5 失败：{jpath} 出现未配白话释义（参考净值/实时净值/盘中净值）的裸 IOPV -> {win!r}"
                    )
                    break

    # 1. rates_bonds_core
    if "rates_bonds_core" not in state:
        if require_presence:
            errs.append("Gate 4 失败：market_state.json 缺少 rates_bonds_core 对象")
    else:
        rb = state.get("rates_bonds_core")
        if not isinstance(rb, dict):
            errs.append("Gate 4 失败：market_state.json.rates_bonds_core 须为对象")
        else:
            if rb.get("lamp") not in _COCKPIT_ALLOWED_LAMPS:
                errs.append(f"Gate 4 失败：market_state.json.rates_bonds_core.lamp 非法枚举 ({rb.get('lamp')!r})")
            for req_s in ("lamp_label", "headline"):
                if not isinstance(rb.get(req_s), str) or not rb[req_s].strip():
                    errs.append(f"Gate 4 失败：market_state.json.rates_bonds_core 缺少非空 {req_s}")
            cn_r = rb.get("cn_rates")
            if not isinstance(cn_r, dict):
                errs.append("Gate 4 失败：market_state.json.rates_bonds_core.cn_rates 须为对象")
            else:
                for nk in ("cgb2y_pct", "cgb10y_pct", "cgb30y_pct", "gc001_pct", "dr001_pct"):
                    if not _is_num(cn_r.get(nk)):
                        errs.append(f"Gate 4 失败：market_state.json.rates_bonds_core.cn_rates.{nk} 须为有限数值")
                if _is_num(cn_r.get("cgb10y_pct")) and _is_num(rates.get("cgb10y_pct")):
                    if abs(float(cn_r["cgb10y_pct"]) - float(rates["cgb10y_pct"])) > 0.005:
                        errs.append(
                            f"Gate G6 失败：rates_bonds_core.cn_rates.cgb10y_pct ({cn_r['cgb10y_pct']}) "
                            f"≠ rates_fx_chain.cgb10y_pct ({rates['cgb10y_pct']})"
                        )
            us_r = rb.get("us_rates")
            if not isinstance(us_r, dict):
                errs.append("Gate 4 失败：market_state.json.rates_bonds_core.us_rates 须为对象")
            else:
                for nk in ("us2y_pct", "us10y_pct", "us30y_pct", "dfii10_pct", "sofr_pct"):
                    if not _is_num(us_r.get(nk)):
                        errs.append(f"Gate 4 失败：market_state.json.rates_bonds_core.us_rates.{nk} 须为有限数值")
                    elif _is_num(rates.get(nk)) and abs(float(us_r[nk]) - float(rates[nk])) > 0.01:
                        errs.append(
                            f"Gate G6 失败：rates_bonds_core.us_rates.{nk} ({us_r[nk]}) "
                            f"≠ rates_fx_chain.{nk} ({rates[nk]})"
                        )
            sp = rb.get("cn_us_10y_spread_bp")
            if not _is_num(sp):
                errs.append("Gate 4 失败：market_state.json.rates_bonds_core.cn_us_10y_spread_bp 须为有限数值")
            else:
                if _is_num(rates.get("cn_us_10y_spread_bp")) and abs(float(sp) - float(rates["cn_us_10y_spread_bp"])) > 1.0:
                    errs.append(
                        f"Gate G6 失败：rates_bonds_core.cn_us_10y_spread_bp ({sp}) "
                        f"≠ rates_fx_chain.cn_us_10y_spread_bp ({rates['cn_us_10y_spread_bp']})"
                    )
                if isinstance(cn_r, dict) and isinstance(us_r, dict) and _is_num(cn_r.get("cgb10y_pct")) and _is_num(us_r.get("us10y_pct")):
                    exp_sp = round((float(cn_r["cgb10y_pct"]) - float(us_r["us10y_pct"])) * 100.0)
                    if abs(float(sp) - exp_sp) > 1.0:
                        errs.append(
                            f"Gate G6 失败：rates_bonds_core.cn_us_10y_spread_bp ({sp}) "
                            f"与 round(({cn_r['cgb10y_pct']}-{us_r['us10y_pct']})*100)={exp_sp} 偏离 > 1bp"
                        )
            fx_drag = rb.get("unhedged_usd_fx_drag")
            if not isinstance(fx_drag, dict):
                errs.append("Gate 4 失败：market_state.json.rates_bonds_core.unhedged_usd_fx_drag 须为对象")
            else:
                if not _is_num(fx_drag.get("usd_cny_spot")):
                    errs.append("Gate 4 失败：rates_bonds_core.unhedged_usd_fx_drag.usd_cny_spot 须为有限数值")
                else:
                    spot_ref = next(
                        (
                            (rk, float(rates[rk]))
                            for rk in ("usd_cny_spot", "usd_cny_night", "usd_cny_1630", "usd_cnh")
                            if _is_num(rates.get(rk))
                        ),
                        None,
                    )
                    if spot_ref is not None and abs(float(fx_drag["usd_cny_spot"]) - spot_ref[1]) > 0.05:
                        errs.append(
                            f"Gate G6 失败：rates_bonds_core.unhedged_usd_fx_drag.usd_cny_spot ({fx_drag['usd_cny_spot']}) "
                            f"与 rates_fx_chain.{spot_ref[0]} ({spot_ref[1]}) 偏离 > 0.05"
                        )
                if not _is_num(fx_drag.get("cfets_cny_fixing")):
                    errs.append("Gate 4 失败：rates_bonds_core.unhedged_usd_fx_drag.cfets_cny_fixing 须为有限数值")
                elif _is_num(rates.get("cfets_cny_fixing")) and abs(float(fx_drag["cfets_cny_fixing"]) - float(rates["cfets_cny_fixing"])) > 0.001:
                    errs.append(
                        f"Gate G6 失败：rates_bonds_core.unhedged_usd_fx_drag.cfets_cny_fixing ({fx_drag['cfets_cny_fixing']}) "
                        f"≠ rates_fx_chain.cfets_cny_fixing ({rates['cfets_cny_fixing']})"
                    )
                if not isinstance(fx_drag.get("real_rmb_drag_range"), str) or not fx_drag["real_rmb_drag_range"].strip():
                    errs.append("Gate 4 失败：rates_bonds_core.unhedged_usd_fx_drag 缺少非空 real_rmb_drag_range")
            ds = rb.get("duration_stance")
            if not (isinstance(ds, dict) and ds) and not (isinstance(ds, str) and ds.strip()):
                errs.append("Gate 4 失败：market_state.json.rates_bonds_core.duration_stance 须为非空对象或字符串")
            key_etfs = rb.get("key_etfs")
            if not isinstance(key_etfs, list) or not key_etfs:
                errs.append("Gate 4 失败：market_state.json.rates_bonds_core.key_etfs 须为非空数组")
            else:
                for ki, ke in enumerate(key_etfs):
                    if not isinstance(ke, dict) or not isinstance(ke.get("kline_id"), str) or not ke["kline_id"].strip():
                        errs.append(f"Gate 4 失败：rates_bonds_core.key_etfs[{ki}] 缺少非空 kline_id")
                    elif kline_catalog_ids is not None and ke["kline_id"].strip() not in kline_catalog_ids:
                        errs.append(
                            f"Gate 4 失败：rates_bonds_core.key_etfs[{ki}].kline_id ({ke['kline_id'].strip()!r}) "
                            f"不存在于 state/klines/manifest.json catalog 中"
                        )
            _scan_hygiene(rb, "market_state.json.rates_bonds_core")

    # 2. non_us_global_satellite
    if "non_us_global_satellite" not in state:
        if require_presence:
            errs.append("Gate 4 失败：market_state.json 缺少 non_us_global_satellite 对象")
    else:
        sat = state.get("non_us_global_satellite")
        if not isinstance(sat, dict):
            errs.append("Gate 4 失败：market_state.json.non_us_global_satellite 须为对象")
        else:
            sat_mkts = sat.get("markets")
            if not isinstance(sat_mkts, list) or not sat_mkts:
                errs.append("Gate 4 失败：market_state.json.non_us_global_satellite.markets 须为非空数组")
            else:
                seen_sat_ids: list[str] = []
                for mi, sm in enumerate(sat_mkts):
                    if not isinstance(sm, dict):
                        errs.append(f"Gate 4 失败：non_us_global_satellite.markets[{mi}] 须为对象")
                        continue
                    mid = str(sm.get("id", "")).strip()
                    if not mid:
                        errs.append(f"Gate 4 失败：non_us_global_satellite.markets[{mi}] 缺少非空 id")
                    else:
                        if mid in seen_sat_ids:
                            errs.append(f"Gate 4 失败：non_us_global_satellite.markets 存在重复 id ({mid!r})")
                        seen_sat_ids.append(mid)
                    if sm.get("lamp") not in _COCKPIT_ALLOWED_LAMPS:
                        errs.append(
                            f"Gate 4 失败：non_us_global_satellite.markets[{mi}]({mid}).lamp 非法枚举 ({sm.get('lamp')!r})"
                        )
                    for req_s in ("name", "kline_id", "access_grade", "warning"):
                        if not isinstance(sm.get(req_s), str) or not sm[req_s].strip():
                            errs.append(f"Gate 4 失败：non_us_global_satellite.markets[{mi}]({mid}) 缺少非空 {req_s}")
                    sm_kid = sm.get("kline_id")
                    if (
                        kline_catalog_ids is not None
                        and isinstance(sm_kid, str)
                        and sm_kid.strip()
                        and sm_kid.strip() not in kline_catalog_ids
                    ):
                        errs.append(
                            f"Gate 4 失败：non_us_global_satellite.markets[{mi}]({mid}).kline_id ({sm_kid.strip()!r}) "
                            f"不存在于 state/klines/manifest.json catalog 中"
                        )
                    bms = sm.get("benchmarks")
                    if not isinstance(bms, list) or not bms:
                        errs.append(f"Gate 4 失败：non_us_global_satellite.markets[{mi}]({mid}) 缺少非空 benchmarks")
                    else:
                        for bi, bm in enumerate(bms):
                            if (
                                not isinstance(bm, dict)
                                or not isinstance(bm.get("name"), str) or not bm["name"].strip()
                                or not _is_num(bm.get("value"))
                                or not _is_num(bm.get("change_pct"))
                            ):
                                errs.append(
                                    f"Gate 4 失败：non_us_global_satellite.markets[{mi}]({mid}).benchmarks[{bi}] 须含有效 name/value/change_pct"
                                )
                    for vk in ("onshore_vehicles", "offshore_vehicles"):
                        vv = sm.get(vk)
                        if not ((isinstance(vv, list) and vv) or (isinstance(vv, str) and vv.strip())):
                            errs.append(f"Gate 4 失败：non_us_global_satellite.markets[{mi}]({mid}) 缺少非空 {vk}")
                req_sat_order = ["jp", "eu", "tw_kr", "in"]
                missing_sat = [sid for sid in req_sat_order if sid not in seen_sat_ids]
                if missing_sat:
                    errs.append(f"Gate 4 失败：non_us_global_satellite.markets 缺少必填市场: {missing_sat}")
                elif [sid for sid in seen_sat_ids if sid in req_sat_order] != req_sat_order:
                    errs.append(
                        f"Gate 4 失败：non_us_global_satellite.markets 排序错误 ({seen_sat_ids}，须按 {req_sat_order})"
                    )
            _scan_hygiene(sat, "market_state.json.non_us_global_satellite")

    return errs


def check_workspace_state(*, precheck: bool = False) -> tuple[list[str], list[str]]:
    """Shared single-source workspace state, RSI playbook/metrics, ledger, INDEX link & _latest sync check."""
    errs: list[str] = []
    warns: list[str] = []
    st: dict | None = None
    require_full_ssot = False
    if not STATE_PATH.exists():
        errs.append("Gate 4 失败：缺少 state/market_state.json")
    else:
        try:
            st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if not isinstance(st, dict):
                errs.append("Gate 4 失败：market_state.json 根元素必须为对象")
                st = None
            else:
                for k in ("markets", "cross_market_linkages", "policy_radars", "pending_backfills", "calendar_overrides"):
                    if k not in st:
                        errs.append(f"Gate 4 失败：market_state.json 缺少必填域 {k}")
                mkts = st.get("markets", {})
                if not isinstance(mkts, dict):
                    errs.append("Gate 4 失败：market_state.json.markets 须为对象")
                else:
                    for mk in (*MARKETS, "gold_mirror_readonly"):
                        if not isinstance(mkts.get(mk), dict):
                            errs.append(f"Gate 4 失败：market_state.json.markets 缺少 {mk}")
                    counts = [
                        mkts[m].get("stock_pool_count")
                        for m in MARKETS
                        if isinstance(mkts.get(m), dict)
                    ]
                    if len(counts) == len(MARKETS) and all(type(c) is int and c > 0 for c in counts):
                        require_full_ssot = sum(counts) >= 100
                errs.extend(_check_state_schedule(st))
                errs.extend(_check_data_caveats(st, require_presence=require_full_ssot))
                errs.extend(_check_market_state_math(st))
                errs.extend(_check_extended_cockpit_markets(st, require_presence=require_full_ssot))
        except json.JSONDecodeError as exc:
            errs.append(f"Gate 4 失败：market_state.json JSON 语法错误: {exc}")

    errs.extend(_check_ssot_databases(st))

    state_ed_key = parse_edition_id(st.get("edition_id")) if isinstance(st, dict) else None
    state_as_of_dt: datetime | None = None
    if isinstance(st, dict) and isinstance(st.get("as_of_cst"), str):
        try:
            state_as_of_dt = datetime.fromisoformat(st["as_of_cst"])
        except ValueError:
            state_as_of_dt = None

    pb = BASE_DIR / "state" / "RSI_PLAYBOOK.md"
    if not pb.exists():
        errs.append("Gate 4 失败：缺少 state/RSI_PLAYBOOK.md")
    else:
        pb_text = pb.read_text(encoding="utf-8")
        n = len(pb_text.splitlines())
        if n > 200:
            errs.append(f"Gate 4 失败：state/RSI_PLAYBOOK.md 超过 200 行硬限 ({n})")
        elif n > 180:
            warns.append(f"Gate 4 警告：state/RSI_PLAYBOOK.md 超过 180 行软限 ({n})")
        errs.extend(_check_playbook_retracted_claims(pb_text))

    mf = BASE_DIR / "state" / "rsi_metrics.json"
    if not mf.exists():
        errs.append("Gate 4 失败：缺少 state/rsi_metrics.json")
    else:
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            errs.extend(f"Gate 4 失败：{error}" for error in _check_rsi_metrics(data))
        except (OSError, ValueError) as exc:
            errs.append(f"Gate 4 失败：rsi_metrics.json 解析失败: {exc}")

    for ledger in (DAILY_DIR / "INDEX.md", DAILY_DIR / "CHANGELOG.md", DAILY_DIR / "SCORECARD.md"):
        if not ledger.exists():
            errs.append(f"Gate 4 失败：缺少 {ledger.relative_to(BASE_DIR)}")
        else:
            ledger_txt = ledger.read_text(encoding="utf-8")
            le, lw = lint_markdown_report(ledger_txt, str(ledger), is_flagship=False)
            errs.extend([f"{ledger.name}: {x}" for x in le])
            warns.extend([f"{ledger.name}: {x}" for x in lw])
            errs.extend(_check_retracted_facts(ledger.name, ledger_txt, skip_scorecard_col3=(ledger.name == "SCORECARD.md")))
            if ledger.name == "SCORECARD.md":
                errs.extend(_reconcile_equity_scorecard(ledger_txt, as_of_dt=state_as_of_dt))
            elif ledger.name == "INDEX.md" and state_ed_key and state_ed_key[:2] >= EDITORIAL_DEPTH_CUTOVER[:2]:
                idx_top = ledger_txt.split("## 每日天气与行动速览", 1)[0]
                errs.extend(_check_shfe_night_close(ledger.name, idx_top))
                errs.extend(_check_tense_drift(ledger.name, idx_top, state_ed_key[0]))
                errs.extend(_check_year_end_countdown(ledger.name, idx_top, state_ed_key[0]))

    idx_path = DAILY_DIR / "INDEX.md"
    if idx_path.exists():
        errs.extend(_check_index_links(idx_path, precheck=precheck))

    if not precheck:
        for market in ("a_share", "hk_stock", "us_stock"):
            meta_f = BASE_DIR / f"report_meta_{market}.json"
            if not meta_f.exists():
                errs.append(f"Gate 4 失败：缺失 {meta_f.name}")
                continue
            try:
                slug = _read_flagship_meta(market)["period_slug"]
            except (OSError, ValueError) as exc:
                errs.append(f"Gate 4 失败：{meta_f.name} JSON 解析失败: {exc}")
                continue
            p_cur = BASE_DIR / f"{market}_market_report_{slug}.md"
            p_lat = BASE_DIR / f"{market}_market_report_latest.md"
            if not p_cur.exists():
                errs.append(f"Gate 4 失败：缺失当期旗舰源稿 {p_cur.name}")
            elif not p_lat.exists() or p_cur.read_bytes() != p_lat.read_bytes():
                errs.append(f"Gate 4 失败：{p_lat.name} 未与 {p_cur.name} 原子同步")
    return errs, warns


def _auto_discover_targets() -> tuple[list[Path], list[str]]:
    targets: list[Path] = []
    disc_errors: list[str] = []
    for market in ("a_share", "hk_stock", "us_stock"):
        meta_f = BASE_DIR / f"report_meta_{market}.json"
        if meta_f.exists():
            try:
                slug = _read_flagship_meta(market)["period_slug"]
            except (OSError, ValueError) as exc:
                disc_errors.append(f"Gate 4 失败：{meta_f.name} JSON 解析失败: {exc}")
                continue
            fp = BASE_DIR / f"{market}_market_report_{slug}.md"
            if fp.exists():
                targets.append(fp)
        daily_files = _market_daily_files(market, keep_invalid=True)
        for invalid in (p for p in daily_files if parse_daily_sort_key(p)[0] == "0000-00-00"):
            disc_errors.append(f"Gate 4 失败：日报文件名非法 {invalid.name}")
        if daily_files and parse_daily_sort_key(daily_files[-1])[0] != "0000-00-00":
            targets.append(daily_files[-1])
    return targets, disc_errors


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["--plan"]:
        if len(args) != 2:
            sys.exit("Usage: lint_equity.py --plan YYYY-MM-DD_HHMM[_rN]")
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            calendar = json.loads(GOLD_CALENDAR_PATH.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("权益状态须为 JSON 对象")
            plan, errors = edition_plan(args[1], state, calendar)
        except (OSError, ValueError) as exc:
            sys.exit(f"无法生成出刊计划：{exc}")
        if errors:
            sys.exit("\n".join(errors))
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    known_flags = {"--precheck", "--strict", "--skip-cross-project"}
    unknown = [a for a in args if a.startswith("-") and a not in known_flags]
    if unknown:
        print(f"Unknown flags: {unknown}", file=sys.stderr)
        sys.exit(2)

    precheck = "--precheck" in args
    strict = "--strict" in args
    skip_cross = "--skip-cross-project" in args
    positional = [Path(a) for a in args if not a.startswith("-")]
    discovery_errors: list[str] = []
    if positional:
        targets = positional
    else:
        targets, discovery_errors = _auto_discover_targets()
    if not targets:
        for derr in discovery_errors:
            print(f"  [FAIL] {derr}", file=sys.stderr)
        print("No target Markdown files found.", file=sys.stderr)
        sys.exit(2)

    state_obj: dict | None = None
    if STATE_PATH.exists():
        try:
            state_obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            state_obj = None
    if not isinstance(state_obj, dict):
        state_obj = {}
    current_id = parse_edition_id(state_obj.get("edition_id"))
    try:
        as_of_cst = datetime.fromisoformat(state_obj.get("as_of_cst", ""))
    except (TypeError, ValueError):
        as_of_cst = None

    all_errors: list[str] = list(discovery_errors)
    all_warnings: list[str] = []

    for p in targets:
        if not p.exists():
            all_errors.append(f"目标文件不存在: {p}")
            continue
        md_text = p.read_text(encoding="utf-8")
        is_flag = _detect_is_flagship(p)
        mkt = _detect_market(p)
        meta: dict | None = None
        if is_flag:
            mf = BASE_DIR / f"report_meta_{mkt}.json"
            if mf.exists():
                try:
                    meta = _read_flagship_meta(mkt)
                except (OSError, ValueError) as exc:
                    all_errors.append(f"{mf.name} 元数据错误: {exc}")
        else:
            meta, jerr = _extract_meta(md_text, p)
            if jerr:
                all_errors.append(f"{p.name}: {jerr}")
            cutoff = as_of_cst if parse_daily_sort_key(p)[:3] == current_id else None
            all_errors.extend(check_daily_contract(p, meta, md_text, as_of_cst=cutoff, warnings=all_warnings))

        errs, warns = lint_markdown_report(md_text, str(p), is_flagship=is_flag, meta=meta)
        all_errors.extend([f"{p.name}: {x}" for x in errs])
        all_warnings.extend([f"{p.name}: {x}" for x in warns])

        b3_errs, b3_warns = _check_gate_3b(md_text, p, is_flagship=is_flag, meta=meta, market=mkt, state=state_obj)
        all_errors.extend(b3_errs)
        all_warnings.extend(b3_warns)

        body_no_meta = re.sub(r"<!--\s*DAILY_META_JSON\s*\{.*?\}\s*-->", "", md_text, flags=re.DOTALL)
        if is_flag or parse_daily_sort_key(p)[:3] >= ALL_MAIN_CUTOVER:
            bin_hits = _DEPRECATED_BINARY_LINK_RE.findall(body_no_meta)
            if bin_hits:
                all_errors.append(
                    f"{p.name}: Gate 4 失败：纯网页版严禁保留已弃用的 PDF/Word 或离线附件链接 -> {sorted(set(bin_hits))[:5]}"
                )
        body_lines_no_meta = re.sub(
            r"<!--\s*DAILY_(?:META_JSON|VISUAL)\s*\{.*?\}\s*-->",
            lambda m: "\n" * m.group(0).count("\n"),
            md_text,
            flags=re.DOTALL,
        )
        long_bullet_items: list[tuple[int, int, str]] = []
        for ln_no, ln in enumerate(body_lines_no_meta.splitlines(), 1):
            st = ln.strip()
            if re.match(r"^\s*[-•*]\s+", ln) and len(st) > 210:
                long_bullet_items.append((ln_no, len(st), st[:26]))
        if long_bullet_items:
            offenders = ", ".join(f'[L{ln}:{nch}字 "{snip}..."]' for ln, nch, snip in long_bullet_items[:5])
            all_warnings.append(
                f"{p.name}: 存在 {len(long_bullet_items)} 条超过 210 字的超长列表项（防密墙）: {offenders}"
            )

    we, ww = check_workspace_state(precheck=precheck)
    all_errors.extend(we)
    all_warnings.extend(ww)

    ge, gw = _check_svg_geometry_all(targets)
    all_errors.extend(ge)
    all_warnings.extend(gw)

    if not skip_cross:
        ce, cw = _check_cross_project_gold(targets, precheck=precheck)
        all_errors.extend(ce)
        all_warnings.extend(cw)

    mode_str = "PRECHECK (Gates 0-5 + SVG)" if precheck else "WEB-ONLY FORENSIC (Gates 0-5 + SVG + SSOT + Cross-Project)"
    print(f"=== lint_equity.py [{mode_str}] checked {len(targets)} file(s) ===")
    for e in all_errors:
        print(f"  [FAIL] {e}")
    for w in all_warnings:
        print(f"  [WARN] {w}")
    print(f"Summary: {len(all_errors)} error(s), {len(all_warnings)} warning(s).")

    if all_errors or (strict and all_warnings):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
