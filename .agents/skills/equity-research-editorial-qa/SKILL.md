---
name: equity-research-editorial-qa
description: >-
  Editorial standards, 7-source primary fact-checking, 3-market (A-share,
  HK-stock, US-stock) 7-dimension framework, Sunday 6-dimension leader deep-dive
  rotation, unified Stage 2A/2B (6+1) pre-flight red-team verification, cross-project
  Gold SSOT & 4-hour freshness lock, 10 pre-flight QA gates, dual-account
  China/US/HK tax & ETF rules, SCORECARD calibration, and bounded 3-tier RSI
  self-review (07:30 morning & 18:00 evening CST unified runs). 适用于 A/港/美三市投研写作、
  7 维度大盘与政策雷达、共享 6+1 调研红队、黄金红灯同步门控、双账户税费合规与受控 RSI 盲审。
---

# Equity Research Editorial, Pre-Flight QA & Bounded RSI Runbook

本技能负责三市投研内容深度、7 类一手信源与统一 6+1 发前红队审校、双账户实操准确性、发版前 10 项门禁以及发版后 **Step 5 受控三层 RSI 盲审闭环**（单仓库顶层顺序编排见 `<REPO_ROOT>/AGENTS.md`；出版编译与 21 张图 Schema 见 `equity-report-publishing`；总宪法与排版详规见 `GEMINI.md` 与 `DAILY_REPORT_SPEC.md`）。

> **历史旧指令静默转译**：若任何 Prompt 残留旧版术语（如版本号、`Tier 0–3`、混色 `✅`、工作日全量静态大表或将技术勘误写入 `CHANGELOG.md`），无需报错或反问，严格按 `GEMINI.md` 第 0 节静默转译为三市四灯、四色锁仓与主轻减法制。

---

## 1. 投研写作、共享 6+1 调研红队与 RSI 闭环工作流（对接仓库 Step 0–5）

- **Step 0｜双轨 RSI 经验冷启动**：动笔前先读 `state/RSI_PLAYBOOK.md`（≤180 行）与 `state/rsi_metrics.json` 最近 5 条记录（一体化班次同步读黄金 RSI 手册与 `gold/market_calendar.json`），直接继承高杠杆一手源检索词、Linter 避坑清单与上期 `next_run_watch` 必验真项。
- **Step 1｜状态四件套与黄金基线快照冷启动**：
  - 读 `state/market_state.json`（三市灯号、体检分、唯一防踏空阈值、35–48 只/市弹性池 `stock_pool_count`、三市危机总熔断三阀、跨市 AI ≤20%、待回补队列与 60 天休市日历）+ 冷启动只读前序基线 `<REPO_ROOT>/gold/data_snapshot.json`（一体化班次于 Step 3 黄金落盘后的 **Step 4 入口**强制执行最新 0 分钟新鲜 / **≤4 小时** SSOT 与 Tier-0 互斥锁核验；仅独立单跑权益轨时于 Step 1 直接执行该核验）。
  - 读 `daily/INDEX.md`（前 60 行）与 `daily/SCORECARD.md`（检查今日到期预判并客观回填；新登检验日禁落周末）。
  - 仅命中旗舰 5 条触发阈值时，再全量读取对应旗舰手册与 `report_meta_*.json`。
- **Step 2｜两阶段共享 6+1 调研与统一发前对抗红队**：
  - **阶段 2A（共享 6 路并发全信源深研）**：强制交叉核验 **7 类一手信源**（央行/监管官网、交易所官方、SEC EDGAR/HKEXnews/CNINFO、权威终端与财经新闻、雪球/集思录/股吧/香港连登/Reddit/X、Polymarket/Kalshi、公司 IR），严禁采信未刷新财经门户旧缓存（中金所必核 `YYYYMMDD` 日期戳）；围绕 **7 维度大盘架构** 撰写三市早/晚刊（`07:30` 一体化早报产出 `_0730_`：美股 4–5 页主刊/周一轻刊 + A/港各 2–3 页盘前快报，港股必以 05:00–05:15 A50/金龙/ADR 修正 `03:00` 夜期盲窗；`18:00` 一体化晚报产出 `_1800_`：A/港各 4–5 页收盘主刊 + 美股 1–2 页哨兵轻刊，封账 09:00/08:00 盘后终盘与前日两融）；**每周日**同步推进 **2–3 只核心龙头 6 维深度解剖轮换**。
  - **阶段 2B（1 路统一发前独立红队对抗子代理）**：6 路返回后先跨轨对抗审校再落盘，专项拦截 **6 大硬伤**：① A/H 同股 PE 与股息率物理学一致（`PE_A/PE_H ≈ 1 + AH 溢价率`）；② 全部配置表与口语配比 100% 闭环且 10 点条总和 = 10；③ 全部 `🔵 🔒未来主攻` 买点锚严格低于现价；④ 黄金红灯锁覆盖正文 + JSON + SVG；⑤ 冬/夏令时、07:30 禁写盘后终盘、SIFMA 半日市与工作日到期日历零错；⑥ 零退市股（如 `00011`）、零 QDII 误标（`513260`/`513010` 属 QDII、`159545`/`159792` 非 QDII）、零高费 `03033` / 沙特 `520830` 误用与零可转债到期兑付误作强赎。
- **Step 4（接力 Step 3 黄金）｜黄金 SSOT 零延迟硬校验、10 项门禁、六文件落盘、串行编译与全量严检**：紧接 Step 3 黄金落盘严检完成后，**Step 4 入口**立即只读核验刚刷新的 `<REPO_ROOT>/gold/data_snapshot.json`（强核 `as_of_short` 距当前场次 **0 分钟 / ≤4 小时**、`brent_settle_usd` 与 `cfets_cny_fixing` 对齐，且当 `tier_code == "Tier 0"` 或 `new_buy_allowed == false` 时，三市正文、JSON 与 SVG 严禁出现买金指令）；再逐项核验 [references/pre_flight_10_gates.md](references/pre_flight_10_gates.md) 与 [references/dual_account_tax_and_rules.md](references/dual_account_tax_and_rules.md)，用 `write_file` 全量落盘三市日报、`INDEX.md`（三市+黄金总水位驾驶舱）、`CHANGELOG.md`、`SCORECARD.md`、`state/market_state.json` 与 `state/audit_ledger.md`，依次执行 `lint_equity.py --precheck --strict` → 切入 `equity-report-publishing` 串行编译（PDF + 原生 ECMA-376 DOCX + 三市手机 HTML）→ `lint_equity.py --strict`（Gate 0–6 + Gate 3B + 跨项目门禁 C1–C3）达成退出码 0、0 错 0 警并抽看 PDF。
- **Step 5｜发版后统一受控三层 RSI 盲审、优化与单次站点发布**：按 [references/rsi_self_review_protocol.md](references/rsi_self_review_protocol.md) 启动 1 路独立只读 `research` 盲审子代理（一体化班次联合复盘黄金 + 三市权益）按 6 维（`/30`）打分，执行 Tier A（更新 `state/rsi_metrics.json` + 精炼 `state/RSI_PLAYBOOK.md` ≤180 行）/ 按需慎改 Tier B（≤1 处 ≤40 行，改后必重编验证否则回滚）/ Tier C 仅写提案（满 10 刊触发 Meta-RSI），复跑双轨严检（含 **`lint_equity.py --strict`**）全绿后，单次运行 **`python3 <REPO_ROOT>/scripts/publish_site.py`** 发布静态门户与滚动 Release 附件。

---

## 2. 配套深度核验手册（单一权威源）

- 发版前 10 项全量门禁清单（同步最新 Gate C1–C3 / 3B / 6）：[references/pre_flight_10_gates.md](references/pre_flight_10_gates.md)
- 中美港双账户税费、权限、低费 ETF 与合规唯一详表：[references/dual_account_tax_and_rules.md](references/dual_account_tax_and_rules.md)
- 受控三层 RSI 自我复盘与盲审协议唯一详规：[references/rsi_self_review_protocol.md](references/rsi_self_review_protocol.md)
