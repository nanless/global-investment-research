"""HTTPS citation checks shared by publishing, editorial lint and the portal."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit


def is_https_source(value: object, *, published_source: bool = False, direct: bool = False) -> bool:
    if not isinstance(value, str) or not value or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 or char == "\\" for char in value
    ) or re.search(r"%(?![0-9a-fA-F]{2})", value):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https" or parsed.username is not None or port == 0
        or "." not in host or not any(char.isalpha() for char in host)
        or any(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is None for label in host.split("."))
        or (direct and not (parsed.path.strip("/") or parsed.query))
    ):
        return False
    if not published_source:
        return True
    return (
        port in (None, 443)
        and not host.endswith((".invalid", ".example", ".test", ".localhost", ".local", ".internal"))
        and re.search(r"(?:^|\.)example\.(?:com|net|org)$", host) is None
    )


def is_sse_daily_quote(value: object, code: object) -> bool:
    """Match a single row on the official Shanghai daily quote feed."""
    if not isinstance(code, str) or re.fullmatch(r"6[0-9]{5}", code) is None:
        return False
    if not is_https_source(value, direct=True):
        return False
    url = urlsplit(value)
    if (
        url.hostname != "yunhq.sse.com.cn" or url.port != 32042
        or url.path != f"/v1/sh1/dayk/{code}" or url.fragment
    ):
        return False
    query = parse_qs(url.query, keep_blank_values=True)
    if query.keys() != {"select", "begin", "end"} or any(len(values) != 1 for values in query.values()):
        return False
    begin, end = query["begin"][0], query["end"][0]
    return (
        query["select"][0] in {"date,close", "date,open,high,low,close,volume,amount"}
        and re.fullmatch(r"[0-9]{1,6}", begin) is not None
        and re.fullmatch(r"[0-9]{1,6}", end) is not None
        and int(end) == int(begin) + 1
    )


def policy_extra_source_error(brief: dict) -> str | None:
    if "source_urls" not in brief:
        return None
    sources = brief["source_urls"]
    if not isinstance(sources, list) or not sources or not all(
        is_https_source(url, published_source=True, direct=True) for url in sources
    ):
        return "invalid"
    if brief.get("source_url") in sources or len(set(sources)) != len(sources):
        return "duplicate"
    return None


def policy_brief_links(brief: dict) -> list[str]:
    """Return usable links for a brief, suppressing malformed or repeated entries."""
    extra = brief.get("source_urls")
    main = brief.get("source_url")
    links = [main] if is_https_source(main, published_source=True) else []
    if isinstance(extra, list):
        links.extend(url for url in extra if is_https_source(url, published_source=True, direct=True))
    return list(dict.fromkeys(links))
