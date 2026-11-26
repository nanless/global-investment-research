#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pure-web HTML & vector SVG rendering engine for the Gold Cross-Century Research Report (1971–2030).
Reads:
  - master_snapshot.json (dedicated Master Report snapshot locked via <!-- MASTER_BASELINE {...} -->)
  - 黄金跨世纪周期与2026-2030终审研究报告.md
Provides cover HTML, body HTML, and 7 sequential 640px vector SVGs for scripts/build_site.py.

Usage:
  python3 build_report.py --check                        # verify MASTER_BASELINE & master_snapshot.json
  python3 build_report.py --check --snapshot <file.json> # check an alternate snapshot
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

from build_daily import (
    HALO,
    esc,
    parse_markdown_to_html,
    sanitize_hex_color,
    svg_esc,
)

OUT_DIR = Path(__file__).resolve().parent
BASE_NAME = "黄金跨世纪周期与2026-2030终审研究报告"
MD_PATH = OUT_DIR / f"{BASE_NAME}.md"
DEFAULT_MASTER_SNAPSHOT = OUT_DIR / "master_snapshot.json"

MASTER_BASELINE_RE = re.compile(r"<!--\s*MASTER_BASELINE\s*(\{.*?\})\s*-->", re.DOTALL)

# Runtime state populated by caller — zero import-time filesystem I/O
SNAP: dict = {}
REPORT_VERSION = "黄金跨世纪周期全景配置指南"
REPORT_TIMESTAMP = "2026年11月24日（周二）16:30"
REPORT_SHORT_DATE = "2026-11-24 16:30"


def parse_master_baseline(md_text: str) -> dict:
    m = MASTER_BASELINE_RE.search(md_text)
    if not m:
        raise ValueError("Master Markdown is missing its MASTER_BASELINE lock")
    try:
        baseline = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in <!-- MASTER_BASELINE ... -->: {exc}") from exc
    if baseline.get("snapshot") != DEFAULT_MASTER_SNAPSHOT.name or not baseline.get("as_of_short"):
        raise ValueError("MASTER_BASELINE requires snapshot='master_snapshot.json' and as_of_short")
    return baseline


def load_master_snapshot(
    md_text: str,
    snapshot_override: Path | None = None,
    allow_drift: bool = False,
) -> tuple[dict, Path]:
    """Load dedicated master_snapshot.json and enforce MASTER_BASELINE timestamp lock."""
    baseline = parse_master_baseline(md_text)
    snap_path = snapshot_override or DEFAULT_MASTER_SNAPSHOT

    if not snap_path.exists():
        raise FileNotFoundError(f"Master Report snapshot missing: {snap_path}")
    snap = json.loads(snap_path.read_text(encoding="utf-8"))

    lock_ts = baseline.get("as_of_short")
    snap_ts = snap.get("as_of_short")
    if not snap_ts:
        raise ValueError(f"{snap_path.name} is missing as_of_short")
    if lock_ts != snap_ts and not allow_drift:
        raise RuntimeError(
            f"MASTER_BASELINE drift detected! Master MD locks as_of_short='{lock_ts}', "
            f"but {snap_path.name} has as_of_short='{snap_ts}'. "
            f"Sync Master Report prose, MASTER_BASELINE, and {snap_path.name} before publishing."
        )
    return snap, snap_path


def _as_of_meta() -> tuple[str, int, int, int, str, str, bool, str]:
    """Return (as_short, yr, mo, dy, mmdd, cn_date, is_am, time_word) dynamically from SNAP."""
    as_short = str(SNAP.get("as_of_short", "2026-11-24 16:30"))
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}))?", as_short.strip())
    if m:
        yr, mo, dy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hr = int(m.group(4)) if m.group(4) is not None else 7
        mmdd = f"{mo:02d}/{dy:02d}"
        cn_date = f"{yr} 年 {mo} 月 {dy} 日"
        is_am = hr < 12
    else:
        yr, mo, dy, mmdd, cn_date, is_am = 2026, 11, 24, "11/24", "2026 年 11 月 24 日", False
    time_word = f"{mmdd}基线"
    return as_short, yr, mo, dy, mmdd, cn_date, is_am, time_word


def _tier_dot_color(snap: dict) -> tuple[str, str]:
    """Return (hex_color, css_class) from explicit tier_code first, falling back to tier_label."""
    code = str(snap.get("tier_code", "")).strip().upper()
    if code == "TIER 0":
        return "#dc2626", "dot-red"
    if code == "TIER 1":
        return "#d97706", "dot-amber"
    if code in ("TIER 2", "TIER 3"):
        return "#16a34a", "dot-green"
    lbl = str(snap.get("tier_label", "")) + " " + str(snap.get("tier_status_sub", ""))
    if "红灯" in lbl:
        return "#dc2626", "dot-red"
    if "满格" in lbl or "绿灯" in lbl:
        return "#16a34a", "dot-green"
    if "黄灯" in lbl:
        return "#d97706", "dot-amber"
    return "#dc2626", "dot-red"


# ==============================================================================
# 1. SEVEN BIG-FONT, ZERO-COLLISION (640px, >=10.0px PRINT-SAFE) VECTOR SVGs
# ==============================================================================

def svg_chart_real_vs_nominal(fig_num: int = 1) -> str:
    """Nominal vs Constant CPI-Adjusted Real Gold Price (1971–Present)."""
    spot = int(SNAP["spot_gold_ny_close_rounded"])
    anchor_1980 = float(SNAP.get("cpi_1980_anchor_usd", 3687.46))
    anchor_1980_r = int(round(anchor_1980))
    cpi_u = float(SNAP.get("cpi_u_index", 337.511))
    dev_1980 = ((spot - anchor_1980) / anchor_1980) * 100.0
    as_short, yr, mo, dy, mmdd, _, _, time_word = _as_of_meta()
    cur_lbl = mmdd if yr == 2026 else f"{yr}.{mo:02d}"
    pts = [
        ("1971", 66, 35, 290),
        ("1980", 142, 850, anchor_1980_r),
        ("1999", 216, 253, 512),
        ("2011", 290, 1920, 2856),
        ("2015", 362, 1046, 1493),
        ("2020", 434, 2075, 2694),
        ("2026.01", 514, 5596, 5807),
        (cur_lbl, 596, spot, spot),
    ]

    y_cap = max(6200.0, float(spot) * 1.08)

    def y_coord(val: float) -> float:
        return round(248.0 - (val / y_cap) * 204.0, 1)

    nom_poly = " ".join(f"{x},{y_coord(n)}" for _, x, n, _ in pts)
    real_poly = " ".join(f"{x},{y_coord(r)}" for _, x, _, r in pts)
    y_1980 = y_coord(anchor_1980)
    y_spot = y_coord(spot)

    step = 1500 if y_cap <= 6500 else 2000
    grid_lines = ""
    for val in range(0, int(y_cap) + 1, step):
        y = y_coord(val)
        grid_lines += f'<line x1="56" y1="{y}" x2="622" y2="{y}" stroke="#e2e8f0" stroke-width="0.9"/>'
        grid_lines += f'<text x="50" y="{y+4}" text-anchor="end" font-size="10.8" fill="#64748b">${val:,}</text>'

    dots = ""
    for lbl, x, n, r in pts:
        yn, yrv = y_coord(n), y_coord(r)
        dots += f'<text x="{x}" y="268" text-anchor="middle" font-size="10.6" fill="#334155" font-weight="700">{svg_esc(lbl)}</text>'
        dots += f'<circle cx="{x}" cy="{yrv}" r="4.2" fill="#1e3a8a" stroke="#ffffff" stroke-width="1.2"/>'
        dots += f'<circle cx="{x}" cy="{yn}" r="3.4" fill="#d97706"/>'

    if y_spot > 195.0:
        box_y = round(y_spot - 48.0, 1)
        stem_y1, stem_y2 = round(y_spot - 14.0, 1), round(y_spot - 5.0, 1)
    else:
        box_y = round(y_spot + 14.0, 1)
        stem_y1, stem_y2 = round(y_spot + 5.0, 1), round(y_spot + 14.0, 1)

    chart_title = esc(f"图 {fig_num}：扣掉 55 年通货膨胀后，{time_word}金价恰好回到 1980 年历史大顶附近")
    return f'''
    <div class="chart-box">
      <div class="chart-title">{chart_title}</div>
      <div class="chart-sub">1971–{yr}.{mmdd.replace("/",".")} 历史标价（橙虚线）vs 折合今日购买力的真实金价（深蓝线 · 美元/盎司 · 非等距关键年份）</div>
      <svg viewBox="0 0 640 288" width="100%" role="img" aria-label="{chart_title}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="640" height="288" fill="#ffffff" rx="6"/>
        {grid_lines}
        <line x1="56" y1="{y_1980}" x2="622" y2="{y_1980}" stroke="#b91c1c" stroke-width="1.6" stroke-dasharray="6,4"/>
        <rect x="198" y="{round(y_1980-21,1)}" width="246" height="17" fill="#fef2f2" rx="3"/>
        <text x="321" y="{round(y_1980-9,1)}" text-anchor="middle" font-size="10.6" fill="#b91c1c" font-weight="700">1980 年历史大顶等值购买力：${anchor_1980_r:,}</text>
        <polyline fill="none" stroke="#1e3a8a" stroke-width="2.6" points="{real_poly}"/>
        <polyline fill="none" stroke="#d97706" stroke-width="2.0" stroke-dasharray="4,3" points="{nom_poly}"/>
        {dots}
        <text x="142" y="{round(y_coord(anchor_1980_r)-9,1)}" text-anchor="middle" font-size="10.8" fill="#1e3a8a" font-weight="700" {HALO}>${anchor_1980_r:,}</text>
        <text x="216" y="{round(y_coord(512)-9,1)}" text-anchor="middle" font-size="10.2" fill="#64748b" font-weight="600" {HALO}>$512</text>
        <text x="290" y="{round(y_coord(2856)-9,1)}" text-anchor="middle" font-size="10.6" fill="#1e3a8a" font-weight="600" {HALO}>$2,856</text>
        <text x="362" y="{round(y_coord(1493)-9,1)}" text-anchor="middle" font-size="10.2" fill="#64748b" font-weight="600" {HALO}>$1,493</text>
        <text x="506" y="{round(y_coord(5807)-9,1)}" text-anchor="end" font-size="11" fill="#1e3a8a" font-weight="800" {HALO}>2026年1月真实顶 $5,807</text>
        <line x1="596" y1="{stem_y1}" x2="596" y2="{stem_y2}" stroke="#d97706" stroke-width="1.3"/>
        <rect x="482" y="{box_y}" width="138" height="34" fill="#fffbeb" stroke="#f59e0b" stroke-width="1.1" rx="4"/>
        <text x="551" y="{round(box_y+14,1)}" text-anchor="middle" font-size="10.8" fill="#92400e" font-weight="800">{time_word}收 ${spot:,}</text>
        <text x="551" y="{round(box_y+28,1)}" text-anchor="middle" font-size="10.2" fill="#b45309">离 1980 锚仅 {dev_1980:+.1f}%</text>
        <line x1="58" y1="12" x2="76" y2="12" stroke="#1e3a8a" stroke-width="2.6"/>
        <text x="82" y="16" font-size="10.8" fill="#1e293b" font-weight="700">真实购买力金价（按今日物价折算）</text>
        <line x1="292" y1="12" x2="312" y2="12" stroke="#d97706" stroke-width="2.2" stroke-dasharray="4,2.5"/>
        <text x="318" y="16" font-size="10.8" fill="#1e293b" font-weight="700">当年名义标价（虚线）</text>
      </svg>
      <div class="chart-note">数据来源：美国劳工部物价指数（CPI-U={cpi_u:.3f}）、伦敦金与国际现货金（截至 {esc(as_short)}）。注：横轴为关键转折年份，非等时间间隔；1980 年真实锚仅作历史购买力标尺，不代表短线必守底线。</div>
    </div>
    '''


def svg_chart_2026_bear_and_vacuum(fig_num: int = 2) -> str:
    """Monthly Candles (dynamic rollover-safe candles + clean zero-occlusion labels)."""
    spot = int(SNAP["spot_gold_ny_close_rounded"])
    peak_26 = float(SNAP.get("spot_gold_2026_peak_usd", 5595.62))
    fri_low = int(round(float(SNAP.get("spot_gold_fri_low_usd", 3502.73))))
    dd_pct = ((spot - peak_26) / peak_26) * 100.0
    as_short, yr, mo, _, mmdd, _, _, _ = _as_of_meta()

    snap_candles = SNAP.get("monthly_candles")
    if isinstance(snap_candles, list) and snap_candles:
        months = [
            (str(c["label"]), float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"]))
            for c in snap_candles[-12:]
        ]
        mo_span_lbl = f"{months[0][0].rstrip('*')}–{months[-1][0].rstrip('*')}"
        live_mo_lbl = months[-1][0].rstrip("*")
    else:
        months = [
            ("1月", 4318, 5596, 4311, 4865),
            ("2月", 4865, 5281, 4404, 5278),
            ("3月", 5278, 5419, 4100, 4697),
            ("4月", 4697, 4890, 4510, 4623),
            ("5月", 4626, 4774, 4366, 4541),
            ("6月", 4540, 4545, 3942, 4006),
            ("7月", 4006, 4202, 3960, 4051),
            ("8月", 4043, 4697, 4020, 4452),
            ("9月", 4452, 4510, 4111, 4156),
            ("10月", 4156, 4225, 3870, 3875),
        ]
        if yr > 2026 or (yr == 2026 and mo >= 12 and "nov_2026_close_usd" in SNAP):
            nov_c = int(round(float(SNAP.get("nov_2026_close_usd", spot))))
            months.append(("11月", 3875, 4146, min(fri_low, nov_c), nov_c))
            lbl_live = "12月*" if yr == 2026 else f"{yr%100:02d}.{mo:02d}*"
            dec_hi = max(nov_c, spot, int(round(float(SNAP.get("spot_gold_intraday_high_usd", spot)))))
            dec_lo = min(nov_c, spot, int(round(float(SNAP.get("dec_2026_low_usd", spot)))))
            months.append((lbl_live, nov_c, dec_hi, dec_lo, spot))
            mo_span_lbl = "2026.01–最新"
            live_mo_lbl = lbl_live.rstrip("*")
        else:
            months.append((f"{mo}月*", 3875, max(4146, spot), min(fri_low, spot), spot))
            mo_span_lbl = f"1–{mo} 月"
            live_mo_lbl = f"{mo} 月"

    all_hi = max(h for _, _, h, _, _ in months)
    all_lo = min(l for _, _, _, l, _ in months)
    y_min_val = min(3000.0, float(int(all_lo // 500) * 500))
    y_max_val = max(5800.0, float(((int(all_hi) // 500) + 1) * 500))
    y_span = max(y_max_val - y_min_val, 500.0)

    def y_p(val: float) -> float:
        return round(266.0 - ((val - y_min_val) / y_span) * 234.0, 1)

    grid = ""
    for val in range(int(y_min_val), int(y_max_val) + 1, 500):
        y = y_p(val)
        if 24.0 <= y <= 270.0:
            grid += f'<line x1="54" y1="{y}" x2="624" y2="{y}" stroke="#e2e8f0" stroke-width="0.8"/>'
            grid += f'<text x="48" y="{y+4}" text-anchor="end" font-size="10.8" fill="#64748b">${val:,}</text>'

    etf_cost = int(round(float(SNAP.get("etf_2y_avg_cost_usd", 3624))))
    y_trap_top = y_p(4873)
    y_trap_bot = y_p(4135)
    y_vac_top = y_p(3880)
    y_vac_bot = y_p(3467)
    y_base_bot = y_p(3121)
    y_etf_be = y_p(etf_cost)
    y_spot = y_p(spot)
    last_l = int(round(months[-1][3]))
    last_col = "#c2410c" if months[-1][4] >= months[-1][1] else "#0f766e"
    box_y = round(max(36.0, min(240.0, y_p(last_l) - 22.0)), 1)

    candles = ""
    n_mo = len(months)
    step_x = 51 if n_mo <= 11 else 46
    start_x = 80 if n_mo <= 11 else 74
    last_x = start_x + (n_mo - 1) * step_x
    for idx, (m, o, h, l, c) in enumerate(months):
        x = start_x + idx * step_x
        yh, yl = y_p(h), y_p(l)
        yo, yc = y_p(o), y_p(c)
        color = "#c2410c" if c >= o else "#0f766e"
        top = min(yo, yc)
        bot = max(yo, yc)
        box_h = max(bot - top, 3.0)
        candles += f'<line x1="{x}" y1="{yh}" x2="{x}" y2="{yl}" stroke="{color}" stroke-width="1.8"/>'
        candles += f'<rect x="{x-9}" y="{top}" width="18" height="{box_h}" fill="{color}" opacity="0.92" rx="1.5"/>'
        candles += f'<text x="{x}" y="286" text-anchor="middle" font-size="10.4" fill="#334155" font-weight="600">{svg_esc(m)}</text>'

    chart_title = esc(f"图 {fig_num}：2026 年冲顶 $5,596 后已回调 {abs(dd_pct):.0f}%，上方套牢盘厚、强支撑在 $3,121–$3,467")
    return f'''
    <div class="chart-box">
      <div class="chart-title">{chart_title}</div>
      <div class="chart-sub">2026 年 {mo_span_lbl}国际现货金月度走势（截至 {mmdd} ${spot:,}）｜ [中文惯例：红涨 / 绿跌]</div>
      <svg viewBox="0 0 640 302" width="100%" role="img" aria-label="{chart_title}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="640" height="302" fill="#ffffff" rx="6"/>
        <rect x="54" y="{y_trap_top}" width="570" height="{round(y_trap_bot - y_trap_top,1)}" fill="#fee2e2" opacity="0.45"/>
        <rect x="54" y="{y_vac_top}" width="570" height="{round(y_vac_bot - y_vac_top,1)}" fill="#fef3c7" opacity="0.48"/>
        <rect x="54" y="{y_vac_bot}" width="570" height="{round(y_base_bot - y_vac_bot,1)}" fill="#dcfce7" opacity="0.52"/>
        {grid}
        <text x="618" y="{round(y_trap_top-5,1)}" text-anchor="end" font-size="10.4" fill="#991b1b" font-weight="700">过去一年追高套牢区（$4,135–$4,873）</text>
        <text x="60" y="{round(y_vac_top-4,1)}" font-size="10.4" fill="#92400e" font-weight="700" {HALO}>筹码真空带（$3,467–$3,880 · 缺密集成交）</text>
        <line x1="54" y1="{y_etf_be}" x2="624" y2="{y_etf_be}" stroke="#b91c1c" stroke-width="1.6" stroke-dasharray="6,3"/>
        <text x="60" y="{round(y_etf_be-5,1)}" font-size="10.4" fill="#991b1b" font-weight="700" {HALO}>近2年基金均本：${etf_cost:,}（多空分水岭）</text>
        <text x="60" y="{round(y_base_bot-5,1)}" font-size="10.6" fill="#065f46" font-weight="800" {HALO}>2025 年四个月换手大底座：$3,121–$3,467（中线强支撑区）</text>
        {candles}
        <circle cx="{start_x}" cy="{y_p(5596)}" r="2.8" fill="#c2410c"/>
        <text x="{start_x+7}" y="{round(y_p(5596)-4,1)}" font-size="10.6" fill="#c2410c" font-weight="800" {HALO}>1月顶 $5,596</text>
        <rect x="{last_x-200}" y="{box_y}" width="176" height="20" fill="#ffffff" stroke="{last_col}" stroke-width="1.1" rx="3"/>
        <text x="{last_x-112}" y="{round(box_y+14,1)}" text-anchor="middle" font-size="10.4" fill="{last_col}" font-weight="800">{mmdd}收 ${spot:,}（低 ${last_l:,}）</text>
        <line x1="{last_x-24}" y1="{round(box_y+10,1)}" x2="{last_x-12}" y2="{y_spot}" stroke="{last_col}" stroke-width="1.3"/>
      </svg>
      <div class="chart-note">数据来源：国际现货金月度行情与世界黄金协会（WGC）基金流向数据。*{live_mo_lbl}为截至 {esc(as_short)} 实时月线；中文习惯以砖红柱代表当月收涨、青绿柱代表当月收跌。</div>
    </div>
    '''


def svg_chart_china_tax_channels(fig_num: int = 5) -> str:
    """Two-Tone Stacked Pure-Gold vs Channel Markup + Dynamic 300-RMB Scale + Concise Tax Breakdown."""
    ch = SNAP["rmb_channels"]
    base = int(ch["etf_base_rmb"])
    brand = int(ch["brand_store_rmb"])
    bank_craft = int(ch["bank_bar_plus_craft_rmb"])
    save_g = int(ch["wedding_save_per_g_rmb"])
    save_pct = float(ch.get("wedding_save_pct", round((save_g / max(brand, 1)) * 100.0, 1)))
    as_short, _, _, _, _, cn_date, _, time_word = _as_of_meta()

    items = [
        ("黄金ETF / 交易所原料", base, "+0元（0%增值税，投资首选）", "#1e3a8a"),
        ("四大行积存金（账面）", int(ch["bank_accum_rmb"]), f"+{int(ch['bank_accum_rmb'])-base}元（卖出扣0.5%）", "#2563eb"),
        ("四大行标准投资金条", int(ch["bank_bar_rmb"]), f"+{int(ch['bank_bar_rmb'])-base}元（实物最划算）", "#0f766e"),
        ("银行金条 + 水贝加工", bank_craft, f"+{bank_craft-base}元（比金店省{save_g}元/克）", "#059669"),
        ("水贝非会员零售金条", int(ch["shuibei_nonmember_bar_rmb"]), f"+{int(ch['shuibei_nonmember_bar_rmb'])-base}元（非会员13%税坑）", "#d97706"),
        ("水贝含税零售首饰", int(ch["shuibei_taxed_jewelry_rmb"]), f"+{int(ch['shuibei_taxed_jewelry_rmb'])-base}元（税差+5%消费税+工费）", "#c2410c"),
        ("品牌金店挂牌（周大福等）", brand, f"+{brand-base}元（+{((brand-base)/max(base,1))*100:.1f}% 溢价）", "#991b1b"),
    ]

    max_price = max(p for _, p, _, _ in items)
    max_scale = max(1200, int(((max_price + 299) // 300) * 300))

    def w_px(val: float) -> float:
        return round((val / float(max_scale)) * 232.0, 1)

    x0 = 158.0
    w_base = w_px(base)
    x_base = round(x0 + w_base, 1)

    # Bottom honest scale ticks in 300-RMB steps (0 / 300 / 600 / 900 / 1200 — avoids 778/800 tick collision!)
    tick_step = 300 if max_scale <= 1500 else 500
    scale_svg = ""
    for tv in range(0, max_scale + 1, tick_step):
        tx = round(x0 + w_px(tv), 1)
        scale_svg += f'<line x1="{tx}" y1="26" x2="{tx}" y2="270" stroke="#e2e8f0" stroke-width="0.8"/>'
        scale_svg += f'<text x="{tx}" y="285" text-anchor="middle" font-size="9.8" fill="#64748b">{tv:,}元</text>'

    bars = ""
    for i, (name, price, note, color) in enumerate(items):
        y = 34 + i * 33
        w = w_px(price)
        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        bars += f'<rect x="8" y="{y-4}" width="624" height="31" fill="{bg}"/>'
        bars += f'<text x="{x0-8}" y="{y+15}" text-anchor="end" font-size="10.6" fill="#1e293b" font-weight="700">{svg_esc(name)}</text>'
        if price <= base:
            bars += f'<rect x="{x0}" y="{y+2}" width="{w}" height="17" fill="#1e3a8a" rx="3" opacity="0.92"/>'
        else:
            extra_w = max(2.0, round(w - w_base, 1))
            bars += f'<rect x="{x0}" y="{y+2}" width="{w_base}" height="17" fill="#1e3a8a" opacity="0.82" rx="2"/>'
            bars += f'<rect x="{round(x_base+1,1)}" y="{y+2}" width="{max(1.5, round(extra_w-1,1))}" height="17" fill="{color}" rx="2" opacity="0.94"/>'
        bars += f'<text x="{round(x0+w+6,1)}" y="{y+15}" font-size="10.2" fill="{color}" font-weight="700">{price:,}元  {svg_esc(note)}</text>'

    chart_title = esc(f"图 {fig_num}：同样买 1 克真金，品牌金店比“银行金条 + 水贝加工”每克多花 {save_g} 元")
    return f'''
    <div class="chart-box">
      <div class="chart-title">{chart_title}</div>
      <div class="chart-sub">{cn_date}中国七大买金渠道克价实测（元/克 · 深蓝段为相同 {base} 元真金原料，彩色段为渠道税费与溢价）</div>
      <svg viewBox="0 0 640 292" width="100%" role="img" aria-label="{chart_title}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="640" height="292" fill="#ffffff" rx="6"/>
        {bars}
        {scale_svg}
        <line x1="{x_base}" y1="24" x2="{x_base}" y2="270" stroke="#1e3a8a" stroke-width="1.3" stroke-dasharray="4,3"/>
        <text x="{x_base}" y="16" text-anchor="middle" font-size="10.4" fill="#1e3a8a" font-weight="700">{time_word}国内原料基准 {base} 元/克</text>
      </svg>
      <div class="chart-note">数据来源：上海期货交易所/上金所基准（截至 {esc(as_short)}，原料 {base} 元/克）、四大行 APP 投资金条报价、周大福/老凤祥最新挂牌（约 {brand:,} 元/克）及财政部、税务总局《公告2025年第11号》与零售环节 5% 金银首饰消费税规定。买 50 克婚庆三金选“银行金条+加工”实省约 {int(ch['wedding_save_50g_rmb']):,} 元（省近 {save_pct:.1f}%）。</div>
    </div>
    '''


def svg_chart_48h_crash_and_weekend(fig_num: int = 3) -> str:
    """FROZEN Historical Case Study (Nov 18–24, 2026) — immutable constants prevent future snapshots from falsifying history!"""
    case_peak = 3690
    case_spot = 3635
    case_fair_usd = 3690
    case_fair_rmb = 791
    case_night_rmb = 786
    steps = [
        ("11/18", 68, 3850, "暴跌前\n高点", "above", 9, 3.5, "start"),
        ("11/19", 142, 3672, "利息飙\n破成本", "below", -10, -1.0, "end"),
        ("11/20午", 216, 3517, "亚股跌\n抽血", "below", 0, 0, "middle"),
        ("11/20晚", 290, 3590, "欧盘\n弱反弹", "above", 0, 0, "middle"),
        ("11/21晨", 364, 3503, "黑五\n双底", "below", 0, 0, "middle"),
        ("11/21收", 438, 3535, "周五\n终盘", "below", 0, 0, "middle"),
        ("11/24 00:30", 516, case_peak, "冲顶触及\n天花板", "above", 0, 0, "middle"),
        ("11/24 06:00", 594, case_spot, "官员表态\n回落收盘", "below", 0, 0, "middle"),
    ]

    def y_w(val: float) -> float:
        return round(218.0 - ((val - 3460.0) / 440.0) * 172.0, 1)

    grid = ""
    for val in [3500, 3600, 3700, 3800, 3900]:
        y = y_w(val)
        grid += f'<line x1="54" y1="{y}" x2="624" y2="{y}" stroke="#e2e8f0" stroke-width="0.9"/>'
        grid += f'<text x="48" y="{y+4}" text-anchor="end" font-size="10.6" fill="#64748b">${val:,}</text>'

    poly = " ".join(f"{x},{y_w(p)}" for _, x, p, *_ in steps)
    nodes = ""
    for idx, (tm, x, p, desc, pos, dx, dy, anc) in enumerate(steps):
        y = y_w(p)
        col = "#c2410c" if idx == 6 else ("#0f766e" if idx in (2, 4, 7) else "#1e3a5f")
        r = "5.0" if idx in (4, 6, 7) else "4.0"
        y_lbl = round((y - 10.0 if pos == "above" else y + 17.0) + dy, 1)
        x_lbl = round(x + dx, 1)
        nodes += f'<circle cx="{x}" cy="{y}" r="{r}" fill="{col}" stroke="#ffffff" stroke-width="1.3"/>'
        nodes += f'<text x="{x_lbl}" y="{y_lbl}" text-anchor="{anc}" font-size="10.8" fill="{col}" font-weight="800" {HALO}>${p:,}</text>'
        nodes += f'<text x="{x}" y="242" text-anchor="middle" font-size="10.2" fill="#0f172a" font-weight="700">{svg_esc(tm)}</text>'
        for li, dl in enumerate(desc.split("\n")):
            nodes += f'<text x="{x}" y="{257 + li*14}" text-anchor="middle" font-size="10.2" fill="#475569">{svg_esc(dl)}</text>'

    y_ceil = y_w(float(case_fair_usd))
    chart_title = esc(f"图 {fig_num}：经典复盘——从 11/21 跌到 $3,503 到 11/24 凌晨冲上 ${case_peak:,} 又回落")
    return f'''
    <div class="chart-box">
      <div class="chart-title">{chart_title}</div>
      <div class="chart-sub">2026 年 11 月 18–24 日流动性冲击与高利息天花板历史教学案例（国际现货金 · 美元/盎司 · 北京时间）</div>
      <svg viewBox="0 0 640 286" width="100%" role="img" aria-label="{chart_title}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="640" height="286" fill="#ffffff" rx="6"/>
        <rect x="336" y="34" width="130" height="188" fill="#fef2f2" opacity="0.65" rx="4"/>
        <text x="401" y="48" text-anchor="middle" font-size="10.4" fill="#991b1b" font-weight="700">周五恐慌抽血谷底</text>
        <rect x="492" y="34" width="128" height="188" fill="#fffbeb" opacity="0.72" rx="4"/>
        <text x="556" y="48" text-anchor="middle" font-size="10.4" fill="#92400e" font-weight="700">11/24 冲顶后回落</text>
        {grid}
        <line x1="54" y1="{y_ceil}" x2="624" y2="{y_ceil}" stroke="#b91c1c" stroke-width="1.5" stroke-dasharray="5,3"/>
        <text x="328" y="{round(y_ceil-6,1)}" text-anchor="end" font-size="10.4" fill="#b91c1c" font-weight="700" {HALO}>宏观合理价天花板 ~${case_fair_usd:,}</text>
        <polyline fill="none" stroke="#1e3a5f" stroke-width="2.5" points="{poly}"/>
        {nodes}
      </svg>
      <div class="chart-note">历史教学案例（固定基线 2026-11-24 07:30）：11/23–24 凌晨美股大涨解除强平抛压，推升金价 00:30 精准触及 ${case_peak:,}（折合约 {case_fair_rmb} 元/克），随后震荡回落并在 05:00 美联储官员强硬加息表态后压至 ${case_spot:,}（国内夜盘 02:30 先收 {case_night_rmb} 元/克，此后日盘随国际盘补跌）。</div>
    </div>
    '''


def _top_round_path(x: float, y: float, w: float, h: float, r: float = 6.0) -> str:
    return (
        f"M {x+r},{y} H {x+w-r} A {r},{r} 0 0 1 {x+w},{y+r} "
        f"V {y+h} H {x} V {y+r} A {r},{r} 0 0 1 {x+r},{y} Z"
    )


def svg_chart_mechanical_clock_and_switch(fig_num: int = 4) -> str:
    """Dynamic 2x2 Mechanical Calendar + Data-Driven 4-Step Traffic Light."""
    dfii_val = SNAP.get("dfii10_fred_official_pct")
    dfii = float(dfii_val if dfii_val is not None else SNAP["dfii10_live_pct"])
    sp = int(SNAP["spread_2y_ff_bp"])
    vix = float(SNAP["vix_close"])
    spot = int(SNAP["spot_gold_ny_close_rounded"])
    gate4_thr = int(round(float(SNAP.get("tier1_gate4_threshold_usd", 3690))))
    passed = int(SNAP.get("tier1_passed", 1))
    total = int(SNAP.get("tier1_total", 4))
    _, _, _, _, _, _, _, time_word = _as_of_meta()
    tier_sub = svg_esc(SNAP.get("tier_status_sub", f"{time_word}仅过 {passed}/{total} 关 · 红灯停，暂不新买"))
    dot_col, _ = _tier_dot_color(SNAP)

    default_cal = [
        {"title": "① 11月下旬（现在）· 感恩节前排雷期", "line1": "• 11/25 晚美国核心通胀 + 11/26 感恩节休市", "line2": "• 策略：管住手不追高，等靴子落地", "bg": "#fff7ed", "brd": "#fb923c", "hdr": "#c2410c", "txt": "#7c2d12"},
        {"title": "② 12/01 – 12/18 · 加息逆风砸坑期", "line1": "• 美欧英日四大央行 10 天内密集加息", "line2": "• 欧美机构年底卖亏本黄金抵税，容易砸出坑", "bg": "#fef2f2", "brd": "#f87171", "hdr": "#b91c1c", "txt": "#7f1d1d"},
        {"title": "③ 12/24 – 01/07 · 情绪拐点观察窗", "line1": "• 加息与年底抵税抛售结束，压力明显减轻", "line2": "• 盯着下方四步红绿灯，亮黄/绿再分批买", "bg": "#f0fdf4", "brd": "#4ade80", "hdr": "#15803d", "txt": "#14532d"},
        {"title": "④ 01/08 – 01/15 · 指数基金强制进货", "line1": "• 两大全球商品指数调高金银权重", "line2": "• 被动基金强制净买 33–48 亿美元金+25 亿银", "bg": "#dcfce7", "brd": "#15803d", "hdr": "#0f5132", "txt": "#14532d"},
    ]
    cal_cards = SNAP.get("mechanical_calendar") or default_cal

    cal_svg = ""
    coords = [(14, 29), (328, 29), (14, 104), (328, 104)]
    for idx, c in enumerate(cal_cards[:4]):
        cx, cy = coords[idx]
        sw = "1.6" if idx == 3 else "1.3"
        c_bg = sanitize_hex_color(c.get("bg"), "#f8fafc")
        c_brd = sanitize_hex_color(c.get("brd"), "#cbd5e1")
        c_hdr = sanitize_hex_color(c.get("hdr"), "#334155")
        c_txt = sanitize_hex_color(c.get("txt"), "#1f2937")
        cal_svg += (
            f'<rect x="{cx}" y="{cy}" width="298" height="66" fill="{c_bg}" stroke="{c_brd}" stroke-width="{sw}" rx="6"/>'
            f'<path d="{_top_round_path(cx, cy, 298, 22, 6)}" fill="{c_hdr}"/>'
            f'<text x="{cx+10}" y="{cy+15}" font-size="10.8" fill="#ffffff" font-weight="700">{svg_esc(c.get("title",""))}</text>'
            f'<text x="{cx+10}" y="{cy+38}" font-size="10.5" fill="{c_txt}" font-weight="{"700" if idx==3 else "400"}">{svg_esc(c.get("line1",""))}</text>'
            f'<text x="{cx+10}" y="{cy+55}" font-size="10.5" fill="{c_txt}">{svg_esc(c.get("line2",""))}</text>'
        )

    default_gates = [
        {"name": "第 1 关：真实利息降下来", "passed": False, "detail": f"{time_word} {dfii:.2f}%（需降到 2.72% 以下）"},
        {"name": "第 2 关：市场不再疯狂押加息", "passed": False, "detail": f"{time_word}高出 +{sp} 基点（需降到 +55 以内）"},
        {"name": "第 3 关：全球股市停止踩踏", "passed": True, "detail": f"恐慌指数降到 {vix:.1f}（已跌破 30 警戒线）"},
        {"name": "第 4 关：金价收盘站上关键高点", "passed": False, "detail": f"{time_word}收 ${spot:,}（需站稳 ${gate4_thr:,} 以上）"},
    ]
    gates = SNAP.get("tier1_gates") or default_gates

    gate_cards = ""
    for idx, g in enumerate(gates[:4]):
        ci = idx % 2
        ri = idx // 2
        x = 14 + ci * 312
        y = 216 + ri * 60
        ok = bool(g.get("passed", False))
        bg = "#f0fdf4" if ok else "#fef2f2"
        brd = "#16a34a" if ok else "#dc2626"
        tcol = "#166534" if ok else "#991b1b"
        badge = "✓ 已过关" if ok else "✕ 未过关"
        detail = g.get("detail") or f'{g.get("reading", "")}（{g.get("threshold", "")}）'
        gate_cards += (
            f'<rect x="{x}" y="{y}" width="300" height="52" fill="{bg}" stroke="{brd}" stroke-width="1.2" rx="6"/>'
            f'<text x="{x+10}" y="{y+18}" font-size="11.0" fill="{tcol}" font-weight="800">{svg_esc(g.get("name",""))}</text>'
            f'<rect x="{x+234}" y="{y+6}" width="58" height="16" fill="{brd}" rx="8"/>'
            f'<text x="{x+263}" y="{y+17.5}" text-anchor="middle" font-size="10.0" fill="#ffffff" font-weight="700">{badge}</text>'
            f'<text x="{x+10}" y="{y+38}" font-size="10.4" fill="#374151">{svg_esc(detail)}</text>'
        )

    chart_title = esc(f"图 {fig_num}：12 月中旬前仍是加息逆风期，明年 1 月中旬大基金强制进货才是顺风窗")
    return f'''
    <div class="chart-box">
      <div class="chart-title">{chart_title}</div>
      <div class="chart-sub">跨年资金节奏时间表（上）与买金四步红绿灯体检仪（下 · 当前满足 {passed}/{total} 项）</div>
      <svg viewBox="0 0 640 342" width="100%" role="img" aria-label="{chart_title}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="640" height="342" fill="#ffffff" rx="6"/>
        <text x="14" y="19" font-size="11.4" fill="#1e3a8a" font-weight="800">一、跨年资金节奏（先避开 12 月逆风，再看 1 月大资金强制买盘）</text>
        {cal_svg}
        <polygon points="316,57 324,62 316,67" fill="#94a3b8"/>
        <polygon points="316,132 324,137 316,142" fill="#15803d"/>
        <line x1="14" y1="184" x2="626" y2="184" stroke="#cbd5e1" stroke-width="1"/>
        <circle cx="20" cy="201" r="5" fill="{dot_col}"/>
        <text x="31" y="205" font-size="11.4" fill="#1e3a8a" font-weight="800">二、买金四步红绿灯体检仪（{tier_sub}）</text>
        {gate_cards}
      </svg>
      <div class="chart-note">数据来源：彭博商品指数、标普商品指数官方公告、法国兴业银行测算及美联储公开利率库。四关全亮（黄灯试买）才动首批 30% 预算，普通人无需每天盯盘猜底。</div>
    </div>
    '''


def svg_chart_institutional_targets(fig_num: int = 7) -> str:
    """Global Audited Institutions — data-driven rows, separated * vs † legend symbols, dynamic collision avoidance."""
    spot = int(SNAP["spot_gold_ny_close_rounded"])
    _, _, _, _, _, cn_date, _, time_word = _as_of_meta()

    COL_MAP = {"pt": "#0f766e", "avg": "#b45309", "horizon": "#475569", "stale": "#64748b"}
    default_banks = [
        {"name": "麦格理（27年均价）", "lo": 3500, "hi": 4600, "base": 4200, "kind": "avg"},
        {"name": "世界银行（27年均价）", "lo": 3650, "hi": 4600, "base": 4250, "kind": "avg"},
        {"name": "高盛（27年末·11月修）", "lo": 3500, "hi": 4800, "base": 4650, "kind": "pt"},
        {"name": "澳新银行（27年末）", "lo": 3400, "hi": 5200, "base": 4800, "kind": "pt"},
        {"name": "美国银行（27年均价）", "lo": 3700, "hi": 5000, "base": 4813, "kind": "avg"},
        {"name": "摩根大通（27年末）", "lo": 4500, "hi": 6000, "base": 5000, "kind": "pt"},
        {"name": "法国兴业（27年末）", "lo": 4200, "hi": 5400, "base": 5000, "kind": "pt", "annual_average_usd": 4625},
        {"name": "瑞银集团（27年末）", "lo": 3750, "hi": 5400, "base": 5000, "kind": "pt"},
        {"name": "花旗集团（6–12月）", "lo": 3500, "hi": 6000, "base": 5000, "kind": "horizon"},
        {"name": "汇丰银行（27年末）", "lo": 3950, "hi": 5300, "base": 5025, "kind": "pt"},
        {"name": "德意志银行（27均价·旧稿†）", "lo": 3950, "hi": 5600, "base": 5150, "kind": "stale"},
        {"name": "摩根士丹利（27年末）", "lo": 4200, "hi": 5600, "base": 5250, "kind": "pt"},
    ]
    banks = SNAP.get("institutional_targets") or default_banks
    pt_vals = [int(b["base"]) for b in banks if b.get("kind") == "pt"]
    avg_vals = [int(b["base"]) for b in banks if b.get("kind") == "avg"]
    avg_vals.extend(int(b["annual_average_usd"]) for b in banks if "annual_average_usd" in b)
    ye_med = statistics.median(pt_vals)
    avg_med = statistics.median(avg_vals)

    all_vals = [spot, ye_med, avg_med] + [int(b["hi"]) for b in banks] + [int(b["lo"]) for b in banks]
    x_min_val = min(3000.0, float((min(all_vals) // 500) * 500))
    x_max_val = max(6200.0, float(((max(all_vals) // 500) + 1) * 500))
    x_span = max(x_max_val - x_min_val, 1000.0)

    def x_p(val: float) -> float:
        return round(176.0 + ((val - x_min_val) / x_span) * 438.0, 1)

    row_h = 26
    top_y = 42
    bot_y = top_y + len(banks) * row_h + 4
    vb_h = bot_y + 50

    grid = ""
    for val in range(int(x_min_val), int(x_max_val), 500):
        x = x_p(val)
        if 170.0 <= x <= 622.0:
            grid += f'<line x1="{x}" y1="36" x2="{x}" y2="{bot_y}" stroke="#e2e8f0" stroke-width="0.8"/>'
            grid += f'<text x="{x}" y="{bot_y+15}" text-anchor="middle" font-size="10.4" fill="#64748b">${val:,}</text>'

    x_spot = x_p(spot)
    x_avg27 = x_p(avg_med)
    x_pt27 = x_p(ye_med)

    rows = ""
    for i, b in enumerate(banks):
        name = str(b["name"])
        lo, hi, base = int(b["lo"]), int(b["hi"]), int(b["base"])
        kind = str(b.get("kind", "pt"))
        col = COL_MAP.get(kind, "#0f766e")
        y = top_y + i * row_h
        x1, x2, xb = x_p(lo), x_p(hi), x_p(base)
        txt_fill = "#64748b" if kind == "stale" else "#1e293b"
        dash = ' stroke-dasharray="4,2"' if kind == "stale" else ""
        if i % 2 == 0:
            rows += f'<rect x="10" y="{y-2}" width="620" height="{row_h}" fill="#f8fafc"/>'
        rows += f'<text x="168" y="{y+14}" text-anchor="end" font-size="10.3" fill="{txt_fill}" font-weight="600">{svg_esc(name)}</text>'
        rows += f'<line x1="{x1}" y1="{y+10}" x2="{x2}" y2="{y+10}" stroke="{col}" stroke-width="4.2" opacity="0.25" stroke-linecap="round"{dash}/>'
        if kind == "pt":
            rows += f'<circle cx="{xb}" cy="{y+10}" r="4.6" fill="{col}"/>'
        else:
            pts = f"{xb},{y+4.8} {xb+5.0},{y+10} {xb},{y+15.2} {xb-5.0},{y+10}"
            rows += f'<polygon points="{pts}" fill="{col}"/>'
        lbl_str = f"${base:,}†" if kind == "stale" else f"${base:,}"
        near_med_left = (0 < (x_avg27 - xb) < 42) or (0 < (x_pt27 - xb) < 42)
        if near_med_left or xb > 560:
            lx, anc = round(xb - 9.0, 1), "end"
        else:
            lx, anc = round(xb + 9.0, 1), "start"
        rows += (
            f'<text x="{lx}" y="{y+14}" text-anchor="{anc}" font-size="10.2" fill="{col}" font-weight="700" '
            f'paint-order="stroke" stroke="#ffffff" stroke-width="4" stroke-linejoin="round">{lbl_str}</text>'
        )

    extra_avgs = [
        f"{str(b['name']).split('（')[0]}全年均价 ${int(b['annual_average_usd']):,}"
        for b in banks
        if "annual_average_usd" in b
    ]
    extra_avg_note = (
        f"{'、'.join(extra_avgs)} 计入均价统计，主标记为年末点位。"
        if extra_avgs
        else ""
    )
    leg_y = bot_y + 23
    stagger_spot = (x_avg27 - x_spot < 145.0) or (abs(x_pt27 - x_spot) < 135.0)
    x_spot_lbl = round(max(60.0, min(580.0, x_spot)), 1)
    y_spot_lbl = 13 if stagger_spot else 24
    y_med_lbl = 27 if stagger_spot else 24
    ref_y1 = 35 if stagger_spot else 34
    chart_title = esc(f"图 {fig_num}：{len(pt_vals)} 家年末点位记录的 2027 年金价中位为 ${ye_med:,.0f}")
    return f'''
    <div class="chart-box">
      <div class="chart-title">{chart_title}</div>
      <div class="chart-sub">2027 年末点位（青绿）、全年均价（琥珀）、其他期限及旧稿（灰色）· 美元/盎司</div>
      <svg viewBox="0 0 640 {vb_h}" width="100%" role="img" aria-label="{chart_title}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="640" height="{vb_h}" fill="#ffffff" rx="6"/>
        {grid}
        <line x1="{x_spot}" y1="{ref_y1}" x2="{x_spot}" y2="{bot_y}" stroke="#b91c1c" stroke-width="1.6" stroke-dasharray="5,3"/>
        <text x="{x_spot_lbl}" y="{y_spot_lbl}" text-anchor="middle" font-size="10.4" fill="#b91c1c" font-weight="800">{time_word} ${spot:,}</text>
        <line x1="{x_avg27}" y1="{ref_y1}" x2="{x_avg27}" y2="{bot_y}" stroke="#b45309" stroke-width="1.4" stroke-dasharray="4,3"/>
        <text x="{round(x_avg27-6,1)}" y="{y_med_lbl}" text-anchor="end" font-size="10.2" fill="#b45309" font-weight="700">均价记录中位 ${avg_med:,.0f}</text>
        <line x1="{x_pt27}" y1="{ref_y1}" x2="{x_pt27}" y2="{bot_y}" stroke="#0f766e" stroke-width="1.5" stroke-dasharray="4,3"/>
        <text x="{round(x_pt27+6,1)}" y="{y_med_lbl}" text-anchor="start" font-size="10.2" fill="#0f766e" font-weight="700">年末中位 ${ye_med:,.0f}</text>
        {rows}
        <rect x="14" y="{leg_y}" width="612" height="20" fill="#f8fafc" stroke="#e2e8f0" stroke-width="0.9" rx="4"/>
        <text x="320" y="{leg_y+14}" text-anchor="middle" font-size="10.0" fill="#334155">● 年末目标：{len(pt_vals)} 条记录 ｜ ◆ 全年均价：{len(avg_vals)} 条记录 ｜ 灰色为其他期限或旧稿</text>
      </svg>
      <div class="chart-note">取自 {esc(cn_date)} 主报告冻结记录。{esc(extra_avg_note)}花旗期限为 6–12 个月，德银为旧稿，两条单列。均价统计仅覆盖仓库中可辨认的 {len(avg_vals)} 条记录。</div>
    </div>
    '''


def svg_chart_fx_and_cross_ratios(fig_num: int = 6) -> str:
    """FX Ledger (exact spot %, sorted/deduped FX, dynamic scale) + 50Y Cross-Asset Ratios (both +/- capped with // slashes)."""
    base_rmb = float(SNAP["rmb_channels"]["etf_base_rmb"])
    fx_now = float(SNAP["usd_cny_short"])
    fx_med = float(SNAP.get("bank_2027_fx_median", 6.44))
    spot_exact = float(SNAP.get("spot_gold_ny_close_usd", SNAP["spot_gold_ny_close_rounded"]))
    ye_med = float(SNAP.get("bank_2027_yearend_median_usd", 5000))
    usd_up = ((ye_med - spot_exact) / spot_exact) * 100.0
    cr = SNAP.get("cross_ratios", {})
    as_short, _, _, _, mmdd, _, _, time_word = _as_of_meta()
    brent_v = float(SNAP["brent_settle_usd"])
    wti_v = float(SNAP["wti_settle_usd"])
    silver_v = float(SNAP["spot_silver_usd"])
    spx_v = float(SNAP["spx_close"])

    raw_fx = [
        ("6.25（若人民币强升）", 6.25, "#c2410c", False),
        ("6.30（高盛/德银预期）", 6.30, "#d97706", False),
        (f"{fx_med:.2f}（大行中位预期）", fx_med, "#b45309", True),
        (f"{fx_now:.2f}（维持{time_word}汇率）", fx_now, "#1e3a8a", True),
        ("6.90（若人民币偏弱）", 6.90, "#0f766e", False),
    ]
    fx_cases = []
    for item in sorted(raw_fx, key=lambda t: t[1]):
        if fx_cases and abs(item[1] - fx_cases[-1][1]) < 0.02:
            if item[3]:
                fx_cases[-1] = item
        else:
            fx_cases.append(item)

    x_lbl = 154.0
    x0 = 162.0
    max_rmb_val = max(base_rmb, max((ye_med / 31.1035) * fx for _, fx, _, _ in fx_cases))
    max_rmb = max(1200.0, float(((int(max_rmb_val) + 199) // 200) * 200))
    bar_max_w = 296.0

    def rmb_w(v: float) -> float:
        return round((v / max_rmb) * bar_max_w, 1)

    x_base_rmb = round(x0 + rmb_w(base_rmb), 1)
    top_bars = ""
    for i, (lbl, fx, col, hi) in enumerate(fx_cases):
        rmb_val = (ye_med / 31.1035) * fx
        gain = ((rmb_val - base_rmb) / base_rmb) * 100.0
        y = 38 + i * 29
        w = rmb_w(rmb_val)
        if hi:
            bg = "#fffbeb" if abs(fx - fx_med) < 0.01 else "#eff6ff"
            top_bars += f'<rect x="10" y="{y-3}" width="620" height="26" fill="{bg}" rx="3"/>'
        top_bars += f'<text x="{x_lbl}" y="{y+14}" text-anchor="end" font-size="10.6" fill="#1e293b" font-weight="{"800" if hi else "600"}">{svg_esc(lbl)}</text>'
        top_bars += f'<rect x="{x0}" y="{y+2}" width="{w}" height="16" fill="{col}" opacity="0.90" rx="3"/>'
        top_bars += f'<text x="{round(x0+w+7,1)}" y="{y+14}" font-size="10.6" fill="{col}" font-weight="700">{rmb_val:,.0f} 元/克（{gain:+.1f}%）</text>'

    ratios = [
        (f"金 / WTI油（{cr['gold_wti_ratio']:.1f}倍）", ((cr["gold_wti_ratio"] / 16.2) - 1.0) * 100.0, "#b91c1c"),
        (f"金 / 铂金（{cr['gold_platinum_ratio']:.2f}倍）", ((cr["gold_platinum_ratio"] / 1.00) - 1.0) * 100.0, "#c2410c"),
        (f"金 / 布伦特油（{cr['gold_brent_ratio']:.1f}倍）", ((cr["gold_brent_ratio"] / 17.0) - 1.0) * 100.0, "#d97706"),
        (f"金 / 白银（{cr['gold_silver_ratio']:.1f}倍）", ((cr["gold_silver_ratio"] / 62.3) - 1.0) * 100.0, "#b45309"),
        (f"金 / 美股标普（{cr['gold_spx_ratio']:.3f}）", ((cr["gold_spx_ratio"] / 0.725) - 1.0) * 100.0, "#0f766e"),
    ]

    x_zero = 232.0
    px_per_100 = 117.5
    pos_cap = 200.0
    neg_cap = 58.0
    bot_grid = ""
    for tv in (-50, 0, 50, 100, 150, 200):
        tx = round(x_zero + (tv / 100.0) * px_per_100, 1)
        if tv != 0:
            bot_grid += f'<line x1="{tx}" y1="226" x2="{tx}" y2="376" stroke="#e2e8f0" stroke-width="0.8" stroke-dasharray="2,3"/>'
        lbl_t = "0%（中位）" if tv == 0 else f"{tv:+d}%"
        bot_grid += f'<text x="{tx}" y="393" text-anchor="middle" font-size="9.8" fill="{"#334155" if tv==0 else "#64748b"}" font-weight="{"700" if tv==0 else "400"}">{lbl_t}</text>'

    bot_bars = f'{bot_grid}<line x1="{x_zero}" y1="226" x2="{x_zero}" y2="376" stroke="#334155" stroke-width="1.3"/>'
    for i, (lbl, dev, col) in enumerate(ratios):
        y = 232 + i * 29
        bot_bars += f'<text x="{x_lbl}" y="{y+14}" text-anchor="end" font-size="10.6" fill="#1e293b" font-weight="600">{svg_esc(lbl)}</text>'
        if dev >= 0:
            capped = dev > pos_cap
            w = round((min(dev, pos_cap) / 100.0) * px_per_100, 1)
            bot_bars += f'<rect x="{x_zero}" y="{y+2}" width="{w}" height="16" fill="{col}" opacity="0.88" rx="3"/>'
            if capped:
                mx = round(x_zero + w - 14.0, 1)
                bot_bars += (
                    f'<line x1="{mx-4}" y1="{y+18}" x2="{mx+1}" y2="{y+2}" stroke="#ffffff" stroke-width="2.2"/>'
                    f'<line x1="{mx+1}" y1="{y+18}" x2="{mx+6}" y2="{y+2}" stroke="#ffffff" stroke-width="2.2"/>'
                )
            bot_bars += f'<text x="{round(x_zero+w+7,1)}" y="{y+14}" font-size="10.6" fill="{col}" font-weight="700">+{dev:.0f}% 偏贵</text>'
        else:
            capped = abs(dev) > neg_cap
            w = round((min(abs(dev), neg_cap) / 100.0) * px_per_100, 1)
            bx = round(x_zero - w, 1)
            bot_bars += f'<rect x="{bx}" y="{y+2}" width="{w}" height="16" fill="{col}" opacity="0.90" rx="3"/>'
            if capped:
                mx = round(bx + 14.0, 1)
                bot_bars += (
                    f'<line x1="{mx-4}" y1="{y+18}" x2="{mx+1}" y2="{y+2}" stroke="#ffffff" stroke-width="2.2"/>'
                    f'<line x1="{mx+1}" y1="{y+18}" x2="{mx+6}" y2="{y+2}" stroke="#ffffff" stroke-width="2.2"/>'
                )
            bot_bars += f'<text x="{round(x_zero+8,1)}" y="{y+14}" font-size="10.6" fill="{col}" font-weight="700">{dev:.0f}% 偏便宜</text>'

    chart_title = esc(f"图 {fig_num}：人民币若升值会吃掉约 5–8 个百分点涨幅；且黄金相对原油、白银并不算全面便宜")
    return f'''
    <div class="chart-box">
      <div class="chart-title">{chart_title}</div>
      <div class="chart-sub">上：国际金涨到 ${ye_med:,.0f} 时的国内克价（0 元起诚实比例，对比{time_word} {base_rmb:.0f} 元）｜ 下：相对 50 年历史比价位置</div>
      <svg viewBox="0 0 640 406" width="100%" role="img" aria-label="{chart_title}" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="640" height="406" fill="#ffffff" rx="6"/>
        <text x="14" y="20" font-size="11.2" fill="#1e3a8a" font-weight="800">一、汇率账本：如果国际金涨到 ${ye_med:,.0f}（美元涨 +{usd_up:.1f}%），你手里的人民币金能赚多少？</text>
        {top_bars}
        <line x1="{x_base_rmb}" y1="32" x2="{x_base_rmb}" y2="182" stroke="#1e3a8a" stroke-width="1.3" stroke-dasharray="4,3"/>
        <text x="{x_base_rmb}" y="195" text-anchor="middle" font-size="10.2" fill="#1e3a8a" font-weight="700">{time_word} {base_rmb:.0f} 元</text>

        <line x1="14" y1="205" x2="626" y2="205" stroke="#cbd5e1" stroke-width="1"/>
        <text x="14" y="221" font-size="11.2" fill="#1e3a8a" font-weight="800">二、50 年跨资产比价尺：黄金目前仅相对高估美股便宜，相对油/铂/银仍明显偏贵</text>
        {bot_bars}
      </svg>
      <div class="chart-note">数据来源：中国外汇交易中心（{mmdd} 汇率 {fx_now:.2f}）、各大行 2027 汇率预测及 {esc(as_short)} 国际大宗与美股收盘（布油 ${brent_v:.2f}、WTI ${wti_v:.2f}、白银 ${silver_v:.2f}、标普 {spx_v:,.0f}）。</div>
    </div>
    '''


def make_sequential_chart_map() -> dict:
    """Assign strictly sequential 图 1 .. 图 7 based on actual appearance order in the Master Markdown."""
    counter = [0]

    def _wrap(fn):
        def _run():
            counter[0] += 1
            return fn(fig_num=counter[0])
        return _run

    return {
        "<!-- CHART_1 -->": [_wrap(svg_chart_real_vs_nominal)],
        "<!-- CHART_2 -->": [_wrap(svg_chart_2026_bear_and_vacuum)],
        "<!-- CHART_1_AND_2 -->": [_wrap(svg_chart_real_vs_nominal), _wrap(svg_chart_2026_bear_and_vacuum)],
        "<!-- CHART_3 -->": [_wrap(svg_chart_china_tax_channels)],
        "<!-- CHART_4 -->": [_wrap(svg_chart_48h_crash_and_weekend)],
        "<!-- CHART_5 -->": [_wrap(svg_chart_mechanical_clock_and_switch)],
        "<!-- CHART_6 -->": [_wrap(svg_chart_institutional_targets)],
        "<!-- CHART_7 -->": [_wrap(svg_chart_fx_and_cross_ratios)],
    }


# ==============================================================================
# 2. MARKDOWN TO HTML CONVERTER (Uses Shared Parser from build_daily.py!)
# ==============================================================================

def convert_md_to_html_body(md_text: str, docx_mode: bool = False) -> tuple[str, list[tuple[str, str]]]:
    _, _, body_html, docx_charts = parse_markdown_to_html(
        md_text,
        docx_mode=docx_mode,
        break_layer3=True,
        chart_map=make_sequential_chart_map(),
        skip_doc_title=True,
    )
    return body_html, docx_charts


def build_cover_html() -> str:
    ch = SNAP["rmb_channels"]
    spot = int(SNAP["spot_gold_ny_close_rounded"])
    peak = int(round(float(SNAP["spot_gold_intraday_high_usd"])))
    peak_26 = float(SNAP.get("spot_gold_2026_peak_usd", 5595.62))
    dd_pct = abs((spot - peak_26) / peak_26) * 100.0
    dfii_val = SNAP.get("dfii10_fred_official_pct")
    dfii = float(dfii_val if dfii_val is not None else SNAP["dfii10_live_pct"])
    dfii_lvl = str(SNAP.get("dfii10_level_short", "20年高位"))
    passed = int(SNAP["tier1_passed"])
    total = int(SNAP["tier1_total"])
    ye_med = int(SNAP.get("bank_2027_yearend_median_usd", 5000))
    fx_med = float(SNAP.get("bank_2027_fx_median", 6.44))
    ye_rmb_med = int(round((ye_med / 31.1035) * fx_med))
    tier_lbl = str(SNAP.get("tier_label", "红灯停")).split("（")[0]
    tier_cover_sub = str(SNAP.get("tier_cover_sub") or SNAP.get("tier_status_sub") or "暂不新买 · 按四步红绿灯执行")
    _, dot_cls = _tier_dot_color(SNAP)
    peak_prefix = "近期冲"

    return f"""
<div class="cover-banner" style="border-bottom:4px solid #b45309;">
  <div class="cover-tag">黄金跨世纪周期全景指南（1971–2030） ｜ 数据基线 {esc(REPORT_SHORT_DATE)}</div>
  <div class="cover-title">黄金跨世纪周期与普通人全景配置指南（1971–2030）</div>
  <div class="cover-meta">
    <strong>基准时点</strong>：{esc(REPORT_TIMESTAMP)} &nbsp;|&nbsp;
    <strong>阅读建议</strong>：前 5 分钟看清结论、买金通道与钱包账，后面按需深读宏观原理与专业复核数据
  </div>
  <div class="kpi-strip">
    <div class="kpi-card">
      <div class="kpi-label">国内原料价 / 品牌金店</div>
      <div class="kpi-val">{ch['etf_base_rmb']} 元/克</div>
      <div class="kpi-sub">银行条 {ch['bank_bar_rmb']} 元 · 品牌金店 {ch['brand_store_rmb']:,} 元</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">国际现货金（美元/盎司）</div>
      <div class="kpi-val">${spot:,}</div>
      <div class="kpi-sub">{peak_prefix} ${peak:,} 回落 · 较年初顶 -{dd_pct:.0f}%</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">买金四步红绿灯</div>
      <div class="kpi-val"><span class="dot {dot_cls}"></span>{esc(tier_lbl)}（{passed}/{total} 关）</div>
      <div class="kpi-sub">{esc(tier_cover_sub)}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">当下最大压制：真实利息</div>
      <div class="kpi-val">{dfii:.2f}%（{esc(dfii_lvl)}）</div>
      <div class="kpi-sub">扣通胀存钱利息过高，压住金价上限</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">普通家庭配置锚 / 渠道</div>
      <div class="kpi-val">总资产 10%–15%</div>
      <div class="kpi-sub">首选 0.2% 费率基金 · 婚庆省 {ch['wedding_save_per_g_rmb']} 元</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">机构 2027 年末点位中位</div>
      <div class="kpi-val">${ye_med:,}（约 {ye_rmb_med:,} 元）</div>
      <div class="kpi-sub">已按汇率升至 {fx_med:.2f} 扣除汇兑影响</div>
    </div>
  </div>
</div>
"""


def main():
    parser = argparse.ArgumentParser(description="Verify Gold Master Report baseline & snapshot (web-only renderer).")
    parser.add_argument("--check", action="store_true", help="Self-check MASTER_BASELINE lock & snapshot.")
    parser.add_argument("--snapshot", type=Path, default=None, help="Explicitly override snapshot JSON path.")
    parser.add_argument("--allow-drift", action="store_true", help="Bypass MASTER_BASELINE timestamp match check.")
    args = parser.parse_args()
    if not MD_PATH.exists():
        raise SystemExit(f"ERROR: Master MD missing: {MD_PATH}")
    md_txt = MD_PATH.read_text(encoding="utf-8")
    snap_chk, snap_path = load_master_snapshot(md_txt, args.snapshot, allow_drift=args.allow_drift)
    print(
        f"OK: build_report.py verified ({snap_path.name}, as_of={snap_chk.get('as_of_short')}, web-only renderer ready)."
    )


if __name__ == "__main__":
    main()
