---
name: gold-research-publishing
description: Orchestrates the zero-barrier, institutional-grade gold deep-research and financial report publishing pipeline (07:30 morning / 18:00 evening / weekend editions and the 1971-2030 master report in global-investment-research/gold) with bounded RSI self-review. Use whenever writing, updating, auditing, or troubleshooting daily or master gold research reports, updating data_snapshot.json, invoking the two-stage 一体化 6+1 / 独立 5+1 research and red-team workflow, compiling magazine-grade Chrome PDFs and native ECMA-376 OOXML Word (.docx) files, passing the 7-gate readability and integrity linter, or publishing via scripts/publish_site.py, or when reusing this 4-layer financial publishing architecture for similar investor reports.
---

# Gold Research Publishing System (`gold-research-publishing`)

本 Skill 沉淀了 `global-investment-research/gold` 黄金投研模块的全套研究、编辑、数据、排版、原生 Word（OOXML）编译、7 道门禁自动化质检、三层安全 RSI 自优化与统一静态门户发布体系，适用于执行或维护每日黄金双刊（07:30 早报 / 18:00 晚报 / 周末专项版）与跨世纪全景主报告，也可复用于同类面向普通投资者的零门槛、真深度金融研报出版流水线。

---

## 1. 工作区与核心文件地图

默认工作区：`<REPO_ROOT>/gold`（技能目录：`<REPO_ROOT>/.agents/skills/gold-research-publishing/`；下表未注前缀的相对路径均以 `<REPO_ROOT>/gold/` 为基准）

| 文件路径 | 职责与角色 |
| :--- | :--- |
| `<REPO_ROOT>/AGENTS.md` | Monorepo 顶层唯一编排宪章（定义 07:30 / 18:00 一体化单会话 Step 0–5 流水线、共享 6+1 调研红队、黄金 SSOT 互斥锁与三道严格门禁） |
| `AGENTS.md` / `daily/AGENTS.md` | 工作区常驻项目规则与日报目录专属规则（含跨项目 SSOT 宣言与防卡壳红线） |
| `data_snapshot.json` | **跨项目单一权威源（SSOT）与日报实时数据源**：在 `07:30` / `18:00` 一体化单会话定时任务（`daily-global-investment-research` / `daily-global-investment-research-evening`）中，第 3 步先由黄金模块写入并锁定唯一权威源（含现货金/COMEX/SHFE/SGE/铜/`DFII10`、`brent_settle_usd`、`cfets_cny_fixing`、`cfets_fixing_date`、`as_of_short` 与红绿灯 `tier_code`/`new_buy_allowed`）；随后第 4 步股研模块以 **0 分钟零滞后**立即只读校核，彻底消除竞态冲突 |
| `master_snapshot.json` | 主报告独立锁定数据源（由主报告顶部 `<!-- MASTER_BASELINE {...} -->` 原子锁定；常规班次采用**惰性加载**仅读本快照核验 5 大触发条件，彻底根除跨日 `--strict` 死锁与上下文膨胀） |
| `market_calendar.json` | 外置 60+ 天跨市场休市与冬/夏令时动态日历（覆盖美/中/港/欧/英/日/印休市、半日市、四大央行议息、BCOM/GSCI 调仓及 `2027-03-14` 切夏令时，取代硬编码节假日） |
| `黄金跨世纪周期与2026-2030终审研究报告.{md,pdf,docx}` | 全景主报告（V7.2 · 21–24 页 · 7 张顺排 `图 1`–`图 7` 640px 矢量图） |
| `daily/YYYY-MM-DD_{0730_早报\|1800_晚报}_黄金深度研报.{md,pdf,docx}` | 每日双刊（V2.2 · 10–13 页 · 3 张 640px 矢量图；支持周末专项版与工作日局部休市叠加模式；同日同班次修订加 `_r2` 防覆写锁） |
| `daily/latest_gold.html` | 最新一期日报响应式单文件手机端 HTML（由 `build_daily.py` 原子生成，含 `viewport-fit=cover`、吸顶快捷导航、自适应 KPI、640px 矢量图横滑不缩字、表格横滑与护眼深色模式） |
| `daily/SCORECARD.md` | 面向普通投资者的公开可证伪预测记分卡（零内部工程/RSI 词汇、历史记录零篡改，记录已到期回验与当前追踪预判） |
| `daily/DAILY_FORMAT_SPEC.md` | V2.2 零门槛·真深度全文档编写宪章 |
| `daily/CHANGELOG.md` | 迭代演进总账（最新置顶；继承上下文时仅读前 150 行） |
| `daily/AUDIT_LOG.md` | 独立红队质检与法证账本（三大信任资产 + 8 大类官方库索引，与正文物理分离） |
| `daily/RSI_PLAYBOOK.md` | 活体 RSI 动态经验手册（硬上限 ≤180 行防膨胀，每班次启动必读、末尾滚动精炼） |
| `daily/rsi_metrics.json` | 结构化 RSI 6 维自评与上期预判回验账本（只追加不删，每满 10 刊触发 Meta-RSI 总复盘） |
| `build_daily.py` | 日报编译器（V2.2 · 共享 `parse_markdown_to_html` 嵌套列表解析器 · Chrome 90s 超时护栏 · 自动原子生成 `daily/latest_gold.html` · 支持 `--check`） |
| `build_report.py` | 主报告编译器（V7.2 · 校验 `MASTER_BASELINE` 锁 · 冻结历史案例图 3 · 顺排图 1–7 · 支持 `--check`） |
| `docx_embed.py` | 纯 Python 原生 ECMA-376 OOXML 引擎（V2.2 · `settings.xml` 自动刷新页码 + Chrome 2× Retina & PIL 自动裁切；**严禁 `textutil`**） |
| `lint_readability.py` | 自动化 7 道门禁质检器（V2.2 · 支持 `--precheck --strict` 编译前 Gate 0–5 秒检，以及交付前 `--strict` 全量 Gate 0–6 含 PDF/DOCX/`latest_gold.html`、外置日历 `market_calendar.json`、`SCORECARD.md` 零内部词校验与 RSI 校验，退出码 `0`） |
| `<REPO_ROOT>/scripts/publish_site.py` | 全仓库统一静态门户构建、严格站点门禁（`lint_site.py --strict`）、Git 限域提交推送与滚动 Release（`latest-reports`）PDF/DOCX 增量上传引擎（一体化单会话流程末尾全绿后仅执行一次；独立运行黄金时于 Step 5 执行） |

---

## 2. 端到端标准发刊操作流程（SOP）

> **独立 vs 一体化步骤映射**：本节 `Step 1–5` 为独立黄金发刊编号；在根宪章 `<REPO_ROOT>/AGENTS.md` 与 `07:30`/`18:00` 一体化单会话任务中，对应映射为 `Step 0–1`（双轨 RSI 经验库与双日历/SSOT 冷启动）→ `Step 2A/2B`（共享 6+1 调研红队）→ `Step 3`（对应本节 Step 3–4 黄金 SSOT 优先落盘、编译与 7 门禁严检）→ `Step 4`（股研 0 分钟零滞后接力出版）→ `Step 5`（对应本节 Step 5 统一 RSI 盲审 + 单次 `publish_site.py` 发布）。

### Step 1：继承基线（外置日历驱动 + 惰性主报告加载 + 防卡壳红线）
1. 直接依据系统当前本地时间（`+08:00`）并读取 `market_calendar.json` 判定工作日/周末、早刊（`12:00` 前）/晚刊（`12:00` 后）、当日局部休市叠加模式（A/B/C/GLOBAL）与北美冬/夏令时换算；**定时任务中严禁调用 `date`/`ls`/`curl` 等未授权 shell 命令，亦严禁调用 `edit_file`（所有 Markdown/JSON 落盘一律使用 `write_file` 全量写盘防权限拦截）**。
2. 按序读取：`market_calendar.json` → `daily/RSI_PLAYBOOK.md`（≤180 行）与 `daily/rsi_metrics.json` 最近 5 条记录 → `daily/SCORECARD.md` → `daily/CHANGELOG.md`（超 150 行仅读前 150 行）→ `data_snapshot.json` 与轻量级 `master_snapshot.json` → `CHANGELOG.md` 顶部记录的最新一期日报。
3. **惰性主报告加载**：常规班次仅凭 `master_snapshot.json` 核验主报告 5 大实质更新触发条件，**仅当命中阈值需同步修订主报告时，才全量读取主报告 Markdown**，节省上下文防模型退化。

### Step 2：两阶段多子代理调研与红队复核（独立黄金 5+1 / 全资产一体化共享 6+1 · 固化 Tier C #2 官收白/黑名单与冬令时硬校验）
1. **阶段 2A（并行启动专项 `research` 子代理：独立跑黄金 5 路；`daily-global-investment-research*` 一体化单会话任务中共享 6 路覆盖黄金+A/港/美+宏观+舆情）**：通过中英双语 `search_web` 覆盖七大信源，并强制执行已获批固化的四大信源硬规：
   - **美股 `GLD`/`GDX` 官收白名单**：交叉校验 `StockAnalysis` / `Investing` 历史收盘表 + `VanEck` 官方 NAV，严禁以盘中快照或开盘价充官收；COMEX 期金/期银/期铜检索直加 `"official settlement"`；
   - **远月滞后源黑名单**：**禁用 `Barchart` 远月滞后合约快照**（如 `GCG27` 滞后价），严防跨合约串位；
   - **定向官方补录检索词**：滞后表强制加 `site:shfe.com.cn`（上期所席位龙虎榜/合约分账）、`site:lbma.org.uk`（伦敦金银定盘表）、`"基金份额" "518880"`（国内 ETF 份额流）；国内夜盘涨跌必以上金所/上期所前一日官方日终清算表为分母；
   - **北美冬/夏令时硬校验**：当前北美冬令时严格锁定 `EST = BJT - 13h`、`CST = BJT - 14h`（COMEX `13:30 EST` 官结 = `02:30 BJT`、NY 现货 `17:00 EST` = `06:00 BJT`），并动态按 `market_calendar.json` 于 `2027-03-14` 切入夏令时（`EDT = BJT - 12h`、`CDT = BJT - 13h`、`COMEX 01:30 BJT`、`NY 05:00 BJT`）。
2. **阶段 2B（等全部 6 路（一体化）或 5 路（独立）返回后启动统一红队 `research` 子代理）**：将阶段 2A 全部证据与 `master_snapshot.json`/`data_snapshot.json`/`CHANGELOG.md`（一体化班次同步交叉核验 `equity/state/market_state.json` 与共享宏观口径）对抗核查，严苛检验四步红绿灯（`Tier 0–3`）、`DFII10` 60 日新高砍半红线、尾部深熊红线、跨时区因果与黄金红灯全载体互斥锁，输出无情的【新增 / 更新 / 修正 / 删除】四张清单。
3. 详见 [./references/5-plus-1-research-playbook.md](./references/5-plus-1-research-playbook.md)。

### Step 3：双快照更新、三账本沉淀与正文写作
1. **先更跨项目 SSOT 日报数据源**：用 `write_file` 全量更新 `data_snapshot.json`（标准无日期比值键 `cross_ratios`、严禁残留旧日期键、同步维护 `tier_code` 与 `new_buy_allowed` 布尔开关、`tier1_gates[4]`、`rmb_channels` 与涨跌幅精确算术）。
2. **撰写本刊 Markdown（含同场 `_r2` 防覆写锁）**：按 V2.2 四层洋葱结构写作（Layer 0 静默牌 + 唯一红绿灯 → Layer 1 信号/噪音 + 四步灯 + 10 万钱包账 + A/B/D 详讲与 C 实算 → Layer 2 充实大白话深读 + 3 张 `DAILY_CHART_*`【图 2 显式标 `"highlight"` 防误亮个股】→ Layer 3 `[进阶复核]` + 3 行 `DAILY_TRUST_BAR`）；同日同班次若需二次修订/重发，新档加 `_r2` 后缀严禁覆盖原归档。
3. **物理分离三账本**：
   - 将本刊相对路径与【新增 / 更新 / 修正 / 删除】置顶追加写入 `daily/CHANGELOG.md`；
   - 将新增谣言证伪、模型升级、细节校准与 8 大类官方来源索引沉淀至 `daily/AUDIT_LOG.md`，切勿塞入正文前两层；
   - 在面向读者的 `daily/SCORECARD.md` 公开回验到期预判并追加新追踪项（零内部工程/RSI 词汇、历史记录零篡改）。
4. **主报告按 5 大触发条件原子同步**（仅当①红绿灯切换档位；②现货较主报告基线变动 `≥3%` 或国内料价 `≥25 元/克`；③12 大行中位或 G4 路径实质变动；④深熊红线或 60 日新高硬止损触发；⑤重大税制/渠道/结构升级时触发）：此时方全量读取主报告 MD，同步更新 `master_snapshot.json`、主报告 `<!-- MASTER_BASELINE {...} -->` 与正文，确保封面、7 图与正文原子一致。

### Step 4：编译前秒检、编译出版、PDF 抽检与 7 道门禁强制验收（绝对路径裸命令，严禁 `cd &&`）
1. **环境自检（可选，首跑或排障时执行）**：
   ```bash
   python3 <REPO_ROOT>/gold/build_daily.py --check
   python3 <REPO_ROOT>/gold/build_report.py --check
   ```
2. **编译前秒检（`--precheck --strict` · 先拦截错键/撞栏/禁词再编译）**：
   ```bash
   python3 <REPO_ROOT>/gold/lint_readability.py --precheck --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md
   ```
   *(跳过尚未生成的 Gate 6 PDF/DOCX 校验，毫秒级拦停 7 类组件嵌套错键、图 2 左标签超宽、禁词、感叹号与快照算术冲突；0 错 0 警后再编译。)*
3. **编译日报（生成 PDF + 原生 OOXML DOCX + 最新日报自动原子输出 `daily/latest_gold.html`）并抽检 PDF 关键页**：
   ```bash
   python3 <REPO_ROOT>/gold/build_daily.py <REPO_ROOT>/gold/daily/<本刊文件名>.md
   ```
4. **编译主报告（仅满足上述 5 大触发条件时执行）**：
   ```bash
   python3 <REPO_ROOT>/gold/build_report.py
   ```
5. **强制 7 道门禁全量严格验收（必须退出码 `0`、0 errors、0 warnings）**：
   ```bash
   python3 <REPO_ROOT>/gold/lint_readability.py --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md
   ```
   *(若同步更新了主报告，一并追加 `<REPO_ROOT>/gold/黄金跨世纪周期与2026-2030终审研究报告.md`。)*

### Step 5：独立 RSI 自我复盘与三层递归优化闭环（门禁全绿后强制执行）
1. **启动 1 路独立只读盲审子代理**（一体化单会话班次调用 `Unified RSI Self-Review & Improvement Auditor` 联合复盘黄金与全球权益 A/港/美股各 `/30`；独立黄金班次调用 `RSI Self-Review & Improvement Auditor`）：对照本刊 MD、PDF 视觉抽检结果、首次 `--strict` 报错记录与上期预判清单，按 6 维量表（每维 1–5 分，总分 `/30`）无情复盘并输出 Tier A/B/C 分级改进清单（完整提示词模板见 [./references/5-plus-1-research-playbook.md](./references/5-plus-1-research-playbook.md) 第 6 节）。
2. **Tier A（每刊必做 · 全自动生效）**：追加结构化记录至 `daily/rsi_metrics.json`，提炼 1–3 条高杠杆规则滚动合并精炼入 `daily/RSI_PLAYBOOK.md`（严格维持 ≤180 行，每满 10 刊做一次 Meta-RSI 趋势复盘）。
3. **Tier B（按需慎做 · 必过验证否则回滚）**：仅当确认存在确定性小 Bug（≤40 行、单次 ≤1 处、**只加固门禁/修 Bug 绝不删禁词或放宽误差**）时可安全修补工作区脚本，改后必过 `--check` + 重编 + `--strict` + PDF 复核，任一步失败立刻回滚并降级为提案。
4. **Tier C（宪法红线锁死 · 仅提案）**：核心金融策略红线、`<REPO_ROOT>/AGENTS.md`、`<REPO_ROOT>/.agents/skills/`、`<REPO_ROOT>/automations/sidecars/`（含 `scripts/install_sidecars.py`）与本地 `sidecar.json` 永不静默篡改，写入 `RSI_PLAYBOOK.md` 第四节提案区并在用户快报末尾呈报；最后补跑 `lint_readability.py --strict` 确保 RSI 手册与账本零错零警告。
5. **门禁全绿后发布网站（Web Publish）**：在一键全资产一体化单会话任务（`daily-global-investment-research` / `daily-global-investment-research-evening`）中，待第 3 步黄金 SSOT、第 4 步股研（0 分钟零滞后直读黄金快照）及第 5 步统一 RSI 终检全部通过 `--strict` 后，统一执行一次站点发布脚本（单独手动发刊黄金时亦于本步执行）：
   ```bash
   python3 <REPO_ROOT>/scripts/publish_site.py
   ```
   *(自动构建响应式静态站 `_site`、通过 `lint_site.py --strict`、SSH 推送至 GitHub Pages 并按 SHA256 增量同步滚动 Release PDF/DOCX；本地预演可附加 `--dry-run`。)*

---

## 3. 核心红线速查（违反任一条即禁止交付）

- **跨项目单一权威源（SSOT）与一体化 0 分钟零滞后宣言**：全仓库定时任务已统一为 `07:30` 早报（`daily-global-investment-research`）与 `18:00` 晚报（`daily-global-investment-research-evening`）两班单会话串行流水线：第 3 步由黄金模块率先出版并拥有 `data_snapshot.json`（现货金/COMEX/SHFE/SGE/铜/`DFII10`、`brent_settle_usd`、`cfets_cny_fixing`、`cfets_fixing_date`、`as_of_short` 与红绿灯 `tier_code`/`new_buy_allowed`）的唯一写入权；第 4 步股研模块（`global-investment-research/equity`）在黄金落盘且门禁全绿后以 **0 分钟零滞后**立即只读校验该快照，严禁逆向改写或与黄金红绿灯指令打架，最终在第 5 步统一 RSI 后单次调用 `scripts/publish_site.py` 发布全站。
- **无人值守防卡壳与治理闭环**：定时任务全程严禁调用 `edit_file`（一律 `write_file` 全量写盘）；休市与时令由 `market_calendar.json` 驱动；常规班次采用惰性主报告加载（只读 `master_snapshot.json`）；同场修订加 `_r2` 防覆写；每刊同步更新公开记分卡 `daily/SCORECARD.md` 并输出 `daily/latest_gold.html`。
- **零幻觉与跨时区真实**：休市必须写「休市 / 沿用上一终盘（标注时点）」；严守官收白名单（`StockAnalysis`/`Investing`/`VanEck NAV`）、禁用 `Barchart` 远月滞后价、`site:shfe.com.cn`/`site:lbma.org.uk` 定向补录与北美冬/夏令时硬校验；禁止将 `02:30` 国内夜盘与 `06:00` 纽约收盘时差混充国内溢价，禁止 `05:00` 讲话倒推归因 `02:30` 收盘。
- **冷静语调与零黑话首屏**：Layer 0–1 严禁感叹号（0 个）、严禁 **68 个禁词（47 个 ASCII/版本代码 + 21 个中文/混合黑话）**、严禁已废除的 `X.X/6` 平行分制；全文禁用 13 个夸张煽动词。
- **单一真相刻度与比例统一**：全系统统一 `Tier 0–3` 四步红绿灯与 A 类 **`30% + 45% + 25%`** 分批配比；静默紧迫度牌禁用绿色；四象限情景概率之和恒等于 100%。
- **原生 Word 架构底线**：严禁使用 macOS `textutil`；所有 `.docx` 必须经 `docx_embed.py` 生成真 `<w:tbl>`、合规 ECMA-376 XML 与 PIL 自动裁切的 2× Retina PNG 图表，且临时文件仅在系统临时目录（`tempfile.mkdtemp`）生成并在 `finally` 清理。

---

## 4. 快速排障对照表

| 报错现象 / 门禁编号 | 根因 | 标准修复动作 |
| :--- | :--- | :--- |
| `[Gate 0 JSON 语法错 / 缺必填键]` | `<!-- DAILY_* {...} -->` 非法 JSON 或漏必填键 | 核对 [./references/directives-and-snapshot-schema.md](./references/directives-and-snapshot-schema.md) 补齐双引号、逗号与必填键 |
| `[Gate 1 术语/自嗨逃逸]` | Layer 0–1（正文或组件内）混入 **68 个禁词（47 个 ASCII/版本代码 + 21 个中文/混合黑话）** 之一 | 将专业代码移入 Layer 3，Layer 0–1 改用人话翻译（如「真实利息」「两债利差」） |
| `[Gate 2 感叹号 / 夸张词]` | Layer 0–1 含 `!`/`！` 或全文含 13 个煽动词 | 替换为句号或冷静客观表述，区分事实/推论/概率 |
| `[Gate 3 平行打分残留]` | Layer 0–1 出现 `X.0/6` 或 `X.5/6` | 删除平行打分，改用四步红绿灯 `满足 X/4 项` |
| `[Gate 5 快照算术冲突 / 过时事实]` | `data_snapshot.json` 涨跌/差额/比值/SSOT `new_buy_allowed` 冲突，或正文含旧事实 | 重算快照精确数值；若跨交易日遇到跨月/跨年与双快照维护问题，参见 [./references/7-gates-and-ooxml-engine.md](./references/7-gates-and-ooxml-engine.md) 第 3 节 |
| `[Gate 6 DOCX / 手机端 HTML 校验失败]` | 未重新编译 `.docx`/`latest_gold.html`、误用 `textutil` 或图数不匹配 | 重新运行 `build_daily.py` / `build_report.py`（检查 Chrome、Pillow、BeautifulSoup4 依赖与 `daily/latest_gold.html` ≥5KB 且含 `viewport`） |
| `[外置日历 / 公开记分卡校验失败]` | `market_calendar.json` 缺失/非法 JSON，或 `daily/SCORECARD.md` 混入内部工程/RSI 词 | 修复 `market_calendar.json` 合法性并清除 `SCORECARD.md` 中所有工程/RSI 术语 |
| SVG 内出现乱码方块或 Skia 渲染异常 | 自定义 SVG 文本未过 `svg_esc()` 残留位图 Emoji | 所有 SVG `<text>` 必须经 `svg_esc()` 过滤并加 `HALO` 描边 |

---

## 5. 按需加载模块化参考手册（Progressive Disclosure）

按当前任务需要，仅读取对应的专题参考文档，避免冗余加载：

1. **编辑宪章、四层洋葱、A/B/D/C 画像与中国零售税制回购规则**：[./references/editorial-charter-and-personas.md](./references/editorial-charter-and-personas.md)
2. **10 个 `DAILY_*` 组件 JSON Schema、主报告 7 图映射、`data_snapshot.json` 契约与四轨矩阵**：[./references/directives-and-snapshot-schema.md](./references/directives-and-snapshot-schema.md)
3. **7 道门禁完整规则与词表、智能表格、640px 矢量图与纯 Python 原生 OOXML 引擎架构（含跨日维护注意事项）**：[./references/7-gates-and-ooxml-engine.md](./references/7-gates-and-ooxml-engine.md)
4. **两阶段调研（一体化 6+1 / 独立 5+1）与红队提示词模板、七大信源清单、周末专项切换与三账本分离协议**：[./references/5-plus-1-research-playbook.md](./references/5-plus-1-research-playbook.md)
