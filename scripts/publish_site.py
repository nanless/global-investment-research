#!/usr/bin/env python3
"""Validate and publish a committed site, then reconcile the rolling Release."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
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
from typing import Callable, Iterator
from uuid import uuid4

if __package__:
    from . import artifact_receipt, edition_run
else:
    import artifact_receipt
    import edition_run

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "_site"
CANONICAL_STAGE_PATHS = (
    "AGENTS.md", ".agents", "automations", "gold", "equity",
    "scripts", "tests", "README.md", ".gitignore", ".github",
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
REMOTE_LOCK = "gir-publication-lock.json"
REMOTE_JOURNAL = "gir-publication-journal.json"


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
        print(_checked(result, script), end="")


def _check_manuscripts(root: Path, env: dict[str, str], expected_edition: str | None = None) -> None:
    gold_daily = _latest_daily(root / "gold" / "daily", GOLD_DAILY_RE)
    gold = json.loads((root / "gold" / "data_snapshot.json").read_text(encoding="utf-8"))
    if isinstance(gold, dict) and isinstance(gold.get("edition_id"), str):
        edition_run.check_edition_reviews(gold["edition_id"], root=root)
    if expected_edition is not None:
        match = GOLD_DAILY_RE.fullmatch(gold_daily.name)
        assert match is not None
        named_edition = f"{match[1]}_{match[2]}" + (f"_r{match[3]}" if match[3] else "")
        equity = json.loads((root / "equity" / "state" / "market_state.json").read_text(encoding="utf-8"))
        if named_edition != expected_edition or any(
            not isinstance(item, dict) or item.get("edition_id") != expected_edition for item in (gold, equity)
        ):
            raise RuntimeError(f"Gold manuscript, gold snapshot and equity state must match {expected_edition}.")
        meta = re.search(r"<!--\s*DAILY_META\s*(\{.*?\})\s*-->", gold_daily.read_text(encoding="utf-8"), re.S)
        if meta is None or json.loads(meta[1]).get("edition_id") != expected_edition:
            raise RuntimeError(f"Gold manuscript metadata must match {expected_edition}.")

    for script, reports in (
        ("gold/lint_readability.py", [str(gold_daily), str(root / "gold" / f"{GOLD_MASTER}.md")]),
        ("equity/lint_equity.py", []),
    ):
        result = _run([sys.executable, "-B", str(root / script), "--precheck", "--strict", *reports], env, cwd=root)
        print(_checked(result, script), end="")


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
    seen = set()
    for path in (*folder.glob("*.md"), *folder.glob("archive/*/*.md")):
        match = pattern.fullmatch(path.name)
        if match and path.is_file():
            try:
                datetime.strptime(f"{match[1]} {match[2]}", "%Y-%m-%d %H%M")
            except ValueError as exc:
                raise RuntimeError(f"Invalid report date/time in {path.name}") from exc
            if match[3] and int(match[3]) < 2:
                raise RuntimeError(f"A revised report must use _r2 or a later revision: {path.name}")
            if match[2] not in {"0730", "1800"}:
                continue
            key = (match[1], int(match[2]), int(match[3] or 1))
            if key in seen:
                raise RuntimeError(f"Duplicate scheduled issue in active reports and archives: {path.name}")
            seen.add(key)
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


def _report_inputs(source: Path, report: Report) -> list[str]:
    if report.asset_stem.startswith("gold-"):
        inputs = ["gold/build_daily.py", "gold/docx_embed.py"]
        if (source / "gold" / "chart_input.py").is_file():
            inputs.append("gold/chart_input.py")
        if report.asset_stem == "gold-master-latest":
            inputs.extend(("gold/build_report.py", "gold/master_snapshot.json"))
        return inputs

    market = next(key for key, slug, _ in MARKETS if report.asset_stem.startswith(f"{slug}-"))
    return artifact_receipt.equity_render_inputs(market, flagship="-daily-" not in report.asset_stem)


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
                shutil.copyfile(original, path)
                validate(path)
                pair.append(LocalAsset(path, name, f"{report.label} ({fmt})", artifact_receipt.sha256_file(path)))
            except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
                errors.append(f"{relative}: {exc}")
        if len(pair) == 2:
            try:
                artifact_receipt.verify_receipt(
                    manuscript, repository=REPO_ROOT, tree=source, inputs=_report_inputs(source, report),
                    outputs={"pdf": pair[0].digest, "docx": pair[1].digest},
                )
                groups.append((pair[0], pair[1]))
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
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


def _validate_revision(
    revision: str, output: Path, copies: Path, env: dict[str, str], *,
    check_release: bool, edition: str | None = None,
) -> list[tuple[LocalAsset, LocalAsset]]:
    with _checkout_revision(revision, env) as source:
        _check_manuscripts(source, env, edition)
        _build_and_lint(source, output, env)
        return _prepare_assets(source, copies) if check_release else []


def _remote_main(env: dict[str, str]) -> str | None:
    result = _run(["git", "ls-remote", "--heads", "origin", "refs/heads/main"], env, timeout=30)
    head = _checked(result, "git ls-remote").strip()
    return head.split()[0] if head else None


def _require_remote_main(env: dict[str, str], sha: str) -> None:
    if _remote_main(env) != sha:
        raise RuntimeError(f"Remote main no longer points to publication commit {sha}; preserve the newer version.")


def _push_verified_commit(env: dict[str, str], commit: str, *, already_pushed: bool = False) -> None:
    if already_pushed or _remote_main(env) == commit:
        _require_remote_main(env, commit)
        return
    try:
        result = _run(["git", "push", "origin", f"{commit}:refs/heads/main"], env, timeout=120)
        _checked(result, "git push")
    except (RuntimeError, subprocess.TimeoutExpired):
        if _remote_main(env) == commit:
            return  # A transport error can occur after origin accepts the ref update.
        raise
    _require_remote_main(env, commit)


def _push_main(
    env: dict[str, str], output: Path, copies: Path, git_dir: Path,
    *, check_release: bool, edition: str | None = None, before_push: Callable[[str], None] | None = None,
) -> tuple[str, list[tuple[LocalAsset, LocalAsset]]]:
    for attempt in (1, 2):
        try:
            if _remote_main(env):
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
            commit, output, copies, env, check_release=check_release, edition=edition,
        )
        if before_push is not None:
            before_push(commit)
        try:
            _push_verified_commit(env, commit)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            if attempt == 2 or before_push is not None:
                raise
            print(f"[git] Retry after {exc}", file=sys.stderr)
            time.sleep(3)
            continue
        print(f"[git] Pushed verified commit {commit[:12]} to origin/main.")
        return commit, groups
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

    def upload(self, path: Path) -> None:
        self._release("upload", RELEASE_TAG, str(path))

    def stage(self, asset: LocalAsset) -> None:
        self._release("upload", RELEASE_TAG, f"{asset.path}#{asset.label}")

    def json_asset(self, asset: RemoteAsset) -> dict:
        result = self._api(f"releases/assets/{asset.id}", "-H", "Accept: application/octet-stream")
        content = _checked(result, f"read Release asset {asset.name}")
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError(f"Invalid Release recovery object {asset.name}")
        return value


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


@contextlib.contextmanager
def _remote_release_lock(
    release: GitHubRelease, common_git_dir: Path, working: Path, sha: str, recover_id: int | None,
) -> Iterator[Callable[[], None]]:
    """Serialize Release mutations by creating one reserved remote asset without replacement."""
    claim = common_git_dir / "release-lock-claim.json"
    asset = release.assets().get(REMOTE_LOCK)
    if recover_id is not None:
        if asset is None or asset.id != recover_id:
            raise RuntimeError("The selected Release lock no longer exists or has changed. No lock was removed.")
        release.delete(asset)
        asset = None
    if asset is not None:
        saved = json.loads(claim.read_text(encoding="utf-8")) if claim.is_file() else {}
        if not isinstance(saved, dict) or (saved.get("repository"), saved.get("digest")) != (
            release.repository, asset.digest,
        ):
            raise RuntimeError(
                f"Another publisher or an interrupted checkout owns Release lock {asset.id}. "
                "Its recovery requires confirming that owner has stopped."
            )
    if asset is None:
        lock_path = working / REMOTE_LOCK
        _save_json(lock_path, {"nonce": uuid4().hex, "sha": sha})
        digest = artifact_receipt.sha256_file(lock_path)
        _save_json(claim, {"repository": release.repository, "digest": digest})
        # GitHub rejects duplicate asset names. Never clobber a rival's lock.
        release.upload(lock_path)
        asset = release.assets().get(REMOTE_LOCK)
        if asset is None or asset.digest != digest:
            raise RuntimeError("GitHub did not confirm this checkout's Release lock.")

    def confirm_owner() -> None:
        current = release.assets().get(REMOTE_LOCK)
        if current is None or current.id != asset.id or current.digest != asset.digest:
            raise RuntimeError("The Release lock changed while publication was running.")

    try:
        yield confirm_owner
    finally:
        confirm_owner()
        release.delete(asset)
        claim.unlink(missing_ok=True)


def _recover_remote_release(
    release: GitHubRelease, groups: list[tuple[LocalAsset, LocalAsset]], guard: Callable[[], None],
) -> None:
    remote = release.assets()
    journal = remote.get(REMOTE_JOURNAL)
    if journal is None:
        if any(asset.backup_name in remote for group in groups for asset in group):
            raise RuntimeError("Release has a backup without a transaction journal. Review the saved asset IDs before publishing.")
        return

    transaction = release.json_asset(journal)
    expected = transaction.get("expected")
    previous = transaction.get("previous")
    names = {asset.name for group in groups for asset in group}
    if (
        transaction.get("schema") != 1 or not isinstance(expected, dict) or not isinstance(previous, dict)
        or set(expected) != names or not previous.keys() <= names
    ):
        raise RuntimeError("The remote Release recovery journal does not match the supported 16 attachments.")
    for group in groups:
        # A completed pair is safe to keep. An interrupted pair can be
        # recovered even in another clone, using the recorded remote IDs.
        if all(asset.name in remote and remote[asset.name].digest == expected[asset.name] for asset in group):
            continue
        prior = {
            asset.name: RemoteAsset(int(previous[asset.name]["id"]), asset.name, previous[asset.name]["digest"])
            for asset in group if asset.name in previous
        }
        guard()
        _restore_pair(release, list(group), prior)

    # Old backups may only be removed after every pair has been recovered.
    remote = release.assets()
    for group in groups:
        for asset in group:
            if asset.backup_name in remote:
                guard()
                release.delete(remote[asset.backup_name])
    guard()
    release.delete(journal)


def _publish_release(
    repository: str, groups: list[tuple[LocalAsset, LocalAsset]], common_git_dir: Path,
    env: dict[str, str], *, force: bool, sha: str, recover_id: int | None = None,
) -> dict[str, str]:
    _require_remote_main(env, sha)
    release = GitHubRelease(repository, env)
    with tempfile.TemporaryDirectory(prefix="gir_release_") as working:
        path = Path(working)
        with _remote_release_lock(release, common_git_dir, path, sha, recover_id) as confirm_owner:
            def guard() -> None:
                _require_remote_main(env, sha)
                confirm_owner()

            guard()
            _recover_remote_release(release, groups, guard)
            return _switch_release_assets(release, groups, common_git_dir, path, guard, force=force, sha=sha)


def _switch_release_assets(
    release: GitHubRelease, groups: list[tuple[LocalAsset, LocalAsset]], common_git_dir: Path,
    working: Path, guard: Callable[[], None], *, force: bool, sha: str,
) -> dict[str, str]:
    expected = {asset.name: asset.digest for group in groups for asset in group}
    remote = release.assets()
    changes = [
        [asset for asset in group if force or asset.name not in remote or remote[asset.name].digest != asset.digest]
        for group in groups
    ]
    pending = common_git_dir / "pending_release_manifest.json"
    _save_json(pending, {"repository": release.repository, "tag": RELEASE_TAG, "sha": sha, "expected": expected})

    for group in changes:
        if group:
            guard()
        for asset in group:
            candidate = remote.get(asset.staged_name)
            if candidate is not None and candidate.digest == asset.digest:
                continue
            if candidate is not None:
                release.delete(candidate)
            release.stage(asset)

    remote = release.assets()
    previous = {}
    for group in changes:
        for asset in group:
            staged = remote.get(asset.staged_name)
            if staged is None or staged.digest != asset.digest:
                raise RuntimeError(f"Remote checksum does not match staged attachment {asset.name}.")
            old = remote.get(asset.name)
            if old is not None and old.digest is None:
                raise RuntimeError(f"Existing Release attachment has no verifiable checksum: {asset.name}.")
            if old is not None:
                previous[asset.name] = {"id": old.id, "digest": old.digest}

    journal = None
    if any(changes):
        guard()
        journal_path = working / REMOTE_JOURNAL
        _save_json(journal_path, {"schema": 1, "sha": sha, "expected": expected, "previous": previous})
        release.upload(journal_path)
        journal = release.assets().get(REMOTE_JOURNAL)
        if journal is None or journal.digest != artifact_receipt.sha256_file(journal_path):
            raise RuntimeError("GitHub did not verify the durable Release recovery journal.")

    for group in changes:
        if not group:
            continue
        guard()
        prior = {asset.name: remote[asset.name] for asset in group if asset.name in remote}
        try:
            for asset in group:
                old = prior.get(asset.name)
                if old is not None:
                    release.rename(old, asset.backup_name)
                release.rename(remote[asset.staged_name], asset.name)
            switched = release.assets()
            for asset in group:
                if asset.name not in switched or switched[asset.name].digest != asset.digest:
                    raise RuntimeError(f"GitHub did not verify switched attachment {asset.name}.")
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            try:
                guard()
                _restore_pair(release, group, prior)
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as rollback:
                raise RuntimeError(
                    f"Release name switch failed: {exc}. Previous copies and recovery journal retained: {rollback}"
                ) from exc
            raise RuntimeError(f"Release name switch failed; previous attachments restored: {exc}") from exc

    guard()
    remote = release.assets()
    mismatches = [name for name, digest in expected.items() if name not in remote or remote[name].digest != digest]
    if mismatches:
        raise RuntimeError(f"Final remote SHA256 mismatch or missing Release attachment: {', '.join(mismatches)}")
    _save_json(common_git_dir / "last_release_manifest.json", expected)
    _save_json(common_git_dir / "last_release_commit.json", {"sha": sha, "assets": expected})
    for group in groups:
        for asset in group:
            for temporary in (asset.backup_name, asset.staged_name):
                if temporary in remote:
                    release.delete(remote[temporary])
    if journal is not None:
        release.delete(journal)
    pending.unlink(missing_ok=True)
    print(f"[release] Verified {len(expected)} stable GitHub attachments by SHA256.")
    return {name: asset.digest for name, asset in remote.items() if name in expected and asset.digest is not None}


def _prepare_commit(
    env: dict[str, str], work: Path, output: Path, copies: Path, *,
    check_release: bool, edition: str | None, message: str | None,
) -> None:
    current_tree = _git(env, "rev-parse", "HEAD^{tree}").strip()
    tree, automatic = _publication_tree(env, work / "publish-index")
    _validate_revision(tree, output, copies, env, check_release=check_release, edition=edition)
    if tree == current_tree:
        return
    if (current_tree if automatic else tree) != _git(env, "write-tree").strip():
        raise RuntimeError("The staged tree changed during validation. Retry with the intended changes.")
    if automatic:
        _git(env, "read-tree", tree)
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    try:
        _git(env, "commit", "-m", message or f"publish: update research reports {now} CST")
    except (RuntimeError, subprocess.TimeoutExpired):
        if (
            automatic and _git(env, "rev-parse", "HEAD^{tree}").strip() == current_tree
            and _git(env, "write-tree").strip() == tree
        ):
            _git(env, "read-tree", current_tree)
        raise
    if tree != _git(env, "rev-parse", "HEAD^{tree}").strip():
        raise RuntimeError("The committed tree changed during validation. The commit was not pushed.")


def _push_edition(
    token: str, edition: str, repository: str, env: dict[str, str], *,
    git_dir: Path, common: Path, work: Path, output: Path, copies: Path, message: str | None,
) -> tuple[str, list[tuple[LocalAsset, LocalAsset]], Path]:
    intent = edition_run.push_intent_path(common, token)
    pushed = edition_run.publication_commit(token)
    if intent.is_file():
        record = json.loads(intent.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("edition") != edition or record.get("repository") != repository:
            raise RuntimeError("The saved push intent does not identify this edition and repository.")
        expected = record["sha"]
        if pushed is not None and expected != pushed:
            raise RuntimeError("The saved push intent and recorded publication disagree.")
    else:
        expected = pushed

    if expected is not None:
        if _git(env, "rev-parse", "HEAD").strip() != expected:
            raise RuntimeError(f"Resume the recorded publication commit {expected} before creating another commit.")
        groups = _validate_revision(expected, output, copies, env, check_release=True, edition=edition)
        edition_run.check_publication_candidate(token, sha=expected, repository=repository)
        _push_verified_commit(env, expected, already_pushed=pushed is not None)
        sha = expected
    else:
        _prepare_commit(env, work, output, copies, check_release=True, edition=edition, message=message)

        def remember(candidate: str) -> None:
            edition_run.check_publication_candidate(token, sha=candidate, repository=repository)
            _save_json(intent, {"edition": edition, "repository": repository, "sha": candidate})

        sha, groups = _push_main(
            env, output, copies, git_dir, check_release=True, edition=edition, before_push=remember,
        )
    edition_run.record_push(token, sha=sha, repository=repository)
    return sha, groups, intent


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--message", help="Custom publication commit message.")
    parser.add_argument("--dry-run", action="store_true", help="Validate in temporary storage and preview Git status.")
    parser.add_argument("--check-manuscripts", action="store_true", help="Run both source manuscript lint gates without building or publishing.")
    parser.add_argument("--skip-release", action="store_true", help="Push the validated website source only.")
    parser.add_argument("--force-release", action="store_true", help="Replace all 16 Release assets after verification.")
    parser.add_argument("--no-push", action="store_true", help="Validate and commit locally without remote changes.")
    parser.add_argument("--edition-token", help="Token for an active edition in the publish phase.")
    parser.add_argument(
        "--recover-release-lock", type=int, metavar="ASSET_ID",
        help="Recover a stale remote Release lock after verifying that its publisher has stopped.",
    )
    args = parser.parse_args(argv)
    if (args.edition_token or args.recover_release_lock is not None) and (
        args.dry_run or args.check_manuscripts or args.no_push or args.skip_release
    ):
        parser.error("Edition tokens and remote lock recovery require full publication.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = _clean_env()
    try:
        if args.check_manuscripts:
            _check_manuscripts(REPO_ROOT, env)
            return 0

        token = args.edition_token
        with tempfile.TemporaryDirectory(prefix="gir_publish_") as tmp:
            work = Path(tmp).resolve()
            output = work / "site"
            copies = work / "attachments"
            copies.mkdir()
            if args.dry_run:
                _check_manuscripts(REPO_ROOT, env)
                _build_and_lint(REPO_ROOT, output, env)
                print(_git(env, "--no-optional-locks", "status", "--short"), end="")
                if not (args.skip_release or args.no_push):
                    for group in _prepare_assets(REPO_ROOT, copies):
                        for asset in group:
                            print(f"[dry-run] {asset.name} SHA256 {asset.digest}")
                print("[dry-run] Temporary site validated.")
                return 0

            git_dir = _git_dir(env)
            common = _git_dir(env, common=True)
            with _publish_lock(common):
                if _git(env, "symbolic-ref", "--quiet", "--short", "HEAD").strip() != "main":
                    raise RuntimeError("Publication requires branch main.")
                if any((git_dir / name).exists() for name in ("MERGE_HEAD", "rebase-merge", "rebase-apply")):
                    raise RuntimeError("Complete the current Git merge or rebase before publishing.")
                if token is not None and not re.fullmatch(r"[0-9a-f]{32}", token):
                    raise RuntimeError("Invalid edition publication token.")
                if token is None:
                    edition_run.assert_manual_publish_allowed()
                edition = edition_run.publication_context(token) if token is not None else None

                repository = None
                if not args.no_push:
                    push_urls = _git(env, "remote", "get-url", "--push", "--all", "origin").splitlines()
                    if len(push_urls) != 1:
                        raise RuntimeError("Publication requires one origin push URL.")
                    if not args.skip_release:
                        repository = _remote_repository(push_urls[0])
                        origin = _remote_repository(_git(env, "remote", "get-url", "origin").strip())
                        if origin.lower() != repository.lower():
                            raise RuntimeError("The origin fetch and push repositories differ.")

                intent = None
                if token is not None:
                    assert edition is not None and repository is not None
                    sha, groups, intent = _push_edition(
                        token, edition, repository, env, git_dir=git_dir, common=common, work=work,
                        output=output, copies=copies, message=args.message,
                    )
                else:
                    _prepare_commit(
                        env, work, output, copies, check_release=repository is not None,
                        edition=None, message=args.message,
                    )
                    if not args.no_push:
                        sha, groups = _push_main(env, output, copies, git_dir, check_release=repository is not None)

                if repository is not None:
                    assets = _publish_release(
                        repository, groups, common, env, force=args.force_release, sha=sha,
                        recover_id=args.recover_release_lock,
                    )
                    if token is not None:
                        edition_run.record_publication(token, sha=sha, repository=repository, assets=assets)
                        intent.unlink(missing_ok=True)

                _install_site(output)
                if args.no_push:
                    print("[DONE] Validated the local publication snapshot.")
                else:
                    result = "Verified source and Release attachments published" if repository else "Verified source pushed"
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
