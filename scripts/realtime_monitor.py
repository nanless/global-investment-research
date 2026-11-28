#!/usr/bin/env python3
"""Zero-dependency real-time market, policy & geopolitical news monitor and interpreter.

Reads repository SSOT files (`gold/data_snapshot.json`, `equity/state/market_state.json`,
`equity/state/policy_calendar.json`, `equity/state/klines/core.json`) strictly READ-ONLY,
persists deduplication/cooldown/audit state solely under `.git/realtime-monitor.sqlite3`
(zero git working-tree pollution), enforces the Gold Tier-0 red-light mutex and PBOC
Doc No. 42 crypto compliance firewall on every outbound alert, and dispatches P0/P1
5-section prudent action memos via `scripts/wechat_notify.py`.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import dataclasses
import email.utils
import fcntl
import hashlib
import html
import json
import math
import os
import re
import sqlite3
import sys
import time
import traceback
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, time as wall_time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

if __package__:
    from .state_transaction import state_read_lock
else:
    from state_transaction import state_read_lock

REPO_ROOT = Path(__file__).resolve().parent.parent
CST = timezone(timedelta(hours=8))
NEW_YORK = ZoneInfo("America/New_York")
QUOTE_MAX_AGE = timedelta(minutes=30)
NEWS_MAX_AGE_SEC = 3 * 3600
_QUOTE_SOURCE_NAMES = {"sina": "新浪行情", "cnbc": "CNBC 行情"}
_ALL_DAY_TIMES = frozenset({"全天", "全天窗口"})

GOLD_SNAPSHOT_PATH = REPO_ROOT / "gold" / "data_snapshot.json"
MARKET_STATE_PATH = REPO_ROOT / "equity" / "state" / "market_state.json"
POLICY_CALENDAR_PATH = REPO_ROOT / "equity" / "state" / "policy_calendar.json"
KLINES_CORE_PATH = REPO_ROOT / "equity" / "state" / "klines" / "core.json"
MARKET_CALENDAR_PATH = REPO_ROOT / "gold" / "market_calendar.json"

DEFAULT_PORTAL_URL = "https://nanless.github.io/global-investment-research/"
USER_AGENT = "GlobalInvestmentResearch-Monitor/1.0 (https://github.com/nanless/global-investment-research)"

# Gold Tier-0 red-light active buy guard (aligned across linters & monitor; uses ASCII lookarounds so CJK+ASCII never bypasses)
_GOLD_ASSETS_PAT = (
    r"(?:黄金|金条|积存金|金矿|现货金|纸黄金|金仓|金饰|沪金|Au99\.99|Au\(T\+D\)|"
    r"518880|518850|518660|159937|159934|518800|517520|159562|"
    r"600547|601899|600489|600988|000975|02899|06181|01929|01818|01787|02099|"
    r"(?<![A-Za-z0-9])(?:XAU|GC|02840|03081|IGLN|GLDM|GLD|IAUM|IAU|GDXJ|GDX|NEM|AEM|gold|bullion)(?![A-Za-z0-9]))"
)
_GOLD_BUY_VERBS_CN = (
    r"(?:(?:立即|马上|抓紧|逢低|逢回调|分批|逐步|果断)\s*)?"
    r"(?:抄底|加仓|补仓|补齐|补足|新建|建仓|定投|买入|买进|增配|加配|低吸|布局|上车|入手|吸纳|配置|做多|抢筹|买金)"
)
_GOLD_ACTIVE_BUY_RE = re.compile(
    rf"{_GOLD_BUY_VERBS_CN}[^\n。；;！？!，,]{{0,14}}{_GOLD_ASSETS_PAT}"
    rf"|{_GOLD_ASSETS_PAT}[^\n。；;！？!，,]{{0,12}}(?:立即买|逢低买|抄底买|果断加仓|立刻补仓|开启定投|分批建仓|分批布局|低吸|布局良机|上车|买进|买入|加仓|做多)"
    rf"|(?<![A-Za-z0-9])(?:buy|add|accumulate|allocate|dca|go\s+long)(?![A-Za-z0-9])[^\n.;!?,]{{0,24}}(?<![A-Za-z0-9])(?:gold|xau|gc|gld|gldm|iau|iaum|gdx|gdxj|igln|bullion)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_GOLD_NEGATION_RE = re.compile(
    r"(?:严禁|禁止|不可|不要|勿|切勿|暂不|暂停|避免|绝不|切忌|不要急于|不得|不建议|无需|严防|切莫|"
    r"(?<![A-Za-z0-9])(?:do\s+not|don't|never|avoid|must\s+not|should\s+not|no\s+new)(?![A-Za-z0-9]))",
    re.IGNORECASE,
)
_CRYPTO_ASSETS_PAT = (
    r"(?:比特币|以太坊|虚拟货币|加密货币|数字货币|稳定币|微策略|"
    r"(?<![A-Za-z0-9])(?:BTC|ETH|USDT|USDC|SOL|Solana|DOGE|XRP|IBIT|FBTC|BITO|ETHA|MSTR|crypto|bitcoin|ethereum)(?![A-Za-z0-9]))"
)
_CRYPTO_BUY_RE = re.compile(
    rf"(?:(?:立即|马上|抓紧|逢低|逢回调|分批|逐步|果断)\s*)?"
    rf"(?:买入|买进|加仓|补仓|抄底|配置|增配|低吸|布局|上车|入手|吸纳|定投|做多|建仓|重仓)[^\n。；;！？!，,]{{0,14}}{_CRYPTO_ASSETS_PAT}"
    rf"|{_CRYPTO_ASSETS_PAT}[^\n。；;！？!，,]{{0,12}}(?:买入|买进|加仓|抄底|配置|增配|低吸|布局|上车|定投|做多|建仓)"
    rf"|(?<![A-Za-z0-9])(?:buy|accumulate|allocate|dca|go\s+long)(?![A-Za-z0-9])[^\n.;!?,]{{0,24}}(?<![A-Za-z0-9])(?:btc|eth|bitcoin|ethereum|crypto|sol|usdt|usdc|ibit|fbtc|mstr)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_CLAUSE_SPLIT_RE = re.compile(r"[。！？；，,、|;!?\n]|(?<!\d)\.(?!\d)")

# Policy Transmission Domains: A-Share Policy Core, HK Dual Satellite, US Policy+Macro, Gold/Rates
@dataclass(frozen=True)
class PolicyDomainRule:
    domain_id: str
    region: str          # CN | HK | US | GLOBAL
    label: str
    authority_default: int  # base S_auth if matched from official source
    keywords_pos: tuple[str, ...]
    keywords_neg: tuple[str, ...]
    primary_anchors: tuple[str, ...]
    transmission_chain: str
    guardrail: str


_FOREIGN_CB_NEG = (
    "欧洲央行", "日本央行", "英国央行", "澳洲联储", "澳大利亚央行", "新西兰联储", "加拿大央行",
    "瑞士央行", "瑞典央行", "韩国央行", "印度央行", "巴西央行", "土耳其央行", "俄罗斯央行",
    "南非央行", "赞比亚央行", "印尼央行", "墨西哥央行", "泰国央行", "马来西亚央行", "菲律宾央行",
    "波兰央行", "捷克央行", "匈牙利央行", "以色列央行", "埃及央行", "尼日利亚央行", "美联储", "FOMC",
    "ECB", "BOJ", "Bank of England", "RBA", "Federal Reserve",
)
_NON_US_MACRO_NEG = ("德国", "欧元区", "英国", "日本", "法国", "意大利", "西班牙", "澳大利亚", "加拿大", "中国", "韩国", "印度")

POLICY_DOMAINS: tuple[PolicyDomainRule, ...] = (
    PolicyDomainRule(
        domain_id="cn_top_meeting",
        region="CN",
        label="A股政策市 · 顶层定调",
        authority_default=40,
        keywords_pos=("政治局会议", "中央经济工作会议", "国务院常务会议", "国常会", "全国两会", "超常规逆周期", "适度宽松", "更加积极的财政", "一揽子增量政策", "发改委新闻发布会", "国家发改委增量政策", "金融监管总局稳市", "金融监管总局重磅", "险资入市", "长期资金入市"),
        keywords_neg=(),
        primary_anchors=("sh000001", "sh000300", "hf_CHA50CFD", "rt_hkHSTECH", "fx_susdcnh"),
        transmission_chain="A股顶层政策定调 → 富时A50/沪深300与中债10Y重定价 → 港股恒科与中资金融同步映射 → 铜/人民币情绪联动",
        guardrail="严分“会议通稿定调”与“财政细则落地”，警惕利好落地后高开兑现（防买预期卖事实）。",
    ),
    PolicyDomainRule(
        domain_id="cn_pboc",
        region="CN",
        label="A股政策市 · 央行货币与流动性",
        authority_default=40,
        keywords_pos=("央行降准", "央行降息", "全面降准", "定向降准", "下调存款准备金率", "存款准备金率", "下调政策利率", "LPR", "MLF", "买断式逆回购", "互换便利", "回购增持再贷款", "外汇风险准备金", "央行货币政策委员会", "货币政策执行报告", "央行流动性支持", "央行购债", "潘功胜", "PBOC cuts", "PBOC lowers", "PBOC injects", "PBOC RRR", "PBOC rate"),
        keywords_neg=_FOREIGN_CB_NEG,
        primary_anchors=("sh000001", "sh511260", "sh511090", "fx_susdcnh", "rt_hkHSI"),
        transmission_chain="若政策改变资金供求，先核对短期融资成本与中债利率，再看 A 股和港股是否同步反应。",
        guardrail="降准降息首日切忌追高30年期超长债与早盘暴拉题材股，先看量能与中债10Y是否二次确认。",
    ),
    PolicyDomainRule(
        domain_id="cn_macro_data",
        region="CN",
        label="A股基本面 · 中国官方宏观与信贷数据",
        authority_default=34,
        keywords_pos=("官方制造业PMI", "制造业采购经理指数", "规上工业企业利润", "规模以上工业企业利润", "社会融资规模", "新增人民币贷款", "中国CPI", "中国PPI", "中国GDP", "社会消费品零售总额", "规模以上工业增加值", "M1同比", "M2同比", "China CPI", "China PPI", "China GDP", "China PMI"),
        keywords_neg=("美国CPI", "美国PPI", "德国", "欧元区"),
        primary_anchors=("sh000001", "sh000300", "rt_hkHSI", "rt_hkHSTECH", "hf_HG"),
        transmission_chain="中国宏观景气/信贷预期差 → 修正A股盈利与政策宽松预期 → 联动港股顺周期/科技与铜价",
        guardrail="核对结构分项与基数效应，警惕单月数据冲高后的风格剧烈切换与追高回吐。",
    ),
    PolicyDomainRule(
        domain_id="cn_fiscal",
        region="CN",
        label="A股政策市 · 财政发债与化债刺激",
        authority_default=36,
        keywords_pos=("特别国债", "超长期特别国债", "地方债化债", "化债方案", "化债额度", "财政赤字率", "赤字率", "专项债额度", "新增专项债", "以旧换新", "消费补贴", "财政刺激", "增量财政", "积极财政政策", "更加积极的财政政策", "财政部发债", "财政部减税", "财政部降费", "财政部新闻发布会"),
        keywords_neg=("美国财政部", "英国财政部", "法国财政部", "德国财政部", "日本财务省", "美债拍卖", "U.S. Treasury"),
        primary_anchors=("sh000300", "sh511090", "rt_hkHSI", "hf_HG"),
        transmission_chain="财政发债扩张 → 顺周期/基建/消费预期抬升 + 超长国债供给承压（长债回调） → 港股顺周期与工业金属共振",
        guardrail="超长债（如30年国债ETF 511090）对供给冲击波动堪比股票，财政超预期时慎防长债回撤。",
    ),
    PolicyDomainRule(
        domain_id="cn_csrc",
        region="CN",
        label="A股政策市 · 证监会与资本市场监管",
        authority_default=38,
        keywords_pos=("吴清", "融券新规", "暂停转融券", "转融券", "融资保证金", "平准基金", "类平准基金", "国家队入市", "汇金增持", "中央汇金", "量化交易监管", "程序化交易", "退市新规", "分红新规", "证券交易印花税", "调降印花税", "下调印花税", "印花税调整", "深化资本市场改革", "稳市机制", "资本市场重磅", "证监会重磅"),
        keywords_neg=("香港证监会", "SFC", "期货和期权注册", "期货注册", "期权注册", "首次公开发行股票注册", "公开发行公司债券", "公开发行可转债", "警示函", "行政处罚决定书", "任职资格"),
        primary_anchors=("sh000001", "sz399006", "sh000688", "hf_CHA50CFD"),
        transmission_chain="交易制度/杠杆/汇金护盘变动 → 直接改变A股微盘与双创筹码供需 → 映射港股券商与中概风偏",
        guardrail="降保证金/制度利好易引发早盘脉冲与尾盘兑现，红灯期严守A股总仓上限且不加杠杆。",
    ),
    PolicyDomainRule(
        domain_id="cn_tariff",
        region="CN",
        label="中美经贸 · 关税与出口管制",
        authority_default=38,
        keywords_pos=("加征关税", "301关税", "232关税", "122条款", "Section 122", "Section 301", "Section 232", "IEEPA", "31 CFR Part 851", "对外投资规则", "出口管制", "实体清单", "Entity List", "商务部反制", "tariff", "tariffs", "export control", "export controls", "BIS export", "BIS Entity List", "BIS chip", "BIS rule", "Bureau of Industry and Security", "USTR", "chip ban", "semiconductor restrictions"),
        keywords_neg=("electricity tariff", "power tariff", "water tariff", "utility tariff", "bus tariff", "rail tariff", "telecom tariff", "roaming tariff", "Bank for International Settlements"),
        primary_anchors=("fx_susdcnh", "hf_CHA50CFD", "rt_hkHSTECH", "hf_NQ", "sh000688"),
        transmission_chain="关税/管制落地 → 离岸人民币(USD/CNH)与外贸/算力链重估 → 港股恒科/中概首当其冲 → 美股芯片与通胀预期联动",
        guardrail="严防单源外媒匿名放风误导，必核商务部/USTR/联邦公报原文及USD/CNH实盘反应。",
    ),
    PolicyDomainRule(
        domain_id="hk_southbound_tax",
        region="HK",
        label="港股双卫星 · 港股通与红利税政策",
        authority_default=35,
        keywords_pos=("港股通红利税", "港股红利税", "港股股息税", "港股红利所得税", "港股通扩容", "互联互通优化", "港股通纳入", "港交所改革", "港股通交易机制"),
        keywords_neg=(),
        primary_anchors=("rt_hkHSI", "rt_hkHSTECH", "sh000300"),
        transmission_chain="互联互通/红利税催化 → 港股高息央国企与AH深度折价股重估 → 港交所成交放量",
        guardrail="港股通红利税减免在财政部/税务总局/证监会未发正式公告前，一律按待核实传闻处理，绝不提前追高。",
    ),
    PolicyDomainRule(
        domain_id="hk_peg_hkma",
        region="HK",
        label="港股双卫星 · 联汇7.85与金管局流动性",
        authority_default=38,
        keywords_pos=("弱方兑换保证", "强方兑换保证", "银行体系总结余", "1个月HIBOR", "港元拆息", "联系汇率", "联汇7.85", "触及7.85", "金管局入市", "金管局承接港元", "金管局加息", "金管局降息", "HKMA intervenes", "HKMA intervention", "HKMA aggregate balance", "HKMA base rate", "HKMA buys HKD", "HKMA sells HKD", "weak-side convertibility", "strong-side convertibility", "Hong Kong dollar peg"),
        keywords_neg=(),
        primary_anchors=("rt_hkHSI", "rt_hkHSTECH", "fx_susdcnh"),
        transmission_chain="若触及弱方兑换保证，关注银行体系总结余能否下降与港元拆息是否上行。强方操作方向相反。",
        guardrail="总结余逼近或跌破400亿港元属跨市场熔断红线，触发时严控港股离岸与港股通仓位。",
    ),
    PolicyDomainRule(
        domain_id="us_fed_fomc",
        region="US",
        label="美股政策 · 美联储FOMC与利率预期",
        authority_default=40,
        keywords_pos=("美联储", "FOMC", "鲍威尔", "Jerome Powell", "Chair Powell", "Fed Chair Powell", "沃什", "Warsh", "联储点阵图", "美联储降息", "美联储加息", "美联储缩表", "Federal Reserve issues FOMC", "Federal Reserve FOMC", "Federal Reserve cuts", "Federal Reserve hikes", "Federal Reserve raises", "Federal Reserve lowers", "Federal Reserve holds", "Federal Reserve rate", "Federal Reserve emergency", "Fed rate", "Fed rates", "Fed chair", "Fed cuts", "Fed hikes", "Fed raises", "Fed pauses", "Fed holds", "Fed balance sheet", "Fed dot plot", "Fed minutes"),
        keywords_neg=("中国人民银行", "中国央行", "欧洲央行", "ECB", "日本央行", "BOJ", "英国央行", "Bank of England", "澳洲联储", "赞比亚央行"),
        primary_anchors=("US10Y", "US2Y", "hf_ES", "hf_NQ", "DINIW", "hf_XAU"),
        transmission_chain="联储鹰鸽定调 → 美债2Y/10Y与实际利率重定价 → 美股纳指/标普估值 + 港股美元流动性 + 黄金利率压制",
        guardrail="决议声明与30分钟后主席发布会常现双向洗盘，严禁赌单边消息与亚盘薄量抢跑。",
    ),
    PolicyDomainRule(
        domain_id="us_macro_data",
        region="US",
        label="美股宏微 · 美国通胀与就业数据",
        authority_default=33,
        keywords_pos=("美国CPI", "美国核心CPI", "美国PCE", "美国核心PCE", "美国非农", "非农就业", "美国失业率", "美国初请", "美国ISM", "美国GDP", "US CPI", "U.S. CPI", "U.S. Core CPI", "Core CPI", "US PCE", "U.S. PCE", "U.S. Core PCE", "US GDP", "U.S. GDP", "US jobs", "U.S. jobs", "US payrolls", "U.S. payrolls", "U.S. inflation", "US ISM", "Nonfarm Payrolls", "Core PCE", "Initial Jobless", "U.S. unemployment"),
        keywords_neg=_NON_US_MACRO_NEG,
        primary_anchors=("US10Y", "US2Y", "hf_ES", "hf_NQ", "DINIW", "hf_XAU"),
        transmission_chain="美通胀/就业预期差 → 修正联储利率路径 → 美债收益率与美元剧震 → 传导至港股科技与黄金",
        guardrail="核对核心分项与前值修正，警惕“坏消息当好消息”或“滞胀双杀”两种截然相反的定价模式。",
    ),
    PolicyDomainRule(
        domain_id="us_treasury_qra",
        region="US",
        label="美股政策 · 美债发债QRA与财政流动性",
        authority_default=35,
        keywords_pos=("美国财政部", "美债发债计划", "季度再融资", "QRA", "美债拍卖", "拍卖尾部", "美国债务上限", "美国政府停摆", "临时拨款法案", "Treasury refunding", "Treasury auction", "Treasury General Account", "TGA balance", "TGA rebuild", "TGA cash", "TGA drawdown", "debt ceiling", "government shutdown"),
        keywords_neg=(),
        primary_anchors=("US10Y", "US30Y", "hf_ES", "b_VIX"),
        transmission_chain="美债供给/TGA抽水 → 长端美债收益率跳升（盯5.25%熔断线） → 挤压全球风险资产估值",
        guardrail="长端美债突破关键阻力位时，优先守超短美元盾（SGOV/IB01）并严控高久期美债与科技仓。",
    ),
    PolicyDomainRule(
        domain_id="us_geopolitics_oil",
        region="GLOBAL",
        label="全球地缘与能源 · 原油供给冲击",
        authority_default=36,
        keywords_pos=("OPEC+", "OPEC", "欧佩克", "霍尔木兹", "炼厂遇袭", "油田遇袭", "中东冲突升级", "油价暴涨", "原油减产", "原油增产", "产油国联盟", "Hormuz", "Strait of Hormuz", "refinery attack", "refinery attacks", "sanctions on oil", "oil sanctions"),
        keywords_neg=(),
        primary_anchors=("hf_OIL", "US10Y", "hf_XAU", "hf_ES", "b_VIX"),
        transmission_chain="原油供给冲击 → 再通胀预期推高美债10Y → 压制股市估值并收紧联储空间 → 黄金受避险与实际利率博弈",
        guardrail="若油价冲高，核对供应中断和通胀预期。注意原油与白银基金场内溢价，退市提案需等正式规则及单基金公告。",
    ),
    PolicyDomainRule(
        domain_id="global_cb_carry",
        region="GLOBAL",
        label="全球央行 · 日欧利率与套息交易",
        authority_default=35,
        keywords_pos=("日本央行加息", "日本央行降息", "日本央行决议", "日本央行按兵不动", "日本央行干预", "日本央行行长", "日本央行利率", "日本央行缩表", "植田和男", "日元干预", "日本财务省干预", "欧洲央行加息", "欧洲央行降息", "欧洲央行决议", "欧洲央行按兵不动", "欧洲央行利率", "拉加德", "英国央行加息", "英国央行降息", "英国央行决议", "英国央行按兵不动", "英国央行利率", "BOJ rate", "BOJ hike", "BOJ cut", "BOJ decision", "BOJ policy", "BOJ monetary", "BOJ Governor", "Kazuo Ueda", "Bank of Japan rate", "Bank of Japan policy", "Bank of Japan monetary", "Bank of Japan hike", "Bank of Japan cut", "Bank of Japan decision", "ECB rate", "ECB hike", "ECB cut", "ECB hold", "ECB decision", "ECB monetary policy", "ECB Governing Council", "ECB policy", "Lagarde", "European Central Bank rate", "European Central Bank cuts", "European Central Bank hikes", "European Central Bank policy", "Bank of England rate", "Bank of England cuts", "Bank of England hikes", "Bank of England holds", "Bank of England MPC", "Bank of England monetary", "Bank of England decision", "BOE rate", "BOE MPC", "BOE cut", "BOE hike", "套息交易", "日元套息", "carry trade"),
        keywords_neg=(),
        primary_anchors=("fx_susdjpy", "US10Y", "hf_NQ", "rt_hkHSI"),
        transmission_chain="日央行加息/干预 → USD/JPY急跌触发日元套息平仓 → 全球高估值科技股与港美同步去杠杆",
        guardrail="USD/JPY 3日急跌>3%属全球危机熔断阀，触发时所有权益新增暂停并降险。",
    ),
    PolicyDomainRule(
        domain_id="crisis_breaker",
        region="GLOBAL",
        label="跨市场危机 · 3+1总熔断与信用冲击",
        authority_default=40,
        keywords_pos=("触发熔断", "市场熔断", "流动性危机", "私募信贷赎回", "高收益债违约", "信用利差飙升", "主权评级下调", "标普负面观察", "QDII停牌", "基金强制退市"),
        keywords_neg=("*ST", "ST股", "面值退市", "退市整理期"),
        primary_anchors=("b_VIX", "US10Y", "fx_susdjpy", "hf_XAU", "hf_ES"),
        transmission_chain="波动率/信用/流动性总阀警报 → 跨资产相关性跃升 → 全市场现金与短久期国债为王",
        guardrail="3+1 危机熔断阀任一触发立即切入防守，严守红灯上限、不抄飞刀、不碰高溢价跨境基金。",
    ),
)

_OFFICIAL_SOURCE_TIERS: dict[str, tuple[int, bool]] = {
    # source_key -> (authority_bonus_cap, is_official_primary)
    "gov_yaowen": (40, True),
    "gov_zhengce": (40, True),
    "csrc_json": (40, True),
    "pbc_omo": (40, True),
    "pbc_news": (40, True),
    "mof_news": (38, True),
    "hkma_rss": (40, True),
    "hkex_rss": (36, True),
    "sfc_rss": (36, True),
    "fed_press": (40, True),
    "fed_monetary": (40, True),
    "sec_rss": (35, True),
    "whitehouse_rss": (40, True),
    "ecb_rss": (36, True),
    "boj_rss": (38, True),
    "boe_rss": (34, True),
    # Tier-2 financial wires (require >=2 independent sources OR official quote for K_verify=1.0)
    "sina_724": (34, False),
    "wscn_global": (34, False),
    "wscn_ashare": (34, False),
    "wscn_us": (34, False),
    "wscn_hk": (34, False),
    "em_top": (36, False),
    "em_724": (34, False),
    "ths_724": (32, False),
    "jin10_flash": (34, False),
    "cnbc_econ": (34, False),
    "cnbc_pol": (34, False),
    "wsj_markets": (34, False),
    "ft_markets": (34, False),
}

_OFFICIAL_ENTITY_IN_TEXT_RE = re.compile(
    r"(?:新华社|央视新闻|人民日报|国务院|政治局|中国人民银行|央行公告|财政部|证监会|国家统计局|国家发改委|商务部|金融监管总局|香港金管局|港交所|美联储|白宫|美国财政部|"
    r"\b(?:FOMC|SEC|ECB|BOJ|BOE|OPEC\+|HKMA|Federal Reserve|White House|U\.S\. Treasury)\b)",
    re.IGNORECASE,
)
_RUMOR_CUE_RE = re.compile(
    r"(?:传闻|据称|据悉|据了解|据透露|有消息称|市场消息|外媒称|彭博引述|路透引述|或将|正考虑|知情人士|消息人士|市场猜测|小作文|未经证实|网传|"
    r"\b(?:rumor|sources say|reportedly|unconfirmed|unverified|people familiar|according to people|said to be|weighing|mulling|speculation)\b)",
    re.IGNORECASE,
)
_EXPLICIT_RUMOR_HARD_RE = re.compile(r"(?:小作文|网传|未经证实|传闻|\brumor\b|\bunconfirmed\b|\bunverified\b)", re.IGNORECASE)
_ROUTINE_NOISE_RE = re.compile(
    r"(?:会见|访问|出席[^\n。；]{0,20}(?:开幕式|闭幕式|峰会|论坛|招待会)|致贺信|致贺电|慰问电|数字身份|"
    r"编造传播[^\n。；]{0,20}误导性信息|警示函|行政处罚|立案调查|纪律处分|任职资格核准|"
    r"纪念币|普通纪念币|纪念钞|汽柴油|成品油价格|生猪价格|彩票公益金|会计准则解释|"
    r"向特定对象发行|境外发行上市备案|公开募集基础设施|仿冒网站|钓鱼网站|金融消费者权益保护|"
    r"(?<![A-Za-z0-9])(?:enforcement\s+action|fraudulent\s+website|phishing|bogus\s+sms|working\s+paper|"
    r"speech\s+calendar|application\s+approval|bank\s+merger\s+approval|opinion:|op-ed|podcast|newsletter)(?![A-Za-z0-9]))",
    re.IGNORECASE,
)
_HARD_CATALYST_OVERRIDE_RE = re.compile(
    r"(?:降准|降息|特别国债|超长期特别国债|平准基金|融资保证金|印花税|加征关税|301关税|232关税|122条款|"
    r"出口管制|实体清单|31 CFR Part 851|互换便利|回购增持再贷款|买断式逆回购|赤字率|化债方案|弱方兑换保证|联系汇率|"
    r"(?<![A-Za-z0-9])(?:LPR|MLF|FOMC|QRA|Section 122|IEEPA|tariffs?|export controls?|rate cut|rate hike)(?![A-Za-z0-9]))",
    re.IGNORECASE,
)
_HK_TAX_TOPIC_RE = re.compile(r"(?:港股通红利税|港股红利税|港股股息税|港股红利所得税)")
_HK_TAX_ENACTED_RE = re.compile(r"(?:正式发布|正式宣布|正式实施|正式落地|印发|联合公告|财政部公告\s*第|税务总局公告\s*第)")
_POSITIVE_CUE_RE = re.compile(
    r"(?:降准|降息|净投放|刺激|增持|放宽|下调保证金|减免|利好|超预期增长|缓和|停火|鸽派|\b(?:dovish|cut rates|stimulus|easing|rally)\b)",
    re.IGNORECASE,
)
_NEGATIVE_CUE_RE = re.compile(
    r"(?:加息|收紧|加征关税|制裁|出口管制|遇袭|暴跌|违约|破净|抽水|鹰派|停牌|退市|\b(?:hawkish|tariff|sanction|attack|default|downgrade|plunge)\b)",
    re.IGNORECASE,
)

# Default FULL-DAY (1-day) volatility baselines (% or bp for yields) matching full-day change_pct / change_bp
_DEFAULT_SIGMA_1D: dict[str, float] = {
    "sh000001": 1.25,
    "sh000300": 1.35,
    "sz399006": 2.00,
    "sh000688": 2.35,
    "sh511260": 0.28,
    "sh511090": 0.75,
    "rt_hkHSI": 1.50,
    "rt_hkHSTECH": 2.40,
    "hf_CHA50CFD": 1.40,
    "hf_ES": 1.20,
    "hf_NQ": 1.65,
    "gb_inx": 1.20,
    "gb_ixic": 1.65,
    "hf_XAU": 1.35,
    "hf_GC": 1.35,
    "hf_OIL": 2.40,
    "hf_HG": 1.75,
    "fx_susdcnh": 0.30,
    "fx_susdjpy": 0.70,
    "DINIW": 0.50,
    "b_VIX": 9.50,
    "US10Y": 7.5,  # full-day bp std
    "US2Y": 7.5,   # full-day bp std
    "US30Y": 7.5,  # full-day bp std
}
_DEFAULT_SIGMA_15M = _DEFAULT_SIGMA_1D  # backward-compatible alias

_ANCHOR_TO_KLINE_ID: dict[str, str] = {
    "sh000001": "idx_sh000001",
    "sh000300": "idx_sh000300",
    "sz399006": "idx_sz399006",
    "sh000688": "idx_sh000688",
    "rt_hkHSI": "idx_hkHSI",
    "rt_hkHSTECH": "idx_hkHSTECH",
    "hf_ES": "idx_SPX",
    "hf_NQ": "idx_NDX",
    "hf_XAU": "cmd_XAU",
    "hf_GC": "cmd_GC",
    "hf_OIL": "cmd_OIL",
    "hf_HG": "cmd_HG",
    "fx_susdcnh": "fx_USDCNH",
    "fx_susdjpy": "fx_USDJPY",
    "DINIW": "fx_DXY",
    "b_VIX": "idx_VIX",
    "US10Y": "rate_US10Y",
    "US2Y": "rate_US2Y",
    "US30Y": "rate_US30Y",
}


@dataclass
class NewsItem:
    source: str
    title: str
    body: str
    published_ts: float
    url: str = ""
    importance_flag: int = 0  # 0 normal, 1 highlighted/red
    is_official: bool = False
    date_only: bool = False


def _news_item_hash(item: NewsItem) -> str:
    return hashlib.sha256(f"{item.source}:{item.title}".encode("utf-8")).hexdigest()[:24]


def _news_source_family(source: str) -> str:
    return source.partition("_")[0] if source.startswith(("wscn_", "em_", "cnbc_")) else source


@dataclass
class QuoteTick:
    symbol: str
    name: str
    last: float
    prev_close: float
    change_pct: float
    change_bp: float | None = None  # populated for yields (US10Y/US2Y/US30Y)
    timestamp: str = ""
    is_yield: bool = False
    source: str = ""


@dataclass
class ScoredSignal:
    signal_id: str
    cluster_key: str
    domain_id: str
    region: str
    domain_label: str
    title: str
    body: str
    sources: list[str]
    source_urls: list[str]
    published_cst: str
    score: int
    severity: str       # P0 | P1 | P2 | SILENT
    s_auth: int
    s_confirm: int
    s_spillover: int
    k_verify: float
    is_official: bool
    is_rumor_capped: bool
    is_flash_unverified: bool
    is_divergence: bool
    is_market_closed_floor: bool
    max_z: float
    anchor_snapshots: list[dict[str, Any]]
    transmission_chain: str
    guardrail: str
    escalation_tag: str = ""
    memo_md: str = ""
    interpreter_tier: str = "tier1_deterministic"
    item_hashes: list[str] = field(default_factory=list)
    is_market_first: bool = False


def _http_get_bytes(
    url: str, *, headers: dict[str, str] | None = None, timeout: int = 10, max_bytes: int = 5_000_000
) -> bytes:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(max_bytes)


def _strip_html(raw: str) -> str:
    txt = html.unescape(re.sub(r"<[^>]+>", " ", str(raw or "")))
    return re.sub(r"\s+", " ", txt).strip()


def _parse_pubdate_ts(raw: str) -> float | None:
    s = str(raw or "").strip()
    if not s:
        return None
    # 1. ISO-8601 (e.g. 2026-10-01T14:00:00Z, +09:00, -04:00)
    try:
        iso_cand = s.replace("Z", "+00:00")
        if "T" in iso_cand or re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", iso_cand):
            dt = datetime.fromisoformat(iso_cand)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CST)
            return dt.timestamp()
    except (ValueError, OverflowError, OSError):
        pass
    # 2. RFC-2822 / HTTP-date
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    # 3. Common CN slash / dash dates
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=CST)
            return dt.timestamp()
        except (ValueError, OverflowError, OSError):
            continue
    return None


_DATE_ONLY_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")


def _is_date_only_str(raw: str) -> bool:
    return bool(_DATE_ONLY_RE.fullmatch(str(raw or "").strip()))


def _news_epoch(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        ts = float(value)
        return ts if ts > 0 and math.isfinite(ts) else None
    except (TypeError, ValueError, OverflowError):
        return None


def parse_rss_xml(raw_bytes: bytes, source: str, *, is_official: bool) -> list[NewsItem]:
    atom = "{http://www.w3.org/2005/Atom}"
    rdf = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"
    rss1 = "{http://purl.org/rss/1.0/}"
    dc_date = "{http://purl.org/dc/elements/1.1/}date"
    try:
        root = ET.fromstring(raw_bytes)
    except ET.ParseError as exc:
        raise ValueError("RSS/Atom response could not be parsed") from exc
    if root.tag == f"{atom}feed":
        entries = root.findall(f"{atom}entry")
        prefix, description, date_tags = atom, "summary", (f"{atom}published", f"{atom}updated")
    elif root.tag == "rss" and root.find("channel") is not None:
        entries = root.findall("channel/item")
        prefix, description, date_tags = "", "description", ("pubDate", dc_date)
    elif root.tag == rdf and root.find(f"{rss1}channel") is not None:
        entries = root.findall(f"{rss1}item")
        prefix, description, date_tags = rss1, "description", (dc_date,)
    else:
        raise ValueError("Expected an RSS/Atom feed document")

    items: list[NewsItem] = []
    titled = 0
    for entry in entries[:20]:
        title = _strip_html(entry.findtext(f"{prefix}title") or "")
        if not title:
            continue
        titled += 1
        published = next((raw.strip() for tag in date_tags if (raw := entry.findtext(tag)) and raw.strip()), "")
        ts = _parse_pubdate_ts(published)
        if ts is None:
            continue
        body = _strip_html(entry.findtext(f"{prefix}{description}") or "")
        if prefix == atom:
            link = next((link.get("href", "") for link in entry.findall(f"{atom}link")
                         if link.get("rel", "alternate") == "alternate"), "")
        else:
            link = entry.findtext(f"{prefix}link") or ""
        items.append(NewsItem(source, title, body[:500], ts, link.strip(), 0, is_official,
                              date_only=_is_date_only_str(published)))
    if titled and not items:
        raise ValueError("RSS/Atom entries have no valid publication dates")
    return items


def parse_sina_724(raw_bytes: bytes, now_ts: float) -> list[NewsItem]:
    data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
    rows = (((data.get("result") or {}).get("data") or {}).get("feed") or {}).get("list") or []
    out: list[NewsItem] = []
    for r in rows[:25]:
        if not isinstance(r, dict):
            continue
        text = _strip_html(r.get("rich_text") or "")
        if not text:
            continue
        ts = _parse_pubdate_ts(r.get("create_time") or "")
        if ts is None:
            continue
        imp = 1 if (r.get("is_focus") or int(r.get("top_value") or 0) > 0) else 0
        out.append(NewsItem("sina_724", text[:90], text[:500], ts, str(r.get("docurl") or ""), imp, False))
    return out


def parse_wscn_lives(raw_bytes: bytes, source: str, now_ts: float) -> list[NewsItem]:
    data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
    rows = (data.get("data") or {}).get("items") or []
    out: list[NewsItem] = []
    for r in rows[:20]:
        if not isinstance(r, dict):
            continue
        text = _strip_html(r.get("content_text") or r.get("title") or "")
        if not text:
            continue
        ts = _news_epoch(r.get("display_time"))
        if ts is None:
            continue
        score = int(r.get("score") or 1)
        out.append(NewsItem(source, text[:90], text[:500], ts, str(r.get("uri") or ""), 1 if score >= 2 else 0, False))
    return out


def parse_eastmoney_fastnews(raw_bytes: bytes, source: str, now_ts: float) -> list[NewsItem]:
    data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
    rows = (data.get("data") or {}).get("fastNewsList") or []
    out: list[NewsItem] = []
    for r in rows[:20]:
        if not isinstance(r, dict):
            continue
        title = _strip_html(r.get("title") or "")
        body = _strip_html(r.get("summary") or title)
        if not title:
            continue
        ts = _parse_pubdate_ts(r.get("showTime") or "")
        if ts is None:
            continue
        imp = 1 if str(r.get("titleColor") or "0") == "3" else 0
        code = str(r.get("code") or "")
        url = f"https://finance.eastmoney.com/a/{code}.html" if code else ""
        out.append(NewsItem(source, title, body[:500], ts, url, imp, False))
    return out


def parse_ths_724(raw_bytes: bytes, now_ts: float) -> list[NewsItem]:
    data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
    rows = (data.get("data") or {}).get("list") or []
    out: list[NewsItem] = []
    for r in rows[:20]:
        if not isinstance(r, dict):
            continue
        title = _strip_html(r.get("title") or "")
        body = _strip_html(r.get("digest") or title)
        if not title:
            continue
        ts = _news_epoch(r.get("ctime"))
        if ts is None:
            continue
        imp = 1 if str(r.get("import") or "") == "3" else 0
        out.append(NewsItem("ths_724", title, body[:500], ts, str(r.get("url") or ""), imp, False))
    return out


def parse_jin10_flash(raw_bytes: bytes, now_ts: float) -> list[NewsItem]:
    data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
    rows = data.get("data") or []
    out: list[NewsItem] = []
    for r in rows[:20]:
        if not isinstance(r, dict):
            continue
        inner = r.get("data") if isinstance(r.get("data"), dict) else {}
        if inner.get("lock"):
            continue
        text = _strip_html(inner.get("content") or "")
        if not text:
            continue
        ts = _parse_pubdate_ts(r.get("time") or "")
        if ts is None:
            continue
        imp = 1 if int(r.get("important") or 0) >= 1 else 0
        out.append(NewsItem("jin10_flash", text[:90], text[:500], ts, "https://www.jin10.com/", imp, False))
    return out


def parse_gov_cn_json(raw_bytes: bytes, source: str, now_ts: float) -> list[NewsItem]:
    rows = json.loads(raw_bytes.decode("utf-8", errors="replace"))
    if not isinstance(rows, list):
        return []
    out: list[NewsItem] = []
    for r in rows[:15]:
        if not isinstance(r, dict):
            continue
        title = _strip_html(r.get("TITLE") or r.get("title") or "")
        if not title:
            continue
        pub_raw = str(r.get("DOCRELPUBTIME") or r.get("pubDate") or "").strip()
        date_only = _is_date_only_str(pub_raw)
        ts = _parse_pubdate_ts(pub_raw)
        if ts is None:
            continue
        url = str(r.get("URL") or r.get("link") or "").strip()
        if url.startswith("/"):
            url = f"https://www.gov.cn{url}"
        out.append(NewsItem(source, title, title, ts, url, 1, True, date_only=date_only))
    return out


def parse_csrc_json(raw_bytes: bytes, now_ts: float) -> list[NewsItem]:
    data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
    rows = (data.get("data") or {}).get("results") or []
    out: list[NewsItem] = []
    for r in rows[:12]:
        if not isinstance(r, dict):
            continue
        title = _strip_html(r.get("title") or "")
        if not title:
            continue
        pub_raw = str(r.get("publishedTimeStr") or "").strip()
        date_only = _is_date_only_str(pub_raw)
        ts = _parse_pubdate_ts(pub_raw)
        if ts is None:
            continue
        url = str(r.get("url") or "").strip()
        if url.startswith("//"):
            url = f"https:{url}"
        out.append(NewsItem("csrc_json", title, title, ts, url, 1, True, date_only=date_only))
    return out


def parse_sina_batch_quotes(raw_bytes: bytes) -> dict[str, QuoteTick]:
    """Parse Sina hq.sinajs.cn multi-asset live quote lines."""
    text = raw_bytes.decode("gbk", errors="replace")
    ticks: dict[str, QuoteTick] = {}
    for line in text.splitlines():
        m = re.match(r'^var hq_str_([^=]+)="([^"]*)";', line.strip())
        if not m:
            continue
        sym, body = m.group(1), m.group(2)
        if not body:
            continue
        parts = body.split(",")
        try:
            if sym.startswith(("sh", "sz", "bj")) and len(parts) >= 32:
                name, prev, last = parts[0], float(parts[2]), float(parts[3])
                if prev > 0 and last > 0:
                    ticks[sym] = QuoteTick(sym, name, last, prev, round((last - prev) / prev * 100.0, 2), timestamp=f"{parts[30]} {parts[31]}")
            elif sym.startswith("rt_hk") and len(parts) >= 19:
                name, prev, last, pct = parts[1], float(parts[3]), float(parts[6]), float(parts[8])
                if last > 0:
                    ticks[sym] = QuoteTick(sym, name, last, prev, round(pct, 2), timestamp=f"{parts[17]} {parts[18]}")
            elif sym.startswith("gb_") and len(parts) >= 5:
                name, last, pct = parts[0], float(parts[1]), float(parts[2])
                prev = last / (1.0 + pct / 100.0) if (1.0 + pct / 100.0) != 0 else last
                if last > 0:
                    ticks[sym] = QuoteTick(sym, name, last, prev, round(pct, 2), timestamp=parts[3])
            elif sym == "b_VIX" and len(parts) >= 10:
                name, last, pct, prev = parts[0], float(parts[1]), float(parts[3]), float(parts[9])
                if last > 0:
                    ticks[sym] = QuoteTick(sym, name, last, prev, round(pct, 2), timestamp=f"{parts[6]} {parts[7]}")
            elif sym.startswith("hf_") and len(parts) >= 14:
                last, prev, name = float(parts[0]), float(parts[7]), parts[13]
                if prev > 0 and last > 0:
                    ticks[sym] = QuoteTick(sym, name, last, prev, round((last - prev) / prev * 100.0, 2), timestamp=f"{parts[12]} {parts[6]}")
            elif (sym.startswith("fx_") or sym == "DINIW") and len(parts) >= 10:
                last, prev, name = float(parts[1]), float(parts[3]), parts[9]
                if prev > 0 and last > 0:
                    timestamp = parts[0]
                    if len(parts) >= 18 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[17]):
                        timestamp = f"{parts[17]} {timestamp}"
                    ticks[sym] = QuoteTick(sym, name, last, prev, round((last - prev) / prev * 100.0, 2), timestamp=timestamp)
        except (ValueError, ZeroDivisionError):
            continue
    for tick in ticks.values():
        tick.source = "sina"
    return ticks


def parse_cnbc_batch_quotes(raw_bytes: bytes) -> dict[str, QuoteTick]:
    """Parse CNBC REST quote JSON for live US2Y/US10Y/US30Y yields and VIX/DXY."""
    data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
    raw_list = (data.get("FormattedQuoteResult") or {}).get("FormattedQuote") or []
    if isinstance(raw_list, dict):
        raw_list = [raw_list]
    ticks: dict[str, QuoteTick] = {}
    for row in raw_list:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "").strip()
        last_s = str(row.get("last") or "").replace("%", "").replace(",", "").strip()
        prev_s = str(row.get("previous_day_closing") or "").replace("%", "").replace(",", "").strip()
        try:
            last = float(last_s)
            prev = float(prev_s) if prev_s else last
        except ValueError:
            continue
        if sym in ("US2Y", "US10Y", "US30Y"):
            bp = round((last - prev) * 100.0, 1)
            pct = round((last - prev) / prev * 100.0, 2) if prev else 0.0
            ticks[sym] = QuoteTick(sym, sym, last, prev, pct, change_bp=bp, timestamp=str(row.get("last_time") or ""), is_yield=True)
        elif sym == ".VIX" and last > 0:
            pct = round((last - prev) / prev * 100.0, 2) if prev else 0.0
            ticks["b_VIX"] = QuoteTick("b_VIX", "VIX", last, prev, pct, timestamp=str(row.get("last_time") or ""))
    for tick in ticks.values():
        tick.source = "cnbc"
    return ticks


def load_vol_baselines(
    klines_core_path: Path = KLINES_CORE_PATH, *, expected_edition: str | None = None,
) -> dict[str, float]:
    """Derive 1-day realized volatility sigma_1d from 20d closes in core.json (read-only), matching full-day change_pct/change_bp."""
    baselines = dict(_DEFAULT_SIGMA_1D)
    core = _read_json_readonly(klines_core_path)
    series = core.get("series")
    if expected_edition is not None and (core.get("edition_id") != expected_edition or not isinstance(series, dict)):
        raise ValueError("Isolated monitor K-line data must match the selected snapshot edition")
    if not isinstance(series, dict):
        return baselines
    for anchor, kid in _ANCHOR_TO_KLINE_ID.items():
        s_obj = series.get(kid)
        bars = s_obj.get("bars") if isinstance(s_obj, dict) else None
        if not isinstance(bars, list) or len(bars) < 10:
            continue
        closes = [float(b[4]) for b in bars[-21:] if isinstance(b, list) and len(b) >= 5 and isinstance(b[4], (int, float))]
        if len(closes) < 8:
            continue
        if anchor in ("US10Y", "US2Y", "US30Y"):
            diffs = [(closes[i] - closes[i - 1]) * 100.0 for i in range(1, len(closes))]
            mean = sum(diffs) / len(diffs)
            var = sum((x - mean) ** 2 for x in diffs) / max(1, len(diffs) - 1)
            s1d = max(5.0, math.sqrt(var))
            baselines[anchor] = round(s1d, 2)
        else:
            rets = [(closes[i] - closes[i - 1]) / closes[i - 1] * 100.0 for i in range(1, len(closes)) if closes[i - 1] > 0]
            if len(rets) < 6:
                continue
            mean = sum(rets) / len(rets)
            var = sum((x - mean) ** 2 for x in rets) / max(1, len(rets) - 1)
            floor = 0.25 if anchor in ("fx_susdcnh", "sh511260") else (0.45 if anchor in ("DINIW", "fx_susdjpy") else 0.75)
            s1d = max(floor, math.sqrt(var))
            baselines[anchor] = round(s1d, 3)
    return baselines


# ---------------------------------------------------------------------------
# Part 2: Live Pollers, SSOT Reader, 0-100 Scorer, SQLite Cooldown,
#         Two-Tier Interpreter, Safety Gates, LaunchAgent & CLI
# ---------------------------------------------------------------------------

def _resolve_git_dir() -> Path:
    """Resolve real .git directory cleanly in both normal repos and git worktrees."""
    dot_git = REPO_ROOT / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        txt = dot_git.read_text(encoding="utf-8", errors="replace").strip()
        if txt.lower().startswith("gitdir:"):
            raw = txt.split(":", 1)[1].strip()
            p = Path(raw)
            return p if p.is_absolute() else (REPO_ROOT / p).resolve()
    return dot_git


def _reject_repo_worktree_write(path: Path, label: str) -> None:
    """Refuse writes anywhere inside REPO_ROOT working tree (only .git/ or outside REPO_ROOT allowed)."""
    resolved = path.resolve()
    repo_res = REPO_ROOT.resolve()
    git_dir = _resolve_git_dir().resolve()
    if resolved.is_relative_to(repo_res) and not resolved.is_relative_to(git_dir):
        raise ValueError(
            f"Refusing to write {label} inside repository working tree (zero git pollution rule): {resolved}"
        )


def parse_html_anchors(raw_bytes: bytes, source: str, base_url: str, now_ts: float) -> list[NewsItem]:
    """Extract dated notices from one government list entry or table row at a time."""
    text = raw_bytes.decode("utf-8", errors="replace")
    row_pattern = re.compile(r"<(li|tr)\b[^>]*>((?:(?!<(?:li|tr)\b).)*?)</\1\s*>", re.I | re.S)
    anchor_pattern = re.compile(r'''<a\s+[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a>''', re.I | re.S)
    date_pattern = re.compile(r"(?<!\d)20\d{2}[-/]\d{1,2}[-/]\d{1,2}(?!\d)")
    out: list[NewsItem] = []
    seen: set[str] = set()
    has_dated_entries = False
    for row in row_pattern.finditer(text):
        anchors = list(anchor_pattern.finditer(row[2]))
        dates = set(date_pattern.findall(_strip_html(anchor_pattern.sub("", row[2]))))
        if len(anchors) != 1 or len(dates) != 1:
            continue
        ts = _parse_pubdate_ts(dates.pop().replace("/", "-"))
        if ts is None:
            continue
        has_dated_entries = True
        href, label = anchors[0].group(1, 2)
        title = _strip_html(label)
        if len(title) < 8 or title in seen:
            continue
        if not any(k in title for k in ("央行", "货币", "逆回购", "利率", "财政", "国债", "关税", "税", "金融", "政策", "债券", "公告", "通知", "会议")):
            continue
        url = urljoin(base_url, html.unescape(href.strip()))
        try:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".gov.cn") or parsed.username:
                continue
        except ValueError:
            continue
        seen.add(title)
        out.append(NewsItem(source, title[:120], title[:500], ts, url, 1, True, date_only=True))
        if len(out) >= 12:
            break
    if not has_dated_entries:
        raise ValueError("Government index contains no identifiable dated entries")
    return out


FEED_SOURCES: tuple[tuple[str, str, str, bool, dict[str, str]], ...] = (
    # (source_key, kind, url, is_official, extra_headers)
    ("sina_724", "sina_724", "https://zhibo.sina.com.cn/api/zhibo/feed?page=1&page_size=25&zhibo_id=152&tag_id=0&type=0", False, {}),
    ("wscn_global", "wscn", "https://api-one-wscn.awtmt.com/apiv1/content/lives?channel=global-channel&limit=20", False, {}),
    ("wscn_ashare", "wscn", "https://api-one-wscn.awtmt.com/apiv1/content/lives?channel=a-stock-channel&limit=15", False, {}),
    ("wscn_us", "wscn", "https://api-one-wscn.awtmt.com/apiv1/content/lives?channel=us-stock-channel&limit=15", False, {}),
    ("wscn_hk", "wscn", "https://api-one-wscn.awtmt.com/apiv1/content/lives?channel=hk-stock-channel&limit=15", False, {}),
    ("em_top", "em", "https://np-weblist.eastmoney.com/comm/web/getFastNewsList?client=web&biz=web_724&fastColumn=101&sortEnd=&pageSize=15&req_trace=1", False, {}),
    ("em_724", "em", "https://np-weblist.eastmoney.com/comm/web/getFastNewsList?client=web&biz=web_724&fastColumn=102&sortEnd=&pageSize=20&req_trace=1", False, {}),
    ("ths_724", "ths", "https://news.10jqka.com.cn/tapp/news/push/stock/?page=1&tag=&track=website", False, {}),
    ("jin10_flash", "jin10", "https://flash-api.jin10.com/get_flash_list?channel=-8200&vip=1", False, {"x-app-id": "bVBF4FyRTn5NJF5n", "x-version": "1.0.0"}),
    ("gov_yaowen", "gov_json", "https://www.gov.cn/yaowen/liebiao/YAOWENLIEBIAO.json", True, {}),
    ("gov_zhengce", "gov_json", "https://www.gov.cn/zhengce/zuixin/ZUIXINZHENGCE.json", True, {}),
    ("csrc_json", "csrc_json", "https://www.csrc.gov.cn/searchList/a1a078ee0bc54721ab6b148884c784a8?_isAgg=true&_isJson=true&_pageSize=12&_template=index&_rangeTimeGte=&_channelName=&page=1", True, {}),
    ("pbc_news", "html_pbc", "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html", True, {}),
    ("mof_news", "html_mof", "https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/", True, {}),
    ("hkma_rss", "rss", "https://www.hkma.gov.hk/eng/other-information/rss/rss_press-release.xml", True, {}),
    ("hkex_rss", "rss", "https://www.hkex.com.hk/Services/RSS-Feeds/News-Releases?sc_lang=en", True, {}),
    ("sfc_rss", "rss", "https://www.sfc.hk/en/RSS-Feeds/Press-releases", True, {}),
    ("fed_press", "rss", "https://www.federalreserve.gov/feeds/press_all.xml", True, {}),
    ("fed_monetary", "rss", "https://www.federalreserve.gov/feeds/press_monetary.xml", True, {}),
    ("sec_rss", "rss", "https://www.sec.gov/news/pressreleases.rss", True, {}),
    ("whitehouse_rss", "rss", "https://www.whitehouse.gov/news/feed/", True, {}),
    ("ecb_rss", "rss", "https://www.ecb.europa.eu/rss/press.html", True, {}),
    ("boj_rss", "rss", "https://www.boj.or.jp/en/rss/whatsnew.xml", True, {}),
    ("boe_rss", "rss", "https://www.bankofengland.co.uk/rss/news", True, {}),
    ("cnbc_econ", "rss", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", False, {}),
    ("cnbc_pol", "rss", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000113", False, {}),
    ("wsj_markets", "rss", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain", False, {}),
    ("ft_markets", "rss", "https://www.ft.com/markets?format=rss", False, {}),
)


def _fetch_one_feed(
    spec: tuple[str, str, str, bool, dict[str, str]], now_ts: float, timeout: int
) -> tuple[str, list[NewsItem], str | None]:
    src, kind, url, is_official, extra_headers = spec
    try:
        raw = _http_get_bytes(url, headers=extra_headers, timeout=timeout)
        if kind == "sina_724":
            return src, parse_sina_724(raw, now_ts), None
        if kind == "wscn":
            return src, parse_wscn_lives(raw, src, now_ts), None
        if kind == "em":
            return src, parse_eastmoney_fastnews(raw, src, now_ts), None
        if kind == "ths":
            return src, parse_ths_724(raw, now_ts), None
        if kind == "jin10":
            return src, parse_jin10_flash(raw, now_ts), None
        if kind == "gov_json":
            return src, parse_gov_cn_json(raw, src, now_ts), None
        if kind == "csrc_json":
            return src, parse_csrc_json(raw, now_ts), None
        if kind == "html_pbc":
            return src, parse_html_anchors(raw, src, url, now_ts), None
        if kind == "html_mof":
            return src, parse_html_anchors(raw, src, url, now_ts), None
        if kind == "rss":
            return src, parse_rss_xml(raw, src, is_official=is_official), None
        return src, [], f"unknown kind {kind}"
    except Exception as exc:
        return src, [], f"{type(exc).__name__}: {exc}"


def poll_all_feeds(
    *,
    sources_filter: set[str] | None = None,
    timeout: int = 8,
    now_ts: float | None = None,
) -> tuple[list[NewsItem], dict[str, str]]:
    """Concurrently poll all selected live policy & financial news feeds."""
    ts = now_ts if now_ts is not None else time.time()
    specs = [s for s in FEED_SOURCES if sources_filter is None or s[0] in sources_filter]
    items: list[NewsItem] = []
    errors: dict[str, str] = {}
    if not specs:
        return items, errors
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(specs))) as pool:
        futs = [pool.submit(_fetch_one_feed, s, ts, timeout) for s in specs]
        for fut in concurrent.futures.as_completed(futs):
            src, got, err = fut.result()
            if err:
                errors[src] = err
            else:
                items.extend(got)
    items.sort(key=lambda x: x.published_ts, reverse=True)
    return items, errors


def poll_live_quotes(*, timeout: int = 8, now_cst: datetime | None = None) -> tuple[dict[str, QuoteTick], dict[str, str]]:
    """Poll Sina multi-asset batch quotes (incl. live rt_hkHSI/VIX/FX/futures) + CNBC live US yields."""
    quotes: dict[str, QuoteTick] = {}
    errors: dict[str, str] = {}
    cutoff = now_cst if now_cst is not None else datetime.now(CST)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=CST)
    sina_batches = (
        ("sina_eq", "sh000001,sh000300,sz399006,sh000688,sh511260,sh511090,rt_hkHSI,rt_hkHSTECH,gb_inx,gb_ixic"),
        ("sina_macro", "hf_CHA50CFD,hf_ES,hf_NQ,hf_XAU,hf_GC,hf_OIL,hf_HG,fx_susdcnh,fx_susdjpy,DINIW,b_VIX"),
    )
    sina_headers = {"Referer": "https://finance.sina.com.cn"}
    for label, syms in sina_batches:
        try:
            raw = _http_get_bytes(f"https://hq.sinajs.cn/list={syms}", headers=sina_headers, timeout=timeout)
            quotes.update(parse_sina_batch_quotes(raw))
        except Exception as exc:
            errors[label] = f"{type(exc).__name__}: {exc}"

    try:
        cnbc_url = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=US2Y%7CUS10Y%7CUS30Y%7C.VIX&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json"
        raw_cnbc = _http_get_bytes(cnbc_url, timeout=timeout)
        cnbc_ticks = parse_cnbc_batch_quotes(raw_cnbc)
        for k, v in cnbc_ticks.items():
            if k not in quotes or v.is_yield:
                quotes[k] = v
                continue
            previous = _quote_observed_at(quotes[k])
            candidate = _quote_observed_at(v)
            if candidate is not None and candidate <= cutoff and (
                previous is None or previous > cutoff or candidate > previous
            ):
                quotes[k] = v
    except Exception as exc:
        errors["cnbc_yields"] = f"{type(exc).__name__}: {exc}"

    return quotes, errors


def _read_json_readonly(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_ssot_context(
    *,
    gold_path: Path = GOLD_SNAPSHOT_PATH,
    market_path: Path = MARKET_STATE_PATH,
    policy_path: Path = POLICY_CALENDAR_PATH,
    calendar_path: Path = MARKET_CALENDAR_PATH,
    require_same_edition: bool = False,
) -> dict[str, Any]:
    """Read repository SSOT files strictly read-only. Fail-closed on gold_locked."""
    gold_snap = _read_json_readonly(gold_path)
    mstate = _read_json_readonly(market_path)
    pcal = _read_json_readonly(policy_path)
    mcal = _read_json_readonly(calendar_path)

    if require_same_edition:
        edition = gold_snap.get("edition_id")
        if not isinstance(edition, str) or not edition or any(
            source.get("edition_id") != edition for source in (mstate, pcal)
        ):
            raise ValueError("Isolated monitor gold, equity and policy snapshots must have the same edition_id")
        if not isinstance(pcal.get("events"), list) or mcal.get("timezone") != "Asia/Shanghai":
            raise ValueError("Isolated monitor data requires a policy event list and a Beijing-time market calendar")

    gold_locked = gold_snap.get("tier_code") == "Tier 0" or gold_snap.get("new_buy_allowed") is not True
    markets = mstate.get("markets") if isinstance(mstate.get("markets"), dict) else {}
    a_m = markets.get("a_share") if isinstance(markets.get("a_share"), dict) else {}
    hk_m = markets.get("hk_stock") if isinstance(markets.get("hk_stock"), dict) else {}
    us_m = markets.get("us_stock") if isinstance(markets.get("us_stock"), dict) else {}

    events = pcal.get("events") if isinstance(pcal.get("events"), list) else []
    return {
        "edition_id": str(mstate.get("edition_id") or gold_snap.get("edition_id") or "unknown"),
        "gold_locked": gold_locked,
        "gold_tier_label": (
            "红灯停（暂不新买 · 新仓 0%）" if gold_locked else str(gold_snap.get("tier_label") or "暂无灯号")
        ),
        "gold_gates_passed": (
            f"{gold_snap['tier1_passed']}/{gold_snap['tier1_total']}"
            if "tier1_passed" in gold_snap and "tier1_total" in gold_snap else None
        ),
        "a_lamp": a_m.get("lamp_label"),
        "a_cap_pct": _snapshot_pct(a_m.get("equity_cap_pct")),
        "a_fomo": a_m.get("fomo_threshold"),
        "hk_lamp": hk_m.get("lamp_label"),
        "hk_offshore_cap_pct": _snapshot_pct(hk_m.get("offshore_equity_cap_pct")),
        "hk_onshore_cap_pct": _snapshot_pct(hk_m.get("onshore_connect_cap_pct")),
        "hk_fomo": hk_m.get("fomo_threshold"),
        "us_lamp": us_m.get("lamp_label"),
        "us_cap_pct": _snapshot_pct(us_m.get("equity_cap_pct")),
        "us_cash_pct": _snapshot_pct(us_m.get("cash_tbill_pct")),
        "us_fomo": us_m.get("fomo_threshold"),
        "events": events,
        "market_calendar": mcal,
    }


def _snapshot_pct(value: object) -> int | float | None:
    if type(value) in (int, float) and 0 <= value <= 100:
        return value
    return None


def _monitor_data_root(data_root: Path | None) -> Path:
    if data_root is None:
        return REPO_ROOT
    root = data_root.expanduser().resolve()
    for path in (GOLD_SNAPSHOT_PATH, MARKET_STATE_PATH, POLICY_CALENDAR_PATH, MARKET_CALENDAR_PATH, KLINES_CORE_PATH):
        relative = path.relative_to(REPO_ROOT)
        selected = (root / relative).resolve()
        if not selected.is_relative_to(root) or not selected.is_file():
            raise ValueError(f"Monitor data root is missing an isolated {relative}: {root}")
    return root


def _load_monitor_inputs(data_root: Path | None) -> tuple[Path, dict[str, Any], dict[str, float]]:
    root = REPO_ROOT if data_root is None else data_root.expanduser().resolve()
    with state_read_lock(root):
        if data_root is not None:
            _monitor_data_root(root)
        ssot = load_ssot_context(
            gold_path=root / GOLD_SNAPSHOT_PATH.relative_to(REPO_ROOT),
            market_path=root / MARKET_STATE_PATH.relative_to(REPO_ROOT),
            policy_path=root / POLICY_CALENDAR_PATH.relative_to(REPO_ROOT),
            calendar_path=root / MARKET_CALENDAR_PATH.relative_to(REPO_ROOT),
            require_same_edition=data_root is not None,
        )
        vol_baselines = load_vol_baselines(
            root / KLINES_CORE_PATH.relative_to(REPO_ROOT),
            expected_edition=ssot["edition_id"] if data_root is not None else None,
        )
    return root, ssot, vol_baselines


def _is_in_quiet_window(
    now_cst: datetime, start_hhmm: str = "23:30", end_hhmm: str = "07:15"
) -> bool:
    """Return True if now_cst falls inside [start_hhmm, end_hhmm) CST (supports overnight wrap)."""
    now_dt = now_cst.astimezone(CST) if now_cst.tzinfo else now_cst.replace(tzinfo=CST)
    try:
        s_h, s_m = (int(x) for x in start_hhmm.split(":"))
        e_h, e_m = (int(x) for x in end_hhmm.split(":"))
    except (ValueError, AttributeError):
        s_h, s_m, e_h, e_m = 23, 30, 7, 15
    cur = now_dt.hour * 60 + now_dt.minute
    start = s_h * 60 + s_m
    end = e_h * 60 + e_m
    if start == end:
        return False
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end


def _calendar_event_scope(
    event: dict[str, Any],
) -> tuple[date, date, datetime | None, bool] | None:
    """Return the validated date span, exact timestamp and explicit all-day flag."""
    try:
        start = date.fromisoformat(str(event.get("date_cst") or ""))
        end = date.fromisoformat(str(event.get("end_date_cst") or start))
        if end < start:
            return None
        time_text = str(event.get("time_cst") or "").strip()
        precision = str(event.get("date_precision") or "").strip()
        clock = re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_text)
        # Legacy rows have no precision. Preserve their literal HH:MM/all-day forms.
        if precision == "exact" or (not precision and clock):
            if not clock or start != end:
                return None
            return start, end, datetime.combine(start, wall_time.fromisoformat(time_text), CST), False
        if precision not in ("", "window_tbd") or clock:
            return None
        return start, end, None, time_text in _ALL_DAY_TIMES
    except ValueError:
        return None


def _monitor_window_minutes(event: dict[str, Any]) -> int:
    value = event.get("monitor_window_min", 120)
    return value if type(value) is int and value > 0 else 0


def is_in_calendar_p0_window(
    events: list[dict[str, Any]],
    now_cst: datetime,
    *,
    quiet_enabled: bool = True,
    quiet_start: str = "23:30",
    quiet_end: str = "07:15",
) -> bool:
    """Return True if now_cst falls within monitor_window_min of a P0 catalyst event.

    Exact-time HH:MM P0 events remain active 24/7 (including overnight quiet hours);
    multi-day / all-day ("全天窗口"/"全天") P0 windows only activate during daytime/evening hours
    so they never disable overnight quiet hours or force 180s overnight polling.
    """
    now_dt = now_cst.astimezone(CST) if now_cst.tzinfo else now_cst.replace(tzinfo=CST)
    in_overnight = (
        _is_in_quiet_window(now_dt, quiet_start, quiet_end)
        if quiet_enabled
        else _is_in_quiet_window(now_dt, "23:30", "07:15")
    )
    for ev in events:
        if not isinstance(ev, dict) or str(ev.get("impact_tier") or "").upper() != "P0":
            continue
        win_min = _monitor_window_minutes(ev)
        scope = _calendar_event_scope(ev)
        if not win_min or scope is None:
            continue
        start, end, exact, all_day = scope
        if exact is not None and abs((now_dt - exact).total_seconds()) <= win_min * 60:
            return True
        if all_day and start <= now_dt.date() <= end and not in_overnight:
            return True
    return False


def find_next_calendar_event(events: list[dict[str, Any]], region: str, now_cst: datetime) -> dict[str, Any] | None:
    now_dt = now_cst.astimezone(CST) if now_cst.tzinfo else now_cst.replace(tzinfo=CST)
    ranked = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        scope = _calendar_event_scope(ev)
        if scope is None:
            continue
        start, end, exact, _ = scope
        if end < now_dt.date() or (exact is not None and exact < now_dt):
            continue
        ev_reg = str(ev.get("region") or "").upper()
        relevant = ev_reg in (region.upper(), "GLOBAL")
        rank = (not relevant, max(start, now_dt.date()), str(ev.get("impact_tier")) != "P0", exact.time() if exact else wall_time.max)
        ranked.append((rank, ev))
    return min(ranked, key=lambda entry: entry[0])[1] if ranked else None


def _market_overrides(market_calendar: dict[str, Any], day: str) -> list[dict[str, Any]]:
    overrides = market_calendar.get("calendar_overrides")
    if not isinstance(overrides, list):
        return []
    return [
        row for row in overrides
        if isinstance(row, dict)
        and str(row.get("overlay_mode") or "").upper() != "NONE"
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", start := str(row.get("date") or ""))
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end := str(row.get("end_date") or start))
        and start <= day <= end
    ]


def _is_holiday_closed(
    region: str, now_dt: datetime, market_calendar: dict[str, Any] | None = None,
    *, us_bonds: bool = False,
) -> bool:
    """Return True if `region` has a full-day holiday closure on `now_dt` per market_calendar.json."""
    if not isinstance(market_calendar, dict):
        return False
    check_dt = now_dt.astimezone(NEW_YORK) if region in ("US", "GLOBAL") else now_dt
    day_str = check_dt.strftime("%Y-%m-%d")

    # 1. Real gold/market_calendar.json schema: calendar_overrides
    overrides = _market_overrides(market_calendar, day_str)
    if overrides:
        target_tokens = {
            "CN": ("CN_A_SHARE", "CN_ALL", "A_SHARE", "SSE", "SZSE"),
            "HK": ("HK_EQUITY", "HKEX", "HK_STOCK"),
            "US": ("US_BOND",) if us_bonds else ("US_EQUITY", "NYSE", "NASDAQ"),
            "GLOBAL": ("COMEX_CME", "GLOBAL_GOLD", "UK_LSE_LBMA"),
        }.get(region, ())
        th_keys = {
            "CN": ("cn_a_share", "cn_a_share_sge_shfe", "global_markets"),
            "HK": ("hk_equity", "hkex", "us_eu_uk_hk_in", "global_markets"),
            "US": (("us_bond",) if us_bonds else ("us_equity",)) + ("us_equity_bond", "us_eu_uk_hk_in", "global_markets"),
            "GLOBAL": ("global_markets", "cme_metals_electronic", "us_eu_uk_hk_in"),
        }.get(region, ())
        for ov in overrides:
            if str(ov.get("overlay_mode") or "").upper() == "GLOBAL":
                return True
            mkts = [str(m).upper() for m in (ov.get("markets") or [])]
            if target_tokens and not any(t in mkts for t in target_tokens):
                continue
            th = ov.get("trading_hours_bjt") if isinstance(ov.get("trading_hours_bjt"), dict) else {}
            mkt_status = ""
            for tk in th_keys:
                if th.get(tk):
                    mkt_status = str(th[tk])
                    break
            ev_txt = str(ov.get("event") or "")
            # Half-day / early-close is still partially open; only full-day closures mark closed
            if mkt_status:
                if (
                    "全天休市" in mkt_status
                    or "法定休市" in mkt_status
                    or mkt_status.strip() == "休市"
                    or "无报价" in mkt_status
                ) and ("半日" not in mkt_status and "提前" not in mkt_status):
                    return True
            elif ("休市" in ev_txt) and ("半日市" not in ev_txt and "提前收盘" not in ev_txt and "提前停盘" not in ev_txt):
                if region != "GLOBAL":
                    return True

    # 2. Backward-compatible synthetic holiday/closure fixtures
    holidays = market_calendar.get("holidays") or market_calendar.get("closures") or {}
    if isinstance(holidays, dict):
        reg_keys = {
            "CN": ("cn", "a_share", "CN"),
            "HK": ("hk", "hk_stock", "HK"),
            "US": ("us", "us_stock", "US"),
            "GLOBAL": ("global", "GLOBAL"),
        }.get(region, ())
        for rk in reg_keys:
            entries = holidays.get(rk)
            if isinstance(entries, dict) and day_str in entries:
                return True
            if isinstance(entries, list) and any(
                (isinstance(e, str) and e == day_str) or (isinstance(e, dict) and e.get("date") == day_str)
                for e in entries
            ):
                return True
    elif isinstance(holidays, list):
        for row in holidays:
            if isinstance(row, dict) and row.get("date") == day_str:
                mkts_s = str(row.get("market") or row.get("markets") or "").upper()
                if region in mkts_s or (region == "CN" and "A_SHARE" in mkts_s):
                    return True
    return False


def _symbol_to_region(sym: str) -> str:
    """Map a live quote symbol to its trading-session region (CN / HK / US / GLOBAL)."""
    if sym.startswith(("sh", "sz", "bj")):
        return "CN"
    if sym.startswith("rt_hk"):
        return "HK"
    if sym in ("US10Y", "US2Y", "US30Y", "b_VIX", "hf_ES", "hf_NQ") or sym.startswith("gb_"):
        return "US"
    return "GLOBAL"


def _early_close(
    market_calendar: dict[str, Any], day: str, key: str, *, eastern: bool,
) -> wall_time | None:
    clock = r"((?:[01]\d|2[0-3]):[0-5]\d)"
    pattern = clock + (r"\s+(?:EST|EDT|ET)\b" if eastern else r"\s+BJT\b")
    for event in _market_overrides(market_calendar, day):
        hours = event.get("trading_hours_bjt")
        if not isinstance(hours, dict):
            continue
        value = str(hours.get(key) or "")
        if not eastern and ("半日" not in value or event.get("date") != day):
            continue
        match = re.search(pattern, value)
        if match:
            return wall_time.fromisoformat(match[1])
    return None


def _vix_window(now_et: datetime, market_calendar: dict[str, Any]) -> tuple[wall_time, wall_time] | None:
    exceptions = market_calendar.get("vix_session_exceptions")
    row = exceptions.get(now_et.date().isoformat()) if isinstance(exceptions, dict) else None
    windows = row.get("windows_et") if isinstance(row, dict) else (("03:15", "09:25"), ("09:31", "16:15"))
    for pair in windows if isinstance(windows, (list, tuple)) else ():
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            try:
                start, end = (wall_time.fromisoformat(value) for value in pair)
            except (TypeError, ValueError):
                continue
            if start <= now_et.time() <= end:
                return start, end
    return None


_QUOTE_CLOCK_ZONE = re.compile(r"\s+(EST|EDT|ET|BJT|CST)$")


def _quote_observed_at(tick: QuoteTick) -> datetime | None:
    raw = tick.timestamp.strip().upper()
    if not re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}", raw):
        return None
    tz = NEW_YORK if tick.source == "cnbc" else CST
    zone = _QUOTE_CLOCK_ZONE.search(raw)
    if zone:
        raw = raw[:zone.start()]
        tz = {"EST": timezone(timedelta(hours=-5)), "EDT": timezone(timedelta(hours=-4)),
              "ET": NEW_YORK, "BJT": CST, "CST": CST}[zone[1]]
    try:
        observed = datetime.fromisoformat(raw.replace("/", "-").replace("Z", "+00:00"))
        return observed if observed.tzinfo else observed.replace(tzinfo=tz)
    except ValueError:
        return None


def _quote_has_clock_only(tick: QuoteTick) -> bool:
    raw = _QUOTE_CLOCK_ZONE.sub("", tick.timestamp.strip().upper())
    try:
        if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A|P)", raw):
            compact = re.sub(r"\s+", "", raw)
            if not compact.endswith("M"):
                compact += "M"
            datetime.strptime(compact, "%I:%M:%S%p" if compact.count(":") == 2 else "%I:%M%p")
        else:
            if not re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", raw):
                return False
            wall_time.fromisoformat(raw)
        return True
    except ValueError:
        return False


def _is_stale_closed_tick(
    tick: QuoteTick,
    region: str,
    now_dt: datetime,
    market_calendar: dict[str, Any] | None = None,
    *,
    allow_undated_reference: bool = False,
) -> bool:
    """Reject closed sessions and vendor observations too old to describe the active market."""
    dt = now_dt.astimezone(CST) if now_dt.tzinfo else now_dt.replace(tzinfo=CST)
    calendar = market_calendar if isinstance(market_calendar, dict) else {}
    now_et = dt.astimezone(NEW_YORK)
    vix_window = None
    if tick.symbol == "b_VIX":
        if now_et.weekday() >= 5 or _is_holiday_closed("US", dt, calendar):
            return True
        vix_window = _vix_window(now_et, calendar)
        if vix_window is None:
            return True
    elif tick.is_yield and region == "US":
        close = _early_close(calendar, now_et.date().isoformat(), "us_bond_close", eastern=True) or wall_time(17)
        if now_et.weekday() >= 5 or _is_holiday_closed("US", dt, calendar, us_bonds=True) or now_et.time() >= close:
            return True
    elif tick.symbol in ("hf_ES", "hf_NQ"):
        if _is_holiday_closed(region, dt, calendar) or not is_region_market_open("GLOBAL", dt, market_calendar=calendar):
            return True
        if wall_time(17) <= now_et.time() < wall_time(18):
            return True
    else:
        if not is_region_market_open(region, dt, market_calendar=calendar):
            return True

    observed = _quote_observed_at(tick)
    if observed is None:
        if allow_undated_reference and _quote_has_clock_only(tick):
            return False
        return bool(tick.source or tick.timestamp)
    if not timedelta(0) <= dt - observed <= QUOTE_MAX_AGE:
        return True
    if vix_window is not None:
        observed_et = observed.astimezone(NEW_YORK)
        return observed_et.date() != now_et.date() or observed_et.time() < vix_window[0]
    return False


def is_region_market_open(
    region: str, now_cst: datetime, *, market_calendar: dict[str, Any] | None = None
) -> bool:
    """CST trading-hour check honoring real gold/market_calendar.json calendar_overrides & legacy holiday fixtures."""
    dt = now_cst.astimezone(CST) if now_cst.tzinfo else now_cst.replace(tzinfo=CST)
    wd = dt.weekday()  # 0=Mon..6=Sun
    hhmm = dt.hour * 60 + dt.minute

    calendar = market_calendar if isinstance(market_calendar, dict) else {}
    if _is_holiday_closed(region, dt, calendar):
        return False

    if region == "CN":
        return wd < 5 and ((570 <= hhmm <= 690) or (780 <= hhmm <= 900))
    if region == "HK":
        early_close = _early_close(calendar, dt.date().isoformat(), "hkex", eastern=False)
        return (
            wd < 5 and ((570 <= hhmm <= 720) or (780 <= hhmm <= 960))
            and (early_close is None or dt.time() < early_close)
        )
    now_et = dt.astimezone(NEW_YORK)
    if region == "US":
        end = _early_close(calendar, now_et.date().isoformat(), "us_equity_close", eastern=True) or wall_time(16)
        return now_et.weekday() < 5 and wall_time(9, 30) <= now_et.time() < end
    # Global FX runs from Sunday 17:00 ET to Friday 17:00 ET.
    day_et = now_et.weekday()
    return day_et < 4 or (day_et == 4 and now_et.time() < wall_time(17)) or (
        day_et == 6 and now_et.time() >= wall_time(17)
    )


def _kw_in_text(kw: str, text_low: str) -> bool:
    """Use word boundaries for pure ASCII keywords (prevents TGA->mortgage, BIS->cannabis, QT->MQTT)."""
    k = kw.lower()
    if k.isascii():
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", text_low))
    return k in text_low


def match_policy_domain(text: str, body: str = "") -> PolicyDomainRule | None:
    """Match a policy domain rule. When body is passed separately from title (text),
    evaluate keywords_neg against title whenever keywords_pos matched in title so cross-market
    mentions in the article body never mutually kill valid policy headlines."""
    title_str = str(text or "")
    body_str = str(body or "")
    full_str = f"{title_str} {body_str}".strip() if body_str else title_str
    if _ROUTINE_NOISE_RE.search(full_str) and not _HARD_CATALYST_OVERRIDE_RE.search(full_str):
        return None
    title_low = title_str.lower()
    full_low = full_str.lower()
    best: tuple[int, int, PolicyDomainRule] | None = None
    for rule in POLICY_DOMAINS:
        title_hits = sum(1 for kw in rule.keywords_pos if _kw_in_text(kw, title_low))
        total_hits = sum(1 for kw in rule.keywords_pos if _kw_in_text(kw, full_low)) if body_str else title_hits
        if total_hits <= 0:
            continue
        neg_scope = title_low if (body_str and title_hits > 0) else full_low
        if any(_kw_in_text(neg, neg_scope) for neg in rule.keywords_neg):
            continue
        cand = (total_hits, rule.authority_default, rule)
        if best is None or (cand[0], cand[1]) > (best[0], best[1]):
            best = cand
    return best[2] if best else None


def _title_shingles(text: str) -> set[str]:
    clean = re.sub(r"[\s\W_]+", "", str(text or "").lower())
    if len(clean) < 3:
        return {clean} if clean else set()
    return {clean[i : i + 3] for i in range(len(clean) - 2)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _compute_anchor_z(sym: str, tick: QuoteTick, vol_baselines: dict[str, float]) -> float:
    sigma = max(0.15, float(vol_baselines.get(sym, _DEFAULT_SIGMA_1D.get(sym, 1.25))))
    if tick.is_yield and tick.change_bp is not None:
        return round(tick.change_bp / sigma, 2)
    return round(tick.change_pct / sigma, 2)


def _anchor_bucket(sym: str) -> str:
    if sym in ("US10Y", "US2Y", "US30Y", "sh511260", "sh511090"):
        return "rates"
    if sym in ("fx_susdcnh", "fx_susdjpy", "DINIW"):
        return "fx"
    if sym in ("hf_XAU", "hf_GC", "hf_OIL", "hf_HG"):
        return "commodity"
    if sym == "b_VIX":
        return "vol"
    return "equity"


def _anchor_snapshot(tick: QuoteTick, z: float | None) -> dict[str, Any]:
    observed = _quote_observed_at(tick)
    return {
        "symbol": tick.symbol,
        "name": tick.name,
        "last": tick.last,
        "change_pct": tick.change_pct,
        "change_bp": tick.change_bp,
        "z": z,
        "is_yield": tick.is_yield,
        "source": _QUOTE_SOURCE_NAMES.get(tick.source, "来源待核"),
        "observed_at_cst": observed.astimezone(CST).isoformat(timespec="seconds") if observed else None,
        "reported_clock": tick.timestamp.strip() if observed is None and _quote_has_clock_only(tick) else None,
    }


def classify_and_score(
    items: list[NewsItem],
    quotes: dict[str, QuoteTick],
    vol_baselines: dict[str, float],
    *,
    now_cst: datetime,
    max_age_sec: int = NEWS_MAX_AGE_SEC,
    market_calendar: dict[str, Any] | None = None,
    state_store: Any | None = None,
    persist_clusters: bool = True,
) -> list[ScoredSignal]:
    """Cluster cross-source policy news (within & across polls) and compute deterministic 0-100 scores."""
    now_dt = now_cst.astimezone(CST) if now_cst.tzinfo else now_cst.replace(tzinfo=CST)
    now_ts = now_dt.timestamp()

    # Step 1: filter recent items matching a policy domain
    matched: list[tuple[NewsItem, PolicyDomainRule, set[str], float]] = []
    today_cst = now_dt.date()
    for it in items:
        eff_ts = it.published_ts
        if it.date_only and datetime.fromtimestamp(it.published_ts, tz=CST).date() == today_cst:
            # Date-only same-day official notices (e.g., pbc_news/mof_news) clamp to fetch time
            # so they are never silently dropped after 03:00 CST by the 3h max_age_sec filter.
            eff_ts = now_ts
        if not 0 <= now_ts - eff_ts <= max_age_sec:
            continue
        rule = match_policy_domain(it.title, it.body)
        if rule is None:
            continue
        matched.append((it, rule, _title_shingles(it.title), eff_ts))

    # Step 2: cluster by same domain_id & 3-gram Jaccard >= 0.40 within 90 min
    clusters: list[dict[str, Any]] = []
    for it, rule, sh, eff_ts in matched:
        placed = False
        for cl in clusters:
            if cl["rule"].domain_id != rule.domain_id:
                continue
            if abs(eff_ts - cl["latest_ts"]) > 5400:
                continue
            if _jaccard(sh, cl["shingles"]) >= 0.40:
                cl["items"].append((it, eff_ts))
                cl["shingles"] |= sh
                cl["latest_ts"] = max(cl["latest_ts"], eff_ts)
                placed = True
                break
        if not placed:
            clusters.append({"rule": rule, "items": [(it, eff_ts)], "shingles": set(sh), "latest_ts": eff_ts})

    signals: list[ScoredSignal] = []
    for cl in clusters:
        rule: PolicyDomainRule = cl["rule"]
        cl_pairs: list[tuple[NewsItem, float]] = cl["items"]
        cl_pairs.sort(key=lambda pair: (1 if pair[0].is_official else 0, pair[0].importance_flag, pair[1]), reverse=True)
        cl_items: list[NewsItem] = [pair[0] for pair in cl_pairs]
        rep, rep_ts = cl_pairs[0]
        unique_sources = sorted({it.source for it in cl_items})
        source_urls = [it.url for it in cl_items if it.url][:4]
        combined_text = " ".join(f"{it.title} {it.body}" for it in cl_items)
        item_hashes = [_news_item_hash(it) for it in cl_items]

        is_official = any(it.is_official or _OFFICIAL_SOURCE_TIERS.get(it.source, (0, False))[1] for it in cl_items)
        has_rumor_cue = bool(_RUMOR_CUE_RE.search(combined_text))
        has_explicit_hard_rumor = bool(_EXPLICIT_RUMOR_HARD_RE.search(combined_text))
        has_official_entity = bool(_OFFICIAL_ENTITY_IN_TEXT_RE.search(combined_text))

        # Immutable cross-poll cluster resolution (reuses initial cluster_key & merges cross-poll sources)
        day_str = now_dt.strftime("%Y-%m-%d")
        norm_core = "".join(sorted(list(cl["shingles"]))[:8])
        default_ckey = f"{rule.domain_id}:{hashlib.sha256(f'{rule.domain_id}:{day_str}:{norm_core}'.encode('utf-8')).hexdigest()[:12]}"
        cluster_key = default_ckey
        if state_store is not None and hasattr(state_store, "resolve_recent_cluster"):
            cluster_key, merged_sources, merged_official = state_store.resolve_recent_cluster(
                domain_id=rule.domain_id,
                shingles=cl["shingles"],
                sources=unique_sources,
                is_official=is_official,
                default_cluster_key=default_ckey,
                now_ts=now_ts,
                persist=persist_clusters,
            )
            unique_sources = merged_sources
            is_official = is_official or merged_official

        # S_auth [0..40]
        if is_official:
            s_auth = min(40, rule.authority_default)
        elif has_official_entity:
            s_auth = min(34, max(24, rule.authority_default - 4))
            if any(it.importance_flag >= 1 for it in cl_items):
                s_auth = min(36, s_auth + 2)
        else:
            s_auth = 20 + (2 if any(it.importance_flag >= 1 for it in cl_items) else 0)

        # K_verify [0.6 | 1.0]
        source_families = {_news_source_family(source) for source in unique_sources}
        k_verify = 1.0 if (is_official or (len(source_families) >= 2 and not has_rumor_cue)) else 0.6

        # Dedicated text-level HK dividend-tax rumor firewall (applies regardless of matched domain!)
        hk_tax_unverified = False
        if rule.domain_id == "hk_southbound_tax" or _HK_TAX_TOPIC_RE.search(combined_text):
            if _HK_TAX_TOPIC_RE.search(combined_text):
                formal_notice = is_official or (not has_rumor_cue and bool(_HK_TAX_ENACTED_RE.search(combined_text)))
                if not formal_notice:
                    k_verify = 0.6
                    hk_tax_unverified = True

        # S_confirm [0..35] & S_spillover [0..25]
        max_z = 0.0
        buckets_hit: set[str] = set()
        anchor_snaps: list[dict[str, Any]] = []
        primary_eq_pct: float | None = None
        for sym in rule.primary_anchors:
            tick = quotes.get(sym)
            if tick is None or _is_stale_closed_tick(
                tick, _symbol_to_region(sym), now_dt, market_calendar=market_calendar,
                allow_undated_reference=True,
            ):
                continue
            if _quote_has_clock_only(tick):
                anchor_snaps.append(_anchor_snapshot(tick, None))
                continue
            z = _compute_anchor_z(sym, tick, vol_baselines)
            abs_z = abs(z)
            if abs_z > max_z:
                max_z = abs_z
            if abs_z >= 1.2:
                buckets_hit.add(_anchor_bucket(sym))
            if primary_eq_pct is None and _anchor_bucket(sym) == "equity":
                primary_eq_pct = tick.change_pct
            anchor_snaps.append(_anchor_snapshot(tick, z))
        anchor_snaps.sort(key=lambda snap: snap["z"] is None)

        if max_z >= 3.0:
            s_confirm = 35
        elif max_z >= 2.2:
            s_confirm = 28
        elif max_z >= 1.5:
            s_confirm = 20
        elif max_z >= 0.9:
            s_confirm = 12
        else:
            s_confirm = 4

        is_closed_floor = False
        if is_official and s_auth >= 35 and not is_region_market_open(rule.region, now_dt, market_calendar=market_calendar) and s_confirm < 20:
            s_confirm = 20
            is_closed_floor = True

        s_spillover = min(25, len(buckets_hit) * 7 + (10 if (rule.region == "GLOBAL" or rule.domain_id in ("cn_tariff", "us_fed_fomc", "crisis_breaker")) else 4))
        raw_score = round((s_auth + s_confirm + s_spillover) * k_verify)

        is_rumor_capped = False
        is_flash_unverified = False
        if k_verify < 1.0:
            if max_z >= 3.0 and not hk_tax_unverified and not has_explicit_hard_rumor:
                is_flash_unverified = True
                raw_score = max(raw_score, 70)
            else:
                raw_score = min(raw_score, 58)
                is_rumor_capped = True

        # Buy-rumor / sell-fact divergence flag
        pos_hits = len(_POSITIVE_CUE_RE.findall(combined_text))
        neg_hits = len(_NEGATIVE_CUE_RE.findall(combined_text))
        is_divergence = False
        if primary_eq_pct is not None:
            if pos_hits > neg_hits and primary_eq_pct <= -0.6:
                is_divergence = True
            elif neg_hits > pos_hits and primary_eq_pct >= 0.8:
                is_divergence = True

        score = max(0, min(100, int(raw_score)))
        severity = "P0" if score >= 82 else ("P1" if score >= 68 else ("P2" if score >= 50 else "SILENT"))

        sig_id = hashlib.sha256(f"{rep.source}:{rep.title}:{int(rep_ts // 60)}".encode("utf-8")).hexdigest()[:16]
        reported_at = datetime.fromtimestamp(rep.published_ts, tz=CST)
        pub_cst = reported_at.strftime("%Y-%m-%d（仅披露日期）" if rep.date_only else "%Y-%m-%d %H:%M CST")

        signals.append(
            ScoredSignal(
                signal_id=sig_id,
                cluster_key=cluster_key,
                domain_id=rule.domain_id,
                region=rule.region,
                domain_label=rule.label,
                title=rep.title,
                body=rep.body,
                sources=unique_sources,
                source_urls=source_urls,
                published_cst=pub_cst,
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
                is_market_closed_floor=is_closed_floor,
                max_z=round(max_z, 2),
                anchor_snapshots=anchor_snaps,
                transmission_chain=rule.transmission_chain,
                guardrail=rule.guardrail,
                item_hashes=item_hashes,
            )
        )

    signals.sort(key=lambda s: s.score, reverse=True)
    return signals


def detect_upcoming_calendar_alerts(
    events: list[dict[str, Any]], *, now_cst: datetime, lead_minutes: int = 60
) -> list[ScoredSignal]:
    """Emit proactive T-60m WeChat pre-alerts for exact-time P0 catalyst events in policy_calendar.json."""
    now_dt = now_cst.astimezone(CST) if now_cst.tzinfo else now_cst.replace(tzinfo=CST)
    pub_cst = now_dt.strftime("%Y-%m-%d %H:%M CST")
    out: list[ScoredSignal] = []
    for ev in events:
        if not isinstance(ev, dict) or str(ev.get("impact_tier") or "").upper() != "P0" or not _monitor_window_minutes(ev):
            continue
        scope = _calendar_event_scope(ev)
        if scope is None or scope[2] is None:
            continue
        ev_dt = scope[2]
        date_s, time_s = ev_dt.strftime("%Y-%m-%d %H:%M").split()
        mins_left = (ev_dt - now_dt).total_seconds() / 60.0
        if not (0.0 <= mins_left <= float(lead_minutes)):
            continue
        eid = str(ev.get("event_id") or f"{date_s}_{time_s}")
        reg = str(ev.get("region") or "GLOBAL").upper()
        if reg not in ("CN", "HK", "US", "GLOBAL"):
            reg = "GLOBAL"
        title = f"重磅日历临近（约{int(round(mins_left))}分钟后）：{ev.get('title', eid)}"
        body = (
            f"预定北京时间 {date_s} {time_s} 发布/启动。"
            f"市场预期：{ev.get('expected_consensus', '')}"
        )
        chain = str(ev.get("market_transmission") or "重大宏观/政策窗口临近，易引发利率、汇率与三市权益共振重定价。")
        guard = str(ev.get("pre_event_stance") or "窗口前不赌单边方向、不加杠杆，严格遵守红灯仓位纪律。")
        out.append(
            ScoredSignal(
                signal_id=hashlib.sha256(f"cal:{eid}".encode("utf-8")).hexdigest()[:16],
                cluster_key=f"cal_prealert:{eid}",
                domain_id="calendar_prealert",
                region=reg,
                domain_label="财经政策日历 · 临近提醒",
                title=title,
                body=body,
                sources=["policy_calendar_ssot"],
                source_urls=[str(ev.get("source_url") or "")],
                published_cst=pub_cst,
                score=74,
                severity="P1",
                s_auth=40,
                s_confirm=20,
                s_spillover=14,
                k_verify=1.0,
                is_official=True,
                is_rumor_capped=False,
                is_flash_unverified=False,
                is_divergence=False,
                is_market_closed_floor=True,
                max_z=0.0,
                anchor_snapshots=[],
                transmission_chain=chain,
                guardrail=guard,
            )
        )
    return out


def detect_market_first_anomalies(
    quotes: dict[str, QuoteTick],
    vol_baselines: dict[str, float],
    *,
    now_cst: datetime,
    market_calendar: dict[str, Any] | None = None,
) -> list[ScoredSignal]:
    """Detect 3+1 crisis breakers & extreme >=3.2-sigma live price shocks independently of news."""
    now_dt = now_cst.astimezone(CST) if now_cst.tzinfo else now_cst.replace(tzinfo=CST)
    pub_cst = now_dt.strftime("%Y-%m-%d %H:%M CST")
    day_str = now_dt.strftime("%Y-%m-%d")
    out: list[ScoredSignal] = []

    def _make_breaker(bid: str, region: str, title: str, body: str, score: int, sym: str, tick: QuoteTick, z: float, chain: str, guard: str) -> ScoredSignal:
        sev = "P0" if score >= 82 else "P1"
        source = _QUOTE_SOURCE_NAMES.get(tick.source, "来源待核")
        source_urls = []
        if tick.source == "cnbc":
            source_urls.append(f"https://www.cnbc.com/quotes/{'.VIX' if sym == 'b_VIX' else sym}")
        elif tick.source == "sina":
            source_urls.append("https://finance.sina.com.cn/")
        return ScoredSignal(
            signal_id=hashlib.sha256(f"mkt:{bid}:{day_str}".encode("utf-8")).hexdigest()[:16],
            cluster_key=f"market_first:{bid}:{day_str}",
            domain_id="crisis_breaker",
            region=region,
            domain_label="盘面异动 · 实时危机熔断监测",
            title=title,
            body=body,
            sources=[source],
            source_urls=source_urls,
            published_cst=pub_cst,
            score=score,
            severity=sev,
            s_auth=40,
            s_confirm=35,
            s_spillover=20,
            k_verify=1.0,
            is_official=False,
            is_rumor_capped=False,
            is_flash_unverified=False,
            is_divergence=False,
            is_market_closed_floor=False,
            max_z=round(abs(z), 2),
            anchor_snapshots=[_anchor_snapshot(tick, z)],
            transmission_chain=chain,
            guardrail=guard,
            is_market_first=True,
        )

    us10y = quotes.get("US10Y")
    if us10y and not _is_stale_closed_tick(us10y, "US", now_dt, market_calendar=market_calendar) and (us10y.last >= 5.25 or (us10y.change_bp is not None and abs(us10y.change_bp) >= 18.0)):
        z = _compute_anchor_z("US10Y", us10y, vol_baselines)
        change = f"{us10y.change_bp:+.1f}bp" if us10y.change_bp is not None else "单日变动待核"
        out.append(_make_breaker(
            "us10y_breaker", "US",
            f"10年美债收益率触发熔断警报：{us10y.last:.3f}%（{change}）",
            f"实时监测显示美国10年期国债收益率报 {us10y.last:.3f}%（{change}），达到收益率或单日变动告警阈值。",
            92, "US10Y", us10y, z,
            "10年美债突破红线 → 全球长久期科技股与地产REITs估值重压 → 港股美元流动性收缩 + 黄金受实际利率挤压",
            "立刻切入超短美元/人民币货币盾防守，严禁抄底高估值科技股与长久期美债。",
        ))

    vix = quotes.get("b_VIX")
    if vix and not _is_stale_closed_tick(vix, "US", now_dt, market_calendar=market_calendar) and (vix.last >= 45.0 or vix.change_pct >= 22.0):
        z = _compute_anchor_z("b_VIX", vix, vol_baselines)
        out.append(_make_breaker(
            "vix_breaker", "US",
            f"VIX恐慌指数剧烈拉升至 {vix.last:.2f}（{vix.change_pct:+.2f}%）",
            f"实时标普隐含波动率 VIX 报 {vix.last:.2f}（{vix.change_pct:+.2f}%），触及跨市场波动率熔断警戒阈值。",
            90 if vix.last >= 45.0 else 78, "b_VIX", vix, z,
            "VIX飙升 → 欧美CTA与风险平价被动降仓 → 港美权益承压并伴随黄金流动性抛售风险",
            "波动率极值期禁止加杠杆与追单日反抽，等待VIX回落并确认收稳后再评估。",
        ))

    usdjpy = quotes.get("fx_susdjpy")
    if usdjpy and not _is_stale_closed_tick(usdjpy, "GLOBAL", now_dt, market_calendar=market_calendar) and usdjpy.change_pct <= -2.5:
        z = _compute_anchor_z("fx_susdjpy", usdjpy, vol_baselines)
        out.append(_make_breaker(
            "usdjpy_carry_breaker", "GLOBAL",
            f"美元/日元急跌 {usdjpy.change_pct:+.2f}%（报 {usdjpy.last:.2f}），警惕套息平仓",
            f"USD/JPY 盘中大跌 {usdjpy.change_pct:+.2f}%，触发全球日元套息交易（Carry Trade）强制平仓警报。",
            88, "fx_susdjpy", usdjpy, z,
            "日元急升 → 全球套息杠杆去化 → 日股/纳斯达克/港股科技同步面临流动性抛压",
            "套息平仓往往持续数日，暂不逆势接飞刀，严守各市红灯仓位上限。",
        ))

    # Core index >= 2.8 daily sigma & >= 2.5% live shock, consolidated to AT MOST 1 alert per region
    watch_map = (
        ("sh000001", "CN", "上证指数"),
        ("sh000300", "CN", "沪深300"),
        ("rt_hkHSI", "HK", "恒生指数"),
        ("rt_hkHSTECH", "HK", "恒生科技"),
        ("hf_ES", "US", "标普500期货"),
        ("hf_NQ", "US", "纳斯达克100期货"),
        ("hf_XAU", "GLOBAL", "伦敦现货黄金"),
        ("hf_OIL", "GLOBAL", "国际原油"),
    )
    by_region: dict[str, list[tuple[float, str, str, QuoteTick]]] = {}
    for sym, reg, cname in watch_map:
        tick = quotes.get(sym)
        if tick is None or abs(tick.change_pct) < 2.5 or _is_stale_closed_tick(tick, reg, now_dt, market_calendar=market_calendar):
            continue
        z = _compute_anchor_z(sym, tick, vol_baselines)
        if abs(z) < 2.8:
            continue
        by_region.setdefault(reg, []).append((z, sym, cname, tick))

    for reg, hits in by_region.items():
        hits.sort(key=lambda row: abs(row[0]), reverse=True)
        lead_z, lead_sym, lead_name, lead_tick = hits[0]
        score = 84 if abs(lead_z) >= 4.0 else 72
        direction = "急涨" if lead_tick.change_pct > 0 else "急跌"
        peers = "、".join(f"{cn}({tk.change_pct:+.2f}%)" for _, _, cn, tk in hits[1:])
        peer_note = f"；同区域共振：{peers}" if peers else ""
        sig = _make_breaker(
            f"shock_region_{reg.lower()}", reg,
            f"盘面剧震：{lead_name} 实时{direction} {lead_tick.change_pct:+.2f}%（{abs(lead_z):.1f}σ）",
            f"{lead_name} 最新报 {lead_tick.last:.2f}，单日变动 {lead_tick.change_pct:+.2f}%（日波动强度 {abs(lead_z):.1f}σ）{peer_note}，已触发实时盘面异动雷达。",
            score, lead_sym, lead_tick, lead_z,
            f"{lead_name} 剧烈波动 → 联动 A股/港股/美股与跨资产风险偏好重新定价",
            "盘面先于官方消息剧震时严禁盲目追涨杀跌，先核实官源公告并严守当前红绿灯纪律。",
        )
        sig.anchor_snapshots = [
            _anchor_snapshot(tk, z) for z, _, _, tk in hits
        ]
        out.append(sig)

    return out


class MonitorStateStore:
    """SQLite dedupe, 2-hour semantic cooldown, cross-poll cluster memory, escalation pierce & audit trail under .git/."""

    def __init__(self, db_path: Path | None = None, *, read_only: bool = False) -> None:
        self.db_path = db_path if db_path is not None else (_resolve_git_dir() / "realtime-monitor.sqlite3")
        _reject_repo_worktree_write(self.db_path, "state_db")
        self.lock_path = Path(f"{self.db_path}.lock")
        self._lock_fh: Any = None
        if read_only:
            self._conn = sqlite3.connect(":memory:")
            if self.db_path.is_file():
                uri = self.db_path.resolve().as_uri() + "?mode=ro"
                with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=10)) as existing:
                    existing.backup(self._conn)
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), timeout=10)
            try:
                os.chmod(self.db_path, 0o600)
            except OSError:
                pass
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen_items (
                item_hash TEXT PRIMARY KEY,
                first_seen_ts REAL NOT NULL,
                source TEXT,
                title TEXT
            );
            CREATE TABLE IF NOT EXISTS pending_news (
                item_hash TEXT PRIMARY KEY,
                expires_ts REAL NOT NULL,
                item_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recent_clusters (
                cluster_key TEXT PRIMARY KEY,
                domain_id TEXT NOT NULL,
                shingles_json TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                latest_ts REAL NOT NULL,
                is_official INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sent_clusters (
                cluster_key TEXT PRIMARY KEY,
                last_sent_ts REAL NOT NULL,
                last_score INTEGER NOT NULL,
                last_severity TEXT NOT NULL,
                last_max_z REAL NOT NULL,
                last_is_official INTEGER NOT NULL,
                sent_count INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS signal_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_ts REAL NOT NULL,
                created_cst TEXT NOT NULL,
                signal_id TEXT NOT NULL,
                cluster_key TEXT NOT NULL,
                severity TEXT NOT NULL,
                score INTEGER NOT NULL,
                domain_id TEXT NOT NULL,
                region TEXT NOT NULL,
                title TEXT NOT NULL,
                action TEXT NOT NULL,
                escalation_tag TEXT NOT NULL DEFAULT '',
                memo_md TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self._conn.commit()

    def acquire_lock(self) -> bool:
        self._lock_fh = self.lock_path.open("a+", encoding="utf-8")
        try:
            os.chmod(self.lock_path, 0o600)
        except OSError:
            pass
        try:
            fcntl.flock(self._lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            self._lock_fh.close()
            self._lock_fh = None
            return False

    def close(self) -> None:
        try:
            self._conn.close()
        finally:
            if self._lock_fh is not None:
                try:
                    fcntl.flock(self._lock_fh, fcntl.LOCK_UN)
                finally:
                    self._lock_fh.close()
                    self._lock_fh = None

    def mark_and_filter_unseen(
        self, items: list[NewsItem], now_ts: float, *, persist: bool = True, retention_sec: int = 30 * 86400
    ) -> list[NewsItem]:
        """Remember and queue first-seen items together so a failed poll can be resumed."""
        unseen: list[NewsItem] = []
        with self._conn if persist else contextlib.nullcontext():
            if persist:
                cutoff = now_ts - retention_sec
                self._conn.execute("DELETE FROM seen_items WHERE first_seen_ts < ?", (cutoff,))
            for it in items:
                if not math.isfinite(it.published_ts) or it.published_ts > now_ts + NEWS_MAX_AGE_SEC:
                    continue
                h = _news_item_hash(it)
                row = self._conn.execute("SELECT 1 FROM seen_items WHERE item_hash = ?", (h,)).fetchone()
                if row is None:
                    unseen.append(it)
                    if persist:
                        self._conn.execute(
                            "INSERT OR IGNORE INTO seen_items(item_hash, first_seen_ts, source, title) VALUES (?, ?, ?, ?)",
                            (h, now_ts, it.source, it.title[:200]),
                        )
            if persist:
                self._queue_news(unseen, now_ts=now_ts)
        return unseen

    def resolve_recent_cluster(
        self,
        *,
        domain_id: str,
        shingles: set[str],
        sources: list[str],
        is_official: bool,
        default_cluster_key: str,
        now_ts: float,
        ttl_sec: int = 7200,
        persist: bool = True,
    ) -> tuple[str, list[str], bool]:
        """Match active 2h cluster by (domain_id, Jaccard >= 0.35) to preserve immutable cluster_key & merge cross-poll sources."""
        cutoff = now_ts - ttl_sec
        if persist:
            self._conn.execute("DELETE FROM recent_clusters WHERE latest_ts < ?", (cutoff,))
        rows = self._conn.execute(
            "SELECT * FROM recent_clusters WHERE domain_id = ? AND latest_ts >= ?",
            (domain_id, cutoff),
        ).fetchall()
        for r in rows:
            try:
                old_shingles = set(json.loads(r["shingles_json"]))
                old_sources = list(json.loads(r["sources_json"]))
            except Exception:
                continue
            if _jaccard(shingles, old_shingles) >= 0.35:
                ckey = str(r["cluster_key"])
                merged_sources = sorted(set(old_sources) | set(sources))
                merged_shingles = sorted(old_shingles | shingles)[:120]
                merged_official = bool(r["is_official"]) or is_official
                if persist:
                    self._conn.execute(
                        "UPDATE recent_clusters SET shingles_json = ?, sources_json = ?, latest_ts = ?, is_official = ? WHERE cluster_key = ?",
                        (json.dumps(merged_shingles, ensure_ascii=False), json.dumps(merged_sources, ensure_ascii=False), now_ts, 1 if merged_official else 0, ckey),
                    )
                    self._conn.commit()
                return ckey, merged_sources, merged_official

        if persist:
            self._conn.execute(
                "INSERT OR REPLACE INTO recent_clusters(cluster_key, domain_id, shingles_json, sources_json, latest_ts, is_official) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    default_cluster_key,
                    domain_id,
                    json.dumps(sorted(shingles)[:120], ensure_ascii=False),
                    json.dumps(sorted(set(sources)), ensure_ascii=False),
                    now_ts,
                    1 if is_official else 0,
                ),
            )
            self._conn.commit()
        return default_cluster_key, sorted(set(sources)), is_official

    def pending_news(self, now_ts: float, *, persist: bool = True) -> list[NewsItem]:
        """Read fresh news awaiting scoring or delivery even if it left the feed."""
        if persist:
            with self._conn:
                self._conn.execute("DELETE FROM pending_news WHERE expires_ts < ?", (now_ts,))
        return [
            NewsItem(**json.loads(row["item_json"])) for row in self._conn.execute(
                "SELECT item_json FROM pending_news WHERE expires_ts >= ?", (now_ts,),
            )
        ]

    def _queue_news(self, items: list[NewsItem], *, now_ts: float) -> None:
        for item in items:
            expires_ts = item.published_ts + NEWS_MAX_AGE_SEC
            if item.date_only:
                day = datetime.fromtimestamp(item.published_ts, CST)
                expires_ts = (day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp() - 1
            if expires_ts < now_ts:
                continue
            self._conn.execute(
                "INSERT OR REPLACE INTO pending_news VALUES (?, ?, ?)",
                (_news_item_hash(item), expires_ts, json.dumps(dataclasses.asdict(item), ensure_ascii=False)),
            )

    def _delete_pending_news(self, item_hashes: list[str] | set[str]) -> None:
        self._conn.executemany("DELETE FROM pending_news WHERE item_hash = ?", ((h,) for h in item_hashes))

    def acknowledge_unalerted_news(self, item_hashes: set[str]) -> None:
        """Confirm items that finished scoring without a signal to record."""
        with self._conn:
            self._delete_pending_news(item_hashes)

    def failed_delivery_attempts(self, cluster_key: str, *, since_ts: float) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM signal_audit
            WHERE cluster_key = ? AND action = 'delivery_failed' AND created_ts >= ?
            """,
            (cluster_key, since_ts),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def seen_items_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS cnt FROM seen_items").fetchone()
        return int(row["cnt"]) if row else 0

    def _domain_p1_in_cooldown(self, domain_id: str, now_ts: float, domain_cooldown_sec: int) -> bool:
        if domain_cooldown_sec <= 0 or domain_id in ("crisis_breaker", "calendar_prealert"):
            return False
        cutoff = now_ts - domain_cooldown_sec
        row = self._conn.execute(
            """
            SELECT 1 FROM signal_audit
            WHERE domain_id = ? AND severity = 'P1'
              AND action IN ('dispatched', 'dry_run_dispatch')
              AND created_ts >= ?
            LIMIT 1
            """,
            (domain_id, cutoff),
        ).fetchone()
        return row is not None

    def _p1_sent_today(self, now_cst: datetime) -> int:
        day_prefix = now_cst.strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM signal_audit WHERE severity = 'P1' AND action IN ('dispatched', 'dry_run_dispatch') AND created_cst LIKE ?",
            (f"{day_prefix}%",),
        ).fetchone()
        return int(row["cnt"]) if row else 0

    def evaluate_dispatch(
        self,
        signal: ScoredSignal,
        now_cst: datetime,
        *,
        in_calendar_p0_window: bool = False,
        cooldown_sec: int = 7200,
        domain_cooldown_sec: int = 1800,
        p1_daily_cap: int = 6,
        quiet_enabled: bool = True,
        quiet_start: str = "23:30",
        quiet_end: str = "07:15",
    ) -> tuple[bool, str]:
        """Return (should_send, decision_reason). Mutates signal.escalation_tag on pierce."""
        if signal.severity == "SILENT":
            return False, "ignored_silent"
        if signal.severity == "P2":
            return False, "recorded_p2"

        now_dt = now_cst.astimezone(CST) if now_cst.tzinfo else now_cst.replace(tzinfo=CST)
        now_ts = now_dt.timestamp()

        # Quiet hours (defaults 23:30-07:15 CST, honors notify.json override; P0 & exact calendar P0 window bypass)
        in_quiet = quiet_enabled and _is_in_quiet_window(now_dt, quiet_start, quiet_end)
        if in_quiet and signal.severity != "P0" and not in_calendar_p0_window:
            return False, "suppressed_quiet"

        # 2-hour semantic cooldown (24h for calendar_prealert) with escalation pierce
        eff_cooldown = 86400 if signal.domain_id == "calendar_prealert" else cooldown_sec
        row = self._conn.execute(
            "SELECT * FROM sent_clusters WHERE cluster_key = ?", (signal.cluster_key,)
        ).fetchone()
        if row is not None:
            elapsed = now_ts - float(row["last_sent_ts"])
            if elapsed < eff_cooldown:
                auth_upgraded = (int(row["last_is_official"]) == 0) and signal.is_official
                sev_upgraded = (str(row["last_severity"]) == "P1") and (signal.severity == "P0")
                vol_widened = (elapsed >= 900) and ((signal.max_z - float(row["last_max_z"])) >= 1.5)
                if auth_upgraded or sev_upgraded or vol_widened:
                    signal.escalation_tag = "【进展升级】"
                else:
                    return False, "suppressed_cooldown"

        if signal.severity == "P1" and not signal.escalation_tag and self._domain_p1_in_cooldown(signal.domain_id, now_ts, domain_cooldown_sec):
            return False, "suppressed_domain_cooldown"

        if signal.severity == "P1" and self._p1_sent_today(now_dt) >= p1_daily_cap:
            return False, "suppressed_daily_cap"

        return True, "dispatched"

    def record_signal(
        self, signal: ScoredSignal, action: str, now_cst: datetime, *, retry_news: list[NewsItem] | None = None,
    ) -> None:
        with self._conn:
            self._insert_signal(signal, action, now_cst)
            self._delete_pending_news(signal.item_hashes)
            if retry_news:
                retry_time = now_cst if now_cst.tzinfo else now_cst.replace(tzinfo=CST)
                self._queue_news(retry_news, now_ts=retry_time.timestamp())

    def _insert_signal(self, signal: ScoredSignal, action: str, now_cst: datetime) -> None:
        now_dt = now_cst.astimezone(CST) if now_cst.tzinfo else now_cst.replace(tzinfo=CST)
        now_ts = now_dt.timestamp()
        if action == "no_provider_configured" and self._conn.execute(
            "SELECT 1 FROM signal_audit WHERE cluster_key = ? AND action = ? AND created_ts >= ? LIMIT 1",
            (signal.cluster_key, action, now_ts - 7200),
        ).fetchone():
            return
        self._conn.execute(
            """
            INSERT INTO signal_audit(
                created_ts, created_cst, signal_id, cluster_key, severity, score,
                domain_id, region, title, action, escalation_tag, memo_md
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_ts,
                now_dt.isoformat(timespec="seconds"),
                signal.signal_id,
                signal.cluster_key,
                signal.severity,
                signal.score,
                signal.domain_id,
                signal.region,
                signal.title[:240],
                action,
                signal.escalation_tag,
                signal.memo_md,
            ),
        )
        if action in ("dispatched", "dry_run_dispatch"):
            self._conn.execute(
                """
                INSERT INTO sent_clusters(cluster_key, last_sent_ts, last_score, last_severity, last_max_z, last_is_official, sent_count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(cluster_key) DO UPDATE SET
                    last_sent_ts = excluded.last_sent_ts,
                    last_score = excluded.last_score,
                    last_severity = excluded.last_severity,
                    last_max_z = excluded.last_max_z,
                    last_is_official = excluded.last_is_official,
                    sent_count = sent_clusters.sent_count + 1
                """,
                (signal.cluster_key, now_ts, signal.score, signal.severity, signal.max_z, 1 if signal.is_official else 0),
            )

    def export_recent_signals(self, hours: int = 24, *, now_ts: float | None = None) -> list[dict[str, Any]]:
        cutoff = (now_ts if now_ts is not None else time.time()) - hours * 3600
        rows = self._conn.execute(
            """
            SELECT created_cst, signal_id, cluster_key, severity, score, domain_id, region, title, action, escalation_tag
            FROM signal_audit
            WHERE created_ts >= ? AND severity IN ('P0', 'P1', 'P2')
            ORDER BY created_ts DESC
            LIMIT 100
            """,
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]


def _sanitize_unnegated_matches(
    text: str, pattern: re.Pattern[str], replacement: str
) -> str:
    """Replace only matches whose immediately preceding clause (within sentence/comma boundary) is NOT negated."""
    def _repl(m: re.Match[str]) -> str:
        prefix = text[: m.start()]
        clause = _CLAUSE_SPLIT_RE.split(prefix)[-1][-24:]
        if _GOLD_NEGATION_RE.search(clause):
            return m.group(0)
        return replacement

    return pattern.sub(_repl, text)


def enforce_safety_gates(text: str, ssot: dict[str, Any], *, append_footer: bool = True) -> str:
    """Hard compliance filter: Gold Tier-0 red-light mutex + PBOC Doc No. 42 crypto firewall (per-clause negation)."""
    out = str(text or "")
    gold_locked = bool(ssot.get("gold_locked", True))

    if gold_locked:
        out = _sanitize_unnegated_matches(
            out, _GOLD_ACTIVE_BUY_RE, "严禁新买黄金（黄金红灯停锁生效，新仓 0%）"
        )
        if append_footer and "黄金红灯锁" not in out:
            out = (
                out.rstrip()
                + f"\n\n> 🔒 **黄金红灯锁同步（{ssot.get('gold_tier_label', '红灯停 · 新仓 0%')}）**："
                "黄金当前新仓 0%，严禁以任何突发消息为由主动新买或加仓黄金/金矿股。"
            )

    out = _sanitize_unnegated_matches(
        out, _CRYPTO_BUY_RE, "严禁境内配仓虚拟货币（遵照央行银发〔2026〕42号，0%配仓）"
    )
    return out


_TRANSMISSION_HYPOTHESES = {
    "funding": "若短期融资成本随消息变化，可能进一步影响借贷和资产估值。可对照短端利率与成交量判断。",
    "earnings": "若消息改变企业订单、成本或信贷条件，影响可能通过盈利预期传导。可对照行业成交与盈利预期。",
    "currency": "若汇率反应持续，可能通过外币融资成本和本币折算影响不同市场。可对照汇率与相关资产的同向变化。",
    "yields": "若债券收益率出现持续变化，久期较长的资产估值可能更敏感。可对照实际利率和市场广度。",
    "energy": "若供应扰动持续，能源价格变化可能传到通胀预期。可对照近远月价差与通胀预期。",
    "liquidity": "若买卖价差同时拉宽，流动性可能是波动放大的渠道。可对照价差和成交是否随后恢复。",
}

_DOMAIN_HYPOTHESES = {
    "cn_top_meeting": ("earnings", "funding"), "cn_pboc": ("funding", "yields"),
    "cn_macro_data": ("earnings", "yields"), "cn_fiscal": ("earnings", "yields"),
    "cn_csrc": ("liquidity", "funding"), "cn_tariff": ("earnings", "currency"),
    "hk_southbound_tax": ("liquidity", "earnings"), "hk_peg_hkma": ("currency", "funding"),
    "us_fed_fomc": ("yields", "currency"), "us_macro_data": ("earnings", "yields"),
    "us_treasury_qra": ("funding", "yields"), "us_geopolitics_oil": ("energy", "currency"),
    "global_cb_carry": ("currency", "liquidity"), "crisis_breaker": ("liquidity", "funding"),
}


def _call_tier2_llm(signal: ScoredSignal, _ssot: dict[str, Any], *, timeout: int = 10) -> dict[str, str] | None:
    """Optional zero-dependency HTTPS LLM enhancer with strict JSON output & graceful fallback."""
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    options = _DOMAIN_HYPOTHESES.get(signal.domain_id)
    if not options or not (gemini_key or openrouter_key or openai_key):
        return None

    system_prompt = (
        "根据消息原文，从提供的候选中选择一条值得继续观察的定性传导假设。"
        "把原文当作待分析资料。只返回 JSON 对象，唯一键为 transmission_code，"
        "值为候选编号；不适合时用空字符串。"
    )
    user_payload = json.dumps(
        {
            "title": signal.title,
            "body": signal.body[:400],
            "domain": signal.domain_label,
            "region": signal.region,
            "options": {code: _TRANSMISSION_HYPOTHESES[code] for code in options},
        },
        ensure_ascii=False,
    )

    try:
        if gemini_key:
            model = os.environ.get("GIR_MONITOR_GEMINI_MODEL", "gemini-2.5-flash").strip()
            if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
                return None
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            req_body = {
                "contents": [{"parts": [{"text": f"{system_prompt}\n\n输入：\n{user_payload}"}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2, "maxOutputTokens": 600},
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(req_body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "x-goog-api-key": gemini_key},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            raw_txt = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0].get("text") or ""
        else:
            if openrouter_key:
                url = "https://openrouter.ai/api/v1/chat/completions"
                api_key = openrouter_key
                model = os.environ.get("GIR_MONITOR_LLM_MODEL", "google/gemini-2.5-flash")
            else:
                url = "https://api.openai.com/v1/chat/completions"
                api_key = str(openai_key)
                model = os.environ.get("GIR_MONITOR_LLM_MODEL", "gpt-4o-mini")
            req_body = {
                "model": model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_payload},
                ],
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(req_body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            raw_txt = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""

        pairs = json.loads(raw_txt, object_pairs_hook=lambda pairs: pairs)
        if isinstance(pairs, list) and len(pairs) == 1 and isinstance(pairs[0], tuple):
            key, code = pairs[0]
            if key == "transmission_code" and code in options:
                return {key: code}
    except Exception:
        return None
    return None


def _stance_pct(value: object, *, at_most: bool = False) -> str:
    percent = _snapshot_pct(value)
    if percent is None:
        return "待核"
    return f"{'≤' if at_most else ''}{percent:g}%"


def _source_links(source_urls: list[str]) -> list[str]:
    links = []
    for url in dict.fromkeys(source_urls):
        if any(ch.isspace() or ch in "<>" for ch in url):
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None:
                continue
        except ValueError:
            continue
        target = url.replace("(", "%28").replace(")", "%29")
        links.append(f"[来源 {len(links) + 1}]({target})")
    return links


def _plain_markdown(raw: str) -> str:
    # The quote is preserved as text even if the source contains Markdown or HTML.
    return re.sub(r"([\\`*{}\[\]_~])", r"\\\1", html.escape(raw, quote=False))


def interpret_and_render_memo(
    signal: ScoredSignal,
    ssot: dict[str, Any],
    *,
    now_cst: datetime,
    enable_llm: bool = False,
    llm_fn: Callable[[ScoredSignal, dict[str, Any]], dict[str, str] | None] | None = None,
) -> tuple[str, str]:
    """Render 5-section prudent WeChat Action Memo (Tier-1 deterministic + optional Tier-2 LLM) + hard safety gates."""
    sev_badge = "🔴【一级强信号】" if signal.severity == "P0" else "🟠【二级重要信号】"
    prefix = f"{sev_badge}{signal.escalation_tag}"
    if signal.is_flash_unverified:
        prefix += "⚠️【盘面剧震·待官方核实】"
    alert_title = f"{prefix} {signal.domain_label}：{_plain_markdown(signal.title[:48])}"

    # Anchor lines
    if signal.anchor_snapshots:
        anchor_parts = []
        for a in signal.anchor_snapshots[:5]:
            score_note = f"，{a['z']:+.1f}σ" if a.get("z") is not None else ""
            if a.get("is_yield") and a.get("change_bp") is not None:
                value = f"{a['last']:.3f}%（{a['change_bp']:+.1f}bp{score_note}）"
            else:
                value = f"{a['last']:.2f}（{a['change_pct']:+.2f}%{score_note}）"
            if a.get("observed_at_cst"):
                observed = datetime.fromisoformat(a["observed_at_cst"]).strftime("%Y-%m-%d %H:%M:%S 北京时间")
            elif a.get("reported_clock"):
                observed = f"原报 {a['reported_clock']}，日期未核，仅作参考"
            else:
                observed = "观测时间待核"
            anchor_parts.append(f"{a['name']} {value} · {a.get('source') or '来源待核'} · {observed}")
        anchor_text = "；".join(anchor_parts)
    elif signal.is_market_closed_floor:
        anchor_text = "当前处于目标市场休市时段（已启用官源保底确认），待开盘/夜期首笔实盘验证。"
    else:
        anchor_text = "暂未捕捉到显著跨市场共振异动，以官方原文为准。"

    # Default Tier-1 prudent stances tailored to region + SSOT lamps
    if signal.region == "CN":
        stance_cap = f"A股当前【{ssot.get('a_lamp') or '灯号待核'}】，总股票仓位严守 {_stance_pct(ssot.get('a_cap_pct'), at_most=True)}"
        threshold = ssot.get("a_fomo")
    elif signal.region == "HK":
        stance_cap = (
            f"港股当前【{ssot.get('hk_lamp') or '灯号待核'}】，"
            f"离岸权益 {_stance_pct(ssot.get('hk_offshore_cap_pct'), at_most=True)}、"
            f"港股通 {_stance_pct(ssot.get('hk_onshore_cap_pct'), at_most=True)}"
        )
        threshold = ssot.get("hk_fomo")
    elif signal.region == "US":
        stance_cap = (
            f"美股当前【{ssot.get('us_lamp') or '灯号待核'}】，"
            f"权益防弹衣 {_stance_pct(ssot.get('us_cap_pct'), at_most=True)} + "
            f"超短美债 {_stance_pct(ssot.get('us_cash_pct'))}"
        )
        threshold = ssot.get("us_fomo")
    else:
        stance_cap = (
            f"当前三市权益仓位上限（A股{_stance_pct(ssot.get('a_cap_pct'), at_most=True)} / "
            f"港股通{_stance_pct(ssot.get('hk_onshore_cap_pct'), at_most=True)} / "
            f"美股{_stance_pct(ssot.get('us_cap_pct'), at_most=True)}），"
            f"黄金【{ssot.get('gold_tier_label') or '灯号待核'}】"
        )
        threshold = None
    stance_cap += f"。转强线：{threshold}。" if threshold else "。"

    obs_advice = f"不凭单条突发消息追涨杀跌，保持现钞/短债流动性，{stance_cap}"
    holder_advice = "对照自身仓位是否超出当前红灯上限：超限部分借脉冲分批降险，未超限则按原计划持有核心红利/防弹衣底仓，严禁盲目加杠杆。"
    if signal.is_divergence:
        obs_advice = "⚠️ 盘面已出现「消息与走势背离（警惕买预期卖事实）」，空仓/观望者严禁追高接盘。" + stance_cap
    if signal.is_flash_unverified:
        obs_advice = "⚠️ 当前为单源未证实消息叠加盘面剧震，空仓/观望者一律按兵不动，等待官方原文确认后再决策。"

    summary_txt = _plain_markdown(signal.body[:280])
    trans_txt = signal.transmission_chain
    falsify_txt = signal.guardrail
    tier_used = "tier1_deterministic"

    options = _DOMAIN_HYPOTHESES.get(signal.domain_id, ())
    if enable_llm and options and signal.severity in ("P0", "P1") and signal.k_verify >= 1.0:
        try:
            llm_res = (llm_fn or _call_tier2_llm)(signal, ssot)
        except Exception:
            llm_res = None
        if isinstance(llm_res, dict) and set(llm_res) == {"transmission_code"}:
            code = llm_res["transmission_code"]
            if code in options:
                trans_txt += f"\n\n- **辅助假设（待验证）**：{_TRANSMISSION_HYPOTHESES[code]}"
                tier_used = "tier2_llm"

    next_ev = find_next_calendar_event(ssot.get("events") or [], signal.region, now_cst)
    next_ev_line = (
        f"下一关键日历：{next_ev.get('date_cst')} {next_ev.get('time_cst', '')} · {next_ev.get('title')}"
        if next_ev
        else "下一关键日历：请查看门户《未来14–30天财经与政策前瞻日历》。"
    )

    links = _source_links(signal.source_urls)
    if signal.is_market_first:
        verify_tag = "行情数据"
    elif signal.is_official:
        verify_tag = "官源消息"
    else:
        verify_tag = "多家平台报道，原始出处待核" if signal.k_verify >= 1.0 else "单源待官方核实"
    source_line = f"- **来源与时间**：{', '.join(signal.sources)} · {signal.published_cst}"
    if links:
        source_line += " · " + " ".join(links)
    body_md = "\n".join(
        [
            f"- **综合评分**：{signal.score}/100（权威 {signal.s_auth} + 盘面 {signal.s_confirm} + 传导 {signal.s_spillover} · {verify_tag}）",
            source_line,
            "",
            "### ① 消息原文摘录",
            summary_txt,
            "",
            "### ② 实时盘面验证（多锚点共振）",
            anchor_text,
            "",
            "### ③ 跨市场传导（待验证）",
            trans_txt,
            "",
            "### ④ 审慎操作建议（严守当前红绿灯纪律）",
            f"- **观望者/空仓者**：{obs_advice}",
            f"- **已有持仓者**：{holder_advice}",
            "",
            "### ⑤ 反向证伪红线与下一关键时间点",
            f"- **防错红线**：{falsify_txt}",
            f"- **{next_ev_line}**",
        ]
    )

    alert_title = enforce_safety_gates(alert_title, ssot, append_footer=False)
    body_md = enforce_safety_gates(body_md, ssot, append_footer=True)
    signal.memo_md = body_md
    signal.interpreter_tier = tier_used
    return alert_title, body_md


def render_launchd_plist(
    *,
    python_bin: str | None = None,
    enable_llm: bool = False,
    label: str = "com.global-investment-research.realtime-monitor",
    env_vars: dict[str, str] | None = None,
    data_root: Path | None = None,
    state_db: Path | None = None,
    notify_config_path: Path | None = None,
) -> str:
    """Render a valid macOS LaunchAgent plist for background real-time monitoring."""
    py = python_bin or sys.executable or "/usr/bin/python3"
    script = str(Path(__file__).resolve())
    log_dir = str(Path.home() / "Library" / "Logs" / "global-investment-research")
    program_args = [py, script, "--daemon"]
    if enable_llm:
        program_args.append("--enable-llm")
    for flag, path in (("--data-root", data_root), ("--state-db", state_db), ("--notify-config", notify_config_path)):
        if path is not None:
            program_args.extend((flag, str(path.expanduser().absolute())))
    args_block = "\n".join(f"    <string>{html.escape(arg)}</string>" for arg in program_args)

    # Propagate safe runtime & proxy vars (never secrets) so launchd matches interactive network reachability.
    if env_vars is None:
        effective_env: dict[str, str] = {"PYTHONUTF8": "1"}
        for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
            v = os.environ.get(k, "").strip()
            if v:
                effective_env[k] = v
    else:
        effective_env = {str(k): str(v) for k, v in env_vars.items() if str(k).strip()}

    env_lines: list[str] = []
    if effective_env:
        env_lines.append("  <key>EnvironmentVariables</key>")
        env_lines.append("  <dict>")
        for k, v in sorted(effective_env.items()):
            env_lines.append(f"    <key>{html.escape(k)}</key><string>{html.escape(v)}</string>")
        env_lines.append("  </dict>")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        "<dict>",
        f"  <key>Label</key><string>{html.escape(label)}</string>",
        "  <key>ProgramArguments</key>",
        "  <array>",
        args_block,
        "  </array>",
        f"  <key>WorkingDirectory</key><string>{html.escape(str(REPO_ROOT))}</string>",
        *env_lines,
        "  <key>RunAtLoad</key><true/>",
        "  <key>KeepAlive</key><true/>",
        "  <key>ThrottleInterval</key><integer>30</integer>",
        f"  <key>StandardOutPath</key><string>{html.escape(log_dir)}/monitor.out.log</string>",
        f"  <key>StandardErrorPath</key><string>{html.escape(log_dir)}/monitor.err.log</string>",
        "</dict>",
        "</plist>",
        "",
    ]
    return "\n".join(lines)


def run_doctor(
    *, notify_config_path: Path | None = None, state_db: Path | None = None, data_root: Path | None = None,
) -> dict[str, Any]:
    """One-shot diagnostic of SSOT health, Gold Tier-0 lock, vol baselines, calendar P0 window, LLM env & WeChat channels."""
    now_dt = datetime.now(CST)
    root, ssot, vols = _load_monitor_inputs(data_root)
    events = ssot.get("events") or []
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import wechat_notify  # type: ignore

    cfg = wechat_notify.load_notify_config(config_path=notify_config_path)
    llm_ready = [
        k for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY")
        if os.environ.get(k, "").strip()
    ]
    db_target = state_db if state_db is not None else (_resolve_git_dir() / "realtime-monitor.sqlite3")
    return {
        "timestamp_cst": now_dt.isoformat(timespec="seconds"),
        "data_root": str(root),
        "ssot": {
            "edition_id": ssot["edition_id"],
            "gold_locked": ssot["gold_locked"],
            "gold_tier_label": ssot["gold_tier_label"],
            "a_cap_pct": ssot["a_cap_pct"],
            "hk_onshore_cap_pct": ssot["hk_onshore_cap_pct"],
            "us_cap_pct": ssot["us_cap_pct"],
            "policy_events_loaded": len(events),
            "in_calendar_p0_window": is_in_calendar_p0_window(
                events,
                now_dt,
                quiet_enabled=cfg.quiet_enabled,
                quiet_start=cfg.quiet_start,
                quiet_end=cfg.quiet_end,
            ),
        },
        "vol_baselines_loaded": len(vols),
        "feed_sources_count": len(FEED_SOURCES),
        "state_db": str(db_target),
        "tier2_llm": {
            "enabled_by_env": os.environ.get("GIR_MONITOR_LLM", "").strip() == "1",
            "keys_present": llm_ready,
            "note": "Pass --enable-llm or set GIR_MONITOR_LLM=1 to activate Tier-2 LLM on P0/P1 signals.",
        },
        "notify": wechat_notify.run_doctor(cfg),
    }


def run_once(
    *,
    store: MonitorStateStore,
    dry_run: bool = False,
    enable_llm: bool = False,
    sources_filter: set[str] | None = None,
    notify_config_path: Path | None = None,
    data_root: Path | None = None,
    now_cst: datetime | None = None,
) -> dict[str, Any]:
    """Execute one full poll -> score -> cooldown -> interpret -> notify cycle (dry_run never mutates production dedupe)."""
    now_dt = now_cst if now_cst is not None else datetime.now(CST)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=CST)
    else:
        now_dt = now_dt.astimezone(CST)

    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import wechat_notify  # type: ignore

    _, ssot, vol_baselines = _load_monitor_inputs(data_root)
    cfg = wechat_notify.load_notify_config(config_path=notify_config_path)
    notifier = wechat_notify.Notifier(cfg, dry_run=dry_run, now_fn=lambda: now_dt)
    use_llm = enable_llm and not dry_run and notifier.has_ready_provider()

    events = ssot.get("events") or []
    mcal = ssot.get("market_calendar")
    in_p0_win = is_in_calendar_p0_window(
        events,
        now_dt,
        quiet_enabled=cfg.quiet_enabled,
        quiet_start=cfg.quiet_start,
        quiet_end=cfg.quiet_end,
    )

    now_ts = now_dt.timestamp()
    raw_items, feed_errors = poll_all_feeds(sources_filter=sources_filter, now_ts=now_ts)
    cold_start_bootstrap = (store.seen_items_count() == 0)
    pending = [
        item for item in store.pending_news(now_ts, persist=not dry_run)
        if sources_filter is None or item.source in sources_filter
    ]
    unseen_items = store.mark_and_filter_unseen(raw_items, now_ts, persist=not dry_run)
    quotes, quote_errors = poll_live_quotes(now_cst=now_dt)
    # Sources can publish while the poll is running. Keep those items queued
    # until a poll cutoff reaches their timestamp.
    news_by_hash = {
        _news_item_hash(item): item for item in pending + unseen_items if item.published_ts <= now_ts
    }
    news_signals = classify_and_score(
        list(news_by_hash.values()),
        quotes,
        vol_baselines,
        now_cst=now_dt,
        market_calendar=mcal,
        state_store=store,
        persist_clusters=not dry_run,
    )
    if not dry_run:
        signal_hashes = {h for signal in news_signals if signal.severity != "SILENT" for h in signal.item_hashes}
        store.acknowledge_unalerted_news(news_by_hash.keys() - signal_hashes)
    cal_signals = detect_upcoming_calendar_alerts(events, now_cst=now_dt)
    market_signals = detect_market_first_anomalies(
        quotes, vol_baselines, now_cst=now_dt, market_calendar=mcal
    )
    # Suppress regional shock_* duplicate if a P0/P1 news signal already covers that region in this cycle
    news_regions_hot = {s.region for s in news_signals if s.severity in ("P0", "P1")}
    filtered_market = [
        s for s in market_signals
        if not (s.cluster_key.startswith("market_first:shock_region_") and s.region in news_regions_hot)
    ]
    all_signals = sorted(news_signals + cal_signals + filtered_market, key=lambda s: s.score, reverse=True)

    dispatched: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    domains_dispatched_p1: set[str] = set()
    sent_or_previewed = 0
    for sig in all_signals:
        should_send, reason = store.evaluate_dispatch(
            sig,
            now_dt,
            in_calendar_p0_window=in_p0_win,
            quiet_enabled=cfg.quiet_enabled,
            quiet_start=cfg.quiet_start,
            quiet_end=cfg.quiet_end,
        )
        if should_send and cold_start_bootstrap and sent_or_previewed >= 2:
            should_send, reason = False, "suppressed_cold_start"
        if (
            should_send
            and sig.severity == "P1"
            and sig.domain_id not in ("crisis_breaker", "calendar_prealert")
            and sig.domain_id in domains_dispatched_p1
        ):
            should_send, reason = False, "suppressed_domain_cooldown"
        if should_send:
            alert_title, memo_md = interpret_and_render_memo(
                sig, ssot, now_cst=now_dt, enable_llm=use_llm,
            )
            msg = wechat_notify.AlertMessage(
                title=alert_title,
                body_md=memo_md,
                severity=sig.severity,
                category=sig.domain_id,
                url=f"{DEFAULT_PORTAL_URL}#sec-policy-calendar",
                dedupe_key=sig.cluster_key,
                bypass_quiet_hours=(sig.severity == "P0" or in_p0_win),
            )
            results = notifier.send(msg)
            if dry_run:
                action = "dry_run_dispatch"
            elif not results:
                action = "no_provider_configured"
            elif any(r.status == "sent" for r in results):
                action = "dispatched"
            else:
                action = "delivery_failed"
            if not dry_run:
                # Missing routes do not spend the delivery retry budget. Reassess
                # the same source items while fresh, even after they leave the feeds.
                retry = action == "no_provider_configured" or (
                    action == "delivery_failed" and store.failed_delivery_attempts(
                        sig.cluster_key, since_ts=now_ts - 7200,
                    ) < 2
                )
                retry_news = [news_by_hash[h] for h in sig.item_hashes] if retry else None
                store.record_signal(sig, action, now_dt, retry_news=retry_news)
            if action in ("dispatched", "dry_run_dispatch"):
                sent_or_previewed += 1
                if sig.severity == "P1":
                    domains_dispatched_p1.add(sig.domain_id)
            dispatched.append(
                {
                    "severity": sig.severity,
                    "score": sig.score,
                    "domain_id": sig.domain_id,
                    "title": alert_title,
                    "action": action,
                    "interpreter_tier": sig.interpreter_tier,
                    "delivery": [dataclasses.asdict(r) for r in results],
                }
            )
        elif sig.severity in ("P0", "P1", "P2"):
            if not dry_run:
                store.record_signal(sig, reason, now_dt)
            suppressed.append({"severity": sig.severity, "score": sig.score, "domain_id": sig.domain_id, "title": sig.title, "reason": reason})

    return {
        "timestamp_cst": now_dt.isoformat(timespec="seconds"),
        "edition_id": ssot["edition_id"],
        "gold_locked": ssot["gold_locked"],
        "in_calendar_p0_window": in_p0_win,
        "in_market_session": any(
            is_region_market_open(region, now_dt, market_calendar=mcal) for region in ("CN", "HK", "US")
        ),
        "feeds_fetched": len(raw_items),
        "feeds_unseen": len(unseen_items),
        "retry_news_count": len(pending),
        "feed_errors_count": len(feed_errors),
        "feed_errors": feed_errors,
        "quotes_fetched": len(quotes),
        "quote_errors": quote_errors,
        "signals_scored": len(all_signals),
        "dispatched_count": len(dispatched),
        "dispatched": dispatched,
        "suppressed_count": len(suppressed),
        "suppressed_preview": suppressed[:8],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Real-time market, policy & geopolitical news monitor with compliant WeChat alerts.")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run one poll->score->notify cycle and exit.")
    mode.add_argument("--daemon", action="store_true", help="Run continuously with adaptive polling cadence.")
    mode.add_argument("--doctor", action="store_true", help="Inspect SSOT, Gold red-light lock, vol baselines & WeChat notifier health.")
    mode.add_argument("--print-launchd", action="store_true", help="Print a valid macOS LaunchAgent XML plist and exit.")
    p.add_argument("--dry-run", action="store_true", help="Poll live sources without external AI, notifications, or production state writes.")
    p.add_argument("--enable-llm", action="store_true", help="Enable optional Tier-2 LLM interpreter for P0/P1 signals.")
    p.add_argument("--export-digest", type=Path, default=None, help="Export last 24h P0/P1/P2 audit digest JSON to path (outside repo worktree).")
    p.add_argument("--state-db", type=Path, default=None, help="Custom SQLite path (default .git/realtime-monitor.sqlite3; outside repo worktree).")
    p.add_argument("--data-root", type=Path, default=None, help="Read a separate validated snapshot tree instead of the source checkout.")
    p.add_argument("--sources", default=None, help="Comma-separated feed source subset (e.g. sina_724,wscn_global,gov_yaowen).")
    p.add_argument("--notify-config", type=Path, default=None, help="External notify.json path.")
    p.add_argument("--active-interval", type=int, default=180, help="Daemon poll interval in seconds during active/P0 windows (default 180).")
    p.add_argument("--quiet-interval", type=int, default=600, help="Daemon poll interval in seconds during quiet hours (default 600).")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    enable_llm = bool(args.enable_llm or os.environ.get("GIR_MONITOR_LLM", "").strip() == "1")

    if args.data_root is not None and not args.print_launchd:
        try:
            _monitor_data_root(args.data_root)
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 2

    if args.doctor:
        try:
            result = run_doctor(
                notify_config_path=args.notify_config, state_db=args.state_db, data_root=args.data_root,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.print_launchd:
        print(render_launchd_plist(
            enable_llm=enable_llm, data_root=args.data_root, state_db=args.state_db,
            notify_config_path=args.notify_config,
        ), end="")
        return 0

    store = MonitorStateStore(db_path=args.state_db, read_only=args.dry_run or args.export_digest is not None)
    if args.export_digest is not None:
        try:
            _reject_repo_worktree_write(args.export_digest, "export_digest")
            records = store.export_recent_signals(hours=24)
            args.export_digest.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "exported_at_cst": datetime.now(CST).isoformat(timespec="seconds"),
                "count": len(records),
                "signals": records,
            }
            args.export_digest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"exported": str(args.export_digest), "count": len(records)}, ensure_ascii=False))
            return 0
        finally:
            store.close()

    if not args.dry_run and not store.acquire_lock():
        print("[SKIP] Another realtime_monitor instance already holds the lock.", file=sys.stderr)
        store.close()
        return 0

    src_filter = {s.strip() for s in args.sources.split(",") if s.strip()} if args.sources else None
    try:
        if args.daemon:
            while True:
                now_dt = datetime.now(CST)
                try:
                    summary = run_once(
                        store=store,
                        dry_run=args.dry_run,
                        enable_llm=enable_llm,
                        sources_filter=src_filter,
                        notify_config_path=args.notify_config,
                        data_root=args.data_root,
                        now_cst=now_dt,
                    )
                    print(json.dumps(summary, ensure_ascii=False), flush=True)
                    in_active = summary["in_calendar_p0_window"] or summary["in_market_session"]
                    sleep_s = max(30, args.active_interval if in_active else args.quiet_interval)
                except Exception:
                    print(
                        f"[ERROR] realtime_monitor daemon cycle failed at {now_dt.isoformat(timespec='seconds')}:",
                        file=sys.stderr,
                    )
                    traceback.print_exc(file=sys.stderr)
                    sys.stderr.flush()
                    sleep_s = max(30, min(60, args.active_interval))
                time.sleep(sleep_s)
        else:
            summary = run_once(
                store=store,
                dry_run=args.dry_run,
                enable_llm=enable_llm,
                sources_filter=src_filter,
                notify_config_path=args.notify_config,
                data_root=args.data_root,
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
