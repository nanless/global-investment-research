from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_site, edition_run, install_sidecars, lint_site


class EditionRunTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        repository = patch.object(edition_run, "ROOT", self.root)
        repository.start()
        self.addCleanup(repository.stop)
        self.git("init", "-q")
        for relative in edition_run.GOLD_HISTORY_LEDGERS:
            ledger = self.root / relative
            ledger.parent.mkdir(parents=True, exist_ok=True)
            ledger.write_text("## Previous edition\n\n- Original evidence\n", encoding="utf-8")
        self.git("add", "gold")
        self.git("commit", "-qm", "Previous deployment")
        self.runs = edition_run.open_runs()
        self.addCleanup(self.runs.close)
        self.edition = "2026-11-26_1800"

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", *args],
            cwd=self.root, capture_output=True, text=True, check=True,
        ).stdout.strip()

    def reach_equity(self):
        token = edition_run.begin(self.runs, self.edition)
        with self.runs:
            edition_run.advance(self.runs, token, "gold")
        for name in ("gold/data_snapshot.json", "equity/state/market_state.json"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"edition_id": self.edition}))
        with self.runs:
            edition_run.advance(self.runs, token, "equity")
        return token

    def write_review(self, name, review):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"runs": [review]}), encoding="utf-8")

    def reach_publish(self):
        token = self.reach_equity()
        with self.assertRaisesRegex((OSError, ValueError), "rsi_metrics.json"), self.runs:
            edition_run.advance(self.runs, token, "publish")
        for name in ("gold/daily/rsi_metrics.json", "equity/state/rsi_metrics.json"):
            self.write_review(name, {
                "run_id": self.edition,
                "review_closure": {"reviewer_completed": True, "findings": []},
            })
        with self.runs:
            edition_run.advance(self.runs, token, "publish")
        return token

    def committed_edition(self):
        self.git("add", "gold", "equity")
        self.git("commit", "-qm", "Current edition")
        return self.git("rev-parse", "HEAD")

    def test_receipt_is_required_and_bound_to_edition_not_head(self):
        token = self.reach_publish()
        with self.assertRaisesRegex(ValueError, "No verified"):
            edition_run.complete(self.runs, token, wait=0)
        previous = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "existed before"):
            edition_run.record_push(token, sha=previous, repository="example/project")
        sha = self.committed_edition()
        edition_run.record_push(token, sha=sha, repository="example/project")
        with self.assertRaisesRegex(ValueError, "all 16"):
            edition_run.record_publication(token, sha=sha, repository="example/project", assets={})
        assets = {name: "c" * 64 for name in edition_run.EXPECTED_ASSETS}
        edition_run.record_publication(token, sha=sha, repository="example/project", assets=assets)
        self.git("commit", "--allow-empty", "-qm", "Unrelated later local HEAD")
        with patch.object(edition_run, "verify_pages", return_value="https://example.invalid/run") as deploy:
            with patch.object(edition_run, "verify_downloads") as downloads, self.runs:
                self.assertEqual(edition_run.complete(self.runs, token), "https://example.invalid/run")
            downloads.assert_called_once_with("example/project", assets)
        deploy.assert_called_once_with(sha, "example/project", 180)
        self.assertEqual(edition_run.status(self.runs)[0]["status"], "complete")

    def test_candidate_preserves_the_actual_gold_ledger_history(self):
        originals = {}
        for relative in edition_run.GOLD_HISTORY_LEDGERS:
            source = Path(__file__).resolve().parents[1] / relative
            originals[relative] = source.read_bytes()
            (self.root / relative).write_bytes(originals[relative])
        self.git("add", "gold")
        self.git("commit", "-qm", "Existing Gold ledger history")
        token = self.reach_publish()

        for relative, content in originals.items():
            ledger = self.root / relative
            lines = [line for line in content.split(b"\n") if line.strip()]
            changes = {
                "truncated tail": lines[:-1],
                "overwritten old line": [*lines[:-1], b"Overwritten evidence"],
                "reordered old lines": [lines[1], lines[0], *lines[2:]],
            }
            for problem, changed_lines in changes.items():
                with self.subTest(ledger=relative, problem=problem):
                    ledger.write_bytes(b"\n".join(changed_lines) + b"\n")
                    candidate = self.committed_edition()
                    ledger.write_bytes(content)
                    with self.assertRaisesRegex(ValueError, f"{Path(relative).stem}.*preserve"):
                        edition_run.check_publication_candidate(token, sha=candidate, repository="example/project")
            ledger.write_bytes(b"## New edition\n\n" + b"\n".join(lines) + b"\n")

        candidate = self.committed_edition()
        edition_run.check_publication_candidate(token, sha=candidate, repository="example/project")

    def test_publish_phase_accepts_only_completed_blind_review_and_closed_findings(self):
        token = self.reach_equity()
        gold = "gold/daily/rsi_metrics.json"
        equity = "equity/state/rsi_metrics.json"
        resolved = {"description": "The chart used yesterday's percentage", "status": "resolved",
                    "evidence": "Replaced the chart value and passed the strict manuscript check"}
        pending = {"description": "The first-party daily file is pending", "status": "deferred_data",
                   "evidence": {"source": "https://example.invalid/daily.csv", "due_edition": "2026-11-27_0730",
                                "disposition": "The missing official daily value was omitted from the chart"}}
        valid = {"reviewer_completed": True, "findings": [resolved, pending]}
        self.write_review(gold, {"run_id": self.edition, "review_closure": valid})
        cases = (
            (None, "reviewer_completed"),
            ({**valid, "reviewer_completed": 1}, "reviewer_completed"),
            ({**valid, "findings": None}, "findings list"),
            ({**valid, "findings": [{**resolved, "status": "open"}]}, "must be resolved"),
            ({**valid, "findings": [{**resolved, "description": " "}]}, "requires a description"),
            ({**valid, "findings": [{**resolved, "evidence": " "}]}, "evidence of resolution"),
            ({**valid, "findings": [{**pending, "evidence": "Maybe next time"}]}, "future due_edition"),
            ({**valid, "findings": [{**pending, "evidence": {**pending["evidence"], "due_edition": self.edition}}]},
             "future due_edition"),
            ({**valid, "findings": [{**pending, "evidence": {**pending["evidence"], "source": "file:///tmp/daily.csv"}}]},
             "source URL"),
            ({**valid, "findings": [{**pending, "evidence": {**pending["evidence"], "disposition": " "}}]},
             "disposition"),
        )
        for closure, error in cases:
            with self.subTest(closure=closure):
                self.write_review(equity, {"run_id": self.edition, "review_closure": closure})
                with self.assertRaisesRegex(ValueError, f"equity/state/rsi_metrics.json.*{error}"), self.runs:
                    edition_run.advance(self.runs, token, "publish")
        self.write_review(equity, {"run_id": self.edition, "review_closure": valid})
        with self.runs:
            self.assertEqual(edition_run.advance(self.runs, token, "publish"), "publish")

    def test_publication_candidate_checks_committed_review_closure(self):
        token = self.reach_publish()
        gold = "gold/daily/rsi_metrics.json"
        finalized = (self.root / gold).read_bytes()
        self.write_review(gold, {"run_id": self.edition, "review_closure": {
            "reviewer_completed": True, "findings": [{"description": "Unresolved", "status": "open", "evidence": " "}],
        }})
        dirty = self.committed_edition()
        (self.root / gold).write_bytes(finalized)
        with self.assertRaisesRegex(ValueError, "gold/daily/rsi_metrics.json.*must be resolved"):
            edition_run.check_publication_candidate(token, sha=dirty, repository="example/project")
        valid = self.committed_edition()
        edition_run.check_publication_candidate(token, sha=valid, repository="example/project")

    def test_replayed_r3_keeps_the_existing_review_format(self):
        edition = "2026-11-25_1800_r3"
        for name in ("gold/daily/rsi_metrics.json", "equity/state/rsi_metrics.json"):
            self.write_review(name, {"run_id": edition})
        edition_run.check_edition_reviews(edition, root=self.root)

    def test_old_recovery_does_not_release_reopened_attempt(self):
        original = edition_run.begin(self.runs, self.edition)
        with self.runs:
            edition_run.fail(self.runs, self.edition, "Confirmed stopped", attempt=original[:12])
        replacement = edition_run.begin(self.runs, self.edition)
        with self.assertRaisesRegex(ValueError, "no longer active"), self.runs:
            edition_run.fail(self.runs, self.edition, "Delayed request", attempt=original[:12])
        self.assertEqual(edition_run.status(self.runs)[0]["attempt"], replacement[:12])
        self.assertEqual(edition_run.status(self.runs)[0]["status"], "running")
        with self.assertRaisesRegex(ValueError, "owns publication"):
            edition_run.assert_manual_publish_allowed()

    def test_skip_advance_wrong_edition_and_legacy_row(self):
        with self.runs:
            self.runs.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("a" * 32, "2026-11-25_1800_r2", "publish", "complete", "before", "before", "legacy"),
            )
        token = edition_run.begin(self.runs, self.edition)
        with self.assertRaisesRegex(ValueError, "Cannot advance"), self.runs:
            edition_run.advance(self.runs, token, "publish")
        with self.runs:
            edition_run.advance(self.runs, token, "gold")
        path = self.root / "gold" / "data_snapshot.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text('{"edition_id":"2026-11-25_1800_r2"}')
        with self.assertRaisesRegex(ValueError, "does not belong"), self.runs:
            edition_run.advance(self.runs, token, "equity")
        self.assertEqual(edition_run.status(self.runs)[1]["source"], "legacy")

    def test_recover_preserves_unrecorded_push_attempt(self):
        token = self.reach_publish()
        intent = edition_run.push_intent_path(edition_run.git_directory(), token)
        intent.write_text(json.dumps({
            "edition": self.edition, "sha": self.committed_edition(), "repository": "example/project",
        }))
        with self.assertRaisesRegex(ValueError, "Resume this publication"):
            edition_run.fail(self.runs, self.edition, "Remote result unknown", attempt=token[:12])
        self.assertEqual(edition_run.resume(self.runs, self.edition, token[:12]), token)

    def test_only_real_pages_deploy_ok(self):
        sha = "a" * 40
        run = {"databaseId": 4, "headSha": sha, "headBranch": "main", "status": "completed", "url": "fixture"}
        detail = {**run, "jobs": [{"name": edition_run.DEPLOY_JOB, "conclusion": "skipped"}]}
        with patch.object(edition_run, "_gh_json", side_effect=[[run], detail]):
            with self.assertRaisesRegex(ValueError, "deploy job did not succeed"):
                edition_run.verify_pages(sha, "example/project", wait=0)
        with patch.object(edition_run, "_gh_json", return_value=[{**run, "headBranch": "feature"}]):
            with self.assertRaises(edition_run.DeploymentPending):
                edition_run.verify_pages(sha, "example/project", wait=0)

    def test_release_drift_blocks_complete(self):
        assets = {name: "c" * 64 for name in edition_run.EXPECTED_ASSETS}
        remote = [{"name": name, "digest": f"sha256:{digest}"} for name, digest in assets.items()]
        remote[-1]["digest"] = "sha256:" + "d" * 64
        with patch.object(edition_run, "_gh_json", return_value={"assets": remote}):
            with self.assertRaisesRegex(ValueError, "Public downloads differ"):
                edition_run.verify_downloads("example/project", assets)

    def test_stale_unpushed_lock_auto_reaped_but_pushed_preserved(self):
        old_edition = "2026-11-26_0730"
        token = edition_run.begin(self.runs, old_edition)
        # 1. Active (<2h) lock is NOT reaped
        self.assertIsNone(edition_run.reap_stale_unpushed_run(self.runs, self.edition))
        self.assertEqual(edition_run.status(self.runs)[0]["status"], "running")

        # Backdate updated timestamp > 2h
        stale_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(timespec="seconds")
        with self.runs:
            self.runs.execute("UPDATE runs SET updated = ? WHERE token = ?", (stale_ts, token))

        # 2. Same-edition lock is NOT reaped
        self.assertIsNone(edition_run.reap_stale_unpushed_run(self.runs, old_edition))
        self.assertEqual(edition_run.status(self.runs)[0]["status"], "running")

        # 3. Lock with a push-intent file is NEVER reaped
        intent = edition_run.push_intent_path(edition_run.git_directory(), token)
        intent.write_text(json.dumps({"edition": old_edition, "sha": "a" * 40, "repository": "example/project"}))
        self.assertIsNone(edition_run.reap_stale_unpushed_run(self.runs, self.edition))
        self.assertEqual(edition_run.status(self.runs)[0]["status"], "running")
        intent.unlink()

        # 4. Inactive (>2h) unpushed older-edition lock IS auto-reaped
        with redirect_stderr(StringIO()) as notice:
            reaped = edition_run.reap_stale_unpushed_run(self.runs, self.edition)
        self.assertEqual(reaped, old_edition)
        self.assertIn("Auto-reaped stale unpushed run", notice.getvalue())
        self.assertEqual(edition_run.status(self.runs)[0]["status"], "failed")

        # 5. Lock with a publications row is NEVER reaped even when >2h stale
        pub_token = self.reach_publish()
        sha = self.committed_edition()
        edition_run.record_push(pub_token, sha=sha, repository="example/project")
        with self.runs:
            self.runs.execute("UPDATE runs SET updated = ? WHERE token = ?", (stale_ts, pub_token))
        self.assertIsNone(edition_run.reap_stale_unpushed_run(self.runs, "2026-11-27_0730"))
        self.assertEqual(edition_run.status(self.runs)[0]["status"], "running")

    def test_disclosed_caveat_and_gold_ledger_monthly_rollover(self):
        token = self.reach_equity()
        gold_metrics = "gold/daily/rsi_metrics.json"
        equity_metrics = "equity/state/rsi_metrics.json"
        self.write_review(gold_metrics, {
            "run_id": self.edition,
            "review_closure": {"reviewer_completed": True, "findings": []},
        })
        empty_caveat = {
            "description": "Holiday thin liquidity",
            "status": "disclosed_caveat",
            "evidence": {"disposition": "   "},
        }
        self.write_review(equity_metrics, {
            "run_id": self.edition,
            "review_closure": {"reviewer_completed": True, "findings": [empty_caveat]},
        })
        with self.assertRaisesRegex(ValueError, "disclosed_caveat"), self.runs:
            edition_run.advance(self.runs, token, "publish")

        valid_caveat = {
            "description": "Holiday thin liquidity",
            "status": "disclosed_caveat",
            "evidence": {"disposition": "Explicitly disclosed in report cover and risk banner"},
        }
        self.write_review(equity_metrics, {
            "run_id": self.edition,
            "review_closure": {"reviewer_completed": True, "findings": [valid_caveat]},
        })
        with self.runs:
            self.assertEqual(edition_run.advance(self.runs, token, "publish"), "publish")

        audit = self.root / "gold/daily/AUDIT_LOG.md"
        prior_text = "## 2026-11-25 18:00\n\n- Entry 2\n\n## 2026-11-24 18:00\n\n- Entry 1\n"
        audit.write_text(prior_text, encoding="utf-8")
        self.git("add", "gold")
        self.git("commit", "-qm", "November audit entries")
        base = self.git("rev-parse", "HEAD")

        archive_file = self.root / "gold/daily/archive/AUDIT_LOG_2026_11.md"
        archive_file.parent.mkdir(parents=True, exist_ok=True)
        archive_file.write_text(prior_text, encoding="utf-8")
        audit.write_text("## 2026-12-01 07:30\n\n- December opening entry\n", encoding="utf-8")
        self.git("add", "gold")
        self.git("commit", "-qm", "Monthly rollover into archive")
        rolled = self.git("rev-parse", "HEAD")
        edition_run._check_gold_ledger_history(base, rolled)

        archive_file.write_text("## 2026-11-25 18:00\n\n- Entry 2\n", encoding="utf-8")
        self.git("add", "gold")
        self.git("commit", "-qm", "Drop prior archived line")
        dropped = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "AUDIT_LOG.*preserve"):
            edition_run._check_gold_ledger_history(base, dropped)

    def test_verify_pages_tolerates_transient_api_error_and_checks_all_runs(self):
        sha = "b" * 40
        failed_run = {
            "databaseId": 10, "headSha": sha, "headBranch": "main",
            "status": "completed", "url": "https://example.invalid/runs/10",
        }
        ok_run = {
            "databaseId": 11, "headSha": sha, "headBranch": "main",
            "status": "completed", "url": "https://example.invalid/runs/11",
        }
        failed_detail = {**failed_run, "jobs": [{"name": edition_run.DEPLOY_JOB, "conclusion": "failure"}]}
        ok_detail = {**ok_run, "jobs": [{"name": edition_run.DEPLOY_JOB, "conclusion": "success"}]}
        with patch.object(
            edition_run, "_gh_json",
            side_effect=[subprocess.CalledProcessError(1, "gh"), [failed_run, ok_run], failed_detail, ok_detail],
        ), patch.object(edition_run.time, "sleep"):
            url = edition_run.verify_pages(sha, "example/project", wait=10)
        self.assertEqual(url, ok_run["url"])


class OperationalRegressionTest(unittest.TestCase):
    def test_cockpit_labels_verified_fx_and_preserves_missing_quotes(self):
        gold = {"as_of_short": "2026-11-25 21:25", "usd_cny_1630": 6.6736, "usd_cny": 9.9999}
        for as_of, rates, label, value in (
            ("2026-11-25T21:25:00+08:00", {"usd_cnh": 6.673, "usd_cny_1630": 6.6736, "usd_hkd": 7.838},
             "美元 / 离岸人民币", "6.6730"),
            ("2026-11-25T21:25:00+08:00", {"usd_cnh": None, "usd_cny_1630": 6.6712, "usd_hkd": None},
             "美元 / 在岸人民币（16:30 收盘）", "6.6712"),
            ("2026-11-25T21:25:00+08:00", {"usd_cnh": None, "usd_cny_1630": None},
             "美元 / 在岸人民币（16:30 收盘）", "6.6736"),
            ("2026-11-25T07:30:00+08:00", {}, "美元 / 人民币", "待核"),
            ("2026-11-26T21:25:00+08:00", {}, "美元 / 人民币", "待核"),
        ):
            with self.subTest(as_of=as_of, rates=rates):
                equity = {"as_of_cst": as_of, "cross_market_linkages": {"rates_fx_chain": rates}}
                page = build_site.build_cockpit_page(gold, equity, {}, {})
                self.assertIn(f'<div class="mirror-lbl">{label}</div>', page)
                self.assertIn(f'<div class="mirror-val">{value}</div>', page)
                hkd = "7.838" if rates.get("usd_hkd") is not None else "待核"
                self.assertIn(f'美元/港元 {hkd}（紧盯 7.85）', page)
                self.assertIn(f'<div class="mirror-val">{hkd}</div>', page)
                self.assertIn("CFETS 中间价 待核", page)
                self.assertNotIn("9.9999", page)

    def test_renderer_keeps_current_and_archived_urls_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            history = root / "equity" / "daily" / "archive" / "2026-11"
            history.mkdir(parents=True)
            old = history / "2026-11-25_1800_a_share.md"
            old.write_text("original")
            (history / "2026-11-23_1630_us_stock.md").write_text("retired")
            (history.parent.parent / "2026-11-25_1800_a_share_r2.md").write_text("revision")
            with patch.multiple(build_site, GOLD_DIR=root / "gold", EQUITY_DIR=root / "equity"):
                editions, _ = build_site.discover_dailies()
                self.assertEqual([edition.slug for edition in editions],
                                 ["a-share-2026-11-25-1800", "a-share-2026-11-25-1800-r2"])
                (history.parent.parent / old.name).write_text("duplicate")
                with self.assertRaisesRegex(ValueError, "Duplicate public edition"):
                    build_site.discover_dailies()

    def test_unrelated_gold_context_cannot_hide_active_recommendation(self):
        for text, expected in (
            ("存量底仓保持，同时立即买入黄金", True),
            ("暂不买金，同时立即买入黄金", True),
            ("严禁立即买入黄金", False),
        ):
            with self.subTest(text=text):
                doc = lint_site.ParsedHtml(
                    rel_path="daily/a-share-latest.html", abs_path=Path("daily/a-share-latest.html"),
                    raw_text=text, visible_text=text,
                )
                errors = []
                lint_site._check_gold_tier0_mutex(doc, errors)
                self.assertEqual(bool(errors), expected, errors)

    def test_cockpit_handles_all_none_metrics_without_type_error(self):
        gold = {
            "as_of_short": "2026-11-26 18:00",
            "as_of_bjt": "2026年11月26日 18:00",
            "tier_code": "Tier 0",
            "new_buy_allowed": False,
            "tier1_passed": None,
            "tier1_total": None,
            "spot_gold_ny_close_usd": None,
            "spot_gold_ny_change_pct": None,
            "spot_gold_asia_open_usd": None,
            "sge_autd_night_rmb": None,
            "sge_autd_day_rmb": None,
            "dfii10_live_pct": None,
            "rmb_channels": {"bank_bar_rmb": None},
            "etf_cn": {"518880": {"close": None}},
            "vix_close": None,
            "brent_settle_usd": None,
            "brent_change_pct": None,
            "wti_settle_usd": None,
            "comex_copper_usd_lb": None,
            "comex_copper_change_pct": None,
            "btc_usd": None,
            "btc_change_pct": None,
            "usd_cny_1630": None,
        }
        equity = {
            "as_of_cst": "2026-11-26T18:00:00+08:00",
            "markets": {
                "a_share": {
                    "stock_pool_count": None,
                    "benchmark_csi300": None,
                    "benchmark_sse": None,
                    "csi300_200w": None,
                    "equity_cap_pct": None,
                    "erp_fwd_pct": None,
                    "erp_ttm_pct": None,
                    "cgb10y_pct": None,
                    "pe_ttm": None,
                    "pboc_total_net_100m": None,
                    "margin_balance_100m": None,
                },
                "hk_stock": {
                    "stock_pool_count": None,
                    "benchmark_hsi": None,
                    "benchmark_hstech": None,
                    "hsi_200d": None,
                    "offshore_equity_cap_pct": None,
                    "onshore_connect_cap_pct": None,
                    "hsahp_index": None,
                    "erp_usd_anchor_fwd_pct": None,
                    "erp_cny_anchor_fwd_pct": None,
                    "southbound_ytd_hkd_b": None,
                },
                "us_stock": {
                    "stock_pool_count": None,
                    "equity_cap_pct": None,
                    "cash_tbill_pct": None,
                    "gold_hold_pct": None,
                    "benchmark_sp500": None,
                    "sp500_high": None,
                    "tech_new_cap_pct": None,
                    "sp500_200d": None,
                    "erp_fwd_pct": None,
                    "erp_ttm_pct": None,
                    "pe_fwd": None,
                    "pe_ttm": None,
                    "us10y_pct": None,
                },
            },
            "cross_market_linkages": {
                "rates_fx_chain": {
                    "us10y_pct": None,
                    "hkma_agg_bal_hkd_100m": None,
                    "usd_jpy": None,
                    "usd_cnh": None,
                    "usd_cny_1630": None,
                    "usd_hkd": None,
                    "cfets_cny_fixing": None,
                    "hibor_1m_pct": None,
                },
                "commodity_mirror": {
                    "brent_usd": None,
                    "brent_chg_pct": None,
                    "wti_usd": None,
                    "comex_copper_usd_lb": None,
                    "comex_copper_chg_pct": None,
                    "btc_usd": None,
                    "btc_chg_pct": None,
                },
                "erp_ruler": {
                    "hsi_erp_cny_fwd_pct": None,
                    "hsi_erp_cny_ttm_pct": None,
                    "csi300_erp_fwd_pct": None,
                    "csi300_erp_ttm_pct": None,
                    "hsi_erp_usd_fwd_pct": None,
                    "hsi_erp_usd_ttm_pct": None,
                    "sp500_erp_fwd_pct": None,
                    "sp500_erp_ttm_pct": None,
                },
                "household_composite_weights": {
                    "equity_total_pct": None,
                    "convertible_bond_pct": None,
                    "bonds_and_cash_pct": None,
                    "gold_existing_hold_pct": None,
                },
                "crisis_correlation_brake": {
                    "vix_close": None,
                    "vix_intraday_high": None,
                    "vix_brake_threshold": None,
                    "usdjpy_level": None,
                    "usdjpy_3d_drop_brake_pct": None,
                    "us10y_brake_pct": None,
                    "hkma_agg_bal_brake_100m": None,
                },
            },
        }
        page = build_site.build_cockpit_page(gold, equity, {}, {})
        self.assertIn("待核", page)
        for stale in ("4,025", "23,515", "7,348", "540.78"):
            self.assertNotIn(stale, page)

    def test_gold_tier0_mutex_reports_multiple_violations_on_same_page(self):
        text = "第一条违规建议：立即买入黄金。\n第二条违规建议：趁急跌补齐黄金。"
        doc = lint_site.ParsedHtml(
            rel_path="daily/a-share-latest.html",
            abs_path=Path("daily/a-share-latest.html"),
            raw_text=text,
            visible_text=text,
        )
        errors = []
        lint_site._check_gold_tier0_mutex(doc, errors)
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(any("立即买入黄金" in err for err in errors), errors)
        self.assertTrue(any("趁急跌补齐黄金" in err for err in errors), errors)

    def test_shared_prompt_and_missing_project(self):
        root = Path(install_sidecars.__file__).resolve().parent.parent
        templates = dict(install_sidecars.discover_templates(root / "automations" / "sidecars"))
        rendered = {name: install_sidecars.render_template(path, root, "/usr/bin/python3")
                    for name, path in templates.items()}
        for name, (_, definition) in rendered.items():
            slot = "1800" if name.endswith("evening") else "0730"
            self.assertIn(f"begin --scheduled {slot}", definition["args"][-1])
            self.assertIn("publish_site.py --edition-token", definition["args"][-1])
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            registry = base / "config.json"
            entries = {}
            (base / "projects").mkdir()
            for idx, (name, (_, definition)) in enumerate(rendered.items()):
                project_id = f"fixture-{idx}"
                grants = definition["agent_permissions"]
                entries[name] = {
                    "enabled": True, "projectId": project_id,
                    "resolvedPermissions": {"workspaceUris": grants["workspace_uris"],
                                            "accessGrants": grants["access_grants"]},
                }
                payload = {
                    "id": project_id, "sidecar": {"sidecarId": name},
                    "projectResources": {"resources": [{"folderUri": root.as_uri()}]},
                    "permissionGrants": {"permissionGrants": {"allow": grants["access_grants"]}},
                    "settings": {"sandboxMode": False},
                }
                (base / "projects" / f"{project_id}.json").write_text(json.dumps(payload))
            registry.write_text(json.dumps({"sidecars": entries}))
            notes = []
            self.assertEqual(install_sidecars.check_registry(registry, rendered, notes), [])
            self.assertEqual(len(notes), 2)
            (base / "projects" / "fixture-0.json").unlink()
            self.assertIn("cannot verify", install_sidecars.check_registry(registry, rendered)[0])

    def test_collect_data_caveats_sanitizes_internal_paths_and_filters_by_market(self):
        gold_snap = {
            "data_caveats": [
                {
                    "id": "gold_explicit_item",
                    "market": "gold",
                    "category": "delayed_official",
                    "severity": "info",
                    "item": "伦敦金定盘与 data_snapshot.json 核销",
                    "detail": "参考 /Users/alice/secret.csv 与 file:///tmp/VIX_History.csv 核对 **官源** `audit_ledger.md`",
                    "impact": "不影响红灯结论",
                    "next_review": "2026-11-26_1800",
                }
            ],
            "vix_daily_row_checks": {
                "2026-11-25": {
                    "status": "provisional_close",
                    "note": "Cboe 官方历史 CSV（VIX_History.csv）仍止于 11/24，暂采官网收盘 28.29。",
                }
            },
        }
        eq_state = {
            "data_caveats": [
                {
                    "id": "us_provisional",
                    "market": "us_stock",
                    "category": "provisional_close",
                    "severity": "high",
                    "item": "美股盘后终盘待封账",
                    "detail": "来自 market_state.json 的挂账",
                    "impact": "次级复核项",
                    "next_review": "2026-11-27_0730",
                }
            ],
            "pending_backfills": [
                {
                    "market": "a_share",
                    "item": "11/25 两融终值（参考 build_site.py）",
                    "due_session": "2026-11-26_1800",
                },
                {
                    "market": "us_stock",
                    "item": "应被已有美股显式挂账跳过",
                    "due_session": "2026-11-26_1800",
                },
            ],
            "publication_exceptions": [
                {
                    "market": "cross",
                    "title": "感恩节休市编排",
                    "detail": "美股切守望刊，其他三市照常",
                }
            ],
        }
        all_caveats = build_site.collect_data_caveats(gold_snap, eq_state)
        self.assertEqual(all_caveats[0]["severity"], "high")
        self.assertEqual(all_caveats[0]["market"], "us-stock")
        self.assertEqual(all_caveats[0]["due_label"], "预计 11/27 07:30 早报核销")
        titles = [c["title"] for c in all_caveats]
        self.assertTrue(any("恐慌指数" in t for t in titles))
        self.assertTrue(any("两融终值" in t for t in titles))
        self.assertFalse(any("应被已有美股显式挂账跳过" in t for t in titles))

        joined = " ".join(f"{c['title']} {c['detail']} {c['impact']}" for c in all_caveats)
        for leak in ("VIX_History.csv", "data_snapshot.json", "market_state.json", "audit_ledger.md", "build_site.py", "file://", "/Users/", "**", "`"):
            self.assertNotIn(leak, joined)

        gold_only = build_site.collect_data_caveats(gold_snap, eq_state, market="gold")
        self.assertTrue(all(c["market"] in ("gold", "cross") for c in gold_only))
        self.assertTrue(any(c["market"] == "cross" for c in gold_only))

    def test_extract_all_stocks_parses_numeric_fields_cleanly(self):
        a_md = (
            "### 5.2\n"
            "| 标的 | 现价 | 估值 | 锚 | 结论 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 招商银行 `600036` | 43.32 | 7.3x | 安全锚：40.00–42.00 元 | 🟢 当下底座 |\n"
            "### 5.3\n"
            "## 附表二\n"
            "| 赛道 | 标的 | 价格 | 估值 | 诊断 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 银行 | 招商银行 `600036` | 43.32（11/25 收） | 7.3x / 0.92x / 4.7% / -5.0% | 🟢 当下底座；派息率 35% |\n"
        )
        hk_md = (
            "## 附表二\n"
            "| 赛道 | 标的 | 价格 | 估值 | 诊断 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 能源 | 中国海油 `00883` | 18.50（1,000 股） | TTM PE 6.8x / 6.2% / 无 A 股 | 🟢 当下底座；锚 17.0 下 |\n"
        )
        us_md = (
            "## 附表二\n"
            "| 赛道 | 标的 | 价格 | 估值 | 诊断 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 矿业 | **纽蒙特** `NEM` | $99.95 (-0.77%) | FWD PE 10.7x · 🟡 观察（禁新买） | 股息 2.5%，存量稳拿；锚 $85–$90 |\n"
        )
        stocks = build_site.extract_all_stocks(
            a_md,
            hk_md,
            us_md,
            ah_benchmarks=[{"name": "中国海油", "a": "600938", "h": "00883.HK", "ah_premium_pct": 69.2}],
        )
        by_code = {s["code"]: s for s in stocks}
        self.assertEqual(by_code["600036"]["price_num"], 43.32)
        self.assertEqual(by_code["600036"]["pe_num"], 7.3)
        self.assertEqual(by_code["600036"]["div_pct"], 4.7)
        self.assertEqual(by_code["600036"]["ah_pct"], -5.0)
        self.assertEqual(by_code["600036"]["anchor_low"], 40.0)
        self.assertEqual(by_code["600036"]["anchor_high"], 42.0)
        self.assertEqual(by_code["600036"]["anchor_gap_pct"], 5.7)
        self.assertFalse(by_code["600036"]["is_gold_locked"])

        self.assertEqual(by_code["00883.HK"]["pe_num"], 6.8)
        self.assertEqual(by_code["00883.HK"]["div_pct"], 6.2)
        self.assertEqual(by_code["00883.HK"]["ah_pct"], 69.2)
        self.assertEqual(by_code["00883.HK"]["anchor_gap_pct"], 8.8)

        self.assertEqual(by_code["NEM"]["price_num"], 99.95)
        self.assertEqual(by_code["NEM"]["pe_num"], 10.7)
        self.assertEqual(by_code["NEM"]["div_pct"], 2.5)
        self.assertEqual(by_code["NEM"]["anchor_low"], 85.0)
        self.assertEqual(by_code["NEM"]["anchor_high"], 90.0)
        self.assertTrue(by_code["NEM"]["is_gold_locked"])

        for st in stocks:
            for k in ("market", "market_label", "sector", "name", "code", "price", "valuation", "color", "action_label", "summary"):
                self.assertIsInstance(st[k], str)
                self.assertNotIn("**", st[k])
                self.assertNotIn("`", st[k])


if __name__ == "__main__":
    unittest.main()
