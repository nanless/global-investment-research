"""Numeric chart values shared by the Markdown linter and SVG renderer."""

from __future__ import annotations

import json
import math
import re


_NUMBER = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+(?:\.\d*)?|\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?%?")


def load_gold_json(raw: str) -> object:
    """Reject duplicates and unrepresentable numbers in published gold inputs."""
    def object_from_pairs(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"重复 JSON 键 {key!r}")
            result[key] = value
        return result

    def finite_number(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            raise ValueError(f"非有限 JSON 数值 {token!r}")
        return value

    return json.loads(raw, object_pairs_hook=object_from_pairs, parse_float=finite_number, parse_constant=finite_number)


def chart_number(value: object) -> float:
    if isinstance(value, str):
        value = value.strip().replace("−", "-").replace("–", "-")
        if _NUMBER.fullmatch(value) is None:
            raise ValueError("须为有限数值")
        value = value.removesuffix("%").replace(",", "")
    elif type(value) not in (int, float):
        raise ValueError("须为有限数值")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("数值超出范围") from exc
    if not math.isfinite(number):
        raise ValueError("须为有限数值")
    return number


def _numeric_fields(data: dict, fields: tuple[str, ...], path: str) -> dict:
    result = data.copy()
    for field in fields:
        if field in result:
            try:
                result[field] = chart_number(result[field])
            except ValueError as exc:
                raise ValueError(f"{path}.{field} {exc}") from exc
    return result


def normalize_chart(kind: str, config: dict) -> dict:
    """Validate and normalize values consumed by a chart without changing the original directive."""
    cfg = config.copy()
    if kind == "DAILY_CHART_TIMELINE":
        cfg = _numeric_fields(cfg, ("y_min", "y_max"), kind)
        if "y_min" in cfg and "y_max" in cfg and cfg["y_min"] >= cfg["y_max"]:
            raise ValueError(f"{kind}.y_min 须小于 y_max")
        ticks = cfg.get("y_ticks", [])
        if not isinstance(ticks, list):
            raise ValueError(f"{kind}.y_ticks 须为数组")
        cfg["y_ticks"] = [chart_number(value) for value in ticks]
        rows = (
            ("points", ("val", "dx", "dy"), "val"),
            ("ref_lines", ("val", "x", "dy"), "val"),
            ("highlight_zones", ("start_idx", "end_idx"), None),
        )
    elif kind == "DAILY_CHART_SWITCH":
        rows = (("gauges", ("pct", "threshold_pct"), "pct"),)
    elif kind == "DAILY_CHART_CROSS":
        cfg = _numeric_fields(cfg, ("linear_cap_pct",), kind)
        if "linear_cap_pct" in cfg and cfg["linear_cap_pct"] <= 0:
            raise ValueError(f"{kind}.linear_cap_pct 须大于 0")
        rows = (("items", ("pct",), "pct"), ("reverse_items", (), None))
    else:
        return cfg

    for name, fields, required in rows:
        entries = cfg.get(name, [])
        if not isinstance(entries, list):
            raise ValueError(f"{kind}.{name} 须为数组")
        normalized = []
        for index, entry in enumerate(entries, 1):
            path = f"{kind}.{name}[{index}]"
            if not isinstance(entry, dict):
                raise ValueError(f"{path} 须为对象")
            if required is not None and required not in entry:
                raise ValueError(f"{path} 缺少 {required}")
            entry = _numeric_fields(entry, fields, path)
            if name == "highlight_zones" and any(not entry[key].is_integer() for key in fields if key in entry):
                raise ValueError(f"{path} 的区间索引须为整数")
            if name == "gauges" and any(not 0 <= entry[key] <= 100 for key in fields if key in entry):
                raise ValueError(f"{path} 的百分值须在 0 至 100 之间")
            normalized.append(entry)
        cfg[name] = normalized
    return cfg
