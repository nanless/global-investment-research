"""Plan the three equity deliveries for a scheduled Beijing edition."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit

MARKETS = ("a_share", "hk_stock", "us_stock")
_EDITION_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(0730|1800)(?:_r([2-9]|[1-9]\d+))?")
_WATCH_TYPES = {"partial_holiday", "half_day", "long_holiday_start", "full_holiday_and_rollover"}
_MODE_WATCH = "mode_2_watch_brief"
_MODE_CLOSED = "mode_3_index_changelog_only"


def _date(value: object) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_edition_id(value: object) -> tuple[str, int, int] | None:
    match = _EDITION_RE.fullmatch(value) if isinstance(value, str) else None
    if match and _date(match[1]):
        return match[1], int(match[2]), int(match[3] or 1)
    return None


def _strings(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(x, str) and x.strip() for x in value)


def _gold_calendar_errors(calendar: dict) -> list[str]:
    if not isinstance(calendar, dict) or calendar.get("timezone") != "Asia/Shanghai":
        return ["黄金日历须为北京时间 Asia/Shanghai 的对象"]
    if not _date(calendar.get("as_of")) or not isinstance(calendar.get("calendar_overrides"), list):
        return ["黄金日历须有有效 as_of 日期及 calendar_overrides 数组"]
    errors = []
    ids = set()
    for index, row in enumerate(calendar["calendar_overrides"]):
        label = f"黄金日历 calendar_overrides[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{label} 须为对象")
            continue
        event_id, start = row.get("id"), row.get("date")
        quarter = re.fullmatch(r"\d{4}-Q[1-4]", start) if isinstance(start, str) else None
        end = _date(row.get("end_date"))
        first = _date(f"{start[:4]}-{(int(start[-1]) - 1) * 3 + 1:02}-01") if quarter else _date(start)
        if not first or not end or end < first:
            errors.append(f"{label} 的日期范围无效")
        if not isinstance(event_id, str) or not event_id or event_id in ids:
            errors.append(f"{label}.id 缺失或重复")
        else:
            ids.add(event_id)
        markets = row.get("markets")
        if not _strings(markets) or len(set(markets)) != len(markets):
            errors.append(f"{label}.markets 缺失或重复")
        editions = row.get("affected_editions")
        if not _strings(editions) or len(set(editions)) != len(editions) or any(
            not (quarter and value == f"{start}_ongoing") and (
                (key := parse_edition_id(value)) is None or key[2] != 1
            )
            for value in editions
        ):
            errors.append(f"{label}.affected_editions 含无效或重复班次")
        if not isinstance(row.get("trading_hours_bjt"), dict) or not row["trading_hours_bjt"]:
            errors.append(f"{label}.trading_hours_bjt 缺少交易时段")
    return errors


def calendar_rules(state: dict, calendar: dict) -> tuple[list[dict], list[str]]:
    """Validate both calendars. The equity rows specify per-market publication effects."""
    errors = _gold_calendar_errors(calendar)
    overrides = state.get("calendar_overrides")
    if not isinstance(overrides, list):
        return [], [*errors, "calendar_overrides 须为数组"]

    shared = {row["id"]: row for row in calendar["calendar_overrides"]} if not errors else {}
    gold_markets = {"a_share": "CN_A_SHARE", "hk_stock": "HK_EQUITY", "us_stock": "US_EQUITY"}
    rules = []
    for index, row in enumerate(overrides):
        label = f"calendar_overrides[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{label} 须为对象")
            continue
        first = _date(row.get("date_cst"))
        last = _date(row.get("end_date_cst", row.get("date_cst")))
        markets = row.get("markets_affected")
        mode, kind = row.get("mode"), row.get("type")
        if not first or not last or first > last:
            errors.append(f"{label} 的 date_cst / end_date_cst 日期范围无效")
            continue
        if not _strings(markets) or any(m not in MARKETS for m in markets) or len(set(markets)) != len(markets):
            errors.append(f"{label}.markets_affected 含未知、重复市场或缺失")
            continue
        if not isinstance(kind, str) or not kind.strip() or not isinstance(mode, str) or not (
            mode in ("mode_1_high_alert", _MODE_WATCH, _MODE_CLOSED, "timezone_shift_edt", "timezone_shift_est")
            or re.fullmatch(r"rollover_\d{4}_(?:0[1-9]|1[0-2])_to_\d{4}_(?:0[1-9]|1[0-2])", mode)
        ):
            errors.append(f"{label} 的 type 或 mode 无效")
            continue
        if ((kind in _WATCH_TYPES or kind == "full_holiday") != (mode in (_MODE_WATCH, _MODE_CLOSED))
                or (mode == _MODE_CLOSED and set(markets) != set(MARKETS))):
            errors.append(f"{label} 的休市类型、模式与受影响市场不一致")
            continue
        sessions = row.get("affected_sessions")
        if sessions is not None:
            if not _strings(sessions) or len(set(sessions)) != len(sessions) or any(
                (key := parse_edition_id(value)) is None or key[2] != 1
                or not first <= date.fromisoformat(key[0]) <= last + timedelta(days=1)
                for value in sessions
            ):
                errors.append(f"{label}.affected_sessions 含无效、重复或超出日期范围的班次")
                continue
            if first == last and markets == ["us_stock"] and mode == _MODE_WATCH:
                expected = {f"{first}_1800", f"{first + timedelta(days=1)}_0730"}
                if set(sessions) != expected:
                    errors.append(f"{label} 美股休市窗口应覆盖当日晚刊和次日早刊")
        if "source_url" in row and not _valid_evidence(row["source_url"]):
            errors.append(f"{label}.source_url 须为有效 HTTPS 网址")
        if "gold_event_id" in row and shared:
            reference = row["gold_event_id"]
            event = shared.get(reference) if isinstance(reference, str) else None
            if (not event or event["date"] != first.isoformat() or event["end_date"] != last.isoformat()
                    or any(gold_markets[market] not in event["markets"] for market in markets)
                    or (markets == ["us_stock"] and sessions is not None and set(sessions) != set(event["affected_editions"]))):
                errors.append(f"{label}.gold_event_id 与黄金日历的日期、市场或美股场次不一致")
        if "session_closes_cst" in row:
            closes = row["session_closes_cst"]
            try:
                if not isinstance(closes, dict) or not closes:
                    raise ValueError
                for value in closes.values():
                    close = datetime.fromisoformat(value)
                    if close.utcoffset() != timedelta(hours=8) or not first <= close.date() <= last + timedelta(days=1):
                        raise ValueError
            except (TypeError, ValueError):
                errors.append(f"{label}.session_closes_cst 须为交易日或次日的有效北京时间")

        if mode not in (_MODE_WATCH, _MODE_CLOSED):
            continue
        rules.append(dict(first=first, last=last, markets=markets, sessions=sessions, mode=mode, kind=kind))

    for left, rule in enumerate(rules):
        if any(
            set(rule["markets"]) & set(other["markets"])
            and max(rule["first"], other["first"]) <= min(rule["last"], other["last"])
            and (not rule["sessions"] or not other["sessions"] or set(rule["sessions"]) & set(other["sessions"]))
            for other in rules[:left]
        ):
            errors.append(f"{rule['first']} 有重复或重叠的权益休市规则")
    return rules, errors


def _scheduled_types(day: date, hhmm: int, rules: list[dict]) -> dict[str, str | None]:
    weekday, morning = day.weekday(), hhmm == 730
    plan: dict[str, str | None] = dict.fromkeys(MARKETS)
    if weekday < 5:
        plan.update(a_share="light" if morning else "main", hk_stock="light" if morning else "main",
                    us_stock="main" if morning and weekday != 0 else "light")
    elif weekday == 5 and morning:
        plan["us_stock"] = "main"

    session = f"{day}_{hhmm:04}"
    for rule in rules:
        if rule["mode"] == _MODE_CLOSED and (
            session in rule["sessions"] if rule["sessions"] else rule["first"] <= day <= rule["last"]
        ):
            return dict.fromkeys(MARKETS)
        for market in rule["markets"]:
            if plan[market] is None:
                continue
            trading_day = day - timedelta(days=1) if market == "us_stock" and morning else day
            affects = (
                session in rule["sessions"] if rule["sessions"] else rule["first"] <= trading_day <= rule["last"]
            )
            if affects:
                plan[market] = None if weekday == 5 and rule["kind"] != "half_day" else "holiday_watch"
    return plan


def _valid_evidence(value: object) -> bool:
    if not isinstance(value, str) or any(ch.isspace() for ch in value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
    except ValueError:
        return False


def edition_plan(edition_id: str, state: dict, calendar: dict) -> tuple[dict, list[str]]:
    key = parse_edition_id(edition_id)
    if key is None:
        return {}, ["edition_id 须为 YYYY-MM-DD_0730 或 YYYY-MM-DD_1800，可附 _rN"]
    rules, errors = calendar_rules(state, calendar)
    if errors:
        return {}, errors
    day, hhmm, revision = key
    scheduled = _scheduled_types(date.fromisoformat(day), hhmm, rules)
    exceptions = state.get("publication_exceptions", {})
    if not isinstance(exceptions, dict):
        return {}, ["publication_exceptions 须为对象"]
    if exceptions and exceptions.get("edition_id") == edition_id:
        rows = exceptions.get("markets")
        if not isinstance(rows, dict) or not rows or any(m not in MARKETS for m in rows):
            return {}, ["publication_exceptions.markets 须列出当班有效市场"]
    else:
        rows = {}

    plans = {}
    suffix = f"_r{revision}" if revision > 1 else ""
    market_state = state.get("markets")
    for market, scheduled_type in scheduled.items():
        kind = scheduled_type
        reason = "calendar_reuse" if kind is None else "scheduled"
        if market in rows:
            row = rows[market]
            if not isinstance(row, dict) or not isinstance(row.get("reason"), str) or not row["reason"].strip():
                errors.append(f"{market} 出版例外须说明实际原因")
                continue
            exception = row.get("kind")
            if exception == "source_outage" and kind is not None and _valid_evidence(row.get("evidence_url")):
                next_review = parse_edition_id(row.get("next_review_session"))
                if next_review and next_review[2] == 1 and next_review[:2] > key[:2]:
                    kind, reason = None, exception
                else:
                    errors.append(f"{market} 数据故障须登记后续核验班次")
            elif exception == "breaking_event" and kind is None and row.get("severity") in ("P0", "P1") and _valid_evidence(row.get("evidence_url")):
                kind, reason = "holiday_watch", exception
            elif exception == "revision_reuse" and revision > 1 and kind is not None:
                kind, reason = None, exception
            else:
                errors.append(f"{market} 出版例外与计划形态不符，或缺少官方 HTTPS 证据")
        entry = {"action": "publish" if kind else "reuse", "edition_type": kind, "reason": reason}
        if kind is not None:
            entry["required_file"] = f"daily/{day}_{hhmm:04}_{market}{suffix}.md"
        else:
            row = market_state.get(market) if isinstance(market_state, dict) else None
            entry["latest_daily"] = row.get("latest_daily") if isinstance(row, dict) else None
        plans[market] = entry
    return {"edition_id": edition_id, "period_slug": day[:7].replace("-", "_"), "markets": plans}, errors
