# 两阶段 5+1 调研与红队复核操作手册

本文档固化 `global-investment-research/gold` 的全信源外部调研、无情红队对抗审计、周末专项切换以及 `CHANGELOG.md` / `AUDIT_LOG.md` / `SCORECARD.md` 三账本维护协议。

---

## 1. 安全、防卡壳、官收白/黑名单与防幻觉前提

1. **命令边界、防卡壳红线与三层 RSI 防篡改**：
   - 在定时自动化任务中，主代理严禁运行 `date`、`ls`、`curl` 等未授权 shell 命令，**亦严禁调用 `edit_file`（所有 Markdown/JSON 更新一律使用 `write_file` 全量写盘，彻底防权限拦截）**；
   - 正常发刊阶段（Step 1–4）严禁修改任何 `.py` 脚本与规则文件，仅在 Step 5 RSI 闭环中严格按 Tier A/B/C 权限边界执行受控自进化（永不削弱门禁，永不静默修改 `AGENTS.md` 或核心金融风控红线）；
   - 调用预授权黄金与发布脚本（`gold/build_daily.py`、`gold/build_report.py`、`gold/lint_readability.py` 及全绿后统一执行的 `scripts/publish_site.py`）必须使用绝对路径裸命令（禁加 `cd &&` 前缀，严禁与股研 Chrome PDF 构建并发）；在 `07:30`/`18:00` 一体化单会话定时任务（`daily-global-investment-research` / `daily-global-investment-research-evening`）中，本手册覆盖的黄金信源与红队核查融入共享 6+1 调研红队，并在第 3 步先完成黄金 SSOT 落盘，随后由第 4 步股研模块以 0 分钟零滞后直读；结合系统本地时间（`+08:00`）与外置日历 `market_calendar.json` 判定工作日/周末/局部休市叠加模式与早/晚刊时段；常规班次执行**惰性主报告加载**（仅读 `master_snapshot.json` 核验 5 大触发条件，命中时才全量读取主报告 MD）；同场修订加 `_r2` 后缀严禁覆写既有归档。
2. **联网边界**：所有外部实时行情、政策原文、研报与舆情调研，统一交由 `research` 子代理使用中英双语 `search_web` 完成。
3. **反幻觉铁律**：
   - 每条新增报价或事件必须附 **信源 + 精确时点**；
   - 休市或查不到当日新报价时，必须如实写「休市 / 沿用上一终盘（标注时点）」，严禁外推、补齐或估算；
   - 严格区分交易时间戳，严禁把不同时点的国内外报价差误作“国内溢价”（溢价必须严格按同一分钟时间戳换算），严禁盘后讲话倒推归因已收盘盘口。
4. **Tier C #2 已正式固化：官收信源白/黑名单、定向补录词与北美冬/夏令时硬校验**：
   - **美股 `GLD`/`GDX` 官收白名单**：强制交叉校验 **`StockAnalysis` / `Investing` 历史收盘表 + `VanEck` 官方 NAV**，严禁误采盘中快照或开盘价充作官方收盘价；COMEX 期金/期银/期铜检索直加 `"official settlement"`；
   - **远月滞后源黑名单**：**严禁采纳 `Barchart` 远月滞后合约快照**（如 `GCG27` 滞后异常值），防止跨合约串位污染；
   - **定向官方补录检索词**：补录滞后官方表时，检索词必须强制包含 **`site:shfe.com.cn`**（上期所席位龙虎榜与合约分账）、**`site:lbma.org.uk`**（伦敦金银定盘官方表）及 **`"基金份额" "518880"`**（国内黄金 ETF 份额流）；国内夜盘涨跌必须以上金所/上期所**前一日官方日终清算表**为分母（严禁串用前日旧收或旧金店牌价）；
   - **北美冬/夏令时硬校验（动态对齐 `market_calendar.json`）**：当前北美冬令时（`2026-11-01` 至 `2027-03-13`）严格执行 **`EST = BJT - 13h`、`CST = BJT - 14h`**（COMEX `13:30 EST` 官结精确重合 `02:30 BJT`、NY 现货 `17:00 EST` 终盘 = `06:00 BJT`、美股 `16:00 EST` 收盘 = `05:00 BJT`、感恩节 CME `17:00 CST` 复盘 = 周五 `07:00 BJT`）；自 **`2027-03-14`** 起依据 `market_calendar.json` 的 `dst_schedule` 自动切入夏令时（`EDT = BJT - 12h`、`CDT = BJT - 13h`、COMEX 官结 `01:30 BJT`、NY 现货收盘 `05:00 BJT`）。

---

## 2. 阶段 2A：并行启动 5 路专项 `research` 子代理

> **一体化单会话 6+1 映射**：在 `07:30` / `18:00` 一体化定时任务中，请参照单仓库根宪章 `<REPO_ROOT>/AGENTS.md`（第 3 节 Step 2A）一次并发启动 **共享 6 路 `research` 子代理**——本节黄金 5 路信源清单归并至一体化第 1 路（黄金与贵金属专线）、第 5 路（跨资产宏观/油铜汇率/四大央行与地缘专线）及第 6 路（社区情绪/预测市场/谣言证伪专线），与第 2–4 路（A/港/美股专线）同轮并发，彻底消除重复抓取。

必须**同一轮并行发起全部 5 路**（独立黄金班次；一体化班次为共享 6 路），通过中英双语交叉检索无死角覆盖七大信源（搜索引擎、金融门户、金融网站、金融系统、交易系统、金融论坛、社交网络）：

### 子代理 1：全球交易系统与跨资产实盘
- **信源**：COMEX/CME（加 `"official settlement"`）、LBMA（定向 `site:lbma.org.uk`）、上金所 SGE（`Au99.99`/`Au(T+D)` 日终表）、上期所 SHFE（定向 `site:shfe.com.cn` 查 `au`/`ag` 收盘与当日龙虎榜）、ICE、TradingView、**美股 `GLD`/`GDX` 官收白名单（`StockAnalysis` / `Investing` / `VanEck NAV`）**、美/A/港股与链上交易所；**黑名单：严禁采纳 `Barchart` 远月滞后合约快照**。
- **必查清单**：
  - 现货金 `XAU/USD`、期金 `GC` / 期银 `SI`、LBMA 定盘价、沪金/上海金与龙虎榜席位持仓；
  - 中美黄金 ETF（`GLD`/`IAU`/`518880`/`159937`/`518660`）资金流与份额变动；
  - 中美金矿股（`GDX`/`GDXJ`/`FNV`/`NEM`/`AEM`/`B`/紫金/山东/中金/山金/老铺）及 `GDX/GLD` 比值；
  - 美债收益率（2Y/10Y/30Y/10Y TIPS `DFII10` 与精确 `2Y−FF` 利差）、`DXY`、`USD/CNY`、`USD/JPY`、`EUR/USD`；
  - 布油/WTI/欧洲 TTF 气、标普/纳指/VIX/核心科技权重、BTC/`XAUT`/`PAXG`；
  - CME、上期所、上金所最新保证金与风控公告（严格核验有无“提保令”）。

### 子代理 2：金融门户、央行与金融系统、宏观信用配管
- **信源**：Federal Reserve、US Treasury（Debt to the Penny）、FRED、NY Fed（`SOFR`/`IORB`/`ON RRP`/`SRF`）、BLS/BEA（含生产率与 ULC）、ECB、BoE、BOJ、PBOC、CFETS、海关总署、IMF、BIS，以及 Bloomberg、Reuters、WSJ、FT、CNBC、MarketWatch、Yahoo Finance、Investing.com、TradingEconomics、东方财富、财联社、新浪财经、华尔街见闻、金十数据、同花顺、格隆汇。
- **必查清单**：CME FedWatch 与欧/英/日央行利率定价、通胀/PMI/就业、信用利差（`HY OAS`/`CDX IG`/`CCC OAS`/私募信贷赎回）、银行配管流动性、法（OAT）/日（JGB）/英/美主权债动向。

### 子代理 3：投行研报、金融网站、衍生品结构与全球实物市场
- **信源**：高盛、摩根大通、摩根士丹利、美银、花旗、瑞银、德银、法兴、汇丰、澳新、Kitco、WGC、LBMA、白银协会、Metals Focus。
- **必查清单**：
  - 投行最新目标价变动（**严格区分“年末点位”与“全年均价”**，核验分析师所属机构现状）；
  - CFTC COT 持仓、`GLD`/COMEX 期权偏度与 Gamma 墙、COMEX-伦敦期现价差与租赁利率、BCOM/GSCI 调仓与税损流；
  - 中国水贝/菜百/品牌金店最新挂牌价与加工费、印度 MCX 与实物溢价、各国央行最新购售金官方月报/季报。

### 子代理 4：地缘政治、能源、关税与政策排雷日历
- **必查清单**：
  - 霍尔木兹海峡/伊朗/中东/UKMTO 航运实况（**必须兼顾“局势升级避险”与“停火油价大跌反推实际利率上行”双向路径**）；
  - 俄乌/北约、中美经贸关税与科技出口管制、白宫/国会（债务上限与财政博弈）/财政部/联储官员最新讲话**原文与精确发稿时点**；
  - 未来 7 天宏观数据、央行会议、期权交割与地缘风险排雷日历。

### 子代理 5：金融论坛、社交网络、预测市场与谣言排雷
- **信源**：X（Twitter）宏观与贵金属大 V、Reddit（`r/Gold`, `r/Silverbugs`, `r/WallStreetBets`, `r/Economics`, `r/investing`）、雪球、东方财富股吧、集思录、淘股吧、华尔街见闻/金十评论区、微博财经热搜、知乎、Seeking Alpha、ZeroHedge、Substack、ForexFactory、Polymarket、Kalshi。
- **必查清单**：提炼一线交易员真实逻辑、散户情绪极值与反身性拥挤信号；对社交网络疯传的黄金传闻**逐条溯源官方数据库证伪**，明确区分「确认谣言」与「已获权威媒体证实的真实异动」。

---

## 3. 阶段 2B：第 6 路无情红队复核与演进审计

**强制时机**：必须等阶段 2A 全部 5 路（独立黄金）或全部 6 路（一体化单会话）`research` 子代理返回完毕后再启动统一红队。

> **一体化单会话 6+1 映射**：在 `07:30` / `18:00` 一体化定时任务中，须参照单仓库根宪章 `<REPO_ROOT>/AGENTS.md`（第 3 节 Step 2B）启动 **1 路统一红队**，除完成下方黄金全部核查项外，同步交叉审计双轨共享宏观基准（现货金/美债/`DFII10`/DXY/`brent_settle_usd`/`cfets_cny_fixing`/VIX/COMEX 铜）100% 一致、黄金 `Tier 0`/`new_buy_allowed == false` 全载体互斥锁与股研 6 大硬伤拦截。

- **输入材料**：前 5 路全部汇总证据 + `market_calendar.json` + `master_snapshot.json`（惰性加载：仅命中 5 大更新阈值时才附全量主报告 MD）+ `data_snapshot.json` + `daily/SCORECARD.md` + `daily/CHANGELOG.md`（前 150 行）。
- **核心核查项**：
  1. 逐项校验买金四步红绿灯（`Tier 0–3`）是否发生过关/失守变化；
  2. 核验是否触发 `DFII10` 60 日收盘新高机械砍半硬止损线，或「布油 `< 80` 且 `DFII10 > 2.95%` 站稳 5 日」尾部深熊升级线；
  3. 逐条对抗旧结论、旧数字、跨源口径冲突与时区归因漏洞，检出任何需修订的误差或已过期风险；
  4. **强制输出四张无情清单**：
     - **【新增】**：真正改变认知或新增的关键事实/风险/催化；
     - **【更新】**：实时报价、利率定价、投行目标价、红绿灯读数更新；
     - **【修正】**：纠偏过往报告中的事实、算术、口径或归因误差（并标明是否改变核心买金建议）；
     - **【删除】**：已证伪谣言、已落地失效的旧预警或过期噪音。

---

## 4. 周末专项版与工作日局部休市叠加协议（由 `market_calendar.json` 动态驱动）

1. **周末专项版（周六 / 周日全市场休市及 `GLOBAL` 全球节假日）**：切勿强找休市当日成交价，将 5 路焦点无缝切换为：7×24 链上黄金（`XAUT`/`PAXG`）与 `BTC`、周日中东股市开盘（沙特 `TASI` / 埃及 `EGX30`）、周五盘后 `CFTC COT` 周度持仓深拆、国内菜百/水贝周末线下客流、美欧周末政经电视访谈（CBS *Face the Nation* / NBC *Meet the Press*）。
2. **工作日局部休市叠加模式（不再硬编码日期，统一先查 `market_calendar.json` 的 `calendar_overrides` 与 `dst_schedule`）**：
   - **A 类（美盘休市/提前收，如感恩节、黑五、平安夜、圣诞、马丁路德金日、总统日）**：美债/美股/CFTC 明标休市或推迟、沿用上一 NY 终盘，聚焦伦敦/上金所/上期所实盘与薄量防插针；
   - **B 类（中国休市，如 2027/02/05–02/14 春节 10 天连休）**：上金所/沪金/在岸汇率明标休市，聚焦 COMEX/伦敦/离岸人民币与海外 ETF，并跟踪节后复市缺口；
   - **C 类（欧/英/日/港/印单边休市或半日市）**：局部标注休市与恢复时刻（如跨年夜港/英半日、英国节礼日、印度共和国日），其余正常编译。
3. **重要背景事实备忘**：巴里克黄金美股代码现为 **`B`**（原 `GOLD` 已更名）；**阿联酋已于 2026 年 5 月 1 日正式退出 OPEC 及 OPEC+**（核心自愿减产组为 7 国）；持续监测 `2027-Q1` 香港贵金属中央清算系统启动进展。

---

## 5. 三账本物理分离维护规范

为确保面向普通读者的报告正文清爽易读，同时保留机构级可审计性与公开可证伪承诺，以下三类账本**与报告正文物理分离**：

1. **`daily/CHANGELOG.md`（迭代演进总账）**：
   - 每发一刊，在文件**最顶部**追加本刊条目，写明本刊完整相对路径（如 `daily/YYYY-MM-DD_1800_晚报_黄金深度研报.md`，同场修订加 `_r2`）以及阶段 2B 输出的完整【新增 / 更新 / 修正 / 删除】摘要；
   - 后续任务继承时若超过 150 行仅读取前 150 行。
2. **`daily/AUDIT_LOG.md`（独立红队质检与法证账本）**：
   - 维护「三大信任资产」累计台账（同步更新 `data_snapshot.json` 的 `trust_assets`）：
     - 资产一：拦下的全网流行误区、谣言与买金深坑清单；
     - 资产二：核心模型与风控策略升级清单；
     - 资产三：公开透明的细节校准清单（每条明标「是否改变核心买金结论」，汇总 `0 / N`）；
   - 附一手官方数据库索引表；报告正文仅在 Layer 3 末尾通过 3 行 `DAILY_TRUST_BAR` 指向本账本。
3. **`daily/SCORECARD.md`（面向普通投资者的公开可证伪预测记分卡）**：
   - 每刊发刊同步回验到期预判（`✅ 兑现` / `⚠️ 部分兑现` / `❌ 证伪`）并锁定追加新追踪预判，严守**历史记录零篡改宣言**；
   - 全文必须**零内部工程/RSI 词汇**（绝不出现 `Subagent`/`RSI`/`Tier A/B/C`/`V2.2` 等），受 `lint_readability.py` 强制检验。

---

## 6. Step 5：RSI（递归自我复盘与优化）盲审协议与提示词模板

每次研报编译并通过 `lint_readability.py --strict` 后，立即执行 **1 路独立只读盲审 + 三层安全进化闭环**（主干交付优先，严禁因过度优化延误发刊，严禁削弱任何门禁）。

### 盲审子代理（`RSI Self-Review & Improvement Auditor`）标准提示词
- **输入**：本刊完整路径（MD + PDF 视觉抽检发现）、本轮首次 `--strict` 是否一次过及报错列表、`daily/RSI_PLAYBOOK.md` 当前内容、`daily/rsi_metrics.json` 最近 5 条记录（含上期 `next_run_watch` 待验真预判）。
- **任务**：
  1. **上期预判无情回验**：逐条核对上期 `next_run_watch` 与关键区间预判是 `hit` / `partial` / `miss`，指出偏差根因，绝不护短；
  2. **6 维定量打分（每维 1–5 整数，总分 `/30`）**：
     - `data_freshness_and_zero_hallucination`（数据鲜活度、时点标明、休市与未出项透明度）
     - `prior_forecast_calibration`（上期预判回验诚实度与框架演化质量）
     - `plain_language_and_strict_readability`（Layer 0–1 一次过门禁率、零黑话与家庭理财医生冷静语调）
     - `visual_layout_and_pagination`（PDF 实际页数 10–13 页、无孤页/无图字碰撞/表格美观度）
     - `research_efficiency_and_source_quality`（5+1 检索信噪比、高价值/失效信源发现）
     - `engine_and_guardrail_reliability`（脚本与门禁有无暴露确定性小缺陷或漏网词）
  3. **严格分级输出改进动作**：
     - **Tier A（1–3 条高杠杆规则）**：明确应新增进 `daily/RSI_PLAYBOOK.md` 的条款，并点名可合并/淘汰的旧条款（确保总行数始终 ≤180 行）；
     - **Tier B（0–1 条确定性工程微调）**：仅当发现确凿、可复现、≤40 行的渲染/解析/门禁加固补丁时提出（**禁止删禁词或放宽门禁**）；否则留空；
     - **Tier C（0–2 条待审批架构提案）**：涉及核心风控策略、红绿灯阈值、`<REPO_ROOT>/AGENTS.md`、`<REPO_ROOT>/.agents/skills/`、`automations/sidecars/` 或本地 `sidecar.json` 调整时仅提议，严禁自动改动；
     - **下期必验真清单（`next_run_watch`，2–4 条）**：为下一班次埋下具体可检验的时间点、价位或事件锚。

### Meta-RSI 周期总复盘（每累计满 10 刊自动触发）
- 当 `daily/rsi_metrics.json` 中 `len(runs) % 10 == 0` 时，盲审子代理额外对比近 10 刊的 6 维均值趋势、一次过 `--strict` 比率、高频扣分项与预判命中率，输出 1–3 条系统级 Tier C 进化提案供用户在下一次交互中集中审批。
- **终检全绿与站点单次发布**：Tier A/B 落盘并复跑 `python3 <REPO_ROOT>/gold/lint_readability.py --strict <REPO_ROOT>/gold/daily/<本刊黄金文件名>.md`（一体化单会话流程 `daily-global-investment-research` / `daily-global-investment-research-evening` 中同步确认第 4 步股研 `python3 <REPO_ROOT>/equity/lint_equity.py --strict` 及统一 RSI 全绿）后，统一运行一次 `python3 <REPO_ROOT>/scripts/publish_site.py` 构建静态门户、通过内部严格站点门禁（`python3 <REPO_ROOT>/scripts/lint_site.py _site --strict`）并推送至 GitHub Pages 与滚动 Release。
