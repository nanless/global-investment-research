#!/usr/bin/env python3
"""Validate, commit, and push the pure-web research portal for GitHub Pages."""

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator, TypeVar

if __package__:
    from . import edition_run, pages_release
    from .state_transaction import state_read_lock, state_write_lock
else:
    import edition_run
    import pages_release
    from state_transaction import state_read_lock, state_write_lock

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "_site"
AUTOMATED_STAGE_PATHS = ("gold", "equity")
CANONICAL_STAGE_PATHS = (
    "AGENTS.md", ".agents", "automations", "gold", "equity",
    "scripts", "tests", "README.md", ".gitignore", ".github",
)
FORBIDDEN_STAGE_SUFFIXES = (".pdf", ".docx", ".artifacts.json")
FORBIDDEN_STAGE_FILENAMES = (
    "_edition_patch.json",
    "_ledger_patch.json",
    "_rsi_patch.json",
    "_audit_patch.json",
    "_rollover_patch.json",
    "_archive_patch.json",
)
TRANSIENT_PATCH_FILES = (
    "equity/state/_edition_patch.json",
    "gold/daily/_ledger_patch.json",
    "gold/daily/_rsi_patch.json",
    "equity/state/_rsi_patch.json",
    "equity/state/_audit_patch.json",
    "equity/state/_rollover_patch.json",
    "gold/daily/_archive_patch.json",
)
STALE_QUOTE_WARN_MINUTES = 45
EXTENDED_EQUITY_STATE_FILES = (
    "equity/state/multi_asset_channels.json",
    "equity/state/etf_universe.json",
    "equity/state/deep_dossiers.json",
    "equity/state/policy_calendar.json",
)
GOLD_MASTER = "黄金跨世纪周期与2026-2030终审研究报告"
CST = timezone(timedelta(hours=8))
GOLD_DAILY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_.*黄金深度研报(?:_r(\d+))?\.md$")
_T = TypeVar("_T")
_TRANSIENT_NET_RE = re.compile(
    r"HTTP 50[0234]|timeout|timed out|connection reset|TLS|EOF|Could not resolve",
    re.IGNORECASE,
)
_NON_FAST_FORWARD_RE = re.compile(
    r"non-fast-forward|fetch first|tip of your current branch is behind|remote contains work that you do not have",
    re.IGNORECASE,
)


class _NonFastForwardError(RuntimeError):
    """Deterministic remote non-fast-forward rejection where the commit never landed."""


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
    cmd: list[str], env: dict[str, str], *, cwd: Path | None = None, timeout: int = 240
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


def _is_transient_error(exc: BaseException) -> bool:
    return isinstance(exc, subprocess.TimeoutExpired) or (
        isinstance(exc, RuntimeError) and bool(_TRANSIENT_NET_RE.search(str(exc)))
    )


def _is_non_fast_forward_error(exc: BaseException) -> bool:
    return isinstance(exc, RuntimeError) and bool(_NON_FAST_FORWARD_RE.search(str(exc)))


def _retry_transient(fn: Callable[[], _T], *, label: str, attempts: int = 3) -> _T:
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            if attempt >= attempts or not _is_transient_error(exc):
                raise
            delay = 2 ** attempt  # 2s, 4s backoff
            print(
                f"[retry] {label} failed transiently ({attempt}/{attempts}): {exc}; retrying in {delay}s",
                file=sys.stderr,
            )
            time.sleep(delay)
    raise RuntimeError(f"{label} failed after {attempts} attempts")


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


def _check_no_transient_patch_files(root: Path) -> None:
    present = [rel for rel in TRANSIENT_PATCH_FILES if (root / rel).exists()]
    if present:
        raise RuntimeError(
            "Transient patch file(s) exist in working tree; apply or remove them before publishing: "
            + ", ".join(present)
        )


def _parse_gold_as_of(gold: dict) -> datetime | None:
    raw = gold.get("as_of_short")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=CST)
    except ValueError:
        return None


def _parse_equity_as_of(equity: dict) -> datetime | None:
    raw = equity.get("as_of_cst")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        return dt.astimezone(CST) if dt.tzinfo is not None else dt.replace(tzinfo=CST)
    except ValueError:
        return None


def _warn_stale_as_of(
    gold: dict,
    equity: dict,
    *,
    now: datetime | None = None,
    max_age_minutes: int = STALE_QUOTE_WARN_MINUTES,
) -> list[str]:
    now_cst = (now or datetime.now(CST)).astimezone(CST)
    threshold = timedelta(minutes=max_age_minutes)
    warnings: list[str] = []

    gold_dt = _parse_gold_as_of(gold)
    if gold_dt is not None and (now_cst - gold_dt) > threshold:
        age_min = int((now_cst - gold_dt).total_seconds() // 60)
        warnings.append(
            f"[WARN] Gold snapshot as_of_short ({gold.get('as_of_short')}) is {age_min}m old "
            f"(>{max_age_minutes}m) at publish time."
        )

    equity_dt = _parse_equity_as_of(equity)
    if equity_dt is not None and (now_cst - equity_dt) > threshold:
        age_min = int((now_cst - equity_dt).total_seconds() // 60)
        warnings.append(
            f"[WARN] Equity market_state as_of_cst ({equity.get('as_of_cst')}) is {age_min}m old "
            f"(>{max_age_minutes}m) at publish time."
        )

    for msg in warnings:
        print(msg, file=sys.stderr)
    return warnings


def _check_manuscripts(root: Path, env: dict[str, str], expected_edition: str | None = None) -> None:
    _check_no_transient_patch_files(root)
    gold_daily = _latest_daily(root / "gold" / "daily", GOLD_DAILY_RE)
    gold = json.loads((root / "gold" / "data_snapshot.json").read_text(encoding="utf-8"))

    market_state_path = root / "equity" / "state" / "market_state.json"
    if not market_state_path.is_file():
        raise RuntimeError("Missing required equity state file: equity/state/market_state.json")
    equity = json.loads(market_state_path.read_text(encoding="utf-8"))
    equity_edition = equity.get("edition_id") if isinstance(equity, dict) else None
    if not isinstance(equity_edition, str) or not equity_edition.strip():
        raise RuntimeError("equity/state/market_state.json must contain a non-empty edition_id.")

    match = GOLD_DAILY_RE.fullmatch(gold_daily.name)
    assert match is not None
    named_edition = f"{match[1]}_{match[2]}" + (f"_r{match[3]}" if match[3] else "")
    target_edition = equity_edition if expected_edition is None else expected_edition
    if named_edition != target_edition or any(
        not isinstance(item, dict) or item.get("edition_id") != target_edition for item in (gold, equity)
    ):
        raise RuntimeError(f"Gold manuscript, gold snapshot and equity state must match {target_edition}.")
    meta = re.search(r"<!--\s*DAILY_META\s*(\{.*?\})\s*-->", gold_daily.read_text(encoding="utf-8"), re.S)
    if meta is None or json.loads(meta[1]).get("edition_id") != target_edition:
        raise RuntimeError(f"Gold manuscript metadata must match {target_edition}.")
    edition_run.check_edition_reviews(target_edition, root=root)
    _warn_stale_as_of(gold, equity)

    for rel in EXTENDED_EQUITY_STATE_FILES:
        state_path = root / rel
        if not state_path.is_file():
            raise RuntimeError(f"Missing required extended equity state file: {rel}")
        try:
            state_obj = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid JSON in {rel}: {exc}") from exc
        if not isinstance(state_obj, dict) or state_obj.get("edition_id") != equity_edition:
            got = state_obj.get("edition_id") if isinstance(state_obj, dict) else None
            raise RuntimeError(
                f"{rel} edition_id ({got!r}) must match equity/state/market_state.json ({equity_edition!r})."
            )

    for script, reports in (
        ("gold/lint_readability.py", [str(gold_daily), str(root / "gold" / f"{GOLD_MASTER}.md")]),
        ("equity/lint_equity.py", []),
    ):
        result = _run([sys.executable, "-B", str(root / script), "--strict", *reports], env, cwd=root)
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


def _scoped(path: str, scope: tuple[str, ...] = CANONICAL_STAGE_PATHS) -> bool:
    return any(path == key or path.startswith(f"{key}/") for key in scope)


def _is_forbidden_stage_path(path: str) -> bool:
    low = path.lower()
    name = Path(path).name.lower()
    return name in FORBIDDEN_STAGE_FILENAMES or any(low.endswith(suffix) for suffix in FORBIDDEN_STAGE_SUFFIXES)


def _check_tree_no_forbidden_files(env: dict[str, str], tree: str) -> None:
    files = []
    non_regular = []
    for entry in _git(env, "ls-tree", "-r", "-z", tree).split("\0"):
        if not entry:
            continue
        header, path = entry.split("\t", 1)
        mode = header.split(" ", 1)[0]
        files.append(path)
        if mode not in {"100644", "100755"}:
            non_regular.append(path)
    if non_regular:
        sample = ", ".join(non_regular[:10])
        raise RuntimeError(f"Publication tree inputs must be regular files: {sample}")
    forbidden = [p for p in files if p and _is_forbidden_stage_path(p)]
    if forbidden:
        sample = ", ".join(forbidden[:10])
        raise RuntimeError(
            f"Forbidden binary/receipt file(s) or temporary patch file(s) cannot enter web-only publication commit: {sample}"
        )


def _normalize_explicit_stage_paths(
    raw_paths: list[str], scope: tuple[str, ...]
) -> list[str]:
    normalized: list[str] = []
    repo_resolved = REPO_ROOT.resolve()
    for raw in raw_paths:
        raw_s = raw.strip()
        if not raw_s:
            continue
        candidate = (repo_resolved / raw_s).resolve()
        if not candidate.is_relative_to(repo_resolved):
            raise RuntimeError(f"Explicit --stage path escapes repository root: {raw_s!r}")
        rel = candidate.relative_to(repo_resolved).as_posix()
        if rel in ("", "."):
            raise RuntimeError("Explicit --stage must specify in-scope paths rather than repository root.")
        if _is_forbidden_stage_path(rel):
            raise RuntimeError(f"Forbidden binary/receipt file cannot be staged: {rel}")
        if not _scoped(rel, scope):
            raise RuntimeError(f"Explicit --stage path is outside publication scope: {rel}")
        normalized.append(rel)
    if not normalized:
        raise RuntimeError("Explicit --stage requires at least one valid in-scope path.")
    return normalized


def _publication_tree(
    env: dict[str, str],
    index: Path,
    *,
    automated: bool = False,
    explicit_stage: list[str] | None = None,
) -> tuple[str, bool]:
    _check_no_transient_patch_files(REPO_ROOT)
    if automated:
        edition_run.check_scheduled_runtime(lambda *args: _git(env, *args))
    scope = AUTOMATED_STAGE_PATHS if automated else CANONICAL_STAGE_PATHS
    staged = [p for p in _git(env, "diff", "--cached", "--name-only", "-z", "--no-renames").split("\0") if p]
    if explicit_stage and staged:
        raise RuntimeError("Clear existing staged changes before using explicit --stage.")
    outside = [path for path in staged if not _scoped(path, scope)]
    if outside:
        raise RuntimeError(f"Already staged outside the publication scope: {', '.join(outside)}")
    if staged:
        # An explicit index is the user's selection. Preserve unstaged changes.
        print("[git] Using existing in-scope staged changes.")
        tree = _git(env, "write-tree").strip()
        _check_tree_no_forbidden_files(env, tree)
        return tree, False

    if explicit_stage:
        targets = _normalize_explicit_stage_paths(explicit_stage, scope)
        tracked = _git(env, "ls-files", "-z", "--", *targets).split("\0")
        paths = [
            key for key in targets
            if (REPO_ROOT / key).exists() or any(path == key or path.startswith(f"{key}/") for path in tracked)
        ]
        if not paths:
            raise RuntimeError(f"None of the explicit --stage paths exist or are tracked: {', '.join(targets)}")
    else:
        tracked = _git(env, "ls-files", "-z", "--", *scope).split("\0")
        paths = [
            key for key in scope
            if (REPO_ROOT / key).exists() or any(path == key or path.startswith(f"{key}/") for path in tracked)
        ]
        if not paths:
            raise RuntimeError("No publication source paths found in this checkout.")

    temporary = dict(env, GIT_INDEX_FILE=str(index))
    _git(temporary, "read-tree", "HEAD")
    _git(temporary, "add", "-A", "--", *paths)
    tree = _git(temporary, "write-tree").strip()
    _check_tree_no_forbidden_files(env, tree)
    return tree, True


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
            if match[2] not in {"0730", "1130", "1800"}:
                continue
            key = (match[1], int(match[2]), int(match[3] or 1))
            if key in seen:
                raise RuntimeError(f"Duplicate scheduled issue in active reports and archives: {path.name}")
            seen.add(key)
            candidates.append((key, path))
    if not candidates:
        raise RuntimeError(f"No report issue found in {folder.name}/")
    return max(candidates)[1]


def _git_dir(env: dict[str, str], *, common: bool = False) -> Path:
    args = ("--path-format=absolute", "--git-common-dir") if common else ("--absolute-git-dir",)
    return Path(_git(env, "rev-parse", *args).strip())


def _remote_repository(url: str) -> str:
    try:
        return edition_run.github_repository(url)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


def _validate_revision(
    revision: str, output: Path, env: dict[str, str], *, edition: str | None = None,
) -> None:
    _check_tree_no_forbidden_files(env, revision)
    with _checkout_revision(revision, env) as source:
        _check_manuscripts(source, env, edition)
        _build_and_lint(source, output, env)


def _require_nonregressing_edition(env: dict[str, str], candidate: str, baseline: str) -> None:
    if candidate == baseline:
        return

    def edition_for(tree: str) -> str:
        return pages_release.edition_from_snapshots([
            _git(env, "show", f"{tree}:{path}").encode("utf-8")
            for path in pages_release.EDITION_PATHS
        ])

    old_edition = edition_for(baseline)
    new_edition = edition_for(candidate)
    old_key = edition_run._edition_key(old_edition)
    new_key = edition_run._edition_key(new_edition)
    if old_key is None or new_key is None:
        raise RuntimeError("Publication snapshots must identify valid dated editions.")
    if new_key < old_key:
        raise RuntimeError(f"Publication edition {new_edition} would replace the newer edition {old_edition}.")


def _remote_main(env: dict[str, str]) -> str | None:
    def _fetch() -> str | None:
        result = _run(["git", "ls-remote", "--heads", "origin", "refs/heads/main"], env, timeout=30)
        head = _checked(result, "git ls-remote").strip()
        return head.split()[0] if head else None

    return _retry_transient(_fetch, label="git ls-remote origin/main")


def _require_remote_main(env: dict[str, str], sha: str) -> None:
    if _remote_main(env) != sha:
        raise RuntimeError(f"Remote main no longer points to publication commit {sha}; preserve the newer version.")


def _fetch_remote_main(env: dict[str, str]) -> str:
    remote = _remote_main(env)
    if remote is None:
        raise RuntimeError("Automated publication requires an existing origin/main branch.")
    commit = f"{remote}^{{commit}}"
    if _run(["git", "cat-file", "-e", commit], env, timeout=30).returncode:
        fetch = _run(["git", "fetch", "--no-write-fetch-head", "origin", "main"], env, timeout=60)
        _checked(fetch, "git fetch origin main")
        _git(env, "cat-file", "-e", commit)
    return remote


def _is_ancestor(env: dict[str, str], ancestor: str, descendant: str) -> bool:
    anc = _run(["git", "merge-base", "--is-ancestor", ancestor, descendant], env, timeout=30)
    if anc.returncode == 0:
        return True
    if anc.returncode == 1:
        return False
    detail = (anc.stderr or anc.stdout).strip()
    raise RuntimeError(f"git merge-base failed ({anc.returncode}): {detail}")


def _is_commit_on_remote_main(env: dict[str, str], commit: str) -> bool:
    """Verify the candidate is still reachable even if main moved after the push."""
    return _is_ancestor(env, commit, _fetch_remote_main(env))


def _automated_push_needed(env: dict[str, str], commit: str, *, already_pushed: bool) -> bool:
    remote = _fetch_remote_main(env)
    if _is_ancestor(env, commit, remote):
        return False
    if already_pushed:
        raise RuntimeError(f"Recorded publication commit {commit} is not reachable from remote main.")
    if not _is_ancestor(env, remote, commit):
        raise _NonFastForwardError("Remote main moved ahead of the publication candidate.")

    # Inspect each outgoing commit. A later revert does not remove paths from Git history.
    paths = _git(
        env, "log", "--format=", "--name-only", "--no-renames", "--diff-merges=first-parent",
        "-z", f"{remote}..{commit}", "--",
    ).split("\0")
    outside = sorted({path for path in paths if path and not _scoped(path, AUTOMATED_STAGE_PATHS)})
    if outside:
        raise RuntimeError(f"Outgoing commits include paths outside automated publication scope: {', '.join(outside)}")
    protected = _git(
        env, "log", "--full-history", "--format=", "--name-only", "--no-renames", "--diff-merges=first-parent",
        "-z", f"{remote}..{commit}", "--", *edition_run.SCHEDULED_RUNTIME_PATHS,
    ).split("\0")
    changed_runtime = sorted({path for path in protected if path})
    if changed_runtime:
        raise RuntimeError(f"Outgoing commits change protected automated publication paths: {', '.join(changed_runtime)}")
    edition_run.check_scheduled_runtime(lambda *args: _git(env, *args))
    return True


def _push_verified_commit(
    env: dict[str, str], commit: str, *, already_pushed: bool = False, automated: bool = False,
    before_push: Callable[[str], None] | None = None,
) -> None:
    if not automated and (already_pushed or _remote_main(env) == commit):
        _require_remote_main(env, commit)
        return
    for attempt in (1, 2):
        if automated:
            try:
                if not _automated_push_needed(env, commit, already_pushed=already_pushed):
                    return
            except _NonFastForwardError as exc:
                if attempt == 1:
                    raise
                # The earlier transport failure may have happened after the server accepted the push.
                raise RuntimeError("Remote main changed during an unconfirmed push; preserve its intent.") from exc
        if attempt == 1 and before_push is not None:
            before_push(commit)
        try:
            result = _run(["git", "push", "origin", f"{commit}:refs/heads/main"], env, timeout=120)
            _checked(result, "git push")
            break
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            landed = _is_commit_on_remote_main(env, commit) if automated else _remote_main(env) == commit
            if landed:
                return  # A transport error can occur after origin accepts the ref update.
            if attempt == 1 and _is_non_fast_forward_error(exc):
                raise _NonFastForwardError(str(exc)) from exc
            if attempt == 2 or not _is_transient_error(exc):
                raise
            print(f"[git] Retry push of {commit[:12]} after transient error: {exc}", file=sys.stderr)
            time.sleep(3)
    if automated:
        if not _is_commit_on_remote_main(env, commit):
            raise RuntimeError(f"Publication commit {commit} is not reachable from remote main after pushing.")
    else:
        _require_remote_main(env, commit)


def _push_main(
    env: dict[str, str], output: Path, git_dir: Path,
    *,
    edition: str | None = None,
    before_push: Callable[[str], None] | None = None,
    on_push_rejected: Callable[[str], None] | None = None,
    validated_tree: str | None = None,
    validated_output: Path | None = None,
) -> str:
    for attempt in (1, 2):
        remote = None
        try:
            remote = _remote_main(env)
            if remote:
                with state_write_lock(REPO_ROOT):
                    pull = _run(["git", "pull", "--rebase", "--autostash", "origin", "main"], env, timeout=90)
                    _checked(pull, "git pull --rebase")
                if pull.stderr.strip():
                    print(pull.stderr.strip())
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            if any((git_dir / name).exists() for name in ("rebase-merge", "rebase-apply")):
                with state_write_lock(REPO_ROOT):
                    _git(env, "rebase", "--abort")
            if attempt == 2:
                raise
            print(f"[git] Retry after {exc}", file=sys.stderr)
            time.sleep(3)
            continue

        if _git(env, "diff", "--name-only", "--diff-filter=U", "-z"):
            raise RuntimeError("Rebase left unmerged paths. Resolve them before continuing.")
        commit = _git(env, "rev-parse", "HEAD").strip()
        if remote:
            _require_nonregressing_edition(env, commit, remote)
        commit_tree = _git(env, "rev-parse", f"{commit}^{{tree}}").strip()
        prebuilt = validated_output or output
        if (
            validated_tree is not None
            and commit_tree == validated_tree
            and prebuilt.is_dir()
            and (prebuilt / "index.html").is_file()
        ):
            if prebuilt != output:
                if output.exists():
                    shutil.rmtree(output)
                shutil.copytree(prebuilt, output)
            print(
                f"[git] Reusing pre-validated tree {commit_tree[:12]} for commit {commit[:12]} "
                f"before push {attempt}/2."
            )
        else:
            print(f"[git] Validating final commit {commit[:12]} before push {attempt}/2.")
            _validate_revision(commit, output, env, edition=edition)
            validated_tree = commit_tree
            validated_output = output
        try:
            _push_verified_commit(env, commit, automated=edition is not None, before_push=before_push)
        except _NonFastForwardError as exc:
            # Origin deterministically rejected the ref update (non-fast-forward) and commit never landed.
            if on_push_rejected is not None:
                on_push_rejected(commit)
            if attempt == 2:
                raise
            print(f"[git] Remote main moved ahead (non-fast-forward); rebasing and retrying: {exc}", file=sys.stderr)
            time.sleep(3)
            continue
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            # Uncertain network/transport failure: keep push intent locked when before_push was used.
            if attempt == 2 or before_push is not None:
                raise
            print(f"[git] Retry after {exc}", file=sys.stderr)
            time.sleep(3)
            continue
        print(f"[git] Pushed verified commit {commit[:12]} to origin/main.")
        return commit
    raise RuntimeError("Git push did not complete.")


def _save_json(path: Path, value: dict) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump(value, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)


def _prepare_commit(
    env: dict[str, str], work: Path, output: Path, *,
    edition: str | None,
    message: str | None,
    automated: bool = False,
    explicit_stage: list[str] | None = None,
    token: str | None = None,
) -> tuple[str, Path]:
    current_tree = _git(env, "rev-parse", "HEAD^{tree}").strip()
    with state_read_lock(REPO_ROOT):
        tree, automatic = _publication_tree(
            env, work / "publish-index", automated=automated, explicit_stage=explicit_stage,
        )
    if token is not None:
        edition_run.check_gold_ledger_history_for_token(token, tree)
    _require_nonregressing_edition(env, tree, current_tree)
    _validate_revision(tree, output, env, edition=edition)
    if tree == current_tree:
        return tree, output
    if automated:
        edition_run.check_scheduled_runtime(lambda *args: _git(env, *args))
    if (current_tree if automatic else tree) != _git(env, "write-tree").strip():
        raise RuntimeError("The staged tree changed during validation. Retry with the intended changes.")
    if automatic:
        _git(env, "read-tree", tree)
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    try:
        _git(env, "commit", "-m", message or f"publish: update web research portal {now} CST")
    except (RuntimeError, subprocess.TimeoutExpired):
        if (
            automatic and _git(env, "rev-parse", "HEAD^{tree}").strip() == current_tree
            and _git(env, "write-tree").strip() == tree
        ):
            _git(env, "read-tree", current_tree)
        raise
    if tree != _git(env, "rev-parse", "HEAD^{tree}").strip():
        raise RuntimeError("The committed tree changed during validation. The commit was not pushed.")
    return tree, output


def _push_edition(
    token: str, edition: str, repository: str, env: dict[str, str], *,
    git_dir: Path, common: Path, work: Path, output: Path, message: str | None,
) -> tuple[str, Path]:
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

    def remember(candidate: str) -> None:
        edition_run.check_publication_candidate(token, sha=candidate, repository=repository)
        _save_json(intent, {"edition": edition, "repository": repository, "sha": candidate})

    def forget(_rejected: str) -> None:
        intent.unlink(missing_ok=True)

    if expected is not None:
        head_changed = _git(env, "rev-parse", "HEAD").strip() != expected
        if head_changed and not _is_commit_on_remote_main(env, expected):
            raise RuntimeError(f"Resume the recorded publication commit {expected} before creating another commit.")
        _validate_revision(expected, output, env, edition=edition)
        edition_run.check_publication_candidate(token, sha=expected, repository=repository)
        try:
            _push_verified_commit(env, expected, already_pushed=pushed is not None or head_changed, automated=True)
            sha = expected
        except _NonFastForwardError:
            if _is_commit_on_remote_main(env, expected):
                sha = expected
            else:
                intent.unlink(missing_ok=True)
                sha = _push_main(
                    env, output, git_dir, edition=edition,
                    before_push=remember, on_push_rejected=forget,
                )
    else:
        prepared = _prepare_commit(
            env, work, output, edition=edition, message=message, automated=True, token=token,
        )
        validated_tree, validated_output = (
            prepared if isinstance(prepared, tuple) and len(prepared) == 2 else (None, output)
        )
        sha = _push_main(
            env, output, git_dir, edition=edition,
            before_push=remember, on_push_rejected=forget,
            validated_tree=validated_tree, validated_output=validated_output,
        )
    edition_run.record_push(token, sha=sha, repository=repository)
    intent.unlink(missing_ok=True)
    return sha, intent


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--message", help="Custom publication commit message.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate in temporary storage and preview Git status.")
    mode.add_argument("--check-manuscripts", action="store_true", help="Run both source manuscript lint gates without building or publishing.")
    mode.add_argument("--no-push", action="store_true", help="Validate and commit locally without remote changes.")
    mode.add_argument("--edition-token", help="Token for an active edition in the publish phase.")
    parser.add_argument(
        "--stage",
        nargs="+",
        metavar="PATH",
        help="Explicit in-scope path(s) to stage for manual publication (cannot be combined with --edition-token).",
    )
    args = parser.parse_args(argv)
    if args.edition_token and args.stage:
        parser.error("--stage cannot be combined with --edition-token.")
    if args.stage and (args.dry_run or args.check_manuscripts):
        parser.error("--stage cannot be combined with --dry-run or --check-manuscripts.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = _clean_env()
    try:
        if args.check_manuscripts:
            _check_tree_no_forbidden_files(env, "HEAD")
            with state_read_lock(REPO_ROOT):
                _check_manuscripts(REPO_ROOT, env)
            return 0

        token = args.edition_token
        with tempfile.TemporaryDirectory(prefix="gir_publish_") as tmp:
            work = Path(tmp).resolve()
            output = work / "site"
            if args.dry_run:
                with state_read_lock(REPO_ROOT):
                    _check_manuscripts(REPO_ROOT, env)
                    _build_and_lint(REPO_ROOT, output, env)
                print(_git(env, "--no-optional-locks", "status", "--short"), end="")
                print("[dry-run] Temporary web portal validated.")
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
                    repository = _remote_repository(push_urls[0])
                    origin = _remote_repository(_git(env, "remote", "get-url", "origin").strip())
                    if origin.lower() != repository.lower():
                        raise RuntimeError("The origin fetch and push repositories differ.")

                pushed_sha: str | None = None
                recovering = False
                if token is not None:
                    assert edition is not None and repository is not None
                    recovering = (
                        edition_run.push_intent_path(common, token).is_file()
                        or edition_run.publication_commit(token) is not None
                    )
                    pushed_sha, _ = _push_edition(
                        token, edition, repository, env, git_dir=git_dir, common=common, work=work,
                        output=output, message=args.message,
                    )
                else:
                    prepared = _prepare_commit(
                        env, work, output, edition=None, message=args.message,
                        automated=False, explicit_stage=args.stage,
                    )
                    validated_tree, validated_output = (
                        prepared if isinstance(prepared, tuple) and len(prepared) == 2 else (None, output)
                    )
                    if not args.no_push:
                        pushed_sha = _push_main(
                            env, output, git_dir,
                            validated_tree=validated_tree, validated_output=validated_output,
                        )

                try:
                    if recovering and SITE_DIR.exists():
                        print("[git] Preserved the existing preview during publication recovery.")
                    else:
                        _install_site(output)
                except (OSError, RuntimeError) as exc:
                    if pushed_sha is not None:
                        print(
                            f"[WARN] Remote push succeeded for commit {pushed_sha}, "
                            f"but local preview install to {SITE_DIR} failed: {exc}",
                            file=sys.stderr,
                        )
                    else:
                        raise

                if args.no_push:
                    print("[DONE] Validated the local publication snapshot.")
                else:
                    sha_note = f" ({pushed_sha[:12]})" if pushed_sha else ""
                    print(
                        f"[DONE] Verified web portal source pushed{sha_note}. "
                        "GitHub Pages deploys asynchronously through Actions."
                    )
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
