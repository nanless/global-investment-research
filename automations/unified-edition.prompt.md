你正在执行北京时间 __RUN_SLOT__ 班次的黄金、全球三市股票（140+ 重点 ETF 与 231 股 7 维深研）及中国大陆 12 大个人多元合规投资渠道联合研报。工作区为 __REPO_ROOT__，这是一个新会话。本项目采用**纯网页静态门户唯一交付（禁生成、托管或链接离线文档附件）**：首页呈现 4 大市场红绿灯、小白「今日行动红绿灯 + 钱怎么分四笔」导览、全部 12 大多元渠道概览卡（直链独立页 `channels/<id>.html`）、5 大市场/资产分组 ETF 概览卡（跳转预筛选 `etfs.html`）、《新手 3 分钟指南》（`guide.html`）与术语白话浮窗。严格按阶段 0 至阶段 4 执行，失败留证并报告缺失；终报用中文，写明交易日与数据截点。

## 阶段 0｜抢锁、出刊计划与 300 秒载荷防超时铁律

1. **抢锁与时间窗**：运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py begin --scheduled __RUN_SLOT__`（允许窗 `[-5m, +6h]`：早班 07:25–13:30、晚班 17:55–次日 00:00 北京时间）。仅在返回 JSON 同时含 `edition_id` 与 `token` 后继续。命令会先收尾已有推送凭据的班次，并自动清理较早期号超 2 小时无进展且未推送的僵尸锁。锁被占、时段不对、同期已完成或失败立即停写并报尝试编号；定时会话禁执行 `recover`、`resume`、改日期、造修订号或绕权限。
2. **出刊计划与冷启动**：运行 `__PYTHON_BIN__ __REPO_ROOT__/equity/lint_equity.py --plan <edition_id>` 获取各市刊型（工作日 07:30/18:00 原则上四市均发收敛主刊 `main`，休市/半日市与周末依计划发 `holiday_watch` 或沿用）。读顶层 `AGENTS.md`、双轨规则、三项 Skill、双日历、现有快照、挂账、两份 `RSI_PLAYBOOK.md` 与上期观察项；确认官方日历覆盖本期，有冲突先纠偏或报阻塞。
3. **300 秒载荷防超时铁律**：
   - **三库大 JSON 禁全量重写**：`multi_asset_channels.json`、`etf_universe.json`、`deep_dossiers.json` 一律只用 `write_file` 写增量补丁 `equity/state/_edition_patch.json`，由 `__PYTHON_BIN__ __REPO_ROOT__/scripts/patch_state_dbs.py --apply` 原子合并、全检并自动删补丁；
   - **黄金双账本禁全量重写**：`gold/daily/CHANGELOG.md` 与 `AUDIT_LOG.md` 一律只用 `write_file` 写增量补丁 `gold/daily/_ledger_patch.json`，由 `__PYTHON_BIN__ __REPO_ROOT__/scripts/patch_state_dbs.py --prepend-gold-ledgers` 无损头插、数学保序自证并自动删补丁；
   - **中小文件单份写盘**：其余 Markdown/JSON 用 `write_file` 每次只写一份（无人值守禁 `edit_file`），严控单次体积。中断后先查磁盘与运行账本，未完成文件聚焦重试一次并沿用已获证据；再败则留证按阶段 4 收尾。进展节点调用 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py heartbeat <token>` 续期。所有 Python 均独立执行预授权绝对路径命令，零 shell 拼接符，禁改规则或填造数据。
4. **分层刷新与三库期号锁**：每班三库顶层 `edition_id` 必同步当班期号，12 渠道须核验小白一句话、今日避坑与红/黄/绿灯，禁模板空话。**07:30 早班**：隔夜美欧/美债/汇率/原油、美股与爱尔兰 UCITS ETF、美股 QDII 溢价停牌、外币存理、港股夜期校正、盘前逆回购/打新/转债日历、4–6 只焦点股 7 维；**18:00 晚班**：A/港日终官收与中金所/南向/16:30 汇率、美股盘后终盘、债基 ETF/逆回购/转债/REITs/非金商品与白银原油 LOF 溢价退市、场内 QDII 日终溢价与次日临停、4–6 只焦点股 7 维；**周末/周日**：周六 07:30 黄金周末专项与美股周五复盘，周日全量校准 12 渠道中低频项（大额存单、外币定存、储蓄保险 IRR、个人养老金、私募信托、租金对比）、140+ ETF 费率规模、轮换精修 6–10 只核心龙头 7 维并更新 `SCORECARD.md`。

## 阶段 1｜10 路 4 段式调研与独立红队四重机构级交叉验证（10+1）

启动 **10 路只读 research 子代理**，共享同一截点与日历，一手官源优先：① 黄金与贵金属；② 中国 A 股；③ 中国香港股市；④ 美国股市；⑤ 跨资产宏观汇率与大宗（必回传 1 句 **利率→汇率→信用→大宗→股票风险溢价（ERP）跨资产传导链** + **未来 48 小时上行/下行双向催化触发线**）；⑥ 三地社区与谣言辟谣；⑦A 境内稳健与税优 6 渠道（`reverse_repo`/`large_cds`/`bonds`/`funds_wm`/`savings_insurance`/`tax_advantaged_accounts`）；⑦B 跨境/增强/另类 6 渠道（`fx_deposits_wm`/`qdii_mrf`/`convertible_bonds`/`c_reits`/`commodity_etfs`/`private_funds_trust`）+ 全市场打新工具箱与双层风控警示墙；⑧A 跨 6 通道 140+ 重点 ETF（支撑首页 5 大市场/资产分组 ETF 概览卡与 `etfs.html`）；⑧B 当班 4–6 只焦点股（周日 6–10 只）7 维深研（必按当期现价实算 **实际股息率 = 年化每股分红 ÷ 现价** 与 **同口径市盈率**，杜绝沿用过期记忆值）。

**每路强制 4 段式回执**：1) **核心硬数据表**（品种、数值、涨跌、交易日、观测时间与时区、盘中/官收口径、来源 URL）；2) **异动归因与正反证**（主因、可复算公式、≥1 条证伪条件）；3) **渠道/税费/溢价/谣言提醒**（港股代码 5 位补零如 `03081.HK`）；4) **缺口与待补清单**（未发布/冲突项的原因、本期处置与下班复核，禁编造、不阻断发刊，入挂账与 `data_caveats`）。容量不足分批跑满十路，单路一启一重试，最多两轮（每轮约 10 分钟）；权限/配额错直接记阻塞。

**独立只读红队四重交叉验证**：十路齐全后另起独立红队（缺红队停发；仅中断未交卷可同班换一路），逐项落盘四重核验：
1. **源数据双向对账**：区分原文直读、搜索摘要与失败源，核验官收白名单、交易日与 `[-5m, +6h]` 实际可得时点，拦截盘中高点/旧价冒充官收；
2. **6 组公式与时区物理核对**：① 上金所同分钟国内溢价；② `2Y−FF` 利差与 `DFII10`；③ 10 点概率条与家庭模板精确求和 `100%`；④ AH 比价与估值物理锁；⑤ 冬/夏令时、CME 复盘时刻及 07:30 美股早刊禁写 09:00/08:00 盘后终盘的时间穿越拦截；⑥ 跨资产比值、渠道价差、税后净息、实际股息率与复权除息；
3. **论点-论据-反证闭环（禁空话、禁拍脑袋概率）**：每项结论绑一手证据与量化失效线，10 点概率条须给全四情景拆分与理由（禁偷懒只写单边 `7/10`），配齐 48 小时上行/下行双向应对剧本；旧预判严格按原判据结案，禁事后重归类；
4. **跨轨红线税费、图表符号与机构级读感**：复核黄金红灯全载体互斥锁（正文/12 渠道/140+ ETF/231 股/SVG）、`008142`/`008143` 费率（2026 费改与旧合同 `008143` 0.55%/满 30 天免赎回）、可转债 ETF 费率区分 `511380`（0.20%/年）vs `511180`（0.30%/年）、`CHART_A2` 期货贴水须为正数 `ann_disc > 0`、禁推停申 `968118` 与退市 `00011`、二手存单禁二次转让与提前支取实亏、交易所公司债 ETF 底层 20% 税区别于银行间 `511360`、中国居民 20% 境外所得与 CRS 合规、`02840.HK` 美国遗产税改选 `IGLN.L`/`03081.HK`；落实小白三层结构、`DXY`/`COT`/`CDS`/`ERP`/`IRR` 首现括注、反复读红线（同一核心数字正文提及 ≤3 次，标题与导语禁「旧缺口清零/核销成绩单」类后台审计腔）、`SCORECARD.md` 仅登可证伪投资预判（禁混入后台数据回补工单），禁用说教口号与内部工程词。

## 阶段 2｜黄金 SSOT 优先落盘、无损账本头插与严检（纯网页）

1. 运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py advance <token> gold`。
2. 锁定截点，先用 `write_file` 更新 `gold/data_snapshot.json`（含纯中文、零内部文件名的 `data_caveats`），再写本班黄金日报 Markdown 与 `gold/daily/SCORECARD.md`（写齐四关证据、四固定 ID 与期号标记；核验导语信号/噪音条数与 `DAILY_SIGNAL_NOISE` 数组长度精确一致，正文禁塞冗余「挂账核销成绩单」表；仅命中 5 大触发阈值时同步主报告与 `master_snapshot.json`）。
3. **Cboe VIX 与沿用口径**：核对最近 10 个已完成交易日 Cboe 官方日收。遇 `VIX_History.csv` 滞后或暂不可取时不阻塞发刊：优先采信 Cboe 官网产品页（或 ≥2 家权威源一致）16:15 美东官收入末行并标 `vix_daily_row_checks[day].status = "provisional_close"`（记 URL、查询时刻与说明）；收盘亦不可核则标 `"pending"` 沿用最近 10 个已发布 CSV 日收，在正文、台账、`data_caveats` 与终报披露，下班清零。半日市受 `provisional_close`，全休市 `no_row_confirmed` 受官告或 CSV 后续交易日自证。无有效窗口盘中报价时两轨留空盘中值与时间，沿用官收标原交易日，单报价不外推高低。
4. **无损账本头插**：用 `write_file` 写 `gold/daily/_ledger_patch.json`（`edition_id`、`changelog_entry_md`、`audit_review_block_md`、可选 `audit_source_index_md`；其中 `GOLD_EDITION_REVIEW` JSON 必填 `edition_id`、`as_of_short`、`note`、四关 HTTPS `sources` 及 `forecast_review`，且 `forecast_review.status` 仅允许 `settled`、`none_due`、`pending_evidence`，严禁 `"tracked"`），运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/patch_state_dbs.py --prepend-gold-ledgers` 无损头插 `CHANGELOG.md` 与 `AUDIT_LOG.md` 并完成 100% 历史行保序自证（跨月归档至 `gold/daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md` 同样须保序）。
5. 运行 `__PYTHON_BIN__ __REPO_ROOT__/gold/lint_readability.py --strict <本刊绝对路径>`（同步主报告时一并传入），须退出码 `0`（`0 errors, 0 warnings`）。

## 阶段 3｜权益三市与三库增量原子合并接力（纯网页）

1. 运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py advance <token> equity`（同步预检黄金快照期号与工作树黄金双账本保序）。
2. 黄金快照严格只读。按计划用 `write_file` 落盘 `equity/state/market_state.json`（含纯中文 `data_caveats`）、三市日报 Markdown、`INDEX.md`（禁离线附件链接）、`CHANGELOG.md`、`SCORECARD.md` 与 `audit_ledger.md`。每篇三市主刊强制包含：**6 维体检拆解分项**、**利率→汇率→信用→大宗→ERP 跨资产传导**、**未来 48 小时上行/下行双向催化剧本**、**10 万/1 万元情景回撤压力实算**、**4–6 只焦点股 × 5 项硬核锚点（估值/股息/财报/证伪线/替身与 `deep_dossiers.json` 100% 同步）**；`CHART_A2` 贴水 `ann_disc` 须填正数（贴水正、升水负）；若发生前刊勘误须联动更新 `SCORECARD.md` 与 `INDEX.md`。无新刊沿用旧稿；旗舰跨月同步 `_latest.md` 字节一致且网址不断链。
3. **三库增量原子合并**：用 `write_file` 写紧凑补丁 `equity/state/_edition_patch.json`（同步扫清修改标的关联兄弟字段与 A/H 双地孪生股口径；严守每只股票诚实 `updated_at`，仅更新本期实审标的，绝不批量刷写未核查股票日期），运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/patch_state_dbs.py --apply` 完成三库原子合并、统计重算、跨库费率与黄金红灯互斥锁全检及补丁清理。
4. 运行 `__PYTHON_BIN__ __REPO_ROOT__/equity/lint_equity.py --strict`，核验源稿、21 张 SVG 防重叠、三库、跨项目黄金 SSOT 与旗舰同步，须 `0 errors, 0 warnings`。

## 阶段 4｜对抗式独立盲审（4 项真核验）、纯网页推送与 Pages 上线闭环

1. **对抗式独立只读盲审**：另起独立只读审稿人，按两轨 6 维 `/30` 打分（第 4 维聚焦纯网页清晰度、SVG 零碰撞与小白 3 分钟可读性）并回验旧预判，强制完成 **4 项真核验**：
   - **真核验一（跨载体数字与红灯锁）**：核对黄金快照、权益状态、三库 JSON、`INDEX.md`、`SCORECARD.md`、正文与图表参数，确认期号、点位、截点与黄金红灯锁零冲突；
   - **真核验二（算术、税费与受限代码）**：复算同刻溢价、`2Y−FF`、模板 100% 权重、10 点概率条，核查 `03081.HK` 5 位补零与受限代码 `968118`/`968001`/`00011` ±40 字避坑护栏；
   - **真核验三（小白可读性与缺口诚实度）**：确认 30 秒白话结论清晰、零说教口号、零内部工程词、零本地路径泄露，`data_caveats` 与挂账闭环；
   - **真核验四（图表符号、跨库费率、焦点股对账与反复读）**：核验 `CHART_A2` 贴水正号、`511180`（0.30%）vs `511380`（0.20%）跨库费率一致、焦点股正文与 `deep_dossiers.json` 股息/估值完全一致、兄弟字段与 A/H 孪生股同步、48 小时双向剧本完整、同一核心数字复读 ≤3 次且标题/导语零后台审计腔。
2. **盲审落盘与闭环门控**：盲审返回后，向两轨 `rsi_metrics.json` 追加本期记录（`run_id == edition_id`，不改写历史错），含 `review_closure: {"reviewer_completed": true, "findings": [...]}`：未修标 `open` 并停发；已修复验标 `resolved`；确未发布/源不可取标 `deferred_data`（含 `source` URL、未来 `due_edition`、`disposition`）；非阻断分歧/薄量且已入 `data_caveats` 标 `disclosed_caveat`（含必填 `disposition` 及可选合法 `source`/未来 `due_edition`）。硬错禁豁免，修正后先黄金后权益复跑严检。两份 `RSI_PLAYBOOK.md` 各 `≤180` 行（Tier B 凭验证依据，Tier C 只提案，禁改程序取巧）。
3. **纯网页推送与排障**：运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py advance <token> publish`，再执行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/publish_site.py --edition-token <token>`（提交前自动预检黄金账本历史、禁提交补丁、构建全站静态门户——首页 4 市场 + 小白导览 + 12 渠道概览卡与 12 独立 `channels/<id>.html` + 5 大市场/资产分组 ETF 概览卡 + `channels`/`etfs`/`screener`/`guide`/`scorecard`/`archive` 及全部报告页——过 S1–S6 严检后原子推送至 `origin/main`）。构建或门禁报错时可用 `__PYTHON_BIN__ __REPO_ROOT__/scripts/build_site.py --out __REPO_ROOT__/_site`、`__PYTHON_BIN__ __REPO_ROOT__/scripts/lint_site.py __REPO_ROOT__/_site --strict` 及必要时 `__PYTHON_BIN__ -m unittest discover -s __REPO_ROOT__/tests` 排障，修正并复跑双轨严检后重试 `publish_site.py`。推送后临时故障仅续同 token 与同提交最多一次；身份/冲突/远端不明立即停手。
4. **Pages 验真与收尾**：推送成功后运行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py complete <token>` 验真 GitHub Pages 部署上线即闭环。返回等待最多复查一次，仍等待报待部署并保锁。已开始推送后的异常保锁并报尝试编号；明确未开始推送且不再继续时才执行 `__PYTHON_BIN__ __REPO_ROOT__/scripts/edition_run.py fail <token> <具体原因>`。

最终中文汇报：黄金、三市权益、12 大渠道、140+ ETF 与焦点股 7 维的实际出刊/沿用状态、交易日与数据截点、核心结论；单列数据缺口清单（项目、原因、本期处理、下班复核）；说明推送与 Pages 上线状态（达“完成”才给上线结论）。严禁输出 token、本机权限或绝对路径。

站点入口：https://nanless.github.io/global-investment-research/
