"""Regression checks for new gold editions. No browser or publication is used."""

from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.build_site import load_renderers


ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "gold"
sys.path.insert(0, str(GOLD))
import edition_validation as rules
import lint_readability as lint

build_daily = load_renderers().gold_daily


ARCHIVED_REPORT = GOLD / "daily" / "2026-11-25_1800_晚报_黄金深度研报_r2.md"
EDITION = "2026-11-26_1800"
AS_OF = "2026-11-26 18:00"


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture():
    snap = dict(
        edition_id=EDITION,
        as_of_short=AS_OF,
        as_of_bjt="2026年11月26日（周四）18:00",
        tier_code="Tier 0",
        new_buy_allowed=False,
        tier1_passed=1,
        tier1_total=4,
        daily_alert_level="L1",
        a_class_tranche_split="30% + 45% + 25%",
        cfets_fixing_date="2026-11-26",
        cfets_cny_fixing=6.71,
        us10y_pct=4.84,
        us2y_pct=4.604,
        effr_pct=3.88,
        spread_2y_ff_bp=72,
        dfii10_fred_official_pct=2.79,
        dfii10_live_pct=2.79,
        dxy=104,
        on_rrp_usd_m=301,
        comex_copper_usd_lb=5.36,
        spot_gold_ny_close_usd=3554.77,
        spot_gold_ny_close_rounded=3555,
        spot_gold_prev_close_usd=3635.24,
        spot_gold_ny_change_pct=-2.21,
        spot_gold_ny_close_date="2026-11-25",
        tier1_gate4_threshold_date="2026-11-24",
        tier1_gate4_target_date="2026-11-25",
        tier1_gate4_threshold_usd=3678.15,
        wti_settle_usd=80,
        brent_settle_usd=90,
        spot_silver_usd=41,
        spx_close=7200,
        spot_platinum_usd=1258,
        rmb_channels={
            "brand_store_rmb": 1068,
            "bank_bar_plus_craft_rmb": 796,
            "wedding_save_per_g_rmb": 272,
            "wedding_save_50g_rmb": 13600,
            "wedding_save_pct": 25.47,
        },
        institutional_targets=[
            {"name": "示例甲", "kind": "pt", "lo": 4300, "base": 4500, "hi": 4700},
            {"name": "示例乙", "kind": "avg", "lo": 4400, "base": 4600, "hi": 4800},
        ],
        bank_2027_yearend_sample_count=1,
        bank_2027_yearend_median_usd=4500,
        bank_2027_avg_sample_count=1,
        bank_2027_avg_median_usd=4600,
        vix_live=None,
        vix_live_as_of=None,
        vix_close=31.50,
        vix_10d_window_end="2026-11-25",
        vix_10d_peak_close=35.89,
        vix_10d_peak_date="2026-11-20",
        vix_daily_source=rules.VIX_DAILY_SOURCE,
    )
    snap["cross_ratios"] = {
        name: snap["spot_gold_ny_close_usd"] / snap[denominator]
        for name, (denominator, _) in lint.RATIO_FIELDS.items()
    }
    snap["tier1_gates"] = [
        {"id": gate_id, "passed": passed, "name": "条件", "reading": "读数", "threshold": "门槛", "detail": "证据"}
        for gate_id, passed in zip(rules.ENTRY_GATE_IDS, (False, False, True, False))
    ]
    # Controlled values. Cboe is not queried by tests.
    snap["vix_10d_session_closes"] = [
        {"date": f"2026-11-{day:02}", "close": close}
        for day, close in zip((12, 13, 16, 17, 18, 19, 20, 23, 24, 25),
                              (18.70, 19.30, 22.91, 25.46, 24.56, 28.44, 35.89, 26.62, 26.36, 31.50))
    ]
    return snap


def _modify_directive(raw, name, update):
    pattern = rf"(<!--\s*{name}\s+)(\{{.*?\}})(\s*-->)"

    def rewrite(match):
        config = json.loads(match[2])
        update(config)
        return match[1] + json.dumps(config, ensure_ascii=False) + match[3]

    return re.sub(pattern, rewrite, raw, count=1, flags=re.DOTALL)


def _calendar_fixture():
    early_close = {"windows_et": [["03:15", "09:25"], ["09:31", "13:00"]], "official_close_et": None,
                   "daily_row_check_after_et": "13:15"}
    full_holiday = {"windows_et": [], "official_close_et": None, "daily_row_check_after_et": "11:30"}
    return {
        "timezone": "Asia/Shanghai",
        "coverage": {
            "start_date": "2026-11-01", "end_date": "2027-01-31", "verified_on": "2026-11-26",
            "vix_schedule_source": "https://www.cboe.com/about/hours/us-options/",
        },
        "calendar_overrides": [{
            "id": "thanksgiving_2026", "date": "2026-11-26", "end_date": "2026-11-27",
            "markets": ["US_EQUITY"], "overlay_mode": "A",
        }],
        "vix_session_exceptions": {"2026-11-26": full_holiday, "2026-11-27": early_close},
    }


def _daily_check(status, checked_at):
    return {"status": status, "checked_at": checked_at, "source": rules.VIX_DAILY_SOURCE,
            "note": "合成样本中的每日收盘证据记录。"}


class GoldWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        self.snapshot_path = self.path / "data_snapshot.json"
        self.calendar_path = self.path / "market_calendar.json"
        self.calendar = _calendar_fixture()
        self.calendar_path.write_text(json.dumps(self.calendar))
        self.audit = self.path / "AUDIT_LOG.md"
        self.changes = self.path / "CHANGELOG.md"
        self.scorecard = self.path / "SCORECARD.md"
        paths = patch.multiple(lint, DAILY_SNAPSHOT_PATH=self.snapshot_path, MARKET_CALENDAR_PATH=self.calendar_path,
                               AUDIT_LOG_PATH=self.audit, CHANGELOG_PATH=self.changes, SCORECARD_PATH=self.scorecard)
        paths.start()
        self.addCleanup(paths.stop)

    def _validate(self, snapshot, *, validated_on=date(2026, 11, 27)):
        self.snapshot_path.write_text(json.dumps(snapshot))
        errors, warnings = [], []
        lint.validate_snapshot_file(self.snapshot_path, errors, warnings, validated_on=validated_on)
        self.assertEqual(warnings, [])
        return errors

    def test_early_close_and_holiday_have_distinct_sessions(self):
        cutoff = datetime(2026, 11, 28, 7, 30)
        errors = []
        first, exceptions = rules.vix_calendar(self.calendar, cutoff, errors)
        self.assertEqual(errors, [])
        checks = {
            "2026-11-26": _daily_check("published", "2026-11-27 07:20"),
            "2026-11-27": _daily_check("published", "2026-11-28 06:20"),
        }
        dates = rules._vix_completed_days(
            cutoff.replace(tzinfo=rules.BEIJING).astimezone(rules.NEW_YORK), first, exceptions, checks, errors,
        )
        self.assertEqual(errors, [])
        self.assertEqual(dates[-3:], ["2026-11-25", "2026-11-26", "2026-11-27"])

    def test_holiday_row_not_assumed_and_pending_requires_current_official_check(self):
        snap = _fixture()
        snap.update(edition_id="2026-11-27_0730", as_of_short="2026-11-27 07:30", as_of_bjt="2026-11-27 07:30")
        self.assertTrue(any("节日日线待核" in e for e in self._validate(snap)))
        snap["vix_daily_row_checks"] = {"2026-11-26": _daily_check("pending", "2026-11-27 07:25")}
        self.assertEqual(self._validate(snap), [])
        snap["vix_daily_row_checks"]["2026-11-26"]["checked_at"] = "2026-11-27 06:29"
        self.assertTrue(any("待披露需重查" in e for e in self._validate(snap)))
        snap["vix_daily_row_checks"]["2026-11-26"] = _daily_check("published", "2026-11-27 07:25")
        self.assertTrue(any("完整交易日不符" in e for e in self._validate(snap)))
        snap["vix_10d_session_closes"] = snap["vix_10d_session_closes"][1:] + [{"date": "2026-11-26", "close": 31.50}]
        snap["vix_10d_window_end"] = "2026-11-26"
        self.assertEqual(self._validate(snap), [])

    def test_cboe_holiday_can_use_official_close_without_live(self):
        snap = _fixture()
        self.assertEqual(self._validate(snap), [])
        snap.pop("vix_live")
        snap.pop("vix_live_as_of")
        self.assertEqual(self._validate(snap), [])

    def test_stale_live_quotes_and_fake_holiday_daily_close_are_rejected(self):
        snap = _fixture()
        snap.update(vix_live=26.36, vix_live_as_of="2026-11-25 21:20")
        self.assertTrue(any("VIX 盘口过时" in e for e in self._validate(snap)))
        snap.update(vix_live=26.36, vix_live_as_of=None)
        self.assertTrue(any("VIX 盘口不完整" in e for e in self._validate(snap)))
        snap = _fixture()
        snap["vix_10d_session_closes"][-1]["date"] = snap["vix_10d_window_end"] = "2026-11-26"
        self.assertTrue(any("VIX 完整交易日不符" in e for e in self._validate(snap)))

    def test_live_quote_must_be_in_the_same_continuous_cboe_window(self):
        snap = _fixture()
        snap.update(edition_id="2026-11-27_1800", as_of_short="2026-11-27 22:00",
                    as_of_bjt="2026-11-27 22:00", vix_live=30.00, vix_live_as_of="2026-11-27 21:45")
        snap["vix_daily_row_checks"] = {"2026-11-26": _daily_check("pending", "2026-11-27 21:45")}
        self.assertEqual(self._validate(snap), [])
        # 09:31 EST is the RTH reopening, even though the old reading is only six minutes old.
        cutoff = datetime(2026, 11, 27, 22, 31)
        errors = []
        schedule = rules.vix_calendar(self.calendar, cutoff, errors)
        self.assertFalse(rules.check_vix_period(snap, cutoff, datetime(2026, 11, 27, 22, 25), schedule, errors))
        self.assertTrue(any("VIX 盘口过时" in e for e in errors))

    def test_wrong_edition_time_expired_calendar_and_manually_opened_gate_fail(self):
        snap = _fixture()
        snap["edition_id"] = "2026-11-28_0730"
        self.assertTrue(any("班次截点错" in e for e in self._validate(snap)))
        snap = _fixture()
        for gate in snap["tier1_gates"]:
            gate["passed"] = True
        snap.update(new_buy_allowed=True, tier_code="Tier 1", tier1_passed=4)
        errors = self._validate(snap)
        for gate in (1, 2, 4):
            self.assertTrue(any(f"第 {gate} 关复算冲突" in error for error in errors), errors)
        self.calendar["coverage"]["end_date"] = "2026-12-01"
        self.calendar_path.write_text(json.dumps(self.calendar))
        self.assertTrue(any("日历覆盖不足" in e for e in self._validate(_fixture())))

    def test_stale_calendar_is_rejected_even_with_legacy_report(self):
        snap = _fixture()
        snap.update(edition_id="2026-11-25_1800_r2", as_of_short="2026-11-25 21:25")
        self.calendar_path.write_text('{"calendar_overrides": [{"date": "2001-01-01"}]}')
        self.assertTrue(any("日历时区错" in e for e in self._validate(snap)))

    def test_replay_uses_calendar_verification_date_without_moving_market_cutoff(self):
        snap = _fixture()
        snap.update(
            edition_id="2026-11-25_1800_r3", as_of_short="2026-11-25 21:25", as_of_bjt="2026-11-25 21:25",
            spot_gold_ny_close_date="2026-11-24", tier1_gate4_target_date="2026-11-25", cfets_fixing_date="2026-11-25",
            vix_close=26.36, vix_10d_window_end="2026-11-24", vix_live=30.99, vix_live_as_of="2026-11-25 21:20",
        )
        snap["vix_10d_session_closes"] = [{"date": "2026-11-11", "close": 17.49}] + snap["vix_10d_session_closes"][:-1]
        self.assertEqual(self._validate(snap, validated_on=date(2026, 11, 26)), [])
        errors = self._validate(snap, validated_on=date(2026, 11, 25))
        self.assertTrue(any("日历核证日期过晚" in error for error in errors))
        snap["vix_live_as_of"] = "2026-11-25 21:30"
        self.assertTrue(any("VIX 盘口过时" in error for error in self._validate(snap)))
        snap["vix_live_as_of"] = "2026-11-25 21:20"
        snap["vix_10d_session_closes"][-1]["date"] = snap["vix_10d_window_end"] = "2026-11-25"
        self.assertTrue(any("VIX 完整交易日不符" in error for error in self._validate(snap)))
        self.calendar["coverage"]["verified_on"] = "2026-11-27"
        self.calendar_path.write_text(json.dumps(self.calendar))
        self.assertTrue(any("日历核证日期过晚" in error for error in self._validate(_fixture())))

    def test_spread_uses_exact_difference_and_gate_four_requires_confirmed_close(self):
        snap = _fixture()
        snap.update(dfii10_fred_official_pct=2.72, us2y_pct=4.43, effr_pct=3.88, spread_2y_ff_bp=55,
                    tier1_gate4_threshold_usd=3500, tier1_gate4_threshold_date="2026-11-25",
                    tier1_gate4_target_date="2026-11-27", tier1_passed=3)
        snap["tier1_gates"][0]["passed"] = True
        snap["tier1_gates"][1]["passed"] = True
        self.assertEqual(self._validate(snap), [])
        snap["us2y_pct"] = 4.431
        self.assertTrue(any("第 2 关复算冲突" in e for e in self._validate(snap)))
        snap["tier1_gates"][3]["passed"] = True
        snap["tier1_passed"] = 4
        self.assertTrue(any("第 4 关复算冲突" in e for e in self._validate(snap)))

    def test_shared_chart_inputs_match_the_renderer(self):
        raw = ARCHIVED_REPORT.read_text()
        timeline = lambda cfg: cfg["points"][0].update(val="3,555")
        updated = _modify_directive(raw, "DAILY_CHART_TIMELINE", timeline)
        old = build_daily.md_to_html(raw)[2]
        self.assertEqual(build_daily.md_to_html(updated)[2], old)
        errors, warnings = [], []
        lint._validate_directive_schema("DAILY_CHART_TIMELINE", {"points": [{"val": "3,55"}]}, errors, warnings)
        self.assertTrue(errors)
        with self.assertRaisesRegex(ValueError, "须为有限数值"):
            build_daily.render_chart_timeline({"points": [{"val": "3,55"}]})

    def test_new_report_requires_ledger_and_legacy_reports_keep_reading(self):
        snap = _fixture()
        master = _read_json(GOLD / "master_snapshot.json")
        legacy = _read_json(GOLD / "data_snapshot.json")
        self.assertEqual(lint.check_file(ARCHIVED_REPORT, legacy, master, precheck=True), ([], []))

        raw = _modify_directive(
            ARCHIVED_REPORT.read_text(), "DAILY_META",
            lambda meta: meta.update(edition_id=EDITION, as_of_short=AS_OF, timestamp=AS_OF),
        )

        def chart_ids(chart):
            for check, gate_id in zip(chart["checks"], rules.ENTRY_GATE_IDS):
                check["id"] = gate_id

        raw = _modify_directive(raw, "DAILY_CHART_SWITCH", chart_ids)
        report = self.path / f"{EDITION}_晚报_黄金深度研报.md"
        report.write_text(raw)
        errors, _ = lint.check_file(report, snap, master, precheck=True)
        self.assertTrue(any("核验台账缺失" in e for e in errors))
        self.assertEqual(sum("刊期台账缺失" in e for e in errors), 2)
        self.changes.write_text(f"<!-- GOLD_EDITION_CHANGELOG {EDITION} -->")
        self.scorecard.write_text(f"<!-- GOLD_EDITION_SCORECARD {EDITION} -->")
        review = {
            "edition_id": EDITION,
            "as_of_short": AS_OF,
            "note": "四关已核验。",
            "sources": {gate_id: ["https://example.com/fixture"] for gate_id in rules.ENTRY_GATE_IDS},
            "forecast_review": {"status": "none_due", "note": "本期无到期预测。", "sources": []},
        }
        self.audit.write_text("<!-- GOLD_EDITION_REVIEW " + json.dumps(review) + " -->")
        self.assertEqual(lint.check_file(report, snap, master, precheck=True), ([], []))

        wallet_claim = "**假设右侧信号转黄（通过 3/4 关）**：届时仅允许动用首批 30% 预算（即 3 万元），分拆为 2–3 笔挂单。"
        body_with_claim = f"{raw}\n\n{wallet_claim}\n"
        card_with_claim = _modify_directive(
            raw, "DAILY_PERSONA",
            lambda persona: persona["cards"][0]["actions"].append("<strong>通过３／４关即可开新仓</strong>。"),
        )
        for source, manuscript in (
            ("正文", body_with_claim),
            ("正文", f"{raw}\n\n通过 3/4 关即转黄。\n"),
            ("DAILY_PERSONA", card_with_claim),
        ):
            with self.subTest(source=source):
                report.write_text(manuscript)
                errors, warnings = lint.check_file(report, snap, master, precheck=True)
                self.assertEqual(warnings, [])
                self.assertEqual(len(errors), 1)
                self.assertIn(f"[Gate 5 四关开仓阈值冲突] {source}", errors[0])

        allowed = (
            "通过 3/4 关仍不得转黄或开仓，四关全部通过才可启用首批 30%。",
            "只通过 1/4 关，维持红灯，继续等待。",
            "“满足三关就能试买”的说法是错误的，必须等四关齐备。",
            "不是转黄（通过 3/4 关）就可买入，须满足全部四关。",
        )
        report.write_text(raw + "\n\n" + "\n\n".join(allowed))
        self.assertEqual(lint.check_file(report, snap, master, precheck=True), ([], []))

        report.write_text(body_with_claim)
        later_snap = dict(snap, edition_id="2026-11-27_0730")
        errors, warnings = lint.check_file(report, later_snap, master, precheck=True)
        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("四关开仓阈值冲突", errors[0])

        legacy_report = self.path / ARCHIVED_REPORT.name
        legacy_report.write_text(f"{ARCHIVED_REPORT.read_text()}\n\n{wallet_claim}\n")
        self.assertEqual(lint.check_file(legacy_report, legacy, master, precheck=True), ([], []))

        report.write_text(raw)
        bad = deepcopy(review)
        bad["forecast_review"]["status"] = "settled"
        self.audit.write_text("<!-- GOLD_EDITION_REVIEW " + json.dumps(bad) + " -->")
        errors, _ = lint.check_file(report, snap, master, precheck=True)
        self.assertTrue(any("预判验真缺项" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
