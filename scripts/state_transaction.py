"""Serialize cooperating readers and writers and recover interrupted state updates."""

from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from stat import S_IMODE
from typing import Iterator
from uuid import uuid4

JOURNAL_NAME = ".tmp_gir_state_transaction.json"


def _storage(repo_root: Path) -> Path:
    root = repo_root.resolve()
    git_dir = root / ".git"
    if git_dir.is_dir():
        return git_dir
    if git_dir.is_file():
        prefix, _, pointer = git_dir.read_text(encoding="utf-8").strip().partition(": ")
        if prefix == "gitdir" and pointer:
            return (root / pointer).resolve()
        raise ValueError(f"Invalid Git worktree metadata at {git_dir}.")
    return root


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _lock(folder: Path, mode: int) -> Iterator[None]:
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, mode)
        yield
    finally:
        os.close(fd)


@contextmanager
def state_read_lock(repo_root: Path) -> Iterator[None]:
    """Read a stable snapshot, refusing a partially applied transaction after a crash."""
    storage = _storage(repo_root)
    with _lock(storage, fcntl.LOCK_SH):
        if (storage / JOURNAL_NAME).exists():
            raise RuntimeError("A state transaction needs recovery. Rerun the interrupted write command.")
        yield


@contextmanager
def state_write_lock(repo_root: Path) -> Iterator[None]:
    """Recover any interrupted transaction, then lock through read, merge and install."""
    root = repo_root.resolve()
    storage = _storage(root)
    with _lock(storage, fcntl.LOCK_EX):
        _recover(root, storage / JOURNAL_NAME)
        yield


def _digest(content: bytes | None) -> str | None:
    return sha256(content).hexdigest() if content is not None else None


def _staging_path(dest: Path, txid: str) -> Path:
    return dest.with_name(f".{dest.name}.{txid}.tmp")


def _ensure_directory(path: Path) -> None:
    if not path.is_dir():
        _ensure_directory(path.parent)
        path.mkdir(exist_ok=True)
        _sync_directory(path.parent)


def _write_durable(path: Path, content: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(content)
        fh.flush()
        os.fchmod(fh.fileno(), mode)
        os.fsync(fh.fileno())


def _replace(dest: Path, content: bytes | None, mode: int, txid: str) -> None:
    staged = _staging_path(dest, txid)
    staged.unlink(missing_ok=True)
    if content is None:
        dest.unlink(missing_ok=True)
    else:
        _ensure_directory(dest.parent)
        _write_durable(staged, content, mode)
        os.replace(staged, dest)
    if dest.parent.is_dir():
        _sync_directory(dest.parent)


def _destination(root: Path, relative: str) -> Path:
    path = Path(relative)
    dest = root / path
    if (
        path.is_absolute() or not path.parts or ".." in path.parts or ".git" in path.parts
        or dest.resolve() != dest
    ):
        raise ValueError(f"Unsafe state transaction destination {relative!r}.")
    return dest


def _recover(root: Path, journal: Path) -> None:
    journal.with_suffix(".pending").unlink(missing_ok=True)
    if journal.is_symlink():
        raise ValueError("State transaction journal must be a regular file.")
    if not journal.is_file():
        return
    record = json.loads(journal.read_bytes())
    if not isinstance(record, dict) or record.get("version") != 1:
        raise ValueError("Invalid state transaction journal.")
    txid, entries = record.get("id"), record.get("entries")
    if not isinstance(txid, str) or not re.fullmatch(r"[a-f0-9]{32}", txid) or not isinstance(entries, list):
        raise ValueError("Invalid state transaction journal.")

    # Validate all inputs before changing any target. Local edits outside the lock must be preserved.
    restoration = []
    seen = set()
    for entry in entries:
        if (
            not isinstance(entry, dict) or set(entry) != {"path", "mode", "old", "old_sha256", "new_sha256"}
            or not isinstance(entry["path"], str)
            or (entry["old"] is not None and not isinstance(entry["old"], str))
        ):
            raise ValueError("Invalid state transaction entry.")
        dest = _destination(root, entry["path"])
        original = base64.b64decode(entry["old"], validate=True) if entry["old"] is not None else None
        mode = entry["mode"]
        if dest in seen or type(mode) is not int or not 0 <= mode <= 0o7777:
            raise ValueError("Invalid state transaction destination or mode.")
        seen.add(dest)
        actual = _digest(dest.read_bytes()) if dest.exists() else None
        old_hash = _digest(original)
        if old_hash != entry["old_sha256"] or actual not in (old_hash, entry["new_sha256"]):
            raise ValueError(f"Cannot recover {dest.relative_to(root)}: bytes differ from the recorded transaction.")
        restoration.append((dest, original, mode, actual == old_hash))

    for dest, original, mode, unchanged in reversed(restoration):
        if not unchanged or (original is not None and S_IMODE(dest.stat().st_mode) != mode):
            _replace(dest, original, mode, txid)
        else:
            _staging_path(dest, txid).unlink(missing_ok=True)
            if dest.parent.is_dir():
                _sync_directory(dest.parent)
    journal.unlink()
    _sync_directory(journal.parent)


def install_locked(repo_root: Path, writes: list[tuple[Path, bytes | None]]) -> None:
    """Install files under an already-held state_write_lock. None deletes a file."""
    if not writes:
        return
    given_root = repo_root.absolute()
    root = given_root.resolve()
    journal = _storage(root) / JOURNAL_NAME
    if journal.exists():
        raise RuntimeError("Previous state transaction must be recovered before installing files.")
    txid = uuid4().hex
    staged = []
    entries = []
    seen = set()
    for path, content in writes:
        requested = path.absolute()
        parent = given_root if requested.is_relative_to(given_root) else root
        relative = requested.relative_to(parent).as_posix()
        dest = _destination(root, relative)
        if dest in seen or dest.name in (JOURNAL_NAME, journal.with_suffix(".pending").name):
            raise ValueError(f"Duplicate or reserved state transaction destination {relative!r}.")
        seen.add(dest)
        original = dest.read_bytes() if dest.exists() else None
        mode = S_IMODE(dest.stat().st_mode) if original is not None else 0o644
        entries.append({
            "path": relative,
            "old": base64.b64encode(original).decode("ascii") if original is not None else None,
            "old_sha256": _digest(original),
            "new_sha256": _digest(content),
            "mode": mode,
        })
        staged.append((dest, content, mode))

    try:
        pending = journal.with_suffix(".pending")
        record = json.dumps({"version": 1, "id": txid, "entries": entries}).encode("ascii")
        _write_durable(pending, record, 0o600)
        os.replace(pending, journal)
        _sync_directory(journal.parent)
        for dest, content, mode in staged:
            _replace(dest, content, mode, txid)
        # All destination directories are durable before discarding the recovery record.
        journal.unlink()
        _sync_directory(journal.parent)
    except (Exception, KeyboardInterrupt) as exc:
        try:
            _recover(root, journal)
        except (Exception, KeyboardInterrupt) as recovery_error:
            raise RuntimeError(
                f"State transaction failed ({exc}); recovery still pending: {recovery_error}"
            ) from exc
        raise
