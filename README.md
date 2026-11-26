# 全球大类资产与跨周期投研门户 · Global Investment Research

> **纯网页在线阅读门户（GitHub Pages）**：[https://nanless.github.io/global-investment-research/](https://nanless.github.io/global-investment-research/)  
> （本站采用**纯网页静态门户唯一交付**，不生成或分发离线二进制文档附件。首页清晰呈现 **4 大核心市场红绿灯**、小白 **「今日行动红绿灯 + 钱怎么分四笔」** 导览、**全部 12 大个人多元合规投资渠道简洁概览卡**【点击直达独立详情页 `channels/<id>.html`】、**5 大 ETF 通道概览卡**【跳转预筛选 `etfs.html`】、**《新手 3 分钟指南》（`guide.html`）** 与 **站内术语白话浮窗**。）

面向普通家庭与进阶投资者的**「小白 3 分钟看懂 × 机构级 7 维硬核证据」**跨市场投研出版仓库。统一覆盖：
- **黄金**（1971–2030 全景主报告 + 每日早晚收敛主刊，跨轨单一事实源 SSOT）；
- **中国 A 股 × 中国香港股市 × 美国股市**（7 维大盘框架 × **231 只全行业核心龙头 7 维机构级深度档案（零模板化）**：A 股 76 / 港股 75 / 美股 80 + **140+ 只跨 6 大交易通道重点 ETF 雷达** + 每日三市早晚完整收敛主刊）；
- **中国大陆 12 大个人多元合规投资渠道 MECE 全景**（活钱与现金管理 / 人民币银行存款全家桶 / 境内个人外币存款与外币理财 / 债券与债券 ETF / 公募基金与银行理财及投顾 / 储蓄型商业保险 / 个人养老金与税优账户 / 场内外 QDII 与香港互认及理财通 / 可转债 / 公募 REITs 与不动产租金对比 / 非黄金大宗商品与白银铂钯渠道 / 合规私募与标品信托 300 万专享），另配横向 **「全市场打新工具箱」** 与 **「双层风控警示墙」**。

通过黄金快照实现跨项目红绿灯联防与零冲突质检，并在门户首页、12 大独立渠道详情页（`channels/<id>.html`）、全渠道总览（`channels.html`）、ETF 雷达（`etfs.html`）、231 股 7 维深研筛选器（`screener.html`）、《新手 3 分钟指南》（`guide.html`）与日报页通过结构化 **`data_caveats`** 自动披露未发布、暂定收盘或存在分歧的数据项及其对裁决的影响。

An institutional-grade, beginner-friendly, **web-only** multi-asset investment research monorepo unifying **Gold**, **Global Equities** (**China A-Share 76 × Hong Kong 75 × US Stocks 80 — 231-stock** zero-template 7-dimension deep dossiers + **140+ ETF Radar across 6 trading channels** + All-4-Main daily editions), and **12 MECE China Personal Multi-Asset Channels** (with dedicated `channels/<id>.html` pages, a 3-minute beginner guide `guide.html`, and inline plain-language glossary tooltips), synchronized via a **10+1** research & red-team workflow, cross-project Gold SSOT consistency gate, structured `data_caveats` transparency, and zero-dependency GitHub Pages publishing.

---

## 更新节拍 · Publication Schedule (CST / UTC+8)

黄金、全球三市权益、140+ 重点 ETF 与 12 大个人多元渠道采用 **每日 2 场一体化单会话流水线**（共享 **10 路并发深度调研 + 1 路统一红队** → 黄金 SSOT 先行落盘严检 → 三地权益、三大扩展数据库强制同期刷新与严检 → 统一 RSI 盲审 + 单次 `scripts/publish_site.py` 构建并推送至 GitHub Pages）。工作日早/晚班次全面执行 **四市全主刊（All-4-Main）+ 10+1 深研 + 纯网页发布**，定时运行窗与跨轨截点容差统一为 **6 小时**：

| 北京时间（CST） | 班次 / Schedule | 单会话串行产出 / Editions（纯网页 All-4-Main + 10+1 深研） |
| :--- | :--- | :--- |
| **07:30** | **一体化早报** (`daily-global-investment-research`) | **Step 3 黄金早报**（刷新 `gold/data_snapshot.json` SSOT 与 `data_caveats` 并严检） → **Step 4 三地权益全主刊 + 三大深研库同期刷新**（A/港/美均发收敛主刊含 ≥2 张矢量图，聚焦隔夜外盘/汇率/美债、美股与爱尔兰 ETF 官收、QDII 溢价停牌、外币存款理财、盘前逆回购/打新/转债日历与当班 4–6 只焦点股 7 维深研；休市/半日市切 `holiday_watch` 含 ≥1 图） → **Step 5 统一 RSI 与单次纯网页发布** |
| **18:00** | **一体化晚报** (`daily-global-investment-research-evening`) | **Step 3 黄金晚报**（刷新 `gold/data_snapshot.json` 与 `data_caveats` 并严检） → **Step 4 三地权益全主刊 + 三大深研库同期刷新**（封账 A/港日终官收、两融、中金所席位、南向资金、16:30 汇率与美股今早盘后终盘，刷新债券/逆回购/可转债/REITs/非金商品/QDII 日终溢价与停牌及当班 4–6 只焦点股 7 维深研） → **Step 5 统一 RSI 与单次纯网页发布** |
| **周六 / 周日** | **周末专项 / 周度校准** | 周六 07:30 黄金周末专项主刊 + 美股周五复盘主刊（美股半日市发 `holiday_watch` 含 ≥1 图，全休沿用旧稿）；周六晚与周日三市默认沿用旧稿，**周日推进全量周度校准**：刷新 12 大渠道中低频制度/利率项、复核 140+ ETF 费率与规模、轮换精修 231 股池中 **6–10 只核心龙头 7 维深度档案**并更新公开记分卡 `SCORECARD.md` |

---

## 仓库结构 · Repository Structure

```text
global-investment-research/
├── AGENTS.md                       # 仓库顶层统一编排宪章（纯网页 10+1 架构、12 大渠道与跨轨硬约束）
├── .agents/skills/                 # 统一工作区三 Skill（黄金出版 + 权益出版 + 权益编辑审校）
├── automations/                    # 定时自动化共享提示词、授权清单与脱敏模板（零个人路径）
│   ├── unified-edition.prompt.md   # 早晚双班共用纯网页 10+1 流水线、分层刷新矩阵与盲审闭环提示词
│   ├── permissions.json            # 统一无通配符命令与读写授权白名单
│   └── sidecars/                   # 脱敏版 07:30/18:00 一体化定时任务模板
├── gold/                           # 黄金深度研报体系（跨项目 SSOT 写入源）
│   ├── 黄金跨世纪周期与2026-2030终审研究报告.md
│   ├── data_snapshot.json          # 日报实时数据源、跨项目红绿灯裁决 SSOT 与 data_caveats 披露源
│   ├── master_snapshot.json        # 全景主报告独立锁定基线
│   ├── market_calendar.json        # 60+ 天跨市场休市与冬/夏令时日历
│   └── daily/                      # 每日早晚报、公开记分卡 SCORECARD、CHANGELOG 与 AUDIT_LOG
├── equity/                         # 全球三市权益、140+ ETF 雷达与 12 大多元渠道研报体系
│   ├── {a_share,hk_stock,us_stock}_market_report_{YYYY_MM,latest}.md
│   ├── report_meta_{a_share,hk_stock,us_stock}.json
│   ├── state/
│   │   ├── market_state.json       # 三市灯号、政策雷达、跨市熔断阀、data_caveats 与黄金只读镜像
│   │   ├── multi_asset_channels.json # 12 大个人多元合规渠道 + 打新工具箱 + 双层风控墙 SSOT
│   │   ├── etf_universe.json       # 140+ 只跨 6 大通道重点 ETF 深度矩阵 SSOT
│   │   └── deep_dossiers.json      # 全部 231 只龙头零模板化 7 维机构级深度研究档案 SSOT
│   ├── edition_plan.py / lint_equity.py（及 21 张矢量 SVG 图表模块）
│   └── daily/                      # 三市每日早晚报、总看板 INDEX、SCORECARD 与 CHANGELOG
├── scripts/                        # 零第三方依赖静态门户构建、严格门禁、班次锁与纯网页发布引擎
│   ├── build_site.py               # 生成双端响应式门户（首页导览/12 独立渠道页/ETF 雷达/231 股 7 维/新手指南/记分卡/档案）
│   ├── lint_site.py                # 静态站点 6 道法证与安全严格校验（S1–S6，严禁离线附件链接）
│   ├── publish_site.py             # 预检 -> 构建严检 -> 单提交推送 -> GitHub Pages 自动部署
│   ├── edition_run.py / install_sidecars.py
│   └── web_assets/                 # 站点样式与交互脚本（含术语白话浮窗、7 维个股与 ETF 详情弹窗）
├── tests/                          # 零依赖编排、出版、门户、黄金与权益全链路单元测试套件
└── .github/workflows/
    └── deploy-pages.yml            # PR 与 main 回归测试、模板干跑、源稿预检、站建严检；仅 main 部署 Pages
```

---

## 本地构建、质检与发布 · Local Build, Lint & Publish

> 零第三方依赖（仅需 Python 3.9+ 标准库即可直接测试、严检、构建与发布，无需 `pip install` 或外部浏览器二进制）。

### 1. 研报质量门禁（Report Linters）
```bash
# 查看该班三市出刊计划与沿用安排
python3 equity/lint_equity.py --plan 2026-11-26_1800

# 黄金源稿与快照严检（0 错误 0 警告）
python3 gold/lint_readability.py \
  gold/黄金跨世纪周期与2026-2030终审研究报告.md \
  gold/daily/2026-11-26_1800_晚报_黄金深度研报.md \
  --strict

# 权益全量源稿 + 21 张 SVG 图表 + 三大深研库 + 跨项目黄金 SSOT 门禁
python3 equity/lint_equity.py --strict

# 统一源稿检查、模板干跑校验与单元测试
python3 scripts/publish_site.py --check-manuscripts
python3 scripts/install_sidecars.py --dry-run
python3 -m unittest discover -s tests
```

### 2. 静态网站构建与严检（Static Site Build & Lint）
```bash
python3 scripts/build_site.py --out _site
python3 scripts/lint_site.py _site --strict
```

### 3. 一键纯网页发布与部署核验（Automated Web Publish CLI）
```bash
python3 scripts/publish_site.py --dry-run
python3 scripts/publish_site.py --no-push
python3 scripts/publish_site.py
python3 scripts/publish_site.py --edition-token <token>
python3 scripts/edition_run.py complete <token>
```

### 4. 本机定时任务安装与漂移校验（Local Sidecar Sync）
```bash
python3 scripts/install_sidecars.py
python3 scripts/install_sidecars.py --check
python3 scripts/install_sidecars.py --check-runtime
python3 scripts/edition_run.py status
```

---

## 免责声明 · Disclaimer

本仓库及在线网站所载全部研报、数据、图表与情景测算均基于公开官方市场与公司披露资料整理，**仅供投资研究、知识学习与风险教育参考，不构成任何针对个人的证券买卖要约、收益承诺或投资建议**。金融市场受利率、汇率、地缘政治与流动性多重风险影响，历史回溯与概率框架不代表未来表现，投资决策请结合自身风险承受能力与专业持牌顾问意见独立审慎作出。
