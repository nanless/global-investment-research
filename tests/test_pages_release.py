from gzip import compress
from http.client import BadStatusLine
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
from zlib import error as GzipError

from scripts import pages_release


class PagesResourceTests(unittest.TestCase):
    def test_first_parent_is_edition_floor_but_same_edition_hotfix_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            def git(*args: str) -> str:
                return subprocess.check_output(
                    ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args],
                    cwd=repo, text=True,
                ).strip()

            git("init", "-q")
            site = repo / "untracked-site"
            for name in pages_release.RELEASE_FILES:
                path = site / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"<html>\n<head>\n</head>\n</html>" if name == "index.html" else name.encode())

            def stamp(edition: str, note: str):
                for name in pages_release.EDITION_PATHS:
                    path = repo / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"edition_id": edition, "note": note}), encoding="utf-8")
                git("add", *pages_release.EDITION_PATHS)
                git("commit", "-qm", note)
                head = git("rev-parse", "HEAD")
                with patch.object(pages_release, "ROOT", repo), patch.object(
                    sys, "argv", ["pages_release.py", "--site", str(site), "--commit", head],
                ), patch.dict(os.environ, {"GIR_PAGES_PUSH_BEFORE": ""}):
                    return pages_release.main()

            self.assertEqual(stamp("2026-11-28_1800_r2", "Root edition"), 0)
            self.assertEqual(stamp("2026-11-28_1800_r2", "Same edition hotfix"), 0)
            with patch("sys.stderr"):
                with self.assertRaises(SystemExit) as caught:
                    stamp("2026-11-28_1130", "Same-day edition rollback")
            self.assertEqual(caught.exception.code, 1)
            self.assertEqual(json.loads((site / pages_release.MANIFEST_PATH).read_bytes())["edition_id"], "2026-11-28_1800_r2")

    def test_push_before_detects_rollback_across_a_shallow_multi_commit_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            origin, checkout = base / "origin", base / "checkout"
            origin.mkdir()

            def git(repo, *args):
                return subprocess.check_output(
                    ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args],
                    cwd=repo, text=True, stderr=subprocess.PIPE,
                ).strip()

            git(origin, "init", "-q")

            def record(edition):
                for relative in pages_release.EDITION_PATHS:
                    path = origin / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"edition_id": edition}), encoding="utf-8")
                git(origin, "add", *pages_release.EDITION_PATHS)
                git(origin, "commit", "-qm", edition)
                return git(origin, "rev-parse", "HEAD")

            before = record("2026-11-28_1800")
            record("2026-11-28_0730")
            current = record("2026-11-28_1130")
            git(base, "clone", "-q", "--depth=2", origin.as_uri(), str(checkout))
            with self.assertRaises(subprocess.CalledProcessError):
                git(checkout, "cat-file", "-e", f"{before}^{{commit}}")
            pages_release._check_parent_edition(checkout, current, "2026-11-28_1130")
            with self.assertRaisesRegex(ValueError, "cannot go back.*2026-11-28_1800.*before the push"):
                pages_release._check_push_edition(checkout, before, "2026-11-28_1130")
            git(checkout, "cat-file", "-e", f"{before}^{{commit}}")

    def test_response_header_failure_is_reported_as_transport_error(self):
        opener = Mock()
        opener.open.side_effect = BadStatusLine("bad response header")
        with patch.object(pages_release, "build_opener", return_value=opener):
            with self.assertRaisesRegex(OSError, "invalid or incomplete"):
                pages_release._fetch("https://example.github.io/project/index.html", 8)

    def test_dripping_body_still_respects_the_deadline(self):
        url = "https://example.github.io/project/index.html"
        clock = 0.0

        def next_chunk(_size):
            nonlocal clock
            clock += 0.4
            return b"x"

        response = Mock(status=200, headers={"Content-Encoding": "identity"})
        response.geturl.return_value = url
        response.read1.side_effect = next_chunk
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch.object(pages_release, "build_opener", return_value=opener), patch.object(
            pages_release.time, "monotonic", side_effect=lambda: clock,
        ):
            with self.assertRaisesRegex(TimeoutError, "Timed out reading"):
                pages_release._fetch(url, 1.0)
        self.assertEqual(response.read1.call_count, 3)

    def test_fetch_decodes_gzip_to_the_original_resource_bytes(self):
        url = "https://example.github.io/project/charts.html"
        body = b"<!doctype html>" + bytes(range(256)) * 512
        opener = self._gzip_opener(url, compress(body))
        with patch.object(pages_release, "build_opener", return_value=opener):
            self.assertEqual(pages_release._fetch(url, 8), body)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Accept-encoding"), "gzip")

    def test_fetch_rejects_incomplete_or_invalid_compressed_data(self):
        url = "https://example.github.io/project/charts.html"
        compressed = compress(b"verified content")
        invalid_deflate = compressed[:10] + b"\x07" + compressed[11:]
        for payload, cause in ((compressed[:-5], EOFError), (invalid_deflate, GzipError)):
            with self.subTest(cause=cause), patch.object(
                pages_release, "build_opener", return_value=self._gzip_opener(url, payload),
            ):
                with self.assertRaisesRegex(OSError, "invalid or incomplete") as caught:
                    pages_release._fetch(url, 8)
                self.assertIsInstance(caught.exception.__cause__, cause)

    def test_fetch_limits_decoded_gzip_size(self):
        url = "https://example.github.io/project/charts.html"
        opener = self._gzip_opener(url, compress(b"a" * 8192))
        with patch.object(pages_release, "build_opener", return_value=opener), patch.object(
            pages_release, "MAX_RESOURCE_BYTES", 64,
        ):
            with self.assertRaisesRegex(ValueError, "oversized"):
                pages_release._fetch(url, 8)

    def test_fetch_stops_reading_dripping_gzip_before_decompression_finishes(self):
        url = "https://example.github.io/project/charts.html"
        payload = BytesIO(compress(b"") * 30 + compress(b"late content"))
        opener = self._gzip_opener(url, b"")
        response = opener.open.return_value.__enter__.return_value
        clock = 0.0

        def receive(size):
            nonlocal clock
            clock += 0.2
            return payload.read(min(size, 3))

        response.read1.side_effect = receive
        with patch.object(pages_release, "build_opener", return_value=opener), patch.object(
            pages_release.time, "monotonic", side_effect=lambda: clock,
        ):
            with self.assertRaisesRegex(TimeoutError, "Timed out reading"):
                pages_release._fetch(url, 1.0)
        self.assertLessEqual(response.read1.call_count, 6)

    @staticmethod
    def _gzip_opener(url, payload):
        response = Mock(status=200, headers={"Content-Encoding": "gzip"})
        response.geturl.return_value = url
        response.read1.side_effect = BytesIO(payload).read
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        return opener

    def test_latest_daily_and_double_reads_detect_a_mixed_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            for name in pages_release.RELEASE_FILES:
                path = site / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"<html>\n<head>\n</head>\n</html>" if name == "index.html" else name.encode())
            edition, commit = "2026-11-28_1130", "a" * 40
            pages_release.write_release(site, commit, edition)
            expected = {
                name: pages_release.hash_bytes((site / name).read_bytes()) for name in pages_release.COPIED_ASSETS
            }
            stale_article = "daily/hk-stock-latest.html"
            manifest_reads = 0

            def fetch(url, _timeout):
                nonlocal manifest_reads
                name = urlsplit(url).path.removeprefix("/project/") or "index.html"
                if name == pages_release.MANIFEST_PATH:
                    manifest_reads += 1
                if manifest_reads == 1 and name == stale_article:
                    return b"old HTML still served by the CDN"
                return (site / name).read_bytes()

            with patch.object(pages_release, "_fetch", side_effect=fetch):
                with self.assertRaisesRegex(ValueError, stale_article):
                    pages_release.verify_release(commit, edition, "example/project", expected, timeout=15)

            manifest_reads = 0

            def rolled_forward(url, _timeout):
                nonlocal manifest_reads
                name = urlsplit(url).path.removeprefix("/project/") or "index.html"
                body = (site / name).read_bytes()
                if name == pages_release.MANIFEST_PATH:
                    manifest_reads += 1
                    if manifest_reads == 2:
                        later = json.loads(body)
                        later["commit"] = "b" * 40
                        body = json.dumps(later).encode()
                return body

            with patch.object(pages_release, "_fetch", side_effect=rolled_forward):
                with self.assertRaisesRegex(ValueError, "changed while checking"):
                    pages_release.verify_release(commit, edition, "example/project", expected, timeout=15)
