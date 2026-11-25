---
name: equity-report-publishing
description: >-
  Engineering runbook for compiling magazine-grade A-share, HK-stock, and US
  equity daily reports (07:55 morning / _0730_ & 18:25 evening / _1800_ CST),
  pure-Python native ECMA-376 OOXML Word (.docx), responsive 3-market mobile
  HTML (daily/latest_{a_share,hk_stock,us_stock}.html), 16-24p flagship
  handbooks, 21 vector SVG charts (A1-A7, H1-H7, U1-U7), standalone
  lint_equity.py (Gates 0-6, Gate 3B & Cross-Project Gold SSOT Gates C1-C3),
  3-market holiday scheduling, and monthly rollovers. 适用于 A/港/美三市日报与
  旗舰编译、原生 OOXML Word、21 张矢量图、独立 Linter 与跨项目黄金门禁验收。
---

# Equity Report Magazine Publishing & PDF Build Runbook

工作区根目录 `<REPO_ROOT>/equity` 永久冻结不改名。全部写作规范、7 维度大盘架构与周日 6 维龙头解剖见 `DAILY_REPORT_SPEC.md`，10 项内容门禁、双账户税费详表及 Step 5 受控 RSI 盲审协议见 `equity-research-editorial-qa` 技能。

---

## 1. 五步出版编译、门禁与站点发布流程（唯一 6 个预授权核心脚本）

1. **编译前毫秒级秒检（`lint_equity.py --precheck --strict`）**：确认日报 `<!-- DAILY_META_JSON { ... } -->` 置于 `.md` 最末尾、JSON 合法且零新旧键混写，先跑独立秒检拦停禁词、Gate 3B（标题分级 ≤27/≤36 字、一句话结论 ≤50 字、段长/列表密墙、10 点进度条总和 = 10、旗舰 Appendix 行数 == `stock_pool_count`）、港股红利税/`520830`/QDII 误标、以及 Gate C1–C3（`brent_settle_usd` + 黄金快照 4 小时新鲜度 + 黄金红灯锁），0 错 0 警后再编译：
   - `python3 <REPO_ROOT>/equity/lint_equity.py --precheck --strict`
2. **串行执行预授权编译命令（自动产出 PDF + 纯 Python 原生 ECMA-376 OOXML `.docx` + 三市手机 HTML；未改旗舰时仅跑 `build_daily.py`；严禁 `textutil`）**：
   - `python3 <REPO_ROOT>/equity/build_a_share_pdf.py`
   - `python3 <REPO_ROOT>/equity/build_hk_stock_pdf.py`
   - `python3 <REPO_ROOT>/equity/build_us_stock_pdf.py`
   - `python3 <REPO_ROOT>/equity/build_daily.py`
3. **全量法证与跨项目门禁验收（`lint_equity.py --strict`）**：编译后执行 `python3 <REPO_ROOT>/equity/lint_equity.py --strict`，强制校验：
   - **Gate 0–5 & Gate 3B**：零工程/RSI 噪声、裸缩写清零、标题/结论/密墙/粗体占比/10 点条守恒/Appendix 实际行数与 `stock_pool_count` 一致；
   - **Gate 6（PDF 页数红线 + 原生 OOXML + 三市终端）**：PDF 页数须落入红线区间（**旗舰 16–24 页 / 主刊 4–5 页 / 轻刊 1–3 页**）、DOCX 7 核心 XML / `<w:tbl>` / 图数与 `docPr` 唯一性、三市 `_latest.{md,pdf,docx}` 原子同步、三市手机端 HTML 与 RSI 账本；
   - **Cross-Project Gates C1–C3**：直读 `../gold/data_snapshot.json` 校验 **`brent_settle_usd`**、`cfets_cny_fixing`（含日期）等全量共享宏观键及 **≤4 小时新鲜度**；Gate C2 当 `tier_code == "Tier 0"` 或 `new_buy_allowed == false` 时，全载体扫描 Markdown、JSON 与编译后 HTML/SVG 严禁买金指令与金矿股违规标绿；Gate C3 检查期铜 ≥3.5% 异动传导。必须退出码 `0`、0 错 0 警。
4. **产物核验与 PDF 视觉抽查**：确认 `daily/latest_{a_share,hk_stock,us_stock}.html`（顶栏 `A 股 ｜ 港股 ｜ 美股` 三市一键互切）与全部 PDF/DOCX 已刷新，用 `read_file` 抽检 PDF 确认零标签遮挡、零半页空白与零孤行尾页。Step 5 完成 RSI 更新后再跑一次 `lint_equity.py --strict` 确认终检全绿。
5. **门禁全绿后统一站点发布（`scripts/publish_site.py`）**：终检全绿后执行第 6 个预授权核心脚本 `python3 <REPO_ROOT>/scripts/publish_site.py`（带 `fcntl.flock` 防并发锁，自动构建双端响应式网页 `_site/`、过 `lint_site.py --strict`、限域提交并 SSH 推送至 GitHub Pages、按 SHA256 增量同步滚动 Release PDF/DOCX）。

---

## 2. 渲染稳定性与防漂移底线

- **macOS Chrome `SkPDF` 防崩与可读字号**：保留 `.md` 语义 Emoji 便于屏幕阅读，编译阶段由 `pdf_common.py` 转为纯 CSS/矢量 Okabe-Ito 形状（零 `Apple Color Emoji sbix` 位图），禁 CJK `paint-order="stroke"` 与 SVG 文字旋转；21 张矢量图数据标签字号统一 `≥ 9.0`（A4 印刷 ≥ 7 pt）；正文不设强制大章换页，`≤ 6` 行短表自动整表防拆页。
- **三市手机端响应式体验**：`daily/latest_{a_share,hk_stock,us_stock}.html` 自动将本地 `file://` 链接转写为相对路径、移除窄屏表格强撑宽、以 `.svg-scroll` 保护图表可读字号、提供**顶栏三市互切**与导航锚点、支持交互式 3 秒勾选框与系统深色模式。
- **原子产出与历史快照隔离**：所有编译输出至 `*.tmp.pdf`（`timeout=120`）校验后 `os.replace` 原子替换并在 `finally` 清理；`build_daily.py` 按 `(YYYY-MM-DD, HHMM, rev)` 确定性选片（免疫 `mtime` 漂移）；编译历史日报时严格独立加载当期 `DAILY_META_JSON`，不与最新旗舰 `report_meta_*.json` 混并防历史污染。
- **内部留痕隔离**：编译修复、数据校对与归档移交清单统一写入 `state/audit_ledger.md`，RSI 自评与手册隔离写入 `state/RSI_PLAYBOOK.md` 与 `state/rsi_metrics.json`，绝不泄露至读者可见文件。

---

## 3. 配套参考文档与三市开箱模板

- 图表元数据与 **21 张矢量图（A1–A7 / H1–H7 / U1–U7）** 动静态契约：[references/chart_meta_schema.md](references/chart_meta_schema.md)
- 2026–2027 三市休市/半日市/冬夏令时表与跨月滚存 SOP：[references/holiday_and_rollover_sop.md](references/holiday_and_rollover_sop.md)
- 三市日报主刊模板（A 股 18:00 晚刊 / 港股 18:00 晚刊 / 美股 07:30 早刊，4–5 页）：[resources/daily_main_template.md](resources/daily_main_template.md)
- 三市轻刊与局部休市守望模板（A 股 07:30 早刊 / 港股 07:30 早刊 / 美股 18:00 晚刊 / 休市，1–3 页）：[resources/daily_light_or_holiday_template.md](resources/daily_light_or_holiday_template.md)
