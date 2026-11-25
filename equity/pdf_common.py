#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared publishing primitives, SkPDF emoji guard, markdown/CSS engine, atomic Chrome PDF builder,
responsive mobile HTML exporter (with sticky nav, dark mode, interactive checklist & SVG scroll),
and embedded pre-render redline linter."""

from __future__ import annotations

import html as html_mod
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.artifact_receipt import FrozenInputs

BASE_DIR = Path(__file__).resolve().parent
DAILY_DIR = BASE_DIR / "daily"
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def freeze_equity_inputs(source: Path, *inputs: Path) -> FrozenInputs | None:
    root = BASE_DIR.parent
    if not source.resolve().is_relative_to(root):
        return None
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.artifact_receipt import freeze_inputs

    return freeze_inputs(source, inputs=(*inputs, Path(__file__), BASE_DIR / "docx_embed.py"))


def write_equity_receipt(frozen: FrozenInputs | None, pdf: Path, docx: Path) -> None:
    if frozen is not None:
        from scripts.artifact_receipt import write_receipt

        write_receipt(frozen, pdf, docx)


# Strip color-emoji ranges that trigger Apple Color Emoji sbix failures in macOS Chrome SkPDF.
# Deliberately preserves U+2610 (☐ ballot box) for printable checklists.
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
    if shape == "g":
        return f'<circle cx="{x}" cy="{y}" r="5.5" fill="{col}" stroke="#ffffff" stroke-width="1.5"/>'
    if shape == "b":
        return f'<polygon points="{x},{y-6.2} {x+6.2},{y} {x},{y+6.2} {x-6.2},{y}" fill="{col}" stroke="#ffffff" stroke-width="1.4"/>'
    if shape == "y":
        return f'<polygon points="{x},{y-6.2} {x+6.2},{y+5.0} {x-6.2},{y+5.0}" fill="{col}" stroke="#ffffff" stroke-width="1.3"/>'
    return (
        f'<circle cx="{x}" cy="{y}" r="6.2" fill="#fee2e2" stroke="{col}" stroke-width="1.4"/>'
        f'<line x1="{x-3.4}" y1="{y-3.4}" x2="{x+3.4}" y2="{y+3.4}" stroke="{col}" stroke-width="1.9" stroke-linecap="round"/>'
        f'<line x1="{x+3.4}" y1="{y-3.4}" x2="{x-3.4}" y2="{y+3.4}" stroke="{col}" stroke-width="1.9" stroke-linecap="round"/>'
    )


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
        href = html_mod.escape(m.group(2), quote=True)
        link_tokens.append(f'<a href="{href}" class="md-link">{lbl}</a>')
        return f"___LINK_{len(link_tokens)-1}___"

    text = re.sub(r"`([^`]+)`", save_code, text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+|file://[^)\s]+|\.\.?/[^)\s]+)\)", save_link, text)
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
    """Wrap raw <svg> inside .svg-scroll for narrow-screen mobile legibility (no-op in print)."""
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
            cells = [c.strip() for c in line.strip("|").split("|")]
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


def escape_css_content(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


def build_theme_css(
    market: str,
    page_footer: str,
    *,
    is_flagship: bool = False,
    compact_us: bool = False,
) -> str:
    if market == "a_share":
        cover_bg = "linear-gradient(135deg, #18181b 0%, #27272a 60%, #3f3f46 100%)"
        accent = "#dc2626"
        kpi_val_col = "#fbbf24"
        vol_border = "#dc2626"
        vol_bg = "linear-gradient(90deg, #fef2f2 0%, #fff7ed 100%)"
        vol_txt = "#7f1d1d"
        h2_border = "#fecaca"
        h3_col = "#991b1b"
        verdict_top = "#dc2626"
        verdict_strong = "#991b1b"
        guard_border = "#334155"
        dark_h3 = "#fca5a5"
        dark_verdict_strong = "#fca5a5"
    elif market == "hk_stock":
        cover_bg = "linear-gradient(135deg, #042f2e 0%, #115e59 58%, #134e4a 100%)"
        accent = "#0d9488"
        kpi_val_col = "#fbbf24"
        vol_border = "#0f766e"
        vol_bg = "linear-gradient(90deg, #f0fdfa 0%, #f8fafc 100%)"
        vol_txt = "#115e59"
        h2_border = "#99f6e4"
        h3_col = "#0f766e"
        verdict_top = "#0f766e"
        verdict_strong = "#115e59"
        guard_border = "#0f766e"
        dark_h3 = "#5eead4"
        dark_verdict_strong = "#5eead4"
    else:
        cover_bg = "linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #1e3a5f 100%)"
        accent = "#2563eb"
        kpi_val_col = "#38bdf8"
        vol_border = "#1d4ed8"
        vol_bg = "linear-gradient(90deg, #eff6ff 0%, #f8fafc 100%)"
        vol_txt = "#1e3a8a"
        h2_border = "#bfdbfe"
        h3_col = "#1e40af"
        verdict_top = "#1d4ed8"
        verdict_strong = "#1e3a8a"
        guard_border = "#1e3a8a"
        dark_h3 = "#93c5fd"
        dark_verdict_strong = "#93c5fd"

    if is_flagship and compact_us:
        td_pad, tbl_lh, body_fs, body_lh = "2.9px 6px", "1.35", "9.3pt", "1.56"
    elif is_flagship:
        td_pad, tbl_lh, body_fs, body_lh = "3.0px 6px", "1.36", "9.3pt", "1.56"
    else:
        td_pad, tbl_lh, body_fs, body_lh = "3.4px 6px", "1.38", "9.25pt", "1.56"

    safe_footer = escape_css_content(page_footer)
    return f"""
@page {{
  size: A4 portrait;
  margin: 14.5mm 14.5mm 15mm 14.5mm;
  @bottom-center {{
    content: "{safe_footer}  ·  第 " counter(page) " / " counter(pages) " 页";
    font-family: "PingFang SC", sans-serif;
    font-size: 7.8pt;
    color: #94a3b8;
  }}
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  font-family: "PingFang SC", "Hiragino Sans GB", "Helvetica Neue", "Microsoft YaHei", sans-serif;
  color: #1f2937;
  font-size: {body_fs};
  line-height: {body_lh};
  font-variant-numeric: tabular-nums;
  margin: 0;
  padding: 0;
  background: #ffffff;
}}
p, li {{ orphans: 3; widows: 3; }}
.md-link {{ color: #0072B2; text-decoration: none; font-weight: 600; }}
.md-link:hover {{ text-decoration: underline; }}
.mob-nav, .svg-hint {{ display: none; }}
.vmark {{
  display: inline-block;
  font-size: 9.0pt;
  font-weight: 900;
  line-height: 1;
  vertical-align: -0.5px;
  margin: 0 3px 0 1px;
  text-indent: 0;
}}
.vm-g {{ color: #009E73; }}
.vm-b {{ color: #0072B2; font-size: 8.6pt; }}
.vm-y {{ color: #D97706; font-size: 8.2pt; }}
.vm-r {{ color: #D55E00; font-size: 10.0pt; }}
.vtag {{
  display: inline-block;
  font-size: 7.0pt;
  font-weight: 800;
  line-height: 1.15;
  padding: 1px 4px;
  border-radius: 3px;
  vertical-align: middle;
  margin: 0 3px 1px 1px;
  text-indent: 0;
}}
.vt-shield {{ background: #fee2e2; color: #991b1b; border: 0.7px solid #fca5a5; }}
.vt-ok {{ background: #dcfce7; color: #166534; border: 0.7px solid #86efac; }}
.vt-go {{ background: #dbeafe; color: #1e40af; border: 0.7px solid #93c5fd; }}
.vt-lock {{ background: #e0e7ff; color: #3730a3; border: 0.7px solid #a5b4fc; }}
.vt-warn {{ background: #fef3c7; color: #92400e; border: 0.7px solid #fcd34d; }}
.vt-stop {{ background: #fee2e2; color: #991b1b; border: 0.7px solid #fca5a5; }}
.vt-tip {{ background: #e0f2fe; color: #075985; border: 0.7px solid #7dd3fc; }}
.vt-money {{ background: #fef3c7; color: #78350f; border: 0.7px solid #fbbf24; }}
.vt-key {{ background: #f3e8ff; color: #6b21a8; border: 0.7px solid #d8b4fe; }}
.vt-wait {{ background: #f1f5f9; color: #475569; border: 0.7px solid #cbd5e1; }}
.vt-hot {{ background: #ffedd5; color: #9a3412; border: 0.7px solid #fdba74; }}
.cover-banner {{
  background: {cover_bg};
  color: #ffffff;
  padding: 16px 20px 14px 20px;
  border-radius: 9px;
  border-bottom: 4px solid {accent};
  margin-bottom: 11px;
}}
.cover-banner .vtag {{ font-size: 7.6pt; padding: 1.5px 5px; }}
.cover-banner .vt-shield, .cover-banner .vt-stop {{
  background: rgba(220, 38, 38, 0.28); color: #fecaca; border-color: rgba(248, 113, 113, 0.55);
}}
.cover-banner .vt-ok {{
  background: rgba(16, 185, 129, 0.26); color: #a7f3d0; border-color: rgba(52, 211, 153, 0.55);
}}
.cover-banner .vt-go {{
  background: rgba(59, 130, 246, 0.28); color: #bfdbfe; border-color: rgba(96, 165, 250, 0.55);
}}
.cover-banner .vt-warn, .cover-banner .vt-money {{
  background: rgba(245, 158, 11, 0.28); color: #fde68a; border-color: rgba(251, 191, 36, 0.55);
}}
.cover-banner .vt-tip, .cover-banner .vt-lock, .cover-banner .vt-key, .cover-banner .vt-wait {{
  background: rgba(56, 189, 248, 0.24); color: #bae6fd; border-color: rgba(125, 211, 252, 0.5);
}}
.cover-tag {{
  display: inline-block;
  background: {accent};
  color: #ffffff;
  font-size: 7.7pt;
  font-weight: 700;
  letter-spacing: 0.5px;
  padding: 2.5px 9px;
  border-radius: 4px;
  margin-bottom: 6px;
}}
.cover-title {{ font-size: 16.0pt; font-weight: 800; line-height: 1.3; margin: 0 0 6px 0; color: #ffffff; }}
.cover-meta {{ font-size: 8.2pt; color: #e2e8f0; line-height: 1.46; margin-bottom: 9px; }}
.cover-banner strong {{ color: #ffffff; }}
.kpi-strip {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 7px; margin-top: 4px; }}
.kpi-strip.cols-3 {{ grid-template-columns: repeat(3, 1fr); gap: 6px; }}
.kpi-card {{
  background: rgba(255, 255, 255, 0.09);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 6px;
  padding: 7px 10px;
}}
.kpi-label {{ font-size: 8.0pt; color: #cbd5e1; font-weight: 600; }}
.kpi-val {{ font-size: 11.1pt; font-weight: 800; color: {kpi_val_col}; margin-top: 1.5px; }}
.kpi-sub {{ font-size: 8.0pt; color: #f1f5f9; margin-top: 1.5px; line-height: 1.38; }}
.vol-header {{
  background: {vol_bg};
  border-left: 5px solid {vol_border};
  color: {vol_txt};
  font-size: 12.2pt;
  font-weight: 800;
  padding: 7px 12px;
  margin: 15px 0 8px 0;
  border-radius: 0 6px 6px 0;
  page-break-after: avoid;
  break-after: avoid;
}}
h2 {{
  font-size: 11.0pt; font-weight: 800; color: #0f172a;
  border-bottom: 1.6px solid {h2_border}; padding-bottom: 3px;
  margin: 12px 0 6px 0; page-break-after: avoid; break-after: avoid;
}}
h3 {{
  font-size: 9.8pt; font-weight: 700; color: {h3_col};
  margin: 9.5px 0 4.5px 0; page-break-after: avoid; break-after: avoid;
}}
h4 {{
  font-size: 9.2pt; font-weight: 700; color: #334155;
  background: #f8fafc; border-left: 3px solid {accent};
  padding: 3px 8px; margin: 9px 0 4.5px 0; page-break-after: avoid; break-after: avoid;
}}
p {{ margin: 4px 0 7px 0; text-align: left; }}
ul {{ margin: 4px 0 7px 0; padding-left: 19px; }}
ol {{ margin: 4px 0 7px 0; padding-left: 22px; }}
.sub-ul {{ margin: 2.5px 0 4.5px 0; padding-left: 16px; list-style-type: disc; }}
li {{ margin-bottom: 3.6px; }}
.ol-sub {{ margin-top: 2px; color: #334155; }}
strong {{ color: #0f172a; font-weight: 700; }}
.inline-code {{
  font-family: "SF Mono", "Menlo", monospace; font-size: 8.3pt;
  color: #1e293b; font-weight: 600; background: #f1f5f9;
  padding: 0.5px 3.5px; border-radius: 3px;
}}
.code-block {{
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;
  padding: 7px 9px; font-family: "SF Mono", "Menlo", monospace;
  font-size: 7.9pt; white-space: pre-wrap; word-break: break-word;
}}
.callout {{
  background: #fffbeb; border-left: 3.5px solid #d97706;
  border-radius: 0 6px 6px 0; padding: 8px 12px; margin: 7px 0 9px 0;
  font-size: 9.0pt; line-height: 1.56; color: #451a03;
  page-break-inside: avoid; break-inside: avoid;
}}
.callout-verdict {{
  background: #f8f7f3; border-left: none;
  border-top: 2px solid {verdict_top}; border-bottom: 1.2px solid #cbd5e1;
  border-radius: 0; color: #1e293b; padding: 8px 11px;
}}
.callout-verdict strong {{ color: {verdict_strong}; }}
.callout-danger {{ background: #fef2f2; border-left: 4px solid #dc2626; color: #7f1d1d; }}
.callout-danger strong {{ color: #991b1b; }}
.callout-guard {{ background: #f8fafc; border-left: 4px solid {guard_border}; color: #1e293b; }}
.callout-guard strong {{ color: #0f172a; }}
.callout-flow {{ page-break-inside: auto; break-inside: auto; }}
.callout-title {{ font-size: 9.4pt; font-weight: 800; color: #0f172a; margin-bottom: 3.5px; }}
.callout-danger .callout-title {{ color: #991b1b; }}
.callout-item {{ margin: 2px 0; padding-left: 2px; }}
.callout-ol {{ margin: 2px 0; padding-left: 2px; text-indent: 0; }}
.callout-chk {{ display: flex; align-items: flex-start; gap: 6px; margin: 3.5px 0; text-indent: 0; cursor: pointer; }}
.chk-inp {{ display: none; }}
.chk-box {{ flex: 0 0 auto; font-weight: 700; color: #dc2626; font-size: 9.8pt; line-height: 1.5; }}
.chk-txt {{ flex: 1 1 auto; text-indent: 0; }}
.callout-line {{ margin: 2px 0; }}
.table-wrap {{ margin: 7px 0 9.5px 0; overflow: visible; }}
.kanban-wrap, .short-table {{ page-break-inside: avoid; break-inside: avoid; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8.2pt; line-height: {tbl_lh}; page-break-inside: auto; }}
thead {{ display: table-header-group; }}
tr {{ page-break-inside: avoid; break-inside: avoid; }}
th {{
  background: #f1f5f9; color: #0f172a; font-weight: 800; padding: 4.5px 6px;
  border-top: 2px solid #0f172a; border-bottom: 1.4px solid #475569;
  border-left: none; border-right: none;
}}
td {{
  padding: {td_pad}; border-bottom: 1px solid #e2e8f0;
  border-left: none; border-right: none; vertical-align: top;
}}
th.c1-nowrap, td.c1-nowrap {{ white-space: nowrap; width: 1%; }}
th.c1-min, td.c1-min {{ min-width: 78px; }}
tbody tr:nth-child(even) {{ background: #f8fafc; }}
tbody tr.row-g td:first-child {{ border-left: 3px solid #009E73; }}
tbody tr.row-b td:first-child {{ border-left: 3px solid #0072B2; }}
tbody tr.row-y td:first-child {{ border-left: 3px solid #D97706; }}
tbody tr.row-r td:first-child {{ border-left: 3px solid #D55E00; }}
.chart-box {{
  background: #ffffff; border: 1px solid #e2e8f0; border-radius: 7px;
  padding: 8.5px 10px 7px 10px; margin: 8px 0 9.5px 0;
  page-break-inside: avoid; break-inside: avoid;
}}
.chart-title {{ font-size: 9.6pt; font-weight: 800; color: #0f172a; margin-bottom: 2px; }}
.chart-sub {{ font-size: 7.8pt; color: #64748b; margin-bottom: 5px; }}
.chart-takeaway {{
  background: #f0f9ff; border-left: 3.5px solid #0072B2; border-radius: 0 5px 5px 0;
  padding: 5.5px 9px; margin-top: 5px; font-size: 8.3pt; line-height: 1.48; color: #0c4a6e;
}}
.chart-note {{ font-size: 7.4pt; color: #94a3b8; line-height: 1.36; margin-top: 3.5px; }}
svg {{ display: block; width: 100%; height: auto; }}
.footer-note {{
  margin-top: 9px; padding-top: 6px; border-top: 1px solid #cbd5e1;
  font-size: 7.7pt; color: #64748b; text-align: center; line-height: 1.46;
}}
@media screen {{
  html {{ background: #f1f5f9; }}
  body {{
    max-width: 780px; margin: 16px auto; padding: 18px 20px 28px 20px;
    border-radius: 12px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.08);
    font-size: 15.5px; line-height: 1.72;
  }}
  .mob-nav {{
    display: flex; align-items: center; gap: 6px; overflow-x: auto;
    -webkit-overflow-scrolling: touch; position: sticky; top: 0; z-index: 40;
    background: rgba(255, 255, 255, 0.94); backdrop-filter: blur(8px);
    padding: 8px 10px; margin: -18px -20px 14px -20px;
    border-bottom: 1px solid #e2e8f0; border-radius: 12px 12px 0 0;
    white-space: nowrap;
  }}
  .mob-nav a {{
    display: inline-block; font-size: 12.5px; font-weight: 700;
    color: #334155; background: #f1f5f9; border: 1px solid #e2e8f0;
    padding: 4px 10px; border-radius: 999px; text-decoration: none; flex: 0 0 auto;
  }}
  .mob-nav a.nav-switch {{
    background: {accent}; color: #ffffff; border-color: {accent};
  }}
  .cover-tag {{ font-size: 12px; padding: 3px 10px; }}
  .cover-title {{ font-size: 21px; }}
  .cover-meta, .kpi-label, .kpi-sub {{ font-size: 13px; }}
  .kpi-val {{ font-size: 16.5px; }}
  .vol-header {{ font-size: 19px; padding: 9px 14px; margin: 20px 0 10px 0; }}
  h2 {{ font-size: 17.5px; margin: 16px 0 8px 0; }}
  h3 {{ font-size: 16px; margin: 13px 0 6px 0; }}
  h4 {{ font-size: 15px; padding: 5px 10px; }}
  .inline-code {{ font-size: 13px; padding: 1px 5px; }}
  .vtag {{ font-size: 11.5px; padding: 1.5px 5px; }}
  .vmark {{ font-size: 14px; }}
  .callout {{ font-size: 14.5px; padding: 11px 14px; }}
  .callout-title {{ font-size: 15.5px; margin-bottom: 5px; }}
  .chk-box {{ display: none; }}
  .chk-inp {{
    display: inline-block; width: 17px; height: 17px; margin-top: 3px;
    accent-color: #dc2626; cursor: pointer; flex: 0 0 auto;
  }}
  .callout-chk:has(.chk-inp:checked) .chk-txt {{ text-decoration: line-through; opacity: 0.62; }}
  .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  table {{ font-size: 13.5px; }}
  th, td {{ padding: 7px 8px; }}
  .chart-title {{ font-size: 15.5px; }}
  .chart-sub, .chart-takeaway {{ font-size: 13.5px; }}
  .chart-note, .footer-note {{ font-size: 12px; }}
}}
@media screen and (max-width: 680px) {{
  .svg-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 4px; }}
  .svg-scroll svg {{ min-width: 640px; }}
  .svg-hint {{
    display: block; text-align: center; font-size: 11.5px; color: #64748b;
    margin-top: 3px; letter-spacing: 0.3px;
  }}
}}
@media screen and (max-width: 600px) {{
  body {{
    margin: 0; border-radius: 0;
    padding: 12px calc(12px + env(safe-area-inset-right, 0px)) calc(22px + env(safe-area-inset-bottom, 0px)) calc(12px + env(safe-area-inset-left, 0px));
    font-size: 16px;
  }}
  .mob-nav {{ margin: -12px -12px 12px -12px; border-radius: 0; }}
  .kpi-strip, .kpi-strip.cols-3 {{ grid-template-columns: 1fr; }}
  table {{ min-width: 0; width: 100%; font-size: 13.5px; }}
  th.c1-min, td.c1-min {{ min-width: 64px; }}
}}
@media screen and (prefers-color-scheme: dark) {{
  html {{ background: #020617; }}
  body {{ background: #0f172a; color: #e2e8f0; box-shadow: none; }}
  .mob-nav {{ background: rgba(15, 23, 42, 0.94); border-bottom-color: #334155; }}
  .mob-nav a {{ background: #1e293b; color: #e2e8f0; border-color: #334155; }}
  h2 {{ color: #f8fafc; border-bottom-color: #334155; }}
  h3 {{ color: {dark_h3}; }}
  h4 {{ color: #e2e8f0; background: #1e293b; }}
  strong {{ color: #f8fafc; }}
  .ol-sub {{ color: #cbd5e1; }}
  .vol-header {{ background: #1e293b; color: #f8fafc; }}
  .inline-code {{ background: #1e293b; color: #93c5fd; }}
  .code-block {{ background: #1e293b; border-color: #334155; color: #e2e8f0; }}
  .callout {{ background: #292012; color: #fde68a; }}
  .callout-verdict {{ background: #1e293b; color: #e2e8f0; border-bottom-color: #334155; }}
  .callout-verdict strong {{ color: {dark_verdict_strong}; }}
  .callout-danger {{ background: #2a1215; color: #fecaca; }}
  .callout-danger strong, .callout-danger .callout-title {{ color: #fca5a5; }}
  .callout-guard {{ background: #1e293b; color: #e2e8f0; }}
  .callout-title {{ color: #f8fafc; }}
  th {{ background: #1e293b; color: #f8fafc; border-top-color: #64748b; border-bottom-color: #475569; }}
  td {{ border-bottom-color: #334155; }}
  tbody tr:nth-child(even) {{ background: #172033; }}
  .chart-box {{ background: #1e293b; border-color: #334155; }}
  .chart-title {{ color: #f8fafc; }}
  .chart-sub, .chart-note, .footer-note, .svg-hint {{ color: #94a3b8; }}
  .chart-takeaway {{ background: #0c2a3e; color: #bae6fd; }}
  .svg-scroll {{ background: #ffffff; border-radius: 6px; padding: 4px; }}
  .md-link {{ color: #38bdf8; }}
}}
"""


def prepare_mobile_html(full_html: str, market: str) -> str:
    """Enhance single-file daily HTML for phone browsers (3-market sticky nav, safe-area viewport, relative links)."""
    mob = full_html.replace(
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
    )
    root_uri = f"file://{BASE_DIR}"
    mob = mob.replace(f"{root_uri}/daily/", "./").replace(f"{root_uri}/", "../")

    market_tabs = [
        ("a_share", "./latest_a_share.html", "A 股"),
        ("hk_stock", "./latest_hk_stock.html", "港股"),
        ("us_stock", "./latest_us_stock.html", "美股"),
    ]
    nav_links = [
        f'<a href="{href}" class="nav-switch">切{lbl}</a>'
        for mkey, href, lbl in market_tabs
        if mkey != market
    ]
    sec_matches = re.findall(r'<h1 id="(sec-\d+)" class="vol-header">(.*?)</h1>', mob)
    if not sec_matches:
        sec_matches = re.findall(r'<h2 id="(h2-\d+)">(.*?)</h2>', mob)[:5]
    for sec_id, raw_lbl in sec_matches:
        plain = re.sub(r"<[^>]+>", "", raw_lbl).strip()
        short = plain.split("：", 1)[0].split("（", 1)[0][:10].rstrip(" 、，,·-—:：")
        nav_links.append(f'<a href="#{sec_id}">{html_mod.escape(short)}</a>')
    nav_links.append('<a href="#top">↑ 顶部</a>')
    nav_bar = '<nav class="mob-nav">' + "".join(nav_links) + "</nav>"
    return mob.replace("<body>", f"<body>{nav_bar}", 1)


_BANNED_INTERNAL_RE = re.compile(
    r"(?:\bV\d+\.\d+\b|Subagent|红队|法证|\bTier\s*[0-3]\b|"
    r"build_(?:a_share_pdf|hk_stock_pdf|us_stock_pdf|daily|report|site|pdf)\.py|"
    r"publish_site\.py|pdf_common\.py|docx_embed\.py|lint_(?:equity|readability|site)\.py|"
    r"DAILY_REPORT_SPEC\.md|DAILY_FORMAT_SPEC\.md|audit_ledger\.md|market_state\.json|"
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
_FLAGSHIP_REL_DATE_RE = re.compile(
    r"(?:昨天|昨日|今天|今日|明天|明日|昨晚|今早|今晚|同晚|本周|上周|下周|去年底|今年以来|今年底|明年一季度)"
)
_RARE_JARGON_RE = re.compile(
    r"(?:\bstop-through\b|\bFVOCI\b|\bON\s+RRP\b|熊平|\bIOPV\b|\bROTCE\b|\bGAAP\b|\d+\s*bp\b|¢)",
    flags=re.IGNORECASE,
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
        errors.append("港股政策硬错误：港股通个人红利税减免截至 2026-11 尚未官方落地，严禁误写为已实施")

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
            cols = len([c for c in st.strip("|").split("|")])
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
    elif Path(filename).name not in ("INDEX.md", "CHANGELOG.md", "SCORECARD.md"):
        index_path = DAILY_DIR / "INDEX.md"
        if index_path.exists():
            idx_txt = index_path.read_text(encoding="utf-8")
            if Path(filename).name not in idx_txt:
                warnings.append(f"提醒：daily/INDEX.md 尚未收录 {Path(filename).name}")

    return errors, warnings


def run_lint_gate(
    md_text: str,
    filename: str,
    *,
    is_flagship: bool = False,
    meta: dict | None = None,
    no_lint: bool = False,
) -> None:
    errors, warnings = lint_markdown_report(md_text, filename, is_flagship=is_flagship, meta=meta)
    for w in warnings:
        print(f"  [LINT WARN] {Path(filename).name}: {w}")
    if errors:
        for e in errors:
            print(f"  [LINT ERROR] {Path(filename).name}: {e}")
        if not no_lint:
            raise SystemExit(f"Blocked by redline linter ({len(errors)} error(s)) in {filename}")


def atomic_copy(src: Path, dst: Path) -> None:
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def render_pdf_atomic(
    full_html: str,
    pdf_path: Path,
    tmp_html: Path,
    tmp_pdf: Path,
    *,
    mobile_html_path: Path | None = None,
    mobile_market: str = "a_share",
) -> None:
    chrome_profile = Path(tempfile.mkdtemp(prefix="eq_chrome_pdf_"))
    try:
        tmp_html.write_text(full_html, encoding="utf-8")
        if tmp_pdf.exists():
            tmp_pdf.unlink()
        subprocess.run(
            [
                CHROME_BIN,
                "--headless",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--no-first-run",
                "--no-default-browser-check",
                f"--user-data-dir={chrome_profile}",
                "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw",
                f"--print-to-pdf={tmp_pdf}",
                str(tmp_html),
            ],
            check=True,
            timeout=120,
        )
        if not tmp_pdf.exists() or tmp_pdf.stat().st_size < 50_000:
            raise RuntimeError(f"PDF generation failed or file too small: {tmp_pdf}")
        os.replace(tmp_pdf, pdf_path)
        if mobile_html_path is not None:
            mob_html = prepare_mobile_html(full_html, mobile_market)
            tmp_mob = mobile_html_path.with_name(mobile_html_path.name + ".tmp")
            tmp_mob.write_text(mob_html, encoding="utf-8")
            os.replace(tmp_mob, mobile_html_path)
    finally:
        tmp_html.unlink(missing_ok=True)
        tmp_pdf.unlink(missing_ok=True)
        shutil.rmtree(chrome_profile, ignore_errors=True)


def render_docx_atomic(
    full_html: str,
    docx_path: Path,
    *,
    market: str = "a_share",
    footer_title: str = "全球股市深度投研报告",
) -> None:
    """Compile pure-Python ECMA-376 native .docx with 2x Retina PIL-cropped charts (zero textutil)."""
    from docx_embed import build_native_docx_from_html

    build_native_docx_from_html(
        full_html,
        docx_path,
        market=market,
        footer_title=footer_title,
    )
