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
├── automations/sidecars/            # 脱敏版 07:30/18:00 一体化定时任务模板（Tier C 只读）
├── gold/                            # 黄金深度研报体系（跨轨 SSOT 唯一写入源）
│   ├── AGENTS.md                    # 黄金子轨永久规则
│   ├── data_snapshot.json           # 日报实时数据源 & 跨项目红绿灯裁决 SSOT
│   ├── master_snapshot.json         # 1971–2030 全景主报告独立锁定基线
│   ├── market_calendar.json         # 60+ 天全球跨市场休市与冬/夏令时日历
│   ├── build_daily.py / build_report.py / docx_embed.py / lint_readability.py
│   └── daily/                       # 日报、SCORECARD、CHANGELOG、AUDIT_LOG、RSI 台账
├── equity/                          # 全球三市权益研报体系（A 股 × 港股 × 美股）
│   ├── GEMINI.md                    # 权益子轨永久宪法
│   ├── DAILY_REPORT_SPEC.md         # 7 维大盘、排版量化与主轻协同唯一详规
│   ├── state/                       # market_state.json、audit_ledger.md、RSI 台账
│   ├── build_{a_share,hk_stock,us_stock}_pdf.py / build_daily.py / pdf_common.py / docx_embed.py / lint_equity.py
│   └── daily/                       # 三市日报、总看板 INDEX、SCORECARD、CHANGELOG
├── scripts/                         # 统一静态门户构建、严格门禁、发布与本地定时安装引擎
│   ├── build_site.py                # 零第三方依赖生成双端响应式门户（_site/）
│   ├── lint_site.py                 # 6 道法证与安全门禁（S1–S6，--strict 零容忍）
│   ├── publish_site.py              # 构建 -> 严检 -> 限域提交推送 -> 增量 Release 上传
│   ├── install_sidecars.py          # 将脱敏定时模板渲染/原子安装至本机并做漂移校验
│   └── web_assets/                  # 站点样式与交互脚本
└── .github/workflows/
    └── deploy-pages.yml             # push main 自动构建、严检并部署至 GitHub Pages
```

---

## 2. 一体化双定时任务节拍（CST / UTC+8）

已彻底整合历史 4 任务拆分架构，统一升级为 **每日 2 个一体化单会话定时任务**，杜绝跨会话竞态与重复全网检索：

| 定时任务 ID | 触发时间（CST） | 班次定位 | 单会话串行产出 |
| :--- | :--- | :--- | :--- |
| **`daily-global-investment-research`** | **每日 `07:30`** | **一体化早报** | ① 黄金 `0730_早报`（刷新 `gold/data_snapshot.json` SSOT） → ② 美股隔夜复盘主刊（周一轻刊；周六仅发美股）+ A 股/港股盘前快报（`_0730_`） → ③ 统一 RSI + 单次网站发布 |
| **`daily-global-investment-research-evening`** | **每日 `18:00`** | **一体化晚报** | ① 黄金 `1800_晚报`（刷新 `gold/data_snapshot.json` SSOT） → ② A 股/港股收盘主刊 + 美股欧亚盘与盘前哨兵轻刊（`_1800_`） → ③ 统一 RSI + 单次网站发布 |

> **周末与局部休市**：周六 `07:30` 发黄金周末专项版 + 美股周五复盘主刊；周六 `18:00` 与周日双场按黄金周末专项版 + 权益模式 3（周日刷新 `SCORECARD.md` 并推进 2–3 只核心龙头 6 维深度解剖轮换）执行；工作日局部休市由 `gold/market_calendar.json` 与 `equity/state/market_state.json` 驱动。

---

## 3. 单会话严格顺序流水线（Step 0 → Step 5）

每次 `07:30` 或 `18:00` 一体化班次必须严格按以下顺序在同一会话内串行推进，严禁跳步或乱序：

1. **Step 0｜双轨 RSI 经验库冷启动**：
   - 读取 `gold/daily/RSI_PLAYBOOK.md`（≤180 行）、`equity/state/RSI_PLAYBOOK.md`（≤180 行）及两轨 `rsi_metrics.json` 最近记录，继承高杠杆检索词、Linter 避坑清单与上期 `next_run_watch`。
2. **Step 1｜跨市场日历、基线快照与账本冷启动**：
   - 读取 `gold/market_calendar.json`、前序基线 `gold/data_snapshot.json`（冷启动锚点；最新 0 分钟新鲜 SSOT 与 Tier-0 互斥锁校验于 Step 3 黄金落盘后的 **Step 4 入口**强制执行）、`gold/master_snapshot.json`（惰性判断主报告触发）、`equity/state/market_state.json`、两轨 `SCORECARD.md`、`gold/daily/CHANGELOG.md`（前 150 行）与 `equity/daily/INDEX.md`（前 60 行）。
3. **Step 2A｜共享 6 路并行 `research` 深度调研**：
   - 一次并发启动 **6 路只读 `research` 子代理** 覆盖双轨全部 7 类一手官方信源，消除重复抓取：
     1. **黄金与贵金属专线**（现货/COMEX 官结、SGE/SHFE 日终与龙虎榜、GLD/GDX 官收白名单、实物金店/水贝与央行动向）；
     2. **中国 A 股专线**（宽基/申万资金、中金所 `cffex.com.cn` 结算与前 20 席位、T-1 两融终值、央行操作与政策雷达）；
     3. **中国香港股市专线**（恒指/恒科/南向终值、沽空比、HIBOR 与金管局总结余 `hkma_agg_bal_hkd_100m`、AH 溢价与夜期盲窗校正）；
     4. **美国股市专线**（标普/纳指/芯片与 11 板块、信用利差与国债拍卖、盘后终盘/T+1 加密 ETF 官流与 SEC/监管日历）；
     5. **跨资产宏观、汇率与大宗专线**（10Y 美债/DFII10/中债、DXY、在岸/离岸人民币与 CFETS 中间价、布油 `brent_settle_usd`、COMEX 期铜与日元/联汇）；
     6. **三地社区、预测市场与谣言辟谣专线**（雪球/集思录/股吧/连登/Reddit/X、Polymarket/Kalshi 实盘赔率、监管官方辟谣与可转债/退市/QDII 事实核查）。
4. **Step 2B｜1 路统一发前红队对抗核验（6+1 架构）**：
   - 待全部 6 路返回后，启动 **1 路统一红队 `research` 子代理** 跨轨交叉审计：校验两轨共享宏观数字（现货金、10Y 美债、`DFII10`、DXY、`brent_settle_usd`、`cfets_cny_fixing`、VIX、ON RRP、COMEX 铜）完全一致；拦截 6 大权益硬伤（A/H PE 物理学一致、100% 配置闭环、买点锚 < 现价、黄金红灯全载体锁、冬夏令时与 07:30 禁写盘后终盘、零退市股 `00011` 与 QDII 误标）及黄金跨时区因果倒置，输出统一【新增 / 更新 / 修正 / 删除】核验清单。
5. **Step 3｜黄金 SSOT 优先落盘、编译与 7 门禁严检**：
   - 先更新 `gold/data_snapshot.json`（写入权威 `tier_code`、`new_buy_allowed` 与全量共享宏观键），用 `write_file` 全量落盘黄金日报、`CHANGELOG.md`、`AUDIT_LOG.md`、`SCORECARD.md`（仅命中 5 大阈值时同步主报告与 `master_snapshot.json`）；
   - 串行执行：`python3 gold/lint_readability.py --precheck --strict <本刊路径>` → `python3 gold/build_daily.py <本刊路径>`（按需 `build_report.py`）→ `python3 gold/lint_readability.py --strict <本刊路径>`（必须 `0 errors, 0 warnings`）+ `read_file` 抽检 PDF。
6. **Step 4｜全球权益三市（A/港/美）接力落盘、编译与全量严检（0 分钟新鲜 SSOT）**：
   - 紧接 Step 3 完成后，在 **Step 4 入口**强制只读校验刚刚刷新的 `gold/data_snapshot.json`（**0 分钟新鲜，远优于 ≤4 小时门禁**）与 Tier-0 行动互斥锁（独立单跑权益轨时于 Step 1 执行），随后用 `write_file` 全量落盘三市日报、`INDEX.md`、`CHANGELOG.md`、`SCORECARD.md`、`state/market_state.json`、`state/audit_ledger.md`（仅命中 5 条阈值时更新旗舰与 `report_meta_*.json`）；
   - 串行执行：`python3 equity/lint_equity.py --precheck --strict` → `python3 equity/build_daily.py`（按需串行 `build_{a_share,hk_stock,us_stock}_pdf.py`）→ `python3 equity/lint_equity.py --strict`（必须 `0 errors, 0 warnings`）+ `read_file` 抽检 PDF。
7. **Step 5｜统一 RSI 盲审闭环 + 单次静态站与 Release 发布**：
   - 启动 **1 路独立只读 `research` 盲审子代理** 联合复盘黄金与三地权益本班次产出（各按 6 维 `/30` 独立打分与预判验真）；
   - 按 Tier A/B/C 安全权限分别更新 `gold/daily/{rsi_metrics.json,RSI_PLAYBOOK.md}` 与 `equity/state/{rsi_metrics.json,RSI_PLAYBOOK.md}`（**两份手册严格 ≤180 行**，Tier B 单次 ≤1 处 ≤40 行且验证失败即回滚，Tier C 含本文件 `AGENTS.md` 仅写提案待批）；
   - 复跑 `gold/lint_readability.py --strict` 与 `equity/lint_equity.py --strict` 确认全绿后，**每班次仅运行一次** `python3 scripts/publish_site.py`（自动编译 `_site/` → `scripts/lint_site.py _site --strict` → 限域提交推送 `main` → SHA256 增量更新 GitHub Release PDF/DOCX）。

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

---

## 5. 子轨权威契约与工作区技能索引

- **黄金子轨规则与格式宪章**：[gold/AGENTS.md](gold/AGENTS.md) · [gold/daily/AGENTS.md](gold/daily/AGENTS.md) · [gold/daily/DAILY_FORMAT_SPEC.md](gold/daily/DAILY_FORMAT_SPEC.md) · [gold/daily/RSI_PLAYBOOK.md](gold/daily/RSI_PLAYBOOK.md)
- **权益子轨宪法与排版详规**：[equity/GEMINI.md](equity/GEMINI.md) · [equity/DAILY_REPORT_SPEC.md](equity/DAILY_REPORT_SPEC.md) · [equity/state/RSI_PLAYBOOK.md](equity/state/RSI_PLAYBOOK.md)
- **统一工作区三 Skill（`.agents/skills/` · Tier C 只读）**：
  - 黄金 7 门禁、OOXML 引擎、组件 Schema 与调研红队：[.agents/skills/gold-research-publishing/SKILL.md](.agents/skills/gold-research-publishing/SKILL.md)
  - 权益出版编译、21 张矢量图与休市/跨月 SOP：[.agents/skills/equity-report-publishing/SKILL.md](.agents/skills/equity-report-publishing/SKILL.md)
  - 权益 7 维大盘、10 项门禁、双账户税费与 RSI 盲审：[.agents/skills/equity-research-editorial-qa/SKILL.md](.agents/skills/equity-research-editorial-qa/SKILL.md)
- **脱敏定时任务模板与安装器（Tier C 只读）**：`automations/sidecars/*.template.json` · [scripts/install_sidecars.py](scripts/install_sidecars.py)
