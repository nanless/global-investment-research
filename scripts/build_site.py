#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static Site Generator for Global Investment Research Portal (Gold × A-Share × HK-Stock × US-Stock).

Pure Python 3 stdlib ONLY (zero Node/npm/Hugo/Chrome/PIL/bs4/markdown dependency).
Works identically on macOS and GitHub Actions Ubuntu:
    python3 scripts/build_site.py --out _site

Safety guarantee:
  - Reads gold/ and equity/ strictly READ-ONLY.
  - Loads gold/ and equity/ renderers in isolated module namespaces
    so gold/build_daily.py and equity/build_daily.py never collide and never invoke Chrome or write files.
  - Writes all static web output exclusively inside --out <dir>.
"""

from __future__ import annotations

import argparse
import html as html_mod
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from difflib import SequenceMatcher
from math import isfinite
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

if __package__:
    from .ah_dividends import parse_exchange_closes, parse_pair
    from .inventory_evidence import ETF_FIELDS, STOCK_FIELDS, inventory_evidence, load_research_json
    from .source_links import is_https_source, policy_brief_links
    from .state_transaction import state_read_lock
else:
    from ah_dividends import parse_exchange_closes, parse_pair
    from inventory_evidence import ETF_FIELDS, STOCK_FIELDS, inventory_evidence, load_research_json
    from source_links import is_https_source, policy_brief_links
    from state_transaction import state_read_lock

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
GOLD_DIR = REPO_ROOT / "gold"
EQUITY_DIR = REPO_ROOT / "equity"
ASSETS_SRC = SCRIPT_DIR / "web_assets"

MARKET_ORDER: dict[str, int] = {
    "gold": 0,
    "a-share": 1,
    "hk-stock": 2,
    "us-stock": 3,
}

SKIP_DAILY_STEMS = {
    "INDEX",
    "CHANGELOG",
    "SCORECARD",
    "AUDIT_LOG",
    "AGENTS",
    "DAILY_FORMAT_SPEC",
    "RSI_PLAYBOOK",
}

MARKET_META = {
    "gold": {
        "slug": "gold",
        "short": "黄金",
        "name": "黄金",
        "emoji": "🥇",
        "report_href": "reports/gold.html",
        "latest_href": "daily/gold-latest.html",
        "manual_label": "跨世纪主报告",
        "accent": "#b45309",
    },
    "a-share": {
        "slug": "a-share",
        "short": "A股",
        "name": "中国 A 股",
        "emoji": "🇨🇳",
        "report_href": "reports/a-share.html",
        "latest_href": "daily/a-share-latest.html",
        "manual_label": "全景手册",
        "accent": "#b91c1c",
    },
    "hk-stock": {
        "slug": "hk-stock",
        "short": "港股",
        "name": "香港股市",
        "emoji": "🇭🇰",
        "report_href": "reports/hk-stock.html",
        "latest_href": "daily/hk-stock-latest.html",
        "manual_label": "全景手册",
        "accent": "#0f766e",
    },
    "us-stock": {
        "slug": "us-stock",
        "short": "美股",
        "name": "美国股市",
        "emoji": "🇺🇸",
        "report_href": "reports/us-stock.html",
        "latest_href": "daily/us-stock-latest.html",
        "manual_label": "全景手册",
        "accent": "#1d4ed8",
    },
}

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#141a24"/>
      <stop offset="100%" stop-color="#222b3a"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="14" fill="url(#g)"/>
  <circle cx="32" cy="32" r="21" fill="none" stroke="#d4a238" stroke-width="2.2" opacity="0.92"/>
  <circle cx="32" cy="32" r="16" fill="none" stroke="#d4a238" stroke-width="0.9" opacity="0.45"/>
  <polygon points="32,12 37.5,32 32,52 26.5,32" fill="#d4a238"/>
  <polygon points="12,32 32,27.5 52,32 32,36.5" fill="#d4a238" opacity="0.35"/>
  <circle cx="32" cy="32" r="3.8" fill="#141a24"/>
</svg>
"""


def esc(s: Any) -> str:
    return html_mod.escape(str(s if s is not None else ""), quote=True)


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", str(s)).strip()


def clean_md_inline_plain(s: str) -> str:
    txt = str(s)
    txt = re.sub(r"<br\s*/?>", " ", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", txt)
    txt = re.sub(r"\*\*|\*|`", "", txt)
    txt = re.sub(r"<[^>]+>", "", txt)
    return re.sub(r"\s+", " ", txt).strip()


def fmt_cst_iso(iso_str: str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", str(iso_str or ""))
    if m:
        return f"{m.group(1)}年{int(m.group(2))}月{int(m.group(3))}日 {m.group(4)}:{m.group(5)} 北京时间"
    return str(iso_str or "")


def fmt_cst_compact(raw: str) -> str:
    """Normalize Gold & Equity timestamps into symmetric 'YYYY-MM-DD HH:MM CST' format."""
    s = str(raw or "").strip()
    if not s:
        return ""
    m_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})[T\s]+(\d{2}):(\d{2})", s)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)} {m_iso.group(4)}:{m_iso.group(5)} CST"
    m_cn = re.search(
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:[（(][^）)]*[）)])?\s*(\d{1,2}):(\d{2})",
        s,
    )
    if m_cn:
        return (
            f"{m_cn.group(1)}-{int(m_cn.group(2)):02d}-{int(m_cn.group(3)):02d} "
            f"{int(m_cn.group(4)):02d}:{m_cn.group(5)} CST"
        )
    return s


def session_label_from_hhmm(hhmm: str) -> tuple[str, str]:
    """Return (session_key, display_label) for archive filtering (0730 morning / 1130 midday / 1800 evening)."""
    hhmm_int = int(hhmm) if len(hhmm) == 4 and hhmm.isdigit() else 730
    disp_time = f"{hhmm[:2]}:{hhmm[2:4]}" if len(hhmm) == 4 else hhmm
    if hhmm_int < 1100:
        return "morning", f"早报 {disp_time}"
    if hhmm_int < 1500:
        return "midday", f"午报 {disp_time}"
    return "evening", f"晚报 {disp_time}"


# ==============================================================================
# 1. ISOLATED RENDERER MODULE LOADER (Zero sys.modules collision, Zero bs4/PIL)
# ==============================================================================

@dataclass
class Renderers:
    gold_daily: Any
    gold_report: Any
    eq_pdf_common: Any
    eq_a: Any
    eq_hk: Any
    eq_us: Any
    eq_daily: Any


def _load_module_from_path(mod_name: str, file_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to create module spec for {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_renderers() -> Renderers:
    """Load gold & equity Python renderers in completely isolated module namespaces."""
    saved = {
        k: sys.modules.get(k)
        for k in ("build_daily", "pdf_common", "lint_equity", "chart_input", "edition_plan")
    }
    try:
        # 1. Load gold modules cleanly (pure web build needs zero bs4/PIL/Chrome)
        _load_module_from_path("chart_input", GOLD_DIR / "chart_input.py")

        gold_daily = _load_module_from_path("_gir_gold_daily", GOLD_DIR / "build_daily.py")
        sys.modules["build_daily"] = gold_daily
        gold_report = _load_module_from_path("_gir_gold_report", GOLD_DIR / "build_report.py")

        # Clear temporary gold aliases before loading equity modules
        sys.modules.pop("build_daily", None)

        # 2. Load equity modules cleanly
        _load_module_from_path("edition_plan", EQUITY_DIR / "edition_plan.py")
        eq_pdf_common = _load_module_from_path("_gir_eq_pdf_common", EQUITY_DIR / "pdf_common.py")
        sys.modules["pdf_common"] = eq_pdf_common
        eq_lint = _load_module_from_path("_gir_eq_lint", EQUITY_DIR / "lint_equity.py")
        sys.modules["lint_equity"] = eq_lint
        eq_a = _load_module_from_path("_gir_eq_a", EQUITY_DIR / "build_a_share_pdf.py")
        eq_hk = _load_module_from_path("_gir_eq_hk", EQUITY_DIR / "build_hk_stock_pdf.py")
        eq_us = _load_module_from_path("_gir_eq_us", EQUITY_DIR / "build_us_stock_pdf.py")
        eq_daily = _load_module_from_path("_gir_eq_daily", EQUITY_DIR / "build_daily.py")
    finally:
        for k, orig in saved.items():
            if orig is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = orig

    return Renderers(
        gold_daily=gold_daily,
        gold_report=gold_report,
        eq_pdf_common=eq_pdf_common,
        eq_a=eq_a,
        eq_hk=eq_hk,
        eq_us=eq_us,
        eq_daily=eq_daily,
    )


def get_equity_charts(R: Renderers, market_key: str, meta_override: dict | None = None) -> dict[str, str]:
    if market_key == "a_share":
        m = R.eq_a
        return {
            "<!-- CHART_A1 -->": m.svg_chart_a1_cycles(meta_override),
            "<!-- CHART_A2 -->": m.svg_chart_a2_split_and_futures(meta_override),
            "<!-- CHART_A3 -->": m.svg_chart_a3_macro_k_split(meta_override),
            "<!-- CHART_A4 -->": m.svg_chart_a4_clock(meta_override),
            "<!-- CHART_A5 -->": m.svg_chart_a5_targets_and_math(meta_override),
            "<!-- CHART_A6 -->": m.svg_chart_a6_sector_heatmap(meta_override),
            "<!-- CHART_A7 -->": m.svg_chart_a7_stock_quadrant(meta_override),
        }
    if market_key == "hk_stock":
        m = R.eq_hk
        return {
            "<!-- CHART_H1 -->": m.svg_chart_h1_cycles(meta_override),
            "<!-- CHART_H2 -->": m.svg_chart_h2_flow_and_rebalance(meta_override),
            "<!-- CHART_H3 -->": m.svg_chart_h3_peg_and_erp(meta_override),
            "<!-- CHART_H4 -->": m.svg_chart_h4_clock(meta_override),
            "<!-- CHART_H5 -->": m.svg_chart_h5_targets_and_scenarios(meta_override),
            "<!-- CHART_H6 -->": m.svg_chart_h6_ah_arbitrage_and_sectors(meta_override),
            "<!-- CHART_H7 -->": m.svg_chart_h7_stock_quadrant(meta_override),
        }
    m = R.eq_us
    return {
        "<!-- CHART_U1 -->": m.svg_chart_u1_crises_and_mas(meta_override),
        "<!-- CHART_U2 -->": m.svg_chart_u2_storm_timeline(meta_override),
        "<!-- CHART_U3 -->": m.svg_chart_u3_credit_split(meta_override),
        "<!-- CHART_U4 -->": m.svg_chart_u4_clock(meta_override),
        "<!-- CHART_U5 -->": m.svg_chart_u5_wall_street_forensic(meta_override),
        "<!-- CHART_U6 -->": m.svg_chart_u6_sector_heatmap(meta_override),
        "<!-- CHART_U7 -->": m.svg_chart_u7_stock_quadrant(meta_override),
    }


# ==============================================================================
# 2. DAILY REPORT DISCOVERY
# ==============================================================================

@dataclass
class DailyItem:
    market: str              # gold / a-share / hk-stock / us-stock
    source_path: Path
    slug: str                # e.g. gold-2026-11-25-0730
    date_str: str            # YYYY-MM-DD
    hhmm: str                # 0730 / 1130 / 1630 / 1800
    rev: int                 # 1, 2, ...
    session_key: str         # morning / midday / evening
    session_label: str       # 早报 07:30
    title: str = ""
    summary: str = ""
    cover_html: str = ""
    body_html: str = ""
    footer_note: str = ""
    chart_count: int = 0
    read_minutes: int = 3
    edition_type: str = "main"
    toc: list[tuple[int, str, str]] = field(default_factory=list)

    @property
    def sort_key(self) -> tuple[str, int, int, str]:
        return (self.date_str, int(self.hhmm), self.rev, self.slug)

    @property
    def rel_url(self) -> str:
        return f"daily/{self.slug}.html"


def discover_dailies() -> tuple[list[DailyItem], dict[str, str]]:
    """Keep scheduled editions addressable after a monthly archive move."""
    items: list[DailyItem] = []
    slug_map: dict[str, str] = {}

    # Gold dailies: YYYY-MM-DD_HHMM_...md
    gold_daily_dir = GOLD_DIR / "daily"
    if gold_daily_dir.exists():
        for p in sorted((*gold_daily_dir.glob("*.md"), *gold_daily_dir.glob("archive/*/*.md"))):
            if p.stem.upper() in SKIP_DAILY_STEMS:
                continue
            m = re.match(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_(?:.*?)(?:_r(\d+))?\.md$", p.name)
            if not m:
                continue
            dt, hhmm, rev_s = m.group(1), m.group(2), m.group(3)
            if p.parent != gold_daily_dir and hhmm not in {"0730", "1130", "1800"}:
                continue
            rev = int(rev_s) if rev_s else 1
            slug = f"gold-{dt}-{hhmm}" + (f"-r{rev}" if rev_s else "")
            s_key, s_lbl = session_label_from_hhmm(hhmm)
            item = DailyItem(
                market="gold",
                source_path=p,
                slug=slug,
                date_str=dt,
                hhmm=hhmm,
                rev=rev,
                session_key=s_key,
                session_label=s_lbl,
            )
            items.append(item)
            slug_map[p.stem] = slug
            slug_map[p.name] = slug

    # Equity dailies: YYYY-MM-DD_HHMM_{a_share,hk_stock,us_stock}[_rN].md
    eq_daily_dir = EQUITY_DIR / "daily"
    mk_to_slug = {"a_share": "a-share", "hk_stock": "hk-stock", "us_stock": "us-stock"}
    if eq_daily_dir.exists():
        for p in sorted((*eq_daily_dir.glob("*.md"), *eq_daily_dir.glob("archive/*/*.md"))):
            if p.stem.upper() in SKIP_DAILY_STEMS:
                continue
            m = re.match(
                r"^(\d{4}-\d{2}-\d{2})_(\d{4})_(a_share|hk_stock|us_stock)(?:_r(\d+))?\.md$",
                p.name,
            )
            if not m:
                continue
            dt, hhmm, mk, rev_s = m.group(1), m.group(2), m.group(3), m.group(4)
            if p.parent != eq_daily_dir and hhmm not in {"0730", "1130", "1800"}:
                continue
            rev = int(rev_s) if rev_s else 1
            mslug = mk_to_slug[mk]
            slug = f"{mslug}-{dt}-{hhmm}" + (f"-r{rev}" if rev_s else "")
            s_key, s_lbl = session_label_from_hhmm(hhmm)
            item = DailyItem(
                market=mslug,
                source_path=p,
                slug=slug,
                date_str=dt,
                hhmm=hhmm,
                rev=rev,
                session_key=s_key,
                session_label=s_lbl,
            )
            items.append(item)
            slug_map[p.stem] = slug
            slug_map[p.name] = slug

    first_paths = {}
    for item in items:
        if item.slug in first_paths:
            raise ValueError(
                f"Duplicate public edition URL {item.rel_url}: "
                f"{first_paths[item.slug].name} and {item.source_path.name}"
            )
        first_paths[item.slug] = item.source_path
    items.sort(key=lambda x: x.sort_key)
    return items, slug_map


# ==============================================================================
# 3. HTML SANITIZATION, LINK REWRITING, TABLE WRAPPING & TOC EXTRACTION
# ==============================================================================

_SVG_SPLIT_RE = re.compile(r"(<svg\b[^>]*>.*?</svg>)", flags=re.DOTALL | re.IGNORECASE)
_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")
_HREF_RE = re.compile(r'href="([^"]*)"')
_HEADING_RE = re.compile(r"<(h[123])(\b[^>]*)>(.*?)</\1>", flags=re.DOTALL | re.IGNORECASE)

_LIT_CMT_OPEN = "___LIT_CMT_OPEN___"
_LIT_CMT_CLOSE = "___LIT_CMT_CLOSE___"
_GIR_REL_PREFIX = "https://gir-local.invalid/"
_FENCED_CODE_SPLIT_RE = re.compile(r"(```.*?```)", flags=re.DOTALL)
_INLINE_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_REL_MD_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]+)\]\((?!(?:https?://|mailto:|tel:|#|file://))([^)\s]+)\)"
)

# Internal engineering files/tooling that must never leak onto public scorecard/changelog pages
_HARD_INFRA_RE = re.compile(
    r"(?:sidecar\.json|RSI_PLAYBOOK(?:\.md)?|rsi_metrics\.json|"
    r"master_snapshot\.json|multi_asset_channels\.json|etf_universe\.json|deep_dossiers\.json|"
    r"policy_calendar\.json|realtime-monitor\.sqlite3|notify\.example\.json|notify\.json|"
    r"permissions\.json|unified-edition\.prompt\.md|"
    r"DAILY_FORMAT_SPEC\.md|DAILY_REPORT_SPEC\.md|"
    r"lint_readability\.py|lint_equity\.py|lint_site\.py|"
    r"build_(?:daily|report|site|a_share_pdf|hk_stock_pdf|us_stock_pdf|pdf)\.py|"
    r"publish_site\.py|pdf_common\.py|docx_embed\.py|"
    r"edition_run\.py|artifact_receipt\.py|edition_plan\.py|edition_validation\.py|"
    r"chart_input\.py|install_sidecars\.py|patch_state_dbs\.py|svg_geometry\.py|fetch_kline_data\.py|"
    r"visual_widgets\.py|realtime_monitor\.py|wechat_notify\.py|"
    r"_edition_patch\.json|_ledger_patch\.json|_rsi_patch\.json|_audit_patch\.json|"
    r"_rollover_patch\.json|_archive_patch\.json|"
    r"AGENTS\.md|SKILL\.md|GEMINI\.md|audit_ledger\.md|gold-research-publishing|"
    r"5-plus-1-research-playbook(?:\.md)?|directives-and-snapshot-schema(?:\.md)?|"
    r"矢量\s*SVG\s*图表完成逐像素|"
    r"\btextutil\b)",
    flags=re.IGNORECASE,
)
_SOFT_FILENAME_REPS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"`?data_snapshot\.json`?", re.IGNORECASE), "实时数据快照"),
    (re.compile(r"`?master_snapshot\.json`?", re.IGNORECASE), "主报告基线快照"),
    (re.compile(r"`?market_calendar\.json`?", re.IGNORECASE), "跨市场交易日历"),
    (re.compile(r"新架构与\s*RSI\s*闭环首次实战跑"), "日终清算与产业链深挖"),
    (re.compile(r"\s*\+\s*原生\s*OOXML\s*Word\s*引擎"), ""),
    (re.compile(r"独立红队质检与法证审计账本"), "独立核查与辟谣账本"),
    (re.compile(r"红队质检与法证审计账本"), "独立核查与辟谣账本"),
    (re.compile(r"红队法证档案"), "独立核查档案"),
    (re.compile(r"独立红队交叉核验"), "多源独立交叉核验"),
    (re.compile(r"红队交叉核验"), "多源独立交叉核验"),
    (re.compile(r"红队审计记录"), "独立核查记录"),
    (re.compile(r"独立红队"), "独立核查"),
    (re.compile(r"红队"), "独立核查"),
    (re.compile(r"Tier\s*0\s*/\s*1\s*/\s*2\s*/\s*3", re.IGNORECASE), "四档红绿灯（红灯停/黄灯/绿灯/重仓）"),
    (re.compile(r"\bTier\s*0\b", re.IGNORECASE), "红灯停"),
    (re.compile(r"\bTier\s*1\b", re.IGNORECASE), "黄灯试探"),
    (re.compile(r"\bTier\s*2\b", re.IGNORECASE), "绿灯建仓"),
    (re.compile(r"\bTier\s*3\b", re.IGNORECASE), "顺风重仓"),
    (re.compile(r"\d+\s*门禁\s*Linter", re.IGNORECASE), "多源数据自动核查"),
    (re.compile(r"\bLinter\b", re.IGNORECASE), "多源数据自动核查"),
    (re.compile(r"[（(](?:AUDIT_LOG|CHANGELOG|INDEX)[）)]"), ""),
    (re.compile(r"`?AUDIT_LOG\s*#(\d+)`?"), r"核查记录 #\1"),
    (re.compile(r"<code>\s*daily/[A-Za-z0-9_*.\u4e00-\u9fff-]+\.md\s*</code>", re.IGNORECASE), "站内研报档案"),
    (re.compile(r"(?<!\]\()(?<!href=\")(?<!href=')`?daily/[A-Za-z0-9_*.\u4e00-\u9fff-]+\.md`?"), "站内研报档案"),
    (re.compile(r"daily/\s*目录下"), "站内"),
)
_SCORECARD_TOP_NAV_RE = re.compile(r"^>\s*(?:返回|快速导航|关联公开档案)\s*[：:]")


def normalize_relative_md_links(md_text: str) -> str:
    """Wrap bare/relative Markdown links (e.g. [x](AUDIT_LOG.md), [x](../report.pdf))
    into a sentinel https://gir-local.invalid/ URL outside code blocks/inline code so both
    gold/build_daily.py and equity/pdf_common.py parse them as <a> tags before _rewrite_href()."""
    parts = _FENCED_CODE_SPLIT_RE.split(md_text)
    for idx, seg in enumerate(parts):
        if idx % 2 == 1:
            continue
        code_segs = re.split(r"(`[^`\n]+`)", seg)
        for j in range(0, len(code_segs), 2):
            if code_segs[j]:
                code_segs[j] = _REL_MD_LINK_RE.sub(
                    lambda m: f"[{m.group(1)}]({_GIR_REL_PREFIX}{m.group(2)})",
                    code_segs[j],
                )
        parts[idx] = "".join(code_segs)
    return "".join(parts)


def protect_backticked_comments(md_text: str) -> str:
    """Pre-escape HTML comment delimiters inside code blocks and inline backticks
    before calling gold/build_daily.py parse_markdown_to_html() so literal
    `<!-- MASTER_BASELINE {...} -->` never gets stripped before backtick parsing."""
    parts = _FENCED_CODE_SPLIT_RE.split(md_text)
    for idx, seg in enumerate(parts):
        if idx % 2 == 1:
            parts[idx] = seg.replace("<!--", _LIT_CMT_OPEN).replace("-->", _LIT_CMT_CLOSE)
        else:
            parts[idx] = _INLINE_BACKTICK_RE.sub(
                lambda m: "`"
                + m.group(1).replace("<!--", _LIT_CMT_OPEN).replace("-->", _LIT_CMT_CLOSE)
                + "`",
                seg,
            )
    return "".join(parts)


def restore_backticked_comments(html_str: str) -> str:
    """Restore protected literal HTML comment syntax safely inside rendered HTML."""
    if _LIT_CMT_OPEN not in html_str and _LIT_CMT_CLOSE not in html_str:
        return html_str
    return html_str.replace(_LIT_CMT_OPEN, "&lt;!--").replace(_LIT_CMT_CLOSE, "--&gt;")


def _clean_soft_filenames(line: str) -> str:
    out = line
    for pat, repl in _SOFT_FILENAME_REPS:
        out = pat.sub(repl, out)
    return out


def _strip_scorecard_top_nav(md_text: str) -> str:
    """Remove obsolete Markdown cross-file nav blockquotes (tabs already unify all 5 ledgers)."""
    out: list[str] = []
    for idx, line in enumerate(md_text.splitlines()):
        if idx < 12 and _SCORECARD_TOP_NAV_RE.match(line.strip()):
            if out and out[-1].endswith("  "):
                out[-1] = out[-1].rstrip()
            continue
        out.append(line)
    return "\n".join(out)


def sanitize_public_ledger_md(md_text: str, *, is_audit_log: bool = False) -> str:
    """Sanitize internal engineering entries from gold CHANGELOG.md / AUDIT_LOG.md
    for public reader-facing scorecard tabs while preserving all market & method evolution."""
    raw_lines = md_text.splitlines()

    if is_audit_log:
        out_lines: list[str] = []
        skip_section = False
        for line in raw_lines:
            st = line.strip()
            if st.startswith("## "):
                skip_section = bool(
                    re.search(r"系统全栈架构升级留痕|全栈架构升级|工程架构升级|自动化脚本", st)
                )
                if skip_section:
                    # Drop preceding separator if immediately above skipped section
                    while out_lines and out_lines[-1].strip() in ("", "---"):
                        out_lines.pop()
                    continue
            if skip_section:
                continue
            # Filter pure internal-engineering numbered items in Asset 2
            if re.match(r"^\d+\.\s+", st) and _HARD_INFRA_RE.search(line):
                continue
            if st.startswith("### ") and "核心模型与出版架构升级" in st:
                line = line.replace(" 15 次核心模型与出版架构升级", "核心量化模型与风控体系升级").replace(
                    "15 次核心模型与出版架构升级", "核心量化模型与风控体系升级"
                )
            if _HARD_INFRA_RE.search(line):
                continue
            out_lines.append(_clean_soft_filenames(line))
        return "\n".join(out_lines)

    # gold/daily/CHANGELOG.md sanitization
    # 1. Clean leading blockquote block if it contains internal engineering references
    cleaned_lines: list[str] = []
    i = 0
    n = len(raw_lines)
    while i < n:
        line = raw_lines[i]
        st = line.strip()
        if i < 15 and st.startswith(">"):
            q_block: list[str] = []
            while i < n and raw_lines[i].strip().startswith(">"):
                q_block.append(raw_lines[i])
                i += 1
            joined_q = "\n".join(q_block)
            if _HARD_INFRA_RE.search(joined_q):
                cleaned_lines.append(
                    "> **账本定位**：本日志按时间倒序记录每日早晚报对实盘锚、买金四步红绿灯、核心论点与数据口径的全部公开演进与透明修正。详细谣言证伪与官方核查记录同步沉淀于「黄金辟谣核查账本」。"
                )
            else:
                cleaned_lines.extend(_clean_soft_filenames(q) for q in q_block)
            continue
        cleaned_lines.append(line)
        i += 1

    # 2. Split into sections on "## " headings; filter internal-engineering bullets and empty sections
    sections: list[tuple[str | None, list[str]]] = []
    cur_hdr: str | None = None
    cur_body: list[str] = []
    for line in cleaned_lines:
        if line.startswith("## "):
            sections.append((cur_hdr, cur_body))
            cur_hdr = _clean_soft_filenames(line)
            cur_body = []
        else:
            cur_body.append(line)
    sections.append((cur_hdr, cur_body))

    final_lines: list[str] = []
    for hdr, body in sections:
        if hdr is None:
            for ln in body:
                if not _HARD_INFRA_RE.search(ln):
                    final_lines.append(_clean_soft_filenames(ln))
            continue

        kept_body: list[str] = []
        substantive_bullets = 0
        for ln in body:
            st = ln.strip()
            if _HARD_INFRA_RE.search(ln):
                continue
            cleaned_ln = _clean_soft_filenames(ln)
            if st.startswith(("- ", "* ", "• ")):
                if not any(
                    tag in st for tag in ("本期归档文件", "最新标杆归档文件", "当日归档文件")
                ):
                    substantive_bullets += 1
            kept_body.append(cleaned_ln)

        # Skip section completely if every substantive bullet was internal engineering
        if substantive_bullets == 0:
            continue

        final_lines.append(hdr)
        final_lines.extend(kept_body)

    # Collapse duplicate consecutive --- separators
    deduped: list[str] = []
    prev_sep = False
    for ln in final_lines:
        is_sep = ln.strip() == "---"
        if is_sep and prev_sep:
            continue
        deduped.append(ln)
        if ln.strip():
            prev_sep = is_sep
    return "\n".join(deduped)


def _rewrite_href(raw_href: str, base_prefix: str, slug_map: dict[str, str], ctx_market: str) -> str:
    href = html_mod.unescape(raw_href).strip()
    had_sentinel = False
    for _pref in (_GIR_REL_PREFIX, "http://gir-local.invalid/"):
        if href.lower().startswith(_pref):
            href = href[len(_pref) :].strip()
            had_sentinel = True
            break
    if not href:
        return "#"

    # Explicitly block dangerous URI schemes (XSS / data exfiltration guard)
    scheme_probe = re.sub(r"[\x00-\x20]+", "", href).lower()
    if scheme_probe.startswith(("javascript:", "data:", "vbscript:", "blob:")):
        return "#"
    if "gir-local.invalid" in scheme_probe:
        return "#"

    if href.startswith("#") or scheme_probe.startswith(("mailto:", "tel:")):
        return href
    if scheme_probe.startswith(("http://", "https://")):
        return href

    lower = href.lower()
    decoded = urllib.parse.unquote(href)

    # Check known portal destinations
    if "index.md" in lower:
        return f"{base_prefix}index.html"
    if "scorecard.md" in lower:
        tab = "gold-scorecard" if ("gold" in lower or ctx_market == "gold") else "equity-scorecard"
        return f"{base_prefix}scorecard.html#{tab}"
    if "changelog.md" in lower:
        tab = "gold-changelog" if ("gold" in lower or ctx_market == "gold") else "equity-changelog"
        return f"{base_prefix}scorecard.html#{tab}"
    if "audit_log.md" in lower:
        return f"{base_prefix}scorecard.html#gold-audit-log"

    # Flagship reports
    if "a_share_market_report" in lower:
        return f"{base_prefix}reports/a-share.html"
    if "hk_stock_market_report" in lower:
        return f"{base_prefix}reports/hk-stock.html"
    if "us_stock_market_report" in lower:
        return f"{base_prefix}reports/us-stock.html"
    if "黄金跨世纪周期" in decoded:
        return f"{base_prefix}reports/gold.html"

    # Latest mobile HTML files
    if "latest_a_share.html" in lower:
        return f"{base_prefix}daily/a-share-latest.html"
    if "latest_hk_stock.html" in lower:
        return f"{base_prefix}daily/hk-stock-latest.html"
    if "latest_us_stock.html" in lower:
        return f"{base_prefix}daily/us-stock-latest.html"
    if "latest_gold.html" in lower:
        return f"{base_prefix}daily/gold-latest.html"

    # Dated daily files (.md / .pdf / .docx)
    basename = Path(decoded.split("#")[0].split("?")[0]).name
    stem = Path(basename).stem
    if basename in slug_map:
        return f"{base_prefix}daily/{slug_map[basename]}.html"
    if stem in slug_map:
        return f"{base_prefix}daily/{slug_map[stem]}.html"

    # Fallback: NEVER allow file://, /Users/, /home/, gir-local.invalid/, or broken local .md/.pdf/.docx paths
    if (
        lower.startswith("file://")
        or "/users/" in lower
        or re.search(r"(?<![a-z0-9._-])/home/", lower)
        or lower.endswith((".md", ".pdf", ".docx"))
        or "gir-local.invalid" in lower
    ):
        return f"{base_prefix}archive.html"

    # Unmapped sentinel relative links must never leak gir-local.invalid/ or break Gate S2
    if had_sentinel:
        clean_path = href.split("#", 1)[0].split("?", 1)[0].lstrip("./")
        known_static = (
            "index.html",
            "charts.html",
            "channels.html",
            "etfs.html",
            "screener.html",
            "scorecard.html",
            "archive.html",
            "guide.html",
        )
        if clean_path in known_static or clean_path.startswith(("reports/", "daily/", "channels/")):
            return f"{base_prefix}{href.lstrip('./')}"
        return f"{base_prefix}archive.html"

    return href


def _strip_local_paths_in_text(fragment: str) -> str:
    """Remove any stray file://, /Users/..., or /home/... paths and internal snapshot filenames in plain text."""
    parts = _TAG_SPLIT_RE.split(fragment)
    for i in range(0, len(parts), 2):
        txt = parts[i]
        if not txt:
            continue
        if "file://" in txt.lower() or "/Users/" in txt or "/home/" in txt:
            txt = re.sub(r"file://[^\s<\"'）)》」]+", "（已归档）", txt, flags=re.IGNORECASE)
            txt = re.sub(r"(?:/Users/|(?<![A-Za-z0-9._-])/home/)[^\s<\"'）)》」`]+", "（站内文档）", txt)
        if "master_snapshot.json" in txt.lower():
            txt = re.sub(r"master_snapshot\.json", "主报告基线快照", txt, flags=re.IGNORECASE)
        parts[i] = txt
    return "".join(parts)


def _ensure_tables_wrapped(html_str: str) -> str:
    """Ensure every <table> (including gold sn-table & glossary-table) is wrapped in .table-wrap."""
    # Wrap sn-table inside sn-box if not already wrapped
    html_str = re.sub(
        r'(?<!class="table-wrap sn-scroll">)(<table\s+class="sn-table"[^>]*>.*?</table>)',
        r'<div class="table-wrap sn-scroll">\1</div>',
        html_str,
        flags=re.DOTALL,
    )
    # Wrap glossary-table if not already wrapped
    html_str = re.sub(
        r'(?<!class="table-wrap">)(<table\s+class="glossary-table"[^>]*>.*?</table>)',
        r'<div class="table-wrap">\1</div>',
        html_str,
        flags=re.DOTALL,
    )
    # Safety net: wrap any other bare <table> not preceded by table-wrap">
    out: list[str] = []
    pos = 0
    for m in re.finditer(r"<table\b[^>]*>.*?</table>", html_str, flags=re.DOTALL | re.IGNORECASE):
        before = html_str[pos : m.start()]
        tail_check = before[-80:] if len(before) > 80 else before
        out.append(before)
        if "table-wrap" in tail_check:
            out.append(m.group(0))
        else:
            out.append(f'<div class="table-wrap">{m.group(0)}</div>')
        pos = m.end()
    out.append(html_str[pos:])
    wrapped = "".join(out)
    wrapped = re.sub(
        r'(?<!mobile-scroll-cue" aria-hidden="true">← 左右滑动查看完整列 →</div>)(<div class="table-wrap\b)',
        r'<div class="mobile-scroll-cue" aria-hidden="true">← 左右滑动查看完整列 →</div>\1',
        wrapped,
    )
    return wrapped


def _normalize_chart_boxes(html_str: str) -> str:
    """Ensure every .chart-box SVG sits on a crisp white stage with uniform zoom hint."""
    # Update existing equity svg-hint wording
    html_str = re.sub(
        r'<div class="svg-hint">.*?</div>',
        '<div class="svg-hint">🔍 点击图表可全屏放大 · 移动端支持缩放查看</div>',
        html_str,
        flags=re.DOTALL,
    )

    def _wrap_chart_box(m: re.Match) -> str:
        box = m.group(0)
        if 'class="svg-scroll"' in box or 'class="chart-svg-stage"' in box:
            return box
        return re.sub(
            r"(<svg\b[^>]*>.*?</svg>)",
            r'<div class="chart-svg-stage">\1</div><div class="svg-hint">🔍 点击图表可全屏放大 · 移动端支持缩放查看</div>',
            box,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )

    return re.sub(
        r'<div class="chart-box(?:\s+[^"]*)?">.*?(?=<div class="chart-note">|<div class="chart-takeaway">|<div class="vchart-takeaway">|</div>\s*$)',
        _wrap_chart_box,
        html_str,
        flags=re.DOTALL,
    )


_BARE_URL_LINK_RE = re.compile(
    r"<a\b([^>]*)>(\s*https?://[^<\s][^<]*?)</a>",
    flags=re.IGNORECASE,
)


def _shorten_bare_url_links(html_seg: str) -> str:
    """Shorten long bare URL display labels (>42 chars) inside <a> to '<domain> ↗' while preserving href/title."""
    def _repl(m: re.Match) -> str:
        attrs = m.group(1) or ""
        raw_label = html_mod.unescape(m.group(2)).strip()
        if len(raw_label) <= 42:
            return m.group(0)
        netloc = urllib.parse.urlsplit(raw_label).netloc.strip()
        if netloc.lower().startswith("www."):
            netloc = netloc[4:]
        if not netloc:
            return m.group(0)
        if not re.search(r'\btitle\s*=', attrs, flags=re.IGNORECASE):
            attrs = f'{attrs} title="{esc(raw_label)}"'
        return f"<a{attrs}>{esc(netloc)} ↗</a>"

    return _BARE_URL_LINK_RE.sub(_repl, html_seg)


def estimate_reading_minutes(body_html: str) -> int:
    """Estimate Chinese + Latin reading duration (420 units/min, floor 2 min)."""
    no_svg = _SVG_SPLIT_RE.sub(" ", body_html or "")
    plain = html_mod.unescape(strip_tags(no_svg))
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", plain))
    latin_words = len(re.findall(r"[A-Za-z0-9]+", plain))
    return max(2, int(round((cjk_count + latin_words) / 420.0)))


def sanitize_and_extract_toc(
    body_html: str,
    *,
    base_prefix: str,
    slug_map: dict[str, str],
    ctx_market: str,
    extract_toc: bool = True,
    id_prefix: str = "",
) -> tuple[str, list[tuple[int, str, str]], int]:
    """Sanitize rendered HTML (zero comments, zero file:// or /Users/, wrapped tables, unique TOC IDs)."""
    # Protect inline <svg> blocks from text mutations
    segments = _SVG_SPLIT_RE.split(body_html)
    svg_count = len(segments) // 2

    for i in range(0, len(segments), 2):
        seg = segments[i]
        # 1. Strip all HTML comments
        seg = re.sub(r"<!--.*?-->", "", seg, flags=re.DOTALL)
        # 2. Rewrite href attributes
        seg = _HREF_RE.sub(
            lambda m: f'href="{esc(_rewrite_href(m.group(1), base_prefix, slug_map, ctx_market))}"',
            seg,
        )
        # 3. Shorten long bare URL display labels (>42 chars) to '<domain> ↗'
        seg = _shorten_bare_url_links(seg)
        # 4. Strip any leaked local paths in text
        seg = _strip_local_paths_in_text(seg)
        # 5. Restore any literal HTML comments that were inside code spans/blocks
        seg = restore_backticked_comments(seg)
        segments[i] = seg

    cleaned = "".join(segments)
    cleaned = _ensure_tables_wrapped(cleaned)
    cleaned = _normalize_chart_boxes(cleaned)

    # Extract headings & assign deterministic unique IDs (also prefixes IDs whenever id_prefix is set)
    toc: list[tuple[int, str, str]] = []
    if extract_toc or id_prefix:
        used_ids: set[str] = set()
        counters = {1: 0, 2: 0, 3: 0}
        has_vol_header = bool(
            re.search(r'<h[12]\b[^>]*\bclass="[^"]*\bvol-header\b', cleaned, flags=re.IGNORECASE)
        )

        def _proc_heading(m: re.Match) -> str:
            tag = m.group(1).lower()
            attrs = m.group(2) or ""
            inner = m.group(3)
            is_vol_header = bool(
                re.search(r'\bclass="[^"]*\bvol-header\b', attrs, flags=re.IGNORECASE)
            )
            if is_vol_header:
                lvl = 1
            elif tag == "h2" and has_vol_header:
                lvl = 2
            else:
                lvl = int(tag[1])
            id_m = re.search(r'\bid="([^"]+)"', attrs)
            if id_m:
                raw_id = id_m.group(1)
                cand = f"{id_prefix}{raw_id}" if (id_prefix and not raw_id.startswith(id_prefix)) else raw_id
                if cand not in used_ids:
                    hid = cand
                else:
                    counters[lvl] += 1
                    prefix = "sec" if lvl == 1 else f"h{lvl}"
                    hid = f"{id_prefix}{prefix}-{counters[lvl]}"
                    while hid in used_ids:
                        counters[lvl] += 1
                        hid = f"{id_prefix}{prefix}-{counters[lvl]}"
                if hid != raw_id:
                    attrs = re.sub(r'\bid="[^"]+"', f'id="{hid}"', attrs)
            else:
                counters[lvl] += 1
                prefix = "sec" if lvl == 1 else f"h{lvl}"
                hid = f"{id_prefix}{prefix}-{counters[lvl]}"
                while hid in used_ids:
                    counters[lvl] += 1
                    hid = f"{id_prefix}{prefix}-{counters[lvl]}"
                attrs = f' id="{hid}"{attrs}'
            used_ids.add(hid)
            if extract_toc:
                label = html_mod.unescape(strip_tags(inner))
                label = re.sub(r"\s+", " ", label).strip()
                if label:
                    toc.append((lvl, hid, label))
            return f"<{tag}{attrs}>{inner}</{tag}>"

        # Apply heading extraction only outside <svg> blocks
        segs2 = _SVG_SPLIT_RE.split(cleaned)
        for i in range(0, len(segs2), 2):
            segs2[i] = _HEADING_RE.sub(_proc_heading, segs2[i])
        cleaned = "".join(segs2)

    return cleaned, toc, svg_count


# ==============================================================================
# 4. GLOBAL STOCK SCREENER EXTRACTOR
# ==============================================================================

COLOR_LABELS = {
    "g": "当下底座",
    "b": "未来主攻",
    "y": "分歧观察",
    "r": "高危回避",
}


def _detect_color(text: str) -> str:
    if "🟢" in text:
        return "g"
    if "🔵" in text:
        return "b"
    if "🔴" in text:
        return "r"
    if "🟡" in text:
        return "y"
    if "底座" in text:
        return "g"
    if "主攻" in text:
        return "b"
    if "回避" in text:
        return "r"
    return "y"


def _split_md_cells(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith(r"\|"):
        inner = inner[:-1]
    return [c.replace(r"\|", "|").strip() for c in re.split(r"(?<!\\)\|", inner)]


def _is_sep_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.match(r"^:?-{2,}:?$", c) for c in cells)


def _parse_app2_rows(md_text: str) -> list[list[str]]:
    idx = md_text.find("## 附表二")
    if idx == -1:
        raise RuntimeError("Could not locate '## 附表二' table in equity flagship markdown")
    section = md_text[idx:]
    rows: list[list[str]] = []
    started = False
    for raw in section.splitlines():
        st = raw.strip()
        if st.startswith("|") and st.endswith("|"):
            cells = _split_md_cells(st)
            if _is_sep_row(cells):
                started = True
                continue
            if started:
                rows.append(cells)
        elif started and st and not st.startswith("|"):
            break
    return rows


def _to_pos_float(raw: str) -> float | None:
    try:
        v = float(raw.replace(",", "").replace("−", "-"))
    except ValueError:
        return None
    return v if isfinite(v) and v > 0 else None


def _parse_price_num(price_str: str) -> float | None:
    head = re.split(r"[（(]", str(price_str or ""), maxsplit=1)[0].strip()
    # Strip leading date stamps like "11/26" or "2026-11-26" or "11/24–25" before reading quote numbers
    head = re.sub(
        r"^(?:20\d{2}[-/.])?\d{1,2}/\d{1,2}(?:\s*[–—\-~]\s*\d{1,2}(?:/\d{1,2})?)?\s*",
        "",
        head,
    ).strip()
    m_rng = re.search(
        r"(?:约\s*)?[\$￥¥]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*[–—\-~]\s*[\$￥¥]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        head,
    )
    if m_rng:
        lo, hi = _to_pos_float(m_rng.group(1)), _to_pos_float(m_rng.group(2))
        if lo is not None and hi is not None:
            return round((lo + hi) / 2.0, 2)
    m_one = re.search(r"[\$￥¥]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", head)
    if m_one:
        return _to_pos_float(m_one.group(1))
    return None


_NON_PE_MULTIPLE_CN = (
    "亏损",
    "负值",
    "—",
    "核心溢利",
    "年化收入",
    "收入",
    "营收",
    "销售",
    "营运资金",
    "市销",
)
_NON_PE_MULTIPLE_EN_RE = re.compile(
    r"(?<![A-Za-z])(?:A?FFO|ARR|P/S|EV/Sales)(?![A-Za-z])",
    re.IGNORECASE,
)
_GOLD_LOCKED_CODES: frozenset[str] = frozenset(
    {"601899", "600547", "02899.HK", "06181.HK", "01929.HK", "NEM", "FCX"}
)
_LEADING_RATING_PREFIX_RE = re.compile(
    r"^[🟢🔵🟡🔴]\s*(?:🔒\s*)?(?:当下底座|未来主攻|分歧观察|高危回避)[；;：:\s]*"
)


def _parse_pe_num(valuation: str, market: str = "") -> float | None:
    txt = str(valuation or "").strip()
    if not txt:
        return None
    # Strip 4-digit calendar/fiscal years (e.g., "2027 预期", "FY2026") so they are never mistaken for PE ratios
    clean_txt = re.sub(
        r"(?:FY)?20\d{2}\s*(?:年|E|预期|远期|前瞻)?",
        " ",
        txt,
        flags=re.IGNORECASE,
    )
    m_lbl = re.search(
        r"(?:(?:TTM|FWD|前瞻|静态|动态|滚动|现价|扣现金经营)?\s*(?:(?<![A-Za-z])PE(?:\s*[-–—]\s*(?:TTM|FWD))?|市盈率)\s*[（(]?(?:TTM|FWD)?[）)]?\s*(?:预期|远期)?\s*[:：]?\s*[~≈<>≤≥约]?\s*)([0-9]+(?:\.[0-9]+)?)(?!\s*年)",
        clean_txt,
        flags=re.IGNORECASE,
    )
    if m_lbl:
        v = _to_pos_float(m_lbl.group(1))
        return round(v, 1) if (v is not None and v < 5000) else None
    target = clean_txt.split("/", 1)[0].strip() if market in ("a-share", "hk-stock") else clean_txt
    if any(tok in target for tok in _NON_PE_MULTIPLE_CN) or _NON_PE_MULTIPLE_EN_RE.search(target):
        return None
    m_x = re.search(
        r"[~≈<>≤≥]?\s*([0-9]+(?:\.[0-9]+)?)(?:\s*[–—\-~]\s*[0-9]+(?:\.[0-9]+)?)?\s*x\+?",
        target,
        flags=re.IGNORECASE,
    )
    if m_x:
        v = _to_pos_float(m_x.group(1))
        return round(v, 1) if (v is not None and v < 5000) else None
    return None


def _parse_div_pct(valuation: str, summary: str, market: str = "") -> float | None:
    val_str = str(valuation or "")
    # 1. Structured slash-separated dividend field in valuation takes precedence
    parts = [p.strip() for p in val_str.split("/")]
    idx = 2 if (market == "a-share" and len(parts) >= 3) else (1 if (market == "hk-stock" and len(parts) >= 2) else -1)
    if idx != -1:
        seg = parts[idx]
        if "AH" not in seg.upper() and not seg.startswith(("+", "-", "−")):
            m_seg = re.search(r"(?<![+\-−0-9.])([0-9]+(?:\.[0-9]+)?)(?:\s*[–—\-~]\s*[0-9.]+)?%", seg)
            if m_seg:
                v = _to_pos_float(m_seg.group(1))
                if v is not None and v <= 25.0:
                    return round(v, 2)
    # 2. Explicit dividend-yield label scan (valuation first, then summary)
    for src in (val_str, str(summary or "")):
        # Ignore 派息率 / 分红率 payout ratios; match explicit dividend yield labels
        cleaned = re.sub(r"(?:派息率|分红率)\s*[~≈约]?\s*[0-9.]+%", "", src)
        m = re.search(
            r"(?:股息率|股息|息率|(?<![高降加升派分])息)\s*[~≈约]?\s*([0-9]+(?:\.[0-9]+)?)(?:\s*[–—\-~]\s*[0-9.]+)?%",
            cleaned,
        )
        if m:
            v = _to_pos_float(m.group(1))
            if v is not None and v <= 25.0:
                return round(v, 2)
        m_rev = re.search(r"(?<![+\-−0-9.])([0-9]+(?:\.[0-9]+)?)%\s*(?:高?息|股息)", cleaned)
        if m_rev:
            v = _to_pos_float(m_rev.group(1))
            if v is not None and v <= 25.0:
                return round(v, 2)
    return None


def _parse_ah_pct(
    valuation: str,
    summary: str,
    market: str,
    code: str,
    ah_lookup: dict[str, float],
) -> float | None:
    # Live market_state.ah_benchmarks lookup always takes precedence over stale flagship strings
    if code:
        if code in ah_lookup:
            return round(ah_lookup[code], 1)
        code_u = code.strip().upper()
        if code_u in ah_lookup:
            return round(ah_lookup[code_u], 1)
    for src in (str(valuation or ""), str(summary or "")):
        m = re.search(
            r"(?:AH\s*(?:溢价|折价|倒挂)?|A\s*折\s*H)\s*[:：]?\s*([+\-−]?[0-9]+(?:\.[0-9]+)?)%",
            src,
            flags=re.IGNORECASE,
        )
        if m:
            try:
                raw_num = m.group(1).replace("−", "-")
                v = float(raw_num)
                if not raw_num.startswith(("+", "-")) and re.search(
                    r"倒挂|折价|A\s*折\s*H", m.group(0), flags=re.IGNORECASE
                ):
                    v = -abs(v)
                if isfinite(v) and -90.0 <= v <= 500.0:
                    return round(v, 1)
            except ValueError:
                pass
    if market == "a-share":
        parts = [p.strip() for p in str(valuation or "").split("/")]
        if len(parts) >= 4:
            m_tail = re.fullmatch(r"([+\-−][0-9]+(?:\.[0-9]+)?)%", parts[3])
            if m_tail:
                try:
                    v = float(m_tail.group(1).replace("−", "-"))
                    if isfinite(v) and -90.0 <= v <= 500.0:
                        return round(v, 1)
                except ValueError:
                    pass
    return None


def _sync_valuation_str(
    valuation: str,
    market: str,
    *,
    pe_num: float | None = None,
    pb_num: float | None = None,
    div_pct: float | None = None,
    ah_pct: float | None = None,
) -> str:
    """Cleanly update PE/PB/Div/AH segments in stock['valuation'] without breaking chip formatting."""
    val = str(valuation or "").strip()
    if not val:
        return val

    # 1. Explicit inline AH chip replacement (e.g. "AH 倒挂 -16%" -> "AH 倒挂 -19.7%")
    if ah_pct is not None:
        ah_lbl = f"AH 倒挂 {ah_pct:+.1f}%" if ah_pct < 0 else f"AH 溢价 {ah_pct:+.1f}%"
        val = re.sub(
            r"(?:深度\s*)?(?:AH\s*(?:溢价|折价|倒挂)?|A\s*折\s*H)\s*[:：]?\s*[+\-−]?[0-9]+(?:\.[0-9]+)?%",
            ah_lbl,
            val,
            count=1,
            flags=re.IGNORECASE,
        )

    # 2. Structured slash-separated segments
    if "/" in val:
        parts = [p.strip() for p in val.split("/")]
        if market == "a-share" and len(parts) >= 4:
            if pe_num is not None and not (
                any(tok in parts[0] for tok in _NON_PE_MULTIPLE_CN) or _NON_PE_MULTIPLE_EN_RE.search(parts[0])
            ):
                if re.search(r"[0-9].*x", parts[0], re.IGNORECASE):
                    parts[0] = f"{pe_num:.1f}x"
            if pb_num is not None and (re.search(r"[0-9].*x", parts[1], re.IGNORECASE) or parts[1] == "—"):
                parts[1] = f"{pb_num:.2f}x"
            if div_pct is not None and ("%" in parts[2] or parts[2] == "—"):
                parts[2] = f"{div_pct:.1f}%"
            if ah_pct is not None and re.fullmatch(r"[+\-−]?[0-9]+(?:\.[0-9]+)?%", parts[3]):
                parts[3] = f"{ah_pct:+.1f}%"
            return " / ".join(parts)
        if market == "hk-stock" and len(parts) >= 2:
            if pe_num is not None and not (
                any(tok in parts[0] for tok in _NON_PE_MULTIPLE_CN) or _NON_PE_MULTIPLE_EN_RE.search(parts[0])
            ):
                if re.search(r"PE", parts[0], re.IGNORECASE):
                    parts[0] = f"PE {pe_num:.1f}x"
                elif re.search(r"[0-9].*x", parts[0], re.IGNORECASE):
                    parts[0] = f"{pe_num:.1f}x"
            if div_pct is not None and "AH" not in parts[1].upper() and not parts[1].startswith(("+", "-", "−")):
                if "%" in parts[1]:
                    parts[1] = f"{div_pct:.1f}%"
            return " / ".join(parts)
        return val

    # 3. Single-segment valuation (primarily us-stock e.g. "9.1–10.7x" or "前瞻 PE 28x")
    if pe_num is not None and not (
        any(tok in val for tok in _NON_PE_MULTIPLE_CN) or _NON_PE_MULTIPLE_EN_RE.search(val)
    ):
        if re.search(r"(?:PE|市盈率)", val, re.IGNORECASE):
            return re.sub(
                r"(?:(?:TTM|FWD|前瞻|静态|动态)?\s*(?:PE(?:-TTM)?|市盈率)\s*(?:(?:FY)?20\d{2}\s*(?:年|E|预期|远期)?)?\s*[:：]?\s*[~≈<>≤≥约]?\s*)[0-9]+(?:\.[0-9]+)?(?:\s*[–—\-~]\s*[0-9]+(?:\.[0-9]+)?)?\s*x?\+?",
                f"PE {pe_num:.1f}x",
                val,
                count=1,
                flags=re.IGNORECASE,
            )
        if re.fullmatch(r"[~≈<>≤≥]?\s*[0-9]+(?:\.[0-9]+)?(?:\s*[–—\-~]\s*[0-9]+(?:\.[0-9]+)?)?\s*x\+?", val, re.IGNORECASE):
            return f"{pe_num:.1f}x"
    return val


def _parse_anchor(summary: str, price_num: float | None) -> tuple[float | None, float | None, float | None]:
    txt = str(summary or "")
    lo: float | None = None
    hi: float | None = None
    m_rng = re.search(
        r"(?:安全锚|重估锚|极值锚|深坑锚|买点锚|锚)[：:\s≤<约]*[\$￥¥]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*[–—\-~]\s*[\$￥¥]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        txt,
    )
    if m_rng:
        lo, hi = _to_pos_float(m_rng.group(1)), _to_pos_float(m_rng.group(2))
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
    else:
        m_one = re.search(
            r"(?:安全锚|重估锚|极值锚|深坑锚|买点锚|锚)[：:\s≤<约]*[\$￥¥]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
            txt,
        )
        if m_one:
            v = _to_pos_float(m_one.group(1))
            lo, hi = v, v
        else:
            m_lt = re.search(r"[≤<]\s*[\$￥¥]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:元|港元|美元)?\s*重估", txt)
            if m_lt:
                v = _to_pos_float(m_lt.group(1))
                lo, hi = v, v
    if lo is None or hi is None:
        return None, None, None
    gap: float | None = None
    if price_num is not None and price_num > 0:
        mid = (lo + hi) / 2.0
        if mid > 0:
            raw_gap = round((price_num - mid) / mid * 100.0, 1)
            if -80.0 <= raw_gap <= 250.0:
                gap = raw_gap
    return round(lo, 2), round(hi, 2), gap


def _enrich_stock_metrics(entry: dict[str, Any], ah_lookup: dict[str, float]) -> dict[str, Any]:
    price_num = _parse_price_num(entry["price"])
    pe_num = _parse_pe_num(entry["valuation"], entry["market"])
    div_pct = _parse_div_pct(entry["valuation"], entry["summary"], entry["market"])
    ah_pct = _parse_ah_pct(entry["valuation"], entry["summary"], entry["market"], entry["code"], ah_lookup)
    if ah_pct is not None and entry["code"] in ah_lookup:
        entry["valuation"] = _sync_valuation_str(entry["valuation"], entry["market"], ah_pct=ah_pct)
    anchor_low, anchor_high, anchor_gap_pct = _parse_anchor(entry["summary"], price_num)
    comb_txt = f"{entry['valuation']} {entry['summary']}"
    code_key = str(entry.get("code") or "").strip().upper()
    is_gold_locked = (
        ("禁新买" in comb_txt)
        or ("黄金红灯" in comb_txt)
        or ("金红灯" in comb_txt)
        or (code_key in _GOLD_LOCKED_CODES)
    )
    entry.update(
        {
            "price_num": price_num,
            "pe_num": pe_num,
            "div_pct": div_pct,
            "ah_pct": ah_pct,
            "anchor_low": anchor_low,
            "anchor_high": anchor_high,
            "anchor_gap_pct": anchor_gap_pct,
            "is_gold_locked": is_gold_locked,
        }
    )
    return entry


def extract_all_stocks(
    a_md: str,
    hk_md: str,
    us_md: str,
    *,
    ah_benchmarks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Extract all flagship pool stocks across A-Share, HK-Stock, and US-Stock with 4-color ratings & numeric helpers."""
    ah_lookup: dict[str, float] = {}
    for row in ah_benchmarks or []:
        if not isinstance(row, dict):
            continue
        pct = _safe_float(row.get("ah_premium_pct"))
        if pct is None:
            continue
        for k in ("a", "h"):
            c = str(row.get(k) or "").strip()
            if c:
                ah_lookup[c] = pct

    stocks: list[dict[str, Any]] = []

    # --- 1. A-Share: ## 附表二 cells[4] is color first truth; 5.2 supplies anchor & cross-check ---
    a_s52_map: dict[str, tuple[str, str]] = {}
    m_s52 = re.search(r"(?m)^#{2,3}\s*5\.2\b", a_md)
    if m_s52:
        m_s53 = re.search(r"(?m)^#{2,3}\s*5\.3\b", a_md[m_s52.end() :])
        s52_end = m_s52.end() + m_s53.start() if m_s53 else len(a_md)
        s52_block = a_md[m_s52.start() : s52_end]
        for raw in s52_block.splitlines():
            st = raw.strip()
            if not (st.startswith("|") and st.endswith("|")):
                continue
            cells = _split_md_cells(st)
            if len(cells) < 5 or _is_sep_row(cells):
                continue
            m_code = re.search(r"`(\d{6})`", cells[0])
            if not m_code:
                continue
            code = m_code.group(1)
            col_52 = _detect_color(cells[4])
            anchor_m = re.search(r"(安全锚|重估锚|极值锚)[：:]\s*([^<|]+)", cells[3])
            anchor_txt = f"{anchor_m.group(1)} {anchor_m.group(2).strip()}" if anchor_m else ""
            a_s52_map[code] = (col_52, anchor_txt)

    for cells in _parse_app2_rows(a_md):
        if len(cells) < 5:
            continue
        sector = clean_md_inline_plain(cells[0])
        m_code = re.search(r"`(\d{6})`", cells[1])
        code = m_code.group(1) if m_code else ""
        name = clean_md_inline_plain(re.sub(r"`[^`]+`", "", cells[1]))
        price = clean_md_inline_plain(cells[2])
        valuation = clean_md_inline_plain(cells[3])
        col = _detect_color(cells[4])
        summary_raw = clean_md_inline_plain(cells[4])
        summary = _LEADING_RATING_PREFIX_RE.sub("", summary_raw).strip()
        anchor_txt = ""
        if code in a_s52_map:
            col_52, anchor_txt = a_s52_map[code]
            if col_52 != col:
                raise RuntimeError(
                    f"A-share color drift for {code} ({name}): "
                    f"附表二={col!r} vs 5.2={col_52!r}"
                )
        if anchor_txt and anchor_txt not in summary:
            summary = f"{summary}｜{anchor_txt}"
        stocks.append(
            _enrich_stock_metrics(
                {
                    "market": "a-share",
                    "market_label": "A股",
                    "sector": sector,
                    "name": name,
                    "code": code,
                    "price": price,
                    "valuation": valuation,
                    "color": col,
                    "action_label": COLOR_LABELS[col],
                    "summary": summary,
                    "report_url": "reports/a-share.html",
                },
                ah_lookup,
            )
        )

    # --- 2. HK-Stock: colors directly in ## 附表二 col 4 ---
    for cells in _parse_app2_rows(hk_md):
        if len(cells) < 5:
            continue
        sector = clean_md_inline_plain(cells[0])
        m_code = re.search(r"`([0-9A-Za-z.]+)`", cells[1])
        raw_code = m_code.group(1) if m_code else ""
        code = f"{raw_code}.HK" if raw_code.isdigit() and len(raw_code) == 5 else raw_code
        name = clean_md_inline_plain(re.sub(r"`[^`]+`", "", cells[1]))
        price = clean_md_inline_plain(cells[2])
        valuation = clean_md_inline_plain(cells[3])
        col = _detect_color(cells[4])
        summary_raw = clean_md_inline_plain(cells[4])
        summary = _LEADING_RATING_PREFIX_RE.sub("", summary_raw).strip()
        stocks.append(
            _enrich_stock_metrics(
                {
                    "market": "hk-stock",
                    "market_label": "港股",
                    "sector": sector,
                    "name": name,
                    "code": code,
                    "price": price,
                    "valuation": valuation,
                    "color": col,
                    "action_label": COLOR_LABELS[col],
                    "summary": summary,
                    "report_url": "reports/hk-stock.html",
                },
                ah_lookup,
            )
        )

    # --- 3. US-Stock: colors directly in ## 附表二 col 3 ---
    for cells in _parse_app2_rows(us_md):
        if len(cells) < 5:
            continue
        sector = clean_md_inline_plain(cells[0])
        m_code = re.search(r"`([A-Z0-9.\-]+)`", cells[1])
        code = m_code.group(1) if m_code else ""
        name = clean_md_inline_plain(re.sub(r"`[^`]+`", "", cells[1]))
        price = clean_md_inline_plain(cells[2])
        col = _detect_color(cells[3])
        val_plain = clean_md_inline_plain(cells[3])
        val_clean = re.sub(r"\s*·\s*[🟢🔵🟡🔴].*$", "", val_plain).strip()
        special_tag = "（黄金红灯禁新买）" if "禁新买" in val_plain else ""
        summary = clean_md_inline_plain(cells[4]) + special_tag
        stocks.append(
            _enrich_stock_metrics(
                {
                    "market": "us-stock",
                    "market_label": "美股",
                    "sector": sector,
                    "name": name,
                    "code": code,
                    "price": price,
                    "valuation": val_clean,
                    "color": col,
                    "action_label": COLOR_LABELS[col],
                    "summary": summary,
                    "report_url": "reports/us-stock.html",
                },
                ah_lookup,
            )
        )

    return stocks


# ==============================================================================
# 4B. DATA COMPLETENESS & CAVEATS TRANSPARENCY DISCLOSURE SYSTEM
# ==============================================================================

_CAVEAT_MARKET_NORM: dict[str, str] = {
    "gold": "gold",
    "a_share": "a-share",
    "a-share": "a-share",
    "hk_stock": "hk-stock",
    "hk-stock": "hk-stock",
    "us_stock": "us-stock",
    "us-stock": "us-stock",
    "cross": "cross",
    "all": "cross",
    "global": "cross",
}

_CAVEAT_MARKET_LABEL: dict[str, str] = {
    "gold": "黄金",
    "a-share": "A股",
    "hk-stock": "港股",
    "us-stock": "美股",
    "cross": "跨市场",
}

_CAVEAT_CATEGORY_LABEL: dict[str, str] = {
    "provisional_close": "暂采官网收盘",
    "delayed_official": "官库待披露",
    "single_source": "单源暂用",
    "source_conflict": "多源口径差异",
    "holiday_thin": "节假日薄量",
    "publication_exception": "编排说明",
}

_CAVEAT_CATEGORY_ALIASES: dict[str, str] = {
    "source_divergence": "source_conflict",
}

_PUB_EXCEPTION_KIND_META: dict[str, tuple[str, str]] = {
    "source_outage": ("官方数据源临时中断 · 沿用已核实基准", "high"),
    "breaking_event": ("重大突发事件加发守望刊", "warn"),
    "revision_reuse": ("本班修订沿用既有已核刊次", "info"),
}

_CAVEAT_SEV_RANK: dict[str, int] = {"critical": 0, "high": 1, "warn": 2, "info": 3}
_CAVEAT_MKT_RANK: dict[str, int] = {"gold": 0, "a-share": 1, "hk-stock": 2, "us-stock": 3, "cross": 4}
_CAVEAT_LABEL_RANK: dict[str, int] = {"黄金": 0, "A股": 1, "港股": 2, "美股": 3, "跨市场": 4}

_HOLIDAY_TYPE_LABEL: dict[str, str] = {
    "partial_holiday": "局部休市",
    "half_day": "半日市",
    "full_holiday_and_rollover": "三市休市",
    "long_holiday_start": "长假休市",
    "rebalance_and_policy": "重大调仓/政策",
    "hk_major_rebalance": "港股季检调仓",
    "policy_deadline": "政策截止日",
    "monthly_rollover": "月度滚存",
    "quad_witching_boj": "衍生品大交割",
    "dst_transition": "夏令时切换",
}

_CAVEAT_SANITIZE_REPS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"file://[^\s<>\"'）)》」]+", re.IGNORECASE), "官方数据源"),
    (re.compile(r"(?:/Users/|(?<![A-Za-z0-9._-])/home/)[^\s<>\"'）)》」`]+", re.IGNORECASE), "站内数据"),
    (re.compile(r"[（(]?\s*`?VIX_History\.csv`?\s*[）)]?", re.IGNORECASE), "官方历史日线表"),
    (re.compile(r"`?data_snapshot\.json`?", re.IGNORECASE), "实时数据快照"),
    (re.compile(r"`?market_state\.json`?", re.IGNORECASE), "三市状态快照"),
    (re.compile(r"`?master_snapshot\.json`?", re.IGNORECASE), "主报告基线快照"),
    (re.compile(r"`?market_calendar\.json`?", re.IGNORECASE), "全球交易日历"),
    (re.compile(r"`?multi_asset_channels\.json`?", re.IGNORECASE), "个人多元渠道快照"),
    (re.compile(r"`?etf_universe\.json`?", re.IGNORECASE), "全球 ETF 雷达快照"),
    (re.compile(r"`?deep_dossiers\.json`?", re.IGNORECASE), "个股 7 维深研档案"),
    (re.compile(r"`?_(?:edition|ledger|rsi|audit|rollover|archive)_patch\.json`?", re.IGNORECASE), "更新补丁"),
    (re.compile(r"`?audit_ledger\.md`?", re.IGNORECASE), "核查台账"),
    (re.compile(r"`?RSI_PLAYBOOK(?:\.md)?`?", re.IGNORECASE), "复盘手册"),
    (re.compile(r"`?rsi_metrics\.json`?", re.IGNORECASE), "复盘指标"),
    (re.compile(r"`?DAILY_FORMAT_SPEC\.md`?", re.IGNORECASE), "日报排版规范"),
    (re.compile(r"`?DAILY_REPORT_SPEC\.md`?", re.IGNORECASE), "日报撰写规范"),
    (re.compile(r"`?unified-edition\.prompt\.md`?", re.IGNORECASE), "统一编排规范"),
    (re.compile(r"`?gold-research-publishing`?", re.IGNORECASE), "黄金研究体系"),
    (re.compile(r"`?(?:AGENTS|SKILL|GEMINI)\.md`?", re.IGNORECASE), "研究规范"),
    (re.compile(r"`?(?:sidecar|permissions)\.json`?", re.IGNORECASE), "运行配置"),
    (re.compile(r"`?(?:patch_state_dbs|svg_geometry)\.py`?", re.IGNORECASE), "核验流程"),
    (re.compile(r"(?<![A-Za-z0-9_/-])[A-Za-z0-9_/-]+\.py(?![A-Za-z0-9_])", re.IGNORECASE), "核验流程"),
    (re.compile(r"(?<![A-Za-z0-9])\d+\s*[-–—]\s*\d+\s*p\s*主刊", re.IGNORECASE), "完整主刊"),
    (re.compile(r"切\s*模式\s*2(?=\s*(?:美股|港股|A\s*股|休市|守望))"), "切换为"),
    (re.compile(r"切\s*模式\s*2"), "切换为休市守望刊"),
)


def _sanitize_caveat_text(text: Any) -> str:
    """Ensure reader-facing caveat text contains zero internal filenames, local paths, or raw Markdown."""
    out = clean_md_inline_plain(str(text or ""))
    for pat, repl in _CAVEAT_SANITIZE_REPS:
        out = pat.sub(repl, out)
    out = re.sub(r"官方历史日线表\s*官方历史日线表", "官方历史日线表", out)
    return re.sub(r"\s+", " ", out).strip()


def _fmt_due_edition(code: Any) -> str:
    s = str(code or "").strip()
    if not s:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(?:_r\d+)?$", s)
    if m:
        hhmm_int = int(m.group(4) + m.group(5))
        slot = "早报" if hhmm_int < 1100 else ("午报" if hhmm_int < 1500 else "晚报")
        return f"计划于 {int(m.group(2))}/{int(m.group(3))} {m.group(4)}:{m.group(5)} {slot}复查"
    m_d = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m_d:
        return f"计划于 {int(m_d.group(2))}/{int(m_d.group(3))} 复查"
    return _sanitize_caveat_text(s)


def _norm_caveat_market(raw: Any, default: str = "cross") -> str:
    key = str(raw or "").strip().lower()
    return _CAVEAT_MARKET_NORM.get(key, default)


def collect_data_caveats(
    gold_snap: dict | None,
    eq_state: dict | None,
    *,
    market: str | None = None,
    extra_caveats: list[dict] | None = None,
) -> list[dict[str, str]]:
    """Collect, normalize, synthesize fallbacks, sanitize, deduplicate, and filter reader-facing caveats."""
    gs = gold_snap if isinstance(gold_snap, dict) else {}
    es = eq_state if isinstance(eq_state, dict) else {}

    raw_items: list[dict[str, str]] = []
    explicit_markets: set[str] = set()

    def _add_raw(
        entry: dict[str, Any],
        default_mkt: str,
        *,
        is_explicit: bool,
    ) -> None:
        mkt = _norm_caveat_market(entry.get("market"), default_mkt)
        sev = str(entry.get("severity") or "info").strip().lower()
        if sev not in _CAVEAT_SEV_RANK:
            sev = "info"
        cat = str(entry.get("category") or "delayed_official").strip().lower()
        cat = _CAVEAT_CATEGORY_ALIASES.get(cat, cat)
        if cat not in _CAVEAT_CATEGORY_LABEL:
            cat = "delayed_official"
        title = _sanitize_caveat_text(entry.get("item") or entry.get("title") or "")
        detail = _sanitize_caveat_text(entry.get("detail") or entry.get("description") or entry.get("note") or "")
        impact = _sanitize_caveat_text(entry.get("impact") or "")
        due_raw = str(entry.get("next_review") or entry.get("due_edition") or entry.get("due_session") or "").strip()
        if not title and detail:
            title, detail = detail[:80], detail
        if not title:
            return
        if is_explicit:
            explicit_markets.add(mkt)
        raw_items.append(
            {
                "id": str(entry.get("id") or "").strip(),
                "market": mkt,
                "market_label": _CAVEAT_MARKET_LABEL.get(mkt, "跨市场"),
                "category": cat,
                "category_label": _CAVEAT_CATEGORY_LABEL[cat],
                "severity": sev,
                "title": title,
                "detail": detail,
                "impact": impact,
                "due_raw": due_raw,
                "due_label": _fmt_due_edition(due_raw),
            }
        )

    for item in gs.get("data_caveats") or []:
        if isinstance(item, dict):
            _add_raw(item, "gold", is_explicit=True)
    for item in es.get("data_caveats") or []:
        if isinstance(item, dict):
            _add_raw(item, "cross", is_explicit=True)
    for item in extra_caveats or []:
        if isinstance(item, dict):
            _add_raw(item, "cross", is_explicit=True)

    # Fallback 1: VIX provisional/pending checks from gold snapshot if no explicit VIX/恐慌 caveat exists
    has_vix_caveat = any(
        "vix" in f"{it['id']} {it['title']} {it['detail']}".lower() or "恐慌" in f"{it['title']} {it['detail']}"
        for it in raw_items
    )
    vix_checks = gs.get("vix_daily_row_checks")
    if not has_vix_caveat and isinstance(vix_checks, dict):
        for dt_key, chk in sorted(vix_checks.items(), reverse=True):
            if not isinstance(chk, dict):
                continue
            st = str(chk.get("status") or "").strip().lower()
            if st in ("provisional_close", "pending"):
                _add_raw(
                    {
                        "id": f"vix_fallback_{dt_key}",
                        "market": "gold",
                        "category": "provisional_close" if st == "provisional_close" else "delayed_official",
                        "severity": "warn",
                        "item": f"美股恐慌指数（VIX）{dt_key} 官方历史日线表待复查",
                        "detail": chk.get("note") or f"{dt_key} 官方历史日线表尚未更新，暂采交易所官网收盘读数。",
                        "impact": "后续班次复查官方历史表。核实后再更新读数与核验状态。",
                    },
                    "gold",
                    is_explicit=False,
                )
                break

    # Fallback 2: pending_backfills for markets lacking explicit caveats
    for pb in es.get("pending_backfills") or []:
        if not isinstance(pb, dict):
            continue
        mkt = _norm_caveat_market(pb.get("market"), "cross")
        if mkt in explicit_markets:
            continue
        _add_raw(
            {
                "market": mkt,
                "category": "delayed_official",
                "severity": "info",
                "item": pb.get("item") or "",
                "detail": "该市场部分官方次级数据尚待收盘或官方数据库披露，计划按所列班次复查。",
                "due_session": pb.get("due_session") or "",
            },
            mkt,
            is_explicit=False,
        )

    # Fallback 3: publication_exceptions (always surface transparently if present)
    pub_exc = es.get("publication_exceptions")
    if isinstance(pub_exc, dict):
        exc_ed_raw = pub_exc.get("edition_id")
        exc_ed = str(exc_ed_raw).strip() if exc_ed_raw is not None else ""
        state_ed = str(es.get("edition_id") or "").strip()
        if not exc_ed or exc_ed == state_ed:
            markets_map = pub_exc.get("markets")
            if isinstance(markets_map, dict):
                for mkt_k, row in markets_map.items():
                    if not isinstance(row, dict):
                        continue
                    kind = str(row.get("kind") or "").strip().lower()
                    default_title, default_sev = _PUB_EXCEPTION_KIND_META.get(
                        kind, ("本期出版编排说明", "warn")
                    )
                    raw_sev = str(row.get("severity") or "").strip().lower()
                    if raw_sev in _CAVEAT_SEV_RANK:
                        sev = raw_sev
                    elif raw_sev == "p0":
                        sev = "high"
                    elif raw_sev == "p1":
                        sev = "warn"
                    else:
                        sev = default_sev
                    _add_raw(
                        {
                            "id": f"pub_exc_{_norm_caveat_market(mkt_k, 'cross')}_{kind or 'note'}",
                            "market": mkt_k,
                            "category": "publication_exception",
                            "severity": sev,
                            "item": row.get("title") or row.get("item") or default_title,
                            "detail": row.get("detail") or row.get("note") or row.get("reason") or "",
                            "impact": row.get("impact") or "",
                            "next_review": (
                                row.get("next_review_session")
                                or row.get("next_review")
                                or row.get("due_session")
                                or ""
                            ),
                        },
                        "cross",
                        is_explicit=False,
                    )
    elif isinstance(pub_exc, list):
        for exc in pub_exc:
            if isinstance(exc, dict):
                _add_raw(
                    {
                        "market": exc.get("market") or "cross",
                        "category": "publication_exception",
                        "severity": exc.get("severity") or "warn",
                        "item": exc.get("title") or exc.get("item") or exc.get("reason") or "本期出版编排说明",
                        "detail": exc.get("detail") or exc.get("note") or exc.get("reason") or "",
                        "impact": exc.get("impact") or "",
                        "next_review": exc.get("next_review") or exc.get("next_review_session") or "",
                    },
                    "cross",
                    is_explicit=False,
                )
            elif isinstance(exc, str) and exc.strip():
                _add_raw(
                    {
                        "market": "cross",
                        "category": "publication_exception",
                        "severity": "warn",
                        "item": "本期出版编排说明",
                        "detail": exc,
                    },
                    "cross",
                    is_explicit=False,
                )

    # Optional market scope filter before cross-market dedup so single-market dailies keep market-specific wording
    if market is not None:
        norm_target = _norm_caveat_market(market, market)
        scoped_items = [it for it in raw_items if it["market"] in (norm_target, "cross")]
    else:
        scoped_items = raw_items

    # Cross-track deduplication: merge identical/near-identical caveats (same id/market, normalized title, or ratio >= 0.82)
    def _norm_caveat_title(title: str) -> str:
        return re.sub(r"[\W_]+", "", str(title or "").lower())

    def _merge_market_labels(lbl_a: str, lbl_b: str) -> str:
        parts: list[str] = []
        for raw_lbl in (lbl_a, lbl_b):
            for seg in str(raw_lbl or "").split("/"):
                s = seg.strip()
                if s and s not in parts:
                    parts.append(s)
        specific = [p for p in parts if p != "跨市场"]
        chosen = specific if specific else parts
        chosen.sort(key=lambda lbl: (_CAVEAT_LABEL_RANK.get(lbl, 9), lbl))
        return " / ".join(chosen) or "跨市场"

    deduped: list[dict[str, str]] = []
    deduped_norms: list[str] = []
    seen_exact_ids: dict[tuple[str, str], int] = {}

    for it in scoped_items:
        norm_title = _norm_caveat_title(it["title"])
        match_idx: int | None = None

        if it["id"]:
            id_key = (it["market"], it["id"].lower())
            if id_key in seen_exact_ids:
                match_idx = seen_exact_ids[id_key]

        if match_idx is None and norm_title:
            for idx, ex_norm in enumerate(deduped_norms):
                if not ex_norm:
                    continue
                if norm_title == ex_norm or SequenceMatcher(None, norm_title, ex_norm).ratio() >= 0.82:
                    match_idx = idx
                    break

        if match_idx is None:
            new_idx = len(deduped)
            deduped.append(it)
            deduped_norms.append(norm_title)
            if it["id"]:
                seen_exact_ids[(it["market"], it["id"].lower())] = new_idx
        else:
            existing = deduped[match_idx]
            existing["market_label"] = _merge_market_labels(existing["market_label"], it["market_label"])
            in_sev_rank = _CAVEAT_SEV_RANK.get(it["severity"], 9)
            ex_sev_rank = _CAVEAT_SEV_RANK.get(existing["severity"], 9)
            if in_sev_rank < ex_sev_rank:
                existing["severity"] = it["severity"]
                existing["category"] = it["category"]
                existing["category_label"] = it["category_label"]
            if len(it["detail"]) > len(existing["detail"]):
                existing["detail"] = it["detail"]
            if len(it["impact"]) > len(existing["impact"]):
                existing["impact"] = it["impact"]
            if len(it["title"]) > len(existing["title"]) and in_sev_rank <= ex_sev_rank:
                existing["title"] = it["title"]
                deduped_norms[match_idx] = norm_title
            if not existing["due_label"] and it["due_label"]:
                existing["due_raw"] = it["due_raw"]
                existing["due_label"] = it["due_label"]
            if _CAVEAT_MKT_RANK.get(it["market"], 9) < _CAVEAT_MKT_RANK.get(existing["market"], 9):
                existing["market"] = it["market"]

    deduped.sort(
        key=lambda it: (
            _CAVEAT_SEV_RANK.get(it["severity"], 9),
            _CAVEAT_MKT_RANK.get(it["market"], 9),
        )
    )
    return deduped


def collect_holiday_alerts(eq_state: dict | None, max_days: int = 7) -> list[dict[str, str]]:
    """Extract upcoming or active calendar_overrides overlapping [as_of_date, as_of_date + max_days]."""
    es = eq_state if isinstance(eq_state, dict) else {}
    as_of_raw = str(es.get("as_of_cst") or "").strip()[:10]
    try:
        base_d = date.fromisoformat(as_of_raw)
    except ValueError:
        return []
    end_d = base_d + timedelta(days=max_days)

    alerts: list[tuple[date, dict[str, str]]] = []
    for ov in es.get("calendar_overrides") or []:
        if not isinstance(ov, dict):
            continue
        ov_type = str(ov.get("type") or "").strip().lower()
        if ov_type == "monthly_rollover":
            continue
        d_raw = str(ov.get("date_cst") or "").strip()[:10]
        try:
            ev_d = date.fromisoformat(d_raw)
        except ValueError:
            continue
        end_raw = str(ov.get("end_date_cst") or "").strip()[:10]
        try:
            ev_end = date.fromisoformat(end_raw) if end_raw else ev_d
        except ValueError:
            ev_end = ev_d
        if ev_end < ev_d:
            ev_end = ev_d
        if not (ev_end >= base_d and ev_d <= end_d):
            continue
        type_lbl = _HOLIDAY_TYPE_LABEL.get(ov_type, "交易日历提示")
        mk_list = [
            _CAVEAT_MARKET_LABEL.get(_norm_caveat_market(m, "cross"), str(m))
            for m in (ov.get("markets_affected") or [])
        ]
        markets_lbl = " / ".join(dict.fromkeys(mk_list)) or "跨市场"
        note = _sanitize_caveat_text(ov.get("note") or "")
        date_lbl = (
            f"{ev_d.month:02d}/{ev_d.day:02d}–{ev_end.month:02d}/{ev_end.day:02d}"
            if ev_end > ev_d
            else f"{ev_d.month:02d}/{ev_d.day:02d}"
        )
        alerts.append(
            (
                ev_d,
                {
                    "date": date_lbl,
                    "type_label": type_lbl,
                    "markets_label": markets_lbl,
                    "note": note,
                },
            )
        )
    alerts.sort(key=lambda pair: pair[0])
    return [item for _, item in alerts]


def _render_caveat_items_html(caveats: list[dict[str, str]], empty_msg: str) -> str:
    if not caveats:
        return (
            '<div class="caveat-item sev-info">'
            '<div class="caveat-title">官源核验齐全</div>'
            f'<div class="caveat-detail">{esc(empty_msg)}</div>'
            "</div>"
        )
    rows: list[str] = []
    for c in caveats:
        due_html = f'<span class="caveat-due">{esc(c["due_label"])}</span>' if c.get("due_label") else ""
        impact_html = (
            f'<div class="caveat-impact"><strong>裁决影响：</strong>{esc(c["impact"])}</div>'
            if c.get("impact")
            else ""
        )
        sev_cls = "high" if c["severity"] in ("critical", "high") else c["severity"]
        rows.append(
            f'<div class="caveat-item sev-{esc(sev_cls)}">'
            f'<div class="caveat-head">'
            f'<span class="caveat-mkt">{esc(c["market_label"])}</span>'
            f'<span class="caveat-cat">{esc(c["category_label"])}</span>'
            f"{due_html}"
            f"</div>"
            f'<div class="caveat-title">{esc(c["title"])}</div>'
            f'<div class="caveat-detail">{esc(c["detail"])}</div>'
            f"{impact_html}"
            f"</div>"
        )
    return "".join(rows)


def render_cockpit_disclosure(caveats: list[dict[str, str]], holidays: list[dict[str, str]]) -> str:
    """Render homepage Data Completeness & Possible Omissions collapsible transparency bar."""
    has_high = any(c.get("severity") in ("critical", "high") for c in caveats)
    open_attr = " open" if has_high else ""
    if has_high:
        badge_cls = "badge-high"
    elif caveats:
        badge_cls = "badge-warn"
    else:
        badge_cls = "badge-ok"
    if caveats:
        badge_txt = f"本期挂账 {len(caveats)} 项"
        if holidays:
            badge_txt += f" · 近7日异动 {len(holidays)} 项"
    elif holidays:
        badge_txt = f"官源齐全 · 近7日异动 {len(holidays)} 项"
    else:
        badge_txt = "本期官源齐全 · 0 挂账"

    items_html = _render_caveat_items_html(
        caveats,
        "本期四市场核心官方数据源均已按时披露并完成交叉核验，无暂用或待补挂账项。",
    )
    holiday_html = ""
    if holidays:
        h_rows = "".join(
            f'<div class="holiday-item">'
            f'<span class="holiday-date">{esc(h["date"])} · {esc(h["markets_label"])} · {esc(h["type_label"])}</span>'
            f'<span class="holiday-note">{esc(h["note"])}</span>'
            f"</div>"
            for h in holidays
        )
        holiday_html = (
            '<div class="holiday-strip">'
            '<div class="holiday-strip-title">近 7 日休市与重大调仓窗口</div>'
            f"{h_rows}"
            "</div>"
        )

    info_svg = (
        '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="10" cy="10" r="8"/><path d="M10 6.2v4.3M10 13.6h.01"/></svg>'
    )
    chev_svg = (
        '<svg class="disclosure-chev" viewBox="0 0 16 16" width="12" height="12" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M4 6l4 4 4-4"/></svg>'
    )
    return (
        f'<details class="disclosure-bar"{open_attr}>'
        '<summary class="disclosure-summary">'
        '<div class="disclosure-summary-main">'
        f'<span class="disclosure-icon" aria-hidden="true">{info_svg}</span>'
        '<div class="disclosure-heading">'
        '<span class="disclosure-title">数据完整性与可能遗漏说明</span>'
        '<span class="disclosure-sub">每日计划在 07:30、11:30、18:00 启动。尚未披露或暂采官网收盘的数据均列明</span>'
        "</div></div>"
        '<div class="disclosure-summary-meta">'
        f'<span class="disclosure-badge {badge_cls}">{esc(badge_txt)}</span>'
        f'<span class="disclosure-toggle-lbl">展开明细 {chev_svg}</span>'
        "</div>"
        "</summary>"
        '<div class="disclosure-body">'
        f'<div class="disclosure-list-col">{items_html}</div>'
        '<div class="disclosure-policy-col">'
        '<div class="disclosure-policy-title">发刊与后续复查</div>'
        '<ul class="disclosure-policy-list">'
        "<li><strong>宁缺毋滥</strong>：未到官库披露时点的次级数据一律留空或沿用最近已核实官收并标注原日期，绝不估算填数。</li>"
        "<li><strong>暂用明示</strong>：跨时区官方历史表尚未更新时，可暂采交易所官网收盘价。在所列班次复查，核实后再更新。</li>"
        "<li><strong>留痕可查</strong>：任何后续官源修订均同步记入公开演进与核查账本，永不事后涂改旧账。</li>"
        "</ul>"
        '<div class="disclosure-policy-links">'
        '<a class="btn btn-sm" href="scorecard.html#gold-audit-log">黄金核查账本 →</a>'
        '<a class="btn btn-sm" href="scorecard.html#equity-changelog">股市观点演进 →</a>'
        "</div>"
        f"{holiday_html}"
        "</div></div></details>"
    )


def render_daily_disclosure(
    caveats: list[dict[str, str]],
    market: str,
    is_latest: bool,
    date_str: str,
    session_label: str,
) -> str:
    """Render scoped inline disclosure bar below cover banner on daily report pages."""
    info_svg = (
        '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="10" cy="10" r="8"/><path d="M10 6.2v4.3M10 13.6h.01"/></svg>'
    )
    chev_svg = (
        '<svg class="disclosure-chev" viewBox="0 0 16 16" width="12" height="12" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M4 6l4 4 4-4"/></svg>'
    )
    if is_latest:
        has_high = any(c.get("severity") in ("critical", "high") for c in caveats)
        badge_cls = "badge-high" if has_high else ("badge-warn" if caveats else "badge-ok")
        badge_txt = f"本市挂账 {len(caveats)} 项" if caveats else "本市官源齐全"
        sum_title = "本刊数据完整性与待核挂账说明"
        ledger_href = "../scorecard.html#gold-audit-log" if market == "gold" else "../scorecard.html#equity-changelog"
        body_inner = (
            _render_caveat_items_html(
                caveats,
                "本市场本期核心官方数据均已核实入账，无待补或暂用挂账项。",
            )
            + '<div class="disclosure-policy-links">'
            + f'<a class="btn btn-sm" href="{ledger_href}">查阅公开核查与演进账本 →</a>'
            + "</div>"
        )
    else:
        badge_cls = "badge-ok"
        badge_txt = "历史原刊留痕"
        sum_title = f"历史档案口径说明（{date_str} {session_label}）"
        body_inner = (
            '<div class="caveat-item sev-info">'
            '<div class="caveat-title">历史原刊如实归档，绝不事后改写</div>'
            f'<div class="caveat-detail">本页完整保留 {esc(date_str)} {esc(session_label)} 发刊时的真实官方观测口径与当时挂账状态。最新实盘锚与后续挂账核销请前往查阅本期最新日报或公开记分卡。</div>'
            "</div>"
            '<div class="disclosure-policy-links">'
            f'<a class="btn btn-sm" href="{esc(market)}-latest.html">查看本期最新日报 →</a>'
            '<a class="btn btn-sm" href="../scorecard.html">公开记分卡与演进 →</a>'
            "</div>"
        )
    return (
        '<details class="disclosure-inline no-print">'
        '<summary class="disclosure-inline-sum">'
        '<div class="disclosure-summary-main">'
        f'<span class="disclosure-icon" aria-hidden="true">{info_svg}</span>'
        f'<span class="disclosure-title">{esc(sum_title)}</span>'
        "</div>"
        '<div class="disclosure-summary-meta">'
        f'<span class="disclosure-badge {badge_cls}">{esc(badge_txt)}</span>'
        f'<span class="disclosure-toggle-lbl">详情 {chev_svg}</span>'
        "</div>"
        "</summary>"
        f'<div class="disclosure-inline-body">{body_inner}</div>'
        "</details>"
    )


# ==============================================================================
# 5. SHARED HTML PAGE SHELL (Sticky Nav, Theme Boot, Progress, TOC, Modals)
# ==============================================================================

THEME_INIT_SCRIPT = (
    "<script>(function(){try{"
    "var t=localStorage.getItem('gir_theme');"
    "if(!t){t=window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';}"
    "document.documentElement.setAttribute('data-theme',t);"
    "var m=document.querySelector('meta[name=\"theme-color\"]');"
    "if(m){m.setAttribute('content',t==='dark'?'#0f131a':'#f6f3ec');}"
    "var rs=parseFloat(localStorage.getItem('gir_read_scale')||'');"
    "if(isFinite(rs)&&rs>=0.88&&rs<=1.24){document.documentElement.style.setProperty('--read-scale',rs.toFixed(2));}"
    "}catch(e){}})();</script>"
)

# Shared Top-48 beginner-friendly glossary (rendered statically on guide.html & synced with app.js tooltip)
GLOSSARY_TERMS: tuple[dict[str, str], ...] = (
    {
        "key": "four_buckets",
        "term": "四笔钱规划（活钱 / 稳钱 / 长钱 / 保障）",
        "cat": "基础入门",
        "plain": "按「什么时候要用这笔钱」把积蓄分成四份：0–6 个月活钱、1–3 年稳钱、3–5 年以上长钱，外加先兜底的基础保障。",
        "avoid": "避坑提醒：最常见的亏损不是买错产品，而是把半年内要用的房租或首付拿去买股票（短钱长投）。",
    },
    {
        "key": "traffic_light",
        "term": "红绿灯信号（红灯停 / 黄灯 / 绿灯）",
        "cat": "基础入门",
        "plain": "红绿灯不是预测明天涨跌，而是仓位安全阀：绿灯代表赔率划算可分批，黄灯代表拉锯观望，红灯停代表风险收益比偏弱。",
        "avoid": "避坑提醒：红灯停绝不等于恐慌清仓，而是老底仓稳拿不乱卖、新钱先放稳钱池暂不追高或暂不新买。",
    },
    {
        "key": "dfii10",
        "term": "10 年美债真实利率（DFII10）",
        "cat": "大盘信号",
        "plain": "扣除美国未来通胀预期后，买 10 年期美国国债能拿到手的「真实利息」。黄金不生息，因此真实利率越高，黄金承压越重。",
        "avoid": "避坑提醒：只要真实利率仍高悬在过关线之上，就别凭感觉猜底抢跑新买黄金。",
    },
    {
        "key": "erp",
        "term": "股权风险溢价（ERP）",
        "cat": "大盘信号",
        "plain": "买一篮子股票的盈利收益率减去无风险国债利率的差值，可以理解为「冒风险买股票比买国债多拿的性价比补贴」，数值越高越划算。",
        "avoid": "避坑提醒：高 ERP 代表长期赔率好，但不代表明天立刻大涨，仍需配合趋势与仓位上限分批进场。",
    },
    {
        "key": "hibor",
        "term": "香港银行同业拆息（HIBOR）",
        "cat": "大盘信号",
        "plain": "香港各家银行之间互相借港元的批发利率。它走高说明香港资金变紧、股票估值承压；走低说明市场流动性偏宽松。",
        "avoid": "避坑提醒：关注港股时要同时看 HIBOR 和美元兑港元汇率是否逼近 7.85 弱方保证线。",
    },
    {
        "key": "hkma_bal",
        "term": "香港金管局总结余",
        "cat": "大盘信号",
        "plain": "香港银行体系放在金管局账户里的「港元总水池」。水位越浅，一旦外部抽水，港元利率越容易突然跳涨。",
        "avoid": "避坑提醒：当总结余逼近低水位警戒线时，港股高估值板块容易放大波动，不宜加杠杆。",
    },
    {
        "key": "vix",
        "term": "美股恐慌指数（VIX）",
        "cat": "大盘信号",
        "plain": "由标普 500 期权价格算出来的市场「紧张度温度计」。20 以下偏平静，超过 30 说明全球资金正剧烈避险。",
        "avoid": "避坑提醒：VIX 急飙突破 30 时各类资产容易一起被抛售变现，切忌在高波动盘中盲目重仓抄底。",
    },
    {
        "key": "us10y",
        "term": "10 年期美债收益率（US10Y）",
        "cat": "大盘信号",
        "plain": "全球资产定价的「无风险锚」。它飙升会直接抬高全球借贷成本，压制高估值科技股和新兴市场资产。",
        "avoid": "避坑提醒：若 10 年美债持续高企甚至触发熔断线，科技成长股新增仓位应保持克制。",
    },
    {
        "key": "ah_premium",
        "term": "A/H 溢价与倒挂",
        "cat": "大盘信号",
        "plain": "同一家公司在 A 股和港股同时上市时的价格差。正值代表 A 股比港股贵；负值（倒挂）代表 A 股反而比港股便宜。",
        "avoid": "避坑提醒：别只看表面便宜就换港股，用内地港股通买标准 H 股分红扣 20% 红利税（个别发行人的源头代扣须查当期分派公告），务必算税后净股息。",
    },
    {
        "key": "etf_vs_feeder",
        "term": "场内 ETF vs 场外联接基金",
        "cat": "基金与ETF",
        "plain": "场内 ETF 在券商 App 像股票一样实时交易、费率极低；场外联接在支付宝或银行按收盘净值申购，无需股票账户且绝不买到场内溢价。",
        "avoid": "避坑提醒：跨境美股 ETF 场内抢购溢价高时，优先用场外联接按净值分批定投，别在场内当高溢价接盘侠。",
    },
    {
        "key": "class_a_c",
        "term": "基金 A 类 vs C 类（+7 天惩罚费）",
        "cat": "基金与ETF",
        "plain": "A 类在买入时一次性交申购费，适合长期持有；C 类不收申购费但按天扣销售服务费，适合短期波段。",
        "avoid": "避坑提醒：无论 A 类还是 C 类，持有不满 7 天卖出通常都要硬扣 1.5% 惩罚性赎回费，短钱别乱进出。",
    },
    {
        "key": "premium_discount",
        "term": "场内折价与溢价（参考净值 IOPV）",
        "cat": "基金与ETF",
        "plain": "基金真实价值叫参考净值（IOPV），场内买价高于真实价值就是溢价——相当于值 100 元的东西大家抢到 120 元卖给你。",
        "avoid": "避坑提醒：跨境 QDII 或商品场内溢价超过 2%–3% 坚决不追高，情绪退潮后多花的那部分溢价会直接蒸发。",
    },
    {
        "key": "duration",
        "term": "债券久期（Duration）",
        "cat": "债券与固收",
        "plain": "衡量债券对利率变化有多敏感的「暴脾气系数」。久期 1 年以下像平稳直线，30 年国债久期近 20 年，利率微涨就能跌 5% 以上。",
        "avoid": "避坑提醒：千万别把 30 年超长国债 ETF 当成保本稳健存款重仓，它属于高波动波段与对冲工具。",
    },
    {
        "key": "nav_break",
        "term": "银行理财破净与真净值化",
        "cat": "债券与固收",
        "plain": "资管新规后银行理财不再保本，每天按底层债券和股票市价算净值；「破净」就是净值跌破 1 元本金线。",
        "avoid": "避坑提醒：业绩比较基准不是保本承诺。比较储蓄国债的提前兑取规则，以及同一存款人在同一家投保机构的被保险存款本息合计 50 万元偿付上限。",
    },
    {
        "key": "t0_t1",
        "term": "T+0 / T+1 与「可用 / 可取」",
        "cat": "基础入门",
        "plain": "T+0 当天买当天能卖（债券/跨境/转债/商品 ETF）；T+1 次交易日才能卖（A 股普通股与 A 股股票 ETF）。资金「可用」指能买证券，「可取」指能提现回银行卡。",
        "avoid": "避坑提醒：做国债逆回购务必点「卖出（借钱）」；周四借 1 天期吃 3 天息，周五借 1 天期周末白闲置，且到期次日才可提现。",
    },
    {
        "key": "deposit_insurance",
        "term": "50 万元存款保险与单法人上限",
        "cat": "债券与固收",
        "plain": "同一存款人在同一家独立法人银行的所有普通存款和大额存单，本金加利息合计 50 万元以内由存款保险全额保障。",
        "avoid": "避坑提醒：同一家银行的不同支行合并计算，实操单行控制在 45–47 万以内留出利息缓冲；理财、基金和保险不在存保范围内。",
    },
    {
        "key": "dividend_tax",
        "term": "红利税与通道税费差异",
        "cat": "税费与跨境",
        "plain": "A 股持股超 1 年免红利税；港股通收标准 H 股息直扣 20%（非 H 股的源头代扣须另查当期分派公告）；个人直买交易所公司债付息扣 20%，交易所公司债/科创债 ETF（551500/159600）底层债券付息环节仍扣 20% 税（区别于银行间短融 ETF 511360 等银行间标的）。",
        "avoid": "避坑提醒：买港股高股息前先按税后折算真实到手率，买交易所信用债 ETF 勿误当作免税债基；境外账户投资收益须依法履行年度全球纳税申报义务。",
    },
    {
        "key": "mrf_hedged",
        "term": "香港互认基金（MRF）对冲累计份额",
        "cat": "税费与跨境",
        "plain": "经两地监管批准在内地合法销售的香港公募基金。「人民币对冲」用于锁住汇率波动，「累计份额」把利息滚入净值。",
        "avoid": "避坑提醒：MRF 现金派息强制代扣 20% 个税，买卖价差暂免个税，认准「对冲 + 累计」份额，并核实未暂停申购。",
    },
    {
        "key": "lof_delist",
        "term": "QDII / 商品 LOF 退市回归净值",
        "cat": "税费与跨境",
        "plain": "部分场内跨境和商品 LOF 按交易所新规面临限期终止上市，退市转场外后只能按真实净值赎回。",
        "avoid": "避坑提醒：高溢价买进此类 LOF，一旦退市回归净值，多付的溢价将永久清零，切勿在两位数溢价时进场。",
    },
    {
        "key": "cb_call",
        "term": "可转债强赎与「Z 标识」",
        "cat": "债券与固收",
        "plain": "正股大涨触发条款后，公司有权按约 100.5 元强行买回转债。临近强赎或到期停牌最后阶段，行情软件会亮出「Z」警示标识。",
        "avoid": "避坑提醒：忘记卖出或转股会被低价强赎瞬间亏掉 25%–50%；而已到期停牌的转债切忌误点转股。新手可优先选投资级转债 ETF 自动分散排雷。",
    },
    {
        "key": "reits_irr",
        "term": "公募 REITs 分派率 vs 中债真实 IRR",
        "cat": "债券与固收",
        "plain": "产权类 REITs（保租房/商场）像买房收租看分派率与出租率；特许经营权类（高速/能源）到期资产无偿移交，高分派里混有本金归还。",
        "avoid": "避坑提醒：绝不能把高速 REITs 8%–12% 的表面分派率当成高股息，必须核对中债真实内部收益率（IRR）与薄量限价挂单。",
    },
    {
        "key": "dxy",
        "term": "美元指数（DXY）",
        "cat": "大盘信号",
        "plain": "衡量美元相对欧元、日元、英镑等一篮子主要货币综合强弱的标尺。美元走强往往意味着全球流动性偏紧，压制黄金与非美股市；走弱则利于非美资产回暖。",
        "avoid": "避坑提醒：美元指数偏强或汇兑价差较大时，切忌冲动新换汇做外币定存或重仓未锁汇的境外资产，务必把汇率波动算进总收益。",
    },
    {
        "key": "cot",
        "term": "期货大资金持仓报告（COT）",
        "cat": "大盘信号",
        "plain": "美国商品期货交易委员会（CFTC）每周公布的机构与投机资金持仓明细，可用来观察黄金、原油和美债期货里的多空拥挤程度。",
        "avoid": "避坑提醒：当投机多头净持仓极端拥挤时，哪怕基本面未变也很容易因获利回吐触发急跌，切忌在极端拥挤区追高。",
    },
    {
        "key": "cds",
        "term": "债务违约保险费率（CDS）",
        "cat": "债券与固收",
        "plain": "给公司债或主权债买的「违约保险」年保费（通常按基点计）。费率越低说明市场认为还本付息越稳，飙升则预示信用违约风险快速升温。",
        "avoid": "避坑提醒：当某发行主体或行业的信用违约保险费率急剧跳升时，切忌只盯着高票面利率去接盘高收益债或弱资质可转债。",
    },
    {
        "key": "w8ben",
        "term": "非美居民税务表（W-8BEN）",
        "cat": "税费与跨境",
        "plain": "中国大陆等非美国税务居民在合规离岸券商开户时签署的税务身份声明表，用于享受中美税收协定优惠，把美股股息预扣税从 30% 降至 10%。",
        "avoid": "避坑提醒：W-8BEN 通常有效至签署年后的第三个日历年末，个人情况改变时应更新。美股直投还须按美国所在地资产和适用赠与合计核对非美国公民、非美国住所者的 6 万美元遗产税申报门槛。",
    },
    {
        "key": "crs",
        "term": "金融账户涉税信息自动交换（CRS）",
        "cat": "税费与跨境",
        "plain": "全球百余个税务管辖区（含中国大陆、香港、新加坡、英国等）之间自动交换非居民金融账户余额、股息与处置收益信息的国际透明机制。",
        "avoid": "避坑提醒：离岸账户早已进入全球税务透明时代，中国税务居民个人境外投资收益须按 20% 依法自行年度汇算申报，切勿听信「离岸免查」误导。",
    },
    {
        "key": "low_water",
        "term": "港股期指低水（贴水）",
        "cat": "大盘信号",
        "plain": "香港市场把期货价格低于现货指数叫做「低水」（A 股称贴水）。除息旺季分红扣点或避险对冲盘偏重时，恒指期货往往呈现明显低水。",
        "avoid": "避坑提醒：看到期指大幅低水先区分是成分股集中除息扣点，还是机构集中做空避险，切忌仅凭盘前低水情绪化杀跌或盲目抄底。",
    },
    {
        "key": "high_water",
        "term": "港股期指高水（升水）",
        "cat": "大盘信号",
        "plain": "香港市场把期货价格高于现货指数叫做「高水」（A 股称升水），通常反映市场做多情绪偏热、资金愿意加价提前锁筹或预期后续上行。",
        "avoid": "避坑提醒：盘中情绪躁动拉出大幅高水后极易出现冲高回落，切忌在期指极端高水时追高进场。",
    },
    {
        "key": "ex_div",
        "term": "除净（除权除息）",
        "cat": "基础入门",
        "plain": "港股把上市公司分红或送股后、股价按派息金额等额下调的交易日称为「除净日」。除净当天买入不再享有本次分红，参考价会直接扣除每股派息额。",
        "avoid": "避坑提醒：高额特别息或年度分红除净当日，软件显示的参考价低开并非暴跌打折，切勿把除净扣价误当抄底良机；内地港股通持仓收标准 H 股息须扣 20% 红利税（非 H 股的源头代扣须查当期分派公告）。",
    },
    {
        "key": "discount_ex_div",
        "term": "贴权（除净后走弱）",
        "cat": "基础入门",
        "plain": "股票除权除息后，股价不仅没有涨回除息前的价格（填权），反而继续下跌，导致「赚了股息却亏了本金价差」的现象。",
        "avoid": "避坑提醒：切忌在除净前一天冲着高股息去短线抢权分红，不仅容易遭遇除净后贴权亏损，还要白白缴纳红利税（A 股持股不满 1 个月补扣 20%）。",
    },
    {
        "key": "margin_hk",
        "term": "孖展（港股保证金融资）",
        "cat": "税费与跨境",
        "plain": "香港券商对「保证金融资借钱买股或打新」（英文 Margin 粤语音译）的统称，相当于把已有股票抵押给券商借钱加杠杆。",
        "avoid": "避坑提醒：高波动市况下用孖展加杠杆，一旦股价跌破维持保证金比例会被券商强制平仓（斩仓）且利息高昂，普通投资者严禁借钱或开孖展买股打新。",
    },
    {
        "key": "official_settle",
        "term": "官结（期货官方结算价）",
        "cat": "基础入门",
        "plain": "交易所每日收市后按加权成交或收盘区间正式公布的官方结算基准价（有别于最后 1 秒撮合收盘价），用于期货盯市保证金清算与次日涨跌停基准。",
        "avoid": "避坑提醒：核对原油、黄金、国债与股指期货涨跌幅时，务必分清「官方结算价」与「实时最新成交价」，避免误把跨口径差额当成大涨大跌。",
    },
    {
        "key": "basis_spread",
        "term": "平水 / 升水 / 贴水",
        "cat": "大盘信号",
        "plain": "衡量期货价与现货价差别的标尺：期货高于现货叫「升水」，低于现货叫「贴水」，两者几乎相等叫「平水」。",
        "avoid": "避坑提醒：商品期货长期大幅升水（如原油常见结构）在每次换月时都会持续磨损净值，切勿把带高升水磨损的品种当成长线躺赢标的。",
    },
    {
        "key": "bps",
        "term": "基点（bp / bps）",
        "cat": "基础入门",
        "plain": "金融市场计量利率与利差微小变动的最小常用单位：1 个基点 = 0.01%，100 个基点 = 1 个百分点（1%）。",
        "avoid": "避坑提醒：别小看「几十个基点」——对 30 年超长国债而言，收益率上行 25 个基点就足以带来约 4%–5% 的债券价格回撤。",
    },
    {
        "key": "limit_order",
        "term": "限价单（防滑点挂单）",
        "cat": "基础入门",
        "plain": "下单时自己写死最高买入价或最低卖出价，只有市场成交价满足你设定的价格才成交，绝不按盘口高价盲扫。",
        "avoid": "避坑提醒：买公募 REITs、冷门债券 ETF 或港股薄量中小盘时严禁市价一键扫单，否则瞬间吃掉 1%–3% 买卖价差滑点。",
    },
    {
        "key": "discount_placement",
        "term": "折价配售（港股闪电配股）",
        "cat": "大盘信号",
        "plain": "港股上市公司向机构投资者以低于前一日市价（常见折价 5%–10%）发行新股快速募资，类似「打折批发增发」，短线常带来抛压与摊薄效应。",
        "avoid": "避坑提醒：盘前突现大额折价配售公告时，切勿急着按前日高价追买或盲目接飞刀，应先等股价在配售价附近充分消化抛压并企稳后再评估。",
    },
    {
        "key": "cbbc_zone",
        "term": "牛熊证重货区",
        "cat": "大盘信号",
        "plain": "香港衍生品市场中大量散户牛证或熊证集中扎堆的强制收回价格区间。大盘逼近该区间时，做市商对冲盘容易引发短线急杀或急拉（俗称「屠牛/屠熊」）。",
        "avoid": "避坑提醒：普通投资者严禁直接买带强制收回机制的港股牛熊证；看盘时仅把它当短线波动预警信号，不在急杀扫损瞬间情绪化操作。",
    },
    {
        "key": "hkd_weak_peg",
        "term": "联汇弱方保证（7.85 港元）",
        "cat": "大盘信号",
        "plain": "香港联系汇率制规定美元兑港元汇率波动区间为 7.75–7.85；一旦触及 7.85 弱方兑换保证线，金管局须被动买入港元回收流动性，令总结余下降、拆息跳涨。",
        "avoid": "避坑提醒：美元兑港元贴近 7.85 且金管局总结余逼近低水位时，港股高估值成长股往往承压加大，切忌逆势加杠杆。",
    },
    {
        "key": "closing_auction",
        "term": "收市竞价（港股 U 盘）",
        "cat": "基础入门",
        "plain": "港股 16:00–16:10 的收市竞价时段（俗称 U 盘），专门承接指数基金调仓、北水尾盘成交与机构大宗定价，最后在 16:08–16:10 随机收市。",
        "avoid": "避坑提醒：指数季检调仓日（如 MSCI/恒指生效日）尾盘竞价常现放量异动与瞬间跳价，普通散户无须在 U 盘跟风挂市价单凑热闹。",
    },
    {
        "key": "margin_ratio",
        "term": "两融与降保（融资保证金比例）",
        "cat": "大盘信号",
        "plain": "「两融」指券商向投资者借钱买股（融资）或借股卖出（融券）；监管下调融资保证金比例（「降保」）可放大杠杆上限，但高企的两融余额也意味着市场筹码更脆弱。",
        "avoid": "避坑提醒：两融余额高位且行情急跌时极易触发连锁平仓踩踏；普通投资者坚决坚持全额自有资金投资，严禁开通融资加杠杆。",
    },
    {
        "key": "pboc_omo",
        "term": "央行逆回购（OMO 流动性操作）",
        "cat": "债券与固收",
        "plain": "中国人民银行每天上午 09:20 通过公开市场操作（OMO）向银行体系投放短期流动性的工具（与个人在券商借钱的国债逆回购方向相反），净投放代表补水、净回笼代表抽水。",
        "avoid": "避坑提醒：月末、季末与税期紧盯央行净投放节奏，若资金面阶段性收敛，短端逆回购收益走高但股市短线波动也会放大。",
    },
    {
        "key": "ann_basis",
        "term": "年化贴水与期指基差",
        "cat": "大盘信号",
        "plain": "把股指期货（如中证 500/1000 期货 IC/IM）低于现货指数的贴水幅度折算成年化百分比。贴水越深，说明机构对冲抛压或悲观预期越浓。",
        "avoid": "避坑提醒：贴水扩大时用「贴水负号」读懂真实方向（负基差 = 贴水），切忌把深度贴水误读成升水看多信号。",
    },
    {
        "key": "top20_short",
        "term": "前 20 席位净空（期指机构持仓）",
        "cat": "大盘信号",
        "plain": "中金所每日收盘后公布的前 20 家期货公司会员多单与空单净差额，常用来追踪量化对冲与大型机构在股指期货上的套保力度变化。",
        "avoid": "避坑提醒：前 20 席位长期净空很大程度来自量化中性基金的现货套保，不能孤立当作单边看空信号，应重点看单日增减幅度与基差联动。",
    },
    {
        "key": "ins_research_rate",
        "term": "保险预定利率研究值",
        "cat": "债券与固收",
        "plain": "中国保险行业协会按季度结合 5 年期以上 LPR、国债收益率与定存利率发布的行业基准参考值，用于动态约束新发传统险、分红险与万能险的预定利率上限。",
        "avoid": "避坑提醒：切勿被营销员「最后一天炒停售」话术逼单；买储蓄险先核对合同保证现价 IRR，确认是 10 年以上绝对不用的闲钱再决策。",
    },
    {
        "key": "cornerstone_mech_b",
        "term": "港股基石投资者与回拨机制 B",
        "cat": "税费与跨境",
        "plain": "港股新股发行中，提前锁定 6 个月禁售期的大机构叫「基石投资者」；「机制 B」是 2025 年港交所新规下取消强制大幅回拨散户的分配模式，使机构筹码更集中、首日流通盘偏薄。",
        "avoid": "避坑提醒：机制 B 新股首日易被资金炒高、6 个月基石解禁期抛压集中，普通人打新切忌借孖展重押，上市后也不宜高估值盲目追炒。",
    },
    {
        "key": "creditwatch",
        "term": "信用观察（CreditWatch / 负面观察）",
        "cat": "债券与固收",
        "plain": "标普、穆迪、惠誉等权威评级机构把某公司或主权主体列入短期重点复核名单（通常 90 天内定夺），「负面信用观察」代表降级风险显著升温。",
        "avoid": "避坑提醒：重仓高负债公司或可转债前务必核查近 24 小时评级观察公告，一旦被纳入负面观察，债务再融资成本跃升常先于股价暴雷。",
    },
    {
        "key": "redemption_gate",
        "term": "赎回闸门（私募 / 半开放基金限赎）",
        "cat": "税费与跨境",
        "plain": "部分私募、海外私募信贷或半开放基金在单季/单月净赎回超过约定比例（如 5%）时启动的暂停或按比例限制赎回条款。",
        "avoid": "避坑提醒：高息宣传的私募信贷或非标类产品在市场恐慌时最易触发赎回闸门导致「看得见净值却取不出钱」，切勿拿短期周转钱去碰限赎产品。",
    },
    {
        "key": "equal_weight",
        "term": "等权指数（如标普 500 等权 RSP）",
        "cat": "基金与ETF",
        "plain": "给指数里每家成分股分配完全相同权重（例如 500 家各占 0.2%），而不按市值大小倾斜，用来分散少数超大科技巨头集中度过高的风险。",
        "avoid": "避坑提醒：当市场宽度极端收窄、前十大科技股占市值比重过高时，可用等权指数对照观察真实市场健康度，但也要留意其换手率与费率略高于市值加权宽基。",
    },
)


def _term_tip(term_key: str, label: str) -> str:
    """Render an accessible inline glossary button handled by app.js zero-dep tooltip."""
    return (
        f'<button type="button" class="term-tip" data-term="{esc(term_key)}" '
        f'aria-label="查看术语白话解释：{esc(label)}">'
        f'{esc(label)}<span class="term-q" aria-hidden="true">?</span></button>'
    )


# Automated first-occurrence glossary injector covering all 48 GLOSSARY_DICT keys.
_GLOSSARY_SKIP_TAGS: frozenset[str] = frozenset(
    {"svg", "a", "button", "h1", "h2", "h3", "h4", "code", "pre", "script", "style", "summary", "title", "option", "textarea"}
)
_GLOSSARY_VOID_TAGS: frozenset[str] = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)
_GLOSSARY_SKIP_CLASSES: frozenset[str] = frozenset(
    {
        "ch-badge",
        "ch-pill",
        "ch-status",
        "ch-bucket-pill",
        "ch-hnw-badge",
        "ch-num",
        "ch-kpi",
        "ch-kpi-lbl",
        "ch-kpi-val",
        "ch-detail-hero",
        "channels-mutex",
        "etf-lock-banner",
        "lamp-pill",
        "meta-pill",
        "live-pill",
        "compact-alert-pill",
        "stance-pill",
        "cover-tag",
        "cover-kpi",
        "cover-banner",
        "exec-masthead",
        "kpi-card",
        "kpi-grid",
        "status-chip",
        "prem-pill",
        "role-pill",
        "etf-chan-tag",
        "etf-ortho-tag",
        "code-tag",
        "mkt-badge",
        "session-pill",
        "ed-pill",
        "pcal-tier-pill",
        "pcal-region-tag",
        "pcal-countdown",
        "doc-meta-pills",
        "breadcrumb",
    }
)
_GLOSSARY_CLASS_ATTR_RE = re.compile(r'\bclass\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', flags=re.IGNORECASE)
_GLOSSARY_RAW_BLOCKS_RE = re.compile(
    r"(<(?:svg|script|style)\b[^>]*>.*?</(?:svg|script|style)>)",
    flags=re.DOTALL | re.IGNORECASE,
)
_GLOSSARY_TOKEN_RE = re.compile(r"(<!--.*?-->|<[^>]+>)", flags=re.DOTALL)
_GLOSSARY_TAG_NAME_RE = re.compile(r"^<\s*(/)?\s*([A-Za-z][A-Za-z0-9:-]*)\b")
_GLOSSARY_EXISTING_KEY_RE = re.compile(r'data-term="([a-z0-9_]+)"')
_GLOSSARY_PHRASE_SPECS: tuple[tuple[str, str], ...] = (
    ("four_buckets", r"四笔钱规划|四笔钱"),
    ("traffic_light", r"买金四步红绿灯|四步买金红绿灯|红绿灯信号|红绿灯"),
    ("dfii10", r"10\s*年(?:期)?美债真实利率|(?<![A-Za-z0-9])DFII10(?![A-Za-z0-9])"),
    ("erp", r"股权风险溢价|\bERP\b"),
    ("hibor", r"香港银行同业拆息|\bHIBOR\b"),
    ("hkma_bal", r"香港金管局总结余|金管局总结余|银行体系总结余"),
    ("vix", r"美股恐慌指数|\bVIX\b"),
    ("us10y", r"10\s*年(?:期)?美债收益率|\bUS10Y\b"),
    ("ah_premium", r"A/H\s*溢价|AH\s*溢价|A/H\s*倒挂|AH\s*倒挂"),
    ("etf_vs_feeder", r"场外联接基金|场外联接"),
    ("class_a_c", r"A\s*类\s*(?:vs|与|和|/)\s*C\s*类|A/C\s*类|销售服务费|惩罚性赎回费"),
    ("premium_discount", r"参考净值（IOPV）|参考净值|\bIOPV\b|场内折溢价|场内溢价"),
    ("duration", r"债券久期|超长久期|久期"),
    ("nav_break", r"真净值化|阶段性破净|破净"),
    ("t0_t1", r"(?<![A-Za-z0-9])T\+0\s*/\s*T\+1(?![A-Za-z0-9])|(?<![A-Za-z0-9])T\+0(?![A-Za-z0-9])|(?<![A-Za-z0-9])T\+1(?![A-Za-z0-9])"),
    ("deposit_insurance", r"50\s*万元?存款保险|存款保险条例|存款保险|存保上限|存保红线|存保线"),
    ("dividend_tax", r"港股通红利税|红利税"),
    ("mrf_hedged", r"香港北向互认基金|香港互认基金|\bMRF\b"),
    ("lof_delist", r"商品\s*LOF|退市回归净值|LOF\s*退市"),
    ("cb_call", r"可转债强赎|强赎条款|「Z」标识|Z\s*标识|强赎"),
    ("reits_irr", r"中债真实\s*IRR|中债隐含\s*IRR|特许经营权(?:类)?\s*REITs|真实内部收益率|\bIRR\b"),
    ("dxy", r"美元指数|\bDXY\b"),
    ("cot", r"期货大资金持仓报告|\bCOT\b"),
    ("cds", r"债务违约保险费率|信用违约互换|\bCDS\b"),
    ("w8ben", r"\bW-?8BEN\b"),
    ("crs", r"(?<![A-Za-z0-9])CRS(?![A-Za-z0-9])|共同申报准则"),
    ("low_water", r"(?:期指|期货|现货)?低水(?!位|平)"),
    ("high_water", r"(?:期指|期货|现货)?高水(?!位|平)"),
    ("ex_div", r"除净日|(?<!剔)除净(?!增)"),
    ("discount_ex_div", r"贴权"),
    ("margin_hk", r"孖展"),
    ("official_settle", r"官方结算价|(?<![A-Za-z0-9])官结"),
    ("basis_spread", r"升贴水|期货升水|期货贴水|期现升水|期现贴水|平水"),
    ("bps", r"(?<![A-Za-z0-9_-])(?:基点|bps)(?![A-Za-z0-9_-])|(?<=\d)\s*bp(?![A-Za-z0-9_-])"),
    ("limit_order", r"限价挂单|限价单"),
    ("discount_placement", r"折价配售|配售新股|配售抛压"),
    ("cbbc_zone", r"牛熊证重货区|牛熊证街货|重货区"),
    ("hkd_weak_peg", r"联汇弱方保证|弱方兑换保证|弱方保证线|弱方保证"),
    ("closing_auction", r"收市竞价时段|收市竞价|竞价盘"),
    ("margin_ratio", r"融资保证金比例|两融与降保|两融余额|两融"),
    ("pboc_omo", r"央行逆回购|公开市场逆回购|\bOMO\b"),
    ("ann_basis", r"年化贴水率|年化贴水|期指基差|股指期货基差"),
    ("top20_short", r"前\s*20\s*席位净空|前二十席位净空|前\s*20\s*大席位"),
    ("ins_research_rate", r"预定利率研究值|预定利率动态调整"),
    ("cornerstone_mech_b", r"基石与机制\s*B|机制\s*B|基石大解禁|基石解禁|基石投资者"),
    ("creditwatch", r"负面信用观察|信用观察|\bCreditWatch\b"),
    ("redemption_gate", r"赎回闸门|巨额赎回限制|赎回限制"),
    ("equal_weight", r"标普\s*500\s*等权|等权重指数|等权指数"),
)
_GLOSSARY_COMBINED_RE = re.compile(
    "|".join(f"(?P<k_{key}>{pat})" for key, pat in _GLOSSARY_PHRASE_SPECS)
)
_GLOSSARY_ALL_KEYS_COUNT = len(_GLOSSARY_PHRASE_SPECS)


def inject_glossary_tips(html_str: str) -> str:
    """Wrap at most 1 first occurrence per glossary key with _term_tip outside protected tags & collapsed <details>."""
    if not html_str:
        return html_str
    used_keys: set[str] = set(_GLOSSARY_EXISTING_KEY_RE.findall(html_str))
    if len(used_keys) >= _GLOSSARY_ALL_KEYS_COUNT:
        return html_str

    raw_blocks = _GLOSSARY_RAW_BLOCKS_RE.split(html_str)
    out_blocks: list[str] = []

    def _replace_match(m: re.Match[str]) -> str:
        group_name = m.lastgroup or ""
        key = group_name[2:] if group_name.startswith("k_") else ""
        if not key or key in used_keys:
            return m.group(0)
        used_keys.add(key)
        return _term_tip(key, html_mod.unescape(m.group(0)))

    for b_idx, block in enumerate(raw_blocks):
        if b_idx % 2 == 1 or len(used_keys) >= _GLOSSARY_ALL_KEYS_COUNT:
            out_blocks.append(block)
            continue
        tokens = _GLOSSARY_TOKEN_RE.split(block)
        # Stack entries: (tag_name, is_skip_tag, is_skip_class, is_collapsed_details)
        elem_stack: list[tuple[str, bool, bool, bool]] = []
        skip_depth = 0
        skip_cls_depth = 0
        collapsed_details_depth = 0
        out_tokens: list[str] = []
        for tok in tokens:
            if not tok:
                continue
            if tok.startswith("<!--"):
                out_tokens.append(tok)
                continue
            if tok.startswith("<"):
                tm = _GLOSSARY_TAG_NAME_RE.match(tok)
                if tm:
                    is_close = bool(tm.group(1))
                    tname = tm.group(2).lower()
                    is_self_close = tok.rstrip().endswith("/>") or (tname in _GLOSSARY_VOID_TAGS)
                    if is_close:
                        for idx_s in range(len(elem_stack) - 1, -1, -1):
                            if elem_stack[idx_s][0] == tname:
                                while len(elem_stack) > idx_s:
                                    _, was_sk_t, was_sk_c, was_col_d = elem_stack.pop()
                                    if was_sk_t and skip_depth > 0:
                                        skip_depth -= 1
                                    if was_sk_c and skip_cls_depth > 0:
                                        skip_cls_depth -= 1
                                    if was_col_d and collapsed_details_depth > 0:
                                        collapsed_details_depth -= 1
                                break
                    elif not is_self_close:
                        is_sk_t = tname in _GLOSSARY_SKIP_TAGS
                        m_cls = _GLOSSARY_CLASS_ATTR_RE.search(tok)
                        cls_str = (m_cls.group(1) or m_cls.group(2) or "") if m_cls else ""
                        is_sk_c = bool(cls_str and any(c in _GLOSSARY_SKIP_CLASSES for c in cls_str.split()))
                        is_col_d = (tname == "details") and not bool(re.search(r"\bopen\b", tok, flags=re.IGNORECASE))
                        elem_stack.append((tname, is_sk_t, is_sk_c, is_col_d))
                        if is_sk_t:
                            skip_depth += 1
                        if is_sk_c:
                            skip_cls_depth += 1
                        if is_col_d:
                            collapsed_details_depth += 1
                out_tokens.append(tok)
                continue
            if (
                skip_depth > 0
                or skip_cls_depth > 0
                or collapsed_details_depth > 0
                or len(used_keys) >= _GLOSSARY_ALL_KEYS_COUNT
                or not tok.strip()
            ):
                out_tokens.append(tok)
                continue
            out_tokens.append(_GLOSSARY_COMBINED_RE.sub(_replace_match, tok))
        out_blocks.append("".join(out_tokens))
    return "".join(out_blocks)


def _fmt_ch_num(order: Any, fallback_idx: int = 1) -> str:
    """Format channel order cleanly as 01..09, 10, 11, 12 (never 010/011/012)."""
    try:
        return f"{int(order):02d}"
    except (TypeError, ValueError):
        return f"{int(fallback_idx):02d}"


def render_toc_list(toc: list[tuple[int, str, str]]) -> str:
    if not toc:
        return ""
    lis = []
    for lvl, hid, label in toc:
        short = label if len(label) <= 32 else label[:31].rstrip(" 、，,·:：—-") + "…"
        lis.append(
            f'<li><a class="toc-link lvl-{lvl}" href="#{esc(hid)}" title="{esc(label)}">{esc(short)}</a></li>'
        )
    return '<ul class="toc-list">' + "".join(lis) + "</ul>"


def _build_cmd_nav_items(
    base_prefix: str,
    total_pool: int,
    channels_list: list[dict[str, Any]] | None = None,
    etf_count: int = 0,
    total_kline_count: int = 0,
) -> list[dict[str, str]]:
    pool_label = f"{total_pool}股池" if total_pool > 0 else "龙头股池"
    ch_items = [c for c in (channels_list or []) if isinstance(c, dict) and str(c.get("id", "")).strip()]
    ch_cnt = len(ch_items)
    ch_cnt_lbl = f"{ch_cnt} 大独立通道" if ch_cnt else "全渠道总览"
    etf_cnt_lbl = f"{etf_count} 只" if etf_count else "全球重点"
    kline_cnt_lbl = f"{total_kline_count} 标的" if total_kline_count > 0 else "480+ 标的"

    items: list[dict[str, str]] = [
        {
            "title": "全球六大市场 10 秒水温驾驶舱",
            "meta": "总览 · 六大市场红绿灯（A/港/美 · 债/金/非美）、四笔钱与全渠道",
            "href": f"{base_prefix}index.html",
            "keywords": "总览 首页 驾驶舱 六大市场 利率 非美 债券 overview cockpit home 四笔钱",
        },
        {
            "title": "⚡ QDII 溢价与直销/支付宝限购对照表",
            "meta": "专窗 · 场内溢价 vs 官方直销 App / 支付宝限额比价与盈亏平衡计算器",
            "href": f"{base_prefix}channels/qdii_mrf.html#sec-qdii-compare",
            "keywords": "qdii 溢价 限购 直销 支付宝 天天 大成 南方 博时 嘉实 易方达 纳指 标普 日经 德国 对比 计算器",
        },
        {
            "title": "⚡ 境内 QDII 溢价排雷",
            "meta": "ETF 雷达 · 场内 QDII 实时折溢价与高危停牌排雷专窗",
            "href": f"{base_prefix}etfs.html#preset=qdii",
            "keywords": "qdii 溢价 排雷 停牌 场内 大成 纳指 标普 非美 etf",
        },
        {
            "title": "🛡️ 债券、现金与中美利率",
            "meta": "核心 #4 · 中美 10Y 利差、中债短融/国债、美债短盾与未锁汇汇损",
            "href": f"{base_prefix}index.html#card-rates",
            "keywords": "债券 现金 利率 国债 美债 利差 汇损 短融 511360 511260 511090 sgov ib01 tlt rates bonds",
        },
        {
            "title": "🌏 非美发达与亚太权益",
            "meta": "卫星 · 日/欧平价低费分散、台韩 AI 晴雨表与印度 LOF 防退市",
            "href": f"{base_prefix}index.html#card-nonus",
            "keywords": "非美 发达 亚太 日本 东证 日经 欧洲 德国 台湾 韩国 印度 513800 159561 159687 vxus vgk iemg nonus global",
        },
        {
            "title": "🧭 核心时政深解与未来 30 天金融日历",
            "meta": "时政日历 · 央行/财政/联储/地缘政策白话深解与未来 14–30 天节点倒计时",
            "href": f"{base_prefix}index.html#sec-policy-calendar",
            "keywords": "时政 政策 日历 央行 财政 美联储 议息 关税 财报 窗口 倒计时 policy calendar pcal",
        },
        {
            "title": "新手 3 分钟入门指南与高频关键词速查",
            "meta": f"指南 · 红绿灯解读、8 大常见避坑与 {len(GLOSSARY_TERMS)} 词白话解释",
            "href": f"{base_prefix}guide.html",
            "keywords": "新手 指南 入门 术语 白话 避坑 四笔钱 guide glossary",
        },
        {
            "title": f"全市场交互 K 线与技术指标终端（{kline_cnt_lbl}）",
            "meta": "终端 · 全球六大市场多指数、中美债率、大宗汇率、重点 ETF 与 231 股 K 线/均线/安全锚",
            "href": f"{base_prefix}charts.html",
            "keywords": "k线 图表 技术指标 ma macd rsi boll kdj 上证 沪深300 标普 纳指 黄金 利率 非美 charts kline",
        },
        {
            "title": "黄金最新日报",
            "meta": "日报 · 四步买金红绿灯与实盘锚",
            "href": f"{base_prefix}daily/gold-latest.html",
            "keywords": "黄金 金价 早报 午报 晚报 gold daily xau",
        },
        {
            "title": "中国 A 股最新日报",
            "meta": "日报 · 七维大盘与红利防守",
            "href": f"{base_prefix}daily/a-share-latest.html",
            "keywords": "a股 沪深300 上证 创业板 科创50 早报 午报 晚报 a-share cn",
        },
        {
            "title": "香港股市最新日报",
            "meta": "日报 · 联汇水位与南向资金",
            "href": f"{base_prefix}daily/hk-stock-latest.html",
            "keywords": "港股 恒生 恒科 国企 早报 午报 晚报 hk-stock hsi",
        },
        {
            "title": "美国股市最新日报",
            "meta": "日报 · 标普纳指与政策雷达",
            "href": f"{base_prefix}daily/us-stock-latest.html",
            "keywords": "美股 标普 纳指 道指 美债 早报 午报 晚报 us-stock sp500",
        },
        {
            "title": "黄金跨世纪周期主报告（1971–2030）",
            "meta": "常青旗舰 · 宏观周期与配置框架",
            "href": f"{base_prefix}reports/gold.html",
            "keywords": "黄金 主报告 旗舰 手册 gold master flagship",
        },
        {
            "title": "中国 A 股跨周期全景手册",
            "meta": "常青旗舰 · 宏观与全池龙头诊断",
            "href": f"{base_prefix}reports/a-share.html",
            "keywords": "a股 全景手册 旗舰 a-share flagship",
        },
        {
            "title": "香港股市跨周期全景手册",
            "meta": "常青旗舰 · 联汇与红筹/H股税制",
            "href": f"{base_prefix}reports/hk-stock.html",
            "keywords": "港股 全景手册 旗舰 hk-stock flagship",
        },
        {
            "title": "美国股市跨周期全景手册",
            "meta": "常青旗舰 · 科技/防弹衣全板块覆盖",
            "href": f"{base_prefix}reports/us-stock.html",
            "keywords": "美股 全景手册 旗舰 us-stock flagship",
        },
        {
            "title": f"个人多元投资渠道总览（{ch_cnt_lbl}）",
            "meta": "专页 · 一眼对比表、组合模板、打新与双层风控墙",
            "href": f"{base_prefix}channels.html",
            "keywords": "多元渠道 活钱 存款 外币 债券 理财 保险 养老金 qdii 互认 可转债 reits 商品 私募 channels",
        },
    ]

    for idx, ch in enumerate(ch_items, start=1):
        cid = str(ch["id"]).strip()
        num = _fmt_ch_num(ch.get("order"), idx)
        cname = str(ch.get("name") or cid).strip()
        short_nm = str(ch.get("short_name") or "").strip()
        cat_lbl = str(ch.get("category_label") or "").strip()
        badge = str(ch.get("badge") or "").strip()
        prod_codes = " ".join(
            str(p.get("code") or "") for p in (ch.get("products") or [])[:6] if isinstance(p, dict)
        )
        items.append(
            {
                "title": f"渠道详情 {num}：{cname}",
                "meta": f"多元渠道 · {cat_lbl or '独立详情页'}",
                "href": f"{base_prefix}channels/{cid}.html",
                "keywords": f"{cid} {cname} {short_nm} {cat_lbl} {badge} {prod_codes}".strip(),
            }
        )

    items.extend(
        [
            {
                "title": f"全球重点 ETF 深度雷达（{etf_cnt_lbl}）",
                "meta": "工具 · A/港/美/全球/债券商品 ETF 费率、溢价与深度拆解",
                "href": f"{base_prefix}etfs.html",
                "keywords": "etf 雷达 宽基 红利 溢价 qdii ucits 债券 现金盾 etfs",
            },
            {
                "title": f"全球核心龙头交互筛选器（{pool_label} · 含7维深研）",
                "meta": "工具 · 三市龙头估值、股息、安全锚与 7 维机构档案",
                "href": f"{base_prefix}screener.html",
                "keywords": "股池 筛选器 龙头 7维 深研 screener stocks",
            },
            {
                "title": "快捷视图：● 当下底座龙头",
                "meta": "股池预设 · 红灯期可配置防弹衣底座",
                "href": f"{base_prefix}screener.html#preset=base",
                "keywords": "底座 绿灯 防守 base green",
            },
            {
                "title": "快捷视图：高股息 ≥4% 龙头",
                "meta": "股池预设 · 现金流与分红缓冲",
                "href": f"{base_prefix}screener.html#preset=high-div",
                "keywords": "高股息 分红 息率 dividend high-div",
            },
            {
                "title": "快捷视图：近安全锚 ≤12%",
                "meta": "股池预设 · 接近目标击球区间",
                "href": f"{base_prefix}screener.html#preset=near-anchor",
                "keywords": "安全锚 买点 击球 near-anchor",
            },
            {
                "title": "快捷视图：A/H 倒挂折价股",
                "meta": "股池预设 · A 股较 H 股折价套利视角",
                "href": f"{base_prefix}screener.html#preset=ah-inverted",
                "keywords": "ah 倒挂 折价 溢价 ah-inverted",
            },
            {
                "title": "全球股市公开预测记分卡",
                "meta": "记分卡 · 到期验真与避坑台账",
                "href": f"{base_prefix}scorecard.html#equity-scorecard",
                "keywords": "记分卡 股市 验真 scorecard equity",
            },
            {
                "title": "黄金公开预测记分卡",
                "meta": "记分卡 · 命中率与勘误留痕",
                "href": f"{base_prefix}scorecard.html#gold-scorecard",
                "keywords": "记分卡 黄金 验真 scorecard gold",
            },
            {
                "title": "股市观点演进日志",
                "meta": "账本 · 历期三市逻辑与仓位演化",
                "href": f"{base_prefix}scorecard.html#equity-changelog",
                "keywords": "演进 日志 changelog equity",
            },
            {
                "title": "黄金观点演进与辟谣核查账本",
                "meta": "账本 · 谣言证伪与官方核查明细",
                "href": f"{base_prefix}scorecard.html#gold-audit-log",
                "keywords": "辟谣 核查 账本 audit changelog gold",
            },
            {
                "title": "历史早午晚报档案与旗舰书架",
                "meta": "档案 · 按市场/早午晚时段/刊型检索",
                "href": f"{base_prefix}archive.html",
                "keywords": "历史 档案 往期 早报 午报 晚报 archive",
            },
        ]
    )
    return items


def render_page_shell(
    *,
    title: str,
    active_nav: str,
    base_prefix: str,
    content_html: str,
    market_attr: str = "overview",
    doc_kind: str = "overview",
    edition_attr: str = "",
    channel_id: str = "",
    total_pool: int = 0,
    channel_count: int = 0,
    channels_list: list[dict[str, Any]] | None = None,
    etf_count: int = 0,
    total_kline_count: int = 0,
    toc_items: list[tuple[int, str, str]] | None = None,
    show_chart_modal: bool = False,
    footer_ts: str = "",
    gold_red_light: bool = False,
) -> str:
    pool_label = f"{total_pool}股池" if total_pool > 0 else "龙头股池"
    ch_footer_lbl = f"{channel_count}大多元渠道" if channel_count > 0 else "多元渠道"
    reports_group = ("gold", "a-share", "hk-stock", "us-stock", "scorecard", "archive")
    screeners_group = ("etfs", "screener")
    rep_active = " active" if active_nav in reports_group else ""
    scr_active = " active" if active_nav in screeners_group else ""
    is_flagship = doc_kind == "flagship"

    nav_html = (
        f'<a class="nav-pill{" active" if active_nav == "overview" else ""}" data-nav="overview" href="{base_prefix}index.html">总览</a>'
        '<div class="nav-group">'
        f'<button type="button" class="nav-pill nav-drop-btn{rep_active}" data-nav="reports" aria-expanded="false" aria-haspopup="true">深度研报 ▾</button>'
        '<div class="nav-dropdown" hidden>'
        f'<a class="nav-drop-item{" active" if (active_nav == "gold" and not is_flagship) else ""}" href="{base_prefix}daily/gold-latest.html"><span class="nav-dot nav-dot-gold" aria-hidden="true"></span>黄金日报</a>'
        f'<a class="nav-drop-item{" active" if (active_nav == "a-share" and not is_flagship) else ""}" href="{base_prefix}daily/a-share-latest.html"><span class="nav-dot nav-dot-a-share" aria-hidden="true"></span>A股日报</a>'
        f'<a class="nav-drop-item{" active" if (active_nav == "hk-stock" and not is_flagship) else ""}" href="{base_prefix}daily/hk-stock-latest.html"><span class="nav-dot nav-dot-hk-stock" aria-hidden="true"></span>港股日报</a>'
        f'<a class="nav-drop-item{" active" if (active_nav == "us-stock" and not is_flagship) else ""}" href="{base_prefix}daily/us-stock-latest.html"><span class="nav-dot nav-dot-us-stock" aria-hidden="true"></span>美股日报</a>'
        '<div class="nav-drop-sep"></div>'
        f'<a class="nav-drop-item{" active" if active_nav == "archive" else ""}" href="{base_prefix}archive.html">历史档案与旗舰手册</a>'
        f'<a class="nav-drop-item{" active" if active_nav == "scorecard" else ""}" href="{base_prefix}scorecard.html">公开预测记分卡</a>'
        "</div></div>"
        f'<a class="nav-pill{" active" if active_nav == "charts" else ""}" data-nav="charts" href="{base_prefix}charts.html">K线图表</a>'
        '<div class="nav-group">'
        f'<button type="button" class="nav-pill nav-drop-btn{scr_active}" data-nav="screeners" aria-expanded="false" aria-haspopup="true">选基选股 ▾</button>'
        '<div class="nav-dropdown" hidden>'
        f'<a class="nav-drop-item{" active" if active_nav == "etfs" else ""}" href="{base_prefix}etfs.html">全球 ETF 雷达</a>'
        f'<a class="nav-drop-item{" active" if active_nav == "screener" else ""}" href="{base_prefix}screener.html">{pool_label} 7维筛选</a>'
        f'<a class="nav-drop-item" href="{base_prefix}screener.html#view=ah-matrix">27 对 A/H 税后比价</a>'
        "</div></div>"
        f'<a class="nav-pill{" active" if active_nav == "channels" else ""}" data-nav="channels" href="{base_prefix}channels.html">多元渠道</a>'
        f'<a class="nav-pill nav-pill-guide{" active" if active_nav == "guide" else ""}" data-nav="guide" href="{base_prefix}guide.html">新手指南</a>'
    )

    subnav_html = ""
    if active_nav in reports_group:
        sub_links = [
            ("gold", f"{base_prefix}daily/gold-latest.html", "黄金日报"),
            ("a-share", f"{base_prefix}daily/a-share-latest.html", "A股日报"),
            ("hk-stock", f"{base_prefix}daily/hk-stock-latest.html", "港股日报"),
            ("us-stock", f"{base_prefix}daily/us-stock-latest.html", "美股日报"),
            ("scorecard", f"{base_prefix}scorecard.html", "记分卡"),
            ("archive", f"{base_prefix}archive.html", "历史档案"),
        ]
        subnav_html = (
            '<nav class="subnav-bar no-print" aria-label="研报与档案快捷导航"><div class="subnav-inner">'
            + "".join(
                f'<a class="subnav-link{" active" if (k == active_nav and not is_flagship) else ""}" href="{h}">{l}</a>'
                for k, h, l in sub_links
            )
            + "</div></nav>"
        )
    elif active_nav in screeners_group:
        etf_sub_lbl = f"全球 ETF 雷达 ({etf_count})" if etf_count > 0 else "全球 ETF 雷达"
        pool_sub_lbl = f"核心龙头股池 ({total_pool})" if total_pool > 0 else "核心龙头股池"
        subnav_html = (
            '<nav class="subnav-bar no-print" aria-label="选基选股快捷导航"><div class="subnav-inner">'
            f'<a class="subnav-link{" active" if active_nav == "etfs" else ""}" href="{base_prefix}etfs.html">{esc(etf_sub_lbl)}</a>'
            f'<a class="subnav-link{" active" if active_nav == "screener" else ""}" href="{base_prefix}screener.html">{esc(pool_sub_lbl)}</a>'
            f'<a class="subnav-link" href="{base_prefix}screener.html#view=ah-matrix">27 对 A/H 税后比价</a>'
            "</div></nav>"
        )
    elif active_nav == "channels":
        ch_ov_lbl = f"{channel_count}大渠道总览" if channel_count > 0 else "12大渠道总览"
        is_qdii_detail = channel_id == "qdii_mrf"
        subnav_html = (
            '<nav class="subnav-bar no-print" aria-label="多元渠道快捷导航"><div class="subnav-inner">'
            f'<a class="subnav-link{" active" if not is_qdii_detail else ""}" href="{base_prefix}channels.html">{esc(ch_ov_lbl)}</a>'
            f'<a class="subnav-link{" active" if is_qdii_detail else ""}" href="{base_prefix}channels/qdii_mrf.html#sec-qdii-compare">QDII溢价与限购专窗</a>'
            f'<a class="subnav-link" href="{base_prefix}channels.html#sec-ipo-toolbox">打新工具箱</a>'
            f'<a class="subnav-link" href="{base_prefix}channels.html#sec-warning-wall">风险警示墙</a>'
            "</div></nav>"
        )

    show_font_ctrl = (doc_kind in ("daily", "flagship", "guide", "scorecard")) or (active_nav in ("guide", "scorecard"))
    font_ctrl_html = (
        '<div class="ctrl-seg">'
        '<button type="button" class="ctrl-btn" id="font-dec" title="缩小字号" aria-label="缩小字号">A-</button>'
        '<button type="button" class="ctrl-btn" id="font-inc" title="放大字号" aria-label="放大字号">A+</button>'
        "</div>"
        if show_font_ctrl
        else ""
    )

    watch_drawer_html = (
        '<div class="drawer-backdrop no-print" id="watch-drawer" hidden role="dialog" aria-modal="true" aria-label="我的自选清单">'
        '<div class="drawer-panel">'
        '<div class="drawer-head">'
        '<div class="drawer-title">★ 我的自选清单</div>'
        '<button type="button" class="ctrl-btn" data-action="close-watch-drawer" aria-label="关闭自选">关闭 ✕</button>'
        "</div>"
        '<div class="drawer-body" id="watch-drawer-body"></div>'
        "</div></div>"
    )

    mtab_overview_svg = (
        '<svg class="mtab-svg" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="12" cy="12" r="9"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>'
    )
    mtab_reports_svg = (
        '<svg class="mtab-svg" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>'
    )
    mtab_charts_svg = (
        '<svg class="mtab-svg" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<polyline points="3 17 9 11 13 15 21 7"/><polyline points="15 7 21 7 21 13"/></svg>'
    )
    mtab_screeners_svg = (
        '<svg class="mtab-svg" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
    )
    mtab_channels_svg = (
        '<svg class="mtab-svg" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
        '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>'
    )

    mobile_tabbar_html = (
        '<nav class="mobile-tabbar no-print" aria-label="移动端主导航">'
        f'<a class="mtab-item{" active" if active_nav == "overview" else ""}" href="{base_prefix}index.html">'
        f'<span class="mtab-icon" aria-hidden="true">{mtab_overview_svg}</span><span class="mtab-lbl">总览</span></a>'
        f'<a class="mtab-item{" active" if active_nav in reports_group else ""}" href="{base_prefix}daily/a-share-latest.html">'
        f'<span class="mtab-icon" aria-hidden="true">{mtab_reports_svg}</span><span class="mtab-lbl">研报</span></a>'
        f'<a class="mtab-item{" active" if active_nav == "charts" else ""}" href="{base_prefix}charts.html">'
        f'<span class="mtab-icon" aria-hidden="true">{mtab_charts_svg}</span><span class="mtab-lbl">K线</span></a>'
        f'<a class="mtab-item{" active" if active_nav in screeners_group else ""}" href="{base_prefix}etfs.html">'
        f'<span class="mtab-icon" aria-hidden="true">{mtab_screeners_svg}</span><span class="mtab-lbl">筛选</span></a>'
        f'<a class="mtab-item{" active" if active_nav == "channels" else ""}" href="{base_prefix}channels.html">'
        f'<span class="mtab-icon" aria-hidden="true">{mtab_channels_svg}</span><span class="mtab-lbl">渠道</span></a>'
        "</nav>"
    )

    has_toc = bool(toc_items)
    toc_drawer_html = ""
    if has_toc:
        toc_drawer_html = (
            '<div class="toc-backdrop" id="toc-backdrop" role="dialog" aria-modal="true" aria-label="章节目录">'
            '<div class="toc-sheet">'
            '<div class="toc-sheet-hdr"><span>报告目录</span>'
            '<button type="button" class="ctrl-btn" data-action="close-toc">关闭 ✕</button></div>'
            f'<div class="toc-sheet-body">{render_toc_list(toc_items or [])}</div>'
            "</div></div>"
        )

    chart_modal_html = ""
    if show_chart_modal:
        chart_modal_html = (
            '<div class="chart-modal" id="chart-modal" role="dialog" aria-modal="true" aria-label="图表放大">'
            '<div class="chart-modal-bar">'
            '<div class="chart-modal-title" id="chart-modal-title">图表放大</div>'
            '<div class="chart-modal-ctrls">'
            '<button type="button" class="modal-btn" data-action="zoom-out">−</button>'
            '<button type="button" class="modal-btn" data-action="zoom-reset" id="chart-zoom-readout">100%</button>'
            '<button type="button" class="modal-btn" data-action="zoom-in">＋</button>'
            '<button type="button" class="modal-btn" data-action="close-chart">关闭 ✕</button>'
            "</div></div>"
            '<div class="chart-modal-stage"><div class="chart-modal-canvas" id="chart-modal-canvas"></div></div>'
            "</div>"
        )

    brand_svg = (
        '<svg viewBox="0 0 28 28" width="20" height="20">'
        '<circle cx="14" cy="14" r="10.5" fill="none" stroke="currentColor" stroke-width="1.6" opacity="0.88"/>'
        '<polygon points="14,4.5 17,14 14,23.5 11,14" fill="currentColor"/>'
        '<circle cx="14" cy="14" r="2.1" fill="#141a24"/></svg>'
    )
    sun_svg = (
        '<svg class="icon-sun" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>'
    )
    moon_svg = (
        '<svg class="icon-moon" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
    )

    cmd_nav_json = json.dumps(
        _build_cmd_nav_items(
            base_prefix,
            total_pool,
            channels_list=channels_list,
            etf_count=etf_count,
            total_kline_count=total_kline_count,
        ),
        ensure_ascii=False,
    ).replace("</", "<\\/")
    cmd_palette_html = (
        '<div class="cmd-backdrop no-print" id="cmd-palette" role="dialog" aria-modal="true" aria-label="快速跳转">'
        '<div class="cmd-dialog">'
        '<div class="cmd-head">'
        '<input type="search" id="cmd-input" class="cmd-input" placeholder="输入市场、渠道、新手指南、股池或关键词快速跳转…" autocomplete="off" aria-label="快速跳转搜索">'
        '<button type="button" class="ctrl-btn" data-action="close-cmd" aria-label="关闭快速跳转">ESC</button>'
        "</div>"
        '<div class="cmd-list" id="cmd-list" role="listbox"></div>'
        "</div></div>"
        f'<script id="cmd-nav-data" type="application/json">{cmd_nav_json}</script>'
    )
    back_to_top_html = (
        '<button type="button" class="back-to-top no-print" id="back-to-top" '
        'data-action="scroll-top" title="回到顶部" aria-label="回到顶部">↑</button>'
    )

    body_classes: list[str] = []
    if subnav_html:
        body_classes.append("has-subnav")
    if active_nav in ("etfs", "screener"):
        body_classes.append("tool-page")
    body_cls_attr = f' class="{" ".join(body_classes)}"' if body_classes else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{esc(title)} ｜ 全球投研</title>
  <meta name="theme-color" content="#f6f3ec">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="全球投研">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="icon" type="image/svg+xml" href="{base_prefix}assets/favicon.svg">
  <link rel="manifest" href="{base_prefix}manifest.json">
  {THEME_INIT_SCRIPT}
  <link rel="stylesheet" href="{base_prefix}assets/app.css">
</head>
<body{body_cls_attr} data-market="{esc(market_attr)}" data-doc-kind="{esc(doc_kind)}" data-base-prefix="{esc(base_prefix)}" data-gold-red-light="{'1' if gold_red_light else '0'}"{f' data-edition="{esc(edition_attr)}"' if edition_attr else ""}>
  <div class="reading-progress" id="reading-progress"></div>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand-link" href="{base_prefix}index.html">
        <span class="brand-mark" aria-hidden="true">{brand_svg}</span>
        <span class="brand-text"><span class="brand-title">全球投研</span><span class="brand-sub">A · 港 · 美 · 债 · 金 · 非美</span></span>
      </a>
      <div class="main-nav-wrap"><nav class="main-nav" aria-label="主导航">{nav_html}</nav></div>
      <div class="header-controls">
        <a class="mobile-guide-btn" href="{base_prefix}guide.html">新手</a>
        <button type="button" class="ctrl-btn ctrl-watch" id="watch-drawer-open" title="打开我的自选清单" aria-label="我的自选" aria-expanded="false" aria-controls="watch-drawer">★ <span class="watch-lbl">自选</span> <span class="watch-badge" id="hdr-watch-cnt">0</span></button>
        <button type="button" class="ctrl-btn ctrl-cmd" id="cmd-open" title="快速搜索与跳转 (⌘K)" aria-label="快速搜索与跳转">搜索 <kbd class="kbd-chip">⌘K</kbd></button>
        {font_ctrl_html}
        <button type="button" class="ctrl-btn ctrl-theme" id="theme-toggle" title="切换深浅色模式" aria-label="切换深浅色模式">{sun_svg}{moon_svg}</button>
      </div>
    </div>
  </header>
  {subnav_html}

  <main class="page-main">
    {content_html}
  </main>

  <footer class="site-footer">
    <div class="footer-inner">
      <div class="footer-grid">
        <div class="footer-col">
          <div class="footer-brand">全球投研 · CN · HK · US · BONDS · GOLD · GLOBAL</div>
          <p class="footer-desc">每日 07:30 早报 · 11:30 午报 · 18:00 晚报北京时间准时交付 · 多源官方库交叉核验{(" · 更新：" + esc(footer_ts)) if footer_ts else ""}</p>
        </div>
        <div class="footer-col">
          <div class="footer-col-title">核心导航</div>
          <div class="footer-links">
            <a href="{base_prefix}index.html">总览</a>
            <a href="{base_prefix}guide.html">新手3分钟指南</a>
            <a href="{base_prefix}charts.html">K线图表终端</a>
            <a href="{base_prefix}daily/gold-latest.html">黄金日报</a>
            <a href="{base_prefix}daily/a-share-latest.html">A股日报</a>
            <a href="{base_prefix}daily/hk-stock-latest.html">港股日报</a>
            <a href="{base_prefix}daily/us-stock-latest.html">美股日报</a>
            <a href="{base_prefix}channels.html">{esc(ch_footer_lbl)}</a>
            <a href="{base_prefix}etfs.html">全球ETF雷达</a>
            <a href="{base_prefix}screener.html">{pool_label}</a>
            <a href="{base_prefix}scorecard.html">记分卡</a>
            <a href="{base_prefix}archive.html">历史档案</a>
          </div>
        </div>
        <div class="footer-col">
          <div class="footer-col-title">透明与风控声明</div>
          <p class="footer-disclaimer">准时发刊不阻塞，未披露官源如实挂账留痕；严守仓位红线、远离杠杆，所有研究仅供信息参考，不构成个性化投资建议。</p>
        </div>
      </div>
    </div>
  </footer>

  {mobile_tabbar_html}
  {back_to_top_html}
  {watch_drawer_html}
  {cmd_palette_html}
  {toc_drawer_html}
  {chart_modal_html}
  <script src="{base_prefix}assets/kline.js" defer></script>
  <script src="{base_prefix}assets/app.js" defer></script>
</body>
</html>
"""


def render_doc_with_toc(
    *,
    toolbar_html: str,
    cover_html: str,
    body_html: str,
    footer_note: str,
    toc_items: list[tuple[int, str, str]],
    doc_kind: str = "daily",
    disclosure_html: str = "",
    kline_strip_html: str = "",
    visual_cockpit_html: str = "",
    market_news_html: str = "",
) -> str:
    footer_note = footer_note.replace("本每日研报数据均经多源官方数据库核验，仅供参考", "本文按所标日期记录行情和研究判断")
    footer_div = f'<div class="footer-note">{esc(footer_note)}</div>' if footer_note else ""
    cited_urls = re.findall(r'<a\b[^>]*\bhref="(https://[^"\s]+)"', body_html, flags=re.I)
    external_citations = any(
        is_https_source(url, direct=True) and urllib.parse.urlsplit(url).hostname != "nanless.github.io"
        for url in cited_urls
    )
    citation_notice = "" if external_citations else '<p class="footer-note">这篇正文暂未附可直接打开的外部出处。</p>'
    mobile_strip = ""
    if toc_items:
        sidebar = (
            '<aside class="toc-sidebar" aria-label="目录导航">'
            '<div class="toc-heading"><span>本篇目录</span><span class="toc-pct" id="toc-pct">0%</span></div>'
            f"{render_toc_list(toc_items)}"
            "</aside>"
        )
        top_toc = [t for t in toc_items if t[0] in (1, 2)] or toc_items[:8]
        pills = "".join(
            f'<a class="mobile-toc-pill" href="#{esc(hid)}">'
            f'{esc(lbl if len(lbl) <= 18 else lbl[:17].rstrip(" 、，,·:：—-") + "…")}</a>'
            for _, hid, lbl in top_toc
        )
        mobile_strip = f'<div class="mobile-toc-strip no-print" aria-label="章节快捷跳转">{pills}</div>'
        layout_cls = "doc-layout"
    else:
        sidebar = ""
        layout_cls = "doc-layout no-toc"

    kline_wrapped_html = ""
    if kline_strip_html:
        kline_wrapped_html = (
            '<details class="kline-daily-collapse no-print">'
            '<summary class="kline-collapse-sum">'
            '<span>📈 展开本市多指数交互 K 线与 10 秒技术体检</span>'
            '<span class="kline-collapse-cta"><span class="kline-cta-closed">点击展开 ▾</span><span class="kline-cta-open">收起 ▴</span></span>'
            "</summary>"
            f"{kline_strip_html}"
            "</details>"
        )

    art_cls = "doc-flagship" if doc_kind == "flagship" else "doc-daily"
    return (
        f"{toolbar_html}"
        f'<div class="{layout_cls}">'
        f"{sidebar}"
        f"{mobile_strip}"
        f'<article class="article-card {art_cls}">'
        f"{cover_html}"
        f"{citation_notice}"
        f"{visual_cockpit_html}"
        f"{disclosure_html}"
        f"{kline_wrapped_html}"
        f'<div class="article-body">{body_html}{market_news_html}</div>'
        f"{footer_div}"
        f"</article>"
        f"</div>"
    )


# ==============================================================================
# 6. PAGE BUILDERS (Cockpit, Flagships, Dailies, Screener, Scorecard, Archive)
# ==============================================================================

def _lamp_css_class(lamp_str: str) -> str:
    s = str(lamp_str or "").lower()
    if "green" in s or "绿灯" in s or "满格" in s:
        return "lamp-green"
    if "yellow" in s or "amber" in s or "黄灯" in s:
        return "lamp-amber"
    return "lamp-red"


def _safe_float(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        num = float(val)
    except (TypeError, ValueError, OverflowError):
        return None
    return num if isfinite(num) else None


def _fmt_num(
    val: Any,
    fmt: str,
    fallback: str = "待核",
    *,
    prefix: str = "",
    suffix: str = "",
) -> str:
    num = _safe_float(val)
    if num is None:
        return fallback
    return f"{prefix}{format(num, fmt)}{suffix}"


def _fmt_chg_span(val: Any, fallback: str = "待核") -> str:
    num = _safe_float(val)
    if num is None:
        return fallback
    cls = "chg-up" if num >= 0 else "chg-dn"
    return f'<span class="{cls}">{num:+.2f}%</span>'


def _positive_quote(value: Any) -> float | None:
    quote = _safe_float(value)
    return quote if quote is not None and quote > 0 else None


def _resolve_dated_metric(
    mapping: dict[str, Any], canonical_key: str, dated_pattern: str,
) -> float | None:
    direct = _safe_float(mapping.get(canonical_key))
    if direct is not None:
        return direct
    dated: list[tuple[tuple[int, str], float]] = []
    for k, v in mapping.items():
        m = re.fullmatch(dated_pattern, str(k))
        if m:
            num = _safe_float(v)
            if num is not None:
                stamp = m.group(1)
                dated.append(((len(stamp), stamp), num))
    if dated:
        dated.sort(key=lambda item: item[0], reverse=True)
        return dated[0][1]
    return None


def _resolve_etf_cn(gold_snap: dict[str, Any]) -> dict[str, Any]:
    direct = gold_snap.get("etf_cn")
    if isinstance(direct, dict) and direct:
        return direct
    dated: list[tuple[tuple[int, str], dict[str, Any]]] = []
    for k, v in gold_snap.items():
        m = re.fullmatch(r"etf_cn_(\d+)", str(k))
        if m and isinstance(v, dict) and v:
            stamp = m.group(1)
            dated.append(((len(stamp), stamp), v))
    if dated:
        dated.sort(key=lambda item: item[0], reverse=True)
        return dated[0][1]
    return {}


def _render_flagship_web_shelf(
    stock_counts: dict[str, int],
    *,
    a_etf_count: int = 0,
    etf_total: int = 0,
    channel_count: int = 0,
) -> str:
    """Render the pure-web evergreen flagship shelf (zero PDF/Word links)."""
    a_pool = stock_counts.get("a-share", 0)
    hk_pool = stock_counts.get("hk-stock", 0)
    us_pool = stock_counts.get("us-stock", 0)
    eff_etf_cnt = etf_total if etf_total > 0 else a_etf_count
    a_etf_lbl = f"{eff_etf_cnt} 只重点 ETF" if eff_etf_cnt > 0 else "核心宽基与红利 ETF"
    ch_lbl = f"{channel_count} 大多元渠道" if channel_count > 0 else "多元合规渠道"
    specs = [
        ("gold", "🥇 黄金跨世纪周期主报告（1971–2030）", "宏观框架 · 四步买金红绿灯 · 中国全渠道税费与回购实操", "reports/gold.html", "daily/gold-latest.html"),
        ("a-share", f"🇨🇳 中国 A 股跨周期全景手册（{a_pool} 股）", f"七维大盘体检 · {a_etf_lbl} · {ch_lbl}与全行业龙头", "reports/a-share.html", "daily/a-share-latest.html"),
        ("hk-stock", f"🇭🇰 中国香港股市跨周期全景手册（{hk_pool} 股）", "联汇双通道水位 · 港股三通道 ETF 税制 · AH 折溢价套利", "reports/hk-stock.html", "daily/hk-stock-latest.html"),
        ("us-stock", f"🇺🇸 美国股市跨周期全景手册（{us_pool} 股）", "政策市五维雷达 · 美股与爱尔兰 UCITS ETF · 11 板块防弹衣", "reports/us-stock.html", "daily/us-stock-latest.html"),
    ]
    cards: list[str] = []
    for mk, title, desc, web_href, daily_href in specs:
        cards.append(
            f'<div class="home-flagship-card">'
            f'<div class="dl-name">{esc(title)}</div>'
            f'<div class="sec-sub">{esc(desc)}</div>'
            f'<div class="dl-links">'
            f'<a class="dl-link dl-badge-web" href="{web_href}">阅读网页版手册 →</a>'
            f'<a class="btn btn-sm" href="{daily_href}">最新日报</a>'
            f"</div>"
            f"</div>"
        )
    return "".join(cards)


# ==============================================================================
# 6A. BEGINNER-FRIENDLY CHANNEL METADATA HELPERS (Graceful Fallback for 8/12 Ch)
# ==============================================================================

_BUCKET_ORDER: tuple[str, ...] = ("liquid", "stable", "growth", "protection")
_BUCKET_META: dict[str, tuple[str, str]] = {
    "liquid": ("💧 活钱（0–6月）", "💧 活钱"),
    "stable": ("🛡️ 稳钱（1–3年）", "🛡️ 稳钱"),
    "growth": ("🌱 长钱（3–5年+）", "🌱 长钱"),
    "protection": ("🏥 保障与超长锁息", "🏥 保障锁息"),
}
_DEFAULT_BUCKET_BY_ID: dict[str, str] = {
    "reverse_repo": "liquid",
    "large_cds": "stable",
    "fx_deposits_wm": "stable",
    "bonds": "stable",
    "funds_wm": "stable",
    "savings_insurance": "protection",
    "tax_advantaged_accounts": "protection",
    "qdii_mrf": "growth",
    "convertible_bonds": "growth",
    "c_reits": "growth",
    "commodity_etfs": "growth",
    "private_funds_trust": "growth",
}

_DEFAULT_CHANNEL_BEGINNER: dict[str, dict[str, Any]] = {
    "reverse_repo": {
        "risk_stars": 1,
        "one_liner": "随存随用的零钱包升级版，把券商或活期闲钱放进低风险工具稳赚日息。",
        "today_alert": "逆回购务必点「卖出」借钱；周五借 1 天期仅计 1 天息，周四买才吃 3 天息。",
        "short_threshold": "100–1,000 元 · 随时可用",
        "what_it_is": "涵盖国债逆回购、货币基金、场内短融 ETF 与同业存单 AAA 等超低波现金管理工具，专为日常备用金和炒股待机现金设计。",
        "how_it_earns": "把短期闲钱借给国家信用担保的机构或银行，按天收取稳定利息，季末或节前资金紧张时常有脉冲加息。",
        "worst_case": "标准国债逆回购由交易所担保几乎零违约；货基与短融 ETF 历史回撤极微，主要风险是忘记周五计息规则白白闲置两天。",
        "steps": [
            ("1. 选对入口 App", "股票账户闲钱在正规券商 App 搜国债逆回购或短融 ETF（511360）；银行卡零钱在支付宝或手机银行选头部货基或同业存单 AAA。"),
            ("2. 查门槛与时间", "沪深逆回购均已统一 1,000 元起，佣金低至十万分之一；上午 09:30–10:30 与 14:30 前利率往往优于尾盘。"),
            ("3. 下单防呆动作", "逆回购操作方向必点「卖出」；周四借 1 天期享周末 3 天息，周五闲钱改放 T+0 短融 ETF；到期次交易日可买股、再下一日才可提现。"),
        ],
        "picks": ["周四与节前倒数第 2 日国债逆回购（GC001 / R-001）", "券商账户活钱停泊池：短融 ETF（511360）", "场外低波升级：同业存单 AAA 指数基金"],
        "avoids": ["周五或节前最后一个交易日盲目做 1 天期逆回购", "把次日必须提现交房租的救命钱锁进 T+2 才能提现的逆回购"],
        "faq": [
            ("做国债逆回购点「买入」还是「卖出」？", "务必点「卖出」，意思是把你的钱借给需要资金的机构收取利息，很多券商界面也直接标作「借出」。"),
            ("为什么说到期后「可用」不等于「可取」？", "T+1 日开盘钱已回到证券账户，能立刻买股票或 ETF（可用），但要等到 T+2 日才能转回银行卡（可取）。"),
        ],
    },
    "large_cds": {
        "risk_stars": 1,
        "one_liner": "有国家 50 万存款保险兜底的保本钱袋子，适合 1–3 年确定不用的稳健资金。",
        "today_alert": "单家独立法人银行本息合计严控 50 万以内；二手接盘存单绝不可直接提前支取。",
        "short_threshold": "定存 50 元 / 存单 20 万起",
        "what_it_is": "包括普通定期存款、大额存单、通知存款与结构性存款，属于真正受存款保险保障的银行表内保本存款。",
        "how_it_earns": "银行按约定固定利率支付利息，个人存款利息暂免个人所得税；大额存单还支持在官方 App 转让专区提前变现。",
        "worst_case": "单家银行 50 万元本息内由存款保险全额保障；主要亏损坑是直接提前支取惨跌至活期利率，或二手接盘后提前支取造成本金实亏。",
        "steps": [
            ("1. 选对入口 App", "在国有大行、股份制银行或本地头部城商行官方手机银行「存款 / 大额存单」专区直接办理，不找中介代抢。"),
            ("2. 查门槛与条款", "普通定存几十元起，大额存单多为 20 万元起；下手前务必确认是否支持「官方 App 零费转让」以及是否禁止二次转让。"),
            ("3. 分散与比价", "对比同期储蓄国债与不同银行利率；单家独立法人银行下所有存款本息实操控制在 45–47 万以内，留出利息缓冲。"),
        ],
        "picks": ["3 年期股份制或头部城商行可转让大额存单", "20 万以下资金选正规银行特色定期存款或改配储蓄国债"],
        "avoids": ["把超过 50 万存款全部集中在同一家银行的不同支行", "二手转让专区接盘后急用钱直接向银行提前支取（只退原票面本金+活期）"],
        "faq": [
            ("同一家银行办两张卡，每张都保 50 万吗？", "不是。50 万元限额按「同一存款人 × 同一独立法人银行」所有支行网点的全部存款本息合并计算。"),
            ("大额存单利息要扣 20% 个人所得税吗？", "不需要。中国大陆对个人储蓄存款和大额存单利息暂免征收个人所得税。"),
        ],
    },
    "fx_deposits_wm": {
        "risk_stars": 2,
        "one_liner": "适合已有存量美元或港元现汇的持币人原币生息，严防人民币换汇赚息亏汇。",
        "today_alert": "人民币新换汇买外币定存须先算汇率波动账，绝不违规拆借个人 5 万美元额度。",
        "short_threshold": "100 美元起 · 锁期定存",
        "what_it_is": "在境内正规银行直接办理的美元、港元等外币定期存款与低波外币理财，面向已有外汇储备或留学旅游刚需家庭。",
        "how_it_earns": "赚取境外货币无风险利率差，但换回人民币时的最终收益 = 外币利息 + 汇率涨跌。",
        "worst_case": "外币存款在境内也受 50 万人民币等值存保上限约束，但外币理财不保本；若人民币显著升值，利息可能被汇兑损失全部吞噬甚至倒亏。",
        "steps": [
            ("1. 选对入口 App", "在持有外币牌照的国有大行、股份行或外资行官方手机银行「外币存款 / 外币理财」栏目办理。"),
            ("2. 分清资金来源", "已有存量美元现汇优先原币定存避免反复换汇点差；若用人民币购汇，务必遵守每年 5 万美元个人便利化额度合规用途。"),
            ("3. 核算综合回报", "比较外币定存利率、银行结售汇点差与未来用汇时间，绝不为了账面息差忽视双向汇率波动。"),
        ],
        "picks": ["存量美元现汇直配正规银行中短期美元定存", "留学/境外消费刚需资金按到期日匹配外币定存"],
        "avoids": ["用人民币盲目换汇追高息外币存款却忽略人民币升值汇损", "轻信代购额度、地下换汇等触碰外汇合规红线的操作"],
        "faq": [
            ("为什么看着外币利率高，换回人民币反而亏了？", "因为外币收益按外币计价，如果持有期间人民币对美元大幅升值，换回人民币时的汇率折损可能大于拿到的利息。"),
            ("外币存款和外币理财都受 50 万存款保险保护吗？", "只有银行表内「外币存款」按折合人民币合并计入 50 万存保上限，净值化外币理财产品不在存款保险保障范围内。"),
        ],
    },
    "bonds": {
        "risk_stars": 1,
        "one_liner": "把钱借给国家或优质大企业稳吃利息，是普通人替代低息定存的稳钱压舱石。",
        "today_alert": "30 年超长国债久期近 20 年、波动像股票，新手严禁把它当保本存款重仓。",
        "short_threshold": "100 元起 · 债基ETF T+0",
        "what_it_is": "核心包含国家发行的储蓄国债，以及在券商账户像买股票一样交易的短融、国债、政金债和高等级公司债/科创债 ETF。",
        "how_it_earns": "主要靠每天稳定累积的债券票息，外加市场降息时债券价格上涨带来的资本利得。",
        "worst_case": "储蓄国债持有到期稳保本息；中短债 ETF 常规回撤约 0.5%–1.5%；但 30 年国债 ETF 利率反弹时可能出现 5%–10% 回撤。",
        "steps": [
            ("1. 选对入口 App", "储蓄国债用六大行或主流股份行官方手机银行；债券 ETF（如 511360、511260、551500）用正规证券公司股票 App。"),
            ("2. 查门槛与规则", "储蓄国债 100 元起、多在每月 10 日开售；债券 ETF 约百元至千元起，普通 A 股账户免印花税且支持 T+0 当日买卖。"),
            ("3. 下单防呆动作", "盘中核对参考净值，溢价超 0.2% 不追高；买公司债优先借道 ETF 分散违约风险并留意底层税负差异，超长债严控仓位。"),
        ],
        "picks": ["3年期 / 5年期电子式储蓄国债（免个税稳保本）", "短融 ETF（511360）与银行间中短久期利率债 ETF", "高等级科创债 / 基准做市公司债 ETF（分散配置）"],
        "avoids": ["把 30 年超长国债 ETF 当保本存款满仓买入", "个人直接重仓单只高息民营信用债（既扣 20% 利息税又有违约风险）"],
        "faq": [
            ("买债券 ETF 会亏本金吗？", "短融 ETF 极少回撤；中长久期债券 ETF 净值随利率波动，短期可能小幅浮亏，持有拿息通常可逐步修复；30 年国债则属高波动工具。"),
            ("为什么储蓄国债提前取会扣利息？", "储蓄国债鼓励持有到期，不满 6 个月兑取无息且扣 0.1% 手续费，满 6 个月后按档扣除相应天数利息。"),
        ],
    },
    "funds_wm": {
        "risk_stars": 2,
        "one_liner": "门槛低至 1 元的净值化理财工具箱，买前务必分清「保本存款」和「波动净值」。",
        "today_alert": "银行理财全面真净值化且存在破净波动，切勿把业绩比较基准当承诺保本利率。",
        "short_threshold": "1–1,000 元 · 申赎灵活",
        "what_it_is": "涵盖公募短债/纯债、固收+、多资产 ETF-FOF、真净值银行理财以及持牌基金投顾组合，适合习惯用银行或三方平台打理资金的人群。",
        "how_it_earns": "由专业团队打包投资债券、存单或少量权益资产，靠底层利息与资产增值推升每日净值。",
        "worst_case": "债市回调或股市下跌时，银行理财和固收+可能跌破 1 元本金线（破净），部分含权较高的固收+回撤可达 3%–8%。",
        "steps": [
            ("1. 选对入口 App", "在官方手机银行、天天基金、蚂蚁财富或持牌券商 App 选购，优先查看 2026 销售费改后的透明低费份额。"),
            ("2. 核对关键参数", "先看底层持仓和历史回撤，再核对本份额、持有期和渠道对应的实际费用。"),
            ("3. 避开 7 天惩罚费", "无论 A 类还是 C 类公募基金，持有不满 7 天赎回通常硬扣 1.5% 惩罚费；选产品按用钱周期匹配，不盲追榜单短期冠军。"),
        ],
        "picks": ["头部低费同业存单 AAA 与高等级短债基金", "费率透明的多资产平衡型 ETF-FOF 或持牌稳健投顾"],
        "avoids": ["把近期宣传高业绩基准的银行固收+理财当保本存款买", "买入公募基金不满 7 天就频繁赎回白交 1.5% 惩罚费"],
        "faq": [
            ("基金 A 类和 C 类怎样比较？", "合计申购费、运营费、销售服务费与赎回费。适用份额持有超过一年后，停止继续收取销售服务费。前一年费用看基金合同和购买渠道。"),
            ("理财显示 R2 中低风险为什么还会亏钱？", "R2 代表波动较小而非保本。债市利率突然反弹或底层信用债估值调整时，净值化理财同样会出现阶段性浮亏。"),
        ],
    },
    "savings_insurance": {
        "risk_stars": 2,
        "one_liner": "适合 10 年以上绝对不动的闲钱提前锁息，前 5 年退保本金亏损极大必须量力而行。",
        "today_alert": "看懂白纸黑字的「保证现价 IRR」而非夸大演示收益，绝不拿 3–5 年内要用的钱买储蓄险。",
        "short_threshold": "数千元至数万元/年 · 锁定 10 年+",
        "what_it_is": "包括增额终身寿险、养老年金险与分红型储蓄险，属于用长期流动性换取合同锁定复利与身故/长寿现金流安排的保险合同。",
        "how_it_earns": "传统险按合同写死的现金价值复利增长；分红险由较低的保证利率加不保证的险企经营分红构成。",
        "worst_case": "保险合同前期扣除渠道与保障成本，前 3–7 年现金价值显著低于已交保费，中途急用钱退保会直接亏损 20%–50% 本金。",
        "steps": [
            ("1. 先配保障再谈储蓄", "确认家庭已配齐基本医保、百万医疗与意外险后，再只拿 10 年以上绝对不用的闲钱考虑储蓄险。"),
            ("2. 自己算清真实 IRR", "向官方渠道索要现金价值表，重点核对第 10 年、20 年的保证复利（IRR）及险企历史分红实现率，不被「单利」话术误导。"),
            ("3. 用好犹豫期与验真", "只在持牌保险公司或正规持牌经纪渠道投保，保单在国家金融监管总局体系可查，15 天犹豫期内反悔可全额退保。"),
        ],
        "picks": ["资本充足、历史分红实现率稳健的头部险企合规产品", "10 年以上确定养老或教育金专款专用规划"],
        "avoids": ["用 3 年内可能买房结婚的钱买长年期储蓄险被迫中途退保", "把分红险演示上限当成保证收益，或轻信地下非合规境外保单"],
        "faq": [
            ("分红险宣传的演示收益一定能拿到吗？", "不一定。合同里只有「保证现金价值」写死必给，分红部分随保险公司投资收益浮动，可能低于演示水平甚至为 0。"),
            ("买完后悔了怎么办？", "签收保单后通常有 15 天犹豫期可无损全退；过了犹豫期前几年退保只能退现金价值，往往大幅低于已交保费。"),
        ],
    },
    "tax_advantaged_accounts": {
        "risk_stars": 2,
        "one_liner": "国家给中高收入工薪族的合法节税专户，个税边际税率 20% 及以上最划算。",
        "today_alert": "领取时本息统一扣 3% 个税，0%–3% 低税档人群切勿盲目锁进个人养老金账户。",
        "short_threshold": "每年上限 1.2 万元 · 锁定至退休",
        "what_it_is": "以个人养老金账户（每年最高缴存 1.2 万元）和税优健康险为核心的法定税收优惠账户，可在年度个税汇算时直接抵扣应纳税所得额。",
        "how_it_earns": "「立刻省下的个税 + 账户内 Y 份额基金/养老储蓄/国债/商业养老保险的长期复利」，且 Y 份额管理费普遍打五折。",
        "worst_case": "资金原则上锁定至退休（大病、长期失业、低保等法定情形除外），且未来领取时连本带利扣 3% 个税；低税档缴存反而倒贴税差。",
        "steps": [
            ("1. 先查个人个税档位", "打开「个人所得税」App 查上年度综合所得边际税率：20% 及以上档高度推荐顶格参与，10% 档视流动需求而定，0%–3% 档暂不参与。"),
            ("2. 选低费正规开户行", "在支持丰富 Y 份额基金、养老储蓄国债与低费产品的头部银行开立唯一个人养老金资金账户。"),
            ("3. 买完别忘报税退税", "每年底前完成缴存并选好底层低费 Y 份额宽基/红利/固收+或国债，次年 3–6 月在个税 App 一键导入凭证办理退税。"),
        ],
        "picks": ["个税边际税率 ≥20% 人群顶格 1.2 万/年配置低费 Y 份额或养老储蓄国债", "符合需求的合规税优健康险（每年最高 2,400 元税前扣除）"],
        "avoids": ["年收入未达起征点或 3% 税档人群跟风开户缴存白交 3% 领取税", "只把钱存进养老金账户当活期放着不动，白白浪费长期复利"],
        "faq": [
            ("为什么说 3% 税档买个人养老金不划算？", "因为你现在只省了 3% 的税，退休领取时连本带利都要交 3% 的税，资金被锁几十年却几乎没有净节税优势。"),
            ("中间遇到重大困难急用钱能提前取吗？", "可以。除达到退休年龄外，遇到完全丧失劳动能力、大病重疾支出、长期领取失业金或低保等法定情形均可按规申请提前领取。"),
        ],
    },
    "qdii_mrf": {
        "risk_stars": 3,
        "one_liner": "合法不出境就能配置全球股债的合规桥梁，核心纪律是「避开高溢价、选对冲累计」。",
        "today_alert": "严禁在场内追买溢价超 3% 或停牌提示的跨境基；香港互认基金需分别核对留在基金内的累计收益、实际分配的代扣和份额转让差价的暂免条件，也要核算汇率与对冲成本。",
        "short_threshold": "10–100 元起（理财通 2.0 需大湾区资格）",
        "what_it_is": "包括场内外 QDII 基金、香港北向互认基金（MRF）以及粤港澳大湾区跨境理财通，全部在国家合规框架内投资海外股票或债券。",
        "how_it_earns": "分享海外优质企业盈利或高评级美元债票息，降低单一市场波动对家庭资产的冲击。",
        "worst_case": "场内高溢价接盘在情绪退潮或 LOF 退市时溢价直接清零；未锁汇美元债遇到人民币大幅升值可能赚息亏汇。",
        "steps": [
            ("1. 选对无溢价通道", "想投海外宽基且场内溢价高时，改在支付宝/银行用场外 QDII 联接按收盘净值定投；想买海外稳健债基在银行/三方搜开放的香港互认基金（MRF）。"),
            ("2. 核对三项必查项", "查实时参考净值溢价（>2%–3% 不买）、查 MRF 是否为「人民币对冲 + 累计份额」、查当前是否开放申购及单日限额。"),
            ("3. 严守合规与税务", "MRF 选累计份额可合法免除 20% 现金派息个税；不触碰非法地下换汇，离岸投资收益依法合规申报。"),
        ],
        "picks": ["开放申购的「人民币对冲 + 累计」香港互认债基（968082 / 968021）", "低溢价非美 QDII（如日股/亚洲）或场外零溢价联接定投"],
        "avoids": ["场内追买两位数溢价及频繁停牌的纳指/标普 ETF 或高溢价 QDII-LOF", "买 MRF 月派息份额白扣 20% 个税，或买已暂停申购的基金代码"],
        "faq": [
            ("为什么一定要选香港互认基金的「累计份额」？", "内地买香港互认基金买卖价差暂免个税，但现金分红会强制代扣 20% 个税；累计份额把利息滚进净值，能合法避开这笔税损。"),
            ("场外美股联接每天限购几十上百元怎么投？", "可以把同一指数下不同基金公司的低费联接基金分散定投拼单，既享受零场内溢价又天然摊薄成本。"),
        ],
    },
    "convertible_bonds": {
        "risk_stars": 3,
        "one_liner": "「进可攻、退可守」的股债混合工具，新手直接选零门槛投资级转债 ETF 最省心。",
        "today_alert": "违约刚兑已打破！个券严防低评级问题债、强赎「Z 标识」与到期停牌误点转股。",
        "short_threshold": "ETF 百元零门槛 / 个券需 10 万+2 年",
        "what_it_is": "上市公司发行的既像债券能到期还本付息、又能按约定价格换成股票的混合品种，场内有 T+0 可转债 ETF 可零门槛一键打包。",
        "how_it_earns": "股市跌时靠债券面值托底抗跌，股市涨时跟着正股上涨赚取弹性差价。",
        "worst_case": "个券已打破刚兑，低评级或退市边缘转债可能大跌超 50%；忘记处理强赎通知会被按约 100.5 元强行买回瞬间大亏。",
        "steps": [
            ("1. 选对入口与品种", "普通人无须凑 10 万元权限，直接在证券 App 买零门槛、T+0 的投资级转债 ETF（511180）或全市场转债 ETF（511380）。"),
            ("2. 进阶个券先开权限", "确需买卖单只转债或参与信用打新，需满足 20 日日均 10 万元资产 + 2 年交易经验在线开通权限。"),
            ("3. 盯紧三道排雷线", "个券坚持分散持仓、剔除 ST 与低评级；行情软件出现「Z」标识或强赎倒计时务必及时卖出或转股，已到期停牌券切勿误点转股。"),
        ],
        "picks": ["零门槛 T+0 自动排雷：上证投资级转债 ETF（511180）", "高流动性低费宽基：中证可转债 ETF（511380）"],
        "avoids": ["为了高表面到期收益率去赌低评级、退市边缘问题转债", "忽略强赎最后交易日被百元强赎，或在到期停牌期间误操作转股"],
        "faq": [
            ("没有 10 万元资金可以买可转债吗？", "买单只可转债需要 10 万资产加 2 年经验，但买场内可转债 ETF（511180、511380）零门槛、几百元就能 T+0 买卖且自动分散风险。"),
            ("可转债打新还会稳赚吗？", "信用打新中签率较低但中签前零占用资金，上市首日仍具正期望，但需核对评级与溢价率，切忌盲目高价追涨上市后的次新券。"),
        ],
    },
    "c_reits": {
        "risk_stars": 3,
        "one_liner": "几百元就能当商场、保租房或算力机房的「包租公」，买前必分清产权与经营权两类。",
        "today_alert": "特许经营权 REITs 到期归零、高分派里混有本金；二级成交较薄务必挂限价单。",
        "short_threshold": "几百元起 · 线上零门槛开通",
        "what_it_is": "把成熟收费基础设施或商业不动产打包上市的公募基金，强制将绝大部分可供分配现金流分红给持有人。",
        "how_it_earns": "靠底层物业租金或收费公路车流收取稳定现金分红，加上资产基本面改善带来的价格重估。",
        "worst_case": "价格波动接近股票，历史回调幅度可达 10%–25%；特许经营权类若只看表面高分派不看真实 IRR，可能越分越亏总账。",
        "steps": [
            ("1. 开通权限或选场外", "A 股证券账户线上零门槛即可开通 REITs 权限；没股票账户也可在支付宝/银行买场外 REITs 指数基金（如 028272/028273）。"),
            ("2. 先分清产权与经营权", "产权类（保租房、消费商场、IDC 数据中心）看中长期出租率与分派率；特许经营权类（高速、能源）必须看中债真实 IRR。"),
            ("3. 分批限价控制仓位", "公募 REITs 日成交较薄，下单务必挂限价单防滑点，作为卫星仓位控制在总组合 10% 以内，不盲目跟风打新。"),
        ],
        "picks": ["一键分散全市场：场外中证 REITs 全收益指数基金", "现金流稳健的头部保租房、核心消费商业与高收缴率 IDC 产权类 REITs"],
        "avoids": ["把高速公路 REITs 的表面高分派率当成永续高股息重仓买入", "大额市价扫单吃出滑点，或在解禁高峰盲目追高"],
        "faq": [
            ("产权类和特许经营权类 REITs 最大区别是什么？", "产权类底层物业类似长期收租资产；特许经营权类到期要无偿移交政府、净值归零，所以每年高额分派里很大一部分是把你自己的本金还给你。"),
            ("买公募 REITs 分红要交个人所得税吗？", "现行规则下，个人二级市场买卖价差与公募 REITs 现金分红暂免征收个人所得税。"),
        ],
    },
    "commodity_etfs": {
        "risk_stars": 4,
        "one_liner": "与股票债市走势关联度极低的抗通胀卫星工具，用普通股票户即可免期货门槛参与。",
        "today_alert": "严守黄金红灯停暂不新买纪律；坚决避开两位数高溢价及面临退市回归净值的商品 LOF。",
        "short_threshold": "几百元起 · 场内 T+0",
        "what_it_is": "直接跟踪豆粕、有色金属、能源化工等大宗商品期货价格的场内 ETF，为组合提供独立的抗通胀对冲能力。",
        "how_it_earns": "在通胀抬头或商品供需偏紧时上涨；其中常年近贵远便宜（贴水）的品种还能在期货换月时持续赚取正展期收益。",
        "worst_case": "大宗商品周期性强、波动剧烈，单品种回撤可达 15%–45%；高溢价商品 LOF 更可能遭遇净值下跌与溢价蒸发双杀。",
        "steps": [
            ("1. 选对纯期货 ETF", "在证券 App 优先查看场内直持期货合约的纯商品 ETF（如豆粕 159985、有色 159980、能化 159981），免 10 万/50 万期货门槛。"),
            ("2. 严查溢价与展期结构", "下单前必看参考净值溢价与合约升贴水结构；警惕高费率、高溢价且受退市新规约束的场内商品 LOF。"),
            ("3. 严控卫星仓位上限", "非金大宗商品仅作组合抗通胀卫星，单品种及合计仓位严控在 5%–10% 以内，切忌急涨后重仓追高。"),
        ],
        "picks": ["常年贴水正展期、与股债低相关的豆粕期货 ETF（159985）", "通胀周期对冲观察：有色金属期货 ETF（159980）"],
        "avoids": ["追买两位数溢价的白银 LOF（161226）或升水磨损的原油 LOF", "单只商品重仓押注，或在黄金红灯停期违规借道新买黄金"],
        "faq": [
            ("为什么同样是大宗商品，有的长期涨、有的长期磨净值？", "期货合约到期必须换月：远月比近月便宜（贴水）时换月能多买份额赚正展期；远月比近月贵（升水，如原油常态）则每次换月都在悄悄扣血。"),
            ("普通人买商品 ETF 会像炒期货一样爆仓吗？", "不会。商品期货 ETF 是无杠杆全额保证金运作，闲置保证金还会买国债存单生息，不会发生期货爆仓倒欠钱。"),
        ],
    },
    "private_funds_trust": {
        "risk_stars": 4,
        "one_liner": "面向 300 万金融资产合格投资者的进阶对冲工具，门槛高、锁定期长、新手无须碰。",
        "today_alert": "按产品规则核验合格投资者身份、单只产品最低认购金额、备案和托管安排。",
        "short_threshold": "300 万资产认证 · 单笔 100 万起",
        "what_it_is": "面向法定合格投资者的合规私募证券基金（如多核量化 CTA、股票多头/指增）与净值化标品信托，提供公募无法实现的危机负相关对冲策略。",
        "how_it_earns": "依赖管理人投研与多策略量化模型获取超额收益或危机期趋势保护，通常收固定管理费加业绩提成。",
        "worst_case": "存在 6–12 个月锁定期或固定开放日，流动性弱；选错管理人或误碰违规非标/高杠杆雪球可能出现大幅本金亏损。",
        "steps": [
            ("1. 核实自身合格资质", "依法需满足家庭金融资产 ≥300 万元或近 3 年年均收入 ≥50 万元，且单只私募起投 100 万元（标品信托多为 30 万–100 万元起）。"),
            ("2. 四道官方系统验真", "付款前务必在中基协、中国信登等官方平台核实机构牌照与产品备案，确认资金打入银行/券商独立托管专户，严拒私账与口头保本。"),
            ("3. 严控仓位与策略分散", "用好 24 小时投资冷静期与回访确认，优先分散至多核量化 CTA 等低相关策略，远离非标政信定融与超限雪球结构。"),
        ],
        "picks": ["中基协备案齐全、券商/大行托管的头部多核量化 CTA", "底层为公开标准化债股资产的净值化标品信托"],
        "avoids": ["资金未达合格门槛硬凑拼单代持", "轻信飞单保本承诺、非标政信定融或将资金转入非托管个人/公司账户"],
        "faq": [
            ("没有 300 万可以找朋友拼单买私募吗？", "绝对不可以。拼单代持违反合格投资者监管红线，一旦发生纠纷或管理人风险，实际出资人权益很难受到法律保护。"),
            ("为什么标品信托和以前的非标信托不一样？", "标品信托底层投资公开市场标准化债券、基金等，每日/每周按净值波动且信息更透明；非标城投/地产信托则缺乏流动性且刚兑已彻底打破。"),
        ],
    },
}


def _normalize_money_bucket(ch: dict[str, Any]) -> str:
    raw = str(ch.get("money_bucket") or "").strip().lower()
    if raw in ("liquid", "cash", "活钱"):
        return "liquid"
    if raw in ("stable", "steady", "稳钱"):
        return "stable"
    if raw in ("growth", "long", "long_term", "长钱"):
        return "growth"
    if raw in ("protection", "insurance", "lock", "tax", "保障"):
        return "protection"
    cid = str(ch.get("id") or "").strip()
    if cid in _DEFAULT_BUCKET_BY_ID:
        return _DEFAULT_BUCKET_BY_ID[cid]
    cat = str(ch.get("category") or "").strip().lower()
    if cat == "cash":
        return "liquid"
    if cat in ("fixed_income", "deposits"):
        return "stable"
    if cat in ("insurance", "tax_advantaged"):
        return "protection"
    return "growth"


def _is_hnw_channel(ch: dict[str, Any]) -> bool:
    if ch.get("high_net_worth_only") is True:
        return True
    cid = str(ch.get("id") or "").strip()
    return cid == "private_funds_trust"


def _channel_min_tier(ch: dict[str, Any]) -> str:
    """Return minimum capital tier token ('1w', '20w', '300w') for homepage beginner capital selector."""
    if _is_hnw_channel(ch):
        return "300w"
    raw = str(ch.get("min_amount_tier") or "").strip().lower()
    if raw in ("1w", "20w", "300w"):
        return raw
    cid = str(ch.get("id") or "").strip()
    if cid == "qdii_mrf":
        return "1w"
    if cid == "large_cds":
        return "20w"
    thr = str(ch.get("min_threshold") or "")
    if "20 万" in thr or "20万" in thr:
        return "20w"
    return "1w"


def _channel_risk_stars(ch: dict[str, Any]) -> int:
    val = ch.get("risk_stars")
    if isinstance(val, int) and 1 <= val <= 5:
        return val
    cid = str(ch.get("id") or "").strip()
    if cid in _DEFAULT_CHANNEL_BEGINNER:
        return int(_DEFAULT_CHANNEL_BEGINNER[cid]["risk_stars"])
    rl = str(ch.get("risk_level") or "")
    if "极低" in rl:
        return 1
    if "中低" in rl or "低至" in rl:
        return 2
    if "中高" in rl:
        return 3
    if "高" in rl:
        return 4
    return 2


def _fmt_stars(n: int) -> tuple[str, str]:
    clamped = max(1, min(5, int(n)))
    lbls = {1: "极低波", 2: "中低波", 3: "中等波", 4: "高波动", 5: "极高波"}
    return ("★" * clamped + "☆" * (5 - clamped)), lbls[clamped]


def _short_yield_for_card(yield_range: str) -> str:
    txt = str(yield_range or "").strip()
    if not txt:
        return "详见详情页"
    first = re.split(r"[｜|]", txt, maxsplit=1)[0].strip()
    if len(first) <= 28:
        return first
    before_paren = re.split(r"[（(]", first, maxsplit=1)[0].strip()
    if before_paren and 4 <= len(before_paren) <= 28:
        return before_paren
    cand = before_paren if len(before_paren) >= 8 else first
    punct_matches = list(re.finditer(r"[，、；：·\s]", cand[:27]))
    if punct_matches and punct_matches[-1].start() >= 8:
        cut = cand[: punct_matches[-1].start()].rstrip("，、；：· （(")
    else:
        cut = re.sub(r"[（(][^）)]*$", "", cand[:26]).strip()
        cut = re.sub(r"[+\-−~–—]?[0-9]+(?:\.[0-9]*)?%?$", "", cut).rstrip("，、；：· （(")
    return (cut or cand[:24].rstrip("，、；：· （(")) + "等"


def _short_threshold_for_card(ch: dict[str, Any]) -> str:
    cid = str(ch.get("id") or "").strip()
    custom = str(ch.get("short_threshold") or "").strip()
    if custom:
        return custom
    if cid in _DEFAULT_CHANNEL_BEGINNER:
        return str(_DEFAULT_CHANNEL_BEGINNER[cid]["short_threshold"])
    thr = str(ch.get("min_threshold") or "").strip()
    first = re.split(r"[（(；;｜|]", thr, maxsplit=1)[0].strip()
    return first or "详见详情页"


def _channel_one_liner(ch: dict[str, Any]) -> str:
    custom = str(ch.get("beginner_one_liner") or "").strip()
    if custom:
        return custom
    cid = str(ch.get("id") or "").strip()
    if cid in _DEFAULT_CHANNEL_BEGINNER:
        return str(_DEFAULT_CHANNEL_BEGINNER[cid]["one_liner"])
    summary = str(ch.get("summary") or "").strip()
    if summary:
        first_sent = re.split(r"[。！？]", summary, maxsplit=1)[0].strip()
        if first_sent:
            return first_sent + "。"
    return str(ch.get("badge") or ch.get("name") or "")


def _channel_today_alert(ch: dict[str, Any]) -> str:
    custom = str(ch.get("today_alert") or "").strip()
    if custom:
        return custom
    cid = str(ch.get("id") or "").strip()
    if cid in _DEFAULT_CHANNEL_BEGINNER:
        return str(_DEFAULT_CHANNEL_BEGINNER[cid]["today_alert"])
    avoid = str(ch.get("avoid_if") or "").strip()
    if avoid:
        first_sent = re.split(r"[。！？；]", avoid, maxsplit=1)[0].strip()
        if first_sent:
            return first_sent + "。"
    return str(ch.get("status_tag") or "下单前核对费率与风险条款。")


def _channel_explainer(ch: dict[str, Any]) -> dict[str, str]:
    raw = ch.get("beginner_explainer")
    cid = str(ch.get("id") or "").strip()
    fb = _DEFAULT_CHANNEL_BEGINNER.get(cid, {})
    if isinstance(raw, dict):
        what = str(raw.get("what_it_is") or "").strip()
        earns = str(raw.get("how_it_earns") or "").strip()
        worst = str(raw.get("worst_case") or "").strip()
        if what or earns or worst:
            return {
                "what_it_is": what or str(fb.get("what_it_is") or ch.get("summary") or ""),
                "how_it_earns": earns or str(fb.get("how_it_earns") or ch.get("yield_range") or ""),
                "worst_case": worst or str(fb.get("worst_case") or ch.get("risk_level") or ""),
            }
    return {
        "what_it_is": str(fb.get("what_it_is") or ch.get("summary") or ""),
        "how_it_earns": str(fb.get("how_it_earns") or ch.get("yield_range") or ""),
        "worst_case": str(fb.get("worst_case") or ch.get("risk_level") or ""),
    }


def _channel_steps(ch: dict[str, Any]) -> list[tuple[str, str]]:
    raw = ch.get("how_to_buy_steps")
    out: list[tuple[str, str]] = []
    if isinstance(raw, list) and raw:
        for idx, item in enumerate(raw[:4], start=1):
            if isinstance(item, dict):
                st = str(item.get("step") or item.get("title") or f"第 {idx} 步").strip()
                dt = str(item.get("detail") or item.get("text") or item.get("desc") or "").strip()
                if dt:
                    out.append((st, dt))
            elif isinstance(item, str) and item.strip():
                out.append((f"第 {idx} 步", item.strip()))
    if out:
        return out
    cid = str(ch.get("id") or "").strip()
    fb = _DEFAULT_CHANNEL_BEGINNER.get(cid, {})
    fb_steps = fb.get("steps")
    if isinstance(fb_steps, list) and fb_steps:
        return [(str(s), str(d)) for s, d in fb_steps]
    return [
        ("1. 选对合规入口", "通过持牌银行、正规证券公司或持牌公募代销平台办理，拒绝任何非正规私下转账。"),
        ("2. 核对门槛与费率", f"起投门槛：{ch.get('min_threshold') or '详见产品公告'}；确认费率与税费规则后再操作。"),
        ("3. 严守风控与仓位", f"流动性特征：{ch.get('liquidity') or '详见产品条款'}；按资金使用期限匹配仓位，不盲目追高。"),
    ]


def _channel_picks_avoids(ch: dict[str, Any]) -> tuple[list[str], list[str]]:
    def _norm_list(val: Any) -> list[str]:
        res: list[str] = []
        if isinstance(val, list):
            for x in val:
                if isinstance(x, str) and x.strip():
                    res.append(x.strip())
                elif isinstance(x, dict):
                    t = str(x.get("title") or x.get("name") or "").strip()
                    d = str(x.get("detail") or x.get("note") or "").strip()
                    comb = f"{t}：{d}" if (t and d) else (t or d)
                    if comb:
                        res.append(comb)
        return res

    picks = _norm_list(ch.get("beginner_picks"))
    avoids = _norm_list(ch.get("beginner_avoids"))
    cid = str(ch.get("id") or "").strip()
    fb = _DEFAULT_CHANNEL_BEGINNER.get(cid, {})
    if not picks:
        picks = list(fb.get("picks") or [])
    if not picks:
        for p in (ch.get("products") or [])[:3]:
            if isinstance(p, dict) and "高危" not in str(p.get("code", "")) and "高危" not in str(p.get("name", "")):
                picks.append(f"{p.get('name', '')}（{p.get('code', '')}）")
    if not avoids:
        avoids = list(fb.get("avoids") or [])
    if not avoids and ch.get("avoid_if"):
        avoids = [str(ch["avoid_if"]).strip()]
    return picks, avoids


def _channel_faq(ch: dict[str, Any]) -> list[tuple[str, str]]:
    raw = ch.get("beginner_faq")
    out: list[tuple[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                q = str(item.get("q") or item.get("question") or "").strip()
                a = str(item.get("a") or item.get("answer") or "").strip()
                if q and a:
                    out.append((q, a))
    if out:
        return out
    cid = str(ch.get("id") or "").strip()
    fb = _DEFAULT_CHANNEL_BEGINNER.get(cid, {})
    return [(str(q), str(a)) for q, a in (fb.get("faq") or [])]


def _render_channel_filter_panel(
    channels: list[dict[str, Any]],
    *,
    right_cta_html: str = "",
) -> str:
    """Render dynamic dual-mode filter bar: Beginner Money Buckets + Advanced Asset Categories."""
    total = len(channels)
    bucket_counts: dict[str, int] = defaultdict(int)
    cat_order: list[tuple[str, str]] = []
    cat_counts: dict[str, int] = defaultdict(int)
    seen_cats: set[str] = set()

    for ch in channels:
        if not isinstance(ch, dict):
            continue
        bk = _normalize_money_bucket(ch)
        bucket_counts[bk] += 1
        ck = str(ch.get("category") or "other").strip()
        clbl = str(ch.get("category_label") or ck).strip()
        cat_counts[ck] += 1
        if ck not in seen_cats:
            seen_cats.add(ck)
            cat_order.append((ck, clbl))

    bucket_btns = [f'<button type="button" class="filter-pill active" data-ch-bucket="all">全部 {total} 大渠道</button>']
    for bk in _BUCKET_ORDER:
        cnt = bucket_counts.get(bk, 0)
        if cnt > 0:
            full_lbl, _ = _BUCKET_META[bk]
            bucket_btns.append(
                f'<button type="button" class="filter-pill" data-ch-bucket="{bk}">{full_lbl} ({cnt})</button>'
            )

    cat_btns = ['<button type="button" class="filter-pill active" data-ch-cat="all">全部类型</button>']
    for ck, clbl in cat_order:
        cat_btns.append(
            f'<button type="button" class="filter-pill" data-ch-cat="{esc(ck)}">{esc(clbl)} ({cat_counts[ck]})</button>'
        )

    return (
        '<section class="filter-panel" aria-label="多元渠道双模式筛选">'
        '<div class="filter-row">'
        '<span class="filter-mode-label">按用钱时间（新手推荐）</span>'
        f'{"".join(bucket_btns)}'
        "</div>"
        '<div class="filter-row filter-divider">'
        '<span class="filter-mode-label">按资产类型（进阶）</span>'
        f'{"".join(cat_btns)}'
        "</div>"
        '<div class="screener-bar" style="margin:0;">'
        f'<strong id="ch-count" role="status">显示 {total} / {total} 大合规个人投资渠道</strong>'
        f"{right_cta_html}"
        "</div>"
        "</section>"
    )


_CHANNEL_ROLE_GROUPS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "cash_base",
        "第一层 · 活钱与现金底座",
        "随时调用 · 零亏本防守（逆回购 / 银行存款 / 外币定存）",
        ("reverse_repo", "large_cds", "fx_deposits_wm"),
    ),
    (
        "fixed_tax",
        "第二层 · 固收压舱与锁息保障",
        "1–10 年稳健票息 · 低波压舱（国债债基 / 理财公募 / 储蓄险）",
        ("bonds", "funds_wm", "savings_insurance"),
    ),
    (
        "crossborder_hybrid",
        "第三层 · QDII 跨境与股债增强卫星",
        "场内溢价 · 直销与支付宝限购 · 转债 · 实体租金（QDII互认 / 可转债 / 公募REITs）",
        ("qdii_mrf", "convertible_bonds", "c_reits"),
    ),
    (
        "alt_hnw",
        "第四层 · 税优养老、非金大宗与合格投资者渠道",
        "节税规划 · 滞胀战术仓 · 合格投资者门槛（个人养老金 / 非金商品排雷 / 私募信托）",
        ("tax_advantaged_accounts", "commodity_etfs", "private_funds_trust"),
    ),
)


def _render_channel_overview_cards(
    channels: list[Any], *, base_prefix: str = "", compact: bool = False
) -> str:
    """Render beginner-friendly overview cards grouped into 4 symmetric 3-card Layer-3 execution roles."""
    cards_by_id: dict[str, str] = {}
    ordered_ids: list[str] = []
    for idx, ch in enumerate(channels, start=1):
        if not isinstance(ch, dict):
            continue
        cid = str(ch.get("id", "")).strip()
        if not cid:
            continue
        num_str = _fmt_ch_num(ch.get("order"), idx)
        cat = str(ch.get("category", "fixed_income"))
        bucket = _normalize_money_bucket(ch)
        _, bucket_short = _BUCKET_META[bucket]
        min_tier = _channel_min_tier(ch)
        is_hnw = _is_hnw_channel(ch)
        tone = str(ch.get("status_tone", "blue")).strip().lower()
        if tone not in ("green", "blue", "amber", "red"):
            tone = "blue"
        href = f"{base_prefix}channels/{cid}.html"

        stars_str, stars_lbl = _fmt_stars(_channel_risk_stars(ch))
        one_liner = _channel_one_liner(ch)
        today_alert = _channel_today_alert(ch)
        short_yield = _short_yield_for_card(str(ch.get("yield_range", "")))
        short_thr = _short_threshold_for_card(ch)

        prods = [p for p in (ch.get("products") or []) if isinstance(p, dict)]
        rules = [r for r in (ch.get("rules_and_redlines") or []) if isinstance(r, str) and r.strip()]
        hnw_badge = '<span class="ch-hnw-badge">合格投资者</span>' if is_hnw else ""
        hnw_cls = " ch-hnw" if is_hnw else ""

        if compact:
            cards_by_id[cid] = (
                f'<article class="ch-overview-card ch-compact-card{hnw_cls}" id="ch-{esc(cid)}" '
                f'data-channel-cat="{esc(cat)}" data-channel-bucket="{esc(bucket)}" data-min-tier="{esc(min_tier)}">'
                f'<div class="ch-ov-top">'
                f'<div class="ch-ov-title-row">'
                f'<span class="ch-num">{esc(num_str)}</span>'
                f'<h3 class="ch-ov-title"><a href="{esc(href)}">{esc(ch.get("name", ""))}</a></h3>'
                f"</div>"
                f'<div class="ch-ov-badges">'
                f"{hnw_badge}"
                f'<span class="ch-status ch-tone-{tone}">{esc(ch.get("status_tag", ""))}</span>'
                f"</div>"
                f"</div>"
                f'<p class="ch-ov-oneliner">{esc(one_liner)}</p>'
                f'<div class="ch-ov-foot">'
                f'<span class="ch-ov-meta">{esc(short_yield)} · {esc(short_thr)}</span>'
                f'<a class="btn btn-sm" href="{esc(href)}">详情 →</a>'
                f"</div>"
                f"</article>"
            )
        else:
            cards_by_id[cid] = (
                f'<article class="ch-overview-card{hnw_cls}" id="ch-{esc(cid)}" '
                f'data-channel-cat="{esc(cat)}" data-channel-bucket="{esc(bucket)}" data-min-tier="{esc(min_tier)}">'
                f'<div class="ch-ov-top">'
                f'<div class="ch-ov-title-row">'
                f'<span class="ch-num">{esc(num_str)}</span>'
                f'<h3 class="ch-ov-title"><a href="{esc(href)}">{esc(ch.get("name", ""))}</a></h3>'
                f"</div>"
                f'<div class="ch-ov-badges">'
                f'<span class="ch-bucket-pill">{bucket_short}</span>'
                f"{hnw_badge}"
                f'<span class="ch-status ch-tone-{tone}">{esc(ch.get("status_tag", ""))}</span>'
                f"</div>"
                f"</div>"
                f'<p class="ch-ov-oneliner">{esc(one_liner)}</p>'
                f'<div class="ch-ov-ruler">'
                f'<div class="ch-ruler-cell"><span class="ch-ruler-lbl">参考年化</span><span class="ch-ruler-val">{esc(short_yield)}</span></div>'
                f'<div class="ch-ruler-cell"><span class="ch-ruler-lbl">风险体感</span><span class="ch-ruler-val"><span class="ch-risk-stars" aria-label="{esc(stars_lbl)}">{stars_str}</span> {esc(stars_lbl)}</span></div>'
                f'<div class="ch-ruler-cell"><span class="ch-ruler-lbl">门槛与流动性</span><span class="ch-ruler-val">{esc(short_thr)}</span></div>'
                f"</div>"
                f'<div class="ch-ov-alert"><strong>今日避坑：</strong>{esc(today_alert)}</div>'
                f'<div class="ch-ov-foot">'
                f'<span class="ch-ov-meta">{len(prods)} 项标的 · {len(rules)} 条红线 · 含 3 步买法</span>'
                f'<a class="btn btn-sm btn-primary" href="{esc(href)}">看 1 分钟指南 →</a>'
                f"</div>"
                f"</article>"
            )
        ordered_ids.append(cid)

    grid_cls = "ch-compact-grid" if compact else "ch-overview-grid"
    used: set[str] = set()
    sections: list[str] = []
    for gid, gtitle, gdesc, member_ids in _CHANNEL_ROLE_GROUPS:
        gcards = [cards_by_id[m] for m in member_ids if m in cards_by_id]
        if not gcards:
            continue
        used.update(m for m in member_ids if m in cards_by_id)
        sections.append(
            f'<div class="ch-role-group" data-ch-role-group="{esc(gid)}">'
            f'<div class="ch-role-head">'
            f'<span class="ch-role-title">{esc(gtitle)}</span>'
            f'<span class="ch-role-sub">{esc(gdesc)}</span>'
            f'<span class="ch-role-count">{len(gcards)} 大渠道</span>'
            f"</div>"
            f'<div class="{grid_cls}">{"".join(gcards)}</div>'
            f"</div>"
        )
    leftovers = [cards_by_id[cid] for cid in ordered_ids if cid not in used]
    if leftovers:
        sections.append(
            '<div class="ch-role-group" data-ch-role-group="other">'
            '<div class="ch-role-head">'
            '<span class="ch-role-title">其他合规投资渠道</span>'
            '<span class="ch-role-sub">扩展个人合规配置通道</span>'
            f'<span class="ch-role-count">{len(leftovers)} 大渠道</span>'
            "</div>"
            f'<div class="{grid_cls}">{"".join(leftovers)}</div>'
            "</div>"
        )
    return "".join(sections)


def _match_related_etfs_for_channel(ch: dict[str, Any] | str, etf_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Find matching ETFs from etf_universe.json for a specific channel detail page.
    Prioritizes explicit related_etf_codes on channel dict; gracefully falls back to category rules."""
    if not isinstance(etf_data, dict):
        return []
    etfs = [x for x in (etf_data.get("etfs") or []) if isinstance(x, dict)]
    if not etfs:
        return []

    ch_id = str(ch.get("id", "")).strip() if isinstance(ch, dict) else str(ch or "").strip()

    # 1. Exact code match via related_etf_codes (preferred for 12-channel schema)
    if isinstance(ch, dict) and isinstance(ch.get("related_etf_codes"), list) and ch["related_etf_codes"]:
        by_code = {str(it.get("code", "")).strip().upper(): it for it in etfs if not it.get("gold_locked")}
        exact: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw_cd in ch["related_etf_codes"]:
            cd = str(raw_cd or "").strip().upper()
            if cd and cd not in seen and cd in by_code:
                exact.append(by_code[cd])
                seen.add(cd)
        if exact:
            return exact[:12]

    # 2. Graceful fallback matching by channel ID
    matched: list[dict[str, Any]] = []
    for it in etfs:
        if it.get("gold_locked"):
            continue
        cat = str(it.get("category", ""))
        mkt = str(it.get("market", ""))
        chan = str(it.get("channel", ""))
        name = str(it.get("name", ""))
        code = str(it.get("code", "")).upper()
        if ch_id == "bonds" and mkt == "multi-asset" and ("债" in cat or "债" in name or "短融" in name):
            if "转债" not in name and "转债" not in cat:
                matched.append(it)
        elif ch_id == "reverse_repo" and (code in {"511360", "511880", "511990", "511700"} or "货币" in name or "短融" in name):
            matched.append(it)
        elif ch_id == "fx_deposits_wm" and code in {"SGOV", "IB01", "SHV", "USFR", "BIL", "SHY"}:
            matched.append(it)
        elif ch_id == "convertible_bonds" and ("转债" in cat or "转债" in name):
            matched.append(it)
        elif ch_id == "commodity_etfs" and mkt == "multi-asset" and (
            "商品" in cat or "期货" in name or "豆粕" in name or "有色" in name or "能化" in name or "白银" in name or "原油" in name
        ):
            matched.append(it)
        elif ch_id == "qdii_mrf" and ("QDII" in chan or mkt == "global"):
            matched.append(it)
        elif ch_id == "c_reits" and ("REIT" in name.upper() or "REIT" in cat.upper()):
            matched.append(it)
    return matched[:10]


_ETF_LOCK_SUFFIX_RE = re.compile(r"[（(]红灯锁[）)]\s*$")
_ETF_RISK_SUFFIX_RE = re.compile(
    r"[（(](?:高危溢价！?|退市大限高危预警！?|高危预警！?|红灯锁)[）)]\s*$"
)


def _clean_etf_display_text(text: str, *, strip_risk_tag: bool = False) -> str:
    raw = str(text or "").strip()
    if strip_risk_tag:
        return _ETF_RISK_SUFFIX_RE.sub("", raw).strip()
    return _ETF_LOCK_SUFFIX_RE.sub("", raw).strip()


def _short_live_pill(label: str, max_len: int = 28) -> str:
    txt = str(label or "").strip()
    if len(txt) <= max_len:
        return txt
    first_clause = re.split(r"[，,；;。]", txt, maxsplit=1)[0].strip()
    if 6 <= len(first_clause) <= max_len:
        return first_clause
    cand = first_clause if len(first_clause) >= 6 else txt
    cut_pos = max_len - 1
    cut = cand[:cut_pos]
    if cut_pos < len(cand) and re.search(r"[A-Za-z0-9.%+-]$", cut) and re.match(r"^[A-Za-z0-9.%+-]", cand[cut_pos:]):
        snapped = re.sub(r"[A-Za-z0-9.%+-]+$", "", cut)
        # If snapping leaves a short dangling CJK prefix after a separator (e.g. "·科创"), snap to the separator cleanly
        sep_hits = list(re.finditer(r"[·\s、/｜|：:]", snapped))
        if sep_hits and len(snapped) - sep_hits[-1].end() <= 3 and sep_hits[-1].start() >= 6:
            snapped = snapped[: sep_hits[-1].start()]
        if len(snapped.strip()) >= 6:
            cut = snapped
    return cut.rstrip(" ·，,；;：:-—、/（(") + "…"


def build_channel_detail_page(
    ch: dict[str, Any],
    all_channels: list[dict[str, Any]],
    channels_data: dict[str, Any],
    etf_data: dict[str, Any] | None = None,
) -> str:
    """Render a standalone channel detail page (channels/<id>.html) with 4-stage beginner loop + institutional depth."""
    cid = str(ch.get("id", "")).strip()
    as_of = str(channels_data.get("as_of_label") or "最新班次")
    mutex_note = str(channels_data.get("gold_mutex_note") or "").replace("零档红灯停", "红灯停")
    tone = str(ch.get("status_tone", "blue")).strip().lower()
    if tone not in ("green", "blue", "amber", "red"):
        tone = "blue"

    bucket = _normalize_money_bucket(ch)
    bucket_full, bucket_short = _BUCKET_META[bucket]
    is_hnw = _is_hnw_channel(ch)
    stars_str, stars_lbl = _fmt_stars(_channel_risk_stars(ch))
    etf_total = len((etf_data or {}).get("etfs") or []) if isinstance(etf_data, dict) else 0
    all_etf_btn_lbl = f"进入全部 {etf_total} 只 ETF 雷达 →" if etf_total else "进入全球 ETF 雷达 →"

    # Quick switcher bar across all channels
    switch_pills: list[str] = []
    cur_idx = 0
    for idx, other in enumerate(all_channels):
        oid = str(other.get("id", "")).strip()
        if not oid:
            continue
        if oid == cid:
            cur_idx = idx
        lbl = str(other.get("short_name") or other.get("name") or oid)
        act_cls = " active" if oid == cid else ""
        o_num = _fmt_ch_num(other.get("order"), idx + 1)
        switch_pills.append(
            f'<a class="ch-switch-pill{act_cls}" href="{esc(oid)}.html">{esc(o_num)} {esc(lbl)}</a>'
        )
    cur_num = _fmt_ch_num(ch.get("order"), cur_idx + 1)
    prev_ch = all_channels[cur_idx - 1] if cur_idx > 0 else None
    next_ch = all_channels[cur_idx + 1] if cur_idx + 1 < len(all_channels) else None

    # Stage 1: Beginner 30-second explainer
    expl = _channel_explainer(ch)
    # Stage 2: 3-step buying guide
    steps = _channel_steps(ch)
    _step_prefix_re = re.compile(r"^(?:第\s*[1-3一二三]\s*步\s*[：:]\s*|[1-3]\s*\.\s*)")
    steps_html = "".join(
        f'<div class="ch-step-card">'
        f'<div class="ch-step-num">STEP {i:02d}</div>'
        f'<div class="ch-step-title">{esc(_step_prefix_re.sub("", st_title).strip() or st_title)}</div>'
        f'<div class="ch-step-detail">{esc(st_detail)}</div>'
        f"</div>"
        for i, (st_title, st_detail) in enumerate(steps, start=1)
    )
    # Stage 3: Picks vs Avoids + FAQ
    picks, avoids = _channel_picks_avoids(ch)
    picks_li = "".join(f"<li>{esc(p)}</li>" for p in picks)
    avoids_li = "".join(f"<li>{esc(a)}</li>" for a in avoids)
    faqs = _channel_faq(ch)
    faq_html = ""
    if faqs:
        faq_items = "".join(
            f'<details class="faq-item"><summary class="faq-q">{esc(q)}</summary>'
            f'<div class="faq-a">{esc(a)}</div></details>'
            for q, a in faqs
        )
        faq_html = (
            '<div class="sec-head"><h2>新手高频问答（点击展开）</h2><span class="sec-sub">先解开最容易卡壳的实操疑问</span></div>'
            f'<div class="ch-faq-list">{faq_items}</div>'
        )

    # Stage 4: Institutional KPIs, products table, rules & interactive related ETFs
    kpis = [k for k in (ch.get("key_metrics") or []) if isinstance(k, dict)]
    kpi_html = "".join(
        f'<div class="ch-kpi"><div class="ch-kpi-lbl">{esc(k.get("label", ""))}</div>'
        f'<div class="ch-kpi-val">{esc(k.get("value", ""))}</div></div>'
        for k in kpis
    )

    prods = [p for p in (ch.get("products") or []) if isinstance(p, dict)]
    prod_rows = "".join(
        f"<tr>"
        f'<td class="nw"><span class="code-tag">{esc(p.get("code", ""))}</span></td>'
        f"<td><strong>{esc(p.get('name', ''))}</strong></td>"
        f"<td>{esc(p.get('metric', ''))}</td>"
        f'<td class="nw">{esc(p.get("fee", ""))}</td>'
        f"<td>{esc(p.get('note', ''))}</td>"
        f"</tr>"
        for p in prods
    )
    prod_table_html = (
        '<div class="sec-head"><h2>代表标的、代码与实操明细</h2><span class="sec-sub">核对一手费率、门槛与当前状态</span></div>'
        '<div class="mobile-scroll-cue" aria-hidden="true">← 左右滑动查看完整列 →</div>'
        '<div class="table-wrap"><table class="data-table">'
        "<thead><tr><th>代码/品种</th><th>代表标的与通道</th><th>核心收益/规模参考</th><th>费率/机制</th><th>实操要点与防坑</th></tr></thead>"
        f"<tbody>{prod_rows}</tbody></table></div>"
        if prod_rows
        else ""
    )

    rules = [r for r in (ch.get("rules_and_redlines") or []) if isinstance(r, str) and r.strip()]
    rules_li = "".join(f"<li>{esc(r)}</li>" for r in rules)
    rules_html = (
        f'<div class="ch-rules"><strong>核心制度、税费与避坑红线</strong><ul>{rules_li}</ul></div>'
        if rules_li
        else ""
    )

    related_etfs = _match_related_etfs_for_channel(ch, etf_data)
    related_etf_html = ""
    if related_etfs:
        prem_lbls = {"normal": "折溢价常规", "watch": "买前核参考净值", "high_risk": "高溢价/高危预警"}

        def _fmt_ch_etf_fee_td(raw_fee: Any) -> str:
            s = str(raw_fee or "").strip()
            m_p = re.match(r"^([^（(]+?)\s*([（(].+)$", s)
            if m_p:
                return f'<td class="col-num"><strong>{esc(m_p.group(1).strip())}</strong><div class="sec-sub">{esc(m_p.group(2).strip())}</div></td>'
            return f'<td class="col-num nw"><strong>{esc(s)}</strong></td>'

        etf_rows = "".join(
            f"<tr>"
            f'<td class="nw"><strong>{esc(_clean_etf_display_text(it.get("name", "")))}</strong><br><span class="code-tag">{esc(it.get("code", ""))}</span></td>'
            f'<td><span class="etf-chan-tag">{esc(it.get("channel", ""))}</span><div class="sec-sub">{esc(it.get("tracking_index", ""))}</div></td>'
            f'{_fmt_ch_etf_fee_td(it.get("fee_total_pct", ""))}'
            f'<td><strong>{esc(it.get("aum", ""))}</strong><div class="sec-sub">{esc(it.get("yield_or_pe", ""))}</div></td>'
            f'<td><span class="prem-pill prem-{esc(it.get("premium_status", "normal"))}">{esc(prem_lbls.get(str(it.get("premium_status", "normal")), "常规"))}</span><div class="sec-sub">{esc(it.get("premium_note", ""))}</div></td>'
            f'<td><div><span class="role-pill {_etf_role_cls(it)}">{esc(it.get("action_role", ""))}</span></div>'
            f'<div style="margin-top:5px;display:flex;gap:5px;flex-wrap:wrap;"><button type="button" class="dossier-btn" style="margin-left:0;" data-etf-code="{esc(it.get("code", ""))}">深度拆解</button>'
            f'<button type="button" class="kline-quick-btn" data-etf-code="{esc(it.get("code", ""))}" data-open-tab="kline">📈 K线</button></div></td>'
            f"</tr>"
            for it in related_etfs
        )
        safe_ch_etf_json = json.dumps(related_etfs, ensure_ascii=False).replace("</", "<\\/")
        related_etf_html = (
            '<div class="sec-head"><h2>关联重点 ETF 参数雷达</h2>'
            f'<a class="btn btn-sm" href="../etfs.html">{esc(all_etf_btn_lbl)}</a></div>'
            '<div class="mobile-scroll-cue" aria-hidden="true">← 左右滑动查看完整列 →</div>'
            '<div class="table-wrap etf-table-wrap"><table class="etf-table" id="ch-related-etf-table">'
            "<thead><tr><th>ETF 名称与代码</th><th>通道与指数</th><th>年费率</th><th>规模与特征</th><th>折溢价状态</th><th>定位与 7 维拆解</th></tr></thead>"
            f"<tbody>{etf_rows}</tbody></table></div>"
            '<div class="dossier-backdrop drawer-modal no-print" id="etf-modal" role="dialog" aria-modal="true" aria-label="ETF 深度拆解">'
            '<div class="dossier-dialog">'
            '<div class="dossier-head">'
            '<div class="dossier-head-main">'
            '<h3 class="dossier-title" id="etf-modal-title">ETF 深度档案</h3>'
            '<div class="dossier-sub" id="etf-modal-sub"></div>'
            '<div class="dossier-badges" id="etf-modal-badges"></div>'
            "</div>"
            '<div class="drawer-nav-btns">'
            '<button type="button" class="ctrl-btn" data-drawer-step="-1" title="上一个 (↑)" aria-label="上一个">↑</button>'
            '<span class="drawer-pos" data-drawer-pos></span>'
            '<button type="button" class="ctrl-btn" data-drawer-step="1" title="下一个 (↓)" aria-label="下一个">↓</button>'
            '<button type="button" class="ctrl-btn" data-action="close-etf" aria-label="关闭 ETF 详情">关闭 ✕</button>'
            "</div>"
            "</div>"
            '<div class="dossier-body" id="etf-modal-body"></div>'
            '<div class="dossier-foot">'
            '<span>数据经交易所、基金定期报告与官网费率交叉核验 · 下单前请实时核对盘口参考净值</span>'
            '<a href="../etfs.html" class="btn btn-sm">前往完整 ETF 雷达 →</a>'
            "</div></div></div>"
            f'<script id="ch-etf-data" type="application/json">{safe_ch_etf_json}</script>'
        )

    prev_num = _fmt_ch_num(prev_ch.get("order"), cur_idx) if prev_ch else ""
    next_num = _fmt_ch_num(next_ch.get("order"), cur_idx + 2) if next_ch else ""
    nav_left = (
        f'<a class="btn" href="{esc(prev_ch["id"])}.html">← {esc(prev_num)} {esc(prev_ch.get("short_name") or prev_ch.get("name", ""))}</a>'
        if prev_ch
        else '<a class="btn" href="../channels.html">← 返回多元渠道总览</a>'
    )
    nav_right = (
        f'<a class="btn btn-primary" href="{esc(next_ch["id"])}.html">{esc(next_num)} {esc(next_ch.get("short_name") or next_ch.get("name", ""))} →</a>'
        if next_ch
        else '<a class="btn btn-primary" href="../etfs.html">前往全球 ETF 雷达 →</a>'
    )
    qdii_compare_html = (
        _render_qdii_comparison_section(channels_data, compact=False)
        if cid == "qdii_mrf"
        else ""
    )
    qdii_hero_cta = (
        '<div class="hero-cta-row" style="margin:12px 0 10px 0;">'
        '<a class="btn btn-qdii" href="#sec-qdii-compare">⚡ 直达 QDII 溢价与限购对照表 →</a>'
        '<a class="hero-cta" href="../etfs.html#preset=qdii">查看境内 QDII ETF 排雷清单 →</a>'
        "</div>"
        if cid == "qdii_mrf"
        else ""
    )
    hnw_hero_badge = '<span class="ch-hnw-badge">合格投资者</span>' if is_hnw else ""
    raw_summary = str(ch.get("summary") or "").strip()
    if len(raw_summary) > 180:
        sent_m = re.search(r"[。！？]", raw_summary[:180])
        if sent_m and sent_m.end() >= 35:
            lead_summary = raw_summary[: sent_m.end()].strip()
            rest_summary = raw_summary[sent_m.end() :].strip()
        else:
            semi_m = re.search(r"[；;。！？]", raw_summary[45:180])
            cut_at = (45 + semi_m.end()) if semi_m else 140
            lead_summary = raw_summary[:cut_at].rstrip(" ，,；;：:") + ("…" if cut_at == 140 else "")
            rest_summary = raw_summary[cut_at:].strip()
        if rest_summary:
            hero_summary_html = (
                f'<p class="channels-hero-sub" style="margin-bottom:8px;">{esc(lead_summary)}</p>'
                '<details class="ch-hero-more">'
                "<summary>展开完整当日动态与盘口明细</summary>"
                f"<p>{esc(rest_summary)}</p>"
                "</details>"
            )
        else:
            hero_summary_html = f'<p class="channels-hero-sub" style="margin-bottom:10px;">{esc(raw_summary)}</p>'
    else:
        hero_summary_html = f'<p class="channels-hero-sub" style="margin-bottom:10px;">{esc(raw_summary)}</p>'

    detail_page_html = f"""
    <div class="doc-toolbar no-print">
      <div class="doc-toolbar-left">
        <nav class="breadcrumb" aria-label="面包屑">
          <a href="../index.html">总览</a>
          <span class="bc-sep" aria-hidden="true">/</span>
          <a href="../channels.html">多元渠道</a>
          <span class="bc-sep" aria-hidden="true">/</span>
          <span>{esc(cur_num)} {esc(ch.get("short_name") or ch.get("name", ""))}</span>
        </nav>
        <div class="doc-meta-pills">
          <span class="meta-pill">{bucket_short}</span>
          <span class="meta-pill">{esc(ch.get("category_label", ""))}</span>
          <span class="meta-pill">更新：{esc(as_of)}</span>
        </div>
      </div>
      <div class="doc-toolbar-right">
        <a class="btn btn-sm" href="../guide.html">新手 3 分钟指南</a>
        <a class="btn btn-sm" href="../channels.html">全渠道对比总表</a>
        <a class="btn btn-sm" href="../etfs.html">ETF 雷达</a>
      </div>
    </div>

    <nav class="ch-switcher" aria-label="切换其他多元投资渠道">
      {"".join(switch_pills)}
    </nav>

    <section class="ch-detail-hero">
      <div class="ch-head">
        <div class="ch-head-left">
          <span class="ch-num">{esc(cur_num)}</span>
          <h1 style="margin:0;font-size:22px;">{esc(ch.get("name", ""))}</h1>
          <span class="ch-bucket-pill">{bucket_full}</span>
          {hnw_hero_badge}
          <span class="ch-badge">{esc(ch.get("badge", ""))}</span>
        </div>
        <span class="ch-status ch-tone-{tone}">{esc(ch.get("status_tag", ""))}</span>
      </div>
      {hero_summary_html}
      {qdii_hero_cta}
      {f'<div class="channels-mutex" style="margin-bottom:0;">🛑 跨市场风控同步：{esc(mutex_note)}</div>' if mutex_note else ''}
    </section>

    <section class="ch-b-section">
      <div class="sec-head" style="margin-top:4px;">
        <h2>① 30 秒看懂：它是什么 · 怎么赚 · 最坏亏多少</h2>
        <span class="sec-sub">风险体感：<span class="ch-risk-stars">{stars_str}</span> {esc(stars_lbl)} · 所属资金桶：{bucket_full}</span>
      </div>
      <div class="ch-explain-grid">
        <div class="ch-explain-card">
          <div class="ch-explain-lbl">它到底是什么</div>
          <div class="ch-explain-txt">{esc(expl["what_it_is"])}</div>
        </div>
        <div class="ch-explain-card">
          <div class="ch-explain-lbl">钱从哪赚</div>
          <div class="ch-explain-txt">{esc(expl["how_it_earns"])}</div>
        </div>
        <div class="ch-explain-card">
          <div class="ch-explain-lbl">最坏会亏多少</div>
          <div class="ch-explain-txt">{esc(expl["worst_case"])}</div>
        </div>
      </div>

      <div class="sec-head">
        <h2>② 去哪买 · 怎么买三步走</h2>
        <span class="sec-sub">从选对 App 到下单防呆，一屏走完实操闭环</span>
      </div>
      <div class="ch-steps-grid">{steps_html}</div>

      <div class="sec-head">
        <h2>③ 新手优选 vs 高危避坑对照</h2>
        <span class="sec-sub">先区分省心底仓与容易踩雷的高危变体</span>
      </div>
      <div class="ch-contrast-grid">
        <div class="ch-picks-box">
          <strong>✅ 新手省心优选区</strong>
          <ul>{picks_li}</ul>
        </div>
        <div class="ch-avoids-box">
          <strong>⛔ 高危避坑绕道区</strong>
          <ul>{avoids_li}</ul>
        </div>
      </div>
      {faq_html}
    </section>

    <div class="sec-head">
      <h2>④ 机构级一线参数、代表标的与制度红线</h2>
      <span class="sec-sub">实盘数据与税费细则完整留痕，方便进阶核对</span>
    </div>
    <article class="channel-card" id="ch-{esc(cid)}">
      <div class="ch-kpi-grid">{kpi_html}</div>
      <div class="ch-meta-grid">
        <div class="ch-meta-item"><strong>参考收益：</strong>{esc(ch.get("yield_range", ""))}</div>
        <div class="ch-meta-item"><strong>风险等级：</strong>{esc(ch.get("risk_level", ""))}</div>
        <div class="ch-meta-item"><strong>起投门槛：</strong>{esc(ch.get("min_threshold", ""))}</div>
        <div class="ch-meta-item"><strong>流动性：</strong>{esc(ch.get("liquidity", ""))}</div>
        <div class="ch-meta-item" style="grid-column:1 / -1;"><strong>税费规则：</strong>{esc(ch.get("tax_summary", ""))}</div>
      </div>
      {prod_table_html}
      {rules_html}
      <div class="ch-fit-grid">
        <div class="ch-fit-box"><strong>适用资金：</strong>{esc(ch.get("fit_for", ""))}</div>
        <div class="ch-avoid-box"><strong>劝退与避坑：</strong>{esc(ch.get("avoid_if", ""))}</div>
      </div>
    </article>

    {qdii_compare_html}
    {related_etf_html}

    <div class="ch-detail-nav">
      {nav_left}
      <a class="btn" href="../index.html">返回首页总览</a>
      {nav_right}
    </div>
    """
    return inject_glossary_tips(detail_page_html)


_ETF_ASSET_CLASS_LABELS: dict[str, str] = {
    "equity": "股票权益",
    "fixed_income": "利率信用债",
    "cash_mmf": "现金货币盾",
    "convertible_bond": "可转债",
    "gold": "黄金（红灯）",
    "commodity": "非金商品",
    "reits": "REITs",
}

_ETF_REGION_LABELS: dict[str, str] = {
    "cn": "中国境内",
    "hk": "中国香港",
    "us": "美国",
    "jp": "日本",
    "eu": "欧洲",
    "apac_em": "亚太新兴",
    "global": "全球",
}


def _infer_etf_ortho(it: dict[str, Any]) -> tuple[str, str]:
    """Return orthogonal (asset_class, region) with graceful fallback for minimal synthetic test fixtures."""
    ac = str(it.get("asset_class") or "").strip()
    reg = str(it.get("region") or "").strip()
    if ac and reg:
        return ac, reg
    code = str(it.get("code") or "").strip().upper()
    mkt = str(it.get("market") or "").strip()
    cat = str(it.get("category") or "").strip()
    if not ac:
        if it.get("gold_locked") or code in ("02840", "03081"):
            ac = "gold"
        elif code in ("511880", "511990", "511360", "03053", "03152", "03096", "SGOV", "VBIL", "USFR", "IB01"):
            ac = "cash_mmf"
        elif code in ("511180", "511380") or "转债" in cat:
            ac = "convertible_bond"
        elif code == "XLRE" or "REIT" in cat.upper():
            ac = "reits"
        elif code in ("159985", "159980", "159981", "161226") or "商品" in cat:
            ac = "commodity"
        elif "债" in cat or code in ("SHY", "VTIP", "BND", "USHY", "TLT"):
            ac = "fixed_income"
        else:
            ac = "equity"
    if not reg:
        if code in ("02840", "03081"):
            reg = "global"
        elif code in ("03096", "IB01", "SGOV", "VBIL", "USFR", "SHY", "VTIP", "BND", "USHY", "TLT", "XLRE"):
            reg = "us"
        elif mkt == "a-share":
            reg = "cn"
        elif mkt == "hk-stock":
            reg = "hk"
        elif mkt == "us-stock":
            reg = "us"
        elif code in ("513800", "513520"):
            reg = "jp"
        elif code in ("VGK", "513030", "159561", "513080"):
            reg = "eu"
        elif code in ("VWO", "IEMG", "520580", "513310", "520830", "164824", "159687"):
            reg = "apac_em"
        elif mkt == "multi-asset" and ac in ("fixed_income", "cash_mmf", "convertible_bond"):
            reg = "cn"
        else:
            reg = "global"
    return ac, reg


def _render_home_etf_showcase(etf_data: dict[str, Any] | None, total_pool: int) -> str:
    """Render 6 orthogonal ETF overview cards (3x2 grid) on index.html linking directly to filtered etfs.html views."""
    if not isinstance(etf_data, dict):
        return ""
    etfs = [x for x in (etf_data.get("etfs") or []) if isinstance(x, dict)]
    if not etfs:
        return ""

    as_of = str(etf_data.get("as_of_label") or "最新班次")
    ortho_pairs = [(it, *_infer_etf_ortho(it)) for it in etfs]

    cn_eq = [it for it, ac, reg in ortho_pairs if ac == "equity" and reg == "cn"]
    hk_eq = [it for it, ac, reg in ortho_pairs if ac == "equity" and reg == "hk"]
    us_eq = [it for it, ac, reg in ortho_pairs if ac == "equity" and reg == "us"]
    nonus_eq = [it for it, ac, reg in ortho_pairs if ac == "equity" and reg in ("jp", "eu", "apac_em", "global")]
    fi_cash = [it for it, ac, _ in ortho_pairs if ac in ("fixed_income", "cash_mmf", "convertible_bond", "reits")]
    qdii_etfs = [it for it, _, _ in ortho_pairs if str(it.get("channel") or "").strip() == "境内QDII"]
    gold_cnt = sum(1 for _, ac, _ in ortho_pairs if ac == "gold")
    cmd_cnt = sum(1 for _, ac, _ in ortho_pairs if ac == "commodity")

    groups = [
        ("cn-eq", "🇨🇳 A 股权益 ETF", cn_eq, "宽基 A500 · 沪深300 · 自由现金流 · 红利低波与行业地板费", "etfs.html#asset_class=equity&region=cn"),
        ("hk-eq", "🇭🇰 港股权益 ETF", hk_eq, "离岸免印花税 · 境内非 QDII 港股通 · 港股高息与恒科", "etfs.html#asset_class=equity&region=hk"),
        ("us-eq", "🇺🇸 美股权益 ETF", us_eq, "美股、爱尔兰 UCITS 与境内 QDII · 费用和跨境税务核对", "etfs.html#asset_class=equity&region=us"),
        ("nonus-eq", "🌏 日欧亚太与全球权益", nonus_eq, "513800 东证平价 · 159561 德国直投 · VWRA / VXUS / IEMG", "etfs.html#asset_class=equity&region=non_us"),
        ("fi-cash", "🏦 债券 / 现金盾 / 转债 / REITs", fi_cash, "中债短融/十年/三十年 · 美元短债 SGOV / IB01 · 投资级转债", "etfs.html#asset_class=fixed_income_plus"),
        ("qdii", "⚡ 境内 QDII 溢价与限购专窗", qdii_etfs, f"{len(qdii_etfs)} 只场内 QDII 实时溢价排雷 · 对比官方直销 App 限额", "etfs.html#preset=qdii"),
    ]
    summary_cards: list[str] = []
    for grp_id, title, items, sub, href in groups:
        low_cnt = sum(1 for x in items if isinstance(x.get("fee_num"), (int, float)) and x["fee_num"] <= 0.20)
        risk_cnt = sum(1 for x in items if x.get("premium_status") == "high_risk")
        non_locked = [x for x in items if not x.get("gold_locked")]
        if grp_id == "fi-cash":
            by_code = {str(x.get("code") or "").strip().upper(): x for x in non_locked}
            preferred = [by_code[c] for c in ("511360", "511260", "SGOV", "IB01") if c in by_code]
            seen_codes = {str(x.get("code") or "").strip().upper() for x in preferred}
            samples = (preferred + [x for x in non_locked if str(x.get("code") or "").strip().upper() not in seen_codes])[:3]
        else:
            samples = non_locked[:3]
        sample_tags = "".join(
            f'<span class="code-tag" title="{esc(x.get("name", ""))}">{esc(x.get("code", ""))}</span>'
            for x in samples
        )
        risk_note = f" · {risk_cnt} 预警" if risk_cnt else ""
        summary_cards.append(
            f'<a class="home-etf-card" href="{esc(href)}">'
            f'<div class="home-etf-head"><strong>{title}</strong><span class="home-etf-count">{len(items)} 只</span></div>'
            f'<div class="sec-sub">{esc(sub)}</div>'
            f'<div class="home-etf-list">{sample_tags}</div>'
            f'<div class="home-etf-foot"><span>低费 ≤0.20%：{low_cnt} 只{risk_note}</span><span>查看详情 →</span></div>'
            f"</a>"
        )

    high_risks = [x for x in etfs if x.get("premium_status") == "high_risk" and not x.get("gold_locked")]
    alert_html = ""
    if high_risks:
        codes_str = "、".join(
            f'{x.get("code", "")}（{_clean_etf_display_text(x.get("name", ""), strip_risk_tag=True)}）'
            for x in high_risks[:3]
        )
        extra = " 等" if len(high_risks) > 3 else ""
        alert_html = (
            f'<a class="home-etf-alert" href="etfs.html#preset=high-risk">'
            f'<span>⚠️ <strong>重点 ETF 雷达高溢价/退市预警（共 {len(high_risks)} 只）</strong>：{esc(codes_str)}{extra} — 点击进入排雷清单</span>'
            f'<span class="nw">立即查看 →</span>'
            f"</a>"
        )

    other_cnt_note = f" · 另含 {gold_cnt} 只黄金红灯锁 + {cmd_cnt} 只非金商品" if (gold_cnt or cmd_cnt) else ""
    return f"""
    <div class="sec-head" id="sec-etf-radar">
      <div>
        <h2>全球 {len(etfs)} 只重点 ETF 正交分类入口（资产大类 × 底层区域 × QDII 专窗）</h2>
        <span class="sec-sub">基准：{esc(as_of)}{esc(other_cnt_note)}</span>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <a href="etfs.html#preset=qdii" class="btn btn-sm btn-qdii">⚡ 境内 QDII 溢价排雷 →</a>
        <a href="etfs.html" class="btn btn-sm btn-primary">全部 {len(etfs)} 只 ETF 雷达 →</a>
        <a href="screener.html" class="btn btn-sm">全部 {total_pool} 股 7 维深研 →</a>
      </div>
    </div>
    <div class="home-etf-grid-6">{"".join(summary_cards)}</div>
    {alert_html}
    """


def _dot_css_class(lamp_cls: str) -> str:
    if lamp_cls == "lamp-green":
        return "dot-green"
    if lamp_cls == "lamp-amber":
        return "dot-amber"
    return "dot-red"


def _breaker_fill_cls(chip_cls: str) -> str:
    if chip_cls == "chip-danger":
        return "fill-danger"
    if chip_cls == "chip-warn":
        return "fill-warn"
    return "fill-ok"


def _edition_pill_html(edition_type: str) -> str:
    ed = str(edition_type or "main").strip().lower()
    if ed == "holiday_watch":
        return '<span class="ed-pill ed-watch">守望刊</span>'
    if ed == "light":
        return '<span class="ed-pill ed-watch">轻刊</span>'
    if ed == "midday":
        return '<span class="ed-pill ed-midday">午刊</span>'
    return '<span class="ed-pill ed-main">主刊</span>'


def _render_score_meter(score_num: float | None, score_str: str) -> str:
    val = score_num if score_num is not None else 0.0
    score_tier = "high" if val >= 4.5 else ("mid" if val >= 2.5 else "low")
    segs: list[str] = []
    for idx in range(1, 7):
        if val >= idx:
            cls = "seg-full"
        elif val >= idx - 0.5:
            cls = "seg-half"
        else:
            cls = "seg-empty"
        segs.append(f'<span class="score-seg {cls}"></span>')
    return (
        '<div class="score-meter-row">'
        f'<div class="score-meter" data-score-tier="{score_tier}" aria-hidden="true">{"".join(segs)}</div>'
        f'<span class="score-meter-lbl">大盘水温 {esc(score_str)}</span>'
        "</div>"
    )


def _render_gold_gate_strip(t1_gates: Any) -> str:
    if not isinstance(t1_gates, list) or not t1_gates:
        return ""
    short_map = {
        "real_yield": "1.真实利率",
        "rate_spread": "2.加息利差",
        "vix": "3.恐慌回落",
        "ny_close": "4.金价站稳",
    }
    chips: list[str] = []
    for idx, gate in enumerate(t1_gates[:4], start=1):
        if not isinstance(gate, dict):
            continue
        gid = str(gate.get("id") or "").strip().lower()
        raw_name = str(gate.get("name") or f"第{idx}关").strip()
        short_lbl = short_map.get(gid) or re.sub(r"^第\s*\d+\s*关[：:]\s*", "", raw_name)[:6]
        passed = bool(gate.get("passed", False))
        reading = str(gate.get("reading") or "").strip()
        threshold = str(gate.get("threshold") or "").strip()
        tip = f"{raw_name}｜读数：{reading}｜门槛：{threshold}" if (reading or threshold) else raw_name
        cls = "gate-pass" if passed else "gate-fail"
        sym = "✓" if passed else "×"
        chips.append(f'<span class="gate-chip {cls}" title="{esc(tip)}">{sym} {esc(short_lbl)}</span>')
    return f'<div class="gate-strip">{"".join(chips)}</div>' if chips else ""


_MULTI_INDEX_SPECS: dict[str, tuple[dict[str, Any], ...]] = {
    "a_share": (
        {"id": "idx_sh000001", "code": "000001", "name": "上证指数", "short": "上证指数", "tier": "大盘总舵", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sh000300", "code": "000300", "name": "沪深300", "short": "沪深300", "tier": "核心宽基", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sz399001", "code": "399001", "name": "深证成指", "short": "深证成指", "tier": "大盘总舵", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sh000510", "code": "000510", "name": "中证A500", "short": "中证A500", "tier": "核心宽基", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sz399006", "code": "399006", "name": "创业板指", "short": "创业板指", "tier": "成长双创", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sh000688", "code": "000688", "name": "科创50", "short": "科创50", "tier": "成长双创", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sh000016", "code": "000016", "name": "上证50", "short": "上证50", "tier": "核心宽基", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sh000905", "code": "000905", "name": "中证500", "short": "中证500", "tier": "中小风格", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sh000852", "code": "000852", "name": "中证1000", "short": "中证1000", "tier": "中小风格", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sh000922", "code": "000922", "name": "中证红利", "short": "中证红利", "tier": "红利防御", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_bj899050", "code": "899050", "name": "北证50", "short": "北证50", "tier": "北交微盘", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sh000832", "code": "000832", "name": "中证转债", "short": "中证转债", "tier": "转债锚", "prefix": "", "suffix": "", "fmt": ",.2f"},
    ),
    "hk_stock": (
        {"id": "idx_hkHSI", "code": "HSI", "name": "恒生指数", "short": "恒生指数", "tier": "大盘总舵", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_hkHSTECH", "code": "HSTECH", "name": "恒生科技", "short": "恒生科技", "tier": "核心旗帜", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_hkHSCEI", "code": "HSCEI", "name": "恒生国企指数", "short": "国企指数", "tier": "核心旗帜", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_HSCI", "code": "HSCI", "name": "恒生综合", "short": "恒生综合", "tier": "市场广度", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_HSAHP", "code": "HSAHP", "name": "恒生AH溢价", "short": "AH溢价", "tier": "两地比价", "prefix": "", "suffix": "", "fmt": ".2f"},
    ),
    "us_stock": (
        {"id": "idx_SPX", "code": "SPX", "name": "标普500", "short": "标普500", "tier": "大盘总舵", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_IXIC", "code": "IXIC", "name": "纳斯达克综合", "short": "纳斯达克", "tier": "核心双璧", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_NDX", "code": "NDX", "name": "纳斯达克100", "short": "纳指100", "tier": "核心双璧", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_DJI", "code": "DJI", "name": "道琼斯工业", "short": "道琼斯", "tier": "核心双璧", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_RUT", "code": "IWM", "name": "罗素2000 ETF", "short": "罗素2000 ETF", "tier": "小盘广度", "prefix": "$", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_SPXEW", "code": "RSP", "name": "标普500等权 ETF", "short": "标普等权 ETF", "tier": "市场广度", "prefix": "$", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_SOX", "code": "SOX", "name": "费城半导体", "short": "费城半导体", "tier": "算力芯片", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_VIX", "code": "VIX", "name": "VIX恐慌指数", "short": "VIX恐慌", "tier": "情绪熔断", "prefix": "", "suffix": "", "fmt": ".2f"},
    ),
    "non_us_global": (
        {"id": "idx_N225", "code": "N225", "name": "日经225", "short": "日经225", "tier": "日本大盘", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_TOPIX", "code": "TOPIX", "name": "日本东证TOPIX", "short": "东证TOPIX", "tier": "日本宽基", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_GDAXI", "code": "DAX", "name": "德国DAX", "short": "德国DAX", "tier": "欧洲引擎", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_STOXX50E", "code": "SX5E", "name": "欧洲斯托克50", "short": "斯托克50", "tier": "欧元区锚", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_FCHI", "code": "CAC40", "name": "法国CAC40", "short": "法国CAC40", "tier": "欧洲核心", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_FTSE", "code": "FTSE", "name": "英国富时100", "short": "富时100", "tier": "英国高息", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_TWII", "code": "TWII", "name": "中国台湾加权", "short": "台湾加权", "tier": "AI供应链", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_KS11", "code": "KOSPI", "name": "韩国KOSPI", "short": "韩国KOSPI", "tier": "存储芯片", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_NSEI", "code": "NIFTY50", "name": "印度Nifty50", "short": "印度Nifty50", "tier": "新兴成长", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "etf_513800", "code": "513800", "name": "南方日本东证ETF", "short": "东证513800", "tier": "境内场内基金", "prefix": "¥", "suffix": "", "fmt": ".3f"},
        {"id": "etf_159561", "code": "159561", "name": "嘉实德国DAX ETF", "short": "德国159561", "tier": "境内场内基金", "prefix": "¥", "suffix": "", "fmt": ".3f"},
        {"id": "etf_VXUS", "code": "VXUS", "name": "全球除美VXUS", "short": "除美VXUS", "tier": "离岸分散", "prefix": "$", "suffix": "", "fmt": ".2f"},
    ),
    "bonds_reits": (
        {"id": "rate_CN10Y", "code": "CN10Y", "name": "中国10Y国债收益率", "short": "中债10Y", "tier": "境内利率锚", "prefix": "", "suffix": "%", "fmt": ".3f"},
        {"id": "rate_CN30Y", "code": "CN30Y", "name": "中国30Y国债收益率", "short": "中债30Y", "tier": "超长久期", "prefix": "", "suffix": "%", "fmt": ".3f"},
        {"id": "rate_CN2Y", "code": "CN2Y", "name": "中国2Y国债收益率", "short": "中债2Y", "tier": "短端利率", "prefix": "", "suffix": "%", "fmt": ".3f"},
        {"id": "rate_US10Y", "code": "US10Y", "name": "美债10Y收益率", "short": "美债10Y", "tier": "全球定价锚", "prefix": "", "suffix": "%", "fmt": ".2f"},
        {"id": "rate_US2Y", "code": "US2Y", "name": "美债2Y收益率", "short": "美债2Y", "tier": "联储预期", "prefix": "", "suffix": "%", "fmt": ".2f"},
        {"id": "rate_US30Y", "code": "US30Y", "name": "美债30Y收益率", "short": "美债30Y", "tier": "美债长端", "prefix": "", "suffix": "%", "fmt": ".2f"},
        {"id": "rate_DFII10", "code": "DFII10", "name": "美债10Y实际利率", "short": "TIPS实利", "tier": "黄金第一关", "prefix": "", "suffix": "%", "fmt": ".2f"},
        {"id": "idx_932047", "code": "932047", "name": "中证REITs全收益", "short": "C-REITs全收益", "tier": "实体租金", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "idx_sh000832", "code": "000832", "name": "中证转债", "short": "中证转债", "tier": "股债混合", "prefix": "", "suffix": "", "fmt": ",.2f"},
        {"id": "etf_511260", "code": "511260", "name": "十年国债ETF", "short": "十年债511260", "tier": "场内利率", "prefix": "¥", "suffix": "", "fmt": ".3f"},
        {"id": "etf_511090", "code": "511090", "name": "30年国债ETF", "short": "三十债511090", "tier": "高波久期", "prefix": "¥", "suffix": "", "fmt": ".3f"},
        {"id": "etf_511360", "code": "511360", "name": "短融ETF", "short": "短融511360", "tier": "活钱现金盾", "prefix": "¥", "suffix": "", "fmt": ".3f"},
        {"id": "etf_SGOV", "code": "SGOV", "name": "0-3月美债SGOV", "short": "短美债SGOV", "tier": "美元现金盾", "prefix": "$", "suffix": "", "fmt": ".2f"},
        {"id": "etf_IB01", "code": "IB01", "name": "爱尔兰0-1Y美债", "short": "爱尔兰IB01", "tier": "美元累积份额", "prefix": "$", "suffix": "", "fmt": ".2f"},
        {"id": "etf_TLT", "code": "TLT", "name": "20+年美债TLT", "short": "长美债TLT", "tier": "长债博弈", "prefix": "$", "suffix": "", "fmt": ".2f"},
        {"id": "etf_XLRE", "code": "XLRE", "name": "美股REITs XLRE", "short": "美REITs", "tier": "海外不动产", "prefix": "$", "suffix": "", "fmt": ".2f"},
    ),
    "gold": (
        {"id": "cmd_XAU", "code": "XAU", "name": "伦敦现货黄金", "short": "现货黄金", "tier": "国际现货", "prefix": "$", "suffix": "", "fmt": ",.2f"},
        {"id": "cmd_GC", "code": "GC", "name": "COMEX黄金", "short": "COMEX金", "tier": "国际期金", "prefix": "$", "suffix": "", "fmt": ",.2f"},
        {"id": "cmd_AU0", "code": "AU0", "name": "沪金主力", "short": "沪金主力", "tier": "国内期金", "prefix": "¥", "suffix": "", "fmt": ",.2f"},
        {"id": "cmd_Au9999", "code": "Au99.99", "name": "上金所Au99.99", "short": "Au99.99", "tier": "国内现货", "prefix": "¥", "suffix": "", "fmt": ",.2f"},
        {"id": "cmd_XAG", "code": "XAG", "name": "伦敦现货银", "short": "伦敦现货银", "tier": "国际白银", "prefix": "$", "suffix": "", "fmt": ",.2f"},
        {"id": "cmd_AG0", "code": "AG0", "name": "沪银主力", "short": "沪银主力", "tier": "国内白银", "prefix": "¥", "suffix": "", "fmt": ",.0f"},
    ),
    "macro": (
        {"id": "cmd_OIL", "code": "BRN", "name": "布伦特原油", "short": "布伦特原油", "tier": "能源通胀", "prefix": "$", "suffix": "", "fmt": ".2f"},
        {"id": "cmd_CL", "code": "CL", "name": "WTI原油", "short": "WTI原油", "tier": "能源通胀", "prefix": "$", "suffix": "", "fmt": ".2f"},
        {"id": "cmd_HG", "code": "HG", "name": "COMEX铜", "short": "COMEX铜", "tier": "工业周期", "prefix": "$", "suffix": "", "fmt": ".2f"},
        {"id": "fx_DXY", "code": "DXY", "name": "美元指数", "short": "美元指数", "tier": "汇率总锚", "prefix": "", "suffix": "", "fmt": ".2f"},
        {"id": "rate_US10Y", "code": "US10Y", "name": "美债10Y收益率", "short": "美债10Y", "tier": "定价之锚", "prefix": "", "suffix": "%", "fmt": ".2f"},
        {"id": "fx_USDCNH", "code": "USD/CNH", "name": "离岸人民币", "short": "离岸人民币", "tier": "人民币锚", "prefix": "", "suffix": "", "fmt": ".4f"},
        {"id": "fx_USDJPY", "code": "USD/JPY", "name": "美元/日元", "short": "美元/日元", "tier": "套息熔断", "prefix": "", "suffix": "", "fmt": ".2f"},
        {"id": "fx_EURUSD", "code": "EUR/USD", "name": "欧元/美元", "short": "欧元/美元", "tier": "欧系汇率", "prefix": "", "suffix": "", "fmt": ".4f"},
        {"id": "fx_GBPUSD", "code": "GBP/USD", "name": "英镑/美元", "short": "英镑/美元", "tier": "英镑汇率", "prefix": "", "suffix": "", "fmt": ".4f"},
        {"id": "fx_USDHKD", "code": "USD/HKD", "name": "美元/港元", "short": "美元/港元", "tier": "联汇锚", "prefix": "", "suffix": "", "fmt": ".4f"},
        {"id": "crypto_BTC", "code": "BTC", "name": "比特币 BTC（只读·禁交易）", "short": "比特币(只读·禁交易)", "tier": "流动风向", "prefix": "$", "suffix": "", "fmt": ",.0f"},
    ),
}

_SPECIAL_WITHHOLDING_CODES: frozenset[str] = frozenset({"00883.HK", "00941.HK", "00836.HK", "00291.HK", "00992.HK", "00267.HK"})


def _valid_iso_date(raw: Any) -> str:
    if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return ""
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return ""


def _kline_source_label(provider: Any) -> str:
    family = str(provider or "").lower().split("_", 1)[0]
    return {
        "tencent": "腾讯行情", "sina": "新浪行情", "sge": "上海黄金交易所",
        "cboe": "芝加哥期权交易所", "us": "美国财政部", "chinabond": "中债",
        "csindex": "中证指数", "eastmoney": "东方财富", "ft": "金融时报",
        "justetf": "justETF", "cnbc": "CNBC 行情", "coinbase": "境外公开报价",
        "exchange": "交易所原表",
    }.get(family, "日线来源待核")


def _quote_status(stamp: str) -> str:
    for pattern, label in (
        (r"沿用|缓存", "沿用报价"), (r"官结|官方结算", "官结"), (r"午收|午盘|早盘收", "午盘"),
        (r"官收|官方收盘|官方终盘", "官收"), (r"盘中|实盘", "盘中"),
        (r"前收|收盘", "收盘参考"),
    ):
        if re.search(pattern, stamp):
            return label
    return "盘口待核"


def _quote_provenance(row: dict[str, Any]) -> str:
    return " · ".join((
        row.get("quote_date") or "行情日待核",
        row.get("quote_status") or "盘口待核",
        row.get("quote_source") or "来源待核",
    ))


def _quote_timestamp(stamp: str, observed_day: str) -> datetime | None:
    if not observed_day:
        return None
    clock = re.search(r"(?<![\d+-])([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:Z|[+-]\d{2}:\d{2})?", stamp)
    if not clock:
        return None
    try:
        observation = datetime.fromisoformat(f"{observed_day}T{clock[0]}")
    except ValueError:
        return None
    if observation.tzinfo is not None:
        return observation
    timezone_label = stamp[clock.end():].strip().upper()
    if re.match(r"E[DS]?T\b|美东", timezone_label):
        return observation.replace(tzinfo=ZoneInfo("America/New_York"))
    if re.match(r"UTC\b|GMT\b", timezone_label):
        return observation.replace(tzinfo=timezone.utc)
    return observation.replace(tzinfo=timezone(timedelta(hours=8)))


def _edition_quote_catalog(
    manifest: dict[str, Any] | None, state: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    manifest = manifest or {}
    edition = state.get("edition_id")
    if edition and manifest.get("edition_id") != edition:
        return {}
    return {
        row["id"]: row for row in (manifest.get("catalog") or [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }


def _resolve_multi_index_groups(
    gold_snap: dict[str, Any],
    eq_state: dict[str, Any],
    kline_manifest: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Choose a single observation for each index, keeping its move and attribution together."""
    cat_by_id = _edition_quote_catalog(kline_manifest, eq_state)
    cutoff = str(eq_state.get("as_of_cst") or "")
    cutoff_day = _valid_iso_date(cutoff[:10])
    cutoff_time = _quote_timestamp(cutoff, cutoff_day)
    calendar = eq_state.get("calendar_overrides")
    cash_index_markets = {"a_share": "a-share", "hk_stock": "hk-stock", "us_stock": "us-stock"}
    fund_listing_markets = {
        "etf_511360": "a-share", "etf_513800": "a-share", "etf_159561": "a-share",
        "etf_SGOV": "us-stock", "etf_TLT": "us-stock", "etf_XLRE": "us-stock", "etf_VXUS": "us-stock",
    }
    markets = eq_state.get("markets") or {}
    a_m = markets.get("a_share") or {}
    hk_m = markets.get("hk_stock") or {}
    us_m = markets.get("us_stock") or {}
    linkages = eq_state.get("cross_market_linkages") or {}
    rates = linkages.get("rates_fx_chain") or {}
    comm = linkages.get("commodity_mirror") or {}
    brake = linkages.get("crisis_correlation_brake") or {}
    cn_rates = (eq_state.get("rates_bonds_core") or {}).get("cn_rates") or {}
    nonus_sat = eq_state.get("non_us_global_satellite") or {}
    nonus_benchmarks = [
        benchmark for market in (nonus_sat.get("markets") or []) if isinstance(market, dict)
        for benchmark in (market.get("benchmarks") or [])
    ] if isinstance(nonus_sat, dict) else []

    eq_source, gold_source = "权益研报快照", "黄金研报快照"
    overrides: dict[str, tuple[dict, str]] = {}
    for source, rows in (
        (eq_source, a_m.get("index_matrix")),
        (eq_source, hk_m.get("index_matrix")),
        (eq_source, us_m.get("index_matrix")),
        (gold_source, (markets.get("gold_mirror_readonly") or {}).get("index_matrix")),
        (gold_source, gold_snap.get("index_matrix")),
        (eq_source, linkages.get("macro_index_matrix")),
        (eq_source, nonus_benchmarks),
    ):
        for row in rows if isinstance(rows, list) else ():
            if not isinstance(row, dict):
                continue
            for field in ("id", "kline_id", "code", "name"):
                key = str(row.get(field) or "").strip().upper()
                if key:
                    overrides[key] = row, source

    # These are per-source alternatives, with optional change and date fields from that same observation.
    scalar_fields = {
        "idx_sh000001": ((a_m, "benchmark_sse"),),
        "idx_sh000300": ((a_m, "benchmark_csi300"),),
        "idx_sh000922": ((a_m, "benchmark_csi_dividend"),),
        "idx_hkHSI": ((hk_m, "benchmark_hsi"),),
        "idx_hkHSTECH": ((hk_m, "benchmark_hstech"),),
        "idx_hkHSCEI": ((hk_m, "benchmark_hscei"),),
        "idx_HSAHP": ((hk_m, "hsahp_index"),),
        "rate_CN10Y": ((cn_rates, "cgb10y_pct", "", "cgb10y_official_curve_date"), (rates, "cgb10y_pct"), (a_m, "cgb10y_pct")),
        "rate_CN30Y": ((cn_rates, "cgb30y_pct", "", "cgb30y_official_curve_date"), (rates, "cgb30y_pct")),
        "rate_CN2Y": ((cn_rates, "cgb2y_pct", "", "cgb2y_official_curve_date"), (rates, "cgb2y_pct")),
        "rate_US2Y": ((rates, "us2y_pct"), (gold_snap, "us2y_pct")),
        "rate_US30Y": ((rates, "us30y_pct"), (gold_snap, "us30y_pct")),
        "rate_DFII10": ((rates, "dfii10_pct"), (gold_snap, "dfii10_live_pct")),
        "idx_SPX": ((us_m, "benchmark_sp500"),),
        "idx_NDX": ((gold_snap, "ndx_close", "ndx_change_pct"),),
        "idx_DJI": ((gold_snap, "dow_close", "dow_change_pct"),),
        "idx_VIX": ((gold_snap, "vix_close", "vix_change_pct"), (brake, "vix_close")),
        "cmd_XAU": ((gold_snap, "spot_gold_ny_close_usd", "spot_gold_ny_change_pct", "spot_gold_ny_close_date"),),
        "cmd_GC": ((gold_snap, "comex_front_settle_usd"),),
        "cmd_AU0": ((gold_snap, "shfe_gold_day_rmb"), (gold_snap, "shfe_gold_night_rmb")),
        "cmd_Au9999": ((gold_snap, "sge_au9999_day_rmb", "sge_au9999_day_change_pct"),),
        "cmd_XAG": ((gold_snap, "spot_silver_ny_close_usd"), (gold_snap, "spot_silver_usd")),
        "cmd_AG0": ((gold_snap, "shfe_silver_day_rmb_kg", "shfe_silver_day_change_pct"), (gold_snap, "shfe_silver_night_rmb_kg")),
        "cmd_OIL": ((comm, "brent_usd", "brent_chg_pct"), (gold_snap, "brent_settle_usd", "brent_change_pct")),
        "cmd_CL": ((comm, "wti_usd"), (gold_snap, "wti_settle_usd", "wti_change_pct")),
        "cmd_HG": ((comm, "comex_copper_usd_lb", "comex_copper_chg_pct"),),
        "fx_DXY": ((rates, "dxy"), (gold_snap, "dxy", "dxy_change_pct")),
        "rate_US10Y": ((rates, "us10y_pct"), (us_m, "us10y_pct")),
        "fx_USDCNH": ((rates, "usd_cnh"),),
        "fx_USDJPY": ((rates, "usd_jpy"), (brake, "usdjpy_level")),
        "crypto_BTC": ((comm, "btc_usd", "btc_chg_pct"), (gold_snap, "btc_usd", "btc_change_pct")),
    }

    result: dict[str, list[dict[str, Any]]] = {}
    for group, specs in _MULTI_INDEX_SPECS.items():
        rows = []
        for rank, spec in enumerate(specs, start=1):
            sid = spec["id"]
            stock_market = cash_index_markets.get(group) or fund_listing_markets.get(sid)
            close_delay_minutes = 15 if sid == "idx_VIX" else 0
            override, source = (
                overrides.get(sid.upper()) or overrides.get(spec["code"].upper())
                or overrides.get(spec["name"].upper()) or ({}, "")
            )
            value = _safe_float(override.get("value"))
            if value is None:
                value = _safe_float(override.get("close"))
            observation = None
            if value is not None:
                change = _safe_float(override.get("change_pct"))
                if change is None:
                    change = _safe_float(override.get("chg_pct"))
                stamp = str(override.get("as_of") or override.get("quote_date") or "")
                observed_day = _valid_iso_date(_extract_iso_date(stamp))
                status = "沿用报价" if override.get("stale") is True else _quote_status(str(override.get("quote_status") or stamp))
                observed_at = _quote_timestamp(stamp, observed_day)
                if observed_at is not None and cutoff_time is not None:
                    in_time = observed_at <= cutoff_time
                elif observed_day and cutoff_time is not None and stock_market and status in ("官收", "收盘参考"):
                    in_time = _closing_quote_available(
                        observed_day, stock_market, cutoff, calendar, close_delay_minutes=close_delay_minutes,
                    )
                else:
                    in_time = not cutoff_day or observed_day <= cutoff_day
                if in_time:
                    observation = value, change, observed_day, status, str(override.get("source_label") or source)

            catalog = cat_by_id.get(sid, {})
            catalog_value = _safe_float(catalog.get("latest_close"))
            catalog_day = _valid_iso_date(catalog.get("latest_date"))
            available = (
                not cutoff
                or (catalog_day and cutoff_day and catalog_day <= cutoff_day
                    and (not stock_market or _closing_quote_available(
                        catalog_day, stock_market, cutoff, calendar, close_delay_minutes=close_delay_minutes,
                    )))
            )
            series_observation = None
            if catalog_value is not None and available:
                series_observation = (
                    catalog_value, _safe_float(catalog.get("change_pct")), catalog_day,
                    "沿用报价" if catalog.get("stale") is True else "日线参考", _kline_source_label(catalog.get("provider")),
                )
            if observation is None and sid not in ("rate_CN10Y", "rate_CN30Y", "idx_HSAHP"):
                observation = series_observation
            if observation is None:
                for record, key, *fields in scalar_fields.get(sid, ()):
                    value = _safe_float(record.get(key))
                    if value is None:
                        continue
                    change = _safe_float(record.get(fields[0])) if fields else None
                    observed_day = _valid_iso_date(record.get(fields[1])) if len(fields) > 1 else ""
                    if cutoff_day and observed_day > cutoff_day:
                        continue
                    status = "收盘参考" if key == "spot_gold_ny_close_usd" else "盘口待核"
                    observation = value, change, observed_day, status, gold_source if record is gold_snap else eq_source
                    break
            value, change, observed_day, status, source = observation or series_observation or (None, None, "", "报价待核", "来源待核")
            rows.append({
                "rank": rank, "id": sid, "code": spec["code"], "name": spec["name"], "short": spec["short"],
                "tier": spec["tier"], "value": value,
                "value_disp": _fmt_num(value, spec["fmt"], prefix=spec["prefix"], suffix=spec["suffix"]),
                "change_pct": change, "has_kline": bool(catalog),
                "quote_date": observed_day, "quote_status": status, "quote_source": source,
            })
        result[group] = rows
    return result


def _render_vix_sparkline_svg(gold_snap: dict[str, Any]) -> str:
    """Use the same VIX session closes as the gold entry gates."""
    pts: list[float] = []
    for row in gold_snap.get("vix_10d_session_closes") or []:
        if isinstance(row, dict):
            v = _safe_float(row.get("close"))
            if v is not None and v > 0:
                pts.append(v)
    if len(pts) < 2:
        return ""

    w, h = 84.0, 22.0
    lo = min(min(pts), 18.0) - 1.5
    hi = max(max(pts), 31.0) + 1.5
    span = max(hi - lo, 2.0)

    def _y(v: float) -> float:
        return round(2.0 + ((hi - v) / span) * (h - 4.0), 1)

    step = (w - 6.0) / max(1, len(pts) - 1)
    coords = [f"{round(3.0 + i * step, 1)},{_y(v)}" for i, v in enumerate(pts)]
    y_thr = _y(30.0)
    last_x = round(3.0 + (len(pts) - 1) * step, 1)
    last_y = _y(pts[-1])
    stroke_col = "#c81e1e" if pts[-1] >= 30.0 else ("#a85d04" if pts[-1] >= 24.0 else "#0d7a5f")
    return (
        f'<svg class="vix-spark-svg" viewBox="0 0 84 22" width="84" height="22" aria-hidden="true">'
        f'<line x1="2" y1="{y_thr}" x2="82" y2="{y_thr}" stroke="#c81e1e" stroke-opacity="0.45" stroke-width="0.9" stroke-dasharray="2 2"/>'
        f'<polyline fill="none" stroke="{stroke_col}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" points="{" ".join(coords)}"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="2.1" fill="{stroke_col}"/>'
        f"</svg>"
    )


def _render_crisis_ribbon(
    gold_snap: dict[str, Any],
    eq_state: dict[str, Any],
    gold_blocked: bool,
) -> str:
    """Render top-of-page 7-pill 3-second Macro Weather & Crisis Brake Ribbon right under homepage hero."""
    linkages = eq_state.get("cross_market_linkages") or {}
    rates = linkages.get("rates_fx_chain") or {}
    comm = linkages.get("commodity_mirror") or {}
    brake = linkages.get("crisis_correlation_brake") or {}
    rb_core = eq_state.get("rates_bonds_core") if isinstance(eq_state.get("rates_bonds_core"), dict) else {}
    rb_cn = rb_core.get("cn_rates") if isinstance(rb_core.get("cn_rates"), dict) else {}
    rb_us = rb_core.get("us_rates") if isinstance(rb_core.get("us_rates"), dict) else {}

    vix_val = _safe_float(gold_snap.get("vix_close"))
    us10y_val = _safe_float(rb_us.get("us10y_pct")) or _safe_float(rates.get("us10y_pct"))
    us10y_live = _safe_float(rb_us.get("us10y_asia_live_pct")) or _safe_float(rates.get("us10y_live_pct"))
    cgb10y_val = _safe_float(rb_cn.get("cgb10y_pct")) or _safe_float(rates.get("cgb10y_pct")) or _safe_float((eq_state.get("markets") or {}).get("a_share", {}).get("cgb10y_pct"))
    spread_bp = _safe_float(rb_core.get("cn_us_10y_spread_bp"))
    if spread_bp is None:
        spread_bp = _safe_float(rates.get("cn_us_10y_spread_bp"))
    if spread_bp is None and cgb10y_val is not None and us10y_val is not None:
        spread_bp = round((cgb10y_val - us10y_val) * 100.0)
    brent_val = _safe_float(comm.get("brent_usd")) or _safe_float(gold_snap.get("brent_settle_usd"))
    brent_live = _safe_float(comm.get("brent_live_usd"))
    jpy_val = _safe_float(brake.get("usdjpy_level")) or _safe_float(rates.get("usd_jpy"))
    jpy_3d = _safe_float(brake.get("usdjpy_3d_change_pct"))
    jpy_3d_txt = f" · 3日{jpy_3d:+.1f}%" if jpy_3d is not None else ""
    btc_val = _safe_float(comm.get("btc_usd")) or _safe_float(gold_snap.get("btc_usd"))
    spark_svg = _render_vix_sparkline_svg(gold_snap)

    vix_cls = "cr-neutral"
    if vix_val is not None:
        vix_cls = "cr-danger" if vix_val >= 30.0 else "cr-warn" if vix_val >= 24.0 else "cr-ok"
    us10y_cls = "cr-danger" if (us10y_val is not None and us10y_val >= 5.25) else ("cr-warn" if (us10y_val is not None and us10y_val >= 4.7) else "cr-ok")
    us10y_sub = (
        f"实盘 {us10y_live:.2f}% · 红线 5.25%"
        if (us10y_val is not None and us10y_live is not None and abs(us10y_live - us10y_val) >= 0.01)
        else "官收基准 · 红线 5.25%"
    )
    brent_sub = (
        f"官结 · 实盘 ${brent_live:.2f}"
        if (brent_val is not None and brent_live is not None and abs(brent_live - brent_val) >= 0.05)
        else "通胀脉冲锚"
    )
    spread_cls = "cr-danger" if (spread_bp is not None and spread_bp <= -350.0) else ("cr-warn" if (spread_bp is not None and spread_bp <= -250.0) else "cr-ok")
    spread_disp = f"{int(round(spread_bp)):+d}bp" if spread_bp is not None else "待核"
    cgb_sub = f"中债 {cgb10y_val:.2f}% · 汇损锚" if cgb10y_val is not None else "中美利差 · 汇损锚"
    jpy_cls = "cr-danger" if (jpy_val is not None and jpy_val >= 160.0) else ("cr-warn" if (jpy_val is not None and jpy_val >= 155.0) else "cr-ok")
    gold_lbl = "红灯观察·暂不新买" if gold_blocked else str(gold_snap.get("tier_label") or "按档分批").split("（")[0]
    gold_cls = "cr-danger" if gold_blocked else "cr-ok"

    return (
        '<section class="crisis-ribbon" aria-label="全球宏观风控 3 秒状态带">'
        '<div class="crisis-ribbon-head">'
        '<span class="crisis-ribbon-title">🛡️ 3 秒宏观天气与危机熔断带（定价因子 · 非持仓市场）</span>'
        '<a class="crisis-ribbon-link" href="#sec-risk-radar">看 3+1 熔断详解 ↓</a>'
        "</div>"
        '<div class="crisis-ribbon-grid">'
        f'<a class="cr-pill {vix_cls}" href="charts.html#sym=idx_VIX">'
        '<span class="cr-lbl">VIX 恐慌</span>'
        f'<span class="cr-val">{_fmt_num(vix_val, ".2f")}</span>'
        f'<span class="cr-spark">{spark_svg}</span>'
        "</a>"
        f'<a class="cr-pill {us10y_cls}" href="charts.html#sym=rate_US10Y">'
        '<span class="cr-lbl">美债 10Y</span>'
        f'<span class="cr-val">{_fmt_num(us10y_val, ".2f", suffix="%")}</span>'
        f'<span class="cr-sub">{esc(us10y_sub)}</span>'
        "</a>"
        f'<a class="cr-pill {spread_cls}" href="charts.html#sym=rate_CN10Y">'
        '<span class="cr-lbl">中美 10Y 利差</span>'
        f'<span class="cr-val">{esc(spread_disp)}</span>'
        f'<span class="cr-sub">{esc(cgb_sub)}</span>'
        "</a>"
        f'<a class="cr-pill cr-neutral" href="charts.html#sym=cmd_OIL">'
        '<span class="cr-lbl">布伦特原油</span>'
        f'<span class="cr-val">{_fmt_num(brent_val, ".2f", prefix="$")}</span>'
        f'<span class="cr-sub">{esc(brent_sub)}</span>'
        "</a>"
        f'<a class="cr-pill {jpy_cls}" href="charts.html#sym=fx_USDJPY">'
        '<span class="cr-lbl">美元 / 日元</span>'
        f'<span class="cr-val">{_fmt_num(jpy_val, ".2f")}</span>'
        f'<span class="cr-sub">盯 160{esc(jpy_3d_txt)}</span>'
        "</a>"
        f'<a class="cr-pill {gold_cls}" href="charts.html#sym=cmd_XAU">'
        '<span class="cr-lbl">黄金风控锁</span>'
        f'<span class="cr-val">{esc(gold_lbl)}</span>'
        '<span class="cr-sub">点看现货金 K 线</span>'
        "</a>"
        f'<a class="cr-pill cr-compliance" href="charts.html#sym=crypto_BTC">'
        '<span class="cr-lbl">BTC 流动风向</span>'
        f'<span class="cr-val">{_fmt_num(btc_val, ",.0f", prefix="$")}</span>'
        '<span class="cr-badge-readonly">仅作流动风向 · 境内禁交易</span>'
        "</a>"
        "</div>"
        "</section>"
    )


def _render_idx_tile(row: dict[str, Any], tab_key: str) -> str:
    chg = row.get("change_pct")
    if isinstance(chg, (int, float)) and isfinite(chg):
        arrow = "▲" if chg >= 0 else "▼"
        c_cls = "chg-up" if chg >= 0 else "chg-dn"
        chg_html = f'<span class="idx-tile-chg {c_cls}">{arrow} {chg:+.2f}%</span>'
    else:
        chg_html = '<span class="idx-tile-chg">涨跌待核</span>'
    return (
        f'<button type="button" class="idx-tile" data-kline-jump="{esc(row["id"])}" '
        f'data-kline-tab="{esc(tab_key)}" title="点击查看 {esc(row["name"])} 交互 K 线">'
        f'<span class="idx-tile-top"><span class="idx-tile-name">{esc(row["short"])}</span>'
        f'<span class="idx-tile-code">{esc(row["code"])}</span></span>'
        f'<span class="idx-tile-bot"><span class="idx-tile-val">{esc(row["value_disp"])}</span>{chg_html}</span>'
        f'<span class="sec-sub">{esc(_quote_provenance(row))}</span>'
        "</button>"
    )


def _render_kline_quote_pill(row: dict[str, Any], *, active: bool) -> str:
    provenance = esc(_quote_provenance(row))
    return (
        f'<button type="button" class="kline-sym-pill{" active" if active else ""}" '
        f'data-deck-sym="{esc(row["id"])}">'
        f'{esc(row["short"])} <span class="kline-pill-val">{esc(row["value_disp"])}</span>'
        f'<span class="sec-sub"><br>{provenance}</span></button>'
    )


def _render_market_index_matrix(
    rows: list[dict[str, Any]],
    tab_key: str,
    *,
    visible_count: int = 8,
    extra_badge_html: str = "",
) -> str:
    if not rows:
        return ""
    head_rows = rows[:visible_count]
    tail_rows = rows[visible_count:]
    head_html = "".join(_render_idx_tile(r, tab_key) for r in head_rows) + extra_badge_html
    tail_html = ""
    if tail_rows:
        tail_names = " · ".join(r["short"] for r in tail_rows)
        tail_tiles = "".join(_render_idx_tile(r, tab_key) for r in tail_rows)
        tail_kind = "行业与情绪指数" if tab_key == "us_stock" else "宽基与风格指数"
        tail_html = (
            '<details class="idx-more">'
            f'<summary class="idx-more-sum">展开其余 {len(tail_rows)} 项{tail_kind}（{esc(tail_names)}）</summary>'
            f'<div class="m-index-matrix m-index-matrix-sub">{tail_tiles}</div>'
            "</details>"
        )
    return f'<div class="m-index-matrix">{head_html}</div>{tail_html}'


def _render_home_kline_deck(multi_idx: dict[str, list[dict[str, Any]]], total_kline_count: int = 480) -> str:
    tabs = (
        ("a_share", "🇨🇳 A股多指数（上证先导）", multi_idx.get("a_share") or []),
        ("hk_stock", "🇭🇰 港股多指数", multi_idx.get("hk_stock") or []),
        ("us_stock", "🇺🇸 美股多指数", multi_idx.get("us_stock") or []),
        ("non_us_global", "🌏 日欧台韩印非美", multi_idx.get("non_us_global") or []),
        ("bonds_reits", "🏦 中美债市与REITs", multi_idx.get("bonds_reits") or []),
        ("gold_macro", "🥇 黄金大宗与汇率", (multi_idx.get("gold") or []) + (multi_idx.get("macro") or [])),
    )
    tab_btns = "".join(
        f'<button type="button" role="tab" aria-selected="{"true" if i == 0 else "false"}" class="kline-deck-tab{" active" if i == 0 else ""}" data-deck-tab="{esc(k)}">{lbl}</button>'
        for i, (k, lbl, _) in enumerate(tabs)
    )
    panels = []
    for i, (k, _, rows) in enumerate(tabs):
        pills = "".join(
            _render_kline_quote_pill(r, active=(i == 0 and j == 0))
            for j, r in enumerate(rows)
        )
        panels.append(f'<div class="kline-pill-strip" data-deck-panel="{esc(k)}"{"" if i == 0 else " hidden"}>{pills}</div>')
    cnt_lbl = f"{total_kline_count}+" if total_kline_count > 0 else "480+"
    return (
        '<section class="kline-deck" id="sec-kline-deck" data-kline-deck="home" aria-label="全球六大板块多指数与债金大宗交互 K 线看板">'
        '<div class="sec-head" style="margin-top:0;">'
        '<div><h2>📈 全球六大板块交互 K 线看板（上证指数先导 · 含非美与中美债率）</h2>'
        '<span class="sec-sub">纯原生零外链画布 · 支持 MA/BOLL/EMA/MACD/RSI/KDJ/ATR/BIAS 与小白 10 秒技术面体检</span></div>'
        f'<a class="btn btn-sm btn-primary" data-deck-full-link="1" href="charts.html#sym=idx_sh000001">打开全市场 {cnt_lbl} 标的 K 线终端 →</a>'
        "</div>"
        f'<div class="kline-deck-tabs" role="tablist">{tab_btns}</div>'
        f'{"".join(panels)}'
        '<div class="kline-card">'
        '<div class="kline-mount" data-kline-deck-mount="1" data-init-sym="idx_sh000001" data-kline-height="340"></div>'
        "</div>"
        "</section>"
    )


def _render_daily_kline_strip(
    market: str,
    multi_idx: dict[str, list[dict[str, Any]]],
    *,
    base_prefix: str = "../",
) -> str:
    """Render compact Multi-Index Overview Strip + Interactive K-Line Panel at top of daily/*.html."""
    mkt_map = {
        "a-share": ("a_share", "🇨🇳 A 股多指数参考行情与交互 K 线（上证先导）", "idx_sh000001"),
        "hk-stock": ("hk_stock", "🇭🇰 港股多指数参考行情与交互 K 线", "idx_hkHSI"),
        "us-stock": ("us_stock", "🇺🇸 美股多指数参考行情与交互 K 线", "idx_SPX"),
        "gold": ("gold", "🥇 黄金与贵金属多基准交互 K 线", "cmd_XAU"),
    }
    grp_key, heading, default_sym = mkt_map.get(market, ("a_share", "多指数交互 K 线", "idx_sh000001"))
    rows = list(multi_idx.get(grp_key) or [])
    if not rows:
        return ""
    init_sym = rows[0]["id"] if rows else default_sym
    pills = "".join(
        _render_kline_quote_pill(r, active=(j == 0))
        for j, r in enumerate(rows)
    )
    return (
        f'<section class="kline-daily-strip no-print" data-kline-deck="daily-{esc(market)}" aria-label="{esc(heading)}">'
        '<div class="kline-daily-head">'
        f'<strong>{esc(heading)}</strong>'
        f'<a class="btn btn-sm" data-deck-full-link="1" href="{esc(base_prefix)}charts.html#sym={esc(init_sym)}">全屏终端 ↗</a>'
        "</div>"
        f'<div class="kline-pill-strip" data-deck-panel="{esc(grp_key)}">{pills}</div>'
        f'<div class="kline-mount" data-kline-deck-mount="1" data-init-sym="{esc(init_sym)}" data-kline-height="320"></div>'
        "</section>"
    )


def _render_wallet_calculator(
    gold_snap: dict[str, Any], eq_state: dict[str, Any], kline_manifest: dict[str, Any] | None = None,
) -> str:
    """Render the wallet calculator with the current equity and gold limits."""
    gold_new_buy = (gold_snap or {}).get("new_buy_allowed") is True
    gold_tier = str((gold_snap or {}).get("tier_code") or "").strip()
    gold_allowed = gold_new_buy and (gold_tier != "Tier 0")
    markets = (eq_state or {}).get("markets") or {}
    a_cap = _safe_float((markets.get("a_share") or {}).get("equity_cap_pct"))
    short_bond_quote = _edition_quote_catalog(kline_manifest, eq_state).get("etf_511360", {})
    short_bond_close = _safe_float(short_bond_quote.get("latest_close"))
    quote_date = _valid_iso_date(short_bond_quote.get("latest_date"))
    has_quote = (
        short_bond_close is not None and short_bond_close > 0
        and short_bond_quote.get("stale") is False
        and (short_bond_quote.get("code"), short_bond_quote.get("currency")) == ("511360", "CNY")
        and bool(quote_date)
        and _closing_quote_available(
            quote_date, "a-share", str(eq_state.get("as_of_cst") or ""), eq_state.get("calendar_overrides"),
        )
    )
    payload = {
        "gold_new_buy_allowed": gold_allowed,
        "eq_cap_pct": a_cap,
        "gold_cap_pct": 10,
        "short_bond_lot_rmb": round(short_bond_close * 100, 2) if has_quote else None,
        "short_bond_quote_date": quote_date if has_quote else None,
    }
    safe_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    gold_status_pill = (
        '<span class="wcalc-gold-pill wcalc-gold-open">黄金允许按档分批（≤10%–15%）</span>'
        if gold_allowed
        else '<span class="wcalc-gold-pill wcalc-gold-locked">🛑 黄金红灯观察锁：新仓严格 0 元</span>'
    )
    return (
        '<div class="wcalc-card" data-wallet-calc="1">'
        '<div class="wcalc-head">'
        '<div><div class="wcalc-title">💰 我的钱包一键试算器（直连今日红绿灯 · 纯本地计算零上传）</div>'
        '<div class="sec-sub">输入可用闲钱与风险偏好，自动按当下大盘红绿灯与 4 条风控硬规则拆算人民币落地方案</div></div>'
        f'<div class="wcalc-head-right">{gold_status_pill}'
        '<button type="button" class="btn btn-sm" data-wcalc-copy="1">复制试算方案</button></div>'
        "</div>"
        '<div class="wcalc-controls">'
        '<div class="wcalc-ctrl-group">'
        '<label class="wcalc-lbl" for="wcalc-amt-input">可投资闲钱（万元）</label>'
        '<div class="wcalc-amt-row">'
        '<input type="number" id="wcalc-amt-input" class="wcalc-input" data-wcalc-amount="1" min="0.1" max="10000" step="0.5" value="10">'
        '<button type="button" class="filter-pill" data-wcalc-preset="1">1万</button>'
        '<button type="button" class="filter-pill" data-wcalc-preset="5">5万</button>'
        '<button type="button" class="filter-pill active" data-wcalc-preset="10">10万</button>'
        '<button type="button" class="filter-pill" data-wcalc-preset="50">50万</button>'
        '<button type="button" class="filter-pill" data-wcalc-preset="100">100万</button>'
        "</div>"
        "</div>"
        '<div class="wcalc-ctrl-group">'
        '<span class="wcalc-lbl">个人风险偏好</span>'
        '<div class="wcalc-amt-row">'
        '<button type="button" class="filter-pill" data-wcalc-profile="conservative">保守稳健</button>'
        '<button type="button" class="filter-pill active" data-wcalc-profile="balanced">均衡成长</button>'
        '<button type="button" class="filter-pill" data-wcalc-profile="aggressive">积极进取</button>'
        "</div>"
        "</div>"
        "</div>"
        '<div class="wcalc-buckets" data-wcalc-buckets="1"></div>'
        '<div class="wcalc-rules-box">'
        '<div class="wcalc-rules-title">⚙️ 自动触发风控纪律（随金额与大盘实时联动）</div>'
        '<ul class="wcalc-rules-list" data-wcalc-rules="1"></ul>'
        "</div>"
        f'<script id="wallet-calc-data" type="application/json">{safe_json}</script>'
        "</div>"
    )


def _build_ah_matrix_payload(
    ah_benchmarks: list[dict[str, Any]] | None,
    stocks: list[dict[str, Any]],
    *,
    kline_manifest: dict[str, Any] | None = None,
    hkd_cny_mid: float | None = None,
    fx_date: str = "",
    as_of_date: str = "",
    as_of_cst: str = "",
    edition_id: str | None = None,
    calendar_overrides: list[dict] | None = None,
) -> list[dict[str, Any]]:
    """Calculate same-day premiums and compare dividends only on a documented common basis."""
    by_code: dict[str, dict[str, Any]] = {}
    for st in stocks:
        cd = str(st.get("code") or "").strip().upper()
        if cd:
            by_code[cd] = st

    fx_date = _valid_iso_date(fx_date)
    quote_day = date.fromisoformat(fx_date) if fx_date else None
    cutoff_iso = _valid_iso_date(as_of_date)
    evidence_day = date.fromisoformat(cutoff_iso) if cutoff_iso else quote_day
    fx_rate = _positive_quote(hkd_cny_mid)
    manifest = kline_manifest or {}
    catalog = (manifest.get("catalog") or []) if edition_id is None or manifest.get("edition_id") == edition_id else []
    by_kline_id = {
        item["id"]: item for item in catalog
        if isinstance(item, dict) and isinstance(item.get("code"), str)
        and item.get("id") == f'stk_{item["code"]}'
        and (item.get("market"), item.get("currency")) in {("a-share", "CNY"), ("hk-stock", "HKD")}
    }

    rows: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for bm in ah_benchmarks or []:
        if not isinstance(bm, dict):
            continue
        name = str(bm.get("name") or "").strip()
        a_cd = str(bm.get("a") or "").strip().upper()
        h_cd = str(bm.get("h") or "").strip().upper()
        if not name or not a_cd or not h_cd:
            continue
        pair_key = (a_cd, h_cd)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        a_st = by_code.get(a_cd)
        h_st = by_code.get(h_cd)
        cand_a_sym = f"stk_{a_cd}"
        cand_h_sym = f"stk_{h_cd}"
        a_quote = by_kline_id.get(cand_a_sym, {})
        h_quote = by_kline_id.get(cand_h_sym, {})
        exchange_quotes = parse_exchange_closes(bm, evidence_day)
        if exchange_quotes.get("a", {}).get("latest_date") == fx_date:
            a_quote = exchange_quotes["a"]
        if exchange_quotes.get("h", {}).get("latest_date") == fx_date:
            h_quote = exchange_quotes["h"]
        a_close = _safe_float(a_quote.get("latest_close"))
        h_close = _safe_float(h_quote.get("latest_close"))
        h_cny = _safe_float(h_close * fx_rate) if h_close is not None and fx_rate is not None else None
        paired_quotes = (
            bool(fx_date) and (not cutoff_iso or fx_date <= cutoff_iso)
            and (not as_of_cst or all(
                _closing_quote_available(fx_date, market, as_of_cst, calendar_overrides)
                for market in ("a-share", "hk-stock")
            ))
            and fx_date == a_quote.get("latest_date") == h_quote.get("latest_date")
            and a_quote.get("stale") is False and h_quote.get("stale") is False
            and a_close is not None and a_close > 0
            and h_close is not None and h_close > 0
            and h_cny is not None and h_cny > 0
            and a_quote.get("currency") == "CNY" and h_quote.get("currency") == "HKD"
        )
        prem = _safe_float((a_close / h_cny - 1) * 100) if paired_quotes else None
        a_div = h_div = None
        dividend_sources: dict[str, list[str]] = {}
        dividend_basis = "股息公告待核"
        dividend_period = ""
        h_local_cash = False
        no_cash = False
        h_not_eligible = False
        cash = bm.get("cash_dividends")
        if evidence_day is not None and cash is not None:
            try:
                a_cash, h_cash = parse_pair(cash)
            except ValueError:
                pass  # Source preflight reports the validation error.
            else:
                last_publication = max(a_cash.published, h_cash.published)
                if last_publication <= evidence_day:
                    a_div = h_div = None
                    dividend_period = f"{a_cash.start} 至 {a_cash.end}"
                    dividend_sources = {"a": list(a_cash.sources), "h": list(h_cash.sources)}
                    no_cash = a_cash.amount == h_cash.amount == 0
                    h_not_eligible = h_cash.unavailable_status is not None
                    h_local_cash = not (h_cash.southbound_cny or no_cash or h_not_eligible)
                    if h_not_eligible:
                        reason = (
                            "H 股上市晚于该期间最后分红登记日"
                            if h_cash.unavailable_status == "listed_after_record_date"
                            else "发行人本期分派范围不含 H 股"
                        )
                        dividend_basis = f"普通现金股息 · {dividend_period} · {reason}"
                    elif no_cash:
                        dividend_basis = f"两地均未派普通现金股息 · {dividend_period}"
                    elif h_local_cash:
                        dividend_basis = f"普通现金股息 · {dividend_period} · H 股为香港登记股东口径，港股通待核"
                    else:
                        dividend_basis = f"普通现金股息 · {dividend_period} · H 股按港股通人民币分派"
                    if no_cash:
                        a_div = h_div = 0.0
                    elif paired_quotes and last_publication <= quote_day <= evidence_day:
                        h_reference_price = h_cny if h_cash.southbound_cny else h_close
                        a_div = _safe_float(a_cash.amount / a_close * 100)
                        if h_cash.amount is not None:
                            h_div = _safe_float(h_cash.amount / h_reference_price * 100)
                    if a_div is None or (h_div is None and not h_not_eligible):
                        dividend_basis += " · 收益率待核"
        withholding_needs_review = (
            bm.get("requires_withholding_check") is True
            or bm.get("is_red_chip_28") is True
            or h_cd in _SPECIAL_WITHHOLDING_CODES
            or ("check_withholding" in str(bm.get("preferred_channel") or "").lower())
        )
        h_tax = 20 if dividend_sources and not (withholding_needs_review or h_local_cash or no_cash or h_not_eligible) else None
        h_tax_pending = bool(withholding_needs_review and dividend_sources and not (h_local_cash or no_cash or h_not_eligible))
        if h_tax_pending:
            dividend_basis += " · 源头代扣待核"
        h_net = h_div * (1.0 - h_tax / 100.0) if h_div is not None and h_tax is not None else None
        spread = (
            round(h_net - a_div, 2)
            if dividend_sources and a_div is not None and h_net is not None and not no_cash
            else None
        )

        is_warn = bool((a_st and a_st.get("color") == "r") or (h_st and h_st.get("color") == "r"))
        if is_warn:
            v_lbl, v_tone = "高危/事件警示", "red"
        elif prem is not None and prem < 0:
            v_lbl, v_tone = "A 股倒挂占优", "green"
        elif spread is not None and spread > 0.25:
            v_lbl, v_tone = "港股通税后占优", "blue"
        elif prem is not None and prem >= 50:
            v_lbl, v_tone = "离岸 H 股显著折价", "amber"
        elif spread is not None and spread < 0:
            v_lbl, v_tone = "A 股免税股息更佳", "green"
        elif prem is None:
            v_lbl, v_tone = "等待同日比价", "neutral"
        elif no_cash:
            v_lbl, v_tone = "两地本期均未派息", "neutral"
        elif h_not_eligible:
            v_lbl, v_tone = "H 股本期未参与分派", "neutral"
        elif h_local_cash:
            v_lbl, v_tone = "港股通分派待核", "neutral"
        elif spread is not None:
            v_lbl, v_tone = "双地均衡比选", "neutral"
        else:
            v_lbl, v_tone = "股息口径待核", "neutral"

        rows.append(
            {
                "name": name,
                "a_code": a_cd,
                "h_code": h_cd,
                "a_key": f"a-share:{a_cd}" if a_st else "",
                "h_key": f"hk-stock:{h_cd}" if h_st else "",
                "a_sym_id": cand_a_sym if cand_a_sym in by_kline_id else "",
                "h_sym_id": cand_h_sym if cand_h_sym in by_kline_id else "",
                "a_price": f"{a_close:g} 元" if paired_quotes else "—",
                "h_price": f"{h_close:g} 港元" if paired_quotes else "—",
                "quote_date": fx_date if paired_quotes else "",
                "quote_urls": {
                    side: quote["source_url"] for side, quote in exchange_quotes.items()
                    if paired_quotes and quote["latest_date"] == fx_date
                },
                "quote_replay_urls": {
                    side: quote["replay_url"] for side, quote in exchange_quotes.items()
                    if paired_quotes and quote["latest_date"] == fx_date and quote["replay_url"]
                },
                "quote_source": (
                    f"A {_kline_source_label(a_quote.get('provider'))} · H {_kline_source_label(h_quote.get('provider'))}"
                    if paired_quotes else ""
                ),
                "ah_premium_pct": round(prem, 1) if prem is not None else None,
                "a_div_pct": round(a_div, 2) if a_div is not None else None,
                "h_div_pct": round(h_div, 2) if h_div is not None else None,
                "h_tax_rate_pct": h_tax,
                "h_connect_after_tax_div": round(h_net, 2) if h_net is not None else None,
                "h_local_cash": h_local_cash,
                "h_tax_pending": h_tax_pending,
                "no_cash_dividend": no_cash,
                "h_not_eligible": h_not_eligible,
                "net_div_spread": spread,
                "dividend_period": dividend_period,
                "dividend_sources": dividend_sources,
                "dividend_basis": dividend_basis,
                "verdict_label": v_lbl,
                "verdict_tone": v_tone,
            }
        )
    rows.sort(key=lambda r: (r["ah_premium_pct"] is None, -(r["ah_premium_pct"] or 0.0)))
    return rows


def _render_qdii_comparison_section(
    channels_data: dict[str, Any] | None,
    *,
    compact: bool = False,
) -> str:
    """Render QDII On-Exchange Premium vs Official Direct-App vs Alipay Comparison Matrix + Breakeven Calculator."""
    raw = None
    if isinstance(channels_data, dict):
        raw = channels_data.get("qdii_channel_comparison")
        if not raw:
            for ch in channels_data.get("channels") or []:
                if isinstance(ch, dict) and ch.get("id") == "qdii_mrf" and ch.get("qdii_channel_comparison"):
                    raw = ch.get("qdii_channel_comparison")
                    break
    rows = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []

    if compact:
        _track_buckets = (
            ("纳斯达克", "纳指100"),
            ("标普", "标普500"),
            ("日本", "日本东证/日经"),
            ("德国", "德国/欧洲"),
            ("全球", "全球/新兴"),
        )
        picked_tracks: list[str] = []
        used_idx: set[int] = set()
        for kw, short_lbl in _track_buckets:
            for idx_r, r in enumerate(rows):
                t_raw = str(r.get("track") or "")
                if idx_r not in used_idx and (kw in t_raw or (kw == "德国" and ("欧洲" in t_raw or "法国" in t_raw)) or (kw == "全球" and ("亚太" in t_raw or "印度" in t_raw or "沙特" in t_raw))):
                    picked_tracks.append(short_lbl)
                    used_idx.add(idx_r)
                    break
        if len(picked_tracks) < min(5, len(rows)):
            seen_t = set(picked_tracks)
            for idx_r, r in enumerate(rows):
                if idx_r in used_idx:
                    continue
                t_clean = re.split(r"[（(]", str(r.get("track") or ""), maxsplit=1)[0].strip()
                if t_clean and t_clean not in seen_t:
                    picked_tracks.append(t_clean)
                    seen_t.add(t_clean)
                if len(picked_tracks) >= 5:
                    break
        sample_tracks = " · ".join(picked_tracks[:5])
        summary = (
            f"{sample_tracks}等 {len(rows)} 项赛道。比较同一份额、同一生效日的申购额度。"
            if rows else "本期分渠道限额待核。可按基金公告打开计算器试算。"
        )
        return (
            '<div class="qdii-summary-panel qdii-panel-slim" id="etf-qdii-panel">'
            '<div class="qdii-sum-main">'
            '<strong>🛡️ 境内 QDII 避坑提示：场内高溢价 vs 场外官方直销 App / 支付宝限额比价</strong>'
            f'<div class="sec-sub">{esc(summary)}</div>'
            "</div>"
            '<a class="btn btn-sm btn-primary" href="channels/qdii_mrf.html#sec-qdii-compare">打开完整 QDII 分渠道限额表与计算器 →</a>'
            "</div>"
        )

    tr_html = []
    for r in rows:
        prem_disp = str(r.get("on_exchange_premium_note") or "折溢价请核成交价及对应净值")
        direct_disp = str(r.get("direct_app_limit") or "以直销渠道当日公告为准")
        ali_disp = str(r.get("alipay_limit") or "以代销渠道当日公告为准")
        ratio_disp = str(r.get("direct_vs_alipay_ratio") or "—")
        verification_note = str(r.get("verification_note") or "").strip()
        verification_html = f'<div class="sec-sub">{esc(verification_note)}</div>' if verification_note else ""
        tr_html.append(
            "<tr>"
            f'<td><strong>{esc(r.get("track", ""))}</strong><div class="sec-sub">{esc(r.get("fund_company", ""))}</div></td>'
            f'<td><span class="code-tag">{esc(r.get("on_exchange_code", ""))}</span><div class="sec-sub">费率 {esc(r.get("on_exchange_fee", ""))} · {esc(prem_disp)}</div></td>'
            f'<td><span class="code-tag">{esc(r.get("otc_codes", ""))}</span></td>'
            f'<td><strong>{esc(direct_disp)}</strong></td>'
            f'<td>{esc(ali_disp)}</td>'
            f'<td class="nw"><span class="qdii-ratio-pill">{esc(ratio_disp)}</span></td>'
            f'<td>{esc(r.get("risk_note", ""))}{verification_html} {_policy_brief_source_links(r)}</td>'
            "</tr>"
        )
    if not tr_html:
        tr_html.append('<tr><td colspan="7">本期分渠道限额待核。</td></tr>')

    return (
        '<div class="sec-head" id="sec-qdii-compare">'
        "<h2>🧭 QDII 场内溢价 vs 场外官方直销 App / 支付宝分渠道限购全景对比</h2>"
        '<span class="sec-sub">各渠道限额以基金公告为准。先确认申购是否开放，再比较可用额度与场内折溢价。</span>'
        "</div>"
        '<div class="mobile-scroll-cue" aria-hidden="true">← 左右滑动查看完整对比 →</div>'
        '<div class="table-wrap"><table class="data-table qdii-compare-table">'
        "<thead><tr>"
        "<th>标的赛道 / 基金公司</th>"
        "<th>场内代码 / 费率 / 溢价</th>"
        "<th>场外联接代码 (A/C/I)</th>"
        "<th>官方直销 App 限额</th>"
        "<th>支付宝 / 天天限额</th>"
        "<th>直销差异倍数</th>"
        "<th>风控与退市提示</th>"
        "</tr></thead>"
        f'<tbody>{"".join(tr_html)}</tbody></table></div>'
        '<div class="qdii-calc-card" data-qdii-calc="1">'
        '<div class="qdii-calc-head">'
        '<strong>🧮 场内溢价 vs 场外排队盈亏平衡计算器</strong>'
        '<span class="sec-sub">假设当天开始按限额逐日申购、同一底层净值每天等比例上涨，比较两种买法最终买到的份额。试算忽略费用、汇率变化和闲置资金利息。</span>'
        "</div>"
        '<div class="qdii-calc-inputs">'
        '<div class="qdii-in-group">'
        '<label class="wcalc-lbl" for="qcalc-prem">当前场内折溢价率（%，折价填负数）</label>'
        '<input type="number" id="qcalc-prem" class="wcalc-input" data-qcalc-prem="1" step="any" value="5.0">'
        "</div>"
        '<div class="qdii-in-group">'
        '<label class="wcalc-lbl" for="qcalc-amt">计划投入金额（万元）</label>'
        '<input type="number" id="qcalc-amt" class="wcalc-input" data-qcalc-amt="1" min="0.000001" step="any" value="5">'
        "</div>"
        '<div class="qdii-in-group">'
        '<label class="wcalc-lbl" for="qcalc-lim">场外单日限额（元，暂停申购填 0）</label>'
        '<div class="wcalc-amt-row">'
        '<input type="number" id="qcalc-lim" class="wcalc-input" data-qcalc-lim="1" min="0" step="any" value="1000">'
        '<button type="button" class="filter-pill" data-qcalc-lim-preset="10">10元</button>'
        '<button type="button" class="filter-pill" data-qcalc-lim-preset="100">100元</button>'
        '<button type="button" class="filter-pill" data-qcalc-lim-preset="200">200元</button>'
        '<button type="button" class="filter-pill" data-qcalc-lim-preset="500">500元</button>'
        '<button type="button" class="filter-pill active" data-qcalc-lim-preset="1000">1000元</button>'
        '<button type="button" class="filter-pill" data-qcalc-lim-preset="5000">5000元</button>'
        "</div>"
        "</div>"
        "</div>"
        '<div class="qcalc-output" data-qcalc-out="1" aria-live="polite"></div>'
        "</div>"
    )


def build_charts_page(
    gold_snap: dict[str, Any],
    eq_state: dict[str, Any],
    multi_idx: dict[str, list[dict[str, Any]]],
    stocks: list[dict[str, Any]],
    etf_data: dict[str, Any] | None,
    kline_manifest: dict[str, Any] | None,
) -> str:
    """Render full-screen Interactive K-Line & Technical Indicators Terminal (charts.html)."""
    gold_blocked = (
        gold_snap.get("new_buy_allowed") is False
        or str(gold_snap.get("tier_code") or "").strip() == "Tier 0"
    )
    total_cnt = (
        int(kline_manifest.get("total_instruments", 0))
        if isinstance(kline_manifest, dict) and kline_manifest.get("total_instruments")
        else (len(stocks) + len((etf_data or {}).get("etfs") or []) + 49)
    )
    raw_gen_ts = (
        str(kline_manifest.get("generated_at_cst") or "").strip()
        if isinstance(kline_manifest, dict)
        else ""
    ) or str(eq_state.get("as_of_cst") or "").strip()
    gen_ts = fmt_cst_compact(raw_gen_ts) or raw_gen_ts

    meta_bridge: dict[str, dict[str, Any]] = {}
    for st in stocks:
        sym = f"stk_{st['code']}"
        entry: dict[str, Any] = {}
        if isinstance(st.get("anchor_low"), (int, float)):
            entry["anchor_low"] = st["anchor_low"]
            entry["anchor_high"] = st.get("anchor_high") if isinstance(st.get("anchor_high"), (int, float)) else st["anchor_low"]
        if st.get("is_gold_locked"):
            entry["gold_locked"] = True
        if entry:
            meta_bridge[sym] = entry
            meta_bridge[f"{st['market']}:{st['code']}"] = entry
    for etf in ((etf_data or {}).get("etfs") or []):
        if isinstance(etf, dict) and etf.get("gold_locked") and etf.get("code"):
            meta_bridge[f"etf_{etf['code']}"] = {"gold_locked": True}
    for g_id in ("cmd_XAU", "cmd_GC", "cmd_AU0", "cmd_Au9999", "cmd_AuTD"):
        if gold_blocked:
            fair = _safe_float(gold_snap.get("fair_value_usd"))
            sma_lo = _safe_float(gold_snap.get("sma_200w_low_usd"))
            if g_id == "cmd_XAU" and fair is not None and sma_lo is not None:
                meta_bridge[g_id] = {"anchor_low": min(fair, sma_lo), "anchor_high": max(fair, sma_lo), "gold_locked": True}
            else:
                meta_bridge[g_id] = {"gold_locked": True}

    meta_bridge["_groups"] = {
        "non_us_global": [
            r["id"] for r in (multi_idx.get("non_us_global") or []) if r.get("id")
        ] + [
            f"etf_{e['code']}"
            for e in ((etf_data or {}).get("etfs") or [])
            if isinstance(e, dict) and e.get("code") and _infer_etf_ortho(e)[1] in ("jp", "eu", "apac_em", "global") and _infer_etf_ortho(e)[0] == "equity"
        ],
        "bonds_reits": [
            r["id"] for r in (multi_idx.get("bonds_reits") or []) if r.get("id")
        ] + [
            f"etf_{e['code']}"
            for e in ((etf_data or {}).get("etfs") or [])
            if isinstance(e, dict) and e.get("code") and _infer_etf_ortho(e)[0] in ("fixed_income", "cash_mmf", "convertible_bond", "reits")
        ],
    }
    safe_bridge_json = json.dumps(meta_bridge, ensure_ascii=False).replace("</", "<\\/")

    stock_cnt = len(stocks)
    stock_cnt_lbl = f"{stock_cnt} 股" if stock_cnt > 0 else "核心股"
    stock_tab_lbl = f"{stock_cnt}股池" if stock_cnt > 0 else "核心股池"
    stock_btn_lbl = f"{stock_cnt} 股池" if stock_cnt > 0 else "核心股池"

    static_rows = []
    seen_sym_ids: set[str] = set()
    for grp_k in ("a_share", "hk_stock", "us_stock", "non_us_global", "bonds_reits", "gold"):
        for r in (multi_idx.get(grp_k) or []):
            sid = str(r.get("id") or "")
            if not sid or sid in seen_sym_ids:
                continue
            seen_sym_ids.add(sid)
            chg = r.get("change_pct")
            has_chg = isinstance(chg, (int, float)) and isfinite(chg)
            chg_txt = f"{chg:+.2f}%" if has_chg else "—"
            chg_cls = ("chg-up" if chg >= 0 else "chg-dn") if has_chg else ""
            chg_cls_attr = f" {chg_cls}" if chg_cls else ""
            static_rows.append(
                f'<div class="kline-sym-row" data-sym-id="{esc(sid)}" role="button" tabindex="0">'
                f'<div class="kline-sym-main"><div class="kline-sym-name">{esc(r["name"])}</div>'
                f'<div class="kline-sym-code">{esc(r["code"])} · {esc(_quote_provenance(r))}</div></div>'
                f'<div class="kline-sym-right"><div class="kline-sym-price">{esc(r["value_disp"])}</div>'
                f'<div class="kline-sym-chg{chg_cls_attr}">{esc(chg_txt)}</div></div>'
                "</div>"
            )
    gold_pill = (
        '<span class="compact-alert-pill">🛑 黄金红灯观察期：新仓 0%，金及金矿 K 线仅参考</span>'
        if gold_blocked
        else ""
    )
    return f"""
    <div class="sec-head" style="margin:4px 0 8px;">
      <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">
        <h1 style="margin:0;">全市场交互 K 线终端</h1>
        <span class="sec-sub">{total_cnt} 标的（六大市场多指数 · 债率 · ETF · {esc(stock_cnt_lbl)}）· 刷新 {esc(gen_ts or "最新班次")}</span>
      </div>
      {gold_pill}
    </div>

    <section class="kline-terminal-grid" data-kline-terminal="1">
      <aside class="kline-watchlist" id="kline-terminal-sidebar" aria-label="全市场 K 线标的检索">
        <div class="search-wrap" style="margin-bottom:8px;">
          <input type="search" id="kline-search" class="search-input" placeholder="搜代码 / 简称（如 000001 / 日经）" autocomplete="off">
          <button type="button" id="kline-search-clear" class="search-clear" aria-label="清空搜索" hidden>×</button>
          <kbd class="kbd-hint" aria-hidden="true">/</kbd>
        </div>
        <div class="kline-group-tabs" role="tablist" aria-label="标的分类">
          <button type="button" role="tab" aria-selected="true" class="filter-pill active" data-chart-group="a_index">A股指数(12)</button>
          <button type="button" role="tab" aria-selected="false" class="filter-pill" data-chart-group="hk_index">港股指数(5)</button>
          <button type="button" role="tab" aria-selected="false" class="filter-pill" data-chart-group="us_index">美股指数(8)</button>
          <button type="button" role="tab" aria-selected="false" class="filter-pill" data-chart-group="non_us_global">日欧台韩印非美</button>
          <button type="button" role="tab" aria-selected="false" class="filter-pill" data-chart-group="bonds_reits">中美债市与REITs</button>
          <button type="button" role="tab" aria-selected="false" class="filter-pill" data-chart-group="gold_macro">黄金大宗汇率</button>
          <button type="button" role="tab" aria-selected="false" class="filter-pill" data-chart-group="etfs">重点ETF</button>
          <button type="button" role="tab" aria-selected="false" class="filter-pill" data-chart-group="stocks">{esc(stock_tab_lbl)}</button>
          <button type="button" role="tab" aria-selected="false" class="filter-pill" data-chart-group="watchlist">★ 我的自选</button>
        </div>
        <div class="kline-list-meta" id="kline-list-count">共 {len(static_rows)} 项核心基准</div>
        <div class="kline-symbol-list" id="kline-symbol-list">{"".join(static_rows)}</div>
      </aside>

      <div class="kline-terminal-main" id="kline-terminal-stage">
        <div class="kline-term-head">
          <div>
            <h2 class="kline-term-title" id="kline-term-title">上证指数 (000001)</h2>
            <div class="sec-sub" id="kline-term-sub">交互日 K 线 · MA / BOLL / EMA / 安全锚 + VOL / MACD / RSI / KDJ / ATR / BIAS</div>
          </div>
          <div class="kline-term-actions">
            <button type="button" id="kline-mobile-switch" class="kline-mobile-switch">🔍 切换标的 ▾</button>
            <button type="button" class="btn btn-sm" id="kline-term-star">☆ 加自选</button>
            <a class="btn btn-sm" href="screener.html">{esc(stock_btn_lbl)}</a>
            <a class="btn btn-sm" href="etfs.html">ETF 雷达</a>
          </div>
        </div>
        <div class="kline-quick-strip" aria-label="热门核心基准快捷切换">
          <button type="button" class="kline-quick-chip active" data-sym-id="idx_sh000001">上证</button>
          <button type="button" class="kline-quick-chip" data-sym-id="idx_hkHSI">恒指</button>
          <button type="button" class="kline-quick-chip" data-sym-id="idx_SPX">标普500</button>
          <button type="button" class="kline-quick-chip" data-sym-id="cmd_XAU">现货金</button>
          <button type="button" class="kline-quick-chip" data-sym-id="rate_US10Y">美债10Y</button>
          <button type="button" class="kline-quick-chip" data-sym-id="idx_N225">日经225</button>
        </div>
        <div class="kline-card">
          <div class="kline-mount" id="kline-terminal-mount"></div>
        </div>
      </div>
    </section>

    <script id="kline-meta-bridge" type="application/json">{safe_bridge_json}</script>
    """


def _pcal_norm_region(raw: Any) -> tuple[str, str]:
    """Normalize policy/calendar region into (filter_code, pure-Chinese badge)."""
    tok = str(raw or "").strip().upper().replace("-", "_")
    if tok in ("CN", "A_SHARE", "CHINA", "ASHARE", "中国", "中国A股", "A股"):
        return "CN", "中国A股"
    if tok in ("HK", "HK_STOCK", "HKSTOCK", "HONGKONG", "中国香港", "中国港股", "港股"):
        return "HK", "中国港股"
    if tok in ("US", "US_STOCK", "USSTOCK", "USA", "美国", "美国政策", "美股"):
        return "US", "美国政策"
    if tok in ("EU", "EURO", "EUROPE", "欧洲"):
        return "EU", "全球宏观 · 欧洲"
    if tok in ("JP", "JAPAN", "日本"):
        return "JP", "全球宏观 · 日本"
    if tok in ("UK", "BRITAIN", "英国"):
        return "UK", "全球宏观 · 英国"
    return "GLOBAL", "全球宏观"


def _pcal_norm_tier(raw: Any) -> tuple[str, str, str]:
    """Normalize impact tier into (machine_code, css_cls, pure-Chinese visible badge)."""
    tok = str(raw or "").strip().upper()
    if tok in ("P0", "0", "CRITICAL", "HIGH", "一级", "一级关键"):
        return "P0", "pcal-tier-p0", "🔴 一级关键"
    if tok in ("P1", "1", "MEDIUM", "IMPORTANT", "二级", "二级重点"):
        return "P1", "pcal-tier-p1", "🟠 二级重点"
    return "P2", "pcal-tier-p2", "⚪ 三级常规"


def _pcal_pick(obj: dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return clean_md_inline_plain(v)
    return default


def _policy_brief_display(brief: dict[str, Any]) -> dict[str, str]:
    """Display the same reviewed fields on the homepage and the market radar."""
    authority = _pcal_pick(brief, "authority", "source_authority", "source", "agency", default="官源追踪")
    day = _pcal_pick(brief, "date_cst", "timestamp_cst", default="日期待核")
    clock = _pcal_pick(brief, "time_cst")
    stamp = f"{day} {clock}" if clock and clock not in day else day
    return {
        "attribution": f"{authority} · {stamp}",
        "headline": _pcal_pick(brief, "headline", "title", default="重要市场动态"),
        "summary": _pcal_pick(brief, "summary", "plain_takeaway", "plain_chinese", "plain_summary", "beginner_summary",
                              default="持续跟踪官方口径与落地节奏。"),
    }


def _policy_brief_source_links(brief: dict[str, Any]) -> str:
    links = policy_brief_links(brief)
    return " ".join(
        f'<a class="mnews-src-link" href="{esc(url)}" target="_blank" rel="noopener noreferrer">'
        f'原始来源{f" {index}" if len(links) > 1 else ""} ↗</a>'
        for index, url in enumerate(links, start=1)
    )


def _policy_event_source_link(event: dict[str, Any]) -> str:
    source = event.get("source_url")
    if not is_https_source(source, published_source=True):
        return ""
    return f' <a class="mnews-src-link" href="{esc(source)}" target="_blank" rel="noopener noreferrer">原始来源 ↗</a>'


def _pcal_parse_base_date(policy_cal: dict[str, Any] | None, eq_state: dict[str, Any]) -> date:
    for raw in (
        (policy_cal or {}).get("as_of_cst"),
        (policy_cal or {}).get("as_of_date"),
        eq_state.get("as_of_cst"),
    ):
        iso = _extract_iso_date(raw)
        if iso:
            try:
                return date.fromisoformat(iso)
            except ValueError:
                pass
    return date.today()


def _pcal_fallback_from_radars(
    eq_state: dict[str, Any], base_date: date, gold_blocked: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build clean pure-Chinese policy briefs & upcoming events from market_state.policy_radars."""
    radars = eq_state.get("policy_radars")
    radars = radars if isinstance(radars, dict) else {}
    as_of_compact = fmt_cst_compact(str(eq_state.get("as_of_cst") or "")) or base_date.isoformat()
    alert_label = clean_md_inline_plain(str(eq_state.get("alert_label") or ""))

    mkt_specs = (
        (
            "a_share",
            "CN",
            "央行/财政部/沪深交易所政策雷达",
            "A 股政策与流动性托底主线",
            "政策稳增长、货币净投放与资本市场托底组合协同发力，重点紧盯量能续航与红利承接。",
            "联动中债 10Y 收益率、A 股两融情绪及港股中资权重估值修复。",
            "遵循红灯防守仓位上限，优先低费宽基与红利底座，不因单日脉冲情绪化追高。",
        ),
        (
            "hk_stock",
            "HK",
            "香港金管局/港交所/跨境政策雷达",
            "港股联汇利率与跨境资金主线",
            "南向互联互通政策延续托举，但联汇水位、拆息变动与地缘合规期限仍主导波动。",
            "港汇贴近 7.85 或拆息抬升会压制恒科高弹性估值，并与 A/H 溢价联动传导。",
            "严守离岸与港股通双轨仓位上限，重大指数调仓与规则截止日前留足现金缓冲。",
        ),
        (
            "us_stock",
            "US",
            "美联储/美国财政部/贸易政策雷达",
            "美债发债、联储路径与关税工具箱",
            "美债长端利率高企、财政发债抽水与关税贸易工具切换共同约束高估值科技扩张。",
            "美债 10Y 收益率与美元指数牵动全球科技估值、港股联汇压力及黄金真实利率压制。",
            "新钱优先美元超短债防弹衣，严控高估值科技新增敞口并核对 QDII 场内溢价。",
        ),
    )

    briefs: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    seen_ev: set[tuple[str, str]] = set()
    p0_kw = re.compile(r"议息|联储|央行|中央经济|MSCI|恒生|Part\s*851|停摆|OPEC|关税|四巫|降保")

    for mkey, rcode, auth, default_hl, plain, trans, guard in mkt_specs:
        robj = radars.get(mkey)
        if not isinstance(robj, dict) or not robj:
            continue
        statuses = [
            str(v).lower()
            for k, v in robj.items()
            if k not in ("next_anchors", "dividend_tax_cut_enacted") and isinstance(v, str)
        ]
        has_red = any(s.startswith("red_") for s in statuses)
        has_amber = any(s.startswith(("orange_", "yellow_")) for s in statuses)
        tier = "P0" if has_red else ("P1" if has_amber else "P2")
        anchors = [
            clean_md_inline_plain(str(a))
            for a in (robj.get("next_anchors") or [])
            if isinstance(a, str) and str(a).strip()
        ]
        headline = f"{default_hl}：{anchors[0]}" if anchors else default_hl
        briefs.append(
            {
                "region": rcode,
                "impact_tier": tier,
                "authority": auth,
                "timestamp_cst": as_of_compact,
                "headline": headline,
                "plain_takeaway": plain,
                "cross_market_transmission": trans,
                "action_guardrail": guard,
            }
        )
        for anc in anchors:
            m_full = re.match(r"^(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}))?\s*(.+)$", anc)
            m_mon = re.match(r"^(\d{4}-\d{2})\s+(.+)$", anc)
            if m_full:
                d_str, t_str, title_txt = m_full.group(1), m_full.group(2) or "", m_full.group(3).strip()
                prec = "exact"
            elif m_mon:
                d_str, t_str, title_txt = m_mon.group(1), "", m_mon.group(2).strip()
                prec = "window_tbd"
            else:
                continue
            dedup_key = (d_str, title_txt[:18])
            if dedup_key in seen_ev:
                continue
            seen_ev.add(dedup_key)
            ev_tier = "P0" if p0_kw.search(title_txt) else "P1"
            events.append(
                {
                    "region": rcode,
                    "impact_tier": ev_tier,
                    "date_cst": d_str,
                    "time_cst": t_str,
                    "date_precision": prec,
                    "title": title_txt,
                    "expected_consensus": "紧盯官方公告口径、落地节奏与市场预期差",
                    "cross_market_transmission": trans,
                    "upside_trigger": "落地措辞温和、资金面平稳或盈利/政策超预期托底",
                    "downside_trigger": "流动性抽水超预期、关税或合规口径收紧引发风险偏好回落",
                    "pre_event_discipline": guard,
                }
            )

    # Supplement from calendar_overrides within the upcoming 35-day window
    for ov in eq_state.get("calendar_overrides") or []:
        if not isinstance(ov, dict):
            continue
        d_str = _extract_iso_date(ov.get("date_cst"))
        note = clean_md_inline_plain(str(ov.get("note") or ""))
        if not d_str or not note:
            continue
        try:
            delta = (date.fromisoformat(d_str) - base_date).days
        except ValueError:
            continue
        if delta < 0 or delta > 35:
            continue
        dedup_key = (d_str, note[:18])
        if dedup_key in seen_ev:
            continue
        seen_ev.add(dedup_key)
        mkts = ov.get("markets_affected") or []
        if len(mkts) == 1:
            rcode = _pcal_norm_region(mkts[0])[0]
        elif len(mkts) > 1:
            rcode = "GLOBAL"
        else:
            rcode = "GLOBAL"
        mode_s = str(ov.get("mode") or "")
        ev_tier = "P0" if ("high_alert" in mode_s or p0_kw.search(note)) else "P1"
        events.append(
            {
                "region": rcode,
                "impact_tier": ev_tier,
                "date_cst": d_str,
                "time_cst": "",
                "date_precision": "exact",
                "title": note,
                "expected_consensus": "按交易所休市/调仓或官方日程提前做好仓位与资金衔接",
                "cross_market_transmission": "跨市场休市与指数调仓易放大尾盘波动与离岸/在岸价差。",
                "upside_trigger": "调仓或节点平稳过渡，成交有序承接",
                "downside_trigger": "薄量时段大幅跳空或集中抽水触发短线波动放大",
                "pre_event_discipline": "节点前严禁市价盲扫与临时追高，保持稳健现金缓冲。",
            }
        )

    if not briefs:
        briefs.append(
            {
                "region": "GLOBAL",
                "impact_tier": "P2",
                "authority": "全球宏观与三市政策跟踪",
                "timestamp_cst": as_of_compact,
                "headline": alert_label or "三市政策雷达常规跟踪中（A/港/美与宏观利率同步巡检）",
                "plain_takeaway": "当前按早/午/晚三班持续核验央行、财政、美联储与交易所官方公告，严守先看红绿灯再行动纪律。",
                "cross_market_transmission": "中美利率差、美元汇率与三市政策节奏共同决定权益与债市仓位上限。",
                "action_guardrail": (
                    "严守各市场仓位上限与单股不超过 8% 纪律；黄金处于红灯观察期，老仓稳拿、暂不新开仓。"
                    if gold_blocked
                    else "严守各市场仓位上限与单股不超过 8% 纪律，远离高溢价追涨。"
                ),
            }
        )
    return briefs, events


def _render_policy_calendar_section(
    policy_cal: dict[str, Any] | None,
    eq_state: dict[str, Any],
    gold_blocked: bool,
) -> str:
    """Render #sec-policy-calendar on index.html with graceful fallback to market_state.policy_radars."""
    base_date = _pcal_parse_base_date(policy_cal, eq_state)
    cal_obj = policy_cal if isinstance(policy_cal, dict) else None

    raw_briefs = (cal_obj.get("policy_briefs") if cal_obj else None) or []
    raw_events = (
        (cal_obj.get("events") if cal_obj else None)
        or (cal_obj.get("upcoming_events") if cal_obj else None)
        or (cal_obj.get("calendar_events") if cal_obj else None)
        or []
    )
    raw_briefs = [b for b in raw_briefs if isinstance(b, dict)]
    raw_events = [e for e in raw_events if isinstance(e, dict)]

    used_fallback = False
    if not raw_briefs or not raw_events:
        fb_briefs, fb_events = _pcal_fallback_from_radars(eq_state, base_date, gold_blocked)
        if not raw_briefs:
            raw_briefs = fb_briefs
            used_fallback = True
        if not raw_events:
            raw_events = fb_events
            used_fallback = True

    as_of_disp = (
        fmt_cst_compact(str((cal_obj or {}).get("as_of_cst") or ""))
        or fmt_cst_compact(str(eq_state.get("as_of_cst") or ""))
        or base_date.isoformat()
    )
    cutoff_clock = as_of_disp[11:16]

    _mkt_cn_map = {
        "a_share": "A股",
        "hk_stock": "港股",
        "us_stock": "美股",
        "rates_bonds_core": "中美债率",
        "gold": "黄金",
        "non_us_global_satellite": "非美全球",
    }

    def _fmt_affected(raw_mkts: Any) -> str:
        if not isinstance(raw_mkts, list):
            return ""
        labels = [_mkt_cn_map.get(str(m).strip(), str(m).strip()) for m in raw_mkts if str(m).strip()]
        return " / ".join(dict.fromkeys(labels))

    def _pcal_meter_html(tier_code: str) -> str:
        lit = 3 if tier_code == "P0" else (2 if tier_code == "P1" else 1)
        bars = "".join(
            f'<span class="pcal-bar{" active" if i <= lit else ""}"></span>'
            for i in range(1, 4)
        )
        return f'<span class="pcal-meter" aria-hidden="true">{bars}</span>'

    _region_guard_fallbacks = {
        "CN": "严守 A 股红灯防守仓位上限，优先低费宽基与红利底座，不追单日情绪脉冲。",
        "HK": "严守港股离岸与港股通双轨仓位上限，重大调仓与拆息波动窗口不追高波科网。",
        "US": "严守美股防弹衣与超短美债配比，高利率压制期不追高估值科技，核对 QDII 溢价。",
        "GLOBAL": (
            "严守跨市场总仓位与单股上限；黄金红灯停期严守新仓 0%，远离高溢价跨境基金与商品 LOF。"
            if gold_blocked
            else "严守跨市场总仓位与单股上限，远离高溢价跨境基金与商品 LOF。"
        ),
    }

    _cat_cn_map = {
        "top_politics": "顶层政策",
        "central_bank": "央行利率",
        "macro_data": "宏观数据",
        "fiscal_policy": "财政与债市",
        "regulation_trade": "监管与贸易",
        "geopolitics_energy": "地缘与能源",
        "liquidity_treasury": "流动性抽水",
        "market_structure": "微观与财报",
        "holiday_schedule": "交易日程",
    }
    _tier_rank = {"P0": 0, "P1": 1, "P2": 2}

    def _select_home_briefs(all_b: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not all_b:
            return []
        has_flag = any(isinstance(b.get("home_featured"), bool) for b in all_b)
        if has_flag:
            featured = [b for b in all_b if b.get("home_featured") is True]
            if len(featured) < 6 and len(all_b) >= 6:
                seen_ids = {id(b) for b in featured}
                rest = sorted(
                    [b for b in all_b if id(b) not in seen_ids],
                    key=lambda x: _tier_rank.get(str(x.get("impact_tier") or "P1").upper(), 1),
                )
                featured.extend(rest[: 6 - len(featured)])
            return featured[:9]
        if len(all_b) > 9:
            return sorted(
                all_b,
                key=lambda x: _tier_rank.get(str(x.get("impact_tier") or "P1").upper(), 1),
            )[:9]
        return list(all_b)

    home_briefs = _select_home_briefs(raw_briefs)
    total_all_briefs = len(raw_briefs)
    brief_cards: list[str] = []
    for b in home_briefs:
        reg_code, reg_lbl = _pcal_norm_region(b.get("region"))
        default_guard = _region_guard_fallbacks.get(reg_code, _region_guard_fallbacks["GLOBAL"])
        b_tier_code, tier_cls, tier_lbl = _pcal_norm_tier(
            b.get("impact_tier") or b.get("tier") or b.get("impact") or b.get("priority")
        )
        cat_raw = str(b.get("category") or "").strip().lower()
        cat_lbl = _cat_cn_map.get(cat_raw, "")
        display = _policy_brief_display(b)
        trans = _pcal_pick(b, "cross_market_transmission", "market_transmission", "transmission", "cross_market_impact", "impact_chain")
        guard = _pcal_pick(b, "action_guardrail", "action_boundary", "practical_boundary", "pre_event_stance", "guardrail", "discipline")
        mkt_imp = _pcal_pick(b, "market_impact")
        aff_txt = _fmt_affected(b.get("affected_markets"))
        if mkt_imp and not trans and not guard:
            if "；" in mkt_imp:
                p1, p2 = mkt_imp.split("；", 1)
                trans = f"波及 {aff_txt}：{p1.strip()}" if aff_txt else p1.strip()
                guard = re.sub(r"^(?:但是|但|不过)[，,：:\s]*", "", p2.strip())
            else:
                trans = f"波及 {aff_txt}：{mkt_imp}" if aff_txt else mkt_imp
                guard = default_guard
        elif mkt_imp and not trans:
            trans = f"波及 {aff_txt}：{mkt_imp}" if aff_txt else mkt_imp
        elif mkt_imp and not guard:
            guard = re.sub(r"^(?:但是|但|不过)[，,：:\s]*", "", mkt_imp.strip())
        if not trans:
            trans = (
                f"联动传导至 {aff_txt} 核心定价锚与风险偏好。"
                if aff_txt
                else "关注对汇率、长债收益率与核心权益板块的联动传导。"
            )
        if not guard:
            guard = default_guard
        brief_id = esc(str(b.get("id") or b.get("brief_id") or ""))
        cat_pill_html = f'<span class="mnews-cat-pill">{esc(cat_lbl)}</span>' if cat_lbl else ""
        brief_cards.append(
            f'<article class="pcal-brief-card" data-pcal-brief-id="{brief_id}" data-pcal-brief-region="{esc(reg_code)}" data-pcal-brief-tier="{esc(b_tier_code)}">'
            '<div class="pcal-brief-meta">'
            f'<span class="pcal-region-tag">{esc(reg_lbl)}</span>'
            f'<span class="pcal-tier-pill {tier_cls}">{_pcal_meter_html(b_tier_code)}{esc(tier_lbl)}</span>'
            f"{cat_pill_html}"
            f'<span class="pcal-src" data-pcal-brief-field="attribution">{esc(display["attribution"])}</span>'
            f"{_policy_brief_source_links(b)}"
            "</div>"
            f'<h4 class="pcal-brief-title" data-pcal-brief-field="headline">{esc(display["headline"])}</h4>'
            f'<div class="pcal-brief-row"><strong>白话看懂：</strong><span data-pcal-brief-field="summary">{esc(display["summary"])}</span></div>'
            f'<div class="pcal-brief-row"><strong>跨市传导：</strong>{esc(trans)}</div>'
            f'<div class="pcal-brief-guard"><strong>实操边界：</strong>{esc(guard)}</div>'
            "</article>"
        )

    mkt_counts = {
        "a_share": sum(1 for b in raw_briefs if "a_share" in (b.get("affected_markets") or [])),
        "hk_stock": sum(1 for b in raw_briefs if "hk_stock" in (b.get("affected_markets") or [])),
        "us_stock": sum(1 for b in raw_briefs if "us_stock" in (b.get("affected_markets") or [])),
        "gold": sum(1 for b in raw_briefs if "gold" in (b.get("affected_markets") or [])),
    }
    brief_filter_html = (
        '<div class="pcal-brief-filters no-print" id="pcal-brief-filters" role="toolbar" aria-label="按地区筛选今日核心时政">'
        f'<button type="button" class="filter-pill active" data-pcal-brief-filter="all" aria-pressed="true">精选全部 ({len(brief_cards)})</button>'
        '<button type="button" class="filter-pill" data-pcal-brief-filter="CN" aria-pressed="false">中国</button>'
        '<button type="button" class="filter-pill" data-pcal-brief-filter="HK" aria-pressed="false">中国香港</button>'
        '<button type="button" class="filter-pill" data-pcal-brief-filter="US" aria-pressed="false">美国</button>'
        '<button type="button" class="filter-pill" data-pcal-brief-filter="GLOBAL_EX" aria-pressed="false">欧日英与地缘</button>'
        "</div>"
        if len(brief_cards) >= 5
        else ""
    )
    jump_specs = (
        ("a_share", "daily/a-share-latest.html#sec-market-news", "🇨🇳 A股全部"),
        ("hk_stock", "daily/hk-stock-latest.html#sec-market-news", "🇭🇰 港股全部"),
        ("us_stock", "daily/us-stock-latest.html#sec-market-news", "🇺🇸 美股全部"),
        ("gold", "daily/gold-latest.html#sec-market-news", "🥇 黄金全部"),
    )
    jump_links_html = "".join(
        f'<a class="pmj-pill" href="{href}">{lbl} {mkt_counts[k]} 条 →</a>'
        for k, href, lbl in jump_specs
        if mkt_counts.get(k, 0) > 0
    )
    market_jump_html = (
        '<div class="pcal-market-jump-bar no-print">'
        f'<span class="pmj-label">📰 本期全市场共收录 <strong>{total_all_briefs}</strong> 条重要新闻（单市场无上限全量展示）：</span>'
        f'<div class="pmj-links">{jump_links_html}</div>'
        "</div>"
        if total_all_briefs >= 4 and jump_links_html
        else ""
    )

    prepared_events: list[tuple[tuple[int, str, str], str, str]] = []
    for ev in raw_events:
        reg_code, reg_lbl = _pcal_norm_region(ev.get("region"))
        tier_code, tier_cls, tier_lbl = _pcal_norm_tier(
            ev.get("impact_tier") or ev.get("tier") or ev.get("impact") or ev.get("priority")
        )
        date_raw = str(ev.get("date_cst") or ev.get("date") or "").strip()
        end_date_raw = str(ev.get("end_date_cst") or "").strip()
        time_raw = str(ev.get("time_cst") or ev.get("time") or "").strip()
        prec = str(ev.get("date_precision") or "exact").strip().lower()
        win_lbl = _pcal_pick(ev, "window_label", "date_window", "window_cst", default="")

        iso_d = _extract_iso_date(date_raw)
        iso_end = _extract_iso_date(end_date_raw)
        delta_days: int | None = None
        if iso_d:
            try:
                delta_days = (date.fromisoformat(iso_d) - base_date).days
            except ValueError:
                delta_days = None
        elif re.match(r"^\d{4}-\d{2}$", date_raw):
            try:
                y, m = int(date_raw[:4]), int(date_raw[5:7])
                delta_days = (date(y, m, 15) - base_date).days
            except ValueError:
                delta_days = None

        end_delta_days: int | None = None
        if iso_end:
            try:
                end_delta_days = (date.fromisoformat(iso_end) - base_date).days
            except ValueError:
                end_delta_days = None
        is_ongoing = (
            delta_days is not None
            and delta_days < 0
            and end_delta_days is not None
            and end_delta_days >= 0
        )
        exact_time_passed = (
            prec == "exact" and delta_days == 0 and (end_delta_days is None or end_delta_days == 0)
            and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_raw)
            and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cutoff_clock)
            and time_raw < cutoff_clock
        )

        explicit_horizon = str(ev.get("horizon") or "").strip().lower()
        if explicit_horizon in ("14d", "30d"):
            horizon = explicit_horizon
        elif delta_days is not None and delta_days <= 14:
            horizon = "14d"
        else:
            horizon = "30d"

        is_soon = False
        if prec == "window_tbd":
            if is_ongoing:
                countdown_lbl = "窗口进行中"
                is_soon = True
                sort_delta = 0
            elif delta_days is not None and 0 <= delta_days <= 3:
                countdown_lbl = "今日" if delta_days == 0 else ("明日" if delta_days == 1 else f"T+{delta_days} 天")
                is_soon = True
                sort_delta = delta_days
            elif delta_days is not None and delta_days > 3:
                countdown_lbl = f"T+{delta_days} 天"
                sort_delta = delta_days
            else:
                countdown_lbl = "窗口待定"
                sort_delta = delta_days if delta_days is not None else 20
            if win_lbl:
                time_disp = win_lbl if "窗口待定" in win_lbl else f"{win_lbl}（窗口待定）"
            elif date_raw and end_date_raw and end_date_raw != date_raw:
                end_short = end_date_raw[5:] if end_date_raw[:4] == date_raw[:4] else end_date_raw
                time_disp = f"{date_raw}–{end_short} · 窗口待定"
            elif date_raw:
                time_disp = f"{date_raw} · 窗口待定"
            else:
                time_disp = "窗口待定"
        else:
            if delta_days is None:
                countdown_lbl = "近期"
                sort_delta = 15
            elif is_ongoing:
                countdown_lbl = "进行中"
                is_soon = True
                sort_delta = 0
            elif delta_days < 0:
                countdown_lbl = "原定日期已过"
                sort_delta = delta_days
            elif exact_time_passed:
                countdown_lbl = "原定时刻已过"
                sort_delta = 0
            elif delta_days == 0:
                countdown_lbl = "今日"
                is_soon = True
                sort_delta = 0
            elif delta_days == 1:
                countdown_lbl = "明日"
                is_soon = True
                sort_delta = 1
            else:
                countdown_lbl = f"T+{delta_days} 天"
                is_soon = delta_days <= 3
                sort_delta = delta_days
            date_span = date_raw
            if date_raw and end_date_raw and end_date_raw != date_raw:
                end_short = end_date_raw[5:] if end_date_raw[:4] == date_raw[:4] else end_date_raw
                date_span = f"{date_raw}–{end_short}"
            if date_span and time_raw:
                time_disp = f"{date_span} {time_raw}"
            else:
                time_disp = date_span or time_raw or "待公布"

        title = _pcal_pick(ev, "title", "headline", "event", "name", default="关键金融时政节点")
        consensus = _pcal_pick(
            ev, "expected_consensus", "consensus", "expectation", "market_expectation",
            default="市场重点观察官方口径与预期差",
        )
        trans = _pcal_pick(
            ev, "market_transmission", "cross_market_transmission", "transmission", "cross_market_impact", "impact_chain",
            default="关注对股指、国债收益率与汇率的跨市场共振。",
        )
        wt = ev.get("watch_triggers") if isinstance(ev.get("watch_triggers"), dict) else {}
        upside = _pcal_pick(
            wt, "upside_bull", "upside_trigger", "bullish_trigger", "warm_trigger", "upside_watch", "bullish_watch",
        ) or _pcal_pick(
            ev, "upside_bull", "upside_trigger", "bullish_trigger", "warm_trigger", "upside_watch", "bullish_watch",
            default="数据温和向好或政策表态超预期偏暖。",
        )
        downside = _pcal_pick(
            wt, "downside_bear", "downside_trigger", "bearish_trigger", "cold_trigger", "downside_watch", "bearish_watch",
        ) or _pcal_pick(
            ev, "downside_bear", "downside_trigger", "bearish_trigger", "cold_trigger", "downside_watch", "bearish_watch",
            default="通胀/利率反跳或政策收紧超预期引发风险偏好回撤。",
        )
        discipline = _pcal_pick(
            ev, "pre_event_stance", "pre_event_discipline", "discipline", "action_guardrail", "action_boundary",
            default="节点公布前严控仓位与杠杆，等落地确认再按纪律执行。",
        )

        cd_cls = "pcal-countdown pcal-countdown-soon" if is_soon else "pcal-countdown"
        item_html = (
            f'<article class="pcal-event-item" data-pcal-region="{esc(reg_code)}" '
            f'data-pcal-tier="{esc(tier_code)}" data-pcal-horizon="{esc(horizon)}">'
            '<div class="pcal-event-top">'
            f'<span class="{cd_cls}">{esc(countdown_lbl)}</span>'
            f'<span class="pcal-event-time">{esc(time_disp)}</span>'
            f'<span class="pcal-region-tag">{esc(reg_lbl)}</span>'
            f'<span class="pcal-tier-pill {tier_cls}">{_pcal_meter_html(tier_code)}{esc(tier_lbl)}</span>'
            f'{_policy_event_source_link(ev)}'
            "</div>"
            f'<div class="pcal-event-title">{esc(title)}</div>'
            f'<div class="pcal-event-cons"><strong>市场预期：</strong>{esc(consensus)}</div>'
            '<details class="pcal-event-more">'
            '<summary class="pcal-event-sum">展开跨市传导、双向哨点与事前纪律</summary>'
            '<div class="pcal-event-detail">'
            f'<div><strong>跨市传导：</strong>{esc(trans)}</div>'
            f'<div><strong>上行/偏暖哨点：</strong>{esc(upside)}</div>'
            f'<div><strong>下行/偏空哨点：</strong>{esc(downside)}</div>'
            f'<div><strong>事前纪律：</strong>{esc(discipline)}</div>'
            "</div>"
            "</details>"
            "</article>"
        )
        time_sort = time_raw if re.match(r"^\d{2}:\d{2}$", time_raw) else "99:99"
        prepared_events.append(((sort_delta, date_raw, time_sort, title), horizon, item_html))

    prepared_events.sort(key=lambda x: x[0])
    count_14d = sum(1 for _, h, _ in prepared_events if h == "14d")
    count_30d = sum(1 for _, h, _ in prepared_events if h == "30d")
    total_ev = len(prepared_events)
    use_30d_toggle = count_30d > 0 and count_14d > 0

    rendered_events: list[str] = []
    non30_idx = 0
    folded_14d_count = 0
    for _, horizon, html_item in prepared_events:
        if use_30d_toggle and horizon == "30d":
            html_item = html_item.replace(
                '<article class="pcal-event-item"',
                '<article class="pcal-event-item" hidden',
                1,
            )
        else:
            if non30_idx >= 5:
                html_item = html_item.replace(
                    '<article class="pcal-event-item"',
                    '<article class="pcal-event-item pcal-fold-hidden"',
                    1,
                )
                folded_14d_count += 1
            non30_idx += 1
        rendered_events.append(html_item)

    base_unfolded = count_14d if use_30d_toggle else total_ev
    initial_shown = max(0, base_unfolded - folded_14d_count)
    more_fold_html = (
        f'<div class="pcal-more-wrap"><button type="button" id="pcal-more-btn" class="btn btn-sm" '
        f'data-pcal-more="0" aria-expanded="false">展开其余 {folded_14d_count} 项近期日程 ▾</button></div>'
        if folded_14d_count > 0
        else ""
    )
    count_txt = (
        f"显示 {initial_shown} / {total_ev} 项日程（另有 {count_30d} 项 15–30 天）"
        if use_30d_toggle
        else (f"显示 {initial_shown} / {total_ev} 项日程" if folded_14d_count > 0 else f"共 {total_ev} 项前瞻日程")
    )
    toggle_btn_html = (
        f'<button type="button" class="btn btn-sm" id="pcal-toggle-30d" data-expanded="0" '
        f'aria-expanded="false">展开 15–30 天前瞻日程（+{count_30d} 项）</button>'
        if use_30d_toggle
        else ""
    )
    gold_note = (
        " · 黄金红灯观察锁生效中（金价受事件波动亦严守新仓 0% 纪律）"
        if gold_blocked
        else ""
    )
    foot_note = (
        f"基线 {as_of_disp}"
        + (" · 由三市政策雷达自动汇整" if used_fallback else " · 同步早/午/晚三班滚动核验")
        + gold_note
    )
    empty_hidden = " hidden" if initial_shown > 0 else ""

    return f"""
    <section class="pcal-section" id="sec-policy-calendar" aria-labelledby="pcal-heading">
      <div class="sec-head">
        <h2 id="pcal-heading">🧭 核心时政政策深解 · 未来 14–30 天金融时政日历</h2>
        <span class="sec-sub">央行/财政/联储/地缘政策白话深解 · 未来 30 天关键节点倒计时与事前纪律</span>
      </div>
      <div class="pcal-stack">
        <div>
          <div class="pcal-col-head">
            <h3>今日核心时政与政策深解</h3>
            <span class="sec-sub">首页精选 {len(brief_cards)} 条（全市场共收录 {total_all_briefs} 条 · 点进单市场看全部）</span>
          </div>
          {brief_filter_html}
          <div class="pcal-briefs-row" id="pcal-briefs-row">
            {"".join(brief_cards)}
          </div>
          {market_jump_html}
        </div>
        <div class="pcal-agenda-card">
          <div class="pcal-col-head">
            <h3>未来 14–30 天关键金融时政日历</h3>
            <span class="sec-sub" id="pcal-count-status" role="status">{esc(count_txt)}</span>
          </div>
          <div class="pcal-filter-row" role="toolbar" aria-label="按地区与重要性筛选时政日历">
            <button type="button" class="filter-pill active" data-pcal-region="all" aria-pressed="true">全部</button>
            <button type="button" class="filter-pill" data-pcal-region="CN" aria-pressed="false">中国A股</button>
            <button type="button" class="filter-pill" data-pcal-region="HK" aria-pressed="false">中国港股</button>
            <button type="button" class="filter-pill" data-pcal-region="US" aria-pressed="false">美国政策</button>
            <button type="button" class="filter-pill" data-pcal-region="GLOBAL_EX" aria-pressed="false">欧日英与全球</button>
            <button type="button" class="filter-pill" id="pcal-only-major" data-pcal-tier="P0" aria-pressed="false">▮▮▮ 只看一级关键</button>
          </div>
          <div class="pcal-event-list" id="pcal-event-list">
            {"".join(rendered_events)}
          </div>
          {more_fold_html}
          <div class="pcal-empty" id="pcal-empty"{empty_hidden}>当前筛选条件下暂无匹配日程，试试切换地区或展开 15–30 天前瞻日程。</div>
          <div class="pcal-foot-row">
            {toggle_btn_html}
            <span class="sec-sub">{esc(foot_note)}</span>
          </div>
        </div>
      </div>
    </section>
    """


def _render_market_forward_calendar(
    market_slug: str,
    policy_cal: dict[str, Any] | None,
    current_edition: str,
) -> str:
    """Render the current publication's in-scope events by identity."""
    if not isinstance(policy_cal, dict) or policy_cal.get("edition_id") != current_edition or not current_edition:
        return ""
    stamp = fmt_cst_compact(str(policy_cal.get("as_of_cst") or "")).removesuffix(" CST")
    start_iso = _valid_iso_date(stamp[:10])
    if not start_iso:
        return ""
    horizon = (date.fromisoformat(start_iso) + timedelta(days=14)).isoformat()
    cutoff_time = stamp[11:16]
    market = market_slug.replace("-", "_")
    events: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for row in policy_cal.get("events") or []:
        if not isinstance(row, dict):
            continue
        affected = row.get("affected_markets")
        if not isinstance(affected, list) or market not in affected:
            continue
        event_id = _pcal_pick(row, "event_id")
        first = _valid_iso_date(row.get("date_cst"))
        last = _valid_iso_date(row.get("end_date_cst"))
        if not event_id or not first or not last or first > last or first > horizon or last < start_iso:
            continue
        time = _pcal_pick(row, "time_cst", default="时刻待核")
        if row.get("date_precision") == "exact" and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
            if first == last == start_iso and time < cutoff_time:
                continue
            clock = time
        else:
            clock = "99:99"
        events.setdefault(event_id, (first, clock, row))
    rows = []
    for event_id, (first, _, event) in sorted(events.items(), key=lambda item: (*item[1][:2], item[0])):
        last = event["end_date_cst"]
        span = first if first == last else f"{first} 至 {last}"
        time = _pcal_pick(event, "time_cst", default="时刻待核")
        _, tier_cls, tier_name = _pcal_norm_tier(event.get("impact_tier"))
        title = esc(_pcal_pick(event, "title"))
        source_link = _policy_event_source_link(event)
        rows.append(
            f'<tr data-event-id="{esc(event_id)}"><td>{esc(span)} · {esc(time)}</td>'
            f'<td><strong>{title}</strong> <span class="pcal-tier-pill {tier_cls}">{esc(tier_name)}</span>{source_link}</td>'
            f'<td>{esc(_pcal_pick(event, "market_transmission", default="传导待核"))}</td>'
            f'<td>{esc(_pcal_pick(event, "pre_event_stance", default="事前纪律待核"))}</td></tr>'
        )
    table = (
        '<div class="mobile-scroll-cue" aria-hidden="true">← 左右滑动查看完整列 →</div>'
        '<div class="table-wrap"><table class="data-table">'
        '<thead><tr><th scope="col">北京时间</th><th scope="col">事件与级别</th>'
        '<th scope="col">市场传导</th><th scope="col">事前纪律</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        if rows else '<p class="sec-sub">共享日历在此窗口无本市场条目。</p>'
    )
    return (
        f'<section id="sec-market-calendar" data-calendar-edition="{esc(current_edition)}">'
        '<h3>本班更新 · 未来 14 天财经与政策日历</h3>'
        f'<p class="sec-sub">日历期号 {esc(current_edition)} · 截至北京时间 {esc(stamp)}'
        f' · 覆盖至 {horizon} · {len(rows)} 项</p>{table}</section>'
    )


_DAILY_CALENDAR_BLOCK_RE = re.compile(
    r'(?P<heading><h([1-4])\b[^>]*>(?P<title>[^<]+)</h\2>)\s*'
    r'(?P<table>(?:<div class="mobile-scroll-cue"[^>]*>[^<]*</div>)?\s*'
    r'<div class="table-wrap(?: [^"]*)?"[^>]*><table\b[^>]*>\s*<thead>(?P<columns>.*?)</thead>.*?</table></div>)',
    re.DOTALL,
)


def _place_daily_calendar(
    body_html: str, calendar_html: str, *, reused: bool, original_issue: str, original_url: str,
) -> str:
    """Replace only an unambiguous calendar table, retaining the historical text on reused pages."""
    if not calendar_html:
        return body_html
    if "<tr data-event-id" not in calendar_html:
        return body_html + calendar_html
    matches = []
    for block in _DAILY_CALENDAR_BLOCK_RE.finditer(body_html):
        title = block["title"]
        if "北京时间" not in title or "日历" not in title or not re.search(r"(?:7\s*[–—-]\s*)?14\s*天", title):
            continue
        headers = [strip_tags(cell) for cell in re.findall(r"<th\b[^>]*>(.*?)</th>", block["columns"], re.DOTALL)]
        if (len(headers) == 4 and "北京时间" in headers[0] and "事件" in headers[1]
                and "级别" in (headers[1] + headers[2]) and "传导" in (headers[2] + headers[3])
                and "纪律" in headers[3]):
            matches.append(block)
    if len(matches) != 1:
        return body_html + calendar_html
    block = matches[0]
    if reused:
        original = (
            f'<details><summary>原稿日历 · {esc(original_issue)}</summary>'
            f'<p class="sec-sub">以下为原稿时点的日程，当前观察请以上表为准。</p>{block["table"]}</details>'
        )
    else:
        anchor = re.search(r'\bid="([^"]+)"', block["heading"])
        href = original_url + (f"#{anchor[1]}" if anchor else "")
        original = f'<p class="sec-sub"><a href="{esc(href)}">查看存档中的原稿日历</a></p>'
    return body_html[:block.start("table")] + calendar_html + original + body_html[block.end("table"):]


def _render_market_news_radar(
    market_slug: str,
    policy_cal: dict[str, Any] | None,
    eq_state: dict[str, Any],
    gold_blocked: bool,
) -> tuple[str, int]:
    """Render uncapped complete news & policy deck for an individual market report page."""
    if not isinstance(policy_cal, dict):
        return "", 0
    raw_briefs = [b for b in (policy_cal.get("policy_briefs") or []) if isinstance(b, dict)]
    if not raw_briefs:
        return "", 0
    mkt_map = {
        "a-share": ("a_share", "🇨🇳 中国 A 股"),
        "hk-stock": ("hk_stock", "🇭🇰 中国香港股市"),
        "us-stock": ("us_stock", "🇺🇸 美国股市"),
        "gold": ("gold", "🥇 黄金与贵金属"),
    }
    eq_key, mkt_title = mkt_map.get(market_slug, (market_slug.replace("-", "_"), market_slug))
    matched = [b for b in raw_briefs if eq_key in (b.get("affected_markets") or [])]
    if not matched:
        return "", 0

    _tier_rank = {"P0": 0, "P1": 1, "P2": 2}

    def _safe_date_sort_num(raw_d: Any) -> int:
        s_raw = str(raw_d or "").strip()
        iso = _extract_iso_date(s_raw)
        if iso:
            try:
                return -int(iso.replace("-", ""))
            except ValueError:
                pass
        digits = re.sub(r"\D+", "", s_raw)[:8]
        if len(digits) == 8:
            try:
                return -int(digits)
            except ValueError:
                pass
        return 0

    matched.sort(
        key=lambda b: (
            _tier_rank.get(str(b.get("impact_tier") or "P1").upper(), 1),
            _safe_date_sort_num(b.get("date_cst")),
            str(b.get("id") or ""),
        )
    )
    _cat_cn = {
        "top_politics": "顶层政策",
        "central_bank": "央行利率",
        "macro_data": "宏观数据",
        "fiscal_policy": "财政与债市",
        "regulation_trade": "监管与贸易",
        "geopolitics_energy": "地缘与能源",
        "liquidity_treasury": "流动性抽水",
        "market_structure": "微观与财报",
        "holiday_schedule": "交易日程",
    }
    _mkt_cn = {
        "a_share": "A股",
        "hk_stock": "港股",
        "us_stock": "美股",
        "rates_bonds_core": "中美债率",
        "gold": "黄金",
        "non_us_global_satellite": "非美全球",
    }
    as_of_disp = (
        fmt_cst_compact(str(policy_cal.get("as_of_cst") or ""))
        or fmt_cst_compact(str(eq_state.get("as_of_cst") or ""))
    )

    def _meter(tier_code: str) -> str:
        lit = 3 if tier_code == "P0" else (2 if tier_code == "P1" else 1)
        bars = "".join(f'<span class="pcal-bar{" active" if i <= lit else ""}"></span>' for i in range(1, 4))
        return f'<span class="pcal-meter" aria-hidden="true">{bars}</span>'

    seen_cats: list[tuple[str, str]] = []
    seen_cat_keys: set[str] = set()
    p0_cnt = 0
    cards: list[str] = []
    for b in matched:
        _, reg_lbl = _pcal_norm_region(b.get("region"))
        b_tier_code, tier_cls, tier_lbl = _pcal_norm_tier(b.get("impact_tier"))
        if b_tier_code == "P0":
            p0_cnt += 1
        cat_k = str(b.get("category") or "market_structure").strip().lower()
        cat_lbl = _cat_cn.get(cat_k, "要闻深解")
        if cat_k not in seen_cat_keys:
            seen_cat_keys.add(cat_k)
            seen_cats.append((cat_k, cat_lbl))
        display = _policy_brief_display(b)
        mkt_imp = _pcal_pick(b, "market_impact")
        aff_labels = [_mkt_cn.get(str(m).strip(), str(m).strip()) for m in (b.get("affected_markets") or []) if str(m).strip()]
        aff_txt = " / ".join(dict.fromkeys(aff_labels))
        if "；" in mkt_imp:
            p1, p2 = mkt_imp.split("；", 1)
            trans = f"波及 {aff_txt}：{p1.strip()}" if aff_txt else p1.strip()
            guard = re.sub(r"^(?:但是|但|不过)[，,：:\s]*", "", p2.strip())
        else:
            trans = f"波及 {aff_txt}：{mkt_imp}" if aff_txt else mkt_imp
            guard = (
                "黄金红灯停期严守新仓 0%，严控权益仓位上限，不追单日情绪脉冲。"
                if gold_blocked
                else "严守仓位纪律与风控锚点，不追单日情绪脉冲。"
            )
        brief_id = esc(str(b.get("id") or b.get("brief_id") or ""))
        cards.append(
            f'<article class="pcal-brief-card mnews-card" data-pcal-brief-id="{brief_id}" data-mnews-cat="{esc(cat_k)}" data-mnews-tier="{esc(b_tier_code)}">'
            '<div class="pcal-brief-meta">'
            f'<span class="pcal-region-tag">{esc(reg_lbl)}</span>'
            f'<span class="pcal-tier-pill {tier_cls}">{_meter(b_tier_code)}{esc(tier_lbl)}</span>'
            f'<span class="mnews-cat-pill">{esc(cat_lbl)}</span>'
            f'<span class="pcal-src" data-pcal-brief-field="attribution">{esc(display["attribution"])}</span>'
            f"{_policy_brief_source_links(b)}"
            "</div>"
            f'<h4 class="pcal-brief-title" data-pcal-brief-field="headline">{esc(display["headline"])}</h4>'
            f'<div class="pcal-brief-row"><strong>白话看懂：</strong><span data-pcal-brief-field="summary">{esc(display["summary"])}</span></div>'
            f'<div class="pcal-brief-row"><strong>跨市传导：</strong>{esc(trans)}</div>'
            f'<div class="pcal-brief-guard"><strong>实操边界：</strong>{esc(guard)}</div>'
            "</article>"
        )

    cat_btns = "".join(
        f'<button type="button" class="filter-pill" data-mnews-filter="{esc(ck)}" aria-pressed="false">{esc(cl)}</button>'
        for ck, cl in seen_cats
    )
    major_btn_html = (
        '<button type="button" class="filter-pill" data-mnews-filter="major" aria-pressed="false">▮▮▮ 只看一级关键</button>'
        if p0_cnt > 0
        else ""
    )
    html_block = f"""
    <section class="mnews-section" id="sec-market-news" aria-labelledby="mnews-heading">
      <div class="mnews-head">
        <div>
          <h2 id="mnews-heading" class="mnews-title">📰 {esc(mkt_title)} · 全部重要新闻与政策雷达</h2>
          <p class="mnews-sub">无上限全量收录影响本市场的全部重要政策、央行、宏观、监管、财报与地缘动态（截至 {esc(as_of_disp)}）</p>
        </div>
        <span class="mnews-count-badge" id="mnews-count-status">全量收录 {len(cards)} 条 · 无上限</span>
      </div>
      <div class="mnews-filter-row no-print" role="toolbar" aria-label="筛选本市场重要新闻">
        <button type="button" class="filter-pill active" data-mnews-filter="all" aria-pressed="true">全部 ({len(cards)})</button>
        {major_btn_html}
        {cat_btns}
      </div>
      <div class="mnews-grid">
        {"".join(cards)}
      </div>
    </section>"""
    return html_block, len(cards)


def _render_daily_visual_cockpit(
    market_slug: str,
    eq_state: dict[str, Any],
    gold_snap: dict[str, Any],
    body_html: str,
    *,
    reused_body: bool = False,
) -> str:
    """Render an instant visual dashboard (scorecard bars, wallet allocation ribbon, crisis gauges) at top of latest daily."""
    markets = eq_state.get("markets") or {}
    links = eq_state.get("cross_market_linkages") or {}
    brake = links.get("crisis_correlation_brake") or {}
    rb_core = eq_state.get("rates_bonds_core") if isinstance(eq_state.get("rates_bonds_core"), dict) else {}
    rb_us = rb_core.get("us_rates") if isinstance(rb_core.get("us_rates"), dict) else {}
    rates_fx = links.get("rates_fx_chain") if isinstance(links.get("rates_fx_chain"), dict) else {}

    gold_blocked = (
        gold_snap.get("new_buy_allowed") is False
        or str(gold_snap.get("tier_code") or "").strip() == "Tier 0"
    )
    t1_gates = [g for g in (gold_snap.get("tier1_gates") or []) if isinstance(g, dict)]
    t1_pass_raw = _safe_float(gold_snap.get("tier1_passed"))
    t1_tot_raw = _safe_float(gold_snap.get("tier1_total"))
    t1_pass = int(t1_pass_raw) if t1_pass_raw is not None else sum(1 for g in t1_gates if g.get("passed"))
    t1_tot = int(t1_tot_raw) if t1_tot_raw is not None else max(len(t1_gates), 4)
    gold_tier_short = (
        str(gold_snap.get("tier_label") or ("红灯停" if gold_blocked else "按档分批"))
        .split("（")[0]
        .strip()
    )

    left_title = "📊 6 维大盘体检可视化仪表"
    score_rows_html: list[str] = []
    if market_slug == "gold":
        left_title = "🚦 买金四步红绿灯进度仪"
        for g in t1_gates[:4]:
            passed = bool(g.get("passed"))
            pct = 100 if passed else 22
            tone = "green" if passed else "red"
            badge = "已过关" if passed else "未过关"
            gname = str(g.get("name") or "")
            gread = str(g.get("reading") or "")
            score_rows_html.append(
                '<div class="dvc-score-row">'
                f'<div class="dvc-sr-head"><span class="dvc-sr-name">{esc(gname)}</span>'
                f'<span class="dvc-sr-val dvc-tone-{tone}">{esc(badge)}</span></div>'
                f'<div class="dvc-bar-track"><div class="dvc-bar-fill dvc-fill-{tone}" style="width:{pct}%"></div></div>'
                f'<div class="dvc-sr-sub" title="{esc(gread)}">{esc(gread)}</div>'
                "</div>"
            )
    else:
        if reused_body:
            left_title = "📊 沿用研报的 6 维大盘评分"
        dim_matches: list[tuple[str, float, float]] = []
        for m in re.finditer(
            r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>",
            body_html,
            flags=re.DOTALL,
        ):
            c1 = re.sub(r"<[^>]+>", "", re.sub(r'<span class="term-q"[^>]*>.*?</span>', "", m.group(1))).strip()
            c2 = re.sub(r"<[^>]+>", "", re.sub(r'<span class="term-q"[^>]*>.*?</span>', "", m.group(2))).strip()
            if not c1 or re.match(r"^(?:总|合计|综合|总分)", c1):
                continue
            if not re.search(r"[1-6]\.|维度|政策|估值|趋势|流动|宏观|利率|联汇|盈利|广度|波动", c1):
                continue
            sm = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*/\s*([0-9]+(?:\.[0-9]+)?)", c2)
            if sm:
                got_v, mx_v = float(sm.group(1)), float(sm.group(2))
                if 0 < mx_v <= 10.0 and 0.0 <= got_v <= mx_v:
                    dim_matches.append((c1, got_v, mx_v))
                    continue
            sm_pts = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*分", c2)
            if sm_pts:
                got_v = float(sm_pts.group(1))
                if 0.0 <= got_v <= 10.0:
                    mx_v = 1.0 if got_v <= 1.0 else (5.0 if got_v <= 5.0 else 10.0)
                    dim_matches.append((c1, got_v, mx_v))
        if len(dim_matches) < 4:
            dim_matches = []
            for m in re.finditer(
                r"<li[^>]*>\s*<strong>\s*([1-6]\.[^<]+?)[（(]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*([0-9]+(?:\.[0-9]+)?)\s*[）)]\s*</strong>",
                body_html,
            ):
                got_v, mx_v = float(m.group(2)), float(m.group(3))
                if 0 < mx_v <= 10.0 and 0.0 <= got_v <= mx_v:
                    dim_matches.append((m.group(1).strip(), got_v, mx_v))
        for lbl, got, mx in dim_matches[:6]:
            pct = max(6, min(100, int(round((got / max(mx, 0.1)) * 100))))
            tone = "green" if got >= mx * 0.85 else ("amber" if got > 0 else "red")
            score_rows_html.append(
                '<div class="dvc-score-row">'
                f'<div class="dvc-sr-head"><span class="dvc-sr-name">{esc(lbl)}</span>'
                f'<span class="dvc-sr-val dvc-tone-{tone}">{got:g}/{mx:g}</span></div>'
                f'<div class="dvc-bar-track"><div class="dvc-bar-fill dvc-fill-{tone}" style="width:{pct}%"></div></div>'
                "</div>"
            )

    alloc_segments: list[tuple[str, float, str]] = []
    alloc_note = "仓位数据待核"
    if market_slug == "a-share":
        cap = _safe_float((markets.get("a_share") or {}).get("equity_cap_pct"))
        if cap is not None and 0 <= cap <= 100:
            alloc_segments = [("A股权益上限", cap, "#1d4ed8"), ("短融/国债防盾", 100 - cap, "#0f766e")]
            alloc_note = f"股票 ≤ {cap:g}% ｜ 债现与多元 ≥ {100 - cap:g}%"
            if gold_blocked:
                alloc_note += " ｜ 黄金新仓 0%"
    elif market_slug == "hk-stock":
        hk_market = markets.get("hk_stock") or {}
        cap_off = _safe_float(hk_market.get("offshore_equity_cap_pct"))
        cap_con = _safe_float(hk_market.get("onshore_connect_cap_pct"))
        if cap_off is not None and 0 <= cap_off <= 100:
            alloc_segments = [("港股离岸上限", cap_off, "#1d4ed8"), ("港元货基/短债盾", 100 - cap_off, "#0f766e")]
        alloc_note = f"离岸上限 {_fmt_num(cap_off, 'g', suffix='%')} ｜ 港股通上限 {_fmt_num(cap_con, 'g', suffix='%')}"
        if gold_blocked:
            alloc_note += " ｜ 黄金新仓 0%"
    elif market_slug == "us-stock":
        us_m = markets.get("us_stock") or {}
        eq_p = _safe_float(us_m.get("equity_cap_pct"))
        cash_p = _safe_float(us_m.get("cash_tbill_pct"))
        gold_p = _safe_float(us_m.get("gold_hold_pct"))
        if all(pct is not None and 0 <= pct <= 100 for pct in (eq_p, cash_p, gold_p)):
            alloc_segments = [
                ("防弹衣价值股", eq_p, "#1d4ed8"),
                ("超短美债盾", cash_p, "#0f766e"),
                ("存量金", gold_p, "#b45309"),
            ]
            alloc_note = f"美股 {eq_p:g}% ｜ 超短债 {cash_p:g}% ｜ 存量金 {gold_p:g}%"
        if gold_blocked:
            alloc_note += " ｜ 黄金新仓 0%"
    else:
        alloc_segments = [("黄金上限", 15, "#b45309"), ("待命债现与非金主池", 85, "#0f766e")]
        if gold_blocked:
            alloc_note = f"存量金占家庭资产上限 10%–15%（不追买）｜ 当前红灯 {t1_pass}/{t1_tot} 关，新仓严格 0%"
        else:
            alloc_note = f"黄金占家庭资产上限 10%–15% ｜ 当前{gold_tier_short}（已解锁 {t1_pass}/{t1_tot} 关），按档位上限控制新仓"

    alloc_bar_html = "".join(
        f'<div class="dvc-alloc-seg" style="width:{pct:g}%;background:{col}" title="{esc(lbl)} {pct:g}%">'
        f'<span>{esc(f"{pct:g}%" if pct <= 18 else f"{lbl} {pct:g}%")}</span></div>'
        for lbl, pct, col in alloc_segments
        if pct > 0
    )

    def _pick_num(*vals: Any) -> float | None:
        for v in vals:
            fv = _safe_float(v)
            if fv is not None:
                return fv
        return None

    us10y_val = _pick_num(
        rb_us.get("us10y_asia_live_pct"),
        rb_us.get("us10y_pct"),
        rates_fx.get("us10y_live_pct"),
        rates_fx.get("us10y_pct"),
        gold_snap.get("us10y_live_pct"),
        gold_snap.get("us10y_pct"),
        (markets.get("us_stock") or {}).get("us10y_pct"),
    )
    vix_val = _pick_num(
        brake.get("vix_live"),
        brake.get("vix_close"),
        gold_snap.get("vix_live"),
        gold_snap.get("vix_close"),
    )
    usdjpy_val = _pick_num(
        brake.get("usdjpy_level"),
        rates_fx.get("usd_jpy"),
        gold_snap.get("usd_jpy"),
    )
    hkma_val = _pick_num(
        rates_fx.get("hkma_agg_bal_hkd_100m"),
        (markets.get("hk_stock") or {}).get("hkma_agg_bal_hkd_100m"),
    )

    gauges: list[tuple[str, str, str, int, str]] = [
        (
            "10年期美债",
            f"{us10y_val:.2f}%" if us10y_val is not None else "—",
            "红线 5.25%",
            max(0, min(100, int(round(us10y_val / 5.25 * 100)))) if us10y_val is not None else 0,
            ("red" if us10y_val >= 5.25 else ("amber" if us10y_val >= 4.70 else "green"))
            if us10y_val is not None
            else "neutral",
        ),
        (
            "恐慌 VIX",
            f"{vix_val:.2f}" if vix_val is not None else "—",
            "红线 30.0",
            max(0, min(100, int(round(vix_val / 30.0 * 100)))) if vix_val is not None else 0,
            ("red" if vix_val >= 30.0 else ("amber" if vix_val >= 24.0 else "green"))
            if vix_val is not None
            else "neutral",
        ),
        (
            "美元/日元",
            f"{usdjpy_val:.2f}" if usdjpy_val is not None else "—",
            "干预警戒 160",
            max(0, min(100, int(round((usdjpy_val - 140.0) / 20.0 * 100)))) if usdjpy_val is not None else 0,
            ("red" if usdjpy_val >= 160.0 else ("amber" if usdjpy_val >= 155.0 else "green"))
            if usdjpy_val is not None
            else "neutral",
        ),
        (
            "港银总结余",
            f"{hkma_val:.0f}亿" if hkma_val is not None else "—",
            "底线 400亿",
            max(0, min(100, int(round((700.0 - hkma_val) / 300.0 * 100)))) if hkma_val is not None else 0,
            ("red" if hkma_val <= 400.0 else ("amber" if hkma_val <= 550.0 else "green"))
            if hkma_val is not None
            else "neutral",
        ),
    ]
    gauge_html = "".join(
        '<div class="dvc-gauge">'
        f'<div class="dvc-g-top"><span class="dvc-g-lbl">{esc(gl)}</span><strong class="dvc-tone-{gt}">{esc(gv)}</strong></div>'
        f'<div class="dvc-bar-track"><div class="dvc-bar-fill dvc-fill-{gt}" style="width:{gp}%"></div></div>'
        f'<div class="dvc-g-sub">{esc(gth)}</div>'
        "</div>"
        for gl, gv, gth, gp, gt in gauges
    )

    left_card = (
        '<div class="dvc-card">'
        f'<div class="dvc-card-head">{esc(left_title)}</div>'
        f'<div class="dvc-score-list">{"".join(score_rows_html)}</div>'
        "</div>"
        if score_rows_html
        else ""
    )
    grid_cls = "dvc-grid" if left_card else "dvc-grid dvc-grid-single"
    snapshot_time = str(eq_state.get("as_of_cst") or gold_snap.get("as_of_short") or "")
    snapshot_time = snapshot_time.replace("T", " ").removesuffix("+08:00")[:16]
    snapshot_label = f'<div class="dvc-alloc-note">本班状态 · 北京时间 {esc(snapshot_time)}</div>' if snapshot_time else ""

    return (
        '<section class="daily-visual-cockpit no-print" aria-label="10秒可视化快读仪表盘">'
        f'<div class="{grid_cls}">'
        f"{left_card}"
        '<div class="dvc-card">'
        '<div class="dvc-card-head">💼 钱包仓位配比条 &amp; 全球 4 阀熔断邻近仪</div>'
        f"{snapshot_label}"
        f'<div class="dvc-alloc-bar">{alloc_bar_html}</div>'
        f'<div class="dvc-alloc-note">{esc(alloc_note)}</div>'
        f'<div class="dvc-brake-grid">{gauge_html}</div>'
        "</div>"
        "</div>"
        "</section>"
    )


def _enhance_daily_body_visuals(body_html: str) -> str:
    """Automatically upgrade scenario probability tables ([●○]{10}) and arrow chains into vivid visual blocks."""
    prob_colors = ["#1d4ed8", "#b45309", "#dc2626", "#0f766e", "#6366f1"]

    def _upgrade_prob_table(match: re.Match[str]) -> str:
        tbl_html = match.group(0)
        if not re.search(r"[●○]{10}", tbl_html):
            return tbl_html
        rows_found: list[tuple[str, int]] = []
        for rm in re.finditer(r"<tr[^>]*>(.*?)</tr>", tbl_html, flags=re.DOTALL):
            row_inner = rm.group(1)
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row_inner, flags=re.DOTALL)
            if not tds:
                continue
            dm = re.search(r"([●○]{10})", row_inner)
            if dm:
                pts = dm.group(1).count("●")
                if pts > 0:
                    c1_raw = re.split(r"<br\s*/?>", tds[0], maxsplit=1)[0]
                    c1 = re.sub(r"<[^>]+>", "", c1_raw).strip()
                    short_lbl = re.sub(r"^(?:情景\s*[A-D一二三四]\s*[：:]\s*)", "", c1)
                    short_lbl = short_lbl if len(short_lbl) <= 14 else short_lbl[:13] + "…"
                    rows_found.append((short_lbl, pts))
        if not rows_found:
            return tbl_html
        total_pts = sum(p for _, p in rows_found)
        if total_pts <= 0:
            return tbl_html

        segs = []
        legends = []
        for idx, (lbl, pts) in enumerate(rows_found):
            col = prob_colors[idx % len(prob_colors)]
            pct = round(pts / total_pts * 100)
            segs.append(
                f'<div class="prob-seg" style="width:{pct}%;background:{col}" title="{esc(lbl)} ({pct}%)">'
                f'<span>{pct}%</span></div>'
            )
            legends.append(
                f'<span class="prob-leg-item"><i style="background:{col}"></i>{esc(lbl)} <strong>{pts}/10 ({pct}%)</strong></span>'
            )

        def _stylize_dots(dm: re.Match[str]) -> str:
            raw_d = dm.group(0)
            spans = "".join(
                '<span class="pdot pdot-on"></span>' if ch == "●" else '<span class="pdot pdot-off"></span>'
                for ch in raw_d
            )
            return f'<span class="prob-dots" aria-label="{raw_d.count("●")} / 10">{spans}</span>'

        upgraded_tbl = re.sub(r"[●○]{10}", _stylize_dots, tbl_html)
        sum_lbl = f"合计 {total_pts}/10（100%）" if total_pts == 10 else f"合计 {total_pts}/10"
        ribbon = (
            '<div class="prob-ribbon-card">'
            '<div class="prob-ribbon-head"><span>🎯 未来 48 小时四情景概率可视化分布</span>'
            f'<span class="prob-ribbon-sum">{sum_lbl}</span></div>'
            f'<div class="prob-ribbon-bar">{"".join(segs)}</div>'
            f'<div class="prob-ribbon-legend">{"".join(legends)}</div>'
            "</div>"
        )
        return ribbon + upgraded_tbl

    out = re.sub(
        r'<div class="table-wrap[^"]*">.*?</table>\s*</div>',
        _upgrade_prob_table,
        body_html,
        flags=re.DOTALL,
    )

    # 1b. Also upgrade <ul> scenario probability lists containing [●○]{10} (e.g., US compact watch reports)
    def _upgrade_prob_ul(match: re.Match[str]) -> str:
        ul_html = match.group(0)
        if not re.search(r"[●○]{10}", ul_html):
            return ul_html
        rows_found: list[tuple[str, int]] = []
        for lm in re.finditer(r"<li[^>]*>(.*?)</li>", ul_html, flags=re.DOTALL):
            plain_li = re.sub(r"<[^>]+>", "", lm.group(1)).strip()
            dm = re.search(r"([●○]{10})", plain_li)
            if dm:
                pts = dm.group(1).count("●")
                if pts > 0:
                    lbl = re.split(r"[（(：:]", plain_li, maxsplit=1)[0].strip()
                    lbl = lbl if len(lbl) <= 14 else lbl[:13] + "…"
                    rows_found.append((lbl, pts))
        if len(rows_found) < 2:
            return ul_html
        total_pts = sum(p for _, p in rows_found)
        if total_pts <= 0:
            return ul_html
        segs = []
        legends = []
        for idx, (lbl, pts) in enumerate(rows_found):
            col = prob_colors[idx % len(prob_colors)]
            pct = round(pts / total_pts * 100)
            segs.append(
                f'<div class="prob-seg" style="width:{pct}%;background:{col}" title="{esc(lbl)} ({pct}%)">'
                f'<span>{pct}%</span></div>'
            )
            legends.append(
                f'<span class="prob-leg-item"><i style="background:{col}"></i>{esc(lbl)} <strong>{pts}/10 ({pct}%)</strong></span>'
            )

        def _stylize_dots(dm: re.Match[str]) -> str:
            raw_d = dm.group(0)
            spans = "".join(
                '<span class="pdot pdot-on"></span>' if ch == "●" else '<span class="pdot pdot-off"></span>'
                for ch in raw_d
            )
            return f'<span class="prob-dots" aria-label="{raw_d.count("●")} / 10">{spans}</span>'

        upgraded_ul = re.sub(r"[●○]{10}", _stylize_dots, ul_html)
        sum_lbl = f"合计 {total_pts}/10（100%）" if total_pts == 10 else f"合计 {total_pts}/10"
        ribbon = (
            '<div class="prob-ribbon-card">'
            '<div class="prob-ribbon-head"><span>🎯 情景概率可视化分布</span>'
            f'<span class="prob-ribbon-sum">{sum_lbl}</span></div>'
            f'<div class="prob-ribbon-bar">{"".join(segs)}</div>'
            f'<div class="prob-ribbon-legend">{"".join(legends)}</div>'
            "</div>"
        )
        return ribbon + upgraded_ul

    out = re.sub(r"<ul[^>]*>.*?</ul>", _upgrade_prob_ul, out, flags=re.DOTALL)

    _VOID_TAGS = {"br", "hr", "img", "input", "wbr"}

    def _split_html_safe_chain(raw_chain: str) -> list[str]:
        """Split raw_chain on '→' strictly at HTML tag depth 0; fall back to escaped plain text if tags wrap arrows."""
        parts: list[str] = []
        buf: list[str] = []
        depth = 0
        pos = 0
        n_len = len(raw_chain)
        while pos < n_len:
            ch = raw_chain[pos]
            if ch == "<":
                end_gt = raw_chain.find(">", pos + 1)
                if end_gt == -1:
                    buf.append(ch)
                    pos += 1
                    continue
                tag_tok = raw_chain[pos : end_gt + 1]
                tm = re.match(r"^<\s*(/?)\s*([a-zA-Z0-9]+)", tag_tok)
                if tm:
                    is_close = bool(tm.group(1))
                    tname = tm.group(2).lower()
                    is_self = tag_tok.endswith("/>") or tname in _VOID_TAGS
                    if not is_self:
                        if is_close:
                            depth = max(0, depth - 1)
                        else:
                            depth += 1
                buf.append(tag_tok)
                pos = end_gt + 1
                continue
            if ch == "→" and depth == 0:
                seg = "".join(buf).strip()
                if seg:
                    parts.append(seg)
                buf = []
                pos += 1
                continue
            buf.append(ch)
            pos += 1
        tail_seg = "".join(buf).strip()
        if tail_seg:
            parts.append(tail_seg)
        if depth == 0 and 3 <= len(parts) <= 6:
            return parts
        plain_chain = html_mod.unescape(re.sub(r"<[^>]+>", "", raw_chain))
        plain_parts = [esc(s.strip()) for s in plain_chain.split("→") if s.strip()]
        return plain_parts

    def _upgrade_flow_para(match: re.Match[str]) -> str:
        full_p = match.group(0)
        qm = re.search(r"「([^」]{20,})」", full_p)
        if not qm or qm.group(1).count("→") < 2:
            return full_p
        raw_chain = qm.group(1)
        steps = _split_html_safe_chain(raw_chain)
        if len(steps) < 3 or len(steps) > 6:
            return full_p
        nodes: list[str] = []
        for idx, st in enumerate(steps):
            nodes.append(
                f'<div class="ifc-node"><span class="ifc-step">第 {idx + 1} 环</span>'
                f'<span class="ifc-txt">{st}</span></div>'
            )
            if idx + 1 < len(steps):
                nodes.append('<span class="ifc-arrow" aria-hidden="true">→</span>')
        flow_html = (
            '<div class="inline-flow-wrap">'
            '<div class="inline-flow-head">🧭 跨资产因果传导可视化链路</div>'
            f'<div class="inline-flow-chain">{"".join(nodes)}</div>'
            "</div>"
        )
        after_inner = re.sub(r"</p>\s*$", "", full_p[qm.end() :], flags=re.IGNORECASE).strip()
        # Strip leading orphan closing inline tags left over if a tag opened before 「
        while True:
            m_cl = re.match(r"^(?:</(?:strong|em|b|i|span|code)>\s*)+", after_inner, flags=re.IGNORECASE)
            if not m_cl:
                break
            after_inner = after_inner[m_cl.end() :].strip()
        after_inner = re.sub(r"^[。；;，,\s]+", "", after_inner).strip()
        after_plain = re.sub(r"<[^>]+>", "", after_inner).strip("。；;，, \t\r\n")
        if after_plain:
            return flow_html + f"<p>{after_inner}</p>"
        return flow_html

    out = re.sub(
        r"<p>(?:<[^>]+>|\s)*[^<]{0,24}跨资产传导.*?</p>",
        _upgrade_flow_para,
        out,
        flags=re.DOTALL,
    )
    return out


def build_cockpit_page(
    gold_snap: dict,
    eq_state: dict,
    latest_by_market: dict[str, DailyItem],
    stock_counts: dict[str, int],
    *,
    channels_data: dict[str, Any] | None = None,
    etf_data: dict[str, Any] | None = None,
    kline_manifest: dict[str, Any] | None = None,
    kline_core: dict[str, Any] | None = None,
    stocks: list[dict[str, Any]] | None = None,
    policy_calendar: dict[str, Any] | None = None,
) -> str:
    markets = eq_state.get("markets") or {}
    a_m = markets.get("a_share") or {}
    hk_m = markets.get("hk_stock") or {}
    us_m = markets.get("us_stock") or {}
    linkages = eq_state.get("cross_market_linkages") or {}
    rates = linkages.get("rates_fx_chain") or {}
    comm = linkages.get("commodity_mirror") or {}
    erp = linkages.get("erp_ruler") or {}
    hcw = linkages.get("household_composite_weights") or {}
    brake = linkages.get("crisis_correlation_brake") or {}
    ah_radar = linkages.get("ah_premium_radar") or {}

    gold_as_of_raw = str(gold_snap.get("as_of_short") or gold_snap.get("as_of_bjt") or "")
    gold_as_of = fmt_cst_compact(gold_as_of_raw) or str(gold_snap.get("as_of_bjt") or "")
    eq_as_of_iso = str(eq_state.get("as_of_cst") or "")
    eq_as_of = fmt_cst_compact(eq_as_of_iso) or fmt_cst_iso(eq_as_of_iso)
    alert_label = str(eq_state.get("alert_label") or gold_snap.get("daily_alert_label") or "常规追踪日")

    # Gold SSOT display (100% dynamic from gold/data_snapshot.json)
    gold_new_buy = bool(gold_snap.get("new_buy_allowed", False))
    gold_tier_code = str(gold_snap.get("tier_code") or "Tier 0").strip()
    gold_tier_label = str(gold_snap.get("tier_label") or "红灯停（暂不新买 · 新仓 0%）")
    gold_tier_short = gold_tier_label.split("（")[0].strip()
    gold_lamp_cls = _lamp_css_class(gold_tier_label)
    t1_passed = _safe_float(gold_snap.get("tier1_passed"))
    t1_total = _safe_float(gold_snap.get("tier1_total"))
    gold_pass = f"{int(t1_passed) if t1_passed is not None else 0}/{int(t1_total) if t1_total is not None else 4} 关"
    gold_spot = _positive_quote(gold_snap.get("spot_gold_ny_close_usd"))
    gold_chg = _safe_float(gold_snap.get("spot_gold_ny_change_pct"))
    gold_asia_open = _positive_quote(gold_snap.get("spot_gold_asia_open_usd"))
    gold_live = _positive_quote(gold_snap.get("spot_gold_live_usd"))
    gold_live_chg = _safe_float(gold_snap.get("spot_gold_live_change_pct"))
    lbma_pm = _positive_quote(gold_snap.get("lbma_pm_fix_usd"))
    shfe_night = _positive_quote(gold_snap.get("shfe_gold_night_rmb"))
    gold_as_of_short = str(gold_snap.get("as_of_short") or "")
    m_hr = re.search(r"\b(\d{2}):(\d{2})\b", gold_as_of_short) or re.search(r"\b(\d{2}):(\d{2})\b", gold_as_of)
    gold_hour = int(m_hr.group(1)) if m_hr else 7
    gold_hhmm = f"{m_hr.group(1)}:{m_hr.group(2)}" if m_hr else ""
    if gold_spot is not None:
        gold_spot_val = (
            f"${gold_spot:,.2f} {_fmt_chg_span(gold_chg)}" if gold_chg is not None else f"${gold_spot:,.2f}"
        )
    else:
        gold_spot_val = "待核"
    if gold_hour >= 15 and gold_live is not None:
        live_chg = gold_live_chg
        if live_chg is None and gold_spot is not None and gold_spot > 0:
            live_chg = ((gold_live / gold_spot) - 1.0) * 100.0
        live_chg_txt = f" ({live_chg:+.2f}%)" if live_chg is not None else ""
        ts_prefix = f"{gold_hhmm} " if gold_hhmm else ""
        ny_prefix = f"纽约官收 ${gold_spot:,.2f} · " if gold_spot is not None else ""
        gold_asia_sub = f"{ny_prefix}{ts_prefix}实盘 ${gold_live:,.2f}{live_chg_txt}"
    elif gold_hour >= 15 and lbma_pm is not None:
        gold_asia_sub = f"纽约官收基准 · 伦敦午定盘 ${lbma_pm:,.2f}"
    elif gold_hour < 12 and gold_asia_open is not None and (gold_spot is None or abs(gold_asia_open - gold_spot) >= 0.5):
        gold_asia_sub = f"纽约官收基准 · 亚盘约 ${gold_asia_open:,.0f}"
    else:
        gold_asia_sub = "纽约官收基准"
    gold_autd_night = _positive_quote(gold_snap.get("sge_autd_night_rmb"))
    gold_autd_day = _positive_quote(gold_snap.get("sge_autd_day_rmb"))
    gold_dfii_val = _fmt_num(gold_snap.get("dfii10_live_pct"), ".2f", suffix="%")
    gold_verdict = str(gold_snap.get("tier_cover_sub") or gold_snap.get("tier_status_sub") or "")
    rmb_ch = gold_snap.get("rmb_channels") or {}
    bank_bar = _positive_quote(rmb_ch.get("bank_bar_rmb"))
    etf_cn = _resolve_etf_cn(gold_snap)

    # SGE Au(T+D) session-aware display: >= 15:00 headlines day session; < 15:00 headlines night session
    if bank_bar is not None:
        bar_disp = f"{int(bank_bar)}" if bank_bar.is_integer() else f"{bank_bar:g}"
        bank_bar_txt = f"银行条 {bar_disp} 元"
    elif isinstance(etf_cn.get("518880"), dict) and _positive_quote(etf_cn["518880"].get("close")) is not None:
        etf_close = _positive_quote(etf_cn["518880"].get("close"))
        bank_bar_txt = f"黄金ETF {etf_close:.3f} 元"
    else:
        bank_bar_txt = ""
    if gold_hour >= 15 and gold_autd_day is not None:
        sge_main_lbl = "上金所 Au(T+D) 日盘"
        sge_main_val = f"{gold_autd_day:.2f} 元/克"
        if gold_hour >= 21 and shfe_night is not None:
            night_part = f"{gold_hhmm} 沪金夜盘 {shfe_night:.2f}" if gold_hhmm else f"沪金夜盘 {shfe_night:.2f}"
        elif gold_autd_night is not None:
            night_part = f"02:30 昨夜盘 {gold_autd_night:.2f}"
        else:
            night_part = ""
        sub_parts = [night_part, bank_bar_txt]
        sge_sub_txt = " · ".join(p for p in sub_parts if p) or "以上金所官方收盘为准"
    elif gold_hour < 5 and shfe_night is not None and gold_autd_day is not None:
        sge_main_lbl = "上金所 Au(T+D) 日盘"
        sge_main_val = f"{gold_autd_day:.2f} 元/克"
        night_part = f"{gold_hhmm} 沪金夜盘 {shfe_night:.2f}" if gold_hhmm else f"沪金夜盘 {shfe_night:.2f}"
        sub_parts = [night_part, bank_bar_txt]
        sge_sub_txt = " · ".join(p for p in sub_parts if p) or "以上金所官方收盘为准"
    elif gold_autd_night is not None:
        sge_main_lbl = "上金所 Au(T+D) 夜盘"
        sge_main_val = f"{gold_autd_night:.2f} 元/克"
        sub_parts = [f"日盘 {gold_autd_day:.2f}" if gold_autd_day is not None else "", bank_bar_txt]
        sge_sub_txt = " · ".join(p for p in sub_parts if p) or "以上金所官方夜盘为准"
    elif gold_autd_day is not None:
        sge_main_lbl = "上金所 Au(T+D) 日盘"
        sge_main_val = f"{gold_autd_day:.2f} 元/克"
        sge_sub_txt = bank_bar_txt or "以上金所官方收盘为准"
    else:
        sge_main_lbl = "上金所 Au(T+D)"
        sge_main_val = "待核"
        sge_sub_txt = bank_bar_txt or "以上金所官方披露为准"

    # Dynamic DFII10 gate threshold + percentile level
    t1_gates = gold_snap.get("tier1_gates") or []
    g1_thr = str(t1_gates[0].get("threshold", "")).strip() if (t1_gates and isinstance(t1_gates[0], dict)) else ""
    dfii_lvl = str(gold_snap.get("dfii10_level_short") or "").strip()
    dfii_sub_parts = [p for p in (g1_thr, dfii_lvl) if p]
    dfii_sub = " · ".join(dfii_sub_parts) if dfii_sub_parts else "跟踪实际利率门槛"
    gold_gate_strip_html = _render_gold_gate_strip(t1_gates)

    # Dynamic Gold new-buy label, household legend suffix, and mirror badge
    if not gold_new_buy or gold_tier_code == "Tier 0":
        gold_new_buy_val = "新仓 0%（暂不新买）"
        gold_new_buy_sub = "存量稳拿 · 家庭资产上限 10%–15%"
        gold_alloc_suffix = "（新仓0%）"
        gold_mirror_badge = f"{gold_tier_short} · 暂不新买"
    else:
        tranche = str(gold_snap.get("a_class_tranche_split") or "").strip()
        gold_new_buy_val = f"可分批建仓（{gold_tier_short}）"
        gold_new_buy_sub = (
            f"分批节奏 {tranche} · 家庭上限 10%–15%" if tranche else "严守家庭资产上限 10%–15%"
        )
        gold_alloc_suffix = f"（{gold_tier_short}）"
        gold_mirror_badge = f"{gold_tier_short} · 按档分批"

    # A-Share
    a_lamp_lbl = str(a_m.get("lamp_label") or "红灯防守期").replace("🛡️", "").strip()
    a_lamp_cls = _lamp_css_class(a_m.get("lamp", "red"))
    a_pool_num = _safe_float(a_m.get("stock_pool_count"))
    a_pool = int(a_pool_num) if a_pool_num is not None else stock_counts.get("a-share", 0)
    a_score = str(a_m.get("score") or "待核")
    a_score_num = _safe_float(a_m.get("score_num"))
    a_csi300_val = _fmt_num(a_m.get("benchmark_csi300"), ",.2f")
    a_sse_val = _fmt_num(a_m.get("benchmark_sse"), ",.2f")
    a_200w_val = _fmt_num(a_m.get("csi300_200w"), ",.0f")
    a_sse_200w_val = _fmt_num(a_m.get("sse_200w"), ",.0f")
    a_eq_cap_val = _fmt_num(a_m.get("equity_cap_pct"), ".0f", prefix="≤ ", suffix="%")
    a_erp_fwd_val = _fmt_num(a_m.get("erp_fwd_pct"), "+.2f", suffix="%")
    a_erp_ttm_val = _fmt_num(a_m.get("erp_ttm_pct"), "+.2f", suffix="%")
    a_cgb10y_val = _fmt_num(a_m.get("cgb10y_pct"), ".3f", suffix="%")

    pboc_net = _resolve_dated_metric(a_m, "pboc_total_net_100m", r"pboc_(\d+)_total_net_100m")
    if pboc_net is not None:
        a_pool_sub = f"央行总净投放 {pboc_net:+,.0f} 亿"
    else:
        margin_val = _resolve_dated_metric(a_m, "margin_balance_100m", r"margin_balance_(\d+)_100m")
        if margin_val is not None:
            a_pool_sub = f"两融余额 {margin_val:,.0f} 亿"
        else:
            a_pool_sub = f'沪深300 PE(TTM) {_fmt_num(a_m.get("pe_ttm"), ".1f", suffix="x")}'

    # HK-Stock
    hk_lamp_lbl = str(hk_m.get("lamp_label") or "红灯防守期").replace("🛡️", "").strip()
    hk_lamp_cls = _lamp_css_class(hk_m.get("lamp", "red"))
    hk_pool_num = _safe_float(hk_m.get("stock_pool_count"))
    hk_pool = int(hk_pool_num) if hk_pool_num is not None else stock_counts.get("hk-stock", 0)
    hk_score = str(hk_m.get("score") or "待核")
    hk_score_num = _safe_float(hk_m.get("score_num"))
    hk_hsi_val = _fmt_num(hk_m.get("benchmark_hsi"), ",.2f")
    hk_hstech_val = _fmt_num(hk_m.get("benchmark_hstech"), ",.2f")
    hk_200d_val = _fmt_num(hk_m.get("hsi_200d"), ",.0f")
    hk_off_cap_val = _fmt_num(hk_m.get("offshore_equity_cap_pct"), ".0f", prefix="≤ ", suffix="%")
    hk_on_cap_val = _fmt_num(hk_m.get("onshore_connect_cap_pct"), ".0f", prefix="≤ ", suffix="%")
    hk_hsahp_val = _fmt_num(hk_m.get("hsahp_index"), ".2f")
    hk_erp_usd_val = _fmt_num(hk_m.get("erp_usd_anchor_fwd_pct"), "+.2f", suffix="%")
    hk_erp_cny_val = _fmt_num(hk_m.get("erp_cny_anchor_fwd_pct"), "+.2f", suffix="%")
    hk_sb_ytd_val = _fmt_num(hk_m.get("southbound_ytd_hkd_b"), "+.0f", suffix="B")

    # US-Stock
    us_lamp_lbl = str(us_m.get("lamp_label") or "红灯防守期").replace("🛡️", "").strip()
    us_lamp_cls = _lamp_css_class(us_m.get("lamp", "red"))
    us_pool_num = _safe_float(us_m.get("stock_pool_count"))
    us_pool = int(us_pool_num) if us_pool_num is not None else stock_counts.get("us-stock", 0)
    us_score = str(us_m.get("score") or "待核")
    us_score_num = _safe_float(us_m.get("score_num"))
    us_alloc_str = (
        f'{_fmt_num(us_m.get("equity_cap_pct"), ".0f", suffix="%")} 防弹衣 + '
        f'{_fmt_num(us_m.get("cash_tbill_pct"), ".0f", suffix="%")} 短债 + '
        f'{_fmt_num(us_m.get("gold_hold_pct"), ".0f", suffix="%")} 存量金'
    )
    us_sp = _safe_float(us_m.get("benchmark_sp500"))
    us_sp_val = _fmt_num(us_sp, ",.2f")
    us_high = _positive_quote(us_m.get("sp500_high"))
    us_tech_cap_val = _fmt_num(us_m.get("tech_new_cap_pct"), ".0f", suffix="%")
    if us_high is not None and us_sp is not None and us_sp > 0:
        us_dd = ((us_sp / us_high) - 1.0) * 100.0
        us_pool_sub = f"距前高 {us_high:,.0f} 回撤 {us_dd:+.1f}% · 11 大板块"
    else:
        us_pool_sub = f"科技新增严控 {us_tech_cap_val} · 全板块覆盖"
    us_200d_val = _fmt_num(us_m.get("sp500_200d"), ",.0f")
    us_erp_fwd_val = _fmt_num(us_m.get("erp_fwd_pct"), "+.2f", suffix="%")
    us_erp_ttm_val = _fmt_num(us_m.get("erp_ttm_pct"), "+.2f", suffix="%")
    us_pe_fwd_val = _fmt_num(us_m.get("pe_fwd"), ".1f", suffix="x")
    us_pe_ttm_val = _fmt_num(us_m.get("pe_ttm"), ".1f", suffix="x")

    # 3+1 Global Crisis Circuit Breakers (100% null-safe)
    vix_close = _safe_float(brake.get("vix_close"))
    if vix_close is None:
        vix_close = _safe_float(gold_snap.get("vix_close"))
    vix_high = _safe_float(brake.get("vix_intraday_high"))
    vix_prev_high = _safe_float(brake.get("vix_prev_session_high"))
    if vix_prev_high is None:
        vix_prev_high = _safe_float(gold_snap.get("vix_prev_session_high"))
    vix_10d_high = _safe_float(gold_snap.get("vix_10d_peak_intraday"))
    if vix_high is not None:
        vix_high_label = f"盘中峰 {vix_high:.2f}"
    elif vix_prev_high is not None:
        vix_high_label = f"前日盘中峰 {vix_prev_high:.2f}"
    elif vix_10d_high is not None:
        vix_high_label = f"10日盘中峰 {vix_10d_high:.2f}"
    else:
        vix_high_label = "盘中峰待核"
    vix_eff_high = vix_high if vix_high is not None else vix_prev_high
    vix_thr = _safe_float(brake.get("vix_brake_threshold"))
    if vix_thr is None:
        vix_thr = 30.0
    if vix_close is None:
        vix_chip = ("chip-warn", "待核")
        vix_meter_pct = 0.0
    else:
        vix_caution = (vix_eff_high is not None and vix_eff_high >= vix_thr) or vix_close >= 24
        vix_chip = ("chip-danger", "已触红线") if vix_close >= vix_thr else (
            ("chip-warn", "逼近警戒") if vix_caution else ("chip-ok", "安全区间")
        )
        vix_meter_pct = max(4.0, min(100.0, (vix_close / max(vix_thr, 1.0)) * 100.0))
    vix_close_val = _fmt_num(vix_close, ".2f")

    usdjpy = _safe_float(brake.get("usdjpy_level"))
    if usdjpy is None:
        usdjpy = _safe_float(rates.get("usd_jpy"))
    jpy_drop_thr_raw = _safe_float(brake.get("usdjpy_3d_drop_brake_pct"))
    jpy_drop_thr = abs(jpy_drop_thr_raw) if jpy_drop_thr_raw is not None else 3.0
    if usdjpy is None:
        jpy_chip = ("chip-warn", "待核")
        jpy_meter_pct = 0.0
    else:
        jpy_chip = ("chip-danger", "干预高危") if usdjpy >= 160 else (
            ("chip-warn", "紧盯干预") if usdjpy >= 155 else ("chip-ok", "平稳")
        )
        jpy_meter_pct = max(4.0, min(100.0, ((usdjpy - 135.0) / 30.0) * 100.0))
    usdjpy_val = _fmt_num(usdjpy, ".2f")

    us10y = _safe_float(rates.get("us10y_pct"))
    if us10y is None:
        us10y = _safe_float(us_m.get("us10y_pct"))
    _rb_us_tmp = (eq_state.get("rates_bonds_core") or {}).get("us_rates") if isinstance(eq_state.get("rates_bonds_core"), dict) else {}
    us10y_live_br = _safe_float((_rb_us_tmp or {}).get("us10y_asia_live_pct")) or _safe_float(rates.get("us10y_live_pct"))
    us10y_thr = _safe_float(brake.get("us10y_brake_pct"))
    if us10y_thr is None:
        us10y_thr = 5.25
    if us10y is None:
        us10y_chip = ("chip-warn", "待核")
        us10y_meter_pct = 0.0
    else:
        us10y_chip = ("chip-danger", "触及熔断") if us10y >= us10y_thr else (
            ("chip-warn", "高息承压") if us10y >= 4.7 else ("chip-ok", "温和")
        )
        us10y_meter_pct = max(4.0, min(100.0, ((us10y - 3.0) / max(us10y_thr - 3.0, 0.5)) * 100.0))
    us10y_val = _fmt_num(us10y, ".3f", suffix="%")
    us10y_thr_line = (
        f"官收基准（实盘 {us10y_live_br:.2f}%）｜熔断线：突破 {us10y_thr:.2f}%"
        if (us10y is not None and us10y_live_br is not None and abs(us10y_live_br - us10y) >= 0.01)
        else f"熔断线：突破 {us10y_thr:.2f}%"
    )

    hkma_bal = _safe_float(rates.get("hkma_agg_bal_hkd_100m"))
    hkma_thr = _safe_float(brake.get("hkma_agg_bal_brake_100m"))
    if hkma_thr is None:
        hkma_thr = 400.0
    if hkma_bal is None:
        hkma_chip = ("chip-warn", "待核")
        hkma_meter_pct = 0.0
    else:
        hkma_chip = ("chip-danger", "触及底线") if hkma_bal <= hkma_thr else (
            ("chip-warn", "薄缓冲警戒") if hkma_bal < 650 else ("chip-ok", "缓冲充裕")
        )
        hkma_meter_pct = max(4.0, min(100.0, ((1200.0 - hkma_bal) / max(1200.0 - hkma_thr, 100.0)) * 100.0))
    hkma_short_val = _fmt_num(hkma_bal, ".1f", suffix="亿")
    hkma_full_val = _fmt_num(hkma_bal, ".2f", suffix=" 亿")

    all_chips = [vix_chip, jpy_chip, us10y_chip, hkma_chip]
    n_danger = sum(1 for cls_c, _ in all_chips if cls_c == "chip-danger")
    n_warn = sum(1 for cls_c, _ in all_chips if cls_c == "chip-warn")
    brake_triggered = bool(brake.get("brake_triggered", False))
    if brake_triggered:
        brake_overall = '<span class="status-chip chip-danger">总熔断已触发 · 全面降险</span>'
    elif n_danger > 0:
        brake_overall = f'<span class="status-chip chip-danger">总熔断未触发 · {n_danger} 项触及高危线</span>'
    elif n_warn >= 2:
        brake_overall = f'<span class="status-chip chip-warn">总熔断未触发 · {n_warn} 项处警戒外围</span>'
    elif n_warn == 1:
        brake_overall = '<span class="status-chip chip-warn">总熔断未触发 · 1 项处警戒外围</span>'
    else:
        brake_overall = '<span class="status-chip chip-ok">总熔断未触发 · 4 项均处安全区间</span>'

    # Three-Market ERP Horizontal Visual Bar (0% to 10% scale)
    erp_rows_data = [
        ("🇭🇰 港股恒指（人民币锚前瞻 ERP）", _safe_float(erp.get("hsi_erp_cny_fwd_pct")), _safe_float(erp.get("hsi_erp_cny_ttm_pct")), "erp-hk", "erp-fill-hk"),
        ("🇨🇳 A 股沪深300（前瞻 ERP）", _safe_float(erp.get("csi300_erp_fwd_pct")), _safe_float(erp.get("csi300_erp_ttm_pct")), "erp-a", "erp-fill-a"),
        ("🇭🇰 港股恒指（美元锚前瞻 ERP）", _safe_float(erp.get("hsi_erp_usd_fwd_pct")), _safe_float(erp.get("hsi_erp_usd_ttm_pct")), "erp-hk", "erp-fill-hk-usd"),
        ("🇺🇸 美股标普500（前瞻 ERP）", _safe_float(erp.get("sp500_erp_fwd_pct")), _safe_float(erp.get("sp500_erp_ttm_pct")), "erp-us", "erp-fill-us"),
    ]
    erp_bars_html = ""
    for lbl, val, ttm_val, txt_cls, fill_cls in erp_rows_data:
        sub_lbl = f"静态 {ttm_val:+.2f}%" if ttm_val is not None else "静态 待核"
        if val is not None:
            width_pct = max(4.0, min(100.0, (val / 10.0) * 100.0))
            val_disp = f"{val:+.2f}%"
        else:
            width_pct = 0.0
            val_disp = "待核"
        erp_bars_html += (
            f'<div class="erp-row">'
            f'<div class="erp-head"><span class="erp-name">{lbl}</span>'
            f'<span class="erp-num {txt_cls}">{val_disp} <span class="erp-sub">({sub_lbl})</span></span></div>'
            f'<div class="erp-track"><div class="erp-fill {fill_cls}" style="width:{width_pct:.1f}%;"></div></div>'
            f"</div>"
        )

    # Household Composite Allocation (100% null-safe; omit 0% segments cleanly)
    eq_pct_f = _safe_float(hcw.get("equity_total_pct"))
    cb_pct_f = _safe_float(hcw.get("convertible_bond_pct"))
    bc_pct_f = _safe_float(hcw.get("bonds_and_cash_pct"))
    gd_pct_f = _safe_float(hcw.get("gold_existing_hold_pct"))
    hcw_complete = all(x is not None for x in (eq_pct_f, cb_pct_f, bc_pct_f, gd_pct_f))
    eq_pct = int(round(eq_pct_f)) if eq_pct_f is not None else 0
    cb_pct = int(round(cb_pct_f)) if cb_pct_f is not None else 0
    bc_pct = int(round(bc_pct_f)) if bc_pct_f is not None else 0
    gd_pct = int(round(gd_pct_f)) if gd_pct_f is not None else 0
    hcw_sum_disp = f"合计 {eq_pct + cb_pct + bc_pct + gd_pct}%" if hcw_complete else "待核"
    hcw_note = str(hcw.get("formula_note") or "")
    eq_seg_lbl = f"{eq_pct}% 股" if eq_pct >= 12 else (f"{eq_pct}%" if eq_pct >= 4 else "")
    cb_seg_lbl = f"{cb_pct}% 转" if cb_pct >= 12 else (f"{cb_pct}%" if cb_pct >= 3 else "")
    bc_seg_lbl = f"{bc_pct}% 债现" if bc_pct >= 14 else (f"{bc_pct}%" if bc_pct >= 4 else "")
    gd_seg_lbl = f"{gd_pct}% 金" if gd_pct >= 10 else (f"{gd_pct}%" if gd_pct >= 4 else "")
    alloc_segs_html = "".join(
        f'<div class="alloc-seg" style="width:{pct}%;background:{bg};" title="{esc(lbl)} {pct}%">{esc(seg_txt)}</div>'
        for pct, bg, lbl, seg_txt in (
            (eq_pct, "#1d4ed8", "股票底座", eq_seg_lbl),
            (cb_pct, "#0f766e", "可转债", cb_seg_lbl),
            (bc_pct, "#475569", "国债短债与现金", bc_seg_lbl),
            (gd_pct, "#b45309", "存量黄金", gd_seg_lbl),
        )
        if pct > 0
    )

    alloc_breakdown_html = ""
    hcw_accounts = hcw.get("accounts")
    if isinstance(hcw_accounts, dict) and hcw_accounts:
        acc_names = {
            "a_share": "境内人民币池",
            "hk_stock": "港股离岸池",
            "us_stock": "美股离岸池",
        }
        acc_rows: list[str] = []
        for ak, av in hcw_accounts.items():
            if not isinstance(av, dict):
                continue
            w_s = _fmt_num(av.get("weight_pct"), ".0f", suffix="%")
            a_eq = _fmt_num(av.get("equity_total_pct"), ".0f", suffix="%")
            a_cb = _fmt_num(av.get("convertible_bond_pct"), ".0f", suffix="%")
            a_bc = _fmt_num(av.get("bonds_and_cash_pct"), ".0f", suffix="%")
            a_gd = _fmt_num(av.get("gold_existing_hold_pct"), ".0f", suffix="%")
            mix_parts = [f"股 {a_eq}"]
            cb_n = _safe_float(av.get("convertible_bond_pct"))
            if cb_n is not None and cb_n > 0:
                mix_parts.append(f"转债 {a_cb}")
            mix_parts.append(f"债现 {a_bc}")
            mix_parts.append(f"存量金 {a_gd}")
            acc_rows.append(
                '<div class="alloc-acc-row">'
                f'<span class="alloc-acc-name">{esc(acc_names.get(ak, ak))}（权重 {w_s}）</span>'
                f'<span class="alloc-acc-mix">{" · ".join(mix_parts)}</span>'
                "</div>"
            )
        if acc_rows:
            alloc_breakdown_html = (
                '<details class="alloc-breakdown">'
                "<summary>展开三账户加权拆解</summary>"
                f'<div class="alloc-acc-list">{"".join(acc_rows)}</div>'
                "</details>"
            )

    # Commodity & FX Mirror Chips (100% dynamic contract / regime / timestamp-matched BTC)
    brent_usd = _safe_float(comm.get("brent_usd"))
    if brent_usd is None:
        brent_usd = _safe_float(gold_snap.get("brent_settle_usd"))
    brent_chg = _safe_float(comm.get("brent_chg_pct"))
    if brent_chg is None:
        brent_chg = _safe_float(gold_snap.get("brent_change_pct"))
    wti_usd = _safe_float(comm.get("wti_usd"))
    if wti_usd is None:
        wti_usd = _safe_float(gold_snap.get("wti_settle_usd"))
    brent_contract = str(comm.get("brent_contract") or "").strip()
    brent_lbl = f"布伦特原油 {brent_contract}" if brent_contract else "布伦特原油"
    brent_val = _fmt_num(brent_usd, ".2f", prefix="$")
    wti_val = _fmt_num(wti_usd, ".2f", prefix="$")

    copper_usd = _safe_float(comm.get("comex_copper_usd_lb"))
    if copper_usd is None:
        copper_usd = _safe_float(gold_snap.get("comex_copper_usd_lb"))
    copper_chg = _safe_float(comm.get("comex_copper_chg_pct"))
    if copper_chg is None:
        copper_chg = _safe_float(gold_snap.get("comex_copper_change_pct"))
    copper_val = _fmt_num(copper_usd, ".4f", prefix="$", suffix="/磅")
    copper_regime_raw = str(comm.get("copper_regime") or "").lower()
    if "bear" in copper_regime_raw:
        copper_regime_cn = "步入技术熊市"
    elif "bull" in copper_regime_raw:
        copper_regime_cn = "多头趋势区"
    elif "correction" in copper_regime_raw or "pullback" in copper_regime_raw:
        copper_regime_cn = "高位回调区"
    elif copper_regime_raw:
        copper_regime_cn = "宏观景气观察"
    else:
        copper_regime_cn = "工业景气风向标"

    comm_btc = _positive_quote(comm.get("btc_usd"))
    comm_btc_chg = _safe_float(comm.get("btc_chg_pct"))
    gold_btc = _positive_quote(gold_snap.get("btc_usd"))
    gold_btc_chg = _safe_float(gold_snap.get("btc_change_pct"))
    if comm_btc is not None and comm_btc_chg is not None:
        btc_usd = comm_btc
        btc_sub_html = f"{_fmt_chg_span(comm_btc_chg)} · 流动敏感风向标"
    elif comm_btc is not None and (gold_btc is None or abs(comm_btc - gold_btc) > 1.0):
        btc_usd = comm_btc
        btc_sub_html = "股市快照锚 · 流动敏感风向标"
    else:
        btc_usd = gold_btc if gold_btc is not None else comm_btc
        btc_sub_html = f"{_fmt_chg_span(gold_btc_chg)} · 流动敏感风向标"
    btc_val = _fmt_num(btc_usd, ",.0f", prefix="$")

    usd_cnh = _positive_quote(rates.get("usd_cnh"))
    usd_cny = _positive_quote(rates.get("usd_cny_1630"))
    if usd_cnh is None and usd_cny is None:
        stamp = r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})"
        gold_stamp = re.match(stamp, gold_as_of_short)
        equity_stamp = re.match(stamp, str(eq_state.get("as_of_cst") or ""))
        if (gold_stamp and equity_stamp and gold_stamp[1] == equity_stamp[1]
                and min(gold_stamp[2], equity_stamp[2]) >= "16:30"):
            usd_cny = _positive_quote(gold_snap.get("usd_cny_1630"))
    if usd_cnh is not None:
        rmb_label = "美元 / 离岸人民币"
        rmb_value = f"{usd_cnh:.4f}"
    elif usd_cny is not None:
        rmb_label = "美元 / 在岸人民币（16:30 收盘）"
        rmb_value = f"{usd_cny:.4f}"
    else:
        rmb_label = "美元 / 人民币"
        rmb_value = "待核"
    usd_hkd = _positive_quote(rates.get("usd_hkd"))
    usd_hkd_value = f"{usd_hkd:.3f}" if usd_hkd is not None else "待核"
    cfets = _positive_quote(rates.get("cfets_cny_fixing"))
    cfets_value = f"{cfets:.4f}" if cfets is not None else "待核"
    hibor_value = _fmt_num(rates.get("hibor_1m_pct"), ".3f", suffix="%")

    # A/H Premium Mini-Strip (top 2 highest A premiums + top 3 deepest A discounts)
    ah_panel_html = ""
    ah_benchmarks = ah_radar.get("benchmarks")
    if isinstance(ah_benchmarks, list) and ah_benchmarks:
        valid_ah = [
            (str(r.get("name") or "").strip(), float(p))
            for r in ah_benchmarks
            if isinstance(r, dict)
            and str(r.get("name") or "").strip()
            and (p := _safe_float(r.get("ah_premium_pct"))) is not None
        ]
        top_prems = sorted((x for x in valid_ah if x[1] > 0), key=lambda x: x[1], reverse=True)[:2]
        top_discs = sorted((x for x in valid_ah if x[1] < 0), key=lambda x: x[1])[:3]
        ah_pills: list[str] = []
        for nm, pct in top_prems:
            ah_pills.append(
                f'<div class="ah-pill ah-prem"><span class="ah-name">{esc(nm)}</span>'
                f'<span class="ah-val">+{pct:.1f}%</span></div>'
            )
        for nm, pct in top_discs:
            ah_pills.append(
                f'<div class="ah-pill ah-disc"><span class="ah-name">{esc(nm)}</span>'
                f'<span class="ah-val">{pct:+.1f}%</span></div>'
            )
        if ah_pills:
            ah_panel_html = (
                '<div class="panel-card span-2">'
                '<div class="panel-title">'
                f'<span>↔ A/H 溢价与倒挂风向标（恒生 AH 溢价指数 {hk_hsahp_val}）</span>'
                '<a class="btn btn-sm" href="screener.html#view=ah-matrix">打开 27 对 A/H 税后比价矩阵 →</a>'
                "</div>"
                f'<div class="ah-strip">{"".join(ah_pills)}</div>'
                "</div>"
            )

    # Synthesize 1-sentence cross-market verdict for Hero Command Deck
    total_pool = a_pool + hk_pool + us_pool
    all_red = all(c == "lamp-red" for c in (gold_lamp_cls, a_lamp_cls, hk_lamp_cls, us_lamp_cls))
    if all_red:
        def_tail = f"，家庭综合债现防守占比 {bc_pct}%" if hcw_complete else ""
        hero_verdict = (
            f"六大市场格局：黄金维持{gold_tier_short}（暂不新买 · {gold_pass}），"
            f"A/港/美股严守红灯仓位上限，中美债短端筑盾、非美卫星严控溢价{def_tail}。"
        )
    else:
        gold_act = f"{gold_tier_short}（暂不新买）" if (not gold_new_buy or gold_tier_code == "Tier 0") else f"{gold_tier_short}（按档分批）"
        hero_verdict = (
            f"六大市场格局：黄金{gold_act}（{gold_pass}）；三市大盘水温 A股 {a_score} · 港股 {hk_score} · 美股 {us_score}，"
            "同步联动中美债率与非美卫星按红绿灯严控回撤。"
        )

    # Data Completeness & Holiday Disclosure Bar
    caveats = collect_data_caveats(gold_snap, eq_state)
    holidays = collect_holiday_alerts(eq_state, max_days=7)
    disclosure_html = render_cockpit_disclosure(caveats, holidays)

    # Latest Daily Feed Grid (4 markets)
    feed_cards_html = ""
    for mk in ("gold", "a-share", "hk-stock", "us-stock"):
        it = latest_by_market.get(mk)
        if not it:
            continue
        mm = MARKET_META[mk]
        chart_pill = f'<span class="session-pill">{it.chart_count} 图</span>' if it.chart_count else ""
        feed_cards_html += (
            f'<a class="feed-card" href="{mm["latest_href"]}">'
            f'<div class="feed-meta">'
            f'<span class="mkt-badge mkt-{mk}">{mm["emoji"]} {mm["short"]}</span>'
            f'{_edition_pill_html(it.edition_type)}'
            f'<span class="session-pill">{esc(it.date_str)} · {esc(it.session_label)}</span>'
            f"{chart_pill}"
            f'<span class="session-pill">约 {it.read_minutes} 分钟</span>'
            f"</div>"
            f'<div class="feed-title">{esc(it.title)}</div>'
            f'<div class="feed-summary">{esc(it.summary)}</div>'
            f"</a>"
        )

    etf_list = (etf_data.get("etfs") or []) if isinstance(etf_data, dict) else []
    a_etf_count = sum(1 for x in etf_list if isinstance(x, dict) and x.get("market") == "a-share")
    ch_list_raw = (channels_data.get("channels") if isinstance(channels_data, dict) else []) or []
    ch_list = [c for c in ch_list_raw if isinstance(c, dict) and str(c.get("id", "")).strip()]
    ch_count_num = len(ch_list)

    flagship_shelf_html = _render_flagship_web_shelf(
        {"a-share": a_pool, "hk-stock": hk_pool, "us-stock": us_pool},
        a_etf_count=a_etf_count,
        etf_total=len(etf_list),
        channel_count=ch_count_num,
    )

    # Layer 1A: Today's Beginner Action Lights (reads beginner_action_lights with Gold-Tier-0-safe fallback)
    gold_blocked = (not gold_new_buy) or (gold_tier_code == "Tier 0")

    def _extract_action_items(raw_seq: Any) -> list[str]:
        out_items: list[str] = []
        if isinstance(raw_seq, list):
            for x in raw_seq[:4]:
                if isinstance(x, str) and x.strip():
                    out_items.append(x.strip())
                elif isinstance(x, dict):
                    t = str(x.get("title") or x.get("action") or "").strip()
                    d = str(x.get("detail") or x.get("reason") or x.get("text") or "").strip()
                    comb = f"{t}：{d}" if (t and d) else (t or d)
                    if comb:
                        out_items.append(comb)
        return out_items

    bal_raw = channels_data.get("beginner_action_lights") if isinstance(channels_data, dict) else None
    al_do_items: list[str] = []
    al_avoid_items: list[str] = []
    if isinstance(bal_raw, dict):
        al_do_items = _extract_action_items(
            bal_raw.get("can_do") or bal_raw.get("do_today") or bal_raw.get("do") or bal_raw.get("green")
        )
        al_avoid_items = _extract_action_items(
            bal_raw.get("avoid") or bal_raw.get("avoid_today") or bal_raw.get("dont") or bal_raw.get("red")
        )
    if not al_do_items:
        al_do_items = [
            "活钱升级：把闲置零钱与待机现金泊入短融 ETF（511360）、同业存单 AAA 或周四国债逆回购。",
            "稳钱压舱：1–3 年确定资金优先配置储蓄国债、高等级债券 ETF 或单行 50 万以内可转让定期存款。",
            "按表控仓：老底仓稳拿高股息防弹衣底座，不急着追高，先花 3 分钟用四笔钱理清个人资金期限。",
        ]
    if not al_avoid_items:
        gold_avoid_line = (
            "严禁抢跑新买黄金或黄金股：黄金当前红灯停（老持仓稳拿不乱卖，新钱先停在稳钱池静待四关信号）。"
            if gold_blocked
            else "严守黄金上限纪律：任何情形下家庭黄金总占比严控 10%–15%，不加杠杆追涨。"
        )
        al_avoid_items = [
            gold_avoid_line,
            "远离高溢价接盘：跨境美股 QDII 与商品 LOF 场内溢价超 3% 坚决不追，情绪回落或退市将令溢价归零。",
            "不把波动产品当保本存款：避开破净隐忧重的伪稳健固收+理财，切忌重仓 30 年超长国债当活钱。",
        ]
    def _fmt_action_light_li(text: str) -> str:
        if "：" in text:
            head, rest = text.split("：", 1)
            return f"<li><strong>{esc(head)}：</strong>{esc(rest)}</li>"
        return f"<li>{esc(text)}</li>"

    action_lights_html = (
        '<section class="action-lights-grid" aria-label="今日行动红绿灯">'
        '<div class="action-light-card al-do">'
        '<div class="al-head"><span>🟢 今天可以做的 3 件事</span><a href="guide.html" class="al-link">新手 3 分钟指南 →</a></div>'
        f'<ul class="al-list">{"".join(_fmt_action_light_li(x) for x in al_do_items[:3])}</ul>'
        "</div>"
        '<div class="action-light-card al-avoid">'
        '<div class="al-head"><span>🔴 今天先别碰的 3 件事</span><a href="channels.html#sec-warning-wall" class="al-link">看双层风控警示墙 →</a></div>'
        f'<ul class="al-list">{"".join(_fmt_action_light_li(x) for x in al_avoid_items[:3])}</ul>'
        "</div>"
        "</section>"
    )

    # Layer 1B: Four-Buckets Beginner Guide + Interactive Capital-Tier Selector
    gold_bucket_note = "黄金当前红灯停暂不新买" if gold_blocked else "黄金按档分批不超上限"
    four_buckets_html = f"""
    <section class="buckets-section" id="sec-four-buckets" aria-label="新手先看：钱怎么分四笔">
      <div class="buckets-head">
        <div>
          <h2 class="buckets-title">新手先看：先按「用钱时间」把钱分四笔</h2>
          <p class="sec-sub" style="margin:2px 0 0 0;">用{_term_tip("four_buckets", "四笔钱")}管住期限：点击下方任意一笔，直接定位对应合规渠道；切换资金档位自动淡化高门槛产品</p>
        </div>
        <div class="cap-tier-bar" role="group" aria-label="按手头可投资金档位过滤">
          <button type="button" class="cap-tier-pill active" data-cap-tier="all">全部档位</button>
          <button type="button" class="cap-tier-pill" data-cap-tier="1-5w">1–5万刚起步</button>
          <button type="button" class="cap-tier-pill" data-cap-tier="10-20w">10–20万攒桶金</button>
          <button type="button" class="cap-tier-pill" data-cap-tier="30-50w">30–50万家庭配</button>
        </div>
      </div>
      <div class="cap-tier-hint" id="cap-tier-hint">当前展示全部档位：建议先留足 3–6 个月活钱与基础保障，再按期限匹配稳钱与长钱。</div>
      <div class="buckets-grid">
        <button type="button" class="bucket-card" data-jump-bucket="liquid">
          <div class="bucket-top"><span class="bucket-icon">💧</span><span class="bucket-horizon">0–6 个月随时用</span></div>
          <div class="bucket-title">第一笔：活钱应急池</div>
          <div class="bucket-desc">留出 3–6 个月生活费。核对到账时间和净值波动，短融 ETF 与同业存单基金均有本金波动风险。</div>
          <div class="bucket-tags"><span class="bucket-tag">短融 ETF</span><span class="bucket-tag">国债逆回购</span><span class="bucket-tag">同业存单 AAA</span></div>
          <div class="bucket-foot">筛选对应渠道 ↓</div>
        </button>
        <button type="button" class="bucket-card" data-jump-bucket="stable">
          <div class="bucket-top"><span class="bucket-icon">🛡️</span><span class="bucket-horizon">1–3 年明确要用</span></div>
          <div class="bucket-title">第二笔：稳钱压舱池</div>
          <div class="bucket-desc">买车、首付、学费等确定支出，追求稳健票息与极小回撤，严守 50 万存保线。</div>
          <div class="bucket-tags"><span class="bucket-tag">储蓄国债</span><span class="bucket-tag">债券 ETF</span><span class="bucket-tag">定期/大额存单</span></div>
          <div class="bucket-foot">筛选对应渠道 ↓</div>
        </button>
        <button type="button" class="bucket-card" data-jump-bucket="growth">
          <div class="bucket-top"><span class="bucket-icon">🌱</span><span class="bucket-horizon">3–5 年以上闲钱</span></div>
          <div class="bucket-title">第三笔：长钱复利池</div>
          <div class="bucket-desc">严守红绿灯节奏分批布局宽基、锁汇互认债、转债与实体租金（{esc(gold_bucket_note)}）。</div>
          <div class="bucket-tags"><span class="bucket-tag">红利/宽基 ETF</span><span class="bucket-tag">锁汇 MRF</span><span class="bucket-tag">转债/REITs</span></div>
          <div class="bucket-foot">筛选对应渠道 ↓</div>
        </button>
        <button type="button" class="bucket-card" data-jump-bucket="protection">
          <div class="bucket-top"><span class="bucket-icon">🏥</span><span class="bucket-horizon">保障底线 · 10年+</span></div>
          <div class="bucket-title">第四笔：保障与超长锁息</div>
          <div class="bucket-desc">先配齐医保、百万医疗与意外险兜底；20%+ 税档再配个人养老金，10 年不动钱再看储蓄险。</div>
          <div class="bucket-tags"><span class="bucket-tag">个人养老金</span><span class="bucket-tag">税优健康险</span><span class="bucket-tag">储蓄型保险</span></div>
          <div class="bucket-foot">筛选对应渠道 ↓</div>
        </button>
      </div>
      {_render_wallet_calculator(gold_snap, eq_state, kline_manifest)}
    </section>
    """

    def _stance_badge_cls(lamp_cls: str, *, is_gold_mkt: bool = False) -> str:
        if is_gold_mkt:
            return "stance-stop" if gold_blocked else "stance-go"
        if lamp_cls == "lamp-red":
            return "stance-defend"
        if lamp_cls == "lamp-amber":
            return "stance-watch"
        return "stance-go"

    us_eq_cap_s = _fmt_num(us_m.get("equity_cap_pct"), ".0f", prefix="≤ ", suffix="%")
    a_stance_txt = (
        f"防守建底期 · 股票上限 {a_eq_cap_val}（空仓可分批建底，不追高）"
        if a_lamp_cls == "lamp-red"
        else ("分歧观察期 · 按安全锚小步分批" if a_lamp_cls == "lamp-amber" else "条件齐备 · 按期限分批配置")
    )
    hk_stance_txt = (
        f"中国离岸折价腿 · 离岸 {hk_off_cap_val} / 港股通 {hk_on_cap_val}"
        if hk_lamp_cls == "lamp-red"
        else "中国离岸折价腿 · 按安全锚分批"
    )
    us_stance_txt = (
        f"防守建底期 · 防弹衣 {us_eq_cap_s} / 科技新仓严控 {us_tech_cap_val}（不追高）"
        if us_lamp_cls == "lamp-red"
        else ("分歧观察期 · 聚焦低估防弹衣" if us_lamp_cls == "lamp-amber" else "条件齐备 · 宽基分批配置")
    )
    gold_stance_txt = (
        "红灯停 · 新仓严格 0%（存量稳拿不乱割，静待四关）"
        if gold_blocked
        else "条件齐备 · 按档分批（家庭总上限 10%–15%）"
    )

    home_channels_section_html = ""
    if ch_list:
        ch_as_of = str((channels_data or {}).get("as_of_label") or eq_as_of or "最新班次")
        home_channels_section_html = f"""
    <div class="sec-head" id="sec-multi-channels">
      <div>
        <h2>中国大陆 {ch_count_num} 大个人合规多元投资渠道（4 角色分层 · 3×4 速览）</h2>
        <span class="sec-sub" id="ch-count" role="status">共 {ch_count_num} 大渠道 · 基准 {esc(ch_as_of)}</span>
      </div>
      <a href="channels.html" class="btn btn-sm btn-primary">打开 {ch_count_num} 大渠道完整对比与筛选 →</a>
    </div>
    <div id="home-ch-active-bar" class="home-ch-active-bar" hidden></div>
    <section class="channel-list">
      {_render_channel_overview_cards(ch_list, compact=True)}
    </section>
    """

    home_etf_section_html = _render_home_etf_showcase(etf_data, total_pool)
    etf_count_num = len(etf_list)

    multi_idx = _resolve_multi_index_groups(gold_snap, eq_state, kline_manifest)
    total_kline_cnt = (
        int(kline_manifest.get("total_instruments", 0))
        if isinstance(kline_manifest, dict) and kline_manifest.get("total_instruments")
        else 0
    )
    crisis_ribbon_html = _render_crisis_ribbon(gold_snap, eq_state, gold_blocked)
    home_kline_deck_html = _render_home_kline_deck(multi_idx, total_kline_cnt)

    a_matrix_html = _render_market_index_matrix(multi_idx["a_share"], "a_share", visible_count=6)
    hk_ah_extra = (
        f'<a class="idx-tile idx-tile-link m-sub-tile-wide" href="screener.html#view=ah-matrix" title="查看 27 对 A/H 税后比价矩阵">'
        '<span class="idx-tile-top"><span class="idx-tile-name">AH溢价指数</span><span class="idx-tile-code">HSAHP</span></span>'
        f'<span class="idx-tile-bot"><span class="idx-tile-val">{hk_hsahp_val}</span><span class="idx-tile-chg">27对比价 →</span></span></a>'
    )
    hk_matrix_rows = [r for r in multi_idx["hk_stock"] if r.get("id") != "idx_HSAHP"]
    hk_matrix_html = _render_market_index_matrix(hk_matrix_rows, "hk_stock", visible_count=4, extra_badge_html=hk_ah_extra)
    us_matrix_html = _render_market_index_matrix(multi_idx["us_stock"], "us_stock", visible_count=6)
    gold_matrix_html = _render_market_index_matrix(multi_idx["gold"], "gold_macro", visible_count=6)

    # Compact home watchlist index (<28KB, 4 fields per stock/ETF, zero long prose)
    watch_idx_map: dict[str, dict[str, str]] = {}
    for st in stocks or []:
        dk = f"{st['market']}:{st['code']}"
        watch_idx_map[dk] = {
            "name": str(st.get("name") or ""),
            "code": str(st.get("code") or ""),
            "price": str(st.get("price") or ""),
            "price_date": _valid_iso_date(_extract_iso_date(st.get("price_updated_at"))),
            "role": str(st.get("action_label") or ""),
        }
    for etf in etf_list:
        if isinstance(etf, dict) and etf.get("code"):
            cd = str(etf["code"])
            watch_idx_map[cd] = {
                "name": _clean_etf_display_text(etf.get("name", "")),
                "code": cd,
                "role": str(etf.get("action_role") or ""),
            }
    safe_watch_idx_json = json.dumps(watch_idx_map, ensure_ascii=False).replace("</", "<\\/")
    home_watchlist_html = (
        '<section class="watch-bar" id="home-watchlist-bar" hidden aria-label="我的自选今日速览">'
        '<div class="watch-bar-head">'
        '<span class="watch-bar-title">★ 我的自选速览 (<span id="home-watchlist-cnt">0</span>)</span>'
        '<div class="watch-bar-links">'
        '<a class="btn btn-sm" href="charts.html">K线终端</a>'
        '<a class="btn btn-sm" href="screener.html#preset=watchlist">自选股池</a>'
        '<a class="btn btn-sm" href="etfs.html#preset=watchlist">自选ETF</a>'
        "</div></div>"
        '<div class="watch-pill-grid" id="home-watchlist-items"></div>'
        f'<script id="home-watch-index" type="application/json">{safe_watch_idx_json}</script>'
        "</section>"
    )

    def _macro_sub_html(row: dict[str, Any]) -> str:
        rid = str(row.get("id") or "")
        rv = _safe_float(row.get("value"))
        chg_v = row.get("change_pct")
        chg_part = _fmt_chg_span(chg_v) if (isinstance(chg_v, (int, float)) and isfinite(chg_v)) else ""
        ref_part = ""
        if rid == "rate_US10Y" and us10y is not None and rv is not None and abs(rv - us10y) >= 0.01:
            ref_part = f"官收 {us10y:.2f}%"
        elif rid == "cmd_OIL" and brent_usd is not None and rv is not None and abs(rv - brent_usd) >= 0.05:
            ref_part = f"官结 ${brent_usd:.2f}"
        elif rid == "cmd_CL" and wti_usd is not None and rv is not None and abs(rv - wti_usd) >= 0.05:
            ref_part = f"官结 ${wti_usd:.2f}"
        parts = [p for p in (ref_part, chg_part, esc(_quote_provenance(row)), "📈 K线") if p]
        return " · ".join(parts)

    rmb_code_tag = "USD/CNH" if usd_cnh is not None else "USD/CNY"
    verified_fx_chips = (
        f'<a class="mirror-chip mirror-chip-link" href="charts.html#sym=fx_USDCNH" '
        f'data-kline-jump="fx_USDCNH" data-kline-tab="gold_macro">'
        f'<div class="mirror-lbl">{esc(rmb_label)}</div>'
        f'<div class="mirror-val">{esc(rmb_value)}</div>'
        f'<div class="mirror-sub"><span class="code-tag">{rmb_code_tag}</span> · CFETS 中间价 {esc(cfets_value)} · 📈 K线</div>'
        "</a>"
        f'<a class="mirror-chip mirror-chip-link" href="charts.html#sym=fx_USDHKD" '
        f'data-kline-jump="fx_USDHKD" data-kline-tab="gold_macro">'
        f'<div class="mirror-lbl">美元 / 港元 <span class="code-tag">USD/HKD</span></div>'
        f'<div class="mirror-val">{esc(usd_hkd_value)}</div>'
        f'<div class="mirror-sub">联汇强弱边界 7.75–7.85 · 📈 K线</div>'
        "</a>"
    )

    def _mirror_name_lbl(row: dict[str, Any]) -> str:
        rid = str(row.get("id") or "")
        nm = str(row.get("name") or "")
        if rid in ("crypto_BTC", "crypto_ETH") and "禁交易" not in nm:
            nm = re.sub(r"[（(]只读[）)]", "", nm).strip() + "（只读·禁交易）"
        return nm

    mirror_rows = [r for r in multi_idx["macro"] if r.get("id") not in ("fx_USDCNH", "fx_USDHKD")]
    xag_row = next((r for r in (multi_idx.get("gold") or []) if r.get("id") == "cmd_XAG"), None)
    if xag_row is not None:
        mirror_rows.append(xag_row)
    macro_mirror_cards = verified_fx_chips + "".join(
        f'<a class="mirror-chip mirror-chip-link" href="charts.html#sym={esc(r["id"])}" '
        f'data-kline-jump="{esc(r["id"])}" data-kline-tab="gold_macro">'
        f'<div class="mirror-lbl">{esc(_mirror_name_lbl(r))} <span class="code-tag">{esc(r["code"])}</span></div>'
        f'<div class="mirror-val">{esc(r["value_disp"])}</div>'
        f'<div class="mirror-sub">{_macro_sub_html(r)}</div>'
        "</a>"
        for r in mirror_rows
    )

    # Build null-safe Core #4 (Rates/Bonds) and Satellite #6 (Non-US Global Equities) cards
    def _short_stance_lbl(raw_txt: Any, fallback: str) -> str:
        s = str(raw_txt or "").strip()
        if not s:
            return fallback
        head = re.split(r"[（(：:；;，,]", s, maxsplit=1)[0].strip()
        return head if head else fallback

    rb_core = eq_state.get("rates_bonds_core") if isinstance(eq_state.get("rates_bonds_core"), dict) else {}
    rb_cn = rb_core.get("cn_rates") if isinstance(rb_core.get("cn_rates"), dict) else {}
    rb_us = rb_core.get("us_rates") if isinstance(rb_core.get("us_rates"), dict) else {}
    rb_dur = rb_core.get("duration_stance") if isinstance(rb_core.get("duration_stance"), dict) else {}
    rb_fx = rb_core.get("unhedged_usd_fx_drag") if isinstance(rb_core.get("unhedged_usd_fx_drag"), dict) else {}

    rb_lamp_raw = str(rb_core.get("lamp") or "yellow").strip().lower()
    rb_lamp_cls = "lamp-green" if rb_lamp_raw == "green" else ("lamp-red" if rb_lamp_raw == "red" else "lamp-amber")
    rb_lamp_lbl = str(rb_core.get("lamp_label") or ("绿灯压舱期" if rb_lamp_cls == "lamp-green" else "黄灯控久期")).replace("⚖️", "").replace("🛡️", "").strip()
    rb_role_tag = str(rb_core.get("role_tag") or "防守压舱石 · 家庭真金白银底仓与全球定价总锚")
    rb_cgb10 = _safe_float(rb_cn.get("cgb10y_pct")) or _safe_float(rates.get("cgb10y_pct")) or _safe_float(a_m.get("cgb10y_pct"))
    rb_cgb30 = _safe_float(rb_cn.get("cgb30y_pct"))
    rb_gc001 = _safe_float(rb_cn.get("gc001_pct"))
    rb_dr001 = _safe_float(rb_cn.get("dr001_pct"))
    rb_us10 = _safe_float(rb_us.get("us10y_pct")) or _safe_float(rates.get("us10y_pct")) or _safe_float(us_m.get("us10y_pct"))
    rb_us2 = _safe_float(rb_us.get("us2y_pct")) or _safe_float(rates.get("us2y_pct")) or _safe_float(gold_snap.get("us2y_pct"))
    rb_us30 = _safe_float(rb_us.get("us30y_pct")) or _safe_float(rates.get("us30y_pct"))
    rb_dfii = _safe_float(rb_us.get("dfii10_pct")) or _safe_float(rb_us.get("tips_dfii10_pct")) or _safe_float(rates.get("dfii10_pct")) or _safe_float(gold_snap.get("dfii10_live_pct"))
    rb_spread = _safe_float(rb_core.get("cn_us_10y_spread_bp"))
    if rb_spread is None:
        rb_spread = _safe_float(rates.get("cn_us_10y_spread_bp"))
    if rb_spread is None and rb_cgb10 is not None and rb_us10 is not None:
        rb_spread = round((rb_cgb10 - rb_us10) * 100.0)
    rb_spread_disp = f"{int(round(rb_spread)):+d}bp" if rb_spread is not None else "待核"
    rb_cgb10_s = _fmt_num(rb_cgb10, ".3f", suffix="%")
    rb_cgb30_s = _fmt_num(rb_cgb30, ".3f", suffix="%")
    rb_us10_s = _fmt_num(rb_us10, ".2f", suffix="%")
    rb_us2_s = _fmt_num(rb_us2, ".2f", suffix="%")
    rb_us30_s = _fmt_num(rb_us30, ".2f", suffix="%")
    rb_dfii_s = _fmt_num(rb_dfii, ".2f", suffix="%")
    rb_gc_s = _fmt_num(rb_gc001, ".3f", suffix="%")
    rb_dr_s = _fmt_num(rb_dr001, ".3f", suffix="%")
    rb_fx_drag_range = str(rb_fx.get("real_rmb_drag_range") or rb_fx.get("ytd_rmb_drag_label") or "防赚息亏汇").strip()
    rb_fx_spot = _fmt_num(_safe_float(rb_fx.get("usd_cny_spot")) or _safe_float(rates.get("usd_cny_1630")) or _safe_float(rates.get("usd_cnh")), ".4f")
    rb_verdict = str(rb_core.get("headline") or rb_core.get("verdict_plain") or "中债短融/短债与美元短债双盾并举；严禁把30年超长债或破净理财当保本活钱，警惕未锁汇美元赚息亏汇。")
    rb_cn_dur = _short_stance_lbl(rb_dur.get("cn_short_cash") or rb_dur.get("cn_short_label"), "活钱/短债优先")
    rb_cn_long_dur = _short_stance_lbl(rb_dur.get("cn_intermediate_long") or rb_dur.get("cn_long_label"), "长债控久期")
    rb_us_dur = _short_stance_lbl(rb_dur.get("us_short_tbill") or rb_dur.get("us_short_label"), "0-1Y短美债甜区")
    rb_us_long_dur = _short_stance_lbl(rb_dur.get("us_long_treasury") or rb_dur.get("us_long_label"), "20Y+长美债审慎")

    nonus = eq_state.get("non_us_global_satellite") if isinstance(eq_state.get("non_us_global_satellite"), dict) else {}
    nonus_raw_mkts = nonus.get("markets") if isinstance(nonus.get("markets"), list) and nonus.get("markets") else None
    nonus_lamp_raw = str(nonus.get("lamp") or "").strip().lower()
    if not nonus_lamp_raw and nonus_raw_mkts:
        _nl = [str(m.get("lamp") or "").strip().lower() for m in nonus_raw_mkts if isinstance(m, dict)]
        nonus_lamp_raw = "green" if (_nl and all(x == "green" for x in _nl)) else ("red" if (_nl and all(x == "red" for x in _nl)) else "yellow")
    if not nonus_lamp_raw:
        nonus_lamp_raw = "amber"
    nonus_lamp_cls = "lamp-green" if nonus_lamp_raw == "green" else ("lamp-red" if nonus_lamp_raw == "red" else "lamp-amber")
    nonus_lamp_lbl = str(nonus.get("lamp_label") or "黄灯精选 · 严防溢价")
    nonus_role_tag = str(nonus.get("role_tag") or "真跨币种海外分散卫星 · 区别于与内地盈利同源的港股")
    nonus_verdict = str(
        nonus.get("allocation_guardrail")
        or nonus.get("headline")
        or nonus.get("qdii_warning_summary")
        or nonus.get("verdict_plain")
        or "非美海外仅作全球分散卫星仓；境内跨境工具买前必核盘中参考净值（IOPV），场内溢价超过 2% 严禁追高。"
    )
    nonus_markets = nonus_raw_mkts or [
        {"id": "jp", "flag": "🇯🇵", "name": "日本股市", "live_metric": "513800 平价微折", "kline_id": "idx_N225", "access_grade": "A 级 · 境内平价", "onshore_vehicles": [{"code": "513800", "name": "南方日本东证ETF", "note": "中日互通平价首选"}], "offshore_vehicles": [{"code": "VXUS"}]},
        {"id": "eu", "flag": "🇪🇺", "name": "欧洲股市", "live_metric": "159561 物理直投", "kline_id": "idx_GDAXI", "access_grade": "A- 级 · 境内直投低费", "onshore_vehicles": [{"code": "159561", "name": "嘉实德国DAX ETF", "note": "境内直投德国低费首选"}], "offshore_vehicles": [{"code": "VGK"}]},
        {"id": "tw_kr", "flag": "🌏", "name": "中国台湾与韩国股市", "live_metric": "离岸为主 · AI晴雨表", "kline_id": "idx_TWII", "access_grade": "B 级 · AI晴雨表", "onshore_vehicles": [{"code": "159687", "name": "南方亚太精选ETF", "note": "间接覆盖亚太龙头"}], "offshore_vehicles": [{"code": "IEMG"}]},
        {"id": "in", "flag": "🇮🇳", "name": "印度股市", "lamp": "red", "lamp_label": "红灯避雷", "live_metric": "场内严避退市风险", "kline_id": "idx_NSEI", "access_grade": "C 级 · 场内避退市雷", "onshore_vehicles": [{"code": "006105", "name": "宏利印度股票", "note": "场外按净值申购"}], "offshore_vehicles": [{"code": "IEMG"}]},
    ]
    _nonus_flag_map = {"jp": "🇯🇵", "eu": "🇪🇺", "tw_kr": "🌏", "in": "🇮🇳"}

    def _nonus_vehicle(m: dict[str, Any], side: str) -> dict[str, Any]:
        plural = f"{side}_vehicles"
        legacy = f"top_{side}_etf"
        vlist = m.get(plural)
        if isinstance(vlist, list) and vlist and isinstance(vlist[0], dict):
            return vlist[0]
        lv = m.get(legacy)
        return lv if isinstance(lv, dict) else {}

    def _nonus_live_metric(m: dict[str, Any]) -> str:
        lm = str(m.get("live_metric") or "").strip()
        if lm:
            return lm
        bms = m.get("benchmarks")
        if isinstance(bms, list) and bms and isinstance(bms[0], dict):
            b0 = bms[0]
            b_nm = str(b0.get("name") or b0.get("code") or "").strip()
            b_val = _safe_float(b0.get("value"))
            b_chg = _safe_float(b0.get("change_pct"))
            if b_val is not None:
                v_txt = f"{b_val:,.2f}"
                if b_chg is not None:
                    return f"{b_nm} {v_txt} ({b_chg:+.2f}%)" if b_nm else f"{v_txt} ({b_chg:+.2f}%)"
                return f"{b_nm} {v_txt}" if b_nm else v_txt
        return str(m.get("lamp_label") or "观察追踪").replace("⚖️", "").replace("🛡️", "").strip()

    nonus_tile_parts: list[str] = []
    for m in nonus_markets[:4]:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "").strip()
        m_flag = str(m.get("flag") or _nonus_flag_map.get(mid, "🌏"))
        m_name = str(m.get("name") or "")
        m_grade = str(m.get("access_grade") or "")
        m_metric = _nonus_live_metric(m)
        m_on_code = str(_nonus_vehicle(m, "onshore").get("code") or "—")
        m_off_code = str(_nonus_vehicle(m, "offshore").get("code") or "—")
        nonus_tile_parts.append(
            f'<button type="button" class="m-sub-tile" data-kline-jump="{esc(str(m.get("kline_id") or "idx_N225"))}" data-kline-tab="non_us_global" title="点击查看 {esc(m_name)} 交互 K 线">'
            f'<span class="m-sub-head"><span>{esc(m_flag)} {esc(m_name)}</span>'
            f'<span class="m-sub-grade">{esc(m_grade)}</span></span>'
            f'<span class="m-sub-val">{esc(m_metric)}</span>'
            f'<span class="m-sub-meta">境内 {esc(m_on_code)} · 离岸 {esc(m_off_code)}</span>'
            "</button>"
        )
    nonus_tiles_html = "".join(nonus_tile_parts)

    # Dynamically derive #card-nonus bottom 3 stat items directly from nonus_markets (zero hardcoded numbers)
    nonus_stat_items: list[tuple[str, str, str]] = []
    valid_nonus_mkts = [m for m in nonus_markets if isinstance(m, dict)]
    for m_idx, m in enumerate(valid_nonus_mkts[:2], start=1):
        on_v = _nonus_vehicle(m, "onshore")
        on_code = str(on_v.get("code") or "—")
        on_name_clean = re.sub(r"(?:指数)?\s*ETF\s*$", "", str(on_v.get("name") or m.get("name") or "")).strip()
        m_short = str(m.get("name") or f"区域{m_idx}")
        val_txt = f"{on_code} · {on_name_clean}" if (on_code != "—" and on_name_clean) else (on_code if on_code != "—" else m_short)
        sub_txt = str(on_v.get("note") or m.get("access_grade") or "境内低费渠道")
        nonus_stat_items.append((f"{m_short}首选", val_txt, sub_txt))
    red_nonus = [m for m in valid_nonus_mkts if str(m.get("lamp") or "").strip().lower() == "red"]
    warn_mkt = red_nonus[0] if red_nonus else (valid_nonus_mkts[2] if len(valid_nonus_mkts) > 2 else None)
    if warn_mkt:
        w_name = str(warn_mkt.get("name") or "卫星排雷")
        w_lamp = str(warn_mkt.get("lamp_label") or "谨慎排雷").replace("🛡️", "").replace("⚖️", "").strip()
        w_off = str(_nonus_vehicle(warn_mkt, "offshore").get("code") or "")
        w_sub = str(warn_mkt.get("access_grade") or (f"离岸分散 {w_off}" if w_off else "严避高溢价与退市雷"))
        nonus_stat_items.append(("高危排雷", f"{w_name} · {w_lamp}", w_sub))
    nonus_stats_html = "".join(
        f'<div class="m-stat">'
        f'<div class="m-stat-lbl">{esc(lbl)}</div>'
        f'<div class="m-stat-val">{esc(val)}</div>'
        f'<div class="m-stat-sub">{esc(sub)}</div>'
        "</div>"
        for lbl, val, sub in nonus_stat_items
    )

    jump_pills: list[str] = [
        '<a class="home-jump-pill" href="#sec-core-markets">六大市场</a>',
        '<a class="home-jump-pill" href="#sec-policy-calendar">🧭 时政深解与日历</a>',
        '<a class="home-jump-pill" href="#sec-kline-deck">交互K线</a>',
        '<a class="home-jump-pill" href="#sec-four-buckets">钱包试算</a>',
    ]
    if home_channels_section_html:
        jump_pills.append(f'<a class="home-jump-pill" href="#sec-multi-channels">{ch_count_num}大渠道</a>')
    jump_pills.append('<a class="home-jump-pill" href="#sec-latest-dailies">最新日报</a>')
    jump_bar_html = f'<nav class="home-jump-bar" aria-label="首页版块快捷导航">{"".join(jump_pills)}</nav>'
    policy_calendar_html = _render_policy_calendar_section(
        policy_calendar, eq_state, gold_blocked=(not gold_new_buy or gold_tier_code == "Tier 0")
    )

    n225_row = next((r for r in (multi_idx.get("non_us_global") or []) if r.get("id") == "idx_N225"), None)
    n225_val = _safe_float((n225_row or {}).get("value"))
    n225_chg = _safe_float((n225_row or {}).get("change_pct"))
    if n225_val is None and isinstance(kline_core, dict):
        n225_bars = ((kline_core.get("series") or {}).get("idx_N225") or {}).get("bars") or []
        if n225_bars and isinstance(n225_bars[-1], list) and len(n225_bars[-1]) >= 5:
            n225_val = _safe_float(n225_bars[-1][4])
            if len(n225_bars) >= 2 and isinstance(n225_bars[-2], list) and len(n225_bars[-2]) >= 5:
                prev_c = _safe_float(n225_bars[-2][4])
                if n225_val is not None and prev_c and prev_c > 0:
                    n225_chg = round(((n225_val / prev_c) - 1.0) * 100.0, 2)
    if n225_val is not None:
        nonus_hero_num = (
            f"{n225_val:,.2f} {_fmt_chg_span(n225_chg)}" if n225_chg is not None else f"{n225_val:,.2f}"
        )
    else:
        nonus_hero_num = "多极观察"
    jp_anchor_cd = str(_nonus_vehicle(valid_nonus_mkts[0], "onshore").get("code") or "513800") if valid_nonus_mkts else "513800"
    eu_anchor_cd = str(_nonus_vehicle(valid_nonus_mkts[1], "onshore").get("code") or "159561") if len(valid_nonus_mkts) > 1 else "159561"
    nonus_hero_sub = f"日本 #1 · {jp_anchor_cd} 平价首选 · 欧洲 #2 · {eu_anchor_cd} 直投锚"

    a_pill_cls = "lamp-defend" if a_lamp_cls == "lamp-red" else a_lamp_cls
    hk_pill_cls = "lamp-defend" if hk_lamp_cls == "lamp-red" else hk_lamp_cls
    us_pill_cls = "lamp-defend" if us_lamp_cls == "lamp-red" else us_lamp_cls

    coverage_parts = [f"{total_pool} 股"]
    if ch_count_num:
        coverage_parts.append(f"{ch_count_num} 渠道")
    if etf_count_num:
        coverage_parts.append(f"{etf_count_num} ETF")
    coverage_summary = " · ".join(coverage_parts)
    live_pill_short = _short_live_pill(alert_label, max_len=48)

    return f"""
    <section class="exec-masthead">
      <div class="exec-top">
        <span class="compact-alert-pill" title="{esc(alert_label)}"><span class="live-pulse"></span>{esc(live_pill_short)}</span>
        <span class="sec-sub">每日 07:30 · 11:30 · 18:00 CST · 更新 {esc(eq_as_of or gold_as_of or "待核")} · {esc(coverage_summary)}</span>
      </div>
      <div class="exec-main">
        <div class="exec-copy">
          <h1>全球大类资产投研驾驶舱</h1>
          <p class="exec-verdict">{esc(hero_verdict)}</p>
        </div>
        <div class="exec-actions">
          <a class="btn btn-qdii" href="channels/qdii_mrf.html#sec-qdii-compare">⚡ QDII 溢价与限购</a>
          <a class="btn btn-primary" href="#sec-four-buckets">试算我的配置 →</a>
        </div>
      </div>
    </section>

    {crisis_ribbon_html}
    {home_watchlist_html}
    {jump_bar_html}
    {disclosure_html}

    <div class="sec-head" id="sec-core-markets" style="margin-top:8px;">
      <h2>六大核心市场红绿灯驾驶舱（5 核心 × 1 非美卫星）</h2>
      <span class="sec-sub">第 1 行权益三市（A/港/美）· 第 2 行压舱/避险/非美（债率/黄金/日欧台韩印）· 点瓦片直看 K 线</span>
    </div>

    <section class="market-grid">
      <article class="m-card m-a" id="card-a-share">
        <div class="m-card-head">
          <div>
            <div class="m-card-name">🇨🇳 中国 A 股</div>
            <div class="m-card-sub">核心 #1 · 上证领衔 12 指数 · {a_pool} 股</div>
          </div>
          <span class="lamp-pill {a_pill_cls}"><span class="lamp-dot"></span>{esc(a_lamp_lbl)} · {esc(a_score)}</span>
        </div>
        <div class="stance-pill {_stance_badge_cls(a_lamp_cls)}">{esc(a_stance_txt)}</div>
        <div class="m-hero-row">
          <div class="m-hero-main">
            <div class="m-hero-lbl">上证指数（000001.SH · 大盘总舵）</div>
            <div class="m-hero-num">{a_sse_val}</div>
            <div class="m-hero-sub">沪深300 {a_csi300_val} · 200周线 {a_200w_val}</div>
          </div>
          {_render_score_meter(a_score_num, a_score)}
        </div>
        {a_matrix_html}
        <div class="m-stat-strip">
          <div class="m-stat">
            <div class="m-stat-lbl">股票仓位上限</div>
            <div class="m-stat-val">{a_eq_cap_val}</div>
            <div class="m-stat-sub">余下稳守国债 / 转债 / 现金</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">前瞻 / 静态 {_term_tip("erp", "ERP")}</div>
            <div class="m-stat-val">{a_erp_fwd_val} / {a_erp_ttm_val}</div>
            <div class="m-stat-sub">10 年国债 {a_cgb10y_val}</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">核心龙头诊断池</div>
            <div class="m-stat-val">{a_pool} 只龙头</div>
            <div class="m-stat-sub">{esc(a_pool_sub)}</div>
          </div>
        </div>
        <div class="m-verdict"><strong>防踏空升级线：</strong>{esc(a_m.get("fomo_threshold", ""))}</div>
        <div class="m-actions">
          <a class="btn btn-primary" href="daily/a-share-latest.html">读日报 →</a>
          <a class="btn" href="charts.html#sym=idx_sh000001">看K线</a>
          <a class="btn" href="screener.html#market=a-share">7维股池</a>
        </div>
      </article>

      <article class="m-card m-hk" id="card-hk-stock">
        <div class="m-card-head">
          <div>
            <div class="m-card-name">🇭🇰 中国香港股市</div>
            <div class="m-card-sub">核心 #2 · 中国离岸腿 · 联汇 · {hk_pool} 股</div>
          </div>
          <span class="lamp-pill {hk_pill_cls}"><span class="lamp-dot"></span>{esc(hk_lamp_lbl)} · {esc(hk_score)}</span>
        </div>
        <div class="stance-pill {_stance_badge_cls(hk_lamp_cls)}">{esc(hk_stance_txt)}</div>
        <div class="m-hero-row">
          <div class="m-hero-main">
            <div class="m-hero-lbl">恒生指数（HSI · 港股总舵）</div>
            <div class="m-hero-num">{hk_hsi_val}</div>
            <div class="m-hero-sub">恒科 {hk_hstech_val} · 200日线 {hk_200d_val}</div>
          </div>
          {_render_score_meter(hk_score_num, hk_score)}
        </div>
        {hk_matrix_html}
        <div class="m-stat-strip">
          <div class="m-stat">
            <div class="m-stat-lbl">离岸 / 港股通上限</div>
            <div class="m-stat-val">{hk_off_cap_val} / {hk_on_cap_val}</div>
            <div class="m-stat-sub">{_term_tip("ah_premium", "AH 溢价")}指数 {hk_hsahp_val}</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">{_term_tip("hibor", "HIBOR 1M")} / {_term_tip("hkma_bal", "总结余")}</div>
            <div class="m-stat-val">{hibor_value} / {hkma_short_val}</div>
            <div class="m-stat-sub">美元/港元 {usd_hkd_value}（紧盯 7.85）</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">美元 / 人民币锚 {_term_tip("erp", "ERP")}</div>
            <div class="m-stat-val">{hk_erp_usd_val} / {hk_erp_cny_val}</div>
            <div class="m-stat-sub">{hk_pool} 只龙头 · 南向年内 {hk_sb_ytd_val}</div>
          </div>
        </div>
        <div class="m-verdict"><strong>防踏空升级线：</strong>{esc(hk_m.get("fomo_threshold", ""))}</div>
        <div class="m-actions">
          <a class="btn btn-primary" href="daily/hk-stock-latest.html">读日报 →</a>
          <a class="btn" href="charts.html#sym=idx_hkHSI">看K线</a>
          <a class="btn" href="screener.html#market=hk-stock">7维股池</a>
        </div>
      </article>

      <article class="m-card m-us" id="card-us-stock">
        <div class="m-card-head">
          <div>
            <div class="m-card-name">🇺🇸 美国股市</div>
            <div class="m-card-sub">核心 #3 · 全球 64% 市值 · {us_pool} 股池</div>
          </div>
          <span class="lamp-pill {us_pill_cls}"><span class="lamp-dot"></span>{esc(us_lamp_lbl)} · {esc(us_score)}</span>
        </div>
        <div class="stance-pill {_stance_badge_cls(us_lamp_cls)}">{esc(us_stance_txt)}</div>
        <div class="m-hero-row">
          <div class="m-hero-main">
            <div class="m-hero-lbl">标普 500（SPX · 美股总舵）</div>
            <div class="m-hero-num">{us_sp_val}</div>
            <div class="m-hero-sub">10Y 美债官收 {us10y_val} · 200日线 {us_200d_val}</div>
          </div>
          {_render_score_meter(us_score_num, us_score)}
        </div>
        {us_matrix_html}
        <div class="m-stat-strip">
          <div class="m-stat">
            <div class="m-stat-lbl">100% 闭环资产配置</div>
            <div class="m-stat-val">{esc(us_alloc_str)}</div>
            <div class="m-stat-sub">科技新增严控 {us_tech_cap_val}</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">前瞻 / 静态 {_term_tip("erp", "ERP")}</div>
            <div class="m-stat-val">{us_erp_fwd_val} / {us_erp_ttm_val}</div>
            <div class="m-stat-sub">前瞻 PE {us_pe_fwd_val}（静态 {us_pe_ttm_val}）</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">核心龙头诊断池</div>
            <div class="m-stat-val">{us_pool} 只龙头</div>
            <div class="m-stat-sub">{esc(us_pool_sub)}</div>
          </div>
        </div>
        <div class="m-verdict"><strong>防踏空升级线：</strong>{esc(us_m.get("fomo_threshold", ""))}</div>
        <div class="m-actions">
          <a class="btn btn-primary" href="daily/us-stock-latest.html">读日报 →</a>
          <a class="btn btn-qdii" href="channels/qdii_mrf.html#sec-qdii-compare">QDII查溢价</a>
          <a class="btn" href="screener.html#market=us-stock">7维股池</a>
        </div>
      </article>

      <article class="m-card m-rates" id="card-rates">
        <div class="m-card-head">
          <div>
            <div class="m-card-name">🛡️ 债券、现金与中美利率</div>
            <div class="m-card-sub">核心 #4 · 家庭 75%–85% 金融压舱与全局定价锚</div>
          </div>
          <span class="lamp-pill {rb_lamp_cls}"><span class="lamp-dot"></span>{esc(rb_lamp_lbl)}</span>
        </div>
        <div class="stance-pill {_stance_badge_cls(rb_lamp_cls)}">{esc(rb_role_tag)}</div>
        <div class="m-hero-row">
          <div class="m-hero-main">
            <div class="m-hero-lbl">中美 10 年国债利差（中债 − 美债）</div>
            <div class="m-hero-num">{esc(rb_spread_disp)}</div>
            <div class="m-hero-sub">中债10Y {esc(rb_cgb10_s)} / 30Y {esc(rb_cgb30_s)} · 美债10Y官收 {esc(rb_us10_s)} / TIPS {esc(rb_dfii_s)}</div>
          </div>
        </div>
        <div class="m-sub-grid">
          <button type="button" class="m-sub-tile" data-kline-jump="rate_CN10Y" data-kline-tab="bonds_reits" title="点击查看中国 10Y 国债收益率 K 线">
            <span class="m-sub-head"><span>🇨🇳 中债 10Y / 30Y</span><span class="m-sub-grade">中债压舱</span></span>
            <span class="m-sub-val">{esc(rb_cgb10_s)} / {esc(rb_cgb30_s)}</span>
            <span class="m-sub-meta">511260 / 511090（防长债大回撤）</span>
          </button>
          <button type="button" class="m-sub-tile" data-kline-jump="etf_511360" data-kline-tab="bonds_reits" title="点击查看短融 ETF 511360 K 线">
            <span class="m-sub-head"><span>💧 活钱 GC001 / DR001</span><span class="m-sub-grade">活钱盾</span></span>
            <span class="m-sub-val">{esc(rb_gc_s)} / {esc(rb_dr_s)}</span>
            <span class="m-sub-meta">短融 511360 银行间免底层 20% 息税</span>
          </button>
          <button type="button" class="m-sub-tile" data-kline-jump="rate_US10Y" data-kline-tab="bonds_reits" title="点击查看美债 10Y 收益率 K 线">
            <span class="m-sub-head"><span>🇺🇸 美债 2Y / 10Y / 30Y</span><span class="m-sub-grade">官收基准</span></span>
            <span class="m-sub-val">2Y {esc(rb_us2_s)} · 10Y {esc(rb_us10_s)}</span>
            <span class="m-sub-meta">30Y {esc(rb_us30_s)} · 短盾 SGOV / IB01</span>
          </button>
          <button type="button" class="m-sub-tile" data-kline-jump="fx_USDCNH" data-kline-tab="gold_macro" title="点击查看离岸人民币 USD/CNH 汇率 K 线">
            <span class="m-sub-head"><span>💱 未锁汇美元汇损</span><span class="m-sub-grade">盯 {esc(rb_fx_spot)}</span></span>
            <span class="m-sub-val">{esc(rb_fx_drag_range)}</span>
            <span class="m-sub-meta">防赚息亏汇 · 换汇前先算汇损</span>
          </button>
        </div>
        <div class="m-stat-strip">
          <div class="m-stat">
            <div class="m-stat-lbl">中债久期灯</div>
            <div class="m-stat-val">{esc(rb_cn_dur)}</div>
            <div class="m-stat-sub">{esc(rb_cn_long_dur)}</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">美债久期灯</div>
            <div class="m-stat-val">{esc(rb_us_dur)}</div>
            <div class="m-stat-sub">{esc(rb_us_long_dur)}</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">核心压舱工具</div>
            <div class="m-stat-val">511360 / 511260</div>
            <div class="m-stat-sub">离岸 SGOV / IB01</div>
          </div>
        </div>
        <div class="m-verdict"><strong>压舱与防坑指南：</strong>{esc(rb_verdict)}</div>
        <div class="m-actions">
          <a class="btn btn-primary" href="channels/bonds.html">债券详规 →</a>
          <a class="btn" href="charts.html#sym=rate_CN10Y">看K线</a>
          <a class="btn" href="etfs.html#asset_class=fixed_income_plus">债现ETF</a>
        </div>
      </article>

      <article class="m-card m-gold" id="card-gold">
        <div class="m-card-head">
          <div>
            <div class="m-card-name">🥇 黄金（单一真相源）</div>
            <div class="m-card-sub">核心 #5 · 独立货币避险 · 四步{_term_tip("traffic_light", "红绿灯")}通过 {esc(gold_pass)}</div>
          </div>
          <span class="lamp-pill {gold_lamp_cls}"><span class="lamp-dot"></span>{esc(gold_tier_short)} · {esc(gold_pass)}</span>
        </div>
        <div class="stance-pill {_stance_badge_cls(gold_lamp_cls, is_gold_mkt=True)}">{esc(gold_stance_txt)}</div>
        <div class="m-hero-row">
          <div class="m-hero-main">
            <div class="m-hero-lbl">纽约现货金（纽约官收 · 美元/盎司）</div>
            <div class="m-hero-num">{gold_spot_val}</div>
            <div class="m-hero-sub">{esc(gold_asia_sub)}</div>
          </div>
          {gold_gate_strip_html}
        </div>
        {gold_matrix_html}
        <div class="m-stat-strip">
          <div class="m-stat">
            <div class="m-stat-lbl">{esc(sge_main_lbl)}</div>
            <div class="m-stat-val">{esc(sge_main_val)}</div>
            <div class="m-stat-sub">{esc(sge_sub_txt)}</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">10 年美债真实利率 {_term_tip("dfii10", "DFII10")}</div>
            <div class="m-stat-val">{esc(gold_dfii_val)}</div>
            <div class="m-stat-sub">{esc(dfii_sub)}</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">新仓规则 / 家庭上限</div>
            <div class="m-stat-val">{esc(gold_new_buy_val)}</div>
            <div class="m-stat-sub">{esc(gold_new_buy_sub)}</div>
          </div>
        </div>
        <div class="m-verdict"><strong>核心指令：</strong>{esc(gold_verdict)}</div>
        <div class="m-actions">
          <a class="btn btn-primary" href="daily/gold-latest.html">读日报 →</a>
          <a class="btn" href="charts.html#sym=cmd_XAU">看K线</a>
          <a class="btn" href="reports/gold.html">主报告</a>
        </div>
      </article>

      <article class="m-card m-nonus" id="card-nonus">
        <div class="m-card-head">
          <div>
            <div class="m-card-name">🌏 非美发达与亚太权益</div>
            <div class="m-card-sub">统一卫星 · 日/欧平价低费分散 · 台韩AI晴雨表 · 印度防退市</div>
          </div>
          <span class="lamp-pill {nonus_lamp_cls}"><span class="lamp-dot"></span>{esc(nonus_lamp_lbl)}</span>
        </div>
        <div class="stance-pill {_stance_badge_cls(nonus_lamp_cls)}">{esc(nonus_role_tag)}</div>
        <div class="m-hero-row">
          <div class="m-hero-main">
            <div class="m-hero-lbl">日经 225（N225 · 非美领衔基准）</div>
            <div class="m-hero-num">{nonus_hero_num}</div>
            <div class="m-hero-sub">{esc(nonus_hero_sub)}</div>
          </div>
        </div>
        <div class="m-sub-grid">{nonus_tiles_html}</div>
        <div class="m-stat-strip">{nonus_stats_html}</div>
        <div class="m-verdict"><strong>QDII / LOF 排雷：</strong>{esc(nonus_verdict)}</div>
        <div class="m-actions">
          <a class="btn btn-qdii" href="channels/qdii_mrf.html#sec-qdii-compare">QDII查溢价 →</a>
          <a class="btn" href="charts.html#sym=idx_N225">看K线</a>
          <a class="btn" href="etfs.html#asset_class=equity&amp;region=non_us">非美ETF</a>
        </div>
      </article>
    </section>

    {policy_calendar_html}
    {action_lights_html}
    {home_kline_deck_html}
    {four_buckets_html}
    {home_channels_section_html}
    {home_etf_section_html}

    <div class="sec-head" id="sec-risk-radar">
      <h2>跨市场风险雷达与家庭总账</h2>
      <span class="sec-sub">3+1 危机总熔断阀 · 三市股债性价比 · 大宗外汇镜像 · 家庭资产闭环</span>
    </div>

    <section class="radar-grid">
      <div class="panel-card span-2">
        <div class="panel-title">
          <span>🛡️ 3+1 全球危机相关性总熔断阀（任一触发即全市场降险）</span>
          {brake_overall}
        </div>
        <div class="breaker-grid">
          <div class="breaker-item">
            <div class="breaker-top">
              <span class="breaker-name">{_term_tip("vix", "VIX 恐慌指数")}</span>
              <span class="status-chip {vix_chip[0]}">{vix_chip[1]}</span>
            </div>
            <div class="breaker-val">{vix_close_val}</div>
            <div class="breaker-meter"><div class="breaker-meter-fill {_breaker_fill_cls(vix_chip[0])}" style="width:{vix_meter_pct:.0f}%;"></div></div>
            <div class="breaker-thr">{vix_high_label} ｜ 熔断线：连2日 &gt; {vix_thr:.0f}</div>
          </div>
          <div class="breaker-item">
            <div class="breaker-top">
              <span class="breaker-name">美元 / 日元 USD/JPY</span>
              <span class="status-chip {jpy_chip[0]}">{jpy_chip[1]}</span>
            </div>
            <div class="breaker-val">{usdjpy_val}</div>
            <div class="breaker-meter"><div class="breaker-meter-fill {_breaker_fill_cls(jpy_chip[0])}" style="width:{jpy_meter_pct:.0f}%;"></div></div>
            <div class="breaker-thr">熔断线：3 日急跌 &gt; {jpy_drop_thr:g}%（日元急升防平仓）</div>
          </div>
          <div class="breaker-item">
            <div class="breaker-top">
              <span class="breaker-name">{_term_tip("us10y", "10 年期美债 US10Y")}</span>
              <span class="status-chip {us10y_chip[0]}">{us10y_chip[1]}</span>
            </div>
            <div class="breaker-val">{us10y_val}</div>
            <div class="breaker-meter"><div class="breaker-meter-fill {_breaker_fill_cls(us10y_chip[0])}" style="width:{us10y_meter_pct:.0f}%;"></div></div>
            <div class="breaker-thr">{esc(us10y_thr_line)}</div>
          </div>
          <div class="breaker-item">
            <div class="breaker-top">
              <span class="breaker-name">{_term_tip("hkma_bal", "香港金管局总结余")}</span>
              <span class="status-chip {hkma_chip[0]}">{hkma_chip[1]}</span>
            </div>
            <div class="breaker-val">{hkma_full_val}</div>
            <div class="breaker-meter"><div class="breaker-meter-fill {_breaker_fill_cls(hkma_chip[0])}" style="width:{hkma_meter_pct:.0f}%;"></div></div>
            <div class="breaker-thr">熔断线：跌破 {hkma_thr:.0f} 亿港元</div>
          </div>
        </div>
      </div>

      <div class="panel-card">
        <div class="panel-title">
          <span>⚖️ 三市股权风险溢价（{_term_tip("erp", "ERP")}）横向标尺</span>
          <span class="sec-sub">数值越高越划算</span>
        </div>
        <div class="erp-list">
          {erp_bars_html}
        </div>
        <div class="erp-scale-marks"><span>0%</span><span>5%</span><span>10%</span></div>
      </div>

      <div class="panel-card">
        <div class="panel-title">
          <span>🏠 家庭跨市场综合资产配置闭环</span>
          <span class="sec-sub">{hcw_sum_disp}</span>
        </div>
        <div class="alloc-bar" role="img" aria-label="家庭综合配置比例条">
          {alloc_segs_html}
        </div>
        <div class="alloc-legend">
          <span class="alloc-leg-item"><span class="alloc-swatch" style="background:#1d4ed8;"></span>股票底座 {eq_pct}%</span>
          <span class="alloc-leg-item"><span class="alloc-swatch" style="background:#0f766e;"></span>可转债 {cb_pct}%</span>
          <span class="alloc-leg-item"><span class="alloc-swatch" style="background:#475569;"></span>国债/短债现金 {bc_pct}%</span>
          <span class="alloc-leg-item"><span class="alloc-swatch" style="background:#b45309;"></span>存量黄金 {gd_pct}%{esc(gold_alloc_suffix)}</span>
        </div>
        <div class="alloc-note">{esc(hcw_note)}</div>
        {alloc_breakdown_html}
      </div>

      <div class="panel-card span-2">
        <div class="panel-title">
          <span>🌐 全球大宗商品与核心汇率镜像（点击卡片直看 K 线）</span>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <a href="charts.html" class="btn btn-sm">全市场 K 线终端 →</a>
            <a href="screener.html" class="btn btn-sm">打开 {total_pool} 股交互筛选器 →</a>
          </div>
        </div>
        <div class="chip-grid">
          {macro_mirror_cards}
        </div>
      </div>
      {ah_panel_html}
    </section>

    <div class="sec-head" id="sec-latest-dailies">
      <h2>四刊最新日报速递（黄金 × A/港/美 · 含债率与非美雷达）</h2>
      <a href="archive.html" class="btn btn-sm">查看全部历史档案 →</a>
    </div>

    <section class="feed-grid">
      {feed_cards_html}
    </section>

    <div class="sec-head" id="sec-flagships">
      <h2>四大常青旗舰全景手册（在线网页直读）</h2>
      <a href="archive.html" class="btn btn-sm">全部档案与书架 →</a>
    </div>

    <section class="home-flagship-grid">
      {flagship_shelf_html}
    </section>
    """


def build_doc_toolbar(
    *,
    market: str,
    doc_kind: str,
    read_minutes: int,
    chart_count: int,
    has_toc: bool,
    total_pool: int = 0,
    channel_count: int = 0,
    stock_counts: dict[str, int] | None = None,
    item: DailyItem | None = None,
    prev_item: DailyItem | None = None,
    next_item: DailyItem | None = None,
    is_latest: bool = False,
) -> str:
    """Build contextual editorial document toolbar (breadcrumb + metadata pills + pure-web actions)."""
    mm = MARKET_META[market]
    sc = stock_counts or {}
    ch_btn_lbl = f"{channel_count}大多元渠道" if channel_count > 0 else "多元渠道"

    if doc_kind == "flagship":
        crumb_tail = mm["manual_label"]
        meta_pills = [
            '<span class="meta-pill">常青旗舰</span>',
            f'<span class="meta-pill">{chart_count} 张矢量图</span>' if chart_count else "",
            f'<span class="meta-pill">约 {read_minutes} 分钟阅读</span>',
        ]
        right_btns = [
            f'<a class="btn btn-sm" href="../daily/{market}-latest.html">最新日报</a>',
            f'<a class="btn btn-sm" href="../screener.html">{total_pool}股池</a>' if total_pool > 0 else "",
            f'<a class="btn btn-sm" href="../channels.html">{esc(ch_btn_lbl)}</a>',
            '<a class="btn btn-sm" href="../etfs.html">ETF雷达</a>',
        ]
    else:
        assert item is not None
        crumb_tail = f"{item.date_str} {item.session_label}"
        ed_lbl = {"main": "深度主刊", "midday": "午间实战", "light": "轻刊", "holiday_watch": "守望刊"}.get(item.edition_type, "深度主刊")
        meta_pills = [
            f'<span class="meta-pill">{ed_lbl}</span>',
            f'<span class="meta-pill">{chart_count} 张矢量图</span>' if chart_count else "",
            f'<span class="meta-pill">约 {read_minutes} 分钟阅读</span>',
        ]
        manual_lbl = (
            mm["manual_label"]
            if market == "gold"
            else f'{mm["manual_label"]} ({sc.get(market, 0)}股)'
        )
        right_btns = []
        if prev_item:
            right_btns.append(
                f'<a class="btn btn-sm" href="{prev_item.slug}.html" title="{esc(prev_item.title)}">← 上一期</a>'
            )
        if next_item:
            right_btns.append(
                f'<a class="btn btn-sm" href="{next_item.slug}.html" title="{esc(next_item.title)}">下一期 →</a>'
            )
        right_btns.append(f'<a class="btn btn-sm" href="../{mm["report_href"]}">{manual_lbl}</a>')
        right_btns.append(f'<a class="btn btn-sm" href="../archive.html#{market}">往期档案</a>')

    if has_toc:
        right_btns.append('<button type="button" class="btn btn-sm toolbar-toc-btn" data-action="open-toc">目录</button>')

    return (
        '<div class="doc-toolbar no-print">'
        '<div class="doc-toolbar-left">'
        '<nav class="breadcrumb" aria-label="面包屑">'
        '<a href="../index.html">总览</a>'
        '<span class="bc-sep" aria-hidden="true">/</span>'
        f'<a href="../archive.html#{market}">{esc(mm["short"])}</a>'
        '<span class="bc-sep" aria-hidden="true">/</span>'
        f'<span>{esc(crumb_tail)}</span>'
        "</nav>"
        f'<div class="doc-meta-pills">{"".join(p for p in meta_pills if p)}</div>'
        "</div>"
        f'<div class="doc-toolbar-right">{"".join(b for b in right_btns if b)}</div>'
        "</div>"
    )


_COLOR_MARKS: dict[str, str] = {"g": "●", "b": "◆", "y": "▲", "r": "×"}


def _render_static_screener_row(stock: dict[str, Any]) -> str:
    """Render static initial screener row matching app.js renderScreener() identically (zero CLS)."""
    col = str(stock["color"])
    mark = _COLOR_MARKS.get(col, "●")
    div_pct = stock.get("div_pct")
    ah_pct = stock.get("ah_pct")
    gap = stock.get("anchor_gap_pct")

    raw_val = str(stock.get("valuation") or "").strip()
    val_parts = [p.strip() for p in re.split(r"\s*[·｜|;；]\s*", raw_val) if p.strip()][:4] if raw_val else []
    val_chips_html = (
        '<div class="val-chips">'
        + "".join(f'<span class="val-chip">{esc(p)}</span>' for p in val_parts)
        + "</div>"
        if val_parts
        else ""
    )

    div_ah_chips: list[str] = []
    if isinstance(div_pct, (int, float)):
        div_ah_chips.append(f'<span class="val-chip">股息 {div_pct:.1f}%</span>')
    if isinstance(ah_pct, (int, float)):
        ah_cls = "ah-pill ah-disc" if ah_pct < 0 else "ah-pill ah-prem"
        div_ah_chips.append(f'<span class="{ah_cls}">AH {ah_pct:+.1f}%</span>')
    div_ah_html = (
        f'<div class="val-chips">{"".join(div_ah_chips)}</div>'
        if div_ah_chips
        else '<span class="sec-sub">—</span>'
    )

    anchor_html = ""
    if isinstance(gap, (int, float)):
        if gap <= 0:
            a_lbl = f"低于锚 {abs(gap):.1f}%" if gap < -0.5 else "已触安全锚"
            anchor_html = f'<span class="anchor-badge anchor-in">{esc(a_lbl)}</span>'
        elif gap <= 12.0:
            anchor_html = f'<span class="anchor-badge anchor-near">距锚 +{gap:.1f}%</span>'
        else:
            anchor_html = f'<span class="anchor-badge anchor-far">距锚 +{gap:.1f}%</span>'

    d_key = f'{stock["market"]}:{stock["code"]}'
    k_sym = f'stk_{stock["code"]}'
    star_btn = (
        f'<button type="button" class="star-btn" data-watch-toggle="1" data-watch-kind="stock" '
        f'data-watch-id="{esc(d_key)}" data-watch-kline="{esc(k_sym)}" '
        f'data-watch-code="{esc(stock["code"])}" data-watch-name="{esc(stock["name"])}" aria-label="切换自选">☆</button>'
    )
    d_btn = (
        f' <button type="button" class="dossier-btn" data-dossier-key="{esc(d_key)}">7维深研</button>'
        f' <button type="button" class="kline-quick-btn" data-dossier-key="{esc(d_key)}" data-open-tab="kline">📈 K线</button>'
        if stock.get("dossier")
        else ""
    )
    quote_meta = " · ".join(v for v in (stock.get("price_updated_at"), stock.get("price_source")) if v)
    quote_html = f'<div class="sec-sub">{esc(quote_meta)}</div>' if quote_meta else ""
    return (
        f'<tr class="row-{esc(col)}" data-market="{esc(stock["market"])}">'
        f'<td class="col-sticky"><span class="mkt-badge mkt-{esc(stock["market"])}">{esc(stock["market_label"])}</span></td>'
        f'<td>{star_btn} <strong>{esc(stock["name"])}</strong> <span class="code-tag">{esc(stock["code"])}</span></td>'
        f'<td class="nw">{esc(stock["sector"])}</td>'
        f'<td><div><strong>{esc(stock["price"])}</strong></div>{quote_html}{val_chips_html}</td>'
        f"<td>{div_ah_html}</td>"
        f'<td><span class="act-pill act-{esc(col)}">{mark} {esc(stock["action_label"])}</span></td>'
        f'<td>{anchor_html}{esc(stock["summary"])}{d_btn} <a href="{esc(stock["report_url"])}" class="nw">手册 →</a></td>'
        f"</tr>"
    )


_DOSSIER_NEGATED_BASE_RE = re.compile(
    r"(?:严禁|禁止|不可|不得|切勿|勿|不能|绝不|非|不再).{0,8}当下底座"
)
_DOSSIER_NEGATED_RED_RE = re.compile(
    r"(?:并非|不是|脱离|解除|不再).{0,6}(?:高危回避|坚决回避)"
)


def _extract_iso_date(raw: Any) -> str:
    """Extract YYYY-MM-DD date string from ISO or Chinese date stamps."""
    s = str(raw or "").strip()
    if not s:
        return ""
    m_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)}"
    m_cn = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", s)
    if m_cn:
        return f"{m_cn.group(1)}-{int(m_cn.group(2)):02d}-{int(m_cn.group(3)):02d}"
    return ""


def _extract_dossier_badge(
    action_etf: str,
    *,
    is_gold_locked: bool,
    gold_tier0_locked: bool,
) -> tuple[str, str] | None:
    """Parse explicit action badge from leading dossier action_etf prose, respecting negation & Gold Tier-0 lock."""
    head = str(action_etf or "").strip()[:60]
    if not head:
        return None
    if ("🔴" in head) or (
        re.search(r"高危回避|坚决回避", head) and not _DOSSIER_NEGATED_RED_RE.search(head)
    ):
        return ("r", COLOR_LABELS["r"])
    if ("🟡" in head) or ("分歧观察" in head):
        return ("y", COLOR_LABELS["y"])
    if ("🔵" in head) or ("未来主攻" in head):
        return ("b", COLOR_LABELS["b"])
    if ("🟢" in head) or (
        ("当下底座" in head) and not _DOSSIER_NEGATED_BASE_RE.search(head)
    ):
        if is_gold_locked and gold_tier0_locked:
            return None
        return ("g", COLOR_LABELS["g"])
    return None


_EXCLUDED_PCT_CONTEXT_RE = re.compile(
    r"ADR|隔夜|布油|两日累跌|累计|溢价|折价|倒挂|股息|息率|沽空|浮亏|回撤|占比|仓位|每手",
    re.IGNORECASE,
)
_URGENT_DOSSIER_WARN_RE = re.compile(
    r"折价配售|暂勿立即加仓|切勿.{0,12}追买|严禁追高"
)


def _extract_fresh_price_from_baseline(baseline_note: str, market: str) -> str | None:
    """Extract a concise latest quote snippet (<= 42 chars) from dossier baseline_note with strict currency lock."""
    raw = clean_md_inline_plain(baseline_note or "")
    if not raw:
        return None
    body = re.sub(
        r"^(?:基线参考价|基线价格与一手|基线价格|最新参考价|参考价)[：:\s]*",
        "",
        raw,
    ).strip()
    clause = re.split(r"[；;。]", body, maxsplit=1)[0].strip()
    if not clause:
        return None

    # For dual-listed baseline notes like "11/26 A股官收 23.30 元（+3.10%）/ H股 01787.HK 收 15.54 港元"
    if market == "a-share" and re.search(r"/\s*H\s*股", clause, re.IGNORECASE):
        clause = re.split(r"/\s*H\s*股", clause, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    elif market == "hk-stock" and re.search(r"/\s*H\s*股", clause, re.IGNORECASE):
        clause = re.split(r"/\s*H\s*股", clause, maxsplit=1, flags=re.IGNORECASE)[1].strip()
    elif market == "hk-stock" and re.search(r"/\s*A\s*股", clause, re.IGNORECASE):
        clause = re.split(r"/\s*A\s*股", clause, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    # Split on progression arrows ("→", "->") FIRST, then dual-date slashes ("/ 11/25 ..."), keeping rightmost segment
    arrow_parts = [p.strip() for p in re.split(r"\s*(?:→|->)\s*", clause) if p.strip()]
    if len(arrow_parts) > 1:
        clause = arrow_parts[-1]
    slash_parts = [p.strip() for p in re.split(r"\s*/\s*(?=\d{1,2}/\d{1,2})", clause) if p.strip()]
    if len(slash_parts) > 1:
        clause = slash_parts[-1]

    m_date = re.search(r"(?<![0-9])(\d{1,2}/\d{1,2})(?![0-9])", clause)
    dt_tok = m_date.group(1) if m_date else ""

    price_tok = ""
    price_start = 0
    price_end = 0

    if market == "us-stock":
        m_usd = re.search(r"(?<!HK)\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)", clause, re.IGNORECASE)
        m_usd_cn = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*美元", clause)
        if m_usd:
            price_tok = f"${m_usd.group(1)}"
            price_start, price_end = m_usd.start(), m_usd.end()
        elif m_usd_cn:
            price_tok = f"${m_usd_cn.group(1)}"
            price_start, price_end = m_usd_cn.start(), m_usd_cn.end()
    elif market == "hk-stock":
        m_hk_sym = re.search(r"HK\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)", clause, re.IGNORECASE)
        m_hk_cn = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*港元", clause)
        if m_hk_cn:
            price_tok = f"{m_hk_cn.group(1)} 港元"
            price_start, price_end = m_hk_cn.start(), m_hk_cn.end()
        elif m_hk_sym:
            price_tok = f"{m_hk_sym.group(1)} 港元"
            price_start, price_end = m_hk_sym.start(), m_hk_sym.end()
        else:
            m_hk_bare = re.search(
                r"(?:官收|官方终盘|终盘|校准为|铁锁|收盘|午逼空|午飙至|午收|午盘|午|(?<![0-9A-Za-z])收)\s*(?:约|~|≈|至)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)(?![0-9.,]|\s*(?:%|美元|(?<!港)元|万|亿|手|股|倍|x))",
                clause,
            )
            if m_hk_bare:
                pre_ctx = clause[max(0, m_hk_bare.start() - 12) : m_hk_bare.start(1)]
                if not re.search(r"[$＄¥￥]|ADR|布油|美股|A\s*股", pre_ctx, re.IGNORECASE):
                    price_tok = f"{m_hk_bare.group(1)} 港元"
                    price_start, price_end = m_hk_bare.start(1), m_hk_bare.end(1)
    elif market == "a-share":
        m_rmb_sym = re.search(r"[¥￥]\s*([0-9][0-9,]*(?:\.[0-9]+)?)", clause)
        m_rmb_cn = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?<!港)(?<!美)元", clause)
        if m_rmb_cn:
            price_tok = f"{m_rmb_cn.group(1)} 元"
            price_start, price_end = m_rmb_cn.start(), m_rmb_cn.end()
        elif m_rmb_sym:
            price_tok = f"{m_rmb_sym.group(1)} 元"
            price_start, price_end = m_rmb_sym.start(), m_rmb_sym.end()
        else:
            m_a_bare = re.search(
                r"(?:官收|官方终盘|终盘|校准为|铁锁|收盘|(?<![0-9A-Za-z])收)\s*(?:约|~|≈|至)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)(?![0-9.,]|\s*(?:%|港元|美元|万|亿|手|股|倍|x))",
                clause,
            )
            if m_a_bare:
                pre_ctx = clause[max(0, m_a_bare.start() - 12) : m_a_bare.start(1)]
                if not re.search(r"[$＄]|HK\$|ADR|布油|H\s*股", pre_ctx, re.IGNORECASE):
                    price_tok = f"{m_a_bare.group(1)} 元"
                    price_start, price_end = m_a_bare.start(1), m_a_bare.end(1)

    if not price_tok:
        return None

    has_close = bool(
        re.search(
            r"官收|官方终盘|终盘|铁锁|收盘|(?<![0-9A-Za-z])收\s*[\$¥￥0-9约~≈]",
            clause[:price_end],
        )
    )

    # Extract optional daily % change right after the price (never pick ADR/隔夜/布油/累计/溢价/折价/沽空/股息 %)
    chg_tok = ""
    tail = clause[price_end : price_end + 48]
    m_paren = re.match(r"\s*[（(]([^）)]+)[）)]", tail)
    if m_paren:
        inner = m_paren.group(1)
        first_part = re.split(r"[，,；;]", inner, maxsplit=1)[0]
        if not _EXCLUDED_PCT_CONTEXT_RE.search(first_part):
            m_chg = re.search(r"([+\-−][0-9]+(?:\.[0-9]+)?%)", first_part)
            if m_chg:
                chg_tok = m_chg.group(1).replace("−", "-")
    if not chg_tok and price_start > 0:
        # Handle pattern like "11/25 更新 -1.92%（~$294.51）" or "11/25 官收大跌 -3.05%（约 11.13 港元）"
        pre_seg = clause[:price_start]
        m_pre_chg = re.search(r"([+\-−][0-9]+(?:\.[0-9]+)?%)\s*[（(][^）)]*$", pre_seg)
        if m_pre_chg:
            pre_ctx = pre_seg[max(0, m_pre_chg.start() - 12) : m_pre_chg.end()]
            if not _EXCLUDED_PCT_CONTEXT_RE.search(pre_ctx):
                chg_tok = m_pre_chg.group(1).replace("−", "-")

    parts: list[str] = []
    if dt_tok:
        parts.append(f"{dt_tok} 官收" if has_close else dt_tok)
    parts.append(price_tok)
    out = " ".join(parts)
    if chg_tok:
        out = f"{out} ({chg_tok})"
    out = re.sub(r"\s+", " ", out).strip()
    return out if len(out) <= 42 else out[:42].rstrip()


def _truncate_clean_summary(text: str, max_len: int = 78) -> str:
    cleaned = clean_md_inline_plain(text or "")
    cleaned = _LEADING_RATING_PREFIX_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"^[（(]([^）)]{1,24})[）)]\s*[：:]\s*", r"\1：", cleaned).strip()
    if len(cleaned) <= max_len:
        return cleaned
    cut = cleaned[: max_len - 1]
    for sep in ("。", "；", ";", "，", ","):
        pos = cut.rfind(sep)
        if pos >= max_len // 2:
            return cut[: pos + 1].rstrip("，,；;")
    return cut.rstrip(" ·，,；;：:-—") + "…"


def _dossier_quote_day(price: str, record_day: str) -> str:
    """Resolve the quote's own month and day relative to the dossier edit date."""
    match = re.match(r"^(\d{1,2})/(\d{1,2})\b", price)
    if not match or not _valid_iso_date(record_day):
        return ""
    reference = date.fromisoformat(record_day)
    month, day = map(int, match.groups())
    year = reference.year
    # A New Year dossier may still quote the last trading day of December.
    if reference.month == 1 and month == 12:
        year -= 1
    try:
        observed = date(year, month, day)
    except ValueError:
        return ""
    return observed.isoformat() if observed <= reference else ""


def _overlay_fresher_dossier_on_stock(
    stock: dict[str, Any],
    dossier: dict[str, Any],
    flagship_date_str: str,
    gold_tier0_locked: bool,
    *,
    ah_lookup: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Synchronize screener stock card badge, price, PE/Div/AH, anchors & summary with fresher deep_dossiers.json data."""
    if not isinstance(stock, dict) or not isinstance(dossier, dict):
        return stock

    market = str(stock.get("market") or "").strip()
    code_raw = str(stock.get("code") or "").strip()
    code_key = code_raw.upper()
    is_gold_locked = bool(
        stock.get("is_gold_locked")
        or stock.get("gold_locked")
        or code_key in _GOLD_LOCKED_CODES
    )
    if is_gold_locked:
        stock["is_gold_locked"] = True

    updated_at = _extract_iso_date(dossier.get("updated_at") or "")
    flagship_dt = _extract_iso_date(flagship_date_str)
    action_etf = str(dossier.get("action_etf") or "").strip()
    baseline_note = str(dossier.get("baseline_note") or "").strip()
    is_strictly_fresher = bool(updated_at and (not flagship_dt or updated_at > flagship_dt))

    # 1. Action Badge Sync
    badge = _extract_dossier_badge(
        action_etf,
        is_gold_locked=is_gold_locked,
        gold_tier0_locked=gold_tier0_locked,
    )
    old_color = str(stock.get("color") or "").strip()
    badge_changed = False
    if badge is not None:
        new_color, new_label = badge
        is_explicit_red = new_color == "r"
        is_fresh_or_equal = bool(updated_at and (not flagship_dt or updated_at >= flagship_dt))
        if is_explicit_red or is_fresh_or_equal:
            if not (is_gold_locked and gold_tier0_locked and new_color == "g"):
                if new_color != old_color:
                    badge_changed = True
                stock["color"] = new_color
                stock["action_label"] = new_label

    # Enforce Gold Tier-0 lock strictly: never allow gold_locked stock to be green base
    if is_gold_locked and gold_tier0_locked and stock.get("color") == "g":
        stock["color"] = "y"
        stock["action_label"] = COLOR_LABELS["y"]

    # 2. Live AH% Sync (ah_lookup always takes precedence; else fresher baseline_note)
    ah_map = ah_lookup or {}
    live_ah: float | None = None
    if code_raw in ah_map:
        live_ah = round(ah_map[code_raw], 1)
    elif code_key in ah_map:
        live_ah = round(ah_map[code_key], 1)
    elif is_strictly_fresher and baseline_note:
        live_ah = _parse_ah_pct(baseline_note, "", market, "", {})
    if live_ah is not None:
        stock["ah_pct"] = live_ah
        if stock.get("valuation"):
            stock["valuation"] = _sync_valuation_str(
                str(stock.get("valuation") or ""),
                market,
                ah_pct=live_ah,
            )

    # 3. Fresh Price, PE/PB/Div & Summary Overlay (strictly fresher than flagship date)
    prev_summary = str(stock.get("summary") or "")
    if is_strictly_fresher:
        fresh_price = _extract_fresh_price_from_baseline(baseline_note, market)
        old_price_num = stock.get("price_num")
        if old_price_num is None and stock.get("price"):
            old_price_num = _parse_price_num(str(stock.get("price") or ""))
        if fresh_price:
            new_price_num = _parse_price_num(fresh_price)
            quote_day = _dossier_quote_day(fresh_price, updated_at)
            # Update quote when fresher dossier carries a newer price or explicit dated close
            has_date_tag = bool(re.match(r"^\d{1,2}/\d{1,2}\b", fresh_price))
            price_changed = (
                new_price_num is not None
                and (old_price_num is None or abs(new_price_num - old_price_num) > 1e-6)
            )
            if quote_day and quote_day >= flagship_dt and (price_changed or has_date_tag):
                stock["price"] = fresh_price
                stock["price_updated_at"] = quote_day
                if new_price_num is not None:
                    stock["price_num"] = new_price_num

        # Refresh PE, PB, and Dividend Yield from fresher baseline_note (incl. US dividend yield when div_pct is None)
        fresh_pe: float | None = None
        fresh_pb: float | None = None
        fresh_div: float | None = None
        if baseline_note:
            pe_candidate = _parse_pe_num(baseline_note, "")
            if pe_candidate is not None and re.search(r"(?:PE|市盈率)", baseline_note, re.IGNORECASE):
                fresh_pe = pe_candidate
                stock["pe_num"] = fresh_pe
            m_pb = re.search(r"(?<![A-Za-z])PB\s*[:：]?\s*[~≈约]?\s*([0-9]+(?:\.[0-9]+)?)x?", baseline_note, re.IGNORECASE)
            if m_pb:
                pb_v = _to_pos_float(m_pb.group(1))
                if pb_v is not None and pb_v < 200:
                    fresh_pb = round(pb_v, 2)
            div_candidate = _parse_div_pct(baseline_note, "", "")
            if div_candidate is not None:
                fresh_div = div_candidate
                stock["div_pct"] = fresh_div
            if (fresh_pe is not None or fresh_pb is not None or fresh_div is not None) and stock.get("valuation"):
                stock["valuation"] = _sync_valuation_str(
                    str(stock.get("valuation") or ""),
                    market,
                    pe_num=fresh_pe,
                    pb_num=fresh_pb,
                    div_pct=fresh_div,
                    ah_pct=live_ah,
                )

        # Refresh summary if badge flipped, urgent placement/chase-buy warning present, OR stale anchor/price contradicts fresh dossier
        old_lo, old_hi, _ = _parse_anchor(prev_summary, stock.get("price_num"))
        new_lo, new_hi, _ = _parse_anchor(f"{action_etf} {baseline_note}", stock.get("price_num"))
        anchor_contradicts = (
            old_lo is not None
            and new_lo is not None
            and (abs(old_lo - new_lo) > 0.5 or (old_hi is not None and new_hi is not None and abs(old_hi - new_hi) > 0.5))
        )
        stale_price_in_sum = False
        if old_price_num is not None and stock.get("price_num") is not None:
            rel_move = abs(stock["price_num"] - old_price_num) / max(old_price_num, 1e-6)
            if rel_move >= 0.08 and prev_summary:
                stale_price_in_sum = True
        has_urgent_warn = bool(_URGENT_DOSSIER_WARN_RE.search(action_etf[:120]))

        if action_etf and (badge_changed or anchor_contradicts or stale_price_in_sum or has_urgent_warn):
            refreshed_sum = _truncate_clean_summary(action_etf, max_len=78)
            if refreshed_sum:
                stock["summary"] = refreshed_sum

    # 4. Recompute anchors from full dossier prose (action_etf + baseline_note), falling back to stock["summary"] / prev_summary
    cur_price_num = stock.get("price_num")
    if cur_price_num is None and stock.get("price"):
        cur_price_num = _parse_price_num(str(stock.get("price") or ""))
        stock["price_num"] = cur_price_num
    if is_strictly_fresher or stock.get("anchor_low") is None:
        a_lo, a_hi, a_gap = _parse_anchor(f"{action_etf} {baseline_note}", cur_price_num)
        if a_lo is None:
            a_lo, a_hi, a_gap = _parse_anchor(str(stock.get("summary") or ""), cur_price_num)
        if a_lo is None and prev_summary:
            a_lo, a_hi, a_gap = _parse_anchor(prev_summary, cur_price_num)
        if a_lo is not None or is_strictly_fresher:
            stock["anchor_low"] = a_lo
            stock["anchor_high"] = a_hi
            stock["anchor_gap_pct"] = a_gap

    return stock


def merge_stock_dossiers(
    stocks: list[dict[str, Any]],
    dossiers_payload: dict[str, Any] | None,
    *,
    flagship_dates: dict[str, str] | None = None,
    gold_tier0_locked: bool = False,
    ah_benchmarks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach 7-dimension institutional deep-research dossiers onto matching pool stocks and sync fresher badges/prices."""
    if not isinstance(dossiers_payload, dict):
        return stocks
    dmap = dossiers_payload.get("dossiers")
    if not isinstance(dmap, dict):
        return stocks
    snapshot_day = _valid_iso_date(dossiers_payload.get("as_of_date"))
    cutoff = date.fromisoformat(snapshot_day) if snapshot_day else None
    ah_lookup: dict[str, float] = {}
    for row in ah_benchmarks or []:
        if not isinstance(row, dict):
            continue
        pct = _safe_float(row.get("ah_premium_pct"))
        if pct is None:
            continue
        for k in ("a", "h"):
            c = str(row.get(k) or "").strip()
            if c:
                ah_lookup[c] = pct
                ah_lookup[c.upper()] = pct
    for st in stocks:
        mkt = str(st.get("market", ""))
        key = f"{mkt}:{st.get('code', '')}"
        d = dmap.get(key)
        if isinstance(d, dict):
            dossier_obj = {
                "depth_tier": str(d.get("depth_tier", "standard_deep")),
                "baseline_note": str(d.get("baseline_note", "")),
                "moat": str(d.get("moat", "")),
                "financials": str(d.get("financials", "")),
                "valuation_anchor": str(d.get("valuation_anchor", "")),
                "shareholder_flow": str(d.get("shareholder_flow", "")),
                "catalysts": str(d.get("catalysts", "")),
                "bear_case": str(d.get("bear_case", "")),
                "action_etf": str(d.get("action_etf", "")),
                "updated_at": str(d.get("updated_at", "")),
                "evidence": inventory_evidence(d, STOCK_FIELDS, cutoff),
            }
            st["dossier"] = dossier_obj
            if flagship_dates is not None or ("color" in st or "price" in st):
                f_dt = (flagship_dates or {}).get(mkt, "")
                _overlay_fresher_dossier_on_stock(
                    st,
                    dossier_obj,
                    f_dt,
                    gold_tier0_locked,
                    ah_lookup=ah_lookup,
                )
    return stocks


def _closing_quote_available(
    observed: str, market: str, cutoff: str, calendar_overrides: list[dict] | None = None,
    *,
    close_delay_minutes: int = 0,
) -> bool:
    """Check a dated daily bar against the local cash session and declared holidays."""
    try:
        day = date.fromisoformat(observed)
        stamp = datetime.fromisoformat(cutoff)
    except (TypeError, ValueError):
        return False
    if day.weekday() >= 5:
        return False

    market_id = market.replace("-", "_")
    holiday_types = {"partial_holiday", "long_holiday_start", "full_holiday", "full_holiday_and_rollover"}
    session_rules = {
        entry.get("type") for entry in calendar_overrides or []
        if isinstance(entry, dict) and isinstance(entry.get("type"), str)
        and isinstance(entry.get("markets_affected"), list) and market_id in entry["markets_affected"]
        and (first := _valid_iso_date(entry.get("date_cst"))) and first <= observed
        and observed <= _valid_iso_date(entry.get("end_date_cst", first))
    }
    if session_rules & holiday_types:
        return False
    if cutoff == cutoff[:10]:
        return day <= stamp.date()
    beijing = ZoneInfo("Asia/Shanghai")
    zone = ZoneInfo("America/New_York") if market == "us-stock" else beijing
    closes = {"a-share": time(15), "hk-stock": time(16, 10), "us-stock": time(16)}
    half_day_closes = {"hk-stock": time(12, 10), "us-stock": time(13)}
    close = half_day_closes.get(market, closes[market]) if "half_day" in session_rules else closes[market]
    cutoff_at = stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=beijing)
    return datetime.combine(day, close, zone) + timedelta(minutes=close_delay_minutes) <= cutoff_at


def _align_screener_quotes(
    stocks: list[dict[str, Any]], manifest: dict[str, Any], cutoff: str, calendar_overrides: list[dict] | None = None,
) -> None:
    """Use the edition's dated candles for prices shared with the chart and watchlist."""
    series = {row["id"]: row for row in (manifest.get("catalog") or []) if isinstance(row, dict) and isinstance(row.get("id"), str)}
    currencies = {"a-share": ("CNY", "元"), "hk-stock": ("HKD", "港元"), "us-stock": ("USD", "美元")}
    for stock in stocks:
        row = series.get(f"stk_{stock['code']}", {})
        observed = _valid_iso_date(row.get("latest_date"))
        currency, unit = currencies[stock["market"]]
        value = _safe_float(row.get("latest_close"))
        if (
            not observed or not _closing_quote_available(observed, stock["market"], cutoff, calendar_overrides)
            or row.get("stale") is not False
            or row.get("currency") != currency or row.get("market") != stock["market"]
            or row.get("code") != stock["code"] or value is None or value <= 0
        ):
            stock.update(price="同口径行情待核", price_num=None, price_updated_at="", price_source="", anchor_gap_pct=None)
            continue
        change = _safe_float(row.get("change_pct"))
        label = format(value, ",.3f").rstrip("0").rstrip(".")
        move = f" ({change:+.2f}%)" if change is not None else ""
        stock.update(price=f"{label} {unit}{move}", price_num=value, price_updated_at=observed,
                     price_source=_kline_source_label(row.get("provider")))
        lo, hi = _safe_float(stock.get("anchor_low")), _safe_float(stock.get("anchor_high"))
        reference = (lo + hi) / 2 if lo and hi and lo > 0 and hi > 0 else None
        gap = round(100 * (value - reference) / reference, 1) if reference else None
        stock["anchor_gap_pct"] = gap if gap is not None and -80 <= gap <= 250 else None


_OFFICIAL_VERIFY_PORTALS: tuple[dict[str, str], ...] = (
    {
        "org": "中国证券投资基金业协会（中基协）",
        "scope": "公募基金、私募基金管理人与私募产品备案真伪查询",
        "url": "https://gs.amac.org.cn/",
    },
    {
        "org": "中国信托登记有限责任公司（中国信登）",
        "scope": "正规信托公司发行的标品与集合信托产品登记编码核验",
        "url": "https://www.chinatrc.com.cn/",
    },
    {
        "org": "中国理财网（银行业理财登记托管中心）",
        "scope": "银行及理财子公司发行的全部正规理财产品登记编码查询",
        "url": "https://www.chinawealth.com.cn/",
    },
    {
        "org": "国家金融监督管理总局（许可证查询）",
        "scope": "核验银行、保险公司、保险中介与持牌金融机构合法金融许可证",
        "url": "https://xkz.nfra.gov.cn/",
    },
)

_DEFAULT_IPO_TOOLBOX: tuple[dict[str, str], ...] = (
    {
        "title": "可转债信用打新（零资金占用）",
        "tag": "新手首选低风险增厚",
        "threshold": "20 日日均 10 万 + 2 年交易经验",
        "detail": "申购日无须预缴现金，中签后按 1,000 元/签缴款；中签率虽低但零占用资金，上市前核对主体评级与溢价定位，上市后及时兑现不盲目高价追炒。",
    },
    {
        "title": "A 股沪深市值配售打新",
        "tag": "持仓底仓顺带增厚",
        "threshold": "T-2 前 20 日日均非限售 A 股市值 ≥1 万元（科创/创业需对应权限）",
        "detail": "仅需日常持有红利宽基个股底仓即可顺带申购，无须为打新专门买高波股；中签后评估发行市盈率与行业景气，严防高估值新股破发。",
    },
    {
        "title": "北交所新股申购规则",
        "tag": "资金门槛偏高 · 留意新政",
        "threshold": "50 万资产 + 2 年经验；现行现金全额冻资竞争激烈，留意市值配售试点演进",
        "detail": "北交所现行申购需提前冻结全额现金，中小资金中签效率偏低，更适合大额闲置资金在无更好票息窗口时理性测算性价比。",
    },
    {
        "title": "港股打新与公募 REITs 认购提醒",
        "tag": "破发常态化 · 切忌盲打",
        "threshold": "港股需合规离岸账户；REITs 线上市值零门槛",
        "detail": "港股新股回拨机制改革后首日分化极大，公募 REITs 新发亦已常态化破发；严禁融资加杠杆打新，只挑基石阵容扎实且估值留足折价的标的。",
    },
)


def _render_ipo_toolbox_section(data: dict[str, Any]) -> str:
    raw = data.get("ipo_toolbox")
    title = "全市场打新与低风险增厚工具箱"
    subtitle = "横向覆盖可转债、A 股沪深、北交所、港股与公募 REITs 打新机制与避坑边界"
    items: list[dict[str, str]] = []

    if isinstance(raw, dict):
        if raw.get("title"):
            title = str(raw["title"]).strip()
        if raw.get("subtitle") or raw.get("summary"):
            subtitle = str(raw.get("subtitle") or raw.get("summary")).strip()
        seq = raw.get("items") or raw.get("channels") or raw.get("markets") or raw.get("tools") or raw.get("rows") or []
    elif isinstance(raw, list):
        seq = raw
    else:
        seq = []

    if isinstance(seq, list):
        for x in seq:
            if not isinstance(x, dict):
                continue
            t = str(x.get("title") or x.get("name") or x.get("market") or "").strip()
            if not t:
                continue
            tag = str(x.get("tag") or x.get("status") or x.get("priority") or "规则核对").strip()
            thr = str(x.get("threshold") or x.get("requirement") or x.get("eligibility") or "").strip()
            detail = str(x.get("detail") or x.get("strategy") or x.get("rules") or x.get("mechanism") or "").strip()
            risk = str(x.get("risk") or x.get("note") or x.get("caveat") or x.get("tip") or "").strip()
            full_detail = f"{detail} {risk}".strip() if (detail and risk and risk not in detail) else (detail or risk)
            items.append({"title": t, "tag": tag, "threshold": thr, "detail": full_detail})

    if not items:
        items = list(_DEFAULT_IPO_TOOLBOX)

    card_parts: list[str] = []
    for it in items:
        thr_html = (
            f'<div class="ipo-meta"><strong>门槛：</strong>{esc(it["threshold"])}</div>'
            if it.get("threshold")
            else ""
        )
        card_parts.append(
            f'<div class="ipo-card">'
            f'<div class="ipo-head"><strong>{esc(it["title"])}</strong><span class="ipo-tag">{esc(it["tag"])}</span></div>'
            f"{thr_html}"
            f'<div class="ipo-detail">{esc(it["detail"])}</div>'
            f"</div>"
        )
    cards = "".join(card_parts)
    return (
        '<div class="sec-head" id="sec-ipo-toolbox">'
        f'<h2>{esc(title)}</h2>'
        f'<span class="sec-sub">{esc(subtitle)}</span>'
        "</div>"
        f'<section class="ipo-grid">{cards}</section>'
    )


def _render_dual_warning_wall(data: dict[str, Any], cgb10y_disp: str) -> str:
    """Render upgraded 2-tier Warning Wall: Legal High-Risk vs Illegal/Forbidden + 4 Official Verification Portals."""
    caution_items: list[dict[str, str]] = []
    ban_items: list[dict[str, str]] = []
    portals: list[dict[str, str]] = []

    wall = data.get("risk_warning_wall") or data.get("warning_wall")
    if isinstance(wall, dict):
        for raw_list, bucket in (
            (wall.get("legal_high_risk") or wall.get("tier1_high_risk") or wall.get("high_risk") or [], caution_items),
            (wall.get("illegal_forbidden") or wall.get("tier2_illegal") or wall.get("regulatory_ban") or wall.get("prohibited") or [], ban_items),
        ):
            if isinstance(raw_list, list):
                for item in raw_list:
                    if isinstance(item, dict) and (item.get("title") or item.get("name")):
                        bucket.append(
                            {
                                "title": str(item.get("title") or item.get("name") or "").strip(),
                                "detail": str(item.get("detail") or item.get("desc") or item.get("reason") or "").strip(),
                            }
                        )
        raw_p = wall.get("verification_portals") or wall.get("official_verifications") or wall.get("verify_links")
        if isinstance(raw_p, list):
            for p in raw_p:
                if isinstance(p, dict) and p.get("url"):
                    url_s = str(p["url"]).strip()
                    if url_s.startswith(("http://", "https://")):
                        portals.append(
                            {
                                "org": str(p.get("org") or p.get("name") or p.get("title") or "").strip(),
                                "scope": str(p.get("scope") or p.get("desc") or p.get("detail") or "").strip(),
                                "url": url_s,
                            }
                        )

    # Also gracefully absorb flat or layered red_flags
    red_flags = data.get("red_flags") if isinstance(data.get("red_flags"), list) else []
    if not caution_items and not ban_items and red_flags:
        caution_kws = ("溢价", "LOF", "理财", "破净", "杠杆衍生", "期权", "30年", "雪球", "退市")
        for rf in red_flags:
            if not isinstance(rf, dict):
                continue
            title = str(rf.get("title") or "").strip()
            detail = str(rf.get("detail") or "").strip()
            if not title:
                continue
            layer = str(rf.get("layer") or rf.get("tier") or rf.get("level") or "").strip().lower()
            if layer in ("legal_high_risk", "high_risk", "caution", "tier1", "1"):
                caution_items.append({"title": title, "detail": detail})
            elif layer in ("illegal", "forbidden", "regulatory_ban", "prohibited", "tier2", "2"):
                ban_items.append({"title": title, "detail": detail})
            elif any(k in title for k in caution_kws) and "空气盘" not in title:
                caution_items.append({"title": title, "detail": detail})
            else:
                ban_items.append({"title": title, "detail": detail})

    if not caution_items:
        caution_items = [
            {"title": "高溢价跨境 QDII 与商品 LOF", "detail": "净值下跌和溢价收窄均可能造成亏损。涉及交易安排时，核对交易所正式规则与该基金公告。"},
            {"title": "银行理财“低波幻觉”与超长债重仓", "detail": "全面真净值化后银行理财同样会阶段性破净；30 年超长国债久期近 20 年，绝非保本稳钱替代品。"},
            {"title": "问题低评级转债、融资融券与复杂场外期权", "detail": "合法交易工具但杠杆或违约风险极高，普通新手切勿因高表面收益率贸然涉足。"},
        ]
    if not ban_items:
        ban_items = [
            {"title": "政信定融、城投非标与违规金交所通道", "detail": "全国合规地方金交所已实质性清零，非标定融违约与展期风险由出资人全额自担。"},
            {"title": "违规私募飞单、实物金托管返息与“保本高息”", "detail": "凡宣称保本年化 6%–8% 以上、或引导转账至个人与非托管对公账户的均为高危骗局。"},
            {"title": "场外高杠杆外汇黑平台、非法 RWA 与 OTC 冻卡", "detail": "境内从未批准面向个人的网络外汇保证金或非法虚拟货币/RWA 集资平台，资金不受法律保护且触碰冻卡与刑事红线。"},
        ]
    if not portals:
        portals = list(_OFFICIAL_VERIFY_PORTALS)

    caution_html = "".join(
        f'<div class="warning-item"><strong>⚠️ {esc(x["title"])}</strong><p>{esc(x["detail"])}</p></div>'
        for x in caution_items
    )
    ban_html = "".join(
        f'<div class="warning-item"><strong>⛔ {esc(x["title"])}</strong><p>{esc(x["detail"])}</p></div>'
        for x in ban_items
    )
    portals_html = "".join(
        f'<a class="verify-card" href="{esc(p["url"])}" target="_blank" rel="noopener noreferrer">'
        f'<div class="verify-org">{esc(p["org"])} ↗</div>'
        f'<div class="verify-desc">{esc(p["scope"])}</div>'
        f"</a>"
        for p in portals
    )
    rate_ctx = f"在当前 10 年国债 {cgb10y_disp} 的低利率环境下" if cgb10y_disp else "在当前低利率环境下"
    return (
        '<div class="sec-head" id="sec-warning-wall">'
        "<h2>双层风控警示墙与四道官方验真入口</h2>"
        f'<span class="sec-sub">{esc(rate_ctx)}，先分清「合法但高风险」与「监管禁区」，凡宣称保本高息一律一票否决</span>'
        "</div>"
        '<section class="warning-wall">'
        '<div class="warning-layer wl-caution">'
        '<div class="wl-head">第一层｜合法但高风险 · 新手勿碰（持牌产品但波动/溢价/结构复杂）</div>'
        f'<div class="warning-grid">{caution_html}</div>'
        "</div>"
        '<div class="warning-layer wl-ban">'
        '<div class="wl-head">第二层｜监管禁区与非法金融 · 零容忍（无牌照、资金池或违法集资）</div>'
        f'<div class="warning-grid">{ban_html}</div>'
        "</div>"
        '<div class="verify-box">'
        '<div class="verify-title">🔍 转账前必查：四道中国官方金融真伪核验官网</div>'
        f'<div class="verify-grid">{portals_html}</div>'
        "</div>"
        "</section>"
    )


def build_channels_page(
    channels_data: dict[str, Any] | None,
    *,
    etf_data: dict[str, Any] | None = None,
    eq_state: dict[str, Any] | None = None,
) -> str:
    """Render the dedicated Personal Multi-Asset Investment Channels overview page (channels.html)."""
    data = channels_data if isinstance(channels_data, dict) else {}
    channels = [c for c in (data.get("channels") or []) if isinstance(c, dict) and str(c.get("id", "")).strip()]
    ch_cnt = len(channels)
    etf_cnt = len((etf_data or {}).get("etfs") or []) if isinstance(etf_data, dict) else 0

    ch_cnt_tag = f"{ch_cnt} 大合规多元投资渠道" if ch_cnt else "合规多元投资渠道"
    headline = str(data.get("headline") or f"中国大陆个人投资者{ch_cnt_tag}全景调研")
    subtitle = str(
        data.get("subtitle")
        or "系统追踪活钱现金、银行存款、外币定存、债券 ETF、基金理财、储蓄险、个人养老金、跨境互认、可转债、公募 REITs、非金商品与合规私募全版图"
    )
    as_of = str(data.get("as_of_label") or "最新班次")
    mutex_note = str(data.get("gold_mutex_note") or "").replace("零档红灯停", "红灯停")
    anchors = data.get("macro_anchors") if isinstance(data.get("macro_anchors"), list) else []
    templates = data.get("allocation_templates") if isinstance(data.get("allocation_templates"), list) else []
    proc = data.get("research_process") if isinstance(data.get("research_process"), dict) else {}

    # Dynamic 10Y CGB yield (never hardcode 1.59%)
    cgb10y_val: float | None = None
    if isinstance(eq_state, dict):
        cgb10y_val = _safe_float(((eq_state.get("markets") or {}).get("a_share") or {}).get("cgb10y_pct"))
        if cgb10y_val is None:
            cgb10y_val = _safe_float(((eq_state.get("cross_market_linkages") or {}).get("rates_fx_chain") or {}).get("cgb10y_pct"))
    cgb10y_disp = f"{cgb10y_val:.2f}%" if cgb10y_val is not None else ""
    if not cgb10y_disp:
        for a in anchors:
            if isinstance(a, dict) and "10Y" in str(a.get("label", "")) and "国债" in str(a.get("label", "")):
                m_cgb = re.search(r"([0-9]+(?:\.[0-9]+)?%)", str(a.get("value", "")))
                if m_cgb:
                    cgb10y_disp = m_cgb.group(1)
                    break

    anchor_html = "".join(
        f'<div class="macro-card">'
        f'<div class="macro-lbl">{esc(a.get("label", ""))}</div>'
        f'<div class="macro-val">{esc(a.get("value", ""))}</div>'
        f'<div class="macro-note">{esc(a.get("note", ""))}</div>'
        f"</div>"
        for a in anchors
        if isinstance(a, dict)
    )

    # New: Side-by-side beginner comparison table across all channels
    compare_rows: list[str] = []
    for idx, ch in enumerate(channels, start=1):
        cid = str(ch["id"]).strip()
        num = _fmt_ch_num(ch.get("order"), idx)
        bk = _normalize_money_bucket(ch)
        _, bk_short = _BUCKET_META[bk]
        stars_str, stars_lbl = _fmt_stars(_channel_risk_stars(ch))
        hnw_tag = ' <span class="ch-hnw-badge">合格投资者</span>' if _is_hnw_channel(ch) else ""
        compare_rows.append(
            f"<tr>"
            f'<td class="nw"><span class="ch-num">{esc(num)}</span> <a href="channels/{esc(cid)}.html"><strong>{esc(ch.get("short_name") or ch.get("name", ""))}</strong></a>{hnw_tag}</td>'
            f'<td class="nw"><span class="ch-bucket-pill">{bk_short}</span></td>'
            f'<td>{esc(_short_yield_for_card(str(ch.get("yield_range", ""))))}</td>'
            f'<td class="nw"><span class="ch-risk-stars" aria-label="{esc(stars_lbl)}">{stars_str}</span> <span class="sec-sub">{esc(stars_lbl)}</span></td>'
            f'<td>{esc(_short_threshold_for_card(ch))}</td>'
            f'<td>{esc(str(ch.get("liquidity", "")))}</td>'
            f'<td>{esc(str(ch.get("tax_summary", "")))}</td>'
            f"</tr>"
        )
    compare_table_html = (
        '<div class="sec-head" id="sec-compare-table">'
        f'<h2>{ch_cnt} 大渠道一眼对比总表（按资金桶、年化、风险、门槛与税费横向比选）</h2>'
        '<span class="sec-sub">点击任意渠道名称直达独立 1 分钟指南页</span>'
        "</div>"
        '<div class="mobile-scroll-cue" aria-hidden="true">← 左右滑动查看完整列 →</div>'
        '<div class="table-wrap"><table class="data-table compare-table">'
        "<thead><tr><th>编号与渠道</th><th>所属资金桶</th><th>参考年化区间</th><th>风险星级</th><th>起投门槛</th><th>流动性特征</th><th>税费核心要点</th></tr></thead>"
        f'<tbody>{"".join(compare_rows)}</tbody></table></div>'
        if compare_rows
        else ""
    )

    etf_cta_lbl = f"进入全球 {etf_cnt} 只 ETF 深度雷达 →" if etf_cnt else "进入全球重点 ETF 深度雷达 →"
    filter_html = _render_channel_filter_panel(
        channels,
        right_cta_html=f'<a href="etfs.html" class="btn btn-sm">{esc(etf_cta_lbl)}</a>',
    )
    ch_cards_rendered = _render_channel_overview_cards(channels)

    tpl_html = "".join(
        f'<div class="tpl-card">'
        f'<div class="tpl-head">{esc(t.get("name", ""))}</div>'
        f'<div class="sec-sub">{esc(t.get("audience", ""))}</div>'
        f'<div class="tpl-target">{esc(t.get("target_yield", ""))}</div>'
        f'<ul class="tpl-list">'
        + "".join(
            f'<li class="tpl-slice"><span class="tpl-weight">{esc(s.get("weight", ""))}</span>'
            f'<strong>{esc(s.get("channel", ""))}</strong>：{esc(s.get("vehicles", ""))}</li>'
            for s in (t.get("slices") or [])
            if isinstance(s, dict)
        )
        + "</ul></div>"
        for t in templates
        if isinstance(t, dict)
    )

    ipo_html = _render_ipo_toolbox_section(data)
    warning_wall_html = _render_dual_warning_wall(data, cgb10y_disp)

    pillars = proc.get("pillars") if isinstance(proc.get("pillars"), list) else []
    proc_html = "".join(
        f'<div class="process-card">'
        f'<div class="process-step">STEP {esc(p.get("step", ""))}</div>'
        f'<div style="font-weight:800;font-size:14.5px;margin-bottom:5px;">{esc(p.get("name", ""))}</div>'
        f'<div class="sec-sub" style="line-height:1.58;">{esc(p.get("detail", ""))}</div>'
        f"</div>"
        for p in pillars
        if isinstance(p, dict)
    )

    ch_filter_h2 = f"按用钱时间或资产类型筛选全部 {ch_cnt} 大渠道" if ch_cnt else "按用钱时间或资产类型筛选全部合规渠道"
    return f"""
    <section class="channels-hero">
      <div class="exec-top">
        <span class="cover-tag">{esc(ch_cnt_tag)} · {esc(as_of)}</span>
        {f'<span class="compact-alert-pill">🛑 {esc(mutex_note)}</span>' if mutex_note else ''}
      </div>
      <div class="exec-main">
        <div class="exec-copy">
          <h1>{esc(headline)}</h1>
          <p class="channels-hero-sub">{esc(subtitle)}</p>
        </div>
        <div class="exec-actions">
          <a class="btn btn-qdii" href="channels/qdii_mrf.html#sec-qdii-compare">⚡ QDII 溢价与限购表 →</a>
          <a class="btn btn-primary" href="#sec-compare-table">一眼对比总表 ↓</a>
        </div>
      </div>
      <div class="macro-strip">{anchor_html}</div>
    </section>

    {compare_table_html}

    <div class="sec-head" id="sec-channel-cards">
      <h2>{esc(ch_filter_h2)}</h2>
      <a href="guide.html" class="btn btn-sm">新手 3 分钟指南 →</a>
    </div>
    {filter_html}

    <section class="channel-list">
      {ch_cards_rendered}
    </section>

    <div class="sec-head">
      <h2>三大落地组合配置模板（与黄金及三市权益互补）</h2>
      <span class="sec-sub">以下为除股票与存量黄金外单独划出的多元防御/增强资金内部配比</span>
    </div>
    <section class="tpl-grid">{tpl_html}</section>

    {ipo_html}
    {warning_wall_html}

    <div class="sec-head">
      <h2>{esc(proc.get("title") or "每班调研追踪与质量核验制度")}</h2>
      <span class="sec-sub">{esc(proc.get("subtitle") or "")}</span>
    </div>
    <section class="process-grid">{proc_html}</section>
    """


def _etf_role_cls(item: dict[str, Any]) -> str:
    if item.get("gold_locked"):
        return "role-lock"
    role = str(item.get("action_role", ""))
    if "高危" in role or "高费" in role:
        return "role-danger"
    if "现金盾" in role:
        return "role-shield"
    if any(k in role for k in ("底座", "核心", "卫星")):
        return "role-base"
    return "role-watch"


def build_etfs_page(
    etf_data: dict[str, Any] | None,
    *,
    channel_count: int = 0,
    channels_data: dict[str, Any] | None = None,
) -> str:
    """Render the interactive Global Multi-Channel ETF Radar page (etfs.html)."""
    data = etf_data if isinstance(etf_data, dict) else {}
    etfs = data.get("etfs") if isinstance(data.get("etfs"), list) else []
    total = len(etfs)
    as_of = str(data.get("as_of_label") or "最新班次")
    lock_notice = str(data.get("gold_lock_notice") or "").replace("零档红灯停", "红灯停")
    rules = data.get("key_2026_rules") if isinstance(data.get("key_2026_rules"), list) else []
    ch_link_lbl = f"查看 {channel_count} 大个人多元渠道详规 →" if channel_count > 0 else "查看个人多元渠道详规 →"
    ch_short_lbl = f"查看 {channel_count} 大多元渠道 →" if channel_count > 0 else "查看个人多元渠道 →"
    qdii_summary_html = _render_qdii_comparison_section(channels_data, compact=True)

    cnt_m = defaultdict(int)
    cnt_ac = defaultdict(int)
    cnt_reg = defaultdict(int)
    cnt_qdii = 0
    enriched_etfs: list[dict[str, Any]] = []
    snapshot_day = _valid_iso_date(data.get("as_of_date"))
    cutoff = date.fromisoformat(snapshot_day) if snapshot_day else None
    for it in etfs:
        if isinstance(it, dict):
            ac, reg = _infer_etf_ortho(it)
            row_copy = dict(it)
            row_copy["asset_class"] = ac
            row_copy["region"] = reg
            row_copy["evidence"] = inventory_evidence(it, ETF_FIELDS, cutoff)
            enriched_etfs.append(row_copy)
            cnt_m[str(it.get("market", ""))] += 1
            cnt_ac[ac] += 1
            cnt_reg[reg] += 1
            if str(it.get("channel") or "").strip() == "境内QDII":
                cnt_qdii += 1
    cnt_nonus = cnt_reg["jp"] + cnt_reg["eu"] + cnt_reg["apac_em"] + cnt_reg["global"]
    cnt_fi_plus = cnt_ac["fixed_income"] + cnt_ac["cash_mmf"] + cnt_ac["convertible_bond"] + cnt_ac["reits"]
    cnt_gold_cmd = cnt_ac["gold"] + cnt_ac["commodity"]

    prem_lbls = {"normal": "折溢价常规", "watch": "买前核参考净值", "high_risk": "高溢价/高危预警"}

    def _fmt_etf_fee_td(raw_fee: Any) -> str:
        s = str(raw_fee or "").strip()
        m_p = re.match(r"^([^（(]+?)\s*([（(].+)$", s)
        if m_p:
            return f'<td class="col-num"><strong>{esc(m_p.group(1).strip())}</strong><div class="sec-sub">{esc(m_p.group(2).strip())}</div></td>'
        return f'<td class="col-num"><strong>{esc(s)}</strong></td>'

    static_rows = "".join(
        f"<tr>"
        f'<td><div><button type="button" class="star-btn" data-watch-toggle="1" data-watch-kind="etf" data-watch-id="{esc(it.get("code", ""))}" data-watch-kline="etf_{esc(it.get("code", ""))}" data-watch-code="{esc(it.get("code", ""))}" data-watch-name="{esc(_clean_etf_display_text(it.get("name", "")))}" aria-label="切换自选">☆</button> <strong>{esc(_clean_etf_display_text(it.get("name", "")))}</strong></div><div><span class="code-tag">{esc(it.get("code", ""))}</span> <span class="etf-ortho-tag">{esc(_ETF_ASSET_CLASS_LABELS.get(it["asset_class"], it["asset_class"]))} · {esc(_ETF_REGION_LABELS.get(it["region"], it["region"]))}</span> <span class="etf-chan-tag">{esc(_clean_etf_display_text(it.get("category", "")))}</span></div></td>'
        f'<td><div><span class="mkt-badge mkt-{esc(it.get("market", ""))}">{esc(it.get("market_label", ""))}</span></div><div><span class="etf-chan-tag">{esc(it.get("channel", ""))}</span></div></td>'
        f'<td><div>{esc(it.get("tracking_index", ""))}</div><div class="sec-sub">{esc(it.get("yield_or_pe", ""))}</div></td>'
        f'{_fmt_etf_fee_td(it.get("fee_total_pct", ""))}'
        f'<td><div><strong>{esc(it.get("aum", ""))}</strong></div><div class="sec-sub">{esc(it.get("liquidity", ""))}</div></td>'
        f'<td><div><span class="prem-pill prem-{esc(it.get("premium_status", "normal"))}">{esc(prem_lbls.get(str(it.get("premium_status", "normal")), "常规"))}</span></div><div class="sec-sub">{esc(it.get("premium_note", ""))}</div></td>'
        f'<td><div><span class="role-pill {_etf_role_cls(it)}">{esc(it.get("action_role", ""))}</span></div><div style="margin-top:5px;display:flex;gap:5px;flex-wrap:wrap;"><button type="button" class="dossier-btn" style="margin-left:0;" data-etf-code="{esc(it.get("code", ""))}">深度拆解</button><button type="button" class="kline-quick-btn" data-etf-code="{esc(it.get("code", ""))}" data-open-tab="kline">📈 K线</button></div></td>'
        f"</tr>"
        for it in enriched_etfs
    )
    safe_json = json.dumps(enriched_etfs, ensure_ascii=False).replace("</", "<\\/")
    rules_html = "".join(
        f'<div class="etf-rule-item">{esc(r)}</div>'
        for r in rules
        if isinstance(r, str) and r.strip()
    )

    rules_box_html = ""
    if rules_html:
        rules_box_html = (
            '<details class="disclosure-bar etf-rules-box">'
            '<summary class="disclosure-summary">'
            '<span class="disclosure-summary-main">'
            '<span class="disclosure-icon" aria-hidden="true">📐</span>'
            '<span class="disclosure-heading">'
            '<span class="disclosure-title">全球 ETF 费用、税务和折溢价规则</span>'
            "</span>"
            "</span>"
            '<span class="disclosure-summary-meta">'
            f'<span class="disclosure-toggle-lbl">{len(rules)} 条规则 ▾</span>'
            "</span>"
            "</summary>"
            f'<div class="etf-rules-body"><div class="etf-rules-grid">{rules_html}</div></div>'
            "</details>"
        )

    etfs_intro_html = inject_glossary_tips(
        f"""
    <div class="sec-head" style="margin-top:4px;">
      <div>
        <h1>全球 {total} 只重点 ETF 多通道深度雷达</h1>
        <span class="sec-sub">档案期号 {esc(as_of)} · 规模、费用与行情各有统计口径和日期。已列明的原始出处见各产品详情。</span>
      </div>
      {f'<span class="compact-alert-pill">🛑 {esc(lock_notice)}</span>' if lock_notice else ''}
    </div>
    {rules_box_html}
    """
    )

    return f"""
    {etfs_intro_html}

    <div class="screener-stats">
      <div class="stat-tile stat-total active" data-etf-stat-ortho="all" role="button" tabindex="0" aria-pressed="true">
        <div class="stat-tile-lbl">全通道 ETF</div>
        <div class="stat-tile-num">{total}</div>
      </div>
      <div class="stat-tile stat-tile-a" data-etf-stat-ortho="equity" role="button" tabindex="0" aria-pressed="false">
        <div class="stat-tile-lbl">📈 股票权益</div>
        <div class="stat-tile-num">{cnt_ac["equity"]}</div>
      </div>
      <div class="stat-tile stat-tile-hk" data-etf-stat-ortho="fixed_income_plus" role="button" tabindex="0" aria-pressed="false">
        <div class="stat-tile-lbl">🏦 债/现/转债/REITs</div>
        <div class="stat-tile-num">{cnt_fi_plus}</div>
      </div>
      <div class="stat-tile stat-tile-us" data-etf-stat-ortho="qdii" role="button" tabindex="0" aria-pressed="false">
        <div class="stat-tile-lbl">⚡ 境内 QDII</div>
        <div class="stat-tile-num">{cnt_qdii}</div>
      </div>
      <div class="stat-tile stat-tile-gold" data-etf-stat-ortho="gold_commodity" role="button" tabindex="0" aria-pressed="false">
        <div class="stat-tile-lbl">🥇 黄金红灯/商品</div>
        <div class="stat-tile-num">{cnt_gold_cmd}</div>
      </div>
    </div>

    <section class="filter-panel toolbar-sticky">
      <div class="filter-row">
        <div class="search-wrap">
          <input type="search" id="etf-search" class="search-input" placeholder="搜索代码 / 简称 / 指数 / 联接（如 563360、IB01、513800、红利）…" autocomplete="off">
          <button type="button" id="etf-clear" class="search-clear" aria-label="清空搜索" hidden>×</button>
          <kbd class="kbd-hint" aria-hidden="true">/</kbd>
        </div>
        <div class="preset-row" role="group" aria-label="ETF 快捷筛选">
          <button type="button" class="preset-pill active" data-etf-preset="all">全部</button>
          <button type="button" class="preset-pill preset-pill-qdii" data-etf-preset="qdii">⚡ QDII排雷 ({cnt_qdii})</button>
          <button type="button" class="preset-pill" data-etf-preset="watchlist">★ 自选</button>
          <button type="button" class="preset-pill" data-etf-preset="low-fee">低费 ≤0.20%</button>
          <button type="button" class="preset-pill" data-etf-preset="high-risk">高危预警</button>
        </div>
        <button type="button" class="ctrl-btn filter-adv-btn" data-toggle-adv-filter="1" aria-expanded="false">精细筛选 ▾</button>
        <button type="button" class="btn btn-sm" id="etf-reset">重置</button>
      </div>
      <div class="filter-adv-tray" hidden>
        <div class="filter-row">
          <span class="filter-row-lbl">更多预设</span>
          <button type="button" class="preset-pill" data-etf-preset="base">红灯稳健底座</button>
          <button type="button" class="preset-pill" data-etf-preset="cash-shield">本外币现金盾</button>
          <button type="button" class="preset-pill" data-etf-preset="hide-gold">隐藏黄金红灯锁</button>
        </div>
        <div class="filter-row">
          <span class="filter-row-lbl">资产大类</span>
          <button type="button" class="filter-pill active" data-etf-asset-class="all">全部大类 ({total})</button>
          <button type="button" class="filter-pill" data-etf-asset-class="equity">股票权益 ({cnt_ac["equity"]})</button>
          <button type="button" class="filter-pill" data-etf-asset-class="fixed_income_plus">固收现金组合 ({cnt_fi_plus})</button>
          <button type="button" class="filter-pill" data-etf-asset-class="fixed_income">利率信用债 ({cnt_ac["fixed_income"]})</button>
          <button type="button" class="filter-pill" data-etf-asset-class="cash_mmf">现金货币盾 ({cnt_ac["cash_mmf"]})</button>
          <button type="button" class="filter-pill" data-etf-asset-class="convertible_bond">可转债 ({cnt_ac["convertible_bond"]})</button>
          <button type="button" class="filter-pill" data-etf-asset-class="gold">黄金红灯 ({cnt_ac["gold"]})</button>
          <button type="button" class="filter-pill" data-etf-asset-class="commodity">非金商品 ({cnt_ac["commodity"]})</button>
          <button type="button" class="filter-pill" data-etf-asset-class="reits">REITs ({cnt_ac["reits"]})</button>
        </div>
        <div class="filter-row">
          <span class="filter-row-lbl">底层区域</span>
          <button type="button" class="filter-pill active" data-etf-region="all">全部区域</button>
          <button type="button" class="filter-pill" data-etf-region="cn">🇨🇳 中国境内 ({cnt_reg["cn"]})</button>
          <button type="button" class="filter-pill" data-etf-region="hk">🇭🇰 中国香港 ({cnt_reg["hk"]})</button>
          <button type="button" class="filter-pill" data-etf-region="us">🇺🇸 美国 ({cnt_reg["us"]})</button>
          <button type="button" class="filter-pill" data-etf-region="non_us">🌏 日欧亚太全球 ({cnt_nonus})</button>
          <button type="button" class="filter-pill" data-etf-region="jp">🇯🇵 日本 ({cnt_reg["jp"]})</button>
          <button type="button" class="filter-pill" data-etf-region="eu">🇪🇺 欧洲 ({cnt_reg["eu"]})</button>
          <button type="button" class="filter-pill" data-etf-region="apac_em">亚太新兴 ({cnt_reg["apac_em"]})</button>
          <button type="button" class="filter-pill" data-etf-region="global">全球大宗/宽基 ({cnt_reg["global"]})</button>
        </div>
        <div class="filter-row">
          <span class="filter-row-lbl">交易通道</span>
          <button type="button" class="filter-pill active" data-etf-channel="all">全部交易通道</button>
          <button type="button" class="filter-pill" data-etf-channel="境内场内">境内场内</button>
          <button type="button" class="filter-pill" data-etf-channel="境内非QDII港股通">境内非QDII港股通</button>
          <button type="button" class="filter-pill" data-etf-channel="境内QDII">境内QDII ({cnt_qdii})</button>
          <button type="button" class="filter-pill" data-etf-channel="离岸港交所">离岸港交所</button>
          <button type="button" class="filter-pill" data-etf-channel="离岸美股">离岸美股</button>
          <button type="button" class="filter-pill" data-etf-channel="爱尔兰UCITS">爱尔兰 UCITS／ETC</button>
        </div>
      </div>
    </section>

    <div class="screener-bar">
      <strong id="etf-count" role="status">显示 {total} / {total} 只重点 ETF</strong>
      <a href="channels.html" class="btn btn-sm">{esc(ch_link_lbl)}</a>
    </div>

    {qdii_summary_html}

    <div class="table-wrap etf-table-wrap">
      <table class="etf-table">
        <thead>
          <tr>
            <th class="sortable" data-sort="code"><button type="button" disabled>ETF 名称与代码 ⇅</button></th>
            <th class="sortable" data-sort="channel"><button type="button" disabled>市场与通道 ⇅</button></th>
            <th>跟踪指数与收益特征</th>
            <th class="sortable" data-sort="fee_num"><button type="button" disabled>年费率 ⇅</button></th>
            <th>规模与流动性</th>
            <th>折溢价状态与风险</th>
            <th class="sortable" data-sort="action_role"><button type="button" disabled>角色与深度拆解 ⇅</button></th>
          </tr>
        </thead>
        <tbody id="etf-tbody">{static_rows}</tbody>
      </table>
    </div>

    <div class="etf-cards" id="etf-cards"></div>
    <div class="pg-bar" id="etf-pg-bar"></div>

    <div class="dossier-backdrop drawer-modal no-print" id="etf-modal" role="dialog" aria-modal="true" aria-label="ETF 深度拆解">
      <div class="dossier-dialog">
        <div class="dossier-head">
          <div class="dossier-head-main">
            <h3 class="dossier-title" id="etf-modal-title">ETF 深度档案</h3>
            <div class="dossier-sub" id="etf-modal-sub"></div>
            <div class="dossier-badges" id="etf-modal-badges"></div>
          </div>
          <div class="drawer-nav-btns">
            <button type="button" class="ctrl-btn" data-drawer-step="-1" title="上一个 (↑)" aria-label="上一个">↑</button>
            <span class="drawer-pos" data-drawer-pos></span>
            <button type="button" class="ctrl-btn" data-drawer-step="1" title="下一个 (↓)" aria-label="下一个">↓</button>
            <button type="button" class="ctrl-btn" data-action="close-etf" aria-label="关闭 ETF 详情">关闭 ✕</button>
          </div>
        </div>
        <div class="dossier-body" id="etf-modal-body"></div>
        <div class="dossier-foot">
          <span>数据经交易所、基金定期报告与官网费率交叉核验 · 下单前请实时核对盘口参考净值</span>
          <a href="channels.html" class="btn btn-sm">{esc(ch_short_lbl)}</a>
        </div>
      </div>
    </div>

    <script id="etf-data" type="application/json">{safe_json}</script>
    """


def build_screener_page(
    stocks: list[dict[str, Any]],
    benchmarks: dict[str, str],
    *,
    default_date: str = "",
    ah_matrix: list[dict[str, Any]] | None = None,
    hsahp_index: float | None = None,
    hkd_cny_mid: float | None = None,
    hkd_cny_mid_date: str = "",
) -> str:
    total = len(stocks)
    cnt_m = defaultdict(int)
    cnt_c = defaultdict(int)
    ah_by_code = {row[key]: row for row in (ah_matrix or []) for key in ("a_code", "h_code")}
    for st in stocks:
        cnt_m[st["market"]] += 1
        cnt_c[st["color"]] += 1
        st["benchmark_time"] = benchmarks[st["market"]]
        if st["code"] in ah_by_code:
            pair = ah_by_code[st["code"]]
            st["ah_pct"] = pair["ah_premium_pct"]
            st["ah_quote_date"] = pair.get("quote_date") or ""
            parts = [part.strip() for part in str(st.get("valuation") or "").split("/")]
            if st["market"] == "a-share" and len(parts) >= 4 and re.fullmatch(r"[+\-−]?\d+(?:\.\d+)?%", parts[3]):
                del parts[3]
            st["valuation"] = " / ".join(part for part in parts if not re.search(r"\bA/?H\b|A\s*折\s*H", part, re.I))
    source_labels = " · ".join(
        f"{label}（{cnt_m[slug]} 家，{esc(benchmarks[slug])}）"
        for slug, label in (("a-share", "A 股"), ("hk-stock", "港股"), ("us-stock", "美股"))
    )

    safe_json = json.dumps(stocks, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    static_rows = "".join(_render_static_screener_row(stock) for stock in stocks)
    date_fallback = default_date.strip() or "最新班次"

    ah_rows = ah_matrix or []
    safe_ah_json = json.dumps(ah_rows, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    ah_cnt = len(ah_rows)
    ah_static_rows = []
    for r in ah_rows:
        prem = r.get("ah_premium_pct")
        prem_txt = f"{prem:+.1f}%" if isinstance(prem, (int, float)) else "—"
        prem_cls = "ah-pill ah-disc" if (isinstance(prem, (int, float)) and prem < 0) else "ah-pill ah-prem"
        a_div_txt = f"{r['a_div_pct']:.2f}%" if isinstance(r.get("a_div_pct"), (int, float)) else "—"
        h_yield_key = "h_div_pct" if r.get("h_local_cash") or r.get("h_tax_pending") or r.get("no_cash_dividend") else "h_connect_after_tax_div"
        h_value = r.get(h_yield_key)
        h_div_txt = f"{h_value:.2f}%" if isinstance(h_value, (int, float)) else "—"
        h_label = "H 香港登记股东税前" if r.get("h_local_cash") else "H 港股通税后"
        if r.get("h_tax_pending"):
            h_label = "H 港股通税前"
        if r.get("h_not_eligible"):
            h_label = "H 本期分派不适用"
        elif r.get("no_cash_dividend"):
            h_label = "H 本期现金股息"
        tax_tag = (
            f'（按 {r["h_tax_rate_pct"]}% 测算）'
            if h_value is not None and r.get("h_tax_rate_pct") is not None and not (r.get("h_local_cash") or r.get("no_cash_dividend"))
            else ""
        )
        kline_sym = str(r.get("a_sym_id") or r.get("h_sym_id") or "").strip()
        kline_cell = (
            f'<a href="charts.html#sym={esc(kline_sym)}" class="kline-quick-btn">📈 K线</a>'
            if kline_sym
            else '<span class="sec-sub">—</span>'
        )
        quote_date = r.get("quote_date") or "同日行情待核"
        quote_source = r.get("quote_source")
        quote_links = " ".join(
            f'<a href="{esc(source)}">{side.upper()} {label}</a>'
            for label, urls in (("收盘来源", r["quote_urls"]), ("报价原始行", r["quote_replay_urls"]))
            for side, source in urls.items()
        )
        dividend_sources = r.get("dividend_sources") or {}
        source_links = " ".join(
            f'<a href="{esc(source)}">{side.upper()} 股息来源{f" {number}" if len(sources) > 1 else ""}</a>'
            for side, sources in dividend_sources.items()
            for number, source in enumerate(sources, start=1)
        )
        dividend_note = esc(r.get("dividend_basis") or "股息资料待核")
        ah_static_rows.append(
            "<tr>"
            f'<td><strong>{esc(r["name"])}</strong><div class="sec-sub">{esc(r["a_code"])} / {esc(r["h_code"])}</div></td>'
            f'<td><div>A: {esc(r["a_price"])}</div><div>H: {esc(r["h_price"])}</div>'
            f'<div class="sec-sub">{esc(quote_date)}{f" · {esc(quote_source)}" if quote_source else ""} {quote_links}</div></td>'
            f'<td><span class="{prem_cls}">{esc(prem_txt)}</span></td>'
            f'<td><div>A 持有>1年免税: <strong>{esc(a_div_txt)}</strong></div>'
            f'<div class="sec-sub">{h_label}：<strong>{esc(h_div_txt)}</strong>{tax_tag}</div>'
            f'<div class="sec-sub">{dividend_note} {source_links}</div></td>'
            f'<td><span class="ah-verdict-pill ah-v-{esc(r["verdict_tone"])}">{esc(r["verdict_label"])}</span></td>'
            f"<td>{kline_cell}</td>"
            "</tr>"
        )
    hsahp_disp = f"{hsahp_index:.2f}" if isinstance(hsahp_index, (int, float)) else "待核"
    fx_disp = f"{hkd_cny_mid:.5f}" if isinstance(hkd_cny_mid, (int, float)) else "待核"

    screener_intro_html = inject_glossary_tips(
        f"""
    <div class="sec-head" style="margin-top:4px;">
      <h1>全球 {total} 家核心龙头交互筛选器</h1>
      <span class="sec-sub">旗舰基准 {source_labels} · 行情按所列交易日期和来源展示。估值、股息与观察价来自研究档案，具体出处见详情。</span>
    </div>
    """
    )

    return f"""
    {screener_intro_html}

    <div class="scr-view-tabs" role="tablist" aria-label="股池视图切换">
      <button type="button" role="tab" aria-selected="true" class="scr-view-btn active" data-scr-view="pool">📋 {total} 股 7 维全景池</button>
      <button type="button" role="tab" aria-selected="false" class="scr-view-btn" data-scr-view="ah-matrix">↔ {ah_cnt} 对 A/H 孪生股税后比价矩阵</button>
    </div>

    <div id="scr-view-pool">
    <div class="screener-stats">
      <div class="stat-tile stat-total" data-stat-color="all" role="button" tabindex="0" aria-pressed="false">
        <div class="stat-tile-lbl">全部龙头池</div>
        <div class="stat-tile-num">{total}</div>
      </div>
      <div class="stat-tile stat-tile-g" data-stat-color="g" role="button" tabindex="0" aria-pressed="false">
        <div class="stat-tile-lbl" style="color:var(--st-green-txt);">● 当下底座</div>
        <div class="stat-tile-num">{cnt_c["g"]}</div>
      </div>
      <div class="stat-tile stat-tile-b" data-stat-color="b" role="button" tabindex="0" aria-pressed="false">
        <div class="stat-tile-lbl" style="color:var(--st-blue-txt);">◆ 未来主攻</div>
        <div class="stat-tile-num">{cnt_c["b"]}</div>
      </div>
      <div class="stat-tile stat-tile-y" data-stat-color="y" role="button" tabindex="0" aria-pressed="false">
        <div class="stat-tile-lbl" style="color:var(--st-amber-txt);">▲ 分歧观察</div>
        <div class="stat-tile-num">{cnt_c["y"]}</div>
      </div>
      <div class="stat-tile stat-tile-r" data-stat-color="r" role="button" tabindex="0" aria-pressed="false">
        <div class="stat-tile-lbl" style="color:var(--st-red-txt);">× 高危回避</div>
        <div class="stat-tile-num">{cnt_c["r"]}</div>
      </div>
    </div>

    <section class="filter-panel toolbar-sticky">
      <div class="filter-row">
        <div class="search-wrap">
          <input type="search" id="scr-search" class="search-input" placeholder="搜索中文名 / 代码 / 赛道 / 关键词（如 宁德、NVDA、00883、银行）…" autocomplete="off">
          <button type="button" id="scr-clear" class="search-clear" aria-label="清空搜索" hidden>×</button>
          <kbd class="kbd-hint" aria-hidden="true">/</kbd>
        </div>
        <div class="preset-row" role="group" aria-label="快捷筛选预设">
          <button type="button" class="preset-pill active" data-preset="all">全部</button>
          <button type="button" class="preset-pill" data-preset="watchlist">★ 自选</button>
          <button type="button" class="preset-pill" data-preset="base">● 当下底座</button>
          <button type="button" class="preset-pill" data-preset="high-div">高股息 ≥4%</button>
          <button type="button" class="preset-pill" data-preset="near-anchor">近安全锚</button>
          <button type="button" class="preset-pill" data-preset="ah-inverted">A/H 倒挂</button>
        </div>
        <button type="button" class="ctrl-btn filter-adv-btn" data-toggle-adv-filter="1" aria-expanded="false">精细筛选 ▾</button>
        <button type="button" class="btn btn-sm" id="scr-reset">重置</button>
      </div>
      <div class="filter-adv-tray" hidden>
        <div class="filter-row">
          <button type="button" class="filter-pill active" data-filter-market="all">全部市场 ({total})</button>
          <button type="button" class="filter-pill" data-filter-market="a-share">🇨🇳 A 股 ({cnt_m["a-share"]})</button>
          <button type="button" class="filter-pill" data-filter-market="hk-stock">🇭🇰 港股 ({cnt_m["hk-stock"]})</button>
          <button type="button" class="filter-pill" data-filter-market="us-stock">🇺🇸 美股 ({cnt_m["us-stock"]})</button>
          <button type="button" class="preset-pill" data-preset="hide-red">隐藏高危回避</button>
        </div>
        <div class="filter-row">
          <button type="button" class="filter-pill active" data-filter-color="all">全部四色阵营</button>
          <button type="button" class="filter-pill" data-filter-color="g" data-color="g">● 当下底座 ({cnt_c["g"]})</button>
          <button type="button" class="filter-pill" data-filter-color="b" data-color="b">◆ 未来主攻 ({cnt_c["b"]})</button>
          <button type="button" class="filter-pill" data-filter-color="y" data-color="y">▲ 分歧观察 ({cnt_c["y"]})</button>
          <button type="button" class="filter-pill" data-filter-color="r" data-color="r">× 高危回避 ({cnt_c["r"]})</button>
        </div>
        <div class="sector-tray" id="scr-sector-tray" aria-label="赛道多选筛选"></div>
      </div>
    </section>

    <div class="screener-bar">
      <strong id="scr-count" role="status">显示 {total} / {total} 家龙头公司</strong>
      <div class="active-filters" id="scr-active-filters"></div>
    </div>

    <div class="screener-table-wrap">
      <table class="screener-table">
        <thead>
          <tr>
            <th class="sortable col-sticky" data-sort="market"><button type="button" disabled>市场 ⇅</button></th>
            <th class="sortable" data-sort="name"><button type="button" disabled>公司与代码 ⇅</button></th>
            <th class="sortable" data-sort="sector"><button type="button" disabled>赛道 ⇅</button></th>
            <th class="sortable" data-sort="pe_num"><button type="button" disabled>现价 / 估值 ⇅</button></th>
            <th class="sortable" data-sort="div_pct"><button type="button" disabled>股息 / AH ⇅</button></th>
            <th class="sortable" data-sort="color"><button type="button" disabled>四色阵营 ⇅</button></th>
            <th class="sortable" data-sort="anchor_gap_pct"><button type="button" disabled>核心诊断与距安全锚 ⇅</button></th>
          </tr>
        </thead>
        <tbody id="scr-tbody">{static_rows}</tbody>
      </table>
    </div>

    <div class="screener-cards" id="scr-cards"></div>
    <div class="pg-bar" id="scr-pg-bar"></div>
    </div>

    <section id="scr-view-ah" class="ah-matrix-panel" hidden aria-label="A/H 孪生股税后股息比价矩阵">
      <div class="sec-head" style="margin-top:4px;">
        <h2>↔ {ah_cnt} 对 A/H 孪生股溢价与税后股息比价矩阵</h2>
        <span class="sec-sub">恒生 AH 溢价指数 {hsahp_disp} · 港元中间价 {fx_disp} {esc(hkd_cny_mid_date)} · 溢价使用同日两地行情和中间价。税后排序使用可核对的港股通分派，先按统计期间分组。香港登记股东股息以税前列示。税率按 A 股持有超过 1 年、标准 H 股港股通 20% 试算。源头代扣待核的分派以税前列示。 <a href="https://fgk.chinatax.gov.cn/zcfgk/c102416/c5204006/content.html">沪港通税务政策</a></span>
      </div>
      <div class="filter-panel">
        <div class="filter-row">
          <button type="button" class="filter-pill active" data-ah-filter="all">全部 {ah_cnt} 对</button>
          <button type="button" class="filter-pill" data-ah-filter="a-cheaper">🟢 A 股倒挂更便宜</button>
          <button type="button" class="filter-pill" data-ah-filter="hk-connect-wins">🇭🇰 港股通税后仍胜</button>
          <button type="button" class="filter-pill" data-ah-filter="a-div-wins">🇨🇳 A 股税后股息占优</button>
          <button type="button" class="filter-pill" data-ah-filter="high-prem">⚠️ 高溢价 &ge;50%</button>
        </div>
        <div class="screener-bar" style="margin:0;">
          <strong id="ah-matrix-count" role="status">显示 {ah_cnt} / {ah_cnt} 对 A/H 孪生股</strong>
          <span class="sec-sub">点击表头按溢价率排序，或在同一统计期间内按税后息差排序</span>
        </div>
      </div>
      <div class="table-wrap">
        <table class="data-table ah-matrix-table">
          <thead>
            <tr>
              <th>公司与双地代码</th>
              <th>A / H 参考价</th>
              <th class="sortable" data-ah-sort="ah_premium_pct"><button type="button">A/H 溢价率 ⇅</button></th>
              <th class="sortable" data-ah-sort="net_div_spread"><button type="button">A 股免税息 vs 港通税后息 ⇅</button></th>
              <th>价格与股息提示</th>
              <th>深度档案与 K 线</th>
            </tr>
          </thead>
          <tbody id="ah-matrix-tbody">{"".join(ah_static_rows)}</tbody>
        </table>
      </div>
      <div id="ah-matrix-cards" class="ah-mcards"></div>
      <script id="ah-matrix-data" type="application/json">{safe_ah_json}</script>
    </section>

    <div class="dossier-backdrop drawer-modal no-print" id="dossier-modal" role="dialog" aria-modal="true" aria-label="个股 7 维机构深度档案">
      <div class="dossier-dialog">
        <div class="dossier-head">
          <div class="dossier-head-main">
            <h3 class="dossier-title" id="dossier-modal-title">个股 7 维深度档案</h3>
            <div class="dossier-sub" id="dossier-modal-sub"></div>
            <div class="dossier-badges" id="dossier-modal-badges"></div>
          </div>
          <div class="drawer-nav-btns">
            <button type="button" class="ctrl-btn" data-drawer-step="-1" title="上一个 (↑)" aria-label="上一个">↑</button>
            <span class="drawer-pos" data-drawer-pos></span>
            <button type="button" class="ctrl-btn" data-drawer-step="1" title="下一个 (↓)" aria-label="下一个">↓</button>
            <button type="button" class="ctrl-btn" data-action="close-dossier" aria-label="关闭个股深度档案">关闭 ✕</button>
          </div>
        </div>
        <div class="dossier-body" id="dossier-modal-body"></div>
        <div class="dossier-foot">
          <span id="dossier-modal-date" data-default-date="{esc(date_fallback)}">7 维档案刷新日：{esc(date_fallback)}</span>
          <a id="dossier-modal-link" href="reports/a-share.html" class="btn btn-sm">前往该市场全景手册 →</a>
        </div>
      </div>
    </div>

    <script id="screener-data" type="application/json">{safe_json}</script>
    """


def build_guide_page(
    gold_snap: dict[str, Any] | None,
    eq_state: dict[str, Any] | None,
    channels_data: dict[str, Any] | None,
    etf_data: dict[str, Any] | None,
    total_pool: int = 0,
    *,
    kline_manifest: dict[str, Any] | None = None,
) -> str:
    """Render standalone Beginner 3-Minute Guide & Top-48 Financial Terms Page (guide.html)."""
    gs = gold_snap if isinstance(gold_snap, dict) else {}
    es = eq_state if isinstance(eq_state, dict) else {}
    gold_blocked = (gs.get("new_buy_allowed") is False) or (str(gs.get("tier_code") or "").strip() == "Tier 0")
    gold_status_text = (
        "当前黄金处于红灯停阶段：老持仓稳拿不乱卖，新钱先停在稳钱池暂不新买黄金，等待四关信号逐步过关。"
        if gold_blocked
        else "黄金操作须严守家庭资产 10%–15% 上限，按四步信号分批推进、远离杠杆。"
    )
    ch_items = [
        c for c in ((channels_data or {}).get("channels") or [])
        if isinstance(c, dict) and str(c.get("id", "")).strip()
    ]
    ch_cnt = len(ch_items)
    etf_cnt = len((etf_data or {}).get("etfs") or []) if isinstance(etf_data, dict) else 0
    ch_lbl = f"{ch_cnt} 大个人多元渠道" if ch_cnt else "个人多元合规渠道"
    etf_lbl = f"{etf_cnt} 只重点 ETF" if etf_cnt else "全球重点 ETF"

    pitfalls: tuple[tuple[str, str, str, str], ...] = (
        (
            "短钱长投：拿半年内要用的钱冲进股市",
            "把交房租、买车或结婚首付投进高波动股票，急用钱时恰逢下跌被迫低位割肉。",
            "先按「活钱 0–6 月 / 稳钱 1–3 年 / 长钱 3–5 年+」切分账户，3 年内确定要用的钱绝不碰高波动权益。",
            "index.html#sec-four-buckets",
        ),
        (
            "把银行理财「业绩比较基准」当成保本利率",
            "资管新规全面真净值化后，银行理财与固收+基金遇到债市调整同样会阶段性破净。",
            "求本金零波动选储蓄国债或 50 万以内正规银行存款；买理财与债基务必先看底层持仓与历史最大回撤。",
            "channels/funds_wm.html",
        ),
        (
            "场内抢买高溢价跨境 QDII 或商品 LOF",
            "刷热点冲进溢价两位数甚至停牌的纳指 ETF 或白银/原油 LOF，即使底层没跌，溢价回落也会造成大幅亏损。",
            "下单前必看实时参考净值（IOPV），场内溢价超过 2%–3% 坚决不追，优先改用场外联接按净值分批定投。",
            "channels/qdii_mrf.html",
        ),
        (
            "误把 30 年超长国债 ETF 当稳健存款重仓",
            "看到「国债」二字便以为稳赚不赔，全仓买入久期近 20 年的超长国债 ETF，利率微涨即出现 5%–10% 回撤。",
            "稳钱底仓优先选短融 ETF、储蓄国债或中短久期债券 ETF；超长久期国债属高波动对冲工具，严控占比。",
            "channels/bonds.html",
        ),
        (
            "把高速公路 REITs 表面高分派率当成永续股息",
            "特许经营权类 REITs 到期资产无偿移交、净值归零，每年高额分派中混有大量本金归还。",
            "产权类（保租房/商场/算力机房）看分派率与出租率；特许经营权类必须看中债真实内部收益率（IRR）。",
            "channels/c_reits.html",
        ),
        (
            "A/C 类基金选反，或持有不满 7 天硬挨 1.5% 赎回费",
            "短期波段买了高申购费 A 类，或长期持有选了持续扣费的旧合同 C 类，甚至几天内频繁进出触发 1.5% 惩罚费。",
            "按预期持有期比较 A/C 的申购费、销售服务费和赎回费。适用份额持有超过一年后停止继续收取销售服务费，首年费用与短期赎回费用看合同。",
            "channels/funds_wm.html",
        ),
        (
            "忽略港股通 20% 红利税（个别发行人的源头代扣待核）与未锁汇汇率损失",
            "冲着高表面股息买港股通，或用人民币新换汇买未锁汇美元债，标准 H 股 20% 红利税（个别发行人的源头代扣须查分派公告）或人民币升值会压低人民币口径收益。",
            "买港股高股息前先按税后折算真实到手率；内地买香港互认债基认准「人民币对冲 + 累计份额」合法避税锁汇。",
            "etfs.html",
        ),
        (
            "周五借 1 天期逆回购踩空 & 二手存单提前支取实亏",
            "周五做 1 天期逆回购周末两天白闲置；单家银行存超 50 万超出存保上限；二手接盘大额存单提前支取按原票面退还致本金实亏。",
            "周四借 1 天期吃 3 天息，周五闲钱放短融 ETF；单家独立法人银行存款控在 45–47 万内；二手接盘前须先核实发卡行是否允许二次转让（多数国有大行禁止二次转让），仅用能持有到期的闲钱接盘，切忌提前支取导致本金实亏。",
            "channels/large_cds.html",
        ),
    )

    pitfall_cards = "".join(
        f'<article class="pitfall-card">'
        f'<div class="pitfall-top"><span class="pitfall-num">{idx:02d}</span><h3>{esc(title)}</h3></div>'
        f'<p class="pitfall-scene"><strong>常见场景：</strong>{esc(scene)}</p>'
        f'<p class="pitfall-fix"><strong>避坑建议：</strong>{esc(fix)}</p>'
        f'<a class="pitfall-link" href="{esc(href)}">查看对应详规 →</a>'
        f"</article>"
        for idx, (title, scene, fix, href) in enumerate(pitfalls, start=1)
    )

    term_cats: list[str] = []
    for t in GLOSSARY_TERMS:
        if t["cat"] not in term_cats:
            term_cats.append(t["cat"])
    cat_pills = '<button type="button" class="filter-pill active" data-guide-cat="all">全部词条</button>' + "".join(
        f'<button type="button" class="filter-pill" data-guide-cat="{esc(c)}">{esc(c)}</button>'
        for c in term_cats
    )

    term_cards = "".join(
        f'<article class="guide-term-card{" guide-term-hidden" if idx >= 12 else ""}" id="term-{esc(t["key"])}" '
        f'data-guide-term-cat="{esc(t["cat"])}" data-guide-term-search="{esc((t["term"] + " " + t["plain"] + " " + t["avoid"]).lower())}">'
        f'<div class="guide-term-head"><h3>{esc(t["term"])}</h3><span class="guide-term-cat">{esc(t["cat"])}</span></div>'
        f'<p class="guide-term-plain">{esc(t["plain"])}</p>'
        f'<div class="guide-term-avoid">{esc(t["avoid"])}</div>'
        f"</article>"
        for idx, t in enumerate(GLOSSARY_TERMS)
    )
    guide_term_more_html = (
        '<div class="guide-term-more-wrap">'
        f'<button type="button" id="guide-term-more-btn" class="btn btn-sm">展开全部 {len(GLOSSARY_TERMS)} 条核心词典 ▾</button>'
        "</div>"
        if len(GLOSSARY_TERMS) > 12
        else ""
    )

    return f"""
    <section class="guide-hero">
      <div class="exec-top">
        <span class="cover-tag">新手 3 分钟入门指南 · 平等透明投研导航</span>
      </div>
      <div class="exec-main">
        <div class="exec-copy">
          <h1>3 分钟读懂全球投研门户与高频金融关键词</h1>
          <p class="channels-hero-sub">不必背诵复杂金融黑话，按「看懂信号灯与仓位区别 → 钱包一键试算 → 避开 8 大误区 → 速查高频词典」四步节奏，轻松把全站 {esc(ch_lbl)}、{esc(etf_lbl)} 与 {total_pool} 只核心龙头变成清晰好用的决策参考。</p>
        </div>
        <div class="exec-actions">
          <a class="btn btn-primary" href="#sec-guide-glossary">直查 Top {len(GLOSSARY_TERMS)} 关键词 ↓</a>
          <a class="btn" href="index.html">回首页驾驶舱 →</a>
        </div>
      </div>
    </section>

    <nav class="guide-step-bar" aria-label="新手入门四步导航">
      <a class="guide-step-pill" href="#sec-guide-lamps">① 读懂信号灯</a>
      <a class="guide-step-pill" href="#sec-guide-wallet">② 钱包一键试算</a>
      <a class="guide-step-pill" href="#sec-guide-pitfalls">③ 8 大避坑</a>
      <a class="guide-step-pill" href="#sec-guide-glossary">④ Top {len(GLOSSARY_TERMS)} 词典</a>
    </nav>

    <div class="sec-head" id="sec-guide-lamps" style="margin-top:8px;">
      <h2>① 1 分钟看懂本站「四档信号灯」与每日 3 分钟动线</h2>
      <span class="sec-sub">信号灯是帮你管住手的仓位安全阀，绝非情绪化喊单</span>
    </div>
    <div class="guide-stance-clarify">
      <strong>⚠️ 必读区分：「股票防守建底期（上限 ≤40%）」≠「黄金红灯停（新仓严格 0%）」</strong>
      <p>股票市场亮红灯防守时，仍允许空仓或低仓者按安全锚分批建立防弹衣底座（严守总股仓上限 ≤35%–40%、不追高）；而黄金若处于红灯停阶段，则是新仓严格 0% 暂不新买（老持仓稳拿不乱割），两类规则切勿混淆。</p>
    </div>
    <section class="guide-lamp-grid guide-lamp-grid-4">
      <div class="guide-lamp-card gl-green">
        <span class="lamp-pill lamp-green"><span class="lamp-dot"></span>绿灯进取 · 条件齐备</span>
        <h3>性价比划算，按计划分批配置</h3>
        <p>说明该市场的估值安全边际、利率环境与趋势条件同步达标，可把对应期限的长钱分 3–4 批稳步建仓。</p>
      </div>
      <div class="guide-lamp-card gl-amber">
        <span class="lamp-pill lamp-amber"><span class="lamp-dot"></span>黄灯均衡 · 分歧观察</span>
        <h3>多空拉锯，小步按锚不追高</h3>
        <p>说明机会与风险并存，仅在回落至关键安全锚附近小额分批，严禁看到单日大涨就冲动追买。</p>
      </div>
      <div class="guide-lamp-card gl-defend">
        <span class="lamp-pill lamp-defend"><span class="lamp-dot"></span>琥珀防守建底 · 股票上限 ≤40%</span>
        <h3>空仓可分批建底，严守仓位红线</h3>
        <p>对应首页三市股票红灯防守期：不恐慌清仓、不追情绪脉冲，低仓者仅按安全锚分批建低费红利与防弹衣底座。</p>
      </div>
      <div class="guide-lamp-card gl-red">
        <span class="lamp-pill lamp-red"><span class="lamp-dot"></span>猩红熔断停 · 黄金新仓 0%</span>
        <h3>老底仓稳拿不乱割，新钱暂泊稳钱池</h3>
        <p>硬止损级新仓门控：不抢跑、不抄底，严防在真实利率压制与高波动半山腰误入。{esc(gold_status_text)}</p>
      </div>
    </section>

    <div class="panel-card guide-roadmap">
      <div class="panel-title">
        <span>🧭 每日 3 分钟标准阅读动线（推荐收藏）</span>
        <a class="btn btn-sm" href="index.html">前往首页驾驶舱 →</a>
      </div>
      <div class="ch-steps-grid">
        <div class="ch-step-card">
          <div class="ch-step-num">第 1 分钟</div>
          <div class="ch-step-title">看首页大势与今日行动红绿灯</div>
          <div class="ch-step-detail">扫一眼六大核心与卫星市场红绿灯和「今天可以做 / 今天先别碰」，立刻掌握当日大方向与禁区。</div>
        </div>
        <div class="ch-step-card">
          <div class="ch-step-num">第 2 分钟</div>
          <div class="ch-step-title">按用钱时间挑合规渠道</div>
          <div class="ch-step-detail">点开「四笔钱」或 {esc(ch_lbl)}，点进对应渠道的独立 1 分钟指南页，核对 3 步买法、税费和起投门槛。</div>
        </div>
        <div class="ch-step-card">
          <div class="ch-step-num">第 3 分钟</div>
          <div class="ch-step-title">查 ETF 溢价与 7 维深度档案</div>
          <div class="ch-step-detail">下单前在 ETF 雷达核对折溢价和低费替身，需要深入研究龙头公司时打开 {total_pool} 股 7 维筛选器。</div>
        </div>
      </div>
    </div>

    <div class="sec-head" id="sec-guide-wallet">
      <h2>② 我的钱包一键试算（直连今日红绿灯）</h2>
      <span class="sec-sub">输入可投资闲钱与风险偏好，按四笔钱与风控硬规则实时拆算落地方案</span>
    </div>
    {_render_wallet_calculator(gs, es, kline_manifest)}

    <div class="sec-head" id="sec-guide-pitfalls">
      <h2>③ 新手最常踩的 8 大真实避坑清单</h2>
      <span class="sec-sub">避开这 8 个常见误区，就能守住绝大部分本金与收益</span>
    </div>
    <section class="pitfall-grid">{pitfall_cards}</section>

    <div class="sec-head" id="sec-guide-glossary">
      <h2>④ Top {len(GLOSSARY_TERMS)} 高频金融关键词白话速查</h2>
      <strong id="guide-term-count" class="sec-sub" role="status">共 {len(GLOSSARY_TERMS)} 个高频词条</strong>
    </div>
    <section class="filter-panel">
      <div class="filter-row">
        <div class="search-wrap">
          <input type="search" id="guide-term-search" class="search-input" placeholder="输入关键词实时搜索（如 溢价、久期、红利税、ERP、逆回购、破净）…" autocomplete="off">
          <button type="button" id="guide-term-clear" class="search-clear" aria-label="清空词条搜索" hidden>×</button>
        </div>
        <button type="button" class="btn btn-sm" id="guide-term-reset">重置</button>
      </div>
      <div class="filter-row">{cat_pills}</div>
    </section>
    <section class="guide-term-grid" id="guide-term-grid">{term_cards}</section>
    {guide_term_more_html}
    <div class="panel-card empty-state guide-empty" id="guide-term-empty" hidden>
      <div class="empty-title">未找到匹配的金融词条</div>
      <div class="empty-sub">换个简短关键词试试，或点击下方按钮查看全部词条。</div>
      <button type="button" class="btn btn-sm" id="guide-empty-reset">显示全部词条</button>
    </div>
    """


def _first_int(text: str, default: int = 0) -> int:
    m = re.search(r"(\d+)", str(text or ""))
    return int(m.group(1)) if m else default


def _first_pct(text: str, default: float | None = None) -> float | None:
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)%", str(text or ""))
    return float(m.group(1)) if m else default


def parse_scorecard_stats(gold_sc_md: str, eq_sc_md: str) -> dict[str, dict[str, Any]]:
    """Extract settled/hit/partial/miss/tracking statistics from Gold & Equity SCORECARD.md files."""
    # --- Gold SCORECARD.md (supports reconciled investment-only summary & optional ops-record column) ---
    g_settled = g_scored = g_hit = g_partial = g_miss = g_untrig = g_track = 0
    g_full_pct: float | None = None
    g_part_pct: float | None = None
    col_idx: dict[str, int] = {}
    for raw in (gold_sc_md or "").splitlines():
        st = raw.strip()
        if not (st.startswith("|") and st.endswith("|")):
            continue
        cells = _split_md_cells(st)
        if len(cells) >= 8 and ("统计口径" in cells[0] or ("兑现" in " ".join(cells) and "证伪" in " ".join(cells))):
            for idx_c, hdr in enumerate(cells):
                if "至少部分" in hdr:
                    col_idx["part_pct"] = idx_c
                elif "完全兑现" in hdr:
                    col_idx["full_pct"] = idx_c
                elif "部分兑现" in hdr and "率" not in hdr and "至少" not in hdr and "评分" not in hdr:
                    col_idx["partial"] = idx_c
                elif "兑现" in hdr and "部分" not in hdr and "率" not in hdr and "评分" not in hdr:
                    col_idx["hit"] = idx_c
                elif "证伪" in hdr:
                    col_idx["miss"] = idx_c
                elif "未触发" in hdr:
                    col_idx["untrig"] = idx_c
            continue
        if len(cells) >= 8 and "已到期" in cells[0]:
            g_settled = _first_int(cells[1])
            m_sc = re.search(r"(?:投资)?计分\s*(\d+)", cells[1])
            g_hit = _first_int(cells[col_idx.get("hit", 2)])
            g_partial = _first_int(cells[col_idx.get("partial", 3)])
            g_miss = _first_int(cells[col_idx.get("miss", 4)])
            g_untrig = _first_int(cells[col_idx.get("untrig", 5)])
            g_scored = int(m_sc.group(1)) if m_sc else (g_hit + g_partial + g_miss)
            g_full_pct = _first_pct(cells[col_idx.get("full_pct", len(cells) - 2)])
            g_part_pct = _first_pct(cells[col_idx.get("part_pct", len(cells) - 1)])
        elif len(cells) >= 2 and "持续追踪" in cells[0]:
            g_track = _first_int(cells[1])
    if g_scored == 0 and (g_hit + g_partial + g_miss) > 0:
        g_scored = g_hit + g_partial + g_miss
    if g_part_pct is None:
        g_part_pct = round(((g_hit + g_partial) / g_scored) * 100.0, 1) if g_scored > 0 else 0.0
    if g_full_pct is None:
        g_full_pct = round((g_hit / g_scored) * 100.0, 1) if g_scored > 0 else 0.0

    # --- Equity SCORECARD.md ---
    e_settled = e_hit = e_partial = e_miss = e_untrig = e_track = 0
    m_eq = re.search(
        r"已到期\s*(\d+)\s*项[（(][^）)]*兑现\s*(\d+)[^）)]*部分兑现\s*(\d+)[^）)]*证伪\s*(\d+)[^）)]*未触发\s*(\d+)[）)][，,、\s]*持续追踪\s*(\d+)\s*项",
        eq_sc_md or "",
    )
    if m_eq:
        e_settled = int(m_eq.group(1))
        e_hit = int(m_eq.group(2))
        e_partial = int(m_eq.group(3))
        e_miss = int(m_eq.group(4))
        e_untrig = int(m_eq.group(5))
        e_track = int(m_eq.group(6))
    else:
        for raw in (eq_sc_md or "").splitlines():
            st = raw.strip()
            if not (st.startswith("|") and st.endswith("|")):
                continue
            if "✅ 兑现" in st:
                e_hit += 1
            elif "⚠️ 部分兑现" in st:
                e_partial += 1
            elif "❌ 证伪" in st:
                e_miss += 1
            elif "条件未触发" in st:
                e_untrig += 1
            elif "⏳" in st:
                e_track += 1
        e_settled = e_hit + e_partial + e_miss + e_untrig
    e_scored = e_hit + e_partial + e_miss
    e_part_pct = round(((e_hit + e_partial) / e_scored) * 100.0, 1) if e_scored > 0 else 0.0
    e_full_pct = round((e_hit / e_scored) * 100.0, 1) if e_scored > 0 else 0.0

    return {
        "gold": {
            "settled": g_settled,
            "scored": g_scored,
            "hit": g_hit,
            "partial": g_partial,
            "miss": g_miss,
            "untriggered": g_untrig,
            "tracking": g_track,
            "full_pct": g_full_pct,
            "at_least_partial_pct": g_part_pct,
        },
        "equity": {
            "settled": e_settled,
            "scored": e_scored,
            "hit": e_hit,
            "partial": e_partial,
            "miss": e_miss,
            "untriggered": e_untrig,
            "tracking": e_track,
            "full_pct": e_full_pct,
            "at_least_partial_pct": e_part_pct,
        },
    }


def _render_ring_svg(pct: float, accent_cls: str, label: str) -> str:
    """Render compact decorative circular gauge SVG (viewBox W=64 < 100, Gate S4 compliant)."""
    clamped = max(0.0, min(100.0, float(pct)))
    circ = 157.08  # 2 * pi * 25
    offset = circ * (1.0 - clamped / 100.0)
    return (
        f'<svg class="ring-svg {esc(accent_cls)}" viewBox="0 0 64 64" width="58" height="58" aria-hidden="true">'
        '<circle class="ring-track" cx="32" cy="32" r="25" fill="none" stroke-width="6"/>'
        f'<circle class="ring-fill" cx="32" cy="32" r="25" fill="none" stroke-width="6" '
        f'stroke-dasharray="{circ:.1f}" stroke-dashoffset="{offset:.1f}" transform="rotate(-90 32 32)"/>'
        f'<text class="ring-val" x="32" y="32" text-anchor="middle">{esc(label)}</text>'
        "</svg>"
    )


def _load_gold_ledger_with_archives(stem: str, *, is_audit_log: bool) -> str:
    """Load active gold ledger plus any monthly archived files (newest month first), sanitized."""
    active_path = GOLD_DIR / "daily" / f"{stem}.md"
    parts = [
        sanitize_public_ledger_md(
            active_path.read_text(encoding="utf-8"),
            is_audit_log=is_audit_log,
        ).strip()
    ]
    archive_dir = GOLD_DIR / "daily" / "archive"
    if archive_dir.is_dir():
        for arch_path in sorted(archive_dir.rglob(f"{stem}_*.md"), key=lambda p: p.name, reverse=True):
            sanitized = sanitize_public_ledger_md(
                arch_path.read_text(encoding="utf-8"),
                is_audit_log=is_audit_log,
            ).strip()
            if sanitized:
                parts.append(sanitized)
    return "\n\n---\n\n".join(p for p in parts if p)


def _load_equity_ledger_with_archives(stem: str) -> str:
    """Load active equity ledger plus any monthly archived files (newest month first), sanitized."""
    active_path = EQUITY_DIR / "daily" / f"{stem}.md"
    parts = [
        sanitize_public_ledger_md(
            active_path.read_text(encoding="utf-8"),
            is_audit_log=False,
        ).strip()
    ]
    archive_dir = EQUITY_DIR / "daily" / "archive"
    if archive_dir.is_dir():
        for arch_path in sorted(archive_dir.rglob(f"{stem}_*.md"), key=lambda p: p.name, reverse=True):
            sanitized = sanitize_public_ledger_md(
                arch_path.read_text(encoding="utf-8"),
                is_audit_log=False,
            ).strip()
            if sanitized:
                parts.append(sanitized)
    return "\n\n---\n\n".join(p for p in parts if p)


def build_scorecard_page(
    R: Renderers,
    slug_map: dict[str, str],
    gold_snap: dict | None = None,
) -> str:
    eq_sc_raw_md = (EQUITY_DIR / "daily" / "SCORECARD.md").read_text(encoding="utf-8")
    gd_sc_raw_md = (GOLD_DIR / "daily" / "SCORECARD.md").read_text(encoding="utf-8")
    sc_stats = parse_scorecard_stats(gd_sc_raw_md, eq_sc_raw_md)
    eq_st = sc_stats["equity"]
    gd_st = sc_stats["gold"]

    trust = (gold_snap or {}).get("trust_assets") or {}
    myths_blocked = _first_int(trust.get("myths_blocked"), 0)
    model_upgrades = _first_int(trust.get("model_upgrades"), 0)
    minor_corr = _first_int(trust.get("minor_corrections"), 0)
    minor_impact = str(trust.get("minor_impact_on_core_verdict") or f"0 / {minor_corr}")

    eq_ring_lbl = f'{eq_st["at_least_partial_pct"]:.0f}%'
    gd_ring_lbl = f'{gd_st["at_least_partial_pct"]:.0f}%'

    eq_sc_md = normalize_relative_md_links(_clean_soft_filenames(_strip_scorecard_top_nav(eq_sc_raw_md)))
    gd_sc_md = normalize_relative_md_links(
        protect_backticked_comments(_clean_soft_filenames(_strip_scorecard_top_nav(gd_sc_raw_md)))
    )
    eq_cl_md = normalize_relative_md_links(
        _clean_soft_filenames(_strip_scorecard_top_nav(_load_equity_ledger_with_archives("CHANGELOG")))
    )
    gd_cl_md = normalize_relative_md_links(
        protect_backticked_comments(
            _clean_soft_filenames(
                _strip_scorecard_top_nav(_load_gold_ledger_with_archives("CHANGELOG", is_audit_log=False))
            )
        )
    )
    gd_al_md = normalize_relative_md_links(
        protect_backticked_comments(
            _clean_soft_filenames(
                _strip_scorecard_top_nav(_load_gold_ledger_with_archives("AUDIT_LOG", is_audit_log=True))
            )
        )
    )

    _, eq_sc_raw = R.eq_pdf_common.render_md_body(eq_sc_md, {}, default_title="全球股市记分卡")
    _, _, gd_sc_raw, _ = R.gold_daily.parse_markdown_to_html(gd_sc_md, docx_mode=False)
    _, eq_cl_raw = R.eq_pdf_common.render_md_body(eq_cl_md, {}, default_title="股市观点演进")
    _, _, gd_cl_raw, _ = R.gold_daily.parse_markdown_to_html(gd_cl_md, docx_mode=False)
    _, _, gd_al_raw, _ = R.gold_daily.parse_markdown_to_html(gd_al_md, docx_mode=False)

    eq_sc_html, _, _ = sanitize_and_extract_toc(eq_sc_raw, base_prefix="", slug_map=slug_map, ctx_market="a-share", extract_toc=False, id_prefix="eq-sc-")
    gd_sc_html, _, _ = sanitize_and_extract_toc(gd_sc_raw, base_prefix="", slug_map=slug_map, ctx_market="gold", extract_toc=False, id_prefix="gd-sc-")
    eq_cl_html, _, _ = sanitize_and_extract_toc(eq_cl_raw, base_prefix="", slug_map=slug_map, ctx_market="a-share", extract_toc=False, id_prefix="eq-cl-")
    gd_cl_html, _, _ = sanitize_and_extract_toc(gd_cl_raw, base_prefix="", slug_map=slug_map, ctx_market="gold", extract_toc=False, id_prefix="gd-cl-")
    gd_al_html, _, _ = sanitize_and_extract_toc(gd_al_raw, base_prefix="", slug_map=slug_map, ctx_market="gold", extract_toc=False, id_prefix="gd-al-")

    def _demote_embedded_h1(frag: str) -> str:
        return re.sub(r"<(/?)h1(\b[^>]*)>", r"<\1h2\2>", frag, flags=re.IGNORECASE)

    def _normalize_scorecard_outcome_cells(frag: str) -> str:
        """Unify outcome cells in Equity & Gold scorecard tables into uniform .st-pill badges."""
        def _repl(m: re.Match[str]) -> str:
            attrs, inner = m.group(1), m.group(2)
            plain = re.sub(r"\s+", " ", html_mod.unescape(strip_tags(inner))).strip()
            if not plain or len(plain) > 22:
                return m.group(0)
            if re.fullmatch(r"(?:[✓✅✔]|是)?\s*兑现", plain):
                return f'<td{attrs}><span class="st-pill st-pass">✓ 兑现</span></td>'
            if re.fullmatch(r"(?:[!⚠⚠️])?\s*部分兑现", plain):
                return f'<td{attrs}><span class="st-pill st-warn">! 部分兑现</span></td>'
            if re.fullmatch(r"(?:[×✕❌])?\s*证伪", plain):
                return f'<td{attrs}><span class="st-pill st-fail">× 证伪</span></td>'
            if re.fullmatch(r"(?:[⚪○])?\s*条件未触发", plain):
                return f'<td{attrs}><span class="st-pill vt-wait">条件未触发</span></td>'
            if re.fullmatch(r"(?:[⚪○])?\s*运维记录(?:[（(][^）)]{1,10}[）)])?", plain):
                clean_lbl = re.sub(r"^[⚪○\s]+", "", plain)
                return f'<td{attrs}><span class="st-pill vt-wait">{esc(clean_lbl)}</span></td>'
            if re.fullmatch(r"(?:[⏳…待])*\s*(?:待验真|持续追踪|追踪中)", plain):
                return f'<td{attrs}><span class="st-pill vt-wait">追踪中</span></td>'
            return m.group(0)

        return re.sub(r"<td([^>]*)>(.*?)</td>", _repl, frag, flags=re.DOTALL | re.IGNORECASE)

    eq_sc_html = _normalize_scorecard_outcome_cells(_demote_embedded_h1(eq_sc_html))
    gd_sc_html = _normalize_scorecard_outcome_cells(_demote_embedded_h1(gd_sc_html))
    eq_cl_html = _demote_embedded_h1(eq_cl_html)
    gd_cl_html = _demote_embedded_h1(gd_cl_html)
    gd_al_html = _demote_embedded_h1(gd_al_html)

    return f"""
    <div class="sec-head" style="margin-top:4px;">
      <h1>公开可证伪预测记分卡与观点演进账本</h1>
      <span class="sec-sub">对就写对、偏就写偏、错就公开认错，绝不事后涂改旧账</span>
    </div>

    <section class="sc-summary-grid" aria-label="双轨可证伪回验核心统计">
      <div class="sc-stat-card">
        <div class="sc-stat-head">
          <div class="sc-stat-title">全球股市记分卡</div>
          <div class="sc-stat-sub">已评分至少部分兑现率</div>
        </div>
        <div class="sc-stat-body">
          {_render_ring_svg(eq_st["at_least_partial_pct"], "ring-eq", eq_ring_lbl)}
          <div class="sc-stat-meta">
            <div>已到期 {eq_st["settled"]} 项（计分 {eq_st["scored"]} 项 · 完全兑现 {eq_st["full_pct"]:.1f}%）</div>
            <div>兑现 {eq_st["hit"]} · 部分 {eq_st["partial"]} · 证伪 {eq_st["miss"]} · 追踪中 {eq_st["tracking"]} 项</div>
          </div>
        </div>
      </div>

      <div class="sc-stat-card">
        <div class="sc-stat-head">
          <div class="sc-stat-title">黄金深度记分卡</div>
          <div class="sc-stat-sub">已评分至少部分兑现率</div>
        </div>
        <div class="sc-stat-body">
          {_render_ring_svg(gd_st["at_least_partial_pct"], "ring-gold", gd_ring_lbl)}
          <div class="sc-stat-meta">
            <div>已到期 {gd_st["settled"]} 项（计分 {gd_st["scored"]} 项 · 完全兑现 {gd_st["full_pct"]:.1f}%）</div>
            <div>兑现 {gd_st["hit"]} · 部分 {gd_st["partial"]} · 证伪 {gd_st["miss"]} · 追踪中 {gd_st["tracking"]} 项</div>
          </div>
        </div>
      </div>

      <div class="sc-stat-card">
        <div class="sc-stat-head">
          <div class="sc-stat-title">谣言拦截与模型升级</div>
          <div class="sc-stat-sub">一手官源交叉对抗沉淀</div>
        </div>
        <div class="sc-stat-body">
          <div class="sc-stat-big">{myths_blocked} 条 / {model_upgrades} 次</div>
          <div class="sc-stat-meta">累计证伪市场失实传闻 {myths_blocked} 条 · 量化与风控模型升级 {model_upgrades} 次</div>
        </div>
      </div>

      <div class="sc-stat-card">
        <div class="sc-stat-head">
          <div class="sc-stat-title">细节勘误与核心裁决</div>
          <div class="sc-stat-sub">动摇仓位方向占比</div>
        </div>
        <div class="sc-stat-body">
          <div class="sc-stat-big">{esc(minor_impact)}</div>
          <div class="sc-stat-meta">公开透明修正次级细节 {minor_corr} 笔 · 核心红绿灯与仓位红线零摇摆</div>
        </div>
      </div>
    </section>

    <div class="transparency-pledge">
      <div class="pledge-title">公开可证伪与准时发刊透明承诺</div>
      <p class="pledge-text">每期预测一经发刊即锁定原时间、原价格与客观判据，到期仅填实盘官方结果、永不涂改历史；遇跨时区官库尚未更新或次级数据暂缺，一律按规则留空或暂采官网收盘并公开挂账核销，绝不估算造数。</p>
    </div>

    <div class="tab-bar no-print" role="tablist">
      <button type="button" class="tab-btn active" role="tab" aria-selected="true" data-tab-target="equity-scorecard">📈 全球股市记分卡</button>
      <button type="button" class="tab-btn" role="tab" aria-selected="false" data-tab-target="gold-scorecard">🥇 黄金记分卡</button>
      <button type="button" class="tab-btn" role="tab" aria-selected="false" data-tab-target="equity-changelog">🧭 股市观点演进</button>
      <button type="button" class="tab-btn" role="tab" aria-selected="false" data-tab-target="gold-changelog">📜 黄金观点演进</button>
      <button type="button" class="tab-btn" role="tab" aria-selected="false" data-tab-target="gold-audit-log">🛡️ 黄金辟谣核查账本</button>
    </div>

    <div class="sc-search-bar no-print">
      <div class="search-wrap">
        <input type="search" id="sc-search" class="search-input" placeholder="输入关键词过滤日期、标的或辟谣（如 2026-11、紫金、黄金、谣言）…" autocomplete="off">
        <button type="button" id="sc-clear" class="search-clear" aria-label="清空记分卡搜索" hidden>×</button>
        <kbd class="kbd-hint" aria-hidden="true">/</kbd>
      </div>
      <span id="sc-filter-status" class="sc-filter-status" role="status"></span>
    </div>

    <section id="equity-scorecard" class="tab-panel active article-card">
      <div class="article-body">{eq_sc_html}</div>
    </section>
    <section id="gold-scorecard" class="tab-panel article-card">
      <div class="article-body">{gd_sc_html}</div>
    </section>
    <section id="equity-changelog" class="tab-panel article-card timeline-ledger">
      <div class="article-body">{eq_cl_html}</div>
    </section>
    <section id="gold-changelog" class="tab-panel article-card timeline-ledger">
      <div class="article-body">{gd_cl_html}</div>
    </section>
    <section id="gold-audit-log" class="tab-panel article-card">
      <div class="article-body">{gd_al_html}</div>
    </section>
    """


def build_archive_page(
    dailies: list[DailyItem],
    flagship_info: list[dict[str, str]],
    stock_counts: dict[str, int],
    total_pool: int,
    total_flagship_charts: int,
) -> str:
    shelf_html = ""
    for fl in flagship_info:
        mk = fl["market"]
        mm = MARKET_META[mk]
        shelf_html += (
            f'<div class="flagship-tile" style="--tile-accent:{fl["accent"]};">'
            '<div class="ft-spine"></div>'
            '<div class="ft-body">'
            f'<div class="feed-meta"><span class="mkt-badge mkt-{mk}">{fl["badge"]}</span>'
            f'<span class="session-pill">{esc(fl["charts"])} 张矢量图</span></div>'
            f'<div class="ft-title"><a href="{fl["href"]}">{esc(fl["title"])}</a></div>'
            f'<div class="ft-meta">数据基线：{esc(fl["baseline"])}</div>'
            '<div class="ft-actions">'
            f'<a class="dl-link dl-badge-web" href="{fl["href"]}">在线阅读手册 →</a>'
            f'<a class="btn btn-sm" href="{mm["latest_href"]}">最新日报</a>'
            "</div></div></div>"
        )

    by_date: dict[str, list[DailyItem]] = defaultdict(list)
    max_rev_by_slot: dict[tuple[str, str, str], int] = {}
    for it in dailies:
        by_date[it.date_str].append(it)
        slot_key = (it.date_str, it.market, it.hhmm)
        if it.rev > max_rev_by_slot.get(slot_key, 0):
            max_rev_by_slot[slot_key] = it.rev

    superseded_count = 0
    active_count = 0
    timeline_html = ""
    for dt in sorted(by_date.keys(), reverse=True):
        day_items = sorted(
            by_date[dt],
            key=lambda x: (-int(x.hhmm), -x.rev, MARKET_ORDER.get(x.market, 9)),
        )
        cards = []
        day_active = 0
        for it in day_items:
            mm = MARKET_META[it.market]
            is_superseded = it.rev < max_rev_by_slot[(it.date_str, it.market, it.hhmm)]
            if is_superseded:
                superseded_count += 1
            else:
                active_count += 1
                day_active += 1
            chart_badge = f'<span class="session-pill">{it.chart_count} 图</span>' if it.chart_count else ""
            revision_badge = f'<span class="session-pill">修订 {it.rev}</span>' if it.rev > 1 else ""
            old_badge = '<span class="session-pill arc-old-badge">修订前原版</span>' if is_superseded else ""
            sup_attrs = ' data-superseded="1" hidden' if is_superseded else ""
            search_text = f"{it.date_str} {mm['short']} {it.session_label} {it.title} {it.summary}".lower()
            arc_session_key = it.session_key
            cards.append(
                f'<a class="feed-card" href="{it.rel_url}" data-arc-item="1" '
                f'data-market="{it.market}" data-session="{arc_session_key}" '
                f'data-edition-type="{esc(it.edition_type)}" data-search="{esc(search_text)}"{sup_attrs}>'
                f'<div class="feed-meta">'
                f'<span class="mkt-badge mkt-{it.market}">{mm["emoji"]} {mm["short"]}</span>'
                f'{_edition_pill_html(it.edition_type)}'
                f'<span class="session-pill">{esc(it.session_label)}</span>'
                f"{revision_badge}"
                f"{old_badge}"
                f"{chart_badge}"
                f'<span class="session-pill">约 {it.read_minutes} 分钟</span>'
                f"</div>"
                f'<div class="feed-title">{esc(it.title)}</div>'
                f'<div class="feed-summary">{esc(it.summary)}</div>'
                f"</a>"
            )
        timeline_html += (
            f'<div class="archive-day">'
            f'<div class="archive-date-hdr">{esc(dt)} <span class="sec-sub arc-day-cnt">（共 {day_active} 期）</span></div>'
            f'<div class="archive-list">{"".join(cards)}</div>'
            f"</div>"
        )

    rev_toggle_html = (
        '<label class="arc-rev-toggle">'
        '<input type="checkbox" id="arc-show-superseded">'
        f'<span>显示修订前原版（{superseded_count} 期）</span>'
        "</label>"
        if superseded_count > 0
        else ""
    )

    return f"""
    <div class="sec-head" style="margin-top:4px;">
      <h1>四大常青旗舰全景手册</h1>
      <span class="sec-sub">{total_flagship_charts} 张原创矢量图表 · 随时查阅宏观框架与 {total_pool} 只龙头全诊断</span>
    </div>
    <section class="flagship-shelf">{shelf_html}</section>

    <div class="sec-head">
      <h2>历史早午晚报时间轴</h2>
      <strong id="arc-count" class="sec-sub">共展示 {active_count} 期历史日报</strong>
    </div>

    <section class="filter-panel">
      <div class="arc-search-row">
        <div class="search-wrap">
          <input type="search" id="arc-search" class="search-input" placeholder="搜索历史早午晚报标题、日期或关键词（如 感恩节、核心通胀、两融、红灯）…" autocomplete="off">
          <button type="button" id="arc-clear-x" class="search-clear" aria-label="清空搜索" hidden>×</button>
          <kbd class="kbd-hint" aria-hidden="true">/</kbd>
        </div>
        <button type="button" class="btn btn-sm" id="arc-reset">重置筛选</button>
      </div>
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-arc-market="all">全部市场</button>
        <button type="button" class="filter-pill" id="gold" data-arc-market="gold">🥇 黄金</button>
        <button type="button" class="filter-pill" id="a-share" data-arc-market="a-share">🇨🇳 A股</button>
        <button type="button" class="filter-pill" id="hk-stock" data-arc-market="hk-stock">🇭🇰 港股</button>
        <button type="button" class="filter-pill" id="us-stock" data-arc-market="us-stock">🇺🇸 美股</button>
      </div>
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-arc-session="all">全部时段</button>
        <button type="button" class="filter-pill" data-arc-session="morning">早报 (07:30)</button>
        <button type="button" class="filter-pill" data-arc-session="midday">午报 (11:30)</button>
        <button type="button" class="filter-pill" data-arc-session="evening">晚报 (18:00)</button>
      </div>
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-arc-type="all">全部刊型</button>
        <button type="button" class="filter-pill" data-arc-type="main">深度主刊</button>
        <button type="button" class="filter-pill" data-arc-type="watch">守望 / 轻刊</button>
        {rev_toggle_html}
      </div>
    </section>

    <section class="archive-rail">{timeline_html}</section>

    <div class="empty-state" id="arc-empty" hidden>
      <div class="empty-title">未找到匹配的历史早午晚报</div>
      <div class="empty-sub">请尝试清空搜索词，或放宽市场、时段与刊型筛选条件。</div>
      <button type="button" class="btn btn-sm" id="arc-empty-reset">重置全部筛选</button>
    </div>
    """


# ==============================================================================
# 7. MAIN BUILD ORCHESTRATION
# ==============================================================================

def _extract_summary_from_daily(md_text: str, meta: dict | None, is_gold: bool) -> str:
    if is_gold:
        m = re.search(r"<!--\s*DAILY_VERDICT\s*(\{.*?\})\s*-->", md_text, flags=re.DOTALL)
        if m:
            try:
                v = json.loads(m.group(1))
                if v.get("headline"):
                    return clean_md_inline_plain(v["headline"])
            except Exception:
                pass
        if meta and meta.get("summary"):
            return clean_md_inline_plain(meta["summary"])
    else:
        lines = md_text.splitlines()
        # Priority 1: explicit lead conclusion blockquotes (3 分钟速读结论 / 30 秒结论 / 一句话结论 / 核心结论)
        for ln in lines[:40]:
            st = ln.strip()
            if st.startswith(">") and re.search(r"(?:3\s*分钟速读结论|30\s*秒[^：:\n]{0,8}结论|一句话结论|核心结论)", st):
                cleaned = re.sub(r"^>\s*(?:\*\*[^*]{1,28}\*\*|[^：:]{1,22})\s*[：:]\s*", "", st)
                plain = clean_md_inline_plain(cleaned)
                if plain:
                    return plain
        # Priority 2: session overview blockquote (日终总纲 / 早间总纲 / 午间总纲 / 晚间总纲)
        for ln in lines[:40]:
            st = ln.strip()
            if st.startswith(">") and re.search(r"(?:日终|早间|午间|晚间|今日)总纲", st):
                cleaned = re.sub(r"^>\s*(?:\*\*[^*]{1,24}\*\*|[^：:]{1,16})\s*[：:]\s*", "", st)
                plain = clean_md_inline_plain(cleaned)
                if plain:
                    return plain
        # Priority 3: first substantive lead summary paragraph before methodology fallback
        for ln in lines[:60]:
            st = ln.strip()
            if (
                not st
                or st.startswith(("#", ">", "|", "-", "*", "<!--", "---", "```"))
                or re.match(r"^\d+\.\s+", st)
            ):
                continue
            plain = clean_md_inline_plain(st)
            if len(plain) >= 24:
                return plain if len(plain) <= 130 else plain[:129].rstrip(" ，,；;：:") + "…"
        if meta and meta.get("methodology"):
            return clean_md_inline_plain(meta["methodology"])
    return "点击阅读完整深度研报与多维度量化数据图表。"


def build_site(out_dir: Path) -> dict[str, Any]:
    """Build a complete tree before replacing the last usable preview."""
    out_dir = out_dir.resolve()
    protected = (GOLD_DIR, EQUITY_DIR, SCRIPT_DIR, REPO_ROOT / "automations",
                 REPO_ROOT / ".git", REPO_ROOT / ".github", REPO_ROOT / ".agents")
    if REPO_ROOT.is_relative_to(out_dir) or any(out_dir.is_relative_to(p) for p in protected):
        raise ValueError(f"Refusing to build over repository sources: {out_dir}")
    if out_dir.exists() and not out_dir.is_dir():
        raise ValueError(f"Output is not a directory: {out_dir}")

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{out_dir.name}-build-", dir=out_dir.parent) as scratch:
        staging = Path(scratch) / "new"
        with state_read_lock(REPO_ROOT):
            summary = _render_site(staging)
        previous = Path(scratch) / "previous"
        if out_dir.exists():
            os.replace(out_dir, previous)
        try:
            os.replace(staging, out_dir)
        except BaseException:
            if previous.exists():
                os.replace(previous, out_dir)
            raise
    summary["out_dir"] = str(out_dir)
    return summary


def _render_site(out_dir: Path) -> dict[str, Any]:
    R = load_renderers()

    # Load SSOT JSONs (read-only)
    gold_snap = json.loads((GOLD_DIR / "data_snapshot.json").read_text(encoding="utf-8"))
    eq_state = load_research_json((EQUITY_DIR / "state" / "market_state.json").read_text(encoding="utf-8"))
    eq_as_of_disp = fmt_cst_iso(str(eq_state.get("as_of_cst", "")))
    channels_path = EQUITY_DIR / "state" / "multi_asset_channels.json"
    etf_path = EQUITY_DIR / "state" / "etf_universe.json"
    dossiers_path = EQUITY_DIR / "state" / "deep_dossiers.json"
    policy_cal_path = EQUITY_DIR / "state" / "policy_calendar.json"
    channels_data = load_research_json(channels_path.read_text(encoding="utf-8")) if channels_path.is_file() else None
    etf_data = load_research_json(etf_path.read_text(encoding="utf-8")) if etf_path.is_file() else None
    dossiers_data = load_research_json(dossiers_path.read_text(encoding="utf-8")) if dossiers_path.is_file() else None
    policy_calendar_data: dict[str, Any] | None = None
    if policy_cal_path.is_file():
        try:
            raw_pc = json.loads(policy_cal_path.read_text(encoding="utf-8"))
            if isinstance(raw_pc, dict):
                policy_calendar_data = raw_pc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            policy_calendar_data = None

    all_chs: list[dict[str, Any]] = (
        [c for c in (channels_data.get("channels") or []) if isinstance(c, dict) and str(c.get("id", "")).strip()]
        if isinstance(channels_data, dict)
        else []
    )
    ch_total = len(all_chs)
    etf_total = len((etf_data or {}).get("etfs") or []) if isinstance(etf_data, dict) else 0
    default_dossier_date = (
        str((dossiers_data or {}).get("as_of_date") or "").strip()
        or str(eq_state.get("as_of_cst") or "").strip()[:10]
        or "最新班次"
    )

    # Pre-load equity flagship metadata & markdowns (with defensive rollover fallback)
    # so dynamic stock pool counts are known before building manifest, navs & reports.
    eq_specs = [
        ("a_share", "a-share", R.eq_a, "🇨🇳 A 股全景手册", "中国 A 股跨周期全景手册"),
        ("hk_stock", "hk-stock", R.eq_hk, "🇭🇰 港股全景手册", "香港股市跨周期全景手册"),
        ("us_stock", "us-stock", R.eq_us, "🇺🇸 美股全景手册", "美国股市跨周期全景手册"),
    ]
    eq_flagship_meta: dict[str, dict] = {}
    eq_flagship_mds: dict[str, str] = {}
    for eq_key, _, eq_mod, _, _ in eq_specs:
        meta = eq_mod.load_meta()
        if hasattr(eq_mod, "resolve_flagship_md"):
            md_path = eq_mod.resolve_flagship_md(meta)
        else:
            md_path = eq_mod.resolve_flagship_paths(meta)[0]
        if not md_path.is_file():
            fallback_md = EQUITY_DIR / f"{eq_key}_market_report_latest.md"
            if fallback_md.is_file():
                md_path = fallback_md
        eq_flagship_meta[eq_key] = meta
        eq_flagship_mds[eq_key] = md_path.read_text(encoding="utf-8")

    ah_benchmarks = (
        (eq_state.get("cross_market_linkages") or {})
        .get("ah_premium_radar", {})
        .get("benchmarks")
    )
    stocks = extract_all_stocks(
        eq_flagship_mds["a_share"],
        eq_flagship_mds["hk_stock"],
        eq_flagship_mds["us_stock"],
        ah_benchmarks=ah_benchmarks,
    )
    flagship_dates = {
        slug: _extract_iso_date(eq_flagship_meta[eq_key].get("benchmark_time") or "")
        for eq_key, slug, *_ in eq_specs
    }
    gold_tier0_locked = (
        gold_snap.get("new_buy_allowed") is False
        or str(gold_snap.get("tier_code") or "").strip() == "Tier 0"
    )
    stocks = merge_stock_dossiers(
        stocks,
        dossiers_data,
        flagship_dates=flagship_dates,
        gold_tier0_locked=gold_tier0_locked,
        ah_benchmarks=ah_benchmarks,
    )
    stock_counts: dict[str, int] = defaultdict(int)
    for st in stocks:
        stock_counts[st["market"]] += 1
    total_pool = len(stocks)

    # The renderer always receives a new output directory.
    out_dir.mkdir(parents=True)
    for sub in ("assets", "reports", "daily", "channels"):
        (out_dir / sub).mkdir()

    # Static assets + .nojekyll + manifest.json + favicon.svg + kline.js + sharded klines/*.json
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copyfile(ASSETS_SRC / "app.css", out_dir / "assets" / "app.css")
    shutil.copyfile(ASSETS_SRC / "app.js", out_dir / "assets" / "app.js")
    if (ASSETS_SRC / "kline.js").is_file():
        shutil.copyfile(ASSETS_SRC / "kline.js", out_dir / "assets" / "kline.js")
    (out_dir / "assets" / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")

    # Bundle sharded K-line JSONs from equity/state/klines/ -> _site/assets/klines/ (graceful when absent)
    klines_src_dir = EQUITY_DIR / "state" / "klines"
    kline_manifest: dict[str, Any] | None = None
    kline_core: dict[str, Any] | None = None
    if (klines_src_dir / "manifest.json").is_file():
        klines_out_dir = out_dir / "assets" / "klines"
        klines_out_dir.mkdir(parents=True, exist_ok=True)
        for kf in sorted(klines_src_dir.glob("*.json")):
            shutil.copyfile(kf, klines_out_dir / kf.name)
        try:
            kline_manifest = json.loads((klines_src_dir / "manifest.json").read_text(encoding="utf-8"))
        except Exception:
            kline_manifest = None
        if (klines_src_dir / "core.json").is_file():
            try:
                kline_core = json.loads((klines_src_dir / "core.json").read_text(encoding="utf-8"))
            except Exception:
                kline_core = None

    _align_screener_quotes(
        stocks,
        kline_manifest if isinstance(kline_manifest, dict) and kline_manifest.get("edition_id") == eq_state.get("edition_id") else {},
        str(eq_state.get("as_of_cst") or ""),
        eq_state.get("calendar_overrides"),
    )
    multi_idx = _resolve_multi_index_groups(gold_snap, eq_state, kline_manifest)
    total_kline_cnt = (
        int(kline_manifest.get("total_instruments", 0))
        if isinstance(kline_manifest, dict) and kline_manifest.get("total_instruments")
        else 0
    )

    manifest = {
        "name": "全球投研 · 六大市场（A/港/美 · 债/金/非美）",
        "short_name": "全球投研",
        "description": f"机构级全球跨市场投研门户：A股、港股、美股、中美债率、黄金与非美全球六大市场驾驶舱、全市场 K 线终端、{total_pool}只龙头筛选器与每日早午晚报。",
        "start_url": "./",
        "display": "standalone",
        "background_color": "#f6f3ec",
        "theme_color": "#141a24",
        "icons": [
            {
                "src": "assets/favicon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            }
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Discover all non-archived dailies
    dailies, slug_map = discover_dailies()

    # ------------------------------------------------------------------
    # A. Build 4 Flagship Evergreen Reports (reports/{gold,a-share,hk-stock,us-stock}.html)
    # ------------------------------------------------------------------
    flagship_stats: dict[str, int] = {}
    flagship_info: list[dict[str, str]] = []

    # A1. Gold Master Report
    gold_md_path = GOLD_DIR / "黄金跨世纪周期与2026-2030终审研究报告.md"
    gold_md = gold_md_path.read_text(encoding="utf-8")
    g_snap_master, _ = R.gold_report.load_master_snapshot(gold_md, allow_drift=False)
    R.gold_report.SNAP = g_snap_master
    R.gold_report.REPORT_VERSION = str(g_snap_master.get("master_version", "普通人终审定版"))
    R.gold_report.REPORT_TIMESTAMP = str(g_snap_master.get("as_of_bjt", ""))
    R.gold_report.REPORT_SHORT_DATE = str(g_snap_master.get("as_of_short", ""))
    g_cover = R.gold_report.build_cover_html()
    g_body_raw, _ = R.gold_report.convert_md_to_html_body(
        normalize_relative_md_links(protect_backticked_comments(_clean_soft_filenames(gold_md))),
        docx_mode=False,
    )
    g_body, g_toc, g_charts = sanitize_and_extract_toc(
        g_body_raw, base_prefix="../", slug_map=slug_map, ctx_market="gold"
    )
    g_read_min = estimate_reading_minutes(g_body)
    g_footer = (
        f"本报告（数据基线 {R.gold_report.REPORT_TIMESTAMP}）数据均经多源官方数据库核验；"
        "投资有风险，请按家庭总资产 10%–15% 合理配置，严禁借钱或加杠杆炒金。"
    )
    gold_report_html = render_page_shell(
        title="黄金跨世纪周期与普通人全景配置指南（1971–2030）",
        active_nav="gold",
        base_prefix="../",
        market_attr="gold",
        doc_kind="flagship",
        total_pool=total_pool,
        channel_count=ch_total,
        channels_list=all_chs,
        etf_count=etf_total,
        total_kline_count=total_kline_cnt,
        toc_items=g_toc,
        show_chart_modal=True,
        footer_ts=R.gold_report.REPORT_SHORT_DATE,
        gold_red_light=gold_tier0_locked,
        content_html=render_doc_with_toc(
            toolbar_html=build_doc_toolbar(
                market="gold",
                doc_kind="flagship",
                read_minutes=g_read_min,
                chart_count=g_charts,
                has_toc=bool(g_toc),
                total_pool=total_pool,
                channel_count=ch_total,
            ),
            cover_html=g_cover,
            body_html=g_body,
            footer_note=g_footer,
            toc_items=g_toc,
            doc_kind="flagship",
        ),
    )
    (out_dir / "reports" / "gold.html").write_text(gold_report_html, encoding="utf-8")
    flagship_stats["gold"] = g_charts
    gold_baseline_norm = (
        fmt_cst_compact(R.gold_report.REPORT_SHORT_DATE or R.gold_report.REPORT_TIMESTAMP)
        .removesuffix(" CST")
        .strip()
        or R.gold_report.REPORT_SHORT_DATE
    )
    flagship_info.append(
        {
            "market": "gold",
            "badge": "🥇 黄金主报告",
            "title": "黄金跨世纪周期与普通人全景配置指南（1971–2030）",
            "baseline": gold_baseline_norm,
            "charts": str(g_charts),
            "href": "reports/gold.html",
            "accent": "#b45309",
        }
    )

    # A2-A4. Equity Flagship Reports (A-Share, HK-Stock, US-Stock)
    for eq_key, m_slug, _, badge_lbl, fallback_title in eq_specs:
        meta = eq_flagship_meta[eq_key]
        md_text = eq_flagship_mds[eq_key]
        charts = get_equity_charts(R, eq_key, meta_override=meta)
        cover_html, doc_title, _, footer_note = R.eq_pdf_common.render_cover_banner(
            meta, fallback_title, badge_lbl, fallback_title, meta_label="阅读说明"
        )
        _, body_raw = R.eq_pdf_common.render_md_body(
            normalize_relative_md_links(md_text), charts, is_flagship=True
        )
        body_clean, toc, n_charts = sanitize_and_extract_toc(
            body_raw, base_prefix="../", slug_map=slug_map, ctx_market=m_slug
        )
        read_min = estimate_reading_minutes(body_clean)
        page_html = render_page_shell(
            title=doc_title,
            active_nav=m_slug,
            base_prefix="../",
            market_attr=m_slug,
            doc_kind="flagship",
            total_pool=total_pool,
            channel_count=ch_total,
            channels_list=all_chs,
            etf_count=etf_total,
            total_kline_count=total_kline_cnt,
            toc_items=toc,
            show_chart_modal=True,
            footer_ts=str(meta.get("benchmark_time", "")).split("（")[0],
            gold_red_light=gold_tier0_locked,
            content_html=render_doc_with_toc(
                toolbar_html=build_doc_toolbar(
                    market=m_slug,
                    doc_kind="flagship",
                    read_minutes=read_min,
                    chart_count=n_charts,
                    has_toc=bool(toc),
                    total_pool=total_pool,
                    channel_count=ch_total,
                ),
                cover_html=cover_html,
                body_html=body_clean,
                footer_note=footer_note,
                toc_items=toc,
                doc_kind="flagship",
            ),
        )
        (out_dir / "reports" / f"{m_slug}.html").write_text(page_html, encoding="utf-8")
        flagship_stats[m_slug] = n_charts
        raw_bm_time = str(meta.get("benchmark_time", ""))
        baseline_disp = (
            fmt_cst_compact(raw_bm_time).removesuffix(" CST").strip()
            or re.sub(r"[（(]周[一二三四五六日天][）)]", " ", raw_bm_time)
            .split("（", 1)[0]
            .replace("北京时间", "")
            .strip()
        )
        flagship_info.append(
            {
                "market": m_slug,
                "badge": badge_lbl,
                "title": doc_title,
                "baseline": baseline_disp,
                "charts": str(n_charts),
                "href": f"reports/{m_slug}.html",
                "accent": MARKET_META[m_slug]["accent"],
            }
        )

    # ------------------------------------------------------------------
    # B. Render All Daily Reports + 4 Canonical Latest Pages
    # ------------------------------------------------------------------
    dailies_by_market: dict[str, list[DailyItem]] = defaultdict(list)
    total_daily_charts = 0

    for item in dailies:
        raw_md = item.source_path.read_text(encoding="utf-8")
        if item.market == "gold":
            title, meta, body_raw, _ = R.gold_daily.md_to_html(
                normalize_relative_md_links(protect_backticked_comments(raw_md)), docx_mode=False
            )
            accent = R.gold_daily.sanitize_hex_color(meta.get("accent", "#b45309"))
            cover_html = R.gold_daily.build_cover_html(title, meta, accent=accent)
            footer_note = str(
                meta.get(
                    "footer_note",
                    "本文按所标日期记录行情和研究判断。",
                )
            )
            item.title = clean_md_inline_plain(title)
            item.summary = _extract_summary_from_daily(raw_md, meta, is_gold=True)
            item.edition_type = str((meta or {}).get("edition_type", "main")).strip().lower() or "main"
        else:
            eq_key = item.market.replace("-", "_")
            meta, md_body = R.eq_daily.extract_daily_meta(raw_md, item.source_path)
            revision = f"_r{item.rev}" if item.rev > 1 else ""
            edition_id = f"{item.date_str}_{item.hhmm}{revision}"
            if edition_id == eq_state.get("edition_id") and (meta or {}).get("edition_id") != edition_id:
                raise ValueError(f"{item.source_path.name}: missing or mismatched edition metadata")
            charts = get_equity_charts(R, eq_key, meta_override=meta) if meta else {}
            mm = MARKET_META[item.market]
            fallback_t = f"{mm['name']}每日投研简报"
            title, body_raw = R.eq_pdf_common.render_md_body(
                normalize_relative_md_links(md_body),
                charts,
                default_title=fallback_t,
                is_flagship=False,
                enable_kanban_wrap=True,
            )
            cover_html, doc_title, _, footer_note = R.eq_pdf_common.render_cover_banner(
                meta, title, f"{mm['short']}每日投研简报", fallback_t, meta_label="阅读提示"
            )
            item.title = clean_md_inline_plain(doc_title)
            item.summary = _extract_summary_from_daily(raw_md, meta, is_gold=False)
            item.edition_type = str((meta or {}).get("edition_type", "main")).strip().lower() or "main"

        body_clean, toc, n_charts = sanitize_and_extract_toc(
            body_raw, base_prefix="../", slug_map=slug_map, ctx_market=item.market
        )
        body_clean = inject_glossary_tips(body_clean)
        # Also sanitize cover_html (strip any residual comments or file:// links)
        cover_clean, _, _ = sanitize_and_extract_toc(
            cover_html, base_prefix="../", slug_map=slug_map, ctx_market=item.market, extract_toc=False
        )
        item.cover_html = cover_clean
        item.body_html = body_clean
        item.footer_note = footer_note
        item.toc = toc
        item.chart_count = n_charts
        item.read_minutes = estimate_reading_minutes(body_clean)
        total_daily_charts += n_charts
        dailies_by_market[item.market].append(item)

    latest_by_market: dict[str, DailyItem] = {}
    for mk, m_list in dailies_by_market.items():
        m_list.sort(key=lambda x: x.sort_key)
        last_by_session = {(item.date_str, item.hhmm): item for item in m_list}
        mk_caveats = collect_data_caveats(gold_snap, eq_state, market=mk)
        for idx, item in enumerate(m_list):
            prev_it = m_list[idx - 1] if idx > 0 else None
            next_it = m_list[idx + 1] if idx + 1 < len(m_list) else None
            is_latest = idx == len(m_list) - 1
            item_edition_id = f"{item.date_str}_{item.hhmm}{f'_r{item.rev}' if item.rev > 1 else ''}"
            current_mk_edition = (
                str(gold_snap.get("edition_id") or "").strip()
                if mk == "gold"
                else str(eq_state.get("edition_id") or "").strip()
            )
            is_reused_latest = bool(
                is_latest
                and current_mk_edition
                and item_edition_id != current_mk_edition
            )
            corrected = last_by_session[item.date_str, item.hhmm]
            revision_notice_html = (
                '<div class="revision-notice no-print">'
                "<span>此页为本班次原刊档案，后续已有修订更新。</span>"
                f'<a class="btn btn-sm" href="{corrected.slug}.html">查看本班次修订稿 →</a>'
                "</div>"
                if item.rev < corrected.rev
                else ""
            )
            daily_kline_strip = _render_daily_kline_strip(item.market, multi_idx, base_prefix="../") if is_latest else ""
            enhanced_body = _enhance_daily_body_visuals(item.body_html)

            def _build_daily_html(apply_live_overlays: bool) -> str:
                tb_html = (
                    build_doc_toolbar(
                        market=item.market,
                        doc_kind="daily",
                        read_minutes=item.read_minutes,
                        chart_count=item.chart_count,
                        has_toc=bool(item.toc),
                        stock_counts=stock_counts,
                        item=item,
                        prev_item=prev_it,
                        next_item=next_it,
                        is_latest=apply_live_overlays,
                    )
                    + revision_notice_html
                )
                disc_inline = render_daily_disclosure(
                    mk_caveats,
                    item.market,
                    apply_live_overlays,
                    item.date_str,
                    item.session_label,
                )
                v_cockpit = (
                    _render_daily_visual_cockpit(
                        item.market, eq_state, gold_snap, item.body_html, reused_body=is_reused_latest,
                    )
                    if apply_live_overlays
                    else ""
                )
                m_news_html = ""
                page_body = enhanced_body
                p_toc = list(item.toc)
                if apply_live_overlays:
                    calendar_html = _render_market_forward_calendar(item.market, policy_calendar_data, current_mk_edition)
                    if calendar_html:
                        page_body = _place_daily_calendar(
                            page_body, calendar_html, reused=is_reused_latest,
                            original_issue=f"{item.date_str} {item.session_label}",
                            original_url=f"{item.slug}.html",
                        )
                        p_toc.append((2, "sec-market-calendar", "本班未来 14 天财经与政策日历"))
                    m_news_html, mnews_cnt = _render_market_news_radar(
                        item.market, policy_calendar_data, eq_state, gold_tier0_locked
                    )
                    if mnews_cnt > 0:
                        p_toc.append((2, "sec-market-news", f"本市场全部重要新闻（{mnews_cnt} 条）"))
                doc_html = render_doc_with_toc(
                    toolbar_html=tb_html,
                    cover_html=item.cover_html,
                    body_html=page_body,
                    footer_note=item.footer_note,
                    toc_items=p_toc,
                    doc_kind="daily",
                    disclosure_html=disc_inline,
                    kline_strip_html=daily_kline_strip if apply_live_overlays else "",
                    visual_cockpit_html=v_cockpit,
                    market_news_html=m_news_html,
                )
                return render_page_shell(
                    title=item.title,
                    active_nav=item.market,
                    base_prefix="../",
                    market_attr=item.market,
                    doc_kind="daily",
                    edition_attr=item.edition_type,
                    total_pool=total_pool,
                    channel_count=ch_total,
                    channels_list=all_chs,
                    etf_count=etf_total,
                    total_kline_count=total_kline_cnt,
                    toc_items=p_toc,
                    show_chart_modal=(item.chart_count > 0),
                    footer_ts=f"{item.date_str} {item.session_label}",
                    gold_red_light=gold_tier0_locked,
                    content_html=doc_html,
                )

            archive_page = _build_daily_html(apply_live_overlays=False)
            (out_dir / "daily" / f"{item.slug}.html").write_text(archive_page, encoding="utf-8")
            if is_latest:
                latest_by_market[mk] = item
                latest_page = _build_daily_html(apply_live_overlays=True)
                (out_dir / "daily" / f"{mk}-latest.html").write_text(latest_page, encoding="utf-8")

    # ------------------------------------------------------------------
    # B2. Build Full-Screen Interactive K-Line Terminal (charts.html)
    # ------------------------------------------------------------------
    charts_html = render_page_shell(
        title="全市场交互 K 线与技术指标终端",
        active_nav="charts",
        base_prefix="",
        market_attr="overview",
        doc_kind="tool",
        total_pool=total_pool,
        channel_count=ch_total,
        channels_list=all_chs,
        etf_count=etf_total,
        total_kline_count=total_kline_cnt,
        footer_ts=eq_as_of_disp,
        gold_red_light=gold_tier0_locked,
        content_html=build_charts_page(
            gold_snap, eq_state, multi_idx, stocks, etf_data, kline_manifest
        ),
    )
    (out_dir / "charts.html").write_text(charts_html, encoding="utf-8")

    # ------------------------------------------------------------------
    # C. Build Global Stock Screener (screener.html)
    # ------------------------------------------------------------------
    screener_benchmarks = {
        slug: str(eq_flagship_meta[key].get("benchmark_time") or "未标明").split("（", 1)[0]
        for key, slug, *_ in eq_specs
    }
    unique_benchmarks = set(screener_benchmarks.values())
    ah_radar_obj = (eq_state.get("cross_market_linkages") or {}).get("ah_premium_radar") or {}
    rates_obj = (eq_state.get("cross_market_linkages") or {}).get("rates_fx_chain") or {}
    hkd_cny_mid = _safe_float(rates_obj.get("hkd_cny_mid"))
    hkd_cny_mid_date = _extract_iso_date(rates_obj.get("cfets_fixing_date") or "")
    ah_matrix = _build_ah_matrix_payload(
        ah_benchmarks, stocks, kline_manifest=kline_manifest,
        hkd_cny_mid=hkd_cny_mid, fx_date=hkd_cny_mid_date,
        as_of_date=_extract_iso_date(eq_state.get("as_of_cst") or ""),
        as_of_cst=str(eq_state.get("as_of_cst") or ""),
        edition_id=eq_state.get("edition_id"),
        calendar_overrides=eq_state.get("calendar_overrides"),
    )
    screener_html = render_page_shell(
        title=f"全球 {total_pool} 家核心龙头筛选器",
        active_nav="screener",
        base_prefix="",
        market_attr="overview",
        doc_kind="tool",
        total_pool=total_pool,
        channel_count=ch_total,
        channels_list=all_chs,
        etf_count=etf_total,
        total_kline_count=total_kline_cnt,
        footer_ts=next(iter(unique_benchmarks)) if len(unique_benchmarks) == 1 else "",
        gold_red_light=gold_tier0_locked,
        content_html=build_screener_page(
            stocks,
            screener_benchmarks,
            default_date=default_dossier_date,
            ah_matrix=ah_matrix,
            hsahp_index=_safe_float(ah_radar_obj.get("hsahp_index")),
            hkd_cny_mid=hkd_cny_mid,
            hkd_cny_mid_date=hkd_cny_mid_date,
        ),
    )
    (out_dir / "screener.html").write_text(screener_html, encoding="utf-8")

    # ------------------------------------------------------------------
    # D. Build Public Accountability Scorecard & Changelog (scorecard.html)
    # ------------------------------------------------------------------
    scorecard_html = render_page_shell(
        title="公开预测记分卡与观点演进账本",
        active_nav="scorecard",
        base_prefix="",
        market_attr="overview",
        doc_kind="scorecard",
        total_pool=total_pool,
        channel_count=ch_total,
        channels_list=all_chs,
        etf_count=etf_total,
        total_kline_count=total_kline_cnt,
        footer_ts=eq_as_of_disp,
        gold_red_light=gold_tier0_locked,
        content_html=build_scorecard_page(R, slug_map, gold_snap=gold_snap),
    )
    (out_dir / "scorecard.html").write_text(scorecard_html, encoding="utf-8")

    # ------------------------------------------------------------------
    # E. Build Archive Page (archive.html)
    # ------------------------------------------------------------------
    total_flagship_charts = sum(flagship_stats.values())
    archive_html = render_page_shell(
        title="历史研报档案与全景书架",
        active_nav="archive",
        base_prefix="",
        market_attr="overview",
        doc_kind="tool",
        total_pool=total_pool,
        channel_count=ch_total,
        channels_list=all_chs,
        etf_count=etf_total,
        total_kline_count=total_kline_cnt,
        footer_ts=eq_as_of_disp,
        gold_red_light=gold_tier0_locked,
        content_html=build_archive_page(
            dailies, flagship_info, stock_counts, total_pool, total_flagship_charts
        ),
    )
    (out_dir / "archive.html").write_text(archive_html, encoding="utf-8")

    # ------------------------------------------------------------------
    # C2. Build Multi-Asset Personal Channels (channels.html + channels/<id>.html),
    #     ETF Radar (etfs.html) & Beginner 3-Min Guide (guide.html)
    # ------------------------------------------------------------------
    ch_page_title = f"{ch_total} 大个人合规多元投资渠道总览" if ch_total else "个人合规多元投资渠道总览"
    channels_html = render_page_shell(
        title=ch_page_title,
        active_nav="channels",
        base_prefix="",
        market_attr="overview",
        doc_kind="tool",
        total_pool=total_pool,
        channel_count=ch_total,
        channels_list=all_chs,
        etf_count=etf_total,
        total_kline_count=total_kline_cnt,
        footer_ts=eq_as_of_disp,
        gold_red_light=gold_tier0_locked,
        content_html=build_channels_page(channels_data, etf_data=etf_data, eq_state=eq_state),
    )
    (out_dir / "channels.html").write_text(channels_html, encoding="utf-8")

    channel_detail_pages = 0
    if isinstance(channels_data, dict):
        for ch in all_chs:
            cid = str(ch["id"]).strip()
            ch_title = str(ch.get("name") or cid)
            detail_html = render_page_shell(
                title=ch_title,
                active_nav="channels",
                base_prefix="../",
                market_attr="overview",
                doc_kind="tool",
                channel_id=cid,
                total_pool=total_pool,
                channel_count=ch_total,
                channels_list=all_chs,
                etf_count=etf_total,
                total_kline_count=total_kline_cnt,
                footer_ts=str(channels_data.get("as_of_label") or eq_as_of_disp),
                gold_red_light=gold_tier0_locked,
                content_html=build_channel_detail_page(ch, all_chs, channels_data, etf_data=etf_data),
            )
            (out_dir / "channels" / f"{cid}.html").write_text(detail_html, encoding="utf-8")
            channel_detail_pages += 1

    etfs_html = render_page_shell(
        title=f"全球 {etf_total} 只重点 ETF 多通道深度雷达" if etf_total else "全球重点 ETF 深度雷达",
        active_nav="etfs",
        base_prefix="",
        market_attr="overview",
        doc_kind="tool",
        total_pool=total_pool,
        channel_count=ch_total,
        channels_list=all_chs,
        etf_count=etf_total,
        total_kline_count=total_kline_cnt,
        footer_ts=eq_as_of_disp,
        gold_red_light=gold_tier0_locked,
        content_html=build_etfs_page(etf_data, channel_count=ch_total, channels_data=channels_data),
    )
    (out_dir / "etfs.html").write_text(etfs_html, encoding="utf-8")

    guide_html = render_page_shell(
        title="新手 3 分钟入门指南与高频关键词速查",
        active_nav="guide",
        base_prefix="",
        market_attr="overview",
        doc_kind="guide",
        total_pool=total_pool,
        channel_count=ch_total,
        channels_list=all_chs,
        etf_count=etf_total,
        total_kline_count=total_kline_cnt,
        footer_ts=eq_as_of_disp,
        gold_red_light=gold_tier0_locked,
        content_html=build_guide_page(
            gold_snap, eq_state, channels_data, etf_data, total_pool=total_pool, kline_manifest=kline_manifest,
        ),
    )
    (out_dir / "guide.html").write_text(guide_html, encoding="utf-8")

    # ------------------------------------------------------------------
    # F. Build Global Weather Cockpit (index.html)
    # ------------------------------------------------------------------
    cockpit_html = render_page_shell(
        title="全球投研总览 · 六大市场（A/港/美 · 债/金/非美）",
        active_nav="overview",
        base_prefix="",
        market_attr="overview",
        doc_kind="overview",
        total_pool=total_pool,
        channel_count=ch_total,
        channels_list=all_chs,
        etf_count=etf_total,
        total_kline_count=total_kline_cnt,
        footer_ts=eq_as_of_disp,
        gold_red_light=gold_tier0_locked,
        content_html=build_cockpit_page(
            gold_snap,
            eq_state,
            latest_by_market,
            stock_counts,
            channels_data=channels_data,
            etf_data=etf_data,
            kline_manifest=kline_manifest,
            kline_core=kline_core,
            stocks=stocks,
            policy_calendar=policy_calendar_data,
        ),
    )
    (out_dir / "index.html").write_text(cockpit_html, encoding="utf-8")

    return {
        "out_dir": str(out_dir),
        "flagship_charts": flagship_stats,
        "flagship_total_charts": sum(flagship_stats.values()),
        "daily_pages": len(dailies),
        "latest_pages": len(latest_by_market),
        "channel_detail_pages": channel_detail_pages,
        "etf_total": etf_total,
        "daily_total_charts": total_daily_charts,
        "screener_total": len(stocks),
        "screener_by_market": dict(stock_counts),
        "html_files": len(list(out_dir.rglob("*.html"))),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Global Investment Research static web portal.")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "_site",
        help="Target output directory (default: <repo>/_site)",
    )
    args = parser.parse_args()
    summary = build_site(args.out.resolve())
    print(
        f"Built static portal -> {summary['out_dir']}\n"
        f"  HTML pages:      {summary['html_files']} "
        f"(8 core + {summary['channel_detail_pages']} channel details + 4 flagships + "
        f"{summary['daily_pages']} dated dailies + {summary['latest_pages']} canonical latest)\n"
        f"  Flagship charts: {summary['flagship_total_charts']} {summary['flagship_charts']}\n"
        f"  Daily charts:    {summary['daily_total_charts']}\n"
        f"  ETF radar:       {summary['etf_total']} ETFs\n"
        f"  Screener pool:   {summary['screener_total']} {summary['screener_by_market']}"
    )


if __name__ == "__main__":
    main()
