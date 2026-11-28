"""Validation for ordinary cash dividends used in the A/H comparison."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
import re
from urllib.parse import parse_qs, urlsplit

if __package__:
    from .source_links import is_https_source, is_sse_daily_quote
else:
    from source_links import is_https_source, is_sse_daily_quote


DISCLOSURE_DOMAINS = (
    "cninfo.com.cn", "sse.com.cn", "szse.cn", "hkexnews.hk", "hkex.com.hk", "sec.gov",
    "chinamobileltd.com", "cmbchina.com",
)


@dataclass(frozen=True)
class CashDividend:
    amount: float | None
    start: date
    end: date
    published: date
    sources: tuple[str, ...]
    southbound_cny: bool
    unavailable_status: str | None


def _date(value: object, field: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError(f"{field} 须为 YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} 不是有效日期") from exc


def _is_disclosure_url(value: object) -> bool:
    if not is_https_source(value, published_source=True, direct=True):
        return False
    url = urlsplit(value)
    host = url.hostname
    if url.path.lower().strip("/") in {"index.html", "index.htm", "home"}:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in DISCLOSURE_DOMAINS)


def _parse_side(item: object, side: str) -> CashDividend:
    if not isinstance(item, dict):
        raise ValueError(f"{side} 须为对象")
    basis = item.get("cash_basis")
    southbound = side == "h" and basis == "southbound_cny"
    if basis is not None and not southbound:
        raise ValueError(f"{side}.cash_basis 须省略或在 H 侧填 southbound_cny")
    start = _date(item.get("period_start"), f"{side}.period_start")
    end = _date(item.get("period_end"), f"{side}.period_end")
    published = _date(item.get("published_date"), f"{side}.published_date")
    if not start <= end <= published:
        raise ValueError(f"{side} 须满足期间开始日 ≤ 结束日 ≤ 公告日")
    status = item.get("status")
    if status is not None and (side != "h" or status not in ("listed_after_record_date", "excluded_from_distribution")):
        raise ValueError(f"{side}.status 须省略或填写有效的 H 股不参与分派原因")
    if status is not None:
        if any(field in item for field in ("ordinary_cash_per_share", "currency", "cash_basis")):
            raise ValueError("不参与分派的 H 股不应填写本期股息金额或币种")
        if status == "listed_after_record_date":
            listed = _date(item.get("listed_date"), "h.listed_date")
            record = _date(item.get("last_record_date"), "h.last_record_date")
            if not end <= record < listed <= published:
                raise ValueError("登记日后上市的 H 股须满足期间结束日 ≤ 最后登记日 < 上市日 ≤ 公告日")
        amount = None
    else:
        currency = "CNY" if side == "a" or southbound else "HKD"
        if item.get("currency") != currency:
            raise ValueError(f"{side}.currency 须为 {currency}")
        raw_amount = item.get("ordinary_cash_per_share")
        try:
            amount = float(raw_amount) if type(raw_amount) in (int, float) else -1
        except OverflowError:
            amount = -1
        if not isfinite(amount) or amount < 0:
            raise ValueError(f"{side}.ordinary_cash_per_share 须为有限非负数")

    if "source_url" in item and "source_urls" in item:
        raise ValueError(f"{side} 只能填写 source_url 或 source_urls 中的一种")
    sources = item.get("source_urls", [item.get("source_url")])
    if not isinstance(sources, list) or not sources or not all(_is_disclosure_url(url) for url in sources):
        raise ValueError(f"{side} 须提供交易所、监管披露平台或项目核准发行人的 HTTPS 公告链接")
    normalized_sources = tuple("https" + url[url.index(":"):] for url in sources)
    if len(set(normalized_sources)) != len(normalized_sources):
        raise ValueError(f"{side} 的公告链接重复")
    return CashDividend(amount, start, end, published, normalized_sources, southbound, status)


def parse_pair(data: object) -> tuple[CashDividend, CashDividend]:
    if not isinstance(data, dict) or set(data) != {"a", "h"}:
        raise ValueError("cash_dividends 须同时提供 a 与 h")
    a = _parse_side(data["a"], "a")
    h = _parse_side(data["h"], "h")
    if (a.start, a.end) != (h.start, h.end):
        raise ValueError("A 与 H 两侧普通现金股息须使用相同的统计期间")
    return a, h


def parse_exchange_closes(record: dict, cutoff: date | None) -> dict[str, dict]:
    rows = record.get("exchange_closes", {})
    if not isinstance(rows, dict) or not rows.keys() <= {"a", "h"}:
        raise ValueError("exchange_closes 须为 a、h 之一或两侧的报价对象")
    result = {}
    for side, row in rows.items():
        currency = "CNY" if side == "a" else "HKD"
        if (
            not isinstance(row, dict) or not isinstance(row.get("code"), str)
            or row["code"] != record.get(side) or row.get("currency") != currency
        ):
            raise ValueError(f"exchange_closes.{side} 的证券代码或币种不匹配")
        as_of = _date(row.get("date"), f"exchange_closes.{side}.date")
        if cutoff is not None and as_of > cutoff:
            raise ValueError(f"exchange_closes.{side} 的交易日晚于数据截点")
        value, source = row.get("close"), row.get("source_url")
        if type(value) not in (int, float) or value <= 0 or value > 1e9 or not isfinite(value):
            raise ValueError(f"exchange_closes.{side} 须填写有限正数收盘价")
        if not is_https_source(source, published_source=True, direct=True):
            raise ValueError(f"exchange_closes.{side} 须提供交易所公开行情链接")
        url = urlsplit(source)
        query = parse_qs(url.query)
        if side == "h":
            matching_source = url.hostname == "www.hkex.com.hk" and url.path == f"/eng/stat/smstat/dayquot/d{as_of:%y%m%d}e.htm"
        elif row["code"].startswith("6"):
            matching_source = (
                url.hostname == "query.sse.com.cn" and url.path == "/commonQuery.do"
                and query.get("sqlId") == ["COMMON_SSE_CP_GPJCTPZ_GPLB_CJGK_MRGK_C"]
                and query.get("SEC_CODE") == [row["code"]] and query.get("TX_DATE") == [f"{as_of:%Y%m%d}"]
            )
        else:
            begin = query.get("txtBeginDate", [])
            end = query.get("txtEndDate", [])
            matching_source = (
                row["code"].startswith(("0", "3")) and url.hostname == "www.szse.cn" and url.path == "/api/report/ShowReport/data"
                and query.get("CATALOGID") == ["1815_stock_snapshot"] and query.get("txtDMorJC") == [row["code"]]
                and len(begin) == len(end) == 1
                and _date(begin[0], f"exchange_closes.{side}.txtBeginDate") <= as_of
                <= _date(end[0], f"exchange_closes.{side}.txtEndDate")
            )
        if not matching_source:
            raise ValueError(f"exchange_closes.{side} 行情链接与交易所、代码或交易日不对应")
        replay = row.get("replay_url")
        if replay is not None and (side != "a" or not is_sse_daily_quote(replay, row["code"])):
            raise ValueError(f"exchange_closes.{side} 单行复查链接与证券代码不对应")
        result[side] = {
            "latest_close": value, "latest_date": as_of.isoformat(), "currency": currency,
            "provider": "exchange", "source_url": source, "replay_url": replay, "stale": False,
        }
    return result
