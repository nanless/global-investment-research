# Global Investment Research · Monorepo Orchestration Contract (`AGENTS.md`)

本文件是 `global-investment-research` 单仓库（Monorepo）的**顶层唯一编排宪章**，统一约束 **黄金深度研报（`gold/`）** 与 **全球三市权益研报（`equity/`：中国 A 股 × 中国香港股市 × 美国股市）** 在一体化双定时任务下的协同调研、串行编译、跨轨门禁、受控 RSI 自我复盘与静态门户发布。

---

## 1. Monorepo 目录结构与职责边界

```text
global-investment-research/
├── AGENTS.md                        # 本文件：单仓库顶层编排宪章与跨轨硬约束
├── README.md                        # 仓库总览、一体化双班次节拍与本地构建说明
├── .agents/skills/                  # 全仓库统一工作区三 Skill（黄金出版 + 权益出版 + 权益编辑审校）
│   ├── gold-research-publishing/    # 黄金 7 门禁、OOXML 引擎、组件 Schema 与调研红队手册
│   ├── equity-report-publishing/    # 权益出版编译、21 张矢量图与三市休市/跨月 SOP
│   └── equity-research-editorial-qa/# 权益 7 维大盘、10 项门禁、双账户税费与 RSI 协议
├── automations/                     # 一个共用提示词、同一份授权声明和两个定时模板（Tier C 只读）
├── gold/                            # 黄金深度研报体系（跨轨 SSOT 唯一写入源）
│   ├── AGENTS.md                    # 黄金子轨永久规则
│   ├── data_snapshot.json           # 日报实时数据源、跨项目红绿灯裁决 SSOT 与 data_caveats 披露源
│   ├── master_snapshot.json         # 1971–2030 全景主报告独立锁定基线
│   ├── market_calendar.json         # 60+ 天全球跨市场休市与冬/夏令时日历
│   ├── edition_validation.py / chart_input.py  # 班次截点/VIX 交易日/四关复算与图表输入校验模块
│   ├── build_daily.py / build_report.py / docx_embed.py / lint_readability.py
│   └── daily/                       # 日报、SCORECARD、CHANGELOG、AUDIT_LOG、archive/ 按月归档与 RSI 台账
├── equity/                          # 全球三市权益研报体系（A 股 × 港股 × 美股）
│   ├── GEMINI.md                    # 权益子轨永久宪法
│   ├── DAILY_REPORT_SPEC.md         # 7 维大盘、全主刊收敛骨架与休市守望唯一详规
│   ├── state/                       # market_state.json（含 data_caveats）、audit_ledger.md、RSI 台账
│   ├── edition_plan.py              # 三市全主刊 / 休市守望 / 沿用与出版例外唯一规划器
│   ├── build_{a_share,hk_stock,us_stock}_pdf.py / build_daily.py / pdf_common.py / docx_embed.py / lint_equity.py
│   └── daily/                       # 三市日报、总看板 INDEX、SCORECARD、CHANGELOG
├── scripts/                         # 统一静态门户构建、严格门禁、发布与本地定时安装引擎
│   ├── build_site.py                # 零第三方依赖生成双端响应式门户（_site/）与数据完整性透明模块
│   ├── lint_site.py                 # 6 道法证与安全门禁（S1–S6，--strict 零容忍）
│   ├── publish_site.py              # 构建 -> 严检 -> 限域提交推送 -> 增量 Release 上传
│   ├── artifact_receipt.py          # 附件编译输入对账与防漂移凭据校验模块
│   ├── install_sidecars.py          # 将脱敏定时模板渲染/原子安装至本机并做漂移校验
│   ├── edition_run.py               # 两个班次共用的运行记录、阶段锁、僵尸锁安全清理与 Pages 验收
│   └── web_assets/                  # 站点样式与交互脚本
├── tests/                           # 端到端流水线、黄金/权益规则、OOXML 与发布回归测试集
└── .github/workflows/
    └── deploy-pages.yml             # 回归测试和双轨预检后构建，核准提交再部署至 GitHub Pages
```

---

## 2. 一体化双定时任务节拍与收敛主刊哲学（CST / UTC+8）

已彻底整合历史 4 任务拆分架构，统一升级为 **每日 2 个一体化单会话定时任务**，杜绝跨会话竞态与重复全网检索；自 **`>= 2026-11-26_1800`** 起，工作日早/晚班次全面切入 **四市全主刊（All-4-Main）** 架构：

| 定时任务 ID | 触发时间（CST） | 班次定位 | 单会话串行产出（`>= 2026-11-26_1800` All-4-Main） |
| :--- | :--- | :--- | :--- |
| **`daily-global-investment-research`** | **每日 `07:30`** | **一体化早报** | ① 黄金 `0730_早报`（完整收敛主刊，刷新 `gold/data_snapshot.json` SSOT） → ② **A 股 / 港股 / 美股三市全部发完整收敛主刊（`main`，5–6 页、≥2 张矢量图）**（周六 `07:30` 发黄金主刊 + 美股主刊；受休市/半日市影响的单一市场切 `holiday_watch` 守望刊含 ≥1 图） → ③ 统一 RSI + 单次网站发布 |
| **`daily-global-investment-research-evening`** | **每日 `18:00`** | **一体化晚报** | ① 黄金 `1800_晚报`（完整收敛主刊，刷新 `gold/data_snapshot.json` SSOT） → ② **A 股 / 港股 / 美股三市全部发完整收敛主刊（`main`，5–6 页、≥2 张矢量图）**（休市/半日市市场切 `holiday_watch` 守望刊含 ≥1 图） → ③ 统一 RSI + 单次网站发布 |

> **周末与局部休市**：周六 `07:30` 权益线仅发美股主刊（常规交易日发周五复盘主刊，美股半日市发 `holiday_watch` 含 ≥1 图，美股全休市沿用旧稿）；周六晚和周日三市默认沿用旧稿，周日推进记分卡复盘与龙头深度轮换。每班必须执行 `python3 equity/lint_equity.py --plan <edition_id>` 获取具体市场、刊型和沿用安排。黄金日历负责全球交易时点，权益计划负责验收当期交付与月度旗舰。

### 收敛主刊编辑哲学（面向懂一点基础财经的进阶普通投资者）

- **统一 5 模块收敛主刊骨架**：① 核心裁决与 4 卡摘要 → ② 隔夜/日内主线与跨市传导 → ③ 深度专题与 ≥2 张矢量图 → ④ 实操配置/焦点股与风控边界 → ⑤ 关键日历与官方数据溯源。
- **机构深度 + 明快人话**：直接给出证据链、估值标尺与可执行的仓位边界——既消除生僻卖方黑话、内部工程词与冗长自嗨，也彻底淘汰居高临下的说教口号（如“小白词典”“直接抄”“蠢事”“1 分钟定心丸”），尊重读者的判断力。

---

## 3. 单会话严格顺序流水线（Step 0 → Step 5）

每次 `07:30` 或 `18:00` 一体化班次必须严格按以下顺序在同一会话内串行推进，严禁跳步或乱序：

- **运行锁、6 小时窗口与僵尸锁清理**：定时入口运行 `scripts/edition_run.py begin --scheduled 0730` 或 `--scheduled 1800`，由脚本按北京时间确定期号，**定时运行窗与跨轨截点容差统一为 6 小时（`07:25–13:30` / `17:55–23:59` CST）**。`begin --scheduled` 会先尝试收尾已有完整发布凭据的班次，并自动清理**超 2 小时无进展且未进入推送**的其他期号僵尸锁（**绝不清理同班次或已开始推送/已有发布记录的班次**）。人工发刊明确指定 `begin <edition_id>`，同场修订追加 `_r2`、`_r3` 等。收到 token 后才进入调研；两班共用运行锁，依次登记 `gold`、`equity`、`publish`，有进展时用 `heartbeat` 留下时间。恢复按尝试编号定位，操作见 README。
- **期号交接与时间戳纪律**：当班黄金快照、黄金日报 `DAILY_META`、权益状态和新权益稿 `DAILY_META_JSON` 记录同一 `edition_id`。黄金日报同时记录与快照一致的 `as_of_short`。班次 ID 表示同一次交接，数据的交易日、观测时刻与披露时刻另行注明。休市沿用旧稿时保留旧稿期号和时间，状态先刷新至当前班次。

1. **Step 0｜双轨 RSI 经验库冷启动**：
   - 读取 `gold/daily/RSI_PLAYBOOK.md`（≤180 行）、`equity/state/RSI_PLAYBOOK.md`（≤180 行）及两轨 `rsi_metrics.json` 最近记录，继承高杠杆检索词、Linter 避坑清单与上期 `next_run_watch`。
2. **Step 1｜跨市场日历、基线快照与账本冷启动**：
   - 读取 `gold/market_calendar.json`、前序基线 `gold/data_snapshot.json`、独立主报告基线 `gold/master_snapshot.json`、`equity/state/market_state.json`、两轨 `SCORECARD.md`、`gold/daily/CHANGELOG.md` 与 `equity/daily/INDEX.md`。核对日历有效期和出刊计划，按官方品种交易日、实际观测时间、披露时间和来源记录数据。
3. **Step 2A｜共享 6 路并行 `research` 深度调研**：
   - 启动 **6 路只读 `research` 子代理**，容量不足时分组完成，覆盖双轨全部 7 类一手官方信源。各路最多重试一次；早/晚报遇单项数据尚未发布或暂不可取时严禁编造、亦不阻塞本期研报发布（按规范省略、标 `provisional_close`/`pending` 或沿用最近已核实官收并标注原交易日/观测时间，写入台账挂账及面向读者的 `data_caveats` 并在终报向用户逐项汇报）；仅在无法启动独立核查、权限/锁异常或严格门禁无法通过时才停止并记录阻塞：
     1. **黄金与贵金属专线**（现货/COMEX 官结、SGE/SHFE 日终与龙虎榜、GLD/GDX 官收白名单、实物金店/水贝与央行动向）；
     2. **中国 A 股专线**（宽基/申万资金、中金所 `cffex.com.cn` 结算与前 20 席位、T-1 两融终值、央行操作与政策雷达）；
     3. **中国香港股市专线**（恒指/恒科/南向终值、沽空比、HIBOR 与金管局总结余 `hkma_agg_bal_hkd_100m`、AH 溢价与夜期盲窗校正）；
     4. **美国股市专线**（标普/纳指/芯片与 11 板块、信用利差与国债拍卖、盘后终盘/T+1 加密 ETF 官流与 SEC/监管日历）；
     5. **跨资产宏观、汇率与大宗专线**（10Y 美债/DFII10/中债、DXY、在岸/离岸人民币与 CFETS 中间价、布油 `brent_settle_usd`、COMEX 期铜与日元/联汇）；
     6. **三地社区、预测市场与谣言辟谣专线**（雪球/集思录/股吧/连登/Reddit/X、Polymarket/Kalshi 实盘赔率、监管官方辟谣与可转债/退市/QDII 事实核查）。
4. **Step 2B｜1 路统一发前红队对抗核验（6+1 架构）**：
   - 待全部 6 路返回后，启动 **1 路统一红队 `research` 子代理** 跨轨交叉审计：校验两轨共享宏观数字（现货金、10Y 美债、`DFII10`、DXY、`brent_settle_usd`、`cfets_cny_fixing`、VIX、ON RRP、COMEX 铜）完全一致；拦截 6 大权益硬伤（A/H PE 物理学一致、100% 配置闭环、买点锚 < 现价、黄金红灯全载体锁、冬夏令时与 07:30 禁写盘后终盘、零退市股 `00011` 与 QDII 误标）及黄金跨时区因果倒置，输出统一【新增 / 更新 / 修正 / 删除】核验清单。
5. **Step 3｜黄金 SSOT 优先落盘、编译与 7 门禁严检**：
   - 先更新 `gold/data_snapshot.json`，写入四关结构化原始读数、观测交易日、权威档位、开仓布尔值与面向读者的结构化 **`data_caveats`** 数组（纯读者中文、严禁内部文件名或本地路径，清晰披露未发布、暂用官网收盘 `provisional_close`、单源或存在分歧的数据项及其对核心裁决的影响）。使用 `write_file` 全量落盘黄金日报和三账本；`gold/daily/AUDIT_LOG.md` 与 `gold/daily/CHANGELOG.md` 支持按月无损归档至 `gold/daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md`（完整保留历史顺序，根除大文件重写截断风险）。首轮预检前记录 `GOLD_EDITION_REVIEW` 及变更日志和公开记分卡的本期标记。仅命中 5 大阈值时同步主报告与 `master_snapshot.json`。
   - 串行执行：`python3 gold/lint_readability.py --precheck --strict <本刊路径>` → `python3 gold/build_daily.py <本刊路径>`（按需 `build_report.py`）→ `python3 gold/lint_readability.py --strict <本刊路径>`（必须 `0 errors, 0 warnings`）+ `read_file` 抽检 PDF。
6. **Step 4｜全球权益三市（A/港/美）接力落盘、编译与全量严检**：
   - Step 4 入口只读校验本期黄金快照、其观测截点（跨轨截点容差 **6 小时**）和 Tier-0 行动互斥锁。权益引用的黄金镜像须使用和黄金快照相同的期号、时间和数值，权益自己的观测时间与班次窗口另查。按计划写本期日报、`INDEX.md`、`CHANGELOG.md`、`SCORECARD.md`、`state/market_state.json`（同步维护纯读者中文、零内部文件名的 **`data_caveats`** 数组，供网站首页与日报页自动渲染披露）、`state/audit_ledger.md`，明确沿用市场、出版例外和跨月旗舰处理。
   - 串行执行：`python3 equity/lint_equity.py --precheck --strict` → `python3 equity/build_daily.py`（按需串行 `build_{a_share,hk_stock,us_stock}_pdf.py`）→ `python3 equity/lint_equity.py --strict`（必须 `0 errors, 0 warnings`）+ `read_file` 抽检 PDF。
7. **Step 5｜统一 RSI 盲审闭环 + 单次静态站与 Release 发布**：
   - 启动 **1 路独立只读 `research` 盲审子代理**，按两轨各 6 维 `/30` 打分与预判验真，并逐项核对当期总看板、记分卡、快照、正文与图表。等待盲审返回，修正全部已证实问题，按黄金在先、权益在后的顺序重编受影响附件。未发布或暂不可取的数据本期留空、明确挂账并同步写入 `data_caveats`。
   - 按 Tier A/B/C 安全权限分别更新 `gold/daily/{rsi_metrics.json,RSI_PLAYBOOK.md}` 与 `equity/state/{rsi_metrics.json,RSI_PLAYBOOK.md}`。两轨复盘各用本期完整 `edition_id` 作 `run_id`。按共享任务提示词填写 `review_closure`，`findings` 支持 **`resolved`**、**`deferred_data`** 及 **`disclosed_caveat`**（非阻断性分歧或口径提示已透明披露至网站，须写明 `disposition`，可选合规 `source` 与未来 `due_edition`）；**仅 `open` 或已证实未修的硬错才拦截发布**。两份手册各 ≤180 行，Tier B 单次 ≤1 处 ≤40 行且验证失败即回滚，Tier C 含本文件 `AGENTS.md`，只写提案待批。
   - 复跑 `gold/lint_readability.py --strict` 与 `equity/lint_equity.py --strict`。进入发布阶段后运行 `python3 scripts/publish_site.py --edition-token <token>`。发布器用最终提交校验两轨稿件、构建站点，将 PDF/Word 与编译输入对账后发布。同班只允许发布一个提交。推送及附件核验都有记录，`complete` 通过实际 Pages 部署步骤和在线附件复验后才算完成。遇到暂时性故障，可续同一 token 和提交。

---

## 4. 跨轨硬不变式（Hard Cross-Track Invariants）

1. **黄金 SSOT 唯一写入权 + Tier-0 行动互斥锁**：
   - `gold/data_snapshot.json` 仅允许黄金轨（Step 3）写入，权益轨（Step 4）严格只读校验；
   - 当 `tier_code == "Tier 0"` 或 `new_buy_allowed == false` 时，权益轨正文、`DAILY_META_JSON`、`report_meta_*.json`、编译后 HTML/SVG 与静态门户均**严禁出现任何新买/补齐黄金指令或将金矿标的标为绿色底座**（由 `equity/lint_equity.py` Gate C2 与 `scripts/lint_site.py` Gate S6 强制阻断）。
2. **严禁并发运行 Chrome 无头 PDF/DOCX 编译**：
   - Chrome headless 渲染 PDF 及 2× Retina PNG（原生 ECMA-376 OOXML `.docx`，全程严禁 `textutil`）必须严格串行：**先 Step 3 黄金，再 Step 4 权益**，避免高内存争抢、进程超时与字体渲染抖动。
3. **零本地绝对路径 PII 与零密钥泄露**：
   - 所有受追踪公开文件（文档、脚本、数据、HTML、Markdown、JSON）严禁出现 `/Users/...`、`/home/...`、`file://` 本地绝对路径或 API/GitHub 密钥；仓库内一律使用相对路径（由 `scripts/lint_site.py` Gate S3 与 `git grep` 严守）。
4. **无人值守全量写盘、预授权绝对路径裸命令与三道严格门禁零容忍**：
   - 定时无人值守任务修改 Markdown/JSON 一律使用 `write_file` 全量写盘（禁 `edit_file`），严禁运行未授权探测命令；且无人值守定时执行全部 Python 脚本时必须使用 `sidecar.json` 中精确预授权的完整绝对路径 `<REPO_ROOT>/...` 裸命令（禁相对路径或 `cd &&` 前缀）；
   - 交付与发布前，以下**三道严格门禁必须全部退出码 `0`（`0 errors, 0 warnings`）**：
     - `python3 gold/lint_readability.py --strict gold/daily/<最新黄金日报>.md`
     - `python3 equity/lint_equity.py --strict`
     - `python3 scripts/build_site.py --out _site && python3 scripts/lint_site.py _site --strict`
5. **准点发刊不阻塞与信息缺口全透明（Anti-Blocker & Data-Caveats Transparency）**：
   - 定时运行窗与跨轨截点容差均为 **6 小时**（`07:25–13:30` / `17:55–23:59` CST）；`begin --scheduled` 仅自动清理超 **2 小时**无进展且未开始推送的其他期号僵尸锁，绝不清理已进入推送的班次；
   - 黄金（`gold/data_snapshot.json`）与权益（`equity/state/market_state.json`）同步维护纯读者中文、零内部文件名的结构化 **`data_caveats`** 数组，并在网站首页与日报页自动披露未发布、暂用官网收盘（`provisional_close`）、单源或存在分歧的数据项及其对核心裁决的影响；
   - 盲审闭环 `review_closure.findings` 支持 `resolved`、`deferred_data` 与 `disclosed_caveat`（仅 `open` 或已证实未修硬错拦截发布）；黄金 `AUDIT_LOG.md` / `CHANGELOG.md` 支持按月无损归档至 `gold/daily/archive/{AUDIT_LOG,CHANGELOG}_YYYY_MM.md`，完整保留历史顺序以根除大文件截断风险。

---

## 5. 子轨权威契约与工作区技能索引

- **黄金子轨规则与格式宪章**：[gold/AGENTS.md](gold/AGENTS.md) · [gold/daily/AGENTS.md](gold/daily/AGENTS.md) · [gold/daily/DAILY_FORMAT_SPEC.md](gold/daily/DAILY_FORMAT_SPEC.md) · [gold/daily/RSI_PLAYBOOK.md](gold/daily/RSI_PLAYBOOK.md)
- **权益子轨宪法与排版详规**：[equity/GEMINI.md](equity/GEMINI.md) · [equity/DAILY_REPORT_SPEC.md](equity/DAILY_REPORT_SPEC.md) · [equity/state/RSI_PLAYBOOK.md](equity/state/RSI_PLAYBOOK.md)
- **统一工作区三 Skill（`.agents/skills/` · Tier C 只读）**：
  - 黄金 7 门禁、OOXML 引擎、组件 Schema 与调研红队：[.agents/skills/gold-research-publishing/SKILL.md](.agents/skills/gold-research-publishing/SKILL.md)
  - 权益出版编译、21 张矢量图与休市/跨月 SOP：[.agents/skills/equity-report-publishing/SKILL.md](.agents/skills/equity-report-publishing/SKILL.md)
  - 权益 7 维大盘、10 项门禁、双账户税费与 RSI 盲审：[.agents/skills/equity-research-editorial-qa/SKILL.md](.agents/skills/equity-research-editorial-qa/SKILL.md)
- **共享提示词、授权和定时安装（Tier C 只读）**：[定时提示词](automations/unified-edition.prompt.md) · [授权配置](automations/permissions.json) · `automations/sidecars/*.template.json` · [安装器](scripts/install_sidecars.py)
