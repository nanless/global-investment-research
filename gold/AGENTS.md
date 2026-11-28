# 黄金深度研报项目规则（global-investment-research/gold）

本目录是「每日黄金深度研报（07:30 早报 / 11:30 午报 / 18:00 晚报 / 周末专项版）」与「跨世纪周期全景主报告（1971–2030）」的纯网页生产工作区，作为顶层宪章 [`../AGENTS.md`](../AGENTS.md) 一体化三班次流水线的 **Step 3** 率先落盘（零离线二进制附件交付）。跨轨编排、全球多指数标准、10+1 调研框架与通用小白三层哲学见 `../AGENTS.md`；完整 JSON Schema、6 道源稿门禁与排障手册按需加载 [`gold-research-publishing`](../.agents/skills/gold-research-publishing/SKILL.md) 及 [`daily/DAILY_FORMAT_SPEC.md`](daily/DAILY_FORMAT_SPEC.md)。

> **实时数值唯一真相源（SSOT）**：本规则仅锁定制度口径、风控红线与校验公式，严禁硬编码随时变动的实盘报价、利率或样本中位数；一切实时数值以 **`data_snapshot.json`** 与 **`master_snapshot.json`** 为唯一真相源。

---

## 1. 工作区资产与跨项目 SSOT 唯一写入权

- **跨项目 SSOT 唯一写入权**：本轨在 Step 3 率先更新 `data_snapshot.json`（含 `edition_id`、`as_of_short`/`as_of_bjt`、多指数优先级 `index_matrix`【伦敦现货金 `XAU` → COMEX 金 `GC` → 沪金 `AU0` → 上金所 `Au99.99`/`Au(T+D)` → 伦敦银/沪银】、全球金银铜/沪金/上金所、`DFII10`、布油官结、CFETS 中间价及日期、买金四步红绿灯 `tier1_gates[4]` 固定 `id` [`real_yield`/`rate_spread`/`vix`/`ny_close`]、`tier_code`/`new_buy_allowed`、VIX 十日日线表 `vix_10d_session_closes` 与 `vix_daily_row_checks`、第四关日期锚、无日期键 `etf_cn`、纯读者中文 `data_caveats`、`rmb_channels`、`cross_ratios`、`institutional_targets` 等；门户三层架构中黄金独立构成 Layer 2 对称 `3×2` 六市场驾驶舱 5 大核心市场之一，BTC 遵照央行 `银发〔2026〕42号` 中国大陆 0% 严禁配仓、仅作 Layer 1 只读全球流动性温度计）并通过 `lint_readability.py --strict`；Step 4 权益轨严格只读校核，严禁逆向改写或输出与黄金红灯冲突的买金建议。
- **主报告独立锁定与惰性加载**：`master_snapshot.json` 与 `data_snapshot.json` 对称，由主报告顶部 `<!-- MASTER_BASELINE {...} -->` 锁定；常规班次仅凭 `master_snapshot.json` 检查 5 大实质更新触发条件（①红绿灯换档；②现货较主报告基线变动 `≥3%` 或国内料价 `≥25 元/克`；③12 大行 2027 中位或四大央行路径实质变；④尾部深熊红线或 60 日新高止损触发；⑤重大税制/渠道升级），仅命中时全量读取并同步主报告。
- **外置日历与三班次抗阻塞契约**：`market_calendar.json` 覆盖至 `2027-06-30`（硬底线 30 天、`<60 天` 提示、核证有效期 90 天）。`edition_validation.py` 支持 **`0730` / `1130` / `1800`** 三个班次，统一强制复算单向截点宽限 **`[-5 分钟, +6 小时]`**（`07:25–13:30` / `11:25–17:30` / `17:55–次日 00:00` CST）与四关精确门槛：Cboe 现货 VIX 独立日历支持节日 4h `pending`、半日市 `provisional_close`、`no_row_confirmed`（官告或 CSV `next_published_date > day` 自证）与普通交易日 3 自然日核销；休市或无 30 分钟连续窗口盘口时（含 `07:30` 与 `11:30` 处于美东非发布窗）`vix_live` 与 `vix_live_as_of` 同时留空。
- **核心产出与质检模块**：收敛主刊 `daily/YYYY-MM-DD_{0730_早报|1130_午报|1800_晚报}_黄金深度研报.md`（同场勘误加 `_r2` 防覆写，3 张 640px SVG 图；`1130_午报` 重点锁定 `11:30 CST` 上金所/沪金早盘官收及同刻 `XAU × USD/CNY ÷ 31.1034768` 平价溢价、四大行金条与品牌金店当日牌价、亚盘美期美债及 `09:15` CFETS/`09:20` 央行 OMO/`09:30` 统计局宏观数据）、全景主报告（7 张图）、公开记分卡 `daily/SCORECARD.md`、历史双账本 `daily/{CHANGELOG,AUDIT_LOG}.md`（支持按月归档至 `daily/archive/` 并保持全量非空行原序）、`daily/RSI_PLAYBOOK.md`（≤180 行 / 硬上限 200 行）、`daily/rsi_metrics.json` 及质检三件套 `lint_readability.py` / `edition_validation.py` / `chart_input.py`。

---

## 2. 冷启动顺序、反幻觉与无人值守安全红线

1. **冷启动继承**：按序读取 `market_calendar.json` → `daily/RSI_PLAYBOOK.md`、`daily/rsi_metrics.json` 最近 5 条与 `daily/SCORECARD.md` → `daily/CHANGELOG.md`（超 150 行仅读前 150 行）→ `data_snapshot.json` 与轻量 `master_snapshot.json` → 上期日报；排版细节核对 `daily/DAILY_FORMAT_SPEC.md`。
2. **零幻觉与跨时区因果**：每条新增数据须标明信源与精确时点，休市或未披露项如实留白并写入纯读者中文 `data_caveats`。严禁把国内 02:30 夜盘与纽约 06:00 终盘的时差混作“国内供需溢价”，午报内盘溢价必须按 `11:30 CST` 同分钟国际金价与在岸即期汇率换算；严禁把 05:00 盘后讲话倒推归因到 02:30 已收盘的内盘价。
3. **调研信源与单跑回退**：一体化班次采用顶层 10+1 并行调研与红队（独立单跑黄金轨回退 5+1），严守美股 `GLD`/`GDX` 官收白名单（`StockAnalysis`/`Investing`/`SSGA`/`VanEck NAV`）、**禁用 `Barchart` 远月滞后合约快照**、善用 `site:shfe.com.cn`/`site:lbma.org.uk` 定向补录与冬/夏令时核对。
4. **无人值守分级写盘与三层 RSI 边界**：定时任务常规禁 `edit_file`（仅允许用 `edit_file` 定点修正当班新建且尚未发布的日报 Markdown，或修复 `equity/state/_edition_patch.json` 校验报错）与未授权 shell 探测，严禁单轮并行打包 >2 个大型 `write_file`——中小文件用 `write_file` 全量写盘；`CHANGELOG.md`/`AUDIT_LOG.md` 一律写微型补丁 `gold/daily/_ledger_patch.json`（`changelog_entry_md` 与 `audit_review_block_md` 须将 `<!-- GOLD_EDITION_CHANGELOG ... -->` / `<!-- GOLD_EDITION_REVIEW ... -->` 置于第 1 行，严禁前放 `#`/`##`/`###` 标题）并调用预授权 `scripts/patch_state_dbs.py --prepend-gold-ledgers` 无损头插（自动校验完整 `GOLD_EDITION_REVIEW` Schema——必填 `as_of_short`、`note`、四关 HTTPS `sources` 与 `forecast_review.status ∈ {"settled","none_due","pending_evidence"}`，严禁 `"tracked"`，支持跨月空锚回退并锁定 `0o644` 权限）；跨月归档上月双账本写 `gold/daily/_archive_patch.json` 走 `--archive-gold-ledgers`；`daily/rsi_metrics.json` 写裸单条运行对象 `gold/daily/_rsi_patch.json` 走 `--append-gold-rsi` 无损追加（防 300s 超时）。正常发刊阶段禁改 `.py` 与规则文件；仅在 Step 5 统一盲审后按 Tier A（`RSI_PLAYBOOK`/`rsi_metrics`）、Tier B（单次 ≤1 处 ≤40 行确定性修 Bug 且必过 `--strict` + 静态站 + 单测，败则回滚）、Tier C（宪法/规则/技能/权限永不自动改，仅提案）执行。

---

## 3. 黄金专属策略、编辑与税制硬红线

1. **唯一买金刻度与风控公式**：
   - 废除正文 `六灯 X/6` 平行分制，严禁“通过 0–3 关即可转黄/开新仓”误导（Gate 5 拦截）；全系统统一 **【历史水位尺】+【买金四步红绿灯（四关全过方亮黄灯）】** 与右侧分批比例 **`30% + 45% + 25%`**（Tier 0 红灯 0% / Tier 1 黄灯 30% / Tier 2 绿灯 +45%→75% / Tier 3 满格 +25%→100%）。
   - **硬止损红线**：`DFII10` 创 60 个交易日收盘新高时机械砍半右侧新仓。
   - **尾部深熊红线**：布伦特原油跌破 80 美元且 `DFII10` 突破 2.95% 并连续站稳 5 个交易日时，将深熊概率由 18% 上调至 25%–30%；四象限概率之和恒 = 100%（完整拆分并附理由，禁偷懒单边概率）。
2. **小白三层、机构级读感与排版红线**（详规见 `daily/DAILY_FORMAT_SPEC.md`）：
   - 严格区分【客观事实】/【逻辑推论】/【概率与失效边界】；全篇配齐 1 句 **利率→汇率→信用→大宗→股票风险溢价（ERP）跨资产传导链**、**未来 48 小时上行/下行双向催化触发线**、**重要一手官源政策/地缘要闻全量覆盖**（取消旧 1–2 条上限：同步录入 `equity/state/policy_calendar.json`，首页 `#sec-policy-calendar` 精选 6–9 条、黄金单页 `#sec-market-news` 无上限全量呈现，正文对重磅政策走完 5 环传导链）与 **4 列未来 7–14 天全北京时间财经与政策日历表**（纯中文级别徽章如重磅/重要，零裸 `P0`/`P1`，严守黄金红灯锁），并鼓励结合价格梯队/流动性拆解嵌入 **`DAILY_VISUAL` 零碰撞矢量信息图**；
   - **零后台审计腔与反重复读**：标题与导语禁写「旧缺口清零」「挂账核销成绩单」类运维话术，正文禁塞冗余核销成绩单表；开篇导语 ≤160 字，同一核心数字提及 ≤3 次；导语所述信号/噪音条数须与 `DAILY_SIGNAL_NOISE` 数组长度精确一致（Gate 5 强制校验）；
   - **`SCORECARD.md` 投资预判纯粹性**：仅登记面向读者的可证伪价格/阈值/宏观预判，严禁混入后台数据回补工单，且历史零篡改；
   - 三档词表与版面硬控：`DXY`/`COT`/`CDS`/`DFII10`/`2Y−FF`/`ON RRP`/`HY OAS`/`IOPV`/`bp` 首现配简短白话括注或交给站内术语浮窗；全篇（含 Layer 2/3 与组件）零内部工程词/版本号/文件名（含 `fetch_kline_data.py`）与 6 个居高临下口号；Layer 0–1 感叹号 0 个（全篇 ≤5）、全篇禁 13 个煽动词、加粗 ≤14%、裸数字不套反引号；640px 矢量图 `DAILY_CHART_TIMELINE` / `DAILY_CHART_CROSS` / `DAILY_CHART_SWITCH` 及通用信息图 `DAILY_VISUAL` 零碰撞且 `L1` 静默牌用暖琥珀菱形禁用绿色。
3. **中国买金、2026 费改、跨境与回购红线**：
   - 按财政部/税务总局 2025 年第 11 号公告区分购入方、是否实物出库及投资或非投资用途。金银首饰零售消费税另按适用规则核算，渠道成交差价以含税价、发票、工费和回购价为准。
   - **场外联接 `008142` / `008143`**：执行顶层 `../AGENTS.md` §6.3。按持有期和购买渠道核对最新合同的申购、运营、销售服务及赎回费用。适用份额持续持有超过一年后停止继续收取销售服务费。旧版工银 `008143` 持有满 30 天免赎回，注意合同更新。支付宝路径为「理财 → 基金」。
   - **场内与离岸**：场内 `518660` 应核对券商佣金与盘中参考净值。香港挂牌的 `02840.HK` 为美国注册信托份额，按美国所在地资产、身份和适用协议核对遗产申报。中国居民个人按所得类别申报境外所得并适用抵免规则。
   - **实物回购与加工**：国有四大行金条绝不拆原厂塑封、留发票证书回原行指定网点（回购常扣 2–4 元/克）；水贝加工按工艺分档报价并支持「料换料零损耗」。

---

## 4. 标准交付门禁（Step 3 → Step 5）

1. 先更新 `data_snapshot.json`（命中 5 阈值时同步主报告与 `master_snapshot.json`），再用 `write_file` 写本刊 Markdown 与 `SCORECARD.md`；跨月归档上月账本时先经 `scripts/patch_state_dbs.py --archive-gold-ledgers` 归档，再经 `--prepend-gold-ledgers` 无损头插 `CHANGELOG.md` 与 `AUDIT_LOG.md`；
2. 必须通过严格门禁（`0 errors, 0 warnings`）：`python3 <REPO_ROOT>/gold/lint_readability.py --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md`（同步主报告时一并传入）；
3. 交棒 Step 4 权益轨完成后，由 Step 5 独立只读盲审闭环经 `scripts/patch_state_dbs.py --append-gold-rsi` 无损追加 `daily/rsi_metrics.json` 并更新 `daily/RSI_PLAYBOOK.md`，复跑双轨严检，运行 `scripts/fetch_kline_data.py --scope all` 刷新全市场 480+ 标的静态 K 线分片后，由 `scripts/publish_site.py --edition-token <token>`（通过 S1–S7 严检）与 `scripts/edition_run.py complete <token>` 完成单次纯网页发布与部署验真。本机伴随实时监测工具 `scripts/realtime_monitor.py` 与 `scripts/wechat_notify.py` 独立运行于定时 56 项权限之外，严格只读消费 `data_snapshot.json` 与 `equity/state/policy_calendar.json`（完全继承黄金红灯锁，告警去重库落于 `.git/realtime-monitor.sqlite3` 零仓库污染）。
