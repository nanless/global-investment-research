#!/usr/bin/env python3
"""Serialize editions and complete them against their own publication receipts."""

from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
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
BEIJING = timezone(timedelta(hours=8))
EDITION_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(0730|1800)(?:_r([2-9]|[1-9]\d+))?")
PHASES = ("research", "gold", "equity", "publish")
GOLD_HISTORY_LEDGERS = ("gold/daily/AUDIT_LOG.md", "gold/daily/CHANGELOG.md")
SHA_RE = re.compile(r"[a-f0-9]{40}")
DIGEST_RE = re.compile(r"[a-f0-9]{64}")
REPOSITORY_RE = re.compile(r"[\w.-]+/[\w.-]+", re.ASCII)
EXPECTED_ASSETS = frozenset(
    f"{stem}-latest.{extension}"
    for stem in ("gold-master", "gold-daily", "a-share-flagship", "a-share-daily",
                 "hk-stock-flagship", "hk-stock-daily", "us-stock-flagship", "us-stock-daily")
    for extension in ("pdf", "docx")
)
DEPLOY_JOB = "Deploy to GitHub Pages"


class DeploymentPending(ValueError):
    """The push is recorded, but Pages has not reported a deployment yet."""


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


def git_directory() -> Path:
    return Path(git_value("rev-parse", "--path-format=absolute", "--git-common-dir"))


def push_intent_path(git_dir: Path, token: str) -> Path:
    return git_dir / f"edition-push-{token}.json"


@contextmanager
def _idle_publish_lock():
    with (git_directory() / "publish_site.lock").open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("The publisher is active in this checkout. Retry after it exits.") from exc
        yield


def open_runs() -> sqlite3.Connection:
    runs = sqlite3.connect(git_directory() / "edition-runs.sqlite3", timeout=10)
    runs.row_factory = sqlite3.Row
    runs.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            token TEXT PRIMARY KEY, edition TEXT NOT NULL, phase TEXT NOT NULL,
            status TEXT NOT NULL, started TEXT NOT NULL, updated TEXT NOT NULL,
            outcome TEXT NOT NULL DEFAULT ''
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_running_edition ON runs(status) WHERE status = 'running';
        CREATE UNIQUE INDEX IF NOT EXISTS one_completed_edition ON runs(edition) WHERE status = 'complete';
        CREATE TABLE IF NOT EXISTS attempts (
            token TEXT PRIMARY KEY REFERENCES runs(token),
            source TEXT NOT NULL, base_sha TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS publications (
            token TEXT PRIMARY KEY REFERENCES runs(token),
            sha TEXT NOT NULL, repository TEXT NOT NULL, assets_json TEXT
        );
    """)
    return runs


def active_run(runs: sqlite3.Connection, token: str) -> sqlite3.Row:
    row = runs.execute("SELECT * FROM runs WHERE token = ? AND status = 'running'", (token,)).fetchone()
    if row is None:
        raise ValueError("This run token does not hold the current edition lock.")
    return row


def _publication(runs: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return runs.execute("SELECT * FROM publications WHERE token = ?", (token,)).fetchone()


def scheduled_edition(slot: str) -> str:
    now = datetime.now(BEIJING)
    hhmm = now.strftime("%H%M")
    end = {"0730": "1130", "1800": "2200"}[slot]
    if not slot <= hhmm < end:
        raise ValueError(f"Outside the Beijing run window for {slot}. Use a manual edition for recovery.")
    return f"{now.date().isoformat()}_{slot}"


def begin(runs: sqlite3.Connection, edition: str, source: str = "manual") -> str:
    with _idle_publish_lock(), runs:
        return _begin(runs, edition, source)


def _begin(runs: sqlite3.Connection, edition: str, source: str) -> str:
    base_sha = git_value("rev-parse", "HEAD")
    runs.execute("BEGIN IMMEDIATE")
    active = runs.execute("SELECT edition, phase, token, updated FROM runs WHERE status = 'running'").fetchone()
    if active is not None:
        receipt = _publication(runs, active["token"])
        push_started = receipt is not None or push_intent_path(git_directory(), active["token"]).exists()
        next_step = (
            "resume the recorded publication or check its deployment"
            if push_started
            else "check the named session before recovering the exact attempt"
        )
        raise ValueError(
            f"{active['edition']} is still running ({active['phase']}, attempt {active['token'][:12]}, "
            f"last update {active['updated']}); {next_step}."
        )
    if runs.execute("SELECT 1 FROM runs WHERE edition = ? AND status = 'complete'", (edition,)).fetchone():
        raise ValueError(f"Edition {edition} is already complete. Use a revision number for new content.")
    token = uuid4().hex
    now = utc_now()
    runs.execute(
        "INSERT INTO runs(token, edition, phase, status, started, updated) VALUES (?, ?, ?, 'running', ?, ?)",
        (token, edition, PHASES[0], now, now),
    )
    runs.execute("INSERT INTO attempts VALUES (?, ?, ?)", (token, source, base_sha))
    return token


def _check_edition_document(edition: str, file: str, sha: str | None = None) -> None:
    contents = git_value("show", f"{sha}:{file}") if sha else (ROOT / file).read_text(encoding="utf-8")
    document = json.loads(contents)
    if not isinstance(document, dict) or document.get("edition_id") != edition:
        raise ValueError(f"{file} does not belong to edition {edition}.")


def check_edition_reviews(edition: str, *, root: Path = ROOT, sha: str | None = None) -> None:
    current = EDITION_RE.fullmatch(edition)
    if current and (current[1], current[2], int(current[3] or 1)) <= ("2026-11-25", "1800", 2):
        return
    for file in ("gold/daily/rsi_metrics.json", "equity/state/rsi_metrics.json"):
        text = git_value("show", f"{sha}:{file}") if sha else (root / file).read_text(encoding="utf-8")
        document = json.loads(text)
        reviews = document.get("runs") if isinstance(document, dict) else None
        if not isinstance(reviews, list) or sum(
            isinstance(review, dict) and review.get("run_id") == edition for review in reviews
        ) != 1:
            raise ValueError(f"{file} requires one completed independent review for {edition}.")


def advance(runs: sqlite3.Connection, token: str, phase: str) -> str:
    runs.execute("BEGIN IMMEDIATE")
    row = active_run(runs, token)
    if PHASES.index(phase) != PHASES.index(row["phase"]) + 1:
        raise ValueError(f"Cannot advance from {row['phase']} to {phase}.")
    if phase in ("equity", "publish"):
        _check_edition_document(row["edition"], "gold/data_snapshot.json")
    if phase == "publish":
        _check_edition_document(row["edition"], "equity/state/market_state.json")
        check_edition_reviews(row["edition"], root=ROOT)
    runs.execute("UPDATE runs SET phase = ?, updated = ? WHERE token = ?", (phase, utc_now(), token))
    return phase


def _publishing_run(runs: sqlite3.Connection, token: str) -> sqlite3.Row:
    row = active_run(runs, token)
    if row["phase"] != "publish":
        raise ValueError("Only an edition in its publish phase can publish or complete.")
    return row


def publication_context(token: str) -> str:
    with closing(open_runs()) as runs, runs:
        return _publishing_run(runs, token)["edition"]


def assert_manual_publish_allowed() -> None:
    with closing(open_runs()) as runs, runs:
        row = runs.execute("SELECT edition FROM runs WHERE status = 'running'").fetchone()
        if row:
            raise ValueError(f"{row['edition']} owns publication. Use its edition token.")


def publication_commit(token: str) -> str | None:
    with closing(open_runs()) as runs, runs:
        _publishing_run(runs, token)
        receipt = _publication(runs, token)
        return receipt["sha"] if receipt else None


def _ledger_lines(sha: str, path: str) -> list[bytes]:
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{sha}:{path}"], cwd=ROOT, capture_output=True, timeout=15,
    )
    if result.returncode:
        raise ValueError(f"Cannot verify the Gold ledger {path} in commit {sha}.")
    return [line for line in result.stdout.split(b"\n") if line.strip()]


def _check_gold_ledger_history(base: str, candidate: str) -> None:
    for path in GOLD_HISTORY_LEDGERS:
        # Searching the remaining iterator consumes each match and preserves the old order.
        remaining = iter(_ledger_lines(candidate, path))
        for line in _ledger_lines(base, path):
            if line not in remaining:
                raise ValueError(f"{path} must preserve every prior nonblank line in its original order.")


def _check_publication_candidate(runs: sqlite3.Connection, token: str, sha: str, repository: str) -> None:
    if not SHA_RE.fullmatch(sha) or not REPOSITORY_RE.fullmatch(repository):
        raise ValueError("Invalid publication commit or GitHub repository.")
    row = _publishing_run(runs, token)
    attempt = runs.execute("SELECT base_sha FROM attempts WHERE token = ?", (token,)).fetchone()
    if attempt is None or attempt["base_sha"] == sha:
        raise ValueError("This commit existed before the run. Start a new attempt for an unrecorded legacy run.")
    _check_edition_document(row["edition"], "gold/data_snapshot.json", sha)
    _check_edition_document(row["edition"], "equity/state/market_state.json", sha)
    check_edition_reviews(row["edition"], sha=sha)
    _check_gold_ledger_history(attempt["base_sha"], sha)
    receipt = _publication(runs, token)
    if receipt is not None and (receipt["sha"], receipt["repository"]) != (sha, repository):
        raise ValueError("A published edition cannot switch commit or repository during recovery.")


def check_publication_candidate(token: str, *, sha: str, repository: str) -> None:
    with closing(open_runs()) as runs:
        _check_publication_candidate(runs, token, sha, repository)


def record_push(token: str, *, sha: str, repository: str) -> None:
    with closing(open_runs()) as runs, runs:
        runs.execute("BEGIN IMMEDIATE")
        _check_publication_candidate(runs, token, sha, repository)
        runs.execute("INSERT OR IGNORE INTO publications (token, sha, repository) VALUES (?, ?, ?)",
                     (token, sha, repository))
        runs.execute("UPDATE runs SET updated = ? WHERE token = ?", (utc_now(), token))


def record_publication(token: str, *, sha: str, repository: str, assets: dict[str, str]) -> None:
    if assets.keys() != EXPECTED_ASSETS or any(not DIGEST_RE.fullmatch(value) for value in assets.values()):
        raise ValueError("A publication receipt requires SHA-256 for all 16 stable downloads.")
    with closing(open_runs()) as runs, runs:
        runs.execute("BEGIN IMMEDIATE")
        _publishing_run(runs, token)
        receipt = _publication(runs, token)
        if receipt is None or (receipt["sha"], receipt["repository"]) != (sha, repository):
            raise ValueError("Attachment receipt does not match this edition's recorded push.")
        encoded = json.dumps(assets, sort_keys=True)
        if receipt["assets_json"] not in (None, encoded):
            raise ValueError("Verified downloads changed for the same edition commit.")
        runs.execute("UPDATE publications SET assets_json = ? WHERE token = ?", (encoded, token))
        runs.execute("UPDATE runs SET updated = ? WHERE token = ?", (utc_now(), token))


def _gh_json(*args: str):
    gh = shutil.which("gh") or next(
        (str(p) for p in (Path("/opt/homebrew/bin/gh"), Path("/usr/local/bin/gh")) if p.is_file()), None,
    )
    if gh is None:
        raise ValueError("GitHub CLI is required to verify Pages deployment.")
    return json.loads(subprocess.check_output([gh, *args], cwd=ROOT, text=True, timeout=30))


def verify_pages(sha: str, repository: str, wait: int = 180) -> str:
    """Require the actual main-branch deploy job for the recorded push."""
    deadline = time.monotonic() + wait
    while True:
        candidates = _gh_json(
            "run", "list", "--repo", repository, "--workflow", "deploy-pages.yml", "--branch", "main",
            "--commit", sha, "--json", "databaseId,headSha,headBranch,status,conclusion,url", "--limit", "10",
        )
        runs = [run for run in candidates if run["headSha"] == sha and run["headBranch"] == "main"]
        if runs and runs[0]["status"] == "completed":
            run = runs[0]
            details = _gh_json("run", "view", str(run["databaseId"]), "--repo", repository,
                               "--json", "headSha,headBranch,jobs,url")
            if details["headSha"] == sha and details["headBranch"] == "main" and any(
                job["name"] == DEPLOY_JOB and job["conclusion"] == "success" for job in details["jobs"]
            ):
                return details["url"]
            raise ValueError(f"Pages deploy job did not succeed for {sha}: {run['url']}. Rerun the workflow, then complete.")
        if time.monotonic() >= deadline:
            raise DeploymentPending(f"Pages is still pending for {sha}; rerun complete for this attempt.")
        time.sleep(min(5, max(0, deadline - time.monotonic())))


def verify_downloads(repository: str, assets: dict[str, str]) -> None:
    release = _gh_json("api", f"repos/{repository}/releases/tags/latest-reports")
    live = {
        item["name"]: item.get("digest")
        for item in release["assets"] if item["name"] in EXPECTED_ASSETS
    }
    if live != {name: f"sha256:{digest}" for name, digest in assets.items()}:
        raise ValueError("Public downloads differ from this edition's verified receipt. Resume or review publication.")


def complete(runs: sqlite3.Connection, token: str, wait: int = 180) -> str:
    _publishing_run(runs, token)
    receipt = _publication(runs, token)
    if receipt is None or receipt["assets_json"] is None:
        raise ValueError("No verified push and attachment receipt for this edition. Finish the same publication first.")
    sha, repository = receipt["sha"], receipt["repository"]
    url = verify_pages(sha, repository, wait)
    verify_downloads(repository, json.loads(receipt["assets_json"]))
    runs.execute("BEGIN IMMEDIATE")
    _publishing_run(runs, token)
    runs.execute(
        "UPDATE runs SET status = 'complete', updated = ?, outcome = ? WHERE token = ?",
        (utc_now(), f"{sha} {url}", token),
    )
    return url


def reconcile_previous_deployment(runs: sqlite3.Connection) -> str | None:
    row = runs.execute("""
        SELECT runs.token FROM runs JOIN publications USING(token)
         WHERE runs.status = 'running' AND publications.assets_json IS NOT NULL
    """).fetchone()
    if row is None:
        return None
    return complete(runs, row["token"], wait=0)


def heartbeat(runs: sqlite3.Connection, token: str) -> str:
    runs.execute("BEGIN IMMEDIATE")
    row = active_run(runs, token)
    runs.execute("UPDATE runs SET updated = ? WHERE token = ?", (utc_now(), token))
    return row["phase"]


def _identify_attempt(runs: sqlite3.Connection, edition: str, attempt: str) -> sqlite3.Row:
    row = runs.execute("SELECT * FROM runs WHERE edition = ? AND status = 'running'", (edition,)).fetchone()
    if row is None or len(attempt) != 12 or row["token"][:12] != attempt:
        raise ValueError("That attempt is no longer active. Read status and recheck the running session.")
    return row


def fail(runs: sqlite3.Connection, identity: str, reason: str, *, attempt: str | None = None) -> str:
    with _idle_publish_lock(), runs:
        runs.execute("BEGIN IMMEDIATE")
        row = _identify_attempt(runs, identity, attempt) if attempt is not None else active_run(runs, identity)
        token = row["token"]
        if _publication(runs, token) or push_intent_path(git_directory(), token).exists():
            raise ValueError("A push has been attempted or recorded. Resume this publication to verify it first.")
        runs.execute(
            "UPDATE runs SET status = 'failed', updated = ?, outcome = ? WHERE token = ?",
            (utc_now(), reason[:500], token),
        )
        return row["edition"]


def resume(runs: sqlite3.Connection, edition: str, attempt: str) -> str:
    """Recover a publisher's token after the previous session has ended."""
    row = _identify_attempt(runs, edition, attempt)
    if row["phase"] != "publish":
        raise ValueError("Only publication can be resumed after a session ends. Recover other phases explicitly.")
    return row["token"]


def close_superseded(runs: sqlite3.Connection, edition: str, attempt: str, reason: str) -> str:
    """Let a maintainer close an interrupted publication superseded on main."""
    with _idle_publish_lock(), runs:
        row = _identify_attempt(runs, edition, attempt)
        receipt = _publication(runs, row["token"])
        if receipt is None:
            intent = push_intent_path(git_directory(), row["token"])
            if not intent.is_file():
                raise ValueError("The attempt has no push intent. Use recover after its session ends.")
            receipt = json.loads(intent.read_text(encoding="utf-8"))
            if receipt.get("edition") != edition:
                raise ValueError("The saved push intent does not identify this edition.")
        if not SHA_RE.fullmatch(receipt["sha"]) or not REPOSITORY_RE.fullmatch(receipt["repository"]):
            raise ValueError("The saved push intent contains an invalid commit or repository.")
        main_ref = _gh_json("api", f"repos/{receipt['repository']}/git/ref/heads/main")
        current = main_ref["object"]["sha"]
        if not SHA_RE.fullmatch(current) or current == receipt["sha"]:
            raise ValueError("The commit is on main. Resume this publication.")
        runs.execute("BEGIN IMMEDIATE")
        _identify_attempt(runs, edition, attempt)
        runs.execute(
            "UPDATE runs SET status = 'failed', updated = ?, outcome = ? WHERE token = ?",
            (utc_now(), f"Attempted {receipt['sha']}; main is {current}: {reason[:320]}", row["token"]),
        )
        return edition


def status(runs: sqlite3.Connection) -> list[dict]:
    rows = runs.execute("""
        SELECT runs.token, edition, phase, status, started, updated, outcome, substr(runs.token, 1, 12) AS attempt,
               coalesce(attempts.source, 'legacy') AS source, publications.sha AS pushed_commit,
               publications.assets_json IS NOT NULL AS downloads_verified
          FROM runs LEFT JOIN attempts USING(token) LEFT JOIN publications USING(token)
         ORDER BY runs.rowid DESC LIMIT 10
    """)
    git_dir = git_directory()
    results = []
    for row in rows:
        result = dict(row)
        token = result.pop("token")
        result["push_started"] = bool(result["pushed_commit"] or push_intent_path(git_dir, token).exists())
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("begin")
    edition_choice = start.add_mutually_exclusive_group(required=True)
    edition_choice.add_argument("edition", nargs="?", type=edition_id)
    edition_choice.add_argument("--scheduled", choices=("0730", "1800"))
    advance_cmd = commands.add_parser("advance")
    advance_cmd.add_argument("token")
    advance_cmd.add_argument("phase", choices=PHASES[1:])
    complete_cmd = commands.add_parser("complete")
    complete_cmd.add_argument("token")
    commands.add_parser("heartbeat").add_argument("token")
    fail_cmd = commands.add_parser("fail")
    fail_cmd.add_argument("token")
    fail_cmd.add_argument("reason")
    commands.add_parser("status")
    recover_cmd = commands.add_parser("recover", help="release a specific crashed attempt after confirming it ended")
    recover_cmd.add_argument("edition", type=edition_id)
    recover_cmd.add_argument("attempt")
    recover_cmd.add_argument("reason")
    resume_cmd = commands.add_parser("resume", help="resume publication after confirming its previous session ended")
    resume_cmd.add_argument("edition", type=edition_id)
    resume_cmd.add_argument("attempt")
    superseded_cmd = commands.add_parser("close-superseded", help="close an interrupted push after main moved")
    superseded_cmd.add_argument("edition", type=edition_id)
    superseded_cmd.add_argument("attempt")
    superseded_cmd.add_argument("reason")
    args = parser.parse_args()

    try:
        with closing(open_runs()) as runs, runs:
            if args.command == "begin":
                if args.scheduled:
                    edition = scheduled_edition(args.scheduled)
                    if reconcile_previous_deployment(runs):
                        runs.commit()
                    token = begin(runs, edition, f"antigravity-{args.scheduled}")
                    print(json.dumps({"edition_id": edition, "token": token}))
                else:
                    print(begin(runs, args.edition))
            elif args.command == "advance":
                print(advance(runs, args.token, args.phase))
            elif args.command == "complete":
                print(complete(runs, args.token))
            elif args.command == "heartbeat":
                print(heartbeat(runs, args.token))
            elif args.command == "fail":
                print(fail(runs, args.token, args.reason))
            elif args.command == "recover":
                print(fail(runs, args.edition, args.reason, attempt=args.attempt))
            elif args.command == "resume":
                print(resume(runs, args.edition, args.attempt))
            elif args.command == "close-superseded":
                print(close_superseded(runs, args.edition, args.attempt, args.reason))
            else:
                print(json.dumps(status(runs), ensure_ascii=False, indent=2))
    except DeploymentPending as exc:
        print(f"[PENDING] {exc}", file=sys.stderr)
        return 2
    except (KeyError, TypeError, ValueError, sqlite3.Error, subprocess.SubprocessError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
