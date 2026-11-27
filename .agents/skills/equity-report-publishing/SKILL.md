---
name: equity-report-publishing
description: >-
  Engineering runbook for pure-web publishing of A-share, HK-stock, and US
  equity daily reports (07:30 morning / _0730_ & 18:00 evening / _1800_ CST,
  all-4-main unified main editions & upgraded holiday_watch since
  2026-11-26_1800, embedding 12 MECE personal multi-asset channels with
  dedicated channel detail pages, expanded 140+ ETF matrix across 6 channels,
  and 231-stock zero-template 7-dimension deep dossiers, executed sequentially
  after Gold SSOT in unified sessions), flagship handbooks, 21 vector SVG
  charts (A1-A7, H1-H7, U1-U7), standalone lint_equity.py (Gates 0-5, Gate 3B
  SVG verification, extended multi-asset/ETF/dossier SSOT validation &
  Cross-Project Gold SSOT Gates C1-C3 with 6-hour freshness tolerance),
  3-market holiday scheduling, and monthly rollovers. 适用于 A/港/美三市全时段主刊与旗舰纯网页出版、12 大个人多元渠道独立详情页、140+ ETF 与 231 股 7 维深研数据验收、21 张矢量图、独立 Linter 与跨项目黄金门禁验收。
---

# Equity Report Web-Only Publishing Runbook

工作区根目录 `<REPO_ROOT>/equity` 永久冻结不改名，在仓库顶层统一编排（`<REPO_ROOT>/AGENTS.md`）的每日 `07:30` / `18:00` 一体化单会话中作为 **Step 4** 紧接 Step 3 黄金落盘严检后运行。本项目采用**纯网页静态门户直读唯一交付（不编译、不托管、不链接任何离线二进制文档附件）**：首页呈现 4 大核心市场红绿灯、小白「今日行动红绿灯 + 钱怎么分四笔」导览、全部 **12 大个人多元合规渠道简洁概览卡**（点击直达各自独立详情页 `channels/<id>.html`，外加横向「全市场打新工具箱」与「双层风控警示墙」）、**5 大市场/资产分组 ETF 概览卡（底层覆盖 6 大交易通道）**（跳转预筛选 `etfs.html`）、**《新手 3 分钟指南》（`guide.html`）** 与 **站内术语白话浮窗**。全部写作规范、全时段完整主刊矩阵、7 维度大盘架构、12 大渠道汇报制度与 7 维个股/ETF 深度标准见 `DAILY_REPORT_SPEC.md`，10 项内容门禁、双账户与 12 大多元渠道税费详表及 Step 5 受控 RSI 盲审协议见 `equity-research-editorial-qa` 技能。

---

## 1. 纯网页三步出版、门禁与站点发布流程

1. **落盘源稿、三大扩展 SSOT 数据库、月初滚存与增长型账本增量写入（防 300s 超时 + 强制同期 `edition_id` 锁）**：中小 Markdown 与轻量状态文件一律用 `write_file` 全量写盘（严禁 `edit_file`）——确认日报顶部导语块 ≤200 字（推荐 ≤160 字）、6 维逐项拆解禁写“其余均 0”、加粗密度 `5%–12%`（底线 `≥4.5%`）、零裸 `IOPV`、`<!-- DAILY_META_JSON { ... } -->` 置于 `.md` 最末尾且 JSON 合法（必填 `edition_id`/`edition_type`、`as_of_year_float` 按实日精确浮点计算、港股仅用 `hkma_agg_bal_hkd_100m`、`CHART_A2` 贴水 `ann_disc` 为正数且红涨 `#c2410c`/青跌 `#0f766e`、`H6` 齐备 `h6.items` 与 `h6.sector_strip`）；更新 `daily/INDEX.md`（仅纯网页/Markdown 链接）与 `SCORECARD.md`（仅登可证伪投资预判，勘误联动更新）；**持续增长的 `state/audit_ledger.md` 写 3 键 `_audit_patch.json` 走 `scripts/patch_state_dbs.py --prepend-equity-audit`；月初切换 `period_slug` 写紧凑 `_rollover_patch.json` 走 `--rollover-equity-month` 原子克隆三旗舰与 `_latest.md` 并同步 `report_meta_*.json`（杜绝 636 KB 超时）；三大扩展大 JSON（合计 ~830 KB）写嵌套 `_edition_patch.json` 调用 `--apply` 原子合并（只读查库用 `--inspect <target>`，支持 `channels`/`channel:<id>`/`etf:<code>`/`stock:<key>`/`stale-dossiers`/`ah-benchmarks`/`etf-freshness`）**，强制推进 `edition_id`、通过跨库费率一致性（`511380` 0.20% vs `511180` 0.30%）、兄弟字段扫清、A/H 孪生股同步与诚实单股 `updated_at`（全部登榜焦点股必须刷新，禁批量刷写未核查股票），增量刷新 12 大渠道、140+ 重点 ETF 与 231 股零模板化 7 维深研（驱动 `screener.html` 实时鲜度覆盖层与 7 维弹窗同步）；若单次修订旗舰手册，保证 `{market}_market_report_{slug}.md` 与 `_latest.md` 字节一致。
2. **全量纯网页法证与跨项目门禁验收（`lint_equity.py --strict`）**：执行 `python3 <REPO_ROOT>/equity/lint_equity.py --strict`，强制校验：
   - **Gate 0–5 & Gate 3B**：零内部工程/RSI 噪声、零跨市涨跌色系混用、零 3 项已证伪税务/ETF/转债误导、零居高临下说教口号、10 点条守恒、21 张矢量 SVG 图实时演练零重叠与 `CHART_A2` 期货贴水正负符号校验、附表二实际行数与 `stock_pool_count`（当前基准 A 76 / 港 75 / 美 80 = 231）及 `state/deep_dossiers.json` 覆盖率 100% 一致，并校验 `state/multi_asset_channels.json`（覆盖全部 12 大渠道）、`state/etf_universe.json`（140+ 重点 ETF 与跨库费率一致）、旗舰 `.md` 原子同步与 `INDEX.md` 零死链/零离线附件链接；
   - **Cross-Project Gates C1–C3**：直读 `../gold/data_snapshot.json` 校验共享宏观键、两轨截点位于所标班次 **`[-5 分钟, +6 小时]`** 单向窗口内且黄金早于或同分钟于权益（差值 ≤6 小时）；Gate C2 黄金红灯停期全载体（含三大扩展 JSON、Markdown 与渲染后 SVG）严禁买金指令与金矿/黄金 ETF 标绿；Gate C3 检查期铜 ≥3.5% 异动传导。必须退出码 `0`、0 错 0 警。
3. **Step 5 统一盲审（5 项真核验）、双轨复检与单次纯网页发布**：双轨源稿严检通过后启动独立盲审（第 4 维核验纯网页视觉清晰度、SVG 零碰撞与小白 3 分钟可读性，并执行 5 项真核验含焦点股 24h 公告扫雷、官源四铁律与 `screener.html` 卡片↔7 维弹窗一致），按 `resolved` / `deferred_data` / `disclosed_caveat` 闭环记录 `review_closure` 并经 `scripts/patch_state_dbs.py --append-equity-rsi` 无损追加至 `state/rsi_metrics.json`，复跑双轨严检后按令牌流程执行 `publish_site.py --edition-token <token>`（生成完整响应式门户并通过 S1–S6 严检后推送至 `origin/main`），再运行 `edition_run.py complete <token>` 验证 GitHub Pages 部署成功。若发布器构建或门禁报错，可调用预授权 `scripts/build_site.py --out _site`、`scripts/lint_site.py _site --strict` 与 `unittest` 定位修复后重试。

---

## 2. 纯网页渲染稳定性、21 张矢量图精度与防漂移底线

- **矢量清晰与色盲友好编码**：21 张矢量 SVG 图使用纯 CSS/矢量 Okabe-Ito 形状（零位图 Emoji），禁 CJK `paint-order="stroke"` 与 SVG 文字旋转；数据标签字号统一 `≥ 9.0`，桌面与手机双端均支持清晰缩放/横滑且零文字重叠。
- **关键图表精准布局**：`H6` 按 `h6.items` 全量动态渲染不截断并自动计算画布高度（必填 `h6.sector_strip`）；`U5` 动态行高；`U6` 统一 1:1 线性刻度。
- **排期与状态隔离**：先用 `lint_equity.py --plan <edition_id>` 确定三市刊型与复用市场；`state/market_state.json` 坚持无日期规范键与纯读者中文 `data_caveats` 数组；内部留痕隔离写入 `state/audit_ledger.md` 与 `state/RSI_*`。

---

## 3. 配套参考文档与三市开箱模板

- 图表元数据与 **21 张矢量图（A1–A7 / H1–H7 / U1–U7）** 动静态契约：[references/chart_meta_schema.md](references/chart_meta_schema.md)
- 2026–2027 三市休市/半日市/冬夏令时表与跨月滚存 SOP：[references/holiday_and_rollover_sop.md](references/holiday_and_rollover_sop.md)
- 三市全时段完整主刊模板（含小白三层结构、12 大渠道与重点 ETF 雷达 + 焦点股 7 维深研 + ≥2 张矢量图）：[resources/daily_main_template.md](resources/daily_main_template.md)
- 局部休市与半日市升级版守望刊模板（`holiday_watch`，建议 ≥1 张矢量图）：[resources/daily_light_or_holiday_template.md](resources/daily_light_or_holiday_template.md)
