"""Cash-market session rules shared by snapshot validation and the portal."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any
from zoneinfo import ZoneInfo


CASH_INDEX_MARKETS = {"a_share": "a-share", "hk_stock": "hk-stock", "us_stock": "us-stock"}
MORNING_CLOSES = {"a-share": time(11, 30), "hk-stock": time(12)}
CLOSED_SESSION_TYPES = frozenset({"partial_holiday", "long_holiday_start", "full_holiday", "full_holiday_and_rollover"})
HALF_DAY_CLOSES = {"hk-stock": time(12, 10), "us-stock": time(13)}

# Regular local close or index dissemination cutoff. Declared holidays are checked separately.
CASH_QUOTE_SESSIONS = {
    "a-share": ("Asia/Shanghai", time(15)),
    "hk-stock": ("Asia/Hong_Kong", time(16, 10)),
    "us-stock": ("America/New_York", time(16)),
    "jp-stock": ("Asia/Tokyo", time(15, 30)),
    # STOXX publishes DAX through 18:00 local time, after the Xetra closing auction.
    "de-stock": ("Europe/Berlin", time(18)),
    "euro-stock": ("Europe/Paris", time(18)),
    "fr-stock": ("Europe/Paris", time(18, 5)),
    "uk-stock": ("Europe/London", time(16, 35)),
    "tw-stock": ("Asia/Taipei", time(13, 30)),
    "kr-stock": ("Asia/Seoul", time(15, 30)),
    "in-stock": ("Asia/Kolkata", time(15, 30)),
}
INDEX_QUOTE_MARKETS = {
    "idx_N225": "jp-stock", "idx_TOPIX": "jp-stock", "idx_GDAXI": "de-stock",
    "idx_STOXX50E": "euro-stock", "idx_FCHI": "fr-stock", "idx_FTSE": "uk-stock",
    "idx_TWII": "tw-stock", "idx_KS11": "kr-stock", "idx_NSEI": "in-stock",
    "idx_932047": "a-share", "idx_sh000832": "a-share", "etf_511260": "a-share",
    "etf_511090": "a-share", "etf_511360": "a-share", "etf_513800": "a-share", "etf_159561": "a-share",
    "etf_IB01": "uk-stock", "etf_SGOV": "us-stock", "etf_TLT": "us-stock", "etf_XLRE": "us-stock",
    "etf_VXUS": "us-stock",
}
INDEX_CODE_ALIASES = {
    "idx_GDAXI": "GDAXI", "idx_STOXX50E": "STOXX50E", "idx_FCHI": "FCHI",
    "idx_KS11": "KS11", "idx_NSEI": "NSEI",
}
_CASH_CODES = {symbol.removeprefix("idx_").removeprefix("etf_").upper(): market
               for symbol, market in INDEX_QUOTE_MARKETS.items()}
_CASH_CODES.update(DAX="de-stock", SX5E="euro-stock", CAC40="fr-stock", KOSPI="kr-stock", NIFTY50="in-stock")
_QUOTE_CLOCK = re.compile(r"(?<![\d+-])([01]?\d|2[0-3])(:[0-5]\d(?::[0-5]\d)?(?:Z|[+-]\d{2}:?\d{2})?)(?![\d:])")
_NAMED_UTC_OFFSETS = {"EDT": -4, "EST": -5, "GMT": 0, "UTC": 0, "BST": 1, "CET": 1, "CEST": 2,
                      "HKT": 8, "JST": 9, "KST": 9}


def valid_iso_date(raw: Any) -> str:
    if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return ""
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return ""


def index_quote_market(group: str, row: dict) -> str | None:
    """Resolve an index or listed fund to the market whose session governs the row."""
    symbol = row.get("id") or row.get("kline_id")
    code = str(row.get("code") or "").upper()
    return (CASH_INDEX_MARKETS.get(group) or INDEX_QUOTE_MARKETS.get(str(symbol)) or _CASH_CODES.get(code))


def quote_status(stamp: str) -> str:
    for pattern, label in (
        (r"沿用|缓存", "沿用报价"), (r"官结|官方结算", "官结"), (r"午盘前|午市前", "盘中"),
        (r"午收|午盘|早盘收|\bmidday\b", "午盘"), (r"官收|官方收盘|官方终盘|\bofficial_close\b", "官收"),
        (r"盘中|实盘|\bintraday\b", "盘中"), (r"前收|收盘|\bclose\b", "收盘参考"),
    ):
        if re.search(pattern, stamp, re.IGNORECASE):
            return label
    return "盘口待核"


def quote_timestamp(stamp: str, observed_day: str) -> datetime | None:
    if not observed_day:
        return None
    clock = _QUOTE_CLOCK.search(stamp)
    if not clock:
        return None
    try:
        observation = datetime.fromisoformat(f"{observed_day}T{clock[1].zfill(2)}{clock[2]}")
    except ValueError:
        return None
    if observation.tzinfo is not None:
        return observation
    timezone_label = stamp[clock.end():].strip().upper()
    if re.match(r"ET\b|美东", timezone_label):
        return observation.replace(tzinfo=ZoneInfo("America/New_York"))
    named = re.match(r"[A-Z]+\b", timezone_label)
    if named and named[0] in _NAMED_UTC_OFFSETS:
        return observation.replace(tzinfo=timezone(timedelta(hours=_NAMED_UTC_OFFSETS[named[0]])))
    return observation.replace(tzinfo=timezone(timedelta(hours=8)))


def extract_iso_date(raw: Any) -> str:
    """Extract YYYY-MM-DD date string from ISO or Chinese date stamps."""
    s = str(raw or "").strip()
    if not s:
        return ""
    m_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)}"
    m_cn = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", s)
    if m_cn:
        return f"{m_cn.group(1)}-{int(m_cn.group(2)):02d}-{int(m_cn.group(3)):02d}"
    return ""


def _session_types(observed: str, market: str, calendar_overrides: list[dict] | None) -> set[str]:
    market_id = market.replace("-", "_")
    return {
        entry["type"] for entry in calendar_overrides or []
        if isinstance(entry, dict) and isinstance(entry.get("type"), str)
        and isinstance(entry.get("markets_affected"), list) and market_id in entry["markets_affected"]
        and (first := valid_iso_date(entry.get("date_cst"))) and first <= observed
        and observed <= valid_iso_date(entry.get("end_date_cst", first))
    }


def closing_quote_available(
    observed: str, market: str, cutoff: str, calendar_overrides: list[dict] | None = None,
    *,
    close_delay_minutes: int = 0,
    observed_closing_time: bool = False,
) -> bool:
    """Check a dated daily bar against the local cash session and declared holidays."""
    try:
        day = date.fromisoformat(observed)
        stamp = datetime.fromisoformat(cutoff)
    except (TypeError, ValueError):
        return False
    if day.weekday() >= 5:
        return False

    session_rules = _session_types(observed, market, calendar_overrides)
    if session_rules & CLOSED_SESSION_TYPES:
        return False
    if cutoff == cutoff[:10]:
        return day <= stamp.date()
    beijing = ZoneInfo("Asia/Shanghai")
    zone_name, ordinary_close = CASH_QUOTE_SESSIONS[market]
    zone = ZoneInfo(zone_name)
    close = HALF_DAY_CLOSES.get(market, ordinary_close) if "half_day" in session_rules else ordinary_close
    cutoff_at = stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=beijing)
    # HKEX's auction ends at a random instant in the last two minutes of the window.
    # A timestamped official close can fall there. Date-only data wait until the window has ended.
    earliest_offset = 2 if market == "hk-stock" and observed_closing_time else 0
    return datetime.combine(day, close, zone) + timedelta(minutes=close_delay_minutes - earliest_offset) <= cutoff_at


def snapshot_quote_timing(
    row: dict, market: str | None, cutoff: str, calendar_overrides: list[dict] | None,
    *, close_delay_minutes: int = 0,
) -> tuple[str, str, str | None]:
    """Return the market date and display label, with a reason if timing cannot support the quote."""
    stamp = str(row.get("as_of") or "")
    raw_stamp_day = extract_iso_date(stamp)
    stamp_day = valid_iso_date(raw_stamp_day)
    observed_at = quote_timestamp(stamp, stamp_day)
    supplied_days = [row[key] for key in ("quote_date", "observation_date") if key in row and row[key] is not None]
    declared_day = supplied_days[0] if supplied_days else None
    observed_day = valid_iso_date(declared_day) or stamp_day
    kind = str(row.get("quote_status") or stamp)
    status = quote_status(kind)
    if (raw_stamp_day and not stamp_day) or any(not valid_iso_date(value) for value in supplied_days):
        return observed_day, status, "行情日期无效"
    if len(supplied_days) == 2 and supplied_days[0] != supplied_days[1]:
        return observed_day, status, "行情日期字段不一致"
    if observed_at is None and re.search(r"(?<![\d+-])\d{1,2}:\d{2}", stamp):
        return observed_day, status, "观察时间无效或缺少完整日期"
    if market and status == "盘中" and observed_at is None:
        return observed_day, status, "盘中报价须记录有日期的观察时间"

    cutoff_day = valid_iso_date(cutoff[:10])
    cutoff_at = quote_timestamp(cutoff, cutoff_day)
    if market and observed_at is not None and not declared_day:
        observed_day = observed_at.astimezone(ZoneInfo(CASH_QUOTE_SESSIONS[market][0])).date().isoformat()
    if (cutoff_day and observed_day > cutoff_day) or (observed_at and cutoff_at and observed_at > cutoff_at):
        return observed_day, status, "行情晚于本刊截点"
    if market and observed_day and cutoff_at:
        day = date.fromisoformat(observed_day)
        if day.weekday() >= 5 or _session_types(observed_day, market, calendar_overrides) & CLOSED_SESSION_TYPES:
            return observed_day, status, "该日无此市场的现金交易"
        check_at = observed_at or cutoff_at
        if status == "午盘" and market in MORNING_CLOSES:
            zone = ZoneInfo(CASH_QUOTE_SESSIONS[market][0])
            if check_at < datetime.combine(day, MORNING_CLOSES[market], zone):
                return observed_day, status, "午盘收盘晚于记录时点或本刊截点"
        elif status in {"官收", "收盘参考"} or (observed_at is None and status in {"盘口待核", "沿用报价"}):
            if not closing_quote_available(observed_day, market, check_at.isoformat(), calendar_overrides,
                                           close_delay_minutes=close_delay_minutes,
                                           observed_closing_time=observed_at is not None and status == "官收"):
                return observed_day, status, "日终收盘晚于记录时点或本刊截点"
    return observed_day, status, None
