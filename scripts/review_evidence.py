"""Content-bound receipts for the two pre-publication manuscript reviews."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

if __package__:
    from .source_links import is_https_source, policy_brief_links
else:
    from source_links import is_https_source, policy_brief_links


LAST_LEGACY_EDITION = ("2026-11-28", 1130, 1)
LAST_LEGACY_CLAIMS_SLOT = "2026-11-28_1800"
LAST_LEGACY_BACKFILL_SLOT = "2026-11-28_1800"
CHECK_IDS = (
    "cross_track",
    "calculations",
    "editorial",
    "charts_and_fees",
    "primary_sources",
)
GOLD_DAILY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4})_.*黄金深度研报(?:_r(\d+))?\.md$")
MARKETS = ("a_share", "hk_stock", "us_stock")
PUBLIC_DAILY_PATTERNS = {
    "gold": re.compile(r"\d{4}-\d{2}-\d{2}_(\d{4})_.*\.md"),
    "equity": re.compile(rf"\d{{4}}-\d{{2}}-\d{{2}}_(\d{{4}})_({'|'.join(MARKETS)})(?:_r\d+)?\.md"),
}
PUBLIC_LEDGER_PREFIXES = {"gold": ("CHANGELOG_", "AUDIT_LOG_"), "equity": ("CHANGELOG_",)}
STATE_PATH = "equity/state/market_state.json"
BACKFILL_STATE_PATHS = {"gold": "gold/data_snapshot.json", "equity": STATE_PATH}
BACKFILL_KINDS = {"gold": ("data_caveats",), "equity": ("data_caveats", "pending_backfills")}
BACKFILL_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")
BACKFILL_CONTENT_FIELDS = ("item", "detail", "impact", "category", "severity")
POLICY_CALENDAR_PATH = "equity/state/policy_calendar.json"
MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
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
    POLICY_CALENDAR_PATH,
    *(f"equity/report_meta_{market}.json" for market in MARKETS),
    *(f"equity/{market}_market_report_latest.md" for market in MARKETS),
)


def _policy_briefs(raw: bytes | str) -> dict[str, dict]:
    calendar = json.loads(raw)
    briefs = calendar.get("policy_briefs") if isinstance(calendar, dict) else None
    if not isinstance(briefs, list):
        raise ValueError("The review candidate policy calendar must contain policy_briefs.")
    by_id: dict[str, dict] = {}
    for brief in briefs:
        brief_id = brief.get("id") if isinstance(brief, dict) else None
        if not isinstance(brief_id, str) or not brief_id.strip() or brief_id in by_id:
            raise ValueError("The review candidate policy briefs must have distinct, nonempty IDs.")
        by_id[brief_id] = brief
    return by_id


def _published_policy_brief(brief: dict) -> bool:
    markets = brief.get("affected_markets")
    return brief.get("home_featured") is True or (
        isinstance(markets, list) and any(market in markets for market in ("gold", *MARKETS))
    )


def _published_daily_paths(paths: Iterable[str]) -> set[str]:
    """Select the top-level and archived manuscripts that can generate portal pages."""
    reports = set()
    for name in paths:
        parts = PurePosixPath(name).parts
        if (len(parts) not in {3, 5} or parts[1] != "daily" or parts[0] not in PUBLIC_DAILY_PATTERNS
                or (len(parts) == 5 and parts[2] != "archive")):
            continue
        match = PUBLIC_DAILY_PATTERNS[parts[0]].fullmatch(parts[-1])
        if match and (len(parts) == 3 or match[1] in {"0730", "1130", "1800"}):
            reports.add(name)
    return reports


def _public_ledger_archive_paths(paths: Iterable[str]) -> set[str]:
    return {
        name for name in paths
        if len(parts := PurePosixPath(name).parts) >= 4 and parts[1:3] == ("daily", "archive")
        and parts[-1].endswith(".md") and parts[-1].startswith(PUBLIC_LEDGER_PREFIXES.get(parts[0], ()))
    }


def snapshot(
    edition: str,
    read: Callable[[str], bytes],
    daily_names: Iterable[str],
) -> dict:
    state_bytes = read(STATE_PATH)
    state = json.loads(state_bytes)
    if not isinstance(state, dict) or state.get("edition_id") != edition:
        raise ValueError(f"Review candidate market state must match {edition}.")
    daily_names = tuple(daily_names)
    published_dailies = _published_daily_paths(daily_names)
    gold = []
    for path in sorted(published_dailies):
        if not path.startswith("gold/daily/"):
            continue
        match = GOLD_DAILY_RE.fullmatch(PurePosixPath(path).name)
        if match:
            key = f"{match[1]}_{match[2]}" + (f"_r{match[3]}" if match[3] else "")
            if key == edition:
                gold.append(path)
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
    featured_policy_briefs = []
    published_policy_briefs = []
    archived_content = set()
    if edition[:15] > LAST_LEGACY_CLAIMS_SLOT:
        archived_content = published_dailies.difference(gold, equity_paths) | _public_ledger_archive_paths(daily_names)
    for path in (*FIXED_PATHS, *gold, *equity_paths, *sorted(archived_content)):
        raw = read(path)
        digests[path] = hashlib.sha256(raw).hexdigest()
        if path == POLICY_CALENDAR_PATH and edition[:15] > LAST_LEGACY_CLAIMS_SLOT:
            for brief_id, brief in _policy_briefs(raw).items():
                details = {"id": brief_id, "headline": brief.get("headline"), "source_urls": policy_brief_links(brief)}
                if brief.get("home_featured") is True:
                    featured_policy_briefs.append(details)
                if _published_policy_brief(brief):
                    published_policy_briefs.append({
                        **details, "summary": brief.get("summary"),
                        **{field: brief[field] for field in ("authority", "date_cst", "time_cst") if field in brief},
                    })
    encoded = json.dumps(digests, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "edition_id": edition,
        "candidate_sha256": hashlib.sha256(encoded).hexdigest(),
        "files": digests,
        "current_manuscripts": [*gold, *(path for path in equity_paths if _equity_edition(path) == edition)],
        "check_ids": list(CHECK_IDS),
        "featured_policy_briefs": featured_policy_briefs,
        "published_policy_briefs": published_policy_briefs,
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
    names = (
        path.relative_to(root).as_posix()
        for track in ("gold", "equity")
        for pattern in ("*.md", "archive/*/*.md", "archive/**/CHANGELOG_*.md", "archive/**/AUDIT_LOG_*.md")
        for path in (root / track / "daily").glob(pattern)
    )
    return snapshot(edition, read, names)


def inspect_changed_historical_manuscripts(
    root: Path, candidate: dict, *, baseline: str = "HEAD", revision: str | None = None,
) -> list[dict[str, str]]:
    if candidate["edition_id"][:15] <= LAST_LEGACY_CLAIMS_SLOT or not (root / ".git").exists():
        return []
    try:
        scope = ("--", "gold/daily", "equity/daily")
        committed = subprocess.check_output(
            ["git", "ls-tree", "--name-only", "-rz", baseline, *scope], cwd=root, timeout=15,
        )
        revisions = [baseline, revision] if revision else [baseline]
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "-z", *revisions, *scope], cwd=root, timeout=15,
        )
        prior_paths = _published_daily_paths(committed.decode("utf-8").split("\0"))
        changed_paths = set(changed.decode("utf-8").split("\0"))
        current_paths = _published_daily_paths(candidate["files"])
        current_manuscripts = set(candidate["current_manuscripts"])
        changes = [
            {"path": path, "status": "modified"}
            for path in (prior_paths & current_paths & changed_paths) - current_manuscripts
        ]
        removed_paths = prior_paths - current_paths
        removed_by_name = {(path.split("/", 1)[0], PurePosixPath(path).name): path for path in removed_paths}
        for path in (current_paths - prior_paths) - current_manuscripts:
            previous = removed_by_name.get((path.split("/", 1)[0], PurePosixPath(path).name))
            if previous is None:
                changes.append({"path": path, "status": "added"})
                continue
            removed_paths.remove(previous)
            raw = subprocess.check_output(["git", "show", f"{baseline}:{previous}"], cwd=root, timeout=15)
            if hashlib.sha256(raw).hexdigest() != candidate["files"][path]:
                changes.append({"path": path, "status": "modified"})
        changes.extend({"path": path, "status": "removed"} for path in removed_paths)
        return sorted(changes, key=lambda entry: entry["path"])
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Cannot compare historical manuscripts with the committed baseline.") from exc


def _planned_slot(value: object) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}_(0730|1130|1800)", value):
        return None
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return None
    return value


def _backfill_rows(raw: bytes, track: str) -> dict[tuple[str, str], dict]:
    state = json.loads(raw)
    if not isinstance(state, dict):
        raise ValueError(f"{track} backfill state must be an object.")
    records: dict[tuple[str, str], dict] = {}
    for kind in BACKFILL_KINDS[track]:
        rows = state.get(kind, [])
        if not isinstance(rows, list):
            raise ValueError(f"{track}.{kind} must be an array for backfill continuity.")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{track}.{kind} contains a non-object backfill.")
            item = row.get("item")
            market = row.get("market", "gold" if track == "gold" else "global")
            backfill_id = row.get("id")
            due = row.get("next_review" if kind == "data_caveats" else "due_session")
            if not isinstance(item, str) or not item.strip() or not isinstance(market, str) or not market:
                raise ValueError(f"{track}.{kind} requires a market and item for each backfill.")
            if kind == "pending_backfills" and backfill_id is None:
                # Pre-ID queue rows use their existing market and normalized item to keep a stable identity.
                identity = market + "\n" + " ".join(item.split())
                backfill_id = "legacy-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
            if not isinstance(backfill_id, str) or BACKFILL_ID_RE.fullmatch(backfill_id) is None:
                raise ValueError(f"{track}.{kind} requires a stable backfill ID.")
            key = (kind, backfill_id)
            if key in records or _planned_slot(due) is None:
                raise ValueError(f"{track}.{kind} {backfill_id} has a duplicate ID or invalid review slot.")
            records[key] = {
                "kind": kind, "id": backfill_id, "market": market, "due_session": due,
                **{field: row[field] for field in BACKFILL_CONTENT_FIELDS if field in row},
            }
    return records


def previous_backfills(edition: str, track: str, raw: bytes) -> dict[tuple[str, str], dict]:
    current_slot = edition[:15]
    if current_slot <= LAST_LEGACY_BACKFILL_SLOT:
        return {}
    prior = json.loads(raw)
    prior_edition = prior.get("edition_id") if isinstance(prior, dict) else None
    if not isinstance(prior_edition, str) or _planned_slot(prior_edition[:15]) is None:
        raise ValueError(f"The previous {track} snapshot does not identify a valid edition.")
    if prior_edition[:15] > current_slot:
        raise ValueError(f"The committed {track} snapshot is newer than the edition under review.")
    if prior_edition[:15] < LAST_LEGACY_BACKFILL_SLOT:
        return {}
    return _backfill_rows(raw, track)


def read_working_backfill_baseline(root: Path, edition: str, track: str) -> bytes | None:
    if edition[:15] <= LAST_LEGACY_BACKFILL_SLOT or not (root / ".git").exists():
        return None
    path = BACKFILL_STATE_PATHS[track]
    try:
        return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=root, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"Cannot read the committed {track} backfill baseline: {path}.") from exc


def inspect_previous_backfills(root: Path, edition: str) -> dict[str, list[dict]]:
    return {
        track: list(previous_backfills(edition, track, raw).values())
        for track in BACKFILL_STATE_PATHS
        if (raw := read_working_backfill_baseline(root, edition, track)) is not None
    }


def validate_backfill_rechecks(closure: dict, edition: str, track: str, previous: bytes, current: bytes) -> None:
    if edition[:15] <= LAST_LEGACY_BACKFILL_SLOT:
        return
    old = previous_backfills(edition, track, previous)
    new = _backfill_rows(current, track)
    evidence = closure.get("backfill_rechecks", [])
    if not isinstance(evidence, list):
        raise ValueError(f"{track} review_closure.backfill_rechecks must be an array.")
    decisions = {}
    for row in evidence:
        if not isinstance(row, dict) or not all(
            isinstance(row.get(field), str) and row[field].strip()
            for field in ("kind", "id", "status", "source_url", "note")
        ):
            raise ValueError(f"{track} backfill recheck requires kind, id, status, source_url and note.")
        key = (row["kind"], row["id"])
        if key not in old or key in decisions or row["status"] not in {"resolved", "still_pending"}:
            raise ValueError(f"{track} backfill recheck must name a unique prior item: {row['kind']}/{row['id']}.")
        if not is_https_source(row["source_url"], published_source=True, direct=True):
            raise ValueError(f"{track} backfill recheck {row['id']} requires specific public HTTPS evidence.")
        decisions[key] = row["status"]

    for row in new.values():
        if row["due_session"] <= edition[:15]:
            raise ValueError(f"{track} backfill {row['kind']}/{row['id']} must set a review slot after the current edition.")

    for key, prior in old.items():
        current_row = new.get(key)
        decision = decisions.get(key)
        label = f"{track} backfill {prior['kind']}/{prior['id']}"
        if current_row is None:
            if decision != "resolved":
                raise ValueError(f"{label} disappeared without a resolved recheck and evidence.")
            continue
        if current_row["market"] != prior["market"] or decision == "resolved":
            raise ValueError(f"{label} cannot change market or remain open after a resolved recheck.")
        changed = current_row["due_session"] != prior["due_session"] or any(
            current_row.get(field) != prior.get(field) for field in BACKFILL_CONTENT_FIELDS
        )
        if changed and decision != "still_pending":
            raise ValueError(f"{label} requires a still_pending recheck and evidence before changing its item or review slot.")


def validate_receipt(
    closure: dict, candidate: dict, label: str, *, read: Callable[[str], bytes],
    historical_changes: Iterable[dict[str, str]] = (),
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
    if candidate["edition_id"][:15] > LAST_LEGACY_BACKFILL_SLOT:
        _validate_resolved_backfill_evidence(closure, candidate, label)
    _validate_historical_review(closure, checks["primary_sources"], historical_changes, label)


def _validate_resolved_backfill_evidence(closure: dict, candidate: dict, label: str) -> None:
    rechecks = closure.get("backfill_rechecks", [])
    if not isinstance(rechecks, list):
        raise ValueError(f"{label} review_closure.backfill_rechecks must be an array.")
    current_files = {STATE_PATH, *FIXED_PATHS, *candidate["current_manuscripts"]}
    verified = {
        (claim["file"], claim["excerpt"], claim["source_url"])
        for claim in closure["checks"]["primary_sources"]["claims"]
        if claim["kind"] in {"fact", "calculation"} and claim["file"] in current_files
    }
    for recheck in rechecks:
        if not isinstance(recheck, dict):
            raise ValueError(f"{label} review_closure.backfill_rechecks entries must be objects.")
        if recheck.get("status") != "resolved":
            continue
        path, excerpt, source = (recheck.get(key) for key in ("file", "excerpt", "source_url"))
        item = recheck.get("id")
        if any(not isinstance(value, str) or not value.strip() for value in (path, excerpt, source)):
            raise ValueError(f"{label} resolved backfill {item} requires its verified file and excerpt.")
        if (path, excerpt, source) not in verified:
            raise ValueError(f"{label} resolved backfill {item} must cite a verified fact or calculation with the same source.")


def _validate_historical_review(closure: dict, primary_sources: dict, changes: Iterable[dict[str, str]], label: str) -> None:
    removals = closure.get("historical_removals", [])
    if not isinstance(removals, list):
        raise ValueError(f"{label} historical_removals must be an array.")
    reasons = set()
    for entry in removals:
        path = entry.get("file") if isinstance(entry, dict) else None
        reason = entry.get("reason") if isinstance(entry, dict) else None
        if (not isinstance(path, str) or not _published_daily_paths((path,)) or path in reasons
                or not isinstance(reason, str) or sum(char.isalnum() for char in reason) < 8):
            raise ValueError(f"{label} historical removal requires a unique manuscript file and substantive reason.")
        reasons.add(path)
    claims = {row["file"] for row in primary_sources["claims"]}
    for change in changes:
        path = change["path"]
        if change["status"] == "removed":
            if path not in reasons:
                raise ValueError(f"{label} must document why this historical manuscript was removed: {path}.")
        elif path not in claims:
            raise ValueError(f"{label} must cite evidence for a claim in the changed historical manuscript: {path}.")


def _validate_claims(
    check: dict, candidate: dict, label: str, read: Callable[[str], bytes],
) -> None:
    claims = check.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError(f"{label} primary_sources requires claim-level verification entries.")
    strict_claims = candidate["edition_id"][:15] > LAST_LEGACY_CLAIMS_SLOT
    current_manuscripts = set(candidate["current_manuscripts"])
    contents: dict[str, str] = {}
    claim_texts: dict[str, str] = {}
    markdown_sources: dict[str, set[str]] = {}

    def content(path: str) -> str:
        if path not in contents:
            raw = read(path)
            if hashlib.sha256(raw).hexdigest() != candidate["files"][path]:
                raise ValueError(f"{label} reviewed file changed during verification: {path}.")
            text = raw.decode("utf-8")
            contents[path] = _markdown_prose(text, portal_fences=strict_claims) if path.endswith(".md") else text
        return contents[path]

    policy_briefs = _policy_briefs(content(POLICY_CALENDAR_PATH)) if strict_claims else {}
    reviewed_briefs = set()
    reviewed_policy_sources = set()
    reviewed_kinds: dict[str, set[str]] = {}
    reviewed_excerpts: dict[str, list[tuple[str, str]]] = {}
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
        brief_id = None
        if strict_claims and path == POLICY_CALENDAR_PATH:
            brief_id = entry.get("policy_brief_id")
            brief = policy_briefs.get(brief_id) if isinstance(brief_id, str) else None
            if brief is None or source_path != path or not any(
                isinstance(value, str) and excerpt in value for value in (brief.get("headline"), brief.get("summary"))
            ):
                raise ValueError(f"{where} must cite the headline or summary of its policy_brief_id in {path}.")
            if url not in policy_brief_links(brief):
                raise ValueError(f"{where} source URL does not belong to policy brief {brief_id}.")
            if kind == "fact":
                reviewed_policy_sources.add((brief_id, url))
                if excerpt == brief.get("summary"):
                    reviewed_briefs.add(brief_id)
        else:
            if excerpt != excerpt.strip() or len(excerpt.splitlines()) != 1:
                raise ValueError(f"{where} excerpt does not match the reviewed file: {path}.")
            if path not in claim_texts:
                text = content(path)
                claim_texts[path] = MARKDOWN_LINK_RE.sub(r"\1", text) if strict_claims and path.endswith(".md") else text
            if excerpt not in claim_texts[path]:
                raise ValueError(f"{where} excerpt does not match the reviewed file: {path}.")
            source_text = content(source_path)
            if strict_claims and source_path.endswith(".md"):
                if source_path not in markdown_sources:
                    markup = re.sub(r"`[^`\n]+`|<code>[^\n]*?</code>", " ", source_text, flags=re.IGNORECASE)
                    if source_path.startswith("gold/"):
                        markup = re.sub(r"<strong>[^\n]*?</strong>", " ", markup, flags=re.IGNORECASE)
                    markdown_sources[source_path] = {
                        target for caption, target in MARKDOWN_LINK_RE.findall(markup) if caption.strip()
                    }
                if url not in markdown_sources[source_path]:
                    raise ValueError(f"{where} source URL does not match a citation link target in {source_path}.")
            elif not re.search(rf"[\s<('=\"]{re.escape(url)}(?=$|[\s>')\"])", " " + html.unescape(source_text)):
                raise ValueError(f"{where} source URL does not match a citation in {source_path}.")
        if strict_claims and path in current_manuscripts:
            normalized = "".join(char for char in excerpt if char.isalnum())
            earlier = reviewed_excerpts.setdefault(path, [])
            if any(
                prior_kind != kind and (prior_excerpt in normalized or normalized in prior_excerpt)
                for prior_kind, prior_excerpt in earlier
            ):
                raise ValueError(f"{where} classifies the same claim excerpt as multiple kinds.")
            earlier.append((kind, normalized))
        key = (path, brief_id, excerpt, url)
        if key in seen:
            raise ValueError(f"{where} repeats an already verified claim and source.")
        seen.add(key)
        reviewed_kinds.setdefault(path, set()).add(kind)
        used_sources.add(url)
    if missing := current_manuscripts - reviewed_kinds.keys():
        raise ValueError(f"{label} primary_sources missing claims for current manuscripts: {', '.join(sorted(missing))}.")
    for path in candidate["current_manuscripts"]:
        kinds = reviewed_kinds[path]
        if strict_claims and kinds != {"fact", "calculation", "inference"}:
            raise ValueError(f"{label} primary_sources must review a fact, calculation and inference in {path}.")
        if not strict_claims and ("inference" not in kinds or not kinds.intersection({"fact", "calculation"})):
            raise ValueError(f"{label} primary_sources must review an observed fact or calculation and an inference in {path}.")
    published_briefs = {brief_id: brief for brief_id, brief in policy_briefs.items() if _published_policy_brief(brief)}
    missing_briefs = published_briefs.keys() - reviewed_briefs
    if missing_briefs:
        raise ValueError(f"{label} primary_sources missing summary facts for published policy briefs: {', '.join(sorted(missing_briefs))}.")
    for brief_id, brief in published_briefs.items():
        for url in policy_brief_links(brief):
            if (brief_id, url) not in reviewed_policy_sources:
                raise ValueError(f"{label} primary_sources has unverified published policy source for {brief_id}: {url}.")
    if used_sources != set(check["source_urls"]):
        raise ValueError(f"{label} primary_sources includes unused source URLs.")


def _markdown_prose(text: str, *, portal_fences: bool = False) -> str:
    text = re.sub(r"<!--.*?(?:-->|\Z)", "", text, flags=re.DOTALL)
    lines = []
    fence = None
    for line in text.splitlines():
        if portal_fences and line.lstrip().startswith("```") and (fence is None or fence.startswith("`")):
            # Both report renderers toggle backtick code on any stripped line beginning with three backticks.
            fence = "```" if fence is None else None
            continue
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is None:
            if match:
                fence = match[1]
            else:
                lines.append(line)
        elif match and match[1].startswith(fence) and not match[2].strip():
            fence = None
    return "\n".join(lines)
