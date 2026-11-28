"""Regression checks for new gold editions. No browser or publication is used."""

from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path
import re
import subprocess
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


def _resolve_archived_report(name: str = "2026-11-25_1800_晚报_黄金深度研报_r2.md") -> Path:
    for candidate in (
        GOLD / "daily" / name,
        GOLD / "daily" / "archive" / "2026-11" / name,
    ):
        if candidate.is_file():
            return candidate
    archive_dir = GOLD / "daily" / "archive"
    if archive_dir.is_dir():
        matches = sorted(p for p in archive_dir.rglob(name) if p.is_file())
        if matches:
            return matches[0]
    raise FileNotFoundError(
        f"Archived legacy gold report not found in daily/ or daily/archive/**: {name}"
    )


ARCHIVED_REPORT = _resolve_archived_report()
EDITION = "2026-11-26_1800"
AS_OF = "2026-11-26 18:00"


def _legacy_snapshot():
    snap = _fixture()
    snap.update(
        edition_id="2026-11-25_1800_r2",
        as_of_short="2026-11-25 21:25",
        as_of_bjt="2026年11月25日（周三）21:25",
    )
    return snap


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
        effr_observation_date="2026-11-24",
        effr_published_at="2026-11-25 22:02",
        effr_source="https://fred.stlouisfed.org/series/EFFR",
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


def _sanitize_for_converged(raw):
    """Strip legacy internal-leak tokens, excess bold markers, and bare-number backticks outside comments."""
    raw = raw.replace("V7.2", "新版").replace("红队", "独立核验")
    parts = re.split(r"(<!--.*?-->)", raw, flags=re.DOTALL)
    for idx in range(0, len(parts), 2):
        seg = lint._BARE_NUM_BACKTICK_RE.sub(lambda m: m.group(0)[1:-1], parts[idx])
        seg = re.sub(r"\*\*([^*]+)\*\*", r"\1", seg)
        parts[idx] = seg
    return "".join(parts)


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
    def test_cli_help_does_not_require_a_manuscript(self):
        command = [sys.executable, str(GOLD / "lint_readability.py")]
        help_result = subprocess.run([*command, "--help"], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--strict", help_result.stdout)
        missing_arguments = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(missing_arguments.returncode, 2)

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
        self.rsi_playbook = self.path / "RSI_PLAYBOOK.md"
        self.rsi_metrics = self.path / "rsi_metrics.json"
        paths = patch.multiple(
            lint,
            DAILY_SNAPSHOT_PATH=self.snapshot_path,
            MARKET_CALENDAR_PATH=self.calendar_path,
            AUDIT_LOG_PATH=self.audit,
            CHANGELOG_PATH=self.changes,
            SCORECARD_PATH=self.scorecard,
            RSI_PLAYBOOK_PATH=self.rsi_playbook,
            RSI_METRICS_PATH=self.rsi_metrics,
        )
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
        snap["vix_daily_row_checks"]["2026-11-26"]["checked_at"] = "2026-11-27 04:00"
        self.assertEqual(self._validate(snap), [])
        snap["vix_daily_row_checks"]["2026-11-26"]["checked_at"] = "2026-11-27 03:29"
        self.assertTrue(any("待披露需重查" in e for e in self._validate(snap)))
        snap["vix_daily_row_checks"]["2026-11-26"] = _daily_check("published", "2026-11-27 07:25")
        self.assertTrue(any("完整交易日不符" in e for e in self._validate(snap)))
        snap["vix_10d_session_closes"] = snap["vix_10d_session_closes"][1:] + [{"date": "2026-11-26", "close": 31.50}]
        snap["vix_10d_window_end"] = "2026-11-26"
        self.assertEqual(self._validate(snap), [])

    def test_half_day_allows_provisional_close_and_self_proving_no_row_confirmed(self):
        snap = _fixture()
        snap.update(
            edition_id="2026-11-28_0730",
            as_of_short="2026-11-28 07:30",
            as_of_bjt="2026年11月28日（周六）07:30",
            cfets_fixing_date="2026-11-27",
            vix_close=29.80,
            vix_10d_window_end="2026-11-27",
        )
        snap["vix_10d_session_closes"] = snap["vix_10d_session_closes"][1:] + [
            {"date": "2026-11-27", "close": 29.80},
        ]
        snap["vix_daily_row_checks"] = {
            "2026-11-26": {
                "status": "no_row_confirmed",
                "checked_at": "2026-11-28 07:10",
                "source": rules.VIX_DAILY_SOURCE,
                "next_published_date": "2026-11-27",
                "note": "官方 CSV 后续交易日已跳至 11/27，自证感恩节 11/26 无日线。",
            },
            "2026-11-27": {
                "status": "provisional_close",
                "checked_at": "2026-11-28 07:10",
                "source": "https://www.cboe.com/tradable_products/vix/",
                "note": "黑五半日市 CSV 尚未批量更新，暂采 Cboe 官网 13:00 EST 读数。",
            },
        }
        # When 2026-11-27 is still provisional_close, it cannot serve as CSV self-proof for 2026-11-26.
        self.assertTrue(any("无日线证据缺失" in e for e in self._validate(snap, validated_on=date(2026, 11, 28))))

        # With explicit Cboe confirmation_source, provisional_close on 11/27 + no_row_confirmed on 11/26 passes.
        with_confirm = deepcopy(snap)
        with_confirm["vix_daily_row_checks"]["2026-11-26"]["confirmation_source"] = "https://www.cboe.com/about/hours/us-options/"
        self.assertEqual(self._validate(with_confirm, validated_on=date(2026, 11, 28)), [])

        # Once 2026-11-27 is published in official CSV, next_published_date alone self-proves 2026-11-26.
        with_csv_published = deepcopy(snap)
        with_csv_published["vix_daily_row_checks"]["2026-11-27"] = {
            "status": "published",
            "checked_at": "2026-11-28 07:10",
            "source": rules.VIX_DAILY_SOURCE,
            "note": "黑五半日市 CSV 终值已发布。",
        }
        self.assertEqual(self._validate(with_csv_published, validated_on=date(2026, 11, 28)), [])

        bad_next = deepcopy(with_csv_published)
        bad_next["vix_daily_row_checks"]["2026-11-26"]["next_published_date"] = "2026-11-26"
        self.assertTrue(any("无日线证据缺失" in e for e in self._validate(bad_next, validated_on=date(2026, 11, 28))))

    def test_stale_provisional_close_expires_after_three_days(self):
        snap = _fixture()
        snap["vix_daily_row_checks"] = {
            "2026-11-23": {
                "status": "provisional_close",
                "checked_at": "2026-11-26 17:50",
                "source": "https://www.cboe.com/tradable_products/vix/",
                "note": "三天内暂定收盘复核仍处于窗口内。",
            },
        }
        self.assertEqual(self._validate(snap), [])

        stale = _fixture()
        stale["vix_daily_row_checks"] = {
            "2026-11-20": {
                "status": "provisional_close",
                "checked_at": "2026-11-26 17:50",
                "source": "https://www.cboe.com/tradable_products/vix/",
                "note": "超过三天的普通日暂定收盘未核销。",
            },
        }
        self.assertTrue(any("暂定收盘超期" in e for e in self._validate(stale)))

    def test_ordinary_day_csv_lag_allows_provisional_or_pending_without_blocking(self):
        # 2026-11-26 07:30 BJT == 2026-11-25 18:30 EST (same ET day after 16:15 EST close, before Cboe CSV batch)
        snap = _fixture()
        snap.update(
            edition_id="2026-11-26_0730",
            as_of_short="2026-11-26 08:50",
            as_of_bjt="2026年11月26日（周四）08:50",
            vix_close=28.29,
        )
        snap["vix_10d_session_closes"][-1]["close"] = 28.29
        # 1. Provisional close from Cboe product page during morning CSV lag passes cleanly (even >1h after check)
        snap["vix_daily_row_checks"] = {
            "2026-11-25": {
                "status": "provisional_close",
                "checked_at": "2026-11-26 07:35",
                "source": "https://www.cboe.com/tradable_products/vix/",
                "note": "07:30 早报时 Cboe CSV 尚未更新 11/25 行，暂采 Cboe 官网 16:15 EST 收盘读数，18:00 晚报复核。",
            }
        }
        self.assertEqual(self._validate(snap), [])

        # 2. Pending fallback when even closing quote is unavailable shifts 10d window back to published CSV ending 11/24
        pending_snap = deepcopy(snap)
        pending_snap["vix_daily_row_checks"] = {"2026-11-25": _daily_check("pending", "2026-11-26 07:35")}
        pending_snap["vix_10d_session_closes"] = [
            {"date": "2026-11-11", "close": 17.49}, *pending_snap["vix_10d_session_closes"][:-1],
        ]
        pending_snap["vix_10d_window_end"] = "2026-11-24"
        pending_snap["vix_close"] = 26.36
        self.assertEqual(self._validate(pending_snap), [])

        # 3. Ordinary day cannot be marked no_row_confirmed or use a non-HTTPS provisional URL
        bad_status = deepcopy(snap)
        bad_status["vix_daily_row_checks"]["2026-11-25"]["status"] = "no_row_confirmed"
        self.assertTrue(any("VIX 日线证据错" in e for e in self._validate(bad_status)))
        bad_source = deepcopy(snap)
        bad_source["vix_daily_row_checks"]["2026-11-25"]["source"] = "http://www.cboe.com/tradable_products/vix/"
        self.assertTrue(any("VIX 日线证据错" in e for e in self._validate(bad_source)))

        # 4. Next ET day (18:00 evening): stale morning provisional/pending must be rechecked, fresh recheck still passes
        evening_snap = deepcopy(snap)
        evening_snap.update(
            edition_id="2026-11-26_1800",
            as_of_short="2026-11-26 18:10",
            as_of_bjt="2026年11月26日（周四）18:10",
        )
        self.assertTrue(any("待复核需重查" in e for e in self._validate(evening_snap)))
        evening_snap["vix_daily_row_checks"]["2026-11-25"]["checked_at"] = "2026-11-26 18:05"
        self.assertEqual(self._validate(evening_snap), [])

        # 5. Once reconciled in CSV at 18:00, removing the check or marking published passes
        evening_snap["vix_daily_row_checks"] = {"2026-11-25": _daily_check("published", "2026-11-26 18:05")}
        self.assertEqual(self._validate(evening_snap), [])
        evening_snap.pop("vix_daily_row_checks")
        self.assertEqual(self._validate(evening_snap), [])

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
        snap["tier1_gate4_threshold_date"] = "2026-11-24"
        self.assertTrue(any("第四关比较日期错" in e for e in self._validate(snap)))
        snap["tier1_gate4_threshold_date"] = "2026-11-25"
        snap["us2y_pct"] = 4.431
        self.assertTrue(any("第 2 关复算冲突" in e for e in self._validate(snap)))
        snap["tier1_gates"][3]["passed"] = True
        snap["tier1_passed"] = 4
        self.assertTrue(any("第 4 关复算冲突" in e for e in self._validate(snap)))

    def test_spread_requires_published_fed_evidence_from_provenance_cutover(self):
        snap = _fixture()
        snap.update(edition_id="2026-11-28_1130", as_of_short="2026-11-28 12:00",
                    effr_observation_date="2026-11-25", effr_published_at="2026-11-27 22:02")
        cases = {
            "effr_observation_date": "2026-11-27",
            "effr_published_at": "2026-11-30 22:00",
            "effr_source": "https://example.com/effr",
        }
        evidence_error = "第二关有效基金利率证据错"
        self.assertFalse(any(evidence_error in e for e in self._validate(snap, validated_on=date(2026, 11, 28))))
        for key, invalid in cases.items():
            with self.subTest(key=key):
                invalid_snap = {**snap, key: invalid}
                errors = self._validate(invalid_snap, validated_on=date(2026, 11, 28))
                self.assertTrue(any(evidence_error in e for e in errors), errors)

    def test_effr_rejects_an_old_release_holiday_observation_and_unrelated_fed_series(self):
        snap = {"effr_observation_date": "2026-11-25", "effr_published_at": "2026-11-27 22:02",
                "effr_source": "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/5.json"}
        cutoff = datetime(2026, 11, 28, 12)
        errors = []
        rules.check_effr_evidence(snap, cutoff, errors)
        self.assertEqual(errors, [])
        for fields in (
            {"effr_observation_date": "2026-11-24", "effr_published_at": "2026-11-25 22:02"},
            {"effr_observation_date": "2026-11-26"},
            {"effr_source": "https://fred.stlouisfed.org/series/SOFR"},
        ):
            with self.subTest(fields=fields):
                errors = []
                rules.check_effr_evidence({**snap, **fields}, cutoff, errors)
                self.assertEqual(len(errors), 1)
        errors = []
        rules.check_effr_evidence(snap, datetime(2026, 11, 30, 21), errors)
        self.assertEqual(errors, [])
        self.assertTrue(rules._is_ny_fed_business_day(date(2027, 6, 18)))
        self.assertFalse(rules._is_ny_fed_business_day(date(2027, 7, 5)))

    def test_disclosed_effr_delay_preserves_publication_and_keeps_gate_closed(self):
        snap = _fixture()
        snap.update(edition_id="2026-11-28_1130", us2y_pct=4.40, spread_2y_ff_bp=52,
                    data_caveats=[{"id": "effr_release_delayed", "market": "gold",
                                   "category": "delayed_official", "next_review": "2026-11-28_1800"}])
        cutoff = datetime(2026, 11, 28, 12)
        errors = []
        current = rules.check_effr_evidence(snap, cutoff, errors)
        self.assertFalse(current)
        self.assertEqual(errors, [])
        rules.recheck_entry_gates(snap, cutoff, None, errors, effr_current=current)
        self.assertEqual(errors, [])
        snap["tier1_gates"][1]["passed"] = True
        rules.recheck_entry_gates(snap, cutoff, None, errors, effr_current=current)
        self.assertTrue(any("第 2 关复算冲突" in error for error in errors))
        errors = []
        snap["data_caveats"][0]["next_review"] = "2026-11-28_0730"
        rules.check_effr_evidence(snap, cutoff, errors)
        self.assertTrue(any("须核对最新已公布利率或披露发布延迟" in error for error in errors))

    def test_effr_release_cannot_be_predeclared_or_silently_carried_after_ny_open(self):
        snap = {
            "edition_id": "2026-11-30_1800", "effr_observation_date": "2026-11-25",
            "effr_published_at": "2026-11-27 22:02", "effr_source": "https://www.newyorkfed.org/markets/reference-rates/effr",
        }
        for cutoff, current in ((datetime(2026, 11, 30, 21, 59), True), (datetime(2026, 11, 30, 22), False)):
            with self.subTest(cutoff=cutoff):
                errors = []
                self.assertIs(rules.check_effr_evidence(snap, cutoff, errors), current)
                self.assertEqual(bool(errors), not current)

        cutoff = datetime(2026, 11, 30, 22, 2)
        late = {**snap, "data_caveats": [{"id": "effr_release_delayed", "market": "gold",
                   "category": "delayed_official", "next_review": "2026-12-01_0730"}]}
        errors = []
        self.assertFalse(rules.check_effr_evidence(late, cutoff, errors))
        self.assertEqual(errors, [])
        for timestamp, valid in (("2026-11-30 20:00", False), ("2026-11-30 22:02", True)):
            with self.subTest(timestamp=timestamp):
                result = {**snap, "effr_observation_date": "2026-11-27", "effr_published_at": timestamp}
                errors = []
                self.assertIs(rules.check_effr_evidence(result, cutoff, errors), valid)
                self.assertEqual(bool(errors), not valid)

        summer = {**snap, "edition_id": "2027-06-21_1800", "effr_observation_date": "2027-06-18",
                  "effr_published_at": "2027-06-21 21:00"}
        errors = []
        self.assertTrue(rules.check_effr_evidence(summer, datetime(2027, 6, 21, 21), errors))
        self.assertEqual(errors, [])

    def test_morning_snapshot_may_not_take_same_day_cfets_fixing_before_0915(self):
        snap = _fixture()
        snap.update(edition_id="2026-11-30_0730", cfets_fixing_date="2026-11-30", data_caveats=[])
        for clock, denied in (("07:30", True), ("09:14", True), ("09:15", False)):
            with self.subTest(clock=clock):
                snap.update(as_of_short=f"2026-11-30 {clock}", as_of_bjt=f"2026-11-30 {clock}")
                errors = self._validate(snap, validated_on=date(2026, 11, 30))
                self.assertEqual(any("中间价尚未发布" in error for error in errors), denied, errors)

    def test_vix_daily_return_uses_the_same_official_close_series(self):
        snap = _fixture()
        snap.update(vix_change_pct=-11.16, vix_10d_session_closes=[
            *snap["vix_10d_session_closes"][:-2],
            {"date": "2026-11-26", "close": 26.80}, {"date": "2026-11-27", "close": 23.81},
        ], vix_10d_window_end="2026-11-27", vix_close=23.81)
        state = snap["vix_10d_session_closes"]
        peak = max(state, key=lambda row: row["close"])
        snap.update(vix_10d_peak_close=peak["close"], vix_10d_peak_date=peak["date"])
        errors = []
        self.assertTrue(lint._check_vix_snapshot(snap, None, errors))
        self.assertEqual(errors, [])
        snap["vix_change_pct"] = -15.836
        self.assertIsNone(lint._check_vix_snapshot(snap, None, errors))
        self.assertTrue(any("VIX 日涨跌幅错" in e for e in errors), errors)

    def test_snapshot_and_renderer_reject_ambiguous_or_nonfinite_json(self):
        for invalid in ('{"value": 1, "value": 2}', '{"value": NaN}', '{"value": 1e400}'):
            with self.subTest(invalid=invalid):
                self.snapshot_path.write_text(invalid)
                errors = []
                self.assertIsNone(lint.validate_snapshot_file(self.snapshot_path, errors, []))
                self.assertEqual(len(errors), 1)
                with self.assertRaisesRegex(ValueError, "Invalid JSON"):
                    build_daily.extract_directives(f"<!-- DAILY_META {invalid} -->")

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

    def test_numeric_table_column_keeps_its_class_at_the_width_limit(self):
        price = "**3,635**（顶 5,596 / 低 3,503）"
        table = [
            "| 年份 | 国际年末价（美元） |",
            "| :--- | :---: |",
            "| **2020** | 1,898 |",
            f"| **2026** | {price} |",
        ]

        self.assertEqual(build_daily._vis_len(price), 15.0)
        html = build_daily.render_md_table(table)
        self.assertIn('<th class="ta-c col-num">', html)
        self.assertIn('<td class="ta-c col-num">1,898</td>', html)

    def test_new_report_requires_ledger_and_legacy_reports_keep_reading(self):
        snap = _fixture()
        master = _read_json(GOLD / "master_snapshot.json")
        legacy = _legacy_snapshot()
        self.assertEqual(lint.check_file(ARCHIVED_REPORT, legacy, master), ([], []))

        raw = _sanitize_for_converged(_modify_directive(
            ARCHIVED_REPORT.read_text(), "DAILY_META",
            lambda meta: meta.update(edition_id=EDITION, as_of_short=AS_OF, timestamp=AS_OF),
        ))

        def chart_ids(chart):
            for check, gate_id in zip(chart["checks"], rules.ENTRY_GATE_IDS):
                check["id"] = gate_id

        raw = _modify_directive(raw, "DAILY_CHART_SWITCH", chart_ids)
        report = self.path / f"{EDITION}_晚报_黄金深度研报.md"
        report.write_text(raw)
        errors, _ = lint.check_file(report, snap, master)
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
        self.assertEqual(lint.check_file(report, snap, master), ([], []))

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
                errors, warnings = lint.check_file(report, snap, master)
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
        self.assertEqual(lint.check_file(report, snap, master), ([], []))

        report.write_text(body_with_claim)
        later_snap = dict(snap, edition_id="2026-11-27_0730")
        errors, warnings = lint.check_file(report, later_snap, master)
        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("四关开仓阈值冲突", errors[0])

        legacy_report = self.path / ARCHIVED_REPORT.name
        legacy_report.write_text(f"{ARCHIVED_REPORT.read_text()}\n\n{wallet_claim}\n")
        self.assertEqual(lint.check_file(legacy_report, legacy, master), ([], []))

        report.write_text(raw)
        bad = deepcopy(review)
        bad["forecast_review"]["status"] = "settled"
        self.audit.write_text("<!-- GOLD_EDITION_REVIEW " + json.dumps(bad) + " -->")
        errors, _ = lint.check_file(report, snap, master)
        self.assertTrue(any("预判验真缺项" in e for e in errors))

    def test_converged_edition_rules_and_part3_internal_leak_guard(self):
        snap = _fixture()
        master = _read_json(GOLD / "master_snapshot.json")
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

        raw = _sanitize_for_converged(_modify_directive(
            ARCHIVED_REPORT.read_text(), "DAILY_META",
            lambda meta: meta.update(
                edition_id=EDITION, as_of_short=AS_OF, timestamp=AS_OF, kpis=meta["kpis"][:4],
            ),
        ))

        def chart_ids(chart):
            for check, gate_id in zip(chart["checks"], rules.ENTRY_GATE_IDS):
                check["id"] = gate_id

        raw = _modify_directive(raw, "DAILY_CHART_SWITCH", chart_ids)
        raw = re.sub(r"<!--\s*DAILY_(?:TRUST_BAR|GLOSSARY)\s*\{.*?\}\s*-->", "", raw, flags=re.DOTALL)
        # Insert semi-pro terms allowed in converged Layer 0-1
        l01_heading = re.compile(r"^(#\s*第一部分[^\n]*)", re.MULTILINE)
        raw = l01_heading.sub(r"\1\n\n今夜重点跟踪 VIX、DXY、GLD 与美联储鹰派信号。\n", raw, count=1)

        report = self.path / f"{EDITION}_晚报_黄金深度研报.md"
        report.write_text(raw)
        self.assertEqual(lint.check_file(report, snap, master), ([], []))

        for leak_token in ("master_snapshot.json", "V7.2"):
            with self.subTest(part3_leak=leak_token):
                report.write_text(f"{raw}\n\n附录核对说明：引用 {leak_token} 基线。\n")
                errors, _ = lint.check_file(report, snap, master)
                self.assertTrue(any("内部工程词/文件名泄露" in e for e in errors), errors)

        for banned_l01 in ("stop-through", "小白词典", "蠢事"):
            with self.subTest(l01_banned=banned_l01):
                injected = l01_heading.sub(rf"\1\n\n本段含禁词 {banned_l01}。\n", raw, count=1)
                report.write_text(injected)
                errors, _ = lint.check_file(report, snap, master)
                self.assertTrue(any("术语/自嗨逃逸" in e for e in errors), errors)

    def test_holiday_half_day_provisional_close_expires_after_three_days(self):
        # 2026-11-27 is a registered holiday half-day (early_close) in _calendar_fixture().
        # Within 3 days (cutoff 2026-11-30 18:00 BJT == 2026-11-30 05:00 EST): provisional_close passes.
        within = _fixture()
        within.update(
            edition_id="2026-11-30_1800",
            as_of_short="2026-11-30 18:00",
            as_of_bjt="2026年11月30日（周一）18:00",
            effr_observation_date="2026-11-25",
            effr_published_at="2026-11-27 22:02",
            cfets_fixing_date="2026-11-30",
            spot_gold_ny_close_date="2026-11-27",
            tier1_gate4_threshold_date="2026-11-25",
            tier1_gate4_target_date="2026-11-27",
            vix_close=29.80,
            vix_10d_window_end="2026-11-27",
            data_caveats=[],
        )
        within["vix_10d_session_closes"] = within["vix_10d_session_closes"][1:] + [
            {"date": "2026-11-27", "close": 29.80},
        ]
        within["vix_daily_row_checks"] = {
            "2026-11-26": {
                "status": "no_row_confirmed",
                "checked_at": "2026-11-30 17:50",
                "source": rules.VIX_DAILY_SOURCE,
                "confirmation_source": "https://www.cboe.com/about/hours/us-options/",
                "next_published_date": "2026-11-27",
                "note": "Cboe 节假日日程确认感恩节 11/26 无常规现货收盘行。",
            },
            "2026-11-27": {
                "status": "provisional_close",
                "checked_at": "2026-11-30 17:50",
                "source": "https://www.cboe.com/tradable_products/vix/",
                "note": "黑五半日市 3 日内核销窗口内，暂采官网读数。",
            },
        }
        self.assertEqual(self._validate(within, validated_on=date(2026, 11, 30)), [])

        # US full holiday (2026-11-26 Thanksgiving) cannot be used as gate-4 threshold reference date.
        bad_holiday_ref = deepcopy(within)
        bad_holiday_ref["tier1_gate4_threshold_date"] = "2026-11-26"
        self.assertTrue(
            any("第四关比较日期错" in e for e in self._validate(bad_holiday_ref, validated_on=date(2026, 11, 30)))
        )

        # Exceeding 3 days (cutoff 2026-12-01 18:00 BJT == 2026-12-01 05:00 EST -> 4 days > 3 days): MUST fail.
        expired = deepcopy(within)
        expired.update(
            edition_id="2026-12-01_1800",
            as_of_short="2026-12-01 18:00",
            as_of_bjt="2026年12月1日（周二）18:00",
            cfets_fixing_date="2026-12-01",
            spot_gold_ny_close_date="2026-11-30",
            tier1_gate4_threshold_date="2026-11-27",
            tier1_gate4_target_date="2026-11-30",
            vix_close=29.10,
            vix_10d_window_end="2026-11-30",
        )
        expired["vix_10d_session_closes"] = expired["vix_10d_session_closes"][1:] + [
            {"date": "2026-11-30", "close": 29.10},
        ]
        expired["vix_daily_row_checks"]["2026-11-27"]["checked_at"] = "2026-12-01 17:50"
        errors = self._validate(expired, validated_on=date(2026, 12, 1))
        self.assertTrue(any("暂定收盘超期" in e and "2026-11-27" in e for e in errors), errors)

    def test_tier0_red_light_blocks_verdict_headline_and_persona_actions(self):
        snap = _fixture()
        master = _read_json(GOLD / "master_snapshot.json")
        self.changes.write_text(f"<!-- GOLD_EDITION_CHANGELOG {EDITION} -->", encoding="utf-8")
        self.scorecard.write_text(f"<!-- GOLD_EDITION_SCORECARD {EDITION} -->", encoding="utf-8")
        review = {
            "edition_id": EDITION,
            "as_of_short": AS_OF,
            "note": "四关已核验。",
            "sources": {gate_id: ["https://example.com/fixture"] for gate_id in rules.ENTRY_GATE_IDS},
            "forecast_review": {"status": "none_due", "note": "本期无到期预测。", "sources": []},
        }
        self.audit.write_text("<!-- GOLD_EDITION_REVIEW " + json.dumps(review) + " -->", encoding="utf-8")

        raw = _sanitize_for_converged(_modify_directive(
            ARCHIVED_REPORT.read_text(), "DAILY_META",
            lambda meta: meta.update(edition_id=EDITION, as_of_short=AS_OF, timestamp=AS_OF),
        ))

        def chart_ids(chart):
            for check, gate_id in zip(chart["checks"], rules.ENTRY_GATE_IDS):
                check["id"] = gate_id

        raw = _modify_directive(raw, "DAILY_CHART_SWITCH", chart_ids)
        report = self.path / f"{EDITION}_晚报_黄金深度研报.md"
        report.write_text(raw, encoding="utf-8")
        self.assertEqual(lint.check_file(report, snap, master), ([], []))

        cases = (
            (
                "DAILY_VERDICT",
                lambda cfg: cfg.update(headline="今日红灯期建议立即买入黄金 518660"),
                "[Gate 5 DAILY_VERDICT.headline动作冲突]",
            ),
            (
                "DAILY_VERDICT",
                lambda cfg: cfg["bullets"].append("现在可直接定投 518880 黄金"),
                "DAILY_VERDICT.bullets[",
            ),
            (
                "DAILY_PERSONA",
                lambda cfg: cfg["cards"][0]["actions"].append("红灯期开启半额自动定投"),
                "DAILY_PERSONA.cards[1:",
            ),
            (
                "DAILY_PERSONA",
                lambda cfg: cfg["cards"][1]["actions"].append("建议直接买入黄金 008142"),
                "DAILY_PERSONA.cards[2:",
            ),
        )
        for directive, mutate, expected_err in cases:
            with self.subTest(directive=directive, expected_err=expected_err):
                mutated = _modify_directive(raw, directive, mutate)
                report.write_text(mutated, encoding="utf-8")
                errors, _ = lint.check_file(report, snap, master)
                self.assertTrue(any(expected_err in e and "动作冲突" in e for e in errors), errors)

        # Guarded red-light text in DAILY_VERDICT.headline & DAILY_PERSONA.cards[].actions remains allowed
        guarded = _modify_directive(
            raw, "DAILY_VERDICT",
            lambda cfg: cfg.update(headline="红灯期严禁买入黄金 518660，等四关全部通过后再定投"),
        )
        guarded = _modify_directive(
            guarded, "DAILY_PERSONA",
            lambda cfg: cfg["cards"][0]["actions"].append("暂不定投 518880，待转黄灯确认后再分批建仓"),
        )
        report.write_text(guarded, encoding="utf-8")
        self.assertEqual(lint.check_file(report, snap, master), ([], []))

    def test_gold_rsi_open_finding_and_changelog_internal_leak_blocked(self):
        # 1. RSI open finding & reviewer_completed=False blocked; disclosed_caveat passes
        self.rsi_playbook.write_text(
            "# 黄金复盘规则\n\n- Tier B 可自动沉淀经验。\n- Tier C 核心门禁规则只读。\n",
            encoding="utf-8",
        )
        scores = dict.fromkeys(lint.RSI_REQUIRED_SCORE_KEYS, 5)
        base_run = {
            "run_id": EDITION,
            "scores": scores,
            "total_score": 30,
            "max_score": 30,
        }

        self.rsi_metrics.write_text(json.dumps({
            "runs": [{
                **base_run,
                "review_closure": {
                    "reviewer_completed": True,
                    "findings": [{"description": "口径未核销", "status": "open"}],
                },
            }],
        }, ensure_ascii=False), encoding="utf-8")
        errs, warns = [], []
        lint.check_rsi_artifacts(errs, warns)
        self.assertTrue(any("[RSI 盲审未闭环]" in e for e in errs), errs)

        self.rsi_metrics.write_text(json.dumps({
            "runs": [{
                **base_run,
                "review_closure": {"reviewer_completed": False, "findings": []},
            }],
        }, ensure_ascii=False), encoding="utf-8")
        errs, warns = [], []
        lint.check_rsi_artifacts(errs, warns)
        self.assertTrue(any("[RSI 盲审未完成]" in e for e in errs), errs)

        self.rsi_metrics.write_text(json.dumps({
            "runs": [{
                **base_run,
                "review_closure": {
                    "reviewer_completed": True,
                    "findings": [{"description": "官方延迟已透明披露", "status": "disclosed_caveat"}],
                },
            }],
        }, ensure_ascii=False), encoding="utf-8")
        errs, warns = [], []
        lint.check_rsi_artifacts(errs, warns)
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])

        # 2. CHANGELOG.md internal engineering leak & deprecated PDF link blocked
        clean_scorecard = (
            "# 黄金深度研报公开记分卡\n\n"
            "本页面向所有读者公开追踪历史预判命中情况、关键宏观阈值验证与客观复盘记录，"
            "所有结论均以公开一手官方数据为准，不夸大、不隐瞒、不事后改口，持续以透明统计口径接受检验。"
            "每期更新都会按既定时间节点核对现货收盘、实际利率、美元指数、波动率与跨资产联动指标，"
            "确保历史判断与实盘结果一一对应、全程可追溯，并定期汇总已到期预判的命中率、偏离原因与方法论改进，"
            "帮助普通投资者清晰看到哪些判断兑现、哪些风险提前发出预警，以及后续仓位纪律应当如何执行。\n"
        )
        self.scorecard.write_text(clean_scorecard, encoding="utf-8")
        self.changes.write_text(
            f"# 演化日志\n\n<!-- GOLD_EDITION_CHANGELOG {EDITION} -->\n\n- 2026-11-26：同步纯网页版面与四关数据。\n",
            encoding="utf-8",
        )
        errs, warns = [], []
        lint.check_calendar_and_scorecard(errs, warns)
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])

        self.changes.write_text(
            f"# 演化日志\n\n<!-- GOLD_EDITION_CHANGELOG {EDITION} -->\n\n"
            "- 更新 data_snapshot.json 与 lint_readability.py，由红队完成 V7.2 验收。\n",
            encoding="utf-8",
        )
        errs, warns = [], []
        lint.check_calendar_and_scorecard(errs, warns)
        self.assertTrue(any("[演化日志内部词泄露]" in e for e in errs), errs)

        self.changes.write_text(
            f"# 演化日志\n\n<!-- GOLD_EDITION_CHANGELOG {EDITION} -->\n\n"
            "- 附件下载：[最新日报](2026-11-26_1800_晚报_黄金深度研报.pdf)\n",
            encoding="utf-8",
        )
        errs, warns = [], []
        lint.check_calendar_and_scorecard(errs, warns)
        self.assertTrue(any("[演化日志二进制死链]" in e for e in errs), errs)

    def test_data_caveats_allows_single_source_and_publication_exception(self):
        snap = _fixture()
        snap["data_caveats"] = [
            {
                "id": "gold_single_src_demo",
                "market": "gold",
                "category": "single_source",
                "severity": "info",
                "item": "伦敦午盘定盘单一官源采录",
                "detail": "因休市前交叉数据源尚未刷新，暂以交易所官方单源读数披露。",
                "impact": "不影响四关硬门槛与红灯结论。",
                "next_review": "2026-11-27_0730",
            },
            {
                "id": "gold_pub_exc_demo",
                "market": "gold",
                "category": "publication_exception",
                "severity": "warn",
                "item": "感恩节休市特别版次说明",
                "detail": "纽约常规盘休市期间保留前一日官收基线并在下一交易班次核销。",
                "impact": "仅影响盘口时效，红灯新买锁保持不变。",
                "next_review": "2026-11-27_1800",
            },
        ]
        self.assertEqual(self._validate(snap), [])

        bad = deepcopy(snap)
        bad["data_caveats"][0]["category"] = "unknown_category"
        errors = self._validate(bad)
        self.assertTrue(any("信息缺口枚举错" in e and "unknown_category" in e for e in errors), errors)

    def test_svg_geometry_detects_overlap_and_oob_and_passes_clean_svg(self):
        from scripts import svg_geometry

        clean_svg = (
            '<svg viewBox="0 0 640 240" xmlns="http://www.w3.org/2000/svg">'
            '<text x="24" y="30" font-size="12">顶部标题</text>'
            '<text x="24" y="120" font-size="12">下方标签</text>'
            '</svg>'
        )
        self.assertEqual(svg_geometry.check_svg_text_geometry(clean_svg), [])

        overlap_svg = (
            '<svg viewBox="0 0 640 240" xmlns="http://www.w3.org/2000/svg">'
            '<text x="100" y="60" font-size="12">重叠标签甲</text>'
            '<text x="105" y="62" font-size="12">重叠标签乙</text>'
            '</svg>'
        )
        ov_issues = svg_geometry.check_svg_text_geometry(overlap_svg)
        self.assertTrue(any("重叠" in i for i in ov_issues), ov_issues)

        oob_svg = (
            '<svg viewBox="0 0 640 240" xmlns="http://www.w3.org/2000/svg">'
            '<text x="610" y="60" font-size="12">这段文字明显超出画布右边界</text>'
            '</svg>'
        )
        oob_issues = svg_geometry.check_svg_text_geometry(oob_svg)
        self.assertTrue(any("越界" in i for i in oob_issues), oob_issues)

    def test_signal_noise_intro_count_mismatch_rejected(self):
        snap = _fixture()
        master = _read_json(GOLD / "master_snapshot.json")
        self.changes.write_text(f"<!-- GOLD_EDITION_CHANGELOG {EDITION} -->", encoding="utf-8")
        self.scorecard.write_text(f"<!-- GOLD_EDITION_SCORECARD {EDITION} -->", encoding="utf-8")
        review = {
            "edition_id": EDITION,
            "as_of_short": AS_OF,
            "note": "四关已核验。",
            "sources": {gate_id: ["https://example.com/fixture"] for gate_id in rules.ENTRY_GATE_IDS},
            "forecast_review": {"status": "none_due", "note": "本期无到期预测。", "sources": []},
        }
        self.audit.write_text("<!-- GOLD_EDITION_REVIEW " + json.dumps(review) + " -->", encoding="utf-8")

        raw = _sanitize_for_converged(_modify_directive(
            ARCHIVED_REPORT.read_text(encoding="utf-8"), "DAILY_META",
            lambda meta: meta.update(edition_id=EDITION, as_of_short=AS_OF, timestamp=AS_OF),
        ))

        def chart_ids(chart):
            for check, gate_id in zip(chart["checks"], rules.ENTRY_GATE_IDS):
                check["id"] = gate_id

        raw = _modify_directive(raw, "DAILY_CHART_SWITCH", chart_ids)
        # Expand noises to 3 items while Part 1 lead / title still claims 2 noise items ("2 条假象")
        raw_mismatch = _modify_directive(
            raw,
            "DAILY_SIGNAL_NOISE",
            lambda cfg: (
                cfg.update(title="今晚资讯过滤器：只盯 2 件真信号，把 2 条假象直接划走"),
                cfg["noises"].append({"head": "第三条假象传闻", "body": "官方口径明确澄清，纯属噪音。"}),
            ),
        )
        report = self.path / f"{EDITION}_晚报_黄金深度研报.md"
        report.write_text(raw_mismatch, encoding="utf-8")
        errors, _ = lint.check_file(report, snap, master)
        self.assertTrue(any("噪音计数冲突" in e or "计数冲突" in e for e in errors), errors)

        # Updating both lead and title to 3 noise items passes cleanly
        raw_fixed = _modify_directive(
            raw_mismatch,
            "DAILY_SIGNAL_NOISE",
            lambda cfg: cfg.update(title="今晚资讯过滤器：只盯 2 件真信号，把 3 条假象直接划走"),
        )
        raw_fixed = raw_fixed.replace("把两条失实传言直接划走", "把三条失实传言直接划走")
        report.write_text(raw_fixed, encoding="utf-8")
        self.assertEqual(lint.check_file(report, snap, master), ([], []))

    def test_resolve_archived_report_supports_monthly_archive_fallback(self):
        with TemporaryDirectory() as tmp:
            fake_gold = Path(tmp)
            arch = fake_gold / "daily" / "archive" / "2026-11" / "sample_legacy.md"
            arch.parent.mkdir(parents=True)
            arch.write_text("# archived\n", encoding="utf-8")
            with patch.object(sys.modules[__name__], "GOLD", fake_gold):
                self.assertEqual(_resolve_archived_report("sample_legacy.md"), arch)


if __name__ == "__main__":
    unittest.main()
