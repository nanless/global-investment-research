#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Site Forensic Linter & Security Gate Validator for Global Investment Research.

Zero-dependency (Python 3 stdlib only) static site validator enforcing 6 forensic gates:
  - Gate S1: Completeness & Non-Empty Output
  - Gate S2: Zero Broken Internal Links, Assets & Same-Page Anchors
  - Gate S3: Zero PII, Local Path, Secret & Unresolved Directive Leaks
  - Gate S4: Vector SVG Chart Integrity
  - Gate S5: Desktop + Mobile Responsive Hygiene
  - Gate S6: Live SSOT & Full-Market Stock Screener Fidelity (全市场龙头股筛选)

Usage:
  python3 scripts/lint_site.py [site_dir] [--strict]

Exit codes:
  0  Pass (0 errors; and 0 warnings if --strict)
  1  Failed (any error, or any warning with --strict)
  2  Invalid CLI arguments
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
try:
    from svg_geometry import check_svg_text_geometry  # type: ignore[import-not-found]
except ImportError:
    check_svg_text_geometry = None  # type: ignore[assignment]
DEFAULT_SITE_DIR = REPO_ROOT / "_site"
GOLD_SNAPSHOT_PATH = REPO_ROOT / "gold" / "data_snapshot.json"
MARKET_STATE_PATH = REPO_ROOT / "equity" / "state" / "market_state.json"

# ---------------------------------------------------------------------------
# Gate S1 configuration
# ---------------------------------------------------------------------------
# Marker files only need to exist (0 bytes is standard for GitHub Pages .nojekyll).
REQUIRED_SENTINEL_FILES: tuple[str, ...] = (".nojekyll",)

# Core site artifacts that MUST exist and be non-empty.
REQUIRED_NONEMPTY_FILES: tuple[str, ...] = (
    "index.html",
    "channels.html",
    "etfs.html",
    "screener.html",
    "guide.html",
    "scorecard.html",
    "archive.html",
    "reports/gold.html",
    "reports/a-share.html",
    "reports/hk-stock.html",
    "reports/us-stock.html",
    "daily/gold-latest.html",
    "daily/a-share-latest.html",
    "daily/hk-stock-latest.html",
    "daily/us-stock-latest.html",
    "assets/app.css",
    "assets/app.js",
    "assets/favicon.svg",
    "manifest.json",
)

MIN_HTML_BYTES = 3_000
HTML_SUFFIXES = {".html", ".htm"}
TEXT_SCAN_SUFFIXES = {".html", ".htm", ".css", ".js", ".mjs", ".json", ".svg"}

# ---------------------------------------------------------------------------
# Gate S2 configuration
# ---------------------------------------------------------------------------
# Only explicitly safe external URI schemes are permitted; dangerous schemes fail Gate S2.
EXTERNAL_SCHEMES = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
)

FORBIDDEN_URI_SCHEMES = (
    "javascript:",
    "vbscript:",
    "data:",
    "blob:",
    "about:",
)

LINK_ATTR_BY_TAG: dict[str, str] = {
    "a": "href",
    "link": "href",
    "script": "src",
    "img": "src",
}

# Web-only publishing: forbid deprecated latest-reports Release links (any scheme)
# and non-HTTP(S) PDF/Word binary links (external official PDF citations remain allowed).
FORBIDDEN_RELEASE_LINK_RE = re.compile(
    r"/releases/(?:download|tag)/latest-reports\b",
    re.IGNORECASE,
)
FORBIDDEN_BINARY_LINK_RE = re.compile(
    r"\.(?:pdf|docx)(?:[?#]|$)",
    re.IGNORECASE,
)
MULTI_ASSET_CHANNELS_PATH = REPO_ROOT / "equity" / "state" / "multi_asset_channels.json"
ETF_UNIVERSE_PATH = REPO_ROOT / "equity" / "state" / "etf_universe.json"
REQUIRED_MULTI_ASSET_CHANNELS: tuple[str, ...] = (
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

# HTML5 void elements that never have a closing tag.
VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

BLOCK_TEXT_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "caption",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "option",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "text",
        "tfoot",
        "th",
        "thead",
        "title",
        "tr",
        "tspan",
        "ul",
    }
)

# ---------------------------------------------------------------------------
# Gate S3 configuration (PII, local paths, secrets, unresolved placeholders)
# ---------------------------------------------------------------------------
S3_RAW_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("local file:// URI", re.compile(r"file://", re.IGNORECASE)),
    (
        "local filesystem path (/Users/ or /home/)",
        re.compile(r"/Users/|(?<![A-Za-z0-9._-])/home/"),
    ),
    (
        "GitHub token prefix (ghp_/gho_/github_pat_)",
        re.compile(r"(?<![A-Za-z0-9_])(?:ghp_|gho_|github_pat_)"),
    ),
    (
        "AWS access key (AKIA...)",
        re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])"),
    ),
    (
        "Google API key (AIza...)",
        re.compile(r"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{35}(?![A-Za-z0-9_-])"),
    ),
    (
        "API secret key (sk-...)",
        re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"),
    ),
    (
        "unresolved chart placeholder (<!-- CHART_)",
        re.compile(r"<!--\s*CHART_"),
    ),
    (
        "unresolved gold directive (<!-- GOLD_)",
        re.compile(r"<!--\s*GOLD_"),
    ),
    (
        "unresolved daily metadata block (<!-- DAILY_META_JSON)",
        re.compile(r"<!--\s*DAILY_META_JSON"),
    ),
    (
        "unresolved gold daily directive (<!-- DAILY_*)",
        re.compile(
            r"<!--\s*DAILY_(?:META|VERDICT|SIGNAL_NOISE|PERSONA|GLOSSARY|"
            r"LAYER_BADGE|TRUST_BAR|CHART_[A-Z0-9_]+)\b"
        ),
    ),
    (
        "unresolved DOCX chart token (___DOCX_CHART_)",
        re.compile(r"___DOCX_CHART_"),
    ),
    (
        "unresolved internal relative-link sentinel (gir-local.invalid)",
        re.compile(r"gir-local\.invalid", re.IGNORECASE),
    ),
)

# Unrendered Markdown table alignment / separator rows appearing in visible HTML text.
S3_RAW_MD_SEP_RE = re.compile(
    r"\|\s*(?::-{2,}:?|-{2,}:)\s*\||\|\s*-{3,}\s*\|\s*-{3,}\s*\|"
)
# Unrendered Markdown bold (**...**) and stray backticks (`) in visible prose outside <code>/<pre>.
S3_RAW_MD_BOLD_RE = re.compile(r"\*\*[^\s*\n][^*\n]{0,160}\*\*")
S3_STRAY_BACKTICK_RE = re.compile(r"`")
# Literal JS rendering corruption tokens in visible HTML or embedded payloads.
S3_JS_RENDER_LEAK_RE = re.compile(
    r"(?<![A-Za-z0-9_])NaN(?![A-Za-z0-9_])|\[object\s+Object\]",
)
# Internal engineering/data filenames and tooling identifiers that must never leak onto public web pages.
S3_INTERNAL_ENG_LEAK_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:sidecar\.json|RSI_PLAYBOOK(?:\.md)?|rsi_metrics\.json|"
    r"data_snapshot\.json|master_snapshot\.json|market_state\.json|market_calendar\.json|"
    r"multi_asset_channels\.json|etf_universe\.json|deep_dossiers\.json|"
    r"report_meta_[A-Za-z0-9_*]+\.json|edition-runs\.sqlite3|"
    r"permissions\.json|unified-edition\.prompt\.md|"
    r"DAILY_FORMAT_SPEC\.md|DAILY_REPORT_SPEC\.md|"
    r"lint_readability\.py|lint_equity\.py|lint_site\.py|"
    r"build_(?:daily|report|site|a_share_pdf|hk_stock_pdf|us_stock_pdf|pdf)\.py|"
    r"publish_site\.py|pdf_common\.py|docx_embed\.py|"
    r"edition_run\.py|artifact_receipt\.py|edition_plan\.py|edition_validation\.py|"
    r"chart_input\.py|install_sidecars\.py|patch_state_dbs\.py|"
    r"_edition_patch\.json|_ledger_patch\.json|"
    r"AGENTS\.md|SKILL\.md|GEMINI\.md|audit_ledger\.md|gold-research-publishing)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Gate S4 configuration (Vector SVG chart integrity)
# ---------------------------------------------------------------------------
FLAGSHIP_MIN_CHARTS: dict[str, int] = {
    "reports/gold.html": 7,
    "reports/a-share.html": 7,
    "reports/hk-stock.html": 7,
    "reports/us-stock.html": 7,
}

# Cutover from which all-4-main (>=2 SVG) and upgraded holiday_watch (>=1 SVG) apply.
ALL_MAIN_CUTOVER: tuple[str, int, int] = ("2026-11-26", 1800, 1)
DAILY_DATED_RE = re.compile(
    r"^daily/(gold|a-share|hk-stock|us-stock)-(\d{4}-\d{2}-\d{2})-(\d{4})(?:-r(\d+))?\.html$"
)
EDITION_KEY_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[_-](\d{4})(?:[_-]r(\d+))?")

DAILY_GOLD_LATEST_PAGE = "daily/gold-latest.html"
DAILY_EQUITY_LATEST_PAGES: tuple[tuple[str, str], ...] = (
    ("a_share", "daily/a-share-latest.html"),
    ("hk_stock", "daily/hk-stock-latest.html"),
    ("us_stock", "daily/us-stock-latest.html"),
)

# Pure JS-only hook classes (if any) exempt from CSS declaration audit in Gate S5.
JS_HOOK_CLASS_ALLOWLIST: frozenset[str] = frozenset()

CHART_CONTAINER_CLASS_RE = re.compile(
    r"(?:^|[-_])(?:chart[-_]?(?:box|card|wrap|wrapper|container|panel|figure|svg|block)|"
    r"svg[-_]?chart|data[-_]?chart)(?:$|[-_])",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Gate S5 configuration (Responsive & table scroll wrappers)
# ---------------------------------------------------------------------------
VIEWPORT_WIDTH_RE = re.compile(r"\bwidth\s*=\s*device-width\b", re.IGNORECASE)
VIEWPORT_COVER_RE = re.compile(r"\bviewport-fit\s*=\s*cover\b", re.IGNORECASE)
INLINE_OVERFLOW_SCROLL_RE = re.compile(
    r"overflow(?:-x)?\s*:\s*(?:auto|scroll)\b", re.IGNORECASE
)
SCROLL_WRAP_CLASS_RE = re.compile(
    r"(?:^|[-_])(?:table[-_]?(?:wrap|wrapper|scroll|responsive|container|box|shell|outer|overflow)|"
    r"tbl[-_]?wrap|kanban[-_]?wrap|scroll[-_]?(?:wrap|table|x)|"
    r"overflow[-_]?x[-_]?(?:auto|scroll)|overflow[-_]?auto|"
    r"responsive[-_]?table|data[-_]?table[-_]?wrap)(?:$|[-_])",
    re.IGNORECASE,
)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_RULE_RE = re.compile(r"([^{}@]+)\{([^{}]+)\}")
CSS_CLASS_RE = re.compile(r"\.([A-Za-z_-][A-Za-z0-9_-]*)")

# ---------------------------------------------------------------------------
# Gate S6 configuration (Live SSOT & Gold Tier 0 mutex)
# ---------------------------------------------------------------------------
GOLD_ETF_CODES: frozenset[str] = frozenset(
    {
        "518660",
        "518880",
        "518850",
        "159934",
        "159937",
        "518800",
        "517520",
        "159562",
        "02840",
        "02840.HK",
        "09840",
        "03081",
        "03081.HK",
        "GLD",
        "IAU",
        "IAUM",
        "GLDM",
        "IGLN",
        "GDX",
        "GDXJ",
        "SGOL",
        "BAR",
        "SGLN",
    }
)
GOLD_ETF_FORBIDDEN_ROLES: tuple[str, ...] = (
    "底座",
    "买入",
    "推荐",
    "加仓",
    "定投",
    "配置",
    "建仓",
)
_GOLD_TARGET_RE_FRAG = (
    r"(?:黄金(?:股|ETF|ETC|基金|积存金|金条)?|金仓|金矿股?|"
    r"(?<![A-Za-z0-9])(?:518660|518880|518850|159934|159937|518800|517520|159562|"
    r"02840(?:\.HK)?|03081(?:\.HK)?|01929(?:\.HK)?|06181(?:\.HK)?|"
    r"GLD|IAU|IAUM|GLDM|IGLN|GDX|GDXJ|NEM|FCX)(?![A-Za-z0-9]))"
)
GOLD_ACTIVE_BUY_RE = re.compile(
    rf"(?:趁急跌.{{0,12}}(?:补齐|买|低吸|定投|建仓).{{0,8}}{_GOLD_TARGET_RE_FRAG}|"
    rf"(?:小批|分批|立刻|马上|立即|同步|今[日早晚]).{{0,8}}(?:补齐|补足|买入|买进|加仓|加配|建仓|配置|定投|抄底).{{0,8}}(?:[0-9一二两三半成%]*\s*)?{_GOLD_TARGET_RE_FRAG}|"
    rf"(?:补齐|补足)\s*[0-9一二两三半成%]*\s*(?:黄金|金仓)|"
    rf"(?:加配|逢低买|抄底|定投|建仓)\s*[0-9一二两三半成%]*\s*{_GOLD_TARGET_RE_FRAG}|"
    rf"(?:立即|马上|现在|建议|可以|开启|启动).{{0,6}}(?:买入|买进|建仓|加仓|配置|定投|抄底).{{0,6}}{_GOLD_TARGET_RE_FRAG}|"
    r"\b(?:buy\s+gold|add\s+gold|accumulate\s+gold|dca\s+into\s+gold|buy\s+now[^\n]{0,20}gold)\b)",
    re.IGNORECASE,
)
GOLD_CTA_BUY_RE = re.compile(
    rf"(?:(?:立即|马上|一键|去|开始)?(?:买入|买进|加仓|建仓|抄底|配置|定投)\s*{_GOLD_TARGET_RE_FRAG}|"
    r"(?:立即|马上|去)买金|"
    r"\b(?:buy\s+gold|accumulate\s+gold|dca\s+into\s+gold)\b)",
    re.IGNORECASE,
)
GOLD_DEFER_GUARD_RE = re.compile(
    r"(?:暂不|严禁|禁止|切忌|勿|停止|先别|不能|不宜|不要|别急着|拒绝|不考虑|不允许|不应|不会|暂停|无需|不)"
    r"(?:现在|今天|今日|当下|立即|马上|急于|立刻|再|去|主动|新|分批|小批|继续|同步|进行|尝试|建议|允许|任何|新增|直接|冲动)*"
    r"\s*(?:补|买|加|建|抄|配置|定投|低吸|开启|启动)"
    r"|(?:待|等).{0,18}(?:黄灯|绿灯|解锁)|(?:黄灯|绿灯|解锁|过四关|全部过关)(?:亮起|确认)?后|"
    r"\b(?:do\s+not|never|should\s+not|must\s+not|hold\s+off|pause)\s+(?:buy|add|accumulat|dca)",
    re.IGNORECASE,
)
GOLD_TIER0_LOCK_INDICATORS_RE = re.compile(
    r"(?:Tier\s*0|红灯停|暂不新买|新仓\s*0%|不新买|严禁新买|严禁抢跑|红灯防守)",
    re.IGNORECASE,
)
SCREENER_RAW_MARKUP_RE = re.compile(r"<br\b|\*\*|`", re.IGNORECASE)
GOLD_STOCK_RE = re.compile(
    r"黄金|金矿|金饰|金业|招金|紫金矿业|紫金黄金|山东黄金|中金黄金|赤峰黄金|山金国际|老铺黄金|周大福|纽蒙特|"
    r"(?<![A-Za-z0-9])(?:518660|518880|518850|159934|159937|518800|517520|159562|"
    r"02840(?:\.HK)?|03081(?:\.HK)?|09840(?:\.HK)?|01929(?:\.HK)?|06181(?:\.HK)?|"
    r"02899(?:\.HK)?|601899|600547|600489|"
    r"GLD|IAU|IAUM|GLDM|IGLN|GDX|GDXJ|NEM|FCX|PAXG|XAUT)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
SCREENER_VALID_COLORS = frozenset({"g", "b", "y", "r"})
SCREENER_REQUIRED_FIELDS: tuple[str, ...] = (
    "market",
    "sector",
    "name",
    "code",
    "price",
    "valuation",
    "color",
    "summary",
)
DOSSIER_DIMENSIONS: tuple[str, ...] = (
    "moat",
    "financials",
    "valuation_anchor",
    "shareholder_flow",
    "catalysts",
    "bear_case",
    "action_etf",
)


# ---------------------------------------------------------------------------
# Parsed HTML model
# ---------------------------------------------------------------------------
@dataclass
class LinkRef:
    tag: str
    attr: str
    value: str
    lineno: int


@dataclass
class SvgInfo:
    lineno: int
    viewbox_w: float | None
    viewbox_h: float | None
    width_px: float | None
    in_chart_container: bool
    is_nested: bool
    has_content: bool

    @property
    def is_data_chart(self) -> bool:
        if self.is_nested or not self.has_content:
            return False
        if self.viewbox_w is not None:
            if self.viewbox_w >= 300.0:
                return True
            if self.viewbox_w < 100.0:
                return False
        if self.in_chart_container:
            return True
        if self.width_px is not None and self.width_px >= 300.0:
            return True
        return False


@dataclass
class TableInfo:
    lineno: int
    in_article_or_main: bool
    ancestor_classes: set[str]
    has_inline_scroll_ancestor: bool


@dataclass
class CtaInfo:
    tag: str
    lineno: int
    classes: set[str]
    text: str


@dataclass
class ParsedHtml:
    rel_path: str
    abs_path: Path
    raw_text: str
    ids: set[str] = field(default_factory=set)
    id_lines: dict[str, list[int]] = field(default_factory=dict)
    secondary_targets: set[str] = field(default_factory=set)
    links: list[LinkRef] = field(default_factory=list)
    svgs: list[SvgInfo] = field(default_factory=list)
    tables: list[TableInfo] = field(default_factory=list)
    ctas: list[CtaInfo] = field(default_factory=list)
    used_classes: set[str] = field(default_factory=set)
    has_utf8_charset: bool = False
    has_viewport_meta: bool = False
    viewport_has_device_width: bool = False
    viewport_has_cover: bool = False
    has_title: bool = False
    title_text: str = ""
    has_nav: bool = False
    edition_attr: str = ""
    stock_row_count: int = 0
    tbody_row_count: int = 0
    etf_tbody_row_count: int = 0
    screener_json_raw: str | None = None
    etf_json_raw: str | None = None
    ch_etf_json_raw: str | None = None
    inline_styles: list[str] = field(default_factory=list)
    visible_text: str = ""
    prose_text: str = ""


def _parse_viewbox(vb: str | None) -> tuple[float | None, float | None]:
    if not vb:
        return None, None
    parts = [p for p in re.split(r"[\s,]+", vb.strip()) if p]
    if len(parts) != 4:
        return None, None
    try:
        return float(parts[2]), float(parts[3])
    except ValueError:
        return None, None


def _parse_px_number(val: str | None) -> float | None:
    if not val:
        return None
    s = val.strip().lower()
    if s.endswith("%"):
        return None
    if s.endswith("px"):
        s = s[:-2].strip()
    try:
        return float(s)
    except ValueError:
        return None


def _extract_scrollable_classes_from_css(css_text: str) -> set[str]:
    """Find CSS class names whose rules declare overflow-x/overflow: auto|scroll."""
    classes: set[str] = set()
    cleaned = CSS_COMMENT_RE.sub("", css_text)
    for sel_group, body in CSS_RULE_RE.findall(cleaned):
        if not INLINE_OVERFLOW_SCROLL_RE.search(body):
            continue
        for sel in sel_group.split(","):
            # Take the rightmost compound selector (the element actually receiving overflow).
            tail = sel.strip().split()[-1] if sel.strip() else ""
            tail = tail.split(">")[-1].split("+")[-1].split("~")[-1]
            for cls in CSS_CLASS_RE.findall(tail):
                classes.add(cls)
    return classes


def _extract_all_declared_css_classes(css_text: str) -> set[str]:
    """Extract every CSS class referenced in selectors (including nested @media/@supports blocks),
    strictly ignoring declaration bodies so url(x.svg) or decimal values are never misread."""
    cleaned = CSS_COMMENT_RE.sub("", css_text)
    classes: set[str] = set()
    block_stack: list[bool] = []  # True = nested at-rule (@media/@supports/@layer); False = style decl block
    buf: list[str] = []
    in_str: str | None = None
    escaped = False

    for ch in cleaned:
        if in_str is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'"):
            in_str = ch
            continue

        in_decl = bool(block_stack and not block_stack[-1])
        if ch == "{":
            if in_decl:
                block_stack.append(False)
            else:
                header = "".join(buf).strip()
                buf = []
                if header.startswith("@"):
                    # @media / @supports / @layer / @container wrap nested selectors; @page / @font-face hold decls
                    is_nested_at = bool(
                        re.match(r"^@(?:media|supports|layer|container|scope|document)\b", header, re.IGNORECASE)
                    )
                    block_stack.append(is_nested_at)
                else:
                    for cls in CSS_CLASS_RE.findall(header):
                        classes.add(cls)
                    block_stack.append(False)
        elif ch == "}":
            buf = []
            if block_stack:
                block_stack.pop()
        elif ch == ";":
            if not in_decl:
                buf = []
        else:
            if not in_decl:
                buf.append(ch)
    return classes


class SiteHtmlParser(HTMLParser):
    """Single-pass stdlib HTMLParser collecting data for Gates S2, S3, S4, S5, S6."""

    def __init__(self, rel_path: str, abs_path: Path, raw_text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.doc = ParsedHtml(rel_path=rel_path, abs_path=abs_path, raw_text=raw_text)
        # Stack of (tag, classes_set, inline_style, elem_id)
        self._stack: list[tuple[str, set[str], str, str]] = []
        self._svg_stack: list[SvgInfo] = []
        self._in_title = False
        self._title_chunks: list[str] = []
        self._in_style = False
        self._style_chunks: list[str] = []
        self._in_screener_json = False
        self._screener_json_chunks: list[str] = []
        self._in_etf_json = False
        self._etf_json_chunks: list[str] = []
        self._in_ch_etf_json = False
        self._ch_etf_json_chunks: list[str] = []
        self._skip_text_depth = 0  # script / style / template
        self._code_depth = 0  # code / pre / kbd / samp
        self._vis_chunks: list[str] = []
        self._prose_chunks: list[str] = []
        self._cta_stack: list[tuple[str, int, set[str], list[str]]] = []

    def _on_open(self, tag: str, attrs: list[tuple[str, str | None]], self_closing: bool) -> None:
        t = tag.lower()
        attr_map: dict[str, str] = {}
        for k, v in attrs:
            if k:
                attr_map[k.lower()] = "" if v is None else v

        lineno = self.getpos()[0]
        cls_raw = attr_map.get("class", "")
        classes = {c for c in cls_raw.split() if c}
        style_raw = attr_map.get("style", "")

        # Track HTML element classes outside <svg> for Gate S5 CSS declaration audit.
        if not self._svg_stack and t != "svg" and classes:
            self.doc.used_classes.update(classes)

        # Capture edition metadata attribute if set on html/body/main/article.
        for ed_key in ("data-edition", "data-edition-type"):
            if ed_key in attr_map and attr_map[ed_key].strip() and not self.doc.edition_attr:
                self.doc.edition_attr = attr_map[ed_key].strip().lower()

        # Track explicit stock ticker rows/cards for Gate S6 fidelity check.
        if "data-ticker" in attr_map or (t == "tr" and "data-market" in attr_map):
            self.doc.stock_row_count += 1
        if t == "tr":
            for st_tag, _, _, st_id in reversed(self._stack):
                if st_tag == "tbody":
                    self.doc.tbody_row_count += 1
                    if st_id == "etf-tbody":
                        self.doc.etf_tbody_row_count += 1
                    break
                if st_tag == "table":
                    break

        # Collect element IDs & secondary JS/tab anchors (Gate S2).
        elem_id = attr_map.get("id", "").strip()
        if elem_id:
            self.doc.ids.add(elem_id)
            if not self._svg_stack and t != "svg":
                self.doc.id_lines.setdefault(elem_id, []).append(lineno)
        if t == "a":
            a_name = attr_map.get("name", "").strip()
            if a_name:
                self.doc.ids.add(a_name)
        for sec_attr in ("data-tab", "data-section", "data-panel", "data-anchor"):
            sv = attr_map.get(sec_attr, "").strip()
            if sv:
                self.doc.secondary_targets.add(sv)

        # Collect link/asset attributes (Gate S2).
        if t in LINK_ATTR_BY_TAG:
            req_attr = LINK_ATTR_BY_TAG[t]
            if req_attr in attr_map:
                self.doc.links.append(
                    LinkRef(tag=t, attr=req_attr, value=attr_map[req_attr], lineno=lineno)
                )

        # Gate S5 metadata & nav checks.
        if t == "meta":
            charset = attr_map.get("charset", "").strip().lower()
            if charset == "utf-8":
                self.doc.has_utf8_charset = True
            name_val = attr_map.get("name", "").strip().lower()
            if name_val == "viewport":
                self.doc.has_viewport_meta = True
                content = attr_map.get("content", "")
                if VIEWPORT_WIDTH_RE.search(content):
                    self.doc.viewport_has_device_width = True
                if VIEWPORT_COVER_RE.search(content):
                    self.doc.viewport_has_cover = True
        elif t == "nav":
            self.doc.has_nav = True

        # Gate S5 table wrapper check.
        if t == "table":
            in_art_main = any(st_tag in ("article", "main") for st_tag, _, _, _ in self._stack)
            anc_classes: set[str] = set()
            has_inline_scroll = bool(
                style_raw and INLINE_OVERFLOW_SCROLL_RE.search(style_raw)
            )
            for _, st_cls, st_style, _ in self._stack:
                anc_classes.update(st_cls)
                if st_style and INLINE_OVERFLOW_SCROLL_RE.search(st_style):
                    has_inline_scroll = True
            self.doc.tables.append(
                TableInfo(
                    lineno=lineno,
                    in_article_or_main=in_art_main,
                    ancestor_classes=anc_classes,
                    has_inline_scroll_ancestor=has_inline_scroll,
                )
            )

        # Gate S4 SVG tracking.
        if self._svg_stack and t != "svg":
            # Any child element inside an open <svg> marks it non-empty.
            self._svg_stack[-1].has_content = True

        if t == "svg":
            if self._svg_stack:
                self._svg_stack[-1].has_content = True
            vb_w, vb_h = _parse_viewbox(attr_map.get("viewbox"))
            width_px = _parse_px_number(attr_map.get("width"))
            in_chart_box = any(
                any(CHART_CONTAINER_CLASS_RE.search(c) for c in st_cls)
                for _, st_cls, _, _ in self._stack
            ) or any(CHART_CONTAINER_CLASS_RE.search(c) for c in classes)
            svg_info = SvgInfo(
                lineno=lineno,
                viewbox_w=vb_w,
                viewbox_h=vb_h,
                width_px=width_px,
                in_chart_container=in_chart_box,
                is_nested=bool(self._svg_stack),
                has_content=False,
            )
            if self_closing:
                self.doc.svgs.append(svg_info)
            else:
                self._svg_stack.append(svg_info)

        # Block text separator for clean visible text extraction.
        if t in BLOCK_TEXT_TAGS and self._skip_text_depth == 0:
            self._vis_chunks.append("\n")
            if self._code_depth == 0 and not self._svg_stack:
                self._prose_chunks.append("\n")

        if self_closing or t in VOID_ELEMENTS:
            return

        # Push onto ancestor stack for non-void elements.
        self._stack.append((t, classes, style_raw, elem_id))

        if t == "title":
            self.doc.has_title = True
            self._in_title = True
            self._title_chunks = []
        elif t in ("script", "style", "template"):
            self._skip_text_depth += 1
            if t == "style":
                self._in_style = True
                self._style_chunks = []
            elif (
                t == "script"
                and elem_id == "screener-data"
                and attr_map.get("type", "").strip().lower() == "application/json"
            ):
                self._in_screener_json = True
                self._screener_json_chunks = []
            elif (
                t == "script"
                and elem_id == "etf-data"
                and attr_map.get("type", "").strip().lower() == "application/json"
            ):
                self._in_etf_json = True
                self._etf_json_chunks = []
            elif (
                t == "script"
                and elem_id == "ch-etf-data"
                and attr_map.get("type", "").strip().lower() == "application/json"
            ):
                self._in_ch_etf_json = True
                self._ch_etf_json_chunks = []
        elif t in ("code", "pre", "kbd", "samp"):
            self._code_depth += 1
        elif t in ("button", "a"):
            self._cta_stack.append((t, lineno, classes, []))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._on_open(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._on_open(tag, attrs, self_closing=True)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in VOID_ELEMENTS:
            return

        if t == "svg" and self._svg_stack:
            self.doc.svgs.append(self._svg_stack.pop())

        if t == "title" and self._in_title:
            self._in_title = False
            if not self.doc.title_text.strip():
                self.doc.title_text = "".join(self._title_chunks).strip()
            self._title_chunks = []

        if t == "style" and self._in_style:
            self._in_style = False
            self.doc.inline_styles.append("".join(self._style_chunks))
            self._style_chunks = []

        if t == "script" and self._in_screener_json:
            self._in_screener_json = False
            self.doc.screener_json_raw = "".join(self._screener_json_chunks)
            self._screener_json_chunks = []

        if t == "script" and self._in_etf_json:
            self._in_etf_json = False
            self.doc.etf_json_raw = "".join(self._etf_json_chunks)
            self._etf_json_chunks = []

        if t == "script" and self._in_ch_etf_json:
            self._in_ch_etf_json = False
            self.doc.ch_etf_json_raw = "".join(self._ch_etf_json_chunks)
            self._ch_etf_json_chunks = []

        if t in ("script", "style", "template") and self._skip_text_depth > 0:
            self._skip_text_depth -= 1

        if t in ("code", "pre", "kbd", "samp") and self._code_depth > 0:
            self._code_depth -= 1

        if t in ("button", "a") and self._cta_stack:
            for idx in range(len(self._cta_stack) - 1, -1, -1):
                if self._cta_stack[idx][0] == t:
                    c_tag, c_line, c_cls, c_chunks = self._cta_stack.pop(idx)
                    c_text = " ".join("".join(c_chunks).split())
                    if c_text:
                        self.doc.ctas.append(
                            CtaInfo(tag=c_tag, lineno=c_line, classes=c_cls, text=c_text)
                        )
                    break

        if t in BLOCK_TEXT_TAGS and self._skip_text_depth == 0:
            self._vis_chunks.append("\n")
            if self._code_depth == 0 and not self._svg_stack:
                self._prose_chunks.append("\n")

        # Resiliently pop back to matching open tag if present on stack.
        for idx in range(len(self._stack) - 1, -1, -1):
            if self._stack[idx][0] == t:
                del self._stack[idx:]
                break

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_chunks.append(data)
        if self._in_style:
            self._style_chunks.append(data)
        if self._in_screener_json:
            self._screener_json_chunks.append(data)
        if self._in_etf_json:
            self._etf_json_chunks.append(data)
        if self._in_ch_etf_json:
            self._ch_etf_json_chunks.append(data)
        if self._svg_stack and data.strip():
            self._svg_stack[-1].has_content = True
        if self._skip_text_depth == 0:
            self._vis_chunks.append(data)
            if self._code_depth == 0 and not self._svg_stack:
                self._prose_chunks.append(data)
            if self._cta_stack:
                self._cta_stack[-1][3].append(data)

    def finish(self) -> ParsedHtml:
        # Flush any unclosed SVGs so they still get inspected.
        while self._svg_stack:
            self.doc.svgs.append(self._svg_stack.pop())
        self.doc.visible_text = "".join(self._vis_chunks)
        self.doc.prose_text = "".join(self._prose_chunks)
        return self.doc


def parse_html_file(rel_path: str, abs_path: Path, raw_text: str) -> ParsedHtml:
    parser = SiteHtmlParser(rel_path, abs_path, raw_text)
    parser.feed(raw_text)
    parser.close()
    return parser.finish()


# ---------------------------------------------------------------------------
# Helpers for Gate S6 numeric matching
# ---------------------------------------------------------------------------
def _numeric_variants(val: float, extra_vals: Iterable[float | int] = ()) -> list[str]:
    """Generate formatted string variants (commas / plain, 2dp / 1dp / rounded / floored)."""
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(s: str) -> None:
        if s and s not in seen:
            seen.add(s)
            candidates.append(s)

    for num in (val, *extra_vals):
        f = float(num)
        r = round(f)
        fl = int(f)
        _add(f"{f:,.2f}")
        _add(f"{f:.2f}")
        _add(f"{f:,.1f}")
        _add(f"{f:.1f}")
        _add(f"{r:,}")
        _add(f"{r}")
        _add(f"{fl:,}")
        _add(f"{fl}")
    return candidates


def _contains_any_number(text: str, variants: list[str]) -> bool:
    for token in variants:
        pat = re.compile(rf"(?<![0-9]){re.escape(token)}(?![0-9])")
        if pat.search(text):
            return True
    return False


def _line_number_at(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


# ---------------------------------------------------------------------------
# Gate runners
# ---------------------------------------------------------------------------
def run_gate_s1(
    site_dir: Path,
    errors: list[str],
    warnings: list[str],
) -> tuple[dict[str, ParsedHtml], list[Path]]:
    """Gate S1: Completeness, valid UTF-8, >= 3,000 byte HTML floor, valid manifest.json."""
    parsed_htmls: dict[str, ParsedHtml] = {}
    all_files: list[Path] = []

    if not site_dir.exists() or not site_dir.is_dir():
        errors.append(f"[S1] Site directory does not exist or is not a directory: {site_dir}")
        return parsed_htmls, all_files

    for rel in REQUIRED_SENTINEL_FILES:
        p = site_dir / rel
        if not p.is_file():
            errors.append(f"[S1] Missing required sentinel file: {rel}")

    for rel in REQUIRED_NONEMPTY_FILES:
        p = site_dir / rel
        if not p.is_file():
            errors.append(f"[S1] Missing required core artifact: {rel}")
        elif p.stat().st_size == 0:
            errors.append(f"[S1] Required core artifact is empty (0 bytes): {rel}")

    manifest_path = site_dir / "manifest.json"
    if manifest_path.is_file() and manifest_path.stat().st_size > 0:
        try:
            manifest_obj = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest_obj, dict) or not manifest_obj:
                errors.append("[S1] manifest.json must be a non-empty JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"[S1] manifest.json failed UTF-8/JSON parsing: {exc}")

    for p in sorted(site_dir.rglob("*")):
        if not p.is_file():
            continue
        all_files.append(p)
        if p.suffix.lower() not in HTML_SUFFIXES:
            continue
        rel_str = p.relative_to(site_dir).as_posix()
        raw_bytes = p.read_bytes()
        if len(raw_bytes) < MIN_HTML_BYTES:
            errors.append(
                f"[S1] HTML page too small ({len(raw_bytes)} bytes < {MIN_HTML_BYTES}): {rel_str}"
            )
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"[S1] Invalid UTF-8 encoding in {rel_str}: {exc}")
            continue
        parsed_htmls[rel_str] = parse_html_file(rel_str, p.resolve(), text)

    return parsed_htmls, all_files


def run_gate_s2(
    site_dir: Path,
    parsed_htmls: dict[str, ParsedHtml],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Gate S2: Zero broken internal links, assets, anchors, duplicate IDs, or non-canonical Release URLs."""
    site_root = site_dir.resolve()
    by_abs: dict[Path, ParsedHtml] = {doc.abs_path: doc for doc in parsed_htmls.values()}

    for rel_path, doc in sorted(parsed_htmls.items()):
        # Hard error on duplicate element IDs within the same HTML document.
        for elem_id, line_list in sorted(doc.id_lines.items()):
            if len(line_list) > 1:
                lines_disp = ", ".join(f"L{ln}" for ln in line_list[:6])
                errors.append(
                    f"[S2] {rel_path}: duplicate id=\"{elem_id}\" appears {len(line_list)} times ({lines_disp})"
                )

        for link in doc.links:
            raw_ref = link.value.strip()
            if not raw_ref:
                if link.tag in ("img", "script", "link"):
                    errors.append(
                        f"[S2] {rel_path}:{link.lineno}: empty <{link.tag} {link.attr}=\"\"> attribute"
                    )
                continue

            lower_ref = raw_ref.lower()
            scheme_norm = re.sub(r"[\x00-\x20]+", "", raw_ref).lower()
            is_http = lower_ref.startswith(("http://", "https://"))

            # Web-only portal check: forbid Release download links (any scheme)
            # and non-HTTP(S) PDF/Word links (external official PDF citations remain allowed).
            if FORBIDDEN_RELEASE_LINK_RE.search(raw_ref) or (
                not is_http and FORBIDDEN_BINARY_LINK_RE.search(raw_ref)
            ):
                errors.append(
                    f"[S2] {rel_path}:{link.lineno}: forbidden PDF/Word or Release download link in web-only portal: {raw_ref!r}"
                )

            # Detect double-escaped '&amp;amp;' in link attributes (decoded by HTMLParser to literal '&amp;').
            if "&amp;" in lower_ref:
                errors.append(
                    f"[S2] {rel_path}:{link.lineno}: double-escaped '&amp;amp;' in <{link.tag} {link.attr}>: {raw_ref!r}"
                )

            if scheme_norm.startswith("file:"):
                errors.append(
                    f"[S2] {rel_path}:{link.lineno}: forbidden local file:// reference in <{link.tag} {link.attr}>: {raw_ref}"
                )
                continue
            if scheme_norm.startswith(FORBIDDEN_URI_SCHEMES):
                errors.append(
                    f"[S2] {rel_path}:{link.lineno}: forbidden URI scheme in <{link.tag} {link.attr}>: {raw_ref!r}"
                )
                continue
            if lower_ref.startswith(EXTERNAL_SCHEMES):
                continue
            if raw_ref.startswith("//"):
                errors.append(
                    f"[S2] {rel_path}:{link.lineno}: disallowed protocol-relative URL in <{link.tag} {link.attr}>: {raw_ref!r}"
                )
                continue

            # Pure "#" is a standard HTML top-of-page / interactive anchor.
            if raw_ref == "#":
                continue

            parsed = urllib.parse.urlsplit(raw_ref)
            if parsed.scheme:
                errors.append(
                    f"[S2] {rel_path}:{link.lineno}: unsupported URI scheme '{parsed.scheme}:' in <{link.tag} {link.attr}>: {raw_ref!r}"
                )
                continue
            path_part = urllib.parse.unquote(parsed.path)
            raw_frag = parsed.fragment
            unquoted_frag = urllib.parse.unquote(raw_frag)

            is_same_file_ref = path_part == ""
            if is_same_file_ref:
                target_path = doc.abs_path
            else:
                if path_part.startswith("/"):
                    candidate = (site_root / path_part.lstrip("/")).resolve()
                else:
                    candidate = (doc.abs_path.parent / path_part).resolve()

                if path_part.endswith("/") or (candidate.exists() and candidate.is_dir()):
                    candidate = (candidate / "index.html").resolve()
                target_path = candidate

            if not target_path.is_relative_to(site_root):
                errors.append(
                    f"[S2] {rel_path}:{link.lineno}: internal link escapes site root: "
                    f"<{link.tag} {link.attr}=\"{raw_ref}\">"
                )
                continue

            if not target_path.exists() or not target_path.is_file():
                errors.append(
                    f"[S2] {rel_path}:{link.lineno}: broken internal {link.tag}[{link.attr}] target: "
                    f"\"{raw_ref}\" (resolved: {target_path.relative_to(site_root).as_posix()})"
                )
                continue

            # Fragment (#anchor) verification against parsed HTML targets.
            if raw_frag:
                if unquoted_frag.lower() == "top":
                    continue
                # Skip SPA/JS query-like hash routes (e.g. #market=a_share or #/tab/1).
                if any(ch in unquoted_frag for ch in ("=", "&", "/")):
                    continue
                target_doc = by_abs.get(target_path)
                if target_doc is not None:
                    matched_id = (
                        raw_frag in target_doc.ids or unquoted_frag in target_doc.ids
                    )
                    if not matched_id:
                        if is_same_file_ref or target_path == doc.abs_path:
                            errors.append(
                                f"[S2] {rel_path}:{link.lineno}: broken same-page anchor \"#{unquoted_frag}\" "
                                f"(no matching id in {rel_path})"
                            )
                        else:
                            matched_secondary = (
                                raw_frag in target_doc.secondary_targets
                                or unquoted_frag in target_doc.secondary_targets
                            )
                            if not matched_secondary:
                                warnings.append(
                                    f"[S2] {rel_path}:{link.lineno}: cross-page anchor \"#{unquoted_frag}\" "
                                    f"not found as id/data-tab in {target_doc.rel_path}"
                                )


def _iter_json_strings(obj: object, prefix: str = "") -> Iterable[tuple[str, str]]:
    """Yield (field_path, string_value) pairs from nested JSON lists/objects."""
    if isinstance(obj, str):
        yield prefix, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            sub = f"{prefix}.{k}" if prefix else str(k)
            yield from _iter_json_strings(v, sub)
    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            yield from _iter_json_strings(v, f"{prefix}[{idx}]")


def _scan_embedded_json_payload(
    rel_path: str,
    json_id: str,
    raw_json: str,
    errors: list[str],
    *,
    check_eng: bool = True,
    check_gold_tier0: bool = False,
    gate_tag: str = "S3",
) -> None:
    """Scan string leaves in #screener-data / #etf-data / #ch-etf-data for engineering leaks, NaN/[object Object], and Gold Tier 0 buy directives."""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return  # Invalid JSON is explicitly reported by Gate S6.

    eng_hits = 0
    js_hits = 0
    gold_hits = 0
    for field_path, val in _iter_json_strings(payload):
        if check_eng and eng_hits < 5:
            m_eng = S3_INTERNAL_ENG_LEAK_RE.search(val)
            if m_eng:
                snippet = " ".join(val[max(0, m_eng.start() - 16) : min(len(val), m_eng.end() + 16)].split())
                errors.append(
                    f"[S3] {rel_path}: #{json_id} ({field_path}) leaked internal engineering filename/identifier -> {snippet!r}"
                )
                eng_hits += 1
        if check_eng and js_hits < 5:
            m_js = S3_JS_RENDER_LEAK_RE.search(val)
            if m_js:
                snippet = " ".join(val[max(0, m_js.start() - 16) : min(len(val), m_js.end() + 16)].split())
                errors.append(
                    f"[S3] {rel_path}: #{json_id} ({field_path}) leaked literal NaN/[object Object] -> {snippet!r}"
                )
                js_hits += 1
        if check_gold_tier0 and gold_hits < 5:
            for raw_seg in re.split(r"[\n。！？；，,]+", val):
                seg = " ".join(raw_seg.split())
                if not seg:
                    continue
                for m_g in GOLD_ACTIVE_BUY_RE.finditer(seg):
                    if not _gold_action_is_guarded(seg, m_g):
                        win = seg[max(0, m_g.start() - 36) : min(len(seg), m_g.end() + 36)]
                        errors.append(
                            f"[{gate_tag}] {rel_path}: Gold Tier 0 mutex violation — unguarded buy-gold directive "
                            f"in #{json_id} ({field_path}): {win!r}"
                        )
                        gold_hits += 1
                        break
                if gold_hits >= 5:
                    break


def run_gate_s3(
    site_dir: Path,
    all_files: list[Path],
    parsed_htmls: dict[str, ParsedHtml],
    errors: list[str],
    warnings: list[str],
    *,
    gold_new_buy_blocked: bool = False,
) -> None:
    """Gate S3: Zero PII, local paths, secrets, unresolved directives, raw Markdown, NaN/[object Object], or JSON payload leaks."""
    for p in all_files:
        if p.suffix.lower() not in TEXT_SCAN_SUFFIXES:
            continue
        rel_str = p.relative_to(site_dir).as_posix()
        if rel_str in parsed_htmls:
            text = parsed_htmls[rel_str].raw_text
        else:
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                errors.append(f"[S3] Non-UTF-8 text asset {rel_str}: {exc}")
                continue

        for label, pattern in S3_RAW_PATTERNS:
            m = pattern.search(text)
            if m:
                ln = _line_number_at(text, m.start())
                snippet = text[max(0, m.start() - 12) : min(len(text), m.end() + 24)]
                snippet = " ".join(snippet.split())
                errors.append(
                    f"[S3] {rel_str}:{ln}: leaked {label} -> {snippet!r}"
                )

    for rel_path, doc in sorted(parsed_htmls.items()):
        m = S3_RAW_MD_SEP_RE.search(doc.visible_text)
        if m:
            snippet = " ".join(
                doc.visible_text[max(0, m.start() - 16) : min(len(doc.visible_text), m.end() + 16)].split()
            )
            errors.append(
                f"[S3] {rel_path}: unrendered raw Markdown table separator in visible HTML -> {snippet!r}"
            )

        m_bold = S3_RAW_MD_BOLD_RE.search(doc.prose_text)
        if m_bold:
            snippet = " ".join(
                doc.prose_text[max(0, m_bold.start() - 12) : min(len(doc.prose_text), m_bold.end() + 12)].split()
            )
            errors.append(
                f"[S3] {rel_path}: unrendered raw Markdown **bold** marker in visible prose -> {snippet!r}"
            )

        m_bt = S3_STRAY_BACKTICK_RE.search(doc.prose_text)
        if m_bt:
            snippet = " ".join(
                doc.prose_text[max(0, m_bt.start() - 16) : min(len(doc.prose_text), m_bt.end() + 16)].split()
            )
            errors.append(
                f"[S3] {rel_path}: stray backtick (`) outside <code>/<pre> in visible prose -> {snippet!r}"
            )

        m_js = S3_JS_RENDER_LEAK_RE.search(doc.visible_text)
        if m_js:
            snippet = " ".join(
                doc.visible_text[max(0, m_js.start() - 16) : min(len(doc.visible_text), m_js.end() + 16)].split()
            )
            errors.append(
                f"[S3] {rel_path}: leaked literal NaN/[object Object] in visible HTML -> {snippet!r}"
            )

        m_eng = S3_INTERNAL_ENG_LEAK_RE.search(doc.visible_text)
        if m_eng:
            snippet = " ".join(
                doc.visible_text[max(0, m_eng.start() - 16) : min(len(doc.visible_text), m_eng.end() + 16)].split()
            )
            errors.append(
                f"[S3] {rel_path}: leaked internal engineering filename/identifier -> {snippet!r}"
            )

        if doc.screener_json_raw is not None:
            _scan_embedded_json_payload(
                rel_path,
                "screener-data",
                doc.screener_json_raw,
                errors,
                check_eng=True,
                check_gold_tier0=gold_new_buy_blocked,
                gate_tag="S3",
            )
        if doc.etf_json_raw is not None:
            _scan_embedded_json_payload(
                rel_path,
                "etf-data",
                doc.etf_json_raw,
                errors,
                check_eng=True,
                check_gold_tier0=gold_new_buy_blocked,
                gate_tag="S3",
            )
        if doc.ch_etf_json_raw is not None:
            _scan_embedded_json_payload(
                rel_path,
                "ch-etf-data",
                doc.ch_etf_json_raw,
                errors,
                check_eng=True,
                check_gold_tier0=gold_new_buy_blocked,
                gate_tag="S3",
            )


def _edition_key_from_text(text: str | None) -> tuple[str, int, int] | None:
    if not text or not isinstance(text, str):
        return None
    m = EDITION_KEY_RE.search(text)
    if not m:
        return None
    return m.group(1), int(m.group(2)), int(m.group(3) or 1)


def _daily_edition_type(market_key: str, doc: ParsedHtml, market_state: dict | None) -> str:
    """Determine the edition_type ('main', 'holiday_watch', or 'light') for an equity daily page."""
    if doc.edition_attr in ("main", "light", "holiday_watch"):
        return doc.edition_attr

    if market_state and isinstance(market_state.get("markets"), dict):
        latest_rel = market_state["markets"].get(market_key, {}).get("latest_daily")
        if isinstance(latest_rel, str) and latest_rel.strip():
            md_path = REPO_ROOT / "equity" / latest_rel
            if md_path.is_file():
                try:
                    md_txt = md_path.read_text(encoding="utf-8")
                    m_meta = re.search(
                        r"<!--\s*DAILY_META_JSON\s*(\{.*?\})\s*-->",
                        md_txt,
                        flags=re.DOTALL,
                    )
                    if m_meta:
                        meta_obj = json.loads(m_meta.group(1))
                        ed = str(meta_obj.get("edition_type", "")).strip().lower()
                        if ed in ("main", "light", "holiday_watch"):
                            return ed
                except (OSError, json.JSONDecodeError):
                    pass
    return "main"


def _daily_is_light(market_key: str, doc: ParsedHtml, market_state: dict | None) -> bool:
    """Backward-compatible helper indicating whether an equity daily page is light/holiday_watch."""
    return _daily_edition_type(market_key, doc, market_state) in ("light", "holiday_watch")


def _min_daily_charts(
    edition_type: str, edition_key: tuple[str, int, int] | None, *, is_gold: bool = False
) -> int:
    """Return required SVG chart floor aligned with AGENTS.md (pre-cutover legacy archives stay compatible)."""
    if edition_key is not None and edition_key < ALL_MAIN_CUTOVER:
        if is_gold:
            return 1
        return 0 if edition_type in ("light", "holiday_watch") else 1
    if edition_type == "holiday_watch":
        return 1
    if edition_type == "light":
        return 1 if is_gold else 0
    return 2


def run_gate_s4(
    parsed_htmls: dict[str, ParsedHtml],
    market_state: dict | None,
    errors: list[str],
    warnings: list[str],
    *,
    gold_snap: dict | None = None,
) -> None:
    """Gate S4: Vector SVG chart counts on flagship/daily pages and zero empty <svg> elements."""
    # Check for empty <svg> elements across ALL HTML pages.
    for rel_path, doc in sorted(parsed_htmls.items()):
        for svg in doc.svgs:
            if not svg.has_content:
                errors.append(
                    f"[S4] {rel_path}:{svg.lineno}: empty <svg></svg> element detected"
                )

    # Flagship pages: require >= 7 data charts each.
    for rel_path, min_charts in FLAGSHIP_MIN_CHARTS.items():
        doc = parsed_htmls.get(rel_path)
        if doc is None:
            continue  # Missing file already reported by Gate S1.
        chart_count = sum(1 for s in doc.svgs if s.is_data_chart)
        if chart_count < min_charts:
            errors.append(
                f"[S4] {rel_path}: found only {chart_count} data <svg> chart(s) "
                f"(required >= {min_charts})"
            )

    # Gold daily latest: >= 2 charts post-cutover (main) or >= 1 (holiday_watch / pre-cutover).
    gold_doc = parsed_htmls.get(DAILY_GOLD_LATEST_PAGE)
    if gold_doc is not None:
        gold_key = _edition_key_from_text(str((gold_snap or {}).get("edition_id") or ""))
        gold_ed = gold_doc.edition_attr or "main"
        min_gold = _min_daily_charts(gold_ed, gold_key, is_gold=True)
        chart_count = sum(1 for s in gold_doc.svgs if s.is_data_chart)
        if chart_count < min_gold:
            errors.append(
                f"[S4] {DAILY_GOLD_LATEST_PAGE}: found only {chart_count} data <svg> chart(s) "
                f"(required >= {min_gold}; edition={gold_ed})"
            )

    # All 3 equity daily latest pages: post-cutover main >= 2, holiday_watch >= 1; legacy archives compatible.
    markets_map = market_state.get("markets") if isinstance(market_state, dict) else None
    for market_key, rel_path in DAILY_EQUITY_LATEST_PAGES:
        doc = parsed_htmls.get(rel_path)
        if doc is None:
            continue
        latest_rel = (
            markets_map.get(market_key, {}).get("latest_daily")
            if isinstance(markets_map, dict) and isinstance(markets_map.get(market_key), dict)
            else None
        )
        eq_key = _edition_key_from_text(latest_rel) or _edition_key_from_text(
            str((market_state or {}).get("edition_id") or "")
        )
        ed_type = _daily_edition_type(market_key, doc, market_state)
        min_req = _min_daily_charts(ed_type, eq_key, is_gold=False)
        chart_count = sum(1 for s in doc.svgs if s.is_data_chart)
        if chart_count < min_req:
            errors.append(
                f"[S4] {rel_path}: {ed_type} edition has only {chart_count} data <svg> chart(s) "
                f"(required >= {min_req}; edition={doc.edition_attr or ed_type})"
            )

    # Dated daily copies: enforce post-cutover floors (>= 2 main / >= 1 holiday_watch) while preserving legacy archives.
    for rel_path, doc in sorted(parsed_htmls.items()):
        m_dated = DAILY_DATED_RE.fullmatch(rel_path)
        if not m_dated:
            continue
        mkt_slug, date_s, hhmm_s, rev_s = m_dated.groups()
        dated_key = (date_s, int(hhmm_s), int(rev_s or 1))
        is_gold = mkt_slug == "gold"
        ed_type = doc.edition_attr or "main"
        min_req = _min_daily_charts(ed_type, dated_key, is_gold=is_gold)
        chart_count = sum(1 for s in doc.svgs if s.is_data_chart)
        if chart_count < min_req:
            errors.append(
                f"[S4] {rel_path}: {ed_type} edition has only {chart_count} data <svg> chart(s) "
                f"(required >= {min_req})"
            )

    # SVG <text> out-of-bounds & pairwise overlap check (non-legacy pages: 4 flagships + 4 latest + >= ALL_MAIN_CUTOVER dailies).
    if check_svg_text_geometry is not None:
        latest_pages = {DAILY_GOLD_LATEST_PAGE} | {p for _, p in DAILY_EQUITY_LATEST_PAGES}
        for rel_path, doc in sorted(parsed_htmls.items()):
            check_geom = rel_path in FLAGSHIP_MIN_CHARTS or rel_path in latest_pages
            if not check_geom:
                m_dated = DAILY_DATED_RE.fullmatch(rel_path)
                if m_dated:
                    _, date_s, hhmm_s, rev_s = m_dated.groups()
                    if (date_s, int(hhmm_s), int(rev_s or 1)) >= ALL_MAIN_CUTOVER:
                        check_geom = True
            if not check_geom:
                continue
            for issue in check_svg_text_geometry(doc.raw_text, label=rel_path):
                errors.append(f"[S4] {issue}")


def run_gate_s5(
    site_dir: Path,
    all_files: list[Path],
    parsed_htmls: dict[str, ParsedHtml],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Gate S5: Desktop + mobile responsive meta hygiene, <title>, <nav>, scrollable tables & CSS class coverage."""
    # Dynamically discover CSS classes declaring overflow-x/overflow: auto|scroll and ALL declared CSS classes.
    global_scroll_classes: set[str] = set()
    global_declared_classes: set[str] = set()
    for p in all_files:
        if p.suffix.lower() == ".css":
            try:
                css_txt = p.read_text(encoding="utf-8")
                global_scroll_classes.update(_extract_scrollable_classes_from_css(css_txt))
                global_declared_classes.update(_extract_all_declared_css_classes(css_txt))
            except (OSError, UnicodeDecodeError):
                pass

    for rel_path, doc in sorted(parsed_htmls.items()):
        if not doc.has_utf8_charset:
            errors.append(f"[S5] {rel_path}: missing <meta charset=\"utf-8\">")

        if not doc.has_viewport_meta:
            errors.append(f"[S5] {rel_path}: missing <meta name=\"viewport\">")
        else:
            if not doc.viewport_has_device_width:
                errors.append(
                    f"[S5] {rel_path}: viewport meta missing width=device-width"
                )
            if not doc.viewport_has_cover:
                errors.append(
                    f"[S5] {rel_path}: viewport meta missing viewport-fit=cover"
                )

        if not doc.has_title or not doc.title_text.strip():
            errors.append(f"[S5] {rel_path}: missing or empty <title> element")

        if not doc.has_nav:
            errors.append(f"[S5] {rel_path}: missing <nav> navigation element")

        local_scroll_classes = set(global_scroll_classes)
        local_declared_classes = set(global_declared_classes)
        for style_block in doc.inline_styles:
            local_scroll_classes.update(_extract_scrollable_classes_from_css(style_block))
            local_declared_classes.update(_extract_all_declared_css_classes(style_block))

        unwrapped_lines: list[int] = []
        for tbl in doc.tables:
            if not tbl.in_article_or_main:
                continue
            is_wrapped = (
                tbl.has_inline_scroll_ancestor
                or bool(tbl.ancestor_classes & local_scroll_classes)
                or any(SCROLL_WRAP_CLASS_RE.search(c) for c in tbl.ancestor_classes)
            )
            if not is_wrapped:
                unwrapped_lines.append(tbl.lineno)

        if unwrapped_lines:
            sample = ", ".join(f"L{ln}" for ln in unwrapped_lines[:5])
            extra = f" (+{len(unwrapped_lines) - 5} more)" if len(unwrapped_lines) > 5 else ""
            errors.append(
                f"[S5] {rel_path}: {len(unwrapped_lines)} unwrapped <table> element(s) inside "
                f"<article>/<main> without scrollable wrapper ({sample}{extra})"
            )

        # Audit all HTML classes against declared CSS rules (+ explicit JS hook allowlist).
        undeclared = sorted(doc.used_classes - local_declared_classes - JS_HOOK_CLASS_ALLOWLIST)
        if undeclared:
            sample_cls = ", ".join(f".{c}" for c in undeclared[:8])
            extra_cls = f" (+{len(undeclared) - 8} more)" if len(undeclared) > 8 else ""
            errors.append(
                f"[S5] {rel_path}: undeclared CSS class(es) not found in stylesheets: {sample_cls}{extra_cls}"
            )


def _load_json_if_present(
    path: Path, label: str, errors: list[str]
) -> dict | None:
    if not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            errors.append(f"[S6] {label} root must be a JSON object: {path.name}")
            return None
        return obj
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"[S6] Failed to parse {label} ({path.name}): {exc}")
        return None


def _load_required_json(
    path: Path, label: str, errors: list[str]
) -> dict | None:
    if not path.is_file():
        errors.append(f"[S6] Missing required SSOT file: {label}")
        return None
    return _load_json_if_present(path, label, errors)


def _is_gold_new_buy_blocked(gold_snap: dict | None, market_state: dict | None) -> bool:
    """Resolve authoritative Gold Tier 0 lock status from gold/data_snapshot.json (fallback to mirror if absent)."""
    if isinstance(gold_snap, dict) and ("new_buy_allowed" in gold_snap or "tier_code" in gold_snap):
        return (
            gold_snap.get("new_buy_allowed") is False
            or str(gold_snap.get("tier_code", "")).strip() == "Tier 0"
        )
    if isinstance(market_state, dict) and isinstance(market_state.get("markets"), dict):
        gold_mirror = market_state["markets"].get("gold_mirror_readonly")
        if isinstance(gold_mirror, dict) and (
            gold_mirror.get("new_buy_allowed") is False
            or str(gold_mirror.get("tier_code", "")).strip() == "Tier 0"
        ):
            return True
    return False


def _check_gold_tier0_mutex(doc: ParsedHtml, errors: list[str]) -> None:
    """Scan current public output, including text in embedded charts."""
    vis = doc.visible_text
    page = doc.rel_path

    # 1. Confirm Tier 0 / red-light lock status is visibly communicated on index.html.
    if page == "index.html" and not GOLD_TIER0_LOCK_INDICATORS_RE.search(vis):
        errors.append(
            "[S6] index.html: Gold new_buy_allowed is False, but no Tier 0 / 红灯停 / 暂不新买 "
            "lock indicator found in visible text"
        )

    # 2. Check all buttons / links for unguarded active buy-gold CTAs.
    for cta in doc.ctas:
        if any(not _gold_action_is_guarded(cta.text, match) for match in GOLD_CTA_BUY_RE.finditer(cta.text)):
            errors.append(
                f"[S6] {page}:{cta.lineno}: Gold Tier 0 mutex violation — active buy-gold "
                f"CTA <{cta.tag}>: {cta.text!r}"
            )

    # 3. Scan visible prose line-by-line for unguarded buy-gold directives (cap at 5 per page).
    prose_hits = 0
    for raw_line in re.split(r"[\n。！？；，,]+", vis):
        line = " ".join(raw_line.split())
        if not line:
            continue
        for m in GOLD_ACTIVE_BUY_RE.finditer(line):
            win = line[max(0, m.start() - 45) : min(len(line), m.end() + 45)]
            if not _gold_action_is_guarded(line, m):
                errors.append(
                    f"[S6] {page}: Gold Tier 0 mutex violation — unguarded buy-gold directive "
                    f"in visible text: {win!r}"
                )
                prose_hits += 1
                if prose_hits >= 5:
                    return


def _gold_action_is_guarded(text: str, action: re.Match) -> bool:
    """A nearby mention of the red light or past holdings cannot excuse an action."""
    before = re.split(r"[。！？；，,\n]", text[:action.start()])[-1]
    scoped = before[-28:] + action.group()
    return bool(GOLD_DEFER_GUARD_RE.search(scoped))


def _validate_screener_json(
    screener_doc: ParsedHtml,
    expected_by_market: dict[str, int],
    errors: list[str],
    *,
    gold_new_buy_blocked: bool,
) -> None:
    """Parse and validate <script id='screener-data' type='application/json'> payload in screener.html."""
    if screener_doc.screener_json_raw is None:
        errors.append(
            "[S6] screener.html: missing <script id=\"screener-data\" type=\"application/json\"> payload"
        )
        return

    try:
        payload = json.loads(screener_doc.screener_json_raw)
    except json.JSONDecodeError as exc:
        errors.append(f"[S6] screener.html: invalid JSON in #screener-data: {exc}")
        return

    if not isinstance(payload, list):
        errors.append("[S6] screener.html: #screener-data JSON root must be a list")
        return

    expected_total = sum(expected_by_market.values())
    if len(payload) < 100:
        errors.append(
            f"[S6] screener.html: #screener-data length ({len(payload)}) < 100 minimum stock pool floor"
        )
    if len(payload) != expected_total:
        errors.append(
            f"[S6] screener.html: #screener-data length ({len(payload)}) != expected total ({expected_total})"
        )

    actual_by_market: dict[str, int] = {"a-share": 0, "hk-stock": 0, "us-stock": 0}
    benchmarks: dict[str, str] = {}
    for mk in actual_by_market:
        meta_path = REPO_ROOT / "equity" / f"report_meta_{mk.replace('-', '_')}.json"
        meta = _load_json_if_present(meta_path, "screener flagship metadata", errors)
        baseline = str((meta or {}).get("benchmark_time") or "").split("（", 1)[0]
        if not baseline or baseline not in screener_doc.visible_text:
            errors.append(f"[S6] screener.html: missing {mk} flagship quote time")
        benchmarks[mk] = baseline

    seen: set[tuple[str, str]] = set()
    bad_entries = 0
    for idx, entry in enumerate(payload):
        if not isinstance(entry, dict):
            errors.append(f"[S6] screener.html: #screener-data[{idx}] is not a JSON object")
            bad_entries += 1
            if bad_entries >= 10:
                break
            continue

        mk = str(entry.get("market", "")).strip()
        code = str(entry.get("code", "")).strip().upper()
        if mk in actual_by_market:
            actual_by_market[mk] += 1
            if entry.get("benchmark_time") != benchmarks[mk]:
                errors.append(f"[S6] screener.html: {mk}/{code} quote time differs from its flagship")
        identity = (mk, code)
        if identity in seen:
            errors.append(f"[S6] screener.html: duplicate stock {mk}/{code}")
        seen.add(identity)

        # Required fields non-empty
        for req_k in SCREENER_REQUIRED_FIELDS:
            val = entry.get(req_k)
            if not isinstance(val, str) or not val.strip():
                errors.append(
                    f"[S6] screener.html: #screener-data[{idx}] ({entry.get('code', '?')}) "
                    f"missing or empty required field '{req_k}'"
                )
                bad_entries += 1
                break
        else:
            action_val = entry.get("action_label") or entry.get("action")
            if not isinstance(action_val, str) or not action_val.strip():
                errors.append(
                    f"[S6] screener.html: #screener-data[{idx}] ({entry.get('code', '?')}) "
                    f"missing or empty 'action_label'/'action'"
                )
                bad_entries += 1

        col_val = str(entry.get("color", "")).strip()
        if gold_new_buy_blocked and col_val == "g" and GOLD_STOCK_RE.search(f"{entry.get('name', '')} {code}"):
            errors.append(f"[S6] screener.html: Gold Tier 0 stock marked as green base: {mk}/{code}")
        if col_val not in SCREENER_VALID_COLORS:
            errors.append(
                f"[S6] screener.html: #screener-data[{idx}] ({entry.get('code', '?')}) "
                f"invalid color {col_val!r} (expected one of {sorted(SCREENER_VALID_COLORS)})"
            )
            bad_entries += 1

        # Zero raw <br>, **, or ` in any string field (including nested 7-dim dossier)
        for k, v in entry.items():
            if isinstance(v, str) and SCREENER_RAW_MARKUP_RE.search(v):
                errors.append(
                    f"[S6] screener.html: #screener-data[{idx}] ({entry.get('code', '?')}) "
                    f"field '{k}' contains raw markup (<br> / ** / `): {v[:80]!r}"
                )
                bad_entries += 1
                break
        dossier = entry.get("dossier")
        if not isinstance(dossier, dict):
            errors.append(
                f"[S6] screener.html: #screener-data[{idx}] ({entry.get('code', '?')}) missing required 7-dim 'dossier' object"
            )
            bad_entries += 1
        else:
            for dk in DOSSIER_DIMENSIONS:
                dv = dossier.get(dk)
                if not isinstance(dv, str) or not dv.strip():
                    errors.append(
                        f"[S6] screener.html: #screener-data[{idx}] ({entry.get('code', '?')}) missing dossier.{dk}"
                    )
                    bad_entries += 1
                    break
                if SCREENER_RAW_MARKUP_RE.search(dv):
                    errors.append(
                        f"[S6] screener.html: #screener-data[{idx}] ({entry.get('code', '?')}) dossier.{dk} contains raw markup"
                    )
                    bad_entries += 1
                    break

        if bad_entries >= 10:
            break

    for mk, exp_cnt in expected_by_market.items():
        act_cnt = actual_by_market.get(mk, 0)
        if act_cnt != exp_cnt:
            errors.append(
                f"[S6] screener.html: #screener-data market '{mk}' count ({act_cnt}) "
                f"!= market_state.json stock_pool_count ({exp_cnt})"
            )


def _check_household_weights(hcw: dict, visible_text: str, errors: list[str]) -> None:
    keys = ("equity_total_pct", "convertible_bond_pct", "bonds_and_cash_pct", "gold_existing_hold_pct")
    message = "[S6] market_state.json: household_composite_weights"
    if any(type(hcw.get(k)) is not int or not 0 <= hcw[k] <= 100 for k in keys):
        errors.append(f"{message} must have four nonnegative integer percentages")
        return
    actual = [hcw[k] for k in keys]
    if sum(actual) != 100 or hcw.get("sum_pct", 100) != 100:
        errors.append(f"{message} must sum to 100, got {sum(actual)}")
    elif "100%" not in visible_text:
        errors.append("[S6] index.html: missing household composite total '100%'")

    accounts = hcw.get("accounts")
    if accounts is None:  # Historic state before the structured recipe was introduced.
        return
    if not isinstance(accounts, dict) or not accounts:
        errors.append(f"{message} accounts must be a nonempty object")
        return
    weighted = [Decimal(0)] * len(keys)
    weight_sum = Decimal(0)
    for name, account in accounts.items():
        if not isinstance(account, dict) or any(
            type(account.get(k)) not in (int, float) or not 0 <= account[k] <= 100
            for k in ("weight_pct", *keys)
        ):
            errors.append(f"{message} invalid account recipe: {name}")
            return
        values = [Decimal(str(account[k])) for k in keys]
        if sum(values) != 100:
            errors.append(f"{message} account {name} must sum to 100")
            return
        share = Decimal(str(account["weight_pct"]))
        weight_sum += share
        for idx, value in enumerate(values):
            weighted[idx] += share * value / 100
    if weight_sum != 100:
        errors.append(f"{message} account weights must sum to 100")
        return
    expected = [int(value) for value in weighted]
    order = sorted(range(len(keys)), key=lambda idx: weighted[idx] - expected[idx], reverse=True)
    for idx in order[:100 - sum(expected)]:
        expected[idx] += 1
    if actual != expected:
        errors.append(f"{message} {actual} disagrees with the account recipe {expected}")


def run_gate_s6(
    parsed_htmls: dict[str, ParsedHtml],
    gold_snap: dict | None,
    market_state: dict | None,
    errors: list[str],
    warnings: list[str],
    *,
    already_checked_json_gold: bool = False,
) -> None:
    """Gate S6: Live SSOT fidelity on index.html, screener.html JSON schema, channels/ETFs, and Gold Tier 0 mutex."""
    index_doc = parsed_htmls.get("index.html")
    channels_doc = parsed_htmls.get("channels.html")
    screener_doc = parsed_htmls.get("screener.html")

    # Never silently skip when required core SSOT JSONs are absent.
    if gold_snap is None and not any("gold/data_snapshot.json" in e for e in errors):
        errors.append("[S6] Missing required SSOT data: gold/data_snapshot.json")
    if market_state is None and not any("equity/state/market_state.json" in e for e in errors):
        errors.append("[S6] Missing required SSOT data: equity/state/market_state.json")

    # 1. Live Gold SSOT metrics & authoritative Tier 0 mutex from gold/data_snapshot.json.
    gold_new_buy_blocked = _is_gold_new_buy_blocked(gold_snap, market_state)
    if gold_snap is not None:
        if index_doc is not None:
            spot_val = gold_snap.get("spot_gold_ny_close_usd")
            spot_rounded = gold_snap.get("spot_gold_ny_close_rounded")
            if spot_val is not None:
                extras = [spot_rounded] if spot_rounded is not None else []
                variants = _numeric_variants(float(spot_val), extras)
                if not _contains_any_number(index_doc.visible_text, variants):
                    errors.append(
                        f"[S6] index.html: missing live Gold spot_gold_ny_close_usd={spot_val} "
                        f"(expected one of {variants[:6]})"
                    )

            dfii_val = gold_snap.get("dfii10_live_pct")
            if dfii_val is not None:
                dfii_vars = _numeric_variants(float(dfii_val))
                if not _contains_any_number(index_doc.visible_text, dfii_vars):
                    errors.append(
                        f"[S6] index.html: missing live Gold dfii10_live_pct={dfii_val}"
                    )

            autd_night = gold_snap.get("sge_autd_night_rmb")
            autd_day = gold_snap.get("sge_autd_day_rmb")
            autd_vals = [float(v) for v in (autd_night, autd_day) if isinstance(v, (int, float)) and v > 0]
            if autd_vals:
                autd_vars = _numeric_variants(autd_vals[0], autd_vals[1:])
                if not _contains_any_number(index_doc.visible_text, autd_vars):
                    errors.append(
                        f"[S6] index.html: missing live SGE Au(T+D) reading ({autd_vals})"
                    )

    # 2. Live A / HK / US benchmark indices, cockpit risk radar SSOT & screener JSON fidelity.
    if market_state is not None:
        markets = market_state.get("markets")
        linkages = market_state.get("cross_market_linkages", {})
        if not isinstance(markets, dict):
            errors.append("[S6] equity/state/market_state.json: missing or invalid 'markets' object")
        else:
            if index_doc is not None:
                # A-Share benchmark (CSI 300 primary).
                a_mkt = markets.get("a_share", {})
                if isinstance(a_mkt, dict):
                    a_val = a_mkt.get("benchmark_csi300")
                    if a_val is not None:
                        a_vars = _numeric_variants(float(a_val))
                        if not _contains_any_number(index_doc.visible_text, a_vars):
                            errors.append(
                                f"[S6] index.html: missing live A-Share benchmark_csi300={a_val} "
                                f"(expected one of {a_vars[:6]})"
                            )

                # HK-Stock benchmark (HSI; allow midday HSI if present in live state).
                hk_mkt = markets.get("hk_stock", {})
                if isinstance(hk_mkt, dict):
                    hk_val = hk_mkt.get("benchmark_hsi")
                    hk_extras = [
                        v
                        for k, v in hk_mkt.items()
                        if k.startswith("midday_") and k.endswith("_hsi") and isinstance(v, (int, float))
                    ]
                    if hk_val is not None:
                        hk_vars = _numeric_variants(float(hk_val), hk_extras)
                        if not _contains_any_number(index_doc.visible_text, hk_vars):
                            errors.append(
                                f"[S6] index.html: missing live HK-Stock benchmark_hsi={hk_val} "
                                f"(expected one of {hk_vars[:6]})"
                            )

                # US-Stock benchmark (S&P 500).
                us_mkt = markets.get("us_stock", {})
                if isinstance(us_mkt, dict):
                    us_val = us_mkt.get("benchmark_sp500")
                    if us_val is not None:
                        us_vars = _numeric_variants(float(us_val))
                        if not _contains_any_number(index_doc.visible_text, us_vars):
                            errors.append(
                                f"[S6] index.html: missing live US-Stock benchmark_sp500={us_val} "
                                f"(expected one of {us_vars[:6]})"
                            )

                # Cross-market cockpit SSOT: us10y, vix, hkma_agg_bal, household_composite_weights == 100.
                if isinstance(linkages, dict):
                    rates = linkages.get("rates_fx_chain", {})
                    brake = linkages.get("crisis_correlation_brake", {})
                    hcw = linkages.get("household_composite_weights", {})

                    if isinstance(rates, dict):
                        us10y_val = rates.get("us10y_pct")
                        if isinstance(us10y_val, (int, float)):
                            u10_vars = _numeric_variants(float(us10y_val)) + [f"{float(us10y_val):.3f}"]
                            if not _contains_any_number(index_doc.visible_text, u10_vars):
                                errors.append(
                                    f"[S6] index.html: missing live us10y_pct={us10y_val}"
                                )
                        hkma_val = rates.get("hkma_agg_bal_hkd_100m")
                        if isinstance(hkma_val, (int, float)):
                            hkma_vars = _numeric_variants(float(hkma_val))
                            if not _contains_any_number(index_doc.visible_text, hkma_vars):
                                errors.append(
                                    f"[S6] index.html: missing live hkma_agg_bal_hkd_100m={hkma_val}"
                                )

                    if isinstance(brake, dict):
                        vix_val = brake.get("vix_close")
                        if isinstance(vix_val, (int, float)):
                            vix_vars = _numeric_variants(float(vix_val))
                            if not _contains_any_number(index_doc.visible_text, vix_vars):
                                errors.append(
                                    f"[S6] index.html: missing live vix_close={vix_val}"
                                )

                    if isinstance(hcw, dict) and hcw:
                        _check_household_weights(hcw, index_doc.visible_text, errors)

            # Screener total stock pool & embedded JSON fidelity across A / HK / US.
            expected_by_market: dict[str, int] = {}
            for mkey, slug in (("a_share", "a-share"), ("hk_stock", "hk-stock"), ("us_stock", "us-stock")):
                mobj = markets.get(mkey)
                if isinstance(mobj, dict) and isinstance(mobj.get("stock_pool_count"), (int, float)):
                    expected_by_market[slug] = int(mobj["stock_pool_count"])

            if len(expected_by_market) == 3 and screener_doc is not None:
                expected_total = sum(expected_by_market.values())
                if expected_total < 100:
                    errors.append(
                        f"[S6] market_state.json: total stock_pool_count ({expected_total}) < 100 minimum floor"
                    )
                tot_pat = re.compile(rf"(?<![0-9]){expected_total}(?![0-9])")
                if not tot_pat.search(screener_doc.visible_text):
                    errors.append(
                        f"[S6] screener.html: missing expected total stock pool count "
                        f"{expected_total} in visible text"
                    )
                if screener_doc.stock_row_count != expected_total:
                    errors.append(
                        f"[S6] screener.html: static stock row count ({screener_doc.stock_row_count}) "
                        f"!= expected total ({expected_total})"
                    )
                _validate_screener_json(
                    screener_doc, expected_by_market, errors, gold_new_buy_blocked=gold_new_buy_blocked,
                )
            elif screener_doc is not None and screener_doc.stock_row_count < 100:
                errors.append(
                    f"[S6] screener.html: static stock row count ({screener_doc.stock_row_count}) < 100 minimum floor"
                )

    # 3. ETF universe SSOT fidelity: tbody static rows == #etf-data == etf_universe.json len(etfs) >= 140.
    etf_universe_obj = _load_required_json(
        ETF_UNIVERSE_PATH, "equity/state/etf_universe.json", errors
    )
    ssot_etf_count: int | None = None
    if isinstance(etf_universe_obj, dict):
        ssot_etfs = etf_universe_obj.get("etfs")
        if not isinstance(ssot_etfs, list) or len(ssot_etfs) < 140:
            errors.append(
                f"[S6] equity/state/etf_universe.json: 'etfs' must be a list with >= 140 entries "
                f"(got {len(ssot_etfs) if isinstance(ssot_etfs, list) else type(ssot_etfs).__name__})"
            )
        else:
            ssot_etf_count = len(ssot_etfs)

    etfs_doc = parsed_htmls.get("etfs.html")
    if etfs_doc is not None:
        if etfs_doc.etf_json_raw is None:
            errors.append('[S6] etfs.html: missing <script id="etf-data" type="application/json"> payload')
        else:
            try:
                etf_payload = json.loads(etfs_doc.etf_json_raw)
            except json.JSONDecodeError as exc:
                errors.append(f"[S6] etfs.html: invalid JSON in #etf-data: {exc}")
                etf_payload = None
            if not isinstance(etf_payload, list) or len(etf_payload) < 140:
                errors.append(
                    f"[S6] etfs.html: #etf-data must contain >= 140 ETFs "
                    f"(got {len(etf_payload) if isinstance(etf_payload, list) else 'non-list'})"
                )
            else:
                etf_tbody_rows = (
                    etfs_doc.etf_tbody_row_count
                    if "etf-tbody" in etfs_doc.ids
                    else etfs_doc.tbody_row_count
                )
                if etf_tbody_rows != len(etf_payload):
                    errors.append(
                        f"[S6] etfs.html: static <tbody> row count ({etf_tbody_rows}) "
                        f"!= #etf-data length ({len(etf_payload)})"
                    )
                if ssot_etf_count is not None and len(etf_payload) != ssot_etf_count:
                    errors.append(
                        f"[S6] etfs.html: #etf-data length ({len(etf_payload)}) "
                        f"!= etf_universe.json len(etfs) ({ssot_etf_count})"
                    )
                seen_etfs: set[str] = set()
                for idx, it in enumerate(etf_payload):
                    if not isinstance(it, dict):
                        errors.append(f"[S6] etfs.html: #etf-data[{idx}] must be an object")
                        break
                    cd = str(it.get("code", "")).strip()
                    if not cd or cd in seen_etfs:
                        errors.append(f"[S6] etfs.html: missing or duplicate ETF code {cd!r}")
                    seen_etfs.add(cd)
                    cd_upper = cd.upper()
                    cd_base = cd_upper.split(".", 1)[0]
                    is_gold_etf = (
                        bool(it.get("gold_locked"))
                        or cd_upper in GOLD_ETF_CODES
                        or cd_base in GOLD_ETF_CODES
                        or bool(GOLD_STOCK_RE.search(f"{it.get('name', '')} {cd_upper}"))
                    )
                    if gold_new_buy_blocked and is_gold_etf:
                        role = str(it.get("action_role", ""))
                        if not it.get("gold_locked") or any(bad in role for bad in GOLD_ETF_FORBIDDEN_ROLES):
                            errors.append(f"[S6] etfs.html: Gold Tier 0 mutex violation on ETF {cd} (role={role!r})")
                    for k, v in it.items():
                        if isinstance(v, str) and SCREENER_RAW_MARKUP_RE.search(v):
                            errors.append(f"[S6] etfs.html: ETF {cd} field '{k}' contains raw markup")
                            break

    # 4. Personal multi-asset channels SSOT (>= 12 standard MECE channels): verify index.html, channels.html, AND each channels/<id>.html.
    channels_obj = _load_required_json(
        MULTI_ASSET_CHANNELS_PATH, "equity/state/multi_asset_channels.json", errors
    )
    if isinstance(channels_obj, dict):
        ch_items = channels_obj.get("channels")
        if not isinstance(ch_items, list) or len(ch_items) < len(REQUIRED_MULTI_ASSET_CHANNELS):
            errors.append(
                f"[S6] equity/state/multi_asset_channels.json: 'channels' must be a list with >= {len(REQUIRED_MULTI_ASSET_CHANNELS)} items "
                f"(got {len(ch_items) if isinstance(ch_items, list) else type(ch_items).__name__})"
            )
        else:
            index_hrefs = {lk.value for lk in index_doc.links if lk.tag == "a"} if index_doc is not None else set()
            channels_hrefs = {lk.value for lk in channels_doc.links if lk.tag == "a"} if channels_doc is not None else set()
            seen_ch_ids: set[str] = set()
            for idx, ch in enumerate(ch_items):
                if not isinstance(ch, dict):
                    errors.append(f"[S6] multi_asset_channels.json: channels[{idx}] must be an object")
                    continue
                ch_id = str(ch.get("id", "")).strip()
                ch_name = str(ch.get("name", "")).strip()
                if not ch_id or not ch_name:
                    errors.append(f"[S6] multi_asset_channels.json: channels[{idx}] missing non-empty id/name")
                    continue
                if ch_id in seen_ch_ids:
                    errors.append(f"[S6] multi_asset_channels.json: duplicate channel id {ch_id!r}")
                seen_ch_ids.add(ch_id)

                prods = [p for p in (ch.get("products") or []) if isinstance(p, dict)]
                rules = [r.strip() for r in (ch.get("rules_and_redlines") or []) if isinstance(r, str) and r.strip()]
                if not prods:
                    errors.append(f"[S6] multi_asset_channels.json: channel {ch_id!r} missing non-empty products")
                if not rules:
                    errors.append(f"[S6] multi_asset_channels.json: channel {ch_id!r} missing non-empty rules_and_redlines")

                detail_rel = f"channels/{ch_id}.html"
                if index_doc is not None:
                    if f"ch-{ch_id}" not in index_doc.ids:
                        errors.append(
                            f"[S6] index.html: missing channel overview card #ch-{ch_id} ({ch_name})"
                        )
                    if detail_rel not in index_hrefs:
                        errors.append(
                            f"[S6] index.html: missing link to separate channel detail page {detail_rel}"
                        )
                    if ch_name not in index_doc.visible_text:
                        errors.append(
                            f"[S6] index.html: missing channel title {ch_name!r} in homepage visible text"
                        )

                if channels_doc is not None:
                    if f"ch-{ch_id}" not in channels_doc.ids:
                        errors.append(
                            f"[S6] channels.html: missing channel overview card #ch-{ch_id} ({ch_name})"
                        )
                    if detail_rel not in channels_hrefs:
                        errors.append(
                            f"[S6] channels.html: missing link to channel detail page {detail_rel}"
                        )
                    if ch_name not in channels_doc.visible_text:
                        errors.append(
                            f"[S6] channels.html: missing channel title {ch_name!r} in visible text"
                        )

                detail_doc = parsed_htmls.get(detail_rel)
                if detail_doc is None:
                    errors.append(
                        f"[S6] Missing dedicated channel detail page: {detail_rel}"
                    )
                else:
                    detail_norm = " ".join(detail_doc.visible_text.split())
                    if ch_name not in detail_doc.visible_text and " ".join(ch_name.split()) not in detail_norm:
                        errors.append(
                            f"[S6] {detail_rel}: missing channel name {ch_name!r} in visible text"
                        )
                    if prods:
                        has_prod = any(
                            (" ".join(str(p.get("name", "")).split()) and " ".join(str(p.get("name", "")).split()) in detail_norm)
                            or (" ".join(str(p.get("code", "")).split()) and " ".join(str(p.get("code", "")).split()) in detail_norm)
                            for p in prods
                        )
                        if not has_prod or not detail_doc.tables:
                            errors.append(
                                f"[S6] {detail_rel}: missing substantial product table/entries for channel {ch_id!r}"
                            )
                    if rules:
                        has_rule = any(
                            " ".join(r.split())[:12] in detail_norm for r in rules if " ".join(r.split())
                        )
                        if not has_rule:
                            errors.append(
                                f"[S6] {detail_rel}: missing substantial rules/redlines content for channel {ch_id!r}"
                            )
            missing_ch_ids = [cid for cid in REQUIRED_MULTI_ASSET_CHANNELS if cid not in seen_ch_ids]
            if missing_ch_ids:
                errors.append(
                    f"[S6] equity/state/multi_asset_channels.json: missing required standard channel IDs: {missing_ch_ids}"
                )

    # 5. A dated archive preserves its original decisions. Check live pages (incl. guide.html) and this edition's dated copies.
    if gold_new_buy_blocked:
        edition_slug = str((gold_snap or {}).get("edition_id", "")).replace("_", "-")
        live_root_pages = {"index.html", "channels.html", "etfs.html", "screener.html", "scorecard.html", "guide.html"}
        for path, doc in parsed_htmls.items():
            if (path in live_root_pages
                    or path.startswith(("reports/", "channels/")) or path.endswith("-latest.html")
                    or (edition_slug and path.startswith("daily/") and path.endswith(f"-{edition_slug}.html"))):
                _check_gold_tier0_mutex(doc, errors)
                if not already_checked_json_gold:
                    if doc.screener_json_raw is not None:
                        _scan_embedded_json_payload(
                            path, "screener-data", doc.screener_json_raw, errors,
                            check_eng=False, check_gold_tier0=True, gate_tag="S6",
                        )
                    if doc.etf_json_raw is not None:
                        _scan_embedded_json_payload(
                            path, "etf-data", doc.etf_json_raw, errors,
                            check_eng=False, check_gold_tier0=True, gate_tag="S6",
                        )
                    if doc.ch_etf_json_raw is not None:
                        _scan_embedded_json_payload(
                            path, "ch-etf-data", doc.ch_etf_json_raw, errors,
                            check_eng=False, check_gold_tier0=True, gate_tag="S6",
                        )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def _usage() -> str:
    return "Usage: python3 scripts/lint_site.py [site_dir] [--strict]"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "-h" in args or "--help" in args:
        print(_usage())
        return 0

    strict = False
    positional: list[str] = []
    for arg in args:
        if arg == "--strict":
            strict = True
        elif arg.startswith("-"):
            print(f"Unknown option: {arg}", file=sys.stderr)
            print(_usage(), file=sys.stderr)
            return 2
        else:
            positional.append(arg)

    if len(positional) > 1:
        print(f"Expected at most 1 site_dir argument, got {len(positional)}.", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2

    site_dir = Path(positional[0]).resolve() if positional else DEFAULT_SITE_DIR.resolve()

    errors: list[str] = []
    warnings: list[str] = []

    # Pre-load required SSOT JSONs (missing or corrupt files fail Gate S6 cleanly).
    gold_snap = _load_required_json(GOLD_SNAPSHOT_PATH, "gold/data_snapshot.json", errors)
    market_state = _load_required_json(MARKET_STATE_PATH, "equity/state/market_state.json", errors)
    gold_new_buy_blocked = _is_gold_new_buy_blocked(gold_snap, market_state)

    # Gate S1: Completeness & non-empty output (also parses all HTML files once).
    parsed_htmls, all_files = run_gate_s1(site_dir, errors, warnings)

    if site_dir.is_dir():
        # Gate S2: Internal links, assets & anchors.
        run_gate_s2(site_dir, parsed_htmls, errors, warnings)

        # Gate S3: Zero PII, local paths, secrets, unresolved directives & JSON payload leaks.
        run_gate_s3(
            site_dir, all_files, parsed_htmls, errors, warnings,
            gold_new_buy_blocked=gold_new_buy_blocked,
        )

        # Gate S4: Vector SVG chart integrity.
        run_gate_s4(parsed_htmls, market_state, errors, warnings, gold_snap=gold_snap)

        # Gate S5: Desktop + mobile responsive hygiene.
        run_gate_s5(site_dir, all_files, parsed_htmls, errors, warnings)

        # Gate S6: Live SSOT & full-market stock screener fidelity (全市场龙头股筛选) + Gold Tier 0 mutex.
        run_gate_s6(
            parsed_htmls, gold_snap, market_state, errors, warnings,
            already_checked_json_gold=True,
        )

    mode = "STRICT" if strict else "STANDARD"
    print(
        f"=== lint_site.py [{mode}] checked {len(parsed_htmls)} HTML / "
        f"{len(all_files)} total file(s) in {site_dir.name} ==="
    )
    if not errors and not warnings:
        print("  PASS: All 6 forensic site gates (S1-S6) passed cleanly.")
    else:
        for e in errors:
            print(f"  [FAIL] {e}")
        for w in warnings:
            print(f"  [WARN] {w}")
    print(f"Summary: {len(errors)} error(s), {len(warnings)} warning(s).")

    if errors or (strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
