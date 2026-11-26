#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-dependency SVG text bounding-box geometry & collision checker.

Shared by gold/lint_readability.py, equity/lint_equity.py, and scripts/lint_site.py
to detect out-of-bounds text and pairwise label collisions across vector charts.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET

_SVG_BLOCK_RE = re.compile(r"<svg\b[^>]*>.*?</svg>", flags=re.DOTALL | re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_NUM_UNIT_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)")
_TRANSLATE_RE = re.compile(
    r"translate\(\s*([+-]?\d+(?:\.\d+)?)(?:[\s,]+([+-]?\d+(?:\.\d+)?))?\s*\)",
    re.IGNORECASE,
)


def _parse_translate(transform: str | None) -> tuple[float, float]:
    """Sum translate(x[, y]) offsets from an SVG transform attribute."""
    if not transform:
        return 0.0, 0.0
    dx = 0.0
    dy = 0.0
    for m in _TRANSLATE_RE.finditer(transform):
        try:
            dx += float(m.group(1))
            if m.group(2) is not None:
                dy += float(m.group(2))
        except ValueError:
            continue
    return dx, dy


def _parse_length_px(raw: str | None, font_size: float) -> float | None:
    """Parse an SVG length supporting bare px numbers and em units."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    m = _NUM_UNIT_RE.match(s)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    rest = s[m.end() :].strip()
    if rest == "em":
        return val * font_size
    return val


def _parse_style(style_str: str | None) -> dict[str, str]:
    if not style_str:
        return {}
    out: dict[str, str] = {}
    for part in style_str.split(";"):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        k_s, v_s = k.strip().lower(), v.strip()
        if k_s and v_s:
            out[k_s] = v_s
    return out


def _get_attr(node: ET.Element, name: str, style: dict[str, str], default: str = "") -> str:
    val = node.attrib.get(name)
    if val is not None and str(val).strip() != "":
        return str(val).strip()
    return style.get(name.lower(), default).strip()


def _parse_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    m = _NUM_UNIT_RE.match(str(raw))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _is_bold_weight(weight: str) -> bool:
    w = weight.strip().lower()
    if w in ("bold", "bolder"):
        return True
    try:
        return float(w) >= 600.0
    except ValueError:
        return False


def _char_width_em(ch: str) -> float:
    """Estimate glyph advance width in em units (CJK=1.0em, proportional ASCII)."""
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


def _estimate_run_width(text: str, font_size: float, is_bold: bool) -> float:
    if not text:
        return 0.0
    em_sum = sum(_char_width_em(ch) for ch in text)
    return em_sum * font_size * (1.04 if is_bold else 1.0)


def _estimate_text_element_width(node: ET.Element, parent_fs: float, parent_bold: bool) -> tuple[str, float, float]:
    """Return (normalized_text, width_px, max_font_size) handling inline <tspan> children."""
    has_children = len(node) > 0
    if not has_children:
        txt = _WS_RE.sub(" ", node.text or "").strip()
        return txt, _estimate_run_width(txt, parent_fs, parent_bold), parent_fs

    runs: list[tuple[str, float, bool]] = []
    if node.text:
        runs.append((node.text, parent_fs, parent_bold))
    for child in node:
        ctag = child.tag.split("}")[-1].lower()
        cstyle = _parse_style(child.attrib.get("style"))
        cfs = _parse_float(_get_attr(child, "font-size", cstyle)) or parent_fs
        cfw = _get_attr(child, "font-weight", cstyle)
        cbold = _is_bold_weight(cfw) if cfw else parent_bold
        ctext = "".join(child.itertext())
        if ctag == "tspan" and ctext:
            runs.append((ctext, cfs, cbold))
        elif ctext:
            runs.append((ctext, parent_fs, parent_bold))
        if child.tail:
            runs.append((child.tail, parent_fs, parent_bold))

    raw_joined = "".join(r[0] for r in runs)
    norm_full = _WS_RE.sub(" ", raw_joined).strip()
    if not norm_full:
        return "", 0.0, parent_fs

    # Normalize whitespace across runs while preserving per-run font metrics
    width = 0.0
    max_fs = parent_fs
    prev_space = True
    for seg_txt, seg_fs, seg_bold in runs:
        max_fs = max(max_fs, seg_fs)
        norm_seg = _WS_RE.sub(" ", seg_txt)
        if prev_space:
            norm_seg = norm_seg.lstrip(" ")
        if not norm_seg:
            continue
        prev_space = norm_seg.endswith(" ")
        width += _estimate_run_width(norm_seg, seg_fs, seg_bold)
    if prev_space and runs:
        width = max(0.0, width - _estimate_run_width(" ", runs[-1][1], runs[-1][2]))
    return norm_full, width, max_fs


def _parse_viewbox(svg_el: ET.Element) -> tuple[float, float, float, float] | None:
    vb = svg_el.attrib.get("viewBox") or svg_el.attrib.get("viewbox")
    if not vb:
        return None
    parts = [p for p in re.split(r"[\s,]+", vb.strip()) if p]
    if len(parts) != 4:
        return None
    try:
        vals = tuple(float(p) for p in parts)
    except ValueError:
        return None
    return vals  # type: ignore[return-value]


def _make_text_box(
    x: float,
    y: float,
    width: float,
    eff_fs: float,
    anchor: str,
    baseline: str,
    txt: str,
) -> tuple[float, float, float, float, str]:
    if anchor == "middle":
        x0, x1 = x - width / 2.0, x + width / 2.0
    elif anchor == "end":
        x0, x1 = x - width, x
    else:
        x0, x1 = x, x + width

    if baseline in ("middle", "central"):
        y0, y1 = y - eff_fs * 0.50, y + eff_fs * 0.50
    elif baseline in ("hanging", "text-before-edge"):
        y0, y1 = y, y + eff_fs * 1.00
    else:
        y0, y1 = y - eff_fs * 0.82, y + eff_fs * 0.18
    return (x0, y0, x1, y1, txt)


def _extract_text_boxes(
    node: ET.Element,
    tx: float,
    ty: float,
    style: dict[str, str],
) -> list[tuple[float, float, float, float, str]]:
    """Extract one or more text bounding boxes from <text>, handling <tspan dy/x/y/dx>."""
    raw_x = _parse_float(node.attrib.get("x"))
    raw_y = _parse_float(node.attrib.get("y"))
    if raw_x is None and raw_y is None:
        return []
    base_x = (raw_x or 0.0) + tx
    base_y = (raw_y or 0.0) + ty
    fs = _parse_float(_get_attr(node, "font-size", style, "10")) or 10.0
    is_bold = _is_bold_weight(_get_attr(node, "font-weight", style))
    anchor = _get_attr(node, "text-anchor", style, "start").lower()
    baseline = _get_attr(node, "dominant-baseline", style).lower()

    # Check if any <tspan> child shifts position explicitly via dy/y/x
    has_positioned_tspan = False
    for child in node:
        if child.tag.split("}")[-1].lower() != "tspan":
            continue
        dy_val = _parse_length_px(child.attrib.get("dy"), fs)
        if (
            child.attrib.get("y") is not None
            or child.attrib.get("x") is not None
            or (dy_val is not None and abs(dy_val) > 1e-6)
        ):
            has_positioned_tspan = True
            break

    if not has_positioned_tspan:
        txt, width, eff_fs = _estimate_text_element_width(node, fs, is_bold)
        if not txt or width <= 0.0:
            return []
        return [_make_text_box(base_x, base_y, width, eff_fs, anchor, baseline, txt)]

    out: list[tuple[float, float, float, float, str]] = []
    cur_x = base_x
    cur_y = base_y
    lead_txt = _WS_RE.sub(" ", node.text or "").strip()
    if lead_txt:
        lw = _estimate_run_width(lead_txt, fs, is_bold)
        if lw > 0.0:
            out.append(_make_text_box(cur_x, cur_y, lw, fs, anchor, baseline, lead_txt))

    for child in node:
        ctag = child.tag.split("}")[-1].lower()
        cstyle = _parse_style(child.attrib.get("style"))
        cfs = _parse_float(_get_attr(child, "font-size", cstyle)) or fs
        cfw = _get_attr(child, "font-weight", cstyle)
        cbold = _is_bold_weight(cfw) if cfw else is_bold
        canc = _get_attr(child, "text-anchor", cstyle, anchor).lower()
        cbase = _get_attr(child, "dominant-baseline", cstyle, baseline).lower()

        if ctag == "tspan":
            cx_attr = _parse_float(child.attrib.get("x"))
            cy_attr = _parse_float(child.attrib.get("y"))
            cdx = _parse_length_px(child.attrib.get("dx"), cfs) or 0.0
            cdy = _parse_length_px(child.attrib.get("dy"), cfs) or 0.0
            if cx_attr is not None:
                cur_x = cx_attr + tx
            cur_x += cdx
            if cy_attr is not None:
                cur_y = cy_attr + ty
            cur_y += cdy

        ctext = _WS_RE.sub(" ", "".join(child.itertext())).strip()
        if ctext:
            cw = _estimate_run_width(ctext, cfs, cbold)
            if cw > 0.0:
                out.append(_make_text_box(cur_x, cur_y, cw, cfs, canc, cbase, ctext))

        if child.tail:
            tail_txt = _WS_RE.sub(" ", child.tail).strip()
            if tail_txt:
                tw = _estimate_run_width(tail_txt, fs, is_bold)
                if tw > 0.0:
                    out.append(_make_text_box(cur_x, cur_y, tw, fs, anchor, baseline, tail_txt))
    return out


def check_svg_text_geometry(
    svg_xml: str,
    *,
    label: str = "svg",
    oob_tol: float = 2.0,
    min_overlap_x: float = 2.0,
    min_overlap_y: float = 2.0,
    check_circles: bool = True,
) -> list[str]:
    """Check all chart <svg> blocks in svg_xml for text out-of-bounds, pairwise overlap,
    and text-vs-data-circle collisions (accumulating <g>/<text> translate transforms and <tspan dy>).

    Small icons (viewBox width < 300) are skipped automatically.
    """
    issues: list[str] = []
    chunks = _SVG_BLOCK_RE.findall(svg_xml or "")
    for idx, chunk in enumerate(chunks, 1):
        tag = f"{label}#{idx}" if len(chunks) > 1 else label
        try:
            root = ET.fromstring(chunk)
        except ET.ParseError as exc:
            issues.append(f"[{tag}] SVG XML 解析失败: {exc}")
            continue

        vb = _parse_viewbox(root)
        if vb is None:
            continue
        vb_x, vb_y, vb_w, vb_h = vb
        if vb_w < 300.0:
            continue

        boxes: list[tuple[float, float, float, float, str]] = []
        circles: list[tuple[float, float, float]] = []

        def _walk(node: ET.Element, acc_tx: float, acc_ty: float) -> None:
            style = _parse_style(node.attrib.get("style"))
            if (
                _get_attr(node, "display", style).lower() == "none"
                or _get_attr(node, "visibility", style).lower() == "hidden"
            ):
                return
            op = _parse_float(_get_attr(node, "opacity", style))
            if op is not None and op <= 0.0:
                return

            ntx, nty = _parse_translate(node.attrib.get("transform"))
            cur_tx = acc_tx + ntx
            cur_ty = acc_ty + nty
            el_tag = node.tag.split("}")[-1].lower()

            if el_tag == "text":
                for box in _extract_text_boxes(node, cur_tx, cur_ty, style):
                    x0, y0, x1, y1, txt = box
                    if (
                        x0 < vb_x - oob_tol
                        or x1 > vb_x + vb_w + oob_tol
                        or y0 < vb_y - oob_tol
                        or y1 > vb_y + vb_h + oob_tol
                    ):
                        issues.append(
                            f"[{tag}] SVG 文字越界 '{txt[:28]}' "
                            f"box=({x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}) "
                            f"viewBox=({vb_x:.0f},{vb_y:.0f},{vb_w:.0f},{vb_h:.0f})"
                        )
                    boxes.append(box)
                return

            if el_tag == "circle":
                cx = _parse_float(node.attrib.get("cx"))
                cy = _parse_float(node.attrib.get("cy"))
                rad = _parse_float(node.attrib.get("r"))
                if cx is not None and cy is not None and rad is not None and rad >= 3.0:
                    circles.append((cx + cur_tx, cy + cur_ty, rad))
                return

            for child in node:
                _walk(child, cur_tx, cur_ty)

        _walk(root, 0.0, 0.0)

        for i in range(len(boxes)):
            ax0, ay0, ax1, ay1, at = boxes[i]
            for j in range(i + 1, len(boxes)):
                bx0, by0, bx1, by1, bt = boxes[j]
                ox = min(ax1, bx1) - max(ax0, bx0)
                oy = min(ay1, by1) - max(ay0, by0)
                if ox >= min_overlap_x and oy >= min_overlap_y:
                    issues.append(
                        f"[{tag}] SVG 文字重叠 (ox={ox:.1f}px, oy={oy:.1f}px): "
                        f"'{at[:24]}' 与 '{bt[:24]}'"
                    )

        if check_circles and circles:
            for cx, cy, rad in circles:
                # Skip legend strips / header/footer indicator dots
                if cy < vb_y + 42.0 or cy > vb_y + vb_h - 24.0:
                    continue
                eff_r_sq = max(0.0, rad - 0.5) ** 2
                for x0, y0, x1, y1, txt in boxes:
                    nx = max(x0, min(cx, x1))
                    ny = max(y0, min(cy, y1))
                    if (cx - nx) ** 2 + (cy - ny) ** 2 < eff_r_sq:
                        issues.append(
                            f"[{tag}] SVG 文字与数据圆点重叠: '{txt[:24]}' "
                            f"box=({x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f}) "
                            f"与 circle({cx:.1f},{cy:.1f},r={rad:.1f})"
                        )
    return issues


check_svg_geometry = check_svg_text_geometry
