#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sanitized Local Sidecar Installer & Drift Checker for Global Investment Research.

Renders tracked sidecar templates from `automations/sidecars/*.template.json`
into local Antigravity schedule sidecars (`~/.gemini/config/sidecars/<id>/sidecar.json`)
by resolving `__REPO_ROOT__` and `__PYTHON_BIN__`, deduplicating `access_grants`,
validating security invariants (zero unresolved placeholders, zero `*` wildcards
in grants, zero `--permission-mode`), and installing atomically.

Usage:
  python3 scripts/install_sidecars.py                 # Render & atomically install all sidecars
  python3 scripts/install_sidecars.py --dry-run       # Render, validate & preview status without writing
  python3 scripts/install_sidecars.py --check         # Exit 0 only if installed sidecars match byte-for-byte
  python3 scripts/install_sidecars.py --repo-root ... --python-bin ... --target-dir ...
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "automations" / "sidecars"
TEMPLATE_SUFFIX = ".template.json"
DEFAULT_TARGET_DIR = Path.home() / ".gemini" / "config" / "sidecars"

PLACEHOLDER_TOKENS = ("__REPO_ROOT__", "__PYTHON_BIN__")
FORBIDDEN_GLOBAL_TOKENS = ("--permission-mode",)
SCHEDULES = {
    "daily-global-investment-research": "CRON_TZ=Asia/Shanghai 30 7 * * *",
    "daily-global-investment-research-evening": "CRON_TZ=Asia/Shanghai 0 18 * * *",
}
RETIRED_IDS = frozenset({
    "daily-gold-deep-research", "daily-gold-deep-research-evening",
    "daily-a-us-equity-research", "daily-a-us-equity-research-evening",
})


def validate_paths(repo_root: Path, python_bin: str) -> None:
    for path in (str(repo_root), python_bin):
        if not Path(path).is_absolute() or re.search(r"[\s\"'\\;&|$`<>()[\]{}?#%*]", path):
            raise ValueError("repository and Python paths must be absolute and usable as bare command arguments")
    if not Path(python_bin).is_file() or not os.access(python_bin, os.X_OK):
        raise ValueError(f"Python interpreter is missing or not executable: {python_bin}")


def discover_templates(template_dir: Path) -> list[tuple[str, Path]]:
    """Return sorted list of (sidecar_id, template_path)."""
    if not template_dir.is_dir():
        raise FileNotFoundError(f"Template directory not found: {template_dir}")
    templates: list[tuple[str, Path]] = []
    for path in sorted(template_dir.iterdir()):
        if path.is_file() and path.name.endswith(TEMPLATE_SUFFIX):
            sidecar_id = path.name[: -len(TEMPLATE_SUFFIX)]
            if not sidecar_id:
                raise ValueError(f"Empty sidecar id for template: {path}")
            templates.append((sidecar_id, path))
    if not templates:
        raise FileNotFoundError(f"No *{TEMPLATE_SUFFIX} files found in {template_dir}")
    return templates


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def render_template(template_path: Path, repo_root: Path, python_bin: str) -> tuple[str, dict[str, Any]]:
    """Render a sidecar template, deduplicate grants, and validate invariants."""
    raw = template_path.read_text(encoding="utf-8")
    rendered_raw = raw.replace("__REPO_ROOT__", str(repo_root)).replace("__PYTHON_BIN__", python_bin)

    for token in PLACEHOLDER_TOKENS:
        if token in rendered_raw:
            raise ValueError(f"{template_path.name}: unresolved placeholder {token!r}")

    try:
        data = json.loads(rendered_raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{template_path.name}: rendered output is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{template_path.name}: top-level JSON must be an object")
    sidecar_id = template_path.name[:-len(TEMPLATE_SUFFIX)]
    args = data.get("args")
    if (data.get("builtin") != "schedule" or data.get("restart_policy") != "always"
            or not isinstance(args, list) or len(args) != 6
            or not all(isinstance(arg, str) and arg.strip() for arg in args)
            or args[0] != SCHEDULES.get(sidecar_id) or args[1:3] != ["agentapi", "new-conversation"]
            or not args[3].startswith("--model=") or args[4] != "--"):
        raise ValueError(f"{template_path.name}: invalid Antigravity schedule or new-conversation arguments")

    perms = data.get("agent_permissions")
    if not isinstance(perms, dict):
        raise ValueError(f"{template_path.name}: missing or invalid 'agent_permissions' object")

    grants = perms.get("access_grants")
    if not isinstance(grants, list) or not all(isinstance(g, str) for g in grants):
        raise ValueError(f"{template_path.name}: 'agent_permissions.access_grants' must be a list of strings")

    deduped_grants = _dedupe_preserve_order(grants)
    for grant in deduped_grants:
        if "*" in grant:
            raise ValueError(f"{template_path.name}: wildcard '*' forbidden in access_grant: {grant!r}")
    perms["access_grants"] = deduped_grants

    uris = perms.get("workspace_uris")
    if not isinstance(uris, list) or not all(isinstance(u, str) for u in uris):
        raise ValueError(f"{template_path.name}: 'agent_permissions.workspace_uris' must be a list of strings")
    for uri in uris:
        if "*" in uri:
            raise ValueError(f"{template_path.name}: wildcard '*' forbidden in workspace_uri: {uri!r}")
    if uris != [repo_root.as_uri()]:
        raise ValueError(f"{template_path.name}: workspace URI must match the repository")

    final_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    for token in PLACEHOLDER_TOKENS:
        if token in final_text:
            raise ValueError(f"{template_path.name}: unresolved placeholder {token!r} after serialization")
    for token in FORBIDDEN_GLOBAL_TOKENS:
        if token in final_text:
            raise ValueError(f"{template_path.name}: forbidden token {token!r} found in rendered sidecar")

    return final_text, data


def atomic_write_text(dest: Path, content: str) -> None:
    """Atomically write UTF-8 text to dest via temp file in same directory + os.replace."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def find_stale_sidecar_dirs(target_dir: Path) -> list[str]:
    """Only report definitions retired by this project."""
    if not target_dir.is_dir():
        return []
    stale: list[str] = []
    for entry in sorted(target_dir.iterdir()):
        if entry.name in RETIRED_IDS and (entry / "sidecar.json").is_file():
            stale.append(entry.name)
    return stale


def check_registry(registry_path: Path, rendered: dict[str, tuple[str, dict[str, Any]]]) -> list[str]:
    """Check that Antigravity has enabled and resolved the installed definitions."""
    try:
        entries = json.loads(registry_path.read_text(encoding="utf-8"))["sidecars"]
        if not isinstance(entries, dict):
            raise ValueError("sidecars must be an object")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"Cannot read Antigravity registry: {exc}"]

    problems = []
    for sidecar_id, (_, definition) in rendered.items():
        entry = entries.get(sidecar_id, {})
        if not isinstance(entry, dict) or entry.get("enabled") is not True or not entry.get("projectId"):
            problems.append(f"{sidecar_id}: register and enable this task in Antigravity")
            continue
        resolved = entry.get("resolvedPermissions") or {}
        expected = definition["agent_permissions"]
        if (not isinstance(resolved, dict) or resolved.get("workspaceUris") != expected["workspace_uris"]
                or sorted(resolved.get("accessGrants") or []) != sorted(expected["access_grants"])):
            problems.append(f"{sidecar_id}: Antigravity has not resolved the current workspace or command grants")
    return problems


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render, validate, check, or atomically install Antigravity schedule sidecars."
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Absolute path to the repository root (default: auto-detected from script location).",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter path for __PYTHON_BIN__ (default: current sys.executable).",
    )
    parser.add_argument(
        "--target-dir",
        default=str(DEFAULT_TARGET_DIR),
        help="Target sidecars directory (default: ~/.gemini/config/sidecars).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Render and validate all templates without writing to target-dir.",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Exit 0 only if all installed sidecar.json files match rendered templates byte-for-byte and no stale sidecar dirs exist.",
    )
    mode.add_argument("--check-runtime", action="store_true", help="Check both files and Antigravity's enablement/grants.")
    parser.add_argument("--registry", type=Path, help="Registry path for --check-runtime (defaults beside sidecars).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    python_bin = str(args.python_bin)
    target_dir = Path(args.target_dir).expanduser().resolve()
    template_dir = repo_root / "automations" / "sidecars"

    try:
        validate_paths(repo_root, python_bin)
        templates = discover_templates(template_dir)
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    rendered_map: dict[str, tuple[str, dict[str, Any]]] = {}
    for sidecar_id, tpl_path in templates:
        try:
            rendered_map[sidecar_id] = render_template(tpl_path, repo_root, python_bin)
        except Exception as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1

    stale_dirs = find_stale_sidecar_dirs(target_dir)

    if args.check or args.check_runtime:
        mismatches = 0
        for sidecar_id, (rendered_text, data) in rendered_map.items():
            dest = target_dir / sidecar_id / "sidecar.json"
            grants_count = len(data["agent_permissions"]["access_grants"])
            if not dest.is_file():
                print(f"[MISS] {dest} does not exist", file=sys.stderr)
                mismatches += 1
                continue
            current_bytes = dest.read_bytes()
            expected_bytes = rendered_text.encode("utf-8")
            if current_bytes != expected_bytes:
                print(f"[DRIFT] {dest} differs from rendered template", file=sys.stderr)
                mismatches += 1
            else:
                print(f"[OK] {sidecar_id}: byte-for-byte match ({grants_count} exact grants)")
        if stale_dirs:
            print(
                f"[STALE] Unexpected sidecar directories in {target_dir}: {', '.join(stale_dirs)}",
                file=sys.stderr,
            )
            mismatches += 1
        if args.check_runtime:
            registry_path = args.registry or target_dir.parent / "config.json"
            for problem in check_registry(registry_path, rendered_map):
                print(f"[RUNTIME] {problem}", file=sys.stderr)
                mismatches += 1
        if mismatches:
            print(f"[FAIL] Sidecar check failed ({mismatches} issue(s)).", file=sys.stderr)
            return 1
        print(f"[PASS] All {len(rendered_map)} sidecar(s) verified clean in {target_dir}.")
        return 0

    if args.dry_run:
        print(f"[DRY-RUN] repo_root={repo_root}")
        print(f"[DRY-RUN] python_bin={python_bin}")
        print(f"[DRY-RUN] target_dir={target_dir}")
        for sidecar_id, (rendered_text, data) in rendered_map.items():
            dest = target_dir / sidecar_id / "sidecar.json"
            grants = data["agent_permissions"]["access_grants"]
            if dest.is_file() and dest.read_bytes() == rendered_text.encode("utf-8"):
                status = "UNCHANGED"
            elif dest.is_file():
                status = "WOULD-UPDATE"
            else:
                status = "WOULD-CREATE"
            print(f"  - [{status}] {sidecar_id} -> {dest} ({len(grants)} grants)")
        if stale_dirs:
            print(f"  [WARN] Stale extra sidecar dirs in {target_dir}: {', '.join(stale_dirs)}")
        print("[DRY-RUN] Validation passed; no files modified.")
        return 0

    for sidecar_id, (rendered_text, data) in rendered_map.items():
        dest = target_dir / sidecar_id / "sidecar.json"
        grants = data["agent_permissions"]["access_grants"]
        atomic_write_text(dest, rendered_text)
        print(f"[INSTALLED] {sidecar_id} -> {dest} ({len(grants)} exact grants)")

    if stale_dirs:
        print(
            f"[WARN] Extra sidecar directories exist in {target_dir}: {', '.join(stale_dirs)}",
            file=sys.stderr,
        )
    print(f"[DONE] Installed {len(rendered_map)} sidecar(s) cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
