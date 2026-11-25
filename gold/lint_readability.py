#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated 7-Gate Readability, Mathematical Accuracy, PDF & Native OOXML Integrity Linter (V2.2).
Supports dedicated master_snapshot.json via <!-- MASTER_BASELINE {...} --> and daily data_snapshot.json.

Usage:
  python3 lint_readability.py <file1.md> [file2.md ...] [--precheck] [--strict]
  --precheck  Skip Gate 6 (PDF/DOCX artifact verification) for fast pre-compile Gate 0–5 checks.
  --strict    Fail with exit code 1 on any warning in addition to errors.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DAILY_SNAPSHOT_PATH = BASE_DIR / "data_snapshot.json"
MASTER_SNAPSHOT_PATH = BASE_DIR / "master_snapshot.json"
MARKET_CALENDAR_PATH = BASE_DIR / "market_calendar.json"
SCORECARD_PATH = BASE_DIR / "daily" / "SCORECARD.md"
LATEST_MOBILE_HTML_PATH = BASE_DIR / "daily" / "latest_gold.html"
RSI_PLAYBOOK_PATH = BASE_DIR / "daily" / "RSI_PLAYBOOK.md"
RSI_METRICS_PATH = BASE_DIR / "daily" / "rsi_metrics.json"
SCORECARD_BANNED_RE = re.compile(
    r"(?:Subagent|子代理|\bRSI\b|Meta-RSI|Recursive\s+Self-Improvement|"
    r"\bTier\s*[ABC](?:\b|/[ABC])|\bV[267]\.\d+\b|"
    r"RSI_PLAYBOOK\.md|rsi_metrics\.json|sidecar\.json|DAILY_FORMAT_SPEC\.md|"
    r"build_daily\.py|build_report\.py|lint_readability\.py|docx_embed\.py|"
    r"63\s*路|红队|法证|\bGate\s*[0-6]\b)",
    flags=re.IGNORECASE,
)
RSI_REQUIRED_SCORE_KEYS = (
    "data_freshness_and_zero_hallucination",
    "prior_forecast_calibration",
    "plain_language_and_strict_readability",
    "visual_layout_and_pagination",
    "research_efficiency_and_source_quality",
    "engine_and_guardrail_reliability",
)

BANNED_HYPE_WORDS = [
    "神准", "分毫不差", "100%胜率", "100% 胜率", "无情推翻", "核雷",
    "拉爆", "血洗", "焊死", "史诗级", "史诗轧空", "彻底打脸", "惊天验证",
]

# Case-insensitive word-boundary ASCII Wall Street / internal code tokens banned in Layer 0–1
BANNED_LAYER01_ASCII = [
    "DFII10", "2Y-FF", "2Y−FF", "T10YIE", "EFFR", "SOFR", "IORB", "HY OAS", "CCC OAS",
    "ON RRP", "au2702", "OGZ26", "GCX26", "GCZ26", "GCG27", "BCOM", "GSCI",
    "Subagent", "Daniel Ghali", "Michael Hsueh", "Call Wall", "Put Wall",
    "stop-through", "IFRS 9", "HQLA", "GDX/GLD", "CDX IG",
    "OAT", "JGB", "DXY", "VIX", "GLD", "GDX", "KRE", "SRF", "CDS", "OIS", "CFTC", "COT",
    "V2.0", "V2.1", "V2.2", "V6.0", "V6.1", "V7.0", "V7.1", "V7.2",
]
_BANNED_ASCII_PATTERNS = [
    (tok, re.compile(rf"(?<![A-Za-z0-9_]){re.escape(tok)}(?![A-Za-z0-9_])", re.IGNORECASE))
    for tok in BANNED_LAYER01_ASCII
]

# CJK / mixed-script jargon & meta-noise banned in Layer 0–1
BANNED_LAYER01_LITERAL = [
    "子代理", "63 路", "63路", "负 Gamma", "负Gamma", "R²=", "R² =",
    "梭哈", "短线波段", "放鹰", "鹰派", "鸽派", "提保", "上影线", "即征即退",
    "高弹性", "六灯", "逼空", "轧空", "做T", "做 T",
]

PERMANENT_FACT_GUARDS = [
    ("912 元/克", "表 6.1 汇率算错旧值（6.30×$4,500 实为 911 元/克）"),
    ("30% + 40% + 30%", "A 类建仓比例旧冲突口径（全系统统一 30% + 45% + 25%）"),
    ("7 天后免赎回费", "场外 C 类错误赎回费（工银/华安/博时 C 均满 30 天才免赎回费）"),
    ("7天后免赎回费", "场外 C 类错误赎回费（工银/华安/博时 C 均满 30 天才免赎回费）"),
    ("去年三季度财报赚的是 4,280", "年份硬伤（应为今年三季度 / 2026 年三季度）"),
]

# Snapshot-date-bound guards (only active on 2026-11-24 baseline; auto-disabled on subsequent trading days)
DATE_BOUND_STALE_GUARDS_20261124 = [
    ("108.8%", "地上黄金/M2 过时旧值（11/24 基线按 $3,635 更新为 111.9%）"),
    ("超 310 吨", "险资额度过时旧值（11/24 基线按 786/778 元/克更新）"),
    ("省 270", "渠道省钱旧口径（11/24 午报基线为省 283 元/克，早报基线为省 267 元/克）"),
    ("省270", "渠道省钱旧口径（11/24 午报基线为省 283 元/克，早报基线为省 267 元/克）"),
    ("+2.78%", "现货涨幅跨源旧值（11/24 单一源 3534.64→3635.24 = +2.85%）"),
    ("布油收涨至 92.57", "11/24 过时油价（官结 89.37）"),
]

KNOWN_DIRECTIVES = {
    "DAILY_META",
    "DAILY_VERDICT",
    "DAILY_SIGNAL_NOISE",
    "DAILY_PERSONA",
    "DAILY_GLOSSARY",
    "DAILY_LAYER_BADGE",
    "DAILY_TRUST_BAR",
    "DAILY_CHART_TIMELINE",
    "DAILY_CHART_SWITCH",
    "DAILY_CHART_CROSS",
}

ANY_DAILY_DIRECTIVE_RE = re.compile(r"<!--\s*(DAILY_[A-Z0-9_]+)\s*(.*?)\s*-->", re.DOTALL)
MASTER_BASELINE_RE = re.compile(r"<!--\s*MASTER_BASELINE\s*(\{.*?\})\s*-->", re.DOTALL)

REQUIRED_KEYS = {
    "DAILY_META": ["tag", "kpis"],
    "DAILY_VERDICT": ["level", "headline"],
    "DAILY_SIGNAL_NOISE": ["signals", "noises"],
    "DAILY_PERSONA": ["cards"],
    "DAILY_GLOSSARY": ["terms"],
    "DAILY_LAYER_BADGE": ["label"],
    "DAILY_TRUST_BAR": ["items"],
    "DAILY_CHART_TIMELINE": ["points"],
    "DAILY_CHART_SWITCH": ["gauges", "checks"],
    "DAILY_CHART_CROSS": ["items"],
}

_STYLE_SKIP_KEYS = {
    "accent", "color", "fill", "text_color", "align", "anchor", "label_pos",
    "tone", "group", "status_color", "unit_prefix", "unit_suffix", "level",
}

# Unicode-safe parallel score regex (catches decimal 0.0/6..6.5/6, integer 0/6..6/6, and fullwidth ／6)
PARALLEL_SCORE_RE = re.compile(r"(?<![0-9.])[0-6](?:\.[05])?\s*[/／]\s*6(?![0-9])")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
RAW_HTML_LEAK_RE = re.compile(
    r"</?(?:div|span|table|thead|tbody|tr|td|th|svg|rect|path|circle|line|polygon|polyline|"
    r"p|ul|ol|li|script|style|iframe|img|h[1-6]|font|center)\b",
    re.IGNORECASE,
)
EXCL_RE = re.compile(r"[!！‼⁉❗❕]")
LIST_OR_BLOCK_RE = re.compile(r"^(?:#|\||[-*•]\s|>\s?|\d+\.\s|---+$)")


def _vis_width(s: str) -> float:
    return sum(1.0 if ord(ch) > 127 else 0.55 for ch in str(s).strip())


def find_layer01_end(raw_md: str) -> int:
    """Locate character offset in raw Markdown where Layer 0-1 ends and Layer 2 begins."""
    patterns = [
        r"^#\s*第二部分",
        r"^##\s*专题一",
        r"^##\s*周末专题",
        r'<!--\s*DAILY_LAYER_BADGE\s*\{[^}]*"tone"\s*:\s*"deep"',
    ]
    earliest = len(raw_md)
    for pat in patterns:
        m = re.search(pat, raw_md, re.MULTILINE | re.DOTALL)
        if m and m.start() < earliest:
            earliest = m.start()
    return earliest


def flatten_json_strings(obj, skip_style_keys: bool = True) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return "\n".join(flatten_json_strings(x, skip_style_keys=skip_style_keys) for x in obj)
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            if skip_style_keys and k in _STYLE_SKIP_KEYS:
                continue
            parts.append(flatten_json_strings(v, skip_style_keys=skip_style_keys))
        return "\n".join(parts)
    return ""


def _parse_num_safe(val) -> float:
    return float(str(val).replace("\u2212", "-").replace("\u2013", "-").replace(",", "").replace("%", "").replace("+", "").strip())


def validate_snapshot_file(snap_path: Path, errors: list[str], warnings: list[str]) -> dict | None:
    label = snap_path.name
    if not snap_path.exists():
        warnings.append(f"[Gate 5 数据源缺失] 未找到 {label}")
        return None
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"[Gate 5 数据源损坏] {label} 解析失败: {exc}")
        return None

    # Alert level, SSOT new_buy_allowed & A-class tranche invariants
    if snap.get("daily_alert_level") not in (None, "L0", "L1", "L2"):
        errors.append(f"[Gate 5 紧迫度非法] {label}: daily_alert_level={snap.get('daily_alert_level')} 非 L0/L1/L2")
    if "new_buy_allowed" in snap:
        nba = snap["new_buy_allowed"]
        if not isinstance(nba, bool):
            errors.append(f"[Gate 5 SSOT 开关非法] {label}: new_buy_allowed 必须为布尔值（实得 {nba!r}）")
        elif snap.get("tier_code"):
            expected_nba = str(snap["tier_code"]).strip() != "Tier 0"
            if nba != expected_nba:
                errors.append(
                    f"[Gate 5 SSOT 开关冲突] {label}: tier_code='{snap['tier_code']}' 与 new_buy_allowed={nba} 矛盾"
                )
    if snap.get("a_class_tranche_split") and str(snap["a_class_tranche_split"]) != "30% + 45% + 25%":
        errors.append(f"[Gate 5 分批比例错] {label}: a_class_tranche_split={snap['a_class_tranche_split']} != '30% + 45% + 25%'")

    # Tier 1 gates invariant
    gates = snap.get("tier1_gates")
    if isinstance(gates, list):
        if len(gates) != 4:
            errors.append(f"[Gate 5 红绿灯数量错] {label}: tier1_gates 应为 4 项，实际 {len(gates)} 项")
        passed_cnt = sum(1 for g in gates if bool(g.get("passed", False)))
        if "tier1_passed" in snap and int(snap["tier1_passed"]) != passed_cnt:
            errors.append(f"[Gate 5 红绿灯计数冲突] {label}: tier1_passed={snap['tier1_passed']} != sum(passed)={passed_cnt}")
        if "tier1_total" in snap and int(snap["tier1_total"]) != len(gates):
            errors.append(f"[Gate 5 红绿灯总数冲突] {label}: tier1_total={snap['tier1_total']} != {len(gates)}")

    # Legacy dated cross_ratios key check
    for k in snap:
        if re.match(r"^cross_ratios_\d{4}$", k):
            warnings.append(f"[Gate 5 遗留日期键] {label} 仍含过时键 '{k}'，应统一使用无日期键 'cross_ratios'")

    # Spot NY close % self-consistency
    try:
        ny_close = float(snap["spot_gold_ny_close_usd"])
        prev_raw = snap.get("spot_gold_prev_close_usd", snap.get("spot_gold_fri_close_usd"))
        if prev_raw is not None:
            prev_close = float(prev_raw)
            chg_pct = float(snap["spot_gold_ny_change_pct"])
            calc_chg = ((ny_close / prev_close) - 1.0) * 100.0
            if abs(chg_pct - calc_chg) > 0.05:
                errors.append(
                    f"[Gate 5 快照算术冲突] {label}: spot_gold_ny_change_pct={chg_pct} 与 {prev_close}->{ny_close} 精确涨幅 {calc_chg:.2f}% 偏差超过 0.05%"
                )
    except (KeyError, ValueError, ZeroDivisionError):
        pass

    ch = snap.get("rmb_channels", {})
    if ch:
        brand = int(ch["brand_store_rmb"])
        exp_save = brand - int(ch["bank_bar_plus_craft_rmb"])
        if int(ch["wedding_save_per_g_rmb"]) != exp_save:
            errors.append(f"[Gate 5 快照渠道算术错] {label}: wedding_save_per_g_rmb={ch['wedding_save_per_g_rmb']} != {exp_save}")
        if int(ch["wedding_save_50g_rmb"]) != exp_save * 50:
            errors.append(f"[Gate 5 快照 50g 算术错] {label}: wedding_save_50g_rmb={ch['wedding_save_50g_rmb']} != {exp_save * 50}")
        if "wedding_save_pct" in ch and brand > 0:
            exp_pct = (exp_save / brand) * 100.0
            if abs(float(ch["wedding_save_pct"]) - exp_pct) > 0.15:
                errors.append(f"[Gate 5 省钱百分比偏差] {label}: wedding_save_pct={ch['wedding_save_pct']} != {exp_pct:.1f}%")

    cr = snap.get("cross_ratios") or snap.get("cross_ratios_1124")
    if cr:
        spot = float(snap["spot_gold_ny_close_usd"])
        checks = [
            ("gold_wti_ratio", spot / float(snap["wti_settle_usd"]), 0.15),
            ("gold_brent_ratio", spot / float(snap["brent_settle_usd"]), 0.15),
            ("gold_silver_ratio", spot / float(snap["spot_silver_usd"]), 0.15),
            ("gold_spx_ratio", spot / float(snap["spx_close"]), 0.015),
        ]
        if snap.get("spot_platinum_usd"):
            checks.append(("gold_platinum_ratio", spot / float(snap["spot_platinum_usd"]), 0.05))
        for k, expected, tol in checks:
            if k in cr and abs(float(cr[k]) - expected) > tol:
                errors.append(f"[Gate 5 跨资产比值偏差] {label}: {k}={cr[k]} 与精确比值 {expected:.3f} 偏差超过 {tol}")
    return snap


def check_pdf_and_docx_artifacts(md_path: Path, raw_md: str, errors: list[str], warnings: list[str]) -> None:
    """Gate 6: Verify both PDF & Native OOXML DOCX freshness, headers, ECMA-376 order, rels, and embedded PNGs."""
    pdf_path = md_path.with_suffix(".pdf")
    docx_path = md_path.with_suffix(".docx")
    md_mtime = md_path.stat().st_mtime

    expected_charts = 0
    for m in re.finditer(r"<!--\s*(DAILY_CHART_(?:TIMELINE|SWITCH|CROSS)|CHART_1_AND_2|CHART_\d+)\b", raw_md):
        tok = m.group(1)
        expected_charts += 2 if tok == "CHART_1_AND_2" else 1

    # PDF checks
    if not pdf_path.exists():
        if expected_charts > 0:
            warnings.append(f"[Gate 6 PDF 未生成] 未检测到同名 {pdf_path.name}，请先运行编译脚本")
    else:
        pdf_stat = pdf_path.stat()
        if pdf_stat.st_size < 10240:
            errors.append(f"[Gate 6 PDF 异常过小] {pdf_path.name} 仅 {pdf_stat.st_size} 字节")
        else:
            with open(pdf_path, "rb") as fp:
                if fp.read(5) != b"%PDF-":
                    errors.append(f"[Gate 6 PDF 文件头损坏] {pdf_path.name} 非合法 PDF 文件")
        if pdf_stat.st_mtime < md_mtime - 2.0:
            warnings.append(f"[Gate 6 PDF 陈旧] {pdf_path.name} 修改时间早于 {md_path.name}，请重新编译")

    # Mobile responsive HTML check for daily reports
    is_daily_report = (
        md_path.resolve().parent == (BASE_DIR / "daily").resolve()
        and re.match(r"^\d{4}-\d{2}-\d{2}_", md_path.name) is not None
    )
    if is_daily_report:
        if not LATEST_MOBILE_HTML_PATH.exists():
            errors.append(
                f"[Gate 6 手机端 HTML 缺失] 未检测到 daily/{LATEST_MOBILE_HTML_PATH.name}，请运行 build_daily.py 重新编译"
            )
        else:
            mob_size = LATEST_MOBILE_HTML_PATH.stat().st_size
            if mob_size < 5120:
                errors.append(
                    f"[Gate 6 手机端 HTML 异常过小] daily/{LATEST_MOBILE_HTML_PATH.name} 仅 {mob_size} 字节（要求 ≥5KB）"
                )
            else:
                mob_text = LATEST_MOBILE_HTML_PATH.read_text(encoding="utf-8", errors="replace")
                if '<meta name="viewport"' not in mob_text:
                    errors.append(
                        f"[Gate 6 手机端 HTML 缺视口声明] daily/{LATEST_MOBILE_HTML_PATH.name} 缺少 <meta name=\"viewport\""
                    )

    if not docx_path.exists():
        if expected_charts > 0:
            warnings.append(f"[Gate 6 DOCX 未生成] 未检测到同名 {docx_path.name}，请先运行编译脚本")
        return

    if docx_path.stat().st_mtime < md_mtime - 2.0:
        warnings.append(f"[Gate 6 DOCX 陈旧] {docx_path.name} 修改时间早于 {md_path.name}，请重新编译")

    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            names = set(zf.namelist())
            required_parts = [
                "[Content_Types].xml",
                "_rels/.rels",
                "word/document.xml",
                "word/_rels/document.xml.rels",
                "word/styles.xml",
                "word/settings.xml",
                "word/footer1.xml",
            ]
            for rp in required_parts:
                if rp not in names:
                    errors.append(f"[Gate 6 DOCX 缺核心部件] {docx_path.name} 缺少 {rp}")
                    return

            xml_roots = {}
            for name in names:
                if name.endswith((".xml", ".rels")):
                    try:
                        xml_roots[name] = ET.fromstring(zf.read(name))
                    except ET.ParseError as exc:
                        errors.append(f"[Gate 6 DOCX 非法 XML] {docx_path.name}:{name} 解析失败: {exc}")
                        return

            doc_str = zf.read("word/document.xml").decode("utf-8")
            ct_root = xml_roots["[Content_Types].xml"]
            doc_root = xml_roots["word/document.xml"]
            rels_root = xml_roots["word/_rels/document.xml.rels"]
            ftr_root = xml_roots["word/footer1.xml"]

            w_ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            r_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
            wp_ns = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
            a_ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
            pic_ns = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"

            # 1. Native tables exist (never flattened by textutil!)
            tbls = doc_root.findall(f".//{w_ns}tbl")
            if not tbls:
                errors.append(f"[Gate 6 DOCX 表格丢失] {docx_path.name} 中 <w:tbl> 数量为 0（疑似误用 textutil 退化）！")

            # 2. Zero invalid Word 2003 <w:sz-cs>
            if "<w:sz-cs" in doc_str or "<w:sz-cs" in zf.read("word/styles.xml").decode("utf-8"):
                errors.append(f"[Gate 6 DOCX 非法标签] {docx_path.name} 含有不合规的 <w:sz-cs> 标签")

            # 3. Zero leaked chart markers
            if "___DOCX_CHART_" in doc_str:
                errors.append(f"[Gate 6 DOCX 占位泄露] {docx_path.name} 残留未替换的 ___DOCX_CHART_ 占位符")

            # 4. <w:sectPr> strictly LAST child of <w:body>
            body = doc_root.find(f"{w_ns}body")
            if body is None or len(body) == 0 or body[-1].tag != f"{w_ns}sectPr":
                errors.append(f"[Gate 6 DOCX 结构错位] {docx_path.name} 的 <w:sectPr> 不是 <w:body> 最后一个子元素")

            # 5. [Content_Types].xml: ALL <Default> before ALL <Override>, and all Override PartNames exist
            seen_override = False
            for child in ct_root:
                tag_local = child.tag.split("}")[-1]
                if tag_local == "Override":
                    seen_override = True
                    pn = child.attrib.get("PartName", "").lstrip("/")
                    if pn and pn not in names:
                        errors.append(f"[Gate 6 Content_Types 悬空覆盖] {docx_path.name} 声明了不存在的 /{pn}")
                elif tag_local == "Default" and seen_override:
                    errors.append(f"[Gate 6 Content_Types 顺序错] {docx_path.name} 中 <Default> 出现在 <Override> 之后")
                    break

            # 6. ECMA-376 child ordering: tblBorders before tblLayout; positive tblGrid <= 9638; footer pBdr before jc
            for t_idx, tbl in enumerate(tbls):
                tblpr = tbl.find(f"{w_ns}tblPr")
                if tblpr is not None:
                    tags = [c.tag.split("}")[-1] for c in tblpr]
                    if "tblBorders" in tags and "tblLayout" in tags and tags.index("tblBorders") > tags.index("tblLayout"):
                        errors.append(f"[Gate 6 OOXML 序错] {docx_path.name} 第 {t_idx+1} 表 tblBorders 出现在 tblLayout 之后")
                        break
                tgrid = tbl.find(f"{w_ns}tblGrid")
                if tgrid is not None:
                    col_ws = [int(gc.attrib.get(f"{w_ns}w", "0")) for gc in tgrid.findall(f"{w_ns}gridCol")]
                    if any(w <= 0 for w in col_ws) or sum(col_ws) > 9638:
                        errors.append(f"[Gate 6 DOCX 表宽越界] {docx_path.name} 第 {t_idx+1} 表 tblGrid 异常: {col_ws}")
                        break

            for ppr in ftr_root.findall(f".//{w_ns}pPr"):
                ftags = [c.tag.split("}")[-1] for c in ppr]
                if "pBdr" in ftags and "jc" in ftags and ftags.index("pBdr") > ftags.index("jc"):
                    errors.append(f"[Gate 6 页脚 OOXML 序错] {docx_path.name}:footer1.xml 中 <w:pBdr> 出现在 <w:jc> 之后")
                    break

            for ppr in doc_root.findall(f".//{w_ns}pPr"):
                ptags = [c.tag.split("}")[-1] for c in ppr]
                if "keepNext" in ptags and "pageBreakBefore" in ptags and ptags.index("keepNext") > ptags.index("pageBreakBefore"):
                    errors.append(f"[Gate 6 段落 OOXML 序错] {docx_path.name} 存在 pageBreakBefore 出现在 keepNext 之前")
                    break

            # 7. Unique wp:docPr/@id AND pic:cNvPr/@id
            docpr_ids = [el.attrib.get("id") for el in doc_root.findall(f".//{wp_ns}docPr")]
            if len(docpr_ids) != len(set(docpr_ids)):
                errors.append(f"[Gate 6 DOCX ID 冲突] {docx_path.name} 存在重复的 wp:docPr/@id: {docpr_ids}")
            cnvpr_ids = [el.attrib.get("id") for el in doc_root.findall(f".//{pic_ns}cNvPr")]
            if len(cnvpr_ids) != len(set(cnvpr_ids)):
                errors.append(f"[Gate 6 DOCX pic ID 冲突] {docx_path.name} 存在重复的 pic:cNvPr/@id: {cnvpr_ids}")

            # 8. Validate ALL r:id relationships (hyperlinks, footerReference, blips) + PNG magic header
            rel_map = {el.attrib.get("Id"): el.attrib.get("Target") for el in rels_root}
            for hl in doc_root.findall(f".//{w_ns}hyperlink"):
                rid = hl.attrib.get(f"{r_ns}id")
                if rid and rid not in rel_map:
                    errors.append(f"[Gate 6 DOCX 超链接断链] {docx_path.name} hyperlink 引用无效 rId={rid}")
            for fr in doc_root.findall(f".//{w_ns}footerReference"):
                rid = fr.attrib.get(f"{r_ns}id")
                if rid and rid not in rel_map:
                    errors.append(f"[Gate 6 DOCX 页脚断链] {docx_path.name} footerReference 引用无效 rId={rid}")

            blips = doc_root.findall(f".//{a_ns}blip")
            valid_imgs = 0
            for b in blips:
                rid = b.attrib.get(f"{r_ns}embed")
                if not rid or rid not in rel_map:
                    errors.append(f"[Gate 6 DOCX 断链图片] {docx_path.name} 存在无效图片引用 rId={rid}")
                    continue
                target_path = f"word/{rel_map[rid]}"
                if target_path not in names:
                    errors.append(f"[Gate 6 DOCX 缺图文件] {docx_path.name} 缺失 {target_path}")
                    continue
                img_bytes = zf.read(target_path)
                if len(img_bytes) < 2048 or not img_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                    errors.append(f"[Gate 6 DOCX 图损/空白] {docx_path.name}:{target_path} 非有效 PNG 或体积不足 2KB")
                    continue
                valid_imgs += 1

            if expected_charts > 0 and valid_imgs < expected_charts:
                errors.append(
                    f"[Gate 6 DOCX 丢图] Markdown 含 {expected_charts} 张图表，但 {docx_path.name} 仅有效内嵌 {valid_imgs} 张"
                )
    except Exception as exc:
        errors.append(f"[Gate 6 DOCX 校验异常] 无法解析 {docx_path.name}: {exc}")


def _find_banned_layer01_tokens(text: str) -> list[str]:
    hits: list[str] = []
    for tok, pat in _BANNED_ASCII_PATTERNS:
        if pat.search(text):
            hits.append(tok)
    for tok in BANNED_LAYER01_LITERAL:
        if tok in text:
            hits.append(tok)
    return hits


def _validate_directive_schema(kind: str, parsed: dict, errors: list[str], warnings: list[str]) -> None:
    if not isinstance(parsed, dict):
        errors.append(f"[Gate 0 Schema 非对象] <!-- {kind} --> 顶层必须为 JSON 对象")
        return
    for req_k in REQUIRED_KEYS.get(kind, []):
        if req_k not in parsed:
            errors.append(f"[Gate 0 Schema 缺必填键] <!-- {kind} --> 缺少字段 '{req_k}'")

    if kind == "DAILY_META":
        kpis = parsed.get("kpis")
        if isinstance(kpis, list):
            if len(kpis) != 6:
                warnings.append(f"[Gate 0 KPI 数量] DAILY_META.kpis 建议为 6 张卡，实际 {len(kpis)} 张")
            for idx, k in enumerate(kpis, 1):
                if not isinstance(k, dict) or not all(f in k for f in ("label", "val", "sub")):
                    errors.append(f"[Gate 0 KPI 结构错] DAILY_META.kpis[{idx}] 缺少 label/val/sub")
                elif _vis_width(k.get("sub", "")) > 17.5:
                    warnings.append(f"[Gate 0 KPI sub 偏长] DAILY_META.kpis[{idx}].sub='{k['sub']}' 视觉宽 {_vis_width(k['sub']):.1f} > 17.5 汉字当量")
    elif kind == "DAILY_VERDICT":
        lvl = str(parsed.get("level", "")).upper()
        if lvl not in ("L0", "L1", "L2"):
            errors.append(f"[Gate 0 紧迫度非法] DAILY_VERDICT.level='{lvl}' 必须为 L0/L1/L2")
        if "🟢" in str(parsed.get("badge", "")):
            errors.append("[Gate 0 禁用绿牌] DAILY_VERDICT.badge 严禁使用绿色 🟢（防止与买金绿灯撞色）")
        if not all(k in parsed for k in ("traffic_light", "bullets", "risk_line")) or not isinstance(parsed.get("bullets"), list):
            errors.append("[Gate 0 VERDICT 结构错] DAILY_VERDICT 须含 traffic_light/risk_line 及数组 bullets")
    elif kind == "DAILY_SIGNAL_NOISE":
        for sn_k in ("signals", "noises"):
            arr = parsed.get(sn_k)
            if not isinstance(arr, list) or any(not isinstance(it, dict) or not all(f in it for f in ("head", "body")) for it in arr):
                errors.append(f"[Gate 0 信号卡项错] DAILY_SIGNAL_NOISE.{sn_k} 须为含 head/body 对象的数组")
        sigs = parsed.get("signals", [])
        if isinstance(sigs, list) and len(sigs) > 2:
            warnings.append(f"[Gate 0 信号超标] DAILY_SIGNAL_NOISE.signals 有 {len(sigs)} 件（规范建议 0–2 件）")
    elif kind == "DAILY_PERSONA":
        cards = parsed.get("cards")
        if not isinstance(cards, list) or not cards or any(not isinstance(c, dict) or not all(f in c for f in ("group", "heading", "actions")) or not isinstance(c.get("actions"), list) for c in cards):
            errors.append("[Gate 0 读者卡项错] DAILY_PERSONA.cards 须为非空数组且每项含 group/heading/数组 actions")
    elif kind == "DAILY_GLOSSARY":
        terms = parsed.get("terms")
        if not isinstance(terms, list) or not terms or any(not isinstance(t, dict) or not all(f in t for f in ("term", "plain")) for t in terms):
            errors.append("[Gate 0 词典项错] DAILY_GLOSSARY.terms 须为非空数组且每项含 term/plain")
    elif kind == "DAILY_LAYER_BADGE":
        tone = parsed.get("tone")
        if tone is not None and tone not in ("deep", "pro"):
            errors.append(f"[Gate 0 分层标非法] DAILY_LAYER_BADGE.tone='{tone}' 必须为 deep 或 pro")
    elif kind == "DAILY_CHART_TIMELINE":
        if "zones" in parsed and "highlight_zones" not in parsed:
            errors.append("[Gate 0 时间轴错键] DAILY_CHART_TIMELINE 请使用 highlight_zones 而非 zones")
        pts = parsed.get("points")
        if not isinstance(pts, list) or not pts:
            errors.append("[Gate 0 时间轴空] DAILY_CHART_TIMELINE.points 不能为空")
        else:
            for idx, p in enumerate(pts):
                if not isinstance(p, dict) or "val" not in p:
                    errors.append(f"[Gate 0 时间轴缺值] points[{idx}] 缺少 val")
                else:
                    try:
                        float(p["val"])
                    except (TypeError, ValueError):
                        errors.append(f"[Gate 0 时间轴非数字] points[{idx}].val={p['val']}")
        if "y_min" in parsed and "y_max" in parsed:
            try:
                if float(parsed["y_min"]) >= float(parsed["y_max"]):
                    errors.append("[Gate 0 纵轴颠倒] DAILY_CHART_TIMELINE y_min 必须小于 y_max")
            except (TypeError, ValueError):
                errors.append("[Gate 0 纵轴非数字] DAILY_CHART_TIMELINE y_min/y_max 须为数字")
    elif kind == "DAILY_CHART_SWITCH":
        checks = parsed.get("checks", [])
        if isinstance(checks, list) and len(checks) != 4:
            errors.append(f"[Gate 0 四步红绿灯数量错] DAILY_CHART_SWITCH.checks 应为 4 项，实际 {len(checks)} 项")
        if not isinstance(checks, list) or any(not isinstance(c, dict) or not all(f in c for f in ("name", "passed", "line1", "line2")) for c in checks):
            errors.append("[Gate 0 红绿灯项错] DAILY_CHART_SWITCH.checks 每项须含 name/passed/line1/line2")
        for idx, g in enumerate(parsed.get("gauges", []), 1):
            if not isinstance(g, dict) or not all(f in g for f in ("label", "value_text", "pct")) or ("safe_pct" in g and "threshold_pct" not in g):
                errors.append(f"[Gate 0 水位尺项错] gauges[{idx}] 须含 label/value_text/pct（且用 threshold_pct 非 safe_pct）")
                continue
            try:
                pct = float(g.get("pct", -1))
                if not (0.0 <= pct <= 100.0):
                    errors.append(f"[Gate 0 水位尺越界] gauges[{idx}].pct={pct} 超出 0..100")
            except (TypeError, ValueError):
                errors.append(f"[Gate 0 水位尺非数字] gauges[{idx}].pct 非法")
    elif kind == "DAILY_CHART_CROSS":
        items = parsed.get("items", [])
        if not isinstance(items, list) or not items:
            errors.append("[Gate 0 跨资产图空] DAILY_CHART_CROSS.items 不能为空")
        else:
            for idx, it in enumerate(items, 1):
                if not isinstance(it, dict) or not all(f in it for f in ("label", "pct")):
                    errors.append(f"[Gate 0 跨资产项错] DAILY_CHART_CROSS.items[{idx}] 须含 label/pct")
                    continue
                lw = _vis_width(str(it["label"]))
                if lw > 9.5:
                    errors.append(f"[Gate 0 图2标签撞栏] items[{idx}].label='{it['label']}' 宽 {lw:.1f} > 9.5（请压至 ≤8.5）")
                elif lw > 9.0:
                    warnings.append(f"[Gate 0 图2标签偏宽] items[{idx}].label='{it['label']}' 宽 {lw:.1f} > 9.0（建议 ≤8.5）")
                try:
                    _parse_num_safe(it["pct"])
                except Exception:
                    errors.append(f"[Gate 0 涨跌幅非数字] DAILY_CHART_CROSS.items[{idx}].pct 非法")
        if any(not isinstance(ri, dict) or not all(f in ri for f in ("label", "detail")) for ri in parsed.get("reverse_items", [])):
            errors.append("[Gate 0 反向指标项错] DAILY_CHART_CROSS.reverse_items 每项须含 label/detail")


def _strip_comments_keep_lines(s: str) -> str:
    return HTML_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), s)


def _strip_code_and_neq(s: str) -> str:
    t = re.sub(r"```.*?```", "", s, flags=re.DOTALL)
    t = re.sub(r"`[^`]+`", "", t)
    return t.replace("!=", "")


def check_file(
    md_path: Path,
    daily_snap: dict | None,
    master_snap: dict | None,
    snap_cache: dict[Path, dict | None],
    precheck: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    raw = md_path.read_text(encoding="utf-8")

    # Select dedicated snapshot for this file (MASTER_BASELINE -> master_snapshot.json, else data_snapshot.json)
    baseline_m = MASTER_BASELINE_RE.search(raw)
    baseline_meta: dict = {}
    if baseline_m:
        try:
            baseline_meta = json.loads(baseline_m.group(1))
        except json.JSONDecodeError as exc:
            errors.append(f"[Gate 0 MASTER_BASELINE JSON 错] {exc}")
        target_snap_path = BASE_DIR / str(baseline_meta.get("snapshot", "master_snapshot.json"))
        if target_snap_path not in snap_cache:
            snap_cache[target_snap_path] = validate_snapshot_file(target_snap_path, errors, warnings)
        snap = snap_cache[target_snap_path]
        if snap and baseline_meta.get("as_of_short") and str(snap.get("as_of_short")) != str(baseline_meta["as_of_short"]):
            errors.append(
                f"[Gate 5 主报告基线锁冲突] MASTER_BASELINE.as_of_short='{baseline_meta['as_of_short']}' "
                f"!= {target_snap_path.name}.as_of_short='{snap.get('as_of_short')}'"
            )
    else:
        snap = daily_snap

    layer01_end = find_layer01_end(raw)
    if len(raw) > 3000 and layer01_end == len(raw):
        errors.append("[Gate 0 缺分层边界] 未检测到 Layer 2 边界（需以 `# 第二部分` / `## 专题一` / `## 周末专题` 或 `DAILY_LAYER_BADGE(deep)` 起头）")

    raw_l01 = raw[:layer01_end]
    layer01_vis = _strip_comments_keep_lines(raw_l01)
    full_vis = _strip_comments_keep_lines(raw)

    # Gate 0: Catch & Schema-validate ALL DAILY_* directives (including typos & malformed payloads!)
    daily_meta: dict = {}
    l01_widget_texts: list[tuple[str, str]] = []
    all_widget_texts: list[tuple[str, str]] = []
    for m in ANY_DAILY_DIRECTIVE_RE.finditer(raw):
        kind, blob = m.group(1), m.group(2).strip()
        if kind not in KNOWN_DIRECTIVES:
            errors.append(f"[Gate 0 未知组件指令] 发现非法/拼写错误指令 <!-- {kind} -->")
            continue
        if not blob.startswith("{") or not blob.endswith("}"):
            errors.append(f"[Gate 0 JSON 格式错] <!-- {kind} --> 载荷不是合法 JSON 对象")
            continue
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError as exc:
            errors.append(f"[Gate 0 JSON 语法错] <!-- {kind} --> 解析失败: {exc}")
            continue
        _validate_directive_schema(kind, parsed, errors, warnings)
        if kind == "DAILY_META":
            daily_meta = parsed
        flat = flatten_json_strings(parsed, skip_style_keys=True)
        all_widget_texts.append((kind, flat))
        if m.start() < layer01_end or kind in ("DAILY_META", "DAILY_VERDICT", "DAILY_SIGNAL_NOISE"):
            l01_widget_texts.append((kind, flat))

    # Gate 1: Zero bare Wall Street codes / internal meta-noise / raw HTML leaks in Layer 0-1
    found_tokens = _find_banned_layer01_tokens(layer01_vis)
    if found_tokens:
        errors.append(f"[Gate 1 术语/自嗨逃逸] Layer 0–1 正文出现禁止词条: {', '.join(found_tokens)}")
    for kind, txt in l01_widget_texts:
        bad = _find_banned_layer01_tokens(txt)
        if bad:
            errors.append(f"[Gate 1 组件术语逃逸] Layer 0–1 {kind} 出现禁止词条: {', '.join(bad)}")

    # Raw HTML leakage in visible Markdown AND widget JSON payloads
    no_code_vis = re.sub(r"```.*?```", "", full_vis, flags=re.DOTALL)
    no_code_vis = re.sub(r"`[^`]+`", "", no_code_vis)
    leaks = RAW_HTML_LEAK_RE.findall(no_code_vis)
    if leaks:
        errors.append(f"[Gate 1 原始 HTML 泄露] 正文出现未转义 HTML 标签: {', '.join(sorted(set(leaks)))}")
    for kind, txt in all_widget_texts:
        wleaks = RAW_HTML_LEAK_RE.findall(txt)
        if wleaks:
            errors.append(f"[Gate 1 组件 HTML 泄露] {kind} 含有非法 HTML 标签: {', '.join(sorted(set(wleaks)))}")

    # Gate 2: Calm doctor tone (markdown-stripped hype scan) & zero exclamation marks in Layer 0-1
    full_combined = full_vis + "\n" + "\n".join(t for _, t in all_widget_texts)
    full_stripped_md = re.sub(r"\*\*|\*", "", full_combined)
    found_hype = [w for w in BANNED_HYPE_WORDS if w in full_stripped_md]
    if found_hype:
        errors.append(f"[Gate 2 夸张/煽动词] 全文出现禁用词: {', '.join(found_hype)}")

    excl_l01_vis = len(EXCL_RE.findall(_strip_code_and_neq(layer01_vis)))
    if excl_l01_vis > 0:
        errors.append(f"[Gate 2 感叹号红线] Layer 0–1 正文出现 {excl_l01_vis} 个感叹号（规定为 0）")
    for kind, txt in l01_widget_texts:
        c = len(EXCL_RE.findall(_strip_code_and_neq(txt)))
        if c > 0:
            errors.append(f"[Gate 2 组件感叹号] Layer 0–1 {kind} 含 {c} 个感叹号（规定为 0）")

    excl_all = len(EXCL_RE.findall(_strip_code_and_neq(full_combined)))
    if excl_all > 2:
        warnings.append(f"[Gate 2 感叹号偏多] 全文共 {excl_all} 个感叹号（建议 ≤2）")

    # Gate 3: Parallel score elimination in Layer 0-1 (catches decimal, integer & fullwidth)
    l01_combined = layer01_vis + "\n" + "\n".join(t for _, t in l01_widget_texts)
    ps_hits = PARALLEL_SCORE_RE.findall(l01_combined)
    if ps_hits:
        errors.append(f"[Gate 3 平行打分残留] Layer 0–1 出现已废除的 X/6 打分: {', '.join(sorted(set(ps_hits)))}")

    # Gate 4: Paragraph conciseness in Layer 0-1 (exact original line numbers + visible text length)
    long_paras = []
    for idx, line in enumerate(layer01_vis.splitlines(), 1):
        s = line.strip()
        if not s or LIST_OR_BLOCK_RE.match(s):
            continue
        vis_s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        vis_s = re.sub(r"\*\*|\*|`", "", vis_s)
        if len(vis_s) > 240:
            long_paras.append((idx, len(vis_s)))
    if long_paras:
        warnings.append(
            "[Gate 4 段落偏长] Layer 0–1 有超过 240 字的自然段: "
            + ", ".join(f"L{ln}({ch}字)" for ln, ch in long_paras[:5])
        )

    # Gate 5: Stale fact & snapshot consistency checks (edition-aware reconciliation!)
    active_guards = list(PERMANENT_FACT_GUARDS)
    if not snap or str(snap.get("as_of_short", "")).startswith("2026-11-24"):
        active_guards.extend(DATE_BOUND_STALE_GUARDS_20261124)
    for stale_tok, reason in active_guards:
        if stale_tok in full_combined:
            errors.append(f"[Gate 5 过时/冲突事实] 检出 '{stale_tok}' — {reason}")

    if snap:
        snap_ts = str(snap.get("as_of_short", ""))
        snap_bjt = str(snap.get("as_of_bjt", ""))
        file_ts = str(baseline_meta.get("as_of_short") or daily_meta.get("timestamp") or "")
        is_current_edition = (
            (not file_ts)
            or (bool(snap_ts) and snap_ts in file_ts)
            or (bool(snap_bjt) and snap_bjt in file_ts)
        )
        if is_current_edition:
            spot_r = int(snap["spot_gold_ny_close_rounded"])
            if f"{spot_r:,}" not in full_combined and str(spot_r) not in full_combined:
                warnings.append(f"[Gate 5 基准价缺失] 正文未检测到最新现货基准价 {spot_r}")
            ch = snap.get("rmb_channels", {})
            if ch:
                brand_r = int(ch["brand_store_rmb"])
                save_r = int(ch["wedding_save_per_g_rmb"])
                if f"{brand_r:,}" not in full_combined and str(brand_r) not in full_combined:
                    warnings.append(f"[Gate 5 金店价未对齐] 正文未检测到快照品牌金店价 {brand_r:,}")
                if str(save_r) not in full_combined:
                    warnings.append(f"[Gate 5 省钱差额未对齐] 正文未检测到快照婚庆省钱差额 {save_r} 元/克")

    # Gate 6: PDF & Native OOXML DOCX forensic verification (skipped in --precheck mode)
    if not precheck:
        check_pdf_and_docx_artifacts(md_path, raw, errors, warnings)

    return errors, warnings


def check_rsi_artifacts(errors: list[str], warnings: list[str]) -> None:
    """Validate bounded RSI playbook anti-bloat cap and structured rsi_metrics.json integrity."""
    if RSI_PLAYBOOK_PATH.exists():
        pb_text = RSI_PLAYBOOK_PATH.read_text(encoding="utf-8")
        line_cnt = len(pb_text.splitlines())
        if line_cnt > 220:
            errors.append(f"[RSI 防膨胀红线] daily/RSI_PLAYBOOK.md 共 {line_cnt} 行，超出硬上限 220 行（目标 ≤180 行），必须合并精炼旧条目")
        elif line_cnt > 180:
            warnings.append(f"[RSI 防膨胀预警] daily/RSI_PLAYBOOK.md 共 {line_cnt} 行，超出 180 行上限，请合并淘汰旧条目")
        if "Tier C" not in pb_text or "Tier B" not in pb_text:
            errors.append("[RSI 边界缺失] daily/RSI_PLAYBOOK.md 缺少 Tier B / Tier C 安全自进化边界声明")

    if RSI_METRICS_PATH.exists():
        try:
            data = json.loads(RSI_METRICS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"[RSI 账本损坏] daily/rsi_metrics.json JSON 非法: {e}")
            return
        runs = data.get("runs")
        if not isinstance(runs, list) or not runs:
            errors.append("[RSI 账本缺项] daily/rsi_metrics.json 缺少非空 runs 数组")
            return
        seen_ids: set[str] = set()
        for idx, r in enumerate(runs):
            if not isinstance(r, dict):
                errors.append(f"[RSI 账本格式] runs[{idx}] 不是对象")
                continue
            rid = str(r.get("run_id", "")).strip()
            if not rid:
                errors.append(f"[RSI 账本格式] runs[{idx}] 缺少 run_id")
            elif rid in seen_ids:
                errors.append(f"[RSI 账本重复] run_id '{rid}' 重复记录")
            else:
                seen_ids.add(rid)
            scores = r.get("scores")
            if not isinstance(scores, dict):
                errors.append(f"[RSI 评分缺项] run '{rid}' 缺少 scores 对象")
                continue
            score_sum = 0
            valid_all = True
            for k in RSI_REQUIRED_SCORE_KEYS:
                v = scores.get(k)
                if not isinstance(v, int) or isinstance(v, bool) or not (1 <= v <= 5):
                    errors.append(f"[RSI 评分非法] run '{rid}' 维度 {k} 须为 1–5 整数（实得 {v!r}）")
                    valid_all = False
                else:
                    score_sum += v
            if valid_all:
                if r.get("total_score") != score_sum:
                    errors.append(f"[RSI 总分冲突] run '{rid}' total_score={r.get('total_score')} != 6 维之和 {score_sum}")
                if r.get("max_score") != 30:
                    warnings.append(f"[RSI 满分口径] run '{rid}' max_score={r.get('max_score')}（应为 30）")


def check_calendar_and_scorecard(errors: list[str], warnings: list[str]) -> None:
    """Validate external 60+ day market_calendar.json and public zero-jargon daily/SCORECARD.md."""
    if not MARKET_CALENDAR_PATH.exists():
        errors.append("[外置日历缺失] 未找到 market_calendar.json")
    else:
        try:
            cal = json.loads(MARKET_CALENDAR_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"[外置日历损坏] market_calendar.json JSON 解析失败: {exc}")
        else:
            overrides = cal.get("calendar_overrides") if isinstance(cal, dict) else None
            if not isinstance(overrides, list) or len(overrides) == 0:
                errors.append("[外置日历空项] market_calendar.json 缺少非空 calendar_overrides 数组")

    if not SCORECARD_PATH.exists():
        errors.append("[公开记分卡缺失] 未找到 daily/SCORECARD.md")
    else:
        sc_text = SCORECARD_PATH.read_text(encoding="utf-8")
        if len(sc_text.strip()) < 200:
            errors.append("[公开记分卡过短] daily/SCORECARD.md 内容异常过短")
        leaked = SCORECARD_BANNED_RE.findall(sc_text)
        if leaked:
            errors.append(
                f"[公开记分卡内部词泄露] daily/SCORECARD.md 含禁止内部工程/RSI 词: {', '.join(sorted(set(leaked)))}"
            )


def main():
    args = sys.argv[1:]
    strict = "--strict" in args
    precheck = "--precheck" in args
    unknown_flags = [a for a in args if a.startswith("-") and a not in ("--strict", "--precheck")]
    if unknown_flags:
        print(f"Unknown option(s): {', '.join(unknown_flags)}")
        print("Usage: python3 lint_readability.py <file1.md> [file2.md ...] [--precheck] [--strict]")
        sys.exit(2)
    files = [Path(a) for a in args if not a.startswith("-")]
    if not files:
        print("Usage: python3 lint_readability.py <file1.md> [file2.md ...] [--precheck] [--strict]")
        sys.exit(2)

    snap_cache: dict[Path, dict | None] = {}
    exit_code = 0

    for snap_path in (DAILY_SNAPSHOT_PATH, MASTER_SNAPSHOT_PATH):
        if snap_path.exists():
            s_errs: list[str] = []
            s_warns: list[str] = []
            snap_cache[snap_path] = validate_snapshot_file(snap_path, s_errs, s_warns)
            if s_errs or s_warns:
                print(f"=== Data Snapshot Consistency Check: {snap_path.name} ===")
                for e in s_errs:
                    print(f"  [FAIL] {e}")
                for w in s_warns:
                    print(f"  [WARN] {w}")
                if s_errs or (strict and s_warns):
                    exit_code = 1

    rsi_errs: list[str] = []
    rsi_warns: list[str] = []
    check_rsi_artifacts(rsi_errs, rsi_warns)
    if rsi_errs or rsi_warns:
        print("=== RSI Playbook & Telemetry Integrity Check ===")
        for e in rsi_errs:
            print(f"  [FAIL] {e}")
        for w in rsi_warns:
            print(f"  [WARN] {w}")
        if rsi_errs or (strict and rsi_warns):
            exit_code = 1

    gov_errs: list[str] = []
    gov_warns: list[str] = []
    check_calendar_and_scorecard(gov_errs, gov_warns)
    if gov_errs or gov_warns:
        print("=== Market Calendar & Public Scorecard Check ===")
        for e in gov_errs:
            print(f"  [FAIL] {e}")
        for w in gov_warns:
            print(f"  [WARN] {w}")
        if gov_errs or (strict and gov_warns):
            exit_code = 1

    daily_snap = snap_cache.get(DAILY_SNAPSHOT_PATH)
    master_snap = snap_cache.get(MASTER_SNAPSHOT_PATH)

    for p in files:
        if not p.exists():
            print(f"[ERROR] File not found: {p}")
            exit_code = 1
            continue
        errs, warns = check_file(p, daily_snap, master_snap, snap_cache, precheck=precheck)
        mode_label = "Pre-Compile Gate 0–5 Check (--precheck)" if precheck else "7-Gate Readability, Accuracy & OOXML Lint"
        print(f"=== {mode_label}: {p.name} ===")
        if not errs and not warns:
            if precheck:
                print("  PASS: Gates 0–5 passed with 0 errors and 0 warnings (Gate 6 PDF/DOCX skipped).")
            else:
                print("  PASS: All 7 quality gates passed with 0 errors and 0 warnings.")
        else:
            for e in errs:
                print(f"  [FAIL] {e}")
            for w in warns:
                print(f"  [WARN] {w}")
        if errs or (strict and warns):
            exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
