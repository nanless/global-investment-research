# 图表元数据 Schema 与 21 张矢量 SVG 图动静态契约（A1–A7 / H1–H7 / U1–U7）

本参考文档定义 `report_meta_{a_share,hk_stock,us_stock}.json`（三份旗舰手册元数据）与日报文末 `<!-- DAILY_META_JSON { ... } -->`（自包含日报元数据）的统一字段契约。**本契约内所有键均与站内 21 张矢量 SVG 图表渲染模块及 `scripts/build_site.py` 1:1 实装接线，无幽灵键，零第三方依赖直接输出双端响应式网页。**

---

## 一、顶层字段契约（旗舰 JSON & 日报尾置 `DAILY_META_JSON` 通用）

| 字段名 | 适用范围 | 类型 | 填写规则与红线 |
| :--- | :--- | :--- | :--- |
| `edition_id` | **日报必填** | `string` | 班次期号，格式 `YYYY-MM-DD_{0730\|1130\|1800}` 或附加 `_rN`（如 `"2026-11-27_1130"`），须与日报文件名、`state/market_state.json`、三大扩展数据库、`state/policy_calendar.json` 及黄金共享快照完全一致。 |
| `edition_type` | **日报必填** | `string` | 场次刊型标识：自 `2026-11-26_1800` 起新刊使用 **`"main"`**（全时段完整主刊，必含 ≥2 张矢量 SVG 图）或 **`"holiday_watch"`**（休市/半日市升级守望刊，建议 ≥1 张矢量 SVG 图）；仅向下兼容 `2026-11-26_1800` 之前的历史 `"light"` 轻刊。 |
| `period_slug` | 旗舰必填 / 日报可选 | `string` | 月刊标识符，格式 `YYYY_MM`（如 `"2026_11"`）。与 `{market}_market_report_{slug}.md` 及 `{market}_market_report_latest.md` 原子同步，供静态门户直读渲染。 |
| `version` | 旗舰必填 | `string` | 刊期中文名（如 `"2026年11月刊"`），**严禁写内部工程版本号如 `V9.2`/`V10.0`**。 |
| `tag` | 必填 | `string` | 页面顶部细栏标签（市场 + 场次 + 精确公历北京时间）。 |
| `title` | 必填 | `string` | 页面结论型主标题（**写作目标：日报 ≤ 27 字 / 旗舰 ≤ 36 字；Gate 3B 门禁警告线：日报 > 32 字 / 旗舰 > 38 字**）。 |
| `benchmark_time` | 必填 | `string` | 数据截点说明。严格遵循冬令时（EST `+13h`）/ 夏令时（EDT `+12h`）；**美股 07:30 早刊严禁写 09:00/08:00 盘后终盘**。 |
| `methodology` | 必填 | `string` | 一句话阅读导引，平等温和、小白友好，零内部工程/RSI/红队词、零居高临下说教口号。 |
| `page_footer` | 必填 | `string` | 页面页脚栏刊名与日期/月刊。 |
| `footer_note` | 必填 | `string` | 页面底部合规与纪律提醒，纯读者中文（黄金红灯停期严禁出现买金措辞，统一写 `黄金红灯停新仓 0%`）。 |
| `kpis` | 必填 | `array[4]` | 固定 4 张首屏核心状态卡片，每项 `{ "label": string, "val": string, "sub": string }`；**JSON 字段内建议移除原始 Emoji（如 `🛡️`），使用纯中文如 `"红灯防守期"`**。 |
| `data_caveats` | 日报可选 | `array` | 当期数据透明披露清单（未到披露时点、暂用收盘、来源口径分歧或节假薄盘），每项 `{ "id", "market", "category", "severity", "item", "detail", "impact", "next_review" }`；**必须全部为纯读者中文、严禁含任何内部文件名或工程词**。 |
| `chart_live` | 必填 | `object` | 驱动全部 21 张矢量 SVG 图表的实时快照与覆写字典（见下文）；其中 `as_of_full` 须以 `YYYY-MM-DD HH:MM` 开头、落在所标班次 **`[-5 分钟, +6 小时]`** 单向窗口内，并与 `state/market_state.json` 时间戳一致。 |

> **尾置、唯一性与全载体黄金锁校验**：日报 `<!-- DAILY_META_JSON { ... } -->` 必须置于 `.md` **文件最末尾**，严禁同一图表混写平铺旧键与嵌套新键，须为严格标准 JSON。所有图表标题使用 `图 {{CHART_NUM}}：` 占位符由渲染引擎按正文顺序自动顺编。**凡正文嵌入的图表（除依赖平铺指数键的 `A1`/`A5` 外），必须在 `chart_live` 中提供对应的非空嵌套对象（如 `a2`/`a6`/`h2`/`h6`/`u3`/`u6`）。当黄金快照为 `Tier 0` 红灯或 `new_buy_allowed == false` 时，`lint_equity.py` Gate C2 与 `lint_site.py` Gate S6/S7 将连同 JSON 字段（`kpis`/`status_line2`/`a4.cards`/`h4.cards`/`u4.cards`/`u7.points`）、交互 K 线技术诊断条与渲染后网页/SVG 文本一并扫描拦停！**

---

## 二、`chart_live` 完整动态键契约（三市 1:1 实装）

### 1. A 股 `chart_live` 动态键（`report_meta_a_share.json` & A 股日报）

| 键名 | 类型 | 驱动图表 | 说明与示例 |
| :--- | :--- | :--- | :--- |
| `as_of_short` / `as_of_full` | `string` | `A1`, `A2`, `A4`, `A5`, `A6` | 短日期（如 `"11/26盘前"` / `"11/26官收"`）与完整北京时间标注（落在所标班次 `[-5 分钟, +6 小时]` 单向窗口内） |
| `as_of_year_float` | `number` | `A1` | 比例时间轴年份浮点坐标（`年 + 当年第几天/365`，如 `2026.905`，跨月必推进） |
| `csi300` / `sse` / `csi300_200w` / `sse_200w` | `number` | `A1`, `A5` | 沪深 300、上证指数及各自 200 周均线（4 年平均成本线） |
| `stock_pool_count` | `number` | `A7` & Gate 3B | 核心代表龙头池实时总数（**弹性 65–85 只**，扩容基准 **`76`**），须与 `state/market_state.json`、`state/deep_dossiers.json` 及旗舰附表二实际行数 100% 一致 |
| `score` / `tier_short` / `status_line1` / `status_line2` | `number` / `string` | `A4` | 体检分（`0–6`）、四灯纯中文名（**A4 自动拼接 `当前 {score} 分 · {tier_short}`，须仅填纯灯号如 `"红灯防守期"` 避免重复拼分**）与总开关下方两行诊断与纪律 |
| `a2` | `object` | `A2` | `{ "title", "sub", "indices": [[name, pct, hex], ...], "futures": [[name, ann_disc, headline, sub, col, bg], ...], "takeaway", "note" }`（**符号铁律：`ann_disc > 0` 代表折价/贴水，`ann_disc < 0` 代表升水**，贴水如「基差 -50.75」必须填正数年化贴水如 `20.5`，严禁填负号引发门禁拦截；`ann_disc` 为 `null` 时渲染灰卡；拆分结算待补核与席位待补核避免误标） |
| `a3` | `object` | `A3` | 中国宏观冷热 K 型六维动态覆写：`{ "title", "sub", "cold": [[label, val, desc], ...], "hot": [[label, val, desc], ...], "takeaway", "note" }`（向下兼容 `cold_items`/`hot_items`） |
| `a4` | `object` | `A4` | 未来窗口阶段卡覆写：`{ "title", "sub", "horizon", "cards": [{"header","color","bg","border","items":[...]}], "takeaway", "note" }`（须覆盖跨年至 3 月全国两会；**黄金红灯期卡片严禁写“补足/新买黄金”，统一写“黄金待亮黄灯后再分批转入”**） |
| `a6` | `object` | `A6` | 申万行业热力图覆写：`{ "title", "sub", "date_short", "sectors": [{"name","pct","flow","camp"}], "sectors_total_flow", "takeaway", "note" }`（须严格区分“全市场总额”与“展示行业小计”，避免算术打架；标题行业数与 `sectors` 长度相等） |
| `a7` | `object` | `A7` | 龙头四象限覆写：`{ "title", "sub", "points": [[name, svg_x, svg_y, shape, col, dx, dy, anchor], ...], "takeaway", "note" }`（**`svg_x ∈ [34, 834]`、`svg_y ∈ [34, 276]` 为像素坐标，禁填市盈率倍数！**） |

### 2. 港股 `chart_live` 动态键（`report_meta_hk_stock.json` & 港股日报）

| 键名 | 类型 | 驱动图表 | 说明与示例 |
| :--- | :--- | :--- | :--- |
| `as_of_short` / `as_of_full` / `as_of_year_float` | `string` / `number` | `H1`–`H6` | 短日期、完整北京时间标注（落在所标班次 `[-5 分钟, +6 小时]` 单向窗口内）与比例时间轴年份浮点坐标 |
| `hsi` / `hsi_200d` / `hstech` / `hstech_200d` | `number` | `H1`, `H5` | 恒生指数、恒指 200 日年线、恒生科技与恒科 200 日年线（偏离率按公式动态算，杜绝手工算错） |
| `hsahp` | `number` | `H6` | 恒生沪深港通 AH 股溢价指数 |
| `usd_hkd` | `number` | `H3` | 美元兑港元即期汇率（用于绘制 7.75–7.85 联汇标尺） |
| **`hkma_agg_bal_hkd_100m`** | `number` | `H3` | **香港金管局银行体系总结余，唯一规范键，显式单位：亿港元**。 |
| `hibor_1m_pct` / `sofr_pct` / `us10y_pct` | `number` | `H3`, `H5` | 1 个月港元拆息、美元隔夜担保融资利率与 10 年期美债收益率（须与全局状态 100% 对齐） |
| `stock_pool_count` | `number` | `H7` & Gate 3B | 港股代表龙头池实时总数（**弹性 65–85 只**，扩容基准 **`75`**），须与 `state/market_state.json`、`state/deep_dossiers.json` 及旗舰附表二实际行数 100% 一致 |
| `score` / `tier_short` / `status_line1` / `status_line2` | `number` / `string` | `H4` | 港股体检分（`0–6`，动态绑定 H4 底框颜色）、四灯纯中文名（**H4 显式提供 `status_line1` 时直接渲染该行，`tier_short` 统一填纯灯号如 `"红灯防守期"` 并在 `status_line1` 写明体检分**）与行动纪律 |
| `h1`–`h5`, `h7` | `object` | `H1`–`H5`, `H7` | 各图结构化覆写：`h1`（周期拐点）、`h2`（5 宽基 + 03:00 夜期盲窗警告卡与南向/沽空卡，夜期盲窗禁标亮绿）、`h3`（联汇与拆息）、`h4`（4 阶段卡片，每条 ≤18 字等宽）、`h5`（四情景整数 10 点条总和 = 10 + 投行目标）、`h7`（像素坐标四象限，同股 PE 必与 A 股满足物理学一致，禁列退市股 `00011`） |
| **`h6`** | `object` | `H6` | AH 溢价/倒挂路由 + 板块强弱覆写：`{ "title", "sub", "items": [[name, finite_pct, route_tag], ...], "sector_strip": string, "takeaway", "note" }`。**`h6.items`（非空数组，每行 `[名称, 有限百分比, 说明]`，按实际行数动态全量渲染、不截断，并自动计算 `svg_h`）与 `h6.sector_strip`（非空本期板块说明字符串）均为必填硬校验字段！** |

### 3. 美股 `chart_live` 动态键（`report_meta_us_stock.json` & 美股日报）

| 键名 | 类型 | 驱动图表 | 说明与示例 |
| :--- | :--- | :--- | :--- |
| `as_of_short` / `as_of_full` / `as_of_year_float` | `string` / `number` | `U1`–`U6` | 短标签、完整北京时间标注（落在所标班次 `[-5 分钟, +6 小时]` 单向窗口内；07:30 早刊禁写 09:00/08:00 盘后终盘）与年份浮点坐标 |
| `spx` / `spx_200d` / `spx_high` | `number` | `U1`, `U2`, `U5` | 标普 500 点位、200 日年线与阶段高点 |
| `us10y` / `us10y_zone` | `number` / `string` | `U4`, `U7` | 10 年期美债收益率（自动计算美债等效市盈率 `100/us10y` 并动态定位 U7 蓝虚线）与分区（`"low"` / `"mid"` / `"high"`，严格对应 `<4.5%`/`4.5%–4.85%`/`>4.85%`） |
| `stock_pool_count` | `number` | `U7` & Gate 3B | 美股代表龙头池实时总数（**弹性 65–85 只**，扩容基准 **`80`**），须与 `state/market_state.json`、`state/deep_dossiers.json` 及旗舰附表二实际行数 100% 一致 |
| `score` / `tier_short` / `status_line1` / `status_line2` | `number` / `string` | `U4` | 体检分、美股四灯纯中文名（**U4 B 行直接拼接 `总开关 · {tier_short}` 而不自动拼 `score`；为与三市模板统一口径，推荐统一填纯灯号 `"红灯防守期"` 并在 `status_line1` 写明精确体检分**）与两行行动纪律（口语配比加总必 = 100%） |
| `u1` / `u2` / `u3` | `object` | `U1`, `U2`, `U3` | 危机阶梯（`u1`）、风暴时间轴（`u2`，含动态 `zone_label` 防过时文案残留）、信用水面上下（`u3`） |
| `u4` | `object` | `U4` | 北京时间未来窗口阶段卡：`{ "title", "sub", "horizon", "cards": [{"header","color","bg","border","items":[...]}], "takeaway", "note" }`（**每条 bullet 去圆点后严控 ≤18 汉字等宽防右框溢字，且禁写裸 `10Y` 等缩写**） |
| **`u5`** | `object` | `U5` | 华尔街大行 2027 目标对比：`{ "title", "sub", "banks": [[name, target_int, hex], ...], "takeaway", "note" }`；**动态行高与画布高度（`svg_h = max(288, 68 + len(banks) * 24)`），全量渲染不截断并自动重算均值与涨跌空间 %**。 |
| **`u6`** | `object` | `U6` | 美股 11 大行业 ETF 热力图：`{ "title", "sub", "date_short", "sectors": [{"name","pct","dd"}], "takeaway", "note" }`；**左面板单日涨跌幅采用统一 1:1 线性刻度**（按正负总跨度统一线性定位零轴，彻底消除正负柱体比例扭曲），画布高度随行业行数动态计算。 |
| `u7` | `object` | `U7` | 美股龙头四象限覆写：`{ "title", "sub", "parity_pe", "points": [[name, svg_x, svg_y, shape, col, dx, dy, anchor], ...], "takeaway", "note" }`（**像素坐标 `x ∈ [34, 834]`、`y ∈ [34, 276]`；必须显式锁定全部代表点与评级色标，如黄金红灯期 `NEM` 须为观察区琥珀三角 `y` `#D97706`，严禁标绿**） |

---

## 三、21 张矢量 SVG 图动静态矩阵（A1–A7 / H1–H7 / U1–U7）

| 图表占位符 | 图表主题 | 动态驱动键 | 静态/脚本默认骨架与特性 | 建议嵌入场景（全时段主刊 ≥2 图 / 守望刊 ≥1 图） |
| :--- | :--- | :--- | :--- | :--- |
| `<!-- CHART_A1 -->` | A 股 2015 至今牛熊周期 + 4 年成本线 | `as_of_short`, `as_of_full`, `as_of_year_float`, `csi300`, `sse`, `csi300_200w`, `sse_200w` | 2015–2026 历史经典拐点比例轴 | A 股旗舰、关键变盘日早/午/晚主刊 |
| `<!-- CHART_A2 -->` | A 股宽基分化 + 中金所前 20 席位多空 | `a2.*`, `as_of_full` | 11 宽基比例缩放 + 4 品种卡片 | **A 股早/午/晚主刊主力图**、旗舰 |
| `<!-- CHART_A3 -->` | 中国宏观经济冷热 K 型六维账本 | `a3.*`, `as_of_full` | 6 冷 + 6 热双列对照（支持 JSON 全覆盖） | A 股旗舰、重磅宏观数据日主刊 |
| `<!-- CHART_A4 -->` | 跨年至两会排雷时钟 + 水温总开关 | `score`, `tier_short`, `status_line1/2`, `a4.*`, `as_of_full` | 4 阶段卡片（含黄金红灯门控）+ 3 色刻度 | **A 股 07:30 早刊 / 11:30 午刊 / 守望刊主力图**、旗舰 |
| `<!-- CHART_A5 -->` | 沪深 300 明年情景（10 点条）+ 跨资产回测 | `csi300`, `as_of_short`（动态重算空间 %） | 目标带 + 21 年配置回测（附红灯门控注） | A 股旗舰手册 |
| `<!-- CHART_A6 -->` | 申万行业涨跌 vs 主力资金净流向 | `a6.*`, `as_of_full` | 防守逆势吸金自动高亮 + 全市场/小计分注 | **A 股 11:30 午刊 / 18:00 晚刊主力图**、旗舰 |
| `<!-- CHART_A7 -->` | A 股代表龙头估值安全四象限 | `a7.*`, `stock_pool_count` | 4 象限底色与 Okabe-Ito 四形状图例 | A 股旗舰手册、周日专题 |
| `<!-- CHART_H1 -->` | 港股 2015 至今估值周期 + 恒指 200 日年线 | `hsi`, `hsi_200d`, `as_of_short`, `as_of_year_float`, `h1.*` | 2015–2026 恒指/恒科真实比例轴与公式年线差 | 港股旗舰手册 |
| `<!-- CHART_H2 -->` | 港股宽基分化 + 03:00 夜期盲窗 / 沽空南向卡 | `h2.*`, `as_of_full` | 5 宽基（无截断缩放）+ 盲窗警示卡（禁亮绿）+ 季检拆清卡 | **港股 07:30 / 11:30 / 18:00 主刊主力图**、旗舰 |
| `<!-- CHART_H3 -->` | 联系汇率 7.85 警戒线 × 金管局总结余 × 拆息利差 | `usd_hkd`, **`hkma_agg_bal_hkd_100m`**, `hibor_1m_pct`, `sofr_pct`, `us10y_pct`, `h3.*` | 7.75–7.85 联汇刻度尺 + 亿港元总结余柱 + 息差对照 | **港股 07:30 早刊 / 11:30 午刊（11:15 官方 HIBOR）主力图**、旗舰 |
| `<!-- CHART_H4 -->` | 未来 60 天港股政策与调仓日历 + 四灯开关 | `score`, `tier_short`, `status_line1/2`, `h4.*`, `as_of_full` | 4 阶段卡片 + 动态灯色 | **港股守望刊 / 大事件周主刊主力图**、旗舰 |
| `<!-- CHART_H5 -->` | 恒指 2027 情景（10 点条）+ 投行目标对比 | `hsi`, `as_of_short`, `h5.*` | 整数 10 点情景条（动态防溢框）+ 投行目标 | 港股旗舰手册 |
| `<!-- CHART_H6 -->` | 港股行业强弱分化 + AH 溢价/倒挂双账户路由 | `hsahp`, **`h6.items`**（动态全量不截断）, **`h6.sector_strip`**, `as_of_full` | 动态全量 AH 溢价/倒挂路由柱 + 底部板块强弱条 | **港股 11:30 午刊 / 18:00 晚刊主力图**、旗舰 |
| `<!-- CHART_H7 -->` | 港股代表龙头估值安全四象限地图 | `h7.*`, `stock_pool_count` | 4 象限底色 + 同口径 A/H 物理一致 PE + Okabe-Ito 四形状 | 港股旗舰手册、周日专题 |
| `<!-- CHART_U1 -->` | 40 年 7 次危机反弹 + 标普 6 档点位图 | `spx`, `spx_200d`, `spx_high`, `u1.*`, `as_of_full` | 1987–2022 历次危机跌幅与 1 年回报 | 美股旗舰、破位/突破主刊 |
| `<!-- CHART_U2 -->` | 本轮见顶回调与风险事件演进时间轴 | `spx`, `spx_200d`, `spx_high`, `u2.*`, `as_of_full` | 年线与痛点线框架 + 动态 `zone_label` | 美股旗舰手册 |
| `<!-- CHART_U3 -->` | 美股信用水面之上 vs 水面之下（债市警报） | `u3.*`, `as_of_full` | 银行体系安全垫 vs AI 债/私募信贷/币圈警报 | **美股 07:30 / 11:30 / 18:00 主刊主力图**、旗舰 |
| `<!-- CHART_U4 -->` | 未来 55 天北京时间排雷 + 10 年美债开关 | `us10y`, `us10y_zone`, `tier_short`, `status_line1/2`, `u4.*`, `as_of_full` | 4 阶段北京时间框（每条 ≤18 字）+ 3 区利率温度条 | **美股 11:30 / 18:00 / 周一前瞻 / 守望刊主力图**、旗舰 |
| `<!-- CHART_U5 -->` | 华尔街主流投行 2027 年标普目标对比 | `spx`, `as_of_short`, `u5.*`（**动态行高** + 自动重算均值与空间 %） | 按 `banks` 数量动态扩高 + 2027E 均值与全样本均值双虚线 | 美股旗舰手册、周一前瞻主刊 |
| `<!-- CHART_U6 -->` | 美股 11 大行业 ETF 单日涨跌 vs 52 周回撤 | `u6.*`, `as_of_full` | **统一 1:1 线性刻度**零轴 + 行业高亮 | **美股 07:30 / 11:30 / 18:00 主刊主力图**、旗舰 |
| `<!-- CHART_U7 -->` | 美股代表龙头四象限 + 动态美债等效线 | `us10y`, `u7.*`, `stock_pool_count` | 按 `parity_pe` 动态定位的蓝虚线 + 4 象限（锁定 `NEM` 观察三角） | 美股旗舰手册、周日专题 |

---

## 四、双端网页可读性与防漂移硬约束

1. **字号与字体**：`viewBox="0 0 850 ..."` 内数据标签 `font-size` 统一保持 **`9.0`–`12.5`**，显式声明 `font-family="PingFang SC, Hiragino Sans GB, sans-serif"`；绝不在图内输出裸 ASCII 记号或未译生僻卖方词，手机端支持清晰缩放/横滑不缩字。
2. **画家顺序与色彩伦理**：高亮背景矩形先于轴线与柱条绘制；红灯、预警、夜期盲窗或“待补核”灰卡严禁配绿徽章/绿柱（挂账统一 `#64748B` / `#F8FAFC`）；柱条采用无截断比例缩放（`U6` 强制统一 1:1 线性刻度，`H6` 动态全量不截断，`U5` 动态行高）；点位编码严格使用 Okabe-Ito 四形状（`g` 绿圆、`b` 蓝菱、`y` 琥珀三角、`r` 红圈叉）且与正文四色评级 100% 同步。
3. **跨快照防污染**：凡日报嵌入含阶段卡片或动态清单的图表（`A2/A4/A6/A7`、`H2/H3/H4/H6/H7`、`U2/U3/U4/U5/U6/U7`），必须在当期 `DAILY_META_JSON` 写齐嵌套覆写键（含 `h6.items` 与 `h6.sector_strip`），确保门户渲染历史快照零污染。
