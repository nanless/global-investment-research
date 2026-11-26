#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the US Equity Cross-Cycle Handbook PDF — Plain-Language Magazine Edition.
Features:
  - 7 novice-friendly Vector SVG charts (U1-U7 full nested JSON override support, dynamic spx_200d /
    spx_high / us10y / stock_pool_count, CCC ~18% & 12/12 13:00 CST fixes, unified-scale U6 bars,
    collision-free U7 19-group quadrant with dynamic US10Y parity line)
  - Automatic sequential chart numbering ({{CHART_NUM}}) so daily & flagship never skip numbers
  - Shared pdf_common engine (SkPDF emoji guard, embedded pre-render redline linter, atomic _latest sync)
"""

from __future__ import annotations

import html as html_mod
import json
import re
import sys
from pathlib import Path

from pdf_common import (
    BASE_DIR,
    DAILY_DIR,
    atomic_copy,
    build_theme_css,
    clean_svg_text,
    freeze_equity_inputs,
    norm_chart_title as _norm_chart_title,
    render_cover_banner,
    render_docx_atomic,
    render_md_body,
    render_pdf_atomic,
    resolve_chrome_bin,
    run_lint_gate,
    svg_shape,
    write_equity_receipt,
)

OUT_DIR = BASE_DIR
META_PATH = OUT_DIR / "report_meta_us_stock.json"
HTML_PDF_PATH = OUT_DIR / "us_stock_print.tmp.html"
TMP_PDF_PATH = OUT_DIR / "us_stock_print.tmp.pdf"

DEFAULT_U_SECTORS = [
    {"name": "科技 (XLK)", "pct": 8.97, "dd": -19.9, "camp": "hot"},
    {"name": "可选消费 (XLY)", "pct": 3.97, "dd": -6.4, "camp": "base"},
    {"name": "工业电力 (XLI)", "pct": 3.90, "dd": -13.4, "camp": "hot"},
    {"name": "通信服务 (XLC)", "pct": 3.57, "dd": -14.2, "camp": "hot"},
    {"name": "原材料 (XLB)", "pct": 3.23, "dd": -8.4, "camp": "base"},
    {"name": "金融 (XLF)", "pct": 1.98, "dd": -7.1, "camp": "def"},
    {"name": "公用事业 (XLU)", "pct": 1.48, "dd": -9.7, "camp": "base"},
    {"name": "医疗健康 (XLV)", "pct": 1.23, "dd": -6.7, "camp": "def"},
    {"name": "房地产 (XLRE)", "pct": 1.04, "dd": -7.4, "camp": "base"},
    {"name": "必选消费 (XLP)", "pct": -0.09, "dd": -3.3, "camp": "avoid"},
    {"name": "能源 (XLE)", "pct": -1.06, "dd": -14.6, "camp": "def"},
]

DEFAULT_U3_CALM = [
    ("大银行之间借钱是否顺畅？", "非常顺畅 (+0.01%)", "传统银行体系没出事，美联储暂不急着降息救市"),
    ("优质大企业发债贵不贵？", "基本正常 (+0.9%)", "好公司借钱成本可控，未现 2008 式全面金融危机"),
    ("大盘债券违约保险指数", "偏稳 (60–65点)", "超过 80 点才会逼美联储转向，目前尚未触线"),
    ("广义高收益债平均水平", "表面尚可 (+3.5%)", "大盘均值看似平稳，但最底层企业其实已亮红灯"),
]

DEFAULT_U3_CRACKS = [
    ("最弱企业借钱利息（CCC 级）", "冲向 18%（爆表）", "较国债加价扩至 13.5%–14.0%，创 2020 年来最差"),
    ("借钱买显卡的科尔韦夫", "违约险破 1,232 点", "背 470 亿美元债，债主已按高违约风险打 8 折甩卖"),
    ("甲骨文（ORCL）AI 基建债", "违约险逼近 328 点", "新墨西哥机房发不可抗力，长债破 8%、贷款打九折"),
    ("私募影子银行赎回挤兑", "Blue Owl 遭 39% 挤兑", "触发季度 5% 赎回上限，北京 12/02 12:59 黑石迎大考"),
    ("美联储隔夜逆回购池", "仅剩 3.01 亿美元", "11/30 晚 2,180 亿美债交割抽血时缓冲垫消失"),
    ("美国比特币基金流向", "11 月流出 47.1 亿", "11/23 连流 5 日创单月纪录，11/24 链上估算再撤 6.14 亿"),
]

DEFAULT_U4_CARDS = [
    {
        "header": "11/25–11/28（感恩节周）",
        "color": "#ea580c",
        "bg": "#fff7ed",
        "border": "#fb923c",
        "items": [
            ("• 11/23 CMS 药价已提前落地", "#047857", True),
            ("• 11/25 21:30 美国核心通胀PCE", "#9a3412", True),
            ("• 11/26 休市 / 11/27 股债半日", "#7c2d12", False),
            ("• 防薄盘洗盘与戴尔盘后消化", "#7c2d12", False),
        ],
    },
    {
        "header": "11/30–12/12（抽血 + 加息）",
        "color": "#dc2626",
        "bg": "#fef2f2",
        "border": "#f87171",
        "items": [
            ("• 11/30 晚 2,180 亿美债交割", "#991b1b", True),
            ("• 12/01–04 英伟达听证+10-Q/黑石", "#7f1d1d", True),
            ("• 12/10 03:00 沃什联储加息大考", "#991b1b", True),
            ("• 12/12 13:00 美国政府停摆大限", "#991b1b", True),
        ],
    },
    {
        "header": "12/14–12/19（最后暴风眼）",
        "color": "#991b1b",
        "bg": "#fef2f2",
        "border": "#b91c1c",
        "items": [
            ("• 企业财报前回购暂停（买盘断）", "#7f1d1d", True),
            ("• 12/17 欧央行 & 英央行议息", "#7f1d1d", False),
            ("• 12/18 日本央行 2026 第 3 次加息", "#991b1b", True),
            ("• 12/19 05:00 四巫日衍生品大交割", "#7f1d1d", False),
        ],
    },
    {
        "header": "12/21–01中（● 主力进场）",
        "color": "#047857",
        "bg": "#dcfce7",
        "border": "#009E73",
        "items": [
            ("• 12/21–23 解除科技锁，加 2 成", "#14532d", True),
            ("• 避开 12/25 圣诞休市", "#166534", False),
            ("• 优选微软/博通/台积电/电力网", "#14532d", False),
            ("→ 1 月中旬收官加满约 6 成美股", "#065f46", True),
        ],
    },
]

DEFAULT_U5_BANKS = [
    ("美国银行 BofA（全街最谨慎·12个月）", 7800, "#D55E00"),
    ("加拿大皇家银行 RBC（11月下修·12个月）", 8050, "#ea580c"),
    ("富国银行 WFC（2027年底目标）", 8200, "#d97706"),
    ("瑞银财富管理 UBS GWM（2027年底目标）", 8200, "#d97706"),
    ("摩根大通私人银行（2027年底中值）", 8600, "#0072B2"),
    ("巴克莱 Barclays（2027年底目标）", 8700, "#009E73"),
    ("高盛 Goldman Sachs（2027年底目标）", 8700, "#009E73"),
    ("摩根士丹利 MS（2027年底目标）", 8700, "#009E73"),
    ("瑞银投行 UBS IB（主流最高·2027年底）", 8900, "#15803d"),
]

DEFAULT_U7_POINTS = [
    ("美光 MU(周期顶3x)",       78, 224, "y", "#D97706",  8,   4, "start"),
    ("纽蒙特金矿 NEM(红灯观)", 114, 194, "y", "#D97706",  8,   4, "start"),
    ("高盛/美银 11x",          116,  72, "g", "#009E73",  8,   3, "start"),
    ("英伟达 NVDA(10x/听证)",  152, 234, "y", "#D97706",  8,   4, "start"),
    ("雪佛龙/埃克森 13x",      162, 102, "g", "#009E73",  8,   4, "start"),
    ("摩根大通 JPM 13x",       196, 134, "g", "#009E73",  8,   4, "start"),
    ("联合健康(CRUSH规)",       224, 198, "y", "#D97706",  8,   4, "start"),
    ("台积电 TSM 15x",         254,  80, "b", "#0072B2",  8,   4, "start"),
    ("洛马 LMT/艾伯维 17x",     276, 114, "g", "#009E73",  8,   4, "start"),
    ("伯克希尔(扣现金~17x)",   294,  62, "g", "#009E73",  0, -10, "middle"),
    ("黑石 BX(12/02赎回考)",   316, 224, "y", "#D97706",  8,   4, "start"),
    ("博通/泛林 18x",          324, 146, "b", "#0072B2",  8,   4, "start"),
    ("谷歌/服务现在 19x",      356,  86, "b", "#0072B2",  8,   4, "start"),
    ("微软 MSFT 24x",          442, 104, "b", "#0072B2",  8,   4, "start"),
    ("礼来 LLY 28x(27E)",      512,  76, "b", "#0072B2",  8,   4, "start"),
    ("核电电力 VST/GEV",       556, 128, "b", "#0072B2",  8,   4, "start"),
    ("甲骨文/科尔韦夫(债75美分)", 502, 232, "r", "#D55E00",  8,   4, "start"),
    ("苹果 AAPL 34x",          592, 194, "r", "#D55E00",  0,  15, "middle"),
    ("沃尔玛 WMT 42x",         688, 212, "r", "#D55E00",  0, -10, "middle"),
    ("微策略/Coinbase",        702, 246, "r", "#D55E00", -8,   4, "end"),
    ("好市多/CrowdStrike",     796, 196, "r", "#D55E00", -8, -10, "end"),
]


def load_meta(meta_override: dict | None = None) -> dict:
    if meta_override:
        return meta_override
    if META_PATH.exists():
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    return {}


def resolve_flagship_paths(meta: dict) -> tuple[Path, Path]:
    slug = str(meta.get("period_slug", "2026_11")).strip() or "2026_11"
    return OUT_DIR / f"us_stock_market_report_{slug}.md", OUT_DIR / f"us_stock_market_report_{slug}.pdf"


def svg_chart_u1_crises_and_mas(meta_override: dict | None = None) -> str:
    """Chart U1: 1987-2026 Seven Crises Rebound History + Clean 6-Milestone SPX Ladder (Full u1 Override)"""
    cl = load_meta(meta_override).get("chart_live", {})
    u1_nest = cl.get("u1") if isinstance(cl.get("u1"), dict) else {}
    spx_now = int(round(float(cl.get("spx", 7201))))
    spx_200d = int(round(float(cl.get("spx_200d", 7348))))
    spx_high = int(round(float(cl.get("spx_high", 7819))))
    as_full = html_mod.escape(clean_svg_text(str(cl.get("as_of_full", "2026-11-25 13:30 北京时间"))))
    cur_lbl = html_mod.escape(clean_svg_text(str(u1_nest.get("cur_lbl") or cl.get("u1_cur_lbl") or "11/24 官方收盘")))
    cur_note = html_mod.escape(clean_svg_text(str(u1_nest.get("cur_note") or cl.get("u1_cur_note") or "反弹 +4.7%，仍压在年线下")))
    diff_200d = ((spx_now - spx_200d) / float(spx_200d)) * 100.0
    cur_dd = ((spx_now - spx_high) / float(spx_high)) * 100.0
    crises = [
        ("1987 闪崩",   -33.5, 22.8),
        ("2000 互联网", -49.2, 33.1),
        ("2008 金融危", -56.8, 68.6),
        ("2018 加息坑", -19.8, 37.1),
        ("2020 疫情坑", -33.9, 74.8),
        ("2022 加息熊", -25.4, 21.6),
        ("本轮最大回撤", -11.6, 0.0),
    ]
    x0 = 232
    left = f'<line x1="{x0}" y1="38" x2="{x0}" y2="262" stroke="#334155" stroke-width="1.2"/>'
    for i, (nm, dd, r12) in enumerate(crises):
        y = 46 + i * 30.5
        w_dd = round((abs(dd) / 65.0) * 102, 1)
        left += f'<text x="78" y="{y+12.5}" text-anchor="end" font-size="9.0" fill="#1e293b" font-weight="600">{nm}</text>'
        left += f'<rect x="{x0-w_dd}" y="{y+2}" width="{w_dd}" height="15" fill="#D55E00" opacity="0.86" rx="2.5"/>'
        left += f'<text x="{x0-w_dd-4}" y="{y+12.5}" text-anchor="end" font-size="9.0" fill="#b91c1c" font-weight="700">{dd:.1f}%</text>'
        if r12 > 0:
            w_r = round((r12 / 80.0) * 148, 1)
            left += f'<rect x="{x0}" y="{y+2}" width="{w_r}" height="15" fill="#009E73" opacity="0.86" rx="2.5"/>'
            left += f'<text x="{x0+w_r+4}" y="{y+12.5}" font-size="9.0" fill="#047857" font-weight="700">+{r12:.1f}%</text>'
        else:
            left += f'<text x="{x0+6}" y="{y+12.5}" font-size="9.0" fill="#b45309" font-weight="700">反弹后距高 {cur_dd:.1f}% · 科技仍打8折</text>'

    ma_note = f"头顶强压力（仍低 {abs(diff_200d):.1f}%）" if diff_200d < 0 else f"已站上（高 {diff_200d:.1f}%）"
    cur_col = "#009E73" if diff_200d >= 0 else "#0072B2"
    cur_bg = "#ecfdf5" if diff_200d >= 0 else "#eff6ff"
    default_levels = [
        ("10 月历史高点",         spx_high, "#64748b", "#f8fafc", "本轮回调起点"),
        ("1 年平均成本线 (年线)",  spx_200d, "#D55E00", "#fef2f2", ma_note),
        (cur_lbl,                 spx_now,  cur_col,   cur_bg,    cur_note),
        ("11/20 暴跌低点",        6910,     "#475569", "#f8fafc", "连跌 7 天砸出的短线坑"),
        ("华尔街“救市痛点线”",     6845,     "#b91c1c", "#fef2f2", "跌破此处，美联储压力骤增"),
        ("极端打折加速买点",       6350,     "#0284c7", "#f0f9ff", "跌到这且恐慌爆表可大举捡便宜"),
    ]
    levels = u1_nest.get("levels") or default_levels
    right = ""
    for i, item in enumerate(levels[:6]):
        lbl, pt, col, bg, note = item[0], int(item[1]), item[2], item[3], item[4]
        y = 46 + i * 35.5
        is_hi = pt in (spx_200d, spx_now, 6845)
        right += f'<rect x="448" y="{y}" width="388" height="29" fill="{bg}" stroke="{col}" stroke-width="{"1.3" if is_hi else "0.7"}" rx="4"/>'
        right += f'<text x="456" y="{y+18}" font-size="9.2" fill="#0f172a" font-weight="{"800" if is_hi else "600"}">{html_mod.escape(clean_svg_text(str(lbl)))}</text>'
        right += f'<text x="630" y="{y+18}" text-anchor="end" font-size="10.0" fill="{col}" font-weight="800">{pt:,}</text>'
        right += f'<text x="640" y="{y+18}" font-size="9.0" fill="#475569">{html_mod.escape(clean_svg_text(str(note)))}</text>'

    title_u1 = _norm_chart_title(
        u1_nest.get("title") or cl.get("u1_title")
        or "历史证明美股大跌后 1 年全都大涨，但眼下还没站回“1 年平均成本线”"
    )
    sub_u1 = html_mod.escape(clean_svg_text(str(
        u1_nest.get("sub") or cl.get("u1_sub")
        or "左：过去 40 年 7 次大危机最大跌幅 vs 见底后 1 年涨幅 ｜ 右：标普 500 你只需盯住这 6 个关键点位"
    )))
    takeaway_u1 = html_mod.escape(clean_svg_text(str(
        u1_nest.get("takeaway") or cl.get("u1_takeaway")
        or f"历史告诉我们美股跌深了都是未来的黄金坑（每次见底后一年最少涨 +21%），但眼下标普仍在 1 年平均成本线（{spx_200d:,} 点）之下，现在追高容易挨回马枪，耐心等 12 月风浪过关再买更稳。"
    )))
    note_u1 = html_mod.escape(clean_svg_text(str(
        u1_nest.get("note") or cl.get("u1_note")
        or f"数据口径：标普道琼斯指数公司历史日线与最新官方收盘，截至 {as_full}。"
    )))

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_u1}</div>
      <div class="chart-sub">{sub_u1}</div>
      <svg viewBox="0 0 850 274" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="274" fill="#ffffff" rx="6"/>
        <text x="14" y="23" font-size="10.0" fill="#0f172a" font-weight="700">A. 历次危机最大跌幅（左橙红） vs 触底后 1 年回报（右青绿）</text>
        <text x="448" y="23" font-size="10.0" fill="#0f172a" font-weight="700">B. 标普 500 关键点位地图（从高到低）</text>
        <line x1="436" y1="10" x2="436" y2="264" stroke="#e2e8f0" stroke-width="1.2"/>
        {left}
        {right}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway_u1}</div>
      <div class="chart-note">{note_u1}</div>
    </div>
    '''


def svg_chart_u2_storm_timeline(meta_override: dict | None = None) -> str:
    """Chart U2: Oct Peak -> Nov Storm -> Rebound Timeline (Full u2 Override & Accurate 10-Q Label)"""
    cl = load_meta(meta_override).get("chart_live", {})
    u2_nest = cl.get("u2") if isinstance(cl.get("u2"), dict) else {}
    spx_now = int(round(float(cl.get("spx", 7201))))
    spx_200d = int(round(float(cl.get("spx_200d", 7348))))
    spx_high = int(round(float(cl.get("spx_high", 7819))))
    as_full = html_mod.escape(clean_svg_text(str(cl.get("as_of_full", "2026-11-25 13:30 北京时间"))))
    last_lbl = html_mod.escape(clean_svg_text(str(u2_nest.get("last_lbl") or cl.get("u2_last_lbl") or "11/24 回落")))
    zone_lbl = html_mod.escape(clean_svg_text(str(u2_nest.get("zone_label") or cl.get("u2_zone_label") or "11/24–25 震荡筑底")))
    diff_200d = ((spx_now - spx_200d) / float(spx_200d)) * 100.0
    cur_dd = ((spx_now - spx_high) / float(spx_high)) * 100.0
    default_steps = [
        ("10/06 高点", 72,  spx_high, "美股创新高\n科技股狂热"),
        ("10 月底",   170,  7580,     "四大云厂烧钱\n自由现金转负"),
        ("11/03 选举", 268, 7510,     "担心 AI 迎\n更严格监管"),
        ("11/12 震荡", 366, 7420,     "英伟达人事\n与芯片封锁"),
        ("11/17 警报", 464, 7280,     "英伟达延交 10-Q\n美联储放鹰"),
        ("11/19 抽血", 564, 7176,     "安思罗匹克上市\n募资超千亿"),
        ("11/20 大跌", 666, 6910,     "连跌 7 天\n恐慌指数飙升"),
        (last_lbl,    778,  spx_now,  "CEO 回归反弹\n但仍压在年线下"),
    ]
    steps = u2_nest.get("steps") or default_steps

    def y_s(val: float) -> float:
        clamped = max(6750, min(7930, val))
        return round(246 - ((clamped - 6750) / 1180.0) * 204, 1)

    grid = ""
    for v in [6800, 7000, 7200, 7400, 7600, 7800]:
        y = y_s(v)
        grid += f'<line x1="56" y1="{y}" x2="830" y2="{y}" stroke="#f1f5f9" stroke-width="1"/>'
        grid += f'<text x="50" y="{y+4}" text-anchor="end" font-size="9.6" fill="#64748b">{v:,}</text>'

    poly = " ".join(f"{s[1]},{y_s(float(s[2]))}" for s in steps)
    y_200d = y_s(spx_200d)
    y_6845 = y_s(6845)

    nodes = ""
    for idx, item in enumerate(steps):
        tm, x, p, desc = str(item[0]), float(item[1]), int(item[2]), str(item[3])
        y = y_s(p)
        col = "#0072B2" if idx in (0, len(steps) - 1) else "#D55E00"
        nodes += f'<circle cx="{x}" cy="{y}" r="4.2" fill="{col}"/>'
        nodes += f'<text x="{x}" y="264" text-anchor="middle" font-size="9.0" fill="#334155" font-weight="600">{html_mod.escape(clean_svg_text(tm))}</text>'
        if idx == 4:
            yl = y + 16
        elif idx == len(steps) - 1:
            yl = y + 16 if abs(y - y_200d) < 28 else y - 10
        else:
            yl = y - 10
        nodes += f'<text x="{x}" y="{yl}" text-anchor="middle" font-size="9.4" fill="{col}" font-weight="700">{p:,}</text>'
        for li, dl in enumerate(desc.split("\n")):
            nodes += f'<text x="{x}" y="{278 + li*12}" text-anchor="middle" font-size="9.0" fill="#475569">{html_mod.escape(clean_svg_text(dl))}</text>'

    pos_lbl = f"现低 {abs(diff_200d):.1f}%" if diff_200d < 0 else f"现高 {diff_200d:.1f}%"
    title_u2 = _norm_chart_title(
        u2_nest.get("title") or cl.get("u2_title")
        or f"从 10 月见顶跌到 11/24 芯片重挫，标普 500 仍差 {abs(diff_200d):.1f}% 才站回年线"
    )
    sub_u2 = html_mod.escape(clean_svg_text(str(
        u2_nest.get("sub") or cl.get("u2_sub")
        or f"2026 年 10 月 6 日至 11 月 23 日标普 500 关键事件演进（纵轴自 6,750 起；本轮最大回撤 -11.6%，反弹后距高点 {cur_dd:.1f}%）"
    )))
    takeaway_u2 = html_mod.escape(clean_svg_text(str(
        u2_nest.get("takeaway") or cl.get("u2_takeaway")
        or f"11/23 黄仁勋复职仅撑起一日空头平仓反弹，11/24 实体清单再砸芯片 -7.78%，标普仍压在 {spx_200d:,} 点年线下方——绝不被单日阳线诱入追高。"
    )))
    note_u2 = html_mod.escape(clean_svg_text(str(
        u2_nest.get("note") or cl.get("u2_note")
        or f"数据口径：标普道琼斯与纳斯达克官方收盘，截至 {as_full}。"
    )))

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_u2}</div>
      <div class="chart-sub">{sub_u2}</div>
      <svg viewBox="0 0 850 300" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="300" fill="#ffffff" rx="6"/>
        <rect x="516" y="20" width="188" height="226" fill="#fff1f2" opacity="0.55"/>
        <text x="610" y="34" text-anchor="middle" font-size="9.2" fill="#be123c" font-weight="700">11 月中旬五日连环风暴</text>
        <rect x="720" y="20" width="112" height="226" fill="#eff6ff" opacity="0.65"/>
        <text x="776" y="34" text-anchor="middle" font-size="9.2" fill="#1d4ed8" font-weight="700">{zone_lbl}</text>
        {grid}
        <line x1="56" y1="{y_200d}" x2="830" y2="{y_200d}" stroke="#b91c1c" stroke-width="1.5" stroke-dasharray="5,3"/>
        <text x="826" y="{y_200d-6}" text-anchor="end" font-size="9.0" fill="#b91c1c" font-weight="700">1年成本线 {spx_200d:,}（没站上去前按反弹对待，{pos_lbl}）</text>
        <line x1="56" y1="{y_6845}" x2="830" y2="{y_6845}" stroke="#D55E00" stroke-width="1.2" stroke-dasharray="3,2"/>
        <text x="278" y="{y_6845-5}" text-anchor="middle" font-size="9.0" fill="#D55E00" font-weight="700">华尔街救市痛点底线：6,845</text>
        <polyline fill="none" stroke="#D55E00" stroke-width="2.5" points="{poly}"/>
        {nodes}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway_u2}</div>
      <div class="chart-note">{note_u2}</div>
    </div>
    '''


def svg_chart_u3_credit_split(meta_override: dict | None = None) -> str:
    """Chart U3: 100% Plain-Language Credit Split (Full u3 Override + Verified CCC ~18% & Blue Owl)"""
    cl = load_meta(meta_override).get("chart_live", {})
    u3_nest = cl.get("u3") if isinstance(cl.get("u3"), dict) else {}
    as_full = html_mod.escape(clean_svg_text(str(cl.get("as_of_full", "2026-11-25 13:30 北京时间"))))
    calm = u3_nest.get("safe_items") or DEFAULT_U3_CALM
    cracks = u3_nest.get("risk_items") or DEFAULT_U3_CRACKS

    title_u3 = _norm_chart_title(
        u3_nest.get("title") or cl.get("u3_title")
        or "债市揭穿了股市反弹的底细——大银行没事，但借钱建 AI 机房的公司拉响警报"
    )
    sub_u3 = html_mod.escape(clean_svg_text(str(
        u3_nest.get("sub") or cl.get("u3_sub")
        or "对比“水面之上”（传统金融很稳）与“水面之下”（借高利贷建机房、私募信贷和比特币 ETF 持续失血）"
    )))
    takeaway_u3 = html_mod.escape(clean_svg_text(str(
        u3_nest.get("takeaway") or cl.get("u3_takeaway")
        or "做债券的债主比炒股的人冷静得多——11/23 甲骨文、科尔韦夫股票暴涨，但它们的债券违约保险费纹丝不动，CCC 级高息债总借钱成本冲向 18%，比特币 ETF 更连 5 日大失血。债主不点头，股市单靠情绪反弹很难一飞冲天。"
    )))
    note_u3 = html_mod.escape(clean_svg_text(str(
        u3_nest.get("note") or cl.get("u3_note")
        or f"数据口径：美联储金融稳定报告、纽约联储、彭博、穆迪、ICE 美银信用利差与 Farside ETF 资金流，截至 {as_full}。"
    )))

    lc = ""
    for i, item in enumerate(calm[:4]):
        k, v, sub = item[0], item[1], item[2]
        y = 46 + i * 54
        lc += f'<rect x="14" y="{y}" width="398" height="46" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="0.9" rx="5"/>'
        lc += f'<text x="22" y="{y+18}" font-size="9.3" fill="#064e3b" font-weight="700">{html_mod.escape(clean_svg_text(str(k)))}</text>'
        lc += f'<text x="22" y="{y+35}" font-size="9.0" fill="#047857">{html_mod.escape(clean_svg_text(str(sub)))}</text>'
        lc += f'<text x="404" y="{y+18}" text-anchor="end" font-size="9.3" fill="#009E73" font-weight="800">{html_mod.escape(clean_svg_text(str(v)))}</text>'

    rc = ""
    for i, item in enumerate(cracks[:6]):
        k, v, sub = item[0], item[1], item[2]
        y = 46 + i * 36.5
        rc += f'<rect x="432" y="{y}" width="404" height="31.5" fill="#fef2f2" stroke="#fecaca" stroke-width="0.9" rx="4"/>'
        rc += f'<text x="440" y="{y+13.5}" font-size="9.0" fill="#7f1d1d" font-weight="700">{html_mod.escape(clean_svg_text(str(k)))}</text>'
        rc += f'<text x="440" y="{y+26.5}" font-size="9.0" fill="#991b1b">{html_mod.escape(clean_svg_text(str(sub)))}</text>'
        rc += f'<text x="828" y="{y+13.5}" text-anchor="end" font-size="9.0" fill="#D55E00" font-weight="800">{html_mod.escape(clean_svg_text(str(v)))}</text>'

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_u3}</div>
      <div class="chart-sub">{sub_u3}</div>
      <svg viewBox="0 0 850 272" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="272" fill="#ffffff" rx="6"/>
        <rect x="14" y="10" width="398" height="26" fill="#009E73" rx="4"/>
        <text x="213" y="27" text-anchor="middle" font-size="9.8" fill="#ffffff" font-weight="700">● 水面之上：传统银行绿灯（美联储暂不急着救市）</text>
        <rect x="432" y="10" width="404" height="26" fill="#D55E00" rx="4"/>
        <text x="634" y="27" text-anchor="middle" font-size="9.8" fill="#ffffff" font-weight="700">× 水面之下：超 3 万亿 AI 借债、私募与币圈剧烈承压</text>
        {lc}
        {rc}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway_u3}</div>
      <div class="chart-note">{note_u3}</div>
    </div>
    '''


def svg_chart_u4_clock(meta_override: dict | None = None) -> str:
    """Chart U4: Beijing-Time Cross-Year Event Clock (Full Nested u4 Override + 12/12 13:00 CST Fix)"""
    cl = load_meta(meta_override).get("chart_live", {})
    u4_nest = cl.get("u4") if isinstance(cl.get("u4"), dict) else {}
    as_full = html_mod.escape(clean_svg_text(str(cl.get("as_of_full", "2026-11-25 13:30 北京时间"))))
    horizon = html_mod.escape(clean_svg_text(str(
        u4_nest.get("horizon") or cl.get("u4_horizon_label") or "2026 年 11 月下旬至 2027 年 1 月中旬"
    )))
    tier_s = html_mod.escape(clean_svg_text(str(cl.get("tier_short", "红灯防守期 (1 / 6 分)"))))
    zone = str(cl.get("us10y_zone", "high")).lower()
    line1 = html_mod.escape(clean_svg_text(str(cl.get("status_line1", "当前体检仅 1 / 6 分：美国 10 年国债利息高达 4.92%–4.94%（躺赚近 5%），标普反弹后仍压在年线（7,348）下方"))))
    line2 = html_mod.escape(clean_svg_text(str(cl.get("status_line2", "行动铁律：严禁追高芯片，守约 3 成防守（精算 28%）+ 62% 超短美债 + 10% 存量黄金 = 100%（黄金红灯停新仓 0%，空仓预算暂泊短债）"))))
    cards = u4_nest.get("cards") or DEFAULT_U4_CARDS

    title_u4 = _norm_chart_title(
        u4_nest.get("title") or cl.get("u4_title")
        or f"{horizon}核弹事件扎堆，12 月 21 日后才是大举买科技股的好时机"
    )
    sub_u4 = html_mod.escape(clean_svg_text(str(
        u4_nest.get("sub") or cl.get("u4_sub")
        or "已全部换算为北京时间的跨年排雷轴 ＋ 10 年期美债“地心引力”总开关"
    )))
    takeaway_u4 = html_mod.escape(clean_svg_text(str(
        u4_nest.get("takeaway") or cl.get("u4_takeaway")
        or "利率就像资产价格的地心引力——现在买无风险 10 年美债能拿近 5% 利息，引力太强，高估值科技股很难直接一飞冲天；等 12 月 18 日美、欧、英、日四大央行议息落地，就是最从容的进场时机。"
    )))
    note_u4 = html_mod.escape(clean_svg_text(str(
        u4_nest.get("note") or cl.get("u4_note")
        or f"数据口径：美国财政部、美联储、欧英日央行与交易所公开日程，截至 {as_full}。"
    )))

    if zone == "low":
        ptr_x, ptr_col, box_bg, box_bd, txt_col = 151, "#009E73", "#f0fdf4", "#86efac", "#166534"
    elif zone == "mid":
        ptr_x, ptr_col, box_bg, box_bd, txt_col = 390, "#ca8a04", "#fefce8", "#fde047", "#854d0e"
    else:
        ptr_x, ptr_col, box_bg, box_bd, txt_col = 640, "#D55E00", "#fef2f2", "#fca5a5", "#991b1b"

    card_specs = [(16, 192, "#64748b"), (226, 198, "#64748b"), (442, 190, "#009E73"), (650, 186, None)]
    cards_svg = ""
    for idx, c in enumerate(cards[:4]):
        cx, cw, arrow_col = card_specs[idx]
        hdr = html_mod.escape(clean_svg_text(str(c.get("header", ""))))
        col = str(c.get("color", "#ea580c"))
        bg = str(c.get("bg", "#fff7ed"))
        bd = str(c.get("border", col))
        cards_svg += f'<rect x="{cx}" y="34" width="{cw}" height="102" fill="{bg}" stroke="{bd}" stroke-width="1.4" rx="5"/>'
        cards_svg += f'<rect x="{cx}" y="34" width="{cw}" height="22" fill="{col}" rx="4"/>'
        cards_svg += f'<text x="{cx + cw/2}" y="49" text-anchor="middle" font-size="9.2" fill="#ffffff" font-weight="700">{hdr}</text>'
        ys = [72, 87, 102, 120]
        for j, it in enumerate(c.get("items", [])[:4]):
            if isinstance(it, (list, tuple)):
                txt, tc, bold = str(it[0]), str(it[1]), bool(it[2])
            else:
                txt, tc, bold = str(it), "#1e293b", False
            fw = "700" if bold else "500"
            cards_svg += f'<text x="{cx+8}" y="{ys[j]}" font-size="9.0" fill="{tc}" font-weight="{fw}">{html_mod.escape(clean_svg_text(txt))}</text>'
        if arrow_col:
            ax = cx + cw + 4
            cards_svg += f'<polygon points="{ax},81 {ax+10},85 {ax},89" fill="{arrow_col}"/>'

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_u4}</div>
      <div class="chart-sub">{sub_u4}</div>
      <svg viewBox="0 0 850 268" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="268" fill="#ffffff" rx="6"/>
        <text x="16" y="22" font-size="10.0" fill="#0f172a" font-weight="700">A. {horizon}美股关键大考（北京时间）与分步上车节奏</text>
        {cards_svg}
        <text x="16" y="162" font-size="10.0" fill="#0f172a" font-weight="700">B. 10 年期美债“地心引力”温度条（决定股市贵不贵的总开关 · {tier_s}）</text>
        <rect x="16" y="173" width="264" height="26" fill="#dcfce7" stroke="#009E73" stroke-width="1.3" rx="4"/>
        <text x="148" y="190" text-anchor="middle" font-size="9.3" fill="#166534" font-weight="700">● 宽松主升区：国债利息 &lt; 4.5%</text>
        <rect x="286" y="173" width="206" height="26" fill="#fef9c3" stroke="#ca8a04" stroke-width="1.2" rx="4"/>
        <text x="389" y="190" text-anchor="middle" font-size="9.3" fill="#854d0e" font-weight="700">▲ 震荡过渡区：4.5% – 4.85%</text>
        <rect x="498" y="173" width="338" height="26" fill="#fee2e2" stroke="#D55E00" stroke-width="1.4" rx="4"/>
        <text x="667" y="190" text-anchor="middle" font-size="9.3" fill="#991b1b" font-weight="700">× 高息压制区（&gt;4.85%）：10 年美债近 5%，高价股承压</text>
        <polygon points="{ptr_x},204 {ptr_x+8},215 {ptr_x-8},215" fill="{ptr_col}"/>
        <rect x="16" y="218" width="820" height="40" fill="{box_bg}" stroke="{box_bd}" stroke-width="0.9" rx="4"/>
        <text x="426" y="234" text-anchor="middle" font-size="9.0" fill="{txt_col}" font-weight="700">{line1}</text>
        <text x="426" y="250" text-anchor="middle" font-size="9.0" fill="#475569">{line2}</text>
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway_u4}</div>
      <div class="chart-note">{note_u4}</div>
    </div>
    '''


def svg_chart_u5_wall_street_forensic(meta_override: dict | None = None) -> str:
    """Chart U5: Clean Wall St 9-Bank Targets with Full u5 Override"""
    cl = load_meta(meta_override).get("chart_live", {})
    u5_nest = cl.get("u5") if isinstance(cl.get("u5"), dict) else {}
    spx_now = int(round(float(cl.get("spx", 7201))))
    spx_lbl = html_mod.escape(clean_svg_text(str(cl.get("as_of_short", f"11/24官收 {spx_now:,}"))))
    banks = u5_nest.get("banks") or DEFAULT_U5_BANKS
    mean_all = int(round(sum(int(t[1]) for t in banks) / max(1, len(banks))))
    b2027 = [t for t in banks if "2027" in str(t[0])] or banks[2:]
    mean_2027 = int(round(sum(int(t[1]) for t in b2027) / max(1, len(b2027))))
    up_2027 = ((mean_2027 - spx_now) / float(spx_now)) * 100.0
    lo_up = ((int(banks[0][1]) - spx_now) / float(spx_now)) * 100.0
    hi_up = ((int(banks[-1][1]) - spx_now) / float(spx_now)) * 100.0

    svg_h = max(288, 68 + len(banks) * 24)
    grid_y2 = svg_h - 26
    axis_y = svg_h - 10

    def x_p(val: float) -> float:
        clamped = max(6900, min(9150, val))
        return round(260 + ((clamped - 6900) / 2300.0) * 518, 1)

    grid = ""
    for val in [7000, 7500, 8000, 8500, 9000]:
        x = x_p(val)
        grid += f'<line x1="{x}" y1="36" x2="{x}" y2="{grid_y2}" stroke="#f1f5f9" stroke-width="1"/>'
        grid += f'<text x="{x}" y="{axis_y}" text-anchor="middle" font-size="9.4" fill="#64748b">{val:,}</text>'

    x_spx = x_p(spx_now)
    x_avg = x_p(mean_2027)

    rows = ""
    for i, item in enumerate(banks):
        name, tgt, col = str(item[0]), int(item[1]), str(item[2])
        y = 46 + i * 24.0
        xt = x_p(tgt)
        up = ((tgt - spx_now) / float(spx_now)) * 100.0
        rows += f'<text x="252" y="{y+9.5}" text-anchor="end" font-size="9.0" fill="#1e293b" font-weight="600">{html_mod.escape(clean_svg_text(name))}</text>'
        rows += f'<line x1="{x_spx}" y1="{y+5.5}" x2="{xt}" y2="{y+5.5}" stroke="{col}" stroke-width="5.2" opacity="0.22" stroke-linecap="round"/>'
        rows += f'<circle cx="{xt}" cy="{y+5.5}" r="4.6" fill="{col}"/>'
        rows += f'<text x="{xt+8}" y="{y+9.0}" font-size="9.0" fill="{col}" font-weight="700">{tgt:,} ({up:+.1f}%)</text>'

    title_u5 = _norm_chart_title(
        u5_nest.get("title") or cl.get("u5_title")
        or f"华尔街主流大行看 2027 年标普 8,450–8,650 中位（较 11/24 收盘仍有 {lo_up:+.0f}% 至 {hi_up:+.0f}% 空间）"
    )
    sub_u5 = html_mod.escape(clean_svg_text(str(
        u5_nest.get("sub") or cl.get("u5_sub")
        or "9 家已公布 2027 年底或未来 12 个月正式目标的华尔街主流机构（已剔除尚未更新的 2026 年旧目标）"
    )))
    takeaway_u5 = html_mod.escape(clean_svg_text(str(
        u5_nest.get("takeaway") or cl.get("u5_takeaway")
        or "哪怕全华尔街最谨慎的美国银行（7,800）也看 2027 年上涨近 8%，高盛/大摩/巴克莱更是看到 8,700（约 +20%）。这说明 2027 年长线并不悲观，我们现在防守只是为了躲过 12 月风浪、买在更舒服的位置。"
    )))
    note_u5 = html_mod.escape(clean_svg_text(str(
        u5_nest.get("note") or cl.get("u5_note")
        or f"数据口径：11 大投行最新 2027 年公开策略目标，相对 11/24 标普官收 {spx_now:,} 计算空间。"
    )))

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_u5}</div>
      <div class="chart-sub">{sub_u5}</div>
      <svg viewBox="0 0 850 {svg_h}" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="{svg_h}" fill="#ffffff" rx="6"/>
        {grid}
        <line x1="{x_spx}" y1="30" x2="{x_spx}" y2="{grid_y2}" stroke="#D55E00" stroke-width="1.6" stroke-dasharray="5,3"/>
        <text x="{x_spx+5}" y="23" text-anchor="start" font-size="9.0" fill="#D55E00" font-weight="700">{spx_lbl}</text>
        <line x1="{x_avg}" y1="30" x2="{x_avg}" y2="{grid_y2}" stroke="#009E73" stroke-width="1.4" stroke-dasharray="4,3"/>
        <text x="{x_avg}" y="23" text-anchor="middle" font-size="9.0" fill="#047857" font-weight="700">{len(b2027)} 家 2027年底均值 {mean_2027:,} ({up_2027:+.1f}%) · {len(banks)} 家总均值 {mean_all:,}</text>
        {rows}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway_u5}</div>
      <div class="chart-note">{note_u5}</div>
    </div>
    '''


def svg_chart_u6_sector_heatmap(meta_override: dict | None = None) -> str:
    """Chart U6: Verified SSGA 11 GICS Sectors Daily Move vs 52W High Drawdown (Nested u6 + Unified Linear Scale)"""
    cl = load_meta(meta_override).get("chart_live", {})
    u6_nest = cl.get("u6") if isinstance(cl.get("u6"), dict) else {}
    as_short = html_mod.escape(clean_svg_text(str(u6_nest.get("date_short") or cl.get("u6_date_short") or "11/24")))
    as_full = html_mod.escape(clean_svg_text(str(cl.get("as_of_full", "2026-11-25 13:30 北京时间"))))
    sectors = u6_nest.get("sectors") or cl.get("sectors") or DEFAULT_U_SECTORS
    n = len(sectors)
    row_h = 24.0
    svg_h = int(64 + n * row_h)

    up_cnt = sum(1 for s in sectors if float(s["pct"]) >= 0)
    dn_cnt = n - up_cnt

    raw_pos = max([float(s["pct"]) for s in sectors if float(s["pct"]) > 0] + [0.0])
    raw_neg = max([abs(float(s["pct"])) for s in sectors if float(s["pct"]) < 0] + [0.0])
    span_pct = max(raw_pos + raw_neg, 1.0)
    left_edge = 140.0
    right_bar_limit = 388.0
    px_per_pct = (right_bar_limit - left_edge) / span_pct
    x_pct0 = round(left_edge + raw_neg * px_per_pct, 1)
    x_dd0 = 824
    max_dd = max([abs(float(s["dd"])) for s in sectors] + [24.0])

    bg_rects = ""
    bars = ""
    for i, s in enumerate(sectors):
        y = 44 + i * row_h
        nm = html_mod.escape(clean_svg_text(str(s["name"])))
        pct = float(s["pct"])
        dd = float(s["dd"])
        is_xlk = "XLK" in nm
        is_xlp = "XLP" in nm
        if is_xlk:
            bg_rects += f'<rect x="10" y="{y-2}" width="830" height="{row_h-1}" fill="#eff6ff" stroke="#93c5fd" stroke-width="0.9" rx="3"/>'
        elif is_xlp:
            bg_rects += f'<rect x="10" y="{y-2}" width="830" height="{row_h-1}" fill="#fef2f2" stroke="#fca5a5" stroke-width="0.9" rx="3"/>'

        bars += f'<text x="128" y="{y+13.5}" text-anchor="end" font-size="9.4" fill="#1e293b" font-weight="{"800" if (is_xlk or is_xlp) else "600"}">{nm}</text>'
        if pct >= 0:
            w = max(round(pct * px_per_pct, 1), 2.0)
            col = "#0072B2" if pct >= 3.0 else "#0284c7"
            bars += f'<rect x="{x_pct0}" y="{y+2}" width="{w}" height="14" fill="{col}" opacity="0.86" rx="2"/>'
            bars += f'<text x="{x_pct0+w+5:.1f}" y="{y+13.5}" font-size="9.1" fill="{col}" font-weight="700">+{pct:.2f}%</text>'
        else:
            w = max(round(abs(pct) * px_per_pct, 1), 2.0)
            bars += f'<rect x="{x_pct0-w:.1f}" y="{y+2}" width="{w}" height="14" fill="#64748b" opacity="0.85" rx="2"/>'
            bars += f'<text x="{x_pct0+5:.1f}" y="{y+13.5}" font-size="9.1" fill="#475569" font-weight="700">{pct:.2f}%</text>'

        wd = max(round((abs(dd) / max_dd) * 235.0, 1), 8.0)
        if is_xlp:
            dcol = "#D55E00"
        elif abs(dd) >= 15:
            dcol = "#1e40af"
        elif abs(dd) >= 10:
            dcol = "#3b82f6"
        else:
            dcol = "#64748b"
        bars += f'<rect x="{x_dd0-wd}" y="{y+2}" width="{wd}" height="14" fill="{dcol}" opacity="0.84" rx="2"/>'
        if is_xlk and abs(dd) >= 15:
            lbl_d = f"{dd:.1f}%（仍打8折）"
        elif is_xlp and abs(dd) <= 5:
            lbl_d = f"{dd:.1f}%（高位偏贵）"
        else:
            lbl_d = f"{dd:.1f}%"
        bars += f'<text x="{x_dd0-wd-6}" y="{y+13.5}" text-anchor="end" font-size="9.0" fill="{dcol}" font-weight="700">{lbl_d}</text>'

    axes = (
        f'<line x1="448" y1="10" x2="448" y2="{svg_h-12}" stroke="#e2e8f0" stroke-width="1.2"/>'
        f'<line x1="{x_pct0}" y1="36" x2="{x_pct0}" y2="{svg_h-14}" stroke="#334155" stroke-width="1.1"/>'
        f'<line x1="{x_dd0}" y1="36" x2="{x_dd0}" y2="{svg_h-14}" stroke="#334155" stroke-width="1.1"/>'
    )
    title_u6 = _norm_chart_title(
        u6_nest.get("title") or cl.get("u6_title")
        or "美股 11 大板块反差——科技暴涨近 9% 仍离高点跌两成，必选消费却挤在山顶"
    )
    sub_u6 = html_mod.escape(clean_svg_text(str(
        u6_nest.get("sub") or cl.get("u6_sub")
        or f"{as_short} 美股 11 只官方行业 ETF 对比（左：当日涨跌幅 ｜ 右：距离 52 周高点回撤幅度，橙红 = 伪防御拥挤警报）"
    )))
    takeaway = html_mod.escape(clean_svg_text(str(
        u6_nest.get("takeaway") or cl.get("u6_takeaway")
        or "科技股（XLK）11/23 虽涨最猛，但离高点仍跌去近两成（打八折），12 月底风浪过后弹性最大；能源（XLE）同样回撤近 15% 跌出便宜价值；而超市必选消费（XLP）几乎没跌（仅 -3.3%）、估值挤在山顶，切忌盲目当作“便宜避风港”。"
    )))
    note_u6 = html_mod.escape(clean_svg_text(str(
        u6_nest.get("note") or cl.get("u6_note")
        or f"数据口径：SSGA 11 只 Select Sector SPDR ETF {as_short} 官方收盘与 52 周高点回撤，截至 {as_full}。"
    )))

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_u6}</div>
      <div class="chart-sub">{sub_u6}</div>
      <svg viewBox="0 0 850 {svg_h}" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="{svg_h}" fill="#ffffff" rx="6"/>
        {bg_rects}
        <text x="16" y="23" font-size="10.0" fill="#0f172a" font-weight="700">A. {as_short} 单日涨跌幅（{up_cnt} 涨 / {dn_cnt} 跌）</text>
        <text x="464" y="23" font-size="10.0" fill="#0f172a" font-weight="700">B. 距离 52 周高点回撤（条越长跌越深）</text>
        {axes}
        {bars}
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway}</div>
      <div class="chart-note">{note_u6}</div>
    </div>
    '''


def svg_chart_u7_stock_quadrant(meta_override: dict | None = None) -> str:
    """Chart U7: Representative US Stocks Quadrant Map — Full Nested u7 Override + Dynamic US10Y Parity Line"""
    cl = load_meta(meta_override).get("chart_live", {})
    u7_nest = cl.get("u7") if isinstance(cl.get("u7"), dict) else {}
    pool_cnt = int(cl.get("stock_pool_count", 46))
    us10y = float(cl.get("us10y", 4.901))
    parity_pe = float(u7_nest.get("parity_pe") or round(100.0 / max(1.0, us10y), 1))
    # Map PE linearly on visual axis (10x -> x=112, 25x -> x=450, 48x -> x=786)
    parity_x = round(max(120.0, min(680.0, 112.0 + ((parity_pe - 10.0) / 15.0) * 338.0)), 1)
    pts = u7_nest.get("points") or DEFAULT_U7_POINTS

    title_u7 = _norm_chart_title(
        u7_nest.get("title") or cl.get("u7_title")
        or "一眼识破美股“伪防御陷阱”——真防弹衣在左上角，苹果/沃尔玛/好市多贵在右下角"
    )
    sub_u7 = html_mod.escape(clean_svg_text(str(
        u7_nest.get("sub") or cl.get("u7_sub")
        or f"横轴：从左到右越来越贵（严格按 2027 预期市盈率递增） ｜ 纵轴：安全垫与现金流越扎实（精选代表标的，全量 {pool_cnt} 只见下表）"
    )))
    takeaway_u7 = html_mod.escape(clean_svg_text(str(
        u7_nest.get("takeaway") or cl.get("u7_takeaway")
        or f"垂直蓝虚线（{parity_pe:.1f} 倍）代表买无风险 10 年美债拿 {us10y:.2f}% 利息的等效估值——右下角的苹果（34 倍）、沃尔玛（42 倍）、好市多（48 倍）远贵于美债线，绝非安全股；真防弹衣在左上角的伯克希尔、大银行、大油企、洛马与艾伯维。"
    )))
    note_u7 = html_mod.escape(clean_svg_text(str(
        u7_nest.get("note") or cl.get("u7_note")
        or "数据口径：11/24 官方收盘与 2027 年预期市盈率（伯克希尔扣现金经营估值约 16–17 倍；纽蒙特金矿受黄金红灯停锁为分歧观察）。"
    )))

    dots = ""
    for item in pts:
        nm, x, y, sh, col, dx, dy, anc = item
        dots += svg_shape(str(sh), float(x), float(y), str(col))
        dots += f'<text x="{float(x)+float(dx)}" y="{float(y)+float(dy)}" text-anchor="{anc}" font-size="9.0" fill="{col}" font-weight="700">{html_mod.escape(clean_svg_text(str(nm)))}</text>'

    return f'''
    <div class="chart-box">
      <div class="chart-title">{title_u7}</div>
      <div class="chart-sub">{sub_u7}</div>
      <svg viewBox="0 0 850 326" width="100%" font-family="PingFang SC, Hiragino Sans GB, sans-serif" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="850" height="326" fill="#ffffff" rx="6"/>
        <rect x="34" y="34" width="416" height="134" fill="#f0fdf4" opacity="0.72"/>
        <rect x="450" y="34" width="384" height="134" fill="#eff6ff" opacity="0.72"/>
        <rect x="34" y="168" width="416" height="110" fill="#fffbeb" opacity="0.65"/>
        <rect x="450" y="168" width="384" height="110" fill="#fef2f2" opacity="0.78"/>
        <line x1="{parity_x}" y1="34" x2="{parity_x}" y2="278" stroke="#0072B2" stroke-width="1.1" stroke-dasharray="3,3" opacity="0.75"/>
        <text x="{parity_x}" y="25" text-anchor="middle" font-size="9.0" fill="#0072B2" font-weight="700">10年美债等效线 {parity_pe:.1f}x ({us10y:.2f}%)</text>
        <line x1="450" y1="34" x2="450" y2="278" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,3"/>
        <line x1="34" y1="168" x2="834" y2="168" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,3"/>
        <rect x="34" y="34" width="800" height="244" fill="none" stroke="#cbd5e1" stroke-width="1"/>
        <text x="44" y="49" font-size="9.0" fill="#166534" font-weight="800">● 真防弹衣 &amp; 未来硬科技区（价格合理、现金流硬）</text>
        <text x="824" y="49" text-anchor="end" font-size="9.0" fill="#1e40af" font-weight="800">◆ 稳健巨头偏贵区（等回调再买）</text>
        <text x="44" y="270" font-size="9.0" fill="#92400e" font-weight="800">▲ 表面低估但有听证/强周期/高债暗流（勿盲抄）</text>
        <text x="824" y="270" text-anchor="end" font-size="9.0" fill="#991b1b" font-weight="800">× 伪防御高估 &amp; 泡沫雷区（坚决避开）</text>
        <text x="34" y="24" font-size="9.0" fill="#475569" font-weight="700">↑ 纵轴越高 = 安全垫与自由现金流越扎实</text>
        <text x="44" y="294" font-size="9.0" fill="#475569" font-weight="600">← 很便宜（10–18 倍）</text>
        <text x="450" y="294" text-anchor="middle" font-size="9.0" fill="#475569" font-weight="600">高利率警戒线（25 倍）</text>
        <text x="824" y="294" text-anchor="end" font-size="9.0" fill="#b91c1c" font-weight="600">严重透支（37–50+ 倍）→</text>
        {dots}
        <rect x="34" y="302" width="800" height="18" fill="#f8fafc" stroke="#e2e8f0" stroke-width="0.7" rx="3"/>
        <text x="434" y="315" text-anchor="middle" font-size="9.0" fill="#334155" font-weight="600">图例：<tspan fill="#009E73" font-weight="800">●</tspan> 当下底座（防弹衣） ｜ <tspan fill="#0072B2" font-weight="800">◆</tspan> 未来主攻（已上锁，12/21 后解锁） ｜ <tspan fill="#D97706" font-weight="800">▲</tspan> 分歧观察 ｜ <tspan fill="#D55E00" font-weight="800">×</tspan> 伪防御/高债回避</text>
      </svg>
      <div class="chart-takeaway"><span class="vtag vt-tip">要</span><strong>一句话看懂这张图：</strong>{takeaway_u7}</div>
      <div class="chart-note">{note_u7}</div>
    </div>
    '''


def main() -> None:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    args = sys.argv[1:]
    if "--check" in args:
        chrome = resolve_chrome_bin()
        assert Path(chrome).exists(), f"Chrome missing: {chrome}"
        import bs4  # noqa: F401
        from PIL import Image  # noqa: F401
        meta = load_meta()
        md_path, _ = resolve_flagship_paths(meta)
        assert md_path.exists(), f"Missing {md_path}"
        print(f"US-Stock builder check OK: {md_path.name} (Chrome + bs4 + Pillow ready)")
        return
    no_lint = "--no-lint" in args
    no_docx = "--no-docx" in args
    meta = load_meta()
    md_path, pdf_path = resolve_flagship_paths(meta)
    docx_path = pdf_path.with_suffix(".docx")
    frozen = freeze_equity_inputs(md_path, Path(__file__), META_PATH) if not no_docx else None
    if frozen is not None:
        meta = load_meta()
        if resolve_flagship_paths(meta)[0] != md_path:
            raise ValueError("Flagship period changed while preparing compilation")
    report_md = md_path.read_text(encoding="utf-8")
    print(f"Loaded US-Stock MD ({len(report_md)} chars): {md_path}")
    run_lint_gate(report_md, str(md_path), is_flagship=True, meta=meta, no_lint=no_lint)

    cover_html, doc_title, page_footer, footer_note = render_cover_banner(
        meta, "美国股市跨周期全景手册", "美股全景研究手册", "美国股市跨周期全景研究手册", meta_label="阅读说明"
    )
    charts = {
        "<!-- CHART_U1 -->": svg_chart_u1_crises_and_mas(meta),
        "<!-- CHART_U2 -->": svg_chart_u2_storm_timeline(meta),
        "<!-- CHART_U3 -->": svg_chart_u3_credit_split(meta),
        "<!-- CHART_U4 -->": svg_chart_u4_clock(meta),
        "<!-- CHART_U5 -->": svg_chart_u5_wall_street_forensic(meta),
        "<!-- CHART_U6 -->": svg_chart_u6_sector_heatmap(meta),
        "<!-- CHART_U7 -->": svg_chart_u7_stock_quadrant(meta),
    }
    _, body_pdf = render_md_body(report_md, charts, is_flagship=True)
    css_final = build_theme_css("us_stock", page_footer, is_flagship=True, compact_us=True)
    full_pdf_html = (
        f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html_mod.escape(doc_title)}</title><style>{css_final}</style></head>"
        f'<body>{cover_html}{body_pdf}<div class="footer-note">{html_mod.escape(footer_note)}</div></body></html>'
    )
    render_pdf_atomic(full_pdf_html, pdf_path, HTML_PDF_PATH, TMP_PDF_PATH)
    print(f"Wrote PDF ({pdf_path.stat().st_size:,} bytes): {pdf_path}")

    if no_docx:
        receipt_path = md_path.with_suffix(".artifacts.json")
        if receipt_path.exists():
            receipt_path.unlink()
            print(f"Removed stale artifact receipt: {receipt_path.name}")
        print("[WARN] --no-docx skips syncing *_latest.* to prevent PDF/DOCX divergence.")
        return

    render_docx_atomic(full_pdf_html, docx_path, market="us_stock", footer_title=page_footer)
    write_equity_receipt(frozen, pdf_path, docx_path)
    print(f"Wrote native OOXML DOCX ({docx_path.stat().st_size:,} bytes): {docx_path}")

    latest_md = OUT_DIR / "us_stock_market_report_latest.md"
    latest_pdf = OUT_DIR / "us_stock_market_report_latest.pdf"
    latest_docx = OUT_DIR / "us_stock_market_report_latest.docx"
    atomic_copy(md_path, latest_md)
    atomic_copy(pdf_path, latest_pdf)
    if docx_path.exists():
        atomic_copy(docx_path, latest_docx)
        print(f"Synced: {latest_md}, {latest_pdf} & {latest_docx}")
    else:
        print(f"Synced: {latest_md} & {latest_pdf}")


if __name__ == "__main__":
    main()
