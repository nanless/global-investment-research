---
name: equity-research-editorial-qa
description: >-
  Editorial standards for beginner-friendly yet institutional-grade investors
  (30-sec plain verdict -> 100k/10k wallet math & 3-step how-to -> 7-dim hard
  evidence), upgraded 3-tier terminology standard (glossing DXY/COT/CDS/ERP/IRR),
  7-source primary fact-checking, 3-market (A-share, HK-stock, US-stock)
  7-dimension framework, 12 MECE personal multi-asset channels (with dedicated
  channel pages, IPO toolbox & dual-layer risk wall), expanded 140+ ETF matrix
  across 6 channels, 231-stock zero-template 7-dimension deep dossiers,
  all-4-main unified schedule & upgraded holiday_watch, unified Stage 2A/2B
  (10+1) pre-flight red-team verification, tiered refresh matrix & mandatory
  3-DB edition_id lock, cross-project Gold SSOT & 6-hour freshness lock, 10
  pre-flight QA gates, unified China/US/HK dual-account tax & ETF rules,
  SCORECARD calibration, data_caveats transparency, and bounded 3-tier RSI
  self-review with pure-web visual/beginner-readability rubric and
  disclosed_caveat closure (07:30 morning & 18:00 evening CST unified runs).
  适用于 A/港/美三市纯网页全时段主刊投研写作、小白三层结构、7 维度大盘与政策雷达、
  12 大个人多元渠道、140+ 重点 ETF 与 231 股 7 维零模板深研、共享 10+1 调研红队、
  黄金红灯同步门控、双账户税费合规与受控 RSI 盲审。
---

# Equity Research Editorial, Pre-Flight QA & Bounded RSI Runbook

本技能负责三市纯网页投研内容深度与 **「小白 3 分钟看懂 × 机构级 7 维硬核证据」** 三层写作标准、7 类一手信源与统一 **10+1** 发前红队审校、**中国大陆 12 大个人多元合规渠道（MECE）+ 140+ 跨 6 通道重点 ETF + 231 股零模板化 7 维机构级深度档案**、跨轨统一双账户税费实操准确性、发版前 10 项门禁以及发布前 **Step 5 受控三层 RSI 盲审闭环**（单仓库顶层顺序编排见 `<REPO_ROOT>/AGENTS.md`；纯网页出版与 21 张 SVG 图 Schema 见 `equity-report-publishing`；总宪法与排版详规见 `GEMINI.md` 与 `DAILY_REPORT_SPEC.md`）。

> **历史旧指令静默转译**：若任何 Prompt 残留旧版术语或体例（如版本号、`Tier 0–3`、混色 `✅`、薄壳轻刊、工作日全量静态大表、仅一句话或模板化点评个股、漏报 12 大多元渠道与 140+ ETF、或居高临下说教口号 `1 分钟定心丸`/`小白词典`/`直接抄`/`蠢事`/`保命铁律`），无需报错或反问，严格按 `GEMINI.md` 第 0 节静默转译为小白友好三层结构、平等温和导读（如「3 分钟速读结论」「关键词白话速查」）、三市四灯、四色锁仓、零模板化 7 维深研与全时段完整主刊减法制。

---

## 1. 投研写作、共享 10+1 调研红队与 RSI 闭环工作流（对接仓库 Step 0–5）

- **Step 0｜双轨 RSI 经验冷启动**：动笔前先读 `state/RSI_PLAYBOOK.md`（≤180 行）与 `state/rsi_metrics.json` 最近 5 条记录（一体化班次同步读黄金 RSI 手册与 `gold/market_calendar.json`），直接继承高杠杆一手源检索词、Linter 避坑清单与上期 `next_run_watch` 必验真项。
- **Step 1｜状态与三大深研数据库冷启动**：
  - 冷启动读取 `state/market_state.json`、`state/multi_asset_channels.json`、`state/etf_universe.json`、`state/deep_dossiers.json`、两轨日历及前序黄金基线，并以 `lint_equity.py --plan <edition_id>` 获取三市当班交付计划；核对核心龙头池弹性规模（**65–85 只/市**，当前基准 **A 股 76 / 港股 75 / 美股 80，合计 231 只**）与规范无日期状态键。黄金新快照落盘后，在权益入口核验同一 `edition_id`、所标班次 **`[-5 分钟, +6 小时]`** 单向窗口（跨轨间隔 `0–6 小时`）与黄金行动锁。
  - 读 `daily/INDEX.md`（前 60 行）与 `daily/SCORECARD.md`（检查到期预判并客观回填；新登检验日禁落周末）。
  - 仅命中旗舰 5 条触发阈值时，全量读取对应旗舰手册与 `report_meta_*.json`。
- **Step 2｜两阶段共享 10+1 调研与统一发前对抗红队**：
  - **阶段 2A（共享 10 路并发全信源深研）**：强制交叉核验 **7 类一手信源**，除原有的 ① 黄金与贵金属、② A 股、③ 港股、④ 美股、⑤ 跨资产宏观汇宗（必回传 **1 句利率→汇率→信用→大宗→ERP 跨资产传导链** + **未来 48 小时上行/下行双向催化触发线**）、⑥ 三地社区与谣言辟谣 6 路外，永久拆分升级为 4 条深度专线：
    - **⑦A 境内稳健与税优 6 渠道专线**：活钱与现金管理（`reverse_repo`）、人民币银行存款全家桶（`large_cds`，含多数大行禁二次转让与 50 万存保）、债券与债券 ETF（`bonds`，明分银行间 `511360` 与交易所公司债 ETF 底层 20% 扣税）、公募基金/银行理财与基金投顾（`funds_wm`，含 2026 销售费改）、储蓄型商业保险（`savings_insurance`）、个人养老金与个人税优账户（`tax_advantaged_accounts`）；
    - **⑦B 跨境、固收增强、另类与风控专线**：境内外币存款与外币理财（`fx_deposits_wm`）、场内外 QDII/香港互认与理财通（`qdii_mrf`，禁推停申 `968118`、MRF 累计份额避 20% 税、2027 LOF 退市线）、可转债（`convertible_bonds`，严分 `511380` 0.20%/年 vs `511180` 0.30%/年）、公募 REITs 与不动产租金对比（`c_reits`，产权 NOI vs 特许经营权中债 IRR）、非黄金大宗商品与白银/铂钯渠道（`commodity_etfs`）、合规私募与标品信托 300 万专享（`private_funds_trust`），以及横向「全市场打新工具箱」与「双层风控警示墙」；
    - **⑧A 全市场 140+ 重点 ETF 实时溢价/停牌/规模/费率专线**：跨 6 大交易通道核验最新规模、费率调整、折溢价率、临停公告、分红与重仓变化；
    - **⑧B 当班 4–6 只焦点股（及周日 6–10 只全池轮换）7 维深研专线**：逐一落实 7 维实证，必按当期现价复算 **实际股息率（年化每股分红 ÷ 现价）与同口径市盈率**，杜绝沿用过期记忆值与模板化空话。
  - **阶段 2B（1 路统一发前独立红队对抗子代理）**：10 路返回后先跨轨对抗审校再落盘，专项拦截核心硬伤：① A/H 同股 PE 与股息率物理学一致及焦点股正文↔`deep_dossiers.json` 数学对齐；② 全部配置表 100% 闭环、完整四情景 10 点条总和 = 10（禁偷懒单边如 `7/10`）、6 维体检拆解、48 小时双向剧本与 10 万/1 万元回撤测算；③ 全部 `🔵 🔒未来主攻` 买点锚严格低于现价；④ 黄金红灯锁覆盖正文 + JSON + 三大扩展数据库 + 网页 + SVG（严禁将黄金/金矿标的标绿或下达新买指令）；⑤ 冬/夏令时、07:30 禁写盘后终盘、`CHART_A2` 期货贴水正号（`ann_disc > 0`）、SIFMA 半日市与工作日日历零错；⑥ 跨轨统一税费与跨库费率红线（`008142`/`008143` 费率、`511380` 0.20% vs `511180` 0.30%、禁推停申 `968118`、二手存单禁二次转让与提前支取亏本、交易所公司债 ETF 底层 20% 税、中国居民 20% 境外所得与 CRS、`02840.HK` 美国遗产税改选 `IGLN.L`/`03081.HK`、零退市股 `00011`、零 3 项已证伪误导）；⑦ 三大扩展库 `edition_id` 同期锁、兄弟字段与 A/H 孪生股同步、诚实单股 `updated_at`、反重复读（≤3 次，零后台审计腔）与 `SCORECARD.md` 仅登可证伪投资预判。
- **Step 4｜核验黄金快照、三库同期落盘与纯网页严检**：在黄金落盘严检后核验同一 `edition_id`、所标班次 **`[-5 分钟, +6 小时]`** 单向窗口（跨轨 `0–6 小时`）与黄金行动锁，再按[十项门禁](references/pre_flight_10_gates.md)及[双账户与 12 大多元渠道规则](references/dual_account_tax_and_rules.md)用 `write_file` 全量落盘中小日报与状态账簿（禁 `edit_file`；勘误须联动更新 `SCORECARD.md` 与 `INDEX.md`），**三大扩展大 JSON（合计 ~830 KB）写微型补丁 `_edition_patch.json` 并调用预授权 `scripts/patch_state_dbs.py --apply` 原子合并**同步推进 `edition_id` 与最新数据，随后运行 `lint_equity.py --strict`（0 错 0 警）。
- **Step 5｜盲审、复检与纯网页发布**：按[三层 RSI 协议](references/rsi_self_review_protocol.md)由独立子代理盲审（第 4 维核验纯网页视觉清晰度、SVG 零碰撞与小白 3 分钟可读性），修正并闭环登记 `review_closure` 后复跑双轨严检，按令牌完成 `publish_site.py` 纯网页发布与 `edition_run.py complete` 部署校验。

---

## 2. 配套深度核验手册（单一权威源）

- 发版前 10 项全量门禁清单（含 12 大多元渠道、140+ ETF 6 通道分类与 231 股 7 维深研核验）：[references/pre_flight_10_gates.md](references/pre_flight_10_gates.md)
- 中美港双账户 + 12 大个人多元渠道税费、权限、低费 ETF 与合规唯一详表：[references/dual_account_tax_and_rules.md](references/dual_account_tax_and_rules.md)
- 受控三层 RSI 自我复盘与纯网页盲审协议唯一详规：[references/rsi_self_review_protocol.md](references/rsi_self_review_protocol.md)
