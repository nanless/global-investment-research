#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pure-web Vector SVG chart renderer for the China A-Share Cross-Cycle Handbook & Dailies.
Exports svg_chart_a1..a7(meta_override) consumed by scripts/build_site.py and equity/build_daily.py.
"""

from __future__ import annotations

import html as html_mod
import json
import sys
from pathlib import Path

from pdf_common import (
    BASE_DIR,
    clean_svg_text,
    norm_chart_title as _norm_chart_title,
    sanitize_hex_color,
    sanitize_svg_anchor,
    svg_shape,
)

OUT_DIR = BASE_DIR
META_PATH = OUT_DIR / "report_meta_a_share.json"

DEFAULT_A_SECTORS = [
    {"name": "传媒", "pct": 4.43, "flow": 21.0, "camp": "hot"},
    {"name": "通信", "pct": 4.34, "flow": 67.7, "camp": "hot"},
    {"name": "机械设备", "pct": 4.04, "flow": 28.0, "camp": "hot"},
    {"name": "有色金属", "pct": 3.00, "flow": 16.3, "camp": "hot"},
    {"name": "汽车", "pct": 2.47, "flow": 20.1, "camp": "base"},
    {"name": "计算机", "pct": 2.41, "flow": -1.4, "camp": "hot"},
    {"name": "医药生物", "pct": 2.39, "flow": 3.5, "camp": "hot"},
    {"name": "电子", "pct": 2.12, "flow": 73.8, "camp": "hot"},
    {"name": "电力设备", "pct": 1.74, "flow": 2.1, "camp": "base"},
    {"name": "家用电器", "pct": 0.54, "flow": 12.9, "camp": "def"},
    {"name": "非银金融", "pct": -0.73, "flow": 4.6, "camp": "base"},
    {"name": "银行(逆势吸金)", "pct": -0.80, "flow": 17.3, "camp": "def"},
    {"name": "公用事业", "pct": -0.87, "flow": -0.6, "camp": "def"},
    {"name": "煤炭", "pct": -1.17, "flow": 0.6, "camp": "def"},
    {"name": "石油石化", "pct": -1.25, "flow": 4.5, "camp": "def"},
    {"name": "食品饮料", "pct": -1.32, "flow": 3.9, "camp": "base"},
]

DEFAULT_A_INDICES = [
    ("科创50 (芯片权重)", 1.81, "#c2410c"),
    ("科创综指 (硬科技)", 1.16, "#c2410c"),
    ("上证50 (超大盘)", 0.45, "#c2410c"),
    ("上证指数 (大盘)", 0.27, "#c2410c"),
    ("沪深300 (蓝筹)", 0.14, "#c2410c"),
    ("创业板指 (成长股)", -0.05, "#0f766e"),
    ("北证50 (小微成长)", -0.22, "#0f766e"),
    ("中证1000 (小盘股)", -0.23, "#0f766e"),
    ("中证500 (中盘股)", -0.27, "#0f766e"),
    ("深证成指", -0.29, "#0f766e"),
    ("中证红利 (000922)", -0.81, "#0f766e"),
]

_A2_COOL_COLORS = frozenset({
    "#0f766e", "#009e73", "#115e59", "#15803d", "#16a34a",
    "#0072b2", "#0d9488", "#047857", "#134e4a", "#064e3b",
})
_A2_WARM_COLORS = frozenset({
    "#c2410c", "#d55e00", "#b91c1c", "#dc2626", "#ef4444",
    "#9f2326", "#c94a4a", "#dc5c4b", "#e67e22", "#f0934b",
})

DEFAULT_A_FUTURES = [
    ("小盘股期货 (中证1000 · IM)", 18.0, "11/24 官结 5,730.2（年化贴水 -18.0%，减仓 2.8 万手）", "空头压力仍重但开始减仓，严禁追小盘题材", "#D55E00", "#fef2f2"),
    ("中盘股期货 (中证500 · IC)", 19.7, "11/24 官结 6,033.4（年化贴水 -19.7%，减仓 1.5 万手）", "中盘贴水最深，对冲资金谨慎，维持逢高减仓思路", "#D55E00", "#fef2f2"),
    ("大蓝筹期货 (沪深300 · IF)", 14.2, "11/24 官结 3,921.0（前 20 席位晚刊核验）", "大蓝筹贴水相对温和，紧盯 4,025 点 4 年成本线", "#0072B2", "#eff6ff"),
    ("超大盘期货 (上证50 · IH)", 14.5, "11/24 官结 2,747.0（前 20 席位晚刊核验）", "银行高股息与国家队护盘托底，防守韧性居前", "#009E73", "#f0fdf4"),
]

DEFAULT_A4_CARDS = [
    {
        "header": "11/25–11/30（先防波动）",
        "color": "#ea580c",
        "bg": "#fff7ed",
        "border": "#fb923c",
        "items": [
            ("• 11/25 央行净投放 +3,210 亿稳跨月", "#7c2d12", True),
            ("• 11/28 商务部暂缓对美两用禁令", "#7c2d12", False),
            ("• 11/30 保证金降 80% + 剔 22 股", "#9a3412", True),
            ("→ 平稳后试探加 0.5 成(红利+转债)", "#047857", True),
        ],
    },
    {
        "header": "12/01–12/18（解禁+外围议息）",
        "color": "#dc2626",
        "bg": "#fef2f2",
        "border": "#f87171",
        "items": [
            ("• 12/04 恒生系列季检(恒科 30→50)", "#7f1d1d", False),
            ("• 12 月 4,742 亿年内最大解禁", "#991b1b", True),
            ("• 12/11–14 宽基与红利低波调规", "#7f1d1d", False),
            ("• 12/10–18 美欧英日密集议息", "#991b1b", True),
        ],
    },
    {
        "header": "12/21–12/24（● 主攻窗口）",
        "color": "#009E73",
        "bg": "#f0fdf4",
        "border": "#4ade80",
        "items": [
            ("• 外围议息与交割风暴全落地", "#166534", True),
            ("• 12/24 港半日/避 12/25 港休市", "#166534", False),
            ("→ 股票加至 5.2 成(解封硬科技)", "#065f46", True),
            ("→ 黄金待转黄灯后再分批转入", "#065f46", True),
        ],
    },
    {
        "header": "2027.01–03（◆ 春季与两会）",
        "color": "#047857",
        "bg": "#dcfce7",
        "border": "#009E73",
        "items": [
            ("• 01/10 中美关税休战到期大限", "#14532d", True),
            ("• 01/27 严避长鑫 550 亿大解禁", "#dc2626", True),
            ("• 03 月全国两会定调财政赤字", "#14532d", True),
            ("→ 顺风站稳年线满配 5.8 成股票", "#065f46", False),
        ],
    },
]

DEFAULT_A7_POINTS = [
    ("招商银行 7.2x(A折H)",  76, 114, "g", "#009E73",  8,   3, "start"),
    ("工商银行 8.5x",        96, 148, "g", "#009E73",  0,  15, "middle"),
    ("紫金矿业 8.6x(防铜)", 114,  88, "b", "#0072B2",  8,   3, "start"),
    ("中国石油 10.5x",      162, 134, "g", "#009E73",  8,   3, "start"),
    ("中国海油 10.1x",      154,  66, "g", "#009E73",  8,   3, "start"),
    ("宁德时代 12.0x",      224, 102, "g", "#009E73",  8,   3, "start"),
    ("美的集团 15.1x",      284, 140, "g", "#009E73",  0,  15, "middle"),
    ("工业富联 15.3x",      292,  72, "b", "#0072B2",  0, -10, "middle"),
    ("药明康德(1260H移除)",  336,  96, "b", "#0072B2",  8,   3, "start"),
    ("中际旭创 18.8x",      378,  66, "y", "#D97706",  0, -10, "middle"),
    ("贵州茅台 22.1x",      414, 196, "y", "#D97706", -8,   4, "end"),
    ("五粮液(Q3-48%倒挂)",   292, 234, "r", "#D55E00",  0,  14, "middle"),
    ("山东黄金(Q3首亏)",     462, 240, "r", "#D55E00",  0,  14, "middle"),
    ("长鑫(1.27大解禁)",     384, 218, "r", "#D55E00",  8,   3, "start"),
    ("恒瑞医药 38x",        488,  92, "b", "#0072B2",  8,   3, "start"),
    ("中微公司 50x",        548,  70, "b", "#0072B2",  0, -10, "middle"),
    ("北方华创(11/25急挫)",  592, 186, "y", "#D97706",  0,  15, "middle"),
    ("寒武纪 140x",         696, 102, "y", "#D97706",  0, -10, "middle"),
    ("宇树科技 518x",       782, 218, "r", "#D55E00", -8, -10, "end"),
]


def load_meta(meta_override: dict | None = None) -> dict:
    if meta_override:
        return meta_override
    if META_PATH.exists():
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    return {}


def resolve_flagship_md(meta: dict) -> Path:
    slug = str(meta.get("period_slug", "2026_11")).strip() or "2026_11"
    return OUT_DIR / f"a_share_market_report_{slug}.md"


def svg_chart_a1_cycles(meta_override: dict | None = None) -> str:
    """Chart A1: Dynamic Proportional Time-Axis 2015-2026+ A-Share Cycles + Collision-Free Labels"""
    cl = load_meta(meta_override).get("chart_live", {})
    as_short = html_mod.escape(clean_svg_text(str(cl.get("as_of_short", "11/24收"))))
    as_full = html_mod.escape(clean_svg_text(str(cl.get("as_of_full", "2026-11-24 18:00 北京时间"))))
    cur_yr = float(cl.get("as_of_year_float", 2026.905))
    max_yr = max(2026.90, cur_yr)
    c3_now = int(round(float(cl.get("csi300", 3964))))
    ss_now = int(round(float(cl.get("sse", 3548))))
    w300 = int(round(float(cl.get("csi300_200w", 4025))))
    wsse = int(round(float(cl.get("sse_200w", 3427))))
    dd_pct = ((c3_now - 5064) / 5064.0) * 100.0
    above_300 = c3_now >= w300
    above_sse = ss_now >= wsse

    raw_pts = [
        ("15.06顶", 2015.46, 5380, 5178),
        ("16.02底", 2016.12, 2821, 2638),
        ("19.01底", 2019.04, 2936, 2441),
        ("21.02顶", 2021.14, 5931, 3732),
        ("24.02底", 2024.10, 3108, 2635),
        ("24.10高", 2024.78, 4450, 3674),
        ("25.04坑", 2025.27, 3514, 3041),
        ("26.06顶", 2026.46, 5064, 4259),
        (as_short,  cur_yr,  c3_now, ss_now),
    ]

    def x_yr(yr: float) -> float:
        return round(74 + ((yr - 2015.46) / (max_yr - 2015.46)) * 716, 1)

    def y_p(val: float) -> float:
        clamped = max(2000, min(6300, val))
        return round(262 - ((clamped - 2000) / 4300.0) * 214, 1)

    pts = [(lbl, x_yr(yr), c3, ss) for lbl, yr, c3, ss in raw_pts]
    p300 = " ".join(f"{x},{y_p(c3)}" for _, x, c3, _ in pts)
    psse = " ".join(f"{x},{y_p(ss)}" for _, x, _, ss in pts)
    y_300_200w = y_p(w300)
    y_sse_200w = y_p(wsse)

    grid = ""
    for val in [2000, 3000, 4000, 5000, 6000]:
        y = y_p(val)
        grid += f'<line x1="60" y1="{y}" x2="834" y2="{y}" stroke="#f1f5f9" stroke-width="1"/>'
        grid += f'<text x="53" y="{y+4}" text-anchor="end" font-size="10.0" fill="#64748b">{val:,}</text>'

    halo = 'paint-order="stroke" stroke="#ffffff" stroke-width="3.2" stroke-linejoin="round"'
    nodes = ""
    for idx, (lbl, x, c3, ss) in enumerate(pts):
        y3, ys = y_p(c3), y_p(ss)
        tick_y = 290 if idx in (5, 7) else 278
        if idx in (5, 7):
            nodes += f'<line x1="{x}" y1="264" x2="{x}" y2="279" stroke="#cbd5e1" stroke-width="0.8"/>'
        nodes += f'<text x="{x}" y="{tick_y}" text-anchor="middle" font-size="9.0" fill="#334155" font-weight="600">{lbl}</text>'
        nodes += f'<circle cx="{x}" cy="{y3}" r="4.0" fill="#0072B2"/>'
        nodes += f'<circle cx="{x}" cy="{ys}" r="3.4" fill="#d97706"/>'

        if idx == 1:
            nodes += f'<text x="{x+7}" y="{y3-3}" text-anchor="start" font-size="9.2" fill="#0072B2" font-weight="700" {halo}>{c3:,}</text>'
        elif idx == 2:
            nodes += f'<text x="{x+7}" y="{y3+4}" text-anchor="start" font-size="9.2" fill="#0072B2" font-weight="700" {halo}>{c3:,}</text>'
        elif idx == 4:
            nodes += f'<text x="{x-7}" y="{y3+3}" text-anchor="end" font-size="9.2" fill="#0072B2" font-weight="700" {halo}>{c3:,}</text>'
        elif idx == 6:
            nodes += f'<text x="{x}" y="{y3-10}" text-anchor="middle" font-size="9.0" fill="#0072B2" font-weight="700" {halo}>{c3:,}</text>'
        elif idx == 8:
            nodes += f'<text x="{x+7}" y="{y3+3}" text-anchor="start" font-size="9.6" fill="#0072B2" font-weight="800" {halo}>{c3:,}</text>'
        else:
            nodes += f'<text x="{x}" y="{y3-10}" text-anchor="middle" font-size="9.4" fill="#0072B2" font-weight="700" {halo}>{c3:,}</text>'

        if idx == 0:
            nodes += f'<text x="{x-4}" y="{ys+15}" text-anchor="middle" font-size="9.0" fill="#b45309" font-weight="600" {halo}>{ss:,}</text>'
        elif idx in (1, 2, 4, 6):
            nodes += f'<text x="{x}" y="{ys+15}" text-anchor="middle" font-size="9.0" fill="#b45309" font-weight="600" {halo}>{ss:,}</text>'
        elif idx == 7:
            nodes += f'<text x="{x-8}" y="{ys+5}" text-anchor="end" font-size="9.0" fill="#b45309" font-weight="700" {halo}>{ss:,}</text>'
        elif idx == 8:
            nodes += f'<text x="{x+7}" y="{ys+5}" text-anchor="start" font-size="9.4" fill="#b45309" font-weight="700" {halo}>{ss:,}</text>'

    c3_tag = f"沪深300 4年成本线 {w300:,} ({'已站稳' if above_300 else '上方压力'})"
    sse_tag = f"上证4年成本线 {wsse:,} ({'已守住' if above_sse else '上方压力'})"
    title_txt = _norm_chart_title(
        f"沪深 300 从 2026 年 6 月高点回调 {abs(dd_pct):.1f}%，"
        + ("已站回“4 年平均成本线”" if above_300 else "进入偏便宜区，但还没站回“4 年平均成本线”")
    )

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_txt}</div>
      <div class="chart-sub">2015–2026 年 A 股按真实时间跨度绘制的五大轮牛熊拐点（蓝线 = 沪深 300，橙虚线 = 上证指数）</div>
      <svg viewBox="0 0 850 298" width="100%" role="img" aria-label="{title_txt}" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="298" fill="#ffffff" rx="6"/>
        {grid}
        <line x1="60" y1="{y_300_200w}" x2="834" y2="{y_300_200w}" stroke="#D55E00" stroke-width="1.5" stroke-dasharray="5,3"/>
        <line x1="60" y1="{y_sse_200w}" x2="834" y2="{y_sse_200w}" stroke="#009E73" stroke-width="1.4" stroke-dasharray="4,3"/>
        <polyline fill="none" stroke="#0072B2" stroke-width="2.6" points="{p300}"/>
        <polyline fill="none" stroke="#d97706" stroke-width="2.0" stroke-dasharray="4,2" points="{psse}"/>
        <rect x="136" y="{y_300_200w-21}" width="218" height="17" fill="#fef2f2" fill-opacity="0.96" stroke="#fca5a5" stroke-width="0.8" rx="3"/>
        <text x="245" y="{y_300_200w-9}" text-anchor="middle" font-size="9.0" fill="#b91c1c" font-weight="700">{c3_tag}</text>
        <rect x="122" y="{y_sse_200w+5}" width="180" height="17" fill="#ecfdf5" fill-opacity="0.96" stroke="#86efac" stroke-width="0.8" rx="3"/>
        <text x="212" y="{y_sse_200w+17}" text-anchor="middle" font-size="9.0" fill="#047857" font-weight="700">{sse_tag}</text>
        {nodes}
        <rect x="64" y="10" width="14" height="4.5" fill="#0072B2"/>
        <text x="83" y="16" font-size="10.0" fill="#1e293b" font-weight="600">沪深 300（当前 {c3_now:,}，距 2026.06 高点 {dd_pct:+.1f}%）</text>
        <rect x="448" y="10" width="14" height="4.5" fill="#d97706"/>
        <text x="467" y="16" font-size="10.0" fill="#1e293b" font-weight="600">上证指数（当前 {ss_now:,}）</text>
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>200 周均线约等于过去 4 年大家买股票的平均成本。上证指数守住了成本线（底部有支撑），但核心大盘股（沪深 300）仍差一点没站上 {w300:,} 点——站稳前追高容易撞上解套抛压。</div>
      <div class="chart-note">数据口径：沪深交易所官方收盘价，截至 {as_full}（横轴严格按实际年份比例绘制）。</div>
    </div>
    '''


def svg_chart_a2_split_and_futures(meta_override: dict | None = None) -> str:
    """Chart A2: Broad Index Divergence (Unified Proportional Scale) + CFFEX Futures Sentiment"""
    cl = load_meta(meta_override).get("chart_live", {})
    a2_nest = cl.get("a2") if isinstance(cl.get("a2"), dict) else {}
    as_full = html_mod.escape(clean_svg_text(str(cl.get("as_of_full", "2026-11-24 18:00 北京时间"))))
    idxs = a2_nest.get("indices") or cl.get("indices") or DEFAULT_A_INDICES
    futs = a2_nest.get("futures") or cl.get("futures") or DEFAULT_A_FUTURES

    title_a2 = _norm_chart_title(
        a2_nest.get("title") or cl.get("a2_title")
        or "11/24 科创领涨但中小盘集体回落，中证 1000 期货贴水继续走阔"
    )
    sub_a2 = html_mod.escape(clean_svg_text(str(
        a2_nest.get("sub") or cl.get("a2_sub")
        or "左：11/24 官方宽基涨跌（统一线性比例，▲红涨 ▼青跌） ｜ 右：中金所 12 月主力合约与期现监控"
    )))
    takeaway_a2 = html_mod.escape(clean_svg_text(str(
        a2_nest.get("takeaway") or cl.get("a2_takeaway")
        or "11/24 科创 50 靠芯片大涨 +1.81%、上证 50 稳涨 +0.45%，但深成指/中证 500/中证 1000 全线回落；中证 1000 期货贴水仍深，印证绝不追小盘题材，大蓝筹期货与前 20 席位晚刊持续跟踪。"
    )))
    note_a2 = html_mod.escape(clean_svg_text(str(
        a2_nest.get("note") or cl.get("a2_note")
        or f"数据口径：沪深北交易所 11/24 官方收盘与中金所 12 月主力合约数据，截至 {as_full}。"
    )))

    x0 = 192
    n_idx = max(1, len(idxs))
    step_y = min(22.5, 248.0 / n_idx)
    max_pos = max([float(x[1]) for x in idxs if float(x[1]) >= 0] + [0.5])
    max_neg = max([abs(float(x[1])) for x in idxs if float(x[1]) < 0] + [0.3])
    px_per_pct = min(155.0 / max_pos, 42.0 / max_neg)

    left = f'<line x1="{x0}" y1="38" x2="{x0}" y2="292" stroke="#334155" stroke-width="1.2"/>'
    for i, item in enumerate(idxs):
        name, pct, col = item[0], float(item[1]), sanitize_hex_color(item[2], "#334155")
        if abs(pct) < 1e-9:
            col = "#64748b"
        elif pct > 0 and col.lower() in _A2_COOL_COLORS:
            col = "#c2410c"
        elif pct < 0 and col.lower() in _A2_WARM_COLORS:
            col = "#0f766e"
        y = 44 + i * step_y
        left += f'<text x="142" y="{y+12}" text-anchor="end" font-size="9.3" fill="#1e293b" font-weight="600">{html_mod.escape(clean_svg_text(str(name)))}</text>'
        if abs(pct) < 1e-9:
            left += f'<rect x="{x0}" y="{y+1}" width="2.0" height="13.5" fill="{col}" opacity="0.86" rx="1"/>'
            left += f'<text x="{x0+7}" y="{y+12}" font-size="9.0" fill="{col}" font-weight="700">0.00%</text>'
        elif pct > 0:
            w = max(round(pct * px_per_pct, 1), 2.0)
            left += f'<rect x="{x0}" y="{y+1}" width="{w}" height="13.5" fill="{col}" opacity="0.86" rx="2.5"/>'
            left += f'<text x="{x0+w+5}" y="{y+12}" font-size="9.0" fill="{col}" font-weight="700">▲+{pct:.2f}%</text>'
        else:
            w = max(round(abs(pct) * px_per_pct, 1), 2.0)
            left += f'<rect x="{x0-w}" y="{y+1}" width="{w}" height="13.5" fill="{col}" opacity="0.86" rx="2.5"/>'
            left += f'<text x="{x0+6}" y="{y+12}" font-size="9.0" fill="{col}" font-weight="700">▼{pct:.2f}%</text>'

    right = ""
    for i, item in enumerate(futs[:4]):
        nm, ann, headline, sub, col_raw, bg_raw = item
        col = sanitize_hex_color(col_raw, "#334155")
        bg = sanitize_hex_color(bg_raw, "#f8fafc")
        y = 46 + i * 61
        is_settlement_pending = ann is None
        if is_settlement_pending:
            ann_lbl = "结算单待次日补核"
            if col.lower() in ("#009e73", "#16a34a", "#15803d"):
                col, bg = "#64748b", "#f8fafc"
        else:
            # ann_f > 0 => annualized discount (折价/贴水); ann_f < 0 => annualized premium (升水)
            ann_f = float(ann)
            if ann_f > 0:
                ann_lbl = f"折价约 {ann_f:.1f}%/年"
            elif ann_f < 0:
                ann_lbl = f"升水约 {abs(ann_f):.1f}%/年"
            else:
                ann_lbl = "期现平水"
        right += f'<rect x="440" y="{y}" width="396" height="53" fill="{bg}" stroke="{col}" stroke-width="1.1" rx="5"/>'
        right += f'<text x="450" y="{y+16}" font-size="9.4" fill="#0f172a" font-weight="700">{html_mod.escape(clean_svg_text(str(nm)))}</text>'
        right += f'<text x="828" y="{y+16}" text-anchor="end" font-size="9.0" fill="#475569">{ann_lbl}</text>'
        right += f'<text x="450" y="{y+32}" font-size="9.0" fill="{col}" font-weight="700">{html_mod.escape(clean_svg_text(str(headline)))}</text>'
        right += f'<text x="450" y="{y+46}" font-size="9.0" fill="#475569">{html_mod.escape(clean_svg_text(str(sub)))}</text>'

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_a2}</div>
      <div class="chart-sub">{sub_a2}</div>
      <svg viewBox="0 0 850 302" width="100%" role="img" aria-label="{title_a2}" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="302" fill="#ffffff" rx="6"/>
        <text x="16" y="24" font-size="10.0" fill="#0f172a" font-weight="700">A. 宽基涨跌对比（权重蓝筹 vs 中小成长）</text>
        <text x="440" y="24" font-size="10.0" fill="#0f172a" font-weight="700">B. 股指期货（聪明钱底牌与基差监控）</text>
        <line x1="426" y1="10" x2="426" y2="292" stroke="#e2e8f0" stroke-width="1.2"/>
        {left}
        {right}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway_a2}</div>
      <div class="chart-note">{note_a2}</div>
    </div>
    '''


def svg_chart_a3_macro_k_split(meta_override: dict | None = None) -> str:
    """Chart A3: China Macro Cold vs Hot K-Shape Split (Dynamic a3 Override Supported)"""
    cl = load_meta(meta_override).get("chart_live", {})
    a3_nest = cl.get("a3") if isinstance(cl.get("a3"), dict) else {}
    cold = a3_nest.get("cold") or a3_nest.get("cold_items") or [
        ("制造业景气度（10 月 PMI）", "49.3%（略冷）", "低于 50 荣枯线，社零仅 +0.4%，传统内需偏弱"),
        ("上游原料 vs 下游消费物价", "差 5.0 百分点", "PPI 涨 5.7% 但 CPI 仅涨 0.7%，中游利润受挤"),
        ("民企与居民借钱意愿", "单月转负", "10 月主要靠政府发债撑场面，私人贷款疲软"),
        ("地方卖地收入与 12 月解禁", "解禁 4,742 亿", "土地收入仍降，12 月迎年内最大规模解禁洪峰"),
        ("8·28 地产新政后销量分化", "二手 +11.4%", "一线房价环比 +0.2% 止跌，但三四线去库仍慢"),
        ("光伏硅料与期铜入熊传导", "铜跌 -4.7%", "弱周期过剩产能出清中，短线防有色矿股飞刀"),
    ]
    hot = a3_nest.get("hot") or a3_nest.get("hot_items") or [
        ("全 A 非金融前三季净利", "稳增 +16.6%", "国产芯片设备/光模块业绩高增，实业底色偏硬"),
        ("11/25 央行全口径大对冲", "总净投 +3,210 亿", "隔夜锚定 1.25%，辟谣回笼传闻，稳住跨月资金"),
        ("国家队 10–11 月 ETF 托底", "买超 7,300 亿", "11/20 单日净买 924 亿创纪录，大盘底线明确"),
        ("保险长钱与红利风险溢价", "溢价 +5.85%", "红利股息率远超 1.58% 国债，险资开门红托底"),
        ("出口与新能源车渗透率", "出口 +35.2%", "10 月出口 4,123 亿美元，新能源车渗透率 67.5%"),
        ("人民币中间价走强至 6.7088", "外资锚定稳", "吸引长钱配置人民币核心资产（略压纯汇兑股）"),
    ]
    title_a3 = _norm_chart_title(
        a3_nest.get("title")
        or "为什么 A 股难有全面疯牛、必须“一手红利一手硬科技”？看经济冷热两极"
    )
    sub_a3 = html_mod.escape(clean_svg_text(str(
        a3_nest.get("sub")
        or "2026 下半年中国经济六维账本：左冷（CPI/PPI 剪刀差、内需偏弱与 12 月解禁） vs 右热（央行对冲、国家队托底与硬科技真盈利）"
    )))
    takeaway_a3 = html_mod.escape(clean_svg_text(str(
        a3_nest.get("takeaway")
        or "普通内需还没全面热起来，所以闭眼追高不现实；但右边两股力量很硬——经济慢也能稳发高利息的红利股，加上靠国产替代真赚大钱的半导体/储能龙头，这就是“哑铃配置”的底层逻辑。"
    )))
    note_a3 = html_mod.escape(clean_svg_text(str(
        a3_nest.get("note")
        or "数据口径：国家统计局、央行（11/25 公开市场实操）、财政部、金融监管总局与上市公司 2026 三季报公开数据。"
    )))
    rows_c = ""
    for i, item in enumerate(cold[:6]):
        k, v, sub = item[0], item[1], item[2]
        y = 46 + i * 39
        rows_c += f'<rect x="14" y="{y}" width="404" height="33" fill="#f8fafc" stroke="#cbd5e1" stroke-width="0.9" rx="4"/>'
        rows_c += f'<text x="22" y="{y+14}" font-size="9.3" fill="#1e293b" font-weight="700">{html_mod.escape(clean_svg_text(str(k)))}</text>'
        rows_c += f'<text x="22" y="{y+27}" font-size="9.0" fill="#64748b">{html_mod.escape(clean_svg_text(str(sub)))}</text>'
        rows_c += f'<text x="410" y="{y+18}" text-anchor="end" font-size="9.4" fill="#b45309" font-weight="800">{html_mod.escape(clean_svg_text(str(v)))}</text>'

    rows_h = ""
    for i, item in enumerate(hot[:6]):
        k, v, sub = item[0], item[1], item[2]
        y = 46 + i * 39
        rows_h += f'<rect x="432" y="{y}" width="404" height="33" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="0.9" rx="4"/>'
        rows_h += f'<text x="440" y="{y+14}" font-size="9.3" fill="#064e3b" font-weight="700">{html_mod.escape(clean_svg_text(str(k)))}</text>'
        rows_h += f'<text x="440" y="{y+27}" font-size="9.0" fill="#047857">{html_mod.escape(clean_svg_text(str(sub)))}</text>'
        rows_h += f'<text x="828" y="{y+18}" text-anchor="end" font-size="9.4" fill="#009E73" font-weight="800">{html_mod.escape(clean_svg_text(str(v)))}</text>'

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_a3}</div>
      <div class="chart-sub">{sub_a3}</div>
      <svg viewBox="0 0 850 284" width="100%" role="img" aria-label="{title_a3}" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="284" fill="#ffffff" rx="6"/>
        <rect x="14" y="10" width="404" height="26" fill="#475569" rx="4"/>
        <text x="216" y="27" text-anchor="middle" font-size="9.8" fill="#ffffff" font-weight="700">▼ 偏冷的一面：传统内需与财政承压（封顶全面普涨）</text>
        <rect x="432" y="10" width="404" height="26" fill="#009E73" rx="4"/>
        <text x="634" y="27" text-anchor="middle" font-size="9.8" fill="#ffffff" font-weight="700">▲ 偏热的一面：硬科技业绩爆发 + 央行/长钱托底</text>
        {rows_c}
        {rows_h}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway_a3}</div>
      <div class="chart-note">{note_a3}</div>
    </div>
    '''


def svg_chart_a4_clock(meta_override: dict | None = None) -> str:
    """Chart A4: Cross-Year Event Clock (Full Nested a4 Override) + Red/Yellow/Green Master Switch"""
    cl = load_meta(meta_override).get("chart_live", {})
    a4_nest = cl.get("a4") if isinstance(cl.get("a4"), dict) else {}
    as_full = html_mod.escape(clean_svg_text(str(cl.get("as_of_full", "2026-11-24 18:00 北京时间"))))
    horizon = html_mod.escape(clean_svg_text(str(
        a4_nest.get("horizon") or cl.get("a4_horizon_label") or "2026 年 11 月底至 2027 年 1 月底"
    )))
    score = float(cl.get("score", 2.5))
    score_s = f"{score:g}"
    tier_s = html_mod.escape(clean_svg_text(str(cl.get("tier_short", "红灯防守期"))))
    line1 = html_mod.escape(clean_svg_text(str(cl.get("status_line1", "当前综合体检 2.5 / 6 分：政策护盘与成交放量亮绿灯，但大盘仍压在 4 年成本线（4,025点）下方"))))
    line2 = html_mod.escape(clean_svg_text(str(cl.get("status_line2", "行动铁律：当下不追高，手里余下 6 成防御资金耐心等 11 月底与 12 月中旬两轮大考过关后再分批上车"))))
    cards = a4_nest.get("cards") or DEFAULT_A4_CARDS

    title_a4 = _norm_chart_title(
        a4_nest.get("title") or cl.get("a4_title")
        or f"{horizon}还有五道时间关，12 月 21 日之后才是大举加仓的黄金窗口"
    )
    sub_a4 = html_mod.escape(clean_svg_text(str(
        a4_nest.get("sub") or cl.get("a4_sub")
        or f"北京时间排雷路线图 ＋ 当前大盘综合水温开关，截至 {as_full}"
    )))
    takeaway_a4 = html_mod.escape(clean_svg_text(str(
        a4_nest.get("takeaway") or cl.get("a4_takeaway")
        or "12 月中旬前有“年内最大解禁 + 全球四大央行密集议息”两道风浪，所以当前停在红灯防守区；等 12 月 18 日风暴过去，再用预留现金从容低吸，胜率高得多。"
    )))
    note_a4 = html_mod.escape(clean_svg_text(str(
        a4_nest.get("note") or cl.get("a4_note")
        or f"数据口径：沪深交易所、中证指数、央行与公开宏观日程，截至 {as_full}。"
    )))

    if score < 3.0:
        ptr_x = int(round(36 + (max(0.0, score) / 3.0) * 238))
        ptr_col = "#D55E00"
    elif score < 4.5:
        ptr_x = int(round(312 + ((score - 3.0) / 1.5) * 192))
        ptr_col = "#ca8a04"
    else:
        ptr_x = int(round(542 + (min(1.5, score - 4.5) / 1.5) * 274))
        ptr_col = "#009E73"

    card_specs = [(16, 194, "#64748b"), (228, 198, "#64748b"), (444, 188, "#009E73"), (650, 186, None)]
    cards_svg = ""
    for idx, c in enumerate(cards[:4]):
        cx, cw, arrow_col = card_specs[idx]
        hdr = html_mod.escape(clean_svg_text(str(c.get("header", ""))))
        col = sanitize_hex_color(c.get("color"), "#ea580c")
        bg = sanitize_hex_color(c.get("bg"), "#fff7ed")
        bd = sanitize_hex_color(c.get("border"), col)
        cards_svg += f'<rect x="{cx}" y="34" width="{cw}" height="102" fill="{bg}" stroke="{bd}" stroke-width="1.4" rx="5"/>'
        cards_svg += f'<rect x="{cx}" y="34" width="{cw}" height="22" fill="{col}" rx="4"/>'
        cards_svg += f'<text x="{cx + cw/2}" y="49" text-anchor="middle" font-size="9.2" fill="#ffffff" font-weight="700">{hdr}</text>'
        ys = [72, 87, 102, 120]
        for j, it in enumerate(c.get("items", [])[:4]):
            if isinstance(it, (list, tuple)):
                txt, tc, bold = str(it[0]), sanitize_hex_color(it[1], "#1e293b"), bool(it[2])
            else:
                txt, tc, bold = str(it), "#1e293b", False
            fw = "700" if bold else "500"
            cards_svg += f'<text x="{cx+8}" y="{ys[j]}" font-size="9.0" fill="{tc}" font-weight="{fw}">{html_mod.escape(clean_svg_text(txt))}</text>'
        if arrow_col:
            ax = cx + cw + 4
            cards_svg += f'<polygon points="{ax},81 {ax+10},85 {ax},89" fill="{arrow_col}"/>'

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_a4}</div>
      <div class="chart-sub">{sub_a4}</div>
      <svg viewBox="0 0 850 268" width="100%" role="img" aria-label="{title_a4}" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="268" fill="#ffffff" rx="6"/>
        <text x="16" y="22" font-size="10.0" fill="#0f172a" font-weight="700">A. {horizon}关键节点与分步上车节奏（从防守 4.0 成 → 逐步加到 5.8 成股票）</text>
        {cards_svg}
        <text x="16" y="162" font-size="10.0" fill="#0f172a" font-weight="700">B. 大盘综合水温总开关（满分 6 分 · 当前 {score_s} 分 · {tier_s}）</text>
        <rect x="16" y="173" width="272" height="26" fill="#fef2f2" stroke="#D55E00" stroke-width="1.2" rx="4"/>
        <text x="152" y="190" text-anchor="middle" font-size="9.3" fill="#991b1b" font-weight="700">× 红灯防守 (&lt;3分)：最多 4 成股票</text>
        <rect x="294" y="173" width="226" height="26" fill="#fef9c3" stroke="#ca8a04" stroke-width="1.2" rx="4"/>
        <text x="407" y="190" text-anchor="middle" font-size="9.3" fill="#854d0e" font-weight="700">▲ 黄灯试探 (3–4分)：11.30 后小加</text>
        <rect x="526" y="173" width="310" height="26" fill="#dcfce7" stroke="#009E73" stroke-width="1.4" rx="4"/>
        <text x="681" y="190" text-anchor="middle" font-size="9.3" fill="#166534" font-weight="700">● 绿灯主攻 (≥4.5分)：站稳 4,025 满配近 6 成</text>
        <polygon points="{ptr_x},204 {ptr_x+8},215 {ptr_x-8},215" fill="{ptr_col}"/>
        <rect x="16" y="218" width="820" height="40" fill="#f8fafc" stroke="#cbd5e1" stroke-width="0.9" rx="4"/>
        <text x="426" y="234" text-anchor="middle" font-size="9.0" fill="#0f172a" font-weight="700">{line1}</text>
        <text x="426" y="250" text-anchor="middle" font-size="9.0" fill="#475569">{line2}</text>
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway_a4}</div>
      <div class="chart-note">{note_a4}</div>
    </div>
    '''


def svg_chart_a5_targets_and_math(meta_override: dict | None = None) -> str:
    """Chart A5: CSI 300 2027 Scenarios + 21-Year Gold Math"""
    cl = load_meta(meta_override).get("chart_live", {})
    as_short = html_mod.escape(clean_svg_text(str(cl.get("as_of_short", "11/24收"))))
    c3_now = int(round(float(cl.get("csi300", 3964))))
    bands = [
        ("极端压力 ●●○○○○○○○○", 3500, 3700, 3600, "#D55E00"),
        ("长期震荡 ●○○○○○○○○○", 3800, 4200, 4000, "#64748b"),
        ("基准修复 ●●●●●○○○○○", 4300, 4550, 4425, "#0072B2"),
        ("高盛 2027 年目标",          4400, 4600, 4500, "#0284c7"),
        ("摩根士丹利 2027 年目标",    4450, 4650, 4550, "#009E73"),
        ("乐观大涨 ●●○○○○○○○○", 4800, 5064, 4932, "#15803d"),
    ]

    def x_c(val: float) -> float:
        clamped = max(3350, min(5250, val))
        return round(176 + ((clamped - 3300) / 2050.0) * 218, 1)

    x_now = x_c(c3_now)
    left = f'<line x1="{x_now}" y1="42" x2="{x_now}" y2="210" stroke="#D55E00" stroke-width="1.5" stroke-dasharray="4,3"/>'
    left += f'<text x="{x_now}" y="36" text-anchor="middle" font-size="9.0" fill="#D55E00" font-weight="700">{as_short} {c3_now:,}</text>'
    for v in [3500, 4000, 4500, 5000]:
        xv = x_c(v)
        left += f'<line x1="{xv}" y1="44" x2="{xv}" y2="210" stroke="#f1f5f9" stroke-width="1"/>'
        left += f'<text x="{xv}" y="224" text-anchor="middle" font-size="9.0" fill="#64748b">{v:,}</text>'

    for i, (nm, lo, hi, mid, col) in enumerate(bands):
        y = 52 + i * 26.5
        x1, x2, xm = x_c(lo), x_c(hi), x_c(mid)
        pct = ((mid - c3_now) / max(1.0, float(c3_now))) * 100.0
        left += f'<text x="169" y="{y+10}" text-anchor="end" font-size="9.0" fill="#1e293b" font-weight="600">{nm}</text>'
        left += f'<line x1="{x1}" y1="{y+6}" x2="{x2}" y2="{y+6}" stroke="{col}" stroke-width="5.0" opacity="0.28" stroke-linecap="round"/>'
        left += f'<circle cx="{xm}" cy="{y+6}" r="4.0" fill="{col}"/>'
        lbl = f"{mid:,} ({pct:+.0f}%)"
        if i == 0:
            left += f'<text x="{xm}" y="{y-2}" text-anchor="middle" font-size="9.0" fill="{col}" font-weight="700">{lbl}</text>'
        else:
            left += f'<text x="{x2+5}" y="{y+9.5}" font-size="9.0" fill="{col}" font-weight="700">{lbl}</text>'

    cards = [
        ("2006–2026.11 年化收益（含2026回调）", "纯股债 7.65%", "加15%黄金 8.12%", "年化多赚 +0.47%", "#009E73"),
        ("2006–2025 长期年化收益", "纯股债 8.21%", "加15%黄金 8.89%", "复利滚雪球更快", "#009E73"),
        ("历史上最惨一年跌了多少（越少越好）", "纯股债 -21.2%", "加15%黄金 -18.3%", "少亏近 3 个百分点", "#0072B2"),
        ("每承担 1 份波动换来的回报（性价比）", "纯股债 0.349", "加15%黄金 0.391", "综合性价比 +12%", "#7c3aed"),
    ]
    right = ""
    for i, (title_c, v1, v2, badge, col) in enumerate(cards):
        y = 42 + i * 47
        right += f'<rect x="466" y="{y}" width="370" height="39" fill="#f8fafc" stroke="#e2e8f0" stroke-width="0.9" rx="5"/>'
        right += f'<text x="476" y="{y+15}" font-size="9.0" fill="#0f172a" font-weight="700">{title_c}</text>'
        right += f'<text x="826" y="{y+15}" text-anchor="end" font-size="9.0" fill="{col}" font-weight="700">{badge}</text>'
        right += f'<text x="476" y="{y+31}" font-size="9.0" fill="#64748b">{v1}  →  <tspan fill="{col}" font-weight="800">{v2}</tspan></text>'

    title_a5 = _norm_chart_title("2027 年大盘基准看涨约 +12% 至 +15%；实证证明“股 + 债 + 黄金”更稳更赚")
    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_a5}</div>
      <div class="chart-sub">左：沪深 300 四大情景（10 点条 = 10 次里约发生几次）与外资目标 ｜ 右：21 年实测“纯股债”vs“加 15% 黄金”</div>
      <svg viewBox="0 0 850 236" width="100%" role="img" aria-label="{title_a5}" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="236" fill="#ffffff" rx="6"/>
        <text x="16" y="20" font-size="9.8" fill="#0f172a" font-weight="700">A. 沪深 300 2027 年情景与主流外资目标</text>
        <text x="466" y="20" font-size="9.8" fill="#0f172a" font-weight="700">B. 过去 21 年人民币资产实测（40股/60债 vs 加15%金）</text>
        <line x1="454" y1="10" x2="454" y2="226" stroke="#e2e8f0" stroke-width="1.2"/>
        {left}
        {right}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>按 10 万元本金算，2027 年约一半概率温和修复 1 万多，极端压力下可能先浮亏 1 万左右；右侧为 21 年长期实证（当前黄金处红灯停，存量底仓不动、空仓预算暂泊国债/短债待黄金转黄灯后再分批转入）。</div>
      <div class="chart-note">数据口径：高盛、摩根士丹利 2027 展望报告及 2006–2026.11 沪深 300 / 中债 / 上海金历史回测。</div>
    </div>
    '''


def svg_chart_a6_sector_heatmap(meta_override: dict | None = None) -> str:
    """Chart A6: 16 Shenwan Sectors Return vs Main Capital Net Flow (Nested a6 Priority + Unified Scale)"""
    cl = load_meta(meta_override).get("chart_live", {})
    a6_nest = cl.get("a6") if isinstance(cl.get("a6"), dict) else {}
    as_short = html_mod.escape(clean_svg_text(str(a6_nest.get("date_short") or cl.get("a6_date_short") or "11/23 完整归档")))
    as_full = html_mod.escape(clean_svg_text(str(cl.get("as_of_full", "2026-11-24 18:00 北京时间"))))
    total_flow = html_mod.escape(clean_svg_text(str(
        a6_nest.get("sectors_total_flow") or cl.get("sectors_total_flow") or "+291.3 亿"
    )))
    sectors = a6_nest.get("sectors") or cl.get("sectors") or DEFAULT_A_SECTORS
    n = len(sectors)
    row_h = 21.5
    svg_h = int(60 + n * row_h)

    x_pct0 = 186
    x_flw0 = 532
    max_p_pos = max([float(s["pct"]) for s in sectors if float(s["pct"]) >= 0] + [1.0])
    max_p_neg = max([abs(float(s["pct"])) for s in sectors if float(s["pct"]) < 0] + [0.5])
    px_pct = min(166.0 / max_p_pos, 50.0 / max_p_neg)

    max_f_pos = max([float(s["flow"]) for s in sectors if float(s["flow"]) >= 0] + [10.0])
    max_f_neg = max([abs(float(s["flow"])) for s in sectors if float(s["flow"]) < 0] + [5.0])
    px_flw = min(176.0 / max_f_pos, 72.0 / max_f_neg)

    bg_rects = ""
    bars = ""
    for i, s in enumerate(sectors):
        y = 42 + i * row_h
        nm = html_mod.escape(clean_svg_text(str(s["name"])))
        pct = float(s["pct"])
        flw = float(s["flow"])
        is_contra = bool(s.get("highlight")) or (s.get("camp") == "def" and pct < 0 and flw >= 5.0)
        if is_contra:
            bg_rects += f'<rect x="10" y="{y-2}" width="830" height="{row_h-1}" fill="#fefce8" stroke="#facc15" stroke-width="0.9" rx="3"/>'

        bars += f'<text x="124" y="{y+12.5}" text-anchor="end" font-size="9.3" fill="{"#92400e" if is_contra else "#1e293b"}" font-weight="{"800" if is_contra else "600"}">{nm}</text>'
        if pct >= 0:
            w = max(round(pct * px_pct, 1), 2.0)
            col = "#c94a4a" if pct >= 2.5 else "#e67e22"
            bars += f'<rect x="{x_pct0}" y="{y+1.5}" width="{w}" height="13" fill="{col}" opacity="0.86" rx="2"/>'
            bars += f'<text x="{x_pct0+w+5}" y="{y+12.5}" font-size="9.0" fill="{col}" font-weight="700">▲+{pct:.2f}%</text>'
        else:
            w = max(round(abs(pct) * px_pct, 1), 2.0)
            bars += f'<rect x="{x_pct0-w}" y="{y+1.5}" width="{w}" height="13" fill="#0f766e" opacity="0.86" rx="2"/>'
            bars += f'<text x="{x_pct0+5}" y="{y+12.5}" font-size="9.0" fill="#0f766e" font-weight="700">▼{pct:.2f}%</text>'

        if flw >= 0:
            wf = max(round(flw * px_flw, 1), 2.0)
            fcol = "#b45309" if is_contra else "#0072B2"
            bars += f'<rect x="{x_flw0}" y="{y+1.5}" width="{wf}" height="13" fill="{fcol}" opacity="0.85" rx="2"/>'
            lbl_f = f"+{flw:.1f}亿"
            if is_contra and flw > 0:
                lbl_f += "（净流入）"
            bars += f'<text x="{x_flw0+wf+5}" y="{y+12.5}" font-size="9.0" fill="{fcol}" font-weight="700">{lbl_f}</text>'
        else:
            wf = max(round(abs(flw) * px_flw, 1), 2.0)
            bars += f'<rect x="{x_flw0-wf}" y="{y+1.5}" width="{wf}" height="13" fill="#64748b" opacity="0.85" rx="2"/>'
            bars += f'<text x="{x_flw0+5}" y="{y+12.5}" font-size="9.0" fill="#64748b" font-weight="700">{flw:.1f}亿</text>'

    axes = (
        f'<line x1="442" y1="10" x2="442" y2="{svg_h-12}" stroke="#e2e8f0" stroke-width="1.2"/>'
        f'<line x1="{x_pct0}" y1="36" x2="{x_pct0}" y2="{svg_h-14}" stroke="#334155" stroke-width="1.1"/>'
        f'<line x1="{x_flw0}" y1="36" x2="{x_flw0}" y2="{svg_h-14}" stroke="#334155" stroke-width="1.1"/>'
    )
    title_a6 = _norm_chart_title(
        a6_nest.get("title") or cl.get("a6_title")
        or "申万行业涨跌与主力资金净额"
    )
    sub_a6 = html_mod.escape(clean_svg_text(str(
        a6_nest.get("sub") or cl.get("a6_sub")
        or f"{as_short} 申万 16 大核心行业（左：当日涨跌 ▲红涨 ▼青跌 ｜ 右：主力净流向，全市场 {total_flow}）"
    )))
    takeaway = html_mod.escape(clean_svg_text(str(
        a6_nest.get("takeaway") or cl.get("a6_takeaway")
        or "左列显示行业涨跌，右列显示按数据来源口径统计的主力资金净额。"
    )))
    note_a6 = html_mod.escape(clean_svg_text(str(
        a6_nest.get("note") or cl.get("a6_note")
        or f"数据口径：证券时报·数据宝 {as_short} 申万一级行业收盘与主力资金统计，文档截点 {as_full}。"
    )))

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_a6}</div>
      <div class="chart-sub">{sub_a6}</div>
      <svg viewBox="0 0 850 {svg_h}" width="100%" role="img" aria-label="{title_a6}" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="{svg_h}" fill="#ffffff" rx="6"/>
        {bg_rects}
        <text x="16" y="23" font-size="9.8" fill="#0f172a" font-weight="700">A. 行业涨跌（%）</text>
        <text x="458" y="23" font-size="9.8" fill="#0f172a" font-weight="700">B. 主力资金净额（亿元）</text>
        {axes}
        {bars}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway}</div>
      <div class="chart-note">{note_a6}</div>
    </div>
    '''


def svg_chart_a7_stock_quadrant(meta_override: dict | None = None) -> str:
    """Chart A7: 19 Representative A-Share Stocks 4-Quadrant Map (Full Nested a7 Override + 11/24 Multiples)"""
    cl = load_meta(meta_override).get("chart_live", {})
    a7_nest = cl.get("a7") if isinstance(cl.get("a7"), dict) else {}
    pool_cnt = int(cl.get("stock_pool_count", 76))
    pts = a7_nest.get("points") or DEFAULT_A7_POINTS

    title_a7 = _norm_chart_title(
        a7_nest.get("title") or cl.get("a7_title")
        or "A 股精选 19 只核心龙头“贵不贵 × 赚不赚钱”四象限地图（一眼分清谁便宜、谁泡沫）"
    )
    sub_a7 = html_mod.escape(clean_svg_text(str(
        a7_nest.get("sub") or cl.get("a7_sub")
        or f"横轴：从左到右越来越贵（严格按 11/24 市盈率递增） ｜ 纵轴：业绩与安全垫越强（颜色 + 形状双编码，全量 {pool_cnt} 只见下表）"
    )))
    takeaway_a7 = html_mod.escape(clean_svg_text(str(
        a7_nest.get("takeaway") or cl.get("a7_takeaway")
        or "左上角藏着最多宝藏——工行/建行/海油/美的/宁德便宜稳健适合当下打底，紫金/盐湖/工业富联适合 12 月底主攻；而左下红叉长鑫（550 亿大解禁）与右下角宇树（约 518 倍）则是普通人最该避开的雷区。"
    )))
    note_a7 = html_mod.escape(clean_svg_text(str(
        a7_nest.get("note") or cl.get("a7_note")
        or "数据口径：2026 年 11 月 24 日官方收盘价与 2026 三季报公开业绩（注：长鑫虽账面市盈率不高，但 2027 年 1 月 27 日 550 亿网下配售解禁使其安全边际落入高危红叉）。"
    )))

    dots = ""
    for item in pts:
        nm, x, y, sh, col_raw, dx, dy, anc_raw = item
        col = sanitize_hex_color(col_raw, "#334155")
        anc = sanitize_svg_anchor(anc_raw, "start")
        dots += svg_shape(str(sh), float(x), float(y), col)
        dots += f'<text x="{float(x)+float(dx)}" y="{float(y)+float(dy)}" text-anchor="{anc}" font-size="9.0" fill="{col}" font-weight="700">{html_mod.escape(clean_svg_text(str(nm)))}</text>'

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_a7}</div>
      <div class="chart-sub">{sub_a7}</div>
      <svg viewBox="0 0 850 322" width="100%" role="img" aria-label="{title_a7}" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="322" fill="#ffffff" rx="6"/>
        <rect x="34" y="34" width="406" height="132" fill="#f0fdf4" opacity="0.72"/>
        <rect x="440" y="34" width="394" height="132" fill="#eff6ff" opacity="0.72"/>
        <rect x="34" y="166" width="406" height="110" fill="#fffbeb" opacity="0.65"/>
        <rect x="440" y="166" width="394" height="110" fill="#fef2f2" opacity="0.75"/>
        <line x1="440" y1="34" x2="440" y2="276" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,3"/>
        <line x1="34" y1="166" x2="834" y2="166" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,3"/>
        <rect x="34" y="34" width="800" height="242" fill="none" stroke="#cbd5e1" stroke-width="1"/>
        <text x="44" y="50" font-size="9.0" fill="#166534" font-weight="800">● 黄金性价比区：估值便宜 + 赚钱给力</text>
        <text x="824" y="50" text-anchor="end" font-size="9.0" fill="#1e40af" font-weight="800">◆ 高成长偏贵区：好公司但等回调/解锁</text>
        <text x="44" y="268" font-size="9.0" fill="#92400e" font-weight="800">▲ 底部磨底/事件或解禁扰动区：耐心排雷</text>
        <text x="824" y="268" text-anchor="end" font-size="9.0" fill="#991b1b" font-weight="800">× 泡沫/减速/高危区：新手坚决绕开</text>
        <text x="34" y="24" font-size="9.0" fill="#475569" font-weight="700">↑ 纵轴越高 = 业绩增速与筹码安全垫越高</text>
        <text x="44" y="292" font-size="9.0" fill="#475569" font-weight="600">← 极便宜（8–15年回本）</text>
        <text x="440" y="292" text-anchor="middle" font-size="9.0" fill="#475569" font-weight="600">估值合理分界（约 25–30 倍）</text>
        <text x="824" y="292" text-anchor="end" font-size="9.0" fill="#b91c1c" font-weight="600">极贵/泡沫（100–500 倍）→</text>
        {dots}
        <rect x="34" y="300" width="800" height="18" fill="#f8fafc" stroke="#e2e8f0" stroke-width="0.7" rx="3"/>
        <text x="434" y="313" text-anchor="middle" font-size="9.0" fill="#334155" font-weight="600">图例：<tspan fill="#009E73" font-weight="800">●</tspan> 当下底座（可逢低配） ｜ <tspan fill="#0072B2" font-weight="800">◆</tspan> 未来主攻（已上锁，等转绿/回调） ｜ <tspan fill="#D97706" font-weight="800">▲</tspan> 分歧观察 ｜ <tspan fill="#D55E00" font-weight="800">×</tspan> 高危回避（不碰）</text>
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway_a7}</div>
      <div class="chart-note">{note_a7}</div>
    </div>
    '''


def main() -> None:
    if "--check" in sys.argv[1:]:
        meta = load_meta()
        md_path = resolve_flagship_md(meta)
        assert md_path.exists(), f"Missing {md_path}"
        for fn in (
            svg_chart_a1_cycles,
            svg_chart_a2_split_and_futures,
            svg_chart_a3_macro_k_split,
            svg_chart_a4_clock,
            svg_chart_a5_targets_and_math,
            svg_chart_a6_sector_heatmap,
            svg_chart_a7_stock_quadrant,
        ):
            assert "<svg" in fn(meta)
        print(f"A-Share pure-web SVG check OK: {md_path.name} (7 vector charts ready)")
        return
    print("Pure-web mode: build_a_share_pdf.py exports SVG charts A1–A7 for scripts/build_site.py.")


if __name__ == "__main__":
    main()
