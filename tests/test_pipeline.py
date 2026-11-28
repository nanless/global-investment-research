from contextlib import redirect_stderr
from datetime import date, datetime, timedelta, timezone
import html
from io import StringIO
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import shutil
from scripts import build_site, edition_run, fetch_kline_data, install_sidecars, lint_site, pages_release, patch_state_dbs, publish_site
from scripts.state_transaction import install_locked, state_write_lock


class EditionRunTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        repository = patch.object(edition_run, "ROOT", self.root)
        repository.start()
        self.addCleanup(repository.stop)
        self.git("init", "-q", "-b", "main")
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

    def test_review_ledger_cannot_be_a_symbolic_link_in_worktree_or_commit(self):
        metrics = self.root / "gold/daily/rsi_metrics.json"
        target = self.root / "gold/daily/copied_metrics.json"
        target.write_text(json.dumps({"runs": [{"run_id": self.edition, "review_closure": {
            "reviewer_completed": True, "findings": [],
        }}]}), encoding="utf-8")
        metrics.symlink_to(target.name)
        with self.assertRaisesRegex(ValueError, "ordinary path.*rsi_metrics.json"):
            edition_run.check_edition_reviews(self.edition, root=self.root)
        self.git("add", "gold")
        self.git("commit", "-qm", "Linked review ledger")
        with self.assertRaisesRegex(ValueError, "ordinary file.*rsi_metrics.json"):
            edition_run.check_edition_reviews(self.edition, sha=self.git("rev-parse", "HEAD"))

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

    def test_complete_can_be_retried_after_the_receipt_was_committed(self):
        token = self.reach_publish()
        sha = self.committed_edition()
        url = "https://example.invalid/actions/runs/1"
        edition_run.record_push(token, sha=sha, repository="example/project")
        with patch.object(edition_run, "verify_pages", return_value=url) as deploy:
            with self.runs:
                self.assertEqual(edition_run.complete(self.runs, token), url)
            completed_row = edition_run.status(self.runs)[0]
            with self.runs:
                self.assertEqual(edition_run.complete(self.runs, token), url)
            self.assertEqual(edition_run.status(self.runs)[0], completed_row)
        deploy.assert_called_once_with(sha, "example/project", 180)

    def test_parallel_completion_returns_the_recorded_exact_proof(self):
        token = self.reach_publish()
        sha = self.committed_edition()
        url = "https://example.invalid/actions/runs/1"
        edition_run.record_push(token, sha=sha, repository="example/project")

        for stale_probe in (False, True):
            with self.subTest(stale_probe=stale_probe):
                with self.runs:
                    self.runs.execute("UPDATE publications SET deployed_sha = NULL WHERE token = ?", (token,))
                    self.runs.execute("UPDATE runs SET status = 'running', outcome = '' WHERE token = ?", (token,))

                def finish_in_another_connection(*_args):
                    other = edition_run.open_runs()
                    try:
                        with other, patch.object(edition_run, "verify_pages", return_value=url):
                            self.assertEqual(edition_run.complete(other, token), url)
                    finally:
                        other.close()
                    if stale_probe:
                        raise edition_run.DeploymentPending("Temporary transport timeout")
                    return "https://example.invalid/actions/runs/2"

                with patch.object(edition_run, "verify_pages", side_effect=finish_in_another_connection), self.runs:
                    self.assertEqual(edition_run.complete(self.runs, token), url)
                self.assertEqual(edition_run.status(self.runs)[0]["outcome"], f"{sha} {url}")

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

    def test_scheduled_editions_do_not_go_back_but_manual_history_is_available(self):
        newer = "2026-11-27_1130"
        token = edition_run.begin(self.runs, newer, "antigravity-1130")
        with self.runs:
            edition_run.fail(self.runs, token, "Fixture timeout")
        with self.assertRaisesRegex(ValueError, "cannot go back before 2026-11-27_1130"):
            edition_run.begin(self.runs, "2026-11-27_0730", "antigravity-0730", reap_stale=True)

        retry = edition_run.begin(self.runs, newer, "antigravity-1130")
        with self.runs:
            edition_run.fail(self.runs, retry, "Fixture timeout")
        manual = edition_run.begin(self.runs, "2026-11-26_1800_r2")
        self.assertEqual(edition_run.active_run(self.runs, manual)["edition"], "2026-11-26_1800_r2")

    def test_scheduled_entry_rejects_runtime_drift_without_creating_an_attempt(self):
        script = self.root / "equity/lint_equity.py"
        script.parent.mkdir()
        script.write_text("# uncommitted runtime dependency\n", encoding="utf-8")
        with patch.object(sys, "argv", ["edition_run.py", "begin", "--scheduled", "1800"]), patch.object(
            edition_run, "scheduled_edition", return_value=self.edition,
        ), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(edition_run.main(), 1)
        self.assertIn("uncommitted workflow or research code", stderr.getvalue())
        self.assertIn("equity/lint_equity.py", stderr.getvalue())
        self.assertEqual(edition_run.status(self.runs), [])

        self.git("add", "equity/lint_equity.py")
        self.git("commit", "-qm", "Reviewed maintenance baseline")
        ledger = self.root / edition_run.GOLD_HISTORY_LEDGERS[0]
        ledger.write_text("## Previous edition\n\n- Mutated evidence\n", encoding="utf-8")
        with patch.object(sys, "argv", ["edition_run.py", "begin", "--scheduled", "1800"]), patch.object(
            edition_run, "scheduled_edition", return_value=self.edition,
        ), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(edition_run.main(), 1)
        self.assertIn("must preserve every prior nonblank line", stderr.getvalue())
        self.assertEqual(edition_run.status(self.runs), [])

    def test_scheduled_entry_keeps_prior_completion_when_recovery_outlasts_its_window(self):
        token = self.reach_publish()
        sha = self.committed_edition()
        edition_run.record_push(token, sha=sha, repository="example/project")

        class Clock(datetime):
            current = datetime(2026, 11, 27, 13, 30, tzinfo=edition_run.BEIJING)

            @classmethod
            def now(cls, tz=None):
                return cls.current if tz is None else cls.current.astimezone(tz)

        def finish_previous_deployment(*_args):
            Clock.current += timedelta(seconds=80)
            return "https://example.invalid/actions/runs/1"

        with (
            patch.object(sys, "argv", ["edition_run.py", "begin", "--scheduled", "0730"]),
            patch.object(edition_run, "datetime", Clock),
            patch.object(edition_run, "verify_pages", side_effect=finish_previous_deployment),
            redirect_stderr(StringIO()) as stderr,
        ):
            self.assertEqual(edition_run.main(), 1)
        self.assertIn("Outside the Beijing run window for 0730", stderr.getvalue())
        completed, = edition_run.status(self.runs)
        self.assertEqual(completed["edition"], self.edition)
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(completed["deployed_commit"], sha)

    def test_scheduled_phase_cannot_advance_after_a_rule_changes_in_the_worktree(self):
        token = edition_run.begin(self.runs, self.edition, "antigravity-1800")
        rule = self.root / "gold/daily/DAILY_FORMAT_SPEC.md"
        rule.write_text("Local rule change\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "gold/daily/DAILY_FORMAT_SPEC.md"):
            edition_run.advance(self.runs, token, "gold")
        self.assertEqual(edition_run.active_run(self.runs, token)["phase"], "research")

        rule.unlink()
        self.assertEqual(edition_run.advance(self.runs, token, "gold"), "gold")

    def test_committed_source_snapshot_sets_scheduled_floor_without_local_run(self):
        snapshot = self.root / "gold/data_snapshot.json"
        snapshot.write_text('{"edition_id":"2026-11-28_0730_r2"}')
        self.git("add", "gold")
        self.git("commit", "-qm", "Already published elsewhere")
        snapshot.write_text('{"edition_id":"2026-11-26_1800"}')
        with self.assertRaisesRegex(ValueError, "cannot go back before 2026-11-28_0730_r2"):
            edition_run.begin(self.runs, "2026-11-28_0730", "antigravity-0730")
        token = edition_run.begin(self.runs, "2026-11-28_1130", "antigravity-1130")
        self.assertEqual(edition_run.active_run(self.runs, token)["phase"], "research")

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

    def test_new_actions_deployment_waits_for_public_pages_before_completing(self):
        token = self.reach_publish()
        sha = self.committed_edition()
        repository = "example/project"
        edition_run.record_push(token, sha=sha, repository=repository)
        run = {"databaseId": 5, "headSha": sha, "headBranch": "main", "status": "completed", "url": "fixture"}
        detail = {**run, "jobs": [{"name": edition_run.DEPLOY_JOB, "conclusion": "success"}]}
        proof = (self.edition, {})
        with patch.object(edition_run, "_pages_release_proof", return_value=proof), \
             patch.object(edition_run, "_gh_json", side_effect=[[run], detail, [run], detail]), \
             patch.object(pages_release, "verify_release", side_effect=[ValueError("cached homepage"), None]) as verify:
            with self.assertRaisesRegex(edition_run.DeploymentPending, "cached homepage"):
                edition_run.complete(self.runs, token, wait=0)
            self.assertEqual(edition_run.active_run(self.runs, token)["phase"], "publish")
            self.assertEqual(edition_run.publication_commit(token), sha)
            with self.runs:
                self.assertEqual(edition_run.complete(self.runs, token, wait=0), "fixture")
        self.assertEqual(verify.call_count, 2)
        self.assertEqual(edition_run.status(self.runs)[0]["deployed_commit"], sha)

    def test_release_protocol_and_hashes_are_read_from_candidate_git_tree(self):
        workflow = self.root / ".github/workflows/deploy-pages.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("legacy deploy job\n")
        self.git("add", ".github")
        self.git("commit", "-qm", "Legacy workflow")
        legacy = self.git("rev-parse", "HEAD")
        self.assertIsNone(edition_run._pages_release_proof(legacy))

        workflow.write_text("run: python3 scripts/pages_release.py\n")
        for path in pages_release.EDITION_PATHS:
            source = self.root / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(json.dumps({"edition_id": self.edition}))
        for path in pages_release.COPIED_ASSETS.values():
            source = self.root / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"committed bytes\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Stamped workflow")
        candidate = self.git("rev-parse", "HEAD")
        (self.root / pages_release.COPIED_ASSETS["assets/app.js"]).write_bytes(b"dirty worktree")
        issue, hashes = edition_run._pages_release_proof(candidate)
        self.assertEqual(issue, self.edition)
        self.assertEqual(hashes, dict.fromkeys(pages_release.COPIED_ASSETS, pages_release.hash_bytes(b"committed bytes\n")))

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

    def test_already_archived_gold_ledgers_must_remain_byte_identical(self):
        archive = self.root / "gold/daily/archive/AUDIT_LOG_2026_10.md"
        archive.parent.mkdir(parents=True)
        original = b"# Previous month\n\n- Audit entry\n"
        archive.write_bytes(original)
        self.git("add", "gold")
        self.git("commit", "-qm", "Previously archived ledger")
        base = self.git("rev-parse", "HEAD")

        new_archive = archive.with_name("AUDIT_LOG_2026_11.md")
        new_archive.write_bytes(b"# Newly archived month\n")
        self.git("add", "gold")
        self.git("commit", "-qm", "Add an archive without editing the old month")
        edition_run._check_gold_ledger_history(base, self.git("rev-parse", "HEAD"))

        archive.write_bytes(original.replace(b"\n", b"\r\n"))
        with self.assertRaisesRegex(ValueError, "AUDIT_LOG_2026_10.*previously archived"):
            edition_run._check_gold_ledger_history(base, None)

        self.git("add", "gold")
        self.git("commit", "-qm", "Rewrite historical archived line endings")
        with self.assertRaisesRegex(ValueError, "AUDIT_LOG_2026_10.*previously archived"):
            edition_run._check_gold_ledger_history(base, self.git("rev-parse", "HEAD"))

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
        ), patch.object(edition_run.time, "sleep"), patch.object(edition_run, "_pages_release_proof", return_value=None):
            url = edition_run.verify_pages(sha, "example/project", wait=10)
        self.assertEqual(url, ok_run["url"])

    def test_actions_wait_does_not_consume_the_public_bytes_budget(self):
        sha = "a" * 40
        run = {"databaseId": 4, "headSha": sha, "headBranch": "main", "status": "completed", "url": "fixture"}
        detail = {**run, "jobs": [{"name": edition_run.DEPLOY_JOB, "conclusion": "success"}]}
        now = 0.0

        def github(*args, **_kwargs):
            nonlocal now
            if args[:2] == ("run", "list"):
                return [run]
            now = 14.9
            return detail

        def live_release(*_args, timeout):
            nonlocal now
            if timeout < 30:
                now = 15.0
                raise TimeoutError("insufficient budget to download release assets")

        with (
            patch.object(edition_run.time, "monotonic", side_effect=lambda: now),
            patch.object(edition_run, "_gh_json", side_effect=github),
            patch.object(edition_run, "_pages_release_proof", return_value=(self.edition, {})),
            patch.object(pages_release, "verify_release", side_effect=live_release) as verify,
        ):
            self.assertEqual(edition_run.verify_pages(sha, "example/project", wait=15), run["url"])
        verify.assert_called_once_with(sha, self.edition, "example/project", {}, timeout=100)

    def test_transient_public_pages_failure_retries_without_wasting_actions_queries(self):
        sha = "a" * 40
        run = {"databaseId": 4, "headSha": sha, "headBranch": "main", "status": "completed", "url": "fixture"}
        detail = {**run, "jobs": [{"name": edition_run.DEPLOY_JOB, "conclusion": "success"}]}
        now = 0.0

        def sleep(seconds):
            nonlocal now
            now += seconds

        with (
            patch.object(edition_run.time, "monotonic", side_effect=lambda: now),
            patch.object(edition_run.time, "sleep", side_effect=sleep),
            patch.object(edition_run, "_gh_json", side_effect=[[run], detail]) as github,
            patch.object(edition_run, "_pages_release_proof", return_value=(self.edition, {})),
            patch.object(pages_release, "verify_release", side_effect=[OSError("CDN timeout"), None]) as verify,
        ):
            self.assertEqual(edition_run.verify_pages(sha, "example/project", wait=15), run["url"])
        self.assertEqual(github.call_count, 2)
        self.assertEqual([call.kwargs["timeout"] for call in verify.call_args_list], [100, 95])

    def test_proxy_fallback_respects_the_remaining_actions_budget(self):
        now = 0.0
        commands = []

        def run(cmd, *, env, timeout, **_kwargs):
            nonlocal now
            commands.append((bool(env.get("HTTPS_PROXY")), timeout))
            if len(commands) == 1:
                now = 12.0
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Proxy failed")
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

        with (
            patch.object(edition_run.time, "monotonic", side_effect=lambda: now),
            patch.object(edition_run, "_clean_env", return_value={"HTTPS_PROXY": "http://127.0.0.1:7890"}),
            patch.object(edition_run.shutil, "which", return_value="/usr/local/bin/gh"),
            patch.object(edition_run.subprocess, "run", side_effect=run),
        ):
            self.assertEqual(edition_run._gh_json("run", "list", deadline=15), {})
        self.assertEqual(commands, [(True, 15), (False, 3)])

    def test_verify_pages_keeps_malformed_actions_responses_pending(self):
        commit = "b" * 40
        run = {
            "databaseId": 10, "headSha": commit, "headBranch": "main",
            "status": "completed", "url": "https://example.invalid/runs/10",
        }
        repository = "example/project"
        malformed_details = (
            None,
            {**run, "jobs": None},
            {**run, "jobs": [{}]},
            {**run, "jobs": [{"name": edition_run.DEPLOY_JOB, "conclusion": "success", "status": "in_progress"}]},
        )
        with patch.object(edition_run, "_gh_json", return_value=None):
            with self.assertRaisesRegex(edition_run.DeploymentPending, "malformed workflow run list"):
                edition_run.verify_pages(commit, repository, wait=0)
        for details in malformed_details:
            with self.subTest(details=details), patch.object(edition_run, "_gh_json", side_effect=[[run], details]):
                with self.assertRaises(edition_run.DeploymentPending):
                    edition_run.verify_pages(commit, repository, wait=0)
        good = {**run, "jobs": [{"name": edition_run.DEPLOY_JOB, "conclusion": "success"}]}
        with patch.object(edition_run, "_gh_json", side_effect=[[{}, run], good]), patch.object(
            edition_run, "_pages_release_proof", return_value=None,
        ):
            self.assertEqual(edition_run.verify_pages(commit, repository, wait=0), run["url"])


class PagesReleaseTest(unittest.TestCase):
    def test_stamped_release_checks_fresh_public_bytes_and_committed_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            for relative in pages_release.RELEASE_FILES:
                target = site / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                body = b"<html>\n<head>\n</head>\n</html>" if relative == "index.html" else relative.encode("ascii")
                target.write_bytes(body)
            sha, edition = "a" * 40, "2026-11-28_1130"
            pages_release.write_release(site, sha, edition)
            base = {path: (site / path).read_bytes() for path in (*pages_release.RELEASE_FILES, pages_release.MANIFEST_PATH)}
            pages_release.write_release(site, sha, edition)
            self.assertEqual((site / "index.html").read_bytes(), base["index.html"])
            self.assertIn(sha.encode("ascii"), base["index.html"])
            trusted = {path: pages_release.hash_bytes(base[path]) for path in pages_release.COPIED_ASSETS}
            requests = []

            def verify_with(responses):
                requests.clear()

                def fetch(url, timeout):
                    uri = urlsplit(url)
                    self.assertEqual(uri.scheme, "https")
                    self.assertEqual(uri.netloc, "example.github.io")
                    self.assertTrue(uri.path.startswith("/project/"))
                    key = uri.path.removeprefix("/project/") or "index.html"
                    query = parse_qs(uri.query)
                    self.assertEqual(query["release"], [sha])
                    requests.append((key, query["verify"][0]))
                    return responses[key]

                with patch.object(pages_release, "_fetch", side_effect=fetch):
                    pages_release.verify_release(sha, edition, "example/project", trusted, timeout=15)

            verify_with(base)
            self.assertEqual([requests[0][0], requests[-1][0]], [pages_release.MANIFEST_PATH] * 2)
            self.assertEqual(len({nonce for _, nonce in requests}), len(requests))

            with self.assertRaisesRegex(ValueError, "index.html"):
                verify_with({**base, "index.html": b"cached homepage;HTTP 200"})

            changed = json.loads(base[pages_release.MANIFEST_PATH])
            changed["files"]["assets/app.js"] = pages_release.hash_bytes(b"altered JS")
            with self.assertRaisesRegex(ValueError, "committed static assets"):
                verify_with({
                    **base, "assets/app.js": b"altered JS",
                    pages_release.MANIFEST_PATH: json.dumps(changed).encode("utf-8"),
                })


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
            slot = install_sidecars.SLOTS[name]
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
                    "settings": {"sandboxMode": True},
                }
                (base / "projects" / f"{project_id}.json").write_text(json.dumps(payload))
            registry.write_text(json.dumps({"sidecars": entries}))
            notes = []
            self.assertEqual(install_sidecars.check_registry(registry, rendered, notes), [])
            self.assertEqual(notes, [])
            project_path = base / "projects" / "fixture-0.json"
            project = json.loads(project_path.read_text())
            project["settings"] = {"sandboxMode": False, "permissionPreset": "AGENT_PERMISSION_PRESET_TURBO"}
            project_path.write_text(json.dumps(project))
            self.assertTrue(any("terminal sandbox" in p for p in install_sidecars.check_registry(registry, rendered)))
            project["settings"]["sandboxMode"] = True
            project_path.write_text(json.dumps(project))

            paused = next(iter(entries))
            paused_entries = dict(entries)
            paused_entries[paused] = {**entries[paused], "enabled": False, "resolvedPermissions": {}}
            registry.write_text(json.dumps({"sidecars": paused_entries}))
            paused_problems = install_sidecars.check_registry(registry, rendered)
            self.assertIn(f"{paused}: disabled in Antigravity", paused_problems)
            self.assertTrue(any("has not resolved" in p for p in paused_problems))

            # Retired or replay entries lingering in config.json must fail check_registry
            entries_with_zombie = dict(entries)
            entries_with_zombie["daily-gold-deep-research"] = {"enabled": True, "projectId": "old-1"}
            entries_with_zombie["gir-local-replay-20261126-014653"] = {"enabled": False, "projectId": "old-2"}
            registry.write_text(json.dumps({"sidecars": entries_with_zombie}))
            zombie_problems = install_sidecars.check_registry(registry, rendered)
            self.assertTrue(any("daily-gold-deep-research" in p and "still enabled" in p for p in zombie_problems))
            self.assertTrue(any("gir-local-replay-20261126-014653" in p for p in zombie_problems))
            registry.write_text(json.dumps({"sidecars": entries}))

            # find_stale_sidecar_dirs must detect gir-local-replay-* dirs as well as retired IDs
            sc_dir = base / "sidecars"
            (sc_dir / "gir-local-replay-20261126-014653").mkdir(parents=True)
            self.assertEqual(install_sidecars.find_stale_sidecar_dirs(sc_dir), ["gir-local-replay-20261126-014653"])

            (base / "projects" / "fixture-0.json").unlink()
            self.assertIn("cannot verify", install_sidecars.check_registry(registry, rendered)[0])

            # Policy calendar must be enforced in both edition_run and publish_site extended state files
            self.assertIn("equity/state/policy_calendar.json", edition_run.EXTENDED_EQUITY_STATE_FILES)
            self.assertIn("equity/state/policy_calendar.json", publish_site.EXTENDED_EQUITY_STATE_FILES)

    def test_sidecar_installer_rejects_permission_count_or_duplicate_drift(self):
        root = Path(install_sidecars.__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            source = root / "automations"
            dest = fixture / "automations"
            shutil.copytree(source, dest)
            permissions = dest / "permissions.json"
            grants = json.loads(permissions.read_text(encoding="utf-8"))
            templates = dict(install_sidecars.discover_templates(dest / "sidecars"))
            for invalid in (grants[:-1], grants + ["read_file(__REPO_ROOT__/tests)"], grants[:-1] + [grants[0]]):
                with self.subTest(length=len(invalid)):
                    permissions.write_text(json.dumps(invalid), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "exactly 56 distinct"):
                        install_sidecars.render_template(next(iter(templates.values())), fixture, sys.executable)

    def test_sidecar_installer_rejects_an_executable_python_with_an_old_version(self):
        root = Path(install_sidecars.__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            python = fixture / "python3.9"
            python.write_text("#!/bin/sh\nprintf '3.9\\n'\n", encoding="utf-8")
            python.chmod(0o755)
            with self.assertRaisesRegex(ValueError, r"requires Python 3\.12 or newer.*reports 3\.9"):
                install_sidecars.validate_paths(root, str(python))
            with redirect_stderr(StringIO()) as failure:
                self.assertEqual(install_sidecars.main([
                    "--python-bin", str(python), "--target-dir", str(fixture / "sidecars"),
                ]), 1)
            self.assertIn("requires Python 3.12 or newer", failure.getvalue())
            self.assertFalse((fixture / "sidecars").exists())
            install_sidecars.validate_paths(root, sys.executable)

    def test_sidecar_registry_argument_never_falls_through_to_install_mode(self):
        with redirect_stderr(StringIO()) as failure:
            with self.assertRaises(SystemExit) as exc:
                install_sidecars.parse_args(["--registry", "custom-registry.json"])
        self.assertEqual(exc.exception.code, 2)
        self.assertIn("--registry requires --check-runtime", failure.getvalue())

    def test_sidecar_install_is_reversible_and_preserves_disabled_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "sidecars"
            identifiers = sorted(install_sidecars.SCHEDULES)
            destinations = [target / name / "sidecar.json" for name in identifiers]
            old = {dest: dest.parent.name.encode("utf-8") for dest in destinations}
            for dest, content in old.items():
                dest.parent.mkdir(parents=True)
                dest.write_bytes(content)
                dest.chmod(0o640)
            registry = root / "config.json"
            settings = json.dumps({"sidecars": {name: {"enabled": False} for name in identifiers}}).encode()
            registry.write_bytes(settings)
            write = install_sidecars.atomic_write_bytes

            def fail_second(dest, content):
                if dest == destinations[1]:
                    raise OSError("simulated install failure")
                write(dest, content)

            with patch.object(install_sidecars, "atomic_write_bytes", side_effect=fail_second), \
                 redirect_stderr(StringIO()):
                self.assertEqual(install_sidecars.main(["--target-dir", str(target)]), 1)
            self.assertEqual({dest: dest.read_bytes() for dest in destinations}, old)
            self.assertTrue(all(stat.S_IMODE(dest.stat().st_mode) == 0o640 for dest in destinations))
            self.assertEqual(registry.read_bytes(), settings)

            self.assertEqual(install_sidecars.main(["--target-dir", str(target)]), 0)
            self.assertEqual(install_sidecars.main(["--target-dir", str(target), "--check"]), 0)
            self.assertEqual(registry.read_bytes(), settings)

            protected = root / "protected.json"
            protected.write_bytes(b"do not change")
            destinations[1].unlink()
            destinations[1].symlink_to(protected)
            with redirect_stderr(StringIO()) as failure:
                self.assertEqual(install_sidecars.main(["--target-dir", str(target)]), 1)
            self.assertIn("must not be a symbolic link", failure.getvalue())
            self.assertEqual(protected.read_bytes(), b"do not change")

    def test_state_transaction_never_follows_a_symlink_inside_the_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "protected.json"
            original.write_bytes(b"original bytes")
            link = root / "state.json"
            link.symlink_to(original)
            with state_write_lock(root):
                with self.assertRaisesRegex(ValueError, "Unsafe state transaction destination 'state.json'"):
                    install_locked(root, [(link, b"incorrect replacement")])
            self.assertTrue(link.is_symlink())
            self.assertEqual(original.read_bytes(), b"original bytes")

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
        self.assertEqual(all_caveats[0]["due_label"], "计划于 11/27 07:30 早报复查")
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
        self.assertEqual(exc_item["due_label"], "计划于 11/27 07:30 早报复查")

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
        ms_data = json.loads((repo / "equity" / "state" / "market_state.json").read_text("utf-8"))
        ch_data = json.loads((repo / "equity" / "state" / "multi_asset_channels.json").read_text("utf-8"))
        etf_data = json.loads((repo / "equity" / "state" / "etf_universe.json").read_text("utf-8"))
        dos_data = json.loads((repo / "equity" / "state" / "deep_dossiers.json").read_text("utf-8"))

        ch_html = build_site.build_channels_page(ch_data, etf_data=etf_data, eq_state=ms_data)
        self.assertGreaterEqual(len(ch_data["channels"]), 12)
        core_channel_ids = {
            "reverse_repo",
            "large_cds",
            "fx_deposits_wm",
            "bonds",
            "funds_wm",
            "savings_insurance",
            "tax_advantaged_accounts",
            "qdii_mrf",
            "convertible_bonds",
            "c_reits",
            "commodity_etfs",
            "private_funds_trust",
        }
        actual_channel_ids = {ch["id"] for ch in ch_data["channels"]}
        self.assertTrue(
            core_channel_ids.issubset(actual_channel_ids),
            f"Missing core multi-asset channels: {core_channel_ids - actual_channel_ids}",
        )
        self.assertIn(f"{len(ch_data['channels'])} 大合规", ch_html)
        self.assertIn("channels/bonds.html", ch_html)
        self.assertIn("data-channel-cat", ch_html)

        pool_counts = {
            "a-share": int(ms_data["markets"]["a_share"]["stock_pool_count"]),
            "hk-stock": int(ms_data["markets"]["hk_stock"]["stock_pool_count"]),
            "us-stock": int(ms_data["markets"]["us_stock"]["stock_pool_count"]),
        }
        expected_pool = sum(pool_counts.values())

        # Homepage (cockpit) renders concise separate overview cards for ALL channels + 5 ETF groups + ZERO PDF/Word links
        cockpit_html = build_site.build_cockpit_page(
            {"as_of_short": "2026-11-26 18:30", "tier_code": "Tier 0", "new_buy_allowed": False},
            {"as_of_cst": "2026-11-26T18:30:00+08:00"},
            {},
            pool_counts,
            channels_data=ch_data,
            etf_data=etf_data,
        )
        for ch in ch_data["channels"]:
            self.assertIn(f'id="ch-{ch["id"]}"', cockpit_html)
            self.assertIn(f'href="channels/{ch["id"]}.html"', cockpit_html)
            self.assertIn(ch["name"], cockpit_html)
            detail_html = build_site.build_channel_detail_page(ch, ch_data["channels"], ch_data, etf_data=etf_data)
            self.assertIn("table-wrap", detail_html)
            self.assertIn("核心制度、税费与避坑红线", detail_html)
            if ch["id"] == "qdii_mrf":
                self.assertNotIn("300万合格投资者专享", detail_html)
        self.assertIn('id="sec-etf-radar"', cockpit_html)
        self.assertIn("etfs.html#asset_class=equity&region=cn", html.unescape(cockpit_html))
        self.assertIn("etfs.html#asset_class=fixed_income_plus", html.unescape(cockpit_html))
        self.assertNotIn("&amp;amp;", cockpit_html)
        for forbidden in ("PDF ↗", "Word ↗", "latest-reports", "离线下载中心"):
            self.assertNotIn(forbidden, cockpit_html)

        etf_html = build_site.build_etfs_page(etf_data, channel_count=len(ch_data["channels"]))
        self.assertGreaterEqual(len(etf_data["etfs"]), 140)
        self.assertEqual(len(etf_data["etfs"]), etf_data["total_etfs"])
        self.assertIn('id="etf-data"', etf_html)
        if etf_data.get("gold_tier0_locked") is True:
            self.assertIn("红灯暂停新买", etf_html)

        # Graceful empty fallback without hardcoded channel count
        empty_ch_html = build_site.build_channels_page(None)
        self.assertIn("合规多元投资渠道", empty_ch_html)
        self.assertIn('class="channels-hero"', empty_ch_html)
        self.assertIn('class="channel-list"', empty_ch_html)
        self.assertIn('id="etf-data"', build_site.build_etfs_page(None))

        # 7-dimension dossier merge dynamically aligns with market_state.json total pool & zero-template invariant
        sample = []
        for mkt in ("a-share", "hk-stock", "us-stock"):
            first_key = next(k for k in dos_data["dossiers"] if k.startswith(f"{mkt}:"))
            _, first_code = first_key.split(":", 1)
            entry = dos_data["dossiers"][first_key]
            sample.append({"market": mkt, "code": first_code, "name": entry.get("name") or first_code})
        merged = build_site.merge_stock_dossiers(sample, dos_data)
        self.assertEqual(dos_data["total_stocks"], expected_pool)
        self.assertEqual(dos_data.get("standard_deep_count"), 0)
        self.assertEqual(dos_data.get("core_deep_count"), len(dos_data["dossiers"]))
        self.assertEqual(len(dos_data["dossiers"]), expected_pool)
        for st in merged:
            self.assertIn("dossier", st)
            for k in ("moat", "financials", "valuation_anchor", "shareholder_flow", "catalysts", "bear_case", "action_etf"):
                self.assertTrue(st["dossier"][k].strip())

    def test_gate_s2_blocks_dangerous_schemes_double_escape_and_binary_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            site_dir = Path(temporary)
            (site_dir / "valid.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
            html_body = (
                "<!doctype html><html><body>"
                '<a href="javascript:alert(1)">js</a>'
                '<a href="java\tscript:void(0)">js-obf</a>'
                '<a href="data:text/html,hi">data</a>'
                '<a href="https://example.com/q?a=1&amp;amp;b=2">double-esc</a>'
                '<a href="reports/a_share.pdf">local-pdf</a>'
                '<a href="daily/gold.docx">local-docx</a>'
                '<a href="https://github.com/org/repo/releases/download/latest-reports/a.pdf">release</a>'
                '<a href="https://www.cboe.com/official/VIX_Whitepaper.pdf">ext-pdf-ok</a>'
                '<a href="https://example.com/q?a=1&amp;b=2">single-esc-ok</a>'
                '<a href="valid.html">ok</a>'
                "</body></html>"
            )
            index_path = site_dir / "index.html"
            index_path.write_text(html_body, encoding="utf-8")
            doc = lint_site.parse_html_file("index.html", index_path.resolve(), html_body)
            valid_doc = lint_site.parse_html_file("valid.html", (site_dir / "valid.html").resolve(), "<html><body>ok</body></html>")

            errors, warnings = [], []
            lint_site.run_gate_s2(site_dir, {"index.html": doc, "valid.html": valid_doc}, errors, warnings)
            self.assertEqual(warnings, [])
            self.assertTrue(any("forbidden URI scheme" in e and "javascript:alert(1)" in e for e in errors), errors)
            self.assertTrue(any("forbidden URI scheme" in e and "void(0)" in e for e in errors), errors)
            self.assertTrue(any("forbidden URI scheme" in e and "data:text/html" in e for e in errors), errors)
            self.assertTrue(any("double-escaped '&amp;amp;'" in e for e in errors), errors)
            self.assertTrue(any("forbidden PDF/Word or Release download link" in e and "a_share.pdf" in e for e in errors), errors)
            self.assertTrue(any("forbidden PDF/Word or Release download link" in e and "gold.docx" in e for e in errors), errors)
            self.assertTrue(any("forbidden PDF/Word or Release download link" in e and "latest-reports" in e for e in errors), errors)
            # Legitimate external official PDF citation and single-escaped query string remain allowed
            self.assertFalse(any("VIX_Whitepaper.pdf" in e for e in errors), errors)
            self.assertFalse(any("a=1&b=2" in e for e in errors), errors)

    def test_rewrite_href_sanitizes_schemes_sentinels_and_avoids_double_escape(self):
        for bad_scheme in (
            "javascript:alert(1)",
            "  Java\tScript:void(0) ",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
            "blob:https://example.com/1234",
        ):
            with self.subTest(bad_scheme=bad_scheme):
                self.assertEqual(build_site._rewrite_href(bad_scheme, "", {}, "gold"), "#")

        self.assertEqual(
            build_site._rewrite_href("https://gir-local.invalid/unknown.html", "", {}, "gold"),
            "archive.html",
        )
        self.assertEqual(
            build_site._rewrite_href("https://gir-local.invalid/unknown.html", "../", {}, "gold"),
            "../archive.html",
        )
        self.assertEqual(
            build_site._rewrite_href("https://gir-local.invalid/etfs.html#market=a-share", "", {}, "gold"),
            "etfs.html#market=a-share",
        )
        self.assertEqual(
            build_site._rewrite_href("https://example.com/redirect?next=gir-local.invalid/foo", "", {}, "gold"),
            "#",
        )
        self.assertEqual(
            build_site._rewrite_href("https://example.com/q?a=1&amp;b=2", "", {}, "gold"),
            "https://example.com/q?a=1&b=2",
        )

        # End-to-end sanitize_and_extract_toc must emit single-escaped &amp; (zero &amp;amp;) and block bad schemes/sentinels
        raw_html = (
            '<p><a href="https://example.com/q?a=1&amp;b=2">ok</a> '
            '<a href="javascript:alert(1)">js</a> '
            '<a href="data:text/html,x">data</a> '
            '<a href="https://gir-local.invalid/stale_file.md">rel</a></p>'
        )
        cleaned, _, _ = build_site.sanitize_and_extract_toc(
            raw_html, base_prefix="", slug_map={}, ctx_market="gold", extract_toc=False,
        )
        self.assertIn('href="https://example.com/q?a=1&amp;b=2"', cleaned)
        self.assertNotIn("&amp;amp;", cleaned)
        self.assertNotIn("javascript:", cleaned)
        self.assertNotIn("data:text/html", cleaned)
        self.assertNotIn("gir-local.invalid", cleaned)

    def test_gate_s3_blocks_embedded_json_leaks_and_gold_tier0_buy(self):
        with tempfile.TemporaryDirectory() as temporary:
            site_dir = Path(temporary)
            screener_payload = [
                {
                    "market": "a-share",
                    "code": "601899",
                    "name": "紫金矿业",
                    "summary": "核对 deep_dossiers.json 与 lint_equity.py 基线",
                    "valuation": "NaN / [object Object]",
                    "dossier": {"action_etf": "建议立即买入黄金 ETF 518880"},
                }
            ]
            etf_payload = [
                {
                    "code": "518660",
                    "name": "黄金ETF",
                    "thesis_deep": "同步 etf_universe.json 规则",
                    "action_role": "逢低买 518660 黄金",
                }
            ]
            scr_html = (
                '<!doctype html><html><body>'
                f'<script id="screener-data" type="application/json">{json.dumps(screener_payload, ensure_ascii=False)}</script>'
                '</body></html>'
            )
            etf_html = (
                '<!doctype html><html><body>'
                f'<script id="etf-data" type="application/json">{json.dumps(etf_payload, ensure_ascii=False)}</script>'
                '</body></html>'
            )
            scr_path = site_dir / "screener.html"
            etf_path = site_dir / "etfs.html"
            scr_path.write_text(scr_html, encoding="utf-8")
            etf_path.write_text(etf_html, encoding="utf-8")
            parsed = {
                "screener.html": lint_site.parse_html_file("screener.html", scr_path.resolve(), scr_html),
                "etfs.html": lint_site.parse_html_file("etfs.html", etf_path.resolve(), etf_html),
            }
            errors, warnings = [], []
            lint_site.run_gate_s3(
                site_dir, [scr_path, etf_path], parsed, errors, warnings, gold_new_buy_blocked=True,
            )
            self.assertTrue(any("#screener-data" in e and "internal engineering filename" in e for e in errors), errors)
            self.assertTrue(any("#screener-data" in e and "NaN/[object Object]" in e for e in errors), errors)
            self.assertTrue(any("#screener-data" in e and "Gold Tier 0 mutex violation" in e for e in errors), errors)
            self.assertTrue(any("#etf-data" in e and "internal engineering filename" in e for e in errors), errors)
            self.assertTrue(any("#etf-data" in e and "Gold Tier 0 mutex violation" in e for e in errors), errors)

            # Clean payloads with guarded red-light wording must pass Gate S3 cleanly
            clean_scr = (
                '<!doctype html><html><body>'
                '<script id="screener-data" type="application/json">'
                '[{"code":"601899","summary":"红灯停期间暂不新买黄金，等待四关齐备"}]'
                '</script></body></html>'
            )
            clean_etf = (
                '<!doctype html><html><body>'
                '<script id="etf-data" type="application/json">'
                '[{"code":"518660","action_role":"红灯暂停新买（严禁定投黄金）"}]'
                '</script></body></html>'
            )
            scr_path.write_text(clean_scr, encoding="utf-8")
            etf_path.write_text(clean_etf, encoding="utf-8")
            clean_parsed = {
                "screener.html": lint_site.parse_html_file("screener.html", scr_path.resolve(), clean_scr),
                "etfs.html": lint_site.parse_html_file("etfs.html", etf_path.resolve(), clean_etf),
            }
            clean_errors, clean_warnings = [], []
            lint_site.run_gate_s3(
                site_dir, [scr_path, etf_path], clean_parsed, clean_errors, clean_warnings, gold_new_buy_blocked=True,
            )
            self.assertEqual(clean_errors, [])
            self.assertEqual(clean_warnings, [])

    def test_build_guide_page_renders_clean_beginner_guide_respecting_gold_lock(self):
        gold_snap = {"tier_code": "Tier 0", "new_buy_allowed": False}
        ch_data = {"channels": [{"id": "bonds", "name": "债券与债券 ETF"}] * 12}
        etf_data = {"etfs": [{"code": "511360"}] * 165}

        guide_html = build_site.build_guide_page(gold_snap, {}, ch_data, etf_data, total_pool=231)
        self.assertIn("新手 3 分钟入门指南", guide_html)
        self.assertIn("高频金融关键词", guide_html)
        self.assertIn("12 大个人多元渠道", guide_html)
        self.assertIn("165 只重点 ETF", guide_html)
        self.assertIn('id="sec-guide-glossary"', guide_html)
        self.assertIn('id="guide-term-grid"', guide_html)

        # Zero condescending banned slogans or internal engineering leaks
        for banned in ("小白词典", "直接抄", "蠢事", "保命铁律", "PDF ↗", "Word ↗"):
            self.assertNotIn(banned, guide_html)
        self.assertIsNone(lint_site.S3_INTERNAL_ENG_LEAK_RE.search(guide_html))

        # Zero Gold Tier 0 buy-gold directive violations
        wrapped = f"<!doctype html><html><body>{guide_html}</body></html>"
        doc = lint_site.parse_html_file("guide.html", Path("guide.html"), wrapped)
        tier0_errors: list[str] = []
        lint_site._check_gold_tier0_mutex(doc, tier0_errors)
        self.assertEqual(tier0_errors, [])

        # Graceful fallback when SSOT inputs are None
        fallback_html = build_site.build_guide_page(None, None, None, None)
        self.assertIn("新手 3 分钟入门指南", fallback_html)
        self.assertIn("个人多元合规渠道", fallback_html)

    def test_install_sidecars_blocks_shell_chaining_injection(self):
        py_bin = "/usr/bin/python3"
        grants = [f"{py_bin} /repo/scripts/publish_site.py"]

        # Clean inline and fenced commands pass
        clean_prompt = (
            f"Run `{py_bin} /repo/scripts/publish_site.py --dry-run`\n"
            f"```bash\n{py_bin} /repo/scripts/publish_site.py --check-manuscripts\n```\n"
        )
        install_sidecars._audit_prompt_commands(clean_prompt, py_bin, grants, "fixture.template.json")

        # Shell chaining & command substitution tokens must be blocked in both inline & fenced forms
        injections = (
            f"`{py_bin} /repo/scripts/publish_site.py; rm -rf /`",
            f"`{py_bin} /repo/scripts/publish_site.py && id`",
            f"`{py_bin} /repo/scripts/publish_site.py || echo pwn`",
            f"`{py_bin} /repo/scripts/publish_site.py | cat`",
            f"`{py_bin} /repo/scripts/publish_site.py $(whoami)`",
            f"```bash\n{py_bin} /repo/scripts/publish_site.py; uname -a\n```",
            f"```bash\n{py_bin} /repo/scripts/publish_site.py && whoami\n```",
            f"```bash\n{py_bin} /repo/scripts/publish_site.py | head\n```",
            f"```bash\n{py_bin} /repo/scripts/publish_site.py $(id)\n```",
            f"```bash\n{py_bin} /repo/scripts/publish_site.py `id`\n```",
        )
        for payload in injections:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "forbidden shell metacharacters"):
                    install_sidecars._audit_prompt_commands(payload, py_bin, grants, "fixture.template.json")

        # Command grants themselves containing shell chaining must also be rejected
        for bad_grant in (f"{py_bin} /repo/scripts/a.py; id", f"{py_bin} /repo/scripts/a.py && id"):
            with self.subTest(bad_grant=bad_grant):
                with self.assertRaisesRegex(ValueError, "command grant contains forbidden shell metacharacters"):
                    install_sidecars._audit_prompt_commands("no commands", py_bin, [bad_grant], "fixture.template.json")

    def test_gate_s1_requires_guide_html(self):
        self.assertIn("guide.html", lint_site.REQUIRED_NONEMPTY_FILES)
        with tempfile.TemporaryDirectory() as temporary:
            site_dir = Path(temporary)
            (site_dir / ".nojekyll").write_text("", encoding="utf-8")
            filler = "<!doctype html><html><head><title>Fixture</title></head><body>" + ("x" * 3200) + "</body></html>"
            for rel in lint_site.REQUIRED_NONEMPTY_FILES:
                if rel == "guide.html":
                    continue
                target = site_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if rel == "manifest.json":
                    target.write_text('{"edition": "fixture"}', encoding="utf-8")
                elif rel.endswith(".html"):
                    target.write_text(filler, encoding="utf-8")
                else:
                    target.write_text("fixture", encoding="utf-8")

            errors, warnings = [], []
            lint_site.run_gate_s1(site_dir, errors, warnings)
            self.assertEqual(warnings, [])
            self.assertTrue(
                any("Missing required core artifact: guide.html" in e for e in errors),
                errors,
            )

            (site_dir / "guide.html").write_text(filler, encoding="utf-8")
            ok_errors, ok_warnings = [], []
            lint_site.run_gate_s1(site_dir, ok_errors, ok_warnings)
            self.assertEqual(ok_errors, [])
            self.assertEqual(ok_warnings, [])

    def test_gate_s3_scans_channel_ch_etf_data_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            site_dir = Path(temporary)
            ch_dir = site_dir / "channels"
            ch_dir.mkdir(parents=True)
            bad_payload = [
                {
                    "code": "518880",
                    "name": "黄金ETF",
                    "thesis_deep": "同步 etf_universe.json 基线并避免 NaN",
                    "action_role": "建议立即买入黄金 ETF 518880",
                }
            ]
            bad_html = (
                "<!doctype html><html><body>"
                f'<script id="ch-etf-data" type="application/json">{json.dumps(bad_payload, ensure_ascii=False)}</script>'
                "</body></html>"
            )
            ch_path = ch_dir / "commodity_etfs.html"
            ch_path.write_text(bad_html, encoding="utf-8")
            parsed = {
                "channels/commodity_etfs.html": lint_site.parse_html_file(
                    "channels/commodity_etfs.html", ch_path.resolve(), bad_html
                ),
            }
            self.assertIsNotNone(parsed["channels/commodity_etfs.html"].ch_etf_json_raw)
            errors, warnings = [], []
            lint_site.run_gate_s3(
                site_dir, [ch_path], parsed, errors, warnings, gold_new_buy_blocked=True,
            )
            self.assertTrue(any("#ch-etf-data" in e and "internal engineering filename" in e for e in errors), errors)
            self.assertTrue(any("#ch-etf-data" in e and "NaN/[object Object]" in e for e in errors), errors)
            self.assertTrue(any("#ch-etf-data" in e and "Gold Tier 0 mutex violation" in e for e in errors), errors)

            clean_html = (
                "<!doctype html><html><body>"
                '<script id="ch-etf-data" type="application/json">'
                '[{"code":"518880","name":"黄金ETF","thesis_deep":"黄金红灯期严禁新买黄金，保持观望","action_role":"红灯暂停新买"}]'
                "</script></body></html>"
            )
            ch_path.write_text(clean_html, encoding="utf-8")
            clean_parsed = {
                "channels/commodity_etfs.html": lint_site.parse_html_file(
                    "channels/commodity_etfs.html", ch_path.resolve(), clean_html
                ),
            }
            clean_errors, clean_warnings = [], []
            lint_site.run_gate_s3(
                site_dir, [ch_path], clean_parsed, clean_errors, clean_warnings, gold_new_buy_blocked=True,
            )
            self.assertEqual(clean_errors, [])
            self.assertEqual(clean_warnings, [])

    def test_edition_run_ledger_char_diff_and_early_equity_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(edition_run, "ROOT", root):
                def _git(*args):
                    subprocess.run(
                        ["git", "-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", *args],
                        cwd=root, capture_output=True, text=True, check=True,
                    )
                _git("init", "-q")
                for relative in edition_run.GOLD_HISTORY_LEDGERS:
                    ledger = root / relative
                    ledger.parent.mkdir(parents=True, exist_ok=True)
                    ledger.write_text("## Previous edition\n\n- Original evidence\n", encoding="utf-8")
                _git("add", "gold")
                _git("commit", "-qm", "Previous deployment")
                runs = edition_run.open_runs()
                try:
                    ed = "2026-11-26_1800"
                    token = edition_run.begin(runs, ed)
                    with runs:
                        edition_run.advance(runs, token, "gold")
                    for name in ("gold/data_snapshot.json", "equity/state/market_state.json"):
                        path = root / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(json.dumps({"edition_id": ed}), encoding="utf-8")
                    # Tamper 2 characters in historical CHANGELOG line before equity phase
                    cl = root / "gold/daily/CHANGELOG.md"
                    cl.write_text("## Previous edition\n\n- Original evXXence\n", encoding="utf-8")
                    with self.assertRaises(ValueError) as ctx, runs:
                        edition_run.advance(runs, token, "equity")
                    msg = str(ctx.exception)
                    self.assertIn("must preserve every prior nonblank line in its original order", msg)
                    self.assertIn("[MODIFIED]", msg)
                finally:
                    runs.close()

    def test_publish_site_blocks_temp_patch_files(self):
        self.assertTrue(publish_site._is_forbidden_stage_path("equity/state/_edition_patch.json"))
        self.assertTrue(publish_site._is_forbidden_stage_path("gold/daily/_ledger_patch.json"))
        self.assertFalse(publish_site._is_forbidden_stage_path("scripts/patch_state_dbs.py"))

    def test_glossary_24_terms_and_sidecar_42_grants(self):
        self.assertGreaterEqual(len(build_site.GLOSSARY_TERMS), 24)
        terms_text = " ".join(f"{t['key']} {t['term']}" for t in build_site.GLOSSARY_TERMS)
        for key in ("DXY", "COT", "CDS", "ERP", "IRR"):
            self.assertIn(key, terms_text, f"Missing glossary term: {key}")
        root = Path(install_sidecars.__file__).resolve().parent.parent
        raw_perms = json.loads((root / "automations" / "permissions.json").read_text(encoding="utf-8"))
        expected_grants = len(install_sidecars._dedupe_preserve_order(raw_perms))
        self.assertGreaterEqual(expected_grants, 42)
        templates = dict(install_sidecars.discover_templates(root / "automations" / "sidecars"))
        self.assertEqual(len(templates), 3)
        for _, path in templates.items():
            _, definition = install_sidecars.render_template(path, root, "/usr/bin/python3")
            grants = definition["agent_permissions"]["access_grants"]
            self.assertEqual(len(grants), expected_grants)
            self.assertGreaterEqual(len(grants), 42)
            self.assertTrue(any("patch_state_dbs.py --apply" in str(g) for g in grants))
            self.assertTrue(any("patch_state_dbs.py --prepend-gold-ledgers" in str(g) for g in grants))
            self.assertTrue(any("fetch_kline_data.py" in str(g) for g in grants))

    def test_patch_state_dbs_apply_rollback_and_prepend_gold_ledgers(self):
        real_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            (sandbox / "gold" / "daily").mkdir(parents=True)
            (sandbox / "equity" / "state").mkdir(parents=True)
            for rel in (
                "gold/data_snapshot.json",
                "gold/daily/CHANGELOG.md",
                "gold/daily/AUDIT_LOG.md",
                "equity/state/market_state.json",
                "equity/state/multi_asset_channels.json",
                "equity/state/etf_universe.json",
                "equity/state/deep_dossiers.json",
            ):
                shutil.copy2(real_root / rel, sandbox / rel)

            next_ed = "2099-12-31_1800_r99"
            gold_obj = json.loads((sandbox / "gold/data_snapshot.json").read_text(encoding="utf-8"))
            live_tier_code = gold_obj.get("tier_code")
            live_new_buy = gold_obj.get("new_buy_allowed")
            live_gold_locked = (live_tier_code == "Tier 0" or live_new_buy is False)
            gold_obj["edition_id"] = next_ed
            gold_obj["as_of_short"] = "2099-12-31 23:55"
            (sandbox / "gold/data_snapshot.json").write_text(
                json.dumps(gold_obj, ensure_ascii=False), encoding="utf-8"
            )
            ms_obj = json.loads((sandbox / "equity/state/market_state.json").read_text(encoding="utf-8"))
            ms_obj["edition_id"] = next_ed
            ms_obj["as_of_cst"] = "2099-12-31T23:55:00+08:00"
            (sandbox / "equity/state/market_state.json").write_text(
                json.dumps(ms_obj, ensure_ascii=False), encoding="utf-8"
            )

            # Dynamically select the first non-gold ETF code and first non-gold A-share dossier key
            ma_seed = json.loads((sandbox / "equity/state/multi_asset_channels.json").read_text(encoding="utf-8"))
            eu_seed = json.loads((sandbox / "equity/state/etf_universe.json").read_text(encoding="utf-8"))
            dd_seed = json.loads((sandbox / "equity/state/deep_dossiers.json").read_text(encoding="utf-8"))

            sample_etf_code = next(
                e["code"]
                for e in eu_seed["etfs"]
                if not e.get("gold_locked")
                and patch_state_dbs._normalize_etf_code(e.get("code")) not in patch_state_dbs.GOLD_ETF_CODES
                and not patch_state_dbs.GOLD_ETF_NAME_RE.search(str(e.get("name", "")))
            )
            sample_a_key = next(
                k
                for k in dd_seed["dossiers"]
                if k.startswith("a-share:")
                and k not in patch_state_dbs.GOLD_DOSSIER_KEYS
                and not patch_state_dbs.GOLD_MINER_TICKERS_RE.search(k)
            )
            rr_orig_liner = next(
                ch["beginner_one_liner"] for ch in ma_seed["channels"] if ch["id"] == "reverse_repo"
            )

            # 1. Dry-run & real apply (preserves live Gold lock state so Gold unlock never breaks CI)
            patch_path = sandbox / "equity/state/_edition_patch.json"
            good_patch = {
                "edition_id": next_ed,
                "as_of_date": "2099-12-31",
                "as_of_label": "2099-12-31 23:55 CST",
                "gold_tier0_locked": live_gold_locked,
                "multi_asset_channels": {
                    "top_level_updates": {"as_of_label": "上一班渠道标签"},
                    "channels_patch": {
                        "reverse_repo": {
                            "beginner_one_liner": f"{rr_orig_liner}（测试更新：严禁新买黄金，优先活钱）",
                        }
                    }
                },
                "etf_universe": {
                    "top_level_updates": {"as_of_label": "上一班 ETF 标签"},
                    "etfs_upsert": [
                        {"code": sample_etf_code, "premium_note": "平价复核通过"}
                    ]
                },
                "deep_dossiers": {
                    "dossiers_patch": {
                        sample_a_key: {
                            "catalysts": "【2099-12-31 补丁核验】跟踪年末业绩兑现与现金流节奏。"
                        }
                    }
                },
            }
            patch_path.write_text(json.dumps(good_patch, ensure_ascii=False), encoding="utf-8")
            with patch.object(patch_state_dbs, "REPO_ROOT", sandbox):
                rc_dry = patch_state_dbs.main(["--apply", "--dry-run"])
                self.assertEqual(rc_dry, 0)
                self.assertTrue(patch_path.exists())
                rc_apply = patch_state_dbs.main(["--apply"])
                self.assertEqual(rc_apply, 0)
                self.assertFalse(patch_path.exists())

            for rel in (
                "equity/state/multi_asset_channels.json",
                "equity/state/etf_universe.json",
                "equity/state/deep_dossiers.json",
            ):
                mode = stat.S_IMODE((sandbox / rel).stat().st_mode)
                self.assertEqual(mode, 0o644, f"{rel} expected 0o644, got {oct(mode)}")

            ch_after = json.loads((sandbox / "equity/state/multi_asset_channels.json").read_text(encoding="utf-8"))
            etf_after = json.loads((sandbox / "equity/state/etf_universe.json").read_text(encoding="utf-8"))
            dos_after = json.loads((sandbox / "equity/state/deep_dossiers.json").read_text(encoding="utf-8"))
            self.assertEqual(ch_after["edition_id"], next_ed)
            self.assertEqual(etf_after["edition_id"], next_ed)
            self.assertEqual(dos_after["edition_id"], next_ed)
            self.assertEqual(dos_after["dossiers"][sample_a_key]["updated_at"], "2099-12-31")
            expected_library_label = "2099年12月31日（周四）23:55 晚刊"
            self.assertEqual(ch_after["as_of_label"], expected_library_label)
            self.assertEqual(etf_after["as_of_label"], expected_library_label)
            self.assertEqual(
                [row for row in etf_after["etfs"] if row["code"] != sample_etf_code],
                [row for row in eu_seed["etfs"] if row["code"] != sample_etf_code],
            )

            written_paths = [sandbox / "equity/state" / name for name in (
                "multi_asset_channels.json", "etf_universe.json", "deep_dossiers.json"
            )]
            before_bad_timestamp = [path.read_bytes() for path in written_paths]
            market_path = sandbox / "equity/state/market_state.json"
            for value in (None, "2099-12-31T23:55:00Z", "2099-12-31T12:00:00+08:00"):
                with self.subTest(market_as_of=value):
                    market_path.write_text(json.dumps(dict(ms_obj, as_of_cst=value)), encoding="utf-8")
                    patch_path.write_text(json.dumps(good_patch), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, r"market_state\.json\.as_of_cst"):
                        patch_state_dbs.apply_equity_patch(sandbox)
                    self.assertEqual([path.read_bytes() for path in written_paths], before_bad_timestamp)
                    self.assertTrue(patch_path.exists())
            market_path.write_text(json.dumps(ms_obj), encoding="utf-8")

            # 2. Gold Tier-0 violation must abort with zero file mutation (explicitly lock snapshot for this subtest)
            before_bytes = (sandbox / "equity/state/multi_asset_channels.json").read_bytes()
            gold_locked_snap = dict(gold_obj, tier_code="Tier 0", new_buy_allowed=False)
            (sandbox / "gold/data_snapshot.json").write_text(
                json.dumps(gold_locked_snap, ensure_ascii=False), encoding="utf-8"
            )
            bad_patch = {
                "edition_id": next_ed,
                "as_of_date": "2099-12-31",
                "gold_tier0_locked": True,
                "multi_asset_channels": {
                    "channels_patch": {
                        "reverse_repo": {"beginner_one_liner": f"{rr_orig_liner}，今日立即买入黄金 518880。"}
                    }
                },
            }
            patch_path.write_text(json.dumps(bad_patch, ensure_ascii=False), encoding="utf-8")
            bad_err = StringIO()
            with patch.object(patch_state_dbs, "REPO_ROOT", sandbox), redirect_stderr(bad_err):
                rc_bad = patch_state_dbs.main(["--apply"])
                self.assertNotEqual(rc_bad, 0)
            self.assertIn("518880", bad_err.getvalue())
            self.assertEqual((sandbox / "equity/state/multi_asset_channels.json").read_bytes(), before_bytes)
            patch_path.unlink()
            # Restore live Gold lock state before subsequent subtests
            (sandbox / "gold/data_snapshot.json").write_text(
                json.dumps(gold_obj, ensure_ascii=False), encoding="utf-8"
            )

            # 2b. Cross-DB fee mismatch (511180 0.20% vs 0.30% in etf_universe.json) must be rejected
            cb_ch = next(c for c in ch_after["channels"] if c["id"] == "convertible_bonds")
            cb_bad_upd = {
                "products_upsert": [{"code": "511180", "fee": "0.20%/年"}],
            }
            for sib_k in ("summary", "beginner_picks"):
                if isinstance(cb_ch.get(sib_k), str) and "0.30%" in cb_ch[sib_k]:
                    cb_bad_upd[sib_k] = cb_ch[sib_k].replace("0.30%", "0.20%")
            fee_mismatch_patch = {
                "edition_id": next_ed,
                "as_of_date": "2099-12-31",
                "gold_tier0_locked": live_gold_locked,
                "multi_asset_channels": {
                    "channels_patch": {"convertible_bonds": cb_bad_upd}
                },
            }
            patch_path.write_text(json.dumps(fee_mismatch_patch, ensure_ascii=False), encoding="utf-8")
            fee_err = StringIO()
            with patch.object(patch_state_dbs, "REPO_ROOT", sandbox), redirect_stderr(fee_err):
                rc_fee = patch_state_dbs.main(["--apply"])
            self.assertNotEqual(rc_fee, 0)
            self.assertIn("511180", fee_err.getvalue())
            self.assertIn("0.30%", fee_err.getvalue())
            self.assertEqual((sandbox / "equity/state/multi_asset_channels.json").read_bytes(), before_bytes)
            patch_path.unlink()

            # 3. Prepend gold ledgers: reject forecast_review.status='tracked', pass full schema, verify 0o644 & idempotency
            ledger_patch = sandbox / "gold/daily/_ledger_patch.json"

            def _make_review(fc_status: str, ed: str = next_ed) -> dict:
                return {
                    "edition_id": ed,
                    "as_of_short": "2099-12-31 23:55",
                    "note": "测试核验通过",
                    "sources": {
                        "real_yield": ["https://home.treasury.gov/resource-center/data-chart-center"],
                        "rate_spread": ["https://www.newyorkfed.org/markets/reference-rates/effr"],
                        "vix": ["https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"],
                        "ny_close": ["https://www.lbma.org.uk/prices-and-data/precious-metal-prices"],
                    },
                    "forecast_review": {"status": fc_status, "note": "无到期项", "sources": []},
                }

            bad_ledger_payload = {
                "edition_id": next_ed,
                "changelog_entry_md": (
                    f"<!-- GOLD_EDITION_CHANGELOG {next_ed} -->\n\n"
                    f"### {next_ed} 修订刊记录\n\n- 完成测试无损头插验收。\n"
                ),
                "audit_review_block_md": (
                    f"<!-- GOLD_EDITION_REVIEW {json.dumps(_make_review('tracked'), ensure_ascii=False)} -->\n"
                    f"### {next_ed} 审计记录\n\n- 审计测试。\n"
                ),
            }
            ledger_patch.write_text(json.dumps(bad_ledger_payload, ensure_ascii=False), encoding="utf-8")
            tracked_err = StringIO()
            with patch.object(patch_state_dbs, "REPO_ROOT", sandbox), redirect_stderr(tracked_err):
                rc_tracked = patch_state_dbs.main(["--prepend-gold-ledgers"])
            self.assertNotEqual(rc_tracked, 0)
            self.assertIn("forecast_review.status", tracked_err.getvalue())

            ledger_payload = {
                "edition_id": next_ed,
                "changelog_entry_md": (
                    f"<!-- GOLD_EDITION_CHANGELOG {next_ed} -->\n\n"
                    f"### {next_ed} 修订刊记录\n\n- 完成测试无损头插验收。\n"
                ),
                "audit_review_block_md": (
                    f"<!-- GOLD_EDITION_REVIEW {json.dumps(_make_review('none_due'), ensure_ascii=False)} -->\n"
                    f"### {next_ed} 审计记录\n\n- 审计测试通过。\n"
                ),
            }
            orig_cl_lines = [l for l in (sandbox / "gold/daily/CHANGELOG.md").read_text(encoding="utf-8").splitlines() if l.strip()]
            ledger_patch.write_text(json.dumps(ledger_payload, ensure_ascii=False), encoding="utf-8")
            with patch.object(patch_state_dbs, "REPO_ROOT", sandbox):
                rc_led = patch_state_dbs.main(["--prepend-gold-ledgers"])
                self.assertEqual(rc_led, 0)
                self.assertFalse(ledger_patch.exists())
                # Duplicate edition_id must be rejected idempotently
                ledger_patch.write_text(json.dumps(ledger_payload, ensure_ascii=False), encoding="utf-8")
                rc_dup = patch_state_dbs.main(["--prepend-gold-ledgers"])
                self.assertNotEqual(rc_dup, 0)
                ledger_patch.unlink()

            for rel in ("gold/daily/CHANGELOG.md", "gold/daily/AUDIT_LOG.md"):
                mode = stat.S_IMODE((sandbox / rel).stat().st_mode)
                self.assertEqual(mode, 0o644, f"{rel} expected 0o644, got {oct(mode)}")

            new_cl = (sandbox / "gold/daily/CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn(f"<!-- GOLD_EDITION_CHANGELOG {next_ed} -->", new_cl)
            new_cl_lines = [l for l in new_cl.splitlines() if l.strip()]
            # Every prior nonblank line preserved in exact original order
            it = iter(new_cl_lines)
            for orig in orig_cl_lines:
                self.assertTrue(any(line == orig for line in it), f"Lost line: {orig}")

            # 4. Monthly-rollover empty-anchor fallback succeeds when fresh-month ledgers lack prior GOLD_EDITION_* markers
            roll_ed = "2099-12-31_1800_r100"
            gold_obj["edition_id"] = roll_ed
            (sandbox / "gold/data_snapshot.json").write_text(
                json.dumps(gold_obj, ensure_ascii=False), encoding="utf-8"
            )
            (sandbox / "gold/daily/CHANGELOG.md").write_text(
                "# 黄金日报演化日志（2099 年 12 月新卷）\n\n---\n", encoding="utf-8"
            )
            (sandbox / "gold/daily/AUDIT_LOG.md").write_text(
                "# 黄金日报核验台账（2099 年 12 月新卷）\n\n---\n", encoding="utf-8"
            )
            roll_payload = {
                "edition_id": roll_ed,
                "changelog_entry_md": (
                    f"<!-- GOLD_EDITION_CHANGELOG {roll_ed} -->\n\n"
                    f"### {roll_ed} 月初新卷首刊\n\n- 跨月空锚回退验证通过。\n"
                ),
                "audit_review_block_md": (
                    f"<!-- GOLD_EDITION_REVIEW {json.dumps(_make_review('none_due', ed=roll_ed), ensure_ascii=False)} -->\n"
                    f"### {roll_ed} 审计记录\n\n- 跨月首刊审计通过。\n"
                ),
            }
            ledger_patch.write_text(json.dumps(roll_payload, ensure_ascii=False), encoding="utf-8")
            with patch.object(patch_state_dbs, "REPO_ROOT", sandbox):
                rc_roll = patch_state_dbs.main(["--prepend-gold-ledgers"])
                self.assertEqual(rc_roll, 0)
            self.assertIn(f"<!-- GOLD_EDITION_CHANGELOG {roll_ed} -->", (sandbox / "gold/daily/CHANGELOG.md").read_text("utf-8"))
            self.assertIn(f'"edition_id": "{roll_ed}"', (sandbox / "gold/daily/AUDIT_LOG.md").read_text("utf-8"))

    def test_restricted_warn_regex_parity_across_validators(self):
        repo = Path(__file__).resolve().parent.parent
        equity_dir = str(repo / "equity")
        if equity_dir not in sys.path:
            sys.path.insert(0, equity_dir)
        import lint_equity

        self.assertEqual(patch_state_dbs.RESTRICTED_WARN_RE.pattern, lint_equity.RESTRICTED_WARN_RE.pattern)
        self.assertEqual(lint_equity.RESTRICTED_WARN_RE.pattern, lint_site.RESTRICTED_WARN_RE.pattern)
        for regex in (
            patch_state_dbs.RESTRICTED_WARN_RE,
            lint_equity.RESTRICTED_WARN_RE,
            lint_site.RESTRICTED_WARN_RE,
        ):
            self.assertIsNotNone(regex.search("严避停申968118"))
            self.assertIsNone(regex.search("推荐买入968118"))

    def test_etf_orthogonal_enum_parity_across_validators(self):
        repo = Path(__file__).resolve().parent.parent
        equity_dir = str(repo / "equity")
        if equity_dir not in sys.path:
            sys.path.insert(0, equity_dir)
        import lint_equity

        expected_ac = {"equity", "fixed_income", "gold", "commodity", "cash_mmf", "convertible_bond", "reits"}
        expected_rg = {"cn", "hk", "us", "jp", "eu", "apac_em", "global"}

        psd_ac = set(
            getattr(patch_state_dbs, "ETF_ALLOWED_ASSET_CLASSES", None)
            or patch_state_dbs._ETF_ALLOWED_ASSET_CLASSES
        )
        eq_ac = set(
            getattr(lint_equity, "ETF_ALLOWED_ASSET_CLASSES", None)
            or lint_equity._ETF_ALLOWED_ASSET_CLASSES
        )
        site_ac = set(
            getattr(lint_site, "ETF_ALLOWED_ASSET_CLASSES", None)
            or lint_site._ETF_ALLOWED_ASSET_CLASSES
        )

        psd_rg = set(
            getattr(patch_state_dbs, "ETF_ALLOWED_REGIONS", None)
            or patch_state_dbs._ETF_ALLOWED_REGIONS
        )
        eq_rg = set(
            getattr(lint_equity, "ETF_ALLOWED_REGIONS", None)
            or lint_equity._ETF_ALLOWED_REGIONS
        )
        site_rg = set(
            getattr(lint_site, "ETF_ALLOWED_REGIONS", None)
            or lint_site._ETF_ALLOWED_REGIONS
        )

        self.assertEqual(psd_ac, expected_ac)
        self.assertEqual(eq_ac, expected_ac)
        self.assertEqual(site_ac, expected_ac)
        self.assertEqual(psd_ac, eq_ac)
        self.assertEqual(eq_ac, site_ac)

        self.assertEqual(psd_rg, expected_rg)
        self.assertEqual(eq_rg, expected_rg)
        self.assertEqual(site_rg, expected_rg)
        self.assertEqual(psd_rg, eq_rg)
        self.assertEqual(eq_rg, site_rg)

    def test_edition_run_midnight_slot_and_complete_superseded_cli(self):
        repo = Path(__file__).resolve().parent.parent
        perms = json.loads((repo / "automations" / "permissions.json").read_text(encoding="utf-8"))
        self.assertFalse(any("complete-superseded" in str(g) for g in perms))

        class _FrozenDateTime(datetime):
            _now: datetime = datetime(2026, 11, 26, 23, 59, tzinfo=edition_run.BEIJING)

            @classmethod
            def now(cls, tz=None):
                return cls._now if tz is None else cls._now.astimezone(tz)

        with patch.object(edition_run, "datetime", _FrozenDateTime):
            _FrozenDateTime._now = datetime(2026, 11, 26, 23, 59, tzinfo=edition_run.BEIJING)
            self.assertEqual(edition_run.scheduled_edition("1800"), "2026-11-26_1800")

            _FrozenDateTime._now = datetime(2026, 11, 27, 0, 0, tzinfo=edition_run.BEIJING)
            self.assertEqual(edition_run.scheduled_edition("1800"), "2026-11-26_1800")

            _FrozenDateTime._now = datetime(2026, 11, 27, 0, 1, tzinfo=edition_run.BEIJING)
            with self.assertRaisesRegex(ValueError, "Outside the Beijing run window"):
                edition_run.scheduled_edition("1800")

        # Verify complete_superseded rejects non-ancestor commits & unauthorized gold/ content diffs cleanly
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def _git(*args):
                return subprocess.run(
                    ["git", "-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", *args],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()

            with patch.object(edition_run, "ROOT", root):
                _git("init", "-q")
                for relative in edition_run.GOLD_HISTORY_LEDGERS:
                    ledger = root / relative
                    ledger.parent.mkdir(parents=True, exist_ok=True)
                    ledger.write_text("## Previous edition\n\n- Original evidence\n", encoding="utf-8")
                (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
                _git("add", ".")
                _git("commit", "-qm", "Base commit")
                base_sha = _git("rev-parse", "HEAD")

                runs = edition_run.open_runs()
                try:
                    ed = "2026-11-26_1800"
                    token = edition_run.begin(runs, ed)
                    attempt = token[:12]
                    with runs:
                        edition_run.advance(runs, token, "gold")
                    for name in ("gold/data_snapshot.json", "equity/state/market_state.json"):
                        p = root / name
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(json.dumps({"edition_id": ed}), encoding="utf-8")
                    with runs:
                        edition_run.advance(runs, token, "equity")
                    for name in ("gold/daily/rsi_metrics.json", "equity/state/rsi_metrics.json"):
                        p = root / name
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(
                            json.dumps({"runs": [{"run_id": ed, "review_closure": {"reviewer_completed": True, "findings": []}}]}),
                            encoding="utf-8",
                        )
                    with runs:
                        edition_run.advance(runs, token, "publish")
                    _git("add", "gold", "equity")
                    _git("commit", "-qm", "Edition commit")
                    orig_sha = _git("rev-parse", "HEAD")
                    edition_run.record_push(token, sha=orig_sha, repository="org/repo")

                    # 1. Non-ancestor commit (base_sha is ancestor of orig_sha, NOT descendant) rejected
                    with self.assertRaisesRegex(ValueError, "not an ancestor"):
                        edition_run.complete_superseded(runs, ed, attempt, base_sha, "bad ancestor")

                    # 2. Unauthorized gold/ follow-up diff rejected when allow_content_hotfix=False
                    (root / "gold/daily/extra.md").write_text("# Unauthorized gold edit\n", encoding="utf-8")
                    _git("add", "gold/daily/extra.md")
                    _git("commit", "-qm", "Unauthorized gold diff")
                    bad_gold_sha = _git("rev-parse", "HEAD")
                    with patch.object(edition_run, "_remote_main_head_sha", return_value=bad_gold_sha), patch.object(
                        edition_run, "verify_pages", return_value="https://example.invalid/site/"
                    ):
                        with self.assertRaisesRegex(ValueError, "modified content paths"):
                            edition_run.complete_superseded(runs, ed, attempt, bad_gold_sha, "gold diff test")

                    # 3. Clean non-content follow-up commit (e.g. README.md only) completes cleanly
                    _git("reset", "--hard", orig_sha)
                    (root / "README.md").write_text("# Fixture updated\n", encoding="utf-8")
                    _git("add", "README.md")
                    _git("commit", "-qm", "Docs follow-up")
                    clean_sha = _git("rev-parse", "HEAD")
                    with patch.object(edition_run, "_remote_main_head_sha", return_value=clean_sha), patch.object(
                        edition_run, "verify_pages", return_value="https://example.invalid/site/"
                    ):
                        url = edition_run.complete_superseded(runs, ed, attempt, clean_sha, "follow-up docs deploy")
                    self.assertEqual(url, "https://example.invalid/site/")
                    row = runs.execute("SELECT status FROM runs WHERE token = ?", (token,)).fetchone()
                    pub = runs.execute("SELECT deployed_sha FROM publications WHERE token = ?", (token,)).fetchone()
                    self.assertEqual(row["status"], "complete")
                    self.assertEqual(pub["deployed_sha"], clean_sha)
                finally:
                    runs.close()

    def test_prompt_has_zero_shell_metacharacters_and_within_line_budget(self):
        repo = Path(__file__).resolve().parent.parent
        prompt_text = (repo / "automations" / "unified-edition.prompt.md").read_text(encoding="utf-8")
        lines = prompt_text.splitlines()
        self.assertLessEqual(len(lines), 62)
        self.assertIn("17:55–次日 00:00", prompt_text)
        self.assertNotIn("17:55–23:59", prompt_text)
        for token in ("&&", "||", "$(", ";"):
            self.assertNotIn(token, prompt_text, f"Forbidden shell token {token!r} in unified-edition.prompt.md")
        for _, tpl_path in install_sidecars.discover_templates(repo / "automations" / "sidecars"):
            install_sidecars.render_template(tpl_path, repo, sys.executable)

    def test_complete_superseded_allows_explicit_content_hotfix_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def _git(*args):
                return subprocess.run(
                    ["git", "-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", *args],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()

            with patch.object(edition_run, "ROOT", root):
                _git("init", "-q")
                for relative in edition_run.GOLD_HISTORY_LEDGERS:
                    ledger = root / relative
                    ledger.parent.mkdir(parents=True, exist_ok=True)
                    ledger.write_text("## Previous edition\n\n- Original evidence\n", encoding="utf-8")
                _git("add", ".")
                _git("commit", "-qm", "Base commit")

                runs = edition_run.open_runs()
                try:
                    ed = "2026-11-26_1800"
                    token = edition_run.begin(runs, ed)
                    attempt = token[:12]
                    with runs:
                        edition_run.advance(runs, token, "gold")
                    for name in ("gold/data_snapshot.json", "equity/state/market_state.json"):
                        p = root / name
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(json.dumps({"edition_id": ed}), encoding="utf-8")
                    with runs:
                        edition_run.advance(runs, token, "equity")
                    for name in ("gold/daily/rsi_metrics.json", "equity/state/rsi_metrics.json"):
                        p = root / name
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(
                            json.dumps({"runs": [{"run_id": ed, "review_closure": {"reviewer_completed": True, "findings": []}}]}),
                            encoding="utf-8",
                        )
                    with runs:
                        edition_run.advance(runs, token, "publish")
                    _git("add", "gold", "equity")
                    _git("commit", "-qm", "Edition commit")
                    orig_sha = _git("rev-parse", "HEAD")
                    edition_run.record_push(token, sha=orig_sha, repository="org/repo")

                    (root / "gold/daily/hotfix_note.md").write_text("# Intentional content hotfix\n", encoding="utf-8")
                    _git("add", "gold/daily/hotfix_note.md")
                    _git("commit", "-qm", "Intentional content hotfix")
                    hotfix_sha = _git("rev-parse", "HEAD")
                    with patch.object(edition_run, "_remote_main_head_sha", return_value=hotfix_sha), patch.object(
                        edition_run, "verify_pages", return_value="https://example.invalid/hotfix/"
                    ):
                        url = edition_run.complete_superseded(
                            runs, ed, attempt, hotfix_sha, "intentional hotfix", allow_content_hotfix=True
                        )
                    self.assertEqual(url, "https://example.invalid/hotfix/")
                    row = runs.execute("SELECT status FROM runs WHERE token = ?", (token,)).fetchone()
                    self.assertEqual(row["status"], "complete")
                finally:
                    runs.close()

    def test_midday_1130_slot_window_reaping_publish_and_gold_validation(self):
        # 1. edition_run 1130 window boundaries (11:24 reject, 11:25 accept, 17:30 accept, 17:31 reject)
        self.assertEqual(edition_run.edition_id("2026-11-27_1130"), "2026-11-27_1130")
        self.assertEqual(edition_run.edition_id("2026-11-27_1130_r2"), "2026-11-27_1130_r2")
        with self.assertRaises(Exception):
            edition_run.edition_id("2026-11-27_1630")

        class _FrozenMiddayDT(datetime):
            _now: datetime = datetime(2026, 11, 27, 11, 25, tzinfo=edition_run.BEIJING)

            @classmethod
            def now(cls, tz=None):
                return cls._now if tz is None else cls._now.astimezone(tz)

        with patch.object(edition_run, "datetime", _FrozenMiddayDT):
            for hour, minute, should_pass in (
                (11, 24, False),
                (11, 25, True),
                (11, 30, True),
                (17, 30, True),
                (17, 31, False),
            ):
                with self.subTest(midday_time=f"{hour:02d}:{minute:02d}"):
                    _FrozenMiddayDT._now = datetime(2026, 11, 27, hour, minute, tzinfo=edition_run.BEIJING)
                    if should_pass:
                        self.assertEqual(edition_run.scheduled_edition("1130"), "2026-11-27_1130")
                    else:
                        with self.assertRaisesRegex(ValueError, "Outside the Beijing run window"):
                            edition_run.scheduled_edition("1130")

        # 2. edition_run stale-lock reaping across 0730 -> 1130 -> 1800
        with tempfile.TemporaryDirectory() as temporary:
            git_dir = Path(temporary)
            with patch.object(edition_run, "git_directory", return_value=git_dir), patch.object(
                edition_run, "git_value", return_value="a" * 40
            ):
                runs = edition_run.open_runs()
                try:
                    t0 = edition_run.begin(runs, "2026-11-27_0730")
                    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(timespec="seconds")
                    with runs:
                        runs.execute("UPDATE runs SET updated = ? WHERE token = ?", (stale_ts, t0))
                    # 1130 cleanly reaps stale unpushed 0730
                    self.assertEqual(
                        edition_run.reap_stale_unpushed_run(runs, "2026-11-27_1130"),
                        "2026-11-27_0730",
                    )
                    t1 = edition_run.begin(runs, "2026-11-27_1130")
                    with runs:
                        runs.execute("UPDATE runs SET updated = ? WHERE token = ?", (stale_ts, t1))
                    # Earlier 0730 must NOT reap newer 1130
                    self.assertIsNone(edition_run.reap_stale_unpushed_run(runs, "2026-11-27_0730"))
                    # Later 1800 cleanly reaps stale unpushed 1130
                    self.assertEqual(
                        edition_run.reap_stale_unpushed_run(runs, "2026-11-27_1800"),
                        "2026-11-27_1130",
                    )
                finally:
                    runs.close()

        # 3. install_sidecars midday template schedule & slot rendering
        repo = Path(__file__).resolve().parent.parent
        templates = dict(install_sidecars.discover_templates(repo / "automations" / "sidecars"))
        self.assertIn("daily-global-investment-research-midday", templates)
        _, midday_def = install_sidecars.render_template(
            templates["daily-global-investment-research-midday"], repo, sys.executable
        )
        self.assertEqual(midday_def["args"][0], "CRON_TZ=Asia/Shanghai 30 11 * * *")
        self.assertIn("begin --scheduled 1130", midday_def["args"][-1])

        # 4. publish_site._latest_daily selects 1130 over 0730, 1800 over 1130, and ignores retired 1630
        with tempfile.TemporaryDirectory() as temporary:
            daily_dir = Path(temporary)
            morn = daily_dir / "2026-11-27_0730_早报_黄金深度研报.md"
            mid = daily_dir / "2026-11-27_1130_午报_黄金深度研报.md"
            retired = daily_dir / "2026-11-27_1630_午报_黄金深度研报.md"
            for p in (morn, mid, retired):
                p.write_text("# test\n", encoding="utf-8")
            self.assertEqual(publish_site._latest_daily(daily_dir, publish_site.GOLD_DAILY_RE), mid)
            eve = daily_dir / "2026-11-27_1800_晚报_黄金深度研报.md"
            eve.write_text("# test\n", encoding="utf-8")
            self.assertEqual(publish_site._latest_daily(daily_dir, publish_site.GOLD_DAILY_RE), eve)

        # 5. gold/edition_validation 1130 window + Thanksgiving VIX holiday check + optional index_matrix
        gold_dir = str(repo / "gold")
        if gold_dir not in sys.path:
            sys.path.insert(0, gold_dir)
        import edition_validation as gold_ev
        import lint_readability as gold_lint

        for hh, mm, ok in ((11, 24, False), (11, 25, True), (11, 30, True), (17, 30, True), (17, 31, False)):
            errs = []
            res = gold_ev.check_edition_time(("2026-11-27", "1130", 1), datetime(2026, 11, 27, hh, mm), errs)
            self.assertEqual(res, ok, f"{hh:02d}:{mm:02d} -> {errs}")
            self.assertEqual(bool(errs), not ok)

        with tempfile.TemporaryDirectory() as temporary:
            tmp_snap = Path(temporary) / "data_snapshot.json"
            tmp_cal = Path(temporary) / "market_calendar.json"
            # 100% self-contained synthetic snapshot + synthetic calendar (zero live-repo coupling)
            synth_cal = {
                "timezone": "Asia/Shanghai",
                "coverage": {
                    "start_date": "2026-11-01",
                    "end_date": "2027-01-31",
                    "verified_on": "2026-11-26",
                    "vix_schedule_source": "https://www.cboe.com/about/hours/us-options/",
                },
                "calendar_overrides": [
                    {
                        "id": "thanksgiving_synth_2026",
                        "date": "2026-11-26",
                        "end_date": "2026-11-27",
                        "markets": ["US_EQUITY"],
                        "overlay_mode": "A",
                    }
                ],
                "vix_session_exceptions": {
                    "2026-11-26": {
                        "windows_et": [],
                        "official_close_et": None,
                        "daily_row_check_after_et": "11:30",
                    },
                    "2026-11-27": {
                        "windows_et": [["03:15", "09:25"], ["09:31", "13:00"]],
                        "official_close_et": None,
                        "daily_row_check_after_et": "13:15",
                    },
                },
            }
            tmp_cal.write_text(json.dumps(synth_cal, ensure_ascii=False), encoding="utf-8")

            ny_close = 3588.78
            snap = {
                "edition_id": "2026-11-27_1130",
                "as_of_short": "2026-11-27 11:30",
                "as_of_bjt": "2026年11月27日（周五）11:30",
                "tier_code": "Tier 0",
                "new_buy_allowed": False,
                "daily_alert_level": "L1",
                "a_class_tranche_split": "30% + 45% + 25%",
                "cfets_fixing_date": "2026-11-27",
                "cfets_cny_fixing": 6.71,
                "us10y_pct": 4.84,
                "us2y_pct": 4.604,
                "effr_pct": 3.88,
                "spread_2y_ff_bp": 72.4,
                "dfii10_fred_official_pct": 2.79,
                "dfii10_live_pct": 2.79,
                "dxy": 104.2,
                "on_rrp_usd_m": 301.0,
                "comex_copper_usd_lb": 5.36,
                "spot_gold_ny_close_usd": ny_close,
                "spot_gold_ny_close_rounded": 3589,
                "spot_gold_prev_close_usd": 3635.24,
                "spot_gold_ny_change_pct": round(((ny_close / 3635.24) - 1.0) * 100.0, 2),
                "spot_gold_ny_close_date": "2026-11-25",
                "tier1_gate4_threshold_usd": round(ny_close + 25.0, 2),
                "tier1_gate4_threshold_date": "2026-11-24",
                "tier1_gate4_target_date": "2026-11-25",
                "wti_settle_usd": 80.0,
                "brent_settle_usd": 90.0,
                "spot_silver_usd": 41.0,
                "spx_close": 7200.0,
                "spot_platinum_usd": 1258.0,
                "rmb_channels": {
                    "brand_store_rmb": 1068.0,
                    "bank_bar_plus_craft_rmb": 796.0,
                    "wedding_save_per_g_rmb": 272.0,
                    "wedding_save_50g_rmb": 13600.0,
                    "wedding_save_pct": 25.47,
                },
                "institutional_targets": [
                    {"name": "示例甲", "kind": "pt", "lo": 4300, "base": 4500, "hi": 4700},
                    {"name": "示例乙", "kind": "avg", "lo": 4400, "base": 4600, "hi": 4800},
                ],
                "bank_2027_yearend_sample_count": 1,
                "bank_2027_yearend_median_usd": 4500,
                "bank_2027_avg_sample_count": 1,
                "bank_2027_avg_median_usd": 4600,
                "vix_close": 28.29,
                "vix_live": None,
                "vix_live_as_of": None,
                "vix_10d_window_end": "2026-11-25",
                "vix_10d_peak_close": 35.89,
                "vix_10d_peak_date": "2026-11-20",
                "vix_daily_source": gold_ev.VIX_DAILY_SOURCE,
                "vix_10d_session_closes": [
                    {"date": "2026-11-12", "close": 21.05},
                    {"date": "2026-11-13", "close": 19.3},
                    {"date": "2026-11-16", "close": 22.91},
                    {"date": "2026-11-17", "close": 25.46},
                    {"date": "2026-11-18", "close": 24.56},
                    {"date": "2026-11-19", "close": 28.44},
                    {"date": "2026-11-20", "close": 35.89},
                    {"date": "2026-11-23", "close": 26.62},
                    {"date": "2026-11-24", "close": 26.36},
                    {"date": "2026-11-25", "close": 28.29},
                ],
                "vix_daily_row_checks": {
                    "2026-11-25": {
                        "status": "published",
                        "checked_at": "2026-11-26 23:45",
                        "source": gold_ev.VIX_DAILY_SOURCE,
                        "note": "synthetic 2026-11-27 11:30 fixture",
                    },
                    "2026-11-26": {
                        "status": "no_row_confirmed",
                        "checked_at": "2026-11-27 11:20",
                        "source": gold_ev.VIX_DAILY_SOURCE,
                        "confirmation_source": "https://www.cboe.com/about/hours/us-options/",
                        "note": "synthetic 2026-11-27 11:30 Thanksgiving no-row fixture",
                    },
                },
                "index_matrix": {"shcomp": {"close": 4012.5, "chg_pct": 0.42}},
            }
            snap["cross_ratios"] = {
                name: snap["spot_gold_ny_close_usd"] / snap[denominator]
                for name, (denominator, _) in gold_lint.RATIO_FIELDS.items()
            }
            g1_pass = float(snap["dfii10_fred_official_pct"]) <= 2.72
            g2_pass = round((float(snap["us2y_pct"]) - float(snap["effr_pct"])) * 100.0, 2) <= 55.0
            g_flags = (g1_pass, g2_pass, True, False)
            snap["tier1_gates"] = [
                {"id": gid, "passed": p_flag, "name": "条件", "reading": "读数", "threshold": "门槛", "detail": "证据"}
                for gid, p_flag in zip(gold_ev.ENTRY_GATE_IDS, g_flags)
            ]
            snap["tier1_passed"] = sum(1 for x in g_flags if x)
            snap["tier1_total"] = 4

            tmp_snap.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            errs, warns = [], []
            with patch.multiple(gold_lint, DAILY_SNAPSHOT_PATH=tmp_snap, MARKET_CALENDAR_PATH=tmp_cal):
                gold_lint.validate_snapshot_file(tmp_snap, errs, warns, validated_on=date(2026, 11, 27))
            self.assertEqual(errs, [])
            self.assertEqual(warns, [])

    def test_upgraded_prompt_institutional_contract_and_56_grants(self):
        repo = Path(__file__).resolve().parent.parent
        grants = json.loads((repo / "automations" / "permissions.json").read_text(encoding="utf-8"))
        self.assertEqual(len(grants), 56)

        prompt_text = (repo / "automations" / "unified-edition.prompt.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(prompt_text.splitlines()), 62)
        for req in (
            "__RUN_SLOT__",
            "__REPO_ROOT__",
            "__PYTHON_BIN__",
            "17:55–次日 00:00",
            "begin --scheduled __RUN_SLOT__",
            "publish_site.py --edition-token",
            ".agents/skills/equity-research-editorial-qa/references/master-research-and-sources-playbook.md",
            "Due-Backfill Sweep",
            "Cutoff Drift Guard",
            "StockAnalysis",
            "Barchart",
            "空付多↔多付空",
            "CBBC",
            "Fed BS",
            "【事前验尸】",
            "4-3-2-1",
            "Evening Midday-Residue Sweep",
            "5 大触发",
            "DAILY_VISUAL",
            "#sec-market-news",
            "home_featured",
        ):
            self.assertIn(req, prompt_text, f"Missing required upgraded prompt token: {req!r}")

    def test_kline_cmd_hg_cents_normalization_oil_label_and_fx_t0_freshness(self):
        specs = {s.id: s for s in fetch_kline_data.build_core_specs()}
        hg_spec = specs["cmd_HG"]
        self.assertEqual(hg_spec.unit, "美元/磅")
        self.assertEqual(hg_spec.price_divisor_if_gt, (50.0, 100.0))
        self.assertEqual(specs["cmd_OIL"].name, "布伦特原油主力连续")

        # Live Sina cents/lb bars (>50) normalize ÷100 to 4-decimal USD/lb; already-USD bars stay idempotent
        raw_hg = [
            ["2026-11-26", "548.050", "555.350", "542.850", "543.350", "0"],
            ["2026-11-27", "548.050", "576.050", "542.850", "567.350", "0"],
        ]
        norm = fetch_kline_data.sanitize_bars(
            raw_hg,
            decimals_override=hg_spec.decimals_override,
            price_divisor_if_gt=hg_spec.price_divisor_if_gt,
        )
        self.assertEqual(
            norm,
            [
                ["2026-11-26", 5.4805, 5.5535, 5.4285, 5.4335, 0],
                ["2026-11-27", 5.4805, 5.7605, 5.4285, 5.6735, 0],
            ],
        )
        self.assertEqual(
            fetch_kline_data.sanitize_bars(
                norm,
                decimals_override=hg_spec.decimals_override,
                price_divisor_if_gt=hg_spec.price_divisor_if_gt,
            ),
            norm,
        )

        # Stale-cache fallback also normalizes legacy cents bars cleanly
        rec, fail = fetch_kline_data.merge_with_stale_cache(
            hg_spec,
            [],
            None,
            "simulated_timeout",
            {"provider": "sina_global_futures", "bars": raw_hg},
            bars_limit=150,
        )
        self.assertIsNotNone(rec)
        self.assertIsNotNone(fail)
        assert rec is not None
        self.assertEqual(rec["latest_close"], 5.6735)
        self.assertEqual(rec["bars"][-1], ["2026-11-27", 5.4805, 5.7605, 5.4285, 5.6735, 0])

        # Sina FX T-0 batch quotes: Sat <06:30 CST maps to Friday NY session; Sat >=06:30 / Sun skipped
        raw_fx_quotes = (
            'var hq_str_fx_susdcnh="00:42:33,6.6560,6.6563,6.6613,139,6.6615,6.6668,6.6529,6.6560,离岸人民币,-0.08,-0.0053,0.002,,6.99,6.64,,2026-11-28";\n'
            'var hq_str_fx_susdjpy="08:00:00,159.48,159.52,159.25,10,159.25,159.59,159.12,159.48,日元,0.14,0.23,0.002,,163.9,152.1,,2026-11-28";\n'
            'var hq_str_fx_seurusd="14:00:00,1.0938,1.0939,1.0967,52,1.0973,1.0986,1.0934,1.0938,欧元,-0.26,-0.0029,0.004,,1.20,1.08,,2026-11-27";\n'
        )
        parsed_q = fetch_kline_data.parse_sina_fx_quotes(raw_fx_quotes)
        self.assertEqual(parsed_q["fx_susdcnh"], ["2026-11-27", 6.6615, 6.6668, 6.6529, 6.656, 0])
        self.assertNotIn("fx_susdjpy", parsed_q)
        self.assertEqual(parsed_q["fx_seurusd"], ["2026-11-27", 1.0973, 1.0986, 1.0934, 1.0938, 0])
        merged = fetch_kline_data.merge_cnbc_t0_quote(
            [["2026-11-26", 6.6687, 6.6699, 6.658, 6.6613, 0]],
            parsed_q["fx_susdcnh"],
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[-1][0], "2026-11-27")
        # Does not duplicate when historical feed already has 2026-11-27
        merged_dup = fetch_kline_data.merge_cnbc_t0_quote(merged, parsed_q["fx_susdcnh"])
        self.assertEqual(len(merged_dup), 2)

    def test_gh_json_retries_once_without_proxy_env_on_proxy_failure(self):
        calls: list[dict[str, str]] = []

        def _fake_run(cmd, cwd=None, env=None, capture_output=True, text=True, timeout=30):
            calls.append(dict(env or {}))
            if len(calls) == 1:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="proxyconnect tcp: connection refused")
            return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true, "sha": "abc123"}', stderr="")

        proxy_env = {
            "PATH": "/usr/bin",
            "http_proxy": "http://127.0.0.1:7890",
            "https_proxy": "http://127.0.0.1:7890",
            "ALL_PROXY": "socks5://127.0.0.1:7891",
        }
        with (
            patch.object(edition_run.shutil, "which", return_value="/usr/local/bin/gh"),
            patch.object(edition_run, "_clean_env", return_value=proxy_env),
            patch.object(edition_run.subprocess, "run", side_effect=_fake_run),
        ):
            res = edition_run._gh_json("api", "repos/owner/repo")

        self.assertEqual(res, {"ok": True, "sha": "abc123"})
        self.assertEqual(len(calls), 2)
        self.assertIn("https_proxy", calls[0])
        for pk in edition_run._PROXY_ENV_VARS:
            self.assertNotIn(pk, calls[1], f"Proxy env var {pk} was not stripped on direct retry")

        # Also retries once on TimeoutExpired when proxy is active; fails clearly if retry fails
        calls_fail: list[dict[str, str]] = []

        def _fake_run_timeout(cmd, cwd=None, env=None, capture_output=True, text=True, timeout=30):
            calls_fail.append(dict(env or {}))
            if len(calls_fail) == 1:
                raise subprocess.TimeoutExpired(cmd, timeout)
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="still unreachable")

        with (
            patch.object(edition_run.shutil, "which", return_value="/usr/local/bin/gh"),
            patch.object(edition_run, "_clean_env", return_value=proxy_env),
            patch.object(edition_run.subprocess, "run", side_effect=_fake_run_timeout),
        ):
            with self.assertRaisesRegex(ValueError, "direct retry after proxy failure"):
                edition_run._gh_json("api", "repos/owner/repo")
        self.assertEqual(len(calls_fail), 2)

        # Without proxy vars, fails immediately on first error (no spurious retry)
        calls_direct: list[int] = []

        def _fake_run_no_proxy(cmd, cwd=None, env=None, capture_output=True, text=True, timeout=30):
            calls_direct.append(1)
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="404 Not Found")

        with (
            patch.object(edition_run.shutil, "which", return_value="/usr/local/bin/gh"),
            patch.object(edition_run, "_clean_env", return_value={"PATH": "/usr/bin"}),
            patch.object(edition_run.subprocess, "run", side_effect=_fake_run_no_proxy),
        ):
            with self.assertRaisesRegex(ValueError, "404 Not Found"):
                edition_run._gh_json("api", "repos/owner/repo")
        self.assertEqual(len(calls_direct), 1)

    def test_deploy_pages_workflow_scopes_concurrency_to_deploy_job(self):
        wf_path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "deploy-pages.yml"
        lines = wf_path.read_text(encoding="utf-8").splitlines()
        # Top-level (indent 0) MUST NOT declare concurrency: so PR builds & main builds are never mutually cancelled
        top_level_concurrency = [ln for ln in lines if ln.startswith("concurrency:")]
        self.assertEqual(top_level_concurrency, [], "deploy-pages.yml must NOT have top-level concurrency:")

        # jobs.deploy MUST scope concurrency: group "pages" with cancel-in-progress: false
        deploy_idx = next((i for i, ln in enumerate(lines) if ln.rstrip() == "  deploy:"), None)
        self.assertIsNotNone(deploy_idx, "Missing jobs.deploy section in deploy-pages.yml")
        assert deploy_idx is not None
        deploy_block = "\n".join(lines[deploy_idx:])
        self.assertNotIn("pages: write", "\n".join(lines[:deploy_idx]))
        self.assertNotIn("id-token: write", "\n".join(lines[:deploy_idx]))
        self.assertIn("    permissions:\n      contents: read\n      pages: write\n      id-token: write", deploy_block)
        self.assertIn("    concurrency:", deploy_block)
        self.assertIn('group: "pages"', deploy_block)
        self.assertIn("cancel-in-progress: false", deploy_block)


if __name__ == "__main__":
    unittest.main()
