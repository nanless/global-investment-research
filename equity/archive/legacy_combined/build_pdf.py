#!/usr/bin/env python3
"""
Generate an editorial-grade, highly readable A4 PDF report:
2026年11月全球股市深度复盘与投资指南（五轮全渠道核查定稿 · 舒朗精读版）
Designed for effortless reading: 10.2pt body, 1.72 line-height, generous margins,
plain-language callouts, separate RMB/USD tables, and 6 crisp vector SVG charts.
"""
import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright

OUT_DIR = Path(__file__).resolve().parent
HTML_PATH = OUT_DIR / "global_equity_market_report_2026_11.html"
PDF_PATH = OUT_DIR / "global_equity_market_report_2026_11.pdf"


def fmt1(val: float) -> str:
    d = Decimal(str(val)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    sign = "+" if d > 0 else ""
    return f"{sign}{d}%"


def fmt2(val: float) -> str:
    d = Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "+" if d > 0 else ""
    return f"{sign}{d}%"


def svg_allocation_chart() -> str:
    """Chart 1: Clean Dual-Mandate x Dual-Phase Allocation Visual."""
    colors = {
        "us": "#1E4E79",
        "cn": "#C83E3B",
        "gl": "#4B8BBE",
        "fi": "#2D7A6E",
        "cb": "#0EA5A4",
        "cash": "#94A3B8",
        "gold": "#C9972C",
    }
    rows = [
        ("人民币 · 避险过渡期 (11.23–12.18)", [("us", 8), ("cn", 22), ("gl", 5), ("fi", 24), ("cb", 6), ("cash", 26), ("gold", 9)], "纯权益 35%"),
        ("人民币 · 2027 Q1 目标仓位",        [("us", 15), ("cn", 28), ("gl", 7), ("fi", 20), ("cb", 7), ("cash", 12), ("gold", 11)], "纯权益 50%"),
        ("美元本位 · 避险过渡期 (11.23–12.18)", [("us", 16), ("cn", 10), ("gl", 6), ("fi", 30), ("cash", 28), ("gold", 10)], "纯权益 32%"),
        ("美元本位 · 2027 Q1 目标仓位",        [("us", 30), ("cn", 15), ("gl", 10), ("fi", 24), ("cash", 10), ("gold", 11)], "纯权益 55%"),
    ]
    bar_x = 212
    bar_w = 426
    bar_h = 26
    svg = [
        '<svg viewBox="0 0 740 248" width="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: PingFang SC, Hiragino Sans GB, sans-serif;">',
        '<rect x="0" y="0" width="740" height="248" rx="7" fill="#FAFBFD" stroke="#DCE3EC" stroke-width="1"/>',
        '<text x="18" y="25" font-size="13" font-weight="700" fill="#0F2537">图 1：两阶段资产配置全景（先守住 12 月央行加息风暴，再把干火药分批换入权益）</text>',
    ]
    legend_items = [
        ("us", "美股"), ("cn", "A股+港股"), ("gl", "其他全球"),
        ("fi", "固收/TIPS/7-10Y"), ("cb", "AA+可转债"), ("cash", "干火药/汇兑"), ("gold", "黄金/尾险")
    ]
    lx = 18
    for key, label in legend_items:
        svg.append(f'<rect x="{lx}" y="38" width="10" height="10" rx="2" fill="{colors[key]}"/>')
        svg.append(f'<text x="{lx+14}" y="47" font-size="9.5" fill="#334155">{label}</text>')
        lx += 98 if key not in ("fi", "us") else (76 if key == "us" else 120)

    y_positions = [68, 105, 152, 189]
    svg.append('<line x1="18" y1="141" x2="722" y2="141" stroke="#CBD5E1" stroke-dasharray="4 3" stroke-width="1"/>')

    for (title, segs, tag), y in zip(rows, y_positions):
        svg.append(f'<text x="18" y="{y+17}" font-size="10.4" font-weight="600" fill="#1E293B">{title}</text>')
        cx = bar_x
        for k, pct in segs:
            w = bar_w * pct / 100.0
            svg.append(f'<rect x="{cx:.1f}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="{colors[k]}" stroke="#FFFFFF" stroke-width="1"/>')
            if pct >= 6:
                svg.append(f'<text x="{cx + w/2:.1f}" y="{y+16.5}" text-anchor="middle" font-size="9.5" font-weight="700" fill="#FFFFFF">{pct}%</text>')
            cx += w
        svg.append(f'<rect x="{bar_x + bar_w + 10}" y="{y+3}" width="80" height="20" rx="4" fill="#EFF6FF" stroke="#BFDBFE" stroke-width="0.9"/>')
        svg.append(f'<text x="{bar_x + bar_w + 50}" y="{y+16.5}" text-anchor="middle" font-size="9.3" font-weight="700" fill="#1E4E79">{tag}</text>')

    svg.append('<text x="18" y="235" font-size="8.6" fill="#64748B">说明：人民币方案新增 6%→7% 严选 AA+ 可转债；美元固收内含 12% 5–10Y TIPS 及 4% 战术 7–10Y 名义美债（不裸配 30 年长债）。</text>')
    svg.append('</svg>')
    return "\n".join(svg)


def svg_timeline_chart() -> str:
    """Chart 2: Clean 50-Day Catalyst & 3-Step Deployment Map."""
    svg = [
        '<svg viewBox="0 0 740 232" width="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: PingFang SC, Hiragino Sans GB, sans-serif;">',
        '<rect x="0" y="0" width="740" height="232" rx="7" fill="#FAFBFD" stroke="#DCE3EC" stroke-width="1"/>',
        '<text x="18" y="25" font-size="13" font-weight="700" fill="#0F2537">图 2：未来 50 天关键节点与“20% → 50% → 30%”三步建仓路线图</text>',
        '<rect x="292" y="40" width="186" height="110" rx="5" fill="#FEF2F2" stroke="#FCA5A5" stroke-dasharray="4 2" stroke-width="1.2"/>',
        '<text x="385" y="55" text-anchor="middle" font-size="9.6" font-weight="700" fill="#B91C1C">⚠ 美欧日三大央行同步加息窗口</text>',
        '<rect x="598" y="40" width="124" height="110" rx="5" fill="#FFFBEB" stroke="#FCD34D" stroke-dasharray="4 2" stroke-width="1.2"/>',
        '<text x="660" y="55" text-anchor="middle" font-size="9.4" font-weight="700" fill="#B45309">⚠ 301调查 + 1.10休战崖</text>',
        '<line x1="28" y1="99" x2="712" y2="99" stroke="#1E4E79" stroke-width="2.6"/>',
    ]
    nodes = [
        (50,  "11.23", "日股休市", "纳指QDII停牌", "#B91C1C", True),
        (118, "11.25–29", "美PCE通胀", "OPEC+定配额", "#1E4E79", False),
        (202, "11.30–12.4", "80%保证金", "恒科老权重稀释", "#047857", True),
        (322, "12.08–10", "美联储加息", "CPI与博通财报", "#B91C1C", False),
        (385, "12月上中旬", "中央经济", "工作会议定调", "#C9972C", True),
        (450, "12.17–18", "欧/日央行", "同步加息落地", "#B91C1C", False),
        (542, "12.18–23", "英伟达10-Q", "量化抛压缓和", "#047857", True),
        (660, "2027.01.10", "中美休战到期", "7国301落地", "#B45309", False),
    ]
    for x, dt, l1, l2, col, up in nodes:
        svg.append(f'<circle cx="{x}" cy="99" r="5.5" fill="{col}" stroke="#FFFFFF" stroke-width="1.8"/>')
        if up:
            svg.append(f'<line x1="{x}" y1="93" x2="{x}" y2="81" stroke="{col}" stroke-width="1"/>')
            svg.append(f'<text x="{x}" y="69" text-anchor="middle" font-size="8.8" font-weight="700" fill="{col}">{dt}</text>')
            svg.append(f'<text x="{x}" y="79" text-anchor="middle" font-size="8.4" fill="#1E293B">{l1}</text>')
            svg.append(f'<text x="{x}" y="118" text-anchor="middle" font-size="8.1" fill="#64748B">{l2}</text>')
        else:
            svg.append(f'<line x1="{x}" y1="105" x2="{x}" y2="117" stroke="{col}" stroke-width="1"/>')
            svg.append(f'<text x="{x}" y="129" text-anchor="middle" font-size="8.8" font-weight="700" fill="{col}">{dt}</text>')
            svg.append(f'<text x="{x}" y="140" text-anchor="middle" font-size="8.4" fill="#1E293B">{l1}</text>')
            svg.append(f'<text x="{x}" y="89" text-anchor="middle" font-size="8.1" fill="#64748B">{l2}</text>')

    tranches = [
        (24,  218, "#EFF6FF", "#1E4E79", "第一步 20%（11.26–12.02 · 0 美股）", "只买 TIPS / 7-10Y / AA+转债 / 红利"),
        (254, 256, "#ECFDF5", "#047857", "第二步 50%（12.18–12.23 · 主力出击）", "加息落地后买美股/港股硬科技/黄金金矿"),
        (522, 196, "#FEF3C7", "#B45309", "第三步 30%（2027.01 中旬）", "贸易悬崖明朗后收官（极端恐慌可提前）"),
    ]
    for tx, tw, bg, bd, t1, t2 in tranches:
        svg.append(f'<rect x="{tx}" y="164" width="{tw}" height="52" rx="6" fill="{bg}" stroke="{bd}" stroke-width="1.2"/>')
        svg.append(f'<text x="{tx + tw/2:.1f}" y="184" text-anchor="middle" font-size="9.4" font-weight="700" fill="{bd}">{t1}</text>')
        svg.append(f'<text x="{tx + tw/2:.1f}" y="203" text-anchor="middle" font-size="8.5" fill="#334155">{t2}</text>')
    svg.append('</svg>')
    return "\n".join(svg)


def svg_microstructure_dashboard() -> str:
    """Chart 3: Clean Market Plumbing & CFTC Reversals Visual."""
    svg = [
        '<svg viewBox="0 0 740 236" width="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: PingFang SC, Hiragino Sans GB, sans-serif;">',
        '<rect x="0" y="0" width="740" height="236" rx="7" fill="#FAFBFD" stroke="#DCE3EC" stroke-width="1"/>',
        '<text x="18" y="24" font-size="13" font-weight="700" fill="#0F2537">图 3：市场底层温度计（左：美股恐慌曲线倒挂｜右：推翻共识的两大期货持仓与流动性红线）</text>',

        '<rect x="18" y="38" width="344" height="182" rx="6" fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1"/>',
        '<text x="30" y="56" font-size="10.4" font-weight="700" fill="#0F2537">美股 VIX 期限结构全面倒挂（11.20 收盘）</text>',
        '<text x="30" y="70" font-size="8.6" fill="#64748B">短期恐慌远高于远期 · 做市商负 Gamma 达 -$73 亿</text>',
    ]
    for val in [25, 30, 35, 40]:
        yp = 190 - (val - 20) * 4.1
        svg.append(f'<line x1="50" y1="{yp:.1f}" x2="348" y2="{yp:.1f}" stroke="#F1F5F9" stroke-width="1"/>')
        svg.append(f'<text x="44" y="{yp+3:.1f}" text-anchor="end" font-size="8.4" fill="#94A3B8">{val}</text>')
    vix_pts = [
        ("9天VIX", 40.72, 72),
        ("现货VIX", 35.89, 130),
        ("3个月", 30.94, 188),
        ("12月期货", 28.46, 246),
        ("1月期货", 26.25, 296),
        ("2月期货", 25.39, 336),
    ]
    poly = [f"{xp},{190 - (val - 20) * 4.1:.1f}" for _, val, xp in vix_pts]
    svg.append(f'<polyline points="{" ".join(poly)}" fill="none" stroke="#B91C1C" stroke-width="2.5"/>')
    for lbl, val, xp in vix_pts:
        yp = 190 - (val - 20) * 4.1
        svg.append(f'<circle cx="{xp}" cy="{yp:.1f}" r="4.2" fill="#B91C1C" stroke="#FFFFFF" stroke-width="1.5"/>')
        svg.append(f'<text x="{xp}" y="{yp-8:.1f}" text-anchor="middle" font-size="8.5" font-weight="700" fill="#991B1B">{val:.1f}</text>')
        svg.append(f'<text x="{xp}" y="207" text-anchor="middle" font-size="8" fill="#475569">{lbl}</text>')
    svg.append('<rect x="184" y="80" width="160" height="34" rx="5" fill="#FEF2F2" stroke="#FECACA"/>')
    svg.append('<text x="264" y="94" text-anchor="middle" font-size="8.4" font-weight="700" fill="#B91C1C">高盛量化 CTA 机械抛压</text>')
    svg.append('<text x="264" y="107" text-anchor="middle" font-size="8" fill="#7F1D1D">反弹仍卖 $286 亿 / 跌卖 $806 亿</text>')

    svg.extend([
        '<rect x="374" y="38" width="348" height="182" rx="6" fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1"/>',
        '<text x="386" y="56" font-size="10.4" font-weight="700" fill="#0F2537">CFTC 期货持仓真相（11.20）与流动性红线</text>',
        '<rect x="386" y="66" width="324" height="36" rx="5" fill="#FEF2F2" stroke="#FECACA"/>',
        '<text x="396" y="81" font-size="9" font-weight="700" fill="#991B1B">10Y 美债对冲基金净空 -248 万手（占持仓近四成）</text>',
        '<text x="396" y="95" font-size="8.2" fill="#475569">极端拥挤空头 → 股市出事易引发美债暴力轧空</text>',
        '<rect x="386" y="108" width="324" height="36" rx="5" fill="#ECFDF5" stroke="#A7F3D0"/>',
        '<text x="396" y="123" font-size="9" font-weight="700" fill="#065F46">日元大投机客实为净多 +11.6 万手（非空头！）</text>',
        '<text x="396" y="137" font-size="8.2" fill="#475569">证伪“2024.8 式日元套息平仓”，关注日债资金回流</text>',
        '<rect x="386" y="150" width="157" height="60" rx="5" fill="#FFFBEB" stroke="#FDE68A"/>',
        '<text x="395" y="165" font-size="8.8" font-weight="700" fill="#92400E">美国资金蓄水池告急</text>',
        '<text x="395" y="180" font-size="8.3" fill="#1E293B">逆回购仅剩 <tspan font-weight="700">$4 亿</tspan>（清零）</text>',
        '<text x="395" y="195" font-size="8.3" fill="#B91C1C">准备金 <tspan font-weight="700">9.03% GDP</tspan>（&lt;10%）</text>',
        '<rect x="553" y="150" width="157" height="60" rx="5" fill="#EFF6FF" stroke="#BFDBFE"/>',
        '<text x="562" y="165" font-size="8.8" font-weight="700" fill="#1E4E79">中港筹码出清极深</text>',
        '<text x="562" y="180" font-size="8.3" fill="#1E293B">港股沽空 <tspan font-weight="700">25.54%</tspan>（恐慌）</text>',
        '<text x="562" y="195" font-size="8.3" fill="#047857">A股期指贴水 <tspan font-weight="700">22%–30%</tspan></text>',
        '</svg>'
    ])
    return "\n".join(svg)


def svg_erp_chart() -> str:
    """Chart 4: Clean Equity Risk Premium Comparison."""
    data = [
        ("恒生指数（按中国利率）", 9.82, 1.58, 8.24, "市盈率 10.1 倍"),
        ("沪深 300（前瞻盈利）",  8.40, 1.58, 6.82, "前瞻 PE 11.9 倍"),
        ("沪深 300（滚动 TTM）",  7.48, 1.58, 5.90, "10 年 32% 偏低分位"),
        ("恒生指数（按美元利率）", 9.82, 4.92, 4.90, "对照 4.92% 美债"),
        ("上证指数（滚动 TTM）",  6.26, 1.58, 4.68, "10 年 40% 分位"),
        ("恒生科技（滚动 TTM）",  5.36, 1.58, 3.78, "历史 4.9% 极低分位"),
        ("标普 500（11.20 前瞻）", 6.06, 4.92, 1.14, "前瞻 PE 16.5 倍"),
    ]
    svg = [
        '<svg viewBox="0 0 740 268" width="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: PingFang SC, Hiragino Sans GB, sans-serif;">',
        '<rect x="0" y="0" width="740" height="268" rx="7" fill="#FAFBFD" stroke="#DCE3EC" stroke-width="1"/>',
        '<text x="18" y="24" font-size="13" font-weight="700" fill="#0F2537">图 4：股票比国债多赚多少？——中美核心市场风险溢价（ERP）呈现“世纪级赔率差”</text>',
        '<rect x="18" y="36" width="10" height="10" rx="2" fill="#047857"/><text x="33" y="45" font-size="9.5" fill="#334155">股票相对国债的超额回报（安全垫越厚越好）</text>',
        '<rect x="296" y="36" width="10" height="10" rx="2" fill="#CBD5E1"/><text x="311" y="45" font-size="9.5" fill="#334155">当地 10 年期国债无风险利率</text>',
        '<rect x="498" y="36" width="10" height="10" rx="2" fill="#B91C1C"/><text x="513" y="45" font-size="9.5" fill="#334155">美股安全垫仅 +1.14%</text>',
    ]
    x0 = 162
    scale = 40.5
    for v in [0, 2, 4, 6, 8, 10]:
        gx = x0 + v * scale
        svg.append(f'<line x1="{gx:.1f}" y1="56" x2="{gx:.1f}" y2="236" stroke="#E2E8F0" stroke-width="1"/>')
        svg.append(f'<text x="{gx:.1f}" y="250" text-anchor="middle" font-size="9" fill="#64748B">{v}%</text>')

    y = 62
    for name, ep, rf, erp, note in data:
        is_us = "标普" in name
        erp_color = "#B91C1C" if is_us else "#047857"
        rf_w = rf * scale
        erp_w = erp * scale
        svg.append(f'<text x="18" y="{y+14}" font-size="10" font-weight="600" fill="#1E293B">{name}</text>')
        svg.append(f'<rect x="{x0}" y="{y}" width="{rf_w:.1f}" height="18.5" fill="#CBD5E1" rx="2"/>')
        if rf >= 1.5:
            svg.append(f'<text x="{x0 + rf_w/2:.1f}" y="{y+13}" text-anchor="middle" font-size="8.6" font-weight="600" fill="#334155">{rf:.2f}%</text>')
        svg.append(f'<rect x="{x0 + rf_w:.1f}" y="{y}" width="{erp_w:.1f}" height="18.5" fill="{erp_color}" rx="2"/>')
        svg.append(f'<text x="{x0 + rf_w + erp_w/2:.1f}" y="{y+13}" text-anchor="middle" font-size="9" font-weight="700" fill="#FFFFFF">+{erp:.2f}%</text>')
        svg.append(f'<text x="{x0 + (rf+erp)*scale + 8:.1f}" y="{y+13}" font-size="9" fill="#475569">{note}</text>')
        y += 25.0

    svg.append('<text x="18" y="262" font-size="8.4" fill="#64748B">数据截至 2026-11-20 收盘：中国 10Y 国债 1.58%，美国 10Y 国债 4.92%；港股 AH 溢价 137.68（近 17 个月高位）。</text>')
    svg.append('</svg>')
    return "\n".join(svg)


def svg_us_sector_chart() -> str:
    """Chart 5: US Styles & Key Sectors YTD Total Return (Nov 20, 2026)."""
    items = [
        ("能源 XLE（全年冠军）", 38.02, -6.85),
        ("半导体 SOXX（上周重挫）", 23.50, -17.35),
        ("美股大盘价值 IWD", 18.88, -6.04),
        ("必选消费 XLP（真避风港）", 18.70, -1.99),
        ("医疗保健 XLV（真防御）", 16.10, -6.02),
        ("美国区域银行 KRE（信用传染）", 10.80, -5.18),
        ("标普 500 等权 RSP", 9.59, -6.20),
        ("材料 XLB", 8.20, -7.45),
        ("房地产 XLRE（伪防御）", 7.74, -4.30),
        ("罗素小盘 2000 IWM", 4.95, -7.54),
        ("信息技术 XLK", 3.87, -12.49),
        ("公用事业 XLU（伪防御）", 2.09, -3.07),
        ("标普 500 SPY", 1.95, -8.56),
        ("工业 XLI", 1.61, -7.35),
        ("金融 XLF", 0.85, -7.00),
        ("纳斯达克 100 QQQ", -0.62, -10.51),
        ("可选消费 XLY", -4.90, -6.27),
        ("美股大盘成长 IWF", -13.80, -11.46),
        ("通信服务 XLC（垫底）", -14.20, -7.97),
    ]
    items.sort(key=lambda r: r[1], reverse=True)
    svg = [
        '<svg viewBox="0 0 740 426" width="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: PingFang SC, Hiragino Sans GB, sans-serif;">',
        '<rect x="0" y="0" width="740" height="426" rx="7" fill="#FAFBFD" stroke="#DCE3EC" stroke-width="1"/>',
        '<text x="18" y="24" font-size="13" font-weight="700" fill="#0F2537">图 5：2026 美股风格大裂变——大盘价值（+18.9%）甩开大盘成长（-13.8%）整整 32.7 个百分点</text>',
        '<text x="18" y="40" font-size="9.2" fill="#475569">柱体 = 年初至 11 月 20 日总回报；右侧标签 = 上周（11.13–20）暴跌周表现。必选消费在暴跌周五甚至逆市收涨。</text>',
    ]
    zero_x = 290.0
    scale = 8.0
    for v in [-15, -10, -5, 0, 10, 20, 30, 40]:
        gx = zero_x + v * scale
        stroke = "#475569" if v == 0 else "#E2E8F0"
        sw = "1.2" if v == 0 else "0.8"
        svg.append(f'<line x1="{gx:.1f}" y1="50" x2="{gx:.1f}" y2="398" stroke="{stroke}" stroke-width="{sw}"/>')
        svg.append(f'<text x="{gx:.1f}" y="413" text-anchor="middle" font-size="8.8" fill="#64748B">{v:+d}%</text>')

    y = 54
    for name, ytd, wk in items:
        is_style = any(k in name for k in ["IWD", "IWF", "RSP", "SPY", "QQQ", "IWM"])
        is_warn = "KRE" in name
        if ytd >= 0:
            col = "#D97706" if is_warn else ("#1E4E79" if is_style else "#047857")
            bx = zero_x
            bw = ytd * scale
            lbl_x = bx + bw + 5
            anchor = "start"
        else:
            col = "#991B1B" if is_style else "#DC2626"
            bw = abs(ytd) * scale
            bx = zero_x - bw
            lbl_x = bx - 5
            anchor = "end"
        fw = "700" if (is_style or is_warn) else "500"
        val_txt = fmt2(ytd) if abs(ytd) < 2.5 else fmt1(ytd)
        svg.append(f'<text x="16" y="{y+11.5}" font-size="9.4" font-weight="{fw}" fill="#1E293B">{name}</text>')
        svg.append(f'<rect x="{bx:.1f}" y="{y}" width="{max(bw, 2):.1f}" height="13.5" rx="2" fill="{col}"/>')
        svg.append(f'<text x="{lbl_x:.1f}" y="{y+10.5}" text-anchor="{anchor}" font-size="8.8" font-weight="700" fill="{col}">{val_txt}</text>')
        wk_col = "#B91C1C" if wk <= -10 else ("#047857" if wk > -3 else "#64748B")
        svg.append(f'<text x="722" y="{y+10.5}" text-anchor="end" font-size="8.6" font-weight="600" fill="{wk_col}">上周 {fmt1(wk)}</text>')
        y += 18.1

    svg.append('</svg>')
    return "\n".join(svg)


def svg_global_indices_chart() -> str:
    """Chart 6: Global 20 Major Equity Indices YTD (Through Nov 20, 2026)."""
    indices = [
        ("台湾加权 TAIEX", 24.41, "单周 -17.5% · 周一禁空令"),
        ("韩国 KOSPI", 15.56, "距高点 -48.1% · 筹备平准基金"),
        ("日本日经 225", 12.11, "周一休市 · 12.18 央行加息"),
        ("欧洲 STOXX 600", 5.70, "德国 2,100 亿欧元强军撑底"),
        ("英国 FTSE 100", 4.27, "低科技 + 资源属性抗跌"),
        ("罗素 2000", 4.02, "距 8 月高点 -15.2%"),
        ("德国 DAX", 1.28, "德国 ETF 场内折价 1.5%"),
        ("美国标普 500", 0.95, "跌破量化止损线 172 点"),
        ("中国中证红利", 0.47, "含息 ~+5% · A股唯一收正"),
        ("美国纳指 100", -0.87, "纳指 QDII 溢价 15%–48%"),
        ("印度 Nifty 50", -1.26, "外资涌入但受制高油价"),
        ("法国 CAC 40", -2.72, "法债危机与倒阁隐忧"),
        ("中国上证 50", -8.09, "上周五国家队 243 亿护盘"),
        ("中国科创 50", -8.41, "11 月反弹 +6% · 存储领衔"),
        ("中国上证指数", -10.96, "3,534 点 · 11.22 三箭齐发"),
        ("香港恒生指数", -12.56, "沽空 25.5% · 513530 折价"),
        ("中国沪深 300", -14.59, "10 年 32% 低位 · ERP 6.8%"),
        ("中国中证 1000", -25.63, "期指年化贴水约 24%"),
        ("中国创业板指", -30.94, "估值落入历史 2%–5% 谷底"),
        ("香港恒生科技", -36.35, "12.4 扩编稀释旧权重 40%"),
    ]
    svg = [
        '<svg viewBox="0 0 740 378" width="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: PingFang SC, Hiragino Sans GB, sans-serif;">',
        '<rect x="0" y="0" width="740" height="378" rx="7" fill="#FAFBFD" stroke="#DCE3EC" stroke-width="1"/>',
        '<text x="18" y="21" font-size="12.6" font-weight="700" fill="#0F2537">图 6：全球 20 大股指 2026 年内涨跌幅全景（截至 11 月 20 日收盘）</text>',
        '<text x="18" y="36" font-size="9" fill="#475569">亚洲 AI 硬件市场（台/韩/日）年内虽仍为正但刚遭血洗并启动救市；中港股市深蹲后赔率已极为突出。</text>',
    ]
    zero_x = 385.0
    scale = 6.0
    for v in [-40, -30, -20, -10, 0, 10, 20, 30]:
        gx = zero_x + v * scale
        stroke = "#475569" if v == 0 else "#E2E8F0"
        sw = "1.2" if v == 0 else "0.8"
        svg.append(f'<line x1="{gx:.1f}" y1="44" x2="{gx:.1f}" y2="355" stroke="{stroke}" stroke-width="{sw}"/>')
        svg.append(f'<text x="{gx:.1f}" y="368" text-anchor="middle" font-size="8.6" fill="#64748B">{v:+d}%</text>')

    y = 47
    for name, ytd, note in indices:
        is_cn = any(k in name for k in ["中国", "香港"])
        if ytd >= 0:
            col = "#C9972C" if is_cn else "#1E4E79"
            bx = zero_x
            bw = ytd * scale
            lbl_x = bx + bw + 5
            anchor = "start"
        else:
            col = "#B91C1C" if is_cn else "#64748B"
            bw = abs(ytd) * scale
            bx = zero_x - bw
            lbl_x = bx - 5
            anchor = "end"
        val_txt = fmt2(ytd) if abs(ytd) < 1.5 else fmt1(ytd)
        svg.append(f'<text x="16" y="{y+10}" font-size="9" font-weight="{"700" if is_cn else "500"}" fill="#1E293B">{name}</text>')
        svg.append(f'<rect x="{bx:.1f}" y="{y}" width="{max(bw, 2):.1f}" height="11.2" rx="2" fill="{col}"/>')
        svg.append(f'<text x="{lbl_x:.1f}" y="{y+9.5}" text-anchor="{anchor}" font-size="8.4" font-weight="700" fill="{col}">{val_txt}</text>')
        svg.append(f'<text x="724" y="{y+9.5}" text-anchor="end" font-size="8.2" fill="#475569">{note}</text>')
        y += 15.2

    svg.append('</svg>')
    return "\n".join(svg)


COMMON_CSS = """
  @page { size: A4; margin: 18mm 16mm 18mm 16mm; }
  @page :first { margin: 0; }
  * { box-sizing: border-box; }
  body {
    font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", -apple-system, "Helvetica Neue", sans-serif;
    color: #222F3E;
    font-size: 10.1pt;
    line-height: 1.72;
    margin: 0; padding: 0;
    font-variant-numeric: tabular-nums;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  /* ===== COVER PAGE ===== */
  .cover {
    width: 210mm; height: 297mm;
    background: #FFFFFF;
    display: flex; flex-direction: column;
    page-break-after: always;
    position: relative; overflow: hidden;
  }
  .cover-banner {
    background: linear-gradient(135deg, #0B1B2B 0%, #153654 58%, #1E4E79 100%);
    color: #FFFFFF;
    padding: 19mm 17mm 15mm 17mm;
    position: relative;
  }
  .cover-banner strong { color: #F3D179 !important; }
  .cover-accent-bar {
    position: absolute; top: 0; left: 0; right: 0; height: 6px;
    background: linear-gradient(90deg, #C9972C 0%, #E5B94E 50%, #047857 100%);
  }
  .cover-kicker {
    display: inline-block; font-size: 8.3pt; letter-spacing: 1.2px; font-weight: 700;
    color: #F3D179; border: 1px solid rgba(243,209,121,0.5);
    padding: 3px 10px; border-radius: 3px; margin-bottom: 11px;
  }
  .cover-title {
    font-size: 25pt; font-weight: 800; line-height: 1.24;
    margin: 0 0 8px 0; letter-spacing: -0.2px; color: #FFFFFF;
  }
  .cover-subtitle { font-size: 11.2pt; color: #CBD5E1; margin: 0 0 15px 0; }
  .cover-meta-row {
    display: grid; grid-template-columns: 1.15fr 1.15fr 0.9fr; gap: 12px;
    font-size: 8.6pt; color: #E2E8F0;
    border-top: 1px solid rgba(255,255,255,0.22); padding-top: 10px;
    line-height: 1.48;
  }
  .cover-body {
    padding: 10mm 17mm 9mm 17mm;
    flex: 1; display: flex; flex-direction: column; justify-content: space-between;
  }
  .kpi-title { font-size: 9pt; font-weight: 700; color: #0F2537; margin-bottom: 8px; }
  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 13px; }
  .kpi-card {
    background: #F7F9FC; border: 1px solid #DCE3EC; border-top: 3px solid #1E4E79;
    border-radius: 6px; padding: 8px 9.5px;
  }
  .kpi-card.neg { border-top-color: #B91C1C; }
  .kpi-card.pos { border-top-color: #047857; }
  .kpi-card.gold { border-top-color: #C9972C; }
  .kpi-label { font-size: 7.8pt; color: #64748B; font-weight: 600; }
  .kpi-val { font-size: 12.6pt; font-weight: 800; color: #0F2537; margin: 2px 0; }
  .kpi-sub { font-size: 7.35pt; font-weight: 600; line-height: 1.3; white-space: nowrap; }
  .text-pos { color: #047857; }
  .text-neg { color: #B91C1C; }
  .text-warn { color: #B45309; }

  .elevator-box {
    background: #F4F7FB; border: 1px solid #DCE3EC; border-left: 4.5px solid #0F2537;
    border-radius: 0 7px 7px 0; padding: 12px 15px; margin-bottom: 12px;
  }
  .elevator-box h3 { margin: 0 0 7px 0; font-size: 11pt; color: #0F2537; }
  .elevator-box ul { margin: 0; padding-left: 17px; }
  .elevator-box li { font-size: 9.2pt; line-height: 1.62; margin-bottom: 5.5px; text-align: justify; }
  .elevator-box li:last-child { margin-bottom: 0; }

  .toc-box { background: #FFFFFF; border: 1px solid #DCE3EC; border-radius: 6px; padding: 10px 14px; }
  .toc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font-size: 8.5pt; color: #334155; line-height: 1.5; }
  .toc-item strong { color: #0F2537; }
  .cover-footer { font-size: 7.4pt; color: #64748B; border-top: 1px solid #E2E8F0; padding-top: 7px; line-height: 1.45; }

  /* ===== EDITORIAL TYPOGRAPHY ===== */
  .section-banner {
    background: #0F2537; color: #FFFFFF;
    padding: 9px 14px; border-radius: 6px; margin: 14px 0 12px 0;
    display: flex; align-items: center; justify-content: space-between;
    page-break-after: avoid; break-after: avoid;
  }
  .section-banner.page-start { margin-top: 0; }
  .section-banner h1 { margin: 0; font-size: 12.6pt; font-weight: 800; white-space: nowrap; }
  .section-tag { font-size: 8pt; color: #F3D179; font-weight: 700; white-space: nowrap; margin-left: 10px; }

  h2 {
    font-size: 11.4pt; font-weight: 800; color: #0F2537;
    border-bottom: 1.8px solid #1E4E79; padding-bottom: 3.5px; margin: 15px 0 8px 0;
    page-break-after: avoid; break-after: avoid;
  }
  h3 {
    font-size: 10.3pt; font-weight: 700; color: #1E4E79;
    margin: 12px 0 6px 0;
    page-break-after: avoid; break-after: avoid;
  }
  p { margin: 0 0 8.5px 0; text-align: justify; }
  ul, ol { margin: 0 0 9px 0; padding-left: 18px; }
  li { margin-bottom: 4.5px; }
  strong { color: #0F2537; }
  code {
    font-family: "SF Mono", Menlo, monospace; font-size: 8.6pt;
    background: #EEF2F6; color: #0F2537; padding: 1px 4.5px; border-radius: 3px;
  }

  /* ===== READER-FRIENDLY CARDS & RIBBONS ===== */
  .tldr-ribbon {
    background: #EFF6FF;
    border-left: 4px solid #1E4E79;
    border-radius: 0 5px 5px 0;
    padding: 7.5px 12px;
    margin: 5px 0 9px 0;
    font-size: 9.4pt;
    color: #0F2537;
    font-weight: 600;
    break-inside: avoid;
  }
  .callout { border-radius: 6px; padding: 10px 13px; margin: 9px 0 11px 0; break-inside: avoid; font-size: 9.3pt; line-height: 1.62; }
  .callout-navy { background: #F4F7FB; border: 1px solid #DCE3EC; border-left: 4px solid #1E4E79; }
  .callout-warn { background: #FFFBEB; border: 1px solid #FDE68A; border-left: 4px solid #D97706; }
  .callout-red  { background: #FEF2F2; border: 1px solid #FECACA; border-left: 4px solid #B91C1C; }
  .callout-green{ background: #ECFDF5; border: 1px solid #A7F3D0; border-left: 4px solid #047857; }
  .callout-title { font-weight: 800; font-size: 9.8pt; margin-bottom: 5px; color: #0F2537; }
  .callout-red .callout-title { color: #991B1B; }
  .callout-warn .callout-title { color: #92400E; }
  .callout-green .callout-title { color: #065F46; }

  .step-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 9px 0 12px 0; break-inside: avoid; }
  .step-card {
    background: #F8FAFC; border: 1px solid #DCE3EC; border-top: 3.5px solid #1E4E79;
    border-radius: 6px; padding: 10px 11px; font-size: 8.9pt; line-height: 1.56;
  }
  .step-card.s2 { border-top-color: #047857; }
  .step-card.s3 { border-top-color: #D97706; }
  .step-card h4 { margin: 0 0 5px 0; font-size: 9.5pt; color: #0F2537; }
  .step-card p { margin: 0 0 4px 0; text-align: left; }
  .step-card p:last-child { margin-bottom: 0; }

  .pitfall-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin: 8px 0 11px 0; }
  .pitfall-card {
    background: #FFFDF7; border: 1px solid #F3E4B8; border-left: 3.5px solid #D97706;
    border-radius: 5px; padding: 9px 11px; font-size: 8.9pt; line-height: 1.56;
    break-inside: avoid;
  }
  .pitfall-card.full { grid-column: 1 / -1; }
  .pitfall-card h4 { margin: 0 0 4px 0; font-size: 9.3pt; color: #92400E; }
  .pitfall-card p { margin: 0; }

  .audit-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 7px 0 6px 0; }
  .audit-card {
    background: #F8FAFC; border: 1px solid #DCE3EC; border-radius: 6px;
    padding: 8px 10px; font-size: 8.65pt; line-height: 1.52;
    break-inside: avoid;
  }
  .audit-head { display: flex; align-items: flex-start; gap: 6px; margin-bottom: 4px; }
  .audit-title { font-weight: 800; color: #0F2537; font-size: 9pt; line-height: 1.35; }

  .pill-del { display:inline-block; background:#FEE2E2; color:#991B1B; font-weight:700; padding:1px 6px; border-radius:3px; font-size:7.8pt; white-space:nowrap; }
  .pill-mod { display:inline-block; background:#FEF3C7; color:#92400E; font-weight:700; padding:1px 6px; border-radius:3px; font-size:7.8pt; white-space:nowrap; }
  .pill-add { display:inline-block; background:#D1FAE5; color:#065F46; font-weight:700; padding:1px 6px; border-radius:3px; font-size:7.8pt; white-space:nowrap; }

  /* ===== CLEAN AIRY TABLES ===== */
  table { width: 100%; border-collapse: collapse; margin: 8px 0 12px 0; font-size: 8.75pt; line-height: 1.52; }
  thead { display: table-header-group; }
  tr { break-inside: avoid; }
  th { background: #0F2537; color: #FFFFFF; font-weight: 700; text-align: left; padding: 6.5px 7.5px; border: 1px solid #0F2537; }
  td { padding: 6px 7.5px; border: 1px solid #DCE3EC; vertical-align: top; }
  tbody tr:nth-child(even) { background: #F8FAFC; }
  .compact-tbl { font-size: 8.3pt; line-height: 1.44; }
  .compact-tbl th { padding: 5.5px 6.5px; }
  .compact-tbl td { padding: 5px 6.5px; }
  .appendix-tbl { font-size: 7.75pt; line-height: 1.32; margin: 5px 0 8px 0; }
  .appendix-tbl th { padding: 4px 5.5px; }
  .appendix-tbl td { padding: 3.1px 5.5px; }
  .num { text-align: right; white-space: nowrap; }
  .ctr { text-align: center; }
  .nowrap { white-space: nowrap; }
  .badge-pos { color: #047857; font-weight: 700; }
  .badge-neg { color: #B91C1C; font-weight: 700; }
  .badge-gold { color: #B45309; font-weight: 700; }

  .chart-wrap { margin: 10px 0 13px 0; break-inside: avoid; }
  .page-break { page-break-before: always; break-before: page; }
  .small-note { font-size: 8pt; color: #64748B; line-height: 1.5; margin-top: 2px; }
"""

COVER_HTML_BLOCK = """
<div class="cover">
  <div class="cover-banner">
    <div class="cover-accent-bar"></div>
    <div class="cover-kicker">GLOBAL EQUITY STRATEGY · 5-ROUND OMNICHANNEL CONVERGED EDITION</div>
    <h1 class="cover-title">2026 年 11 月全球股市深度复盘与投资指南</h1>
    <div class="cover-subtitle">风暴眼中的守与攻：美股、A 股与港股投资策略（结论先行 · 重点论据先行 · 舒朗精读版）</div>
    <div class="cover-meta-row">
      <div><strong>数据截点：</strong>2026 年 11 月 22 日深夜<br>（含 11.20 收盘与周末实时动态）</div>
      <div><strong>调研广度：</strong>5 轮 · 19 位全渠道子代理<br>（13F / CFTC / 管道 / 雪球 / Reddit）</div>
      <div><strong>纠偏闭环：</strong>累计 26 项纠偏升级<br>（无自相矛盾 · 全文说人话）</div>
    </div>
  </div>

  <div class="cover-body">
    <div>
      <div class="kpi-title">全球核心市场实时仪表盘（截至 2026 年 11 月 22 日深夜）</div>
      <div class="kpi-grid">
        <div class="kpi-card neg">
          <div class="kpi-label">标普 500 / 纳指 100</div>
          <div class="kpi-val">6,910 / 25,029</div>
          <div class="kpi-sub text-neg">周跌-8.6%/-10.4%·破CTA线</div>
        </div>
        <div class="kpi-card neg">
          <div class="kpi-label">VIX 恐慌 / 量化抛压</div>
          <div class="kpi-val">35.89 / 806亿</div>
          <div class="kpi-sub text-neg">盘中破40 · 反弹仍抛$286亿</div>
        </div>
        <div class="kpi-card gold">
          <div class="kpi-label">10Y 美债 / 银行准备金</div>
          <div class="kpi-val">4.92% / 9.03%</div>
          <div class="kpi-sub text-warn">逆回购$4亿 · 破10%红线</div>
        </div>
        <div class="kpi-card neg">
          <div class="kpi-label">AI 债务传染（上周）</div>
          <div class="kpi-val">CRWV -25.6%</div>
          <div class="kpi-sub text-neg">ORCL -19% · 银行KRE -5.2%</div>
        </div>
        <div class="kpi-card pos">
          <div class="kpi-label">沪深 300 / 中证红利</div>
          <div class="kpi-val">3,955 / 5,530</div>
          <div class="kpi-sub text-pos">安全垫6.82% · 11.22三箭</div>
        </div>
        <div class="kpi-card pos">
          <div class="kpi-label">恒生指数 / 港股沽空</div>
          <div class="kpi-val">22,411 / 25.5%</div>
          <div class="kpi-sub text-pos">AH溢价137.7 · 513530折价</div>
        </div>
        <div class="kpi-card gold">
          <div class="kpi-label">黄金 / 布油 / 海峡</div>
          <div class="kpi-val">$3,535 / $92.6</div>
          <div class="kpi-sub text-warn">金3日-$314 · 运力低65%</div>
        </div>
        <div class="kpi-card pos">
          <div class="kpi-label">24/7 实时比特币</div>
          <div class="kpi-val">~$61,000</div>
          <div class="kpi-sub text-pos">周六爆仓$26亿后周日反弹</div>
        </div>
      </div>

      <div class="elevator-box">
        <h3>30 秒电梯版结论：现在是什么局势？我该怎么做？</h3>
        <ul>
          <li><strong>总原则（先守后攻，绝不急着一把抄底）：</strong>12 月 8–18 日美、欧、日三大央行大概率<strong>十天内同步加息</strong>（跌市没有“央行放水护盘”）。12 月 18 日前把纯股票仓位压低到 <strong>32%–35%</strong>，手握 <strong>26%–28%</strong> 现金干火药，随后分三步（20% → 50% → 30%）低吸。</li>
          <li><strong>美股（业绩没崩，但筹码还没洗干净）：</strong>美企三季报大增 32.9%、台积电 10 月营收创新高，但量化基金还有数百亿美元机械卖盘，且美国散户仍在高位狂抄科技股。<strong>12 月 18 日前暂不新买美股</strong>，存量仓位转向标普等权、价值、医疗与必选消费；12 月下旬再买 AI 存储龙头与精选科技。</li>
          <li><strong>A 股与港股（上有顶、下有铁底，打“哑铃”最稳）：</strong>11 月 22 日晚“降保证金回 80%（含存量释 4,000 亿）+ 创业板做市商 + 28 亿降费”共振韩台救市，砸出极强政策底；但 11 月新房、汽车仍偏冷且面临 1.10 中美休战悬崖。建议 <strong>60% 高股息底仓 + 40% 国产替代/硬科技</strong>，内地投资者可新增 <strong>6–7% 严选 AA+ 可转债</strong>，并借道<strong>折价 QDII 港股红利（513530 / 513950）</strong>直省 10–18% 红利税。</li>
          <li><strong>跨资产压舱石：</strong><strong>5–10 年期通胀保值美债（TIPS，实际收益 ~2.9%）</strong>攻守兼备；黄金等 12 月 9 日美联储加息落地后，用“现货黄金 + 优质金矿股”分批定投。</li>
        </ul>
      </div>

      <div class="toc-box">
        <div class="kpi-title" style="margin-bottom:5px;">阅读路线图（结论放最前面，细节与数据放后面，按需翻阅）</div>
        <div class="toc-grid">
          <div class="toc-item"><strong>第一部分：可直接照抄的配置方案与避坑指南</strong>（人民币/美元分表、周一提醒、三步建仓与四条止损线）</div>
          <div class="toc-item"><strong>第四部分：未来三种剧本、七大风险与 50 天日历</strong>（悲观概率升至 30–32%、一目了然的盯盘红灯）</div>
          <div class="toc-item"><strong>第二部分：支撑结论的五大核心逻辑</strong>（为什么没央行护盘、美股筹码真相、AI 债务外溢与全球赔率差）</div>
          <div class="toc-item"><strong>第五部分：五轮核查是如何帮我们避坑纠偏的？</strong>（推翻 8 大市场错觉的前后对照故事）</div>
          <div class="toc-item"><strong>第三部分：近期全球股市到底发生了什么？</strong>（像看复盘大片一样读懂美股、A/H 股与全球动荡）</div>
          <div class="toc-item"><strong>附录：全渠道实时数据速查总表</strong>（2026 年 11 月 22 日深夜精准行情、管道与权威信源）</div>
        </div>
      </div>
    </div>

    <div class="cover-footer">
      <strong>免责声明：</strong>本报告基于截至 2026 年 11 月 22 日深夜之公开行情、央行/统计局/交易所公告、SEC 13F、CFTC 期货持仓及海内外社区数据编写，仅供投资研究与资产配置框架参考，不构成针对任何个人的投资建议或收益承诺。市场存在地缘与信用风险，请结合自身情况独立决策。
    </div>
  </div>
</div>
"""

BODY_HTML_BLOCK = f"""
<!-- ==================== PART 1: CONCLUSIONS & ACTIONABLE PLAN ==================== -->
<div class="section-banner page-start">
  <h1>第一部分：核心结论与可直接照抄的配置方案</h1>
  <div class="section-tag">结论先行 · 先看怎么配、怎么避坑</div>
</div>

<h2>1.1 两套配置方案：区分“内地人民币投资者”与“海外美元投资者”</h2>
<p>不同货币本位的投资者，面临完全不同的汇率趋势、红利税负和跨境渠道限制（例如内地买美股 ETF 面临高溢价，买港股通要交 20%–28% 红利税）。因此，我们将方案明确拆为<strong>两套本位</strong>和<strong>两个阶段</strong>：先在<strong>避险过渡期（11.23–12.18）</strong>压低股票仓位扛过央行加息风暴，再在<strong>2027 Q1 目标期</strong>把手里现金分批换入高赔率资产。</p>

<div class="chart-wrap">
  {svg_allocation_chart()}
</div>

<h3>方案 A：中国内地投资者（人民币本位）</h3>
<table>
  <thead>
    <tr>
      <th style="width:17%;">资产类别</th>
      <th class="ctr" style="width:14%;">避险过渡期<br>(11.23–12.18)</th>
      <th class="ctr" style="width:14%;">2027 Q1<br>目标仓位</th>
      <th style="width:55%;">怎么买、买什么？（大白话操作要点）</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>A 股 + 港股</strong></td>
      <td class="ctr"><strong>22%</strong><br><span style="font-size:7.6pt;color:#64748B;">(A 16% + H 6%)</span></td>
      <td class="ctr"><strong>28%</strong><br><span style="font-size:7.6pt;color:#64748B;">(A 18% + H 10%)</span></td>
      <td><strong>60% 守底仓：</strong>A 股买满 1 年免税的 <code>中证红利低波 512890</code> 与国有大行；港股高息借道<strong>折价 QDII 港股红利 <code>513530</code>(-0.76%) 或 <code>513950</code>(-1.02%)</strong>，合法省下 10%–18% 红利税。<br><strong>40% 搏弹性：</strong>半导体设备与国产存储（<code>长鑫科技</code> 链）、创新药出海、低美依赖出海龙头；<strong>12 月 7 日调仓后再买恒生科技硬科技</strong>。</td>
    </tr>
    <tr>
      <td><strong>美股权益</strong></td>
      <td class="ctr"><strong>8%</strong></td>
      <td class="ctr"><strong>15%</strong></td>
      <td><strong>严禁买场内美股科技 QDII！</strong>纳指科技 <code>159509</code> 周一隐含溢价高达 45%–48%。仅通过无溢价的场外限额基金或离岸账户，在 <strong>12 月 18 日后</strong>分批买标普等权、大盘价值与医疗消费。</td>
    </tr>
    <tr>
      <td><strong>其他全球市场</strong></td>
      <td class="ctr"><strong>5%</strong></td>
      <td class="ctr"><strong>7%</strong></td>
      <td><strong>隐藏折价红利：</strong>场内非美 QDII 全线折价（德国 <code>513030</code> -1.5%、日经 <code>513520</code> -1.3%、中概 <code>513050</code> -1.3%）。首选受益财政扩张的德国工业防务；<strong>暂停加仓印度</strong>（等油价回落至 95 美元下方）。</td>
    </tr>
    <tr>
      <td><strong>境内固收 + 转债</strong></td>
      <td class="ctr"><strong>30%</strong><br><span style="font-size:7.6pt;color:#047857;">债24% + 转债6%</span></td>
      <td class="ctr"><strong>27%</strong><br><span style="font-size:7.6pt;color:#047857;">债20% + 转债7%</span></td>
      <td>中短国债/高评级债打底；<strong>新增 6%–7% 严选 AA+/AAA 可转债</strong>（百元溢价率跌至 25.37% 历史低位），但严格剔除弱信用与光伏破面债，只选国企与银行龙头。</td>
    </tr>
    <tr>
      <td><strong>干火药 + 汇兑对冲</strong></td>
      <td class="ctr"><strong>26%</strong><br><span style="font-size:7.6pt;color:#64748B;">RMB 20% + USD 6%</span></td>
      <td class="ctr"><strong>12%</strong><br><span style="font-size:7.6pt;color:#64748B;">RMB 6% + USD 6%</span></td>
      <td>人民币货基作随时抄底的弹药；<strong>留 6% 美元短债专门对冲“1 月 10 日中美关税升级”黑天鹅</strong>（不重配，因机构普遍看人民币明年升向 6.40–6.46 会吃掉利息）。</td>
    </tr>
    <tr>
      <td><strong>黄金与尾部对冲</strong></td>
      <td class="ctr"><strong>9%</strong><br><span style="font-size:7.6pt;color:#B45309;">金6% + 尾险3%</span></td>
      <td class="ctr"><strong>11%</strong><br><span style="font-size:7.6pt;color:#B45309;">金8% + 尾险3%</span></td>
      <td>12 月 9 日美联储加息落地后，分批定投<strong>黄金 ETF + 优质金矿龙头（如紫金矿业）</strong>；留 3% 做油价冲破 110 美元的尾部保护。</td>
    </tr>
    <tr style="background:#EFF6FF;font-weight:700;">
      <td><strong>合计（纯权益）</strong></td>
      <td class="ctr text-pos"><strong>100%（35%）</strong></td>
      <td class="ctr text-pos"><strong>100%（50%）</strong></td>
      <td>保守型可将目标纯权益下调至 ~35%；激进型可放宽至 65%–70%（12.18 前均建议留足 ≥18% 现金）。</td>
    </tr>
  </tbody>
</table>

<h3>方案 B：海外 / 离岸投资者（美元本位）</h3>
<table>
  <thead>
    <tr>
      <th style="width:17%;">资产类别</th>
      <th class="ctr" style="width:14%;">避险过渡期<br>(11.23–12.18)</th>
      <th class="ctr" style="width:14%;">2027 Q1<br>目标仓位</th>
      <th style="width:55%;">怎么买、买什么？（大白话操作要点）</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>美股权益</strong></td>
      <td class="ctr"><strong>16%</strong></td>
      <td class="ctr"><strong>30%</strong></td>
      <td>过渡期仅留<strong>标普等权（<code>RSP</code>）、大盘价值（<code>VTV/IWD</code>）、医疗（<code>XLV</code>）、必选消费（<code>XLP</code>）与苹果（<code>AAPL</code>）</strong>；<strong>12 月 18 日后</strong>再加仓 AI 企业级存储龙头（<code>MU/STX/WDC</code>）与博通（<code>AVGO</code>）。</td>
    </tr>
    <tr>
      <td><strong>中国 A + H 股</strong></td>
      <td class="ctr"><strong>10%</strong></td>
      <td class="ctr"><strong>15%</strong></td>
      <td>离岸直买港股红利仅扣 <strong>10% 预扣税</strong>，性价比极高。过渡期守港股高息央国企（股息率近 6.9%），<strong>12 月 7 日调仓后</strong>介入硬科技与高沽空逼空机会。</td>
    </tr>
    <tr>
      <td><strong>其他全球市场</strong></td>
      <td class="ctr"><strong>6%</strong></td>
      <td class="ctr"><strong>10%</strong></td>
      <td>适当收敛仓位防美国年底 7 国 301 调查。首选<strong>德国工业防务</strong>与<strong>英/加/澳资源价值股</strong>；印度严守布油 &lt;$95 前提；韩台芯片等 12 月下旬出清后再看。</td>
    </tr>
    <tr>
      <td><strong>美元核心固收</strong></td>
      <td class="ctr"><strong>30%</strong><br><span style="font-size:7.6pt;color:#047857;">短14/TIPS12/7-10Y 4</span></td>
      <td class="ctr"><strong>24%</strong><br><span style="font-size:7.6pt;color:#047857;">短8/TIPS12/7-10Y 4</span></td>
      <td><strong>12% 重配 5–10Y US TIPS</strong>（锁定 ~2.9% 实际收益，抗通胀防衰退两头通吃）；<strong>新增 4% 战术 7–10Y 名义美债</strong>博弈极端空头轧空；<strong>不裸配 30 年期长债</strong>。</td>
    </tr>
    <tr>
      <td><strong>美元干火药</strong></td>
      <td class="ctr"><strong>28%</strong></td>
      <td class="ctr"><strong>10%</strong></td>
      <td>停泊在 3–6 个月美国国库券（<strong>4.32%</strong>）或政府货基（<strong>3.95%</strong>），坐收高息静待 12 月下旬黄金买点。</td>
    </tr>
    <tr>
      <td><strong>黄金与尾部对冲</strong></td>
      <td class="ctr"><strong>10%</strong><br><span style="font-size:7.6pt;color:#B45309;">金7% + 期权3%</span></td>
      <td class="ctr"><strong>11%</strong><br><span style="font-size:7.6pt;color:#B45309;">金8% + 期权3%</span></td>
      <td>12 月 9 日后分批配置<strong>现货黄金（<code>GLD</code>）+ 头部金矿股（<code>NEM/AEM</code>）</strong>；用 3% 虚值布油/VIX 看涨价差防霍尔木兹突然断航。</td>
    </tr>
    <tr style="background:#EFF6FF;font-weight:700;">
      <td><strong>合计（纯权益）</strong></td>
      <td class="ctr text-pos"><strong>100%（32%）</strong></td>
      <td class="ctr text-pos"><strong>100%（55%）</strong></td>
      <td>预留高达 23 个百分点的现金弹性，等风暴眼过后从容捡筹码。</td>
    </tr>
  </tbody>
</table>

<h2>1.2 周一开盘提醒与“三步建仓”时间表</h2>

<div class="callout callout-navy">
  <div class="callout-title">⚡ 周一（2026 年 11 月 23 日）开盘前必看的三件事</div>
  <p style="margin-bottom:0;"><strong>① 盘面偏薄波动大：</strong>日本东京股市周一因勤劳感谢日<strong>全天休市</strong>（周二复市补跌/补涨），美国本周四感恩节休市、周五提前收盘。<strong>② 多空正面撞车：</strong>中国“三箭救市”与韩台稳市，将直接对撞上周五纳指 -5.28%、英伟达 -14% 的暴跌余波及早 7:00 CME 美股期货定价。<strong>③ 三条开盘纪律：</strong>一不追高券商开盘；二不碰早盘停牌复牌的高溢价纳指 QDII；三留意上周五暴涨创新高的国有大行是否出现短线“跷跷板”歇脚。</p>
</div>

<div class="chart-wrap">
  {svg_timeline_chart()}
</div>

<div class="step-grid">
  <div class="step-card">
    <h4>第一步｜花掉 20% 现金<br><span style="font-weight:500;color:#1E4E79;">11 月 26 日 – 12 月 2 日</span></h4>
    <p><strong>前提：</strong>11.25 美国 10 月 PCE 通胀不失控，11.29 OPEC+ 没引爆油价破百。</p>
    <p><strong>买什么：</strong><strong>这一批 0 买入美股！</strong>只买稳健债底与红利——5–10Y TIPS、4% 战术美债、严选 AA+ 可转债、A 股中证红利与折价港股红利 QDII。</p>
  </div>
  <div class="step-card s2">
    <h4>第二步｜花掉 50% 现金（主攻）<br><span style="font-weight:500;color:#047857;">12 月 18 日 – 12 月 23 日</span></h4>
    <p><strong>前提：</strong>美、欧、日三大央行加息全部落地 + 中央经济工作会议定调 + 英伟达 10-Q 与恒科调仓消化完毕。</p>
    <p><strong>买什么：</strong>主力弹药投入美股等权/价值与 AI 存储龙头、港股硬科技、A 股国产替代进攻端，以及黄金与金矿股。</p>
  </div>
  <div class="step-card s3">
    <h4>第三步｜花掉最后 30% 现金<br><span style="font-weight:500;color:#B45309;">2027 年 1 月中旬</span></h4>
    <p><strong>前提：</strong>美国年底 7 国 301 调查落地 + 明年 1 月 10 日中美贸易休战是否延期明朗。</p>
    <p><strong>加速特例：</strong>若 12 月提前跌破标普 6,350 且 VIX &gt;45、同时美银现金回升 &gt;4.5% 且美国散户杠杆 ETF 转净流出，可提前合并出手。</p>
  </div>
</div>

<h2>1.3 必须绕开的“五大实战暗坑”与“四条保命止损线”</h2>

<div class="pitfall-grid">
  <div class="pitfall-card">
    <h4>暗坑一：闭眼买内地场内美股 QDII，惨遭双重暴击</h4>
    <p>景顺纳指科技（<code>159509</code>）官方溢价已达 <strong>+36.8%</strong>，计入周五夜盘暴跌后周一隐含溢价逼近 <strong>45%–48%</strong>，多只纳指 ETF 周一早盘停牌。<strong>铁律：场内溢价超过 2%–3% 坚决不碰</strong>；反观德国、日经、印度、中概等非美 QDII 全线折价 0.3%–1.9%，完全可零溢价买。</p>
  </div>
  <div class="pitfall-card">
    <h4>暗坑二：港股通买高息股白交 20%–28% 红利税</h4>
    <p>内地个人走港股通买 H 股要扣 20% 税、买中移动/中海油等红筹综合扣近 <strong>28%</strong>（6.5% 股息到手仅剩 4.68%）。<strong>破局法：</strong>A 股买满 1 年免税的 <code>512890</code>，港股改买 <strong>QDII 红利 ETF <code>513530</code>(-0.76%) 或 <code>513950</code>(-1.02%)</strong>，合法享 10% 税率且折价！</p>
  </div>
  <div class="pitfall-card">
    <h4>暗坑三：盲信低价可转债“到期肯定刚兑”</h4>
    <p>11 月 13–17 日<strong><code>侨银转债</code></strong>在停牌后突发违约预警、惊魂 72 小时才压哨兑付，叠加光伏等弱信用破面债扩容，“无脑摊大饼买临期低价转债”已彻底失效。配置转债必须死守 <strong>AA+/AAA 高评级国企与银行龙头</strong>。</p>
  </div>
  <div class="pitfall-card">
    <h4>暗坑四：周一追高券商，或 12 月 4 日前抢买恒生科技</h4>
    <p>2023 年 8 月底同样降保证金至 80% 后券商周一高开低走阴跌 5 个月，切忌追高；且 12 月 4 日盘后恒生科技由 30 只扩至 50 只将<strong>被动稀释腾讯/阿里/美团权重约 40%</strong>，引发机械卖盘，12 月 7 日落地后再买更从容。</p>
  </div>
  <div class="pitfall-card full">
    <h4>暗坑五：误把美股公用事业（<code>XLU</code>）和地产（<code>XLRE</code>）当成“安全避风港”</h4>
    <p>2026 年这两大传统防御板块已经变质：<code>XLU</code> 挤满炒作 AI 数据中心电力的拥挤筹码，股息率（2.8%）反而倒挂 10 年期美债 200 个基点；<code>XLRE</code> 直面 5% 高利率再融资墙和数据中心信用风险。<strong>美股真正的避风港只有医疗（<code>XLV</code>）与必选消费（<code>XLP</code>）</strong>。</p>
  </div>
</div>

<div class="callout callout-red">
  <div class="callout-title">四条保命止损线（触发任意一条立即执行减仓，绝不抱幻想）</div>
  <ul style="margin-bottom:0;">
    <li><strong>红线 ① 油价失控：</strong>布伦特原油连续 5 天站稳 <strong>105 美元/桶</strong> → 清仓印度与美股顺周期，切入 TIPS、虚值原油看涨及英/加/澳资源股。</li>
    <li><strong>红线 ② 关税休战破裂：</strong>年底 301 调查或明年 1 月 10 日中美谈判破裂、全面重启高关税与稀土禁运 → 压缩中国进攻股回纯红利，人民币本位将美元对冲提至 12%。</li>
    <li><strong>红线 ③ AI 信用传染升级：</strong>美国投资级债利差破 <strong>120–130bps</strong>、高收益债破 <strong>450bps</strong>，或甲骨文降级垃圾债、区域银行 <code>KRE</code> 破位 → 暂停一切股票抄底，全面转向 2–10Y 美债与 TIPS。</li>
    <li><strong>红线 ④ 美国银行流动性断流：</strong>隔夜利率 <code>SOFR</code> 高出 <code>IORB</code> <strong>20 基点以上</strong>，或美联储银行准备金跌破 <strong>2.85 万亿美元</strong> → 冻结全部新增权益买单，防范类似 2019 年 9 月的美元“钱荒”。</li>
  </ul>
</div>

<!-- ==================== PART 2: FIVE CORE LOGICS ==================== -->
<div class="page-break"></div>
<div class="section-banner page-start">
  <h1>第二部分：支撑结论的五大核心逻辑</h1>
  <div class="section-tag">重点论据先行 · 为什么这么判断？</div>
</div>

<h2>逻辑一：这次暴跌没有“央行救市保护伞”，且美元流动性蓄水池已经见底</h2>
<div class="tldr-ribbon">一句话看懂：过去几年每次恐慌都能闭眼抄底，是因为央行随时准备降息放水；但这一次，美、欧、日央行将在 12 月中旬反手同步加息。</div>
<p>第五轮最新核实纠正了一个关键误区：此前有旧报道称霍尔木兹海峡运力已恢复 80%（其实包含陆路管道绕行）。据英国海事监测组织（UKMTO）11 月下旬最新数据，<strong>海峡直航商船运力仍比战前锐减约 65%</strong>；就在 11 月 20–21 日，阿曼海域再发多起油轮遇袭，战争险保费飙升至船价的 <strong>7.5%–10%</strong>（过一趟海峡仅保费就要 750 万–1,000 万美元），伊朗外长周末也拒绝了卡塔尔调停。高油价（布油 92.57 美元，年内 +52%）重新点燃美欧通胀。</p>
<p>面对 3.5%–4.0% 的顽固通胀和依然强劲的美国经济（三季度 GDP +3.4%、制造业 PMI 55.5），由凯文·沃什掌舵的美联储（9 月已加息至 3.75%–4.00%）与欧央行、日本央行，大概率将在 <strong>12 月 8 日至 18 日十天内接连加息</strong>（市场定价 85%–97%）；美联储理事库克 11 月 20 日更警告“后续可能需要更大幅度的加息”。与此同时，过去几年兜底美元流动性的美联储隔夜逆回购已<strong>彻底清零至仅剩 4 亿美元</strong>，银行准备金占美国 GDP 比重跌至 <strong>9.03%（跌破 10% 安全红线）</strong>，年末市场缺乏缓冲垫。</p>

<h2>逻辑二：美股并非“实体经济崩了”，而是“量化砸盘 + 散户死扛”还没洗干净</h2>
<div class="tldr-ribbon">一句话看懂：AI 的物理订单还在爆表，但美股筹码和杠杆结构极其脆弱，现在一把梭哈很容易接在半山腰。</div>
<p>从基本面看，美国企业根本没有衰退：标普 500 三季度整体盈利同比大增 <strong>32.9%</strong>，科技七巨头之外的“标普 493”盈利增速罕见反超七巨头；<strong>台积电 10 月营收暴增 +59.7% 创历史新高</strong>；《金融时报》周六更独家曝出戴尔、惠普、联想、超微对已签单的 AI 服务器<strong>追涨价高达 45%</strong>。标普动态市盈率经上周暴跌也已回落到 <strong>16.5 倍</strong>（低于十年均值 19.1 倍）。</p>
<p>但金融系统的微观数据清晰告诉我们<strong>底部还没夯实</strong>：一方面，标普跌穿高盛趋势量化（CTA）长期线超过 170 点，模型测算即便反弹，量化基金下周仍要机械卖出 <strong>286 亿美元</strong>（若续跌则高达 <strong>806 亿美元</strong>）；另一方面，美银调查显示机构现金仓位反降至 <strong>3.6%</strong>，而 Vanda 追踪发现美国散户仍在 <strong>99% 历史极值力度</strong>狂买英伟达（3 日净买 16 亿）与杠杆 ETF——散户根本没投降！反观刚披露的三季度 13F 顶级巨鲸，<strong>伯克希尔囤积 3,523 亿美元现金</strong>、<strong>德鲁肯米勒清仓 45 只股票转买金矿</strong>、<strong>段永平暴跌前大砍 63% 英伟达</strong>、大空头 <strong>Burry</strong> 虽止盈一半半导体空单但死守 2027 纳指空单。</p>

<div class="chart-wrap">
  {svg_microstructure_dashboard()}
</div>

<h2>逻辑三：AI 债务裂缝已外溢至银行股，CFTC 持仓更推翻了两大主流错觉</h2>
<div class="tldr-ribbon">一句话看懂：华尔街正在重演“2001 年电信设备商融资危机”——高杠杆借钱建算力的玩家已经开始流血，但不是 2008 年式系统崩盘。</div>
<p>美联储 11 月《金融稳定报告》首次亮出底牌：美国科技巨头在表外背负了<strong>超过 3 万亿美元</strong>的数据中心租约与算力担保。随着英伟达代理 CEO 宣布收紧对算力新贵的融资担保，压力上周全面外溢至二级市场——算力商 <strong>CoreWeave</strong> 周跌 <strong>-25.6%</strong>（5 年期违约互换破 1,230 基点）、高负债的<strong>甲骨文</strong>周跌 <strong>-19.3%</strong>（新发债被迫付 7.0%–8.65% 利息）、私募巨头 <strong>Blue Owl</strong> 科技基金遭 <strong>39% 集中赎回</strong>（触发 5% 赎回限制），风险更已传染到给私募信贷提供授信的<strong>美国区域银行（<code>KRE</code> 周跌 -5.18%）</strong>。</p>
<p>同时，11 月 20 日最新发布的 CFTC 期货持仓报告直接推翻了市场上流传最广的两个错觉：① <strong>日元大投机客并非拥挤空头，而是重仓净多 +11.6 万手</strong>，所以不会重演 2024 年 8 月那种空头连环爆仓，日本真正的长期冲击是 2.8% 日债吸走美债和法债的险资买盘；② <strong>对冲基金在 10 年期美债上做空已到三年极致（占总持仓近 40%）</strong>，一旦股市出意外，空头被迫平仓反而会引爆美债猛烈上涨（轧空）。</p>

<h2>逻辑四：全球估值出现“世纪级赔率差”——中国资产硬底已成，但必须尊重内需与关税现实</h2>
<div class="tldr-ribbon">一句话看懂：买美股现在只比美债多赚 1.1% 的超额收益，而买沪深 300 比国内国债多出整整 6.8%——但内需和关税决定了中国只能打“哑铃”。</div>

<div class="chart-wrap">
  {svg_erp_chart()}
</div>

<p><strong>为什么说中国资产“往下跌不动了”？</strong>除极高赔率与 1.58% 国债利率倒逼险资“资产荒”入市（险资权益占比已创 <strong>16.26%</strong> 新高）外，11 月 22 日晚监管层祭出<strong>“融资保证金降回 80%（破例覆盖 2.2 万亿存量合约、释约 4,000 亿空间）+ 创业板引入做市商 + 28 亿降费延至 2028 年”三箭齐发</strong>，叠加国家队上周五 243 亿护盘上证 50ETF、港股主板沽空比率飙至 <strong>25.54%</strong> 对撞南向扫货、中金所期指贴水高达 <strong>22%–30%</strong>，以及人民币强势升至 <strong>6.67</strong>，系统性暴跌已被焊死。</p>
<p><strong>为什么又不能指望“单边疯牛”？</strong>11 月高频数据依然冷峻：前 21 天<strong>30 城新房成交同比扩大至 -21.9%</strong>（1% 贴息限总价 150 万仅盘活了低价二手房）；上半月<strong>乘用车零售暴跌 -25%</strong>（新能源渗透率冲破 <strong>73.2%</strong>，燃油车崩塌 -45%）。外部还有美国年底 7 国 301 产能过剩调查与明年 1 月 10 日中美休战到期悬崖。因此，<strong>“60% 免/省税高股息 + 40% 自主可控/硬科技 + 6–7% 严选可转债”</strong>是最贴合现实的致胜阵型。</p>

<h2>逻辑五：2026 年的终极赚钱密码——抛弃拥挤旧故事，跟随聪明钱大轮动</h2>
<div class="tldr-ribbon">一句话看懂：2026 年是 2000 年以来风格切换最剧烈的一年。中美顶级机构的唯一跨界共识，是从拥挤算力转向“AI 企业级存储与先进晶圆”。</div>
<ul>
  <li><strong>美股价值碾压成长 32.7 个百分点：</strong>截至 11 月 20 日，美股大盘价值（<code>IWD</code> 年内总回报 +18.9%）把大盘成长（<code>IWF</code> -13.8%）远远甩在身后，标普等权（<code>RSP</code> +9.6%）完胜市值加权标普（+1.95%）。</li>
  <li><strong>中美巨鲸罕见同向押注存储：</strong>华尔街巨鲸（Tepper 第一重仓<strong>美光 <code>MU</code></strong>、桥水加仓美光翻倍、德鲁肯米勒三倍加仓<strong>希捷 <code>STX</code></strong>）与中国公募/外资 QFII（联手抢筹 7 月上市的<strong>长鑫科技 <code>688825.SH</code></strong> 至主动公募第四、QFII 第一新进），共同押注 AI 企业级存储与先进晶圆——同时坚决切割现货大跌 20% 的<strong>消费级 NAND</strong>。</li>
  <li><strong>避开公募极端拥挤区：</strong>国内主动偏股公募前两大重仓目前依然是<strong>中际旭创（959 亿）与新易盛（871 亿）</strong>，虽有公司大手笔回购，但需防范黄仁勋离任后供应链再平衡的波动；相反，北向资金三季度已将 <strong>673 亿元（+47%）</strong> 重金投向<strong>银行与紫金矿业</strong>，高瓴、李录、段永平三位华人巨鲸则逆着海外悲观情绪齐聚<strong>拼多多（<code>PDD</code>）</strong>。</li>
</ul>

<!-- ==================== PART 3: MARKET DEEP-DIVE ==================== -->
<div class="section-banner">
  <h1>第三部分：近期全球股市到底发生了什么？</h1>
  <div class="section-tag">各市场详细复盘 · 还原事件时间线</div>
</div>

<h2>3.1 美股：从 10 月历史新高到 11 月“五日完美风暴”</h2>
<p>10 月 6 日标普 500（7,819 点）与纳斯达克 100（31,225 点）刚刚同步创下历史新高，短短六周便急转直下，核心是五记重拳接连砸下：</p>
<ol>
  <li><strong>云巨头烧钱烧出负现金流（10 月下旬）：</strong>微软、谷歌、亚马逊、Meta 三季度现金资本开支翻倍至 <strong>2,019 亿美元</strong>，把谷歌（FCF -91 亿）和 Meta 直接烧成负现金流，市场首次强烈质疑 AI 回报周期。</li>
  <li><strong>中期选举“蓝色浪潮”（11 月 3 日）：</strong>民主党同时夺回参议院（56–44）和众议院（~258–173），短暂反弹后迅速引发对 AI 数据中心与电力环保监管收紧的担忧。</li>
  <li><strong>黄仁勋突然辞职 + 堵死离岸云漏洞（11 月 12 日 &amp; 16 日）：</strong>英伟达创始人因涉新加坡算力商 Megaspeed 前高管个人合规调查即刻卸任 CEO 与董事，CFO Colette Kress 代理（特朗普 11.20 喊话“给第二次机会”与财长贝森特公开分歧，并威胁对美企海外建 AI 数据中心征重税）。16 日美商务部正式封堵中资租用东南亚云算力通道。</li>
  <li><strong>英伟达推迟 10-Q + 史上最大 IPO 抽血（11 月 17–19 日）：</strong>英伟达 Q3 营收 <strong>1,158 亿美元（+103%）</strong>却破例推迟提交 10-Q；18 日鹰派美联储纪要点名警示 AI 债务；19 日 <strong>Anthropic（<code>ANT</code>）</strong>完成人类史上最大 IPO（含八大科技巨头私募合计抽血约 <strong>1,195 亿美元</strong>），次日跌回 88.91 美元，引发“循环融资”群嘲。</li>
  <li><strong>SEC 会计调查引爆周五踩踏（11 月 20 日）：</strong>WSJ 与路透证实 SEC 调查英伟达会计及地区营收披露（原占 22% 的新加坡营收口径变更后消失），叠加加州总检察长传票，<strong>英伟达单日暴跌 -14.01% 至 125.53 美元</strong>（6 周腰斩 -48.4%、市值缩水 2.7 万亿），将标普单周砸跌 -8.61%、纳指 100 砸至距熊市仅差 0.16%。</li>
</ol>

<div class="chart-wrap">
  {svg_us_sector_chart()}
</div>

<h3>华尔街 2027 展望与顶级 13F 巨鲸最新动向（2026 年 11 月）</h3>
<table class="compact-tbl">
  <thead>
    <tr>
      <th style="width:18%;">顶级机构 / 巨鲸</th>
      <th style="width:27%;">最新规模 / 2027 标普目标</th>
      <th style="width:28%;">重点买入 / 看好方向</th>
      <th style="width:27%;">重点减持 / 核心提醒</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>伯克希尔 (阿贝尔)</strong></td>
      <td>持有 <strong>$3,523 亿现金</strong> + 单季创纪录 $96 亿回购</td>
      <td>苹果（25%）、安达不动；大加建商 <code>LEN</code>、达美航空</td>
      <td>减持第一资本、美银；用巨额现金严防宏观风险</td>
    </tr>
    <tr>
      <td><strong>桥水 / 德鲁肯米勒</strong></td>
      <td>桥水 $230 亿 / Duquesne 大幅瘦身至 ~65 只</td>
      <td>桥水加仓<strong>新兴市场 <code>IEMG</code>、美光翻倍</strong>；德氏重仓<strong>希捷 + 三大金矿</strong></td>
      <td>桥水砍标普 ETF 与谷歌/英伟达；德氏清仓全部指数看涨期权</td>
    </tr>
    <tr>
      <td><strong>高瓴 / 李录 / 段永平</strong></td>
      <td>HHLR +85% / 喜马拉雅 $38 亿 / H&amp;H $172 亿</td>
      <td><strong>华人巨鲸齐聚拼多多</strong>；高瓴大幅回补阿里；景林猛买台积电</td>
      <td><strong>段永平暴跌前大砍英伟达 -63%</strong> 并清仓阿里</td>
    </tr>
    <tr>
      <td><strong>华尔街大行 2027 共识</strong></td>
      <td>8 家均值 <strong>8,638 点</strong>（高盛/大摩/巴克莱看 8,700）</td>
      <td>高盛“切 A 买 H”看港股 +23%；大摩偏好 A 股；瑞银首选欧元区</td>
      <td>瑞银/富国保守看 8,200、贝莱德推短美债；均警惕 5% 债市竞争</td>
    </tr>
  </tbody>
</table>

<h2>3.2 中国 A 股与港股：上半年狂欢、下半年深蹲，与 11 月 22 日的强托底</h2>
<p>在 2025 年牛市之后，2026 年中资股市走出剧烈的<strong>“倒 V 洗牌”</strong>：上半年半导体暴涨超 105%、两融破 2.6 万亿迫使监管 1 月提高保证金至 100%；10–11 月随全球 AI 杀估值与国内需求转冷回落至年内低位，仅<strong>中证红利（年内 +0.47% / 含息约 +5%）</strong>收正（工商银行 11 月 20 日创 9.40 元历史新高，六大行三季报罕见实现营收净利双正增长与息差企稳）。</p>
<p>把深蹲背后的宏观与财报面纱揭开，能看到三层容易被表面数字误导的真相：</p>
<ul>
  <li><strong>宏观极端撕裂：</strong>10 月出口暴增 <strong>+35.2%</strong>（集成电路 +137%、服务器 +115%）、前 10 月顺差破 <strong>1.043 万亿美元</strong>、PPI 飙至 <strong>+5.7%</strong>；但内需冰封——前 10 月固投 <strong>-8.1%</strong>（地产 -21.6%、卖地 -25.8%），10 月社零表观仅 <strong>+0.4%</strong>（<strong>剔除汽车实为 +2.5%</strong>，价格战拖累超 2 个百分点），10 月实体贷款实际净减 <strong>5,846 亿</strong>（居民缩表 -4,300 亿，被非银贷款 +3,470 亿遮盖了部分表观降幅）。</li>
  <li><strong>财报“错杀”与腾讯现金流冲击：</strong>A 股 Q3 单季盈利表观下滑 -11% 至 -13.9% 纯属券商/保险自营浮亏拖累，<strong>全 A 非金融实业 Q3 实际稳健增长 +9.5%–10.3%</strong>。港股则分化剧烈：腾讯 Q3 AI 资本开支飙增 5 倍至 814 亿，把季度自由现金流砸至 <strong>-691 亿元</strong>，股价跌破 350 港元；阿里云外部收入则暴增 +67%，逆市抗跌。</li>
  <li><strong>社区真实体感与 2027 券商共识：</strong>11 月 22 日晚“三箭齐发”出台后，雪球、股吧、淘股吧并未陷入盲目狂热，而是普遍抱有“防强平及时雨 + 谨防 2023.8.28 高开砸盘”的克制心态。中信、华泰、申万、中金等头部券商一致预期 12 月中央经济工作会议定调明年 GDP 4.5%–5.0%、赤字 ~4.0%、超长期国债 ~1.3 万亿，看好 3,500 点阶段底与 <strong>2027 春季躁动</strong>。</li>
</ul>

<h3 style="margin:8px 0 4px 0;">内地场内 QDII 实时折溢价对照表（截至 2026-11-20 收盘 · 集思录/交易所）</h3>
<table class="compact-tbl" style="break-inside: avoid; margin: 5px 0 8px 0;">
  <thead>
    <tr>
      <th style="width:22%;">代码</th>
      <th style="width:22%;">基金名称</th>
      <th class="num" style="width:15%;">11.20 官方溢价</th>
      <th style="width:41%;">实操判断（一眼避坑、一眼捡漏）</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>159509</code></td>
      <td>纳指科技 ETF（景顺）</td>
      <td class="num badge-neg">+36.84%</td>
      <td><strong>周一早盘停牌！</strong>计入周五暴跌后隐含溢价逼近 <strong>45%–48%</strong>，绝对禁碰</td>
    </tr>
    <tr>
      <td><code>513100</code> / <code>159941</code></td>
      <td>纳指 ETF（国泰 / 广发）</td>
      <td class="num badge-neg">+17.0% / +15.1%</td>
      <td>多只纳指 ETF 周一停牌，隐含溢价 <strong>22%–24%</strong>，极易双杀</td>
    </tr>
    <tr>
      <td><code>513500</code></td>
      <td>标普 500 ETF（博时）</td>
      <td class="num badge-neg">+8.59%</td>
      <td>隐含溢价 ~10%+，严守 &gt;2%–3% 不在场内买的铁律</td>
    </tr>
    <tr>
      <td><code>513530</code> / <code>513950</code></td>
      <td><strong>港股通/恒生红利 ETF（QDII）</strong></td>
      <td class="num badge-pos">-0.76% / -1.02%</td>
      <td><strong>省税利器！</strong>轻度折价 + 合法享 10% 机构税（比港股通省 10–18pp）</td>
    </tr>
    <tr>
      <td><code>513030</code> / <code>513520</code> / <code>513050</code></td>
      <td>德国 / 日经 / 中概互联 ETF</td>
      <td class="num badge-pos">-1.5% / -1.3% / -1.3%</td>
      <td><strong>全线折价！</strong>非美全球分散配置零溢价摩擦（印度 LOF 亦折价）</td>
    </tr>
  </tbody>
</table>

<h2 style="margin:10px 0 6px 0;">3.3 欧、日、韩、台、印股市与大宗加密全景</h2>
<div class="chart-wrap" style="margin:6px 0 8px 0;">
  {svg_global_indices_chart()}
</div>
<p><strong>泛亚洲同步打响“股市保卫战”：</strong>除中国三箭齐发外，<strong>台湾</strong>（单周 -17.5%、台积电破 NT$2,000）宣布周一实施 2015 年来首次平盘下禁空令并提高融券保证金至 150%，国安基金 5,000 亿台币护盘；<strong>韩国</strong>（较 6 月腰斩 -48.1%）周日召开 F4 紧急会议筹备重启 2008 年来首次证券平准基金；<strong>日本</strong>周一休市，高市早苗积极财政与春斗 +5.01% 支撑长逻辑但 12.18 加息在即。<strong>欧洲</strong>则是德国（2,100 亿欧元强军基建）撑底、法国（赤字 5.4%、法德利差 155–176bp、49.3 倒阁风险）承压。<strong>商品与加密端：</strong>现货黄金三日急跌 -$314 至 $3,535（央行 Q3 逆市购金 321 吨）；铜期货熊市但上海洋山现货溢价飙至 ~$500/吨；<strong>比特币</strong>周六爆仓 26 亿美元下探 5.51 万后，周日晚已快速反弹回 <strong>6.1 万美元上方</strong>。</p>

<!-- ==================== PART 4: SCENARIOS & CALENDAR ==================== -->
<div class="page-break"></div>
<div class="section-banner page-start">
  <h1>第四部分：未来三种剧本、七大风险与 50 天日历</h1>
  <div class="section-tag">看清最坏情况 · 提前写好应对预案</div>
</div>

<h2>4.1 2026 年末 – 2027 上半年三种情景推演（悲观概率上调至 30%–32%）</h2>
<table>
  <thead>
    <tr>
      <th style="width:17%;">情景剧本</th>
      <th style="width:32%;">未来怎么演？</th>
      <th style="width:22%;">中美股市大致区间</th>
      <th style="width:29%;">最占优势的配置</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>基准剧本：风暴后软着陆</strong><br><span class="badge-pos">概率 48%–50%</span></td>
      <td>12 月美欧日各加息一次后明年初见顶；霍尔木兹僵持但不彻底断航，布油稳在 78–95 美元；AI 信用局限在局部重组；1.10 中美再延期或小额协议。</td>
      <td><strong>标普：</strong>12 月探底 6,350–6,650 后 2027 修复至 <strong>7,800–8,400</strong>；<br><strong>沪深300 / 恒指：</strong>4,300–4,550 / 25,000–26,500。</td>
      <td>5–10Y TIPS、美股等权/价值与 AI 存储、中证红利 + AA+ 转债 + 国产替代、折价 QDII 红利、黄金/金矿。</td>
    </tr>
    <tr>
      <td><strong>乐观剧本：油价破位、紧缩速止</strong><br><span class="badge-gold">概率 18%–20%</span></td>
      <td>11.29 OPEC+ 谈崩或中东意外停火令布油跌向 65–75 美元；通胀速降使 12 月成“最后一加”且明年 Q2 转降息；英伟达 10-Q 仅涉合规罚款。</td>
      <td><strong>标普：</strong>盈利估值双击冲向 <strong>8,700+</strong>；<br><strong>港股/韩台：</strong>恒指破 27,000，恒生科技与韩台芯片暴力逼空反弹。</td>
      <td>恒生科技（12.7 后）、韩台芯片/<code>MU/AVGO</code>、美股精选成长、印度（油价 &lt;$85）、黄金/金矿。</td>
    </tr>
    <tr>
      <td><strong>悲观剧本：断油 / 信用传染 / 钱荒</strong><br><span class="badge-neg nowrap">概率 30%–32%↑</span></td>
      <td>霍尔木兹封锁推油破 115–120 美元逼美联储更大幅加息；或甲骨文降级/银行信用外溢 + 年末美元回购钱荒；叠加全球 301 关税与 1.10 休战破裂。</td>
      <td><strong>标普：</strong>杀盈利叠杀估值破 <strong>5,900–6,200</strong> 步入全面熊市；<br><strong>中国：</strong>出口熄火压制进攻股，红利与国债显著抗跌。</td>
      <td>短端美债/现金 + <strong>4% 战术 7–10Y 美债（吃轧空）</strong> + 虚值原油/VIX 期权 + 黄金滞胀避险 + 中国国债与纯红利。</td>
    </tr>
  </tbody>
</table>

<h2>4.2 七大尾部风险“红灯监控表”</h2>
<table class="compact-tbl">
  <thead>
    <tr>
      <th style="width:19%;">风险事件</th>
      <th class="ctr" style="width:14%;">时间 / 概率</th>
      <th style="width:41%;">为什么危险？（大白话解读）</th>
      <th style="width:26%;">盯紧这个红灯指标</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>1. 美欧日十日同步加息</strong></td>
      <td class="ctr">12.08–18<br><span class="badge-neg nowrap">高 75%+</span></td>
      <td>跌市无央行托底；库克放出“更大加息”狠话；2.8% 日债抽走美/法债长期险资买盘。</td>
      <td>美联储 2027 点阵图 &gt;4.5%；日债破 3.0%</td>
    </tr>
    <tr>
      <td><strong>2. AI 债务向银行传染</strong></td>
      <td class="ctr">未来半年<br><span class="badge-neg nowrap">高 65%↑</span></td>
      <td>美联储揭露超 3 万亿表外 AI 债务；CoreWeave/甲骨文承压已波及私募赎回与区域银行 <code>KRE</code>。</td>
      <td>IG 利差 &gt;120–130bps；HY &gt;450bps；甲骨文降级</td>
    </tr>
    <tr>
      <td><strong>3. 英伟达 10-Q 与洗牌</strong></td>
      <td class="ctr">11底–12月<br><span class="badge-neg nowrap">高 70%</span></td>
      <td>推迟财报暗藏内控整改风险；后黄仁勋时代分散供应商可能挤压国内光模块份额。</td>
      <td>10-Q 披露措辞；SEC/司法部正式文件</td>
    </tr>
    <tr>
      <td><strong>4. 全球 301 + 1.10 中美崖</strong></td>
      <td class="ctr">年底–1.10<br><span class="badge-gold nowrap">中高 50–55%</span></td>
      <td>美国年底前完成对中/韩/日/欧/印/墨/越 7 国产能过剩调查，叠 1.10 休战到期与海外 DC 重税。</td>
      <td>12 月 USTR 301 终裁；中美“30-for-30”进展</td>
    </tr>
    <tr>
      <td><strong>5. 法国倒阁撞欧央行</strong></td>
      <td class="ctr">11底–12月<br><span class="badge-gold nowrap">中高 50%</span></td>
      <td>总理若用 49.3 条款遭不信任倒阁，恰逢欧央行加息且高门槛拒救，易冲击欧洲银行股。</td>
      <td>10Y 法德利差突破 200 基点</td>
    </tr>
    <tr>
      <td><strong>6. 霍尔木兹袭击升级</strong></td>
      <td class="ctr">随时爆发<br><span class="badge-gold nowrap">中 40–45%↑</span></td>
      <td>11.20–21 连发袭击、海峡运力低战前 65%、战险高达 10%、伊朗拒谈；彻底封锁油破 $120。</td>
      <td>布油连续 5 天站稳 105 美元/桶</td>
    </tr>
    <tr>
      <td><strong>7. 美国年末回购钱荒</strong></td>
      <td class="ctr">11底–12底<br><span class="nowrap">中 35–40%</span></td>
      <td>隔夜逆回购清零、准备金跌破 GDP 10% 红线，年末缴税发债易重演 2019 年 9 月回购飙升。</td>
      <td><code>SOFR−IORB</code> &gt; +20bps；准备金 &lt;$2.85T</td>
    </tr>
  </tbody>
</table>

<h2>4.3 未来 50 天关键日程速查（2026.11.23 – 2027.01.10）</h2>
<table class="compact-tbl" style="break-inside: avoid;">
  <thead>
    <tr>
      <th style="width:17%;">日期</th>
      <th style="width:36%;">大事预告</th>
      <th style="width:47%;">对应操作提醒</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>11.23 (周一)</strong></td>
      <td><strong>日本休市</strong> / 早 7:00 CME 期指 / A 股三箭齐发 / 6–7 只纳指 QDII 停牌 / 台股禁空令生效</td>
      <td>盘面薄、波动大；严禁追高券商与 15–48% 溢价美股 QDII，留意银行短线跷跷板。</td>
    </tr>
    <tr>
      <td><strong>11.24–27</strong></td>
      <td>日本复市（24日）/ <strong>美国 10 月 PCE &amp; GDP（25日）</strong>/ 美感恩节休市（26日）/ 美团财报（27日）</td>
      <td>若 25 日 PCE 未失控，启动<strong>第一步（20%）固收 / TIPS / AA+ 转债 / 红利</strong>部署（0 美股）。</td>
    </tr>
    <tr>
      <td><strong>11.29–30</strong></td>
      <td><strong>OPEC+ 部长会议（29日）</strong>/ <strong>中国 80% 融资保证金生效（30日）</strong>/ 美银 2027 展望</td>
      <td>紧盯布油是否突破 105 美元红线或破位下行释放通缩红利。</td>
    </tr>
    <tr>
      <td><strong>12.04 (周五)</strong></td>
      <td>美国 11 月非农就业 / 盘后<strong>恒生科技 30→50 扩编执行</strong>（12.7 生效）</td>
      <td>避开 12.4 尾盘老牌互联网权重稀释约 40% 的机械卖压，12.7 后择机低吸。</td>
    </tr>
    <tr>
      <td><strong>12.08–18</strong></td>
      <td><strong>美联储（9日）+ 中央经济工作会议（中旬）+ 欧央行（17日）+ 日央行（18日）</strong>+ 英伟达 10-Q + 301 终裁</td>
      <td>全年最密集风暴窗；待 18 日全部落地后，果断启动<strong>第二步（50%）主力建仓</strong>！</td>
    </tr>
    <tr>
      <td><strong>2027.01.03 &amp; 10</strong></td>
      <td>美国民主党新国会履职 / <strong>中美 301 贸易休战到期悬崖</strong></td>
      <td>休战明朗后启动<strong>第三步（30%）收官建仓</strong>；若谈判破裂全面回弹关税则触发红线 ②。</td>
    </tr>
  </tbody>
</table>

<!-- ==================== PART 5: AUDIT & APPENDIX ==================== -->
<div class="section-banner">
  <h1>第五部分：五轮核查是如何帮我们避坑纠偏的？</h1>
  <div class="section-tag">研究透明化 · 8 次改变决策的关键纠偏</div>
</div>

<p>很多听起来“很有道理”的市场共识，一查底层数据就会露馅。在 <strong>5 轮、19 位子代理</strong>的自我推翻与全渠道核验中，我们一共完成了 <strong>26 项关键纠偏</strong>。下面挑出对你的真金白银影响最大的 <strong>8 次核心纠偏</strong>：</p>

<div class="audit-grid">
<div class="audit-card">
  <div class="audit-head"><span class="pill-del">删除+反转</span><span class="audit-title">1. 戳破“日元套息空头崩盘”假象</span></div>
  <div>前三轮我们顺着惯性担忧 12 月日本加息重演 2024 年 8 月日元空头踩踏；第四轮直查 11.20 CFTC 期货持仓才发现，大投机客目前其实是 <strong>+11.6 万手日元净多头</strong>！于是果断删除旧论点，转盯 2.8% 日债触发的险资回流。</div>
</div>

<div class="audit-card">
  <div class="audit-head"><span class="pill-del">删除+推迟</span><span class="audit-title">2. 紧急叫停“11 月底抄底美股”</span></div>
  <div>原计划 11.26 第一批就买美股防御股；第四轮挖出高盛 CTA 反弹市仍要卖 <strong>$286 亿</strong>、做市商负 Gamma 创 2019 年最深，且美国散户仍在 <strong>99% 极值狂买英伟达与杠杆 ETF</strong>，遂果断删除第一批全部美股买单，推迟至 12.18 后。</div>
</div>

<div class="audit-card">
  <div class="audit-head"><span class="pill-del">删除+重构</span><span class="audit-title">3. 拆穿 QDII 误区，挖出省税神器</span></div>
  <div>早期笼统提示内地 QDII 溢价 10%–24%；第四轮逐只拉取 11.20 净值发现：<strong>美股科技 QDII 溢价 15%–48% 极致命，但德/日/印/中概及港股红利 <code>513530</code>(-0.76%)/<code>513950</code>(-1.02%) 全线折价</strong>！直接破解港股通 20–28% 红利税痛点。</div>
</div>

<div class="audit-card">
  <div class="audit-head"><span class="pill-del">删除+上调</span><span class="audit-title">4. 纠正霍尔木兹口径，上调悲观概率</span></div>
  <div>早期误引 9 月底含陆路管道的“运力恢复 80%”；第五轮核对 UKMTO 11 月下旬通报，证实<strong>海峡直航运力仍低战前 65%</strong> 且周末再发遇袭，随即将海峡风险提至 <strong>40%–45%</strong>，悲观情景从 20% 上调至 <strong>30%–32%</strong>。</div>
</div>

<div class="audit-card">
  <div class="audit-head"><span class="pill-mod">战术修正</span><span class="audit-title">5. 解除 10 年期美债一刀切禁令</span></div>
  <div>发现对冲基金在 10Y 美债上的净空头已占总持仓近四成（三年最极端），在继续禁止裸配 30 年长债的同时，为美元本位增配 <strong>4% 战术 7–10Y 美债</strong>，专门防范突发信用危机引发的美债暴力轧空。</div>
</div>

<div class="audit-card">
  <div class="audit-head"><span class="pill-mod">算术修复</span><span class="audit-title">6. 修复美股错配与沪深 300 估值倒置</span></div>
  <div>第二轮抓出第一轮混用 11.13 与 11.20 收盘数据导致的算术冲突，对齐后加权还原标普误差仅 <strong>0.11%</strong>；同时纠正把沪深 300“比历史 68% 便宜”倒写成“68% 偏贵分位”的错误，还原真实 <strong>32%–33% 低位</strong>。</div>
</div>

<div class="audit-card">
  <div class="audit-head"><span class="pill-add">全新升级</span><span class="audit-title">7. 补全三箭齐发、准备金与转债排雷</span></div>
  <div>将单一降保证金补全为“80% 含存量 + 创业板做市商 + 28 亿降费”共振韩台稳市；新增<strong>美国准备金跌破 GDP 10% 红线</strong>监测；新增 6%–7% AA+ 可转债，并用<strong><code>侨银转债</code> 72 小时惊魂</strong>打破低价转债刚兑幻想。</div>
</div>

<div class="audit-card">
  <div class="audit-head"><span class="pill-mod">事实还原</span><span class="audit-title">8. 厘清关税法源、南向断点与 Q3 真相</span></div>
  <div>核实最高法院 2 月已废止 IEEPA 芬太尼税，现行对华税源为 <strong>301+232（实征 24.3%）</strong>；还原南向 34 连月纪录早在今年 5 月终结；拆解出 A 股 Q3 <strong>非金融实业单季实增 +9.5%–10.3%</strong>，并非全面失速。</div>
</div>
</div>

<!-- ==================== APPENDIX ==================== -->
<div class="page-break"></div>
<div class="section-banner page-start">
  <h1>附录：全渠道实时数据速查总表</h1>
  <div class="section-tag">截至 2026 年 11 月 22 日深夜 · 备查底表</div>
</div>

<h2 style="margin:8px 0 5px 0;">附表 A：全球主要股指与核心板块精准表现（截至 2026-11-20 收盘）</h2>
<table class="appendix-tbl">
  <thead>
    <tr>
      <th style="width:30%;">市场 / 指数</th>
      <th class="num" style="width:16%;">11.20 收盘</th>
      <th class="num" style="width:14%;">上周（11.13–20）</th>
      <th class="num" style="width:16%;">2026 年内（YTD）</th>
      <th style="width:24%;">一句话备注</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>标普 500 / 纳指 100</strong></td>
      <td class="num">6,910 / 25,029</td>
      <td class="num badge-neg">-8.61% / -10.43%</td>
      <td class="num">+0.95% / -0.87%</td>
      <td>前瞻 PE ~16.5x；纳指距熊市差 0.16%</td>
    </tr>
    <tr>
      <td><strong>罗素价值 (IWD) / 成长 (IWF)</strong></td>
      <td class="num">$247.4 / $101.7</td>
      <td class="num">-6.0% / -11.5%</td>
      <td class="num"><strong>+18.9% / -13.8%</strong></td>
      <td>总回报差 32.7pp（2000 来最剧烈）</td>
    </tr>
    <tr>
      <td><strong>等权标普 (RSP) / 必选 (XLP) / 医疗 (XLV)</strong></td>
      <td class="num">$207 / $90.5 / $177</td>
      <td class="num">-6.2% / -2.0% / -6.0%</td>
      <td class="num badge-pos">+9.6% / +18.7% / +16.1%</td>
      <td>XLP 暴跌周五逆市收涨 +0.72%</td>
    </tr>
    <tr>
      <td><strong>能源 (XLE) / 科技 (XLK) / 通信 (XLC)</strong></td>
      <td class="num">$60.5 / $149 / $100</td>
      <td class="num">-6.9% / -12.5% / -8.0%</td>
      <td class="num">+38.0% / +3.9% / -14.2%</td>
      <td>能源全年冠军，通信服务垫底</td>
    </tr>
    <tr>
      <td><strong>上证 / 沪深 300 / 中证红利</strong></td>
      <td class="num">3,534 / 3,955 / 5,530</td>
      <td class="num">-2.8% / -1.6% / 稳</td>
      <td class="num">-11.0% / -14.6% / <span class="badge-pos">+0.47%</span></td>
      <td>中证红利含息 ~+5%，A 股唯一收正</td>
    </tr>
    <tr>
      <td><strong>创业板 / 科创 50 / 中证 1000</strong></td>
      <td class="num">2,212 / 1,231 / 5,649</td>
      <td class="num badge-neg">-8.8% / -3.8% / 重挫</td>
      <td class="num badge-neg">-30.9% / -8.4% / -25.6%</td>
      <td>创业板估值落入近 10 年 2%–5% 谷底</td>
    </tr>
    <tr>
      <td><strong>恒生指数 / 恒生科技</strong></td>
      <td class="num">22,411 / 3,511</td>
      <td class="num badge-neg">-5.19% / -7.92%</td>
      <td class="num badge-neg">-12.56% / -36.35%</td>
      <td>主板沽空 25.54%；AH 溢价 137.68</td>
    </tr>
    <tr>
      <td><strong>台湾加权 / 韩国 KOSPI / 日经 225</strong></td>
      <td class="num">36,033 / 4,870 / 56,437</td>
      <td class="num badge-neg">-17.5% / 熔断 / 重挫</td>
      <td class="num badge-pos">+24.4% / +15.6% / +12.1%</td>
      <td>台/韩启动禁空与平准基金救市</td>
    </tr>
    <tr>
      <td><strong>欧 STOXX 600 / 德 DAX / 法 CAC / 印 Nifty</strong></td>
      <td class="num">626 / 24,803 / 7,928 / 25,801</td>
      <td class="num">-5.8% / -7.3% / -5.3% / 涨</td>
      <td class="num">+5.7% / +1.3% / -2.7% / -1.3%</td>
      <td>德强军 vs 法债危 vs 印度油价软肋</td>
    </tr>
  </tbody>
</table>

<h2 style="margin:10px 0 5px 0;">附表 B：宏观利率、金融管道、大宗与实时加密总表（截至 2026-11-22 深夜）</h2>
<table class="appendix-tbl">
  <thead>
    <tr>
      <th style="width:19%;">类别</th>
      <th style="width:31%;">核心指标</th>
      <th style="width:26%;">最新精确水平</th>
      <th style="width:24%;">一句话解读</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>主要央行利率</strong></td>
      <td>美联储 / 欧央行 / 日央行 / 中国隔夜 (LPR)</td>
      <td>3.75–4.00% / 2.50% / 1.25% / 1.25% (3.0/3.5%)</td>
      <td>12.8–18 美欧日同步加息；中国独宽</td>
    </tr>
    <tr>
      <td><strong>美国国债与现金</strong></td>
      <td>3M / 2Y / 10Y / 30Y / <strong>10Y TIPS 实际利率</strong></td>
      <td>4.32% / 4.63% / <strong>4.92%</strong> / 5.31% / <strong>~2.90–2.95%</strong></td>
      <td>5–10Y TIPS 攻守兼备；货基 3.76–3.95%</td>
    </tr>
    <tr>
      <td><strong>欧日中 10Y 国债</strong></td>
      <td>德 Bund / 法 OAT / 日 JGB / 中国 CGB (30Y)</td>
      <td>3.30% / 4.87% / <strong>2.75–2.79%</strong> / <strong>1.58%</strong> (2.04%)</td>
      <td>法德利差 155bp；中债独降引发资产荒</td>
    </tr>
    <tr>
      <td><strong>美国流动性管道</strong></td>
      <td>ON RRP / TGA / 银行准备金 / SOFR vs IORB</td>
      <td><strong>$4.01 亿</strong> / $8,912 亿 / <strong>9.03% GDP</strong> / 3.91% vs 3.90%</td>
      <td>缓冲垫清空，准备金跌破 10% 红线</td>
    </tr>
    <tr>
      <td><strong>信用与恐慌指标</strong></td>
      <td>VIX / HY OAS / IG OAS / CRWV &amp; ORCL CDS</td>
      <td><strong>35.89 (高40.03)</strong> / 352bp / 94bp / <strong>&gt;1,230 &amp; 320bp</strong></td>
      <td>AI 债务裂缝已外溢至区域银行 KRE</td>
    </tr>
    <tr>
      <td><strong>中国 11 月高频</strong></td>
      <td>30 城新房 / 乘用车零售 / 可转债中位数</td>
      <td><strong>-21.9% YoY</strong> / <strong>-25% (NEV 73.2%)</strong> / <strong>119.44 元</strong></td>
      <td>内需仍冷；转债溢价率跌至 2017 年级低位</td>
    </tr>
    <tr>
      <td><strong>大宗、汇率与加密</strong></td>
      <td>黄金 / 布油 / 铜 / 美元 / 人民币 / <strong>实时 BTC</strong></td>
      <td><strong>$3,535</strong> / <strong>$92.57</strong> / $5.44 / 103.81 / <strong>6.675</strong> / <strong>~$61,000</strong></td>
      <td>金三日急跌洗盘；人民币最强；BTC 止跌</td>
    </tr>
  </tbody>
</table>

<p class="small-note"><strong>权威信源汇总：</strong>美联储（FOMC / H.4.1 / 2026.11 金融稳定报告 / NY Fed）、美国财政部、BEA、BLS、USTR、白宫、SEC EDGAR（Q3 2026 13F）、CFTC（11.20 COT）、Cboe、UKMTO/JMIC、ECB、BOJ、OPEC、中国国家统计局/财政部/央行/海关总署/金融监管总局、沪深北交易所与中登公司、港交所/香港证监会/恒生指数公司、FactSet、BofA FMS、Goldman CTA、Nomura、Vanda Research、TrendForce、乘联会、集思录、Wind/ChinaBond，以及 Reddit/X/Stocktwits/Substack、雪球/淘股吧/财联社与国内外主流投行券商 2027 年度报告。</p>
"""

FULL_HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<title>2026 年 11 月全球股市深度复盘与投资指南（舒朗精读版）</title>
<style>{COMMON_CSS}</style>
</head>
<body>
{COVER_HTML_BLOCK}
{BODY_HTML_BLOCK}
</body>
</html>
"""

COVER_ONLY_HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<style>{COMMON_CSS}</style>
</head>
<body>
{COVER_HTML_BLOCK}
</body>
</html>
"""


def main():
    assert "**" not in FULL_HTML, "Found raw markdown ** in HTML!"
    assert "`" not in FULL_HTML, "Found raw markdown backtick in HTML!"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(FULL_HTML, encoding="utf-8")
    cover_html_path = OUT_DIR / "_tmp_cover.html"
    cover_html_path.write_text(COVER_ONLY_HTML, encoding="utf-8")
    cover_pdf_path = OUT_DIR / "_tmp_cover.pdf"
    full_pdf_path = OUT_DIR / "_tmp_full.pdf"

    header_html = """
    <div style="width:100%; font-family:'PingFang SC','Hiragino Sans GB',sans-serif; font-size:7.6pt; color:#64748B; padding:0 16mm; display:flex; justify-content:space-between; border-bottom:0.5px solid #E2E8F0; padding-bottom:3.5px;">
      <span>2026 年 11 月全球股市深度复盘与投资指南（五轮全渠道定稿）</span>
      <span>结论先行 · 重点论据先行 · 截至 2026-11-22 深夜</span>
    </div>
    """
    footer_html = """
    <div style="width:100%; font-family:'PingFang SC','Hiragino Sans GB',sans-serif; font-size:7.6pt; color:#64748B; padding:0 16mm; display:flex; justify-content:space-between; border-top:0.5px solid #E2E8F0; padding-top:3.5px;">
      <span>仅供参考，不构成个性化投资承诺 · 5 轮 19 位全渠道子代理核验</span>
      <span>第 <span class="pageNumber"></span> 页 / 共 <span class="totalPages"></span> 页</span>
    </div>
    """

    with sync_playwright() as p:
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        launch_kwargs = {"headless": True}
        if os.path.exists(chrome_path):
            launch_kwargs["executable_path"] = chrome_path
        browser = p.chromium.launch(**launch_kwargs)

        page1 = browser.new_page()
        page1.goto(cover_html_path.as_uri(), wait_until="networkidle")
        page1.pdf(
            path=str(cover_pdf_path),
            format="A4",
            print_background=True,
            display_header_footer=False,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            prefer_css_page_size=True,
        )

        page_all = browser.new_page()
        page_all.goto(HTML_PATH.as_uri(), wait_until="networkidle")
        page_all.pdf(
            path=str(full_pdf_path),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template=header_html,
            footer_template=footer_html,
            margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
            prefer_css_page_size=True,
        )
        browser.close()

    doc_cover = fitz.open(cover_pdf_path)
    doc_full = fitz.open(full_pdf_path)
    merged = fitz.open()
    merged.insert_pdf(doc_cover, from_page=0, to_page=0)
    merged.insert_pdf(doc_full, from_page=1, to_page=len(doc_full) - 1)
    merged.save(str(PDF_PATH), deflate=True, garbage=4)
    total_pages = len(merged)
    merged.close()
    doc_cover.close()
    doc_full.close()

    for tmp in (cover_html_path, cover_pdf_path, full_pdf_path):
        if tmp.exists():
            tmp.unlink()

    print(f"Generated readable editorial PDF: {PDF_PATH} ({PDF_PATH.stat().st_size:,} bytes, {total_pages} pages)")


if __name__ == "__main__":
    main()
