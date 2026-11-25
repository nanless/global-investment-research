#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-Interactive Site Builder, Linter, Git Publisher & Rolling Release Uploader
for the Global Investment Research monorepo.

Usage:
  python3 scripts/publish_site.py                     # Full build -> strict lint -> commit -> push -> rolling release
  python3 scripts/publish_site.py --dry-run           # Build + strict lint + status preview only
  python3 scripts/publish_site.py --no-push           # Build + strict lint + local commit only
  python3 scripts/publish_site.py --skip-release      # Build + strict lint + commit + push (skip PDF/DOCX release)
  python3 scripts/publish_site.py --force-release     # Force re-upload all rolling Release PDF/DOCX assets
  python3 scripts/publish_site.py --message "..."     # Custom commit message
"""

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_site.py"
LINT_SCRIPT = REPO_ROOT / "scripts" / "lint_site.py"
SITE_DIR = REPO_ROOT / "_site"
LOCK_PATH = REPO_ROOT / ".git" / "publish_site.lock"
MANIFEST_PATH = REPO_ROOT / ".git" / "last_release_manifest.json"

CANONICAL_STAGE_PATHS = ("gold", "equity", "scripts", "README.md", ".gitignore", ".github")

RELEASE_TAG = "latest-reports"
RELEASE_TITLE = "Latest Research Reports (PDF & Word)"
RELEASE_NOTES = (
    "Rolling latest compiled PDF and native ECMA-376 OOXML Word (.docx) editions "
    "for Gold, A-Share, HK-Stock, and US-Stock research reports.\n\n"
    "Updated automatically by `scripts/publish_site.py`."
)

CST = timezone(timedelta(hours=8))

_GOLD_DAILY_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})_(\d{4})_.*黄金深度研报(?:_r(\d+))?\.(pdf|docx)$"
)


@contextlib.contextmanager
def _publish_lock() -> Iterator[None]:
    """Serialize overlapping publish_site.py runs via an exclusive advisory lock inside .git/."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_fp = LOCK_PATH.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"[lock] Waiting for active publish_site.py lock ({LOCK_PATH})...")
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
        finally:
            lock_fp.close()


def _clean_env() -> dict[str, str]:
    """Return a clean non-interactive environment without stale GitHub tokens."""
    env = os.environ.copy()
    # Strip any stale tokens so git relies on SSH remote and gh uses its
    # configured keyring credentials rather than an expired environment token.
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GH_PROMPT_DISABLED"] = "1"
    env["GIT_SSH_COMMAND"] = (
        "ssh -o BatchMode=yes -o ConnectTimeout=20 "
        "-o ServerAliveInterval=15 -o ServerAliveCountMax=3"
    )

    preferred_bins = [
        extra
        for extra in ("/Users/francis7999/miniforge3/bin", "/opt/homebrew/bin", "/usr/local/bin")
        if os.path.isdir(extra)
    ]
    existing_parts = [p for p in env.get("PATH", "").split(os.pathsep) if p and p not in preferred_bins]
    env["PATH"] = os.pathsep.join(preferred_bins + existing_parts)
    return env


def _run(
    cmd: list[str],
    *,
    env: dict[str, str],
    check: bool = True,
    capture: bool = False,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        check=check,
        text=True,
        capture_output=capture,
        timeout=timeout,
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_release_manifest() -> dict[str, str]:
    if not MANIFEST_PATH.is_file():
        return {}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _save_release_manifest(manifest: dict[str, str]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MANIFEST_PATH.with_name(MANIFEST_PATH.name + ".tmp")
    try:
        tmp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, MANIFEST_PATH)
    finally:
        tmp_path.unlink(missing_ok=True)


def _find_latest_gold_daily(ext: str) -> Path | None:
    daily_dir = REPO_ROOT / "gold" / "daily"
    if not daily_dir.is_dir():
        return None
    matches: list[tuple[tuple[str, int, int, str], Path]] = []
    for p in daily_dir.iterdir():
        if not p.is_file():
            continue
        m = _GOLD_DAILY_RE.match(p.name)
        if m and m.group(4).lower() == ext:
            key = (m.group(1), int(m.group(2)), int(m.group(3) or 1), p.name)
            matches.append((key, p))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[-1][1]


def _find_latest_equity_daily(market: str, ext: str) -> Path | None:
    daily_dir = REPO_ROOT / "equity" / "daily"
    if not daily_dir.is_dir():
        return None
    pat = re.compile(
        rf"^(\d{{4}}-\d{{2}}-\d{{2}})_(\d{{4}})_{re.escape(market)}(?:_r(\d+))?\.{re.escape(ext)}$"
    )
    matches: list[tuple[tuple[str, int, int, str], Path]] = []
    for p in daily_dir.iterdir():
        if not p.is_file():
            continue
        m = pat.match(p.name)
        if m:
            key = (m.group(1), int(m.group(2)), int(m.group(3) or 1), p.name)
            matches.append((key, p))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[-1][1]


def discover_release_assets() -> list[tuple[Path, str, str]]:
    """Discover up to 16 latest compiled PDF/DOCX assets with stable ASCII names."""
    candidates: list[tuple[Path | None, str, str]] = [
        (
            REPO_ROOT / "gold" / "黄金跨世纪周期与2026-2030终审研究报告.pdf",
            "gold-master-latest.pdf",
            "黄金跨世纪周期全景主报告 (PDF)",
        ),
        (
            REPO_ROOT / "gold" / "黄金跨世纪周期与2026-2030终审研究报告.docx",
            "gold-master-latest.docx",
            "黄金跨世纪周期全景主报告 (Word)",
        ),
        (
            _find_latest_gold_daily("pdf"),
            "gold-daily-latest.pdf",
            "黄金每日深度研报最新刊 (PDF)",
        ),
        (
            _find_latest_gold_daily("docx"),
            "gold-daily-latest.docx",
            "黄金每日深度研报最新刊 (Word)",
        ),
    ]

    equity_specs = [
        ("a_share", "a-share", "A股"),
        ("hk_stock", "hk-stock", "港股"),
        ("us_stock", "us-stock", "美股"),
    ]
    for market, slug, cn_name in equity_specs:
        candidates.extend(
            [
                (
                    REPO_ROOT / "equity" / f"{market}_market_report_latest.pdf",
                    f"{slug}-flagship-latest.pdf",
                    f"{cn_name}跨周期全景手册 (PDF)",
                ),
                (
                    REPO_ROOT / "equity" / f"{market}_market_report_latest.docx",
                    f"{slug}-flagship-latest.docx",
                    f"{cn_name}跨周期全景手册 (Word)",
                ),
                (
                    _find_latest_equity_daily(market, "pdf"),
                    f"{slug}-daily-latest.pdf",
                    f"{cn_name}每日深度研报最新刊 (PDF)",
                ),
                (
                    _find_latest_equity_daily(market, "docx"),
                    f"{slug}-daily-latest.docx",
                    f"{cn_name}每日深度研报最新刊 (Word)",
                ),
            ]
        )

    found: list[tuple[Path, str, str]] = []
    for src, ascii_name, label in candidates:
        if src is not None and src.is_file() and src.stat().st_size > 0:
            found.append((src, ascii_name, label))
    return found


def _verify_main_branch(env: dict[str, str]) -> str:
    """Return current branch name or raise RuntimeError if detached/non-main."""
    res = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], env=env, check=False, capture=True)
    if res.returncode != 0:
        detail = (res.stderr or res.stdout).strip()
        raise RuntimeError(f"Unable to determine current git branch: {detail}")
    branch = res.stdout.strip()
    if branch != "main":
        raise RuntimeError(
            f"Refusing to commit/push from branch {branch!r}; expected 'main' (detached or wrong branch)."
        )
    return branch


def _has_origin_remote(env: dict[str, str]) -> str | None:
    res = _run(["git", "remote", "get-url", "origin"], env=env, check=False, capture=True)
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    return None


def _remote_has_main(env: dict[str, str]) -> bool:
    res = _run(
        ["git", "ls-remote", "--heads", "origin", "main"],
        env=env,
        check=False,
        capture=True,
        timeout=30,
    )
    return res.returncode == 0 and bool(res.stdout.strip())


def _abort_rebase_if_active(env: dict[str, str]) -> None:
    git_dir = REPO_ROOT / ".git"
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        _run(["git", "rebase", "--abort"], env=env, check=False, capture=True)


def _push_main_with_retry(env: dict[str, str]) -> None:
    for attempt in (1, 2):
        if _remote_has_main(env):
            print(f"[git] Pulling latest origin/main with rebase (attempt {attempt}/2)...")
            pull_res = _run(
                ["git", "pull", "--rebase", "--autostash", "origin", "main"],
                env=env,
                check=False,
                capture=True,
                timeout=90,
            )
            if pull_res.returncode != 0:
                _abort_rebase_if_active(env)
                msg = (pull_res.stderr or pull_res.stdout).strip()
                if attempt == 1:
                    print(f"[git] Rebase pull failed ({msg}); retrying in 3s...", file=sys.stderr)
                    time.sleep(3)
                    continue
                raise RuntimeError(f"git pull --rebase failed after retry: {msg}")
        else:
            print("[git] Remote origin/main not found yet; performing initial push...")

        print(f"[git] Pushing main to origin (attempt {attempt}/2)...")
        push_res = _run(
            ["git", "push", "-u", "origin", "main"],
            env=env,
            check=False,
            capture=True,
            timeout=120,
        )
        if push_res.returncode == 0:
            if push_res.stdout.strip():
                print(push_res.stdout.strip())
            if push_res.stderr.strip():
                print(push_res.stderr.strip())
            print("[git] Push to origin/main succeeded.")
            return

        err_msg = (push_res.stderr or push_res.stdout).strip()
        if attempt == 1:
            print(f"[git] Push failed ({err_msg}); retrying pull-rebase + push in 3s...", file=sys.stderr)
            time.sleep(3)
            continue
        raise RuntimeError(f"git push origin main failed after retry: {err_msg}")


def _upload_rolling_release(env: dict[str, str], *, force_release: bool = False) -> None:
    """Non-fatal rolling upload of changed PDF/DOCX reports to GitHub Release `latest-reports`."""
    gh_bin = shutil.which("gh", path=env.get("PATH"))
    if not gh_bin:
        print("[WARN] `gh` CLI not found in PATH; skipping rolling Release upload.", file=sys.stderr)
        return

    assets = discover_release_assets()
    if not assets:
        print("[WARN] No compiled PDF/DOCX assets found locally; skipping Release upload.", file=sys.stderr)
        return

    try:
        release_created = False
        view_res = _run(
            [gh_bin, "release", "view", RELEASE_TAG],
            env=env,
            check=False,
            capture=True,
            timeout=30,
        )
        if view_res.returncode != 0:
            print(f"[release] Release `{RELEASE_TAG}` not found; creating...")
            create_res = _run(
                [
                    gh_bin,
                    "release",
                    "create",
                    RELEASE_TAG,
                    "--target",
                    "main",
                    "--title",
                    RELEASE_TITLE,
                    "--notes",
                    RELEASE_NOTES,
                ],
                env=env,
                check=False,
                capture=True,
                timeout=60,
            )
            if create_res.returncode != 0:
                detail = (create_res.stderr or create_res.stdout).strip()
                print(
                    f"[WARN] Could not create Release `{RELEASE_TAG}` (non-fatal): {detail}",
                    file=sys.stderr,
                )
                return
            release_created = True

        prev_manifest = {} if (force_release or release_created) else _load_release_manifest()
        current_hashes: dict[str, str] = {}
        changed_assets: list[tuple[Path, str, str]] = []
        for src, ascii_name, label in assets:
            digest = _sha256_file(src)
            current_hashes[ascii_name] = digest
            if prev_manifest.get(ascii_name) != digest:
                changed_assets.append((src, ascii_name, label))

        if not changed_assets:
            print(
                f"[release] All {len(assets)} Release assets unchanged (SHA256 match); "
                f"skipping upload (pass --force-release to override)."
            )
            return

        skipped = len(assets) - len(changed_assets)
        with tempfile.TemporaryDirectory(prefix="gir_release_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            upload_specs: list[str] = []
            for src, ascii_name, label in changed_assets:
                dst = tmp_dir / ascii_name
                shutil.copy2(src, dst)
                upload_specs.append(f"{dst}#{label}")

            print(
                f"[release] Uploading {len(upload_specs)} changed PDF/DOCX asset(s) "
                f"(skipped {skipped} unchanged) to `{RELEASE_TAG}`..."
            )
            up_res = _run(
                [gh_bin, "release", "upload", RELEASE_TAG, *upload_specs, "--clobber"],
                env=env,
                check=False,
                capture=True,
                timeout=300,
            )
            if up_res.returncode != 0:
                detail = (up_res.stderr or up_res.stdout).strip()
                print(
                    f"[WARN] Release asset upload failed (non-fatal): {detail}",
                    file=sys.stderr,
                )
                return

        merged_manifest = dict(prev_manifest)
        merged_manifest.update(current_hashes)
        _save_release_manifest(merged_manifest)
        print(
            f"[release] Successfully uploaded {len(changed_assets)} changed asset(s) "
            f"to Release `{RELEASE_TAG}` ({skipped} unchanged skipped)."
        )
    except Exception as exc:
        print(f"[WARN] Rolling Release upload encountered an error (non-fatal): {exc}", file=sys.stderr)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build, strictly lint, commit, push, and optionally publish rolling PDF/DOCX releases."
    )
    parser.add_argument(
        "-m",
        "--message",
        default=None,
        help="Optional custom git commit message.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build + strict lint + print git status and release asset plan without committing or pushing.",
    )
    parser.add_argument(
        "--skip-release",
        action="store_true",
        help="Skip uploading compiled PDF/DOCX files to GitHub Release `latest-reports`.",
    )
    parser.add_argument(
        "--force-release",
        action="store_true",
        help="Force re-upload all discovered PDF/DOCX Release assets regardless of SHA256 cache.",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Build + strict lint + local git commit only (skip push and release upload).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = _clean_env()

    if not BUILD_SCRIPT.is_file():
        print(f"[FAIL] Missing site builder: {BUILD_SCRIPT}", file=sys.stderr)
        return 1
    if not LINT_SCRIPT.is_file():
        print(f"[FAIL] Missing site linter: {LINT_SCRIPT}", file=sys.stderr)
        return 1

    with _publish_lock():
        # 1. Build static site
        print(f"[1/4] Building static site -> {SITE_DIR}")
        build_res = _run(
            [sys.executable, str(BUILD_SCRIPT), "--out", str(SITE_DIR)],
            env=env,
            check=False,
        )
        if build_res.returncode != 0:
            print(f"[FAIL] build_site.py failed with exit code {build_res.returncode}", file=sys.stderr)
            return build_res.returncode

        # 2. Strict lint generated site
        print(f"[2/4] Running strict site linter -> {SITE_DIR}")
        lint_res = _run(
            [sys.executable, str(LINT_SCRIPT), str(SITE_DIR), "--strict"],
            env=env,
            check=False,
        )
        if lint_res.returncode != 0:
            print(f"[FAIL] lint_site.py --strict failed with exit code {lint_res.returncode}", file=sys.stderr)
            return lint_res.returncode

        # 3. Dry-run preview
        if args.dry_run:
            status_res = _run(["git", "status", "--short"], env=env, check=False, capture=True)
            print("\n=== [DRY-RUN] Git Status ===")
            print(status_res.stdout.strip() or "(working tree clean)")
            assets = discover_release_assets()
            prev_manifest = {} if args.force_release else _load_release_manifest()
            print(f"\n=== [DRY-RUN] Discovered Release Assets ({len(assets)}) ===")
            for src, ascii_name, label in assets:
                rel = src.relative_to(REPO_ROOT)
                state = "UPLOAD" if prev_manifest.get(ascii_name) != _sha256_file(src) else "SKIP-UNCHANGED"
                print(f"  - [{state}] {ascii_name}  <-  {rel}  [{label}]")
            print("\n[DRY-RUN] Build & strict lint passed. No commit, push, or release upload performed.")
            return 0

        # 4. Verify branch is strictly `main` before committing or pushing
        try:
            _verify_main_branch(env)
        except Exception as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1

        # 5. Explicitly scoped Git staging & commit
        stage_paths = [p for p in CANONICAL_STAGE_PATHS if (REPO_ROOT / p).exists()]
        if not stage_paths:
            print("[FAIL] No canonical repository paths found to stage.", file=sys.stderr)
            return 1

        print(f"[3/4] Staging canonical paths ({', '.join(stage_paths)}) and committing updates...")
        add_res = _run(["git", "add", "--", *stage_paths], env=env, check=False, capture=True)
        if add_res.returncode != 0:
            detail = (add_res.stderr or add_res.stdout).strip()
            print(f"[FAIL] git add failed: {detail}", file=sys.stderr)
            return 1

        diff_cached = _run(["git", "diff", "--cached", "--quiet"], env=env, check=False)
        if diff_cached.returncode != 0:
            now_cst = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
            commit_msg = args.message or f"publish: update research reports {now_cst} CST"
            try:
                commit_res = _run(
                    ["git", "commit", "-m", commit_msg],
                    env=env,
                    check=False,
                    capture=True,
                )
                if commit_res.returncode != 0:
                    detail = (commit_res.stderr or commit_res.stdout).strip()
                    print(f"[FAIL] git commit failed: {detail}", file=sys.stderr)
                    return 1
                if commit_res.stdout.strip():
                    print(commit_res.stdout.strip())
            except Exception as exc:
                print(f"[FAIL] git commit encountered an unexpected error: {exc}", file=sys.stderr)
                return 1
        else:
            print("[git] No staged changes to commit.")

        if args.no_push:
            print("[4/4] --no-push set; skipping remote push and Release upload.")
            return 0

        remote_url = _has_origin_remote(env)
        if not remote_url:
            print("[4/4] No git remote `origin` configured; skipping push and Release upload.")
            return 0

        # 6. Pull-rebase & push with retry
        print(f"[4/4] Syncing with origin ({remote_url})...")
        has_head = _run(["git", "rev-parse", "--verify", "HEAD"], env=env, check=False, capture=True)
        if has_head.returncode != 0:
            print("[WARN] Repository has no commits yet; nothing to push.", file=sys.stderr)
            return 0

        try:
            _push_main_with_retry(env)
        except Exception as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1

        # 7. Optional non-fatal rolling Release PDF/DOCX upload (SHA256 deduplicated)
        if args.skip_release:
            print("[release] --skip-release set; skipping Release asset upload.")
        else:
            _upload_rolling_release(env, force_release=args.force_release)

        print("[DONE] Publish pipeline completed successfully.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
