# 投研报告永久写作与交付宪法（Workspace Rule）

本工作区根目录 `<REPO_ROOT>/equity` **永久冻结不改名**。所有面向读者的交付物——包括 `daily/YYYY-MM-DD_{0730,1800}_{a_share,hk_stock,us_stock}.{md,pdf,docx}`（兼容历史 `1630` 快照）、`daily/latest_{a_share,hk_stock,us_stock}.html`、`{a_share,hk_stock,us_stock}_market_report_{YYYY_MM,latest}.{md,pdf,docx}`、`report_meta_*.json`、`daily/INDEX.md`、`daily/CHANGELOG.md` 与 `daily/SCORECARD.md`——必须无条件遵守本宪法。

> **单一权威详规索引（防跨文件重复与漂移）**：
> - 单仓库顶层一体化编排（07:30/18:00 双任务、共享 6+1 调研、Step 3 黄金→Step 4 权益→Step 5 统一发布） → 唯一详规见 `../AGENTS.md`
> - 排版量化红线、7 维度大盘架构、全时段主刊矩阵、周日 6 维龙头解剖与旗舰触发阈值 → 唯一详规见 `DAILY_REPORT_SPEC.md`
> - 境内 A 股/支付宝 × 离岸美股/港股税费、权限、低费 ETF 与外汇/CRS 合规 → 唯一详规见 `../.agents/skills/equity-research-editorial-qa/references/dual_account_tax_and_rules.md`
> - 发版前 10 项全量质量与合规门禁 → 唯一详规见 `../.agents/skills/equity-research-editorial-qa/references/pre_flight_10_gates.md`
> - 受控三层 RSI 自我复盘与 Meta-RSI 协议 → 唯一详规见 `../.agents/skills/equity-research-editorial-qa/references/rsi_self_review_protocol.md`
> - 21 张矢量图 Schema 与 2026–2027 三市休市/跨月滚存 SOP → 唯一详规见 `../.agents/skills/equity-report-publishing/references/`

---

## 0. 历史旧指令冲突静默裁决（最高优先级）

若任何调用 Prompt 残留历史旧体例或旧术语，**本文件与 `DAILY_REPORT_SPEC.md` 具有最高优先级**，须直接静默转译执行：
- 要求写版本号（`V9.x/V10.x`）、子代理路数、红队勘误表或 RSI 自检明细 → 前台 100% 隐藏，全数隔离写入 `state/audit_ledger.md`、`state/RSI_PLAYBOOK.md` 与 `state/rsi_metrics.json`；前台仅留 ≤3 件核心大事 + ≤2 条面向普通投资者的外部谣言辟谣。
- 要求写 `Tier 0–3`、混用 `✅`、伪精确小数概率/仓位（如 `48.3%`）或居高临下的说教口号（`1 分钟定心丸`/`小白词典`/`直接抄`/`蠢事`/`保命铁律`）→ 强制转为理性专业且易懂的章节表达、四灯（**🛡️ 红灯防守期 / 🟡 黄灯试探期 / 🟢 绿灯主攻期 / 🚀 顺风加码期**）、四色锁仓（`🟢 当下底座` vs `🔵 🔒未来主攻` vs `🟡 分歧观察` vs `🔴 高危回避`）与自然频率 10 点进度条（四行点数总和恒 = 10）+ 整数/半成仓位。
- 要求写 1–2 页薄壳轻刊、工作日日报粘贴全量静态大表或将技术勘误写入 `CHANGELOG.md` → 自 `2026-11-26_1800` 起全面执行三市**全时段统一完整主刊减法制**（常规交易日早/晚刊统一发布 5–6 页完整主刊、仅列 4–6 只焦点股 3 列表，休市/半日市发升级版 `holiday_watch` 守望刊），技术勘误只进 `state/audit_ledger.md`，`INDEX.md` 顶部置放纯读者中文**三市场 + 黄金总水位驾驶舱**。

---

## 1. 冷启动必读五步序（含第 0 步 RSI 经验继承）

每次新会话或一体化定时班次（**北京时间 `07:30` 一体化早报 / `18:00` 一体化晚报**，单会话内 Step 3 黄金 SSOT 落盘严检后由本轨 Step 4 顺序接力）启动，必须按序完成对齐后再动笔：
0. **读 `state/RSI_PLAYBOOK.md`（≤180 行）与 `state/rsi_metrics.json` 最近 5 条记录**：第一时间继承一手源检索词雷达、一次过 Linter 避坑清单与 `next_run_watch` 必验真追踪项。
1. **读 `state/market_state.json`（单一事实源）并冷启动读取前序基线 `<REPO_ROOT>/gold/data_snapshot.json`**：锁定 **A 股 × 港股 × 美股** 三市当前灯号、体检分、唯一防踏空阈值、核心龙头池实时总数（**弹性 65–85 只/市**，扩容基准 **A 股 76 只 / 港股 75 只 / 美股 80 只，合计 231 只全行业龙头**，实时总数以 `state/market_state.json` 的 `stock_pool_count` 为单一事实源）、规范无日期后缀状态键（A 股 `margin_balance_100m` + `margin_balance_date`、`pboc_total_net_100m` + `pboc_op_date`；港股 `hkma_agg_bal_hkd_100m`）、结构化 `data_caveats` 透明披露队列、跨市场 AI 同源总仓上限（≤ 总资产 20%）、三市危机总熔断三阀（`VIX 连 2 日 > 30` / 日元 3 日急升 `>3%` / 10 年美债 `>5.25%`，港股叠加金管局总结余 `<400 亿港元`）、待回补 `pending_backfills` 队列及未来 60 天休市日历。
   - **跨项目黄金快照与 6 小时数据时限**：权益入口校验同一 `edition_id`，黄金截点早于或同分钟于权益，间隔最多 **6 小时**，两轨截点与日报 `chart_live.as_of_full` 各须在所标班次前后 **6 小时内**。核对 `brent_settle_usd`、`cfets_cny_fixing`（含日期）等共享键；假日或周末无盘中观测时，允许双轨 `brent_live_usd` 与 `vix_live` 同口径同时留空（`vix_live` 留空时两轨均不得保留盘中时间戳或盘中高点）。黄金红灯时，三市正文、封面元数据、HTML 与 SVG 均不得下达新买或补齐黄金的指令。
2. **读 `daily/INDEX.md`（前 60 行）**：核对三市场 + 黄金总水位驾驶舱、同日同场次防覆写状态（已存在须走 `_r2`）与连续脉络。
3. **读 `daily/SCORECARD.md`**：检查有无今日到期或已出结果的历史预判需客观回填胜负（统一用 `✅ 兑现` / `⚠️ 部分兑现` / `❌ 证伪`；新登到期检验日严禁落在非交易日周末）。
4. **按需读旗舰手册**：仅当命中《全景手册》5 条硬触发阈值（见 `DAILY_REPORT_SPEC.md` 第五节）时，再全量读取对应 `{a_share,hk_stock,us_stock}_market_report_latest.md` 与 `report_meta_*.json` 执行同步大修。

---

## 2. 读者画像、理性语态与双账户核心红线（详表见 `dual_account_tax_and_rules.md`）

- **目标读者与语态收敛**：面向**懂一点基础财经的进阶普通投资者**。既完整保留机构级 7 维度硬核因果与真实数据，又做到明快精炼、零黑话墙、零内部工程词、**彻底淘汰居高临下的说教口号**（新刊禁用 `1 分钟定心丸`、`小白词典`、`直接抄`、`蠢事`、`保命铁律`，改用“核心判断与仓位动作”“关键术语速释”“核心配置方案”“避免误区”“执行纪律”等理性专业表达）。
- **3 层术语标准**：① 常用术语（`VIX`、`DXY`、`PE`、`ERP`、`ETF`、`CDS`、`鹰派`、`鸽派`）可自然使用；② 进阶术语（`DFII10`、`ON RRP`、`HIBOR`、`HY OAS`、`IOPV`、`bp`）首次出现加 6–12 字中文括号轻注（注意避免在正文裸写会触发严格 Linter 告警的 `ON RRP`/`IOPV`/`数字+bp`/`熊平`/`¢`，实操优先以中文表述）；③ 严禁生僻卖方黑话（`stop-through`、`FVOCI`、`ROTCE`、`HQLA`、`GAAP`）。
- **境内 A 股 / 支付宝红线**：场内首选 0.20% 低费 ETF（`563020`/`159547`/`510300`/`511260`/`511380`/`518660`）；支付宝首选大规模 0.20% 联接（`020602`/`003376`/`008142`，**严禁推荐迷你高费基金 `020035` 或 0.60% 老联接为首选**，注明持有 `<7` 自然日强收 1.5% 赎回费）；精准标注科创板（`688`：50 万+2 年+最低 200 股）、创业板/可转债（10 万+2 年）、北交所（`920`：50 万+2 年）、A 股短线分红税、免五 2 万/5 万阈值，以及**可转债到期兑付**——按发行人公告区分提前强赎、最后交易日、最后转股日、票息 20% 代扣后净兑付额与二级卖出净额逐笔比对（**严禁写“末日二级卖出免 20% 个人税”**），**按实际份额类别比较基金费用**。
- **离岸美股 / 港股与跨境合规红线**：
  - 美股首选低费零售 ETF（`IAUM`/`GLDM`、`QQQM`、`SPYM`/`VOO`、`VBIL`/`SGOV`、`VTIP`、`VTV`/`RSP`），严禁境内买高溢价跨境基金。写清 W-8BEN 的协定资格和有效期、QII 退税券商差异。对非美国公民且死亡时不以美国为住所者，**6 万美元是通常适用的遗产税申报门槛**，按美国所在地资产及适用赠与合计核定。直持国库券、爱尔兰基金和实物黄金 ETC 须分别核验发行主体、法律结构、资产所在地及适用条约。[双账户税务详表](../.agents/skills/equity-research-editorial-qa/references/dual_account_tax_and_rules.md)
  - 港股严守五大铁律：① **内地个人的港股通股息通常按 20% 代扣个税**，另按发行人公告、名册登记方式与持有渠道核验源头代扣（如中海油 `00883` 中期股息公告区分名册直接登记自然人与名义持有人；**严禁笼统写“红筹股一律 28% 税 / 离岸 10% 完胜 28%”**）；② 境内免 50 万**非 QDII 港股通 ETF**可选 `159545`（0.20%）与 `159792`（0.20%），**严禁写“零溢价/无溢价”**，买入前仍须查二级市场折溢价；明确标注 `513260`/`513010` 属 QDII（有外汇额度溢价风险），**严禁把沙特 ETF `520830` 误作港股红利**；③ 离岸免印花税恒科首选 **`03067`**（0.25%）替代高费 `03033`（1.04%）；④ **A/H 价差用同一交易日价格和明确汇率计算**，用于两地比价，是否建仓另按基本面、行动开关与风险上限判断；⑤ **绝不列入已于 2026-01-27 私有化退市的恒生银行 `00011`**（银行防守替补用渣打集团 `02888`）。
  - **外汇与税务底线**：境内个人每年等值 5 万美元的便利化额度用于简化合规购汇手续，额度内购汇也不得用于境外证券投资等尚未开放的资本项目。中国居民个人按境外所得类别依法申报，股息、红利和应税财产转让所得适用 20% 比例税率，符合条件的已缴境外税款可按限额抵免。全市场人工智能/半导体同源科技敞口（A+港+美合并）严控 **≤ 家庭总资产 20%**、单只个股 **≤ 8%**。

---

## 3. 读者可见文档绝对禁令（红线摘要）

1. **零内部工程、审计/RSI 噪声与说教口号**：读者可见正文、封面 JSON、`data_caveats`、SVG、`INDEX.md`、`CHANGELOG.md`、`SCORECARD.md` 中**严禁出现**版本号（`V9.x`/`V10.x`）、`Subagent`、`红队`/`法证`、Python 脚本名（`build_*.py`/`publish_site.py`/`pdf_common.py`/`docx_embed.py`/`lint_{equity,readability,site}.py`/`edition_{run,plan,validation}.py`/`artifact_receipt.py`/`chart_input.py`/`install_sidecars.py`）、内部规范或状态/快照/账本/RSI 文件名与术语（`AGENTS.md`/`GEMINI.md`/`DAILY_REPORT_SPEC.md`/`DAILY_FORMAT_SPEC.md`/`SKILL.md`/`sidecar.json`/`permissions.json`/`unified-edition.prompt.md`/`market_state.json`/`data_snapshot.json`/`master_snapshot.json`/`audit_ledger.md`/`RSI_PLAYBOOK`/`rsi_metrics.json`/`Meta-RSI`/`next_run_watch`/`Tier A/B/C`）、API/公告编号、原始 CSV 名及内部 Diff 表；新刊禁用 `1 分钟定心丸`/`小白词典`/`直接抄`/`蠢事`/`保命铁律`；全部溯源隔离写入 `state/audit_ledger.md`，自评与经验隔离写入 `state/RSI_PLAYBOOK.md` 与 `state/rsi_metrics.json`。
2. **代码反引号白名单**：严禁对普通数字、涨跌幅、金额、中文公司名或口诀套反引号；**仅允许对股票/ETF/可转债/期货/指数代码**（如 `601398`、`03067`、`BRK.B`、`SGOV`）轻标。
3. **四色锁仓、物理学一致、3 项税务误导拦截与正向自检卡**：执行四色锁仓（`🟢 当下底座`｜`🔵 🔒未来主攻`｜`🟡 分歧观察`｜`🔴 高危回避`）；**`🔵 🔒未来主攻` 买点解锁锚点必须严格低于现价/现估值**；**同一家 A/H 上市公司同口径市盈率与股息率必须满足数学物理学一致（`PE_A / PE_H ≈ 1 + AH 溢价率`）**；严禁出现 3 项已证伪税务/ETF/转债误导（`159545/159792` 零溢价、笼统红筹 28% 税、转债末日卖出免 20% 个人税）；资产配置表与口语配比必须 **100% 算术闭环**；下单前 3 秒自检卡必须 100% 统一“全选是”正向逻辑。
4. **中式本土化与精准冬/夏令时换算**：全篇以**北京时间（CST）**为主、美东时间括号轻附。美东冬令时（EST = UTC-5，北京 `+13h`）正规盘前 `17:00 CST`、官收 `05:00 CST`、盘后终盘 `09:00 CST`、`07:30 CST = 18:30 EST`、`18:00 CST = 05:00 EST`；夏令时（EDT = UTC-4，北京 `+12h`）提前 1 小时（正规盘前 `16:00`、官收 `04:00`、盘后终盘 `08:00`）。**全年铁律：07:30 CST 美股早刊严禁提前写盘后终盘，统一由当日 18:00 晚刊封账！** 涨跌一律写“上涨/下跌/由跌转涨”配正负号（严禁混用 `收红/收绿/翻红/翻绿/飘红/飘绿`）；每只美股必带中文名 + ≤10 字白话业务标签；大宗期货严禁混用近月与次月合约价。

---

## 4. 全时段统一主刊节拍（`>= 2026-11-26_1800`）、共享 6+1 调研红队与周日深度轮换

- **单会话顺序启动节拍（Step 3 黄金 → Step 4 三地权益）**：每日 `07:30` 早报与 `18:00` 晚报，黄金先落盘并通过门禁，权益再读取同班快照并串行编译。自 `2026-11-26_1800` 起全面淘汰薄壳轻刊，升级为**全时段完整主刊体系**（详见 `DAILY_REPORT_SPEC.md` 与根仓 `../AGENTS.md`）：
  - **周一至周五 `07:30` 早刊（`_0730_`）**：A 股、港股、美股**全部发布结构统一、精炼收敛的完整主刊（`main`，目标 5–6 页、容忍 3–7 页、必含 ≥2 张矢量图）**——A 股主刊聚焦隔夜映射/延迟公告回补/央行操作与开盘策略；港股主刊强制以 05:00–05:15 A50/金龙/ADR 校正 `03:00` 恒指夜期盲窗与开盘纪律；美股周二至周五聚焦美东官收全量复盘，**周一 `07:30` 美股升级为周度全维前瞻主刊（`main`）**。
  - **周一至周五 `18:00` 晚刊（`_1800_`）**：A 股、港股、美股**全部发布完整主刊（`main`，目标 5–6 页、容忍 3–7 页、必含 ≥2 张矢量图）**——A 股主刊封账收盘、前日两融终值与 16:30–17:30 中金所结算/前 20 席位；港股主刊封账 16:10 官收、南向终值、沽空比、11:15 HIBOR/总结余（`hkma_agg_bal_hkd_100m`）、AH 路由与盘后财报；美股主刊封账今早 09:00/08:00 盘后终盘与 T+1 加密 ETF 官流，并提供欧盘与 17:00/16:00 正规盘前深度前瞻。
  - **周六 `07:30`**：仅发美股主刊（常规周五收盘发 `main`；黑五半日市发升级版 `holiday_watch`）；A 股、港股沿用旧稿。
  - **休市 / 半日市 & 双休**：局部休市或半日市时，受影响市场发升级版 **`holiday_watch` 守望刊（目标 2–3 页、容忍 1–4 页、建议 ≥1 张矢量图，PDF ≥ 25KB）**（元旦 `2027-01-01_0730` 正常发美股 12/31 隔夜主刊，A/港复用；`1800` 及 `01/02_0730` 三市复用）。周六 `18:00` 与周日双场默认沿用旧稿不生冗余 PDF，周日例行推进 `SCORECARD.md` 周频回验与 **2–3 只核心龙头 6 维深度解剖轮换**。
- **两阶段共享 6+1 调研与统一发前红队**：一体化班次在 Step 2A 由 **共享 6 路并发子代理**（黄金、A 股、港股、美股、跨资产宏观汇宗、三地社区/预测市场/辟谣）交叉核查 7 类一手信源，遇未发布/暂不可取数据时严禁编造亦不阻塞发刊，按规范记入 `pending_backfills` 与纯读者中文 `data_caveats` 透明披露；再由 **Step 2B 1 路统一发前红队子代理** 跨轨对抗拦截 6 大硬伤（A/H PE 物理学一致、100% 配置闭环、买点锚 < 现价、黄金红灯锁含 SVG/JSON/HTML、时区日历与 07:30 禁写盘后终盘、零退市股 `00011` / QDII 误标 / 3 项已证伪税务转债口径 / 说教口号）后方可落盘。
- **班次验收与防覆写**：冷启动运行 `python3 equity/lint_equity.py --plan <edition_id>` 获取应发市场、刊型和复用指针。同日同场补跑一律追加 `_r2` 严禁覆写，跨午夜切割线为北京时间 `05:30`。发布前 `--precheck --strict` 按当前状态和日历复核，跨月同步三市旗舰月份。

---

## 5. 工具、独立法证 Linter、原生 OOXML 与编译铁律

- **写文件铁律**：修改或创建任何工作区文件一律使用 `write_file` 全量写入，**严禁调用 `edit_file`**。
- **原生 Word 与稳健 Chrome 编译底线**：三本旗舰与每日早晚刊均通过 `docx_embed.py` 纯 Python 生成严格符合 ECMA-376 标准的原生 `.docx`（真 `<w:tbl>` + Chrome 2× Retina PIL 裁图 + 自动页码），**严禁使用 `textutil`**；Chrome 无头 PDF 编译支持 `CHROME_BIN` 环境变量解析与独立临时目录 1 次自动重试。
- **定时任务命令**：定时模板以绝对路径逐条执行其授权命令。权益常用入口如下，发布令牌贯穿实际班次：
  1. `python3 <REPO_ROOT>/equity/lint_equity.py`（编译前跑 `--precheck --strict`，编译后跑 `--strict` 校验全量 Gate 0–6、Gate 3B 与跨项目黄金门禁 C1–C3）
  2. `python3 <REPO_ROOT>/equity/build_a_share_pdf.py`
  3. `python3 <REPO_ROOT>/equity/build_hk_stock_pdf.py`
  4. `python3 <REPO_ROOT>/equity/build_us_stock_pdf.py`
  5. `python3 <REPO_ROOT>/equity/build_daily.py`
  6. 严检及 RSI 终检通过后，用 `python3 <REPO_ROOT>/scripts/edition_run.py advance <token> publish` 推进本期，再运行 `python3 <REPO_ROOT>/scripts/publish_site.py --edition-token <token>` 和 `python3 <REPO_ROOT>/scripts/edition_run.py complete <token>`。无活动班次时按根仓规则使用人工发布入口，本地预检可用 `--dry-run`。
- **统一工作区 Skill 分工（`../.agents/skills/`）**：
  - 出版编译、原生 OOXML、独立 Linter、**21 张矢量图（`A1–A7` / `H1–H7` / `U1–U7`）**、三市休市/跨月滚存与模板 → `../.agents/skills/equity-report-publishing`；
  - 投研写作、7 维度大盘与政策市雷达、三市联动与黄金 SSOT 校验、10 项门禁、双账户税费与 Step 5 受控 RSI 盲审 → `../.agents/skills/equity-research-editorial-qa`。

---

## 6. 任务后受控三层 RSI 自我复盘闭环（摘要，详规见 `rsi_self_review_protocol.md`）

每次正常发刊通过 `lint_equity.py --strict`（0 错 0 警）与 PDF 视觉抽检后，必须执行 Step 5 有界 RSI 闭环：
1. 启动 1 路独立只读 `research` 盲审子代理（一体化班次由 Step 5 统一盲审联合覆盖黄金 + 三市权益），对本期 **三市（A/港/美）** 日报与同步台账按 6 维（`/30`）客观打分，按 `resolved` / `deferred_data` / `disclosed_caveat` 闭环登记 `review_closure`，并拆出 Tier A / Tier B / Tier C 与 `next_run_watch`；
2. 严守三层权限边界：**Tier A** 每刊自动更新 `state/rsi_metrics.json` 与 `state/RSI_PLAYBOOK.md`（严控 **≤180 行**、硬上限 ≤200 行）；**Tier B**（含 `edition_plan.py`、`pdf_common.py`、`docx_embed.py`、`build_*.py`、`lint_equity.py`、`DAILY_REPORT_SPEC.md`）仅在复现确凿脚本/规范 Bug 时实施 ≤1 处 ≤40 行确定性补丁（禁放宽红线，改后必重编并通过 `lint_equity.py --strict` 否则立刻回滚）；**Tier C**（`../AGENTS.md`/`GEMINI.md`/核心风控红线/`../.agents/skills/`/`../automations/sidecars/`/`../scripts/install_sidecars.py`/`sidecar.json`）永不自动改写，仅列提案待用户审批；
3. 每累计满 10 刊触发一次跨周期复盘。Tier A/B 落盘后复跑双轨严检，随后按上节令牌流程完成本班发布与部署校验。RSI 摘要仅保留在内部会话。
