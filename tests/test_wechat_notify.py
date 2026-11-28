#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""100%-offline unit test suite for scripts/wechat_notify.py (ZERO network calls)."""

from __future__ import annotations

import contextlib
import io
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error

from scripts import wechat_notify as wn


class _FakeHTTPResponse:
    """Minimal context-manager stub mimicking urllib.request.urlopen responses."""

    def __init__(self, body: dict | str | bytes, status: int = 200) -> None:
        self.status = status
        if isinstance(body, dict):
            self._raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            self._raw = body.encode("utf-8")
        else:
            self._raw = body

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _make_http_error(url: str, code: int, body: str = "error") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url=url,
        code=code,
        msg=f"HTTP {code}",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(body.encode("utf-8")),
    )


def _cst(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=wn.CST)


def _make_config(tmp_dir: Path, providers: dict, **overrides) -> wn.NotifyConfig:
    kwargs = {
        "providers": providers,
        "quiet_enabled": True,
        "quiet_start": "23:30",
        "quiet_end": "07:15",
        "cooldown_seconds": {"P0": 300, "P1": 900, "P2": 3600},
        "outbox_path": tmp_dir / "notify_outbox.jsonl",
        "dedupe_path": tmp_dir / "notify_dedupe.json",
        "config_source": "unit-test",
    }
    kwargs.update(overrides)
    return wn.NotifyConfig(**kwargs)


def _read_outbox(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestProviderPayloadsAndResponses(unittest.TestCase):
    """Covers all 4 safe WeChat providers + Bark + macOS osascript."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.daytime = _cst(2026, 11, 27, 10, 30)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_wecom_webhook_markdown_and_text_modes(self) -> None:
        # 1. Markdown mode with full webhook_url
        captured: list[tuple[str, dict]] = []

        def fake_urlopen(req, timeout=10):
            captured.append((req.full_url, json.loads(req.data.decode("utf-8"))))
            return _FakeHTTPResponse({"errcode": 0, "errmsg": "ok"}, status=200)

        cfg = _make_config(
            self.tmp_dir,
            {
                "wecom_webhook": {
                    "enabled": True,
                    "min_severity": "P2",
                    "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-secret-key-1111",
                    "msgtype": "markdown",
                }
            },
        )
        msg = wn.AlertMessage(
            title="黄金跌破阈值",
            body_md="伦敦现货金短线异动 **-2.3%**",
            severity="P1",
            category="gold",
            url="https://example.invalid/report",
        )
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen):
            notifier = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None)
            results = notifier.send(msg)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.provider, "wecom_webhook")
        self.assertEqual(res.status, "sent")
        self.assertEqual(res.api_code, 0)
        self.assertEqual(res.http_status, 200)
        self.assertEqual(res.receipt, "wecom:ok")
        self.assertEqual(len(captured), 1)
        url, payload = captured[0]
        self.assertEqual(url, "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-secret-key-1111")
        self.assertEqual(payload["msgtype"], "markdown")
        self.assertIn("## 黄金跌破阈值", payload["markdown"]["content"])
        self.assertIn("https://example.invalid/report", payload["markdown"]["content"])

        # 2. Text mode with bare key (constructs full webhook URL & uses 1900-byte chunk budget)
        captured.clear()
        cfg_text = _make_config(
            self.tmp_dir,
            {
                "wecom_webhook": {
                    "enabled": True,
                    "min_severity": "P2",
                    "key": "bare-wecom-key-2222",
                    "msgtype": "text",
                }
            },
        )
        long_text_msg = wn.AlertMessage(title="长文本分片", body_md="中" * 700, severity="P2")
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen):
            notifier_text = wn.Notifier(cfg_text, now_fn=lambda: self.daytime, sleep_fn=lambda _: None)
            results_text = notifier_text.send(long_text_msg)

        self.assertEqual(results_text[0].status, "sent")
        self.assertGreater(results_text[0].chunks, 1)
        self.assertEqual(
            captured[0][0],
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=bare-wecom-key-2222",
        )
        for _, p in captured:
            self.assertEqual(p["msgtype"], "text")
            self.assertIn("content", p["text"])
            self.assertLessEqual(len(p["text"]["content"].encode("utf-8")), 1900)

    def test_wxpusher_success_and_item_validation(self) -> None:
        captured: list[tuple[str, dict]] = []

        def fake_urlopen_ok(req, timeout=10):
            captured.append((req.full_url, json.loads(req.data.decode("utf-8"))))
            return _FakeHTTPResponse(
                {
                    "code": 1000,
                    "msg": "处理成功",
                    "success": True,
                    "data": [
                        {"uid": "UID_REAL_USER_1", "code": 1000, "messageContentId": 987654321},
                        {"uid": "UID_REAL_USER_2", "code": 1000, "messageId": 987654322},
                        {"topicId": 1234, "code": 1000, "messageContentId": 987654321},
                    ],
                },
                status=200,
            )

        cfg = _make_config(
            self.tmp_dir,
            {
                "wxpusher": {
                    "enabled": True,
                    "min_severity": "P1",
                    "app_token": "AT_REAL_SECRET_TOKEN_9999",
                    "uids": ["UID_REAL_USER_1", "UID_REAL_USER_2"],
                    "content_type": 3,
                    "topic_ids": [1234],
                }
            },
        )
        msg = wn.AlertMessage(
            title="A股政策信号",
            body_md="央行宣布降准 25bp",
            severity="P1",
            url="https://example.invalid/policy",
        )
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen_ok):
            res = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg)[0]

        self.assertEqual(res.status, "sent")
        self.assertEqual(res.api_code, 1000)
        self.assertEqual(res.receipt, "987654321")
        url, payload = captured[0]
        self.assertEqual(url, "https://wxpusher.zjiecode.com/api/send/message")
        self.assertEqual(payload["appToken"], "AT_REAL_SECRET_TOKEN_9999")
        self.assertEqual(payload["uids"], ["UID_REAL_USER_1", "UID_REAL_USER_2"])
        self.assertEqual(payload["contentType"], 3)
        self.assertEqual(payload["topicIds"], [1234])
        self.assertEqual(payload["verifyPayType"], 0)
        self.assertEqual(payload["url"], "https://example.invalid/policy")
        self.assertTrue(payload["summary"].startswith("[10:30 P1] "))

        # Item-level failure must fail even when top-level code==1000 & success==True
        def fake_urlopen_item_fail(req, timeout=10):
            return _FakeHTTPResponse(
                {
                    "code": 1000,
                    "msg": "partial fail",
                    "success": True,
                    "data": [
                        {"uid": "UID_REAL_USER_1", "code": 1000, "messageId": 1},
                        {"uid": "UID_REAL_USER_2", "code": 1005, "status": "uid not found"},
                    ],
                },
                status=200,
            )

        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen_item_fail):
            res_fail = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg)[0]
        self.assertEqual(res_fail.status, "failed")

        # Top-level success=False must fail even if code==1000
        def fake_urlopen_success_false(req, timeout=10):
            return _FakeHTTPResponse({"code": 1000, "msg": "rejected", "success": False, "data": []}, status=200)

        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen_success_false):
            res_false = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg)[0]
        self.assertEqual(res_false.status, "failed")

    def test_wxpusher_topic_only_requires_receipt_and_preserves_outbox_failure(self) -> None:
        cfg = _make_config(self.tmp_dir, {"wxpusher": {
            "enabled": True, "app_token": "AT_TOPIC_TEST_SECRET", "topic_ids": [77],
        }})
        msg = wn.AlertMessage("测试公告", "测试内容", dedupe_key="topic-only")
        notifier = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None)
        self.assertTrue(notifier.has_ready_provider())
        response = {"code": 1000, "success": True}
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen",
                        return_value=_FakeHTTPResponse({**response, "data": []})) as opener:
            result = notifier.send(msg)[0]
        self.assertEqual(result.status, "failed")
        opener.assert_called_once()
        data = [{"topicId": 77, "code": 1000, "messageContentId": "AT_TOPIC_TEST_SECRET"}]
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen",
                        return_value=_FakeHTTPResponse({**response, "data": data})) as opener:
            with mock.patch.object(notifier, "_append_outbox", side_effect=OSError("outbox unavailable")):
                result = notifier.send(msg)[0]
        self.assertEqual(result.status, "sent")
        self.assertIn("outbox unavailable", result.audit_error)
        self.assertNotIn("AT_TOPIC_TEST_SECRET", result.receipt)
        payload = json.loads(opener.call_args.args[0].data)
        self.assertEqual((payload["uids"], payload["topicIds"]), ([], [77]))
        self.assertEqual(notifier.send(msg)[0].status, "suppressed_dedupe")

        def unavailable_on_commit(*args, commit):
            if commit:
                raise OSError("dedupe disk full")
            return False

        with mock.patch.object(notifier, "_check_and_update_dedupe", side_effect=unavailable_on_commit):
            with mock.patch("scripts.wechat_notify.urllib.request.urlopen",
                            return_value=_FakeHTTPResponse({**response, "data": data})):
                result = notifier.send(msg)[0]
        self.assertEqual(result.status, "sent")
        self.assertIn("dedupe disk full", result.audit_error)

    def test_pushplus_success_and_payload(self) -> None:
        captured: list[tuple[str, dict]] = []

        def fake_urlopen(req, timeout=10):
            captured.append((req.full_url, json.loads(req.data.decode("utf-8"))))
            return _FakeHTTPResponse({"code": 200, "msg": "请求成功", "data": "pp-receipt-888"}, status=200)

        cfg = _make_config(
            self.tmp_dir,
            {
                "pushplus": {
                    "enabled": True,
                    "min_severity": "P1",
                    "token": "pp_secret_token_abcdef1234",
                    "channel": "wechat",
                    "template": "markdown",
                    "topic": "gir_group",
                }
            },
        )
        msg = wn.AlertMessage(title="港股午盘异动", body_md="恒生科技大涨 3.2%", severity="P1")
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen):
            res = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg)[0]

        self.assertEqual(res.status, "sent")
        self.assertEqual(res.api_code, 200)
        self.assertEqual(res.receipt, "pp-receipt-888")
        url, payload = captured[0]
        self.assertEqual(url, "https://www.pushplus.plus/send")
        self.assertEqual(payload["token"], "pp_secret_token_abcdef1234")
        self.assertEqual(payload["channel"], "wechat")
        self.assertEqual(payload["template"], "markdown")
        self.assertEqual(payload["topic"], "gir_group")
        self.assertEqual(payload["title"], "[10:30 P1] 港股午盘异动")

    def test_serverchan_turbo_sc3_and_32char_single_line_title_clamp(self) -> None:
        # Direct unit checks for endpoint routing & title sanitization
        self.assertEqual(
            wn.serverchan_endpoint("SCT123456abcdef"),
            "https://sctapi.ftqq.com/SCT123456abcdef.send",
        )
        self.assertEqual(
            wn.serverchan_endpoint("sctp87654tSecretKeyXYZ"),
            "https://87654.push.ft07.com/send/sctp87654tSecretKeyXYZ.send",
        )
        self.assertEqual(
            wn.serverchan_endpoint("  SCTP42TUpperCaseKey  "),
            "https://42.push.ft07.com/send/SCTP42TUpperCaseKey.send",
        )
        sanitized = wn.sanitize_serverchan_title("第一行标题\n第二行\t\t超长标题内容一二三四五六七八九十甲乙丙丁戊己庚辛")
        self.assertNotIn("\n", sanitized)
        self.assertNotIn("\t", sanitized)
        self.assertNotIn("  ", sanitized)
        self.assertLessEqual(len(sanitized), 32)
        self.assertEqual(wn.sanitize_serverchan_title("   \n\t  "), "投资监测提醒")

        # 1. ServerChan Turbo delivery
        captured: list[tuple[str, dict]] = []

        def fake_urlopen_sc(req, timeout=10):
            captured.append((req.full_url, json.loads(req.data.decode("utf-8"))))
            return _FakeHTTPResponse(
                {"code": 0, "message": "", "data": {"pushid": "turbo-101", "errno": 0}},
                status=200,
            )

        cfg_turbo = _make_config(
            self.tmp_dir,
            {"serverchan": {"enabled": True, "min_severity": "P0", "sendkey": "SCT999888TurboSecret"}},
        )
        multiline_long_title = "熔断警报\n美股暴跌超5%触发危机阈值并且这个标题故意超过三十二个字符用于测试截断"
        msg_p0 = wn.AlertMessage(
            title=multiline_long_title,
            body_md="标普500期货触发盘前熔断",
            severity="P0",
            category="crisis",
        )
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen_sc):
            res_turbo = wn.Notifier(cfg_turbo, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg_p0)[0]

        self.assertEqual(res_turbo.status, "sent")
        self.assertEqual(res_turbo.api_code, 0)
        self.assertEqual(res_turbo.receipt, "turbo-101")
        url_t, payload_t = captured[0]
        self.assertEqual(url_t, "https://sctapi.ftqq.com/SCT999888TurboSecret.send")
        self.assertEqual(payload_t["noip"], 1)
        self.assertNotIn("tags", payload_t)
        self.assertNotIn("\n", payload_t["title"])
        self.assertLessEqual(len(payload_t["title"]), 32)

        # 2. ServerChan SC3 delivery
        captured.clear()
        cfg_sc3 = _make_config(
            self.tmp_dir,
            {"serverchan": {"enabled": True, "min_severity": "P0", "sendkey": "sctp54321tSc3RealSecretKey"}},
        )
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen_sc):
            res_sc3 = wn.Notifier(cfg_sc3, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg_p0)[0]

        self.assertEqual(res_sc3.status, "sent")
        url_3, payload_3 = captured[0]
        self.assertEqual(url_3, "https://54321.push.ft07.com/send/sctp54321tSc3RealSecretKey.send")
        self.assertEqual(payload_3["tags"], "P0|crisis")
        self.assertNotIn("noip", payload_3)
        self.assertNotIn("\n", payload_3["title"])
        self.assertLessEqual(len(payload_3["title"]), 32)

        # 3. Inner data.errno != 0 must fail
        def fake_urlopen_errno(req, timeout=10):
            return _FakeHTTPResponse(
                {"code": 0, "message": "bad", "data": {"errno": 1024}},
                status=200,
            )

        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen_errno):
            res_err = wn.Notifier(cfg_sc3, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg_p0)[0]
        self.assertEqual(res_err.status, "failed")
        self.assertEqual(res_err.attempts, 1)

    def test_serverchan_receipt_never_returns_readkey(self) -> None:
        cfg = _make_config(
            self.tmp_dir,
            {"serverchan": {"enabled": True, "min_severity": "P0", "sendkey": "SCT777666ReadkeyCheck"}},
        )
        msg_p0 = wn.AlertMessage(title="熔断警报", body_md="测试回执不含readkey", severity="P0", category="crisis")

        # 1. Both pushid and readkey present -> returns pushid only
        with mock.patch(
            "scripts.wechat_notify.urllib.request.urlopen",
            return_value=_FakeHTTPResponse(
                {
                    "code": 0,
                    "message": "",
                    "data": {"pushid": "pid-999", "readkey": "SCT_SECRET_READKEY_LEAK_1", "errno": 0},
                },
                status=200,
            ),
        ):
            res_with_pid = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg_p0)[0]
        self.assertEqual(res_with_pid.status, "sent")
        self.assertEqual(res_with_pid.receipt, "pid-999")
        self.assertNotIn("SCT_SECRET_READKEY_LEAK_1", res_with_pid.receipt or "")

        # 2. Only readkey present (no pushid) -> returns "ok", NEVER readkey
        with mock.patch(
            "scripts.wechat_notify.urllib.request.urlopen",
            return_value=_FakeHTTPResponse(
                {
                    "code": 0,
                    "message": "",
                    "data": {"readkey": "SCT_SECRET_READKEY_LEAK_2", "errno": 0},
                },
                status=200,
            ),
        ):
            res_no_pid = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg_p0)[0]
        self.assertEqual(res_no_pid.status, "sent")
        self.assertEqual(res_no_pid.receipt, "ok")
        self.assertNotIn("SCT_SECRET_READKEY_LEAK_2", res_no_pid.receipt or "")

        outbox_raw = cfg.outbox_path.read_text(encoding="utf-8")
        self.assertNotIn("SCT_SECRET_READKEY_LEAK_1", outbox_raw)
        self.assertNotIn("SCT_SECRET_READKEY_LEAK_2", outbox_raw)

    def test_wecom_and_bark_reject_plaintext_http_urls(self) -> None:
        msg = wn.AlertMessage(title="明文拦截", body_md="必须使用HTTPS", severity="P0")

        # Direct helper check for WeCom plaintext http://
        with self.assertRaisesRegex(ValueError, "https://"):
            wn._wecom_url({"webhook_url": "http://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=plain-key-1111"})

        # End-to-end Notifier check: WeCom http:// fails without network call
        cfg_wecom_http = _make_config(
            self.tmp_dir,
            {
                "wecom_webhook": {
                    "enabled": True,
                    "min_severity": "P2",
                    "webhook_url": "http://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=plain-key-2222",
                }
            },
        )
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen") as m_open:
            res_wecom = wn.Notifier(cfg_wecom_http, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg)[0]
        self.assertEqual(res_wecom.status, "failed")
        self.assertIn("https://", res_wecom.error or "")
        self.assertEqual(m_open.call_count, 0)

        # Direct & end-to-end Bark plaintext http:// check
        cfg_bark_http = _make_config(
            self.tmp_dir,
            {
                "bark": {
                    "enabled": True,
                    "min_severity": "P2",
                    "base_url": "http://bark.example.invalid",
                    "device_key": "bark_plain_device_key_3333",
                }
            },
        )
        notifier_bark = wn.Notifier(cfg_bark_http, now_fn=lambda: self.daytime, sleep_fn=lambda _: None)
        with self.assertRaisesRegex(ValueError, "https://"):
            notifier_bark._build_chunks_and_payloads("bark", cfg_bark_http.providers["bark"], msg, self.daytime)

        with mock.patch("scripts.wechat_notify.urllib.request.urlopen") as m_open:
            res_bark = notifier_bark.send(msg)[0]
        self.assertEqual(res_bark.status, "failed")
        self.assertIn("https://", res_bark.error or "")
        self.assertEqual(m_open.call_count, 0)

    def test_bark_levels_and_p0_critical(self) -> None:
        captured: list[tuple[str, dict]] = []

        def fake_urlopen(req, timeout=10):
            captured.append((req.full_url, json.loads(req.data.decode("utf-8"))))
            return _FakeHTTPResponse({"code": 200, "message": "success"}, status=200)

        cfg = _make_config(
            self.tmp_dir,
            {
                "bark": {
                    "enabled": True,
                    "min_severity": "P2",
                    "base_url": "https://bark.example.invalid/",
                    "device_key": "bark_real_device_key_7777",
                }
            },
        )
        notifier = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None)

        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen):
            res_p0 = notifier.send(
                wn.AlertMessage(title="危机熔断", body_md="VIX 突破 40", severity="P0", url="https://example.invalid/vix")
            )[0]
            res_p1 = notifier.send(wn.AlertMessage(title="重要提醒", body_md="沪指突破", severity="P1"))[0]
            res_p2 = notifier.send(wn.AlertMessage(title="常规播报", body_md="午盘播报", severity="P2"))[0]

        self.assertEqual(res_p0.status, "sent")
        self.assertEqual(res_p0.receipt, "bark:ok")
        self.assertEqual(res_p1.status, "sent")
        self.assertEqual(res_p2.status, "sent")

        # P0 -> critical, alarm, volume=10, trailing slash stripped
        self.assertEqual(captured[0][0], "https://bark.example.invalid/push")
        self.assertEqual(captured[0][1]["level"], "critical")
        self.assertEqual(captured[0][1]["sound"], "alarm")
        self.assertEqual(captured[0][1]["volume"], 10)
        self.assertEqual(captured[0][1]["url"], "https://example.invalid/vix")
        # P1 -> timeSensitive, minuet, no volume
        self.assertEqual(captured[1][1]["level"], "timeSensitive")
        self.assertEqual(captured[1][1]["sound"], "minuet")
        self.assertNotIn("volume", captured[1][1])
        # P2 -> active
        self.assertEqual(captured[2][1]["level"], "active")
        self.assertNotIn("volume", captured[2][1])

    def test_macos_osascript_safe_argv_mock(self) -> None:
        cfg = _make_config(
            self.tmp_dir,
            {"macos_osascript": {"enabled": True, "min_severity": "P2"}},
        )
        # Include quotes & shell metacharacters to confirm argv passing (no string interpolation)
        msg_p0 = wn.AlertMessage(
            title='黄金"熔断" $(rm -rf /)',
            body_md="价格跌破\n安全锚 `whoami`",
            severity="P0",
            category="gold",
        )
        msg_p1 = wn.AlertMessage(title="一般提醒", body_md="常规更新", severity="P1", category="market")

        ok_proc = subprocess.CompletedProcess(args=["osascript"], returncode=0, stdout="", stderr="")
        with mock.patch("scripts.wechat_notify.sys.platform", "darwin"):
            with mock.patch("scripts.wechat_notify.subprocess.run", return_value=ok_proc) as m_run:
                notifier = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None)
                res_p0 = notifier.send(msg_p0)[0]
                res_p1 = notifier.send(msg_p1)[0]

        self.assertEqual(res_p0.status, "sent")
        self.assertEqual(res_p0.receipt, "osascript:ok")
        self.assertEqual(res_p1.status, "sent")
        self.assertEqual(m_run.call_count, 2)

        argv_p0 = m_run.call_args_list[0].args[0]
        self.assertEqual(argv_p0[0], "osascript")
        self.assertEqual(argv_p0[1], "-e")
        self.assertIn("on run argv", argv_p0[2])
        self.assertNotIn("$(rm -rf /)", argv_p0[2])
        self.assertEqual(argv_p0[3], "--")
        self.assertEqual(argv_p0[4], msg_p0.title[:100])
        self.assertEqual(argv_p0[5], "价格跌破 安全锚 `whoami`")
        self.assertEqual(argv_p0[6], "P0 · gold")
        self.assertEqual(argv_p0[7], "Ping")

        argv_p1 = m_run.call_args_list[1].args[0]
        self.assertEqual(argv_p1[3], "--")
        self.assertEqual(argv_p1[7], "default")

        # Title starting with "-e" must be safely passed AFTER "--" (end-of-options injection guard)
        msg_flag = wn.AlertMessage(
            title='-e do shell script "id"',
            body_md="参数注入防护校验",
            severity="P0",
            category="security",
        )
        with mock.patch("scripts.wechat_notify.sys.platform", "darwin"):
            with mock.patch("scripts.wechat_notify.subprocess.run", return_value=ok_proc) as m_run_flag:
                res_flag = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg_flag)[0]
        self.assertEqual(res_flag.status, "sent")
        argv_flag = m_run_flag.call_args.args[0]
        self.assertEqual(argv_flag[3], "--")
        self.assertEqual(argv_flag[4], '-e do shell script "id"')
        self.assertEqual(argv_flag.index("--"), 3)

        # Non-zero exit code -> failed
        fail_proc = subprocess.CompletedProcess(args=["osascript"], returncode=1, stdout="", stderr="not authorized")
        with mock.patch("scripts.wechat_notify.sys.platform", "darwin"):
            with mock.patch("scripts.wechat_notify.subprocess.run", return_value=fail_proc):
                res_fail = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg_p1)[0]
        self.assertEqual(res_fail.status, "failed")
        self.assertIn("not authorized", res_fail.error or "")


class TestRetryFailFastAndFanOut(unittest.TestCase):
    """Covers retryable vs fail-fast API/HTTP errors, backoff, pacing, and fail-independent fan-out."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.daytime = _cst(2026, 11, 27, 14, 0)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_wecom_retry_on_45009_and_http_500_vs_fail_fast_40008_and_93000(self) -> None:
        cfg = _make_config(
            self.tmp_dir,
            {
                "wecom_webhook": {
                    "enabled": True,
                    "min_severity": "P2",
                    "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-retry-key-3333",
                }
            },
        )
        msg = wn.AlertMessage(title="重试测试", body_md="内容", severity="P1")

        # 1. Retryable errcode 45009 -> retries then succeeds on 3rd attempt
        sleeps: list[float] = []
        seq_45009 = [
            _FakeHTTPResponse({"errcode": 45009, "errmsg": "freq limit"}, status=200),
            _FakeHTTPResponse({"errcode": 45009, "errmsg": "freq limit"}, status=200),
            _FakeHTTPResponse({"errcode": 0, "errmsg": "ok"}, status=200),
        ]
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=seq_45009):
            res = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=sleeps.append).send(msg)[0]
        self.assertEqual(res.status, "sent")
        self.assertEqual(res.attempts, 3)
        self.assertEqual(sleeps, [1.0, 2.5])

        # 2. Retryable HTTP 500 -> exhausts 3 attempts and fails with backoffs [1.0, 2.5]
        sleeps.clear()
        url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-retry-key-3333"
        seq_500 = [
            _make_http_error(url, 500, "internal error"),
            _make_http_error(url, 500, "internal error"),
            _make_http_error(url, 500, "internal error"),
        ]
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=seq_500):
            res_500 = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=sleeps.append).send(msg)[0]
        self.assertEqual(res_500.status, "failed")
        self.assertEqual(res_500.attempts, 3)
        self.assertEqual(res_500.http_status, 500)
        self.assertEqual(sleeps, [1.0, 2.5])

        # 3. Retryable HTTP 429 & URLError -> recovers on retry
        sleeps.clear()
        seq_net = [
            _make_http_error(url, 429, "too many requests"),
            urllib.error.URLError("temporary dns glitch"),
            _FakeHTTPResponse({"errcode": 0, "errmsg": "ok"}, status=200),
        ]
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=seq_net):
            res_net = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=sleeps.append).send(msg)[0]
        self.assertEqual(res_net.status, "sent")
        self.assertEqual(res_net.attempts, 3)
        self.assertEqual(sleeps, [1.0, 2.5])

        # 4. Fail-fast errcode 40008 and 93000 -> immediate failure, attempts == 1, NO sleep
        for bad_code in (40008, 93000):
            sleeps.clear()
            with mock.patch(
                "scripts.wechat_notify.urllib.request.urlopen",
                return_value=_FakeHTTPResponse({"errcode": bad_code, "errmsg": "invalid request"}, status=200),
            ) as m_open:
                res_ff = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=sleeps.append).send(msg)[0]
            self.assertEqual(res_ff.status, "failed", f"errcode={bad_code} must fail")
            self.assertEqual(res_ff.attempts, 1, f"errcode={bad_code} must fail-fast without retry")
            self.assertEqual(res_ff.api_code, bad_code)
            self.assertEqual(m_open.call_count, 1)
            self.assertEqual(sleeps, [])

    def test_pushplus_retry_on_900_vs_fail_fast_on_905(self) -> None:
        cfg = _make_config(
            self.tmp_dir,
            {
                "pushplus": {
                    "enabled": True,
                    "min_severity": "P2",
                    "token": "pp_retry_token_4444",
                }
            },
        )
        msg = wn.AlertMessage(title="PushPlus 重试测试", body_md="内容", severity="P1")

        # code == 900 is retryable -> succeeds on 2nd attempt
        sleeps: list[float] = []
        seq_900 = [
            _FakeHTTPResponse({"code": 900, "msg": "rate limited"}, status=200),
            _FakeHTTPResponse({"code": 200, "msg": "ok", "data": "rec-ok"}, status=200),
        ]
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=seq_900):
            res_ok = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=sleeps.append).send(msg)[0]
        self.assertEqual(res_ok.status, "sent")
        self.assertEqual(res_ok.attempts, 2)
        self.assertEqual(sleeps, [1.0])

        # code == 905 is fail-fast -> immediate fail, attempts == 1, NO sleep
        sleeps.clear()
        with mock.patch(
            "scripts.wechat_notify.urllib.request.urlopen",
            return_value=_FakeHTTPResponse({"code": 905, "msg": "bad token or quota"}, status=200),
        ) as m_open:
            res_905 = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=sleeps.append).send(msg)[0]
        self.assertEqual(res_905.status, "failed")
        self.assertEqual(res_905.attempts, 1)
        self.assertEqual(res_905.api_code, 905)
        self.assertEqual(m_open.call_count, 1)
        self.assertEqual(sleeps, [])

    def test_wxpusher_fail_fast_codes_vs_retryable(self) -> None:
        cfg = _make_config(
            self.tmp_dir,
            {
                "wxpusher": {
                    "enabled": True,
                    "min_severity": "P2",
                    "app_token": "AT_WXP_TEST_5555",
                    "uids": ["UID_WXP_TEST_5555"],
                }
            },
        )
        msg = wn.AlertMessage(title="WxPusher 重试测试", body_md="内容", severity="P1")

        # Fail-fast on 1001, 1002, 1005
        for code in (1001, 1002, 1005):
            sleeps: list[float] = []
            with mock.patch(
                "scripts.wechat_notify.urllib.request.urlopen",
                return_value=_FakeHTTPResponse({"code": code, "msg": "auth/param err", "success": False}, status=200),
            ):
                res = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=sleeps.append).send(msg)[0]
            self.assertEqual(res.status, "failed")
            self.assertEqual(res.attempts, 1)
            self.assertEqual(sleeps, [])

        # Transient error 5000 retries and succeeds
        sleeps = []
        seq = [
            _FakeHTTPResponse({"code": 5000, "msg": "server busy", "success": False}, status=200),
            _FakeHTTPResponse(
                {"code": 1000, "msg": "ok", "success": True, "data": [{"code": 1000, "messageId": 77}]},
                status=200,
            ),
        ]
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=seq):
            res_ok = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=sleeps.append).send(msg)[0]
        self.assertEqual(res_ok.status, "sent")
        self.assertEqual(res_ok.attempts, 2)
        self.assertEqual(sleeps, [1.0])

    def test_fail_independent_fan_out_and_chunk_pacing(self) -> None:
        cfg = _make_config(
            self.tmp_dir,
            {
                "wecom_webhook": {
                    "enabled": True,
                    "min_severity": "P2",
                    "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-fanout-key-6666",
                },
                "pushplus": {
                    "enabled": True,
                    "min_severity": "P2",
                    "token": "pp_fanout_token_7777",
                },
            },
        )

        def fake_urlopen(req, timeout=10):
            if "qyapi.weixin.qq.com" in req.full_url:
                return _FakeHTTPResponse({"errcode": 93000, "errmsg": "invalid webhook"}, status=200)
            if "pushplus.plus" in req.full_url:
                return _FakeHTTPResponse({"code": 200, "msg": "ok", "data": "pp-fanout-ok"}, status=200)
            raise AssertionError(f"Unexpected URL: {req.full_url}")

        msg = wn.AlertMessage(title="多通道独立扇出", body_md="正文内容", severity="P1")
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen):
            results = wn.Notifier(cfg, now_fn=lambda: self.daytime, sleep_fn=lambda _: None).send(msg)

        by_provider = {r.provider: r for r in results}
        self.assertEqual(set(by_provider), {"wecom_webhook", "pushplus"})
        self.assertEqual(by_provider["wecom_webhook"].status, "failed")
        self.assertEqual(by_provider["wecom_webhook"].api_code, 93000)
        self.assertEqual(by_provider["pushplus"].status, "sent")
        self.assertEqual(by_provider["pushplus"].receipt, "pp-fanout-ok")

        # Both results recorded in outbox
        outbox = _read_outbox(cfg.outbox_path)
        self.assertEqual(len(outbox), 2)
        self.assertEqual({row["provider"]: row["status"] for row in outbox}, {"wecom_webhook": "failed", "pushplus": "sent"})

        # Multi-chunk pacing between chunks for wecom_webhook (3.2s)
        sleeps: list[float] = []
        cfg_pace = _make_config(
            self.tmp_dir,
            {
                "wecom_webhook": {
                    "enabled": True,
                    "min_severity": "P2",
                    "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-pace-key-8888",
                    "msgtype": "text",
                }
            },
        )
        long_msg = wn.AlertMessage(title="节奏测试", body_md="中" * 700, severity="P1")
        with mock.patch(
            "scripts.wechat_notify.urllib.request.urlopen",
            return_value=_FakeHTTPResponse({"errcode": 0, "errmsg": "ok"}, status=200),
        ):
            res_pace = wn.Notifier(cfg_pace, now_fn=lambda: self.daytime, sleep_fn=sleeps.append).send(long_msg)[0]
        self.assertEqual(res_pace.status, "sent")
        self.assertGreaterEqual(res_pace.chunks, 2)
        self.assertEqual(sleeps, [3.2] * (res_pace.chunks - 1))


class TestChunkTextUtf8Safety(unittest.TestCase):
    """Covers UTF-8 byte-safe, char-safe, Markdown-aware Chinese chunking."""

    def test_empty_and_short_text_unsplit(self) -> None:
        self.assertEqual(wn.chunk_text("", max_bytes=100), [""])
        short = "## 午盘播报\n\n上证指数上涨 1.2%。"
        self.assertEqual(wn.chunk_text(short, max_bytes=500, max_chars=200), [short])

    def test_chinese_markdown_and_4byte_emoji_exact_byte_and_char_limits(self) -> None:
        paragraphs = [
            f"### 🚨 第{i}段市场快讯\n- 标普500与沪深300联动波动 📈，黄金红灯门禁严格执行，仓位上限 0%。"
            for i in range(1, 20)
        ]
        doc = "\n\n".join(paragraphs)

        for max_bytes, max_chars in ((240, None), (300, 95), (600, 220)):
            chunks = wn.chunk_text(doc, max_bytes=max_bytes, max_chars=max_chars)
            total = len(chunks)
            self.assertGreater(total, 1)
            for idx, chunk in enumerate(chunks, start=1):
                # Prefix format [i/N]
                expected_prefix = f"[{idx}/{total}] "
                self.assertTrue(chunk.startswith(expected_prefix), f"Missing prefix {expected_prefix!r} in {chunk!r}")
                # Strict UTF-8 round-trip integrity (no broken multi-byte sequences)
                encoded = chunk.encode("utf-8")
                self.assertEqual(encoded.decode("utf-8"), chunk)
                self.assertNotIn("\ufffd", chunk)
                # Strict byte and char caps
                self.assertLessEqual(
                    len(encoded),
                    max_bytes,
                    f"Chunk {idx}/{total} exceeded {max_bytes} bytes: {len(encoded)}",
                )
                if max_chars is not None:
                    self.assertLessEqual(
                        len(chunk),
                        max_chars,
                        f"Chunk {idx}/{total} exceeded {max_chars} chars: {len(chunk)}",
                    )

            # Reconstruct content (ignoring whitespace stripped at split boundaries) -> zero data loss
            rebuilt = "".join(c[len(f"[{i}/{total}] "):] for i, c in enumerate(chunks, start=1))
            self.assertEqual(
                "".join(rebuilt.split()),
                "".join(doc.split()),
                "Chunking dropped or corrupted characters",
            )

    def test_continuous_dense_multibyte_without_newlines(self) -> None:
        # Pure 3-byte Chinese and 4-byte emoji with zero newlines or spaces
        dense = "金🚀银💎铜🔥" * 120
        chunks = wn.chunk_text(dense, max_bytes=120, max_chars=45)
        total = len(chunks)
        self.assertGreater(total, 5)
        stripped_parts: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            prefix = f"[{idx}/{total}] "
            self.assertTrue(chunk.startswith(prefix))
            encoded = chunk.encode("utf-8")
            self.assertEqual(encoded.decode("utf-8"), chunk)
            self.assertLessEqual(len(encoded), 120)
            self.assertLessEqual(len(chunk), 45)
            stripped_parts.append(chunk[len(prefix):])
        self.assertEqual("".join(stripped_parts), dense)


class TestQuietHoursAndSeverity(unittest.TestCase):
    """Covers overnight quiet-hours wrap-around (23:30-07:15 CST), P0 override, and severity filtering."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_is_in_quiet_hours_overnight_and_same_day_boundaries(self) -> None:
        # Overnight wrap-around 23:30-07:15
        self.assertFalse(wn.is_in_quiet_hours(_cst(2026, 11, 27, 23, 29), "23:30", "07:15"))
        self.assertTrue(wn.is_in_quiet_hours(_cst(2026, 11, 27, 23, 30), "23:30", "07:15"))
        self.assertTrue(wn.is_in_quiet_hours(_cst(2026, 11, 28, 0, 0), "23:30", "07:15"))
        self.assertTrue(wn.is_in_quiet_hours(_cst(2026, 11, 28, 3, 45), "23:30", "07:15"))
        self.assertTrue(wn.is_in_quiet_hours(_cst(2026, 11, 28, 7, 14), "23:30", "07:15"))
        self.assertFalse(wn.is_in_quiet_hours(_cst(2026, 11, 28, 7, 15), "23:30", "07:15"))
        self.assertFalse(wn.is_in_quiet_hours(_cst(2026, 11, 28, 12, 0), "23:30", "07:15"))

        # Same-day window 12:00-13:00
        self.assertFalse(wn.is_in_quiet_hours(_cst(2026, 11, 27, 11, 59), "12:00", "13:00"))
        self.assertTrue(wn.is_in_quiet_hours(_cst(2026, 11, 27, 12, 0), "12:00", "13:00"))
        self.assertTrue(wn.is_in_quiet_hours(_cst(2026, 11, 27, 12, 59), "12:00", "13:00"))
        self.assertFalse(wn.is_in_quiet_hours(_cst(2026, 11, 27, 13, 0), "12:00", "13:00"))

        # Equal start & end disables quiet window
        self.assertFalse(wn.is_in_quiet_hours(_cst(2026, 11, 27, 0, 0), "00:00", "00:00"))

    def test_quiet_hours_suppresses_p1_p2_and_p0_always_overrides(self) -> None:
        cfg = _make_config(
            self.tmp_dir,
            {
                "wecom_webhook": {
                    "enabled": True,
                    "min_severity": "P2",
                    "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-quiet-key-9999",
                }
            },
            quiet_enabled=True,
            quiet_start="23:30",
            quiet_end="07:15",
        )

        # Test both sides of midnight: 23:45 CST and 03:20 CST
        for quiet_dt in (_cst(2026, 11, 27, 23, 45), _cst(2026, 11, 28, 3, 20)):
            with mock.patch(
                "scripts.wechat_notify.urllib.request.urlopen",
                return_value=_FakeHTTPResponse({"errcode": 0, "errmsg": "ok"}, status=200),
            ) as m_open:
                notifier = wn.Notifier(cfg, now_fn=lambda dt=quiet_dt: dt, sleep_fn=lambda _: None)

                # P1 & P2 suppressed without network call
                r_p1 = notifier.send(wn.AlertMessage(title="夜间P1", body_md="次要提醒", severity="P1"))[0]
                r_p2 = notifier.send(wn.AlertMessage(title="夜间P2", body_md="常规提醒", severity="P2"))[0]
                self.assertEqual(r_p1.status, "suppressed_quiet")
                self.assertEqual(r_p1.chunks, 0)
                self.assertEqual(r_p1.attempts, 0)
                self.assertEqual(r_p2.status, "suppressed_quiet")
                self.assertEqual(m_open.call_count, 0)

                # P0 ALWAYS overrides quiet hours even when bypass_quiet_hours=False
                r_p0 = notifier.send(
                    wn.AlertMessage(
                        title="夜间P0危机熔断",
                        body_md="美股触发一级熔断",
                        severity="P0",
                        bypass_quiet_hours=False,
                    )
                )[0]
                self.assertEqual(r_p0.status, "sent")
                self.assertEqual(m_open.call_count, 1)

        outbox = _read_outbox(cfg.outbox_path)
        self.assertEqual(len(outbox), 6)
        statuses = [row["status"] for row in outbox]
        self.assertEqual(
            statuses,
            ["suppressed_quiet", "suppressed_quiet", "sent", "suppressed_quiet", "suppressed_quiet", "sent"],
        )

        # Explicit bypass_quiet_hours=True on P2 also overrides quiet hours
        with mock.patch(
            "scripts.wechat_notify.urllib.request.urlopen",
            return_value=_FakeHTTPResponse({"errcode": 0, "errmsg": "ok"}, status=200),
        ) as m_open:
            notifier = wn.Notifier(cfg, now_fn=lambda: _cst(2026, 11, 28, 2, 0), sleep_fn=lambda _: None)
            r_bypass = notifier.send(
                wn.AlertMessage(title="测试直通", body_md="连通测试", severity="P2", bypass_quiet_hours=True)
            )[0]
            self.assertEqual(r_bypass.status, "sent")
            self.assertEqual(m_open.call_count, 1)

    def test_min_severity_filtering_and_invalid_severity(self) -> None:
        cfg = _make_config(
            self.tmp_dir,
            {
                "serverchan": {
                    "enabled": True,
                    "min_severity": "P0",
                    "sendkey": "SCT00001111ServerChan",
                }
            },
        )
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen") as m_open:
            notifier = wn.Notifier(cfg, now_fn=lambda: _cst(2026, 11, 27, 11, 0), sleep_fn=lambda _: None)
            res = notifier.send(wn.AlertMessage(title="仅P1", body_md="不触发P0通道", severity="P1"))[0]
        self.assertEqual(res.status, "skipped_severity")
        self.assertEqual(m_open.call_count, 0)

        with self.assertRaises(ValueError):
            wn.AlertMessage(title="坏级别", body_md="x", severity="P9").normalized_severity()


class TestDeduplicationCooldown(unittest.TestCase):
    """Covers per-provider cooldown deduplication, expiry, failure non-commit, and stale pruning."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_dedupe_suppresses_within_cooldown_and_releases_after_expiry(self) -> None:
        cfg = _make_config(
            self.tmp_dir,
            {
                "wecom_webhook": {
                    "enabled": True,
                    "min_severity": "P2",
                    "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-dedupe-key-1212",
                },
                "pushplus": {
                    "enabled": True,
                    "min_severity": "P2",
                    "token": "pp_dedupe_token_3434",
                },
            },
            cooldown_seconds={"P0": 300, "P1": 900, "P2": 3600},
        )

        clock = [_cst(2026, 11, 27, 10, 0, 0)]

        def fake_urlopen(req, timeout=10):
            if "qyapi.weixin.qq.com" in req.full_url:
                return _FakeHTTPResponse({"errcode": 0, "errmsg": "ok"}, status=200)
            return _FakeHTTPResponse({"code": 200, "msg": "ok", "data": "pp-ok"}, status=200)

        msg_a = wn.AlertMessage(title="黄金红灯锁", body_md="禁止追高", severity="P1", dedupe_key="gold:red_lock")
        msg_b = wn.AlertMessage(title="另一信号", body_md="沪指突破", severity="P1", dedupe_key="a_share:breakout")

        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen) as m_open:
            notifier = wn.Notifier(cfg, now_fn=lambda: clock[0], sleep_fn=lambda _: None)

            # 1. First send at T0 on wecom_webhook only -> sent
            r1 = notifier.send(msg_a, providers=["wecom_webhook"])[0]
            self.assertEqual(r1.status, "sent")
            self.assertEqual(m_open.call_count, 1)

            # 2. Repeat at T0 + 120s (<900s) -> suppressed_dedupe on wecom_webhook, BUT pushplus still sends!
            clock[0] = clock[0] + timedelta(seconds=120)
            r2_list = notifier.send(msg_a, providers=["wecom_webhook", "pushplus"])
            r2_map = {r.provider: r for r in r2_list}
            self.assertEqual(r2_map["wecom_webhook"].status, "suppressed_dedupe")
            self.assertEqual(r2_map["pushplus"].status, "sent")
            self.assertEqual(m_open.call_count, 2)

            # 3. Different dedupe_key on wecom_webhook within window -> sent
            r3 = notifier.send(msg_b, providers=["wecom_webhook"])[0]
            self.assertEqual(r3.status, "sent")
            self.assertEqual(m_open.call_count, 3)

            # 4. After P1 cooldown expires (T0 + 901s) -> wecom_webhook sends msg_a again
            clock[0] = _cst(2026, 11, 27, 10, 0, 0) + timedelta(seconds=901)
            r4 = notifier.send(msg_a, providers=["wecom_webhook"])[0]
            self.assertEqual(r4.status, "sent")
            self.assertEqual(m_open.call_count, 4)

        outbox = _read_outbox(cfg.outbox_path)
        self.assertIn("suppressed_dedupe", [row["status"] for row in outbox])

    def test_failed_and_dry_run_do_not_commit_dedupe_and_stale_entries_pruned(self) -> None:
        cfg = _make_config(
            self.tmp_dir,
            {
                "wecom_webhook": {
                    "enabled": True,
                    "min_severity": "P2",
                    "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=wecom-dedupe-key-5656",
                }
            },
        )
        now = _cst(2026, 11, 27, 10, 0, 0)
        # Seed a stale entry >48h old in dedupe file
        cfg.dedupe_path.write_text(
            json.dumps({"wecom_webhook:stale_key": (now - timedelta(hours=50)).timestamp()}),
            encoding="utf-8",
        )
        msg = wn.AlertMessage(title="去重边界", body_md="内容", severity="P1", dedupe_key="edge:key")

        # Dry run must not commit dedupe key
        r_dry = wn.Notifier(cfg, dry_run=True, now_fn=lambda: now, sleep_fn=lambda _: None).send(msg)[0]
        self.assertEqual(r_dry.status, "dry_run")

        # Failed send must not commit dedupe key
        with mock.patch(
            "scripts.wechat_notify.urllib.request.urlopen",
            return_value=_FakeHTTPResponse({"errcode": 93000, "errmsg": "bad"}, status=200),
        ):
            r_fail = wn.Notifier(cfg, now_fn=lambda: now, sleep_fn=lambda _: None).send(msg)[0]
        self.assertEqual(r_fail.status, "failed")

        # Subsequent real send succeeds immediately (not suppressed) and prunes >48h stale entry
        with mock.patch(
            "scripts.wechat_notify.urllib.request.urlopen",
            return_value=_FakeHTTPResponse({"errcode": 0, "errmsg": "ok"}, status=200),
        ):
            r_ok = wn.Notifier(cfg, now_fn=lambda: now, sleep_fn=lambda _: None).send(msg)[0]
        self.assertEqual(r_ok.status, "sent")

        dedupe_state = json.loads(cfg.dedupe_path.read_text(encoding="utf-8"))
        self.assertNotIn("wecom_webhook:stale_key", dedupe_state)
        self.assertIn("wecom_webhook:edge:key", dedupe_state)


class TestSecretSecurityAndRedaction(unittest.TestCase):
    """Covers config path guardrails (git-tracked, gold/, equity/), chmod warnings, and secret redaction."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_refuses_git_tracked_config_files(self) -> None:
        missing_env = self.tmp_dir / "nonexistent.env"

        # 1. Real git-tracked file in automations/ (passes without mocks in any commit state)
        tracked_file = wn.REPO_ROOT / "automations" / "permissions.json"
        self.assertTrue(tracked_file.is_file())
        with self.assertRaisesRegex(ValueError, "git-tracked"):
            wn.load_notify_config(config_path=tracked_file, dotenv_path=missing_env, env={})

        # 2. automations/notify.example.json (must be refused whenever git-tracked)
        example_file = wn.REPO_ROOT / "automations" / "notify.example.json"
        self.assertTrue(example_file.is_file())
        if wn._is_git_tracked(example_file):
            with self.assertRaisesRegex(ValueError, "git-tracked"):
                wn.load_notify_config(config_path=example_file, dotenv_path=missing_env, env={})

        # Also deterministically verify git-tracked refusal for automations/notify.example.json
        # even in a pre-commit working tree before `git add automations/notify.example.json`.
        fake_tracked = subprocess.CompletedProcess(args=["git"], returncode=0)
        with mock.patch("scripts.wechat_notify.subprocess.run", return_value=fake_tracked) as m_git:
            with self.assertRaisesRegex(ValueError, "git-tracked"):
                wn.load_notify_config(config_path=example_file, dotenv_path=missing_env, env={})
        self.assertIn("automations/notify.example.json", m_git.call_args.args[0])

        # Also refused if passed as dotenv_path
        with self.assertRaisesRegex(ValueError, "git-tracked"):
            wn.load_notify_config(config_path=self.tmp_dir / "missing.json", dotenv_path=tracked_file, env={})

    def test_refuses_any_file_inside_gold_or_equity(self) -> None:
        missing_env = self.tmp_dir / "nonexistent.env"

        # Existing files inside gold/ and equity/
        gold_file = wn.REPO_ROOT / "gold" / "data_snapshot.json"
        equity_file = wn.REPO_ROOT / "equity" / "state" / "market_state.json"
        self.assertTrue(gold_file.is_file())
        self.assertTrue(equity_file.is_file())

        with self.assertRaisesRegex(ValueError, "published data directory"):
            wn.load_notify_config(config_path=gold_file, dotenv_path=missing_env, env={})
        with self.assertRaisesRegex(ValueError, "published data directory"):
            wn.load_notify_config(config_path=equity_file, dotenv_path=missing_env, env={})

        # Untracked hypothetical paths inside gold/ and equity/
        with self.assertRaisesRegex(ValueError, "published data directory"):
            wn._validate_secret_config_path(wn.REPO_ROOT / "gold" / "untracked_notify.json")
        with self.assertRaisesRegex(ValueError, "published data directory"):
            wn._validate_secret_config_path(wn.REPO_ROOT / "equity" / "state" / "untracked_notify.json")

        # Symlink outside repo pointing into gold/ is resolved and still refused
        symlink_path = self.tmp_dir / "sneaky_link.json"
        symlink_path.symlink_to(gold_file)
        with self.assertRaisesRegex(ValueError, "published data directory"):
            wn.load_notify_config(config_path=symlink_path, dotenv_path=missing_env, env={})

    def test_is_git_tracked_fails_closed_when_git_missing(self) -> None:
        repo_path = wn.REPO_ROOT / "untracked_secret_config.json"
        outside_path = self.tmp_dir / "outside_notify.json"

        with mock.patch("scripts.wechat_notify.subprocess.run", side_effect=FileNotFoundError("git not installed")):
            # Inside REPO_ROOT: fail-closed -> treated as tracked (True) and refused
            self.assertTrue(wn._is_git_tracked(repo_path))
            with self.assertRaisesRegex(ValueError, "git-tracked"):
                wn._validate_secret_config_path(repo_path)
            # Outside REPO_ROOT: returns False without invoking git
            self.assertFalse(wn._is_git_tracked(outside_path))

    def test_refuses_untracked_repo_config_and_worktree_state_paths(self) -> None:
        untracked_proc = subprocess.CompletedProcess(args=["git"], returncode=1)
        untracked_repo_json = wn.REPO_ROOT / "untracked_local_notify.json"
        nested_repo_dotenv = wn.REPO_ROOT / "scripts" / ".env.notify"
        root_dotenv = wn.REPO_ROOT / ".env.notify"

        with mock.patch("scripts.wechat_notify.subprocess.run", return_value=untracked_proc):
            # Untracked JSON config anywhere inside REPO_ROOT is refused
            with self.assertRaisesRegex(ValueError, "repository working tree"):
                wn._validate_secret_config_path(untracked_repo_json, allow_repo_dotenv=False)
            # Even with allow_repo_dotenv=True, only REPO_ROOT/.env.notify is permitted
            with self.assertRaisesRegex(ValueError, "repository working tree"):
                wn._validate_secret_config_path(nested_repo_dotenv, allow_repo_dotenv=True)
            wn._validate_secret_config_path(root_dotenv, allow_repo_dotenv=True)

        # outbox_path and dedupe_path inside REPO_ROOT working tree are refused via helper & load_notify_config
        with self.assertRaisesRegex(ValueError, "repository working tree"):
            wn._validate_state_output_path(wn.REPO_ROOT / "notify_outbox.jsonl", "outbox_path")
        with self.assertRaisesRegex(ValueError, "repository working tree"):
            wn._validate_state_output_path(wn.REPO_ROOT / "gold" / "notify_dedupe.json", "dedupe_path")

        missing_cfg = self.tmp_dir / "missing.json"
        missing_env = self.tmp_dir / "missing.env"
        with self.assertRaisesRegex(ValueError, "repository working tree"):
            wn.load_notify_config(
                config_path=missing_cfg,
                dotenv_path=missing_env,
                env={"GIR_NOTIFY_OUTBOX_PATH": str(wn.REPO_ROOT / "outbox.jsonl")},
            )
        with self.assertRaisesRegex(ValueError, "repository working tree"):
            wn.load_notify_config(
                config_path=missing_cfg,
                dotenv_path=missing_env,
                env={"GIR_NOTIFY_DEDUPE_PATH": str(wn.REPO_ROOT / "equity" / "dedupe.json")},
            )

        # .git/ and external temp directories are permitted for state output paths
        wn._validate_state_output_path(wn.REPO_ROOT / ".git" / "notify_outbox.jsonl", "outbox_path")
        wn._validate_state_output_path(self.tmp_dir / "notify_dedupe.json", "dedupe_path")

    def test_bark_base_url_credentials_are_redacted(self) -> None:
        bark_user = "barkAdminUser"
        bark_pass = "SuperSecretBarkPass9988"
        bark_key = "BARK_DEV_KEY_5544"
        bark_url = f"https://{bark_user}:{bark_pass}@bark.example.invalid"

        cfg = _make_config(
            self.tmp_dir,
            {
                "bark": {
                    "enabled": True,
                    "min_severity": "P2",
                    "base_url": bark_url,
                    "device_key": bark_key,
                }
            },
        )
        secrets = wn._collect_secrets(cfg)
        self.assertIn(f"{bark_user}:{bark_pass}", secrets)
        self.assertIn(bark_user, secrets)
        self.assertIn(bark_pass, secrets)

        redacted = wn.redact_text(f"POST {bark_url}/push failed for {bark_user} / {bark_pass}", secrets)
        self.assertNotIn(bark_user, redacted)
        self.assertNotIn(bark_pass, redacted)
        self.assertIn("bark.example.invalid", redacted)

        # End-to-end leaky HTTP error containing full Bark URL credentials -> scrubbed from result & outbox
        def fake_leaky_bark(req, timeout=10):
            raise _make_http_error(req.full_url, 401, f"unauthorized at {bark_url}/push user={bark_user} pass={bark_pass}")

        msg = wn.AlertMessage(title="Bark凭证脱敏", body_md="正文", severity="P1")
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_leaky_bark):
            res = wn.Notifier(cfg, now_fn=lambda: _cst(2026, 11, 27, 15, 0), sleep_fn=lambda _: None).send(msg)[0]

        self.assertEqual(res.status, "failed")
        self.assertNotIn(bark_user, res.error or "")
        self.assertNotIn(bark_pass, res.error or "")
        outbox_raw = cfg.outbox_path.read_text(encoding="utf-8")
        self.assertNotIn(bark_user, outbox_raw)
        self.assertNotIn(bark_pass, outbox_raw)

    def test_permission_warning_placeholders_and_env_overrides(self) -> None:
        # Copy automations/notify.example.json outside git to test placeholder handling & chmod check
        example_text = (wn.REPO_ROOT / "automations" / "notify.example.json").read_text(encoding="utf-8")
        cfg_file = self.tmp_dir / "notify.json"
        cfg_file.write_text(example_text, encoding="utf-8")
        os.chmod(cfg_file, 0o644)

        cfg_warn = wn.load_notify_config(
            config_path=cfg_file,
            dotenv_path=self.tmp_dir / "missing.env",
            env={},
        )
        self.assertTrue(any("chmod 600" in w for w in cfg_warn.warnings))
        doc = wn.run_doctor(cfg_warn)
        for p in ("wecom_webhook", "wxpusher", "pushplus", "serverchan", "bark"):
            self.assertFalse(doc["providers"][p]["ready"])

        # Tightening to 0o600 clears warning; env overrides providers & quiet hours
        os.chmod(cfg_file, 0o600)
        cfg_ok = wn.load_notify_config(
            config_path=cfg_file,
            dotenv_path=self.tmp_dir / "missing.env",
            env={
                "GIR_NOTIFY_WECOM_WEBHOOK_URL": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=env-secret-key-4321",
                "GIR_NOTIFY_QUIET_HOURS": "22:45-06:30",
                "GIR_NOTIFY_PROVIDERS": "wecom_webhook",
            },
        )
        self.assertEqual(cfg_ok.warnings, [])
        self.assertTrue(cfg_ok.quiet_enabled)
        self.assertEqual((cfg_ok.quiet_start, cfg_ok.quiet_end), ("22:45", "06:30"))
        self.assertTrue(cfg_ok.providers["wecom_webhook"]["enabled"])
        self.assertFalse(cfg_ok.providers["macos_osascript"]["enabled"])

    def test_redacts_secrets_and_webhook_query_keys_from_errors_and_outbox(self) -> None:
        wecom_key = "SUPER_SECRET_WECOM_KEY_9876"
        wecom_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={wecom_key}"
        wxp_token = "AT_SUPER_SECRET_WXP_TOKEN_5432"
        wxp_uid = "UID_PRIVATE_TARGET_1111"
        pp_token = "PP_SUPER_SECRET_TOKEN_2468"
        sc_key = "sctp99887tSUPERSECRETSCK3333"
        bark_key = "BARK_SUPER_SECRET_DEVICE_7777"

        cfg = _make_config(
            self.tmp_dir,
            {
                "wecom_webhook": {"enabled": True, "min_severity": "P2", "webhook_url": wecom_url},
                "wxpusher": {"enabled": True, "min_severity": "P2", "app_token": wxp_token, "uids": [wxp_uid]},
                "pushplus": {"enabled": True, "min_severity": "P2", "token": pp_token},
                "serverchan": {"enabled": True, "min_severity": "P2", "sendkey": sc_key},
                "bark": {"enabled": True, "min_severity": "P2", "device_key": bark_key},
            },
        )

        # Direct redact_text check including inline ?key=... and &key=...
        sample = (
            f"POST {wecom_url}&foo=1 failed; alt https://host/hook?a=1&key=INLINE_QUERY_SECRET_ABCD "
            f"tokens={wxp_token} {wxp_uid} {pp_token} {sc_key} {bark_key}"
        )
        redacted = wn.redact_text(sample, wn._collect_secrets(cfg))
        for raw_secret in (wecom_key, "INLINE_QUERY_SECRET_ABCD", wxp_token, wxp_uid, pp_token, sc_key, bark_key):
            self.assertNotIn(raw_secret, redacted)
        self.assertIn("***", redacted)

        # End-to-end error echoes EVERY secret back from remote APIs / HTTP errors
        def fake_urlopen_leaky(req, timeout=10):
            if "qyapi.weixin.qq.com" in req.full_url:
                raise _make_http_error(req.full_url, 400, f"bad request for {wecom_url}")
            if "wxpusher" in req.full_url:
                return _FakeHTTPResponse(
                    {"code": 1001, "msg": f"invalid appToken={wxp_token} uid={wxp_uid}", "success": False},
                    status=200,
                )
            if "pushplus" in req.full_url:
                return _FakeHTTPResponse(
                    {"code": 905, "msg": f"token rejected: {pp_token}"},
                    status=200,
                )
            if "push.ft07.com" in req.full_url:
                return _FakeHTTPResponse(
                    {"code": 40001, "message": f"bad sendkey {sc_key}"},
                    status=200,
                )
            if "api.day.app" in req.full_url:
                raise _make_http_error(req.full_url, 403, f"forbidden device_key={bark_key}")
            raise AssertionError(f"Unexpected URL: {req.full_url}")

        msg = wn.AlertMessage(title="脱敏验证", body_md="正文", severity="P1")
        with mock.patch("scripts.wechat_notify.urllib.request.urlopen", side_effect=fake_urlopen_leaky):
            results = wn.Notifier(cfg, now_fn=lambda: _cst(2026, 11, 27, 15, 0), sleep_fn=lambda _: None).send(msg)

        self.assertEqual(len(results), 5)
        all_secrets = (wecom_key, wxp_token, wxp_uid, pp_token, sc_key, bark_key)
        for res in results:
            self.assertEqual(res.status, "failed")
            self.assertIsNotNone(res.error)
            for secret in all_secrets:
                self.assertNotIn(secret, res.error or "", f"Leaked secret in {res.provider} error")

        outbox_raw = cfg.outbox_path.read_text(encoding="utf-8")
        for secret in all_secrets:
            self.assertNotIn(secret, outbox_raw, f"Leaked secret in notify_outbox.jsonl")

        doctor_raw = json.dumps(wn.run_doctor(cfg), ensure_ascii=False)
        for secret in all_secrets:
            self.assertNotIn(secret, doctor_raw, "Leaked secret in run_doctor report")


class TestCliSmoke(unittest.TestCase):
    """Covers CLI --doctor and --dry-run (both in-process and subprocess smoke tests)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.outbox = self.tmp_dir / "outbox.jsonl"
        self.dedupe = self.tmp_dir / "dedupe.json"
        self.cfg_path = self.tmp_dir / "notify.json"
        cfg_data = {
            "quiet_hours": {"enabled": False, "start": "23:30", "end": "07:15"},
            "outbox_path": str(self.outbox),
            "dedupe_path": str(self.dedupe),
            "providers": {
                "wecom_webhook": {
                    "enabled": True,
                    "min_severity": "P2",
                    "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=CLI_SECRET_KEY_2026",
                    "msgtype": "markdown",
                },
                "serverchan": {
                    "enabled": True,
                    "min_severity": "P0",
                    "sendkey": "sctp10001tCLISecretSendkey",
                },
                "macos_osascript": {
                    "enabled": False,
                    "min_severity": "P1",
                },
            },
        }
        self.cfg_path.write_text(json.dumps(cfg_data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(self.cfg_path, 0o600)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cli_main_doctor_and_dry_run_in_process(self) -> None:
        clean_env = {"PATH": os.environ.get("PATH", "")}
        missing_dotenv = self.tmp_dir / "missing.env"

        with mock.patch.dict(os.environ, clean_env, clear=True), mock.patch.object(
            wn, "DEFAULT_DOTENV_PATH", missing_dotenv
        ), mock.patch(
            "scripts.wechat_notify.urllib.request.urlopen",
            side_effect=AssertionError("Network must NOT be called during --doctor or --dry-run"),
        ):
            # 1. --doctor
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = wn.main(["--config", str(self.cfg_path), "--doctor"])
            self.assertEqual(rc, 0)
            self.assertEqual(stderr.getvalue(), "")
            doc = json.loads(stdout.getvalue())
            self.assertEqual(doc["config_source"], str(self.cfg_path))
            self.assertTrue(doc["providers"]["wecom_webhook"]["ready"])
            self.assertTrue(doc["providers"]["serverchan"]["ready"])
            self.assertNotIn("CLI_SECRET_KEY_2026", stdout.getvalue())
            self.assertNotIn("CLISecretSendkey", stdout.getvalue())

            # 2. --dry-run with explicit --title / --body / --severity
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = wn.main(
                    [
                        "--config",
                        str(self.cfg_path),
                        "--dry-run",
                        "--severity",
                        "P1",
                        "--title",
                        "干跑自检",
                        "--body",
                        "验证本地渲染与落盘",
                        "--provider",
                        "wecom_webhook",
                    ]
                )
            self.assertEqual(rc, 0)
            res_list = json.loads(stdout.getvalue())
            self.assertEqual(len(res_list), 1)
            self.assertEqual(res_list[0]["provider"], "wecom_webhook")
            self.assertEqual(res_list[0]["status"], "dry_run")
            self.assertEqual(res_list[0]["chunks"], 1)
            self.assertEqual(res_list[0]["attempts"], 0)
            self.assertFalse(self.outbox.exists())
            self.assertFalse(self.dedupe.exists())

            # 3. --dry-run --test
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = wn.main(["--config", str(self.cfg_path), "--dry-run", "--test"])
            self.assertEqual(rc, 0)
            test_res = {r["provider"]: r["status"] for r in json.loads(stdout.getvalue())}
            self.assertEqual(test_res["wecom_webhook"], "dry_run")
            self.assertEqual(test_res["serverchan"], "skipped_severity")

            # 4. Missing --title returns exit code 2
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = wn.main(["--config", str(self.cfg_path), "--dry-run"])
            self.assertEqual(rc, 2)
            self.assertIn("--title is required", stderr.getvalue())

            # 5. Refused git-tracked config returns exit code 2
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                rc = wn.main(["--config", str(wn.REPO_ROOT / "automations" / "permissions.json"), "--doctor"])
            self.assertEqual(rc, 2)
            self.assertIn("[FAIL] Config error:", stderr.getvalue())

    def test_cli_subprocess_doctor_and_dry_run_smoke(self) -> None:
        script = wn.REPO_ROOT / "scripts" / "wechat_notify.py"
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.tmp_dir),
            "PYTHONUTF8": "1",
        }

        proc_doc = subprocess.run(
            [sys.executable, str(script), "--config", str(self.cfg_path), "--doctor"],
            cwd=wn.REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(proc_doc.returncode, 0, proc_doc.stderr)
        doc = json.loads(proc_doc.stdout)
        self.assertTrue(doc["providers"]["wecom_webhook"]["ready"])
        self.assertNotIn("CLI_SECRET_KEY_2026", proc_doc.stdout)

        proc_dry = subprocess.run(
            [
                sys.executable,
                str(script),
                "--config",
                str(self.cfg_path),
                "--dry-run",
                "--severity",
                "P0",
                "--title",
                "子进程干跑",
                "--body",
                "零联网冒烟验证",
            ],
            cwd=wn.REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(proc_dry.returncode, 0, proc_dry.stderr)
        results = json.loads(proc_dry.stdout)
        self.assertEqual({r["provider"]: r["status"] for r in results}, {"wecom_webhook": "dry_run", "serverchan": "dry_run"})
        self.assertFalse(self.outbox.exists())
        self.assertFalse(self.dedupe.exists())


    def test_wecom_and_bark_case_insensitive_non_https_refused(self) -> None:
        with self.assertRaises(ValueError):
            wn._wecom_url({"webhook_url": "HTTP://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc"})
        with self.assertRaises(ValueError):
            wn._wecom_url({"webhook_url": "ftp://example.com/hook"})
        self.assertTrue(
            wn._wecom_url({"webhook_url": "HTTPS://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc"}).startswith("HTTPS://")
        )

    def test_placeholder_detection_catches_short_replace_tokens(self) -> None:
        for tok in ("AT_REPLACE_WITH_WXPUSHER_TOKEN", "REPLACE_WITH_YOUR_UID", "REPLACE_ME", "YOUR_KEY", "..."):
            self.assertTrue(wn._is_placeholder(tok), f"Expected placeholder rejected: {tok}")
        self.assertFalse(wn._is_placeholder("AT_realLiveToken99887766"))

    def test_corrupt_dedupe_json_recovers_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            cfg = _make_config(
                tdir,
                {"wecom_webhook": {"enabled": True, "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=TESTKEY99", "min_severity": "P2"}},
            )
            cfg.dedupe_path.write_text("{corrupt non-json payload!!!", encoding="utf-8")
            notifier = wn.Notifier(cfg, dry_run=False, now_fn=lambda: _cst(2026, 11, 27, 14, 0))
            msg = wn.AlertMessage(
                title="损坏去重文件恢复测试",
                body_md="正文内容",
                severity="P1",
                dedupe_key="recover_corrupt_dedupe_001",
            )
            with mock.patch("urllib.request.urlopen", return_value=_FakeHTTPResponse({"errcode": 0, "errmsg": "ok"})):
                results = notifier.send(msg)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, "sent")
            repaired = json.loads(cfg.dedupe_path.read_text(encoding="utf-8"))
            self.assertIsInstance(repaired, dict)
            self.assertIn("wecom_webhook:recover_corrupt_dedupe_001", repaired)

    def test_serverchan_appends_msg_url_when_missing_and_avoids_duplication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            cfg = _make_config(
                tdir,
                {"serverchan": {"enabled": True, "sendkey": "SCT999888testkey", "min_severity": "P2"}},
            )
            notifier = wn.Notifier(cfg, dry_run=False, now_fn=lambda: _cst(2026, 11, 27, 14, 0))
            captured_bodies: list[dict] = []

            def _fake_open(req, timeout=15):
                raw = req.data.decode("utf-8") if req.data else "{}"
                captured_bodies.append(json.loads(raw))
                return _FakeHTTPResponse({"code": 0, "message": "success"})

            target_url = "https://nanless.github.io/global-investment-research/daily/a-share-latest.html"
            with mock.patch("urllib.request.urlopen", side_effect=_fake_open):
                res1 = notifier.send(
                    wn.AlertMessage(
                        title="附带链接测试一",
                        body_md="市场跟踪快报正文",
                        severity="P1",
                        url=target_url,
                        dedupe_key="sc_url_append_1",
                    )
                )
                res2 = notifier.send(
                    wn.AlertMessage(
                        title="附带链接测试二",
                        body_md=f"正文已含链接：{target_url}",
                        severity="P1",
                        url=target_url,
                        dedupe_key="sc_url_append_2",
                    )
                )
            self.assertEqual(res1[0].status, "sent")
            self.assertEqual(res2[0].status, "sent")
            self.assertEqual(len(captured_bodies), 2)
            self.assertIn(f"详情链接：{target_url}", captured_bodies[0]["desp"])
            self.assertEqual(captured_bodies[1]["desp"].count(target_url), 1)
            self.assertNotIn("详情链接：", captured_bodies[1]["desp"])


if __name__ == "__main__":
    unittest.main()
