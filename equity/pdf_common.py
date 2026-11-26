#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared pure-web publishing primitives, vector badge/SVG helpers, Markdown-to-HTML engine,
and embedded redline linter for global equity reports."""

from __future__ import annotations

import html as html_mod
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DAILY_DIR = BASE_DIR / "daily"

# Strip color-emoji ranges cleanly while preserving U+2610 (☐ ballot box) for checklists.
_EMOJI_STRIP_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U0000260F"
    "\U00002611-\U000027BF"
    "\U00002300-\U000023FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE0E-\U0000FE0F"
    "\U0000200D"
    "\U000020E3"
    "\U00002139"
    "\U00002194-\U000021AA"
    "\U00003030"
    "\U0000303D"
    "\U00003297"
    "\U00003299"
    "]+",
    flags=re.UNICODE,
)

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_ALLOWED_SVG_ANCHORS = frozenset({"start", "middle", "end"})


def sanitize_hex_color(val: object, default: str = "#334155") -> str:
    """Validate hex color tokens sourced from JSON before interpolating into SVG attributes."""
    s = str(val).strip() if val is not None else ""
    return s if _HEX_COLOR_RE.fullmatch(s) else default


def sanitize_svg_anchor(val: object, default: str = "start") -> str:
    """Validate SVG text-anchor values sourced from JSON."""
    s = str(val).strip().lower() if val is not None else ""
    return s if s in _ALLOWED_SVG_ANCHORS else default


def clean_plain_text(s: str) -> str:
    """Convert semantic emojis inside SVG/title/footer text to monochrome PingFang vector glyphs."""
    rep = [
        ("🛡️ ", ""), ("🛡️", ""), ("🛡 ", ""), ("🛡", ""),
        ("🚀 ", ""), ("🚀", ""),
        ("🔒 ", ""), ("🔒", ""),
        ("⚠️ ", ""), ("⚠️", ""), ("⚠ ", ""), ("⚠", ""),
        ("🛑 ", ""), ("🛑", ""),
        ("🔑 ", ""), ("🔑", ""),
        ("🔐 ", ""), ("🔐", ""),
        ("💰 ", ""), ("💰", ""),
        ("🟢 ", "● "), ("🟢", "●"),
        ("🔵 ", "◆ "), ("🔵", "◆"),
        ("🟡 ", "▲ "), ("🟡", "▲"),
        ("🔴 ", "× "), ("🔴", "×"),
        ("✅ ", "✓ "), ("✅", "✓"),
        ("❌ ", "× "), ("❌", "×"),
        ("⏳ ", "… "), ("⏳", "…"),
        ("❄️ ", ""), ("❄️", ""), ("❄", ""),
        ("🔥 ", ""), ("🔥", ""),
        ("🧭 ", "◆ "), ("🧭", "◆"),
        ("🚫 ", "× "), ("🚫", "×"),
        ("💡 ", "◆ "), ("💡", "◆"),
        ("🌤️ ", ""), ("🌤️", ""),
        ("🌧️ ", ""), ("🌧️", ""),
        ("🌋", ""),
        ("🎯", ""),
        ("⚡", ""),
        ("📅", ""),
        ("📌", ""),
        ("📋", ""),
        ("🌐", ""),
        ("🥇 ", ""),
        ("🥇", ""),
    ]
    for k, v in rep:
        s = s.replace(k, v)
    return _EMOJI_STRIP_RE.sub("", s)


clean_svg_text = clean_plain_text


def norm_chart_title(raw: str) -> str:
    """Normalize chart title with sequential {{CHART_NUM}} placeholder across A/HK/US builders."""
    clean = html_mod.escape(clean_svg_text(str(raw)).strip())
    if "{{CHART_NUM}}" in clean:
        return clean
    if re.match(r"^图\s*\d+\s*[：:]", clean):
        return re.sub(r"^图\s*\d+\s*[：:]", "图 {{CHART_NUM}}：", clean, count=1)
    return f"图 {{{{CHART_NUM}}}}：{clean}"


def html_vector_badges(s: str) -> str:
    """Replace emojis in HTML prose/tables with Okabe-Ito pure-CSS vector shapes & editorial pills."""
    rep = [
        ("🟢 ", '<span class="vmark vm-g">●</span>'),
        ("🟢", '<span class="vmark vm-g">●</span>'),
        ("🔵 ", '<span class="vmark vm-b">◆</span>'),
        ("🔵", '<span class="vmark vm-b">◆</span>'),
        ("🟡 ", '<span class="vmark vm-y">▲</span>'),
        ("🟡", '<span class="vmark vm-y">▲</span>'),
        ("🔴 ", '<span class="vmark vm-r">×</span>'),
        ("🔴", '<span class="vmark vm-r">×</span>'),
        ("✅ ", '<span class="vtag vt-ok">是</span>'),
        ("✅", '<span class="vtag vt-ok">是</span>'),
        ("❌ ", '<span class="vmark vm-r">×</span>'),
        ("❌", '<span class="vmark vm-r">×</span>'),
        ("⏳ ", '<span class="vtag vt-wait">待</span>'),
        ("⏳", '<span class="vtag vt-wait">待</span>'),
        ("🛡️ ", '<span class="vtag vt-shield">防</span>'),
        ("🛡️", '<span class="vtag vt-shield">防</span>'),
        ("🛡 ", '<span class="vtag vt-shield">防</span>'),
        ("🛡", '<span class="vtag vt-shield">防</span>'),
        ("🚀 ", '<span class="vtag vt-go">攻</span>'),
        ("🚀", '<span class="vtag vt-go">攻</span>'),
        ("🔒 ", '<span class="vtag vt-lock">锁</span>'),
        ("🔒", '<span class="vtag vt-lock">锁</span>'),
        ("⚠️ ", '<span class="vtag vt-warn">!</span>'),
        ("⚠️", '<span class="vtag vt-warn">!</span>'),
        ("⚠ ", '<span class="vtag vt-warn">!</span>'),
        ("⚠", '<span class="vtag vt-warn">!</span>'),
        ("🛑 ", '<span class="vtag vt-stop">止</span>'),
        ("🛑", '<span class="vtag vt-stop">止</span>'),
        ("💡 ", '<span class="vtag vt-tip">要</span>'),
        ("💡", '<span class="vtag vt-tip">要</span>'),
        ("💰 ", '<span class="vtag vt-money">账</span>'),
        ("💰", '<span class="vtag vt-money">账</span>'),
        ("🔑 ", '<span class="vtag vt-key">钥</span>'),
        ("🔑", '<span class="vtag vt-key">钥</span>'),
        ("🔐 ", '<span class="vtag vt-key">控</span>'),
        ("🔐", '<span class="vtag vt-key">控</span>'),
        ("🧭 ", '<span class="vtag vt-wait">观</span>'),
        ("🧭", '<span class="vtag vt-wait">观</span>'),
        ("🚫 ", '<span class="vtag vt-stop">禁</span>'),
        ("🚫", '<span class="vtag vt-stop">禁</span>'),
        ("🔥 ", '<span class="vtag vt-hot">热</span>'),
        ("🔥", '<span class="vtag vt-hot">热</span>'),
        ("🌋 ", '<span class="vtag vt-stop">险</span>'),
        ("🌋", '<span class="vtag vt-stop">险</span>'),
        ("🌤️ ", '<span class="vtag vt-ok">稳</span>'),
        ("🌤️", '<span class="vtag vt-ok">稳</span>'),
        ("🌤 ", '<span class="vtag vt-ok">稳</span>'),
        ("🌤", '<span class="vtag vt-ok">稳</span>'),
        ("🌧️ ", '<span class="vtag vt-wait">磨</span>'),
        ("🌧️", '<span class="vtag vt-wait">磨</span>'),
        ("🌧 ", '<span class="vtag vt-wait">磨</span>'),
        ("🌧", '<span class="vtag vt-wait">磨</span>'),
        ("🌦️ ", ""), ("🌦️", ""), ("🌦 ", ""), ("🌦", ""),
        ("❄️ ", '<span class="vtag vt-wait">冷</span>'),
        ("❄️", '<span class="vtag vt-wait">冷</span>'),
        ("❄", '<span class="vtag vt-wait">冷</span>'),
        ("🎯 ", '<span class="vtag vt-key">标</span>'),
        ("🎯", '<span class="vtag vt-key">标</span>'),
        ("⚡ ", '<span class="vtag vt-warn">急</span>'),
        ("⚡", '<span class="vtag vt-warn">急</span>'),
        ("📅 ", '<span class="vtag vt-tip">历</span>'),
        ("📅", '<span class="vtag vt-tip">历</span>'),
        ("📌 ", '<span class="vtag vt-tip">注</span>'),
        ("📌", '<span class="vtag vt-tip">注</span>'),
        ("📋 ", '<span class="vtag vt-tip">单</span>'),
        ("📋", '<span class="vtag vt-tip">单</span>'),
        ("🌐 ", '<span class="vtag vt-tip">全</span>'),
        ("🌐", '<span class="vtag vt-tip">全</span>'),
        ("🥇 ", '<span class="vtag vt-money">金</span>'),
        ("🥇", '<span class="vtag vt-money">金</span>'),
    ]
    for k, v in rep:
        s = s.replace(k, v)
    return _EMOJI_STRIP_RE.sub("", s)


def svg_shape(shape: str, x: float, y: float, col: str) -> str:
    """Okabe-Ito colorblind-safe vector markers: circle(g), diamond(b), triangle(y), cross(r)."""
    safe_col = sanitize_hex_color(col, "#334155")
    if shape == "g":
        return f'<circle cx="{x}" cy="{y}" r="5.5" fill="{safe_col}" stroke="#ffffff" stroke-width="1.5"/>'
    if shape == "b":
        return f'<polygon points="{x},{y-6.2} {x+6.2},{y} {x},{y+6.2} {x-6.2},{y}" fill="{safe_col}" stroke="#ffffff" stroke-width="1.4"/>'
    if shape == "y":
        return f'<polygon points="{x},{y-6.2} {x+6.2},{y+5.0} {x-6.2},{y+5.0}" fill="{safe_col}" stroke="#ffffff" stroke-width="1.3"/>'
    return (
        f'<circle cx="{x}" cy="{y}" r="6.2" fill="#fee2e2" stroke="{safe_col}" stroke-width="1.4"/>'
        f'<line x1="{x-3.4}" y1="{y-3.4}" x2="{x+3.4}" y2="{y+3.4}" stroke="{safe_col}" stroke-width="1.9" stroke-linecap="round"/>'
        f'<line x1="{x+3.4}" y1="{y-3.4}" x2="{x-3.4}" y2="{y+3.4}" stroke="{safe_col}" stroke-width="1.9" stroke-linecap="round"/>'
    )


def _split_md_row(line: str) -> list[str]:
    """Split a Markdown table row on unescaped pipes while preserving escaped \\| literals."""
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith(r"\|"):
        inner = inner[:-1]
    return [c.replace(r"\|", "|").strip() for c in re.split(r"(?<!\\)\|", inner)]


def md_inline(text: str) -> str:
    text = text.replace("<br>", "___BR_TAG___").replace("<br/>", "___BR_TAG___").replace("<br />", "___BR_TAG___")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("___BR_TAG___", "<br/>")
    code_tokens: list[str] = []
    link_tokens: list[str] = []

    def save_code(m):
        code_tokens.append(f'<code class="inline-code">{m.group(1)}</code>')
        return f"___CODE_{len(code_tokens)-1}___"

    def save_link(m):
        lbl = html_vector_badges(m.group(1))
        raw_href = html_mod.unescape(m.group(2)).strip()
        if raw_href.lower().startswith(("file:", "javascript:", "data:")):
            return lbl
        if not re.match(r"^(?:https?://|\.\.?/|#[A-Za-z0-9_.:-]+$)", raw_href, flags=re.IGNORECASE):
            return m.group(0)
        href = html_mod.escape(raw_href, quote=True)
        link_tokens.append(f'<a href="{href}" class="md-link">{lbl}</a>')
        return f"___LINK_{len(link_tokens)-1}___"

    text = re.sub(r"`([^`]+)`", save_code, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", save_link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![A-Za-z0-9_])\*(?!\s|ST)([^*\n]+?)(?<!\s)\*(?![A-Za-z0-9_])", r"<em>\1</em>", text)
    text = html_vector_badges(text)
    for idx, tok in enumerate(link_tokens):
        text = text.replace(f"___LINK_{idx}___", tok)
    for idx, tok in enumerate(code_tokens):
        text = text.replace(f"___CODE_{idx}___", tok)
    return text


def parse_alignments(sep_cells: list[str]) -> list[str]:
    aligns: list[str] = []
    for c in sep_cells:
        c = c.strip()
        if c.startswith(":") and c.endswith(":"):
            aligns.append("center")
        elif c.endswith(":"):
            aligns.append("right")
        else:
            aligns.append("left")
    return aligns


def classify_callout(raw_lines: list[str]) -> str:
    joined = " ".join(raw_lines)
    if any(k in joined for k in ("一句话", "本章核心结论")):
        cls = "callout callout-verdict"
    elif any(k in joined for k in ("头号雷区", "头号避雷", "避雷", "避坑", "下单前", "🛑", "高危")):
        cls = "callout callout-danger"
    elif any(
        k in joined
        for k in (
            "双钥匙", "压力测试", "前置安全", "默认核心", "极简方案", "3 只 ETF", "路线 A", "极端恐慌",
            "昨日→今日", "早刊→晚刊", "早刊→午刊", "今早", "万一不回调", "双账户专属", "双账户实操",
            "昨日预判验真", "早刊预判验真", "下单执行", "港股衔接", "税务", "双向防踏空",
        )
    ):
        cls = "callout callout-guard"
    else:
        cls = "callout"
    non_empty = [x for x in raw_lines if x.strip()]
    if len(non_empty) >= 6 and "下单前" not in joined:
        cls += " callout-flow"
    return cls


def _wrap_svg_scrollable(chart_html: str) -> str:
    """Wrap raw <svg> inside .svg-scroll for narrow-screen mobile legibility."""
    if 'class="svg-scroll"' in chart_html:
        return chart_html
    return re.sub(
        r"(<svg\b.*?</svg>)",
        r'<div class="svg-scroll">\1</div><div class="svg-hint">← 图表可左右滑动清晰查看 →</div>',
        chart_html,
        count=1,
        flags=re.DOTALL,
    )


def render_md_body(
    md_text: str,
    charts: dict[str, str],
    *,
    default_title: str = "",
    is_flagship: bool = False,
    enable_kanban_wrap: bool = False,
) -> tuple[str, str]:
    lines = md_text.strip().splitlines()
    title = default_title
    html_out: list[str] = []
    in_table = False
    table_header_cells: list[str] = []
    table_aligns: list[str] = []
    table_body_rows: list[tuple[str, list[str]]] = []
    in_ol = False
    in_ul = False
    in_sub_ul = False
    in_callout = False
    callout_buf: list[str] = []
    in_code_block = False
    code_block_buf: list[str] = []
    chart_counter = 0
    sec_counter = 0
    h2_counter = 0

    def close_lists():
        nonlocal in_ol, in_ul, in_sub_ul
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
        nonlocal in_table, table_header_cells, table_aligns, table_body_rows
        if not in_table:
            return
        if table_header_cells:
            is_kanban = enable_kanban_wrap and any("四色阵营" in c for c in table_header_cells)
            total_chars = sum(sum(len(c) for c in cells) for _, cells in table_body_rows)
            is_short = (not is_kanban) and (1 <= len(table_body_rows) <= 5) and (total_chars <= 650)
            wrap_cls = "table-wrap"
            if is_kanban:
                wrap_cls += " kanban-wrap"
            elif is_short:
                wrap_cls += " short-table"

            h0 = table_header_cells[0] if table_header_cells else ""
            c1_cls = ""
            if any(k in h0 for k in ("所属赛道", "核验周次", "锁定日期")):
                c1_cls = ' class="c1-nowrap"'
            elif any(k in h0 for k in ("账户现状", "北京时间", "常见词", "对比维度", "市场与场次")):
                c1_cls = ' class="c1-min"'

            parts: list[str] = [f'<div class="{wrap_cls}"><table><thead><tr>']
            for idx, c in enumerate(table_header_cells):
                al = table_aligns[idx] if idx < len(table_aligns) else "left"
                cls_attr = c1_cls if idx == 0 else ""
                parts.append(f'<th{cls_attr} style="text-align:{al};">{md_inline(c)}</th>')
            parts.append("</tr></thead><tbody>")
            for row_cls, cells in table_body_rows:
                parts.append(f"<tr{row_cls}>")
                for idx, c in enumerate(cells):
                    al = table_aligns[idx] if idx < len(table_aligns) else "left"
                    cls_attr = c1_cls if idx == 0 else ""
                    parts.append(f'<td{cls_attr} style="text-align:{al};">{md_inline(c)}</td>')
                parts.append("</tr>")
            parts.append("</tbody></table></div>")
            html_out.append("".join(parts))

        in_table = False
        table_header_cells = []
        table_aligns = []
        table_body_rows = []

    def flush_callout():
        nonlocal in_callout, callout_buf
        if in_callout and callout_buf:
            cls = classify_callout(callout_buf)
            parts: list[str] = []
            for raw_c in callout_buf:
                sc = raw_c.strip()
                if not sc:
                    continue
                if sc.startswith("### "):
                    parts.append(f'<div class="callout-title">{md_inline(sc[4:].strip())}</div>')
                elif sc.startswith("## "):
                    parts.append(f'<div class="callout-title">{md_inline(sc[3:].strip())}</div>')
                elif sc.startswith("☐ ") or sc.startswith("- [ ] "):
                    body_c = sc[2:].strip() if sc.startswith("☐ ") else sc[6:].strip()
                    parts.append(
                        f'<label class="callout-chk">'
                        f'<input type="checkbox" class="chk-inp"/>'
                        f'<span class="chk-box">☐</span>'
                        f'<span class="chk-txt">{md_inline(body_c)}</span>'
                        f"</label>"
                    )
                elif re.match(r"^\d+\.\s+", sc):
                    parts.append(f'<div class="callout-ol">{md_inline(sc)}</div>')
                elif re.match(r"^[-•*]\s+", sc):
                    clean_item = re.sub(r"^[-•*]\s+", "", sc)
                    parts.append(f'<div class="callout-item">• {md_inline(clean_item)}</div>')
                else:
                    parts.append(f'<div class="callout-line">{md_inline(sc)}</div>')
            html_out.append(f'<div class="{cls}">{"".join(parts)}</div>')
        in_callout = False
        callout_buf = []

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_callout()
            close_lists()
            close_table()
            if in_code_block:
                esc_code = html_mod.escape("\n".join(code_block_buf))
                html_out.append(f'<pre class="code-block"><code>{esc_code}</code></pre>')
                code_block_buf = []
                in_code_block = False
            else:
                in_code_block = True
            continue
        if in_code_block:
            code_block_buf.append(line)
            continue

        if not (line.startswith("> ") or stripped == ">"):
            flush_callout()

        if stripped in charts:
            close_lists()
            close_table()
            chart_counter += 1
            rendered_chart = charts[stripped].replace("{{CHART_NUM}}", str(chart_counter))
            html_out.append(_wrap_svg_scrollable(rendered_chart))
            continue

        if stripped.startswith("<!--") and stripped.endswith("-->"):
            continue

        if not stripped or stripped == "---":
            close_lists()
            close_table()
            continue

        if line.startswith("# "):
            close_lists()
            close_table()
            txt = line[2:].strip()
            if is_flagship:
                if any(k in txt for k in ("第一部分", "第二部分", "第三部分", "第四部分", "附录")):
                    sec_counter += 1
                    html_out.append(f'<h1 id="sec-{sec_counter}" class="vol-header">{md_inline(txt)}</h1>')
                continue
            if any(k in txt for k in ("第一部分", "第二部分", "第三部分", "第四部分", "附录")):
                sec_counter += 1
                html_out.append(f'<h1 id="sec-{sec_counter}" class="vol-header">{md_inline(txt)}</h1>')
            elif title == default_title:
                title = txt
            else:
                sec_counter += 1
                html_out.append(f'<h1 id="sec-{sec_counter}" class="vol-header">{md_inline(txt)}</h1>')
            continue

        if line.startswith("> ") or stripped == ">":
            close_lists()
            close_table()
            in_callout = True
            callout_buf.append(line[2:].strip() if line.startswith("> ") else "")
            continue

        if line.startswith("|") and line.endswith("|"):
            close_lists()
            cells = _split_md_row(line)
            if all(re.match(r"^:?-{2,}:?$", c) for c in cells):
                table_aligns = parse_alignments(cells)
                continue
            if not in_table:
                in_table = True
                table_header_cells = cells
                table_aligns = ["left"] * len(cells)
                table_body_rows = []
            else:
                row_cls = ""
                row_join = " ".join(cells)
                if "🟢 当下底座" in row_join:
                    row_cls = ' class="row-g"'
                elif "🔵 🔒未来主攻" in row_join:
                    row_cls = ' class="row-b"'
                elif "🟡 分歧观察" in row_join:
                    row_cls = ' class="row-y"'
                elif "🔴 高危回避" in row_join:
                    row_cls = ' class="row-r"'
                table_body_rows.append((row_cls, cells))
            continue
        else:
            close_table()

        if line.startswith("## "):
            close_lists()
            h2_counter += 1
            html_out.append(f'<h2 id="h2-{h2_counter}">{md_inline(line[3:].strip())}</h2>')
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
        if (in_ol or in_ul) and re.match(r"^\s{2,}\S", line) and not m_num and not m_bul:
            if in_sub_ul:
                html_out.append("</ul>")
                in_sub_ul = False
            html_out.append(f'<div class="ol-sub">{md_inline(stripped)}</div>')
            continue
        if m_num:
            if in_ul:
                close_lists()
            if in_sub_ul:
                html_out.append("</ul></li>")
                in_sub_ul = False
            elif in_ol:
                html_out.append("</li>")
            if not in_ol:
                in_ol = True
                html_out.append("<ol>")
            html_out.append(f"<li>{md_inline(m_num.group(2))}")
            continue
        if m_bul or m_sub:
            txt = m_bul.group(1) if m_bul else m_sub.group(1)
            if in_ol:
                close_lists()
            if in_sub_ul:
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

    flush_callout()
    close_lists()
    close_table()
    return title, "\n".join(html_out)


def render_cover_banner(
    meta: dict | None,
    fallback_title: str,
    fallback_tag: str,
    fallback_footer: str,
    *,
    meta_label: str = "阅读说明",
) -> tuple[str, str, str, str]:
    esc = lambda x: html_vector_badges(html_mod.escape(str(x)))
    if not meta:
        cover = (
            f'<div class="cover-banner" id="top">\n'
            f'  <div class="cover-tag">{esc(fallback_tag)}</div>\n'
            f'  <div class="cover-title">{md_inline(fallback_title)}</div>\n'
            f"</div>"
        )
        return cover, clean_plain_text(fallback_title), clean_plain_text(fallback_footer), ""

    tag = esc(meta.get("tag", fallback_tag))
    cov_title = esc(meta.get("title", fallback_title))
    bench = esc(meta.get("benchmark_time", ""))
    meth = esc(meta.get("methodology", ""))
    kpis = meta.get("kpis", [])[:6]
    strip_cls = "kpi-strip cols-3" if len(kpis) > 4 else "kpi-strip"
    cards = [
        f'    <div class="kpi-card">\n'
        f'      <div class="kpi-label">{esc(k.get("label", ""))}</div>\n'
        f'      <div class="kpi-val">{esc(k.get("val", ""))}</div>\n'
        f'      <div class="kpi-sub">{esc(k.get("sub", ""))}</div>\n'
        f'    </div>'
        for k in kpis
    ]
    kpi_html = f'  <div class="{strip_cls}">\n' + "\n".join(cards) + "\n  </div>\n" if cards else ""
    parts = []
    if bench:
        parts.append(f"<strong>更新时点</strong>：{bench}")
    if meth:
        parts.append(f"<strong>{meta_label}</strong>：{meth}")
    meta_line = f'  <div class="cover-meta">{" &nbsp;|&nbsp; ".join(parts)}</div>\n' if parts else ""
    cover = (
        f'<div class="cover-banner" id="top">\n'
        f'  <div class="cover-tag">{tag}</div>\n'
        f'  <div class="cover-title">{cov_title}</div>\n'
        f"{meta_line}{kpi_html}</div>"
    )
    doc_title = clean_plain_text(str(meta.get("title", fallback_title)))
    page_footer = clean_plain_text(str(meta.get("page_footer", fallback_footer)))
    footer_note = clean_plain_text(str(meta.get("footer_note", "")))
    return cover, doc_title, page_footer, footer_note


_BANNED_INTERNAL_RE = re.compile(
    r"(?:\bV\d+\.\d+\b|Subagent|红队|法证|\bTier\s*[0-3]\b|"
    r"build_(?:a_share_pdf|hk_stock_pdf|us_stock_pdf|daily|report|site|pdf)\.py|"
    r"publish_site\.py|pdf_common\.py|docx_embed\.py|lint_(?:equity|readability|site)\.py|"
    r"edition_(?:run|plan|validation)\.py|artifact_receipt\.py|chart_input\.py|install_sidecars\.py|"
    r"patch_state_dbs\.py|_edition_patch\.json|_ledger_patch\.json|"
    r"DAILY_REPORT_SPEC\.md|DAILY_FORMAT_SPEC\.md|audit_ledger\.md|market_state\.json|"
    r"multi_asset_channels\.json|etf_universe\.json|deep_dossiers\.json|market_calendar\.json|"
    r"master_snapshot\.json|data_snapshot\.json|unified-edition\.prompt\.md|permissions\.json|"
    r"AGENTS\.md|GEMINI\.md|SKILL\.md|sidecar\.json|"
    r"RSI_PLAYBOOK(?:\.md)?|rsi_metrics\.json|Meta-RSI|Recursive\s+Self-Improvement|"
    r"next_run_watch|rsi_self_review_protocol|"
    r"RSI\s*(?:自(?:我|优|评|检|进)|盲审|复盘|闭环|体检|遥测|打分|简报|手册|进化|迭代|协议)|"
    r"\bTier\s*[ABC](?:/[ABC])+\b|"
    r"\bTier\s*[ABC]\s*(?:自|提案|补丁|改进|优化|经验|规则|落盘|落地|架构|锁定|权限|边界|评估|升级)|"
    r"20\d{6}_1\.csv|适配手机端免横滑)",
    flags=re.IGNORECASE,
)
_COLOR_CONFUSION_RE = re.compile(r"(?:收红|收绿|翻红|翻绿|飘红|飘绿)")
_BARE_NUM_BACKTICK_RE = re.compile(r"`[\+\-]?\d+(?:[.,–\-]\d+)?(?:%|元|港元|美元|亿|万|倍|点|手)`")
_HK_SAUDI_ETF_MISUSE_RE = re.compile(r"520830.{0,14}(?:港股|红利|高股息|央企)|(?:港股|红利|高股息|央企).{0,14}520830")
_HK_SAUDI_ETF_WARN_ALLOW_RE = re.compile(r"(?:严禁|切忌|勿|不可|非|并非|不是|误作|误买|当成|沙特)")
_HK_TAX_CUT_FALSE_RE = re.compile(r"港股通.{0,12}红利税.{0,8}(?:已正式落地|已经取消|已下调至\s*10%)")
_HK_ETF_ZERO_PREM_RE = re.compile(r"(?:159545|159792).{0,18}(?:零溢价|无溢价)|(?:零溢价|无溢价).{0,18}(?:159545|159792)")
_HK_ETF_ZERO_PREM_ALLOW_RE = re.compile(r"(?:并非|不是|不保证|仍须查|仍要查|严禁写|不等同于)")
_HK_REDCHIP_28_RE = re.compile(
    r"离岸.{0,6}10%\s*税.{0,8}28%|港股通.{0,12}(?:红筹|00883|00941|01378|00836).{0,10}28%|"
    r"红筹.{0,6}28%\s*税|28%\s*红筹税"
)
_HK_REDCHIP_28_ALLOW_RE = re.compile(r"(?:严禁笼统|不能笼统|并非一律|不是一律|不再写|废止|纠偏|勿写|严禁写|并非固定|不能简单按)")
_CB_TAX_FREE_RE = re.compile(r"末日.{0,10}二级卖出.{0,8}免\s*20%\s*个人税|二级市场卖出可免税")
_CB_TAX_FREE_ALLOW_RE = re.compile(r"(?:并非|不是|严禁写|不能笼统|废止|勿写|纠偏)")
_CONDESCENDING_SLOGAN_RE = re.compile(r"(?:蠢事|直接抄|小白词典|1\s*分钟定心丸|保命铁律)")
_NEW_DAILY_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_(?:a_share|hk_stock|us_stock)(?:_r\d+)?\.md$")
_FLAGSHIP_REL_DATE_RE = re.compile(
    r"(?:昨天|昨日|今天|今日|明天|明日|昨晚|今早|今晚|同晚|本周|上周|下周|去年底|今年以来|今年底|明年一季度)"
)
_RARE_JARGON_RE = re.compile(
    r"(?:\bstop-through\b|\bFVOCI\b|\bHQLA\b|熊平|\bROTCE\b|\bGAAP\b|¢)",
    flags=re.IGNORECASE,
)
_TIER2_GLOSS_PATTERNS: tuple[tuple[str, re.Pattern[str], re.Pattern[str], int], ...] = (
    ("ON RRP", re.compile(r"\bON\s+RRP\b", re.IGNORECASE), re.compile(r"(?:隔夜逆回购|逆回购)"), 20),
    ("IOPV", re.compile(r"\bIOPV\b", re.IGNORECASE), re.compile(r"(?:参考净值|盘中净值)"), 20),
    ("bp", re.compile(r"\d+\s*bp\b", re.IGNORECASE), re.compile(r"基点"), 16),
    ("DXY", re.compile(r"\bDXY\b", re.IGNORECASE), re.compile(r"美元指数"), 24),
    ("COT", re.compile(r"\bCOT\b", re.IGNORECASE), re.compile(r"(?:持仓|期货持仓|投机净多|仓位报告)"), 24),
    ("CDS", re.compile(r"\bCDS\b", re.IGNORECASE), re.compile(r"(?:违约互换|信用违约|违约保险|主权违约)"), 24),
    ("ERP", re.compile(r"\bERP\b", re.IGNORECASE), re.compile(r"(?:风险溢价|股权溢价|股债性价比)"), 24),
    ("IRR", re.compile(r"\bIRR\b", re.IGNORECASE), re.compile(r"(?:内部收益率|年化复利|复利收益|到期收益|真实年化)"), 24),
)
_US_0730_AFTERHOURS_RE = re.compile(
    r"(?:09:00.{0,8}盘后终盘|盘后终盘.{0,12}09:00|20:00\s*EST.{0,8}盘后终盘|"
    r"08:00.{0,8}盘后终盘|盘后终盘.{0,12}08:00|20:00\s*EDT.{0,8}盘后终盘)"
)
_US_0730_DEFER_ALLOW_RE = re.compile(
    r"(?:待下期补核|待补核|待今晚|待今日|待明日|由.{0,6}18:00|由晚刊封账|尚未终盘|人工补核|盘后回溯)"
)


def _extract_meta_strings(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, list):
        for x in obj:
            out.extend(_extract_meta_strings(x))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_extract_meta_strings(v))
    return out


def lint_markdown_report(
    md_text: str,
    filename: str,
    *,
    is_flagship: bool = False,
    meta: dict | None = None,
) -> tuple[list[str], list[str]]:
    """Pre-render redline linter returning (hard_errors, soft_warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    meta_match = re.search(r"<!--\s*DAILY_META_JSON\s*\{.*?\}\s*-->", md_text, flags=re.DOTALL)
    body_no_meta = re.sub(r"<!--\s*DAILY_META_JSON\s*\{.*?\}\s*-->", "", md_text, flags=re.DOTALL)

    if meta_match and md_text[meta_match.end() :].strip():
        warnings.append("DAILY_META_JSON 未置于文件最末尾（末尾仍有正文残留）")

    meta_text = "\n".join(_extract_meta_strings(meta)) if meta else ""
    combined_scan = body_no_meta + "\n" + meta_text

    m_ban = _BANNED_INTERNAL_RE.findall(combined_scan)
    if m_ban:
        errors.append(f"禁止内部工程词泄露 ({len(m_ban)} 处): {sorted(set(m_ban))}")

    m_col = _COLOR_CONFUSION_RE.findall(combined_scan)
    if m_col:
        errors.append(f"跨市场涨跌颜色混用 ({len(m_col)} 处): {sorted(set(m_col))}")

    if "_0730_us_stock" in filename:
        for ln in combined_scan.splitlines():
            if _US_0730_AFTERHOURS_RE.search(ln) and not _US_0730_DEFER_ALLOW_RE.search(ln):
                errors.append("07:30 美股早刊时间穿越违规：严禁写入 09:00/08:00 CST 盘后终盘（统一由 18:00 晚刊封账）")
                break

    for ln in combined_scan.splitlines():
        if _HK_SAUDI_ETF_MISUSE_RE.search(ln) and not _HK_SAUDI_ETF_WARN_ALLOW_RE.search(ln):
            errors.append("ETF 代码硬错误：520830 为沙特 ETF(QDII)，并非港股通红利 ETF（应改用 159545/513630/520810）")
            break
    if _HK_TAX_CUT_FALSE_RE.search(combined_scan):
        errors.append("港股政策硬错误：港股通个人红利税减免尚未官方落地，严禁误写为已实施")

    for ln in combined_scan.splitlines():
        if _HK_ETF_ZERO_PREM_RE.search(ln) and not _HK_ETF_ZERO_PREM_ALLOW_RE.search(ln):
            errors.append('ETF 规则硬错误：159545/159792 为非 QDII 港股通 ETF，买入前仍须查二级市场折溢价，严禁写"零溢价/无溢价"')
            break
    for ln in combined_scan.splitlines():
        if _HK_REDCHIP_28_RE.search(ln) and not _HK_REDCHIP_28_ALLOW_RE.search(ln):
            errors.append('港股税务口径硬错误：红筹股息须按发行人派息公告、登记方式与持有渠道分别核验源头代扣与 20% 港股通个税，严禁笼统写"红筹28%税/离岸10%完胜28%"')
            break
    for ln in combined_scan.splitlines():
        if _CB_TAX_FREE_RE.search(ln) and not _CB_TAX_FREE_ALLOW_RE.search(ln):
            errors.append('可转债到期税费硬错误：须按发行人公告核对到期票息 20% 代扣后净兑付额并与二级净卖出额逐笔比较，严禁写"末日二级卖出免20%个人税"')
            break

    if meta is not None:
        kpis = meta.get("kpis")
        if not isinstance(kpis, list) or not (2 <= len(kpis) <= 6):
            errors.append("元数据结构错误：kpis 须为 2–6 个对象的数组")
        else:
            for idx, k in enumerate(kpis):
                if not isinstance(k, dict) or not all(f in k for f in ("label", "val", "sub")):
                    errors.append(f"元数据 kpis[{idx}] 缺少 label/val/sub 必填字段")
        cl = meta.get("chart_live")
        if isinstance(cl, dict) and "us10y_zone" in cl and str(cl["us10y_zone"]).lower() not in ("low", "mid", "high"):
            errors.append(f"chart_live.us10y_zone 非法枚举值: {cl['us10y_zone']}")

    bare_bt = _BARE_NUM_BACKTICK_RE.findall(body_no_meta)
    if bare_bt:
        warnings.append(f"裸数字/金额反引号 ({len(bare_bt)} 处): {bare_bt[:5]}")

    jargon_hits = _RARE_JARGON_RE.findall(body_no_meta)
    for _label, term_re, gloss_re, win in _TIER2_GLOSS_PATTERNS:
        for m in term_re.finditer(body_no_meta):
            ctx = body_no_meta[max(0, m.start() - win) : min(len(body_no_meta), m.end() + win)]
            if not gloss_re.search(ctx):
                jargon_hits.append(m.group(0))
    if jargon_hits:
        warnings.append(f"未转译生僻行话 ({len(jargon_hits)} 处): {sorted(set(jargon_hits))}")

    bold_chars = sum(len(x) for x in re.findall(r"\*\*([^*]+)\*\*", body_no_meta))
    plain_chars = max(1, len(re.sub(r"\s+", "", body_no_meta)))
    bold_pct = (bold_chars / plain_chars) * 100.0
    if bold_pct > 13.5:
        warnings.append(f"加粗文字占比偏高: {bold_pct:.1f}% (目标 ≤12%)")

    long_paras = 0
    wide_tables = 0
    max_cols = 6 if Path(filename).name == "SCORECARD.md" else 5
    for ln in body_no_meta.splitlines():
        st = ln.strip()
        if st.startswith("|") and st.endswith("|"):
            cols = len(_split_md_row(st))
            if cols > max_cols:
                wide_tables += 1
        elif st and not st.startswith(("#", "|", ">", "-", "*", "<!--", "```")) and not re.match(r"^\d+\.\s", st):
            if len(st) > 180:
                long_paras += 1
    if long_paras:
        warnings.append(f"存在 {long_paras} 段超过 180 字的长段落")
    if wide_tables:
        warnings.append(f"存在 {wide_tables} 行表格超过 {max_cols} 列")

    if is_flagship:
        rel_hits = _FLAGSHIP_REL_DATE_RE.findall(body_no_meta)
        if rel_hits:
            warnings.append(f"常青旗舰手册残留相对时间词 ({len(rel_hits)} 处): {sorted(set(rel_hits))}")
    else:
        m_daily = _NEW_DAILY_NAME_RE.match(Path(filename).name)
        if m_daily and (m_daily.group(1), int(m_daily.group(2))) >= ("2026-11-26", 1800):
            slogan_hits = _CONDESCENDING_SLOGAN_RE.findall(combined_scan)
            if slogan_hits:
                warnings.append(f"口号化/说教用语提醒 ({len(slogan_hits)} 处): {sorted(set(slogan_hits))}")
        if Path(filename).name not in ("INDEX.md", "CHANGELOG.md", "SCORECARD.md"):
            index_path = DAILY_DIR / "INDEX.md"
            if index_path.exists():
                idx_txt = index_path.read_text(encoding="utf-8")
                if Path(filename).name not in idx_txt:
                    warnings.append(f"提醒：daily/INDEX.md 尚未收录 {Path(filename).name}")

    return errors, warnings
