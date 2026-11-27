#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-dependency production daily K-line (OHLCV) fetcher for Global Investment Research.

Fetches historical daily OHLCV bars for ~454+ instruments across:
  - Core macro & index benchmarks (`core.json`): A/HK/US indices, gold/metals,
    energy, FX, US Treasury yields, and crypto
  - All 174 ETFs across 6 trading channels (`etfs_onshore.json`,
    `etfs_crossborder.json`, `etfs_offshore.json`)
  - All 231 institutional deep-dossier stocks (`stocks_a.json`, `stocks_hk.json`,
    `stocks_us.json`)

Strictly uses Python 3 standard library (`urllib.request`, `concurrent.futures`,
`json`, `csv`, `threading`) with live-verified providers, per-host concurrency
limits, jittered retry backoff, stale-while-error cache preservation, strict
OHLCV sanity filtering, and atomic 0o644 JSON writes.

Usage:
  python3 scripts/fetch_kline_data.py [--scope {all,core,etfs,stocks}]
                                      [--bars 150]
                                      [--edition-id 2026-11-27_0730]
                                      [--out-dir equity/state/klines]
                                      [--workers 12]
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import io
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import tempfile
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "equity" / "state" / "klines"
MARKET_STATE_PATH = REPO_ROOT / "equity" / "state" / "market_state.json"
ETF_UNIVERSE_PATH = REPO_ROOT / "equity" / "state" / "etf_universe.json"
DEEP_DOSSIERS_PATH = REPO_ROOT / "equity" / "state" / "deep_dossiers.json"
US_SUFFIX_CACHE_PATH = REPO_ROOT / "equity" / "state" / "kline_us_suffix_cache.json"

CST = timezone(timedelta(hours=8))
SCHEMA_VERSION = "1.0"
DEFAULT_BARS = 150
MIN_BARS = 60
MAX_BARS = 240
DEFAULT_WORKERS = 12
HTTP_TIMEOUT_SEC = 12
HTTP_RETRIES = 2

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
SINA_REFERER = "https://finance.sina.com.cn/"

SH_INDEX_CODES = frozenset({
    "000001",
    "000300",
    "000510",
    "000016",
    "000688",
    "000680",
    "000905",
    "000852",
    "000922",
    "000832",
})
SZ_INDEX_CODES = frozenset({"399001", "399006"})
US_ALLOWED_SUFFIXES = ("OQ", "N", "AM")
DATE_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

FT_UCITS_XID_MAP: dict[str, str] = {
    "IB01": "518909489",
    "VUAA": "534460756",
    "VWRA": "544896897",
    "CNDX": "26390447",
    "IGLN": "33139564",
    "CSPX": "26390464",
    "SWDA": "21061415",
    "XDEW": "77827242",
    "EQQQ": "86266974",
    "IUIT": "93233034",
}

JUSTETF_ISIN_MAP: dict[str, str] = {
    "IB01": "IE00BGSF1X88",
    "VUAA": "IE00BFMXXD54",
    "VWRA": "IE00BK5BQT80",
    "CNDX": "IE00B53SZB19",
    "IGLN": "IE00B4ND3602",
    "CSPX": "IE00B5BMR087",
    "SWDA": "IE00B4L5Y983",
    "XDEW": "IE00BLNMYC90",
    "EQQQ": "IE0032077012",
    "IUIT": "IE00B3WJKG14",
}

ETF_SHARD_BY_CHANNEL: dict[str, str] = {
    "境内场内": "etfs_onshore",
    "境内场外": "etfs_onshore",
    "境内QDII": "etfs_crossborder",
    "境内非QDII港股通": "etfs_crossborder",
    "离岸港交所": "etfs_offshore",
    "离岸美股": "etfs_offshore",
    "爱尔兰UCITS": "etfs_offshore",
}

ETF_CURRENCY_UNIT_BY_CHANNEL: dict[str, tuple[str, str]] = {
    "境内场内": ("CNY", "元"),
    "境内场外": ("CNY", "元"),
    "境内QDII": ("CNY", "元"),
    "境内非QDII港股通": ("CNY", "元"),
    "离岸港交所": ("HKD", "港元"),
    "离岸美股": ("USD", "美元"),
    "爱尔兰UCITS": ("USD", "美元"),
}

STOCK_META_BY_MARKET: dict[str, tuple[str, str, str, str]] = {
    # market_slug -> (shard, market_label, currency, unit)
    "a-share": ("stocks_a", "A股", "CNY", "元"),
    "hk-stock": ("stocks_hk", "港股", "HKD", "港元"),
    "us-stock": ("stocks_us", "美股", "USD", "美元"),
}

ALL_SHARDS_ORDER: tuple[str, ...] = (
    "core",
    "etfs_onshore",
    "etfs_crossborder",
    "etfs_offshore",
    "stocks_a",
    "stocks_hk",
    "stocks_us",
)

SCOPE_SHARDS: dict[str, tuple[str, ...]] = {
    "all": ALL_SHARDS_ORDER,
    "core": ("core",),
    "etfs": ("etfs_onshore", "etfs_crossborder", "etfs_offshore"),
    "stocks": ("stocks_a", "stocks_hk", "stocks_us"),
}


@dataclass(frozen=True)
class InstrumentSpec:
    id: str
    code: str
    name: str
    group: str
    market: str
    currency: str
    unit: str
    shard: str
    kind: str  # routing kind
    provider_symbol: str = ""
    fallback_symbol: str = ""
    market_label: str = ""
    category: str = ""
    dossier_key: str = ""
    optional_min_bars: int = 0  # if > 0 and fetched bars < this, omit cleanly
    force_no_volume: bool = False
    decimals_override: int | None = None


def build_core_specs() -> list[InstrumentSpec]:
    """Exact core benchmark specifications in canonical priority order."""
    specs: list[InstrumentSpec] = [
        # --- A-share Indices (12) ---
        InstrumentSpec("idx_sh000001", "000001", "上证指数", "a_index", "A股", "CNY", "点", "core", "cn_index", "sh000001"),
        InstrumentSpec("idx_sh000300", "000300", "沪深300", "a_index", "A股", "CNY", "点", "core", "cn_index", "sh000300"),
        InstrumentSpec("idx_sz399001", "399001", "深证成指", "a_index", "A股", "CNY", "点", "core", "cn_index", "sz399001"),
        InstrumentSpec("idx_sh000510", "000510", "中证A500", "a_index", "A股", "CNY", "点", "core", "cn_index", "sh000510"),
        InstrumentSpec("idx_sh000016", "000016", "上证50", "a_index", "A股", "CNY", "点", "core", "cn_index", "sh000016"),
        InstrumentSpec("idx_sz399006", "399006", "创业板指", "a_index", "A股", "CNY", "点", "core", "cn_index", "sz399006"),
        InstrumentSpec("idx_sh000688", "000688", "科创50", "a_index", "A股", "CNY", "点", "core", "cn_index", "sh000688"),
        InstrumentSpec("idx_sh000905", "000905", "中证500", "a_index", "A股", "CNY", "点", "core", "cn_index", "sh000905"),
        InstrumentSpec("idx_sh000852", "000852", "中证1000", "a_index", "A股", "CNY", "点", "core", "cn_index", "sh000852"),
        InstrumentSpec("idx_sh000922", "000922", "中证红利", "a_index", "A股", "CNY", "点", "core", "cn_index", "sh000922"),
        InstrumentSpec("idx_bj899050", "899050", "北证50", "a_index", "A股", "CNY", "点", "core", "bj_sina", "bj899050"),
        InstrumentSpec("idx_sh000832", "000832", "中证转债", "a_index", "A股", "CNY", "点", "core", "cn_index", "sh000832"),
        # --- HK Indices (3 + 1 optional) ---
        InstrumentSpec("idx_hkHSI", "HSI", "恒生指数", "hk_index", "港股", "HKD", "点", "core", "hk_index", "hkHSI"),
        InstrumentSpec("idx_hkHSTECH", "HSTECH", "恒生科技", "hk_index", "港股", "HKD", "点", "core", "hk_index", "hkHSTECH"),
        InstrumentSpec("idx_hkHSCEI", "HSCEI", "恒生国企", "hk_index", "港股", "HKD", "点", "core", "hk_index", "hkHSCEI"),
        InstrumentSpec("idx_hkHSCI", "HSCI", "恒生综合", "hk_index", "港股", "HKD", "点", "core", "hk_index", "hkHSCI", optional_min_bars=10),
        # --- US Indices (8) ---
        InstrumentSpec("idx_SPX", "SPX", "标普500", "us_index", "美股", "USD", "点", "core", "us_index", "us.INX", ".inx"),
        InstrumentSpec("idx_IXIC", "IXIC", "纳斯达克综合", "us_index", "美股", "USD", "点", "core", "us_index", "us.IXIC", ".ixic"),
        InstrumentSpec("idx_NDX", "NDX", "纳斯达克100", "us_index", "美股", "USD", "点", "core", "us_index", "us.NDX", ".ndx"),
        InstrumentSpec("idx_DJI", "DJI", "道琼斯工业", "us_index", "美股", "USD", "点", "core", "us_index", "us.DJI", ".dji"),
        InstrumentSpec("idx_RUT", "IWM", "罗素2000·IWM", "us_index", "美股", "USD", "点", "core", "us_index", "usIWM.AM", "iwm"),
        InstrumentSpec("idx_SPXEW", "RSP", "标普500等权·RSP", "us_index", "美股", "USD", "点", "core", "us_index", "usRSP.AM", "rsp"),
        InstrumentSpec("idx_SOX", "SOX", "费城半导体", "us_index", "美股", "USD", "点", "core", "us_sina_only", ".sox"),
        InstrumentSpec("idx_VIX", "VIX", "VIX恐慌指数", "us_index", "美股", "USD", "点", "core", "cboe_vix", "VIX", force_no_volume=True),
        # --- Gold & Metals (11 canonical + Ag(T+D)) ---
        InstrumentSpec("cmd_XAU", "XAU", "伦敦现货黄金", "gold_metal", "黄金与贵金属", "USD", "美元/盎司", "core", "sina_global_futures", "XAU"),
        InstrumentSpec("cmd_GC", "GC", "COMEX黄金主力", "gold_metal", "黄金与贵金属", "USD", "美元/盎司", "core", "sina_global_futures", "GC"),
        InstrumentSpec("cmd_AU0", "AU0", "沪金主力连续", "gold_metal", "黄金与贵金属", "CNY", "元/克", "core", "sina_inner_futures", "AU0"),
        InstrumentSpec("cmd_Au9999", "Au99.99", "上金所Au99.99", "gold_metal", "黄金与贵金属", "CNY", "元/克", "core", "sge_daily", "Au99.99", force_no_volume=True),
        InstrumentSpec("cmd_AuTD", "Au(T+D)", "上金所Au(T+D)", "gold_metal", "黄金与贵金属", "CNY", "元/克", "core", "sge_daily", "Au(T+D)", force_no_volume=True),
        InstrumentSpec("cmd_XAG", "XAG", "伦敦现货白银", "gold_metal", "黄金与贵金属", "USD", "美元/盎司", "core", "sina_global_futures", "XAG"),
        InstrumentSpec("cmd_SI", "SI", "COMEX白银", "gold_metal", "黄金与贵金属", "USD", "美元/盎司", "core", "sina_global_futures", "SI"),
        InstrumentSpec("cmd_AG0", "AG0", "沪银主力连续", "gold_metal", "黄金与贵金属", "CNY", "元/千克", "core", "sina_inner_futures", "AG0"),
        InstrumentSpec("cmd_HG", "HG", "COMEX铜", "gold_metal", "黄金与贵金属", "USD", "美元/磅", "core", "sina_global_futures", "HG"),
        InstrumentSpec("cmd_CU0", "CU0", "沪铜主力连续", "gold_metal", "黄金与贵金属", "CNY", "元/吨", "core", "sina_inner_futures", "CU0"),
        InstrumentSpec("cmd_XPT", "XPT", "现货铂金", "gold_metal", "黄金与贵金属", "USD", "美元/盎司", "core", "sina_global_futures", "XPT"),
        InstrumentSpec("cmd_AgTD", "Ag(T+D)", "上金所Ag(T+D)", "gold_metal", "黄金与贵金属", "CNY", "元/千克", "core", "sge_daily", "Ag(T+D)", force_no_volume=True),
        # --- Energy, FX, Rates & Crypto (14) ---
        InstrumentSpec("cmd_OIL", "OIL", "布伦特原油", "macro_cmd", "宏观商品与汇率", "USD", "美元/桶", "core", "sina_global_futures", "OIL"),
        InstrumentSpec("cmd_CL", "CL", "WTI原油", "macro_cmd", "宏观商品与汇率", "USD", "美元/桶", "core", "sina_global_futures", "CL"),
        InstrumentSpec("cmd_SC0", "SC0", "上海原油主力", "macro_cmd", "宏观商品与汇率", "CNY", "元/桶", "core", "sina_inner_futures", "SC0"),
        InstrumentSpec("cmd_NG", "NG", "NYMEX天然气", "macro_cmd", "宏观商品与汇率", "USD", "美元/百万英热", "core", "sina_global_futures", "NG"),
        InstrumentSpec("fx_DXY", "DXY", "美元指数", "macro_cmd", "宏观商品与汇率", "USD", "点", "core", "sina_fx", "DINIW", force_no_volume=True, decimals_override=4),
        InstrumentSpec("fx_USDCNH", "USDCNH", "离岸人民币", "macro_cmd", "宏观商品与汇率", "CNH", "汇率", "core", "sina_fx", "fx_susdcnh", force_no_volume=True, decimals_override=4),
        InstrumentSpec("fx_USDCNY", "USDCNY", "在岸人民币", "macro_cmd", "宏观商品与汇率", "CNY", "汇率", "core", "sina_fx", "fx_susdcny", force_no_volume=True, decimals_override=4),
        InstrumentSpec("fx_USDJPY", "USDJPY", "美元兑日元", "macro_cmd", "宏观商品与汇率", "JPY", "汇率", "core", "sina_fx", "fx_susdjpy", force_no_volume=True, decimals_override=4),
        InstrumentSpec("rate_US10Y", "US10Y", "美债10Y收益率", "macro_cmd", "宏观商品与汇率", "%", "%", "core", "treasury_nominal", "10 Yr", force_no_volume=True, decimals_override=2),
        InstrumentSpec("rate_US2Y", "US2Y", "美债2Y收益率", "macro_cmd", "宏观商品与汇率", "%", "%", "core", "treasury_nominal", "2 Yr", force_no_volume=True, decimals_override=2),
        InstrumentSpec("rate_US30Y", "US30Y", "美债30Y收益率", "macro_cmd", "宏观商品与汇率", "%", "%", "core", "treasury_nominal", "30 Yr", force_no_volume=True, decimals_override=2),
        InstrumentSpec("rate_DFII10", "DFII10", "10Y TIPS实际利率", "macro_cmd", "宏观商品与汇率", "%", "%", "core", "treasury_real", "10 YR", force_no_volume=True, decimals_override=2),
        InstrumentSpec("crypto_BTC", "BTC-USD", "比特币", "macro_cmd", "宏观商品与汇率", "USD", "美元", "core", "coinbase_crypto", "BTC-USD"),
        InstrumentSpec("crypto_ETH", "ETH-USD", "以太坊", "macro_cmd", "宏观商品与汇率", "USD", "美元", "core", "coinbase_crypto", "ETH-USD"),
    ]
    return specs


# ---------------------------------------------------------------------------
# Code Routing Helpers
# ---------------------------------------------------------------------------

def route_cn_symbol(code: str, *, is_index: bool = False) -> str:
    """Route a 6-digit China A-share stock, ETF, LOF, or index code to sh/sz/bj prefix."""
    cleaned = code.strip().upper()
    if cleaned.endswith((".SH", ".SS")):
        return f"sh{cleaned[:-3]}"
    if cleaned.endswith(".SZ"):
        return f"sz{cleaned[:-3]}"
    if cleaned.endswith(".BJ"):
        return f"bj{cleaned[:-3]}"
    low = cleaned.lower()
    if low.startswith(("sh", "sz", "bj")):
        return low
    if is_index:
        if cleaned in SH_INDEX_CODES:
            return f"sh{cleaned}"
        if cleaned in SZ_INDEX_CODES or cleaned.startswith("399"):
            return f"sz{cleaned}"
        if cleaned.startswith(("899", "8", "9", "4")):
            return f"bj{cleaned}"
        return f"sh{cleaned}"
    if cleaned.startswith(("5", "6")):
        return f"sh{cleaned}"
    if cleaned.startswith(("0", "1", "3")):
        return f"sz{cleaned}"
    if cleaned.startswith(("8", "9", "4")):
        return f"bj{cleaned}"
    return f"sh{cleaned}"


def route_hk_symbol(code: str, *, is_index: bool = False) -> str:
    """Route an HK ticker or index code to Tencent hk* symbol."""
    cleaned = code.strip()
    if cleaned.lower().startswith("hk"):
        rest = cleaned[2:]
    else:
        rest = cleaned
    if rest.upper().endswith(".HK"):
        rest = rest[:-3]
    if is_index or not rest.isdigit():
        return f"hk{rest.upper()}"
    return f"hk{rest.zfill(5)}"


def strip_lse_suffix(code: str) -> str:
    """Normalize Irish UCITS LSE ticker (e.g. VUAA.L -> VUAA)."""
    cleaned = code.strip().upper()
    if cleaned.endswith(".L"):
        return cleaned[:-2]
    return cleaned


def load_etf_specs(etf_path: Path = ETF_UNIVERSE_PATH) -> list[InstrumentSpec]:
    """Load all ETF instruments from equity/state/etf_universe.json."""
    data = json.loads(etf_path.read_text(encoding="utf-8"))
    specs: list[InstrumentSpec] = []
    for item in data.get("etfs", []):
        code = str(item["code"]).strip()
        name = str(item["name"]).strip()
        channel = str(item["channel"]).strip()
        market = str(item.get("market", "")).strip()
        market_label = str(item.get("market_label", "")).strip()
        category = str(item.get("category", "")).strip()
        shard = ETF_SHARD_BY_CHANNEL.get(channel, "etfs_onshore")
        currency, unit = ETF_CURRENCY_UNIT_BY_CHANNEL.get(channel, ("CNY", "元"))
        inst_id = f"etf_{code}"

        if channel in ("境内场内", "境内场外", "境内QDII", "境内非QDII港股通"):
            cn_sym = route_cn_symbol(code, is_index=False)
            kind = "bj_sina" if cn_sym.startswith("bj") else "cn_equity"
            specs.append(
                InstrumentSpec(
                    id=inst_id,
                    code=code,
                    name=name,
                    group=channel,
                    market=market,
                    currency=currency,
                    unit=unit,
                    shard=shard,
                    kind=kind,
                    provider_symbol=cn_sym,
                    market_label=market_label,
                    category=category,
                )
            )
        elif channel == "离岸港交所":
            hk_sym = route_hk_symbol(code, is_index=False)
            specs.append(
                InstrumentSpec(
                    id=inst_id,
                    code=code,
                    name=name,
                    group=channel,
                    market=market,
                    currency=currency,
                    unit=unit,
                    shard=shard,
                    kind="hk_equity",
                    provider_symbol=hk_sym,
                    market_label=market_label,
                    category=category,
                )
            )
        elif channel == "离岸美股":
            specs.append(
                InstrumentSpec(
                    id=inst_id,
                    code=code,
                    name=name,
                    group=channel,
                    market=market,
                    currency=currency,
                    unit=unit,
                    shard=shard,
                    kind="us_equity",
                    provider_symbol=code.upper(),
                    fallback_symbol=code.lower(),
                    market_label=market_label,
                    category=category,
                )
            )
        elif channel == "爱尔兰UCITS":
            base = strip_lse_suffix(code)
            specs.append(
                InstrumentSpec(
                    id=inst_id,
                    code=code,
                    name=name,
                    group=channel,
                    market=market,
                    currency=currency,
                    unit=unit,
                    shard=shard,
                    kind="ucits_ft",
                    provider_symbol=base,
                    fallback_symbol=JUSTETF_ISIN_MAP.get(base, ""),
                    market_label=market_label,
                    category=category,
                    force_no_volume=True,
                )
            )
        else:
            cn_sym = route_cn_symbol(code, is_index=False)
            specs.append(
                InstrumentSpec(
                    id=inst_id,
                    code=code,
                    name=name,
                    group=channel,
                    market=market,
                    currency=currency,
                    unit=unit,
                    shard=shard,
                    kind="cn_equity",
                    provider_symbol=cn_sym,
                    market_label=market_label,
                    category=category,
                )
            )
    return specs


def load_stock_specs(dossiers_path: Path = DEEP_DOSSIERS_PATH) -> list[InstrumentSpec]:
    """Load all deep-dossier stock instruments from equity/state/deep_dossiers.json."""
    data = json.loads(dossiers_path.read_text(encoding="utf-8"))
    dossiers = data.get("dossiers", {})
    specs: list[InstrumentSpec] = []
    for dossier_key, entry in dossiers.items():
        market_slug = str(entry.get("market", "")).strip()
        code = str(entry.get("code", "")).strip()
        if not code and ":" in dossier_key:
            code = dossier_key.split(":", 1)[1].strip()
        name = str(entry.get("name", code)).strip()
        shard, market_label, currency, unit = STOCK_META_BY_MARKET.get(
            market_slug, ("stocks_a", "A股", "CNY", "元")
        )
        inst_id = f"stk_{code}"

        if market_slug == "a-share":
            cn_sym = route_cn_symbol(code, is_index=False)
            kind = "bj_sina" if cn_sym.startswith("bj") else "cn_equity"
            prov_sym = cn_sym
            fb_sym = cn_sym
        elif market_slug == "hk-stock":
            kind = "hk_equity"
            prov_sym = route_hk_symbol(code, is_index=False)
            fb_sym = prov_sym
        else:
            kind = "us_equity"
            prov_sym = code.upper()
            fb_sym = code.lower()

        specs.append(
            InstrumentSpec(
                id=inst_id,
                code=code,
                name=name,
                group=market_slug,
                market=market_slug,
                currency=currency,
                unit=unit,
                shard=shard,
                kind=kind,
                provider_symbol=prov_sym,
                fallback_symbol=fb_sym,
                market_label=market_label,
                dossier_key=dossier_key,
            )
        )
    return specs


# ---------------------------------------------------------------------------
# OHLCV Sanity Filtering, Normalization & Rounding
# ---------------------------------------------------------------------------

def _to_float(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        f = float(val)
    else:
        s = str(val).strip().replace(",", "")
        if not s or s.upper() in ("N/A", "NA", "NULL", "NONE", "-", "--"):
            return None
        try:
            f = float(s)
        except ValueError:
            return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _round_price(val: float, decimals_override: int | None = None) -> float:
    if decimals_override is not None:
        return round(val, decimals_override)
    abs_v = abs(val)
    if abs_v < 20.0:
        return round(val, 4)
    if abs_v < 1000.0:
        return round(val, 3)
    return round(val, 2)


def _round_volume(val: float) -> int | float:
    if val <= 0:
        return 0
    if val >= 100.0:
        return int(round(val))
    rounded = round(val, 2)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def normalize_date_mmddyyyy(raw: str) -> str | None:
    """Convert MM/DD/YYYY (or YYYY-MM-DD) to ISO YYYY-MM-DD."""
    s = raw.strip().strip('"').strip("'")
    if not s:
        return None
    if DATE_ISO_RE.match(s):
        return s
    if "T" in s and DATE_ISO_RE.match(s[:10]):
        return s[:10]
    parts = s.split("/")
    if len(parts) == 3:
        m, d, y = parts
        if len(y) == 4 and m.isdigit() and d.isdigit():
            try:
                dt = datetime(int(y), int(m), int(d))
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return None
    return None


def sanitize_bars(
    raw_bars: list[list[Any]],
    *,
    bars_limit: int = DEFAULT_BARS,
    decimals_override: int | None = None,
    force_no_volume: bool = False,
) -> list[list[Any]]:
    """Validate, deduplicate by ISO date, sort ascending, round, and slice to last N bars.

    Each input bar must already be ordered as [date_iso, open, high, low, close, volume].
    Drops bars where close <= 0, open <= 0, high <= 0, low <= 0, raw high < low,
    invalid date, or NaN/Inf. Clamps slight intraday envelope anomalies where
    open/close lies outside [low, high] while raw high >= low.
    """
    by_date: dict[str, list[Any]] = {}
    for row in raw_bars:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        date_iso = normalize_date_mmddyyyy(str(row[0]))
        if not date_iso:
            continue
        o = _to_float(row[1])
        h = _to_float(row[2])
        l = _to_float(row[3])
        c = _to_float(row[4])
        v = 0.0 if force_no_volume else (_to_float(row[5]) if len(row) > 5 else 0.0)
        if o is None or h is None or l is None or c is None:
            continue
        if o <= 0 or h <= 0 or l <= 0 or c <= 0:
            continue
        if h < l:
            continue
        if v is None or v < 0:
            v = 0.0
        # Ensure strict candlestick envelope: low <= min(open, close) <= max(open, close) <= high
        h = max(h, o, c)
        l = min(l, o, c)
        by_date[date_iso] = [
            date_iso,
            _round_price(o, decimals_override),
            _round_price(h, decimals_override),
            _round_price(l, decimals_override),
            _round_price(c, decimals_override),
            0 if force_no_volume else _round_volume(v),
        ]

    ordered = [by_date[d] for d in sorted(by_date.keys())]
    if bars_limit > 0 and len(ordered) > bars_limit:
        ordered = ordered[-bars_limit:]
    return ordered


# ---------------------------------------------------------------------------
# Provider Response Parsers (Pure functions — 100% offline unit-testable!)
# ---------------------------------------------------------------------------

def _extract_jsonp_payload(text: str) -> str:
    """Strip leading comment/callback wrapper and trailing ');' from JSONP."""
    s = text.strip()
    # Remove leading /* ... */ comments if any
    while s.startswith("/*"):
        end_c = s.find("*/")
        if end_c == -1:
            break
        s = s[end_c + 2 :].strip()
    # Find callback( ... )
    lparen = s.find("(")
    rparen = s.rfind(")")
    if lparen != -1 and rparen > lparen:
        return s[lparen + 1 : rparen].strip()
    return s


def parse_tencent_kline(raw_text: str, symbol_key: str | None = None) -> list[list[Any]]:
    """Parse Tencent newfqkline / hkfqkline / usfqkline JSON response.

    CRITICAL COLUMN ORDER: Tencent raw row is [date, open, close, high, low, volume, ...].
    Reorders to [date, open, high, low, close, volume].
    """
    payload = json.loads(raw_text)
    if not isinstance(payload, dict) or payload.get("code") not in (0, "0", None):
        return []
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        return []
    entry = data.get(symbol_key) if symbol_key and symbol_key in data else next(iter(data.values()))
    if not isinstance(entry, dict):
        return []
    rows = entry.get("qfqday") or entry.get("day") or []
    if not isinstance(rows, list):
        return []
    out: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        date_s = str(row[0]).strip()
        o = row[1]
        c = row[2]
        h = row[3]
        l = row[4]
        v = row[5] if len(row) > 5 else 0
        out.append([date_s, o, h, l, c, v])
    return out


def parse_tencent_smartbox_us_suffix(raw_text: str, ticker: str) -> str | None:
    """Parse Tencent smartbox US hint response to extract exact .OQ / .N / .AM suffix."""
    target = ticker.strip().lower()
    if not target:
        return None
    m = re.search(r'v_hint\s*=\s*"([^"]*)"', raw_text)
    content = m.group(1) if m else raw_text
    if not content:
        return None
    candidates: list[str] = []
    for item in content.split("^"):
        parts = item.split("~")
        if len(parts) < 2:
            continue
        mkt = parts[0].strip().lower()
        sym = parts[1].strip().lower()
        if mkt != "us" or "." not in sym:
            continue
        base, suffix = sym.rsplit(".", 1)
        suf_up = suffix.upper()
        if base == target and suf_up in US_ALLOWED_SUFFIXES:
            candidates.append(suf_up)
    if candidates:
        return candidates[0]
    return None


def parse_sina_cn_kline(raw_text: str) -> list[list[Any]]:
    """Parse Sina CN_MarketData.getKLineData JSON array [{day, open, high, low, close, volume}]."""
    text = raw_text.strip()
    if not text or text == "null":
        return []
    rows = json.loads(text)
    if not isinstance(rows, list):
        return []
    out: list[list[Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append([
            r.get("day", ""),
            r.get("open"),
            r.get("high"),
            r.get("low"),
            r.get("close"),
            r.get("volume", 0),
        ])
    return out


def parse_sina_us_kline(raw_text: str) -> list[list[Any]]:
    """Parse Sina US_MinKService.getDailyK JSON array [{d, o, h, l, c, v}]."""
    text = raw_text.strip()
    if not text or text == "null":
        return []
    rows = json.loads(text)
    if not isinstance(rows, list):
        return []
    out: list[list[Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append([
            r.get("d", ""),
            r.get("o"),
            r.get("h"),
            r.get("l"),
            r.get("c"),
            r.get("v", 0),
        ])
    return out


def parse_sina_global_futures(raw_text: str) -> list[list[Any]]:
    """Parse Sina GlobalFuturesService JSONP [{date, open, high, low, close, volume}]."""
    inner = _extract_jsonp_payload(raw_text)
    if not inner or inner == "null":
        return []
    rows = json.loads(inner)
    if not isinstance(rows, list):
        return []
    out: list[list[Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append([
            r.get("date", ""),
            r.get("open"),
            r.get("high"),
            r.get("low"),
            r.get("close"),
            r.get("volume", 0),
        ])
    return out


def parse_sina_inner_futures(raw_text: str) -> list[list[Any]]:
    """Parse Sina InnerFuturesNewService JSONP [{d, o, h, l, c, v}]."""
    inner = _extract_jsonp_payload(raw_text)
    if not inner or inner == "null":
        return []
    rows = json.loads(inner)
    if not isinstance(rows, list):
        return []
    out: list[list[Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        out.append([
            r.get("d", ""),
            r.get("o"),
            r.get("h"),
            r.get("l"),
            r.get("c"),
            r.get("v", 0),
        ])
    return out


def parse_sge_daily(raw_text: str) -> list[list[Any]]:
    """Parse SGE Dailyhq JSON {"time": [[date, open, close, low, high], ...]}.

    CRITICAL COLUMN ORDER: [date, open, close, low, high] -> [date, open, high, low, close, 0].
    """
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        return []
    rows = payload.get("time") or []
    if not isinstance(rows, list):
        return []
    out: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        date_s = str(row[0]).strip()
        o = row[1]
        c = row[2]
        l = row[3]
        h = row[4]
        out.append([date_s, o, h, l, c, 0])
    return out


def parse_sina_fx(raw_text: str) -> list[list[Any]]:
    """Parse Sina NewForexService.getDayKLine JSONP.

    CRITICAL COLUMN ORDER: pipe-separated "date,open,low,high,close"
    -> [date, open, high, low, close, 0].
    """
    inner = _extract_jsonp_payload(raw_text)
    if not inner or inner == "null":
        return []
    if inner.startswith('"') and inner.endswith('"'):
        data_str = json.loads(inner)
    else:
        data_str = inner.strip('"').strip("'")
    if not isinstance(data_str, str):
        return []
    out: list[list[Any]] = []
    for chunk in data_str.split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",")]
        if len(parts) < 5:
            continue
        date_s, o, l, h, c = parts[0], parts[1], parts[2], parts[3], parts[4]
        out.append([date_s, o, h, l, c, 0])
    return out


def parse_cboe_vix_csv(raw_text: str) -> list[list[Any]]:
    """Parse CBOE VIX_History.csv (DATE,OPEN,HIGH,LOW,CLOSE; MM/DD/YYYY)."""
    out: list[list[Any]] = []
    reader = csv.DictReader(io.StringIO(raw_text.lstrip("\ufeff")))
    for row in reader:
        date_s = normalize_date_mmddyyyy(row.get("DATE", ""))
        if not date_s:
            continue
        out.append([
            date_s,
            row.get("OPEN"),
            row.get("HIGH"),
            row.get("LOW"),
            row.get("CLOSE"),
            0,
        ])
    return out


def parse_treasury_csv(raw_text: str, column_name: str) -> list[list[Any]]:
    """Parse US Treasury daily rates CSV for a specific tenor column.

    Synthesizes OHLC as [date, val, val, val, val, 0].
    """
    out: list[list[Any]] = []
    reader = csv.DictReader(io.StringIO(raw_text.lstrip("\ufeff")))
    if not reader.fieldnames:
        return out
    # Match column case-insensitively with whitespace stripped
    col_match: str | None = None
    target_norm = column_name.strip().lower()
    for fn in reader.fieldnames:
        if fn and fn.strip().strip('"').lower() == target_norm:
            col_match = fn
            break
    if col_match is None:
        return out
    date_col = reader.fieldnames[0]
    for row in reader:
        date_s = normalize_date_mmddyyyy(row.get(date_col, "") or "")
        if not date_s:
            continue
        val = _to_float(row.get(col_match))
        if val is None or val <= 0:
            continue
        out.append([date_s, val, val, val, val, 0])
    return out


def parse_coinbase_candles(raw_text: str) -> list[list[Any]]:
    """Parse Coinbase Exchange daily candles JSON.

    CRITICAL COLUMN ORDER: descending [unix_ts, low, high, open, close, volume]
    -> [date_iso_utc, open, high, low, close, volume].
    """
    rows = json.loads(raw_text)
    if not isinstance(rows, list):
        return []
    out: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        ts = _to_float(row[0])
        if ts is None or ts <= 0:
            continue
        date_iso = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        l, h, o, c, v = row[1], row[2], row[3], row[4], row[5]
        out.append([date_iso, o, h, l, c, v])
    return out


def parse_ft_batch_series(raw_text: str) -> dict[str, list[list[Any]]]:
    """Parse FT chartapi/series response into {label: [[date, o, h, l, c, 0], ...]}.

    Safety guard: FT multi-element batch responses share a single top-level `Dates`
    array without padding missing dates for elements that skipped a trading day.
    Elements whose Close array length != len(Dates) are skipped here so the caller
    refetches them individually with exact 1:1 date alignment.
    """
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        return {}
    dates = payload.get("Dates") or []
    elements = payload.get("Elements") or []
    result: dict[str, list[list[Any]]] = {}
    for el in elements:
        if not isinstance(el, dict):
            continue
        label = str(el.get("Label", "")).strip().upper()
        if not label:
            continue
        comp: dict[str, list[Any]] = {}
        for cs in el.get("ComponentSeries") or []:
            if isinstance(cs, dict) and cs.get("Type"):
                comp[str(cs["Type"])] = cs.get("Values") or []
        closes = comp.get("Close") or []
        if len(closes) != len(dates) or not dates:
            continue
        opens = comp.get("Open") or []
        highs = comp.get("High") or []
        lows = comp.get("Low") or []
        rows: list[list[Any]] = []
        for idx, raw_d in enumerate(dates):
            c = _to_float(closes[idx])
            if c is None or c <= 0:
                continue
            date_iso = normalize_date_mmddyyyy(str(raw_d))
            if not date_iso:
                continue
            o = _to_float(opens[idx]) if idx < len(opens) else None
            h = _to_float(highs[idx]) if idx < len(highs) else None
            l = _to_float(lows[idx]) if idx < len(lows) else None
            o = o if (o is not None and o > 0) else c
            h = h if (h is not None and h > 0) else c
            l = l if (l is not None and l > 0) else c
            rows.append([date_iso, o, h, l, c, 0])
        result[label] = rows
    return result


def parse_justetf_performance(raw_text: str) -> list[list[Any]]:
    """Parse JustETF performance-chart JSON response into synthesized OHLC bars."""
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        return []
    series = payload.get("series") or []
    out: list[list[Any]] = []
    for pt in series:
        if not isinstance(pt, dict):
            continue
        date_iso = normalize_date_mmddyyyy(str(pt.get("date", "")))
        val_obj = pt.get("value")
        val = val_obj.get("raw") if isinstance(val_obj, dict) else val_obj
        f = _to_float(val)
        if not date_iso or f is None or f <= 0:
            continue
        out.append([date_iso, f, f, f, f, 0])
    return out


# ---------------------------------------------------------------------------
# HTTP Client with Per-Host Semaphores & Jittered Retries
# ---------------------------------------------------------------------------

class RateLimitedHttpClient:
    """Thread-safe stdlib HTTP client with per-host concurrency semaphores and retries."""

    def __init__(
        self,
        *,
        timeout: int = HTTP_TIMEOUT_SEC,
        retries: int = HTTP_RETRIES,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self._opener = opener or urllib.request.urlopen
        self._semaphores: dict[str, threading.Semaphore] = {
            "tencent": threading.Semaphore(8),
            "sina": threading.Semaphore(4),
            "ft": threading.Semaphore(1),
            "justetf": threading.Semaphore(1),
            "treasury": threading.Semaphore(2),
            "sge": threading.Semaphore(2),
            "cboe": threading.Semaphore(2),
            "coinbase": threading.Semaphore(2),
            "default": threading.Semaphore(4),
        }

    def _bucket_for_url(self, url: str) -> str:
        host = urllib.parse.urlsplit(url).netloc.lower()
        if "gtimg.cn" in host or "finance.qq.com" in host:
            return "tencent"
        if "sina.com.cn" in host:
            return "sina"
        if "ft.com" in host:
            return "ft"
        if "justetf.com" in host:
            return "justetf"
        if "treasury.gov" in host:
            return "treasury"
        if "sge.com.cn" in host:
            return "sge"
        if "cboe.com" in host:
            return "cboe"
        if "coinbase.com" in host:
            return "coinbase"
        return "default"

    def request_text(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        encoding: str = "utf-8",
    ) -> str:
        req_headers = {"User-Agent": USER_AGENT}
        if headers:
            req_headers.update(headers)
        sem = self._semaphores[self._bucket_for_url(url)]
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with sem:
                    req = urllib.request.Request(url, data=data, headers=req_headers)
                    with self._opener(req, timeout=self.timeout) as resp:
                        raw = resp.read()
                try:
                    return raw.decode(encoding)
                except UnicodeDecodeError:
                    return raw.decode("utf-8" if encoding != "utf-8" else "gbk", errors="replace")
            except urllib.error.HTTPError as exc:
                last_err = exc
                # Do not retry deterministic client/not-implemented errors
                if exc.code in (400, 401, 403, 404, 405, 501):
                    raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = exc
            if attempt < self.retries:
                delay = 0.35 * (2**attempt) + random.uniform(0.05, 0.25)
                time.sleep(delay)
        assert last_err is not None
        raise last_err


# ---------------------------------------------------------------------------
# US Ticker Suffix Cache
# ---------------------------------------------------------------------------

class UsSuffixCache:
    """Persistent thread-safe cache mapping US ticker -> Tencent suffix (OQ/N/AM)."""

    def __init__(self, path: Path = US_SUFFIX_CACHE_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._dirty = False
        self._data: dict[str, str] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    raw_map = loaded.get("suffixes", loaded)
                    if isinstance(raw_map, dict):
                        for k, v in raw_map.items():
                            if isinstance(k, str) and isinstance(v, str) and v.upper() in US_ALLOWED_SUFFIXES:
                                self._data[k.upper()] = v.upper()
            except (OSError, json.JSONDecodeError):
                pass

    def get(self, ticker: str) -> str | None:
        with self._lock:
            return self._data.get(ticker.upper())

    def set(self, ticker: str, suffix: str) -> None:
        suf = suffix.upper()
        if suf not in US_ALLOWED_SUFFIXES:
            return
        key = ticker.upper()
        with self._lock:
            if self._data.get(key) != suf:
                self._data[key] = suf
                self._dirty = True

    def save_if_dirty(self) -> bool:
        with self._lock:
            if not self._dirty:
                return False
            payload = {
                "schema_version": SCHEMA_VERSION,
                "updated_at_cst": datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "count": len(self._data),
                "suffixes": dict(sorted(self._data.items())),
            }
            atomic_write_json(self.path, payload, compact=False)
            self._dirty = False
            return True


# ---------------------------------------------------------------------------
# Atomic File I/O & Stale-While-Error Cache Merge
# ---------------------------------------------------------------------------

def atomic_write_json(path: Path, payload: Any, *, compact: bool = True) -> int:
    """Atomically write JSON with 0o644 permissions and return byte size."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    encoded = text.encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(encoded)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return len(encoded)


def load_existing_shard(path: Path) -> dict[str, dict[str, Any]]:
    """Load existing shard series map for stale-while-error preservation."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        series = data.get("series")
        if isinstance(series, dict):
            return series
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def build_series_record(
    spec: InstrumentSpec,
    bars: list[list[Any]],
    *,
    provider: str,
    stale: bool = False,
) -> dict[str, Any]:
    """Assemble standardized series record for shard JSON."""
    has_volume = False if spec.force_no_volume else any((b[5] or 0) > 0 for b in bars)
    latest_date = bars[-1][0] if bars else ""
    latest_close = bars[-1][4] if bars else None
    if len(bars) >= 2:
        prev_close = bars[-2][4]
    elif len(bars) == 1:
        prev_close = bars[-1][1]
    else:
        prev_close = None
    if latest_close is not None and prev_close is not None and prev_close > 0:
        change_pct = round((latest_close - prev_close) / prev_close * 100.0, 2)
    else:
        change_pct = 0.0

    rec: dict[str, Any] = {
        "id": spec.id,
        "code": spec.code,
        "name": spec.name,
        "group": spec.group,
        "market": spec.market,
        "currency": spec.currency,
        "unit": spec.unit,
        "provider": provider,
        "has_volume": has_volume,
        "latest_date": latest_date,
        "latest_close": latest_close,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "bars_count": len(bars),
        "stale": stale,
        "bars": bars,
    }
    if spec.market_label:
        rec["market_label"] = spec.market_label
    if spec.category:
        rec["category"] = spec.category
    if spec.dossier_key:
        rec["dossier_key"] = spec.dossier_key
    return rec


def catalog_entry_from_series(rec: dict[str, Any], shard: str) -> dict[str, Any]:
    """Extract lightweight manifest catalog entry (without full bars array)."""
    entry: dict[str, Any] = {
        "id": rec["id"],
        "code": rec["code"],
        "name": rec["name"],
        "group": rec["group"],
        "market": rec["market"],
        "currency": rec["currency"],
        "unit": rec["unit"],
        "shard": shard,
        "provider": rec["provider"],
        "has_volume": rec["has_volume"],
        "latest_date": rec["latest_date"],
        "latest_close": rec["latest_close"],
        "prev_close": rec["prev_close"],
        "change_pct": rec["change_pct"],
        "bars_count": rec["bars_count"],
        "stale": rec.get("stale", False),
    }
    if rec.get("market_label"):
        entry["market_label"] = rec["market_label"]
    if rec.get("category"):
        entry["category"] = rec["category"]
    if rec.get("dossier_key"):
        entry["dossier_key"] = rec["dossier_key"]
    return entry


def merge_with_stale_cache(
    spec: InstrumentSpec,
    fetched_bars: list[list[Any]] | None,
    provider: str | None,
    error_reason: str | None,
    cached_entry: dict[str, Any] | None,
    *,
    bars_limit: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Merge live fetch result with stale cache on failure.

    Returns (series_record_or_None, failure_entry_or_None).
    """
    if fetched_bars:
        rec = build_series_record(spec, fetched_bars, provider=provider or "unknown", stale=False)
        return rec, None

    if cached_entry and isinstance(cached_entry.get("bars"), list) and cached_entry["bars"]:
        sanitized = sanitize_bars(
            cached_entry["bars"],
            bars_limit=bars_limit,
            decimals_override=spec.decimals_override,
            force_no_volume=spec.force_no_volume,
        )
        if sanitized:
            cached_prov = str(cached_entry.get("provider", "cached"))
            rec = build_series_record(spec, sanitized, provider=cached_prov, stale=True)
            failure = {
                "id": spec.id,
                "code": spec.code,
                "shard": spec.shard,
                "reason": error_reason or "empty live response",
                "used_stale_cache": True,
            }
            return rec, failure

    failure = {
        "id": spec.id,
        "code": spec.code,
        "shard": spec.shard,
        "reason": error_reason or "empty live response",
        "used_stale_cache": False,
    }
    return None, failure


# ---------------------------------------------------------------------------
# Provider Fetch Engine
# ---------------------------------------------------------------------------

class KlineFetcher:
    """Orchestrates batch and per-instrument live K-line fetching across providers."""

    def __init__(
        self,
        http: RateLimitedHttpClient,
        us_cache: UsSuffixCache,
        *,
        bars_limit: int = DEFAULT_BARS,
        ref_year: int | None = None,
    ) -> None:
        self.http = http
        self.us_cache = us_cache
        self.bars_limit = bars_limit
        self.ref_year = ref_year or datetime.now(CST).year
        self._ft_cache: dict[str, list[list[Any]]] | None = None
        self._treasury_nom_cache: list[str] | None = None
        self._treasury_real_cache: list[str] | None = None
        self._batch_lock = threading.Lock()

    # --- Batch pre-fetchers ---

    def _fetch_ft_elements(self, base_codes: list[str]) -> dict[str, list[list[Any]]]:
        elements = []
        for bc in base_codes:
            xid = FT_UCITS_XID_MAP.get(bc)
            if xid:
                elements.append({"Label": bc, "Type": "price", "Symbol": xid})
        if not elements:
            return {}
        cal_days = max(240, int(self.bars_limit * 1.65) + 30)
        payload = {
            "days": cal_days,
            "dataNormalized": False,
            "dataPeriod": "Day",
            "dataInterval": 1,
            "realtime": False,
            "yFormat": "0.###",
            "timeServiceFormat": "JSON",
            "returnDateType": "ISO8601",
            "elements": elements,
        }
        raw = self.http.request_text(
            "https://markets.ft.com/data/chartapi/series",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://markets.ft.com",
                "Referer": "https://markets.ft.com/",
            },
            data=json.dumps(payload).encode("utf-8"),
        )
        return parse_ft_batch_series(raw)

    def prefetch_ft_ucits(self, base_codes: list[str]) -> dict[str, list[list[Any]]]:
        """Batch POST to FT chartapi/series, then individually refetch any length-mismatched tickers."""
        try:
            parsed = self._fetch_ft_elements(base_codes)
        except Exception:
            parsed = {}
        # Any ticker omitted due to multi-element date-length mismatch gets a 1-element exact-date fetch
        for bc in base_codes:
            if bc not in parsed and bc in FT_UCITS_XID_MAP:
                try:
                    single = self._fetch_ft_elements([bc])
                    if bc in single and single[bc]:
                        parsed[bc] = single[bc]
                except Exception:
                    pass
        with self._batch_lock:
            self._ft_cache = parsed
        return parsed

    def _get_treasury_csvs(self, curve_type: str) -> list[str]:
        with self._batch_lock:
            if curve_type == "nominal" and self._treasury_nom_cache is not None:
                return self._treasury_nom_cache
            if curve_type == "real" and self._treasury_real_cache is not None:
                return self._treasury_real_cache

        api_type = (
            "daily_treasury_yield_curve"
            if curve_type == "nominal"
            else "daily_treasury_real_yield_curve"
        )
        csvs: list[str] = []
        row_count = 0
        for year in (self.ref_year, self.ref_year - 1):
            url = (
                f"https://home.treasury.gov/resource-center/data-chart-center/"
                f"interest-rates/daily-treasury-rates.csv/{year}/all"
                f"?type={api_type}&field_tdr_date_value={year}&page&_format=csv"
            )
            try:
                raw = self.http.request_text(url)
                if raw.strip():
                    csvs.append(raw)
                    row_count += max(0, len(raw.splitlines()) - 1)
            except Exception:
                pass
            if row_count >= self.bars_limit + 5:
                break

        with self._batch_lock:
            if curve_type == "nominal":
                self._treasury_nom_cache = csvs
            else:
                self._treasury_real_cache = csvs
        return csvs

    # --- Individual provider callers ---

    def _fetch_tencent_cn(self, sym: str) -> tuple[list[list[Any]], str]:
        urls = [
            (
                "tencent_newfqkline",
                f"https://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={sym},day,,,{self.bars_limit},qfq",
            ),
            (
                "tencent_proxy_newfqkline",
                f"https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?param={sym},day,,,{self.bars_limit},qfq",
            ),
        ]
        last_err: Exception | None = None
        for prov, url in urls:
            try:
                raw = self.http.request_text(url)
                bars = parse_tencent_kline(raw, symbol_key=sym)
                if bars:
                    return bars, prov
            except Exception as exc:
                last_err = exc
        if last_err is not None:
            raise last_err
        return [], "tencent_newfqkline"

    def _fetch_sina_cn(self, sym: str) -> tuple[list[list[Any]], str]:
        url = (
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={self.bars_limit}"
        )
        raw = self.http.request_text(url, headers={"Referer": SINA_REFERER}, encoding="gbk")
        return parse_sina_cn_kline(raw), "sina_cn_kline"

    def _fetch_tencent_hk(self, sym: str) -> tuple[list[list[Any]], str]:
        urls = [
            (
                "tencent_hkfqkline",
                f"https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get?param={sym},day,,,{self.bars_limit},qfq",
            ),
            (
                "tencent_proxy_newfqkline",
                f"https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?param={sym},day,,,{self.bars_limit},qfq",
            ),
        ]
        last_err: Exception | None = None
        for prov, url in urls:
            try:
                raw = self.http.request_text(url)
                bars = parse_tencent_kline(raw, symbol_key=sym)
                if bars:
                    return bars, prov
            except Exception as exc:
                last_err = exc
        if last_err is not None:
            raise last_err
        return [], "tencent_hkfqkline"

    def _resolve_us_suffix(self, ticker: str) -> str | None:
        cached = self.us_cache.get(ticker)
        if cached:
            return cached
        q = urllib.parse.quote(ticker.lower())
        url = f"https://smartbox.gtimg.cn/s3/?v=2&q={q}&t=us"
        try:
            raw = self.http.request_text(url)
            suf = parse_tencent_smartbox_us_suffix(raw, ticker)
            if suf:
                self.us_cache.set(ticker, suf)
                return suf
        except Exception:
            pass
        return None

    def _fetch_tencent_us_raw(self, full_sym: str) -> list[list[Any]]:
        q_sym = urllib.parse.quote(full_sym, safe=".")
        url = f"https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get?param={q_sym},day,,,{self.bars_limit},qfq"
        raw = self.http.request_text(url)
        return parse_tencent_kline(raw, symbol_key=full_sym)

    def _fetch_sina_us(self, lower_sym: str) -> tuple[list[list[Any]], str]:
        q_sym = urllib.parse.quote(lower_sym, safe=".")
        url = f"https://stock.finance.sina.com.cn/usstock/api/json_v2.php/US_MinKService.getDailyK?symbol={q_sym}&___qn=3"
        raw = self.http.request_text(url, headers={"Referer": SINA_REFERER})
        return parse_sina_us_kline(raw), "sina_us_kline"

    def _fetch_justetf(self, isin: str) -> tuple[list[list[Any]], str]:
        end_dt = datetime.now(CST).date()
        start_dt = end_dt - timedelta(days=max(260, int(self.bars_limit * 1.7) + 30))
        url = (
            f"https://www.justetf.com/api/etfs/{isin}/performance-chart"
            f"?locale=en&currency=USD&valuesType=MARKET_VALUE&reduceData=false"
            f"&includeDividends=false&features=DIVIDENDS"
            f"&dateFrom={start_dt.isoformat()}&dateTo={end_dt.isoformat()}"
        )
        raw = self.http.request_text(url, headers={"Accept": "application/json"})
        return parse_justetf_performance(raw), "justetf_api"

    def fetch_instrument(self, spec: InstrumentSpec) -> tuple[list[list[Any]], str | None, str | None]:
        """Fetch and sanitize daily OHLCV bars for a single instrument with fallback chain.

        Returns (sanitized_bars, provider_name, error_reason).
        """
        errors: list[str] = []

        def _clean(raw_bars: list[list[Any]]) -> list[list[Any]]:
            return sanitize_bars(
                raw_bars,
                bars_limit=self.bars_limit,
                decimals_override=spec.decimals_override,
                force_no_volume=spec.force_no_volume,
            )

        kind = spec.kind

        if kind in ("cn_index", "cn_equity"):
            try:
                raw_bars, prov = self._fetch_tencent_cn(spec.provider_symbol)
                bars = _clean(raw_bars)
                if bars:
                    return bars, prov, None
                errors.append(f"{prov}:empty")
            except Exception as exc:
                errors.append(f"tencent_cn:{type(exc).__name__}")
            try:
                raw_bars, prov = self._fetch_sina_cn(spec.provider_symbol)
                bars = _clean(raw_bars)
                if bars:
                    return bars, prov, None
                errors.append(f"{prov}:empty")
            except Exception as exc:
                errors.append(f"sina_cn:{type(exc).__name__}")

        elif kind == "bj_sina":
            try:
                raw_bars, prov = self._fetch_sina_cn(spec.provider_symbol)
                bars = _clean(raw_bars)
                if bars:
                    return bars, prov, None
                errors.append(f"{prov}:empty")
            except Exception as exc:
                errors.append(f"sina_bj:{type(exc).__name__}")
            try:
                raw_bars, prov = self._fetch_tencent_cn(spec.provider_symbol)
                bars = _clean(raw_bars)
                if bars:
                    return bars, prov, None
                errors.append(f"{prov}:empty")
            except Exception as exc:
                errors.append(f"tencent_bj:{type(exc).__name__}")

        elif kind in ("hk_index", "hk_equity"):
            try:
                raw_bars, prov = self._fetch_tencent_hk(spec.provider_symbol)
                bars = _clean(raw_bars)
                if bars:
                    return bars, prov, None
                errors.append(f"{prov}:empty")
            except Exception as exc:
                errors.append(f"tencent_hk:{type(exc).__name__}")

        elif kind == "us_index":
            try:
                raw_bars = self._fetch_tencent_us_raw(spec.provider_symbol)
                bars = _clean(raw_bars)
                if bars:
                    return bars, "tencent_usfqkline", None
                errors.append("tencent_usfqkline:empty")
            except Exception as exc:
                errors.append(f"tencent_us:{type(exc).__name__}")
            if spec.fallback_symbol:
                try:
                    raw_bars, prov = self._fetch_sina_us(spec.fallback_symbol)
                    bars = _clean(raw_bars)
                    if bars:
                        return bars, prov, None
                    errors.append(f"{prov}:empty")
                except Exception as exc:
                    errors.append(f"sina_us:{type(exc).__name__}")

        elif kind == "us_sina_only":
            try:
                raw_bars, prov = self._fetch_sina_us(spec.provider_symbol)
                bars = _clean(raw_bars)
                if bars:
                    return bars, prov, None
                errors.append(f"{prov}:empty")
            except Exception as exc:
                errors.append(f"sina_us:{type(exc).__name__}")

        elif kind == "us_equity":
            ticker = spec.provider_symbol
            suf = self._resolve_us_suffix(ticker)
            if suf:
                try:
                    raw_bars = self._fetch_tencent_us_raw(f"us{ticker}.{suf}")
                    bars = _clean(raw_bars)
                    if bars:
                        return bars, "tencent_usfqkline", None
                    errors.append(f"tencent_us({suf}):empty")
                except Exception as exc:
                    errors.append(f"tencent_us({suf}):{type(exc).__name__}")
            # Fallback to Sina US daily K-line (no suffix required, handles BRK.B / new ETFs)
            try:
                raw_bars, prov = self._fetch_sina_us(spec.fallback_symbol or ticker.lower())
                bars = _clean(raw_bars)
                if bars:
                    return bars, prov, None
                errors.append(f"{prov}:empty")
            except Exception as exc:
                errors.append(f"sina_us:{type(exc).__name__}")
            # Last resort: probe remaining Tencent suffixes if smartbox missed
            if not suf:
                for cand_suf in US_ALLOWED_SUFFIXES:
                    try:
                        raw_bars = self._fetch_tencent_us_raw(f"us{ticker}.{cand_suf}")
                        bars = _clean(raw_bars)
                        if len(bars) >= 2:
                            self.us_cache.set(ticker, cand_suf)
                            return bars, "tencent_usfqkline", None
                    except Exception:
                        pass

        elif kind == "cboe_vix":
            try:
                raw = self.http.request_text(
                    "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
                )
                bars = _clean(parse_cboe_vix_csv(raw))
                if bars:
                    return bars, "cboe_vix_csv", None
                errors.append("cboe_vix:empty")
            except Exception as exc:
                errors.append(f"cboe_vix:{type(exc).__name__}")

        elif kind == "ucits_ft":
            base = spec.provider_symbol
            with self._batch_lock:
                ft_map = self._ft_cache
            if ft_map and base in ft_map:
                bars = _clean(ft_map[base])
                if bars:
                    return bars, "ft_chartapi", None
            errors.append("ft_chartapi:empty")
            isin = spec.fallback_symbol or JUSTETF_ISIN_MAP.get(base, "")
            if isin:
                try:
                    raw_bars, prov = self._fetch_justetf(isin)
                    bars = _clean(raw_bars)
                    if bars:
                        return bars, prov, None
                    errors.append(f"{prov}:empty")
                except Exception as exc:
                    errors.append(f"justetf:{type(exc).__name__}")

        elif kind == "sina_global_futures":
            url = (
                "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/x/"
                f"GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={urllib.parse.quote(spec.provider_symbol)}"
            )
            try:
                raw = self.http.request_text(url, headers={"Referer": SINA_REFERER}, encoding="gbk")
                bars = _clean(parse_sina_global_futures(raw))
                if bars:
                    return bars, "sina_global_futures", None
                errors.append("sina_global_futures:empty")
            except Exception as exc:
                errors.append(f"sina_global_futures:{type(exc).__name__}")

        elif kind == "sina_inner_futures":
            url = (
                "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/x/"
                f"InnerFuturesNewService.getDailyKLine?symbol={urllib.parse.quote(spec.provider_symbol)}"
            )
            try:
                raw = self.http.request_text(url, headers={"Referer": SINA_REFERER}, encoding="gbk")
                bars = _clean(parse_sina_inner_futures(raw))
                if bars:
                    return bars, "sina_inner_futures", None
                errors.append("sina_inner_futures:empty")
            except Exception as exc:
                errors.append(f"sina_inner_futures:{type(exc).__name__}")

        elif kind == "sge_daily":
            url = f"https://www.sge.com.cn/graph/Dailyhq?instid={urllib.parse.quote(spec.provider_symbol)}"
            try:
                raw = self.http.request_text(url)
                bars = _clean(parse_sge_daily(raw))
                if bars:
                    return bars, "sge_dailyhq", None
                errors.append("sge_dailyhq:empty")
            except Exception as exc:
                errors.append(f"sge_dailyhq:{type(exc).__name__}")

        elif kind == "sina_fx":
            url = (
                "https://vip.stock.finance.sina.com.cn/forex/api/jsonp.php/x/"
                f"NewForexService.getDayKLine?symbol={urllib.parse.quote(spec.provider_symbol)}"
            )
            try:
                raw = self.http.request_text(url, headers={"Referer": SINA_REFERER}, encoding="gbk")
                bars = _clean(parse_sina_fx(raw))
                if bars:
                    return bars, "sina_forex", None
                errors.append("sina_forex:empty")
            except Exception as exc:
                errors.append(f"sina_forex:{type(exc).__name__}")

        elif kind in ("treasury_nominal", "treasury_real"):
            curve = "nominal" if kind == "treasury_nominal" else "real"
            csvs = self._get_treasury_csvs(curve)
            combined: list[list[Any]] = []
            for raw_csv in csvs:
                combined.extend(parse_treasury_csv(raw_csv, spec.provider_symbol))
            bars = _clean(combined)
            if bars:
                return bars, "us_treasury_csv", None
            errors.append("us_treasury_csv:empty")

        elif kind == "coinbase_crypto":
            url = f"https://api.exchange.coinbase.com/products/{urllib.parse.quote(spec.provider_symbol)}/candles?granularity=86400"
            try:
                raw = self.http.request_text(url, headers={"Accept": "application/json"})
                bars = _clean(parse_coinbase_candles(raw))
                if bars:
                    return bars, "coinbase_candles", None
                errors.append("coinbase_candles:empty")
            except Exception as exc:
                errors.append(f"coinbase_candles:{type(exc).__name__}")

        else:
            errors.append(f"unknown_kind:{kind}")

        return [], None, "; ".join(errors) if errors else "fetch_failed"


# ---------------------------------------------------------------------------
# Main Orchestration
# ---------------------------------------------------------------------------

def resolve_edition_id(explicit_edition_id: str | None) -> str:
    if explicit_edition_id and explicit_edition_id.strip():
        return explicit_edition_id.strip()
    if MARKET_STATE_PATH.exists():
        try:
            data = json.loads(MARKET_STATE_PATH.read_text(encoding="utf-8"))
            eid = str(data.get("edition_id", "")).strip()
            if eid:
                return eid
        except (OSError, json.JSONDecodeError):
            pass
    return datetime.now(CST).strftime("%Y-%m-%d_%H%M")


def run_fetch(
    *,
    scope: str = "all",
    bars_limit: int = DEFAULT_BARS,
    edition_id: str | None = None,
    out_dir: Path = DEFAULT_OUT_DIR,
    workers: int = DEFAULT_WORKERS,
    etf_path: Path = ETF_UNIVERSE_PATH,
    dossiers_path: Path = DEEP_DOSSIERS_PATH,
    us_suffix_cache_path: Path = US_SUFFIX_CACHE_PATH,
    http_client: RateLimitedHttpClient | None = None,
) -> dict[str, Any]:
    """Execute K-line fetch for the selected scope and atomically write shard + manifest JSONs."""
    t0 = time.monotonic()
    bars_limit = max(MIN_BARS, min(MAX_BARS, int(bars_limit)))
    workers = max(1, min(32, int(workers)))
    eid = resolve_edition_id(edition_id)
    now_cst = datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")

    ref_year = int(eid[:4]) if len(eid) >= 4 and eid[:4].isdigit() else datetime.now(CST).year

    target_shards = SCOPE_SHARDS[scope]
    specs: list[InstrumentSpec] = []
    if scope in ("all", "core"):
        specs.extend(build_core_specs())
    if scope in ("all", "etfs"):
        specs.extend(load_etf_specs(etf_path))
    if scope in ("all", "stocks"):
        specs.extend(load_stock_specs(dossiers_path))

    # Load existing shards for stale-while-error preservation
    existing_by_shard: dict[str, dict[str, dict[str, Any]]] = {
        sh: load_existing_shard(out_dir / f"{sh}.json") for sh in target_shards
    }

    http = http_client or RateLimitedHttpClient()
    us_cache = UsSuffixCache(us_suffix_cache_path)
    fetcher = KlineFetcher(http, us_cache, bars_limit=bars_limit, ref_year=ref_year)

    # Batch pre-fetch Irish UCITS ETFs in a single FT POST if any are in scope
    ucits_bases = [s.provider_symbol for s in specs if s.kind == "ucits_ft"]
    if ucits_bases:
        fetcher.prefetch_ft_ucits(ucits_bases)

    # Parallel fetch across all specs in scope
    fetched_results: dict[str, tuple[list[list[Any]], str | None, str | None]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(fetcher.fetch_instrument, sp): sp for sp in specs}
        for fut in as_completed(future_map):
            sp = future_map[fut]
            try:
                fetched_results[sp.id] = fut.result()
            except Exception as exc:
                fetched_results[sp.id] = ([], None, f"unhandled:{type(exc).__name__}")

    us_cache.save_if_dirty()

    # Merge with stale cache in canonical spec order
    shard_series: dict[str, dict[str, dict[str, Any]]] = {sh: {} for sh in target_shards}
    new_catalog_by_shard: dict[str, list[dict[str, Any]]] = {sh: [] for sh in target_shards}
    new_failures_by_shard: dict[str, list[dict[str, Any]]] = {sh: [] for sh in target_shards}
    omitted_optional: list[str] = []

    for sp in specs:
        bars, prov, err = fetched_results.get(sp.id, ([], None, "missing_result"))
        if sp.optional_min_bars > 0 and len(bars) < sp.optional_min_bars:
            omitted_optional.append(sp.id)
            continue
        cached = existing_by_shard.get(sp.shard, {}).get(sp.id)
        rec, failure = merge_with_stale_cache(
            sp, bars, prov, err, cached, bars_limit=bars_limit
        )
        if rec is not None:
            shard_series[sp.shard][sp.id] = rec
            new_catalog_by_shard[sp.shard].append(catalog_entry_from_series(rec, sp.shard))
        if failure is not None:
            new_failures_by_shard[sp.shard].append(failure)

    # Atomically write each target shard JSON
    shard_meta: dict[str, dict[str, Any]] = {}
    for sh in target_shards:
        shard_file = out_dir / f"{sh}.json"
        shard_payload = {
            "schema_version": SCHEMA_VERSION,
            "shard": sh,
            "edition_id": eid,
            "generated_at_cst": now_cst,
            "bars_limit": bars_limit,
            "count": len(shard_series[sh]),
            "series": shard_series[sh],
        }
        nbytes = atomic_write_json(shard_file, shard_payload, compact=True)
        shard_meta[sh] = {
            "file": f"{sh}.json",
            "count": len(shard_series[sh]),
            "bytes": nbytes,
        }

    # Load previous manifest to preserve untouched shards on partial scopes
    manifest_path = out_dir / "manifest.json"
    prev_manifest: dict[str, Any] = {}
    if scope != "all" and manifest_path.exists():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                prev_manifest = loaded
        except (OSError, json.JSONDecodeError):
            prev_manifest = {}

    final_shards: dict[str, dict[str, Any]] = {}
    final_catalog: list[dict[str, Any]] = []
    final_failures: list[dict[str, Any]] = []

    prev_catalog_by_shard: dict[str, list[dict[str, Any]]] = {}
    for item in prev_manifest.get("catalog", []):
        if isinstance(item, dict) and item.get("shard"):
            prev_catalog_by_shard.setdefault(str(item["shard"]), []).append(item)

    prev_failures_by_shard: dict[str, list[dict[str, Any]]] = {}
    for item in prev_manifest.get("partial_failures", []):
        if isinstance(item, dict) and item.get("shard"):
            prev_failures_by_shard.setdefault(str(item["shard"]), []).append(item)

    for sh in ALL_SHARDS_ORDER:
        if sh in target_shards:
            final_shards[sh] = shard_meta[sh]
            final_catalog.extend(new_catalog_by_shard[sh])
            final_failures.extend(new_failures_by_shard[sh])
        elif sh in prev_manifest.get("shards", {}):
            final_shards[sh] = prev_manifest["shards"][sh]
            final_catalog.extend(prev_catalog_by_shard.get(sh, []))
            final_failures.extend(prev_failures_by_shard.get(sh, []))

    stale_count = sum(1 for c in final_catalog if c.get("stale"))
    ok_count = len(final_catalog)
    failed_count = sum(1 for f in final_failures if not f.get("used_stale_cache"))
    total_instruments = ok_count + failed_count

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "edition_id": eid,
        "generated_at_cst": now_cst,
        "bars_limit": bars_limit,
        "total_instruments": total_instruments,
        "ok_count": ok_count,
        "fresh_count": ok_count - stale_count,
        "stale_count": stale_count,
        "failed_count": failed_count,
        "shards": final_shards,
        "catalog": final_catalog,
        "partial_failures": final_failures,
    }
    manifest_bytes = atomic_write_json(manifest_path, manifest, compact=True)
    elapsed = round(time.monotonic() - t0, 2)

    return {
        "edition_id": eid,
        "scope": scope,
        "elapsed_sec": elapsed,
        "total_instruments": total_instruments,
        "ok_count": ok_count,
        "fresh_count": ok_count - stale_count,
        "stale_count": stale_count,
        "failed_count": failed_count,
        "omitted_optional": omitted_optional,
        "manifest_bytes": manifest_bytes,
        "shards": final_shards,
        "partial_failures": final_failures,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Zero-dependency daily K-line (OHLCV) fetcher for Global Investment Research."
    )
    parser.add_argument(
        "--scope",
        choices=("all", "core", "etfs", "stocks"),
        default="all",
        help="Instrument scope to fetch (default: all).",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=DEFAULT_BARS,
        help=f"Maximum daily bars per instrument, clamped to {MIN_BARS}..{MAX_BARS} (default: {DEFAULT_BARS}).",
    )
    parser.add_argument(
        "--edition-id",
        default=None,
        help="Edition ID label (defaults to market_state.json edition_id).",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR.relative_to(REPO_ROOT)),
        help="Output directory for K-line shard JSONs and manifest.json.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Concurrent worker threads (default: {DEFAULT_WORKERS}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_path = Path(args.out_dir)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    summary = run_fetch(
        scope=args.scope,
        bars_limit=args.bars,
        edition_id=args.edition_id,
        out_dir=out_path,
        workers=args.workers,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # Exit non-zero only if total collapse (<90% coverage)
    total = summary["total_instruments"]
    ok = summary["ok_count"]
    if total == 0 or (ok / total) < 0.90:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
