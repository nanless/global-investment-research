from contextlib import closing, redirect_stderr
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import artifact_receipt
from scripts import publish_site as publish


class ArtifactReceiptTests(unittest.TestCase):
    def test_archive_keeps_same_receipt_and_ignores_historical_midday_issue(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            daily = root / "equity" / "daily"
            archive = daily / "archive" / "2026-11"
            archive.mkdir(parents=True)
            archived = daily / "2026-11-23_1800_a_share.md"
            old_midday = daily / "2026-11-24_1630_a_share.md"
            pdf, docx = archived.with_suffix(".pdf"), archived.with_suffix(".docx")
            for path in (archived, old_midday, pdf, docx):
                path.write_text(path.name, encoding="utf-8")
            frozen = artifact_receipt.freeze_inputs(archived, root=root)
            artifact_receipt.write_receipt(frozen, pdf, docx)
            outputs = {"pdf": artifact_receipt.sha256_file(pdf), "docx": artifact_receipt.sha256_file(docx)}
            for path in (archived, pdf, docx, archived.with_suffix(".artifacts.json")):
                path.rename(archive / path.name)

            pattern = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{4})_a_share(?:_r(\d+))?\.md")
            selected = publish._latest_daily(daily, pattern)
            self.assertEqual(selected, archive / archived.name)
            artifact_receipt.verify_receipt(selected, repository=root, tree=root, inputs=[], outputs=outputs)
            archived.write_text("duplicate scheduled issue", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Duplicate scheduled issue"):
                publish._latest_daily(daily, pattern)

    def test_receipt_rejects_changed_render_metadata_or_binary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            md = root / "issue.md"
            meta = root / "meta.json"
            pdf, docx = md.with_suffix(".pdf"), md.with_suffix(".docx")
            for path in (md, meta, pdf, docx):
                path.write_text(path.name, encoding="utf-8")
            inputs = artifact_receipt.freeze_inputs(md, inputs=[meta], root=root)
            artifact_receipt.write_receipt(inputs, pdf, docx)
            outputs = {"pdf": artifact_receipt.sha256_file(pdf), "docx": artifact_receipt.sha256_file(docx)}
            artifact_receipt.verify_receipt(md, repository=root, tree=root, inputs=["meta.json"], outputs=outputs)

            meta.write_text("new chart values", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale"):
                artifact_receipt.verify_receipt(md, repository=root, tree=root, inputs=["meta.json"], outputs=outputs)
            with self.assertRaisesRegex(ValueError, "changed during compilation"):
                artifact_receipt.write_receipt(inputs, pdf, docx)

            meta.write_text(meta.name, encoding="utf-8")
            outputs["docx"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "fingerprints"):
                artifact_receipt.verify_receipt(md, repository=root, tree=root, inputs=["meta.json"], outputs=outputs)


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


class FakeRelease:
    repository = "example/research"

    def __init__(self):
        self.remote = {}
        self.content = {}
        self.next_id = 1

    def add(self, name, digest):
        if name in self.remote:
            raise RuntimeError("duplicate GitHub asset")
        item = publish.RemoteAsset(self.next_id, name, digest)
        self.next_id += 1
        self.remote[name] = item
        return item

    def assets(self):
        return self.remote.copy()

    def json_asset(self, asset):
        return self.content[asset.id]

    def upload(self, path):
        item = self.add(path.name, artifact_receipt.sha256_file(path))
        self.content[item.id] = json.loads(path.read_text(encoding="utf-8"))

    def delete(self, asset):
        if self.remote[asset.name].id != asset.id:
            raise RuntimeError("another process replaced an asset")
        del self.remote[asset.name]

    def rename(self, asset, name):
        if name in self.remote:
            raise RuntimeError("duplicate GitHub asset")
        self.delete(asset)
        self.remote[name] = replace(asset, name=name)

    def stage(self, asset):
        self.add(asset.staged_name, asset.digest)


class PublicationRecoveryTests(unittest.TestCase):
    def test_cross_clone_recovers_pair_with_both_stable_names_present(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, fresh = root / "first", root / "fresh"
            first.mkdir()
            fresh.mkdir()
            candidate = "a" * 40
            pdf = publish.LocalAsset(root / "gir-next-issue.pdf", "issue.pdf", "PDF", "b" * 64)
            docx = publish.LocalAsset(root / "gir-next-issue.docx", "issue.docx", "Word", "b" * 64)
            release = FakeRelease()
            old_pdf = release.add(pdf.backup_name, "a" * 64)
            release.add(pdf.name, pdf.digest)
            old_docx = release.add(docx.name, "a" * 64)
            journal = first / publish.REMOTE_JOURNAL
            publish._save_json(journal, {
                "schema": 1, "sha": candidate,
                "expected": {pdf.name: pdf.digest, docx.name: docx.digest},
                "previous": {
                    pdf.name: {"id": old_pdf.id, "digest": old_pdf.digest},
                    docx.name: {"id": old_docx.id, "digest": old_docx.digest},
                },
            })
            release.upload(journal)

            def stop_after_recovery(asset):
                raise RuntimeError("injected upload failure")

            with patch.object(release, "stage", stop_after_recovery), \
                 patch.object(publish, "GitHubRelease", return_value=release), \
                 patch.object(publish, "_remote_main", return_value=candidate):
                with self.assertRaisesRegex(RuntimeError, "upload failure"):
                    publish._publish_release(
                        release.repository, [(pdf, docx)], fresh, {}, force=False, sha=candidate,
                    )
            self.assertEqual(release.remote[pdf.name].id, old_pdf.id)
            self.assertEqual(release.remote[docx.name].id, old_docx.id)
            self.assertNotIn(publish.REMOTE_LOCK, release.remote)
            with patch.object(publish, "GitHubRelease", return_value=release), \
                 patch.object(publish, "_remote_main", return_value=candidate):
                verified = publish._publish_release(
                    release.repository, [(pdf, docx)], fresh, {}, force=False, sha=candidate,
                )
            self.assertEqual(verified, {pdf.name: pdf.digest, docx.name: docx.digest})
            self.assertEqual(set(release.remote), {pdf.name, docx.name})
            self.assertEqual(json.loads((fresh / "last_release_commit.json").read_text())["sha"], candidate)

    def test_newer_main_refuses_an_older_release_before_remote_mutation(self):
        with patch.object(publish, "_remote_main", return_value="b" * 40), \
             patch.object(publish, "GitHubRelease") as remote:
            with self.assertRaisesRegex(RuntimeError, "no longer points"):
                publish._publish_release(
                    "example/research", [], Path("."), {}, force=False, sha="a" * 40,
                )
        remote.assert_not_called()

    def test_another_clone_cannot_take_over_a_live_release_lock(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            release = FakeRelease()
            with publish._remote_release_lock(release, first, first, "a" * 40, None):
                lock = release.remote[publish.REMOTE_LOCK]
                with self.assertRaisesRegex(RuntimeError, "Another publisher"):
                    with publish._remote_release_lock(release, second, second, "b" * 40, None):
                        self.fail("a different clone acquired the active remote lock")
                self.assertEqual(release.remote[publish.REMOTE_LOCK].id, lock.id)
            self.assertNotIn(publish.REMOTE_LOCK, release.remote)

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
                 patch.object(publish, "_validate_revision", return_value=[]), \
                 patch.object(publish, "_prepare_commit") as prepare, \
                 patch.object(publish, "_push_verified_commit") as push:
                confirmed, _, _ = publish._push_edition(
                    token, edition, repo, {}, git_dir=root, common=root, work=root,
                    output=root / "site", copies=root / "copies", message=None,
                )
            self.assertEqual(confirmed, sha)
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
                        output=root / "site", copies=root / "copies", message=None,
                    )
            self.assertFalse(publish.edition_run.push_intent_path(root, token).exists())
            record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
