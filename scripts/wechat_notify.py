#!/usr/bin/env python3
"""Compliant zero-dependency WeChat & OS real-time alert notifier.

Supports 4 official/compliant WeChat channels (wecom_webhook, wxpusher,
pushplus, serverchan Turbo & SC3) plus Bark and macOS osascript fallbacks.
Strictly forbids personal-WeChat protocol hooking (itchat/WeChatFerry/ntchat)
and refuses to load any secret config file tracked by git or under gold/equity.
"""

from __future__ import annotations

import argparse
import dataclasses
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
CST = timezone(timedelta(hours=8))

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "global-investment-research" / "notify.json"
DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "global-investment-research"
DEFAULT_OUTBOX_PATH = DEFAULT_STATE_DIR / "notify_outbox.jsonl"
DEFAULT_DEDUPE_PATH = DEFAULT_STATE_DIR / "notify_dedupe.json"
DEFAULT_DOTENV_PATH = REPO_ROOT / ".env.notify"

SEVERITY_RANK: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2}
SUPPORTED_PROVIDERS: tuple[str, ...] = (
    "wecom_webhook",
    "wxpusher",
    "pushplus",
    "serverchan",
    "bark",
    "macos_osascript",
)
_SC3_KEY_RE = re.compile(r"^sctp(\d+)t", re.IGNORECASE)
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_WEBHOOK_KEY_RE = re.compile(r"([?&]key=)([^&\s]+)", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"REPLACE_WITH_YOUR_|YOUR_[A-Z0-9_]+|^\.\.\.$", re.IGNORECASE)


@dataclass(frozen=True)
class AlertMessage:
    title: str
    body_md: str
    severity: str = "P1"
    category: str = "market"
    url: str | None = None
    dedupe_key: str | None = None
    bypass_quiet_hours: bool = False

    def normalized_severity(self) -> str:
        sev = str(self.severity or "P1").strip().upper()
        if sev not in SEVERITY_RANK:
            raise ValueError(f"Unsupported severity {self.severity!r}; expected one of {tuple(SEVERITY_RANK)}")
        return sev


@dataclass(frozen=True)
class DeliveryResult:
    provider: str
    status: str  # sent | dry_run | suppressed_quiet | suppressed_dedupe | skipped_severity | failed
    chunks: int
    attempts: int
    http_status: int | None = None
    api_code: int | str | None = None
    receipt: str | None = None
    error: str | None = None
    latency_ms: int = 0


@dataclass
class NotifyConfig:
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    quiet_enabled: bool = True
    quiet_start: str = "23:30"
    quiet_end: str = "07:15"
    cooldown_seconds: dict[str, int] = field(
        default_factory=lambda: {"P0": 300, "P1": 900, "P2": 3600}
    )
    outbox_path: Path = DEFAULT_OUTBOX_PATH
    dedupe_path: Path = DEFAULT_DEDUPE_PATH
    config_source: str = "defaults"
    warnings: list[str] = field(default_factory=list)


def _is_placeholder(val: str) -> bool:
    s = val.strip()
    return not s or bool(_PLACEHOLDER_RE.search(s))


def _is_git_tracked(path: Path) -> bool:
    resolved = path.resolve()
    repo_res = REPO_ROOT.resolve()
    if not resolved.is_relative_to(repo_res):
        return False
    try:
        rel = resolved.relative_to(repo_res).as_posix()
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", rel],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        # Fail-closed when git is unavailable for paths inside the repository
        return True


def _validate_secret_config_path(path: Path, *, allow_repo_dotenv: bool = False) -> None:
    resolved = path.resolve()
    repo_res = REPO_ROOT.resolve()
    if resolved.is_relative_to(repo_res):
        rel_parts = resolved.relative_to(repo_res).parts
        if rel_parts and rel_parts[0] in ("gold", "equity"):
            raise ValueError(
                f"Refusing to load notification config inside published data directory: {resolved}"
            )
    if _is_git_tracked(resolved):
        raise ValueError(
            f"Refusing to load git-tracked notification config (secret leak risk): {resolved}"
        )
    if resolved.is_relative_to(repo_res):
        if not (allow_repo_dotenv and resolved.parent == repo_res and resolved.name == ".env.notify"):
            raise ValueError(
                f"Refusing to load notification config inside repository working tree: {resolved}"
            )


def _validate_state_output_path(path: Path, label: str) -> None:
    resolved = path.resolve()
    repo_res = REPO_ROOT.resolve()
    git_dir = (repo_res / ".git").resolve()
    if resolved.is_relative_to(repo_res) and not resolved.is_relative_to(git_dir):
        raise ValueError(
            f"Refusing to write {label} inside repository working tree (use ~/.local/state or temp path): {resolved}"
        )


def _parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def _collect_secrets(cfg: NotifyConfig) -> list[str]:
    secrets: list[str] = []
    for pcfg in cfg.providers.values():
        if not isinstance(pcfg, dict):
            continue
        for k in ("webhook_url", "key", "app_token", "token", "sendkey", "device_key", "base_url"):
            val = str(pcfg.get(k) or "").strip()
            if val and not _is_placeholder(val):
                if k == "base_url":
                    if "@" in val:
                        cred_part = val.split("://", 1)[-1].split("@", 1)[0]
                        if cred_part:
                            secrets.append(cred_part)
                            for part in cred_part.split(":"):
                                if len(part) >= 4:
                                    secrets.append(part)
                    continue
                secrets.append(val)
                m = _WEBHOOK_KEY_RE.search(val)
                if m:
                    secrets.append(m.group(2))
        uids = pcfg.get("uids")
        if isinstance(uids, list):
            for u in uids:
                us = str(u or "").strip()
                if us and not _is_placeholder(us):
                    secrets.append(us)
    return sorted(set(secrets), key=len, reverse=True)


def redact_text(text: str, secrets: list[str]) -> str:
    if not text:
        return text
    out = _WEBHOOK_KEY_RE.sub(
        lambda m: f"{m.group(1)}***{m.group(2)[-4:] if len(m.group(2)) > 4 else '****'}",
        text,
    )
    for sec in secrets:
        if len(sec) < 4:
            continue
        mask = f"***{sec[-4:]}" if len(sec) >= 8 else "****"
        out = out.replace(sec, mask)
    return out


def load_notify_config(
    *,
    config_path: Path | None = None,
    dotenv_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> NotifyConfig:
    """Load notification config with precedence: env > external notify.json > .env.notify."""
    cfg = NotifyConfig()
    merged_env: dict[str, str] = {}

    dotenv_file = dotenv_path if dotenv_path is not None else (DEFAULT_DOTENV_PATH if config_path is None else None)
    if dotenv_file is not None and dotenv_file.is_file():
        _validate_secret_config_path(dotenv_file, allow_repo_dotenv=True)
        dmode = stat.S_IMODE(dotenv_file.stat().st_mode)
        if dmode & 0o077:
            cfg.warnings.append(f"[WARN] {dotenv_file} permissions are {oct(dmode)}; recommend chmod 600.")
        merged_env.update(_parse_dotenv(dotenv_file))
        cfg.config_source = str(dotenv_file)

    file_path = config_path if config_path is not None else DEFAULT_CONFIG_PATH
    if file_path.is_file():
        _validate_secret_config_path(file_path, allow_repo_dotenv=False)
        mode = stat.S_IMODE(file_path.stat().st_mode)
        if mode & 0o077:
            msg = f"[WARN] {file_path} permissions are {oct(mode)}; recommend chmod 600."
            cfg.warnings.append(msg)
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid JSON object in {file_path}")
        cfg.config_source = str(file_path)
        qh = raw.get("quiet_hours")
        if isinstance(qh, dict):
            cfg.quiet_enabled = bool(qh.get("enabled", True))
            if isinstance(qh.get("start"), str) and _HHMM_RE.match(qh["start"]):
                cfg.quiet_start = qh["start"]
            if isinstance(qh.get("end"), str) and _HHMM_RE.match(qh["end"]):
                cfg.quiet_end = qh["end"]
        cd = raw.get("cooldown_seconds")
        if isinstance(cd, dict):
            for sev in SEVERITY_RANK:
                if isinstance(cd.get(sev), (int, float)) and cd[sev] >= 0:
                    cfg.cooldown_seconds[sev] = int(cd[sev])
        if raw.get("outbox_path"):
            cfg.outbox_path = Path(str(raw["outbox_path"])).expanduser()
        if raw.get("dedupe_path"):
            cfg.dedupe_path = Path(str(raw["dedupe_path"])).expanduser()
        provs = raw.get("providers")
        if isinstance(provs, dict):
            for pname, pval in provs.items():
                if pname in SUPPORTED_PROVIDERS and isinstance(pval, dict):
                    cfg.providers[pname] = dict(pval)

    active_env = dict(merged_env)
    active_env.update(os.environ if env is None else env)

    # Env overrides
    if active_env.get("GIR_NOTIFY_OUTBOX_PATH"):
        cfg.outbox_path = Path(active_env["GIR_NOTIFY_OUTBOX_PATH"]).expanduser()
    if active_env.get("GIR_NOTIFY_DEDUPE_PATH"):
        cfg.dedupe_path = Path(active_env["GIR_NOTIFY_DEDUPE_PATH"]).expanduser()
    _validate_state_output_path(cfg.outbox_path, "outbox_path")
    _validate_state_output_path(cfg.dedupe_path, "dedupe_path")
    qh_env = active_env.get("GIR_NOTIFY_QUIET_HOURS", "").strip()
    if qh_env:
        if qh_env.lower() in ("off", "false", "0", "none"):
            cfg.quiet_enabled = False
        elif "-" in qh_env:
            s, e = [x.strip() for x in qh_env.split("-", 1)]
            if _HHMM_RE.match(s) and _HHMM_RE.match(e):
                cfg.quiet_enabled = True
                cfg.quiet_start, cfg.quiet_end = s, e

    def _ensure_provider(name: str, default_min: str) -> dict[str, Any]:
        entry = cfg.providers.setdefault(name, {"enabled": False, "min_severity": default_min})
        return entry

    if active_env.get("GIR_NOTIFY_WECOM_WEBHOOK_URL"):
        p = _ensure_provider("wecom_webhook", "P2")
        p["webhook_url"] = active_env["GIR_NOTIFY_WECOM_WEBHOOK_URL"].strip()
        p["enabled"] = True
    if active_env.get("GIR_NOTIFY_WXPUSHER_APP_TOKEN") and active_env.get("GIR_NOTIFY_WXPUSHER_UIDS"):
        p = _ensure_provider("wxpusher", "P1")
        p["app_token"] = active_env["GIR_NOTIFY_WXPUSHER_APP_TOKEN"].strip()
        p["uids"] = [u.strip() for u in active_env["GIR_NOTIFY_WXPUSHER_UIDS"].split(",") if u.strip()]
        p["enabled"] = True
    if active_env.get("GIR_NOTIFY_PUSHPLUS_TOKEN"):
        p = _ensure_provider("pushplus", "P1")
        p["token"] = active_env["GIR_NOTIFY_PUSHPLUS_TOKEN"].strip()
        p["enabled"] = True
    if active_env.get("GIR_NOTIFY_SERVERCHAN_SENDKEY"):
        p = _ensure_provider("serverchan", "P0")
        p["sendkey"] = active_env["GIR_NOTIFY_SERVERCHAN_SENDKEY"].strip()
        p["enabled"] = True
    if active_env.get("GIR_NOTIFY_BARK_DEVICE_KEY"):
        p = _ensure_provider("bark", "P0")
        p["device_key"] = active_env["GIR_NOTIFY_BARK_DEVICE_KEY"].strip()
        if active_env.get("GIR_NOTIFY_BARK_URL"):
            p["base_url"] = active_env["GIR_NOTIFY_BARK_URL"].strip().rstrip("/")
        p["enabled"] = True

    explicit_list = active_env.get("GIR_NOTIFY_PROVIDERS", "").strip()
    if explicit_list:
        allowed = {x.strip() for x in explicit_list.split(",") if x.strip()}
        for pname in SUPPORTED_PROVIDERS:
            if pname in cfg.providers:
                cfg.providers[pname]["enabled"] = pname in allowed
            elif pname in allowed and pname == "macos_osascript":
                cfg.providers[pname] = {"enabled": True, "min_severity": "P1"}

    return cfg


def is_in_quiet_hours(now_cst: datetime, start_hhmm: str, end_hhmm: str) -> bool:
    s_h, s_m = (int(x) for x in start_hhmm.split(":"))
    e_h, e_m = (int(x) for x in end_hhmm.split(":"))
    cur = now_cst.hour * 60 + now_cst.minute
    start = s_h * 60 + s_m
    end = e_h * 60 + e_m
    if start == end:
        return False
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end


def chunk_text(text: str, max_bytes: int, max_chars: int | None = None) -> list[str]:
    """Split text into UTF-8 byte-safe, Markdown-aware chunks without breaking multi-byte chars."""
    clean = str(text or "")
    if not clean:
        return [""]

    def _fits(s: str, budget_b: int, budget_c: int | None) -> bool:
        if len(s.encode("utf-8")) > budget_b:
            return False
        if budget_c is not None and len(s) > budget_c:
            return False
        return True

    if _fits(clean, max_bytes, max_chars):
        return [clean]

    reserve_b = 18
    eff_b = max(32, max_bytes - reserve_b)
    eff_c = max(16, max_chars - 12) if max_chars is not None else None

    raw_chunks: list[str] = []
    remaining = clean
    while remaining:
        if _fits(remaining, eff_b, eff_c):
            raw_chunks.append(remaining)
            break
        # Find longest prefix that fits byte & char budgets
        lo, hi = 1, len(remaining) if eff_c is None else min(len(remaining), eff_c)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if _fits(remaining[:mid], eff_b, eff_c):
                lo = mid
            else:
                hi = mid - 1
        cut = lo
        # Prefer paragraph or line break in the latter half of the slice
        cand = remaining[:cut]
        split_at = -1
        for sep in ("\n\n", "\n"):
            idx = cand.rfind(sep)
            if idx >= max(1, cut // 3):
                split_at = idx + len(sep)
                break
        if split_at <= 0:
            split_at = cut
        piece = remaining[:split_at].rstrip()
        if not piece:
            piece = remaining[:cut]
            split_at = cut
        raw_chunks.append(piece)
        remaining = remaining[split_at:].lstrip("\n")

    total = len(raw_chunks)
    if total == 1:
        return raw_chunks
    return [f"[{i}/{total}] {chunk}" for i, chunk in enumerate(raw_chunks, start=1)]


def sanitize_serverchan_title(title: str) -> str:
    single = re.sub(r"\s+", " ", str(title or "")).strip()
    return (single or "投资监测提醒")[:32]


def serverchan_endpoint(sendkey: str) -> str:
    m = _SC3_KEY_RE.match(sendkey.strip())
    if m:
        uid = m.group(1)
        return f"https://{uid}.push.ft07.com/send/{sendkey.strip()}.send"
    return f"https://sctapi.ftqq.com/{sendkey.strip()}.send"


def _wecom_url(pcfg: dict[str, Any]) -> str:
    raw = str(pcfg.get("webhook_url") or pcfg.get("key") or "").strip()
    if "://" in raw and not raw.lower().startswith("https://"):
        raise ValueError("WeCom webhook_url must use https:// (non-HTTPS scheme refused).")
    if raw.lower().startswith("https://"):
        return raw
    return f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={raw}"


def _provider_configured(name: str, pcfg: dict[str, Any]) -> tuple[bool, str]:
    if not pcfg.get("enabled"):
        return False, "disabled"
    if name == "wecom_webhook":
        u = str(pcfg.get("webhook_url") or pcfg.get("key") or "").strip()
        return (not _is_placeholder(u)), "missing webhook_url/key"
    if name == "wxpusher":
        tok = str(pcfg.get("app_token") or "").strip()
        uids = [str(x).strip() for x in (pcfg.get("uids") or []) if not _is_placeholder(str(x))]
        return (not _is_placeholder(tok) and bool(uids)), "missing app_token or uids"
    if name == "pushplus":
        tok = str(pcfg.get("token") or "").strip()
        return (not _is_placeholder(tok)), "missing token"
    if name == "serverchan":
        sk = str(pcfg.get("sendkey") or "").strip()
        return (not _is_placeholder(sk)), "missing sendkey"
    if name == "bark":
        dk = str(pcfg.get("device_key") or "").strip()
        return (not _is_placeholder(dk)), "missing device_key"
    if name == "macos_osascript":
        return (sys.platform == "darwin"), "macOS only"
    return False, "unknown provider"


class _HttpResult(Exception):
    def __init__(self, msg: str, *, retryable: bool, http_status: int | None = None, api_code: Any = None):
        super().__init__(msg)
        self.retryable = retryable
        self.http_status = http_status
        self.api_code = api_code


class Notifier:
    """Zero-dependency compliant multi-channel WeChat/OS alert dispatcher."""

    def __init__(
        self,
        config: NotifyConfig | None = None,
        *,
        dry_run: bool = False,
        now_fn: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config if config is not None else load_notify_config()
        self.dry_run = bool(dry_run)
        self._now_fn = now_fn or (lambda: datetime.now(CST))
        self._sleep_fn = sleep_fn or time.sleep
        self._secrets = _collect_secrets(self.config)

    def _now(self) -> datetime:
        dt = self._now_fn()
        return dt.astimezone(CST) if dt.tzinfo is not None else dt.replace(tzinfo=CST)

    def _append_outbox(self, record: dict[str, Any]) -> None:
        path = self.config.outbox_path
        path.parent.mkdir(parents=True, exist_ok=True)
        safe = json.loads(redact_text(json.dumps(record, ensure_ascii=False), self._secrets))
        with path.open("a+", encoding="utf-8") as fh:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.write(json.dumps(safe, ensure_ascii=False) + "\n")
                fh.flush()
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _check_and_update_dedupe(self, provider: str, dedupe_key: str, severity: str, *, commit: bool) -> bool:
        """Return True if suppressed by active cooldown window."""
        cooldown = int(self.config.cooldown_seconds.get(severity, 900))
        if cooldown <= 0:
            return False
        path = self.config.dedupe_path
        path.parent.mkdir(parents=True, exist_ok=True)
        now_ts = self._now().timestamp()
        compound = f"{provider}:{dedupe_key}"
        with path.open("a+", encoding="utf-8") as fh:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.seek(0)
                raw = fh.read().strip()
                data = json.loads(raw) if raw else {}
                if not isinstance(data, dict):
                    data = {}
                # Prune entries >48h old
                data = {k: v for k, v in data.items() if isinstance(v, (int, float)) and (now_ts - float(v)) < 172800}
                prev = data.get(compound)
                if isinstance(prev, (int, float)) and (now_ts - float(prev)) < cooldown:
                    return True
                if commit:
                    data[compound] = now_ts
                    fh.seek(0)
                    fh.truncate()
                    fh.write(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
                    fh.flush()
                return False
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _http_post_json(self, url: str, payload: dict[str, Any], *, timeout: int = 10) -> tuple[int, dict[str, Any]]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "GlobalInvestmentResearch-Notifier/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = int(getattr(resp, "status", 200))
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            code = int(exc.code)
            raw_err = exc.read().decode("utf-8", errors="replace")[:300]
            raise _HttpResult(
                f"HTTP {code}: {raw_err}",
                retryable=(code == 429 or code >= 500),
                http_status=code,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise _HttpResult(f"Network error: {exc}", retryable=True) from exc

        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            raise _HttpResult(f"Invalid JSON response: {raw[:200]}", retryable=False, http_status=status) from exc
        if not isinstance(parsed, dict):
            parsed = {"raw": parsed}
        return status, parsed

    def _build_chunks_and_payloads(
        self, provider: str, pcfg: dict[str, Any], msg: AlertMessage, now_cst: datetime
    ) -> list[tuple[str, dict[str, Any]]]:
        ts_hhmm = now_cst.strftime("%H:%M")
        sev = msg.normalized_severity()
        stamped_title = f"[{ts_hhmm} {sev}] {msg.title}".strip()
        full_md = f"## {msg.title}\n\n{msg.body_md}".strip()
        if msg.url and msg.url not in full_md:
            full_md = f"{full_md}\n\n详情链接：{msg.url}"

        if provider == "wecom_webhook":
            msgtype = str(pcfg.get("msgtype") or "markdown").strip()
            budget = 1900 if msgtype == "text" else 3800
            chunks = chunk_text(full_md, max_bytes=budget)
            url = _wecom_url(pcfg)
            if msgtype == "text":
                return [(url, {"msgtype": "text", "text": {"content": c}}) for c in chunks]
            return [(url, {"msgtype": "markdown", "markdown": {"content": c}}) for c in chunks]

        if provider == "wxpusher":
            chunks = chunk_text(full_md, max_bytes=28000, max_chars=36000)
            url = "https://wxpusher.zjiecode.com/api/send/message"
            uids = [str(u).strip() for u in (pcfg.get("uids") or []) if not _is_placeholder(str(u))]
            summary = stamped_title[:100]
            content_type = int(pcfg.get("content_type", 3))
            out: list[tuple[str, dict[str, Any]]] = []
            for c in chunks:
                payload: dict[str, Any] = {
                    "appToken": str(pcfg["app_token"]).strip(),
                    "content": c,
                    "summary": summary,
                    "contentType": content_type,
                    "uids": uids,
                    "topicIds": pcfg.get("topic_ids") or [],
                    "verifyPayType": 0,
                }
                if msg.url:
                    payload["url"] = msg.url[:1000]
                out.append((url, payload))
            return out

        if provider == "pushplus":
            chunks = chunk_text(full_md, max_bytes=40000, max_chars=18000)
            url = "https://www.pushplus.plus/send"
            out = []
            for c in chunks:
                payload = {
                    "token": str(pcfg["token"]).strip(),
                    "title": stamped_title[:100],
                    "content": c,
                    "template": str(pcfg.get("template") or "markdown"),
                    "channel": str(pcfg.get("channel") or "wechat"),
                }
                if pcfg.get("topic"):
                    payload["topic"] = str(pcfg["topic"])
                out.append((url, payload))
            return out

        if provider == "serverchan":
            chunks = chunk_text(msg.body_md if msg.body_md else msg.title, max_bytes=28000)
            sendkey = str(pcfg["sendkey"]).strip()
            url = serverchan_endpoint(sendkey)
            sc_title = sanitize_serverchan_title(stamped_title)
            short = re.sub(r"\s+", " ", msg.body_md or msg.title).strip()[:64]
            out = []
            for c in chunks:
                payload = {"title": sc_title, "desp": c, "short": short}
                if not _SC3_KEY_RE.match(sendkey):
                    payload["noip"] = 1
                else:
                    payload["tags"] = f"{sev}|{msg.category}"
                out.append((url, payload))
            return out

        if provider == "bark":
            chunks = chunk_text(msg.body_md or msg.title, max_bytes=3500)
            base = str(pcfg.get("base_url") or "https://api.day.app").strip().rstrip("/")
            if not base.lower().startswith("https://"):
                raise ValueError("Bark base_url must use https://.")
            url = f"{base}/push"
            level = "critical" if sev == "P0" else ("timeSensitive" if sev == "P1" else "active")
            out = []
            for c in chunks:
                payload = {
                    "device_key": str(pcfg["device_key"]).strip(),
                    "title": stamped_title[:100],
                    "body": c,
                    "level": level,
                    "sound": "alarm" if sev == "P0" else "minuet",
                    "group": "GIR-Monitor",
                }
                if sev == "P0":
                    payload["volume"] = 10
                if msg.url:
                    payload["url"] = msg.url[:1000]
                out.append((url, payload))
            return out

        raise ValueError(f"Unsupported HTTP provider: {provider}")

    def _validate_api_response(self, provider: str, status: int, data: dict[str, Any]) -> tuple[Any, str | None]:
        if provider == "wecom_webhook":
            errcode = data.get("errcode")
            if status == 200 and errcode == 0:
                return errcode, "wecom:ok"
            raise _HttpResult(
                f"WeCom error {errcode}: {data.get('errmsg', '')}",
                retryable=(errcode in (-1, 9300000, 45009)),
                http_status=status,
                api_code=errcode,
            )
        if provider == "wxpusher":
            code = data.get("code")
            items = data.get("data") if isinstance(data.get("data"), list) else []
            items_ok = all(isinstance(it, dict) and it.get("code") == 1000 for it in items)
            if status == 200 and code == 1000 and data.get("success") is True and items_ok:
                receipt = str(items[0].get("messageContentId") or items[0].get("messageId") or "ok") if items else "ok"
                return code, receipt
            raise _HttpResult(
                f"WxPusher error {code}: {data.get('msg', '')}",
                retryable=(code not in (1001, 1002, 1005)),
                http_status=status,
                api_code=code,
            )
        if provider == "pushplus":
            code = data.get("code")
            if status == 200 and code == 200:
                return code, str(data.get("data") or "ok")
            raise _HttpResult(
                f"PushPlus error {code}: {data.get('msg', '')}",
                retryable=(code == 900),
                http_status=status,
                api_code=code,
            )
        if provider == "serverchan":
            code = data.get("code")
            inner = data.get("data") if isinstance(data.get("data"), dict) else {}
            errno = inner.get("errno", 0)
            if status == 200 and code == 0 and errno == 0:
                return code, str(inner.get("pushid") or "ok")
            raise _HttpResult(
                f"ServerChan error code={code} errno={errno}: {data.get('message') or data.get('info') or ''}",
                retryable=False,
                http_status=status,
                api_code=code,
            )
        if provider == "bark":
            code = data.get("code")
            if status == 200 and code == 200:
                return code, "bark:ok"
            raise _HttpResult(
                f"Bark error {code}: {data.get('message', '')}",
                retryable=(status >= 500 or status == 429),
                http_status=status,
                api_code=code,
            )
        return None, None

    def _send_macos_osascript(self, msg: AlertMessage) -> DeliveryResult:
        t0 = time.monotonic()
        sev = msg.normalized_severity()
        subtitle = f"{sev} · {msg.category}"
        body = re.sub(r"\s+", " ", msg.body_md or msg.title).strip()[:240]
        sound = "Ping" if sev == "P0" else "default"
        script = (
            "on run argv\n"
            "  display notification (item 2 of argv) with title (item 1 of argv) "
            "subtitle (item 3 of argv) sound name (item 4 of argv)\n"
            "end run"
        )
        try:
            proc = subprocess.run(
                ["osascript", "-e", script, "--", msg.title[:100], body, subtitle, sound],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
            ms = int((time.monotonic() - t0) * 1000)
            if proc.returncode == 0:
                return DeliveryResult("macos_osascript", "sent", 1, 1, receipt="osascript:ok", latency_ms=ms)
            return DeliveryResult(
                "macos_osascript", "failed", 1, 1, error=redact_text(proc.stderr.strip(), self._secrets), latency_ms=ms
            )
        except Exception as exc:
            ms = int((time.monotonic() - t0) * 1000)
            return DeliveryResult(
                "macos_osascript", "failed", 1, 1, error=redact_text(str(exc), self._secrets), latency_ms=ms
            )

    def _deliver_one(self, provider: str, pcfg: dict[str, Any], msg: AlertMessage, now_cst: datetime) -> DeliveryResult:
        sev = msg.normalized_severity()
        min_sev = str(pcfg.get("min_severity") or "P2").strip().upper()
        if min_sev in SEVERITY_RANK and SEVERITY_RANK[sev] > SEVERITY_RANK[min_sev]:
            return DeliveryResult(provider, "skipped_severity", 0, 0)

        bypass = sev == "P0" or bool(msg.bypass_quiet_hours)
        if self.config.quiet_enabled and not bypass and is_in_quiet_hours(now_cst, self.config.quiet_start, self.config.quiet_end):
            return DeliveryResult(provider, "suppressed_quiet", 0, 0)

        if msg.dedupe_key:
            if self._check_and_update_dedupe(provider, msg.dedupe_key, sev, commit=False):
                return DeliveryResult(provider, "suppressed_dedupe", 0, 0)

        if provider == "macos_osascript":
            if self.dry_run:
                return DeliveryResult(provider, "dry_run", 1, 0, receipt="dry_run:osascript")
            res = self._send_macos_osascript(msg)
            if res.status == "sent" and msg.dedupe_key:
                self._check_and_update_dedupe(provider, msg.dedupe_key, sev, commit=True)
            return res

        payloads = self._build_chunks_and_payloads(provider, pcfg, msg, now_cst)
        if self.dry_run:
            return DeliveryResult(provider, "dry_run", len(payloads), 0, receipt=f"dry_run:{len(payloads)}_chunks")

        pacing = {"wecom_webhook": 3.2, "wxpusher": 1.1, "pushplus": 12.5, "serverchan": 1.5, "bark": 0.5}.get(provider, 1.0)
        backoffs = (1.0, 2.5, 5.0)
        t0 = time.monotonic()
        total_attempts = 0
        last_status: int | None = None
        last_code: Any = None
        last_receipt: str | None = None

        for idx, (url, payload) in enumerate(payloads):
            if idx > 0:
                self._sleep_fn(pacing)
            for attempt in range(1, 4):
                total_attempts += 1
                try:
                    st, data = self._http_post_json(url, payload)
                    last_status = st
                    last_code, last_receipt = self._validate_api_response(provider, st, data)
                    break
                except _HttpResult as err:
                    last_status = err.http_status
                    last_code = err.api_code
                    if not err.retryable or attempt >= 3:
                        ms = int((time.monotonic() - t0) * 1000)
                        return DeliveryResult(
                            provider=provider,
                            status="failed",
                            chunks=len(payloads),
                            attempts=total_attempts,
                            http_status=last_status,
                            api_code=last_code,
                            error=redact_text(str(err), self._secrets),
                            latency_ms=ms,
                        )
                    self._sleep_fn(backoffs[attempt - 1])

        if msg.dedupe_key:
            self._check_and_update_dedupe(provider, msg.dedupe_key, sev, commit=True)
        ms = int((time.monotonic() - t0) * 1000)
        return DeliveryResult(
            provider=provider,
            status="sent",
            chunks=len(payloads),
            attempts=total_attempts,
            http_status=last_status,
            api_code=last_code,
            receipt=last_receipt,
            latency_ms=ms,
        )

    def send(self, msg: AlertMessage, *, providers: list[str] | None = None) -> list[DeliveryResult]:
        now_cst = self._now()
        sev = msg.normalized_severity()
        targets = providers if providers is not None else list(SUPPORTED_PROVIDERS)
        results: list[DeliveryResult] = []
        body_hash = hashlib.sha256((msg.body_md or "").encode("utf-8")).hexdigest()[:16]

        for pname in targets:
            if pname not in SUPPORTED_PROVIDERS:
                results.append(DeliveryResult(pname, "failed", 0, 0, error=f"Unsupported provider: {pname}"))
                continue
            pcfg = self.config.providers.get(pname) or {}
            ok, reason = _provider_configured(pname, pcfg)
            if not ok:
                if providers is not None:
                    results.append(DeliveryResult(pname, "failed", 0, 0, error=f"Provider not ready: {reason}"))
                continue
            try:
                res = self._deliver_one(pname, pcfg, msg, now_cst)
            except Exception as exc:
                res = DeliveryResult(pname, "failed", 0, 1, error=redact_text(str(exc), self._secrets))
            results.append(res)
            self._append_outbox(
                {
                    "timestamp_cst": now_cst.isoformat(timespec="seconds"),
                    "severity": sev,
                    "category": msg.category,
                    "title": msg.title,
                    "body_sha256": body_hash,
                    "dedupe_key": msg.dedupe_key,
                    **dataclasses.asdict(res),
                }
            )
        return results


def run_doctor(cfg: NotifyConfig) -> dict[str, Any]:
    report: dict[str, Any] = {
        "config_source": cfg.config_source,
        "quiet_hours": {"enabled": cfg.quiet_enabled, "start": cfg.quiet_start, "end": cfg.quiet_end},
        "outbox_path": str(cfg.outbox_path),
        "warnings": list(cfg.warnings),
        "providers": {},
    }
    for pname in SUPPORTED_PROVIDERS:
        pcfg = cfg.providers.get(pname) or {}
        ready, reason = _provider_configured(pname, pcfg)
        report["providers"][pname] = {
            "enabled": bool(pcfg.get("enabled")),
            "ready": ready,
            "min_severity": str(pcfg.get("min_severity") or "P2"),
            "status": "ready" if ready else reason,
        }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compliant zero-dependency WeChat & OS alert notifier.")
    p.add_argument("--config", type=Path, default=None, help="External notify.json path (outside git & gold/equity).")
    p.add_argument("--severity", default="P1", choices=tuple(SEVERITY_RANK), help="Alert severity (P0 bypasses quiet hours).")
    p.add_argument("--category", default="market", help="Alert category.")
    p.add_argument("--title", default="", help="Alert title.")
    p.add_argument("--body", default="", help="Alert Markdown body.")
    p.add_argument("--url", default=None, help="Optional detail link.")
    p.add_argument("--dedupe-key", default=None, help="Optional cooldown deduplication key.")
    p.add_argument("--provider", default=None, help="Comma-separated provider subset.")
    p.add_argument("--dry-run", action="store_true", help="Render & log to outbox without network send.")
    p.add_argument("--doctor", action="store_true", help="Inspect config safety & ready providers (secrets redacted).")
    p.add_argument("--test", action="store_true", help="Send a safe P2 timestamped connectivity test message.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        cfg = load_notify_config(config_path=args.config)
    except Exception as exc:
        print(f"[FAIL] Config error: {exc}", file=sys.stderr)
        return 2

    for w in cfg.warnings:
        print(w, file=sys.stderr)

    if args.doctor:
        print(json.dumps(run_doctor(cfg), ensure_ascii=False, indent=2))
        return 0

    prov_list = [x.strip() for x in args.provider.split(",") if x.strip()] if args.provider else None
    if args.test:
        now_s = datetime.now(CST).strftime("%Y-%m-%d %H:%M CST")
        msg = AlertMessage(
            title=f"[TEST] 全球投研实时监测连通性测试 ({now_s})",
            body_md="这是一条合规微信推送连通性自检消息。\n\n- 状态：配置加载正常，脱敏与去重门禁就绪\n- 说明：本通道仅在强信号（P0/P1）时推送，严守防刷屏冷却。",
            severity="P2",
            category="test",
            url="https://nanless.github.io/global-investment-research/",
            bypass_quiet_hours=True,
        )
    else:
        if not args.title:
            print("[FAIL] --title is required unless --doctor or --test is set.", file=sys.stderr)
            return 2
        msg = AlertMessage(
            title=args.title,
            body_md=args.body or args.title,
            severity=args.severity,
            category=args.category,
            url=args.url,
            dedupe_key=args.dedupe_key,
        )

    notifier = Notifier(cfg, dry_run=args.dry_run)
    results = notifier.send(msg, providers=prov_list)
    print(json.dumps([dataclasses.asdict(r) for r in results], ensure_ascii=False, indent=2))
    if any(r.status == "failed" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
