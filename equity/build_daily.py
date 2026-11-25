#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build magazine-grade plain-language PDF, pure-Python ECMA-376 native DOCX, & responsive 3-market mobile HTML
from daily A-Share / HK-Stock / US-Stock Markdown reports.

Features:
  - Shared pdf_common engine (SkPDF emoji guard, 3-market themes, embedded pre-render redline linter)
  - Pure-Python native ECMA-376 OOXML .docx (replaces macOS textutil completely; zero table/border stripping)
  - Self-contained SVG chart rendering via DAILY_META_JSON (A1-A7, H1-H7, U1-U7)
  - Default mode builds only the reports required by the active edition plan
  - Outputs responsive 3-market mobile HTML (daily/latest_{a_share,hk_stock,us_stock}.html) alongside A4 PDF & DOCX
  - Delegates workspace/RSI/ledger hygiene audit cleanly to lint_equity.check_workspace_state() (single source)
"""

from __future__ import annotations

import glob
import html as html_mod
import json
import re
import sys
from pathlib import Path

from lint_equity import check_daily_contract, check_workspace_state, load_current_edition_plan, parse_daily_sort_key
from pdf_common import (
    BASE_DIR,
    CHROME_BIN,
    DAILY_DIR,
    build_theme_css,
    clean_plain_text,
    freeze_equity_inputs,
    render_cover_banner,
    render_docx_atomic,
    render_md_body,
    render_pdf_atomic,
    run_lint_gate,
    write_equity_receipt,
)

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


def build_one(
    md_path: Path,
    *,
    export_docx: bool = True,
    no_lint: bool = False,
    write_mobile_latest: bool = False,
) -> None:
    market = detect_market(md_path)
    frozen = freeze_equity_inputs(md_path, Path(__file__), BASE_DIR / f"build_{market}_pdf.py") if export_docx else None
    raw_text = md_path.read_text(encoding="utf-8")
    meta, md_body = extract_daily_meta(raw_text, md_path)
    if not no_lint:
        errors = check_daily_contract(md_path, meta, md_body)
        if errors:
            raise ValueError("\n".join(errors))
    run_lint_gate(raw_text, str(md_path), is_flagship=False, meta=meta, no_lint=no_lint)

    defaults = {
        "a_share": ("A股每日大白话投研简报", "A 股每日大白话投研简报", "A 股每日大白话投研简报（07:30 早刊 & 18:00 晚刊）"),
        "hk_stock": ("港股每日大白话投研简报", "港股每日大白话投研简报", "港股每日大白话投研简报（07:30 早刊 & 18:00 晚刊）"),
        "us_stock": ("美股每日大白话投研简报", "美股每日大白话投研简报", "美股每日大白话投研简报（07:30 早刊 & 18:00 晚刊）"),
    }
    default_title, default_tag, default_footer = defaults[market]

    charts = load_optional_charts(market, meta_override=meta)
    title, body = render_md_body(
        md_body, charts, default_title=default_title, is_flagship=False, enable_kanban_wrap=True
    )
    cover_html, doc_title, page_footer, footer_note = render_cover_banner(
        meta, title, default_tag, default_footer, meta_label="阅读提示"
    )
    pdf_path = md_path.with_suffix(".pdf")
    docx_path = md_path.with_suffix(".docx")
    tmp_html = md_path.with_suffix(".tmp.html")
    tmp_pdf = md_path.with_suffix(".tmp.pdf")
    footer_div = f'<div class="footer-note">{html_mod.escape(footer_note)}</div>' if footer_note else ""
    full_html = (
        f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html_mod.escape(clean_plain_text(doc_title))}</title>"
        f"<style>{build_theme_css(market, page_footer, is_flagship=False)}</style></head>"
        f"<body>{cover_html}{body}{footer_div}</body></html>"
    )
    mobile_path = (DAILY_DIR / f"latest_{market}.html") if write_mobile_latest else None
    render_pdf_atomic(
        full_html,
        pdf_path,
        tmp_html,
        tmp_pdf,
        mobile_html_path=mobile_path,
        mobile_market=market,
    )
    print(f"Built daily PDF ({pdf_path.stat().st_size:,} bytes): {pdf_path}")
    if mobile_path is not None:
        print(f"Synced mobile HTML ({mobile_path.stat().st_size:,} bytes): {mobile_path}")

    if export_docx:
        render_docx_atomic(full_html, docx_path, market=market, footer_title=page_footer)
        write_equity_receipt(frozen, pdf_path, docx_path)
        print(f"Built native OOXML DOCX ({docx_path.stat().st_size:,} bytes): {docx_path}")


def run_workspace_check(*, fail_on_error: bool = True) -> int:
    assert Path(CHROME_BIN).exists(), "Chrome missing"
    import bs4  # noqa: F401
    from PIL import Image  # noqa: F401
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    errs, warns = check_workspace_state(precheck=False)
    for e in errs:
        print(f"[CHECK FAIL] {e}")
    for w in warns:
        print(f"[CHECK WARN] {w}")
    print(f"Hygiene check completed ({len(errs)} hard error(s), {len(warns)} warning(s)).")
    if fail_on_error and errs:
        raise SystemExit(f"Workspace hygiene check failed ({len(errs)} hard error(s)).")
    return len(errs)


def main() -> None:
    args = sys.argv[1:]
    if "--check" in args:
        run_workspace_check(fail_on_error=True)
        return

    export_docx = "--no-docx" not in args
    build_all = "--all" in args
    force_legacy = "--force-legacy" in args
    no_lint = "--no-lint" in args
    positional = [a for a in args if not a.startswith("-")]

    market_files: dict[str, list[Path]] = {}
    for mk in ALL_MARKETS:
        market_files[mk] = sorted(
            (Path(p).resolve() for p in glob.glob(str(DAILY_DIR / f"????-??-??_*_{mk}*.md"))),
            key=parse_daily_sort_key,
        )
    latest_set = {files[-1].resolve() for files in market_files.values() if files}

    try:
        plan = load_current_edition_plan() if not positional and not build_all else None
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot build equity edition: {exc}") from exc
    targets: list[Path] = []
    if positional:
        targets = [Path(p).resolve() for p in positional]
    elif build_all:
        candidates = sorted(
            (Path(p).resolve() for p in glob.glob(str(DAILY_DIR / "????-??-??_*.md"))),
            key=parse_daily_sort_key,
        )
        for c in candidates:
            if not force_legacy and "DAILY_META_JSON" not in c.read_text(encoding="utf-8"):
                print(f"Skipping legacy snapshot (no DAILY_META_JSON): {c.name}")
                continue
            targets.append(c)
    elif plan is not None:
        targets = [
            (BASE_DIR / item["required_file"]).resolve()
            for item in plan["markets"].values() if item["action"] == "publish"
        ]
        missing = [target.name for target in targets if not target.is_file()]
        if missing:
            raise SystemExit(f"Missing required reports for {plan['edition_id']}: {', '.join(missing)}")
        if not targets:
            print(f"{plan['edition_id']}: all markets reuse the previous issue.")
            return
    else:
        latest_dates = {parse_daily_sort_key(f)[0] for f in latest_set}
        all_candidates = sorted(
            {f.resolve() for files in market_files.values() for f in files},
            key=parse_daily_sort_key,
        )
        for c in all_candidates:
            if c in latest_set:
                targets.append(c)
            elif parse_daily_sort_key(c)[0] in latest_dates and "DAILY_META_JSON" in c.read_text(encoding="utf-8"):
                pdf_p = c.with_suffix(".pdf")
                docx_p = c.with_suffix(".docx")
                if not pdf_p.exists() or c.stat().st_mtime > pdf_p.stat().st_mtime or (export_docx and not docx_p.exists()):
                    targets.append(c)

    if not targets:
        raise SystemExit("No daily YYYY-MM-DD_*_{a_share,hk_stock,us_stock}.md files found in daily/")

    for t in targets:
        build_one(
            t,
            export_docx=export_docx,
            no_lint=no_lint,
            write_mobile_latest=(t.resolve() in latest_set),
        )

    run_workspace_check(fail_on_error=not no_lint)


if __name__ == "__main__":
    main()
