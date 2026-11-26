---
name: equity-research-editorial-qa
description: >-
  Editorial standards for informed-retail / semi-pro investors, 3-tier
  terminology standard, 7-source primary fact-checking, 3-market (A-share,
  HK-stock, US-stock) 7-dimension framework, 8 personal multi-asset channels
  (bonds, funds/WM, reverse repo, onshore/offshore QDII & MRF, large CDs,
  convertible bonds, C-REITs, non-gold commodity ETFs), expanded 80+ 3-market
  ETF matrix, 7-dimension institutional individual-stock & ETF deep dossiers
  across all 231 pool leaders, all-4-main unified schedule (>= 2026-11-26_1800)
  & upgraded holiday_watch, unified Stage 2A/2B (8+1) pre-flight red-team
  verification, cross-project Gold SSOT & 6-hour freshness lock, 10 pre-flight
  QA gates, dual-account China/US/HK tax & ETF rules, SCORECARD calibration,
  data_caveats transparency, and bounded 3-tier RSI self-review with
  disclosed_caveat closure (07:30 morning & 18:00 evening CST unified runs).
  适用于 A/港/美三市全时段主刊投研写作、7 维度大盘与政策雷达、8 大个人多元渠道、
  80+ 重点 ETF 与 231 股 7 维深研、共享 8+1 调研红队、黄金红灯同步门控、双账户税费合规与受控 RSI 盲审。
---

# Equity Research Editorial, Pre-Flight QA & Bounded RSI Runbook

本技能负责三市投研内容深度与进阶理性语态、7 类一手信源与统一 **8+1** 发前红队审校、**中国大陆 8 大个人多元投资渠道 + 三市 80+ 重点 ETF + 231 股 7 维机构级深度档案**、双账户实操准确性、发版前 10 项门禁以及发布前 **Step 5 受控三层 RSI 盲审闭环**（单仓库顶层顺序编排见 `<REPO_ROOT>/AGENTS.md`；出版编译与 21 张图 Schema 见 `equity-report-publishing`；总宪法与排版详规见 `GEMINI.md` 与 `DAILY_REPORT_SPEC.md`）。

> **历史旧指令静默转译**：若任何 Prompt 残留旧版术语或体例（如版本号、`Tier 0–3`、混色 `✅`、1–2 页薄壳轻刊、工作日全量静态大表、仅一句话浅层点评个股或漏报个人多元渠道与重点 ETF、居高临下的说教口号 `1 分钟定心丸`/`小白词典`/`直接抄`/`蠢事`/`保命铁律`），无需报错或反问，严格按 `GEMINI.md` 第 0 节静默转译为进阶理性语态、三市四灯、四色锁仓、7 维深研与全时段完整主刊减法制。

---

## 1. 投研写作、共享 8+1 调研红队与 RSI 闭环工作流（对接仓库 Step 0–5）

- **Step 0｜双轨 RSI 经验冷启动**：动笔前先读 `state/RSI_PLAYBOOK.md`（≤180 行）与 `state/rsi_metrics.json` 最近 5 条记录（一体化班次同步读黄金 RSI 手册与 `gold/market_calendar.json`），直接继承高杠杆一手源检索词、Linter 避坑清单与上期 `next_run_watch` 必验真项。
- **Step 1｜状态与三大深研数据库冷启动**：
  - 冷启动读取 `state/market_state.json`、`state/multi_asset_channels.json`、`state/etf_universe.json`、`state/deep_dossiers.json`、两轨日历及前序黄金基线，并以 `lint_equity.py --plan <edition_id>` 获取三市当班交付计划；核对核心龙头池弹性规模（**65–85 只/市**，当前基准 **A 股 76 / 港股 75 / 美股 80，合计 231 只**）与规范无日期状态键。黄金新快照落盘后，在权益入口核验同一 `edition_id`、**6 小时数据时限**与黄金行动锁。
  - 读 `daily/INDEX.md`（前 60 行）与 `daily/SCORECARD.md`（检查到期预判并客观回填；新登检验日禁落周末）。
  - 仅命中旗舰 5 条触发阈值时，全量读取对应旗舰手册（16–32 页）与 `report_meta_*.json`。
- **Step 2｜两阶段共享 8+1 调研与统一发前对抗红队**：
  - **阶段 2A（共享 8 路并发全信源深研）**：强制交叉核验 **7 类一手信源**，除原有的黄金、A 股、港股、美股、宏观汇宗、社区辟谣 6 路外，永久增设：
    - **第 7 路｜中国大陆个人 8 大多元投资渠道专线**：实时核验 **债券（储蓄国债/超长特别国债/万亿债券与科创债 ETF）、基金与理财（货基/同业存单/真净值理财/固收+/多资产 FOF/个人养老金与 2026 C 类费改）、国债逆回购（GC001/R-001 周四与节前窗）、场内外 QDII 与香港北向互认基金 MRF（汇率锁汇/累计份额避 20% 税/溢价临停/2027 LOF 退市线）、大额存单（六大行/股份行/城商行利率、转让折价与 50 万存保）、可转债（规模/中位数/511380/511180/违约强赎/到期税）、公募 REITs（百只规模/产权 NOI vs 特许经营权 IRR/薄量破发）、非黄金大宗商品 ETF（豆粕正展期/有色/能化/白银原油 LOF 溢价与退市）**；
    - **第 8 路｜三市重点 ETF 矩阵与个股 7 维深研专线**：核验 A/港/美及全球 **80+ 只** 重点 ETF 的规模、费率、持仓、通道属性与折溢价，并对当班焦点股、变色股、财报股及周日轮换龙头逐一落实 **7 维机构级深研**（①护城河与收入利润拆解、②财务质量/FCF-CapEx/债墙、③估值分位与无风险锚/AH 比价、④股东回报与机构/南向/沽空筹码、⑤政策/监管/指数调仓与财报日历、⑥空头证伪与下行底线、⑦IF→THEN 边界与低费 ETF 替身）。
  - **阶段 2B（1 路统一发前独立红队对抗子代理）**：8 路返回后先跨轨对抗审校再落盘，专项拦截核心硬伤：① A/H 同股 PE 与股息率物理学一致；② 全部配置表 100% 闭环且 10 点条总和 = 10；③ 全部 `🔵 🔒未来主攻` 买点锚严格低于现价；④ 黄金红灯锁覆盖正文 + JSON + 三大扩展数据库 + HTML + SVG（严禁将 `517520`/`02840`/`IGLN`/`IAUM`/`NEM`/`601899`/`02899.HK` 标绿或下达新买指令）；⑤ 冬/夏令时、07:30 禁写盘后终盘、SIFMA 半日市与工作日日历零错；⑥ 零退市股（`00011`）、零 ETF 通道/代码误标（如 `513530`/`513950`/`513970` 实为 QDII、`513750` 实为非银、`516310` 为 0.20% 银行 ETF、`515080` 为招商中证红利、`159611` 为 A 股电力、`03119`/`03141` 非港股红利）、零 3 项已证伪税务/转债误导、零 8 大多元渠道关键制度硬伤（MRF 累计份额避 20% 税、REITs 产权 vs 特许经营权 IRR、大额存单 50 万存保与二手提前支取亏本、LOF 2027 退市线）及零内部工程词泄露。
- **Step 4｜核验黄金快照、落盘与编译**：在黄金落盘严检后核验同一 `edition_id`、6 小时数据时限与黄金行动锁，再按[十项门禁](references/pre_flight_10_gates.md)及[双账户与多元渠道规则](references/dual_account_tax_and_rules.md)落盘应发日报、状态账簿及增量更新 `state/multi_asset_channels.json`、`state/etf_universe.json`、`state/deep_dossiers.json`。串行执行严格预检、编译、严格终检与 PDF 抽查。
- **Step 5｜盲审、复检与发布**：按[三层 RSI 协议](references/rsi_self_review_protocol.md)由独立子代理盲审，逐项检查总看板、记分卡、状态、三大扩展数据库与三市报告，修正并闭环登记 `review_closure` 后复跑双轨严检，按令牌完成单次站点发布与部署校验。

---

## 2. 配套深度核验手册（单一权威源）

- 发版前 10 项全量门禁清单（含 8 大多元渠道、ETF 分类与 7 维深研核验）：[references/pre_flight_10_gates.md](references/pre_flight_10_gates.md)
- 中美港双账户 + 8 大个人多元渠道税费、权限、低费 ETF 与合规唯一详表：[references/dual_account_tax_and_rules.md](references/dual_account_tax_and_rules.md)
- 受控三层 RSI 自我复盘与盲审协议唯一详规：[references/rsi_self_review_protocol.md](references/rsi_self_review_protocol.md)
