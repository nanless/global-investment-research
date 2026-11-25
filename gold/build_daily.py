#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build magazine-grade, beginner-friendly PDF & Native OOXML DOCX from a daily gold research Markdown report (V2.2):
  - Dark-slate cover banner + 6 plain-Chinese KPI cards (DAILY_META) with zero orphan characters
  - 7 beginner visual primitives (DAILY_VERDICT, DAILY_SIGNAL_NOISE, DAILY_PERSONA, DAILY_GLOSSARY,
    DAILY_LAYER_BADGE, DAILY_TRUST_BAR, and 3 big-font 640px vector SVGs)
  - Shared smart table renderer (alignment preserved, auto col-nowrap guard, tabular-nums, atomic unit protection,
    crisp vector status pills, escaped pipe support, compact table keep-together)
  - Shared Markdown-to-HTML parser (nested lists, h4+, blank quote lines, ol start, typo-safe directive checks)
  - Native ECMA-376 OOXML DOCX output (real <w:tbl>, cross-platform cards, PIL auto-cropped 2x Retina PNG charts,
    ZERO macOS textutil dependency!)

Usage:
  python3 build_daily.py                    # builds latest daily/YYYY-MM-DD_*.md (by filename descending)
  python3 build_daily.py /path/to/daily.md  # builds specific daily markdown file
  python3 build_daily.py --check            # self-check environment
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from chart_input import normalize_chart
from docx_embed import build_native_docx, render_chart_to_png

BASE_DIR = Path(__file__).resolve().parent
DAILY_DIR = BASE_DIR / "daily"
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

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

    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+|file://[^)\s]+)\)", save_link, s)
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
    rf"(?:(?<![\d.,+-])[+-]?\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?%?[–~]\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?%?(?![\d.,])(?:\s*{_NW_UNITS})?"
    rf"|(?<![\d.,+-])[+-]?\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?\s*{_NW_UNITS}"
    r"|元/克|元/千克|美元/盎司|美元|港元|基点|全年|前三季)"
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
        w = sum(1.0 if ord(ch) > 127 else 0.55 for ch in plain)
        if w > best:
            best = w
    return best


def _protect_atomic_units(cell_html: str) -> str:
    """Wrap atomic currency/range strings in <span class="nw"> outside of HTML tags."""
    parts = re.split(r"(<[^>]+>)", cell_html)
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

    protect_col0 = (ncols <= 4 and 0 not in nowrap_cols and any(b_maxs[c] >= 24.0 for c in range(1, ncols)))

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
    headline = md_inline(cfg.get("headline", ""))
    traffic = replace_dot_emojis(md_inline(cfg.get("traffic_light", "")), is_alert_badge=False)
    bullets = cfg.get("bullets", [])
    risk_line = md_inline(cfg.get("risk_line", ""))

    bul_html = "".join(f"<li>{md_inline(b)}</li>" for b in bullets)
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
      <table class="sn-table">
        <thead>
          <tr>
            <th style="width:46%;background:#0f3d2e;color:#ffffff;">✓ 今天真正影响决策的信号（{len(signals)} 件）</th>
            <th style="width:54%;background:#475569;color:#ffffff;">✕ 今天刷屏、但普通人不用管的噪音（{len(noises)} 件）</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style="background:#f0fdf4;"><ul class="sn-ul">{sig_items}</ul></td>
            <td style="background:#f8fafc;"><ul class="sn-ul">{noi_items}</ul></td>
          </tr>
        </tbody>
      </table>
    </div>
    '''


def render_persona_cards(cfg: dict) -> str:
    title = esc(cfg.get("title", "对号入座：不管你现在是什么情况，今天到底该怎么办？"))
    cards = cfg.get("cards", [])
    accent_map = {
        "A": ("#0284c7", "#f0f9ff"),
        "B": ("#b45309", "#fffbeb"),
        "C": ("#059669", "#ecfdf5"),
        "D": ("#4f46e5", "#eef2ff"),
    }
    rendered_cards = []
    for c in cards:
        grp = str(c.get("group", "A"))[:1].upper()
        brd, bg = accent_map.get(grp, ("#475569", "#f8fafc"))
        heading = md_inline(c.get("heading", ""))
        sub = md_inline(c.get("subtitle", ""))
        actions = "".join(f"<li>{md_inline(a)}</li>" for a in c.get("actions", []))
        avoid = md_inline(c.get("avoid", ""))
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

    vb_w, vb_h = 640, 266

    def y_w(val: float) -> float:
        return round(198.0 - ((val - y_min) / span) * 152.0, 1)

    n = len(pts)
    if n == 1:
        xs = [334.0]
    else:
        xs = [round(76.0 + i * (512.0 / (n - 1)), 1) for i in range(n)]

    zone_svg = ""
    for z in zones:
        i0 = max(0, min(n - 1, int(z.get("start_idx", 0))))
        i1 = max(0, min(n - 1, int(z.get("end_idx", n - 1))))
        if i0 > i1:
            i0, i1 = i1, i0
        x0 = max(56.0, xs[i0] - 22.0)
        x1 = min(626.0, xs[i1] + 22.0)
        cx = round((x0 + x1) / 2.0, 1)
        zone_svg += (
            f'<rect x="{x0}" y="24" width="{round(max(x1-x0, 4.0),1)}" height="178" '
            f'fill="{esc(z.get("fill", "#f1f5f9"))}" opacity="0.72" rx="4"/>'
            f'<text x="{cx}" y="38" text-anchor="middle" font-size="10.6" '
            f'fill="{esc(z.get("text_color", "#334155"))}" font-weight="700">{svg_esc(z.get("label", ""))}</text>'
        )

    grid_svg = ""
    for tv in y_ticks:
        y = y_w(tv)
        grid_svg += f'<line x1="56" y1="{y}" x2="626" y2="{y}" stroke="#e2e8f0" stroke-width="0.9"/>'
        tick_str = _fmt_axis_val(tv, span, unit_prefix, unit_suffix)
        grid_svg += f'<text x="50" y="{y+4}" text-anchor="end" font-size="10.6" fill="#64748b">{svg_esc(tick_str)}</text>'

    ref_svg = ""
    for rl in ref_lines:
        ry = y_w(rl["val"])
        col = esc(rl.get("color", "#b45309"))
        anchor = esc(rl.get("align", "end"))
        rx = rl.get("x", 622 if anchor == "end" else 62)
        dy = rl.get("dy", -6)
        ref_svg += f'<line x1="56" y1="{ry}" x2="626" y2="{ry}" stroke="{col}" stroke-width="1.5" stroke-dasharray="6,4"/>'
        ref_svg += (
            f'<text x="{rx}" y="{round(max(32.0, min(204.0, ry+dy)),1)}" text-anchor="{anchor}" '
            f'font-size="10.6" fill="{col}" font-weight="700" {HALO}>{svg_esc(rl.get("label", ""))}</text>'
        )

    poly = " ".join(f"{xs[i]},{y_w(val)}" for i, val in enumerate(vals))
    nodes_svg = ""
    for i, p in enumerate(pts):
        x = xs[i]
        y = y_w(vals[i])
        col = esc(p.get("color", "#b45309" if p.get("highlight") else "#1e3a5f"))
        pos = p.get("label_pos") or ("above" if (y > 70 and i % 2 == 0) else "below")
        dx = p.get("dx", 0.0)
        dy_extra = p.get("dy", 0.0)
        anc = esc(p.get("anchor", "middle"))
        y_lbl = round(max(34.0, min(205.0, (y - 10.5 if pos == "above" else y + 17.0) + dy_extra)), 1)
        x_lbl = round(max(66.0, min(614.0, x + dx)), 1)
        val_txt = p.get("val_label") or _fmt_axis_val(vals[i], span, unit_prefix, unit_suffix)
        r = "5.0" if p.get("highlight") else "4.2"
        nodes_svg += f'<circle cx="{x}" cy="{y}" r="{r}" fill="{col}" stroke="#ffffff" stroke-width="1.5"/>'
        nodes_svg += f'<text x="{x_lbl}" y="{y_lbl}" text-anchor="{anc}" font-size="11" fill="{col}" font-weight="800" {HALO}>{svg_esc(val_txt)}</text>'
        nodes_svg += f'<text x="{x}" y="220" text-anchor="middle" font-size="10.5" fill="#0f172a" font-weight="700">{svg_esc(p.get("time", ""))}</text>'
        for li, dl in enumerate(str(p.get("desc", "")).split("\n")[:2]):
            nodes_svg += f'<text x="{x}" y="{235 + li*14}" text-anchor="middle" font-size="10.4" fill="#475569">{svg_esc(dl)}</text>'

    sub_html = f'<div class="chart-sub">{sub}</div>' if sub else ""
    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      {sub_html}
      <svg viewBox="0 0 {vb_w} {vb_h}" width="100%" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="{vb_w}" height="{vb_h}" fill="#ffffff" rx="6"/>
        {zone_svg}
        {grid_svg}
        {ref_svg}
        <polyline fill="none" stroke="#1e3a5f" stroke-width="2.6" points="{poly}"/>
        {nodes_svg}
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
        dot_col = esc(cfg["status_color"])
    elif "红灯" in status_line:
        dot_col = "#dc2626"
    elif "绿灯" in status_line or "满格" in status_line:
        dot_col = "#16a34a"
    elif "黄灯" in status_line:
        dot_col = "#d97706"
    else:
        dot_col = "#dc2626"

    n_gauges = max(len(gauges), 1)
    sep_y = 38 + n_gauges * 44
    cards_y0 = sep_y + 36
    n_rows = max((len(checks) + 1) // 2, 1)
    vb_w = 640
    vb_h = cards_y0 + n_rows * 64 + 8

    gauge_svg = ""
    for gi, g in enumerate(gauges):
        y = 40 + gi * 44
        pct = g["pct"]
        lbl = svg_esc(g.get("label", ""))
        val_txt = svg_esc(g.get("value_text", ""))
        bar_col = esc(g.get("color", "#b45309"))
        bx = 16
        bw = 608
        fill_w = round(bw * pct / 100.0, 1)
        gauge_svg += (
            f'<text x="{bx}" y="{y}" font-size="11.2" fill="#0f172a" font-weight="700">{lbl}</text>'
            f'<text x="{bx+bw}" y="{y}" text-anchor="end" font-size="11.0" fill="{bar_col}" font-weight="700">{val_txt}</text>'
            f'<rect x="{bx}" y="{y+7}" width="{bw}" height="12" fill="#e2e8f0" rx="6"/>'
            f'<rect x="{bx}" y="{y+7}" width="{fill_w}" height="12" fill="{bar_col}" rx="6"/>'
        )
        if g.get("threshold_pct") is not None:
            tp = g["threshold_pct"]
            tx = round(bx + bw * tp / 100.0, 1)
            gauge_svg += f'<line x1="{tx}" y1="{y+5}" x2="{tx}" y2="{y+21}" stroke="#0f172a" stroke-width="1.8"/>'

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
      <svg viewBox="0 0 {vb_w} {vb_h}" width="100%" xmlns="http://www.w3.org/2000/svg">
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

    # Subtle vertical reference ticks (-10%, -5%, +5%, +10%) strictly left of top-right legend (x < 425)
    ticks_svg = ""
    for tv in (-10, -5, 5, 10):
        tx = round(x_zero + tv * px_per_pct, 1)
        if x_label + 14 < tx < 425:
            ticks_svg += f'<line x1="{tx}" y1="{top_pad-3}" x2="{tx}" y2="{main_h}" stroke="#e2e8f0" stroke-width="0.8" stroke-dasharray="2,3"/>'
            ticks_svg += f'<text x="{tx}" y="18" text-anchor="middle" font-size="9.8" fill="#94a3b8">{tv:+d}%</text>'

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
            col = esc(it.get("color", "#64748b"))
            tx = round(x_zero + 7.0, 1)
        elif pct > 0:
            w = max(4.0, round(eff_abs * px_per_pct, 1))
            bx = x_zero
            col = esc(it.get("color", "#b91c1c" if is_gold else "#c2410c"))
            tx = round(bx + w + 7.0, 1)
        else:
            w = max(4.0, round(eff_abs * px_per_pct, 1))
            bx = round(x_zero - w, 1)
            col = esc(it.get("color", "#0f766e"))
            tx = round(x_zero + 7.0, 1)
        bg = "#fffbeb" if is_gold else ("#f8fafc" if i % 2 == 0 else "#ffffff")
        op = "0.96" if is_gold else "0.78"
        rows_svg += f'<rect x="10" y="{round(y-2.5,1)}" width="620" height="{row_h}" fill="{bg}"/>'
        if is_gold:
            rows_svg += f'<rect x="10" y="{round(y-2.5,1)}" width="3.5" height="{row_h}" fill="#d97706"/>'
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
      <svg viewBox="0 0 {vb_w} {vb_h}" width="100%" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="{vb_w}" height="{vb_h}" fill="#ffffff" rx="6"/>
        <text x="{x_label}" y="18" text-anchor="end" font-size="10.6" fill="#64748b" font-weight="700">核心资产</text>
        <text x="{x_zero}" y="18" text-anchor="middle" font-size="10.6" fill="#334155" font-weight="700">0%</text>
        <text x="626" y="18" text-anchor="end" font-size="10.2" fill="#64748b">{legend_txt}</text>
        {rows_svg}
        {ticks_svg}
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
            joined = "<br/>".join(md_inline(q) if q else "&nbsp;" for q in quote_buf)
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
                html_out.append(f'<div class="volume-break"></div><h1 class="vol-header">{md_inline(vol_txt)}</h1>')
            else:
                html_out.append(f'<h1 class="vol-header">{md_inline(vol_txt)}</h1>')
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
        html_out.append(f"<p>{md_inline(line)}</p>")

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


# ==============================================================================
# MAGAZINE-GRADE PDF CSS (FT / Economist / Morningstar / W3C CLREQ Standard)
# ==============================================================================

PDF_CSS = """
@page {
  size: A4 portrait;
  margin: 14mm 14.5mm 14.5mm 14.5mm;
  @top-left {
    content: "__FOOTER_TITLE__";
    font-family: "PingFang SC", sans-serif;
    font-size: 7.2pt;
    color: #94a3b8;
    border-bottom: 0.5pt solid #e2e8f0;
    padding-bottom: 3px;
    margin-bottom: 6px;
  }
  @top-right {
    content: "多源核验 · 理性配置";
    font-family: "PingFang SC", sans-serif;
    font-size: 7.2pt;
    color: #94a3b8;
    border-bottom: 0.5pt solid #e2e8f0;
    padding-bottom: 3px;
    margin-bottom: 6px;
  }
  @bottom-left {
    content: "仅供参考 · 严守家庭资产 10%–15% 上限";
    font-family: "PingFang SC", sans-serif;
    font-size: 7.2pt;
    color: #94a3b8;
  }
  @bottom-right {
    content: "第 " counter(page) " / " counter(pages) " 页";
    font-family: "PingFang SC", sans-serif;
    font-size: 7.5pt;
    font-weight: 600;
    color: #64748b;
  }
}
@page :first {
  @top-left { content: none; border: none; }
  @top-right { content: none; border: none; }
}
* { box-sizing: border-box; }
body {
  font-family: "PingFang SC", "Hiragino Sans GB", -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif;
  color: #1f2937;
  font-size: 9.75pt;
  line-height: 1.61;
  margin: 0;
  padding: 0;
  background: #ffffff;
}

.dot { display: inline-block; width: 7.5px; height: 7.5px; border-radius: 50%; vertical-align: 0.5px; margin-right: 4px; }
.dot-red { background: #ef4444; box-shadow: 0 0 0 1.5px rgba(239,68,68,0.28); }
.dot-amber { background: #f59e0b; box-shadow: 0 0 0 1.5px rgba(245,158,11,0.28); }
.dot-green { background: #22c55e; box-shadow: 0 0 0 1.5px rgba(34,197,94,0.28); }
.dot-slate { background: #cbd5e1; box-shadow: 0 0 0 1.5px rgba(203,213,225,0.35); }
.dot-diamond {
  width: 7px;
  height: 7px;
  border-radius: 1.2px;
  transform: rotate(45deg);
  background: #f59e0b;
  box-shadow: 0 0 0 1.2px rgba(245,158,11,0.35);
  margin-right: 5px;
  vertical-align: 0.5px;
}
.verdict-badge .dot-diamond, .cover-banner .dot-diamond {
  background: #fde68a;
  box-shadow: 0 0 0 1.2px rgba(253,230,138,0.40);
}

.cover-banner {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 65%, #334155 100%);
  color: #ffffff;
  padding: 16px 19px 15px 19px;
  border-radius: 10px;
  border-bottom: 4px solid __ACCENT__;
  margin-bottom: 12px;
  break-inside: avoid;
  page-break-inside: avoid;
}
.cover-tag {
  display: inline-block;
  background: __ACCENT__;
  color: #ffffff;
  font-size: 7.6pt;
  font-weight: 700;
  letter-spacing: 0.3px;
  padding: 2.5px 9px;
  border-radius: 4px;
  margin-bottom: 6px;
}
.cover-title { font-size: 15.8pt; font-weight: 800; line-height: 1.30; letter-spacing: -0.2px; margin: 0 0 6px 0; color: #f8fafc; text-wrap: balance; }
.cover-meta { font-size: 8.2pt; color: #cbd5e1; line-height: 1.48; margin-bottom: 9px; }
.cover-banner strong { color: #f8fafc; }
.kpi-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6.5px; margin-top: 5px; }
.kpi-card { background: rgba(255,255,255,0.09); border: 1px solid rgba(255,255,255,0.16); border-radius: 6px; padding: 7px 8.5px; overflow: hidden; }
.kpi-label { font-size: 7.5pt; color: #cbd5e1; }
.kpi-val { font-size: 10.3pt; font-weight: 700; color: #fbbf24; margin-top: 2px; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-sub { font-size: 7.4pt; color: #e2e8f0; margin-top: 2px; line-height: 1.32; letter-spacing: -0.1px; font-variant-numeric: tabular-nums; }

.verdict-card { border-radius: 0 8px 8px 0; padding: 10px 13px; margin: 9px 0 11px 0; break-inside: avoid; page-break-inside: avoid; }
.verdict-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; gap: 8px; }
.verdict-badge { color: #ffffff; font-size: 8.1pt; font-weight: 700; padding: 2.5px 9px; border-radius: 4px; }
.verdict-light { font-size: 8.9pt; font-weight: 700; color: #0f172a; }
.verdict-headline { font-size: 10.6pt; font-weight: 800; line-height: 1.45; margin-bottom: 4px; }
.verdict-list { margin: 3.5px 0 5px 0; padding-left: 18px; font-size: 9.25pt; line-height: 1.58; }
.verdict-risk { font-size: 8.7pt; color: #7f1d1d; background: rgba(254,226,226,0.62); padding: 5px 9px; border-radius: 5px; margin-top: 4px; }

.sn-box { margin: 9px 0 12px 0; }
.sn-title { font-size: 9.9pt; font-weight: 800; color: #0f172a; margin-bottom: 4.5px; break-after: avoid; page-break-after: avoid; }
.sn-table { width: 100%; border-collapse: collapse; font-size: 8.75pt; line-height: 1.50; }
.sn-table thead { display: table-header-group; }
.sn-table th { padding: 6px 8.5px; text-align: left; font-weight: 700; border: none; }
.sn-table td { padding: 6.5px 8.5px; vertical-align: top; border-bottom: 1.5px solid #cbd5e1; }
.sn-ul { margin: 0; padding-left: 15px; }
.sn-ul li { margin-bottom: 3.5px; }

.persona-wrap { margin: 8px 0 10px 0; }
.persona-lead { break-inside: avoid; page-break-inside: avoid; }
.persona-title { font-size: 10.0pt; font-weight: 800; color: #0f172a; margin-bottom: 4.5px; break-after: avoid; page-break-after: avoid; }
.persona-card { border-radius: 0 7px 7px 0; padding: 6.5px 10.5px; margin-bottom: 5px; break-inside: avoid; page-break-inside: avoid; }
.persona-head { font-size: 9.45pt; font-weight: 800; color: #0f172a; margin-bottom: 1.5px; }
.grp-badge { display: inline-block; color: #ffffff; font-size: 7.7pt; font-weight: 800; padding: 0.5px 5.5px; border-radius: 3px; margin-right: 6px; vertical-align: 1px; }
.persona-sub { font-size: 8.25pt; color: #475569; margin-bottom: 3px; }
.persona-ul { margin: 2px 0 3px 0; padding-left: 17px; font-size: 8.7pt; line-height: 1.46; }
.persona-ul li { margin-bottom: 1.5px; }
.persona-avoid { font-size: 8.15pt; color: #991b1b; background: rgba(254,226,226,0.52); padding: 3px 7.5px; border-radius: 4px; margin-top: 2.5px; line-height: 1.42; }

.glossary-box { background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 0 7px 7px 0; padding: 8px 11px; margin: 9px 0 11px 0; break-inside: avoid; page-break-inside: avoid; }
.glossary-title { font-size: 9.3pt; font-weight: 800; color: #92400e; margin-bottom: 4.5px; break-after: avoid; page-break-after: avoid; }
.gloss-pill { display: inline-block; background: #d97706; color: #ffffff; font-size: 7.5pt; font-weight: 700; padding: 1px 6px; border-radius: 3px; margin-right: 4px; vertical-align: 1px; }
.glossary-table { width: 100%; border-collapse: collapse; font-size: 8.55pt; line-height: 1.48; }
.glossary-table td { padding: 3.5px 6px; border-bottom: 1px dashed #fcd34d; vertical-align: top; color: #374151; }
.glossary-table td:first-child strong { color: #78350f; }
.glossary-table tr:last-child td { border-bottom: none; }

.layer-badge-pro, .layer-badge-deep {
  background: transparent;
  border: none;
  border-bottom: 1px dashed #cbd5e1;
  padding: 2px 0 5px 0;
  margin: -3px 0 9px 0;
  font-size: 8.45pt;
  font-weight: 600;
  color: #475569;
  border-radius: 0;
  break-after: avoid;
  page-break-after: avoid;
}
.lb-pill-deep { display: inline-block; background: #1d4ed8; color: #ffffff; font-size: 7.4pt; font-weight: 700; padding: 1px 6px; border-radius: 3px; margin-right: 5px; }
.lb-pill-pro { display: inline-block; background: #475569; color: #ffffff; font-size: 7.4pt; font-weight: 700; padding: 1px 6px; border-radius: 3px; margin-right: 5px; }

.trust-box { background: #f8fafc; border: 1px solid #cbd5e1; border-left: 4px solid #475569; border-radius: 0 8px 8px 0; padding: 7.5px 11px; margin: 9px 0 7px 0; break-inside: avoid; page-break-inside: avoid; }
.trust-title { font-size: 9.15pt; font-weight: 800; color: #0f172a; margin-bottom: 3.5px; break-after: avoid; page-break-after: avoid; }
.trust-ul { margin: 2.5px 0 3.5px 0; padding-left: 17px; font-size: 8.55pt; color: #334155; line-height: 1.48; }
.trust-note { font-size: 7.9pt; color: #64748b; }

.vol-header {
  background: linear-gradient(90deg, #eff6ff 0%, #f8fafc 100%);
  border-left: 5px solid #1d4ed8;
  color: #1e3a8a;
  font-size: 12.6pt;
  font-weight: 800;
  padding: 7.5px 12px;
  margin: 13px 0 9px 0;
  border-radius: 0 6px 6px 0;
  break-after: avoid;
  page-break-after: avoid;
}
.volume-break { page-break-before: always; break-before: page; }
h2 { font-size: 11.4pt; font-weight: 800; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 3px; margin: 13px 0 7px 0; break-after: avoid; page-break-after: avoid; }
h3 { font-size: 10.1pt; font-weight: 700; color: #1e40af; margin: 9.5px 0 4.5px 0; break-after: avoid; page-break-after: avoid; }
h4 { font-size: 9.6pt; font-weight: 700; color: #334155; margin: 8px 0 3.5px 0; break-after: avoid; page-break-after: avoid; }
p { margin: 5px 0 8px 0; text-align: justify; text-justify: inter-ideograph; orphans: 3; widows: 3; text-wrap: pretty; line-break: strict; }
ul { margin: 3.5px 0 8px 0; padding-left: 19px; }
ol { margin: 3.5px 0 8px 0; padding-left: 24px; }
.sub-ul { margin: 2.5px 0 4px 0; padding-left: 17px; list-style-type: disc; }
li { margin-bottom: 3.2px; orphans: 3; widows: 3; text-wrap: pretty; line-break: strict; }
strong { color: #0f172a; font-weight: 700; }
th strong { color: #ffffff !important; }
th em { color: #e2e8f0; }
a { color: #1d4ed8; text-decoration: none; }
.inline-code { font-family: "SF Mono", "Menlo", monospace; font-size: 8.7pt; color: #1e3a8a; font-weight: 600; }
.code-block { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 7.5px 10px; font-family: "SF Mono", "Menlo", monospace; font-size: 8.4pt; white-space: pre-wrap; word-break: break-word; break-inside: avoid; }
.callout {
  background: #f0f9ff;
  border-left: 4px solid #0284c7;
  border-radius: 0 6px 6px 0;
  padding: 8px 12px;
  margin: 8px 0 10px 0;
  font-size: 9.3pt;
  line-height: 1.60;
  color: #0c4a6e;
  break-inside: avoid;
  page-break-inside: avoid;
}
.callout strong { color: #0369a1; }

/* Clean 3-Line Magazine Tables with Auto col-nowrap, Tabular Numerals & Status Pills */
.table-wrap { margin: 8px 0 11px 0; }
.table-wrap.table-keep { break-inside: avoid; page-break-inside: avoid; }
table.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 8.55pt;
  line-height: 1.45;
  border-top: 2px solid #0f172a;
  border-bottom: 2px solid #0f172a;
  font-variant-numeric: tabular-nums;
}
table.data-table thead { display: table-header-group; }
table.data-table tr { break-inside: avoid; page-break-inside: avoid; }
table.data-table th {
  background: #1e293b;
  color: #f8fafc;
  font-weight: 700;
  font-size: 8.1pt;
  line-height: 1.34;
  text-align: left;
  padding: 5.5px 6.5px;
  border: none;
  border-top: 2.5px solid __ACCENT__;
}
table.data-table td {
  padding: 4.8px 6.5px;
  border: none;
  border-bottom: 0.75px solid #e2e8f0;
  vertical-align: top;
}
table.data-table tbody tr:nth-child(even) { background: #f8fafc; }
table.data-table th.col-nowrap, table.data-table td.col-nowrap { white-space: nowrap; width: 1%; }
table.data-table th.col-first-min, table.data-table td.col-first-min { min-width: 15%; }
table.data-table th.col-num, table.data-table td.col-num { font-variant-numeric: tabular-nums; }
table.data-table th.ta-c, table.data-table td.ta-c { text-align: center; }
table.data-table th.ta-r, table.data-table td.ta-r { text-align: right; }
.nw { white-space: nowrap; }
.st-pill {
  display: inline-block;
  white-space: nowrap;
  font-size: 7.85pt;
  font-weight: 700;
  padding: 1.5px 7px;
  border-radius: 10px;
  line-height: 1.30;
}
.st-fail { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
.st-pass { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
.st-warn { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }

.chart-box {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-top: 2.5px solid #1e3a8a;
  border-radius: 8px;
  padding: 9px 11px 7.5px 11px;
  margin: 9.5px 0 11px 0;
  break-inside: avoid;
  page-break-inside: avoid;
}
.chart-title { font-size: 10.2pt; font-weight: 800; color: #0f172a; line-height: 1.35; margin-bottom: 2px; text-align: left; }
.chart-sub { font-size: 8.15pt; color: #64748b; margin-bottom: 4.5px; text-align: left; }
.chart-note { font-size: 7.9pt; color: #64748b; line-height: 1.44; margin-top: 4.5px; }
.footer-note { margin-top: 8px; padding-top: 5.5px; border-top: 1px solid #cbd5e1; font-size: 7.75pt; color: #64748b; text-align: center; line-height: 1.42; }
"""


_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def sanitize_hex_color(val: str, default: str = "#b45309") -> str:
    s = str(val or "").strip()
    return s if _HEX_COLOR_RE.match(s) else default


def sanitize_css_string(val: str) -> str:
    return re.sub(r'["\\\r\n]', "", str(val or "")).strip()


def count_pdf_pages(pdf_path: Path) -> int:
    try:
        raw = pdf_path.read_bytes()
        return len(re.findall(rb"/Type\s*/Page\b(?!s)", raw))
    except Exception:
        return 0


def build_cover_html(title: str, meta: dict, accent: str = "#b45309") -> str:
    tag = esc(meta.get("tag", "每日黄金深度研报 · 北京时间 07:30 & 18:00 双刊"))
    ts = esc(meta.get("timestamp", ""))
    summary = esc(meta.get("summary", ""))
    kpis = meta.get("kpis", [])

    meta_html = ""
    if ts or summary:
        line = f"<strong>基准时点</strong>：{ts}" if ts else ""
        if summary:
            line += f" &nbsp;|&nbsp; {summary}" if line else summary
        meta_html = f'<div class="cover-meta">{line}</div>'

    kpi_html = ""
    if kpis:
        cards = [
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{esc(k.get("label", ""))}</div>'
            f'<div class="kpi-val">{replace_dot_emojis(esc(k.get("val", "")))}</div>'
            f'<div class="kpi-sub">{esc(k.get("sub", ""))}</div>'
            f'</div>'
            for k in kpis[:6]
        ]
        kpi_html = f'<div class="kpi-strip">{"".join(cards)}</div>'

    return f'''
    <div class="cover-banner" style="border-bottom:4px solid {accent};">
      <div class="cover-tag">{tag}</div>
      <div class="cover-title">{md_inline(title)}</div>
      {meta_html}
      {kpi_html}
    </div>
    '''


GOLD_MOBILE_CSS = """
html { scroll-behavior: smooth; }
[id^="sec-"], #top { scroll-margin-top: 56px; }
.mob-nav, .svg-hint { display: none; }
.svg-scroll svg { display: block; width: 100%; height: auto; }
@media screen {
  html { background: #f1f5f9; }
  body {
    max-width: 820px;
    margin: 16px auto;
    padding: 18px 22px 28px 22px;
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(15, 23, 42, 0.08);
    font-size: 15.5px;
    line-height: 1.72;
  }
  .mob-nav {
    display: flex;
    align-items: center;
    gap: 6px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    position: sticky;
    top: 0;
    z-index: 40;
    background: rgba(255, 255, 255, 0.94);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    padding: 9px 12px;
    margin: -18px -22px 16px -22px;
    border-bottom: 1px solid #e2e8f0;
    border-radius: 12px 12px 0 0;
    white-space: nowrap;
  }
  .mob-nav a {
    display: inline-block;
    font-size: 12.5px;
    font-weight: 700;
    color: #334155;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    padding: 4px 11px;
    border-radius: 999px;
    text-decoration: none;
    flex: 0 0 auto;
  }
  .mob-nav a.nav-accent {
    background: __ACCENT__;
    color: #ffffff;
    border-color: __ACCENT__;
  }
  .cover-tag { font-size: 12px; padding: 3px 10px; }
  .cover-title { font-size: 21px; }
  .cover-meta, .kpi-label, .kpi-sub { font-size: 13px; }
  .kpi-val { font-size: 16px; }
  .verdict-badge { font-size: 12.5px; }
  .verdict-light { font-size: 14px; }
  .verdict-headline { font-size: 16.5px; }
  .verdict-list { font-size: 14.5px; }
  .verdict-risk { font-size: 13.5px; }
  .sn-title, .persona-title { font-size: 16px; }
  .sn-table { font-size: 14px; }
  .persona-head { font-size: 15.5px; }
  .persona-sub, .persona-avoid { font-size: 13.5px; }
  .persona-ul { font-size: 14.5px; line-height: 1.62; }
  .glossary-title, .trust-title { font-size: 15px; }
  .glossary-table, .trust-ul { font-size: 14px; }
  .trust-note, .chart-note, .footer-note { font-size: 12.5px; }
  .layer-badge-deep, .layer-badge-pro { font-size: 13.5px; }
  .vol-header { font-size: 19px; padding: 9px 14px; margin: 20px 0 10px 0; }
  h2 { font-size: 17.5px; margin: 18px 0 8px 0; }
  h3 { font-size: 16px; margin: 14px 0 6px 0; }
  h4 { font-size: 15px; }
  p { text-align: left; }
  .callout { font-size: 14.5px; padding: 11px 14px; }
  .table-wrap, .sn-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  table.data-table { font-size: 13.5px; }
  table.data-table th { font-size: 13px; padding: 7px 8px; }
  table.data-table td { padding: 7px 8px; }
  .st-pill { font-size: 12px; }
  .chart-title { font-size: 16px; }
  .chart-sub { font-size: 13.5px; }
  .inline-code { font-size: 13.5px; background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }
}
@media screen and (max-width: 680px) {
  body {
    margin: 0;
    border-radius: 0;
    box-shadow: none;
    padding: 12px calc(12px + env(safe-area-inset-right, 0px)) calc(24px + env(safe-area-inset-bottom, 0px)) calc(12px + env(safe-area-inset-left, 0px));
    font-size: 15.5px;
  }
  .mob-nav {
    margin: -12px calc(-12px - env(safe-area-inset-right, 0px)) 12px calc(-12px - env(safe-area-inset-left, 0px));
    padding-left: calc(10px + env(safe-area-inset-left, 0px));
    padding-right: calc(10px + env(safe-area-inset-right, 0px));
    border-radius: 0;
  }
  .cover-banner { padding: 14px 14px 13px 14px; }
  .cover-title { font-size: 19px; }
  .kpi-strip { grid-template-columns: repeat(2, 1fr); gap: 7px; }
  .kpi-val { font-size: 14.5px; white-space: normal; overflow: visible; text-overflow: clip; }
  .verdict-top { flex-direction: column; align-items: flex-start; gap: 5px; }
  .svg-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 4px; }
  .svg-scroll svg { min-width: 640px; width: 640px; max-width: none; height: auto; }
  .svg-hint {
    display: block;
    text-align: center;
    font-size: 11.5px;
    color: #64748b;
    margin-top: 4px;
    letter-spacing: 0.3px;
  }
  table.data-table, table.sn-table { min-width: 520px; font-size: 13.5px; }
}
@media screen and (max-width: 440px) {
  .kpi-strip { grid-template-columns: 1fr; }
}
@media (prefers-color-scheme: dark) {
  html { background: #020617; }
  body { background: #0f172a; color: #e2e8f0; box-shadow: none; }
  .mob-nav { background: rgba(15, 23, 42, 0.94); border-bottom-color: #334155; }
  .mob-nav a { background: #1e293b; color: #e2e8f0; border-color: #334155; }
  .mob-nav a.nav-accent { background: __ACCENT__; color: #ffffff; border-color: __ACCENT__; }
  .verdict-card { background: #1e293b !important; color: #e2e8f0; }
  .verdict-light { color: #f8fafc; }
  .verdict-headline { color: #fcd34d !important; }
  .verdict-risk { color: #fecaca; background: rgba(153, 27, 27, 0.38); }
  .sn-title, .persona-title, .trust-title { color: #f8fafc; }
  .sn-table td { background: #172033 !important; color: #e2e8f0; border-bottom-color: #334155; }
  .persona-card { background: #1e293b !important; color: #e2e8f0; }
  .persona-head { color: #f8fafc; }
  .persona-sub { color: #cbd5e1; }
  .persona-avoid { color: #fecaca; background: rgba(153, 27, 27, 0.38); }
  .glossary-box { background: #292012; border-color: #78350f; }
  .glossary-title { color: #fcd34d; }
  .glossary-table td { color: #e2e8f0; border-bottom-color: #78350f; }
  .glossary-table td:first-child strong { color: #fde68a; }
  .layer-badge-deep, .layer-badge-pro { color: #cbd5e1; border-bottom-color: #334155; }
  .trust-box { background: #1e293b; border-color: #334155; }
  .trust-ul { color: #cbd5e1; }
  .trust-note, .chart-sub, .chart-note, .footer-note, .svg-hint { color: #94a3b8; }
  .vol-header { background: #1e293b; color: #f8fafc; border-left-color: #60a5fa; }
  h2 { color: #f8fafc; border-bottom-color: #334155; }
  h3 { color: #93c5fd; }
  h4 { color: #e2e8f0; }
  strong { color: #f8fafc; }
  a { color: #38bdf8; }
  .inline-code { background: #1e293b; color: #93c5fd; }
  .code-block { background: #1e293b; border-color: #334155; color: #e2e8f0; }
  .callout { background: #0c2a3e; color: #bae6fd; border-left-color: #38bdf8; }
  .callout strong { color: #7dd3fc; }
  table.data-table { border-top-color: #64748b; border-bottom-color: #64748b; }
  table.data-table th { background: #1e293b; color: #f8fafc; }
  table.data-table td { border-bottom-color: #334155; color: #e2e8f0; }
  table.data-table tbody tr:nth-child(even) { background: #172033; }
  .st-fail { background: rgba(153, 27, 27, 0.35); color: #fecaca; border-color: #991b1b; }
  .st-pass { background: rgba(22, 101, 52, 0.35); color: #bbf7d0; border-color: #166534; }
  .st-warn { background: rgba(146, 64, 14, 0.35); color: #fde68a; border-color: #92400e; }
  .chart-box { background: #1e293b; border-color: #334155; border-top-color: #60a5fa; }
  .chart-title { color: #f8fafc; }
  .svg-scroll { background: #ffffff; border-radius: 6px; padding: 4px; }
}
@media print {
  .mob-nav, .svg-hint { display: none !important; }
}
"""


_DAILY_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_.*?(?:_r(\d+))?\.md$")


def _daily_sort_key(p: Path) -> tuple[str, int, int, str]:
    """Deterministic sort key (date, int(hhmm), int(rev or 1), name) so _r10 sorts after _r2."""
    m = _DAILY_FILENAME_RE.match(p.name)
    if m:
        return (m.group(1), int(m.group(2)), int(m.group(3) or 1), p.name)
    return ("0000-00-00", 0, 0, p.name)


def _is_latest_daily(md_path: Path) -> bool:
    files = sorted(
        (Path(p).resolve() for p in glob.glob(str(DAILY_DIR / "????-??-??_*.md"))),
        key=_daily_sort_key,
    )
    if not files:
        return True
    return md_path.resolve() == files[-1]


def build_gold_mobile_html(html_doc: str, meta: dict, out_path: Path | str) -> Path:
    """Build responsive single-file mobile HTML (sticky nav, viewport-fit=cover, SVG scroll, dark mode) atomically."""
    accent = sanitize_hex_color((meta or {}).get("accent", "#b45309"))
    mob = html_doc

    # 1. Inject mobile viewport meta with safe-area support
    if '<meta name="viewport"' not in mob:
        mob = mob.replace(
            '<meta charset="utf-8">',
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
            1,
        )

    # 2. Append mobile responsive & dark-mode CSS before </style>
    rendered_mob_css = GOLD_MOBILE_CSS.replace("__ACCENT__", accent)
    if "</style>" in mob:
        mob = mob.replace("</style>", f"\n{rendered_mob_css}\n</style>", 1)
    else:
        mob = mob.replace("</head>", f"<style>{rendered_mob_css}</style></head>", 1)

    # 3. Convert local workspace file:// links to relative links for portable viewing
    root_uri = f"file://{BASE_DIR}"
    mob = mob.replace(f"{root_uri}/daily/", "./").replace(f"{root_uri}/", "../")

    # 4. Inject stable section anchors for sticky quick-jump navigation
    mob = mob.replace('<div class="cover-banner"', '<div id="top" class="cover-banner"', 1)

    has_verdict = False
    if '<div class="verdict-card"' in mob:
        mob = mob.replace('<div class="verdict-card"', '<div id="sec-verdict" class="verdict-card"', 1)
        has_verdict = True

    has_wallet = False
    m_wallet = re.search(r"<h2>((?:(?!</h2>).)*(?:钱包账|10\s*万)(?:(?!</h2>).)*)</h2>", mob)
    if m_wallet:
        mob = mob[:m_wallet.start()] + f'<h2 id="sec-wallet">{m_wallet.group(1)}</h2>' + mob[m_wallet.end():]
        has_wallet = True

    has_persona = False
    m_persona = re.search(r"<h2>((?:(?!</h2>).)*对号入座(?:(?!</h2>).)*)</h2>", mob)
    if m_persona:
        mob = mob[:m_persona.start()] + f'<h2 id="sec-persona">{m_persona.group(1)}</h2>' + mob[m_persona.end():]
        has_persona = True
    elif '<div class="persona-wrap">' in mob:
        mob = mob.replace('<div class="persona-wrap">', '<div id="sec-persona" class="persona-wrap">', 1)
        has_persona = True

    has_deep = False
    m_deep = re.search(r'<h1 class="vol-header">((?:(?!</h1>).)*第二部分(?:(?!</h1>).)*)</h1>', mob)
    if m_deep:
        mob = mob[:m_deep.start()] + f'<h1 id="sec-deep" class="vol-header">{m_deep.group(1)}</h1>' + mob[m_deep.end():]
        has_deep = True
    elif '<div class="layer-badge-deep">' in mob:
        mob = mob.replace('<div class="layer-badge-deep">', '<div id="sec-deep" class="layer-badge-deep">', 1)
        has_deep = True

    has_pro = False
    m_pro = re.search(r'<h1 class="vol-header">((?:(?!</h1>).)*(?:第三部分|进阶)(?:(?!</h1>).)*)</h1>', mob)
    if m_pro:
        mob = mob[:m_pro.start()] + f'<h1 id="sec-pro" class="vol-header">{m_pro.group(1)}</h1>' + mob[m_pro.end():]
        has_pro = True
    elif '<div class="layer-badge-pro">' in mob:
        mob = mob.replace('<div class="layer-badge-pro">', '<div id="sec-pro" class="layer-badge-pro">', 1)
        has_pro = True

    # 5. Wrap 640px vector SVGs inside .svg-scroll & wrap .sn-table inside .sn-scroll for smooth phone swiping
    mob = re.sub(
        r'(?<!<div class="svg-scroll">)(<svg\b[^>]*>.*?</svg>)',
        r'<div class="svg-scroll">\1</div><div class="svg-hint">← 图表可左右滑动清晰查看 →</div>',
        mob,
        flags=re.DOTALL,
    )
    mob = re.sub(
        r'(<table class="sn-table">.*?</table>)',
        r'<div class="sn-scroll">\1</div>',
        mob,
        flags=re.DOTALL,
    )

    # 6. Prepend sticky navigation bar
    nav_links: list[str] = []
    if has_verdict:
        nav_links.append('<a href="#sec-verdict" class="nav-accent">首屏结论</a>')
    if has_wallet:
        nav_links.append('<a href="#sec-wallet">10万钱包账</a>')
    if has_persona:
        nav_links.append('<a href="#sec-persona">四类读者</a>')
    if has_deep:
        nav_links.append('<a href="#sec-deep">深度专题与图表</a>')
    if has_pro:
        nav_links.append('<a href="#sec-pro">进阶复核</a>')
    nav_links.append('<a href="#top">↑ 顶部</a>')
    nav_bar = '<nav class="mob-nav" aria-label="快捷导航">' + "".join(nav_links) + "</nav>"
    mob = mob.replace("<body>", f"<body>\n{nav_bar}", 1)

    # 7. Atomic write (.tmp + os.replace)
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    tmp_p = out_p.with_name(out_p.name + ".tmp")
    try:
        tmp_p.write_text(mob, encoding="utf-8")
        os.replace(tmp_p, out_p)
    finally:
        tmp_p.unlink(missing_ok=True)
    return out_p


def build_one(md_path: Path):
    root = str(BASE_DIR.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    from scripts.artifact_receipt import freeze_inputs, write_receipt

    frozen = None
    if md_path.resolve().is_relative_to(BASE_DIR.parent):
        frozen = freeze_inputs(md_path, inputs=(BASE_DIR / "build_daily.py", BASE_DIR / "docx_embed.py", BASE_DIR / "chart_input.py"))
    text = md_path.read_text(encoding="utf-8")
    title, meta, body_pdf, _ = md_to_html(text, docx_mode=False, break_layer3=False)
    _, _, body_docx, docx_charts = md_to_html(text, docx_mode=True, break_layer3=False)

    pdf_path = md_path.with_suffix(".pdf")
    docx_path = md_path.with_suffix(".docx")

    accent = sanitize_hex_color(meta.get("accent", "#b45309"))
    footer_title = sanitize_css_string(meta.get("footer_title", "每日黄金深度研报（07:30 & 18:00 双刊）"))
    rendered_pdf_css = (
        PDF_CSS
        .replace("__ACCENT__", accent)
        .replace("__FOOTER_TITLE__", footer_title)
    )

    ts = esc(meta.get("timestamp", ""))
    tag = esc(meta.get("tag", "每日黄金深度研报"))
    footer_note = (
        f'<div class="footer-note">'
        f'本刊（{tag}{(" · " + ts) if ts else ""}）数据均经多源官方数据库核验；投资有风险，请按家庭总资产 10%–15% 合理配置，严禁借钱或高杠杆操作。'
        f'</div>'
    )

    cover_html = build_cover_html(title, meta, accent=accent)
    pdf_html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>{esc(title)}</title><style>{rendered_pdf_css}</style></head>
<body>
{cover_html}
{body_pdf}
{footer_note}
</body></html>"""

    docx_full_html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>{esc(title)}</title></head>
<body>
{cover_html}
{body_docx}
{footer_note}
</body></html>"""

    # All temporary directories isolated inside system /tmp (zero workspace pollution!)
    work_tmp = Path(tempfile.mkdtemp(prefix="gold_daily_build_"))
    chrome_profile = work_tmp / "chrome_profile"
    png_dir = work_tmp / "pngs"
    chrome_profile.mkdir()
    png_dir.mkdir()
    tmp_pdf_html = work_tmp / "daily_print.html"
    tmp_pdf_html.write_text(pdf_html, encoding="utf-8")
    tmp_pdf_out = md_path.with_suffix(".pdf.tmp")

    try:
        # 1. Render PDF (atomic temp write + timeout + non-empty assertion)
        tmp_pdf_out.unlink(missing_ok=True)
        proc = subprocess.run(
            [
                CHROME_BIN,
                "--headless",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={chrome_profile}",
                "--no-pdf-header-footer",
                f"--print-to-pdf={tmp_pdf_out}",
                tmp_pdf_html.as_uri(),
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode != 0 or not tmp_pdf_out.exists() or tmp_pdf_out.stat().st_size < 10000:
            raise RuntimeError(
                f"Chrome headless PDF print failed for {md_path.name} (rc={proc.returncode}): {proc.stderr.strip()[:400]}"
            )
        tmp_pdf_out.replace(pdf_path)

        # 2. Rasterize every SVG chart to PIL-cropped 2x Retina PNG
        embed_specs: list[tuple[str, Path]] = []
        for idx, (marker, chart_html) in enumerate(docx_charts):
            png_out = png_dir / f"chart_{idx + 1}.png"
            render_chart_to_png(chart_html, png_out, png_dir, chrome_profile, idx)
            embed_specs.append((marker, png_out))

        # 3. Build 100% native OOXML DOCX (real tables, cross-platform cards, Retina PNGs)
        build_native_docx(docx_full_html, docx_path, embed_specs, footer_title=footer_title)
    finally:
        tmp_pdf_out.unlink(missing_ok=True)
        shutil.rmtree(work_tmp, ignore_errors=True)

    pages = count_pdf_pages(pdf_path)
    print(f"Built daily PDF:  {pdf_path} ({pages} pages)")
    print(f"Built daily DOCX: {docx_path} (native OOXML + {len(docx_charts)} PIL-cropped Retina PNG charts)")

    if _is_latest_daily(md_path):
        mobile_out = build_gold_mobile_html(pdf_html, meta, DAILY_DIR / "latest_gold.html")
        print(f"Built mobile HTML: {mobile_out} ({mobile_out.stat().st_size:,} bytes)")
    if frozen is not None:
        write_receipt(frozen, pdf_path, docx_path)


def main():
    parser = argparse.ArgumentParser(description="Build daily gold research PDF & Native OOXML DOCX (V2.2).")
    parser.add_argument("md_file", nargs="?", help="Path to target daily Markdown file (defaults to latest by filename).")
    parser.add_argument("--check", action="store_true", help="Self-check Chrome, BeautifulSoup, PIL, and daily/ dir.")
    args = parser.parse_args()

    if args.check:
        if not Path(CHROME_BIN).exists():
            raise SystemExit(f"ERROR: Chrome binary missing at {CHROME_BIN}")
        import bs4  # noqa: F401
        from PIL import Image  # noqa: F401
        DAILY_DIR.mkdir(parents=True, exist_ok=True)
        print("OK: build_daily.py V2.2 native OOXML & PDF environment verified.")
        return
    if args.md_file:
        target = Path(args.md_file)
    else:
        files = sorted(
            (Path(p) for p in glob.glob(str(DAILY_DIR / "????-??-??_*.md"))),
            key=_daily_sort_key,
        )
        if not files:
            raise SystemExit("No daily YYYY-MM-DD_*.md files found in daily/")
        target = files[-1]
    if not target.exists():
        raise SystemExit(f"ERROR: Target Markdown file not found: {target}")
    build_one(target)


if __name__ == "__main__":
    main()
