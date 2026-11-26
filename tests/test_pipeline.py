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
        self.git("commit", "--allow-empty", "-qm", "Unrelated later local HEAD")
        with patch.object(edition_run, "verify_pages", return_value="https://example.invalid/run") as deploy, self.runs:
            self.assertEqual(edition_run.complete(self.runs, token), "https://example.invalid/run")
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

    def test_reconcile_previous_deployment_completes_recorded_push(self):
        token = self.reach_publish()
        sha = self.committed_edition()
        edition_run.record_push(token, sha=sha, repository="example/project")
        with patch.object(edition_run, "verify_pages", return_value="https://example.invalid/pages") as deploy, self.runs:
            url = edition_run.reconcile_previous_deployment(self.runs)
        self.assertEqual(url, "https://example.invalid/pages")
        deploy.assert_called_once_with(sha, "example/project", 0)
        self.assertEqual(edition_run.status(self.runs)[0]["status"], "complete")

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

    def test_reap_preserves_newer_revision_and_completed_next_edition(self):
        stale_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(timespec="seconds")

        # 1. Newer revision (0730_r2) must NOT be reaped by base slot (0730)
        rev_token = edition_run.begin(self.runs, "2026-11-26_0730_r2")
        with self.runs:
            self.runs.execute("UPDATE runs SET updated = ? WHERE token = ?", (stale_ts, rev_token))
        self.assertIsNone(edition_run.reap_stale_unpushed_run(self.runs, "2026-11-26_0730"))
        self.assertEqual(edition_run.status(self.runs)[0]["status"], "running")

        # Release revision lock cleanly so we can test next_edition already complete
        with self.runs:
            edition_run.fail(self.runs, rev_token, "Test cleanup")

        # 2. If next_edition is already complete, an older stale lock must NOT be reaped
        with self.runs:
            self.runs.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("f" * 32, self.edition, "publish", "complete", stale_ts, stale_ts, "done"),
            )
        older_token = edition_run.begin(self.runs, "2026-11-26_0730")
        with self.runs:
            self.runs.execute("UPDATE runs SET updated = ? WHERE token = ?", (stale_ts, older_token))
        self.assertIsNone(edition_run.reap_stale_unpushed_run(self.runs, self.edition))
        running_rows = [r for r in edition_run.status(self.runs) if r["status"] == "running"]
        self.assertEqual(len(running_rows), 1)
        self.assertEqual(running_rows[0]["edition"], "2026-11-26_0730")

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

    def test_gold_ledger_rollover_with_standing_bottom_summary_table(self):
        audit = self.root / "gold/daily/AUDIT_LOG.md"
        header = "# 黄金研报体系·审计账本\n\n> 档案定位说明\n"
        nov_entries = (
            "## 2026-11-26 08:30\n\n- Nov 26 audit note\n\n"
            "## 2026-11-25 18:00\n\n- Nov 25 audit note\n"
        )
        standing_table = (
            "## 一、三大信任资产全景汇总\n\n"
            "| 编号 | 误区 | 真相 |\n"
            "| :---: | :--- | :--- |\n"
            "| 1 | 谣言甲 | 官源核查甲 |\n"
            "| 2 | 谣言乙 | 官源核查乙 |\n"
        )
        audit.write_text(f"{header}\n{nov_entries}\n{standing_table}", encoding="utf-8")
        self.git("add", "gold")
        self.git("commit", "-qm", "November audit with standing summary table")
        base = self.git("rev-parse", "HEAD")

        archive_file = self.root / "gold/daily/archive/AUDIT_LOG_2026_11.md"
        archive_file.parent.mkdir(parents=True, exist_ok=True)
        archive_file.write_text(nov_entries, encoding="utf-8")
        dec_entry = "## 2026-12-01 07:30\n\n- Dec 1 audit note\n"
        audit.write_text(f"{header}\n{dec_entry}\n{standing_table}", encoding="utf-8")
        self.git("add", "gold")
        self.git("commit", "-qm", "Archive Nov entries while keeping standing bottom summary")
        rolled = self.git("rev-parse", "HEAD")
        edition_run._check_gold_ledger_history(base, rolled)

        # Dropping a standing summary row must still fail
        bad_table = standing_table.replace("| 2 | 谣言乙 | 官源核查乙 |\n", "")
        audit.write_text(f"{header}\n{dec_entry}\n{bad_table}", encoding="utf-8")
        self.git("add", "gold")
        self.git("commit", "-qm", "Drop row from standing summary table")
        dropped_row = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "AUDIT_LOG.*preserve"):
            edition_run._check_gold_ledger_history(base, dropped_row)

        # Modifying an archived line must also fail
        audit.write_text(f"{header}\n{dec_entry}\n{standing_table}", encoding="utf-8")
        archive_file.write_text(nov_entries.replace("Nov 25 audit note", "Tampered note"), encoding="utf-8")
        self.git("add", "gold")
        self.git("commit", "-qm", "Modify archived audit entry")
        tampered = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "AUDIT_LOG.*preserve"):
            edition_run._check_gold_ledger_history(base, tampered)

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

    def test_collect_data_caveats_dict_exceptions_source_divergence_and_home_sanitization(self):
        gold_snap = {
            "data_caveats": [
                {
                    "id": "src_div_item",
                    "market": "gold",
                    "category": "source_divergence",
                    "severity": "warn",
                    "item": "伦敦与纽约收盘口径分歧",
                    "detail": (
                        "路径 /home/runner/work/data.csv 与 DAILY_FORMAT_SPEC.md / DAILY_REPORT_SPEC.md / "
                        "unified-edition.prompt.md / gold-research-publishing / market_calendar.json，"
                        "11/25 隔夜 4-5p 主刊与 11/26 切模式 2 美股休市守望简报"
                    ),
                    "impact": "已透明披露",
                }
            ]
        }
        eq_state = {
            "edition_id": "2026-11-26_1800",
            "as_of_cst": "2027-02-08T18:00:00+08:00",
            "publication_exceptions": {
                "edition_id": "2026-11-26_1800",
                "markets": {
                    "a_share": {
                        "kind": "source_outage",
                        "reason": "交易所接口临时维护（参考 /home/ci/log.txt）",
                        "evidence_url": "https://www.sse.com.cn/notice",
                        "next_review_session": "2026-11-27_0730",
                    },
                },
            },
            "calendar_overrides": [
                {
                    "date_cst": "2027-02-05",
                    "end_date_cst": "2027-02-14",
                    "type": "long_holiday_start",
                    "markets_affected": ["a_share"],
                    "note": "春节休市，切模式 2 守望刊（4-5p 主刊节后恢复）",
                },
                {
                    "date_cst": "2027-02-10",
                    "type": "monthly_rollover",
                    "markets_affected": ["a_share", "hk_stock", "us_stock"],
                    "note": "内部滚存不应展示",
                },
            ],
        }
        caveats = build_site.collect_data_caveats(gold_snap, eq_state)
        by_id = {c["id"]: c for c in caveats}
        self.assertEqual(by_id["src_div_item"]["category"], "source_conflict")
        self.assertEqual(by_id["src_div_item"]["category_label"], "多源口径差异")
        self.assertIn("pub_exc_a-share_source_outage", by_id)
        exc_item = by_id["pub_exc_a-share_source_outage"]
        self.assertEqual(exc_item["market"], "a-share")
        self.assertEqual(exc_item["severity"], "high")
        self.assertEqual(exc_item["due_label"], "预计 11/27 07:30 早报核销")

        joined = " ".join(f"{c['title']} {c['detail']} {c['impact']}" for c in caveats)
        for leak in (
            "/home/",
            "DAILY_FORMAT_SPEC.md",
            "DAILY_REPORT_SPEC.md",
            "unified-edition.prompt.md",
            "gold-research-publishing",
            "market_calendar.json",
            "4-5p 主刊",
            "切模式 2",
        ):
            self.assertNotIn(leak, joined)

        # Edition-id None dict exception is also surfaced; mismatched edition_id is skipped
        eq_none = {**eq_state, "publication_exceptions": {**eq_state["publication_exceptions"], "edition_id": None}}
        self.assertTrue(any(c["id"] == "pub_exc_a-share_source_outage" for c in build_site.collect_data_caveats({}, eq_none)))
        eq_stale = {**eq_state, "publication_exceptions": {**eq_state["publication_exceptions"], "edition_id": "2026-11-25_1800"}}
        self.assertFalse(any(c["id"] == "pub_exc_a-share_source_outage" for c in build_site.collect_data_caveats({}, eq_stale)))

        # Local /home/ href & text stripping
        self.assertEqual(build_site._rewrite_href("/home/runner/report.md", "", {}, "gold"), "archive.html")
        self.assertNotIn("/home/", build_site._strip_local_paths_in_text("<p>见 /home/runner/work/a.md 档案</p>"))

        # Holiday alerts: multi-day range overlap, monthly_rollover excluded, note sanitized
        holidays = build_site.collect_holiday_alerts(eq_state, max_days=7)
        self.assertEqual(len(holidays), 1)
        self.assertEqual(holidays[0]["date"], "02/05–02/14")
        self.assertNotIn("切模式 2", holidays[0]["note"])
        self.assertNotIn("4-5p 主刊", holidays[0]["note"])

    def test_extract_all_stocks_parses_numeric_fields_cleanly(self):
        a_md = (
            "### 5.2\n"
            "| 标的 | 现价 | 估值 | 锚 | 结论 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 招商银行 `600036` | 43.32 | 7.3x | 安全锚：40.00–42.00 元 | 🟢 当下底座 |\n"
            "| 紫金矿业 `601899` | 24.50 | 8.6x | 安全锚：20.5–22.0 元 | 🔵 🔒未来主攻 |\n"
            "### 5.3\n"
            "## 附表二\n"
            "| 赛道 | 标的 | 价格 | 估值 | 诊断 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 银行 | 招商银行 `600036` | 43.32（11/25 收） | 7.3x / 0.92x / 4.7% / -5.0% | 🟢 当下底座；派息率 35% |\n"
            "| 有色 | 紫金矿业 `601899` | 24.50 | 8.6x / 2.96x / 3.4% / +16% | 🔵 🔒未来主攻；警期铜入熊 |\n"
        )
        hk_md = (
            "## 附表二\n"
            "| 赛道 | 标的 | 价格 | 估值 | 诊断 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 能源 | 中国海油 `00883` | 18.50（1,000 股） | TTM PE 6.8x / 6.2% / 无 A 股 | 🟢 当下底座；锚 17.0 下 |\n"
            "| 保险 | 中国平安 `02318` | 50.20 | 8.0x(营运6.5x) / 5.5% / AH +27.7% | 🟢 当下底座；前三季营运利润 +8.3% 高息 |\n"
            "| 有色 | 紫金矿业 `02899` | 22.10 | 7.5–8.0x / 3.6%–4.0% / AH +16% | 🟡 分歧观察；受铜熊金红灯压制 |\n"
            "| 测试 | 示例公司 `09999` | 10.00 | 12.0x / — / 无 A 股 | 🟡 分歧观察；前三季营运利润 +8.3% 高息 |\n"
        )
        us_md = (
            "## 附表二\n"
            "| 赛道 | 标的 | 价格 | 估值 | 诊断 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 矿业 | **纽蒙特** `NEM` | $99.95 (-0.77%) | FWD PE 10.7x · 🟡 观察（禁新买） | 股息 2.5%，存量稳拿；锚 $85–$90 |\n"
            "| AI | **安思罗匹克** `ANT` | $78.00 | 约 13.5x 年化收入 · 🟡 分歧观察 | 首周破发；锚 $65–$72 |\n"
            "| 地产 | **易昆尼克斯** `EQIX` | $910.00 | ~24x 经调营运资金 · 🟡 分歧观察 | 息 2.10%；锚 $880–$920 |\n"
            "| 地产 | **普洛斯** `PLD` | $115.00 | ~18.7x 营运资金 · 🟡 分歧观察 | 息 3.35%；锚 $112–$118 |\n"
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
        self.assertFalse(by_code["600036"]["summary"].startswith(("🟢", "当下底座")))
        self.assertTrue(by_code["601899"]["is_gold_locked"])
        self.assertFalse(by_code["601899"]["summary"].startswith(("🔵", "🔒", "未来主攻")))

        self.assertEqual(by_code["00883.HK"]["pe_num"], 6.8)
        self.assertEqual(by_code["00883.HK"]["div_pct"], 6.2)
        self.assertEqual(by_code["00883.HK"]["ah_pct"], 69.2)
        self.assertEqual(by_code["00883.HK"]["anchor_gap_pct"], 8.8)

        self.assertEqual(by_code["02318.HK"]["pe_num"], 8.0)
        self.assertEqual(by_code["02318.HK"]["div_pct"], 5.5)
        self.assertIsNone(by_code["09999.HK"]["div_pct"])
        self.assertTrue(by_code["02899.HK"]["is_gold_locked"])

        self.assertEqual(by_code["NEM"]["price_num"], 99.95)
        self.assertEqual(by_code["NEM"]["pe_num"], 10.7)
        self.assertEqual(by_code["NEM"]["div_pct"], 2.5)
        self.assertEqual(by_code["NEM"]["anchor_low"], 85.0)
        self.assertEqual(by_code["NEM"]["anchor_high"], 90.0)
        self.assertTrue(by_code["NEM"]["is_gold_locked"])
        self.assertIsNone(by_code["ANT"]["pe_num"])
        self.assertIsNone(by_code["EQIX"]["pe_num"])
        self.assertEqual(by_code["EQIX"]["div_pct"], 2.1)
        self.assertIsNone(by_code["PLD"]["pe_num"])
        self.assertEqual(by_code["PLD"]["div_pct"], 3.35)

        for st in stocks:
            for k in ("market", "market_label", "sector", "name", "code", "price", "valuation", "color", "action_label", "summary"):
                self.assertIsInstance(st[k], str)
                self.assertNotIn("**", st[k])
                self.assertNotIn("`", st[k])

    def test_load_gold_ledger_with_archives_appends_newest_first(self):
        with tempfile.TemporaryDirectory() as temporary:
            gold_dir = Path(temporary) / "gold"
            daily_dir = gold_dir / "daily"
            arch_dir = daily_dir / "archive"
            arch_dir.mkdir(parents=True)
            (daily_dir / "CHANGELOG.md").write_text("## 2026-12-01\n\n- Dec entry\n", encoding="utf-8")
            (arch_dir / "CHANGELOG_2026_10.md").write_text("## 2026-10-31\n\n- Oct entry\n", encoding="utf-8")
            (arch_dir / "CHANGELOG_2026_11.md").write_text("## 2026-11-30\n\n- Nov entry\n", encoding="utf-8")
            with patch.object(build_site, "GOLD_DIR", gold_dir):
                combined = build_site._load_gold_ledger_with_archives("CHANGELOG", is_audit_log=False)
            self.assertLess(combined.index("Dec entry"), combined.index("Nov entry"))
            self.assertLess(combined.index("Nov entry"), combined.index("Oct entry"))

    def test_multi_asset_channels_etfs_and_dossiers_render_cleanly(self):
        repo = Path(build_site.__file__).resolve().parent.parent
        ch_data = json.loads((repo / "equity" / "state" / "multi_asset_channels.json").read_text("utf-8"))
        etf_data = json.loads((repo / "equity" / "state" / "etf_universe.json").read_text("utf-8"))
        dos_data = json.loads((repo / "equity" / "state" / "deep_dossiers.json").read_text("utf-8"))

        ch_html = build_site.build_channels_page(ch_data)
        self.assertEqual(len(ch_data["channels"]), 8)
        self.assertIn("储蓄国债", ch_html)
        self.assertIn("table-wrap", ch_html)
        self.assertIn("data-channel-cat", ch_html)

        # Homepage (cockpit) renders ALL 8 investment channels in detail + ETF showcase + ZERO PDF/Word links
        cockpit_html = build_site.build_cockpit_page(
            {"as_of_short": "2026-11-26 18:30", "tier_code": "Tier 0", "new_buy_allowed": False},
            {"as_of_cst": "2026-11-26T18:30:00+08:00"},
            {},
            {"a-share": 76, "hk-stock": 75, "us-stock": 80},
            channels_data=ch_data,
            etf_data=etf_data,
        )
        for ch in ch_data["channels"]:
            self.assertIn(f'id="ch-{ch["id"]}"', cockpit_html)
            self.assertIn(ch["name"], cockpit_html)
        self.assertIn('id="sec-etf-radar"', cockpit_html)
        for forbidden in ("PDF ↗", "Word ↗", "latest-reports", "离线下载中心"):
            self.assertNotIn(forbidden, cockpit_html)

        etf_html = build_site.build_etfs_page(etf_data)
        self.assertGreaterEqual(len(etf_data["etfs"]), 75)
        self.assertIn('id="etf-data"', etf_html)
        self.assertIn("红灯暂停新买", etf_html)

        # Graceful empty fallback
        self.assertIn("8 大合规", build_site.build_channels_page(None))
        self.assertIn('id="etf-data"', build_site.build_etfs_page(None))

        # 7-dimension dossier merge covers all 231 pool stocks
        sample = [
            {"market": "a-share", "code": "601398", "name": "工商银行"},
            {"market": "hk-stock", "code": "00005.HK", "name": "汇丰控股"},
            {"market": "us-stock", "code": "NVDA", "name": "英伟达"},
        ]
        merged = build_site.merge_stock_dossiers(sample, dos_data)
        self.assertEqual(dos_data["total_stocks"], 231)
        for st in merged:
            self.assertIn("dossier", st)
            for k in ("moat", "financials", "valuation_anchor", "shareholder_flow", "catalysts", "bear_case", "action_etf"):
                self.assertTrue(st["dossier"][k].strip())


if __name__ == "__main__":
    unittest.main()
