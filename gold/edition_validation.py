"""Calendar and market data checks for newly issued gold reports."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from chart_input import load_gold_json


BEIJING = ZoneInfo("Asia/Shanghai")
NEW_YORK = ZoneInfo("America/New_York")
LAST_LEGACY_EDITION = ("2026-11-25", "1800", 2)
EDITION_SLOTS = ("0730", "1130", "1800")
ENTRY_GATE_IDS = ("real_yield", "rate_spread", "vix", "ny_close")
MAX_EDITION_EARLY = timedelta(minutes=5)
MAX_EDITION_LAG = timedelta(hours=6)
MAX_VIX_QUOTE_AGE = timedelta(minutes=30)
MAX_PENDING_DAILY_CHECK_AGE = timedelta(hours=4)
MIN_CALENDAR_HORIZON = timedelta(days=30)
MAX_CALENDAR_VERIFIED_AGE = timedelta(days=90)
VIX_DAILY_SOURCE = "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
DEFAULT_VIX_WINDOWS = ((time(3, 15), time(9, 25)), (time(9, 31), time(16, 15)))
BASE_DAY = timedelta(days=1)
EFFR_RELEASE_TIME = time(9)


class VixSession(NamedTuple):
    windows: tuple[tuple[time, time], ...]
    close: time | None
    daily_row_check_after: time | None = None


def parse_day(value: object) -> date | None:
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return None


def _parse_clock(value: object) -> time | None:
    if isinstance(value, str) and re.fullmatch(r"[0-2]\d:[0-5]\d", value):
        try:
            return time.fromisoformat(value)
        except ValueError:
            pass
    return None


def evidence_url(value: object) -> bool:
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and parsed.username is None
    except ValueError:
        return False


def _valid_number(value: object) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def check_edition_time(edition: tuple[str, str, int], as_of: datetime, errors: list[str]) -> bool:
    day, slot, revision = edition
    if slot not in EDITION_SLOTS or revision < 1:
        errors.append("[Gate 5 班次非法] 新刊仅支持 07:30、11:30 与 18:00 班次")
        return False
    if as_of.tzinfo is not None:
        as_of = as_of.astimezone(BEIJING).replace(tzinfo=None)
    scheduled = datetime.strptime(f"{day} {slot}", "%Y-%m-%d %H%M")
    if not -MAX_EDITION_EARLY <= as_of - scheduled <= MAX_EDITION_LAG:
        errors.append("[Gate 5 班次截点错] 北京时间 as_of_short 须在所标班次前五分钟至其后六小时内")
        return False
    return True


def cutoff_displayed(value: object, as_of: datetime) -> bool:
    if not isinstance(value, str):
        return False
    iso = as_of.strftime("%Y-%m-%d %H:%M")
    cn = rf"{as_of.year}年0?{as_of.month}月0?{as_of.day}日(?:[（(][^）)]+[）)])?\s*{as_of:%H:%M}"
    return bool(re.search(rf"(?<!\d)(?:{re.escape(iso)}|{cn})(?!\d)", value))


def _calendar_override_dates(event: dict) -> tuple[date | None, date | None]:
    begin = parse_day(event.get("date"))
    end = parse_day(event.get("end_date"))
    if begin is None and event.get("overlay_mode") == "NONE" and isinstance(event.get("date"), str):
        quarter = re.fullmatch(r"(\d{4})-Q([1-4])", event["date"])
        if quarter:
            begin = parse_day(f"{quarter[1]}-{int(quarter[2]) * 3 - 2:02}-01")
    return begin, end


def _validate_overrides(calendar: dict, first: date, last: date, exceptions: dict, errors: list[str]) -> None:
    overrides = calendar.get("calendar_overrides")
    if not isinstance(overrides, list):
        errors.append("[外置日历明细错] calendar_overrides 须为数组")
        return
    ids = set()
    for event in overrides:
        if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not event["id"].strip():
            errors.append("[外置日历明细错] 每条记录须有唯一 id")
            continue
        event_id = event["id"]
        begin, end = _calendar_override_dates(event)
        markets = event.get("markets")
        mode = event.get("overlay_mode")
        if (
            event_id in ids or begin is None or end is None or not first <= begin <= end <= last
            or mode not in ("A", "B", "C", "GLOBAL", "NONE") or not isinstance(markets, list)
            or not markets or any(not isinstance(market, str) or not market.strip() for market in markets)
        ):
            errors.append(f"[外置日历明细错] {event_id}: 日期超出有效期、id 重复或市场及休市模式非法")
            continue
        ids.add(event_id)
        if "US_EQUITY" in markets and mode in ("A", "GLOBAL"):
            for n in range((end - begin).days + 1):
                day = begin + n * BASE_DAY
                if day.weekday() < 5 and day.isoformat() not in exceptions:
                    errors.append(f"[外置日历 VIX 例外缺失] {event_id}: {day} 须明确登记 Cboe 现货指数时段")


def vix_calendar(
    calendar: dict | None, as_of: datetime, errors: list[str], *, verified_by: date | None = None,
) -> tuple[date, dict] | None:
    """Use the evidence cutoff for market coverage and a separate limit for calendar verification."""
    if not isinstance(calendar, dict) or calendar.get("timezone") != "Asia/Shanghai":
        errors.append("[外置日历时区错] market_calendar.json 须声明 Asia/Shanghai")
        return None
    coverage = calendar.get("coverage")
    first = parse_day(coverage.get("start_date")) if isinstance(coverage, dict) else None
    last = parse_day(coverage.get("end_date")) if isinstance(coverage, dict) else None
    verified = parse_day(coverage.get("verified_on")) if isinstance(coverage, dict) else None
    source = coverage.get("vix_schedule_source") if isinstance(coverage, dict) else None
    if (
        first is None or last is None or verified is None or not evidence_url(source)
        or not first <= as_of.date() <= last or not first <= verified <= last
        or as_of.date() - verified > MAX_CALENDAR_VERIFIED_AGE
        or last - as_of.date() < MIN_CALENDAR_HORIZON
    ):
        errors.append("[外置日历覆盖不足] 需有效起止日期、近 90 日核证日期、Cboe 来源和班次后至少 30 天覆盖")
        return None
    if verified > (verified_by or as_of.date()):
        errors.append("[外置日历核证日期过晚] 首刊须在观测日或之前核证；修订刊不得使用晚于实际验收日的核证记录")
        return None
    remaining_horizon = last - as_of.date()
    if MIN_CALENDAR_HORIZON <= remaining_horizon < timedelta(days=60):
        print(
            f"[INFO] market_calendar.json 覆盖余量剩余 {remaining_horizon.days} 天（至 {last}），建议提前滚动延长覆盖区间。"
        )
    rows = calendar.get("vix_session_exceptions")
    if not isinstance(rows, dict):
        errors.append("[外置日历 VIX 例外错] vix_session_exceptions 须为对象")
        return None
    _validate_overrides(calendar, first, last, rows, errors)
    exceptions = {}
    for key, row in rows.items():
        day = parse_day(key)
        if (
            day is None or not first <= day <= last or not isinstance(row, dict)
            or "official_close_et" not in row or not isinstance(row.get("windows_et"), list)
        ):
            errors.append(f"[外置日历 VIX 例外错] {key}: 缺少有效日期、windows_et 或 official_close_et")
            continue
        windows = [
            (_parse_clock(pair[0]), _parse_clock(pair[1]))
            for pair in row["windows_et"]
            if isinstance(pair, list) and len(pair) == 2
        ]
        close = _parse_clock(row["official_close_et"])
        check_after = _parse_clock(row.get("daily_row_check_after_et"))
        if (
            len(windows) != len(row["windows_et"])
            or any(start is None or end is None or start >= end for start, end in windows)
            or any(windows[i][1] >= windows[i + 1][0] for i in range(len(windows) - 1))
            or (row["official_close_et"] is not None and (close is None or any(end > close for _, end in windows)))
            or ("daily_row_check_after_et" in row and (
                check_after is None or close is not None or any(end > check_after for _, end in windows)
            ))
        ):
            errors.append(f"[外置日历 VIX 例外错] {key}: 东部时段须升序不重叠，日收或日线核验界线须在窗口之后")
            continue
        exceptions[day] = VixSession(tuple(windows), close, check_after)
    return first, exceptions


def _vix_session(day: date, exceptions: dict) -> VixSession:
    if day in exceptions:
        return exceptions[day]
    if day.weekday() >= 5:
        return VixSession((), None)
    return VixSession(DEFAULT_VIX_WINDOWS, DEFAULT_VIX_WINDOWS[-1][1])


def _parse_bjt_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=BEIJING)
    except ValueError:
        return None


def _has_holiday_daily_row(
    day: date,
    eligible: datetime,
    cutoff: datetime,
    checks: dict,
    errors: list[str],
    *,
    has_windows: bool = False,
    recorded_dates: set[str] | None = None,
) -> bool:
    check = checks.get(day.isoformat())
    if not isinstance(check, dict):
        errors.append(f"[Gate 5 VIX 节日日线待核] {day} 须记录官方 CSV 当日行状态")
        return False
    checked = _parse_bjt_timestamp(check.get("checked_at"))
    status = check.get("status")
    note = check.get("note")
    source = check.get("source")
    allowed_statuses = (
        ("published", "provisional_close", "pending", "no_row_confirmed")
        if has_windows
        else ("published", "pending", "no_row_confirmed")
    )
    valid_source = evidence_url(source) if (has_windows and status == "provisional_close") else source == VIX_DAILY_SOURCE
    if (
        status not in allowed_statuses
        or not isinstance(note, str) or not note.strip() or not valid_source
        or checked is None or not eligible <= checked <= cutoff
    ):
        errors.append(f"[Gate 5 VIX 节日日线证据错] {day} 须提供该行状态、官方 CSV 或有效来源、北京时间和核验说明")
        return False
    if status == "pending" and cutoff - checked > MAX_PENDING_DAILY_CHECK_AGE:
        errors.append(f"[Gate 5 VIX 节日待披露需重查] {day} 本次截点前四小时内须重新查看官方 CSV")
    if status == "provisional_close" and cutoff.date() - day > timedelta(days=3):
        errors.append(f"[Gate 5 VIX 暂定收盘超期] {day} 须以 Cboe 官方 CSV 终值核销")
    if status == "provisional_close" and cutoff.date() > day and cutoff - checked > MAX_EDITION_LAG:
        errors.append(f"[Gate 5 VIX 待复核需重查] {day} 次日班次须在本班窗口内重新核查官方 CSV")
    if status == "no_row_confirmed":
        confirmation = check.get("confirmation_source")
        has_cboe_confirm = (
            evidence_url(confirmation)
            and (urlsplit(confirmation).hostname or "").endswith(".cboe.com")
        )
        next_pub = parse_day(check.get("next_published_date"))
        next_check = checks.get(next_pub.isoformat()) if next_pub is not None else None
        next_pub_csv_ok = (
            next_check is None
            or (isinstance(next_check, dict) and next_check.get("status") == "published")
        )
        has_csv_proof = (
            source == VIX_DAILY_SOURCE
            and next_pub is not None
            and day < next_pub <= cutoff.date()
            and (recorded_dates is None or next_pub.isoformat() in recorded_dates)
            and next_pub_csv_ok
        )
        if not (has_cboe_confirm or has_csv_proof):
            errors.append(
                f"[Gate 5 VIX 节日无日线证据缺失] {day} 须另附 Cboe 确认无日线的公告，或以官方 CSV 后续交易日 next_published_date 自证"
            )
    return status in ("published", "provisional_close")


def _has_ordinary_daily_row(day: date, close_dt: datetime, cutoff: datetime, checks: dict, errors: list[str]) -> bool:
    check = checks.get(day.isoformat())
    if check is None:
        return True
    if not isinstance(check, dict):
        errors.append(f"[Gate 5 VIX 日线证据错] {day} 的 vix_daily_row_checks 记录须为对象")
        return True
    status = check.get("status")
    note = check.get("note")
    checked = _parse_bjt_timestamp(check.get("checked_at"))
    source = check.get("source")
    if status not in ("published", "provisional_close", "pending"):
        errors.append(f"[Gate 5 VIX 日线证据错] {day} 仅允许状态 published/provisional_close/pending")
        return True
    valid_source = evidence_url(source) if status == "provisional_close" else source == VIX_DAILY_SOURCE
    if (
        not isinstance(note, str) or not note.strip() or not valid_source
        or checked is None or not close_dt <= checked <= cutoff
    ):
        errors.append(f"[Gate 5 VIX 日线证据错] {day} 须提供有效状态、来源链接、收盘后至截点间的北京时间和核验说明")
        return status != "pending"
    if status == "provisional_close" and cutoff.date() - day > timedelta(days=3):
        errors.append(f"[Gate 5 VIX 暂定收盘超期] {day} 须以 Cboe 官方 CSV 终值核销")
    if cutoff.date() > day and status in ("provisional_close", "pending") and cutoff - checked > MAX_EDITION_LAG:
        errors.append(f"[Gate 5 VIX 待复核需重查] {day} 次日班次须在本班窗口内重新核查官方 CSV")
    return status != "pending"


def _vix_completed_days(
    cutoff: datetime,
    first: date,
    exceptions: dict,
    checks: dict,
    errors: list[str],
    *,
    recorded_dates: set[str] | None = None,
) -> list[str]:
    days = []
    day = cutoff.date()
    while day >= first and len(days) < 10:
        session = _vix_session(day, exceptions)
        if session.close is not None:
            close_dt = datetime.combine(day, session.close, NEW_YORK)
            if close_dt <= cutoff and _has_ordinary_daily_row(day, close_dt, cutoff, checks, errors):
                days.append(day.isoformat())
        if session.daily_row_check_after is not None:
            eligible = datetime.combine(day, session.daily_row_check_after, NEW_YORK)
            if eligible <= cutoff and _has_holiday_daily_row(
                day, eligible, cutoff, checks, errors,
                has_windows=bool(session.windows),
                recorded_dates=recorded_dates,
            ):
                days.append(day.isoformat())
        day -= BASE_DAY
    return list(reversed(days))


def check_vix_period(snap: dict, as_of: datetime, observed_at: datetime | None, schedule: tuple[date, dict], errors: list[str]) -> bool:
    initial_errors = len(errors)
    first, exceptions = schedule
    cutoff = as_of.replace(tzinfo=BEIJING).astimezone(NEW_YORK)
    checks = snap.get("vix_daily_row_checks", {})
    if not isinstance(checks, dict):
        errors.append("[Gate 5 VIX 节日日线证据错] vix_daily_row_checks 须为日期键对象")
        return False
    dates = [row["date"] for row in snap["vix_10d_session_closes"]]
    expected = _vix_completed_days(cutoff, first, exceptions, checks, errors, recorded_dates=set(dates))
    if len(expected) != 10 or dates != expected:
        errors.append(f"[Gate 5 VIX 完整交易日不符] 截点前最近十个 Cboe 完整交易日应为 {', '.join(expected)}")
    if snap.get("vix_daily_source") != VIX_DAILY_SOURCE:
        errors.append("[Gate 5 VIX 日线来源错] 十日日收须使用 Cboe 现货指数官方历史表")
    if observed_at is None:
        if snap.get("vix_live") is not None or snap.get("vix_live_as_of") is not None:
            errors.append("[Gate 5 VIX 盘口不完整] 盘口价和观测时间须同时有效，或同时留空")
    elif snap.get("vix_live") is None:
        errors.append("[Gate 5 VIX 盘口不完整] 盘口价和观测时间须同时有效，或同时留空")
    else:
        observed = observed_at.replace(tzinfo=BEIJING).astimezone(NEW_YORK)
        windows = _vix_session(cutoff.date(), exceptions).windows
        if (
            observed.date() != cutoff.date() or not timedelta(0) <= as_of - observed_at <= MAX_VIX_QUOTE_AGE
            or not any(start <= observed.time() <= cutoff.time() <= end for start, end in windows)
        ):
            errors.append("[Gate 5 VIX 盘口过时] 观测与截点须在同一现货指数发布窗口，间隔至多 30 分钟")
    return len(errors) == initial_errors


def _load_default_exceptions() -> dict[date, VixSession]:
    cal_path = Path(__file__).with_name("market_calendar.json")
    try:
        raw = load_gold_json(cal_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = raw.get("vix_session_exceptions") if isinstance(raw, dict) else None
    if not isinstance(rows, dict):
        return {}
    out: dict[date, VixSession] = {}
    for key, row in rows.items():
        day = parse_day(key)
        if day is None or not isinstance(row, dict) or not isinstance(row.get("windows_et"), list):
            continue
        windows = tuple(
            (s, e)
            for pair in row["windows_et"]
            if isinstance(pair, list) and len(pair) == 2
            for s, e in ((_parse_clock(pair[0]), _parse_clock(pair[1])),)
            if s is not None and e is not None
        )
        out[day] = VixSession(
            windows,
            _parse_clock(row.get("official_close_et")),
            _parse_clock(row.get("daily_row_check_after_et")),
        )
    return out


def _is_us_full_holiday(day: date, exceptions: dict[date, VixSession]) -> bool:
    ex = exceptions.get(day)
    return ex is not None and not ex.windows and ex.close is None


def _is_ny_session(day: date, exceptions: dict[date, VixSession]) -> bool:
    return day.weekday() < 5 and not _is_us_full_holiday(day, exceptions)


def _previous_ny_session(day: date, exceptions: dict[date, VixSession]) -> date:
    previous = day - BASE_DAY
    while not _is_ny_session(previous, exceptions):
        previous -= BASE_DAY
    return previous


def _is_ny_fed_business_day(day: date) -> bool:
    """Apply the New York Fed holiday calendar for unsecured rates, not exchange holidays."""
    if day.weekday() >= 5:
        return False
    for month, number in ((1, 1), (6, 19), (7, 4), (11, 11), (12, 25)):
        holiday = date(day.year, month, number)
        if holiday.weekday() == 6:
            holiday += BASE_DAY
        if day == holiday:
            return False
    nth_weekday = (day.day - 1) // 7 + 1
    if (day.month, day.weekday(), nth_weekday) in ((1, 0, 3), (2, 0, 3), (9, 0, 1), (10, 0, 2), (11, 3, 4)):
        return False
    return not (day.month == 5 and day.weekday() == 0 and day.day >= 25)


def _previous_ny_fed_business_day(day: date) -> date:
    day -= BASE_DAY
    while not _is_ny_fed_business_day(day):
        day -= BASE_DAY
    return day


def check_effr_evidence(snap: dict, as_of: datetime, errors: list[str]) -> bool:
    """Validate the latest release. A disclosed delay keeps the entry gate closed."""
    observation = parse_day(snap.get("effr_observation_date"))
    published = _parse_bjt_timestamp(snap.get("effr_published_at"))
    source = snap.get("effr_source")
    url = urlsplit(source) if evidence_url(source) else None
    official_series = url is not None and (
        (url.hostname == "fred.stlouisfed.org" and url.path.rstrip("/") in ("/series/EFFR", "/data/EFFR"))
        or (url.hostname == "www.newyorkfed.org" and url.path.rstrip("/") == "/markets/reference-rates/effr")
        or (url.hostname == "markets.newyorkfed.org" and url.path.startswith("/api/rates/unsecured/effr/"))
    )
    cutoff = as_of.astimezone(BEIJING) if as_of.tzinfo is not None else as_of.replace(tzinfo=BEIJING)
    if observation is None or published is None or published > cutoff or not official_series:
        errors.append("[Gate 5 第二关有效基金利率证据错] 须记录观测交易日、截点前公布时间和联储 EFFR 序列")
        return False
    release_et = published.astimezone(NEW_YORK)
    release_day = release_et.date()
    if not _is_ny_fed_business_day(release_day) or observation != _previous_ny_fed_business_day(release_day):
        errors.append("[Gate 5 第二关有效基金利率证据错] 公布日须对应纽约联储上一个营业日的利率")
        return False
    if release_et.time() < EFFR_RELEASE_TIME:
        errors.append("[Gate 5 第二关有效基金利率证据错] 公布时间早于美东 09:00 的常规发布点")
        return False
    cutoff_et = cutoff.astimezone(NEW_YORK)
    if _is_ny_fed_business_day(cutoff_et.date()) and cutoff_et.time() >= EFFR_RELEASE_TIME:
        latest_completed_release_day = cutoff_et.date()
    else:
        latest_completed_release_day = _previous_ny_fed_business_day(cutoff_et.date())
    if release_day < latest_completed_release_day:
        caveats = snap.get("data_caveats")
        edition = str(snap.get("edition_id") or "").split("_r", 1)[0]
        if not isinstance(caveats, list) or not any(
            isinstance(caveat, dict) and caveat.get("id") == "effr_release_delayed"
            and caveat.get("market") == "gold" and caveat.get("category") == "delayed_official"
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}_(?:0730|1130|1800)", str(caveat.get("next_review") or ""))
            and parse_day(caveat["next_review"][:10]) is not None and caveat["next_review"] > edition
            for caveat in caveats
        ):
            errors.append("[Gate 5 第二关有效基金利率证据错] 已过下一纽约联储营业日，须核对最新已公布利率或披露发布延迟")
        return False
    return True


def recheck_entry_gates(
    snap: dict,
    as_of: datetime,
    vix_passed: bool | None,
    errors: list[str],
    *,
    exceptions: dict[date, VixSession] | None = None,
    effr_current: bool = True,
) -> None:
    gates = snap.get("tier1_gates")
    if not isinstance(gates, list) or len(gates) != 4 or any(not isinstance(gate, dict) for gate in gates):
        return
    if tuple(gate.get("id") for gate in gates) != ENTRY_GATE_IDS:
        errors.append("[Gate 5 四关顺序错] 请使用 real_yield、rate_spread、vix、ny_close 四个固定 id")
    real_yield, us2y, effr, spread, close, threshold = (
        snap.get(key) for key in (
            "dfii10_fred_official_pct", "us2y_pct", "effr_pct", "spread_2y_ff_bp",
            "spot_gold_ny_close_usd", "tier1_gate4_threshold_usd",
        )
    )
    if not all(_valid_number(value) for value in (real_yield, us2y, effr, spread, close, threshold)) or min(close, threshold) <= 0:
        errors.append("[Gate 5 四关复算数据缺失] 须记录实际收益率、两年期收益率、有效联邦基金利率、利差和精确现货价")
        return
    calc_spread = (Decimal(str(us2y)) - Decimal(str(effr))) * 100
    if abs(Decimal(str(spread)) - calc_spread) > Decimal("0.5"):
        errors.append(f"[Gate 5 第二关利差不符] 两年期减有效基金利率应为 {calc_spread} 基点")
    observed_date, reference, target = (
        parse_day(snap.get(key)) for key in (
            "spot_gold_ny_close_date", "tier1_gate4_threshold_date", "tier1_gate4_target_date",
        )
    )
    cutoff = as_of.replace(tzinfo=BEIJING).astimezone(NEW_YORK)
    exc_map = _load_default_exceptions() if exceptions is None else exceptions
    breakout = None
    if (
        None in (observed_date, reference, target) or not reference < target or not reference <= observed_date <= target
        or cutoff.date() - observed_date > timedelta(days=7) or target - reference > timedelta(days=7)
        or not all(_is_ny_session(day, exc_map) for day in (observed_date, reference, target))
        or reference != _previous_ny_session(target, exc_map)
        or datetime.combine(observed_date, time(17), NEW_YORK) > cutoff
    ):
        errors.append("[Gate 5 第四关比较日期错] 已完成的纽约日收和前一有效交易日高点须对应同一次突破检验")
    else:
        breakout = observed_date == target and close > threshold
    expected = (real_yield <= 2.72, effr_current and calc_spread <= 55, vix_passed, breakout)
    for number, (gate, passed) in enumerate(zip(gates, expected), 1):
        if passed is not None and gate.get("passed") is not passed:
            errors.append(f"[Gate 5 第 {number} 关复算冲突] 按结构化来源字段复算应为 {passed}")
