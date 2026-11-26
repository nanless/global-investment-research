#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static Site Generator for Global Investment Research Portal (Gold × A-Share × HK-Stock × US-Stock).

Pure Python 3 stdlib ONLY (zero Node/npm/Hugo/Chrome/PIL/bs4/markdown dependency).
Works identically on macOS and GitHub Actions Ubuntu:
    python3 scripts/build_site.py --out _site

Safety guarantee:
  - Reads gold/ and equity/ strictly READ-ONLY.
  - Loads gold/ and equity/ renderers in isolated module namespaces with stubbed docx_embed
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
import types
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from math import isfinite
from pathlib import Path
from typing import Any

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


def session_label_from_hhmm(hhmm: str) -> tuple[str, str]:
    """Return (session_key, display_label) for archive filtering."""
    h = int(hhmm[:2]) if len(hhmm) >= 2 and hhmm[:2].isdigit() else 7
    disp_time = f"{hhmm[:2]}:{hhmm[2:4]}" if len(hhmm) == 4 else hhmm
    if h < 12:
        return "morning", f"早报 {disp_time}"
    if h < 17:
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
        for k in ("docx_embed", "build_daily", "pdf_common", "lint_equity", "chart_input", "edition_plan")
    }
    try:
        # 1. Stub docx_embed so gold/build_daily.py & gold/build_report.py need ZERO bs4/PIL
        stub_docx = types.ModuleType("docx_embed")
        stub_docx.build_native_docx = lambda *a, **kw: None  # type: ignore[attr-defined]
        stub_docx.render_chart_to_png = lambda *a, **kw: None  # type: ignore[attr-defined]
        stub_docx.resolve_chrome_bin = lambda *a, **kw: ""  # type: ignore[attr-defined]
        stub_docx.__getattr__ = lambda name: (lambda *a, **kw: None)  # type: ignore[attr-defined]
        sys.modules["docx_embed"] = stub_docx
        _load_module_from_path("chart_input", GOLD_DIR / "chart_input.py")

        gold_daily = _load_module_from_path("_gir_gold_daily", GOLD_DIR / "build_daily.py")
        sys.modules["build_daily"] = gold_daily
        gold_report = _load_module_from_path("_gir_gold_report", GOLD_DIR / "build_report.py")

        # Clear temporary gold aliases before loading equity modules
        sys.modules.pop("build_daily", None)
        sys.modules.pop("docx_embed", None)

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
    hhmm: str                # 0730 / 1630 / 1800
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
            if p.parent != gold_daily_dir and hhmm not in {"0730", "1800"}:
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
            if p.parent != eq_daily_dir and hhmm not in {"0730", "1800"}:
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
    r"master_snapshot\.json|permissions\.json|unified-edition\.prompt\.md|"
    r"DAILY_FORMAT_SPEC\.md|DAILY_REPORT_SPEC\.md|"
    r"lint_readability\.py|lint_equity\.py|lint_site\.py|"
    r"build_(?:daily|report|site|a_share_pdf|hk_stock_pdf|us_stock_pdf|pdf)\.py|"
    r"publish_site\.py|pdf_common\.py|docx_embed\.py|"
    r"edition_run\.py|artifact_receipt\.py|edition_plan\.py|edition_validation\.py|"
    r"chart_input\.py|install_sidecars\.py|"
    r"AGENTS\.md|SKILL\.md|GEMINI\.md|audit_ledger\.md|gold-research-publishing|"
    r"5-plus-1-research-playbook(?:\.md)?|directives-and-snapshot-schema(?:\.md)?|"
    r"\btextutil\b)",
    flags=re.IGNORECASE,
)
_SOFT_FILENAME_REPS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"`?data_snapshot\.json`?", re.IGNORECASE), "实时数据快照"),
    (re.compile(r"`?master_snapshot\.json`?", re.IGNORECASE), "主报告基线快照"),
    (re.compile(r"`?market_calendar\.json`?", re.IGNORECASE), "跨市场交易日历"),
    (re.compile(r"新架构与\s*RSI\s*闭环首次实战跑"), "日终清算与产业链深挖"),
    (re.compile(r"\s*\+\s*原生\s*OOXML\s*Word\s*引擎"), ""),
)


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
    if href.startswith(_GIR_REL_PREFIX):
        href = href[len(_GIR_REL_PREFIX) :]
    if not href or href.startswith("#") or href.startswith("mailto:"):
        return raw_href
    if href.startswith("http://") or href.startswith("https://"):
        return raw_href

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

    # Fallback: NEVER allow file://, /Users/, /home/, or broken local .md/.pdf paths
    if (
        lower.startswith("file://")
        or "/users/" in lower
        or re.search(r"(?<![a-z0-9._-])/home/", lower)
        or lower.endswith((".md", ".pdf", ".docx"))
    ):
        return f"{base_prefix}archive.html"

    return raw_href


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
    return "".join(out)


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
        r'<div class="chart-box">.*?(?=<div class="chart-note">|<div class="chart-takeaway">|</div>\s*$)',
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

        def _proc_heading(m: re.Match) -> str:
            tag = m.group(1).lower()
            attrs = m.group(2) or ""
            inner = m.group(3)
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
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


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
    m_lbl = re.search(
        r"(?:(?:TTM|FWD|前瞻|静态|动态)?\s*PE\s*[（(]?(?:TTM|FWD)?[）)]?\s*[:：]?\s*[~≈<>≤≥]?\s*)([0-9]+(?:\.[0-9]+)?)",
        txt,
        flags=re.IGNORECASE,
    )
    if m_lbl:
        v = _to_pos_float(m_lbl.group(1))
        return round(v, 1) if (v is not None and v < 5000) else None
    target = txt.split("/", 1)[0].strip() if market in ("a-share", "hk-stock") else txt
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
    for src in (str(valuation or ""), str(summary or "")):
        m = re.search(r"AH\s*(?:溢价|折价|倒挂)?\s*[:：]?\s*([+\-−]?[0-9]+(?:\.[0-9]+)?)%", src, flags=re.IGNORECASE)
        if m:
            try:
                v = float(m.group(1).replace("−", "-"))
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
    if code and code in ah_lookup:
        return round(ah_lookup[code], 1)
    return None


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

    # --- 1. A-Share: map colors from ### 5.2, then merge with ## 附表二 ---
    a_color_map: dict[str, tuple[str, str]] = {}
    s52_start = a_md.find("### 5.2")
    s52_end = a_md.find("### 5.3", s52_start if s52_start != -1 else 0)
    if s52_start != -1:
        s52_block = a_md[s52_start : (s52_end if s52_end != -1 else len(a_md))]
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
            col = _detect_color(cells[4])
            anchor_m = re.search(r"(安全锚|重估锚|极值锚)[：:]\s*([^<|]+)", cells[3])
            anchor_txt = f"{anchor_m.group(1)} {anchor_m.group(2).strip()}" if anchor_m else ""
            a_color_map[code] = (col, anchor_txt)

    for cells in _parse_app2_rows(a_md):
        if len(cells) < 5:
            continue
        sector = clean_md_inline_plain(cells[0])
        m_code = re.search(r"`(\d{6})`", cells[1])
        code = m_code.group(1) if m_code else ""
        name = clean_md_inline_plain(re.sub(r"`[^`]+`", "", cells[1]))
        price = clean_md_inline_plain(cells[2])
        valuation = clean_md_inline_plain(cells[3])
        summary_raw = clean_md_inline_plain(cells[4])
        summary = _LEADING_RATING_PREFIX_RE.sub("", summary_raw).strip()
        col, anchor_txt = a_color_map.get(code, ("y", ""))
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

_CAVEAT_SEV_RANK: dict[str, int] = {"high": 0, "warn": 1, "info": 2}
_CAVEAT_MKT_RANK: dict[str, int] = {"gold": 0, "a-share": 1, "hk-stock": 2, "us-stock": 3, "cross": 4}

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
    (re.compile(r"`?audit_ledger\.md`?", re.IGNORECASE), "核查台账"),
    (re.compile(r"`?RSI_PLAYBOOK(?:\.md)?`?", re.IGNORECASE), "复盘手册"),
    (re.compile(r"`?rsi_metrics\.json`?", re.IGNORECASE), "复盘指标"),
    (re.compile(r"`?DAILY_FORMAT_SPEC\.md`?", re.IGNORECASE), "日报排版规范"),
    (re.compile(r"`?DAILY_REPORT_SPEC\.md`?", re.IGNORECASE), "日报撰写规范"),
    (re.compile(r"`?unified-edition\.prompt\.md`?", re.IGNORECASE), "统一编排规范"),
    (re.compile(r"`?gold-research-publishing`?", re.IGNORECASE), "黄金研究体系"),
    (re.compile(r"`?(?:AGENTS|SKILL|GEMINI)\.md`?", re.IGNORECASE), "研究规范"),
    (re.compile(r"`?(?:sidecar|permissions)\.json`?", re.IGNORECASE), "运行配置"),
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
        hh = int(m.group(4))
        slot = "早报" if hh < 12 else ("午报" if hh < 17 else "晚报")
        return f"预计 {int(m.group(2))}/{int(m.group(3))} {m.group(4)}:{m.group(5)} {slot}核销"
    m_d = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m_d:
        return f"预计 {int(m_d.group(2))}/{int(m_d.group(3))} 核销"
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
                        "item": f"美股恐慌指数（VIX）{dt_key} 官方历史日线表待核销",
                        "detail": chk.get("note") or f"{dt_key} 官方历史日线表尚未更新，暂采交易所官网收盘读数。",
                        "impact": "次班官方历史表刷新后自动复核清零，不影响核心风控红线。",
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
                "detail": "该市场部分官方次级数据尚待收盘或官方数据库披露，本期严守宁缺毋滥原则，下个班次统一封账核销。",
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

    # Deduplicate cleanly
    deduped: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    for it in raw_items:
        key_val = it["id"].lower() if it["id"] else re.sub(r"\W+", "", it["title"].lower())[:48]
        dedup_key = (it["market"], key_val)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        deduped.append(it)

    # Optional market scope filter (always keeps "cross")
    if market is not None:
        norm_target = _norm_caveat_market(market, market)
        deduped = [it for it in deduped if it["market"] in (norm_target, "cross")]

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
        rows.append(
            f'<div class="caveat-item sev-{esc(c["severity"])}">'
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
    has_high = any(c.get("severity") == "high" for c in caveats)
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
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
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
        '<span class="disclosure-sub">早报 07:30 · 晚报 18:00 准时发刊，未到官库披露时点或暂采官网收盘的数据如实挂账，绝不估算填表</span>'
        "</div></div>"
        '<div class="disclosure-summary-meta">'
        f'<span class="disclosure-badge {badge_cls}">{esc(badge_txt)}</span>'
        f'<span class="disclosure-toggle-lbl">展开明细 {chev_svg}</span>'
        "</div>"
        "</summary>"
        '<div class="disclosure-body">'
        f'<div class="disclosure-list-col">{items_html}</div>'
        '<div class="disclosure-policy-col">'
        '<div class="disclosure-policy-title">准时发刊与纠偏机制</div>'
        '<ul class="disclosure-policy-list">'
        "<li><strong>宁缺毋滥</strong>：未到官库披露时点的次级数据一律留空或沿用最近已核实官收并标注原日期，绝不估算填数。</li>"
        "<li><strong>暂用明示</strong>：跨时区官方历史表尚未更新时，可暂采交易所官网收盘价，并在下一班次自动复核清零。</li>"
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
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="10" cy="10" r="8"/><path d="M10 6.2v4.3M10 13.6h.01"/></svg>'
    )
    chev_svg = (
        '<svg class="disclosure-chev" viewBox="0 0 16 16" width="12" height="12" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M4 6l4 4 4-4"/></svg>'
    )
    if is_latest:
        has_high = any(c.get("severity") == "high" for c in caveats)
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
    "}catch(e){}})();</script>"
)


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


def _build_cmd_nav_items(base_prefix: str, total_pool: int) -> list[dict[str, str]]:
    pool_label = f"{total_pool}股池" if total_pool > 0 else "龙头股池"
    return [
        {
            "title": "全球大类资产 10 秒水温驾驶舱",
            "meta": "总览 · 四市红绿灯与风险雷达",
            "href": f"{base_prefix}index.html",
            "keywords": "总览 首页 驾驶舱 overview cockpit home",
        },
        {
            "title": "黄金最新早晚报",
            "meta": "日报 · 四步买金红绿灯与实盘锚",
            "href": f"{base_prefix}daily/gold-latest.html",
            "keywords": "黄金 金价 早报 晚报 gold daily xau",
        },
        {
            "title": "中国 A 股最新早晚报",
            "meta": "日报 · 七维大盘与红利防守",
            "href": f"{base_prefix}daily/a-share-latest.html",
            "keywords": "a股 沪深300 上证 早报 晚报 a-share cn",
        },
        {
            "title": "香港股市最新早晚报",
            "meta": "日报 · 联汇水位与南向资金",
            "href": f"{base_prefix}daily/hk-stock-latest.html",
            "keywords": "港股 恒生 恒科 早报 晚报 hk-stock hsi",
        },
        {
            "title": "美国股市最新早晚报",
            "meta": "日报 · 标普纳指与政策雷达",
            "href": f"{base_prefix}daily/us-stock-latest.html",
            "keywords": "美股 标普 纳指 美债 早报 晚报 us-stock sp500",
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
            "title": "个人多元投资渠道总览（8 大独立通道）",
            "meta": "专页 · 8 大渠道卡片、组合模板与排雷红线",
            "href": f"{base_prefix}channels.html",
            "keywords": "多元渠道 债券 理财 逆回购 qdii 互认 大额存单 可转债 reits 商品 channels",
        },
        {
            "title": "渠道详情 01：债券（储蓄国债与万亿债券 ETF）",
            "meta": "多元渠道 · 独立详情页",
            "href": f"{base_prefix}channels/bonds.html",
            "keywords": "债券 储蓄国债 债券etf 科创债 短融 511360 511260 bonds",
        },
        {
            "title": "渠道详情 02：公募基金、银行理财与税优养老金",
            "meta": "多元渠道 · 独立详情页",
            "href": f"{base_prefix}channels/funds_wm.html",
            "keywords": "公募基金 银行理财 破净 养老金 同业存单 固收+ funds",
        },
        {
            "title": "渠道详情 03：国债逆回购（GC001 / R-001）",
            "meta": "多元渠道 · 独立详情页",
            "href": f"{base_prefix}channels/reverse_repo.html",
            "keywords": "逆回购 gc001 r-001 204001 131810 闲钱 repo",
        },
        {
            "title": "渠道详情 04：场内外 QDII、香港互认 MRF 与理财通",
            "meta": "多元渠道 · 独立详情页",
            "href": f"{base_prefix}channels/qdii_mrf.html",
            "keywords": "qdii 互认基金 mrf 跨境理财通 锁汇 停牌 159509 968050",
        },
        {
            "title": "渠道详情 05：银行大额存单（CDs）",
            "meta": "多元渠道 · 独立详情页",
            "href": f"{base_prefix}channels/large_cds.html",
            "keywords": "大额存单 存单 转让 50万 存款保险 cds",
        },
        {
            "title": "渠道详情 06：可转债（零门槛 ETF 与个券排雷）",
            "meta": "多元渠道 · 独立详情页",
            "href": f"{base_prefix}channels/convertible_bonds.html",
            "keywords": "可转债 转债 511380 511180 强赎 到期 convertible",
        },
        {
            "title": "渠道详情 07：中国公募 REITs（百只时代）",
            "meta": "多元渠道 · 独立详情页",
            "href": f"{base_prefix}channels/c_reits.html",
            "keywords": "公募reits reits 产权 特许经营权 irr 028272 508610",
        },
        {
            "title": "渠道详情 08：非黄金大宗商品 ETF（期货直持与 LOF 排雷）",
            "meta": "多元渠道 · 独立详情页",
            "href": f"{base_prefix}channels/commodity_etfs.html",
            "keywords": "大宗商品 豆粕 有色 能化 白银lof 原油lof 159985 161226",
        },
        {
            "title": "全球三通道重点 ETF 深度雷达（100+ 只）",
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
            "title": "历史早晚报档案与旗舰书架",
            "meta": "档案 · 按市场/时段/刊型检索",
            "href": f"{base_prefix}archive.html",
            "keywords": "历史 档案 往期 archive",
        },
    ]


def render_page_shell(
    *,
    title: str,
    active_nav: str,
    base_prefix: str,
    content_html: str,
    market_attr: str = "overview",
    doc_kind: str = "overview",
    edition_attr: str = "",
    total_pool: int = 0,
    toc_items: list[tuple[int, str, str]] | None = None,
    show_chart_modal: bool = False,
    footer_ts: str = "",
) -> str:
    pool_label = f"{total_pool}股池" if total_pool > 0 else "龙头股池"
    nav_items = [
        ("overview", f"{base_prefix}index.html", "总览"),
        ("gold", f"{base_prefix}daily/gold-latest.html", "黄金"),
        ("a-share", f"{base_prefix}daily/a-share-latest.html", "A股"),
        ("hk-stock", f"{base_prefix}daily/hk-stock-latest.html", "港股"),
        ("us-stock", f"{base_prefix}daily/us-stock-latest.html", "美股"),
        ("channels", f"{base_prefix}channels.html", "多元渠道"),
        ("etfs", f"{base_prefix}etfs.html", "ETF雷达"),
        ("screener", f"{base_prefix}screener.html", pool_label),
        ("scorecard", f"{base_prefix}scorecard.html", "记分卡"),
        ("archive", f"{base_prefix}archive.html", "档案"),
    ]
    nav_parts: list[str] = []
    for key, href, lbl in nav_items:
        dot_html = (
            f'<span class="nav-dot nav-dot-{key}" aria-hidden="true"></span>'
            if key in ("gold", "a-share", "hk-stock", "us-stock")
            else ""
        )
        nav_parts.append(
            f'<a class="nav-pill{" active" if key == active_nav else ""}" data-nav="{key}" href="{href}">{dot_html}{lbl}</a>'
        )
    nav_html = "".join(nav_parts)

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
        _build_cmd_nav_items(base_prefix, total_pool), ensure_ascii=False
    ).replace("</", "<\\/")
    cmd_palette_html = (
        '<div class="cmd-backdrop no-print" id="cmd-palette" role="dialog" aria-modal="true" aria-label="快速跳转">'
        '<div class="cmd-dialog">'
        '<div class="cmd-head">'
        '<input type="search" id="cmd-input" class="cmd-input" placeholder="输入市场、股池视图、记分卡或关键词快速跳转…" autocomplete="off" aria-label="快速跳转搜索">'
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

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{esc(title)} ｜ 全球投研</title>
  <meta name="theme-color" content="#141a24">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="全球投研">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="icon" type="image/svg+xml" href="{base_prefix}assets/favicon.svg">
  <link rel="manifest" href="{base_prefix}manifest.json">
  {THEME_INIT_SCRIPT}
  <link rel="stylesheet" href="{base_prefix}assets/app.css">
</head>
<body data-market="{esc(market_attr)}" data-doc-kind="{esc(doc_kind)}"{f' data-edition="{esc(edition_attr)}"' if edition_attr else ""}>
  <div class="reading-progress" id="reading-progress"></div>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand-link" href="{base_prefix}index.html">
        <span class="brand-mark" aria-hidden="true">{brand_svg}</span>
        <span class="brand-text"><span class="brand-title">全球投研</span><span class="brand-sub">GOLD · CN · HK · US</span></span>
      </a>
      <div class="main-nav-wrap"><nav class="main-nav" aria-label="主导航">{nav_html}</nav></div>
      <div class="header-controls">
        <button type="button" class="ctrl-btn ctrl-cmd" id="cmd-open" title="快速跳转 (⌘K)" aria-label="快速跳转">跳转 <kbd class="kbd-chip">⌘K</kbd></button>
        <div class="ctrl-seg"><button type="button" class="ctrl-btn" id="font-dec" title="缩小字号" aria-label="缩小字号">A-</button><button type="button" class="ctrl-btn" id="font-inc" title="放大字号" aria-label="放大字号">A+</button></div>
        <button type="button" class="ctrl-btn ctrl-theme" id="theme-toggle" title="切换深浅色模式" aria-label="切换深浅色模式">{sun_svg}{moon_svg}</button>
      </div>
    </div>
  </header>

  <main class="page-main">
    {content_html}
  </main>

  <footer class="site-footer">
    <div class="footer-inner">
      <div class="footer-grid">
        <div class="footer-col">
          <div class="footer-brand">全球投研 · GOLD × CN × HK × US</div>
          <p class="footer-desc">每日 07:30 早报 · 18:00 晚报北京时间准时交付 · 多源官方库交叉核验{(" · 更新：" + esc(footer_ts)) if footer_ts else ""}</p>
        </div>
        <div class="footer-col">
          <div class="footer-col-title">核心导航</div>
          <div class="footer-links">
            <a href="{base_prefix}index.html">总览</a>
            <a href="{base_prefix}daily/gold-latest.html">黄金日报</a>
            <a href="{base_prefix}daily/a-share-latest.html">A股日报</a>
            <a href="{base_prefix}daily/hk-stock-latest.html">港股日报</a>
            <a href="{base_prefix}daily/us-stock-latest.html">美股日报</a>
            <a href="{base_prefix}channels.html">8大多元渠道</a>
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

  {back_to_top_html}
  {cmd_palette_html}
  {toc_drawer_html}
  {chart_modal_html}
  <script src="{base_prefix}assets/app.js"></script>
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
) -> str:
    footer_div = f'<div class="footer-note">{esc(footer_note)}</div>' if footer_note else ""
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

    art_cls = "doc-flagship" if doc_kind == "flagship" else "doc-daily"
    return (
        f"{toolbar_html}"
        f'<div class="{layout_cls}">'
        f"{sidebar}"
        f"{mobile_strip}"
        f'<article class="article-card {art_cls}">'
        f"{cover_html}"
        f"{disclosure_html}"
        f'<div class="article-body">{body_html}</div>'
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


def _render_flagship_web_shelf(stock_counts: dict[str, int]) -> str:
    """Render the pure-web evergreen flagship shelf (zero PDF/Word links)."""
    a_pool = stock_counts.get("a-share", 0)
    hk_pool = stock_counts.get("hk-stock", 0)
    us_pool = stock_counts.get("us-stock", 0)
    specs = [
        ("gold", "🥇 黄金跨世纪周期主报告（1971–2030）", "宏观框架 · 四步买金红绿灯 · 中国全渠道税费与回购实操", "reports/gold.html", "daily/gold-latest.html"),
        ("a-share", f"🇨🇳 中国 A 股跨周期全景手册（{a_pool} 股）", "七维大盘体检 · 35 只核心 ETF · 8 大多元渠道与全行业龙头", "reports/a-share.html", "daily/a-share-latest.html"),
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


def _render_channel_overview_cards(channels: list[Any], *, base_prefix: str = "") -> str:
    """Render concise, scannable overview cards for each personal channel linking to its dedicated detail page."""
    cards: list[str] = []
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        cid = str(ch.get("id", "")).strip()
        if not cid:
            continue
        order = ch.get("order", "")
        cat = str(ch.get("category", "fixed_income"))
        tone = str(ch.get("status_tone", "blue"))
        if tone not in ("green", "blue", "amber"):
            tone = "blue"
        href = f"{base_prefix}channels/{cid}.html"
        kpis = [k for k in (ch.get("key_metrics") or []) if isinstance(k, dict)][:2]
        kpi_html = "".join(
            f'<div class="ch-ov-kpi"><span class="ch-ov-kpi-lbl">{esc(k.get("label", ""))}</span>'
            f'<span class="ch-ov-kpi-val">{esc(k.get("value", ""))}</span></div>'
            for k in kpis
        )
        prods = [p for p in (ch.get("products") or []) if isinstance(p, dict)]
        rules = [r for r in (ch.get("rules_and_redlines") or []) if isinstance(r, str) and r.strip()]
        summary_full = str(ch.get("summary", "")).strip()
        summary_short = summary_full if len(summary_full) <= 88 else summary_full[:86].rstrip("，、；： ") + "…"
        cards.append(
            f'<article class="ch-overview-card" id="ch-{esc(cid)}" data-channel-cat="{esc(cat)}">'
            f'<div class="ch-ov-top">'
            f'<div class="ch-ov-title-row">'
            f'<span class="ch-num">0{esc(order)}</span>'
            f'<h3 class="ch-ov-title"><a href="{esc(href)}">{esc(ch.get("name", ""))}</a></h3>'
            f"</div>"
            f'<span class="ch-status ch-tone-{tone}">{esc(ch.get("status_tag", ""))}</span>'
            f"</div>"
            f'<div class="ch-ov-yield">{esc(ch.get("yield_range", ""))}</div>'
            f'<div class="ch-ov-kpis">{kpi_html}</div>'
            f'<p class="ch-ov-summary">{esc(summary_short)}</p>'
            f'<div class="ch-ov-foot">'
            f'<span class="ch-ov-meta">{len(prods)} 项代表标的 · {len(rules)} 条风控红线</span>'
            f'<a class="btn btn-sm btn-primary" href="{esc(href)}">查看详情 →</a>'
            f"</div>"
            f"</article>"
        )
    return f'<div class="ch-overview-grid">{"".join(cards)}</div>'


def _match_related_etfs_for_channel(ch_id: str, etf_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Find matching ETFs from etf_universe.json for a specific channel detail page."""
    if not isinstance(etf_data, dict):
        return []
    etfs = [x for x in (etf_data.get("etfs") or []) if isinstance(x, dict)]
    if not etfs:
        return []
    matched: list[dict[str, Any]] = []
    for it in etfs:
        if it.get("gold_locked"):
            continue
        cat = str(it.get("category", ""))
        mkt = str(it.get("market", ""))
        chan = str(it.get("channel", ""))
        name = str(it.get("name", ""))
        if ch_id == "bonds" and mkt == "multi-asset" and ("债" in cat or "债" in name or "短融" in name):
            if "转债" not in name and "转债" not in cat:
                matched.append(it)
        elif ch_id == "convertible_bonds" and ("转债" in cat or "转债" in name):
            matched.append(it)
        elif ch_id == "commodity_etfs" and mkt == "multi-asset" and ("商品" in cat or "期货" in name or "豆粕" in name or "有色" in name or "能化" in name or "白银" in name or "原油" in name):
            matched.append(it)
        elif ch_id == "qdii_mrf" and ("QDII" in chan or mkt == "global"):
            matched.append(it)
    return matched[:10]


def build_channel_detail_page(
    ch: dict[str, Any],
    all_channels: list[dict[str, Any]],
    channels_data: dict[str, Any],
    etf_data: dict[str, Any] | None = None,
) -> str:
    """Render a standalone, full-detail page for one personal investment channel (channels/<id>.html)."""
    cid = str(ch.get("id", "")).strip()
    order = ch.get("order", "")
    as_of = str(channels_data.get("as_of_label") or "最新班次")
    mutex_note = str(channels_data.get("gold_mutex_note") or "")
    tone = str(ch.get("status_tone", "blue"))
    if tone not in ("green", "blue", "amber"):
        tone = "blue"

    # Quick switcher bar across all 8 channels
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
        switch_pills.append(
            f'<a class="ch-switch-pill{act_cls}" href="{esc(oid)}.html">0{esc(other.get("order", idx + 1))} {esc(lbl)}</a>'
        )
    prev_ch = all_channels[cur_idx - 1] if cur_idx > 0 else None
    next_ch = all_channels[cur_idx + 1] if cur_idx + 1 < len(all_channels) else None

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

    related_etfs = _match_related_etfs_for_channel(cid, etf_data)
    related_etf_html = ""
    if related_etfs:
        prem_lbls = {"normal": "折溢价常规", "watch": "买前核参考净值", "high_risk": "高溢价/高危预警"}
        etf_rows = "".join(
            f"<tr>"
            f'<td class="nw"><strong>{esc(it.get("name", ""))}</strong><br><span class="code-tag">{esc(it.get("code", ""))}</span></td>'
            f'<td><span class="etf-chan-tag">{esc(it.get("channel", ""))}</span><div class="sec-sub">{esc(it.get("tracking_index", ""))}</div></td>'
            f'<td class="col-num nw"><strong>{esc(it.get("fee_total_pct", ""))}</strong></td>'
            f'<td><strong>{esc(it.get("aum", ""))}</strong><div class="sec-sub">{esc(it.get("yield_or_pe", ""))}</div></td>'
            f'<td><span class="prem-pill prem-{esc(it.get("premium_status", "normal"))}">{esc(prem_lbls.get(str(it.get("premium_status", "normal")), "常规"))}</span><div class="sec-sub">{esc(it.get("premium_note", ""))}</div></td>'
            f'<td><span class="role-pill {_etf_role_cls(it)}">{esc(it.get("action_role", ""))}</span></td>'
            f"</tr>"
            for it in related_etfs
        )
        related_etf_html = (
            '<div class="sec-head"><h2>关联重点 ETF 参数雷达</h2>'
            '<a class="btn btn-sm" href="../etfs.html">进入全部 106 只 ETF 雷达 →</a></div>'
            '<div class="table-wrap etf-table-wrap"><table class="etf-table">'
            "<thead><tr><th>ETF 名称与代码</th><th>通道与指数</th><th>年费率</th><th>规模与特征</th><th>折溢价状态</th><th>当前定位</th></tr></thead>"
            f"<tbody>{etf_rows}</tbody></table></div>"
        )

    nav_left = (
        f'<a class="btn" href="{esc(prev_ch["id"])}.html">← 0{esc(prev_ch.get("order", ""))} {esc(prev_ch.get("short_name") or prev_ch.get("name", ""))}</a>'
        if prev_ch
        else '<a class="btn" href="../channels.html">← 返回多元渠道总览</a>'
    )
    nav_right = (
        f'<a class="btn btn-primary" href="{esc(next_ch["id"])}.html">0{esc(next_ch.get("order", ""))} {esc(next_ch.get("short_name") or next_ch.get("name", ""))} →</a>'
        if next_ch
        else '<a class="btn btn-primary" href="../etfs.html">前往全球 ETF 雷达 →</a>'
    )

    return f"""
    <div class="doc-toolbar no-print">
      <div class="doc-toolbar-left">
        <nav class="breadcrumb" aria-label="面包屑">
          <a href="../index.html">总览</a>
          <span class="bc-sep">/</span>
          <a href="../channels.html">多元渠道</a>
          <span class="bc-sep">/</span>
          <span>0{esc(order)} {esc(ch.get("short_name") or ch.get("name", ""))}</span>
        </nav>
        <div class="doc-meta-pills">
          <span class="meta-pill">{esc(ch.get("category_label", ""))}</span>
          <span class="meta-pill">更新：{esc(as_of)}</span>
        </div>
      </div>
      <div class="doc-toolbar-right">
        <a class="btn btn-sm" href="../index.html#sec-multi-channels">回首页全渠道</a>
        <a class="btn btn-sm" href="../channels.html">配置模板与排雷</a>
        <a class="btn btn-sm" href="../etfs.html">ETF 雷达</a>
      </div>
    </div>

    <nav class="ch-switcher" aria-label="切换其他多元投资渠道">
      {"".join(switch_pills)}
    </nav>

    <section class="ch-detail-hero">
      <div class="ch-head" style="border-bottom-color:rgba(255,255,255,0.16);">
        <div class="ch-head-left">
          <span class="ch-num">0{esc(order)}</span>
          <h1 style="margin:0;font-size:22px;color:#fffefb;">{esc(ch.get("name", ""))}</h1>
          <span class="ch-badge">{esc(ch.get("badge", ""))}</span>
        </div>
        <span class="ch-status ch-tone-{tone}">{esc(ch.get("status_tag", ""))}</span>
      </div>
      <p class="channels-hero-sub" style="margin-bottom:10px;">{esc(ch.get("summary", ""))}</p>
      {f'<div class="channels-mutex" style="margin-bottom:0;">🛑 跨市场风控同步：{esc(mutex_note)}</div>' if mutex_note else ''}
    </section>

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

    {related_etf_html}

    <div class="ch-detail-nav">
      {nav_left}
      <a class="btn" href="../index.html">返回首页总览</a>
      {nav_right}
    </div>
    """


def _render_home_etf_showcase(etf_data: dict[str, Any] | None, total_pool: int) -> str:
    """Render concise separate ETF channel overview cards on index.html linking directly to filtered etfs.html views."""
    if not isinstance(etf_data, dict):
        return ""
    etfs = [x for x in (etf_data.get("etfs") or []) if isinstance(x, dict)]
    if not etfs:
        return ""

    as_of = str(etf_data.get("as_of_label") or "最新班次")
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in etfs:
        by_market[str(it.get("market", ""))].append(it)

    groups = [
        ("a-share", "🇨🇳 A 股核心 ETF", by_market["a-share"], "宽基 A500 · 自由现金流 · 红利低波 · 行业地板费", "etfs.html#market=a-share"),
        ("hk-stock", "🇭🇰 港股三通道 ETF", by_market["hk-stock"], "离岸免印花税 · 境内非 QDII 港股通 · 境内 QDII", "etfs.html#market=hk-stock"),
        ("us-stock", "🇺🇸 美股核心 ETF", by_market["us-stock"], "0.02%–0.08% 地板费宽基 · 11 行业 · 美元短债盾", "etfs.html#market=us-stock"),
        ("global", "🌐 爱尔兰 UCITS 与全球", by_market["global"], "免美国 40% 遗产税 · VWRA / IB01 · 日印欧非美", "etfs.html#market=global"),
        ("multi-asset", "🛡️ 债券 / 转债 / 商品", by_market["multi-asset"], "短融/科创债 · 投资级转债 · 豆粕贴水与 LOF 排雷", "etfs.html#market=multi-asset"),
    ]
    summary_cards: list[str] = []
    for _, title, items, sub, href in groups:
        low_cnt = sum(1 for x in items if isinstance(x.get("fee_num"), (int, float)) and x["fee_num"] <= 0.20)
        risk_cnt = sum(1 for x in items if x.get("premium_status") == "high_risk")
        samples = [x for x in items if not x.get("gold_locked")][:3]
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
        codes_str = "、".join(f'{x.get("code", "")}（{x.get("name", "")}）' for x in high_risks[:4])
        extra = f" 等 {len(high_risks)} 只" if len(high_risks) > 4 else ""
        alert_html = (
            f'<a class="home-etf-alert" href="etfs.html#preset=high-risk">'
            f'<span>⚠️ <strong>高溢价 / 高危预警</strong>：{esc(codes_str)}{extra} — 点击进入排雷清单</span>'
            f'<span class="nw">立即查看 →</span>'
            f"</a>"
        )

    return f"""
    <div class="sec-head" id="sec-etf-radar">
      <h2>全球 {len(etfs)} 只重点 ETF 通道分类入口（基准 {esc(as_of)}）</h2>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <a href="etfs.html" class="btn btn-sm btn-primary">全部 {len(etfs)} 只 ETF 雷达 →</a>
        <a href="screener.html" class="btn btn-sm">全部 {total_pool} 股 7 维深研 →</a>
      </div>
    </div>
    <div class="home-etf-grid-5">{"".join(summary_cards)}</div>
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
    return '<span class="ed-pill ed-main">主刊</span>'


def _render_score_meter(score_num: float | None, score_str: str) -> str:
    val = score_num if score_num is not None else 0.0
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
        f'<div class="score-meter" aria-hidden="true">{"".join(segs)}</div>'
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


def build_cockpit_page(
    gold_snap: dict,
    eq_state: dict,
    latest_by_market: dict[str, DailyItem],
    stock_counts: dict[str, int],
    *,
    channels_data: dict[str, Any] | None = None,
    etf_data: dict[str, Any] | None = None,
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

    gold_as_of = str(gold_snap.get("as_of_bjt") or gold_snap.get("as_of_short") or "")
    eq_as_of = fmt_cst_iso(str(eq_state.get("as_of_cst") or ""))
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
    if gold_spot is not None:
        gold_spot_val = (
            f"${gold_spot:,.2f} {_fmt_chg_span(gold_chg)}" if gold_chg is not None else f"${gold_spot:,.2f}"
        )
    else:
        gold_spot_val = "待核"
    gold_asia_sub = f"亚盘约 ${gold_asia_open:,.0f}" if gold_asia_open is not None else "纽约官收基准"
    gold_autd_night = _positive_quote(gold_snap.get("sge_autd_night_rmb"))
    gold_autd_day = _positive_quote(gold_snap.get("sge_autd_day_rmb"))
    gold_dfii_val = _fmt_num(gold_snap.get("dfii10_live_pct"), ".2f", suffix="%")
    gold_verdict = str(gold_snap.get("tier_cover_sub") or gold_snap.get("tier_status_sub") or "")
    rmb_ch = gold_snap.get("rmb_channels") or {}
    bank_bar = _positive_quote(rmb_ch.get("bank_bar_rmb"))
    etf_cn = _resolve_etf_cn(gold_snap)

    # SGE Au(T+D) session-aware display: >= 15:00 headlines day session; < 15:00 headlines night session
    gold_as_of_short = str(gold_snap.get("as_of_short") or "")
    m_hr = re.search(r"\b(\d{2}):\d{2}\b", gold_as_of_short)
    gold_hour = int(m_hr.group(1)) if m_hr else 7
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
        sub_parts = [f"夜盘 {gold_autd_night:.2f}" if gold_autd_night is not None else "", bank_bar_txt]
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
    vix_high_label = f"盘中峰 {vix_high:.2f}" if vix_high is not None else "盘中峰待核"
    vix_thr = _safe_float(brake.get("vix_brake_threshold"))
    if vix_thr is None:
        vix_thr = 30.0
    if vix_close is None:
        vix_chip = ("chip-warn", "待核")
        vix_meter_pct = 0.0
    else:
        vix_caution = (vix_high is not None and vix_high >= vix_thr) or vix_close >= 24
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

    # Household Composite Allocation (100% null-safe)
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
                '<a class="btn btn-sm" href="screener.html#preset=ah-inverted">在股池中查看倒挂股 →</a>'
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
            f"四市场同步防守：黄金维持{gold_tier_short}（暂不新买 · {gold_pass}），"
            f"A/港/美股严守红灯仓位上限{def_tail}，耐心等待宏观与四关信号明确。"
        )
    else:
        gold_act = f"{gold_tier_short}（暂不新买）" if (not gold_new_buy or gold_tier_code == "Tier 0") else f"{gold_tier_short}（按档分批）"
        hero_verdict = (
            f"黄金{gold_act}（{gold_pass}）；三市大盘水温 A股 {a_score} · 港股 {hk_score} · 美股 {us_score}，"
            "按红绿灯机械上限分账户严控回撤。"
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

    flagship_shelf_html = _render_flagship_web_shelf(
        {"a-share": a_pool, "hk-stock": hk_pool, "us-stock": us_pool},
    )

    home_channels_section_html = ""
    ch_count_num = 0
    if isinstance(channels_data, dict):
        ch_list = channels_data.get("channels") if isinstance(channels_data.get("channels"), list) else []
        ch_count_num = len(ch_list)
        if ch_list:
            ch_as_of = str(channels_data.get("as_of_label") or eq_as_of or "最新班次")
            ch_anchors = channels_data.get("macro_anchors") if isinstance(channels_data.get("macro_anchors"), list) else []
            home_macro_cards = "".join(
                f'<div class="home-macro-card">'
                f'<div class="home-macro-lbl">{esc(a.get("label", ""))}</div>'
                f'<div class="home-macro-val">{esc(a.get("value", ""))}</div>'
                f"</div>"
                for a in ch_anchors
                if isinstance(a, dict)
            )
            home_channels_section_html = f"""
    <div class="sec-head" id="sec-multi-channels">
      <h2>中国大陆 {ch_count_num} 大个人多元投资渠道（点击各卡片进独立详情）</h2>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        <span class="sec-sub">基准：{esc(ch_as_of)}</span>
        <a href="channels.html" class="btn btn-sm">配置模板与 6 大排雷 →</a>
      </div>
    </div>
    {f'<div class="home-macro-bar"><div class="home-macro-grid">{home_macro_cards}</div></div>' if home_macro_cards else ''}
    <section class="filter-panel">
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-ch-cat="all">全部 {ch_count_num} 大渠道</button>
        <button type="button" class="filter-pill" data-ch-cat="fixed_income">固收与票息（债券 / 基金理财）</button>
        <button type="button" class="filter-pill" data-ch-cat="cash">现金与短期流动（逆回购 / 大额存单）</button>
        <button type="button" class="filter-pill" data-ch-cat="cross_border">跨境与汇率（QDII / 北向互认）</button>
        <button type="button" class="filter-pill" data-ch-cat="hybrid">股债与实体（可转债 / 公募 REITs）</button>
        <button type="button" class="filter-pill" data-ch-cat="alternatives">独立抗通胀（非金大宗商品 ETF）</button>
      </div>
      <div class="screener-bar" style="margin:0;">
        <strong id="ch-count" role="status">显示 {ch_count_num} / {ch_count_num} 大合规个人投资渠道</strong>
        <a href="channels.html" class="btn btn-sm">查看组合模板与排雷红线 →</a>
      </div>
    </section>
    <section class="channel-list">
      {_render_channel_overview_cards(ch_list)}
    </section>
    """

    home_etf_section_html = _render_home_etf_showcase(etf_data, total_pool)
    etf_count_num = len((etf_data or {}).get("etfs") or []) if isinstance(etf_data, dict) else 0

    jump_pills: list[str] = ['<a class="home-jump-pill" href="#sec-core-markets">① 四大核心市场（金/A/港/美）</a>']
    if home_channels_section_html:
        jump_pills.append(f'<a class="home-jump-pill" href="#sec-multi-channels">② {ch_count_num} 大多元渠道卡片</a>')
    if home_etf_section_html:
        jump_pills.append(f'<a class="home-jump-pill" href="#sec-etf-radar">③ 5 大 ETF 通道入口</a>')
    jump_pills.append('<a class="home-jump-pill" href="#sec-risk-radar">④ 风险雷达与家庭总账</a>')
    jump_pills.append('<a class="home-jump-pill" href="#sec-latest-dailies">⑤ 最新早晚报与全景手册</a>')
    jump_bar_html = f'<nav class="home-jump-bar" aria-label="首页版块快捷导航">{"".join(jump_pills)}</nav>'

    coverage_parts = [f"{total_pool} 家跨市场核心公司"]
    if ch_count_num:
        coverage_parts.append(f"{ch_count_num} 大个人多元渠道")
    if etf_count_num:
        coverage_parts.append(f"{etf_count_num} 只全球重点 ETF")
    coverage_summary = " · ".join(coverage_parts)

    return f"""
    <section class="hero-deck">
      <div class="hero-main">
        <div class="hero-top">
          <span class="live-pill"><span class="live-pulse"></span>{esc(alert_label)}</span>
          <span class="live-cadence">每日 07:30 早报 · 18:00 晚报（北京时间）</span>
        </div>
        <h1 class="live-title">全球全渠道投资 10 秒水温驾驶舱</h1>
        <p class="hero-verdict">{esc(hero_verdict)}</p>
        <div class="live-meta-row">
          <span><strong>黄金快照</strong>：{esc(gold_as_of or "待核")}</span>
          <span><strong>三市与渠道快照</strong>：{esc(eq_as_of or "待核")}</span>
          <span><strong>覆盖全版图</strong>：{esc(coverage_summary)}</span>
        </div>
        <div class="hero-cta-row">
          {f'<a class="hero-cta hero-cta-primary" href="#sec-multi-channels">直看 {ch_count_num} 大多元渠道卡片 ↓</a>' if home_channels_section_html else f'<a class="hero-cta hero-cta-primary" href="screener.html">打开 {total_pool} 股交互筛选器 →</a>'}
          <a class="hero-cta" href="etfs.html">全球 ETF 雷达</a>
          <a class="hero-cta" href="screener.html">{total_pool} 股 7 维筛选器</a>
          <a class="hero-cta" href="scorecard.html">公开记分卡</a>
          <a class="hero-cta" href="archive.html">历史档案</a>
        </div>
      </div>
      <div class="hero-pulse" aria-label="四市场实时水温速览">
        <a class="pulse-row pulse-gold" href="daily/gold-latest.html">
          <span class="pulse-mkt">黄金 XAU</span>
          <span class="pulse-val">{_fmt_num(gold_spot, ",.2f", prefix="$")}</span>
          <span class="pulse-meta"><span class="pulse-dot {_dot_css_class(gold_lamp_cls)}"></span><span class="pulse-score">{esc(gold_tier_short)} · {esc(gold_pass)}</span></span>
        </a>
        <a class="pulse-row pulse-a-share" href="daily/a-share-latest.html">
          <span class="pulse-mkt">A 股 · 沪深300</span>
          <span class="pulse-val">{a_csi300_val}</span>
          <span class="pulse-meta"><span class="pulse-dot {_dot_css_class(a_lamp_cls)}"></span><span class="pulse-score">{esc(a_score)}</span></span>
        </a>
        <a class="pulse-row pulse-hk-stock" href="daily/hk-stock-latest.html">
          <span class="pulse-mkt">港股 · 恒生</span>
          <span class="pulse-val">{hk_hsi_val}</span>
          <span class="pulse-meta"><span class="pulse-dot {_dot_css_class(hk_lamp_cls)}"></span><span class="pulse-score">{esc(hk_score)}</span></span>
        </a>
        <a class="pulse-row pulse-us-stock" href="daily/us-stock-latest.html">
          <span class="pulse-mkt">美股 · 标普500</span>
          <span class="pulse-val">{us_sp_val}</span>
          <span class="pulse-meta"><span class="pulse-dot {_dot_css_class(us_lamp_cls)}"></span><span class="pulse-score">{esc(us_score)}</span></span>
        </a>
      </div>
    </section>

    {jump_bar_html}
    {disclosure_html}

    <div class="sec-head" id="sec-core-markets" style="margin-top:6px;">
      <h2>四大核心市场红绿灯水温卡片</h2>
      <span class="sec-sub">所有指标直连单一真相快照，严守机械仓位红线</span>
    </div>

    <section class="market-grid">
      <article class="m-card m-gold">
        <div class="m-card-head">
          <div>
            <div class="m-card-name">🥇 黄金（单一真相源）</div>
            <div class="m-card-sub">四步买金红绿灯 · 当前通过 {esc(gold_pass)}</div>
          </div>
          <span class="lamp-pill {gold_lamp_cls}"><span class="lamp-dot"></span>{esc(gold_tier_short)} · {esc(gold_pass)}</span>
        </div>
        <div class="m-hero-row">
          <div class="m-hero-main">
            <div class="m-hero-lbl">纽约现货金（美元/盎司）</div>
            <div class="m-hero-num">{gold_spot_val}</div>
            <div class="m-hero-sub">{esc(gold_asia_sub)}</div>
          </div>
        </div>
        {gold_gate_strip_html}
        <div class="m-stat-strip">
          <div class="m-stat">
            <div class="m-stat-lbl">{esc(sge_main_lbl)}</div>
            <div class="m-stat-val">{esc(sge_main_val)}</div>
            <div class="m-stat-sub">{esc(sge_sub_txt)}</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">10 年美债真实利率 DFII10</div>
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
          <a class="btn btn-primary" href="daily/gold-latest.html">最新日报 →</a>
          <a class="btn" href="reports/gold.html">跨世纪主报告</a>
          <a class="btn" href="scorecard.html#gold-scorecard">记分卡</a>
        </div>
      </article>

      <article class="m-card m-a">
        <div class="m-card-head">
          <div>
            <div class="m-card-name">🇨🇳 中国 A 股</div>
            <div class="m-card-sub">七维大盘体检 · {a_pool} 只核心龙头池</div>
          </div>
          <span class="lamp-pill {a_lamp_cls}"><span class="lamp-dot"></span>{esc(a_lamp_lbl)} · {esc(a_score)}</span>
        </div>
        <div class="m-hero-row">
          <div class="m-hero-main">
            <div class="m-hero-lbl">沪深 300 基准</div>
            <div class="m-hero-num">{a_csi300_val}</div>
            <div class="m-hero-sub">上证 {a_sse_val} · 4年成本线 {a_200w_val}</div>
          </div>
        </div>
        {_render_score_meter(a_score_num, a_score)}
        <div class="m-stat-strip">
          <div class="m-stat">
            <div class="m-stat-lbl">股票仓位上限</div>
            <div class="m-stat-val">{a_eq_cap_val}</div>
            <div class="m-stat-sub">余下稳守国债 / 转债 / 现金</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">前瞻 / 静态 ERP</div>
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
          <a class="btn btn-primary" href="daily/a-share-latest.html">最新日报 →</a>
          <a class="btn" href="reports/a-share.html">全景手册 ({a_pool}股)</a>
          <a class="btn" href="screener.html#market=a-share">A 股 7 维股池</a>
        </div>
      </article>

      <article class="m-card m-hk">
        <div class="m-card-head">
          <div>
            <div class="m-card-name">🇭🇰 中国香港股市</div>
            <div class="m-card-sub">联汇双通道体检 · {hk_pool} 只核心龙头池</div>
          </div>
          <span class="lamp-pill {hk_lamp_cls}"><span class="lamp-dot"></span>{esc(hk_lamp_lbl)} · {esc(hk_score)}</span>
        </div>
        <div class="m-hero-row">
          <div class="m-hero-main">
            <div class="m-hero-lbl">恒生指数基准</div>
            <div class="m-hero-num">{hk_hsi_val}</div>
            <div class="m-hero-sub">恒科 {hk_hstech_val} · 200日线 {hk_200d_val}</div>
          </div>
        </div>
        {_render_score_meter(hk_score_num, hk_score)}
        <div class="m-stat-strip">
          <div class="m-stat">
            <div class="m-stat-lbl">离岸 / 港股通上限</div>
            <div class="m-stat-val">{hk_off_cap_val} / {hk_on_cap_val}</div>
            <div class="m-stat-sub">AH 溢价指数 {hk_hsahp_val}</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">HIBOR 1M / 总结余</div>
            <div class="m-stat-val">{hibor_value} / {hkma_short_val}</div>
            <div class="m-stat-sub">美元/港元 {usd_hkd_value}（紧盯 7.85）</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">美元 / 人民币锚 ERP</div>
            <div class="m-stat-val">{hk_erp_usd_val} / {hk_erp_cny_val}</div>
            <div class="m-stat-sub">{hk_pool} 只龙头 · 南向年内 {hk_sb_ytd_val}</div>
          </div>
        </div>
        <div class="m-verdict"><strong>防踏空升级线：</strong>{esc(hk_m.get("fomo_threshold", ""))}</div>
        <div class="m-actions">
          <a class="btn btn-primary" href="daily/hk-stock-latest.html">最新日报 →</a>
          <a class="btn" href="reports/hk-stock.html">全景手册 ({hk_pool}股)</a>
          <a class="btn" href="screener.html#market=hk-stock">港股 7 维股池</a>
        </div>
      </article>

      <article class="m-card m-us">
        <div class="m-card-head">
          <div>
            <div class="m-card-name">🇺🇸 美国股市</div>
            <div class="m-card-sub">政策市五维雷达 · {us_pool} 只全板块龙头</div>
          </div>
          <span class="lamp-pill {us_lamp_cls}"><span class="lamp-dot"></span>{esc(us_lamp_lbl)} · {esc(us_score)}</span>
        </div>
        <div class="m-hero-row">
          <div class="m-hero-main">
            <div class="m-hero-lbl">标普 500 基准</div>
            <div class="m-hero-num">{us_sp_val}</div>
            <div class="m-hero-sub">10Y 美债 {us10y_val} · 200日线 {us_200d_val}</div>
          </div>
        </div>
        {_render_score_meter(us_score_num, us_score)}
        <div class="m-stat-strip">
          <div class="m-stat">
            <div class="m-stat-lbl">100% 闭环资产配置</div>
            <div class="m-stat-val">{esc(us_alloc_str)}</div>
            <div class="m-stat-sub">科技新增严控 {us_tech_cap_val}</div>
          </div>
          <div class="m-stat">
            <div class="m-stat-lbl">前瞻 / 静态 ERP</div>
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
          <a class="btn btn-primary" href="daily/us-stock-latest.html">最新日报 →</a>
          <a class="btn" href="reports/us-stock.html">全景手册 ({us_pool}股)</a>
          <a class="btn" href="screener.html#market=us-stock">美股 7 维股池</a>
        </div>
      </article>
    </section>

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
              <span class="breaker-name">VIX 恐慌指数</span>
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
              <span class="breaker-name">10 年期美债 US10Y</span>
              <span class="status-chip {us10y_chip[0]}">{us10y_chip[1]}</span>
            </div>
            <div class="breaker-val">{us10y_val}</div>
            <div class="breaker-meter"><div class="breaker-meter-fill {_breaker_fill_cls(us10y_chip[0])}" style="width:{us10y_meter_pct:.0f}%;"></div></div>
            <div class="breaker-thr">熔断线：突破 {us10y_thr:.2f}%</div>
          </div>
          <div class="breaker-item">
            <div class="breaker-top">
              <span class="breaker-name">香港金管局总结余</span>
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
          <span>⚖️ 三市股权风险溢价（ERP）横向标尺</span>
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
          <div class="alloc-seg" style="width:{eq_pct}%;background:#1d4ed8;" title="股票底座 {eq_pct}%">{eq_seg_lbl}</div>
          <div class="alloc-seg" style="width:{cb_pct}%;background:#0f766e;" title="可转债 {cb_pct}%">{cb_seg_lbl}</div>
          <div class="alloc-seg" style="width:{bc_pct}%;background:#475569;" title="国债短债与现金 {bc_pct}%">{bc_seg_lbl}</div>
          <div class="alloc-seg" style="width:{gd_pct}%;background:#b45309;" title="存量黄金 {gd_pct}%">{gd_seg_lbl}</div>
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
          <span>🌐 全球大宗商品与核心汇率镜像</span>
          <a href="screener.html" class="btn btn-sm">打开 {total_pool} 股交互筛选器 →</a>
        </div>
        <div class="chip-grid">
          <div class="mirror-chip">
            <div class="mirror-lbl">纽约现货金</div>
            <div class="mirror-val">{_fmt_num(gold_spot, ",.2f", prefix="$")}</div>
            <div class="mirror-sub">{_fmt_chg_span(gold_chg)} · {esc(gold_mirror_badge)}</div>
          </div>
          <div class="mirror-chip">
            <div class="mirror-lbl">{esc(brent_lbl)}</div>
            <div class="mirror-val">{brent_val}</div>
            <div class="mirror-sub">{_fmt_chg_span(brent_chg)} · WTI {wti_val}</div>
          </div>
          <div class="mirror-chip">
            <div class="mirror-lbl">纽约期铜 COMEX</div>
            <div class="mirror-val">{copper_val}</div>
            <div class="mirror-sub">{_fmt_chg_span(copper_chg)} · {esc(copper_regime_cn)}</div>
          </div>
          <div class="mirror-chip">
            <div class="mirror-lbl">比特币 BTC</div>
            <div class="mirror-val">{btc_val}</div>
            <div class="mirror-sub">{btc_sub_html}</div>
          </div>
          <div class="mirror-chip">
            <div class="mirror-lbl">{rmb_label}</div>
            <div class="mirror-val">{rmb_value}</div>
            <div class="mirror-sub">CFETS 中间价 {cfets_value}</div>
          </div>
          <div class="mirror-chip">
            <div class="mirror-lbl">美元 / 港元</div>
            <div class="mirror-val">{usd_hkd_value}</div>
            <div class="mirror-sub">弱方兑换保证线 7.850</div>
          </div>
        </div>
      </div>
      {ah_panel_html}
    </section>

    <div class="sec-head" id="sec-latest-dailies">
      <h2>四市场最新早晚报速递</h2>
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
    stock_counts: dict[str, int] | None = None,
    item: DailyItem | None = None,
    prev_item: DailyItem | None = None,
    next_item: DailyItem | None = None,
    is_latest: bool = False,
) -> str:
    """Build contextual editorial document toolbar (breadcrumb + metadata pills + pure-web actions)."""
    mm = MARKET_META[market]
    sc = stock_counts or {}

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
            '<a class="btn btn-sm" href="../channels.html">8大多元渠道</a>',
            '<a class="btn btn-sm" href="../etfs.html">ETF雷达</a>',
        ]
    else:
        assert item is not None
        crumb_tail = f"{item.date_str} {item.session_label}"
        ed_lbl = {"main": "深度主刊", "light": "轻刊", "holiday_watch": "守望刊"}.get(item.edition_type, "深度主刊")
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
        '<span class="bc-sep">/</span>'
        f'<a href="../archive.html#{market}">{esc(mm["short"])}</a>'
        '<span class="bc-sep">/</span>'
        f'<span>{esc(crumb_tail)}</span>'
        "</nav>"
        f'<div class="doc-meta-pills">{"".join(p for p in meta_pills if p)}</div>'
        "</div>"
        f'<div class="doc-toolbar-right">{"".join(b for b in right_btns if b)}</div>'
        "</div>"
    )


_COLOR_MARKS: dict[str, str] = {"g": "●", "b": "◆", "y": "▲", "r": "×"}


def _render_static_screener_row(stock: dict[str, Any]) -> str:
    col = str(stock["color"])
    mark = _COLOR_MARKS.get(col, "●")
    pe_num = stock.get("pe_num")
    div_pct = stock.get("div_pct")
    ah_pct = stock.get("ah_pct")
    gap = stock.get("anchor_gap_pct")

    pe_chip = (
        f'<span class="val-chip">PE {pe_num:.1f}x</span>'
        if isinstance(pe_num, (int, float))
        else f'<span class="val-chip">{esc(stock["valuation"])}</span>'
    )
    div_ah_chips: list[str] = []
    if isinstance(div_pct, (int, float)):
        div_ah_chips.append(f'<span class="val-chip">息 {div_pct:.1f}%</span>')
    if isinstance(ah_pct, (int, float)):
        div_ah_chips.append(f'<span class="val-chip">AH {ah_pct:+.1f}%</span>')
    div_ah_html = (
        f'<div class="val-chips">{"".join(div_ah_chips)}</div>'
        if div_ah_chips
        else '<span class="sec-sub">—</span>'
    )
    anchor_html = ""
    if isinstance(gap, (int, float)):
        a_cls = "anchor-in" if gap <= 0 else ("anchor-near" if gap <= 12.0 else "anchor-far")
        anchor_html = f'<span class="anchor-badge {a_cls}">距锚 {gap:+.1f}%</span> '

    d_btn = (
        f' <button type="button" class="dossier-btn" data-dossier-key="{esc(stock["market"])}:{esc(stock["code"])}">7维深研</button>'
        if stock.get("dossier")
        else ""
    )
    return (
        f'<tr class="row-{esc(col)}" data-market="{esc(stock["market"])}">'
        f'<td><span class="mkt-badge mkt-{esc(stock["market"])}">{esc(stock["market_label"])}</span></td>'
        f'<td class="col-sticky"><strong>{esc(stock["name"])}</strong> <span class="code-tag">{esc(stock["code"])}</span></td>'
        f'<td class="nw">{esc(stock["sector"])}</td>'
        f'<td><div class="nw"><strong>{esc(stock["price"])}</strong></div><div class="val-chips">{pe_chip}</div></td>'
        f"<td>{div_ah_html}</td>"
        f'<td><span class="act-pill act-{esc(col)}">{mark} {esc(stock["action_label"])}</span></td>'
        f'<td>{anchor_html}{esc(stock["summary"])}{d_btn} <a class="nw" href="{esc(stock["report_url"])}">手册 →</a></td>'
        f"</tr>"
    )


def merge_stock_dossiers(
    stocks: list[dict[str, Any]], dossiers_payload: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Attach 7-dimension institutional deep-research dossiers onto matching pool stocks."""
    if not isinstance(dossiers_payload, dict):
        return stocks
    dmap = dossiers_payload.get("dossiers")
    if not isinstance(dmap, dict):
        return stocks
    for st in stocks:
        key = f"{st.get('market', '')}:{st.get('code', '')}"
        d = dmap.get(key)
        if isinstance(d, dict):
            st["dossier"] = {
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
            }
    return stocks


def build_channels_page(channels_data: dict[str, Any] | None) -> str:
    """Render the dedicated 8 Personal Multi-Asset Investment Channels page (channels.html)."""
    data = channels_data if isinstance(channels_data, dict) else {}
    headline = str(data.get("headline") or "中国大陆个人投资者 8 大合规多元投资渠道全景调研")
    subtitle = str(
        data.get("subtitle")
        or "系统追踪债券、公募基金理财、国债逆回购、场内外 QDII 与香港北向互认、大额存单、可转债、公募 REITs 与非黄金大宗商品 ETF"
    )
    as_of = str(data.get("as_of_label") or "最新班次")
    mutex_note = str(data.get("gold_mutex_note") or "")
    anchors = data.get("macro_anchors") if isinstance(data.get("macro_anchors"), list) else []
    channels = data.get("channels") if isinstance(data.get("channels"), list) else []
    templates = data.get("allocation_templates") if isinstance(data.get("allocation_templates"), list) else []
    red_flags = data.get("red_flags") if isinstance(data.get("red_flags"), list) else []
    proc = data.get("research_process") if isinstance(data.get("research_process"), dict) else {}

    anchor_html = "".join(
        f'<div class="macro-card">'
        f'<div class="macro-lbl">{esc(a.get("label", ""))}</div>'
        f'<div class="macro-val">{esc(a.get("value", ""))}</div>'
        f'<div class="macro-note">{esc(a.get("note", ""))}</div>'
        f"</div>"
        for a in anchors
        if isinstance(a, dict)
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

    rf_html = "".join(
        f'<div class="redflag-card"><strong>⛔ {esc(rf.get("title", ""))}</strong>{esc(rf.get("detail", ""))}</div>'
        for rf in red_flags
        if isinstance(rf, dict)
    )

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

    return f"""
    <section class="channels-hero">
      <div class="cover-tag">8 大个人合规多元投资渠道 · {esc(as_of)}</div>
      <h1>{esc(headline)}</h1>
      <p class="channels-hero-sub">{esc(subtitle)}</p>
      {f'<div class="channels-mutex">🛑 跨市场风控同步：{esc(mutex_note)}</div>' if mutex_note else ''}
      <div class="macro-strip">{anchor_html}</div>
    </section>

    <section class="filter-panel">
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-ch-cat="all">全部 8 大渠道</button>
        <button type="button" class="filter-pill" data-ch-cat="fixed_income">固收与票息（债券 / 基金理财）</button>
        <button type="button" class="filter-pill" data-ch-cat="cash">现金与短期流动（逆回购 / 大额存单）</button>
        <button type="button" class="filter-pill" data-ch-cat="cross_border">跨境与汇率（QDII / 北向互认）</button>
        <button type="button" class="filter-pill" data-ch-cat="hybrid">股债与实体（可转债 / 公募 REITs）</button>
        <button type="button" class="filter-pill" data-ch-cat="alternatives">独立抗通胀（非金大宗商品 ETF）</button>
      </div>
      <div class="screener-bar" style="margin:0;">
        <strong id="ch-count" role="status">显示 {len(channels)} / {len(channels)} 大合规个人投资渠道</strong>
        <a href="etfs.html" class="btn btn-sm">进入全球 100+ ETF 深度雷达 →</a>
      </div>
    </section>

    <section class="channel-list">
      {ch_cards_rendered}
    </section>

    <div class="sec-head">
      <h2>三大落地组合配置模板（与黄金及三市权益互补）</h2>
      <span class="sec-sub">以下为除股票与存量黄金外单独划出的多元防御/增强资金内部配比</span>
    </div>
    <section class="tpl-grid">{tpl_html}</section>

    <div class="sec-head">
      <h2>中国大陆 6 大高危“伪投资”排雷红线</h2>
      <span class="sec-sub">在 10 年国债 1.59% 环境下，凡宣称保本高息 6%–8%+ 一律一票否决</span>
    </div>
    <section class="redflag-grid">{rf_html}</section>

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


def build_etfs_page(etf_data: dict[str, Any] | None) -> str:
    """Render the interactive 100+ Global Three-Channel ETF Radar page (etfs.html)."""
    data = etf_data if isinstance(etf_data, dict) else {}
    etfs = data.get("etfs") if isinstance(data.get("etfs"), list) else []
    total = len(etfs)
    as_of = str(data.get("as_of_label") or "最新班次")
    lock_notice = str(data.get("gold_lock_notice") or "")
    rules = data.get("key_2026_rules") if isinstance(data.get("key_2026_rules"), list) else []

    cnt_m = defaultdict(int)
    for it in etfs:
        if isinstance(it, dict):
            cnt_m[str(it.get("market", ""))] += 1

    prem_lbls = {"normal": "折溢价常规", "watch": "买前核参考净值", "high_risk": "高溢价/高危预警"}
    static_rows = "".join(
        f"<tr>"
        f'<td><div><strong>{esc(it.get("name", ""))}</strong></div><div><span class="code-tag">{esc(it.get("code", ""))}</span> <span class="etf-chan-tag">{esc(it.get("category", ""))}</span></div></td>'
        f'<td><div><span class="mkt-badge mkt-{esc(it.get("market", ""))}">{esc(it.get("market_label", ""))}</span></div><div><span class="etf-chan-tag">{esc(it.get("channel", ""))}</span></div></td>'
        f'<td><div>{esc(it.get("tracking_index", ""))}</div><div class="sec-sub">{esc(it.get("yield_or_pe", ""))}</div></td>'
        f'<td class="col-num"><strong>{esc(it.get("fee_total_pct", ""))}</strong></td>'
        f'<td><div><strong>{esc(it.get("aum", ""))}</strong></div><div class="sec-sub">{esc(it.get("liquidity", ""))}</div></td>'
        f'<td><div><span class="prem-pill prem-{esc(it.get("premium_status", "normal"))}">{esc(prem_lbls.get(str(it.get("premium_status", "normal")), "常规"))}</span></div><div class="sec-sub">{esc(it.get("premium_note", ""))}</div></td>'
        f'<td><div><span class="role-pill {_etf_role_cls(it)}">{esc(it.get("action_role", ""))}</span></div><div style="margin-top:5px;"><button type="button" class="dossier-btn" style="margin-left:0;" data-etf-code="{esc(it.get("code", ""))}">深度拆解</button></div></td>'
        f"</tr>"
        for it in etfs
        if isinstance(it, dict)
    )
    safe_json = json.dumps(etfs, ensure_ascii=False).replace("</", "<\\/")
    rules_html = "".join(
        f'<div class="etf-rule-item">{esc(r)}</div>'
        for r in rules
        if isinstance(r, str) and r.strip()
    )

    return f"""
    <div class="sec-head" style="margin-top:4px;">
      <h2>全球 {total} 只重点 ETF 三通道深度雷达</h2>
      <span class="sec-sub">覆盖 A 股、港股三通道、美股原版、爱尔兰 UCITS、境内非美 QDII 及债券商品 ETF · 基准 {esc(as_of)}</span>
    </div>

    {f'<div class="etf-lock-banner">🛑 {esc(lock_notice)}</div>' if lock_notice else ''}
    {f'<div class="etf-rules-grid">{rules_html}</div>' if rules_html else ''}

    <div class="screener-stats">
      <div class="stat-tile stat-total">
        <div class="stat-tile-lbl">全通道重点 ETF</div>
        <div class="stat-tile-num">{total}</div>
      </div>
      <div class="stat-tile" style="border-top:3px solid #9f2326;">
        <div class="stat-tile-lbl">🇨🇳 A 股核心 ETF</div>
        <div class="stat-tile-num">{cnt_m["a-share"]}</div>
      </div>
      <div class="stat-tile" style="border-top:3px solid #0d6963;">
        <div class="stat-tile-lbl">🇭🇰 港股三通道 ETF</div>
        <div class="stat-tile-num">{cnt_m["hk-stock"]}</div>
      </div>
      <div class="stat-tile" style="border-top:3px solid #1b4b8a;">
        <div class="stat-tile-lbl">🇺🇸 美股与爱尔兰/全球</div>
        <div class="stat-tile-num">{cnt_m["us-stock"] + cnt_m["global"]}</div>
      </div>
      <div class="stat-tile" style="border-top:3px solid #b45309;">
        <div class="stat-tile-lbl">🛡️ 债券/转债/商品</div>
        <div class="stat-tile-num">{cnt_m["multi-asset"]}</div>
      </div>
    </div>

    <section class="filter-panel">
      <div class="preset-row" role="group" aria-label="ETF 快捷筛选">
        <button type="button" class="preset-pill active" data-etf-preset="all">全部 ETF</button>
        <button type="button" class="preset-pill" data-etf-preset="low-fee">地板费率 ≤0.20%</button>
        <button type="button" class="preset-pill" data-etf-preset="base">红灯稳健底座</button>
        <button type="button" class="preset-pill" data-etf-preset="cash-shield">本外币现金盾</button>
        <button type="button" class="preset-pill" data-etf-preset="high-risk">高溢价/高危排雷</button>
        <button type="button" class="preset-pill" data-etf-preset="hide-gold">隐藏黄金红灯锁</button>
      </div>
      <div class="filter-row">
        <div class="search-wrap">
          <input type="search" id="etf-search" class="search-input" placeholder="搜索代码 / 简称 / 跟踪指数 / 重仓股 / 联接代码（如 563360、159545、IB01、159509、红利）…" autocomplete="off">
          <button type="button" id="etf-clear" class="search-clear" aria-label="清空搜索" hidden>×</button>
          <kbd class="kbd-hint" aria-hidden="true">/</kbd>
        </div>
        <button type="button" class="btn btn-sm" id="etf-reset">重置筛选</button>
      </div>
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-etf-market="all">全部市场 ({total})</button>
        <button type="button" class="filter-pill" data-etf-market="a-share">🇨🇳 A 股 ({cnt_m["a-share"]})</button>
        <button type="button" class="filter-pill" data-etf-market="hk-stock">🇭🇰 港股 ({cnt_m["hk-stock"]})</button>
        <button type="button" class="filter-pill" data-etf-market="us-stock">🇺🇸 美股 ({cnt_m["us-stock"]})</button>
        <button type="button" class="filter-pill" data-etf-market="global">🌐 全球与爱尔兰 ({cnt_m["global"]})</button>
        <button type="button" class="filter-pill" data-etf-market="multi-asset">🛡️ 债券/转债/商品 ({cnt_m["multi-asset"]})</button>
      </div>
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-etf-channel="all">全部交易通道</button>
        <button type="button" class="filter-pill" data-etf-channel="境内场内">境内场内</button>
        <button type="button" class="filter-pill" data-etf-channel="境内非QDII港股通">境内非QDII港股通</button>
        <button type="button" class="filter-pill" data-etf-channel="境内QDII">境内QDII</button>
        <button type="button" class="filter-pill" data-etf-channel="离岸港交所">离岸港交所</button>
        <button type="button" class="filter-pill" data-etf-channel="离岸美股">离岸美股</button>
        <button type="button" class="filter-pill" data-etf-channel="爱尔兰UCITS">爱尔兰UCITS</button>
      </div>
    </section>

    <div class="screener-bar">
      <strong id="etf-count" role="status">显示 {total} / {total} 只重点 ETF</strong>
      <a href="channels.html" class="btn btn-sm">查看 8 大个人多元渠道详规 →</a>
    </div>

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

    <div class="dossier-backdrop no-print" id="etf-modal" role="dialog" aria-modal="true" aria-label="ETF 深度拆解">
      <div class="dossier-dialog">
        <div class="dossier-head">
          <div class="dossier-head-main">
            <h3 class="dossier-title" id="etf-modal-title">ETF 深度档案</h3>
            <div class="dossier-sub" id="etf-modal-sub"></div>
            <div class="dossier-badges" id="etf-modal-badges"></div>
          </div>
          <button type="button" class="ctrl-btn" data-action="close-etf" aria-label="关闭 ETF 详情">关闭 ✕</button>
        </div>
        <div class="dossier-body" id="etf-modal-body"></div>
        <div class="dossier-foot">
          <span>数据经交易所、基金定期报告与官网费率交叉核验 · 下单前请实时核对盘口参考净值</span>
          <a href="channels.html" class="btn btn-sm">查看 8 大多元渠道 →</a>
        </div>
      </div>
    </div>

    <script id="etf-data" type="application/json">{safe_json}</script>
    """


def build_screener_page(stocks: list[dict[str, Any]], benchmarks: dict[str, str]) -> str:
    total = len(stocks)
    cnt_m = defaultdict(int)
    cnt_c = defaultdict(int)
    for st in stocks:
        cnt_m[st["market"]] += 1
        cnt_c[st["color"]] += 1
        st["benchmark_time"] = benchmarks[st["market"]]
    source_labels = " · ".join(
        f"{label}（{cnt_m[slug]} 家，{esc(benchmarks[slug])}）"
        for slug, label in (("a-share", "A 股"), ("hk-stock", "港股"), ("us-stock", "美股"))
    )

    # Escape </script> safely inside embedded JSON
    safe_json = json.dumps(stocks, ensure_ascii=False).replace("</", "<\\/")
    static_rows = "".join(_render_static_screener_row(stock) for stock in stocks)

    return f"""
    <div class="sec-head" style="margin-top:4px;">
      <h2>全球 {total} 家核心龙头交互筛选器</h2>
      <span class="sec-sub">各市场数据基准取自旗舰手册附表二 · {source_labels}</span>
    </div>

    <div class="screener-stats">
      <div class="stat-tile stat-total" data-stat-color="all">
        <div class="stat-tile-lbl">全部龙头池</div>
        <div class="stat-tile-num">{total}</div>
      </div>
      <div class="stat-tile" data-stat-color="g" style="border-top:3px solid #059669;">
        <div class="stat-tile-lbl" style="color:var(--st-green-txt);">● 当下底座</div>
        <div class="stat-tile-num">{cnt_c["g"]}</div>
      </div>
      <div class="stat-tile" data-stat-color="b" style="border-top:3px solid #0072b2;">
        <div class="stat-tile-lbl" style="color:var(--st-blue-txt);">◆ 未来主攻（已锁）</div>
        <div class="stat-tile-num">{cnt_c["b"]}</div>
      </div>
      <div class="stat-tile" data-stat-color="y" style="border-top:3px solid #d97706;">
        <div class="stat-tile-lbl" style="color:var(--st-amber-txt);">▲ 分歧观察</div>
        <div class="stat-tile-num">{cnt_c["y"]}</div>
      </div>
      <div class="stat-tile" data-stat-color="r" style="border-top:3px solid #dc2626;">
        <div class="stat-tile-lbl" style="color:var(--st-red-txt);">× 高危回避</div>
        <div class="stat-tile-num">{cnt_c["r"]}</div>
      </div>
    </div>

    <section class="filter-panel">
      <div class="preset-row" role="group" aria-label="快捷筛选预设">
        <button type="button" class="preset-pill active" data-preset="all">全部龙头</button>
        <button type="button" class="preset-pill" data-preset="base">● 当下底座</button>
        <button type="button" class="preset-pill" data-preset="high-div">高股息 ≥4%</button>
        <button type="button" class="preset-pill" data-preset="near-anchor">近安全锚 ≤12%</button>
        <button type="button" class="preset-pill" data-preset="ah-inverted">A/H 倒挂折价</button>
        <button type="button" class="preset-pill" data-preset="hide-red">隐藏高危回避</button>
      </div>
      <div class="filter-row">
        <div class="search-wrap">
          <input type="search" id="scr-search" class="search-input" placeholder="搜索中文名 / 代码 / 赛道 / 关键词（如 宁德、NVDA、00883、银行、回购）…" autocomplete="off">
          <button type="button" id="scr-clear" class="search-clear" aria-label="清空搜索" hidden>×</button>
          <kbd class="kbd-hint" aria-hidden="true">/</kbd>
        </div>
        <button type="button" class="btn btn-sm" id="scr-reset">重置筛选</button>
      </div>
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-filter-market="all">全部市场 ({total})</button>
        <button type="button" class="filter-pill" data-filter-market="a-share">🇨🇳 A 股 ({cnt_m["a-share"]})</button>
        <button type="button" class="filter-pill" data-filter-market="hk-stock">🇭🇰 港股 ({cnt_m["hk-stock"]})</button>
        <button type="button" class="filter-pill" data-filter-market="us-stock">🇺🇸 美股 ({cnt_m["us-stock"]})</button>
      </div>
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-filter-color="all">全部四色阵营</button>
        <button type="button" class="filter-pill" data-filter-color="g" data-color="g">● 当下底座 ({cnt_c["g"]})</button>
        <button type="button" class="filter-pill" data-filter-color="b" data-color="b">◆ 未来主攻 ({cnt_c["b"]})</button>
        <button type="button" class="filter-pill" data-filter-color="y" data-color="y">▲ 分歧观察 ({cnt_c["y"]})</button>
        <button type="button" class="filter-pill" data-filter-color="r" data-color="r">× 高危回避 ({cnt_c["r"]})</button>
      </div>
      <div class="sector-tray" id="scr-sector-tray" aria-label="赛道多选筛选"></div>
    </section>

    <div class="screener-bar">
      <strong id="scr-count" role="status">显示 {total} / {total} 家龙头公司</strong>
      <div class="active-filters" id="scr-active-filters"></div>
    </div>

    <div class="screener-table-wrap">
      <table class="screener-table">
        <thead>
          <tr>
            <th class="sortable" data-sort="market"><button type="button" disabled>市场 ⇅</button></th>
            <th class="sortable col-sticky" data-sort="name"><button type="button" disabled>公司与代码 ⇅</button></th>
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

    <div class="dossier-backdrop no-print" id="dossier-modal" role="dialog" aria-modal="true" aria-label="个股 7 维机构深度档案">
      <div class="dossier-dialog">
        <div class="dossier-head">
          <div class="dossier-head-main">
            <h3 class="dossier-title" id="dossier-modal-title">个股 7 维深度档案</h3>
            <div class="dossier-sub" id="dossier-modal-sub"></div>
            <div class="dossier-badges" id="dossier-modal-badges"></div>
          </div>
          <button type="button" class="ctrl-btn" data-action="close-dossier" aria-label="关闭个股深度档案">关闭 ✕</button>
        </div>
        <div class="dossier-body" id="dossier-modal-body"></div>
        <div class="dossier-foot">
          <span id="dossier-modal-date">更新日期：最新班次</span>
          <a id="dossier-modal-link" href="reports/a-share.html" class="btn btn-sm">前往该市场全景手册 →</a>
        </div>
      </div>
    </div>

    <script id="screener-data" type="application/json">{safe_json}</script>
    """


def _first_int(text: str, default: int = 0) -> int:
    m = re.search(r"(\d+)", str(text or ""))
    return int(m.group(1)) if m else default


def _first_pct(text: str, default: float | None = None) -> float | None:
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)%", str(text or ""))
    return float(m.group(1)) if m else default


def parse_scorecard_stats(gold_sc_md: str, eq_sc_md: str) -> dict[str, dict[str, Any]]:
    """Extract settled/hit/partial/miss/tracking statistics from Gold & Equity SCORECARD.md files."""
    # --- Gold SCORECARD.md ---
    g_settled = g_scored = g_hit = g_partial = g_miss = g_untrig = g_track = 0
    g_full_pct: float | None = None
    g_part_pct: float | None = None
    for raw in (gold_sc_md or "").splitlines():
        st = raw.strip()
        if not (st.startswith("|") and st.endswith("|")):
            continue
        cells = _split_md_cells(st)
        if len(cells) >= 8 and "已到期" in cells[0]:
            g_settled = _first_int(cells[1])
            m_sc = re.search(r"计分\s*(\d+)", cells[1])
            g_hit = _first_int(cells[2])
            g_partial = _first_int(cells[3])
            g_miss = _first_int(cells[4])
            g_untrig = _first_int(cells[5])
            g_scored = int(m_sc.group(1)) if m_sc else (g_hit + g_partial + g_miss)
            g_full_pct = _first_pct(cells[6])
            g_part_pct = _first_pct(cells[7])
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
        for arch_path in sorted(archive_dir.glob(f"{stem}_*.md"), key=lambda p: p.name, reverse=True):
            sanitized = sanitize_public_ledger_md(
                arch_path.read_text(encoding="utf-8"),
                is_audit_log=is_audit_log,
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

    eq_sc_md = normalize_relative_md_links(eq_sc_raw_md)
    gd_sc_md = normalize_relative_md_links(protect_backticked_comments(gd_sc_raw_md))
    eq_cl_md = normalize_relative_md_links(
        (EQUITY_DIR / "daily" / "CHANGELOG.md").read_text(encoding="utf-8")
    )
    gd_cl_md = normalize_relative_md_links(
        protect_backticked_comments(
            _load_gold_ledger_with_archives("CHANGELOG", is_audit_log=False)
        )
    )
    gd_al_md = normalize_relative_md_links(
        protect_backticked_comments(
            _load_gold_ledger_with_archives("AUDIT_LOG", is_audit_log=True)
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

    return f"""
    <div class="sec-head" style="margin-top:4px;">
      <h2>公开可证伪预测记分卡与观点演进账本</h2>
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
            <div>已到期 {eq_st["settled"]} 项（计分 {eq_st["scored"]} 项）</div>
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
            <div>已到期 {gd_st["settled"]} 项（完全兑现 {gd_st["full_pct"]:.1f}%）</div>
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
    for it in dailies:
        by_date[it.date_str].append(it)

    timeline_html = ""
    for dt in sorted(by_date.keys(), reverse=True):
        day_items = sorted(
            by_date[dt],
            key=lambda x: (-int(x.hhmm), -x.rev, MARKET_ORDER.get(x.market, 9)),
        )
        cards = []
        for it in day_items:
            mm = MARKET_META[it.market]
            chart_badge = f'<span class="session-pill">{it.chart_count} 图</span>' if it.chart_count else ""
            revision_badge = f'<span class="session-pill">修订 {it.rev}</span>' if it.rev > 1 else ""
            search_text = f"{it.date_str} {mm['short']} {it.session_label} {it.title} {it.summary}".lower()
            cards.append(
                f'<a class="feed-card" href="{it.rel_url}" data-arc-item="1" '
                f'data-market="{it.market}" data-session="{it.session_key}" '
                f'data-edition-type="{esc(it.edition_type)}" data-search="{esc(search_text)}">'
                f'<div class="feed-meta">'
                f'<span class="mkt-badge mkt-{it.market}">{mm["emoji"]} {mm["short"]}</span>'
                f'{_edition_pill_html(it.edition_type)}'
                f'<span class="session-pill">{esc(it.session_label)}</span>'
                f"{revision_badge}"
                f"{chart_badge}"
                f'<span class="session-pill">约 {it.read_minutes} 分钟</span>'
                f"</div>"
                f'<div class="feed-title">{esc(it.title)}</div>'
                f'<div class="feed-summary">{esc(it.summary)}</div>'
                f"</a>"
            )
        timeline_html += (
            f'<div class="archive-day">'
            f'<div class="archive-date-hdr">{esc(dt)} <span class="sec-sub">（共 {len(cards)} 期）</span></div>'
            f'<div class="archive-list">{"".join(cards)}</div>'
            f"</div>"
        )

    return f"""
    <div class="sec-head" style="margin-top:4px;">
      <h2>四大常青旗舰全景手册</h2>
      <span class="sec-sub">{total_flagship_charts} 张原创矢量图表 · 随时查阅宏观框架与 {total_pool} 只龙头全诊断</span>
    </div>
    <section class="flagship-shelf">{shelf_html}</section>

    <div class="sec-head">
      <h2>历史早晚报时间轴</h2>
      <strong id="arc-count" class="sec-sub">共展示 {len(dailies)} 期历史日报</strong>
    </div>

    <section class="filter-panel">
      <div class="arc-search-row">
        <input type="search" id="arc-search" class="search-input" placeholder="搜索历史早晚报标题、日期或关键词（如 感恩节、核心通胀、两融、红灯）…" autocomplete="off">
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
        <button type="button" class="filter-pill" data-arc-session="midday">午报 (16:30)</button>
        <button type="button" class="filter-pill" data-arc-session="evening">晚报 (18:00)</button>
      </div>
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-arc-type="all">全部刊型</button>
        <button type="button" class="filter-pill" data-arc-type="main">深度主刊</button>
        <button type="button" class="filter-pill" data-arc-type="watch">守望 / 轻刊</button>
      </div>
    </section>

    <section class="archive-rail">{timeline_html}</section>

    <div class="empty-state" id="arc-empty" hidden>
      <div class="empty-title">未找到匹配的历史早晚报</div>
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
        for ln in md_text.splitlines():
            st = ln.strip()
            if st.startswith(">") and "一句话结论" in st:
                cleaned = re.sub(r"^>\s*\*\*一句话结论\*\*[：:]\s*", "", st)
                return clean_md_inline_plain(cleaned)
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
    eq_state = json.loads((EQUITY_DIR / "state" / "market_state.json").read_text(encoding="utf-8"))
    eq_as_of_disp = fmt_cst_iso(str(eq_state.get("as_of_cst", "")))
    channels_path = EQUITY_DIR / "state" / "multi_asset_channels.json"
    etf_path = EQUITY_DIR / "state" / "etf_universe.json"
    dossiers_path = EQUITY_DIR / "state" / "deep_dossiers.json"
    channels_data = json.loads(channels_path.read_text(encoding="utf-8")) if channels_path.is_file() else None
    etf_data = json.loads(etf_path.read_text(encoding="utf-8")) if etf_path.is_file() else None
    dossiers_data = json.loads(dossiers_path.read_text(encoding="utf-8")) if dossiers_path.is_file() else None

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
        paths = eq_mod.resolve_flagship_paths(meta)
        md_path = paths[0]
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
    stocks = merge_stock_dossiers(stocks, dossiers_data)
    stock_counts: dict[str, int] = defaultdict(int)
    for st in stocks:
        stock_counts[st["market"]] += 1
    total_pool = len(stocks)

    # The renderer always receives a new output directory.
    out_dir.mkdir(parents=True)
    for sub in ("assets", "reports", "daily", "channels"):
        (out_dir / sub).mkdir()

    # Static assets + .nojekyll + manifest.json + favicon.svg
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copyfile(ASSETS_SRC / "app.css", out_dir / "assets" / "app.css")
    shutil.copyfile(ASSETS_SRC / "app.js", out_dir / "assets" / "app.js")
    (out_dir / "assets" / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")

    manifest = {
        "name": "全球投研 · 黄金 × A股 × 港股 × 美股",
        "short_name": "全球投研",
        "description": f"机构级全球跨市场投研门户：黄金、A股、港股、美股红绿灯驾驶舱、{total_pool}只龙头筛选器与每日早晚报。",
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
    g_snap_master, _ = R.gold_report.load_master_snapshot(gold_md, allow_drift=True)
    R.gold_report.SNAP = g_snap_master
    R.gold_report.REPORT_VERSION = str(g_snap_master.get("master_version", "普通人终审定版"))
    R.gold_report.REPORT_TIMESTAMP = str(g_snap_master.get("as_of_bjt", ""))
    R.gold_report.REPORT_SHORT_DATE = str(g_snap_master.get("as_of_short", ""))
    g_cover = R.gold_report.build_cover_html()
    g_body_raw, _ = R.gold_report.convert_md_to_html_body(
        normalize_relative_md_links(protect_backticked_comments(gold_md)), docx_mode=False
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
        toc_items=g_toc,
        show_chart_modal=True,
        footer_ts=R.gold_report.REPORT_SHORT_DATE,
        content_html=render_doc_with_toc(
            toolbar_html=build_doc_toolbar(
                market="gold",
                doc_kind="flagship",
                read_minutes=g_read_min,
                chart_count=g_charts,
                has_toc=bool(g_toc),
                total_pool=total_pool,
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
    flagship_info.append(
        {
            "market": "gold",
            "badge": "🥇 黄金主报告",
            "title": "黄金跨世纪周期与普通人全景配置指南（1971–2030）",
            "baseline": R.gold_report.REPORT_SHORT_DATE,
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
            toc_items=toc,
            show_chart_modal=True,
            footer_ts=str(meta.get("benchmark_time", "")).split("（")[0],
            content_html=render_doc_with_toc(
                toolbar_html=build_doc_toolbar(
                    market=m_slug,
                    doc_kind="flagship",
                    read_minutes=read_min,
                    chart_count=n_charts,
                    has_toc=bool(toc),
                    total_pool=total_pool,
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
        flagship_info.append(
            {
                "market": m_slug,
                "badge": badge_lbl,
                "title": doc_title,
                "baseline": str(meta.get("benchmark_time", "")).split("（")[0],
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
                    "本每日研报数据均经多源官方数据库核验，仅供参考；请严守家庭资产 10%–15% 黄金上限，远离杠杆。",
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
            toolbar_html = build_doc_toolbar(
                market=item.market,
                doc_kind="daily",
                read_minutes=item.read_minutes,
                chart_count=item.chart_count,
                has_toc=bool(item.toc),
                stock_counts=stock_counts,
                item=item,
                prev_item=prev_it,
                next_item=next_it,
                is_latest=is_latest,
            )
            corrected = last_by_session[item.date_str, item.hhmm]
            if item.rev < corrected.rev:
                toolbar_html += (
                    '<div class="revision-notice no-print">'
                    "<span>此页为本班次原刊档案，后续已有修订更新。</span>"
                    f'<a class="btn btn-sm" href="{corrected.slug}.html">查看本班次修订稿 →</a>'
                    "</div>"
                )
            disclosure_inline = render_daily_disclosure(
                mk_caveats,
                item.market,
                is_latest,
                item.date_str,
                item.session_label,
            )
            doc_html = render_doc_with_toc(
                toolbar_html=toolbar_html,
                cover_html=item.cover_html,
                body_html=item.body_html,
                footer_note=item.footer_note,
                toc_items=item.toc,
                doc_kind="daily",
                disclosure_html=disclosure_inline,
            )
            full_page = render_page_shell(
                title=item.title,
                active_nav=item.market,
                base_prefix="../",
                market_attr=item.market,
                doc_kind="daily",
                edition_attr=item.edition_type,
                total_pool=total_pool,
                toc_items=item.toc,
                show_chart_modal=(item.chart_count > 0),
                footer_ts=f"{item.date_str} {item.session_label}",
                content_html=doc_html,
            )
            (out_dir / "daily" / f"{item.slug}.html").write_text(full_page, encoding="utf-8")
            if is_latest:
                latest_by_market[mk] = item
                (out_dir / "daily" / f"{mk}-latest.html").write_text(full_page, encoding="utf-8")

    # ------------------------------------------------------------------
    # C. Build Global Stock Screener (screener.html)
    # ------------------------------------------------------------------
    screener_benchmarks = {
        slug: str(eq_flagship_meta[key].get("benchmark_time") or "未标明").split("（", 1)[0]
        for key, slug, *_ in eq_specs
    }
    unique_benchmarks = set(screener_benchmarks.values())
    screener_html = render_page_shell(
        title=f"全球 {total_pool} 家核心龙头筛选器",
        active_nav="screener",
        base_prefix="",
        market_attr="overview",
        doc_kind="tool",
        total_pool=total_pool,
        footer_ts=next(iter(unique_benchmarks)) if len(unique_benchmarks) == 1 else "",
        content_html=build_screener_page(stocks, screener_benchmarks),
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
        doc_kind="tool",
        total_pool=total_pool,
        footer_ts=eq_as_of_disp,
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
        footer_ts=eq_as_of_disp,
        content_html=build_archive_page(
            dailies, flagship_info, stock_counts, total_pool, total_flagship_charts
        ),
    )
    (out_dir / "archive.html").write_text(archive_html, encoding="utf-8")

    # ------------------------------------------------------------------
    # C2. Build Multi-Asset Personal Channels (channels.html + channels/<id>.html) & ETF Radar (etfs.html)
    # ------------------------------------------------------------------
    channels_html = render_page_shell(
        title="8 大个人合规多元投资渠道总览",
        active_nav="channels",
        base_prefix="",
        market_attr="overview",
        doc_kind="tool",
        total_pool=total_pool,
        footer_ts=eq_as_of_disp,
        content_html=build_channels_page(channels_data),
    )
    (out_dir / "channels.html").write_text(channels_html, encoding="utf-8")

    channel_detail_pages = 0
    if isinstance(channels_data, dict):
        all_chs = [c for c in (channels_data.get("channels") or []) if isinstance(c, dict) and str(c.get("id", "")).strip()]
        for ch in all_chs:
            cid = str(ch["id"]).strip()
            ch_title = str(ch.get("name") or cid)
            detail_html = render_page_shell(
                title=ch_title,
                active_nav="channels",
                base_prefix="../",
                market_attr="overview",
                doc_kind="tool",
                total_pool=total_pool,
                footer_ts=str(channels_data.get("as_of_label") or eq_as_of_disp),
                content_html=build_channel_detail_page(ch, all_chs, channels_data, etf_data=etf_data),
            )
            (out_dir / "channels" / f"{cid}.html").write_text(detail_html, encoding="utf-8")
            channel_detail_pages += 1

    etf_total = len((etf_data or {}).get("etfs") or [])
    etfs_html = render_page_shell(
        title=f"全球 {etf_total} 只重点 ETF 三通道深度雷达" if etf_total else "全球重点 ETF 深度雷达",
        active_nav="etfs",
        base_prefix="",
        market_attr="overview",
        doc_kind="tool",
        total_pool=total_pool,
        footer_ts=eq_as_of_disp,
        content_html=build_etfs_page(etf_data),
    )
    (out_dir / "etfs.html").write_text(etfs_html, encoding="utf-8")

    # ------------------------------------------------------------------
    # F. Build Global Weather Cockpit (index.html)
    # ------------------------------------------------------------------
    cockpit_html = render_page_shell(
        title="全球投研总览 · 黄金 × A/港/美",
        active_nav="overview",
        base_prefix="",
        market_attr="overview",
        doc_kind="overview",
        total_pool=total_pool,
        footer_ts=eq_as_of_disp,
        content_html=build_cockpit_page(
            gold_snap,
            eq_state,
            latest_by_market,
            stock_counts,
            channels_data=channels_data,
            etf_data=etf_data,
        ),
    )
    (out_dir / "index.html").write_text(cockpit_html, encoding="utf-8")

    return {
        "out_dir": str(out_dir),
        "flagship_charts": flagship_stats,
        "flagship_total_charts": sum(flagship_stats.values()),
        "daily_pages": len(dailies),
        "latest_pages": len(latest_by_market),
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
        f"(6 core + 4 flagships + {summary['daily_pages']} dated dailies + {summary['latest_pages']} canonical latest)\n"
        f"  Flagship charts: {summary['flagship_total_charts']} {summary['flagship_charts']}\n"
        f"  Daily charts:    {summary['daily_total_charts']}\n"
        f"  Screener pool:   {summary['screener_total']} {summary['screener_by_market']}"
    )


if __name__ == "__main__":
    main()
