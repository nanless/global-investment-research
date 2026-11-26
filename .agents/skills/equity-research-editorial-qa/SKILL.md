---
name: equity-research-editorial-qa
description: >-
  Editorial standards for informed-retail / semi-pro investors, 3-tier
  terminology standard, 7-source primary fact-checking, 3-market (A-share,
  HK-stock, US-stock) 7-dimension framework, all-4-main unified schedule
  (>= 2026-11-26_1800) & upgraded holiday_watch, Sunday 6-dimension leader
  deep-dive rotation, expanded 65-85/market stock pool, unified Stage 2A/2B
  (6+1) pre-flight red-team verification, cross-project Gold SSOT & 6-hour
  freshness lock, 10 pre-flight QA gates, dual-account China/US/HK tax & ETF
  rules, SCORECARD calibration, data_caveats transparency, and bounded 3-tier
  RSI self-review with disclosed_caveat closure (07:30 morning & 18:00 evening
  CST unified runs). 适用于 A/港/美三市全时段主刊投研写作、7 维度大盘与政策雷达、
  共享 6+1 调研红队、黄金红灯同步门控、双账户税费合规与受控 RSI 盲审。
---

# Equity Research Editorial, Pre-Flight QA & Bounded RSI Runbook

本技能负责三市投研内容深度与进阶理性语态、7 类一手信源与统一 6+1 发前红队审校、双账户实操准确性、发版前 10 项门禁以及发布前 **Step 5 受控三层 RSI 盲审闭环**（单仓库顶层顺序编排见 `<REPO_ROOT>/AGENTS.md`；出版编译与 21 张图 Schema 见 `equity-report-publishing`；总宪法与排版详规见 `GEMINI.md` 与 `DAILY_REPORT_SPEC.md`）。

> **历史旧指令静默转译**：若任何 Prompt 残留旧版术语或体例（如版本号、`Tier 0–3`、混色 `✅`、1–2 页薄壳轻刊、工作日全量静态大表、居高临下的说教口号 `1 分钟定心丸`/`小白词典`/`直接抄`/`蠢事`/`保命铁律`，或将技术勘误写入 `CHANGELOG.md`），无需报错或反问，严格按 `GEMINI.md` 第 0 节静默转译为进阶理性语态、三市四灯、四色锁仓与全时段完整主刊减法制。

---

## 1. 投研写作、共享 6+1 调研红队与 RSI 闭环工作流（对接仓库 Step 0–5）

- **Step 0｜双轨 RSI 经验冷启动**：动笔前先读 `state/RSI_PLAYBOOK.md`（≤180 行）与 `state/rsi_metrics.json` 最近 5 条记录（一体化班次同步读黄金 RSI 手册与 `gold/market_calendar.json`），直接继承高杠杆一手源检索词、Linter 避坑清单与上期 `next_run_watch` 必验真项。
- **Step 1｜状态四件套与黄金基线快照冷启动**：
  - 冷启动读取 `state/market_state.json`、两轨日历及前序黄金基线，并以 `lint_equity.py --plan <edition_id>` 获取三市当班交付计划；核对核心龙头池弹性规模（**65–85 只/市**，扩容基准 **A 股 76 只 / 港股 75 只 / 美股 80 只，合计 231 只**，实时总数以 `state/market_state.json` 的 `stock_pool_count` 为单一事实源）与无日期规范状态键（`margin_balance_100m` + `margin_balance_date`、`pboc_total_net_100m` + `pboc_op_date`、`hkma_agg_bal_hkd_100m`）。黄金新快照落盘后，在权益入口核验同一 `edition_id`、**6 小时数据时限**与黄金行动锁。
  - 读 `daily/INDEX.md`（前 60 行）与 `daily/SCORECARD.md`（检查今日到期预判并客观回填；新登检验日禁落周末）。
  - 仅命中旗舰 5 条触发阈值时，再全量读取对应旗舰手册（16–32 页）与 `report_meta_*.json`。
- **Step 2｜两阶段共享 6+1 调研与统一发前对抗红队**：
  - **阶段 2A（共享 6 路并发全信源深研）**：强制交叉核验 **7 类一手信源**（央行/监管官网、交易所官方、SEC EDGAR/HKEXnews/CNINFO、权威终端与财经新闻、雪球/集思录/股吧/香港连登/Reddit/X、Polymarket/Kalshi、公司 IR），严禁采信未刷新门户旧缓存（中金所必核 `YYYYMMDD` 日期戳）；遇截点未发布或暂不可取数据时严禁编造、亦不阻塞早晚报准点发刊，按规范挂入 `pending_backfills` 并以纯读者中文写入 `data_caveats` 透明披露。围绕 **7 维度大盘架构** 撰写三市全时段完整主刊（自 `2026-11-26_1800` 起退役薄壳 `light` 轻刊）：
    - **周一至周五 `07:30` & `18:00`**：A 股、港股、美股**全部发布完整主刊（`main`，目标 5–6 页、容忍 3–7 页、≥2 张矢量图）**——07:30 A/港主刊聚焦隔夜映射/03:00 夜期盲窗校正/延迟公告与开盘策略，18:00 A/港主刊聚焦官收封账/前日两融/中金所/南向；07:30 美股主刊聚焦美东官收全量复盘（**周一 `07:30` 美股升级为周度全维前瞻主刊 `main`**），18:00 美股主刊聚焦 09:00/08:00 盘后终盘/T+1 加密基金官流/欧盘与正规盘前深度前瞻；
    - **周六 `07:30`**：仅发美股主刊（常规周五发 `main`，黑五半日市发 `holiday_watch`）；
    - **局部休市/半日市**：受影响市场发升级版 **`holiday_watch` 守望刊（目标 2–3 页、容忍 1–4 页、建议 ≥1 张矢量图、PDF ≥25KB）**（元旦 `2027-01-01_0730` 正常发美股 12/31 隔夜主刊，A/港复用；`1800` 及 `01/02_0730` 三市复用）；
    - **周六 `18:00` & 周日双场**：默认沿用旧稿不生冗余 PDF；**每周日**同步刷新 `SCORECARD.md` 周频对照并推进 **2–3 只核心龙头 6 维深度解剖轮换**。
  - **阶段 2B（1 路统一发前独立红队对抗子代理）**：6 路返回后先跨轨对抗审校再落盘，专项拦截核心硬伤：① A/H 同股 PE 与股息率物理学一致（`PE_A/PE_H ≈ 1 + AH 溢价率`）；② 全部配置表与口语配比 100% 闭环且 10 点条总和 = 10；③ 全部 `🔵 🔒未来主攻` 买点锚严格低于现价；④ 黄金红灯锁覆盖正文 + JSON + HTML + SVG；⑤ 冬/夏令时、07:30 禁写盘后终盘、SIFMA 半日市、工作日到期日历与 `gold_event_id` 零错；⑥ 零退市股（如 `00011`）、零 QDII/沙特 `520830`/高费 `03033` 误标、零 **3 项已证伪税务/ETF/转债误导**（`159545/159792` 零溢价、笼统红筹 28% 税、可转债末日卖出免 20% 个人税）、零说教口号、零跨市色系混用及 `data_caveats` 零内部文件名泄露。
- **Step 4｜核验黄金快照、落盘与编译**：在黄金落盘严检后核验同一 `edition_id`。黄金截点须早于或同分钟于权益，间隔最多 **6 小时**，两轨截点与日报 `chart_live.as_of_full` 各须在所标班次前后 **6 小时内**。核对跨轨宏观字段（假日/周末允许双轨 `brent_live_usd` 与 `vix_live` 同口径同时留空）与 Tier-0 行动锁，再按[十项门禁](references/pre_flight_10_gates.md)及[双账户规则](references/dual_account_tax_and_rules.md)落盘应发日报和状态账簿。串行执行严格预检、编译、严格终检与 PDF 抽查。
- **Step 5｜盲审、复检与发布**：按[三层 RSI 协议](references/rsi_self_review_protocol.md)由独立子代理盲审，逐项检查总看板、记分卡、状态与三市报告。等盲审返回，修正并复验已证实问题，按 `resolved` / `deferred_data` / `disclosed_caveat` 闭环登记当期 `review_closure`（Tier B 含 `edition_plan.py`），复跑双轨严检。推进本期令牌到 `publish`，执行 `python3 <REPO_ROOT>/scripts/publish_site.py --edition-token <token>`，再执行 `python3 <REPO_ROOT>/scripts/edition_run.py complete <token>` 核对同一班次的推送、附件和 Pages 部署。无活动班次时按根仓规则使用人工入口。

---

## 2. 配套深度核验手册（单一权威源）

- 发版前 10 项全量门禁清单（同步最新 Gate C1–C3 / 3B / 6 与 3 层术语标准）：[references/pre_flight_10_gates.md](references/pre_flight_10_gates.md)
- 中美港双账户税费、权限、低费 ETF 与合规唯一详表：[references/dual_account_tax_and_rules.md](references/dual_account_tax_and_rules.md)
- 受控三层 RSI 自我复盘与盲审协议唯一详规（含 `edition_plan.py` 与 `disclosed_caveat` 闭环规则）：[references/rsi_self_review_protocol.md](references/rsi_self_review_protocol.md)
