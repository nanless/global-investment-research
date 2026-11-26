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
    from . import edition_run
else:
    import edition_run

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "_site"
CANONICAL_STAGE_PATHS = (
    "AGENTS.md", ".agents", "automations", "gold", "equity",
    "scripts", "tests", "README.md", ".gitignore", ".github",
)
GOLD_MASTER = "黄金跨世纪周期与2026-2030终审研究报告"
CST = timezone(timedelta(hours=8))
GOLD_DAILY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_.*黄金深度研报(?:_r(\d+))?\.md$")
_T = TypeVar("_T")
_TRANSIENT_NET_RE = re.compile(
    r"HTTP 50[0234]|timeout|timed out|connection reset|TLS|EOF|Could not resolve",
    re.IGNORECASE,
)


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


def _is_transient_error(exc: BaseException) -> bool:
    return isinstance(exc, subprocess.TimeoutExpired) or (
        isinstance(exc, RuntimeError) and bool(_TRANSIENT_NET_RE.search(str(exc)))
    )


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


def _git_dir(env: dict[str, str], *, common: bool = False) -> Path:
    args = ("--path-format=absolute", "--git-common-dir") if common else ("--absolute-git-dir",)
    return Path(_git(env, "rev-parse", *args).strip())


def _remote_repository(url: str) -> str:
    pattern = r"(?:(?:https://|ssh://(?:git@)?|git@)github\.com[/:])([\w.-]+/[\w.-]+?)(?:\.git)?/?"
    match = re.fullmatch(pattern, url, flags=re.ASCII)
    if not match:
        raise RuntimeError("Publication requires an origin URL that identifies a github.com repository.")
    return match[1]


def _validate_revision(
    revision: str, output: Path, env: dict[str, str], *, edition: str | None = None,
) -> None:
    with _checkout_revision(revision, env) as source:
        _check_manuscripts(source, env, edition)
        _build_and_lint(source, output, env)


def _remote_main(env: dict[str, str]) -> str | None:
    def _fetch() -> str | None:
        result = _run(["git", "ls-remote", "--heads", "origin", "refs/heads/main"], env, timeout=30)
        head = _checked(result, "git ls-remote").strip()
        return head.split()[0] if head else None

    return _retry_transient(_fetch, label="git ls-remote origin/main")


def _require_remote_main(env: dict[str, str], sha: str) -> None:
    if _remote_main(env) != sha:
        raise RuntimeError(f"Remote main no longer points to publication commit {sha}; preserve the newer version.")


def _push_verified_commit(env: dict[str, str], commit: str, *, already_pushed: bool = False) -> None:
    if already_pushed or _remote_main(env) == commit:
        _require_remote_main(env, commit)
        return
    for attempt in (1, 2):
        try:
            result = _run(["git", "push", "origin", f"{commit}:refs/heads/main"], env, timeout=120)
            _checked(result, "git push")
            break
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            if _remote_main(env) == commit:
                return  # A transport error can occur after origin accepts the ref update.
            if attempt == 2 or not _is_transient_error(exc):
                raise
            print(f"[git] Retry push of {commit[:12]} after transient error: {exc}", file=sys.stderr)
            time.sleep(3)
    _require_remote_main(env, commit)


def _push_main(
    env: dict[str, str], output: Path, git_dir: Path,
    *, edition: str | None = None, before_push: Callable[[str], None] | None = None,
) -> str:
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
        _validate_revision(commit, output, env, edition=edition)
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
        finally:
            temporary.unlink(missing_ok=True)


def _prepare_commit(
    env: dict[str, str], work: Path, output: Path, *,
    edition: str | None, message: str | None,
) -> None:
    current_tree = _git(env, "rev-parse", "HEAD^{tree}").strip()
    tree, automatic = _publication_tree(env, work / "publish-index")
    _validate_revision(tree, output, env, edition=edition)
    if tree == current_tree:
        return
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

    if expected is not None:
        if _git(env, "rev-parse", "HEAD").strip() != expected:
            raise RuntimeError(f"Resume the recorded publication commit {expected} before creating another commit.")
        _validate_revision(expected, output, env, edition=edition)
        edition_run.check_publication_candidate(token, sha=expected, repository=repository)
        _push_verified_commit(env, expected, already_pushed=pushed is not None)
        sha = expected
    else:
        _prepare_commit(env, work, output, edition=edition, message=message)

        def remember(candidate: str) -> None:
            edition_run.check_publication_candidate(token, sha=candidate, repository=repository)
            _save_json(intent, {"edition": edition, "repository": repository, "sha": candidate})

        sha = _push_main(env, output, git_dir, edition=edition, before_push=remember)
    edition_run.record_push(token, sha=sha, repository=repository)
    intent.unlink(missing_ok=True)
    return sha, intent


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-m", "--message", help="Custom publication commit message.")
    parser.add_argument("--dry-run", action="store_true", help="Validate in temporary storage and preview Git status.")
    parser.add_argument("--check-manuscripts", action="store_true", help="Run both source manuscript lint gates without building or publishing.")
    parser.add_argument("--no-push", action="store_true", help="Validate and commit locally without remote changes.")
    parser.add_argument("--edition-token", help="Token for an active edition in the publish phase.")
    args = parser.parse_args(argv)
    if args.edition_token and (args.dry_run or args.check_manuscripts or args.no_push):
        parser.error("Edition tokens require full publication.")
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
            if args.dry_run:
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

                if token is not None:
                    assert edition is not None and repository is not None
                    _push_edition(
                        token, edition, repository, env, git_dir=git_dir, common=common, work=work,
                        output=output, message=args.message,
                    )
                else:
                    _prepare_commit(env, work, output, edition=None, message=args.message)
                    if not args.no_push:
                        _push_main(env, output, git_dir)

                _install_site(output)
                if args.no_push:
                    print("[DONE] Validated the local publication snapshot.")
                else:
                    print("[DONE] Verified web portal source pushed. GitHub Pages deploys asynchronously through Actions.")
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
