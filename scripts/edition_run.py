#!/usr/bin/env python3
"""Serialize editions and complete them against their own publication receipts."""

from __future__ import annotations

import argparse
from bisect import bisect_left
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import difflib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
BEIJING = timezone(timedelta(hours=8))
EDITION_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(0730|1800)(?:_r([2-9]|[1-9]\d+))?")
PHASES = ("research", "gold", "equity", "publish")
GOLD_HISTORY_LEDGERS = ("gold/daily/AUDIT_LOG.md", "gold/daily/CHANGELOG.md")
EXTENDED_EQUITY_STATE_FILES = (
    "equity/state/multi_asset_channels.json",
    "equity/state/etf_universe.json",
    "equity/state/deep_dossiers.json",
)
LAST_EDITION_WITHOUT_REVIEW = ("2026-11-25", 1800, 2)
LAST_EDITION_WITHOUT_REVIEW_CLOSURE = ("2026-11-25", 1800, 3)
SHA_RE = re.compile(r"[a-f0-9]{40}")
REPOSITORY_RE = re.compile(r"[\w.-]+/[\w.-]+", re.ASCII)
DEPLOY_JOB = "Deploy to GitHub Pages"
_STRIPPED_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GH_REPO",
    "GIT_TERMINAL_PROMPT",
)


class DeploymentPending(ValueError):
    """The push is recorded, but Pages has not reported a deployment yet."""


def _clean_env() -> dict[str, str]:
    """Return a sanitized subprocess environment isolated from inherited Git/GitHub overrides."""
    env = os.environ.copy()
    for key in _STRIPPED_ENV_VARS:
        env.pop(key, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GH_PROMPT_DISABLED"] = "1"
    return env


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
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, env=_clean_env(), text=True, timeout=15
    ).strip()


def _git_object_exists(spec: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", spec],
        cwd=ROOT,
        env=_clean_env(),
        capture_output=True,
        timeout=15,
    )
    return result.returncode == 0


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=ROOT,
        env=_clean_env(),
        capture_output=True,
        timeout=15,
    )
    return result.returncode == 0


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
            sha TEXT NOT NULL, repository TEXT NOT NULL, assets_json TEXT,
            deployed_sha TEXT
        );
    """)
    pub_cols = {row["name"] for row in runs.execute("PRAGMA table_info(publications)").fetchall()}
    if "deployed_sha" not in pub_cols:
        runs.execute("ALTER TABLE publications ADD COLUMN deployed_sha TEXT")
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
    if slot == "0730":
        in_window = "0725" <= hhmm <= "1330"
        edition_day = now.date()
    elif slot == "1800":
        if "1755" <= hhmm <= "2359":
            in_window = True
            edition_day = now.date()
        elif hhmm == "0000":
            in_window = True
            edition_day = now.date() - timedelta(days=1)
        else:
            in_window = False
            edition_day = now.date()
    else:
        raise ValueError(f"Unknown scheduled slot: {slot!r}")
    if not in_window:
        raise ValueError(f"Outside the Beijing run window for {slot}. Use a manual edition for recovery.")
    return f"{edition_day.isoformat()}_{slot}"


def _reap_stale_unpushed_run(
    runs: sqlite3.Connection, next_edition: str, max_idle_hours: float = 2.0,
) -> str | None:
    """Internal helper assuming _idle_publish_lock() and BEGIN IMMEDIATE are already held."""
    if runs.execute(
        "SELECT 1 FROM runs WHERE edition = ? AND status = 'complete'", (next_edition,),
    ).fetchone():
        return None
    active = runs.execute(
        "SELECT token, edition, phase, updated FROM runs WHERE status = 'running'"
    ).fetchone()
    if active is None or active["edition"] == next_edition:
        return None
    active_key = _edition_key(active["edition"])
    next_key = _edition_key(next_edition)
    if active_key is None or next_key is None or active_key >= next_key:
        return None
    token = active["token"]
    push_started = (
        _publication(runs, token) is not None
        or push_intent_path(git_directory(), token).exists()
    )
    if push_started:
        return None
    try:
        raw_updated = str(active["updated"]).replace("Z", "+00:00")
        updated_dt = datetime.fromisoformat(raw_updated)
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    now_dt = datetime.fromisoformat(utc_now().replace("Z", "+00:00"))
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    if now_dt - updated_dt <= timedelta(hours=max_idle_hours):
        return None
    outcome = f"Auto-reaped stale unpushed lock (>{max_idle_hours:g}h inactive) before {next_edition}"
    runs.execute(
        "UPDATE runs SET status = 'failed', updated = ?, outcome = ? WHERE token = ? AND status = 'running'",
        (utc_now(), outcome, token),
    )
    print(
        f"[NOTICE] Auto-reaped stale unpushed run {active['edition']} "
        f"({active['phase']}, attempt {token[:12]}, last update {active['updated']}) "
        f"before {next_edition}.",
        file=sys.stderr,
    )
    return active["edition"]


def reap_stale_unpushed_run(
    runs: sqlite3.Connection, next_edition: str, max_idle_hours: float = 2.0,
) -> str | None:
    """Reap an orphaned unpushed running lock from an older edition after prolonged inactivity."""
    with _idle_publish_lock(), runs:
        runs.execute("BEGIN IMMEDIATE")
        return _reap_stale_unpushed_run(runs, next_edition, max_idle_hours=max_idle_hours)


def begin(
    runs: sqlite3.Connection,
    edition: str,
    source: str = "manual",
    *,
    reap_stale: bool = False,
    max_idle_hours: float = 2.0,
) -> str:
    with _idle_publish_lock(), runs:
        base_sha = git_value("rev-parse", "HEAD")
        runs.execute("BEGIN IMMEDIATE")
        if reap_stale:
            _reap_stale_unpushed_run(runs, edition, max_idle_hours=max_idle_hours)
        return _begin(runs, edition, source, base_sha=base_sha)


def _begin(runs: sqlite3.Connection, edition: str, source: str, *, base_sha: str | None = None) -> str:
    if base_sha is None:
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
    if sha:
        try:
            contents = git_value("show", f"{sha}:{file}")
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"{file} is missing in commit {sha} for edition {edition}.") from exc
    else:
        path = ROOT / file
        if not path.is_file():
            raise ValueError(f"{file} is missing for edition {edition}.")
        contents = path.read_text(encoding="utf-8")
    document = json.loads(contents)
    if not isinstance(document, dict) or document.get("edition_id") != edition:
        raise ValueError(f"{file} does not belong to edition {edition}.")


def _check_extended_equity_documents(
    edition: str, *, sha: str | None = None, base_sha: str | None = None
) -> None:
    """Verify multi_asset_channels, etf_universe & deep_dossiers edition_id sync whenever tracked/present."""
    for file in EXTENDED_EQUITY_STATE_FILES:
        if sha is not None:
            present = _git_object_exists(f"{sha}:{file}") or (
                base_sha is not None and _git_object_exists(f"{base_sha}:{file}")
            )
        else:
            present = (ROOT / file).exists() or _git_object_exists(f"HEAD:{file}")
        if present:
            _check_edition_document(edition, file, sha)


def _edition_key(value: object) -> tuple[str, int, int] | None:
    if not isinstance(value, str):
        return None
    try:
        edition_id(value)
    except argparse.ArgumentTypeError:
        return None
    match = EDITION_RE.fullmatch(value)
    assert match is not None
    return match[1], int(match[2]), int(match[3] or 1)


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_http_url(value: object) -> bool:
    if not isinstance(value, str) or re.search(r"\s", value):
        return False
    try:
        url = urlsplit(value)
        return url.scheme in {"http", "https"} and bool(url.hostname)
    except ValueError:
        return False


def _has_deferred_data_evidence(evidence: object, current: tuple[str, int, int]) -> bool:
    if not isinstance(evidence, dict):
        return False
    due = _edition_key(evidence.get("due_edition"))
    if due is None or due <= current or not _has_text(evidence.get("disposition")):
        return False
    return _is_http_url(evidence.get("source"))


def _has_disclosed_caveat_evidence(evidence: object, current: tuple[str, int, int]) -> bool:
    if not isinstance(evidence, dict) or not _has_text(evidence.get("disposition")):
        return False
    if "source" in evidence and evidence["source"] is not None:
        if not _is_http_url(evidence["source"]):
            return False
    if "due_edition" in evidence and evidence["due_edition"] is not None:
        due = _edition_key(evidence["due_edition"])
        if due is None or due <= current:
            return False
    return True


def _check_review_closure(review: dict, file: str, current: tuple[str, int, int]) -> None:
    closure = review.get("review_closure")
    if not isinstance(closure, dict) or closure.get("reviewer_completed") is not True:
        raise ValueError(f"{file} requires review_closure.reviewer_completed to be true.")
    findings = closure.get("findings")
    if not isinstance(findings, list):
        raise ValueError(f"{file} requires a review_closure.findings list.")
    for index, finding in enumerate(findings, start=1):
        label = f"{file} review finding {index}"
        if not isinstance(finding, dict) or not _has_text(finding.get("description")):
            raise ValueError(f"{label} requires a description.")
        status = finding.get("status")
        evidence = finding.get("evidence")
        if status == "resolved":
            if not _has_text(evidence):
                raise ValueError(f"{label} requires evidence of resolution.")
        elif status == "deferred_data":
            if not _has_deferred_data_evidence(evidence, current):
                raise ValueError(f"{label} requires a source URL, future due_edition and disposition for deferred data.")
        elif status == "disclosed_caveat":
            if not _has_disclosed_caveat_evidence(evidence, current):
                raise ValueError(
                    f"{label} requires a disposition (and valid HTTP(S) source URL / future due_edition if provided) "
                    "for disclosed_caveat."
                )
        else:
            raise ValueError(
                f"{label} must be resolved or documented as deferred_data/disclosed_caveat before publication."
            )


def check_edition_reviews(edition: str, *, root: Path = ROOT, sha: str | None = None) -> None:
    current = _edition_key(edition)
    if current is None:
        raise ValueError(f"Invalid edition ID for blind review: {edition!r}.")
    if current <= LAST_EDITION_WITHOUT_REVIEW:
        return
    for file in ("gold/daily/rsi_metrics.json", "equity/state/rsi_metrics.json"):
        text = git_value("show", f"{sha}:{file}") if sha else (root / file).read_text(encoding="utf-8")
        document = json.loads(text)
        reviews = document.get("runs") if isinstance(document, dict) else None
        matches = [
            review for review in reviews if isinstance(review, dict) and review.get("run_id") == edition
        ] if isinstance(reviews, list) else []
        if len(matches) != 1:
            raise ValueError(f"{file} requires one completed independent review for {edition}.")
        if current > LAST_EDITION_WITHOUT_REVIEW_CLOSURE:
            _check_review_closure(matches[0], file, current)


def advance(runs: sqlite3.Connection, token: str, phase: str) -> str:
    # Perform read-only state and filesystem checks before acquiring the SQLite write lock.
    row = active_run(runs, token)
    if PHASES.index(phase) != PHASES.index(row["phase"]) + 1:
        raise ValueError(f"Cannot advance from {row['phase']} to {phase}.")
    attempt = runs.execute("SELECT base_sha FROM attempts WHERE token = ?", (token,)).fetchone()
    if phase in ("equity", "publish"):
        _check_edition_document(row["edition"], "gold/data_snapshot.json")
    if phase == "equity" and attempt is not None:
        _check_gold_ledger_history(attempt["base_sha"], None)
    if phase == "publish":
        _check_edition_document(row["edition"], "equity/state/market_state.json")
        _check_extended_equity_documents(row["edition"])
        check_edition_reviews(row["edition"], root=ROOT)

    runs.execute("BEGIN IMMEDIATE")
    current = active_run(runs, token)
    if PHASES.index(phase) != PHASES.index(current["phase"]) + 1:
        raise ValueError(f"Cannot advance from {current['phase']} to {phase}.")
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


def _ledger_indexed_lines(sha: str | None, path: str) -> list[tuple[int, bytes]]:
    if sha is None:
        disk_path = ROOT / path
        if not disk_path.is_file():
            raise ValueError(f"Cannot verify the Gold ledger {path} in working tree.")
        try:
            raw = disk_path.read_bytes()
        except OSError as exc:
            raise ValueError(f"Cannot read the Gold ledger {path} in working tree: {exc}") from exc
    else:
        result = subprocess.run(
            ["git", "cat-file", "blob", f"{sha}:{path}"],
            cwd=ROOT, env=_clean_env(), capture_output=True, timeout=15,
        )
        if result.returncode:
            raise ValueError(f"Cannot verify the Gold ledger {path} in commit {sha}.")
        raw = result.stdout
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return [
        (lineno, line)
        for lineno, line in enumerate(normalized.split(b"\n"), start=1)
        if line.strip()
    ]


def _ledger_lines(sha: str | None, path: str) -> list[bytes]:
    return [line for _, line in _ledger_indexed_lines(sha, path)]


def _preserves_order(prior: list[bytes], candidate_lines: list[bytes]) -> bool:
    # Searching the remaining iterator consumes each match and preserves the old order.
    remaining = iter(candidate_lines)
    return all(line in remaining for line in prior)


def _preserves_partitioned_order(
    prior: list[bytes], first: list[bytes], second: list[bytes],
) -> bool:
    """True iff prior can be cleanly partitioned in order across subsequences of first and second."""
    first_pos: dict[bytes, list[int]] = {}
    for idx, line in enumerate(first):
        first_pos.setdefault(line, []).append(idx)
    second_pos: dict[bytes, list[int]] = {}
    for idx, line in enumerate(second):
        second_pos.setdefault(line, []).append(idx)

    # Pareto frontier of reachable (next_first_idx, next_second_idx) cursors,
    # kept sorted by ascending first cursor and strictly descending second cursor.
    frontier: list[tuple[int, int]] = [(0, 0)]
    for line in prior:
        pos1 = first_pos.get(line)
        pos2 = second_pos.get(line)
        if not pos1 and not pos2:
            return False
        candidates: list[tuple[int, int]] = []
        for i1, i2 in frontier:
            if pos1:
                k1 = bisect_left(pos1, i1)
                if k1 < len(pos1):
                    candidates.append((pos1[k1] + 1, i2))
            if pos2:
                k2 = bisect_left(pos2, i2)
                if k2 < len(pos2):
                    candidates.append((i1, pos2[k2] + 1))
        if not candidates:
            return False
        candidates.sort()
        pruned: list[tuple[int, int]] = []
        best_i2 = len(second) + 1
        for i1, i2 in candidates:
            if i2 < best_i2:
                pruned.append((i1, i2))
                best_i2 = i2
        frontier = pruned
    return True


def _archived_ledger_paths(sha: str | None, path: str) -> list[str]:
    ledger = Path(path)
    archive_dir = f"{ledger.parent.as_posix()}/archive"
    prefix = f"{ledger.stem}_"
    if sha is None:
        archive_root = ROOT / archive_dir
        if not archive_root.is_dir():
            return []
        matches = [
            entry.relative_to(ROOT).as_posix()
            for entry in archive_root.rglob("*.md")
            if entry.is_file() and entry.name.startswith(prefix)
        ]
        return sorted(matches, key=lambda entry: (Path(entry).name, entry))
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", sha, "--", archive_dir],
        cwd=ROOT, env=_clean_env(), capture_output=True, text=True, timeout=15,
    )
    if result.returncode:
        return []
    matches = [
        entry.strip()
        for entry in result.stdout.splitlines()
        if entry.strip().endswith(".md") and Path(entry.strip()).name.startswith(prefix)
    ]
    return sorted(matches, key=lambda entry: (Path(entry).name, entry))


def _format_char_diff(base_text: str, cand_text: str, *, max_hunks: int = 3, context: int = 14) -> str:
    matcher = difflib.SequenceMatcher(None, base_text, cand_text, autojunk=False)
    hunks: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        left = base_text[max(0, i1 - context) : i1]
        right = base_text[i2 : min(len(base_text), i2 + context)]
        old_seg = base_text[i1:i2]
        new_seg = cand_text[j1:j2]
        if len(old_seg) > 48:
            old_seg = old_seg[:45] + "..."
        if len(new_seg) > 48:
            new_seg = new_seg[:45] + "..."
        parts = [left]
        if old_seg:
            parts.append(f"[-{old_seg}]")
        if new_seg:
            parts.append(f"[+{new_seg}]")
        parts.append(right)
        hunks.append("".join(parts))
        if len(hunks) >= max_hunks:
            break
    return " | ".join(hunks) if hunks else base_text[:80]


def _diagnose_ledger_mismatch(
    prior_indexed: list[tuple[int, bytes]],
    candidate_indexed: list[tuple[str, int, bytes]],
    *,
    max_items: int = 5,
) -> str:
    cand_positions: dict[bytes, list[int]] = {}
    cand_decoded: list[tuple[str, int, str]] = []
    for idx, (src_lbl, cand_ln, line_bytes) in enumerate(candidate_indexed):
        cand_positions.setdefault(line_bytes, []).append(idx)
        cand_decoded.append((src_lbl, cand_ln, line_bytes.decode("utf-8", errors="replace")))

    diagnostics: list[str] = []
    pos = 0
    for base_ln, line_bytes in prior_indexed:
        positions = cand_positions.get(line_bytes)
        if positions:
            k = bisect_left(positions, pos)
            if k < len(positions):
                pos = positions[k] + 1
                continue
            first_src, first_ln, first_str = cand_decoded[positions[0]]
            preview = first_str.strip()[:80]
            diagnostics.append(
                f"  - [REORDERED] base L{base_ln} -> found earlier at {first_src}L{first_ln}: {preview!r}"
            )
        else:
            base_str = line_bytes.decode("utf-8", errors="replace")
            best_ratio = 0.0
            best_match: tuple[str, int, str] | None = None
            sm = difflib.SequenceMatcher(None, base_str, "", autojunk=False)
            for src_lbl, cand_ln, cand_str in cand_decoded:
                sm.set_seq2(cand_str)
                if sm.real_quick_ratio() < max(0.55, best_ratio):
                    continue
                if sm.quick_ratio() < max(0.55, best_ratio):
                    continue
                ratio = sm.ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = (src_lbl, cand_ln, cand_str)
            if best_match is not None and best_ratio >= 0.55:
                src_lbl, cand_ln, cand_str = best_match
                snippet = _format_char_diff(base_str, cand_str)
                diagnostics.append(
                    f"  - [MODIFIED] base L{base_ln} -> closest {src_lbl}L{cand_ln} "
                    f"(similarity {best_ratio:.1%}): {snippet}"
                )
            else:
                preview = base_str.strip()[:90]
                diagnostics.append(f"  - [MISSING] base L{base_ln}: {preview!r}")
        if len(diagnostics) >= max_items:
            break
    if not diagnostics:
        return ""
    return "\n" + "\n".join(diagnostics)


def _check_gold_ledger_history(base: str, candidate: str | None) -> None:
    for path in GOLD_HISTORY_LEDGERS:
        prior_indexed = _ledger_indexed_lines(base, path)
        active_indexed = _ledger_indexed_lines(candidate, path)
        prior = [line for _, line in prior_indexed]
        active = [line for _, line in active_indexed]
        if _preserves_order(prior, active):
            continue
        archived_paths = _archived_ledger_paths(candidate, path)
        archived_indexed: list[tuple[str, int, bytes]] = []
        if archived_paths:
            archived_by_path = [(ap, _ledger_indexed_lines(candidate, ap)) for ap in archived_paths]
            archived_chrono = [line for _, rows in archived_by_path for _, line in rows]
            archived_rev = [line for _, rows in reversed(archived_by_path) for _, line in rows]
            if (
                _preserves_order(prior, archived_chrono + active)
                or _preserves_order(prior, active + archived_rev)
                or _preserves_partitioned_order(prior, active, archived_chrono)
                or _preserves_partitioned_order(prior, active, archived_rev)
            ):
                continue
            for ap, rows in archived_by_path:
                prefix = f"{Path(ap).name}:"
                archived_indexed.extend((prefix, ln, line) for ln, line in rows)
        candidate_pool: list[tuple[str, int, bytes]] = [("", ln, line) for ln, line in active_indexed]
        candidate_pool.extend(archived_indexed)
        diag = _diagnose_ledger_mismatch(prior_indexed, candidate_pool, max_items=5)
        raise ValueError(f"{path} must preserve every prior nonblank line in its original order.{diag}")


def check_gold_ledger_history_for_token(token: str, candidate_ref: str | None = None) -> None:
    """Verify Gold ledger history against the active run's base_sha for a commit/tree ref or working tree."""
    with closing(open_runs()) as runs:
        active_run(runs, token)
        attempt = runs.execute("SELECT base_sha FROM attempts WHERE token = ?", (token,)).fetchone()
        if attempt is None:
            raise ValueError("This run has no recorded base commit for Gold ledger history verification.")
        base_sha = attempt["base_sha"]
    _check_gold_ledger_history(base_sha, candidate_ref)


def _check_publication_candidate(runs: sqlite3.Connection, token: str, sha: str, repository: str) -> None:
    if not SHA_RE.fullmatch(sha) or not REPOSITORY_RE.fullmatch(repository):
        raise ValueError("Invalid publication commit or GitHub repository.")
    row = _publishing_run(runs, token)
    attempt = runs.execute("SELECT base_sha FROM attempts WHERE token = ?", (token,)).fetchone()
    if attempt is None or attempt["base_sha"] == sha:
        raise ValueError("This commit existed before the run. Start a new attempt for an unrecorded legacy run.")
    _check_edition_document(row["edition"], "gold/data_snapshot.json", sha)
    _check_edition_document(row["edition"], "equity/state/market_state.json", sha)
    _check_extended_equity_documents(row["edition"], sha=sha, base_sha=attempt["base_sha"])
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


def _gh_json(*args: str):
    gh = shutil.which("gh") or next(
        (str(p) for p in (Path("/opt/homebrew/bin/gh"), Path("/usr/local/bin/gh")) if p.is_file()), None,
    )
    if gh is None:
        raise ValueError("GitHub CLI is required to verify Pages deployment.")
    return json.loads(
        subprocess.check_output([gh, *args], cwd=ROOT, env=_clean_env(), text=True, timeout=30)
    )


def _remote_main_head_sha(repository: str) -> str | None:
    """Best-effort lookup of remote origin/main HEAD SHA via GitHub API."""
    try:
        ref = _gh_json("api", f"repos/{repository}/git/ref/heads/main")
        head = ref.get("object", {}).get("sha") if isinstance(ref, dict) else None
        if isinstance(head, str) and SHA_RE.fullmatch(head):
            return head
    except (subprocess.SubprocessError, ValueError, OSError, KeyError, TypeError, StopIteration):
        return None
    return None


def _gh_is_ancestor(repository: str, ancestor: str, descendant: str) -> bool:
    """Check ancestry via GitHub Compare API when local refs do not yet contain descendant."""
    try:
        cmp_data = _gh_json("api", f"repos/{repository}/compare/{ancestor}...{descendant}")
        return isinstance(cmp_data, dict) and cmp_data.get("status") in {"ahead", "identical"}
    except (subprocess.SubprocessError, ValueError, OSError, KeyError, TypeError, StopIteration):
        return False


def verify_pages(sha: str, repository: str, wait: int = 180) -> str:
    """Require the actual main-branch deploy job for the recorded push."""
    deadline = time.monotonic() + wait
    while True:
        try:
            candidates = _gh_json(
                "run", "list", "--repo", repository, "--workflow", "deploy-pages.yml", "--branch", "main",
                "--commit", sha, "--json", "databaseId,headSha,headBranch,status,conclusion,url", "--limit", "10",
            )
        except (subprocess.SubprocessError, ValueError, OSError) as exc:
            if time.monotonic() >= deadline:
                raise DeploymentPending(
                    f"Pages status check failed transiently for {sha}: {exc}; rerun complete for this attempt."
                ) from exc
            time.sleep(min(5, max(0, deadline - time.monotonic())))
            continue

        runs = [run for run in candidates if run["headSha"] == sha and run["headBranch"] == "main"]
        completed = [run for run in runs if run.get("status") == "completed"]
        has_pending = any(run.get("status") != "completed" for run in runs)

        failed_url: str | None = None
        transient_err: Exception | None = None
        for run in completed:
            try:
                details = _gh_json(
                    "run", "view", str(run["databaseId"]), "--repo", repository,
                    "--json", "headSha,headBranch,jobs,url",
                )
            except (subprocess.SubprocessError, ValueError, OSError) as exc:
                transient_err = exc
                continue
            if details["headSha"] == sha and details["headBranch"] == "main" and any(
                job["name"] == DEPLOY_JOB and job["conclusion"] == "success" for job in details["jobs"]
            ):
                return details["url"]
            if failed_url is None:
                failed_url = run["url"]

        if completed and not has_pending and transient_err is None and failed_url is not None:
            current_main = _remote_main_head_sha(repository)
            if current_main is not None and current_main != sha:
                raise ValueError(
                    f"Pages deploy job did not succeed for {sha} ({failed_url}), and remote origin/main has "
                    f"already moved ahead to {current_main}. Run edition_run.py complete-superseded "
                    "(if deployed via a follow-up commit) or close-superseded (if abandoned)."
                )
            raise ValueError(
                f"Pages deploy job did not succeed for {sha}: {failed_url}. Rerun the workflow, then complete."
            )
        if time.monotonic() >= deadline:
            if transient_err is not None:
                raise DeploymentPending(
                    f"Pages status check failed transiently for {sha}: {transient_err}; rerun complete for this attempt."
                ) from transient_err
            raise DeploymentPending(f"Pages is still pending for {sha}; rerun complete for this attempt.")
        time.sleep(min(5, max(0, deadline - time.monotonic())))


def complete(runs: sqlite3.Connection, token: str, wait: int = 180) -> str:
    _publishing_run(runs, token)
    receipt = _publication(runs, token)
    if receipt is None or not receipt["sha"] or not receipt["repository"]:
        raise ValueError("No verified push receipt for this edition. Finish the same publication first.")
    sha, repository = receipt["sha"], receipt["repository"]
    url = verify_pages(sha, repository, wait)
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
         WHERE runs.status = 'running' AND publications.sha IS NOT NULL
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


def complete_superseded(
    runs: sqlite3.Connection,
    edition: str,
    attempt: str,
    deployed_sha: str,
    reason: str,
    *,
    allow_content_hotfix: bool = False,
) -> str:
    """Maintainer-only: complete a publish-phase attempt deployed via a follow-up commit on main."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A non-empty reason is required for complete-superseded.")
    with _idle_publish_lock(), runs:
        # 1. Identify active running attempt in publish phase with an existing publication receipt.
        row = _identify_attempt(runs, edition, attempt)
        if row["phase"] != "publish":
            raise ValueError("Only an edition in its publish phase can be completed via complete-superseded.")
        token = row["token"]
        receipt = _publication(runs, token)
        if receipt is None or not receipt["sha"] or not receipt["repository"]:
            raise ValueError("No recorded publication receipt for this attempt; cannot complete-superseded.")
        orig_sha = receipt["sha"]
        repository = receipt["repository"]
        if not SHA_RE.fullmatch(orig_sha) or not REPOSITORY_RE.fullmatch(repository):
            raise ValueError("Recorded publication receipt contains an invalid commit or repository.")
        attempt_row = runs.execute("SELECT base_sha FROM attempts WHERE token = ?", (token,)).fetchone()
        if attempt_row is None:
            raise ValueError("Recorded attempt metadata missing base_sha; cannot verify publication history.")
        base_sha = attempt_row["base_sha"]

        # 2. Validate deployed_sha is a 40-hex commit distinct from orig_sha and descending from orig_sha.
        if not isinstance(deployed_sha, str) or not SHA_RE.fullmatch(deployed_sha):
            raise ValueError(f"Invalid deployed_sha (must be 40-hex git commit): {deployed_sha!r}.")
        if deployed_sha == orig_sha:
            raise ValueError("deployed_sha equals the original pushed commit; use normal complete instead.")
        if not _git_object_exists(f"{deployed_sha}^{{commit}}"):
            raise ValueError(f"Commit {deployed_sha} does not exist in local git repository.")
        if not _git_is_ancestor(orig_sha, deployed_sha):
            raise ValueError(f"Original pushed commit {orig_sha} is not an ancestor of {deployed_sha}.")

        # 3. Verify deployed_sha is reachable from remote origin/main (is HEAD or ancestor of it).
        remote_main = _remote_main_head_sha(repository)
        if remote_main is None:
            raise ValueError(f"Cannot resolve remote origin/main HEAD for {repository}.")
        if deployed_sha != remote_main:
            if not _git_is_ancestor(deployed_sha, remote_main) and not _gh_is_ancestor(
                repository, deployed_sha, remote_main
            ):
                raise ValueError(
                    f"Commit {deployed_sha} is not reachable from remote origin/main ({remote_main})."
                )

        # 4. Verify deployed_sha still passes core edition publication checks.
        if base_sha == deployed_sha:
            raise ValueError("deployed_sha existed before the run started.")
        _check_edition_document(edition, "gold/data_snapshot.json", deployed_sha)
        _check_edition_document(edition, "equity/state/market_state.json", deployed_sha)
        _check_extended_equity_documents(edition, sha=deployed_sha, base_sha=base_sha)
        check_edition_reviews(edition, sha=deployed_sha)
        _check_gold_ledger_history(base_sha, deployed_sha)

        # 5. Refuse content mutations under gold/ or equity/ unless --allow-content-hotfix is explicitly set.
        if not allow_content_hotfix:
            changed_paths = [
                p.strip()
                for p in git_value("diff", "--name-only", orig_sha, deployed_sha).splitlines()
                if p.strip()
            ]
            content_changes = [p for p in changed_paths if p.startswith(("gold/", "equity/"))]
            if content_changes:
                raise ValueError(
                    f"Follow-up commits between {orig_sha[:12]} and {deployed_sha[:12]} modified content paths "
                    f"({', '.join(content_changes[:5])}); pass --allow-content-hotfix only for an intentional content hotfix."
                )

        # 6. Verify GitHub Pages deployment succeeded for deployed_sha directly (wait=0).
        url = verify_pages(deployed_sha, repository, wait=0)

        runs.execute("BEGIN IMMEDIATE")
        _identify_attempt(runs, edition, attempt)
        _publishing_run(runs, token)
        outcome = f"{deployed_sha} {url} (superseded {orig_sha[:12]}: {reason.strip()[:240]})"
        runs.execute("UPDATE publications SET deployed_sha = ? WHERE token = ?", (deployed_sha, token))
        runs.execute(
            "UPDATE runs SET status = 'complete', updated = ?, outcome = ? WHERE token = ?",
            (utc_now(), outcome, token),
        )
        return url


def status(runs: sqlite3.Connection) -> list[dict]:
    rows = runs.execute("""
        SELECT runs.token, edition, phase, status, started, updated, outcome, substr(runs.token, 1, 12) AS attempt,
               coalesce(attempts.source, 'legacy') AS source, publications.sha AS pushed_commit,
               publications.deployed_sha AS deployed_commit
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
    complete_sup_cmd = commands.add_parser(
        "complete-superseded",
        help="maintainer-only: complete a publish-phase attempt deployed via a follow-up commit on main",
    )
    complete_sup_cmd.add_argument("edition", type=edition_id)
    complete_sup_cmd.add_argument("attempt")
    complete_sup_cmd.add_argument("deployed_sha")
    complete_sup_cmd.add_argument("reason")
    complete_sup_cmd.add_argument(
        "--allow-content-hotfix",
        action="store_true",
        help="allow follow-up commits modifying gold/ or equity/ content paths",
    )
    args = parser.parse_args()

    try:
        with closing(open_runs()) as runs, runs:
            if args.command == "begin":
                if args.scheduled:
                    edition = scheduled_edition(args.scheduled)
                    if reconcile_previous_deployment(runs):
                        runs.commit()
                    token = begin(runs, edition, f"antigravity-{args.scheduled}", reap_stale=True)
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
            elif args.command == "complete-superseded":
                print(
                    complete_superseded(
                        runs,
                        args.edition,
                        args.attempt,
                        args.deployed_sha,
                        args.reason,
                        allow_content_hotfix=args.allow_content_hotfix,
                    )
                )
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
