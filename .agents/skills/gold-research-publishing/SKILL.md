---
name: gold-research-publishing
description: Orchestrates the beginner-friendly, institutional-grade pure-web gold deep-research and financial report publishing pipeline (converged 07:30 morning / 11:30 midday / 18:00 evening / weekend editions and the 1971-2030 master report in global-investment-research/gold) with 6-gate linting, 640px SVG vector charts, priority-ordered multi-index gold/macro anchors, unified 10+1 research and red-team workflow, 440+ interactive K-line refresh, and bounded RSI self-review. Use whenever writing, updating, auditing, or troubleshooting daily or master gold research reports, updating data_snapshot.json, invoking the two-stage 10+1 research and red-team workflow, passing the pure-web 6-gate readability and integrity linter, or publishing the static web portal via scripts/publish_site.py (web-only, zero offline document binaries).
---

# Gold Research Publishing System (`gold-research-publishing`)

本 Skill 编排 `<REPO_ROOT>/gold` 黄金深度研报（**07:30 早报 / 11:30 午报 / 18:00 晚报** / 周末专项版 / 1971–2030 全景主报告）的纯网页生产、6 门禁严检、640px 矢量图表与受控 RSI 闭环（零离线二进制附件交付）。顶层三班次编排、全球多指数标准、440+ 交互 K 线管线与跨轨红线见 `<REPO_ROOT>/AGENTS.md`；黄金子轨永久规则与税制细节见 `gold/AGENTS.md` 与 `gold/daily/DAILY_FORMAT_SPEC.md`。

---

## 1. 核心工作区文件速查（相对 `<REPO_ROOT>/gold/`）

| 文件 | 角色与约束 |
| :--- | :--- |
| `data_snapshot.json` | 跨项目 SSOT 唯一写入源（含 `edition_id`、`as_of_short`、多指数优先级 `index_matrix`【伦敦金 `XAU` → COMEX `GC` → 沪金 `AU0` → 上金所 `Au99.99`/`Au(T+D)` → 白银】、四关固定 `id` 精确输入、`vix_10d_session_closes`/`vix_daily_row_checks`、`etf_cn`、`data_caveats`、`tier_code`/`new_buy_allowed`），供 Step 4 权益轨零滞后只读校核 |
| `master_snapshot.json` / `market_calendar.json` | 主报告独立基线（常规班次惰性只读核验 5 大触发条件）；外置跨市场休市与冬/夏令时日历（覆盖至 `2027-06-30`，硬底线 30 天 / 核证 90 天） |
| `daily/YYYY-MM-DD_{0730_早报\|1130_午报\|1800_晚报}_黄金深度研报.md` | 收敛在线主刊（3 张 640px SVG 图；同场勘误加 `_r2` 防覆写；`1130_午报` 锁 11:30 上金/沪金早盘同刻平价溢价、四大行金条/金店牌价与 09:15–09:30 官方宏观）；主报告为 7 图百科版 |
| `daily/{SCORECARD,CHANGELOG,AUDIT_LOG}.md` | 公开记分卡（仅登可证伪投资预判，零后台回补工单与内部词）；历史双账本经 `scripts/patch_state_dbs.py --prepend-gold-ledgers` 无损头插、跨月经 `--archive-gold-ledgers`（`_archive_patch.json`）无损归档 |
| `daily/{RSI_PLAYBOOK.md,rsi_metrics.json}` | 受控 RSI 经验库（≤180 行软限 / 200 行硬限）与 6 维 `/30` 盲审闭环账本（经 `--append-gold-rsi` 无损追加） |
| `lint_readability.py` / `edition_validation.py` / `chart_input.py` | 6 道纯网页源稿门禁（Gate 0–5、`--strict` 零容忍）、`0730/1130/1800` 三班次 `[-5m, +6h]` 单向截点与四关复算、图表数值规范化 |

---

## 2. 端到端标准发刊 SOP（对应仓库 Step 0–5）

1. **Step 1｜日历冷启动与惰性基线继承**：依系统 `+08:00` 时间与 `market_calendar.json` 判定班次（`0730`/`1130`/`1800`）/休市模式与冬夏令时；依次读 `RSI_PLAYBOOK.md`、`rsi_metrics.json`（近 5 条）、`SCORECARD.md`、`CHANGELOG.md`（前 150 行）、`data_snapshot.json`、`master_snapshot.json`（仅命中 5 阈值时全读主报告）及上期日报。定时任务禁 `edit_file` 与未授权 shell 探测。
2. **Step 2｜两阶段 10+1 调研与统一红队（单跑回退 5+1）**：并行子代理严控 `≤ 12 KB` 紧凑回执，严守美股 `GLD`/`GDX` 官收白名单、禁用 `Barchart` 远月滞后价、善用 `site:shfe.com.cn`/`site:lbma.org.uk` 定向补录与冬/夏令时核对（午报重点锁 `11:30 CST` 上金所/沪金早盘官收、`XAU × USD/CNY ÷ 31.1034768` 同刻溢价、四大行金条与品牌金店新牌价及 09:15/09:20/09:30 国内宏观；同步归集联储/央行购金/关税/地缘与人民币利率政策要闻及未来 14–30 天 P0/P1 财经与政策日历增量供 `equity/state/policy_calendar.json` 同步）；全部返回后启动红队复核四步灯、宏观官源盘口铁律（日本 CPI 直核 `stat.go.jp` 区分日央行版剔生鲜能源[权重 9162]与欧美版[权重 6959]；上期所夜盘严分 `02:30` 金银/`01:00` 有色/`23:00` 黑色化工；LME 严守 17:00 同盘口）、跨时区因果、跨资产传导链、48 小时双向催化、政策日历一手官源与统一税费口径。
3. **Step 3｜双快照落盘、收敛主刊写作与无损头插**：
   - 先用 `write_file` 全量更新 `data_snapshot.json`（含 `index_matrix` 多锚点、无日期键 `cross_ratios`/`etf_cn`、纯中文 `data_caveats`、VIX 10 日表与核查台账：普通日 `provisional_close` 3 日内核销、节日 `pending` 4h 复查、`no_row_confirmed` 官告/CSV 自证，无有效窗口盘口时【含 `07:30` 与 `11:30` 处于美东非发布窗】`vix_live`/`vix_live_as_of` 同时留空）；
   - 再写本刊 Markdown（小白三层结构、导语 ≤160 字且信号/噪音条数须与 `DAILY_SIGNAL_NOISE` 数组长度精确一致、Layer 2 自然段 ≤250 字[建议 ≤220 字]、正文必含 **1–2 条一手官源政策/地缘要闻精读** 与 **4 列未来 7–14 天全北京时间财经/政策日历表**【与 `equity/state/policy_calendar.json` 及门户 `#sec-policy-calendar` 同步，纯中文级别徽章如重磅/重要，零裸 `P0`/`P1`、严守黄金红灯锁】、正文禁塞冗余「挂账核销成绩单」表、同一核心数字复读 ≤3 次、标题/导语零后台审计腔、1 句跨资产传导链 + 48h 双向催化 + 四情景完整 100% 拆分）与 `SCORECARD.md`（仅登可证伪投资预判）；
   - 跨月归档上月双账本时先写 `gold/daily/_archive_patch.json` 运行 `python3 <REPO_ROOT>/scripts/patch_state_dbs.py --archive-gold-ledgers`；再写微型补丁 `gold/daily/_ledger_patch.json`（`GOLD_EDITION_REVIEW` JSON 必填 `edition_id`、`as_of_short`、`note`、四关 HTTPS `sources` 与 `forecast_review.status ∈ {"settled","none_due","pending_evidence"}`，严禁 `"tracked"`），运行 `python3 <REPO_ROOT>/scripts/patch_state_dbs.py --prepend-gold-ledgers` 无损头插 `CHANGELOG.md` 与 `AUDIT_LOG.md`。命中 5 阈值时同步主报告与 `master_snapshot.json`。
4. **Step 4｜6 门禁严格验收（绝对路径裸命令，无 `cd &&`）**：
   ```bash
   python3 <REPO_ROOT>/gold/lint_readability.py --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md
   ```
   须 `0 errors, 0 warnings`（同步主报告时一并传入），随后交棒权益轨 Step 4。
5. **Step 5｜统一 RSI 盲审（5 项真核验）、全市场 K 线刷新与单次纯网页发布**：双轨源稿全绿后由独立只读盲审按 6 维 `/30` 打分并完成 5 项真核验（含政策/地缘新闻官源真实性与 7–14 天全北京时间日历和门户 `#sec-policy-calendar` 逐项一致核对）闭环登记 `review_closure`；通过 `scripts/patch_state_dbs.py --append-gold-rsi` 无损追加 `rsi_metrics.json`（严禁整文件重写）并更新 `RSI_PLAYBOOK.md`（≤180 行），Tier B 仅在确凿 Bug 时 ≤1 处 ≤40 行补丁并重跑全套校验，Tier C 仅提案。复跑双轨严检后运行 `python3 <REPO_ROOT>/scripts/fetch_kline_data.py --scope all` 刷新全市场 480+ 静态 K 线分片，按令牌运行 `python3 <REPO_ROOT>/scripts/publish_site.py --edition-token <token>`（过 S1–S7 严检）与 `edition_run.py complete <token>` 验真上线。本机伴随实时监测工具 `scripts/realtime_monitor.py` 与 `scripts/wechat_notify.py` 独立于定时 56 项权限之外运行，严格只读读取 `gold/data_snapshot.json` 与 `equity/state/policy_calendar.json`（完全继承黄金红灯锁，去重状态写入 `.git/realtime-monitor.sqlite3` 零仓库污染）。

---

## 3. 快速排障对照

| 门禁报错 | 根因与修复 |
| :--- | :--- |
| `Gate 0` JSON / 必填键 / 图 2 标签宽 | 检查 `<!-- DAILY_* {...} -->` 合法 JSON、`edition_id`/`as_of_short`/`checks[].id` 与 `items[].label ≤ 8.5` 汉字当量 |
| `Gate 1–3` 术语/泄露/感叹号/平行打分 | 清空全篇内部工程词/版本号/文件名（含 `fetch_kline_data.py`）与 6 说教口号；Layer 0–1 零感叹号（全篇 ≤5）、零 13 煽动词、零 `X/6` |
| `Gate 4` 段落/加粗/裸数字反引号 | Layer 0–1 自然段 ≤240 字、加粗 ≤14%、仅代码套反引号 |
| `Gate 5` 快照/四关/信号计数/开仓话术 | 按 `edition_validation.py` 复算四关与 VIX；核齐导语信号/噪音条数 == `DAILY_SIGNAL_NOISE` 长度；删部分过关开仓话术 |
| 账本/日历/记分卡/静态站报错 | 核查 `GOLD_EDITION_REVIEW` 禁用 `"tracked"`、日历 ≥30 天、`SCORECARD.md` 零内部词；用 `build_site.py` + `lint_site.py --strict`（含 Gate S7）定位 |

---

## 4. 按需加载参考手册（Progressive Disclosure）

1. **小白三层编辑宪章、升级版三档词汇、A/B/D/C 画像与买金税制回购详规**：[./references/editorial-charter-and-personas.md](./references/editorial-charter-and-personas.md)
2. **10 个 `DAILY_*` 组件 JSON Schema、主报告 7 图、双快照与三班次抗阻塞日历契约**：[./references/directives-and-snapshot-schema.md](./references/directives-and-snapshot-schema.md)
3. **纯网页 6 道门禁词表、`.sn-grid`/`.kpi-strip.cols-4`、640px 矢量防撞引擎与跨月运维**：[./references/7-gates-and-ooxml-engine.md](./references/7-gates-and-ooxml-engine.md)
4. **统一 10+1（独立 5+1 回退）调研红队操作手册、七大信源、月度归档与 RSI 协议**：[./references/5-plus-1-research-playbook.md](./references/5-plus-1-research-playbook.md)
