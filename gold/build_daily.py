#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pure-web HTML & vector SVG rendering engine for daily gold research Markdown reports:
  - Dark-slate cover banner + plain-Chinese KPI cards (DAILY_META)
  - Visual primitives (DAILY_VERDICT, DAILY_SIGNAL_NOISE, DAILY_PERSONA, DAILY_GLOSSARY,
    DAILY_LAYER_BADGE, DAILY_TRUST_BAR, and 3 big-font 640px vector SVGs)
  - Shared smart table renderer (alignment preserved, auto col-nowrap guard, tabular-nums,
    atomic unit protection, crisp vector status pills, escaped pipe support)
  - Shared Markdown-to-HTML parser used by scripts/build_site.py and gold/build_report.py
"""

from __future__ import annotations

import html
import json
import re
from math import fsum
from pathlib import Path

from chart_input import normalize_chart

BASE_DIR = Path(__file__).resolve().parent
DAILY_DIR = BASE_DIR / "daily"

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_VALID_SVG_ANCHORS = frozenset({"start", "middle", "end"})


def sanitize_hex_color(val: object, default: str = "#b45309") -> str:
    s = str(val or "").strip()
    return s if _HEX_COLOR_RE.match(s) else default


def _sanitize_svg_anchor(val: object, default: str = "middle") -> str:
    s = str(val or "").strip().lower()
    return s if s in _VALID_SVG_ANCHORS else default

# Strip bitmap emojis, variation selectors, ZWJ, keycap combiner & XML 1.0 control chars while keeping vector ✓/✕
EMOJI_STRIP_RE = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u2712\u2714\u2716-\u27bf\u23e9-\u23fa\u2b05-\u2b55\ufe0f\u200d\u20e3\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)
_DOT_EMOJI_RE = re.compile(r"(⚪|🔴|🟡|🟢|🚨)\ufe0f?\s?")


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def svg_esc(s: str) -> str:
    """Strip ALL bitmap emojis, ZWJ/VS16 & XML control chars (preserving vector ✓/✕) for Skia-safe SVGs."""
    cleaned = EMOJI_STRIP_RE.sub("", str(s))
    cleaned = re.sub(r"\s{2,}", " ", cleaned).replace("： ", "：").strip()
    return html.escape(cleaned, quote=True)


def replace_dot_emojis(html_str: str, is_alert_badge: bool = False) -> str:
    """Replace status circle/alert emojis with crisp pure-CSS vector dots (amber diamond for L1 alert badges & L1 tags)."""
    def _sub(m: re.Match) -> str:
        ch = m.group(1)
        if ch == "🟡":
            after = html_str[m.end():m.end() + 8]
            if is_alert_badge or re.match(r"\s*L1\b", after):
                return '<span class="dot dot-amber dot-diamond"></span>'
            return '<span class="dot dot-amber"></span>'
        cls_map = {
            "⚪": "dot-slate",
            "🔴": "dot-red",
            "🟢": "dot-green",
            "🚨": "dot-red",
        }
        return f'<span class="dot {cls_map[ch]}"></span>'

    return _DOT_EMOJI_RE.sub(_sub, html_str)


def apply_dot_emojis_safe(html_str: str) -> str:
    """Apply vector dot substitution ONLY in text outside <svg>, <code>, <pre>, and HTML tags."""
    protected = re.split(r"(<svg\b[^>]*>.*?</svg>|<pre\b[^>]*>.*?</pre>|<code\b[^>]*>.*?</code>|<[^>]+>)", html_str, flags=re.DOTALL | re.IGNORECASE)
    for i in range(0, len(protected), 2):
        if protected[i]:
            protected[i] = replace_dot_emojis(protected[i], is_alert_badge=False)
    return "".join(protected)


def _format_inline_styles(seg: str) -> str:
    seg = re.sub(r"\*\*((?:(?!\*\*).)+?)\*\*", r"<strong>\1</strong>", seg)
    seg = re.sub(r"(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", seg)
    return seg


def md_inline(text: str) -> str:
    """Safe inline Markdown parser: backticks first, <br />, paired <strong>/<code>, escaped links, math-safe *."""
    s = str(text)
    s = re.sub(r"<br\s*/?>", "___BR_TAG___", s, flags=re.IGNORECASE)
    s = s.replace("\n", "___BR_TAG___")

    code_tokens: list[str] = []
    paired_strong: list[str] = []
    link_tokens: list[str] = []

    def save_code_raw(m):
        inner_esc = esc(m.group(1))
        code_tokens.append(f'<code class="inline-code">{inner_esc}</code>')
        return f"___CODE_{len(code_tokens)-1}___"

    # Protect inline backtick code & paired <code> FIRST so literal HTML/markdown inside code is never altered
    s = re.sub(r"`([^`]+)`", save_code_raw, s)
    s = re.sub(r"<code>(.*?)</code>", save_code_raw, s, flags=re.IGNORECASE | re.DOTALL)

    def _hold_strong(m):
        paired_strong.append(m.group(1))
        return f"___PSTRONG_{len(paired_strong)-1}___"

    s = re.sub(r"<strong>(.*?)</strong>", _hold_strong, s, flags=re.IGNORECASE | re.DOTALL)

    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def save_link(m):
        label = _format_inline_styles(m.group(1))
        url = esc(m.group(2).replace("&amp;", "&"))
        link_tokens.append(f'<a href="{url}">{label}</a>')
        return f"___LINK_{len(link_tokens)-1}___"

    s = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+|(?!file:|javascript:|data:)(?:\.\.?/|/)?[^)\s:]+\.(?:md|html)(?:#[^)\s]+)?|#[A-Za-z0-9_-]+)\)",
        save_link,
        s,
    )
    s = _format_inline_styles(s)

    for idx, inner in enumerate(paired_strong):
        inner_esc = _format_inline_styles(inner.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        s = s.replace(f"___PSTRONG_{idx}___", f"<strong>{inner_esc}</strong>")
    for idx, tok in enumerate(link_tokens):
        s = s.replace(f"___LINK_{idx}___", tok)
    for idx, tok in enumerate(code_tokens):
        s = s.replace(f"___CODE_{idx}___", tok)
    s = s.replace("___BR_TAG___", "<br/>")
    return s


# ==============================================================================
# SHARED SMART MARKDOWN TABLE RENDERER (Alignment, col-nowrap, Atomic Units, Status Pills)
# ==============================================================================

_NW_UNITS = r"(?:元/克|元/千克|美元/盎司|美元|港元|欧元|基点|吨|盎司|万元|亿元|元(?![/旦]))"
_ATOMIC_NW_RE = re.compile(
    rf"(?:(?<![\d.,+-])[+-]?\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?%?\s*[–~]\s*\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?%?(?![\d.,])(?:\s*{_NW_UNITS})?"
    rf"|(?<![\d.,+-])[+-]?\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?\s*{_NW_UNITS}"
    r"|元/克|元/千克|美元/盎司|美元|港元|基点|全年|前三季)"
)
_PROTECT_SKIP_RE = re.compile(
    r"(<a\b[^>]*>.*?</a>|<code\b[^>]*>.*?</code>|<pre\b[^>]*>.*?</pre>|<svg\b[^>]*>.*?</svg>"
    r'|<span\b[^>]*\bclass="nw"[^>]*>.*?</span>|<[^>]+>)',
    flags=re.DOTALL | re.IGNORECASE,
)

_STATUS_PILLS = [
    (re.compile(r"^(?:\*\*)?❌\ufe0f?\s*(?:\*\*)?([^\s|*]{2,10})(?:\*\*)?$"), "st-fail", "✕"),
    (re.compile(r"^(?:\*\*)?✅\ufe0f?\s*(?:\*\*)?([^\s|*]{2,10})(?:\*\*)?$"), "st-pass", "✓"),
    (re.compile(r"^(?:\*\*)?⚠️?\s*(?:\*\*)?([^\s|*]{2,10})(?:\*\*)?$"), "st-warn", "!"),
]

_NUM_CELL_RE = re.compile(r"^(?:约|近|超|仅|省|约省|差|±|[+-])?\s*[$¥€£]?\d")


def _split_md_row(raw: str) -> list[str]:
    inner = raw.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith(r"\|"):
        inner = inner[:-1]
    parts = re.split(r"(?<!\\)\|", inner)
    return [p.replace(r"\|", "|").strip() for p in parts]


def _vis_len(md_cell: str) -> float:
    # Split on <br/> BEFORE stripping HTML tags so multi-line cells report max single-line width
    raw_lines = re.split(r"<br\s*/?>|\n", md_cell, flags=re.IGNORECASE)
    best = 0.0
    for ln in raw_lines:
        plain = re.sub(r"\*\*|\*|`", "", ln)
        plain = re.sub(r"<[^>]+>", "", plain).strip()
        w = fsum(1.0 if ord(ch) > 127 else 0.55 for ch in plain)
        if w > best:
            best = w
    return best


def _protect_atomic_units(cell_html: str) -> str:
    """Wrap atomic currency/range strings in <span class="nw"> outside HTML tags, <a>, <code>, <pre>, <svg>."""
    parts = _PROTECT_SKIP_RE.split(cell_html)
    for i in range(0, len(parts), 2):
        if parts[i]:
            parts[i] = _ATOMIC_NW_RE.sub(r'<span class="nw">\g<0></span>', parts[i])
    return "".join(parts)


def _format_cell(raw_md: str, is_header: bool = False, pdf_mode: bool = True) -> str:
    stripped = raw_md.strip()
    if not is_header:
        for pat, cls, sym in _STATUS_PILLS:
            m = pat.match(stripped)
            if m:
                return f'<span class="st-pill {cls}">{sym} {esc(m.group(1))}</span>'
    rendered = md_inline(stripped)
    if pdf_mode:
        rendered = _protect_atomic_units(rendered)
    return rendered


def render_md_table(table_lines: list[str], pdf_mode: bool = True) -> str:
    """Render a buffered Markdown table with preserved alignment, auto col-nowrap, tabular-nums, and pills."""
    parsed_rows: list[list[str]] = []
    aligns: list[str] = []
    for raw in table_lines:
        cells = _split_md_row(raw)
        if cells and all(re.match(r"^:?-{2,}:?$", c) for c in cells):
            aligns = [
                ("ta-c" if c.startswith(":") and c.endswith(":") else ("ta-r" if c.endswith(":") else "ta-l"))
                for c in cells
            ]
            continue
        parsed_rows.append(cells)

    if not parsed_rows:
        return ""

    header = parsed_rows[0]
    body = parsed_rows[1:]
    ncols = len(header)
    while len(aligns) < ncols:
        aligns.append("ta-l")

    # Compute column metrics for intelligent col-nowrap & numeric alignment
    h_lens = [_vis_len(header[c]) for c in range(ncols)]
    b_maxs = [0.0] * ncols
    num_hits = [0] * ncols
    total_chars = 0
    for row in body:
        for c in range(min(ncols, len(row))):
            cell_raw = row[c]
            total_chars += len(cell_raw)
            vl = _vis_len(cell_raw)
            if vl > b_maxs[c]:
                b_maxs[c] = vl
            plain_c = re.sub(r"\*\*|\*|`|<[^>]+>", "", cell_raw).strip()
            if _NUM_CELL_RE.match(plain_c):
                num_hits[c] += 1

    # Candidate nowrap columns with padding-aware width cap <= 25.0 (protects wrapping columns!)
    candidates = []
    for c in range(ncols):
        if (h_lens[c] <= 7.5 and b_maxs[c] <= 9.5) or (h_lens[c] <= 9.0 and b_maxs[c] <= 6.5):
            candidates.append((max(h_lens[c], b_maxs[c]), c))
    candidates.sort()
    nowrap_cols: set[int] = set()
    used_w = 0.0
    for w, c in candidates:
        if len(nowrap_cols) >= ncols - 1:
            break
        cost = w + 1.5
        if used_w + cost <= 25.0:
            nowrap_cols.add(c)
            used_w += cost

    protect_col0 = (ncols <= 5 and 0 not in nowrap_cols and any(b_maxs[c] >= 24.0 for c in range(1, ncols)))

    col_classes: list[str] = []
    for c in range(ncols):
        cls = [aligns[c]]
        if c in nowrap_cols:
            cls.append("col-nowrap")
        if c == 0 and protect_col0:
            cls.append("col-first-min")
        if body and (num_hits[c] / len(body)) >= 0.7 and b_maxs[c] <= 15.0:
            cls.append("col-num")
        col_classes.append(" ".join(cls))

    ths = "".join(
        f'<th class="{col_classes[c]}">{_format_cell(header[c], is_header=True, pdf_mode=pdf_mode)}</th>'
        for c in range(ncols)
    )
    trs = []
    for row in body:
        tds = []
        for c in range(ncols):
            val = row[c] if c < len(row) else ""
            tds.append(f'<td class="{col_classes[c]}">{_format_cell(val, is_header=False, pdf_mode=pdf_mode)}</td>')
        trs.append(f"<tr>{''.join(tds)}</tr>")

    keep_cls = " table-keep" if (len(body) <= 6 and total_chars <= 900) else ""
    return (
        f'<div class="table-wrap{keep_cls}"><table class="data-table">'
        f"<thead><tr>{ths}</tr></thead>"
        f"<tbody>{''.join(trs)}</tbody>"
        "</table></div>"
    )


# ==============================================================================
# BEGINNER-FRIENDLY HTML COMPONENT RENDERERS (PDF + Native OOXML Word)
# ==============================================================================

def render_verdict_card(cfg: dict) -> str:
    level = str(cfg.get("level", "L0")).upper()
    palette = {
        "L0": ("#475569", "#f8fafc", "#334155", "L0 静默观察日"),
        "L1": ("#b45309", "#fffbeb", "#92400e", "L1 关键节点前瞻"),
        "L2": ("#b91c1c", "#fef2f2", "#991b1b", "L2 正式行动信号"),
    }
    brd, bg, txt, default_badge = palette.get(level, palette["L0"])
    badge = replace_dot_emojis(esc(cfg.get("badge", default_badge)), is_alert_badge=(level == "L1"))
    headline = _protect_atomic_units(md_inline(cfg.get("headline", "")))
    traffic = replace_dot_emojis(md_inline(cfg.get("traffic_light", "")), is_alert_badge=False)
    bullets = cfg.get("bullets", [])
    risk_line = _protect_atomic_units(md_inline(cfg.get("risk_line", "")))

    bul_html = "".join(f"<li>{_protect_atomic_units(md_inline(b))}</li>" for b in bullets)
    risk_html = f'<div class="verdict-risk"><strong>底线风险提示：</strong>{risk_line}</div>' if risk_line else ""
    return f'''
    <div class="verdict-card" style="border-left:5px solid {brd};background:{bg};">
      <div class="verdict-top">
        <span class="verdict-badge" style="background:{brd};">{badge}</span>
        <span class="verdict-light">{traffic}</span>
      </div>
      <div class="verdict-headline" style="color:{txt};">{headline}</div>
      {"<ul class='verdict-list'>" + bul_html + "</ul>" if bul_html else ""}
      {risk_html}
    </div>
    '''


def render_signal_noise(cfg: dict) -> str:
    title = esc(cfg.get("title", "30 秒降噪过滤：今天什么是真信号，什么可以直接划走？"))
    signals = cfg.get("signals", [])
    noises = cfg.get("noises", [])
    sig_items = "".join(
        f'<li><strong>{md_inline(s.get("head",""))}</strong>：{md_inline(s.get("body",""))}</li>'
        for s in signals
    ) or "<li><strong>0 件改变大局的事件</strong>：今日市场波动属常规噪音，无需调整既定计划。</li>"
    noi_items = "".join(
        f'<li><strong>{md_inline(n.get("head",""))}</strong>：{md_inline(n.get("body",""))}</li>'
        for n in noises
    )
    return f'''
    <div class="sn-box">
      <div class="sn-title">{title}</div>
      <div class="sn-grid">
        <div class="sn-col sn-col-sig">
          <div class="sn-col-head">✓ 今天真正影响决策的信号（{len(signals)} 件）</div>
          <div class="sn-col-body"><ul class="sn-ul">{sig_items}</ul></div>
        </div>
        <div class="sn-col sn-col-noi">
          <div class="sn-col-head">✕ 今天刷屏、但普通人不用管的噪音（{len(noises)} 件）</div>
          <div class="sn-col-body"><ul class="sn-ul">{noi_items}</ul></div>
        </div>
      </div>
    </div>
    '''


def render_persona_cards(cfg: dict) -> str:
    title = esc(cfg.get("title", "对号入座：不管你现在是什么情况，今天到底该怎么办？"))
    cards = cfg.get("cards", [])
    accent_map = {
        "A": ("#0369a1", "#f0f9ff"),
        "B": ("#b45309", "#fffbeb"),
        "C": ("#047857", "#ecfdf5"),
        "D": ("#4f46e5", "#eef2ff"),
    }
    rendered_cards = []
    for c in cards:
        grp = str(c.get("group", "A"))[:1].upper()
        brd, bg = accent_map.get(grp, ("#475569", "#f8fafc"))
        heading = md_inline(c.get("heading", ""))
        sub = md_inline(c.get("subtitle", ""))
        actions = "".join(f"<li>{_protect_atomic_units(md_inline(a))}</li>" for a in c.get("actions", []))
        avoid = _protect_atomic_units(md_inline(c.get("avoid", "")))
        avoid_html = f'<div class="persona-avoid"><strong>切忌踩坑：</strong>{avoid}</div>' if avoid else ""
        badge_html = f'<span class="grp-badge" style="background:{brd};">{grp}</span>'
        sub_html = f'<div class="persona-sub">{sub}</div>' if sub else ""
        rendered_cards.append(
            f'<div class="persona-card" style="border-left:4px solid {brd};background:{bg};">'
            f'<div class="persona-head">{badge_html}{heading}</div>'
            f'{sub_html}'
            f'<ul class="persona-ul">{actions}</ul>'
            f'{avoid_html}'
            f'</div>'
        )
    if not rendered_cards:
        return ""
    # Physically bind title + first card inside .persona-lead so Chromium never strands an orphan title!
    lead_html = f'<div class="persona-lead"><div class="persona-title">{title}</div>{rendered_cards[0]}</div>'
    rest_html = "".join(rendered_cards[1:])
    return f'<div class="persona-wrap">{lead_html}{rest_html}</div>'


def render_glossary(cfg: dict) -> str:
    raw_title = EMOJI_STRIP_RE.sub("", str(cfg.get("title", "30 秒人话词典（本章涉及的金融词，看这一框就全懂）"))).strip()
    title = esc(raw_title)
    terms = cfg.get("terms", [])
    rows = "".join(
        f'<tr><td style="width:26%;"><strong>{md_inline(t.get("term",""))}</strong></td>'
        f'<td>{md_inline(t.get("plain",""))}</td></tr>'
        for t in terms
    )
    return f'''
    <div class="glossary-box">
      <div class="glossary-title"><span class="gloss-pill">人话词典</span> {title}</div>
      <table class="glossary-table"><tbody>{rows}</tbody></table>
    </div>
    '''


def render_layer_badge(cfg: dict) -> str:
    raw_lbl = EMOJI_STRIP_RE.sub("", str(cfg.get("label", "进阶专业复核区｜给想看底层数据与公式的读者，新手可直接跳过"))).strip()
    tone = cfg.get("tone", "pro")
    pill = "进阶复核" if tone == "pro" else "深度精读"
    cls = "layer-badge-pro" if tone == "pro" else "layer-badge-deep"
    p_cls = "lb-pill-pro" if tone == "pro" else "lb-pill-deep"
    return f'<div class="{cls}"><span class="{p_cls}">{pill}</span> {md_inline(raw_lbl)}</div>'


def render_trust_bar(cfg: dict) -> str:
    title = esc(cfg.get("title", "本刊透明质检徽章（严守事实核验，不遮掩细节修订）"))
    items = cfg.get("items", [])
    note = md_inline(cfg.get("note", ""))
    li_html = "".join(f"<li>{md_inline(it)}</li>" for it in items)
    note_html = f'<div class="trust-note">{note}</div>' if note else ""
    return f'''
    <div class="trust-box">
      <div class="trust-title">{title}</div>
      <ul class="trust-ul">{li_html}</ul>
      {note_html}
    </div>
    '''


# ==============================================================================
# BIG-FONT, ZERO-COLLISION 640px VECTOR SVG CHART RENDERERS (Print Font >= 8.5pt!)
# ==============================================================================

HALO = 'paint-order="stroke" stroke="#ffffff" stroke-width="3.5" stroke-linejoin="round"'
_NON_SPOT_GOLD_RE = re.compile(r"(老铺|中金|紫金|山东|山金|赤峰|银泰|周大福|老凤祥|六福|周生生|矿|股|首饰|金店|ETF)")


def _fmt_axis_val(val: float, span: float, prefix: str = "", suffix: str = "") -> str:
    if span <= 6.0 or (abs(val - round(val)) > 1e-6 and span <= 40.0):
        num_s = f"{val:,.2f}"
    elif span <= 30.0:
        num_s = f"{val:,.1f}"
    else:
        num_s = f"{int(round(val)):,}"
    return f"{prefix}{num_s}{suffix}"


def _svg_label_pill(
    tx: float,
    ty: float,
    txt: str,
    font_size: float,
    anchor: str = "middle",
    *,
    fill: str = "#ffffff",
    fill_opacity: float = 0.94,
    stroke: str = "",
    stroke_opacity: float = 0.35,
    rx_radius: float = 3.0,
) -> tuple[str, tuple[float, float, float, float]]:
    """Build a crisp opaque/semi-opaque rounded pill rect behind an SVG label (no stroke-halo OCR doubling)."""
    plain = EMOJI_STRIP_RE.sub("", str(txt)).strip()
    text_w = round(max(_vis_len(plain) * font_size * 1.08, font_size * 1.6), 1)
    pad_x = 4.5
    w = round(text_w + 2.0 * pad_x, 1)
    h = round(font_size + 4.4, 1)
    if anchor == "start":
        rx = round(tx - pad_x, 1)
    elif anchor == "end":
        rx = round(tx - text_w - pad_x, 1)
    else:
        rx = round(tx - w / 2.0, 1)
    ry = round(ty - font_size * 0.88 - 1.7, 1)
    stroke_attr = f' stroke="{stroke}" stroke-opacity="{stroke_opacity}" stroke-width="0.8"' if stroke else ""
    rect = f'<rect x="{rx}" y="{ry}" width="{w}" height="{h}" fill="{fill}" fill-opacity="{fill_opacity:.2f}"{stroke_attr} rx="{rx_radius:g}"/>'
    return rect, (rx, ry, round(rx + w, 1), round(ry + h, 1))


def _boxes_overlap_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    pad_x: float = 2.0,
    pad_y: float = 1.5,
) -> float:
    ox = min(a[2] + pad_x, b[2]) - max(a[0] - pad_x, b[0])
    oy = min(a[3] + pad_y, b[3]) - max(a[1] - pad_y, b[1])
    return ox * oy if (ox > 0.0 and oy > 0.0) else 0.0


def _clamp_label_x(
    tx: float, txt: str, font_size: float, anchor: str = "middle",
    min_x: float = 56.0, max_x: float = 634.0,
) -> float:
    plain = EMOJI_STRIP_RE.sub("", str(txt)).strip()
    text_w = round(max(_vis_len(plain) * font_size * 1.08, font_size * 1.6), 1)
    pad_x = 4.0
    if anchor == "start":
        lo, hi = min_x + pad_x, max_x - text_w - pad_x
    elif anchor == "end":
        lo, hi = min_x + text_w + pad_x, max_x - pad_x
    else:
        half_w = (text_w + 2.0 * pad_x) / 2.0
        lo, hi = min_x + half_w, max_x - half_w
    if lo <= hi:
        tx = max(lo, min(hi, tx))
    return round(tx, 1)


def _ref_crossing_penalty(
    val: float,
    bbox: tuple[float, float, float, float],
    ref_coords: list[tuple[float, float]],
) -> float:
    """Penalize point labels that cross or straddle a horizontal reference line.

    SVG y increases downward: val < ref_val means the point sits below the ref line
    (higher y), so its label must not cross above ry (lower y), and vice versa.
    """
    pen = 0.0
    cy = (bbox[1] + bbox[3]) / 2.0
    for ref_val, ry in ref_coords:
        if val < ref_val - 1e-9:
            if cy <= ry:
                pen += 10000.0
            elif bbox[1] < ry:
                pen += 2000.0
        elif val > ref_val + 1e-9:
            if cy >= ry:
                pen += 10000.0
            elif bbox[3] > ry:
                pen += 2000.0
        else:
            if bbox[1] < ry < bbox[3]:
                pen += 2000.0
    return pen


def _polyline_crossing_penalty(
    bbox: tuple[float, float, float, float],
    segments: list[tuple[float, float, float, float]],
) -> float:
    """Softly penalize point labels that cut across polyline segments."""
    bx0, by0, bx1, by1 = bbox
    pen = 0.0
    for x1, y1, x2, y2 in segments:
        if max(x1, x2) < bx0 or min(x1, x2) > bx1 or max(y1, y2) < by0 or min(y1, y2) > by1:
            continue
        # Sample interior points along segment to estimate overlap with label pill
        hits = 0
        for step in (0.2, 0.35, 0.5, 0.65, 0.8):
            sx = x1 + (x2 - x1) * step
            sy = y1 + (y2 - y1) * step
            if bx0 <= sx <= bx1 and by0 <= sy <= by1:
                hits += 1
        if hits:
            pen += hits * 14.0
    return pen


def render_chart_timeline(cfg: dict) -> str:
    cfg = normalize_chart("DAILY_CHART_TIMELINE", cfg)
    title = esc(cfg.get("title", "金价走势核心结论"))
    sub = esc(cfg.get("subtitle", ""))
    note = esc(cfg.get("note", ""))
    pts = cfg.get("points", [])
    if not pts:
        return ""
    vals = [p["val"] for p in pts]
    v_lo, v_hi = min(vals), max(vals)
    pad = max((v_hi - v_lo) * 0.18, abs(v_hi) * 0.015, 1.0)
    y_min = cfg.get("y_min", v_lo - pad)
    y_max = cfg.get("y_max", v_hi + pad)
    if y_max <= y_min:
        mid = y_min
        y_min, y_max = mid - max(abs(mid) * 0.05, 1.0), mid + max(abs(mid) * 0.05, 1.0)
    span = y_max - y_min
    y_ticks = cfg.get("y_ticks") or [y_min + i * span / 4.0 for i in range(5)]
    ref_lines = cfg.get("ref_lines", [])
    zones = cfg.get("highlight_zones", [])
    unit_prefix = str(cfg.get("unit_prefix", "$"))
    unit_suffix = str(cfg.get("unit_suffix", ""))

    vb_w, vb_h = 640, 284

    def y_w(val: float) -> float:
        raw_y = 210.0 - ((val - y_min) / span) * 162.0
        return round(max(26.0, min(216.0, raw_y)), 1)

    n = len(pts)
    if n == 1:
        xs = [334.0]
    else:
        xs = [round(76.0 + i * (512.0 / (n - 1)), 1) for i in range(n)]

    placed_boxes: list[tuple[float, float, float, float]] = []
    all_dot_boxes: list[tuple[float, float, float, float]] = [
        (xs[j] - 6.0, y_w(vals[j]) - 6.0, xs[j] + 6.0, y_w(vals[j]) + 6.0)
        for j in range(n)
    ]
    poly_segments: list[tuple[float, float, float, float]] = [
        (xs[j], y_w(vals[j]), xs[j + 1], y_w(vals[j + 1]))
        for j in range(n - 1)
    ]

    zone_svg = ""
    for z in zones:
        i0 = max(0, min(n - 1, int(z.get("start_idx", 0))))
        i1 = max(0, min(n - 1, int(z.get("end_idx", n - 1))))
        if i0 > i1:
            i0, i1 = i1, i0
        x0 = max(56.0, xs[i0] - 22.0)
        x1 = min(626.0, xs[i1] + 22.0)
        cx = round((x0 + x1) / 2.0, 1)
        z_fill = sanitize_hex_color(z.get("fill"), "#f1f5f9")
        z_txt = sanitize_hex_color(z.get("text_color"), "#334155")
        z_lbl = str(z.get("label", ""))
        zone_svg += (
            f'<rect x="{x0}" y="24" width="{round(max(x1-x0, 4.0),1)}" height="190" '
            f'fill="{z_fill}" opacity="0.72" rx="4"/>'
            f'<text x="{cx}" y="38" text-anchor="middle" font-size="10.6" '
            f'fill="{z_txt}" font-weight="700">{svg_esc(z_lbl)}</text>'
        )
        if z_lbl.strip():
            _, z_bbox = _svg_label_pill(cx, 38.0, z_lbl, 10.6, "middle")
            placed_boxes.append(z_bbox)

    grid_svg = ""
    for tv in y_ticks:
        y = y_w(tv)
        grid_svg += f'<line x1="56" y1="{y}" x2="626" y2="{y}" stroke="#e2e8f0" stroke-width="0.9"/>'
        tick_str = _fmt_axis_val(tv, span, unit_prefix, unit_suffix)
        grid_svg += f'<text x="50" y="{y+4}" text-anchor="end" font-size="10.6" fill="#64748b">{svg_esc(tick_str)}</text>'

    ref_coords: list[tuple[float, float]] = []
    ref_lines_svg = ""
    ref_labels_svg = ""
    for rl in ref_lines:
        rval = float(rl["val"])
        ry = y_w(rval)
        ref_coords.append((rval, ry))
        col = sanitize_hex_color(rl.get("color"), "#b45309")
        anchor = _sanitize_svg_anchor(rl.get("align"), "end")
        raw_ref_lbl = str(rl.get("label", ""))
        rx = _clamp_label_x(
            float(rl.get("x", 622 if anchor == "end" else 62)),
            raw_ref_lbl, 10.6, anchor,
        )
        dy = float(rl.get("dy", -6))
        ref_lines_svg += f'<line x1="56" y1="{ry}" x2="626" y2="{ry}" stroke="{col}" stroke-width="1.5" stroke-dasharray="6,4"/>'
        if raw_ref_lbl.strip():
            base_ry = round(max(34.0, min(212.0, ry + dy)), 1)
            ref_cands = [
                base_ry,
                round(max(34.0, min(212.0, ry - dy + (12.0 if dy < 0 else -12.0))), 1),
                round(max(34.0, min(212.0, base_ry - 16.0)), 1),
                round(max(34.0, min(212.0, base_ry + 16.0)), 1),
            ]
            best_ry = base_ry
            best_pill = ""
            best_bbox = (0.0, 0.0, 0.0, 0.0)
            best_pen = float("inf")
            for cand_y in dict.fromkeys(ref_cands):
                pill, bbox = _svg_label_pill(
                    rx, cand_y, raw_ref_lbl, 10.6, anchor,
                    fill="#ffffff", fill_opacity=0.96, stroke=col, stroke_opacity=0.35, rx_radius=3.5,
                )
                pen = sum(_boxes_overlap_area(bbox, ob) for ob in placed_boxes)
                pen += 2.0 * sum(_boxes_overlap_area(bbox, db, pad_x=0.5, pad_y=0.5) for db in all_dot_boxes)
                pen += 0.25 * _polyline_crossing_penalty(bbox, poly_segments)
                if pen < best_pen:
                    best_pen = pen
                    best_ry = cand_y
                    best_pill = pill
                    best_bbox = bbox
                if pen == 0.0:
                    break
            placed_boxes.append(best_bbox)
            ref_labels_svg += best_pill
            ref_labels_svg += (
                f'<text x="{rx}" y="{best_ry}" text-anchor="{anchor}" '
                f'font-size="10.6" fill="{col}" font-weight="700">{svg_esc(raw_ref_lbl)}</text>'
            )

    poly = " ".join(f"{xs[i]},{y_w(val)}" for i, val in enumerate(vals))
    leaders_svg = ""
    dots_svg = ""
    point_labels_svg = ""
    axis_labels_svg = ""
    for i, p in enumerate(pts):
        x = xs[i]
        y = y_w(vals[i])
        col = sanitize_hex_color(p.get("color"), "#b45309" if p.get("highlight") else "#1e3a5f")
        pos = p.get("label_pos") or ("above" if (y > 72 and i % 2 == 0) else "below")
        dx = float(p.get("dx", 0.0))
        dy_extra = float(p.get("dy", 0.0))
        anc = _sanitize_svg_anchor(p.get("anchor"), "middle")
        y_default = round(max(34.0, min(212.0, (y - 11.0 if pos == "above" else y + 17.5) + dy_extra)), 1)
        # Do NOT apply pos's dy_extra onto the opposite flipped side
        y_alt = round(max(34.0, min(212.0, y + 17.5 if pos == "above" else y - 11.0)), 1)
        val_txt = p.get("val_label") or _fmt_axis_val(vals[i], span, unit_prefix, unit_suffix)
        x_default = _clamp_label_x(max(66.0, min(614.0, x + dx)), val_txt, 11.0, anc)
        r = "5.0" if p.get("highlight") else "4.2"
        dots_svg += f'<circle cx="{x}" cy="{y}" r="{r}" fill="{col}" stroke="#ffffff" stroke-width="1.5"/>'

        def _cy(val_y: float) -> float:
            return round(max(34.0, min(212.0, val_y)), 1)

        cands_2d: list[tuple[float, float, str]] = []
        y_above_base = y_default if pos == "above" else y_alt
        y_below_base = y_alt if pos == "above" else y_default
        first_dir = (y_above_base, -1.0) if pos == "above" else (y_below_base, 1.0)
        second_dir = (y_below_base, 1.0) if pos == "above" else (y_above_base, -1.0)

        # 1. Same-x fine vertical offsets (+0, +4, +8, +12, +16) before wider jumps
        for base_y, sign in (first_dir, second_dir):
            for step in (0.0, 4.0, 8.0, 12.0, 16.0, 22.0, 28.0):
                cands_2d.append((x_default, _cy(base_y + sign * step), anc))
        # 2. Fine horizontal x±12 shifts before lateral flips
        for dx_fine in (-12.0, 12.0):
            cx_f = _clamp_label_x(x + dx_fine, val_txt, 11.0, anc)
            for base_y, sign in (first_dir, second_dir):
                for step in (0.0, 4.0, 8.0, 12.0, 16.0):
                    cands_2d.append((cx_f, _cy(base_y + sign * step), anc))
        # 3. Lateral side-shift x±10 flipping anchor to end/start
        cx_left = _clamp_label_x(x - 10.0, val_txt, 11.0, "end")
        cx_right = _clamp_label_x(x + 10.0, val_txt, 11.0, "start")
        for cx_side, anc_side in ((cx_left, "end"), (cx_right, "start")):
            for dy_s in (4.0, -9.0, 16.0, -20.0, 26.0):
                cands_2d.append((cx_side, _cy(y + dy_s), anc_side))
        # 4. Horizontal dx ±26 / ±38 shifts with clamped x
        for dx_shift in (-26.0, 26.0, -38.0, 38.0):
            cx_sh = _clamp_label_x(x + dx_shift, val_txt, 11.0, anc)
            for cy in (y_default, y_alt, _cy(y + 4.0), _cy(y - 15.0), _cy(y + 20.0)):
                cands_2d.append((cx_sh, cy, anc))

        best_key: tuple[float, float] = (float("inf"), float("inf"))
        best_x = x_default
        best_y = y_default
        best_anc = anc
        best_pill = ""
        best_bbox = (0.0, 0.0, 0.0, 0.0)
        for cand_x, cand_y, cand_anc in dict.fromkeys(cands_2d):
            pill, bbox = _svg_label_pill(cand_x, cand_y, val_txt, 11.0, cand_anc)
            overlap_pen = sum(_boxes_overlap_area(bbox, ob) for ob in placed_boxes)
            dot_pen = 2.0 * sum(_boxes_overlap_area(bbox, db, pad_x=1.0, pad_y=1.0) for db in all_dot_boxes)
            cross_pen = _ref_crossing_penalty(vals[i], bbox, ref_coords)
            hard_pen = cross_pen + overlap_pen * 10.0 + dot_pen * 35.0
            lbl_cx = (bbox[0] + bbox[2]) / 2.0
            lbl_cy = (bbox[1] + bbox[3]) / 2.0
            poly_pen = _polyline_crossing_penalty(bbox, poly_segments)
            side_pen = 3.0 if ((pos == "above" and lbl_cy > y) or (pos == "below" and lbl_cy < y)) else 0.0
            dist_pen = (
                abs(lbl_cx - x) * 1.15
                + abs(lbl_cy - y)
                + poly_pen
                + side_pen
                + (4.0 if cand_anc != anc else 0.0)
            )
            key = (hard_pen, dist_pen)
            if key < best_key:
                best_key = key
                best_x = cand_x
                best_y = cand_y
                best_anc = cand_anc
                best_pill = pill
                best_bbox = bbox
            if hard_pen == 0.0 and poly_pen == 0.0 and cand_x == x_default and cand_y == y_default and cand_anc == anc:
                break
        placed_boxes.append(best_bbox)
        if abs(best_y - y) > 20.0:
            lx_end = round(max(best_bbox[0], min(x, best_bbox[2])), 1)
            ly_end = round(max(best_bbox[1], min(y, best_bbox[3])), 1)
            leaders_svg += (
                f'<line x1="{x}" y1="{y}" x2="{lx_end}" y2="{ly_end}" '
                f'stroke="#94a3b8" stroke-width="1" stroke-dasharray="2,2"/>'
            )
        point_labels_svg += best_pill
        point_labels_svg += f'<text x="{best_x}" y="{best_y}" text-anchor="{best_anc}" font-size="11" fill="{col}" font-weight="800">{svg_esc(val_txt)}</text>'
        axis_labels_svg += f'<text x="{x}" y="234" text-anchor="middle" font-size="10.5" fill="#0f172a" font-weight="700">{svg_esc(p.get("time", ""))}</text>'
        for li, dl in enumerate(str(p.get("desc", "")).split("\n")[:2]):
            axis_labels_svg += f'<text x="{x}" y="{250 + li*14}" text-anchor="middle" font-size="10.4" fill="#475569">{svg_esc(dl)}</text>'

    sub_html = f'<div class="chart-sub">{sub}</div>' if sub else ""
    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      {sub_html}
      <svg viewBox="0 0 {vb_w} {vb_h}" width="100%" role="img" aria-label="{title}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="{vb_w}" height="{vb_h}" fill="#ffffff" rx="6"/>
        {zone_svg}
        {grid_svg}
        {ref_lines_svg}
        <polyline fill="none" stroke="#1e3a5f" stroke-width="2.6" points="{poly}"/>
        {leaders_svg}
        {dots_svg}
        {ref_labels_svg}
        {point_labels_svg}
        {axis_labels_svg}
      </svg>
      <div class="chart-note">{note}</div>
    </div>
    '''


def render_chart_switch(cfg: dict) -> str:
    """Dual-Gauge Dashboard (640px, >=10.0px print-safe, dynamic height, safe red/amber/green detection)."""
    cfg = normalize_chart("DAILY_CHART_SWITCH", cfg)
    title = esc(cfg.get("title", "买点到了吗？四项安全条件仅亮 1 项，继续保持红灯观望"))
    sub = esc(cfg.get("subtitle", "买金四步红绿灯体检表与历史水位尺（单一真相刻度）"))
    note = esc(cfg.get("note", ""))
    gauges = cfg.get("gauges", [])
    checks = cfg.get("checks", [])
    status_line = svg_esc(cfg.get("status_line", "当前判定：红灯停（暂不新买 · 满足 1/4 项）"))

    # Dynamic traffic light dot color (explicit override -> Red checked BEFORE Amber so "距黄灯差3关" stays Red!)
    if cfg.get("status_color"):
        dot_col = sanitize_hex_color(cfg.get("status_color"), "#dc2626")
    elif "红灯" in status_line:
        dot_col = "#dc2626"
    elif "绿灯" in status_line or "满格" in status_line:
        dot_col = "#16a34a"
    elif "黄灯" in status_line:
        dot_col = "#d97706"
    else:
        dot_col = "#dc2626"

    n_gauges = max(len(gauges), 1)
    gauge_stride = 54
    sep_y = 38 + n_gauges * gauge_stride
    cards_y0 = sep_y + 36
    n_rows = max((len(checks) + 1) // 2, 1)
    vb_w = 640
    vb_h = cards_y0 + n_rows * 64 + 8

    gauge_svg = ""
    for gi, g in enumerate(gauges):
        y = 40 + gi * gauge_stride
        pct = g["pct"]
        raw_lbl = str(g.get("label", ""))
        raw_val_txt = str(g.get("value_text", ""))
        lbl = svg_esc(raw_lbl)
        val_txt = svg_esc(raw_val_txt)
        bar_col = sanitize_hex_color(g.get("color"), "#b45309")
        bx = 16
        bw = 608
        fill_w = round(bw * pct / 100.0, 1)
        gauge_svg += (
            f'<text x="{bx}" y="{y}" font-size="11.2" fill="#0f172a" font-weight="700">{lbl}</text>'
            f'<text x="{bx+bw}" y="{y}" text-anchor="end" font-size="11.0" fill="{bar_col}" font-weight="700">{val_txt}</text>'
            f'<rect x="{bx}" y="{y+7}" width="{bw}" height="12" fill="#e2e8f0" rx="6"/>'
            f'<rect x="{bx}" y="{y+7}" width="{fill_w}" height="12" fill="{bar_col}" rx="6"/>'
        )
        tp = g.get("threshold_pct")
        tx = round(bx + bw * tp / 100.0, 1) if tp is not None else None
        if tx is not None:
            gauge_svg += f'<line x1="{tx}" y1="{y+5}" x2="{tx}" y2="{y+21}" stroke="#0f172a" stroke-width="1.8"/>'

        # Crisp non-overlapping scale & threshold micro-labels cleanly below the gauge bar
        y_micro = y + 32
        is_drawdown = bool(re.search(r"(?:45\.5%|回调|回撤|熊市)", raw_lbl + raw_val_txt))
        if is_drawdown:
            x_20 = round(bx + bw * (20.0 / 45.5), 1)
            x_30 = tx if (tx is not None and abs(tp - (30.0 / 45.5 * 100.0)) <= 6.0) else round(bx + bw * (30.0 / 45.5), 1)
            gauge_svg += (
                f'<line x1="{x_20}" y1="{y+7}" x2="{x_20}" y2="{y+19}" stroke="#94a3b8" stroke-width="1.0" stroke-dasharray="2,2"/>'
                f'<text x="{bx}" y="{y_micro}" text-anchor="start" font-size="8.8" fill="#64748b">0%</text>'
                f'<text x="{x_20}" y="{y_micro}" text-anchor="middle" font-size="8.8" fill="#64748b">-20%</text>'
                f'<text x="{x_30}" y="{y_micro}" text-anchor="middle" font-size="8.8" fill="#0f172a" font-weight="700">-30%</text>'
                f'<text x="{bx+bw}" y="{y_micro}" text-anchor="end" font-size="8.8" fill="#64748b">-45.5%</text>'
            )
        else:
            gauge_svg += (
                f'<text x="{bx}" y="{y_micro}" text-anchor="start" font-size="8.8" fill="#64748b">0%</text>'
                f'<text x="{bx+bw}" y="{y_micro}" text-anchor="end" font-size="8.8" fill="#64748b">100%</text>'
            )
            if tx is not None:
                th_lbl = svg_esc(str(g.get("threshold_label") or f"参考线 {tp:g}%"))
                th_x = round(max(bx + 54.0, min(bx + bw - 60.0, tx)), 1)
                gauge_svg += f'<text x="{th_x}" y="{y_micro}" text-anchor="middle" font-size="8.8" fill="#0f172a" font-weight="700">{th_lbl}</text>'

    card_svg = ""
    for idx, ch in enumerate(checks):
        ci = idx % 2
        ri = idx // 2
        x = 16 + ci * 310
        y = cards_y0 + ri * 64
        passed = bool(ch.get("passed", False))
        bg = "#f0fdf4" if passed else "#fef2f2"
        brd = "#16a34a" if passed else "#dc2626"
        tcol = "#166534" if passed else "#991b1b"
        pill_bg = "#16a34a" if passed else "#dc2626"
        badge = "✓ 已过关" if passed else "✕ 未过关"
        nm = svg_esc(ch.get("name", f"第 {idx+1} 关"))
        d1 = svg_esc(ch.get("line1", ""))
        d2 = svg_esc(ch.get("line2", ""))
        card_svg += (
            f'<rect x="{x}" y="{y}" width="298" height="56" fill="{bg}" stroke="{brd}" stroke-width="1.3" rx="6"/>'
            f'<text x="{x+10}" y="{y+18}" font-size="11.2" fill="{tcol}" font-weight="800">{nm}</text>'
            f'<rect x="{x+232}" y="{y+6}" width="58" height="16" fill="{pill_bg}" rx="8"/>'
            f'<text x="{x+261}" y="{y+17.5}" text-anchor="middle" font-size="10.0" fill="#ffffff" font-weight="700">{badge}</text>'
            f'<text x="{x+10}" y="{y+35}" font-size="10.6" fill="#1f2937">{d1}</text>'
            f'<text x="{x+10}" y="{y+49}" font-size="10.4" fill="#475569">{d2}</text>'
        )

    sub_html = f'<div class="chart-sub">{sub}</div>' if sub else ""
    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      {sub_html}
      <svg viewBox="0 0 {vb_w} {vb_h}" width="100%" role="img" aria-label="{title}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="{vb_w}" height="{vb_h}" fill="#ffffff" rx="6"/>
        <text x="16" y="18" font-size="11.6" fill="#1e3a8a" font-weight="800">一、历史水位尺（帮你一秒判断压力有多大）</text>
        {gauge_svg}
        <line x1="16" y1="{sep_y}" x2="624" y2="{sep_y}" stroke="#cbd5e1" stroke-width="1"/>
        <circle cx="22" cy="{sep_y+18}" r="5" fill="{dot_col}"/>
        <text x="33" y="{sep_y+22}" font-size="11.6" fill="#1e3a8a" font-weight="800">二、{status_line}</text>
        {card_svg}
      </svg>
      <div class="chart-note">{note}</div>
    </div>
    '''


def _is_protagonist_gold(it: dict) -> bool:
    if "highlight" in it:
        return bool(it["highlight"])
    raw_lbl = str(it.get("label", ""))
    if _NON_SPOT_GOLD_RE.search(raw_lbl):
        return False
    return any(tok in raw_lbl for tok in ("黄金", "沪金", "现货金", "伦敦金", "上海金", "金条", "Au99"))


def render_chart_cross(cfg: dict) -> str:
    """1:1 Honest Linear Scale Cross-Asset Diverging Bar Chart with collision-proof x_zero & strict protagonist highlight."""
    cfg = normalize_chart("DAILY_CHART_CROSS", cfg)
    title = esc(cfg.get("title", "隔夜全球市场分化全景"))
    sub = esc(cfg.get("subtitle", "主要资产单日涨跌幅（%）｜ [中文惯例：红涨 / 绿跌 · 1:1 真实线性比例]"))
    note = esc(cfg.get("note", ""))
    items = cfg.get("items", [])
    reverse_items = cfg.get("reverse_items", [])
    if not items:
        return ""

    cap_abs = max(cfg.get("linear_cap_pct", 10.0), 1.0)
    row_h = 23.5
    top_pad = 30
    main_h = round(top_pad + len(items) * row_h, 1)

    # Pre-measure reverse_items so long labels never collide with right-aligned details
    rev_layouts: list[tuple[bool, float, dict]] = []
    rev_total_h = 0.0
    if reverse_items:
        rev_total_h = 28.0
        for ri in reverse_items:
            l_w = _vis_len(str(ri.get("label", "")))
            d_w = _vis_len(str(ri.get("detail", "")))
            two_line = (l_w + d_w) > 46.0
            rh = 36.0 if two_line else 21.0
            rev_layouts.append((two_line, rh, ri))
            rev_total_h += rh + 4.5

    vb_w = 640
    vb_h = int(round(main_h + rev_total_h + 14))

    x_label = 124.0
    parsed_pcts = [it["pct"] for it in items]
    max_neg = min(cap_abs, max([abs(p) for p in parsed_pcts if p < 0] or [2.5]))
    max_pos = min(cap_abs, max([abs(p) for p in parsed_pcts if p > 0] or [4.0]))
    usable_span_px = 228.0
    px_per_pct = round(min(15.0, usable_span_px / max(max_neg + max_pos, 7.5)), 2)
    # Guarantee negative bars NEVER cross x_label + 10, and positive bars leave >= 200px for right labels
    min_x_zero = x_label + 12.0 + max_neg * px_per_pct
    x_zero = round(max(198.0, min_x_zero), 1)
    any_capped = any(abs(p) > cap_abs for p in parsed_pcts)

    # Dynamic vertical reference ticks bounded strictly by actual negative/positive bar extent and cap_abs
    actual_neg = min(cap_abs, max((abs(p) for p in parsed_pcts if p < 0), default=0.0))
    actual_pos = min(cap_abs, max((p for p in parsed_pcts if p > 0), default=0.0))
    span_peak = max(actual_neg, actual_pos)
    if cap_abs <= 6.0 or span_peak <= 4.5:
        tick_step = 2
    elif cap_abs <= 15.0:
        tick_step = 5
    else:
        tick_step = 10
    neg_ticks = [-v for v in range(tick_step, int(actual_neg) + 1, tick_step)]
    pos_ticks = [v for v in range(tick_step, int(actual_pos) + 1, tick_step)]
    ticks_svg = ""
    for tv in sorted(neg_ticks + pos_ticks):
        tx = round(x_zero + tv * px_per_pct, 1)
        if x_label + 14 < tx < 425 and abs(tx - x_zero) >= 22.0:
            ticks_svg += f'<line x1="{tx}" y1="{top_pad-3}" x2="{tx}" y2="{main_h}" stroke="#e2e8f0" stroke-width="0.8" stroke-dasharray="2,3"/>'
            ticks_svg += f'<text x="{tx}" y="18" text-anchor="middle" font-size="9.8" fill="#94a3b8">{tv:+d}%</text>'

    stripes_svg = ""
    rows_svg = ""
    for i, it in enumerate(items):
        y = round(top_pad + i * row_h, 1)
        pct = parsed_pcts[i]
        raw_lbl = str(it.get("label", ""))
        lbl = svg_esc(raw_lbl)
        tag = svg_esc(it.get("tag", ""))
        val_str = svg_esc(it.get("pct_label") or f"{pct:+.2f}%")
        is_gold = _is_protagonist_gold(it)
        capped = abs(pct) > cap_abs
        eff_abs = cap_abs if capped else abs(pct)
        if abs(pct) < 1e-6:
            w = 2.5
            bx = round(x_zero - 1.2, 1)
            col = sanitize_hex_color(it.get("color"), "#64748b")
            tx = round(x_zero + 7.0, 1)
        elif pct > 0:
            w = max(4.0, round(eff_abs * px_per_pct, 1))
            bx = x_zero
            col = sanitize_hex_color(it.get("color"), "#b91c1c" if is_gold else "#c2410c")
            tx = round(bx + w + 7.0, 1)
        else:
            w = max(4.0, round(eff_abs * px_per_pct, 1))
            bx = round(x_zero - w, 1)
            col = sanitize_hex_color(it.get("color"), "#0f766e")
            tx = round(x_zero + 7.0, 1)
        bg = "#fffbeb" if is_gold else ("#f8fafc" if i % 2 == 0 else "#ffffff")
        op = "0.96" if is_gold else "0.78"
        stripes_svg += f'<rect x="10" y="{round(y-2.5,1)}" width="620" height="{row_h}" fill="{bg}"/>'
        if is_gold:
            stripes_svg += f'<rect x="10" y="{round(y-2.5,1)}" width="3.5" height="{row_h}" fill="#d97706"/>'
        rows_svg += f'<text x="{x_label}" y="{round(y+13.2,1)}" text-anchor="end" font-size="10.8" fill="{"#92400e" if is_gold else "#1e293b"}" font-weight="{"800" if is_gold else "700"}">{lbl}</text>'
        rows_svg += f'<rect x="{bx}" y="{round(y+2.5,1)}" width="{w}" height="14" fill="{col}" opacity="{op}" rx="2.5"/>'
        if capped:
            mx = round(bx + w - 16.0, 1) if pct >= 0 else round(bx + 16.0, 1)
            rows_svg += (
                f'<line x1="{mx-4}" y1="{round(y+17,1)}" x2="{mx+1}" y2="{round(y+2,1)}" stroke="#ffffff" stroke-width="2.2"/>'
                f'<line x1="{mx+1}" y1="{round(y+17,1)}" x2="{mx+6}" y2="{round(y+2,1)}" stroke="#ffffff" stroke-width="2.2"/>'
            )
        label_full = f"{val_str} {tag}".strip()
        rows_svg += f'<text x="{tx}" y="{round(y+13.2,1)}" text-anchor="start" font-size="10.5" fill="{col}" font-weight="700">{label_full}</text>'

    rev_svg = ""
    if rev_layouts:
        ry0 = round(main_h + 10, 1)
        rev_svg += f'<line x1="10" y1="{ry0}" x2="630" y2="{ry0}" stroke="#cbd5e1" stroke-width="1"/>'
        rev_svg += f'<text x="14" y="{ry0+16}" font-size="10.8" fill="#1e3a8a" font-weight="800">反向情绪与信用指标（独立展示，避免与涨跌颜色混淆）</text>'
        cur_y = ry0 + 23.0
        for two_line, rh, ri in rev_layouts:
            ry = round(cur_y, 1)
            rev_svg += f'<rect x="14" y="{ry}" width="612" height="{rh}" fill="#eff6ff" stroke="#bfdbfe" stroke-width="1" rx="4"/>'
            if two_line:
                rev_svg += (
                    f'<text x="22" y="{round(ry+14.0,1)}" font-size="10.4" fill="#1e3a8a" font-weight="700">{svg_esc(ri.get("label",""))}</text>'
                    f'<text x="22" y="{round(ry+29.5,1)}" font-size="10.2" fill="#1e40af" font-weight="600">{svg_esc(ri.get("detail",""))}</text>'
                )
            else:
                rev_svg += (
                    f'<text x="22" y="{round(ry+14.5,1)}" font-size="10.6" fill="#1e3a8a" font-weight="700">{svg_esc(ri.get("label",""))}</text>'
                    f'<text x="618" y="{round(ry+14.5,1)}" text-anchor="end" font-size="10.4" fill="#1e40af" font-weight="700">{svg_esc(ri.get("detail",""))}</text>'
                )
            cur_y += rh + 4.5

    legend_txt = "红涨 / 绿跌 · // 极值断轴 · 金底标主角" if any_capped else "红涨 / 绿跌 · 金底标主角"
    sub_html = f'<div class="chart-sub">{sub}</div>' if sub else ""
    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      {sub_html}
      <svg viewBox="0 0 {vb_w} {vb_h}" width="100%" role="img" aria-label="{title}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="{vb_w}" height="{vb_h}" fill="#ffffff" rx="6"/>
        <text x="{x_label}" y="18" text-anchor="end" font-size="10.6" fill="#64748b" font-weight="700">核心资产</text>
        <text x="{x_zero}" y="18" text-anchor="middle" font-size="10.6" fill="#334155" font-weight="700">0%</text>
        <text x="626" y="18" text-anchor="end" font-size="10.2" fill="#64748b">{legend_txt}</text>
        {stripes_svg}
        {ticks_svg}
        {rows_svg}
        <line x1="{x_zero}" y1="{top_pad-4}" x2="{x_zero}" y2="{main_h}" stroke="#475569" stroke-width="1.4"/>
        {rev_svg}
      </svg>
      <div class="chart-note">{note}</div>
    </div>
    '''


# ==============================================================================
# MARKDOWN PARSER
# ==============================================================================

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

COMMENT_RE = re.compile(
    r"<!--\s*(DAILY_[A-Z0-9_]+)\s*(.*?)\s*-->",
    re.DOTALL,
)
GENERIC_HTML_COMMENT_RE = re.compile(r"<!--(?!\s*CHART_[A-Z0-9_]+\s*-->).*?-->", re.DOTALL)

CHART_KINDS = {"DAILY_CHART_TIMELINE", "DAILY_CHART_SWITCH", "DAILY_CHART_CROSS"}


def extract_directives(md_text: str) -> tuple[dict, str, dict]:
    meta = {}
    widgets = {}
    counter = 0

    def repl(m):
        nonlocal meta, counter
        kind = m.group(1)
        raw_json = m.group(2).strip()
        if kind not in KNOWN_DIRECTIVES:
            raise ValueError(f"Unknown DAILY_* directive name: <!-- {kind} ... --> (possible typo)")
        if not raw_json.startswith("{") or not raw_json.endswith("}"):
            raise ValueError(f"Malformed JSON payload in <!-- {kind} ... --> directive")
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in <!-- {kind} ... --> directive: {e}") from e
        if kind == "DAILY_META":
            meta = data
            return ""
        tok = f"___DAILY_WIDGET_{counter}___"
        counter += 1
        widgets[tok] = (kind, data)
        return f"\n{tok}\n"

    cleaned = COMMENT_RE.sub(repl, md_text)
    # Strip any remaining ordinary HTML comments (e.g. MASTER_BASELINE, editorial notes) while keeping CHART_* hooks
    cleaned = GENERIC_HTML_COMMENT_RE.sub("", cleaned)
    return meta, cleaned, widgets


def render_widget(kind: str, data: dict) -> str:
    if kind == "DAILY_VERDICT":
        return render_verdict_card(data)
    if kind == "DAILY_SIGNAL_NOISE":
        return render_signal_noise(data)
    if kind == "DAILY_PERSONA":
        return render_persona_cards(data)
    if kind == "DAILY_GLOSSARY":
        return render_glossary(data)
    if kind == "DAILY_LAYER_BADGE":
        return render_layer_badge(data)
    if kind == "DAILY_TRUST_BAR":
        return render_trust_bar(data)
    if kind == "DAILY_CHART_TIMELINE":
        return render_chart_timeline(data)
    if kind == "DAILY_CHART_SWITCH":
        return render_chart_switch(data)
    if kind == "DAILY_CHART_CROSS":
        return render_chart_cross(data)
    return ""


def parse_markdown_to_html(
    md_text: str,
    *,
    docx_mode: bool = False,
    break_layer3: bool = False,
    chart_map: dict | None = None,
    skip_doc_title: bool = True,
) -> tuple[str, dict, str, list[tuple[str, str]]]:
    """Shared Markdown-to-HTML converter for both Daily & Master Reports.
    Supports nested lists (under both <ul> and <ol>), h1–h4, blank '>' lines, <ol start>,
    DAILY_* widgets, CHART_* hooks, and automatic Layer 2 page breaks.
    """
    meta, cleaned, widgets = extract_directives(md_text)
    lines = cleaned.splitlines()
    title = "黄金每日深度研报"
    title_captured = False
    layer2_broken = False
    html_out: list[str] = []
    docx_charts: list[tuple[str, str]] = []
    in_ul = False
    in_ol = False
    in_sub_ul = False
    table_buf: list[str] = []
    in_code = False
    code_buf: list[str] = []
    quote_buf: list[str] = []

    def flush_quote():
        nonlocal quote_buf
        if quote_buf:
            joined = "<br/>".join(
                (_protect_atomic_units(md_inline(q)) if not docx_mode else md_inline(q)) if q else "&nbsp;"
                for q in quote_buf
            )
            html_out.append(f'<div class="callout">{joined}</div>')
            quote_buf = []

    def close_lists():
        nonlocal in_ul, in_ol, in_sub_ul
        if in_sub_ul:
            html_out.append("</ul></li>")
            in_sub_ul = False
        elif in_ol or in_ul:
            html_out.append("</li>")
        if in_ol:
            html_out.append("</ol>")
            in_ol = False
        if in_ul:
            html_out.append("</ul>")
            in_ul = False

    def close_table():
        nonlocal table_buf
        if table_buf:
            html_out.append(render_md_table(table_buf, pdf_mode=not docx_mode))
            table_buf = []

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped in widgets:
            flush_quote()
            close_lists()
            close_table()
            kind, data = widgets[stripped]
            rendered = render_widget(kind, data)
            if kind == "DAILY_LAYER_BADGE" and data.get("tone") == "deep" and not layer2_broken:
                html_out.append('<div class="volume-break"></div>')
                layer2_broken = True
            if docx_mode and kind in CHART_KINDS:
                marker = f"___DOCX_CHART_{len(docx_charts)}___"
                docx_charts.append((marker, rendered))
                html_out.append(f"<p>{marker}</p>")
            else:
                html_out.append(rendered)
            continue

        if chart_map and stripped in chart_map:
            flush_quote()
            close_lists()
            close_table()
            for fn in chart_map[stripped]:
                rendered = fn()
                if docx_mode:
                    marker = f"___DOCX_CHART_{len(docx_charts)}___"
                    docx_charts.append((marker, rendered))
                    html_out.append(f"<p>{marker}</p>")
                else:
                    html_out.append(rendered)
            continue

        if stripped.startswith("```"):
            flush_quote()
            close_lists()
            close_table()
            if not in_code:
                in_code = True
                code_buf = []
            else:
                escaped = "\n".join(code_buf).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_out.append(f'<pre class="code-block"><code>{escaped}</code></pre>')
                in_code = False
                code_buf = []
            continue
        if in_code:
            code_buf.append(raw)
            continue

        if line.startswith("> ") or stripped == ">":
            close_lists()
            close_table()
            quote_buf.append(line[2:].strip() if line.startswith("> ") else "")
            continue
        else:
            flush_quote()

        if not stripped or stripped == "---":
            close_lists()
            close_table()
            continue

        if line.startswith("|") and line.endswith("|"):
            close_lists()
            table_buf.append(line)
            continue
        else:
            close_table()

        if line.startswith("# "):
            close_lists()
            vol_txt = line[2:].strip()
            is_part_heading = any(k in vol_txt for k in ("第一部分", "第二部分", "第三部分", "附录"))
            if skip_doc_title and not title_captured and not is_part_heading:
                title = vol_txt
                title_captured = True
                continue
            should_break = False
            if "第二部分" in vol_txt:
                should_break = not layer2_broken
                layer2_broken = True
            elif break_layer3 and ("第三部分" in vol_txt or "附录" in vol_txt):
                should_break = True
            if should_break:
                html_out.append(f'<div class="volume-break"></div><h2 class="vol-header">{md_inline(vol_txt)}</h2>')
            else:
                html_out.append(f'<h2 class="vol-header">{md_inline(vol_txt)}</h2>')
            continue

        if line.startswith("## "):
            close_lists()
            h2_txt = line[3:].strip()
            if not layer2_broken and (h2_txt.startswith("专题一") or h2_txt.startswith("周末专题")):
                html_out.append(f'<div class="volume-break"></div><h2>{md_inline(h2_txt)}</h2>')
                layer2_broken = True
            else:
                html_out.append(f"<h2>{md_inline(h2_txt)}</h2>")
            continue
        if line.startswith("### "):
            close_lists()
            html_out.append(f"<h3>{md_inline(line[4:].strip())}</h3>")
            continue
        if line.startswith("#### "):
            close_lists()
            html_out.append(f"<h4>{md_inline(line[5:].strip())}</h4>")
            continue

        m_sub = re.match(r"^\s{2,}[-•*]\s+(.*)$", line)
        m_num = re.match(r"^(\d+)\.\s+(.*)$", line)
        m_bul = re.match(r"^[-•*]\s+(.*)$", line)
        if m_sub and (in_ol or in_ul):
            if not in_sub_ul:
                in_sub_ul = True
                html_out.append('<ul class="sub-ul">')
            html_out.append(f"<li>{md_inline(m_sub.group(1))}</li>")
            continue
        if m_num:
            start_n = int(m_num.group(1))
            if in_ul:
                close_lists()
            elif in_sub_ul:
                html_out.append("</ul></li>")
                in_sub_ul = False
            elif in_ol:
                html_out.append("</li>")
            if not in_ol:
                in_ol = True
                start_attr = f' start="{start_n}"' if start_n != 1 else ""
                html_out.append(f"<ol{start_attr}>")
            html_out.append(f"<li>{md_inline(m_num.group(2))}")
            continue
        if m_bul or m_sub:
            txt = m_bul.group(1) if m_bul else m_sub.group(1)
            if in_ol:
                close_lists()
            elif in_sub_ul:
                html_out.append("</ul></li>")
                in_sub_ul = False
            elif in_ul:
                html_out.append("</li>")
            if not in_ul:
                in_ul = True
                html_out.append("<ul>")
            html_out.append(f"<li>{md_inline(txt)}")
            continue

        close_lists()
        p_html = md_inline(line)
        if not docx_mode:
            p_html = _protect_atomic_units(p_html)
        html_out.append(f"<p>{p_html}</p>")

    if in_code and code_buf:
        escaped = "\n".join(code_buf).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html_out.append(f'<pre class="code-block"><code>{escaped}</code></pre>')
    flush_quote()
    close_lists()
    close_table()
    final_html = apply_dot_emojis_safe("\n".join(html_out))
    return title, meta, final_html, docx_charts


def md_to_html(
    md_text: str,
    docx_mode: bool = False,
    break_layer3: bool = False,
) -> tuple[str, dict, str, list[tuple[str, str]]]:
    """Backwards-compatible wrapper around parse_markdown_to_html."""
    return parse_markdown_to_html(md_text, docx_mode=docx_mode, break_layer3=break_layer3)


def build_cover_html(title: str, meta: dict, accent: str = "#b45309") -> str:
    safe_accent = sanitize_hex_color(accent, "#b45309")
    tag = esc(meta.get("tag", "每日黄金深度研报 · 北京时间 07:30 · 11:30 · 18:00 三刊"))
    ts = esc(meta.get("timestamp", ""))
    summary = _protect_atomic_units(esc(meta.get("summary", "")))
    kpis = meta.get("kpis", [])

    meta_html = ""
    if ts or summary:
        line = f"<strong>基准时点</strong>：{ts}" if ts else ""
        if summary:
            line += f" &nbsp;|&nbsp; {summary}" if line else summary
        meta_html = f'<div class="cover-meta">{line}</div>'

    kpi_html = ""
    if kpis:
        shown = kpis[:6]
        cards = [
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{esc(k.get("label", ""))}</div>'
            f'<div class="kpi-val">{replace_dot_emojis(esc(k.get("val", "")))}</div>'
            f'<div class="kpi-sub">{esc(k.get("sub", ""))}</div>'
            f'</div>'
            for k in shown
        ]
        strip_cls = "kpi-strip cols-4" if len(shown) == 4 else "kpi-strip"
        kpi_html = f'<div class="{strip_cls}">{"".join(cards)}</div>'

    return f'''
    <div class="cover-banner" style="border-bottom:4px solid {safe_accent};">
      <div class="cover-tag">{tag}</div>
      <h1 class="cover-title">{md_inline(title)}</h1>
      {meta_html}
      {kpi_html}
    </div>
    '''
