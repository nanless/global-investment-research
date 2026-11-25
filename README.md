# 全球大类资产与跨周期投研门户 · Global Investment Research

> **在线阅读门户（GitHub Pages）**：[https://nanless.github.io/global-investment-research/](https://nanless.github.io/global-investment-research/)  
> **最新精排 PDF & 原生 Word（`.docx`）打包下载**：[GitHub Releases · `latest-reports`](https://github.com/nanless/global-investment-research/releases/tag/latest-reports)

面向普通理性投资者的机构级、零术语墙跨市场投研出版仓库。统一覆盖 **黄金（1971–2030 全景主报告 + 每日早晚报）** 与 **中国 A 股 × 中国香港股市 × 美国股市（7 维大盘框架 × 135 只全板块核心龙头全景手册 + 每日三市早晚报）**，以黄金快照为跨项目单一事实源（SSOT）实现跨市场红绿灯联防与零冲突质检。

An institutional-grade, plain-language multi-asset investment research monorepo unifying **Gold** (1971–2030 Master Report + Daily Morning/Evening Editions) and **Global Equities** (**China A-Share × Hong Kong × US Stocks** flagship handbooks + daily briefings), synchronized via a cross-project Gold SSOT consistency gate and published automatically to GitHub Pages.

---

## 更新节拍 · Publication Schedule (CST / UTC+8)

黄金与全球三市权益采用 **每日 2 场一体化单会话流水线**（共享 6 路并发调研 + 1 路统一红队 → 黄金 SSOT 先行落盘严检 → 三地权益零延迟只读接力 → 统一 RSI 盲审 + 单次 `scripts/publish_site.py` 发布至 GitHub Pages 与 Releases）：

| 北京时间（CST） | 班次 / Schedule | 单会话串行产出 / Editions |
| :--- | :--- | :--- |
| **07:30** | **一体化早报** (`daily-global-investment-research`) | **Step 3 黄金早报**（纽约 06:00 终盘、国内夜盘、跨资产分化与买金四步红绿灯，写入 `gold/data_snapshot.json` SSOT） → **Step 4 三地权益早刊**（美股隔夜复盘主刊 + A 股 / 港股盘前快报，零延迟只读校验黄金 SSOT 并校核 03:00 恒指夜期盲窗） → **Step 5 统一 RSI 与单次发布** |
| **18:00** | **一体化晚报** (`daily-global-investment-research-evening`) | **Step 3 黄金晚报**（上金所 15:30 终盘、沪金 15:00 收盘与龙虎榜、亚欧盘实况，刷新 `gold/data_snapshot.json`） → **Step 4 三地权益晚刊**（A 股 / 港股收盘主刊 + 美股欧亚盘/盘前哨兵轻刊，封账两融、中金所席位、南向资金与盘后终盘） → **Step 5 统一 RSI 与单次发布** |
| **周六 / 周日** | **周末专项 / 复盘** | 周六 07:30 黄金周末专项版（CFTC / 链上金 / 线下客流）+ 美股周五复盘主刊；周日刷新 `SCORECARD.md` 公开记分卡并推进核心龙头 6 维轮换深研 |

---

## 仓库结构 · Repository Structure

```text
global-investment-research/
├── AGENTS.md                       # 仓库顶层统一编排宪章（07:30/18:00 一体化双任务与跨轨硬约束）
├── .agents/skills/                 # 统一工作区三 Skill（gold-research-publishing + equity 双 Skill）
├── automations/sidecars/           # 脱敏版 07:30/18:00 一体化定时任务模板（零个人路径）
├── gold/                           # 黄金深度研报体系（跨项目 SSOT 写入源）
│   ├── 黄金跨世纪周期与2026-2030终审研究报告.md
│   ├── data_snapshot.json          # 日报实时数据源 & 跨项目红绿灯裁决 SSOT
│   ├── master_snapshot.json        # 全景主报告独立锁定基线
│   ├── market_calendar.json        # 60+ 天跨市场休市与冬/夏令时日历
│   ├── build_daily.py / build_report.py / docx_embed.py / lint_readability.py
│   └── daily/                      # 每日早晚报、公开记分卡 SCORECARD、CHANGELOG 与 AUDIT_LOG
├── equity/                         # 全球三市权益研报体系（A 股 × 港股 × 美股）
│   ├── {a_share,hk_stock,us_stock}_market_report_{YYYY_MM,latest}.md
│   ├── report_meta_{a_share,hk_stock,us_stock}.json
│   ├── state/market_state.json     # 三市灯号、政策雷达、跨市熔断阀与黄金只读镜像
│   ├── build_{a_share,hk_stock,us_stock}_pdf.py / build_daily.py / pdf_common.py / docx_embed.py / lint_equity.py
│   └── daily/                      # 三市每日早晚报、总看板 INDEX、SCORECARD 与 CHANGELOG
├── scripts/                        # 统一静态门户构建、严格门禁、发布与本地定时安装引擎
│   ├── build_site.py               # 生成响应式多资产静态阅读门户（_site/）
│   ├── lint_site.py                # 静态站点死链、结构与可读性严格校验
│   ├── publish_site.py             # 编译 -> 严检 -> 提交推送 -> 滚动更新 Release PDF/DOCX
│   ├── install_sidecars.py         # 渲染/原子安装本机定时任务配置并校验零漂移
│   └── web_assets/                 # 站点样式与交互脚本
└── .github/workflows/
    └── deploy-pages.yml            # push main 自动构建、严检并部署至 GitHub Pages
```

> 注：本地编译生成的 `.pdf`、`.docx`、`_site/` 与 `latest_*.html` 均已通过 `.gitignore` 隔离，保持 Git 仓库轻量整洁；最新精排 PDF 与原生 ECMA-376 OOXML Word 文档通过 `scripts/publish_site.py` 滚动发布至 GitHub Releases（`latest-reports`）。

---

## 本地构建、质检与发布 · Local Build, Lint & Publish

### 1. 研报质量门禁（Report Linters）
```bash
# 黄金 7 道门禁全量严检（0 错误 0 警告）
python3 gold/lint_readability.py \
  gold/黄金跨世纪周期与2026-2030终审研究报告.md \
  gold/daily/2026-11-25_0730_早报_黄金深度研报.md \
  --strict

# 权益全量法证 + 跨项目黄金 SSOT 门禁（Gates 0-6, 3B, C1-C3）
python3 equity/lint_equity.py --strict
```

### 2. 静态网站构建与严检（Static Site Build & Lint）
> 零第三方依赖（仅需 Python 3.9+ 标准库即可直接构建与严检，无需 `pip install`）。
```bash
python3 scripts/build_site.py --out _site
python3 scripts/lint_site.py _site --strict
```

### 3. 一键构建、严检与发布（Automated Publish CLI）
```bash
# 本地预演（临时目录构建 + 严检 + 预览 Git 状态和同刊附件）
python3 scripts/publish_site.py --dry-run

# 仅本地提交（不推送远程）
python3 scripts/publish_site.py --no-push

# 全自动发布（验证最终提交树、推送 main，并逐件核对线上附件哈希）
python3 scripts/publish_site.py

# 仅推送网站源码，跳过 Release 附件上传
python3 scripts/publish_site.py --skip-release
```

### 4. 本机定时任务安装与漂移校验（Local Sidecar Sync）

使用同一个 Python 执行安装和两种检查。`--check` 比对配置文件，`--check-runtime` 另验 Antigravity 的启用、项目和授权。渲染目标是 `~/.gemini/config/sidecars/`。首次安装后，在 Antigravity 内启用这两个任务，已有任务会保留注册状态。

```bash
python3 scripts/install_sidecars.py
python3 scripts/install_sidecars.py --check
python3 scripts/install_sidecars.py --check-runtime
python3 scripts/edition_run.py status
```

两条定时任务共享运行锁，状态记录包括研究、黄金、权益、发布和 Pages 结果。失败后在任务记录里核对当前阶段。若会话意外终止，确认它已结束后可用 `scripts/edition_run.py recover <班次ID> <原因>` 释放锁，再从已验证的材料继续。

---

## 免责声明 · Disclaimer

本仓库及在线网站所载全部研报、数据、图表与情景测算均基于公开官方市场与公司披露资料整理，**仅供投资研究、知识学习与风险教育参考，不构成任何针对个人的证券买卖要约、收益承诺或投资建议**。金融市场受利率、汇率、地缘政治与流动性多重风险影响，历史回溯与概率框架不代表未来表现，投资决策请结合自身风险承受能力与专业持牌顾问意见独立审慎作出。

*All reports, data tables, and scenario analyses in this repository and its published portal are compiled from public official sources for informational and educational research purposes only. Nothing herein constitutes personalized financial, tax, or legal advice, nor a solicitation to buy or sell any security or commodity. Past performance and historical regimes do not guarantee future results.*
