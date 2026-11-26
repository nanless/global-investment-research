---
name: equity-report-publishing
description: >-
  Engineering runbook for pure-web publishing of A-share, HK-stock, and US
  equity daily reports (07:30 morning / _0730_ & 18:00 evening / _1800_ CST,
  all-4-main unified main editions & upgraded holiday_watch since
  2026-11-26_1800, embedding 8 personal multi-asset channel radar rendered in
  full on the homepage, expanded 106-ETF matrix, and 7-dimension focus-stock
  analysis, executed sequentially after Gold SSOT in unified sessions),
  flagship handbooks, 21 vector SVG charts (A1-A7, H1-H7, U1-U7), standalone
  lint_equity.py (Gates 0-5, Gate 3B SVG verification, extended
  multi-asset/ETF/dossier SSOT validation & Cross-Project Gold SSOT Gates C1-C3
  with 6-hour freshness tolerance), 3-market holiday scheduling, and monthly
  rollovers. 适用于 A/港/美三市全时段主刊与旗舰纯网页出版（不生成 PDF/Word）、首页 8 大多元渠道与 7 维深研数据验收、21 张矢量图、独立 Linter 与跨项目黄金门禁验收。
---

# Equity Report Web-Only Publishing Runbook

工作区根目录 `<REPO_ROOT>/equity` 永久冻结不改名，在仓库顶层统一编排（`<REPO_ROOT>/AGENTS.md`）的每日 `07:30` / `18:00` 一体化单会话中作为 **Step 4** 紧接 Step 3 黄金落盘严检后运行。本项目采用**纯网页静态门户交付（不生成 PDF、Word 或 GitHub Releases 离线附件）**。全部写作规范、全时段完整主刊矩阵（`>= 2026-11-26_1800`）、7 维度大盘架构、**8 大个人多元渠道汇报制度（完整详列于网站首页与 `channels.html`）**与 **7 维个股/ETF 深度标准** 见 `DAILY_REPORT_SPEC.md`，10 项内容门禁、双账户与多元渠道税费详表及 Step 5 受控 RSI 盲审协议见 `equity-research-editorial-qa` 技能。

---

## 1. 纯网页三步出版、门禁与站点发布流程

1. **落盘源稿与三大扩展 SSOT 数据库**：确认日报 `<!-- DAILY_META_JSON { ... } -->` 置于 `.md` 最末尾、JSON 合法（必填 `edition_id` 与 `edition_type`，可选 `data_caveats`，零原始 Emoji，港股仅用 `hkma_agg_bal_hkd_100m`，含 `H6` 时齐备 `h6.items` 与 `h6.sector_strip`）；更新 `daily/INDEX.md`（仅保留纯网页/Markdown 链接，严禁 `.pdf`/`.docx` 链接）；同步刷新 `state/multi_asset_channels.json`（全部 8 大渠道最新全景，直出首页详列）、`state/etf_universe.json` 与 `state/deep_dossiers.json`；若修订旗舰手册，保证 `{market}_market_report_{slug}.md` 与 `{market}_market_report_latest.md` 字节一致。
2. **全量纯网页法证与跨项目门禁验收（`lint_equity.py --strict`）**：执行 `python3 <REPO_ROOT>/equity/lint_equity.py --strict`（**无需执行 PDF/Word 编译**），强制校验：
   - **Gate 0–5 & Gate 3B**：零内部工程/RSI 噪声、零跨市涨跌色系混用、零 3 项已证伪税务/ETF/转债误导、零说教口号、10 点条守恒、21 张矢量图实时演练零重叠、附表二实际行数与 `stock_pool_count`（当前基准 A 76 / 港 75 / 美 80 = 231）及 `state/deep_dossiers.json` 覆盖率 100% 一致，并校验 `state/multi_asset_channels.json`（覆盖全部 8 大渠道）与 `state/etf_universe.json`、旗舰 `.md` 原子同步与 `INDEX.md` 零死链/零 PDF/Word 链接；
   - **Cross-Project Gates C1–C3**：直读 `../gold/data_snapshot.json` 校验共享宏观键与 **≤6 小时**截点宽限；Gate C2 黄金红灯停期全载体（含三大扩展 JSON、Markdown 与渲染后 SVG）严禁买金指令与金矿/黄金 ETF 标绿；Gate C3 检查期铜 ≥3.5% 异动传导。必须退出码 `0`、0 错 0 警。
3. **Step 5 统一盲审、双轨复检与单次纯网页发布**：双轨源稿严检通过后启动独立盲审，按 `resolved` / `deferred_data` / `disclosed_caveat` 闭环记录 `review_closure`，复跑双轨严检后按令牌流程执行 `publish_site.py --edition-token <token>`（生成完整响应式网站——首页全渠道详览、`channels.html`、`etfs.html`、`screener.html` 7 维深研弹窗、`scorecard.html`、`archive.html` 及全部报告页——通过 S1–S6 严检后推送至 `origin/main`），再运行 `edition_run.py complete <token>` 验证 GitHub Pages 部署成功。

---

## 2. 渲染稳定性、图表精度与防漂移底线

- **macOS Chrome `SkPDF` 防崩与可读字号**：编译阶段由 `pdf_common.py` 转为纯 CSS/矢量 Okabe-Ito 形状（零 `Apple Color Emoji sbix` 位图），禁 CJK `paint-order="stroke"` 与 SVG 文字旋转；21 张矢量图数据标签字号统一 `≥ 9.0`；正文不设强制大章换页，`≤ 5` 行短表自动整表防拆页。
- **关键图表精准布局**：`H6` 按 `h6.items` 全量动态渲染不截断并自动计算画布高度（必填 `h6.sector_strip`）；`U5` 动态行高；`U6` 统一 1:1 线性刻度。
- **三市手机端响应式体验与历史快照隔离**：先用 `lint_equity.py --plan <edition_id>` 确定三市刊型与复用市场；`state/market_state.json` 坚持无日期规范键与纯读者中文 `data_caveats` 数组；默认日刊编译跳过复用市场；内部留痕隔离写入 `state/audit_ledger.md` 与 `state/RSI_*`。

---

## 3. 配套参考文档与三市开箱模板

- 图表元数据与 **21 张矢量图（A1–A7 / H1–H7 / U1–U7）** 动静态契约：[references/chart_meta_schema.md](references/chart_meta_schema.md)
- 2026–2027 三市休市/半日市/冬夏令时表与跨月滚存 SOP：[references/holiday_and_rollover_sop.md](references/holiday_and_rollover_sop.md)
- 三市全时段完整主刊模板（含个人多元渠道与重点 ETF 雷达 + 焦点股 7 维深研，目标 5–6 页、容忍 3–7 页、≥2 张矢量图）：[resources/daily_main_template.md](resources/daily_main_template.md)
- 局部休市与半日市升级版守望刊模板（`holiday_watch`，目标 2–3 页、容忍 1–4 页、建议 ≥1 张矢量图、PDF ≥25KB）：[resources/daily_light_or_holiday_template.md](resources/daily_light_or_holiday_template.md)
