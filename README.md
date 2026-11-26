# 全球大类资产与跨周期投研门户 · Global Investment Research

> **在线阅读门户（GitHub Pages）**：[https://nanless.github.io/global-investment-research/](https://nanless.github.io/global-investment-research/)  
> **最新精排 PDF & 原生 Word（`.docx`）打包下载**：[GitHub Releases · `latest-reports`](https://github.com/nanless/global-investment-research/releases/tag/latest-reports)

面向普通理性投资者的机构级、零术语墙跨市场投研出版仓库。统一覆盖 **黄金（1971–2030 全景主报告 + 每日早晚报）** 与 **中国 A 股 × 中国香港股市 × 美国股市（7 维大盘框架 × 全板块核心龙头全景手册 + 每日三市早晚报）**，以黄金快照为跨项目单一事实源（SSOT）实现跨市场红绿灯联防与零冲突质检。

An institutional-grade, plain-language multi-asset investment research monorepo unifying **Gold** (1971–2030 Master Report + Daily Morning/Evening Editions) and **Global Equities** (**China A-Share × Hong Kong × US Stocks** flagship handbooks + daily briefings), synchronized via a cross-project Gold SSOT consistency gate and published automatically to GitHub Pages.

---

## 更新节拍 · Publication Schedule (CST / UTC+8)

黄金与全球三市权益采用 **每日 2 场一体化单会话流水线**（共享 6 路并发调研 + 1 路统一红队 → 黄金 SSOT 先行落盘严检 → 三地权益按当班计划只读接力 → 统一 RSI 盲审 + 单次 `scripts/publish_site.py` 发布至 GitHub Pages 与 Releases）：

| 北京时间（CST） | 班次 / Schedule | 单会话串行产出 / Editions |
| :--- | :--- | :--- |
| **07:30** | **一体化早报** (`daily-global-investment-research`) | **Step 3 黄金早报**（纽约 06:00 终盘、国内夜盘、跨资产分化与买金四步红绿灯，写入 `gold/data_snapshot.json` SSOT） → **Step 4 三地权益早刊**（美股隔夜复盘主刊 + A 股 / 港股盘前快报，零延迟只读校验黄金 SSOT 并校核 03:00 恒指夜期盲窗） → **Step 5 统一 RSI 与单次发布** |
| **18:00** | **一体化晚报** (`daily-global-investment-research-evening`) | **Step 3 黄金晚报**（上金所 15:30 终盘、沪金 15:00 收盘与龙虎榜、亚欧盘实况，刷新 `gold/data_snapshot.json`） → **Step 4 三地权益晚刊**（A 股 / 港股收盘主刊 + 美股欧亚盘/盘前哨兵轻刊，封账两融、中金所席位、南向资金与盘后终盘） → **Step 5 统一 RSI 与单次发布** |
| **周六 / 周日** | **周末专项 / 复盘** | 周六 07:30 黄金周末专项版（CFTC / 链上金 / 线下客流）+ 美股周五复盘主刊；周日刷新 `SCORECARD.md` 公开记分卡并推进核心龙头 6 维轮换深研 |

进入发布前，独立盲审须核对当期总看板、记分卡、状态和各载体。两轨分别记录已修正问题的复验证据。待公布或一时取不到的数字须在报告中留空或挂账，并记录数据来源和回补期号。程序在切换到发布阶段和检查提交时，都核对两轨的盲审处置记录。

---

## 仓库结构 · Repository Structure

```text
global-investment-research/
├── AGENTS.md                       # 仓库顶层统一编排宪章（07:30/18:00 一体化双任务与跨轨硬约束）
├── .agents/skills/                 # 统一工作区三 Skill（gold-research-publishing + equity 双 Skill）
├── automations/                    # 定时自动化共享提示词、授权清单与脱敏模板（零个人路径）
│   ├── unified-edition.prompt.md   # 早晚双班共用流水线与盲审闭环提示词
│   ├── permissions.json            # 统一无通配符命令与读写授权白名单
│   └── sidecars/                   # 脱敏版 07:30/18:00 一体化定时任务模板
├── gold/                           # 黄金深度研报体系（跨项目 SSOT 写入源）
│   ├── 黄金跨世纪周期与2026-2030终审研究报告.md
│   ├── data_snapshot.json          # 日报实时数据源 & 跨项目红绿灯裁决 SSOT
│   ├── master_snapshot.json        # 全景主报告独立锁定基线
│   ├── market_calendar.json        # 60+ 天跨市场休市与冬/夏令时日历
│   ├── build_daily.py / build_report.py / chart_input.py / docx_embed.py
│   ├── edition_validation.py / lint_readability.py
│   └── daily/                      # 每日早晚报、公开记分卡 SCORECARD、CHANGELOG 与 AUDIT_LOG
├── equity/                         # 全球三市权益研报体系（A 股 × 港股 × 美股）
│   ├── {a_share,hk_stock,us_stock}_market_report_{YYYY_MM,latest}.md
│   ├── report_meta_{a_share,hk_stock,us_stock}.json
│   ├── state/market_state.json     # 三市灯号、政策雷达、跨市熔断阀与黄金只读镜像
│   ├── build_{a_share,hk_stock,us_stock}_pdf.py / build_daily.py / pdf_common.py / docx_embed.py
│   ├── edition_plan.py / lint_equity.py
│   └── daily/                      # 三市每日早晚报、总看板 INDEX、SCORECARD 与 CHANGELOG
├── scripts/                        # 统一静态门户构建、严格门禁、班次锁、凭据校验与发布引擎
│   ├── artifact_receipt.py         # PDF/Word 与编译输入指纹凭据生成及校验
│   ├── edition_run.py              # 早晚双班运行锁、阶段推进、盲审闭合与 Pages/Release 验收
│   ├── build_site.py               # 生成响应式多资产静态阅读门户（_site/）
│   ├── lint_site.py                # 静态站点 6 道法证与安全严格校验（S1–S6）
│   ├── publish_site.py             # 预检 -> 构建严检 -> 单提交推送 -> 滚动更新 Release PDF/DOCX
│   ├── install_sidecars.py         # 渲染/原子安装本机定时任务配置并校验零漂移
│   └── web_assets/                 # 站点样式与交互脚本
├── tests/                          # 编排、出版、黄金与权益全链路单元测试套件
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

# 权益全量法证 + 跨项目黄金 SSOT 门禁（Gates 0-6, 3B, C1-C3）
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
# 本地预演（临时目录构建 + 严检 + 预览 Git 状态和同刊附件）
python3 scripts/publish_site.py --dry-run

# 仅本地提交（不推送远程）
python3 scripts/publish_site.py --no-push

# 无活动班次时的人工发布
python3 scripts/publish_site.py

# 仅同步站点源码的人工操作
python3 scripts/publish_site.py --skip-release

# 一体化班次在 publish 阶段正式交付
python3 scripts/publish_site.py --edition-token <token>
python3 scripts/edition_run.py complete <token>
```

发布使用最终提交的源稿、数据时点、模板和渲染代码核对 PDF/Word 的编译凭据。首次启用需要为现行黄金主报告、黄金最新日报、三个权益旗舰和三个最新权益日报各编一次，以实际编译生成本地的 `*.artifacts.json`。黄金先编、权益后编，合计八对。遇到某一对因输入变化被拒，按报错重新编译那一对即可。只做源码预演可以使用 `--check-manuscripts`，或使用 `--dry-run --skip-release` 同时验证站点。

归档时一并移动同名的 Markdown、PDF、Word 和 `*.artifacts.json`。曾发布的早晚报保留原网页地址，修订版各有独立地址。门户的下载入口提供最新文件，历史网页可以在线阅读和打印。

### 4. 本机定时任务安装与漂移校验（Local Sidecar Sync）

早晚班共用 [定时提示词](automations/unified-edition.prompt.md) 与 [授权声明](automations/permissions.json)。安装器从模板生成 Antigravity 本机定义，运行时使用安装同一个 Python。先检查两个班次均无执行中会话，更新后在 Antigravity 内确认注册、授权和启用状态。`--check` 比对安装文件，`--check-runtime` 另外校验真实项目和配置授权，报告终端沙箱状态。首次实跑用任务触发记录与 `status` 的本期记录、GitHub Pages 部署和附件凭据核对。

```bash
python3 scripts/install_sidecars.py
python3 scripts/install_sidecars.py --check
python3 scripts/install_sidecars.py --check-runtime
python3 scripts/edition_run.py status
```

### 5. 恢复中断班次

先查 `python3 scripts/edition_run.py status` 和 Antigravity 对话状态。恢复涉及释放锁时，确认之前的会话已经结束，再读取刚返回的 `edition` 和 `attempt`。不要把完整 token 转发或写进报告。

- 研究或编译阶段退出，且明确未发起推送，执行 `python3 scripts/edition_run.py recover <班次ID> <尝试编号> <原因>`。下一次使用同一期号，重新验证已有材料；旧失败记录会保留。
- 发布中断或推送结果不明，执行 `python3 scripts/edition_run.py resume <班次ID> <尝试编号>` 取回该次 token，接着重跑 `publish_site.py --edition-token <token>`。发布器使用原来那次提交和已保存的传输状态。下载已验完、仅 Pages 未结束时，直接重跑 `edition_run.py complete <token>`。下一班可以自动复验已有完整凭据的部署。
- 远端 Release 仍被前一个发布者占用时，先确认其进程已经退出，核对报错所列的锁资产编号，再在人工恢复中使用 `--recover-release-lock <资产ID>`。原发布会话已退出、确定放弃该次提交且它已不在远端 `main` 上时，可用 `edition_run.py close-superseded <班次ID> <尝试编号> <原因>` 关闭旧尝试，保留尝试提交与现有远端提交的记录。

---

## 免责声明 · Disclaimer

本仓库及在线网站所载全部研报、数据、图表与情景测算均基于公开官方市场与公司披露资料整理，**仅供投资研究、知识学习与风险教育参考，不构成任何针对个人的证券买卖要约、收益承诺或投资建议**。金融市场受利率、汇率、地缘政治与流动性多重风险影响，历史回溯与概率框架不代表未来表现，投资决策请结合自身风险承受能力与专业持牌顾问意见独立审慎作出。

*All reports, data tables, and scenario analyses in this repository and its published portal are compiled from public official sources for informational and educational research purposes only. Nothing herein constitutes personalized financial, tax, or legal advice, nor a solicitation to buy or sell any security or commodity. Past performance and historical regimes do not guarantee future results.*
