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
from math import isfinite
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
GOLD_DIR = REPO_ROOT / "gold"
EQUITY_DIR = REPO_ROOT / "equity"
ASSETS_SRC = SCRIPT_DIR / "web_assets"

RELEASES_BASE = "https://github.com/nanless/global-investment-research/releases"
RELEASES_TAG_URL = f"{RELEASES_BASE}/tag/latest-reports"
RELEASES_DL_BASE = f"{RELEASES_BASE}/download/latest-reports"

# Canonical 16-file ASCII kebab-case release asset map matching scripts/publish_site.py 1-to-1
RELEASE_ASSET_NAMES: dict[str, dict[str, str]] = {
    "gold": {
        "flagship_pdf": "gold-master-latest.pdf",
        "flagship_docx": "gold-master-latest.docx",
        "daily_pdf": "gold-daily-latest.pdf",
        "daily_docx": "gold-daily-latest.docx",
    },
    "a-share": {
        "flagship_pdf": "a-share-flagship-latest.pdf",
        "flagship_docx": "a-share-flagship-latest.docx",
        "daily_pdf": "a-share-daily-latest.pdf",
        "daily_docx": "a-share-daily-latest.docx",
    },
    "hk-stock": {
        "flagship_pdf": "hk-stock-flagship-latest.pdf",
        "flagship_docx": "hk-stock-flagship-latest.docx",
        "daily_pdf": "hk-stock-daily-latest.pdf",
        "daily_docx": "hk-stock-daily-latest.docx",
    },
    "us-stock": {
        "flagship_pdf": "us-stock-flagship-latest.pdf",
        "flagship_docx": "us-stock-flagship-latest.docx",
        "daily_pdf": "us-stock-daily-latest.pdf",
        "daily_docx": "us-stock-daily-latest.docx",
    },
}

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
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="60%" stop-color="#1e3a5f"/>
      <stop offset="100%" stop-color="#b45309"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="14" fill="url(#g)"/>
  <circle cx="32" cy="32" r="21" fill="none" stroke="#fbbf24" stroke-width="2.4" opacity="0.9"/>
  <polygon points="32,14 38,32 32,50 26,32" fill="#fbbf24"/>
  <circle cx="32" cy="32" r="4" fill="#0f172a"/>
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

    # Fallback: NEVER allow file:// or /Users/ or broken local .md/.pdf paths
    if lower.startswith("file://") or "/users/" in lower or lower.endswith((".md", ".pdf", ".docx")):
        return f"{base_prefix}archive.html"

    return raw_href


def _strip_local_paths_in_text(fragment: str) -> str:
    """Remove any stray file:// or /Users/... paths and internal snapshot filenames in plain text."""
    parts = _TAG_SPLIT_RE.split(fragment)
    for i in range(0, len(parts), 2):
        txt = parts[i]
        if not txt:
            continue
        if "file://" in txt or "/Users/" in txt:
            txt = re.sub(r"file:///[^\s<\"'）)》」]+", "（已归档）", txt)
            txt = re.sub(r"/Users/[^\s<\"'）)》」`]+", "（站内文档）", txt)
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
        # 3. Strip any leaked local paths in text
        seg = _strip_local_paths_in_text(seg)
        # 4. Restore any literal HTML comments that were inside code spans/blocks
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


def extract_all_stocks(a_md: str, hk_md: str, us_md: str) -> list[dict[str, str]]:
    """Extract all flagship pool stocks across A-Share, HK-Stock, and US-Stock with exact 4-color ratings."""
    stocks: list[dict[str, str]] = []

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
        summary = clean_md_inline_plain(cells[4])
        col, anchor_txt = a_color_map.get(code, ("y", ""))
        if anchor_txt and anchor_txt not in summary:
            summary = f"{summary}｜{anchor_txt}"
        stocks.append(
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
            }
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
        summary = re.sub(
            r"^[🟢🔵🟡🔴]\s*(?:🔒)?(?:当下底座|未来主攻|分歧观察|高危回避)[；;：:\s]*",
            "",
            summary_raw,
        ).strip()
        stocks.append(
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
            }
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
            }
        )

    return stocks


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


def render_page_shell(
    *,
    title: str,
    active_nav: str,
    base_prefix: str,
    content_html: str,
    market_attr: str = "overview",
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
        ("screener", f"{base_prefix}screener.html", pool_label),
        ("scorecard", f"{base_prefix}scorecard.html", "记分卡"),
        ("archive", f"{base_prefix}archive.html", "档案"),
    ]
    nav_html = "".join(
        f'<a class="nav-pill{" active" if key == active_nav else ""}" data-nav="{key}" href="{href}">{lbl}</a>'
        for key, href, lbl in nav_items
    )

    has_toc = bool(toc_items)
    toc_drawer_html = ""
    if has_toc:
        toc_drawer_html = (
            '<div class="toc-backdrop" id="toc-backdrop" role="dialog" aria-modal="true" aria-label="章节目录">'
            '<div class="toc-sheet">'
            '<div class="toc-sheet-hdr"><span>📑 报告目录</span>'
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

    dock_toc_btn = (
        '<button type="button" class="dock-btn dock-toc-btn" data-action="open-toc">📑 目录</button>'
        if has_toc
        else ""
    )
    mobile_dock_html = (
        '<div class="mobile-dock no-print" aria-label="快捷工具">'
        f"{dock_toc_btn}"
        '<button type="button" class="dock-btn" data-action="scroll-top">↑ 顶部</button>'
        '<button type="button" class="dock-btn" data-action="print">🖨️ PDF</button>'
        "</div>"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{esc(title)} ｜ 全球投研</title>
  <meta name="theme-color" content="#0f172a">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="全球投研">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="icon" type="image/svg+xml" href="{base_prefix}assets/favicon.svg">
  <link rel="manifest" href="{base_prefix}manifest.json">
  {THEME_INIT_SCRIPT}
  <link rel="stylesheet" href="{base_prefix}assets/app.css">
</head>
<body data-market="{esc(market_attr)}"{f' data-edition="{esc(edition_attr)}"' if edition_attr else ""}>
  <div class="reading-progress" id="reading-progress"></div>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand-link" href="{base_prefix}index.html">
        <span class="brand-mark" aria-hidden="true">◈</span>
        <span>全球投研<span class="brand-sub"> · 黄金 × A/港/美</span></span>
      </a>
      <nav class="main-nav" aria-label="主导航">{nav_html}</nav>
      <div class="header-controls">
        <button type="button" class="ctrl-btn" id="font-dec" title="缩小字号" aria-label="缩小字号">A-</button>
        <button type="button" class="ctrl-btn" id="font-inc" title="放大字号" aria-label="放大字号">A+</button>
        <button type="button" class="ctrl-btn" id="theme-toggle" title="切换深浅色模式" aria-label="切换深浅色模式">🌙</button>
      </div>
    </div>
  </header>

  <main class="page-main">
    {content_html}
  </main>

  <footer class="site-footer">
    <div class="footer-inner">
      <div>全球投研 · 黄金 × A股 × 港股 × 美股 ｜ 多源官方库交叉核验 · 严守仓位与风控纪律{(" · 更新：" + esc(footer_ts)) if footer_ts else ""}</div>
      <div class="footer-links">
        <a href="{base_prefix}index.html">总览</a>
        <a href="{base_prefix}screener.html">{pool_label}</a>
        <a href="{base_prefix}scorecard.html">记分卡</a>
        <a href="{base_prefix}archive.html">历史档案</a>
        <a href="{RELEASES_TAG_URL}" target="_blank" rel="noopener">PDF/Word 下载 ↗</a>
      </div>
    </div>
  </footer>

  {mobile_dock_html}
  {toc_drawer_html}
  {chart_modal_html}
  <script src="{base_prefix}assets/app.js"></script>
</body>
</html>
"""


def render_doc_with_toc(
    *,
    sibling_bar_html: str,
    cover_html: str,
    body_html: str,
    footer_note: str,
    toc_items: list[tuple[int, str, str]],
) -> str:
    footer_div = f'<div class="footer-note">{esc(footer_note)}</div>' if footer_note else ""
    if toc_items:
        sidebar = (
            '<aside class="toc-sidebar" aria-label="目录导航">'
            '<div class="toc-heading">本篇目录</div>'
            f"{render_toc_list(toc_items)}"
            "</aside>"
        )
        layout_cls = "doc-layout"
    else:
        sidebar = ""
        layout_cls = "doc-layout no-toc"

    return (
        f"{sibling_bar_html}"
        f'<div class="{layout_cls}">'
        f"{sidebar}"
        f'<article class="article-card">'
        f"{cover_html}"
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


def _render_release_downloads_grid(
    stock_counts: dict[str, int],
    *,
    include_web_link: bool = False,
) -> str:
    a_pool = stock_counts.get("a-share", 0)
    hk_pool = stock_counts.get("hk-stock", 0)
    us_pool = stock_counts.get("us-stock", 0)
    specs = [
        ("gold", "🥇 黄金主报告 & 日报", "主报告", "reports/gold.html"),
        ("a-share", f"🇨🇳 A 股全景手册 ({a_pool}股)", "手册", "reports/a-share.html"),
        ("hk-stock", f"🇭🇰 港股全景手册 ({hk_pool}股)", "手册", "reports/hk-stock.html"),
        ("us-stock", f"🇺🇸 美股全景手册 ({us_pool}股)", "手册", "reports/us-stock.html"),
    ]
    cards: list[str] = []
    for mk, title, f_lbl, web_href in specs:
        assets = RELEASE_ASSET_NAMES[mk]
        links: list[str] = []
        if include_web_link:
            links.append(f'<a class="dl-link" href="{web_href}">网页版</a>')
        links.append(
            f'<a class="dl-link" href="{RELEASES_DL_BASE}/{assets["flagship_pdf"]}" target="_blank" rel="noopener">{f_lbl} PDF ↗</a>'
        )
        links.append(
            f'<a class="dl-link" href="{RELEASES_DL_BASE}/{assets["flagship_docx"]}" target="_blank" rel="noopener">{f_lbl} Word ↗</a>'
        )
        links.append(
            f'<a class="dl-link" href="{RELEASES_DL_BASE}/{assets["daily_pdf"]}" target="_blank" rel="noopener">日报 PDF ↗</a>'
        )
        links.append(
            f'<a class="dl-link" href="{RELEASES_DL_BASE}/{assets["daily_docx"]}" target="_blank" rel="noopener">日报 Word ↗</a>'
        )
        cards.append(
            f'<div class="dl-card">'
            f'<div class="dl-name">{title}</div>'
            f'<div class="dl-links">{"".join(links)}</div>'
            f"</div>"
        )
    return "".join(cards)


def build_cockpit_page(
    gold_snap: dict,
    eq_state: dict,
    latest_by_market: dict[str, DailyItem],
    stock_counts: dict[str, int],
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
    a_csi300_val = _fmt_num(a_m.get("benchmark_csi300"), ",.2f")
    a_sse_val = _fmt_num(a_m.get("benchmark_sse"), ",.2f")
    a_200w_val = _fmt_num(a_m.get("csi300_200w"), ",.0f")
    a_eq_cap_val = _fmt_num(a_m.get("equity_cap_pct"), ".0f", prefix="≤ ", suffix="%")
    a_erp_fwd_val = _fmt_num(a_m.get("erp_fwd_pct"), "+.2f", suffix="%")
    a_erp_ttm_val = _fmt_num(a_m.get("erp_ttm_pct"), "+.2f", suffix="%")
    a_cgb10y_val = _fmt_num(a_m.get("cgb10y_pct"), ".3f", suffix="%")

    # Dynamic PBOC / margin scan (normalized canonical keys with dated fallback)
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
        us_pool_sub = f"距前高 {us_high:,.0f} 回撤 {us_dd:+.1f}% · 7 大赛道"
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
    else:
        vix_caution = (vix_high is not None and vix_high >= vix_thr) or vix_close >= 24
        vix_chip = ("chip-danger", "已触红线") if vix_close >= vix_thr else (
            ("chip-warn", "逼近警戒") if vix_caution else ("chip-ok", "安全区间")
        )
    vix_close_val = _fmt_num(vix_close, ".2f")

    usdjpy = _safe_float(brake.get("usdjpy_level"))
    if usdjpy is None:
        usdjpy = _safe_float(rates.get("usd_jpy"))
    jpy_drop_thr_raw = _safe_float(brake.get("usdjpy_3d_drop_brake_pct"))
    jpy_drop_thr = abs(jpy_drop_thr_raw) if jpy_drop_thr_raw is not None else 3.0
    if usdjpy is None:
        jpy_chip = ("chip-warn", "待核")
    else:
        jpy_chip = ("chip-danger", "干预高危") if usdjpy >= 160 else (
            ("chip-warn", "紧盯干预") if usdjpy >= 155 else ("chip-ok", "平稳")
        )
    usdjpy_val = _fmt_num(usdjpy, ".2f")

    us10y = _safe_float(rates.get("us10y_pct"))
    if us10y is None:
        us10y = _safe_float(us_m.get("us10y_pct"))
    us10y_thr = _safe_float(brake.get("us10y_brake_pct"))
    if us10y_thr is None:
        us10y_thr = 5.25
    if us10y is None:
        us10y_chip = ("chip-warn", "待核")
    else:
        us10y_chip = ("chip-danger", "触及熔断") if us10y >= us10y_thr else (
            ("chip-warn", "高息承压") if us10y >= 4.7 else ("chip-ok", "温和")
        )
    us10y_val = _fmt_num(us10y, ".3f", suffix="%")

    hkma_bal = _safe_float(rates.get("hkma_agg_bal_hkd_100m"))
    hkma_thr = _safe_float(brake.get("hkma_agg_bal_brake_100m"))
    if hkma_thr is None:
        hkma_thr = 400.0
    if hkma_bal is None:
        hkma_chip = ("chip-warn", "待核")
    else:
        hkma_chip = ("chip-danger", "触及底线") if hkma_bal <= hkma_thr else (
            ("chip-warn", "薄缓冲警戒") if hkma_bal < 650 else ("chip-ok", "缓冲充裕")
        )
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

    # Three-Market ERP Horizontal Visual Bar (0% to 10% scale, WCAG AA semantic classes)
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

    # Latest Daily Feed Grid (4 markets)
    feed_cards_html = ""
    for mk in ("gold", "a-share", "hk-stock", "us-stock"):
        it = latest_by_market.get(mk)
        if not it:
            continue
        mm = MARKET_META[mk]
        feed_cards_html += (
            f'<a class="feed-card" href="{mm["latest_href"]}">'
            f'<div class="feed-meta">'
            f'<span class="mkt-badge mkt-{mk}">{mm["emoji"]} {mm["short"]}</span>'
            f'<span class="session-pill">{esc(it.date_str)} · {esc(it.session_label)}</span>'
            f"</div>"
            f'<div class="feed-title">{esc(it.title)}</div>'
            f'<div class="feed-summary">{esc(it.summary)}</div>'
            f"</a>"
        )

    dl_cards_html = _render_release_downloads_grid(
        {"a-share": a_pool, "hk-stock": hk_pool, "us-stock": us_pool},
        include_web_link=True,
    )

    total_pool = a_pool + hk_pool + us_pool

    return f"""
    <section class="live-banner">
      <div class="live-banner-top">
        <span class="live-pill"><span class="live-pulse"></span>{esc(alert_label)}</span>
        <span class="live-cadence">每日 07:30 一体化早报 ｜ 18:00 一体化晚报（黄金 × A/港/美 自动刷新）</span>
      </div>
      <h1 class="live-title">全球大类资产 10 秒水温驾驶舱</h1>
      <div class="live-meta-row">
        <span><strong>黄金快照</strong>：{esc(gold_as_of)}</span>
        <span><strong>三市股市快照</strong>：{esc(eq_as_of)}</span>
        <span><strong>覆盖龙头</strong>：{total_pool} 家跨市场核心公司</span>
      </div>
    </section>

    <div class="sec-head" style="margin-top:6px;">
      <h2>四市场红绿灯水温卡片</h2>
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
        <div class="m-metrics">
          <div class="m-metric">
            <div class="m-metric-lbl">纽约现货金（美元/盎司）</div>
            <div class="m-metric-val">{gold_spot_val}</div>
            <div class="m-metric-sub">{esc(gold_asia_sub)}</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">{esc(sge_main_lbl)}</div>
            <div class="m-metric-val">{esc(sge_main_val)}</div>
            <div class="m-metric-sub">{esc(sge_sub_txt)}</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">10 年美债真实利率 DFII10</div>
            <div class="m-metric-val">{esc(gold_dfii_val)}</div>
            <div class="m-metric-sub">{esc(dfii_sub)}</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">新仓规则 / 家庭上限</div>
            <div class="m-metric-val">{esc(gold_new_buy_val)}</div>
            <div class="m-metric-sub">{esc(gold_new_buy_sub)}</div>
          </div>
        </div>
        <div class="m-verdict"><strong>核心指令：</strong>{esc(gold_verdict)}</div>
        <div class="m-actions">
          <a class="btn btn-primary" href="daily/gold-latest.html">最新日报 →</a>
          <a class="btn" href="reports/gold.html">跨世纪主报告</a>
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
        <div class="m-metrics">
          <div class="m-metric">
            <div class="m-metric-lbl">沪深 300 / 上证指数</div>
            <div class="m-metric-val">{a_csi300_val}</div>
            <div class="m-metric-sub">上证 {a_sse_val} · 4年成本线 {a_200w_val}</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">股票仓位上限</div>
            <div class="m-metric-val">{a_eq_cap_val}</div>
            <div class="m-metric-sub">余下稳守国债 / 转债 / 现金</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">前瞻 / 静态 ERP</div>
            <div class="m-metric-val">{a_erp_fwd_val} / {a_erp_ttm_val}</div>
            <div class="m-metric-sub">10 年国债 {a_cgb10y_val}</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">核心龙头诊断池</div>
            <div class="m-metric-val">{a_pool} 只龙头</div>
            <div class="m-metric-sub">{esc(a_pool_sub)}</div>
          </div>
        </div>
        <div class="m-verdict"><strong>防踏空升级线：</strong>{esc(a_m.get("fomo_threshold", ""))}</div>
        <div class="m-actions">
          <a class="btn btn-primary" href="daily/a-share-latest.html">最新日报 →</a>
          <a class="btn" href="reports/a-share.html">全景手册 ({a_pool}股)</a>
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
        <div class="m-metrics">
          <div class="m-metric">
            <div class="m-metric-lbl">恒生指数 / 恒生科技</div>
            <div class="m-metric-val">{hk_hsi_val}</div>
            <div class="m-metric-sub">恒科 {hk_hstech_val} · 200日线 {hk_200d_val}</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">离岸 / 港股通上限</div>
            <div class="m-metric-val">{hk_off_cap_val} / {hk_on_cap_val}</div>
            <div class="m-metric-sub">AH 溢价指数 {hk_hsahp_val}</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">HIBOR 1M / 总结余</div>
            <div class="m-metric-val">{hibor_value} / {hkma_short_val}</div>
            <div class="m-metric-sub">美元/港元 {usd_hkd_value}（紧盯 7.85）</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">美元 / 人民币锚前瞻 ERP</div>
            <div class="m-metric-val">{hk_erp_usd_val} / {hk_erp_cny_val}</div>
            <div class="m-metric-sub">{hk_pool} 只核心龙头 · 南向年内 {hk_sb_ytd_val}</div>
          </div>
        </div>
        <div class="m-verdict"><strong>防踏空升级线：</strong>{esc(hk_m.get("fomo_threshold", ""))}</div>
        <div class="m-actions">
          <a class="btn btn-primary" href="daily/hk-stock-latest.html">最新日报 →</a>
          <a class="btn" href="reports/hk-stock.html">全景手册 ({hk_pool}股)</a>
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
        <div class="m-metrics">
          <div class="m-metric">
            <div class="m-metric-lbl">标普 500 / 10 年美债</div>
            <div class="m-metric-val">{us_sp_val}</div>
            <div class="m-metric-sub">10Y 美债 {us10y_val} · 200日线 {us_200d_val}</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">100% 闭环资产配置</div>
            <div class="m-metric-val" style="font-size:13.5px;">{esc(us_alloc_str)}</div>
            <div class="m-metric-sub">科技新增严控 {us_tech_cap_val}</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">前瞻 / 静态 ERP</div>
            <div class="m-metric-val">{us_erp_fwd_val} / {us_erp_ttm_val}</div>
            <div class="m-metric-sub">前瞻 PE {us_pe_fwd_val}（静态 {us_pe_ttm_val}）</div>
          </div>
          <div class="m-metric">
            <div class="m-metric-lbl">核心龙头诊断池</div>
            <div class="m-metric-val">{us_pool} 只龙头</div>
            <div class="m-metric-sub">{esc(us_pool_sub)}</div>
          </div>
        </div>
        <div class="m-verdict"><strong>防踏空升级线：</strong>{esc(us_m.get("fomo_threshold", ""))}</div>
        <div class="m-actions">
          <a class="btn btn-primary" href="daily/us-stock-latest.html">最新日报 →</a>
          <a class="btn" href="reports/us-stock.html">全景手册 ({us_pool}股)</a>
        </div>
      </article>
    </section>

    <div class="sec-head">
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
            <div class="breaker-thr">{vix_high_label} ｜ 熔断线：连2日 &gt; {vix_thr:.0f}</div>
          </div>
          <div class="breaker-item">
            <div class="breaker-top">
              <span class="breaker-name">美元 / 日元 USD/JPY</span>
              <span class="status-chip {jpy_chip[0]}">{jpy_chip[1]}</span>
            </div>
            <div class="breaker-val">{usdjpy_val}</div>
            <div class="breaker-thr">熔断线：3 日急跌 &gt; {jpy_drop_thr:g}%（日元急升防平仓）</div>
          </div>
          <div class="breaker-item">
            <div class="breaker-top">
              <span class="breaker-name">10 年期美债 US10Y</span>
              <span class="status-chip {us10y_chip[0]}">{us10y_chip[1]}</span>
            </div>
            <div class="breaker-val">{us10y_val}</div>
            <div class="breaker-thr">熔断线：突破 {us10y_thr:.2f}%</div>
          </div>
          <div class="breaker-item">
            <div class="breaker-top">
              <span class="breaker-name">香港金管局总结余</span>
              <span class="status-chip {hkma_chip[0]}">{hkma_chip[1]}</span>
            </div>
            <div class="breaker-val">{hkma_full_val}</div>
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
      </div>

      <div class="panel-card">
        <div class="panel-title">
          <span>🏠 家庭跨市场综合资产配置闭环</span>
          <span class="sec-sub">{hcw_sum_disp}</span>
        </div>
        <div class="alloc-bar" role="img" aria-label="家庭综合配置比例条">
          <div class="alloc-seg" style="width:{eq_pct}%;background:#1d4ed8;" title="股票底座 {eq_pct}%">{eq_pct}% 股</div>
          <div class="alloc-seg" style="width:{cb_pct}%;background:#0f766e;" title="可转债 {cb_pct}%">{cb_pct}%</div>
          <div class="alloc-seg" style="width:{bc_pct}%;background:#475569;" title="国债短债与现金 {bc_pct}%">{bc_pct}% 债现</div>
          <div class="alloc-seg" style="width:{gd_pct}%;background:#b45309;" title="存量黄金 {gd_pct}%">{gd_pct}% 金</div>
        </div>
        <div class="alloc-legend">
          <span class="alloc-leg-item"><span class="alloc-swatch" style="background:#1d4ed8;"></span>股票底座 {eq_pct}%</span>
          <span class="alloc-leg-item"><span class="alloc-swatch" style="background:#0f766e;"></span>可转债 {cb_pct}%</span>
          <span class="alloc-leg-item"><span class="alloc-swatch" style="background:#475569;"></span>国债/短债现金 {bc_pct}%</span>
          <span class="alloc-leg-item"><span class="alloc-swatch" style="background:#b45309;"></span>存量黄金 {gd_pct}%{esc(gold_alloc_suffix)}</span>
        </div>
        <div class="alloc-note">{esc(hcw_note)}</div>
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
    </section>

    <div class="sec-head">
      <h2>四市场最新早晚报速递</h2>
      <a href="archive.html" class="btn btn-sm">查看全部历史档案 →</a>
    </div>

    <section class="feed-grid">
      {feed_cards_html}
    </section>

    <section class="downloads-box">
      <div class="panel-title" style="margin-bottom:4px;">
        <span>📥 杂志级 PDF / 原生 Word 离线下载中心</span>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button type="button" class="btn btn-sm" data-action="print">🖨️ 当前页一键存 PDF</button>
          <a class="btn btn-sm" href="{RELEASES_TAG_URL}" target="_blank" rel="noopener">GitHub Releases 全部附件 ↗</a>
        </div>
      </div>
      <div class="sec-sub">离线文件托管于 GitHub Releases（不占网页仓库体积）；打开任意报告网页点击右下角「🖨️ PDF」亦可零等待即时打印导出。</div>
      <div class="downloads-grid">
        {dl_cards_html}
      </div>
    </section>
    """


def build_flagship_sibling_bar(active_market: str, total_pool: int) -> str:
    tabs = [
        ("gold", "gold.html", "🥇 黄金主报告"),
        ("a-share", "a-share.html", "🇨🇳 A股手册"),
        ("hk-stock", "hk-stock.html", "🇭🇰 港股手册"),
        ("us-stock", "us-stock.html", "🇺🇸 美股手册"),
    ]
    left = "".join(
        f'<a class="sib-pill{" active" if mk == active_market else ""}" href="{href}">{lbl}</a>'
        for mk, href, lbl in tabs
    )
    latest_href = f"../daily/{active_market}-latest.html"
    return (
        '<div class="sibling-bar no-print">'
        f'<div class="sibling-group">{left}</div>'
        '<div class="sibling-group">'
        f'<a class="btn btn-sm" href="{latest_href}">📰 最新日报</a>'
        f'<a class="btn btn-sm" href="../screener.html">🔍 {total_pool}股池</a>'
        '<button type="button" class="btn btn-sm" data-action="print">🖨️ 打印/存PDF</button>'
        "</div></div>"
    )


def build_daily_sibling_bar(
    item: DailyItem,
    prev_item: DailyItem | None,
    next_item: DailyItem | None,
    stock_counts: dict[str, int],
) -> str:
    tabs = [
        ("gold", "gold-latest.html", "🥇 黄金最新"),
        ("a-share", "a-share-latest.html", "🇨🇳 A股最新"),
        ("hk-stock", "hk-stock-latest.html", "🇭🇰 港股最新"),
        ("us-stock", "us-stock-latest.html", "🇺🇸 美股最新"),
    ]
    left = "".join(
        f'<a class="sib-pill{" active" if mk == item.market else ""}" href="{href}">{lbl}</a>'
        for mk, href, lbl in tabs
    )
    mm = MARKET_META[item.market]
    manual_lbl = (
        mm["manual_label"]
        if item.market == "gold"
        else f'{mm["manual_label"]} ({stock_counts.get(item.market, 0)}股)'
    )
    nav_btns = []
    if prev_item:
        nav_btns.append(f'<a class="btn btn-sm" href="{prev_item.slug}.html" title="{esc(prev_item.title)}">← 上一期</a>')
    if next_item:
        nav_btns.append(f'<a class="btn btn-sm" href="{next_item.slug}.html" title="{esc(next_item.title)}">下一期 →</a>')
    nav_btns.append(f'<a class="btn btn-sm" href="../{mm["report_href"]}">📖 {manual_lbl}</a>')
    nav_btns.append(f'<a class="btn btn-sm" href="../archive.html#{item.market}">🗂️ 往期档案</a>')
    return (
        '<div class="sibling-bar no-print">'
        f'<div class="sibling-group">{left}</div>'
        f'<div class="sibling-group">{"".join(nav_btns)}</div>'
        "</div>"
    )


def build_screener_page(stocks: list[dict[str, str]], benchmarks: dict[str, str]) -> str:
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
    static_rows = "".join(
        f'<tr class="row-{esc(stock["color"])}" data-market="{esc(stock["market"])}">'
        f'<td>{esc(stock["market_label"])}</td><td>{esc(stock["sector"])}</td>'
        f'<td><strong>{esc(stock["name"])}</strong> <span class="code-tag">{esc(stock["code"])}</span></td>'
        f'<td>{esc(stock["price"])}</td><td>{esc(stock["valuation"])}</td>'
        f'<td>{esc(stock["action_label"])}</td>'
        f'<td>{esc(stock["summary"])} <a href="{esc(stock["report_url"])}">手册 →</a></td></tr>'
        for stock in stocks
    )

    return f"""
    <div class="sec-head" style="margin-top:4px;">
      <h2>🔍 全球 {total} 家核心龙头交互筛选器</h2>
      <span class="sec-sub">各市场数据基准取自旗舰手册附表二 · {source_labels}</span>
    </div>

    <div class="screener-stats">
      <div class="stat-tile" data-stat-color="all">
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
      <div class="filter-row">
        <input type="search" id="scr-search" class="search-input" placeholder="搜索中文名 / 代码 / 赛道 / 关键词（如 宁德、NVDA、00883、银行、回购）…" autocomplete="off">
        <select id="scr-sector" class="sector-select" aria-label="按赛道筛选"></select>
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
    </section>

    <div class="screener-bar">
      <strong id="scr-count" role="status">显示 {total} / {total} 家龙头公司</strong>
    </div>

    <div class="screener-table-wrap">
      <table class="screener-table">
        <thead>
          <tr>
            <th class="sortable" data-sort="market"><button type="button" disabled>市场 ⇅</button></th>
            <th class="sortable" data-sort="sector"><button type="button" disabled>赛道 ⇅</button></th>
            <th class="sortable" data-sort="name"><button type="button" disabled>公司与代码 ⇅</button></th>
            <th>最新价 / 一手</th>
            <th>估值 / 股息 / AH</th>
            <th class="sortable" data-sort="color"><button type="button" disabled>四色阵营 ⇅</button></th>
            <th>核心诊断与安全锚摘要</th>
          </tr>
        </thead>
        <tbody id="scr-tbody">{static_rows}</tbody>
      </table>
    </div>

    <div class="screener-cards" id="scr-cards"></div>

    <script id="screener-data" type="application/json">{safe_json}</script>
    """


def build_scorecard_page(
    R: Renderers,
    slug_map: dict[str, str],
) -> str:
    eq_sc_md = normalize_relative_md_links(
        (EQUITY_DIR / "daily" / "SCORECARD.md").read_text(encoding="utf-8")
    )
    gd_sc_md = normalize_relative_md_links(
        protect_backticked_comments(
            (GOLD_DIR / "daily" / "SCORECARD.md").read_text(encoding="utf-8")
        )
    )
    eq_cl_md = normalize_relative_md_links(
        (EQUITY_DIR / "daily" / "CHANGELOG.md").read_text(encoding="utf-8")
    )
    gd_cl_md = normalize_relative_md_links(
        protect_backticked_comments(
            sanitize_public_ledger_md(
                (GOLD_DIR / "daily" / "CHANGELOG.md").read_text(encoding="utf-8"),
                is_audit_log=False,
            )
        )
    )
    gd_al_md = normalize_relative_md_links(
        protect_backticked_comments(
            sanitize_public_ledger_md(
                (GOLD_DIR / "daily" / "AUDIT_LOG.md").read_text(encoding="utf-8"),
                is_audit_log=True,
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

    return f"""
    <div class="sec-head" style="margin-top:4px;">
      <h2>📋 公开可证伪预测记分卡与观点演进账本</h2>
      <span class="sec-sub">对就写对、偏就写偏、错就公开认错，绝不事后涂改旧账</span>
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
    <section id="equity-changelog" class="tab-panel article-card">
      <div class="article-body">{eq_cl_html}</div>
    </section>
    <section id="gold-changelog" class="tab-panel article-card">
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
        shelf_html += (
            f'<a class="flagship-tile" href="{fl["href"]}" style="--tile-accent:{fl["accent"]};">'
            f'<div class="feed-meta"><span class="mkt-badge mkt-{fl["market"]}">{fl["badge"]}</span>'
            f'<span class="session-pill">{esc(fl["charts"])} 张高清矢量图</span></div>'
            f'<div class="ft-title">{esc(fl["title"])}</div>'
            f'<div class="ft-meta">数据基线：{esc(fl["baseline"])}</div>'
            f"</a>"
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
            cards.append(
                f'<a class="feed-card" href="{it.rel_url}" data-arc-item="1" '
                f'data-market="{it.market}" data-session="{it.session_key}">'
                f'<div class="feed-meta">'
                f'<span class="mkt-badge mkt-{it.market}">{mm["emoji"]} {mm["short"]}</span>'
        f'<span class="session-pill">{esc(it.session_label)}</span>'
                f"{revision_badge}"
                f"{chart_badge}"
                f"</div>"
                f'<div class="feed-title">{esc(it.title)}</div>'
                f'<div class="feed-summary">{esc(it.summary)}</div>'
                f"</a>"
            )
        timeline_html += (
            f'<div class="archive-day">'
            f'<div class="archive-date-hdr">📅 {esc(dt)} <span class="sec-sub">（共 {len(cards)} 期）</span></div>'
            f'<div class="archive-list">{"".join(cards)}</div>'
            f"</div>"
        )

    dl_cards_html = _render_release_downloads_grid(stock_counts, include_web_link=False)

    return f"""
    <div class="sec-head" style="margin-top:4px;">
      <h2>📖 四大常青旗舰全景手册</h2>
      <span class="sec-sub">{total_flagship_charts} 张原创矢量图表 · 随时查阅宏观框架与 {total_pool} 只龙头全诊断</span>
    </div>
    <section class="flagship-shelf">{shelf_html}</section>

    <div class="sec-head">
      <h2>🗂️ 历史早晚报</h2>
      <strong id="arc-count" class="sec-sub">共展示 {len(dailies)} 期历史日报</strong>
    </div>

    <section class="filter-panel">
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-arc-market="all">全部市场</button>
        <button type="button" class="filter-pill" id="gold" data-arc-market="gold">🥇 黄金</button>
        <button type="button" class="filter-pill" id="a-share" data-arc-market="a-share">🇨🇳 A股</button>
        <button type="button" class="filter-pill" id="hk-stock" data-arc-market="hk-stock">🇭🇰 港股</button>
        <button type="button" class="filter-pill" id="us-stock" data-arc-market="us-stock">🇺🇸 美股</button>
      </div>
      <div class="filter-row">
        <button type="button" class="filter-pill active" data-arc-session="all">全部时段</button>
        <button type="button" class="filter-pill" data-arc-session="morning">🌅 早报 (07:30)</button>
        <button type="button" class="filter-pill" data-arc-session="midday">☀️ 午报 (16:30)</button>
        <button type="button" class="filter-pill" data-arc-session="evening">🌆 晚报 (18:00)</button>
      </div>
    </section>

    <section>{timeline_html}</section>

    <section class="downloads-box">
      <div class="panel-title">
        <span>📦 最新 PDF / Word 下载</span>
        <a class="btn btn-sm" href="{RELEASES_TAG_URL}" target="_blank" rel="noopener">前往 Releases 页面 ↗</a>
      </div>
      <div class="downloads-grid">
        {dl_cards_html}
      </div>
    </section>
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

    stocks = extract_all_stocks(
        eq_flagship_mds["a_share"],
        eq_flagship_mds["hk_stock"],
        eq_flagship_mds["us_stock"],
    )
    stock_counts: dict[str, int] = defaultdict(int)
    for st in stocks:
        stock_counts[st["market"]] += 1
    total_pool = len(stocks)

    # The renderer always receives a new output directory.
    out_dir.mkdir(parents=True)
    for sub in ("assets", "reports", "daily"):
        (out_dir / sub).mkdir()

    # Static assets + .nojekyll + manifest.json + favicon.svg
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    shutil.copyfile(ASSETS_SRC / "app.css", out_dir / "assets" / "app.css")
    shutil.copyfile(ASSETS_SRC / "app.js", out_dir / "assets" / "app.js")
    (out_dir / "assets" / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")

    manifest = {
        "name": "全球投研 · 黄金 × A股 × 港股 × 美股",
        "short_name": "全球投研",
        "description": f"零门槛机构级全球跨市场投研门户：黄金、A股、港股、美股红绿灯驾驶舱、{total_pool}只龙头筛选器与每日早晚报。",
        "start_url": "./",
        "display": "standalone",
        "background_color": "#f5f6f8",
        "theme_color": "#0f172a",
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
    g_footer = (
        f"本报告（数据基线 {R.gold_report.REPORT_TIMESTAMP}）数据均经多源官方数据库核验；"
        "投资有风险，请按家庭总资产 10%–15% 合理配置，严禁借钱或加杠杆炒金。"
    )
    gold_report_html = render_page_shell(
        title="黄金跨世纪周期与普通人全景配置指南（1971–2030）",
        active_nav="gold",
        base_prefix="../",
        market_attr="gold",
        total_pool=total_pool,
        toc_items=g_toc,
        show_chart_modal=True,
        footer_ts=R.gold_report.REPORT_SHORT_DATE,
        content_html=render_doc_with_toc(
            sibling_bar_html=build_flagship_sibling_bar("gold", total_pool),
            cover_html=g_cover,
            body_html=g_body,
            footer_note=g_footer,
            toc_items=g_toc,
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
        page_html = render_page_shell(
            title=doc_title,
            active_nav=m_slug,
            base_prefix="../",
            market_attr=m_slug,
            total_pool=total_pool,
            toc_items=toc,
            show_chart_modal=True,
            footer_ts=str(meta.get("benchmark_time", "")).split("（")[0],
            content_html=render_doc_with_toc(
                sibling_bar_html=build_flagship_sibling_bar(m_slug, total_pool),
                cover_html=cover_html,
                body_html=body_clean,
                footer_note=footer_note,
                toc_items=toc,
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
            fallback_t = f"{mm['name']}每日大白话投研简报"
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
        total_daily_charts += n_charts
        dailies_by_market[item.market].append(item)

    latest_by_market: dict[str, DailyItem] = {}
    for mk, m_list in dailies_by_market.items():
        m_list.sort(key=lambda x: x.sort_key)
        last_by_session = {(item.date_str, item.hhmm): item for item in m_list}
        for idx, item in enumerate(m_list):
            prev_it = m_list[idx - 1] if idx > 0 else None
            next_it = m_list[idx + 1] if idx + 1 < len(m_list) else None
            sib_bar = build_daily_sibling_bar(item, prev_it, next_it, stock_counts)
            corrected = last_by_session[item.date_str, item.hhmm]
            if item.rev < corrected.rev:
                sib_bar += (
                    '<p class="no-print">此页为原刊档案。'
                    f'<a href="{corrected.slug}.html">查看本班次修订稿</a>。</p>'
                )
            doc_html = render_doc_with_toc(
                sibling_bar_html=sib_bar,
                cover_html=item.cover_html,
                body_html=item.body_html,
                footer_note=item.footer_note,
                toc_items=item.toc,
            )
            full_page = render_page_shell(
                title=item.title,
                active_nav=item.market,
                base_prefix="../",
                market_attr=item.market,
                edition_attr=item.edition_type,
                total_pool=total_pool,
                toc_items=item.toc,
                show_chart_modal=(item.chart_count > 0),
                footer_ts=f"{item.date_str} {item.session_label}",
                content_html=doc_html,
            )
            (out_dir / "daily" / f"{item.slug}.html").write_text(full_page, encoding="utf-8")
            if idx == len(m_list) - 1:
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
        total_pool=total_pool,
        footer_ts=eq_as_of_disp,
        content_html=build_scorecard_page(R, slug_map),
    )
    (out_dir / "scorecard.html").write_text(scorecard_html, encoding="utf-8")

    # ------------------------------------------------------------------
    # E. Build Archive Page (archive.html)
    # ------------------------------------------------------------------
    total_flagship_charts = sum(flagship_stats.values())
    archive_html = render_page_shell(
        title="历史研报档案与下载中心",
        active_nav="archive",
        base_prefix="",
        market_attr="overview",
        total_pool=total_pool,
        footer_ts=eq_as_of_disp,
        content_html=build_archive_page(
            dailies, flagship_info, stock_counts, total_pool, total_flagship_charts
        ),
    )
    (out_dir / "archive.html").write_text(archive_html, encoding="utf-8")

    # ------------------------------------------------------------------
    # F. Build Global Weather Cockpit (index.html)
    # ------------------------------------------------------------------
    cockpit_html = render_page_shell(
        title="全球投研总览 · 黄金 × A/港/美",
        active_nav="overview",
        base_prefix="",
        market_attr="overview",
        total_pool=total_pool,
        footer_ts=eq_as_of_disp,
        content_html=build_cockpit_page(gold_snap, eq_state, latest_by_market, stock_counts),
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
        f"(4 core + 4 flagships + {summary['daily_pages']} dated dailies + {summary['latest_pages']} canonical latest)\n"
        f"  Flagship charts: {summary['flagship_total_charts']} {summary['flagship_charts']}\n"
        f"  Daily charts:    {summary['daily_total_charts']}\n"
        f"  Screener pool:   {summary['screener_total']} {summary['screener_by_market']}"
    )


if __name__ == "__main__":
    main()
