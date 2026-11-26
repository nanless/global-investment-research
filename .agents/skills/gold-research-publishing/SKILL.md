---
name: gold-research-publishing
description: Orchestrates the informed-retail, institutional-grade pure-web gold deep-research and financial report publishing pipeline (converged 07:30 morning / 18:00 evening / weekend editions and the 1971-2030 master report in global-investment-research/gold) with bounded RSI self-review. Use whenever writing, updating, auditing, or troubleshooting daily or master gold research reports, updating data_snapshot.json, invoking the two-stage 一体化 8+1 research and red-team workflow, passing the readability and integrity linter, or publishing the static web portal via scripts/publish_site.py (web-only, no PDF or Word binaries).
---

# Gold Research Publishing System (`gold-research-publishing`)

本 Skill 沉淀了 `global-investment-research/gold` 黄金投研模块的全套研究、编辑、数据、自动化质检、三层安全 RSI 自优化与**纯网页静态门户发布体系（不生成 PDF、Word 或 GitHub Releases 离线附件）**，面向「懂一点基础财经、比普通人多一点市场认知的理性投资者」。

---

## 1. 工作区与核心文件地图

默认工作区：`<REPO_ROOT>/gold`（技能目录：`<REPO_ROOT>/.agents/skills/gold-research-publishing/`；下表未注前缀的相对路径均以 `<REPO_ROOT>/gold/` 为基准）

| 文件路径 | 职责与角色 |
| :--- | :--- |
| `<REPO_ROOT>/AGENTS.md` | Monorepo 顶层唯一编排宪章（定义 07:30 / 18:00 一体化单会话 Step 0–5 流水线、共享 6+1 调研红队、黄金 SSOT 互斥锁与三道严格门禁） |
| `AGENTS.md` / `daily/AGENTS.md` | 工作区常驻项目规则与日报目录专属规则（含跨项目 SSOT 宣言、收敛主刊规范、月度账本归档与防卡壳红线） |
| `data_snapshot.json` | **跨项目单一权威源（SSOT）与日报实时数据源**：在 `07:30` / `18:00` 一体化单会话定时任务中，第 3 步先由黄金模块写入并锁定唯一权威源（含 `edition_id`、`as_of_short`/`as_of_bjt`、现货金/COMEX/SHFE/SGE/铜/`DFII10`、`brent_settle_usd`、`usd_cny_1630`、`cfets_cny_fixing`/`cfets_fixing_date`、四关固定 `id` 精确输入、`vix_10d_session_closes`/`vix_daily_row_checks`、`spot_gold_ny_close_date`/`tier1_gate4_*`、`bank_2027_*_sample_count`、无日期键 **`etf_cn`**、纯读者中文缺口数组 **`data_caveats`** 与红绿灯 `tier_code`/`new_buy_allowed`）；随后第 4 步股研模块以 **0 分钟零滞后**只读校核 |
| `master_snapshot.json` | 主报告独立锁定数据源（与 `data_snapshot.json` 对称，补齐 `edition_id`、`new_buy_allowed`、`cfets_fixing_date` 与 `tier1_gates[].id`；由主报告顶部 `<!-- MASTER_BASELINE {...} -->` 原子锁定，常规班次采用**惰性加载**仅读本快照核验 5 大触发条件） |
| `market_calendar.json` | 外置跨市场休市与冬/夏令时动态日历（已延展至 **`2027-06-30`**，覆盖美/中/港/欧/英/日/印休市与半日市【含耶稣受难日、清明、劳动节、阵亡将士纪念日、六月节补休】、独立 Cboe 现货 VIX 例外、四大央行议息、BCOM/GSCI 调仓及 `2027-03-14` 切夏令时；有效覆盖硬底线 30 天 / `<60 天` 提示 / 核证有效期 90 天） |
| `黄金跨世纪周期与2026-2030终审研究报告.{md,pdf,docx}` | 全景主报告（21–24 页 · 7 张顺排 `图 1`–`图 7` 640px 矢量图） |
| `daily/YYYY-MM-DD_{0730_早报\|1800_晚报}_黄金深度研报.{md,pdf,docx}` | 每日双刊（自 `2026-11-26_1800` 起启用**收敛主刊 5–6 页**，重大议息/危机日可扩至 **7–8 页** · 3 张 640px 矢量图；支持周末专项版与工作日局部休市叠加模式；同日同班次修订加 `_r2` 防覆写锁） |
| `daily/latest_gold.html` | 最新一期日报响应式单文件手机端 HTML（由 `build_daily.py` 原子生成，含 `viewport-fit=cover`、吸顶快捷导航、4–6 KPI 自适应、`.sn-grid` 单栏、640px 矢量图横滑不缩字、表格横滑与护眼深色模式） |
| `daily/SCORECARD.md` | 面向理性投资者的公开可证伪预测记分卡（零内部工程/RSI/脚本文件名词汇、历史记录零篡改，记录已到期回验与当前追踪预判） |
| `daily/DAILY_FORMAT_SPEC.md` | 收敛主刊与全景主报告编写宪章（永久规范） |
| `daily/CHANGELOG.md` / `daily/AUDIT_LOG.md` | 迭代演进总账与独立红队审计账本（与正文物理分离；支持按月归档至 `daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md` 并保留全部历史非空行原序；继承上下文时仅读前 150 行） |
| `daily/RSI_PLAYBOOK.md` | 活体 RSI 动态经验手册（软限 **≤180 行** / 硬上限 **200 行**防膨胀，每班次启动必读、末尾滚动精炼） |
| `daily/rsi_metrics.json` | 结构化 RSI 6 维自评与上期预判回验账本（只追加不删，每满 10 刊触发 Meta-RSI 总复盘） |
| `build_daily.py` | 日报编译器（共享 `parse_markdown_to_html`、4–6 卡 `.kpi-strip.cols-4`、`.sn-grid` 防跨页双栏、图 1 胶囊标签 2D 防撞 `vb_h=284`、图 2 back-to-front 动态刻度、`CHROME_BIN` + 120s×2 重试、`.artifacts.json` 凭据写入、自动原子输出 `daily/latest_gold.html`、支持 `--check`） |
| `build_report.py` | 主报告编译器（校验 `MASTER_BASELINE` 锁、清除 `V7.2` 页脚泄露与“今早”字样、动态月线低点与日期、冻结历史案例图 3、顺排图 1–7、`CHROME_BIN` + 120s×2 重试、`.artifacts.json` 凭据、支持 `--check`） |
| `docx_embed.py` | 纯 Python 原生 ECMA-376 OOXML 引擎（`settings.xml` 自动刷新页码 + Chrome 2× Retina & PIL 自动裁切、`CHROME_BIN` + 60s×2 重试；**严禁 `textutil`**） |
| `lint_readability.py` | 自动化 7 道门禁质检器（支持 `--precheck --strict` 编译前 Gate 0–5 秒检及交付前 `--strict` 全量 Gate 0–6；收敛三档词表、全篇内部词/文件名拦截、加粗 ≤14%、裸数字反引号预警、金店休市/`data_caveats` 放行、Gate 6 `.artifacts.json` 凭据核验、RSI 180/200 行校验，退出码 `0`） |
| `edition_validation.py` | 新刊时点与市场数据校验引擎（6h 班次截点宽限、4h 节日 `pending` 复查、半日市 `provisional_close`、`no_row_confirmed` 公告/CSV 自证、普通交易日 3 自然日核销、30min VIX 盘中窗、30d/90d 日历校验与四关精确复算） |
| `chart_input.py` | `lint_readability.py` 与 `build_daily.py` 共享图表数值解析与区间规范化模块 |
| `<REPO_ROOT>/scripts/publish_site.py` | 全仓库统一静态门户构建、严格站点门禁（`lint_site.py --strict`）、Git 限域提交推送与滚动 Release（`latest-reports`）PDF/DOCX 增量上传引擎（一体化单会话流程末尾全绿后仅执行一次） |

---

## 2. 端到端标准发刊操作流程（SOP）

> **独立 vs 一体化步骤映射**：本节 `Step 1–5` 为黄金轨逻辑编号；在根宪章 `<REPO_ROOT>/AGENTS.md` 与 `07:30`/`18:00` 一体化单会话任务中，对应映射为 `Step 0–1`（双轨 RSI 经验库与双日历/SSOT 冷启动）→ `Step 2A/2B`（**一体化 6+1 日常主力**共享调研红队）→ `Step 3`（对应本节 Step 3–4 黄金 SSOT 优先落盘、编译与 7 门禁严检）→ `Step 4`（股研 0 分钟零滞后接力出版）→ `Step 5`（对应本节 Step 5 统一 RSI 盲审 + 单次 `publish_site.py` 发布）。

### Step 1：继承基线（外置日历驱动 + 惰性主报告加载 + 防卡壳红线）
1. 直接依据系统当前本地时间（`+08:00`）并读取 `market_calendar.json`（覆盖至 `2027-06-30`）判定工作日/周末、早刊（`12:00` 前）/晚刊（`12:00` 后）、当日局部休市叠加模式（A/B/C/GLOBAL）与北美冬/夏令时换算；**定时任务中严禁调用 `date`/`ls`/`curl` 等未授权 shell 命令，亦严禁调用 `edit_file`（所有 Markdown/JSON 落盘一律使用 `write_file` 全量写盘防权限拦截）**。
2. 按序读取：`market_calendar.json` → `daily/RSI_PLAYBOOK.md`（≤180 行）与 `daily/rsi_metrics.json` 最近 5 条记录 → `daily/SCORECARD.md` → `daily/CHANGELOG.md`（超 150 行仅读前 150 行）→ `data_snapshot.json` 与轻量级 `master_snapshot.json` → `CHANGELOG.md` 顶部记录的最新一期日报。
3. **惰性主报告加载**：常规班次仅凭 `master_snapshot.json` 核验主报告 5 大实质更新触发条件，**仅当命中阈值需同步修订主报告时，才全量读取主报告 Markdown**，节省上下文防模型退化。

### Step 2：两阶段多子代理调研与红队复核（一体化 6+1 日常主力 / 独立黄金 5+1 单跑回退）
1. **阶段 2A（并行启动 `research` 子代理）**：每日 `07:30`/`18:00` 一体化单会话班次执行 **一体化 6+1（共享 6 路并发覆盖黄金 + A/港/美 + 跨资产宏观 + 三地社区与谣言）**；仅独立单跑黄金轨时回退至 **独立黄金 5+1（5 路并发）**。强制执行四大信源硬规：
   - **美股 `GLD`/`GDX` 官收白名单**：交叉校验 `StockAnalysis` / `Investing` 历史收盘表 + `SSGA .xlsx` / `VanEck` 官方 NAV，严禁以盘中快照或开盘价充官收；COMEX 期金/期银/期铜检索直加 `"official settlement"`；
   - **远月滞后源黑名单**：**禁用 `Barchart` 远月滞后合约快照**（如 `GCG27` 滞后价），严防跨合约串位；
   - **定向官方补录检索词**：滞后表强制加 `site:shfe.com.cn`（上期所席位龙虎榜/合约分账）、`site:lbma.org.uk`（伦敦金银定盘表）、`"基金份额" "518880"`（国内 ETF 份额流，落盘无日期键 `etf_cn`）；国内夜盘涨跌必以上金所/上期所前一日官方日终清算表为分母；
   - **北美冬/夏令时硬校验**：当前北美冬令时锁定 `EST = BJT - 13h`、`CST = BJT - 14h`（COMEX `13:30 EST` 官结 = `02:30 BJT`、NY 现货 `17:00 EST` = `06:00 BJT`），并动态按 `market_calendar.json` 于 `2027-03-14` 切入夏令时。
2. **阶段 2B（等全部 6 路或 5 路返回后启动统一红队 `research` 子代理）**：对抗核查全部证据与基线快照（一体化班次同步交叉审计双轨共享宏观基准与黄金红灯全载体互斥锁），严苛检验四步红绿灯、`DFII10` 60 日新高止损线、尾部深熊红线与跨时区因果，输出【新增 / 更新 / 修正 / 删除】四张清单。
3. 详见 [./references/5-plus-1-research-playbook.md](./references/5-plus-1-research-playbook.md)。

### Step 3：双快照更新、三账本沉淀与收敛主刊写作
新刊先核对北京刊期与数据截点（班次后 6 小时内）、Cboe 现货指数独立日历（含半日市 `provisional_close`、节日 4h `pending`、`no_row_confirmed` 自证及普通交易日 3 个自然日核销）和四关精确输入，再记录红队来源、预判核验结果并同步三个账本。休市或无合格盘中 VIX 读数时 `vix_live` 与 `vix_live_as_of` 同时留空。字段及台账示例见 [黄金快照契约](./references/directives-and-snapshot-schema.md)。
1. **先更跨项目 SSOT 日报数据源**：用 `write_file` 全量更新 `data_snapshot.json`（标准无日期键 `cross_ratios` 与 `etf_cn`、纯读者中文缺口数组 `data_caveats`、SSOT 裁决字段 `tier_code`/`new_buy_allowed`、四关精确输入、`vix_10d_session_closes`/`vix_daily_row_checks`、`spot_gold_ny_close_date`/`tier1_gate4_*`、`usd_cny_1630`、`bank_2027_*_sample_count`、`rmb_channels` 与算术自洽）。
2. **撰写本刊收敛主刊 Markdown（含同场 `_r2` 防覆写锁）**：自 `2026-11-26_1800` 起目标 **5–6 页**（重大议息/危机日 7–8 页），封面 4–6 张 KPI 卡（推荐 4 张触发 `.kpi-strip.cols-4`）→ Layer 0 静默牌 + 唯一红绿灯 → Layer 1 `.sn-grid` 信号/噪音 + 四步灯 + 10 万钱包账 + A/B/D/C 紧凑行动卡 → Layer 2 精炼深度专题 + 3 张 `DAILY_CHART_*`（图 2 显式标 `"highlight"`）→ Layer 3 `[进阶复核]`；`DAILY_TRUST_BAR` 与 `DAILY_GLOSSARY` 改为可选（0–1 次）；严格执行三档知情散户词汇、全篇零内部词/文件名泄露、加粗 ≤14% 与零裸数字反引号。
3. **物理分离三账本（支持月度归档）**：
   - 将本刊相对路径、`GOLD_EDITION_CHANGELOG` 与【新增 / 更新 / 修正 / 删除】置顶追加至 `daily/CHANGELOG.md`；
   - 将 `GOLD_EDITION_REVIEW`、三大信任资产增量与 8 大类官方来源索引沉淀至 `daily/AUDIT_LOG.md`（两者均支持跨月归档至 `daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md` 并保持历史非空行原序）；
   - 在 `daily/SCORECARD.md` 写入 `GOLD_EDITION_SCORECARD`、公开回验到期预判并追加新追踪项（零内部工程/RSI/脚本词、历史零篡改）。
4. **主报告按 5 大触发条件原子同步**（仅当①红绿灯切换档位；②现货较主报告基线变动 `≥3%` 或国内料价 `≥25 元/克`；③12 大行中位或 G4 路径实质变动；④深熊红线或 60 日新高硬止损触发；⑤重大税制/渠道/结构升级时触发）：此时方全量读取主报告 MD，同步更新对称结构的 `master_snapshot.json`、`MASTER_BASELINE` 与正文。

### Step 4：编译前秒检、编译出版、PDF 抽检与 7 道门禁强制验收（绝对路径裸命令，严禁 `cd &&`）
1. **环境自检（可选，首跑或排障时执行）**：
   ```bash
   python3 <REPO_ROOT>/gold/build_daily.py --check
   python3 <REPO_ROOT>/gold/build_report.py --check
   ```
2. **编译前秒检（`--precheck --strict` · 先拦截再编译）**：
   ```bash
   python3 <REPO_ROOT>/gold/lint_readability.py --precheck --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md
   ```
   *(跳过 Gate 6 PDF/DOCX/手机端 HTML 校验，毫秒级拦停组件错键、图 2 左标签超宽、三档禁词、全篇内部词/文件名泄露、感叹号、加粗密度、裸数字反引号、部分过关开仓话术与快照冲突；0 错 0 警后再编译。)*
3. **编译日报（支持 `CHROME_BIN` + 1 次自动重试，生成 PDF + 原生 OOXML DOCX + `.artifacts.json` 凭据 + `daily/latest_gold.html`）并抽检 PDF 关键页**：
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
1. **启动 1 路独立只读盲审子代理**（一体化单会话班次联合复盘黄金与三地权益各 `/30`；独立黄金班次单轨复盘）：按 6 维量表（满分 30）严苛自审并输出 Tier A/B/C 分级改进清单（模板见 [./references/5-plus-1-research-playbook.md](./references/5-plus-1-research-playbook.md) 第 6 节）。
2. **Tier A（每刊必做 · 全自动生效）**：等盲审返回并修正已证实问题后，追加结构化记录至 `daily/rsi_metrics.json`（联合班次填写 `review_closure`），滚动精炼 `daily/RSI_PLAYBOOK.md`（软限 **≤180 行** / 硬上限 **200 行**，每满 10 刊做 Meta-RSI 复盘）。
3. **Tier B（按需慎做 · 必过验证否则回滚）**：仅当确认存在确定性小 Bug（≤40 行、单次 ≤1 处、**只加固门禁/修 Bug 绝不删禁词或放宽误差**）时可修补工作区脚本（`build_daily.py`/`build_report.py`/`docx_embed.py`/`lint_readability.py`/`edition_validation.py`/`chart_input.py`）与 `DAILY_FORMAT_SPEC.md`，改后必过 `--check` + 重编 + `--strict` + PDF 复核，任一步失败立刻回滚并转提案。
4. **Tier C（宪法红线锁死 · 仅提案）**：核心金融策略红线、`<REPO_ROOT>/AGENTS.md`、`gold/AGENTS.md`、`<REPO_ROOT>/.agents/skills/`、`<REPO_ROOT>/automations/sidecars/`（含 `scripts/install_sidecars.py`）与本地 `sidecar.json` 永不静默修改，写入 `RSI_PLAYBOOK.md` 第四节提案区；补跑 `lint_readability.py --strict` 全绿。
5. **门禁全绿后发布网站**：联合班次按根契约登记进入 `publish`，执行一次：
   ```bash
   python3 <REPO_ROOT>/scripts/publish_site.py --edition-token <token>
   ```
   使用同一 token 验证 Pages 部署及 Release 附件。独立手动发布和本地预演见 [仓库 README](../../../README.md)。

---

## 3. 核心红线速查（违反任一条即禁止交付）

- **跨项目单一权威源（SSOT）与同刊期顺序交接**：每日 `07:30`/`18:00` 一体化单会话班次第 3 步先由黄金模块写入 `data_snapshot.json`（含 `edition_id`/`as_of_short`/`tier_code`/`new_buy_allowed`/`data_caveats`/`etf_cn` 等），第 4 步股研模块只读校验同刊期快照并严守黄金红灯互斥锁，第 5 步统一盲审后单次发布。
- **收敛主刊定位与三档知情散户词汇（`>= 2026-11-26_1800`）**：目标 **5–6 页**（重大日 7–8 页）、4–6 张 KPI 卡、`.sn-grid` 非拆行双栏、`DAILY_TRUST_BAR`/`DAILY_GLOSSARY` 可选；主流词自由用、6 个专业词首次括号轻注、严禁生僻卖方量化词/赌徒口语/跨市涨跌色混用/居高临下说教/平行 `X/6`；**全篇（含 Layer 2/3）零内部工程词、版本号（`V2.x/V6.x/V7.x`）与内部文件名泄露**；Layer 0–1 感叹号 0 个、全篇 ≤5 个；加粗 ≤14%，裸数字不套反引号；全文禁用 13 个煽动词。
- **无人值守防卡壳与抗阻塞核验**：定时任务全程严禁 `edit_file`（一律 `write_file` 全量写盘）；日历（延展至 `2027-06-30`）与 `edition_validation.py` 统一校验 6h 班次截点、4h 节日 `pending`、半日市 `provisional_close`、普通交易日 3 日核销与 `no_row_confirmed` 自证；常规班次惰性只读 `master_snapshot.json`；同场修订加 `_r2`。
- **零幻觉与跨时区真实**：休市/未出项必须如实标注并写入纯读者中文的 `data_caveats`；严守官收白名单与禁用 `Barchart` 远月滞后价；禁止将 `02:30` 国内夜盘与 `06:00` 纽约收盘时差混充国内溢价，禁止 `05:00` 讲话倒推归因 `02:30` 收盘。
- **单一真相刻度与比例统一**：全系统统一 `Tier 0–3` 四步红绿灯（四关全过方亮黄灯，严禁部分过关开仓话术）与 A 类 **`30% + 45% + 25%`** 分批配比；静默紧迫度牌禁用绿色；四象限情景概率之和恒等于 100%。
- **原生 Word 与弹性编译底线**：严禁 macOS `textutil`；`.docx` 必须经 `docx_embed.py` 生成合规 ECMA-376 XML 与 PIL 裁切 2× Retina PNG，Chrome 编译支持 `CHROME_BIN` 与 1 次自动重试并写入 `.artifacts.json` 凭据，临时目录仅建于 `tempfile.mkdtemp` 并在 `finally` 清理。

---

## 4. 快速排障对照表

| 报错现象 / 门禁编号 | 根因 | 标准修复动作 |
| :--- | :--- | :--- |
| `[Gate 0 JSON 语法错 / 缺必填键]` | `<!-- DAILY_* {...} -->` 非法 JSON、漏必填键（如 `edition_id`/`as_of_short`/`checks[].id`）或收敛版可选组件超 1 次 | 核对 [./references/directives-and-snapshot-schema.md](./references/directives-and-snapshot-schema.md) 修复 JSON 与必填键 |
| `[Gate 1 术语/自嗨逃逸 / 内部工程词泄露]` | Layer 0–1 混入禁词（生僻量化词/赌徒口语/收红收绿/说教口号），或全篇任意层泄露 `V2.x/V7.x`、`Subagent`、`红队`、`法证`、内部文件名/`*.py` | 清除全部内部工程词与文件名；生僻量化词改用知情散户白话或保留必要轻注 |
| `[Gate 2 感叹号 / 夸张词]` | Layer 0–1 含 `!`/`！`、收敛新刊全篇感叹号 `>5`（旧刊 `>2`）或全文含 13 个煽动词 | 替换为句号或克制客观表述，区分事实/推论/概率 |
| `[Gate 3 平行打分残留]` | Layer 0–1 出现 `X/6` 或 `六灯` | 删除平行打分，改用四步红绿灯 `满足 X/4 项` |
| `[Gate 4 段落偏长 / 加粗密度偏高 / 裸数字反引号]` | Layer 0–1 自然段 `>240` 字；收敛新刊加粗占比 `>14%` 或用反引号包裸数字/金额/百分比 | 拆短段落、收敛加粗重点、仅对证券/期货代码（如 `518660`）使用反引号 |
| `[Gate 5 快照算术/四关复算/开仓话术冲突]` | `data_snapshot.json` 算术/VIX 十日窗口/四关日期/机构样本中位/`etf_cn` 冲突，或正文含部分过关开仓话术；或金店价未对齐 | 按 `edition_validation.py` 规则复算四关与 VIX；国内休市或未开盘时在 `data_caveats` 规范标注以自动放行金店对齐 |
| `[Gate 6 PDF / DOCX / 手机端 HTML 校验失败]` | 未重新编译、误用 `textutil`、图数不匹配，或 checkout 改 mtime 且 `.artifacts.json` 凭据缺失/失配 | 重新运行 `build_daily.py` / `build_report.py`（可设 `CHROME_BIN`），确认 `.artifacts.json` 与 `daily/latest_gold.html` 同步刷新 |
| `[外置日历 / 公开记分卡 / RSI 校验失败]` | `market_calendar.json` 覆盖不足 30 天或核证超 90 天；`SCORECARD.md` 混入内部词；`RSI_PLAYBOOK.md` 超 180/200 行 | 滚动展期日历；清除 `SCORECARD.md` 内部词；合并精炼 `RSI_PLAYBOOK.md` 至 ≤180 行 |

---

## 5. 按需加载模块化参考手册（Progressive Disclosure）

按当前任务需要，仅读取对应的专题参考文档，避免冗余加载：

1. **收敛版编辑宪章、三档词汇标准、A/B/D/C 画像与中国买金税制回购规则**：[./references/editorial-charter-and-personas.md](./references/editorial-charter-and-personas.md)
2. **10 个 `DAILY_*` 组件 JSON Schema、主报告 7 图映射、双快照（含 `etf_cn`/`data_caveats`）与抗阻塞日历契约**：[./references/directives-and-snapshot-schema.md](./references/directives-and-snapshot-schema.md)
3. **7 道门禁完整规则与词表、`.sn-grid`/`.kpi-strip.cols-4`、图 1 胶囊 2D 防撞、图 2 动态刻度与原生 OOXML 架构**：[./references/7-gates-and-ooxml-engine.md](./references/7-gates-and-ooxml-engine.md)
4. **两阶段调研与红队操作手册（一体化 6+1 日常主力 · 独立黄金 5+1 单跑回退）、七大信源、月度账本归档与 RSI 盲审协议**：[./references/5-plus-1-research-playbook.md](./references/5-plus-1-research-playbook.md)
