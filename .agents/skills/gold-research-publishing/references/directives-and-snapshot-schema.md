# 指令 Schema、`data_snapshot.json` 契约与四轨矩阵

本文档是 `build_daily.py`、`build_report.py` 与 `lint_readability.py` 共享的精确数据结构说明书。所有字段名、必填键与类型均与现网 Python 源码逐字节对齐。

## 新刊数据时点与台账

`2026-11-25_1800_r2` 为沿用旧字段的最后已刊版本。后续新增日报及同场修订按 [日报规格](../../../../gold/daily/DAILY_FORMAT_SPEC.md) 记录北京 `edition_id`、`as_of_short` 及显示时间，四关使用 `real_yield`、`rate_spread`、`vix`、`ny_close` 的固定顺序，含图 3 的对应 `id`。

`market_calendar.json` 的 `coverage` 含 `start_date`、`end_date`、`verified_on`、`vix_schedule_source`。核证日用北京时间日期，随维护更新，不能比本刊数据截点早逾 60 日。首刊的核证日须在观测日或之前。修订刊可用晚于原截点的核证日，最晚为实际验收当天；仍按原截点确定十日覆盖和盘中观测资格。开始日期须覆盖截点前最新十个 Cboe 现货指数交易日，结束日期须覆盖刊期后至少 60 天。月底与跨年时重核并滚动展期。每个美国休市或半日市的非周末日期，都需在 `vix_session_exceptions` 留独立记录。日期及 `windows_et`、`official_close_et` 都按美国东部时间，程序按 IANA 时区换算夏令时。

- 普通工作日的现货指数发布时段为 03:15–09:25 和 09:31–16:15 ET。截点所属连续发布时段与报价时点相同，且相差不超过 30 分钟，方可用盘中数值。
- `windows_et` 只登记已核实、可采用的现货指数发布窗。“无 RTH”和“没有现货盘中发布窗”均不能推导出“没有日线”。2023、2024、2025 年感恩节以及 2026 年 MLK 日、总统日的 Cboe 官方 CSV 均有独立 OHLC。对假日或半日市，只掌握期权或参考交易时段而尚无现货指数精确终盘证据时，设 `official_close_et: null`，以 `daily_row_check_after_et` 记录保守的核验起点。例 `{"windows_et": [], "official_close_et": null, "daily_row_check_after_et": "11:30"}`。这个时刻不声称为指数终盘、更不承诺 CSV 已发布。指数期权或期货可交易，也须证实现货指数实际发布才能填写盘中值。
- `vix_10d_session_closes` 逐日保留最近十个已收盘交易日的 `date` 与 `close`，略过没有完整日收的日期，保留有完整日收的半日市。`vix_daily_source` 必须为 Cboe 现货指数官方历史表。早报（北京时间 `07:30`，美东同日盘后）时 Cboe 官方 CSV 通常尚未批量更新当日行（常于北京时间 `10:15` 前后更新），或早/晚报遇该 CSV 延迟/暂不可取时，**不阻塞发刊**：可在 `vix_daily_row_checks` 以该美东交易日期为键记录 `status: "provisional_close"`（采信 Cboe 官网产品页或权威源交叉一致的 `16:15 ET` 收盘读数计入十日末行，`source` 记该 HTTPS 来源，次日班次须重查官方 CSV 并清零）或 `status: "pending"`（`source` 记官方 CSV URL，十日序列暂沿用截至前一已发布交易日的十条官方行并披露缺口，下一班次重查补录）。留空 `vix_live`、`vix_live_as_of` 时按最近官收复算第三关，不丢弃官收及其日期。 [Cboe 现货指数方法](https://cdn.cboe.com/resources/indices/Volatility_Index_Methodology_Cboe_Volatility_Index.pdf) · [Cboe 假日时刻](https://www.cboe.com/about/hours/us-options/) · [Cboe 日线表](https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv)
- 核验起点已到且该日可能进入十日窗口时，在黄金快照 `vix_daily_row_checks` 以美国东部交易日期为键留记录。值写 `status`、北京时间 `checked_at`（须在核验起点至本刊截点之间）、`source`（Cboe 官方历史 CSV URL）、`note`（核对结果与缺口）。官方 CSV 有该日行时用 `published` 并纳入回看。查到末行仍停在此前交易日时用 `pending`，本刊按已见的最近官收复算并披露缺口，下一班在截点前一小时内重查。只有另有 Cboe 原始依据确认无当日行时才用 `no_row_confirmed`，并附 `confirmation_source`。感恩节 18:00 北京时间在美国东部 05:00，11:30 ET 的核验点尚未到。次日 07:30 早报须核 CSV 日期及当日实际行状态。 [Cboe 假日分段说明](https://www.cboe.com/document/tech-spec/document/technical-specifications/cboe-options-exchange-245-faq) · [Cboe 半日市技术规范](https://www.cboe.com/document/tech-spec/document/technical-specifications/cboe-titanium-u.s.-options-fix-specification)

发刊前在 `daily/CHANGELOG.md` 和 `daily/SCORECARD.md` 的当期记录旁分别写一条 `<!-- GOLD_EDITION_CHANGELOG 2026-11-26_0730 -->`、`<!-- GOLD_EDITION_SCORECARD 2026-11-26_0730 -->`。在 `daily/AUDIT_LOG.md` 的同一期写下本次核验结论与原始证据。以下链接只演示结构，发刊时替换为能追溯相应读数、时点、精确价格和前高的具体页面。没有当期到期预测时用 `none_due`，到期但缺一手结案证据时用 `pending_evidence` 并说明缺何材料。`settled` 须提供结案证据链接。

```markdown
<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-26_0730",
  "as_of_short": "2026-11-26 07:30",
  "note": "列明四关核验、盘口来源与跨时区争议的处理结果。",
  "sources": {
    "real_yield": ["https://fred.stlouisfed.org/series/DFII10"],
    "rate_spread": ["https://fred.stlouisfed.org/series/DGS2", "https://www.newyorkfed.org/markets/reference-rates/effr"],
    "vix": ["https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"],
    "ny_close": ["https://example.com/replace-with-the-original-ny-session-record"]
  },
  "forecast_review": {
    "status": "pending_evidence",
    "note": "写明未披露的数据、原刊锁定标准及下次核验点。",
    "sources": []
  }
} -->
```

---

## 1. 10 个 `DAILY_*` 组件 JSON Schema 规范

所有组件必须以独立 HTML 注释块形式写在 Markdown 中：

```markdown
<!-- DIRECTIVE_NAME { ...合法 JSON... } -->
```

> **强约束**：JSON 语法错误会导致 `build_daily.py` 直接抛出 `ValueError` 中止编译，且 Gate 0 会检验每个指令的必填键；Layer 0–1 区域内（以及 `DAILY_META` / `DAILY_VERDICT` / `DAILY_SIGNAL_NOISE` 无论位于何处）的所有 JSON 字符串值同样接受 Gate 1（**68 个禁词：47 个 ASCII/版本代码 + 21 个中文/混合黑话**）、Gate 2（0 感叹号 & 13 煽动词）、Gate 3（禁 `X.X/6`）与 Gate 5（过时事实）扫描。

### 1.1 `DAILY_META`（封面横幅 + 6 张 KPI 卡）
- **必填键（Gate 0）**：`tag`, `kpis`
- **完整字段**：
  ```json
  {
    "tag": "每日黄金深度研报 · 07:30 早报",
    "timestamp": "2026年11月24日（周二）07:30",
    "summary": "纽约 06:00 终盘与亚盘早段全景复盘",
    "accent": "#b45309",
    "footer_title": "每日黄金深度研报（07:30 早报）",
    "kpis": [
      {"label": "国内原料价 / 品牌金店", "val": "786 元/克", "sub": "银行条 806 元 · 品牌金店 1,091 元"}
    ]
  }
  ```
- **硬限制**：`kpis` 渲染前 6 项（2×3 网格）；每条 `sub` 严控 **≤17 个汉字当量**，防止 A4 折出单字孤行；`val` 中的圆点 Emoji（`⚪`/`🔴`/`🟡`/`🟢`/`🚨`）会被 `replace_dot_emojis()` 自动转为纯 CSS 矢量圆点。

### 1.2 `DAILY_VERDICT`（Layer 0 10 秒行动结论卡）
- **必填键（Gate 0）**：`level`, `headline`
- **完整字段**：
  ```json
  {
    "level": "L0",
    "badge": "⚪ L0 今日无操作 · 安心上班",
    "traffic_light": "🔴 红灯停（满足 1/4 关）",
    "headline": "隔夜金价冲高回落，今日继续空仓观望，切勿追买。",
    "bullets": ["要点一", "要点二", "要点三"],
    "risk_line": "若真实利息继续创 60 日新高，短线波动风险将显著放大。"
  }
  ```
- **配色规则**：`level` 仅取 `"L0"`（灰蓝 `#475569`）、`"L1"`（暖琥珀 `#b45309`）、`"L2"`（深红 `#b91c1c`），**严禁绿色**。

### 1.3 `DAILY_SIGNAL_NOISE`（30 秒信号 vs 噪音双栏过滤卡）
- **必填键（Gate 0）**：`signals`, `noises`
- **完整字段**：
  ```json
  {
    "title": "30 秒降噪过滤：今天什么是真信号，什么可以直接划走？",
    "signals": [{"head": "信号标题（0–2件）", "body": "白话解释对买金决策的实际影响"}],
    "noises": [{"head": "噪音标题（3–5件）", "body": "为何普通人今天不用管"}]
  }
  ```

### 1.4 `DAILY_PERSONA`（A / B / D / C 对号入座行动卡）
- **必填键（Gate 0）**：`cards`
- **完整字段**：
  ```json
  {
    "title": "对号入座：不管你现在是什么情况，今天到底该怎么办？",
    "cards": [
      {
        "group": "A",
        "heading": "空仓持币想等买点",
        "subtitle": "一句话情绪定位",
        "actions": ["具体动作 1", "具体动作 2"],
        "avoid": "切忌踩坑的一句话红线"
      }
    ]
  }
  ```
- **配色映射**：`"A"` 蓝 `#0284c7`、`"B"` 琥珀 `#b45309`、`"C"` 翠绿 `#059669`、`"D"` 靛蓝 `#4f46e5`。标题与首卡通过 `.persona-lead` 物理绑定，防止 PDF 分页悬孤。

### 1.5 `DAILY_GLOSSARY`（30 秒人话词典框）
- **必填键（Gate 0）**：`terms`
- **完整字段**：
  ```json
  {
    "title": "30 秒人话词典（本章涉及的金融词，看这一框就全懂）",
    "terms": [{"term": "词条名", "plain": "一句大白话解释 + 生活体感"}]
  }
  ```

### 1.6 `DAILY_LAYER_BADGE`（层级眉批）
- **必填键（Gate 0）**：`label`
- **完整字段**：
  ```json
  {"tone": "deep", "label": "深度精读区｜用 8 分钟讲透今天金价背后的真实推手"}
  ```
- **重要触发机制**：`tone` 取 `"deep"`（深度精读，蓝色）或 `"pro"`（进阶复核，灰蓝）。**当 `tone` 为 `"deep"` 时，同时作为 `lint_readability.py` 切分 Layer 0–1 与 Layer 2 的官方边界标记之一**（另三个匹配标题为 `^#\s*第二部分`、`^##\s*专题一`、`^##\s*周末专题`）。

### 1.7 `DAILY_TRUST_BAR`（文末 3 行质检徽章）
- **必填键（Gate 0）**：`items`
- **完整字段**：
  ```json
  {
    "title": "本刊透明质检徽章（严守事实核验，不遮掩细节修订）",
    "items": ["拦下 20 个全网流行谣言与深坑", "完成 12 次模型与风控升级", "公开 8 项细节校准（对核心建议影响 0 / 8）"],
    "note": "完整红队审计与一手数据库索引独立留档于 daily/AUDIT_LOG.md 与 daily/CHANGELOG.md。"
  }
  ```

### 1.8 `DAILY_CHART_TIMELINE`（图 1：走势折线矢量图）
- **必填键（Gate 0）**：`points`（嵌套必填：`points[].val` 与 `ref_lines[].val` 必须可解析为数字，且 `y_min < y_max`；`build_daily.py` V2.2 自动按纵轴跨度自适应整数/一位/两位小数，支持 `unit_prefix` 与 `unit_suffix`）
- **完整字段**：
  ```json
  {
    "title": "图 1：...",
    "subtitle": "...",
    "note": "数据来源与精确时点说明",
    "unit_prefix": "$",
    "unit_suffix": "",
    "y_min": 3580,
    "y_max": 3725,
    "y_ticks": [3600, 3630, 3660, 3690, 3720],
    "highlight_zones": [
      {"start_idx": 1, "end_idx": 2, "label": "关键冲击窗口", "fill": "#fffbeb", "text_color": "#92400e"}
    ],
    "ref_lines": [
      {"val": 3690, "label": "关键阻力 $3,690", "color": "#b91c1c", "align": "end", "x": 622, "dy": -6}
    ],
    "points": [
      {
        "time": "10:15",
        "val": 3681,
        "val_label": "$3,681",
        "desc": "亚盘高点",
        "color": "#c2410c",
        "label_pos": "above",
        "dx": 0,
        "dy": -3,
        "anchor": "middle",
        "highlight": true
      }
    ]
  }
  ```

### 1.9 `DAILY_CHART_CROSS`（图 2：1:1 真实线性跨资产分化条形图）
- **必填键（Gate 0）**：`items`（嵌套必填：`items[].pct` 必须为合法数字，支持 Unicode 负号 `−`）
- **完整字段**：
  ```json
  {
    "title": "图 2：...",
    "subtitle": "主要资产单日涨跌幅（%）｜ [中文惯例：红涨 / 绿跌 · 1:1 真实线性比例]",
    "note": "...",
    "linear_cap_pct": 10.0,
    "items": [
      {"label": "国际现货黄金", "pct": -0.28, "pct_label": "-0.28%", "tag": "($3,625)", "highlight": true},
      {"label": "中金黄金（A股）", "pct": -5.04, "pct_label": "-5.04%", "tag": "矿股补跌", "highlight": false}
    ],
    "reverse_items": [
      {"label": "日本 10 年期国债利率（越低越稳）", "detail": "节后骤降至 2.71%"}
    ]
  }
  ```
- **视觉规则**：优先读取显式 `"highlight": true/false`（缺省时自动排除「老铺/中金/紫金/山东/矿/股/金店」等非现货黄金标的，彻底防止股票误亮金底）；仅当存在超过 `linear_cap_pct` 的极值条时才画 `//` 断轴并在右上角显示 `· // 极值断轴`；`reverse_items` 过长时自动切换 2 行高卡片防碰撞。

### 1.10 `DAILY_CHART_SWITCH`（图 3：历史水位尺 + 四步红绿灯体检仪）
- **必填键（Gate 0）**：`gauges`（`pct` 须在 `0..100`）, `checks`（必须严格 4 项）
- **完整字段**：
  ```json
  {
    "title": "图 3：...",
    "subtitle": "买金四步红绿灯体检表与历史水位尺（单一真相刻度）",
    "note": "...",
    "status_line": "当前判定：红灯停（暂不新买 · 满足 1/4 项）",
    "status_color": "#dc2626",
    "gauges": [
      {"label": "20 年真实利息水位", "value_text": "2.79%（99% 高压区）", "pct": 99, "threshold_pct": 85, "color": "#b91c1c"}
    ],
    "checks": [
      {"name": "第 1 关：真实利息降下来", "passed": false, "line1": "午盘 2.79%", "line2": "需降到 2.72% 以下"}
    ]
  }
  ```
- **动态色彩与高度**：优先读取 `status_color`，否则按 **红灯 → 绿灯/满格 → 黄灯** 顺序匹配（防止「红灯停（距黄灯差3关）」被误判成琥珀点）；画布高度随 `gauges`/`checks` 数量自动伸展，零截断。

---

## 2. 主报告 7 张内置矢量图占位符与顺排编号（`build_report.py` V7.2）

主报告顶部必须含 `<!-- MASTER_BASELINE {"as_of_short": "YYYY-MM-DD HH:MM", "snapshot": "master_snapshot.json"} -->` 基线锁；`build_report.py` 按占位符在正文中实际出现顺序自动顺排为 **`图 1`–`图 7`**（`<!-- CHART_1_AND_2 -->` 计为 2 张图）：

| 出现顺位 | Markdown 占位符 | 渲染函数与图表内容 |
| :---: | :--- | :--- |
| **图 1** | `<!-- CHART_1 -->` | `svg_chart_real_vs_nominal`（1971–当前名义 vs 扣通胀真实购买力金价） |
| **图 2** | `<!-- CHART_2 -->` | `svg_chart_2026_bear_and_vacuum`（动态月线蜡烛图，支持 `monthly_candles` 跨年翻页） |
| **图 3** | `<!-- CHART_4 -->` | `svg_chart_48h_crash_and_weekend`（**冻结历史教学案例**：11/18–24 流动性冲击与高利息天花板，固定常量防未来快照篡改历史） |
| **图 4** | `<!-- CHART_5 -->` | `svg_chart_mechanical_clock_and_switch`（数据驱动跨年机械时钟 + 四步红绿灯） |
| **图 5** | `<!-- CHART_3 -->` | `svg_chart_china_tax_channels`（中国 2025 年 11 号公告下七大渠道每克成本与省钱对比，动态 300 元刻度） |
| **图 6** | `<!-- CHART_7 -->` | `svg_chart_fx_and_cross_ratios`（人民币升值汇兑账本 + 50 年跨资产比价尺，正负双端断轴保护） |
| **图 7** | `<!-- CHART_6 -->` | `svg_chart_institutional_targets`（数据驱动 12 大投行 2027 目标，分离 `*` 全样本注与 `†` 25.11 旧稿符） |

---

## 3. 双快照数据域（`data_snapshot.json` & `master_snapshot.json`）、跨项目 SSOT 与 Gate 5 算术契约

日报使用 `data_snapshot.json`，主报告使用独立锁定的 `master_snapshot.json`（两者结构同源，常规班次仅惰性读取 `master_snapshot.json` 核验 5 大触发条件，命中时方原子同步）。**跨项目单一权威源（SSOT）与同刊期顺序交接**：在 `07:30` / `18:00` BJT 一体化单会话定时任务（`daily-global-investment-research` / `daily-global-investment-research-evening`）中，第 3 步先由黄金模块出版并拥有 `data_snapshot.json`（现货金/COMEX/SHFE/SGE/铜/`DFII10`、`brent_settle_usd`、`cfets_cny_fixing`、`cfets_fixing_date`、`as_of_short`、`tier_code` 与 `new_buy_allowed`）的唯一写入权；第 4 步股研模块（`global-investment-research/equity`）只读校验同刊期黄金快照，镜像保留黄金的原始截点，严禁与黄金红绿灯指令冲突，最终于第 5 步统一 RSI 后单次发布站点。快照包含 9 大核心域及结构化图表配置数组：

1. **版本、紧迫度与 SSOT 裁决元信息**：`as_of_bjt`, `as_of_short`, `master_version`, `daily_alert_level` (`L0`/`L1`/`L2`), `daily_alert_label`, `tier_code` (`Tier 0`/`Tier 1`/`Tier 2`/`Tier 3`), **`new_buy_allowed` (bool，与 `tier_code != "Tier 0"` 强制一致)**, `tier_label`, `tier_status_sub`, `tier_cover_sub`, `tier1_passed`, `tier1_total`, `a_class_tranche_split` (`"30% + 45% + 25%"`), `tier1_gate4_threshold_usd`。
2. **四步红绿灯明细 (`tier1_gates`)**：严格长度 4 的数组，每项含 `name`, `passed` (bool), `reading`, `threshold`, `detail`。
3. **全球贵金属与内盘实盘**：`spot_gold_ny_close_usd`, `spot_gold_ny_close_rounded`, `spot_gold_ny_change_pct`, `spot_gold_intraday_high_usd`, `spot_gold_asia_open_usd`, `spot_gold_asia_high_usd`, `spot_gold_asia_low_usd`, `spot_gold_london_open_usd`, `spot_gold_prev_close_usd`, `spot_gold_fri_close_usd`, `spot_gold_fri_low_usd`, `spot_gold_fri_high_usd`, `spot_gold_2026_peak_usd`, `comex_front_settle_usd`, `comex_front_change_pct`, `comex_ny_late_usd`, `comex_gcz26_settle_usd`, `comex_gcz26_change_pct`, `spot_silver_usd`, `spot_silver_change_pct`, `spot_silver_live_usd`, `spot_platinum_usd`, `spot_platinum_live_usd`, `comex_copper_usd_lb`（官结）, `comex_copper_change_pct`, `comex_copper_live_usd_lb`, `comex_copper_live_change_pct`, `shfe_gold_night_rmb`, `shfe_gold_night_change_pct`, `shfe_gold_day_rmb`, `shfe_gold_day_change_pct`, `sge_am_fix_rmb`, `sge_pm_fix_rmb`, `sge_autd_night_rmb`, `sge_autd_night_change_pct`, `sge_autd_day_rmb`, `sge_autd_day_change_pct`, `sge_au9999_day_rmb`, `sge_same_ts_premium_rmb`, `sge_au9999_1530_premium_rmb`, `shfe_silver_night_rmb_kg`, `shfe_silver_night_change_pct`, `shfe_silver_day_rmb_kg`, `shfe_silver_day_change_pct`。
4. **利率、汇率与长期估值锚**：`usd_cny`, `usd_cny_short`, `cfets_cny_fixing`, `cfets_fixing_date`, `dxy`, `dxy_change_pct`, `dxy_london_1715`, `us2y_pct`, `us2y_te_pct`, `us10y_pct`, `us30y_pct`, `effr_pct`, `spread_2y_ff_bp`, `spread_2y_ff_range`, `dfii10_live_pct`, `dfii10_fred_official_pct`, `t10yie_fred_pct`, `dfii10_20d_peak_pct`, `dfii10_60d_peak_pct`, `dfii10_percentile_20y`, `dfii10_level_short`, `fair_value_usd`, `fair_value_rmb`, `cpi_u_index`, `cpi_1980_anchor_usd`, `gold_mcap_to_us_m2_pct`, `etf_2y_avg_cost_usd`, `sma_200w_low_usd`, `sma_200w_high_usd`, `sma_200w_q1_2027_usd`。
5. **能源、风险资产、金矿、ETF 与信用配管**：`brent_settle_usd`, `brent_change_pct`, `brent_live_usd`, `brent_london_1715_usd`, `wti_settle_usd`, `wti_change_pct`, `wti_live_usd`, `wti_london_1715_usd`, `ttf_gas_eur`, `vix_close`, `vix_change_pct`, `nvda_close_usd`, `nvda_change_pct`, `spx_close`, `spx_change_pct`, `ndx_close`, `ndx_change_pct`, `btc_usd`, `btc_change_pct`, `btc_london_1715_usd`, `gdx_close_usd`, `gdx_change_pct`, `gld_close_usd`, `gld_change_pct`, `gld_holdings_tonnes`, `gld_daily_flow_tonnes`, `gdx_gld_ratio`, `gdx_gld_change_pct`, `hy_oas_bp`, `ccc_oas_bp`, `coreweave_cds_bp`, `sofr_iorb_bp`, `on_rrp_usd_m`。
6. **四大央行、大行预测与盘后宏观**：`fed_dec_hike_prob`, `ecb_dec_hike_prob`, `boe_dec_hike_prob`, `boj_dec_hike_prob`, `bank_2027_yearend_median_usd`, `bank_2027_avg_median_usd`, `bank_2027_fx_median`, `germany_ifo_nov`, `ctf_fy27_h1_net_profit_yoy_pct`。
7. **中国零售渠道成本 (`rmb_channels`)**：`etf_base_rmb`, `bank_accum_rmb`, `bank_bar_rmb`, `bank_bar_plus_craft_rmb`, `shuibei_nonmember_bar_rmb`, `shuibei_taxed_jewelry_rmb`, `brand_store_rmb`, `wedding_save_per_g_rmb`, `wedding_save_50g_rmb`, `wedding_save_pct`, `note`。
8. **跨资产比值 (`cross_ratios`)**：**唯一标准无日期键名 `cross_ratios`**（严禁写遗留日期键 `cross_ratios_XXXX`，否则 Gate 5 报警）。
9. **结构化图表数组与三大信任资产**：`monthly_candles`（支持跨年翻页）、`mechanical_calendar`（4 格机械时钟）、`institutional_targets`（12 大行数组）、`trust_assets`（`myths_blocked`, `model_upgrades`, `minor_corrections`, `minor_impact_on_core_verdict`）。

### Gate 5 强制算术自洽公式（偏离即报 FAIL / WARN）
1. 现货涨跌幅：`|spot_gold_ny_change_pct - ((spot_gold_ny_close_usd / prev_close) - 1) * 100| <= 0.05`
2. 婚庆渠道省钱：`wedding_save_per_g_rmb == brand_store_rmb - bank_bar_plus_craft_rmb`、`wedding_save_50g_rmb == wedding_save_per_g_rmb * 50`、`|wedding_save_pct - (save / brand) * 100| <= 0.15`
3. 四步红绿灯、SSOT 开关与紧迫度：`len(tier1_gates) == 4`、`sum(passed) == tier1_passed`、`daily_alert_level in L0/L1/L2`、`a_class_tranche_split == "30% + 45% + 25%"`、若含 `new_buy_allowed` 须为布尔值且与 `tier_code != "Tier 0"` 严格一致
4. 跨资产比值精确容差：`gold_wti_ratio` / `gold_brent_ratio` / `gold_silver_ratio` `<= 0.15`；`gold_platinum_ratio <= 0.05`；**`gold_spx_ratio <= 0.015`**
5. 当期正文核对：当 `DAILY_META.timestamp` 或 `MASTER_BASELINE.as_of_short` 命中对应快照时，核验正文含 `spot_gold_ny_close_rounded`、`brand_store_rmb`、`wedding_save_per_g_rmb`

---

## 4. 四轨时段差异速查矩阵（由 `market_calendar.json` 驱动）

| 轨道 | 时段（`+08:00`） | 文件名 | 核心覆盖范围 | 3 图映射 |
| :--- | :--- | :--- | :--- | :--- |
| **工作日早报** | 周一至周五 `< 12:00` | `daily/YYYY-MM-DD_0730_早报_黄金深度研报.md` | 纽约 06:00 终盘（夏令时 05:00）、COMEX 02:30 官结（夏令时 01:30）、国内 02:30 沪金/延期夜盘、美欧股债油、联储/白宫动向、07:30 亚盘早段 | 图 1 隔夜折线 / 图 2 跨资产分化 / 图 3 水位尺+四步灯 |
| **工作日晚报** | 周一至周五 `>= 12:00`（定时 `18:00`） | `daily/YYYY-MM-DD_1800_晚报_黄金深度研报.md` | 上金所 15:30 终盘及日终清算表、上期所 15:00 收盘及龙虎榜、A/H 与金矿/金饰股收盘及盘后财报、16:30 人民币官收、16:00–18:00 伦敦盘与 17:00–18:00 欧洲数据（冬令时 18:30 伦敦定盘与晚间 A 股 ETF 净值未出则明标待出） | 图 1 日内亚欧分时 / 图 2 亚太与欧盘股汇金矿分化 / 图 3 水位尺+四步灯 |
| **周末专项版** | 周六 / 周日休市 | 沿用 `0730_早报` 或 `1800_晚报` 文件名，主标题加`（周末专项版）` | 休市市场明标「休市 · 沿用周五终盘」；聚焦 XAUT/PAXG 与 BTC、周五盘后 CFTC COT、菜百/水贝线下客流、周日中东股市（TASI/EGX30）与欧美周末政经访谈 | 图 1 本周 5 日复盘 / 图 2 全周累计分化 / 图 3 周末静态水位尺+下周门槛 |
| **工作日局部休市叠加** | 周一至周五遇中美欧英日港印单边假日（统一查询 `market_calendar.json`） | 沿用当日工作日文件名，文内明标休市市场与复盘时刻 | **A 类美盘休市/提前收**：沿用上一 NY 终盘，聚焦伦敦/内盘与薄量预警；**B 类中国休市**：聚焦外盘与离岸汇率；**C 类欧英日港印单边休市**：局部标注休市时段 | 同对应早/晚报 3 图结构，严禁编造休市盘口 |

*补充契约：同日同班次修订强制加 `_r2` 后缀防覆写；`build_daily.py` 编译最新日报时同步原子生成手机端单文件 HTML `daily/latest_gold.html`；无人值守定时任务全程禁止 `edit_file`，一律使用 `write_file` 全量落盘。*
