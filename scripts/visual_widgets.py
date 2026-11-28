#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-dependency declarative SVG infographic engine for Global Investment Research.

Supports four vivid, collision-checked vector chart types embedded via
`<!-- DAILY_VISUAL { ... } -->` in both Gold and Equity daily reports:
  1. `waterfall`     — P&L bridge / Treasury liquidity net-drain waterfall
  2. `bar_compare`   — Channel price ladder / central-bank odds / cross comparison
  3. `anchor_range`  — Focus stock current price vs safe-anchor ruler
  4. `flow_chain`    — Multi-step cross-asset / policy causal transmission flow

Every SVG uses explicit integer viewBox="0 0 640 H", strict text width clamping,
and non-overlapping geometry validated by scripts/svg_geometry.py.
"""

from __future__ import annotations

import html
import json
import math
import re
import unicodedata
from typing import Any

SUPPORTED_VISUAL_TYPES = frozenset({"waterfall", "bar_compare", "anchor_range", "flow_chain"})

DAILY_VISUAL_RE = re.compile(
    r"<!--\s*DAILY_VISUAL\s*(\{.*?\})\s*-->",
    re.DOTALL,
)

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

TONE_PALETTE: dict[str, dict[str, str]] = {
    "red": {"bar": "#dc2626", "bg": "#fef2f2", "border": "#fecaca", "text": "#991b1b"},
    "orange": {"bar": "#c2410c", "bg": "#fff7ed", "border": "#fed7aa", "text": "#9a3412"},
    "amber": {"bar": "#b45309", "bg": "#fffbeb", "border": "#fde68a", "text": "#92400e"},
    "green": {"bar": "#15803d", "bg": "#f0fdf4", "border": "#bbf7d0", "text": "#166534"},
    "teal": {"bar": "#0f766e", "bg": "#f0fdfa", "border": "#99f6e4", "text": "#115e59"},
    "blue": {"bar": "#1d4ed8", "bg": "#eff6ff", "border": "#bfdbfe", "text": "#1e3a8a"},
    "slate": {"bar": "#334155", "bg": "#f8fafc", "border": "#cbd5e1", "text": "#0f172a"},
}

STANCE_STYLE: dict[str, tuple[str, str, str]] = {
    "base": ("#15803d", "#f0fdf4", "#bbf7d0"),
    "lock": ("#1d4ed8", "#eff6ff", "#bfdbfe"),
    "watch": ("#b45309", "#fffbeb", "#fde68a"),
    "avoid": ("#dc2626", "#fef2f2", "#fecaca"),
}


def _esc(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=True)


def _safe_color(val: Any, default: str = "#1d4ed8") -> str:
    s = str(val or "").strip()
    return s if HEX_COLOR_RE.fullmatch(s) else default


def _char_width_u(ch: str) -> float:
    """Estimate glyph advance width in em units aligned with scripts/svg_geometry.py."""
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):
        return 1.0
    if ch == " ":
        return 0.28
    if ch in "ilI.,:;|!'\"`":
        return 0.30
    if ch in "fjrt()-/\\[]{}·":
        return 0.38
    if ch in "MW":
        return 0.82
    if ch in "%@":
        return 0.78
    if ch == "—":
        return 0.95
    if ch == "–":
        return 0.55
    if "A" <= ch <= "Z":
        return 0.64
    if "0" <= ch <= "9":
        return 0.56
    if "a" <= ch <= "z":
        return 0.52
    if ch in "$+-=<>?~*^&#_":
        return 0.56
    if ord(ch) >= 0x2000:
        return 0.75
    return 0.55


def _vis_width_units(text: str) -> float:
    return sum(_char_width_u(ch) for ch in text)


def _est_px(text: str, font_size: float, *, bold: bool = False) -> float:
    if not text:
        return 0.0
    return _vis_width_units(text) * font_size * (1.04 if bold else 1.0)


def _clip_text(text: str, max_units: float) -> str:
    s = str(text or "").strip()
    if _vis_width_units(s) <= max_units:
        return s
    out: list[str] = []
    acc = 0.0
    ell_u = _char_width_u("…")
    limit = max(0.8, max_units - ell_u - 0.05)
    for ch in s:
        u = _char_width_u(ch)
        if acc + u > limit:
            break
        out.append(ch)
        acc += u
    return "".join(out).rstrip(" ，,；;·") + "…"


def _wrap_lines(text: str, max_units: float, max_lines: int = 2) -> list[str]:
    s = str(text or "").strip()
    if not s:
        return []
    lines: list[str] = []
    cur: list[str] = []
    acc = 0.0
    truncated = False
    for idx, ch in enumerate(s):
        u = _char_width_u(ch)
        if acc + u > max_units and cur:
            lines.append("".join(cur).strip())
            if len(lines) >= max_lines:
                if s[idx:].strip():
                    truncated = True
                cur = []
                break
            cur = [ch] if ch != " " else []
            acc = u if ch != " " else 0.0
        else:
            cur.append(ch)
            acc += u
    if len(lines) < max_lines and cur:
        lines.append("".join(cur).strip())
    if truncated and lines:
        lines[-1] = _clip_text(lines[-1] + "…", max_units)
    elif lines and _vis_width_units(lines[-1]) > max_units:
        lines[-1] = _clip_text(lines[-1], max_units)
    return [ln for ln in lines if ln]


def _is_finite_number(val: Any) -> bool:
    if isinstance(val, bool) or val is None:
        return False
    try:
        v = float(val)
        return math.isfinite(v)
    except (TypeError, ValueError):
        return False


def _safe_float(val: Any, default: float = 0.0) -> float:
    if isinstance(val, bool) or val is None:
        return default
    try:
        v = float(val)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def validate_visual_spec(data: Any) -> list[str]:
    """Validate a DAILY_VISUAL JSON payload before rendering."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["DAILY_VISUAL 须为 JSON 对象"]
    vtype = str(data.get("type") or "").strip().lower()
    if vtype not in SUPPORTED_VISUAL_TYPES:
        errs.append(f"DAILY_VISUAL.type 非法 ({vtype!r})，仅支持 {sorted(SUPPORTED_VISUAL_TYPES)}")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        errs.append("DAILY_VISUAL 缺少非空 title")
    if vtype == "waterfall":
        bars = data.get("bars")
        if not isinstance(bars, list) or not (2 <= len(bars) <= 8):
            errs.append("DAILY_VISUAL(waterfall) 须包含 2–8 根 bars")
        else:
            for idx, b in enumerate(bars):
                if not isinstance(b, dict) or not str(b.get("label") or "").strip():
                    errs.append(f"DAILY_VISUAL(waterfall).bars[{idx}] 缺少 label")
                if not isinstance(b, dict) or not _is_finite_number(b.get("value")):
                    errs.append(f"DAILY_VISUAL(waterfall).bars[{idx}] value 须为有限数值")
        bench = data.get("benchmark")
        if isinstance(bench, dict) and bench.get("value") is not None and not _is_finite_number(bench.get("value")):
            errs.append("DAILY_VISUAL(waterfall).benchmark.value 须为有限数值")
    elif vtype == "bar_compare":
        items = data.get("items")
        if not isinstance(items, list) or len(items) < 2:
            errs.append("DAILY_VISUAL(bar_compare) 须包含至少 2 项 items")
        else:
            for idx, it in enumerate(items):
                if not isinstance(it, dict) or not str(it.get("label") or "").strip():
                    errs.append(f"DAILY_VISUAL(bar_compare).items[{idx}] 缺少 label")
                if not isinstance(it, dict) or not _is_finite_number(it.get("value")):
                    errs.append(f"DAILY_VISUAL(bar_compare).items[{idx}] value 须为有限数值")
        for opt_k in ("min_val", "max_val"):
            if data.get(opt_k) is not None and not _is_finite_number(data.get(opt_k)):
                errs.append(f"DAILY_VISUAL(bar_compare).{opt_k} 须为有限数值")
        thresh = data.get("threshold")
        if isinstance(thresh, dict) and thresh.get("val") is not None and not _is_finite_number(thresh.get("val")):
            errs.append("DAILY_VISUAL(bar_compare).threshold.val 须为有限数值")
    elif vtype == "anchor_range":
        items = data.get("items")
        if not isinstance(items, list) or not items:
            errs.append("DAILY_VISUAL(anchor_range) 须包含至少 1 项 items")
        else:
            for idx, it in enumerate(items):
                if not isinstance(it, dict) or not str(it.get("name") or "").strip():
                    errs.append(f"DAILY_VISUAL(anchor_range).items[{idx}] 缺少 name")
                if not isinstance(it, dict):
                    continue
                ok_nums = True
                for k in ("current", "anchor_low", "anchor_high"):
                    if not _is_finite_number(it.get(k)):
                        errs.append(f"DAILY_VISUAL(anchor_range).items[{idx}].{k} 须为有限数值")
                        ok_nums = False
                if ok_nums and float(it["anchor_low"]) > float(it["anchor_high"]):
                    errs.append(
                        f"DAILY_VISUAL(anchor_range).items[{idx}] anchor_low ({it['anchor_low']}) 不得大于 anchor_high ({it['anchor_high']})"
                    )
    elif vtype == "flow_chain":
        steps = data.get("steps")
        if not isinstance(steps, list) or not (3 <= len(steps) <= 6):
            errs.append("DAILY_VISUAL(flow_chain) 须包含 3–6 个 steps 节点")
        else:
            for idx, st in enumerate(steps):
                if not isinstance(st, dict) or not str(st.get("title") or "").strip():
                    errs.append(f"DAILY_VISUAL(flow_chain).steps[{idx}] 缺少 title")
    return errs


def _wrap_chart_box(title: str, subtitle: str, svg_inner: str, vb_h: int, takeaway: str = "", note: str = "") -> str:
    sub_html = f'<div class="chart-sub">{_esc(subtitle)}</div>' if subtitle else ""
    tk_html = f'<div class="vchart-takeaway"><strong>一图看懂：</strong>{_esc(takeaway)}</div>' if takeaway else ""
    note_html = f'<div class="chart-note">{_esc(note)}</div>' if note else ""
    return (
        '<div class="chart-box visual-chart-box">'
        f'<div class="chart-title">{_esc(title)}</div>'
        f"{sub_html}"
        f'<svg viewBox="0 0 640 {vb_h}" width="640" height="{vb_h}" '
        'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{_esc(title)}" style="max-width:100%;height:auto;display:block;margin:6px auto 0;">'
        f"{svg_inner}"
        "</svg>"
        f"{tk_html}"
        f"{note_html}"
        "</div>"
    )


def _render_waterfall(data: dict[str, Any]) -> str:
    title = str(data.get("title") or "关键数据瀑布拆解")
    subtitle = str(data.get("subtitle") or "")
    note = str(data.get("note") or "")
    takeaway = str(data.get("takeaway") or "")
    unit = str(data.get("unit") or "")
    bars = [b for b in (data.get("bars") or []) if isinstance(b, dict)]
    n = len(bars)

    # Compute running bridge coordinates (y0, y1) for each bar
    running = 0.0
    segments: list[dict[str, Any]] = []
    min_y = 0.0
    max_y = 0.0
    for idx, b in enumerate(bars):
        val = _safe_float(b.get("value"))
        kind = str(b.get("kind") or ("start" if idx == 0 else "add")).strip().lower()
        if kind == "start":
            y0, y1 = 0.0, val
            running = val
        elif kind == "total":
            y0, y1 = 0.0, val
            running = val
        elif kind == "compare":
            y0, y1 = 0.0, val
        elif kind == "sub":
            delta = -abs(val)
            y0, y1 = running, running + delta
            running = y1
        else:  # add / delta
            y0, y1 = running, running + val
            running = y1
        min_y = min(min_y, y0, y1)
        max_y = max(max_y, y0, y1)
        segments.append({"bar": b, "kind": kind, "val": val, "y0": y0, "y1": y1})

    bench = data.get("benchmark") if isinstance(data.get("benchmark"), dict) else None
    if bench is not None and bench.get("value") is not None:
        bv = _safe_float(bench.get("value"))
        min_y = min(min_y, bv)
        max_y = max(max_y, bv)

    span = max(max_y - min_y, 1.0)
    pad_top = span * 0.24
    pad_bot = span * (0.24 if min_y < 0 else 0.06)
    dom_min = min_y - pad_bot if min_y < 0 else 0.0
    dom_max = max_y + pad_top

    vb_h = 286
    plot_l, plot_r = 56.0, 618.0
    plot_t, plot_b = 26.0, 206.0
    plot_w = plot_r - plot_l
    plot_h = plot_b - plot_t

    def y_px(v: float) -> float:
        return plot_b - (v - dom_min) / max(dom_max - dom_min, 1e-6) * plot_h

    svg: list[str] = [
        f'<rect x="0" y="0" width="640" height="{vb_h}" rx="10" fill="#ffffff" stroke="#e2e8f0" stroke-width="1"/>',
    ]

    # Grid lines (4 clean levels)
    for gi in range(5):
        gv = dom_min + (dom_max - dom_min) * (gi / 4.0)
        gy = y_px(gv)
        svg.append(f'<line x1="{plot_l:.1f}" y1="{gy:.1f}" x2="{plot_r:.1f}" y2="{gy:.1f}" stroke="#f1f5f9" stroke-width="1"/>')
        lbl_g = f"{gv:.0f}" if abs(dom_max - dom_min) >= 15 else f"{gv:.1f}"
        lbl_g = _clip_text(lbl_g, (plot_l - 12.0) / 9.5)
        svg.append(
            f'<text x="{plot_l - 8:.1f}" y="{gy + 3.5:.1f}" text-anchor="end" '
            f'font-size="9.5" fill="#64748b" font-family="sans-serif">{_esc(lbl_g)}</text>'
        )

    # Zero baseline
    y_zero = y_px(0.0)
    svg.append(f'<line x1="{plot_l:.1f}" y1="{y_zero:.1f}" x2="{plot_r:.1f}" y2="{y_zero:.1f}" stroke="#94a3b8" stroke-width="1.2"/>')

    slot_w = plot_w / max(n, 1)
    bar_w = min(64.0, slot_w * 0.54)

    # Pre-compute optional benchmark pill bounding box so value labels guarantee zero collision
    bench_info: tuple[float, float, float, float, float, str, str] | None = None
    if bench is not None and bench.get("value") is not None:
        bv = _safe_float(bench.get("value"))
        by = y_px(bv)
        bcol = _safe_color(bench.get("color"), "#dc2626")
        blbl = _clip_text(str(bench.get("label") or f"基准 {bv}"), 14.0)
        pill_w = min(148.0, max(64.0, _est_px(blbl, 9.2, bold=True) + 14.0))
        b_px = plot_r - pill_w
        b_py = max(plot_t + 2.0, min(plot_b - 17.0, by - 17.0))
        bench_info = (by, b_px, b_py, pill_w, 15.0, bcol, blbl)

    def _box_collides_bench(vx0: float, vy0: float, vx1: float, vy1: float) -> bool:
        if bench_info is None:
            return False
        _, b_px, b_py, b_pw, b_ph, _, _ = bench_info
        ox = min(vx1, b_px + b_pw + 2.0) - max(vx0, b_px - 2.0)
        oy = min(vy1, b_py + b_ph + 2.0) - max(vy0, b_py - 2.0)
        return ox > 0.0 and oy > 0.0

    prev_right_x: float | None = None
    prev_end_y: float | None = None

    for idx, seg in enumerate(segments):
        b = seg["bar"]
        kind = seg["kind"]
        y0_px = y_px(seg["y0"])
        y1_px = y_px(seg["y1"])
        top_y = min(y0_px, y1_px)
        bot_y = max(y0_px, y1_px)
        rect_h = max(3.0, bot_y - top_y)
        cx = plot_l + slot_w * (idx + 0.5)
        bx = cx - bar_w / 2.0

        # Dashed connector from previous step (skip for compare bars)
        if prev_right_x is not None and prev_end_y is not None and kind != "compare":
            svg.append(
                f'<line x1="{prev_right_x:.1f}" y1="{prev_end_y:.1f}" x2="{bx:.1f}" y2="{prev_end_y:.1f}" '
                'stroke="#94a3b8" stroke-width="1" stroke-dasharray="3,2"/>'
            )

        default_col = {
            "start": "#1e3a8a",
            "add": "#c2410c",
            "sub": "#0f766e",
            "total": "#b45309",
            "compare": "#64748b",
        }.get(kind, "#1d4ed8")
        fill_col = _safe_color(b.get("color"), default_col)
        dash_attr = ' stroke-dasharray="4,2" fill-opacity="0.22" stroke-width="1.5"' if kind == "compare" else ""
        stroke_col = fill_col if kind == "compare" else "none"

        svg.append(
            f'<rect x="{bx:.1f}" y="{top_y:.1f}" width="{bar_w:.1f}" height="{rect_h:.1f}" '
            f'rx="4" fill="{fill_col}" stroke="{stroke_col}"{dash_attr}/>'
        )

        # Value label: exact precedence for custom val_label + minus sign on sub + collision-safe placement
        disp_val = -abs(seg["val"]) if kind == "sub" else seg["val"]
        default_lbl = f"{disp_val:+.2f}{unit}" if kind in ("add", "sub") else f"{disp_val:.2f}{unit}"
        raw_val_lbl = b.get("val_label")
        v_raw = str(raw_val_lbl).strip() if (raw_val_lbl is not None and str(raw_val_lbl).strip()) else default_lbl
        val_max_u = min(11.0, max(4.2, (slot_w - 6.0) / (10.5 * 1.04)))
        v_txt = _clip_text(v_raw, val_max_u)
        v_w = _est_px(v_txt, 10.5, bold=True)
        val_x = max(plot_l + v_w / 2.0, min(plot_r - v_w / 2.0, cx))
        vx0, vx1 = val_x - v_w / 2.0, val_x + v_w / 2.0

        is_neg_bar = (seg["y1"] < 0 and seg["y0"] <= 0) or (seg["y1"] < seg["y0"] and seg["y1"] < 0)
        cand_positions: list[tuple[float, str]] = []
        if is_neg_bar:
            cand_positions.append((min(plot_b - 3.0, bot_y + 13.0), fill_col))
            if rect_h >= 24.0 and kind != "compare":
                cand_positions.append((bot_y - 7.0, "#ffffff"))
            cand_positions.append((max(15.0, top_y - 7.0), fill_col))
        else:
            cand_positions.append((max(15.0, top_y - 7.0), fill_col))
            if rect_h >= 24.0 and kind != "compare":
                cand_positions.append((top_y + 17.0, "#ffffff"))
            cand_positions.append((min(plot_b - 3.0, bot_y + 13.0), fill_col))
        if bench_info is not None:
            _, _, b_py, _, b_ph, _, _ = bench_info
            if b_py - 5.0 >= 13.0:
                cand_positions.append((b_py - 5.0, fill_col))
            if b_py + b_ph + 13.0 <= plot_b - 3.0:
                inside_dark = (
                    kind != "compare"
                    and rect_h >= 24.0
                    and (top_y + 10.0) <= (b_py + b_ph + 13.0) <= (bot_y - 3.0)
                )
                cand_positions.append((b_py + b_ph + 13.0, "#ffffff" if inside_dark else fill_col))

        val_y, val_fill = cand_positions[0]
        for cy_cand, cf_cand in cand_positions:
            if not _box_collides_bench(vx0, cy_cand - 10.5 * 0.82, vx1, cy_cand + 10.5 * 0.18):
                val_y, val_fill = cy_cand, cf_cand
                break

        svg.append(
            f'<text x="{val_x:.1f}" y="{val_y:.1f}" text-anchor="middle" font-size="10.5" '
            f'font-weight="700" fill="{val_fill}" font-family="sans-serif">{_esc(v_txt)}</text>'
        )

        # X-axis label (up to 2 crisp wrapped lines + optional tag)
        max_u = max(3.4, (slot_w - 6.0) / (10.0 * 1.04))
        lbl_lines = _wrap_lines(str(b.get("label") or ""), max_units=max_u, max_lines=2)
        for li, ltxt in enumerate(lbl_lines):
            ly = plot_b + 16.0 + li * 13.5
            svg.append(
                f'<text x="{cx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="10" '
                f'font-weight="700" fill="#1e293b" font-family="sans-serif">{_esc(ltxt)}</text>'
            )
        tag = str(b.get("tag") or "").strip()
        if tag:
            tag_max_u = max(3.6, (slot_w - 6.0) / 9.0)
            tag_clipped = _clip_text(tag, tag_max_u)
            ty = plot_b + 16.0 + len(lbl_lines) * 13.5 + 3.0
            svg.append(
                f'<text x="{cx:.1f}" y="{min(vb_h - 10.0, ty):.1f}" text-anchor="middle" font-size="9" '
                f'fill="#64748b" font-family="sans-serif">{_esc(tag_clipped)}</text>'
            )

        if kind != "compare":
            prev_right_x = bx + bar_w
            prev_end_y = y1_px

    # Optional benchmark horizontal reference line (drawn above bars for clear visibility)
    if bench_info is not None:
        by, b_px, b_py, pill_w, pill_h, bcol, blbl = bench_info
        svg.append(
            f'<line x1="{plot_l:.1f}" y1="{by:.1f}" x2="{plot_r:.1f}" y2="{by:.1f}" '
            f'stroke="{bcol}" stroke-width="1.3" stroke-dasharray="5,3"/>'
        )
        svg.append(
            f'<rect x="{b_px:.1f}" y="{b_py:.1f}" width="{pill_w:.1f}" height="{pill_h:.0f}" rx="4" '
            f'fill="#ffffff" fill-opacity="0.94" stroke="{bcol}" stroke-width="0.9"/>'
        )
        svg.append(
            f'<text x="{b_px + pill_w / 2.0:.1f}" y="{b_py + 10.8:.1f}" text-anchor="middle" '
            f'font-size="9.2" font-weight="700" fill="{bcol}" font-family="sans-serif">{_esc(blbl)}</text>'
        )

    return _wrap_chart_box(title, subtitle, "".join(svg), vb_h, takeaway=takeaway, note=note)


def _render_bar_compare(data: dict[str, Any]) -> str:
    title = str(data.get("title") or "多维对比阶梯图")
    subtitle = str(data.get("subtitle") or "")
    note = str(data.get("note") or "")
    takeaway = str(data.get("takeaway") or "")
    callout_badge = str(data.get("callout_badge") or "").strip()
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]

    vals = [_safe_float(it.get("value")) for it in items]
    has_neg = any(v < 0 for v in vals)
    raw_min = min(vals) if vals else 0.0
    raw_max = max(vals) if vals else 1.0
    if data.get("min_val") is not None and _is_finite_number(data.get("min_val")):
        min_v = _safe_float(data.get("min_val"))
    else:
        min_v = min(0.0, raw_min) if has_neg else 0.0
    if data.get("max_val") is not None and _is_finite_number(data.get("max_val")):
        max_v = _safe_float(data.get("max_val"))
    else:
        max_v = max(0.0, raw_max) if has_neg else max(raw_max, 1.0)
    if max_v <= min_v:
        max_v = min_v + 1.0

    thresh = data.get("threshold") if isinstance(data.get("threshold"), dict) else None
    has_thresh_lbl = bool(thresh is not None and thresh.get("val") is not None and str(thresh.get("label") or "").strip())

    row_h = 34.0
    top_pad = 38.0 if callout_badge else 16.0
    bot_pad = 22.0 if has_thresh_lbl else 16.0
    vb_h = int(top_pad + len(items) * row_h + bot_pad)

    lbl_x = 146.0
    bar_l = 156.0
    bar_max_w = 248.0
    val_x = bar_l + bar_max_w + 8.0
    tag_x = 496.0
    val_max_u_with_tag = (tag_x - val_x - 8.0) / (10.5 * 1.04)
    val_max_u_no_tag = (626.0 - val_x) / (10.5 * 1.04)
    tag_max_u = (628.0 - tag_x) / 9.5

    svg: list[str] = [
        f'<rect x="0" y="0" width="640" height="{vb_h}" rx="10" fill="#ffffff" stroke="#e2e8f0" stroke-width="1"/>',
    ]

    if callout_badge:
        cb = _clip_text(callout_badge, 46.0)
        svg.append('<rect x="14" y="8" width="612" height="22" rx="6" fill="#fffbeb" stroke="#fde68a" stroke-width="1"/>')
        svg.append(
            f'<text x="320" y="22.5" text-anchor="middle" font-size="10.5" font-weight="700" '
            f'fill="#92400e" font-family="sans-serif">{_esc(cb)}</text>'
        )

    diverging = min_v < 0.0 <= max_v
    zero_x = bar_l + ((0.0 - min_v) / max(max_v - min_v, 1e-6)) * bar_max_w if diverging else bar_l

    for idx, it in enumerate(items):
        ry = top_pad + idx * row_h
        cy = ry + row_h / 2.0
        hi = bool(it.get("highlight"))
        if hi:
            svg.append(
                f'<rect x="10" y="{ry + 2:.1f}" width="620" height="{row_h - 4:.1f}" rx="6" '
                'fill="#fff7ed" stroke="#fed7aa" stroke-width="0.9"/>'
            )
        elif idx % 2 == 1:
            svg.append(
                f'<rect x="10" y="{ry + 2:.1f}" width="620" height="{row_h - 4:.1f}" rx="6" fill="#f8fafc"/>'
            )

        lbl = _clip_text(str(it.get("label") or ""), 12.0)
        svg.append(
            f'<text x="{lbl_x:.1f}" y="{cy + 4:.1f}" text-anchor="end" font-size="10.5" '
            f'font-weight="{"700" if hi else "600"}" fill="#0f172a" font-family="sans-serif">{_esc(lbl)}</text>'
        )

        # Background track
        svg.append(f'<rect x="{bar_l:.1f}" y="{cy - 8:.1f}" width="{bar_max_w:.1f}" height="16" rx="4" fill="#eef2f7"/>')

        v = _safe_float(it.get("value"))
        bcol = _safe_color(it.get("color"), "#c2410c" if hi else ("#0f766e" if v < 0 else "#1d4ed8"))
        if diverging:
            vx = bar_l + max(0.0, min(1.0, (v - min_v) / max(max_v - min_v, 1e-6))) * bar_max_w
            if v >= 0:
                bx = zero_x
                bw = max(3.0, min(bar_l + bar_max_w - zero_x, vx - zero_x))
            else:
                bw = max(3.0, min(zero_x - bar_l, zero_x - vx))
                bx = max(bar_l, zero_x - bw)
            svg.append(f'<rect x="{bx:.1f}" y="{cy - 8:.1f}" width="{bw:.1f}" height="16" rx="4" fill="{bcol}"/>')
        else:
            frac = max(0.03, min(1.0, (v - min_v) / max(max_v - min_v, 1e-6)))
            bw = frac * bar_max_w
            svg.append(f'<rect x="{bar_l:.1f}" y="{cy - 8:.1f}" width="{bw:.1f}" height="16" rx="4" fill="{bcol}"/>')

        tag = _clip_text(str(it.get("tag") or ""), tag_max_u)
        v_raw_lbl = it.get("val_label")
        v_base = str(v_raw_lbl).strip() if (v_raw_lbl is not None and str(v_raw_lbl).strip()) else f"{v:g}"
        v_lbl = _clip_text(v_base, val_max_u_with_tag if tag else val_max_u_no_tag)
        svg.append(
            f'<text x="{val_x:.1f}" y="{cy + 4:.1f}" text-anchor="start" font-size="10.5" '
            f'font-weight="700" fill="{bcol}" font-family="sans-serif">{_esc(v_lbl)}</text>'
        )

        if tag:
            svg.append(
                f'<text x="{tag_x:.1f}" y="{cy + 3.5:.1f}" text-anchor="start" font-size="9.5" '
                f'fill="#475569" font-family="sans-serif">{_esc(tag)}</text>'
            )

    if diverging:
        svg.append(
            f'<line x1="{zero_x:.1f}" y1="{top_pad:.1f}" x2="{zero_x:.1f}" y2="{top_pad + len(items) * row_h:.1f}" '
            'stroke="#64748b" stroke-width="1.1"/>'
        )

    # Optional vertical threshold line rendered ABOVE bars & row zebra fills for clear visibility
    if thresh is not None and thresh.get("val") is not None:
        tv = _safe_float(thresh.get("val"))
        ratio = max(0.0, min(1.0, (tv - min_v) / max(max_v - min_v, 1e-6)))
        tx = bar_l + ratio * bar_max_w
        tcol = _safe_color(thresh.get("color"), "#dc2626")
        line_y2 = top_pad + len(items) * row_h + 2.0
        svg.append(
            f'<line x1="{tx:.1f}" y1="{top_pad - 2:.1f}" x2="{tx:.1f}" y2="{line_y2:.1f}" '
            f'stroke="{tcol}" stroke-width="1.4" stroke-dasharray="4,3"/>'
        )
        tlbl = _clip_text(str(thresh.get("label") or ""), 14.0)
        if tlbl:
            tlbl_half = _est_px(tlbl, 9.0, bold=True) / 2.0 + 4.0
            tlbl_x = max(14.0 + tlbl_half, min(626.0 - tlbl_half, tx))
            svg.append(
                f'<text x="{tlbl_x:.1f}" y="{vb_h - 5.0:.1f}" text-anchor="middle" font-size="9" '
                f'font-weight="700" fill="{tcol}" font-family="sans-serif">{_esc(tlbl)}</text>'
            )

    return _wrap_chart_box(title, subtitle, "".join(svg), vb_h, takeaway=takeaway, note=note)


def _render_anchor_range(data: dict[str, Any]) -> str:
    title = str(data.get("title") or "标的现价 vs 安全锚距离尺")
    subtitle = str(data.get("subtitle") or "")
    note = str(data.get("note") or "")
    takeaway = str(data.get("takeaway") or "")
    col_left_label = _clip_text(str(data.get("col_left_label") or "标的与阵营"), 12.0)
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]

    row_h = 54.0
    top_pad = 30.0
    bot_pad = 14.0
    vb_h = int(top_pad + len(items) * row_h + bot_pad)

    track_l = 166.0
    track_w = 276.0
    track_r = track_l + track_w
    right_x = 456.0

    svg: list[str] = [
        f'<rect x="0" y="0" width="640" height="{vb_h}" rx="10" fill="#ffffff" stroke="#e2e8f0" stroke-width="1"/>',
        # Column headers
        f'<text x="16" y="19" font-size="9.5" font-weight="700" fill="#64748b" font-family="sans-serif">{_esc(col_left_label)}</text>',
        f'<text x="{track_l + track_w / 2:.1f}" y="19" text-anchor="middle" font-size="9.5" font-weight="700" fill="#64748b" font-family="sans-serif">绿带 = 左侧安全锚区 ｜ 圆点 = 最新现价位置</text>',
        f'<text x="{right_x:.1f}" y="19" font-size="9.5" font-weight="700" fill="#64748b" font-family="sans-serif">偏离度与实操纪律</text>',
        '<line x1="12" y1="25" x2="628" y2="25" stroke="#e2e8f0" stroke-width="1"/>',
    ]

    for idx, it in enumerate(items):
        ry = top_pad + idx * row_h
        cy = ry + row_h / 2.0
        if idx % 2 == 1:
            svg.append(f'<rect x="10" y="{ry + 2:.1f}" width="620" height="{row_h - 4:.1f}" rx="6" fill="#f8fafc"/>')

        stance = str(it.get("stance") or "watch").strip().lower()
        st_fg, st_bg, st_bd = STANCE_STYLE.get(stance, STANCE_STYLE["watch"])
        st_lbl = _clip_text(str(it.get("stance_label") or "观察"), 5.0)
        pw = max(44.0, _est_px(st_lbl, 9.0, bold=True) + 10.0)
        pill_left = 154.0 - pw
        name_max_u = min(6.5, max(3.5, (pill_left - 20.0) / (11.0 * 1.04)))
        name = _clip_text(str(it.get("name") or ""), name_max_u)
        code = _clip_text(str(it.get("code") or ""), 13.5)

        svg.append(
            f'<text x="16" y="{ry + 20:.1f}" font-size="11" font-weight="700" fill="#0f172a" font-family="sans-serif">{_esc(name)}</text>'
        )
        svg.append(
            f'<text x="16" y="{ry + 36:.1f}" font-size="9.2" fill="#64748b" font-family="sans-serif">{_esc(code)}</text>'
        )
        # Compact stance pill
        svg.append(
            f'<rect x="{pill_left:.1f}" y="{ry + 11:.1f}" width="{pw:.1f}" height="17" rx="4" '
            f'fill="{st_bg}" stroke="{st_bd}" stroke-width="0.9"/>'
        )
        svg.append(
            f'<text x="{154.0 - pw / 2:.1f}" y="{ry + 22.8:.1f}" text-anchor="middle" font-size="9" '
            f'font-weight="700" fill="{st_fg}" font-family="sans-serif">{_esc(st_lbl)}</text>'
        )

        # Compute local normalized track scale containing anchor_low, anchor_high, and current
        cur = _safe_float(it.get("current"))
        alo = _safe_float(it.get("anchor_low"))
        ahi = _safe_float(it.get("anchor_high"))
        if alo > ahi:
            alo, ahi = ahi, alo
        lo_all = min(alo, cur)
        hi_all = max(ahi, cur)
        span = max(hi_all - lo_all, max(abs(cur) * 0.12, 1.0))
        d_min = lo_all - span * 0.16
        d_max = hi_all + span * 0.16

        def x_pos(val: float) -> float:
            return track_l + max(0.0, min(1.0, (val - d_min) / max(d_max - d_min, 1e-6))) * track_w

        ax1 = x_pos(alo)
        ax2 = max(ax1 + 10.0, x_pos(ahi))
        if ax2 > track_r:
            ax2 = track_r
            ax1 = min(ax1, max(track_l, ax2 - 10.0))
        cx = max(track_l, min(track_r, x_pos(cur)))

        # Base ruler track
        svg.append(f'<rect x="{track_l:.1f}" y="{cy - 4:.1f}" width="{track_w:.1f}" height="8" rx="4" fill="#e2e8f0"/>')
        # Safe anchor green zone
        svg.append(
            f'<rect x="{ax1:.1f}" y="{cy - 6:.1f}" width="{ax2 - ax1:.1f}" height="12" rx="4" '
            'fill="#dcfce7" stroke="#16a34a" stroke-width="1.3"/>'
        )
        # Anchor range text cleanly BELOW track, clipped and clamped inside [track_l, right_x - 8]
        unit = str(it.get("unit") or "")
        a_max_u = (right_x - 8.0 - track_l - 6.0) / (8.8 * 1.04)
        a_raw = f"锚 {alo:g}–{ahi:g}{unit}" if alo != ahi else f"锚 {alo:g}{unit}"
        a_txt = _clip_text(a_raw, min(26.0, a_max_u))
        a_half = _est_px(a_txt, 8.8, bold=True) / 2.0 + 3.0
        a_cx = max(track_l + a_half, min(right_x - 8.0 - a_half, (ax1 + ax2) / 2.0))
        svg.append(
            f'<text x="{a_cx:.1f}" y="{cy + 19.5:.1f}" text-anchor="middle" font-size="8.8" '
            f'font-weight="600" fill="#15803d" font-family="sans-serif">{_esc(a_txt)}</text>'
        )

        # Current price pin + label ABOVE track, clipped and clamped inside [track_l, right_x - 8]
        above_anchor = cur > ahi
        pin_col = "#dc2626" if (stance == "avoid" or above_anchor) else "#0f766e"
        svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5.5" fill="{pin_col}" stroke="#ffffff" stroke-width="1.8"/>')
        p_max_u = (right_x - 8.0 - track_l - 6.0) / (9.5 * 1.04)
        p_txt = _clip_text(f"现 {cur:g}{unit}", min(24.0, p_max_u))
        p_half = _est_px(p_txt, 9.5, bold=True) / 2.0 + 3.0
        p_cx = max(track_l + p_half, min(right_x - 8.0 - p_half, cx))
        svg.append(
            f'<text x="{p_cx:.1f}" y="{cy - 11.5:.1f}" text-anchor="middle" font-size="9.5" '
            f'font-weight="700" fill="{pin_col}" font-family="sans-serif">{_esc(p_txt)}</text>'
        )

        # Right column: gap & discipline hint
        gap_lbl = _clip_text(str(it.get("gap_label") or ""), (632.0 - right_x) / (10.2 * 1.04))
        hint = _clip_text(str(it.get("hint") or ""), (632.0 - right_x) / 9.2)
        svg.append(
            f'<text x="{right_x:.1f}" y="{ry + 21:.1f}" font-size="10.2" font-weight="700" '
            f'fill="{pin_col}" font-family="sans-serif">{_esc(gap_lbl)}</text>'
        )
        if hint:
            svg.append(
                f'<text x="{right_x:.1f}" y="{ry + 37:.1f}" font-size="9.2" '
                f'fill="#475569" font-family="sans-serif">{_esc(hint)}</text>'
            )

    return _wrap_chart_box(title, subtitle, "".join(svg), vb_h, takeaway=takeaway, note=note)


def _render_flow_chain(data: dict[str, Any]) -> str:
    title = str(data.get("title") or "跨资产因果传导链")
    subtitle = str(data.get("subtitle") or "")
    note = str(data.get("note") or "")
    takeaway = str(data.get("takeaway") or "")
    steps = [s for s in (data.get("steps") or []) if isinstance(s, dict)][:6]
    n = len(steps)

    # Layout: <=3 steps single row; 4..6 steps clean 2-row flow (row1 up to 3, row2 rest)
    row1 = steps[:3] if n > 3 else steps
    row2 = steps[3:] if n > 3 else []
    card_h = 98.0
    row_gap = 28.0
    pad_x = 14.0
    top_y = 14.0
    vb_h = int(top_y + card_h + (row_gap + card_h if row2 else 0.0) + 14.0)

    svg: list[str] = [
        f'<rect x="0" y="0" width="640" height="{vb_h}" rx="10" fill="#ffffff" stroke="#e2e8f0" stroke-width="1"/>',
    ]

    def draw_row(row_steps: list[dict[str, Any]], ry: float, start_idx: int) -> list[tuple[float, float]]:
        cnt = len(row_steps)
        arrow_gap = 22.0
        usable_w = 640.0 - 2 * pad_x - max(0, cnt - 1) * arrow_gap
        cw = usable_w / max(cnt, 1)
        inner_w = max(60.0, cw - 20.0)
        step_max_u = min(10.0, inner_w / (9.0 * 1.04))
        title_max_u = inner_w / (10.8 * 1.04)
        metric_max_u = inner_w / (11.2 * 1.04)
        desc_max_u = inner_w / 9.2
        centers: list[tuple[float, float]] = []
        for i, st in enumerate(row_steps):
            cx_l = pad_x + i * (cw + arrow_gap)
            tone_k = str(st.get("tone") or "blue").strip().lower()
            pal = TONE_PALETTE.get(tone_k, TONE_PALETTE["blue"])
            # Card box + top color bar
            svg.append(
                f'<rect x="{cx_l:.1f}" y="{ry:.1f}" width="{cw:.1f}" height="{card_h:.1f}" rx="8" '
                f'fill="{pal["bg"]}" stroke="{pal["border"]}" stroke-width="1.1"/>'
            )
            svg.append(
                f'<rect x="{cx_l:.1f}" y="{ry:.1f}" width="{cw:.1f}" height="5" rx="3" fill="{pal["bar"]}"/>'
            )
            step_lbl = _clip_text(str(st.get("step") or f"第 {start_idx + i + 1} 环"), step_max_u)
            st_title = _clip_text(str(st.get("title") or ""), title_max_u)
            metric = _clip_text(str(st.get("metric") or ""), metric_max_u)
            desc_lines = _wrap_lines(str(st.get("desc") or ""), max_units=desc_max_u, max_lines=2)

            svg.append(
                f'<text x="{cx_l + 9:.1f}" y="{ry + 20:.1f}" font-size="9" font-weight="700" '
                f'fill="{pal["bar"]}" font-family="sans-serif">{_esc(step_lbl)}</text>'
            )
            svg.append(
                f'<text x="{cx_l + 9:.1f}" y="{ry + 36:.1f}" font-size="10.8" font-weight="800" '
                f'fill="#0f172a" font-family="sans-serif">{_esc(st_title)}</text>'
            )
            if metric:
                svg.append(
                    f'<text x="{cx_l + 9:.1f}" y="{ry + 54:.1f}" font-size="11.2" font-weight="800" '
                    f'fill="{pal["text"]}" font-family="sans-serif">{_esc(metric)}</text>'
                )
            base_dy = ry + (70.0 if metric else 54.0)
            for di, dl in enumerate(desc_lines):
                svg.append(
                    f'<text x="{cx_l + 9:.1f}" y="{base_dy + di * 13.0:.1f}" font-size="9.2" '
                    f'fill="#334155" font-family="sans-serif">{_esc(dl)}</text>'
                )

            # Rightward arrow between cards in the same row
            if i + 1 < cnt:
                ax1 = cx_l + cw + 3.0
                ax2 = cx_l + cw + arrow_gap - 5.0
                ay = ry + card_h / 2.0
                svg.append(f'<line x1="{ax1:.1f}" y1="{ay:.1f}" x2="{ax2:.1f}" y2="{ay:.1f}" stroke="#64748b" stroke-width="1.6"/>')
                svg.append(
                    f'<polygon points="{ax2 + 4:.1f},{ay:.1f} {ax2 - 2:.1f},{ay - 4:.1f} {ax2 - 2:.1f},{ay + 4:.1f}" fill="#64748b"/>'
                )
            centers.append((cx_l + cw / 2.0, ry + card_h))
        return centers

    r1_centers = draw_row(row1, top_y, 0)
    if row2:
        ry2 = top_y + card_h + row_gap
        # Clean downward stepped connector from last card of Row 1 to first card of Row 2
        mid_y = top_y + card_h + row_gap / 2.0
        sx = r1_centers[-1][0]
        cnt2 = len(row2)
        cw2 = (640.0 - 2 * pad_x - max(0, cnt2 - 1) * 22.0) / max(cnt2, 1)
        tx = pad_x + cw2 / 2.0
        svg.append(
            f'<path d="M {sx:.1f} {top_y + card_h + 2:.1f} L {sx:.1f} {mid_y:.1f} '
            f'L {tx:.1f} {mid_y:.1f} L {tx:.1f} {ry2 - 5:.1f}" '
            'fill="none" stroke="#64748b" stroke-width="1.5" stroke-dasharray="4,2"/>'
        )
        svg.append(
            f'<polygon points="{tx:.1f},{ry2 - 1:.1f} {tx - 4:.1f},{ry2 - 7:.1f} {tx + 4:.1f},{ry2 - 7:.1f}" fill="#64748b"/>'
        )
        draw_row(row2, ry2, len(row1))

    return _wrap_chart_box(title, subtitle, "".join(svg), vb_h, takeaway=takeaway, note=note)


def render_visual_chart(data: dict[str, Any]) -> str:
    """Dispatch a validated DAILY_VISUAL payload to its SVG renderer."""
    errs = validate_visual_spec(data)
    if errs:
        raise ValueError("; ".join(errs))
    vtype = str(data["type"]).strip().lower()
    if vtype == "waterfall":
        return _render_waterfall(data)
    if vtype == "bar_compare":
        return _render_bar_compare(data)
    if vtype == "anchor_range":
        return _render_anchor_range(data)
    if vtype == "flow_chain":
        return _render_flow_chain(data)
    raise ValueError(f"Unsupported visual chart type: {vtype!r}")


_FENCE_OPEN_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_INLINE_OR_VISUAL_RE = re.compile(
    r"(`[^`\n]+`)|<!--\s*DAILY_VISUAL\s*(\{.*?\})\s*-->",
    re.DOTALL,
)


def _split_fenced_code_blocks(md_text: str) -> list[tuple[bool, str]]:
    """Split Markdown into alternating (is_fenced_code, chunk) segments."""
    segments: list[tuple[bool, str]] = []
    buf: list[str] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    for line in md_text.splitlines(keepends=True):
        m = _FENCE_OPEN_RE.match(line)
        if not in_fence:
            if m:
                if buf:
                    segments.append((False, "".join(buf)))
                    buf = []
                in_fence = True
                fence_char = m.group(1)[0]
                fence_len = len(m.group(1))
                buf.append(line)
            else:
                buf.append(line)
        else:
            buf.append(line)
            stripped = line.strip()
            if (
                stripped
                and len(stripped) >= fence_len
                and set(stripped) == {fence_char}
            ):
                segments.append((True, "".join(buf)))
                buf = []
                in_fence = False
    if buf:
        segments.append((in_fence, "".join(buf)))
    return segments


def strip_visual_directives(md_text: str) -> str:
    """Remove `<!-- DAILY_VISUAL {...} -->` directives outside fenced code blocks and inline backticks."""
    out: list[str] = []
    for is_code, chunk in _split_fenced_code_blocks(md_text):
        if is_code:
            out.append(chunk)
        else:
            out.append(
                _INLINE_OR_VISUAL_RE.sub(
                    lambda m: m.group(1) if m.group(1) is not None else "",
                    chunk,
                )
            )
    return "".join(out)


def extract_visual_directives(md_text: str) -> tuple[str, dict[str, str]]:
    """Extract `<!-- DAILY_VISUAL {...} -->` directives outside code blocks into token->rendered-HTML map."""
    charts: dict[str, str] = {}
    idx = 0

    def _repl(match: re.Match[str]) -> str:
        nonlocal idx
        if match.group(1) is not None:
            return match.group(1)
        raw_json = match.group(2).strip()
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in <!-- DAILY_VISUAL ... -->: {exc}") from exc
        token = f"<!-- VISUAL_SLOT_{idx} -->"
        idx += 1
        charts[token] = render_visual_chart(payload)
        return f"\n{token}\n"

    out_parts: list[str] = []
    for is_code, chunk in _split_fenced_code_blocks(md_text):
        if is_code:
            out_parts.append(chunk)
        else:
            out_parts.append(_INLINE_OR_VISUAL_RE.sub(_repl, chunk))
    return "".join(out_parts), charts
