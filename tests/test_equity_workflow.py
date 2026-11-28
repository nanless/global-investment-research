import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "equity"))
import build_hk_stock_pdf
import build_us_stock_pdf
import pdf_common
from build_daily import extract_daily_meta, load_optional_charts
from lint_equity import (
    MARKETS, _check_ah_dividend_evidence, _check_market_index_quotes, _check_market_state_math,
    _check_playbook_retracted_claims, _check_release_snapshot, _check_rsi_metrics, _scan_text_for_gold_buy,
)

KPI_CARDS = [{"label": "数据", "val": "1", "sub": "测试"} for _ in range(4)]
WATCH = "mode_2_watch_brief"
ALL_CLOSED = "mode_3_index_changelog_only"


def holiday(day, kind, markets, **fields):
    return {"date_cst": day, "type": kind, "markets_affected": list(markets), "mode": WATCH, **fields}


class AhDividendPreflightTests(unittest.TestCase):
    def test_rejects_duplicate_pairs_and_receipt_dated_after_edition_cutoff(self):
        dividend = {
            "ordinary_cash_per_share": 0.2, "currency": "CNY", "period_start": "2025-01-01",
            "period_end": "2025-12-31", "published_date": "2026-04-15",
            "source_url": "https://www.sse.com.cn/disclosure/notice",
        }
        row = {
            "name": "双地标的", "a": "600030", "h": "06030.HK",
            "cash_dividends": {"a": dividend, "h": dict(dividend, cash_basis="southbound_cny")},
        }
        state = {
            "edition_id": "2026-11-28_1130",
            "cross_market_linkages": {"ah_premium_radar": {"benchmarks": [row]}},
        }
        self.assertEqual(_check_ah_dividend_evidence(state), [])
        radar = state["cross_market_linkages"]["ah_premium_radar"]
        radar["benchmarks"].insert(0, {"a": row["a"], "h": row["h"]})
        self.assertIn("同一 A/H 配对有重复记录", _check_ah_dividend_evidence(state)[0])
        radar["benchmarks"].pop(0)
        row["cash_dividends"]["h"]["published_date"] = "2026-11-29"
        self.assertIn("公告日晚于当前数据截点", _check_ah_dividend_evidence(state)[0])


class MarketComparisonTests(unittest.TestCase):
    def test_prospective_equity_snapshot_rejects_unavailable_index_quotes(self):
        state = {"edition_id": "2026-11-30_1130", "as_of_cst": "2026-11-30T11:45:00+08:00", "markets": {}}
        scenarios = (
            ("a_share", {"id": "idx_sh000001", "as_of": "2026-11-30 11:30 午收"}, None),
            ("a_share", {"id": "idx_sh000001", "as_of": "2026-11-30 11:26 午收"}, "午盘收盘晚于"),
            ("a_share", {"id": "idx_sh000001", "as_of": "2026-11-30 15:00 官收"}, "晚于本刊截点"),
            ("a_share", {"id": "idx_sh000001", "as_of": "2026-11-30 11:35 官收"}, "日终收盘晚于"),
            ("a_share", {"id": "idx_sh000001", "quote_date": "2026-11-29", "stale": True}, "无此市场"),
            ("a_share", {"id": "idx_sh000001", "quote_date": "2026-11-30"}, "日终收盘晚于"),
            ("a_share", {"id": "idx_sh000001"}, "须记录行情交易日"),
            ("a_share", {"id": "idx_sh000001", "quote_date": "2026-11-27", "stale": True}, None),
            ("hk_stock", {"id": "idx_hkHSI", "as_of": "2026-11-30 11:40 午盘前实盘"}, None),
            ("hk_stock", {"id": "idx_hkHSI", "as_of": "2026-11-30 11:40 午收"}, "午盘收盘晚于"),
            ("hk_stock", {"id": "idx_hkHSI", "quote_date": "2026-11-30", "quote_status": "盘中"}, "须记录有日期的观察时间"),
            ("us_stock", {"code": "SPX", "as_of": "2026-11-30 09:30 EST 盘中"}, "晚于本刊截点"),
        )
        for group, quote, problem in scenarios:
            with self.subTest(quote=quote):
                state["markets"] = {group: {"index_matrix": [{"value": 100, **quote}]}}
                errors = _check_market_index_quotes(state)
                if problem:
                    self.assertTrue(any(problem in error for error in errors), errors)
                else:
                    self.assertEqual(errors, [])

        state["as_of_cst"] = "2026-11-30T16:08:30+08:00"
        row = {"id": "idx_hkHSI", "value": 100, "as_of": "2026-11-30 16:08 官收"}
        state["markets"] = {"hk_stock": {"index_matrix": [row]}}
        self.assertEqual(_check_market_index_quotes(state), [])
        row["as_of"] = "2026-11-30 16:07 官收"
        self.assertIn("日终收盘晚于", _check_market_index_quotes(state)[0])
        row["as_of"] = "2026-11-30 官收"
        self.assertIn("日终收盘晚于", _check_market_index_quotes(state)[0])

    def test_cfets_equity_mirror_requires_published_fixing_at_gold_cutoff(self):
        gold = json.loads((ROOT / "gold/data_snapshot.json").read_bytes())
        state = json.loads((ROOT / "equity/state/market_state.json").read_bytes())
        gold.update(edition_id="2026-11-30_0730", as_of_short="2026-11-30 09:14", cfets_fixing_date="2026-11-30")
        state.update(edition_id=gold["edition_id"], as_of_cst="2026-11-30T09:20:00+08:00")
        mirror = state["markets"]["gold_mirror_readonly"]
        mirror.update(edition_id=gold["edition_id"], as_of_short=gold["as_of_short"])
        state["cross_market_linkages"]["rates_fx_chain"]["cfets_fixing_date"] = gold["cfets_fixing_date"]
        self.assertTrue(any("早于 CFETS 当日 09:15" in error for error in _check_release_snapshot(gold, state, [])))
        gold["as_of_short"] = mirror["as_of_short"] = "2026-11-30 09:15"
        self.assertEqual(_check_release_snapshot(gold, state, []), [])

    def test_close_change_uses_the_declared_previous_value(self):
        observation = {"code": "VIX", "value": 23.81, "change_pct": -11.16, "previous_value": 26.8}
        state = {"markets": {"us_stock": {"index_matrix": [observation]}}}
        self.assertEqual(_check_market_state_math(state), [])
        observation["previous_value"] = 28.29
        self.assertIn("与所列比较基准算得的 -15.84% 不一致", _check_market_state_math(state)[0])
        for previous in (0, float("nan"), 10**400):
            with self.subTest(previous=previous):
                observation["previous_value"] = previous
                self.assertIn("需要正数现值、比较值与有限涨跌幅", _check_market_state_math(state)[0])


class EquityWorkflowTests(unittest.TestCase):
    def test_help_explains_modes_without_linting(self):
        for flag in ("--help", "-h"):
            with self.subTest(flag=flag):
                result = self.lint(flag)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("--plan YYYY-MM-DD_HHMM", result.stdout)
                self.assertIn("--strict", result.stdout)
                self.assertNotIn("Summary:", result.stdout)
        self.assertEqual(self.lint("--unexpected").returncode, 2)

    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        equity = self.root / "equity"
        (equity / "daily/archive/2026-11").mkdir(parents=True)
        (equity / "state").mkdir()
        (self.root / "gold").mkdir()
        for module in ("edition_validation.py", "chart_input.py"):
            shutil.copy2(ROOT / "gold" / module, self.root / "gold" / module)
        for script in (ROOT / "equity").glob("*.py"):
            shutil.copy2(script, equity / script.name)
        scripts = self.root / "scripts"
        scripts.mkdir()
        for module in ("source_links.py", "svg_geometry.py", "visual_widgets.py", "ah_dividends.py", "inventory_evidence.py", "quote_sessions.py"):
            shutil.copy2(ROOT / "scripts" / module, scripts / module)
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
            "data_caveats": [],
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
            "timezone": "Asia/Shanghai", "as_of": "2026-11-25",
            "coverage": {"start_date": "2026-11-01", "end_date": "2027-06-30", "verified_on": "2026-11-25",
                         "vix_schedule_source": "https://www.cboe.com/about/hours/us-options/"},
            "vix_session_exceptions": {"2026-11-26": {"official_close_et": None, "windows_et": []}},
            "calendar_overrides": [{
                "id": "thanksgiving", "date": "2026-11-26", "end_date": "2026-11-26", "markets": ["US_EQUITY"],
                "overlay_mode": "A",
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

    def test_preflight_blocks_a_new_cash_quote_falsely_dated_on_a_closed_day(self):
        self.advance("2026-11-29_1800")
        quote = {"id": "idx_sh000001", "code": "000001", "value": 3600.0,
                 "quote_date": "2026-11-29", "quote_status": "官收"}
        self.state["markets"]["a_share"]["index_matrix"] = [quote]
        self.save()
        invalid = self.lint("--precheck", "--strict")
        self.assertEqual(invalid.returncode, 1, invalid.stdout + invalid.stderr)
        self.assertIn("该日无此市场的现金交易", invalid.stdout)
        quote.update(quote_date="2026-11-27", stale=True)
        self.save()
        valid = self.lint("--precheck", "--strict")
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)

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
        pending = {"market": "us_stock", "item": "待补非农数据", "due_session": "2026-11-26_1800"}
        self.state["pending_backfills"].append(pending)
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("数据故障须在 pending_backfills", result.stdout)
        pending["item"] = "交易所公告服务中断"
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_source_outage_backfill_id_tracks_the_same_item_when_review_changes(self):
        edition = "2026-11-26_0730"
        self.advance(edition)
        outage = {
            "kind": "source_outage", "reason": "交易所公告服务中断", "evidence_url": "https://www.nyse.com/",
            "backfill_id": "nyse_notice_outage", "next_review_session": "2026-11-26_1800",
        }
        self.state["publication_exceptions"] = {"edition_id": edition, "markets": {"us_stock": outage}}
        pending = {"id": "nyse_notice_outage", "market": "us_stock", "item": "复核交易所公告服务恢复时间",
                   "due_session": "2026-11-26_1800"}
        self.state["pending_backfills"] = [pending]
        self.issue("a_share", "light")
        self.issue("hk_stock", "light")
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        for changed_entry in ({"id": "other_id"}, {"due_session": "2026-11-27_0730"}):
            with self.subTest(changed_entry=changed_entry):
                self.state["pending_backfills"] = [{**pending, "item": outage["reason"], **changed_entry}]
                self.save()
                result = self.lint("--precheck", "--strict")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("数据故障须在 pending_backfills", result.stdout)

        self.state["pending_backfills"] = [pending, {**pending, "item": "重复同一待补编号"}]
        self.save()
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("数据故障须在 pending_backfills", result.stdout)

        outage.update(next_review_session="2026-11-27_0730", evidence_url="https://www.nyse.com/markets/status")
        pending.update(due_session="2026-11-27_0730", item="新查公告服务仍在维护，改下班复核")
        self.state["pending_backfills"] = [pending]
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

    def test_new_edition_requires_an_explicit_data_caveats_array(self):
        self.advance("2026-11-28_1800")
        del self.state["data_caveats"]
        self.save()
        historical = self.lint("--precheck", "--strict")
        self.assertEqual(historical.returncode, 0, historical.stdout + historical.stderr)

        self.advance("2026-11-29_0730")
        missing = self.lint("--precheck", "--strict")
        self.assertEqual(missing.returncode, 1, missing.stdout + missing.stderr)
        self.assertIn("缺少 data_caveats 数组", missing.stdout)

        self.state["data_caveats"] = []
        self.save()
        current = self.lint("--precheck", "--strict")
        self.assertEqual(current.returncode, 0, current.stdout + current.stderr)

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

    def _install_clean_ssot_dbs(self):
        """Populate matching flagship Appendix 2 tables plus valid 3 SSOT databases in temp workspace."""
        equity = self.root / "equity"
        edition = self.state["edition_id"]
        a_codes = [f"6000{i:02d}" for i in range(1, 12)] + ["601899"]
        hk_codes = [f"000{i:02d}" for i in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 16)]
        us_codes = [f"STK{chr(ord('A') + i)}" for i in range(12)]
        market_specs = (
            ("a_share", "a-share", [(c, c) for c in a_codes]),
            ("hk_stock", "hk-stock", [(c, f"{c}.HK") for c in hk_codes]),
            ("us_stock", "us-stock", [(c, c) for c in us_codes]),
        )
        dossiers = {}
        for mkt, prefix, pairs in market_specs:
            rows = ["| 赛道 | 标的 | 估值 |", "| --- | --- | --- |"]
            for idx, (disp_code, key_code) in enumerate(pairs, 1):
                rows.append(f"| 行业{idx} | 标的{idx} `{disp_code}` | 10.0x |")
                dkey = f"{prefix}:{key_code}"
                dossiers[dkey] = {
                    "moat": f"{dkey} 护城河与商业壁垒说明",
                    "financials": f"{dkey} 现金流与净资产收益率稳健",
                    "valuation_anchor": f"{dkey} 历史估值分位与安全锚区间",
                    "shareholder_flow": f"{dkey} 分红回购与机构资金流向",
                    "catalysts": f"{dkey} 下季财报与资本开支观察催化第 {idx} 项",
                    "bear_case": f"{dkey} 行业景气下行与竞争加剧风险第 {idx} 项",
                    "action_etf": (
                        "红灯观察锁，严禁列为当下底座，等待信号确认"
                        if key_code == "601899"
                        else f"{dkey} 结合安全锚分批观察并配低费率行业 ETF"
                    ),
                }
            (equity / f"{mkt}_market_report_2026_11.md").write_text(
                "# 权益手册\n\n覆盖期铜。\n\n## 附表二\n\n" + "\n".join(rows) + "\n",
                encoding="utf-8",
            )
            meta_path = equity / f"report_meta_{mkt}.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["chart_live"]["stock_pool_count"] = len(pairs)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            self.state["markets"][mkt]["stock_pool_count"] = len(pairs)

        self.state["data_caveats"] = []
        self.save()

        req_channels = (
            ("bonds", "债券与债券 ETF"),
            ("funds_wm", "公募基金与银行理财"),
            ("reverse_repo", "活钱与国债逆回购"),
            ("qdii_mrf", "场内外 QDII 与香港互认"),
            ("large_cds", "人民币银行存款全家桶"),
            ("convertible_bonds", "可转债"),
            ("c_reits", "公募 REITs"),
            ("commodity_etfs", "非黄金大宗商品渠道"),
        )
        ma = {
            "edition_id": edition,
            "channels": [
                {
                    "id": cid,
                    "name": cname,
                    "key_metrics": [{"label": "参考收益", "value": "2.0%–3.0%"}],
                    "products": [
                        {
                            "code": f"CH{idx:03d}",
                            "name": f"{cname}代表产品",
                            "metric": "规模稳定",
                            "fee": "0.15%/年",
                            "note": "费率透明，按用钱期限匹配",
                        }
                    ],
                    "rules_and_redlines": [f"{cname}合规持有与流动性管理规则"],
                }
                for idx, (cid, cname) in enumerate(req_channels, 1)
            ],
            "allocation_templates": [
                {
                    "id": "steady_core",
                    "name": "稳健防御模板",
                    "slices": [
                        {"channel": "活钱现金", "weight": "40%", "vehicles": "逆回购与短融"},
                        {"channel": "纯债底仓", "weight": "60%", "vehicles": "国债与短债基"},
                    ],
                }
            ],
        }
        etfs = [
            {
                "code": f"510{idx:03d}",
                "name": f"宽基示例ETF{idx:03d}",
                "market": "a-share" if idx < 50 else "us-stock",
                "channel": "境内场内" if idx < 50 else "离岸美股",
                "fee_total_pct": "0.15%",
                "premium_status": "normal",
                "thesis_deep": f"追踪核心指数样本 {idx}",
                "risk_boundary": "注意股市波动与仓位控制",
                "action_role": "核心宽基观察",
            }
            for idx in range(100)
        ]
        eu = {
            "edition_id": edition,
            "total_etfs": 100,
            "counts_by_market": {"a-share": 50, "us-stock": 50},
            "counts_by_channel": {"境内场内": 50, "离岸美股": 50},
            "etfs": etfs,
        }
        dd = {
            "edition_id": edition,
            "total_stocks": len(dossiers),
            "dossiers": dossiers,
        }
        (equity / "state/multi_asset_channels.json").write_text(json.dumps(ma, ensure_ascii=False), encoding="utf-8")
        (equity / "state/etf_universe.json").write_text(json.dumps(eu, ensure_ascii=False), encoding="utf-8")
        (equity / "state/deep_dossiers.json").write_text(json.dumps(dd, ensure_ascii=False), encoding="utf-8")
        return ma, eu, dd

    def test_one_directional_edition_time_window_rejects_too_early(self):
        self.advance("2026-11-29_1800")
        self.gold["cfets_fixing_date"] = "2026-11-29"
        self.state["cross_market_linkages"]["rates_fx_chain"]["cfets_fixing_date"] = "2026-11-29"

        # 12:00 noon masquerading as 18:00 evening (6 hours too early) must be rejected
        for stamp, iso, should_pass in (
            ("2026-11-29 12:00", "2026-11-29T12:00:00+08:00", False),
            ("2026-11-29 17:54", "2026-11-29T17:54:00+08:00", False),
            ("2026-11-29 17:55", "2026-11-29T17:55:00+08:00", True),
            ("2026-11-30 00:00", "2026-11-30T00:00:00+08:00", True),
            ("2026-11-30 00:01", "2026-11-30T00:01:00+08:00", False),
        ):
            with self.subTest(stamp=stamp):
                self.gold["as_of_short"] = stamp
                self.state["as_of_cst"] = iso
                self.state["markets"]["gold_mirror_readonly"]["as_of_short"] = stamp
                self.save()
                result = self.lint("--precheck", "--strict")
                if should_pass:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                else:
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn("班次前 5 分钟至班次后 6 小时内", result.stdout)

        # Daily report chart_live.as_of_full also enforces the [-5m, +6h] one-directional window
        self.advance("2026-11-26_1800")
        a_daily = self.issue("a_share", "main")
        self.issue("hk_stock", "main")
        self.issue("us_stock", "holiday_watch")
        meta, body = extract_daily_meta(a_daily.read_text(encoding="utf-8"), a_daily)
        meta["chart_live"]["as_of_full"] = "2026-11-26 12:00 北京时间"
        a_daily.write_text(
            f"{body}\n\n<!-- DAILY_META_JSON {json.dumps(meta, ensure_ascii=False)} -->\n",
            encoding="utf-8",
        )
        result = self.lint("--precheck", "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("chart_live.as_of_full 须在班次前 5 分钟至班次后 6 小时内", result.stdout)

    def test_gold_tier0_expanded_mutex_across_prose_and_ssot_dbs(self):
        # 1. Expanded prose regex checks (定投黄金 / 逢低配置 518850 / 吸纳 159934)
        for bad_line in (
            "建议定投黄金 ETF 分散风险",
            "可逢低配置 518850 黄金",
            "分批吸纳 159934 做底仓",
        ):
            self.assertTrue(_scan_text_for_gold_buy("report", bad_line), bad_line)
        for guarded_line in (
            "黄金红灯停期间暂不定投黄金 ETF",
            "等黄灯确认后再配置 518850",
            "严禁吸纳 159934",
        ):
            self.assertFalse(_scan_text_for_gold_buy("report", guarded_line), guarded_line)

        # 2. End-to-end Gate C2 under Gold Tier 0 across etf_universe / multi_asset_channels / deep_dossiers
        self.advance("2026-11-29_1800")
        self.gold.update(tier_code="Tier 0", new_buy_allowed=False, tier1_passed=1)
        self.state["markets"]["gold_mirror_readonly"].update(
            tier_code="Tier 0", new_buy_allowed=False, gates_passed="1/4",
        )
        ma_base, eu_base, dd_base = self._install_clean_ssot_dbs()
        state_dir = self.root / "equity/state"

        baseline = self.lint("--precheck", "--strict")
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)

        # (a) 159934 without gold_locked=True and forbidden action_role
        eu_bad = deepcopy(eu_base)
        eu_bad["etfs"][0].update(code="159934", name="易方达黄金ETF", action_role="逢低配置")
        (state_dir / "etf_universe.json").write_text(json.dumps(eu_bad, ensure_ascii=False), encoding="utf-8")
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("Gate C2 跨项目硬冲突 (etf_universe.json:159934)", res.stdout)
        (state_dir / "etf_universe.json").write_text(json.dumps(eu_base, ensure_ascii=False), encoding="utf-8")

        # (b) multi_asset_channels.json prose directive ("逢低配置 518850")
        ma_bad_prose = deepcopy(ma_base)
        ma_bad_prose["channels"][0]["rules_and_redlines"].append("当前可逢低配置 518850 对冲波动")
        (state_dir / "multi_asset_channels.json").write_text(json.dumps(ma_bad_prose, ensure_ascii=False), encoding="utf-8")
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("Gate C2 跨项目硬冲突", res.stdout)

        # (c) multi_asset_channels.json gold product missing explicit red-light lock note
        ma_bad_prod = deepcopy(ma_base)
        ma_bad_prod["channels"][-1]["products"].append({
            "code": "518880", "name": "华安黄金ETF", "metric": "流动充裕", "fee": "0.60%/年", "note": "场内主流商品标的",
        })
        (state_dir / "multi_asset_channels.json").write_text(json.dumps(ma_bad_prod, ensure_ascii=False), encoding="utf-8")
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("Gate C2 跨项目硬冲突 (multi_asset_channels.json:518880)", res.stdout)
        (state_dir / "multi_asset_channels.json").write_text(json.dumps(ma_base, ensure_ascii=False), encoding="utf-8")

        # (d) deep_dossiers.json gold stock marked as green base (当下底座)
        dd_bad_base = deepcopy(dd_base)
        dd_bad_base["dossiers"]["a-share:601899"]["action_etf"] = "🟢 当下底座，核心长期持有"
        (state_dir / "deep_dossiers.json").write_text(json.dumps(dd_bad_base, ensure_ascii=False), encoding="utf-8")
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("Gate C2 跨项目硬冲突 (deep_dossiers.json:a-share:601899.action_etf)", res.stdout)

        # (e) deep_dossiers.json unguarded buy-gold directive in stock dossier
        dd_bad_buy = deepcopy(dd_base)
        dd_bad_buy["dossiers"]["a-share:600001"]["action_etf"] = "建议同步定投黄金 ETF 518850"
        (state_dir / "deep_dossiers.json").write_text(json.dumps(dd_bad_buy, ensure_ascii=False), encoding="utf-8")
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("Gate C2 跨项目硬冲突 (deep_dossiers.json:a-share:600001.action_etf:L1)", res.stdout)

    def test_ssot_databases_deep_validation(self):
        self.advance("2026-11-29_1800")
        ma_base, eu_base, dd_base = self._install_clean_ssot_dbs()
        state_dir = self.root / "equity/state"

        baseline = self.lint("--precheck", "--strict")
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)

        def write_all(ma=ma_base, eu=eu_base, dd=dd_base):
            (state_dir / "multi_asset_channels.json").write_text(json.dumps(ma, ensure_ascii=False), encoding="utf-8")
            (state_dir / "etf_universe.json").write_text(json.dumps(eu, ensure_ascii=False), encoding="utf-8")
            (state_dir / "deep_dossiers.json").write_text(json.dumps(dd, ensure_ascii=False), encoding="utf-8")

        # 1. Duplicate channel ID
        ma_dup = deepcopy(ma_base)
        ma_dup["channels"].append(deepcopy(ma_base["channels"][0]))
        write_all(ma=ma_dup)
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("存在重复渠道 id: bonds", res.stdout)

        # 2. allocation_templates weights != 100%
        ma_wt = deepcopy(ma_base)
        ma_wt["allocation_templates"][0]["slices"][1]["weight"] = "40%"
        write_all(ma=ma_wt)
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("精确权重之和=80.00% ≠ 100%", res.stdout)

        # 3. Unwarned recommendation of suspended 968118 (both product & prose); warned mention passes
        ma_968_prod = deepcopy(ma_base)
        ma_968_prod["channels"][3]["products"][0].update(code="968118", name="摩根太平洋科技", note="业绩优秀优先考虑")
        write_all(ma=ma_968_prod)
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("未带暂停/退市/避坑警示直接推荐受限代码 '968118'", res.stdout)

        ma_968_prose = deepcopy(ma_base)
        ma_968_prose["channels"][3]["rules_and_redlines"].append("内地投资者可关注 968118 互认基金")
        write_all(ma=ma_968_prose)
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("未带暂停/退市/避坑警示提及受限代码 968118", res.stdout)

        ma_968_warned = deepcopy(ma_base)
        ma_968_warned["channels"][3]["rules_and_redlines"].append("968118 已暂停申购，切忌盲目跟风误配")
        write_all(ma=ma_968_warned)
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        # 4. etf_universe.json summary counter mismatches
        for label, mutate, expected_msg in (
            ("total_etfs", lambda u: u.update(total_etfs=99), "total_etfs (99) ≠ len(etfs) (100)"),
            ("counts_by_market", lambda u: u["counts_by_market"].update({"a-share": 49}), "counts_by_market"),
            ("counts_by_channel", lambda u: u["counts_by_channel"].update({"离岸美股": 49}), "counts_by_channel"),
        ):
            with self.subTest(etf_counter=label):
                eu_bad = deepcopy(eu_base)
                mutate(eu_bad)
                write_all(eu=eu_bad)
                res = self.lint("--precheck", "--strict")
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertIn(expected_msg, res.stdout)

        # 5. Cross-stock template copy-paste (>10 identical catalysts blocked; ==10 allowed)
        a_keys = [k for k in dd_base["dossiers"] if k.startswith("a-share:")]
        dd_copy_ok = deepcopy(dd_base)
        for k in a_keys[:10]:
            dd_copy_ok["dossiers"][k]["catalysts"] = "完全相同的行业季度催化模板文案"
        write_all(dd=dd_copy_ok)
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        dd_copy_bad = deepcopy(dd_copy_ok)
        dd_copy_bad["dossiers"][a_keys[10]]["catalysts"] = "完全相同的行业季度催化模板文案"
        write_all(dd=dd_copy_bad)
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("完全复制粘贴相同 catalysts 模板（上限 10 只）", res.stdout)

        # 6. edition_id drift on each of the 3 SSOT files
        for db_name, kwargs in (
            ("multi_asset_channels.json", {"ma": {**ma_base, "edition_id": "2026-11-26_0730"}}),
            ("etf_universe.json", {"eu": {**eu_base, "edition_id": "2026-11-26_0730"}}),
            ("deep_dossiers.json", {"dd": {**dd_base, "edition_id": "2026-11-26_0730"}}),
        ):
            with self.subTest(edition_drift=db_name):
                write_all(**kwargs)
                res = self.lint("--precheck", "--strict")
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertIn(f"{db_name} edition_id", res.stdout)
                self.assertIn("≠ market_state.json", res.stdout)

    def test_rsi_open_finding_and_daily_deprecated_pdf_link_blocked(self):
        # 1. RSI status == "open" blocked in both review_closure.findings & top-level findings
        dims = list("abcdef")
        base_run = {
            "run_id": "2026-11-26_1800",
            "scores": dict.fromkeys(dims, 5),
            "total_score": 30,
            "max_score": 30,
        }
        for payload, should_fail in (
            ({**base_run, "review_closure": {"reviewer_completed": True, "findings": [{"description": "待修", "status": "open"}]}}, True),
            ({**base_run, "findings": [{"description": "顶层未闭环", "status": "open"}]}, True),
            ({**base_run, "review_closure": {"reviewer_completed": True, "findings": [{"description": "已披露", "status": "disclosed_caveat"}]}}, False),
            ({**base_run, "review_closure": {"reviewer_completed": True, "findings": [{"description": "已解决", "status": "resolved"}]}}, False),
            ({**base_run, "review_closure": {"reviewer_completed": True, "findings": [{"description": "待官源", "status": "deferred_data"}]}}, False),
        ):
            with self.subTest(rsi_payload=payload):
                errs = _check_rsi_metrics({"score_dimensions": dims, "runs": [payload]})
                self.assertEqual(bool(errs), should_fail, errs)

        self.advance("2026-11-26_1800")
        a_daily = self.issue("a_share", "main")
        self.issue("hk_stock", "main")
        self.issue("us_stock", "holiday_watch")

        rsi_path = self.root / "equity/state/rsi_metrics.json"
        rsi_path.write_text(json.dumps({
            "score_dimensions": dims,
            "runs": [{
                **base_run,
                "review_closure": {
                    "reviewer_completed": True,
                    "findings": [{"description": "图表口径未闭环", "status": "open"}],
                },
            }],
        }, ensure_ascii=False), encoding="utf-8")
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("存在未闭环 finding (status=open)", res.stdout)

        # Close RSI finding cleanly, then test deprecated .pdf dead link inside equity daily .md
        rsi_path.write_text(json.dumps({
            "score_dimensions": dims,
            "runs": [{
                **base_run,
                "review_closure": {
                    "reviewer_completed": True,
                    "findings": [{"description": "图表口径已披露", "status": "disclosed_caveat"}],
                },
            }],
        }, ensure_ascii=False), encoding="utf-8")
        original_md = a_daily.read_text(encoding="utf-8")
        a_daily.write_text(
            original_md.replace("覆盖期铜。", "覆盖期铜。参考 [下载PDF](2026-11-26_1800_a_share.pdf)。"),
            encoding="utf-8",
        )
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("纯网页版严禁保留已弃用的 PDF/Word 或离线附件链接", res.stdout)

        # External official HTTPS PDF citation remains allowed
        a_daily.write_text(
            original_md.replace("覆盖期铜。", "覆盖期铜。参考 [交易所公告](https://www.sse.com.cn/notice.pdf)。"),
            encoding="utf-8",
        )
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_chart_a2_futures_sign_contradiction_blocked(self):
        self.advance("2026-11-26_1800")
        a_daily = self.issue("a_share", "main")
        self.issue("hk_stock", "main")
        self.issue("us_stock", "holiday_watch")
        meta, body = extract_daily_meta(a_daily.read_text(encoding="utf-8"), a_daily)

        # Negative ann=-20.5 paired with "基差 -50.75" must be rejected as sign inversion
        meta["chart_live"]["a2"] = {
            "title": "A股宽基分化与股指期货基差",
            "sub": "截至 2026-11-26 18:00 北京时间",
            "indices": [["沪深300", -0.8, "#0072B2"], ["中证1000", -1.9, "#D55E00"]],
            "futures": [
                ["中证1000期货 IM", -20.5, "贴水加深", "基差 -50.75 点", "#D55E00", "#FEF2F2"],
            ],
            "takeaway": "小盘期指维持深度贴水。",
            "note": "数据来源：中金所官收。",
        }
        a_daily.write_text(
            f"{body}\n\n<!-- CHART_A2 -->\n\n<!-- DAILY_META_JSON {json.dumps(meta, ensure_ascii=False)} -->\n",
            encoding="utf-8",
        )
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("CHART_A2 正负号反转", res.stdout)

        # Flipping ann to positive 20.5 for discount ("基差 -50.75") passes cleanly
        meta["chart_live"]["a2"]["futures"][0][1] = 20.5
        a_daily.write_text(
            f"{body}\n\n<!-- CHART_A2 -->\n\n<!-- DAILY_META_JSON {json.dumps(meta, ensure_ascii=False)} -->\n",
            encoding="utf-8",
        )
        res_ok = self.lint("--precheck", "--strict")
        self.assertEqual(res_ok.returncode, 0, res_ok.stdout + res_ok.stderr)

    def test_chart_a2_futures_premium_positive_ann_blocked(self):
        self.advance("2026-11-26_1800")
        a_daily = self.issue("a_share", "main")
        self.issue("hk_stock", "main")
        self.issue("us_stock", "holiday_watch")
        meta, body = extract_daily_meta(a_daily.read_text(encoding="utf-8"), a_daily)

        meta["chart_live"]["a2"] = {
            "title": "A股宽基分化与股指期货基差",
            "sub": "截至 2026-11-26 18:00 北京时间",
            "indices": [["沪深300", 0.9, "#0072B2"]],
            "futures": [
                ["上证50期货 IH", 6.2, "小幅升水", "基差 +12.50 点", "#009E73", "#ECFDF5"],
            ],
            "takeaway": "大盘期指小幅升水。",
            "note": "数据来源：中金所官收。",
        }
        a_daily.write_text(
            f"{body}\n\n<!-- CHART_A2 -->\n\n<!-- DAILY_META_JSON {json.dumps(meta, ensure_ascii=False)} -->\n",
            encoding="utf-8",
        )
        res = self.lint("--precheck", "--strict")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("CHART_A2 正负号反转", res.stdout)

        meta["chart_live"]["a2"]["futures"][0][1] = -6.2
        a_daily.write_text(
            f"{body}\n\n<!-- CHART_A2 -->\n\n<!-- DAILY_META_JSON {json.dumps(meta, ensure_ascii=False)} -->\n",
            encoding="utf-8",
        )
        res_ok = self.lint("--precheck", "--strict")
        self.assertEqual(res_ok.returncode, 0, res_ok.stdout + res_ok.stderr)

    def test_midday_1130_plan_matrix_and_window_validation(self):
        # 1. Plan matrix with legacy 2-item us_thanksgiving_2026 still yields holiday_watch on 2026-11-27_1130
        for session, expected in (
            ("2026-11-27_1130", ("main", "main", "holiday_watch")),
            ("2026-11-28_1130", (None, None, None)),
            ("2026-11-29_1130", (None, None, None)),
            ("2026-11-30_1130", ("main", "main", "main")),
            ("2026-12-01_1130", ("main", "main", "main")),
            ("2026-12-24_1130", ("main", "holiday_watch", "main")),
            ("2026-12-25_1130", ("main", "holiday_watch", "holiday_watch")),
            ("2027-01-01_1130", (None, None, "main")),
            ("2027-02-08_1130", ("holiday_watch", "holiday_watch", "main")),
        ):
            with self.subTest(session=session):
                self.assertEqual(self._types(session), expected)

        # 2. Explicit 3-item affected_sessions on weekday-following single-day US holiday passes & plans holiday_watch
        self.state["calendar_overrides"][0]["affected_sessions"] = [
            "2026-11-26_1800", "2026-11-27_0730", "2026-11-27_1130",
        ]
        cal_path = self.root / "gold/market_calendar.json"
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
        cal["calendar_overrides"][0]["affected_editions"] = [
            "2026-11-26_1800", "2026-11-27_0730", "2026-11-27_1130",
        ]
        cal_path.write_text(json.dumps(cal, ensure_ascii=False), encoding="utf-8")
        self.save()
        self.assertEqual(self._types("2026-11-27_1130"), ("main", "main", "holiday_watch"))

        # 3. Single-day US holiday followed by Saturday (Black Friday 2026-11-27 -> Sat 2026-11-28) rejects 2026-11-28_1130
        bad_bf = deepcopy(self.state)
        bad_bf["calendar_overrides"][1]["affected_sessions"] = [
            "2026-11-27_1800", "2026-11-28_0730", "2026-11-28_1130",
        ]
        self.state_path.write_text(json.dumps(bad_bf, ensure_ascii=False), encoding="utf-8")
        res_bf = self.lint("--plan", "2026-11-27_1800")
        self.assertNotEqual(res_bf.returncode, 0)
        self.save()

        # 4. Full 1130 precheck + optional index_matrix + window boundaries (11:24 reject, 11:25 pass, 17:30 pass, 17:31 reject)
        self.advance("2026-11-27_1130")
        self.state["index_matrix"] = {"shcomp": {"close": 4010.2, "chg_pct": 0.35}}
        self.save()
        self.issue("a_share", "main")
        self.issue("hk_stock", "main")
        self.issue("us_stock", "holiday_watch")
        res_mid = self.lint("--precheck", "--strict")
        self.assertEqual(res_mid.returncode, 0, res_mid.stdout + res_mid.stderr)

        for stamp, iso, should_pass in (
            ("2026-11-27 11:24", "2026-11-27T11:24:00+08:00", False),
            ("2026-11-27 11:25", "2026-11-27T11:25:00+08:00", True),
            ("2026-11-27 17:30", "2026-11-27T17:30:00+08:00", True),
            ("2026-11-27 17:31", "2026-11-27T17:31:00+08:00", False),
        ):
            with self.subTest(midday_window=stamp):
                self.gold["as_of_short"] = stamp
                self.state["as_of_cst"] = iso
                self.state["markets"]["gold_mirror_readonly"]["as_of_short"] = stamp
                self.save()
                for mkt in MARKETS:
                    daily_p = self.root / "equity" / self.state["markets"][mkt]["latest_daily"]
                    meta, body = extract_daily_meta(daily_p.read_text(encoding="utf-8"), daily_p)
                    meta["chart_live"]["as_of_full"] = f"{stamp} 北京时间"
                    daily_p.write_text(
                        f"{body}\n\n<!-- DAILY_META_JSON {json.dumps(meta, ensure_ascii=False)} -->\n",
                        encoding="utf-8",
                    )
                res_win = self.lint("--precheck", "--strict")
                if should_pass:
                    self.assertEqual(res_win.returncode, 0, res_win.stdout + res_win.stderr)
                else:
                    self.assertEqual(res_win.returncode, 1, res_win.stdout)
                    self.assertIn("班次前 5 分钟至班次后 6 小时内", res_win.stdout)

        # 5. pdf_common allows 07:30 US report deferring after-hours to 11:30 midday & blocks fetch_kline_data.py
        errs_ok, _ = pdf_common.lint_markdown_report(
            "美股 09:00 盘后终盘由 11:30 午刊封账。", "2026-11-27_0730_us_stock.md"
        )
        self.assertEqual(errs_ok, [])
        errs_leak, _ = pdf_common.lint_markdown_report(
            "参考 fetch_kline_data.py 拉取行情。", "2026-11-27_1130_a_share.md"
        )
        self.assertTrue(any("fetch_kline_data.py" in e for e in errs_leak), errs_leak)

    def test_gate_c2_catches_gold_buy_in_market_state_rates_and_nonus(self):
        self.advance("2026-11-29_1800")
        self.gold.update(tier_code="Tier 0", new_buy_allowed=False, tier1_passed=1)
        self.state["markets"]["gold_mirror_readonly"].update(
            tier_code="Tier 0", new_buy_allowed=False, gates_passed="1/4",
        )
        self._install_clean_ssot_dbs()

        # Baseline with schema-valid, guarded wording in top-level rates_bonds_core & non_us_global_satellite passes cleanly
        self.state["rates_bonds_core"] = {
            "as_of": "2026-11-29 18:00",
            "lamp": "yellow",
            "lamp_label": "黄灯分化 · 短债筑盾",
            "headline": "短中久期利率债稳守，黄金红灯停期暂不新买黄金。",
            "cn_rates": {
                "cgb2y_pct": 1.21,
                "cgb10y_pct": 1.60,
                "cgb30y_pct": 2.06,
                "gc001_pct": 1.41,
                "dr001_pct": 1.28,
            },
            "us_rates": {
                "us2y_pct": 4.61,
                "us10y_pct": 4.80,
                "us30y_pct": 5.24,
                "dfii10_pct": 2.60,
                "sofr_pct": 3.94,
            },
            "cn_us_10y_spread_bp": -320,
            "unhedged_usd_fx_drag": {
                "usd_cny_spot": 6.66,
                "cfets_cny_fixing": 6.90,
                "real_rmb_drag_range": "-1.0% 至 -2.5%",
                "summary": "未锁汇美元短债须计入汇兑波动。",
            },
            "duration_stance": {"summary": "短端筑盾、长端控久期。"},
            "key_etfs": [
                {"id": "etf_511360", "code": "511360", "name": "海富通短融ETF", "kline_id": "etf_511360"},
            ],
        }
        self.state["non_us_global_satellite"] = {
            "as_of": "2026-11-29 18:00",
            "headline": "日欧台韩印非美严控溢价，严禁新买黄金 518880。",
            "allocation_guardrail": "非美卫星严控溢价与单区仓位。",
            "markets": [
                {
                    "id": mid,
                    "name": mname,
                    "lamp": "yellow",
                    "lamp_label": "黄灯观察",
                    "kline_id": kid,
                    "access_grade": "A 级 · 平价观察",
                    "benchmarks": [{"name": bname, "code": bcode, "value": bval, "change_pct": 0.5}],
                    "onshore_vehicles": [{"code": "513800", "name": "境内替代标的"}],
                    "offshore_vehicles": [{"code": "VXUS", "name": "离岸分散标的"}],
                    "warning": "黄金红灯停期暂不新买黄金，严控溢价与汇率波动。",
                }
                for mid, mname, kid, bname, bcode, bval in (
                    ("jp", "日本股市", "idx_N225", "日经225", "N225", 58700.0),
                    ("eu", "欧洲股市", "idx_GDAXI", "德国DAX", "GDAXI", 25200.0),
                    ("tw_kr", "中国台湾与韩国股市", "idx_TWII", "台湾加权指数", "TWII", 39300.0),
                    ("in", "印度股市", "idx_NSEI", "印度Nifty50", "NSEI", 25700.0),
                )
            ],
        }
        self.save()
        res_ok = self.lint("--precheck", "--strict")
        self.assertEqual(res_ok.returncode, 0, res_ok.stdout + res_ok.stderr)

        # (a) Forbidden Gold buy instruction inside rates_bonds_core must be caught by Gate C2
        self.state["rates_bonds_core"]["headline"] = "建议今日立即买入黄金 ETF 518880 对冲美债波动。"
        self.save()
        res_rates = self.lint("--precheck", "--strict")
        self.assertEqual(res_rates.returncode, 1, res_rates.stdout)
        self.assertIn("Gate C2", res_rates.stdout)

        # Restore rates_bonds_core; (b) forbidden Gold buy instruction inside non_us_global_satellite must also be caught
        self.state["rates_bonds_core"]["headline"] = "短中久期利率债稳守，黄金红灯停期暂不新买黄金。"
        self.state["non_us_global_satellite"]["markets"][0]["warning"] = "可逢低配置 518850 黄金分散非美汇率波动。"
        self.save()
        res_nonus = self.lint("--precheck", "--strict")
        self.assertEqual(res_nonus.returncode, 1, res_nonus.stdout)
        self.assertIn("Gate C2", res_nonus.stdout)

    def test_policy_calendar_validation_gold_lock_and_filename_leak_guards(self):
        # 1. Internal filename leak regexes block policy_calendar.json, realtime_monitor.py, wechat_notify.py in prose
        for leaked in ("policy_calendar.json", "realtime_monitor.py", "wechat_notify.py"):
            with self.subTest(prose_leak=leaked):
                errs_md, _ = pdf_common.lint_markdown_report(
                    f"详情参见 {leaked} 自动更新。", "2026-11-27_1130_a_share.md"
                )
                self.assertTrue(any(leaked in e for e in errs_md), errs_md)

        # 2. End-to-end lint_equity.py validation on policy_calendar.json under Gold Tier 0
        self.advance("2026-11-29_1800")
        self.gold.update(tier_code="Tier 0", new_buy_allowed=False, tier1_passed=1)
        self.state["markets"]["gold_mirror_readonly"].update(
            tier_code="Tier 0", new_buy_allowed=False, gates_passed="1/4",
        )
        self._install_clean_ssot_dbs()

        pc_path = self.root / "equity/state/policy_calendar.json"
        clean_pc = {
            "schema_version": "1.0",
            "edition_id": "2026-11-29_1800",
            "as_of_cst": "2026-11-29T18:00:00+08:00",
            "horizon_days": 30,
            "policy_briefs": [
                {
                    "id": "brief_clean_1",
                    "date_cst": "2026-11-29",
                    "region": "CN",
                    "category": "macro_data",
                    "impact_tier": "P1",
                    "authority": "国家统计局",
                    "headline": "工业利润回升支撑风偏",
                    "summary": "规上工业企业利润同比走强，黄金维持红灯停新仓 0%。",
                    "affected_markets": ["a_share", "gold"],
                    "market_impact": "红灯防守期严守股票仓位上限。",
                    "source_url": "https://www.stats.gov.cn/",
                }
            ],
            "events": [
                {
                    "event_id": "fomc_dec_test",
                    "date_cst": "2026-12-10",
                    "end_date_cst": "2026-12-10",
                    "date_precision": "exact",
                    "time_cst": "03:00",
                    "region": "US",
                    "category": "central_bank",
                    "impact_tier": "P0",
                    "title": "美联储 12 月议息决议（FOMC）",
                    "affected_markets": ["us_stock", "rates_bonds_core", "gold"],
                    "expected_consensus": "市场高度关注点阵图与利率路径。",
                    "market_transmission": "经美债曲线传导至权益与贵金属。",
                    "watch_triggers": {
                        "upside_bull": "利率回落缓和估值压制。",
                        "downside_bear": "鹰派措辞推升美债砸盘风险资产。",
                    },
                    "pre_event_stance": "黄金维持红灯停新仓 0%，静待决议落地。",
                    "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                    "monitor_window_min": 120,
                },
                {
                    "event_id": "boj_dec_test",
                    "date_cst": "2026-12-18",
                    "end_date_cst": "2026-12-18",
                    "date_precision": "exact",
                    "time_cst": "11:00",
                    "region": "JP",
                    "category": "central_bank",
                    "impact_tier": "P0",
                    "title": "日本央行 12 月议息会议",
                    "affected_markets": ["non_us_global_satellite", "us_stock"],
                    "expected_consensus": "紧盯加息节奏与日元汇率波动。",
                    "market_transmission": "套息波动影响全球科技与日股。",
                    "watch_triggers": {
                        "upside_bull": "汇率有序企稳消除套息踩踏。",
                        "downside_bear": "日元急升触发全球杠杆回撤。",
                    },
                    "pre_event_stance": "控制仓位上限、防汇率剧震。",
                    "source_url": "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm",
                    "monitor_window_min": 120,
                },
            ],
        }
        pc_path.write_text(json.dumps(clean_pc, ensure_ascii=False), encoding="utf-8")
        res_ok = self.lint("--precheck", "--strict")
        self.assertEqual(res_ok.returncode, 0, res_ok.stdout + res_ok.stderr)

        # (a) Gate C2 catches Gold active buy verb inside policy_calendar.json events & briefs
        pc_gold_ev = deepcopy(clean_pc)
        pc_gold_ev["events"][0]["pre_event_stance"] = "建议会前立即买入黄金 518880 对冲波动。"
        pc_path.write_text(json.dumps(pc_gold_ev, ensure_ascii=False), encoding="utf-8")
        res_gold_ev = self.lint("--precheck", "--strict")
        self.assertEqual(res_gold_ev.returncode, 1, res_gold_ev.stdout)
        self.assertIn("Gate C2", res_gold_ev.stdout)

        pc_gold_br = deepcopy(clean_pc)
        pc_gold_br["policy_briefs"][0]["market_impact"] = "可逢低布局黄金 ETF 518660 或上车 518880 防御。"
        pc_path.write_text(json.dumps(pc_gold_br, ensure_ascii=False), encoding="utf-8")
        res_gold_br = self.lint("--precheck", "--strict")
        self.assertEqual(res_gold_br.returncode, 1, res_gold_br.stdout)
        self.assertIn("Gate C2", res_gold_br.stdout)

        # (b) Bad enum (incl. affected_markets) & edition_id drift caught by Gate 4
        pc_bad_enum = deepcopy(clean_pc)
        pc_bad_enum["events"][0]["region"] = "INVALID_REG"
        pc_bad_enum["events"][0]["category"] = "invalid_cat"
        pc_bad_enum["events"][0]["impact_tier"] = "P9"
        pc_bad_enum["events"][0]["date_precision"] = "fuzzy"
        pc_bad_enum["events"][0]["affected_markets"] = ["us_stock", "invalid_mkt"]
        pc_path.write_text(json.dumps(pc_bad_enum, ensure_ascii=False), encoding="utf-8")
        res_enum = self.lint("--precheck", "--strict")
        self.assertEqual(res_enum.returncode, 1, res_enum.stdout)
        for token in (
            ".region 非法枚举",
            ".category 非法枚举",
            ".impact_tier 非法枚举",
            ".date_precision 非法枚举",
            ".affected_markets 非法枚举",
        ):
            self.assertIn(token, res_enum.stdout)

        # (b2) PBOC Doc No. 42 crypto active-buy, local path, and unguarded restricted code caught by Gate 4
        pc_hygiene = deepcopy(clean_pc)
        pc_hygiene["events"][0]["pre_event_stance"] = "建议趁波动买入 BTC 避险，路径 /Users/demo/notes.txt，关注 968118 表现。"
        pc_path.write_text(json.dumps(pc_hygiene, ensure_ascii=False), encoding="utf-8")
        res_hyg = self.lint("--precheck", "--strict")
        self.assertEqual(res_hyg.returncode, 1, res_hyg.stdout)
        self.assertIn("银发〔2026〕42号", res_hyg.stdout)
        self.assertIn("泄露本机文件系统路径", res_hyg.stdout)
        self.assertIn("968118", res_hyg.stdout)

        # Negated PBOC crypto warning & negated Gold buy verbs pass cleanly
        pc_neg_ok = deepcopy(clean_pc)
        pc_neg_ok["events"][0]["pre_event_stance"] = "遵照银发〔2026〕42号严禁配置比特币与买入 BTC；黄金红灯停期暂不布局黄金、不要上车 518880。"
        pc_path.write_text(json.dumps(pc_neg_ok, ensure_ascii=False), encoding="utf-8")
        res_neg = self.lint("--precheck", "--strict")
        self.assertEqual(res_neg.returncode, 0, res_neg.stdout + res_neg.stderr)

        pc_bad_ed = deepcopy(clean_pc)
        pc_bad_ed["edition_id"] = "2026-11-28_0730"
        pc_path.write_text(json.dumps(pc_bad_ed, ensure_ascii=False), encoding="utf-8")
        res_ed = self.lint("--precheck", "--strict")
        self.assertEqual(res_ed.returncode, 1, res_ed.stdout)
        self.assertIn("policy_calendar.json edition_id", res_ed.stdout)

        # (c) Internal filename leak inside policy_calendar.json & report prose both caught
        pc_leak = deepcopy(clean_pc)
        pc_leak["events"][0]["pre_event_stance"] = "参考 realtime_monitor.py 与 wechat_notify.py 推送。"
        pc_path.write_text(json.dumps(pc_leak, ensure_ascii=False), encoding="utf-8")
        res_leak = self.lint("--precheck", "--strict")
        self.assertEqual(res_leak.returncode, 1, res_leak.stdout)
        self.assertIn("realtime_monitor.py", res_leak.stdout)
        self.assertIn("wechat_notify.py", res_leak.stdout)

        pc_path.write_text(json.dumps(clean_pc, ensure_ascii=False), encoding="utf-8")
        self.advance("2026-11-26_1800")
        pc_26 = deepcopy(clean_pc)
        pc_26["edition_id"] = "2026-11-26_1800"
        pc_26["as_of_cst"] = "2026-11-26T18:00:00+08:00"
        pc_path.write_text(json.dumps(pc_26, ensure_ascii=False), encoding="utf-8")
        for db in ("multi_asset_channels.json", "etf_universe.json", "deep_dossiers.json"):
            p_db = self.root / "equity/state" / db
            if p_db.is_file():
                obj = json.loads(p_db.read_text(encoding="utf-8"))
                obj["edition_id"] = "2026-11-26_1800"
                p_db.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        a_daily = self.issue("a_share", "main")
        self.issue("hk_stock", "main")
        self.issue("us_stock", "holiday_watch")
        a_daily.write_text(
            a_daily.read_text(encoding="utf-8").replace("覆盖期铜。", "覆盖期铜，详情见 policy_calendar.json 与 realtime_monitor.py。"),
            encoding="utf-8",
        )
        res_prose = self.lint("--precheck", "--strict")
        self.assertEqual(res_prose.returncode, 1, res_prose.stdout)
        self.assertIn("policy_calendar.json", res_prose.stdout)
        self.assertIn("realtime_monitor.py", res_prose.stdout)

    def test_policy_brief_evidence_links_require_specific_unique_pages(self):
        import equity.lint_equity as le

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy_calendar.json"
            brief = {
                "id": "rate", "date_cst": "2026-11-29", "region": "US",
                "category": "central_bank", "impact_tier": "P1", "authority": "美联储",
                "headline": "联储议息排程", "summary": "时间以联储日历为准。",
                "affected_markets": ["us_stock"], "market_impact": "关注美元利率变化。",
                "source_url": "https://www.federalreserve.gov/newsevents/2026-december.htm",
                "source_urls": ["https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"],
            }
            calendar = {
                "edition_id": "2026-11-29_1800", "as_of_cst": "2026-11-29T18:00:00+08:00",
                "schema_version": "1.0", "horizon_days": 30, "policy_briefs": [brief], "events": [],
            }

            def link_errors():
                path.write_text(json.dumps(calendar, ensure_ascii=False), encoding="utf-8")
                with mock.patch.object(le, "POLICY_CALENDAR_PATH", path):
                    return [
                        error for error in le._check_policy_calendar(
                            calendar["edition_id"], calendar["edition_id"][:10], require_horizon=False,
                            enforce_g5_g7=False, enforce_live_contract=True, market_as_of_cst=calendar["as_of_cst"],
                        ) if ".source_url" in error
                    ]

            self.assertEqual(link_errors(), [])
            brief["source_urls"] = [brief["source_url"]]
            self.assertTrue(any("重复证据" in error for error in link_errors()))
            for bad in ([], "https://www.federalreserve.gov/news", ["https://www.federalreserve.gov/"],
                        ["https://www.federalreserve.gov:99999/news"], ["https://www.federalreserve.gov\\@example.org/news"],
                        ["https://example.org/press-release"]):
                with self.subTest(bad=bad):
                    brief["source_urls"] = bad
                    self.assertTrue(any(".source_urls" in error for error in link_errors()))

            del brief["source_urls"]
            brief["source_url"] = "https://www.federalreserve.gov/"
            self.assertTrue(any("须指向具体证据页面" in error for error in link_errors()))
            calendar["edition_id"] = "2026-11-28_1130"
            self.assertEqual(link_errors(), [])

    def test_numeric_ranges_currency_pe_skip_uk_region_bare_p0_and_bare_9m(self):
        import equity.lint_equity as le

        # 1. Currency-prefixed upper bound matched & valuation multiples skipped
        self.assertEqual(le._extract_numeric_ranges("安全买点 $540–$555 与 ¥10–¥20"), [(540.0, 555.0), (10.0, 20.0)])
        self.assertEqual(le._extract_numeric_ranges("前瞻 PE 14.3–15.0x，历史均值 12–15倍"), [])
        self.assertIn("UK", le.POLICY_CAL_REGIONS)

        # 2. Bare P0 in policy_calendar.json prose blocked, while UK region with clean prose passes
        self.advance("2026-11-26_1800")
        pc_path = self.root / "equity/state/policy_calendar.json"
        clean_uk = {
            "schema_version": "1.0",
            "edition_id": "2026-11-26_1800",
            "as_of_cst": "2026-11-26T18:00:00+08:00",
            "horizon_days": 14,
            "policy_briefs": [
                {
                    "id": "uk_boe_brief",
                    "date_cst": "2026-11-26",
                    "region": "UK",
                    "category": "central_bank",
                    "impact_tier": "P0",
                    "authority": "Bank of England",
                    "affected_markets": ["non_us_global_satellite", "rates_bonds_core"],
                    "headline": "英国央行维持利率不变",
                    "summary": "英国央行最新声明偏审慎。",
                    "market_impact": "影响英债与欧股风险偏好。",
                    "source_url": "https://www.bankofengland.co.uk/",
                }
            ],
            "events": [
                {
                    "event_id": "uk_boe_20261217",
                    "date_cst": "2026-12-17",
                    "end_date_cst": "2026-12-17",
                    "date_precision": "exact",
                    "time_cst": "20:00",
                    "region": "UK",
                    "category": "central_bank",
                    "impact_tier": "P0",
                    "title": "英国央行 12 月利率决议",
                    "affected_markets": ["non_us_global_satellite", "rates_bonds_core"],
                    "expected_consensus": "市场预期按兵不动。",
                    "market_transmission": "英债与欧元区利率联动。",
                    "watch_triggers": {"upside_bull": "释放降息路径", "downside_bear": "再通胀抬头"},
                    "pre_event_stance": "维持全球防守配比。",
                    "source_url": "https://www.bankofengland.co.uk/",
                    "monitor_window_min": 60,
                }
            ],
        }
        for db in ("multi_asset_channels.json", "etf_universe.json", "deep_dossiers.json"):
            p_db = self.root / "equity/state" / db
            if p_db.is_file():
                obj = json.loads(p_db.read_text(encoding="utf-8"))
                obj["edition_id"] = "2026-11-26_1800"
                p_db.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        a_daily = self.issue("a_share", "main")
        self.issue("hk_stock", "main")
        self.issue("us_stock", "holiday_watch")

        pc_path.write_text(json.dumps(clean_uk, ensure_ascii=False), encoding="utf-8")
        res_ok = self.lint("--precheck", "--strict")
        self.assertEqual(res_ok.returncode, 0, res_ok.stdout + res_ok.stderr)

        bad_p0 = deepcopy(clean_uk)
        bad_p0["events"][0]["title"] = "英国央行 P0 重磅决议"
        pc_path.write_text(json.dumps(bad_p0, ensure_ascii=False), encoding="utf-8")
        res_p0 = self.lint("--precheck", "--strict")
        self.assertEqual(res_p0.returncode, 1, res_p0.stdout)
        self.assertIn("P0", res_p0.stdout)

        # 3. Bare 9M warning caught in post-cutover editorial check while 9MB / $9M / 前三季度 stay clean
        _, warns_9m = le._check_phase_d_editorial(
            "## 正文\n\n**公司要点**：公司 9M 归母净利大增。\n",
            "2026-11-27_1800_a_share.md",
            {"edition_type": "main"},
        )
        self.assertTrue(any("9M" in w for w in warns_9m), warns_9m)
        _, warns_clean = le._check_phase_d_editorial(
            "## 正文\n\n**公司要点**：附件 9MB、融资 $9M、前三季度业绩稳健。\n",
            "2026-11-27_1800_a_share.md",
            {"edition_type": "main"},
        )
        self.assertFalse(any("裸期限缩写" in w for w in warns_clean), warns_clean)


if __name__ == "__main__":
    unittest.main()
