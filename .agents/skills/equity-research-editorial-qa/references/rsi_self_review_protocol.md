# 受控三层 RSI 自我复盘与递归优化唯一详规（Bounded RSI Self-Review Protocol · 纯网页版）

本协议为全项目 Step 5 受控三层 RSI 自我复盘的**唯一权威详规**（`GEMINI.md`、`DAILY_REPORT_SPEC.md` 与 `state/RSI_PLAYBOOK.md` 均以本协议为准，一体化单会话编排见 `<REPO_ROOT>/AGENTS.md`）。每次 **07:30 一体化早报（`_0730_`）**、**11:30 一体化午报（`_1130_`）** 或 **18:00 一体化晚报（`_1800_`）**（含周末突发升级刊）的候选源稿通过双轨严检（0 错 0 警）后，发布前必须执行本闭环（一体化班次由 1 路统一盲审子代理联合覆盖黄金 + 三市权益 + 4 角色层 12 大多元渠道/181+ 正交标注 ETF/231 股 7 维深研库/`policy_calendar.json`，并分别落盘至两轨 RSI 台账）。全部 RSI 产物永久隔离于 `state/RSI_PLAYBOOK.md` 与 `state/rsi_metrics.json`，**绝不泄露至任何读者可见 `.md` / `.html` / 三大扩展 JSON / `policy_calendar.json` / K 线分片 JSON / `INDEX.md` / `CHANGELOG.md` / `SCORECARD.md`**。

---

## 一、核心原则：安全、有界、可回滚、永不退化

1. **冷启动先读经验（Step 0）**：每班次开始动笔前，必须先读取 `state/RSI_PLAYBOOK.md`（≤180 行）与 `state/rsi_metrics.json` 最近 5 条记录，直接继承历史教训、一手源检索词雷达与 `next_run_watch`。发布前为每张公开政策简报核对完整摘要，并对全部实际展示的原始链接逐条登记。待补核销关联当班已核验的事实或计算、文件和同一出处。
2. **源稿严检后启动发布前盲审（Step 5）**：先通过 `gold/lint_readability.py --strict` 与 `equity/lint_equity.py --strict` 验收全部候选源稿、21 张 SVG 参数与三大扩展数据库。等独立只读盲审返回后，修正本期所有已证实的错误并复验受影响轨道。发布前按 `resolved` / `deferred_data` / `disclosed_caveat` 闭环记录每项发现的处置结果。
3. **防退化铁律**：只允许**加固门禁、消除 Bug、提炼更高杠杆规则**；**严禁**为凑“一次过”而删除红线禁词、调松字数/加粗/表宽/黄金锁门禁，或悄悄改写策略红线与宪法规则。

---

## 二、三层权限边界（Tier A / Tier B / Tier C · 全库统一口径）

| 层级 | 允许改动的文件范围 | 动作权限 | 强制验证与失败回滚机制 |
| :--- | :--- | :--- | :--- |
| **Tier A（每刊自动）** | `state/RSI_PLAYBOOK.md`、`state/rsi_metrics.json` | 每刊经 `equity/state/_rsi_patch.json` + `scripts/patch_state_dbs.py --append-equity-rsi`（黄金经 `gold/daily/_rsi_patch.json` + `--append-gold-rsi`）无损追加 1 条盲审遥测、滚动精炼经验手册并更新 `next_run_watch` | 手册严格 **≤180 行**（181–200 行告警，>200 行阻断；合并重复、淘汰已固化项，且不得残留 3 项已证伪税务/ETF/转债旧口径）；JSON 合法、`run_id` 唯一、`total_score == sum(scores)`、`max_score == 30`；须通过 `lint_equity.py --strict` 终检 |
| **Tier B（按需慎改）** | `equity/edition_plan.py`、`lint_equity.py`、`DAILY_REPORT_SPEC.md` 及站内 SVG 图表辅助模块 | 仅当本轮复现了确凿的排期判定、SVG 渲染碰撞、JSON 解析或 Linter 漏网 Bug 时，允许实施 **≤1 处、≤40 行** 最小补丁 | 改后必须通过 **`lint_equity.py --strict`**（0 错 0 警）+ 静态站构建严检（`build_site.py --out _site` + `lint_site.py _site --strict`）+ 单元测试；**任一步报错、误报或网页效果恶化，必须立即回滚**并降级写入 Tier C 提案区 |
| **Tier C（宪法锁定）** | `<REPO_ROOT>/AGENTS.md`、`GEMINI.md`、核心风控红线（四灯阈值、三市危机总熔断阀、AI 跨市 ≤20%、单股 ≤8%、黄金红灯锁、5 万美元购汇红线、6 万美元美国遗产税边界）、工作区三 Skill（`<REPO_ROOT>/.agents/skills/`）、`<REPO_ROOT>/automations/`（含 `scripts/install_sidecars.py`）与本地 `sidecar.json` | **严禁无人值守自改**；仅作为结构化提案写入 `state/RSI_PLAYBOOK.md` 第四节与 `rsi_metrics.json` 的 `tier_c_proposals` | 在最终快报中向用户明确呈报，等待用户在交互会话中明确审批后再执行 |

---

## 三、Step 5 独立只读盲审子代理 Prompt 模板（纯网页三市 + 12 大渠道 + 黄金 SSOT 版）

每次候选源稿通过本地严格门禁后，启动 **1 个独立只读 `research` 子代理**（`Role: "RSI Self-Review & Improvement Auditor"`）：

> 你负责独立只读盲审，所有判断交回主会话。请完整核查本期候选 **三市日报源稿**（`daily/YYYY-MM-DD_HHMM_a_share.md`、`daily/YYYY-MM-DD_HHMM_hk_stock.md`、`daily/YYYY-MM-DD_HHMM_us_stock.md`，含涉及更新的旗舰手册与 `report_meta_*.json`）、**三大扩展数据库与政策日历**（`state/multi_asset_channels.json`、`state/etf_universe.json`、`state/deep_dossiers.json`、`state/policy_calendar.json`，重点核查顶层 `edition_id` 同期锁、4 角色层 12 大渠道小白一句话/今日避坑/统一灯号、181+ 正交 `asset_class × region` ETF 与 `asset_class == "gold" <=> gold_locked=True` 双向锁、焦点股 7 维零模板化深研，以及 **首页 `#sec-policy-calendar` 6–9 条精选与单市场 `#sec-market-news` 无上限全量重要新闻官源真实性**、每刊 **1–2 张 `DAILY_VISUAL` 矢量信息图零碰撞**、4 列 7–14 天全北京时间日历同步与零裸 `P0`/`P1`）、配套同步文件（`daily/INDEX.md`、`daily/CHANGELOG.md`、`daily/SCORECARD.md`、`state/market_state.json`、`state/audit_ledger.md`）、跨项目黄金快照与日报（`../gold/data_snapshot.json` 与本期黄金日报）以及历史经验文件（`state/RSI_PLAYBOOK.md`、`state/rsi_metrics.json`）。按以下 6 个维度逐项打分（1–5 分整数），写清每项缺陷、文件位置、原值、核对依据及其观测时点：
> 1. `data_freshness_and_zero_hallucination`（7 类一手源鲜度、两轨截点落在所标班次 **`[-5 分钟, +6 小时]`** 单向窗口且黄金早于或同分钟于权益【差值 ≤6 小时】、共享宏观键对齐、假日/周末双轨 `brent_live_usd`/`vix_live` 空值口径一致、T+1 挂账与纯读者中文 `data_caveats` 透明披露、无日期规范键、三大扩展库与 `policy_calendar.json` 同期 `edition_id` 锁、A/H 同股 PE 物理学一致、冬夏令时与合约口径零误差、央行 `银发〔2026〕42号` BTC 0% 严禁配仓只读防火墙、无退市股 `00011`、停申基金 `968118` 或未加避坑警示的派息份额 `968001` 误推）
> 2. `prior_forecast_calibration`（上期 `next_run_watch` 与 `SCORECARD.md` 到期预判客观验真、不回避失误、新登检验日均为工作日）
> 3. `plain_language_and_strict_readability`（小白友好三层结构：`30 秒红绿灯白话结论 → 10 万/1 万元钱包实算与三步怎么买 → 机构级 7 维硬核证据`、`DXY`/`COT`/`CDS`/`ERP`/`IRR` 首现配简短白话括注、零居高临下说教口号、零内部工程/RSI/版本词泄露、零跨市涨跌色系混用、跨轨统一税费红线零冲突【`008142`/`008143`、二手存单禁二次转让、交易所公司债 ETF 底层 20% 税、中国居民 20% 境外税与 CRS、`02840.HK` 美国遗产税】、零 3 项已证伪税务/ETF/转债误导、反引号/粗体/段长/3 秒正向自检卡/黄金红灯全载体互斥锁零破口）
> 4. `visual_layout_and_pagination`（JSON 兼容键名；**评判标准全面升级为「纯网页视觉清晰度、SVG 零碰撞与小白 3 分钟可读性」**：首屏 Layer 1 7 枚宏观天气胶囊 + Layer 2 对称 `3×2` 六市场驾驶舱【5 核心含 `rates_bonds_core` 与独立黄金 + 1 非美全球卫星 `non_us_global_satellite`】 + `#sec-policy-calendar` 政策日历 + 3 分钟速读与 4 张 KPI 卡清晰不拥挤、桌面与手机双端自适应零爆版、主刊 ≥2 张 / 守望刊 ≥1 张矢量 SVG 图零文字压线碰撞、`H6` 全量动态不截断、`U5` 动态行高、`U6` 统一 1:1 线性刻度、图文四色评级一致、4 角色层 12 大渠道概览卡【渠道 08 为 10 元起普惠「QDII 跨境基金（场内溢价·直销与支付宝限购）、香港互认与理财通」】与独立详情页及 181+ 正交 `asset_class × region` ETF 概览卡入口清晰、零基础读者 3 分钟能准确看懂红绿灯与下一步动作）
> 5. `research_efficiency_and_source_quality`（阶段 2A 共享 **10 路**并发分工 + 阶段 2B 统一发前独立红队高效拦截核心硬伤、一手官源占比高、有效拦截门户脏缓存或市场谣言、焦点股 7 维深研零模板化）
> 6. `engine_and_guardrail_reliability`（一次过 `lint_equity.py --strict` 与 `lint_readability.py --strict` 零重试、必填 `edition_id`/`edition_type` 与 JSON 零混键零原始 Emoji、`h6.items`/`h6.sector_strip` 与 `hkma_agg_bal_hkd_100m` 规范、`INDEX.md` 零死链零离线附件链接）
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

每刊严禁整文件重写 `rsi_metrics.json`，须分别写裸单条运行对象根 `gold/daily/_rsi_patch.json` 与 `equity/state/_rsi_patch.json` 并调用预授权 `scripts/patch_state_dbs.py --append-gold-rsi` 与 `--append-equity-rsi` 无损追加至 `runs` 数组末尾，保留历史记录（纯网页交付，**不再记录已退役的历史页数字段**；周六 `07:30` 仅发美股主刊或半日市 `holiday_watch` 时，`reports` 仅列当期实际新发日报路径，周五滞后美股盘后终盘与 BTC ETF 官流 `pending_backfills` 挂至下周一 `0730` 美股周度前瞻主刊）。联合班次按 [共享任务提示词](../../../../automations/unified-edition.prompt.md) 与发布门禁脚本登记 `review_closure`。

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
2. **统一终检、K 线刷新与单次纯网页站点发布**：Tier A 经 `--append-gold-rsi` / `--append-equity-rsi` 无损追加（及按需 Tier B）落盘后复跑双轨严检，确认手册行数、JSON 合法性、`run_id` 唯一性及各维分数在 1–5 且合计正确。随后执行 `python3 <REPO_ROOT>/scripts/fetch_kline_data.py --scope all` 刷新全市场 480+ 标的（含 68 只核心基准）静态 K 线分片至 `equity/state/klines/`，推进本期令牌到 `publish`，执行 `python3 <REPO_ROOT>/scripts/publish_site.py --edition-token <token>`（通过 S1–S7 严检；若构建或门禁异常可用预授权 `build_site.py` / `lint_site.py` / `unittest` 排障修复后重跑），再执行 `python3 <REPO_ROOT>/scripts/edition_run.py complete <token>` 验证 GitHub Pages 部署成功即闭环。
