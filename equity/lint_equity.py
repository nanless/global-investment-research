#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent Pre-Flight & Full Forensic Quality Linter for Global Equity Research
(A-Share × HK-Stock × US-Stock + Cross-Project Gold SSOT Consistency Gate).

Usage:
  python3 lint_equity.py --plan YYYY-MM-DD_HHMM[_rN]          # Compute required reports before refreshing snapshots
  python3 lint_equity.py --precheck --strict [file1.md ...]   # Fast Gates 0-5 + SVG Gold-Lock scan before compiling
  python3 lint_equity.py --strict [file1.md ...]              # Full Gates 0-6 (PDF + ECMA-376 DOCX + Mobile HTML + Cross-Project)
  python3 lint_equity.py --strict                             # Auto-check all 3 flagships + latest 3 dailies + workspace state
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path

from edition_plan import MARKETS, calendar_rules, edition_plan, parse_edition_id
from pdf_common import BASE_DIR, DAILY_DIR, lint_markdown_report

GOLD_SNAPSHOT_PATH = BASE_DIR.parent / "gold" / "data_snapshot.json"
GOLD_CALENDAR_PATH = GOLD_SNAPSHOT_PATH.with_name("market_calendar.json")
STATE_PATH = BASE_DIR / "state" / "market_state.json"
BEIJING = timezone(timedelta(hours=8))
EDITION_CUTOVER = ("2026-11-25", 1800, 2)
_PERIOD_RE = re.compile(r"\d{4}_(?:0[1-9]|1[0-2])")
_DAILY_NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{4})_(a_share|hk_stock|us_stock)(?:_r([2-9]|[1-9]\d+))?\.md")
_REPORT_CUTOFF_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})(?:\s|$)")
_FLAGSHIP_CUTOFF_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{4}年\d{1,2}月\d{1,2}日) +(\d{2}:\d{2})(?!\d)")

_CHART_PLACEHOLDER_RE = re.compile(r"<!--\s*CHART_[AHU]\d+\s*-->")
_GOLD_ACTIVE_BUY_RE = re.compile(
    r"(?:补齐|补足|买入|买进|加仓|加配|抄底|逢低买|低吸|新买|买)"
    r"\s*[0-9一二两三半成%]*\s*(?:现货)?(?:黄金|金仓)"
)
_GOLD_DEFER_GUARD_RE = re.compile(
    r"(?:暂不|严禁|禁止|切忌|勿|停止|先别|不能|不宜|不要|别急着|拒绝|不考虑|不允许|不应|不会|未在黄金红灯停期|不)"
    r"(?:追高芯片[与或])?(?:现在|今天|今日|当下|任何|立即|马上|急于|立刻|再|去|主动|新|分批|小批|继续|同步|直接|冲动|抢跑)*[\s“‘「\x22*_]*$"
    r"|(?:等到?|待).{0,12}(?:黄灯|绿灯|解锁)(?:亮起|确认)?(?:后|再|才)?[\s“‘「\x22]*$"
    r"|(?:黄灯|绿灯|解锁|过四关|全部过关)(?:亮起|确认)?后(?:再|才|择机)?[\s“‘「\x22]*$"
    r"|(?:原稿曾建议|原稿曾考虑|过去曾建议)[\s“‘「\x22]*$"
)
_GOLD_MINER_TICKERS_RE = re.compile(
    r"(?:NEM|纽蒙特|山东黄金|中金黄金|赤峰黄金|山金国际|紫金黄金|招金|GLD|IAUM|518660|518880|159934)",
    flags=re.IGNORECASE,
)
_TEN_DOT_RE = re.compile(r"[●○]{10}")


def parse_daily_sort_key(p: Path) -> tuple[str, int, int, str]:
    """Deterministic sort key (YYYY-MM-DD, HHMM, rev_int, name) — immune to file mtime drift."""
    match = _DAILY_NAME_RE.fullmatch(p.name)
    if match:
        try:
            datetime.strptime(f"{match[1]}_{match[2]}", "%Y-%m-%d_%H%M")
        except ValueError:
            pass
        else:
            return match[1], int(match[2]), int(match[4] or 1), p.name
    return "0000-00-00", 0, 0, p.name


def check_daily_contract(path: Path, meta: dict | None, md_text: str, *, as_of_cst: datetime | None = None) -> list[str]:
    """Check publication metadata while allowing immutable reports predating the contract."""
    sort_key = parse_daily_sort_key(path)[:3]
    if sort_key[0] == "0000-00-00":
        return [f"{path.name}: 日报文件名包含无效市场、日期、时刻或修订号"]
    requires_edition = sort_key >= EDITION_CUTOVER
    if meta is None:
        return [f"{path.name}: 当前体例须有文末 DAILY_META_JSON"] if requires_edition else []
    errors: list[str] = []
    edition = meta.get("edition_id")
    if (requires_edition or edition is not None) and parse_edition_id(edition) != sort_key:
        errors.append(f"{path.name}: edition_id 必须与文件名的日期、班次和修订号一致")
    if (requires_edition or "edition_type" in meta) and meta.get("edition_type") not in ("main", "light", "holiday_watch"):
        errors.append(f"{path.name}: edition_type 必须为 main、light 或 holiday_watch")
    chart = meta.get("chart_live")
    if isinstance(chart, dict) and "hkma_agg_bal_hkd_b" in chart and (requires_edition or "hkma_agg_bal_hkd_100m" in chart):
        errors.append(f"{path.name}: 金管局总结余须使用唯一的 hkma_agg_bal_hkd_100m（亿港元）")
    if requires_edition:
        cover_fields = ("tag", "title", "benchmark_time", "methodology", "page_footer", "footer_note")
        if any(not isinstance(meta.get(k), str) or not meta[k].strip() for k in cover_fields):
            errors.append(f"{path.name}: 当前体例缺少必填封面字段")
        if not isinstance(meta.get("kpis"), list) or len(meta["kpis"]) != 4:
            errors.append(f"{path.name}: 当前体例须提供四张 KPI 卡片")
        if not isinstance(chart, dict) or not chart:
            errors.append(f"{path.name}: 当前体例须有自身 chart_live 元数据")
        else:
            market_prefix = {"a_share": "A", "hk_stock": "H", "us_stock": "U"}[_detect_market(path)]
            for key in re.findall(r"<!--\s*CHART_([AHU]\d+)\s*-->", md_text):
                if key not in {f"{market_prefix}{n}" for n in range(1, 8)}:
                    errors.append(f"{path.name}: 图 {key} 不属于该市场")
                elif key not in ("A1", "A5") and not (isinstance(chart.get(key.lower()), dict) and chart[key.lower()]):
                    errors.append(f"{path.name}: 图 {key} 缺少本期 chart_live.{key.lower()} 数据")
                elif key == "H6" and sort_key > EDITION_CUTOVER:
                    h6 = chart["h6"]
                    items = h6.get("items")
                    if not isinstance(items, list) or not items or any(
                        not isinstance(row, list) or len(row) != 3
                        or not isinstance(row[0], str) or not row[0].strip()
                        or type(row[1]) not in (int, float) or not -sys.float_info.max <= row[1] <= sys.float_info.max
                        or not isinstance(row[2], str) or not row[2].strip()
                        for row in items
                    ):
                        errors.append(f"{path.name}: 图 H6 的 chart_live.h6.items 须提供本期非空的 [名称, 有限百分比, 说明] 行")
                    sector_strip = h6.get("sector_strip")
                    if not isinstance(sector_strip, str) or not sector_strip.strip():
                        errors.append(f"{path.name}: 图 H6 的 chart_live.h6.sector_strip 须提供本期板块说明")
            raw = chart.get("as_of_full")
            cutoff = _REPORT_CUTOFF_RE.match(raw) if isinstance(raw, str) else None
            try:
                local_cutoff = datetime.strptime(cutoff[1], "%Y-%m-%d %H:%M").replace(tzinfo=BEIJING) if cutoff else None
                edition_time = datetime.strptime(f"{sort_key[0]}_{sort_key[1]:04}", "%Y-%m-%d_%H%M").replace(tzinfo=BEIJING)
                if local_cutoff is None or abs(local_cutoff - edition_time) > timedelta(hours=4):
                    raise ValueError
                if as_of_cst is not None and local_cutoff.replace(second=0, microsecond=0) != as_of_cst.replace(second=0, microsecond=0):
                    errors.append(f"{path.name}: 图表数据截点与市场状态时间戳不一致")
            except ValueError:
                errors.append(f"{path.name}: chart_live.as_of_full 须为班次四小时内的有效北京时间")
    return errors


def _extract_meta(md_text: str, path: Path) -> tuple[dict | None, str | None]:
    m = re.search(r"<!--\s*DAILY_META_JSON\s*(\{.*?\})\s*-->", md_text, flags=re.DOTALL)
    if not m:
        return None, None
    try:
        return json.loads(m.group(1)), None
    except json.JSONDecodeError as exc:
        return None, f"DAILY_META_JSON 语法错误: {exc}"


def _detect_is_flagship(p: Path) -> bool:
    return p.parent.resolve() == BASE_DIR.resolve() and "_market_report_" in p.name


def _detect_market(p: Path) -> str:
    n = p.name.lower()
    if "hk_stock" in n:
        return "hk_stock"
    if "us_stock" in n:
        return "us_stock"
    return "a_share"


def _count_pdf_pages(pdf_path: Path) -> int | None:
    try:
        import pypdf  # type: ignore
        return len(pypdf.PdfReader(str(pdf_path)).pages)
    except Exception:
        pass
    try:
        raw = pdf_path.read_bytes()
        hits = re.findall(rb"/Type\s*/Page\b", raw)
        return len(hits) if hits else None
    except Exception:
        return None


def _count_appendix2_stock_rows(md_text: str) -> int | None:
    """Count stock rows in the flagship Appendix 2 (附表二 / 附录二) full stock pool table."""
    m = re.search(r"(?:^|\n)#{1,3}\s*附[录表]二[^\n]*\n(.*?)(?=\n#{1,2}\s*(?:附[录表]三|免责声明)|$)", md_text, flags=re.DOTALL)
    if not m:
        return None
    sec = m.group(1)
    tables: list[list[str]] = []
    cur: list[str] = []
    for ln in sec.splitlines():
        st = ln.strip()
        if st.startswith("|") and st.endswith("|"):
            cur.append(st)
        else:
            if cur:
                tables.append(cur)
                cur = []
    if cur:
        tables.append(cur)
    best_rows = 0
    for tbl in tables:
        data_rows = [
            r for r in tbl[1:]
            if not all(re.match(r"^:?-{2,}:?$", c.strip()) for c in r.strip("|").split("|"))
        ]
        if len(data_rows) > best_rows:
            best_rows = len(data_rows)
    return best_rows if best_rows > 0 else None


def _check_gate_3b(md_text: str, path: Path, *, is_flagship: bool, meta: dict | None, market: str, state: dict | None) -> tuple[list[str], list[str]]:
    """Gate 3B: verdict length, cover title length, 10-dot probability sum, Appendix 2 count & delisted guard."""
    errs: list[str] = []
    warns: list[str] = []
    body = re.sub(r"<!--\s*DAILY_META_JSON\s*\{.*?\}\s*-->", "", md_text, flags=re.DOTALL)

    # 1. Cover title length check
    if meta and meta.get("title"):
        t_clean = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", str(meta["title"])).strip()
        cap = 38 if is_flagship else 32
        if len(t_clean) > cap:
            warns.append(f"{path.name}: Gate 3B 封面主标题偏长 ({len(t_clean)} 字 > {cap} 字)")

    # 2. One-sentence verdict length check
    for ln in body.splitlines():
        st = ln.strip()
        if st.startswith(">") and ("一句话" in st):
            m_v = re.search(r"一句话[^：:]*[：:]\s*(.+)$", st)
            if m_v:
                v_plain = re.sub(r"[*`]", "", m_v.group(1)).strip()
                if len(v_plain) > 60:
                    warns.append(f"{path.name}: Gate 3B 一句话总判断偏长 ({len(v_plain)} 字，建议 ≤50 字 / 硬上限 60 字)")
            break

    # 3. Gigerenzer 10-dot probability bar sum check per table
    cur_table: list[str] = []
    tables: list[list[str]] = []
    for ln in body.splitlines():
        st = ln.strip()
        if st.startswith("|") and st.endswith("|"):
            cur_table.append(st)
        elif cur_table:
            tables.append(cur_table)
            cur_table = []
    if cur_table:
        tables.append(cur_table)
    for tbl in tables:
        dot_rows = []
        for r in tbl:
            bars = _TEN_DOT_RE.findall(r)
            if bars:
                dot_rows.append(bars[0].count("●"))
        if len(dot_rows) >= 3 and sum(dot_rows) != 10:
            errs.append(f"{path.name}: Gate 3B 情景表 10 点概率条合计={sum(dot_rows)} ≠ 10 ({dot_rows})")

    # 4. Flagship Appendix 2 row count vs stock_pool_count + HK delisted 00011 guard
    if is_flagship:
        app_rows = _count_appendix2_stock_rows(body)
        meta_cnt = None
        if meta and isinstance(meta.get("chart_live"), dict) and meta["chart_live"].get("stock_pool_count") is not None:
            meta_cnt = int(meta["chart_live"]["stock_pool_count"])
        state_cnt = None
        if state and isinstance(state.get("markets", {}).get(market), dict):
            sc = state["markets"][market].get("stock_pool_count")
            if sc is not None:
                state_cnt = int(sc)
        if app_rows is None:
            errs.append(f"{path.name}: Gate 3B 未检测到附表二个股总表")
        elif meta_cnt is not None and app_rows != meta_cnt:
            errs.append(f"{path.name}: Gate 3B 附表二实表行数 ({app_rows}) ≠ report_meta.stock_pool_count ({meta_cnt})")
        if meta_cnt is not None and state_cnt is not None and meta_cnt != state_cnt:
            errs.append(f"{path.name}: Gate 3B report_meta.stock_pool_count ({meta_cnt}) ≠ market_state ({state_cnt})")

    # 5. Guard against listing delisted Hang Seng Bank 00011 as an active pool/focus row (both flagship & daily)
    if market == "hk_stock":
        for ln in body.splitlines():
            if ln.strip().startswith("|") and ("00011" in ln or "恒生银行" in ln) and "退市" not in ln and "私有化" not in ln:
                errs.append(f"{path.name}: Gate 3B 港股严禁将已于 2026-01-27 退市的恒生银行 00011 列为活跃标的 -> {ln[:50]}")
                break

    return errs, warns


def _check_docx_forensics(docx_path: Path, md_mtime: float, expected_charts: int) -> tuple[list[str], list[str]]:
    errs: list[str] = []
    warns: list[str] = []
    if not docx_path.exists():
        return [f"Gate 6 失败：缺失原生 Word 文件 {docx_path.name}"], warns
    if docx_path.stat().st_mtime < md_mtime - 2.0:
        errs.append(f"Gate 6 失败：{docx_path.name} 修改时间早于源 Markdown（请重新编译）")
    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            names = set(zf.namelist())
            req_parts = {
                "[Content_Types].xml",
                "_rels/.rels",
                "word/document.xml",
                "word/_rels/document.xml.rels",
                "word/styles.xml",
                "word/settings.xml",
                "word/footer1.xml",
            }
            missing = req_parts - names
            if missing:
                errs.append(f"Gate 6 DOCX 缺少核心 OOXML 部件: {sorted(missing)}")
                return errs, warns

            parsed: dict[str, ET.Element] = {}
            for part in req_parts:
                raw = zf.read(part)
                try:
                    parsed[part] = ET.fromstring(raw)
                except ET.ParseError as exc:
                    errs.append(f"Gate 6 DOCX XML 损坏 ({part}): {exc}")
                    return errs, warns

            ct_root = parsed["[Content_Types].xml"]
            seen_override = False
            for child in ct_root:
                tag = child.tag.split("}")[-1]
                if tag == "Override":
                    seen_override = True
                    pname = child.attrib.get("PartName", "").lstrip("/")
                    if pname and pname not in names:
                        errs.append(f"Gate 6 DOCX [Content_Types] 悬空 Override: {pname}")
                elif tag == "Default" and seen_override:
                    errs.append("Gate 6 DOCX [Content_Types] 违反 ECMA-376：<Default> 出现在 <Override> 之后")

            doc_bytes = zf.read("word/document.xml").decode("utf-8")
            if "<w:sz-cs" in doc_bytes:
                errs.append("Gate 6 DOCX 含非法标签 <w:sz-cs>")
            if "___DOCX_CHART_" in doc_bytes:
                errs.append("Gate 6 DOCX 残留未替换图表占位符 ___DOCX_CHART_")

            w_ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            wp_ns = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
            pic_ns = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"
            doc_root = parsed["word/document.xml"]
            body = doc_root.find(f"{w_ns}body")
            if body is None or len(list(body)) == 0 or list(body)[-1].tag != f"{w_ns}sectPr":
                errs.append("Gate 6 DOCX <w:sectPr> 不在 <w:body> 末尾")

            tables = doc_root.findall(f".//{w_ns}tbl")
            if not tables:
                errs.append("Gate 6 DOCX 未检测到真 <w:tbl>（疑似退化为 textutil）")

            for tbl in tables:
                tbl_pr = tbl.find(f"{w_ns}tblPr")
                if tbl_pr is not None:
                    tags = [c.tag.split("}")[-1] for c in tbl_pr]
                    if "tblBorders" in tags and "tblLayout" in tags and tags.index("tblBorders") > tags.index("tblLayout"):
                        errs.append("Gate 6 DOCX tblPr 违反 ECMA-376 顺序（tblBorders 须早于 tblLayout）")
                grid = tbl.find(f"{w_ns}tblGrid")
                if grid is not None:
                    gws = [int(c.attrib.get(f"{w_ns}w", "0")) for c in grid.findall(f"{w_ns}gridCol")]
                    if any(w <= 0 for w in gws) or sum(gws) > 9638:
                        errs.append(f"Gate 6 DOCX tblGrid 异常: {gws} (和={sum(gws)} > 9638)")

            ftr_root = parsed["word/footer1.xml"]
            for ppr in ftr_root.findall(f".//{w_ns}pPr"):
                tags = [c.tag.split("}")[-1] for c in ppr]
                if "pBdr" in tags and "jc" in tags and tags.index("pBdr") > tags.index("jc"):
                    errs.append("Gate 6 DOCX 页脚 pBdr 晚于 jc")

            docpr_ids = [el.attrib.get("id") for el in doc_root.findall(f".//{wp_ns}docPr")]
            cnvpr_ids = [el.attrib.get("id") for el in doc_root.findall(f".//{pic_ns}cNvPr")]
            if len(docpr_ids) != len(set(docpr_ids)):
                errs.append("Gate 6 DOCX wp:docPr/@id 重复")
            if len(cnvpr_ids) != len(set(cnvpr_ids)):
                errs.append("Gate 6 DOCX pic:cNvPr/@id 重复")

            rels_root = parsed["word/_rels/document.xml.rels"]
            valid_pngs = 0
            for rel in rels_root:
                tgt = rel.attrib.get("Target", "")
                mode = rel.attrib.get("TargetMode", "")
                if mode != "External":
                    full_t = f"word/{tgt.lstrip('/')}"
                    if full_t not in names:
                        errs.append(f"Gate 6 DOCX 断链关系目标: {tgt}")
                    elif full_t.endswith(".png"):
                        pdata = zf.read(full_t)
                        if pdata[:8] == b"\x89PNG\r\n\x1a\n" and len(pdata) >= 2048:
                            valid_pngs += 1
                        else:
                            errs.append(f"Gate 6 DOCX 内嵌图片异常: {full_t}")
            if valid_pngs < expected_charts:
                errs.append(f"Gate 6 DOCX 有效内嵌图表数不足 ({valid_pngs} < 预期 {expected_charts})")
    except zipfile.BadZipFile as exc:
        errs.append(f"Gate 6 DOCX ZIP 损坏: {exc}")
    return errs, warns


def _scan_text_for_gold_buy(label: str, text: str) -> list[str]:
    found: list[str] = []
    for idx, ln in enumerate(text.splitlines(), 1):
        if any(
            not _GOLD_DEFER_GUARD_RE.search(re.split(r"[。！？；，,、|]", ln[:action.start()])[-1])
            for action in _GOLD_ACTIVE_BUY_RE.finditer(ln)
        ):
            found.append(
                f"Gate C2 跨项目硬冲突 ({label}:L{idx})：黄金当前为红灯停（new_buy_allowed=false），"
                f"权益侧严禁下达新买/补足黄金指令 -> {ln.strip()[:72]}"
            )
    return found


def _check_release_snapshot(gold: dict, state: dict, targets: list[Path]) -> list[str]:
    errors: list[str] = []
    edition_id = state.get("edition_id")
    edition_key = parse_edition_id(edition_id)
    if edition_key is None or parse_edition_id(gold.get("edition_id")) != edition_key:
        return ["Gate C1 失败：黄金与权益须声明同一有效 edition_id"]
    if any(parse_daily_sort_key(p)[:3] > edition_key for p in targets if not _detect_is_flagship(p)):
        errors.append("Gate C1 失败：日报场次晚于共享快照场次")
    try:
        g_ts = datetime.strptime(gold["as_of_short"], "%Y-%m-%d %H:%M").replace(tzinfo=BEIJING)
        e_ts = datetime.fromisoformat(state["as_of_cst"])
        edition_time = datetime.strptime(f"{edition_key[0]}_{edition_key[1]:04}", "%Y-%m-%d_%H%M").replace(tzinfo=BEIJING)
        if e_ts.utcoffset() != BEIJING.utcoffset(e_ts):
            raise ValueError("权益状态须明确使用 +08:00")
        if not timedelta(0) <= e_ts - g_ts <= timedelta(hours=4):
            errors.append("Gate C1 失败：黄金须先于或同分钟于权益落盘，且数据时间差须在四小时内")
        if any(abs(ts - edition_time) > timedelta(hours=4) for ts in (g_ts, e_ts)):
            errors.append("Gate C1 失败：快照数据时间偏离所标班次超过四小时")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"Gate C1 失败：跨项目时间戳非法：{exc}")

    try:
        mirror = state["markets"]["gold_mirror_readonly"]
        rates = state["cross_market_linkages"]["rates_fx_chain"]
        comm = state["cross_market_linkages"]["commodity_mirror"]
        brake = state["cross_market_linkages"]["crisis_correlation_brake"]
        if not all(isinstance(obj, dict) for obj in (mirror, rates, comm, brake)):
            raise TypeError("镜像字段须为对象")
    except (KeyError, TypeError) as exc:
        return errors + [f"Gate C1 失败：黄金跨市场镜像结构不完整：{exc}"]

    if mirror.get("edition_id") != edition_id or mirror.get("as_of_short") != gold.get("as_of_short"):
        errors.append("Gate C1 失败：黄金镜像场次或数据截点与权威快照不一致")
    if not gold.get("tier_code") or mirror.get("tier_code") != gold["tier_code"]:
        errors.append("Gate C1 失败：黄金档位与镜像不一致")
    if not isinstance(gold.get("new_buy_allowed"), bool) or mirror.get("new_buy_allowed") is not gold["new_buy_allowed"]:
        errors.append("Gate C1 失败：黄金新仓开关与镜像不一致或类型非法")
    if mirror.get("gates_passed") != f"{gold.get('tier1_passed')}/{gold.get('tier1_total')}":
        errors.append("Gate C1 失败：黄金过关计数与镜像不一致")
    values = (
        ("spot_gold_ny_close_usd", mirror, "spot_ny_close_usd"),
        ("us10y_pct", rates, "us10y_pct"),
        ("dfii10_live_pct", rates, "dfii10_pct"),
        ("dxy", rates, "dxy"),
        ("brent_settle_usd", comm, "brent_usd"),
        ("brent_live_usd", comm, "brent_live_usd"),
        ("cfets_cny_fixing", rates, "cfets_cny_fixing"),
        ("vix_close", brake, "vix_close"),
        ("on_rrp_usd_m", brake, "on_rrp_usd_m"),
        ("comex_copper_usd_lb", comm, "comex_copper_usd_lb"),
        ("comex_copper_change_pct", comm, "comex_copper_chg_pct"),
    )
    for gold_key, mirror_group, equity_key in values:
        gold_value, equity_value = gold.get(gold_key), mirror_group.get(equity_key)
        if (any(type(v) not in (int, float) or not isfinite(v) for v in (gold_value, equity_value))
                or gold_value != equity_value or (gold_key == "vix_close" and gold_value <= 0)):
            errors.append(f"Gate C1 失败：{gold_key} 跨轨数值缺失、非法或漂移 gold={gold_value} equity={equity_value}")
    gold_live, equity_live = gold.get("vix_live"), brake.get("vix_live")
    if gold_live is None and equity_live is None and edition_key > EDITION_CUTOVER:
        if gold.get("vix_live_as_of") is not None:
            errors.append("Gate C1 失败：VIX 无盘中观测时不得保留 vix_live_as_of")
        if brake.get("vix_intraday_high") is not None:
            errors.append("Gate C1 失败：VIX 无盘中观测时不得保留 vix_intraday_high")
    elif (any(type(v) not in (int, float) or not isfinite(v) or v <= 0 for v in (gold_live, equity_live))
          or gold_live != equity_live):
        errors.append(f"Gate C1 失败：vix_live 跨轨数值缺失、非法或漂移 gold={gold_live} equity={equity_live}")
    fixing_date = gold.get("cfets_fixing_date")
    try:
        if fixing_date != rates.get("cfets_fixing_date") or datetime.strptime(fixing_date, "%Y-%m-%d").date().isoformat() != fixing_date or fixing_date > edition_key[0]:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Gate C1 失败：CFETS 中间价日期须有效、跨轨一致且不晚于班次日期")
    return errors


def _check_cross_project_gold(targets: list[Path], *, precheck: bool) -> tuple[list[str], list[str]]:
    """Cross-Project Consistency Gates C1-C3 against ../gold/data_snapshot.json."""
    errs: list[str] = []
    warns: list[str] = []
    if not GOLD_SNAPSHOT_PATH.exists():
        warns.append(f"Gate C1 跳过：未找到黄金快照 {GOLD_SNAPSHOT_PATH}")
        return errs, warns

    try:
        gold = json.loads(GOLD_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Gate C1 失败：无法解析黄金快照: {exc}"], warns

    if not isinstance(gold, dict):
        return ["Gate C1 失败：黄金快照须为 JSON 对象"], warns

    st: dict = {}
    if STATE_PATH.exists():
        try:
            st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return [f"Gate C1 失败：无法解析权益状态：{exc}"], warns
    if not isinstance(st, dict):
        return ["Gate C1 失败：权益状态须为 JSON 对象"], warns
    release = gold.get("edition_id") is not None or st.get("edition_id") is not None or any(
        parse_daily_sort_key(p)[:3] >= EDITION_CUTOVER for p in targets if not _detect_is_flagship(p)
    )
    if release:
        errs.extend(_check_release_snapshot(gold, st, targets))

    req_gold_keys = ("tier_code", "spot_gold_ny_close_usd", "us10y_pct", "brent_settle_usd", "vix_close")
    for rk in req_gold_keys:
        if gold.get(rk) is None:
            errs.append(f"Gate C1 失败：黄金快照缺少必填核心键 {rk}")

    gold_tier = str(gold.get("tier_code", "")).strip()
    gold_new_buy = gold.get("new_buy_allowed", gold_tier != "Tier 0")
    try:
        gold_copper_chg = float(gold.get("comex_copper_change_pct", 0) or 0)
    except (TypeError, ValueError):
        return errs + ["Gate C3 失败：COMEX 铜异动数值非法"], warns

    # Gate C1: market_state.json mirror & freshness consistency
    if st and not release:
        try:
            gold_spot, gold_us10y, gold_brent, gold_vix, gold_dfii10, gold_dxy, gold_on_rrp = (
                float(gold.get(key, 0) or 0) for key in (
                    "spot_gold_ny_close_usd", "us10y_pct", "brent_settle_usd", "vix_close", "dfii10_live_pct", "dxy", "on_rrp_usd_m"
                )
            )
        except (TypeError, ValueError):
            return errs + ["Gate C1 失败：黄金快照的历史宏观字段含非数值"], warns
        mirror = st.get("markets", {}).get("gold_mirror_readonly", {})
        if not mirror:
            errs.append("Gate C1 失败：state/market_state.json 缺少 markets.gold_mirror_readonly 镜像锁")
        else:
            if mirror.get("tier_code") != gold_tier:
                errs.append(f"Gate C1 失败：黄金档位漂移 market_state={mirror.get('tier_code')} vs gold={gold_tier}")
            if bool(mirror.get("new_buy_allowed")) != bool(gold_new_buy):
                errs.append(f"Gate C1 失败：黄金 new_buy_allowed 漂移 equity={mirror.get('new_buy_allowed')} vs gold={gold_new_buy}")
            if gold_spot and abs(float(mirror.get("spot_ny_close_usd", 0) or 0) - gold_spot) > 1.5:
                errs.append(f"Gate C1 失败：现货金漂移 market_state={mirror.get('spot_ny_close_usd')} vs gold={gold_spot}")
            link_rates = st.get("cross_market_linkages", {}).get("rates_fx_chain", {})
            if gold_us10y and link_rates.get("us10y_pct") is not None:
                if abs(float(link_rates["us10y_pct"]) - gold_us10y) > 0.03:
                    errs.append(f"Gate C1 失败：10Y美债漂移 equity={link_rates['us10y_pct']} vs gold={gold_us10y}")
            if gold_dfii10 and link_rates.get("dfii10_pct") is not None:
                if abs(float(link_rates["dfii10_pct"]) - gold_dfii10) > 0.04:
                    errs.append(f"Gate C1 失败：10Y实际利率漂移 equity={link_rates['dfii10_pct']} vs gold={gold_dfii10}")
            if gold_dxy and link_rates.get("dxy") is not None:
                if abs(float(link_rates["dxy"]) - gold_dxy) > 0.4:
                    errs.append(f"Gate C1 失败：美元指数漂移 equity={link_rates['dxy']} vs gold={gold_dxy}")
            comm = st.get("cross_market_linkages", {}).get("commodity_mirror", {})
            if gold_brent and comm.get("brent_usd") is not None:
                if abs(float(comm["brent_usd"]) - gold_brent) > 0.5:
                    errs.append(f"Gate C1 失败：布油漂移 equity={comm['brent_usd']} vs gold={gold_brent}")
            brake = st.get("cross_market_linkages", {}).get("crisis_correlation_brake", {})
            if gold_vix and brake.get("vix_close") is not None:
                if abs(float(brake["vix_close"]) - gold_vix) > 0.5:
                    errs.append(f"Gate C1 失败：VIX 漂移 equity={brake['vix_close']} vs gold={gold_vix}")
            if gold_on_rrp and brake.get("on_rrp_usd_m") is not None:
                if abs(float(brake["on_rrp_usd_m"]) - gold_on_rrp) > 20.0:
                    errs.append(f"Gate C1 失败：ON RRP 漂移 equity={brake['on_rrp_usd_m']} vs gold={gold_on_rrp}")

            # CFETS CNY fixing cross-check when both snapshots share the same fixing date
            gold_cfets = float(gold.get("cfets_cny_fixing", 0) or 0)
            gold_cfets_dt = str(gold.get("cfets_fixing_date", "")).strip()
            eq_cfets = link_rates.get("cfets_cny_fixing")
            eq_cfets_dt = str(link_rates.get("cfets_fixing_date", "")).strip()
            if gold_cfets and eq_cfets is not None and gold_cfets_dt and eq_cfets_dt == gold_cfets_dt:
                try:
                    if abs(float(eq_cfets) - gold_cfets) > 0.002:
                        errs.append(
                            f"Gate C1 失败：CFETS 中间价漂移 ({gold_cfets_dt}) equity={eq_cfets} vs gold={gold_cfets}"
                        )
                except (TypeError, ValueError):
                    errs.append(f"Gate C1 失败：cfets_cny_fixing 数值格式非法 ({eq_cfets})")

            # Window-aware Gold snapshot freshness check (fail loudly on malformed timestamps)
            g_ts_s = str(gold.get("as_of_short", "")).strip()
            e_ts_s = str(st.get("as_of_cst", "")).strip()
            try:
                g_dt = datetime.strptime(g_ts_s, "%Y-%m-%d %H:%M")
                e_dt = datetime.fromisoformat(e_ts_s).replace(tzinfo=None)
                delta_h = (e_dt - g_dt).total_seconds() / 3600.0
                # Unified sequential run windows (07:00–10:59 / 18:00–20:59 CST, Gold SSOT first -> Equity second) require <= 4.0h freshness; midday manual <= 10.5h
                max_h = 4.0 if e_dt.hour in (7, 8, 9, 10, 18, 19, 20) else 10.5
                if delta_h > max_h:
                    warns.append(
                        f"Gate C1 新鲜度提醒：黄金快照 ({g_ts_s}) 早于股研状态 ({e_ts_s[:16]}) {delta_h:.1f} 小时 (> {max_h:.1f}h 阈值)"
                    )
                elif delta_h < -4.0:
                    warns.append(
                        f"Gate C1 反向滞后提醒：股研状态 ({e_ts_s[:16]}) 落后黄金快照 ({g_ts_s}) {abs(delta_h):.1f} 小时 (> 4.0h 阈值)"
                    )
            except Exception as exc:
                errs.append(f"Gate C1 失败：跨项目时间戳解析异常 gold={g_ts_s!r} equity={e_ts_s!r} ({exc})")

    # Gate C2: P0 Action Mutex Lock — when Gold is Tier 0 or new_buy_allowed is False, scan MD + Daily JSON + Flagship JSON + ALL SVGs + HTML!
    if gold_tier == "Tier 0" or gold_new_buy is False:
        for p in targets:
            txt = p.read_text(encoding="utf-8")
            # Scan FULL file including DAILY_META_JSON so daily chart/KPI strings cannot bypass C2
            errs.extend(_scan_text_for_gold_buy(p.name, txt))
        for mkt_k, chart_k, mf in (
            ("a_share", "a7", BASE_DIR / "report_meta_a_share.json"),
            ("hk_stock", "h7", BASE_DIR / "report_meta_hk_stock.json"),
            ("us_stock", "u7", BASE_DIR / "report_meta_us_stock.json"),
        ):
            if mf.exists():
                m_raw = mf.read_text(encoding="utf-8")
                errs.extend(_scan_text_for_gold_buy(mf.name, m_raw))
                try:
                    m_obj = json.loads(m_raw)
                    pts = m_obj.get("chart_live", {}).get(chart_k, {}).get("points", [])
                    for pt in pts:
                        if isinstance(pt, (list, tuple)) and len(pt) >= 5:
                            plbl, pcls, pcol = str(pt[0]), str(pt[3]).lower(), str(pt[4]).upper()
                            if _GOLD_MINER_TICKERS_RE.search(plbl) and (pcls == "g" or pcol == "#009E73"):
                                errs.append(
                                    f"Gate C2 跨项目硬冲突 ({mf.name}:{chart_k})：黄金红灯停期严禁将金矿/黄金标的标为绿色底座 -> {plbl}"
                                )
                except Exception as exc:
                    errs.append(f"Gate C2 失败：{mf.name} 解析异常: {exc}")
        # Also scan rendered flagship & daily SVGs directly so hardcoded SVG cards can never bypass C2!
        try:
            if str(BASE_DIR) not in sys.path:
                sys.path.insert(0, str(BASE_DIR))
            import build_a_share_pdf as mod_a
            import build_hk_stock_pdf as mod_h
            import build_us_stock_pdf as mod_u
            import build_daily as mod_d
            svg_checks = [
                ("SVG:A4", mod_a.svg_chart_a4_clock()),
                ("SVG:A5", mod_a.svg_chart_a5_targets_and_math()),
                ("SVG:H4", mod_h.svg_chart_h4_clock()),
                ("SVG:U4", mod_u.svg_chart_u4_clock()),
            ]
            for p in targets:
                if not _detect_is_flagship(p):
                    d_meta, _ = _extract_meta(p.read_text(encoding="utf-8"), p)
                    if d_meta:
                        d_charts = mod_d.load_optional_charts(_detect_market(p), meta_override=d_meta)
                        for ck, c_html in d_charts.items():
                            svg_checks.append((f"{p.name}:{ck}", c_html))
            for lbl, svg_html in svg_checks:
                plain_svg = re.sub(r"<[^>]+>", "\n", svg_html)
                errs.extend(_scan_text_for_gold_buy(lbl, plain_svg))
        except Exception as exc:
            warns.append(f"Gate C2 SVG 预扫跳过: {exc}")
        if not precheck:
            for mob in (DAILY_DIR / "latest_a_share.html", DAILY_DIR / "latest_hk_stock.html", DAILY_DIR / "latest_us_stock.html"):
                if mob.exists():
                    plain_mob = re.sub(r"<[^>]+>", "\n", mob.read_text(encoding="utf-8"))
                    errs.extend(_scan_text_for_gold_buy(mob.name, plain_mob))

    # Gate C3: Commodity shock propagation check (Copper >= 3.5% shock must be noted in A/HK dailies & flagships)
    if abs(gold_copper_chg) >= 3.5:
        for p in targets:
            if "_a_share" in p.name or "_hk_stock" in p.name or "a_share_market_report" in p.name or "hk_stock_market_report" in p.name:
                txt = p.read_text(encoding="utf-8")
                if "铜" not in txt:
                    warns.append(
                        f"Gate C3 大宗跨市联动提醒 ({p.name})：COMEX 铜异动 {gold_copper_chg:+.2f}%，"
                        "A股/港股报告须评估对有色/紫金/洛钼的传导"
                    )
    return errs, warns


def _check_state_schedule(state: dict) -> list[str]:
    errors: list[str] = []
    current = parse_edition_id(state.get("edition_id"))
    queue = state.get("pending_backfills")
    if not isinstance(queue, list):
        errors.append("Gate 4 失败：pending_backfills 须为数组")
    else:
        for index, item in enumerate(queue):
            if not isinstance(item, dict) or item.get("market") not in MARKETS or not isinstance(item.get("item"), str) or not item["item"].strip():
                errors.append(f"Gate 4 失败：pending_backfills[{index}] 须有有效市场和待补事项")
                continue
            due = parse_edition_id(item.get("due_session"))
            if due is None or due[2] != 1:
                errors.append(f"Gate 4 失败：pending_backfills[{index}].due_session 须为有效计划班次")
            elif current and due[:2] < current[:2]:
                errors.append(f"Gate 4 失败：pending_backfills[{index}] 已逾期，须结清或指定下次核验班次")

    try:
        calendar = json.loads(GOLD_CALENDAR_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return errors + [f"Gate 4 失败：无法读取黄金交易日历：{exc}"]
    if not current:
        _, calendar_errors = calendar_rules(state, calendar)
        if "edition_id" in state:
            errors.append("Gate 4 失败：market_state.json.edition_id 非法")
        return errors + [f"Gate 4 失败：{error}" for error in calendar_errors]

    plan, plan_errors = edition_plan(state["edition_id"], state, calendar)
    errors.extend(f"Gate 4 失败：{error}" for error in plan_errors)
    if not plan_errors:
        errors.extend(_check_edition_delivery(state, current, plan))
    return errors


def _check_edition_delivery(state: dict, current: tuple[str, int, int], plan: dict) -> list[str]:
    errors = []
    if state.get("period_slug") != plan["period_slug"]:
        errors.append(f"Gate 4 失败：市场状态 period_slug 须更新为 {plan['period_slug']}")
    exceptions = state.get("publication_exceptions")
    if exceptions and exceptions.get("edition_id") != plan["edition_id"]:
        errors.append("Gate 4 失败：publication_exceptions 须标记当前 edition_id，旧班次的例外应移除")
    markets = state.get("markets")
    if not isinstance(markets, dict):
        return errors

    for market, expected in plan["markets"].items():
        per_market = markets.get(market)
        if not isinstance(per_market, dict):
            continue
        try:
            meta = _read_flagship_meta(market)
            if meta["period_slug"] != plan["period_slug"]:
                errors.append(f"Gate 4 失败：report_meta_{market}.json.period_slug 须为 {plan['period_slug']}")
            else:
                month = plan["period_slug"]
                if not (BASE_DIR / f"{market}_market_report_{month}.md").is_file():
                    errors.append(f"Gate 4 失败：{market} 缺少 {month} 旗舰 Markdown")
                chart = meta.get("chart_live")
                stamp = chart.get("as_of_full") if isinstance(chart, dict) else None
                match = _FLAGSHIP_CUTOFF_RE.match(stamp) if isinstance(stamp, str) else None
                try:
                    cutoff = datetime.strptime(
                        f"{match[1]} {match[2]}", "%Y年%m月%d日 %H:%M" if "年" in match[1] else "%Y-%m-%d %H:%M"
                    ) if match else None
                except ValueError:
                    cutoff = None
                if cutoff is None or cutoff.strftime("%Y_%m") != month or cutoff.date().isoformat() > current[0]:
                    errors.append(f"Gate 4 失败：report_meta_{market}.json.chart_live.as_of_full 须为当期且不超出班次日期的有效截点")
        except (OSError, ValueError) as exc:
            errors.append(f"Gate 4 失败：report_meta_{market}.json：{exc}")

        reports = _market_daily_files(market)
        seen = {}
        for report in reports:
            key = parse_daily_sort_key(report)[:3]
            if key in seen:
                errors.append(f"Gate 4 失败：重复的 {market} 日报 {seen[key].relative_to(BASE_DIR)} 与 {report.relative_to(BASE_DIR)}")
            else:
                seen[key] = report
        latest = max(reports, key=parse_daily_sort_key, default=None)
        pointer = per_market.get("latest_daily")
        if latest is None or pointer != latest.relative_to(BASE_DIR).as_posix():
            errors.append(f"Gate 4 失败：{market} 的 latest_daily 须指向该市场最近的实际日报")
        if latest and parse_daily_sort_key(latest)[:3] > current:
            errors.append(f"Gate 4 失败：{latest.name} 晚于当前刊期 {plan['edition_id']}")
        if expected["action"] == "publish":
            report = BASE_DIR / expected["required_file"]
            if not report.is_file():
                errors.append(f"Gate 4 失败：{plan['edition_id']} 缺当班 {market} {expected['edition_type']}：{report.name}")
                continue
            data, err = _extract_meta(report.read_text(encoding="utf-8"), report)
            if err or not data or data.get("edition_id") != plan["edition_id"]:
                errors.append(f"Gate 4 失败：{report.name} 须绑定当班 edition_id")
            if not data or data.get("edition_type") != expected["edition_type"]:
                errors.append(f"Gate 4 失败：{report.name} 刊型应为 {expected['edition_type']}")
            continue
        if latest and parse_daily_sort_key(latest)[:3] == current:
            errors.append(f"Gate 4 失败：{latest.name} 当班应复用旧刊，不应生成新刊")
        if expected["reason"] == "revision_reuse" and (
            latest is None or parse_daily_sort_key(latest)[:2] != current[:2]
        ):
            errors.append(f"Gate 4 失败：{market} 修订复用须有同班更早版本")
        if expected["reason"] == "source_outage":
            next_review = exceptions["markets"][market]["next_review_session"]
            queue = state.get("pending_backfills")
            if not isinstance(queue, list) or not any(
                isinstance(entry, dict) and entry.get("market") == market and entry.get("due_session") == next_review
                for entry in queue
            ):
                errors.append(f"Gate 4 失败：{market} 数据故障须在 pending_backfills 登记相同核验班次")
    return errors


def _read_flagship_meta(market: str) -> dict:
    meta_file = BASE_DIR / f"report_meta_{market}.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    slug = meta.get("period_slug") if isinstance(meta, dict) else None
    if not isinstance(slug, str) or not _PERIOD_RE.fullmatch(slug):
        raise ValueError("period_slug 须为有效 YYYY_MM")
    return meta


def _market_daily_files(market: str, *, keep_invalid: bool = False) -> list[Path]:
    pattern = f"????-??-??_*_{market}*.md"
    paths = (*DAILY_DIR.glob(pattern), *(DAILY_DIR / "archive").rglob(pattern))
    return sorted(
        (path for path in paths if keep_invalid or parse_daily_sort_key(path)[0] != "0000-00-00"),
        key=parse_daily_sort_key,
    )


def load_current_edition_plan() -> dict | None:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("权益状态须为 JSON 对象")
    if "edition_id" not in state:
        return None
    calendar = json.loads(GOLD_CALENDAR_PATH.read_text(encoding="utf-8"))
    edition_id = state["edition_id"]
    plan, errors = edition_plan(edition_id, state, calendar)
    if errors:
        raise ValueError("\n".join(errors))
    current = parse_edition_id(edition_id)
    assert current is not None
    delivery_errors = _check_edition_delivery(state, current, plan)
    if delivery_errors:
        raise ValueError("\n".join(delivery_errors))
    return plan


def _check_rsi_metrics(data: dict) -> list[str]:
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        return ["rsi_metrics.json 须为包含 runs 数组的对象"]
    dims = data.get("score_dimensions")
    if (not isinstance(dims, list) or len(dims) != 6
            or any(not isinstance(dim, str) or not dim.strip() for dim in dims) or len(set(dims)) != 6):
        return ["rsi_metrics.json score_dimensions 须为 6 个唯一维度"]
    errors = []
    seen = set()
    for index, run in enumerate(data["runs"]):
        if not isinstance(run, dict):
            errors.append(f"rsi_metrics.json runs[{index}] 须为对象")
            continue
        identifier = run.get("run_id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            errors.append(f"rsi_metrics.json ({index}) run_id 重复或缺失")
            continue
        seen.add(identifier)
        scores = run.get("scores")
        if not isinstance(scores, dict) or scores.keys() != set(dims):
            errors.append(f"rsi_metrics.json ({identifier}) scores 维度不匹配")
        elif any(type(score) is not int or not 1 <= score <= 5 for score in scores.values()):
            errors.append(f"rsi_metrics.json ({identifier}) 各维度分数须为 1–5 的整数")
        elif type(run.get("total_score")) is not int or sum(scores.values()) != run["total_score"] or type(run.get("max_score")) is not int or run["max_score"] != 30:
            errors.append(f"rsi_metrics.json ({identifier}) 分数合计不一致")
    return errors


def _check_index_links(index: Path, *, precheck: bool) -> list[str]:
    errors = []
    latest_stems = {
        reports[-1].with_suffix("").resolve()
        for market in MARKETS if (reports := _market_daily_files(market))
    }
    for href in re.findall(r"\[[^\]]+\]\(([^)\s]+)\)", index.read_text(encoding="utf-8")):
        if href.startswith(("http://", "https://", "#")):
            continue
        target = Path(href[len("file://") :]) if href.startswith("file://") else (index.parent / href).resolve()
        suffix = target.suffix.lower()
        if target.is_file():
            continue
        if suffix in (".pdf", ".docx") and target.is_relative_to(DAILY_DIR.resolve()):
            source = target.with_suffix(".md")
            if (source.is_file() and parse_daily_sort_key(source)[0] != "0000-00-00"
                    and (precheck or source.with_suffix("").resolve() not in latest_stems)):
                continue
        if precheck and target in {DAILY_DIR / f"latest_{market}.html" for market in MARKETS}:
            continue
        if precheck and target.parent == BASE_DIR and suffix in (".md", ".pdf", ".docx"):
            flagship = re.fullmatch(r"(a_share|hk_stock|us_stock)_market_report_(latest|\d{4}_\d{2})", target.stem)
            if flagship:
                market, slug = flagship.groups()
                if slug == "latest":
                    try:
                        slug = _read_flagship_meta(market)["period_slug"]
                    except (OSError, ValueError):
                        slug = ""
                if (BASE_DIR / f"{market}_market_report_{slug}.md").is_file():
                    continue
        errors.append(f"Gate 4 失败：INDEX.md 死链 {href}")
    return errors


def check_workspace_state(*, precheck: bool = False) -> tuple[list[str], list[str]]:
    """Shared single-source workspace state, RSI playbook/metrics, ledger, INDEX link & _latest sync check."""
    errs: list[str] = []
    warns: list[str] = []
    if not STATE_PATH.exists():
        errs.append("Gate 4 失败：缺少 state/market_state.json")
    else:
        try:
            st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if not isinstance(st, dict):
                errs.append("Gate 4 失败：market_state.json 根元素必须为对象")
            else:
                for k in ("markets", "cross_market_linkages", "policy_radars", "pending_backfills", "calendar_overrides"):
                    if k not in st:
                        errs.append(f"Gate 4 失败：market_state.json 缺少必填域 {k}")
                mkts = st.get("markets", {})
                if not isinstance(mkts, dict):
                    errs.append("Gate 4 失败：market_state.json.markets 须为对象")
                else:
                    for mk in (*MARKETS, "gold_mirror_readonly"):
                        if not isinstance(mkts.get(mk), dict):
                            errs.append(f"Gate 4 失败：market_state.json.markets 缺少 {mk}")
                errs.extend(_check_state_schedule(st))
        except json.JSONDecodeError as exc:
            errs.append(f"Gate 4 失败：market_state.json JSON 语法错误: {exc}")

    pb = BASE_DIR / "state" / "RSI_PLAYBOOK.md"
    if not pb.exists():
        errs.append("Gate 4 失败：缺少 state/RSI_PLAYBOOK.md")
    else:
        n = len(pb.read_text(encoding="utf-8").splitlines())
        if n > 200:
            errs.append(f"Gate 4 失败：state/RSI_PLAYBOOK.md 超过 200 行硬限 ({n})")
        elif n > 180:
            warns.append(f"Gate 4 警告：state/RSI_PLAYBOOK.md 超过 180 行软限 ({n})")

    mf = BASE_DIR / "state" / "rsi_metrics.json"
    if not mf.exists():
        errs.append("Gate 4 失败：缺少 state/rsi_metrics.json")
    else:
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            errs.extend(f"Gate 4 失败：{error}" for error in _check_rsi_metrics(data))
        except (OSError, ValueError) as exc:
            errs.append(f"Gate 4 失败：rsi_metrics.json 解析失败: {exc}")

    for ledger in (DAILY_DIR / "INDEX.md", DAILY_DIR / "CHANGELOG.md", DAILY_DIR / "SCORECARD.md"):
        if not ledger.exists():
            errs.append(f"Gate 4 失败：缺少 {ledger.relative_to(BASE_DIR)}")
        else:
            le, lw = lint_markdown_report(ledger.read_text(encoding="utf-8"), str(ledger), is_flagship=False)
            errs.extend([f"{ledger.name}: {x}" for x in le])
            warns.extend([f"{ledger.name}: {x}" for x in lw])

    idx_path = DAILY_DIR / "INDEX.md"
    if idx_path.exists():
        errs.extend(_check_index_links(idx_path, precheck=precheck))

    if not precheck:
        for market in ("a_share", "hk_stock", "us_stock"):
            meta_f = BASE_DIR / f"report_meta_{market}.json"
            if not meta_f.exists():
                errs.append(f"Gate 6 失败：缺失 {meta_f.name}")
                continue
            try:
                slug = _read_flagship_meta(market)["period_slug"]
            except (OSError, ValueError) as exc:
                errs.append(f"Gate 6 失败：{meta_f.name} JSON 解析失败: {exc}")
                continue
            for ext in ("md", "pdf", "docx"):
                p_cur = BASE_DIR / f"{market}_market_report_{slug}.{ext}"
                p_lat = BASE_DIR / f"{market}_market_report_latest.{ext}"
                if not p_cur.exists():
                    errs.append(f"Gate 6 失败：缺失当期旗舰文件 {p_cur.name}")
                elif not p_lat.exists() or p_cur.read_bytes() != p_lat.read_bytes():
                    errs.append(f"Gate 6 失败：{p_lat.name} 未与 {p_cur.name} 原子同步")
            mob = DAILY_DIR / f"latest_{market}.html"
            if not mob.exists() or mob.stat().st_size < 5000:
                errs.append(f"Gate 6 失败：缺失或过小的手机端 HTML {mob.name}")
            else:
                mtxt = mob.read_text(encoding="utf-8")
                if "viewport-fit=cover" not in mtxt or "nav-switch" not in mtxt:
                    errs.append(f"Gate 6 失败：{mob.name} 缺少三市手机端导航或安全区适配")
    return errs, warns


def _auto_discover_targets() -> tuple[list[Path], list[str]]:
    targets: list[Path] = []
    disc_errors: list[str] = []
    for market in ("a_share", "hk_stock", "us_stock"):
        meta_f = BASE_DIR / f"report_meta_{market}.json"
        if meta_f.exists():
            try:
                slug = _read_flagship_meta(market)["period_slug"]
            except (OSError, ValueError) as exc:
                disc_errors.append(f"Gate 6 失败：{meta_f.name} JSON 解析失败: {exc}")
                continue
            fp = BASE_DIR / f"{market}_market_report_{slug}.md"
            if fp.exists():
                targets.append(fp)
        daily_files = _market_daily_files(market, keep_invalid=True)
        for invalid in (p for p in daily_files if parse_daily_sort_key(p)[0] == "0000-00-00"):
            disc_errors.append(f"Gate 4 失败：日报文件名非法 {invalid.name}")
        if daily_files and parse_daily_sort_key(daily_files[-1])[0] != "0000-00-00":
            targets.append(daily_files[-1])
    return targets, disc_errors


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["--plan"]:
        if len(args) != 2:
            sys.exit("Usage: lint_equity.py --plan YYYY-MM-DD_HHMM[_rN]")
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            calendar = json.loads(GOLD_CALENDAR_PATH.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("权益状态须为 JSON 对象")
            plan, errors = edition_plan(args[1], state, calendar)
        except (OSError, ValueError) as exc:
            sys.exit(f"无法生成出刊计划：{exc}")
        if errors:
            sys.exit("\n".join(errors))
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    known_flags = {"--precheck", "--strict", "--skip-cross-project"}
    unknown = [a for a in args if a.startswith("-") and a not in known_flags]
    if unknown:
        print(f"Unknown flags: {unknown}", file=sys.stderr)
        sys.exit(2)

    precheck = "--precheck" in args
    strict = "--strict" in args
    skip_cross = "--skip-cross-project" in args
    positional = [Path(a) for a in args if not a.startswith("-")]
    discovery_errors: list[str] = []
    if positional:
        targets = positional
    else:
        targets, discovery_errors = _auto_discover_targets()
    if not targets:
        for derr in discovery_errors:
            print(f"  [FAIL] {derr}", file=sys.stderr)
        print("No target Markdown files found.", file=sys.stderr)
        sys.exit(2)

    state_obj: dict | None = None
    if STATE_PATH.exists():
        try:
            state_obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            state_obj = None
    if not isinstance(state_obj, dict):
        state_obj = {}
    current_id = parse_edition_id(state_obj.get("edition_id"))
    try:
        as_of_cst = datetime.fromisoformat(state_obj.get("as_of_cst", ""))
    except (TypeError, ValueError):
        as_of_cst = None

    all_errors: list[str] = list(discovery_errors)
    all_warnings: list[str] = []

    for p in targets:
        if not p.exists():
            all_errors.append(f"目标文件不存在: {p}")
            continue
        md_text = p.read_text(encoding="utf-8")
        is_flag = _detect_is_flagship(p)
        mkt = _detect_market(p)
        meta: dict | None = None
        if is_flag:
            mf = BASE_DIR / f"report_meta_{mkt}.json"
            if mf.exists():
                try:
                    meta = _read_flagship_meta(mkt)
                except (OSError, ValueError) as exc:
                    all_errors.append(f"{mf.name} 元数据错误: {exc}")
        else:
            meta, jerr = _extract_meta(md_text, p)
            if jerr:
                all_errors.append(f"{p.name}: {jerr}")
            cutoff = as_of_cst if parse_daily_sort_key(p)[:3] == current_id else None
            all_errors.extend(check_daily_contract(p, meta, md_text, as_of_cst=cutoff))

        errs, warns = lint_markdown_report(md_text, str(p), is_flagship=is_flag, meta=meta)
        all_errors.extend([f"{p.name}: {x}" for x in errs])
        all_warnings.extend([f"{p.name}: {x}" for x in warns])

        b3_errs, b3_warns = _check_gate_3b(md_text, p, is_flagship=is_flag, meta=meta, market=mkt, state=state_obj)
        all_errors.extend(b3_errs)
        all_warnings.extend(b3_warns)

        body_no_meta = re.sub(r"<!--\s*DAILY_META_JSON\s*\{.*?\}\s*-->", "", md_text, flags=re.DOTALL)
        long_bullets = sum(
            1 for ln in body_no_meta.splitlines()
            if re.match(r"^\s*[-•*]\s+", ln) and len(ln.strip()) > 210
        )
        if long_bullets:
            all_warnings.append(f"{p.name}: 存在 {long_bullets} 条超过 210 字的超长列表项（防密墙）")

        if not precheck:
            md_mtime = p.stat().st_mtime
            pdf_p = p.with_suffix(".pdf")
            if not pdf_p.exists() or pdf_p.stat().st_size < 50_000:
                all_errors.append(f"Gate 6 失败：缺失或过小的 PDF {pdf_p.name}")
            elif pdf_p.read_bytes()[:5] != b"%PDF-":
                all_errors.append(f"Gate 6 失败：{pdf_p.name} 文件头非法")
            elif pdf_p.stat().st_mtime < md_mtime - 2.0:
                all_errors.append(f"Gate 6 失败：{pdf_p.name} 修改时间早于 {p.name}")
            else:
                n_pages = _count_pdf_pages(pdf_p)
                if n_pages is not None:
                    if is_flag and not (16 <= n_pages <= 24):
                        all_warnings.append(f"Gate 6 页数提醒：{pdf_p.name} 共 {n_pages} 页（旗舰手册建议 16–24 页）")
                    elif not is_flag:
                        ed_type = str((meta or {}).get("edition_type", "")).strip().lower()
                        if ed_type == "main" and not (3 <= n_pages <= 6):
                            all_warnings.append(f"Gate 6 页数提醒：{pdf_p.name} (main) 共 {n_pages} 页（主刊建议 4–5 页，容忍 3–6 页）")
                        elif ed_type in ("light", "holiday_watch") and not (1 <= n_pages <= 4):
                            all_warnings.append(f"Gate 6 页数提醒：{pdf_p.name} ({ed_type}) 共 {n_pages} 页（轻刊建议 2–3 页，容忍 1–4 页）")
                        elif not ed_type and n_pages > 6:
                            all_warnings.append(f"Gate 6 页数提醒：{pdf_p.name} 共 {n_pages} 页（日报偏长，建议 ≤6 页）")

            exp_charts = len(_CHART_PLACEHOLDER_RE.findall(body_no_meta)) if is_flag or meta else 0
            de, dw = _check_docx_forensics(p.with_suffix(".docx"), md_mtime, exp_charts)
            all_errors.extend([f"{p.name}: {x}" for x in de])
            all_warnings.extend([f"{p.name}: {x}" for x in dw])

    we, ww = check_workspace_state(precheck=precheck)
    all_errors.extend(we)
    all_warnings.extend(ww)

    if not skip_cross:
        ce, cw = _check_cross_project_gold(targets, precheck=precheck)
        all_errors.extend(ce)
        all_warnings.extend(cw)

    mode_str = "PRECHECK (Gates 0-5 + SVG)" if precheck else "FULL FORENSIC (Gates 0-6 + Cross-Project)"
    print(f"=== lint_equity.py [{mode_str}] checked {len(targets)} file(s) ===")
    for e in all_errors:
        print(f"  [FAIL] {e}")
    for w in all_warnings:
        print(f"  [WARN] {w}")
    print(f"Summary: {len(all_errors)} error(s), {len(all_warnings)} warning(s).")

    if all_errors or (strict and all_warnings):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
