from contextlib import closing, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import publish_site as publish


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
            push.assert_called_once_with({}, sha, already_pushed=False)
            record.assert_called_once_with(token, sha=sha, repository=repo)

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
    def test_check_tree_no_forbidden_files_blocks_binary_and_receipt_files(self):
        clean_tree = (
            "gold/data_snapshot.json\0"
            "gold/daily/2026-11-26_1800_晚报_黄金深度研报.md\0"
            "equity/state/market_state.json\0"
        )
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
                dirty_tree = f"{clean_tree}{forbidden_path}\0"
                with patch.object(publish, "_git", return_value=dirty_tree):
                    with self.assertRaisesRegex(RuntimeError, "Forbidden binary/receipt file"):
                        publish._check_tree_no_forbidden_files({}, "deadbeef")

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
