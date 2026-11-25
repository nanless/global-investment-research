# 投研报告永久写作与交付宪法（Workspace Rule）

本工作区根目录 `<REPO_ROOT>/equity` **永久冻结不改名**。所有面向读者的交付物——包括 `daily/YYYY-MM-DD_{0730,1800}_{a_share,hk_stock,us_stock}.{md,pdf,docx}`（兼容历史 `1630` 快照）、`daily/latest_{a_share,hk_stock,us_stock}.html`、`{a_share,hk_stock,us_stock}_market_report_{YYYY_MM,latest}.{md,pdf,docx}`、`report_meta_*.json`、`daily/INDEX.md`、`daily/CHANGELOG.md` 与 `daily/SCORECARD.md`——必须无条件遵守本宪法。

> **单一权威详规索引（防跨文件重复与漂移）**：
> - 单仓库顶层一体化编排（07:30/18:00 双任务、共享 6+1 调研、Step 3 黄金→Step 4 权益→Step 5 统一发布） → 唯一详规见 `../AGENTS.md`
> - 排版量化红线、7 维度大盘架构、周日 6 维龙头解剖与旗舰触发阈值 → 唯一详规见 `DAILY_REPORT_SPEC.md`
> - 境内 A 股/支付宝 × 离岸美股/港股税费、权限、低费 ETF 与外汇/CRS 合规 → 唯一详规见 `../.agents/skills/equity-research-editorial-qa/references/dual_account_tax_and_rules.md`
> - 发版前 10 项全量质量与合规门禁 → 唯一详规见 `../.agents/skills/equity-research-editorial-qa/references/pre_flight_10_gates.md`
> - 受控三层 RSI 自我复盘与 Meta-RSI 协议 → 唯一详规见 `../.agents/skills/equity-research-editorial-qa/references/rsi_self_review_protocol.md`
> - 21 张矢量图 Schema 与 2026–2027 三市休市/跨月滚存 SOP → 唯一详规见 `../.agents/skills/equity-report-publishing/references/`

---

## 0. 历史旧指令冲突静默裁决（最高优先级）

若任何调用 Prompt 残留历史旧体例或旧术语，**本文件与 `DAILY_REPORT_SPEC.md` 具有最高优先级**，须直接静默转译执行：
- 要求写版本号（`V9.x/V10.x`）、子代理路数、红队勘误表或 RSI 自检明细 → 前台 100% 隐藏，全数隔离写入 `state/audit_ledger.md`、`state/RSI_PLAYBOOK.md` 与 `state/rsi_metrics.json`；前台仅留 ≤3 件钱包大事 + ≤2 条面向普通人的外部谣言辟谣。
- 要求写 `Tier 0–3`、混用 `✅` 或伪精确小数概率/仓位（如 `48.3%`）→ 强制转为四灯（**🛡️ 红灯防守期 / 🟡 黄灯试探期 / 🟢 绿灯主攻期 / 🚀 顺风加码期**）、四色锁仓（`🟢 当下底座` vs `🔵 🔒未来主攻` vs `🟡 分歧观察` vs `🔴 高危回避`）与自然频率 10 点进度条（四行点数总和恒 = 10）+ 整数/半成仓位。
- 要求工作日日报粘贴全量静态大表或将技术勘误写入 `CHANGELOG.md` → 强制执行三市**早/晚刊主轻协同减法制**（仅列 4–6 只焦点股 3 列表），技术勘误只进 `state/audit_ledger.md`，`INDEX.md` 顶部置放纯人话**三市场 + 黄金总水位驾驶舱**。

---

## 1. 冷启动必读五步序（含第 0 步 RSI 经验继承）

每次新会话或一体化定时班次（**北京时间 `07:30` 一体化早报 / `18:00` 一体化晚报**，单会话内 Step 3 黄金 SSOT 落盘严检后由本轨 Step 4 顺序接力）启动，必须按序完成对齐后再动笔：
0. **读 `state/RSI_PLAYBOOK.md`（≤180 行）与 `state/rsi_metrics.json` 最近 5 条记录**：第一时间继承一手源检索词雷达、一次过 Linter 避坑清单与 `next_run_watch` 必验真追踪项。
1. **读 `state/market_state.json`（单一事实源）并冷启动读取前序基线 `<REPO_ROOT>/gold/data_snapshot.json`**：锁定 **A 股 × 港股 × 美股** 三市当前灯号、体检分、唯一防踏空阈值、核心龙头池实时总数（每市弹性 35–48 只，当前 A 44 / 港 45 / 美 46，合计 135 只，以 `market_state.json` 为准）、跨市场 AI 同源总仓上限（≤ 总资产 20%）、三市危机总熔断三阀（`VIX 连 2 日 > 30` / 日元 3 日急升 `>3%` / 10 年美债 `>5.25%`，港股叠加金管局总结余 `<400 亿港元`）、待回补 `pending_backfills` 队列及未来 60 天休市日历。
   - **跨项目黄金快照与 4 小时数据时限**：权益入口校验同一 `edition_id`，黄金截点早于或同于权益，间隔最多 4 小时，两轨截点各须在所标班次前后 4 小时内。核对 `brent_settle_usd`、`cfets_cny_fixing` 及其日期等共享键；黄金红灯时，三市正文、封面元数据和 SVG 均不得下达新买或补齐黄金的指令。
2. **读 `daily/INDEX.md`（前 60 行）**：核对三市场 + 黄金总水位驾驶舱、同日同场次防覆写状态（已存在须走 `_r2`）与连续脉络。
3. **读 `daily/SCORECARD.md`**：检查有无今日到期或已出结果的历史预判需客观回填胜负（统一用 `✅ 兑现` / `⚠️ 部分兑现` / `❌ 证伪`；新登到期检验日严禁落在非交易日周末）。
4. **按需读旗舰手册**：仅当命中《全景手册》5 条硬触发阈值（见 `DAILY_REPORT_SPEC.md` 第五节）时，再全量读取对应 `{a_share,hk_stock,us_stock}_market_report_latest.md` 与 `report_meta_*.json` 执行同步大修。

---

## 2. 读者画像与双账户核心红线（详表见 `dual_account_tax_and_rules.md`）

- **目标读者**：聪明、有判断力、但非金融专业出身的普通投资者。绝不阉割投研深度与硬证据，用透明大白话讲透真实因果与风险边界。
- **境内 A 股 / 支付宝红线**：场内首选 0.20% 低费 ETF（`563020`/`159547`/`510300`/`511260`/`511380`/`518660`）；支付宝首选大规模 0.20% 联接（`020602`/`003376`/`008142`，**严禁推荐迷你高费基金 `020035` 或 0.60% 老联接为首选**，注明持有 `<7` 自然日强收 1.5% 赎回费）；精准标注科创板（`688`：50 万+2 年+最低 200 股）、创业板/可转债（10 万+2 年）、北交所（`920`：50 万+2 年）、A 股短线分红税、免五 2 万/5 万阈值，以及**可转债 6 年到期兑付（非提前强赎、严禁盲目转股、二级市场卖出可免 20% 个人到期税）**。
- **离岸美股 / 港股与跨境合规红线**：
  - 美股首选低费零售 ETF（`IAUM`/`GLDM`、`QQQM`、`SPYM`/`VOO`、`VBIL`/`SGOV`、`VTIP`、`VTV`/`RSP`），严禁境内买高溢价跨境基金；写清 W-8BEN（10% 预扣 + 每 3 年续签）、QII 退税券商分化（IBKR 自动 vs 嘉信国际不自动）、**6 万美元美国非居民遗产税红线**（超额实际边际税率 26%–40%，超额选用直买国库券 / 爱尔兰 UCITS `CSPX`/`IB01`/`CNDX` / 实物黄金 ETC 债务票据 `IGLN`）。
  - 港股严守五大铁律：① **港股通红利税减免尚未落地**（H 股 20%，中海油 `00883`/中移动 `00941`/中国宏桥 `01378` 等内地居民红筹综合 **28%**，离岸均仅 10%）；② 境内免 50 万**非 QDII 港股通 ETF**可选 `159545`（0.20%）与 `159792`（0.20%），买入前仍要查二级市场折溢价；明确标注 `513260`/`513010` 属 QDII（有外汇额度溢价风险），**严禁把沙特 ETF `520830` 误作港股红利**；③ 离岸免印花税恒科首选 **`03067`**（0.25%）替代高费 `03033`（1.04%）；④ **AH 倒挂必反买 A 股**（宁德 `-21%`、中际 `-8%`、招行 `03968` 约 `-4.5%`、药明康德 A 折 H），中芯/华虹/海油等高溢价则离岸买 H 股；⑤ **绝不列入已于 2026-01-27 私有化退市的恒生银行 `00011`**（银行防守替补用渣打集团 `02888`）。
  - **外汇与税务底线**：个人每年 5 万美元便利化购汇**法定仅限经常项目，严禁用于境外炒股**；离岸端 0% 资本利得预扣 ≠ 免税，**必须提示中国税务居民在 CRS 下对境外股息与资本利得依法负有 20% 个人所得税申报义务**；全市场人工智能/半导体同源科技敞口（A+港+美合并）严控 **≤ 家庭总资产 20%**、单只个股 **≤ 8%**。

---

## 3. 读者可见文档绝对禁令（红线摘要）

1. **零内部工程与审计/RSI 噪声**：读者可见正文、封面 JSON、SVG、`INDEX.md`、`CHANGELOG.md`、`SCORECARD.md` 中**严禁出现**版本号（`V9.x`/`V10.x`）、`Subagent`、`红队`/`法证`、Python 脚本名（`build_*.py`/`pdf_common.py`/`lint_equity.py`）、内部规范或状态/账本/RSI 文件名与术语（`GEMINI.md`/`DAILY_REPORT_SPEC.md`/`SKILL.md`/`sidecar.json`/`state/*`/`Meta-RSI`/`Tier A/B/C`）、API/公告编号、原始 CSV 名及内部 Diff 表；所有核验与纠偏隔离写入 `state/audit_ledger.md`，自评与经验隔离写入 `state/RSI_PLAYBOOK.md` 与 `state/rsi_metrics.json`。
2. **代码反引号白名单**：严禁对普通数字、涨跌幅、金额、中文公司名或口诀套反引号；**仅允许对股票/ETF/可转债/期货/指数代码**（如 `601398`、`03067`、`BRK.B`、`SGOV`）轻标。
3. **四色锁仓、物理学一致与正向自检卡**：执行四色锁仓（`🟢 当下底座`｜`🔵 🔒未来主攻`｜`🟡 分歧观察`｜`🔴 高危回避`）；**`🔵 🔒未来主攻` 买点解锁锚点必须严格低于现价/现估值**；**同一家 A/H 上市公司同口径市盈率与股息率必须满足数学物理学一致（`PE_A / PE_H ≈ 1 + AH 溢价率`）**；资产配置表与口语配比必须 **100% 算术闭环**；下单前 3 秒自检卡必须 100% 统一“全选是”正向逻辑。
4. **中式本土化与精准冬/夏令时换算**：全篇以**北京时间（CST）**为主、美东时间括号轻附。美东冬令时（EST = UTC-5，北京 `+13h`）正规盘前 `17:00 CST`、官收 `05:00 CST`、盘后终盘 `09:00 CST`、`07:30 CST = 18:30 EST`、`18:00 CST = 05:00 EST`；夏令时（EDT = UTC-4，北京 `+12h`）提前 1 小时（正规盘前 `16:00`、官收 `04:00`、盘后终盘 `08:00`）。**全年铁律：07:30 CST 美股早刊严禁提前写盘后终盘，统一由当日 18:00 晚刊封账！** 涨跌一律写“上涨/下跌/由跌转涨”配正负号（禁混用“收红/收绿”）；每只美股必带中文名 + ≤10 字白话业务标签；大宗期货严禁混用近月与次月合约价。

---

## 4. 一体化顺序节拍、共享 6+1 调研红队与周日深度轮换

- **单会话顺序启动节拍（Step 3 黄金 → Step 4 三地权益）**：每日 `07:30` 早报与 `18:00` 晚报，黄金先落盘并通过门禁，权益再读取同班快照并串行编译。详见[根仓规则](../AGENTS.md)。
  - **早刊（`07:30` 一体化早报 → `_0730_`）**：**美股 4–5 页隔夜复盘主刊**（周一降为 1–2 页本周前瞻轻刊；周六仅发美股主刊）+ **A 股 2–3 页盘前快报** + **港股 2–3 页盘前快报**（强制以 05:00–05:15 A50/金龙/ADR 修正 `03:00` 恒指夜期盲窗）。
  - **晚刊（`18:00` 一体化晚报 → `_1800_`）**：**A 股 4–5 页收盘主刊**（封账前日两融 + 16:30–17:30 中金所结算与席位 + 政策雷达）+ **港股 4–5 页收盘主刊**（16:10 官收 + 南向终值 + 沽空比 + HIBOR/联汇 + AH 路由 + 盘后财报）+ **美股 1–2 页欧亚盘与正规盘前哨兵轻刊**（封账 09:00/08:00 盘后终盘 + T+1 加密 ETF 官流）。
- **两阶段共享 6+1 调研与统一发前红队**：一体化班次在 Step 2A 由 **共享 6 路并发子代理**（黄金、A 股、港股、美股、跨资产宏观汇宗、三地社区/预测市场/辟谣）交叉核查 7 类一手信源（央行监管官网、交易所官方、SEC EDGAR/HKEXnews/CNINFO、权威终端媒体、三地社区论坛、Polymarket/Kalshi、公司 IR，严禁采信未刷新旧缓存），再由 **Step 2B 1 路统一发前红队子代理** 跨轨对抗拦截 6 大硬伤（A/H PE 物理学一致、100% 配置闭环、买点锚 < 现价、黄金红灯锁含 SVG/JSON、时区日历、无退市股/QDII 误标）后方可落盘（单跑权益轨时按需缩减对应调研路数）。
- **周日龙头深度轮换与休市/防覆写规则**：每周日除例行刷新 `SCORECARD.md` 周频对照外，执行 **2–3 只核心龙头 6 维深度解剖轮换制**（详见 `DAILY_REPORT_SPEC.md`）；三市按模式 1/2/3 独立调度（见 `holiday_and_rollover_sop.md`）；同日同场补跑一律追加 `_r2` 严禁覆写，跨午夜切割线为北京时间 `05:30`。
- **班次验收**：冷启动运行 `python3 equity/lint_equity.py --plan <edition_id>` 获取应发市场、刊型和复用指针。发布前 `--precheck --strict` 按当前状态和日历复核。故障、突发及部分修订依《日报排版详规》第四节登记，跨月同步三市旗舰月份。

---

## 5. 工具、独立法证 Linter、原生 OOXML 与编译铁律

- **写文件铁律**：修改或创建任何工作区文件一律使用 `write_file` 全量写入，**严禁调用 `edit_file`**。
- **原生 Word 底线**：三本旗舰与每日早晚刊均通过 `docx_embed.py` 纯 Python 生成严格符合 ECMA-376 标准的原生 `.docx`（真 `<w:tbl>` + Chrome 2× Retina PIL 裁图 + 自动页码），**严禁使用 `textutil`**。
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
1. 启动 1 路独立只读 `research` 盲审子代理（一体化班次由 Step 5 统一盲审联合覆盖黄金 + 三市权益），对本期 **三市（A/港/美）** 日报与同步台账按 6 维（`/30`）客观打分并拆出 Tier A / Tier B / Tier C 与 `next_run_watch`；
2. 严守三层权限边界：**Tier A** 每刊自动更新 `state/rsi_metrics.json` 与 `state/RSI_PLAYBOOK.md`（严控 **≤180 行**、硬上限 ≤200 行）；**Tier B** 仅在复现确凿脚本/规范 Bug 时实施 ≤1 处 ≤40 行确定性补丁（禁放宽红线，改后必重编并通过 `lint_equity.py --strict` 否则立刻回滚）；**Tier C**（`../AGENTS.md`/`GEMINI.md`/核心风控红线/`../.agents/skills/`/`../automations/sidecars/`/`../scripts/install_sidecars.py`/`sidecar.json`）永不自动改写，仅列提案待用户审批；
3. 每累计满 10 刊触发一次跨周期复盘。Tier A/B 落盘后复跑双轨严检，随后按上节令牌流程完成本班发布与部署校验。RSI 摘要仅保留在内部会话。
