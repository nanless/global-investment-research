# 全球大类资产与跨周期投研门户 · Global Investment Research

> **在线阅读门户（GitHub Pages）**：[https://nanless.github.io/global-investment-research/](https://nanless.github.io/global-investment-research/)  
> **最新精排 PDF & 原生 Word（`.docx`）打包下载**：[GitHub Releases · `latest-reports`](https://github.com/nanless/global-investment-research/releases/tag/latest-reports)

面向懂一点基础财经的进阶普通投资者的机构级、明快人话跨市场投研出版仓库。统一覆盖：
- **黄金**（1971–2030 全景主报告 + 每日早晚收敛主刊，跨轨单一事实源 SSOT）；
- **中国 A 股 × 中国香港股市 × 美国股市**（7 维大盘框架 × **231 只全板块核心龙头 7 维机构级深度档案**：A 股 76 / 港股 75 / 美股 80 + **80+ 只三市与全球重点 ETF 雷达** + 每日三市早晚完整收敛主刊）；
- **中国大陆 8 大个人多元合规投资渠道**（债券与万亿债券 ETF、公募基金与银行理财、国债逆回购、场内外 QDII 与香港北向互认基金 MRF、银行大额存单、可转债、公募 REITs、非黄金大宗商品 ETF）。

通过黄金快照实现跨项目红绿灯联防与零冲突质检，并在门户首页、多元渠道页（`channels.html`）、ETF 雷达页（`etfs.html`）、231 股 7 维深研筛选器（`screener.html`）与日报页通过结构化 **`data_caveats`** 自动披露未发布、暂定收盘或存在分歧的数据项及其对裁决的影响。

An institutional-grade, plain-language multi-asset investment research monorepo unifying **Gold** (1971–2030 Master Report + Daily Morning/Evening Converged Main Editions), **Global Equities** (**China A-Share 76 × Hong Kong 75 × US Stocks 80 — 231-stock** 7-dimension deep dossiers + **80+ ETF Radar** + All-4-Main daily editions since `2026-11-26_1800`), and **8 China Personal Multi-Asset Channels** (Bonds, Funds/WM, Reverse Repo, Onshore/Offshore QDII & MRF, Large CDs, Convertible Bonds, C-REITs, and Non-Gold Commodity ETFs), synchronized via an **8+1** research workflow, cross-project Gold SSOT consistency gate, structured `data_caveats` transparency, and automated GitHub Pages publishing.

---

## 更新节拍 · Publication Schedule (CST / UTC+8)

黄金、全球三市权益、重点 ETF 与 8 大个人多元渠道采用 **每日 2 场一体化单会话流水线**（共享 **8 路并发深度调研 + 1 路统一红队** → 黄金 SSOT 先行落盘严检 → 三地权益、多元渠道、ETF 矩阵与 7 维个股深研只读接力 → 统一 RSI 盲审 + 单次 `scripts/publish_site.py` 发布至 GitHub Pages 与 Releases）。自 **`>= 2026-11-26_1800`** 起，工作日早/晚班次全面升级为 **四市全主刊（All-4-Main）+ 8+1 深研** 架构，定时运行窗与跨轨截点容差统一为 **6 小时**：

| 北京时间（CST） | 班次 / Schedule | 单会话串行产出 / Editions（`>= 2026-11-26_1800` All-4-Main + 8+1 深研） |
| :--- | :--- | :--- |
| **07:30** | **一体化早报** (`daily-global-investment-research`) | **Step 3 黄金早报**（完整收敛主刊，写入 `gold/data_snapshot.json` SSOT 与 `data_caveats`） → **Step 4 三地权益全主刊 + 多元渠道/ETF/7 维个股深研**（A/港/美三市均发 5–6 页完整主刊含 ≥2 图，内嵌 8 大多元渠道与重点 ETF 雷达及焦点股 7 维拆解，并增量刷新三大深研 JSON；休市/半日市受影响市场切 `holiday_watch` 含 ≥1 图） → **Step 5 统一 RSI 与单次发布** |
| **18:00** | **一体化晚报** (`daily-global-investment-research-evening`) | **Step 3 黄金晚报**（完整收敛主刊，刷新 `gold/data_snapshot.json` 与 `data_caveats`） → **Step 4 三地权益全主刊 + 多元渠道/ETF/7 维个股深研**（封账两融、中金所席位、南向资金、美股盘后终盘及 8 大多元渠道日终利率/溢价/退市红线，刷新重点 ETF 与焦点股 7 维档案） → **Step 5 统一 RSI 与单次发布** |
| **周六 / 周日** | **周末专项 / 复盘** | 周六 07:30 黄金周末专项主刊 + 美股周五复盘主刊（美股半日市发 `holiday_watch` 含 ≥1 图，全休沿用旧稿）；周六晚与周日三市默认沿用旧稿，周日刷新 `SCORECARD.md` 公开记分卡、轮换精修 231 股池 7 维深度档案及周度校准 8 大多元渠道与 80+ 重点 ETF |

---

## 仓库结构 · Repository Structure

```text
global-investment-research/
├── AGENTS.md                       # 仓库顶层统一编排宪章（07:30/18:00 一体化 8+1 架构与跨轨硬约束）
├── .agents/skills/                 # 统一工作区三 Skill（gold-research-publishing + equity 双 Skill）
├── automations/                    # 定时自动化共享提示词、授权清单与脱敏模板（零个人路径）
│   ├── unified-edition.prompt.md   # 早晚双班共用 8+1 流水线与盲审闭环提示词
│   ├── permissions.json            # 统一无通配符命令与读写授权白名单
│   └── sidecars/                   # 脱敏版 07:30/18:00 一体化定时任务模板
├── gold/                           # 黄金深度研报体系（跨项目 SSOT 写入源）
│   ├── 黄金跨世纪周期与2026-2030终审研究报告.md
│   ├── data_snapshot.json          # 日报实时数据源、跨项目红绿灯裁决 SSOT 与 data_caveats 披露源
│   ├── master_snapshot.json        # 全景主报告独立锁定基线
│   ├── market_calendar.json        # 60+ 天跨市场休市与冬/夏令时日历
│   └── daily/                      # 每日早晚报、公开记分卡 SCORECARD、CHANGELOG 与 AUDIT_LOG
├── equity/                         # 全球三市权益、ETF 雷达与 8 大多元渠道研报体系
│   ├── {a_share,hk_stock,us_stock}_market_report_{YYYY_MM,latest}.md
│   ├── report_meta_{a_share,hk_stock,us_stock}.json
│   ├── state/
│   │   ├── market_state.json       # 三市灯号、政策雷达、跨市熔断阀、data_caveats 与黄金只读镜像
│   │   ├── multi_asset_channels.json # 8 大个人多元合规渠道实盘利率、规则红线与追踪流程 SSOT
│   │   ├── etf_universe.json       # 80+ 只三市与全球/跨境/固收/商品重点 ETF 深度矩阵 SSOT
│   │   └── deep_dossiers.json      # 全部 231 只龙头 7 维机构级深度研究档案 SSOT
│   ├── build_{a_share,hk_stock,us_stock}_pdf.py / build_daily.py / pdf_common.py / docx_embed.py
│   ├── edition_plan.py / lint_equity.py
│   └── daily/                      # 三市每日早晚报、总看板 INDEX、SCORECARD 与 CHANGELOG
├── scripts/                        # 统一静态门户构建、严格门禁、班次锁、凭据校验与发布引擎
│   ├── build_site.py               # 生成双端响应式门户（index/channels/etfs/screener/scorecard/archive/reports/daily）
│   ├── lint_site.py                # 静态站点 6 道法证与安全严格校验（S1–S6）
│   ├── publish_site.py             # 预检 -> 构建严检 -> 单提交推送 -> 滚动更新 Release PDF/DOCX
│   ├── edition_run.py / artifact_receipt.py / install_sidecars.py
│   └── web_assets/                 # 站点样式与交互脚本（含 7 维个股弹窗与 ETF 详情弹窗）
├── tests/                          # 编排、出版、门户、黄金与权益全链路单元测试套件
└── .github/workflows/
    └── deploy-pages.yml            # 回归测试与源稿预检后构建并部署至 GitHub Pages
```

> 注：本地编译生成的 `.pdf`、`.docx`、`_site/` 与 `latest_*.html` 均已通过 `.gitignore` 隔离，保持 Git 仓库轻量整洁；最新精排 PDF 与原生 ECMA-376 OOXML Word 文档通过 `scripts/publish_site.py` 滚动发布至 GitHub Releases（`latest-reports`）。

---

## 本地构建、质检与发布 · Local Build, Lint & Publish

### 1. 研报质量门禁（Report Linters）
```bash
# 先看该班三市应交哪种稿件、哪些市场沿用旧稿
python3 equity/lint_equity.py --plan 2026-11-26_1800

# 黄金 7 道门禁全量严检（0 错误 0 警告）
python3 gold/lint_readability.py \
  gold/黄金跨世纪周期与2026-2030终审研究报告.md \
  gold/daily/2026-11-26_0730_早报_黄金深度研报.md \
  --strict

# 权益全量法证 + 三大深研库校验 + 跨项目黄金 SSOT 门禁（Gates 0-6, 3B, C1-C3）
python3 equity/lint_equity.py --strict

# 与发布器和 GitHub Actions 共用的源稿检查，可在没有 PDF / Word 的环境运行
python3 scripts/publish_site.py --check-manuscripts
python3 -m unittest discover -s tests
```

### 2. 静态网站构建与严检（Static Site Build & Lint）
> 零第三方依赖（仅需 Python 3.9+ 标准库即可直接构建与严检，无需 `pip install`）。
```bash
python3 scripts/build_site.py --out _site
python3 scripts/lint_site.py _site --strict
```

### 3. 一键构建、严检与发布（Automated Publish CLI）
```bash
python3 scripts/publish_site.py --dry-run
python3 scripts/publish_site.py --no-push
python3 scripts/publish_site.py
python3 scripts/publish_site.py --skip-release
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

### 5. 恢复中断班次
先查 `python3 scripts/edition_run.py status` 和对话状态，明确未发起推送时用 `recover <班次ID> <尝试编号> <原因>`，发布中断时用 `resume <班次ID> <尝试编号>` 续跑同一提交与 token，仅 Pages 等待时重跑 `complete <token>`。

---

## 免责声明 · Disclaimer

本仓库及在线网站所载全部研报、数据、图表与情景测算均基于公开官方市场与公司披露资料整理，**仅供投资研究、知识学习与风险教育参考，不构成任何针对个人的证券买卖要约、收益承诺或投资建议**。金融市场受利率、汇率、地缘政治与流动性多重风险影响，历史回溯与概率框架不代表未来表现，投资决策请结合自身风险承受能力与专业持牌顾问意见独立审慎作出。
