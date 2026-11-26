# 受控三层 RSI 自我复盘与递归优化唯一详规（Bounded RSI Self-Review Protocol）

本协议为全项目 Step 5 受控三层 RSI 自我复盘的**唯一权威详规**（`GEMINI.md`、`DAILY_REPORT_SPEC.md` 与 `state/RSI_PLAYBOOK.md` 均以本协议为准，一体化单会话编排见 `<REPO_ROOT>/AGENTS.md`）。每次 **07:30 一体化早报（`_0730_`）** 或 **18:00 一体化晚报（`_1800_`）**（含周末突发升级刊）的候选稿通过严检（0 错 0 警）与 PDF 视觉抽检后，发布前必须执行本闭环（一体化班次由 1 路统一盲审子代理联合覆盖黄金 + 三市权益并分别落盘至两轨 RSI 台账）。全部 RSI 产物永久隔离于 `state/RSI_PLAYBOOK.md` 与 `state/rsi_metrics.json`，**绝不泄露至任何读者可见 `.md` / `.pdf` / `.docx` / `.html` / `INDEX.md` / `CHANGELOG.md` / `SCORECARD.md`**。

---

## 一、核心原则：安全、有界、可回滚、永不退化

1. **冷启动先读经验（Step 0）**：每班次开始动笔前，必须先读取 `state/RSI_PLAYBOOK.md`（≤180 行）与 `state/rsi_metrics.json` 最近 5 条记录，直接继承历史教训、一手源检索词雷达与 `next_run_watch`。
2. **本地检查后启动发布前盲审（Step 5）**：先编译三市候选稿，通过 `lint_equity.py --strict` 和 PDF 逐页抽检。等独立只读盲审返回后，修正本期所有已证实的错误，并重编、复验受影响的报告。发布前按 `resolved` / `deferred_data` / `disclosed_caveat` 闭环记录每项发现的处置结果。
3. **防退化铁律**：只允许**加固门禁、消除 Bug、提炼更高杠杆规则**；**严禁**为凑“一次过”而删除红线禁词、调松字数/加粗/表宽/页数/黄金锁门禁，或悄悄改写策略红线与宪法规则。

---

## 二、三层权限边界（Tier A / Tier B / Tier C · 全库统一口径）

| 层级 | 允许改动的文件范围 | 动作权限 | 强制验证与失败回滚机制 |
| :--- | :--- | :--- | :--- |
| **Tier A（每刊自动）** | `state/RSI_PLAYBOOK.md`、`state/rsi_metrics.json` | 每刊全自动追加 1 条三市盲审遥测、滚动精炼经验手册并更新 `next_run_watch` | 手册严格 **≤180 行**（181–200 行告警，>200 行阻断；合并重复、淘汰已固化项，且不得残留 3 项已证伪税务/ETF/转债旧口径）；JSON 合法、`run_id` 唯一、`total_score == sum(scores)`、`max_score == 30`；须通过 `lint_equity.py --strict` 终检 |
| **Tier B（按需慎改）** | `equity/edition_plan.py`、`pdf_common.py`、`docx_embed.py`、`build_daily.py`、`build_a_share_pdf.py`、`build_hk_stock_pdf.py`、`build_us_stock_pdf.py`、`lint_equity.py`、`DAILY_REPORT_SPEC.md` | 仅当本轮复现了确凿的排期判定、渲染碰撞、JSON 解析或 Linter 漏网 Bug 时，允许实施 **≤1 处、≤40 行** 最小补丁 | 改后必须串行重跑受影响的 `build_*.py` 并执行 **`lint_equity.py --strict`** 达成 **0 错 0 警** + 抽看 PDF；**任一步报错、误报或版面恶化，必须立即回滚**并降级写入 Tier C 提案区 |
| **Tier C（宪法锁定）** | `<REPO_ROOT>/AGENTS.md`、`GEMINI.md`、核心风控红线（四灯阈值、三市危机总熔断阀、AI 跨市 ≤20%、单股 ≤8%、黄金红灯锁、5 万美元购汇红线、6 万美元美国遗产税边界）、工作区三 Skill（`<REPO_ROOT>/.agents/skills/`）、`<REPO_ROOT>/automations/sidecars/`（含 `scripts/install_sidecars.py`）与本地 `sidecar.json` | **严禁无人值守自改**；仅作为结构化提案写入 `state/RSI_PLAYBOOK.md` 第四节与 `rsi_metrics.json` 的 `tier_c_proposals` | 在最终快报中向用户明确呈报，等待用户在交互会话中明确审批后再执行 |

---

## 三、Step 5 独立只读盲审子代理 Prompt 模板（三市 + 黄金 SSOT 版）

每次候选稿通过本地验收后，启动 **1 个独立只读 `research` 子代理**（`Role: "RSI Self-Review & Improvement Auditor"`）：

> 你负责独立只读盲审，所有判断交回主会话。请完整核查本期候选 **三市日报**（`daily/YYYY-MM-DD_HHMM_a_share.{md,pdf}`、`daily/YYYY-MM-DD_HHMM_hk_stock.{md,pdf}`、`daily/YYYY-MM-DD_HHMM_us_stock.{md,pdf}`，含涉及更新的旗舰手册与 `report_meta_*.json`）、配套同步文件（`daily/INDEX.md`、`daily/CHANGELOG.md`、`daily/SCORECARD.md`、`state/market_state.json`、`state/audit_ledger.md`）、跨项目黄金快照（`../gold/data_snapshot.json`）以及历史经验文件（`state/RSI_PLAYBOOK.md`、`state/rsi_metrics.json`）。按以下 6 个维度逐项打分（1–5 分整数），写清每项缺陷、文件位置、原值、核对依据及其观测时点：
> 1. `data_freshness_and_zero_hallucination`（7 类一手源鲜度、黄金快照 **6 小时**截点宽限与 `brent_settle_usd`/`cfets_cny_fixing` 对齐、假日/周末双轨 `brent_live_usd`/`vix_live` 空值口径一致、T+1 挂账与纯读者中文 `data_caveats` 透明披露、无日期规范键 `margin_balance_100m`/`margin_balance_date`/`pboc_total_net_100m`/`pboc_op_date`/`hkma_agg_bal_hkd_100m`、A/H 同股 PE 物理学一致、冬夏令时与合约口径零误差、无退市股或事件误判）
> 2. `prior_forecast_calibration`（上期 `next_run_watch` 与 `SCORECARD.md` 到期预判客观验真、不回避失误、新登检验日均为工作日）
> 3. `plain_language_and_strict_readability`（进阶普通投资者理性专业语态、3 层术语标准、零说教口号 `1 分钟定心丸`/`小白词典`/`直接抄`/`蠢事`/`保命铁律`、零内部工程/RSI/版本词泄露、零跨市涨跌色系混用、零 3 项已证伪税务/ETF/转债误导、反引号/粗体/段长/列表密墙/3 秒正向自检卡/黄金红灯全载体互斥锁零破口）
> 4. `visual_layout_and_pagination`（PDF 页数精准落于红线区间：**旗舰 16–32p / 常规主刊 `main` 目标 5–6p（容忍 3–7p，≥2 张矢量图）/ 守望刊 `holiday_watch` 及历史 `light` 目标 2–3p（容忍 1–4p，建议 ≥1 张矢量图，PDF ≥25KB）**、零文字/图表压线碰撞、零尾页孤行、图号顺排、图文评级色标一致、`H6` 全量动态不截断、`U5` 动态行高、`U6` 统一 1:1 线性刻度）
> 5. `research_efficiency_and_source_quality`（阶段 2A 共享六路并发分工 + 阶段 2B 统一发前独立红队高效拦截核心硬伤、一手官源占比高、有效拦截门户脏缓存或市场谣言）
> 6. `engine_and_guardrail_reliability`（一次过 `lint_equity.py --precheck --strict` 与 `--strict` 零重试、原生 ECMA-376 DOCX 完整无损、必填 `edition_id`/`edition_type` 与 JSON 零混键零原始 Emoji、`h6.items`/`h6.sector_strip` 与 `hkma_agg_bal_hkd_100m` 规范）
>
> 请直接输出结构化盲审报告：
> - (a) 6 维整数打分与总分 `/30` + 每维扣分/亮点硬证据；
> - (b) 上期 `next_run_watch` 逐条回验表（`hit` / `partial` / `miss` / `pending_tonight` / `pending_next` + 客观证据）；
> - (c) **Tier A 改进清单**（2–4 条可直接沉淀进 `state/RSI_PLAYBOOK.md` 的高杠杆新规则，如手册接近 180 行同时指出可合并/淘汰的旧条款）；
> - (d) **Tier B 补丁评估**（若本轮无确定性脚本/排期/Linter Bug 明确写“无需 Tier B 补丁”；若有则给出 ≤40 行精确最小改动建议与回归测试点）；
> - (e) **Tier C 架构提案**（如有需用户审批的规则/宪法/Skill/定时架构升级，最多 2 条，否则为空）；
> - (f) **下班次 3–4 条 `next_run_watch` 必验真追踪项**（必须带精确北京时间节点与客观检验标准）；
> - (g) **发布前必须闭环的事实与载体问题**，供主会话逐项处置：已证实错误必须修正并标 `resolved`；确属官方尚未披露或源暂不可取且本期已省略/挂账的标 `deferred_data`；确属节假薄盘、暂定收盘或来源口径分歧且已通过 `data_caveats` 与正文充分透明披露、不构成事实错误的提醒项可标 `disclosed_caveat`（严禁以 `disclosed_caveat` 放行硬错）。

---

## 四、`state/rsi_metrics.json` 单条运行记录 Schema 与 `review_closure` 闭环规则

每刊向 `runs` 数组末尾追加 1 个对象，保留历史记录。联合班次按 [共享任务提示词](../../../../automations/unified-edition.prompt.md) 与发布门禁脚本登记 `review_closure`。周六 `07:30` 仅发美股主刊（或黑五 `holiday_watch`）时，`pdf_pages` 按实际页数登记，A 股、港股为 `null`；周五滞后美股盘后终盘与 BTC ETF 官流 `pending_backfills` 挂至下周一 `0730` 美股周度前瞻主刊。

### `review_closure.findings[].status` 合法终态定义（`open` 将阻断发布）
- **`resolved`**：已证实的事实、图表或结构问题已完成修正并复验；`evidence` 须为非空字符串，写清修改文件、具体改动与复验结果。
- **`deferred_data`**：数据确实尚未官方发布或权威源暂不可取，且本期已省略该值或明确挂账；`evidence` 须为对象，必填 `source`（有效 HTTP(S) URL）、`due_edition`（晚于本期的有效期号）与 `disposition`（本期处理方式）。
- **`disclosed_caveat`**：非硬性事实错误的数据限制（如节假薄盘流动性偏稀、暂定收盘过渡、多源微小口径差异等），且本期已在正文与 `data_caveats` 中向读者充分透明披露、不阻塞准点发刊；`evidence` 须为对象，必填非空 `disposition`（透明披露内容与影响边界说明），若提供 `source` 须为有效 HTTP(S) URL，若提供 `due_edition` 须为晚于本期的有效期号。**严禁将已证实正文/图表/算术硬错降级标为 `disclosed_caveat` 放行。**

```json
{
  "run_id": "2026-11-26_1800",
  "edition_type": "weekday_evening",
  "reports": [
    "daily/2026-11-26_1800_a_share.md",
    "daily/2026-11-26_1800_hk_stock.md",
    "daily/2026-11-26_1800_us_stock.md"
  ],
  "timestamp_cst": "2026-11-26T18:45:00+08:00",
  "first_pass_clean": true,
  "lint_retries": 0,
  "lint_errors_fixed": [],
  "pdf_pages": { "a_share": 5, "hk_stock": 5, "us_stock": 3 },
  "flagship_updated": { "a_share": false, "hk_stock": false, "us_stock": false },
  "scores": {
    "data_freshness_and_zero_hallucination": 5,
    "prior_forecast_calibration": 4,
    "plain_language_and_strict_readability": 5,
    "visual_layout_and_pagination": 5,
    "research_efficiency_and_source_quality": 5,
    "engine_and_guardrail_reliability": 5
  },
  "total_score": 29,
  "max_score": 30,
  "review_closure": {
    "reviewer_completed": true,
    "findings": [
      {
        "description": "总看板错引盘中恐慌指数旧值",
        "status": "resolved",
        "evidence": "daily/INDEX.md 已改为带交易日的 Cboe 官收，逐项对照快照及美股报告，复检通过。"
      },
      {
        "description": "感恩节休市期间美股盘中衍生指标与原油实时价暂无连续盘口",
        "status": "disclosed_caveat",
        "evidence": {
          "disposition": "已在正文及 state/market_state.json 的 data_caveats 中以纯读者中文透明披露休市薄盘与沿用 11/25 官收口径，双轨盘中键同步留空。",
          "source": "https://www.nasdaqtrader.com/TraderNews.aspx?id=UTP2026-34",
          "due_edition": "2026-11-27_1800"
        }
      }
    ]
  },
  "prior_predictions_checked": [
    {
      "claim": "具体预判或追踪项",
      "outcome": "hit | partial | miss | pending_tonight | pending_next",
      "evidence": "客观一手行情或数据证据"
    }
  ],
  "tier_a_improvements": ["..."],
  "tier_b_patches": [],
  "tier_c_proposals": [],
  "next_run_watch": ["..."]
}
```

---

## 五、每 10 刊 Meta-RSI 跨周期趋势总复盘与终检收官

1. **Meta-RSI 触发**：每当 `len(runs) > 0` 且 `len(runs) % 10 == 0` 时，盲审子代理同步统计最近 10 刊总分均值、一次过率（`first_pass_clean` 占比）与 6 个维度各自均分，锁定连续得分最低的 1–2 个结构性瓶颈维度，输出 **≤2 条高价值 Tier C 根因升级提案** 写入 `state/RSI_PLAYBOOK.md` 第四节待用户审批，同时彻底淘汰过时条目保持手册 ≤180 行。
2. **统一终检与单次站点发布**：Tier A（及按需 Tier B）落盘后复跑双轨严检，确认手册行数、JSON 合法性、`run_id` 唯一性及各维分数在 1–5 且合计正确。推进本期令牌到 `publish`，执行 `python3 <REPO_ROOT>/scripts/publish_site.py --edition-token <token>`，再执行 `python3 <REPO_ROOT>/scripts/edition_run.py complete <token>` 验证同一班次的发布结果。
