# 7 道门禁质检规则与原生 PDF / OOXML 出版引擎架构

本文档记录 `lint_readability.py`、`edition_validation.py`、`chart_input.py`、`build_daily.py`、`build_report.py` 与 `docx_embed.py` 的全部硬性工程合约、收敛版三档词表、矢量图防碰撞算法与跨日/跨月运维保障。

---

## 1. 自动化 7 道门禁（`lint_readability.py`）完整规范

- **编译前秒检命令**：`python3 <REPO_ROOT>/gold/lint_readability.py --precheck --strict <file1.md> [file2.md ...]`（仅运行双快照、RSI、日历/记分卡与 Gate 0–5，跳过尚未生成的 Gate 6 PDF/DOCX/手机端 HTML 检查，0 错 0 警后再调用 `build_daily.py`）；
- **交付前全量严格命令**：`python3 <REPO_ROOT>/gold/lint_readability.py --strict <file1.md> [file2.md ...]`（覆盖全部 Gate 0–6；任何 `FAIL` 或 `WARN` 都会导致退出码 `1`，必须 `0 errors, 0 warnings` 方可交付；未知选项以退出码 `2` 报错）。

### Layer 0–1 自动边界切分规则
脚本取以下 4 个正则在全文中最早出现的位置作为 Layer 0–1 终点（若全文超 3,000 字且均未匹配，Gate 0 直接报错阻断）：
1. `^#\s*第二部分`
2. `^##\s*专题一`
3. `^##\s*周末专题`
4. `<!--\s*DAILY_LAYER_BADGE\s*\{[^}]*"tone"\s*:\s*"deep"`

### Gate 0：全量指令语法、拼写、结构与嵌套 Schema 校验（FAIL / WARN）
- 捕获**一切** `<!-- DAILY_* ... -->` 注释，拦截拼写错误与非 JSON 载荷；图表数值经共享模块 `chart_input.py` 统一校验；
- **收敛主刊结构规则（`CONVERGED_CUTOVER = 2026-11-26_1800`）**：
  - `DAILY_META.kpis` 合法数量为 **4–6 张卡**（旧刊建议 6 张），每项含 `label/val/sub` 且 `sub` 视觉宽 `≤17.5`；新刊必填 `edition_id`、`as_of_short` 且 `timestamp` 须展示一致北京时间，并通过 `edition_validation.check_edition_time()`（6 小时截点宽限）；
  - `DAILY_TRUST_BAR` 与 `DAILY_GLOSSARY` 在收敛新刊中改为**可选（`0` 或 `1` 次，`>1` 报 FAIL）**；旧刊仍要求 `DAILY_TRUST_BAR == 1` 且 `DAILY_GLOSSARY >= 1`；
  - `DAILY_VERDICT` 限 `L0/L1/L2`、`badge` 禁用 `🟢`、含 `traffic_light/risk_line/数组 bullets`；新刊同步校验 `tier_code`/`new_buy_allowed`/`tier1_passed`；
  - `DAILY_SIGNAL_NOISE.signals/noises` 每项含 `head/body` 且 `signals ≤2`；`DAILY_PERSONA.cards` 含 `group/heading/数组 actions`；`DAILY_LAYER_BADGE.tone` 限 `deep`/`pro`；
  - `DAILY_CHART_TIMELINE` 拦截误写 `zones`（须 `highlight_zones`）、`points[].val` 为数字且 `y_min < y_max`；`DAILY_CHART_SWITCH` `checks==4`（含 `passed/name/line1/line2`，新刊加固定 `id` 顺序）且 `gauges` 含 `label/value_text/pct ∈ [0,100]`（拦截 `safe_pct`）；`DAILY_CHART_CROSS` `items[].label` 视觉宽 **`>9.5` 报 FAIL / `>9.0` 报 WARN（建议 `≤8.5`）**；
- 新刊预检同步校验三账本同期标记（`GOLD_EDITION_CHANGELOG`、`GOLD_EDITION_SCORECARD`、`GOLD_EDITION_REVIEW` 四关 HTTPS 证据与 `forecast_review`）。

### Gate 1：收敛三档知情散户词汇、全篇零内部泄露与零原始 HTML（FAIL）
1. **收敛新刊 Layer 0–1 禁用词表（`>= 2026-11-26_1800`）**：
   - **放行主流投资者通用词**：`VIX`、`DXY`、`GLD`、`GDX`、`ETF`、`CFTC`、`COT`、`CDS`、`鹰派`、`鸽派`、`提保`、`轧空`、`逼空`、`上影线`（以及首次 6–12 字中文括号轻注的 `DFII10`、`2Y−FF`、`ON RRP`、`HY/CCC OAS`、`IOPV`、`bp`）；
   - **ASCII/版本禁用表（`CONVERGED_BANNED_LAYER01_ASCII` + 版本正则）**：
     `Subagent`, `stop-through`, `IFRS 9`, `HQLA`, `FVOCI`, `ROTCE`, `Call Wall`, `Put Wall`, `Daniel Ghali`, `Michael Hsueh`, `V[267].\d+`
   - **中文/混合禁用表（`CONVERGED_BANNED_LAYER01_LITERAL`）**：
     `子代理`, `63 路`, `63路`, `负 Gamma`, `负Gamma`, `R²=`, `R² =`, `梭哈`, `做T`, `做 T`, `短线波段`, `高弹性`, `收红`, `收绿`, `翻红`, `翻绿`, `六灯`
   - **全篇说教口号硬拦（`CONVERGED_BANNED_SLOGANS`，`>= 2026-11-26_1800`，扫描 Layer 0–3 全部正文与全部组件 JSON，含 `DAILY_GLOSSARY`！）**：
     `小白词典`, `直接抄`, `蠢事`, `1分钟定心丸`, `1 分钟定心丸`, `保命铁律`
   - *(历史旧刊 `< 2026-11-26_1800` 保持向后兼容，沿用旧版 68 词表。)*
2. **全篇内部工程词、版本号与文件名硬拦（`INTERNAL_LEAK_CUTOVER = 2026-11-26_0730`，扫描 Layer 0–3 全部正文与全部组件 JSON！）**：
   - `_INTERNAL_FILENAME_LEAK_RE` 全篇阻断：`master_snapshot.json`、`data_snapshot.json`、`market_state.json`、`audit_ledger.md`、`RSI_PLAYBOOK(.md)`、`rsi_metrics.json`、`sidecar.json`、`permissions.json`、`unified-edition.prompt.md`、`DAILY_FORMAT_SPEC.md`、`DAILY_REPORT_SPEC.md`、`AGENTS.md`、`GEMINI.md`、`SKILL.md`、任意 `*.py` 脚本名、`V[267].\d+`、`Subagent(s)`、`红队`、`法证`。
3. **裸 HTML 标签泄露检查**：正文代码块外 + 所有组件 JSON 内禁止出现未转义的 `div`/`span`/`table`/`tr`/`td`/`th`/`svg`/`rect`/`path`/`p`/`ul`/`ol`/`li`/`script`/`style`/`iframe`/`img`/`h1–h6`/`font`/`center` 等标签（组件内仅允许 `<br/>`、`<strong>`、`<code>`）。

### Gate 2：克制理性语调与感叹号红线
- **13 个全文禁用夸张/煽动词 (`BANNED_HYPE_WORDS`，剥离 `**`/`*` 后扫描，FAIL)**：
  `神准`, `分毫不差`, `100%胜率`, `100% 胜率`, `无情推翻`, `核雷`, `拉爆`, `血洗`, `焊死`, `史诗级`, `史诗轧空`, `彻底打脸`, `惊天验证`
- **感叹号红线（覆盖 Unicode `[!！‼⁉❗❕]`，剔除代码块与 `!=`）**：Layer 0–1 必须为 **0**（FAIL）；收敛新刊全文超过 **5** 个报 WARN（历史旧刊超过 2 个报 WARN）。

### Gate 3：彻底清除 Layer 0–1 平行打分（FAIL）
- 使用 Unicode 安全正则 `(?<![0-9.])[0-6](?:\.[05])?\s*[/／]\s*6(?![0-9])`，同步拦截小数 `X.5/6`、整数 `X/6` 及全角 `／6`。

### Gate 4：段落简洁度、加粗密度与裸数字反引号守卫（WARN）
- Layer 0–1 自然段去除 Markdown 语法后可见字符数 `> 240` 字报 WARN；
- **收敛新刊（`>= 2026-11-26_1800`）新增两项排版干净度预警**：
  - **加粗密度**：全文 `**...**` 加粗字符占正文去空白字符数 **`> 14.0%`** 报 WARN；
  - **裸数字反引号**：使用 `_BARE_NUM_BACKTICK_RE` 拦截用反引号包裹非代码数字、金额、百分比或带单位数值（如 `` `$3,589` ``、`` `+0.96%` ``、`` `757.35 元/克` ``），仅放行证券/期货/基金代码（如 `` `518660` ``、`` `008142` ``、`` `GCZ26` ``、`` `au2702` ``）与代码块。

### Gate 5：双快照算术、抗阻塞四关复算、部分过关拦截与全局治理
- 含 `<!-- MASTER_BASELINE {...} -->` 的主报告自动校验 `master_snapshot.json` 且锁定 `as_of_short` 一致；日报校验 `data_snapshot.json`（均含 `edition_id`/`new_buy_allowed`/`cfets_fixing_date`/`tier1_gates[].id` 对称结构）；
- 校验现货涨跌幅（`≤0.05`）、婚庆 1g/50g/百分比（`≤0.15`）、`tier1_gates` 长度 4 与求和、`tier_code`/`new_buy_allowed` 一致性、`a_class_tranche_split`、5 项 `cross_ratios`（检出 `cross_ratios_\d{4}` 报 WARN）、`etf_cn` 为对象、`institutional_targets` 同期限样本数与中位数复算；
- **抗阻塞市场校验（`edition_validation.py`）**：6 小时班次截点、4 小时节日 `pending` 复查、半日市 `provisional_close`、普通交易日 `provisional_close` **3 个自然日**核销、`no_row_confirmed` 支持 `*.cboe.com` 公告或 CSV `next_published_date > day`、30 分钟 VIX 盘中窗、四关固定 `id` 精确复算；
- **部分过关开仓话术拦截（`PARTIAL_ENTRY_CLAIM_RE`）**：全篇（正文 + 组件，自动排除明确否定/反例语境）禁止宣称“通过 0–3 关即可转黄/开新仓”；
- **当期正文与金店对齐放行（`_skip_domestic_brand_check`）**：核验正文含 `spot_gold_ny_close_rounded`；`data_caveats.category` 标准枚举为 `provisional_close`/`delayed_official`/`single_source`/`source_conflict`/`holiday_thin`/`publication_exception`，当处于中国内地 B 类休市或 `data_caveats` 含 `delayed_official`/`holiday_thin` 且明示金店/国内牌价/内盘/春节未开盘时，自动跳过 `brand_store_rmb` 与 `wedding_save_per_g_rmb` 对齐预警；
- **全局治理校验**：`market_calendar.json` 覆盖硬底线 **30 天**（`<60 天` 输出 `[INFO]` 提示）、核证有效期 **90 天**；`daily/SCORECARD.md` 零内部工程/RSI/脚本文件名词（`SCORECARD_BANNED_RE`）；`daily/RSI_PLAYBOOK.md` **软限 180 行（WARN）/ 硬上限 200 行（FAIL）** 及 Tier B/C 边界声明；`daily/rsi_metrics.json` 6 维求和自洽。

### Gate 6：PDF、手机端 HTML 与原生 OOXML DOCX 法证校验（含 `.artifacts.json` 凭据）
1. **`.artifacts.json` 凭据免误报陈旧**：当 Git checkout 等操作导致 PDF/DOCX/`latest_gold.html` 的 `mtime` 早于 Markdown 时，自动调用 `scripts/artifact_receipt.verify_receipt()` 核验源文件与编译脚本（`build_daily.py`/`docx_embed.py`/`chart_input.py`，主报告另含 `build_report.py`/`master_snapshot.json`）及 PDF/DOCX 输出 SHA-256 凭据，核验通过即放行陈旧警告；
2. **PDF 检查**：存在、`>=10KB`、文件头 `%PDF-`、未陈旧（或凭据有效）；
3. **手机端 HTML 检查（日报）**：`daily/latest_gold.html` 存在、`>=5KB`、含 `<meta name="viewport"`，且当期日报标题与修改时间（或凭据）一致；
4. **DOCX 检查**：具备 7 个核心部件（含 `styles.xml`/`settings.xml`/`footer1.xml`）；全部 XML 经 `ET.fromstring`；`<w:tbl>` > 0（严防 `textutil`）；零 `<w:sz-cs>` 与 `___DOCX_CHART_`；`<w:sectPr>` 位于 `<w:body>` 最末；`[Content_Types].xml` 所有 `<Default>` 早于 `<Override>` 且无悬空目标；严格验证 ECMA-376 顺序（`tblBorders` 早于 `tblLayout`、`tblGrid` 正整数且和 `<=9638`、页脚 `pBdr` 早于 `jc`、无 `pageBreakBefore` 早于 `keepNext`）；`wp:docPr/@id` 与 `pic:cNvPr/@id` 全局唯一；全部超链接/页脚/图片 `rId` 有效且图片为合法 PNG（`\x89PNG\r\n\x1a\n` 且 `>=2KB`），图数 `>=` Markdown 图表总数。

---

## 2. 排版组件升级、640px 矢量图防撞算法与原生 OOXML 架构

- **封面 4–6 张 KPI 网格（`.kpi-strip.cols-4`）**：`build_cover_html()` 在 `len(kpis) == 4` 时自动挂载 `.kpi-strip.cols-4` 渲染 4 列高密度单排卡片（5–6 张沿用 3 列网格），手机端 `max-width: 680px` 统一折为 2 列清晰排布；
- **防跨页信号/噪音网格（`.sn-grid`）**：`render_signal_noise()` 升级为 CSS Grid `minmax(0, 46fr) minmax(0, 54fr)` 双栏卡片 + `.sn-ul li { break-inside: avoid }`，根除旧版表格跨页撕裂断句问题；手机端 `max-width: 680px` 自动折为单栏堆叠；
- **图 1（`DAILY_CHART_TIMELINE` · 胶囊标签 + 2D 碰撞避让）**：
  - 画布固定 `viewBox="0 0 640 284"`（`vb_h=284`），数值经 `chart_input.normalize_chart()` 规范化；
  - 废除粗描边光晕（防止 PDF OCR 重影），改用 `_svg_label_pill()` 为每条参考线标签与数据点数值绘制圆角半透明白底胶囊（`fill="#ffffff" fill-opacity="0.88" rx="3"`）；
  - 通过 `_boxes_overlap_area()` 逐一计算候选位与已放置标签框（`placed_boxes`）的重叠面积：参考线标签尝试 **4 个垂直候选位**，数据点标签尝试 **8 个候选位**并对数据圆点 `dot_box` 施加 **2× 惩罚权重**，取最小重叠位确保零压字、零压点；
- **图 2（`DAILY_CHART_CROSS` · Back-to-Front 分层与动态网格刻度）**：
  - 严格按 **从后向前（back-to-front）** 顺序输出 SVG 图层：白底 → 行底纹 `stripes_svg` → 垂直网格刻度 `ticks_svg` → 资产名/条形/右标签 `rows_svg` → 零轴线 `x_zero` → 反向指标栏 `rev_svg`，避免网格线遮挡数据条或标签；
  - 刻度步长随 `cap_abs` 与实际正负最大涨跌幅自动选取 `2%` / `5%` / `10%`，且仅在实际负/正跨度与绘图区安全边界内绘制刻度线；
- **主报告编译器（`build_report.py`）清洁化**：清除封面与页眉/页脚中的 `V7.2` 内部版本号泄露与“今早”静态字样（改为动态 `{mmdd}基线`），图 2 月线蜡烛图动态读取 `monthly_candles` 低点与日期，图 3 历史教学案例保持常量冻结；
- **共享解析器、智能表格与手机端单文件 HTML**：`parse_markdown_to_html()` 共享支持双嵌套列表、`####`、`render_md_table()` 智能 `col-nowrap`（总宽 `<=25.0`）、原子单位保护与矢量状态胶囊；`build_gold_mobile_html()` 原子生成 `daily/latest_gold.html`（含吸顶导航、640px SVG 横滑与护眼深色模式）；
- **全套 Chrome 弹性编译与原生 OOXML（`CHROME_BIN` + 自动重试）**：
  - `docx_embed.resolve_chrome_bin()` 优先读取 **`CHROME_BIN` 环境变量**，依次回退 macOS Chrome 与 PATH 中 `google-chrome`/`chromium`/`chromium-browser`；
  - `build_daily.py` 与 `build_report.py` 的 PDF 打印配置 **`120s` 超时 + 独立临时 profile + 1 次自动重试（共 2 尝试）**，并写入 `.artifacts.json` SHA-256 凭据；
  - `docx_embed.py` 生成原生 ECMA-376 OOXML（`word/settings.xml` 自动刷新页码、真 `<w:tbl>`、无 `textutil`），单图 2× Retina PNG 光栅化配置 **`60s` 超时 + 1 次自动重试 + `2400→4800` 自动扩高**并经 `PIL` 裁切，全临时文件建于 `tempfile.mkdtemp()` 并在 `finally` 彻底清理。

---

## 3. 跨日、跨月与跨年运行保障

1. **双快照解耦与惰性加载**：日常只更新 `data_snapshot.json`（跨项目 SSOT 唯一写入权），常规班次仅惰性读取对称结构的 `master_snapshot.json` 核验 5 大触发条件，命中时才全量读取并同步更新主报告正文与 `MASTER_BASELINE`；
2. **外置长周期日历与抗阻塞校验**：`market_calendar.json` 已延展至 **`2027-06-30`**，集中维护美/中/港/欧/英/日/印休市叠加（A/B/C/GLOBAL）、半日市、独立 Cboe 现货 VIX 例外、四大央行议息、BCOM/GSCI 调仓及 `2027-03-14` 北美切换夏令时；覆盖硬底线 30 天（`<60 天` 自动提示展期）、核证有效期 90 天；
3. **月度账本归档**：跨月后可将 `daily/AUDIT_LOG.md` 与 `daily/CHANGELOG.md` 历史月度条目归档至 `daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md`（与发布器历史非空行保序校验兼容），防止单账本无限膨胀；
4. **动态跨月/跨年渲染**：主报告图 2 优先读 `monthly_candles`（跨入 12 月与 2027 年零重叠），图 4 机械时钟读 `mechanical_calendar`，图 7 投行读 `institutional_targets`，图 3 历史教学案例永久冻结。
