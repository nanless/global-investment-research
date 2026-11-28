#!/usr/bin/env python3
"""Stamp and verify the revision and key resources served by GitHub Pages."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import date
from gzip import GzipFile
import hashlib
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4
from zlib import error as GzipError

if __package__:
    from .fetch_kline_data import ALL_SHARDS_ORDER
else:
    from fetch_kline_data import ALL_SHARDS_ORDER

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = "assets/release.json"
COPIED_ASSETS = {
    "assets/app.css": "scripts/web_assets/app.css",
    "assets/app.js": "scripts/web_assets/app.js",
    "assets/kline.js": "scripts/web_assets/kline.js",
    "assets/klines/manifest.json": "equity/state/klines/manifest.json",
    **{f"assets/klines/{shard}.json": f"equity/state/klines/{shard}.json" for shard in ALL_SHARDS_ORDER},
}
RELEASE_FILES = (
    "index.html", "charts.html", "screener.html",
    *(f"daily/{market}-latest.html" for market in ("gold", "a-share", "hk-stock", "us-stock")),
    *COPIED_ASSETS,
)
EDITION_PATHS = ("gold/data_snapshot.json", "equity/state/market_state.json")
SHA_RE = re.compile(r"[a-f0-9]{40}")
HASH_RE = re.compile(r"[a-f0-9]{64}")
EDITION_RE = re.compile(r"\d{4}-\d{2}-\d{2}_(?:0730|1130|1800)(?:_r(?:[2-9]|[1-9]\d+))?")
REPOSITORY_RE = re.compile(r"([a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)/([\w.-]+)", re.ASCII)
META_RE = re.compile(rb'  <meta name="gir-release-commit" content="[a-f0-9]{40}">\n')
MAX_RESOURCE_BYTES = 8 * 1024 * 1024


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _valid_edition(value: object) -> bool:
    if not isinstance(value, str) or not EDITION_RE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return False
    return True


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field in Pages release data: {key!r}")
        result[key] = value
    return result


def edition_from_snapshots(snapshots: list[bytes]) -> str:
    if len(snapshots) != len(EDITION_PATHS):
        raise ValueError("Both source snapshots are required for a Pages release.")
    editions = []
    for raw in snapshots:
        snapshot = json.loads(raw, object_pairs_hook=_unique_object)
        edition = snapshot.get("edition_id") if isinstance(snapshot, dict) else None
        if not _valid_edition(edition):
            raise ValueError("Pages release requires a valid edition_id in both source snapshots.")
        editions.append(edition)
    if len(set(editions)) != 1:
        raise ValueError("Pages release requires matching source snapshot editions.")
    return editions[0]


def _edition_order(edition: str) -> tuple[date, int, int]:
    parts = edition.split("_")
    return date.fromisoformat(parts[0]), int(parts[1]), int(parts[2][1:]) if len(parts) == 3 else 1


def _check_baseline_edition(root: Path, revision: str, edition: str, label: str) -> None:
    try:
        snapshots = [
            subprocess.check_output(
                ["git", "cat-file", "blob", f"{revision}:{path}"], cwd=root, timeout=10,
            )
            for path in EDITION_PATHS
        ]
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Cannot read both snapshots from {label}.") from exc
    previous_edition = edition_from_snapshots(snapshots)
    if _edition_order(edition) < _edition_order(previous_edition):
        raise ValueError(f"Pages release cannot go back from {previous_edition} to {edition} ({label}).")


def _check_parent_edition(root: Path, commit: str, edition: str) -> None:
    # Inspect the actual commit header. A shallow boundary must never be mistaken for a root commit.
    raw = subprocess.check_output(["git", "cat-file", "commit", commit], cwd=root, timeout=10)
    header = raw.split(b"\n\n", 1)[0].splitlines()
    parent = next((line.decode("ascii").removeprefix("parent ") for line in header if line.startswith(b"parent ")), None)
    if parent is not None:
        _check_baseline_edition(root, parent, edition, "the first parent of the Pages commit")


def _check_push_edition(root: Path, before: str, edition: str) -> None:
    if not before or before == "0" * 40:
        return
    if not SHA_RE.fullmatch(before):
        raise ValueError("Invalid GitHub push.before commit for the Pages edition check.")
    found = subprocess.run(
        ["git", "cat-file", "-e", f"{before}^{{commit}}"], cwd=root, capture_output=True, timeout=10,
    )
    if found.returncode:
        try:
            subprocess.run(
                ["git", "fetch", "--no-tags", "--depth=1", "origin", before], cwd=root, check=True, timeout=30,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError("Cannot retrieve the original main commit for the Pages push edition check.") from exc
    _check_baseline_edition(root, before, edition, "the main commit before the push")


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _commit_meta(commit: str) -> bytes:
    return f'  <meta name="gir-release-commit" content="{commit}">'.encode("ascii")


def write_release(site: Path, commit: str, edition: str) -> None:
    if not SHA_RE.fullmatch(commit) or not _valid_edition(edition):
        raise ValueError("Invalid commit or edition for the Pages release.")
    resources = {name: (site / name).read_bytes() for name in RELEASE_FILES}
    if not all(resources.values()):
        raise ValueError("The Pages release contains an empty key resource.")
    homepage = META_RE.sub(b"", resources["index.html"])
    if homepage.count(b"</head>") != 1:
        raise ValueError("The Pages homepage must have one closing head tag.")
    homepage = homepage.replace(b"</head>", _commit_meta(commit) + b"\n</head>", 1)
    resources["index.html"] = homepage
    manifest = {
        "schema_version": 1,
        "commit": commit,
        "edition_id": edition,
        "files": {name: hash_bytes(content) for name, content in resources.items()},
    }
    (site / "index.html").write_bytes(homepage)
    (site / MANIFEST_PATH).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


class _DeadlineReader:
    """Apply the resource deadline to each network chunk requested by gzip."""

    def __init__(self, response, deadline: float):
        self.response = response
        self.deadline = deadline

    def read(self, size: int) -> bytes:
        # gzip expects this call to fill `size` bytes unless the response ends.
        data = bytearray()
        while len(data) < size:
            if time.monotonic() >= self.deadline:
                raise TimeoutError("Timed out reading a public Pages resource.")
            chunk = self.response.read1(size - len(data))
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)


def _fetch(url: str, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    request = Request(url, headers={
        "Cache-Control": "no-cache, no-store",
        "Pragma": "no-cache",
        "Accept-Encoding": "gzip",
    })
    try:
        with build_opener(_NoRedirect()).open(request, timeout=min(timeout, 8.0)) as response:
            if response.status != 200 or response.geturl() != url:
                raise ValueError("Pages returned an unexpected URL or HTTP status.")
            encoding = response.headers.get("Content-Encoding", "identity").strip().lower()
            if encoding not in {"gzip", "identity"}:
                raise ValueError("Pages returned an unsupported content encoding.")
            # Hash the decoded resource and enforce the size limit even for highly compressed responses.
            content = bytearray()
            if encoding == "gzip":
                body = GzipFile(fileobj=_DeadlineReader(response, deadline), mode="rb")
            else:
                body = nullcontext(response)
            with body as stream:
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out reading a public Pages resource.")
                    chunk = stream.read1(min(64 * 1024, MAX_RESOURCE_BYTES + 1 - len(content)))
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out reading a public Pages resource.")
                    if not chunk:
                        break
                    content.extend(chunk)
                    if len(content) > MAX_RESOURCE_BYTES:
                        raise ValueError("Pages returned an oversized release resource.")
            if not content:
                raise ValueError("Pages returned an empty release resource.")
            return bytes(content)
    except (HTTPException, EOFError, GzipError) as exc:
        raise OSError("The Pages response was invalid or incomplete.") from exc


def verify_release(
    commit: str, edition: str, repository: str, source_hashes: dict[str, str], *, timeout: float,
) -> None:
    match = REPOSITORY_RE.fullmatch(repository)
    if not match or not SHA_RE.fullmatch(commit) or not _valid_edition(edition):
        raise ValueError("Invalid commit, edition or repository for Pages verification.")
    owner, repo = match.groups()
    if repo in (".", "..") or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Invalid repository path or timeout for Pages verification.")
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(COPIED_ASSETS):
        raise ValueError("Pages verification requires hashes for all committed static assets.")
    # This portal deliberately uses the GitHub-owned Pages origin and its repository path.
    prefix = f"https://{owner.lower()}.github.io/"
    if repo.lower() != f"{owner.lower()}.github.io":
        prefix += f"{repo}/"
    deadline = time.monotonic() + timeout

    def fetch_resource(path: str) -> bytes:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("Timed out checking public Pages resources.")
        query = urlencode({"release": commit, "verify": uuid4().hex})
        body = _fetch(f"{prefix}{path}?{query}", left)
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out checking public Pages resources.")
        return body

    release_bytes = fetch_resource(MANIFEST_PATH)
    try:
        manifest = json.loads(release_bytes, object_pairs_hook=_unique_object)
    except RecursionError as exc:
        raise ValueError("The public Pages release manifest is too deeply nested.") from exc
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("The public Pages release manifest has an unsupported schema.")
    live_commit, live_edition = manifest.get("commit"), manifest.get("edition_id")
    if not isinstance(live_commit, str) or not SHA_RE.fullmatch(live_commit) or not _valid_edition(live_edition):
        raise ValueError("The public Pages release manifest has an invalid commit or edition.")
    if (live_commit, live_edition) != (commit, edition):
        raise ValueError(
            f"The public Pages release is serving {live_commit[:12]} ({live_edition}), "
            f"expected {commit[:12]} ({edition})."
        )
    expected = manifest.get("files")
    if not isinstance(expected, dict) or set(expected) != set(RELEASE_FILES):
        raise ValueError("The public Pages release manifest does not list every key resource.")
    if any(not isinstance(digest, str) or not HASH_RE.fullmatch(digest) for digest in expected.values()):
        raise ValueError("The public Pages release manifest has invalid SHA-256 hashes.")
    if any(expected[path] != source_hashes[path] for path in COPIED_ASSETS):
        raise ValueError("The Pages release manifest differs from the committed static assets.")

    paths = ("" if path == "index.html" else path for path in RELEASE_FILES)
    with ThreadPoolExecutor(max_workers=4) as downloads:
        for path, body in zip(RELEASE_FILES, downloads.map(fetch_resource, paths)):
            if hash_bytes(body) != expected[path]:
                raise ValueError(f"Public Pages content does not match the release hash for {path}.")
            if path == "index.html" and _commit_meta(commit) not in body:
                raise ValueError("The public homepage does not identify the expected commit.")
    if fetch_resource(MANIFEST_PATH) != release_bytes:
        raise ValueError("The public Pages release changed while checking its resources.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10).strip()
        if args.commit != head:
            raise ValueError("The Actions commit differs from the checked-out commit.")
        subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=ROOT, check=True, timeout=10)
        edition = edition_from_snapshots([(ROOT / path).read_bytes() for path in EDITION_PATHS])
        _check_parent_edition(ROOT, head, edition)
        _check_push_edition(ROOT, os.environ.get("GIR_PAGES_PUSH_BEFORE", "").strip(), edition)
        write_release(args.site, head, edition)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Pages release: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
