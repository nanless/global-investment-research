# 发版前 10 项全量质量与合规门禁（Pre-Flight 10 Gates · 全时段主刊 21 图版）

每次发布 **A 股 / 港股 / 美股** 独立全时段主刊（`main`）、升级版休市守望刊（`holiday_watch`）或修订三份旗舰常青手册（16–32 页）前，必须逐项通过以下 **10 道硬门禁**（已与最新 `lint_equity.py` Gate 0–6、Gate 3B 及跨项目黄金门禁 C1–C3 100% 同步）；任何一项未通过均须修订后再编译，自查溯源隔离记入 `state/audit_ledger.md`（编译验收全绿后再执行 Step 5 受控 RSI 盲审，见 `rsi_self_review_protocol.md`）。

---

## 门禁 1｜7 类一手源核验、跨项目黄金 SSOT 6 小时宽限与透明披露反阻塞
- ☐ 全部收盘、成交额（区分“沪深两市”与“沪深北全市场”）、央行公开市场（MLF 与逆回购切忌混算）、国债拍卖、公司财报、退市与监管状态均核验至 **7 类官方一手信源**（央行监管官网、交易所官方、SEC EDGAR/HKEXnews/CNINFO、主流金融终端、三地社区核伪、预测市场、公司 IR），**严禁仅凭财经聚合门户未刷新缓存推断报价或裁决状态**（中金所必查 `site:cffex.com.cn` 验日期戳等于目标 `YYYYMMDD`）。
- ☐ **跨项目黄金 SSOT 与 6 小时截点宽限（对齐 `lint_equity.py` Gate C1）**：黄金与权益声明同一有效 `edition_id`；黄金截点须早于或同分钟于权益落盘且间隔 **≤ 6 小时**，两轨截点与日报 `chart_live.as_of_full` 各须在所标班次前后 **6 小时内**；全量共享宏观键严格对齐，重点校验 **`brent_settle_usd`**、`cfets_cny_fixing`（带 `cfets_fixing_date`）、`spot_gold_ny_close_usd`、`us10y_pct`、`dfii10_live_pct`、`dxy`、`vix_close`、`on_rrp_usd_m`、`comex_copper_usd_lb` / `comex_copper_change_pct`；假日或周末无盘中观测时，允许双轨 **`brent_live_usd`** 与 **`vix_live`** 同口径同时留空（`vix_live` 留空时两轨不得保留 `vix_live_as_of` 与 `vix_intraday_high`）；COMEX 铜异动 `≥ 3.5%` 时 A/港报告须评估有色/紫金/洛钼传导（Gate C3）。
- ☐ 严防退市股、更名与到期兑付误判：核实池内标的处于正常上市状态（**绝不列入已于 2026-01-27 私有化退市的恒生银行 `00011`**，用渣打 `02888` 替代）；准确区分可转债到期兑付与提前强赎；准确区分恒生指数权重（汇丰/建行）与恒生科技扩容；严分利润跌幅与股价跌幅。
- ☐ **反阻塞透明披露与 T+1 零编造**：截点未出官方终值或来源暂不可取的数据严禁编造，亦**不得阻塞早/晚报准点发刊**；写入文末“待下期补核项”、挂入 `state/market_state.json` 的 `pending_backfills`（A 股 T 日两融固定次晨 08:00–09:00 披露、美股 BTC ETF 官流次日午间归档，统一挂至**次日 `1800` 晚刊**；延迟中金所挂次日 `0730` 早刊），并同步写入纯读者中文的 **`data_caveats`** 数组（零内部文件名）供门户与读者透明查验；上期挂账已在本期封账清零。

## 门禁 2｜算术 100% 闭环、A/H 同股 PE 物理学锁与 10 点进度条守恒
- ☐ 任何资产配置表格（含 `INDEX.md` 家庭总盘子）与口语概括中，各类资产占比加总**精确等于 100%**；未来窗口待换仓份额在当下执行列诚实归入“现金/超短债（待换仓）”。
- ☐ **A/H 同股估值物理学一致**：同一两地上市公司同口径市盈率与股息率必须严格满足 `PE_A / PE_H ≈ 1 + AH 溢价率`、`Div_H / Div_A ≈ 1 + AH 溢价率`，并在表头注明统一口径（TTM / 2026E / 2027E）。
- ☐ 均线偏离率、信用总借债成本、行业流向小计（严格区分“全市场总额”与“展示行业小计”）、10 万本金压力测试经反算零误差；自然频率 10 点进度条（`●●●●●○○○○○`）四情景实心点之和**必须精确等于 10**（对齐 Gate 3B），严禁伪精确小数概率/仓位。

## 门禁 3｜四灯、四色锁仓、买点锚 < 现价与三市危机熔断统一
- ☐ 封面、正文、SVG 图表与 `state/market_state.json` 中的四灯、体检分、股票总上限、唯一防踏空阈值及三市 `stock_pool_count` 100% 一致，零 `Tier 0–3` 或混用 `✅`。
- ☐ 四色锁仓严格区分 `🟢 当下底座`、`🔵 🔒未来主攻`、`🟡 分歧观察`、`🔴 高危回避`；**全部 `🔵 🔒未来主攻` 买点解锁锚点必须严格低于现价/现估值**；**图文色标 100% 一致**（如黄金红灯期 `NEM` 正文与图 U7 均为 `🟡` 观察三角，绝不画成绿点）。
- ☐ **三市危机总熔断三阀完全统一**：全库锁死 **`VIX 连 2 日 > 30` / 日元 3 日急升 >3% / 10 年美债 >5.25%**（港股叠加第 4 阀：**金管局总结余 < 400 亿港元**）。
- ☐ 下单前 3 秒自检卡为 **100% 正向“全选是”逻辑**，含 `☐` 方框、单只个股 ≤ 8%、跨三市（A+港+美）AI 同源科技 ≤ 20% 及“事前验尸”条款。

## 门禁 4｜双账户权限、QDII 属性、3 项已证伪税务/转债误导硬拦截（详表见 `dual_account_tax_and_rules.md`）
- ☐ **A 股**：场内首选 0.20% 低费 ETF，支付宝首选大规模 0.20% 联接（严禁推 `020035` 或 0.60% 老联接作首选，标明持 `<7` 天 1.5% 赎回费）；精准标注 `688`（50 万+2 年+200 股起步）、`300`（含创业板 ST 仍 ±20%）、`920`（50 万+2 年）、短线分红税与免五阈值；**【误导拦截 1】可转债临近到期须按发行人公告核对到期票息 20% 代扣后的税后净兑付额，并与二级市场净卖出额逐笔比较，严禁写“末日二级卖出免 20% 个人税”**。
- ☐ **港股**：① **【误导拦截 2】严禁笼统写“红筹股一律 28% 税 / 离岸 10% 完胜 28%”**，须写清内地个人港股通股息通常按 20% 代扣个税，并按发行人公告、名册登记方式与持有渠道分别核验源头代扣；② **【误导拦截 3】非 QDII 港股通 ETF `159545`/`159792` 买入前仍须核查二级市场折溢价，严禁写“零溢价/无溢价”**；明确标注 `513260`/`513010` 属 QDII；离岸恒科用 **`03067`（0.25%）** 替代 `03033`（1.04%）；严禁把沙特 `520830` 误作港股红利；严禁宣称港股通红利税减免已实施；A/H 价差仅作两地比价。
- ☐ **美股与跨境合规**：核对低费平替（`IAUM`/`GLDM`、`QQQM`、`SPYM`/`VOO`、`VBIL`/`SGOV`、`VTIP`、`VTV`/`RSP`）、W-8BEN 协定资格与有效期、QII 退税券商差异；美国遗产税 6 万美元为特定非居民非公民遗产通常适用的申报门槛（分产品核定资产所在地）；**境内个人年度等值 5 万美元便利化购汇不得用于境外证券投资**；中国居民个人按所得类别依法申报境外所得及核算抵免。

## 门禁 5｜精准时区、冬夏令时、07:30/18:00 截点与工作日日历
- ☐ 全篇以北京时间（CST）为主，美东冬令时 `+13h` / 夏令时 `+12h` 零错误；**全年硬禁令：`07:30 CST` 美股早刊绝未提前写 09:00/08:00 盘后终盘**，统一由当日 `18:00` 晚刊封账；港股 `07:30` 早刊必以 05:00–05:15 A50/金龙/ADR 修正 `03:00` 恒指夜期盲窗。
- ☐ 休市与到期日历精确核实：SIFMA 美债提前收市在**黑五**而非感恩节前周三；元旦 `2027-01-01_0730` 正常发美股 12/31 主刊（A/港复用），`1800` 及 `01/02_0730` 三市复用；`SCORECARD.md` 新登检验日严格落在**交易工作日**；涨跌一律写“上涨/下跌/由跌转涨”配正负号（严禁 `收红/收绿/翻红/翻绿/飘红/飘绿`）；美股必带中文名 + ≤10 字业务标签；大宗期货严禁混用近月与次月合约价。

## 门禁 6｜进阶理性语态、3 层术语标准、零内部工程词与反引号白名单
- ☐ **零内部工程与后台/RSI 噪声**：全部读者可见文件（含 `.md`、`report_meta_*.json`、`DAILY_META_JSON`、`data_caveats`、SVG、`INDEX.md`、`CHANGELOG.md`、`SCORECARD.md`）**零**版本号、`Subagent`、`红队`/`法证`、`Tier 0–3`、`Tier A/B/C`、`Meta-RSI`、`next_run_watch`、`RSI_PLAYBOOK`、`rsi_metrics.json`、Python 脚本名（`build_*.py`/`publish_site.py`/`pdf_common.py`/`docx_embed.py`/`lint_{equity,readability,site}.py`/`edition_{run,plan,validation}.py`/`artifact_receipt.py`/`chart_input.py`/`install_sidecars.py`）、内部规范/快照/状态文件名（`AGENTS.md`/`GEMINI.md`/`DAILY_REPORT_SPEC.md`/`DAILY_FORMAT_SPEC.md`/`SKILL.md`/`sidecar.json`/`permissions.json`/`unified-edition.prompt.md`/`market_state.json`/`data_snapshot.json`/`master_snapshot.json`/`audit_ledger.md`）、API/公告编号及原始 CSV 名。
- ☐ **零说教口号**：新刊（`>= 2026-11-26_1800`）严禁出现 `1 分钟定心丸`、`小白词典`、`直接抄`、`蠢事`、`保命铁律`，统一采用面向进阶普通投资者的理性专业章节名（如“核心判断与仓位动作”“关键术语速释”“核心配置方案”“常见误区”）。
- ☐ **3 层术语标准与反引号白名单**：① 常用术语（`VIX`/`DXY`/`PE`/`ERP`/`ETF`/`CDS`/`鹰派`/`鸽派`）可自然使用；② 进阶术语（`DFII10`/`ON RRP`/`HIBOR`/`HY OAS`/`IOPV`/`bp`）首次出现加 6–12 字中文括号轻注（正文避免裸写会触发 Linter 警告的 `ON RRP`/`IOPV`/`数字+bp`/`熊平`/`¢`，优先用中文表述）；③ 严禁生僻卖方词（`stop-through`/`FVOCI`/`ROTCE`/`HQLA`/`GAAP`）；反引号仅用于证券/ETF/可转债/期货/指数代码。

## 门禁 7｜Gate 3B 排版目标 vs 警告线、全时段主刊与弹性龙头池闭环
- ☐ **写作目标与 Gate 3B / Linter 警告线全项达标**：
  - 封面主标题：目标 **日报 ≤ 27 字 / 旗舰 ≤ 36 字**（警告线 **> 32 字 / > 38 字**）；
  - 开篇一句话结论：目标 **≤ 50 字**（警告线 **> 60 字**）；
  - 正文单段：目标 **≤ 130 字**（警告线 **> 180 字**）；
  - 列表项（`- `）：目标 **≤ 160 字**（警告线 **> 210 字**）；`CHANGELOG.md` 单条 **≤ 130 字**；
  - 真实粗体占比：目标 **≤ 12%**（警告线 **> 13.5%**）；
  - 主表 **≤ 5 列**（`SCORECARD.md` ≤ 6 列），日报焦点股表 3 列（4–6 只）；旗舰正文零相对日期词且清除非池内题材股流水账。
- ☐ **旗舰龙头池行数精确闭环（Gate 3B）**：三本旗舰附表二（Appendix 2）实际个股行数 **100% 等于 `report_meta_*.json` 与 `state/market_state.json` 各市 `stock_pool_count`**（**弹性区间 65–85 只/市**，扩容基准 **A 股 76 只 / 港股 75 只 / 美股 80 只，合计 231 只**，实时总数以 `state/market_state.json` 为单一事实源）。
- ☐ **全时段主刊结构与 `DAILY_META_JSON`**：自 `2026-11-26_1800` 起常规交易日三市统一发 `main`（必含 ≥2 张矢量图），休市/半日市发 `holiday_watch`（建议 ≥1 张矢量图）；`<!-- DAILY_META_JSON -->` 尾置、必填 `edition_id` 与 `edition_type`、可选 `data_caveats`、零原始 Emoji、零新旧键混写。

## 门禁 8｜21 张图动态键覆写、黄金红灯全载体锁（Gate C2）与日历跨轨校验
- ☐ 正文嵌入的每张 `<!-- CHART_{A,H,U}* -->`（除 `A1`/`A5` 外）所依赖的嵌套动态键均已写齐：含港股唯一规范键 **`hkma_agg_bal_hkd_100m`**（亿港元）、**`h6.items`**（必填非空全量不截断）与 **`h6.sector_strip`**（必填非空板块说明）、美股 **`u5`**（动态行高）与 **`u6`**（统一 1:1 线性刻度）、`u4.cards`（每条 ≤18 字）与 `u7.points`；SVG 数据标签字号 `≥ 9.0`；图 4/图 7 无过时静态文案或评级色标打架。
- ☐ **跨项目黄金红灯互斥锁全载体达标（Gate C2）**：当黄金快照 `tier_code == "Tier 0"` 或 `new_buy_allowed == false` 时，Markdown 正文、`DAILY_META_JSON`、`report_meta_*.json`、渲染后 SVG 与手机端 HTML 均零新买/补齐/低吸黄金指令，且金矿股（如 `NEM`）在图 7 中严禁标绿。
- ☐ 已执行 `lint_equity.py --plan <edition_id>` 核对当班刊型和复用指针，核对 `calendar_overrides` 的 `gold_event_id` 跨轨一致性（覆盖元旦 `2027-01-01_0730`、耶稣受难日 `2027-03-26` 等）及北京时间 `05:30` 跨午夜 `_r2` 切割线。

## 门禁 9｜三市六文件 + 审计账本闭环同步
一次标准发版须用 `write_file`（严禁 `edit_file`）全量同步：
1. ☐ `daily/YYYY-MM-DD_{0730,1800}_{a_share,hk_stock,us_stock}.md`（或 `_r2`）
2. ☐ `daily/INDEX.md`（刷新顶部 ≤4 列**三市场 + 黄金总水位驾驶舱** + 家庭占比 100% 闭环 + 追加最新行，单行指令 ≤35 字 + 有效链接）
3. ☐ `daily/CHANGELOG.md`（仅写纯读者中文观点/灯号/仓位/龙头池演进，单条 ≤130 字，零工程/勘误/RSI 词）
4. ☐ `daily/SCORECARD.md`（统一用 `✅ 兑现 / ⚠️ 部分兑现 / ❌ 证伪` 回填到期旧预判 + 登记新预判且检验日为工作日）
5. ☐ `state/market_state.json`（同步三市灯号、分数、点位、`stock_pool_count`、无日期规范键 `margin_balance_100m`/`margin_balance_date`/`pboc_total_net_100m`/`pboc_op_date`/`hkma_agg_bal_hkd_100m`、黄金镜像、`brent_settle_usd`、`cfets_cny_fixing`、防踏空阈值、`pending_backfills`、纯读者中文 `data_caveats` 与最新文件名）
6. ☐ `state/audit_ledger.md`（倒序置顶归档一手源核验、红队纠偏 Diff、数据回补日志与编译字节数）
- ☐ 若命中旗舰 5 条触发阈值，同步更新 `{a_share,hk_stock,us_stock}_market_report_{YYYY_MM}.md` 与 `report_meta_{a_share,hk_stock,us_stock}.json`。

## 门禁 10｜独立预检、串行编译、Gate 6 红线与站点发布
- ☐ **编译前秒检**：运行 `python3 .../lint_equity.py --precheck --strict`（Gate 0–5 + Gate 3B + Gate C1–C3），确认 0 错 0 警后再编译。
- ☐ **按定时模板的授权命令串行执行**（支持 `CHROME_BIN` 环境变量及 1 次自动重试；未改旗舰时只运行权益日报编译脚本与权益门禁；Word 由 `docx_embed.py` 生成原生 ECMA-376 OOXML）。
- ☐ **编译后全量严检**：运行 `python3 .../lint_equity.py --strict`，确认 Gate 0–6（含 **PDF 页数与体积红线：旗舰 16–32 页 ≥50KB / 常规主刊 `main` 目标 5–6 页、容忍 3–7 页、≥2 图、≥50KB / 守望刊 `holiday_watch` 及历史 `light` 目标 2–3 页、容忍 1–4 页、建议 ≥1 图、≥25KB**、DOCX 7 核心 XML / `<w:tbl>` / 图数与 `docPr` 唯一性、三市 `_latest.{md,pdf,docx}` 与三市手机 HTML、RSI 账本）、Gate 3B 及跨项目 Gate C1–C3（`brent_settle_usd` + **6 小时**截点宽限 + HTML/SVG 黄金锁）**退出码 0、0 错 0 警**。
- ☐ 抽检 PDF 的标签、留白、图号和尾页。Step 5 完成盲审并按 `resolved`/`deferred_data`/`disclosed_caveat` 闭环后复跑双轨严检，推进本期令牌到 `publish`，执行 `python3 .../scripts/publish_site.py --edition-token <token>`，再执行 `python3 .../scripts/edition_run.py complete <token>`。无活动班次时按根仓规则使用人工发布入口。
