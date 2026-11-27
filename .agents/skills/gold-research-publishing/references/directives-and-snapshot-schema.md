# 指令 Schema、`data_snapshot.json` 契约与抗阻塞日历规范

本文档是 `lint_readability.py`、`edition_validation.py`、`chart_input.py` 与静态门户 `scripts/build_site.py` 黄金矢量图表渲染模块共享的精确数据结构说明书。所有字段名、必填键与类型均与现网 Python 源码逐字节对齐。

---

## 0. 新刊数据时点、抗阻塞日历与三账本契约（`edition_validation.py`）

`2026-11-25_1800_r2` 为沿用旧字段的最后已刊版本；`2026-11-26_1800` 为收敛主刊架构切分线（`CONVERGED_CUTOVER`）。新刊及同场修订按 [日报规格](../../../../gold/daily/DAILY_FORMAT_SPEC.md) 记录北京时间 `edition_id`、`as_of_short` 及显示时间：

- **班次与单向截点宽限（`MAX_EDITION_EARLY = 5min`、`MAX_EDITION_LAG = 6h`）**：新刊支持 **`0730`（早报）、`1130`（午报）与 `1800`（晚报）** 三个班次，北京时间 `as_of_short` 须落在所标班次 **`[-5 分钟, +6 小时]`** 单向窗口内（`07:25–13:30` / `11:25–17:30` / `17:55–次日 00:00`）；封面 `DAILY_META.timestamp` 与快照 `as_of_bjt` 均须展示与 `as_of_short` 一致的北京时间（支持 ISO `YYYY-MM-DD HH:MM` 或中文 `YYYY年M月D日... HH:MM`）。`11:30 CST` 对应美东前一日 `22:30 EST` / `23:30 EDT`（非 Cboe 现货 VIX 连续发布窗），`vix_live` 与 `vix_live_as_of` 同 `07:30` 一律留空。
- **四关固定 `id` 顺序**：`tier1_gates` 与 `DAILY_CHART_SWITCH.checks` 必须严格使用 `("real_yield", "rate_spread", "vix", "ny_close")` 固定顺序，由 `edition_validation.recheck_entry_gates()` 根据原始精度输入复算。
- **外置日历覆盖与抗阻塞容忍（`market_calendar.json`）**：
  - `market_calendar.json` 覆盖已延展至 **`2027-06-30`**（含耶稣受难日 `2027-03-26`、清明 `2027-04-05`、劳动节 `2027-05-01..05`、阵亡将士纪念日 `2027-05-31`、六月节补休 `2027-06-18` 等），`coverage` 必填 `start_date`、`end_date`、`verified_on`、`vix_schedule_source`（HTTPS）；
  - **覆盖硬底线 `MIN_CALENDAR_HORIZON = 30 天`**（不足 30 天报 FAIL；30–59 天打印 `[INFO]` 提示建议滚动展期）；**核证有效期 `MAX_CALENDAR_VERIFIED_AGE = 90 天`**；首刊核证日须 `<= 观测日`，修订刊不得晚于实际验收日；
  - `start_date` 须覆盖截点前最新十个 Cboe 现货指数交易日；每个 `US_EQUITY` 相关的 `A`/`GLOBAL` 非周末日期都须在 `vix_session_exceptions` 独立登记。
- **Cboe 现货 VIX 独立日历与非阻塞核验规则**：
  - 普通工作日发布窗口为 `03:15–09:25` 和 `09:31–16:15 ET`；盘中读数仅在与截点处于同一连续发布窗口且间隔 **≤30 分钟**（`MAX_VIX_QUOTE_AGE = 30min`）时方可用；休市或无合格盘口时 `vix_live` 与 `vix_live_as_of` 必须**同时留空**（按最近官收复算第 3 关）。
  - `vix_10d_session_closes` 逐日升序保留最近 10 条 `{"date": "YYYY-MM-DD", "close": num}`，`vix_daily_source` 必须为 `https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv`。
  - **普通交易日非阻塞协议**：遇 Cboe 官方 CSV 尚未批量更新当日行或暂不可取时，在 `vix_daily_row_checks[YYYY-MM-DD]` 登记 `status`（`published` / `provisional_close` / `pending`）、北京时间 `checked_at`（收盘后至截点间）、`source`（`provisional_close` 可为有效 HTTPS 权威源，其余须为 `VIX_DAILY_SOURCE`）与 `note`；其中 **`provisional_close` 须在 3 个自然日内以官方 CSV 终值核销**（`cutoff.date() - day > 3 天` 报 FAIL），且次日班次遇 `provisional_close`/`pending` 须在本班 6 小时窗口内重查官方 CSV。
  - **美国假日与半日市非阻塞协议**：对设 `daily_row_check_after_et` 的例外日（核验起点已过且可能落入十日窗），在 `vix_daily_row_checks[YYYY-MM-DD]` 留记录：
    - **半日市（如黑五 `2026-11-27`、平安夜 `2026-12-24`，`windows_et` 非空）**：允许 `published`、`provisional_close`（有效 HTTPS 来源）、`pending`、`no_row_confirmed`；
    - **全休假日（`windows_et == []`）**：允许 `published`、`pending`、`no_row_confirmed`；
    - **`pending` 复查间隔**：`MAX_PENDING_DAILY_CHECK_AGE = 4 小时`（截点前 4 小时内须重查官方 CSV）；
    - **`no_row_confirmed` 双轨自证（二选一）**：① 附 Cboe 官方域（`*.cboe.com`）公告链接 `confirmation_source`；② 以官方 CSV 自证 `next_published_date`（`source == VIX_DAILY_SOURCE` 且 `day < next_published_date <= cutoff.date()`）。
    - 参考：[Cboe 现货指数方法](https://cdn.cboe.com/resources/indices/Volatility_Index_Methodology_Cboe_Volatility_Index.pdf) · [Cboe 假日时刻](https://www.cboe.com/about/hours/us-options/) · [Cboe 日线表](https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv)

- **三账本同期标记与月度归档**：
  - 发刊严检前，在 `daily/CHANGELOG.md` 写一条 `<!-- GOLD_EDITION_CHANGELOG <edition_id> -->`，在 `daily/SCORECARD.md` 写一条 `<!-- GOLD_EDITION_SCORECARD <edition_id> -->`，并在 `daily/AUDIT_LOG.md` 写入唯一一条同期 `GOLD_EDITION_REVIEW` JSON 注释（`sources` 四关各有 ≥1 条 HTTPS 证据链接；`forecast_review.status` 取 `settled`/`none_due`/`pending_evidence`，`settled` 必附 HTTPS `sources`）；
  - `AUDIT_LOG.md` 与 `CHANGELOG.md` 支持按月归档历史条目至 `gold/daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md`（归档文件 + 活跃文件合并后须保留全部历史非空行原序）。

```markdown
<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-26_1800",
  "as_of_short": "2026-11-26 18:30",
  "note": "列明四关核验、盘口来源、滞后项清零与跨时区争议的处理结果。",
  "sources": {
    "real_yield": ["https://fred.stlouisfed.org/series/DFII10"],
    "rate_spread": ["https://fred.stlouisfed.org/series/DGS2", "https://www.newyorkfed.org/markets/reference-rates/effr"],
    "vix": ["https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"],
    "ny_close": ["https://www.investing.com/currencies/xau-usd-historical-data"]
  },
  "forecast_review": {
    "status": "settled",
    "note": "写明到期预判的客观结案或待披露项的下次核验点。",
    "sources": ["https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"]
  }
} -->
```

---

## 1. 10 个 `DAILY_*` 组件 JSON Schema 规范

所有组件必须以独立 HTML 注释块形式写在 Markdown 中：`<!-- DIRECTIVE_NAME { ...合法 JSON... } -->`。

> **强约束**：JSON 语法错误会导致 `lint_readability.py` 与静态站构建器直接报错中止，且 Gate 0 校验全部顶层与嵌套必填键；Layer 0–1 区域内（及 `DAILY_META`/`DAILY_VERDICT`/`DAILY_SIGNAL_NOISE` 无论位于何处）的 JSON 字符串均接受收敛版 Gate 1 三档词表、Gate 2 零感叹号与 13 煽动词、Gate 3 禁 `X/6` 扫描；**全部层级与全部组件（含 Layer 2/3 及 `DAILY_GLOSSARY`）均接受全篇内部工程词/版本号/文件名泄露拦截，收敛新刊（`>= 2026-11-26_1800`）并全篇统一拦截 6 个居高临下说教口号（`小白词典`/`直接抄`/`蠢事`/`1分钟定心丸`/`1 分钟定心丸`/`保命铁律`）**。

### 1.1 `DAILY_META`（封面横幅 + 4–6 张核心 KPI 卡）
- **必填键（Gate 0）**：`tag`, `kpis`；新刊（及同场修订）同时必填 **`edition_id`**, **`as_of_short`**（并与文件名、快照及 `timestamp` 展示时间严格一致）
- **完整字段**（以下 `kpis` 报价与日期仅作 **Schema 历史示例**，实时值一律以 `data_snapshot.json` 为准）：
  ```json
  {
    "edition_id": "2026-11-26_1800",
    "as_of_short": "2026-11-26 18:30",
    "tag": "每日黄金深度研报 · 18:00 晚报",
    "timestamp": "2026年11月26日（周四）18:30",
    "summary": "上金所收盘与感恩节美盘休市应对策略",
    "accent": "#b45309",
    "footer_title": "每日黄金深度研报（18:00 晚报）",
    "kpis": [
      {"label": "国内原料价 / 品牌金店", "val": "769 元/克", "sub": "银行条 788 元 · 金店 1,078 元"},
      {"label": "国际现货金（纽约官收）", "val": "$3,589/盎司", "sub": "日内深V反抽 · 较年初顶 -36%"},
      {"label": "买金四步红绿灯", "val": "🔴 红灯停（1/4 关）", "sub": "暂不新买 · 真实利息差 1 基点"},
      {"label": "核心压制：真实利息", "val": "2.73%（20年高位）", "sub": "需降破 2.72% 方过第 1 关"}
    ]
  }
  ```
- **硬限制**：收敛新刊（`>= 2026-11-26_1800`）合法数量为 **4–6 张卡**（4 张自动触发 `.kpi-strip.cols-4` 单排高密度横条，手机端自动折为 2×2）；每条 `sub` 严控 **≤17 个汉字当量**（`>17.5` 报 WARN）；含 `红绿灯` 字样的 KPI `val` 须与快照档位及 `X/4` 一致；`footer_title` 严禁含 `V2.x/V5.x/V6.x/V7.x`。

### 1.2 `DAILY_VERDICT`（Layer 0 首屏 30 秒白话行动裁决卡）
- **必填键（Gate 0）**：`level`, `headline`, `traffic_light`, `bullets` (数组), `risk_line`；新刊同时必填 **`tier_code`** (`"Tier 0"|"Tier 1"|"Tier 2"|"Tier 3"`), **`new_buy_allowed`** (bool), **`tier1_passed`** (int)（三项与快照逐项校验一致）
- **完整字段**：
  ```json
  {
    "level": "L1",
    "badge": "🟡 L1 节点前瞻 · 仍非买点",
    "traffic_light": "🔴 红灯停（满足 1/4 关 · 新仓 0%）",
    "tier_code": "Tier 0",
    "new_buy_allowed": false,
    "tier1_passed": 1,
    "headline": "隔夜金价深 V 反抽但四步条件仅过一关，继续维持空仓观望。",
    "bullets": ["要点一", "要点二", "要点三"],
    "risk_line": "若 10 年实际利率重返 60 日收盘新高，需防二次流动性下杀。"
  }
  ```
- **配色规则**：`level` 仅取 `"L0"`（灰蓝 `#475569`）、`"L1"`（暖琥珀 `#b45309` 菱形）、`"L2"`（深红 `#b91c1c`），`badge` **严禁使用 `🟢`**。

### 1.3 `DAILY_SIGNAL_NOISE`（`.sn-grid` 信号 vs 噪音双栏过滤网格）
- **必填键（Gate 0）**：`signals`, `noises`（每项须为含 `head`/`body` 的对象；`signals` 建议 0–2 件，`>2` 报 WARN）
- **渲染升级**：由 `.sn-grid` 双栏 CSS Grid（`46fr / 54fr`）渲染，手机端自动堆叠单栏。

### 1.4 `DAILY_PERSONA`（A / B / D / C 行动卡）
- **必填键（Gate 0）**：`cards`（非空数组，每项须含 `group` / `heading` / 数组 `actions`，可选 `subtitle` / `avoid`）。
- **配色映射**：`"A"` `#0284c7`、`"B"` `#b45309`、`"C"` `#059669`、`"D"` `#4f46e5`。

### 1.5 `DAILY_GLOSSARY`（关键词白话速查 · 收敛新刊可选 0–1 次）
- **必填键（Gate 0）**：`terms`（非空数组，每项含 `term`/`plain`）。收敛新刊（`>= 2026-11-26_1800`）允许 `0` 或 `1` 次（`>1` 次报 FAIL）；全篇及全部组件（含 `DAILY_GLOSSARY`）硬拦截 `小白词典`/`直接抄`/`蠢事`/`1分钟定心丸`/`1 分钟定心丸`/`保命铁律`；推荐标题为 **「关键词白话速查」**（网站另配全局术语白话浮窗）。

### 1.6 `DAILY_LAYER_BADGE`（层级眉批）
- **必填键（Gate 0）**：`label`（可选 `tone`: `"deep"` 或 `"pro"`）。当 `tone == "deep"` 时作为 `lint_readability.py` 切分 Layer 0–1 与 Layer 2 的官方边界标记之一（另三个为 `^#\s*第二部分`、`^##\s*专题一`、`^##\s*周末专题`）。

### 1.7 `DAILY_TRUST_BAR`（文末核验徽章 · 收敛新刊可选 0–1 次）
- **必填键（Gate 0）**：`items`（严格 3 条非空文字），可选 `title`/`note`。收敛新刊允许 `0` 或 `1` 次（`>1` 次报 FAIL）；**严禁在 `items`/`note` 中泄露任何内部文件名、版本号或工程术语（改为面向读者的自然中文说明如「公开预测记分卡与官方数据核验」）**。

### 1.8 `DAILY_CHART_TIMELINE`（图 1：走势折线矢量图）
- **必填键（Gate 0）**：`points`（非空；禁止把 `highlight_zones` 误写为 `zones`）；数值经共享模块 `chart_input.py` 规范化（支持小数、千位逗号、百分值与 Unicode 负号，`y_min < y_max`，`highlight_zones` 索引须为整数）。
- **渲染特性**：`viewBox="0 0 640 284"`（`vb_h=284`），标签采用半透明白底圆角胶囊 `_svg_label_pill()` + 2D 碰撞面积最小化避让算法。

### 1.9 `DAILY_CHART_CROSS`（图 2：1:1 真实线性跨资产分化条形图）
- **必填键（Gate 0）**：`items`（非空，每项含 `label` / 合法数值 `pct`，可选 `pct_label`/`tag`/`highlight`）、可选 `reverse_items`（每项含 `label`/`detail`）。
- **硬限制与视觉升级**：每条 `items[].label` 视觉宽严控 **≤8.5 汉字当量**（Gate 0 `>9.5` 报 FAIL / `>9.0` 报 WARN）；优先读取显式 `"highlight": true/false`；采用 **back-to-front 分层渲染 + 动态垂直网格刻度**（步长自动取 `2%`/`5%`/`10%` 并限定在实际正负极值范围内）。

### 1.10 `DAILY_CHART_SWITCH`（图 3：历史水位尺 + 四步红绿灯体检仪）
- **必填键（Gate 0）**：`gauges`（非空，`pct`/`threshold_pct ∈ [0, 100]`，禁误写 `safe_pct`）, `checks`（严格 4 项，每项含布尔 `passed` 及 `name`/`line1`/`line2`；新刊同时必填固定顺序 **`id`**：`"real_yield"`, `"rate_spread"`, `"vix"`, `"ny_close"`）。
- **口径同步**：`status_line` 须含快照档位名称与 `X/4`；若设 `status_color` 须与档位色值（`#dc2626`/`#d97706`/`#16a34a`）严格一致；`checks[].passed` 顺序须与快照 `tier1_gates` 完全一致。

---

## 2. 主报告 7 张内置矢量图占位符与顺排编号（由静态门户引擎直接渲染）

主报告顶部必须含 `<!-- MASTER_BASELINE {"as_of_short": "YYYY-MM-DD HH:MM", "snapshot": "master_snapshot.json"} -->` 基线锁；静态门户渲染引擎自动按实际出现顺序顺排为 **`图 1`–`图 7`**（7 图必须各出现一次）：

| 出现顺位 | Markdown 占位符 | 渲染函数与图表内容 |
| :---: | :--- | :--- |
| **图 1** | `<!-- CHART_1 -->` | `svg_chart_real_vs_nominal`（1971–当前名义 vs 扣通胀真实购买力金价） |
| **图 2** | `<!-- CHART_2 -->` | `svg_chart_2026_bear_and_vacuum`（动态月线蜡烛图，优先读 `monthly_candles` 动态低点与跨年翻页） |
| **图 3** | `<!-- CHART_4 -->` | `svg_chart_48h_crash_and_weekend`（**冻结历史教学案例**：11/18–24 流动性冲击与高利息天花板） |
| **图 4** | `<!-- CHART_5 -->` | `svg_chart_mechanical_clock_and_switch`（数据驱动跨年机械时钟 + 四步红绿灯） |
| **图 5** | `<!-- CHART_3 -->` | `svg_chart_china_tax_channels`（中国 2025 年 11 号公告下七大渠道每克成本与省钱对比） |
| **图 6** | `<!-- CHART_7 -->` | `svg_chart_fx_and_cross_ratios`（人民币升值汇兑账本 + 50 年跨资产比价尺） |
| **图 7** | `<!-- CHART_6 -->` | `svg_chart_institutional_targets`（数据驱动 12 大投行 2027 目标，区分 `pt`/`avg`/`horizon`/`stale`） |

---

## 3. 双快照数据域（`data_snapshot.json` & `master_snapshot.json`）、跨项目 SSOT 与 Gate 5 契约

日报使用 `data_snapshot.json`（跨项目 SSOT 唯一写入源，Step 4 权益轨零延迟只读校验），主报告使用独立锁定的 `master_snapshot.json`（**对称结构**：同样补齐 `edition_id`、`new_buy_allowed`、`cfets_fixing_date` 及 `tier1_gates[].id`）。快照包含 11 大核心域：

1. **班次、紧迫度与 SSOT 裁决元信息**：`edition_id`, `as_of_bjt`, `as_of_short`, `master_version`, `daily_alert_level` (`L0`/`L1`/`L2`), `daily_alert_label`, `tier_code` (`Tier 0`/`Tier 1`/`Tier 2`/`Tier 3`), **`new_buy_allowed` (bool，与 `tier_code != "Tier 0"` 强制一致)**, `tier_label`, `tier_status_sub`, `tier_cover_sub`, `tier1_passed`, `tier1_total`, `a_class_tranche_split` (`"30% + 45% + 25%"`)。
2. **四步红绿灯明细 (`tier1_gates`)**：严格长度 4 的数组，新刊与主报告均按固定 `id` 顺序（`real_yield`, `rate_spread`, `vix`, `ny_close`），每项含 `id`, `name`, `passed` (bool), `reading`, `threshold`, `detail`。
3. **全球贵金属、内盘实盘与第 4 关日期锚**：`spot_gold_ny_close_usd`, `spot_gold_ny_close_rounded`, **`spot_gold_ny_close_date`**, `spot_gold_ny_change_pct`, `spot_gold_live_usd`, `spot_gold_intraday_high_usd`, `spot_gold_intraday_low_usd`, `spot_gold_prev_close_usd`, `spot_gold_2026_peak_usd`, **`tier1_gate4_threshold_usd`**, **`tier1_gate4_threshold_date`**, **`tier1_gate4_target_date`**, `tier1_gate4_next_threshold_usd`, `comex_front_settle_usd`, `comex_copper_usd_lb`（官结）, `spot_silver_usd`, `spot_platinum_usd`, `shfe_gold_night_rmb`/`day_rmb`, `sge_am_fix_rmb`/`pm_fix_rmb`, `sge_autd_*`, `sge_au9999_*`, `sge_same_ts_premium_rmb`。
4. **利率、汇率与长期估值锚**：`usd_cny`, **`usd_cny_1630`**（16:30 在岸人民币官收）, `usd_cny_short`, `usd_cnh_live`, `cfets_cny_fixing`, **`cfets_fixing_date`**, `dxy`, `us2y_pct`, `us10y_pct`, `us30y_pct`, `effr_pct`, `spread_2y_ff_bp`, `dfii10_live_pct`, `dfii10_fred_official_pct`, `t10yie_fred_pct`, `dfii10_20d_peak_pct`, `dfii10_60d_peak_pct`, `dfii10_percentile_20y`, `fair_value_usd`/`rmb`, `cpi_u_index`, `cpi_1980_anchor_usd`, `gold_mcap_to_us_m2_pct`（线性乘算仅限月内快算；每月第 4 个周二 FRED `M2SL` 变动 ≥1% 或 WGC 年度地上存量更新时必须重锚定分母常数）, `etf_2y_avg_cost_usd`, `sma_200w_*`。
5. **VIX 独立日线与盘中校验域**：`vix_close`, `vix_change_pct`, **`vix_live`** (num | null), **`vix_live_as_of`** (str | null，与 `vix_live` 成对), `vix_10d_peak_close`, `vix_10d_peak_date`, `vix_10d_window_end`, **`vix_10d_session_closes`** (`[{"date": "YYYY-MM-DD", "close": num} × 10]`), **`vix_daily_row_checks`**（按美东日期键记录 `status`/`checked_at`/`source`/`note` 及可选 `confirmation_source`/`next_published_date`）, `vix_daily_source`。
6. **能源、风险资产、海外金矿/ETF 与信用配管**：`brent_settle_usd`, `wti_settle_usd`, `ttf_gas_eur`, `nvda_close_usd`, `spx_close`, `ndx_close`, `btc_usd`, `gdx_close_usd`, `gld_close_usd`, `gld_holdings_tonnes`, `gld_daily_flow_tonnes`, `gdx_gld_ratio`, `hy_oas_bp`, `ccc_oas_bp`, `coreweave_cds_bp`, `sofr_iorb_bp`, `on_rrp_usd_m`。
7. **国内黄金 ETF 标准无日期键 (`etf_cn`)**（以下数值仅作 **Schema 历史示例**，实时值一律以 `data_snapshot.json` 为准）：
   ```json
   "etf_cn": {
     "as_of_date": "2026-11-25",
     "518880": {"close": 7.169, "chg_pct": -3.00, "nav": 7.1947, "flow_100m": -4.33},
     "159937": {"close": 7.155, "chg_pct": -3.00, "nav": 7.1788, "flow_100m": -1.04},
     "518660": {"close": 7.200, "chg_pct": -3.02, "nav": 7.2247, "flow_100m": -0.17}
   }
   ```
8. **面向读者的结构化缺口声明数组 (`data_caveats`)**：纯读者中文、**零内部文件名/工程词**，每项包含 8 个标准字段：
   ```json
   "data_caveats": [
     {
       "id": "cn_retail_quotes_1126_preopen",
       "market": "gold",
       "category": "delayed_official",
       "severity": "warn",
       "item": "国内 11/26 银行金条与品牌金店开盘牌价尚未挂出",
       "detail": "截至 08:30 国内现货与四大行贵金属尚未开盘调价，暂沿用 11/25 牌价。",
       "impact": "受隔夜外盘反抽影响，开盘后存在小幅上调可能，晚报封账。",
       "next_review": "2026-11-26_1800"
     }
   ]
   ```
   *(标准 `category` 枚举：`provisional_close`、`delayed_official`、`single_source`、`source_conflict`、`holiday_thin`、`publication_exception`；`severity`：`warn` / `info`。当处于中国内地 B 类休市或 `data_caveats` 含 `delayed_official`/`holiday_thin` 且说明金店/国内牌价/内盘/春节未开盘时，Gate 5 自动放行金店价对齐预警。)*
9. **四大央行与 12 大行样本汇总**：`fed_dec_hike_prob`/`ecb_`/`boe_`/`boj_`, `bank_2027_yearend_median_usd`, **`bank_2027_yearend_sample_count`**, `bank_2027_avg_median_usd`, **`bank_2027_avg_sample_count`**, `bank_2027_fx_median`；`institutional_targets` 每项含 `name`, `lo <= base <= hi`, `kind ∈ ("pt", "avg", "horizon", "stale")` 及可选 `annual_average_usd`，由 Gate 5 按同期限复算样本数与精确中位数。
10. **中国零售渠道成本 (`rmb_channels`) 与无日期跨资产比值 (`cross_ratios`)**：`rmb_channels` 含 `etf_base_rmb`、`bank_accum_rmb`、`bank_bar_rmb`、`bank_bar_plus_craft_rmb`、`shuibei_nonmember_bar_rmb`、`shuibei_taxed_jewelry_rmb`、`brand_store_rmb`、`wedding_save_per_g_rmb`、`wedding_save_50g_rmb`、`wedding_save_pct`、`note`；跨资产比值唯一标准无日期键 `cross_ratios`（禁写遗留日期键 `cross_ratios_XXXX`）。
11. **结构化图表数组与三大信任资产**：`monthly_candles`、`mechanical_calendar`、`trust_assets`。

### Gate 5 强制算术与逻辑复算契约（偏离即报 FAIL / WARN）
1. 现货涨跌幅与四舍五入：`|spot_gold_ny_close_rounded - spot_gold_ny_close_usd| <= 0.5`；`|spot_gold_ny_change_pct - ((ny_close / prev_close) - 1) * 100| <= 0.05`；
2. 婚庆渠道省钱：`wedding_save_per_g_rmb == brand_store_rmb - bank_bar_plus_craft_rmb`（容差 `0.01`）、`wedding_save_50g_rmb == save * 50`（容差 `0.01`）、`|wedding_save_pct - (save / brand) * 100| <= 0.15`；
3. 四步红绿灯、SSOT 开关与精确复算：`len(tier1_gates) == 4`、`sum(passed) == tier1_passed`、`tier_code in Tier 1–3` 时必 `tier1_passed == 4`、`new_buy_allowed == (tier_code != "Tier 0")`、`a_class_tranche_split == "30% + 45% + 25%"`；新刊经 `edition_validation.recheck_entry_gates()` 复算四关并核对正文/组件零部分过关开仓误导话术；
4. 跨资产比值与机构样本复算：`gold_wti_ratio`/`gold_brent_ratio`/`gold_silver_ratio <= 0.15`、`gold_platinum_ratio <= 0.05`、`gold_spx_ratio <= 0.015`；`institutional_targets` 样本数与精确中位数必须与 `bank_2027_*` 逐项一致；
5. 当期正文核对：核验正文含 `spot_gold_ny_close_rounded`；非 B 类国内休市且 `data_caveats` 未声明金店未开盘时，核验正文含 `brand_store_rmb` 与 `wedding_save_per_g_rmb`。

---

## 4. 五轨时段差异速查矩阵（由 `market_calendar.json` 驱动）

| 轨道 | 时段（`+08:00`） | 文件名 | 核心覆盖范围 | 3 图映射 |
| :--- | :--- | :--- | :--- | :--- |
| **工作日早报** | 周一至周五定时 `07:30`（允许窗 `07:25–13:30`） | `daily/YYYY-MM-DD_0730_早报_黄金深度研报.md` | 纽约 06:00 终盘（夏令时 05:00）、COMEX 02:30 官结（夏令时 01:30）、国内 02:30 夜盘、美欧股债油、联储/白宫动向、07:30 亚盘早段 | 图 1 隔夜折线 / 图 2 跨资产分化 / 图 3 水位尺+四步灯 |
| **工作日午报** | 周一至周五定时 `11:30`（允许窗 `11:25–17:30`） | `daily/YYYY-MM-DD_1130_午报_黄金深度研报.md` | **上金所/沪金 11:30 早盘官收与同分钟平价溢价（`XAU × USD/CNY ÷ 31.1034768`）**、国内四大行金条与品牌金店当日最新挂牌价、亚盘美期美债、09:15 CFETS 中间价 / 09:20 央行 OMO / 09:30 统计局官发数据（美东非 VIX 窗口，`vix_live` 留空） | 图 1 亚盘早段至午盘折线 / 图 2 亚太金银股汇早盘分化 / 图 3 水位尺+四步灯 |
| **工作日晚报** | 周一至周五定时 `18:00`（允许窗 `17:55–次日 00:00`） | `daily/YYYY-MM-DD_1800_晚报_黄金深度研报.md` | 上金所 15:30 终盘及清算表、上期所 15:00 收盘及龙虎榜、A/H 与金矿/金饰股收盘及财报、16:30 在岸人民币官收（`usd_cny_1630`）、伦敦盘与欧洲数据 | 图 1 日内亚欧分时 / 图 2 亚太与欧盘股汇金矿分化 / 图 3 水位尺+四步灯 |
| **周末专项版** | 周六 / 周日休市 | 沿用 `0730_早报` / `1130_午报` / `1800_晚报` 文件名，主标题加`（周末专项版）` | 休市市场明标「休市 · 沿用周五终盘」；聚焦 XAUT/PAXG 与 BTC、周五盘后期货持仓周报、菜百/水贝周末线下客流、周日中东股市与欧美周末访谈 | 图 1 本周 5 日复盘 / 图 2 全周累计分化 / 图 3 周末静态水位尺+下周门槛 |
| **工作日局部休市叠加** | 周一至周五遇中美欧英日港印单边假日（查 `market_calendar.json`） | 沿用当日工作日文件名，文内明标休市市场与复盘时刻 | **A 类美盘休市/半日市提前收**：沿用上一 NY 终盘，半日市支持 VIX `provisional_close`；**B 类中国休市**：聚焦外盘与离岸汇率且自动放行金店价对齐；**C 类欧英日港印单边休市**：局部标注休市时段 | 同对应早/午/晚报 3 图结构，严禁编造休市盘口 |
