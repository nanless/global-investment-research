#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Independent Pre-Flight & Full Forensic Quality Linter for Global Equity Research
(A-Share × HK-Stock × US-Stock + Cross-Project Gold SSOT Consistency Gate).

Usage:
  python3 lint_equity.py --precheck --strict [file1.md ...]   # Fast Gates 0-5 + SVG Gold-Lock scan before compiling
  python3 lint_equity.py --strict [file1.md ...]              # Full Gates 0-6 (PDF + ECMA-376 DOCX + Mobile HTML + Cross-Project)
  python3 lint_equity.py --strict                             # Auto-check all 3 flagships + latest 3 dailies + workspace state
"""

from __future__ import annotations

import glob
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

from pdf_common import BASE_DIR, DAILY_DIR, lint_markdown_report

GOLD_SNAPSHOT_PATH = BASE_DIR.parent / "gold" / "data_snapshot.json"
STATE_PATH = BASE_DIR / "state" / "market_state.json"

_CHART_PLACEHOLDER_RE = re.compile(r"<!--\s*CHART_[AHU]\d+\s*-->")
_GOLD_ACTIVE_BUY_RE = re.compile(
    r"(?:趁急跌.{0,12}(?:补齐|买|低吸).{0,8}黄金|"
    r"(?:小批|分批|立刻|马上|同步|今[日早晚]).{0,8}(?:补齐|补足|买入|加仓|加配|抄底).{0,8}(?:[0-9一二两三半成%]*\s*)?(?:黄金|金仓)|"
    r"(?:补齐|补足|加配|逢低买|抄底)\s*[0-9一二两三半成%]*\s*(?:黄金|金仓))"
)
_GOLD_DEFER_GUARD_RE = re.compile(
    r"(?:暂不|严禁|不新买|不动|不买|切忌|禁止|待.{0,10}黄灯|等.{0,10}黄灯|解锁后|12/18|存量底仓|预算暂泊|原稿曾建议|门控校正|历史实证|红灯停[（(]暂不新买|红灯期严禁|新仓\s*0%)"
)
_GOLD_MINER_TICKERS_RE = re.compile(
    r"(?:NEM|纽蒙特|山东黄金|中金黄金|赤峰黄金|山金国际|紫金黄金|招金|GLD|IAUM|518660|518880|159934)",
    flags=re.IGNORECASE,
)
_TEN_DOT_RE = re.compile(r"[●○]{10}")


def parse_daily_sort_key(p: Path) -> tuple[str, int, int, str]:
    """Deterministic sort key (YYYY-MM-DD, HHMM, rev_int, name) — immune to file mtime drift."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_(?:a_share|hk_stock|us_stock)(?:_r(\d+))?\.md$", p.name)
    if m:
        return (m.group(1), int(m.group(2)), int(m.group(3) or 1), p.name)
    return ("0000-00-00", 0, 0, p.name)


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
        if _GOLD_ACTIVE_BUY_RE.search(ln) and not _GOLD_DEFER_GUARD_RE.search(ln):
            found.append(
                f"Gate C2 跨项目硬冲突 ({label}:L{idx})：黄金当前为红灯停（new_buy_allowed=false），"
                f"权益侧严禁下达新买/补足黄金指令 -> {ln.strip()[:72]}"
            )
    return found


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

    req_gold_keys = ("tier_code", "spot_gold_ny_close_usd", "us10y_pct", "brent_settle_usd", "vix_close")
    for rk in req_gold_keys:
        if gold.get(rk) is None:
            errs.append(f"Gate C1 失败：黄金快照缺少必填核心键 {rk}")

    gold_tier = str(gold.get("tier_code", "")).strip()
    gold_new_buy = gold.get("new_buy_allowed", gold_tier != "Tier 0")
    gold_spot = float(gold.get("spot_gold_ny_close_usd", 0) or 0)
    gold_us10y = float(gold.get("us10y_pct", 0) or 0)
    gold_brent = float(gold.get("brent_settle_usd", 0) or 0)
    gold_vix = float(gold.get("vix_close", 0) or 0)
    gold_dfii10 = float(gold.get("dfii10_live_pct", 0) or 0)
    gold_dxy = float(gold.get("dxy", 0) or 0)
    gold_on_rrp = float(gold.get("on_rrp_usd_m", 0) or 0)
    gold_copper_chg = float(gold.get("comex_copper_change_pct", 0) or 0)

    # Gate C1: market_state.json mirror & freshness consistency
    if STATE_PATH.exists():
        st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
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
                # Auto-run staggered windows (07:30-10:30 / 18:00-21:00 CST) require <= 4.0h freshness; midday manual <= 10.5h
                max_h = 4.0 if e_dt.hour in (7, 8, 9, 10, 18, 19, 20) else 10.5
                if delta_h > max_h:
                    warns.append(
                        f"Gate C1 新鲜度提醒：黄金快照 ({g_ts_s}) 早于股研状态 ({e_ts_s[:16]}) {delta_h:.1f} 小时 (> {max_h:.1f}h 阈值)"
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
                for mk in ("a_share", "hk_stock", "us_stock", "gold_mirror_readonly"):
                    if mk not in mkts:
                        errs.append(f"Gate 4 失败：market_state.json.markets 缺少 {mk}")
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
            dims = data.get("score_dimensions", [])
            runs = data.get("runs", [])
            if not isinstance(dims, list) or len(dims) != 6 or len(set(dims)) != 6:
                errs.append("Gate 4 失败：rsi_metrics.json score_dimensions 须为 6 个唯一维度")
            dim_set = set(dims)
            seen: set[str] = set()
            for r in runs:
                rid = str(r.get("run_id", "")).strip()
                if not rid or rid in seen:
                    errs.append(f"Gate 4 失败：rsi_metrics.json run_id 重复或缺失: {rid}")
                seen.add(rid)
                sc = r.get("scores", {})
                if not isinstance(sc, dict) or set(sc.keys()) != dim_set:
                    errs.append(f"Gate 4 失败：rsi_metrics.json ({rid}) scores 维度不匹配")
                elif sum(sc.values()) != r.get("total_score") or r.get("max_score") != 30:
                    errs.append(f"Gate 4 失败：rsi_metrics.json ({rid}) 分数合计不一致")
        except Exception as exc:
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
        for href in re.findall(r"\[[^\]]+\]\(([^)\s]+)\)", idx_path.read_text(encoding="utf-8")):
            if href.startswith(("http://", "https://", "#")):
                continue
            target = Path(href[len("file://") :]) if href.startswith("file://") else (idx_path.parent / href).resolve()
            if precheck and (target.suffix.lower() in (".pdf", ".docx", ".html") or "_latest." in target.name):
                continue
            if not target.exists():
                errs.append(f"Gate 4 失败：INDEX.md 死链 {href}")

    if not precheck:
        for market in ("a_share", "hk_stock", "us_stock"):
            meta_f = BASE_DIR / f"report_meta_{market}.json"
            if not meta_f.exists():
                errs.append(f"Gate 6 失败：缺失 {meta_f.name}")
                continue
            try:
                slug = json.loads(meta_f.read_text(encoding="utf-8")).get("period_slug", "2026_11")
            except Exception as exc:
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
                slug = json.loads(meta_f.read_text(encoding="utf-8")).get("period_slug", "2026_11")
            except Exception as exc:
                disc_errors.append(f"Gate 6 失败：{meta_f.name} JSON 解析失败: {exc}")
                continue
            fp = BASE_DIR / f"{market}_market_report_{slug}.md"
            if fp.exists():
                targets.append(fp)
        daily_files = sorted(
            (Path(p) for p in glob.glob(str(DAILY_DIR / f"????-??-??_*_{market}*.md"))),
            key=parse_daily_sort_key,
        )
        if daily_files:
            targets.append(daily_files[-1])
    return targets, disc_errors


def main() -> None:
    args = sys.argv[1:]
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
                    meta = json.loads(mf.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    all_errors.append(f"{mf.name} JSON 语法错误: {exc}")
        else:
            meta, jerr = _extract_meta(md_text, p)
            if jerr:
                all_errors.append(f"{p.name}: {jerr}")

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

            exp_charts = len(_CHART_PLACEHOLDER_RE.findall(body_no_meta))
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
