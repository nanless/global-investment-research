#!/usr/bin/env python3
"""Validate and publish a committed site, then reconcile the rolling Release."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "_site"
CANONICAL_STAGE_PATHS = (
    "AGENTS.md", ".agents", "automations", "gold", "equity",
    "scripts", "README.md", ".gitignore", ".github",
)
RELEASE_TAG = "latest-reports"
RELEASE_TITLE = "Latest Research Reports (PDF & Word)"
GOLD_MASTER = "黄金跨世纪周期与2026-2030终审研究报告"
MARKETS = (
    ("a_share", "a-share", "A股"),
    ("hk_stock", "hk-stock", "港股"),
    ("us_stock", "us-stock", "美股"),
)
CST = timezone(timedelta(hours=8))
GOLD_DAILY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_.*黄金深度研报(?:_r(\d+))?\.md$")
SHA256_RE = re.compile(r"sha256:([0-9a-f]{64})")


@dataclass(frozen=True)
class Report:
    source: Path
    asset_stem: str
    label: str


@dataclass(frozen=True)
class LocalAsset:
    path: Path
    name: str
    label: str
    digest: str

    @property
    def staged_name(self) -> str:
        return f"gir-next-{self.name}"

    @property
    def backup_name(self) -> str:
        return f"gir-prev-{self.name}"


@dataclass(frozen=True)
class RemoteAsset:
    id: int
    name: str
    digest: str | None


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    # Run in the explicitly selected checkout and GitHub repository.
    for key in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
        "GITHUB_TOKEN", "GH_TOKEN", "GH_REPO",
    ):
        env.pop(key, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GH_PROMPT_DISABLED"] = "1"
    env["GIT_SSH_COMMAND"] = (
        "ssh -o BatchMode=yes -o ConnectTimeout=20 "
        "-o ServerAliveInterval=15 -o ServerAliveCountMax=3"
    )
    candidates = (
        str(Path(sys.executable).resolve().parent),
        str(Path.home() / "miniforge3" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    )
    preferred = [p for p in dict.fromkeys(candidates) if os.path.isdir(p)]
    existing = [p for p in env.get("PATH", "").split(os.pathsep) if p and p not in preferred]
    env["PATH"] = os.pathsep.join(preferred + existing)
    return env


def _run(
    cmd: list[str], env: dict[str, str], *, cwd: Path | None = None, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd or REPO_ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
    )


def _checked(result: subprocess.CompletedProcess[str], operation: str) -> str:
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{operation} failed ({result.returncode}): {detail}")
    return result.stdout


def _git(env: dict[str, str], *args: str) -> str:
    return _checked(_run(["git", *args], env), f"git {args[0]}")


@contextlib.contextmanager
def _publish_lock(common_git_dir: Path) -> Iterator[None]:
    with (common_git_dir / "publish_site.lock").open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _build_and_lint(root: Path, output: Path, env: dict[str, str]) -> None:
    for script, args in (
        ("build_site.py", ["--out", str(output)]),
        ("lint_site.py", [str(output), "--strict"]),
    ):
        result = _run([sys.executable, "-B", str(root / "scripts" / script), *args], env, cwd=root)
        print(result.stdout, end="")
        _checked(result, script)


@contextlib.contextmanager
def _checkout_revision(revision: str, env: dict[str, str]) -> Iterator[Path]:
    """Read an exact staged or committed tree into an isolated index and directory."""
    with tempfile.TemporaryDirectory(prefix="gir_publish_tree_") as tmp:
        tmp_dir = Path(tmp).resolve()
        source = tmp_dir / "source"
        source.mkdir()
        snapshot_env = dict(env, GIT_INDEX_FILE=str(tmp_dir / "index"))
        _git(snapshot_env, "read-tree", revision)
        _git(snapshot_env, "checkout-index", "--all", "--prefix", f"{source}{os.sep}")
        yield source


def _scoped(path: str) -> bool:
    return any(path == key or path.startswith(f"{key}/") for key in CANONICAL_STAGE_PATHS)


def _publication_tree(env: dict[str, str], index: Path) -> tuple[str, bool]:
    staged = _git(env, "diff", "--cached", "--name-only", "-z", "--no-renames").split("\0")
    outside = [path for path in staged if path and not _scoped(path)]
    if outside:
        raise RuntimeError(f"Already staged outside the publication scope: {', '.join(outside)}")
    if any(staged):
        # An explicit index is the user's selection. Preserve unstaged changes.
        print("[git] Using existing in-scope staged changes.")
        return _git(env, "write-tree").strip(), False

    tracked = _git(env, "ls-files", "-z", "--", *CANONICAL_STAGE_PATHS).split("\0")
    paths = [
        key for key in CANONICAL_STAGE_PATHS
        if (REPO_ROOT / key).exists() or any(path == key or path.startswith(f"{key}/") for path in tracked)
    ]
    if not paths:
        raise RuntimeError("No publication source paths found in this checkout.")
    temporary = dict(env, GIT_INDEX_FILE=str(index))
    _git(temporary, "read-tree", "HEAD")
    _git(temporary, "add", "-A", "--", *paths)
    return _git(temporary, "write-tree").strip(), True


def _latest_daily(folder: Path, pattern: re.Pattern[str]) -> Path:
    candidates = []
    for path in folder.glob("*.md"):
        match = pattern.fullmatch(path.name)
        if match and path.is_file():
            try:
                datetime.strptime(f"{match[1]} {match[2]}", "%Y-%m-%d %H%M")
            except ValueError as exc:
                raise RuntimeError(f"Invalid report date/time in {path.name}") from exc
            if match[3] and int(match[3]) < 2:
                raise RuntimeError(f"A revised report must use _r2 or a later revision: {path.name}")
            key = (match[1], int(match[2]), int(match[3] or 1), path.name)
            candidates.append((key, path))
    if not candidates:
        raise RuntimeError(f"No report issue found in {folder.name}/")
    return max(candidates)[1]


def _reports(source: Path) -> list[Report]:
    equity = source / "equity"
    gold = source / "gold"
    reports = [
        Report(gold / f"{GOLD_MASTER}.md", "gold-master-latest", "黄金跨世纪周期全景主报告"),
        Report(_latest_daily(gold / "daily", GOLD_DAILY_RE), "gold-daily-latest", "黄金每日深度研报最新刊"),
    ]
    for market, slug, name in MARKETS:
        meta = json.loads((equity / f"report_meta_{market}.json").read_text(encoding="utf-8"))
        period = str(meta.get("period_slug", "")).strip()
        if not re.fullmatch(r"\d{4}_(?:0[1-9]|1[0-2])", period):
            raise RuntimeError(f"Invalid flagship period in report_meta_{market}.json: {period!r}")
        pattern = re.compile(rf"^(\d{{4}}-\d{{2}}-\d{{2}})_(\d{{4}})_{market}(?:_r(\d+))?\.md$")
        reports.extend((
            Report(equity / f"{market}_market_report_{period}.md",
                   f"{slug}-flagship-latest", f"{name}跨周期全景手册"),
            Report(_latest_daily(equity / "daily", pattern),
                   f"{slug}-daily-latest", f"{name}每日深度研报最新刊"),
        ))
    return reports


def _validate_pdf(path: Path) -> None:
    with path.open("rb") as pdf:
        if not re.fullmatch(rb"%PDF-\d\.\d", pdf.read(8)):
            raise ValueError("missing PDF header")
        size = pdf.seek(0, os.SEEK_END)
        pdf.seek(max(0, size - 4096))
        trailer = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", pdf.read())
        if not trailer or int(trailer[1]) >= size:
            raise ValueError("invalid PDF trailer")
        pdf.seek(int(trailer[1]))
        xref = pdf.read(1024)
        if not xref.startswith(b"xref") and not (
            re.match(rb"\d+\s+\d+\s+obj\b", xref) and re.search(rb"/Type\s*/XRef\b", xref)
        ):
            raise ValueError("invalid PDF cross-reference")


def _validate_docx(path: Path) -> None:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    office_document = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    with zipfile.ZipFile(path) as docx:
        failed = docx.testzip()
        if failed:
            raise ValueError(f"invalid DOCX entry: {failed}")
        content_types = ET.fromstring(docx.read("[Content_Types].xml"))
        relationships = ET.fromstring(docx.read("_rels/.rels"))
        document = ET.fromstring(docx.read("word/document.xml"))
        if not any(
            entry.get("PartName") == "/word/document.xml"
            and entry.get("ContentType") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
            for entry in content_types
        ) or not any(
            entry.get("Type") == office_document and entry.get("Target") in {"word/document.xml", "/word/document.xml"}
            for entry in relationships
        ) or document.tag != f"{ns}document" or document.find(f"{ns}body") is None:
            raise ValueError("missing OOXML Word main document")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_assets(source: Path, copies: Path) -> list[tuple[LocalAsset, LocalAsset]]:
    """Select both formats by one authoritative committed source stem."""
    groups = []
    errors = []
    for report in _reports(source):
        if not report.source.is_file():
            errors.append(f"{report.source.relative_to(source)}: manuscript missing")
            continue
        relative_source = report.source.relative_to(source)
        manuscript = REPO_ROOT / relative_source
        pair = []
        for ext, fmt, validate in (("pdf", "PDF", _validate_pdf), ("docx", "Word", _validate_docx)):
            relative = relative_source.with_suffix(f".{ext}")
            original = REPO_ROOT / relative
            name = f"{report.asset_stem}.{ext}"
            path = copies / f"gir-next-{name}"
            try:
                if not original.is_file() or original.is_symlink():
                    raise ValueError("missing regular artifact")
                if original.stat().st_mtime < manuscript.stat().st_mtime - 2:
                    raise ValueError("artifact is older than its source Markdown; recompile the report")
                shutil.copyfile(original, path)
                validate(path)
                pair.append(LocalAsset(path, name, f"{report.label} ({fmt})", _sha256_file(path)))
            except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
                errors.append(f"{relative}: {exc}")
        if len(pair) == 2:
            groups.append((pair[0], pair[1]))
    if errors:
        raise RuntimeError("Release requires eight complete, valid PDF/Word pairs:\n  " + "\n  ".join(errors))
    return groups


def _git_dir(env: dict[str, str], *, common: bool = False) -> Path:
    args = ("--path-format=absolute", "--git-common-dir") if common else ("--absolute-git-dir",)
    return Path(_git(env, "rev-parse", *args).strip())


def _remote_repository(url: str) -> str:
    pattern = r"(?:(?:https://|ssh://(?:git@)?|git@)github\.com[/:])([\w.-]+/[\w.-]+?)(?:\.git)?/?"
    match = re.fullmatch(pattern, url, flags=re.ASCII)
    if not match:
        raise RuntimeError("Release requires an origin URL that identifies a github.com repository.")
    return match[1]


def _release_inputs(source: Path) -> list[str]:
    paths = [str(report.source.relative_to(source)) for report in _reports(source)]
    paths.extend((
        "gold/data_snapshot.json", "gold/master_snapshot.json",
        "gold/build_daily.py", "gold/build_report.py", "gold/docx_embed.py",
        "equity/state/market_state.json", "equity/pdf_common.py", "equity/docx_embed.py",
        "equity/build_daily.py",
    ))
    for market, _, _ in MARKETS:
        paths.extend((f"equity/report_meta_{market}.json", f"equity/build_{market}_pdf.py"))
    return paths


def _validate_revision(
    revision: str, output: Path, copies: Path, env: dict[str, str], *,
    check_release: bool, artifact_tree: str | None = None,
) -> list[tuple[LocalAsset, LocalAsset]]:
    with _checkout_revision(revision, env) as source:
        _build_and_lint(source, output, env)
        if not check_release:
            return []
        paths = _release_inputs(source)
        if artifact_tree is not None:
            # A pull can change publication inputs without changing their filenames.
            changes = _git(env, "diff", "--name-only", "-z", artifact_tree, revision, "--", *paths)
            if changes:
                raise RuntimeError("Rebase changed report inputs. Recompile the rebased reports and retry.")
        for relative in paths:
            frozen, current = source / relative, REPO_ROOT / relative
            if frozen.is_file() and (not current.is_file() or frozen.read_bytes() != current.read_bytes()):
                raise RuntimeError(f"Release input differs from the selected Git tree: {relative}")
        return _prepare_assets(source, copies)


def _push_main(
    env: dict[str, str], output: Path, copies: Path, git_dir: Path,
    *, check_release: bool, artifact_tree: str,
) -> list[tuple[LocalAsset, LocalAsset]]:
    for attempt in (1, 2):
        try:
            remote = _run(["git", "ls-remote", "--heads", "origin", "refs/heads/main"], env, timeout=30)
            remote_head = _checked(remote, "git ls-remote").strip()
            if remote_head:
                pull = _run(["git", "pull", "--rebase", "--autostash", "origin", "main"], env, timeout=90)
                _checked(pull, "git pull --rebase")
                if pull.stderr.strip():
                    print(pull.stderr.strip())
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            if any((git_dir / name).exists() for name in ("rebase-merge", "rebase-apply")):
                _git(env, "rebase", "--abort")
            if attempt == 2:
                raise
            print(f"[git] Retry after {exc}", file=sys.stderr)
            time.sleep(3)
            continue

        if _git(env, "diff", "--name-only", "--diff-filter=U", "-z"):
            raise RuntimeError("Rebase left unmerged paths. Resolve them before continuing.")
        commit = _git(env, "rev-parse", "HEAD").strip()
        print(f"[git] Validating final commit {commit[:12]} before push {attempt}/2.")
        groups = _validate_revision(
            commit, output, copies, env, check_release=check_release, artifact_tree=artifact_tree,
        )
        try:
            # Publish the exact commit validated above, even if another process moves main.
            result = _run(["git", "push", "origin", f"{commit}:refs/heads/main"], env, timeout=120)
            _checked(result, "git push")
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            if attempt == 2:
                raise
            print(f"[git] Retry after {exc}", file=sys.stderr)
            time.sleep(3)
            continue
        print(f"[git] Pushed verified commit {commit[:12]} to origin/main.")
        return groups
    raise RuntimeError("Git push did not complete.")


class GitHubRelease:
    """Operate on a single explicit repository and the rolling release tag."""

    def __init__(self, repository: str, env: dict[str, str]):
        gh = shutil.which("gh", path=env["PATH"])
        if gh is None:
            raise RuntimeError("GitHub CLI (gh) is required for Release publication.")
        self.gh = gh
        self.repository = repository
        self.env = env
        result = self._api(f"releases/tags/{RELEASE_TAG}")
        if result.returncode and "HTTP 404" in result.stderr:
            self._release(
                "create", RELEASE_TAG, "--target", "main", "--title", RELEASE_TITLE,
                "--notes", "Rolling latest compiled PDF and native Word reports for Gold, A-Share, HK-Stock, and US-Stock.",
            )
            result = self._api(f"releases/tags/{RELEASE_TAG}")
        self.id = int(json.loads(_checked(result, "read GitHub Release"))["id"])

    def _api(self, endpoint: str, *args: str) -> subprocess.CompletedProcess[str]:
        return _run([self.gh, "api", "--hostname", "github.com", f"repos/{self.repository}/{endpoint}", *args],
                    self.env, timeout=30)

    def _release(self, *args: str) -> None:
        _checked(_run([self.gh, "release", *args, "--repo", self.repository], self.env, timeout=300),
                 f"gh release {args[0]}")

    def assets(self) -> dict[str, RemoteAsset]:
        result = self._api(f"releases/{self.id}/assets?per_page=100", "--paginate", "--slurp")
        pages = json.loads(_checked(result, "list GitHub Release assets"))
        assets = {}
        for page in pages:
            for item in page:
                digest = SHA256_RE.fullmatch(str(item.get("digest") or ""))
                name = str(item["name"])
                if name in assets:
                    raise RuntimeError(f"Duplicate Release asset name: {name}")
                assets[name] = RemoteAsset(
                    int(item["id"]), name, digest[1] if digest and item.get("state") == "uploaded" else None,
                )
        return assets

    def rename(self, asset: RemoteAsset, name: str) -> RemoteAsset:
        result = self._api(f"releases/assets/{asset.id}", "--method", "PATCH", "-f", f"name={name}")
        item = json.loads(_checked(result, f"rename Release asset {asset.name}"))
        if item.get("id") != asset.id or item.get("name") != name:
            raise RuntimeError(f"GitHub did not confirm the requested name {name}")
        return RemoteAsset(asset.id, name, asset.digest)

    def delete(self, asset: RemoteAsset) -> None:
        _checked(self._api(f"releases/assets/{asset.id}", "--method", "DELETE"),
                 f"delete temporary Release asset {asset.name}")

    def stage(self, asset: LocalAsset) -> None:
        self._release("upload", RELEASE_TAG, f"{asset.path}#{asset.label}")


def _save_json(path: Path, value: dict) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump(value, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _restore_pair(
    release: GitHubRelease, group: list[LocalAsset], prior: dict[str, RemoteAsset],
) -> None:
    assets = release.assets()
    for asset in group:
        old = prior.get(asset.name)
        if old is None:
            continue
        current = assets.get(asset.name)
        if current is not None and current.id == old.id:
            continue
        backup = assets.get(asset.backup_name)
        if backup is None or backup.id != old.id:
            raise RuntimeError(f"Previous Release attachment {asset.name} was not found.")
        if current is not None:
            if asset.staged_name in assets:
                release.delete(assets[asset.staged_name])
            release.rename(current, asset.staged_name)
        release.rename(backup, asset.name)


def _publish_release(
    repository: str, groups: list[tuple[LocalAsset, LocalAsset]], common_git_dir: Path,
    env: dict[str, str], *, force: bool,
) -> None:
    pending = common_git_dir / "pending_release_manifest.json"
    expected = {asset.name: asset.digest for group in groups for asset in group}
    previous = {}
    if pending.is_file():
        saved = json.loads(pending.read_text(encoding="utf-8"))
        if not isinstance(saved, dict) or not isinstance(saved.get("expected"), dict):
            raise RuntimeError(f"Invalid Release recovery record: {pending.name}")
        if saved.get("repository") == repository and saved.get("tag") == RELEASE_TAG:
            previous = saved["expected"]
    else:
        _save_json(pending, {"repository": repository, "tag": RELEASE_TAG, "expected": expected})
    release = GitHubRelease(repository, env)
    remote = release.assets()

    # Restore interrupted name switches before staging new content. Keep all
    # usable old bytes accessible while the next version uploads and verifies.
    for group in groups:
        # A prior process may have stopped after switching one format. Backups
        # identify the previous pair even when both stable names still exist.
        prior = {asset.name: remote[asset.backup_name] for asset in group if asset.backup_name in remote}
        if prior and any(
            asset.name not in remote
            or (asset.name in previous and remote[asset.name].digest != previous[asset.name])
            for asset in group
        ):
            _restore_pair(release, list(group), prior)
    _save_json(pending, {"repository": repository, "tag": RELEASE_TAG, "expected": expected})
    remote = release.assets()

    changes = [
        [asset for asset in group if force or asset.name not in remote or remote[asset.name].digest != asset.digest]
        for group in groups
    ]
    for group in changes:
        for asset in group:
            candidate = remote.get(asset.staged_name)
            if candidate is not None and candidate.digest == asset.digest:
                continue
            if candidate is not None:
                release.delete(candidate)
            release.stage(asset)

    remote = release.assets()
    for group in changes:
        for asset in group:
            staged = remote.get(asset.staged_name)
            if staged is None or staged.digest != asset.digest:
                raise RuntimeError(f"Remote checksum does not match staged attachment {asset.name}.")

    for group in changes:
        if not group:
            continue
        prior = {asset.name: remote[asset.name] for asset in group if asset.name in remote}
        if any(item.digest is None for item in prior.values()):
            raise RuntimeError("An existing stable Release attachment has no verifiable checksum.")
        try:
            for asset in group:
                old = prior.get(asset.name)
                if old is not None:
                    stale = remote.get(asset.backup_name)
                    if stale is not None:
                        release.delete(stale)
                    release.rename(old, asset.backup_name)
                release.rename(remote[asset.staged_name], asset.name)
            switched = release.assets()
            for asset in group:
                if asset.name not in switched or switched[asset.name].digest != asset.digest:
                    raise RuntimeError(f"GitHub did not verify switched attachment {asset.name}.")
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            try:
                _restore_pair(release, group, prior)
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as rollback:
                raise RuntimeError(
                    f"Release name switch failed: {exc}. Old copies were retained; restoration pending: {rollback}"
                ) from exc
            raise RuntimeError(f"Release name switch failed; previous attachments restored: {exc}") from exc

    remote = release.assets()
    mismatches = [name for name, digest in expected.items() if name not in remote or remote[name].digest != digest]
    if mismatches:
        raise RuntimeError(f"Final remote SHA256 mismatch or missing Release attachment: {', '.join(mismatches)}")
    _save_json(common_git_dir / "last_release_manifest.json", expected)
    for group in groups:
        for asset in group:
            for temporary in (asset.backup_name, asset.staged_name):
                if temporary in remote:
                    release.delete(remote[temporary])
    pending.unlink(missing_ok=True)
    print(f"[release] Verified {len(expected)} stable GitHub attachments by SHA256.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--message", help="Custom publication commit message.")
    parser.add_argument("--dry-run", action="store_true", help="Validate in temporary storage and preview Git status.")
    parser.add_argument("--skip-release", action="store_true", help="Push the validated website source only.")
    parser.add_argument("--force-release", action="store_true", help="Replace all 16 Release assets after verification.")
    parser.add_argument("--no-push", action="store_true", help="Validate and commit locally without remote changes.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = _clean_env()
    try:
        with tempfile.TemporaryDirectory(prefix="gir_publish_") as tmp:
            work = Path(tmp).resolve()
            output = work / "site"
            copies = work / "attachments"
            copies.mkdir()
            if args.dry_run:
                _build_and_lint(REPO_ROOT, output, env)
                print(_git(env, "--no-optional-locks", "status", "--short"), end="")
                if not (args.skip_release or args.no_push):
                    for group in _prepare_assets(REPO_ROOT, copies):
                        for asset in group:
                            print(f"[dry-run] {asset.name} SHA256 {asset.digest}")
                print("[dry-run] Temporary site validated.")
                return 0

            git_dir = _git_dir(env)
            common_git_dir = _git_dir(env, common=True)
            with _publish_lock(common_git_dir):
                if _git(env, "symbolic-ref", "--quiet", "--short", "HEAD").strip() != "main":
                    raise RuntimeError("Publication requires branch main.")
                if any((git_dir / name).exists() for name in ("MERGE_HEAD", "rebase-merge", "rebase-apply")):
                    raise RuntimeError("Complete the current Git merge or rebase before publishing.")
                remote_url = ""
                if not args.no_push:
                    push_urls = _git(env, "remote", "get-url", "--push", "--all", "origin").splitlines()
                    if len(push_urls) != 1:
                        raise RuntimeError("Publication requires one origin push URL.")
                    remote_url = push_urls[0]
                release_repo = None if args.skip_release or args.no_push else _remote_repository(remote_url)
                if release_repo is not None:
                    origin = _remote_repository(_git(env, "remote", "get-url", "origin").strip())
                    if origin.lower() != release_repo.lower():
                        raise RuntimeError("The origin fetch and push repositories differ.")
                current_tree = _git(env, "rev-parse", "HEAD^{tree}").strip()
                tree, automatic = _publication_tree(env, work / "publish-index")
                _validate_revision(tree, output, copies, env, check_release=release_repo is not None)
                if tree != current_tree:
                    if (current_tree if automatic else tree) != _git(env, "write-tree").strip():
                        raise RuntimeError("The staged tree changed during validation. Retry with the intended changes.")
                    if automatic:
                        _git(env, "read-tree", tree)
                    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
                    try:
                        _git(env, "commit", "-m", args.message or f"publish: update research reports {now} CST")
                    except (RuntimeError, subprocess.TimeoutExpired):
                        if (
                            automatic and _git(env, "rev-parse", "HEAD^{tree}").strip() == current_tree
                            and _git(env, "write-tree").strip() == tree
                        ):
                            _git(env, "read-tree", current_tree)
                        raise
                    if tree != _git(env, "rev-parse", "HEAD^{tree}").strip():
                        raise RuntimeError("The committed tree changed during validation. The commit was not pushed.")

                if args.no_push:
                    print("[git] Validated locally; remote push and Release skipped.")
                else:
                    groups = _push_main(env, output, copies, git_dir, check_release=release_repo is not None,
                                        artifact_tree=tree)
                    if release_repo is not None:
                        _publish_release(release_repo, groups, common_git_dir, env, force=args.force_release)
                # The locked final source has already produced these verified files.
                # Keep a previous site if the validated replacement cannot be installed.
                _install_site(output)
                if args.no_push:
                    print("[DONE] Validated the local publication snapshot.")
                else:
                    result = "Verified source and Release attachments published" if release_repo else "Verified source pushed"
                    print(f"[DONE] {result}. GitHub Pages deploys asynchronously through Actions.")
                return 0
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


def _install_site(output: Path) -> None:
    """Copy the validated site locally without losing an existing preview on error."""
    tmp = Path(tempfile.mkdtemp(prefix=".tmp_site_", dir=SITE_DIR.parent))
    incoming, previous = tmp / "incoming", tmp / "previous"
    keep_backup = False
    try:
        shutil.copytree(output, incoming)
        if SITE_DIR.exists():
            SITE_DIR.rename(previous)
        try:
            incoming.rename(SITE_DIR)
        except OSError as exc:
            if previous.exists():
                try:
                    previous.rename(SITE_DIR)
                except OSError as restore_error:
                    keep_backup = True
                    raise RuntimeError(f"Previous site retained at {previous}: {restore_error}") from exc
            raise
    finally:
        if not keep_backup:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    sys.exit(main())
