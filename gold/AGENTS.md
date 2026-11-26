# 黄金深度研报项目规则（global-investment-research/gold）

本目录是面向「懂一点基础财经、比普通人多一点市场认知的理性投资者」的「每日黄金深度研报（07:30 早报 & 18:00 晚报 / 周末专项版）」与「跨世纪周期全景主报告（1971–2030）」生产与出版工作区，隶属于仓库顶层统一编排宪章 `../AGENTS.md`（07:30 / 18:00 一体化单会话流水线的 Step 3）。以下规则为黄金子轨的永久约束；完整 JSON Schema、7 道门禁词表、OOXML 引擎架构与调研提示词请按需加载工作区 Skill **`gold-research-publishing`**（[`../.agents/skills/gold-research-publishing/SKILL.md`](../.agents/skills/gold-research-publishing/SKILL.md)）。

---

## 1. 核心工作区资产地图与跨项目单一权威源（SSOT）

- **双快照防撕裂数据源与跨项目 SSOT 宣言**：
  - **跨项目单一权威源（SSOT）**：在每日 **`07:30` / `18:00` CST** 一体化单会话流水线中，黄金深度研报在 **Step 3** 率先落盘、编译并严检通过，拥有 `data_snapshot.json`（涵盖国际现货金、COMEX 期金、SHFE 沪金、SGE 现货、COMEX 期铜、`DFII10` 实际利率、布油官结、CFETS 中间价、买金四步红绿灯 `tier_code` 与新买开关 `new_buy_allowed` 等核心裁决字段）的**唯一写入权**；紧随其后的全球股研模块（`../equity/`）在 **Step 4** 对刚刷新的本快照执行**零延迟只读校验**（详见仓库根规则 `../AGENTS.md`），严禁逆向修改黄金快照，亦严禁输出与黄金红绿灯指令冲突的买金建议；
  - **日报唯一实时数据源**：`data_snapshot.json`（涵盖 `edition_id`、`as_of_short`/`as_of_bjt`、L0/L1/L2 警报、四步红绿灯 `tier1_gates[4]`（固定 `id`：`real_yield`/`rate_spread`/`vix`/`ny_close`）、`tier_code`/`new_buy_allowed`、全球金银铜/沪金/上金所实盘、美债/汇率（含 `usd_cny_1630`/`cfets_fixing_date`）/估值锚、油气/风险资产/金矿/信用、VIX 十日日线表 `vix_10d_session_closes` 与核验台账 `vix_daily_row_checks`、第四关日期锚 `spot_gold_ny_close_date`/`tier1_gate4_*`、国内黄金 ETF 标准无日期键 **`etf_cn`**、面向读者的结构化缺口数组 **`data_caveats`**（`category` 枚举：`provisional_close`/`delayed_official`/`single_source`/`source_conflict`/`holiday_thin`/`publication_exception`）、四大央行与 12 大行样本数/中位 `bank_2027_*_sample_count`、`rmb_channels`、`cross_ratios`、`monthly_candles`、`mechanical_calendar`、`institutional_targets`、`trust_assets`）；
  - **四关复算与抗阻塞日历契约**：新刊的四关均由快照精确输入值通过 `edition_validation.py` 复算：班次截点宽限 **6 小时**；节日待披露复查间隔 **4 小时**；半日市（黑五 `11/27`、平安夜 `12/24`）支持 `provisional_close`；`no_row_confirmed` 支持 Cboe 官方公告或官方 CSV 自证（`next_published_date > day`）；普通交易日 `provisional_close` 须在 **3 个自然日**内以官方 CSV 终值核销；`market_calendar.json` 覆盖已延展至 **`2027-06-30`**（含耶稣受难日、清明、劳动节、阵亡将士纪念日、六月节补休等），有效覆盖硬底线 **30 天**（`<60 天` 输出提示）、核证有效期 **90 天**。现货指数发布窗口独立于美股与 COMEX 期金，休市或未核得有效盘口时用最近官收，`vix_live` 与 `vix_live_as_of` 同时留空。字段、临界值与三账本标记见 [DAILY_FORMAT_SPEC.md](daily/DAILY_FORMAT_SPEC.md) 与[黄金快照契约](../.agents/skills/gold-research-publishing/references/directives-and-snapshot-schema.md)。
  - **主报告独立锁定数据源**：`master_snapshot.json`（与 `data_snapshot.json` 对称，补齐 `edition_id`、`new_buy_allowed`、`cfets_fixing_date` 及 `tier1_gates[].id`；由主报告顶部 `<!-- MASTER_BASELINE {"as_of_short": "...", "snapshot": "master_snapshot.json"} -->` 原子锁定，`build_report.py` 与 `lint_readability.py` 强制校验一致，彻底根除跨日更新日报导致主报告 `--strict` 死锁或图表/正文撕裂）；
  - **外置跨市场休市与时令日历**：`market_calendar.json`（覆盖至 `2027-06-30` 的美/中/港/欧/英/日/印休市、半日市、独立 Cboe 现货 VIX 例外、四大央行议息、BCOM/GSCI 调仓及北美冬/夏令时切换规则，取代硬编码节假日）。
- **全景主报告（21–24 页 · 7 图顺排 `图 1`–`图 7`）**：`黄金跨世纪周期与2026-2030终审研究报告.{md,pdf,docx}`。
- **每日双刊、手机端快阅、公开记分卡、双账本与 RSI 资产**：
  - `daily/YYYY-MM-DD_{0730_早报|1800_晚报}_黄金深度研报.{md,pdf,docx}`：自 `2026-11-26_1800` 起全面启用**精炼收敛主刊**（目标 **5–6 页**，重大议息/危机日可扩至 **7–8 页** · 3 张 640px 矢量图，取代旧版 10–13 页冗长复读；同日同班次修订加 `_r2` 防覆写；历史早期归档兼容保留）；
  - `daily/latest_gold.html`（最新日报响应式单文件手机端 HTML，含吸顶导航、4–6 KPI 自适应、`.sn-grid` 自动单栏、640px 图表横滑与护眼深色模式）；
  - `daily/SCORECARD.md`（面向读者零内部工程词的公开可证伪预测记分卡，历史零篡改）；
  - `daily/DAILY_FORMAT_SPEC.md`、`daily/CHANGELOG.md`、`daily/AUDIT_LOG.md`（`AUDIT_LOG.md` 与 `CHANGELOG.md` 支持按月归档至 `daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md`，归档与活跃账本合并保留全部历史非空行原序）；
  - `daily/RSI_PLAYBOOK.md`（动态经验库，软限 **≤180 行** / 硬上限 **200 行**）与 `daily/rsi_metrics.json`（每刊 6 维自审与预判验真账本；旧版历史归档于 `daily/archive_v6/`）。
- **六大出版与质检核心模块**：
  - `build_daily.py`（日报 MD → PDF + 原生 OOXML DOCX + 原子输出 `daily/latest_gold.html`；共享 `parse_markdown_to_html`、4–6 卡 `.kpi-strip.cols-4`、`.sn-grid` 非拆行双栏卡片、图 1 胶囊标签 2D 防撞 `vb_h=284`、图 2 back-to-front 动态刻度、`CHROME_BIN` 解析与 120s×2 次重试、`.artifacts.json` 凭据写入，支持 `--check`）
  - `build_report.py`（主报告 MD + `master_snapshot.json` → PDF + 原生 OOXML DOCX；强制校验 `MASTER_BASELINE` 锁，清除页眉/页脚内部版本号与“今早”字样，动态读取月线低点与日期，冻结历史教学案例图 3，支持 `CHROME_BIN` 120s×2 重试与 `--check`）
  - `docx_embed.py`（纯 Python 原生 ECMA-376 OOXML 生成器 + `word/settings.xml` 自动刷新页码 + Chrome 2× Retina & PIL 自动裁切图表光栅化引擎，支持 `CHROME_BIN` 与 60s×2 重试）
  - `lint_readability.py`（自动化 7 道门禁质检器，支持 `--precheck --strict` 编译前 Gate 0–5 秒检及交付前 `--strict` 全量 Gate 0–6；收敛版三档词表、全篇内部词/文件名拦截、加粗密度 ≤14%、裸数字反引号预警、金店休市/未开盘自动放行、Gate 6 `.artifacts.json` 凭据核验、RSI 180/200 行门槛，零错零警告）
  - `edition_validation.py`（新刊班次 6h 截点、Cboe 现货 VIX 独立日历/30 分钟盘中窗口/节日 4h pending/半日市 `provisional_close`/3 日核销/`no_row_confirmed` 自证、30 天/90 天日历覆盖与四关精确复算模块）
  - `chart_input.py`（`lint_readability.py` 与 `build_daily.py` 共享图表数值解析与区间校验模块）

---

## 2. 强制启动与上下文继承顺序（含惰性主报告加载）

每次续写、更新或修订研报前，必须按以下顺序继承既有基线：
1. 读取 `market_calendar.json`，依据系统当前本地时间（`+08:00`）查明当日休市叠加模式（A/B/C/GLOBAL）、半日市/重要议息窗口与北美冬/夏令时换算规则（严禁硬编码节假日）；
2. 读取 `daily/RSI_PLAYBOOK.md`（≤180 行）、`daily/rsi_metrics.json` 最近 5 条记录与 `daily/SCORECARD.md`，继承历史高杠杆避坑经验与待回验公开预判；
3. 读取 `daily/CHANGELOG.md`（若超过 150 行，**仅读前 150 行**以防上下文膨胀；跨月时历史条目可按月归档至 `daily/archive/CHANGELOG_YYYY_MM.md`），确认最新一期相对路径与历史纠错；
4. 读取 `data_snapshot.json` 与轻量级 `master_snapshot.json`（**惰性主报告加载**：常规班次仅凭 `master_snapshot.json` 核验主报告 5 大实质更新触发条件，**仅当命中阈值需同步修订主报告时，才全量读取 78KB 主报告 Markdown**，大幅节省上下文防止模型注意退化）；
5. 读取 `CHANGELOG.md` 顶部记录的最新一期日报；涉及排版或结构变更时，核对 `daily/DAILY_FORMAT_SPEC.md`。

---

## 3. 零幻觉、跨时区真实性与防越权调研铁律

1. **反幻觉铁律**：每一条新增报价、政策、研报或传闻必须标明**信源 + 精确时点**。某市场休市或搜不到当日新报价时，必须如实写「休市 / 沿用上一终盘（标注时点）」并将重要暂定或延迟披露项写入 `data_snapshot.json` 的 **`data_caveats`**（纯读者中文、零内部文件名），严禁猜测、外推或编造任何数字。
2. **跨时区因果红线**：
   - 严禁把国内 02:30 夜盘收盘价与纽约 06:00 现货终盘价之间的 3.5 小时时差混充为「国内供需溢价」（比较溢价必须使用同一时点折算）；
   - 严禁把 05:00 等盘后官员讲话或突发新闻因果倒置地归因到 02:30 已经收盘的国内夜盘价格。
3. **一体化 6+1（日常主力）与独立 5+1（单跑回退）两阶段调研机制、官收信源白/黑名单与防卡壳/防篡改红线**：
   - 所有外部联网实盘与资讯调研必须通过两阶段 `research` 子代理使用中英双语 `search_web` 覆盖七大信源完成：在每日 `07:30` / `18:00` 一体化班次中执行仓库级 **阶段 2A 共享 6 路并行调研 + 阶段 2B 1 路统一红队（一体化 6+1）**（详见 `../AGENTS.md`；仅独立单跑黄金轨时回退至 5 路并行 + 第 6 路红队），严格遵守美股 `GLD`/`GDX` 官收白名单 `StockAnalysis`/`Investing`/`VanEck NAV`、**禁用 `Barchart` 远月滞后合约快照**、`site:shfe.com.cn`/`site:lbma.org.uk` 定向补录与 `market_calendar.json` 北美冬/夏令时硬校验，**必须等全部调研子代理返回后**再启动红队复核审计，输出【新增 / 更新 / 修正 / 删除】四张清单；
   - **无人值守防卡壳铁律**：在定时自动化任务中，主代理严禁调用 `date`、`ls`、`curl` 等未授权外部抓取或探测 shell 命令，**亦严禁调用 `edit_file`**（所有 Markdown/JSON 更新一律使用 `write_file` 全量写盘，彻底杜绝交互权限拦截或上下文漂移），**仅运行预授权的绝对路径裸命令**（不加 `cd &&` 前缀）执行 Python 编译与质检脚本，直接依据系统本地时间（`+08:00`）+ `market_calendar.json` 判定刊期与休市叠加；同日同班次若需二次重发/勘误，新档加 `_r2` 后缀严禁覆盖原归档；
   - **定时任务三层 RSI 防篡改与防退化铁律**：在正常发刊编译阶段（Step 1–4）严禁修改任何 `.py` 脚本与规则文件；仅在每刊 7 道门禁全绿交付验收通过后的 **Step 5 RSI 闭环阶段** 按三层分级执行自进化——**Tier A**（`daily/RSI_PLAYBOOK.md` 软限 ≤180 行 / 硬上限 200 行 + `daily/rsi_metrics.json`）全自动迭代；**Tier B**（工作区 `.py` 含 `build_daily.py`/`build_report.py`/`docx_embed.py`/`lint_readability.py`/`edition_validation.py`/`chart_input.py` 或 `DAILY_FORMAT_SPEC.md` 确凿小 Bug）仅允许单次 ≤1 处最小补丁（≤40 行，**只允许加固门禁或修 Bug，严禁删禁词/放宽误差**）且必须通过 `--check` + 重编 + `--strict` + PDF 视觉复核，**任一步失败立即回滚并转提案**；**Tier C**（核心风控策略红线、`AGENTS.md`、`../.agents/skills/`、`../automations/sidecars/`、`../scripts/install_sidecars.py` 与本地 `sidecar.json`）永不静默修改，仅写入提案区待用户审批。

---

## 4. 收敛版（`>= 2026-11-26_1800`）面向理性投资者的五大编辑与金融红线

1. **平等克制的专业理财经纪语调（去居高临下、去黑话堆砌）**：
   - 面向**懂一点基础财经、比普通人多一点市场认知的理性投资者**：既绝不居高临下说教（禁 `小白词典`/`直接抄`/`蠢事`/`1 分钟定心丸`/`保命铁律`），也不堆砌生僻卖方量化词或内部工程词；
   - 严格区分 **【客观事实】/【逻辑推论】/【概率与失效边界】**；关键指标配齐 **【当前读数 + 历史水位 + 决策含义】**；
   - **感叹号红线**：Layer 0–1 严禁出现任何感叹号（`!` / `！`，规定为 **0**），收敛新刊全篇 **≤5** 个（历史旧刊 ≤2）；
   - **版面干净度红线（收敛新刊 Gate 4）**：Layer 0–1 自然段 ≤240 字；全篇**加粗文字密度 ≤14%**；**裸数字、金额、百分比严禁套反引号**（仅基金/期货/股票代码如 `` `518660` ``、`` `008142` ``、`` `GCZ26` ``、`` `au2702` `` 及代码块可用反引号）；
   - 全文（含组件 JSON 字符串）禁用 **13 个夸张/煽动词**：`神准`、`分毫不差`、`100%胜率`、`100% 胜率`、`无情推翻`、`核雷`、`拉爆`、`血洗`、`焊死`、`史诗级`、`史诗轧空`、`彻底打脸`、`惊天验证`。
2. **三档知情散户词汇标准（`CONVERGED_CUTOVER = 2026-11-26_1800`）与全篇零内部泄露**：
   - **第一档 · 自由使用（主流投资者通用词）**：`VIX`、`DXY`、`GLD`、`GDX`、`ETF`、`CFTC`、`COT`、`CDS`、`鹰派`、`鸽派`、`提保`、`轧空`、`逼空`、`上影线`；
   - **第二档 · 首次出现用 6–12 字中文括号轻注**：`DFII10`（10 年美债实际利率）、`2Y−FF`（2 年美债减政策利率利差）、`ON RRP`（联储隔夜逆回购余额）、`HY/CCC OAS`（高收益信用利差）、`IOPV`（盘中参考净值）、`bp`（基点）；
   - **第三档 · 硬门禁拦截（违者 FAIL）**：
     - **全篇（含 Layer 2/3 与全部组件，含 `DAILY_GLOSSARY`）严禁**：① 自 `2026-11-26_0730` 起拦截内部工程词、版本号与文件名（`V2.x/V6.x/V7.x`、`Subagent`、`红队`、`法证`、`master_snapshot.json`、`data_snapshot.json`、`market_state.json`、`audit_ledger.md`、`RSI_PLAYBOOK(.md)`、`rsi_metrics.json`、`sidecar.json`、`permissions.json`、`DAILY_FORMAT_SPEC.md`、`AGENTS.md`、`SKILL.md` 及任意 `*.py` 脚本名）；② 自 `2026-11-26_1800` 起全篇与全部组件（含 `DAILY_GLOSSARY`）统一拦截 6 个居高临下口号（`小白词典`、`直接抄`、`蠢事`、`1分钟定心丸`、`1 分钟定心丸`、`保命铁律`）；
     - **Layer 0–1 严禁**：生僻卖方量化词（`stop-through`、`IFRS 9`、`HQLA`、`FVOCI`、`ROTCE`、`Call Wall`/`Put Wall`、`负 Gamma`、`R²=`）、未消歧分析师人名（`Daniel Ghali`/`Michael Hsueh`）、工程路数（`子代理`/`63 路`）、赌徒口语（`梭哈`、`做T`、`短线波段`、`高弹性`）、跨市涨跌色混用（`收红`/`收绿`/`翻红`/`翻绿`）及平行打分（`六灯`、`X/6`）。
3. **四层洋葱精炼收敛结构（日报 5–6 页 · 重大日 7–8 页）**：
   - **Layer 0（首屏决策区）**：封面支持 **4 张高密度核心 KPI 卡**（`.kpi-strip.cols-4`，兼容 4–6 张，每条 `sub` ≤17 汉字当量）+ 三色静默紧迫度牌（`L0` 沉稳灰蓝 / `L1` 暖琥珀菱形 / `L2` 深红警示，**禁用绿色**）+ 唯一买金红绿灯 + ≤80 字核心结论与底线风险；
   - **Layer 1（核心行动区）**：`.sn-grid` 信号（0–2 件）vs 噪音（3–5 件）防跨页双栏网格 + 买金四步红绿灯（满足 X/4 项）+ 10 万元人民币钱包账（6 周内锚定现行汇率，跨年显式标注汇率联动区间 `6.20–6.45`）+ **A（空仓）/ B（B1 轻仓套牢 · B2 重仓焦虑 · B3 早年浮盈）/ D（宏观原理）与 C（婚庆/实体省钱实算）紧凑行动卡**；
   - **Layer 2（精炼深度专题）**：以 `# 第二部分` / `## 专题一` / `## 周末专题` 或 `DAILY_LAYER_BADGE`（`tone: "deep"`）起头以触发门禁分层与自动分页；早/晚报收敛至 **5–6 页**（重大议息/危机日可扩至 **7–8 页**），保留 3 张 640px 矢量图，聚焦核心驱动与可证伪观察点，杜绝冗长复读与机械抄主报告；`DAILY_GLOSSARY` 改为可选（0–1 次）；
   - **Layer 3（可选进阶复核区）**：顶部挂 `DAILY_LAYER_BADGE`（`tone: "pro"`），精炼呈现关键指标明细、Tier 0–3 阈值、高门槛工具（明标 50 万元门槛）与免费官方自查路径；`DAILY_TRUST_BAR` 改为可选（0–1 次，且全篇零内部文件名/工程词）；版本演进 Diff、子代理核验与人名消歧**物理分离**至 `daily/CHANGELOG.md` 与 `daily/AUDIT_LOG.md`。
4. **单一真相刻度与核心策略口径**：
   - Layer 0–1 彻底废除 `六灯 X.X/6` 平行分制（由正则强制拦截），且全篇严禁出现「通过 0–3 关即可转黄/开新仓」等部分过关误导话术（由 Gate 5 强制拦截），统一仅用 **【历史水位尺】+【买金四步红绿灯（满足 X/4 项，须四关全过方亮黄灯）】**；
   - 四档右侧建仓与 A 类分批比例全系统唯一统一为 **`30% + 45% + 25%`**（`Tier 0` 红灯 0% / `Tier 1` 黄灯 30% / `Tier 2` 绿灯 +45%→75% / `Tier 3` 满格 +25%→100%）；
   - 硬止损红线：`DFII10` 创 60 个交易日收盘新高时机械砍半右侧新仓；
   - 尾部深熊升级红线：布伦特原油跌破 80 美元且 `DFII10` 突破 2.95% 并连续站稳 5 个交易日时，将深熊概率由 18% 上调至 25%–30%；四象限情景概率之和必须恒等于 100%。
5. **中国买金、税制与回购事实红线**：
   - 财政部/税务总局 2025 年第 11 号公告（2025-10-29）：区分投资与非投资增值税路径，并计入 **5% 金银首饰零售消费税**；非会员零售水贝投资金条存在约 13% 增值税转嫁坑；
   - 场外黄金 ETF 联接基金透明费率铁律：**A 类（`008142`）** 仅收 `0.20%/年` 运营费 + 支付宝/天天 1 折申购 `0.06%` + 持有满 1 年免赎回（7天–1年 `0.10%`），拿超 **167 天（约 5.5 个月）** 即比 C 类省钱；**C 类（`008143`/`000217`/`002611`）** 0 申购费但另收 **`0.35%/年` 销售服务费（合计 `0.55%/年`）**，且持有 `<7 天` 1.50%、`7–29 天` 0.10%、**满 30 天方免赎回费**（严禁误写为「7 天后免赎回费」或把 A/C 笼统合写为 `0.20%`）；支付宝应走「理财 → 基金」，勿走首页「黄金」频道（主推 ~0.95%/年高费场外 C 类；国有行「积存金」赎回常扣 0.50% 或点差，不宜短线进出）；
   - 场内低费率 ETF（如 `518660` 合计 0.20%）须提示核查券商「免五」与 IOPV（盘中参考净值）溢价（<0.3%）；
   - 国有四大行投资金条回购铁律：**绝不拆原厂塑封、保留发票与证书、回原行指定网点**（本行金条回购扣 2–4 元/克）；水贝加工按工艺分档报价（素圈 10–20 元/克、古法 30–50 元/克、3D 硬金一般不熔料），支持「料换料零损耗」。

---

## 5. 单源数据与出版级编译工程铁律

1. **双快照原子算术一致性与透明缺口**：日报每次先更新 `data_snapshot.json`（跨资产比值统一使用无日期键 `cross_ratios`，国内 ETF 使用无日期键 `etf_cn`，重要暂定/未披露数据写入纯读者中文的 `data_caveats`）；国内节假日（B 类）或 `data_caveats` 明示金店未开盘时 Gate 5 自动放行金店价对齐预警；仅当满足主报告 **5 大实质更新触发条件**（① 买金四步红绿灯切换档位；② 国际现货金较主报告基线变动 `≥3%` 或国内料价变动 `≥25 元/克`；③ 12 大行 2027 中位目标或四大央行利率路径实质改变；④ 尾部深熊红线或 60 日新高硬止损触发；⑤ 重大税制/渠道/结构性研究升级）时，方同步修订主报告 MD、`MASTER_BASELINE` 与 `master_snapshot.json` 并运行 `build_report.py`。
2. **指令、表格与防跨页组件规范**：10 个 `DAILY_*` 组件必须为独立 HTML 注释中的合法 JSON（缺必填键、拼写错或坏 JSON 均会被拦截；收敛新刊中 `DAILY_TRUST_BAR` 与 `DAILY_GLOSSARY` 为可选 0–1 次）；`DAILY_SIGNAL_NOISE` 采用 `.sn-grid` 双栏网格防跨页断句；Markdown 表格共享 `render_md_table`（自动对齐、防折行 `col-nowrap` 总宽 ≤25.0、等宽数字 `tabular-nums`、原子单位保护、转义 `\|` 支持、紧凑表 `table-keep` 防孤行、矢量状态胶囊），正文及组件 JSON 禁止残留裸 HTML 布局标签。
3. **矢量图表规范**：所有 SVG 采用 `viewBox="0 0 640 ..."`、主标签字号 `≥10.2px`（辅助刻度/徽章 `9.8–10.0px`）、全部文本经 `svg_esc()` 剔除位图 Emoji 与控制字符（保留矢量 `✓`/`✕`）；**图 1（`DAILY_CHART_TIMELINE`）** 采用 `vb_h=284` + 半透明白底胶囊标签 `_svg_label_pill()` 与 2D 碰撞面积最小化避让算法；**图 2（`DAILY_CHART_CROSS`）** 采用 1:1 诚实线性比例 + 防越界动态 `x_zero` + back-to-front 动态网格刻度（底纹 → 刻度 → 条形/文字 → 零轴）+ 中文惯例「红涨 / 绿跌」+ 仅标现货/期货主角黄金（显式 `highlight` 键）+ 独立反向指标栏；`L1` 暖琥珀警报牌采用菱形标记 `.dot-diamond` 与买金红绿灯圆点物理区分。
4. **原生 ECMA-376 OOXML Word 与弹性编译红线（严禁 `textutil`）**：
   - **严禁调用 macOS `textutil` 转换 `.docx`**（会静默摧毁全部表格与卡片边框）；
   - 必须通过 `docx_embed.py` 生成真 `<w:tbl>`、`<w:tblHeader/>`、`<w:cantSplit/>`、跨平台 1×1 左色边卡片、`10pt` 无 `<w:sz-cs>` 样式、自动刷新页码的 `word/settings.xml`（`<w:updateFields w:val="true"/>` + `w:dirty="true"`），严格遵守 ECMA-376 元素顺序；
   - 全套 Chrome 编译（`build_daily.py`/`build_report.py`/`docx_embed.py`）支持 **`CHROME_BIN` 环境变量**与 **1 次自动重试**（PDF `120s`×2 尝试、2× Retina 图表 PNG `60s`×2 尝试，自动 `2400→4800` 扩高并经 `PIL` 裁切），编译后写入 `.artifacts.json` SHA-256 凭据供 Gate 6 免误报校验；所有临时目录仅建于系统临时目录（`tempfile.mkdtemp`）并在 `finally` 中彻底清理。

---

## 6. 标准发刊闭环与强制门禁（纯网页版）

任何报告更新必须完整走完以下闭环方可视为完成（本项目采用纯网页静态门户交付，**不生成 PDF、Word 或 Release 附件**）：
1. 更新 `data_snapshot.json`（同步维护跨项目 SSOT 裁决键 `tier_code`、`new_buy_allowed`、四关精确输入、`vix_10d_session_closes`、`vix_daily_row_checks`、`etf_cn`、`data_caveats`、`rmb_channels` 与 `cross_ratios` 算术自洽；若命中主报告 5 大触发条件，方全量读取并同步更新主报告、`master_snapshot.json` 与 `MASTER_BASELINE`）；
2. 撰写/修订目标 Markdown（无人值守定时任务一律用 `write_file` 全量写盘，同日同班次修订加 `_r2` 后缀防覆写），并将【新增 / 更新 / 修正 / 删除】、红队消歧与 `GOLD_EDITION_REVIEW`/`GOLD_EDITION_CHANGELOG`/`GOLD_EDITION_SCORECARD` 同步记入 `daily/CHANGELOG.md`（最新置顶）、`daily/AUDIT_LOG.md` 与公开记分卡 `daily/SCORECARD.md`（零内部工程/RSI 词汇、历史记录零篡改；跨月时历史账本可按月归档至 `daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md`）；
3. **强制运行源稿严格门禁**（退出码必须为 `0`，**0 errors、0 warnings**）：
   - 仅发日报：`python3 <REPO_ROOT>/gold/lint_readability.py --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md`
   - 同步更新主报告时：`python3 <REPO_ROOT>/gold/lint_readability.py --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md <REPO_ROOT>/gold/黄金跨世纪周期与2026-2030终审研究报告.md`
4. **独立 RSI 自我复盘与递归优化闭环（一体化班次于 Step 5 联合执行）**：
   - 在每日 `07:30` / `18:00` 一体化班次中，黄金 Step 3 全绿后先交棒 Step 4 全球权益出刊，再由 **Step 5 的 1 路统一只读 `research` 盲审子代理**联合复盘黄金与三地权益，按 6 维定量量表（满分 30）严苛自审本刊；
   - **Tier A 必做**：追加结构化记录至 `daily/rsi_metrics.json`，提炼 1–3 条高杠杆规则滚动精炼写入 `daily/RSI_PLAYBOOK.md`（软限 ≤180 行 / 硬上限 200 行）；
   - **Tier B 慎做 / Tier C 仅提案**：如有确凿确定性小 Bug，最多安全落地 1 处 ≤40 行补丁并重跑 `--strict` 与静态站构建严检（失败立即回滚）；宪法级策略与配置变更一律记入 `RSI_PLAYBOOK.md` 提案区；最后补跑 `lint_readability.py --strict` 确保全绿。
5. **双轨门禁全绿后单次纯网页发布**：一体化班次待两轨和统一 RSI 复检全绿后，登记进入 `publish`，运行 `python3 <REPO_ROOT>/scripts/publish_site.py --edition-token <token>` 构建、严检并推送静态网页，再用同一 token 运行 `edition_run.py complete <token>` 验证 GitHub Pages 实际部署成功即闭环。仅本地预演时用 `publish_site.py --dry-run`，不传班次 token。
