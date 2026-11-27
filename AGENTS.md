# Global Investment Research · Monorepo Orchestration Contract (`AGENTS.md`)

本文件是 `global-investment-research` 单仓库（Monorepo）的**顶层唯一编排宪章**，统一约束 **黄金深度研报（`gold/`）**、**全球三市权益与重点 ETF 研报（`equity/`：中国 A 股 × 中国香港股市 × 美国股市，覆盖 231 只全行业龙头 7 维机构级深研与 140+ 只跨 6 大通道重点 ETF）** 以及 **中国大陆 12 大个人多元合规投资渠道（MECE 全覆盖 + 横向「全市场打新工具箱」与「双层风控警示墙」）** 在一体化双定时任务下的协同调研、纯网页严检、跨轨门禁、受控 RSI 自我复盘与静态门户发布。

> **纯网页唯一交付原则**：本项目**仅发布纯网页静态门户（GitHub Pages）**，不编译、不托管、不链接任何离线二进制文档附件。门户首页（`index.html`）呈现 **4 大核心市场红绿灯**、小白 **「今日行动红绿灯 + 钱怎么分四笔」** 导览、**全部 12 大个人多元合规投资渠道简洁概览卡**（点击进入各自独立详情页 `channels/<id>.html`）、**5 大市场/资产分组 ETF 概览卡（底层覆盖 6 大交易通道）**（跳转预筛选 `etfs.html`）、**《新手 3 分钟指南》（`guide.html`）** 与 **站内术语白话浮窗**。
>
> **实时数值唯一真相源原则（SSOT）**：所有宪法、规则与技能文档只锁定制度口径、风控红线与计算方法，**严禁硬编码随时变动的实盘利率、收益率、溢价率、规模、点位或比例数字**；一切实时数值以 **`gold/data_snapshot.json`** 与 **`equity/state/*.json`** 为唯一真相源。

---

## 1. Monorepo 目录结构与职责边界

```text
global-investment-research/
├── AGENTS.md                        # 本文件：单仓库顶层编排宪章与跨轨硬约束
├── README.md                        # 仓库总览、纯网页 10+1 双班次节拍与本地构建说明
├── .agents/skills/                  # 全仓库统一工作区三 Skill（黄金出版 + 权益出版 + 权益编辑审校）
├── automations/                     # 共用提示词、统一权限清单和两个定时模板（Tier C 只读）
├── gold/                            # 黄金深度研报体系（跨轨 SSOT 唯一写入源）
│   ├── AGENTS.md                    # 黄金子轨永久规则
│   ├── data_snapshot.json           # 日报实时数据源、跨项目红绿灯裁决 SSOT 与 data_caveats 披露源
│   ├── master_snapshot.json         # 1971–2030 全景主报告独立锁定基线
│   ├── market_calendar.json         # 60+ 天全球跨市场休市与冬/夏令时日历
│   ├── edition_validation.py / chart_input.py / lint_readability.py（及站内 640px SVG 矢量图表模块）
│   └── daily/                       # 日报、SCORECARD、CHANGELOG、AUDIT_LOG、archive/ 按月归档与 RSI 台账
├── equity/                          # 全球三市权益、140+ ETF 雷达与 12 大多元渠道研报体系
│   ├── GEMINI.md                    # 权益子轨永久宪法
│   ├── DAILY_REPORT_SPEC.md         # 7 维大盘、7 维个股/ETF 深研、12 大多元渠道与全主刊唯一详规
│   ├── state/                       # market_state.json、multi_asset_channels.json、etf_universe.json、deep_dossiers.json、audit_ledger.md、RSI 台账
│   ├── edition_plan.py / lint_equity.py（及 21 张矢量 SVG 图表与网页渲染模块）
│   └── daily/                       # 三市日报、总看板 INDEX、SCORECARD、CHANGELOG
├── scripts/                         # 零依赖静态门户构建、严格门禁、纯网页发布与本地定时安装引擎
│   ├── build_site.py                # 零第三方依赖生成双端响应式门户（首页导览/12 独立渠道页/ETF 雷达/231 股 7 维/新手指南/记分卡/档案）
│   ├── svg_geometry.py              # SVG 矢量文本边界框解析与零碰撞/零越界几何校验引擎
│   ├── patch_state_dbs.py           # 权益三库原子合并、双账本/审计无损头插、双轨 RSI 无损追加、月初原子滚存/归档与 --inspect <target> 查库工具（防 300s 超时）
│   ├── lint_site.py                 # 6 道法证与安全门禁（S1–S6，--strict 零容忍，禁用离线附件链接）
│   ├── publish_site.py              # 源稿严检 -> 静态站构建严检 -> 限域提交推送（GitHub Pages 自动部署）
│   ├── install_sidecars.py          # 将脱敏定时模板渲染/原子安装至本机并做漂移校验
│   ├── edition_run.py               # 两个班次共用的运行记录、阶段锁、僵尸锁安全清理与 Pages 验收
│   └── web_assets/                  # 站点样式与交互脚本（含术语白话浮窗、7 维个股深研与 ETF 详情弹窗）
├── tests/                           # 零依赖全链路回归测试集
└── .github/workflows/
    └── deploy-pages.yml             # PR 与 main 分支全量回归测试、模板干跑、源稿预检与静态站构建；仅 main 自动部署 Pages
```

---

## 2. 中国大陆 12 大个人多元合规渠道 MECE 目录与数据底座

门户首页以简洁概览卡呈现全部 **12 大个人多元合规投资渠道**（统一红/黄/绿灯 + 小白一句话 + 今日避坑提醒），点击卡片直达各自独立详情页 `channels/<id>.html`（`channels.html` 提供全渠道总览），另配横向 **「全市场打新工具箱」** 与 **「双层风控警示墙」**。12 大渠道标准 ID 与边界永久统一为：

| 序号 | 渠道名称 | 标准 `id` | 核心覆盖范围 |
| :---: | :--- | :--- | :--- |
| 1 | 活钱与现金管理 | `reverse_repo` | 国债逆回购（`GC001`/`R-001`）、货币基金、现金管理类理财、同业存单 AAA 指数 |
| 2 | 人民币银行存款全家桶 | `large_cds` | 定期存款、大额存单（含二手转让与禁止二次转让规则）、结构性存款、50 万元存保红线 |
| 3 | 境内个人外币存款与外币理财 | `fx_deposits_wm` | 境内美元/港元等外币定存、外币理财、锁汇/汇兑损益测算与 5 万美元便利化额度边界 |
| 4 | 债券与债券 ETF | `bonds` | 储蓄国债、超长期特别国债、银行间短融 ETF（`511360`）、政金债/国债/交易所公司债与科创债 ETF |
| 5 | 公募基金、银行理财与基金投顾 | `funds_wm` | 真净值银行理财、短债/纯债、固收+、多资产 ETF-FOF、持牌基金投顾与 2026 公募销售费改 |
| 6 | 储蓄型商业保险 | `savings_insurance` | 增额终身寿险、养老年金、分红险（预定利率、实现率、退保现价与真实 IRR 透明测算） |
| 7 | 个人养老金与个人税优账户 | `tax_advantaged_accounts` | 个人养老金账户（1.2 万/年节税测算、Y 份额/养老储蓄/国债/保险）、税优健康险与适用税档 |
| 8 | 场内外 QDII、香港互认与理财通 | `qdii_mrf` | 场内外 QDII 额度与溢价停牌、香港北向互认基金（MRF 累计份额避税与锁汇）、跨境理财通 2.0、LOF 退市红线 |
| 9 | 可转债 | `convertible_bonds` | 转债全市场 `511380`（综合费率 0.20%/年）vs 投资级 AA+ `511180`（综合费率 0.30%/年）、个券权限、去刚兑违约排雷、强赎与到期兑付核对 |
| 10 | 公募 REITs 与不动产租金对比 | `c_reits` | 产权类（NOI/出租率/Cap Rate）vs 特许经营权类（中债 IRR）、指数基金、薄量限价与住宅租售比参照 |
| 11 | 非黄金大宗商品与白银/铂钯渠道 | `commodity_etfs` | 豆粕/有色/能化期货 ETF、白银/原油 LOF 溢价磨损退市风险、铂钯/贵金属跨市场合规渠道 |
| 12 | 合规私募与标品信托 300 万专享 | `private_funds_trust` | 合格投资者门槛、私募证券（量化/主观/套利）与标品信托费率结构、锁定期、冷静期与尽调红线 |

---

## 3. 一体化双定时任务节拍与分层刷新矩阵（CST / UTC+8）

统一运行 **每日 2 个一体化单会话定时任务**，工作日早/晚班次全面执行 **四市全主刊（All-4-Main）+ 10+1 并行调研红队 + 三大扩展数据库强制期号锁 + 纯网页发布**：

| 定时任务 ID | 触发时间（CST） | 班次定位 | 单会话串行产出与分层刷新重点 |
| :--- | :--- | :--- | :--- |
| **`daily-global-investment-research`** | **每日 `07:30`** | **一体化早报** | ① 黄金 `0730_早报`（刷新 `gold/data_snapshot.json` SSOT 并严检） → ② **A 股 / 港股 / 美股三市全发收敛主刊（`main`，≥2 张矢量图）**；同步推进 **`multi_asset_channels.json`（12 大渠道）、`etf_universe.json`（140+ ETF）与 `deep_dossiers.json`（231 股）** 至当班 `edition_id`：早班聚焦隔夜美盘/美债/汇率、美股与爱尔兰 UCITS ETF 官收、美股 QDII 溢价停牌、外币存款与理财、港股夜期盲窗、盘前逆回购/打新/转债日历及当班 4–6 只焦点股 7 维刷新 → ③ 统一 RSI 盲审 + 单次纯网页发布 |
| **`daily-global-investment-research-evening`** | **每日 `18:00`** | **一体化晚报** | ① 黄金 `1800_晚报`（刷新 `gold/data_snapshot.json` SSOT 并严检） → ② **A 股 / 港股 / 美股三市全发收敛主刊（`main`，≥2 张矢量图）**；封账 A/港日终官收、中金所/南向/16:30 汇率与美股今早盘后终盘，同步推进三大扩展数据库至当班 `edition_id`：晚班聚焦债券 ETF/逆回购日终利率、可转债与 REITs 日终估值、非金商品 ETF 收盘、场内 QDII 日终溢价与停牌公告及当班 4–6 只焦点股 7 维刷新 → ③ 统一 RSI 盲审 + 单次纯网页发布 |
| **周六 / 周日** | **周末专项 / 周度校准** | **休市与深研轮换** | 周六 `07:30` 黄金周末专项主刊 + 美股周五复盘主刊（美股半日市发 `holiday_watch` 含 ≥1 图，美股全休沿用旧稿）；周六晚与周日三市默认沿用旧稿，**周日执行全量周度校准**：更新 12 大渠道中低频项（大额存单、外币定存、储蓄保险、个人养老金、私募信托、租金对比）、全量核对 140+ ETF 费率规模、轮换精修 231 股池中的 **6–10 只核心龙头 7 维档案**并推进 `SCORECARD.md` 公开记分卡周频复盘 |

> 每班启动必须执行 `python3 equity/lint_equity.py --plan <edition_id>` 获取具体市场、刊型（`main` / `holiday_watch`）与沿用安排。

---

## 4. 单会话严格顺序流水线（Step 0 → Step 5 · 纯网页极速版）

每次 `07:30` 或 `18:00` 一体化班次必须严格按以下顺序在同一会话内串行推进，严禁跳步或乱序：

- **运行锁、单向时间窗、僵尸锁清理与维护者专属运维命令**：定时入口运行 `scripts/edition_run.py begin --scheduled 0730` 或 `--scheduled 1800`，**定时运行窗与单向截点宽限统一为 `[-5 分钟, +6 小时]`（`07:25–13:30` / `17:55–次日 00:00` CST；黄金截点须早于或同分钟于权益且跨轨差值 `0–6 小时`）**。`begin --scheduled` 会先尝试收尾已有推送凭据的班次，并自动清理**严格较早期号**、超 2 小时无进展且尚未进入推送的僵尸锁。收到 token 后才进入调研；依次登记 `gold`、`equity`、`publish`，有进展时用 `heartbeat` 刷新时间。若历史已推送班次被后续提交覆盖，维护者可人工区分 **`complete-superseded`**（校验目标提交已是现网祖先且仅含授权文件变更后结案为 `complete`）与 **`close-superseded`**（将其标为 `superseded` 释锁）——**两项均为维护者专属手动运维命令，严禁纳入定时自动化 `automations/permissions.json` 白名单**。
- **期号交接与三库同期锁**：当班黄金快照、黄金日报 `DAILY_META`、权益状态、新权益稿 `DAILY_META_JSON` 以及三大扩展数据库（`multi_asset_channels.json`、`etf_universe.json`、`deep_dossiers.json`）记录同一 `edition_id`。黄金日报同时记录与快照一致的 `as_of_short`。休市沿用旧稿时保留旧稿期号与时间，状态与三大数据库仍刷新至当班期号。

1. **Step 0｜双轨 RSI 经验库冷启动**：
   - 读取 `gold/daily/RSI_PLAYBOOK.md`（≤180 行）、`equity/state/RSI_PLAYBOOK.md`（≤180 行）及两轨 `rsi_metrics.json` 最近记录。
2. **Step 1｜跨市场日历、基线快照与三大深研库冷启动**：
   - 读取 `gold/market_calendar.json`、`gold/data_snapshot.json`、`gold/master_snapshot.json`、`equity/state/market_state.json`、`equity/state/multi_asset_channels.json`、`equity/state/etf_universe.json`、`equity/state/deep_dossiers.json`、两轨 `SCORECARD.md`、`gold/daily/CHANGELOG.md` 与 `equity/daily/INDEX.md`。
3. **Step 2A｜共享 10 路并行 `research` 深度调研（10+1 架构）**：
   - 启动 **10 路只读 `research` 子代理**（每路回执严控 `≤ 12 KB` 紧凑表格防拖尾）：① 黄金与贵金属、② 中国 A 股、③ 中国香港股市、④ 美国股市、⑤ 跨资产宏观汇率与大宗、⑥ 三地社区与谣言辟谣、**⑦A 境内活钱/存款/债券/基金理财/储蓄保险/个人养老金专线**、**⑦B 境内外币/QDII与MRF/可转债/C-REITs/非金商品与白银铂钯/私募信托与打新反诈专线**、**⑧A 全市场 140+ 重点 ETF 分批溢价/停牌/规模/费率专线**、**⑧B 当班全部焦点股（约 16 只及周日 6–10 只全池轮换）7 维深研与近 24 小时官方公告硬扫雷专线**（必查沪深/港交所/SEC 近 24 小时折价配售、分红、管理层变动与信用评级观察，现价实算股息/估值并刷新 `updated_at`）。遇单项数据未发布或暂不可取时严禁编造、亦不阻塞发布，按规范挂账并写入纯读者中文 `data_caveats`。
4. **Step 2B｜1 路统一发前红队对抗核验（10+1 架构）**：
   - 跨轨交叉审计共享宏观数字与 **T-0 宏观官源四铁律**（日本 CPI 直核 `stat.go.jp` 区分日央行版剔生鲜能源[权重 9162]与欧美版剔全部食品能源[权重 6959]；香港金管局查当日总结余及未来两日预测；上期所夜盘严分 `02:30` 金银/`01:00` 有色/`23:00` 黑色化工且 LME 严守 17:00 同盘口；高溢价 QDII 严分暂停申购/仅恢复赎回与恢复申赎）、黄金红灯全载体锁、A/H 物理一致、100% 配置闭环、12 大多元渠道制度与风险红线、140+ ETF 6 通道分类与跨库费率防错（含 `511380` 0.20% vs `511180` 0.30%）、`CHART_A2` 贴水正号与红涨青跌色、焦点股 7 维近 24 小时公告/现价实算与小白友好白话清晰度。
5. **Step 3｜黄金 SSOT 优先落盘与 6 门禁严检（纯网页）**：
   - 先用 `write_file` 全量更新 `gold/data_snapshot.json`（含纯读者中文 `data_caveats`）、当期黄金日报 Markdown 与 `gold/daily/SCORECARD.md`；跨月归档上月黄金账本时先写 `gold/daily/_archive_patch.json` 并调用预授权 `scripts/patch_state_dbs.py --archive-gold-ledgers` 无损归档；持续增长的历史双账本（`gold/daily/CHANGELOG.md`、`gold/daily/AUDIT_LOG.md`，含本期 `GOLD_EDITION_REVIEW` 标记）通过 `write_file` 写微型补丁 `gold/daily/_ledger_patch.json` 并调用预授权 `scripts/patch_state_dbs.py --prepend-gold-ledgers` 无损头插（防 300s 超时；自动校验 `GOLD_EDITION_REVIEW` 全量 Schema——含 `as_of_short`/`note`/四关 HTTPS `sources` 及 `forecast_review.status ∈ {"settled","none_due","pending_evidence"}`、支持跨月空锚回退并锁定 `0o644` 权限）。仅命中 5 大阈值时同步主报告与 `master_snapshot.json`。
   - 运行：`python3 gold/lint_readability.py --strict <本刊路径>`（必须 `0 errors, 0 warnings`）。
6. **Step 4｜全球权益三市、12 大多元渠道、140+ ETF 与 231 股 7 维深研库接力落盘与严检（纯网页）**：
   - 只读校验本期黄金快照（两轨截点均须在所标班次 `[-5 分钟, +6 小时]` 单向窗口内且黄金早于或同分钟于权益、差值 `0–6 小时`）和 Tier-0 行动互斥锁。用 `write_file` 全量落盘本期日报 Markdown、`INDEX.md`（纯网页/Markdown 链接，禁用离线附件链接）、`CHANGELOG.md`、`SCORECARD.md` 与 `state/market_state.json`（含 `data_caveats`）；月初遇 `--plan` 切换 `period_slug` 时写紧凑 `equity/state/_rollover_patch.json` 并调用预授权 `scripts/patch_state_dbs.py --rollover-equity-month` 原子克隆三旗舰与 `_latest.md` 并更新 `report_meta_*.json`（杜绝 636 KB 全写超时）；持续增长的 `state/audit_ledger.md` 写 3 键 `equity/state/_audit_patch.json` 经 `scripts/patch_state_dbs.py --prepend-equity-audit` 无损头插；**权益三大扩展大 JSON（`state/multi_asset_channels.json`、`state/etf_universe.json`、`state/deep_dossiers.json`，合计 ~830 KB）统一写微型补丁 `equity/state/_edition_patch.json` 并调用预授权 `scripts/patch_state_dbs.py --apply` 原子合并（只读查库用 `--inspect <target>`，支持 `channels`/`channel:<id>`/`etf:<code>`/`stock:<key>`/`stale-dossiers`/`ah-benchmarks`/`etf-freshness`），强制同步 `edition_id`，并执行跨库费率一致性护栏、兄弟字段与 A/H 孪生股一致性校验、诚实单股 `updated_at`（严禁批量刷写未核查股票）以及 12 大渠道（含小白一句话、今日避坑与红/黄/绿灯）、140+ ETF 与 231 股零模板化 7 维深研全检**。
   - 运行：`python3 equity/lint_equity.py --strict`（校验源稿、21 张 SVG 防重叠与 `CHART_A2` 贴水正号、三大深研库、跨项目黄金 SSOT 与旗舰 Markdown 同步，必须 `0 errors, 0 warnings`）。
7. **Step 5｜统一 RSI 盲审闭环（5 项真核验）+ 单次纯网页门户发布**：
   - 启动 **1 路独立只读 `research` 盲审子代理**，按两轨各 6 维 `/30` 打分（第 4 维聚焦**纯网页视觉清晰度、SVG 零碰撞与小白 3 分钟可读性**）、预判验真并执行 **5 项真核验**（含焦点股近 24 小时公告扫雷、6 维逐项拆解、三市分情景依据、宏观官源四铁律与 `screener.html` 鲜度卡片↔7 维弹窗一致），通过 `scripts/patch_state_dbs.py --append-gold-rsi` 与 `--append-equity-rsi` 无损追加双轨 `rsi_metrics.json` 并更新两份 `RSI_PLAYBOOK.md`（`findings` 支持 `resolved`、`deferred_data`、`disclosed_caveat`；仅 `open` 或未修硬错拦截发布）。
   - 复跑 `gold/lint_readability.py --strict` 与 `equity/lint_equity.py --strict`，随后进入 `publish` 阶段运行 `python3 scripts/publish_site.py --edition-token <token>`（构建完整静态门户——首页 4 市场 + 小白导览 + 12 大渠道概览卡 + 5 大市场/资产分组 ETF 概览卡【底层覆盖 6 大交易通道】、12 个独立 `channels/<id>.html` 详情页、`channels.html`、`etfs.html`、`screener.html`、`guide.html`、`scorecard.html`、`archive.html`——通过 S1–S6 严检后单提交推送至 `origin/main`），最后运行 `python3 scripts/edition_run.py complete <token>` 验证 GitHub Pages 实际部署成功即闭环。

---

## 5. 跨轨硬不变式（Hard Cross-Track Invariants）

1. **黄金 SSOT 唯一写入权 + Tier-0 行动互斥锁**：
   - `gold/data_snapshot.json` 仅允许黄金轨（Step 3）写入，权益轨（Step 4）严格只读校验；
   - 当 `tier_code == "Tier 0"` 或 `new_buy_allowed == false` 时，全仓库公开正文、三大扩展 JSON 与全站网页（含首页、`channels.html`、`channels/*.html`、`etfs.html`、`screener.html`、`guide.html`）严禁出现新买/补齐黄金指令或将黄金/金矿标的标为绿色底座（由 `equity/lint_equity.py` Gate C2 与 `scripts/lint_site.py` Gate S6 强制阻断）。
2. **纯网页零离线附件交付与首页全渠道透明**：
   - 全站严禁输出或链接任何离线二进制文档附件（由 `scripts/lint_site.py` Gate S2 与 `equity/lint_equity.py` Gate 4 强制阻断）；
   - 门户首页 `index.html` 必须清晰呈现四大核心市场、小白导览、全部 12 大个人多元渠道概览卡（直链各独立详情页 `channels/<id>.html`）与 5 大市场/资产分组 ETF 概览卡（底层覆盖 6 大交易通道）（由 `scripts/lint_site.py` Gate S6 强制核验）。
3. **跨轨核心合规与费率口径完全统一**：
   - **黄金联接 `008142` / `008143`**：依据 2026 公募销售费改（商品基参照债基），A 类申购上限 0.30%（1 折 0.03%，旧合同过渡期 0.06%）、运营费 0.20%/年；C 类销售服务费上限 0.20%/年且自 2027-01-01 起满 1 年“先收后返”免收，但长持 ≥1 年仍以 1 折 A 类（`008142`）更省；现行尚未完成整改的旧合同 `008143` 仍按 0.55%/年（含 0.35% 销服费）且满 30 天免赎回费（严禁误写 7 天免赎回）；
   - **可转债 ETF 费率区分**：全市场可转债 ETF **`511380`** 综合费率为 **0.20%/年**（管理 0.15%+托管 0.05%），而投资级上证可转债 ETF **`511180`** 综合费率为 **0.30%/年**（管理 0.25%+托管 0.05%），严禁跨库混写费率；
   - **MRF 禁推停申基金**：严禁推荐已暂停申购的 `968118`；
   - **二手大额存单**：多数国有大行禁止二次转让，且二手接盘单严禁直接提前支取（否则仅按原票面本金 + 活期计息致本金实亏）；
   - **债券 ETF 底层税负区分**：交易所公司债/科创债 ETF 底层债券付息环节仍扣 20% 税（区别于银行间市场的短融 ETF `511360` 等银行间标的）；
   - **离岸资产与跨境合规**：中国居民个人境外所得须依法按 20% 全球申报纳税（含 CRS 金融账户涉税信息自动交换透明合规）；香港挂牌的 `02840.HK` 底层为美国注册信托，计入非美居民 6 万美元美国遗产税应税范围，大额离岸黄金（黄灯解锁后）应改选爱尔兰 `IGLN.L` 或香港本土注册实物金 `03081.HK`。
4. **小白友好三层写作与零本地路径/内部词泄露**：
   - 确立 **「30 秒红绿灯白话结论 → 10 万/1 万元钱包实算与三步怎么买 → 机构级 7 维硬核证据」** 三层结构；`DXY`/`COT`/`CDS`/`ERP`/`IRR` 等专业词移出“可不解释裸用”名单，首现配简短白话括注或交由站内术语浮窗解释；禁用居高临下说教口号，鼓励平等温和的「3 分钟速读结论」「关键词白话速查」；
   - 所有公开文件与生成静态网页严禁出现本地绝对路径、密钥或内部工程/脚本/RSI 文件名（由 `scripts/lint_site.py` Gate S3 严守）。
5. **无人值守分级写盘、预授权绝对路径裸命令与三道严格门禁零容忍**：
   - 定时无人值守任务严禁调用 `edit_file`：中小 Markdown 与轻量快照（日报、记分卡、`INDEX.md`、`data_snapshot.json`、`market_state.json`、`RSI_PLAYBOOK.md` 等）一律使用 `write_file` 全量写盘；**权益三大扩展大 JSON（合计 ~830 KB）、黄金历史双账本（`CHANGELOG.md` / `AUDIT_LOG.md` 及跨月归档）、权益审计账本（`audit_ledger.md`）、三市旗舰月初滚存与双轨 `rsi_metrics.json` 统一走预授权 `scripts/patch_state_dbs.py` 增量原子命令（`--apply` / `--prepend-gold-ledgers` / `--prepend-equity-audit` / `--append-gold-rsi` / `--append-equity-rsi` / `--rollover-equity-month` / `--archive-gold-ledgers` / 只读 `--inspect <target>`）**，彻底杜绝 300s 流式超时；所有命令行操作仅运行 `sidecar.json` 预授权的绝对路径裸命令；
   - 交付与发布前，以下**三道严格门禁必须全部退出码 `0`（`0 errors, 0 warnings`）**：
     - `python3 gold/lint_readability.py --strict gold/daily/<最新黄金日报>.md`
     - `python3 equity/lint_equity.py --strict`
     - `python3 scripts/build_site.py --out _site && python3 scripts/lint_site.py _site --strict`
6. **准点发刊不阻塞与信息缺口全透明（Anti-Blocker & Data-Caveats Transparency）**：
   - 定时运行窗与单向截点宽限均为 **`[-5 分钟, +6 小时]`**（黄金早于或同分钟于权益且跨轨差值 `0–6 小时`）；`begin --scheduled` 自动清理**严格较早期号**、超 **2 小时**无进展且尚未进入推送的僵尸锁；
   - 两轨同步维护纯读者中文、零内部文件名的结构化 **`data_caveats`** 数组，在首页与日报页自动披露信息缺口及对核心裁决的影响。

---

## 6. 子轨权威契约与工作区技能索引

- **黄金子轨规则与格式宪章**：[gold/AGENTS.md](gold/AGENTS.md) · [gold/daily/AGENTS.md](gold/daily/AGENTS.md) · [gold/daily/DAILY_FORMAT_SPEC.md](gold/daily/DAILY_FORMAT_SPEC.md) · [gold/daily/RSI_PLAYBOOK.md](gold/daily/RSI_PLAYBOOK.md)
- **权益、12 大多元渠道与 7 维深研宪法与排版详规**：[equity/GEMINI.md](equity/GEMINI.md) · [equity/DAILY_REPORT_SPEC.md](equity/DAILY_REPORT_SPEC.md) · [equity/state/RSI_PLAYBOOK.md](equity/state/RSI_PLAYBOOK.md)
- **统一工作区三 Skill（`.agents/skills/` · Tier C 只读）**：
  - [.agents/skills/gold-research-publishing/SKILL.md](.agents/skills/gold-research-publishing/SKILL.md)
  - [.agents/skills/equity-report-publishing/SKILL.md](.agents/skills/equity-report-publishing/SKILL.md)
  - [.agents/skills/equity-research-editorial-qa/SKILL.md](.agents/skills/equity-research-editorial-qa/SKILL.md)
- **共享提示词、授权和定时安装（Tier C 只读）**：[定时提示词](automations/unified-edition.prompt.md) · [授权配置](automations/permissions.json) · `automations/sidecars/*.template.json` · [安装器](scripts/install_sidecars.py)
