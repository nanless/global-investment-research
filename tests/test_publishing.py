from contextlib import closing, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import install_sidecars, publish_site as publish


class SidecarRuntimeTests(unittest.TestCase):
    def test_presets_with_the_terminal_sandbox_disabled_fail_the_runtime_check(self):
        sidecar_id = "test-sidecar"
        project_id = "test-project"
        folder_uri = "file:///repo"
        rendered = {
            sidecar_id: ("", {"agent_permissions": {"workspace_uris": [folder_uri], "access_grants": []}}),
        }
        registry = {"sidecars": {sidecar_id: {
            "enabled": True,
            "projectId": project_id,
            "resolvedPermissions": {"workspaceUris": [folder_uri], "accessGrants": []},
        }}}
        project = {
            "id": project_id,
            "sidecar": {"sidecarId": sidecar_id},
            "projectResources": {"resources": [{"folderUri": folder_uri}]},
            "permissionGrants": {"permissionGrants": {"allow": []}},
            "settings": {"sandboxMode": True},
        }
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "registry.json"
            project_path = root / "projects" / f"{project_id}.json"
            project_path.parent.mkdir()
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            for preset in ("AGENT_PERMISSION_PRESET_TURBO", "AGENT_PERMISSION_PRESET_REQUEST_REVIEW"):
                with self.subTest(preset=preset):
                    project["settings"]["permissionPreset"] = preset
                    project_path.write_text(json.dumps(project), encoding="utf-8")
                    problems = install_sidecars.check_registry(registry_path, rendered)
                    self.assertEqual(len(problems), 1)
                    self.assertIn(preset, problems[0])

            project["settings"]["permissionPreset"] = "AGENT_PERMISSION_PRESET_DEFAULT"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            self.assertEqual(install_sidecars.check_registry(registry_path, rendered), [])


class DailyDiscoveryTests(unittest.TestCase):
    def test_archive_discovery_ignores_historical_midday_and_rejects_duplicates(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            daily = root / "equity" / "daily"
            archive = daily / "archive" / "2026-11"
            archive.mkdir(parents=True)
            archived = archive / "2026-11-23_1800_a_share.md"
            old_midday = daily / "2026-11-24_1630_a_share.md"
            for path in (archived, old_midday):
                path.write_text(path.name, encoding="utf-8")

            pattern = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{4})_a_share(?:_r(\d+))?\.md")
            selected = publish._latest_daily(daily, pattern)
            self.assertEqual(selected, archived)

            duplicate = daily / archived.name
            duplicate.write_text("duplicate scheduled issue", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Duplicate scheduled issue"):
                publish._latest_daily(daily, pattern)


class PublicationEntryTests(unittest.TestCase):
    def test_explicit_publication_modes_cannot_ignore_each_other(self):
        for args in (["--dry-run", "--check-manuscripts"], ["--dry-run", "--no-push"]):
            with self.subTest(args=args), redirect_stderr(StringIO()) as failure:
                with self.assertRaises(SystemExit) as exc:
                    publish.parse_args(args)
                self.assertEqual(exc.exception.code, 2)
                self.assertIn("not allowed with argument", failure.getvalue())

    def test_manual_and_ci_checks_require_the_gold_manuscript_at_the_snapshot_edition(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            current, previous = "2026-11-28_1130", "2026-11-28_0730"
            for relative in (*publish.pages_release.EDITION_PATHS, *publish.EXTENDED_EQUITY_STATE_FILES):
                file = root / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(json.dumps({"edition_id": current}), encoding="utf-8")
            daily = root / "gold" / "daily"
            daily.mkdir()
            old = daily / f"{previous}_早报_黄金深度研报.md"
            old.write_text(f'<!-- DAILY_META {{"edition_id":"{previous}"}} -->', encoding="utf-8")
            with patch.object(publish.edition_run, "check_edition_reviews") as reviews, \
                 patch.object(publish, "_run") as lint:
                with self.assertRaisesRegex(RuntimeError, "Gold manuscript, gold snapshot and equity state must match"):
                    publish._check_manuscripts(root, {})
                reviews.assert_not_called()
                lint.assert_not_called()

                new = daily / f"{current}_午报_黄金深度研报.md"
                new.write_text(old.read_text(encoding="utf-8"), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "Gold manuscript metadata must match"):
                    publish._check_manuscripts(root, {})
                lint.assert_not_called()

                new.write_text(f'<!-- DAILY_META {{"edition_id":"{current}"}} -->', encoding="utf-8")
                lint.return_value = subprocess.CompletedProcess([], 0, "", "")
                publish._check_manuscripts(root, {})
                reviews.assert_called_once_with(current, root=root)
                self.assertEqual(lint.call_count, 2)

    def test_publishing_recovery_preserves_existing_preview(self):
        with TemporaryDirectory() as tmp:
            git_dir = Path(tmp)
            preview = git_dir / "_site"
            preview.mkdir()
            sha, token = "a" * 40, "1" * 32
            intent = publish.edition_run.push_intent_path(git_dir, token)
            intent.touch()
            repo_url = "git@github.com:example/research.git"
            results = {
                ("symbolic-ref", "--quiet", "--short", "HEAD"): "main",
                ("remote", "get-url", "--push", "--all", "origin"): repo_url,
                ("remote", "get-url", "origin"): repo_url,
            }
            with patch.object(publish, "SITE_DIR", preview), \
                 patch.object(publish, "_git_dir", return_value=git_dir), \
                 patch.object(publish, "_git", side_effect=lambda env, *args: results[args]), \
                 patch.object(publish.edition_run, "publication_context", return_value="2026-11-28_1130"), \
                 patch.object(publish, "_push_edition", return_value=(sha, intent)), \
                 patch.object(publish, "_install_site") as install:
                self.assertEqual(publish.main(["--edition-token", token]), 0)
            install.assert_not_called()

    def test_no_push_cannot_commit_during_an_active_edition(self):
        with TemporaryDirectory() as tmp:
            git_dir = Path(tmp)
            with patch.object(publish.edition_run, "git_directory", return_value=git_dir), \
                 patch.object(publish.edition_run, "git_value", return_value="a" * 40):
                with closing(publish.edition_run.open_runs()) as runs:
                    publish.edition_run.begin(runs, "2026-11-26_0730")
                with patch.object(publish, "_git_dir", return_value=git_dir), \
                     patch.object(publish, "_git", return_value="main\n"), \
                     patch.object(publish, "_prepare_commit") as prepare, \
                     redirect_stderr(StringIO()) as failure:
                    self.assertEqual(publish.main(["--no-push"]), 1)
                self.assertIn("owns publication", failure.getvalue())
                prepare.assert_not_called()


class WebPublicationRecoveryTests(unittest.TestCase):
    def test_push_timeout_checks_if_the_selected_commit_landed(self):
        sha = "a" * 40
        with patch.object(publish, "_remote_main", side_effect=[None, sha]), \
             patch.object(publish, "_run", side_effect=subprocess.TimeoutExpired("git push", 1)) as push:
            publish._push_verified_commit({}, sha)
        self.assertEqual(push.call_count, 1)

    def test_after_interruption_edition_resumes_saved_push_without_commit(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha, token = "a" * 40, "1" * 32
            edition = "2026-11-25_1800_r2"
            repo = "example/research"
            publish._save_json(
                root / f"edition-push-{token}.json",
                {"edition": edition, "repository": repo, "sha": sha},
            )
            with patch.object(publish.edition_run, "publication_commit", return_value=None), \
                 patch.object(publish.edition_run, "check_publication_candidate") as preflight, \
                 patch.object(publish.edition_run, "record_push") as record, \
                 patch.object(publish, "_git", return_value=sha), \
                 patch.object(publish, "_validate_revision"), \
                 patch.object(publish, "_prepare_commit") as prepare, \
                 patch.object(publish, "_push_verified_commit") as push:
                confirmed, intent = publish._push_edition(
                    token, edition, repo, {}, git_dir=root, common=root, work=root,
                    output=root / "site", message=None,
                )
            self.assertEqual(confirmed, sha)
            self.assertFalse(intent.exists())
            prepare.assert_not_called()
            preflight.assert_called_once_with(token, sha=sha, repository=repo)
            push.assert_called_once_with({}, sha, already_pushed=False, automated=True)
            record.assert_called_once_with(token, sha=sha, repository=repo)

    def test_automated_push_accepts_confirmed_ancestor_when_main_moves(self):
        base, sha, newer = "b" * 40, "a" * 40, "c" * 40

        def git(_env, *args):
            if args[0] == "log" and args[-1] == "--":
                return "gold/data_snapshot.json\0equity/state/market_state.json\0"
            return ""

        with patch.object(publish, "_fetch_remote_main", side_effect=[base, newer]), \
             patch.object(publish, "_is_ancestor", side_effect=[False, True, True]) as ancestor, \
             patch.object(publish, "_git", side_effect=git), \
             patch.object(publish, "_run", return_value=subprocess.CompletedProcess([], 0, "", "")) as push:
            publish._push_verified_commit({}, sha, automated=True)
        push.assert_called_once_with(["git", "push", "origin", f"{sha}:refs/heads/main"], {}, timeout=120)
        ancestor.assert_called_with({}, sha, newer)

    def test_automated_push_rechecks_outgoing_scope_after_transport_error(self):
        sha = "a" * 40
        with patch.object(publish, "_automated_push_needed", side_effect=[True, RuntimeError("outside scope")]) as preflight, \
             patch.object(publish, "_is_commit_on_remote_main", return_value=False), \
             patch.object(publish, "_run", side_effect=subprocess.TimeoutExpired("git push", 1)) as push, \
             patch.object(publish.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "outside scope"):
                publish._push_verified_commit({}, sha, automated=True)
        self.assertEqual(preflight.call_count, 2)
        self.assertEqual(push.call_count, 1)

    def test_resume_records_original_ancestor_without_rewinding_or_republishing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha, newer, token = "a" * 40, "c" * 40, "1" * 32
            edition, repo = "2026-11-25_1800_r2", "example/research"
            intent = publish.edition_run.push_intent_path(root, token)
            publish._save_json(intent, {"edition": edition, "repository": repo, "sha": sha})
            with patch.object(publish.edition_run, "publication_commit", return_value=None), \
                 patch.object(publish.edition_run, "check_publication_candidate"), \
                 patch.object(publish.edition_run, "record_push") as record, \
                 patch.object(publish, "_git", return_value=newer), \
                 patch.object(publish, "_validate_revision") as validate, \
                 patch.object(publish, "_fetch_remote_main", return_value=newer), \
                 patch.object(publish, "_is_ancestor", return_value=True), \
                 patch.object(publish, "_run") as push:
                confirmed, _ = publish._push_edition(
                    token, edition, repo, {}, git_dir=root, common=root, work=root,
                    output=root / "site", message=None,
                )
            self.assertEqual(confirmed, sha)
            self.assertFalse(intent.exists())
            validate.assert_called_once_with(sha, root / "site", {}, edition=edition)
            record.assert_called_once_with(token, sha=sha, repository=repo)
            push.assert_not_called()

    def test_rejected_candidate_leaves_no_intent_or_push(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha, token = "a" * 40, "1" * 32
            edition = "2026-11-26_0730"

            def push_main(*args, before_push, **kwargs):
                before_push(sha)
                self.fail("A rejected candidate cannot proceed to push")

            with patch.object(publish.edition_run, "publication_commit", return_value=None), \
                 patch.object(publish.edition_run, "check_publication_candidate", side_effect=ValueError("old commit")), \
                 patch.object(publish.edition_run, "record_push") as record, \
                 patch.object(publish, "_prepare_commit"), patch.object(publish, "_push_main", side_effect=push_main):
                with self.assertRaisesRegex(ValueError, "old commit"):
                    publish._push_edition(
                        token, edition, "example/research", {}, git_dir=root, common=root, work=root,
                        output=root / "site", message=None,
                    )
            self.assertFalse(publish.edition_run.push_intent_path(root, token).exists())
            record.assert_not_called()


class PublicationIsolationTests(unittest.TestCase):
    def test_publication_floor_checks_snapshots_in_the_selected_git_tree(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.check_output(
                    ["git", "-c", "user.name=Test", "-c", "user.email=fixture@example.invalid", *args],
                    cwd=root, text=True,
                ).strip()

            def commit(edition, message):
                for relative in publish.pages_release.EDITION_PATHS:
                    snapshot = root / relative
                    snapshot.parent.mkdir(parents=True, exist_ok=True)
                    snapshot.write_text(json.dumps({"edition_id": edition}), encoding="utf-8")
                git("add", "--all")
                git("commit", "--allow-empty", "-qm", message)
                return git("rev-parse", "HEAD")

            git("init", "-q")
            base = commit("2026-11-28_1800", "Latest edition")
            old = commit("2026-11-28_1130", "Accidental downgrade")
            new = commit("2026-11-28_1800", "Same edition content correction")
            with patch.object(publish, "REPO_ROOT", root):
                env = publish._clean_env()
                with self.assertRaisesRegex(RuntimeError, "would replace the newer edition"):
                    publish._require_nonregressing_edition(env, old, base)
                publish._require_nonregressing_edition(env, new, base)

    def test_automated_scope_includes_prior_unpushed_commits_even_after_revert(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.run(
                    ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                    cwd=root, capture_output=True, text=True, check=True,
                ).stdout.strip()

            git("init", "-q")
            (root / "scripts").mkdir()
            helper = root / "scripts" / "renderer"
            helper.write_text("shared\n", encoding="utf-8")
            git("add", "--all")
            git("commit", "-qm", "Remote base")
            base = git("rev-parse", "HEAD")
            helper.write_text("local unpublished code\n", encoding="utf-8")
            git("commit", "-qam", "Local code")
            git("revert", "--no-edit", "HEAD")
            (root / "gold").mkdir()
            (root / "gold" / "data").write_text("current edition\n", encoding="utf-8")
            git("add", "--all")
            git("commit", "-qm", "Scheduled edition")
            candidate = git("rev-parse", "HEAD")
            self.assertEqual(git("diff", "--name-only", base, candidate), "gold/data")

            with patch.object(publish, "REPO_ROOT", root), \
                 patch.object(publish, "_fetch_remote_main", return_value=base):
                with self.assertRaisesRegex(RuntimeError, "outside automated publication scope: scripts/renderer"):
                    publish._automated_push_needed(publish._clean_env(), candidate, already_pushed=False)

            prior_to_edition = git("rev-parse", "HEAD^")
            with patch.object(publish, "REPO_ROOT", root), \
                 patch.object(publish, "_fetch_remote_main", return_value=prior_to_edition):
                self.assertTrue(publish._automated_push_needed(publish._clean_env(), candidate, already_pushed=False))

    @staticmethod
    def _publication_fixture_git(root):
        def git(*args):
            return subprocess.check_output(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                cwd=root, text=True,
            ).strip()

        git("init", "-q")
        (root / "baseline").write_text("committed\n", encoding="utf-8")
        git("add", "baseline")
        git("commit", "-qm", "Baseline")
        return git

    def test_automatic_candidate_rejects_protected_runtime_drift_only_for_tokenized_publication(self):
        for path, tracked, staged in (
            ("equity/lint_equity.py", True, False),
            ("gold/daily/AGENTS.md", True, True),
            ("equity/new_publish_helper.py", False, False),
            ("equity/DAILY_REPORT_SPEC.md", False, True),
            (".agents/skills/alternative/SKILL.md", False, False),
        ):
            with self.subTest(path=path), TemporaryDirectory() as tmp:
                root = Path(tmp)
                git = self._publication_fixture_git(root)
                target = root / path
                target.parent.mkdir(parents=True)
                if tracked:
                    target.write_text("original\n", encoding="utf-8")
                    git("add", path)
                    git("commit", "-qm", "Original rule or executable")
                target.write_text("local maintenance\n", encoding="utf-8")
                if staged:
                    git("add", path)
                with patch.object(publish, "REPO_ROOT", root):
                    env = publish._clean_env()
                    with self.assertRaisesRegex(ValueError, re.escape(path)):
                        publish._publication_tree(env, root / "tokenized-index", automated=True)
                    tree, _ = publish._publication_tree(env, root / "maintainer-index")
                    self.assertEqual(git("diff", "--name-only", "HEAD", tree), path)

    def test_automatic_candidate_accepts_reports_rsi_and_flagship_rollover(self):
        files = {
            "gold/daily/2026-12-01_0730_早报_黄金深度研报.md",
            "gold/daily/RSI_PLAYBOOK.md",
            "gold/market_calendar.json",
            "equity/daily/2026-12-01_0730_a_share.md",
            "equity/a_share_market_report_2026_12.md",
            "equity/a_share_market_report_latest.md",
            "equity/report_meta_a_share.json",
            "equity/state/RSI_PLAYBOOK.md",
        }
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            git = self._publication_fixture_git(root)
            for name in files:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("scheduled output\n", encoding="utf-8")
            with patch.object(publish, "REPO_ROOT", root):
                tree, automatic = publish._publication_tree(publish._clean_env(), root / "tokenized-index", automated=True)
            self.assertTrue(automatic)
            self.assertEqual(set(git("-c", "core.quotePath=false", "diff", "--name-only", "HEAD", tree).splitlines()), files)
            self.assertEqual(git("diff", "--cached", "--name-only"), "")

    def test_automated_push_rejects_a_precommitted_protected_path_even_after_revert(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            git = self._publication_fixture_git(root)
            target = root / "gold" / "lint_readability.py"
            target.parent.mkdir()
            target.write_text("original runtime\n", encoding="utf-8")
            git("add", "gold")
            git("commit", "-qm", "Runtime baseline")
            base = git("rev-parse", "HEAD")
            target.write_text("local runtime\n", encoding="utf-8")
            git("commit", "-qam", "Protected path mixed in")
            git("revert", "--no-edit", "HEAD")
            (target.parent / "data_snapshot.json").write_text("{}", encoding="utf-8")
            git("add", "gold")
            git("commit", "-qm", "Scheduled output")
            candidate = git("rev-parse", "HEAD")
            self.assertEqual(git("diff", "--name-only", base, candidate), "gold/data_snapshot.json")

            with patch.object(publish, "REPO_ROOT", root), patch.object(publish, "_fetch_remote_main", return_value=base):
                with self.assertRaisesRegex(RuntimeError, "gold/lint_readability.py"):
                    publish._automated_push_needed(publish._clean_env(), candidate, already_pushed=False)

    def test_check_tree_no_forbidden_files_blocks_binary_and_receipt_files(self):
        header = f"100644 blob {'a' * 40}\t"
        clean_tree = "".join(header + path + "\0" for path in (
            "gold/data_snapshot.json",
            "gold/daily/2026-11-26_1800_晚报_黄金深度研报.md",
            "equity/state/market_state.json",
        ))
        with patch.object(publish, "_git", return_value=clean_tree):
            publish._check_tree_no_forbidden_files({}, "deadbeef")

        for forbidden_path in (
            "gold/daily/2026-11-26_1800_晚报_黄金深度研报.pdf",
            "equity/daily/2026-11-26_1800_a_share.docx",
            "gold/daily/2026-11-26_1800_晚报_黄金深度研报.artifacts.json",
            "equity/REPORT.PDF",
            "gold/ARCHIVE.DOCX",
        ):
            with self.subTest(forbidden_path=forbidden_path):
                self.assertTrue(publish._is_forbidden_stage_path(forbidden_path))
                dirty_tree = f"{clean_tree}{header}{forbidden_path}\0"
                with patch.object(publish, "_git", return_value=dirty_tree):
                    with self.assertRaisesRegex(RuntimeError, "Forbidden binary/receipt file"):
                        publish._check_tree_no_forbidden_files({}, "deadbeef")

    def test_publication_revision_rejects_a_symlink_before_checkout(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "data.json").symlink_to("missing.json")
            subprocess.run(["git", "add", "data.json"], cwd=root, check=True)
            tree = subprocess.check_output(["git", "write-tree"], cwd=root, text=True).strip()
            with patch.object(publish, "REPO_ROOT", root), \
                 patch.object(publish, "_checkout_revision") as checkout:
                with self.assertRaisesRegex(RuntimeError, "must be regular files: data.json"):
                    publish._validate_revision(tree, root / "site", publish._clean_env())
            checkout.assert_not_called()

    def test_automated_stage_paths_strictly_limited_to_gold_and_equity(self):
        self.assertEqual(publish.AUTOMATED_STAGE_PATHS, ("gold", "equity"))
        self.assertNotIn("scripts", publish.AUTOMATED_STAGE_PATHS)
        self.assertNotIn("tests", publish.AUTOMATED_STAGE_PATHS)

        for path, expected in (
            ("gold/data_snapshot.json", True),
            ("gold/daily/SCORECARD.md", True),
            ("equity/state/market_state.json", True),
            ("equity/state/multi_asset_channels.json", True),
            ("scripts/publish_site.py", False),
            ("scripts/build_site.py", False),
            ("tests/test_publishing.py", False),
            ("AGENTS.md", False),
            (".github/workflows/deploy-pages.yml", False),
        ):
            with self.subTest(path=path):
                self.assertEqual(publish._scoped(path, publish.AUTOMATED_STAGE_PATHS), expected)

    def test_remote_repository_parses_custom_ssh_aliases_and_credentialed_https(self):
        valid_urls = (
            ("https://github.com/org/research-repo.git", "org/research-repo"),
            ("https://github.com/org/research-repo/", "org/research-repo"),
            ("https://x-access-token:ghs_secret123@github.com/org/research-repo.git", "org/research-repo"),
            ("https://alice@github.com/org/research-repo", "org/research-repo"),
            ("git@github.com:org/research-repo.git", "org/research-repo"),
            ("git@github-work:org/research-repo.git", "org/research-repo"),
            ("git@corp.github.alias:org/research-repo", "org/research-repo"),
            ("ssh://git@github.com/org/research-repo.git", "org/research-repo"),
            ("ssh://git@github-personal:2222/org/research-repo.git", "org/research-repo"),
        )
        for url, expected in valid_urls:
            with self.subTest(url=url):
                self.assertEqual(publish._remote_repository(url), expected)

        invalid_urls = (
            "https://gitlab.com/org/research-repo.git",
            "git@bitbucket.org:org/research-repo.git",
            "https://github.com/org/research-repo/extra",
            "/local/path/research-repo.git",
        )
        for bad_url in invalid_urls:
            with self.subTest(bad_url=bad_url):
                with self.assertRaisesRegex(RuntimeError, "github.com"):
                    publish._remote_repository(bad_url)


if __name__ == "__main__":
    unittest.main()
