# Global Investment Research · Monorepo Orchestration Contract (`AGENTS.md`)

本文件是 `global-investment-research` 单仓库（Monorepo）的**顶层唯一编排宪章**，统一约束 **黄金深度研报（`gold/`）**、**全球三市权益与重点 ETF 研报（`equity/`：中国 A 股 × 中国香港股市 × 美国股市，覆盖 231 只全行业龙头 7 维深研与 106 只三通道重点 ETF）** 以及 **中国大陆 8 大个人多元合规投资渠道（债券 / 公募基金与理财 / 国债逆回购 / 场内外 QDII 与北向互认 / 大额存单 / 可转债 / 公募 REITs / 非黄金大宗商品 ETF）** 在一体化双定时任务下的协同调研、纯网页严检、跨轨门禁、受控 RSI 自我复盘与静态门户发布。

> **纯网页唯一交付原则**：本项目**仅发布纯网页静态门户**（GitHub Pages，`index.html` 首页完整详列四大核心市场、全部 8 大个人多元投资渠道最新情况与全球重点 ETF 雷达），**不编译、不托管、不链接任何 PDF、Word（`.docx`）或 GitHub Releases 离线附件**。

---

## 1. Monorepo 目录结构与职责边界

```text
global-investment-research/
├── AGENTS.md                        # 本文件：单仓库顶层编排宪章与跨轨硬约束
├── README.md                        # 仓库总览、纯网页 8+1 双班次节拍与本地构建说明
├── .agents/skills/                  # 全仓库统一工作区三 Skill（黄金出版 + 权益出版 + 权益编辑审校）
├── automations/                     # 共用提示词、统一权限清单和两个定时模板（Tier C 只读）
├── gold/                            # 黄金深度研报体系（跨轨 SSOT 唯一写入源）
│   ├── AGENTS.md                    # 黄金子轨永久规则
│   ├── data_snapshot.json           # 日报实时数据源、跨项目红绿灯裁决 SSOT 与 data_caveats 披露源
│   ├── master_snapshot.json         # 1971–2030 全景主报告独立锁定基线
│   ├── market_calendar.json         # 60+ 天全球跨市场休市与冬/夏令时日历
│   ├── edition_validation.py / chart_input.py / build_daily.py / build_report.py / lint_readability.py
│   └── daily/                       # 日报、SCORECARD、CHANGELOG、AUDIT_LOG、archive/ 按月归档与 RSI 台账
├── equity/                          # 全球三市权益、ETF 雷达与 8 大多元渠道研报体系
│   ├── GEMINI.md                    # 权益子轨永久宪法
│   ├── DAILY_REPORT_SPEC.md         # 7 维大盘、7 维个股/ETF 深研、8 大多元渠道与全主刊唯一详规
│   ├── state/                       # market_state.json、multi_asset_channels.json、etf_universe.json、deep_dossiers.json、audit_ledger.md、RSI 台账
│   ├── edition_plan.py / lint_equity.py / pdf_common.py / build_*（为静态站提供矢量 SVG 图表与 HTML 渲染）
│   └── daily/                       # 三市日报、总看板 INDEX、SCORECARD、CHANGELOG
├── scripts/                         # 零依赖静态门户构建、严格门禁、纯网页发布与本地定时安装引擎
│   ├── build_site.py                # 零第三方依赖生成双端响应式门户（首页全渠道详览/多元渠道/ETF雷达/231股7维/记分卡/档案）
│   ├── lint_site.py                 # 6 道法证与安全门禁（S1–S6，--strict 零容忍，禁用 PDF/Word 链接）
│   ├── publish_site.py              # 源稿严检 -> 静态站构建严检 -> 限域提交推送（GitHub Pages 自动部署）
│   ├── install_sidecars.py          # 将脱敏定时模板渲染/原子安装至本机并做漂移校验
│   ├── edition_run.py               # 两个班次共用的运行记录、阶段锁、僵尸锁安全清理与 Pages 验收
│   └── web_assets/                  # 站点样式与交互脚本（含 7 维个股深研与 ETF 详情弹窗）
├── tests/                           # 零依赖全链路回归测试集
└── .github/workflows/
    └── deploy-pages.yml             # 零外部依赖回归测试和双轨预检后构建，核准提交再部署至 GitHub Pages
```

---

## 2. 一体化双定时任务节拍与收敛主刊哲学（CST / UTC+8）

统一运行 **每日 2 个一体化单会话定时任务**，工作日早/晚班次全面执行 **四市全主刊（All-4-Main）+ 8 大多元渠道（直出首页详列）+ 106 只 ETF 雷达与 231 股 7 维深研 + 纯网页发布**：

| 定时任务 ID | 触发时间（CST） | 班次定位 | 单会话串行产出（纯网页 All-4-Main + 8+1 深研） |
| :--- | :--- | :--- | :--- |
| **`daily-global-investment-research`** | **每日 `07:30`** | **一体化早报** | ① 黄金 `0730_早报`（刷新 `gold/data_snapshot.json` SSOT 并严检） → ② **A 股 / 港股 / 美股三市全部发完整收敛主刊（`main`，≥2 张矢量图）**，同步刷新首页详列的 **`multi_asset_channels.json`（8 大渠道）**、**`etf_universe.json`** 与 **`deep_dossiers.json`**（周六 `07:30` 发黄金 + 美股主刊；休市/半日市受影响市场切 `holiday_watch` 含 ≥1 图） → ③ 统一 RSI + 单次纯网页发布 |
| **`daily-global-investment-research-evening`** | **每日 `18:00`** | **一体化晚报** | ① 黄金 `1800_晚报`（刷新 `gold/data_snapshot.json` SSOT 并严检） → ② **A 股 / 港股 / 美股三市全部发完整收敛主刊（`main`，≥2 张矢量图）**，封账日终官收并同步刷新首页详列的 **8 大个人多元渠道实时利率/溢价/退市红线、重点 ETF 与焦点股 7 维深研**（休市/半日市受影响市场切 `holiday_watch` 含 ≥1 图） → ③ 统一 RSI + 单次纯网页发布 |

> **周末与局部休市**：周六 `07:30` 权益线仅发美股主刊（常规交易日发周五复盘主刊，美股半日市发 `holiday_watch` 含 ≥1 图，美股全休市沿用旧稿）；周六晚和周日三市默认沿用旧稿，周日推进记分卡复盘、**核心龙头 7 维深度档案轮换升级**及 8 大多元渠道周度校准。每班必须执行 `python3 equity/lint_equity.py --plan <edition_id>` 获取具体市场、刊型和沿用安排。

---

## 3. 单会话严格顺序流水线（Step 0 → Step 5 · 纯网页极速版）

每次 `07:30` 或 `18:00` 一体化班次必须严格按以下顺序在同一会话内串行推进，严禁跳步或乱序：

- **运行锁、6 小时窗口与僵尸锁清理**：定时入口运行 `scripts/edition_run.py begin --scheduled 0730` 或 `--scheduled 1800`，**定时运行窗与跨轨截点容差统一为 6 小时（`07:25–13:30` / `17:55–23:59` CST）**。`begin --scheduled` 会先尝试收尾已有推送凭据的班次，并自动清理**超 2 小时无进展且未进入推送**的其他期号僵尸锁。收到 token 后才进入调研；两班共用运行锁，依次登记 `gold`、`equity`、`publish`，有进展时用 `heartbeat` 留下时间。
- **期号交接与时间戳纪律**：当班黄金快照、黄金日报 `DAILY_META`、权益状态和新权益稿 `DAILY_META_JSON` 记录同一 `edition_id`。黄金日报同时记录与快照一致的 `as_of_short`。休市沿用旧稿时保留旧稿期号和时间，状态先刷新至当前班次。

1. **Step 0｜双轨 RSI 经验库冷启动**：
   - 读取 `gold/daily/RSI_PLAYBOOK.md`（≤180 行）、`equity/state/RSI_PLAYBOOK.md`（≤180 行）及两轨 `rsi_metrics.json` 最近记录。
2. **Step 1｜跨市场日历、基线快照与多元/ETF/深研账本冷启动**：
   - 读取 `gold/market_calendar.json`、`gold/data_snapshot.json`、`gold/master_snapshot.json`、`equity/state/market_state.json`、`equity/state/multi_asset_channels.json`、`equity/state/etf_universe.json`、`equity/state/deep_dossiers.json`、两轨 `SCORECARD.md`、`gold/daily/CHANGELOG.md` 与 `equity/daily/INDEX.md`。
3. **Step 2A｜共享 8 路并行 `research` 深度调研（8+1 架构）**：
   - 启动 **8 路只读 `research` 子代理**：① 黄金与贵金属、② 中国 A 股、③ 中国香港股市、④ 美国股市、⑤ 跨资产宏观汇率与大宗、⑥ 三地社区与谣言辟谣、⑦ **中国大陆个人 8 大多元投资渠道专线**（债券、公募基金与理财、国债逆回购、场内外 QDII 与香港北向互认 MRF、大额存单、可转债、公募 REITs、非黄金大宗商品 ETF）、⑧ **三市重点 ETF 矩阵与个股 7 维深度基本面专线**。遇单项数据未发布或暂不可取时严禁编造、亦不阻塞发布，按规范挂账并写入 `data_caveats`。
4. **Step 2B｜1 路统一发前红队对抗核验（8+1 架构）**：
   - 跨轨交叉审计两轨共享宏观数字、黄金红灯全载体锁、A/H 物理一致、100% 配置闭环、8 大多元渠道关键制度与红线、三市 ETF 通道分类及焦点股 7 维财报催化日期。
5. **Step 3｜黄金 SSOT 优先落盘与严格门禁（纯网页）**：
   - 先更新 `gold/data_snapshot.json`（含纯读者中文 `data_caveats`），全量写入黄金日报 Markdown、三账本与本期 `GOLD_EDITION_REVIEW` 标记。仅命中 5 大阈值时同步主报告与 `master_snapshot.json`。
   - 运行：`python3 gold/lint_readability.py --strict <本刊路径>`（必须 `0 errors, 0 warnings`），**无需生成 PDF 或 Word**。
6. **Step 4｜全球权益三市、8 大多元渠道与 7 维深研数据库接力落盘与严检（纯网页）**：
   - 只读校验本期黄金快照（6 小时容差）和 Tier-0 行动互斥锁。落盘本期日报 Markdown、`INDEX.md`（纯网页/Markdown 链接，禁 `.pdf`/`.docx`）、`CHANGELOG.md`、`SCORECARD.md`、`state/market_state.json`（含 `data_caveats`）、**增量更新 `state/multi_asset_channels.json`（直出首页详列）、`state/etf_universe.json` 与 `state/deep_dossiers.json`**，并更新 `state/audit_ledger.md`。
   - 运行：`python3 equity/lint_equity.py --strict`（校验源稿、SVG 防重叠、三大深研库、跨项目黄金 SSOT 与旗舰 Markdown 同步，必须 `0 errors, 0 warnings`），**无需生成 PDF 或 Word**。
7. **Step 5｜统一 RSI 盲审闭环 + 单次纯网页门户发布**：
   - 启动 **1 路独立只读 `research` 盲审子代理**，按两轨各 6 维 `/30` 打分与预判验真，更新 `gold/daily/{rsi_metrics.json,RSI_PLAYBOOK.md}` 与 `equity/state/{rsi_metrics.json,RSI_PLAYBOOK.md}`（`findings` 支持 `resolved`、`deferred_data`、`disclosed_caveat`；仅 `open` 或未修硬错拦截发布）。
   - 复跑 `gold/lint_readability.py --strict` 与 `equity/lint_equity.py --strict`，随后进入 `publish` 阶段运行 `python3 scripts/publish_site.py --edition-token <token>`（构建完整静态门户——含首页全部 4 大市场 + 8 大多元渠道详表 + ETF 雷达、独立 `channels.html`、`etfs.html`、231 股 7 维 `screener.html`——通过 S1–S6 严检后单提交推送至 `origin/main`），最后运行 `python3 scripts/edition_run.py complete <token>` 验证 GitHub Pages 实际部署成功即闭环。

---

## 4. 跨轨硬不变式（Hard Cross-Track Invariants）

1. **黄金 SSOT 唯一写入权 + Tier-0 行动互斥锁**：
   - `gold/data_snapshot.json` 仅允许黄金轨（Step 3）写入，权益轨（Step 4）严格只读校验；
   - 当 `tier_code == "Tier 0"` 或 `new_buy_allowed == false` 时，全仓库公开正文、三大扩展 JSON 与全站网页（含首页、`channels.html`、`etfs.html`、`screener.html`）严禁出现新买/补齐黄金指令或将黄金/金矿标的标为绿色底座（由 `equity/lint_equity.py` Gate C2 与 `scripts/lint_site.py` Gate S6 强制阻断）。
2. **纯网页零二进制交付与首页全渠道透明**：
   - 全站严禁输出 `.pdf` / `.docx` 或 `releases/download/latest-reports` 下载链接（由 `scripts/lint_site.py` Gate S2 与 `equity/lint_equity.py` Gate 4 强制阻断）；
   - 门户首页 `index.html` 必须完整呈现四大核心市场及 `multi_asset_channels.json` 中全部 8 大个人多元投资渠道的详细最新情况（由 `scripts/lint_site.py` Gate S6 强制核验）。
3. **零本地绝对路径 PII、零密钥泄露与零内部工程词**：
   - 所有公开文件与生成的静态网页严禁出现 `/Users/...`、`/home/...`、`file://` 本地路径、密钥或内部工程/脚本/RSI 文件名（由 `scripts/lint_site.py` Gate S3 严守）。
4. **无人值守全量写盘、预授权绝对路径裸命令与三道严格门禁零容忍**：
   - 定时无人值守任务修改 Markdown/JSON 一律使用 `write_file` 全量写盘（禁 `edit_file`），且仅运行 `sidecar.json` 预授权的绝对路径裸命令；
   - 交付与发布前，以下**三道严格门禁必须全部退出码 `0`（`0 errors, 0 warnings`）**：
     - `python3 gold/lint_readability.py --strict gold/daily/<最新黄金日报>.md`
     - `python3 equity/lint_equity.py --strict`
     - `python3 scripts/build_site.py --out _site && python3 scripts/lint_site.py _site --strict`
5. **准点发刊不阻塞与信息缺口全透明（Anti-Blocker & Data-Caveats Transparency）**：
   - 定时运行窗与跨轨截点容差均为 **6 小时**；`begin --scheduled` 自动清理超 **2 小时**无进展且未开始推送的其他期号僵尸锁；
   - 两轨同步维护纯读者中文、零内部文件名的结构化 **`data_caveats`** 数组，在首页与日报页自动披露信息缺口及对核心裁决的影响。

---

## 5. 子轨权威契约与工作区技能索引

- **黄金子轨规则与格式宪章**：[gold/AGENTS.md](gold/AGENTS.md) · [gold/daily/AGENTS.md](gold/daily/AGENTS.md) · [gold/daily/DAILY_FORMAT_SPEC.md](gold/daily/DAILY_FORMAT_SPEC.md) · [gold/daily/RSI_PLAYBOOK.md](gold/daily/RSI_PLAYBOOK.md)
- **权益、多元渠道与 7 维深研宪法与排版详规**：[equity/GEMINI.md](equity/GEMINI.md) · [equity/DAILY_REPORT_SPEC.md](equity/DAILY_REPORT_SPEC.md) · [equity/state/RSI_PLAYBOOK.md](equity/state/RSI_PLAYBOOK.md)
- **统一工作区三 Skill（`.agents/skills/` · Tier C 只读）**：
  - [.agents/skills/gold-research-publishing/SKILL.md](.agents/skills/gold-research-publishing/SKILL.md)
  - [.agents/skills/equity-report-publishing/SKILL.md](.agents/skills/equity-report-publishing/SKILL.md)
  - [.agents/skills/equity-research-editorial-qa/SKILL.md](.agents/skills/equity-research-editorial-qa/SKILL.md)
- **共享提示词、授权和定时安装（Tier C 只读）**：[定时提示词](automations/unified-edition.prompt.md) · [授权配置](automations/permissions.json) · `automations/sidecars/*.template.json` · [安装器](scripts/install_sidecars.py)
