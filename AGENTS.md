# Global Investment Research · Monorepo Orchestration Contract (`AGENTS.md`)

本文件是 `global-investment-research` 单仓库（Monorepo）的**顶层唯一编排宪章**，统一约束 **黄金深度研报（`gold/`）**、**全球三市权益与重点 ETF 研报（`equity/`：中国 A 股 × 中国香港股市 × 美国股市，覆盖 231 只全行业龙头 7 维机构级深研、181+ 只按 `asset_class` × `region` × 6 大通道正交标注重点 ETF 与 480+ 标的交互 K 线数据底座）** 以及 **中国大陆 12 大个人多元合规投资渠道（MECE 全覆盖 + 按 4 大执行角色分层 + 横向「全市场打新工具箱」与「双层风控警示墙」）** 在一体化**三班次定时任务（07:30 早报 · 11:30 午报 · 18:00 晚报）**下的协同调研、纯网页严检、跨轨门禁、受控 RSI 自我复盘与静态门户发布。

> **纯网页唯一交付原则**：本项目**仅发布纯网页静态门户（GitHub Pages）**，不编译、不托管、不链接任何离线二进制文档附件。门户首页（`index.html`）按三层架构呈现：**Layer 1 7 枚宏观气象与危机熔断邻近条**（含中美 10Y 利差与依据银发〔2026〕42号提示境内业务禁令、本项目配置为 0% 的 BTC 只读流动性温度计）、**Layer 2 对称 `3×2` 六大市场驾驶舱**（**5 大核心市场**：A 股【上证指数 #1 领衔 12 指数】、港股【中国离岸折价腿，非海外分散】、美股【8 指数 + 直达 QDII 入口】、**债券/现金与中美利率 `rates_bonds_core`**、黄金【独立货币避险】 + **1 个统一非美全球卫星 `non_us_global_satellite`**【日本 #1 `513800`、欧洲 #2 `159561`、台湾/韩国 AI 景气晴雨表、印度场外观察清单及 `164824` LOF 拟议退市风险提示 + 直达 QDII 入口】；每日 `07:30 / 11:30 / 18:00` 保持 **4 条完整日报正文主轨**不变）、小白 **「今日行动红绿灯 + 我的钱包一键试算器」** 交互导览、**Layer 3 6 市场交互 K 线切换区（480+ 标的）**、**全站统一自选清单 `★`**、**27 对 A/H 税后股息交互比价矩阵**、**按 4 大执行角色分层的全部 12 大个人多元合规投资渠道概览卡**（点击直达独立详情页 `channels/<id>.html`，渠道 08 显式定名「QDII 跨境基金（场内溢价·直销与支付宝限购）、香港互认与理财通」，10 元起普惠渠道而非高净值专属）、**181+ 只正交标注（`asset_class` × `region` × 6 通道）ETF 概览卡**（跳转预筛选 `etfs.html`）、**全屏交互 K 线终端（`charts.html`）**、**《新手 3 分钟指南》（`guide.html`）** 与 **站内术语白话浮窗**。
>
> **实时数值唯一真相源原则（SSOT）**：所有宪法、规则与技能文档只锁定制度口径、风控红线与计算方法，**严禁硬编码随时变动的实盘利率、收益率、限购金额、溢价率、规模、点位或比例数字**；一切实时数值以 **`gold/data_snapshot.json`** 与 **`equity/state/*.json`** 为唯一真相源。

---

## 1. Monorepo 目录结构与职责边界

```text
global-investment-research/
├── AGENTS.md                        # 本文件：单仓库顶层编排宪章与跨轨硬约束
├── README.md                        # 仓库总览、纯网页三班次 10+1 节拍、交互 K 线终端与本地构建说明
├── .agents/skills/                  # 全仓库统一工作区三 Skill（黄金出版 + 权益出版 + 权益编辑审校）
├── automations/                     # 共用提示词、56 项精确权限清单、三个定时模板（07:30/11:30/18:00，Tier C 只读）与微信推送配置样例 notify.example.json
├── gold/                            # 黄金深度研报体系（跨轨 SSOT 唯一写入源）
│   ├── AGENTS.md                    # 黄金子轨永久规则
│   ├── data_snapshot.json           # 日报实时数据源、多指数锚点、跨项目红绿灯裁决 SSOT 与 data_caveats 披露源
│   ├── master_snapshot.json         # 1971–2030 全景主报告独立锁定基线
│   ├── market_calendar.json         # 60+ 天全球跨市场休市与冬/夏令时日历
│   ├── edition_validation.py / chart_input.py / lint_readability.py（及站内 640px SVG 矢量图表模块）
│   └── daily/                       # 早/午/晚日报、SCORECARD、CHANGELOG、AUDIT_LOG、archive/ 按月归档与 RSI 台账
├── equity/                          # 全球三市权益、181+ 正交标注 ETF 雷达与 12 大多元渠道研报体系
│   ├── GEMINI.md                    # 权益子轨永久宪法
│   ├── DAILY_REPORT_SPEC.md         # 7 维大盘、多指数优先级、7 维个股/ETF 深研、12 大多元渠道与全主刊唯一详规
│   ├── state/                       # market_state.json、multi_asset_channels.json、etf_universe.json、deep_dossiers.json、policy_calendar.json、klines/*.json、audit_ledger.md、RSI 台账
│   ├── edition_plan.py / lint_equity.py（及 21 张矢量 SVG 图表与网页渲染模块）
│   └── daily/                       # 三市早/午/晚日报、总看板 INDEX、SCORECARD、CHANGELOG
├── scripts/                         # 零依赖静态门户构建、交互 K 线抓取、严格门禁、纯网页发布、本地定时安装与伴随实时监测引擎
│   ├── fetch_kline_data.py          # 零第三方依赖全市场 480+ 标的静态分片 K 线抓取引擎（写入 equity/state/klines/*.json）
│   ├── build_site.py                # 零第三方依赖生成双端响应式门户（首页驾驶舱/#sec-policy-calendar/charts.html/12 独立渠道页/ETF 雷达/231 股 7 维/27 对 AH 矩阵/钱包试算/新手指南/记分卡/档案）
│   ├── svg_geometry.py              # SVG 矢量文本边界框解析与零碰撞/零越界几何校验引擎
│   ├── visual_widgets.py            # 零依赖声明式 DAILY_VISUAL 640px 矢量信息图引擎（waterfall / bar_compare / anchor_range / flow_chain）
│   ├── patch_state_dbs.py           # 权益三库与 policy_calendar.json 原子合并、双账本/审计无损头插、双轨 RSI 无损追加、月初原子滚存/归档与 --inspect <target> 查库工具（防 300s 超时）
│   ├── lint_site.py                 # 7 道法证与安全门禁（S1–S7，--strict 零容忍，含 K 线分片与黄金红灯锁验收，禁用离线附件链接）
│   ├── publish_site.py              # 源稿严检 -> 静态站构建严检 -> 限域提交推送（GitHub Pages 自动部署）
│   ├── install_sidecars.py          # 将 3 份脱敏定时模板（07:30/11:30/18:00）渲染/原子安装至本机并做漂移校验
│   ├── edition_run.py               # 三个班次共用的运行记录、阶段锁、僵尸锁安全清理与 Pages 验收
│   ├── realtime_monitor.py          # 伴随本机实时行情/政策/时政监测守护引擎（只读消费 SSOT，去重状态写入 .git/realtime-monitor.sqlite3 零仓库污染）
│   ├── wechat_notify.py             # 合规微信推送分发器（WxPusher/企业微信机器人/PushPlus/Server酱，零个人号 Hook 风险，密钥外置 ~/.config）
│   └── web_assets/                  # 站点样式与零依赖交互脚本（app.js + kline.js 双层 HiDPI Canvas K 线、技术指标、钱包试算、自选清单与术语浮窗）
├── tests/                           # 零依赖全链路回归测试集
└── .github/workflows/
    └── deploy-pages.yml             # PR 与 main 分支全量回归测试、模板干跑、源稿预检与静态站构建；仅 main 自动部署 Pages
```

---

## 2. 中国大陆 12 大个人多元合规渠道 MECE 目录与数据底座

门户首页按 **4 大执行角色分层** 以简洁概览卡呈现全部 **12 大个人多元合规投资渠道**（统一红/黄/绿灯 + 小白一句话 + 今日避坑提醒），点击卡片直达各自独立详情页 `channels/<id>.html`（`channels.html` 提供全渠道总览），另配横向 **「全市场打新工具箱」** 与 **「双层风控警示墙」**。12 大渠道标准 ID 与边界永久统一为：

| 序号 | 渠道名称 | 标准 `id` | 核心覆盖范围 |
| :---: | :--- | :--- | :--- |
| 1 | 活钱与现金管理 | `reverse_repo` | 国债逆回购（`GC001`/`R-001`）、货币基金、现金管理类理财、同业存单 AAA 指数 |
| 2 | 人民币银行存款全家桶 | `large_cds` | 定期存款、大额存单（含二手转让与禁止二次转让规则）、结构性存款、50 万元存保红线 |
| 3 | 境内个人外币存款与外币理财 | `fx_deposits_wm` | 境内美元/港元等外币定存、外币理财、锁汇/汇兑损益测算与 5 万美元便利化额度边界 |
| 4 | 债券与债券 ETF | `bonds` | 储蓄国债、超长期特别国债、银行间短融 ETF（`511360`）、政金债/国债/交易所公司债与科创债 ETF |
| 5 | 公募基金、银行理财与基金投顾 | `funds_wm` | 真净值银行理财、短债/纯债、固收+、多资产 ETF-FOF、持牌基金投顾与 2026 公募销售费改 |
| 6 | 储蓄型商业保险 | `savings_insurance` | 增额终身寿险、养老年金、分红险（预定利率、实现率、退保现价与真实 IRR 透明测算） |
| 7 | 个人养老金与个人税优账户 | `tax_advantaged_accounts` | 个人养老金账户（1.2 万/年节税测算、Y 份额/养老储蓄/国债/保险）、税优健康险与适用税档 |
| 8 | QDII 跨境基金（场内溢价·直销与支付宝限购）、香港互认与理财通 | `qdii_mrf` | **10 元起普通人普惠跨境渠道（绝非高净值专属）**：场内 QDII 溢价停牌 vs 官方直销 App/支付宝限购分轨、TA 账户合并铁律、互挂双层穿透费、香港北向互认基金（区分收益分配与份额转让的税务口径，并核算锁汇成本）、跨境理财通 2.0、2026-08-07 LOF 征求意见稿及后续公告核验 |
| 9 | 可转债 | `convertible_bonds` | 转债全市场 `511380`（管理与托管合计 0.20%/年）vs 主体 AA 及以上且评级展望非负面 `511180`（管理与托管合计 0.30%/年）、个券权限、去刚兑违约排雷、强赎与到期兑付核对 |
| 10 | 公募 REITs 与不动产租金对比 | `c_reits` | 产权类（NOI/出租率/Cap Rate）vs 特许经营权类（中债 IRR）、指数基金、薄量限价与住宅租售比参照 |
| 11 | 非黄金大宗商品与白银/铂钯渠道 | `commodity_etfs` | 豆粕/有色/能化期货 ETF、白银/原油 LOF 的溢价磨损与拟议退市风险、铂钯/贵金属跨市场合规渠道 |
| 12 | 合规私募与标品信托（合格投资者） | `private_funds_trust` | 合格投资者门槛、私募证券（量化/主观/套利）与标品信托费率结构、锁定期、冷静期与尽调红线 |

---

## 3. 全球多指数优先级播报标准与交互 K 线管线

### 3.1 对称 `3×2` 六大市场驾驶舱与全球多指数优先级标准（严禁单指数播报）
全站门户驾驶舱采用 **对称 `3×2` 六大市场格局（5 大核心市场 + 1 个统一非美全球卫星；仍保持黄金/A 股/港股/美股 4 条每日全主刊正文轨不变）**，日报封面 KPI、正文数据速查表与 `market_state.json` / `gold/data_snapshot.json` 的 `index_matrix` 数组，必须严格按机构终端优先级排序（`rank` 升序、读者可见纯中文 `tier_label`，严禁泄露 `Tier 0–3`）：
- **核心 1 · 中国 A 股（政策驱动型核心市场 · 大盘为先，12 指数）**：**第 1 必须领衔上证指数（`000001`）** → 沪深 300（`000300`）→ 深证成指（`399001`）→ 中证 A500（`000510`）→ 上证 50（`000016`）→ 创业板指（`399006`）→ 科创 50（`000688`）→ 中证 500（`000905`）→ 中证 1000（`000852`）→ 中证红利（`000922`）→ 北证 50（`899050`）→ 中证转债（`000832`）；紧扣央行/财政/产业/监管政策市主线。
- **核心 2 · 中国香港股市（5 基准：`index_matrix` 4 项 + `hsahp_index` · 中国离岸折价腿，A 股政策基本面 + 美股流动性/政策双轨驱动卫星，非海外分散）**：恒生指数（`HSI`）→ 恒生科技（`HSTECH`）→ 恒生国企（`HSCEI`）→ 恒生综合（`HSCI`）+ 恒生 AH 溢价（`HSAHP`，存储于 `hsahp_index`）。
- **核心 3 · 美国股市（联储/财政/关税与地缘政策驱动 · 8 基准 + 直达 QDII 申购入口 CTA）**：标普 500（`SPX`）→ 纳斯达克综合（`IXIC`）→ 纳斯达克 100（`NDX`）→ 道琼斯工业（`DJI`）→ 罗素 2000（`IWM`）→ 标普 500 等权（`RSP`）→ 费城半导体（`SOX`）→ VIX 恐慌指数。
- **核心 4 · 债券/现金与中美利率（`rates_bonds_core`）**：中国国债 2Y/10Y/30Y、美债 2Y/10Y/30Y/TIPS、中美 10Y 利差、`GC001`/`DR001`、中证 REITs（`932047`/`932006`）与短融/长债基锚点。
- **核心 5 · 黄金、大宗与宏观汇率（独立货币避险多锚点）**：伦敦现货金（`XAU`）→ COMEX 金（`GC`）→ 沪金主连（`AU0`）→ 上金所 `Au99.99`/`Au(T+D)` → 伦敦银/沪银 → 布伦特/WTI 原油、铜、美元指数（`DXY`）、`EURUSD`/`GBPUSD`/`USDHKD`/人民币/日元；**BTC 仅作 Layer 1 只读全球流动性温度计，项目配置为 0%，境内虚拟货币业务遵守银发〔2026〕42号禁令**。
- **卫星 6 · 非美全球卫星市场（`non_us_global_satellite` + 直达 QDII 入口 CTA）**：覆盖 9 大非美全球指数——**日本 #1（`513800`）**、**欧洲 #2（`159561`）**、台湾/韩国 AI 景气晴雨表、印度场外观察清单及 `164824` LOF 拟议退市风险提示。

### 3.2 全市场交互 K 线抓取、渲染与 Gate S7 契约
- **零依赖静态分片抓取（`scripts/fetch_kline_data.py --scope all`）**：仅用 Python 标准库按多源路由（腾讯 `fqkline`/`usfqkline`、新浪期货/外汇/北交所/美股、FT 批量 POST 覆盖爱尔兰 UCITS、上金所 `Dailyhq`、中债/美国财政部官方利率 CSV、CBOE VIX 官方 CSV、Coinbase）抓取全市场 **480+ 标的**（核心指数/9 大非美全球指数/中国国债 2Y·10Y·30Y 收益率/中证 REITs `932047`·`932006`/港股 `HSCI`·`HSAHP`/`EURUSD`·`GBPUSD`·`USDHKD` 与大宗汇债 + 181+ 正交标注 ETF + 231 股）写入 `equity/state/klines/*.json`（纳入既有 `AUTOMATED_STAGE_PATHS = ("gold", "equity")` 零扩权），由 `scripts/build_site.py` 复制至 `_site/assets/klines/*.json`。
- **双层 HiDPI Canvas 交互引擎（`scripts/web_assets/kline.js`）**：支持主图叠加（`MA` / `BOLL` / `EMA` / 基本面 `安全锚`）、副图指标（`VOL` / `MACD` / `RSI` / `KDJ` / `ATR` / `BIAS`）、`红涨绿跌`/`绿涨红跌` 切换及 **「技术面 10 秒白话体检条」**（仅输出客观技术状态词，**严禁任何主动买进动词并严格执行黄金红灯锁**）；贯穿全屏 K 线终端 **`charts.html`**、首页 **6 市场交互 K 线切换区**、日报 K 线带及 `screener.html` / `etfs.html` 弹窗 K 线标签页。
- **门户交互增强与 Gate S7**：同期提供 **Layer 1 7 枚宏观气象与危机熔断邻近条**（含中美 10Y 利差与 `银发〔2026〕42号` BTC 只读流动性温度计）、**「我的钱包一键试算器」**（直连实时红绿灯与零金规则、纯本地零上传）、**全站统一自选清单 `★`** 与 **27 对 A/H 税后股息交互比价矩阵**；静态站严检升级为 **S1–S7（7 道门禁）**，Gate S7 专检 480+ K 线分片清单、`charts.html` 完整性、零 NaN 污染与黄金红灯锁一致。

### 3.3 首页 6–9 条与单市场无上限新闻雷达、视觉图表优先与本机伴随监测
- **双层新闻分层架构与 4 列前瞻日历（`07:30 / 11:30 / 18:00` 统一口径）**：彻底废除旧“首页 3 条 / 单市 1–2 条”的人为截断——① **首页 `#sec-policy-calendar`** 精选展示 **6–9 条**（`home_featured: true`）跨市场重磅时政/政策要闻并附按地区筛选及直达各市场全量新闻入口；② **单个市场日报页 `#sec-market-news`（A 股/港股/美股/黄金）无数量上限**，按 `affected_markets` 全量收录该市场全部重要政策/监管/地缘/公司/流动性新闻（正文亦取消 1–2 条上限，核心重磅走完 5 环传导链），并配 **4 列未来 7–14 天全北京时间财经与政策日历表**（与 **`equity/state/policy_calendar.json`** 14–30 天前瞻底座逐项同步；读者可见纯中文级别徽章如「重磅/重要」，严禁裸露 `P0`/`P1`，严格遵守黄金红灯锁）。增量更新经 `equity/state/_edition_patch.json` 可选 `policy_calendar` 键走 `scripts/patch_state_dbs.py --apply` 同步 `edition_id`，只读查库用 `--inspect policy-calendar`。
- **视觉图表优先呈现（Visual-First · 零死板文字墙）**：黄金与三市每篇主刊/守望刊除既有标准矢量图外，须结合数据特征嵌入 **1–2 张通用矢量信息图 `<!-- DAILY_VISUAL { ... } -->`**（由 `scripts/visual_widgets.py` 渲染 4 大零碰撞 640px 图型：`waterfall` 损益桥/净流动性瀑布、`bar_compare` 央行概率/多渠道价差横条、`anchor_range` 焦点股现价 vs 安全锚区间、`flow_chain` 因果传导链，全部纳入双轨 SVG 零碰撞严检）；门户构建时自动为每篇日报注入首屏可视化体检驾驶舱（6 维/四关进度条 + 钱包比例条 + 危机熔断进度仪表）、100% 堆叠情景概率条与传导链节点卡片。
- **本机伴随实时监测与合规微信推送（零扩权、零仓库污染）**：`scripts/realtime_monitor.py` 与 `scripts/wechat_notify.py` 作为本机伴随工具独立运行于 56 项定时出版权限清单之外（`automations/permissions.json` 严格锁定 56 项不变），以**严格只读**方式消费 `gold/data_snapshot.json`、`equity/state/market_state.json` 与 `equity/state/policy_calendar.json`（严格继承黄金红灯锁），告警去重与冷却状态仅写入 **`.git/realtime-monitor.sqlite3`**（零 Git 工作树污染），推送密钥外置于 `~/.config/global-investment-research/notify.json`（`chmod 600`），通过 WxPusher / 企业微信机器人 / PushPlus / Server酱合规推送（零个人微信 Hook 封号风险）。

---

## 4. 一体化三定时任务节拍与分层刷新矩阵（CST / UTC+8）

统一运行 **每日 3 个一体化单会话定时任务**，工作日早/午/晚三班全面执行 **四市全主刊（All-4-Main，保持 4 条完整日报正文轨不变，休市市场按计划切 `holiday_watch`）+ 10+1 并行调研红队 + 三大扩展数据库强制期号锁 + 480+ K 线刷新 + 纯网页发布**；三个班次共享统一单向允许窗 **`[-5 分钟, +6 小时]`**，早班与午班的允许窗重叠，实际运行由同一互斥锁串行控制：

| 定时任务 ID | 触发时间与窗口（CST） | 班次定位 | 单会话串行产出与分层刷新重点 |
| :--- | :--- | :--- | :--- |
| **`daily-global-investment-research`** | **每日 `07:30`**<br>（`07:25–13:30`） | **一体化早报** | ① 黄金 `0730_早报`（刷新 `gold/data_snapshot.json` SSOT 并严检） → ② **A 股 / 港股 / 美股全发收敛主刊（`main`，≥2 图；休市切 `holiday_watch` ≥1 图）**；同步推进三大扩展库至当班 `edition_id`：早班聚焦隔夜美盘/美债/汇率、美股与爱尔兰 UCITS 官收、美股 QDII 溢价停牌、外币存款理财、港股夜期盲窗、盘前逆回购/打新/转债日历及 4–6 只焦点股 7 维刷新 → ③ 统一 RSI 盲审 + K 线抓取 + 单次纯网页发布 |
| **`daily-global-investment-research-midday`** | **每日 `11:30`**<br>（`11:25–17:30`） | **一体化午报** | ① 黄金 `1130_午报`（锁定 `11:30 CST` 上金所/沪金早盘官收与同刻 `XAU × USD/CNY ÷ 31.1034768` 平价溢价、国内四大行金条与品牌金店当日牌价、亚盘美期/美债及 `09:15` CFETS 中间价/`09:20` 央行 OMO/`09:30` 统计局宏观数据；美东非 VIX 窗口 `vix_live` 留空） → ② **权益午班**：**A 股 `11:30` 官方早盘收盘**（全 12 优先指数、沪深半日成交、中金所午盘基差、`10:30` 停牌 QDII 复牌溢价、`11:30` `GC001`/`DR001`/10 年国债）；**港股 `11:30–11:45` 午盘前实盘**（`11:15` 官方 HKAB HIBOR、恒指/恒科/国指/恒综/AH 溢价、除权配售与新股招股；南向午盘 12:00 后披露写入 `data_caveats`）；**美股隔夜终盘（已过 09:00/08:00 盘后终盘）或休市/黑五守望刊** + 亚盘 ES/NQ/美债期货 → ③ 统一 RSI 盲审 + K 线抓取 + 单次纯网页发布 |
| **`daily-global-investment-research-evening`** | **每日 `18:00`**<br>（`17:55–次日 00:00`） | **一体化晚报** | ① 黄金 `1800_晚报`（刷新 `gold/data_snapshot.json` SSOT 并严检） → ② **A 股 / 港股 / 美股全发收敛主刊（`main`，≥2 图）**；封账 A/港日终官收、中金所/南向/16:30 汇率与美股盘前及滞后盘后终盘，同步推进三大扩展库至当班 `edition_id`：晚班聚焦债券 ETF/逆回购日终利率、可转债与 REITs 日终估值、非金商品 ETF 收盘、场内 QDII 日终溢价与停牌公告及 4–6 只焦点股 7 维刷新 → ③ 统一 RSI 盲审 + K 线抓取 + 单次纯网页发布 |
| **周六 / 周日** | **周末专项 / 周度校准** | **休市与深研轮换** | 周六 `07:30` 黄金周末专项主刊 + 美股周五复盘主刊（美股半日市发 `holiday_watch` ≥1 图，美股全休沿用旧稿）；**周六 `11:30` / `18:00` 与周日 `07:30` / `11:30` / `18:00` 三市默认沿用旧稿**，**仅周日 `18:00` 班执行全量周度校准**：更新 12 大渠道中低频项（大额存单、外币定存、储蓄保险、个人养老金、私募信托、租金对比）、全量核对 181+ 正交标注 ETF 费率规模、轮换精修 231 股池中的 **6–10 只核心龙头 7 维档案**并推进 `SCORECARD.md` 周频复盘 |

> 每班启动必须执行 `python3 equity/lint_equity.py --plan <edition_id>` 获取具体市场、刊型（`main` / `holiday_watch`）与沿用安排。

---

## 5. 单会话严格顺序流水线（Step 0 → Step 5 · 纯网页极速版）

每次 `07:30`、`11:30` 或 `18:00` 一体化班次必须严格按以下顺序在同一会话内串行推进，严禁跳步或乱序：

- **运行锁、单向时间窗、僵尸锁清理与维护者专属运维命令**：定时入口运行 `scripts/edition_run.py begin --scheduled 0730` / `--scheduled 1130` / `--scheduled 1800`，**定时运行窗与单向截点宽限统一为 `[-5 分钟, +6 小时]`（`07:25–13:30` / `11:25–17:30` / `17:55–次日 00:00` CST；黄金截点须早于或同分钟于权益且跨轨差值 `0–6 小时`）**。`begin --scheduled` 会先尝试收尾已有推送凭据的班次，并自动清理**严格较早期号**（`0730 < 1130 < 1800`）、超 2 小时无进展且尚未进入推送的僵尸锁。收到 token 后才进入调研；依次登记 `gold`、`equity`、`publish`，有进展时用 `heartbeat` 刷新时间。若历史已推送班次被后续提交覆盖，维护者可人工区分 **`complete-superseded`**（校验目标提交已是现网祖先且仅含授权文件变更后结案为 `complete`）与 **`close-superseded`**（将其标为 `failed` 并记录被后续提交替代的 `outcome` 以释锁）——**两项均为维护者专属手动运维命令，严禁纳入定时自动化 `automations/permissions.json` 白名单**。
- **期号交接与三库同期锁**：当班黄金快照、黄金日报 `DAILY_META`、权益状态、新权益稿 `DAILY_META_JSON`、三大扩展数据库（`multi_asset_channels.json`、`etf_universe.json`、`deep_dossiers.json`）与 `equity/state/policy_calendar.json` 记录同一 `edition_id`。黄金日报同时记录与快照一致的 `as_of_short`。休市沿用旧稿时保留旧稿期号与时间，状态、政策日历与三大数据库仍刷新至当班期号。

1. **Step 0｜双轨 RSI 经验库冷启动**：
   - 读取 `gold/daily/RSI_PLAYBOOK.md`（≤180 行）、`equity/state/RSI_PLAYBOOK.md`（≤180 行）及两轨 `rsi_metrics.json` 最近记录。
2. **Step 1｜跨市场日历、基线快照与三大深研库冷启动**：
   - 读取 `gold/market_calendar.json`、`gold/data_snapshot.json`、`gold/master_snapshot.json`、`equity/state/market_state.json`、`equity/state/multi_asset_channels.json`、`equity/state/etf_universe.json`、`equity/state/deep_dossiers.json`、`equity/state/policy_calendar.json`、两轨 `SCORECARD.md`、`gold/daily/CHANGELOG.md` 与 `equity/daily/INDEX.md`。
3. **Step 2A｜共享 10 路并行 `research` 深度调研（10+1 架构）**：
   - 启动 **10 路只读 `research` 子代理**（每路回执严控 `≤ 12 KB` 紧凑表格防拖尾）：① 黄金与贵金属（午班锁 11:30 上金/沪金早盘与同刻溢价、银行金条/品牌金店牌价）、② 中国 A 股（全 12 优先指数且上证 #1 领衔）、③ 中国香港股市（5 基准 + `11:15` HIBOR）、④ 美国股市（8 基准）、⑤ 跨资产宏观汇率与大宗（含 Layer 1 7 枚宏观气象与危机熔断邻近条、中美 10Y 利差、非美全球卫星日/欧/台韩/印锚点、跨资产传导链与 48h 双向触发线）、⑥ 三地社区与谣言辟谣、**⑦A 境内稳健与税优 6 渠道专线**、**⑦B 境内外币/QDII与MRF（含直销 vs 代销限额分轨、TA 合并与 LOF 退市提案状态）/可转债/C-REITs/非金商品与白银铂钯/私募信托与打新反诈专线**、**⑧A 全市场 181+ 重点 ETF（正交标注 `asset_class` × `region` × 6 通道）分批溢价/停牌/规模/费率（含互挂穿透双层费）专线**、**⑧B 当班全部焦点股（约 16 只及周日 `18:00` 班 6–10 只全池轮换）7 维深研与近 24 小时官方公告硬扫雷专线**（必查沪深/港交所/SEC 近 24 小时折价配售、分红、管理层变动与信用评级观察，现价实算股息/估值并刷新 `updated_at`）。遇单项数据未发布或暂不可取时严禁编造、亦不阻塞发布，按规范挂账并写入纯读者中文 `data_caveats`。
4. **Step 2B｜1 路统一发前红队对抗核验（10+1 架构）**：
   - 跨轨交叉审计共享宏观数字与 **T-0 宏观官源四铁律**（日本 CPI 直核 `stat.go.jp` 区分日央行版剔生鲜能源[权重 9162]与欧美版剔全部食品能源[权重 6959]；香港金管局查当日总结余及未来两日预测；上期所夜盘严分 `02:30` 金银/`01:00` 有色/`23:00` 黑色化工且 LME 严守 17:00 同盘口；高溢价 QDII 严分暂停申购/仅恢复赎回与恢复申赎）、多指数优先级秩序、黄金红灯全载体锁、A/H 物理一致、100% 配置闭环、12 大多元渠道与 QDII 制度红线、181+ ETF 正交分类（`asset_class` × `region` × 6 通道）与跨库费率防错（含 `511380` 0.20% vs `511180` 0.30%）、`CHART_A2` 贴水正号与红涨青跌色、焦点股 7 维近 24 小时公告/现价实算与小白友好白话清晰度。
5. **Step 3｜黄金 SSOT 优先落盘与 6 门禁严检（纯网页）**：
   - 先用 `write_file` 全量更新 `gold/data_snapshot.json`（含 `index_matrix` 与纯读者中文 `data_caveats`）、当期黄金日报 Markdown（`0730_早报` / `1130_午报` / `1800_晚报`）与 `gold/daily/SCORECARD.md`；跨月归档上月黄金账本时先写 `gold/daily/_archive_patch.json` 并调用预授权 `scripts/patch_state_dbs.py --archive-gold-ledgers` 无损归档；持续增长的历史双账本（`gold/daily/CHANGELOG.md`、`gold/daily/AUDIT_LOG.md`，含本期 `GOLD_EDITION_REVIEW` 标记）通过 `write_file` 写微型补丁 `gold/daily/_ledger_patch.json` 并调用预授权 `scripts/patch_state_dbs.py --prepend-gold-ledgers` 无损头插。仅命中 5 大阈值时同步主报告与 `master_snapshot.json`。
   - 运行：`python3 gold/lint_readability.py --strict <本刊路径>`（必须 `0 errors, 0 warnings`）。
6. **Step 4｜全球权益三市、12 大多元渠道、181+ ETF 与 231 股 7 维深研库接力落盘与严检（纯网页）**：
   - 只读校验本期黄金快照（两轨截点均须在所标班次 `[-5 分钟, +6 小时]` 单向窗口内且黄金早于或同分钟于权益、差值 `0–6 小时`）和 Tier-0 行动互斥锁。用 `write_file` 全量落盘本期日报 Markdown、`INDEX.md`（纯网页/Markdown 链接，禁用离线附件链接）、`CHANGELOG.md`、`SCORECARD.md` 与 `state/market_state.json`（含 `index_matrix`、27 对 A/H 基准与 `data_caveats`）；月初遇 `--plan` 切换 `period_slug` 时写紧凑 `equity/state/_rollover_patch.json` 并调用预授权 `scripts/patch_state_dbs.py --rollover-equity-month` 原子克隆三旗舰与 `_latest.md` 并更新 `report_meta_*.json`；持续增长的 `state/audit_ledger.md` 写 3 键 `equity/state/_audit_patch.json` 经 `scripts/patch_state_dbs.py --prepend-equity-audit` 无损头插；**权益三大扩展大 JSON 统一写微型补丁 `equity/state/_edition_patch.json` 并调用预授权 `scripts/patch_state_dbs.py --apply` 原子合并（只读查库用 `--inspect <target>`），强制同步 `edition_id`，执行跨库费率一致性护栏、兄弟字段与 A/H 孪生股一致性校验、诚实单股 `updated_at` 及 12 大渠道/181+ 正交标注 ETF/231 股零模板化 7 维深研全检**。
   - 运行：`python3 equity/lint_equity.py --strict`（必须 `0 errors, 0 warnings`）。
7. **Step 5｜统一 RSI 盲审闭环（5 项真核验）+ 480+ 交互 K 线刷新 + 单次纯网页门户发布**：
   - 先用 `scripts/patch_state_dbs.py --inspect review-candidate` 取得候选期号、稿件与数据文件清单和摘要。启动 **1 路独立只读 `research` 盲审子代理**，按两轨各 6 维 `/30` 打分（第 4 维聚焦**纯网页视觉清晰度、SVG 零碰撞与小白 3 分钟可读性**）、预判验真并执行 **5 项真核验**。晚于 `2026-11-28_1130` 的双轨回执应写入 `candidate_sha256` 和逐项核验的文件与结果。官源项逐条绑定当班新稿的原句、事实或推论类型、原始出处和实查结果，具体字段沿用 [定时提示词](automations/unified-edition.prompt.md)。修稿后须重新获取摘要并复审，发布前重新核对实际文件。用 `scripts/patch_state_dbs.py --append-gold-rsi` 与 `--append-equity-rsi` 无损入账，并更新两份 `RSI_PLAYBOOK.md`。已解决、待外部数据和已披露限制分别登记 `resolved`、`deferred_data`、`disclosed_caveat`。未解决硬错或回执与候选版本不一致时停止发布。
   - 复跑 `gold/lint_readability.py --strict` 与 `equity/lint_equity.py --strict`，随后运行 `python3 scripts/fetch_kline_data.py --scope all` 刷新全市场 480+ 标的静态分片 K 线至 `equity/state/klines/`，进入 `publish` 阶段运行 `python3 scripts/publish_site.py --edition-token <token>`（构建完整静态门户——含 `charts.html`、Layer 1 7 枚宏观气象与危机熔断条、Layer 2 对称 `3×2` 六大市场驾驶舱、我的钱包一键试算器、6 市场 K 线交互区、自选 `★`、27 对 A/H 矩阵、按 4 大执行角色分层的 12 渠道概览卡与独立 `channels/<id>.html`、181+ 正交标注 ETF 概览卡与 `channels`/`etfs`/`screener`/`guide`/`scorecard`/`archive`——通过 **S1–S7** 严检后单提交推送至 `origin/main`），最后运行 `python3 scripts/edition_run.py complete <token>` 验证 GitHub Pages 实际部署成功即闭环。

---

## 6. 跨轨硬不变式（Hard Cross-Track Invariants）

1. **黄金 SSOT 唯一写入权 + Tier-0 行动互斥锁**：
   - `gold/data_snapshot.json` 仅允许黄金轨（Step 3）写入，权益轨（Step 4）严格只读校验；
   - 当 `tier_code == "Tier 0"` 或 `new_buy_allowed == false` 时，全仓库公开正文、三大扩展 JSON、交互 K 线技术诊断条与全站网页（含首页、`charts.html`、`channels.html`、`channels/*.html`、`etfs.html`、`screener.html`、`guide.html`）严禁出现新买/补齐黄金指令或将黄金/金矿标的标为绿色底座（由 `equity/lint_equity.py` Gate C2 与 `scripts/lint_site.py` Gate S6/S7 强制阻断）。
2. **纯网页零离线附件交付与首页全渠道透明**：
   - 全站严禁输出或链接任何离线二进制文档附件（由 `scripts/lint_site.py` Gate S2 与 `equity/lint_equity.py` Gate 4 强制阻断）；
   - 门户首页 `index.html` 必须清晰呈现 Layer 1 7 枚宏观气象与危机熔断条（含中美 10Y 利差与银发〔2026〕42号业务禁令与项目配置为 0% 的 BTC 只读流动性温度计）、Layer 2 对称 `3×2` 六大市场驾驶舱（5 核心 + 1 非美全球卫星，A 股上证 #1，4 条完整日报正文轨不变）、小白钱包试算器、6 市场 K 线交互切换区、按 4 大执行角色分层的全部 12 大个人多元渠道概览卡（直链独立页 `channels/<id>.html`）与 181+ 正交标注（`asset_class` × `region` × 6 通道）ETF 概览卡（由 `scripts/lint_site.py` Gate S6/S7 强制核验）。
3. **跨轨核心合规、QDII 制度铁律与费率口径完全统一**：
   - **QDII 场内 vs 官方直销 App vs 支付宝五大制度铁律（实时限额与溢价均以 `state/*.json` 为唯一真相源，严禁在此硬编码实时数字）**：
     - **TA 账户全网合并 vs 直销/代销双轨分计**：场外公募“单日单个基金账户”在 TA 注册登记层按身份证号合并全部第三方代销平台（支付宝/天天基金/微信理财通/银行），跨平台同日重复买同一代码将在 T+1 清算拒单退款；合法扩容仅有三条路径——① 公告明确“各类份额分别单独计算”时分买不同份额代码（`A`/`C`/`I`/`USD`）；② 基金公司官方公告明确区分“直销渠道与非直销/代销渠道”限额时（如部分实行直销倾斜的公募官方 App vs 全渠道一刀切公募），通过官方直销 App 获取更高额度或分开叠加；③ 跨不同基金公司的独立外管局 SAFE QDII 额度池；
     - **美元现汇份额不破 SAFE 总额度**：境内美元现汇申购依然计入同一管理人在国家外汇管理局核批的同一 QDII 额度池，切勿专门花结售汇点差换美元去追逐更高限购额度；
     - **跨境互挂/互通 ETF 年费核验**：中日互通、中新互通、沪深港沙特互挂、中巴互挂等适用 SAFE QDII 额度的产品，继续核对管理人额度。境内及底层费用分别披露。按合同核对目标 ETF 持仓部分是否减免境内管托费，结合实际持仓比例及同一期间可比费率估算；资料不足时分列费率与口径。 与物理直投型产品对照时按相同费用口径比较；
     - **2026-08-07 LOF 公开征求意见**：沪市草案涉及 QDII-LOF，深市草案还涉及商品期货 LOF。两所草案均将 **`2027-12-31`** 列为相关品种拟议退出期限。核对交易所正式规则和基金管理人的个别公告，区分拟议期限、场外转型与依法清盘；场内交易退出会使既有溢价面临损失。[上交所征求意见通知](https://www.sse.com.cn/lawandrules/publicadvice/c/c_20260807_10828305.shtml)；
     - **场内溢价 vs 场外排队盈亏平衡数学与代码核验铁律**：场外均匀分批建仓预期机会成本近似为 `0.5 × (N / 250) × r_excess`（`N = M / D` 为按日限额 `D` 建仓资金 `M` 所需交易日数，`r_excess` 为权益预期年化收益减现金泊车收益），量化证明场内溢价超过 `2%–3%` 即相当于提前透支数月至数年超额收益；**严禁默认每只场内 QDII ETF 均配有场外联接或凭相邻代码臆测**（必须逐只核查基金公司官方名录与币种代码，如核实无联接产品、区分美元 A 与人民币 C）。
   - **黄金联接 `008142` / `008143`**：按基金最新合同和渠道披露比较申购费、运营费、销售服务费及赎回费。证监会新规自 2026 年 1 月 1 日施行，存量不合规费用限 12 个月调整。适用份额持续持有超过一年后停止继续收取销售服务费，首年费用按合同。旧版工银 `008143` 的免赎回期为满 30 天，使用时核对现行合同。[证监会销售费用管理规定](https://www.csrc.gov.cn/csrc/c101954/c7606091/content.shtml)
   - **可转债 ETF 费率区分**：全市场可转债 ETF **`511380`** 综合费率为 **0.20%/年**（管理 0.15%+托管 0.05%），而投资级上证可转债 ETF **`511180`** 综合费率为 **0.30%/年**（管理 0.25%+托管 0.05%），严禁跨库混写费率；
   - **MRF 禁推停申基金与受限代码护栏**：严禁推荐已暂停申购的 `968118`，须警示派息份额 `968001`（按现金流需要比较份额类型；对符合条件的内地个人，互认份额转让差价暂免个税至 2027 年底，取得的基金分配收益适用 20% 代扣，实际以分配构成及公告为准），并严禁列入已退市恒生银行 `00011`（用渣打 `02888` 替代）；
   - **二手大额存单**：多数国有大行禁止二次转让，且二手接盘单严禁直接提前支取（否则仅按原票面本金 + 活期计息致本金实亏）；
   - **债券 ETF 底层税负区分**：交易所公司债/科创债 ETF 底层债券付息环节仍扣 20% 税（区别于银行间市场的短融 ETF `511360` 等银行间标的）；
   - **离岸资产与跨境合规**：中国居民个人按所得类别计算境外所得税额并申报，利息、股息、红利等分类所得适用 20% 法定税率，符合规定的境外已缴税额可在限额内抵免。香港挂牌的 `02840.HK` 为美国注册信托份额，按持仓结构和美国所在地资产规则核验。对非美国公民且死亡时不以美国为住所者，6 万美元是一般遗产税申报门槛，须核对全部美国所在地资产、适用赠与及协定。[国家税务总局](https://www.chinatax.gov.cn/chinatax/n810219/n810744/n3752930/n3752974/c5143076/content.html) · [美国国税局](https://www.irs.gov/instructions/i706na)
4. **小白友好三层写作与零本地路径/内部词泄露**：
   - 确立 **「30 秒红绿灯白话结论 → 10 万/1 万元钱包实算与三步怎么买 → 机构级 7 维硬核证据」** 三层结构；`DXY`/`COT`/`CDS`/`ERP`/`IRR` 等专业词移出“可不解释裸用”名单，首现配简短白话括注或交由站内术语浮窗解释；禁用居高临下说教口号，鼓励平等温和的「3 分钟速读结论」「关键词白话速查」；
   - 所有公开文件、K 线分片 JSON 与生成静态网页严禁出现本地绝对路径、密钥或内部工程/脚本/RSI 文件名（含 `fetch_kline_data.py`，由 `scripts/lint_site.py` Gate S3 严守）。
5. **无人值守分级写盘、预授权绝对路径裸命令与三道严格门禁零容忍**：
   - 定时无人值守任务常规禁 `edit_file`（**仅允许用 `edit_file` 定点修正 `equity/state/_edition_patch.json` 校验报错**）且严禁单轮并行打包 >2 个大型 `write_file`：中小 Markdown 与轻量快照一律使用 `write_file` 全量写盘；权益三大扩展大 JSON 与 `policy_calendar.json`、黄金历史双账本（`_ledger_patch.json` 须将 `<!-- GOLD_EDITION_CHANGELOG ... -->`/`<!-- GOLD_EDITION_REVIEW ... -->` 置于第 1 行）与跨月归档、权益审计账本、三市旗舰月初滚存与双轨 `rsi_metrics.json` 统一走预授权 `scripts/patch_state_dbs.py` 增量原子命令；全市场 K 线刷新统一走预授权 `scripts/fetch_kline_data.py --scope all`；所有命令行操作仅运行 `sidecar.json` 预授权的绝对路径裸命令（56 项无通配符精确授权）；
   - 交付与发布前，以下**三道严格门禁必须全部退出码 `0`（`0 errors, 0 warnings`）**：
     - `python3 gold/lint_readability.py --strict gold/daily/<最新黄金日报>.md`
     - `python3 equity/lint_equity.py --strict`
     - `python3 scripts/build_site.py --out _site && python3 scripts/lint_site.py _site --strict`
6. **准点发刊不阻塞与信息缺口全透明（Anti-Blocker & Data-Caveats Transparency）**：
   - 定时运行窗与单向截点宽限均为 **`[-5 分钟, +6 小时]`**（黄金早于或同分钟于权益且跨轨差值 `0–6 小时`）；`begin --scheduled` 自动清理**严格较早期号**、超 **2 小时**无进展且尚未进入推送的僵尸锁；
   - 两轨同步维护纯读者中文、零内部文件名的结构化 **`data_caveats`** 数组，在首页与日报页自动披露信息缺口及对核心裁决的影响。

---

## 7. 子轨权威契约与工作区技能索引

- **黄金子轨规则与格式宪章**：[gold/AGENTS.md](gold/AGENTS.md) · [gold/daily/AGENTS.md](gold/daily/AGENTS.md) · [gold/daily/DAILY_FORMAT_SPEC.md](gold/daily/DAILY_FORMAT_SPEC.md) · [gold/daily/RSI_PLAYBOOK.md](gold/daily/RSI_PLAYBOOK.md)
- **权益、12 大多元渠道与 7 维深研宪法与排版详规**：[equity/GEMINI.md](equity/GEMINI.md) · [equity/DAILY_REPORT_SPEC.md](equity/DAILY_REPORT_SPEC.md) · [equity/state/RSI_PLAYBOOK.md](equity/state/RSI_PLAYBOOK.md)
- **统一工作区三 Skill（`.agents/skills/` · Tier C 只读）**：
  - [.agents/skills/gold-research-publishing/SKILL.md](.agents/skills/gold-research-publishing/SKILL.md)
  - [.agents/skills/equity-report-publishing/SKILL.md](.agents/skills/equity-report-publishing/SKILL.md)
  - [.agents/skills/equity-research-editorial-qa/SKILL.md](.agents/skills/equity-research-editorial-qa/SKILL.md)
- **共享提示词、授权和定时安装（Tier C 只读）**：[定时提示词](automations/unified-edition.prompt.md) · [授权配置](automations/permissions.json) · `automations/sidecars/*.template.json` · [安装器](scripts/install_sidecars.py)
