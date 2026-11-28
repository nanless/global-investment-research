#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure offline unit tests for scripts/fetch_kline_data.py (ZERO network calls)."""

from __future__ import annotations

from datetime import date
import io
import json
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from scripts import fetch_kline_data as fk
from scripts import lint_site, state_transaction


class TestCanonicalKlineUniverse(unittest.TestCase):
    def test_duplicate_id_is_rejected_before_fetch(self):
        spec = fk.build_core_specs()[0]
        with patch.object(fk, "load_etf_specs", return_value=[spec]):
            with self.assertRaisesRegex(ValueError, "Duplicate K-line instrument ID"):
                fk.load_instrument_specs("all")

    def test_roster_rejects_count_preserving_replacement_and_misrouted_failure(self):
        specs = fk.load_instrument_specs("all")
        manifest = json.loads((fk.DEFAULT_OUT_DIR / "manifest.json").read_text(encoding="utf-8"))
        catalog = {row["id"]: row for row in manifest["catalog"]}
        failures = {row["id"]: row for row in manifest["partial_failures"]}
        errors = []
        lint_site.check_s7_roster(specs, catalog, failures, manifest["shards"], errors)
        self.assertEqual(errors, [])

        stock = next(spec for spec in specs if spec.shard == "stocks_us" and spec.id in catalog)
        removed = catalog.pop(stock.id)
        catalog["stk_FAKE"] = {**removed, "id": "stk_FAKE"}
        lint_site.check_s7_roster(specs, catalog, failures, manifest["shards"], errors)
        self.assertTrue(any(stock.id in error and "stk_FAKE" in error for error in errors), errors)

        del catalog["stk_FAKE"]
        failures[stock.id] = {
            "id": stock.id, "code": stock.code, "shard": "stocks_a",
            "reason": "source unavailable", "used_stale_cache": False,
        }
        errors.clear()
        lint_site.check_s7_roster(specs, catalog, failures, manifest["shards"], errors)
        self.assertTrue(any(stock.id in error and "invalid metadata" in error for error in errors), errors)

        failures[stock.id]["shard"] = stock.shard
        errors.clear()
        lint_site.check_s7_roster(specs, catalog, failures, manifest["shards"], errors)
        self.assertEqual(errors, [])

    def test_failed_partial_refresh_keeps_the_previous_generation(self):
        spec = fk.build_core_specs()[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.json"
            manifest.write_text('{"edition_id":"2026-11-27_0730","shards":{}}', encoding="utf-8")
            baseline = manifest.read_bytes()
            with (
                patch.object(fk, "load_instrument_specs", return_value=[spec]),
                patch.object(fk.KlineFetcher, "fetch_instrument", return_value=([], None, "offline")),
            ):
                summary = fk.run_fetch(
                    scope="core", edition_id="2026-11-27_1130", out_dir=root,
                    http_client=fk.RateLimitedHttpClient(retries=0),
                )
            self.assertFalse(summary["promoted"])
            self.assertEqual(summary["failed_count"], 1)
            self.assertEqual(manifest.read_bytes(), baseline)
            self.assertFalse((root / "core.json").exists())

    def test_canonical_partial_refresh_cannot_replace_a_complete_site_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "publication"
            with patch.object(fk, "DEFAULT_OUT_DIR", root):
                with self.assertRaisesRegex(ValueError, "publication directory needs --scope all"):
                    fk.run_fetch(scope="core", out_dir=root)
            self.assertFalse(root.exists())

    def test_full_refresh_keeps_existing_files_when_required_series_is_missing(self):
        specs = fk.load_instrument_specs("all")
        missing_id = "idx_TOPIX"
        issue = "2026-11-28_1130"
        bars = [["2026-11-27", 10, 12, 9, 11, 100]]

        def fetch_instrument(spec):
            return ([], None, "offline") if spec.id == missing_id else (bars, "fixture", None)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "manifest.json").write_bytes(b'{"edition_id":"2026-11-28_0730"}')
            (root / "core.json").write_bytes(b'{"series":{}}')
            previous = {p.name: p.read_bytes() for p in root.glob("*.json")}
            with (
                patch.object(fk, "DEFAULT_OUT_DIR", root),
                patch.object(fk, "resolve_edition_id", return_value=issue),
                patch.object(fk, "load_instrument_specs", return_value=specs),
                patch.object(fk.KlineFetcher, "prefetch_ft_ucits"),
                patch.object(fk.KlineFetcher, "prefetch_cnbc_quotes"),
                patch.object(fk.KlineFetcher, "prefetch_sina_fx_quotes"),
                patch.object(fk.KlineFetcher, "prefetch_eastmoney_cgb"),
                patch.object(fk.KlineFetcher, "fetch_instrument", side_effect=fetch_instrument),
            ):
                summary = fk.run_fetch(out_dir=root)
            self.assertGreater(summary["ok_count"], fk.MIN_PUBLISHED_INSTRUMENTS - 10)
            self.assertFalse(summary["promoted"])
            self.assertTrue(summary["retained_previous"])
            self.assertEqual(summary["publication_blockers"], ["Missing required K-line series: idx_TOPIX"])
            self.assertEqual({p.name: p.read_bytes() for p in root.glob("*.json")}, previous)

    def test_us_etf_benchmarks_show_dollars_and_match_stored_candle_metadata(self):
        specs = {spec.id: spec for spec in fk.build_core_specs()}
        core = json.loads((fk.DEFAULT_OUT_DIR / "core.json").read_text(encoding="utf-8"))
        manifest = json.loads((fk.DEFAULT_OUT_DIR / "manifest.json").read_text(encoding="utf-8"))
        catalog = {row["id"]: row for row in manifest["catalog"]}
        for asset_id, ticker in (("idx_RUT", "IWM"), ("idx_SPXEW", "RSP")):
            spec = specs[asset_id]
            self.assertIn(f"ETF（{ticker}）", spec.name)
            self.assertEqual(spec.unit, "美元")
            for row in (core["series"][asset_id], catalog[asset_id]):
                self.assertEqual((row["code"], row["name"], row["unit"]), (ticker, spec.name, spec.unit))

    def test_ucits_usd_quote_labels_keep_the_directory_code_and_show_the_actual_london_ticker(self):
        specs = {spec.id: spec for spec in fk.load_etf_specs()}
        offshore = json.loads((fk.DEFAULT_OUT_DIR / "etfs_offshore.json").read_bytes())
        manifest = json.loads((fk.DEFAULT_OUT_DIR / "manifest.json").read_bytes())
        catalog = {row["id"]: row for row in manifest["catalog"]}
        for code, ticker in (("SWDA", "IWDA"), ("EQQQ", "EQQU")):
            asset_id = f"etf_{code}"
            spec = specs[asset_id]
            self.assertEqual((spec.code, spec.currency), (code, "USD"))
            self.assertIn(f"伦交所美元代码 {ticker}", spec.name)
            for row in (offshore["series"][asset_id], catalog[asset_id]):
                self.assertEqual((row["code"], row["name"], row["currency"]), (code, spec.name, "USD"))

    def test_same_edition_outage_preserves_the_generation_and_recovers_after_sigkill(self):
        child = """
import os
from pathlib import Path
import signal
import sys
from unittest.mock import patch
from scripts import fetch_kline_data as fetcher

root, issue = Path(sys.argv[1]), sys.argv[2]
spec = fetcher.build_core_specs()[0]
replace = os.replace
def kill_after_shard(source, target):
    replace(source, target)
    if target.name == "core.json":
        os.kill(os.getpid(), signal.SIGKILL)

with (
    patch.object(os, "replace", side_effect=kill_after_shard),
    patch.object(fetcher, "load_instrument_specs", return_value=[spec]),
    patch.object(fetcher.KlineFetcher, "fetch_instrument", return_value=(
        [["2026-11-27", 10, 12, 9, 12, 100]], "fixture", None,
    )),
):
    fetcher.run_fetch(scope="core", edition_id=issue, out_dir=root)
"""
        spec = fk.build_core_specs()[0]
        issue = "2026-11-28_1130"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(fk, "load_instrument_specs", return_value=[spec]),
                patch.object(fk.KlineFetcher, "fetch_instrument", return_value=(
                    [["2026-11-27", 10, 12, 9, 11, 100]], "fixture", None,
                )),
            ):
                self.assertTrue(fk.run_fetch(scope="core", edition_id=issue, out_dir=root)["promoted"])
            first = {path.name: path.read_bytes() for path in root.glob("*.json")}
            stopped = subprocess.run(
                [sys.executable, "-B", "-c", child, tmp, issue], capture_output=True, timeout=10,
            )
            self.assertEqual(stopped.returncode, -signal.SIGKILL, stopped.stderr.decode())
            self.assertNotEqual(first["core.json"], (root / "core.json").read_bytes())
            self.assertEqual(first["manifest.json"], (root / "manifest.json").read_bytes())
            with self.assertRaisesRegex(RuntimeError, "needs recovery"), state_transaction.state_read_lock(root):
                self.fail("A reader must reject a pending transaction")

            with (
                patch.object(fk, "load_instrument_specs", return_value=[spec]),
                patch.object(fk.KlineFetcher, "fetch_instrument", return_value=([], None, "offline")),
            ):
                result = fk.run_fetch(scope="core", edition_id=issue, out_dir=root)
            self.assertFalse(result["promoted"])
            self.assertTrue(result["retained_previous"])
            self.assertTrue(result["partial_failures"][0]["used_stale_cache"])
            with state_transaction.state_read_lock(root):
                self.assertEqual({path.name: path.read_bytes() for path in root.glob("*.json")}, first)

    def test_during_fetch_a_changed_shard_cannot_be_overwritten_with_unchanged_manifest(self):
        spec = fk.build_core_specs()[0]
        bars = [["2026-11-27", 10, 12, 9, 11, 100]]
        with tempfile.TemporaryDirectory() as tmp, patch.object(fk, "load_instrument_specs", return_value=[spec]):
            root = Path(tmp)
            with patch.object(fk.KlineFetcher, "fetch_instrument", return_value=(bars, "fixture", None)):
                fk.run_fetch(scope="core", edition_id="2026-11-28_1130", out_dir=root)
            old_manifest = (root / "manifest.json").read_bytes()

            def fetch_after_outside_write(_spec):
                (root / "core.json").write_bytes(b"different bytes under the same manifest")
                return bars, "fixture", None

            with patch.object(fk.KlineFetcher, "fetch_instrument", side_effect=fetch_after_outside_write):
                with self.assertRaisesRegex(RuntimeError, "K-line data changed during the fetch"):
                    fk.run_fetch(scope="core", edition_id="2026-11-28_1130", out_dir=root)
            self.assertEqual((root / "core.json").read_bytes(), b"different bytes under the same manifest")
            self.assertEqual((root / "manifest.json").read_bytes(), old_manifest)

    def test_s7_recomputes_previous_close_and_rejects_bad_volume_number_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            shipped = site / "assets/klines"
            shutil.copytree(fk.DEFAULT_OUT_DIR, shipped)
            shutil.copy2(fk.REPO_ROOT / "scripts/web_assets/kline.js", site / "assets/kline.js")
            charts = lint_site.parse_html_file(
                "charts.html", site / "charts.html",
                '<button data-chart-group="non_us_global"></button><button data-chart-group="bonds_reits"></button>',
            )
            specs = fk.load_instrument_specs("all")
            manifest_path = shipped / "manifest.json"
            manifest_original = manifest_path.read_bytes()
            edition = json.loads(manifest_original)["edition_id"]
            shard_path = shipped / "core.json"
            shard_original = shard_path.read_bytes()
            symbol = "idx_sh000001"

            def check() -> list[str]:
                issues = []
                lint_site.run_gate_s7(
                    site, {"charts.html": charts}, issues, [], expected_edition=edition, expected_specs=specs,
                )
                return issues

            self.assertEqual(check(), [])
            for field, value, expected_error in (
                ("prev_close", 0, "previous close, change or volume metadata differs"),
                ("change_pct", 99, "previous close, change or volume metadata differs"),
                ("volume", -1, "invalid volume"),
                ("open", 10 ** 600, "non-finite OHLC"),
                ("generation", None, "valid Beijing-time generation timestamp"),
            ):
                with self.subTest(field=field):
                    manifest = json.loads(manifest_original)
                    shard = json.loads(shard_original)
                    series = shard["series"][symbol]
                    entry = next(row for row in manifest["catalog"] if row["id"] == symbol)
                    if field in ("prev_close", "change_pct"):
                        entry[field] = series[field] = value
                    elif field == "generation":
                        shard["generated_at_cst"] = manifest["generated_at_cst"] = value
                    else:
                        series["bars"][0][5 if field == "volume" else 1] = value
                    manifest["shards"]["core"]["bytes"] = fk.atomic_write_json(shard_path, shard)
                    fk.atomic_write_json(manifest_path, manifest)
                    errors = check()
                    self.assertTrue(any(expected_error in error for error in errors), errors)

class _FakeResponse:
    def __init__(self, body: bytes | str) -> None:
        self._data = body.encode("utf-8") if isinstance(body, str) else body

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class TestCodeRouting(unittest.TestCase):
    def test_cn_index_routing(self) -> None:
        for code in (
            "000001", "000300", "000510", "000016", "000688",
            "000680", "000905", "000852", "000922", "000832",
        ):
            self.assertEqual(fk.route_cn_symbol(code, is_index=True), f"sh{code}")
        self.assertEqual(fk.route_cn_symbol("399001", is_index=True), "sz399001")
        self.assertEqual(fk.route_cn_symbol("399006", is_index=True), "sz399006")
        self.assertEqual(fk.route_cn_symbol("899050", is_index=True), "bj899050")

    def test_cn_stock_and_etf_routing(self) -> None:
        self.assertEqual(fk.route_cn_symbol("601088"), "sh601088")
        self.assertEqual(fk.route_cn_symbol("688981"), "sh688981")
        self.assertEqual(fk.route_cn_symbol("510300"), "sh510300")
        self.assertEqual(fk.route_cn_symbol("588000"), "sh588000")
        self.assertEqual(fk.route_cn_symbol("563360"), "sh563360")
        self.assertEqual(fk.route_cn_symbol("551500"), "sh551500")
        self.assertEqual(fk.route_cn_symbol("000333"), "sz000333")
        self.assertEqual(fk.route_cn_symbol("002594"), "sz002594")
        self.assertEqual(fk.route_cn_symbol("159509"), "sz159509")
        self.assertEqual(fk.route_cn_symbol("161226"), "sz161226")
        self.assertEqual(fk.route_cn_symbol("300750"), "sz300750")
        self.assertEqual(fk.route_cn_symbol("830799"), "bj830799")
        self.assertEqual(fk.route_cn_symbol("430047"), "bj430047")
        self.assertEqual(fk.route_cn_symbol("920001"), "bj920001")

    def test_hk_and_lse_routing(self) -> None:
        self.assertEqual(fk.route_hk_symbol("00700.HK"), "hk00700")
        self.assertEqual(fk.route_hk_symbol("700.hk"), "hk00700")
        self.assertEqual(fk.route_hk_symbol("02800"), "hk02800")
        self.assertEqual(fk.route_hk_symbol("HSI", is_index=True), "hkHSI")
        self.assertEqual(fk.route_hk_symbol("HSTECH", is_index=True), "hkHSTECH")
        self.assertEqual(fk.strip_lse_suffix("VUAA.L"), "VUAA")
        self.assertEqual(fk.strip_lse_suffix("ib01"), "IB01")


class TestParsersAndColumnReordering(unittest.TestCase):
    def test_tencent_kline_reorders_open_close_high_low(self) -> None:
        # Tencent raw order: [date, open, close, high, low, volume]
        payload = json.dumps({
            "code": 0,
            "msg": "",
            "data": {
                "sh601088": {
                    "qfqday": [
                        ["2026-11-24", "50.00", "51.50", "52.10", "49.80", "350000", {}, "0.22"],
                        ["2026-11-25", "51.60", "50.90", "52.00", "50.50", "280000"],
                    ]
                }
            },
        })
        rows = fk.parse_tencent_kline(payload, symbol_key="sh601088")
        self.assertEqual(len(rows), 2)
        # Reordered to: [date, open, high, low, close, volume]
        self.assertEqual(rows[0], ["2026-11-24", "50.00", "52.10", "49.80", "51.50", "350000"])
        self.assertEqual(rows[1], ["2026-11-25", "51.60", "52.00", "50.50", "50.90", "280000"])

    def test_tencent_kline_falls_back_to_day_when_no_qfqday(self) -> None:
        payload = json.dumps({
            "code": 0,
            "data": {
                "sh000001": {
                    "day": [["2026-11-25", "3500.0", "3510.0", "3525.0", "3490.0", "450000000"]]
                }
            },
        })
        rows = fk.parse_tencent_kline(payload, symbol_key="sh000001")
        self.assertEqual(rows, [["2026-11-25", "3500.0", "3525.0", "3490.0", "3510.0", "450000000"]])

    def test_tencent_smartbox_us_suffix(self) -> None:
        raw_nvda = 'v_hint="us~nvda.oq~\\u82f1\\u4f1f\\u8fbe~ywd~GP^us~nvdx.am~2x~*~ETF"'
        self.assertEqual(fk.parse_tencent_smartbox_us_suffix(raw_nvda, "NVDA"), "OQ")

        raw_brkb = 'v_hint="us~brk.b.n~berkshire~bkxeb~GP"'
        self.assertEqual(fk.parse_tencent_smartbox_us_suffix(raw_brkb, "BRK.B"), "N")

        # Ignores OTC pink sheets (.ps) and partial prefix hits
        raw_ant = 'v_hint="us~ant.ps~fake~*~GP^us~antx.oq~other~*~GP^us~ant.oq~anthropic~*~GP"'
        self.assertEqual(fk.parse_tencent_smartbox_us_suffix(raw_ant, "ANT"), "OQ")
        self.assertIsNone(fk.parse_tencent_smartbox_us_suffix('v_hint="us~foo.ps~otc~*~GP"', "FOO"))

    def test_sina_cn_and_us_kline(self) -> None:
        raw_cn = json.dumps([
            {"day": "2026-11-25", "open": "765.0", "high": "772.0", "low": "743.2", "close": "752.4", "volume": "535542085"}
        ])
        self.assertEqual(
            fk.parse_sina_cn_kline(raw_cn),
            [["2026-11-25", "765.0", "772.0", "743.2", "752.4", "535542085"]],
        )
        raw_us = json.dumps([
            {"d": "2026-11-25", "o": "8302.93", "h": "8781.01", "l": "8129.23", "c": "8774.86", "v": "0"}
        ])
        self.assertEqual(
            fk.parse_sina_us_kline(raw_us),
            [["2026-11-25", "8302.93", "8781.01", "8129.23", "8774.86", "0"]],
        )

    def test_sina_global_and_inner_futures_jsonp(self) -> None:
        raw_gf = (
            "/*<script>location.href='//sina.com';</script>*/\n"
            'x([{"date":"2026-11-26","open":"3566.84","high":"3636.92","low":"3557.80","close":"3631.99","volume":"0"}]);'
        )
        self.assertEqual(
            fk.parse_sina_global_futures(raw_gf),
            [["2026-11-26", "3566.84", "3636.92", "3557.80", "3631.99", "0"]],
        )
        raw_if = (
            "/*<script>location.href='//sina.com';</script>*/\n"
            'x([{"d":"2026-11-26","o":"758.32","h":"776.28","l":"737.92","c":"767.62","v":"584368"}]);'
        )
        self.assertEqual(
            fk.parse_sina_inner_futures(raw_if),
            [["2026-11-26", "758.32", "776.28", "737.92", "767.62", "584368"]],
        )

    def test_sge_daily_reorders_open_close_low_high_and_filters_zero(self) -> None:
        # SGE raw order: [date, open, close, low, high]
        raw = json.dumps({
            "time": [
                ["2026-11-24", 778.0, 0.0, 0.0, 0.0],
                ["2026-11-25", 780.0, 757.35, 755.0, 784.0],
                ["2026-11-26", 757.8, 765.82, 736.51, 775.0],
            ]
        })
        parsed = fk.parse_sge_daily(raw)
        # Reordered: [date, open, high, low, close, 0]
        self.assertEqual(parsed[1], ["2026-11-25", 780.0, 784.0, 755.0, 757.35, 0])
        clean = fk.sanitize_bars(parsed, force_no_volume=True)
        self.assertEqual(len(clean), 2)
        self.assertEqual(clean[0], ["2026-11-25", 780.0, 784.0, 755.0, 757.35, 0])
        self.assertEqual(clean[1], ["2026-11-26", 757.8, 775.0, 736.51, 765.82, 0])

    def test_sina_fx_reorders_open_low_high_close(self) -> None:
        # FX raw pipe order: date,open,low,high,close
        raw = (
            "/*<script>location.href='//sina.com';</script>*/\n"
            'x("2026-11-25,6.6650,6.6580,6.6796,6.6678,|2026-11-26,6.6687,6.6580,6.6699,6.6613");'
        )
        parsed = fk.parse_sina_fx(raw)
        self.assertEqual(parsed[0], ["2026-11-25", "6.6650", "6.6796", "6.6580", "6.6678", 0])
        clean = fk.sanitize_bars(parsed, decimals_override=4, force_no_volume=True)
        self.assertEqual(clean[1], ["2026-11-26", 6.6687, 6.6699, 6.658, 6.6613, 0])

    def test_cboe_vix_csv(self) -> None:
        raw = "DATE,OPEN,HIGH,LOW,CLOSE\n11/24/2026,26.52,32.38,25.98,26.36\n11/25/2026,28.16,34.95,27.49,28.29\n"
        clean = fk.sanitize_bars(fk.parse_cboe_vix_csv(raw), force_no_volume=True)
        self.assertEqual(
            clean,
            [
                ["2026-11-24", 26.52, 32.38, 25.98, 26.36, 0],
                ["2026-11-25", 28.16, 34.95, 27.49, 28.29, 0],
            ],
        )

    def test_treasury_csv_nominal_and_real_reversed_to_ascending(self) -> None:
        raw_nom = (
            'Date,"2 Yr","10 Yr","30 Yr"\n'
            "11/25/2026,4.61,4.85,5.24\n"
            "11/24/2026,4.55,N/A,5.19\n"
            "11/23/2026,4.50,4.78,5.15\n"
        )
        bars_10y = fk.sanitize_bars(fk.parse_treasury_csv(raw_nom, "10 Yr"), decimals_override=2, force_no_volume=True)
        self.assertEqual(
            bars_10y,
            [
                ["2026-11-23", 4.78, 4.78, 4.78, 4.78, 0],
                ["2026-11-25", 4.85, 4.85, 4.85, 4.85, 0],
            ],
        )
        raw_real = 'Date,"5 YR","10 YR"\n11/25/2026,2.52,2.73\n11/24/2026,2.58,2.79\n'
        bars_tips = fk.sanitize_bars(fk.parse_treasury_csv(raw_real, "10 YR"), decimals_override=2, force_no_volume=True)
        self.assertEqual(bars_tips[0][0], "2026-11-24")
        self.assertEqual(bars_tips[1], ["2026-11-25", 2.73, 2.73, 2.73, 2.73, 0])

    def test_coinbase_candles_reorders_and_sorts_ascending(self) -> None:
        # Coinbase raw order (descending): [unix_ts, low, high, open, close, volume]
        # 1764028800 = 2025-11-25T00:00:00Z, 1763942400 = 2025-11-24T00:00:00Z
        raw = json.dumps([
            [1764028800, 59800.0, 61800.0, 60400.0, 61400.0, 1401.25],
            [1763942400, 57200.0, 60500.0, 59700.0, 60400.0, 2100.75],
        ])
        clean = fk.sanitize_bars(fk.parse_coinbase_candles(raw))
        self.assertEqual(
            clean,
            [
                ["2025-11-24", 59700.0, 60500.0, 57200.0, 60400.0, 2101],
                ["2025-11-25", 60400.0, 61800.0, 59800.0, 61400.0, 1401],
            ],
        )

    def test_ft_batch_and_justetf_parsers(self) -> None:
        raw_ft = json.dumps({
            "Dates": ["2026-11-24T00:00:00", "2026-11-25T00:00:00", "2026-11-26T00:00:00"],
            "Elements": [
                {
                    "Label": "VUAA",
                    "ComponentSeries": [
                        {"Type": "Open", "Values": [138.0, None, 139.6]},
                        {"Type": "High", "Values": [139.5, None, 140.3]},
                        {"Type": "Low", "Values": [137.5, None, 139.5]},
                        {"Type": "Close", "Values": [139.0, None, 140.08]},
                    ],
                },
                {
                    "Label": "IB01",
                    "ComponentSeries": [
                        {"Type": "Open", "Values": [None, 122.7, 122.78]},
                        {"Type": "Close", "Values": [122.65, 122.74, 122.78]},
                    ],
                },
                {
                    "Label": "IGLN",
                    "ComponentSeries": [
                        {"Type": "Close", "Values": [66.99, 69.23]},  # mismatched len 2 vs 3 dates -> skipped for exact refetch!
                    ],
                },
            ],
        })
        parsed = fk.parse_ft_batch_series(raw_ft)
        self.assertEqual(len(parsed["VUAA"]), 2)
        self.assertEqual(parsed["VUAA"][1], ["2026-11-26", 139.6, 140.3, 139.5, 140.08, 0])
        # Missing O/H/L filled from Close
        self.assertEqual(parsed["IB01"][0], ["2026-11-24", 122.65, 122.65, 122.65, 122.65, 0])
        # Length-mismatched element rejected to prevent date-shift corruption
        self.assertNotIn("IGLN", parsed)

        raw_je = json.dumps({
            "series": [
                {"date": "2026-11-25", "value": {"raw": 139.8}},
                {"date": "2026-11-26", "value": {"raw": 140.12}},
            ]
        })
        self.assertEqual(
            fk.parse_justetf_performance(raw_je),
            [
                ["2026-11-25", 139.8, 139.8, 139.8, 139.8, 0],
                ["2026-11-26", 140.12, 140.12, 140.12, 140.12, 0],
            ],
        )

    def test_cnbc_harmony_and_rest_quote_t0_guards(self) -> None:
        raw_harmony = json.dumps({
            "barData": {
                "priceBars": [
                    {
                        "open": "58383.4900",
                        "high": "58472.5600",
                        "low": "56502.9700",
                        "close": "57011.6200",
                        "volume": 1990653500,
                        "tradeTime": "20261125000000",
                    },
                    {
                        "open": "57429.5400",
                        "high": "58251.9300",
                        "low": "57288.1000",
                        "close": "57499.1600",
                        "volume": 1651446400,
                        "tradeTime": "20261126000000",
                    },
                ]
            }
        })
        hist = fk.parse_cnbc_harmony(raw_harmony)
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[1][0], "2026-11-26")

        # restQuote with valid T-0 (.N225), pre-open OHLC=0 (.GDAXI), same-day (.FTSE), inverted H<L (.FCHI)
        raw_quote = json.dumps({
            "FormattedQuoteResult": {
                "FormattedQuote": [
                    {
                        "symbol": ".N225",
                        "open": "57,669.79",
                        "high": "58,738.02",
                        "low": "57,447.16",
                        "last": "58,717.48",
                        "volume": "0",
                        "last_time": "2026-11-27T15:28:35.000+0900",
                    },
                    {
                        "symbol": ".GDAXI",
                        "open": "0",
                        "high": "0",
                        "low": "0",
                        "last": "25,215.52",
                        "volume": "0",
                        "last_time": "2026-11-27T08:00:00.000+0100",
                    },
                    {
                        "symbol": ".FTSE",
                        "open": "10,426.06",
                        "high": "10,636.49",
                        "low": "10,425.37",
                        "last": "10,609.30",
                        "volume": "0",
                        "last_time": "2026-11-26T16:35:00.000+0000",
                    },
                    {
                        "symbol": ".FCHI",
                        "open": "8,100.00",
                        "high": "8,050.00",
                        "low": "8,120.00",
                        "last": "8,108.74",
                        "volume": "0",
                        "last_time": "2026-11-27T10:00:00.000+0100",
                    },
                ]
            }
        })
        quotes = fk.parse_cnbc_rest_quote(raw_quote)
        self.assertIn(".N225", quotes)
        self.assertIn(".FTSE", quotes)
        # Pre-open OHLC=0 and high < low strictly rejected
        self.assertNotIn(".GDAXI", quotes)
        self.assertNotIn(".FCHI", quotes)

        # Valid newer date appends T-0 bar
        merged_new = fk.sanitize_bars(fk.merge_cnbc_t0_quote(hist, quotes[".N225"]))
        self.assertEqual(len(merged_new), 3)
        self.assertEqual(merged_new[-1], ["2026-11-27", 57669.79, 58738.02, 57447.16, 58717.48, 0])

        # Same-date quote does NOT append or overwrite last historical bar
        merged_same = fk.sanitize_bars(fk.merge_cnbc_t0_quote(hist, quotes[".FTSE"]))
        self.assertEqual(len(merged_same), 2)
        self.assertEqual(merged_same[-1][0], "2026-11-26")
        self.assertEqual(merged_same[-1][4], 57499.16)

        # Direct pre-open OHLC=0 bar passed to merge helper is also rejected
        merged_zero = fk.sanitize_bars(fk.merge_cnbc_t0_quote(hist, ["2026-11-27", 0, 0, 0, 58000, 0]))
        self.assertEqual(len(merged_zero), 2)

    def test_eastmoney_cgb_skips_null_rows(self) -> None:
        raw_cgb = json.dumps({
            "result": {
                "data": [
                    {"SOLAR_DATE": "2026-11-26 00:00:00", "EMM00588704": 1.214, "EMM00166466": 1.5912, "EMM00166469": 2.0662},
                    {"SOLAR_DATE": "2026-11-25 00:00:00", "EMM00588704": None, "EMM00166466": None, "EMM00166469": 2.061},
                    {"SOLAR_DATE": "2026-11-24 00:00:00", "EMM00588704": 1.2304, "EMM00166466": 1.5853, "EMM00166469": 2.045},
                ]
            }
        })
        bars_10y = fk.sanitize_bars(
            fk.parse_eastmoney_cgb(raw_cgb, "EMM00166466"),
            decimals_override=4,
            force_no_volume=True,
        )
        self.assertEqual(
            bars_10y,
            [
                ["2026-11-24", 1.5853, 1.5853, 1.5853, 1.5853, 0],
                ["2026-11-26", 1.5912, 1.5912, 1.5912, 1.5912, 0],
            ],
        )
        bars_30y = fk.sanitize_bars(
            fk.parse_eastmoney_cgb(raw_cgb, "EMM00166469"),
            decimals_override=4,
            force_no_volume=True,
        )
        self.assertEqual(len(bars_30y), 3)
        self.assertEqual(bars_30y[1], ["2026-11-25", 2.061, 2.061, 2.061, 2.061, 0])

    def test_csindex_perf_ohlcv_and_close_only(self) -> None:
        raw_932047 = json.dumps({
            "code": "200",
            "data": [
                {"tradeDate": "20261125", "open": 935.25, "high": 935.71, "low": 930.36, "close": 931.36, "tradingVol": 67050313.0},
                {"tradeDate": "20261126", "open": 929.73, "high": 934.3, "low": 929.05, "close": 930.45, "tradingVol": 54182565.0},
            ],
        })
        bars_tr = fk.sanitize_bars(fk.parse_csindex_perf(raw_932047))
        self.assertEqual(
            bars_tr,
            [
                ["2026-11-25", 935.25, 935.71, 930.36, 931.36, 67050313],
                ["2026-11-26", 929.73, 934.3, 929.05, 930.45, 54182565],
            ],
        )

        raw_932006 = json.dumps({
            "code": "200",
            "data": [
                {"tradeDate": "20261125", "open": None, "high": None, "low": None, "close": 680.65, "tradingVol": 67050313.0},
                {"tradeDate": "20261126", "open": None, "high": None, "low": None, "close": 679.98, "tradingVol": 54182565.0},
            ],
        })
        bars_close = fk.sanitize_bars(fk.parse_csindex_perf(raw_932006))
        self.assertEqual(
            bars_close,
            [
                ["2026-11-25", 680.65, 680.65, 680.65, 680.65, 67050313],
                ["2026-11-26", 679.98, 679.98, 679.98, 679.98, 54182565],
            ],
        )

    def test_core_taxonomy_and_counts(self) -> None:
        specs = fk.build_core_specs()
        self.assertEqual(len(specs), 68)
        by_id = {s.id: s for s in specs}
        self.assertEqual(len(by_id), 68)

        # Pure precious metals only in gold_metal (no copper)
        gold_ids = {s.id for s in specs if s.group == "gold_metal"}
        self.assertEqual(
            gold_ids,
            {"cmd_XAU", "cmd_GC", "cmd_AU0", "cmd_Au9999", "cmd_AuTD",
             "cmd_XAG", "cmd_SI", "cmd_AG0", "cmd_XPT", "cmd_AgTD"},
        )
        # Copper and new FX pairs in macro_cmd
        for cid in ("cmd_HG", "cmd_CU0", "fx_EURUSD", "fx_GBPUSD", "fx_USDHKD"):
            self.assertEqual(by_id[cid].group, "macro_cmd")
            self.assertEqual(by_id[cid].market, "宏观商品与汇率")
        # All sovereign yield curves (US + CN) and CSI REITs in rates_reits
        rates_ids = {s.id for s in specs if s.group == "rates_reits"}
        self.assertEqual(
            rates_ids,
            {"rate_US10Y", "rate_US2Y", "rate_US30Y", "rate_DFII10",
             "rate_CN2Y", "rate_CN10Y", "rate_CN30Y", "idx_932047", "idx_932006"},
        )
        for rid in rates_ids:
            self.assertEqual(by_id[rid].market, "债券与利率")
        # 9 non-US global indices
        global_ids = {s.id for s in specs if s.group == "global_index"}
        self.assertEqual(
            global_ids,
            {"idx_N225", "idx_TOPIX", "idx_GDAXI", "idx_FCHI", "idx_STOXX50E",
             "idx_FTSE", "idx_NSEI", "idx_TWII", "idx_KS11"},
        )
        # 5 HK indices including live idx_HSCI & idx_HSAHP
        hk_ids = {s.id for s in specs if s.group == "hk_index"}
        self.assertEqual(hk_ids, {"idx_hkHSI", "idx_hkHSTECH", "idx_hkHSCEI", "idx_HSCI", "idx_HSAHP"})
        self.assertTrue(by_id["idx_HSAHP"].force_no_volume)


class TestSanityFiltersAndCacheMerge(unittest.TestCase):
    def test_sanitize_bars_rejects_future_sessions_and_rounded_zero_prices(self) -> None:
        cutoff = date(2026, 11, 28)
        kept = ["2026-11-28", 1, 2, 1, 2, 0]
        rows = [
            ["2026-11-27", 0.00001, 0.00004, 0.00001, 0.00003, 0],
            kept,
            ["2026-11-29", 1, 2, 1, 2, 0],
        ]
        self.assertEqual(fk.sanitize_bars(rows, through_date=cutoff), [kept])

    def test_sanitize_bars_drops_corrupt_and_deduplicates(self) -> None:
        raw = [
            ["2026-11-20", 10.0, 11.0, 9.5, 10.5, 100],
            ["2026-11-20", 10.1, 11.2, 9.6, 10.8, 200],  # duplicate -> latest wins
            ["2026-11-21", 10.0, 9.0, 11.0, 10.5, 100],  # high < low -> drop
            ["2026-11-22", 10.0, 11.0, 9.0, 0.0, 100],  # close <= 0 -> drop
            ["2026-11-23", float("nan"), 11.0, 9.0, 10.0, 100],  # NaN -> drop
            ["2026-11-24", 10.0, float("inf"), 9.0, 10.0, 100],  # Inf -> drop
            ["bad-date", 10.0, 11.0, 9.0, 10.0, 100],  # bad date -> drop
            ["2026-11-25", 91.7, 92.51, 91.84, 92.2, 10541],  # open < low while high >= low -> clamped
        ]
        clean = fk.sanitize_bars(raw, bars_limit=10)
        self.assertEqual(len(clean), 2)
        self.assertEqual(clean[0], ["2026-11-20", 10.1, 11.2, 9.6, 10.8, 200])
        # Low clamped down to 91.7 so candlestick envelope low <= min(o,c) <= max(o,c) <= high holds
        self.assertEqual(clean[1], ["2026-11-25", 91.7, 92.51, 91.7, 92.2, 10541])

    def test_stale_while_error_merge(self) -> None:
        spec = fk.InstrumentSpec(
            "idx_sh000001", "000001", "上证指数", "a_index", "A股", "CNY", "点", "core", "cn_index", "sh000001"
        )
        cached = {
            "provider": "tencent_newfqkline",
            "bars": [
                ["2026-11-24", 3450.0, 3490.0, 3440.0, 3480.0, 100000],
                ["2026-11-25", 3480.0, 3500.0, 3460.0, 3476.88, 120000],
            ],
        }
        # Live failure with warm cache -> stale=True + failure recorded with used_stale_cache=True
        rec, fail = fk.merge_with_stale_cache(spec, [], None, "timeout", cached, bars_limit=150)
        self.assertIsNotNone(rec)
        assert rec is not None and fail is not None
        self.assertTrue(rec["stale"])
        self.assertEqual(rec["bars_count"], 2)
        self.assertEqual(rec["latest_close"], 3476.88)
        self.assertTrue(fail["used_stale_cache"])

        # Live failure without cache -> rec=None + used_stale_cache=False
        rec2, fail2 = fk.merge_with_stale_cache(spec, [], None, "http_503", None, bars_limit=150)
        self.assertIsNone(rec2)
        assert fail2 is not None
        self.assertFalse(fail2["used_stale_cache"])

        # Live success -> stale=False, fail=None
        rec3, fail3 = fk.merge_with_stale_cache(
            spec,
            [["2026-11-25", 3480.0, 3500.0, 3460.0, 3476.88, 120000]],
            "tencent_newfqkline",
            None,
            cached,
            bars_limit=150,
        )
        self.assertIsNotNone(rec3)
        self.assertIsNone(fail3)
        assert rec3 is not None
        self.assertFalse(rec3["stale"])


class TestOfflineEndToEndWorkflow(unittest.TestCase):
    def _build_mock_opener(self, *, fail_nvda: bool = False, fail_cnbc_gdaxi: bool = False):
        def opener(req, timeout=12):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "smartbox.gtimg.cn" in url:
                if "q=nvda" in url:
                    return _FakeResponse('v_hint="us~nvda.oq~nvidia~*~GP"')
                if "q=brk.b" in url:
                    return _FakeResponse('v_hint="us~brk.b.n~berkshire~*~GP"')
                if "q=voo" in url:
                    return _FakeResponse('v_hint="us~voo.am~vanguard~*~ETF"')
                return _FakeResponse('v_hint=""')

            if "usfqkline" in url:
                if fail_nvda and "usNVDA.OQ" in url:
                    raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)
                sym = url.split("param=")[1].split(",")[0]
                return _FakeResponse(json.dumps({
                    "code": 0,
                    "data": {
                        sym: {
                            "qfqday": [
                                ["2026-11-24", "140.0", "145.0", "146.0", "139.0", "5000000"],
                                ["2026-11-25", "145.5", "148.0", "149.0", "144.0", "6000000"],
                            ]
                        }
                    },
                }))

            if "US_MinKService" in url:
                if fail_nvda and "symbol=nvda" in url:
                    raise urllib.error.URLError("simulated outage")
                return _FakeResponse(json.dumps([
                    {"d": "2026-11-24", "o": "8000", "h": "8100", "l": "7950", "c": "8050", "v": "0"},
                    {"d": "2026-11-25", "o": "8060", "h": "8200", "l": "8010", "c": "8180", "v": "0"},
                ]))

            if "hkfqkline" in url:
                sym = url.split("param=")[1].split(",")[0]
                return _FakeResponse(json.dumps({
                    "code": 0,
                    "data": {
                        sym: {
                            "qfqday": [
                                ["2026-11-24", "340.0", "344.0", "349.0", "339.0", "3000000"],
                                ["2026-11-25", "344.0", "346.5", "350.0", "342.0", "3200000"],
                            ]
                        }
                    },
                }))

            if "newfqkline" in url:
                sym = url.split("param=")[1].split(",")[0]
                return _FakeResponse(json.dumps({
                    "code": 0,
                    "data": {
                        sym: {
                            "qfqday": [
                                ["2026-11-24", "3.90", "3.95", "3.98", "3.88", "20000000"],
                                ["2026-11-25", "3.95", "3.96", "3.99", "3.92", "21000000"],
                            ]
                        }
                    },
                }))

            if "CN_MarketData.getKLineData" in url:
                return _FakeResponse(json.dumps([
                    {"day": "2026-11-24", "open": "750.0", "high": "765.0", "low": "745.0", "close": "760.0", "volume": "500000"},
                    {"day": "2026-11-25", "open": "760.0", "high": "770.0", "low": "748.0", "close": "752.4", "volume": "520000"},
                ]))

            if "ts-api.cnbc.com/harmony/app/charts/1Y.json" in url:
                if fail_cnbc_gdaxi and ".GDAXI" in url:
                    raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)
                vol = 0 if ".HSCAHPI" in url else 1500000
                return _FakeResponse(json.dumps({
                    "barData": {
                        "priceBars": [
                            {"open": "1000.0", "high": "1020.0", "low": "990.0", "close": "1010.0", "volume": vol, "tradeTime": "20261125000000"},
                            {"open": "1012.0", "high": "1030.0", "low": "1005.0", "close": "1025.0", "volume": vol, "tradeTime": "20261126000000"},
                        ]
                    }
                }))

            if "quote.cnbc.com/quote-html-webservice/restQuote" in url:
                return _FakeResponse(json.dumps({
                    "FormattedQuoteResult": {
                        "FormattedQuote": [
                            {
                                "symbol": ".N225",
                                "open": "1,028.00",
                                "high": "1,042.00",
                                "low": "1,020.00",
                                "last": "1,040.00",
                                "volume": "0",
                                "last_time": "2026-11-27T15:00:00.000+0900",
                            },
                            {
                                "symbol": ".GDAXI",
                                "open": "0",
                                "high": "0",
                                "low": "0",
                                "last": "1,025.00",
                                "volume": "0",
                                "last_time": "2026-11-27T08:00:00.000+0100",
                            },
                        ]
                    }
                }))

            if "datacenter-web.eastmoney.com/api/data/v1/get" in url:
                return _FakeResponse(json.dumps({
                    "result": {
                        "data": [
                            {"SOLAR_DATE": "2026-11-26 00:00:00", "EMM00588704": 1.214, "EMM00166466": 1.5912, "EMM00166469": 2.0662},
                            {"SOLAR_DATE": "2026-11-25 00:00:00", "EMM00588704": None, "EMM00166466": None, "EMM00166469": None},
                            {"SOLAR_DATE": "2026-11-24 00:00:00", "EMM00588704": 1.2304, "EMM00166466": 1.5853, "EMM00166469": 2.045},
                        ]
                    }
                }))

            if "csindex.com.cn/csindex-home/perf/index-perf" in url:
                if "indexCode=932006" in url:
                    return _FakeResponse(json.dumps({
                        "code": "200",
                        "data": [
                            {"tradeDate": "20261125", "open": None, "high": None, "low": None, "close": 680.65, "tradingVol": 67050313.0},
                            {"tradeDate": "20261126", "open": None, "high": None, "low": None, "close": 679.98, "tradingVol": 54182565.0},
                        ],
                    }))
                return _FakeResponse(json.dumps({
                    "code": "200",
                    "data": [
                        {"tradeDate": "20261125", "open": 935.25, "high": 935.71, "low": 930.36, "close": 931.36, "tradingVol": 67050313.0},
                        {"tradeDate": "20261126", "open": 929.73, "high": 934.3, "low": 929.05, "close": 930.45, "tradingVol": 54182565.0},
                    ],
                }))

            if "markets.ft.com/data/chartapi/series" in url:
                req_body = json.loads(req.data.decode("utf-8")) if getattr(req, "data", None) else {}
                elems = []
                for el in req_body.get("elements", []):
                    elems.append({
                        "Label": el["Label"],
                        "ComponentSeries": [
                            {"Type": "Open", "Values": [138.0, 139.5]},
                            {"Type": "High", "Values": [139.5, 140.3]},
                            {"Type": "Low", "Values": [137.5, 139.0]},
                            {"Type": "Close", "Values": [139.0, 140.08]},
                        ],
                    })
                return _FakeResponse(json.dumps({
                    "Dates": ["2026-11-24T00:00:00", "2026-11-25T00:00:00"],
                    "Elements": elems,
                }))

            if "VIX_History.csv" in url:
                return _FakeResponse("DATE,OPEN,HIGH,LOW,CLOSE\n11/24/2026,26.5,32.3,25.9,26.3\n11/25/2026,28.1,34.9,27.4,28.29\n")

            if "GlobalFuturesService" in url:
                return _FakeResponse(
                    '/*c*/x([{"date":"2026-11-24","open":"3550","high":"3600","low":"3540","close":"3590","volume":"0"},'
                    '{"date":"2026-11-25","open":"3590","high":"3640","low":"3580","close":"3630","volume":"0"}]);'
                )

            if "InnerFuturesNewService" in url:
                return _FakeResponse(
                    '/*c*/x([{"d":"2026-11-24","o":"755","h":"770","l":"750","c":"765","v":"500000"},'
                    '{"d":"2026-11-25","o":"765","h":"776","l":"738","c":"767.62","v":"580000"}]);'
                )

            if "sge.com.cn/graph/Dailyhq" in url:
                return _FakeResponse(json.dumps({
                    "time": [
                        ["2026-11-24", 778.0, 777.72, 775.4, 794.5],
                        ["2026-11-25", 757.8, 765.82, 736.51, 775.0],
                    ]
                }))

            if "NewForexService" in url:
                return _FakeResponse('/*c*/x("2026-11-24,103.50,103.20,103.90,103.70,|2026-11-25,103.70,103.60,103.85,103.80");')

            if "daily_treasury_real_yield_curve" in url:
                return _FakeResponse('Date,"5 YR","10 YR"\n11/25/2026,2.52,2.73\n11/24/2026,2.58,2.79\n')

            if "daily_treasury_yield_curve" in url:
                return _FakeResponse('Date,"2 Yr","10 Yr","30 Yr"\n11/25/2026,4.61,4.85,5.24\n11/24/2026,4.55,4.78,5.19\n')

            if "api.exchange.coinbase.com" in url:
                return _FakeResponse(json.dumps([
                    [1764028800, 59800, 61800, 60400, 61400, 1401.2],
                    [1763942400, 57200, 60500, 59700, 60400, 2100.5],
                ]))

            raise AssertionError(f"Unexpected network URL in offline test: {url}")

        return opener

    def test_full_offline_pipeline_and_stale_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_dir = root / "klines"
            suffix_cache = root / "us_suffix.json"
            etf_path = root / "etfs.json"
            dd_path = root / "dossiers.json"

            etf_path.write_text(json.dumps({
                "etfs": [
                    {"code": "510300", "name": "沪深300ETF", "market": "a-share", "market_label": "中国 A 股", "channel": "境内场内", "category": "宽基核心"},
                    {"code": "159509", "name": "纳指科技ETF", "market": "us-stock", "market_label": "美国股市", "channel": "境内QDII", "category": "跨境科技"},
                    {"code": "02800", "name": "盈富基金", "market": "hk-stock", "market_label": "中国香港股市", "channel": "离岸港交所", "category": "宽基"},
                    {"code": "VOO", "name": "标普500ETF", "market": "us-stock", "market_label": "美国股市", "channel": "离岸美股", "category": "宽基"},
                    {"code": "VUAA", "name": "标普500 UCITS", "market": "us-stock", "market_label": "美国股市", "channel": "爱尔兰UCITS", "category": "宽基"},
                ]
            }, ensure_ascii=False), encoding="utf-8")

            dd_path.write_text(json.dumps({
                "dossiers": {
                    "a-share:601088": {"market": "a-share", "code": "601088", "name": "中国神华"},
                    "hk-stock:00700.HK": {"market": "hk-stock", "code": "00700.HK", "name": "腾讯控股"},
                    "us-stock:NVDA": {"market": "us-stock", "code": "NVDA", "name": "英伟达"},
                    "us-stock:BRK.B": {"market": "us-stock", "code": "BRK.B", "name": "伯克希尔B"},
                }
            }, ensure_ascii=False), encoding="utf-8")

            http1 = fk.RateLimitedHttpClient(retries=0, opener=self._build_mock_opener(fail_nvda=False))
            summary1 = fk.run_fetch(
                scope="all",
                bars_limit=150,
                edition_id="2026-11-27_0730",
                out_dir=out_dir,
                workers=4,
                etf_path=etf_path,
                dossiers_path=dd_path,
                us_suffix_cache_path=suffix_cache,
                http_client=http1,
            )

            self.assertEqual(summary1["failed_count"], 0)
            self.assertEqual(summary1["stale_count"], 0)
            self.assertEqual(summary1["omitted_optional"], [])
            # 68 core + 5 ETFs + 4 stocks = 77
            self.assertEqual(summary1["ok_count"], 77)
            self.assertEqual(summary1["total_instruments"], 77)

            # Verify US suffix cache persisted with exact suffixes
            saved_cache = json.loads(suffix_cache.read_text(encoding="utf-8"))
            self.assertEqual(saved_cache["suffixes"]["NVDA"], "OQ")
            self.assertEqual(saved_cache["suffixes"]["BRK.B"], "N")
            self.assertEqual(saved_cache["suffixes"]["VOO"], "AM")

            # Verify manifest & shard schema, permissions, and zero leaks
            manifest_raw = (out_dir / "manifest.json").read_text(encoding="utf-8")
            self.assertNotIn("/Users/", manifest_raw)
            self.assertNotIn("file://", manifest_raw)
            self.assertNotIn("NaN", manifest_raw)
            manifest = json.loads(manifest_raw)
            self.assertEqual(manifest["edition_id"], "2026-11-27_0730")
            self.assertEqual(len(manifest["catalog"]), 77)
            ids = {c["id"]: c for c in manifest["catalog"]}
            self.assertNotIn("idx_hkHSCI", ids)
            self.assertIn("idx_HSCI", ids)
            self.assertIn("idx_HSAHP", ids)
            self.assertEqual(ids["idx_HSCI"]["provider"], "cnbc_harmony")
            self.assertFalse(ids["idx_HSAHP"]["has_volume"])
            # .N225 got T-0 restQuote appended (2 hist + 1 live = 3), .GDAXI pre-open OHLC=0 rejected (2)
            self.assertEqual(ids["idx_N225"]["bars_count"], 3)
            self.assertEqual(ids["idx_N225"]["latest_date"], "2026-11-27")
            self.assertEqual(ids["idx_GDAXI"]["bars_count"], 2)
            self.assertEqual(ids["idx_GDAXI"]["latest_date"], "2026-11-26")
            self.assertEqual(ids["rate_CN10Y"]["provider"], "eastmoney_cgb")
            self.assertEqual(ids["rate_CN10Y"]["group"], "rates_reits")
            self.assertEqual(ids["rate_CN10Y"]["bars_count"], 2)
            self.assertFalse(ids["rate_CN10Y"]["has_volume"])
            self.assertEqual(ids["rate_US10Y"]["group"], "rates_reits")
            self.assertEqual(ids["rate_US10Y"]["market"], "债券与利率")
            self.assertEqual(ids["idx_932047"]["provider"], "csindex_perf")
            self.assertEqual(ids["idx_932006"]["provider"], "csindex_perf")
            self.assertTrue(ids["idx_932006"]["has_volume"])
            self.assertEqual(ids["fx_EURUSD"]["provider"], "sina_forex")
            self.assertEqual(ids["cmd_HG"]["group"], "macro_cmd")
            self.assertEqual(ids["cmd_CU0"]["group"], "macro_cmd")
            self.assertEqual(ids["stk_BRK.B"]["dossier_key"], "us-stock:BRK.B")
            self.assertEqual(ids["etf_VUAA"]["shard"], "etfs_offshore")
            self.assertEqual(ids["etf_VUAA"]["provider"], "ft_chartapi")
            self.assertFalse(ids["idx_VIX"]["has_volume"])
            self.assertFalse(ids["rate_US10Y"]["has_volume"])
            self.assertTrue(ids["crypto_BTC"]["has_volume"])

            for fn in ("manifest.json", "core.json", "etfs_onshore.json", "etfs_crossborder.json",
                       "etfs_offshore.json", "stocks_a.json", "stocks_hk.json", "stocks_us.json"):
                fp = out_dir / fn
                self.assertTrue(fp.exists(), f"Missing {fn}")
                mode = stat.S_IMODE(os.stat(fp).st_mode)
                self.assertEqual(mode, 0o644)

            # Second run: simulate NVDA total outage -> stale-while-error preserves NVDA bars!
            http2 = fk.RateLimitedHttpClient(retries=0, opener=self._build_mock_opener(fail_nvda=True))
            summary2 = fk.run_fetch(
                scope="stocks",
                bars_limit=150,
                edition_id="2026-11-27_1800",
                out_dir=out_dir,
                workers=4,
                etf_path=etf_path,
                dossiers_path=dd_path,
                us_suffix_cache_path=suffix_cache,
                http_client=http2,
            )
            # Partial scope="stocks" must preserve core + etfs in manifest!
            self.assertEqual(summary2["ok_count"], 77)
            self.assertEqual(summary2["stale_count"], 1)
            self.assertEqual(summary2["failed_count"], 0)
            self.assertEqual(len(summary2["partial_failures"]), 1)
            self.assertEqual(summary2["partial_failures"][0]["id"], "stk_NVDA")
            self.assertTrue(summary2["partial_failures"][0]["used_stale_cache"])

            stocks_us = json.loads((out_dir / "stocks_us.json").read_text(encoding="utf-8"))
            self.assertTrue(stocks_us["series"]["stk_NVDA"]["stale"])
            self.assertEqual(stocks_us["series"]["stk_NVDA"]["bars_count"], 2)

            # Third run: simulate CNBC failure on .GDAXI -> falls back cleanly to ft_chartapi
            http3 = fk.RateLimitedHttpClient(retries=0, opener=self._build_mock_opener(fail_cnbc_gdaxi=True))
            summary3 = fk.run_fetch(
                scope="core",
                bars_limit=150,
                edition_id="2026-11-27_1800",
                out_dir=out_dir,
                workers=4,
                etf_path=etf_path,
                dossiers_path=dd_path,
                us_suffix_cache_path=suffix_cache,
                http_client=http3,
            )
            self.assertEqual(summary3["failed_count"], 0)
            core_data = json.loads((out_dir / "core.json").read_text(encoding="utf-8"))
            self.assertEqual(core_data["series"]["idx_GDAXI"]["provider"], "ft_chartapi")
            self.assertFalse(core_data["series"]["idx_GDAXI"]["stale"])


class TestWave2KlineResilienceRegressions(unittest.TestCase):
    def test_rate_dfii10_preserves_negative_real_yield_values(self) -> None:
        core_map = {sp.id: sp for sp in fk.build_core_specs()}
        dfii10 = core_map["rate_DFII10"]
        self.assertTrue(dfii10.allow_nonpositive)
        self.assertFalse(core_map["rate_US10Y"].allow_nonpositive)

        csv_text = (
            "Date,5 YR,7 YR,10 YR,20 YR,30 YR\n"
            "11/27/2026,0.10,0.20,0.00,0.40,0.50\n"
            "11/26/2026,-0.60,-0.55,-0.45,-0.10,0.15\n"
            "11/25/2026,1.10,1.15,1.25,1.40,1.55\n"
        )
        # Default allow_nonpositive=False drops <= 0; allow_nonpositive=True preserves negative & zero yields
        pos_only = fk.parse_treasury_csv(csv_text, "10 YR")
        self.assertEqual(pos_only, [["2026-11-25", 1.25, 1.25, 1.25, 1.25, 0]])

        with_neg = fk.parse_treasury_csv(csv_text, "10 YR", allow_nonpositive=True)
        sanitized = fk.sanitize_bars(
            with_neg,
            decimals_override=dfii10.decimals_override,
            force_no_volume=True,
            allow_nonpositive=True,
        )
        self.assertEqual(
            sanitized,
            [
                ["2026-11-25", 1.25, 1.25, 1.25, 1.25, 0],
                ["2026-11-26", -0.45, -0.45, -0.45, -0.45, 0],
                ["2026-11-27", 0.0, 0.0, 0.0, 0.0, 0],
            ],
        )

        # Stale cache fallback also preserves negative real yields cleanly
        rec, fail = fk.merge_with_stale_cache(
            dfii10,
            [],
            None,
            "simulated_timeout",
            {"provider": "us_treasury_csv", "bars": sanitized},
            bars_limit=150,
        )
        self.assertIsNotNone(rec)
        self.assertIsNotNone(fail)
        assert rec is not None
        self.assertEqual([b[4] for b in rec["bars"]], [1.25, -0.45, 0.0])

    def test_load_etf_specs_skips_otc_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            etf_path = Path(tmp) / "etf_universe.json"
            etf_path.write_text(
                json.dumps(
                    {
                        "etfs": [
                            {"code": "008142", "name": "国泰黄金ETF联接A", "channel": "境内场外", "market": "gold"},
                            {"code": "510300", "name": "华泰柏瑞沪深300ETF", "channel": "境内场内", "market": "a-share"},
                            {"code": "513500", "name": "博时标普500ETF", "channel": "境内QDII", "market": "us-stock"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            specs = fk.load_etf_specs(etf_path)
            ids = [sp.id for sp in specs]
            self.assertNotIn("etf_008142", ids)
            self.assertEqual(ids, ["etf_510300", "etf_513500"])

    def test_weekend_cnbc_quotes_rejected_and_usdhkd_parsed_via_sina_fx(self) -> None:
        cnbc_payload = json.dumps(
            {
                "FormattedQuoteResult": {
                    "FormattedQuote": [
                        {
                            "symbol": ".GDAXI",
                            "last_time": "2026-11-28T10:00:00Z",  # Saturday -> MUST be rejected
                            "open": "23000", "high": "23100", "low": "22900", "last": "23050",
                        },
                        {
                            "symbol": ".N225",
                            "last_time": "2026-11-29T05:00:00Z",  # Sunday -> MUST be rejected
                            "open": "50000", "high": "50200", "low": "49900", "last": "50100",
                        },
                        {
                            "symbol": ".FTSE",
                            "last_time": "2026-11-27T16:30:00Z",  # Friday -> valid weekday
                            "open": "9000", "high": "9050", "low": "8980", "last": "9025",
                        },
                    ]
                }
            }
        )
        parsed = fk.parse_cnbc_rest_quote(cnbc_payload)
        self.assertNotIn(".GDAXI", parsed)
        self.assertNotIn(".N225", parsed)
        self.assertEqual(parsed[".FTSE"], ["2026-11-27", 9000.0, 9050.0, 8980.0, 9025.0, 0])

        hist = [["2026-11-27", 9000.0, 9050.0, 8980.0, 9020.0, 12345.0]]
        # Weekend bar rejected even when newer than last_hist_date
        self.assertEqual(
            fk.merge_cnbc_t0_quote(hist, ["2026-11-28", 9010.0, 9060.0, 8990.0, 9040.0, 0]),
            hist,
        )
        self.assertEqual(
            fk.merge_cnbc_t0_quote(hist, ["2026-11-29", 9010.0, 9060.0, 8990.0, 9040.0, 0]),
            hist,
        )
        # Same-day weekday refresh replaces in place & preserves historical volume when T-0 vol=0
        refreshed = fk.merge_cnbc_t0_quote(
            hist,
            ["2026-11-27", 9000.0, 9055.0, 8980.0, 9035.0, 0],
            allow_same_day=True,
        )
        self.assertEqual(refreshed, [["2026-11-27", 9000.0, 9055.0, 8980.0, 9035.0, 12345.0]])

        # fx_USDHKD parsed cleanly via parse_sina_fx_quotes, including fallback to parts[1] when parts[8] is empty/0
        raw_fx = (
            'var hq_str_fx_susdhkd="15:30:00,7.7812,7.7815,7.7805,12,7.7808,7.7830,7.7795,0.0000,美元兑港元,0.01,0.0007,0.0003,,7.85,7.75,,2026-11-27";\n'
        )
        fx_parsed = fk.parse_sina_fx_quotes(raw_fx)
        self.assertIn("fx_susdhkd", fx_parsed)
        self.assertEqual(fx_parsed["fx_susdhkd"], ["2026-11-27", 7.7808, 7.783, 7.7795, 7.7812, 0])


if __name__ == "__main__":
    unittest.main()
