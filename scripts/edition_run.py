#!/usr/bin/env python3
"""Serialize unified editions across Antigravity sessions and record their outcome."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4


ROOT = Path(__file__).resolve().parent.parent
EDITION_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(0730|1800)(?:_r([2-9]|[1-9]\d+))?")
PHASES = ("research", "gold", "equity", "publish")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def edition_id(value: str) -> str:
    match = EDITION_RE.fullmatch(value)
    if match is None:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD_0730 or YYYY-MM-DD_1800, optionally followed by _rN")
    try:
        datetime.strptime(match[1], "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, timeout=15).strip()


def open_runs() -> sqlite3.Connection:
    git_dir = Path(git_value("rev-parse", "--path-format=absolute", "--git-common-dir"))
    runs = sqlite3.connect(git_dir / "edition-runs.sqlite3", timeout=10)
    runs.row_factory = sqlite3.Row
    runs.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            token TEXT PRIMARY KEY, edition TEXT NOT NULL, phase TEXT NOT NULL,
            status TEXT NOT NULL, started TEXT NOT NULL, updated TEXT NOT NULL,
            outcome TEXT NOT NULL DEFAULT ''
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_running_edition ON runs(status) WHERE status = 'running';
        CREATE UNIQUE INDEX IF NOT EXISTS one_completed_edition ON runs(edition) WHERE status = 'complete';
    """)
    return runs


def active_run(runs: sqlite3.Connection, token: str) -> sqlite3.Row:
    row = runs.execute("SELECT * FROM runs WHERE token = ? AND status = 'running'", (token,)).fetchone()
    if row is None:
        raise ValueError("This run token does not hold the current edition lock.")
    return row


def begin(runs: sqlite3.Connection, edition: str) -> str:
    runs.execute("BEGIN IMMEDIATE")
    active = runs.execute("SELECT edition, phase FROM runs WHERE status = 'running'").fetchone()
    if active is not None:
        raise ValueError(f"{active['edition']} is still running ({active['phase']}).")
    existing = runs.execute("SELECT 1 FROM runs WHERE edition = ? AND status = 'complete'", (edition,)).fetchone()
    if existing is not None:
        raise ValueError(f"Edition {edition} is already complete. Use a revision number for new content.")
    token = uuid4().hex
    now = utc_now()
    runs.execute(
        "INSERT INTO runs(token, edition, phase, status, started, updated) VALUES (?, ?, ?, 'running', ?, ?)",
        (token, edition, PHASES[0], now, now),
    )
    return token


def advance(runs: sqlite3.Connection, token: str, phase: str) -> str:
    runs.execute("BEGIN IMMEDIATE")
    row = active_run(runs, token)
    previous = PHASES.index(row["phase"])
    if PHASES.index(phase) != previous + 1:
        raise ValueError(f"Cannot advance from {row['phase']} to {phase}.")
    runs.execute("UPDATE runs SET phase = ?, updated = ? WHERE token = ?", (phase, utc_now(), token))
    return phase


def verify_pages(sha: str) -> str:
    """Find a deployment for this commit, preserving the lock during the wait."""
    gh = shutil.which("gh") or next(
        (str(p) for p in (Path("/opt/homebrew/bin/gh"), Path("/usr/local/bin/gh")) if p.is_file()), None,
    )
    if gh is None:
        raise ValueError("GitHub CLI is required to verify Pages deployment.")
    deadline = time.monotonic() + 180
    while True:
        output = subprocess.check_output(
            [gh, "run", "list", "--workflow", "deploy-pages.yml", "--commit", sha,
             "--json", "status,conclusion,url", "--limit", "5"], cwd=ROOT, text=True, timeout=30,
        )
        jobs = json.loads(output)
        success = next((job["url"] for job in jobs if job["conclusion"] == "success"), None)
        if success:
            return success
        if jobs and all(job["status"] == "completed" for job in jobs):
            raise ValueError(f"Pages deployment did not succeed for {sha}: {jobs[0]['url']}")
        if time.monotonic() >= deadline:
            raise ValueError(f"Pages deployment is still unverified for {sha}; rerun complete to check again.")
        time.sleep(5)


def complete(runs: sqlite3.Connection, token: str) -> str:
    row = active_run(runs, token)
    if row["phase"] != "publish":
        raise ValueError("Only an edition in its publish phase can be completed.")
    sha = git_value("rev-parse", "HEAD")
    url = verify_pages(sha)
    runs.execute("BEGIN IMMEDIATE")
    active_run(runs, token)
    runs.execute(
        "UPDATE runs SET status = 'complete', updated = ?, outcome = ? WHERE token = ?",
        (utc_now(), f"{sha} {url}", token),
    )
    return url


def fail(runs: sqlite3.Connection, identity: str, reason: str, *, recover: bool = False) -> str:
    runs.execute("BEGIN IMMEDIATE")
    if recover:
        row = runs.execute("SELECT * FROM runs WHERE edition = ? AND status = 'running'", (identity,)).fetchone()
        if row is None:
            raise ValueError(f"Edition {identity} has no running lock to recover.")
    else:
        row = active_run(runs, identity)
    runs.execute(
        "UPDATE runs SET status = 'failed', updated = ?, outcome = ? WHERE token = ?",
        (utc_now(), reason[:500], row["token"]),
    )
    return row["edition"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("begin").add_argument("edition", type=edition_id)
    advance_cmd = commands.add_parser("advance")
    advance_cmd.add_argument("token")
    advance_cmd.add_argument("phase", choices=PHASES[1:])
    commands.add_parser("complete").add_argument("token")
    fail_cmd = commands.add_parser("fail")
    fail_cmd.add_argument("token")
    fail_cmd.add_argument("reason")
    commands.add_parser("status")
    recover_cmd = commands.add_parser("recover", help="release a crashed run after confirming its session has ended")
    recover_cmd.add_argument("edition", type=edition_id)
    recover_cmd.add_argument("reason")
    args = parser.parse_args()

    try:
        with open_runs() as runs:
            if args.command == "begin":
                print(begin(runs, args.edition))
            elif args.command == "advance":
                print(advance(runs, args.token, args.phase))
            elif args.command == "complete":
                print(complete(runs, args.token))
            elif args.command == "fail":
                print(fail(runs, args.token, args.reason))
            elif args.command == "recover":
                print(fail(runs, args.edition, args.reason, recover=True))
            else:
                rows = runs.execute(
                    "SELECT edition, phase, status, started, updated, outcome FROM runs ORDER BY rowid DESC LIMIT 10",
                )
                print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
    except (ValueError, sqlite3.Error, subprocess.SubprocessError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
