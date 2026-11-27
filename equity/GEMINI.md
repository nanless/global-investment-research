# 投研报告永久写作与交付宪法（global-investment-research/equity）

本工作区根目录 `<REPO_ROOT>/equity` **永久冻结不改名**，作为顶层宪章 [`../AGENTS.md`](../AGENTS.md) 一体化**三班次流水线（07:30 早报 / 11:30 午报 / 18:00 晚报）**的 **Step 4** 紧接黄金 SSOT 严检后运行，采用**纯网页静态门户直读唯一交付（零离线二进制文档附件）**。所有源稿（三市早/午/晚主刊与守望刊、三份旗舰手册、`report_meta_*.json`、`state/{market_state,multi_asset_channels,etf_universe,deep_dossiers,policy_calendar}.json`、`state/klines/*.json`、`daily/{INDEX,CHANGELOG,SCORECARD}.md`）必须无条件遵守本宪法。

> **单一权威索引（零重复、零漂移）**：一切实时利率、收益率、限购金额、溢价率、规模与点位均以 `../gold/data_snapshot.json` 与 `state/*.json` 为唯一真相源，本宪法严禁硬编码易过时实盘数值。顶层三班次编排、多指数标准、K 线管线与 12 大渠道 MECE 目录见 [`../AGENTS.md`](../AGENTS.md)；纯网页量化排版、7 维大盘与个股深研标准见 [`DAILY_REPORT_SPEC.md`](DAILY_REPORT_SPEC.md)；双账户与 12 大多元渠道（含 QDII 场内外分轨）税费/权限唯一详表见 [`dual_account_tax_and_rules.md`](../.agents/skills/equity-research-editorial-qa/references/dual_account_tax_and_rules.md)；10 项发前门禁见 [`pre_flight_10_gates.md`](../.agents/skills/equity-research-editorial-qa/references/pre_flight_10_gates.md)；21 张矢量图 Schema 与休市滚存 SOP 见 `../.agents/skills/equity-report-publishing/references/`。

---

## 0. 历史旧指令冲突静默裁决（最高优先级）

若任何调用 Prompt 残留历史旧体例，本文件与 `DAILY_REPORT_SPEC.md` 具有最高优先级，须直接静默转译：
- 版本号（`V9.x/V10.x`）、子代理路数、红队勘误表或 RSI 明细 → 前台 100% 隐藏，隔离写入 `state/audit_ledger.md` 与 `state/RSI_*`；前台仅留 ≤3 件核心大事与 ≤2 条面向读者的外部谣言辟谣。
- `Tier 0–3`、混用 `✅`、伪精确小数概率或说教口号（`1 分钟定心丸`/`小白词典`/`直接抄`/`蠢事`/`保命铁律`） → 转为平等温和导读、四灯（**🛡️ 红灯防守期 / 🟡 黄灯试探期 / 🟢 绿灯主攻期 / 🚀 顺风加码期**）、四色锁仓（`🟢 当下底座` / `🔵 🔒未来主攻` / `🟡 分歧观察` / `🔴 高危回避`）与完整 10 点进度条（四行精确求和 = 10，禁偷懒单边如 `7/10`）。
- 薄壳轻刊、单指数播报、工作日粘贴全量静态大表、漏报 12 渠道/ETF 雷达或模板化个股点评 → 全面执行三市**全时段完整主刊（`main`，≥2 图）**与休市/半日市升级版 **`holiday_watch`（≥1 图）**，落实**多指数优先级播报（A 股必以上证指数 #1 领衔）**，内嵌 12 渠道精选、本市重点 ETF 与 4–6 只焦点股 7 维实证拆解。

---

## 1. 冷启动五步序与跨项目黄金 SSOT 校验

0. 读 `state/RSI_PLAYBOOK.md`（≤180 行）与 `state/rsi_metrics.json` 最近 5 条记录，继承检索词、避坑清单与 `next_run_watch`。
1. 运行 `python3 equity/lint_equity.py --plan <edition_id>` 获取当班刊型（支持 `0730`/`1130`/`1800` 三班次）；读 `state/market_state.json`、三大扩展数据库（`multi_asset_channels.json`、`etf_universe.json`、`deep_dossiers.json`）与只读校验 `../gold/data_snapshot.json`：
   - **同刊期与单向时间窗**：两轨同一 `edition_id`，黄金截点早于或同分钟于权益（差值 ≤6 小时），两轨截点与日报 `chart_live.as_of_full` 各须落在所标班次 **`[-5 分钟, +6 小时]`** 单向窗口内（早班 `07:25–13:30` / 午班 `11:25–17:30` / 晚班 `17:55–次日 00:00` CST）；假日无盘中观测时允许双轨 `brent_live_usd` 与 `vix_live` 同口径留空（`07:30` 与 `11:30` 处于美东非 VIX 窗口，`vix_live` 均留空）；
   - **黄金红灯互斥锁（Gate C2 全栈扫描）**：黄金红灯时，全载体（正文、封面 JSON、`state/market_state.json`【Gate C2 同步扫描】、三大扩展库、交互 K 线技术诊断条、全站网页与 SVG）严禁新买/补齐黄金指令或将黄金/金矿标的标绿；`etf_universe.json` 强制双向绑定 **`asset_class == "gold" <=> gold_locked=True`**；
   - **三层门户架构、状态规范键、多指数矩阵与核心池**：门户与数据底座统一落实三层信息架构——**Layer 1 7 颗宏观天气胶囊**（含中美 10 年期利差 + 比特币/加密只读风险晴雨表，严守 **`银发〔2026〕42号`** 合规防火墙、禁交易导流）；**Layer 2 对称 `3×2` 六市场驾驶舱**（**5 大核心市场**：A 股【上证 #1】· 港股【中国离岸折价腿，非海外分散】· 美股 · **债券/现金与中美利率 `rates_bonds_core`** · 黄金【独立】 + **1 个统一非美海外卫星 `non_us_global_satellite`**【日/欧/台韩/印】，同时正文日报严格封顶四轨 `07:30/11:30/18:00`）；**Layer 3 四角色层 12 大执行渠道**（渠道 08 显式定名「**QDII 跨境基金（场内溢价·直销与支付宝限购）、香港互认与理财通**」，10 元起非高净值友好）+ **181+ 重点 ETF**（正交 `asset_class × region` 枚举）+ **480+ 交互 K 线**。坚持无日期后缀规范键（`margin_balance_100m`/`pboc_total_net_100m`/`hkma_agg_bal_hkd_100m`）、同步每市严格升序的 `index_matrix`、27 对 A/H 基准与纯读者中文 `data_caveats`；核心龙头池弹性 65–85 只/市（基准 A 76 / 港 75 / 美 80 = 231 只，实时总数以 `market_state.json` 为准）；三市危机总熔断三阀统一锁定 `VIX 连 2 日 > 30` / 日元 3 日急升 `>3%` / 10 年期美债 `>5.25%`（港股叠加金管局总结余 `<400 亿港元`），跨三市 AI/半导体同源科技敞口合并 ≤ 家庭总资产 20%、单股 ≤ 8%。
2. 读 `daily/INDEX.md`（前 60 行）核对总水位与 `_r2` 防覆写状态（跨午夜切割线为北京时间 `05:30`）。
3. 读 `daily/SCORECARD.md` 客观回填到期预判（`✅ 兑现` / `⚠️ 部分兑现` / `❌ 证伪`；新登检验日禁落周末；**仅登可证伪投资预判，严禁混入后台数据回补工单**；若前刊勘误须联动更新 `SCORECARD.md` 与 `INDEX.md`）。
4. 仅命中旗舰手册 5 条硬触发阈值（见 `DAILY_REPORT_SPEC.md` §五）时，全量读取并同步 `{market}_market_report_{slug,latest}.md` 与 `report_meta_*.json`。

---

## 2. 权益专属内容深度、多指数秩序、QDII 制度铁律与防错硬红线

1. **多指数优先级标准、机构级内容必含项与反重复读**：
   - **严禁单指数播报（对齐 Layer 2 六市场与 68 只核心基准）**：A 股必以**上证指数（`000001`）#1 领衔**，依次沪深300/深证成指/中证A500/上证50/创业板指/科创50/中证500/中证1000/中证红利/北证50/中证转债；港股（定位**中国离岸折价腿，非海外分散**）恒生指数→恒生科技→恒生国企→恒生综合（`HSCI`）+ AH 溢价（`HSAHP`）；美股标普500→纳斯达克综合→纳斯达克100→道琼斯→罗素2000→标普500等权→费城半导体→VIX 恐慌指数；并同步追踪 **债券/现金与中美利率 `rates_bonds_core`**（中债 2Y/10Y/30Y、美债与中美 10Y 利差）与 **非美海外卫星 `non_us_global_satellite`**（日/欧/台韩/印 9 只非美核心指数）；比特币/加密仅作 Layer 1 宏观天气只读观察（严守 `银发〔2026〕42号` 合规防火墙，严禁买卖建议或渠道导流）；
   - 每篇主刊落实小白三层结构（30 秒白话结论 → 10 万/1 万元双刻度钱包实算与三步怎么买 → 7 维硬核证据）与**视觉图表优先原则**（除标准市图外嵌入 1–2 张通用 `<!-- DAILY_VISUAL {...} -->` 零碰撞矢量信息图：`waterfall`/`bar_compare`/`anchor_range`/`flow_chain`，杜绝死板纯文字墙），并强制配齐：**6 维体检拆解分项**、**1 句利率→汇率→信用→大宗→股票风险溢价（ERP）跨资产传导链**、**重要一手官源政策/时政/监管/财报/地缘要闻全量覆盖**（彻底取消旧 1–2 条上限：同步写入 `state/policy_calendar.json`，门户首页 `#sec-policy-calendar` 精选展示 6–9 条【`home_featured: true`】，单市场日报页 `#sec-market-news` 按 `affected_markets` 无上限全量呈现；A 股政策市主线、港股 A+美双轨催化、美股联储/财政/关税地缘，重磅要闻走完 5 环传导链）与 **4 列未来 7–14 天全北京时间财经与政策日历表**（纯中文级别徽章如重磅/重要，零裸 `P0`/`P1`，严守黄金红灯锁）、**未来 48 小时上行/下行双向催化剧本**、**10 万/1 万元情景回撤压力实算**、**完整四情景 10 点概率拆分与理由**及 **4–6 只焦点股 × 5 项硬核锚点**（按现价实算实际股息率 `年化分红 ÷ 现价` 与同口径市盈率，与 `deep_dossiers.json` 100% 同步）；
   - **零后台审计腔与反重复读**：标题与导语禁写「旧缺口清零」「挂账核销成绩单」类运维话术；开篇导语 ≤200 字（推荐 ≤160 字），同一核心数字提及 ≤3 次；升级版 3 层术语标准将 `DXY`/`COT`/`CDS`/`ERP`/`IRR` 移出裸用名单（首现配简短白话括注或交由站内术语浮窗），正文避免裸写 `ON RRP`/`IOPV`/`数字+bp`/`熊平`/`¢` 及裸期限 `2Y/3Y/5Y/10Y/20Y/30Y`。
2. **QDII 场内外分轨制度铁律、代码费率与税费高危陷阱（详表见 `dual_account_tax_and_rules.md`）**：
   - **QDII 五大永久制度铁律（一切实时限额/溢价/规模均以 `state/*.json` 为准）**：① **TA 账户全网合并 vs 直销/代销双轨**：场外“单日单个基金账户”按身份证跨三方平台（支付宝/天天/微信/银行）合并清算，跨平台重复买同一代码将在 T+1 拒单；合法扩容仅靠不同份额分计（`A`/`C`/`I`/`USD`）、公募官方明确区分直销与代销限额的官方 App 或跨基金公司独立 SAFE 额度池；② **美元现汇仍占同公司 SAFE 额度**，严禁为抢限购专门购汇承兑点差；③ **跨境互挂/互通 ETF 仍占 SAFE 额度且具双层费**（中日/中新/沪深港沙特/中巴），必须透明披露 **穿透总年费（境内显性费 + 境外底层 TER）** 并对照物理直投单层费产品；④ **2026-08-07 交易所 LOF 退市新规**：指定 QDII-LOF 与商品期货 LOF 最晚于 **`2027-12-31`** 终止上市（转场外按净值赎回，不等于清盘，但**场内高溢价 100% 永久清零**）；⑤ **溢价-排队盈亏平衡与代码核验**：按 `机会成本 ≈ 0.5 × (N / 250) × r_excess` 警示 >2%–3% 溢价追高成本，且严禁臆测场外联接代码（必须核验无联接品种及币种代码差异）；
   - **可转债 ETF 跨库费率护栏**：全市场 **`511380` 综合费率 0.20%/年**，投资级 AA+ **`511180` 综合费率 0.30%/年**，严禁跨库混写；
   - **A 股低费与防混淆**：首选 0.20% 宽基/现金流/红利/银行 ETF（`510300`/`563360`/`159201`/`563020`/`515180`/`516310`）；严防把 `561910`（电池）误作银行、`515080`（中证红利）误作红利质量（`159758`）或推荐微型 `158008`/`020035`；
   - **3 项已证伪误导硬拦截**：① 严禁写非 QDII 港股通 ETF（`159545`/`159792`）“零溢价”；② 严禁笼统写“红筹股一律 28% 税”；③ 严禁写“可转债末日二级卖出免 20% 个人税”；
   - **港股/跨境/12 大渠道必守红线**：区分非 QDII（`159545`/`159792`/`520900`/`159570`/`513750`）vs QDII（`513530`/`513950`/`513970`/`513260`/`513010`），不把 `520830`/`159611`/`03119`/`03141` 误作港股红利；离岸恒科用 `03067` 替代 `03033`；严禁列入已退市恒生银行 `00011`（用渣打 `02888`）与停申 MRF `968118`；严守 `008142`/`008143` 2026 费改统一口径、二手大额存单禁二次转让与提前支取实亏、交易所公司债 ETF 底层 20% 税区别于银行间 `511360`、`02840.HK` 美国遗产税改选 `IGLN.L`/`03081.HK` 及中国居民 20% 境外所得与 CRS 合规。
3. **物理学一致、`CHART_A2` 符号、时区与读者可见禁令**：
   - 全部读者可见文档、三大扩展 JSON、K 线分片 JSON、SVG 与 `INDEX`/`CHANGELOG`/`SCORECARD` **零**内部工程词、版本号、脚本/快照/补丁/RSI 文件名（含 `fetch_kline_data.py`）与说教口号；反引号仅用于证券/期货/指数代码；配置表精确求和 100%；27 对 A/H 同股 PE 与股息率满足物理学一致；`🔵 🔒未来主攻` 解锁锚严格低于现价；下单前自检卡 100% 正向“全选是”且含 ≥2 条当期特化核对项；
   - **`CHART_A2` 期货贴水正负号铁律**：`a2.futures` 年化贴水 `ann_disc` 正数代表折价/贴水、负数代表升水，严禁贴水填负号；
   - **时区与涨跌**：北京时间为主（美东轻附括号），**07:30 美股早刊全年严禁提前写盘后终盘**（由当日 **11:30 午刊或 18:00 晚刊**封账；11:30 CST 已过冬令时 09:00 / 夏令时 08:00 美股盘后终盘）；涨跌一律写“上涨/下跌/由跌转涨”配正负号（禁 `收红/收绿/翻红/翻绿`）；每只美股配中文名 + ≤10 字白话业务标签。

---

## 3. 分级写盘、三库原子补丁、K 线刷新、门禁与受控 RSI 闭环

- **分级写盘、增长账本、月初滚存与三库原子合并（防 300s 超时）**：无人值守常规禁 `edit_file`（**仅允许用 `edit_file` 定点修正 `equity/state/_edition_patch.json` 校验报错**），严禁单轮并行打包 >2 个大型 `write_file`。中小源稿与轻量账簿（日报、`INDEX`/`CHANGELOG`/`SCORECARD`、`state/market_state.json`、`state/RSI_PLAYBOOK.md`）用 `write_file` 全量写盘；所有持续增长大文件与月初旗舰滚存一律走预授权 `scripts/patch_state_dbs.py` 原子命令：
  - **三大扩展大 JSON 与 `state/policy_calendar.json`**：写紧凑嵌套补丁 `equity/state/_edition_patch.json`（可选 `policy_calendar` 键同步 14–30 天前瞻财经/政策日历，仅允许 `top_level_updates`、`policy_briefs_replace`、`events_upsert`、`events_remove` 四键）运行 `--apply` 原子合并（强制同步顶层 `edition_id`、校验 4 角色层 12 大执行渠道【渠道 08 显式定名「QDII 跨境基金（场内溢价·直销与支付宝限购）、香港互认与理财通」，10 元起非高净值友好】/ **181+ ETF 正交 `asset_class × region` 枚举与 `asset_class == "gold" <=> gold_locked=True` 双向锁** / 231 股完整度、黄金红灯锁与跨库费率一致性）；只读查库用 `--inspect <target>`（`channels`/`channel:<id>`/`etf:<code>`/`stock:<key>`/`stale-dossiers`/`ah-benchmarks`/`etf-freshness`/`policy-calendar`）；
  - **增长账本、RSI 与月初跨月滚存**：`state/audit_ledger.md` 写 3 键 `equity/state/_audit_patch.json` 走 `--prepend-equity-audit` 无损头插；`state/rsi_metrics.json` 写裸单条运行对象 `equity/state/_rsi_patch.json` 走 `--append-equity-rsi` 无损追加；月初切换 `period_slug` 写 `equity/state/_rollover_patch.json` 走 `--rollover-equity-month` 原子克隆三旗舰与 `_latest.md` 并更新 `report_meta_*.json`；
  - **兄弟字段扫清、A/H 孪生股同步与诚实单股 `updated_at`**：修改任一标的时须同步检查其关联兄弟字段及 A/H 双地孪生股口径（凡 QDII 限额/溢价变动必同步 `multi_asset_channels.qdii_channel_comparison`、`etf_universe.key_2026_rules` 及同系纳指等兄弟 ETF）；仅更新本期实际核查标的的 `updated_at`，**严禁批量刷写未核查股票日期**。
- **独立门禁、交互 K 线抓取、受控三层 RSI 闭环与本机伴随只读监测**：运行 `python3 <REPO_ROOT>/equity/lint_equity.py --strict`（Gate 0–5 / Gate 3B / 21 图含 `CHART_A2` 符号与零碰撞 / 三库含 `asset_class × region` 正交枚举与 `asset_class == "gold" <=> gold_locked=True` / 跨项目黄金 C1–C3 含 Gate C2 扫描 `market_state.json`，必须 `0 errors, 0 warnings`）→ Step 5 启动 1 路独立只读盲审按 6 维 `/30` 打分并闭环登记 `review_closure`（Tier A 经 `--append-equity-rsi` 无损追加 `state/rsi_metrics.json` 并更新 `state/RSI_PLAYBOOK.md` ≤180 行；Tier B 单次 ≤1 处 ≤40 行确定性修 Bug 且必过 `--strict` + 静态站 + 单测，败则回滚；Tier C 宪法/技能/权限仅提案）→ 复跑双轨严检并运行 `python3 <REPO_ROOT>/scripts/fetch_kline_data.py --scope all` 刷新全市场 **480+ 标的**（含 **68 只核心基准**：9 只非美指数、中债 2Y/10Y/30Y 收益率、中证 REITs `932047`/`932006`、港股 `HSCI`/`HSAHP` 与 `EURUSD`/`GBPUSD`/`USDHKD`）静态 K 线分片 → 按令牌完成 `publish_site.py`（通过 S1–S7 严检）与 `edition_run.py complete` 纯网页上线验收。本机伴随监测引擎 `scripts/realtime_monitor.py` 与 `scripts/wechat_notify.py` 独立于定时 56 项权限之外，严格只读消费 `gold/data_snapshot.json`、`state/market_state.json` 与 `state/policy_calendar.json`（完全继承黄金红灯锁，告警去重库落于 `.git/realtime-monitor.sqlite3` 零仓库污染）。
