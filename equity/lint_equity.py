#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent Pre-Flight & Pure-Web Forensic Quality Linter for Global Equity Research
(A-Share × HK-Stock × US-Stock + 8–12 Multi-Asset Channels + ETF Universe + 231-Stock Deep Dossiers
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
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path

import edition_plan as _edition_plan_mod
from edition_plan import MARKETS, calendar_rules, edition_plan, parse_edition_id
from pdf_common import BASE_DIR, DAILY_DIR, _BANNED_INTERNAL_RE, _split_md_row, lint_markdown_report

GOLD_SNAPSHOT_PATH = BASE_DIR.parent / "gold" / "data_snapshot.json"
GOLD_CALENDAR_PATH = GOLD_SNAPSHOT_PATH.with_name("market_calendar.json")
STATE_PATH = BASE_DIR / "state" / "market_state.json"
MULTI_ASSET_PATH = BASE_DIR / "state" / "multi_asset_channels.json"
ETF_UNIVERSE_PATH = BASE_DIR / "state" / "etf_universe.json"
DEEP_DOSSIERS_PATH = BASE_DIR / "state" / "deep_dossiers.json"
BEIJING = timezone(timedelta(hours=8))
MAX_EDITION_EARLY = timedelta(minutes=5)
MAX_EDITION_LAG = timedelta(hours=6)
EDITION_CUTOVER = ("2026-11-25", 1800, 2)
ALL_MAIN_CUTOVER = getattr(_edition_plan_mod, "ALL_MAIN_CUTOVER", ("2026-11-26", 1800, 1))
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
_MA_RESTRICTED_WARN_RE = re.compile(
    r"(?:暂停|封盘|已停|停售|限购|退市|私有化|勿买|勿选|勿误配|严禁|禁止|切忌|避坑|避开|不可|高危|雷区|警示|清盘|改以|替代)"
)
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
    "us-stock:NEM", "us-stock:GOLD", "us-stock:AEM", "us-stock:WPM", "us-stock:FNV",
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
    r"(?:补齐|补足|买入|买进|加仓|加配|抄底|逢低买|低吸|新买|买|定投|配置|建仓|吸纳)"
    r"\s*(?:[0-9一二两三半成%–\-~约近超]*\s*)?"
    r"(?:(?:现货|实物|纸|积存)?(?:黄金|金仓|金矿股?|黄金股)|"
    r"(?:518660|518880|518850|159934|159937|518800|517520|159562|02840|03081|"
    r"(?<![A-Za-z])(?:GLD|IAU|IAUM|GLDM|IGLN|GDX|GDXJ)(?![A-Za-z])))",
    flags=re.IGNORECASE,
)
_GOLD_DEFER_GUARD_RE = re.compile(
    r"(?:暂不|严禁|禁止|切忌|勿|停止|暂停|先别|不能|不宜|不要|别急着|拒绝|不考虑|不允许|不应|不会|未在黄金红灯停期|不)"
    r"(?:追高芯片[与或])?(?:现在|今天|今日|当下|任何|立即|马上|急于|立刻|再|去|主动|新|分批|小批|继续|同步|直接|冲动|抢跑)*"
    r"(?:(?:新买|买入|加仓|抄底|定投|配置|建仓|补齐)[/／、与或])?[\s“‘「\x22*_]*$"
    r"|(?:等到?|待).{0,14}(?:黄灯|绿灯|解锁)(?:亮起|确认)?(?:后)?(?:再|才)?(?:分批|择机|恢复|重启|再)*[\s“‘「\x22]*$"
    r"|(?:黄灯|绿灯|解锁|过四关|全部过关)(?:亮起|确认)?后(?:再|才)?(?:分批|择机|恢复|重启|再)*[\s“‘「\x22]*$"
    r"|(?:原稿曾建议|原稿曾考虑|过去曾建议|曾建议)[\s“‘「\x22]*$"
)
_GOLD_MINER_TICKERS_RE = re.compile(
    r"(?:NEM|纽蒙特|山东黄金|中金黄金|赤峰黄金|山金国际|紫金黄金|紫金矿业|招金|老铺黄金|周大福|"
    r"GLD|GLDM|IAU|IAUM|IGLN|GDX|GDXJ|518660|518880|518850|518800|517520|159934|159937|159562|02840|03081|02899|06181|01929)",
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
    skip_keys: frozenset[str] = frozenset({"schema_version", "id", "edition_id", "as_of_date", "updated_at", "category", "status_tone"}),
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

    return errs, warns


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
                # Unified sequential run windows (07:25–13:30 / 17:55–23:59 CST, Gold SSOT first -> Equity second) allow <= 6.0h freshness; off-window manual <= 10.5h
                max_h = 6.0 if e_dt.hour in (7, 8, 9, 10, 11, 12, 13, 17, 18, 19, 20, 21, 22, 23) else 10.5
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
                    is_gold_etf = (
                        etf.get("gold_locked") is True
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
    except Exception as exc:
        return [f"Gate 3B SVG 几何检失败：无法导入 scripts/svg_geometry.py ({exc})"], []

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
    if isinstance(state, dict):
        ed = state.get("edition_id")
        if isinstance(ed, str) and parse_edition_id(ed) is not None:
            state_edition_id = ed
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

    req_channels = _SYNTHETIC_LEGACY_MULTI_ASSET_CHANNELS if is_synthetic_small_pool else _REQUIRED_MULTI_ASSET_CHANNELS
    min_etf_count = 100 if is_synthetic_small_pool else 140

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
                            ck = code.strip().upper()
                            if ck in seen_codes:
                                errs.append(f"Gate 4 失败：etf_universe.json 存在重复代码 {ck}")
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
                        if "premium_status" in item and item["premium_status"] not in _ETF_ALLOWED_PREMIUM_STATUSES:
                            errs.append(
                                f"Gate 4 失败：etf_universe.json etfs[{idx}]({code}).premium_status 非法枚举 ({item['premium_status']!r})"
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
                for jpath, sval in _walk_json_strings(eu, "etf_universe.json"):
                    hits = _BANNED_INTERNAL_RE.findall(sval)
                    if hits:
                        errs.append(f"Gate 4 失败：{jpath} 泄露内部词: {sorted(set(hits))}")

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
        except json.JSONDecodeError as exc:
            errs.append(f"Gate 4 失败：market_state.json JSON 语法错误: {exc}")

    errs.extend(_check_ssot_databases(st))

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
            le, lw = lint_markdown_report(ledger.read_text(encoding="utf-8"), str(ledger), is_flagship=False)
            errs.extend([f"{ledger.name}: {x}" for x in le])
            warns.extend([f"{ledger.name}: {x}" for x in lw])

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
        long_bullets = sum(
            1 for ln in body_no_meta.splitlines()
            if re.match(r"^\s*[-•*]\s+", ln) and len(ln.strip()) > 210
        )
        if long_bullets:
            all_warnings.append(f"{p.name}: 存在 {long_bullets} 条超过 210 字的超长列表项（防密墙）")

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
