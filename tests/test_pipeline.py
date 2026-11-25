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


if __name__ == "__main__":
    unittest.main()
