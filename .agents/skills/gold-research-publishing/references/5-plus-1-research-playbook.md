# 两阶段调研与红队复核操作手册（一体化 10+1 日常主力 · 独立黄金 5+1 单跑回退）

> **调度架构总览**：
> - **一体化 10+1（日常主力 · 每日 `07:30` 早报 / `11:30` 午报 / `18:00` 晚报定时三班次强制执行）**：在单仓库一体化单会话任务（`daily-global-investment-research` / `daily-global-investment-research-midday` / `daily-global-investment-research-evening`）中，**阶段 2A 并行启动共享 10 路 `research` 子代理**：① 黄金与贵金属（午报锁 11:30 上金/沪金早盘同刻平价与四大行金条/金店新牌价）、② 中国 A 股（全 12 大优先指数且上证 #1 领衔）、③ 中国香港股市（5 基准 + `11:15` HIBOR）、④ 美国股市（8 基准）、⑤ 跨资产宏观汇率与大宗、⑥ 三地社区与谣言辟谣、**⑦A 境内稳健与税优 6 渠道**（活钱与现金管理 `reverse_repo`、人民币银行存款全家桶 `large_cds`、债券与债券 ETF `bonds`、公募基金/银行理财与投顾 `funds_wm`、储蓄型商业保险 `savings_insurance`、个人养老金与税优账户 `tax_advantaged_accounts`）、**⑦B 跨境/固收增强/另类/私募信托与打新反诈**（境内外币存款与理财 `fx_deposits_wm`、场内外 QDII/香港互认与理财通 `qdii_mrf`【含直销 App vs 支付宝分轨与 LOF 退市】、可转债 `convertible_bonds`、公募 REITs 与不动产租金对比 `c_reits`、非黄金大宗商品与白银铂钯 `commodity_etfs`、合规私募与标品信托 300 万专享 `private_funds_trust` 及横向打新工具箱/双层风控警示墙）、**⑧A 全市场 174+ 重点 ETF 实时溢价/停牌/规模/穿透费率专线**、**⑧B 当班全部约 16 只焦点股（A/港/美各 4–6 只及周日 6–10 只全池轮换）7 维深研与近 24 小时官方公告硬扫雷专线**。待全部返回后启动 **阶段 2B 1 路统一跨轨红队**，一次覆盖双轨 7 类官方信源、同步锁定共享宏观数字、跨轨统一税费口径与黄金红灯互斥锁，详见仓库根宪章 `<REPO_ROOT>/AGENTS.md`。
> - **独立黄金 5+1（单跑回退 · 仅单独维护、勘误或手动重跑黄金轨时使用）**：当不联动权益与多元渠道轨、仅独立运行黄金深度研报时，回退至下文第 2–3 节的 **5 路黄金专项并发调研 + 第 6 路黄金红队**；其全部信源清单与一体化 10+1 的第 ①、⑤、⑥ 路一一对应。

本文档固化 `global-investment-research/gold` 的全信源外部调研、无情红队对抗审计、周末/局部休市切换、`CHANGELOG.md` / `AUDIT_LOG.md` / `SCORECARD.md` 三账本维护及月度归档协议与 Step 5 RSI 盲审模板（纯网页版，不涉任何离线二进制文档）。

---

## 1. 安全、防卡壳、官收白/黑名单与抗阻塞前提

1. **命令边界、防卡壳红线与三层 RSI 防篡改**：
   - 在定时自动化任务中，主代理严禁运行 `date`、`ls`、`curl` 等未授权 shell 命令，**亦严禁调用 `edit_file`**：中小 Markdown 与轻量快照（日报、`data_snapshot.json`、`market_state.json`、`SCORECARD.md`、两份 `RSI_PLAYBOOK.md` 等）一律使用 `write_file` 全量写盘；**所有大文件、增长型账本、双轨 `rsi_metrics.json` 与月初滚存/归档严禁整文件重写，统一写微型补丁并调用预授权 `scripts/patch_state_dbs.py` 原子命令（彻底防 300s 超时）**：权益三大扩展大 JSON（`_edition_patch.json` → `--apply`，只读查库用 `--inspect <target>`）、黄金历史双账本（`_ledger_patch.json` → `--prepend-gold-ledgers`；跨月归档 `_archive_patch.json` → `--archive-gold-ledgers`）、权益审计账本（`_audit_patch.json` → `--prepend-equity-audit`）、双轨 `rsi_metrics.json`（`gold/daily/_rsi_patch.json` → `--append-gold-rsi`、`equity/state/_rsi_patch.json` → `--append-equity-rsi`）及权益月初旗舰滚存（`_rollover_patch.json` → `--rollover-equity-month`）；
   - 正常发刊阶段（Step 1–4）严禁修改任何 `.py` 脚本与规则文件，仅在 Step 5 RSI 闭环中严格按 Tier A/B/C 权限边界执行受控自进化（永不削弱门禁，永不静默修改 `AGENTS.md` 或核心金融风控红线）；
   - 调用预授权质检、大库补丁、K 线抓取与发布脚本（`scripts/patch_state_dbs.py`、`scripts/fetch_kline_data.py`、`gold/lint_readability.py`、`equity/lint_equity.py`、`scripts/build_site.py`、`scripts/lint_site.py`、`scripts/publish_site.py`、`scripts/edition_run.py` 及排障用 `unittest`）必须使用绝对路径裸命令（禁加 `cd &&` 前缀）；常规班次执行**惰性主报告加载**（仅读 `master_snapshot.json` 核验 5 大触发条件，命中时才全量读取主报告 MD）；同场修订加 `_r2` 后缀严禁覆写既有归档。
2. **联网边界**：所有外部实时行情、政策原文、研报与舆情调研，统一交由 `research` 子代理使用中英双语 `search_web` 完成。
3. **反幻觉与透明缺口铁律**：
   - 每条新增报价或事件必须附 **信源 + 精确时点**；
   - 某市场休市或单项官报尚未发布时**严禁编造、亦不阻塞发刊**：正文如实写「休市 / 待披露 · 沿用上一终盘（标注时点）」，并在 `data_snapshot.json` 的 **`data_caveats`** 写入纯读者中文结构化声明（零内部文件名/工程词），供下一班次清零；
   - 严格区分交易时间戳，严禁把不同时点的国内外报价差误作“国内溢价”（溢价必须按同一分钟时间戳换算），严禁盘后讲话倒推归因已收盘盘口。
4. **官收信源白/黑名单、抗阻塞校验参数与北美冬/夏令时硬校验**：
   - **美股 `GLD`/`GDX` 官收白名单**：强制交叉校验 **`StockAnalysis` / `Investing` / Yahoo / 腾讯历史收盘表 + `SSGA .xlsx` / `VanEck` 官方 NAV**，严禁误采盘中快照或开盘价充作官方收盘价；COMEX 期金/期银/期铜检索直加 `"official settlement"`；
   - **远月滞后源黑名单**：**严禁采纳 `Barchart` 远月滞后合约快照**（如 `GCG27` 滞后异常值），防止跨合约串位污染；
   - **定向官方补录检索词**：补录滞后官方表时，检索词强制包含 **`site:shfe.com.cn`**（上期所席位龙虎榜与合约分账）、**`site:lbma.org.uk`**（伦敦金银定盘官方表）及 **`"基金份额" "518880"`**（国内黄金 ETF 份额流，落盘至无日期标准键 **`etf_cn`**）；国内夜盘涨跌必须以上金所/上期所**前一日官方日终清算表**为分母；
   - **抗阻塞校验时限（`edition_validation.py`）**：单向班次截点宽限 **`[-5 分钟, +6 小时]`**；节日待披露 `pending` 复查间隔 **4 小时**；普通交易日与半日市（黑五 `11/27`、平安夜 `12/24`）均支持 Cboe 现货 VIX `provisional_close`（普通日须在 **3 个自然日**内以官方 CSV 终值核销，次日班次须在 6h 窗口内重查）；`no_row_confirmed` 支持 `*.cboe.com` 公告或官方 CSV 自证 `next_published_date > day`；日历已延展至 **`2027-06-30`**（有效覆盖硬底线 30 天 / `<60 天` 提示 / 核证有效期 90 天）；
   - **北美冬/夏令时硬校验（动态对齐 `market_calendar.json`）**：当前北美冬令时（`2026-11-01` 至 `2027-03-13`）严格执行 **`EST = BJT - 13h`、`CST = BJT - 14h`**（COMEX `13:30 EST` 官结 = `02:30 BJT`、NY 现货 `17:00 EST` = `06:00 BJT`、美股 `16:00 EST` = `05:00 BJT`）；自 **`2027-03-14`** 起自动切入夏令时（`EDT = BJT - 12h`、`CDT = BJT - 13h`、COMEX 官结 `01:30 BJT`、NY 现货 `05:00 BJT`）。

---

## 2. 阶段 2A：并行启动调研子代理（一体化 10 路主力 / 独立黄金 5 路回退）

- **一体化 10+1 映射（日常主力）**：遵循 `<REPO_ROOT>/AGENTS.md` 第 4 节 Step 2A，一次并发启动 **共享 10 路 `research` 子代理**（容量不足时按平台支持并发数分组，仍严守 10 路独立分工）。下表明确「一体化 10 路主力」与「独立黄金 5 路单跑回退」的 1:1 映射关系：

| 一体化 10 路主力（`07:30` / `11:30` / `18:00` 定时日常） | 独立黄金 5 路回退（单跑黄金轨） | 核心覆盖范围 |
| :--- | :--- | :--- |
| **第 ① 路：黄金与贵金属专线** | **黄金专线 1 + 黄金专线 3** | 全球金银铜实盘、SGE/SHFE（含 11:30 午盘同刻平价）/LBMA/GLD/GDX 官收、投行目标价、COT、水贝/四大行/央行购金 |
| **第 ②–④ 路：A 股 / 港股 / 美股三市专线** | *仅一体化班次启用（单跑跳过）* | 三市多指数优先级矩阵（A 股上证 #1 领衔 12 指数）、7 维大盘、盘面/两融/南向/联汇/11:15 HIBOR/美股盘后与政策雷达 |
| **第 ⑤ 路：跨资产宏观、汇率与地缘专线** | **黄金专线 2 + 黄金专线 4** | G4 央行、美债 `DFII10`/`2Y-FF`、汇市/油气/VIX/信用配管、霍尔木兹与地缘排雷日历 |
| **第 ⑥ 路：三地社区情绪与谣言辟谣专线** | **黄金专线 5** | 国内外金融论坛、社媒情绪极值、Polymarket/Kalshi 赔率与官方谣言证伪 |
| **第 ⑦A / ⑦B 路：12 大个人多元渠道双专线** | *仅一体化班次启用（单跑跳过）* | ⑦A 境内稳健税优 6 渠道；⑦B 跨境（含 QDII 直销 vs 支付宝分轨与 LOF 退市）/固收增强/另类/私募信托与打新反诈 |
| **第 ⑧A / ⑧B 路：174+ ETF 与焦点股 7 维双专线** | *仅一体化班次启用（单跑跳过）* | ⑧A 全市场 174+ ETF 溢价/停牌/规模与互挂穿透费率；⑧B 当班全部约 16 只焦点股（A/港/美各 4–6 只及周日 6–10 只全池轮换）7 维深研与近 24h 扫雷 |

- **独立黄金 5 路细分清单（单跑黄金轨时使用；亦作为一体化第 ①/⑤/⑥ 路的完整检索验收单）**：

### 黄金专线 1（一体化第 ① 路核心）：全球交易系统与贵金属实盘
- **信源**：COMEX/CME（加 `"official settlement"`）、LBMA（定向 `site:lbma.org.uk`）、上金所 SGE（`Au99.99`/`Au(T+D)` 日终表）、上期所 SHFE（定向 `site:shfe.com.cn` 查 `au`/`ag` 收盘与当日龙虎榜）、ICE、TradingView、**美股 `GLD`/`GDX` 官收白名单（`StockAnalysis` / `Investing` / `SSGA .xlsx` / `VanEck NAV`）**、A/港金矿与金饰股、链上交易所；**禁用 `Barchart` 远月滞后合约快照**。
- **必查清单**：
  - 现货金 `XAU/USD`（含 `spot_gold_ny_close_date` 与高点）、期金 `GC` / 期银 `SI`、LBMA 定盘价、沪金/上海金与龙虎榜席位持仓；
  - 中美黄金 ETF（`GLD`/`IAU` 及国内 `etf_cn`: `518880`/`159937`/`518660`）资金流与份额变动；
  - 中美金矿股（`GDX`/`GDXJ`/`FNV`/`NEM`/`AEM`/`B`/紫金/山东/中金/山金/老铺）及 `GDX/GLD` 比值；
  - CME、上期所、上金所最新保证金与风控公告（严格核验有无“提保令”）。

### 黄金专线 2（一体化第 ⑤ 路核心）：央行、美债汇率、跨资产与宏观信用配管
- **信源**：Federal Reserve、US Treasury（Daily Treasury Rates CSV）、FRED、NY Fed（`SOFR`/`IORB`/`ON RRP`/`SRF`）、Cboe（`VIX_History.csv` & VIX 产品页）、BLS/BEA、ECB、BoE、BOJ、PBOC、CFETS、IMF、BIS，以及 Bloomberg、Reuters、WSJ、FT、CNBC、东方财富、财联社、华尔街见闻、金十数据。
- **必查清单**：美债收益率（2 年/10 年/30 年/10 年 TIPS `DFII10` 与精确 `2Y−FF`）、美元指数（`DXY`）、`USD/CNY`（含 `usd_cny_1630` 与 `cfets_cny_fixing`/`cfets_fixing_date`）、`USD/JPY`、`EUR/USD`；布油/WTI/欧洲 TTF 气、COMEX 期铜、标普/纳指/Cboe 现货 VIX 十日日线表、BTC/`XAUT`/`PAXG`；CME FedWatch 与 G4 央行利率定价、信用利差（`HY OAS`/`CCC OAS`/私募信贷）与银行配管流动性。

### 黄金专线 3（并入一体化第 ① 路）：投行研报、衍生品结构与全球实物市场
- **信源**：高盛、摩根大通、摩根士丹利、美银、花旗、瑞银、德银、法兴、汇丰、澳新、Kitco、WGC、LBMA、白银协会、Metals Focus。
- **必查清单**：
  - 投行最新目标价变动（**严格区分“年末点位 `pt`”、“全年均价 `avg`”、“6–12 月 `horizon`”与“旧稿 `stale`”**，核验样本数与中位）；
  - CFTC 期货持仓周报（`COT`）、COMEX-伦敦期现价差与租赁利率、BCOM/GSCI 调仓与税损流；
  - 中国水贝/菜百/四大行金条/品牌金店最新挂牌价与加工费、印度 MCX 与实物溢价、各国央行最新购售金官方月报/季报。

### 黄金专线 4（并入一体化第 ⑤ 路）：地缘政治、能源、关税与政策排雷日历
- **必查清单**：
  - 霍尔木兹海峡/伊朗/中东/UKMTO 航运实况（**兼顾“局势升级避险”与“停火油价大跌反推实际利率上行”双向路径**）；
  - 俄乌/北约、中美经贸关税与科技出口管制、白宫/国会/财政部/联储官员最新讲话**原文与精确发稿时点**；
  - 未来 7 天宏观数据、央行会议、期权交割与地缘风险排雷日历。

### 黄金专线 5（一体化第 ⑥ 路核心）：金融论坛、社交网络、预测市场与谣言排雷
- **信源**：X（Twitter）、Reddit（`r/Gold`, `r/Silverbugs`, `r/WallStreetBets`, `r/Economics`, `r/investing`）、雪球、东方财富股吧、集思录、淘股吧、连登、微博财经、知乎、Seeking Alpha、ZeroHedge、Polymarket、Kalshi。
- **必查清单**：提炼一线交易员真实逻辑、散户情绪极值与反身性拥挤信号；对社交网络疯传的黄金传闻**逐条溯源官方数据库证伪**，明确区分「确认谣言」与「已获权威媒体证实的真实异动」。

---

## 3. 阶段 2B：1 路统一无情红队复核与演进审计

**强制时机**：必须等阶段 2A 全部 **10 路（一体化主力）** 或全部 **5 路（独立黄金单跑）** `research` 子代理返回完毕后再启动统一红队。

- **输入材料**：阶段 2A 全部汇总证据 + `market_calendar.json` + `master_snapshot.json`（惰性加载：仅命中 5 大更新阈值时才附全量主报告 MD）+ `data_snapshot.json` + `daily/SCORECARD.md` + `daily/CHANGELOG.md`（前 150 行）；一体化班次同步输入 `equity/state/{market_state,multi_asset_channels,etf_universe,deep_dossiers}.json`。
- **核心核查项**：
  1. 逐项精确复算买金四步红绿灯（`real_yield`/`rate_spread`/`vix`/`ny_close`）及 VIX 十日窗口与 `vix_daily_row_checks`；
  2. 核验是否触发 `DFII10` 60 日收盘新高机械砍半硬止损线，或「布油 `< 80` 且 `DFII10 > 2.95%` 站稳 5 日」尾部深熊升级线；
  3. **一体化班次额外必核**：双轨共享宏观基准与多指数优先级秩序（A 股上证 #1）100% 一致、黄金 `Tier 0`/`new_buy_allowed == false` 全载体互斥锁（含交互 K 线诊断）、跨轨统一税费与 QDII 制度红线（`008142`/`008143`、TA 合并 vs 直销分轨、互挂双层穿透费、2027-12-31 LOF 退市、禁推 `968118`、二手存单禁二次转让、交易所公司债 ETF 底层 20% 扣税、中国居民 20% 离岸税与 CRS、`02840.HK` 美国遗产税）、12 大渠道与 174+ ETF 分类、焦点股 7 维实证及三大扩展库同期 `edition_id` 锁；
  4. 逐条对抗旧结论、旧数字、跨源口径冲突、时区归因漏洞与小白三层白话清晰度，核查 `data_caveats` 无内部文件名泄露；
  5. **强制输出四张无情清单**：**【新增】** / **【更新】** / **【修正】**（标明是否改变核心买金建议）/ **【删除】**。

---

## 4. 周末专项版与工作日局部休市叠加协议（由 `market_calendar.json` 动态驱动）

1. **周末专项版（周六 / 周日全市场休市及 `GLOBAL` 全球节假日）**：切勿强找休市当日成交价，将焦点切换为：7×24 链上黄金（`XAUT`/`PAXG`）与 `BTC`、周日中东股市开盘（沙特 `TASI` / 埃及 `EGX30`）、周五盘后期货持仓周报深拆、国内菜百/水贝周末线下客流、美欧周末政经访谈。
2. **工作日局部休市叠加模式（统一先查覆盖至 `2027-06-30` 的 `market_calendar.json`）**：
   - **A 类（美盘休市/半日市提前收，如感恩节、黑五、平安夜、圣诞、马丁路德金日、总统日、耶稣受难日、阵亡将士纪念日、六月节）**：美债/美股/期金报告明标休市或推迟、沿用上一 NY 终盘，半日市支持 VIX `provisional_close`，聚焦伦敦/上金所/上期所实盘与薄量防插针；
   - **B 类（中国休市，如春节连休、清明、劳动节）**：上金所/沪金/在岸汇率与国内金店明标休市（Gate 5 自动放行金店价对齐预警），聚焦 COMEX/伦敦/离岸人民币与海外 ETF，并跟踪节后复市缺口；
   - **C 类（欧/英/日/港/印单边休市或半日市）**：局部标注休市与恢复时刻，其余正常出刊。
3. **重要背景事实备忘**：巴里克黄金美股代码现为 **`B`**（原 `GOLD` 已更名）；**阿联酋已于 2026 年 5 月 1 日正式退出 OPEC 及 OPEC+**（核心自愿减产组为 7 国）；持续监测 `2027-Q1` 香港贵金属中央清算系统启动进展。

---

## 5. 三账本物理分离维护与月度归档规范

为确保面向读者的收敛主刊清爽精炼（且全篇零内部工程词/文件名泄露），同时保留机构级可审计性与公开可证伪承诺，以下三类账本**与报告正文物理分离**：

1. **`daily/CHANGELOG.md`（迭代演进总账）**：
   - 每发一刊，将同期标记 `<!-- GOLD_EDITION_CHANGELOG <edition_id> -->`、本刊完整相对路径（同场修订加 `_r2`）以及阶段 2B 输出的完整【新增 / 更新 / 修正 / 删除】摘要写入微型补丁 `_ledger_patch.json`，调用预授权 `scripts/patch_state_dbs.py --prepend-gold-ledgers` 在文件**最顶部**无损头插（防 300s 超时）；
   - 后续任务继承时若超过 150 行仅读取前 150 行；跨月膨胀时写 `gold/daily/_archive_patch.json` 运行预授权 `scripts/patch_state_dbs.py --archive-gold-ledgers`，将已完成月份条目无损归档至 **`gold/daily/archive/CHANGELOG_YYYY_MM.md`**（归档 + 活跃合并保留全部历史非空行原序）。
2. **`daily/AUDIT_LOG.md`（独立红队质检与法证账本）**：
   - 同样经 `_ledger_patch.json` + `scripts/patch_state_dbs.py --prepend-gold-ledgers` 无损头插同期 `<!-- GOLD_EDITION_REVIEW {...} -->`（含四关 HTTPS 证据与 `forecast_review`），并持续维护「三大信任资产」（拦谣、升级、校准及 `0 / N` 核心影响）与一手官方数据库索引；
   - 跨月膨胀时写 `gold/daily/_archive_patch.json` 运行预授权 `scripts/patch_state_dbs.py --archive-gold-ledgers`，将历史月度记录无损归档至 **`gold/daily/archive/AUDIT_LOG_YYYY_MM.md`**（归档 + 活跃合并保留全部历史非空行原序）；报告正文面向读者，严禁出现内部工程文件名、版本号或「红队」「法证」等内部术语。
3. **`daily/SCORECARD.md`（面向投资者的公开可证伪预测记分卡）**：
   - 每刊写入 `<!-- GOLD_EDITION_SCORECARD <edition_id> -->`，同步回验到期预判（`✅ 兑现` / `⚠️ 部分兑现` / `❌ 证伪` / `⚪ 条件未触发`）并锁定追加新追踪预判，严守**历史记录零篡改宣言**；
   - 全文必须**零内部工程/RSI/脚本文件名词汇**，受 `lint_readability.py` 强制检验。

---

## 6. Step 5：RSI（递归自我复盘与优化）盲审协议与提示词模板

每次研报通过 `lint_readability.py --strict`（一体化班次待 Step 4 权益与三大深研库亦通过 `lint_equity.py --strict`）后，启动 **1 路独立只读盲审 + 三层安全进化闭环**：

### 盲审子代理标准提示词（一体化联合盲审 / 独立黄金盲审）
- **输入**：本刊完整路径（Markdown 源稿与 3 张矢量图参数）、本轮首次 `--strict` 是否一次过及报错列表、`daily/RSI_PLAYBOOK.md` 当前内容、`daily/rsi_metrics.json` 最近 5 条记录（含上期 `next_run_watch` 待验真预判）；一体化班次同步输入权益本刊与 `equity/state/` 账本及三大扩展数据库。
- **任务**：
  1. **上期预判无情回验**：逐条核对上期 `next_run_watch` 与关键区间预判是 `hit` / `partial` / `miss`，指出偏差根因，绝不护短；
  2. **6 维定量打分（每维 1–5 整数，总分 `/30`）**：
     - `data_freshness_and_zero_hallucination`（数据鲜活度、时点标明、`data_caveats` 透明度与休市诚实度）
     - `prior_forecast_calibration`（上期预判回验诚实度与框架演化质量）
     - `plain_language_and_strict_readability`（小白友好三层写作、`DXY`/`COT`/`CDS` 首现白话括注、全篇零内部词与说教口号泄露、加粗 ≤14% 与零裸数字反引号）
     - `visual_layout_and_pagination`（JSON 兼容键名；评判升级为**纯网页视觉清晰度、SVG 零碰撞与小白 3 分钟可读性**：首屏 4 KPI 卡、`.sn-grid` 双栏自适应、图 1/2/3 零碰撞与双端美观度、30 秒结论→钱包实算→硬核证据层次清晰）
     - `research_efficiency_and_source_quality`（一体化 10+1 / 独立 5+1 检索信噪比、高价值/失效信源发现）
     - `engine_and_guardrail_reliability`（脚本与 6 门禁有无暴露确定性小缺陷或漏网词）
  3. **严格分级输出改进动作**：
     - **Tier A（1–3 条高杠杆规则）**：明确应新增进 `daily/RSI_PLAYBOOK.md` 的条款，并点名可合并/淘汰的旧条款（严格保持 **≤180 行**软限 / **200 行**硬上限）；
     - **Tier B（0–1 条确定性工程微调）**：仅当发现确凿、可复现、≤40 行的解析/渲染/门禁加固补丁时提出（可覆盖 `lint_readability.py`/`edition_validation.py`/`chart_input.py` 与 `DAILY_FORMAT_SPEC.md`，**禁止删禁词或放宽门禁**）；否则留空；
     - **Tier C（0–2 条待审批架构提案）**：涉及核心风控策略、红绿灯阈值、`<REPO_ROOT>/AGENTS.md`、`gold/AGENTS.md`、`<REPO_ROOT>/.agents/skills/`、`automations/` 或本地 `sidecar.json` 调整时仅提议，严禁自动改动；
     - **下期必验真清单（`next_run_watch`，2–4 条）**：为下一班次埋下具体可检验的时间点、价位或事件锚。

### Meta-RSI 周期总复盘与纯网页站点单次发布
- 当 `daily/rsi_metrics.json` 中 `len(runs) % 10 == 0` 时，盲审子代理额外对比近 10 刊的 6 维均值趋势、一次过 `--strict` 比率、高频扣分项与预判命中率，输出 1–3 条系统级 Tier C 进化提案呈报用户。
- **终检全绿、K 线刷新与纯网页单次发布**：修正已证实盲审发现并经 `scripts/patch_state_dbs.py --append-gold-rsi`（及一体化班次 `--append-equity-rsi`）无损追加两轨 `rsi_metrics.json`、完成 Tier A/B 落盘后，复跑黄金与权益严格门禁；一体化班次先执行 `python3 <REPO_ROOT>/scripts/fetch_kline_data.py --scope all` 刷新全市场 440+ 静态 K 线分片，再按根契约登记进入 `publish`，用同一班次 token 执行一次 `python3 <REPO_ROOT>/scripts/publish_site.py --edition-token <token>`（通过 S1–S7 严检），随后运行 `edition_run.py complete <token>` 验证 GitHub Pages 部署成功后结束。
