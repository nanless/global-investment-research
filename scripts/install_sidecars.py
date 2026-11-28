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
import subprocess
import sys
import tempfile
from pathlib import Path
from stat import S_IMODE
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "automations" / "sidecars"
TEMPLATE_SUFFIX = ".template.json"
DEFAULT_TARGET_DIR = Path.home() / ".gemini" / "config" / "sidecars"

PLACEHOLDER_TOKENS = (
    "__REPO_ROOT__", "__PYTHON_BIN__", "__RUN_SLOT__", "__UNIFIED_PROMPT__", "__SHARED_GRANTS__",
)
FORBIDDEN_GLOBAL_TOKENS = ("--permission-mode",)
PERMISSION_GRANT_COUNT = 56
SHELL_INJECTION_RE = re.compile(r"(?:;|&&|\|\||\||`|\$\()")
FENCED_CODE_BLOCK_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
SCHEDULES = {
    "daily-global-investment-research": "CRON_TZ=Asia/Shanghai 30 7 * * *",
    "daily-global-investment-research-midday": "CRON_TZ=Asia/Shanghai 30 11 * * *",
    "daily-global-investment-research-evening": "CRON_TZ=Asia/Shanghai 0 18 * * *",
}
SLOTS = {
    "daily-global-investment-research": "0730",
    "daily-global-investment-research-midday": "1130",
    "daily-global-investment-research-evening": "1800",
}
RETIRED_IDS = frozenset({
    "daily-gold-deep-research", "daily-gold-deep-research-evening",
    "daily-a-us-equity-research", "daily-a-us-equity-research-evening",
})
STALE_PREFIXES = ("gir-local-replay-",)


def _is_stale_sidecar_id(sidecar_id: str) -> bool:
    return sidecar_id in RETIRED_IDS or any(sidecar_id.startswith(prefix) for prefix in STALE_PREFIXES)


def validate_paths(repo_root: Path, python_bin: str) -> None:
    for path in (str(repo_root), python_bin):
        if not Path(path).is_absolute() or re.search(r"[\s\"'\\;&|$`<>()[\]{}?#%*]", path):
            raise ValueError("repository and Python paths must be absolute and usable as bare command arguments")
    if not Path(python_bin).is_file() or not os.access(python_bin, os.X_OK):
        raise ValueError(f"Python interpreter is missing or not executable: {python_bin}")
    try:
        result = subprocess.run(
            [python_bin, "-I", "-S", "-c", "import sys\nprint(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            check=True, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"Cannot determine Python interpreter version: {python_bin}") from exc
    version = re.fullmatch(r"([0-9]+)\.([0-9]+)", result.stdout.strip())
    if version is None or tuple(map(int, version.groups())) < (3, 12):
        actual = result.stdout.strip() if version else "unknown"
        raise ValueError(f"Scheduled publication requires Python 3.12 or newer: {python_bin} reports {actual}")


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
    if {sidecar_id for sidecar_id, _ in templates} != set(SCHEDULES):
        raise ValueError("The automation directory must contain exactly the three unified templates.")
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
    try:
        data = json.loads(template_path.read_text(encoding="utf-8"))
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
    if args[5] != "__UNIFIED_PROMPT__":
        raise ValueError(f"{template_path.name}: use the shared automation prompt")
    prompt = (template_path.parent.parent / "unified-edition.prompt.md").read_text(encoding="utf-8")
    if "__RUN_SLOT__" not in prompt:
        raise ValueError("The shared prompt does not select its scheduled slot.")
    slot = SLOTS[sidecar_id]
    args[5] = (prompt.replace("__RUN_SLOT__", slot).replace("__REPO_ROOT__", str(repo_root))
               .replace("__PYTHON_BIN__", python_bin))

    perms = data.get("agent_permissions")
    if not isinstance(perms, dict):
        raise ValueError(f"{template_path.name}: missing or invalid 'agent_permissions' object")

    if perms.get("access_grants") != ["__SHARED_GRANTS__"]:
        raise ValueError(f"{template_path.name}: use the shared permission configuration")
    grants = json.loads((template_path.parent.parent / "permissions.json").read_text(encoding="utf-8"))
    if not isinstance(grants, list) or not all(isinstance(g, str) for g in grants):
        raise ValueError(f"{template_path.name}: 'agent_permissions.access_grants' must be a list of strings")

    deduped_grants = _dedupe_preserve_order([
        grant.replace("__REPO_ROOT__", str(repo_root)).replace("__PYTHON_BIN__", python_bin) for grant in grants
    ])
    if len(grants) != PERMISSION_GRANT_COUNT or len(deduped_grants) != PERMISSION_GRANT_COUNT:
        raise ValueError(f"{template_path.name}: require exactly {PERMISSION_GRANT_COUNT} distinct configured grants")
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
    uris = [uri.replace("__REPO_ROOT__", str(repo_root)) for uri in uris]
    if uris != [repo_root.as_uri()]:
        raise ValueError(f"{template_path.name}: workspace URI must match the repository")
    perms["workspace_uris"] = uris

    command_grants = [
        entry[len("command("):-1] for entry in deduped_grants
        if entry.startswith("command(") and entry.endswith(")")
    ]
    _audit_prompt_commands(args[5], python_bin, command_grants, template_path.name)

    final_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    for token in PLACEHOLDER_TOKENS:
        if token in final_text:
            raise ValueError(f"{template_path.name}: unresolved placeholder {token!r} after serialization")
    for token in FORBIDDEN_GLOBAL_TOKENS:
        if token in final_text:
            raise ValueError(f"{template_path.name}: forbidden token {token!r} found in rendered sidecar")

    return final_text, data


def _audit_prompt_commands(
    prompt_text: str, python_bin: str, command_grants: list[str], template_name: str
) -> None:
    """Audit both inline backticks and fenced code blocks for Python invocations and shell chaining/injection."""
    for grant in command_grants:
        if SHELL_INJECTION_RE.search(grant):
            raise ValueError(f"{template_name}: command grant contains forbidden shell metacharacters: {grant!r}")

    candidates: list[str] = []
    for block_match in FENCED_CODE_BLOCK_RE.finditer(prompt_text):
        for raw_line in block_match.group(1).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("$ "):
                line = line[2:].strip()
            if line:
                candidates.append(line)

    inline_only = FENCED_CODE_BLOCK_RE.sub("", prompt_text)
    for inline_cmd in re.findall(r"`([^\n`]+)`", inline_only):
        cmd = inline_cmd.strip()
        if cmd:
            candidates.append(cmd)

    py_cmd_re = re.compile(
        rf"(?:^|[\s;|&])(?:{re.escape(python_bin)}|__PYTHON_BIN__|python3(?:\.\d+)?)(?:\s|$)"
    )
    for command in candidates:
        if not py_cmd_re.search(command):
            continue
        if SHELL_INJECTION_RE.search(command):
            raise ValueError(
                f"{template_name}: shared prompt command contains forbidden shell metacharacters: {command!r}"
            )
        if not any(command == grant or command.startswith(grant + " ") for grant in command_grants):
            raise ValueError(f"{template_name}: shared prompt uses an unlisted command: {command!r}")


def atomic_write_bytes(dest: Path, content: bytes) -> None:
    """Atomically write raw bytes to dest via temp file in same directory + os.replace."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    mode = S_IMODE(dest.stat().st_mode) if dest.exists() else 0o600
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fchmod(fh.fileno(), mode)
            os.fsync(fh.fileno())
        os.replace(tmp_path, dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_text(dest: Path, content: str) -> None:
    """Atomically write UTF-8 text to dest via temp file in same directory + os.replace."""
    atomic_write_bytes(dest, content.encode("utf-8"))


def find_stale_sidecar_dirs(target_dir: Path) -> list[str]:
    """Report sidecar directories retired by this project or left over from local replay runs."""
    if not target_dir.is_dir():
        return []
    stale: list[str] = []
    for entry in sorted(target_dir.iterdir()):
        if _is_stale_sidecar_id(entry.name) and (entry.is_dir() or (entry / "sidecar.json").is_file()):
            stale.append(entry.name)
    return stale


def _string_list(value: Any) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return sorted(value)
    return None


def check_registry(
    registry_path: Path, rendered: dict[str, tuple[str, dict[str, Any]]], notes: list[str] | None = None,
) -> list[str]:
    """Check both Antigravity's registration and the referenced project files."""
    try:
        entries = json.loads(registry_path.read_text(encoding="utf-8"))["sidecars"]
        if not isinstance(entries, dict):
            raise ValueError("sidecars must be an object")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"Cannot read Antigravity registry: {exc}"]

    problems = []
    for stale_id in sorted(k for k in entries if _is_stale_sidecar_id(k)):
        stale_entry = entries.get(stale_id)
        enabled_flag = isinstance(stale_entry, dict) and stale_entry.get("enabled") is True
        state_desc = "still enabled" if enabled_flag else "stale entry"
        problems.append(f"{stale_id}: retired/replay sidecar ({state_desc}) must be removed from Antigravity registry")
    projects_seen = set()
    for sidecar_id, (_, definition) in rendered.items():
        entry = entries.get(sidecar_id, {})
        project_id = entry.get("projectId") if isinstance(entry, dict) else None
        if not isinstance(project_id, str) or not re.fullmatch(r"[\w-]+", project_id, re.ASCII):
            problems.append(f"{sidecar_id}: missing or invalid Antigravity registration")
            continue
        if entry.get("enabled") is False:
            problems.append(f"{sidecar_id}: disabled in Antigravity")
        elif entry.get("enabled") is not True:
            problems.append(f"{sidecar_id}: Antigravity registration lacks a valid enablement status")
        resolved = entry.get("resolvedPermissions") or {}
        expected = definition["agent_permissions"]
        if (not isinstance(resolved, dict) or resolved.get("workspaceUris") != expected["workspace_uris"]
                or _string_list(resolved.get("accessGrants")) != sorted(expected["access_grants"])
                or entry.get("argumentValues") not in (None, {})):
            problems.append(f"{sidecar_id}: Antigravity has not resolved the current workspace or command grants")
        if project_id in projects_seen:
            problems.append(f"{sidecar_id}: automation must have its own Antigravity project")
        projects_seen.add(project_id)
        try:
            project_path = registry_path.parent / "projects" / f"{project_id}.json"
            project = json.loads(project_path.read_text(encoding="utf-8"))
            project_grants = project["permissionGrants"]["permissionGrants"]
            settings = project["settings"]
            resources = project["projectResources"]["resources"]
            locations = {
                folder_uri for resource in resources
                for folder_uri in (resource.get("folderUri"), resource.get("gitFolder", {}).get("folderUri"))
                if folder_uri is not None
            }
            if (project["id"] != project_id or project["sidecar"]["sidecarId"] != sidecar_id
                    or locations != set(expected["workspace_uris"])
                    or _string_list(project_grants.get("allow")) != sorted(expected["access_grants"])):
                problems.append(f"{sidecar_id}: project identity, workspace or recorded allow rules differ")
            preset = settings.get("permissionPreset", "inherited policy")
            if settings.get("sandboxMode") is not True or preset == "AGENT_PERMISSION_PRESET_TURBO":
                message = (
                    f"{sidecar_id}: terminal sandbox is not verified as enabled under "
                    f"{preset}; "
                    "recorded grants cannot verify effective access"
                )
                if entry.get("enabled") is True:
                    problems.append(message)
                elif notes is not None:
                    notes.append(message)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            problems.append(f"{sidecar_id}: cannot verify the referenced Antigravity project")
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
    args = parser.parse_args(argv)
    if args.registry is not None and not args.check_runtime:
        parser.error("--registry requires --check-runtime.")
    return args


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

    destinations = {sidecar_id: target_dir / sidecar_id / "sidecar.json" for sidecar_id in rendered_map}
    for dest in destinations.values():
        if dest.is_symlink() or dest.parent.is_symlink():
            print(f"[FAIL] Sidecar destination must not be a symbolic link: {dest}", file=sys.stderr)
            return 1

    stale_dirs = find_stale_sidecar_dirs(target_dir)

    if args.check or args.check_runtime:
        mismatches = 0
        for sidecar_id, (rendered_text, data) in rendered_map.items():
            dest = destinations[sidecar_id]
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
                print(f"[OK] {sidecar_id}: byte-for-byte match ({grants_count} configured grants)")
        if stale_dirs:
            print(
                f"[STALE] Unexpected sidecar directories in {target_dir}: {', '.join(stale_dirs)}",
                file=sys.stderr,
            )
            mismatches += 1
        if args.check_runtime:
            registry_path = args.registry or target_dir.parent / "config.json"
            notes: list[str] = []
            for problem in check_registry(registry_path, rendered_map, notes):
                print(f"[RUNTIME] {problem}", file=sys.stderr)
                mismatches += 1
            for note in notes:
                print(f"[RUNTIME] {note}")
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
            dest = destinations[sidecar_id]
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

    written: list[tuple[Path, bytes | None]] = []
    try:
        for sidecar_id, (rendered_text, data) in rendered_map.items():
            dest = destinations[sidecar_id]
            expected_bytes = rendered_text.encode("utf-8")
            previous = dest.read_bytes() if dest.is_file() else None
            if previous == expected_bytes:
                continue
            atomic_write_bytes(dest, expected_bytes)
            written.append((dest, previous))
            print(f"[INSTALLED] {sidecar_id} -> {dest} ({len(data['agent_permissions']['access_grants'])} grants)")
    except (OSError, ValueError) as exc:
        print(f"[FAIL] Cannot install all scheduled tasks: {exc}", file=sys.stderr)
        for path, previous in reversed(written):
            try:
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write_bytes(path, previous)
            except OSError as rollback_error:
                print(f"[FAIL] Cannot roll back {path.name}: {rollback_error}", file=sys.stderr)
        return 1

    if stale_dirs:
        print(
            f"[WARN] Extra sidecar directories exist in {target_dir}: {', '.join(stale_dirs)}",
            file=sys.stderr,
        )
    print(f"[DONE] Installed {len(rendered_map)} sidecar(s) cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
