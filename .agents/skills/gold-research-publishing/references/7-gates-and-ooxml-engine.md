# 7 道门禁质检规则与原生 PDF / OOXML 出版引擎架构（V2.2 / V7.2）

本文档记录 `lint_readability.py`（V2.2）、`build_daily.py`（V2.2）、`build_report.py`（V7.2）与 `docx_embed.py`（V2.2）的全部硬性工程合约、精确禁用词表与跨日维护排雷点。

---

## 1. 自动化 7 道门禁（`lint_readability.py`）完整规范

- **编译前秒检命令**：`python3 <REPO_ROOT>/gold/lint_readability.py --precheck --strict <file1.md> [file2.md ...]`（仅运行双快照、RSI 与 Gate 0–5，跳过尚未生成的 Gate 6 PDF/DOCX 文件检查，毫秒级拦停组件错键、图 2 左标签超宽、禁词与感叹号，0 错 0 警后再调用 `build_daily.py`）；
- **交付前全量严格命令**：`python3 <REPO_ROOT>/gold/lint_readability.py --strict <file1.md> [file2.md ...]`（覆盖全部 Gate 0–6；任何 `FAIL` 或 `WARN` 都会导致退出码 `1`，必须 `0 errors, 0 warnings` 方可交付；未知选项自动以退出码 `2` 报错）。

### Layer 0–1 自动边界切分规则
脚本取以下 4 个正则在全文中最早出现的位置作为 Layer 0–1 终点（若全文超 3,000 字且均未匹配，Gate 0 直接报错阻断）：
1. `^#\s*第二部分`
2. `^##\s*专题一`
3. `^##\s*周末专题`
4. `<!--\s*DAILY_LAYER_BADGE\s*\{[^}]*"tone"\s*:\s*"deep"`

### Gate 0：全量指令语法、拼写与嵌套 Schema 校验（FAIL / WARN）
- 捕获**一切** `<!-- DAILY_* ... -->` 注释，拦截拼写错误（如 `DAILY_CHART_TIEMLINE`）与非 JSON 载荷；
- 校验 `json.loads()` 成功、顶层 `REQUIRED_KEYS` 齐全，并深入校验全部嵌套合约：`DAILY_META.kpis` 长度 6、每项含 `label/val/sub` 且 `sub` 视觉宽 `≤17.5`；`DAILY_VERDICT` 限 `L0/L1/L2`、`badge` 禁用 `🟢` 且含 `traffic_light/risk_line/数组 bullets`；`DAILY_SIGNAL_NOISE.signals/noises` 每项须为含 `head/body` 的对象且 `signals ≤2`；`DAILY_PERSONA.cards` 每项须含 `group/heading/数组 actions`；`DAILY_GLOSSARY.terms` 每项须含 `term/plain`；`DAILY_LAYER_BADGE.tone` 限 `deep`/`pro`；`DAILY_CHART_TIMELINE` 拦截误写 `zones`（须 `highlight_zones`）、`points[].val` 为数字且 `y_min < y_max`；`DAILY_CHART_SWITCH` `checks==4`（含 `name/passed/line1/line2`）且 `gauges` 含 `label/value_text/pct ∈ [0,100]`（拦截误写 `safe_pct`）；`DAILY_CHART_CROSS` `items` 含 `label/pct`、`reverse_items` 含 `label/detail`，且 **`items[].label` 视觉宽 `>9.5` 报 FAIL / `>9.0` 报 WARN（强制防撞左高亮竖条，建议 `≤8.5`）**；
- 展平 JSON 字符串（自动跳过 `accent`/`color`/`fill`/`tone`/`group` 等样式键）纳入后续文本门禁。

### Gate 1：零裸金融代码、零内部元噪音、零原始 HTML 泄露（68 个禁词 · FAIL）
- **ASCII 词边界不区分大小写禁用词表 (`BANNED_LAYER01_ASCII`，47 个 ASCII/版本代码)**：
  `DFII10`, `2Y-FF`, `2Y−FF`, `T10YIE`, `EFFR`, `SOFR`, `IORB`, `HY OAS`, `CCC OAS`, `ON RRP`, `au2702`, `OGZ26`, `GCX26`, `GCZ26`, `GCG27`, `BCOM`, `GSCI`, `Subagent`, `Daniel Ghali`, `Michael Hsueh`, `Call Wall`, `Put Wall`, `stop-through`, `IFRS 9`, `HQLA`, `GDX/GLD`, `CDX IG`, `OAT`, `JGB`, `DXY`, `VIX`, `GLD`, `GDX`, `KRE`, `SRF`, `CDS`, `OIS`, `CFTC`, `COT`, `V2.0/2.1/2.2`, `V6.0/6.1`, `V7.0/7.1/7.2`
- **中文/混合禁用词表 (`BANNED_LAYER01_LITERAL`，21 个中文/混合黑话)**：
  `子代理`, `63 路`, `63路`, `负 Gamma`, `负Gamma`, `R²=`, `R² =`, `梭哈`, `短线波段`, `放鹰`, `鹰派`, `鸽派`, `提保`, `上影线`, `即征即退`, `高弹性`, `六灯`, `逼空`, `轧空`, `做T`, `做 T`
- **裸 HTML 标签泄露检查（正文代码块外 + 所有组件 JSON 字符串内）**：禁止出现未转义的 `div`/`span`/`table`/`tr`/`td`/`th`/`svg`/`rect`/`path`/`p`/`ul`/`ol`/`li`/`script`/`style`/`iframe`/`img`/`h1–h6`/`font`/`center` 等标签（组件内仅允许 `<br/>`、`<strong>`、`<code>`）。

### Gate 2：家庭理财医生冷静语调与感叹号红线
- **13 个全文禁用夸张/煽动词 (`BANNED_HYPE_WORDS`，先剥离 `**`/`*` 后扫描，FAIL)**：
  `神准`, `分毫不差`, `100%胜率`, `100% 胜率`, `无情推翻`, `核雷`, `拉爆`, `血洗`, `焊死`, `史诗级`, `史诗轧空`, `彻底打脸`, `惊天验证`
- **感叹号红线（覆盖 Unicode `[!！‼⁉❗❕]`，剔除代码块与 `!=`）**：Layer 0–1 必须为 **0**（FAIL），全文合计超过 **2** 个报 WARN。

### Gate 3：彻底清除 Layer 0–1 平行打分（FAIL）
- 使用 Unicode 安全正则 `(?<![0-9.])[0-6](?:\.[05])?\s*[/／]\s*6(?![0-9])`，同步拦截小数 `X.5/6`、整数 `X/6` 及全角 `／6`。

### Gate 4：Layer 0–1 自然段简洁度（WARN）
- 保留原始行号（注释替换保留等量换行），通过正则跳过标题/表格/列表（`-`/`*`/`•`/`\d+\.`）/引用/分割线，按去除 Markdown 语法后的可见字符数校验 `≤ 240` 字。

### Gate 5：双快照算术自洽 + SSOT 开关 + 过时/冲突事实拦停 + 当期正文核对
- 含 `<!-- MASTER_BASELINE {...} -->` 的主报告自动校验 `master_snapshot.json` 且强制锁定 `as_of_short` 一致；日报自动校验 `data_snapshot.json`；
- 校验现货涨跌幅（`≤0.05`）、婚庆 1g/50g/百分比（`≤0.15`）、`tier1_gates` 长度 4 与求和、`daily_alert_level`、SSOT `new_buy_allowed` 布尔值与 `tier_code != "Tier 0"` 一致性、`a_class_tranche_split`、5 项跨资产比值（`gold_spx_ratio ≤0.015`、`gold_platinum_ratio ≤0.05`、其余 `≤0.15`），检出遗留 `cross_ratios_\d{4}` 报 WARN；
- 校验 5 条永久事实守卫 + 日期绑定守卫；当文件时间戳匹配快照时，核验正文含 `spot_gold_ny_close_rounded`、`brand_store_rmb`、`wedding_save_per_g_rmb`；
- 全局治理校验（`--precheck` 与全量均生效）：强制校验 `market_calendar.json` 存在、合法 JSON 且 `calendar_overrides` 非空；强制校验 `daily/SCORECARD.md` 存在且零内部工程/RSI 泄露词；强制校验 `daily/RSI_PLAYBOOK.md` ≤180 行上限与 `daily/rsi_metrics.json` 6 维评分自洽。

### Gate 6：PDF、手机端响应式 HTML 与原生 ECMA-376 OOXML DOCX 三产物法证校验
1. **PDF 检查**：文件存在、`>=10KB`、文件头为 `%PDF-`、且修改时间不早于 Markdown（防陈旧 PDF）；
2. **手机端 HTML 检查（针对日报，非 `--precheck` 模式）**：校验 `daily/latest_gold.html` 存在、体积 `>=5KB` 且包含 `<meta name="viewport"` 声明；
3. **DOCX 检查**：修改时间不早于 Markdown；具备 7 个核心部件（含 `styles.xml`、`settings.xml`、`footer1.xml`）；全部 XML 通过 `ET.fromstring`；`<w:tbl>` > 0；零 `<w:sz-cs>` 与 `___DOCX_CHART_`；`<w:sectPr>` 在 `<w:body>` 最末；`[Content_Types].xml` 所有 `<Default>` 早于 `<Override>` 且无悬空目标；严格验证 ECMA-376 顺序（`tblBorders` 早于 `tblLayout`、`tblGrid` 正整数且总和 `<=9638`、页脚 `pBdr` 早于 `jc`、无 `pageBreakBefore` 早于 `keepNext`）；`wp:docPr/@id` 与 `pic:cNvPr/@id` 全局唯一；所有超链接/页脚/图片 `rId` 有效且图片为合法 PNG（魔数 `\x89PNG\r\n\x1a\n` 且 `>=2KB`），图数 `>=` Markdown 图表总数。

---

## 2. 共享排版引擎、手机端 HTML 与 640px 矢量图 + 原生 OOXML 架构（V2.2）

- **共享 `parse_markdown_to_html()`（`build_daily.py`）**：主报告与日报共用一套解析器，支持 `<ul>`/`<ol>` 双嵌套子列表、`####`、空 `>` 行、`<ol start=N>`、清理普通 HTML 注释、拼写错误指令即时报错、统一 `DAILY_CHART_*` 与 `CHART_*` DOCX 光栅化；
- **手机端响应式单文件导出 `build_gold_mobile_html()`（`build_daily.py`）**：编译最新日报时通过 `.tmp` + `os.replace` 原子生成 `daily/latest_gold.html`，注入 `viewport-fit=cover`、吸顶快捷导航栏（首屏结论 / 10万钱包账 / 四类读者 / 深度专题与图表 / 进阶复核 / ↑ 顶部）、`@media screen and (max-width: 680px)` 下 KPI 卡片自适应与 640px SVG `.svg-scroll` 水平平滑滚动不缩字、表格横滑防挤扁以及 `@media (prefers-color-scheme: dark)` 护眼深色模式，且零影响 Chrome PDF 打印样式；
- **智能表格 `render_md_table()`**：先按 `<br/>` 拆行再测宽、支持转义 `\|`、2–10 字状态胶囊自动识别、防拆逗号数字与日期的 `_ATOMIC_NW_RE`、`col-nowrap` 含内边距上限 `<=25.0` + 首列保护 `.col-first-min`、6 行以内紧凑表自动挂 `.table-keep` 防孤行；
- **640px 矢量图 + `svg_esc()`**：`EMOJI_STRIP_RE` 剔除位图 Emoji/变体符/控制字符但保留矢量 `✓`/`✕`；`PDF_CSS` 新增 `.dot-diamond` 琥珀菱形与 Chrome `--print-to-pdf` `90s` 超时护栏；
- **原生 OOXML `docx_embed.py` V2.2**：新增 `word/settings.xml`（`<w:updateFields w:val="true"/>`）与页脚 `w:dirty="true"` 自动刷新总页数；封面 KPI 2×3 原生表直接保留彩色矢量圆点/菱形与动态色边；Chrome 单图 `45s` 超时 + 独立 profile + 触底自动 `2400→4800` 重试；全临时文件建于 `tempfile.mkdtemp()` 并在 `finally` 彻底清理。

---

## 3. 跨日、跨月与跨年运行保障

1. **双快照解耦与惰性加载**：日常只更新 `data_snapshot.json`（跨项目 SSOT 唯一写入权），常规班次仅惰性读取 `master_snapshot.json` 核验 5 大触发条件，命中时才全量读取并同步更新主报告正文与 `MASTER_BASELINE`，彻底杜绝次日 `--strict` 死锁；
2. **外置 60+ 天日历与冬/夏令时自动切换**：`market_calendar.json` 集中维护美/中/港/欧/英/日/印休市叠加（A/B/C/GLOBAL）、半日市、四大央行议息、BCOM/GSCI 调仓及 `2027-03-14` 北美切换夏令时时钟偏移，取代所有硬编码节假日；
3. **动态跨月/跨年渲染**：主报告图 2 优先读 `monthly_candles`（跨入 12 月与 2027 年零重叠），图 4 机械时钟读 `mechanical_calendar`，图 7 投行读 `institutional_targets`，图 3 历史复盘案例以常量永久冻结防篡改历史。
