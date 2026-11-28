"""Validate claim-level citations stored alongside ETF and stock research."""

from __future__ import annotations

from datetime import date
import json
from math import isfinite

if __package__:
    from .source_links import is_https_source, is_sse_daily_quote
else:
    from source_links import is_https_source, is_sse_daily_quote


STOCK_FIELDS = frozenset({
    "baseline_note", "moat", "financials", "valuation_anchor", "shareholder_flow",
    "catalysts", "bear_case", "action_etf",
})
ETF_FIELDS = frozenset({
    "name", "channel", "category", "tracking_index", "aum", "fee_total_pct",
    "liquidity", "yield_or_pe", "top_holdings", "premium_note", "tax_and_rules",
    "thesis_deep", "risk_boundary", "action_role", "otc_feeder",
})


def load_research_json(text: str):
    """Refuse ambiguous or non-finite input before validating research records."""
    def object_from_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate JSON field {key!r}")
            value[key] = item
        return value

    def finite_decimal(token: str) -> float:
        value = float(token)
        if not isfinite(value):
            raise ValueError(f"Non-finite JSON value {token!r}")
        return value

    return json.loads(text, object_pairs_hook=object_from_pairs, parse_float=finite_decimal, parse_constant=finite_decimal)


def inventory_evidence(record: dict, fields: frozenset[str], cutoff: date | None = None) -> list[dict]:
    entries = record.get("evidence", [])
    if not isinstance(entries, list):
        raise ValueError("evidence must be an array")
    seen = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"field", "source_url", "as_of", "note"}:
            raise ValueError(f"evidence[{index}] requires field, source_url, as_of and note")
        field, url, observed, note = (entry[key] for key in ("field", "source_url", "as_of", "note"))
        if not isinstance(field, str) or field not in fields or not record.get(field):
            raise ValueError(f"evidence[{index}] must reference a populated research field")
        official_sse_quote = (
            field == "baseline_note" and record.get("market") == "a-share"
            and is_sse_daily_quote(url, record.get("code"))
        )
        if not official_sse_quote and not is_https_source(url, published_source=True, direct=True):
            raise ValueError(f"evidence[{index}].source_url must identify a specific HTTPS document")
        try:
            parsed = date.fromisoformat(observed)
        except (TypeError, ValueError):
            raise ValueError(f"evidence[{index}].as_of must use YYYY-MM-DD") from None
        if observed != parsed.isoformat() or (cutoff is not None and parsed > cutoff):
            raise ValueError(f"evidence[{index}].as_of is invalid or later than the edition cutoff")
        if not isinstance(note, str) or len(note.splitlines()) != 1 or sum(char.isalnum() for char in note) < 8:
            raise ValueError(f"evidence[{index}].note must identify the passage or data verified")
        key = (field, url, observed)
        if key in seen:
            raise ValueError(f"evidence[{index}] duplicates a citation")
        seen.add(key)
    return entries


def retain_inventory_evidence(before: dict, after: dict, patch: dict) -> None:
    """When a patch edits a claim, require its citation to be supplied again."""
    entries = before.get("evidence")
    if "evidence" not in patch and isinstance(entries, list):
        after["evidence"] = [
            entry for entry in entries
            if not isinstance(entry, dict) or not isinstance((field := entry.get("field")), str)
            or before.get(field) == after.get(field)
        ]
