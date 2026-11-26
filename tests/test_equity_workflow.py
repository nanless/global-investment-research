import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts import artifact_receipt


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "equity"))
import build_hk_stock_pdf
import build_us_stock_pdf
import pdf_common
from build_daily import extract_daily_meta, load_optional_charts
from lint_equity import (
    MARKETS, _check_playbook_retracted_claims, _check_rsi_metrics, _scan_text_for_gold_buy,
)

KPI_CARDS = [{"label": "数据", "val": "1", "sub": "测试"} for _ in range(4)]
WATCH = "mode_2_watch_brief"
ALL_CLOSED = "mode_3_index_changelog_only"


def holiday(day, kind, markets, **fields):
    return {"date_cst": day, "type": kind, "markets_affected": list(markets), "mode": WATCH, **fields}


class EquityWorkflowTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        equity = self.root / "equity"
        (equity / "daily/archive/2026-11").mkdir(parents=True)
        (equity / "state").mkdir()
        (self.root / "gold").mkdir()
        for script in (ROOT / "equity").glob("*.py"):
            shutil.copy2(script, equity / script.name)
        self.state_path = equity / "state/market_state.json"
        self.gold_path = self.root / "gold/data_snapshot.json"
        for ledger in ("INDEX", "CHANGELOG", "SCORECARD"):
            (equity / f"daily/{ledger}.md").write_text("# 账本\n", encoding="utf-8")
        (equity / "state/RSI_PLAYBOOK.md").write_text("# 复盘规则\n", encoding="utf-8")
        (equity / "state/rsi_metrics.json").write_text(json.dumps({"score_dimensions": list("abcdef"), "runs": []}))
        self.gold = {
            "tier_code": "Tier 1", "new_buy_allowed": True, "tier1_passed": 4, "tier1_total": 4,
            "spot_gold_ny_close_usd": 3500, "us10y_pct": 4.8, "dfii10_live_pct": 2.6, "dxy": 99.8,
            "brent_settle_usd": 90, "brent_live_usd": 90.2, "cfets_cny_fixing": 6.9, "cfets_fixing_date": "2026-11-25",
            "vix_close": 27.3, "vix_live": 30, "vix_live_as_of": "2026-11-25 18:00",
            "on_rrp_usd_m": 21, "comex_copper_usd_lb": 4.7, "comex_copper_change_pct": -4.7,
        }
        self.state = {
            "period_slug": "2026_11", "markets": {market: {} for market in MARKETS}, "policy_radars": {},
            "cross_market_linkages": {
                "rates_fx_chain": {key: self.gold[key] for key in ("us10y_pct", "dxy", "cfets_cny_fixing", "cfets_fixing_date")}
                | {"dfii10_pct": self.gold["dfii10_live_pct"]},
                "commodity_mirror": {key: self.gold[key] for key in ("brent_live_usd", "comex_copper_usd_lb")}
                | {"brent_usd": self.gold["brent_settle_usd"], "comex_copper_chg_pct": self.gold["comex_copper_change_pct"]},
                "crisis_correlation_brake": {key: self.gold[key] for key in ("vix_close", "vix_live", "on_rrp_usd_m")},
            },
            "calendar_overrides": [
                holiday("2026-11-26", "partial_holiday", ["us_stock"], gold_event_id="thanksgiving",
                        affected_sessions=["2026-11-26_1800", "2026-11-27_0730"]),
                holiday("2026-11-27", "half_day", ["us_stock"]),
                holiday("2026-12-24", "half_day", ["hk_stock", "us_stock"]),
                holiday("2026-12-25", "partial_holiday", ["hk_stock", "us_stock"]),
                holiday("2026-12-31", "half_day", ["hk_stock"]),
                holiday("2027-01-01", "full_holiday_and_rollover", MARKETS, mode=ALL_CLOSED),
                holiday("2027-02-05", "long_holiday_start", ["a_share"], end_date_cst="2027-02-14"),
                holiday("2027-02-08", "partial_holiday", ["hk_stock"], end_date_cst="2027-02-09"),
            ],
        }
        self.state["markets"]["gold_mirror_readonly"] = {
            "tier_code": "Tier 1", "new_buy_allowed": True, "gates_passed": "4/4", "spot_ny_close_usd": 3500,
        }
        calendar = {
            "timezone": "Asia/Shanghai", "as_of": "2026-11-25", "calendar_overrides": [{
                "id": "thanksgiving", "date": "2026-11-26", "end_date": "2026-11-26", "markets": ["US_EQUITY"],
                "affected_editions": ["2026-11-26_1800", "2026-11-27_0730"], "trading_hours_bjt": {"US": "休市"},
            }],
        }
        (self.root / "gold/market_calendar.json").write_text(json.dumps(calendar))
        self.advance("2026-11-25_1800_r2", no_live=False)
        for market, kind in zip(MARKETS, ("main", "main", "light")):
            (equity / f"{market}_market_report_2026_11.md").write_text(
                "# 权益手册\n\n覆盖期铜。\n\n## 附表二\n\n| 名称 | 数值 |\n| --- | --- |\n| 示例 | 1 |\n",
                encoding="utf-8",
            )
            meta = {"period_slug": "2026_11", "kpis": KPI_CARDS,
                    "chart_live": {"as_of_full": "2026年11月25日 13:30（北京时间）"}}
            (equity / f"report_meta_{market}.json").write_text(json.dumps(meta), encoding="utf-8")
            self.issue(market, kind)

    def lint(self, *args):
        return subprocess.run(
            [sys.executable, "equity/lint_equity.py", *args], cwd=self.root,
            encoding="utf-8", capture_output=True, check=False,
        )

    def save(self):
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
        self.gold_path.write_text(json.dumps(self.gold, ensure_ascii=False), encoding="utf-8")

    def _types(self, session):
        result = self.lint("--plan", session)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return tuple(row["edition_type"] for row in json.loads(result.stdout)["markets"].values())

    def advance(self, session, *, no_live=True):
        day, time, *_ = session.split("_")
        local_time = f"{time[:2]}:{time[2:]}"
        stamp = f"{day} {local_time}"
        self.state.update(edition_id=session, as_of_cst=f"{day}T{local_time}:00+08:00", pending_backfills=[])
        self.gold.update(edition_id=session, as_of_short=stamp)
        self.state["markets"]["gold_mirror_readonly"].update(edition_id=session, as_of_short=stamp)
        if no_live:
            self.gold.pop("vix_live", None)
            self.gold.pop("vix_live_as_of", None)
            self.state["cross_market_linkages"]["crisis_correlation_brake"]["vix_live"] = None
        self.save()

    def issue(self, market, kind):
        edition = self.state["edition_id"]
        day, hhmm, *revision = edition.split("_")
        ext = f"_{revision[0]}" if revision else ""
        name = f"{day}_{hhmm}_{market}{ext}.md"
        spec = {
            "edition_id": edition, "edition_type": kind, "tag": "权益简报", "title": "权益简报",
            "benchmark_time": "按北京时间", "methodology": "测试样稿", "page_footer": "权益简报",
            "footer_note": "测试样稿", "kpis": KPI_CARDS,
            "chart_live": {"as_of_full": self.state["as_of_cst"][:16].replace("T", " ") + " 北京时间"},
        }
        path = self.root / "equity/daily" / name
        timing = "黑五 06:00 盘后终盘已结束。" if day == "2026-11-28" and market == "us_stock" else ""
        path.write_text(
            f"# 权益简报\n\n本刊检查交付形态，覆盖期铜。{timing}\n\n"
            f"<!-- DAILY_META_JSON {json.dumps(spec, ensure_ascii=False)} -->\n",
            encoding="utf-8",
        )
        with (path.parent / "INDEX.md").open("a", encoding="utf-8") as index:
            index.write(f"\n[权益简报]({name})\n")
        self.state["markets"][market]["latest_daily"] = f"daily/{name}"
        self.save()
        return path

    def test_plan_matrix(self):
        for session, expected in (
            ("2026-11-26_0730", ("light", "light", "main")),
            ("2026-11-26_1800", ("main", "main", "holiday_watch")),
            ("2026-11-27_0730", ("main", "main", "holiday_watch")),
            ("2026-11-28_0730", (None, None, "holiday_watch")),
            ("2026-11-28_1800", (None, None, None)),
            ("2026-11-29_0730", (None, None, None)),
            ("2026-11-30_0730", ("main", "main", "main")),
            ("2026-12-24_0730", ("main", "holiday_watch", "main")),
            ("2026-12-26_0730", (None, None, None)),
            ("2026-12-31_1800", ("main", "holiday_watch", "main")),
            ("2027-01-01_0730", (None, None, "main")),
            ("2027-01-01_1800", (None, None, None)),
            ("2027-01-02_0730", (None, None, None)),
            ("2027-02-08_1800", ("holiday_watch", "holiday_watch", "main")),
            ("2027-02-10_1800", ("holiday_watch", "main", "main")),
        ):
            with self.subTest(session=session):
                self.assertEqual(self._types(session), expected)

    def test_correct_black_friday_issue_and_extra_market(self):
        self.advance("2026-11-28_0730")
        self.issue("us_stock", "holiday_watch")
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.issue("a_share", "light")
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("当班应复用旧刊", result.stdout)

    def test_required_reports_and_edition_types(self):
        self.advance("2026-11-26_1800")
        self.issue("us_stock", "main")
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("缺当班 a_share main", result.stdout)
        self.assertIn("缺当班 hk_stock main", result.stdout)
        self.assertIn("刊型应为 holiday_watch", result.stdout)

    def test_weekend_exception_requires_evidence(self):
        edition = "2026-11-29_0730"
        self.advance(edition)
        row = {"kind": "breaking_event", "severity": "P1", "reason": "交易所发布临时公告"}
        self.state["publication_exceptions"] = {"edition_id": edition, "markets": {"a_share": row}}
        self.issue("a_share", "holiday_watch")
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("缺少官方 HTTPS", result.stdout)
        row.update(evidence_url="https://www.sse.com.cn/")
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_source_outage_includes_future_backfill(self):
        edition = "2026-11-26_0730"
        self.advance(edition)
        self.state["publication_exceptions"] = {"edition_id": edition, "markets": {"us_stock": {
            "kind": "source_outage", "reason": "交易所公告服务中断", "evidence_url": "https://www.nyse.com/",
            "next_review_session": "2026-11-26_1800",
        }}}
        self.issue("a_share", "light")
        self.issue("hk_stock", "light")
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("数据故障须在 pending_backfills", result.stdout)
        self.state["pending_backfills"].append({
            "market": "us_stock", "item": "交易所公告服务中断", "due_session": "2026-11-26_1800",
        })
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cross_month_does_not_accept_old_flagships(self):
        self.advance("2026-12-01_0730")
        self.state["period_slug"] = "2026_12"
        for market, kind in (("a_share", "main"), ("hk_stock", "main"), ("us_stock", "main")):
            self.issue(market, kind)
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stdout.count("period_slug 须为 2026_12"), 3)
        equity = self.root / "equity"
        for market in MARKETS:
            shutil.copyfile(equity / f"{market}_market_report_2026_11.md", equity / f"{market}_market_report_2026_12.md")
            path = equity / f"report_meta_{market}.json"
            meta = json.loads(path.read_text())
            meta["period_slug"] = "2026_12"
            path.write_text(json.dumps(meta))
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stdout.count("须为当期且不超出班次日期"), 3)
        for market, stamp in zip(MARKETS, ("2026年12月1日 07:25（北京时间）", "2026-12-01 07:25 北京时间",
                                            "2026-12-01 07:25 北京时间")):
            path = equity / f"report_meta_{market}.json"
            meta = json.loads(path.read_text())
            meta["chart_live"]["as_of_full"] = stamp
            path.write_text(json.dumps(meta))
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_revision_may_reuse_earlier_issue_in_same_session(self):
        edition = "2026-11-25_1800_r3"
        self.advance(edition)
        self.state["publication_exceptions"] = {"edition_id": edition, "markets": {
            market: {"kind": "revision_reuse", "reason": "此次勘误仅涉及美股"}
            for market in ("a_share", "hk_stock")
        }}
        self.issue("us_stock", "light")
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_h6_requires_current_chart_data_for_new_reports(self):
        self.advance("2026-11-25_1800_r3")
        self.issue("a_share", "main")
        hk_report = self.issue("hk_stock", "main")
        self.issue("us_stock", "light")
        meta, body = extract_daily_meta(hk_report.read_text(encoding="utf-8"), hk_report)
        items = [["本期样本", -17.57, "本期价差"]]
        sector_strip = "本期板块数据"
        for h6, invalid_field in (
            ({"title": "本期两地价差"}, "items"),
            ({"items": []}, "items"),
            ({"items": [["本期样本", 1]]}, "items"),
            ({"items": [[" ", 1, "本期价差"]]}, "items"),
            ({"items": [["本期样本", True, "本期价差"]]}, "items"),
            ({"items": [["本期样本", float("nan"), "本期价差"]]}, "items"),
            ({"items": [["本期样本", float("inf"), "本期价差"]]}, "items"),
            ({"items": [["本期样本", 10**400, "本期价差"]]}, "items"),
            ({"items": [["本期样本", 1, " "]]}, "items"),
            ({"items": items}, "sector_strip"),
            ({"items": items, "sector_strip": " "}, "sector_strip"),
            ({"items": items, "sector_strip": sector_strip}, None),
        ):
            with self.subTest(h6=h6):
                meta["chart_live"]["h6"] = h6
                hk_report.write_text(
                    f"{body}\n\n<!-- CHART_H6 -->\n\n<!-- DAILY_META_JSON {json.dumps(meta, ensure_ascii=False)} -->\n",
                    encoding="utf-8",
                )
                result = self.lint("--precheck", "--strict")
                self.assertEqual(result.returncode, 1 if invalid_field else 0, result.stdout + result.stderr)
                if invalid_field:
                    self.assertIn(f"图 H6 的 chart_live.h6.{invalid_field}", result.stdout)

        chart = load_optional_charts("hk_stock", meta)["<!-- CHART_H6 -->"]
        svg = chart.partition("<svg")[2].partition("</svg>")[0]
        self.assertIn("本期样本", svg)
        self.assertIn("-17.6%", svg)
        self.assertIn(sector_strip, svg)
        self.assertNotIn("-21.1%", svg)

    def test_vix_missing_both_sides_requires_no_stale_quote(self):
        self.advance("2026-11-29_1800")
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.gold["vix_live_as_of"] = "2026-11-25 21:20"
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("无盘中观测时不得保留", result.stdout)
        del self.gold["vix_live_as_of"]
        self.state["cross_market_linkages"]["crisis_correlation_brake"]["vix_live"] = 30.99
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("vix_live 跨轨", result.stdout)
        self.state["cross_market_linkages"]["crisis_correlation_brake"].update(vix_live=None, vix_intraday_high=31)
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("不得保留 vix_intraday_high", result.stdout)

    def test_strict_web_only_checks_flagship_md_sync_without_pdf_or_docx(self):
        md = self.root / "equity/a_share_market_report_2026_11.md"
        latest_md = self.root / "equity/a_share_market_report_latest.md"
        latest_md.write_bytes(md.read_bytes())
        result = self.lint("--strict", str(md))
        self.assertIn("WEB-ONLY FORENSIC", result.stdout, result.stderr)
        self.assertNotIn("缺失或过小的 PDF", result.stdout)
        self.assertNotIn("缺失原生 Word", result.stdout)

        latest_md.write_text("stale latest copy\n", encoding="utf-8")
        result = self.lint("--strict", str(md))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("未与 a_share_market_report_2026_11.md 原子同步", result.stdout)

    def test_backfill_and_archive_duplicates_fail(self):
        self.advance("2026-11-28_0730")
        path = self.issue("us_stock", "holiday_watch")
        shutil.copy2(path, path.parent / "archive/2026-11" / path.name)
        self.state["pending_backfills"].append({
            "market": "us_stock", "item": "前一班数据", "due_session": "2026-11-27_1800",
        })
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("重复的 us_stock 日报", result.stdout)
        self.assertIn("已逾期", result.stdout)

    def test_calendar_rejects_duplicate_market_and_bad_revision(self):
        self.state["calendar_overrides"][0]["markets_affected"].append("us_stock")
        self.save()
        result = self.lint("--plan", "2026-11-26_1800")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("重复市场", result.stderr)
        result = self.lint("--plan", "2026-11-26_1800_r1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("edition_id", result.stderr)

    def test_index_rejects_deprecated_pdf_docx_and_dead_links(self):
        self.advance("2026-11-26_0730")
        for market, kind in zip(MARKETS, ("light", "light", "main")):
            self.issue(market, kind)
        index = self.root / "equity/daily/INDEX.md"
        with index.open("a", encoding="utf-8") as file:
            file.write(
                "\n[这一期Markdown](2026-11-26_0730_us_stock.md)\n"
                "[弃用PDF](2026-11-26_0730_us_stock.pdf)\n"
                "[弃用Word](2026-11-24_1800_us_stock.docx)\n"
                "[死链](2026-11-24_1800_us_stock.md)\n"
            )
        result = self.lint("--strict")
        self.assertIn("INDEX.md 含已弃用的 PDF/Word 链接 2026-11-26_0730_us_stock.pdf", result.stdout)
        self.assertIn("INDEX.md 含已弃用的 PDF/Word 链接 2026-11-24_1800_us_stock.docx", result.stdout)
        self.assertIn("INDEX.md 死链 2026-11-24_1800_us_stock.md", result.stdout)
        self.assertNotIn("2026-11-26_0730_us_stock.md", result.stdout)

    def test_rsi_and_gold_action_scope(self):
        dims = list("abcdef")
        data = {"score_dimensions": dims, "runs": [{"run_id": "run", "scores": dict.fromkeys(dims, 5),
                                                     "total_score": 30, "max_score": 30}]}
        self.assertFalse(_check_rsi_metrics(data))
        for value in (True, 5.0, 6, -1):
            with self.subTest(value=value):
                data["runs"][0]["scores"]["a"] = value
                self.assertTrue(_check_rsi_metrics(data))
        for sentence in ("存量底仓保持，同时立即买入黄金", "严禁买入股票后立即买入黄金", "严禁买入黄金；马上买入黄金"):
            self.assertTrue(_scan_text_for_gold_buy("report", sentence), sentence)
        for sentence in ("存量底仓保持，不立即买入黄金", "严禁追高芯片与抢跑新买黄金", "等黄灯后再买入黄金"):
            self.assertFalse(_scan_text_for_gold_buy("report", sentence), sentence)

    def test_brent_live_none_allowed_on_both_sides_only(self):
        self.advance("2026-11-29_1800")
        comm = self.state["cross_market_linkages"]["commodity_mirror"]
        self.gold["brent_live_usd"] = None
        comm["brent_live_usd"] = None
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        comm["brent_live_usd"] = 90.2
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Gate C1 失败：brent_live_usd", result.stdout)

        self.gold["brent_live_usd"] = 90.2
        comm["brent_live_usd"] = None
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Gate C1 失败：brent_live_usd", result.stdout)

    def test_retracted_tax_etf_bond_gates_block_reports_and_playbook(self):
        report_cases = (
            ("买 159545 可享零溢价优势。", "ETF 规则硬错误"),
            ("港股通持有红筹 28% 税成本偏高。", "港股税务口径硬错误"),
            ("可转债末日二级卖出免 20% 个人税。", "可转债到期税费硬错误"),
        )
        for prose, expected_err in report_cases:
            with self.subTest(report_claim=prose):
                errors, _ = pdf_common.lint_markdown_report(prose, "2026-11-26_1800_hk_stock.md")
                self.assertTrue(any(expected_err in err for err in errors), errors)

        allowed_prose = (
            "159545 并非零溢价，买入前仍须查折溢价。\n"
            "港股通红筹并非一律 28% 税，须按发行人公告核验。\n"
            "严禁写末日二级卖出免 20% 个人税。\n"
        )
        errors, _ = pdf_common.lint_markdown_report(allowed_prose, "2026-11-26_1800_hk_stock.md")
        self.assertEqual(errors, [])

        playbook = self.root / "equity/state/RSI_PLAYBOOK.md"
        playbook_cases = (
            ("经验：159545 零溢价可直接买入。", "159545/159792 零溢价已撤回旧口径"),
            ("经验：红筹 28% 税。", "红筹股一刀切 28% 税已撤回旧口径"),
            ("经验：末日二级卖出免 20% 个人税。", "可转债末日二级卖出免 20% 个人税已撤回旧口径"),
        )
        self.advance("2026-11-29_1800")
        for line, expected_err in playbook_cases:
            with self.subTest(playbook_claim=line):
                self.assertTrue(any(expected_err in err for err in _check_playbook_retracted_claims(line)))
                playbook.write_text(f"# 复盘规则\n\n{line}\n", encoding="utf-8")
                result = self.lint("--precheck", "--strict")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(expected_err, result.stdout)

        playbook.write_text(
            "# 复盘规则\n\n"
            "- 严禁写 159545 零溢价；严禁笼统称红筹 28% 税；严禁写末日二级卖出免 20% 个人税。\n",
            encoding="utf-8",
        )
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_svg_chart_regression_fixes(self):
        # 1. Chart H6 with 13 items includes item #13 (no silent [:12] truncation)
        items_13 = [(f"测试标的{idx:02d}", float(20 - idx), f"结论{idx:02d}") for idx in range(1, 14)]
        h6_html = build_hk_stock_pdf.svg_chart_h6_ah_arbitrage_and_sectors({
            "chart_live": {"h6": {"items": items_13, "sector_strip": "十三标的完整性校验"}},
        })
        self.assertIn("测试标的13", h6_html)
        self.assertIn("结论13", h6_html)

        # 2. Chart H1 with as_of_short="11/26早" preserves leading "1" (not "1/26早")
        h1_html = build_hk_stock_pdf.svg_chart_h1_cycles({
            "chart_live": {"as_of_short": "11/26早", "hsi": 22300},
        })
        self.assertIn("11/26早 22,300", h1_html)
        self.assertNotIn(">1/26早 22,300<", h1_html)

        # 3. Chart H3 with negative ERP renders "-0.72%" and never "+-0.72%"
        h3_html = build_hk_stock_pdf.svg_chart_h3_peg_and_erp({
            "chart_live": {
                "h3": {
                    "erps": [
                        ("恒生指数 · 人民币锚", 8.10, "#009E73"),
                        ("沪深 300 · A 股锚", 5.80, "#0D9488"),
                        ("恒生指数 · 美元锚", 4.50, "#0072B2"),
                        ("标普 500 · 美股锚", -0.72, "#D55E00"),
                    ],
                },
            },
        })
        self.assertIn("-0.72%", h3_html)
        self.assertNotIn("+-0.72%", h3_html)

        # 4. Chart U6 uses unified 1:1 linear scale for positive +3.09% and negative -3.81%
        u6_html = build_us_stock_pdf.svg_chart_u6_sector_heatmap({
            "chart_live": {
                "u6": {
                    "date_short": "11/26",
                    "sectors": [
                        {"name": "能源 (XLE)", "pct": 3.09, "dd": -10.5},
                        {"name": "科技 (XLK)", "pct": -3.81, "dd": -18.2},
                    ],
                },
            },
        })
        pos_m = re.search(r'<rect[^>]*width="([0-9.]+)"[^>]*height="14"[^>]*/>\s*<text[^>]*>\+3\.09%</text>', u6_html)
        neg_m = re.search(r'<rect[^>]*width="([0-9.]+)"[^>]*height="14"[^>]*/>\s*<text[^>]*>-3\.81%</text>', u6_html)
        self.assertIsNotNone(pos_m, u6_html)
        self.assertIsNotNone(neg_m, u6_html)
        w_pos = float(pos_m.group(1))
        w_neg = float(neg_m.group(1))
        expected_ratio = 3.81 / 3.09
        actual_ratio = w_neg / w_pos
        self.assertLessEqual(abs(actual_ratio - expected_ratio) / expected_ratio, 0.05)

        # 5. Chart U5 with 11 banks dynamically scales SVG height > 288 without clipping
        banks_11 = [(f"华尔街大行{idx:02d}（2027年底）", 7800 + idx * 100, "#0072B2") for idx in range(1, 12)]
        u5_html = build_us_stock_pdf.svg_chart_u5_wall_street_forensic({
            "chart_live": {"spx": 7200, "u5": {"banks": banks_11}},
        })
        vb_m = re.search(r'viewBox="0 0 850 (\d+)"', u5_html)
        self.assertIsNotNone(vb_m, u5_html)
        svg_h = int(vb_m.group(1))
        self.assertGreater(svg_h, 288)
        last_y_m = re.search(r'<text[^>]*y="([0-9.]+)"[^>]*>华尔街大行11（2027年底）</text>', u5_html)
        self.assertIsNotNone(last_y_m, u5_html)
        self.assertLess(float(last_y_m.group(1)), svg_h)


if __name__ == "__main__":
    unittest.main()
