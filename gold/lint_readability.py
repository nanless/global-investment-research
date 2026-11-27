#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Web-Only Readability, Mathematical Accuracy & SSOT Integrity Linter (Gates 0–5).
Supports dedicated master_snapshot.json via <!-- MASTER_BASELINE {...} --> and daily data_snapshot.json.

Usage:
  python3 lint_readability.py <file1.md> [file2.md ...] [--precheck] [--strict]
  --precheck  Accepted for backwards compatibility (web-only mode always runs Gates 0–5).
  --strict    Fail with exit code 1 on any warning in addition to errors.
"""

from __future__ import annotations

import html
import importlib.util
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from chart_input import normalize_chart
from edition_validation import (
    BEIJING, ENTRY_GATE_IDS, LAST_LEGACY_EDITION, check_edition_time, check_vix_period, cutoff_displayed,
    evidence_url, recheck_entry_gates, vix_calendar,
)

CONVERGED_CUTOVER = ("2026-11-26", "1800", 1)
INTERNAL_LEAK_CUTOVER = ("2026-11-26", "0730", 1)
EDITORIAL_DEPTH_CUTOVER = ("2026-11-27", "0730", 1)

_SHFE_0230_RE = re.compile(r"(?<!\d)02:30(?!\d)")
_SHFE_NON_GOLD_METAL_RE = re.compile(
    r"(?:沪铜|沪铝|沪锌|沪镍|沪锡|沪铅|氧化铝|螺纹钢|热卷|不锈钢|纯碱|(?<![A-Za-z])(?:cu|al|zn|ni|rb)\d{4}(?!\d))",
    re.IGNORECASE,
)
_SHFE_EARLY_CLOSE_QUAL_RE = re.compile(r"(?<!\d)(?:01:00|23:00)(?!\d)")
_TEN_DOT_RE = re.compile(r"[●○]{10}")
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
_CREDIT_SPREAD_CCC_RE = re.compile(r"(?:垃圾债利差\s*1,\d{3}|高收益与垃圾债)")
_CCC_QUAL_RE = re.compile(r"CCC", re.IGNORECASE)

BASE_DIR = Path(__file__).resolve().parent
DAILY_DIR = BASE_DIR / "daily"
MASTER_FILENAME = "黄金跨世纪周期与2026-2030终审研究报告.md"
DAILY_SNAPSHOT_PATH = BASE_DIR / "data_snapshot.json"
MASTER_SNAPSHOT_PATH = BASE_DIR / "master_snapshot.json"
MARKET_CALENDAR_PATH = BASE_DIR / "market_calendar.json"
SCORECARD_PATH = BASE_DIR / "daily" / "SCORECARD.md"
AUDIT_LOG_PATH = DAILY_DIR / "AUDIT_LOG.md"
CHANGELOG_PATH = DAILY_DIR / "CHANGELOG.md"
RSI_PLAYBOOK_PATH = BASE_DIR / "daily" / "RSI_PLAYBOOK.md"
RSI_METRICS_PATH = BASE_DIR / "daily" / "rsi_metrics.json"
SCORECARD_BANNED_RE = re.compile(
    r"(?:Subagent|子代理|\bRSI\b|Meta-RSI|Recursive\s+Self-Improvement|"
    r"\bTier\s*[ABC](?:\b|/[ABC])|\bV[2567]\.\d+\b|"
    r"RSI_PLAYBOOK(?:\.md)?|rsi_metrics\.json|sidecar\.json|"
    r"master_snapshot\.json|data_snapshot\.json|market_state\.json|permissions\.json|"
    r"multi_asset_channels\.json|etf_universe\.json|deep_dossiers\.json|market_calendar\.json|"
    r"DAILY_FORMAT_SPEC\.md|DAILY_REPORT_SPEC\.md|unified-edition\.prompt\.md|"
    r"AGENTS\.md|SKILL\.md|GEMINI\.md|audit_ledger\.md|"
    r"build_(?:daily|report|site|a_share_pdf|hk_stock_pdf|us_stock_pdf|pdf)\.py|"
    r"publish_site\.py|lint_(?:readability|equity|site)\.py|pdf_common\.py|docx_embed\.py|"
    r"edition_run\.py|artifact_receipt\.py|edition_plan\.py|edition_validation\.py|"
    r"chart_input\.py|install_sidecars\.py|svg_geometry\.py|patch_state_dbs\.py|"
    r"_(?:edition|ledger|rsi|audit|rollover|archive)_patch\.json|"
    r"63\s*路|红队|法证|\bGate\s*[0-6]\b)",
    flags=re.IGNORECASE,
)
_INTERNAL_FILENAME_LEAK_RE = re.compile(
    r"(?:master_snapshot\.json|data_snapshot\.json|market_state\.json|"
    r"multi_asset_channels\.json|etf_universe\.json|deep_dossiers\.json|market_calendar\.json|"
    r"audit_ledger\.md|RSI_PLAYBOOK(?:\.md)?|rsi_metrics\.json|sidecar\.json|"
    r"permissions\.json|unified-edition\.prompt\.md|"
    r"svg_geometry\.py|patch_state_dbs\.py|_(?:edition|ledger|rsi|audit|rollover|archive)_patch\.json|"
    r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_-]*\.py(?![A-Za-z0-9_])|"
    r"DAILY_FORMAT_SPEC\.md|DAILY_REPORT_SPEC\.md|"
    r"AGENTS\.md|GEMINI\.md|SKILL\.md|"
    r"(?<![A-Za-z0-9_])V[2567]\.\d+(?![A-Za-z0-9_])|"
    r"(?<![A-Za-z0-9_])Subagents?(?![A-Za-z0-9_])|红队|法证)",
    flags=re.IGNORECASE,
)
_DEPRECATED_BINARY_LINK_RE = re.compile(
    r"(?:\[[^\]]+\]\((?!https?://)[^)\s]+\.(?:pdf|docx)(?:#[^)\s]*)?\)"
    r"|/releases/download/"
    r"|\{md,pdf,docx\}"
    r"|(?:daily/|archive/|\.\.?/)[^\s`\"'()<>]+\.(?:pdf|docx))",
    flags=re.IGNORECASE,
)
_CAVEAT_ALLOWED_CATEGORIES = frozenset({
    "holiday_thin", "provisional_close", "delayed_official", "source_conflict",
    "partial_data", "single_source", "publication_exception", "other",
})
_CAVEAT_ALLOWED_SEVERITIES = frozenset({"info", "warn", "critical"})
_RSI_ALLOWED_FINDING_STATUSES = frozenset({"resolved", "deferred_data", "disclosed_caveat"})
RSI_REQUIRED_SCORE_KEYS = (
    "data_freshness_and_zero_hallucination",
    "prior_forecast_calibration",
    "plain_language_and_strict_readability",
    "visual_layout_and_pagination",
    "research_efficiency_and_source_quality",
    "engine_and_guardrail_reliability",
)

BANNED_HYPE_WORDS = [
    "神准", "分毫不差", "100%胜率", "100% 胜率", "无情推翻", "核雷",
    "拉爆", "血洗", "焊死", "史诗级", "史诗轧空", "彻底打脸", "惊天验证",
]

# Case-insensitive word-boundary ASCII Wall Street / internal code tokens banned in Layer 0–1
BANNED_LAYER01_ASCII = [
    "DFII10", "2Y-FF", "2Y−FF", "T10YIE", "EFFR", "SOFR", "IORB", "HY OAS", "CCC OAS",
    "ON RRP", "au2702", "OGZ26", "GCX26", "GCZ26", "GCG27", "BCOM", "GSCI",
    "Subagent", "Daniel Ghali", "Michael Hsueh", "Call Wall", "Put Wall",
    "stop-through", "IFRS 9", "HQLA", "GDX/GLD", "CDX IG",
    "OAT", "JGB", "DXY", "VIX", "GLD", "GDX", "KRE", "SRF", "CDS", "OIS", "CFTC", "COT",
    "V2.0", "V2.1", "V2.2", "V6.0", "V6.1", "V7.0", "V7.1", "V7.2",
]
_BANNED_ASCII_PATTERNS = [
    (tok, re.compile(rf"(?<![A-Za-z0-9_]){re.escape(tok)}(?![A-Za-z0-9_])", re.IGNORECASE))
    for tok in BANNED_LAYER01_ASCII
]

# CJK / mixed-script jargon & meta-noise banned in Layer 0–1 (legacy editions < CONVERGED_CUTOVER)
BANNED_LAYER01_LITERAL = [
    "子代理", "63 路", "63路", "负 Gamma", "负Gamma", "R²=", "R² =",
    "梭哈", "短线波段", "放鹰", "鹰派", "鸽派", "提保", "上影线", "即征即退",
    "高弹性", "六灯", "逼空", "轧空", "做T", "做 T",
]

# Converged Informed-Retail Layer 0–1 banned tokens (>= CONVERGED_CUTOVER):
# Allows standard semi-pro terms (VIX, DXY, GLD, GDX, ETF, CFTC, COT, CDS, 鹰派, 鸽派, 提保, 轧空, 逼空, 上影线)
# while hard-banning internal eng/RSI/version strings, obscure quant jargon, retail slang,
# cross-market color confusion, condescending slogans, and parallel scores.
CONVERGED_BANNED_LAYER01_ASCII = [
    "Subagent", "stop-through", "IFRS 9", "HQLA", "FVOCI", "ROTCE",
    "Call Wall", "Put Wall", "Daniel Ghali", "Michael Hsueh",
]
_CONVERGED_BANNED_ASCII_PATTERNS = [
    (tok, re.compile(rf"(?<![A-Za-z0-9_]){re.escape(tok)}(?![A-Za-z0-9_])", re.IGNORECASE))
    for tok in CONVERGED_BANNED_LAYER01_ASCII
] + [
    ("V2/V6/V7版本号", re.compile(r"(?<![A-Za-z0-9_])V[267]\.\d+(?![A-Za-z0-9_])", re.IGNORECASE)),
]
CONVERGED_BANNED_LAYER01_LITERAL = [
    "子代理", "63 路", "63路",
    "负 Gamma", "负Gamma", "R²=", "R² =",
    "梭哈", "做T", "做 T", "短线波段", "高弹性",
    "收红", "收绿", "翻红", "翻绿",
    "六灯",
]
# Condescending slogans banned across ALL layers and ALL widgets (incl. DAILY_GLOSSARY)
# in converged editions (>= CONVERGED_CUTOVER).
CONVERGED_BANNED_SLOGANS = [
    "小白词典", "直接抄", "蠢事", "1分钟定心丸", "1 分钟定心丸", "保命铁律",
]
# Bare-number/amount/percentage backticks banned as soft warning in converged editions
# (excludes pure ticker codes like `518660`/`008142`/`GCZ26`/`au2702` and dates/times).
_BARE_NUM_BACKTICK_RE = re.compile(
    r"`(?:"
    r"[+\-~≈<>≤≥]*[$¥€£₹]\s*\d[\d,.–\-]*(?:\s*(?:亿份?|万份?|美元|元|港元|欧元|吨|t))?"
    r"|[+\-~≈<>≤≥]?\d+(?:[.,–\-]\d+)*\s*(?:%|bp|元(?:/克|/千克|/kg)?|港元|美元|欧元|亿份?|万份?|倍|点|手|吨|t)"
    r"|[+\-]\d+(?:[.,]\d+)?"
    r"|\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    r"|\d+\.\d+"
    r")`"
)

PERMANENT_FACT_GUARDS = [
    ("912 元/克", "表 6.1 汇率算错旧值（6.30×$4,500 实为 911 元/克）"),
    ("30% + 40% + 30%", "A 类建仓比例旧冲突口径（全系统统一 30% + 45% + 25%）"),
    ("7 天后免赎回费", "场外 C 类错误赎回费（工银 008143 须满 30 天才免赎回费，不可笼统写 7 天后免赎回费）"),
    ("7天后免赎回费", "场外 C 类错误赎回费（工银 008143 须满 30 天才免赎回费，不可笼统写 7 天后免赎回费）"),
    ("去年三季度财报赚的是 4,280", "年份硬伤（应为今年三季度 / 2026 年三季度）"),
]

# Snapshot-date-bound guards (only active on 2026-11-24 baseline; auto-disabled on subsequent trading days)
DATE_BOUND_STALE_GUARDS_20261124 = [
    ("108.8%", "地上黄金/M2 过时旧值（11/24 基线按 $3,635 更新为 111.9%）"),
    ("超 310 吨", "险资额度过时旧值（11/24 基线按 786/778 元/克更新）"),
    ("省 270", "渠道省钱旧口径（11/24 午报基线为省 283 元/克，早报基线为省 267 元/克）"),
    ("省270", "渠道省钱旧口径（11/24 午报基线为省 283 元/克，早报基线为省 267 元/克）"),
    ("+2.78%", "现货涨幅跨源旧值（11/24 单一源 3534.64→3635.24 = +2.85%）"),
    ("布油收涨至 92.57", "11/24 过时油价（官结 89.37）"),
]

KNOWN_DIRECTIVES = {
    "DAILY_META",
    "DAILY_VERDICT",
    "DAILY_SIGNAL_NOISE",
    "DAILY_PERSONA",
    "DAILY_GLOSSARY",
    "DAILY_LAYER_BADGE",
    "DAILY_TRUST_BAR",
    "DAILY_CHART_TIMELINE",
    "DAILY_CHART_SWITCH",
    "DAILY_CHART_CROSS",
}

ANY_DAILY_DIRECTIVE_RE = re.compile(r"<!--\s*(DAILY_[A-Z0-9_]+)\s*(.*?)\s*-->", re.DOTALL)
EDITION_REVIEW_RE = re.compile(r"<!--\s*GOLD_EDITION_REVIEW\s+(.*?)\s*-->", re.DOTALL)
MASTER_BASELINE_RE = re.compile(r"<!--\s*MASTER_BASELINE\s*(\{.*?\})\s*-->", re.DOTALL)
DAILY_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_.*黄金深度研报(?:_r(\d+))?\.md$")
EDITION_ID_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{4})(?:_r([1-9]\d*))?")
TIER_LABELS = ("红灯", "黄灯", "绿灯", "满格")
GATE_COUNT_RE = re.compile(r"(?<!\d)([0-4])\s*[/／]\s*4(?!\d)")
RED_LIGHT_CONFLICT_RE = re.compile(r"🟢|🟡|(?<!红)绿灯|黄灯|满格|允许新买|(?:新仓|新买|试仓)\s*[1-9]\d*(?:\.\d+)?\s*%")
_TIER0_PROSE_BUY_RE = re.compile(
    r"允许新买"
    r"|(?:新仓|新买|试仓)\s*[1-9]\d*(?:\.\d+)?\s*%"
    r"|红灯期(?:(?!暂不|暂停|停止|严禁|禁止|不可|切忌|勿).){0,12}(?:开(?:半额|全额|自动)?(?:定投|扣款)|启(?:动)?(?:定投|扣款)|买入|新买|加仓|抄底|建仓|定投(?!预算|资金|额度|计划|暂存))"
    r"|(?:立即|马上|今日|今天|现在|当下|直接|建议|宜|可以|可先?)\s*(?:买入|买进|新买|加仓|抄底|低吸|建仓|试买|定投)\s*[0-9一二两三半成%]*\s*(?:现货)?(?:黄金|金仓|金矿|黄金\s*ETF|518660|518880|518850|159934|159937|517520|159562|008142|008143|02840|3081|IGLN|GLD|IAUM|GLDM)",
    flags=re.IGNORECASE,
)
_TIER0_PROSE_GUARD_RE = re.compile(
    r"(?:暂不|严禁|禁止|切忌|勿|停止|先别|不能|不宜|不要|绝非|并非|不是|不|拒绝|不允许|不急于|无须|无需|停止|暂停|取消)"
    r"(?:现在|今天|今日|当下|任何|立即|马上|急于|立刻|再|去|主动|新|分批|小批|继续|直接|盲目|提前|在红灯期)*[\s“‘「\"*_]*$"
    r"|(?:静?等|待|须等|需等|等到|四(?:关|项)(?:条件)?(?:全部|全)?(?:通过|过关|齐备|亮起?)|转(?:亮为?)?黄(?:灯)?|亮黄|黄/绿灯|绿灯|解锁).{0,26}(?:后|再|才)?[\s“‘「\"*_]*$"
    r"|(?:平滑换至|平换进|换仓至|切换至)[\s“‘「\"*_]*$"
)
_PARTIAL_ENTRY_PASS = r"(?:通过|满足|过)\s*(?:[0-3]\s*/\s*4(?!\d)\s*关?|[零一二两三0-3]\s*(?:道?关|项(?:条件)?))"
_ENTRY_ACTION = r"(?:转(?:为)?黄(?:灯)?|亮黄灯|开(?:新)?仓|建仓|试仓|新买(?:入)?|试买|买入|动用首批)"
PARTIAL_ENTRY_CLAIM_RE = re.compile(
    rf"{_PARTIAL_ENTRY_PASS}\s*[,、]?\s*(?:即(?:可)?|便可|就可以|就可|就能|可以|允许|可)\s*{_ENTRY_ACTION}"
    rf"|(?:转(?:为)?黄(?:灯)?|亮黄灯)\s*\(\s*{_PARTIAL_ENTRY_PASS}\s*\)"
)
_DISCLAIMED_ENTRY_PREFIX_RE = re.compile(
    r"(?:并非|不是|不能|不得|不可|禁止|否认|误写(?:成|为)?|错误说法|错误示例)[\s:：‘“\"']*$"
)
_DISCLAIMED_ENTRY_SUFFIX_RE = re.compile(
    r"^[\s’”\"']*(?:的说法)?\s*(?:是|属于)?\s*(?:错误|不实)"
)
TIER_COLORS = ("#dc2626", "#d97706", "#16a34a", "#16a34a")
RATIO_FIELDS = {
    "gold_wti_ratio": ("wti_settle_usd", 0.15),
    "gold_brent_ratio": ("brent_settle_usd", 0.15),
    "gold_silver_ratio": ("spot_silver_usd", 0.15),
    "gold_spx_ratio": ("spx_close", 0.015),
    "gold_platinum_ratio": ("spot_platinum_usd", 0.05),
}

REQUIRED_KEYS = {
    "DAILY_META": ["tag", "kpis"],
    "DAILY_VERDICT": ["level", "headline"],
    "DAILY_SIGNAL_NOISE": ["signals", "noises"],
    "DAILY_PERSONA": ["cards"],
    "DAILY_GLOSSARY": ["terms"],
    "DAILY_LAYER_BADGE": ["label"],
    "DAILY_TRUST_BAR": ["items"],
    "DAILY_CHART_TIMELINE": ["points"],
    "DAILY_CHART_SWITCH": ["gauges", "checks"],
    "DAILY_CHART_CROSS": ["items"],
}

_STYLE_SKIP_KEYS = {
    "accent", "color", "fill", "text_color", "align", "anchor", "label_pos",
    "tone", "group", "status_color", "unit_prefix", "unit_suffix", "level",
}

# Unicode-safe parallel score regex (catches decimal 0.0/6..6.5/6, integer 0/6..6/6, and fullwidth ／6)
PARALLEL_SCORE_RE = re.compile(r"(?<![0-9.])[0-6](?:\.[05])?\s*[/／]\s*6(?![0-9])")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
RAW_HTML_LEAK_RE = re.compile(
    r"</?(?:div|span|table|thead|tbody|tr|td|th|svg|rect|path|circle|line|polygon|polyline|"
    r"p|ul|ol|li|script|style|iframe|img|h[1-6]|font|center)\b",
    re.IGNORECASE,
)
EXCL_RE = re.compile(r"[!！‼⁉❗❕]")
LIST_OR_BLOCK_RE = re.compile(r"^(?:#|\||[-*•]\s|>\s?|\d+\.\s|---+$)")


def _vis_width(s: str) -> float:
    return sum(1.0 if ord(ch) > 127 else 0.55 for ch in str(s).strip())


def find_layer01_end(raw_md: str) -> int:
    """Locate character offset in raw Markdown where Layer 0-1 ends and Layer 2 begins."""
    patterns = [
        r"^#\s*第二部分",
        r"^##\s*专题一",
        r"^##\s*周末专题",
        r'<!--\s*DAILY_LAYER_BADGE\s*\{[^}]*"tone"\s*:\s*"deep"',
    ]
    earliest = len(raw_md)
    for pat in patterns:
        m = re.search(pat, raw_md, re.MULTILINE | re.DOTALL)
        if m and m.start() < earliest:
            earliest = m.start()
    return earliest


def flatten_json_strings(obj, skip_style_keys: bool = True) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return "\n".join(flatten_json_strings(x, skip_style_keys=skip_style_keys) for x in obj)
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            if skip_style_keys and k in _STYLE_SKIP_KEYS:
                continue
            parts.append(flatten_json_strings(v, skip_style_keys=skip_style_keys))
        return "\n".join(parts)
    return ""


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _edition_key(edition_id: object) -> tuple[str, str, int] | None:
    match = EDITION_ID_RE.fullmatch(edition_id) if isinstance(edition_id, str) else None
    if not match:
        return None
    date, slot, revision = match.groups()
    if revision == "1" or not _parse_timestamp(f"{date} {slot[:2]}:{slot[2:]}"):
        return None
    return date, slot, int(revision or 1)


def _filename_edition(path: Path) -> str | None:
    match = DAILY_FILENAME_RE.fullmatch(path.name)
    if not match:
        return None
    date, slot, revision = match.groups()
    return f"{date}_{slot}" + (f"_r{revision}" if revision else "")


def _valid_number(value: object) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _snapshot_numbers(data: dict, label: str, errors: list[str], keys: tuple[str, ...], *, positive: bool = False) -> bool:
    invalid = [k for k in keys if not _valid_number(data.get(k)) or (positive and data[k] <= 0)]
    if invalid:
        errors.append(f"[Gate 5 数值字段缺失或非法] {label}: {', '.join(invalid)}")
    return not invalid


def _check_vix_snapshot(
    snap: dict, as_of: datetime | None, errors: list[str], *, schedule: tuple | None = None,
) -> bool | None:
    observations = snap.get("vix_10d_session_closes")
    if not isinstance(observations, list) or len(observations) != 10 or any(
        not isinstance(row, dict)
        or not _parse_timestamp(f"{row.get('date')} 00:00")
        or not _valid_number(row.get("close"))
        or row["close"] <= 0
        for row in observations
    ):
        errors.append("[Gate 5 VIX 回看区间非法] 须记录十个完整交易日的日期和收盘值")
        return None
    dates = [row["date"] for row in observations]
    if dates != sorted(set(dates)) or (as_of is not None and dates[-1] > as_of.date().isoformat()):
        errors.append("[Gate 5 VIX 回看日期非法] 日期须按交易日升序、不重复且不晚于快照")
        return None
    peak = max(row["close"] for row in observations)
    peak_dates = {row["date"] for row in observations if row["close"] == peak}
    if (
        snap.get("vix_10d_window_end") != dates[-1]
        or snap.get("vix_close") != observations[-1]["close"]
        or snap.get("vix_10d_peak_close") != peak
        or not isinstance(snap.get("vix_10d_peak_date"), str)
        or snap["vix_10d_peak_date"] not in peak_dates
    ):
        errors.append("[Gate 5 VIX 回看数值冲突] 末日、官收或十日收盘峰未与交易日序列对齐")
        return None
    observed_at = _parse_timestamp(snap.get("vix_live_as_of"))
    if as_of is not None and schedule is not None and not check_vix_period(snap, as_of, observed_at, schedule, errors):
        return None
    quote_key = "vix_live" if snap.get("vix_live") is not None else "vix_close"
    if quote_key == "vix_live":
        if observed_at is None or (as_of is not None and observed_at > as_of):
            errors.append("[Gate 5 VIX 时间非法] vix_live_as_of 须为不晚于快照的有效观测时间")
    if not _snapshot_numbers(snap, DAILY_SNAPSHOT_PATH.name, errors, (quote_key,), positive=True):
        return None
    return snap[quote_key] < 30 or Decimal(str(snap[quote_key])) <= Decimal(str(peak)) * Decimal("0.9")


def _check_institutional_snapshot(snap: dict, label: str, errors: list[str]) -> None:
    targets = snap.get("institutional_targets")
    if not isinstance(targets, list) or not targets or any(
        not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip()
        or row.get("kind") not in ("pt", "avg", "horizon", "stale")
        or any(not _valid_number(row.get(k)) for k in ("lo", "base", "hi"))
        or not 0 < row["lo"] <= row["base"] <= row["hi"]
        or ("annual_average_usd" in row and (not _valid_number(row["annual_average_usd"]) or row["annual_average_usd"] <= 0))
        for row in targets
    ):
        errors.append(f"[Gate 5 机构样本结构错] {label}: 须列示机构、期限及有效点位区间")
        return
    yearend = [row["base"] for row in targets if row["kind"] == "pt"]
    annual = [row["base"] for row in targets if row["kind"] == "avg"]
    annual.extend(row["annual_average_usd"] for row in targets if "annual_average_usd" in row)
    for key, values in (("yearend", yearend), ("avg", annual)):
        count = snap.get(f"bank_2027_{key}_sample_count")
        mid = snap.get(f"bank_2027_{key}_median_usd")
        if not values or type(count) is not int or count != len(values) or mid != statistics.median(values):
            errors.append(f"[Gate 5 机构样本汇总冲突] {label}: {key} 样本数、中位须由同期限记录复算")


def _read_vix_calendar(as_of: datetime, errors: list[str], *, verified_by: date) -> tuple | None:
    try:
        calendar = json.loads(MARKET_CALENDAR_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"[外置日历读取失败] {exc}")
        return None
    return vix_calendar(calendar, as_of, errors, verified_by=verified_by)


def validate_snapshot_file(
    snap_path: Path, errors: list[str], warnings: list[str], *, validated_on: date | None = None,
) -> dict | None:
    label = snap_path.name
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"[Gate 5 数据源缺失或损坏] {label}: {exc}")
        return None
    if not isinstance(snap, dict) or not snap:
        errors.append(f"[Gate 5 数据源非法] {label} 必须为非空 JSON 对象")
        return None

    is_daily = snap_path == DAILY_SNAPSHOT_PATH
    as_of = _parse_timestamp(snap.get("as_of_short"))
    if as_of is None:
        errors.append(f"[Gate 5 快照时间非法] {label}: as_of_short 须为有效 YYYY-MM-DD HH:MM")
    tier = snap.get("tier_code")
    if tier not in ("Tier 0", "Tier 1", "Tier 2", "Tier 3"):
        errors.append(f"[Gate 5 档位非法] {label}: tier_code 必须为 Tier 0–3")
    if snap.get("daily_alert_level") not in ("L0", "L1", "L2"):
        errors.append(f"[Gate 5 紧迫度非法] {label}: daily_alert_level 必须为 L0/L1/L2")
    if snap.get("a_class_tranche_split") != "30% + 45% + 25%":
        errors.append(f"[Gate 5 分批比例错] {label}: 应为 30% + 45% + 25%")
    if is_daily or "new_buy_allowed" in snap:
        buy = snap.get("new_buy_allowed")
        if type(buy) is not bool or buy != (tier != "Tier 0"):
            errors.append(f"[Gate 5 SSOT 开关冲突] {label}: new_buy_allowed 必须为布尔值并与 {tier!r} 一致")

    gates = snap.get("tier1_gates")
    if not isinstance(gates, list) or len(gates) != 4 or any(
        not isinstance(g, dict) or type(g.get("passed")) is not bool
        or any(not isinstance(g.get(k), str) or not g[k].strip() for k in ("name", "reading", "threshold", "detail"))
        for g in gates
    ):
        errors.append(f"[Gate 5 红绿灯结构错] {label}: 四项须含布尔 passed 及非空 name/reading/threshold/detail")
        gates = None
    if gates is not None and (
        type(snap.get("tier1_passed")) is not int
        or snap["tier1_passed"] != sum(g["passed"] for g in gates)
        or type(snap.get("tier1_total")) is not int
        or snap["tier1_total"] != 4
    ):
        errors.append(f"[Gate 5 红绿灯计数冲突] {label}: tier1_passed/tier1_total 须与四项明细一致")
    if tier in ("Tier 1", "Tier 2", "Tier 3") and snap.get("tier1_passed") != 4:
        errors.append(f"[Gate 5 档位与关卡冲突] {label}: 开放新仓前须先满足四项安全条件")

    if is_daily:
        edition = _edition_key(snap.get("edition_id"))
        if edition is None:
            errors.append(f"[Gate 5 刊期非法] {label}: edition_id 须为 YYYY-MM-DD_HHMM[_rN]")
        fixing_date = snap.get("cfets_fixing_date")
        fixing_dt = _parse_timestamp(f"{fixing_date} 00:00")
        if fixing_dt is None or (as_of is not None and fixing_dt.date() > as_of.date()):
            errors.append(f"[Gate 5 中间价日期非法] {label}: cfets_fixing_date 须为不晚于快照的交易日期")
        _snapshot_numbers(snap, label, errors, ("us10y_pct", "dfii10_live_pct", "dxy", "cfets_cny_fixing", "vix_close", "on_rrp_usd_m", "comex_copper_usd_lb"))
        new_rules = edition is not None and edition > LAST_LEGACY_EDITION
        schedule = None
        if as_of is not None:
            verified_by = validated_on or datetime.now(BEIJING).date()
            if edition is not None and edition[2] == 1:
                verified_by = min(verified_by, as_of.date())
            schedule = _read_vix_calendar(as_of, errors, verified_by=verified_by)
        if new_rules and as_of is not None:
            check_edition_time(edition, as_of, errors)
            if not cutoff_displayed(snap.get("as_of_bjt"), as_of):
                errors.append("[Gate 5 快照展示时间错] as_of_bjt 须展示与 as_of_short 一致的北京时间")
            passed = _check_vix_snapshot(snap, as_of, errors, schedule=schedule) if schedule is not None else None
            recheck_entry_gates(
                snap, as_of, passed, errors,
                exceptions=schedule[1] if schedule is not None else {},
            )
        else:
            passed = _check_vix_snapshot(snap, as_of, errors)
            if gates is not None and passed is not None and gates[2]["passed"] != passed:
                errors.append(f"[Gate 5 VIX 第三关冲突] {label}: 应过关={passed}（低于 30 或较十日收盘峰回落至少 10%）")

    for key in snap:
        if re.fullmatch(r"cross_ratios_\d{4}", key):
            warnings.append(f"[Gate 5 遗留日期键] {label} 保留旧键 {key!r}，请使用 cross_ratios")
    if "etf_cn" in snap and not isinstance(snap["etf_cn"], dict):
        errors.append(f"[Gate 5 场内 ETF 字段错] {label}: etf_cn 须为对象")

    prices = ("spot_gold_ny_close_usd", "spot_gold_ny_close_rounded", "spot_gold_prev_close_usd")
    if _snapshot_numbers(snap, label, errors, prices, positive=True) and _snapshot_numbers(snap, label, errors, ("spot_gold_ny_change_pct",)):
        ny_close, rounded, prev_close = (snap[k] for k in prices)
        calc_chg = ((ny_close / prev_close) - 1.0) * 100.0
        if type(rounded) is not int or abs(rounded - ny_close) > 0.5:
            errors.append(f"[Gate 5 现货四舍五入冲突] {label}: {rounded} 与 {ny_close} 不一致")
        if abs(snap["spot_gold_ny_change_pct"] - calc_chg) > 0.05:
            errors.append(f"[Gate 5 快照算术冲突] {label}: 现货涨跌幅应约为 {calc_chg:.2f}%")

    channels = snap.get("rmb_channels")
    if not isinstance(channels, dict):
        errors.append(f"[Gate 5 渠道数据缺失] {label}: rmb_channels 须为对象")
    elif _snapshot_numbers(channels, f"{label}.rmb_channels", errors, ("brand_store_rmb", "bank_bar_plus_craft_rmb"), positive=True) and _snapshot_numbers(channels, f"{label}.rmb_channels", errors, ("wedding_save_per_g_rmb", "wedding_save_50g_rmb", "wedding_save_pct")):
        brand = channels["brand_store_rmb"]
        save = brand - channels["bank_bar_plus_craft_rmb"]
        for key, expected, tolerance in (
            ("wedding_save_per_g_rmb", save, 0.01),
            ("wedding_save_50g_rmb", save * 50, 0.01),
            ("wedding_save_pct", save / brand * 100, 0.15),
        ):
            if abs(channels[key] - expected) > tolerance:
                errors.append(f"[Gate 5 快照渠道算术错] {label}: {key} 应约为 {expected:.2f}")

    ratios = snap.get("cross_ratios")
    if not isinstance(ratios, dict):
        errors.append(f"[Gate 5 跨资产比值缺失] {label}: cross_ratios 须为对象")
    else:
        for key, (denominator, tolerance) in RATIO_FIELDS.items():
            if not _snapshot_numbers(ratios, f"{label}.cross_ratios", errors, (key,), positive=True):
                continue
            if _snapshot_numbers(snap, label, errors, ("spot_gold_ny_close_usd", denominator), positive=True):
                expected = snap["spot_gold_ny_close_usd"] / snap[denominator]
                if abs(ratios[key] - expected) > tolerance:
                    errors.append(f"[Gate 5 跨资产比值偏差] {label}: {key} 应约为 {expected:.3f}")

    # Gate G6: Additional deterministic snapshot math checks (when required fields are present)
    if (
        _valid_number(snap.get("fair_value_rmb"))
        and _valid_number(snap.get("fair_value_usd"))
        and _valid_number(snap.get("usd_cny_1630"))
        and snap["usd_cny_1630"] > 0
    ):
        exp_fv_rmb = round(snap["fair_value_usd"] * snap["usd_cny_1630"] / 31.1034768)
        if abs(snap["fair_value_rmb"] - exp_fv_rmb) > 0.6:
            errors.append(
                f"[Gate G6 快照算术错] {label}: fair_value_rmb={snap['fair_value_rmb']} "
                f"与 round({snap['fair_value_usd']}×{snap['usd_cny_1630']}/31.1034768)={exp_fv_rmb} 偏离 > 0.6"
            )
    if (
        _valid_number(snap.get("dfii10_live_pct"))
        and _valid_number(snap.get("t10yie_fred_pct"))
        and _valid_number(snap.get("us10y_pct"))
    ):
        if abs((snap["dfii10_live_pct"] + snap["t10yie_fred_pct"]) - snap["us10y_pct"]) > 0.08:
            errors.append(
                f"[Gate G6 利率恒等式冲突] {label}: dfii10({snap['dfii10_live_pct']}) + "
                f"t10yie({snap['t10yie_fred_pct']}) 与 us10y({snap['us10y_pct']}) 偏离 > 0.08"
            )
    if (
        _valid_number(snap.get("gdx_gld_ratio"))
        and _valid_number(snap.get("gdx_close_usd"))
        and _valid_number(snap.get("gld_close_usd"))
        and snap["gld_close_usd"] > 0
    ):
        exp_ratio = snap["gdx_close_usd"] / snap["gld_close_usd"]
        if abs(snap["gdx_gld_ratio"] - exp_ratio) > 0.0006:
            errors.append(
                f"[Gate G6 金矿比值算术错] {label}: gdx_gld_ratio={snap['gdx_gld_ratio']} "
                f"与 {snap['gdx_close_usd']}/{snap['gld_close_usd']}={exp_ratio:.4f} 偏离 > 0.0006"
            )
    if (
        _valid_number(snap.get("spot_gold_live_change_pct"))
        and _valid_number(snap.get("spot_gold_live_usd"))
        and _valid_number(snap.get("spot_gold_ny_close_usd"))
        and snap["spot_gold_ny_close_usd"] > 0
    ):
        exp_live_chg = ((snap["spot_gold_live_usd"] / snap["spot_gold_ny_close_usd"]) - 1.0) * 100.0
        if abs(snap["spot_gold_live_change_pct"] - exp_live_chg) > 0.06:
            errors.append(
                f"[Gate G6 实时涨跌幅算术错] {label}: spot_gold_live_change_pct={snap['spot_gold_live_change_pct']} "
                f"与 ((live/ny_close)-1)*100={exp_live_chg:.2f}% 偏离 > 0.06"
            )

    _check_institutional_snapshot(snap, label, errors)
    if is_daily and "data_caveats" in snap:
        _validate_data_caveats(snap.get("data_caveats"), label, errors)
    return snap


def _validate_data_caveats(caveats: object, label: str, errors: list[str]) -> None:
    """Validate structured data_caveats array and ensure zero internal engineering leaks."""
    if not isinstance(caveats, list):
        errors.append(f"[Gate 5 信息缺口结构错] {label}: data_caveats 须为数组")
        return
    req_fields = ("id", "market", "category", "severity", "item", "detail", "impact", "next_review")
    seen_ids: set[str] = set()
    for idx, entry in enumerate(caveats):
        if not isinstance(entry, dict):
            errors.append(f"[Gate 5 信息缺口结构错] {label}: data_caveats[{idx}] 须为对象")
            continue
        for fk in req_fields:
            val = entry.get(fk)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"[Gate 5 信息缺口缺项] {label}: data_caveats[{idx}] 缺少非空字段 {fk}")
        cid = str(entry.get("id", "")).strip()
        if cid:
            if cid in seen_ids:
                errors.append(f"[Gate 5 信息缺口重复] {label}: data_caveats id '{cid}' 重复")
            seen_ids.add(cid)
        cat = str(entry.get("category", "")).strip()
        if cat and cat not in _CAVEAT_ALLOWED_CATEGORIES:
            errors.append(f"[Gate 5 信息缺口枚举错] {label}: data_caveats[{idx}].category={cat!r} 非法")
        sev = str(entry.get("severity", "")).strip()
        if sev and sev not in _CAVEAT_ALLOWED_SEVERITIES:
            errors.append(f"[Gate 5 信息缺口枚举错] {label}: data_caveats[{idx}].severity={sev!r} 非法")
        for text_f in ("item", "detail", "impact"):
            txt = str(entry.get(text_f, ""))
            leaks = _INTERNAL_FILENAME_LEAK_RE.findall(txt) + SCORECARD_BANNED_RE.findall(txt)
            if leaks:
                errors.append(
                    f"[Gate 5 信息缺口内部词泄露] {label}: data_caveats[{idx}].{text_f} 含禁止内部词: {sorted(set(leaks))}"
                )


def _find_banned_layer01_tokens(text: str, *, is_converged: bool = False) -> list[str]:
    ascii_pats = _CONVERGED_BANNED_ASCII_PATTERNS if is_converged else _BANNED_ASCII_PATTERNS
    literals = CONVERGED_BANNED_LAYER01_LITERAL if is_converged else BANNED_LAYER01_LITERAL
    hits: list[str] = []
    for tok, pat in ascii_pats:
        m = pat.search(text)
        if m:
            hits.append(m.group(0) if tok == "V2/V6/V7版本号" else tok)
    for tok in literals:
        if tok in text:
            hits.append(tok)
    return hits


def _validate_directive_schema(
    kind: str, parsed: dict, errors: list[str], warnings: list[str], *, is_converged: bool = False,
) -> None:
    if not isinstance(parsed, dict):
        errors.append(f"[Gate 0 Schema 非对象] <!-- {kind} --> 顶层必须为 JSON 对象")
        return
    for req_k in REQUIRED_KEYS.get(kind, []):
        if req_k not in parsed:
            errors.append(f"[Gate 0 Schema 缺必填键] <!-- {kind} --> 缺少字段 '{req_k}'")
    if kind.startswith("DAILY_CHART_"):
        try:
            normalize_chart(kind, parsed)
        except ValueError as exc:
            errors.append(f"[Gate 0 图表数值结构错] {exc}")

    if kind == "DAILY_META":
        kpis = parsed.get("kpis")
        if not isinstance(kpis, list):
            errors.append("[Gate 0 KPI 结构错] DAILY_META.kpis 须为数组")
        else:
            if is_converged:
                if not (4 <= len(kpis) <= 6):
                    warnings.append(f"[Gate 0 KPI 数量] DAILY_META.kpis 须为 4–6 张卡，实际 {len(kpis)} 张")
            else:
                if len(kpis) != 6:
                    warnings.append(f"[Gate 0 KPI 数量] DAILY_META.kpis 建议为 6 张卡，实际 {len(kpis)} 张")
            for idx, k in enumerate(kpis, 1):
                if not isinstance(k, dict) or any(not isinstance(k.get(f), str) for f in ("label", "val", "sub")):
                    errors.append(f"[Gate 0 KPI 结构错] DAILY_META.kpis[{idx}] 须含 label/val/sub 文本")
                elif _vis_width(k.get("sub", "")) > 17.5:
                    warnings.append(f"[Gate 0 KPI sub 偏长] DAILY_META.kpis[{idx}].sub='{k['sub']}' 视觉宽 {_vis_width(k['sub']):.1f} > 17.5 汉字当量")
    elif kind == "DAILY_VERDICT":
        lvl = str(parsed.get("level", "")).upper()
        if lvl not in ("L0", "L1", "L2"):
            errors.append(f"[Gate 0 紧迫度非法] DAILY_VERDICT.level='{lvl}' 必须为 L0/L1/L2")
        if "🟢" in str(parsed.get("badge", "")):
            errors.append("[Gate 0 禁用绿牌] DAILY_VERDICT.badge 严禁使用绿色 🟢（防止与买金绿灯撞色）")
        if not all(k in parsed for k in ("traffic_light", "bullets", "risk_line")) or not isinstance(parsed.get("bullets"), list):
            errors.append("[Gate 0 VERDICT 结构错] DAILY_VERDICT 须含 traffic_light/risk_line 及数组 bullets")
    elif kind == "DAILY_SIGNAL_NOISE":
        for sn_k in ("signals", "noises"):
            arr = parsed.get(sn_k)
            if not isinstance(arr, list) or any(not isinstance(it, dict) or not all(f in it for f in ("head", "body")) for it in arr):
                errors.append(f"[Gate 0 信号卡项错] DAILY_SIGNAL_NOISE.{sn_k} 须为含 head/body 对象的数组")
        sigs = parsed.get("signals", [])
        if isinstance(sigs, list) and len(sigs) > 2:
            warnings.append(f"[Gate 0 信号超标] DAILY_SIGNAL_NOISE.signals 有 {len(sigs)} 件（规范建议 0–2 件）")
    elif kind == "DAILY_PERSONA":
        cards = parsed.get("cards")
        if not isinstance(cards, list) or not cards or any(not isinstance(c, dict) or not all(f in c for f in ("group", "heading", "actions")) or not isinstance(c.get("actions"), list) for c in cards):
            errors.append("[Gate 0 读者卡项错] DAILY_PERSONA.cards 须为非空数组且每项含 group/heading/数组 actions")
    elif kind == "DAILY_GLOSSARY":
        terms = parsed.get("terms")
        if not isinstance(terms, list) or not terms or any(not isinstance(t, dict) or not all(f in t for f in ("term", "plain")) for t in terms):
            errors.append("[Gate 0 词典项错] DAILY_GLOSSARY.terms 须为非空数组且每项含 term/plain")
    elif kind == "DAILY_LAYER_BADGE":
        tone = parsed.get("tone")
        if tone is not None and tone not in ("deep", "pro"):
            errors.append(f"[Gate 0 分层标非法] DAILY_LAYER_BADGE.tone='{tone}' 必须为 deep 或 pro")
    elif kind == "DAILY_TRUST_BAR":
        items = parsed.get("items")
        if not isinstance(items, list) or len(items) != 3 or any(not isinstance(item, str) or not item.strip() for item in items):
            errors.append("[Gate 0 质检徽章结构错] DAILY_TRUST_BAR.items 须为三条非空文字")
    elif kind == "DAILY_CHART_TIMELINE":
        if "zones" in parsed and "highlight_zones" not in parsed:
            errors.append("[Gate 0 时间轴错键] DAILY_CHART_TIMELINE 请使用 highlight_zones 而非 zones")
        pts = parsed.get("points")
        if not isinstance(pts, list) or not pts:
            errors.append("[Gate 0 时间轴空] DAILY_CHART_TIMELINE.points 不能为空")
    elif kind == "DAILY_CHART_SWITCH":
        checks = parsed.get("checks", [])
        if isinstance(checks, list) and len(checks) != 4:
            errors.append(f"[Gate 0 四步红绿灯数量错] DAILY_CHART_SWITCH.checks 应为 4 项，实际 {len(checks)} 项")
        if not isinstance(checks, list) or any(
            not isinstance(c, dict) or type(c.get("passed")) is not bool
            or any(not isinstance(c.get(f), str) for f in ("name", "line1", "line2"))
            for c in checks
        ):
            errors.append("[Gate 0 红绿灯项错] DAILY_CHART_SWITCH.checks 每项须含布尔 passed 及 name/line1/line2 文本")
        gauges = parsed.get("gauges")
        if not isinstance(gauges, list) or not gauges:
            errors.append("[Gate 0 水位尺空] DAILY_CHART_SWITCH.gauges 须为非空数组")
            return
        for idx, g in enumerate(gauges, 1):
            if not isinstance(g, dict) or not all(f in g for f in ("label", "value_text", "pct")) or ("safe_pct" in g and "threshold_pct" not in g):
                errors.append(f"[Gate 0 水位尺项错] gauges[{idx}] 须含 label/value_text/pct（且用 threshold_pct 非 safe_pct）")
                continue
    elif kind == "DAILY_CHART_CROSS":
        items = parsed.get("items", [])
        if not isinstance(items, list) or not items:
            errors.append("[Gate 0 跨资产图空] DAILY_CHART_CROSS.items 不能为空")
        else:
            for idx, it in enumerate(items, 1):
                if not isinstance(it, dict) or not all(f in it for f in ("label", "pct")):
                    errors.append(f"[Gate 0 跨资产项错] DAILY_CHART_CROSS.items[{idx}] 须含 label/pct")
                    continue
                lw = _vis_width(str(it["label"]))
                if lw > 9.5:
                    errors.append(f"[Gate 0 图2标签撞栏] items[{idx}].label='{it['label']}' 宽 {lw:.1f} > 9.5（请压至 ≤8.5）")
                elif lw > 9.0:
                    warnings.append(f"[Gate 0 图2标签偏宽] items[{idx}].label='{it['label']}' 宽 {lw:.1f} > 9.0（建议 ≤8.5）")
        reverse_items = parsed.get("reverse_items", [])
        if not isinstance(reverse_items, list) or any(
            not isinstance(ri, dict) or not all(f in ri for f in ("label", "detail")) for ri in reverse_items
        ):
            errors.append("[Gate 0 反向指标项错] DAILY_CHART_CROSS.reverse_items 每项须含 label/detail")


def _strip_comments_keep_lines(s: str) -> str:
    return HTML_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), s)


def _strip_code_and_neq(s: str) -> str:
    t = re.sub(r"```.*?```", "", s, flags=re.DOTALL)
    t = re.sub(r"`[^`]+`", "", t)
    return t.replace("!=", "")


def _check_report_structure(
    raw: str, directives: dict[str, list[dict]], *, is_master: bool, is_converged: bool = False, errors: list[str],
) -> None:
    visible = _strip_comments_keep_lines(raw)
    for part in ("第一部分", "第三部分"):
        if not re.search(rf"^#\s*{part}", visible, re.MULTILINE):
            errors.append(f"[Gate 0 缺章节] 缺少 {part} 标题")
    if find_layer01_end(raw) == len(raw):
        errors.append("[Gate 0 缺章节] 缺少深读分层边界")
    required_card_counts = {"DAILY_VERDICT": 1, "DAILY_PERSONA": 1}
    if not is_converged:
        required_card_counts["DAILY_TRUST_BAR"] = 1
    if not is_master:
        required_card_counts.update({
            "DAILY_META": 1,
            "DAILY_SIGNAL_NOISE": 1,
            "DAILY_CHART_TIMELINE": 1,
            "DAILY_CHART_CROSS": 1,
            "DAILY_CHART_SWITCH": 1,
        })
    for kind, count in required_card_counts.items():
        if len(directives.get(kind, [])) != count:
            errors.append(f"[Gate 0 组件数量错] {kind} 必须出现 {count} 次")
    if is_converged:
        for opt_kind in ("DAILY_TRUST_BAR", "DAILY_GLOSSARY"):
            if len(directives.get(opt_kind, [])) > 1:
                errors.append(f"[Gate 0 组件数量错] {opt_kind} 最多出现 1 次")
    elif not directives.get("DAILY_GLOSSARY"):
        errors.append("[Gate 0 缺组件] 至少需要一处 DAILY_GLOSSARY")
    if is_master:
        tokens = re.findall(r"(?m)^\s*<!--\s*CHART_(\d+|1_AND_2)\s*-->\s*$", raw)
        counts = Counter(n for token in tokens for n in (("1", "2") if token == "1_AND_2" else (token,)))
        if counts != Counter(str(n) for n in range(1, 8)):
            errors.append("[Gate 0 主报告图数错误] 七张主报告图必须各出现一次")


_CN_COUNT_MAP: dict[str, int] = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}
_SIGNAL_COUNT_RE = re.compile(
    r"([1-9]|[一二两三四五])\s*(?:件|条|个)\s*(?:晚间|早间|盘前|盘后|实盘|真|核心)?(?:真信号|信号)"
)
_NOISE_COUNT_RE = re.compile(
    r"([1-9]|[一二两三四五])\s*(?:件|条|个)\s*(?:刚出现的)?(?:晚间|早间|盘前|实盘|热传|隔夜|全网|今日|流行)?(?:假象|误导|谣言|噪音)"
)


def _parse_small_cn_int(tok: str) -> int | None:
    if tok.isdigit():
        return int(tok)
    return _CN_COUNT_MAP.get(tok)


def _check_directive_item_counts(
    raw: str, directives: dict[str, list[dict]], errors: list[str],
) -> None:
    """Verify explicit signal/noise counts stated in Part 1 lead or DAILY_SIGNAL_NOISE.title match item arrays."""
    sn_list = directives.get("DAILY_SIGNAL_NOISE", [])
    if len(sn_list) != 1 or not isinstance(sn_list[0], dict):
        return
    sn = sn_list[0]
    signals = sn.get("signals")
    noises = sn.get("noises")
    if not isinstance(signals, list) or not isinstance(noises, list):
        return

    m_p1 = re.search(r"^#\s*第一部分", raw, re.MULTILINE)
    m_sn = re.search(r"<!--\s*DAILY_SIGNAL_NOISE\b", raw)
    lead_seg = ""
    if m_p1 and m_sn and m_p1.start() < m_sn.start():
        lead_seg = _strip_comments_keep_lines(raw[m_p1.start() : m_sn.start()])
    title_str = str(sn.get("title", "")) if isinstance(sn.get("title"), str) else ""
    scan_text = f"{lead_seg}\n{title_str}"

    for m in _SIGNAL_COUNT_RE.finditer(scan_text):
        stated = _parse_small_cn_int(m.group(1))
        if stated is not None and stated != len(signals):
            errors.append(
                f"[Gate 0 信号计数冲突] 文中声称「{m.group(0)}」，但 DAILY_SIGNAL_NOISE.signals 实有 {len(signals)} 项"
            )
    for m in _NOISE_COUNT_RE.finditer(scan_text):
        stated = _parse_small_cn_int(m.group(1))
        if stated is not None and stated != len(noises):
            errors.append(
                f"[Gate 0 噪音计数冲突] 文中声称「{m.group(0)}」，但 DAILY_SIGNAL_NOISE.noises 实有 {len(noises)} 项"
            )


def _check_daily_verdict(directives: dict[str, list[dict]], snap: dict, errors: list[str]) -> None:
    tier = snap.get("tier_code")
    passed = snap.get("tier1_passed")
    expected_checks = snap.get("tier1_gates")
    if tier not in ("Tier 0", "Tier 1", "Tier 2", "Tier 3") or type(passed) is not int or not isinstance(expected_checks, list):
        return
    verdict = next(iter(directives.get("DAILY_VERDICT", [])), {})
    if (
        verdict.get("tier_code") != tier
        or type(verdict.get("new_buy_allowed")) is not bool
        or verdict["new_buy_allowed"] != snap.get("new_buy_allowed")
        or type(verdict.get("tier1_passed")) is not int
        or verdict["tier1_passed"] != passed
    ):
        errors.append("[Gate 5 裁决卡与快照冲突] DAILY_VERDICT 的档位、开关或过关数与快照不一致")
    if str(verdict.get("level", "")).upper() != snap.get("daily_alert_level"):
        errors.append("[Gate 5 紧迫度与快照冲突] DAILY_VERDICT.level 与快照不一致")
    chart = next(iter(directives.get("DAILY_CHART_SWITCH", [])), {})
    if "status_color" in chart and str(chart["status_color"]).lower() != TIER_COLORS[int(tier[-1])]:
        errors.append("[Gate 5 图 3 色值冲突] status_color 须采用对应档位的圆点颜色")
    checks = chart.get("checks", [])
    if not isinstance(checks, list) or [
        c.get("passed") for c in checks if isinstance(c, dict) and type(c.get("passed")) is bool
    ] != [g.get("passed") for g in expected_checks if isinstance(g, dict)]:
        errors.append("[Gate 5 图 3 与快照冲突] 四项过关状态或顺序与快照不一致")
    edition = _edition_key(snap.get("edition_id"))
    if edition is not None and edition > LAST_LEGACY_EDITION and (
        not isinstance(checks, list) or tuple(check.get("id") for check in checks if isinstance(check, dict)) != ENTRY_GATE_IDS
    ):
        errors.append("[Gate 5 图 3 顺序错] checks 须按快照四关 id 标注")
    meta = next(iter(directives.get("DAILY_META", [])), {})
    kpis = meta.get("kpis", [])
    kpi = next(
        (k for k in kpis if isinstance(k, dict) and "红绿灯" in str(k.get("label", ""))),
        {},
    ) if isinstance(kpis, list) else {}
    expected_label = TIER_LABELS[int(tier[-1])]
    for source, value in (
        ("封面", kpi.get("val")),
        ("裁决卡", verdict.get("traffic_light")),
        ("图 3", chart.get("status_line")),
    ):
        if not isinstance(value, str) or expected_label not in value or GATE_COUNT_RE.findall(value) != [str(passed)]:
            errors.append(f"[Gate 5 {source}口径冲突] 须显示 {expected_label} 与 {passed}/4")
        elif tier == "Tier 0" and RED_LIGHT_CONFLICT_RE.search(value):
            errors.append(f"[Gate 5 {source}动作冲突] 黄金处于红灯，不得标注开新仓")
    _check_tier0_widget_prose(directives, snap, errors)


def _scan_tier0_prose(source: str, text: str, errors: list[str]) -> None:
    plain = unicodedata.normalize("NFKC", html.unescape(re.sub(r"<[^>]+>", "", str(text))))
    for clause in re.split(r"[。！？；\n]", plain):
        for m in _TIER0_PROSE_BUY_RE.finditer(clause):
            prefix = clause[:m.start()]
            tail_seg = re.split(r"[，,、：:→]", prefix)[-1]
            if _TIER0_PROSE_GUARD_RE.search(prefix) or _TIER0_PROSE_GUARD_RE.search(tail_seg):
                continue
            errors.append(f"[Gate 5 {source}动作冲突] 黄金处于红灯停，严禁出现新买/定投开仓指令：{m.group(0)}")


def _check_tier0_widget_prose(directives: dict[str, list[dict]], snap: dict, errors: list[str]) -> None:
    """Extend Tier 0 red-light mutex checks to DAILY_VERDICT headline/bullets and DAILY_PERSONA actions."""
    if snap.get("tier_code") != "Tier 0" and snap.get("new_buy_allowed") is not False:
        return
    verdict = next(iter(directives.get("DAILY_VERDICT", [])), {})
    if isinstance(verdict, dict):
        if isinstance(verdict.get("headline"), str):
            _scan_tier0_prose("DAILY_VERDICT.headline", verdict["headline"], errors)
        for idx, bullet in enumerate(verdict.get("bullets") or [], 1):
            if isinstance(bullet, str):
                _scan_tier0_prose(f"DAILY_VERDICT.bullets[{idx}]", bullet, errors)
    for persona in directives.get("DAILY_PERSONA", []):
        for cidx, card in enumerate(persona.get("cards") or [], 1):
            if not isinstance(card, dict):
                continue
            grp = str(card.get("group", "")).strip().upper()
            for aidx, act in enumerate(card.get("actions") or [], 1):
                if isinstance(act, str):
                    _scan_tier0_prose(f"DAILY_PERSONA.cards[{cidx}:{grp}].actions[{aidx}]", act, errors)


def _check_partial_entry_claims(visible: str, widgets: list[tuple[str, str]], errors: list[str]) -> None:
    """Reject explicit partial-gate entry thresholds in daily prose and rendered cards."""
    for source, raw in [("正文", visible), *widgets]:
        text = unicodedata.normalize("NFKC", html.unescape(raw))
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"</?[A-Za-z][^<>\n]*>|[*_`]", "", text)
        for line in text.splitlines():
            for match in PARTIAL_ENTRY_CLAIM_RE.finditer(line):
                if (
                    _DISCLAIMED_ENTRY_PREFIX_RE.search(line[:match.start()])
                    or _DISCLAIMED_ENTRY_SUFFIX_RE.match(line[match.end():])
                ):
                    continue
                errors.append(f"[Gate 5 四关开仓阈值冲突] {source} 须四关全部通过才可转黄或开新仓：{match[0]}")


def _skip_domestic_brand_check(snap: dict, filename_key: tuple[str, str, int] | None, daily_meta: dict) -> bool:
    caveats = snap.get("data_caveats")
    if isinstance(caveats, list) and any(
        isinstance(c, dict)
        and c.get("category") in ("delayed_official", "holiday_thin")
        and any(kw in (str(c.get("item", "")) + str(c.get("detail", ""))) for kw in ("金店", "国内牌价", "内盘", "春节"))
        for c in caveats
    ):
        return True
    if str(snap.get("overlay_mode", "")).upper() == "B" or str(daily_meta.get("overlay_mode", "")).upper() == "B":
        return True
    day_str = filename_key[0] if filename_key else str(snap.get("as_of_short", ""))[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_str) and MARKET_CALENDAR_PATH.exists():
        try:
            cal = json.loads(MARKET_CALENDAR_PATH.read_text(encoding="utf-8"))
            for ev in cal.get("calendar_overrides", []):
                if (
                    isinstance(ev, dict)
                    and ev.get("overlay_mode") == "B"
                    and isinstance(ev.get("date"), str)
                    and isinstance(ev.get("end_date"), str)
                    and ev["date"] <= day_str <= ev["end_date"]
                ):
                    return True
        except (OSError, ValueError):
            pass
    return False


def check_file(
    md_path: Path,
    daily_snap: dict | None,
    master_snap: dict | None,
    precheck: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    raw = md_path.read_text(encoding="utf-8")

    baseline_matches = list(MASTER_BASELINE_RE.finditer(raw))
    is_master = md_path.name == MASTER_FILENAME or bool(baseline_matches)
    filename_edition = _filename_edition(md_path)
    if filename_edition and baseline_matches:
        errors.append("[Gate 0 基线分轨冲突] 日报不应包含 MASTER_BASELINE")
    if is_master:
        baseline_meta = {}
        snap = master_snap
        try:
            if len(baseline_matches) == 1:
                baseline_meta = json.loads(baseline_matches[0].group(1))
        except json.JSONDecodeError as exc:
            errors.append(f"[Gate 0 MASTER_BASELINE JSON 错] {exc}")
        if not _parse_timestamp(baseline_meta.get("as_of_short")) or baseline_meta.get("snapshot") != MASTER_SNAPSHOT_PATH.name:
            errors.append("[Gate 5 主报告基线锁缺失或非法] 须有唯一的 MASTER_BASELINE，指定 master_snapshot.json 和合法时间")
        elif not snap or snap.get("as_of_short") != baseline_meta["as_of_short"]:
            errors.append("[Gate 5 主报告基线锁冲突] MASTER_BASELINE.as_of_short 与独立快照不一致")
    else:
        snap = daily_snap
    filename_key = _edition_key(filename_edition)
    snapshot_key = _edition_key(daily_snap.get("edition_id")) if daily_snap else None
    is_current_daily = filename_edition is not None and (filename_key is None or snapshot_key is None or filename_key >= snapshot_key)
    is_converged = not is_master and filename_key is not None and filename_key >= CONVERGED_CUTOVER

    layer01_end = find_layer01_end(raw)
    if len(raw) > 3000 and layer01_end == len(raw):
        errors.append("[Gate 0 缺分层边界] 未检测到 Layer 2 边界（需以 `# 第二部分` / `## 专题一` / `## 周末专题` 或 `DAILY_LAYER_BADGE(deep)` 起头）")

    raw_l01 = raw[:layer01_end]
    layer01_vis = _strip_comments_keep_lines(raw_l01)
    full_vis = _strip_comments_keep_lines(raw)

    # Gate 0: Catch & Schema-validate ALL DAILY_* directives (including typos & malformed payloads!)
    daily_meta: dict = {}
    directives: dict[str, list[dict]] = {}
    l01_widget_texts: list[tuple[str, str]] = []
    all_widget_texts: list[tuple[str, str]] = []
    for m in ANY_DAILY_DIRECTIVE_RE.finditer(raw):
        kind, blob = m.group(1), m.group(2).strip()
        if kind not in KNOWN_DIRECTIVES:
            errors.append(f"[Gate 0 未知组件指令] 发现非法/拼写错误指令 <!-- {kind} -->")
            continue
        if not blob.startswith("{") or not blob.endswith("}"):
            errors.append(f"[Gate 0 JSON 格式错] <!-- {kind} --> 载荷不是合法 JSON 对象")
            continue
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError as exc:
            errors.append(f"[Gate 0 JSON 语法错] <!-- {kind} --> 解析失败: {exc}")
            continue
        _validate_directive_schema(kind, parsed, errors, warnings, is_converged=is_converged)
        if not isinstance(parsed, dict):
            continue
        directives.setdefault(kind, []).append(parsed)
        if kind == "DAILY_META":
            daily_meta = parsed
        flat = flatten_json_strings(parsed, skip_style_keys=True)
        all_widget_texts.append((kind, flat))
        if m.start() < layer01_end or kind in ("DAILY_META", "DAILY_VERDICT", "DAILY_SIGNAL_NOISE"):
            l01_widget_texts.append((kind, flat))

    if is_master or filename_edition:
        _check_report_structure(raw, directives, is_master=is_master, is_converged=is_converged, errors=errors)
    if not is_master and directives.get("DAILY_SIGNAL_NOISE"):
        _check_directive_item_counts(raw, directives, errors)
    if is_current_daily or daily_meta.get("edition_id") is not None:
        if filename_key is None or daily_meta.get("edition_id") != filename_edition:
            errors.append("[Gate 0 日报刊期不匹配] DAILY_META.edition_id 须与文件名含修订号一致")
        if _parse_timestamp(daily_meta.get("as_of_short")) is None:
            errors.append("[Gate 0 日报数据时间非法] DAILY_META.as_of_short 须为有效 YYYY-MM-DD HH:MM")
    if filename_key is not None and filename_key > LAST_LEGACY_EDITION:
        cutoff = _parse_timestamp(daily_meta.get("as_of_short"))
        if cutoff is not None:
            check_edition_time(filename_key, cutoff, errors)
            if not cutoff_displayed(daily_meta.get("timestamp"), cutoff):
                errors.append("[Gate 0 封面截点错] DAILY_META.timestamp 须展示与 as_of_short 一致的北京时间")
        _check_edition_ledgers(
            filename_edition, daily_meta.get("as_of_short"), errors, is_current=is_current_daily,
        )
        _check_partial_entry_claims(full_vis, all_widget_texts, errors)
    if is_current_daily:
        if not daily_snap or daily_snap.get("edition_id") != filename_edition or daily_meta.get("as_of_short") != daily_snap.get("as_of_short"):
            errors.append("[Gate 5 日报快照错刊] 文件名、DAILY_META 与 data_snapshot 的 edition_id/as_of_short 须一致")
        else:
            _check_daily_verdict(directives, daily_snap, errors)
    elif is_master and master_snap:
        _check_tier0_widget_prose(directives, master_snap, errors)

    full_combined = full_vis + "\n" + "\n".join(t for _, t in all_widget_texts)

    # Gate 1: Zero banned jargon / internal meta-noise / internal filename leaks / raw HTML leaks
    found_tokens = _find_banned_layer01_tokens(layer01_vis, is_converged=is_converged)
    if found_tokens:
        errors.append(f"[Gate 1 术语/自嗨逃逸] Layer 0–1 正文出现禁止词条: {', '.join(found_tokens)}")
    for kind, txt in l01_widget_texts:
        bad = _find_banned_layer01_tokens(txt, is_converged=is_converged)
        if bad:
            errors.append(f"[Gate 1 组件术语逃逸] Layer 0–1 {kind} 出现禁止词条: {', '.join(bad)}")

    # Full-document condescending slogan ban (ALL layers + ALL widgets incl. DAILY_GLOSSARY for >= CONVERGED_CUTOVER)
    if is_converged:
        slogan_hits = [tok for tok in CONVERGED_BANNED_SLOGANS if tok in full_combined]
        if slogan_hits:
            errors.append(
                f"[Gate 1 术语/自嗨逃逸 · 说教口号] 全文及组件严禁出现居高临下口号: {', '.join(slogan_hits)}"
            )

    # Full-document internal filename, version, binary dead-link & engineering term leak check (>= 2026-11-26_0730)
    if not is_master and filename_key is not None and filename_key >= INTERNAL_LEAK_CUTOVER:
        internal_leaks = _INTERNAL_FILENAME_LEAK_RE.findall(full_combined)
        if internal_leaks:
            errors.append(
                f"[Gate 1 内部工程词/文件名泄露] 全文严禁出现内部文件名、版本号或工程术语: {', '.join(sorted(set(internal_leaks)))}"
            )
        bin_leaks = _DEPRECATED_BINARY_LINK_RE.findall(full_combined)
        if bin_leaks:
            errors.append(
                f"[Gate 1 已弃用二进制死链] 纯网页日报严禁包含 .pdf/.docx 或 Releases 离线下载链接: {', '.join(sorted(set(bin_leaks))[:5])}"
            )

    # Raw HTML leakage in visible Markdown AND widget JSON payloads
    no_code_vis = re.sub(r"```.*?```", "", full_vis, flags=re.DOTALL)
    no_code_vis = re.sub(r"`[^`]+`", "", no_code_vis)
    leaks = RAW_HTML_LEAK_RE.findall(no_code_vis)
    if leaks:
        errors.append(f"[Gate 1 原始 HTML 泄露] 正文出现未转义 HTML 标签: {', '.join(sorted(set(leaks)))}")
    for kind, txt in all_widget_texts:
        wleaks = RAW_HTML_LEAK_RE.findall(txt)
        if wleaks:
            errors.append(f"[Gate 1 组件 HTML 泄露] {kind} 含有非法 HTML 标签: {', '.join(sorted(set(wleaks)))}")

    # Gate 2: Calm doctor tone (markdown-stripped hype scan) & zero exclamation marks in Layer 0-1
    full_stripped_md = re.sub(r"\*\*|\*", "", full_combined)
    found_hype = [w for w in BANNED_HYPE_WORDS if w in full_stripped_md]
    if found_hype:
        errors.append(f"[Gate 2 夸张/煽动词] 全文出现禁用词: {', '.join(found_hype)}")

    excl_l01_vis = len(EXCL_RE.findall(_strip_code_and_neq(layer01_vis)))
    if excl_l01_vis > 0:
        errors.append(f"[Gate 2 感叹号红线] Layer 0–1 正文出现 {excl_l01_vis} 个感叹号（规定为 0）")
    for kind, txt in l01_widget_texts:
        c = len(EXCL_RE.findall(_strip_code_and_neq(txt)))
        if c > 0:
            errors.append(f"[Gate 2 组件感叹号] Layer 0–1 {kind} 含 {c} 个感叹号（规定为 0）")

    excl_all = len(EXCL_RE.findall(_strip_code_and_neq(full_combined)))
    excl_cap = 5 if is_converged else 2
    if excl_all > excl_cap:
        warnings.append(f"[Gate 2 感叹号偏多] 全文共 {excl_all} 个感叹号（建议 ≤{excl_cap}）")

    # Gate 3: Parallel score elimination in Layer 0-1 (catches decimal, integer & fullwidth)
    l01_combined = layer01_vis + "\n" + "\n".join(t for _, t in l01_widget_texts)
    ps_hits = PARALLEL_SCORE_RE.findall(l01_combined)
    if ps_hits:
        errors.append(f"[Gate 3 平行打分残留] Layer 0–1 出现已废除的 X/6 打分: {', '.join(sorted(set(ps_hits)))}")

    # Gate 4: Paragraph conciseness in Layer 0-1 (exact original line numbers + visible text length)
    long_paras = []
    for idx, line in enumerate(layer01_vis.splitlines(), 1):
        s = line.strip()
        if not s or LIST_OR_BLOCK_RE.match(s):
            continue
        vis_s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        vis_s = re.sub(r"\*\*|\*|`", "", vis_s)
        if len(vis_s) > 240:
            long_paras.append((idx, len(vis_s)))
    if long_paras:
        warnings.append(
            "[Gate 4 段落偏长] Layer 0–1 有超过 240 字的自然段: "
            + ", ".join(f"L{ln}({ch}字)" for ln, ch in long_paras[:5])
        )
    if is_converged:
        no_fenced_vis = re.sub(r"```.*?```", "", full_vis, flags=re.DOTALL)
        bold_chars = sum(len(x) for x in re.findall(r"\*\*([^*]+)\*\*", no_fenced_vis))
        plain_chars = max(1, len(re.sub(r"\s+", "", no_fenced_vis)))
        bold_pct = (bold_chars / plain_chars) * 100.0
        if bold_pct > 14.0:
            warnings.append(f"[Gate 4 加粗密度偏高] 全文加粗文字占比 {bold_pct:.1f}%（建议 ≤14%）")
        bare_bt = _BARE_NUM_BACKTICK_RE.findall(no_fenced_vis)
        if bare_bt:
            warnings.append(
                f"[Gate 4 裸数字反引号] 请勿用反引号包裹非代码数字/金额（{len(bare_bt)} 处）: {', '.join(bare_bt[:5])}"
            )

    # Gate 5: Stale fact & snapshot consistency checks (edition-aware reconciliation!)
    active_guards = list(PERMANENT_FACT_GUARDS)
    if snap and str(snap.get("as_of_short", "")).startswith("2026-11-24"):
        active_guards.extend(DATE_BOUND_STALE_GUARDS_20261124)
    for stale_tok, reason in active_guards:
        if stale_tok in full_combined:
            errors.append(f"[Gate 5 过时/冲突事实] 检出 '{stale_tok}' — {reason}")

    if snap and (is_master or is_current_daily):
        spot_r = snap.get("spot_gold_ny_close_rounded")
        if type(spot_r) is int:
            if f"{spot_r:,}" not in full_combined and str(spot_r) not in full_combined:
                warnings.append(f"[Gate 5 基准价缺失] 正文未检测到最新现货基准价 {spot_r}")
            ch = snap.get("rmb_channels")
            if (
                isinstance(ch, dict)
                and _valid_number(ch.get("brand_store_rmb"))
                and _valid_number(ch.get("wedding_save_per_g_rmb"))
                and not _skip_domestic_brand_check(snap, filename_key, daily_meta)
            ):
                brand_r = round(ch["brand_store_rmb"])
                save_r = round(ch["wedding_save_per_g_rmb"])
                if f"{brand_r:,}" not in full_combined and str(brand_r) not in full_combined:
                    warnings.append(f"[Gate 5 金店价未对齐] 正文未检测到快照品牌金店价 {brand_r:,}")
                if str(save_r) not in full_combined:
                    warnings.append(f"[Gate 5 省钱差额未对齐] 正文未检测到快照婚庆省钱差额 {save_r} 元/克")

    # Gate 4B: Deterministic G2 / G3 / G6 / G7 / S2 & Layer 2 paragraph cap (>= 2026-11-27_0730 dailies)
    if not is_master and filename_key is not None and filename_key[:2] >= EDITORIAL_DEPTH_CUTOVER[:2]:
        errors.extend(_check_wallet_anchor_grams(full_vis))
        errors.extend(_check_shfe_night_close(md_path.name, full_vis))
        errors.extend(_check_scenario_10pt_and_dots(md_path.name, full_vis))
        errors.extend(_check_tense_drift(md_path.name, full_vis, filename_key[0]))
        errors.extend(_check_credit_spread_ccc(md_path.name, full_vis))
        for kind, wtxt in all_widget_texts:
            wlbl = f"{md_path.name}:{kind}"
            errors.extend(_check_shfe_night_close(wlbl, wtxt))
            errors.extend(_check_scenario_10pt_and_dots(wlbl, wtxt))
            errors.extend(_check_tense_drift(wlbl, wtxt, filename_key[0]))
            errors.extend(_check_credit_spread_ccc(wlbl, wtxt))
        if layer01_end < len(raw):
            layer2_end = _find_layer2_end(raw, layer01_end)
            l2_start_line = raw[:layer01_end].count("\n") + 1
            l2_vis = _strip_comments_keep_lines(raw[layer01_end:layer2_end])
            l2_long: list[tuple[int, int, str]] = []
            for offset, line in enumerate(l2_vis.splitlines()):
                s = line.strip()
                if not s or LIST_OR_BLOCK_RE.match(s):
                    continue
                vis_s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
                vis_s = re.sub(r"\*\*|\*|`", "", vis_s)
                if len(vis_s) > 260:
                    l2_long.append((l2_start_line + offset, len(vis_s), vis_s[:26]))
            if l2_long:
                warnings.append(
                    "[Gate 4 Layer 2 段落偏长] Layer 2 有超过 260 字的自然段: "
                    + ", ".join(f'[L{ln}:{ch}字 "{snip}..."]' for ln, ch, snip in l2_long[:5])
                )

    # Gate 4B: Vector SVG text bounding-box geometry & collision check (3 daily SVGs or 7 master SVGs)
    if not any("[Gate 0 图表数值结构错]" in e or "[Gate 0 JSON 语法错]" in e for e in errors):
        _check_svg_geometry(directives, is_master=is_master, master_snap=master_snap, errors=errors)

    # Web-only publishing mode: Gates 0–5 cover all manuscript, chart-input, snapshot, and ledger gates.
    # Binary PDF/DOCX artifacts are no longer produced or required.
    return errors, warnings


_SVG_GEOM_CACHE: dict[str, object] = {}


def _load_gold_module(mod_name: str, file_path: Path):
    cached = _SVG_GEOM_CACHE.get(mod_name)
    if cached is not None:
        return cached
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    existing = sys.modules.get(mod_name)
    existing_file = getattr(existing, "__file__", None)
    if existing is not None and existing_file and Path(existing_file).resolve() == file_path.resolve():
        _SVG_GEOM_CACHE[mod_name] = existing
        return existing
    spec = importlib.util.spec_from_file_location(f"_gold_lint_{mod_name}", file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {file_path}")
    mod = importlib.util.module_from_spec(spec)
    prev = sys.modules.get("build_daily")
    if mod_name == "build_report":
        gold_daily = _load_gold_module("build_daily", BASE_DIR / "build_daily.py")
        sys.modules["build_daily"] = gold_daily
    try:
        spec.loader.exec_module(mod)
    finally:
        if mod_name == "build_report":
            if prev is None:
                sys.modules.pop("build_daily", None)
            else:
                sys.modules["build_daily"] = prev
    _SVG_GEOM_CACHE[mod_name] = mod
    return mod


def _find_layer2_end(raw_md: str, layer01_end: int) -> int:
    """Locate character offset where Layer 2 ends and Layer 3 begins."""
    tail = raw_md[layer01_end:]
    patterns = [
        r"^#\s*第三部分",
        r'<!--\s*DAILY_LAYER_BADGE\s*\{[^}]*"tone"\s*:\s*"pro"',
    ]
    earliest = len(raw_md)
    for pat in patterns:
        m = re.search(pat, tail, re.MULTILINE | re.DOTALL)
        if m and (layer01_end + m.start()) < earliest:
            earliest = layer01_end + m.start()
    return earliest


_WALLET_WAN_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*万")


def _resolve_wallet_principal(text: str, pos: int) -> float | None:
    """Resolve explicit 10万 / 1万 principal near pos; return None for other tranches (e.g. 3万元) or unlabelled."""
    matches = list(_WALLET_WAN_RE.finditer(text))
    if not matches:
        return None
    before = [m for m in matches if m.end() <= pos]
    chosen = before[-1] if before else min(matches, key=lambda m: abs(m.start() - pos))
    val = float(chosen.group(1))
    if abs(val - 10.0) < 1e-6:
        return 100000.0
    if abs(val - 1.0) < 1e-6:
        return 10000.0
    return None


def _check_wallet_anchor_grams(text: str) -> list[str]:
    """Verify explicit 10万 / 1万 wallet anchor grams (持约 X 克) match principal/anchor within ±0.12g."""
    errs: list[str] = []
    m_sec = re.search(
        r"(?:^|\n)#{2,3}\s*[^\n]*(?:10\s*万元|钱包账)[^\n]*\n(.*?)(?=\n#{1,2}\s|\Z)",
        text,
        flags=re.DOTALL,
    )
    scope = m_sec.group(0) if m_sec else text
    m_anc = re.search(r"(?:以|按|锚定)[^。\n]{0,24}?(\d{3,4}(?:\.\d+)?)\s*元/克", scope)
    if not m_anc:
        return errs
    anchor = float(m_anc.group(1))
    if anchor <= 0:
        return errs

    in_table = False
    col_principals: list[float | None] = []

    def _check_gram_match(principal: float, grams: float) -> None:
        exp_g = principal / anchor
        if abs(exp_g - grams) > 0.12:
            label_wan = "10 万元" if principal >= 50000.0 else "1 万元"
            errs.append(
                f"[Gate G6 钱包克重算术错] {label_wan}按 {anchor:g} 元/克 应持约 {exp_g:.2f} 克，"
                f"但文中写持约 {grams:g} 克（偏差 {abs(exp_g - grams):.2f} > 0.12 克）"
            )

    for ln in scope.splitlines():
        st = ln.strip()
        is_tbl = st.startswith("|") and st.endswith("|")
        if is_tbl:
            cells = [c.strip() for c in st.strip("|").split("|")]
            if not in_table:
                in_table = True
                col_principals = []
                for hc in cells:
                    if re.search(r"(?<![\d.])10\s*万", hc):
                        col_principals.append(100000.0)
                    elif re.search(r"(?<![\d.])1\s*万", hc):
                        col_principals.append(10000.0)
                    else:
                        col_principals.append(None)
                continue
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            if "持约" not in ln:
                continue
            for ci, cell in enumerate(cells):
                if "持约" not in cell:
                    continue
                col_p = col_principals[ci] if ci < len(col_principals) else None
                has_explicit_wan = bool(_WALLET_WAN_RE.search(cell))
                for m_g in re.finditer(r"持约\s*(\d+(?:\.\d+)?)\s*克", cell):
                    principal = _resolve_wallet_principal(cell, m_g.start()) if has_explicit_wan else col_p
                    if principal is not None:
                        _check_gram_match(principal, float(m_g.group(1)))
        else:
            in_table = False
            col_principals = []
            if "持约" not in ln:
                continue
            if not _WALLET_WAN_RE.search(ln):
                continue
            for m_g in re.finditer(r"持约\s*(\d+(?:\.\d+)?)\s*克", ln):
                principal = _resolve_wallet_principal(ln, m_g.start())
                if principal is not None:
                    _check_gram_match(principal, float(m_g.group(1)))
    return errs


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
                        f"[Gate G2 夜盘收盘时段混淆] {label} (L{line_no}) 将 02:30 误关联至非金银标的 "
                        f"({m_metal.group(0)}，有色夜盘 01:00 / 黑色 23:00 收盘)"
                    )
                    flagged = True
                    break
            if flagged:
                break
    return errs


def _check_scenario_10pt_and_dots(label: str, text: str) -> list[str]:
    """Gate G3: Check 10-point scenario weight sums (single-line & multi-line blocks) and [●○]{10} dot-bar parity."""
    errs: list[str] = []
    lines = text.splitlines()
    for line_no, ln in enumerate(lines, 1):
        has_bar = bool(_TEN_DOT_RE.search(ln))
        if not has_bar and not _SCENARIO_LINE_TRIGGER_RE.search(ln):
            continue
        weights: list[tuple[int, int, int]] = []
        for m in _SCENARIO_WEIGHT_RE.finditer(ln):
            raw_num = next(g for g in m.groups() if g is not None)
            weights.append((m.start(), m.end(), int(raw_num)))
        if len(weights) >= 2 and not _SCENARIO_DELTA_RE.search(ln):
            total = sum(w for _, _, w in weights)
            if total != 10:
                errs.append(
                    f"[Gate G3 情景权重未满 10 点] {label} (L{line_no}) 情景权重之和={total} ≠ 10 ({[w for _, _, w in weights]})"
                )
        if has_bar:
            anchors = list(weights)
            if not anchors:
                for m_r in _SCENARIO_SINGLE_RATIO_RE.finditer(ln):
                    anchors.append((m_r.start(), m_r.end(), int(m_r.group(1))))
            for m_bar in _TEN_DOT_RE.finditer(ln):
                filled = m_bar.group(0).count("●")
                if not anchors:
                    continue
                before = [w for w in anchors if w[1] <= m_bar.start()]
                chosen = before[-1] if before else min(anchors, key=lambda w: abs(w[0] - m_bar.end()))
                if filled != chosen[2]:
                    errs.append(
                        f"[Gate G3 概率点条不一致] {label} (L{line_no}) 实心数 ({filled}) ≠ 权重 ({chosen[2]})"
                    )

    # Scan consecutive multi-line scenario bullet/table blocks (2–6 adjacent lines) under a scenario context
    def _extract_block_line_weight(line: str) -> int | None:
        st = line.strip()
        is_bullet = bool(re.match(r"^(?:[-•*]|\d+\.)\s+", st))
        is_table_row = st.startswith("|") and st.endswith("|")
        if not (is_bullet or is_table_row):
            return None
        if is_table_row:
            cells = [c.strip() for c in st.strip("|").split("|")]
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
                    f"[Gate G3 情景权重未满 10 点] {label} (L{idx + 1}-L{end_idx}) 多行情景权重之和={total} ≠ 10 ({block_weights})"
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
                errs.append(f"[Gate G7 时态错位] {label} (L{line_no}) {desc} -> {m.group(0)!r}")
    return errs


def _check_credit_spread_ccc(label: str, text: str) -> list[str]:
    """Gate S2: Require explicit CCC qualifier within ±20 chars of CCC-tier junk spread mentions."""
    errs: list[str] = []
    for line_no, ln in enumerate(text.splitlines(), 1):
        for m in _CREDIT_SPREAD_CCC_RE.finditer(ln):
            win = ln[max(0, m.start() - 20) : min(len(ln), m.end() + 20)]
            if not _CCC_QUAL_RE.search(win):
                errs.append(
                    f"[Gate S2 信用利差口径混淆] {label} (L{line_no}) 信用利差表述缺少 CCC 分级限定"
                    f"（防止混淆全口径高收益债与 CCC 级垃圾债利差）-> {win!r}"
                )
                break
    return errs


def _closest_gold_md_dt(mo: int, d: int, hh: int, mm: int, ref_dt: datetime) -> datetime | None:
    cands: list[datetime] = []
    for yr in (ref_dt.year - 1, ref_dt.year, ref_dt.year + 1):
        try:
            cands.append(datetime(yr, mo, d, hh, mm))
        except ValueError:
            continue
    if not cands:
        return None
    return min(cands, key=lambda dt: (abs((dt - ref_dt).days), abs((dt - ref_dt).total_seconds())))


def _parse_gold_scorecard_due_dt(cell_text: str, ref_dt: datetime) -> datetime | None:
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
            return _closest_gold_md_dt(mo, d, hh, mm, ref_dt)
        return None
    m_md_only = re.search(r"(?<![0-9/])(\d{1,2})/(\d{1,2})(?![0-9/]|(?:\s*(?:关|分|项|点|家|只)))", plain)
    if m_md_only:
        mo, d = int(m_md_only.group(1)), int(m_md_only.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return _closest_gold_md_dt(mo, d, 23, 59, ref_dt)
    return None


def _check_gold_scorecard_past_due(sc_text: str, as_of_dt: datetime | None) -> list[str]:
    """Gate G7: Fail if any ⏳ tracking row in gold/daily/SCORECARD.md is overdue by >= 1 hour."""
    if as_of_dt is None:
        m_asof = re.search(r"截至\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", sc_text)
        if m_asof:
            as_of_dt = _parse_timestamp(m_asof.group(1))
    if as_of_dt is None:
        return []
    ref_naive = as_of_dt.replace(tzinfo=None)
    errs: list[str] = []
    for ln in sc_text.splitlines():
        st = ln.strip()
        if not (st.startswith("|") and st.endswith("|")) or "⏳" not in st:
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if len(cells) < 4 or all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        due_cell = cells[2]
        due_dt = _parse_gold_scorecard_due_dt(due_cell, ref_naive)
        if due_dt is not None and due_dt <= ref_naive - timedelta(hours=1):
            summary = re.sub(r"[*`]", "", cells[1])[:36]
            errs.append(
                f"[Gate G7 公开记分卡逾期未结案] ⏳ 条目到期节点 {due_cell} <= 截点-1h ({ref_naive:%Y-%m-%d %H:%M}) -> {summary}"
            )
    return errs


def _extract_top_ledger_block(raw_text: str, marker_prefix: str) -> tuple[tuple[str, str, int] | None, str]:
    """Return (top_edition_key, top_block_text) for CHANGELOG.md or AUDIT_LOG.md."""
    matches = list(re.finditer(rf"<!--\s*{marker_prefix}\s+(.+?)\s*-->", raw_text, flags=re.DOTALL))
    if not matches:
        return None, ""
    first = matches[0]
    end_pos = matches[1].start() if len(matches) > 1 else len(raw_text)
    payload = first.group(1).strip()
    ed_id: str | None = None
    if payload.startswith("{"):
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict) and isinstance(obj.get("edition_id"), str):
                ed_id = obj["edition_id"]
        except json.JSONDecodeError:
            ed_id = None
    else:
        ed_id = payload.split()[0] if payload else None
    ed_key = _edition_key(ed_id)
    return ed_key, raw_text[first.start() : end_pos]


def _check_svg_geometry(
    directives: dict[str, list[dict]],
    *,
    is_master: bool,
    master_snap: dict | None,
    errors: list[str],
) -> None:
    """Render vector SVGs (3 daily charts or 7 master charts) and verify 0 OOB & 0 text overlap."""
    scripts_path = BASE_DIR.parent / "scripts"
    if not scripts_path.is_dir():
        return
    scripts_dir = str(scripts_path)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        from svg_geometry import check_svg_text_geometry
    except Exception as exc:
        errors.append(f"[Gate 4 SVG 几何检失败] 无法导入 scripts/svg_geometry.py: {exc}")
        return

    svg_items: list[tuple[str, str]] = []
    if is_master:
        if not isinstance(master_snap, dict) or not master_snap:
            return
        try:
            br = _load_gold_module("build_report", BASE_DIR / "build_report.py")
        except Exception as exc:
            errors.append(f"[Gate 4 SVG 几何检失败] 无法加载 build_report.py: {exc}")
            return
        prev_snap = br.SNAP
        try:
            br.SNAP = master_snap
            svg_items = [
                ("Master图1", br.svg_chart_real_vs_nominal(1)),
                ("Master图2", br.svg_chart_2026_bear_and_vacuum(2)),
                ("Master图3", br.svg_chart_china_tax_channels(3)),
                ("Master图4", br.svg_chart_48h_crash_and_weekend(4)),
                ("Master图5", br.svg_chart_mechanical_clock_and_switch(5)),
                ("Master图6", br.svg_chart_institutional_targets(6)),
                ("Master图7", br.svg_chart_fx_and_cross_ratios(7)),
            ]
        except Exception as exc:
            errors.append(f"[Gate 4 SVG 几何检失败] 主报告 SVG 渲染异常: {exc}")
            return
        finally:
            br.SNAP = prev_snap
    else:
        chart_kinds = (
            ("DAILY_CHART_TIMELINE", "render_chart_timeline"),
            ("DAILY_CHART_CROSS", "render_chart_cross"),
            ("DAILY_CHART_SWITCH", "render_chart_switch"),
        )
        if not any(directives.get(k) for k, _ in chart_kinds):
            return
        try:
            bd = _load_gold_module("build_daily", BASE_DIR / "build_daily.py")
        except Exception as exc:
            errors.append(f"[Gate 4 SVG 几何检失败] 无法加载 build_daily.py: {exc}")
            return
        for kind, fn_name in chart_kinds:
            for idx, cfg in enumerate(directives.get(kind, []), 1):
                lbl = f"{kind}#{idx}" if len(directives.get(kind, [])) > 1 else kind
                try:
                    svg_items.append((lbl, getattr(bd, fn_name)(cfg)))
                except Exception as exc:
                    errors.append(f"[Gate 4 SVG 渲染错] {lbl}: {exc}")

    for lbl, svg_html in svg_items:
        for issue in check_svg_text_geometry(svg_html, label=lbl):
            errors.append(f"[Gate 4 SVG 几何碰撞] {issue}")


def check_rsi_artifacts(errors: list[str], warnings: list[str]) -> None:
    """Validate bounded RSI playbook anti-bloat cap and structured rsi_metrics.json integrity."""
    if RSI_PLAYBOOK_PATH.exists():
        pb_text = RSI_PLAYBOOK_PATH.read_text(encoding="utf-8")
        line_cnt = len(pb_text.splitlines())
        if line_cnt > 200:
            errors.append(f"[RSI 防膨胀红线] daily/RSI_PLAYBOOK.md 共 {line_cnt} 行，超出硬上限 200 行（目标 ≤180 行），必须合并精炼旧条目")
        elif line_cnt > 180:
            warnings.append(f"[RSI 防膨胀预警] daily/RSI_PLAYBOOK.md 共 {line_cnt} 行，超出 180 行上限，请合并淘汰旧条目")
        if "Tier C" not in pb_text or "Tier B" not in pb_text:
            errors.append("[RSI 边界缺失] daily/RSI_PLAYBOOK.md 缺少 Tier B / Tier C 安全自进化边界声明")
    else:
        errors.append("[RSI 手册缺失] 未找到 daily/RSI_PLAYBOOK.md")

    if RSI_METRICS_PATH.exists():
        try:
            data = json.loads(RSI_METRICS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"[RSI 账本损坏] daily/rsi_metrics.json JSON 非法: {e}")
            return
        runs = data.get("runs") if isinstance(data, dict) else None
        if not isinstance(runs, list) or not runs:
            errors.append("[RSI 账本缺项] daily/rsi_metrics.json 缺少非空 runs 数组")
            return
        seen_ids: set[str] = set()
        for idx, r in enumerate(runs):
            if not isinstance(r, dict):
                errors.append(f"[RSI 账本格式] runs[{idx}] 不是对象")
                continue
            rid = str(r.get("run_id", "")).strip()
            if not rid:
                errors.append(f"[RSI 账本格式] runs[{idx}] 缺少 run_id")
            elif rid in seen_ids:
                errors.append(f"[RSI 账本重复] run_id '{rid}' 重复记录")
            else:
                seen_ids.add(rid)
            scores = r.get("scores")
            if not isinstance(scores, dict):
                errors.append(f"[RSI 评分缺项] run '{rid}' 缺少 scores 对象")
                continue
            score_sum = 0
            valid_all = True
            for k in RSI_REQUIRED_SCORE_KEYS:
                v = scores.get(k)
                if not isinstance(v, int) or isinstance(v, bool) or not (1 <= v <= 5):
                    errors.append(f"[RSI 评分非法] run '{rid}' 维度 {k} 须为 1–5 整数（实得 {v!r}）")
                    valid_all = False
                else:
                    score_sum += v
            if valid_all:
                if r.get("total_score") != score_sum:
                    errors.append(f"[RSI 总分冲突] run '{rid}' total_score={r.get('total_score')} != 6 维之和 {score_sum}")
                if r.get("max_score") != 30:
                    warnings.append(f"[RSI 满分口径] run '{rid}' max_score={r.get('max_score')}（应为 30）")

        latest_run = runs[-1]
        if isinstance(latest_run, dict):
            latest_id = str(latest_run.get("run_id", "")).strip() or "latest"
            closure = latest_run.get("review_closure")
            if isinstance(closure, dict):
                if closure.get("reviewer_completed") is False:
                    errors.append(f"[RSI 盲审未完成] 最新班次 '{latest_id}' review_closure.reviewer_completed=false")
                findings = closure.get("findings")
                if findings is not None:
                    if not isinstance(findings, list):
                        errors.append(f"[RSI 盲审结构错] 最新班次 '{latest_id}' review_closure.findings 须为数组")
                    else:
                        for fidx, item in enumerate(findings):
                            if not isinstance(item, dict):
                                errors.append(f"[RSI 盲审项错] 最新班次 '{latest_id}' findings[{fidx}] 须为对象")
                                continue
                            st = str(item.get("status", "")).strip()
                            if st == "open" or st not in _RSI_ALLOWED_FINDING_STATUSES:
                                errors.append(
                                    f"[RSI 盲审未闭环] 最新班次 '{latest_id}' findings[{fidx}] 状态为 {st!r}（严禁 open，须为 resolved/deferred_data/disclosed_caveat）"
                                )
    else:
        errors.append("[RSI 账本缺失] 未找到 daily/rsi_metrics.json")


def _check_edition_ledgers(
    edition: str, as_of: str | None, errors: list[str], *, is_current: bool = True,
) -> None:
    """Require red-team evidence and synchronized public/internal records before building new reports."""
    try:
        cl_raw = CHANGELOG_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"[黄金刊期台账缺失] {CHANGELOG_PATH.name}: {exc}")
    else:
        cl_texts = [cl_raw]
        cl_archive_dir = CHANGELOG_PATH.parent / "archive"
        if cl_archive_dir.is_dir():
            for arch_p in sorted(cl_archive_dir.rglob("*.md")):
                try:
                    cl_texts.append(arch_p.read_text(encoding="utf-8"))
                except OSError:
                    continue
        cl_pat = re.compile(rf"<!--\s*GOLD_EDITION_CHANGELOG\s+{re.escape(edition)}\s*-->")
        if sum(len(cl_pat.findall(src)) for src in cl_texts) != 1:
            errors.append(f"[黄金刊期台账错] {CHANGELOG_PATH.name} 须含一条 GOLD_EDITION_CHANGELOG {edition} 标记")

    try:
        sc_raw = SCORECARD_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"[黄金刊期台账缺失] {SCORECARD_PATH.name}: {exc}")
    else:
        if is_current:
            if len(re.findall(rf"<!--\s*GOLD_EDITION_SCORECARD\s+{re.escape(edition)}\s*-->", sc_raw)) != 1:
                errors.append(f"[黄金刊期台账错] {SCORECARD_PATH.name} 须含一条 GOLD_EDITION_SCORECARD {edition} 标记")
        else:
            target_key = _edition_key(edition)
            sc_keys = [
                k for m in re.findall(r"<!--\s*GOLD_EDITION_SCORECARD\s+(\S+)\s*-->", sc_raw)
                if (k := _edition_key(m)) is not None
            ]
            if target_key is None or not any(k >= target_key for k in sc_keys):
                errors.append(
                    f"[黄金刊期台账错] {SCORECARD_PATH.name} 须含不早于 {edition} 的 GOLD_EDITION_SCORECARD 标记"
                )

    try:
        raw = AUDIT_LOG_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"[黄金核验台账缺失] {AUDIT_LOG_PATH.name}: {exc}")
        return
    audit_texts = [raw]
    al_archive_dir = AUDIT_LOG_PATH.parent / "archive"
    if al_archive_dir.is_dir():
        for arch_p in sorted(al_archive_dir.rglob("*.md")):
            try:
                audit_texts.append(arch_p.read_text(encoding="utf-8"))
            except OSError:
                continue
    reviews = []
    for audit_src in audit_texts:
        for match in EDITION_REVIEW_RE.finditer(audit_src):
            try:
                review = json.loads(match[1])
            except json.JSONDecodeError as exc:
                errors.append(f"[黄金核验台账 JSON 错] GOLD_EDITION_REVIEW: {exc}")
                continue
            if not isinstance(review, dict):
                errors.append("[黄金核验台账结构错] GOLD_EDITION_REVIEW 须为对象")
            elif review.get("edition_id") == edition:
                reviews.append(review)
    if len(reviews) != 1:
        errors.append(f"[黄金核验记录错] {AUDIT_LOG_PATH.name} 须含一条 {edition} 的 GOLD_EDITION_REVIEW")
        return
    review = reviews[0]
    if review.get("as_of_short") != as_of or not isinstance(review.get("note"), str) or not review["note"].strip():
        errors.append("[黄金核验记录错] 审阅截点须与日报一致，并保留非空核验说明")
    sources = review.get("sources")
    for key in ENTRY_GATE_IDS:
        links = sources.get(key) if isinstance(sources, dict) else None
        if not isinstance(links, list) or not links or not all(evidence_url(link) for link in links):
            errors.append(f"[黄金核验来源缺失] 四关对应 {key} 项须附至少一条 HTTPS 证据链接")
    forecast = review.get("forecast_review")
    if not isinstance(forecast, dict):
        errors.append("[黄金预判验真缺项] forecast_review 须为对象")
        return
    status, note, forecast_sources = forecast.get("status"), forecast.get("note"), forecast.get("sources")
    if (
        status not in ("settled", "none_due", "pending_evidence") or not isinstance(note, str) or not note.strip()
        or not isinstance(forecast_sources, list) or not all(evidence_url(link) for link in forecast_sources)
        or (status == "settled" and not forecast_sources)
    ):
        errors.append("[黄金预判验真缺项] 记录状态、核验说明与证据链接，结案必须附证据")


def _reconcile_gold_scorecard(sc_text: str, errors: list[str]) -> None:
    """Reconcile Gold SCORECARD.md overview summary counts against Table 1 (settled) & Table 2 (tracking) rows."""
    m_settled = re.search(
        r"\|\s*\*\*已到期公开回验\*\*\s*\|\s*\*\*(\d+)\s*项\*\*（计分\s*(\d+)\s*项[^）]*）\s*\|"
        r"\s*\*\*(\d+)\s*项\*\*\s*\|\s*\*\*(\d+)\s*项\*\*\s*\|\s*\*\*(\d+)\s*项\*\*\s*\|\s*\*\*(\d+)\s*项\*\*",
        sc_text,
    )
    m_track = re.search(r"\|\s*\*\*当前持续追踪中\*\*\s*\|\s*\*\*(\d+)\s*项\*\*", sc_text)
    if not m_settled and not m_track:
        return

    def _extract_table_rows(section_body: str) -> list[list[str]]:
        tbl_lines = [ln.strip() for ln in section_body.splitlines() if ln.strip().startswith("|") and ln.strip().endswith("|")]
        if len(tbl_lines) < 3:
            return []
        rows: list[list[str]] = []
        for ln in tbl_lines[1:]:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                continue
            rows.append(cells)
        return rows

    if m_settled:
        exp_tot, exp_scored, exp_pass, exp_partial, exp_fail, exp_untrig = (int(x) for x in m_settled.groups())
        if exp_scored != exp_pass + exp_partial + exp_fail:
            errors.append(
                f"[公开记分卡总览算术错] 计分 {exp_scored} 项 ≠ 兑现({exp_pass})+部分({exp_partial})+证伪({exp_fail})"
            )
        m_t1 = re.search(r"^##\s*二、[^\n]*\n(.*?)(?=^##\s*三、|\Z)", sc_text, flags=re.MULTILINE | re.DOTALL)
        if m_t1:
            t1_rows = _extract_table_rows(m_t1.group(1))
            act_pass = act_partial = act_fail = act_untrig = act_non_inv = 0
            for cells in t1_rows:
                row_text = " ".join(cells)
                verdict_cell = cells[4] if len(cells) >= 5 else ""
                if (
                    "⚪ 运维记录" in row_text
                    or "运维记录" in verdict_cell
                    or "不计入投资胜率" in row_text
                ):
                    act_non_inv += 1
                elif "✅" in verdict_cell:
                    act_pass += 1
                elif "⚠️" in verdict_cell or "部分兑现" in verdict_cell:
                    act_partial += 1
                elif "❌" in verdict_cell or "证伪" in verdict_cell:
                    act_fail += 1
                elif "⚪" in verdict_cell or "条件未触发" in verdict_cell:
                    act_untrig += 1
            act_scored = act_pass + act_partial + act_fail
            valid_folded = (
                exp_tot == exp_pass + exp_partial + exp_fail + exp_untrig
                and (len(t1_rows), act_scored, act_pass, act_partial, act_fail, act_untrig + act_non_inv)
                == (exp_tot, exp_scored, exp_pass, exp_partial, exp_fail, exp_untrig)
            )
            valid_separate = (
                act_non_inv > 0
                and exp_tot == exp_pass + exp_partial + exp_fail + exp_untrig + act_non_inv
                and (len(t1_rows), act_scored, act_pass, act_partial, act_fail, act_untrig)
                == (exp_tot, exp_scored, exp_pass, exp_partial, exp_fail, exp_untrig)
            )
            if not (valid_folded or valid_separate):
                ops_note = f"/运维{act_non_inv}" if act_non_inv else ""
                errors.append(
                    f"[公开记分卡表一对账错] 头部汇总=(总{exp_tot}/计分{exp_scored}: ✅{exp_pass}/⚠️{exp_partial}/❌{exp_fail}/⚪{exp_untrig}) "
                    f"≠ 表一实有行=(总{len(t1_rows)}/计分{act_scored}: ✅{act_pass}/⚠️{act_partial}/❌{act_fail}/⚪{act_untrig}{ops_note})"
                )
        else:
            if exp_tot != exp_pass + exp_partial + exp_fail + exp_untrig:
                errors.append(
                    f"[公开记分卡总览算术错] 已到期 {exp_tot} 项 ≠ 兑现({exp_pass})+部分({exp_partial})+证伪({exp_fail})+未触发({exp_untrig})"
                )

    if m_track:
        exp_track = int(m_track.group(1))
        m_t2 = re.search(r"^##\s*三、[^\n]*\n(.*?)(?=^##\s*四、|^---|\Z)", sc_text, flags=re.MULTILINE | re.DOTALL)
        if m_t2:
            t2_rows = _extract_table_rows(m_t2.group(1))
            if len(t2_rows) != exp_track:
                errors.append(
                    f"[公开记分卡表二对账错] 头部汇总持续追踪={exp_track} 项 ≠ 表二实有行={len(t2_rows)} 项"
                )


def check_calendar_and_scorecard(errors: list[str], warnings: list[str]) -> None:
    """Validate external 60+ day market_calendar.json and public zero-jargon daily/SCORECARD.md."""
    if not MARKET_CALENDAR_PATH.exists():
        errors.append("[外置日历缺失] 未找到 market_calendar.json")
    else:
        try:
            cal = json.loads(MARKET_CALENDAR_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"[外置日历损坏] market_calendar.json JSON 解析失败: {exc}")
        else:
            overrides = cal.get("calendar_overrides") if isinstance(cal, dict) else None
            if not isinstance(overrides, list) or len(overrides) == 0:
                errors.append("[外置日历空项] market_calendar.json 缺少非空 calendar_overrides 数组")

    if not SCORECARD_PATH.exists():
        errors.append("[公开记分卡缺失] 未找到 daily/SCORECARD.md")
    else:
        sc_text = SCORECARD_PATH.read_text(encoding="utf-8")
        if len(sc_text.strip()) < 200:
            errors.append("[公开记分卡过短] daily/SCORECARD.md 内容异常过短")
        leaked = SCORECARD_BANNED_RE.findall(sc_text)
        if leaked:
            errors.append(
                f"[公开记分卡内部词泄露] daily/SCORECARD.md 含禁止内部工程/RSI 词: {', '.join(sorted(set(leaked)))}"
            )
        _reconcile_gold_scorecard(sc_text, errors)
        sc_as_of: datetime | None = None
        if DAILY_SNAPSHOT_PATH.exists():
            try:
                ds = json.loads(DAILY_SNAPSHOT_PATH.read_text(encoding="utf-8"))
                if isinstance(ds, dict):
                    sc_as_of = _parse_timestamp(ds.get("as_of_short"))
            except (OSError, ValueError):
                sc_as_of = None
        errors.extend(_check_gold_scorecard_past_due(sc_text, sc_as_of))

    if CHANGELOG_PATH.exists():
        cl_raw = CHANGELOG_PATH.read_text(encoding="utf-8")
        cl_text = _strip_comments_keep_lines(cl_raw)
        cl_leaked = SCORECARD_BANNED_RE.findall(cl_text) + _INTERNAL_FILENAME_LEAK_RE.findall(cl_text)
        if cl_leaked:
            errors.append(
                f"[演化日志内部词泄露] daily/CHANGELOG.md 含禁止内部工程词/文件名: {', '.join(sorted(set(cl_leaked)))}"
            )
        cl_bin = _DEPRECATED_BINARY_LINK_RE.findall(cl_text)
        if cl_bin:
            errors.append(
                f"[演化日志二进制死链] daily/CHANGELOG.md 含已弃用 PDF/DOCX 残留: {', '.join(sorted(set(cl_bin))[:5])}"
            )
        cl_top_key, cl_top_block = _extract_top_ledger_block(cl_raw, "GOLD_EDITION_CHANGELOG")
        if cl_top_key is not None and cl_top_key[:2] >= EDITORIAL_DEPTH_CUTOVER[:2]:
            errors.extend(_check_shfe_night_close(CHANGELOG_PATH.name, cl_top_block))

    if AUDIT_LOG_PATH.exists():
        al_raw = AUDIT_LOG_PATH.read_text(encoding="utf-8")
        al_top_key, al_top_block = _extract_top_ledger_block(al_raw, "GOLD_EDITION_REVIEW")
        if al_top_key is not None and al_top_key[:2] >= EDITORIAL_DEPTH_CUTOVER[:2]:
            errors.extend(_check_shfe_night_close(AUDIT_LOG_PATH.name, al_top_block))


def main():
    args = sys.argv[1:]
    strict = "--strict" in args
    precheck = "--precheck" in args
    unknown_flags = [a for a in args if a.startswith("-") and a not in ("--strict", "--precheck")]
    if unknown_flags:
        print(f"Unknown option(s): {', '.join(unknown_flags)}")
        print("Usage: python3 lint_readability.py <file1.md> [file2.md ...] [--precheck] [--strict]")
        sys.exit(2)
    files = [Path(a) for a in args if not a.startswith("-")]
    if not files:
        print("Usage: python3 lint_readability.py <file1.md> [file2.md ...] [--precheck] [--strict]")
        sys.exit(2)

    snap_cache: dict[Path, dict | None] = {}
    exit_code = 0

    for snap_path in (DAILY_SNAPSHOT_PATH, MASTER_SNAPSHOT_PATH):
        s_errs: list[str] = []
        s_warns: list[str] = []
        snap_cache[snap_path] = validate_snapshot_file(snap_path, s_errs, s_warns)
        if s_errs or s_warns:
            print(f"=== Data Snapshot Consistency Check: {snap_path.name} ===")
            for e in s_errs:
                print(f"  [FAIL] {e}")
            for w in s_warns:
                print(f"  [WARN] {w}")
            if s_errs or (strict and s_warns):
                exit_code = 1

    rsi_errs: list[str] = []
    rsi_warns: list[str] = []
    check_rsi_artifacts(rsi_errs, rsi_warns)
    if rsi_errs or rsi_warns:
        print("=== RSI Playbook & Telemetry Integrity Check ===")
        for e in rsi_errs:
            print(f"  [FAIL] {e}")
        for w in rsi_warns:
            print(f"  [WARN] {w}")
        if rsi_errs or (strict and rsi_warns):
            exit_code = 1

    gov_errs: list[str] = []
    gov_warns: list[str] = []
    check_calendar_and_scorecard(gov_errs, gov_warns)
    if gov_errs or gov_warns:
        print("=== Market Calendar & Public Scorecard Check ===")
        for e in gov_errs:
            print(f"  [FAIL] {e}")
        for w in gov_warns:
            print(f"  [WARN] {w}")
        if gov_errs or (strict and gov_warns):
            exit_code = 1

    daily_snap = snap_cache.get(DAILY_SNAPSHOT_PATH)
    master_snap = snap_cache.get(MASTER_SNAPSHOT_PATH)

    for p in files:
        if not p.exists():
            print(f"[ERROR] File not found: {p}")
            exit_code = 1
            continue
        errs, warns = check_file(p, daily_snap, master_snap, precheck=precheck)
        mode_label = "Web-Only Readability & Accuracy Lint (Gates 0–5)"
        print(f"=== {mode_label}: {p.name} ===")
        if not errs and not warns:
            print("  PASS: All web-publishing quality gates (Gates 0–5) passed with 0 errors and 0 warnings.")
        else:
            for e in errs:
                print(f"  [FAIL] {e}")
            for w in warns:
                print(f"  [WARN] {w}")
        if errs or (strict and warns):
            exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
