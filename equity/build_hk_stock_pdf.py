#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the standalone Hong Kong Stock Market Flagship Manual (PDF + Pure-Python ECMA-376 DOCX)
with 7 bespoke 850px colorblind-safe vector SVGs (CHART_H1 through CHART_H7).

Also exports svg_chart_h1..h7(meta_override) for build_daily.py HK daily editions.
"""

from __future__ import annotations

import html as html_mod
import json
import sys
from pathlib import Path

from pdf_common import (
    BASE_DIR,
    CHROME_BIN,
    atomic_copy,
    build_theme_css,
    clean_svg_text,
    norm_chart_title as _norm_chart_title,
    render_cover_banner,
    render_docx_atomic,
    render_md_body,
    render_pdf_atomic,
    run_lint_gate,
    svg_shape,
)

OUT_DIR = BASE_DIR
META_PATH = OUT_DIR / "report_meta_hk_stock.json"
HTML_PDF_PATH = OUT_DIR / ".tmp_hk_stock_pdf.html"
TMP_PDF_PATH = OUT_DIR / ".tmp_hk_stock.pdf"


def _svg_esc(val: object) -> str:
    return html_mod.escape(clean_svg_text(str(val)))


def load_meta(meta_override: dict | None = None) -> dict:
    """Strictly isolate daily meta_override from current flagship JSON (zero historical pollution)."""
    if meta_override:
        return meta_override
    if META_PATH.exists():
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    return {}


def resolve_flagship_paths(meta: dict) -> tuple[Path, Path, Path]:
    slug = str(meta.get("period_slug", "2026_11")).strip() or "2026_11"
    md_path = OUT_DIR / f"hk_stock_market_report_{slug}.md"
    pdf_path = OUT_DIR / f"hk_stock_market_report_{slug}.pdf"
    docx_path = OUT_DIR / f"hk_stock_market_report_{slug}.docx"
    return md_path, pdf_path, docx_path


def _read_hkma_bal_100m(cl: dict) -> float:
    """Read HKMA Aggregate Balance in 100M HKD (亿港元), supporting legacy key safely."""
    if cl.get("hkma_agg_bal_hkd_100m") is not None:
        return float(cl["hkma_agg_bal_hkd_100m"])
    if cl.get("hkma_agg_bal_hkd_b") is not None:
        val = float(cl["hkma_agg_bal_hkd_b"])
        return val * 10.0 if val < 200.0 else val
    return 540.78


def svg_chart_h1_cycles(meta_override: dict | None = None) -> str:
    """Chart H1: 2016-2026 Hang Seng Index Proportional Time-Axis Cycles, MA200 & Southbound Rise."""
    cl = load_meta(meta_override).get("chart_live", {})
    h1 = cl.get("h1") if isinstance(cl.get("h1"), dict) else {}
    hsi = float(cl.get("hsi", 22265.68))
    hsi_200d = float(cl.get("hsi_200d", 23515))
    as_short = str(cl.get("as_of_short", "2026/11/25午"))
    cur_yr = float(cl.get("as_of_year_float", 2026.905))
    ma200_gap = ((hsi - hsi_200d) / hsi_200d) * 100.0
    peak_dd = ((hsi - 28056.0) / 28056.0) * 100.0

    title = _norm_chart_title(
        h1.get("title") or f"港股十年五轮周期与南向定价权崛起：{hsi:,.0f} 点为何不是 2022 式流动性崩塌"
    )
    sub = html_mod.escape(clean_svg_text(str(
        h1.get("sub") or f"恒生指数 2016–{as_short} 真实时间跨度拐点与 200 日年线 {hsi_200d:,.0f} 点 ｜ 南向日均占比跃升至 22%–25%"
    )))
    gap_desc = f"下方 {abs(ma200_gap):.1f}%" if ma200_gap < 0 else f"上方 {ma200_gap:.1f}%"
    takeaway = html_mod.escape(clean_svg_text(str(
        h1.get("takeaway") or f"恒指自 2026 年 1 月高点 28,056 回撤 {abs(peak_dd):.1f}% 至 {hsi:,.0f} 点，仍压在 200 日年线{gap_desc}，但南向年内净买逾 4,300 亿港元叠加 1,370 亿回购托底，显著区别于 2022 年 14,597 点的流动性枯竭。"
    )))
    note = html_mod.escape(clean_svg_text(str(
        h1.get("note") or "数据来源：恒生指数公司、港交所、Wind（横轴严格按实际年份比例绘制）。"
    )))

    raw_pts = [
        (2016.12, 18278, "16/02底 18,278", "below", "#009E73"),
        (2018.06, 33484, "18/01顶 33,484", "above", "#D55E00"),
        (2020.22, 21139, "20/03底 21,139", "below", "#009E73"),
        (2021.13, 31183, "21/02顶 31,183", "above", "#D55E00"),
        (2022.82, 14597, "22/10极底 14,597", "below", "#D55E00"),
        (2024.06, 14794, "24/01双底 14,794", "below", "#009E73"),
        (2026.06, 28056, "26/01顶 28,056", "above", "#0072B2"),
        (max(2026.88, cur_yr), hsi, f"{as_short[-5:]} {hsi:,.0f}", "above", "#0F766E"),
    ]
    min_yr = 2016.12
    max_yr = max(2026.90, cur_yr)
    y_min, y_max = 12000.0, 36000.0
    top_y, bot_y = 42.0, 238.0

    def map_x(yr: float) -> float:
        return round(72.0 + ((yr - min_yr) / (max_yr - min_yr)) * 736.0, 1)

    def map_y(v: float) -> float:
        return round(bot_y - (v - y_min) / (y_max - y_min) * (bot_y - top_y), 1)

    pts = [(map_x(yr), v, lbl, pos, col) for yr, v, lbl, pos, col in raw_pts]
    poly = " ".join(f"{x:.1f},{map_y(v):.1f}" for x, v, _, _, _ in pts)
    area = f"{pts[0][0]},{bot_y} " + poly + f" {pts[-1][0]},{bot_y}"
    y_200d = map_y(hsi_200d)

    grid = ""
    for tv in (15000, 20000, 25000, 30000, 35000):
        yy = map_y(tv)
        grid += (
            f'<line x1="58" y1="{yy:.1f}" x2="824" y2="{yy:.1f}" stroke="#e2e8f0" stroke-width="0.9"/>'
            f'<text x="52" y="{yy+3.5:.1f}" text-anchor="end" font-size="9.2" fill="#64748b">{tv:,}</text>'
        )

    nodes = ""
    for idx, (x, v, lbl, pos, col) in enumerate(pts):
        yy = map_y(v)
        dy = -11 if pos == "above" else 15
        if idx == 6:
            anc, dx = "end", -6
        elif idx == len(pts) - 1:
            anc, dx = "end", 8
            dy = 16 if abs(yy - y_200d) < 20 else -11
        elif idx == 0:
            anc, dx = "start", 0
        else:
            anc, dx = "middle", 0
        r = 5.2 if idx == len(pts) - 1 else 4.0
        lbl_esc = _svg_esc(lbl)
        nodes += (
            f'<circle cx="{x}" cy="{yy:.1f}" r="{r}" fill="{col}" stroke="#ffffff" stroke-width="1.5"/>'
            f'<text x="{x+dx:.1f}" y="{yy+dy:.1f}" text-anchor="{anc}" font-size="9.0" fill="{col}" font-weight="700">{lbl_esc}</text>'
        )

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      <div class="chart-sub">{sub}</div>
      <svg viewBox="0 0 850 288" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="288" fill="#ffffff" rx="6"/>
        <rect x="58" y="42" width="766" height="196" fill="#f8fafc"/>
        {grid}
        <line x1="58" y1="{y_200d:.1f}" x2="824" y2="{y_200d:.1f}" stroke="#D97706" stroke-width="1.4" stroke-dasharray="5,3"/>
        <rect x="62" y="{y_200d-17:.1f}" width="268" height="14" fill="#ffffff" opacity="0.88" rx="3"/>
        <text x="66" y="{y_200d-6:.1f}" text-anchor="start" font-size="9.0" fill="#B45309" font-weight="700">200日年线 {hsi_200d:,.0f} 点（强弱分水岭，现处{gap_desc}）</text>
        <polygon points="{area}" fill="#0d9488" opacity="0.11"/>
        <polyline points="{poly}" fill="none" stroke="#0f766e" stroke-width="2.4" stroke-linejoin="round"/>
        {nodes}
        <rect x="58" y="255" width="766" height="24" fill="#f0fdfa" stroke="#99f6e4" stroke-width="0.9" rx="4"/>
        <text x="441" y="270.5" text-anchor="middle" font-size="9.0" fill="#115e59" font-weight="700">南向港股通成交占比跃升：2017–19 年约 5%–6% → 2021 年破 20% → 2026 年稳居 22%–25%（年内净买逾 4,300 亿 + 回购 1,370 亿）</text>
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway}</div>
      <div class="chart-note">{note}</div>
    </div>
    '''


def svg_chart_h2_flow_and_rebalance(meta_override: dict | None = None) -> str:
    """Chart H2: HK Core Indices + Liquidity/Short Ratio + 11/30 MSCI vs 12/04 HSI+HSTECH Rebalance."""
    cl = load_meta(meta_override).get("chart_live", {})
    h2 = cl.get("h2") if isinstance(cl.get("h2"), dict) else {}
    as_short = str(cl.get("as_of_short", "2026/11/25午"))

    title = _norm_chart_title(
        h2.get("title") or f"{as_short} 港股指数分化、高沽空逼空与 12/04 恒生季检 125 亿美元资金流"
    )
    sub = html_mod.escape(clean_svg_text(str(
        h2.get("sub") or "左：核心指数涨跌（夜期以琥珀警示冬季 03:00 盲窗） ｜ 右：南向承接、沽空比与 11/30–12/04 被动调仓大撞车"
    )))
    takeaway = html_mod.escape(clean_svg_text(str(
        h2.get("takeaway") or "港股当前处“高沽空释压 + 南向 V 型抄底”的左侧磨底期；11/30 MSCI 剔除 15 只港股先压尾盘，12/04 恒生系列合并季检（恒指权重调整 + 恒科 30 扩 50）合计触发超 125 亿美元双向被动资金重构。"
    )))
    note = html_mod.escape(clean_svg_text(str(
        h2.get("note") or "数据来源：恒生指数公司、港交所、高盛测算、MSCI 官网（截至 2026-11-25 午盘实盘）。"
    )))

    indices = h2.get("indices") or [
        ["恒生指数 (22,266)", 0.21, -13.1],
        ["恒生国企 (7,487)", 0.46, -16.0],
        ["恒生科技 (3,474)", 0.20, -37.0],
        ["中国高息 (3,867)", -0.85, 6.2],
        ["恒指夜期 (03:00)", 0.72, 0.0],
    ]
    max_abs = max([abs(float(r[1])) for r in indices[:5]] + [1.2])
    px_per_pct = 76.0 / max_abs
    bars = ""
    y0 = 56
    for idx, row in enumerate(indices[:5]):
        nm, d_pct, ytd = str(row[0]), float(row[1]), float(row[2])
        yy = y0 + idx * 37
        zero_x = 248.0
        w = max(4.0, min(82.0, abs(d_pct) * px_per_pct))
        is_blind = ("夜期" in nm) or (ytd == 0.0)
        col = "#D97706" if is_blind else ("#009E73" if d_pct >= 0 else "#D55E00")
        bx = zero_x if d_pct >= 0 else zero_x - w
        tx = zero_x + w + 5 if d_pct >= 0 else zero_x - w - 5
        anc = "start" if d_pct >= 0 else "end"
        ytd_str = "冬季03:00盲窗(勿轻信)" if is_blind else f"年内 {ytd:+.1f}%"
        bars += (
            f'<text x="16" y="{yy+14}" font-size="9.1" fill="#0f172a" font-weight="700">{_svg_esc(nm)}</text>'
            f'<text x="16" y="{yy+27}" font-size="8.4" fill="{"#B45309" if is_blind else "#64748b"}">{_svg_esc(ytd_str)}</text>'
            f'<rect x="{bx:.1f}" y="{yy+4}" width="{w:.1f}" height="15" fill="{col}" rx="2.5"/>'
            f'<text x="{tx:.1f}" y="{yy+15}" text-anchor="{anc}" font-size="9.0" fill="{col}" font-weight="700">{d_pct:+.2f}%</text>'
        )

    cards = h2.get("cards") or [
        ("资金与沽空实时水位", "#0F766E", "#F0FDFA", [
            "11/25 半日成交 1,065 亿｜南向 V 反转净买超 50 亿",
            "沽空比逾 20% 诱发小米(+4.1%)/B站(+9.2%)逼空",
            "EPFR 外资周净流入 +7.9 亿美元（被动 +6.3 亿）",
        ]),
        ("11/30 尾盘 · MSCI 半年度调整", "#B91C1C", "#FEF2F2", [
            "MSCI 中国仅新纳 1 港股（中际旭创 03308）",
            "集中剔除 15 只港股（金沙/龙湖/名创/赣锋等）",
            "风险：16:06–16:10 竞价不可撤单，防被动砸盘",
        ]),
        ("12/04 尾盘 · 恒生系列合并季检（超 125 亿美元）", "#1D4ED8", "#EFF6FF", [
            "恒指权重调整：影响汇丰/建行等重磅金融蓝筹",
            "恒科 30→50 零剔除净增 20 股（宁德 H 居首 2.17%）",
            "净流入：阿里/腾讯/宁德 H ｜ 摊薄：小米/美团",
        ]),
    ]
    right_xml = ""
    cy = 42
    for hdr, col, bg, lines in cards[:3]:
        right_xml += (
            f'<rect x="404" y="{cy}" width="432" height="71" fill="{bg}" stroke="{col}" stroke-width="1" rx="5"/>'
            f'<text x="416" y="{cy+17}" font-size="9.3" fill="{col}" font-weight="800">{_svg_esc(hdr)}</text>'
        )
        for li, ln in enumerate(lines[:3]):
            right_xml += f'<text x="416" y="{cy+33+li*15}" font-size="8.8" fill="#1f2937">• {_svg_esc(ln)}</text>'
        cy += 78

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      <div class="chart-sub">{sub}</div>
      <svg viewBox="0 0 850 286" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="286" fill="#ffffff" rx="6"/>
        <text x="16" y="25" font-size="9.8" fill="#0f172a" font-weight="800">A. 港股核心指数实盘分化（{_svg_esc(as_short)}）</text>
        <text x="404" y="25" font-size="9.8" fill="#0f172a" font-weight="800">B. 流动性温度与 11/30–12/04 被动调仓冲击</text>
        <rect x="12" y="42" width="380" height="226" fill="#f8fafc" stroke="#e2e8f0" stroke-width="0.9" rx="5"/>
        <line x1="248" y1="50" x2="248" y2="258" stroke="#94a3b8" stroke-width="1.1"/>
        {bars}
        {right_xml}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway}</div>
      <div class="chart-note">{note}</div>
    </div>
    '''


def svg_chart_h3_peg_and_erp(meta_override: dict | None = None) -> str:
    """Chart H3: HKMA Linked Exchange Rate Thin Buffer + A/HK/US 3-Market Forward ERP Ruler."""
    cl = load_meta(meta_override).get("chart_live", {})
    h3 = cl.get("h3") if isinstance(cl.get("h3"), dict) else {}
    usdhkd = float(cl.get("usd_hkd", 7.842))
    agg_bal = _read_hkma_bal_100m(cl)
    hibor1m = float(cl.get("hibor_1m_pct", 2.88))
    sofr = float(cl.get("sofr_pct", 3.92))
    us10y = float(cl.get("us10y_pct", 4.901))

    title = _norm_chart_title(
        h3.get("title") or "港股“美息分母 × 中国分子”双锚图：联汇紧绷线与 A/港/美三市赔率比价尺"
    )
    sub = html_mod.escape(clean_svg_text(str(
        h3.get("sub") or f"上：港汇 {usdhkd:.3f} 贴 7.85 弱方线、总结余 {agg_bal:.1f} 亿港元 ｜ 下：三市前瞻盈利收益率减无风险利率（越高越便宜）"
    )))
    takeaway = html_mod.escape(clean_svg_text(str(
        h3.get("takeaway") or f"恒指相对中国国债的风险溢价高达 +8.1% 至 +8.7%（驱动南向年内净买逾 4,300 亿），相对美债亦远胜标普 500（+0.88%）；但 11/25 1M 港元拆息连涨 4 日至 {hibor1m:.2f}% 且总结余仅 {agg_bal:.1f} 亿，须防 12/10 联储加息引发抽水。"
    )))
    note = html_mod.escape(clean_svg_text(str(
        h3.get("note") or "数据来源：香港金管局(HKMA)、香港银行公会(HKAB 11/25 11:15 定盘)、NY Fed、FRED、中金/高盛。"
    )))

    peg_ratio = max(0.0, min(1.0, (usdhkd - 7.75) / 0.10))
    peg_x = 40.0 + peg_ratio * 370.0
    bal_ratio = max(0.0, min(1.0, agg_bal / 2000.0))
    bal_x = 450.0 + bal_ratio * 370.0
    bal_warn_x = 450.0 + (400.0 / 2000.0) * 370.0

    erps = h3.get("erps") or [
        ("恒生指数 · 人民币南向锚（vs 1.58% 国债）", 8.13, "#009E73"),
        ("沪深 300 · A 股前瞻锚（vs 1.58% 国债）", 5.85, "#0D9488"),
        (f"恒生指数 · 外资美元锚（vs {us10y:.2f}% 美债）", 4.81, "#0072B2"),
        (f"标普 500 · 美股前瞻锚（vs {us10y:.2f}% 美债）", 0.88, "#D55E00"),
    ]
    erp_bars = ""
    ey0 = 158
    for idx, (lbl, val, col) in enumerate(erps[:4]):
        yy = ey0 + idx * 30
        bw = max(6.0, (float(val) / 10.0) * 440.0)
        erp_bars += (
            f'<text x="34" y="{yy+14}" font-size="9.1" fill="#0f172a" font-weight="700">{_svg_esc(lbl)}</text>'
            f'<rect x="312" y="{yy+3}" width="{bw:.1f}" height="15" fill="{col}" rx="3"/>'
            f'<text x="{312+bw+7:.1f}" y="{yy+14}" font-size="9.2" fill="{col}" font-weight="800">+{float(val):.2f}%</text>'
        )

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      <div class="chart-sub">{sub}</div>
      <svg viewBox="0 0 850 296" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="296" fill="#ffffff" rx="6"/>
        <rect x="20" y="14" width="405" height="106" fill="#fef2f2" stroke="#fecaca" stroke-width="1" rx="6"/>
        <text x="34" y="34" font-size="9.4" fill="#991b1b" font-weight="800">阀门 1：联系汇率 美元/港元 = {usdhkd:.3f}（紧贴 7.85 弱方线！）</text>
        <rect x="40" y="50" width="370" height="14" fill="#e2e8f0" rx="7"/>
        <rect x="40" y="50" width="{peg_x-40:.1f}" height="14" fill="#dc2626" opacity="0.82" rx="7"/>
        <circle cx="{peg_x:.1f}" cy="57" r="7" fill="#991b1b" stroke="#ffffff" stroke-width="2"/>
        <text x="40" y="81" font-size="8.8" fill="#166534" font-weight="700">7.75 强方流入</text>
        <text x="225" y="81" text-anchor="middle" font-size="8.8" fill="#475569">7.80 中枢</text>
        <text x="410" y="81" text-anchor="end" font-size="8.8" fill="#991b1b" font-weight="800">7.85 弱方抽水</text>
        <text x="34" y="105" font-size="8.8" fill="#7f1d1d" font-weight="600">1个月港元拆息 {hibor1m:.2f}% vs 美元隔夜 {sofr:.2f}%（利差 {hibor1m-sofr:+.2f}%）</text>

        <rect x="435" y="14" width="395" height="106" fill="#fffbeb" stroke="#fde68a" stroke-width="1" rx="6"/>
        <text x="450" y="34" font-size="9.4" fill="#92400e" font-weight="800">阀门 2：金管局银行总结余 = {agg_bal:.1f} 亿港元（薄缓冲水位）</text>
        <rect x="450" y="50" width="370" height="14" fill="#e2e8f0" rx="7"/>
        <rect x="450" y="50" width="{bal_x-450:.1f}" height="14" fill="#d97706" rx="7"/>
        <line x1="{bal_warn_x:.1f}" y1="45" x2="{bal_warn_x:.1f}" y2="70" stroke="#dc2626" stroke-width="1.8"/>
        <text x="{bal_warn_x:.1f}" y="82" text-anchor="middle" font-size="8.6" fill="#dc2626" font-weight="800">400亿警戒线</text>
        <text x="820" y="82" text-anchor="end" font-size="8.6" fill="#475569">2,000亿宽裕</text>
        <text x="450" y="105" font-size="8.8" fill="#78350f" font-weight="600">若 12/10 联储加息致总结余破 400 亿 → 拆息恐破 4.0%–4.5%</text>

        <text x="24" y="146" font-size="9.8" fill="#0f172a" font-weight="800">A / 港 / 美三市前瞻 / 滚动股权风险溢价（盈利收益率 − 10 年国债利率）跨市比价尺</text>
        <rect x="20" y="152" width="810" height="132" fill="#f8fafc" stroke="#e2e8f0" stroke-width="0.9" rx="6"/>
        {erp_bars}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway}</div>
      <div class="chart-note">{note}</div>
    </div>
    '''


def svg_chart_h4_clock(meta_override: dict | None = None) -> str:
    """Chart H4: HK Next 90-Day Policy & Rebalance Calendar + Score-Bound Water-Temp Switch."""
    cl = load_meta(meta_override).get("chart_live", {})
    h4 = cl.get("h4") if isinstance(cl.get("h4"), dict) else {}
    score = float(cl.get("score", 2.0))
    tier_short = str(cl.get("tier_short", f"红灯防守期 ({score:g} / 6 分)"))
    st1 = str(cl.get("status_line1", f"当前灯号：{tier_short} ｜ 离岸仓位上限 ≤ 35%（境内港股通 ≤ 25%）"))
    st2 = str(cl.get("status_line2", "防踏空升级线：恒指连 3 日放量收站 23,515 点且港汇脱离 7.845 弱方红线"))

    if score < 3.0:
        b_fill, b_brd, b_t1, b_t2 = "#fef2f2", "#dc2626", "#991b1b", "#7f1d1d"
    elif score < 4.5:
        b_fill, b_brd, b_t1, b_t2 = "#fffbeb", "#d97706", "#92400e", "#78350f"
    else:
        b_fill, b_brd, b_t1, b_t2 = "#f0fdf4", "#009E73", "#166534", "#14532d"

    title = _norm_chart_title(
        h4.get("title") or "港股跨年 90 天“政策×筹码”四道排雷关与红绿灯总开关"
    )
    sub = html_mod.escape(clean_svg_text(str(
        h4.get("sub") or "盯紧 11/30 MSCI、12/04 恒生季检、12/07 美对外投资规则、12/10 联储联汇与 2027 一季度黄金清算"
    )))
    takeaway = html_mod.escape(clean_svg_text(str(
        h4.get("takeaway") or "11 月底至 12 月中旬同时密集撞上被动调仓、美国对外投资规则征询截止与美联储加息联汇大考，先守红利底座，等 12 月 21 日后联汇压力缓和再解锁硬科技主攻池。"
    )))
    note = html_mod.escape(clean_svg_text(str(
        h4.get("note") or "全部时间已换算为北京时间；12/24 与 12/31 为港股半日市（12:00 收，无夜盘），12/28 周一正常开市。"
    )))

    cards = h4.get("cards") or [
        {"header": "第 1 关：11/30–12/04 调仓潮", "color": "#B91C1C", "bg": "#FEF2F2", "border": "#FCA5A5", "items": [
            "11/30 MSCI 剔 15 港股尾盘放量", "12/04 恒指+恒科 50 超 125 亿流", "16:06 后收盘竞价禁撤单勿追高"]},
        {"header": "第 2 关：12/07–12/18 双重考", "color": "#B45309", "bg": "#FFFBEB", "border": "#FCD34D", "items": [
            "12/07 美对外投资限令征询截止", "12/10 联储加息→金管局升至 4.50%", "盯 7.85 弱方与 400 亿总结余底线"]},
        {"header": "第 3 关：12/21–12/31 解锁窗", "color": "#0F766E", "bg": "#F0FDFA", "border": "#99F6E4", "items": [
            "中央经济工作会 + 四大央行落地", "12/24 半日 / 12/25 休 / 12/28 开", "企稳 23,515 点后解锁蓝钻主攻"]},
        {"header": "第 4 关：2027 一季度催化", "color": "#1D4ED8", "bg": "#EFF6FF", "border": "#93C5FD", "items": [
            "香港黄金中央清算 Q1 启动试行", "美对外投资终稿(不迟于 3/13)", "2027 年中人民币柜台与房托窗口"]},
    ]
    cards_xml = ""
    for i, c in enumerate(cards[:4]):
        cx = 16 + i * 206
        cards_xml += (
            f'<rect x="{cx}" y="14" width="198" height="128" fill="{c["bg"]}" stroke="{c["border"]}" stroke-width="1.1" rx="6"/>'
            f'<rect x="{cx}" y="14" width="198" height="24" fill="{c["color"]}" rx="5"/>'
            f'<text x="{cx+99}" y="30" text-anchor="middle" font-size="9.0" fill="#ffffff" font-weight="800">{_svg_esc(c["header"])}</text>'
        )
        for j, it in enumerate(c.get("items", [])[:3]):
            cards_xml += f'<text x="{cx+8}" y="{56+j*26}" font-size="8.6" fill="#1f2937">• {_svg_esc(it)}</text>'

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      <div class="chart-sub">{sub}</div>
      <svg viewBox="0 0 850 218" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="218" fill="#ffffff" rx="6"/>
        {cards_xml}
        <rect x="16" y="154" width="818" height="52" fill="{b_fill}" stroke="{b_brd}" stroke-width="1.3" rx="6"/>
        <text x="30" y="175" font-size="9.4" fill="{b_t1}" font-weight="800">{html_mod.escape(clean_svg_text(st1))}</text>
        <text x="30" y="195" font-size="8.9" fill="{b_t2}" font-weight="600">{html_mod.escape(clean_svg_text(st2))}</text>
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway}</div>
      <div class="chart-note">{note}</div>
    </div>
    '''


def svg_chart_h5_targets_and_scenarios(meta_override: dict | None = None) -> str:
    """Chart H5: 2027 Major Bank Targets vs 4-Scenario Integer-Dot Probability Tree."""
    cl = load_meta(meta_override).get("chart_live", {})
    h5 = cl.get("h5") if isinstance(cl.get("h5"), dict) else {}
    hsi = float(cl.get("hsi", 22265.68))

    title = _norm_chart_title(
        h5.get("title") or "2027 年各大行恒指目标共识（25,000–26,000）与四大情景剧本"
    )
    sub = html_mod.escape(clean_svg_text(str(
        h5.get("sub") or f"左：中外 7 大投行 2027 恒指目标（对照现价 {hsi:,.0f}） ｜ 右：2027 年四套整数 10 点概率剧本（合计 100%）"
    )))
    takeaway = html_mod.escape(clean_svg_text(str(
        h5.get("takeaway") or "大摩、瑞银、中金、中信一致锚定 25,000–26,000 点（+12% 至 +17%），高盛超配离岸看 +23%，花旗最乐观至 30,500；但若联汇抽水叠加美滞胀，大摩熊市线 17,200 仍是必须用仓位守住的底线。"
    )))
    note = html_mod.escape(clean_svg_text(str(
        h5.get("note") or "数据来源：花旗、高盛、摩根士丹利、瑞银、中金、中信 2026 年 11 月下旬公开 2027 年度展望。"
    )))

    banks = h5.get("banks") or [
        ("花旗 (2027年中)", 30500, "#009E73"),
        ("高盛 (隐含+23%)", 27330, "#0D9488"),
        ("摩根士丹利 (基准)", 26000, "#0072B2"),
        ("瑞银 UBS (基准)", 26000, "#0072B2"),
        ("中信证券 (基准)", 25500, "#475569"),
        ("中金公司 (基准)", 25500, "#475569"),
        ("大摩极端熊市线", 17200, "#D55E00"),
    ]
    bars = ""
    base_x = 142.0
    max_w = 258.0
    cur_x = base_x + (hsi - 14000) / (33000 - 14000) * max_w
    for idx, (nm, tgt, col) in enumerate(banks[:7]):
        yy = 48 + idx * 30
        bw = max(8.0, (float(tgt) - 14000) / (33000 - 14000) * max_w)
        chg = (float(tgt) / hsi - 1) * 100
        bars += (
            f'<text x="136" y="{yy+14}" text-anchor="end" font-size="9.0" fill="#0f172a" font-weight="700">{_svg_esc(nm)}</text>'
            f'<rect x="{base_x:.1f}" y="{yy+3}" width="{bw:.1f}" height="14" fill="{col}" rx="2.5"/>'
            f'<text x="{base_x+bw+5:.1f}" y="{yy+14}" font-size="8.8" fill="{col}" font-weight="700">{int(tgt):,} ({chg:+.0f}%)</text>'
        )

    scenarios = h5.get("scenarios") or [
        ("主剧本 A：先蹲后起温和修复", 50, "25,000–26,500 (+12%~+19%)", "#0F766E"),
        ("乐观 B：美息拐头+红利税减免", 20, "28,500–30,500 (+28%~+37%)", "#009E73"),
        ("承压 C：联汇抽水+地缘升级", 20, "17,200–19,500 (-12%~-23%)", "#D55E00"),
        ("磨底 D：高息拉锯红利独舞", 10, "20,500–23,800 (-8%~+7%)", "#D97706"),
    ]
    max_prob = max([50.0] + [float(s[1]) for s in scenarios[:4]])
    sc_xml = ""
    sy = 50
    for nm, prob, rng, col in scenarios[:4]:
        prob_f = float(prob)
        pw = min(320.0, (prob_f / max_prob) * 290.0)
        dots_n = max(1, int(round(prob_f / 10.0)))
        sc_xml += (
            f'<text x="488" y="{sy+12}" font-size="9.0" fill="#0f172a" font-weight="800">{_svg_esc(nm)}（10次约{dots_n}次）</text>'
            f'<rect x="488" y="{sy+18}" width="320" height="12" fill="#e2e8f0" rx="4"/>'
            f'<rect x="488" y="{sy+18}" width="{pw:.1f}" height="12" fill="{col}" rx="4"/>'
            f'<text x="488" y="{sy+43}" font-size="8.6" fill="{col}" font-weight="700">区间：{_svg_esc(rng)} ｜ 概率 {prob_f:g}%</text>'
        )
        sy += 54

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      <div class="chart-sub">{sub}</div>
      <svg viewBox="0 0 850 280" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="280" fill="#ffffff" rx="6"/>
        <text x="16" y="25" font-size="9.6" fill="#0f172a" font-weight="800">A. 2027 年大行恒指目标点位（虚线为现价 {hsi:,.0f}）</text>
        <text x="488" y="25" font-size="9.6" fill="#0f172a" font-weight="800">B. 2027 四大情景剧本（概率之和 = 100%）</text>
        <rect x="12" y="38" width="456" height="228" fill="#f8fafc" stroke="#e2e8f0" stroke-width="0.9" rx="5"/>
        <line x1="{cur_x:.1f}" y1="42" x2="{cur_x:.1f}" y2="260" stroke="#0f172a" stroke-width="1.2" stroke-dasharray="3,3"/>
        {bars}
        <rect x="478" y="38" width="356" height="228" fill="#f8fafc" stroke="#e2e8f0" stroke-width="0.9" rx="5"/>
        {sc_xml}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway}</div>
      <div class="chart-note">{note}</div>
    </div>
    '''


def svg_chart_h6_ah_arbitrage_and_sectors(meta_override: dict | None = None) -> str:
    """Chart H6: AH Premium Arbitrage Routing Bar Chart + HK Sector Strength Strip."""
    cl = load_meta(meta_override).get("chart_live", {})
    h6 = cl.get("h6") if isinstance(cl.get("h6"), dict) else {}
    hsahp = float(cl.get("hsahp", 137.62))

    title = _norm_chart_title(
        h6.get("title") or f"双账户 AH 价差路由真相（溢价指数 {hsahp:.1f}）：中芯 A 股贵 2 倍，宁德/招行 H 股反倒挂！"
    )
    sub = html_mod.escape(clean_svg_text(str(
        h6.get("sub") or "按最新 A/H 价差核算：(A 股 / H 股折人民币) − 1 ｜ 正值买 H 股省钱，负值（倒挂）坚决买 A 股！"
    )))
    takeaway = html_mod.escape(clean_svg_text(str(
        h6.get("takeaway") or "切忌盲信“港股一定比 A 股便宜”！中芯（+202%）、华虹（+224%）、中海油（+66%）、工行（+37.4%）买离岸 H 股大幅省钱；但宁德（-21.1%，11/25 午盘已跌超 6% 兑现警告）、药明康德（-10.3%）、中际（-8.1%）及招行（-5.0%）H 股反贵，有 A 股账户者优先买 A 股！"
    )))
    note = html_mod.escape(clean_svg_text(str(
        h6.get("note") or "数据口径：A/H 最新官方收盘与 11/25 午盘实盘，超 +100% 柱条采用 // 断轴示意以免挤压常规标的。"
    )))
    sector_strip = html_mod.escape(clean_svg_text(str(
        h6.get("sector_strip") or "11/25 港股板块强弱：互联网逼空领涨（B站 +9.2% / 小米 +4.1% / 阿里 +0.6%） ｜ 本地高息公用稳健 ｜ 芯片与倒挂新能源重挫（华虹 -12%+ / 宁德 H -6%+）"
    )))

    items = h6.get("items") or [
        ("华虹半导体 (01347)", 223.8, "离岸 H 股折价 -69%"),
        ("中芯国际 (00981)", 201.6, "离岸 H 股折价 -67%"),
        ("中国电信 (00728)", 85.3, "H 股 20% 税具优势"),
        ("中国海油 (00883)", 66.1, "离岸 10% 税完胜港股通 28%"),
        ("中国移动 (00941)", 58.2, "离岸 10% 税完胜港股通 28%"),
        ("比亚迪 (01211)", 47.2, "离岸折价显著"),
        ("中国神华 (01088)", 44.7, "H 股高息优势显著"),
        ("工商银行 (01398)", 38.6, "H 股高息优势显著"),
        ("紫金矿业 (02899)", 16.0, "价差收窄两地中性"),
        ("招商银行 (03968)", -4.5, "倒挂！买 A 股 600036 更省"),
        ("中际旭创 (03308)", -8.1, "倒挂！买 A 股 300308 更省"),
        ("宁德时代 (03750)", -21.1, "深倒挂！买 A 股 300750 省两成"),
    ]
    zero_x = 296.0
    cap_pos = 100.0
    pos_px_per_pct = 2.60
    neg_px_per_pct = 3.50

    rows_xml = ""
    for idx, (nm, pct, tag) in enumerate(items[:12]):
        yy = 42 + idx * 24
        pct_f = float(pct)
        if pct_f >= 0:
            draw_pct = min(pct_f, cap_pos)
            bw = max(6.0, draw_pct * pos_px_per_pct)
            col = "#009E73" if pct_f >= 35 else "#0072B2"
            rows_xml += f'<rect x="{zero_x:.1f}" y="{yy+3}" width="{bw:.1f}" height="14" fill="{col}" rx="2"/>'
            if pct_f > cap_pos:
                bx = zero_x + bw - 22
                rows_xml += f'<line x1="{bx:.1f}" y1="{yy+2}" x2="{bx+6:.1f}" y2="{yy+18}" stroke="#ffffff" stroke-width="2.4"/><line x1="{bx+6:.1f}" y1="{yy+2}" x2="{bx+12:.1f}" y2="{yy+18}" stroke="#ffffff" stroke-width="2.4"/>'
            rows_xml += (
                f'<text x="{zero_x+bw+6:.1f}" y="{yy+14}" font-size="8.8" fill="{col}" font-weight="800">+{pct_f:.1f}%</text>'
                f'<text x="628" y="{yy+14}" font-size="8.6" fill="#334155">{_svg_esc(tag)}</text>'
            )
        else:
            bw = max(10.0, min(95.0, abs(pct_f) * neg_px_per_pct))
            col = "#D55E00"
            rows_xml += (
                f'<rect x="{zero_x-bw:.1f}" y="{yy+3}" width="{bw:.1f}" height="14" fill="{col}" rx="2"/>'
                f'<text x="{zero_x-bw-6:.1f}" y="{yy+14}" text-anchor="end" font-size="8.8" fill="{col}" font-weight="800">{pct_f:.1f}%</text>'
                f'<text x="628" y="{yy+14}" font-size="8.6" fill="#991b1b" font-weight="700">{_svg_esc(tag)}</text>'
            )
        rows_xml += f'<text x="16" y="{yy+14}" font-size="8.9" fill="#0f172a" font-weight="700">{_svg_esc(nm)}</text>'

    strip_y = 46 + len(items[:12]) * 24 + 4
    svg_h = strip_y + 32
    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      <div class="chart-sub">{sub}</div>
      <svg viewBox="0 0 850 {svg_h}" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="{svg_h}" fill="#ffffff" rx="6"/>
        <text x="16" y="24" font-size="9.2" fill="#0f172a" font-weight="800">双地核心标的</text>
        <text x="296" y="24" text-anchor="middle" font-size="9.0" fill="#475569" font-weight="700">← H 股更贵(倒挂) ｜ A 股更贵(买 H 省钱) →</text>
        <text x="628" y="24" font-size="9.2" fill="#0f172a" font-weight="800">双账户最优路由结论</text>
        <line x1="{zero_x:.1f}" y1="34" x2="{zero_x:.1f}" y2="{strip_y-6}" stroke="#64748b" stroke-width="1.2"/>
        {rows_xml}
        <rect x="14" y="{strip_y}" width="822" height="24" fill="#f0fdfa" stroke="#99f6e4" stroke-width="0.9" rx="4"/>
        <text x="425" y="{strip_y+15.5}" text-anchor="middle" font-size="8.8" fill="#115e59" font-weight="700">{sector_strip}</text>
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway}</div>
      <div class="chart-note">{note}</div>
    </div>
    '''


DEFAULT_H7_POINTS = [
    ("中海油/中石油 6x", 104, 68, "g", "#009E73", 9, 4, "start"),
    ("工行/建行/中银 7-9x", 124, 98, "g", "#009E73", 9, 4, "start"),
    ("紫金H 7.8x(防铜)", 114, 152, "b", "#0072B2", 9, 4, "start"),
    ("腾讯 11x", 224, 70, "g", "#009E73", 9, 4, "start"),
    ("阿里 12x(锚75)", 242, 102, "b", "#0072B2", 9, 4, "start"),
    ("汇丰/渣打 12x", 268, 52, "g", "#009E73", 9, 4, "start"),
    ("中电/神华/中移动", 258, 130, "g", "#009E73", 9, 4, "start"),
    ("友邦/平安H 14x", 336, 90, "g", "#009E73", 9, 4, "start"),
    ("比亚迪H 15x", 352, 152, "b", "#0072B2", 9, 4, "start"),
    ("宁德H 16x(倒挂)", 474, 86, "b", "#0072B2", 9, 4, "start"),
    ("中际H 20x(倒挂)", 538, 66, "b", "#0072B2", 9, 4, "start"),
    ("港交所 23x(息4%)", 568, 118, "b", "#0072B2", 9, 4, "start"),
    ("药明/信达生物", 652, 140, "b", "#0072B2", 9, 4, "start"),
    ("百济神州 48x", 734, 96, "b", "#0072B2", -9, 4, "end"),
    ("中国宏桥(28%税)", 128, 206, "y", "#D97706", 9, 4, "start"),
    ("小米(逼空/存储压)", 320, 198, "y", "#D97706", 9, 4, "start"),
    ("美团(待11/27报)", 468, 204, "y", "#D97706", 9, 4, "start"),
    ("中芯H 43x(较A折67%)", 642, 196, "y", "#D97706", 9, 4, "start"),
    ("老铺黄金(11/27除净)", 142, 248, "r", "#D55E00", 9, 4, "start"),
    ("周大福(主营-18%)", 318, 246, "r", "#D55E00", 9, 4, "start"),
    ("金沙中国(MSCI剔除)", 502, 248, "r", "#D55E00", 9, 4, "start"),
    ("泡泡玛特(Q3-48%)", 742, 246, "r", "#D55E00", -9, 4, "end"),
]


def svg_chart_h7_stock_quadrant(meta_override: dict | None = None) -> str:
    """Chart H7: Representative HK Stocks 4-Quadrant Map (Okabe-Ito color+shape encoding)."""
    cl = load_meta(meta_override).get("chart_live", {})
    h7 = cl.get("h7") if isinstance(cl.get("h7"), dict) else {}
    pool_cnt = int(cl.get("stock_pool_count", 45))
    pts = h7.get("points") or DEFAULT_H7_POINTS

    title = _norm_chart_title(
        h7.get("title") or f"港股精选代表龙头四象限地图（全量 {pool_cnt} 只见下表）：左边真便宜，底下避业绩与剔除雷！"
    )
    sub = html_mod.escape(clean_svg_text(str(
        h7.get("sub") or "横轴：估值从左到右由便宜到贵（严格对齐同股 A/H 物理市盈率） ｜ 纵轴：现金流与政策护城河越扎实"
    )))
    takeaway = html_mod.escape(clean_svg_text(str(
        h7.get("takeaway") or "左上角集齐全球罕见的“低估值高现金流底座”（汇丰/渣打/中电/中海油/工行/中移动/腾讯/友邦）；中芯 H 股实为 43 倍（较 A 股折价 67%），而宁德与中际 H 股因较 A 股倒挂溢价须等回调或转买 A 股；下方老铺/周大福/金沙/泡泡玛特暴露雷区。"
    )))
    note = html_mod.escape(clean_svg_text(str(
        h7.get("note") or "数据口径：2026-11-25 午盘实盘与最新财报（同股 A/H 采用统一汇率与 TTM 口径，颜色+形状双编码）。"
    )))

    dots = ""
    for nm, x, y, sh, col, dx, dy, anc in pts:
        dots += svg_shape(str(sh), float(x), float(y), str(col))
        dots += f'<text x="{float(x)+float(dx)}" y="{float(y)+float(dy)}" text-anchor="{anc}" font-size="8.8" fill="{col}" font-weight="700">{html_mod.escape(clean_svg_text(str(nm)))}</text>'

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title}</div>
      <div class="chart-sub">{sub}</div>
      <svg viewBox="0 0 850 326" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="326" fill="#ffffff" rx="6"/>
        <rect x="34" y="34" width="406" height="134" fill="#f0fdf4" opacity="0.72"/>
        <rect x="440" y="34" width="394" height="134" fill="#eff6ff" opacity="0.72"/>
        <rect x="34" y="168" width="406" height="108" fill="#fffbeb" opacity="0.68"/>
        <rect x="440" y="168" width="394" height="108" fill="#fef2f2" opacity="0.76"/>
        <line x1="440" y1="34" x2="440" y2="276" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,3"/>
        <line x1="34" y1="168" x2="834" y2="168" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,3"/>
        <rect x="34" y="34" width="800" height="242" fill="none" stroke="#cbd5e1" stroke-width="1"/>
        <text x="44" y="49" font-size="9.0" fill="#166534" font-weight="800">● 便宜真现金流底座（当下低吸/收息首选）</text>
        <text x="824" y="49" text-anchor="end" font-size="9.0" fill="#1e40af" font-weight="800">◆ 优质成长/A+H倒挂区（等回调或改买A股）</text>
        <text x="44" y="268" font-size="9.0" fill="#92400e" font-weight="800">▲ 成本冲击/税务/周期观察（勿盲抄）</text>
        <text x="824" y="268" text-anchor="end" font-size="9.0" fill="#991b1b" font-weight="800">× 业绩降速/失真/MSCI剔除雷区（回避！）</text>
        <text x="34" y="24" font-size="9.0" fill="#475569" font-weight="700">↑ 纵轴越高 = 自由现金流、回购与政策护城河越扎实</text>
        <text x="44" y="294" font-size="8.8" fill="#475569" font-weight="600">← 深度低估（6–15 倍）</text>
        <text x="440" y="294" text-anchor="middle" font-size="8.8" fill="#475569" font-weight="600">估值分界（约 18–22 倍 / 倒挂线）</text>
        <text x="824" y="294" text-anchor="end" font-size="8.8" fill="#b91c1c" font-weight="600">高估/亏损博弈 →</text>
        {dots}
        <rect x="34" y="302" width="800" height="19" fill="#f8fafc" stroke="#e2e8f0" stroke-width="0.7" rx="3"/>
        <text x="434" y="315" text-anchor="middle" font-size="8.8" fill="#334155" font-weight="600">图例：<tspan fill="#009E73" font-weight="800">●</tspan> 当下底座 ｜ <tspan fill="#0072B2" font-weight="800">◆</tspan> 未来主攻（已上锁） ｜ <tspan fill="#D97706" font-weight="800">▲</tspan> 分歧观察 ｜ <tspan fill="#D55E00" font-weight="800">×</tspan> 高危回避</text>
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway}</div>
      <div class="chart-note">{note}</div>
    </div>
    '''


def run_check() -> None:
    assert Path(CHROME_BIN).exists(), f"Chrome missing: {CHROME_BIN}"
    import bs4  # noqa: F401
    from PIL import Image  # noqa: F401
    assert META_PATH.exists(), f"Missing {META_PATH}"
    meta = load_meta()
    md_path, _, _ = resolve_flagship_paths(meta)
    assert md_path.exists(), f"Missing {md_path}"
    print(f"HK-Stock builder check OK: {md_path.name} (Chrome + bs4 + Pillow ready)")


def main() -> None:
    args = sys.argv[1:]
    if "--check" in args:
        run_check()
        return
    no_lint = "--no-lint" in args
    no_docx = "--no-docx" in args
    meta = load_meta()
    md_path, pdf_path, docx_path = resolve_flagship_paths(meta)
    report_md = md_path.read_text(encoding="utf-8")
    print(f"Loaded HK-Stock MD ({len(report_md)} chars): {md_path}")
    run_lint_gate(report_md, str(md_path), is_flagship=True, meta=meta, no_lint=no_lint)

    cover_html, doc_title, page_footer, footer_note = render_cover_banner(
        meta, "中国香港股市跨周期全景手册", "港股全景研究手册", "中国香港股市跨周期全景研究手册", meta_label="阅读说明"
    )
    charts = {
        "<!-- CHART_H1 -->": svg_chart_h1_cycles(meta),
        "<!-- CHART_H2 -->": svg_chart_h2_flow_and_rebalance(meta),
        "<!-- CHART_H3 -->": svg_chart_h3_peg_and_erp(meta),
        "<!-- CHART_H4 -->": svg_chart_h4_clock(meta),
        "<!-- CHART_H5 -->": svg_chart_h5_targets_and_scenarios(meta),
        "<!-- CHART_H6 -->": svg_chart_h6_ah_arbitrage_and_sectors(meta),
        "<!-- CHART_H7 -->": svg_chart_h7_stock_quadrant(meta),
    }
    _, body_pdf = render_md_body(report_md, charts, is_flagship=True)
    css_final = build_theme_css("hk_stock", page_footer, is_flagship=True)
    full_pdf_html = (
        f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html_mod.escape(doc_title)}</title><style>{css_final}</style></head>"
        f'<body>{cover_html}{body_pdf}<div class="footer-note">{html_mod.escape(footer_note)}</div></body></html>'
    )
    render_pdf_atomic(full_pdf_html, pdf_path, HTML_PDF_PATH, TMP_PDF_PATH)
    print(f"Wrote PDF ({pdf_path.stat().st_size:,} bytes): {pdf_path}")

    if not no_docx:
        render_docx_atomic(full_pdf_html, docx_path, market="hk_stock", footer_title=page_footer)
        print(f"Wrote native OOXML DOCX ({docx_path.stat().st_size:,} bytes): {docx_path}")

    latest_md = OUT_DIR / "hk_stock_market_report_latest.md"
    latest_pdf = OUT_DIR / "hk_stock_market_report_latest.pdf"
    latest_docx = OUT_DIR / "hk_stock_market_report_latest.docx"
    atomic_copy(md_path, latest_md)
    atomic_copy(pdf_path, latest_pdf)
    if not no_docx and docx_path.exists():
        atomic_copy(docx_path, latest_docx)
        print(f"Synced: {latest_md}, {latest_pdf} & {latest_docx}")
    else:
        print(f"Synced: {latest_md} & {latest_pdf}")


if __name__ == "__main__":
    main()
