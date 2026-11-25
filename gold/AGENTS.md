# 黄金深度研报项目规则（global-investment-research/gold）

本目录是面向普通理性投资者的「每日黄金深度研报（07:30 早报 & 18:00 晚报 / 周末专项版）」与「跨世纪周期全景主报告（1971–2030）」生产与出版工作区，隶属于仓库顶层统一编排宪章 `../AGENTS.md`（07:30 / 18:00 一体化单会话流水线的 Step 3）。以下规则为黄金子轨的永久约束；完整 JSON Schema、7 道门禁词表、OOXML 引擎架构与调研提示词请按需加载本机全局 Skill **`gold-research-publishing`**（`~/.gemini/config/skills/gold-research-publishing/SKILL.md`）。

---

## 1. 核心工作区资产地图与跨项目单一权威源（SSOT）

- **双快照防撕裂数据源与跨项目 SSOT 宣言**：
  - **跨项目单一权威源（SSOT）**：在每日 **`07:30` / `18:00` CST** 一体化单会话流水线中，黄金深度研报在 **Step 3** 率先落盘、编译并严检通过，拥有 `data_snapshot.json`（涵盖国际现货金、COMEX 期金、SHFE 沪金、SGE 现货、COMEX 期铜、`DFII10` 实际利率、以及买金四步红绿灯 `tier_code` 与新买开关 `new_buy_allowed` 等核心裁决字段）的**唯一写入权**；紧随其后的全球股研模块（`../equity/`）在 **Step 4** 对刚刷新的本快照执行**零延迟只读校验**（详见仓库根规则 `../AGENTS.md`），严禁逆向修改黄金快照，亦严禁输出与黄金红绿灯指令冲突的买金建议；
  - 日报唯一实时数据源：`data_snapshot.json`（涵盖版本号、L0/L1/L2 警报、四步红绿灯 `tier1_gates[4]`、`tier_code`/`new_buy_allowed`、全球金银铜/沪金/上金所实盘、美债/汇率/估值锚、油气/风险资产/金矿/信用、四大央行与 12 大行 2027 中位、`rmb_channels`、`cross_ratios`、`monthly_candles`、`mechanical_calendar`、`institutional_targets`、`trust_assets`）；
  - 主报告独立锁定数据源：`master_snapshot.json`（由主报告顶部 `<!-- MASTER_BASELINE {"as_of_short": "...", "snapshot": "master_snapshot.json"} -->` 原子锁定，`build_report.py` 与 `lint_readability.py` 强制校验一致，彻底根除跨日更新日报导致主报告 `--strict` 死锁或图表/正文撕裂）；
  - 外置跨市场休市与时令日历：`market_calendar.json`（覆盖 60+ 天美/中/港/欧/英/日/印休市、半日市、四大央行议息、BCOM/GSCI 调仓及北美冬/夏令时切换规则，取代硬编码节假日）。
- **全景主报告（21–24 页 · 7 图顺排 `图 1`–`图 7`）**：`黄金跨世纪周期与2026-2030终审研究报告.{md,pdf,docx}`（现为 V7.2）。
- **每日双刊、手机端快阅、公开记分卡、双账本与 RSI 资产（10–13 页 · 3 图）**：`daily/YYYY-MM-DD_{0730_早报|1800_晚报}_黄金深度研报.{md,pdf,docx}`（V2.2，同日同班次修订加 `_r2` 防覆写；历史早期 `1630_午报` 兼容保留）、`daily/latest_gold.html`（最新日报响应式单文件手机端 HTML，含吸顶导航、640px 图表横滑与护眼深色模式）、`daily/SCORECARD.md`（面向读者零工程词的公开可证伪预测记分卡，历史零篡改）、`daily/DAILY_FORMAT_SPEC.md`、`daily/CHANGELOG.md`、`daily/AUDIT_LOG.md`、`daily/RSI_PLAYBOOK.md`（≤180 行精炼动态经验库）与 `daily/rsi_metrics.json`（每刊 6 维自审与预判验真账本；旧版历史归档于 `daily/archive_v6/`）。
- **四大出版与质检引擎**：
  - `build_daily.py`（日报 MD → PDF + 原生 OOXML DOCX + 最新日报自动原子输出 `daily/latest_gold.html`，共享 `parse_markdown_to_html` 嵌套列表解析器，Chrome 90s 超时护栏，支持 `--check`）
  - `build_report.py`（主报告 MD + `master_snapshot.json` → PDF + 原生 OOXML DOCX，强制校验 `MASTER_BASELINE` 锁，冻结历史教学案例图 3，支持 `--check`）
  - `docx_embed.py`（纯 Python 原生 ECMA-376 OOXML 生成器 + `word/settings.xml` 自动刷新页码 + Chrome 2× Retina & PIL 自动裁切图表光栅化引擎）
  - `lint_readability.py`（自动化 7 道门禁质检，支持 `--precheck --strict` 编译前 Gate 0–5 嵌套键名/图 2 防撞秒检，以及交付前强制 `--strict` 全量 Gate 0–6 含 PDF/DOCX/手机端 HTML 时效、外置日历 `market_calendar.json`、公开记分卡 `daily/SCORECARD.md` 无工程词校验与 RSI 防膨胀校验，零错零警告）

---

## 2. 强制启动与上下文继承顺序（含惰性主报告加载）

每次续写、更新或修订研报前，必须按以下顺序继承既有基线：
1. 读取 `market_calendar.json`，依据系统当前本地时间（`+08:00`）查明当日休市叠加模式（A/B/C/GLOBAL）、半日市/重要议息窗口与北美冬/夏令时换算规则（严禁硬编码节假日）；
2. 读取 `daily/RSI_PLAYBOOK.md`（≤180 行）、`daily/rsi_metrics.json` 最近 5 条记录与 `daily/SCORECARD.md`，继承历史高杠杆避坑经验与待回验公开预判；
3. 读取 `daily/CHANGELOG.md`（若超过 150 行，**仅读前 150 行**以防上下文膨胀），确认最新一期相对路径与历史纠错；
4. 读取 `data_snapshot.json` 与轻量级 `master_snapshot.json`（**惰性主报告加载**：常规班次仅凭 `master_snapshot.json` 核验主报告 5 大实质更新触发条件，**仅当命中阈值需同步修订主报告时，才全量读取 78KB 主报告 Markdown**，大幅节省上下文防止模型注意退化）；
5. 读取 `CHANGELOG.md` 顶部记录的最新一期日报；涉及排版或结构变更时，核对 `daily/DAILY_FORMAT_SPEC.md`。

---

## 3. 零幻觉、跨时区真实性与防越权调研铁律

1. **反幻觉铁律**：每一条新增报价、政策、研报或传闻必须标明**信源 + 精确时点**。某市场休市或搜不到当日新报价时，必须如实写「休市 / 沿用上一终盘（标注时点）」，严禁猜测、外推或编造任何数字。
2. **跨时区因果红线**：
   - 严禁把国内 02:30 夜盘收盘价与纽约 06:00 现货终盘价之间的 3.5 小时时差混充为「国内供需溢价」（比较溢价必须使用同一时点折算）；
   - 严禁把 05:00 等盘后官员讲话或突发新闻因果倒置地归因到 02:30 已经收盘的国内夜盘价格。
3. **共享 6+1（单跑 5+1）两阶段调研机制、官收信源白/黑名单与防卡壳/防篡改红线**：
   - 所有外部联网实盘与资讯调研必须通过两阶段 `research` 子代理使用中英双语 `search_web` 覆盖七大信源完成：在每日 `07:30` / `18:00` 一体化班次中执行仓库级 **阶段 2A 共享 6 路并发调研 + 阶段 2B 1 路统一红队**（详见 `../AGENTS.md`；独立单跑黄金轨时沿用 5 路并行 + 第 6 路红队），严格遵守美股 `GLD`/`GDX` 官收白名单 `StockAnalysis`/`Investing`/`VanEck NAV`、**禁用 `Barchart` 远月滞后合约快照**、`site:shfe.com.cn`/`site:lbma.org.uk` 定向补录与 `market_calendar.json` 北美冬/夏令时硬校验，**必须等全部调研子代理返回后**再启动红队复核审计，输出【新增 / 更新 / 修正 / 删除】四张清单；
   - **无人值守防卡壳铁律**：在定时自动化任务中，主代理严禁调用 `date`、`ls`、`curl` 等未授权外部抓取或探测 shell 命令，**亦严禁调用 `edit_file`**（所有 Markdown/JSON 更新一律使用 `write_file` 全量写盘，彻底杜绝交互权限拦截或上下文漂移），**仅运行预授权的绝对路径裸命令**（不加 `cd &&` 前缀）执行 Python 编译与质检脚本，直接依据系统本地时间（`+08:00`）+ `market_calendar.json` 判定刊期与休市叠加；同日同班次若需二次重发/勘误，新档加 `_r2` 后缀严禁覆盖原归档；
   - **定时任务三层 RSI 防篡改与防退化铁律**：在正常发刊编译阶段（Step 1–4）严禁修改任何 `.py` 脚本与规则文件；仅在每刊 7 道门禁全绿交付验收通过后的 **Step 5 RSI 闭环阶段** 按三层分级执行自进化——**Tier A**（`daily/RSI_PLAYBOOK.md` ≤180 行 + `daily/rsi_metrics.json`）全自动迭代；**Tier B**（工作区 `.py` 或 `DAILY_FORMAT_SPEC.md` 确凿小 Bug）仅允许单次 ≤1 处最小补丁（≤40 行，**只允许加固门禁或修 Bug，严禁删禁词/放宽误差**）且必须通过 `--check` + 重编 + `--strict` + PDF 视觉复核，**任一步失败立即回滚并转提案**；**Tier C**（核心风控策略红线、`AGENTS.md`、`sidecar.json`、全局 Skill）永不静默修改，仅写入提案区待用户审批。

---

## 4. V2.2 / V7.2 面向普通人的五大编辑与金融红线

1. **家庭理财医生冷静语调与少即是多**：
   - 严格区分 **【客观事实】/【逻辑推论】/【概率与失效边界】**；概率优先用「如果重演 10 次大概出现几次」表达；
   - Layer 0–1 每句 ≤2 个数字、每条论点 ≤2 个锚点数字，关键指标配齐 **【当前读数 + 历史水位尺 + 体感翻译】**；
   - **Layer 0–1 严禁出现任何感叹号（`!` / `！`，规定为 0）**，全文感叹号 ≤2；
   - 全文（含组件 JSON 字符串）禁用 13 个夸张/煽动词：`神准`、`分毫不差`、`100%胜率`、`100% 胜率`、`无情推翻`、`核雷`、`拉爆`、`血洗`、`焊死`、`史诗级`、`史诗轧空`、`彻底打脸`、`惊天验证`。
2. **四层洋葱物理隔离**：
   - **Layer 0（10 秒行动首屏）**：三色静默紧迫度牌（`L0` 沉稳灰蓝 / `L1` 暖琥珀 / `L2` 深红警示，**禁用绿色**防与绿灯可买撞色）+ 唯一买金红绿灯 + ≤80 字核心结论与底线风险。0 英文代码、0 感叹号、0 内部版本号、优先报人民币元/克。
   - **Layer 1（3 分钟白话自包含核心）**：信号（0–2 件）vs 噪音（3–5 件）双栏卡 + 买金四步红绿灯（满足 X/4 项）+ 10 万元人民币钱包账（6 周内锚定现行汇率，跨年显式标注汇率联动区间 `6.20–6.45`，如 2027 大行中位 `6.44`）+ **A（空仓）/ B（B1 轻仓套牢 · B2 重仓焦虑 · B3 早年浮盈）/ D（想学宏观原理）重点详讲操作卡（附 C 类婚庆/实体省钱实算）**。自然段 ≤240 字；**严禁出现 `DFII10`、`2Y-FF`、`au2702`、`OGZ26`、`BCOM`、`Subagent`、`子代理`、`梭哈`、`短线波段`、`放鹰`、`鹰派`、`提保`、`上影线`、`即征即退`、`高弹性` 等 68 个禁词（47 个 ASCII/版本代码 + 21 个中文/混合黑话）**。
   - **Layer 2（8–12 分钟大白话深读专题）**：**必须以 `# 第二部分` / `## 专题一` / `## 周末专题` 或 `DAILY_LAYER_BADGE`（`tone: "deep"`）起头，以触发门禁分层与自动分页**；平时早/晚报保留充实大白话深读篇幅（10–13 页），主报告保持全景百科深度（21–24 页）；配 30 秒人话词典、生活类比与类比边界；严禁日报与主报告机械互抄。
   - **Layer 3（可选进阶专业复核区）**：顶部挂 `DAILY_LAYER_BADGE`（`tone: "pro"`），保留精确代码、公式、Tier 0–3 细则、高门槛工具（明标 50 万元门槛）与 D 类自学自查路径；版本演进 Diff、子代理路数与人名消歧**物理分离**至 `daily/CHANGELOG.md` 与 `daily/AUDIT_LOG.md`，正文文末仅留 3 行 `DAILY_TRUST_BAR`。
3. **单一真相刻度与核心策略口径**：
   - 正文 Layer 0–1 彻底废除 `六灯 X.X/6` 平行分制（由正则强制拦截），统一仅用 **【历史水位尺】+【买金四步红绿灯（满足 X/4 项）】**；
   - 四档右侧建仓与 A 类分批比例全系统唯一统一为 **`30% + 45% + 25%`**（`Tier 0` 红灯 0% / `Tier 1` 黄灯 30% / `Tier 2` 绿灯 +45%→75% / `Tier 3` 满格 +25%→100%）；
   - 硬止损红线：`DFII10` 创 60 个交易日收盘新高时机械砍半右侧新仓；
   - 尾部深熊升级红线：布伦特原油跌破 80 美元且 `DFII10` 突破 2.95% 并连续站稳 5 个交易日时，将深熊概率由 18% 上调至 25%–30%；四象限情景概率之和必须恒等于 100%。
4. **中国普通人买金、税制与回购事实红线**：
   - 财政部/税务总局 2025 年第 11 号公告（2025-10-29）：区分投资与非投资增值税路径，并计入 **5% 金银首饰零售消费税**；非会员零售水贝投资金条存在约 13% 增值税转嫁坑；
   - 场外黄金 ETF 联接基金透明费率铁律：**A 类（`008142`）** 仅收 `0.20%/年` 运营费 + 支付宝/天天 1 折申购 `0.06%` + 持有满 1 年免赎回（7天–1年 `0.10%`），拿超 **167 天（约 5.5 个月）** 即比 C 类省钱；**C 类（`008143`/`000217`/`002611`）** 0 申购费但另收 **`0.35%/年` 销售服务费（合计 `0.55%/年`）**，且持有 `<7 天` 1.50%、`7–29 天` 0.10%、**满 30 天方免赎回费**（严禁误写为「7 天后免赎回费」或把 A/C 笼统合写为 `0.20%`）；支付宝应走「理财 → 基金」，勿走首页「黄金」频道（主推 ~0.95%/年高费场外 C 类；另国有行「积存金」赎回常扣 0.50% 或点差，不宜短线进出）；
   - 场内低费率 ETF（如 `518660` 合计 0.20%）须提示核查券商「免五」与 IOPV 溢价（<0.3%）；
   - 国有四大行投资金条回购铁律：**绝不拆原厂塑封、保留发票与证书、回原行指定网点**（本行金条回购扣 2–4 元/克）；水贝加工按工艺分档报价（素圈 10–20 元/克、古法 30–50 元/克、3D 硬金一般不熔料），支持「料换料零损耗」。
5. **透明可追溯原则**：所有新增观点与数据变动不得在正文中隐瞒历史修正，须同步留痕于独立双账本（`daily/CHANGELOG.md` 与 `daily/AUDIT_LOG.md`），正文仅以 3 行质检徽章指引核查。

---

## 5. 单源数据与出版级编译工程铁律

1. **双快照原子算术一致性**：日报每次先更新 `data_snapshot.json`（跨资产比值统一使用无日期键 `cross_ratios`，严禁残留带日期旧键）；仅当满足主报告 **5 大实质更新触发条件**（① 买金四步红绿灯切换档位；② 国际现货金较主报告基线变动 `≥3%` 或国内料价变动 `≥25 元/克`；③ 12 大行 2027 中位目标或四大央行利率路径实质改变；④ 尾部深熊红线或 60 日新高硬止损触发；⑤ 重大税制/渠道/结构性研究升级）时，方同步修订主报告 MD、`MASTER_BASELINE` 与 `master_snapshot.json` 并运行 `build_report.py`。
2. **指令与表格规范**：10 个 `DAILY_*` 组件必须为独立 HTML 注释中的合法 JSON（缺必填键、拼写错或坏 JSON 均会被拦截）；Markdown 表格共享 `render_md_table`（自动对齐、防折行 `col-nowrap` 总宽 ≤25.0、等宽数字 `tabular-nums`、原子单位保护、转义 `\|` 支持、紧凑表 `table-keep` 防孤行、矢量状态胶囊），正文及组件 JSON 禁止残留裸 HTML 布局标签。
3. **矢量图表规范**：所有 SVG 采用 `viewBox="0 0 640 ..."`、主标签字号 `≥10.2px`（辅助刻度/徽章 `9.8–10.0px`，A4 打印清晰可读）、全部文本经 `svg_esc()` 剔除位图 Emoji 与控制字符（保留矢量 `✓`/`✕`）、标签带白色描边光晕 `HALO`；涨跌条形图采用 1:1 诚实线性比例 + 防越界动态 `x_zero` + 中文惯例「红涨 / 绿跌」+ 仅标现货/期货主角黄金（支持显式 `highlight` 键，禁止误亮金矿/金饰股票）+ 独立反向指标栏；`L1` 暖琥珀警报牌采用菱形标记 `.dot-diamond` 与买金红绿灯圆点物理区分。
4. **原生 ECMA-376 OOXML Word 红线（严禁 `textutil`）**：
   - **严禁调用 macOS `textutil` 转换 `.docx`**（会静默摧毁全部表格与卡片边框）；
   - 必须通过 `docx_embed.py` 生成真 `<w:tbl>`、`<w:tblHeader/>`、`<w:cantSplit/>`、跨平台 1×1 左色边卡片、`10pt` 无 `<w:sz-cs>` 样式、自动刷新页码的 `word/settings.xml`（`<w:updateFields w:val="true"/>` + `w:dirty="true"`），严格遵守 ECMA-376 元素顺序（`<w:sectPr>` 位于 `<w:body>` 最末、`[Content_Types].xml` 中 `<Default>` 严格早于 `<Override>`、`<w:tblBorders>` 早于 `<w:tblLayout>`、页脚 `<w:pBdr>` 早于 `<w:jc>`、`wp:docPr/@id` 与 `pic:cNvPr/@id` 全局唯一）；
   - SVG 图表由 Chrome 2× Retina（`664×2400`，超长自动重试 `4800`，单图 `45s` 超时）渲染并经 `PIL` 自动裁切（20px 对称白边、A4 上限 `6.10in × 8.20in`）嵌入，写入前经 `ET.fromstring` 校验并通过 `os.replace` 原子落盘；所有临时目录仅建于系统临时目录（`tempfile.mkdtemp`）并在 `finally` 中彻底清理。

---

## 6. 标准发刊闭环与强制门禁

任何报告更新必须完整走完以下闭环方可视为完成：
1. 更新 `data_snapshot.json`（同步维护跨项目 SSOT 裁决键 `tier_code` 与 `new_buy_allowed`，保证现货涨跌幅、`rmb_channels` 省钱差额与 `cross_ratios` 算术自洽；若命中主报告 5 大触发条件，方全量读取并同步更新主报告、`master_snapshot.json` 与 `MASTER_BASELINE`）；
2. 撰写/修订目标 Markdown（无人值守定时任务一律用 `write_file` 全量写盘，同日同班次修订加 `_r2` 后缀防覆写），并将【新增 / 更新 / 修正 / 删除】与红队消歧同步记入 `daily/CHANGELOG.md`（最新置顶）与 `daily/AUDIT_LOG.md`，同步在 `daily/SCORECARD.md` 公开回验到期预判并追加新追踪项（零内部工程/RSI 词汇、历史记录零篡改）；
3. **编译前秒检（`--precheck --strict` · 先拦截再编译）**：运行 `python3 <REPO_ROOT>/gold/lint_readability.py --precheck --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md`（同步更新主报告时一并传入主报告路径），跳过尚未生成的 Gate 6，毫秒级拦截组件错键、图 2 左标签超宽、68 个禁词、感叹号、外置日历/记分卡异常与快照冲突，**0 错 0 警后再进入编译**；
4. 运行预授权绝对路径编译脚本生成 PDF、原生 OOXML DOCX 与手机端响应式单文件 HTML（最新日报自动原子写入 `daily/latest_gold.html`），并用 `read_file` 抽检生成 PDF 关键页确认零文字碰撞、零断尾白页：
   - 日报：`python3 <REPO_ROOT>/gold/build_daily.py <REPO_ROOT>/gold/daily/<本刊文件名>.md`
   - 主报告（仅满足 5 大触发条件时）：`python3 <REPO_ROOT>/gold/build_report.py`
5. **强制运行 7 道门禁全量严格模式**（退出码必须为 `0`，**0 errors、0 warnings**）：
   - 仅发日报：`python3 <REPO_ROOT>/gold/lint_readability.py --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md`
   - 同步更新主报告时：`python3 <REPO_ROOT>/gold/lint_readability.py --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md <REPO_ROOT>/gold/黄金跨世纪周期与2026-2030终审研究报告.md`
6. **独立 RSI 自我复盘与递归优化闭环（一体化班次于 Step 5 联合执行）**：
   - 在每日 `07:30` / `18:00` 一体化班次中，黄金 Step 3 全绿后先交棒 Step 4 全球权益串行出刊，再由 **Step 5 的 1 路统一只读 `research` 盲审子代理**联合复盘黄金与三地权益（单跑黄金轨时单独启动 1 路盲审），按 6 维定量量表（数据零幻觉 / 上期预判回验 / 白话可读性 / 视觉排版 / 检索效率 / 工具稳健性，每维 1–5 分、满分 30）严苛自审本刊；
   - **Tier A 必做**：追加结构化记录至 `daily/rsi_metrics.json`，提炼 1–3 条高杠杆规则滚动精炼写入 `daily/RSI_PLAYBOOK.md`（严格保持 ≤180 行，合并旧项防膨胀；每满 10 刊自动执行一次 Meta-RSI 趋势总复盘）；
   - **Tier B 慎做 / Tier C 仅提案**：如有确凿确定性小 Bug 且改后能通过 `--check` + 重编 + `--strict` + 视觉复核，最多安全落地 1 处补丁（失败立即回滚）；宪法级策略与配置变更一律记入 `RSI_PLAYBOOK.md` 提案区；最后补跑一次 `lint_readability.py --strict` 确保 RSI 账本与手册全绿，并在快报末尾汇报本轮 RSI 得分与优化动作。
7. **双轨门禁全绿后单次发布网站（Web Publish）**：在一体化班次中待 Step 3 黄金、Step 4 权益与 Step 5 统一 RSI 复检全部绿灯后（单跑黄金轨则在本轨全绿后），**仅运行一次** `python3 <REPO_ROOT>/scripts/publish_site.py`（自动编译静态站 `_site`、通过 `lint_site.py --strict`、提交推送至 GitHub Pages 并滚动更新 Release PDF/DOCX 附件；本地预演可附加 `--dry-run`）。
