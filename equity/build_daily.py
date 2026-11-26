#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure-web daily metadata extractor and SVG chart loader for A-Share / HK-Stock / US-Stock dailies.

Used by scripts/build_site.py and equity/lint_equity.py to parse DAILY_META_JSON and render
self-contained vector SVG charts (A1–A7, H1–H7, U1–U7) with zero PDF/DOCX/Chrome dependencies.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pdf_common import BASE_DIR, DAILY_DIR

ALL_MARKETS = ("a_share", "hk_stock", "us_stock")


def extract_daily_meta(md_text: str, md_path: Path) -> tuple[dict | None, str]:
    """Extract optional <!-- DAILY_META_JSON { ... } --> block (top or bottom); raise loudly on JSON syntax errors."""
    m = re.search(r"<!--\s*DAILY_META_JSON\s*(\{.*?\})\s*-->", md_text, flags=re.DOTALL)
    if not m:
        return None, md_text
    cleaned = (md_text[: m.start()] + md_text[m.end() :]).strip()
    try:
        meta = json.loads(m.group(1))
        return meta, cleaned
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid DAILY_META_JSON in {md_path}: {exc}") from exc


def load_optional_charts(market: str, meta_override: dict | None = None) -> dict[str, str]:
    """Render self-contained vector SVGs using this daily snapshot's own DAILY_META_JSON."""
    if not meta_override:
        return {}
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    if market == "a_share":
        import build_a_share_pdf as mod
        return {
            "<!-- CHART_A1 -->": mod.svg_chart_a1_cycles(meta_override),
            "<!-- CHART_A2 -->": mod.svg_chart_a2_split_and_futures(meta_override),
            "<!-- CHART_A3 -->": mod.svg_chart_a3_macro_k_split(meta_override),
            "<!-- CHART_A4 -->": mod.svg_chart_a4_clock(meta_override),
            "<!-- CHART_A5 -->": mod.svg_chart_a5_targets_and_math(meta_override),
            "<!-- CHART_A6 -->": mod.svg_chart_a6_sector_heatmap(meta_override),
            "<!-- CHART_A7 -->": mod.svg_chart_a7_stock_quadrant(meta_override),
        }
    if market == "hk_stock":
        import build_hk_stock_pdf as mod
        return {
            "<!-- CHART_H1 -->": mod.svg_chart_h1_cycles(meta_override),
            "<!-- CHART_H2 -->": mod.svg_chart_h2_flow_and_rebalance(meta_override),
            "<!-- CHART_H3 -->": mod.svg_chart_h3_peg_and_erp(meta_override),
            "<!-- CHART_H4 -->": mod.svg_chart_h4_clock(meta_override),
            "<!-- CHART_H5 -->": mod.svg_chart_h5_targets_and_scenarios(meta_override),
            "<!-- CHART_H6 -->": mod.svg_chart_h6_ah_arbitrage_and_sectors(meta_override),
            "<!-- CHART_H7 -->": mod.svg_chart_h7_stock_quadrant(meta_override),
        }
    import build_us_stock_pdf as mod
    return {
        "<!-- CHART_U1 -->": mod.svg_chart_u1_crises_and_mas(meta_override),
        "<!-- CHART_U2 -->": mod.svg_chart_u2_storm_timeline(meta_override),
        "<!-- CHART_U3 -->": mod.svg_chart_u3_credit_split(meta_override),
        "<!-- CHART_U4 -->": mod.svg_chart_u4_clock(meta_override),
        "<!-- CHART_U5 -->": mod.svg_chart_u5_wall_street_forensic(meta_override),
        "<!-- CHART_U6 -->": mod.svg_chart_u6_sector_heatmap(meta_override),
        "<!-- CHART_U7 -->": mod.svg_chart_u7_stock_quadrant(meta_override),
    }


def detect_market(md_path: Path) -> str:
    name = md_path.name.lower()
    if "hk_stock" in name or "hk-" in name:
        return "hk_stock"
    if "us_stock" in name or "us-" in name:
        return "us_stock"
    if "a_share" in name or "a-" in name:
        return "a_share"
    raise ValueError(f"Cannot detect market (a_share / hk_stock / us_stock) from filename: {md_path.name}")


def main() -> None:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    if "--check" in sys.argv[1:]:
        if str(BASE_DIR) not in sys.path:
            sys.path.insert(0, str(BASE_DIR))
        from lint_equity import check_workspace_state

        errs, warns = check_workspace_state(precheck=False)
        for e in errs:
            print(f"[CHECK FAIL] {e}")
        for w in warns:
            print(f"[CHECK WARN] {w}")
        print(f"Pure-web equity daily check completed ({len(errs)} hard error(s), {len(warns)} warning(s)).")
        if errs:
            raise SystemExit(1)
        return
    print("Pure-web mode: equity/build_daily.py provides SVG chart loaders and metadata parsers; use scripts/build_site.py to build the static portal.")


if __name__ == "__main__":
    main()
