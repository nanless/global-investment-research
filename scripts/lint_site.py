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
  - Gate S6: Live SSOT & 135-Stock Screener Fidelity

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
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
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
    "screener.html",
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
EXTERNAL_SCHEMES = (
    "http://",
    "https://",
    "//",
    "mailto:",
    "tel:",
    "javascript:",
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
        re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9]{20,}"),
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
)

# Unrendered Markdown table alignment / separator rows appearing in visible HTML text.
S3_RAW_MD_SEP_RE = re.compile(
    r"\|\s*(?::-{2,}:?|-{2,}:)\s*\||\|\s*-{3,}\s*\|\s*-{3,}\s*\|"
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

DAILY_REQUIRED_CHART_PAGES: tuple[str, ...] = (
    "daily/gold-latest.html",
    "daily/hk-stock-latest.html",
    "daily/us-stock-latest.html",
)
DAILY_OPTIONAL_LIGHT_PAGE = "daily/a-share-latest.html"

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
GOLD_ACTIVE_BUY_RE = re.compile(
    r"(?:趁急跌.{0,12}(?:补齐|买|低吸).{0,8}黄金|"
    r"(?:小批|分批|立刻|马上|立即|同步|今[日早晚]).{0,8}(?:补齐|补足|买入|买进|加仓|加配|建仓|抄底).{0,8}(?:[0-9一二两三半成%]*\s*)?(?:黄金|金仓|黄金ETF)|"
    r"(?:补齐|补足|加配|逢低买|抄底)\s*[0-9一二两三半成%]*\s*(?:黄金|金仓)|"
    r"(?:立即|马上|现在|建议|可以|开启|启动).{0,6}(?:买入|买进|建仓|加仓|配置|抄底).{0,6}(?:黄金|金仓|黄金ETF)|"
    r"\b(?:buy\s+gold|add\s+gold|accumulate\s+gold|buy\s+now[^\n]{0,20}gold)\b)",
    re.IGNORECASE,
)
GOLD_CTA_BUY_RE = re.compile(
    r"(?:(?:立即|马上|一键|去|开始)?(?:买入|买进|加仓|建仓|抄底|配置)\s*黄金|"
    r"(?:立即|马上|去)买金|"
    r"\b(?:buy\s+gold|accumulate\s+gold)\b)",
    re.IGNORECASE,
)
GOLD_DEFER_GUARD_RE = re.compile(
    r"(?:暂不|严禁|禁止|不新买|不动|不买|切忌|勿|停止|锁定|红灯停|新仓\s*0%|0%\s*新仓|"
    r"待.{0,12}(?:黄灯|绿灯|解锁)|等.{0,12}(?:黄灯|绿灯|解锁)|解锁后|12/18|存量底仓|预算暂泊|"
    r"原稿曾建议|门控校正|历史实证|no\s+new\s+buy|do\s+not\s+buy|hold\s+off|tier\s*0)",
    re.IGNORECASE,
)
GOLD_TIER0_LOCK_INDICATORS_RE = re.compile(
    r"(?:Tier\s*0|红灯停|暂不新买|新仓\s*0%|不新买|严禁新买|严禁抢跑|红灯防守)",
    re.IGNORECASE,
)
LIGHT_EDITION_HINTS_RE = re.compile(
    r"(?:早刊|盘前精简|盘前轻刊|轻刊|守望简报|休市简报|holiday_watch)",
    re.IGNORECASE,
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
    secondary_targets: set[str] = field(default_factory=set)
    links: list[LinkRef] = field(default_factory=list)
    svgs: list[SvgInfo] = field(default_factory=list)
    tables: list[TableInfo] = field(default_factory=list)
    ctas: list[CtaInfo] = field(default_factory=list)
    has_utf8_charset: bool = False
    has_viewport_meta: bool = False
    viewport_has_device_width: bool = False
    viewport_has_cover: bool = False
    has_title: bool = False
    title_text: str = ""
    has_nav: bool = False
    edition_attr: str = ""
    stock_row_count: int = 0
    inline_styles: list[str] = field(default_factory=list)
    visible_text: str = ""


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


class SiteHtmlParser(HTMLParser):
    """Single-pass stdlib HTMLParser collecting data for Gates S2, S3, S4, S5, S6."""

    def __init__(self, rel_path: str, abs_path: Path, raw_text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.doc = ParsedHtml(rel_path=rel_path, abs_path=abs_path, raw_text=raw_text)
        # Stack of (tag, classes_set, inline_style)
        self._stack: list[tuple[str, set[str], str]] = []
        self._svg_stack: list[SvgInfo] = []
        self._in_title = False
        self._title_chunks: list[str] = []
        self._in_style = False
        self._style_chunks: list[str] = []
        self._skip_text_depth = 0  # script / style / template
        self._vis_chunks: list[str] = []
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

        # Capture edition metadata attribute if set on html/body/main/article.
        for ed_key in ("data-edition", "data-edition-type"):
            if ed_key in attr_map and attr_map[ed_key].strip() and not self.doc.edition_attr:
                self.doc.edition_attr = attr_map[ed_key].strip().lower()

        # Track explicit stock ticker rows/cards for Gate S6 fidelity check.
        if "data-ticker" in attr_map or (t == "tr" and "data-market" in attr_map):
            self.doc.stock_row_count += 1

        # Collect element IDs & secondary JS/tab anchors (Gate S2).
        elem_id = attr_map.get("id", "").strip()
        if elem_id:
            self.doc.ids.add(elem_id)
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
            in_art_main = any(st_tag in ("article", "main") for st_tag, _, _ in self._stack)
            anc_classes: set[str] = set()
            has_inline_scroll = bool(
                style_raw and INLINE_OVERFLOW_SCROLL_RE.search(style_raw)
            )
            for _, st_cls, st_style in self._stack:
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
                for _, st_cls, _ in self._stack
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

        if self_closing or t in VOID_ELEMENTS:
            return

        # Push onto ancestor stack for non-void elements.
        self._stack.append((t, classes, style_raw))

        if t == "title":
            self.doc.has_title = True
            self._in_title = True
            self._title_chunks = []
        elif t in ("script", "style", "template"):
            self._skip_text_depth += 1
            if t == "style":
                self._in_style = True
                self._style_chunks = []
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

        if t in ("script", "style", "template") and self._skip_text_depth > 0:
            self._skip_text_depth -= 1

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
        if self._svg_stack and data.strip():
            self._svg_stack[-1].has_content = True
        if self._skip_text_depth == 0:
            self._vis_chunks.append(data)
            if self._cta_stack:
                self._cta_stack[-1][3].append(data)

    def finish(self) -> ParsedHtml:
        # Flush any unclosed SVGs so they still get inspected.
        while self._svg_stack:
            self.doc.svgs.append(self._svg_stack.pop())
        self.doc.visible_text = "".join(self._vis_chunks)
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
    """Gate S2: Zero broken internal links, assets & same-page anchors."""
    site_root = site_dir.resolve()
    by_abs: dict[Path, ParsedHtml] = {doc.abs_path: doc for doc in parsed_htmls.values()}

    for rel_path, doc in sorted(parsed_htmls.items()):
        for link in doc.links:
            raw_ref = link.value.strip()
            if not raw_ref:
                if link.tag in ("img", "script", "link"):
                    errors.append(
                        f"[S2] {rel_path}:{link.lineno}: empty <{link.tag} {link.attr}=\"\"> attribute"
                    )
                continue

            lower_ref = raw_ref.lower()
            if lower_ref.startswith(EXTERNAL_SCHEMES):
                continue
            if lower_ref.startswith("file:"):
                errors.append(
                    f"[S2] {rel_path}:{link.lineno}: forbidden local file:// reference in <{link.tag} {link.attr}>: {raw_ref}"
                )
                continue

            # Pure "#" is a standard HTML top-of-page / interactive anchor.
            if raw_ref == "#":
                continue

            parsed = urllib.parse.urlsplit(raw_ref)
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


def run_gate_s3(
    site_dir: Path,
    all_files: list[Path],
    parsed_htmls: dict[str, ParsedHtml],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Gate S3: Zero PII, local paths, secrets, unresolved directives, or raw Markdown separators."""
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


def _a_share_daily_is_light(doc: ParsedHtml, market_state: dict | None) -> bool:
    """Determine if daily/a-share-latest.html represents a light/holiday edition (0 charts allowed)."""
    if doc.edition_attr in ("light", "holiday_watch"):
        return True
    if doc.edition_attr == "main":
        return False
    if LIGHT_EDITION_HINTS_RE.search(doc.title_text) or LIGHT_EDITION_HINTS_RE.search(
        doc.visible_text[:2000]
    ):
        return True
    if re.search(r"(?:晚刊|收盘主刊)", doc.title_text):
        return False
    if market_state and isinstance(market_state.get("markets"), dict):
        latest_rel = market_state["markets"].get("a_share", {}).get("latest_daily")
        if isinstance(latest_rel, str) and latest_rel.strip():
            md_path = REPO_ROOT / "equity" / latest_rel
            if md_path.is_file():
                try:
                    md_txt = md_path.read_text(encoding="utf-8")
                    if re.search(r'"edition_type"\s*:\s*"(?:light|holiday_watch)"', md_txt):
                        return True
                    if not re.search(r"<!--\s*CHART_[A-Z]\d+", md_txt):
                        return True
                except OSError:
                    pass
    return False


def run_gate_s4(
    parsed_htmls: dict[str, ParsedHtml],
    market_state: dict | None,
    errors: list[str],
    warnings: list[str],
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

    # Daily latest pages: gold, hk-stock, us-stock require >= 1 data chart.
    for rel_path in DAILY_REQUIRED_CHART_PAGES:
        doc = parsed_htmls.get(rel_path)
        if doc is None:
            continue
        chart_count = sum(1 for s in doc.svgs if s.is_data_chart)
        if chart_count < 1:
            errors.append(
                f"[S4] {rel_path}: found 0 data <svg> charts (required >= 1)"
            )

    # A-share daily: light edition may legitimately have 0 charts; warn only if main edition lacks charts.
    a_doc = parsed_htmls.get(DAILY_OPTIONAL_LIGHT_PAGE)
    if a_doc is not None:
        chart_count = sum(1 for s in a_doc.svgs if s.is_data_chart)
        if chart_count < 1 and not _a_share_daily_is_light(a_doc, market_state):
            warnings.append(
                f"[S4] {DAILY_OPTIONAL_LIGHT_PAGE}: main edition has 0 data <svg> charts"
            )


def run_gate_s5(
    site_dir: Path,
    all_files: list[Path],
    parsed_htmls: dict[str, ParsedHtml],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Gate S5: Desktop + mobile responsive meta hygiene, <title>, <nav>, and scrollable tables."""
    # Dynamically discover CSS classes declaring overflow-x / overflow: auto|scroll.
    global_scroll_classes: set[str] = set()
    for p in all_files:
        if p.suffix.lower() == ".css":
            try:
                global_scroll_classes.update(
                    _extract_scrollable_classes_from_css(p.read_text(encoding="utf-8"))
                )
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
        for style_block in doc.inline_styles:
            local_scroll_classes.update(_extract_scrollable_classes_from_css(style_block))

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


def _check_gold_tier0_mutex(index_doc: ParsedHtml, errors: list[str]) -> None:
    """Ensure index.html enforces Gold Tier 0 mutex (no active buy-gold CTA/instructions)."""
    vis = index_doc.visible_text

    # 1. Confirm Tier 0 / red-light lock status is visibly communicated on index.html.
    if not GOLD_TIER0_LOCK_INDICATORS_RE.search(vis):
        errors.append(
            "[S6] index.html: Gold new_buy_allowed is False, but no Tier 0 / 红灯停 / 暂不新买 "
            "lock indicator found in visible text"
        )

    # 2. Check all buttons / links for unguarded active buy-gold CTAs.
    for cta in index_doc.ctas:
        if GOLD_CTA_BUY_RE.search(cta.text) and not GOLD_DEFER_GUARD_RE.search(cta.text):
            errors.append(
                f"[S6] index.html:{cta.lineno}: Gold Tier 0 mutex violation — active buy-gold "
                f"CTA <{cta.tag}>: {cta.text!r}"
            )

    # 3. Scan visible prose line-by-line for unguarded buy-gold directives.
    for raw_line in vis.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        for m in GOLD_ACTIVE_BUY_RE.finditer(line):
            win = line[max(0, m.start() - 45) : min(len(line), m.end() + 45)]
            if not GOLD_DEFER_GUARD_RE.search(win):
                errors.append(
                    f"[S6] index.html: Gold Tier 0 mutex violation — unguarded buy-gold directive "
                    f"in visible text: {win!r}"
                )
                return


def run_gate_s6(
    parsed_htmls: dict[str, ParsedHtml],
    gold_snap: dict | None,
    market_state: dict | None,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Gate S6: Live SSOT fidelity on index.html, screener.html total count, and Gold Tier 0 mutex."""
    index_doc = parsed_htmls.get("index.html")
    screener_doc = parsed_htmls.get("screener.html")

    # 1. Live spot gold & Gold Tier 0 mutex from gold/data_snapshot.json.
    gold_new_buy_blocked = False
    if gold_snap is not None:
        spot_val = gold_snap.get("spot_gold_ny_close_usd")
        spot_rounded = gold_snap.get("spot_gold_ny_close_rounded")
        if index_doc is not None and spot_val is not None:
            extras = [spot_rounded] if spot_rounded is not None else []
            variants = _numeric_variants(float(spot_val), extras)
            if not _contains_any_number(index_doc.visible_text, variants):
                errors.append(
                    f"[S6] index.html: missing live Gold spot_gold_ny_close_usd={spot_val} "
                    f"(expected one of {variants[:6]})"
                )
        if gold_snap.get("new_buy_allowed") is False or (
            str(gold_snap.get("tier_code", "")).strip() == "Tier 0"
        ):
            gold_new_buy_blocked = True

    # 2. Live A / HK / US benchmark indices & 135-stock screener count from market_state.json.
    if market_state is not None:
        markets = market_state.get("markets")
        if isinstance(markets, dict):
            gold_mirror = markets.get("gold_mirror_readonly")
            if isinstance(gold_mirror, dict) and gold_mirror.get("new_buy_allowed") is False:
                gold_new_buy_blocked = True

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

            # Screener total stock pool fidelity across A / HK / US.
            pool_counts: list[int] = []
            for mkey in ("a_share", "hk_stock", "us_stock"):
                mobj = markets.get(mkey)
                if isinstance(mobj, dict) and isinstance(mobj.get("stock_pool_count"), (int, float)):
                    pool_counts.append(int(mobj["stock_pool_count"]))

            if len(pool_counts) == 3 and screener_doc is not None:
                expected_total = sum(pool_counts)
                tot_pat = re.compile(rf"(?<![0-9]){expected_total}(?![0-9])")
                if not tot_pat.search(screener_doc.visible_text):
                    errors.append(
                        f"[S6] screener.html: missing expected total stock pool count "
                        f"{expected_total} ({'+'.join(str(c) for c in pool_counts)}) in visible text"
                    )
                if screener_doc.stock_row_count >= 20 and screener_doc.stock_row_count != expected_total:
                    errors.append(
                        f"[S6] screener.html: static stock row count ({screener_doc.stock_row_count}) "
                        f"!= expected total ({expected_total})"
                    )

    # 3. Gold Tier 0 mutex enforcement on index.html.
    if gold_new_buy_blocked and index_doc is not None:
        _check_gold_tier0_mutex(index_doc, errors)


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

    # Pre-load SSOT JSONs (optional if absent; error if corrupt).
    gold_snap = _load_json_if_present(GOLD_SNAPSHOT_PATH, "gold/data_snapshot.json", errors)
    market_state = _load_json_if_present(MARKET_STATE_PATH, "equity/state/market_state.json", errors)

    # Gate S1: Completeness & non-empty output (also parses all HTML files once).
    parsed_htmls, all_files = run_gate_s1(site_dir, errors, warnings)

    if site_dir.is_dir():
        # Gate S2: Internal links, assets & anchors.
        run_gate_s2(site_dir, parsed_htmls, errors, warnings)

        # Gate S3: Zero PII, local paths, secrets & unresolved directives.
        run_gate_s3(site_dir, all_files, parsed_htmls, errors, warnings)

        # Gate S4: Vector SVG chart integrity.
        run_gate_s4(parsed_htmls, market_state, errors, warnings)

        # Gate S5: Desktop + mobile responsive hygiene.
        run_gate_s5(site_dir, all_files, parsed_htmls, errors, warnings)

        # Gate S6: Live SSOT & 135-stock screener fidelity + Gold Tier 0 mutex.
        run_gate_s6(parsed_htmls, gold_snap, market_state, errors, warnings)

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
