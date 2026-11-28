#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""100%-offline unit test suite for scripts/realtime_monitor.py (ZERO network calls)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import plistlib
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from scripts import realtime_monitor as rm, state_transaction


def _cst(year: int, month: int, day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=rm.CST)


def _tick(
    symbol: str,
    last: float,
    change_pct: float,
    *,
    name: str | None = None,
    prev_close: float | None = None,
    change_bp: float | None = None,
    is_yield: bool = False,
    timestamp: str = "",
) -> rm.QuoteTick:
    if prev_close is None:
        if is_yield and change_bp is not None:
            prev_close = round(last - change_bp / 100.0, 4)
        else:
            denom = 1.0 + change_pct / 100.0
            prev_close = round(last / denom, 4) if denom else last
    return rm.QuoteTick(
        symbol=symbol,
        name=name or symbol,
        last=last,
        prev_close=prev_close,
        change_pct=change_pct,
        change_bp=change_bp,
        timestamp=timestamp,
        is_yield=is_yield,
    )


def _signal(
    *,
    signal_id: str = "sig-001",
    cluster_key: str = "cn_pboc:abc123",
    domain_id: str = "cn_pboc",
    region: str = "CN",
    domain_label: str = "A股政策市 · 央行货币与流动性",
    title: str = "中国人民银行宣布降准0.5个百分点",
    body: str = "中国人民银行宣布全面降准0.5个百分点，向市场提供长期流动性约1万亿元。",
    sources: list[str] | None = None,
    severity: str = "P1",
    score: int = 76,
    s_auth: int = 40,
    s_confirm: int = 20,
    s_spillover: int = 16,
    k_verify: float = 1.0,
    is_official: bool = True,
    is_rumor_capped: bool = False,
    is_flash_unverified: bool = False,
    is_divergence: bool = False,
    is_market_closed_floor: bool = False,
    max_z: float = 2.0,
    anchor_snapshots: list[dict] | None = None,
    escalation_tag: str = "",
) -> rm.ScoredSignal:
    return rm.ScoredSignal(
        signal_id=signal_id,
        cluster_key=cluster_key,
        domain_id=domain_id,
        region=region,
        domain_label=domain_label,
        title=title,
        body=body,
        sources=sources if sources is not None else ["pbc_news"],
        source_urls=["https://www.pbc.gov.cn/notice/1"],
        published_cst="2026-11-25 10:30 CST",
        score=score,
        severity=severity,
        s_auth=s_auth,
        s_confirm=s_confirm,
        s_spillover=s_spillover,
        k_verify=k_verify,
        is_official=is_official,
        is_rumor_capped=is_rumor_capped,
        is_flash_unverified=is_flash_unverified,
        is_divergence=is_divergence,
        is_market_closed_floor=is_market_closed_floor,
        max_z=max_z,
        anchor_snapshots=anchor_snapshots if anchor_snapshots is not None else [],
        transmission_chain="央行宽货币 → 短端资金下行 → A股与港股风险偏好回暖",
        guardrail="降准首日切忌追高超长债与早盘暴拉题材股。",
        escalation_tag=escalation_tag,
    )


def _sample_ssot(*, gold_locked: bool = True, events: list[dict] | None = None) -> dict:
    return {
        "edition_id": "2026-11-25_0730",
        "gold_locked": gold_locked,
        "gold_tier_label": "红灯停（暂不新买 · 新仓 0%）" if gold_locked else "黄灯观察（轻仓分批）",
        "gold_gates_passed": "1/4" if gold_locked else "3/4",
        "a_lamp": "红灯防守期",
        "a_cap_pct": 38,
        "a_fomo": "上证稳守3,500且沪深300连3日站上4,025",
        "hk_lamp": "红灯防守期",
        "hk_offshore_cap_pct": 33,
        "hk_onshore_cap_pct": 24,
        "hk_fomo": "恒指连3日站上23,515且港汇稳守7.840下方",
        "us_lamp": "红灯防守期",
        "us_cap_pct": 26,
        "us_cash_pct": 64,
        "us_fomo": "标普500连3日站上7,352且10年美债回落4.70%下方",
        "events": events
        if events is not None
        else [
            {
                "date_cst": "2026-11-26",
                "time_cst": "09:30",
                "region": "CN",
                "impact_tier": "P0",
                "title": "中国11月官方制造业PMI",
                "monitor_window_min": 90,
            },
            {
                "date_cst": "2026-11-27",
                "time_cst": "03:00",
                "region": "US",
                "impact_tier": "P0",
                "title": "美联储FOMC利率决议与新闻发布会",
                "monitor_window_min": 120,
            },
            {
                "date_cst": "2026-11-28",
                "time_cst": "11:15",
                "region": "HK",
                "impact_tier": "P1",
                "title": "香港金管局HIBOR与银行体系总结余例行披露",
                "monitor_window_min": 60,
            },
        ],
        "market_calendar": {},
    }


class _FakeHTTPResponse:
    def __init__(self, body: bytes | str | dict, status: int = 200) -> None:
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


def _snapshot_tree_metadata(roots: list[Path]) -> dict[str, tuple[int, int]]:
    meta: dict[str, tuple[int, int]] = {}
    for root in roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fname in filenames:
                fpath = Path(dirpath) / fname
                st = fpath.stat()
                meta[str(fpath)] = (st.st_mtime_ns, st.st_size)
    return meta


# ===========================================================================
# 1. All Parsers, Mocked Pollers & Realized Volatility Baselines
# ===========================================================================


class TestParsersAndPollers(unittest.TestCase):
    def setUp(self) -> None:
        self.now_ts = _cst(2026, 11, 25, 10, 30).timestamp()

    def test_parse_rss_xml_rss2_dc_date_and_truncation(self) -> None:
        long_desc = "美联储公布最新纪要。" + ("详细阐述通胀路径与资产负债表缩减计划。" * 40)
        xml_bytes = f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <channel>
            <title>Fed Press</title>
            <item>
              <title>&lt;b&gt;Federal Reserve&lt;/b&gt; issues &amp; updates FOMC statement</title>
              <description>&lt;p&gt;{long_desc}&lt;/p&gt;</description>
              <link> https://www.federalreserve.gov/newsevents/pressreleases/monetary20261125a.htm </link>
              <pubDate>Wed, 25 Nov 2026 02:00:00 GMT</pubDate>
            </item>
            <item>
              <title>Second item with DC date</title>
              <description>Liquidity facility notice</description>
              <link>https://www.federalreserve.gov/notice/2</link>
              <dc:date>2026-11-25 10:00:00</dc:date>
            </item>
            <item>
              <title>   </title>
              <description>Empty title must be skipped</description>
            </item>
          </channel>
        </rss>""".encode("utf-8")

        items = rm.parse_rss_xml(xml_bytes, "fed_monetary", is_official=True)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].source, "fed_monetary")
        self.assertTrue(items[0].is_official)
        self.assertEqual(items[0].title, "Federal Reserve issues & updates FOMC statement")
        self.assertLessEqual(len(items[0].body), 500)
        self.assertEqual(
            items[0].url,
            "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261125a.htm",
        )
        # 2026-11-25 02:00:00 GMT == 2026-11-25 10:00:00 CST
        self.assertAlmostEqual(items[0].published_ts, _cst(2026, 11, 25, 10, 0).timestamp(), delta=1.0)
        self.assertAlmostEqual(items[1].published_ts, _cst(2026, 11, 25, 10, 0).timestamp(), delta=1.0)

    def test_parse_rss_xml_atom_and_malformed(self) -> None:
        atom_bytes = """<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>ECB Press</title>
          <entry>
            <title>ECB Governing Council rate decision</title>
            <summary>Key ECB interest rates held steady.</summary>
            <link href="https://www.ecb.europa.eu/press/pr/date/2026/html/ecb.mp261125.en.html"/>
            <updated>2026-11-25 09:45:00</updated>
          </entry>
          <entry>
            <title>Published fallback entry</title>
            <summary>Fallback timestamp check</summary>
            <link href="https://www.ecb.europa.eu/press/2"/>
            <published>2026-11-25 09:15:00</published>
          </entry>
        </feed>""".encode("utf-8")

        items = rm.parse_rss_xml(atom_bytes, "ecb_rss", is_official=True)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "ECB Governing Council rate decision")
        self.assertEqual(items[0].url, "https://www.ecb.europa.eu/press/pr/date/2026/html/ecb.mp261125.en.html")
        self.assertAlmostEqual(items[0].published_ts, _cst(2026, 11, 25, 9, 45).timestamp(), delta=1.0)
        self.assertAlmostEqual(items[1].published_ts, _cst(2026, 11, 25, 9, 15).timestamp(), delta=1.0)

        for bad_feed in (b"<rss><channel><item><title>broken", b"", b"<html><head/><body/></html>"):
            with self.assertRaisesRegex(ValueError, "RSS/Atom"):
                rm.parse_rss_xml(bad_feed, "bad", is_official=False)
        self.assertEqual(rm.parse_rss_xml(b"<rss><channel/></rss>", "empty", is_official=False), [])

    def test_atom_keeps_original_publication_and_skips_unverifiable_dates(self) -> None:
        raw = b'''<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>Old news, updated this morning</title><published>2026-11-20T03:00:00Z</published>
          <updated>2026-11-25T02:00:00Z</updated><link rel="self" href="https://www.ecb.europa.eu/self"/>
          <link rel="alternate" href="https://www.ecb.europa.eu/article"/></entry>
          <entry><title>Unverifiable release time</title><published>not a date</published></entry>
          <entry><title>No date</title></entry>
        </feed>'''
        articles = rm.parse_rss_xml(raw, "ecb_rss", is_official=True)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].published_ts, _cst(2026, 11, 20, 11).timestamp())
        self.assertEqual(articles[0].url, "https://www.ecb.europa.eu/article")
        with self.assertRaisesRegex(ValueError, "no valid publication dates"):
            rm.parse_rss_xml(b"<rss><channel><item><title>no date</title></item></channel></rss>", "bad", is_official=False)

    def test_feed_distinguishes_html_error_from_valid_empty_rss(self) -> None:
        spec = ("test_rss", "rss", "https://example.invalid/source", False, {})
        for response, expect_error in ((b"<html><body>temporary error</body></html>", True),
                                       (b"<rss><channel/></rss>", False)):
            with mock.patch.object(rm, "_http_get_bytes", return_value=response):
                src, articles, error = rm._fetch_one_feed(spec, self.now_ts, 1)
            self.assertEqual(src, "test_rss")
            self.assertEqual(articles, [])
            self.assertEqual(bool(error), expect_error)

    def test_parse_sina_724(self) -> None:
        payload = {
            "result": {
                "data": {
                    "feed": {
                        "list": [
                            {
                                "rich_text": "<span>【央行公开市场净投放5000亿元】</span>" + ("流动性充裕。" * 25),
                                "create_time": "2026-11-25 09:20:00",
                                "docurl": "https://finance.sina.com.cn/7x24/1",
                                "is_focus": True,
                                "top_value": 0,
                            },
                            {
                                "rich_text": "普通快讯条目",
                                "create_time": "2026-11-25 09:10:00",
                                "docurl": "https://finance.sina.com.cn/7x24/2",
                                "is_focus": False,
                                "top_value": 0,
                            },
                            {"rich_text": "   "},
                            "not-a-dict",
                        ]
                    }
                }
            }
        }
        items = rm.parse_sina_724(json.dumps(payload).encode("utf-8"), self.now_ts)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].source, "sina_724")
        self.assertEqual(items[0].importance_flag, 1)
        self.assertFalse(items[0].is_official)
        self.assertLessEqual(len(items[0].title), 90)
        self.assertNotIn("<span>", items[0].title)
        self.assertAlmostEqual(items[0].published_ts, _cst(2026, 11, 25, 9, 20).timestamp(), delta=1.0)
        self.assertEqual(items[1].importance_flag, 0)

    def test_parse_wscn_lives(self) -> None:
        ts_val = int(_cst(2026, 11, 25, 10, 5).timestamp())
        payload = {
            "data": {
                "items": [
                    {
                        "content_text": "华尔街见闻：美联储官员称通胀进展缓慢",
                        "display_time": ts_val,
                        "uri": "https://wallstreetcn.com/livenews/1001",
                        "score": 2,
                    },
                    {
                        "content_text": "",
                        "title": "仅标题条目",
                        "display_time": ts_val - 60,
                        "uri": "https://wallstreetcn.com/livenews/1002",
                        "score": 1,
                    },
                    {"content_text": "", "title": ""},
                ]
            }
        }
        items = rm.parse_wscn_lives(json.dumps(payload).encode("utf-8"), "wscn_global", self.now_ts)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].source, "wscn_global")
        self.assertEqual(items[0].importance_flag, 1)
        self.assertEqual(items[0].published_ts, float(ts_val))
        self.assertEqual(items[1].title, "仅标题条目")
        self.assertEqual(items[1].importance_flag, 0)

    def test_parse_eastmoney_fastnews(self) -> None:
        payload = {
            "data": {
                "fastNewsList": [
                    {
                        "title": "财政部拟发行超长期特别国债",
                        "summary": "发行期限30年，规模1000亿元。",
                        "showTime": "2026-11-25 10:15:00",
                        "titleColor": "3",
                        "code": "20261125001",
                    },
                    {
                        "title": "普通行业动态",
                        "summary": "",
                        "showTime": "2026-11-25 10:00:00",
                        "titleColor": "0",
                        "code": "",
                    },
                    {"title": ""},
                ]
            }
        }
        items = rm.parse_eastmoney_fastnews(json.dumps(payload).encode("utf-8"), "em_top", self.now_ts)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].importance_flag, 1)
        self.assertEqual(items[0].url, "https://finance.eastmoney.com/a/20261125001.html")
        self.assertEqual(items[0].body, "发行期限30年，规模1000亿元。")
        self.assertEqual(items[1].importance_flag, 0)
        self.assertEqual(items[1].body, "普通行业动态")
        self.assertEqual(items[1].url, "")

    def test_parse_ths_724(self) -> None:
        ts_val = int(_cst(2026, 11, 25, 10, 12).timestamp())
        payload = {
            "data": {
                "list": [
                    {
                        "title": "证监会召开资本市场深化改革座谈会",
                        "digest": "研究进一步优化融券与量化交易监管安排。",
                        "ctime": ts_val,
                        "import": "3",
                        "url": "https://news.10jqka.com.cn/20261125/1.shtml",
                    },
                    {
                        "title": "普通公司公告",
                        "digest": "",
                        "ctime": ts_val - 120,
                        "import": "1",
                        "url": "https://news.10jqka.com.cn/20261125/2.shtml",
                    },
                ]
            }
        }
        items = rm.parse_ths_724(json.dumps(payload).encode("utf-8"), self.now_ts)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].source, "ths_724")
        self.assertEqual(items[0].importance_flag, 1)
        self.assertEqual(items[0].published_ts, float(ts_val))
        self.assertEqual(items[1].importance_flag, 0)
        self.assertEqual(items[1].body, "普通公司公告")

    def test_parse_jin10_flash_skips_locked_items(self) -> None:
        payload = {
            "data": [
                {
                    "time": "2026-11-25 10:20:00",
                    "important": 1,
                    "data": {"lock": True, "content": "VIP锁定付费内容，应当被跳过"},
                },
                {
                    "time": "2026-11-25 10:18:00",
                    "important": 1,
                    "data": {"lock": False, "content": "<b>美国10年期国债收益率</b>短线跳升8bp"},
                },
                {
                    "time": "2026-11-25 10:10:00",
                    "important": 0,
                    "data": {"content": "普通免费快讯"},
                },
                {
                    "time": "2026-11-25 10:05:00",
                    "important": 0,
                    "data": {"content": ""},
                },
            ]
        }
        items = rm.parse_jin10_flash(json.dumps(payload).encode("utf-8"), self.now_ts)
        self.assertEqual(len(items), 2)
        self.assertTrue(all("VIP锁定" not in it.title for it in items))
        self.assertEqual(items[0].title, "美国10年期国债收益率 短线跳升8bp")
        self.assertEqual(items[0].importance_flag, 1)
        self.assertEqual(items[0].url, "https://www.jin10.com/")
        self.assertEqual(items[1].importance_flag, 0)

    def test_parse_gov_cn_json_and_csrc_json(self) -> None:
        gov_payload = [
            {
                "TITLE": "国务院常务会议研究部署更加积极的财政政策",
                "DOCRELPUBTIME": "2026-11-25 10:00:00",
                "URL": "/yaowen/liebiao/202611/content_123.htm",
            },
            {
                "title": "外部绝对链接政策文件",
                "pubDate": "2026-11-25",
                "link": "https://www.gov.cn/zhengce/202611/content_456.htm",
            },
        ]
        gov_items = rm.parse_gov_cn_json(json.dumps(gov_payload).encode("utf-8"), "gov_yaowen", self.now_ts)
        self.assertEqual(len(gov_items), 2)
        self.assertTrue(gov_items[0].is_official)
        self.assertEqual(gov_items[0].importance_flag, 1)
        self.assertEqual(gov_items[0].url, "https://www.gov.cn/yaowen/liebiao/202611/content_123.htm")
        self.assertEqual(gov_items[1].url, "https://www.gov.cn/zhengce/202611/content_456.htm")
        self.assertEqual(rm.parse_gov_cn_json(b'{"not": "a list"}', "gov_yaowen", self.now_ts), [])

        csrc_payload = {
            "data": {
                "results": [
                    {
                        "title": "证监会发布关于进一步优化港股通机制的正式公告",
                        "publishedTimeStr": "2026-11-25 09:50:00",
                        "url": "//www.csrc.gov.cn/csrc/c100028/c999/content.shtml",
                    },
                    {"title": ""},
                ]
            }
        }
        csrc_items = rm.parse_csrc_json(json.dumps(csrc_payload).encode("utf-8"), self.now_ts)
        self.assertEqual(len(csrc_items), 1)
        self.assertTrue(csrc_items[0].is_official)
        self.assertEqual(csrc_items[0].source, "csrc_json")
        self.assertEqual(csrc_items[0].url, "https://www.csrc.gov.cn/csrc/c100028/c999/content.shtml")

    def test_parse_html_anchors(self) -> None:
        html_doc = """
        <html><body>
          <a href="/about.html">关于我们网站简介栏目</a>
          <a href="/short">央行公告</a>
          <tr><td><a href="/goutongjiaoliu/113456/a.html">中国人民银行公开市场业务交易公告（2026年第220号）</a></td><td>2026-11-25</td></tr>
          <li><a href="/goutongjiaoliu/113456/a-dup.html">中国人民银行公开市场业务交易公告（2026年第220号）</a><span>2026-11-25</span></li>
          <li><a href="./202611/t20261125.html">财政部关于2026年超长期特别国债发行工作有关事宜的通知</a><span>2026-11-25</span></li>
          <li><a href="https://www.mof.gov.cn/news/tariff.html">关于调整部分进口商品关税税率政策的公告</a><span>2026-11-25</span></li>
        </body></html>
        """.encode("utf-8")
        items = rm.parse_html_anchors(html_doc, "pbc_news", "https://www.pbc.gov.cn", self.now_ts)
        self.assertEqual(len(items), 3)
        self.assertTrue(all(it.is_official and it.importance_flag == 1 for it in items))
        self.assertEqual(items[0].url, "https://www.pbc.gov.cn/goutongjiaoliu/113456/a.html")
        self.assertEqual(items[1].url, "https://www.pbc.gov.cn/202611/t20261125.html")
        self.assertEqual(items[2].url, "https://www.mof.gov.cn/news/tariff.html")

    def test_parse_pubdate_iso8601_and_html_anchors_nearby_date(self) -> None:
        # P1-7: ISO-8601 Z, +09:00, and -04:00 offsets
        ts_z = rm._parse_pubdate_ts("2026-10-01T14:00:00Z")
        self.assertAlmostEqual(ts_z, _cst(2026, 10, 1, 22, 0, 0).timestamp(), delta=1.0)

        ts_jst = rm._parse_pubdate_ts("2026-10-01T14:00:00+09:00")
        self.assertAlmostEqual(ts_jst, _cst(2026, 10, 1, 13, 0, 0).timestamp(), delta=1.0)

        ts_edt = rm._parse_pubdate_ts("2026-10-01T14:00:00-04:00")
        self.assertAlmostEqual(ts_edt, _cst(2026, 10, 2, 2, 0, 0).timestamp(), delta=1.0)

        # P1-7: parse_html_anchors extracts nearby date so weeks-old notices don't look brand-new
        html_with_dates = """
        <html><body>
          <ul>
            <li><span>2026-10-05</span><a href="/old.html">中国人民银行关于开展公开市场逆回购操作的旧公告</a></li>
            <li><a href="/recent.html">财政部关于超长期特别国债发行工作的新通知</a><em>2026/11/25</em></li>
            <li><a href="/nodate.html">国家发展改革委关于宏观政策落地实施的专项会议通知</a></li>
          </ul>
        </body></html>
        """.encode("utf-8")
        items = rm.parse_html_anchors(html_with_dates, "pbc_news", "https://www.pbc.gov.cn", self.now_ts)
        self.assertEqual(len(items), 2)
        self.assertAlmostEqual(items[0].published_ts, _cst(2026, 10, 5, 0, 0).timestamp(), delta=1.0)
        self.assertAlmostEqual(items[1].published_ts, _cst(2026, 11, 25, 0, 0).timestamp(), delta=1.0)
        self.assertTrue(all(item.date_only for item in items))

        # Confirm weeks-old notice is filtered out by max_age_sec during classify_and_score
        sigs = rm.classify_and_score([items[0]], {}, dict(rm._DEFAULT_SIGMA_1D), now_cst=_cst(2026, 11, 25, 10, 30))
        self.assertEqual(sigs, [])

    def test_parse_sina_batch_quotes_all_asset_prefixes(self) -> None:
        # Build realistic Sina hq.sinajs.cn lines for sh, rt_hk, gb_, b_VIX, hf_, fx_, DINIW
        sh_parts = ["上证指数", "3300.00", "3280.00", "3329.20"] + ["0"] * 26 + ["2026-11-25", "10:30:00", "00"]
        hk_parts = ["HSI", "恒生指数", "20100.0", "20000.0", "20300.0", "19950.0", "20240.0", "240.0", "1.20"] + ["0"] * 8 + ["2026/11/25", "10:30:00"]
        gb_parts = ["标普500", "6060.00", "1.00", "2026-11-25 05:00:00", "60.00"]
        vix_parts = ["VIX恐慌指数", "18.50", "1.20", "6.94", "17.50", "19.00", "2026-11-25", "05:00:00", "0", "17.30"]
        hf_parts = ["2650.00", "", "2649.5", "2650.5", "2660.0", "2620.0", "10:30:00", "2600.00", "2605.0", "0", "0", "0", "2026-11-25", "伦敦金"]
        fx_parts = [
            "10:30:00", "7.2450", "7.2455", "7.2100", "0", "7.2150", "7.2500", "7.2050", "7.2450", "离岸人民币",
            "0", "0", "0", "0", "0", "0", "0", "2026-11-25",
        ]
        dxy_parts = ["10:30:00", "106.50", "106.51", "106.00", "0", "106.10", "106.80", "105.90", "106.50", "美元指数"]

        lines = [
            f'var hq_str_sh000001="{",".join(sh_parts)}";',
            f'var hq_str_rt_hkHSI="{",".join(hk_parts)}";',
            f'var hq_str_gb_inx="{",".join(gb_parts)}";',
            f'var hq_str_b_VIX="{",".join(vix_parts)}";',
            f'var hq_str_hf_XAU="{",".join(hf_parts)}";',
            f'var hq_str_fx_susdcnh="{",".join(fx_parts)}";',
            f'var hq_str_DINIW="{",".join(dxy_parts)}";',
            'var hq_str_sh000999="";',
            'var hq_str_gb_bad="bad,notfloat,oops,ts,0";',
        ]
        raw = "\n".join(lines).encode("gbk")
        ticks = rm.parse_sina_batch_quotes(raw)

        self.assertEqual(set(ticks.keys()), {"sh000001", "rt_hkHSI", "gb_inx", "b_VIX", "hf_XAU", "fx_susdcnh", "DINIW"})
        self.assertEqual(ticks["sh000001"].name, "上证指数")
        self.assertAlmostEqual(ticks["sh000001"].change_pct, 1.50, places=2)
        self.assertEqual(ticks["sh000001"].timestamp, "2026-11-25 10:30:00")

        self.assertEqual(ticks["rt_hkHSI"].name, "恒生指数")
        self.assertAlmostEqual(ticks["rt_hkHSI"].last, 20240.0)
        self.assertAlmostEqual(ticks["rt_hkHSI"].change_pct, 1.20)

        self.assertAlmostEqual(ticks["gb_inx"].last, 6060.0)
        self.assertAlmostEqual(ticks["gb_inx"].prev_close, 6000.0, places=2)
        self.assertAlmostEqual(ticks["gb_inx"].change_pct, 1.0)

        self.assertAlmostEqual(ticks["b_VIX"].last, 18.50)
        self.assertAlmostEqual(ticks["b_VIX"].prev_close, 17.30)
        self.assertAlmostEqual(ticks["b_VIX"].change_pct, 6.94)

        self.assertEqual(ticks["hf_XAU"].name, "伦敦金")
        self.assertAlmostEqual(ticks["hf_XAU"].change_pct, 1.92, places=2)

        self.assertEqual(ticks["fx_susdcnh"].name, "离岸人民币")
        self.assertAlmostEqual(ticks["fx_susdcnh"].change_pct, 0.49, places=2)
        self.assertEqual(ticks["fx_susdcnh"].timestamp, "2026-11-25 10:30:00")

        self.assertEqual(ticks["DINIW"].name, "美元指数")
        self.assertEqual(ticks["DINIW"].timestamp, "10:30:00")
        self.assertAlmostEqual(ticks["DINIW"].change_pct, 0.47, places=2)

    def test_parse_cnbc_batch_quotes_yields_vix_and_single_dict(self) -> None:
        payload = {
            "FormattedQuoteResult": {
                "FormattedQuote": [
                    {"symbol": "US2Y", "last": "4.350%", "previous_day_closing": "4.250%", "last_time": "10:29 EST"},
                    {"symbol": "US10Y", "last": "4.625%", "previous_day_closing": "4.500%", "last_time": "10:29 EST"},
                    {"symbol": "US30Y", "last": "4.800%", "previous_day_closing": "4.820%", "last_time": "10:29 EST"},
                    {"symbol": ".VIX", "last": "21.50", "previous_day_closing": "20.00", "last_time": "10:29 EST"},
                    {"symbol": "US10Y_BAD", "last": "N/A", "previous_day_closing": "4.0%"},
                ]
            }
        }
        ticks = rm.parse_cnbc_batch_quotes(json.dumps(payload).encode("utf-8"))
        self.assertEqual(set(ticks.keys()), {"US2Y", "US10Y", "US30Y", "b_VIX"})
        self.assertTrue(ticks["US10Y"].is_yield)
        self.assertAlmostEqual(ticks["US10Y"].last, 4.625)
        self.assertAlmostEqual(ticks["US10Y"].change_bp, 12.5)
        self.assertAlmostEqual(ticks["US2Y"].change_bp, 10.0)
        self.assertAlmostEqual(ticks["US30Y"].change_bp, -2.0)
        self.assertFalse(ticks["b_VIX"].is_yield)
        self.assertAlmostEqual(ticks["b_VIX"].last, 21.50)
        self.assertAlmostEqual(ticks["b_VIX"].change_pct, 7.50)

        # Single-dict FormattedQuote shape
        single_payload = {
            "FormattedQuoteResult": {
                "FormattedQuote": {"symbol": "US10Y", "last": "5.30%", "previous_day_closing": "5.10%"}
            }
        }
        single_ticks = rm.parse_cnbc_batch_quotes(json.dumps(single_payload).encode("utf-8"))
        self.assertIn("US10Y", single_ticks)
        self.assertAlmostEqual(single_ticks["US10Y"].change_bp, 20.0)

    def test_poll_all_feeds_and_poll_live_quotes_offline_mocked(self) -> None:
        sina_json = json.dumps(
            {
                "result": {
                    "data": {
                        "feed": {
                            "list": [
                                {"rich_text": "央行开展逆回购操作", "create_time": "2026-11-25 09:20:00", "is_focus": True}
                            ]
                        }
                    }
                }
            }
        ).encode("utf-8")

        def fake_http_get(url: str, *, headers=None, timeout=10) -> bytes:
            if "zhibo.sina.com.cn" in url:
                return sina_json
            if "wallstreetcn" in url or "awtmt.com" in url:
                raise urllib.error.URLError("simulated timeout")
            if "hq.sinajs.cn" in url and "sh000001" in url:
                sh_parts = ["上证指数", "3300", "3300", "3333"] + ["0"] * 26 + ["2026-11-25", "10:30:00", "00"]
                return f'var hq_str_sh000001="{",".join(sh_parts)}";'.encode("gbk")
            if "hq.sinajs.cn" in url and "b_VIX" in url:
                vix_parts = ["VIX", "19.0", "0.5", "2.70", "18.5", "19.5", "2026-11-25", "05:00:00", "0", "18.5"]
                return f'var hq_str_b_VIX="{",".join(vix_parts)}";'.encode("gbk")
            if "quote.cnbc.com" in url:
                return json.dumps(
                    {
                        "FormattedQuoteResult": {
                            "FormattedQuote": [
                                {"symbol": "US10Y", "last": "4.55%", "previous_day_closing": "4.50%"},
                                {"symbol": ".VIX", "last": "99.0", "previous_day_closing": "18.5"},
                            ]
                        }
                    }
                ).encode("utf-8")
            raise AssertionError(f"Unexpected URL in offline test: {url}")

        with mock.patch.object(rm, "_http_get_bytes", side_effect=fake_http_get):
            items, errors = rm.poll_all_feeds(sources_filter={"sina_724", "wscn_global"}, now_ts=self.now_ts)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].source, "sina_724")
            self.assertIn("wscn_global", errors)

            quotes, q_errors = rm.poll_live_quotes()
            self.assertEqual(q_errors, {})
            self.assertIn("sh000001", quotes)
            self.assertIn("US10Y", quotes)
            # Sina b_VIX already present so CNBC .VIX does not clobber it
            self.assertAlmostEqual(quotes["b_VIX"].last, 19.0)

    def test_load_vol_baselines_synthetic_and_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "does_not_exist.json"
            fallback = rm.load_vol_baselines(missing)
            self.assertEqual(fallback, rm._DEFAULT_SIGMA_15M)

            core_path = Path(td) / "core.json"
            eq_bars = [[f"2026-11-{i:02d}", 100, 102, 99, 100.0 + (2.0 if i % 2 == 0 else -1.0)] for i in range(1, 16)]
            y_bars = [[f"2026-11-{i:02d}", 4.5, 4.6, 4.4, 4.50 + (0.12 if i % 2 == 0 else -0.04)] for i in range(1, 16)]
            core_path.write_text(
                json.dumps({"series": {"idx_sh000001": {"bars": eq_bars}, "rate_US10Y": {"bars": y_bars}}}),
                encoding="utf-8",
            )
            loaded = rm.load_vol_baselines(core_path)
            self.assertGreater(loaded["sh000001"], 0.08)
            self.assertGreater(loaded["US10Y"], 2.5)
            self.assertNotEqual(loaded["sh000001"], rm._DEFAULT_SIGMA_15M["sh000001"])


# ===========================================================================
# 2. 0–100 Scoring, Clustering & Anti-Rumor Firewalls
# ===========================================================================


class TestScoringClusteringAndFirewalls(unittest.TestCase):
    def setUp(self) -> None:
        # Wed 2026-11-25 10:30 CST: CN & HK open, US closed
        self.cn_open_cst = _cst(2026, 11, 25, 10, 30)
        # Wed 2026-11-25 20:00 CST: CN, HK, US cash all closed
        self.all_cash_closed_cst = _cst(2026, 11, 25, 20, 0)
        # Wed 2026-11-25 23:00 CST: US cash open
        self.us_open_cst = _cst(2026, 11, 25, 23, 0)
        self.vols = dict(rm._DEFAULT_SIGMA_15M)

    def test_official_pboc_politburo_fomc_multi_anchor_scores_p0_p1(self) -> None:
        ts = self.cn_open_cst.timestamp() - 120
        # PBOC official + multi-anchor |z| >= 2.2 -> P0
        pboc_item = rm.NewsItem(
            source="pbc_news",
            title="中国人民银行宣布全面降准0.5个百分点并下调LPR利率",
            body="央行决定下调金融机构存款准备金率0.5个百分点，释放长期流动性。",
            published_ts=ts,
            url="https://www.pbc.gov.cn/1",
            importance_flag=1,
            is_official=True,
        )
        quotes = {
            "sh000001": _tick("sh000001", 3425.0, 3.80, name="上证指数"),      # sigma=1.25 -> z = +3.04 (equity)
            "sh511260": _tick("sh511260", 115.8, 0.70, name="十年国债ETF"),   # sigma=0.28 -> z = +2.50 (rates)
            "fx_susdcnh": _tick("fx_susdcnh", 7.16, -0.75, name="离岸人民币"), # sigma=0.30 -> z = -2.50 (fx)
        }
        sigs = rm.classify_and_score([pboc_item], quotes, self.vols, now_cst=self.cn_open_cst)
        self.assertEqual(len(sigs), 1)
        s = sigs[0]
        self.assertEqual(s.domain_id, "cn_pboc")
        self.assertEqual(s.k_verify, 1.0)
        self.assertEqual(s.s_auth, 40)
        self.assertGreaterEqual(s.max_z, 2.2)
        self.assertEqual(s.severity, "P0")
        self.assertGreaterEqual(s.score, 82)

        # Politburo official + multi-anchor |z| ~ 2.5 -> P0
        poli_item = rm.NewsItem(
            source="gov_yaowen",
            title="中共中央政治局会议部署超常规逆周期调节与适度宽松货币政策",
            body="政治局会议强调实施更加积极的财政政策与适度宽松的货币政策。",
            published_ts=ts,
            url="https://www.gov.cn/poli",
            importance_flag=1,
            is_official=True,
        )
        poli_quotes = {
            "sh000001": _tick("sh000001", 3405.0, 3.20),    # sigma=1.25 -> z = +2.56 (equity)
            "fx_susdcnh": _tick("fx_susdcnh", 7.16, -0.70), # sigma=0.30 -> z = -2.33 (fx)
        }
        poli_sigs = rm.classify_and_score([poli_item], poli_quotes, self.vols, now_cst=self.cn_open_cst)
        self.assertEqual(len(poli_sigs), 1)
        self.assertEqual(poli_sigs[0].domain_id, "cn_top_meeting")
        self.assertEqual(poli_sigs[0].severity, "P0")
        self.assertGreaterEqual(poli_sigs[0].score, 82)

        # FOMC official during US session with |z| >= 2.2 -> P0, and moderate |z| ~ 1.6 -> P1
        us_ts = self.us_open_cst.timestamp() - 60
        fomc_item = rm.NewsItem(
            source="fed_monetary",
            title="Federal Reserve FOMC statement signals rate path shift",
            body="Powell and FOMC committee update monetary policy guidance and QT pace.",
            published_ts=us_ts,
            url="https://www.federalreserve.gov/fomc",
            importance_flag=1,
            is_official=True,
        )
        fomc_quotes_strong = {
            "US10Y": _tick("US10Y", 4.72, 4.9, change_bp=22.0, is_yield=True),  # sigma=7.5bp -> z = +2.93 (rates)
            "hf_ES": _tick("hf_ES", 5820.0, -3.10),                             # sigma=1.20  -> z = -2.58 (equity)
        }
        fomc_strong = rm.classify_and_score([fomc_item], fomc_quotes_strong, self.vols, now_cst=self.us_open_cst)[0]
        self.assertEqual(fomc_strong.domain_id, "us_fed_fomc")
        self.assertEqual(fomc_strong.severity, "P0")

        fomc_quotes_mod = {
            "US10Y": _tick("US10Y", 4.62, 2.7, change_bp=12.0, is_yield=True),  # sigma=7.5bp -> z = 1.60 -> s_confirm=20, 1 bucket -> s_spillover=17
        }
        fomc_mod = rm.classify_and_score([fomc_item], fomc_quotes_mod, self.vols, now_cst=self.us_open_cst)[0]
        self.assertEqual(fomc_mod.severity, "P1")
        self.assertEqual(fomc_mod.score, 77)

    def test_cross_source_3gram_jaccard_clustering_merges_two_wires_k_verify_1(self) -> None:
        ts = self.cn_open_cst.timestamp() - 180
        item_a = rm.NewsItem(
            source="sina_724",
            title="中国人民银行决定下调存款准备金率并开展买断式逆回购操作",
            body="央行公告称旨在保持银行体系流动性合理充裕。",
            published_ts=ts,
            url="https://finance.sina.com.cn/1",
            importance_flag=1,
            is_official=False,
        )
        item_b = rm.NewsItem(
            source="wscn_global",
            title="中国人民银行决定下调存款准备金率并开展买断式逆回购操作以稳流动性",
            body="华尔街见闻快讯：央行今日宣布降准及逆回购安排。",
            published_ts=ts + 60,
            url="https://wallstreetcn.com/1",
            importance_flag=1,
            is_official=False,
        )
        quotes = {
            "sh000001": _tick("sh000001", 3402.0, 3.10),    # sigma=1.25 -> z = 2.48
            "sh511260": _tick("sh511260", 115.6, 0.56),     # sigma=0.28 -> z = 2.00
        }
        sigs = rm.classify_and_score([item_a, item_b], quotes, self.vols, now_cst=self.cn_open_cst)
        self.assertEqual(len(sigs), 1)
        sig = sigs[0]
        self.assertEqual(sig.sources, ["sina_724", "wscn_global"])
        self.assertEqual(sig.k_verify, 1.0)
        self.assertFalse(sig.is_rumor_capped)
        self.assertIn(sig.severity, ("P0", "P1"))

        # Negative checks: > 90 min apart does NOT merge; > max_age_sec (3h) filtered out
        stale_item = rm.NewsItem(
            source="em_724",
            title=item_a.title,
            body=item_a.body,
            published_ts=self.cn_open_cst.timestamp() - 11000,  # > 10800s
            is_official=False,
        )
        far_apart = rm.NewsItem(
            source="ths_724",
            title=item_a.title,
            body=item_a.body,
            published_ts=ts - 6000,  # > 5400s from item_a
            is_official=False,
        )
        sigs2 = rm.classify_and_score([item_a, far_apart, stale_item], quotes, self.vols, now_cst=self.cn_open_cst)
        self.assertEqual(len(sigs2), 2)
        self.assertTrue(all("em_724" not in s.sources for s in sigs2))

    def test_cross_poll_recent_clusters_immutable_key_and_source_merging(self) -> None:
        # P0-4: Poll 1 (single source -> k_verify=0.6) + Poll 2 10m later (second source, Jaccard >= 0.35)
        # must reuse the EXACT same cluster_key and upgrade to 2 sources (k_verify=1.0).
        with tempfile.TemporaryDirectory() as td:
            store = rm.MonitorStateStore(db_path=Path(td) / "cross_poll.sqlite3")
            try:
                t1_dt = self.cn_open_cst
                t2_dt = self.cn_open_cst + timedelta(minutes=10)
                quotes = {
                    "sh000001": _tick("sh000001", 3405.0, 3.20),   # z = 2.56
                    "sh511260": _tick("sh511260", 115.6, 0.56),    # z = 2.00
                }
                poll1_item = rm.NewsItem(
                    source="sina_724",
                    title="中国人民银行决定下调存款准备金率并开展买断式逆回购操作",
                    body="央行公告称保持银行体系流动性合理充裕。",
                    published_ts=t1_dt.timestamp() - 30,
                    importance_flag=1,
                    is_official=False,
                )
                # Dry-run (persist_clusters=False) must NOT seed recent_clusters
                dry_sigs = rm.classify_and_score(
                    [poll1_item], quotes, self.vols, now_cst=t1_dt, state_store=store, persist_clusters=False
                )
                self.assertEqual(len(dry_sigs), 1)
                self.assertEqual(
                    store._conn.execute("SELECT COUNT(*) FROM recent_clusters").fetchone()[0], 0
                )

                # Live Poll 1 persists initial cluster_key
                sigs1 = rm.classify_and_score(
                    [poll1_item], quotes, self.vols, now_cst=t1_dt, state_store=store, persist_clusters=True
                )
                self.assertEqual(len(sigs1), 1)
                s1 = sigs1[0]
                self.assertEqual(s1.sources, ["sina_724"])
                self.assertEqual(s1.k_verify, 0.6)
                self.assertTrue(s1.is_rumor_capped)

                # Live Poll 2 (10 min later, wscn_global, slightly different headline with Jaccard >= 0.35)
                poll2_item = rm.NewsItem(
                    source="wscn_global",
                    title="中国人民银行决定下调存款准备金率并开展买断式逆回购操作稳预期",
                    body="华尔街见闻快讯确认央行降准与逆回购安排。",
                    published_ts=t2_dt.timestamp() - 20,
                    importance_flag=1,
                    is_official=False,
                )
                sigs2 = rm.classify_and_score(
                    [poll2_item], quotes, self.vols, now_cst=t2_dt, state_store=store, persist_clusters=True
                )
                self.assertEqual(len(sigs2), 1)
                s2 = sigs2[0]
                self.assertEqual(s2.cluster_key, s1.cluster_key)
                self.assertEqual(s2.sources, ["sina_724", "wscn_global"])
                self.assertEqual(s2.k_verify, 1.0)
                self.assertFalse(s2.is_rumor_capped)
                self.assertIn(s2.severity, ("P0", "P1"))
            finally:
                store.close()

    def test_single_source_rumor_hard_capped_58_never_p0_or_p1(self) -> None:
        ts = self.cn_open_cst.timestamp() - 120
        moderate_quotes = {
            "sh000001": _tick("sh000001", 3320.0, 0.70),   # z = 2.00 (< 3.0)
            "sh511260": _tick("sh511260", 115.1, 0.15),    # z = 1.88 (< 3.0)
            "fx_susdcnh": _tick("fx_susdcnh", 7.22, -0.25), # z = -1.79
        }
        # Case A: Single non-official wire without rumor words
        single_wire = rm.NewsItem(
            source="sina_724",
            title="央行或将在本周宣布降准并扩大MLF投放规模",
            body="市场关注央行降准与MLF流动性安排。",
            published_ts=ts,
            importance_flag=1,
            is_official=False,
        )
        sig_a = rm.classify_and_score([single_wire], moderate_quotes, self.vols, now_cst=self.cn_open_cst)[0]
        self.assertEqual(sig_a.k_verify, 0.6)
        self.assertTrue(sig_a.is_rumor_capped)
        self.assertFalse(sig_a.is_flash_unverified)
        self.assertLessEqual(sig_a.score, 58)
        self.assertNotIn(sig_a.severity, ("P0", "P1"))

        # Case B: Even TWO independent wires carrying "传闻"/"知情人士" stay k_verify=0.6 & capped <= 58
        rumor_1 = rm.NewsItem(
            source="sina_724",
            title="知情人士传闻财政部正在讨论新一轮增量财政刺激方案",
            body="据知情人士透露，市场传闻特别国债规模将扩大。",
            published_ts=ts,
            importance_flag=1,
            is_official=False,
        )
        rumor_2 = rm.NewsItem(
            source="wscn_global",
            title="知情人士传闻财政部正在讨论新一轮增量财政刺激方案细节",
            body="消息人士称相关特别国债计划仍未最终敲定。",
            published_ts=ts + 30,
            importance_flag=1,
            is_official=False,
        )
        sig_b = rm.classify_and_score([rumor_1, rumor_2], moderate_quotes, self.vols, now_cst=self.cn_open_cst)[0]
        self.assertEqual(sig_b.k_verify, 0.6)
        self.assertTrue(sig_b.is_rumor_capped)
        self.assertLessEqual(sig_b.score, 58)
        self.assertNotIn(sig_b.severity, ("P0", "P1"))

    def test_single_source_unverified_with_extreme_shock_passes_as_flash_unverified(self) -> None:
        ts = self.cn_open_cst.timestamp() - 60
        unverified_tariff = rm.NewsItem(
            source="sina_724",
            title="据外媒消息人士称美方考虑立即启动新一轮301关税加征",
            body="单源快讯称加征关税清单可能覆盖关键科技产品。",
            published_ts=ts,
            importance_flag=1,
            is_official=False,
        )
        extreme_quotes = {
            "fx_susdcnh": _tick("fx_susdcnh", 7.35, 1.15, name="离岸人民币"),    # sigma=0.30 -> z=+3.83 >= 3.0!
            "rt_hkHSTECH": _tick("rt_hkHSTECH", 4000.0, -7.80, name="恒生科技"), # sigma=2.40 -> z=-3.25
        }
        sig = rm.classify_and_score([unverified_tariff], extreme_quotes, self.vols, now_cst=self.cn_open_cst)[0]
        self.assertEqual(sig.k_verify, 0.6)
        self.assertGreaterEqual(sig.max_z, 3.0)
        self.assertTrue(sig.is_flash_unverified)
        self.assertFalse(sig.is_rumor_capped)
        self.assertGreaterEqual(sig.score, 70)
        self.assertIn(sig.severity, ("P0", "P1"))

        alert_title, memo_md = rm.interpret_and_render_memo(sig, _sample_ssot(), now_cst=self.cn_open_cst)
        self.assertIn("⚠️【盘面剧震·待官方核实】", alert_title)
        self.assertIn("单源待官方核实", memo_md)
        self.assertIn("按兵不动", memo_md)

    def test_hk_dividend_tax_rumor_firewall_and_official_pass(self) -> None:
        ts = self.cn_open_cst.timestamp() - 60
        extreme_hk_quotes = {
            "rt_hkHSI": _tick("rt_hkHSI", 21500.0, 5.00, name="恒生指数"),      # sigma=1.50 -> z = 3.33 >= 3.0!
            "rt_hkHSTECH": _tick("rt_hkHSTECH", 4780.0, 7.60, name="恒生科技"), # sigma=2.40 -> z = 3.17
            "sh000300": _tick("sh000300", 4160.0, 4.10, name="沪深300"),        # sigma=1.35 -> z = 3.04
        }
        # Non-official media (even 2 independent wires + extreme |z| >= 3.0!) MUST be downgraded <= 58
        wire1 = rm.NewsItem(
            source="sina_724",
            title="港股通红利税将取消并下调个人投资者20%股息税率",
            body="市场报道港股通红利税有望减免，恒指午盘直线拉升。",
            published_ts=ts,
            importance_flag=1,
            is_official=False,
        )
        wire2 = rm.NewsItem(
            source="wscn_hk",
            title="港股通红利税将取消并下调个人投资者股息税率引发暴涨",
            body="港股红利税减免预期推动高息央国企大涨。",
            published_ts=ts + 20,
            importance_flag=1,
            is_official=False,
        )
        blocked = rm.classify_and_score([wire1, wire2], extreme_hk_quotes, self.vols, now_cst=self.cn_open_cst)[0]
        self.assertEqual(blocked.domain_id, "hk_southbound_tax")
        self.assertEqual(blocked.k_verify, 0.6)
        self.assertTrue(blocked.is_rumor_capped)
        self.assertFalse(blocked.is_flash_unverified)
        self.assertLessEqual(blocked.score, 58)
        self.assertNotIn(blocked.severity, ("P0", "P1"))

        # Official CSRC/MOF notice MUST pass as P0/P1
        official_notice = rm.NewsItem(
            source="csrc_json",
            title="财政部税务总局证监会联合发布互联互通优化与港股通红利税正式公告",
            body="三部门联合公告明确互联互通优化及港股通红利税调整安排与生效日期。",
            published_ts=ts,
            url="https://www.csrc.gov.cn/hk-tax",
            importance_flag=1,
            is_official=True,
        )
        passed = rm.classify_and_score([official_notice], extreme_hk_quotes, self.vols, now_cst=self.cn_open_cst)[0]
        self.assertEqual(passed.domain_id, "hk_southbound_tax")
        self.assertEqual(passed.k_verify, 1.0)
        self.assertFalse(passed.is_rumor_capped)
        self.assertIn(passed.severity, ("P0", "P1"))
        self.assertGreaterEqual(passed.score, 68)

        # Dual non-official wires citing explicit enacted "财政部公告第...号/正式发布" clear formal notice check
        formal_wire1 = rm.NewsItem(
            source="sina_724",
            title="财政部公告第18号正式发布港股通红利税政策并公布互联互通优化细则",
            body="财政部公告第18号正式实施互联互通优化与港股通红利税新政。",
            published_ts=ts,
            importance_flag=1,
            is_official=False,
        )
        formal_wire2 = rm.NewsItem(
            source="wscn_hk",
            title="财政部公告第18号正式发布港股通红利税政策及互联互通优化细则落地",
            body="三部门联合公告落地，港股通红利税正式实施下调。",
            published_ts=ts + 15,
            importance_flag=1,
            is_official=False,
        )
        passed_dual = rm.classify_and_score([formal_wire1, formal_wire2], extreme_hk_quotes, self.vols, now_cst=self.cn_open_cst)[0]
        self.assertEqual(passed_dual.domain_id, "hk_southbound_tax")
        self.assertEqual(passed_dual.k_verify, 1.0)
        self.assertFalse(passed_dual.is_rumor_capped)
        self.assertIn(passed_dual.severity, ("P0", "P1"))

    def test_word_boundary_and_cross_country_isolation(self) -> None:
        # P1-5: ASCII word boundaries & cross-country negative keyword isolation
        self.assertIsNone(rm.match_policy_domain("US mortgage rates fall"))
        self.assertIsNone(rm._OFFICIAL_ENTITY_IN_TEXT_RE.search("Tech sector rebounds"))
        self.assertIsNone(rm.match_policy_domain("赞比亚央行维持基准利率"))
        self.assertIsNone(rm.match_policy_domain("德国11月失业率6.4%"))
        self.assertIsNone(rm.match_policy_domain("中国证监会同意瓦楞原纸期货和期权注册"))

        ecb_rule = rm.match_policy_domain("ECB monetary policy decision")
        self.assertIsNotNone(ecb_rule)
        self.assertEqual(ecb_rule.domain_id, "global_cb_carry")

        warsh_cn = rm.match_policy_domain("沃什谈美联储资产负债表与通胀路径")
        self.assertIsNotNone(warsh_cn)
        self.assertEqual(warsh_cn.domain_id, "us_fed_fomc")

        warsh_en = rm.match_policy_domain("Warsh outlines monetary policy framework")
        self.assertIsNotNone(warsh_en)
        self.assertEqual(warsh_en.domain_id, "us_fed_fomc")

    def test_rumor_cues_text_level_hk_tax_firewall_and_explicit_rumor_block(self) -> None:
        # P1-6: "据悉"/"据透露" keeps k_verify=0.6 even across 2 wires
        ts = self.cn_open_cst.timestamp() - 60
        mod_quotes = {
            "sh000001": _tick("sh000001", 3375.0, 2.30),  # z = 1.84 (< 3.0)
            "sh511260": _tick("sh511260", 115.5, 0.50),   # z = 1.79 (< 3.0)
        }
        for cue in ("据悉", "据透露"):
            w1 = rm.NewsItem(
                source="sina_724",
                title=f"{cue}中国人民银行正在评估新一轮降准与买断式逆回购安排",
                body=f"{cue}相关政策正在研究论证阶段。",
                published_ts=ts,
                importance_flag=1,
                is_official=False,
            )
            w2 = rm.NewsItem(
                source="wscn_global",
                title=f"{cue}中国人民银行正在评估新一轮降准与买断式逆回购安排细节",
                body=f"{cue}市场关注后续货币政策工具。",
                published_ts=ts + 20,
                importance_flag=1,
                is_official=False,
            )
            sig_cue = rm.classify_and_score([w1, w2], mod_quotes, self.vols, now_cst=self.cn_open_cst)[0]
            self.assertEqual(sig_cue.k_verify, 0.6, f"Expected k_verify=0.6 for rumor cue {cue!r}")
            self.assertTrue(sig_cue.is_rumor_capped)
            self.assertLessEqual(sig_cue.score, 58)

        # P1-6: Text-level HK tax firewall applies REGARDLESS of matched domain (here cn_fiscal wins over hk_southbound_tax)
        extreme_quotes = {
            "sh000300": _tick("sh000300", 4180.0, 4.50),    # z = 3.33 >= 3.0
            "rt_hkHSI": _tick("rt_hkHSI", 21500.0, 5.20),   # z = 3.47 >= 3.0
            "fx_susdcnh": _tick("fx_susdcnh", 7.36, 1.20),  # z = 4.00 >= 3.0
            "rt_hkHSTECH": _tick("rt_hkHSTECH", 3980.0, -8.20),  # z = -3.42
        }
        hk_cross_domain_1 = rm.NewsItem(
            source="sina_724",
            title="网传港股股息税将减免，市场期待财政部公告",
            body="网传港股股息税将减免，市场期待财政部公告落地。",
            published_ts=ts,
            importance_flag=1,
            is_official=False,
        )
        hk_cross_domain_2 = rm.NewsItem(
            source="wscn_hk",
            title="网传港股股息税将减免，市场期待财政部公告出炉",
            body="市场热议港股股息税减免与财政部公告预期。",
            published_ts=ts + 15,
            importance_flag=1,
            is_official=False,
        )
        sig_hk_text = rm.classify_and_score(
            [hk_cross_domain_1, hk_cross_domain_2], extreme_quotes, self.vols, now_cst=self.cn_open_cst
        )[0]
        self.assertEqual(sig_hk_text.k_verify, 0.6)
        self.assertTrue(sig_hk_text.is_rumor_capped)
        self.assertFalse(sig_hk_text.is_flash_unverified)
        self.assertLessEqual(sig_hk_text.score, 58)

        # P1-6: Explicit "小作文" / "网传" MUST NOT be promoted by is_flash_unverified even with |z| >= 3.0
        for hard_cue in ("小作文", "网传"):
            hard_rumor = rm.NewsItem(
                source="sina_724",
                title=f"{hard_cue}称美方将立即启动新一轮301关税加征",
                body=f"{hard_cue}引发离岸人民币与科技股大幅波动。",
                published_ts=ts,
                importance_flag=1,
                is_official=False,
            )
            sig_hard = rm.classify_and_score([hard_rumor], extreme_quotes, self.vols, now_cst=self.cn_open_cst)[0]
            self.assertGreaterEqual(sig_hard.max_z, 3.0)
            self.assertFalse(sig_hard.is_flash_unverified, f"{hard_cue!r} must NOT promote to flash_unverified")
            self.assertTrue(sig_hard.is_rumor_capped)
            self.assertLessEqual(sig_hard.score, 58)
            self.assertNotIn(sig_hard.severity, ("P0", "P1"))

    def test_buy_rumor_sell_fact_divergence(self) -> None:
        ts = self.cn_open_cst.timestamp() - 60
        pos_headline = rm.NewsItem(
            source="gov_yaowen",
            title="国务院常务会议部署新一轮财政刺激、降准降息与消费补贴利好政策",
            body="会议强调加大逆周期刺激力度与流动性净投放。",
            published_ts=ts,
            is_official=True,
        )
        # Positive stimulus headline + primary equity drop <= -0.6% -> is_divergence=True
        sell_fact_quotes = {
            "sh000001": _tick("sh000001", 3270.0, -0.85, name="上证指数"),
            "sh000300": _tick("sh000300", 3920.0, -0.90, name="沪深300"),
        }
        sig_div = rm.classify_and_score([pos_headline], sell_fact_quotes, self.vols, now_cst=self.cn_open_cst)[0]
        self.assertTrue(sig_div.is_divergence)
        _, memo_md = rm.interpret_and_render_memo(sig_div, _sample_ssot(), now_cst=self.cn_open_cst)
        self.assertIn("买预期卖事实", memo_md)

        # Positive headline + positive equity -> no divergence
        aligned_quotes = {"sh000001": _tick("sh000001", 3360.0, 1.10, name="上证指数")}
        sig_aligned = rm.classify_and_score([pos_headline], aligned_quotes, self.vols, now_cst=self.cn_open_cst)[0]
        self.assertFalse(sig_aligned.is_divergence)

        # Reverse divergence: negative tariff headline + primary equity rally >= +0.8% -> is_divergence=True
        neg_headline = rm.NewsItem(
            source="whitehouse_rss",
            title="White House announces new tariff and export control sanctions",
            body="New tariff and sanction package targeting technology exports.",
            published_ts=ts,
            is_official=True,
        )
        rally_quotes = {"hf_CHA50CFD": _tick("hf_CHA50CFD", 13200.0, 1.15, name="富时A50")}
        sig_rev = rm.classify_and_score([neg_headline], rally_quotes, self.vols, now_cst=self.cn_open_cst)[0]
        self.assertTrue(sig_rev.is_divergence)

    def test_market_closed_s_grade_official_floor(self) -> None:
        ts_closed = self.all_cash_closed_cst.timestamp() - 60
        cn_official = rm.NewsItem(
            source="gov_yaowen",
            title="中共中央政治局会议部署更加积极的财政与适度宽松货币政策",
            body="盘后晚间新华社通稿发布重要政策定调。",
            published_ts=ts_closed,
            is_official=True,
        )
        us_official = rm.NewsItem(
            source="fed_monetary",
            title="Federal Reserve FOMC emergency monetary policy announcement",
            body="FOMC updates Fed rate target range outside US cash hours.",
            published_ts=ts_closed,
            is_official=True,
        )
        flat_quotes = {
            "sh000001": _tick("sh000001", 3300.0, 0.0),
            "US10Y": _tick("US10Y", 4.50, 0.0, change_bp=0.0, is_yield=True),
        }
        sigs = rm.classify_and_score([cn_official, us_official], flat_quotes, self.vols, now_cst=self.all_cash_closed_cst)
        by_domain = {s.domain_id: s for s in sigs}

        self.assertTrue(by_domain["cn_top_meeting"].is_market_closed_floor)
        self.assertEqual(by_domain["cn_top_meeting"].s_confirm, 20)
        self.assertTrue(by_domain["us_fed_fomc"].is_market_closed_floor)
        self.assertEqual(by_domain["us_fed_fomc"].s_confirm, 20)
        self.assertEqual(by_domain["us_fed_fomc"].score, 70)
        self.assertEqual(by_domain["us_fed_fomc"].severity, "P1")

        # When CN market IS open and quotes are flat, floor MUST NOT activate
        cn_open_item = rm.NewsItem(
            source="gov_yaowen",
            title=cn_official.title,
            body=cn_official.body,
            published_ts=self.cn_open_cst.timestamp() - 60,
            is_official=True,
        )
        open_sig = rm.classify_and_score([cn_open_item], flat_quotes, self.vols, now_cst=self.cn_open_cst)[0]
        self.assertFalse(open_sig.is_market_closed_floor)
        self.assertEqual(open_sig.s_confirm, 4)


# ===========================================================================
# 3. Market-First Crisis Breakers & Live Shock Detector
# ===========================================================================


class TestMarketFirstCrisisBreakers(unittest.TestCase):
    def setUp(self) -> None:
        self.now_cst = _cst(2026, 11, 25, 14, 0)
        self.vols = dict(rm._DEFAULT_SIGMA_15M)

    def test_crisis_breakers_us10y_vix_usdjpy(self) -> None:
        quotes = {
            "US10Y": _tick("US10Y", 5.28, 2.5, change_bp=12.0, is_yield=True),
            "b_VIX": _tick("b_VIX", 46.2, 18.0, name="VIX"),
            "fx_susdjpy": _tick("fx_susdjpy", 148.0, -2.75, name="USD/JPY"),
        }
        now_usa = _cst(2026, 11, 25, 23, 0)
        sigs = rm.detect_market_first_anomalies(quotes, self.vols, now_cst=now_usa)
        by_key = {s.cluster_key.split(":")[1]: s for s in sigs}

        self.assertEqual(set(by_key.keys()), {"us10y_breaker", "vix_breaker", "usdjpy_carry_breaker"})
        self.assertEqual(by_key["us10y_breaker"].severity, "P0")
        self.assertEqual(by_key["us10y_breaker"].score, 92)
        self.assertEqual(by_key["vix_breaker"].severity, "P0")
        self.assertEqual(by_key["vix_breaker"].score, 90)
        self.assertEqual(by_key["usdjpy_carry_breaker"].severity, "P0")
        self.assertEqual(by_key["usdjpy_carry_breaker"].score, 88)

        # Secondary trigger paths: US10Y |bp| >= 18 (< 5.25%) -> P0; VIX < 45 & >= +22% -> P1
        quotes_alt = {
            "US10Y": _tick("US10Y", 4.90, 4.0, change_bp=-19.0, is_yield=True),
            "b_VIX": _tick("b_VIX", 32.0, 24.5, name="VIX"),
        }
        sigs_alt = rm.detect_market_first_anomalies(quotes_alt, self.vols, now_cst=now_usa)
        by_key_alt = {s.cluster_key.split(":")[1]: s for s in sigs_alt}
        self.assertEqual(by_key_alt["us10y_breaker"].severity, "P0")
        self.assertEqual(by_key_alt["vix_breaker"].severity, "P1")
        self.assertEqual(by_key_alt["vix_breaker"].score, 78)

    def test_core_index_live_shock_and_quiet_guard(self) -> None:
        # Calibrated daily-vol quotes: consolidated to AT MOST 1 shock alert per region
        quotes = {
            "sh000001": _tick("sh000001", 3440.0, 4.20, name="上证指数"),      # sigma=1.25 -> z=+3.36 (CN lead, P1)
            "sh000300": _tick("sh000300", 4160.0, 4.00, name="沪深300"),       # sigma=1.35 -> z=+2.96 (CN peer, consolidated)
            "rt_hkHSTECH": _tick("rt_hkHSTECH", 4120.0, -7.50, name="恒生科技"), # sigma=2.40 -> z=-3.12 (HK, P1)
            # Below change_pct threshold (2.4% < 2.5%) -> must NOT fire
            "hf_ES": _tick("hf_ES", 6145.0, 2.40, name="标普500期货"),
            # Above change_pct (5.5%) but below |z| < 2.8 (5.5/2.40 = 2.29) -> must NOT fire
            "hf_OIL": _tick("hf_OIL", 74.0, 5.50, name="国际原油"),
        }
        sigs = rm.detect_market_first_anomalies(quotes, self.vols, now_cst=self.now_cst)
        by_key = {s.cluster_key.split(":")[1]: s for s in sigs}
        self.assertEqual(set(by_key.keys()), {"shock_region_cn", "shock_region_hk"})

        cn_sig = by_key["shock_region_cn"]
        self.assertEqual(cn_sig.severity, "P1")
        self.assertIn("急涨", cn_sig.title)
        self.assertIn("同区域共振", cn_sig.body)
        self.assertEqual([a["symbol"] for a in cn_sig.anchor_snapshots], ["sh000001", "sh000300"])

        hk_sig = by_key["shock_region_hk"]
        self.assertEqual(hk_sig.severity, "P1")
        self.assertIn("急跌", hk_sig.title)
        self.assertEqual([a["symbol"] for a in hk_sig.anchor_snapshots], ["rt_hkHSTECH"])

        # Extreme >= 4.0 daily sigma shock escalates to P0 (score=84)
        p0_sigs = rm.detect_market_first_anomalies(
            {"rt_hkHSTECH": _tick("rt_hkHSTECH", 3960.0, -10.20, name="恒生科技")},  # |z| = 4.25 >= 4.0 -> P0
            self.vols,
            now_cst=self.now_cst,
        )
        self.assertEqual(len(p0_sigs), 1)
        self.assertEqual(p0_sigs[0].severity, "P0")
        self.assertEqual(p0_sigs[0].score, 84)

        # Quiet market -> empty list
        quiet_quotes = {
            "US10Y": _tick("US10Y", 4.40, 0.2, change_bp=1.0, is_yield=True),
            "b_VIX": _tick("b_VIX", 16.0, 1.5),
            "fx_susdjpy": _tick("fx_susdjpy", 153.0, -0.3),
            "sh000001": _tick("sh000001", 3310.0, 0.4),
        }
        self.assertEqual(rm.detect_market_first_anomalies(quiet_quotes, self.vols, now_cst=self.now_cst), [])


# ===========================================================================
# 4. SQLite State Store (Dedupe, Cooldown, Escalation, Caps, Quiet, Audit)
# ===========================================================================


class TestMonitorStateStore(unittest.TestCase):
    def _new_store(self) -> rm.MonitorStateStore:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        store = rm.MonitorStateStore(db_path=Path(td.name) / "monitor.sqlite3")
        self.addCleanup(store.close)
        return store

    def test_exact_24h_dedupe_and_expiry(self) -> None:
        # 30-day retention (retention_sec=30*86400), expires after 31 days
        store = self._new_store()
        t0 = _cst(2026, 11, 25, 10, 0).timestamp()
        it1 = rm.NewsItem("sina_724", "央行开展买断式逆回购操作", "body", t0)
        it2 = rm.NewsItem("wscn_global", "央行开展买断式逆回购操作", "body", t0)

        # First pass keeps both (different sources)
        unseen1 = store.mark_and_filter_unseen([it1, it2], t0)
        self.assertEqual(len(unseen1), 2)

        # 12 hours and 29 days later -> still deduped within 30-day retention window
        self.assertEqual(store.mark_and_filter_unseen([it1, it2], t0 + 12 * 3600), [])
        self.assertEqual(store.mark_and_filter_unseen([it1, it2], t0 + 29 * 86400), [])

        # 31 days later (> 30*86400) -> expired from seen_items, accepted again
        unseen3 = store.mark_and_filter_unseen([it1], t0 + 31 * 86400)
        self.assertEqual(len(unseen3), 1)
        self.assertEqual(unseen3[0].source, "sina_724")

    def test_first_seen_and_recovery_queue_are_atomic_and_expire(self) -> None:
        store = self._new_store()
        now_ts = _cst(2026, 11, 25, 10, 0).timestamp()
        item = rm.NewsItem("sina_724", "央行开展买断式逆回购操作", "body", now_ts)
        with mock.patch.object(store, "_queue_news", side_effect=RuntimeError("enqueue interrupted")):
            with self.assertRaisesRegex(RuntimeError, "enqueue interrupted"):
                store.mark_and_filter_unseen([item], now_ts)
        self.assertEqual(store.seen_items_count(), 0)
        self.assertEqual(store.pending_news(now_ts), [])

        self.assertEqual(store.mark_and_filter_unseen([item], now_ts, persist=False), [item])
        self.assertEqual(store.seen_items_count(), 0)
        self.assertEqual(store.pending_news(now_ts), [])

        self.assertEqual(store.mark_and_filter_unseen([item], now_ts), [item])
        self.assertEqual(store.pending_news(now_ts), [item])
        self.assertEqual(store.pending_news(now_ts + rm.NEWS_MAX_AGE_SEC + 1), [])
        self.assertEqual(store.mark_and_filter_unseen([item], now_ts + rm.NEWS_MAX_AGE_SEC + 1), [])

    def test_upcoming_calendar_p0_prealert_and_24h_cooldown(self) -> None:
        # P1-9: T-60m proactive pre-alert for exact-time P0 events + 24h cooldown
        events = [
            {
                "event_id": "cn_pmi_11",
                "date_cst": "2026-11-26",
                "time_cst": "09:30",
                "region": "CN",
                "impact_tier": "P0",
                "title": "中国11月官方制造业PMI",
                "expected_consensus": "市场预期 50.2",
            },
            {
                "event_id": "hk_p1_within_60m",
                "date_cst": "2026-11-26",
                "time_cst": "09:15",
                "region": "HK",
                "impact_tier": "P1",
                "title": "香港例行数据（P1应忽略）",
            },
            {
                "event_id": "cn_p0_too_far",
                "date_cst": "2026-11-26",
                "time_cst": "11:00",
                "region": "CN",
                "impact_tier": "P0",
                "title": "超60分钟的P0事件（应忽略）",
            },
            {
                "event_id": "cn_p0_past",
                "date_cst": "2026-11-26",
                "time_cst": "08:30",
                "region": "CN",
                "impact_tier": "P0",
                "title": "已过期P0事件（应忽略）",
            },
            {
                "event_id": "cn_p0_allday",
                "date_cst": "2026-11-26",
                "time_cst": "全天",
                "region": "CN",
                "impact_tier": "P0",
                "title": "无精确时分的全天P0事件（应忽略）",
            },
        ]
        now_dt = _cst(2026, 11, 26, 8, 45)  # 45 min before cn_pmi_11
        cal_sigs = rm.detect_upcoming_calendar_alerts(events, now_cst=now_dt, lead_minutes=60)
        self.assertEqual(len(cal_sigs), 1)
        sig = cal_sigs[0]
        self.assertEqual(sig.domain_id, "calendar_prealert")
        self.assertEqual(sig.cluster_key, "cal_prealert:cn_pmi_11")
        self.assertEqual(sig.region, "CN")
        self.assertEqual(sig.severity, "P1")
        self.assertEqual(sig.score, 74)
        self.assertIn("45分钟后", sig.title)

        # 24h cooldown prevents repeat even after standard 2h cooldown expires
        store = self._new_store()
        self.assertEqual(store.evaluate_dispatch(sig, now_dt), (True, "dispatched"))
        store.record_signal(sig, "dispatched", now_dt)
        self.assertEqual(
            store.evaluate_dispatch(sig, now_dt + timedelta(hours=3)),
            (False, "suppressed_cooldown"),
        )
        self.assertEqual(
            store.evaluate_dispatch(sig, now_dt + timedelta(hours=25)),
            (True, "dispatched"),
        )

    def test_2h_semantic_cluster_cooldown_and_expiry(self) -> None:
        store = self._new_store()
        t0 = _cst(2026, 11, 25, 10, 0)
        sig1 = _signal(cluster_key="cn_pboc:clusterA", severity="P1", is_official=True, max_z=2.0)

        ok, reason = store.evaluate_dispatch(sig1, t0)
        self.assertEqual((ok, reason), (True, "dispatched"))
        store.record_signal(sig1, "dispatched", t0)

        # Within 2h (30 min later), no escalation -> suppressed_cooldown
        sig2 = _signal(cluster_key="cn_pboc:clusterA", severity="P1", is_official=True, max_z=2.2)
        ok2, reason2 = store.evaluate_dispatch(sig2, t0 + timedelta(minutes=30))
        self.assertEqual((ok2, reason2), (False, "suppressed_cooldown"))
        self.assertEqual(sig2.escalation_tag, "")

        # After 2h (121 min later) -> cooldown expired, dispatches normally
        sig3 = _signal(cluster_key="cn_pboc:clusterA", severity="P1", is_official=True, max_z=2.0)
        ok3, reason3 = store.evaluate_dispatch(sig3, t0 + timedelta(minutes=121))
        self.assertEqual((ok3, reason3), (True, "dispatched"))
        self.assertEqual(sig3.escalation_tag, "")

    def test_escalation_pierce_all_three_triggers(self) -> None:
        t0 = _cst(2026, 11, 25, 10, 0)

        # (a) Authority upgrade: non-official -> official
        store_a = self._new_store()
        base_a = _signal(cluster_key="cn_tariff:escA", severity="P1", is_official=False, max_z=2.0)
        store_a.record_signal(base_a, "dispatched", t0)
        upg_a = _signal(cluster_key="cn_tariff:escA", severity="P1", is_official=True, max_z=2.0)
        ok_a, reason_a = store_a.evaluate_dispatch(upg_a, t0 + timedelta(minutes=10))
        self.assertEqual((ok_a, reason_a), (True, "dispatched"))
        self.assertEqual(upg_a.escalation_tag, "【进展升级】")

        # (b) Severity upgrade: P1 -> P0
        store_b = self._new_store()
        base_b = _signal(cluster_key="cn_pboc:escB", severity="P1", is_official=True, max_z=2.0)
        store_b.record_signal(base_b, "dispatched", t0)
        upg_b = _signal(cluster_key="cn_pboc:escB", severity="P0", score=88, is_official=True, max_z=2.5)
        ok_b, reason_b = store_b.evaluate_dispatch(upg_b, t0 + timedelta(minutes=10))
        self.assertEqual((ok_b, reason_b), (True, "dispatched"))
        self.assertEqual(upg_b.escalation_tag, "【进展升级】")

        # (c) max_z widens by >= 1.5 sigma at least 15 min later
        store_c = self._new_store()
        base_c = _signal(cluster_key="us_fed_fomc:escC", severity="P1", is_official=True, max_z=2.0)
        store_c.record_signal(base_c, "dispatched", t0)

        # Only 10 min later (< 15 min): even +2.0σ MUST still be suppressed!
        too_early = _signal(cluster_key="us_fed_fomc:escC", severity="P1", is_official=True, max_z=4.0)
        self.assertEqual(store_c.evaluate_dispatch(too_early, t0 + timedelta(minutes=10)), (False, "suppressed_cooldown"))

        # 20 min later but only +1.2σ (< 1.5σ): MUST still be suppressed!
        too_small = _signal(cluster_key="us_fed_fomc:escC", severity="P1", is_official=True, max_z=3.2)
        self.assertEqual(store_c.evaluate_dispatch(too_small, t0 + timedelta(minutes=20)), (False, "suppressed_cooldown"))

        # 16 min later (>= 900s) and +1.5σ (>= 1.5σ): pierces cooldown!
        pierced = _signal(cluster_key="us_fed_fomc:escC", severity="P1", is_official=True, max_z=3.5)
        ok_c, reason_c = store_c.evaluate_dispatch(pierced, t0 + timedelta(minutes=16))
        self.assertEqual((ok_c, reason_c), (True, "dispatched"))
        self.assertEqual(pierced.escalation_tag, "【进展升级】")

    def test_p1_daily_cap_6_and_p0_bypass(self) -> None:
        store = self._new_store()
        t0 = _cst(2026, 11, 25, 10, 0)
        domains = ("cn_pboc", "cn_fiscal", "cn_csrc", "hk_peg_hkma", "us_fed_fomc", "us_macro_data")

        for i, dom in enumerate(domains):
            sig = _signal(signal_id=f"p1-{i}", cluster_key=f"{dom}:c{i}", domain_id=dom, severity="P1")
            ok, reason = store.evaluate_dispatch(sig, t0 + timedelta(minutes=i))
            self.assertEqual((ok, reason), (True, "dispatched"))
            store.record_signal(sig, "dispatched", t0 + timedelta(minutes=i))

        # 7th P1 on same day (even distinct domain) -> suppressed_daily_cap
        sig7 = _signal(signal_id="p1-6", cluster_key="cn_tariff:c6", domain_id="cn_tariff", severity="P1")
        self.assertEqual(store.evaluate_dispatch(sig7, t0 + timedelta(minutes=10)), (False, "suppressed_daily_cap"))

        # P0 on same day still dispatches
        sig_p0 = _signal(signal_id="p0-1", cluster_key="crisis_breaker:p0", domain_id="crisis_breaker", severity="P0", score=92)
        self.assertEqual(store.evaluate_dispatch(sig_p0, t0 + timedelta(minutes=11)), (True, "dispatched"))

        # Next CST day -> P1 quota resets
        next_day = _cst(2026, 11, 26, 9, 30)
        sig_next = _signal(signal_id="p1-next", cluster_key="cn_pboc:next", domain_id="cn_pboc", severity="P1")
        self.assertEqual(store.evaluate_dispatch(sig_next, next_day), (True, "dispatched"))

    def test_per_domain_p1_cooldown_and_routine_noise_filter(self) -> None:
        store = self._new_store()
        t0 = _cst(2026, 11, 25, 10, 0)

        s1 = _signal(signal_id="d1", cluster_key="cn_csrc:1", domain_id="cn_csrc", severity="P1")
        self.assertEqual(store.evaluate_dispatch(s1, t0), (True, "dispatched"))
        store.record_signal(s1, "dispatched", t0)

        # Second distinct cluster in SAME domain within 30 min -> suppressed_domain_cooldown
        s2 = _signal(signal_id="d2", cluster_key="cn_csrc:2", domain_id="cn_csrc", severity="P1")
        self.assertEqual(store.evaluate_dispatch(s2, t0 + timedelta(minutes=10)), (False, "suppressed_domain_cooldown"))

        # P0 in same domain bypasses domain cooldown
        s_p0 = _signal(signal_id="d3", cluster_key="cn_csrc:p0", domain_id="cn_csrc", severity="P0", score=88)
        self.assertEqual(store.evaluate_dispatch(s_p0, t0 + timedelta(minutes=10)), (True, "dispatched"))

        # After 31 min -> same-domain P1 allowed again
        self.assertEqual(store.evaluate_dispatch(s2, t0 + timedelta(minutes=31)), (True, "dispatched"))

        # Routine diplomatic / administrative noise filtered out unless hard catalyst present
        self.assertIsNone(rm.match_policy_domain("中国证监会主席会见外宾并出席开幕式"))
        self.assertIsNone(rm.match_policy_domain("中国证监会通报编造传播误导性信息及行政处罚案例"))
        self.assertIsNone(rm.match_policy_domain("国家发改委发布个人数字身份管理试点通知"))
        # Hard catalyst overrides courtesy/meeting phrasing
        matched = rm.match_policy_domain("中国人民银行行长会见外宾时宣布全面降准50个基点")
        self.assertIsNotNone(matched)
        self.assertEqual(matched.domain_id, "cn_pboc")

    def test_cold_start_bootstrap_caps_first_poll_to_2_alerts(self) -> None:
        now_dt = _cst(2026, 11, 27, 14, 0)
        now_ts = now_dt.timestamp()
        store = self._new_store()
        # 4 distinct official high-score news items across 4 distinct domains on an EMPTY seen_items DB
        items = [
            rm.NewsItem("gov_yaowen", "国务院常务会议部署更加积极的财政政策", "国常会定调超常规逆周期调节", now_ts - 60, "https://www.gov.cn/1", 1, True),
            rm.NewsItem("pbc_news", "中国人民银行宣布全面降准50个基点", "中国人民银行释放长期流动性", now_ts - 120, "https://www.pbc.gov.cn/2", 1, True),
            rm.NewsItem("fed_press", "Federal Reserve FOMC emergency rate cut statement", "Federal Reserve cuts rates sharply", now_ts - 180, "https://www.federalreserve.gov/3", 1, True),
            rm.NewsItem("hkma_rss", "HKMA intervenes at 7.85 weak-side convertibility undertaking", "HKMA 弱方兑换保证 银行体系总结余", now_ts - 240, "https://www.hkma.gov.hk/4", 1, True),
        ]
        quotes = {
            "sh000001": rm.QuoteTick("sh000001", "上证", 3600.0, 3500.0, 2.86),
            "sh000300": rm.QuoteTick("sh000300", "沪深300", 4060.0, 3900.0, 4.10),
            "rt_hkHSI": rm.QuoteTick("rt_hkHSI", "恒指", 22700.0, 22000.0, 3.18),
            "US10Y": rm.QuoteTick("US10Y", "US10Y", 4.95, 4.80, 3.12, change_bp=15.0, is_yield=True),
        }
        with mock.patch.object(rm, "poll_all_feeds", return_value=(items, {})), mock.patch.object(
            rm, "poll_live_quotes", return_value=(quotes, {})
        ), mock.patch.object(rm, "detect_market_first_anomalies", return_value=[]), mock.patch.object(
            rm, "detect_upcoming_calendar_alerts", return_value=[]
        ):
            summary = rm.run_once(
                store=store, dry_run=True, now_cst=now_dt,
                notify_config_path=store.db_path.with_name("missing-notify.json"),
            )
        self.assertGreaterEqual(summary["signals_scored"], 4)
        self.assertLessEqual(summary["dispatched_count"], 2)
        sup_reasons = [s["reason"] for s in summary["suppressed_preview"]]
        self.assertIn("suppressed_cold_start", sup_reasons)

    def test_quiet_hours_2330_to_0715_cst(self) -> None:
        store = self._new_store()
        p1 = _signal(cluster_key="us_macro_data:q1", severity="P1")
        p0 = _signal(cluster_key="crisis_breaker:q0", severity="P0", score=90)

        for quiet_dt in (_cst(2026, 11, 25, 23, 30), _cst(2026, 11, 26, 2, 15), _cst(2026, 11, 26, 7, 14)):
            self.assertEqual(store.evaluate_dispatch(p1, quiet_dt, in_calendar_p0_window=False), (False, "suppressed_quiet"))
            self.assertEqual(store.evaluate_dispatch(p0, quiet_dt, in_calendar_p0_window=False), (True, "dispatched"))
            self.assertEqual(store.evaluate_dispatch(p1, quiet_dt, in_calendar_p0_window=True), (True, "dispatched"))

        for active_dt in (_cst(2026, 11, 25, 23, 29), _cst(2026, 11, 26, 7, 15), _cst(2026, 11, 26, 14, 0)):
            self.assertEqual(store.evaluate_dispatch(p1, active_dt, in_calendar_p0_window=False), (True, "dispatched"))

    def test_p2_silent_and_export_recent_signals_and_lock(self) -> None:
        store = self._new_store()
        t0 = _cst(2026, 11, 25, 10, 0)

        p2 = _signal(signal_id="s-p2", cluster_key="c:p2", severity="P2", score=55)
        silent = _signal(signal_id="s-silent", cluster_key="c:silent", severity="SILENT", score=30)
        self.assertEqual(store.evaluate_dispatch(p2, t0), (False, "recorded_p2"))
        self.assertEqual(store.evaluate_dispatch(silent, t0), (False, "ignored_silent"))

        # Record P0, P1, P2, SILENT, plus an expired P1 (>24h ago)
        p0 = _signal(signal_id="s-p0", cluster_key="c:p0", severity="P0", score=92)
        p1 = _signal(signal_id="s-p1", cluster_key="c:p1", severity="P1", score=74)
        old_p1 = _signal(signal_id="s-old", cluster_key="c:old", severity="P1", score=72)
        store.record_signal(old_p1, "dispatched", t0 - timedelta(hours=30))
        store.record_signal(silent, "ignored_silent", t0 - timedelta(minutes=20))
        store.record_signal(p2, "recorded_p2", t0 - timedelta(minutes=10))
        store.record_signal(p1, "dispatched", t0 - timedelta(minutes=5))
        store.record_signal(p0, "dispatched", t0)

        exported = store.export_recent_signals(hours=24, now_ts=t0.timestamp() + 60)
        self.assertEqual([r["signal_id"] for r in exported], ["s-p0", "s-p1", "s-p2"])
        self.assertEqual([r["severity"] for r in exported], ["P0", "P1", "P2"])

        # File lock mutual exclusion
        self.assertTrue(store.acquire_lock())
        peer = rm.MonitorStateStore(db_path=store.db_path)
        try:
            self.assertFalse(peer.acquire_lock())
        finally:
            peer.close()


# ===========================================================================
# 5. Mandatory Safety Gates & Two-Tier Interpreter
# ===========================================================================


class TestSafetyGatesAndTwoTierInterpreter(unittest.TestCase):
    def setUp(self) -> None:
        self.now_cst = _cst(2026, 11, 25, 10, 30)

    def test_tier1_5_section_memo_across_regions_with_caps_and_calendar(self) -> None:
        ssot = _sample_ssot(gold_locked=True)
        for region, expected_cap, expected_event in (
            ("CN", "总股票仓位严守 ≤38%", "中国11月官方制造业PMI"),
            ("HK", "离岸权益 ≤33%、港股通 ≤24%", "香港金管局HIBOR与银行体系总结余例行披露"),
            ("US", "权益防弹衣 ≤26% + 超短美债 64%", "美联储FOMC利率决议与新闻发布会"),
            ("GLOBAL", "A股≤38% / 港股通≤24% / 美股≤26%", "中国11月官方制造业PMI"),
        ):
            sig = _signal(
                region=region,
                severity="P0" if region == "US" else "P1",
                anchor_snapshots=[
                    {"symbol": "US10Y", "name": "US10Y", "last": 4.625, "change_pct": 2.5, "change_bp": 12.5, "z": 2.5, "is_yield": True},
                    {"symbol": "sh000001", "name": "上证指数", "last": 3330.0, "change_pct": 1.15, "change_bp": None, "z": 3.29, "is_yield": False},
                ],
            )
            title, memo = rm.interpret_and_render_memo(sig, ssot, now_cst=self.now_cst, enable_llm=False)
            self.assertIn("🔴【一级强信号】" if region == "US" else "🟠【二级重要信号】", title)
            for sec in ("### ① ", "### ② ", "### ③ ", "### ④ ", "### ⑤ "):
                self.assertIn(sec, memo)
            self.assertIn("观望者/空仓者", memo)
            self.assertIn("已有持仓者", memo)
            self.assertIn(expected_cap, memo)
            self.assertIn(expected_event, memo)
            self.assertIn("+12.5bp", memo)
            self.assertIn("黄金红灯锁", memo)
            self.assertEqual(sig.interpreter_tier, "tier1_deterministic")

    def test_untrusted_llm_cannot_override_facts_actions_or_falsification(self) -> None:
        ssot = _sample_ssot(gold_locked=True)
        sig = _signal(region="GLOBAL", severity="P0", score=88)

        def malicious_llm(_sig, _ctx):
            return {
                "summary": "避险情绪升温，市场热议黄金大涨。",
                "transmission": "风险资产走弱，资金涌向避险资产。",
                "action_observer": "建议立即抄底买入黄金ETF 518880并分批加仓金条，同时逢低买进GLD。",
                "action_holder": "建议518880立刻补仓并分批建仓紫金矿业601899。",
                "falsification": "若金价跌破支撑则止损。",
            }

        baseline = rm.interpret_and_render_memo(sig, ssot, now_cst=self.now_cst)
        result = rm.interpret_and_render_memo(sig, ssot, now_cst=self.now_cst, enable_llm=True, llm_fn=malicious_llm)
        self.assertEqual(sig.interpreter_tier, "tier1_deterministic")
        self.assertEqual(result, baseline)
        self.assertIn("黄金红灯锁", result[1])
        self.assertNotIn("抄底买入黄金ETF", result[1])

        # Every line MUST have ZERO unnegated active Gold-buy verb!
        for line in result[1].splitlines():
            has_buy = bool(rm._GOLD_ACTIVE_BUY_RE.search(line))
            has_neg = bool(rm._GOLD_NEGATION_RE.search(line))
            self.assertFalse(
                has_buy and not has_neg,
                f"Unnegated active Gold-buy phrase survived safety gate: {line!r}",
            )

    def test_llm_adds_only_allowed_hypothesis_and_source_markup_stays_text(self) -> None:
        signal = _signal(body="资金成本待核 <img> [来源](https://example.invalid)")
        context = _sample_ssot()
        _, baseline = rm.interpret_and_render_memo(signal, context, now_cst=self.now_cst)
        _, result = rm.interpret_and_render_memo(
            signal, context, now_cst=self.now_cst, enable_llm=True,
            llm_fn=lambda *_: {"transmission_code": "funding"},
        )
        hypothesis = f"\n\n- **辅助假设（待验证）**：{rm._TRANSMISSION_HYPOTHESES['funding']}"
        self.assertEqual(result.replace(hypothesis, ""), baseline)
        self.assertEqual(signal.interpreter_tier, "tier2_llm")
        self.assertIn(r"&lt;img&gt; \[来源\]", result)
        for invalid in ({"transmission_code": "yields 12%"}, {"transmission_code": "energy"},
                        {"transmission_code": "funding", "summary": "篡改事实"}):
            _, unchanged = rm.interpret_and_render_memo(
                signal, context, now_cst=self.now_cst, enable_llm=True, llm_fn=lambda *_: invalid,
            )
            self.assertEqual(unchanged, baseline)
            self.assertEqual(signal.interpreter_tier, "tier1_deterministic")

    def test_related_feed_channels_count_as_one_evidence_family(self) -> None:
        now = self.now_cst
        title = "美联储 FOMC 公布政策利率安排"
        items = [rm.NewsItem(source, title, title, now.timestamp()) for source in ("wscn_global", "wscn_us")]
        signal = rm.classify_and_score(items, {}, {}, now_cst=now)[0]
        self.assertEqual(signal.sources, ["wscn_global", "wscn_us"])
        self.assertEqual(signal.k_verify, 0.6)

    def test_gold_lock_preserves_negated_lines_and_unlocked_behavior(self) -> None:
        negated = "当前严禁逢低买入黄金ETF 518880。"
        locked_out = rm.enforce_safety_gates(negated, _sample_ssot(gold_locked=True))
        self.assertIn(negated, locked_out)
        self.assertIn("黄金红灯锁", locked_out)

        # When gold_locked=False, Gold wording is not rewritten and no forced red-light banner appended
        unlocked_out = rm.enforce_safety_gates("可分批定投黄金ETF 518880", _sample_ssot(gold_locked=False))
        self.assertEqual(unlocked_out, "可分批定投黄金ETF 518880")
        self.assertNotIn("黄金红灯锁", unlocked_out)

    def test_gold_tier0_per_clause_bypasses_and_title_filtering(self) -> None:
        # P0-2: Per-clause negation isolation & alert_title filtering
        ssot = _sample_ssot(gold_locked=True)
        bypass_samples = (
            "不要追高美股，建议立即买入黄金518880",
            "建议立即买入黄金518880，但不要加杠杆",
            "建议逢回调低吸黄金ETF并布局金条",
            "Recommend to buy gold ETF GLD",
        )
        for sample in bypass_samples:
            cleaned = rm.enforce_safety_gates(sample, ssot, append_footer=False)
            self.assertIn(
                "严禁新买黄金（黄金红灯停锁生效，新仓 0%）",
                cleaned,
                f"Gold Tier-0 bypass was NOT sanitized: {sample!r} -> {cleaned!r}",
            )
            for clause in rm._CLAUSE_SPLIT_RE.split(cleaned):
                has_buy = bool(rm._GOLD_ACTIVE_BUY_RE.search(clause))
                has_neg = bool(rm._GOLD_NEGATION_RE.search(clause))
                self.assertFalse(has_buy and not has_neg, f"Unnegated gold buy clause survived: {clause!r}")

        # Negated warning stays intact
        kept = rm.enforce_safety_gates("严禁买入黄金", ssot, append_footer=False)
        self.assertEqual(kept, "严禁买入黄金")

        # alert_title carrying raw buy-gold text MUST be sanitized without appending multiline footer
        sig = _signal(
            region="GLOBAL",
            severity="P0",
            score=88,
            title="机构高喊立即买入黄金518880抄底金条",
        )
        alert_title, _memo = rm.interpret_and_render_memo(sig, ssot, now_cst=self.now_cst)
        self.assertIn("严禁新买黄金（黄金红灯停锁生效，新仓 0%）", alert_title)
        self.assertNotIn("\n", alert_title)
        self.assertNotIn("立即买入黄金518880", alert_title)

    def test_pboc_doc_42_crypto_firewall(self) -> None:
        # P0-3: Crypto bypasses (CN & EN) sanitized while negated warnings preserved cleanly
        bad_samples = (
            "建议配置比特币对冲通胀，并在回调时买入BTC、定投以太坊或抄底虚拟货币。",
            "建议逢低低吸比特币并增配ETH",
            "Time to buy BTC and accumulate IBIT",
            "不要追高美股，建议立即买入比特币",
        )
        for gold_locked in (True, False):
            ssot = _sample_ssot(gold_locked=gold_locked)
            for sample in bad_samples:
                cleaned = rm.enforce_safety_gates(sample, ssot, append_footer=False)
                self.assertIn(
                    "严禁境内配仓虚拟货币（遵照央行银发〔2026〕42号，0%配仓）",
                    cleaned,
                    f"Crypto bypass was NOT sanitized: {sample!r} -> {cleaned!r}",
                )
                for clause in rm._CLAUSE_SPLIT_RE.split(cleaned):
                    has_buy = bool(rm._CRYPTO_BUY_RE.search(clause))
                    has_neg = bool(rm._GOLD_NEGATION_RE.search(clause))
                    self.assertFalse(has_buy and not has_neg, f"Unnegated crypto buy clause survived: {clause!r}")

            # Negated crypto warning preserved cleanly (NOT mangled into "严禁严禁...")
            preserved = rm.enforce_safety_gates("严禁买入比特币", ssot, append_footer=False)
            self.assertEqual(preserved, "严禁买入比特币")
            self.assertNotIn("严禁严禁", preserved)

    def test_tier2_fallback_on_none_and_mocked_llm_providers(self) -> None:
        ssot = _sample_ssot(gold_locked=True)
        sig = _signal(severity="P1", score=75)

        # Returning None gracefully falls back to tier1_deterministic without crashing
        _title, memo = rm.interpret_and_render_memo(
            sig, ssot, now_cst=self.now_cst, enable_llm=True, llm_fn=lambda _s, _c: None
        )
        self.assertEqual(sig.interpreter_tier, "tier1_deterministic")
        self.assertIn("### ① ", memo)
        self.assertIn("### ⑤ ", memo)

        # Direct tests of _call_tier2_llm (100% offline via mocked urlopen + env)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(rm._call_tier2_llm(sig, ssot))

        valid_json_obj = {"transmission_code": "funding"}
        gemini_resp = {"candidates": [{"content": {"parts": [{"text": json.dumps(valid_json_obj, ensure_ascii=False)}]}}]}
        captured_reqs: list[urllib.request.Request] = []

        def fake_gemini_urlopen(req, timeout=10):
            captured_reqs.append(req)
            return _FakeHTTPResponse(gemini_resp)

        # P1-3: Gemini API key passed via x-goog-api-key header (NEVER in URL query string)
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake-gemini-header-key"}, clear=True):
            with mock.patch("urllib.request.urlopen", side_effect=fake_gemini_urlopen):
                parsed = rm._call_tier2_llm(sig, ssot)
                self.assertEqual(parsed, valid_json_obj)
        self.assertEqual(len(captured_reqs), 1)
        req_g = captured_reqs[0]
        self.assertNotIn("fake-gemini-header-key", req_g.full_url)
        self.assertNotIn("?key=", req_g.full_url)
        hdrs_lower = {k.lower(): v for k, v in req_g.header_items()}
        self.assertEqual(hdrs_lower.get("x-goog-api-key"), "fake-gemini-header-key")

        # P1-3: Invalid model path rejected without making any network call
        for bad_model in ("../v1/evil", "gemini-2.5?key=x", "models/bad", ""):
            with mock.patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "fake-gemini-header-key", "GIR_MONITOR_GEMINI_MODEL": bad_model},
                clear=True,
            ):
                with mock.patch("urllib.request.urlopen") as m_bad:
                    self.assertIsNone(rm._call_tier2_llm(sig, ssot))
                    self.assertEqual(m_bad.call_count, 0)

        openai_resp = {"choices": [{"message": {"content": json.dumps(valid_json_obj, ensure_ascii=False)}}]}
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "fake-oai"}, clear=True):
            with mock.patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(openai_resp)):
                parsed_oai = rm._call_tier2_llm(sig, ssot)
                self.assertEqual(parsed_oai, valid_json_obj)

        # Network error -> returns None gracefully
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}, clear=True):
            with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
                self.assertIsNone(rm._call_tier2_llm(sig, ssot))


# ===========================================================================
# 6. CLI & Operational Guarantees
# ===========================================================================


class TestCLIAndOperationalGuarantees(unittest.TestCase):
    def test_render_launchd_plist_valid_xml_keepalive_runatload(self) -> None:
        xml_str = rm.render_launchd_plist(python_bin="/usr/bin/python3", enable_llm=True)
        root = ET.fromstring(xml_str)
        self.assertEqual(root.tag, "plist")
        dict_el = root.find("dict")
        self.assertIsNotNone(dict_el)

        # Parse plist <dict> key/value pairs
        children = list(dict_el)
        plist_map = {}
        for i in range(0, len(children), 2):
            plist_map[children[i].text] = children[i + 1]

        self.assertIn("KeepAlive", plist_map)
        self.assertEqual(plist_map["KeepAlive"].tag, "true")
        self.assertIn("RunAtLoad", plist_map)
        self.assertEqual(plist_map["RunAtLoad"].tag, "true")
        self.assertEqual(plist_map["Label"].text, "com.global-investment-research.realtime-monitor")
        prog_args = [el.text for el in plist_map["ProgramArguments"].findall("string")]
        self.assertIn("--daemon", prog_args)
        self.assertIn("--enable-llm", prog_args)

        # CLI --print-launchd exits 0 and emits valid XML
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = rm.main(["--print-launchd"])
        self.assertEqual(rc, 0)
        ET.fromstring(buf.getvalue())

    def test_cli_export_digest_writes_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "state.sqlite3"
            out_path = Path(td) / "nested" / "digest.json"

            store = rm.MonitorStateStore(db_path=db_path)
            now_dt = datetime.now(rm.CST)
            store.record_signal(_signal(signal_id="exp-p0", severity="P0", score=90), "dispatched", now_dt)
            store.record_signal(_signal(signal_id="exp-p2", severity="P2", score=54), "recorded_p2", now_dt)
            store.close()

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = rm.main(["--state-db", str(db_path), "--export-digest", str(out_path)])
            self.assertEqual(rc, 0)
            self.assertTrue(out_path.is_file())

            digest = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(digest["count"], 2)
            self.assertIn("exported_at_cst", digest)
            self.assertEqual({s["signal_id"] for s in digest["signals"]}, {"exp-p0", "exp-p2"})

    def test_load_ssot_context_fails_closed_when_missing_or_corrupt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            # Missing gold snapshot -> fail closed (gold_locked=True)
            ctx_missing = rm.load_ssot_context(
                gold_path=d / "missing_gold.json",
                market_path=d / "missing_mkt.json",
                policy_path=d / "missing_pol.json",
                calendar_path=d / "missing_cal.json",
            )
            self.assertTrue(ctx_missing["gold_locked"])
            self.assertIsNone(ctx_missing["a_cap_pct"])
            self.assertIsNone(ctx_missing["a_fomo"])

            # Corrupt JSON -> fail closed
            corrupt = d / "corrupt.json"
            corrupt.write_text("{not valid json", encoding="utf-8")
            ctx_corrupt = rm.load_ssot_context(gold_path=corrupt, market_path=d / "m.json", policy_path=d / "p.json", calendar_path=d / "c.json")
            self.assertTrue(ctx_corrupt["gold_locked"])

            # String "true" (not bool True) -> fail closed
            non_bool = d / "non_bool.json"
            non_bool.write_text(json.dumps({"new_buy_allowed": "true"}), encoding="utf-8")
            ctx_non_bool = rm.load_ssot_context(gold_path=non_bool, market_path=d / "m.json", policy_path=d / "p.json", calendar_path=d / "c.json")
            self.assertTrue(ctx_non_bool["gold_locked"])

            # Explicit bool True -> unlocks
            unlocked = d / "unlocked.json"
            unlocked.write_text(json.dumps({"new_buy_allowed": True, "edition_id": "2026-11-25_0730"}), encoding="utf-8")
            ctx_unlocked = rm.load_ssot_context(gold_path=unlocked, market_path=d / "m.json", policy_path=d / "p.json", calendar_path=d / "c.json")
            self.assertFalse(ctx_unlocked["gold_locked"])
            self.assertEqual(ctx_unlocked["edition_id"], "2026-11-25_0730")

    def test_conflicting_gold_lock_and_zero_market_caps(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            gold = Path(td) / "gold.json"
            market = Path(td) / "market.json"
            gold.write_text(json.dumps({"tier_code": "Tier 0", "new_buy_allowed": True}), encoding="utf-8")
            market.write_text(json.dumps({"markets": {
                "a_share": {"equity_cap_pct": 0},
                "hk_stock": {"onshore_connect_cap_pct": 0},
                "us_stock": {"equity_cap_pct": 0, "cash_tbill_pct": 0},
            }}), encoding="utf-8")
            snapshot = rm.load_ssot_context(gold_path=gold, market_path=market)
        self.assertTrue(snapshot["gold_locked"])
        self.assertEqual([snapshot[key] for key in ("a_cap_pct", "hk_onshore_cap_pct", "us_cap_pct", "us_cash_pct")], [0, 0, 0, 0])
        self.assertIsNone(snapshot["hk_offshore_cap_pct"])
        _, memo = rm.interpret_and_render_memo(_signal(region="HK"), snapshot, now_cst=_cst(2026, 11, 25, 10))
        self.assertIn("离岸权益 待核、港股通 ≤0%", memo)
        self.assertIn("黄金红灯锁", memo)

    def test_dry_run_cli_does_not_create_db_or_lock(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "nested" / "realtime.sqlite3"
            with mock.patch.object(rm, "run_once", return_value={}) as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rm.main(["--once", "--dry-run", "--state-db", str(db)]), 0)
            self.assertTrue(run.call_args.kwargs["dry_run"])
            self.assertFalse(db.parent.exists())

    def test_isolated_data_root_tracks_complete_release_once_and_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            selected = folder / "current"
            editions = ("2026-11-28_1130", "2026-11-28_1800")
            for edition in editions:
                release = folder / edition
                for relative, payload in (
                    ("gold/data_snapshot.json", {"edition_id": edition, "new_buy_allowed": False}),
                    ("gold/market_calendar.json", {"timezone": "Asia/Shanghai"}),
                    ("equity/state/market_state.json", {"edition_id": edition}),
                    ("equity/state/policy_calendar.json", {"edition_id": edition, "events": []}),
                    ("equity/state/klines/core.json", {"edition_id": edition, "series": {}}),
                ):
                    path = release / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(payload), encoding="utf-8")

            selected.symlink_to(folder / editions[0], target_is_directory=True)
            before = _snapshot_tree_metadata([folder / editions[0], folder / editions[1]])
            config = folder / "missing-notify.json"
            state = folder / "monitor.sqlite"
            doctor_args = [
                "--doctor", "--data-root", str(selected), "--state-db", str(state), "--notify-config", str(config),
            ]
            with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(rm.main(doctor_args), 0)
                self.assertEqual(json.loads(stdout.getvalue())["ssot"]["edition_id"], editions[0])

            replacement = folder / "next"
            replacement.symlink_to(folder / editions[1], target_is_directory=True)
            replacement.replace(selected)
            with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(rm.main(doctor_args), 0)
                self.assertEqual(json.loads(stdout.getvalue())["ssot"]["edition_id"], editions[1])
                plist = plistlib.loads(rm.render_launchd_plist(
                    data_root=selected, state_db=state, notify_config_path=config,
                ).encode())
            self.assertEqual(plist["ProgramArguments"][-6:], [
                "--data-root", str(selected), "--state-db", str(state), "--notify-config", str(config),
            ])
            self.assertFalse(state.exists())
            self.assertEqual(before, _snapshot_tree_metadata([folder / editions[0], folder / editions[1]]))

            bad_policy = folder / editions[1] / "equity/state/policy_calendar.json"
            bad_policy.write_text(json.dumps({"edition_id": editions[0], "events": []}), encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(rm.main(doctor_args), 2)
                self.assertIn("same edition_id", stderr.getvalue())

            unresolved = folder / editions[1] / state_transaction.JOURNAL_NAME
            unresolved.write_text("{}", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(rm.main(doctor_args), 2)
                self.assertIn("state transaction needs recovery", stderr.getvalue())

    def test_load_ssot_context_real_repo_strictly_readonly(self) -> None:
        gold_dir = rm.REPO_ROOT / "gold"
        equity_dir = rm.REPO_ROOT / "equity"
        before = _snapshot_tree_metadata([gold_dir, equity_dir])

        ctx = rm.load_ssot_context()
        vols = rm.load_vol_baselines()

        after = _snapshot_tree_metadata([gold_dir, equity_dir])
        self.assertEqual(before, after, "Read-only SSOT/vol load must never modify or create files under gold/ or equity/")
        self.assertIn("edition_id", ctx)
        self.assertIsInstance(ctx["gold_locked"], bool)
        self.assertIsInstance(ctx["a_cap_pct"], int)
        self.assertIsInstance(ctx["events"], list)
        self.assertIn("sh000001", vols)
        self.assertIn("US10Y", vols)

    def test_calendar_p0_window_and_region_market_hours(self) -> None:
        events = [
            {
                "date_cst": "2026-11-26",
                "time_cst": "03:00",
                "region": "US",
                "impact_tier": "P0",
                "title": "FOMC决议",
                "monitor_window_min": 90,
            },
            {
                "date_cst": "2026-11-28",
                "end_date_cst": "2026-11-29",
                "time_cst": "全天",
                "region": "CN",
                "impact_tier": "P0",
                "title": "重要政策会议",
            },
            {
                "date_cst": "2026-11-26",
                "time_cst": "10:00",
                "region": "CN",
                "impact_tier": "P1",
                "title": "一般P1事件",
                "monitor_window_min": 120,
            },
        ]
        self.assertTrue(rm.is_in_calendar_p0_window(events, _cst(2026, 11, 26, 2, 0)))
        self.assertFalse(rm.is_in_calendar_p0_window(events, _cst(2026, 11, 26, 10, 0)))  # P1 only
        self.assertTrue(rm.is_in_calendar_p0_window(events, _cst(2026, 11, 29, 15, 0)))  # multi-day P0

        # Market hours sanity
        self.assertTrue(rm.is_region_market_open("CN", _cst(2026, 11, 25, 10, 0)))
        self.assertFalse(rm.is_region_market_open("CN", _cst(2026, 11, 25, 12, 0)))
        self.assertTrue(rm.is_region_market_open("HK", _cst(2026, 11, 25, 15, 30)))
        self.assertTrue(rm.is_region_market_open("US", _cst(2026, 11, 25, 22, 30)))
        self.assertTrue(rm.is_region_market_open("US", _cst(2026, 11, 26, 3, 0)))
        self.assertFalse(rm.is_region_market_open("CN", _cst(2026, 11, 28, 10, 0)))  # Saturday

    def test_reject_repo_worktree_writes_and_doctor_cli(self) -> None:
        # P1-4: _reject_repo_worktree_write blocks --state-db and --export-digest inside gold/ or equity/
        gold_db = rm.REPO_ROOT / "gold" / "forbidden_monitor.sqlite3"
        equity_digest = rm.REPO_ROOT / "equity" / "state" / "forbidden_digest.json"

        with self.assertRaisesRegex(ValueError, "repository working tree"):
            rm._reject_repo_worktree_write(gold_db, "state_db")
        with self.assertRaisesRegex(ValueError, "repository working tree"):
            rm._reject_repo_worktree_write(equity_digest, "export_digest")
        with self.assertRaisesRegex(ValueError, "repository working tree"):
            rm.MonitorStateStore(db_path=gold_db)
        with self.assertRaisesRegex(ValueError, "repository working tree"):
            rm.main(["--state-db", str(gold_db), "--once"])

        # .git/ target is permitted by worktree guard
        rm._reject_repo_worktree_write(rm._resolve_git_dir() / "realtime-monitor.sqlite3", "state_db")

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            valid_db = d / "monitor.sqlite3"
            with self.assertRaisesRegex(ValueError, "repository working tree"):
                rm.main(["--state-db", str(valid_db), "--export-digest", str(equity_digest)])
            self.assertFalse(equity_digest.exists())

            # P1-9: --doctor CLI runs cleanly offline and reports SSOT, Gold lock, vols & notify health
            cfg_path = d / "notify.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "outbox_path": str(d / "outbox.jsonl"),
                        "dedupe_path": str(d / "dedupe.json"),
                        "providers": {},
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(cfg_path, 0o600)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = rm.main(["--doctor", "--notify-config", str(cfg_path), "--state-db", str(valid_db)])
            self.assertEqual(rc, 0)
            doc = json.loads(buf.getvalue())
            self.assertIn("timestamp_cst", doc)
            self.assertIn("edition_id", doc["ssot"])
            self.assertIsInstance(doc["ssot"]["gold_locked"], bool)
            self.assertGreater(doc["vol_baselines_loaded"], 0)
            self.assertEqual(doc["feed_sources_count"], len(rm.FEED_SOURCES))
            self.assertEqual(doc["state_db"], str(valid_db))
            self.assertIn("providers", doc["notify"])

    def test_run_once_end_to_end_offline_dry_run(self) -> None:
        now_dt = _cst(2026, 11, 25, 10, 30)
        # sh000001 +2.21% (< 2.5% shock threshold, z~1.8) + fx_susdcnh -0.83% (z~-2.8) -> strong news signal without standalone market shock
        sh_parts = ["上证指数", "3300", "3300", "3373"] + ["0"] * 26 + ["2026-11-25", "10:30:00", "00"]
        fx_parts = ["10:30:00", "7.1500", "7.1505", "7.2100", "0", "7.20", "7.21", "7.14", "7.15", "离岸人民币"]
        gov_payload = json.dumps(
            [
                {
                    "TITLE": "国务院常务会议部署更加积极的财政与适度宽松货币政策",
                    "DOCRELPUBTIME": "2026-11-25 10:25:00",
                    "URL": "/yaowen/202611/1.htm",
                }
            ],
            ensure_ascii=False,
        ).encode("utf-8")

        def fake_http_get(url: str, *, headers=None, timeout=10) -> bytes:
            if "YAOWENLIEBIAO.json" in url:
                return gov_payload
            if "hq.sinajs.cn" in url and "sh000001" in url:
                return f'var hq_str_sh000001="{",".join(sh_parts)}";'.encode("gbk")
            if "hq.sinajs.cn" in url and "fx_susdcnh" in url:
                return f'var hq_str_fx_susdcnh="{",".join(fx_parts)}";'.encode("gbk")
            if "quote.cnbc.com" in url:
                return json.dumps(
                    {
                        "FormattedQuoteResult": {
                            "FormattedQuote": [
                                {"symbol": "US10Y", "last": "4.45%", "previous_day_closing": "4.42%"}
                            ]
                        }
                    }
                ).encode("utf-8")
            raise AssertionError(f"Unexpected URL: {url}")

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            notify_cfg = d / "notify.json"
            notify_cfg.write_text(
                json.dumps(
                    {
                        "outbox_path": str(d / "outbox.jsonl"),
                        "dedupe_path": str(d / "dedupe.json"),
                        "providers": {},
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(notify_cfg, 0o600)

            store = rm.MonitorStateStore(db_path=d / "monitor.sqlite3")
            try:
                with mock.patch.object(rm, "_http_get_bytes", side_effect=fake_http_get), mock.patch.object(
                    rm, "_call_tier2_llm", side_effect=AssertionError("dry-run must not call an LLM"),
                ) as llm:
                    summary = rm.run_once(
                        store=store,
                        dry_run=True,
                        enable_llm=True,
                        sources_filter={"gov_yaowen"},
                        notify_config_path=notify_cfg,
                        now_cst=now_dt,
                    )
                    self.assertEqual(summary["feeds_fetched"], 1)
                    self.assertEqual(summary["feeds_unseen"], 1)
                    self.assertGreaterEqual(summary["dispatched_count"], 1)
                    self.assertEqual(summary["dispatched"][0]["domain_id"], "cn_top_meeting")
                    self.assertEqual(summary["dispatched"][0]["action"], "dry_run_dispatch")
                    self.assertIn(summary["dispatched"][0]["severity"], ("P0", "P1"))
                    llm.assert_not_called()

                    # dry_run=True MUST NOT mutate production seen_items / sent_clusters / signal_audit
                    self.assertEqual(store._conn.execute("SELECT COUNT(*) FROM seen_items").fetchone()[0], 0)
                    self.assertEqual(store._conn.execute("SELECT COUNT(*) FROM sent_clusters").fetchone()[0], 0)

                    # Second dry-run immediately after still sees 1 unseen item
                    summary2 = rm.run_once(
                        store=store,
                        dry_run=True,
                        enable_llm=False,
                        sources_filter={"gov_yaowen"},
                        notify_config_path=notify_cfg,
                        now_cst=now_dt + timedelta(minutes=2),
                    )
                    self.assertEqual(summary2["feeds_unseen"], 1)
                    self.assertGreaterEqual(summary2["dispatched_count"], 1)
            finally:
                store.close()

    def test_run_once_live_mode_dedupe_and_failed_delivery_does_not_lock_cooldown(self) -> None:
        now_dt = _cst(2026, 11, 25, 10, 30)
        sh_parts = ["上证指数", "3300", "3300", "3373"] + ["0"] * 26 + ["2026-11-25", "10:30:00", "00"]
        fx_parts = ["10:30:00", "7.1500", "7.1505", "7.2100", "0", "7.20", "7.21", "7.14", "7.15", "离岸人民币"]
        gov_payload = json.dumps(
            [
                {
                    "TITLE": "国务院常务会议部署更加积极的财政与适度宽松货币政策",
                    "DOCRELPUBTIME": "2026-11-25 10:25:00",
                    "URL": "/yaowen/202611/1.htm",
                }
            ],
            ensure_ascii=False,
        ).encode("utf-8")

        def fake_http_get(url: str, *, headers=None, timeout=10) -> bytes:
            if "YAOWENLIEBIAO.json" in url:
                return gov_payload
            if "hq.sinajs.cn" in url and "sh000001" in url:
                return f'var hq_str_sh000001="{",".join(sh_parts)}";'.encode("gbk")
            if "hq.sinajs.cn" in url and "fx_susdcnh" in url:
                return f'var hq_str_fx_susdcnh="{",".join(fx_parts)}";'.encode("gbk")
            if "quote.cnbc.com" in url:
                return json.dumps(
                    {
                        "FormattedQuoteResult": {
                            "FormattedQuote": [
                                {"symbol": "US10Y", "last": "4.45%", "previous_day_closing": "4.42%"}
                            ]
                        }
                    }
                ).encode("utf-8")
            raise AssertionError(f"Unexpected URL: {url}")

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)

            # 1. no_provider_configured MUST NOT lock sent_clusters cooldown
            empty_cfg = d / "empty_notify.json"
            empty_cfg.write_text(
                json.dumps(
                    {
                        "outbox_path": str(d / "outbox_empty.jsonl"),
                        "dedupe_path": str(d / "dedupe_empty.json"),
                        "providers": {},
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(empty_cfg, 0o600)
            store_empty = rm.MonitorStateStore(db_path=d / "empty.sqlite3")
            try:
                with mock.patch.object(rm, "_http_get_bytes", side_effect=fake_http_get), mock.patch.dict(
                    os.environ, {}, clear=True
                ):
                    s_empty = rm.run_once(
                        store=store_empty,
                        dry_run=False,
                        enable_llm=False,
                        sources_filter={"gov_yaowen"},
                        notify_config_path=empty_cfg,
                        now_cst=now_dt,
                    )
                self.assertEqual(s_empty["dispatched"][0]["action"], "no_provider_configured")
                self.assertEqual(store_empty._conn.execute("SELECT COUNT(*) FROM sent_clusters").fetchone()[0], 0)
                self.assertEqual(len(store_empty.pending_news(now_dt.timestamp())), 1)
                self.assertFalse(store_empty.pending_news((now_dt + timedelta(hours=3)).timestamp(), persist=False))
            finally:
                store_empty.close()

            # 2. delivery_failed MUST NOT lock sent_clusters cooldown
            wecom_cfg = d / "wecom_notify.json"
            wecom_cfg.write_text(
                json.dumps(
                    {
                        "quiet_hours": {"enabled": False, "start": "23:30", "end": "07:15"},
                        "outbox_path": str(d / "outbox_wecom.jsonl"),
                        "dedupe_path": str(d / "dedupe_wecom.json"),
                        "providers": {
                            "wecom_webhook": {
                                "enabled": True,
                                "min_severity": "P2",
                                "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=live-test-key-1111",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(wecom_cfg, 0o600)

            restored_config = d / "restored_notify.json"
            restored_payload = json.loads(wecom_cfg.read_text(encoding="utf-8"))
            restored_payload["dedupe_path"] = str(d / "restored_dedupe.json")
            restored_config.write_text(json.dumps(restored_payload), encoding="utf-8")
            os.chmod(restored_config, 0o600)
            def feed_after_rotation(url: str, *, headers=None, timeout=10) -> bytes:
                if "YAOWENLIEBIAO.json" in url:
                    return b"[]"
                return fake_http_get(url, headers=headers, timeout=timeout)

            with contextlib.closing(rm.MonitorStateStore(db_path=d / "empty.sqlite3")) as restored:
                with mock.patch.object(rm, "_http_get_bytes", side_effect=feed_after_rotation), mock.patch(
                    "urllib.request.urlopen",
                    return_value=_FakeHTTPResponse({"errcode": 0, "errmsg": "ok"}, status=200),
                ), mock.patch.dict(os.environ, {}, clear=True):
                    recovered = rm.run_once(
                        store=restored, sources_filter={"gov_yaowen"}, notify_config_path=restored_config,
                        now_cst=now_dt + timedelta(minutes=2),
                    )
                    self.assertEqual(recovered["feeds_fetched"], 0)
                    self.assertEqual(recovered["retry_news_count"], 1)
                    self.assertEqual(recovered["dispatched"][0]["action"], "dispatched")
                    self.assertFalse(restored.pending_news(now_dt.timestamp()))

            store_fail = rm.MonitorStateStore(db_path=d / "fail.sqlite3")
            try:
                with mock.patch.object(rm, "_http_get_bytes", side_effect=fake_http_get), mock.patch(
                    "urllib.request.urlopen",
                    return_value=_FakeHTTPResponse({"errcode": 93000, "errmsg": "bad webhook"}, status=200),
                ), mock.patch.dict(os.environ, {}, clear=True):
                    s_fail = rm.run_once(
                        store=store_fail,
                        dry_run=False,
                        enable_llm=False,
                        sources_filter={"gov_yaowen"},
                        notify_config_path=wecom_cfg,
                        now_cst=now_dt,
                    )
                self.assertEqual(s_fail["dispatched"][0]["action"], "delivery_failed")
                self.assertEqual(store_fail._conn.execute("SELECT COUNT(*) FROM sent_clusters").fetchone()[0], 0)
            finally:
                store_fail.close()

            # 3. Live successful delivery commits seen_items & sent_clusters, deduping poll 2
            store_ok = rm.MonitorStateStore(db_path=d / "ok.sqlite3")
            try:
                with mock.patch.object(rm, "_http_get_bytes", side_effect=fake_http_get), mock.patch(
                    "urllib.request.urlopen",
                    return_value=_FakeHTTPResponse({"errcode": 0, "errmsg": "ok"}, status=200),
                ), mock.patch.dict(os.environ, {}, clear=True):
                    s_ok1 = rm.run_once(
                        store=store_ok,
                        dry_run=False,
                        enable_llm=False,
                        sources_filter={"gov_yaowen"},
                        notify_config_path=wecom_cfg,
                        now_cst=now_dt,
                    )
                    self.assertEqual(s_ok1["feeds_unseen"], 1)
                    self.assertEqual(s_ok1["dispatched"][0]["action"], "dispatched")
                    self.assertEqual(store_ok._conn.execute("SELECT COUNT(*) FROM sent_clusters").fetchone()[0], 1)

                    s_ok2 = rm.run_once(
                        store=store_ok,
                        dry_run=False,
                        enable_llm=False,
                        sources_filter={"gov_yaowen"},
                        notify_config_path=wecom_cfg,
                        now_cst=now_dt + timedelta(minutes=2),
                    )
                    self.assertEqual(s_ok2["feeds_unseen"], 0)
                    self.assertEqual(s_ok2["dispatched_count"], 0)
            finally:
                store_ok.close()

    def test_run_once_recovers_unscored_and_unrendered_news_after_restart(self) -> None:
        now = _cst(2026, 11, 25, 10, 30)
        alert = rm.NewsItem("gov_yaowen", "国务院常务会议部署财政政策", "财政政策", now.timestamp())
        unrelated = rm.NewsItem("sina_724", "无相关信号", "", now.timestamp())

        def score(items, *args, **kwargs):
            if alert not in items:
                return []
            signal = _signal(title=alert.title, severity="P0", score=87)
            signal.item_hashes = [rm._news_item_hash(alert)]
            return [signal]

        for step, expected_pending in (("classify_and_score", 2), ("interpret_and_render_memo", 1)):
            with self.subTest(step=step), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                db = root / "monitor.sqlite3"
                config = root / "notify.json"
                config.write_text(json.dumps({
                    "outbox_path": str(root / "outbox.jsonl"),
                    "dedupe_path": str(root / "dedupe.json"),
                    "providers": {"wecom_webhook": {
                        "enabled": True,
                        "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=offline-fixture",
                    }},
                }), encoding="utf-8")
                config.chmod(0o600)
                with contextlib.ExitStack() as mocks:
                    for name, value in (
                        ("_load_monitor_inputs", (root, _sample_ssot(), {})),
                        ("poll_live_quotes", ({}, {})),
                        ("detect_upcoming_calendar_alerts", []),
                        ("detect_market_first_anomalies", []),
                    ):
                        mocks.enter_context(mock.patch.object(rm, name, return_value=value))
                    mocks.enter_context(mock.patch.dict(os.environ, {}, clear=True))
                    mocks.enter_context(mock.patch.object(rm, "classify_and_score", side_effect=score))
                    feed = mocks.enter_context(mock.patch.object(
                        rm, "poll_all_feeds", side_effect=[([alert, unrelated], {}), ([], {}), ([alert, unrelated], {})],
                    ))
                    post = mocks.enter_context(mock.patch(
                        "urllib.request.urlopen", return_value=_FakeHTTPResponse({"errcode": 0}, status=200),
                    ))
                    with contextlib.closing(rm.MonitorStateStore(db)) as store:
                        with mock.patch.object(rm, step, side_effect=RuntimeError("cycle interrupted")):
                            with self.assertRaisesRegex(RuntimeError, "cycle interrupted"):
                                rm.run_once(store=store, notify_config_path=config, now_cst=now)
                        self.assertEqual(store.seen_items_count(), 2)
                        self.assertEqual(len(store.pending_news(now.timestamp())), expected_pending)
                    post.assert_not_called()

                    with contextlib.closing(rm.MonitorStateStore(db)) as reopened:
                        retry = rm.run_once(store=reopened, notify_config_path=config, now_cst=now + timedelta(minutes=2))
                        self.assertEqual(retry["feeds_fetched"], 0)
                        self.assertEqual(retry["retry_news_count"], expected_pending)
                        self.assertEqual([d["action"] for d in retry["dispatched"]], ["dispatched"])
                        self.assertEqual(reopened.pending_news(now.timestamp()), [])
                        repeat = rm.run_once(store=reopened, notify_config_path=config, now_cst=now + timedelta(minutes=3))
                        self.assertEqual(repeat["dispatched_count"], 0)
                    self.assertEqual(feed.call_count, 3)
                    post.assert_called_once()

    def test_run_once_keeps_news_published_after_the_poll_cutoff(self) -> None:
        now = _cst(2026, 11, 25, 18, 0)
        news = rm.NewsItem(
            "gov_yaowen", "国务院常务会议部署财政政策", "财政政策", now.timestamp() + 1,
        )
        bad_time = rm.NewsItem("sina_724", "行情资讯时间错误", "", now.timestamp() + 86400)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        store = rm.MonitorStateStore(Path(temporary.name) / "monitor.sqlite3")
        self.addCleanup(store.close)

        with (
            mock.patch.object(rm, "_load_monitor_inputs", return_value=(store.db_path.parent, _sample_ssot(), {})),
            mock.patch.object(rm, "poll_all_feeds", side_effect=[([news, bad_time], {}), ([], {})]),
            mock.patch.object(rm, "poll_live_quotes", return_value=({}, {})),
            mock.patch.object(rm, "classify_and_score", wraps=rm.classify_and_score) as scorer,
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            config = store.db_path.with_name("missing-notify.json")
            rm.run_once(store=store, notify_config_path=config, now_cst=now)
            self.assertEqual(scorer.call_args.args[0], [])
            self.assertEqual(store.pending_news(now.timestamp()), [news])
            self.assertEqual(store.seen_items_count(), 1)

            result = rm.run_once(store=store, notify_config_path=config, now_cst=now + timedelta(minutes=3))
            self.assertEqual(result["feeds_fetched"], 0)
            self.assertEqual(scorer.call_args.args[0], [news])


    def test_round3_cjk_ascii_safety_gates_ascii_clauses_trim_and_live_market_calendar(self) -> None:
        ssot = rm.load_ssot_context()
        ssot["gold_locked"] = True

        # P0: CJK-adjacent ASCII tickers MUST be caught (增配ETH, 买入BTC, 配置USDT, 低吸gold)
        c1 = rm.enforce_safety_gates("建议逢低低吸比特币并增配ETH", ssot, append_footer=False)
        self.assertNotIn("增配ETH", c1)
        self.assertNotIn("低吸比特币", c1)
        self.assertIn("银发〔2026〕42号", c1)

        for raw in ("建议买入BTC和ETH", "建议配置USDT", "建议低吸gold"):
            san = rm.enforce_safety_gates(raw, ssot, append_footer=False)
            self.assertNotEqual(san, raw, f"Should sanitize: {raw}")

        # P1: ASCII ';' and '.' clause split + English negation preservation
        s_semi = rm.enforce_safety_gates("不要追高美股; 建议立即买入黄金518880", ssot, append_footer=False)
        self.assertNotIn("买入黄金518880", s_semi)
        self.assertIn("严禁新买黄金", s_semi)

        s_dot = rm.enforce_safety_gates("Do not buy BTC. Buy gold ETF GLD", ssot, append_footer=False)
        self.assertIn("Do not buy BTC", s_dot)
        self.assertNotIn("Buy gold ETF GLD", s_dot)

        s_neg_en = rm.enforce_safety_gates("Do not buy gold ETF GLD right now.", ssot, append_footer=False)
        self.assertEqual(s_neg_en, "Do not buy gold ETF GLD right now.")

        # P2: Bare adverbs must NOT corrupt valid gold-trim/sell advice
        s_trim = rm.enforce_safety_gates("重仓户可分批减仓黄金并严守红灯", ssot, append_footer=False)
        self.assertEqual(s_trim, "重仓户可分批减仓黄金并严守红灯")

        # P1: Self-contained synthetic market_calendar fixture (immune to live calendar start_date rollover)
        synth_mcal = {
            "schema_version": "1.0",
            "timezone": "Asia/Shanghai",
            "calendar_overrides": [
                {
                    "id": "us_thanksgiving_synth",
                    "date": "2026-11-26",
                    "end_date": "2026-11-26",
                    "markets": ["US_EQUITY", "US_BOND", "COMEX_CME"],
                    "event": "美国感恩节全天休市",
                    "overlay_mode": "A",
                    "trading_hours_bjt": {"us_equity": "全天休市", "us_bond": "全天休市"},
                },
                {
                    "id": "us_black_friday_synth",
                    "date": "2026-11-27",
                    "end_date": "2026-11-27",
                    "markets": ["US_EQUITY", "US_BOND", "COMEX_CME"],
                    "event": "美国黑色星期五提前收盘（半日市）",
                    "overlay_mode": "A",
                    "trading_hours_bjt": {"us_equity": "提前收盘半日市"},
                },
                {
                    "id": "christmas_2026_synth",
                    "date": "2026-12-25",
                    "end_date": "2026-12-25",
                    "markets": ["HK_EQUITY", "US_EQUITY", "US_BOND"],
                    "event": "圣诞节全天休市",
                    "overlay_mode": "A",
                    "trading_hours_bjt": {"hk_equity": "全天休市", "us_equity": "全天休市"},
                },
                {
                    "id": "cn_spring_festival_synth",
                    "date": "2027-02-08",
                    "end_date": "2027-02-12",
                    "markets": ["CN_A_SHARE"],
                    "event": "中国春节法定休市",
                    "overlay_mode": "B",
                    "trading_hours_bjt": {"cn_a_share": "法定休市"},
                },
            ],
        }
        # Live market_calendar schema smoke check (never tied to historical dates that roll off)
        self.assertIsInstance(ssot.get("market_calendar"), dict)
        self.assertIsInstance(ssot["market_calendar"].get("calendar_overrides"), list)

        # US Thanksgiving 2026-11-26 (23:00 CST & next-day 01:00 CST overnight session) -> CLOSED
        self.assertFalse(rm.is_region_market_open("US", _cst(2026, 11, 26, 23, 0), market_calendar=synth_mcal))
        self.assertFalse(rm.is_region_market_open("US", _cst(2026, 11, 27, 1, 0), market_calendar=synth_mcal))
        # Black Friday 2026-11-27 is a half-day session (NOT full-day closed at 23:00 CST) -> OPEN
        self.assertTrue(rm.is_region_market_open("US", _cst(2026, 11, 27, 23, 0), market_calendar=synth_mcal))
        # Christmas 2026-12-25 -> HK & US CLOSED
        self.assertFalse(rm.is_region_market_open("HK", _cst(2026, 12, 25, 10, 30), market_calendar=synth_mcal))
        self.assertFalse(rm.is_region_market_open("US", _cst(2026, 12, 25, 23, 0), market_calendar=synth_mcal))
        # CN Spring Festival 2027-02-08 -> CN CLOSED
        self.assertFalse(rm.is_region_market_open("CN", _cst(2027, 2, 8, 10, 30), market_calendar=synth_mcal))


class TestWave2MonitorHardeningRegressions(unittest.TestCase):
    def test_market_hours_use_eastern_dst_and_separate_early_closes(self) -> None:
        calendar = rm.load_ssot_context()["market_calendar"]
        self.assertFalse(rm.is_region_market_open("US", _cst(2026, 11, 27, 21, 30), market_calendar=calendar))
        self.assertTrue(rm.is_region_market_open("US", _cst(2026, 11, 27, 22, 30), market_calendar=calendar))
        self.assertFalse(rm.is_region_market_open("US", _cst(2026, 11, 28, 2, 0), market_calendar=calendar))
        self.assertTrue(rm.is_region_market_open("US", _cst(2027, 3, 15, 21, 30), market_calendar=calendar))
        self.assertFalse(rm.is_region_market_open("US", _cst(2027, 3, 16, 4, 0), market_calendar=calendar))
        self.assertFalse(rm.is_region_market_open("HK", _cst(2026, 12, 24, 13, 0), market_calendar=calendar))

        us10y = rm.QuoteTick("US10Y", "美债十年期", 5.3, 5.11, 3.7, 19, "2026-11-27 13:29 EST", True, "cnbc")
        vix = rm.QuoteTick("b_VIX", "VIX", 45, 35, 28.6, timestamp="2026-11-27 12:59 EST", source="cnbc")
        quotes = {"US10Y": us10y, "b_VIX": vix}
        at_0230 = rm.detect_market_first_anomalies(quotes, {}, now_cst=_cst(2026, 11, 28, 2, 30), market_calendar=calendar)
        self.assertEqual([sig.cluster_key.split(":")[1] for sig in at_0230], ["us10y_breaker"])
        self.assertEqual(rm.detect_market_first_anomalies(
            quotes, {}, now_cst=_cst(2026, 11, 28, 3, 0), market_calendar=calendar,
        ), [])

    def test_old_and_cross_window_vix_are_excluded_and_fresh_vendor_quote_linked(self) -> None:
        regular = _cst(2026, 11, 25, 23, 45)
        for raw_time, emits in (("2026-11-25 10:10 EST", False), ("2026-11-25 10:30 EST", True), ("10:30 EST", False), ("", False)):
            vix = rm.QuoteTick("b_VIX", "VIX", 45, 35, 28.6, timestamp=raw_time, source="cnbc")
            signals = rm.detect_market_first_anomalies({"b_VIX": vix}, {}, now_cst=regular)
            self.assertEqual(bool(signals), emits)
            if signals:
                self.assertFalse(signals[0].is_official)
                _, memo = rm.interpret_and_render_memo(signals[0], _sample_ssot(), now_cst=regular)
                self.assertIn("行情数据", memo)
                self.assertIn("[来源 1](https://www.cnbc.com/quotes/.VIX)", memo)
                self.assertIn("CNBC 行情 · 2026-11-25 23:30:00 北京时间", memo)
        prior_window = rm.QuoteTick("b_VIX", "VIX", 45, 35, 28.6, timestamp="2026-11-25 09:24 EST", source="cnbc")
        self.assertEqual(rm.detect_market_first_anomalies(
            {"b_VIX": prior_window}, {}, now_cst=_cst(2026, 11, 25, 22, 31),
        ), [])

    def test_time_only_vendor_quote_has_display_provenance_but_no_scoring_weight(self) -> None:
        now = _cst(2026, 11, 25, 23, 45)
        item = rm.NewsItem(
            "fed_monetary", "Federal Reserve FOMC statement signals rate path shift",
            "FOMC committee update", now.timestamp() - 60, is_official=True,
        )
        quote = rm.QuoteTick("US10Y", "美债十年期", 5.3, 5.11, 3.7, 19, "10:30 EST", True, "cnbc")
        self.assertIsNone(rm._quote_observed_at(quote))
        self.assertEqual(rm.detect_market_first_anomalies({"US10Y": quote}, {}, now_cst=now), [])
        reference = rm.classify_and_score([item], {"US10Y": quote}, {}, now_cst=now)[0]
        baseline = rm.classify_and_score([item], {}, {}, now_cst=now)[0]
        self.assertEqual((reference.score, reference.max_z), (baseline.score, baseline.max_z))
        self.assertIsNone(reference.anchor_snapshots[0]["observed_at_cst"])
        _, memo = rm.interpret_and_render_memo(reference, _sample_ssot(), now_cst=now)
        self.assertIn("CNBC 行情 · 原报 10:30 EST，日期未核，仅作参考", memo)

    def test_stale_closed_tick_suppressed_in_classify_and_score_weekend_and_holiday(self) -> None:
        vol_baselines = {"sh000001": 1.0, "US10Y": 5.0, "hf_ES": 1.0}
        # 1. Weekend (Saturday 2026-11-28 14:00 CST): stale Friday huge moves must NOT confirm news
        sat_now = _cst(2026, 11, 28, 14, 0)
        item_wknd = rm.NewsItem(
            source="pbc_news",
            title="央行宣布全面降准0.5个百分点",
            body="释放长期流动性。",
            published_ts=sat_now.timestamp() - 60,
            url="https://www.pbc.gov.cn/1",
            importance_flag=1,
            is_official=True,
        )
        stale_quotes = {
            "sh000001": _tick("sh000001", 3900.0, -4.8, timestamp="2026-11-27 15:00:00"),
            "US10Y": _tick("US10Y", 5.30, 3.8, change_bp=22.0, is_yield=True, timestamp="2026-11-27 16:00:00"),
            "hf_ES": _tick("hf_ES", 6800.0, -4.5, timestamp="2026-11-27 16:00:00"),
        }
        sigs_wknd = rm.classify_and_score([item_wknd], stale_quotes, vol_baselines, now_cst=sat_now)
        self.assertEqual(len(sigs_wknd), 1)
        self.assertEqual(sigs_wknd[0].max_z, 0.0)
        self.assertEqual(sigs_wknd[0].anchor_snapshots, [])
        self.assertEqual(
            rm.detect_market_first_anomalies(stale_quotes, vol_baselines, now_cst=sat_now),
            [],
        )

        # 2. Full-day US holiday (Thanksgiving Thu 2026-11-26 23:00 CST): US10Y / ES stale shocks suppressed
        holiday_cal = {
            "calendar_overrides": [
                {
                    "id": "us_holiday_test",
                    "date": "2026-11-26",
                    "end_date": "2026-11-26",
                    "markets": ["US_EQUITY", "US_BOND"],
                    "event": "美国感恩节全天休市",
                    "overlay_mode": "A",
                    "trading_hours_bjt": {"us_equity": "全天休市", "us_bond": "全天休市"},
                }
            ]
        }
        hol_now = _cst(2026, 11, 26, 23, 0)
        item_hol = rm.NewsItem(
            source="fed_rss",
            title="Federal Reserve issues FOMC statement on policy rate",
            body="FOMC policy rate decision.",
            published_ts=hol_now.timestamp() - 60,
            url="https://www.federalreserve.gov/1",
            importance_flag=1,
            is_official=True,
        )
        hol_quotes = {
            "US10Y": _tick("US10Y", 5.32, 4.0, change_bp=24.0, is_yield=True, timestamp="2026-11-25 16:00:00"),
            "hf_ES": _tick("hf_ES", 6750.0, -4.2, timestamp="2026-11-25 16:00:00"),
        }
        sigs_hol = rm.classify_and_score(
            [item_hol], hol_quotes, vol_baselines, now_cst=hol_now, market_calendar=holiday_cal
        )
        self.assertEqual(len(sigs_hol), 1)
        self.assertEqual(sigs_hol[0].max_z, 0.0)
        self.assertEqual(sigs_hol[0].anchor_snapshots, [])
        self.assertEqual(
            rm.detect_market_first_anomalies(
                hol_quotes, vol_baselines, now_cst=hol_now, market_calendar=holiday_cal
            ),
            [],
        )

    def test_sunday_global_is_closed_in_is_region_market_open(self) -> None:
        self.assertFalse(rm.is_region_market_open("GLOBAL", _cst(2026, 11, 28, 6, 0)))   # Fri 17:00 EST
        self.assertFalse(rm.is_region_market_open("GLOBAL", _cst(2026, 11, 29, 12, 0)))  # Sun 12:00
        self.assertFalse(rm.is_region_market_open("GLOBAL", _cst(2026, 11, 29, 23, 30))) # Sun 23:30
        self.assertFalse(rm.is_region_market_open("GLOBAL", _cst(2026, 11, 30, 5, 30)))  # Mon 05:30
        self.assertTrue(rm.is_region_market_open("GLOBAL", _cst(2026, 11, 30, 6, 30)))   # Mon 06:30

    def test_same_day_date_only_official_notice_survives_afternoon_while_prior_day_expires(self) -> None:
        afternoon = _cst(2026, 11, 25, 14, 30)
        today_midnight = _cst(2026, 11, 25, 0, 0).timestamp()
        yesterday_midnight = _cst(2026, 11, 24, 0, 0).timestamp()

        # 1. Direct NewsItem with date_only=True (same-day pbc_news) survives at 14:30 CST (> 3h after 00:00)
        same_day = rm.NewsItem(
            source="pbc_news",
            title="央行宣布下调存款准备金率0.5个百分点",
            body="释放长期流动性",
            published_ts=today_midnight,
            url="https://www.pbc.gov.cn/today",
            importance_flag=1,
            is_official=True,
            date_only=True,
        )
        prior_day = rm.NewsItem(
            source="pbc_news",
            title="央行宣布下调存款准备金率0.25个百分点",
            body="昨日公告",
            published_ts=yesterday_midnight,
            url="https://www.pbc.gov.cn/yesterday",
            importance_flag=1,
            is_official=True,
            date_only=True,
        )
        sigs = rm.classify_and_score([same_day, prior_day], {}, {}, now_cst=afternoon)
        self.assertEqual(len(sigs), 1)
        self.assertIn("0.5个百分点", sigs[0].title)

        # 2. parse_gov_cn_json also marks same-day date-only notices as fresh while leaving prior-day stale
        gov_payload = json.dumps(
            [
                {"TITLE": "国务院常务会议部署一揽子增量政策", "DOCRELPUBTIME": "2026-11-25", "URL": "/yaowen/today.htm"},
                {"TITLE": "国务院常务会议昨日旧闻", "DOCRELPUBTIME": "2026-11-24", "URL": "/yaowen/old.htm"},
            ],
            ensure_ascii=False,
        ).encode("utf-8")
        parsed_gov = rm.parse_gov_cn_json(gov_payload, "gov_yaowen", afternoon.timestamp())
        gov_sigs = rm.classify_and_score(parsed_gov, {}, {}, now_cst=afternoon)
        self.assertEqual(len(gov_sigs), 1)
        self.assertIn("一揽子增量政策", gov_sigs[0].title)

    def test_tightened_keywords_reject_false_positives_and_title_scope_keywords_neg(self) -> None:
        # False positives MUST NOT match any policy domain
        for noise in (
            "京东方 BOE 公布柔性 OLED 面板产线最新进展",
            "The Game Awards TGA 2026 年度最佳游戏提名揭晓",
            "Wall St. edges higher in light holiday trading",
            "St. Louis Fed working paper analyzes regional bank lending",
        ):
            with self.subTest(noise=noise):
                self.assertIsNone(rm.match_policy_domain(noise), f"False positive matched: {noise!r}")

        # True positives MUST match expected domains
        r_tariff = rm.match_policy_domain("USTR announces new Section 301 tariffs on semiconductor imports")
        self.assertIsNotNone(r_tariff)
        assert r_tariff is not None
        self.assertEqual(r_tariff.domain_id, "cn_tariff")

        r_cpi = rm.match_policy_domain("U.S. CPI comes in hotter than expected in November")
        self.assertIsNotNone(r_cpi)
        assert r_cpi is not None
        self.assertEqual(r_cpi.domain_id, "us_macro_data")

        # Title-scoped keywords_neg: title matches us_fomc, body mentions foreign CBs -> MUST NOT kill match!
        r_scoped = rm.match_policy_domain(
            "美联储FOMC宣布下调基准利率25个基点",
            "分析称市场亦关注中国人民银行、欧洲央行与日本央行后续货币政策动向。",
        )
        self.assertIsNotNone(r_scoped)
        assert r_scoped is not None
        self.assertEqual(r_scoped.domain_id, "us_fed_fomc")

    def test_multiday_allday_p0_event_respects_quiet_hours_while_exact_time_stays_active(self) -> None:
        allday_ev = [
            {
                "event_id": "cewc_2026",
                "date_cst": "2026-12-10",
                "end_date_cst": "2026-12-12",
                "time_cst": "全天窗口",
                "impact_tier": "P0",
                "monitor_window_min": 60,
            }
        ]
        # Overnight quiet hours (01:30 CST) -> multi-day 全天窗口 P0 MUST NOT wake quiet hours
        self.assertFalse(rm.is_in_calendar_p0_window(allday_ev, _cst(2026, 12, 11, 1, 30)))
        # Daytime (14:00 CST) -> active
        self.assertTrue(rm.is_in_calendar_p0_window(allday_ev, _cst(2026, 12, 11, 14, 0)))

        exact_ev = [
            {
                "event_id": "fomc_dec_2026",
                "date_cst": "2026-12-10",
                "end_date_cst": "2026-12-10",
                "time_cst": "03:00",
                "impact_tier": "P0",
                "monitor_window_min": 60,
            }
        ]
        # Exact HH:MM P0 event stays active even during overnight quiet hours (02:30 CST)
        self.assertTrue(rm.is_in_calendar_p0_window(exact_ev, _cst(2026, 12, 10, 2, 30)))

    def test_calendar_precision_windows_zero_and_next_event(self) -> None:
        exact = {
            "event_id": "known_time", "date_cst": "2026-12-10", "time_cst": "14:00",
            "date_precision": "exact", "impact_tier": "P0", "region": "CN",
        }
        now = _cst(2026, 12, 10, 13, 55)
        variants = (
            ({**exact, "monitor_window_min": 0}, False, False),
            ({**exact, "date_precision": "window_tbd"}, False, False),
            ({**exact, "date_precision": "window_tbd", "time_cst": "时间待定"}, False, False),
            ({**exact, "date_precision": "window_tbd", "time_cst": "全天"}, True, False),
            ({**exact, "date_precision": "window_tbd", "time_cst": "全天", "monitor_window_min": 0}, False, False),
            ({**exact, "monitor_window_min": 15}, True, True),
        )
        for event, high_frequency, countdown in variants:
            with self.subTest(event=event):
                self.assertEqual(rm.is_in_calendar_p0_window([event], now), high_frequency)
                self.assertEqual(bool(rm.detect_upcoming_calendar_alerts([event], now_cst=now)), countdown)
        later = {**exact, "event_id": "later", "time_cst": "15:00"}
        self.assertEqual(rm.find_next_calendar_event([exact, later], "CN", _cst(2026, 12, 10, 14, 5)), later)

    def test_gold_tier0_lock_covers_shfe_sge_xau_gc_without_false_matching_gc001(self) -> None:
        ssot = {"gold_locked": True, "gold_tier_code": "Tier 0", "gold_passed_gates": 2, "gold_total_gates": 4}
        for bad in (
            "建议逢低买入沪金主力合约",
            "建议立即加仓Au99.99现货",
            "建议顺势做多XAU现货黄金",
            "Recommend to buy GC futures on dip",
        ):
            with self.subTest(bad=bad):
                san = rm.enforce_safety_gates(bad, ssot, append_footer=False)
                self.assertNotEqual(san, bad)
                self.assertIn("严禁新买黄金", san)

        # Reverse repo GC001 MUST NOT false-match GC gold futures!
        ok_repo = "周四尾盘买入GC001国债逆回购锁定周末三天利息。"
        self.assertEqual(rm.enforce_safety_gates(ok_repo, ssot, append_footer=False), ok_repo)


if __name__ == "__main__":
    unittest.main()
