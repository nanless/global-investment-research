---
name: equity-report-publishing
description: >-
  Engineering runbook for compiling magazine-grade A-share, HK-stock, and US
  equity daily reports (07:30 morning / _0730_ & 18:00 evening / _1800_ CST,
  all-4-main unified main editions 5-6p & upgraded holiday_watch 1-4p since
  2026-11-26_1800, executed sequentially after Gold SSOT in unified sessions),
  pure-Python native ECMA-376 OOXML Word (.docx), responsive 3-market mobile
  HTML (daily/latest_{a_share,hk_stock,us_stock}.html), 16-32p flagship
  handbooks, 21 vector SVG charts (A1-A7, H1-H7, U1-U7), standalone
  lint_equity.py (Gates 0-6, Gate 3B & Cross-Project Gold SSOT Gates C1-C3
  with 6-hour freshness tolerance), 3-market holiday scheduling, and monthly
  rollovers. 适用于 A/港/美三市全时段主刊与旗舰编译、原生 OOXML Word、21 张矢量图、
  独立 Linter 与跨项目黄金门禁验收。
---

# Equity Report Magazine Publishing & PDF Build Runbook

工作区根目录 `<REPO_ROOT>/equity` 永久冻结不改名，在仓库顶层统一编排（`<REPO_ROOT>/AGENTS.md`）的每日 `07:30` / `18:00` 一体化单会话中作为 **Step 4** 紧接 Step 3 黄金落盘严检后串行运行（严禁并发跑 Chrome 无头编译）。全部写作规范、全时段完整主刊矩阵（`>= 2026-11-26_1800`）、7 维度大盘架构与周日 6 维龙头解剖见 `DAILY_REPORT_SPEC.md`，10 项内容门禁、双账户税费详表及 Step 5 受控 RSI 盲审协议见 `equity-research-editorial-qa` 技能。

---

## 1. 五步出版编译、门禁与站点发布流程

1. **编译前毫秒级秒检（`lint_equity.py --precheck --strict`）**：确认日报 `<!-- DAILY_META_JSON { ... } -->` 置于 `.md` 最末尾、JSON 合法（必填 `edition_id` 与 `edition_type`，可选 `data_caveats`，零原始 Emoji，零新旧键混写，港股仅用 `hkma_agg_bal_hkd_100m`，含 `H6` 时齐备 `h6.items` 与 `h6.sector_strip`），先跑独立秒检拦停禁词、说教口号、3 项已证伪税务/ETF/转债误导、Gate 3B（标题目标 ≤27/≤36 字、警告线 >32/>38 字；一句话结论目标 ≤50 字、警告线 >60 字；单段目标 ≤130 字、警告线 >180 字；列表项目标 ≤160 字、警告线 >210 字；粗体目标 ≤12%、警告线 >13.5%；10 点进度条总和 = 10；旗舰附表二行数 == `stock_pool_count`）、以及 Gate C1–C3（`brent_settle_usd` + 黄金快照 **6 小时**截点宽限 + 假日双轨 `brent_live_usd`/`vix_live` 空值口径 + 黄金红灯全载体锁），0 错 0 警后再编译：
   - `python3 <REPO_ROOT>/equity/lint_equity.py --precheck --strict`
2. **串行执行预授权编译命令（自动产出 PDF + 纯 Python 原生 ECMA-376 OOXML `.docx` + 三市手机 HTML；未改旗舰时仅跑 `build_daily.py`；严禁 `textutil`）**：
   - `python3 <REPO_ROOT>/equity/build_a_share_pdf.py`
   - `python3 <REPO_ROOT>/equity/build_hk_stock_pdf.py`
   - `python3 <REPO_ROOT>/equity/build_us_stock_pdf.py`
   - `python3 <REPO_ROOT>/equity/build_daily.py`
   - **Chrome 无头编译稳健性**：`pdf_common.py` 通过 `resolve_chrome_bin()` 优先支持 **`CHROME_BIN`** 环境变量（再回退 macOS Google Chrome 与 PATH 中 `google-chrome`/`chromium`/`chromium-browser`），并使用隔离临时用户目录执行 **最多 1 次自动重试**，防瞬时渲染抖动阻塞发刊。
3. **全量法证与跨项目门禁验收（`lint_equity.py --strict`）**：编译后执行 `python3 <REPO_ROOT>/equity/lint_equity.py --strict`，强制校验：
   - **Gate 0–5 & Gate 3B**：零内部工程/RSI 噪声（含 `master_snapshot.json`/`edition_run.py`/`edition_plan.py` 等全量拦截）、零跨市涨跌色系混用、零 3 项已证伪税务/ETF/转债误导、零说教口号、排版密度与警告线、10 点条守恒、附表二实际行数与 `stock_pool_count`（弹性 65–85 只/市，扩容基准 A 76 / 港 75 / 美 80，实时以 `state/market_state.json` 为准）100% 一致；
   - **Gate 6（PDF 页数/体积红线 + 原生 OOXML + 三市终端）**：
     - **PDF 页数与体积**：旗舰手册 **16–32 页**（≥50KB）；常规全时段主刊 `main` **目标 5–6 页、容忍 3–7 页**（`>= 2026-11-26_1800` 建议内嵌 ≥2 张矢量图，≥50KB）；休市/半日市守望刊 `holiday_watch`（及历史 `light`）**目标 2–3 页、容忍 1–4 页**（建议内嵌 ≥1 张矢量图，体积下限 **≥25KB**）；
     - **DOCX 与三市终端**：DOCX 7 核心 XML / `<w:tbl>` / 图数与 `docPr` 唯一性、三市 `_latest.{md,pdf,docx}` 原子同步、三市手机端 HTML（`viewport-fit=cover` + `nav-switch`）与 RSI 账本；
   - **Cross-Project Gates C1–C3**：直读 `../gold/data_snapshot.json` 校验 **`brent_settle_usd`**、`cfets_cny_fixing`（含日期）等全量共享宏观键及 **≤6 小时新鲜度与班次截点宽限**（假日/周末允许双轨 `brent_live_usd` 与 `vix_live` 同口径同时留空）；Gate C2 当 `tier_code == "Tier 0"` 或 `new_buy_allowed == false` 时，全载体扫描 Markdown、JSON、HTML 与渲染后 SVG 严禁买金指令与金矿股违规标绿；Gate C3 检查期铜 ≥3.5% 异动传导。必须退出码 `0`、0 错 0 警。
4. **产物核验与 PDF 视觉抽查**：确认 `daily/latest_{a_share,hk_stock,us_stock}.html`（顶栏 `A 股 ｜ 港股 ｜ 美股` 三市一键互切）与全部 PDF/DOCX 已刷新，用 `read_file` 抽检 PDF 确认零标签遮挡、零半页空白与零孤行尾页。
5. **Step 5 统一盲审、双轨复检与单次站点发布**：双轨完成编译与严检后，启动一名独立盲审子代理，按 `resolved` / `deferred_data` / `disclosed_caveat` 闭环记录 `review_closure`，按 Tier A/B 权限落盘（Tier B 含 `edition_plan.py`），Tier C 仅写提案。复跑双轨严格门禁后，运行 `python3 <REPO_ROOT>/scripts/edition_run.py advance <token> publish`，再用 `python3 <REPO_ROOT>/scripts/publish_site.py --edition-token <token>` 提交推送与验证附件。最后运行 `python3 <REPO_ROOT>/scripts/edition_run.py complete <token>` 核对同一提交、附件及 Pages 部署。无活动班次时，人可按根仓规则使用人工发布入口。

---

## 2. 渲染稳定性、图表精度与防漂移底线

- **macOS Chrome `SkPDF` 防崩与可读字号**：保留 `.md` 语义标识便于屏幕阅读（JSON 内免用原始 Emoji），编译阶段由 `pdf_common.py` 转为纯 CSS/矢量 Okabe-Ito 形状（零 `Apple Color Emoji sbix` 位图），禁 CJK `paint-order="stroke"` 与 SVG 文字旋转；21 张矢量图数据标签字号统一 `≥ 9.0`（A4 印刷 ≥ 7 pt）；正文不设强制大章换页，`≤ 5` 行短表自动整表防拆页。
- **关键图表精准布局**：`H6` 按 `h6.items` 全量动态渲染不截断并自动计算画布高度（必填 `h6.sector_strip`）；`U5` 按 `banks` 数量动态计算行高与画布高度；`U6` 单日涨跌幅采用**统一 1:1 线性刻度**定位零轴，彻底消除正负柱体比例扭曲。
- **三市手机端响应式体验**：`daily/latest_{a_share,hk_stock,us_stock}.html` 自动将本地 `file://` 链接转写为相对路径、移除窄屏表格强撑宽、以 `.svg-scroll` 保护图表可读字号、提供**顶栏三市互切**与导航锚点、支持交互式 3 秒勾选框与系统深色模式。
- **班次计划、状态规范键与历史快照隔离**：先用 `python3 equity/lint_equity.py --plan <edition_id>` 确定三市刊型、文件和复用市场。`state/market_state.json` 坚持无日期规范键（`margin_balance_100m` + `margin_balance_date`、`pboc_total_net_100m` + `pboc_op_date`、`hkma_agg_bal_hkd_100m`）与纯读者中文 `data_caveats` 数组；默认日刊编译按计划跳过复用市场，编译历史日报时独立加载当期 `DAILY_META_JSON`。例外结构见[权益日报规格](../../../equity/DAILY_REPORT_SPEC.md)。
- **内部留痕隔离**：编译修复、数据校对与归档移交清单统一写入 `state/audit_ledger.md`，RSI 自评与手册隔离写入 `state/RSI_PLAYBOOK.md` 与 `state/rsi_metrics.json`，绝不泄露至读者可见文件。

---

## 3. 配套参考文档与三市开箱模板

- 图表元数据与 **21 张矢量图（A1–A7 / H1–H7 / U1–U7）** 动静态契约：[references/chart_meta_schema.md](references/chart_meta_schema.md)
- 2026–2027 三市休市/半日市/冬夏令时表与跨月滚存 SOP：[references/holiday_and_rollover_sop.md](references/holiday_and_rollover_sop.md)
- 三市全时段完整主刊模板（周一至周五 07:30/18:00 三市全时段主刊 + 周六 07:30 美股主刊，目标 5–6 页、容忍 3–7 页、≥2 张矢量图）：[resources/daily_main_template.md](resources/daily_main_template.md)
- 局部休市与半日市升级版守望刊模板（`holiday_watch`，目标 2–3 页、容忍 1–4 页、建议 ≥1 张矢量图、PDF ≥25KB；向下兼容历史 `light`）：[resources/daily_light_or_holiday_template.md](resources/daily_light_or_holiday_template.md)
