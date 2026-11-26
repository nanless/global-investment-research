#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-dependency atomic incremental merge & lossless ledger prepender.

Prevents 300s streaming write timeouts during automated editions by applying
compact patch files with full pre-write forensic validation and all-or-nothing
transactional rollback.

Fixed safe commands (no arbitrary external path arguments accepted):
  python3 scripts/patch_state_dbs.py --apply [--dry-run] [--keep-patch] [--skip-edition-lock]
  python3 scripts/patch_state_dbs.py --prepend-gold-ledgers [--dry-run] [--keep-patch]
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent

EDITION_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(0730|1800)(?:_r([2-9]|[1-9]\d+))?")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED_MULTI_ASSET_CHANNELS = (
    "reverse_repo",
    "large_cds",
    "fx_deposits_wm",
    "bonds",
    "funds_wm",
    "savings_insurance",
    "tax_advantaged_accounts",
    "qdii_mrf",
    "convertible_bonds",
    "c_reits",
    "commodity_etfs",
    "private_funds_trust",
)
REQUIRED_CHANNEL_SET = frozenset(REQUIRED_MULTI_ASSET_CHANNELS)
ALLOWED_STATUS_TONES = frozenset({"green", "blue", "amber", "red"})

ETF_REQUIRED_STR_FIELDS = (
    "code",
    "name",
    "market",
    "channel",
    "fee_total_pct",
    "thesis_deep",
    "risk_boundary",
    "action_role",
)
ETF_ALL_21_KEYS = frozenset({
    "code",
    "name",
    "market",
    "market_label",
    "channel",
    "category",
    "tracking_index",
    "aum",
    "fee_total_pct",
    "fee_num",
    "liquidity",
    "yield_or_pe",
    "top_holdings",
    "premium_status",
    "premium_note",
    "tax_and_rules",
    "thesis_deep",
    "risk_boundary",
    "action_role",
    "otc_feeder",
    "gold_locked",
})
ETF_ALLOWED_MARKETS = frozenset({"a-share", "hk-stock", "us-stock", "global", "multi-asset"})
ETF_ALLOWED_CHANNELS = frozenset({
    "境内场内",
    "境内场外",
    "离岸港交所",
    "境内非QDII港股通",
    "境内QDII",
    "离岸美股",
    "爱尔兰UCITS",
})
ETF_ALLOWED_PREMIUM_STATUSES = frozenset({"normal", "watch", "high_risk"})
MIN_ETF_COUNT = 140
MAX_ETF_DELTA = 10

DOSSIER_DIMENSIONS = (
    "moat",
    "financials",
    "valuation_anchor",
    "shareholder_flow",
    "catalysts",
    "bear_case",
    "action_etf",
)

RAW_MARKUP_RE = re.compile(r"\*\*|<br\s*/?>|`", flags=re.IGNORECASE)
EXACT_PCT_RE = re.compile(r"^(\d+(?:\.\d+)?)%$")
RANGE_PCT_RE = re.compile(r"\d+(?:\.\d+)?%\s*[–\-~至]\s*\d+(?:\.\d+)?%")
RESTRICTED_CODES_RE = re.compile(r"(?<![0-9])(?:968118|968001|00011)(?![0-9])")
RESTRICTED_WARN_RE = re.compile(
    r"(?:暂停|停申|停购|封盘|已停|停售|限购|退市|私有化|勿买|勿选|勿误配|"
    r"严禁|禁止|严避|禁买|禁推|禁配|禁碰|切忌|避坑|避开|绕开|远离|回避|"
    r"不可|不买|不推|莫买|别买|别碰|慎碰|高危|雷区|警示|清盘|剔除|弃用|改以|替代)"
)

ENTRY_GATE_IDS = ("real_yield", "rate_spread", "vix", "ny_close")
AS_OF_SHORT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
ALLOWED_FORECAST_REVIEW_STATUSES = frozenset({"settled", "none_due", "pending_evidence"})
DEPRECATED_BINARY_LINK_RE = re.compile(
    r"(?:\[[^\]]+\]\((?!https?://)[^)\s]+\.(?:pdf|docx)(?:#[^)\s]*)?\)"
    r"|/releases/download/"
    r"|\{md,pdf,docx\}"
    r"|(?:daily/|archive/|\.\.?/)[^\s`\"'()<>]+\.(?:pdf|docx))",
    flags=re.IGNORECASE,
)
FEE_EXCLUDE_SPAN_RE = re.compile(
    r"(?:申购费?|赎回费?|1折|一折|佣金|销服(?:优惠至|费)?|销售服务费)"
    r"[^\s｜|，,；;）)。”\"·]{0,12}?"
    r"\d+(?:\.\d+)?%(?:\s*[–\-~至]\s*\d+(?:\.\d+)?%)?"
)
DYNAMIC_SIGNED_PCT_RE = re.compile(r"(?<![0-9A-Za-z%])[+\-]\d+(?:\.\d+)?%")
DYNAMIC_COUNT_RE = re.compile(r"\d+\s*只(?:跨境|纳指|美股|停牌)")
HISTORICAL_CTX_RE = re.compile(
    r"(?:对\d+/\d+|较|原|前日|昨日|自.{0,8}降至|由.{0,8}升至|历史|11/\d+)"
)
AH_PREMIUM_MENTION_RE = re.compile(
    r"(?:AH\s*溢价|A/H\s*溢价|A\s*股较\s*H\s*股[^，。；]{0,24}?溢价|"
    r"A\s*折\s*H|AH\s*(?:罕见|深度)?倒挂|A/H\s*(?:仍呈)?倒挂)"
    r"[^0-9+\-，。；（）]{0,14}([+\-]?\d+(?:\.\d+)?)%"
    r"(?:\s*[–\-~～至]\s*([+\-]?\d+(?:\.\d+)?)%)?"
)
CHANNEL_META_KEYS = frozenset({
    "id", "order", "category", "category_label", "money_bucket",
    "high_net_worth_only", "min_amount_tier", "risk_stars", "status_tone",
    "related_etf_codes",
})

GOLD_ETF_CODES = frozenset({
    "518660", "518880", "518850", "159934", "159937", "518800",
    "517520", "159562", "02840", "03081",
    "GLD", "IAU", "IAUM", "GLDM", "IGLN", "GDX", "GDXJ",
})
GOLD_ETF_NAME_RE = re.compile(
    r"(?<!非)(?:黄金|金矿|实物金|沪金|金股|SPDR\s*金(?!融)|SPDR\s*Gold|iShares\s*Gold|Physical\s*Gold|Gold\s*Miners)",
    flags=re.IGNORECASE,
)
GOLD_ETF_FORBIDDEN_ROLE_RE = re.compile(r"(?:底座|买入|推荐|定投|配置|建仓|吸纳|加仓)")
GOLD_DOSSIER_KEYS = frozenset({
    "a-share:601899", "a-share:600547", "a-share:600489", "a-share:600988", "a-share:000975",
    "hk-stock:02899.HK", "hk-stock:06181.HK", "hk-stock:01929.HK", "hk-stock:01818.HK",
    "hk-stock:01787.HK", "hk-stock:02099.HK",
    "us-stock:NEM", "us-stock:GOLD", "us-stock:AEM", "us-stock:WPM", "us-stock:FNV",
})
GOLD_BASE_ROLE_RE = re.compile(r"(?:当下底座|绿色底座|🟢)")
GOLD_BASE_NEGATION_RE = re.compile(
    r"(?:严禁|禁止|切忌|不可|不得|暂不|不|非|不是|勿)(?:列为|标为|作为|当成|视为)?[\s“‘「\x22*_]*$"
)
GOLD_ACTIVE_BUY_RE = re.compile(
    r"(?:补齐|补足|买入|买进|加仓|加配|抄底|逢低买|低吸|新买|买|定投|配置|建仓|吸纳)"
    r"\s*(?:[0-9一二两三半成%–\-~约近超]*\s*)?"
    r"(?:(?:现货|实物|纸|积存)?(?:黄金|金仓|金矿股?|黄金股)|"
    r"(?:518660|518880|518850|159934|159937|518800|517520|159562|02840|03081|"
    r"(?<![A-Za-z])(?:GLD|IAU|IAUM|GLDM|IGLN|GDX|GDXJ)(?![A-Za-z])))",
    flags=re.IGNORECASE,
)
GOLD_DEFER_GUARD_RE = re.compile(
    r"(?:暂不|严禁|禁止|切忌|勿|停止|暂停|先别|不能|不宜|不要|别急着|拒绝|不考虑|不允许|不应|不会|未在黄金红灯停期|不)"
    r"(?:追高芯片[与或])?(?:现在|今天|今日|当下|任何|立即|马上|急于|立刻|再|去|主动|新|分批|小批|继续|同步|直接|冲动|抢跑)*"
    r"(?:(?:新买|买入|加仓|抄底|定投|配置|建仓|补齐)[/／、与或])?[\s“‘「\x22*_]*$"
    r"|(?:等到?|待).{0,14}(?:黄灯|绿灯|解锁)(?:亮起|确认)?(?:后)?(?:再|才)?(?:分批|择机|恢复|重启|再)*[\s“‘「\x22]*$"
    r"|(?:黄灯|绿灯|解锁|过四关|全部过关)(?:亮起|确认)?后(?:再|才)?(?:分批|择机|恢复|重启|再)*[\s“‘「\x22]*$"
    r"|(?:原稿曾建议|原稿曾考虑|过去曾建议|曾建议)[\s“‘「\x22]*$"
)
GOLD_MINER_TICKERS_RE = re.compile(
    r"(?:NEM|纽蒙特|山东黄金|中金黄金|赤峰黄金|山金国际|紫金黄金|紫金矿业|招金|老铺黄金|周大福|"
    r"GLD|GLDM|IAU|IAUM|IGLN|GDX|GDXJ|518660|518880|518850|518800|517520|159934|159937|159562|02840|03081|02899|06181|01929)",
    flags=re.IGNORECASE,
)

BANNED_INTERNAL_RE = re.compile(
    r"(?:\bV\d+\.\d+\b|Subagent|红队|法证|\bTier\s*[0-3]\b|\bSSOT\b|"
    r"build_(?:a_share_pdf|hk_stock_pdf|us_stock_pdf|daily|report|site|pdf)\.py|"
    r"publish_site\.py|pdf_common\.py|docx_embed\.py|lint_(?:equity|readability|site)\.py|"
    r"edition_(?:run|plan|validation)\.py|patch_state_dbs\.py|artifact_receipt\.py|chart_input\.py|install_sidecars\.py|"
    r"DAILY_REPORT_SPEC\.md|DAILY_FORMAT_SPEC\.md|audit_ledger\.md|market_state\.json|"
    r"multi_asset_channels\.json|etf_universe\.json|deep_dossiers\.json|market_calendar\.json|"
    r"master_snapshot\.json|data_snapshot\.json|_edition_patch\.json|_ledger_patch\.json|"
    r"unified-edition\.prompt\.md|permissions\.json|"
    r"AGENTS\.md|GEMINI\.md|SKILL\.md|sidecar\.json|"
    r"RSI_PLAYBOOK(?:\.md)?|rsi_metrics\.json|Meta-RSI|Recursive\s+Self-Improvement|"
    r"next_run_watch|rsi_self_review_protocol|"
    r"RSI\s*(?:自(?:我|优|评|检|进)|盲审|复盘|闭环|体检|遥测|打分|简报|手册|进化|迭代|协议)|"
    r"\bTier\s*[ABC](?:/[ABC])+\b|"
    r"\bTier\s*[ABC]\s*(?:自|提案|补丁|改进|优化|经验|规则|落盘|落地|架构|锁定|权限|边界|评估|升级)|"
    r"20\d{6}_1\.csv|适配手机端免横滑)",
    flags=re.IGNORECASE,
)
LOCAL_PATH_RE = re.compile(r"(?:file:///|/Users/|/home/|[A-Za-z]:\\Users\\|/opt/homebrew/)")

GOLD_REVIEW_BLOCK_RE = re.compile(r"<!--\s*GOLD_EDITION_REVIEW\s+(\{.*?\})\s*-->", re.DOTALL)
GOLD_CHANGELOG_MARKER_RE = re.compile(r"<!--\s*GOLD_EDITION_CHANGELOG\s+([^\s]+)\s*-->")

ALLOWED_EQUITY_PATCH_TOP_KEYS = frozenset({
    "edition_id",
    "as_of_date",
    "as_of_label",
    "gold_tier0_locked",
    "gold_mutex_note",
    "gold_lock_notice",
    "multi_asset_channels",
    "etf_universe",
    "deep_dossiers",
    "note",
    "summary",
})
ALLOWED_LEDGER_PATCH_KEYS = frozenset({
    "edition_id",
    "changelog_entry_md",
    "audit_review_block_md",
    "audit_source_index_md",
    "note",
})


def _safe_repo_path(repo_root: Path, *parts: str) -> Path:
    root = repo_root.resolve()
    target = (root.joinpath(*parts)).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Path escapes repository root: {parts!r}")
    return target


def _validate_edition_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("edition_id must be a string (YYYY-MM-DD_0730 or YYYY-MM-DD_1800[_rN]).")
    m = EDITION_RE.fullmatch(value.strip())
    if m is None:
        raise ValueError(f"Invalid edition_id format: {value!r}")
    try:
        datetime.strptime(m.group(1), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid calendar date in edition_id {value!r}: {exc}") from exc
    return value.strip()


def _validate_date(value: object, label: str) -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value.strip()):
        raise ValueError(f"{label} must be YYYY-MM-DD, got {value!r}")
    val = value.strip()
    try:
        datetime.strptime(val, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid {label} date {val!r}: {exc}") from exc
    return val


def _normalize_etf_code(code: object) -> str:
    raw = str(code or "").strip().upper()
    base = re.sub(r"\.(?:HK|L|SS|SZ|US)$", "", raw)
    if base.isdigit() and len(base) == 4:
        return base.zfill(5)
    return base


def _walk_json_strings(
    obj: object,
    path: str = "",
    *,
    skip_keys: frozenset[str] = frozenset({
        "schema_version", "id", "edition_id", "as_of_date", "updated_at", "category", "status_tone",
    }),
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(obj, str):
        out.append((path, obj))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            out.extend(_walk_json_strings(item, f"{path}[{i}]", skip_keys=skip_keys))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in skip_keys:
                continue
            child = f"{path}.{k}" if path else str(k)
            out.extend(_walk_json_strings(v, child, skip_keys=skip_keys))
    return out


def _scan_text_for_gold_buy(label: str, text: str) -> list[str]:
    found: list[str] = []
    for idx, ln in enumerate(text.splitlines(), 1):
        if any(
            not GOLD_DEFER_GUARD_RE.search(re.split(r"[。！？；，,、|]", ln[: action.start()])[-1])
            for action in GOLD_ACTIVE_BUY_RE.finditer(ln)
        ):
            found.append(
                f"Gold Tier-0 互斥冲突 ({label}:L{idx})：黄金红灯停期严禁下达新买/补齐黄金指令 -> {ln.strip()[:72]}"
            )
    return found


def _read_json_obj(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Missing required JSON file: {label}")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot parse {label}: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError(f"{label} root must be a JSON object.")
    return obj


def _serialize_json(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _target_file_mode(dest: Path) -> int:
    if dest.exists():
        orig_mode = dest.stat().st_mode & 0o777
        return 0o644 if orig_mode == 0o600 else orig_mode
    return 0o644


def _is_strict_https_url(value: object) -> bool:
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        return (
            parsed.scheme == "https"
            and bool(host)
            and "." in host
            and not host.startswith(".")
            and not host.endswith(".")
            and parsed.username is None
        )
    except ValueError:
        return False


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _extract_annual_fee_pcts(fee_text: str) -> list[float]:
    cleaned = FEE_EXCLUDE_SPAN_RE.sub("", fee_text)
    return [float(m.group(1)) for m in re.finditer(r"(\d+(?:\.\d+)?)%", cleaned)]


def _extract_dynamic_tokens(obj: object) -> set[str]:
    tokens: set[str] = set()
    for _, sval in _walk_json_strings(obj, ""):
        for m in DYNAMIC_SIGNED_PCT_RE.finditer(sval):
            tokens.add(m.group(0))
        for m in DYNAMIC_COUNT_RE.finditer(sval):
            tokens.add(re.sub(r"\s+", "", m.group(0)))
    return tokens


def _check_sibling_token_drift(
    obj_label: str,
    replaced_tokens: set[str],
    untouched_items: list[tuple[str, str]],
) -> None:
    if not replaced_tokens:
        return
    for field_path, sval in untouched_items:
        for tok in sorted(replaced_tokens):
            if tok.endswith("%"):
                pat = re.compile(rf"(?<![0-9A-Za-z%]){re.escape(tok)}")
            else:
                # Allow optional spaces between digits and 只
                m_cnt = re.fullmatch(r"(\d+)(.+)", tok)
                pat = re.compile(rf"(?<![0-9]){m_cnt.group(1)}\s*{re.escape(m_cnt.group(2))}") if m_cnt else re.compile(re.escape(tok))
            for m in pat.finditer(sval):
                win = sval[max(0, m.start() - 20) : min(len(sval), m.end() + 20)]
                if not HISTORICAL_CTX_RE.search(win):
                    raise ValueError(
                        f"Stale sibling token drift in {obj_label}.{field_path}: "
                        f"replaced token {tok!r} still appears without historical context -> {win!r}"
                    )


def _atomic_write_single(dest: Path, content: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    target_mode = _target_file_mode(dest)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, target_mode)
        os.replace(tmp_path, dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _atomic_write_transaction(writes: list[tuple[Path, bytes]]) -> None:
    """All-or-nothing transactional write across multiple target files with full rollback."""
    originals: list[tuple[Path, bytes]] = []
    for dest, _ in writes:
        originals.append((dest, dest.read_bytes()))

    staged: list[tuple[Path, Path, bytes]] = []
    replaced: list[tuple[Path, bytes]] = []
    try:
        # Phase 1: Stage and fsync every temp file in its target directory first.
        for (dest, new_bytes), (_, orig_bytes) in zip(writes, originals):
            dest.parent.mkdir(parents=True, exist_ok=True)
            target_mode = _target_file_mode(dest)
            fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(new_bytes)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.chmod(tmp_path, target_mode)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise
            staged.append((tmp_path, dest, orig_bytes))

        # Phase 2: Replace targets sequentially; roll back every replaced file on any failure.
        for tmp_path, dest, orig_bytes in staged:
            os.replace(tmp_path, dest)
            replaced.append((dest, orig_bytes))
    except Exception as exc:
        for tmp_path, _, _ in staged:
            tmp_path.unlink(missing_ok=True)
        rollback_errors: list[str] = []
        for dest, orig_bytes in reversed(replaced):
            try:
                _atomic_write_single(dest, orig_bytes)
            except Exception as rb_exc:
                rollback_errors.append(f"{dest.name}: {rb_exc}")
        if rollback_errors:
            raise RuntimeError(
                f"Atomic transaction failed ({exc}); rollback errors: {'; '.join(rollback_errors)}"
            ) from exc
        raise


def _merge_multi_asset(
    orig: dict[str, Any],
    patch_root: dict[str, Any],
    edition_id: str,
    as_of_date: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ma = copy.deepcopy(orig)
    ma["edition_id"] = edition_id
    ma["as_of_date"] = as_of_date
    if "as_of_label" in patch_root and patch_root["as_of_label"] is not None:
        if not isinstance(patch_root["as_of_label"], str) or not patch_root["as_of_label"].strip():
            raise ValueError("patch.as_of_label must be a non-empty string.")
        ma["as_of_label"] = patch_root["as_of_label"].strip()
    if "gold_mutex_note" in patch_root and patch_root["gold_mutex_note"] is not None:
        if not isinstance(patch_root["gold_mutex_note"], str) or not patch_root["gold_mutex_note"].strip():
            raise ValueError("patch.gold_mutex_note must be a non-empty string.")
        ma["gold_mutex_note"] = patch_root["gold_mutex_note"].strip()

    sec = patch_root.get("multi_asset_channels")
    stats: dict[str, Any] = {
        "top_keys_updated": 0,
        "channels_patched": 0,
        "products_upserted": 0,
        "untouched_channel_siblings": {},
    }
    if sec is None:
        return ma, stats
    if not isinstance(sec, dict):
        raise ValueError("patch.multi_asset_channels must be an object.")
    unknown_sec = set(sec.keys()) - {"top_level_updates", "channels_patch"}
    if unknown_sec:
        raise ValueError(f"Unknown key(s) in multi_asset_channels patch: {sorted(unknown_sec)}")

    top_upd = sec.get("top_level_updates")
    if top_upd is not None:
        if not isinstance(top_upd, dict):
            raise ValueError("multi_asset_channels.top_level_updates must be an object.")
        if "channels" in top_upd:
            raise ValueError("Use multi_asset_channels.channels_patch instead of replacing top-level 'channels'.")
        for k, v in top_upd.items():
            ma[k] = copy.deepcopy(v)
            stats["top_keys_updated"] += 1

    ch_patch = sec.get("channels_patch")
    if ch_patch is not None:
        if not isinstance(ch_patch, dict):
            raise ValueError("multi_asset_channels.channels_patch must be an object keyed by channel id.")
        channels = ma.get("channels")
        if not isinstance(channels, list):
            raise ValueError("multi_asset_channels.json missing 'channels' list.")
        by_id = {ch.get("id"): ch for ch in channels if isinstance(ch, dict) and isinstance(ch.get("id"), str)}
        for cid, upd in ch_patch.items():
            if cid not in REQUIRED_CHANNEL_SET:
                raise ValueError(f"Unknown channel id in channels_patch: {cid!r} (must be one of 12 standard IDs).")
            if cid not in by_id:
                raise ValueError(f"Channel {cid!r} not found in existing multi_asset_channels.json.")
            if not isinstance(upd, dict):
                raise ValueError(f"channels_patch[{cid!r}] must be an object.")
            target_ch = by_id[cid]
            orig_ch = copy.deepcopy(target_ch)
            old_tokens: set[str] = set()
            new_tokens: set[str] = set()
            touched_top_keys: set[str] = set()
            touched_product_fields: dict[str, set[str]] = {}
            stats["channels_patched"] += 1
            for k, v in upd.items():
                if k == "id":
                    if v != cid:
                        raise ValueError(f"Cannot change channel id {cid!r} -> {v!r}.")
                    continue
                if k == "products_upsert":
                    touched_top_keys.add("products")
                    if not isinstance(v, list):
                        raise ValueError(f"channels_patch[{cid!r}].products_upsert must be a list.")
                    prods = target_ch.setdefault("products", [])
                    if not isinstance(prods, list):
                        raise ValueError(f"Existing channel {cid!r}.products is not a list.")
                    for pi, p_upd in enumerate(v):
                        if not isinstance(p_upd, dict) or not isinstance(p_upd.get("code"), str) or not p_upd["code"].strip():
                            raise ValueError(
                                f"channels_patch[{cid!r}].products_upsert[{pi}] must be an object with non-empty 'code'."
                            )
                        p_key = p_upd["code"].strip().upper()
                        existing = next(
                            (p for p in prods if isinstance(p, dict) and str(p.get("code", "")).strip().upper() == p_key),
                            None,
                        )
                        if existing is not None:
                            p_touched = touched_product_fields.setdefault(p_key, set())
                            for pk, pv in p_upd.items():
                                if pk != "code":
                                    old_tokens |= _extract_dynamic_tokens(existing.get(pk))
                                    new_tokens |= _extract_dynamic_tokens(pv)
                                    p_touched.add(pk)
                                existing[pk] = copy.deepcopy(pv)
                        else:
                            for req_f in ("code", "name", "metric", "fee", "note"):
                                if not isinstance(p_upd.get(req_f), str) or not p_upd[req_f].strip():
                                    raise ValueError(
                                        f"New product in channels_patch[{cid!r}].products_upsert[{pi}] missing non-empty {req_f!r}."
                                    )
                            new_tokens |= _extract_dynamic_tokens(p_upd)
                            prods.append(copy.deepcopy(p_upd))
                        stats["products_upserted"] += 1
                elif k == "products_remove":
                    touched_top_keys.add("products")
                    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
                        raise ValueError(f"channels_patch[{cid!r}].products_remove must be a list of product codes.")
                    rem_keys = {x.strip().upper() for x in v}
                    prods = target_ch.get("products", [])
                    for p in prods:
                        if isinstance(p, dict) and str(p.get("code", "")).strip().upper() in rem_keys:
                            old_tokens |= _extract_dynamic_tokens(p)
                    target_ch["products"] = [
                        p for p in prods if not (isinstance(p, dict) and str(p.get("code", "")).strip().upper() in rem_keys)
                    ]
                else:
                    touched_top_keys.add(k)
                    old_tokens |= _extract_dynamic_tokens(orig_ch.get(k))
                    new_tokens |= _extract_dynamic_tokens(v)
                    target_ch[k] = copy.deepcopy(v)

            replaced_tokens = old_tokens - new_tokens
            untouched_strings: list[tuple[str, str]] = []
            for sk, sv in target_ch.items():
                if sk in CHANNEL_META_KEYS:
                    continue
                if sk not in touched_top_keys:
                    untouched_strings.extend(_walk_json_strings(sv, sk))
                elif sk == "products" and "products" not in upd and isinstance(sv, list):
                    for pi, prod in enumerate(sv):
                        if not isinstance(prod, dict):
                            continue
                        pk_norm = str(prod.get("code", "")).strip().upper()
                        t_fields = touched_product_fields.get(pk_norm)
                        if t_fields is None:
                            untouched_strings.extend(_walk_json_strings(prod, f"products[{pi}]"))
                        else:
                            for pf, pval in prod.items():
                                if pf != "code" and pf not in t_fields:
                                    untouched_strings.extend(_walk_json_strings(pval, f"products[{pi}].{pf}"))
            _check_sibling_token_drift(f"multi_asset_channels[{cid}]", replaced_tokens, untouched_strings)
            untouched_sibs = sorted(
                sk for sk in target_ch.keys() if sk not in touched_top_keys and sk not in CHANNEL_META_KEYS
            )
            stats["untouched_channel_siblings"][cid] = untouched_sibs

    return ma, stats


def _merge_etf_universe(
    orig: dict[str, Any],
    patch_root: dict[str, Any],
    edition_id: str,
    as_of_date: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    eu = copy.deepcopy(orig)
    eu["edition_id"] = edition_id
    eu["as_of_date"] = as_of_date
    eu["updated_at"] = as_of_date
    if "as_of_label" in patch_root and patch_root["as_of_label"] is not None:
        if not isinstance(patch_root["as_of_label"], str) or not patch_root["as_of_label"].strip():
            raise ValueError("patch.as_of_label must be a non-empty string.")
        eu["as_of_label"] = patch_root["as_of_label"].strip()
    if "gold_tier0_locked" in patch_root and patch_root["gold_tier0_locked"] is not None:
        if not isinstance(patch_root["gold_tier0_locked"], bool):
            raise ValueError("patch.gold_tier0_locked must be a boolean.")
        eu["gold_tier0_locked"] = patch_root["gold_tier0_locked"]
    if "gold_lock_notice" in patch_root and patch_root["gold_lock_notice"] is not None:
        if not isinstance(patch_root["gold_lock_notice"], str) or not patch_root["gold_lock_notice"].strip():
            raise ValueError("patch.gold_lock_notice must be a non-empty string.")
        eu["gold_lock_notice"] = patch_root["gold_lock_notice"].strip()

    etfs = eu.get("etfs")
    if not isinstance(etfs, list):
        raise ValueError("etf_universe.json missing 'etfs' list.")
    orig_count = len(etfs)

    stats = {"top_keys_updated": 0, "etfs_updated": 0, "etfs_added": 0, "etfs_removed": 0}
    sec = patch_root.get("etf_universe")
    if sec is not None:
        if not isinstance(sec, dict):
            raise ValueError("patch.etf_universe must be an object.")
        unknown_sec = set(sec.keys()) - {"top_level_updates", "etfs_upsert", "etfs_remove"}
        if unknown_sec:
            raise ValueError(f"Unknown key(s) in etf_universe patch: {sorted(unknown_sec)}")

        top_upd = sec.get("top_level_updates")
        if top_upd is not None:
            if not isinstance(top_upd, dict):
                raise ValueError("etf_universe.top_level_updates must be an object.")
            forbidden_top = {"etfs", "total_etfs", "counts_by_market", "counts_by_channel"}
            overlap = forbidden_top & set(top_upd.keys())
            if overlap:
                raise ValueError(f"Cannot override auto-managed etf_universe keys via top_level_updates: {sorted(overlap)}")
            for k, v in top_upd.items():
                eu[k] = copy.deepcopy(v)
                stats["top_keys_updated"] += 1

        # Process etfs_remove first
        rem_raw = sec.get("etfs_remove")
        if rem_raw is not None:
            if not isinstance(rem_raw, list) or not all(isinstance(c, str) and c.strip() for c in rem_raw):
                raise ValueError("etf_universe.etfs_remove must be a list of non-empty ETF code strings.")
            rem_norms = {_normalize_etf_code(c) for c in rem_raw}
            if len(rem_norms) > MAX_ETF_DELTA:
                raise ValueError(
                    f"etfs_remove attempts to remove {len(rem_norms)} ETFs (> safety limit {MAX_ETF_DELTA})."
                )
            existing_norms = {_normalize_etf_code(e.get("code")) for e in etfs if isinstance(e, dict)}
            missing_rem = sorted(rem_norms - existing_norms)
            if missing_rem:
                raise ValueError(f"etfs_remove references unknown ETF code(s): {missing_rem}")
            new_etfs: list[dict[str, Any]] = []
            for item in etfs:
                if isinstance(item, dict) and _normalize_etf_code(item.get("code")) in rem_norms:
                    stats["etfs_removed"] += 1
                    continue
                new_etfs.append(item)
            etfs = new_etfs
            eu["etfs"] = etfs

        # Process etfs_upsert (list of dicts, or dict keyed by code)
        ups_raw = sec.get("etfs_upsert")
        if ups_raw is not None:
            ups_list: list[dict[str, Any]] = []
            if isinstance(ups_raw, list):
                for idx, entry in enumerate(ups_raw):
                    if not isinstance(entry, dict) or not isinstance(entry.get("code"), str) or not entry["code"].strip():
                        raise ValueError(f"etf_universe.etfs_upsert[{idx}] must be an object with non-empty 'code'.")
                    ups_list.append(entry)
            elif isinstance(ups_raw, dict):
                for code_k, entry in ups_raw.items():
                    if not isinstance(entry, dict):
                        raise ValueError(f"etf_universe.etfs_upsert[{code_k!r}] must be an object.")
                    merged_e = dict(entry)
                    merged_e.setdefault("code", str(code_k))
                    ups_list.append(merged_e)
            else:
                raise ValueError("etf_universe.etfs_upsert must be a list of ETF objects (or object keyed by code).")

            index_by_norm: dict[str, dict[str, Any]] = {}
            for item in etfs:
                if isinstance(item, dict) and item.get("code"):
                    index_by_norm[_normalize_etf_code(item["code"])] = item

            for entry in ups_list:
                norm_code = _normalize_etf_code(entry["code"])
                if not norm_code:
                    raise ValueError(f"Invalid ETF code in etfs_upsert: {entry.get('code')!r}")
                if norm_code in index_by_norm:
                    target = index_by_norm[norm_code]
                    canonical_code = target["code"]
                    orig_etf = copy.deepcopy(target)
                    old_tokens: set[str] = set()
                    new_tokens: set[str] = set()
                    touched_keys: set[str] = set()
                    for k, v in entry.items():
                        if k == "code":
                            continue  # Preserve existing canonical code format
                        touched_keys.add(k)
                        old_tokens |= _extract_dynamic_tokens(orig_etf.get(k))
                        new_tokens |= _extract_dynamic_tokens(v)
                        target[k] = copy.deepcopy(v)
                    target["code"] = canonical_code
                    replaced_tokens = old_tokens - new_tokens
                    untouched_strings: list[tuple[str, str]] = []
                    for sk, sv in target.items():
                        if sk == "code" or sk in touched_keys:
                            continue
                        untouched_strings.extend(_walk_json_strings(sv, sk))
                    _check_sibling_token_drift(f"etf_universe[{canonical_code}]", replaced_tokens, untouched_strings)
                    stats["etfs_updated"] += 1
                else:
                    missing_keys = sorted(ETF_ALL_21_KEYS - set(entry.keys()))
                    extra_keys = sorted(set(entry.keys()) - ETF_ALL_21_KEYS)
                    if missing_keys:
                        raise ValueError(
                            f"New ETF {norm_code!r} in etfs_upsert must provide all 21 standard keys; missing: {missing_keys}"
                        )
                    if extra_keys:
                        raise ValueError(f"New ETF {norm_code!r} has unknown key(s): {extra_keys}")
                    new_item = copy.deepcopy(entry)
                    new_item["code"] = norm_code
                    etfs.append(new_item)
                    index_by_norm[norm_code] = new_item
                    stats["etfs_added"] += 1

    delta = len(etfs) - orig_count
    if abs(delta) > MAX_ETF_DELTA:
        raise ValueError(
            f"ETF universe net count change |{delta:+d}| exceeds safety limit ({MAX_ETF_DELTA}); "
            f"orig={orig_count}, new={len(etfs)}."
        )

    # Recompute exact summary counters preserving existing key order
    mkt_counter: Counter[str] = Counter()
    ch_counter: Counter[str] = Counter()
    for item in etfs:
        if isinstance(item, dict):
            mv = str(item.get("market", "")).strip()
            cv = str(item.get("channel", "")).strip()
            if mv:
                mkt_counter[mv] += 1
            if cv:
                ch_counter[cv] += 1

    orig_mkt_order = list((orig.get("counts_by_market") or {}).keys())
    orig_ch_order = list((orig.get("counts_by_channel") or {}).keys())
    eu["total_etfs"] = len(etfs)
    eu["counts_by_market"] = {
        k: mkt_counter[k] for k in dict.fromkeys([*orig_mkt_order, *mkt_counter.keys()]) if mkt_counter.get(k, 0) > 0
    }
    eu["counts_by_channel"] = {
        k: ch_counter[k] for k in dict.fromkeys([*orig_ch_order, *ch_counter.keys()]) if ch_counter.get(k, 0) > 0
    }
    return eu, stats


def _build_ah_twin_map(
    market_state: dict[str, Any] | None,
    dossiers: dict[str, Any],
) -> dict[str, tuple[str, float]]:
    twin_map: dict[str, tuple[str, float]] = {}
    if not isinstance(market_state, dict):
        return twin_map
    benchmarks = (
        market_state.get("cross_market_linkages", {})
        .get("ah_premium_radar", {})
        .get("benchmarks")
    )
    if not isinstance(benchmarks, list):
        return twin_map
    for b in benchmarks:
        if not isinstance(b, dict):
            continue
        a_code = b.get("a")
        h_code = b.get("h")
        ah_pct = b.get("ah_premium_pct")
        if (
            not isinstance(a_code, str) or not a_code.strip()
            or not isinstance(h_code, str) or not h_code.strip()
            or not isinstance(ah_pct, (int, float)) or isinstance(ah_pct, bool)
        ):
            continue
        ak = f"a-share:{a_code.strip()}"
        hk = f"hk-stock:{h_code.strip()}"
        if ak in dossiers and hk in dossiers:
            pct = float(ah_pct)
            twin_map[ak] = (hk, pct)
            twin_map[hk] = (ak, pct)
    return twin_map


def _merge_deep_dossiers(
    orig: dict[str, Any],
    patch_root: dict[str, Any],
    edition_id: str,
    as_of_date: str,
    *,
    market_state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    dd = copy.deepcopy(orig)
    dd["edition_id"] = edition_id
    dd["as_of_date"] = as_of_date
    dd["updated_at"] = as_of_date

    dossiers = dd.get("dossiers")
    if not isinstance(dossiers, dict):
        raise ValueError("deep_dossiers.json missing 'dossiers' object.")

    twin_map = _build_ah_twin_map(market_state, dossiers)
    stats: dict[str, Any] = {
        "top_keys_updated": 0,
        "stocks_patched": 0,
        "unpatched_ah_twins": {},
    }
    sec = patch_root.get("deep_dossiers")
    if sec is not None:
        if not isinstance(sec, dict):
            raise ValueError("patch.deep_dossiers must be an object.")
        unknown_sec = set(sec.keys()) - {"top_level_updates", "dossiers_patch"}
        if unknown_sec:
            raise ValueError(f"Unknown key(s) in deep_dossiers patch: {sorted(unknown_sec)}")

        top_upd = sec.get("top_level_updates")
        if top_upd is not None:
            if not isinstance(top_upd, dict):
                raise ValueError("deep_dossiers.top_level_updates must be an object.")
            forbidden_top = {"dossiers", "total_stocks", "core_deep_count", "standard_deep_count"}
            overlap = forbidden_top & set(top_upd.keys())
            if overlap:
                raise ValueError(
                    f"Cannot override auto-managed deep_dossiers keys via top_level_updates: {sorted(overlap)}"
                )
            for k, v in top_upd.items():
                dd[k] = copy.deepcopy(v)
                stats["top_keys_updated"] += 1

        dp = sec.get("dossiers_patch")
        if dp is not None:
            if not isinstance(dp, dict):
                raise ValueError("deep_dossiers.dossiers_patch must be an object keyed by stock key.")
            for stock_key, upd in dp.items():
                if stock_key not in dossiers:
                    raise ValueError(
                        f"dossiers_patch key {stock_key!r} is not in the existing stock pool (strictly forbidden to add/rename pool keys)."
                    )
                if not isinstance(upd, dict) or not upd:
                    raise ValueError(f"dossiers_patch[{stock_key!r}] must be a non-empty object.")
                target = dossiers[stock_key]
                for k, v in upd.items():
                    if k in ("market", "code") and v != target.get(k):
                        raise ValueError(f"Cannot mutate immutable {k!r} on dossier {stock_key!r}.")
                    target[k] = copy.deepcopy(v)
                target["updated_at"] = as_of_date
                stats["stocks_patched"] += 1

            # A/H Twin Sync Guard: if baseline_note or valuation_anchor changed on one side,
            # ensure its unpatched A/H twin does not drift >1.5pct from market_state benchmark.
            for stock_key, upd in dp.items():
                if not isinstance(upd, dict):
                    continue
                if "baseline_note" not in upd and "valuation_anchor" not in upd:
                    continue
                twin_info = twin_map.get(stock_key)
                if twin_info is None:
                    continue
                twin_key, bench_pct = twin_info
                if twin_key in dp:
                    continue
                stats["unpatched_ah_twins"][stock_key] = twin_key
                twin_entry = dossiers.get(twin_key)
                if not isinstance(twin_entry, dict):
                    continue
                for field in ("baseline_note", "valuation_anchor"):
                    fval = str(twin_entry.get(field, ""))
                    for m_ah in AH_PREMIUM_MENTION_RE.finditer(fval):
                        v1 = float(m_ah.group(1))
                        v2 = float(m_ah.group(2)) if m_ah.group(2) is not None else v1
                        lo, hi = min(v1, v2), max(v1, v2)
                        if bench_pct < lo - 1.5 or bench_pct > hi + 1.5:
                            raise ValueError(
                                f"A/H twin sync required: patched {stock_key!r} without twin {twin_key!r}, "
                                f"whose {field} still states {m_ah.group(0)!r} vs market_state benchmark "
                                f"{bench_pct:+.1f}% (drift > 1.5pct)."
                            )

    dd["total_stocks"] = len(dossiers)
    dd["core_deep_count"] = sum(
        1 for entry in dossiers.values() if isinstance(entry, dict) and entry.get("depth_tier") == "core_deep"
    )
    dd["standard_deep_count"] = dd["total_stocks"] - dd["core_deep_count"]
    return dd, stats


def _validate_merged_equity_dbs(
    ma: dict[str, Any],
    eu: dict[str, Any],
    dd: dict[str, Any],
    *,
    edition_id: str,
    gold_tier0_active: bool,
    expected_pool: int,
) -> list[str]:
    errs: list[str] = []

    # 1. Edition ID alignment
    for name, doc in (
        ("multi_asset_channels.json", ma),
        ("etf_universe.json", eu),
        ("deep_dossiers.json", dd),
    ):
        if doc.get("edition_id") != edition_id:
            errs.append(f"{name}: edition_id ({doc.get('edition_id')!r}) != {edition_id!r}")

    # 2. Validate multi_asset_channels (12 channels, products, rules, template weights=100%, restricted codes, leaks)
    channels = ma.get("channels")
    if not isinstance(channels, list):
        errs.append("multi_asset_channels.json: channels must be a list.")
    else:
        seen_cids: set[str] = set()
        for idx, ch in enumerate(channels):
            if not isinstance(ch, dict):
                errs.append(f"multi_asset_channels.json: channels[{idx}] must be an object.")
                continue
            cid = str(ch.get("id", "")).strip()
            if not cid:
                errs.append(f"multi_asset_channels.json: channels[{idx}] missing non-empty id.")
                continue
            if cid in seen_cids:
                errs.append(f"multi_asset_channels.json: duplicate channel id {cid!r}.")
            seen_cids.add(cid)
            for req_s in ("name", "beginner_one_liner", "today_alert"):
                if not isinstance(ch.get(req_s), str) or not ch[req_s].strip():
                    errs.append(f"multi_asset_channels.json: channel {cid} missing non-empty {req_s}.")
            if ch.get("status_tone") not in ALLOWED_STATUS_TONES:
                errs.append(f"multi_asset_channels.json: channel {cid} invalid status_tone {ch.get('status_tone')!r}.")
            kms = ch.get("key_metrics")
            if not isinstance(kms, list) or not kms:
                errs.append(f"multi_asset_channels.json: channel {cid} missing non-empty key_metrics.")
            else:
                for ki, km in enumerate(kms):
                    if (
                        not isinstance(km, dict)
                        or not isinstance(km.get("label"), str) or not km["label"].strip()
                        or not isinstance(km.get("value"), str) or not km["value"].strip()
                    ):
                        errs.append(f"multi_asset_channels.json: channel {cid}.key_metrics[{ki}] missing label/value.")
            prods = ch.get("products")
            if not isinstance(prods, list) or not prods:
                errs.append(f"multi_asset_channels.json: channel {cid} missing non-empty products.")
            else:
                for pi, prod in enumerate(prods):
                    if not isinstance(prod, dict):
                        errs.append(f"multi_asset_channels.json: channel {cid}.products[{pi}] must be an object.")
                        continue
                    for pf in ("code", "name", "metric", "fee", "note"):
                        if not isinstance(prod.get(pf), str) or not prod[pf].strip():
                            errs.append(f"multi_asset_channels.json: channel {cid}.products[{pi}] missing non-empty {pf}.")
                    pcode = str(prod.get("code", ""))
                    if RESTRICTED_CODES_RE.search(pcode):
                        ctx = f"{prod.get('name', '')} {prod.get('note', '')}"
                        if not RESTRICTED_WARN_RE.search(ctx):
                            errs.append(
                                f"multi_asset_channels.json: channel {cid}.products[{pi}] restricted code {pcode!r} lacks warning."
                            )
                    if gold_tier0_active:
                        pnorm = _normalize_etf_code(pcode)
                        pname = str(prod.get("name", ""))
                        pnote = str(prod.get("note", ""))
                        if pnorm in GOLD_ETF_CODES or GOLD_ETF_NAME_RE.search(pname):
                            if not re.search(r"(?:红灯|暂不|暂停|严禁|禁止|锁)", pnote + pname):
                                errs.append(
                                    f"Gold Tier-0 互斥冲突 (multi_asset_channels:{pnorm or pname})：涉金产品须显式注明红灯暂停新买锁"
                                )
            rules = ch.get("rules_and_redlines")
            if not isinstance(rules, list) or not rules or any(not isinstance(r, str) or not r.strip() for r in rules):
                errs.append(f"multi_asset_channels.json: channel {cid} missing non-empty rules_and_redlines.")

        missing_ch = [c for c in REQUIRED_MULTI_ASSET_CHANNELS if c not in seen_cids]
        if missing_ch:
            errs.append(f"multi_asset_channels.json: missing required channels {missing_ch}.")

    templates = ma.get("allocation_templates")
    if templates is not None:
        if not isinstance(templates, list):
            errs.append("multi_asset_channels.json: allocation_templates must be a list.")
        else:
            for ti, tpl in enumerate(templates):
                if not isinstance(tpl, dict) or not isinstance(tpl.get("slices"), list) or not tpl["slices"]:
                    errs.append(f"multi_asset_channels.json: allocation_templates[{ti}] missing non-empty slices.")
                    continue
                exact_pcts: list[float] = []
                has_range = False
                for sl in tpl["slices"]:
                    if not isinstance(sl, dict):
                        continue
                    w = str(sl.get("weight", "")).strip()
                    m_ex = EXACT_PCT_RE.fullmatch(w)
                    if m_ex:
                        exact_pcts.append(float(m_ex.group(1)))
                    elif RANGE_PCT_RE.search(w):
                        has_range = True
                if len(exact_pcts) >= 2 and not has_range and abs(sum(exact_pcts) - 100.0) > 0.01:
                    errs.append(
                        f"multi_asset_channels.json: allocation_templates[{ti}]({tpl.get('id')}) "
                        f"exact weights sum={sum(exact_pcts):.2f}% != 100%."
                    )

    # 3. Validate etf_universe (>= 140 ETFs, unique codes, valid enums, zero markup, Gold Tier-0 lock)
    if gold_tier0_active and eu.get("gold_tier0_locked") is not True:
        errs.append("etf_universe.json: gold_tier0_locked must be true while Gold is Tier 0 / new_buy_allowed=false.")
    etfs = eu.get("etfs")
    if not isinstance(etfs, list):
        errs.append("etf_universe.json: etfs must be a list.")
    else:
        if len(etfs) < MIN_ETF_COUNT:
            errs.append(f"etf_universe.json: ETF count {len(etfs)} < {MIN_ETF_COUNT}.")
        if eu.get("total_etfs") != len(etfs):
            errs.append(f"etf_universe.json: total_etfs ({eu.get('total_etfs')}) != len(etfs) ({len(etfs)}).")
        seen_etf_codes: set[str] = set()
        etf_fee_map: dict[str, float] = {}
        for idx, item in enumerate(etfs):
            if not isinstance(item, dict):
                errs.append(f"etf_universe.json: etfs[{idx}] must be an object.")
                continue
            code = str(item.get("code", "")).strip()
            norm = _normalize_etf_code(code)
            if not norm:
                errs.append(f"etf_universe.json: etfs[{idx}] missing non-empty code.")
            elif norm in seen_etf_codes:
                errs.append(f"etf_universe.json: duplicate normalized ETF code {norm!r}.")
            else:
                seen_etf_codes.add(norm)
            for field in ETF_REQUIRED_STR_FIELDS:
                val = item.get(field)
                if not isinstance(val, str) or not val.strip():
                    errs.append(f"etf_universe.json: etfs[{idx}]({code}) missing non-empty {field}.")
                elif RAW_MARKUP_RE.search(val):
                    errs.append(f"etf_universe.json: etfs[{idx}]({code}).{field} contains raw Markdown/HTML markup.")
            fee_num = item.get("fee_num")
            if isinstance(fee_num, (int, float)) and not isinstance(fee_num, bool):
                fee_num_f = float(fee_num)
                if norm:
                    etf_fee_map[norm] = fee_num_f
                fee_total = str(item.get("fee_total_pct", "")).strip()
                m_ft = re.match(r"^(\d+(?:\.\d+)?)%", fee_total)
                if m_ft and abs(float(m_ft.group(1)) - fee_num_f) > 0.005:
                    errs.append(
                        f"etf_universe.json: etfs[{idx}]({code}) fee_total_pct ({fee_total!r}) != fee_num ({fee_num})."
                    )
            mkt = str(item.get("market", "")).strip()
            if mkt not in ETF_ALLOWED_MARKETS:
                errs.append(f"etf_universe.json: etfs[{idx}]({code}) invalid market {mkt!r}.")
            ch = str(item.get("channel", "")).strip()
            if ch not in ETF_ALLOWED_CHANNELS:
                errs.append(f"etf_universe.json: etfs[{idx}]({code}) invalid channel {ch!r}.")
            if "premium_status" in item and item["premium_status"] not in ETF_ALLOWED_PREMIUM_STATUSES:
                errs.append(f"etf_universe.json: etfs[{idx}]({code}) invalid premium_status {item['premium_status']!r}.")
            if gold_tier0_active:
                name = str(item.get("name", "")).strip()
                is_gold = item.get("gold_locked") is True or norm in GOLD_ETF_CODES or bool(GOLD_ETF_NAME_RE.search(name))
                if is_gold:
                    role = str(item.get("action_role", "")).strip()
                    if not role or GOLD_ETF_FORBIDDEN_ROLE_RE.search(role):
                        errs.append(
                            f"Gold Tier-0 互斥冲突 (etf_universe:{code})：黄金/金矿 ETF 严禁标为底座/买入/推荐/定投/配置 -> {role!r}"
                        )

        # Cross-DB ETF Fee Consistency: multi_asset_channels.json x etf_universe.json
        if isinstance(channels, list) and etf_fee_map:
            for ch_obj in channels:
                if not isinstance(ch_obj, dict):
                    continue
                cid = str(ch_obj.get("id", "")).strip()
                prods = ch_obj.get("products")
                if not isinstance(prods, list):
                    continue
                for pi, prod in enumerate(prods):
                    if not isinstance(prod, dict):
                        continue
                    pcode = str(prod.get("code", ""))
                    pfee = str(prod.get("fee", ""))
                    matched: dict[str, float] = {}
                    for tok in re.findall(r"[A-Za-z0-9.]+", pcode):
                        nt = _normalize_etf_code(tok)
                        if nt in etf_fee_map:
                            matched[nt] = etf_fee_map[nt]
                    if not matched:
                        continue
                    parsed_fees = _extract_annual_fee_pcts(pfee)
                    if len(matched) == 1:
                        only_code, ssot_fee = next(iter(matched.items()))
                        if parsed_fees and abs(parsed_fees[0] - ssot_fee) > 0.005:
                            errs.append(
                                f"multi_asset_channels.json: channel {cid}.products[{pi}]({pcode}) "
                                f"fee {pfee!r} ({parsed_fees[0]:.2f}%) != etf_universe {only_code} ({ssot_fee:.2f}%)."
                            )
                    else:
                        lo_fee = min(matched.values())
                        hi_fee = max(matched.values())
                        if hi_fee - lo_fee > 0.05:
                            if len(parsed_fees) < 2 or min(parsed_fees) > lo_fee + 0.005 or max(parsed_fees) < hi_fee - 0.005:
                                errs.append(
                                    f"multi_asset_channels.json: channel {cid}.products[{pi}]({pcode}) "
                                    f"lists ETFs with distinct fees {matched} ({lo_fee:.2f}%..{hi_fee:.2f}%), "
                                    f"but fee {pfee!r} does not disclose both or a covering range."
                                )
                        elif parsed_fees and (parsed_fees[0] < lo_fee - 0.005 or parsed_fees[0] > hi_fee + 0.005):
                            errs.append(
                                f"multi_asset_channels.json: channel {cid}.products[{pi}]({pcode}) "
                                f"fee {pfee!r} ({parsed_fees[0]:.2f}%) != etf_universe {matched}."
                            )

    # 4. Validate deep_dossiers (expected_pool stocks, all 7 dims non-empty, zero markup, anti-template, Gold Tier-0)
    dossiers = dd.get("dossiers")
    if not isinstance(dossiers, dict):
        errs.append("deep_dossiers.json: dossiers must be an object.")
    else:
        if len(dossiers) != expected_pool:
            errs.append(f"deep_dossiers.json: stock count {len(dossiers)} != expected pool {expected_pool}.")
        if dd.get("total_stocks") != len(dossiers):
            errs.append(f"deep_dossiers.json: total_stocks ({dd.get('total_stocks')}) != len(dossiers) ({len(dossiers)}).")
        tpl_counts: dict[tuple[str, str], Counter[str]] = {}
        for dkey, entry in dossiers.items():
            if not isinstance(entry, dict):
                errs.append(f"deep_dossiers.json[{dkey}] must be an object.")
                continue
            mkt_prefix = str(dkey).split(":", 1)[0]
            for dim in DOSSIER_DIMENSIONS:
                val = entry.get(dim)
                if not isinstance(val, str) or not val.strip():
                    errs.append(f"deep_dossiers.json[{dkey}] missing non-empty {dim}.")
                    continue
                if RAW_MARKUP_RE.search(val):
                    errs.append(f"deep_dossiers.json[{dkey}].{dim} contains raw Markdown/HTML markup.")
                if dim in ("catalysts", "bear_case"):
                    norm_txt = re.sub(r"\s+", " ", val.strip())
                    tpl_counts.setdefault((mkt_prefix, dim), Counter())[norm_txt] += 1
            if gold_tier0_active:
                is_gold_stock = dkey in GOLD_DOSSIER_KEYS or bool(GOLD_MINER_TICKERS_RE.search(dkey))
                if is_gold_stock:
                    act = str(entry.get("action_etf", ""))
                    for m_base in GOLD_BASE_ROLE_RE.finditer(act):
                        prefix = re.split(r"[。！？；，,、|]", act[: m_base.start()])[-1]
                        if not GOLD_BASE_NEGATION_RE.search(prefix):
                            errs.append(
                                f"Gold Tier-0 互斥冲突 (deep_dossiers:{dkey}.action_etf)：涉金标的严禁标为绿色/当下底座 -> {act[:72]}"
                            )
                            break
        for (mkt_prefix, dim), counter in sorted(tpl_counts.items()):
            for sample, cnt in counter.items():
                if cnt > 10:
                    errs.append(
                        f"deep_dossiers.json ({mkt_prefix}): {cnt} stocks duplicate identical {dim} template (>10) -> {sample[:40]!r}"
                    )

    # 5. Global string scan across all 3 DBs: raw markup, banned internal words, local paths, restricted codes, gold buy
    for doc_name, doc_obj in (
        ("multi_asset_channels.json", ma),
        ("etf_universe.json", eu),
        ("deep_dossiers.json", dd),
    ):
        for jpath, sval in _walk_json_strings(doc_obj, doc_name):
            if RAW_MARKUP_RE.search(sval):
                errs.append(f"{jpath}: contains raw Markdown/HTML markup.")
            hits = BANNED_INTERNAL_RE.findall(sval)
            if hits:
                errs.append(f"{jpath}: leaked internal term(s): {sorted(set(hits))}")
            if LOCAL_PATH_RE.search(sval):
                errs.append(f"{jpath}: leaked local filesystem path.")
            if not jpath.endswith(".code"):
                for m_rc in RESTRICTED_CODES_RE.finditer(sval):
                    win = sval[max(0, m_rc.start() - 40) : min(len(sval), m_rc.end() + 40)]
                    if not RESTRICTED_WARN_RE.search(win):
                        errs.append(
                            f"{jpath}: restricted code {m_rc.group(0)} mentioned without warning within ±40 chars -> {win!r}"
                        )
                        break
            if gold_tier0_active:
                errs.extend(_scan_text_for_gold_buy(jpath, sval))

    return errs


def apply_equity_patch(
    repo_root: Path = REPO_ROOT,
    *,
    dry_run: bool = False,
    keep_patch: bool = False,
    skip_edition_lock: bool = False,
) -> dict[str, Any]:
    patch_path = _safe_repo_path(repo_root, "equity", "state", "_edition_patch.json")
    ma_path = _safe_repo_path(repo_root, "equity", "state", "multi_asset_channels.json")
    eu_path = _safe_repo_path(repo_root, "equity", "state", "etf_universe.json")
    dd_path = _safe_repo_path(repo_root, "equity", "state", "deep_dossiers.json")
    gold_path = _safe_repo_path(repo_root, "gold", "data_snapshot.json")
    state_path = _safe_repo_path(repo_root, "equity", "state", "market_state.json")

    patch_root = _read_json_obj(patch_path, "equity/state/_edition_patch.json")
    unknown_top = set(patch_root.keys()) - ALLOWED_EQUITY_PATCH_TOP_KEYS
    if unknown_top:
        raise ValueError(f"Unknown top-level key(s) in _edition_patch.json: {sorted(unknown_top)}")

    edition_id = _validate_edition_id(patch_root.get("edition_id"))
    as_of_date = (
        _validate_date(patch_root["as_of_date"], "as_of_date")
        if patch_root.get("as_of_date") is not None
        else edition_id[:10]
    )

    gold_snap: dict[str, Any] | None = None
    if gold_path.is_file():
        gold_snap = _read_json_obj(gold_path, "gold/data_snapshot.json")
    elif not skip_edition_lock:
        raise ValueError("Missing gold/data_snapshot.json for edition lock and Gold Tier-0 mirror verification.")

    market_state: dict[str, Any] | None = None
    if state_path.is_file():
        market_state = _read_json_obj(state_path, "equity/state/market_state.json")
    elif not skip_edition_lock:
        raise ValueError("Missing equity/state/market_state.json for edition lock verification.")

    if not skip_edition_lock:
        assert gold_snap is not None and market_state is not None
        if gold_snap.get("edition_id") != edition_id:
            raise ValueError(
                f"Edition lock mismatch: patch edition_id ({edition_id!r}) != gold/data_snapshot.json ({gold_snap.get('edition_id')!r})."
            )
        if market_state.get("edition_id") != edition_id:
            raise ValueError(
                f"Edition lock mismatch: patch edition_id ({edition_id!r}) != equity/state/market_state.json ({market_state.get('edition_id')!r})."
            )

    orig_ma = _read_json_obj(ma_path, "equity/state/multi_asset_channels.json")
    orig_eu = _read_json_obj(eu_path, "equity/state/etf_universe.json")
    orig_dd = _read_json_obj(dd_path, "equity/state/deep_dossiers.json")

    if gold_snap is not None:
        gold_tier0_active = (
            str(gold_snap.get("tier_code", "")).strip() == "Tier 0" or gold_snap.get("new_buy_allowed") is False
        )
    else:
        gold_tier0_active = bool(patch_root.get("gold_tier0_locked", orig_eu.get("gold_tier0_locked", True)))

    expected_pool = 231
    if isinstance(market_state, dict) and isinstance(market_state.get("markets"), dict):
        counts = [
            market_state["markets"][m].get("stock_pool_count")
            for m in ("a_share", "hk_stock", "us_stock")
            if isinstance(market_state["markets"].get(m), dict)
        ]
        if len(counts) == 3 and all(type(c) is int and c > 0 for c in counts):
            expected_pool = sum(counts)

    merged_ma, ma_stats = _merge_multi_asset(orig_ma, patch_root, edition_id, as_of_date)
    merged_eu, eu_stats = _merge_etf_universe(orig_eu, patch_root, edition_id, as_of_date)
    merged_dd, dd_stats = _merge_deep_dossiers(
        orig_dd,
        patch_root,
        edition_id,
        as_of_date,
        market_state=market_state,
    )

    untouched_channel_siblings = ma_stats.pop("untouched_channel_siblings", {})
    unpatched_ah_twins = dd_stats.pop("unpatched_ah_twins", {})

    # Mirror live Gold Tier-0 status if patch did not explicitly override
    if gold_snap is not None and "gold_tier0_locked" not in patch_root:
        merged_eu["gold_tier0_locked"] = gold_tier0_active

    errors = _validate_merged_equity_dbs(
        merged_ma,
        merged_eu,
        merged_dd,
        edition_id=edition_id,
        gold_tier0_active=gold_tier0_active,
        expected_pool=expected_pool,
    )
    if errors:
        preview = "\n  - ".join(errors[:20])
        more = f"\n  ... (+{len(errors) - 20} more)" if len(errors) > 20 else ""
        raise ValueError(f"Pre-write validation failed ({len(errors)} error(s)):\n  - {preview}{more}")

    writes = [
        (ma_path, _serialize_json(merged_ma)),
        (eu_path, _serialize_json(merged_eu)),
        (dd_path, _serialize_json(merged_dd)),
    ]

    summary = {
        "mode": "apply",
        "dry_run": dry_run,
        "edition_id": edition_id,
        "as_of_date": as_of_date,
        "gold_tier0_active": gold_tier0_active,
        "multi_asset_channels": {**ma_stats, "total_channels": len(merged_ma["channels"])},
        "etf_universe": {**eu_stats, "total_etfs": merged_eu["total_etfs"]},
        "deep_dossiers": {
            **dd_stats,
            "total_stocks": merged_dd["total_stocks"],
            "core_deep_count": merged_dd["core_deep_count"],
        },
        "review_hints": {
            "untouched_channel_siblings": untouched_channel_siblings,
            "unpatched_ah_twins": unpatched_ah_twins,
        },
        "patch_deleted": False,
    }

    if not dry_run:
        _atomic_write_transaction(writes)
        if not keep_patch:
            patch_path.unlink(missing_ok=True)
            summary["patch_deleted"] = True

    return summary


def _nonblank_lines(raw: bytes) -> list[bytes]:
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return [line for line in normalized.split(b"\n") if line.strip()]


def _preserves_order(prior: list[bytes], candidate: list[bytes]) -> bool:
    remaining = iter(candidate)
    return all(line in remaining for line in prior)


def _insert_before_anchor(
    text: str,
    anchor: str,
    block: str,
    *,
    file_label: str,
    allow_rollover_fallback: bool = False,
) -> str:
    clean_block = block.strip()
    if not clean_block:
        raise ValueError(f"{file_label}: insertion block must be non-empty.")
    lines = clean_block.splitlines()
    ends_with_hr = bool(lines and lines[-1].strip() == "---")
    sep = "\n\n" if ends_with_hr else "\n\n---\n\n"

    idx = text.find(anchor)
    if idx >= 0:
        prefix = text[:idx]
        suffix = text[idx:]
        if prefix and not prefix.endswith("\n\n"):
            prefix = prefix.rstrip("\n") + "\n\n"
        return f"{prefix}{clean_block}{sep}{suffix}"

    if not allow_rollover_fallback:
        raise ValueError(f"{file_label}: anchor {anchor!r} not found; cannot safely prepend.")

    # Monthly-rollover fallback: insert after first '---' separator, or after the first '# ...' heading block.
    m_hr = re.search(r"(?:^|\n)[ \t]*---[ \t]*(?:\n|$)", text)
    if m_hr is not None:
        prefix = text[: m_hr.end()].rstrip("\n") + "\n\n"
        suffix = text[m_hr.end() :]
        if suffix.strip():
            return f"{prefix}{clean_block}{sep}{suffix.lstrip(chr(10))}"
        return f"{prefix}{clean_block}\n"

    m_h1 = re.search(r"(?:^|\n)#+ [^\n]*(?:\n|$)", text)
    if m_h1 is not None:
        pos = m_h1.end()
        tail = text[pos:]
        # Keep any immediately contiguous intro blockquote / blank lines attached to the H1 header.
        offset = 0
        for raw_ln in tail.splitlines(keepends=True):
            stripped = raw_ln.strip()
            if stripped == "" or stripped.startswith(">"):
                offset += len(raw_ln)
            else:
                break
        split_at = pos + offset
        prefix = text[:split_at].rstrip("\n") + "\n\n---\n\n"
        suffix = text[split_at:]
        if suffix.strip():
            return f"{prefix}{clean_block}{sep}{suffix.lstrip(chr(10))}"
        return f"{prefix}{clean_block}\n"

    raise ValueError(
        f"{file_label}: anchor {anchor!r} not found and no '---' or heading block available for monthly-rollover fallback."
    )


def _validate_gold_edition_review(
    review_obj: object,
    edition_id: str,
    gold_snap: dict[str, Any] | None,
) -> None:
    if not isinstance(review_obj, dict):
        raise ValueError("audit_review_block_md GOLD_EDITION_REVIEW must be a JSON object.")
    if review_obj.get("edition_id") != edition_id:
        raise ValueError(
            f"audit_review_block_md GOLD_EDITION_REVIEW.edition_id ({review_obj.get('edition_id')!r}) != {edition_id!r}."
        )
    as_of_short = review_obj.get("as_of_short")
    if not isinstance(as_of_short, str) or not AS_OF_SHORT_RE.fullmatch(as_of_short):
        raise ValueError(
            f"GOLD_EDITION_REVIEW.as_of_short must match YYYY-MM-DD HH:MM, got {as_of_short!r}."
        )
    try:
        datetime.strptime(as_of_short, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ValueError(f"GOLD_EDITION_REVIEW.as_of_short invalid timestamp {as_of_short!r}: {exc}") from exc
    if isinstance(gold_snap, dict) and gold_snap.get("edition_id") == edition_id:
        snap_as_of = gold_snap.get("as_of_short")
        if snap_as_of != as_of_short:
            raise ValueError(
                f"GOLD_EDITION_REVIEW.as_of_short ({as_of_short!r}) != gold/data_snapshot.json as_of_short ({snap_as_of!r})."
            )

    note = review_obj.get("note")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("GOLD_EDITION_REVIEW.note must be a non-empty string.")

    sources = review_obj.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("GOLD_EDITION_REVIEW.sources must be an object containing all 4 entry gates.")
    for gate_id in ENTRY_GATE_IDS:
        links = sources.get(gate_id)
        if not isinstance(links, list) or not links or not all(_is_strict_https_url(link) for link in links):
            raise ValueError(
                f"GOLD_EDITION_REVIEW.sources[{gate_id!r}] must be a non-empty list of strict https:// URLs."
            )

    forecast = review_obj.get("forecast_review")
    if not isinstance(forecast, dict):
        raise ValueError("GOLD_EDITION_REVIEW.forecast_review must be a JSON object.")
    fc_status = forecast.get("status")
    if fc_status not in ALLOWED_FORECAST_REVIEW_STATUSES:
        raise ValueError(
            f"GOLD_EDITION_REVIEW.forecast_review.status must be one of {sorted(ALLOWED_FORECAST_REVIEW_STATUSES)}, got {fc_status!r}."
        )
    fc_note = forecast.get("note")
    if not isinstance(fc_note, str) or not fc_note.strip():
        raise ValueError("GOLD_EDITION_REVIEW.forecast_review.note must be a non-empty string.")
    fc_sources = forecast.get("sources")
    if not isinstance(fc_sources, list) or not all(_is_strict_https_url(link) for link in fc_sources):
        raise ValueError("GOLD_EDITION_REVIEW.forecast_review.sources must be a list of strict https:// URLs.")
    if fc_status == "settled" and not fc_sources:
        raise ValueError("GOLD_EDITION_REVIEW.forecast_review.sources must be non-empty when status == 'settled'.")


def prepend_gold_ledgers(
    repo_root: Path = REPO_ROOT,
    *,
    dry_run: bool = False,
    keep_patch: bool = False,
) -> dict[str, Any]:
    patch_path = _safe_repo_path(repo_root, "gold", "daily", "_ledger_patch.json")
    changelog_path = _safe_repo_path(repo_root, "gold", "daily", "CHANGELOG.md")
    audit_path = _safe_repo_path(repo_root, "gold", "daily", "AUDIT_LOG.md")
    gold_snap_path = _safe_repo_path(repo_root, "gold", "data_snapshot.json")

    patch = _read_json_obj(patch_path, "gold/daily/_ledger_patch.json")
    unknown = set(patch.keys()) - ALLOWED_LEDGER_PATCH_KEYS
    if unknown:
        raise ValueError(f"Unknown key(s) in _ledger_patch.json: {sorted(unknown)}")

    edition_id = _validate_edition_id(patch.get("edition_id"))
    changelog_entry = patch.get("changelog_entry_md")
    audit_review_block = patch.get("audit_review_block_md")
    audit_source_index = patch.get("audit_source_index_md")

    if not isinstance(changelog_entry, str) or not changelog_entry.strip():
        raise ValueError("_ledger_patch.json requires non-empty 'changelog_entry_md'.")
    if not isinstance(audit_review_block, str) or not audit_review_block.strip():
        raise ValueError("_ledger_patch.json requires non-empty 'audit_review_block_md'.")
    if audit_source_index is not None and (not isinstance(audit_source_index, str) or not audit_source_index.strip()):
        raise ValueError("_ledger_patch.json 'audit_source_index_md' must be null or a non-empty string.")

    for label, sval in (
        ("changelog_entry_md", changelog_entry),
        ("audit_review_block_md", audit_review_block),
        ("audit_source_index_md", audit_source_index or ""),
    ):
        if LOCAL_PATH_RE.search(sval):
            raise ValueError(f"_ledger_patch.json.{label} leaks a local filesystem path.")

    # Pre-write check on public changelog_entry_md: zero internal leaks & zero deprecated binary links
    visible_cl = _strip_html_comments(changelog_entry)
    cl_leaks = BANNED_INTERNAL_RE.findall(visible_cl)
    if cl_leaks:
        raise ValueError(
            f"_ledger_patch.json.changelog_entry_md leaks banned internal term(s): {sorted(set(cl_leaks))}"
        )
    cl_bin_links = DEPRECATED_BINARY_LINK_RE.findall(visible_cl)
    if cl_bin_links:
        raise ValueError(
            f"_ledger_patch.json.changelog_entry_md contains deprecated local binary/release link(s): {sorted(set(cl_bin_links))[:5]}"
        )

    # Ensure CHANGELOG entry carries the canonical edition marker matching edition_id
    cl_markers = GOLD_CHANGELOG_MARKER_RE.findall(changelog_entry)
    if cl_markers:
        if cl_markers != [edition_id]:
            raise ValueError(
                f"changelog_entry_md GOLD_EDITION_CHANGELOG marker(s) {cl_markers!r} do not match edition_id {edition_id!r}."
            )
        normalized_changelog_entry = changelog_entry.strip()
    else:
        normalized_changelog_entry = f"<!-- GOLD_EDITION_CHANGELOG {edition_id} -->\n\n{changelog_entry.strip()}"

    # Validate GOLD_EDITION_REVIEW JSON inside audit_review_block_md (mirroring gold/lint_readability.py)
    review_matches = GOLD_REVIEW_BLOCK_RE.findall(audit_review_block)
    if len(review_matches) != 1:
        raise ValueError(
            f"audit_review_block_md must contain exactly one <!-- GOLD_EDITION_REVIEW {{...}} --> JSON block (found {len(review_matches)})."
        )
    try:
        review_obj = json.loads(review_matches[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"audit_review_block_md GOLD_EDITION_REVIEW JSON syntax error: {exc}") from exc

    gold_snap: dict[str, Any] | None = None
    if gold_snap_path.is_file():
        gold_snap = _read_json_obj(gold_snap_path, "gold/data_snapshot.json")
    _validate_gold_edition_review(review_obj, edition_id, gold_snap)

    if not changelog_path.is_file():
        raise ValueError("Missing gold/daily/CHANGELOG.md.")
    if not audit_path.is_file():
        raise ValueError("Missing gold/daily/AUDIT_LOG.md.")

    orig_changelog_bytes = changelog_path.read_bytes()
    orig_audit_bytes = audit_path.read_bytes()
    orig_changelog = orig_changelog_bytes.decode("utf-8")
    orig_audit = orig_audit_bytes.decode("utf-8")

    # Idempotency guard: reject duplicate edition_id in either ledger
    existing_cl_ids = set(GOLD_CHANGELOG_MARKER_RE.findall(orig_changelog))
    if edition_id in existing_cl_ids:
        raise ValueError(f"gold/daily/CHANGELOG.md already contains GOLD_EDITION_CHANGELOG {edition_id}; refusing duplicate prepend.")
    for raw_block in GOLD_REVIEW_BLOCK_RE.findall(orig_audit):
        try:
            obj = json.loads(raw_block)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("edition_id") == edition_id:
            raise ValueError(f"gold/daily/AUDIT_LOG.md already contains GOLD_EDITION_REVIEW for {edition_id}; refusing duplicate prepend.")

    new_changelog = _insert_before_anchor(
        orig_changelog,
        "<!-- GOLD_EDITION_CHANGELOG",
        normalized_changelog_entry,
        file_label="gold/daily/CHANGELOG.md",
        allow_rollover_fallback=True,
    )
    new_audit = _insert_before_anchor(
        orig_audit,
        "<!-- GOLD_EDITION_REVIEW",
        audit_review_block,
        file_label="gold/daily/AUDIT_LOG.md",
        allow_rollover_fallback=True,
    )
    source_index_inserted = False
    if audit_source_index is not None:
        if "### 📌 最新 8 大类" in new_audit:
            new_audit = _insert_before_anchor(
                new_audit,
                "### 📌 最新 8 大类",
                audit_source_index,
                file_label="gold/daily/AUDIT_LOG.md",
            )
        else:
            new_audit = f"{new_audit.rstrip()}\n\n---\n\n{audit_source_index.strip()}\n"
        source_index_inserted = True

    new_changelog_bytes = new_changelog.encode("utf-8")
    new_audit_bytes = new_audit.encode("utf-8")

    # Mathematical order-preservation proof before writing any byte
    orig_cl_lines = _nonblank_lines(orig_changelog_bytes)
    new_cl_lines = _nonblank_lines(new_changelog_bytes)
    if not _preserves_order(orig_cl_lines, new_cl_lines):
        raise ValueError("Mathematical proof failed: gold/daily/CHANGELOG.md lost or reordered prior nonblank lines.")

    orig_au_lines = _nonblank_lines(orig_audit_bytes)
    new_au_lines = _nonblank_lines(new_audit_bytes)
    if not _preserves_order(orig_au_lines, new_au_lines):
        raise ValueError("Mathematical proof failed: gold/daily/AUDIT_LOG.md lost or reordered prior nonblank lines.")

    summary = {
        "mode": "prepend-gold-ledgers",
        "dry_run": dry_run,
        "edition_id": edition_id,
        "changelog_prior_lines": len(orig_cl_lines),
        "changelog_new_lines": len(new_cl_lines),
        "audit_prior_lines": len(orig_au_lines),
        "audit_new_lines": len(new_au_lines),
        "audit_source_index_inserted": source_index_inserted,
        "order_proof_verified": True,
        "patch_deleted": False,
    }

    if not dry_run:
        _atomic_write_transaction([
            (changelog_path, new_changelog_bytes),
            (audit_path, new_audit_bytes),
        ])
        if not keep_patch:
            patch_path.unlink(missing_ok=True)
            summary["patch_deleted"] = True

    return summary


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Validate and atomically merge equity/state/_edition_patch.json into the 3 equity state databases.",
    )
    mode.add_argument(
        "--prepend-gold-ledgers",
        action="store_true",
        help="Losslessly prepend gold/daily/_ledger_patch.json into CHANGELOG.md and AUDIT_LOG.md.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all validations and print summary without modifying target files or deleting the patch.",
    )
    parser.add_argument(
        "--keep-patch",
        action="store_true",
        help="Retain the temporary patch file after successful apply/prepend.",
    )
    parser.add_argument(
        "--skip-edition-lock",
        action="store_true",
        help="Testing-only flag for --apply: skip matching edition_id against gold/data_snapshot.json and market_state.json.",
    )
    args = parser.parse_args(argv)
    if args.skip_edition_lock and not args.apply:
        parser.error("--skip-edition-lock can only be combined with --apply.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.apply:
            summary = apply_equity_patch(
                REPO_ROOT,
                dry_run=args.dry_run,
                keep_patch=args.keep_patch,
                skip_edition_lock=args.skip_edition_lock,
            )
        else:
            summary = prepend_gold_ledgers(
                REPO_ROOT,
                dry_run=args.dry_run,
                keep_patch=args.keep_patch,
            )
        prefix = "[DRY-RUN]" if args.dry_run else "[OK]"
        print(f"{prefix} {json.dumps(summary, ensure_ascii=False)}")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
