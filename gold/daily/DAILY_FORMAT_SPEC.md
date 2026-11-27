# 黄金研报体系《收敛主刊与全景主报告编写宪章》（永久规范）

> **永久铁律（纯网页收敛架构定版 · `CONVERGED_CUTOVER = 2026-11-26_1800`）**：面向普通家庭与进阶投资者，所有每日双刊（07:30 早报 / 18:00 晚报 / 周末专项版 / 工作日局部休市版）与跨世纪全景主报告均执行**「纯网页静态门户直读 · 同源异构 · 双快照防撕裂 · 小白友好三层递进 · 零内部泄露 · 640px 零碰撞矢量 SVG」**的唯一标准。*（历史旧刊 `< 2026-11-26_1800` 继续由质检器兼容校验。）*

---

## 一、六大呈现铁律（信息 · 论点 · 论据）

1. **三色静默紧迫度牌 + `.sn-grid` 信号/噪音双栏（先降噪，再给结论）**：
   - 日报首屏固定挂载紧迫度牌（**禁用绿色，防与绿灯可买撞色**；`L1` 在网页端渲染为**琥珀菱形** `.dot-diamond`，与买金红绿灯圆点物理区分）：
     * `⚪ L0 沉稳灰蓝`：今日无操作 · 安心上班（约 80% 交易日）
     * `🟡 L1 暖琥珀`：关键节点临近 · 提前看预案（约 15% 交易日；**仅提示预案，绝非买点信号**）
     * `🚨 L2 深红警示`：正式信号触发 · 按计划核对仓位（全年仅 3–6 次）
   - 紧接 **`.sn-grid` 信号（0–2 件）vs 噪音（3–5 件）双栏网格卡**（电脑端并排对照、手机端自动单栏堆叠），帮读者迅速清除市场噪音与传闻。
2. **小白友好三层递进 × 四层洋葱收敛结构**：
   - **三层阅读体验映射**：**① 30 秒红绿灯白话结论**（Layer 0） → **② 10 万/1 万元钱包实算与三步怎么买**（Layer 1） → **③ 机构级硬核证据、3 张矢量图与官方自查**（Layer 2–3）。
   - **Layer 0（首屏决策区）**：封面支持 **4 张高密度核心 KPI 卡**（`.kpi-strip.cols-4`，兼容 4–6 张）+ 静默牌 + 唯一买金红绿灯 + 1 句白话核心结论与底线风险（≤80 字，**0 感叹号、0 内部版本号、0 内部工程词/文件名**，优先报人民币元/克）。
   - **Layer 1（核心行动与钱包实算区）**：`.sn-grid` 信号/噪音双栏 + 买金四步红绿灯（满足 X/4 项）+ 历史水位尺 + **10 万元与 1 万元双刻度人民币钱包实算（6 周内锚定现行汇率，跨年显式标注汇率联动区间）+ A（空仓，统一 `30% + 45% + 25%` 配比与三步怎么买，严格落实 `008142` / `008143` 统一费率与 2026 销售费改口径）/ B（B1 轻仓套牢 · B2 重仓焦虑 · B3 早年浮盈）/ D（宏观原理）与 C（婚庆/实体省钱实算）紧凑操作卡**。
   - **Layer 2（精炼深度专题）**：**必须以 `# 第二部分` / `## 专题一` / `## 周末专题` 或 `DAILY_LAYER_BADGE`（`tone: "deep"`）起头以触发门禁分层**；每日 07:30 早报与 18:00 晚报均发布精炼收敛主刊，内嵌 3 张 640px 矢量图，聚焦核心驱动、关键情景与 7 日排雷；全景主报告保持百科深度并内嵌 7 张 640px 矢量图；**严格分工不互抄**；`DAILY_GLOSSARY`（「关键词白话速查」）为可选（0–1 次，亦可交由站内术语白话浮窗自动释义）。
   - **Layer 3（可选进阶复核区）**：顶部标明轻量眉批 `DAILY_LAYER_BADGE`（`tone: "pro"`），保留精确口径、Tier 0–3 阈值、高门槛工具（明标 50 万门槛）与免费官方数据自查路径；`DAILY_TRUST_BAR` 为可选（0–1 次）；版本演进 Diff、子代理核验与人名勘误**物理分离**至 `daily/AUDIT_LOG.md` 与 `daily/CHANGELOG.md`（支持按月归档至 `daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md`）。
   - **统一 5 模块收敛主刊映射**：**Layer 0 → ① 3 分钟速读结论与 4 卡摘要**；**Layer 1 信号/噪音与水位 → ② 隔夜/日内主线与跨市传导**；**Layer 2 专题与 3 图 → ③ 深度专题与矢量图**；**Layer 1 双刻度钱包账与 A/B/D/C 行动卡 → ④ 实操配置与风控边界**；**Layer 2 排雷日历 + Layer 3 → ⑤ 关键日历与官方数据溯源**。
3. **单一真相刻度（废除正文平行打分与部分过关误导）**：
   - 正文 Layer 0–1 彻底废除 `六灯 X.X/6`（含整数 `X/6` 及全角 `／6`）平行分制；全篇严禁出现「通过 0–3 关即可转黄/开新仓」等与四关全过原则冲突的错误表述（Gate 5 强制拦截），统一只用 **【历史水位尺】+【买金四步红绿灯（红灯停 Tier 0 / 黄灯试买 Tier 1 [30%] / 绿灯主买 Tier 2 [+45%→75%] / 满格配齐 Tier 3 [+25%→100%]，显示满足 X/4 项，四关全过方开新仓）】**。
4. **平等温和的白话语调与升级版三档词汇标准**：
   - 严格区分 **【客观事实】/【逻辑推论】/【概率与失效红线】**，绝不居高临下说教，鼓励平等温和的「3 分钟速读结论」「关键词白话速查」；
   - **第一档 · 自由使用（仅日常极高频词与代码）**：`ETF`、`VIX`（首现建议顺带附“恐慌指数”）、`GLD`/`GDX`（仅代码）、`鹰派`、`鸽派`、`提保`、`轧空`、`逼空`、`上影线`；
   - **第二档 · 首次出现必配简短白话括注（或交给站内术语白话浮窗，`DXY`/`COT`/`CDS` 移出裸用名单）**：`DXY`（美元指数）、`COT`（期货大资金持仓报告）、`CDS`（债务违约保险费率）、`CFTC`（美国期交委）、`DFII10`（10 年美债扣除通胀后的真实利率）、`2Y−FF`（2 年美债减政策利率利差）、`ON RRP`（联储隔夜逆回购余额）、`HY/CCC OAS`（高收益信用利差）、`IOPV`（盘中实时参考净值）、`bp`（基点，1% 的百分之一）；
   - **第三档 · 门禁硬拦（违者 FAIL）**：
     - **全篇（含 Layer 2/3 与全部组件，含 `DAILY_GLOSSARY`）严禁**：① 内部工程词、版本号与文件名（`V2.x/V5.x/V6.x/V7.x`、`Subagent`、`红队`、`法证`、`master_snapshot.json`、`data_snapshot.json`、`market_state.json`、`multi_asset_channels.json`、`etf_universe.json`、`deep_dossiers.json`、`market_calendar.json`、`_edition_patch.json`、`_ledger_patch.json`、`_rsi_patch.json`、`_audit_patch.json`、`_rollover_patch.json`、`_archive_patch.json`、`audit_ledger.md`、`RSI_PLAYBOOK(.md)`、`rsi_metrics.json`、`sidecar.json`、`permissions.json`、`DAILY_FORMAT_SPEC.md`、`AGENTS.md`、`SKILL.md` 及 `patch_state_dbs.py`/`svg_geometry.py` 等任意 `*.py` 脚本名）；② 6 个居高临下口号（`小白词典`、`直接抄`、`蠢事`、`1分钟定心丸`、`1 分钟定心丸`、`保命铁律`）；
     - **Layer 0–1 严禁**：生僻卖方量化词（`stop-through`、`IFRS 9`、`HQLA`、`FVOCI`、`ROTCE`、`Call Wall`/`Put Wall`、`负 Gamma`、`R²=`）、未消歧人名（`Daniel Ghali`/`Michael Hsueh`）、工程路数（`子代理`/`63 路`）、赌徒口语（`梭哈`、`做T`、`短线波段`、`高弹性`）、跨市涨跌色混用（`收红`/`收绿`/`翻红`/`翻绿`）及平行打分（`六灯`、`X/6`）；
   - **感叹号、煽动词、反重复读与排版密度红线**：Layer 0–1 感叹号严格 **0** 个（FAIL），收敛新刊全篇 **≤5** 个（旧刊 ≤2）；全篇禁用 **13 个夸张煽动词**（`神准`/`分毫不差`/`100%胜率`/`100% 胜率`/`无情推翻`/`核雷`/`拉爆`/`血洗`/`焊死`/`史诗级`/`史诗轧空`/`彻底打脸`/`惊天验证`）；Layer 0–1 自然段 ≤240 字、**Layer 2 正文自然段 ≤250 字（建议 ≤220 字以适配手机窄屏）**，开篇导语总长 **≤160 字**；全篇**加粗密度 ≤14%**；**裸数字/金额/百分比不套反引号**（仅代码可用）；**反重复读与零后台审计腔**：同一核心数字正文提及 **≤3 次**，标题与导语严禁出现「旧缺口清零」「挂账核销成绩单」等后台运维话术，正文严禁塞入冗余「挂账核销成绩单」表；导语所述的信号/噪音条数必须与 `DAILY_SIGNAL_NOISE` 数组长度精确一致（Gate 5 强制拦截）。
5. **少即是多 + 透明缺口 + 宏观官源口径与对称情景闭环**：
   - 关键数字配齐 **`[当前读数 + 历史水位 + 决策含义]`**；未披露或暂定数据统一记入快照 `data_caveats`（纯读者中文、零内部文件名）并在正文中如实标注；每刊须配齐 **1 句利率→汇率→信用→大宗→股票风险溢价（ERP）跨资产传导链**、**未来 48 小时上行/下行双向催化触发线**及**四情景完整概率拆分与理由**（合计精确 = 100%，严禁只甩偷懒单边概率）；**严守官源盘口一致性**：日本 CPI 直核 `stat.go.jp` 严分日央行版核心（剔生鲜与能源，权重 9162）与欧美版剔全部食品能源（权重 6959）；上期所夜盘严分 `02:30`（金银）/ `01:00`（有色）/ `23:00`（黑色化工），LME 涨跌幅严守同盘口（17:00 收对 17:00 收，禁混 12:30 场内价）；**严禁把不同时点的国内外报价差混作“国内供需溢价”，亦严禁把 05:00 盘后讲话因果倒置归因到 02:30 已收盘的国内价**。
   - **`SCORECARD.md` 投资预判纯粹性**：公开记分卡仅登记面向读者的可证伪价格/阈值/宏观投资预判，严禁混入后台数据回补工单（回补任务隔离至 `data_caveats` 与 `AUDIT_LOG.md`）。
6. **纯网页零碰撞矢量图表规范**：
   - 全部 SVG 画布采用 **`viewBox="0 0 640 ..."`**、主标签字号 **`≥10.2px`**（辅助刻度/徽章 `9.8–10.0px`）、全部文本经 `svg_esc()` 剔除位图 Emoji 与控制字符（保留矢量 `✓`/`✕`），手机端支持流畅横滑不缩字；
   - **图 1（`DAILY_CHART_TIMELINE`）** 采用 `vb_h=284` + 半透明白底胶囊标签 `_svg_label_pill()` 与 2D 碰撞面积最小化避让算法；**图 2（`DAILY_CHART_CROSS`）** 采用 1:1 真实线性比例 + 动态 `x_zero` + back-to-front 动态网格刻度（底纹 → 刻度 → 条形/文字 → 零轴）+ 中文惯例 `[红涨 / 绿跌]` + 精准主角高亮（显式 `"highlight": true/false`）+ 独立反向指标栏；所有页面经 `scripts/build_site.py` 直接输出纯网页静态站并通过 `scripts/lint_site.py --strict` 验收。

---

## 二、07:30 早报 / 18:00 晚报 / 周末专项版 / 工作日局部休市四轨矩阵

| 刊物类型 | 文件名规范（永不互相覆盖） | 唯一行情与事件锚点 | 3 张标准图表映射 |
| :--- | :--- | :--- | :--- |
| **工作日 07:30 早报** | `daily/YYYY-MM-DD_0730_早报_黄金深度研报.md` | 纽约 06:00 现货终盘（夏令时 05:00）、COMEX 02:30 官结（夏令时 01:30）、国内 02:30 沪金/延期夜盘、隔夜美欧股债油与美联储/白宫动向、07:30 亚盘早段 | **专题一**：图 1（隔夜走势折线）+ 图 2（跨资产线性分化）<br>**专题二**：图 3（历史水位尺 + 四步红绿灯） |
| **工作日 18:00 晚报** | `daily/YYYY-MM-DD_1800_晚报_黄金深度研报.md` | 上金所 15:30 终盘及日终清算表、上期所 15:00 收盘及龙虎榜持仓、A/H 股与金矿/金饰股收盘及盘后财报、16:30 在岸人民币官收（`usd_cny_1630`）、16:00–18:00 伦敦盘与 17:00–18:00 欧洲数据（冬令时 18:30 伦敦定盘与晚间 A 股 ETF 净值未出则明标待出） | **专题一**：图 1（日内亚欧分时折线）+ 图 2（亚太与欧盘股汇金矿分化）<br>**专题二**：图 3（历史水位尺 + 四步红绿灯） |
| **周末专项版（周六/周日）** | 仍严格沿用 `YYYY-MM-DD_0730_早报_黄金深度研报.md` 或 `1800_晚报`，主标题注明 **（周末专项版）** | 绝不编造休市盘口（休市市场明标“休市 · 沿用周五终盘”）；聚焦 7×24 链上黄金（XAUT/PAXG）与 BTC、周五盘后期货持仓周报、菜百/水贝周末线下客流、周日中东股市（沙特 TASI / 埃及 EGX30）与欧美周末政经访谈 | **周末专题一**：图 1（本周 5 日复盘折线）+ 图 2（全周跨资产累计涨跌）<br>**周末专题二**：图 3（周末静态水位尺 + 下周四步触发门槛） |
| **工作日局部休市叠加** | 沿用当日工作日 `0730_早报` / `1800_晚报` 文件名，文内醒目标注休市市场与恢复时刻 | 统一由外置日历 `market_calendar.json`（覆盖至 `2027-06-30`）驱动：**A 类（美盘休市/半日市提前收）** 沿用上一 NY 终盘聚焦伦敦/内盘与薄量预警，半日市（黑五 `11/27`、平安夜 `12/24`）支持 VIX `provisional_close`；**B 类（中国休市，如春节/清明/劳动节）** 内盘明标休市且自动放行金店价对齐预警，聚焦 COMEX/伦敦/离岸汇率；**C 类（欧英日港印单边休市）** 局部标注休市与复盘时间 | 同对应早/晚报 3 图结构，图中严禁伪造已休市市场当日新 K 线 |

*命名铁律：同日同班次若因突发事件或勘误需要重发，须启用 **`_r2` 防覆写锁**（如 `YYYY-MM-DD_0730_早报_黄金深度研报_r2.md`），绝不覆盖既有已发归档。*

---

## 三、10 个 `DAILY_*` 组件标准 JSON Schema 与结构化契约

所有组件须置于独立 HTML 注释中 `<!-- DIRECTIVE_NAME { ...合法 JSON... } -->`（拼写错误、缺必填键或坏 JSON 均触发 `lint_readability.py` 与静态站构建器强制报错）：

新刊与勘误版的 `DAILY_META` 必填 `edition_id` 和 `as_of_short`。刊号为 `YYYY-MM-DD_HHMM[_rN]`，与文件名和实时快照一致；数据截点为 `YYYY-MM-DD HH:MM`，与快照逐字相同。班次仅用 `0730` 或 `1800`，北京时间截点须落在所标班次 **`[-5 分钟, +6 小时]`** 单向窗口内（`MAX_EDITION_EARLY = 5min`、`MAX_EDITION_LAG = 6h`）。封面 `DAILY_META.timestamp`、快照 `as_of_bjt` 均须清楚显示同一截点（中文年月日或 ISO 日期均可）。休市栏继续注明上一可用报价的交易日或观测时间。

首刊使用截至观测日已核证的日历；修订刊可用晚于原截点、但不晚于实际验收当天的日历确认原班次盘时，交易证据仍按原截点计算。日历硬底线为班次后至少 **30 天**（`<60 天` 输出提示）、核证有效期 **90 天**。

1. **`DAILY_META`**：`{"edition_id": "YYYY-MM-DD_HHMM[_rN]", "as_of_short": "YYYY-MM-DD HH:MM", "tag": str, "timestamp": str, "summary": str, "accent": "#hex", "footer_title": str, "kpis": [{"label": str, "val": str, "sub": str} × 4–6]}`（收敛新刊推荐 **4 张**核心卡触发 `.kpi-strip.cols-4`，兼容 4–6 张；每条 `sub` 严控 ≤17 汉字当量；`footer_title` 严禁含 `V2.x/V5.x/V6.x/V7.x`）
2. **`DAILY_VERDICT`**：`{"level": "L0"|"L1"|"L2", "badge": str, "traffic_light": str, "tier_code": "Tier 0"|"Tier 1"|"Tier 2"|"Tier 3", "new_buy_allowed": bool, "tier1_passed": int, "headline": str, "bullets": [str × 3], "risk_line": str}`（`badge` 禁用 `🟢`；`tier_code`/`new_buy_allowed`/`tier1_passed` 须与快照逐项一致）
3. **`DAILY_SIGNAL_NOISE`**：`{"title": str, "signals": [{"head": str, "body": str}], "noises": [{"head": str, "body": str}]}`（`signals` 建议 0–2 件；渲染为 `.sn-grid` 双栏网格）
4. **`DAILY_PERSONA`**：`{"title": str, "cards": [{"group": "A"|"B"|"D"|"C", "heading": str, "subtitle": str, "actions": [str], "avoid": str}]}`
5. **`DAILY_GLOSSARY`**（收敛新刊可选 0–1 次，标题推荐「关键词白话速查」）：`{"title": str, "terms": [{"term": str, "plain": str}]}`
6. **`DAILY_LAYER_BADGE`**：`{"tone": "deep"|"pro", "label": str}`
7. **`DAILY_TRUST_BAR`**（收敛新刊可选 0–1 次）：`{"title": str, "items": [str × 3], "note": str}`（全篇严禁出现内部文件名或工程词）
8. **`DAILY_CHART_TIMELINE`**：`{"title": str, "subtitle": str, "note": str, "y_min": num, "y_max": num, "y_ticks"?: [num], "unit_prefix"?: str, "unit_suffix"?: str, "ref_lines": [{"val": num, "label": str, "color": str, "align": "start"|"end", "x"?: num, "dy": num}], "highlight_zones": [{"start_idx": int, "end_idx": int, "label": str, "fill": str, "text_color": str}], "points": [{"time": str, "val": num, "val_label": str, "desc": str, "color": str, "label_pos": "above"|"below", "dx"?: num, "dy"?: num, "anchor"?: str, "highlight"?: bool}]}`
9. **`DAILY_CHART_CROSS`**：`{"title": str, "subtitle": str, "note": str, "linear_cap_pct": num, "items": [{"label": str, "pct": num, "pct_label": str, "tag": str, "highlight"?: bool}], "reverse_items": [{"label": str, "detail": str}]}`（每条 `items[].label` 视觉宽严控 **≤8.5 汉字当量**，Gate 0 强制 `>9.5` 阻断 / `>9.0` 警告）
10. **`DAILY_CHART_SWITCH`**：`{"title": str, "subtitle": str, "note": str, "status_line": str, "status_color"?: "#hex", "gauges": [{"label": str, "value_text": str, "pct": num, "threshold_pct"?: num, "color": str}], "checks": [{"id": "real_yield"|"rate_spread"|"vix"|"ny_close", "name": str, "passed": bool, "line1": str, "line2": str} × 4]}`

封面红绿灯、裁决卡和图 3 均须同步显示一致的档位名称与 `X/4`；新刊的 `tier1_gates` 与 `DAILY_CHART_SWITCH.checks` 使用相同的固定 `id` 顺序。下列数值保留原始精度，正文可另外显示舍入后的读数：

| `id` | 结构化证据与过关条件（`edition_validation.py` 强制复算） |
| --- | --- |
| `real_yield` | 官方 `dfii10_fred_official_pct ≤ 2.72`。盘中估算另行标注。 |
| `rate_spread` | `(us2y_pct - effr_pct) × 100 ≤ 55` 基点。显示使用的 `spread_2y_ff_bp` 须和精确差值相差不超过 0.5 基点。 |
| `vix` | 使用截点前最近十个已核实的 **Cboe 现货指数**日收（存于 `vix_10d_session_closes` 10 条 `{"date", "close"}`）。过关条件为当前可用读数 `< 30` 或较十日收盘峰回落 `≥ 10%`。普通交易日遇 Cboe 官方 CSV 尚未批量更新当日行或暂不可取时**不阻塞发刊**：可在 `vix_daily_row_checks` 标 `provisional_close`（须在 **3 个自然日**内以官方 CSV 终值核销，次日班次在 6h 窗口内重查）或 `pending`（暂沿用最近十条官方行并披露缺口）。美国假日按日历 `daily_row_check_after_et` 核查：半日市（如黑五 `11/27`、平安夜 `12/24`，有 `windows_et`）亦支持 `provisional_close`；`pending` 复查间隔 **4 小时**；`no_row_confirmed` 支持 Cboe 官方域公告 `confirmation_source` 或官方 CSV 自证 `next_published_date > day`。仅可用与截点处在同一连续发布窗口、距截点 ≤30 分钟的盘中现货指数作为比较读数；休市或无合格盘口时 `vix_live` 与 `vix_live_as_of` 同时留空。 |
| `ny_close` | `spot_gold_ny_close_date` 是同口径已完成纽约 17:00 现货日线的交易日，`tier1_gate4_threshold_date` 是目标日之前有效交易日，`tier1_gate4_target_date` 是本次突破检验日。只有已完成日线的交易日等于目标日，且 `spot_gold_ny_close_usd > tier1_gate4_threshold_usd`（未舍入前高），才算通过。 |

快照核心新增与对称字段（详见[黄金快照契约](../../.agents/skills/gold-research-publishing/references/directives-and-snapshot-schema.md)）：
- **`etf_cn`**：国内黄金 ETF 标准无日期键（含 `as_of_date` 及 `518880`/`159937`/`518660` 的 `close`/`chg_pct`/`nav`/`flow_100m`）；
- **`data_caveats`**：面向读者的结构化缺口数组（纯读者中文、零内部文件名；每项含 `id`/`market`/`category` [`provisional_close`/`delayed_official`/`single_source`/`source_conflict`/`holiday_thin`/`publication_exception`]/`severity`/`item`/`detail`/`impact`/`next_review`）；国内节假日或 `data_caveats` 明示金店未开盘时 Gate 5 自动放行金店价对齐预警；
- **`usd_cny_1630`、`cfets_fixing_date`、`bank_2027_yearend_sample_count`、`bank_2027_avg_sample_count`** 与 `master_snapshot.json` 对称字段（`edition_id`/`new_buy_allowed`/`cfets_fixing_date`/`tier1_gates[].id`）。

图表数字字段与显示字段分开，由共享模块 `chart_input.py` 统一规范化：数字允许普通小数、合法千位格式（`"3,555"`）及百分值（`"+1.25%"`）；货币符号和完整文字放进 `val_label` 或对应标签。

---

## 四、一体化 10+1 红队核验、自动化安全与纯网页质检强制工作流

1. **严禁越权、编造、防卡壳与三层受控自进化边界（与仓库根规则 `../../AGENTS.md` 及 `../AGENTS.md` 严格对齐）**：所有外部实盘与新闻调研在每日 `07:30` / `18:00` 一体化班次中通过 **一体化 10+1（共享 10 路并行 + 1 路统一红队）** `research` 子代理完成（仅独立单跑黄金轨时回退 5+1）；主代理禁止运行未授权 `date`/`ls`/`curl` 等外部抓取命令；**无人值守定时任务全程严禁调用 `edit_file`：中小 Markdown 与快照一律用 `write_file` 全量写盘，持续增长的历史双账本（`daily/CHANGELOG.md` / `daily/AUDIT_LOG.md`）、跨月归档与 `daily/rsi_metrics.json` 分别写微型补丁 `_ledger_patch.json` / `_archive_patch.json` / `_rsi_patch.json` 并通过预授权 `scripts/patch_state_dbs.py --prepend-gold-ledgers` / `--archive-gold-ledgers` / `--append-gold-rsi` 无损增量写入（防 300s 超时）**；**正常发刊阶段（Step 1–4）严禁修改任何 `.py` 脚本与规则文件**；仅在双轨门禁全绿后的 **Step 5 统一 RSI 闭环**中允许对确凿确定性 Bug 执行受控 Tier B 最小补丁（单次 ≤1 处、≤40 行，只加固门禁或修 Bug、严禁删禁词或放宽误差，且改后必过 `--strict` + 静态站构建严检 + 单元测试，任一步失败立即回滚并转提案）。
2. **标准发刊闭环（Step 3 黄金 SSOT 优先，绝对路径裸命令，无 `cd &&` 前缀）**：
   1) 启动先读 `market_calendar.json` 查明休市叠加模式与北美冬/夏令时换算，并按**惰性主报告加载**仅读轻量级 `master_snapshot.json` 核验 5 大触发条件（命中时才全量读取主报告 MD）；随后用 `write_file` 全量更新日报数据源 `<REPO_ROOT>/gold/data_snapshot.json`（标准无日期键 `cross_ratios`、`etf_cn`、结构化 `data_caveats`、跨项目 SSOT 裁决字段 `tier_code`/`new_buy_allowed`、四关完整证据、`rmb_channels` 与 `trust_assets`，供 Step 4 权益轨零延迟只读校验）；仅当触发主报告 5 大更新条件时，同步更新 `master_snapshot.json`、`MASTER_BASELINE` 与主报告正文；
   2) 用 `write_file` 全量撰写本刊收敛主刊 Markdown 与公开记分卡 `daily/SCORECARD.md`（落实小白友好三层结构 + 3 张 640px 矢量图；同场修订加 `_r2` 防覆写；记分卡零内部工程/RSI 词汇、历史记录零篡改）；跨月归档上月历史双账本时先写 `_archive_patch.json` 运行预授权 `scripts/patch_state_dbs.py --archive-gold-ledgers` 无损归档至 `daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md`；再将【新增/更新/修正/删除】、`GOLD_EDITION_CHANGELOG`、`GOLD_EDITION_REVIEW` 与口径消歧写入微型补丁 `_ledger_patch.json` 并运行预授权 `scripts/patch_state_dbs.py --prepend-gold-ledgers` 无损头插至 `daily/CHANGELOG.md`（最新置顶）与 `daily/AUDIT_LOG.md`；
      - 新刊严检前，三个账本须同时登记本刊（`GOLD_EDITION_CHANGELOG` / `GOLD_EDITION_SCORECARD` / `GOLD_EDITION_REVIEW`）。`GOLD_EDITION_REVIEW` JSON 必填 `edition_id`、`as_of_short`、`note`、四关 HTTPS `sources` 与 `forecast_review`（`status` 仅允许 `settled` / `none_due` / `pending_evidence`，严禁 `"tracked"`），并由 `scripts/patch_state_dbs.py --prepend-gold-ledgers` 在无损头插前强制校验（支持跨月空锚回退）。记录格式见黄金技能的[快照与审阅台账契约](../../.agents/skills/gold-research-publishing/references/directives-and-snapshot-schema.md)。预测情景须事前划定互斥区间与未覆盖时的处理方式。来源仍未披露的结论留待验，按事先锁定的原口径结算。
   3) **强制运行纯网页 6 门禁严格验收（退出码必须为 `0`，0 errors、0 warnings）**：
      - `python3 <REPO_ROOT>/gold/lint_readability.py --strict <REPO_ROOT>/gold/daily/<本刊文件名>.md`
      - 若同步更新了主报告，一并传入 `<REPO_ROOT>/gold/黄金跨世纪周期与2026-2030终审研究报告.md`；
      - 一次性覆盖 **Gate 0–5**（组件 Schema、图 2 标签宽、三档词表、全篇内部词泄露、感叹号、加粗密度、裸数字反引号、部分过关话术、双快照算术与四关复算、`market_calendar.json`、`SCORECARD.md` 与 RSI 180/200 行校验），全绿后即交棒 Step 4 权益轨；
   4) **Step 5 统一 RSI 复盘与优化闭环**：一体化班次待 Step 4 三市权益与三大扩展库亦通过 `lint_equity.py --strict` 后，由 1 路独立只读盲审子代理联合按 6 维量表（满分 30，第 4 维聚焦**纯网页视觉清晰度、SVG 零碰撞与小白 3 分钟可读性**）复盘双轨本刊与回验上期预判，经 `_rsi_patch.json` + `scripts/patch_state_dbs.py --append-gold-rsi` 无损追加 `daily/rsi_metrics.json` 并更新 `daily/RSI_PLAYBOOK.md`（软限 ≤180 行 / 硬上限 200 行），按 Tier A/B/C 分级谨慎落地改进并复验 `--strict` 全绿；
   5) **双轨全绿后单次纯网页发布**：联合班次按根契约登记进入 `publish` 阶段，运行 `python3 <REPO_ROOT>/scripts/publish_site.py --edition-token <token>`（构建静态门户并通过 S1–S6 严检后推送），再用同一 token 执行 `edition_run.py complete <token>` 验证 GitHub Pages 部署成功后结束。本地预演单独运行 `publish_site.py --dry-run`，不附班次 token。
