---
name: equity-research-editorial-qa
description: >-
  Editorial standards for beginner-friendly yet institutional-grade investors
  (30-sec plain verdict -> 100k/10k wallet math & 3-step how-to -> 7-dim hard
  evidence), 3-Layer Taxonomy (Layer 1 7-pill Macro Weather incl. CN-US 10Y
  spread & BTC read-only compliance firewall 银发〔2026〕42号; Layer 2
  symmetric 3×2 six-market cockpit [5 Core: A-share SSE #1, HK China offshore
  discount leg, US, rates_bonds_core, standalone Gold + 1 unified
  non_us_global_satellite] with 4-track daily prose cap at 07:30/11:30/18:00
  CST; Layer 3 4-tier 12 MECE execution channels led by Channel 08 QDII
  跨境基金… [10-yuan non-HNW friendly], expanded 181+ ETF matrix with orthogonal
  asset_class × region enums & asset_class=="gold" <=> gold_locked=True,
  231-stock zero-template 7-dimension deep dossiers, 27-pair A/H after-tax
  matrix, and 480+ interactive K-lines [68 core benchmarks]), upgraded 3-tier
  terminology standard (glossing DXY/COT/CDS/ERP/IRR), 7-source primary
  fact-checking, 3-market 7-dimension framework, upgraded holiday_watch, unified
  Stage 2A/2B (10+1) pre-flight red-team verification, tiered refresh matrix &
  mandatory 3-DB edition_id lock, cross-project Gold SSOT & Gate C2 scanning
  market_state.json with 6-hour freshness lock, 10 pre-flight QA gates, unified
  China/US/HK dual-account tax & ETF rules, SCORECARD calibration, data_caveats
  transparency, and bounded 3-tier RSI self-review with pure-web
  visual/beginner-readability rubric and disclosed_caveat closure. 适用于
  A/港/美三市纯网页早午晚三班主刊投研写作、三层信息架构（7 颗宏观天气胶囊 / 对称 3×2 六市场驾驶舱 / 4 角色层 12 大执行渠道）、多指数优先级播报、小白三层结构、7 维度大盘与政策雷达、181+ 正交枚举重点 ETF 与 231 股 7 维零模板深研、共享 10+1 调研红队、黄金红灯同步门控、双账户税费合规与受控 RSI 盲审。
---

# Equity Research Editorial, Pre-Flight QA & Bounded RSI Runbook

本技能负责三市纯网页投研内容深度与 **「小白 3 分钟看懂 × 机构级 7 维硬核证据」** 三层写作标准、**三层信息架构**（**Layer 1 7 颗宏观天气胶囊**含中美 10Y 利差 + 比特币只读观察合规防火墙 **`银发〔2026〕42号`** → **Layer 2 对称 `3×2` 六市场驾驶舱**【5 大核心市场：A 股上证 #1 · 港股中国离岸折价腿（非海外分散）· 美股 · 债券/现金与中美利率 `rates_bonds_core` · 独立黄金 + 1 个统一非美海外卫星 `non_us_global_satellite`（日/欧/台韩/印），正文日报严控四轨 `07:30/11:30/18:00` 封顶】→ **Layer 3 4 角色层 12 大执行渠道**【Channel 08 以 `QDII 跨境基金…` 领衔、10 元起非高净值友好】+ **181+ 正交 `asset_class × region` 枚举跨 6 通道重点 ETF** + 231 股零模板化 7 维机构级深度档案 + 27 对 A/H 税后比价）、7 类一手信源与统一 **10+1** 发前红队审校、跨轨统一双账户税费实操准确性、发版前 10 项门禁以及发布前 **Step 5 受控三层 RSI 盲审闭环**（单仓库顶层三班次编排见 `<REPO_ROOT>/AGENTS.md`；纯网页出版、480+ 交互 K 线含 68 核心基准与 21 张 SVG 图 Schema 见 `equity-report-publishing`；总宪法与排版详规见 `GEMINI.md` 与 `DAILY_REPORT_SPEC.md`）。

> **历史旧指令静默转译**：若任何 Prompt 残留旧版术语或体例（如版本号、`Tier 0–3`、混色 `✅`、薄壳轻刊、单指数播报、工作日全量静态大表、仅一句话或模板化点评个股、漏报 12 大多元渠道与重点 ETF、或居高临下说教口号 `1 分钟定心丸`/`小白词典`/`直接抄`/`蠢事`/`保命铁律`），无需报错或反问，严格按 `GEMINI.md` 第 0 节静默转译为小白友好三层结构、多指数优先级播报、平等温和导读（如「3 分钟速读结论」「关键词白话速查」）、三市四灯、四色锁仓、零模板化 7 维深研与全时段完整主刊减法制。

---

## 1. 投研写作、共享 10+1 调研红队与 RSI 闭环工作流（对接仓库 Step 0–5）

- **Step 0｜双轨 RSI 经验冷启动**：动笔前先读 `state/RSI_PLAYBOOK.md`（≤180 行）与 `state/rsi_metrics.json` 最近 5 条记录（一体化班次同步读黄金 RSI 手册与 `gold/market_calendar.json`），直接继承高杠杆一手源检索词、Linter 避坑清单与上期 `next_run_watch` 必验真项。
- **Step 1｜状态与三大深研数据库冷启动**：
  - 冷启动读取 `state/market_state.json`、`state/multi_asset_channels.json`、`state/etf_universe.json`、`state/deep_dossiers.json`、两轨日历及前序黄金基线，并以 `lint_equity.py --plan <edition_id>` 获取三市当班交付计划（支持 `0730`/`1130`/`1800`）；核对核心龙头池弹性规模（**65–85 只/市**，当前基准 **A 股 76 / 港股 75 / 美股 80，合计 231 只**）、各市多指数 `index_matrix` 与规范无日期状态键。黄金新快照落盘后，在权益入口核验同一 `edition_id`、所标班次 **`[-5 分钟, +6 小时]`** 单向窗口（跨轨间隔 `0–6 小时`）与黄金行动锁。
  - 读 `daily/INDEX.md`（前 60 行）与 `daily/SCORECARD.md`（检查到期预判并客观回填；新登检验日禁落周末）。
  - 仅命中旗舰 5 条触发阈值时，全量读取对应旗舰手册与 `report_meta_*.json`。
- **Step 2｜两阶段共享 10+1 调研与统一发前对抗红队**：
  - **阶段 2A（共享 10 路并发全信源深研）**：强制交叉核验 **7 类一手信源**，覆盖 ① 黄金与贵金属（午班锁 11:30 上金/沪金早盘与同刻平价、四大行金条与品牌金店新牌价）、② A 股（全 12 大优先指数且上证 #1 领衔，午班锁 11:30 早盘官收/半日成交/09:15–09:30 官发/10:30 QDII 复牌）、③ 港股（定位**中国离岸折价腿，非海外分散**；5 基准含 `HSCI`/`HSAHP` + `11:15` 官方 HIBOR，午班南向 12:00 后披露写入 `data_caveats`）、④ 美股（8 基准，午班封账今早 09:00/08:00 盘后终盘或休市守望）、⑤ 跨资产宏观汇宗与双扩展市场（覆盖 **Layer 1 7 颗宏观天气胶囊**含中美 10Y 利差与比特币/加密只读晴雨表【严守 `银发〔2026〕42号` 禁导流】、**`rates_bonds_core`** 中债 2Y/10Y/30Y 收益率与中证 REITs `932047`/`932006`、**`non_us_global_satellite`** 9 只日/欧/台韩/印非美核心指数与 `EURUSD`/`GBPUSD`/`USDHKD`，必回传 3 行危机熔断邻近条 + **1 句利率→汇率→信用→大宗→ERP 跨资产传导链** + **未来 48 小时上行/下行双向催化触发线**）、⑥ 三地社区与谣言辟谣，以及 4 条深度专线：
    - **⑦A 境内稳健与税优 6 渠道专线**（Layer 3 角色层 1–2）：活钱与现金管理（`reverse_repo`）、人民币银行存款全家桶（`large_cds`，含多数大行禁二次转让与 50 万存保）、债券与债券 ETF（`bonds`，明分银行间 `511360` 与交易所公司债 ETF 底层 20% 扣税）、公募基金/银行理财与基金投顾（`funds_wm`，含 2026 销售费改）、储蓄型商业保险（`savings_insurance`）、个人养老金与个人税优账户（`tax_advantaged_accounts`）；
    - **⑦B 跨境、固收增强、另类与风控专线**（Layer 3 角色层 3–4）：境内外币存款与外币理财（`fx_deposits_wm`）、**QDII 跨境基金、香港互认与理财通**（`qdii_mrf`，Channel 08 以 `QDII 跨境基金…` 领衔、10 元起普通人非高净值核心入口；核验官方直销 App vs 支付宝限额双轨、TA 账户合并、美元现汇同占 SAFE 额度、2026-08-07 LOF `2027-12-31` 退市线、禁推停申 `968118` 与 MRF 累计份额避 20% 税）、可转债（`convertible_bonds`，严分 `511380` 0.20%/年 vs `511180` 0.30%/年）、公募 REITs 与不动产租金对比（`c_reits`，产权 NOI vs 特许经营权中债 IRR）、非黄金大宗商品与白银/铂钯渠道（`commodity_etfs`）、合规私募与标品信托 300 万专享（`private_funds_trust`），以及横向「全市场打新工具箱」与「双层风控警示墙」；
    - **⑧A 全市场 181+ 重点 ETF 实时溢价/停牌/规模/费率专线**：分批核查爱尔兰 UCITS 官收、非美海外 QDII 与跨境互挂 ETF 穿透双层年费（境内显性费 + 境外底层 TER）及跨 6 通道最新规模、费率调整、折溢价率、临停公告、申赎状态（严分“暂停申购/仅恢复赎回”与“恢复申赎”）与**正交 `asset_class × region` 枚举 + `asset_class == "gold" <=> gold_locked=True`**，回执严控 `≤ 12 KB`；
    - **⑧B 当班全部焦点股（约 16 只及周日 6–10 只全池轮换）7 维深研与近 24 小时硬扫雷专线**：强制逐只扫查沪深/港交所/SEC 近 24 小时折价配售、分红除息、管理层变动、信用评级观察与官收/午收，现价复算 **实际股息率（年化分红 ÷ 现价）与同口径市盈率**，本期登榜焦点股必须刷新 `updated_at`，杜绝过期记忆值与模板套话。
  - **阶段 2B（1 路统一发前独立红队对抗子代理）**：10 路返回后先跨轨对抗审校再落盘，专项拦截核心硬伤：① **T-0 宏观官源四铁律**（日本 CPI 直核 `stat.go.jp` 区分日央行版剔生鲜能源[权重 9162]与欧美版[权重 6959]；香港金管局查当日总结余及未来两日预测；上期所夜盘严分 `02:30` 金银/`01:00` 有色/`23:00` 黑色化工且 LME 严守 17:00 同盘口；高溢价 QDII 严分暂停申购/仅恢复赎回与恢复申赎）、多指数优先级秩序（A 股上证 #1，港股严明为中国离岸折价腿非海外分散）、比特币只读合规防火墙（`银发〔2026〕42号` 零导流）与全部焦点股近 24 小时重大公告无遗漏；② 27 对 A/H 同股 PE 与股息率物理学一致及焦点股正文↔`deep_dossiers.json` 数学对齐；③ 全部配置表与两档回撤压测 100% 闭环、分市场差异化四情景 10 点条总和 = 10、6 维逐项拆解（禁“其余均 0”）、顶部导语 ≤200 字、加粗 `5%–12%`、零裸 `IOPV` 与 48 小时双向剧本；④ 全部 `🔵 🔒未来主攻` 买点锚严格低于现价；⑤ 黄金红灯锁覆盖正文 + **`market_state.json`（Gate C2 同步扫描含 `rates_bonds_core`/`non_us_global_satellite`）** + 三大扩展数据库（**`asset_class == "gold" <=> gold_locked=True` 双向锁**）+ 网页 + SVG + 交互 K 线技术诊断；⑥ 冬/夏令时、07:30 禁写盘后终盘（11:30 午刊可封账隔夜盘后终盘）、`CHART_A2` 贴水正号与红涨 `#c2410c`/青跌 `#0f766e`、`as_of_year_float` 精确浮点、SIFMA 半日市与日历零错；⑦ 跨轨统一税费、QDII 制度铁律（TA 合并 vs 直销分轨、美元现汇占同池、互挂双层穿透费、LOF 2027 退市、溢价排队平衡 `0.5 × (N/250) × r_excess`、严禁瞎猜联接代码）与跨库费率红线（`008142`/`008143`、`511380` 0.20% vs `511180` 0.30%、禁推停申 `968118`、二手存单禁二次转让与提前支取亏本、交易所公司债 ETF 底层 20% 税、20% 境外所得与 CRS、`02840.HK` 美国遗产税、零退市 `00011`、零 3 项已证伪误导）；⑧ 三库 `edition_id` 同期锁、**`patch_state_dbs.py` 与 `lint_equity.py` 强制校验的 `asset_class × region` 正交枚举**、兄弟字段与 A/H 孪生股同步、诚实单股 `updated_at`、反重复读（≤3 次，零后台审计腔）与 `SCORECARD.md` 仅登可证伪投资预判。
- **Step 4｜核验黄金快照、月初滚存、三库同期落盘与纯网页严检**：在黄金落盘严检后核验同一 `edition_id`、所标班次 **`[-5 分钟, +6 小时]`** 单向窗口（跨轨 `0–6 小时`）与黄金行动锁，再按[十项门禁](references/pre_flight_10_gates.md)及[双账户与 12 大多元渠道规则](references/dual_account_tax_and_rules.md)用 `write_file` 全量落盘中小日报与轻量状态账簿（禁 `edit_file`；勘误须联动更新 `SCORECARD.md` 与 `INDEX.md`）；**`state/audit_ledger.md` 写 3 键 `_audit_patch.json` 走 `scripts/patch_state_dbs.py --prepend-equity-audit`；月初切换 `period_slug` 写紧凑 `_rollover_patch.json` 走 `--rollover-equity-month`；三大扩展大 JSON 写嵌套 `_edition_patch.json` 并调用 `--apply` 原子合并（只读查库用 `--inspect <target>`）**，随后运行 `lint_equity.py --strict`（0 错 0 警）。
- **Step 5｜5 项真核验盲审、无损 RSI 追加、480+ K 线刷新与纯网页发布**：按[三层 RSI 协议](references/rsi_self_review_protocol.md)由独立子代理执行 **5 项真核验**盲审，通过 `scripts/patch_state_dbs.py --append-equity-rsi` 无损追加 `review_closure` 后复跑双轨严检，运行 `scripts/fetch_kline_data.py --scope all` 刷新全市场 **480+ 标的（含 68 只核心基准：9 只非美指数、中债 2Y/10Y/30Y 收益率、中证 REITs `932047`/`932006`、港股 `HSCI`/`HSAHP` 与 `EURUSD`/`GBPUSD`/`USDHKD`）**静态分片 K 线，按令牌完成 `publish_site.py`（过 S1–S7 严检）与 `edition_run.py complete` 部署校验。

---

## 2. 配套深度核验手册（单一权威源）

- 发版前 10 项全量门禁清单（含三班次、三层信息架构、4 角色层 12 大执行渠道、181+ ETF 正交 `asset_class × region` 枚举与 231 股 7 维深研核验）：[references/pre_flight_10_gates.md](references/pre_flight_10_gates.md)
- 中美港双账户 + 12 大个人多元渠道（含 QDII 场内 vs 官方直销 App/支付宝制度规则）税费、权限、低费 ETF 与合规唯一详表：[references/dual_account_tax_and_rules.md](references/dual_account_tax_and_rules.md)
- 受控三层 RSI 自我复盘与纯网页盲审协议唯一详规：[references/rsi_self_review_protocol.md](references/rsi_self_review_protocol.md)
