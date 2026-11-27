---
name: equity-report-publishing
description: >-
  Engineering runbook for pure-web publishing of A-share, HK-stock, and US
  equity daily reports (07:30 morning / _0730_, 11:30 midday / _1130_, & 18:00
  evening / _1800_ CST, 4-track daily prose cap & upgraded holiday_watch,
  3-Layer Taxonomy: Layer 1 7-pill Macro Weather incl. CN-US 10Y spread & BTC
  read-only compliance firewall 银发〔2026〕42号, Layer 2 symmetric 3×2
  six-market cockpit [5 Core: A-share SSE #1, HK China offshore discount leg,
  US, rates_bonds_core, standalone Gold + 1 unified non_us_global_satellite],
  Layer 3 4-tier 12 MECE execution channels led by Channel 08 QDII 跨境基金…
  [10-yuan non-HNW friendly], expanded 181+ ETF matrix with orthogonal
  asset_class × region enums & asset_class=="gold" <=> gold_locked=True,
  231-stock zero-template 7-dimension deep dossiers, 27-pair A/H after-tax
  matrix, and 480+ interactive K-line shards [68 core benchmarks] via
  scripts/fetch_kline_data.py, executed sequentially after Gold SSOT in unified
  sessions), flagship handbooks, 21 vector SVG charts (A1-A7, H1-H7, U1-U7),
  standalone lint_equity.py (Gates 0-5, Gate 3B SVG verification, extended
  multi-asset/ETF/dossier SSOT validation & Cross-Project Gold SSOT Gates C1-C3
  with Gate C2 scanning market_state.json and 6-hour freshness tolerance),
  static-site lint_site.py (Gates S1-S7 incl. charts.html & K-line shards),
  3-market holiday scheduling, and monthly rollovers. 适用于
  A/港/美三市早午晚三班主刊与旗舰纯网页出版、三层信息架构（7 颗宏观天气胶囊 / 对称 3×2 六市场驾驶舱 / 4 角色层 12 大执行渠道）、480+ 交互 K 线终端（68 核心基准）、181+ 正交枚举 ETF 与 231 股 7 维深研数据验收、21 张矢量图、独立 Linter 与跨项目黄金门禁验收。
---

# Equity Report Web-Only Publishing Runbook

工作区根目录 `<REPO_ROOT>/equity` 永久冻结不改名，在仓库顶层统一编排（`<REPO_ROOT>/AGENTS.md`）的每日 **`07:30` 早报 / `11:30` 午报 / `18:00` 晚报** 一体化单会话中作为 **Step 4** 紧接 Step 3 黄金落盘严检后运行。本项目采用**纯网页静态门户直读唯一交付（不编译、不托管、不链接任何离线二进制文档附件）**，首页严格落地 **三层分类体系**：**Layer 1 首屏 3 秒危机熔断条 + 7 颗宏观天气胶囊**（含中美 10Y 利差 + 比特币只读风险晴雨表，严守 **`银发〔2026〕42号`** 合规防火墙）；**Layer 2 对称 `3×2` 六市场驾驶舱**（**5 大核心市场**：A 股【政策驱动型核心市场 · 上证 #1 领衔】· 港股【中国离岸折价腿，受 A 股政策基本面 + 美股流动性/政策双轨驱动卫星，非海外分散】· 美股【联储/财政/关税与地缘政策驱动】 · **债券/现金与中美利率 `rates_bonds_core`** · 独立黄金 + **1 个统一非美海外卫星 `non_us_global_satellite`**【日/欧/台韩/印】；正文日报仍严控四轨 `07:30/11:30/18:00` 封顶，实行 **首页 `#sec-policy-calendar` 精选 6–9 条（`home_featured: true`）+ 单市场页 `#sec-market-news` 无上限全量重要新闻雷达** 与 **4 列未来 7–14 天全北京时间财经/政策日历表**，且每刊必含 **1–2 张定制 `<!-- DAILY_VISUAL {...} -->` 零碰撞矢量信息图** 与自动首屏视觉体检驾驶舱/100% 堆叠概率条）、**财经与政策日历模块 `#sec-policy-calendar`**（由 `equity/state/policy_calendar.json` 14–30 天前瞻底座驱动）、交互 K 线切换区、小白 **「今日行动红绿灯 + 我的钱包一键试算器」**、**全站统一自选 `★`** 与 **27 对 A/H 税后比价矩阵**；**Layer 3 按 4 个角色层级组织的 12 大执行渠道概览卡**（Channel 08 以 `QDII 跨境基金…` 领衔、10 元起非高净值友好，直链独立详情页 `channels/<id>.html`）、**181+ 正交 `asset_class × region` 枚举 ETF 概览卡**（跳转预筛选 `etfs.html`）、**全屏交互 K 线终端（`charts.html`，覆盖 480+ 标的含 68 核心基准）**、**《新手 3 分钟指南》（`guide.html`）** 与 **站内术语白话浮窗**。全部写作规范、三班次主刊矩阵、7 维度大盘架构、12 大渠道汇报制度与 7 维个股/ETF 深度标准见 `DAILY_REPORT_SPEC.md`，10 项内容门禁、双账户与 12 大多元渠道（含 QDII 场内外分轨）税费详表及 Step 5 受控 RSI 盲审协议见 `equity-research-editorial-qa` 技能。

---

## 1. 纯网页三步出版、K 线抓取、门禁与站点发布流程

1. **落盘源稿、三大扩展 SSOT 数据库、政策日历、月初滚存与增长型账本增量写入（防 300s 超时 + 强制同期 `edition_id` 锁）**：中小 Markdown 与轻量状态文件一律用 `write_file` 全量写盘（严禁 `edit_file`）——确认多指数优先级排序（A 股上证指数 #1 领衔，同步 `market_state.json` 各市 `index_matrix`、`rates_bonds_core` 与 `non_us_global_satellite`）、每篇三市主刊实行**重要新闻全量覆盖**（取消旧 1–2 条上限：同步入库 `policy_calendar.json`，首页 `#sec-policy-calendar` 精选 6–9 条【`home_featured: true`】，单市场页 `#sec-market-news` 按 `affected_markets` 无上限全量呈现，配 **4 列未来 7–14 天全北京时间财经/政策日历表**，纯中文级别徽章、零裸 `P0`/`P1`、严守黄金红灯锁）与**视觉图表优先**（每刊嵌入 **1–2 张 `<!-- DAILY_VISUAL {...} -->`** 零碰撞矢量信息图，纳入 Gate 3B 几何校验）、日报顶部导语块 ≤200 字（推荐 ≤160 字）、6 维逐项拆解禁写“其余均 0”、加粗密度 `5%–12%`（底线 `≥4.5%`）、零裸 `IOPV`、`<!-- DAILY_META_JSON { ... } -->` 置于 `.md` 最末尾且 JSON 合法（必填 `edition_id`/`edition_type`、`as_of_year_float` 按实日精确浮点计算、港股仅用 `hkma_agg_bal_hkd_100m`、`CHART_A2` 贴水 `ann_disc` 为正数且红涨 `#c2410c`/青跌 `#0f766e`、`H6` 齐备 `h6.items` 与 `h6.sector_strip`）；更新 `daily/INDEX.md`（仅纯网页/Markdown 链接）与 `SCORECARD.md`（仅登可证伪投资预判，勘误联动更新）；**持续增长的 `state/audit_ledger.md` 写 3 键 `_audit_patch.json` 走 `scripts/patch_state_dbs.py --prepend-equity-audit`；月初切换 `period_slug` 写紧凑 `_rollover_patch.json` 走 `--rollover-equity-month` 原子克隆三旗舰与 `_latest.md` 并同步 `report_meta_*.json`（杜绝 636 KB 超时）；三大扩展大 JSON 与可选 `policy_calendar`（同步 `state/policy_calendar.json` 14–30 天前瞻日历）写嵌套 `_edition_patch.json` 调用 `--apply` 原子合并（只读查库用 `--inspect <target>` 含 `policy-calendar`）**，强制推进 `edition_id`、强制校验 **正交 `asset_class × region` 枚举与 `asset_class == "gold" <=> gold_locked=True` 双向锁**、跨库费率一致性（`511380` 0.20% vs `511180` 0.30%）、兄弟字段扫清、27 对 A/H 孪生股同步与诚实单股 `updated_at`（全部登榜焦点股必须刷新，禁批量刷写未核查股票），增量刷新 4 角色层 12 大执行渠道（Channel 08 以 `QDII 跨境基金…` 领衔）、**181+ 重点 ETF** 与 231 股零模板化 7 维深研；若单次修订旗舰手册，保证 `{market}_market_report_{slug}.md` 与 `_latest.md` 字节一致。
   - **本机伴随实时监测（独立于定时 56 项权限清单）**：`scripts/realtime_monitor.py` 与 `scripts/wechat_notify.py` 仅在本机按需或 `launchd` 运行，严格只读消费仓库 SSOT（含 `gold/data_snapshot.json`、`equity/state/market_state.json`、`equity/state/policy_calendar.json`）并继承黄金红灯锁，去重状态写入 `.git/realtime-monitor.sqlite3` 零仓库污染。
2. **全量纯网页法证与跨项目门禁验收（`lint_equity.py --strict`）**：执行 `python3 <REPO_ROOT>/equity/lint_equity.py --strict`，强制校验：
   - **Gate 0–5 & Gate 3B**：零内部工程/RSI 噪声（含 `fetch_kline_data.py`）、零跨市涨跌色系混用、零 3 项已证伪税务/ETF/转债误导、零居高临下说教口号、10 点条守恒、21 张矢量 SVG 图实时演练零重叠与 `CHART_A2` 期货贴水正负符号校验、附表二实际行数与 `stock_pool_count`（当前基准 A 76 / 港 75 / 美 80 = 231）及 `state/deep_dossiers.json` 覆盖率 100% 一致，并校验 `state/multi_asset_channels.json`（覆盖 4 角色层 12 大执行渠道）、`state/etf_universe.json`（**181+ 重点 ETF**、**正交 `asset_class × region` 枚举**、**`asset_class == "gold" <=> gold_locked=True`** 与跨库费率一致）、旗舰 `.md` 原子同步与 `INDEX.md` 零死链/零离线附件链接；
   - **Cross-Project Gates C1–C3**：直读 `../gold/data_snapshot.json` 校验共享宏观键、两轨截点位于所标班次（`0730`/`1130`/`1800`）**`[-5 分钟, +6 小时]`** 单向窗口内且黄金早于或同分钟于权益（差值 ≤6 小时）；**Gate C2 黄金红灯停期全载体同步扫描 `market_state.json`（含 `rates_bonds_core` 与 `non_us_global_satellite`）、三大扩展 JSON（强制 `asset_class == "gold" <=> gold_locked=True`）、Markdown 与渲染后 SVG**，严禁买金指令与金矿/黄金 ETF 标绿；Gate C3 检查期铜 ≥3.5% 异动传导。必须退出码 `0`、0 错 0 警。
3. **Step 5 统一盲审（5 项真核验）、全市场 K 线刷新与单次纯网页发布**：双轨源稿严检通过后启动独立盲审（第 4 维核验纯网页视觉清晰度、SVG 零碰撞与小白 3 分钟可读性，并执行 5 项真核验含焦点股 24h 公告扫雷、官源四铁律与 `screener.html` 卡片↔7 维弹窗一致），按 `resolved` / `deferred_data` / `disclosed_caveat` 闭环记录 `review_closure` 并经 `scripts/patch_state_dbs.py --append-equity-rsi` 无损追加至 `state/rsi_metrics.json`，复跑双轨严检后运行 **`python3 <REPO_ROOT>/scripts/fetch_kline_data.py --scope all`** 刷新全市场 **480+ 标的**（含 **68 只核心基准**：9 只非美海外指数、中债 2Y/10Y/30Y 收益率、中证 REITs `932047`/`932006`、港股 `HSCI`/`HSAHP` 与 `EURUSD`/`GBPUSD`/`USDHKD`）静态 K 线分片至 `equity/state/klines/*.json`（构建时自动复制至 `_site/assets/klines/*.json`），再按令牌流程执行 `publish_site.py --edition-token <token>`（生成完整响应式门户含 `charts.html` 并通过 **S1–S7** 严检后推送至 `origin/main`），最后运行 `edition_run.py complete <token>` 验证 GitHub Pages 部署成功。若发布器构建或门禁报错，可调用预授权 `scripts/build_site.py --out _site`、`scripts/lint_site.py _site --strict` 与 `unittest` 定位修复后重试。

---

## 2. 纯网页渲染稳定性、21 张矢量图、交互 K 线与防漂移底线

- **矢量清晰与色盲友好编码**：21 张矢量 SVG 图使用纯 CSS/矢量 Okabe-Ito 形状（零位图 Emoji），禁 CJK `paint-order="stroke"` 与 SVG 文字旋转；数据标签字号统一 `≥ 9.0`，桌面与手机双端均支持清晰缩放/横滑且零文字重叠。
- **交互 K 线引擎与 Gate S4/S5/S7 兼容**：`scripts/web_assets/kline.js` 采用双层 HiDPI `<canvas>` 渲染（杜绝空 `<svg></svg>` 占位触发 Gate S4），支持 `MA`/`BOLL`/`EMA`/`安全锚` 与 `VOL`/`MACD`/`RSI`/`KDJ`/`ATR`/`BIAS`，其 10 秒白话体检条零主动买进动词且严格服从黄金红灯锁；所有新增 CSS 类须在 `scripts/web_assets/app.css` 显式声明以过 Gate S5；`charts.html` 与 `_site/assets/klines/*.json` 均由 Gate S3/S7 联合验收零 NaN、零内部泄露、零红灯冲突。
- **关键图表精准布局**：`H6` 按 `h6.items` 全量动态渲染不截断并自动计算画布高度（必填 `h6.sector_strip`）；`U5` 动态行高；`U6` 统一 1:1 线性刻度。
- **排期与状态隔离**：先用 `lint_equity.py --plan <edition_id>` 确定三市刊型与复用市场（支持 `0730`/`1130`/`1800`）；`state/market_state.json` 坚持无日期规范键、多指数 `index_matrix` 与纯读者中文 `data_caveats` 数组；内部留痕隔离写入 `state/audit_ledger.md` 与 `state/RSI_*`。

---

## 3. 机构级深度验收、截点漂移防线与发前 4 项卫生清扫（对接总作战手册）

出版与落盘阶段（Step 4–5）须同步核验 [master-research-and-sources-playbook.md](../equity-research-editorial-qa/references/master-research-and-sources-playbook.md) 中的出版硬门槛，防止浅薄摘要或跨班次脏数据上线：
- **深度底线与移动端分块澄清**：单段/列表字数约束仅为移动端清晰阅读分块，严禁据此压缩成 7 段简报；A/港主刊须达 **`≥ 4,200–5,500` 字**（含首屏外 ≥2 个深度专题与完整 5 环政策传导链），美股主刊/守望刊 **`≥ 3,500–5,000` 字**（`holiday_watch` 须含 `≥ 60%` 全新增量、克隆前班 `≤ 35%`），核心数字正文复读 `≤ 3 次`，四情景 10 点条须分市场差异化且零反引号。
- **截点漂移防线（Cutoff Drift Guard）**：若距调研启动已超 **45 分钟**且期间有重大预定事件（`18:30` 定盘、`19:00` 财报电话会、`20:00–21:00` SOFR/美宏观、`12:00` 南向等）落地，先做定向增量补刷更新 `as_of` 与正文再送检，严禁发布过时“待公布”文案。
- **送检前 4 项卫生清扫**：在运行 `lint_equity.py --strict` 前完成 ① `next_review == 当班 edition_id` 到期挂账清零；② 4 点跨库联动（重算全部 27 对 A/H、刷新所有 `≥ 5%` 异动 ETF/个股并清除过时阻力位旧述、同步 5 只兄弟纳指 ETF 与 A/H 孪生股、同步 `qdii_channel_comparison`/`key_2026_rules`）；③ `18:00` 晚刊跨 4 JSON 与源稿清扫 `午收`/`11:30`/`12:00`/`10:30复牌` 午盘残迹；④ 在 `state/audit_ledger.md` 显式登记旗舰 5 条触发核查（尤须核验 200 日/200 周线突破与框架级政策落地）。

---

## 4. 配套参考文档与三市开箱模板

- **全球多资产 12 支柱投研因子、4 级权威信源、10+1 双语检索模板、班次核查单与深度硬底线总手册**：[../equity-research-editorial-qa/references/master-research-and-sources-playbook.md](../equity-research-editorial-qa/references/master-research-and-sources-playbook.md)
- 图表元数据与 **21 张矢量图（A1–A7 / H1–H7 / U1–U7）** 动静态契约：[references/chart_meta_schema.md](references/chart_meta_schema.md)
- 2026–2027 三市休市/半日市/冬夏令时表（含三班次 `0730`/`1130`/`1800` 判定）与跨月滚存 SOP：[references/holiday_and_rollover_sop.md](references/holiday_and_rollover_sop.md)
- 三市全时段完整主刊模板（含小白三层结构、多指数标准、12 大渠道与重点 ETF 雷达 + 焦点股 7 维深研 + ≥2 张矢量图）：[resources/daily_main_template.md](resources/daily_main_template.md)
- 局部休市与半日市升级版守望刊模板（`holiday_watch`，建议 ≥1 张矢量图）：[resources/daily_light_or_holiday_template.md](resources/daily_light_or_holiday_template.md)
