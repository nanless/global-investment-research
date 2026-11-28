"""Content-bound receipts for the two pre-publication manuscript reviews."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re

if __package__:
    from .source_links import is_https_source
else:
    from source_links import is_https_source


LAST_LEGACY_EDITION = ("2026-11-28", 1130, 1)
CHECK_IDS = (
    "cross_track",
    "calculations",
    "editorial",
    "charts_and_fees",
    "primary_sources",
)
GOLD_DAILY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_.*黄金深度研报(?:_r(\d+))?\.md$")
MARKETS = ("a_share", "hk_stock", "us_stock")
STATE_PATH = "equity/state/market_state.json"
FIXED_PATHS = (
    "gold/data_snapshot.json",
    "gold/master_snapshot.json",
    "gold/market_calendar.json",
    "gold/黄金跨世纪周期与2026-2030终审研究报告.md",
    "gold/daily/SCORECARD.md",
    "gold/daily/AUDIT_LOG.md",
    "gold/daily/CHANGELOG.md",
    "equity/daily/INDEX.md",
    "equity/daily/SCORECARD.md",
    "equity/daily/CHANGELOG.md",
    "equity/state/audit_ledger.md",
    "equity/state/multi_asset_channels.json",
    "equity/state/etf_universe.json",
    "equity/state/deep_dossiers.json",
    "equity/state/policy_calendar.json",
    *(f"equity/report_meta_{market}.json" for market in MARKETS),
    *(f"equity/{market}_market_report_latest.md" for market in MARKETS),
)


def snapshot(
    edition: str,
    read: Callable[[str], bytes],
    gold_names: Iterable[str],
) -> dict:
    state_bytes = read(STATE_PATH)
    state = json.loads(state_bytes)
    if not isinstance(state, dict) or state.get("edition_id") != edition:
        raise ValueError(f"Review candidate market state must match {edition}.")
    gold = []
    for relative in gold_names:
        path = PurePosixPath(relative)
        if len(path.parts) != 1 and not (len(path.parts) == 3 and path.parts[0] == "archive"):
            continue
        match = GOLD_DAILY_RE.fullmatch(path.name)
        if match:
            key = f"{match[1]}_{match[2]}" + (f"_r{match[3]}" if match[3] else "")
            if key == edition:
                gold.append(f"gold/daily/{path}")
    if len(gold) != 1:
        raise ValueError(f"Review candidate {edition} must have exactly one matching gold manuscript.")

    markets = state.get("markets")
    if not isinstance(markets, dict):
        raise ValueError("Review candidate market state has no markets object.")
    equity_paths = []
    for market in MARKETS:
        info = markets.get(market)
        name = info.get("latest_daily") if isinstance(info, dict) else None
        path = PurePosixPath(name) if isinstance(name, str) else None
        in_archive = path is not None and len(path.parts) == 4 and path.parts[1] == "archive"
        if (
            path is None or (len(path.parts) != 2 and not in_archive) or path.parts[0] != "daily"
            or ".." in path.parts
            or not re.fullmatch(rf"\d{{4}}-\d{{2}}-\d{{2}}_\d{{4}}_{market}(?:_r\d+)?\.md", path.name)
        ):
            raise ValueError(f"Review candidate has an invalid latest_daily path for {market}.")
        equity_paths.append(f"equity/{path}")

    digests = {STATE_PATH: hashlib.sha256(state_bytes).hexdigest()}
    for path in (*FIXED_PATHS, *gold, *equity_paths):
        digests[path] = hashlib.sha256(read(path)).hexdigest()
    encoded = json.dumps(digests, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "edition_id": edition,
        "candidate_sha256": hashlib.sha256(encoded).hexdigest(),
        "files": digests,
        "current_manuscripts": [*gold, *(path for path in equity_paths if _equity_edition(path) == edition)],
        "check_ids": list(CHECK_IDS),
    }


def _equity_edition(path: str) -> str:
    stem = PurePosixPath(path).stem
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}_\d{4})_(?:a_share|hk_stock|us_stock)(_r\d+)?", stem)
    assert match is not None
    return match[1] + (match[2] or "")


def read_working_file(root: Path, relative: str) -> bytes:
    root = root.resolve()
    path = root / relative
    if path.resolve() != path or not path.is_relative_to(root):
        raise ValueError(f"Review candidate must use an ordinary path inside the project: {relative}")
    return path.read_bytes()


def working_snapshot(root: Path, edition: str | None = None) -> dict:
    def read(rel: str) -> bytes:
        return read_working_file(root, rel)

    if edition is None:
        state = json.loads(read(STATE_PATH))
        edition = state.get("edition_id") if isinstance(state, dict) else None
        if not isinstance(edition, str) or not edition:
            raise ValueError("Review candidate market state has no edition_id.")
    daily = root / "gold/daily"
    names = (path.relative_to(daily).as_posix() for path in (*daily.glob("*.md"), *daily.glob("archive/*/*.md")))
    return snapshot(edition, read, names)


def validate_receipt(
    closure: dict, candidate: dict, label: str, *, read: Callable[[str], bytes],
) -> None:
    if closure.get("candidate_sha256") != candidate["candidate_sha256"]:
        raise ValueError(f"{label} review candidate digest differs from the current manuscripts and source data.")
    checks = closure.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(CHECK_IDS):
        raise ValueError(f"{label} requires evidence for exactly these five checks: {', '.join(CHECK_IDS)}.")
    for check_id in CHECK_IDS:
        check = checks[check_id]
        evidence = check.get("evidence") if isinstance(check, dict) else None
        paths = check.get("files") if isinstance(check, dict) else None
        if (
            not isinstance(evidence, str) or not evidence.strip()
            or not isinstance(paths, list) or not paths
            or any(not isinstance(path, str) or path not in candidate["files"] for path in paths)
            or len(set(paths)) != len(paths)
        ):
            raise ValueError(f"{label} check {check_id} requires an evidence note and candidate file paths.")
    if not {"gold/data_snapshot.json", STATE_PATH} <= set(checks["cross_track"]["files"]):
        raise ValueError(f"{label} cross_track check must reference both source snapshots.")
    sources = checks["primary_sources"].get("source_urls")
    if (
        not isinstance(sources, list) or not sources
        or not all(is_https_source(url, published_source=True, direct=True) for url in sources)
        or len(set(sources)) != len(sources)
    ):
        raise ValueError(f"{label} primary_sources check requires distinct public HTTPS source URLs.")
    _validate_claims(checks["primary_sources"], candidate, label, read)


def _validate_claims(
    check: dict, candidate: dict, label: str, read: Callable[[str], bytes],
) -> None:
    claims = check.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError(f"{label} primary_sources requires claim-level verification entries.")
    contents: dict[str, str] = {}

    def content(path: str) -> str:
        if path not in contents:
            raw = read(path)
            if hashlib.sha256(raw).hexdigest() != candidate["files"][path]:
                raise ValueError(f"{label} reviewed file changed during verification: {path}.")
            text = raw.decode("utf-8")
            contents[path] = _markdown_prose(text) if path.endswith(".md") else text
        return contents[path]

    reviewed_kinds: dict[str, set[str]] = {}
    used_sources = set()
    seen = set()
    for index, entry in enumerate(claims, start=1):
        where = f"{label} primary_sources claim {index}"
        if not isinstance(entry, dict):
            raise ValueError(f"{where} must be an object.")
        path, excerpt, source_path, url, verification = (
            entry.get(key) for key in ("file", "excerpt", "source_file", "source_url", "verification")
        )
        if any(not isinstance(value, str) or not value.strip() for value in (path, excerpt, source_path, url, verification)):
            raise ValueError(f"{where} requires file, excerpt, source_file, source_url and verification.")
        if sum(char.isalnum() for char in excerpt) < 8 or sum(char.isalnum() for char in verification) < 8:
            raise ValueError(f"{where} requires a substantive excerpt and verification note.")
        if path not in check["files"] or source_path not in check["files"] or url not in check["source_urls"]:
            raise ValueError(f"{where} references a file or source outside the primary_sources check.")
        kind = entry.get("kind")
        if kind not in ("fact", "calculation", "inference"):
            raise ValueError(f"{where} requires kind fact, calculation or inference.")
        if excerpt != excerpt.strip() or len(excerpt.splitlines()) != 1 or excerpt not in content(path):
            raise ValueError(f"{where} excerpt does not match the reviewed file: {path}.")
        source_text = html.unescape(content(source_path))
        if not re.search(rf"[\s<('=\"]{re.escape(url)}(?=$|[\s>')\"])", " " + source_text):
            raise ValueError(f"{where} source URL does not match a citation in {source_path}.")
        key = (path, excerpt, url)
        if key in seen:
            raise ValueError(f"{where} repeats an already verified claim and source.")
        seen.add(key)
        reviewed_kinds.setdefault(path, set()).add(kind)
        used_sources.add(url)
    if missing := set(candidate["current_manuscripts"]) - reviewed_kinds.keys():
        raise ValueError(f"{label} primary_sources missing claims for current manuscripts: {', '.join(sorted(missing))}.")
    for path in candidate["current_manuscripts"]:
        kinds = reviewed_kinds[path]
        if "inference" not in kinds or not kinds.intersection({"fact", "calculation"}):
            raise ValueError(f"{label} primary_sources must review an observed fact or calculation and an inference in {path}.")
    if used_sources != set(check["source_urls"]):
        raise ValueError(f"{label} primary_sources includes unused source URLs.")


def _markdown_prose(text: str) -> str:
    text = re.sub(r"<!--.*?(?:-->|\Z)", "", text, flags=re.DOTALL)
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is None:
            if match:
                fence = match[1]
            else:
                lines.append(line)
        elif match and match[1].startswith(fence) and not match[2].strip():
            fence = None
    return "\n".join(lines)
