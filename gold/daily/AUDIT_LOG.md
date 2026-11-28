# 黄金研报体系·独立红队质检与法证审计账本（AUDIT_LOG）

> **档案定位**：本文件专门收纳全部跨源数据消歧、版本迭代详细修订、病毒式谣言逐条证伪与一手官方数据库索引，与面向普通读者的主报告/早午报正文**物理分离**——既确保 100% 机构级透明溯源与自动化系统继承，又不污染读者的首屏阅读体验。

---

## 2026-11-28 · 维护勘误

原记录第 15 项的场外金条税负与回购条件曾作统一推定。当前口径按购入主体、标准黄金的实际出库用途、销售环节发票及回购合同逐笔核对。[财政部、税务总局黄金税收公告](https://fgk.chinatax.gov.cn/zcfgk/c102416/c5244740/content.html)

<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-28_1130",
  "as_of_short": "2026-11-28 12:00",
  "note": "完成 2026-11-28 11:30 周末专项午报四重交叉验证与 7 项分歧终审仲裁：直连 Cboe 官方历史日线表核销 2026-11-27 完整行（O 24.89 / H 27.52 / L 23.81 / C 23.81，正式升级为已发布并清零暂定滞后项）；直连 SSGA 官方净值表核销 GLD 11/27 官方 NAV $332.980175 (+4.85%, AUM $120.073B, 份额 360.6M 零变动 = 0.00 吨净流，全周 -6.56 吨)、VanEck 官网核销 GDX 11/27 官方 NAV $78.89 (+7.04%, AUM $24.77B) 及双源与 7 位小数数学反验核销 LBMA 11/27 午盘定盘 $3,634.50 (+1.55%，清零午盘定盘滞后项)；直连上金所官方日表纠偏 11/27 Ag(T+D) 递延费为多付空（交收量自 11/26 256.92 吨骤降 90.8% 至 23.76 吨）；三源核实周六品牌金店提价 20-25 元至周大福 1,093 元/克（老凤祥/周生生 1,092 元，婚庆立省扩至 279 元/克 / 50 克 13,950 元 / 25.5%），并驳回工行主动积存 0 费今日到期误读（核实官网已无缝延至 2027-03-31）；核实标普下调法国展望至负面、日央行行长植田和男 11/30 09:05 CST 名古屋演讲、ICE 布油 1 月合约 11/30 到期换月、土耳其央行 11/26 暂停本土矿金优先购金权、COMEX 银库存降至 323.0M oz 及周六午间只读 XAUT $3,649.55 / PAXG $3,647.89 / BTC $59,980；买金维持红灯停（2/4 关，禁止新买）与全景主报告 0/5 锁（+0.46% < 3%、60日新高止损与尾部深熊 0/2）。",
  "sources": {
    "real_yield": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv"],
    "rate_spread": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv", "https://markets.newyorkfed.org/api/rates/all/latest.json"],
    "vix": ["https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", "https://www.cboe.com/us/futures/market_statistics/settlement/csv?dt=2026-11-27"],
    "ny_close": ["https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/navhist-us-en-gld.xlsx", "https://www.vaneck.com/us/en/investments/gold-miners-etf-gdx/", "https://www.sge.com.cn/sjzx/quotation_daily_new", "https://www.cmegroup.com/markets/metals/precious/gold.settlements.html"]
  },
  "forecast_review": {
    "status": "none_due",
    "note": "本 2026-11-28 11:30 周末午报时段无新增到期结案预判（累计保持 10 项计分：5 兑现 / 5 部分兑现 / 0 证伪，完全兑现率 50.0%、至少部分兑现 100.0%），新增 1 项周一四大行金条温和浮动与植田和男演讲联动追踪，并在既有追踪项追加 11/27 Cboe 官表、GLD 零流、Ag(T+D) 翻多付空与链上零缺口进展注记。",
    "sources": ["https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", "https://www.sge.com.cn/sjzx/quotation_daily_new"]
  }
} -->

### 2026-11-28 11:30 周末专项午报核验记录（截点 2026-11-28 12:00）

- **三大信任资产增量（累计拦谣 51 条 · 模型升级 18 项 · 细节校准 47 项 · 核心结论影响 0/47）**：① 新增拦谣 #49–#51：拆穿“工行主动积存 0 费今日到期须赶单”（官网已无缝顺延至 2027-03-31）、“品牌金店周六涨 25 元且水贝热闹等于周一跳空逼空”（链上 XAUT $3,649.55 对应平价约 781.3 元零缺口）与“布油跌破 91 美元等于通胀警报解除”（系 11/30 1 月合约切 2 月 4.60 美元换月贴水）；② 新增校准 #45–#47：依上金所官方日表将 11/27 `Ag(T+D)` 递延费方向纠偏为 `多付空`（交收量 256.92→23.76 吨）、更新周六品牌金店提价至 `1,093 元/克`（婚庆立省扩至 `279 元/克` / `25.5%`）、并提前全量核销 Cboe 11/27 VIX 官行 `23.81`、SSGA `GLD` 11/27 官净 `$332.98`（`0.00 吨` 零流）、VanEck `GDX` 11/27 官净 `$78.89`（`$24.77B`）与 LBMA 11/27 PM `$3,634.50`。
- **剩余滞后官方表挂账（归周一晚报/周二早报）**：仅余山东黄金（`600547`）11/26 业绩说明会正式文字纪要与因感恩节按官方日历顺延至 `2026-12-01 04:30 CST` 的 CFTC COT 持仓周报。

---

<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-28_0730",
  "as_of_short": "2026-11-28 07:55",
  "note": "完成 2026-11-28 07:30 周末专项早报四重交叉验证：核销美国财政部 11/27 官方收益率曲线（10Y 4.94% +9bp、DFII10 2.79% +6bp、T10YIE 2.15% +3bp、2Y 4.69% +8bp -> +81bp 利差、30Y 5.33% +9bp）；核销纽约 17:00 现货金官收 $3,652.11 (+1.76%，高于 11/25 前高 $3,589.85 闯过第 4 关，下周新门槛 $3,685.31)，买金由 1/4 升至 2/4 仍严格锁定 Tier 0 红灯停（new_buy_allowed=false）与主报告 0/5 锁（+0.46% < 3%、60日新高硬止损与尾部深熊 0/2）；核销 Cboe 11/27 黑五早收暂定 VIX 23.81（-11.16%，10日窗口推进至 11/16..11/27，同步核销官方期货结算 UX1 22.8402 / UX2 22.7857 与 SKEW 145.90，周末非发布窗 vix_live=null）；核销美联储 H.4.1 周报（周三银行储备 $2,928.66B 跌破 $2.98T、TGA $923.56B）、NY Fed 黑五 SRF $23.15B、ON RRP $350M、FRED 11/25 HY 377bp / CCC 1,417bp、COMEX 11/27 官结（GCZ26 $3,639.60 / GCG27 $3,668.50 / SIZ26 $43.167 / HGZ26 $5.517）、LME 3M 铜官收 $12,262、02:30 国内金银夜盘终盘（au2702 781.36 / Au99.99 782.00 同刻溢价 +2.97 元 / Au(T+D) 780.14 溢价 +1.11 元 / ag2702 10,344）与 01:00 有色夜盘沪铜 92,590 (+0.84%)、深交所 159934/159937 份额（6金基合计净赎回 -3.99 亿元）及周日 OPEC+ 与周一 $81.51B 私部门净抽水官方算式。",
  "sources": {
    "real_yield": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv"],
    "rate_spread": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv", "https://markets.newyorkfed.org/api/rates/all/latest.json"],
    "vix": ["https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", "https://finance.yahoo.com/quote/%5EVIX"],
    "ny_close": ["https://www.kitco.com/charts/gold", "https://www.sge.com.cn/sjzx/mrhqsj", "https://www.shfe.com.cn/data/tradedata/future/dailydata/kx20261127.dat", "https://www.cmegroup.com/markets/metals/precious/gold.settlements.html"]
  },
  "forecast_review": {
    "status": "settled",
    "note": "客观结案 2 项到期预测（2026-11-26 早报黑五第 4 关与实际利率双检验、2026-11-27 午报亚盘轧空不改黑五红灯停）均为 ✅ 兑现：11/27 纽约金收 $3,652.11 站上 $3,589.85 闯过第 4 关，但美债官方曲线 DFII10 升至 2.79%、2Y-FF 扩至 +81bp 双卡前两关，严格维持 2/4 红灯停新仓 0%；累计投资计分 10 项升至 5 兑现 / 5 部分兑现 / 0 证伪（完全兑现率 50.0%、至少部分兑现 100.0%），新增 2 项下周一/二追踪。",
    "sources": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv", "https://www.federalreserve.gov/releases/h41/current/"]
  }
} -->

### 2026-11-28 07:30 周末专项早报核验记录（截点 2026-11-28 07:55）

- **三大信任资产增量（累计拦谣 48 条 · 模型升级 18 项 · 细节校准 44 项 · 核心结论影响 0/44）**：① 新增拦谣 #47–#48：拆穿“纽约金站稳 3,652 闯过第 4 关升至 2/4 已亮黄灯”与“纽约联储常备回购激增 231.5 亿等于重启放水”；② 新增校准 #42–#44：锁定周一 11/30 美债私部门真实净抽水官方算式（$218.00B 发行 − $136.49B 私营到期 = $81.51B）、核销 `161226` 11/27 正式净值 `1.1213`（静态溢价 +14.96%，明确系董事长曲刚变更非基金经理）并校准 `IAUM` 规模为 `$7.25B`。
- **剩余滞后官方表挂账（归周一早/晚报）**：11/27 Cboe 官方 CSV 日线行（现用暂定 23.81）、11/27 SPDR 持仓 / VanEck 净值 / LBMA 午盘金定盘公开镜像、山东黄金说明会文字纪要及因感恩节顺延至 12/01 04:30 的 CFTC COT 持仓周报。

---

<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-27_1800_r2",
  "as_of_short": "2026-11-27 23:55",
  "note": "完成 2026-11-27 18:00 工作日晚报 23:55 BJT 修订封账版四重交叉验证：核销 Cboe VIX_History.csv 已补录 2026-11-26 完整行（O 27.18 / H 27.54 / L 26.57 / C 26.80，status 升级为 published，十日窗口推进至 2026-11-13..2026-11-26）及 23:55 BJT（10:55 EST 黑五常规窗内）实盘 VIX 25.38（倒挂 UX1 23.73 > UX2 23.30）；核销 23:55 黑五美盘现货金自日高 $3,685.11 倒吐 $61.77 至 $3,623.34 (+0.96% vs 11/25 NY)、布油 1 月 BZF27 自 $98.06 倒跌至 $94.80 (-1.83%) 与 WTI 翻跌至 $83.45 (-0.27%) 之际 10Y 名义美债反升至 4.914%、10Y 实际利率 US10YTIPS 扩至 2.783%（日内 2.735%-2.796% 未触 ≤2.72%）、2Y 美债升至 4.697%（实时利差 +81.7bp）；核销 NY Fed 11/25 SOFR 3.95% (+5bp vs IORB)、11/27 LBMA AM 金定盘 $3,672.10 (+3.08%) / 银午盘 $44.0400 (+6.02%)、国内四大黄金 ETF 11/27 官方 NAV（518880 7.4473/-0.085%/-3.72 亿、518800 7.8078/+0.80 亿、159934 7.7806、159937 7.4308；沪市 4 只合计净赎回 -3.25 亿）、SGE Au(T+D) 递延费由空付多翻转为多付空及夜盘自 786.60 回吐至 778.03（按同刻离岸汇率 6.6552 折算理论平价 775.28、温和价差 +2.75 元/+0.35%，无逼空抢筹）、SHFE au2702 夜盘 777.32 (-1.08%/OI +1,882) 与 ag2702 夜盘 10,287 (-1.87%/OI +11,152) 及具名席位明细；买金维持 Tier 0 红灯停（1/4 关、new_buy_allowed=false）与主报告 0/5 锁（含 60 日新高硬止损与尾部深熊 0/2 核验）。",
  "sources": {
    "real_yield": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv"],
    "rate_spread": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv", "https://markets.newyorkfed.org/api/rates/all/latest.json"],
    "vix": ["https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", "https://www.cboe.com/tradable_products/vix/"],
    "ny_close": ["https://www.lbma.org.uk/prices-and-data/precious-metal-prices", "https://www.sge.com.cn/sjzx/mrhqsj", "https://www.shfe.com.cn/data/tradedata/future/dailydata/kx20261127.dat", "https://www.shfe.com.cn/data/tradedata/future/dailydata/pm20261127.dat"]
  },
  "forecast_review": {
    "status": "none_due",
    "note": "本 23:55 修订封账版无新增到期结案项（11/27 早报 161226 与老铺除净项已于同日 18:30 初版严格结案为部分兑现，历史 10 项结案行保持原样零改动），并在 6 项持续追踪项中追加 23:55 美盘倒吐、实际利率 2.783% 与沪银夜盘回吐进展注记，待 2026-11-28 07:30 周六早报起逐项验真。",
    "sources": ["https://www.shfe.com.cn/data/tradedata/future/dailydata/kx20261127.dat", "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"]
  }
} -->

### 2026-11-27 18:00 晚报修订封账核验记录（截点 2026-11-27 23:55）

- **三大信任资产增量（累计拦谣 46 条 · 模型升级 18 项 · 细节校准 41 项 · 核心结论影响 0/41）**：① 新增拦谣 #45–#46：拆穿“欧盘破 3,685 证明高美债利率已拦不住金价启动”（美盘油价倒跌却推升 10Y 实际利率至 2.783%、现货金回吐 61.77 美元且沪市金基净赎回 3.25 亿）与“Au(T+D) 大涨代表实物逼空”（递延费已翻向多付空、15:30 仅微溢 +0.83 元且夜盘自 786.60 回吐至 778.03）；② 新增校准 #39–#41：彻底核销国内四大黄金基金 11/27 官方净值与沪市官方份额流（修正 18:30 初版混用 11/26 净值口径），补录 Cboe 11/26 官方收盘 26.80、NY Fed 11/25 SOFR 3.95% 及 11/27 LBMA 早盘金银定盘，并修正婚庆省钱表述重复笔误。
- **真正处于 23:55 窗口外的剩余挂账（归 `2026-11-28_0730`）**：美盘黑五正式收盘（02:00 美股 / 03:00 美债 / 03:45 期金 / 06:00 纽约现货日收）与 11/27 美债官曲/GLD 持仓/GDX 净值、11/25 TGA 与 HY/CCC OAS、11/27 LBMA 午盘金定盘公开镜像、01:00 LME 17:00 官收，以及深交所 159934/159937 当日份额变动与山东黄金说明会文字纪要。

---

<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-27_1800",
  "as_of_short": "2026-11-27 18:30",
  "note": "完成 2026-11-27 18:00 工作日晚报（黑五半日市盘前 A 类局部休市）四重交叉验证：全量封账 SGE 15:30 官方日终（Au99.99 784.00/+2.37%/加权 777.79、Au(T+D) 783.35 多付空、Ag(T+D) 10,456 多付空、上海金早 775.47[纠偏午报 768.24 旧值]/午 784.26）及 15:30 同刻溢价（+0.83 元/+0.11%）、SHFE kx20261127.dat（au2702 收 785.84/结 775.18、ag2702 收 10,483/结 9,971、cu2701 收 93,660/结 91,820）与 pm20261127.dat 前 20 席位（au2702 净多 +56,631/+2,647、ag2702 净多 +17,228/-3,147）；直核 18:20 BJT（05:20 EST，落入 Cboe 11/27 首窗 03:15-09:25 EST）实时现货恐慌 24.82（官收死守 11/25 28.29，11/26 no_row_confirmed），同步 18:11 欧盘现货金 $3,671.08 (+2.29% vs NY)、欧盘 10 年美债 4.912%/2 年 4.687%、布油 1 月 $97.25 与 16:30 在岸人民币 6.6544；买金维持 Tier 0 红灯停（1/4 关、新仓 0%）与主报告 0/5 锁。",
  "sources": {
    "real_yield": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv"],
    "rate_spread": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv", "https://markets.newyorkfed.org/api/rates/all/latest.json"],
    "vix": ["https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", "https://www.cboe.com/tradable_products/vix/"],
    "ny_close": ["https://www.sge.com.cn/sjzx/mrhqsj", "https://www.shfe.com.cn/data/tradedata/future/dailydata/kx20261127.dat", "https://www.shfe.com.cn/data/tradedata/future/dailydata/pm20261127.dat"]
  },
  "forecast_review": {
    "status": "settled",
    "note": "客观结案 2026-11-27 07:30 早报 161226 白银上市基金溢价压缩与老铺黄金 06181.HK 除净首日防贴权追踪项：161226 收涨 +5.22% 至 1.289 元但按 ag2702 官结 9,971 估值真实溢价反扩至 +14.88%-+15.25%；老铺大涨 +7.51% 盘中触 270.00 港元（填权 115.2%）、日终官收 264.20 港元（填权 87.65%，距 266.80 差 2.60 港元），严格记为 ⚠️ 部分兑现（累计投资计分 8 项：3 兑现 / 5 部分兑现 / 0 证伪，完全兑现率 37.5%），并新增 11/30 沪银空头与产油国会议追踪项。",
    "sources": ["https://www.shfe.com.cn/data/tradedata/future/dailydata/kx20261127.dat", "https://www.hkex.com.hk/"]
  }
} -->

### 2026-11-27 18:00 晚报核验记录（截点 2026-11-27 18:30）

- **三大信任资产增量（累计拦谣 44 条 · 模型升级 18 项 · 细节校准 38 项 · 核心结论影响 0/38）**：① 新增拦谣 #43–#44：拆穿“欧盘冲 3,671 已转黄灯/161226 溢价归零”（按 `ag2702` 官结 9,971 估值真实溢价仍约 +14.9%）与“银行金条紧缺断货”谣言；② 新增校准 #37–#38：纠偏 11/27 上海金早盘基准价为 `775.47` 元/克（替换滞后 11/26 旧值 `768.24`），并依黑五首发布窗（03:15–09:25 EST）精准记录 `18:20` 实盘恐慌 `24.82`（拦截 `26.80` 盘外杂讯作为官收）。
- **剩余晚间未挂网挂账（归 `2026-11-28_0730`）**：11/27 LBMA 早/午定盘、国内四大黄金 ETF 11/27 官方净值与份额流、山东黄金 11/26 业绩说明会文字纪要、LME 17:00 官收及 11/27 美盘黑五早收与 11/25 美国联邦滞后统计。

---

### 2026-11-27 11:30 午报核验记录（截点 2026-11-27 12:28）

<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-27_1130",
  "as_of_short": "2026-11-27 12:28",
  "note": "首次运行 11:30 午报：精确锁定 11:30 上金/沪金早盘官收与同刻平价溢价（+1.48 元）、11:11 国有四大行金条上调至 795.87 元/克、09:30 中国 10 月工企利润 +20.1% 及亚盘 10 年美债反跳 4.910%；严守四关以官方收盘为准（1/4 红灯停，新仓 0%），日终清算与份额流透明挂账至 18:00 晚报。",
  "sources": {
    "real_yield": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026"],
    "rate_spread": ["https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value=2026"],
    "vix": ["https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"],
    "ny_close": ["https://www.lbma.org.uk/prices-and-data/precious-metal-prices"]
  },
  "forecast_review": {
    "status": "none_due",
    "note": "本午报无到期结案项（11/27 早报 161226 与老铺除净项于今日 18:00 晚报按日终官收结案），新增 1 项黑五亚盘轧空不改红灯追踪项（周六 07:30 验真）。",
    "sources": ["https://www.sge.com.cn/sjzx/yshqbg", "https://www.stats.gov.cn/"]
  }
} -->

- **三大信任资产增量（累计拦谣 42 条 · 模型升级 18 项 · 细节校准 36 项 · 核心结论影响 0/36）**：① 拦截“现货金盘中破 3,630 已提前闯过第 4 关”、“沪银飙涨 10.75% 填平 161226 溢价（实测实时溢价仍约 +9% 且叠 2027 退市线）”与“银行金条半日涨 12.8 元系缺金恐慌”3 条午间误导；② 落地 `11:30` 三时段午报同刻溢价精算与 `index_matrix` 多锚点同步；③ 精确核实日本统计局东京都 11 月初报公报与国家统计局 10 月工企利润结构。

---

<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-27_0730",
  "as_of_short": "2026-11-27 07:55",
  "note": "完成 2026-11-27 07:30 一体化早报（07:55 BJT 截点，美国感恩节后黑五半日市前瞻）四重独立红队交叉核验：直连 Cboe VIX_History.csv（07:34 BJT = 18:34 EST > 11:30 EST 节日门槛）确认末行止于 2026-11-25（28.29），正式记录 2026-11-26 为 no_row_confirmed 并拒采 Yahoo 盘外零星 26.80；其余三关严格沿用 11/25 官数（DFII10 2.73% 差 1bp、2Y-FF +73bp、NY 收 $3,588.78 未过 $3,678.15，今晚黑五门槛滚降至 $3,589.85），维持 Tier 0 红灯停（1/4 关、new_buy_allowed=false）与主报告 0/5 锁；锁定 11/26 ICE 布油 1 月官结 $96.57 (+2.07%，拦截次月 2 月合约 $91.58-$91.75 换月贴水误判，金油比更新 37.16）、LSE IGLN.L 官收 $69.2375 (+3.34%/两日 +0.09%，纠偏 11/24 旧价 $69.18)、LME 3M 铜同口径 17:00 收 $11,872 (+1.91%)、02:30 金银夜盘官收与同分钟溢价（au2702 766.00/+1.92、Au(T+D) 764.00/-0.08、Au99.99 765.00/+0.92）与 01:00 有色夜盘官收（cu2701 89,270/+0.56%）、03:00 在岸人民币 6.6609 及 07:30 东京 11 月通胀（总体 2.8%/不含生鲜 2.9%/日央行版核心剔生鲜与能源 2.5%，仅较前值 2.6% 微降 0.1pp；欧美口径剔全部食品与能源为 2.3%）。",
  "sources": {
    "real_yield": [
      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv"
    ],
    "rate_spread": [
      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv",
      "https://markets.newyorkfed.org/api/rates/all/latest.json"
    ],
    "vix": [
      "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
      "https://www.cboe.com/about/hours/us-options/"
    ],
    "ny_close": [
      "https://www.lbma.org.uk/prices-and-data/precious-metal-prices",
      "https://www.sge.com.cn/sjzx/mrhqsj",
      "https://www.shfe.com.cn/"
    ]
  },
  "forecast_review": {
    "status": "settled",
    "note": "客观结案 11/26 18:00/23:55 追踪项（美盘感恩节停盘 3.5 小时薄量箱体 $3,530-$3,615 预警及三大滞后官表补录）：实测 11/26 感恩节全段国际现货金波幅 $3,551.57-$3,607.12（停盘前 $3,566.84、07:00 复盘 $3,564-$3,569）100% 落于锁定箱体内无突破，且伦敦定盘、SGE/SHFE 清算与三大黄金 ETF 份额流全部核实闭环，记为 ✅ 兑现（投资计分 7 项：3 兑现 / 4 部分兑现 / 0 证伪，完全兑现率 42.9%，另 1 项条件未触发、1 项运维记录不计胜率）。",
    "sources": [
      "https://www.lbma.org.uk/prices-and-data/precious-metal-prices",
      "https://www.sge.com.cn/sjzx/mrhqsj",
      "https://www.cmegroup.com/tools-information/holiday-calendar.html"
    ]
  }
} -->

## 2026-11-27 07:55 早报增量红队法证档案（累计 91 项：39 拦谣 / 17 升级 / 35 校准，核心影响 0 / 35）

- **新增拦谣 #38–#39（累计 39 项）**：
  - **#38**：行情端热传“布油突发暴跌 5% 跌回 91.6 美元，中东冲突缓和”——经核实 11/26 沙特吉赞炼厂遇袭推动 ICE 布油 1 月近月合约（`BRNF27`）官结大涨 `+2.07%` 至 **`$96.57/桶`**（今晨电子盘约 `$95.80`），终端所显 `$91.58–$91.75` 系自动换月至 2 月次月合约（`BRNG27`）因深贴水产生的 ~$5 展期价差，绝非暴跌。
  - **#39**：市场渲染“伦敦金基金 `IGLN.L` 暴涨 `+3.34%` 或 COMEX 2 月期金 `GCG27` 站上 `$3,592` 已提前突破第 4 关”——核实 `IGLN.L` `$69.24 (+3.34%)` 系补涨 11/25 伦敦收盘后美盘深 V（两日净变仅 `+0.09%`），而 `GCG27` 含高利率持仓升水 ~$25，现货金今晨 `$3,567.32` 仍压在 `$3,589.85` 下方，买金严格守红灯停。
- **新增细节校准 #34–#35（累计 35 项，对核心买金结论影响 0 / 35）**：
  - **#34**：直连 Cboe `VIX_History.csv` 确认 `2026-11-26` 无常规日线行（`no_row_confirmed`，`checked_at = 2026-11-27 07:34`），拦截 Yahoo Finance 盘外杂讯 `26.80` 并维持 `vix_live = null`。
  - **#35**：校准伦交所 `IGLN.L` 11/26 官收为 **`$69.2375`（`$69.24`）**（纠偏第 8A 路滞后 11/24 `$69.18`），并按 11/26 布油 1 月官结 `$96.57` 将 `gold_brent_ratio` 由 `37.93` 更新为 **`37.16`**。
- **一手链接与剩余日盘顺延**：[Cboe VIX_History.csv](https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv) · [Cboe US Options Hours](https://www.cboe.com/about/hours/us-options/) · [SGE 每日行情](https://www.sge.com.cn/sjzx/mrhqsj) · [SHFE](https://www.shfe.com.cn/) · [Japan Statistics Bureau Tokyo CPI](https://www.stat.go.jp/english/data/cpi/index.html) · [BoE Financial Stability Report](https://www.bankofengland.co.uk/financial-stability-report/2026/november-2026)。仅余 11/25 FRED OAS/SOFR/TGA（感恩节顺延至美东周五）、山东黄金 11/26 业绩会正式文字纪要及今日 09:00 国内银行金条/金店最新牌价待 `2026-11-27_1800` 晚报封账。

---

<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-26_1800_r2",
  "as_of_short": "2026-11-26 23:55",
  "note": "完成 2026-11-26 18:00 晚报修订封账版（23:55 BJT 截点，严格隔离次日凌晨 00:30 欧股/LSE、01:00 沪铜/TTF、03:00 CNY 延长夜盘与 03:30 布油官结）四重独立红队交叉核验：直连 Cboe VIX_History.csv 核销 2026-11-25 完整官方行（O 28.16 / H 34.95 / L 27.49 / C 28.29，正式由 provisional_close 升级为 published；23:55 BJT=10:55 EST < 11:30 EST 节日核查界线）；其余三关沿用 11/25 官数（DFII10 2.73%、2Y-FF +73bp、NY 收 $3,588.78），维持 Tier 0 红灯停（1/4 关、new_buy_allowed=false）与主报告 0/5 锁；集中核销 11/26 LBMA AM $3,562.40 / PM $3,578.90 / Ag $41.54、SGE Au99.99 均价 767.39 / Au(T+D) 均价 763.18 多付空 / Ag(T+D) 9,606、SHFE kx20261126.dat au2702 今结 756.32（纠偏昨结 768.96）与 pm20261126.dat 净多 +54,083 (+2,549)、SSE/SZSE 官方三大黄金 ETF 11/26 NAV 与合计净赎回 -3.42 亿元（518880 -1.86 亿连流 10 日、159937 -1.25 亿、518660 -0.31 亿）、HKEX 老铺 06181.HK 266.80（沽空暴增 112% 至 27.48%）与紫金 H 02899.HK 23.22，及 20:30 ECB 10 月鹰派纪要与 23:55 同刻沪金溢价 +2.43 元/克。",
  "sources": {
    "real_yield": [
      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv"
    ],
    "rate_spread": [
      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv",
      "https://markets.newyorkfed.org/api/rates/all/latest.json"
    ],
    "vix": [
      "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
      "https://www.cboe.com/tradable_products/vix/"
    ],
    "ny_close": [
      "https://www.lbma.org.uk/prices-and-data/precious-metal-prices",
      "https://www.sge.com.cn/sjzx/mrhqsj",
      "https://www.shfe.com.cn/data/tradedata/future/dailydata/kx20261126.dat"
    ]
  },
  "forecast_review": {
    "status": "none_due",
    "note": "原 18:00 晚报已结案 11/26 07:30 项为部分兑现（本修订版坚持历史不改判原则）；11/26 18:00 追踪项仍保留 11/27 07:30 验真节点，其中 11/26 LBMA/SGE/SHFE/三大金基/VIX 原表/老铺收盘等 6 大滞后表已于 23:55 提前清零。",
    "sources": [
      "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
      "https://www.sge.com.cn/sjzx/mrhqsj",
      "https://www.shfe.com.cn/data/tradedata/future/dailydata/pm20261126.dat"
    ]
  }
} -->

## 2026-11-26 23:55 晚报修订封账增量红队法证档案（累计 87 项：37 拦谣 / 17 升级 / 33 校准，核心影响 0 / 33）

- **新增拦谣 #36–#37（累计 37 项）**：
  - **#36**：行情软件传播“518880 今日主力大举净流入 +3.54 亿元，机构已右侧抄底”——经上交所 11/26 官方 ETF 份额表实证为二级市场盘口大单误导，一级市场实际净赎回 `-2,560 万份`（`-1.86 亿元`，连流 10 日），连同 `159937`（`-1.25 亿`）与 `518660`（`-0.31 亿`）合计净赎回 `-3.42 亿元`。
  - **#37**：晚间快讯渲染“沪银夜盘暴涨 +3.66%、沪金拉涨 +1.41% 假期逼空”——经上期所 `kx20261126.dat` 核实源于昨夜低位巨量拉低 11/26 官方结算价（`au2702 756.32`、`ag2702 9,332`），23:55 沪金 `767.02` 较 15:00 收盘实际微跌 `-0.08%`，同刻溢价仅 `+2.43 元/克`。
- **新增细节校准 #31–#33（累计 33 项，对核心买金结论影响 0 / 33）**：
  - **#31**：依 `kx20261126.dat` 与 SGE 日终表更正 `SHFE au2702` 今结为 `756.32`（原 1800 误留昨结 `768.96`）、`SGE Au99.99` 加权均价 `767.39`（替换旧值 `760.18`）与 `Ag(T+D)` 日收 `9,606`。
  - **#32**：依港交所 `d261126e.htm` 终结老铺黄金 `06181.HK` 18:30 多源冲突（铁锁官收 `266.80 港元`，沽空暴增 112% 至 `27.48%`），并校准紫金 H `02899.HK` 官收 `23.22 港元 (+2.74%)`。
  - **#33**：直连 Cboe `VIX_History.csv` 核销 `2026-11-25` 终值（`28.29` / 高 `34.95`）解除 `provisional_close`，补齐 11/26 `LBMA` AM `$3,562.40` / PM `$3,578.90` / Ag `$41.54`，并严格拦截次日凌晨 `00:30/01:00/03:00/03:30 CST` 欧股/LSE/沪铜/CNY/布油官收以保 23:55 截点纯度。
- **一手链接与剩余次晨待补**：[Cboe VIX_History.csv](https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv) · [SGE 每日行情](https://www.sge.com.cn/sjzx/mrhqsj) · [SHFE kx20261126](https://www.shfe.com.cn/data/tradedata/future/dailydata/kx20261126.dat) · [SHFE pm20261126](https://www.shfe.com.cn/data/tradedata/future/dailydata/pm20261126.dat) · [ECB 10 月纪要](https://www.ecb.europa.eu/press/accounts/2026/html/index.en.html) · [LME Copper](https://www.lme.com/Metals/Non-ferrous/LME-Copper)。仅余 11/25 FRED OAS（感恩节休市顺延）及山东黄金 11/26 业绩会文字纪要待次晨补核。

---

<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-26_1800",
  "as_of_short": "2026-11-26 18:30",
  "note": "完成 2026-11-26 18:00 一体化晚报（美国感恩节 A 类局部休市 · 收敛主刊首刊）独立红队交叉核验：美国股市与债市全天休市，四步红绿灯严格沿用 11/25 官数——DFII10 2.73%（差 1bp 未过第 1 关）、US2Y 4.61% − EFFR 3.88% = +73bp（未过第 2 关）、Cboe 官网产品页与 FRED VIXCLS 双锁 11/25 VIX 官收 28.29（+7.32%，第三方日高 34.95，vix_live=null，checked_at 刷新至 18:25 延续 provisional_close 通过第 3 关）、11/25 NY 现货官收 $3,588.78 未过 $3,678.15（第 4 关未过，周五黑五下期门槛 $3,589.85，主报告 0/5 锁）；红队拦截 SGE Au99.99 盘中高点 770.00 并校准日盘官收为 765.82 元/克（+1.12%，与上海金午盘 765.96、Au(T+D) 765.78、SHFE au2702 767.62 闭合），核实四大行金条均价上调 +4.91 元至 783.07 元/克、周大福足金饰品 1,068 元/克（驳回 939 金条价混用）、在岸 CNY 16:30 官收 6.6600（CFETS 6.7096），补齐 11/25 LBMA AM/PM $3,533.20/$3,466.35、GLD 1,027.88t (+0.57t)、GDX NAV $73.70 与 11/24 FRED OAS 372/1,405bp，并拦截老铺黄金 06181.HK 多源冲突报价挂账 pending。",
  "sources": {
    "real_yield": [
      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv"
    ],
    "rate_spread": [
      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv",
      "https://markets.newyorkfed.org/api/rates/all/latest.json"
    ],
    "vix": [
      "https://www.cboe.com/tradable_products/vix/",
      "https://fred.stlouisfed.org/series/VIXCLS",
      "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    ],
    "ny_close": [
      "https://www.investing.com/currencies/xau-usd-historical-data",
      "https://www.sge.com.cn/"
    ]
  },
  "forecast_review": {
    "status": "settled",
    "note": "按事先锁定标准客观结案 11/26 07:30 早报到期项（国内早盘补涨 +8–11 元与银行金条微调窗及四项滞后官方表补核）：国内 SGE Au(T+D) +8.88 元、Au99.99 +8.47 元精准落入 +6–12 元区间，四大行均价 778.16 → 783.07（+4.91 元）贴近 +5 元下沿，四项滞后表补齐 3 项（GLD 1,027.88t、GDX NAV $73.70、LBMA $3,533.20/$3,466.35）但 Cboe VIX_History.csv 原表未直连核销，依严苛标准记为“部分兑现”。",
    "sources": [
      "https://www.sge.com.cn/",
      "https://www.vaneck.com/us/en/investments/gold-miners-etf-gdx/",
      "https://www.spdrgoldshares.com/",
      "https://www.lbma.org.uk/prices-and-data/precious-metal-prices"
    ]
  }
} -->

## 2026-11-26 18:30 晚报增量红队法证档案（累计 82 项：35 拦谣 / 17 升级 / 30 校准，核心影响 0 / 30）

- **新增拦谣 #35（累计 35 项）**：船舶追踪与海外社媒热传伊朗 VLCC 超级油轮 *Khat Shekan*（“破线者”）突破美军封锁驶离霍尔木兹海峡、海峡封锁即将松动——经海事情报机构（TankerTrackers）与卫星影像证实完全为虚假 AIS 信号欺骗（hoax/spoofing），系拼接利比里亚籍无关油轮无线电呼号；海峡周度油轮通行量仍降逾 40%，预测市场定价年底前恢复正常航运仅 1%–4%。
- **新增系统升级 #17（累计 17 项）**：自 `2026-11-26_1800` 起全面切入收敛主刊架构（目标 5–6 页、4 张核心 KPI 卡、理性知情三档词表、全篇及全部组件零内部工程词与零居高临下说教口号、`.sn-grid` 防断句、图 1 胶囊 2D 防撞、图 2 动态刻度及 `data_caveats` 门户透明缺口披露）。
- **新增细节校准 #29–#30（累计 30 项，对核心买金结论影响 0 / 30）**：
  - **#29**：拦截第 1 路调研将盘中高点 `770.00` 混充 11/26 `SGE Au99.99` 日盘收盘，跨源核定 15:30 官收为 **`765.82 元/克 (+1.12%)`**（与上海金午盘 `765.96`、`Au(T+D) 765.78` 及 `SHFE au2702 767.62` 高度收敛）；同时拦截周大福投资金条 `939 元/克` 混充足金饰品价（仍稳于 **`1,068 元/克`**）。
  - **#30**：拦截港股老铺黄金（`06181.HK`）11/26 多源严重撕裂报价（`254.0` / `264.40` / `272.60` / `274.80`，含误用 11/24 旧收 `272.60` 作分母），严格裁定挂账 `pending` 沿用 11/25 确认官收 `HK$265.40`；同步补齐 11/25 `LBMA` AM `$3,533.20` / PM `$3,466.35` / Ag `$39.40`、`SPDR GLD 1,027.88t (+0.57t)`、`VanEck GDX NAV $73.70 (+3.08%)` 与 11/24 FRED `HY OAS 372bp / CCC OAS 1,405bp`。
- **2026-11-26 18:30 一手直采核心链接与待次晨补核清单**：
  - 核心源：[SGE 上海金基准](https://www.sge.com.cn/) · [SHFE](https://www.shfe.com.cn/) · [VanEck GDX NAV](https://www.vaneck.com/us/en/investments/gold-miners-etf-gdx/) · [SPDR GLD](https://www.spdrgoldshares.com/) · [LBMA Prices](https://www.lbma.org.uk/prices-and-data/precious-metal-prices) · [Cboe VIX](https://www.cboe.com/tradable_products/vix/) · [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS) · [FRED HY OAS](https://fred.stlouisfed.org/series/BAMLH0A0HYM2) · [FRED CCC OAS](https://fred.stlouisfed.org/series/BAMLH0A3HYC) · [CFETS](https://www.chinamoney.com.cn/english/bmkcpr/) · [OPEC](https://www.opec.org/)。
  - 待 `2026-11-27_0730` 早报补核项：① Cboe `VIX_History.csv` 11/25 原表直连核销；② 11/26 LBMA Gold AM Fix（18:30 刚到点）；③ SGE 11/26 加权均价与递延费方向、SHFE 今结与 `pm20261126.dat` 前 20 席位；④ 国内黄金 ETF（`518880`/`159937`/`518660`）11/26 官收与净值份额流；⑤ 山东黄金 16:00 说明会文字实录与老铺黄金 `06181.HK` 11/26 官收及 11/27 除净表现；⑥ FRED 11/25 `HY/CCC OAS`（感恩节休假顺延至美东 11/27）。

---

<!-- GOLD_EDITION_REVIEW {
  "edition_id": "2026-11-26_0730",
  "as_of_short": "2026-11-26 08:30",
  "note": "完成 2026-11-26 07:30 一体化早报红队交叉核验：美国财政部官方曲线确认 11/25 DFII10 2.73%（差 1bp 未过第 1 关）、US2Y 4.61% 减 NY Fed 11/24 EFFR 3.88% 等于 +73bp（未过第 2 关）；截至 08:24 BJT Cboe VIX_History.csv 仍止于 11/24（Last-Modified: Wed, 25 Nov 2026 02:11:05 GMT），依新规采信 Cboe 官网产品页 16:15 EST 官收 28.29（+7.32%）标 provisional_close 通过第 3 关（拒绝将第三方 34.95/27.49 归属 Cboe 官网，并清零 vix_live/vix_live_as_of），18:00 晚报用官方 CSV 复核清零；11/25 现货金深 V 后 NY 17:00 EST 官收 $3,588.78 未过周二高点 $3,678.15（第 4 关未过，且较主报告基线 $3,635.24 仅 -1.28% < 3%，主报告 0/5 保持锁定）；直查 SSGA 官方 .xlsx 纠偏 11/24 GLD 持仓为 1,027.31t (-3.99t)，三源锁定 11/25 GLD $327.45 驳回 StockAnalysis 滞后 $325.70。",
  "sources": {
    "real_yield": [
      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv"
    ],
    "rate_spread": [
      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv",
      "https://markets.newyorkfed.org/api/rates/all/latest.json"
    ],
    "vix": [
      "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
      "https://www.cboe.com/tradable_products/vix/"
    ],
    "ny_close": [
      "https://www.investing.com/currencies/xau-usd-historical-data",
      "https://www.morningstar.com/news/dow-jones/202611256404/comex-gold-settles-071-lower-at-353470-data-talk"
    ]
  },
  "forecast_review": {
    "status": "settled",
    "note": "按事先锁定标准客观结案 11/25 07:30 两项到期追踪：① 美英数据三情景预案因核心 PCE 环比 +0.3%/同比 +3.3% 且 GDP +4.3% 属混合触发、盘中深探 $3,427.01 跌破情景二下沿 $3,520 后尾盘收 $3,588.78，严格判为“部分兑现”（不事后归入有利情景）；② 主报告 -3% 官收触发线（$3,526）因 NY 官收拉回 $3,588.78（-1.28%）未触发，诚实单列为“条件未触发”不计入胜率分母。",
    "sources": [
      "https://www.investing.com/currencies/xau-usd-historical-data",
      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv",
      "https://www.cboe.com/tradable_products/vix/"
    ]
  }
} -->

## 2026-11-26 08:30 早报增量红队法证档案（累计 78 项：34 拦谣 / 16 升级 / 28 校准，核心影响 0 / 28）

- **新增拦谣 #34（累计 34 项）**：海外论坛与社媒流传“Tether 稳定币或中国央行暗中抛售黄金砸穿 3,500 美元”——经核查外管局/央行 10 月官报确认中国连续 24 个月增持至 2,435.4 吨零抛售，链上 `PAXG`（`$3,566.74`）/ `XAUT`（`$3,568.35`）折价仅 `-0.22%` 至 `-0.25%` 零脱锚且 Q3 BDO 鉴证 Tether 持金反增至 168.54 吨；已证实官方净卖仅俄罗斯 Q3 约 18.66 吨与哈萨克斯坦表态。
- **新增系统升级 #16（累计 16 项）**：落地 `gold/edition_validation.py` 与双班次共享提示词的 Cboe `VIX_History.csv` 批处理滞后非阻塞 `provisional_close` / `pending` 校验及全数据缺口透明汇报机制，彻底消除冬夏令时 07:30 早报撞上 Cboe `~10:11 CST` 批处理延时的硬阻塞，并强制 18:00 晚报核对官方 CSV 终值。
- **新增细节校准 #26–#28（累计 28 项，对核心买金结论影响 0 / 28）**：
  - **#26**：直查 SSGA 官方 `.xlsx`（`https://www.ssga.com/us/en/intermediary/etfs/library-content/products/fund-data/etfs/us/navhist-us-en-gld.xlsx`）与 SPDR 官方历史档案，确认 11/24 `GLD` 份额由 `361.8M` 降至 **`360.4M`**、实物持仓实为 **`1,027.31 吨（-3.99 吨）`**，纠偏上期快照与第三方站点滞后 `1,031.30 吨 / 0.00 吨` 假象。
  - **#27**：Investing UK / Yahoo Finance / 腾讯美股三源一致锁定 11/25 `GLD` 官收 **`$327.45 (+0.61%)`**，拦截 StockAnalysis 滞后 `3:39 PM EST` 盘中快照 `$325.70`；同时确认 `NEM` 于 11/25 除息 `$0.260`（复权 `+2.02%` / 原始 `+1.76%` 收 `$101.44`）。
  - **#28**：直查美联储官网日历（`https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`）明确 12 月 FOMC 会议美东日期为 **`12/08–09`（北京 `12/10 03:00` 公布决议）**；同时核实 `cboe.com/tradable_products/vix/` 不含日内高低 `34.95 / 27.49`，禁止将第三方摘要数字归属为 Cboe 官网官方数据。
- **2026-11-26 08:30 一手直采核心链接与待晚报补核清单**：
  - 直采一手源：[UST Real Yield CSV](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_real_yield_curve&field_tdr_date_value=2026&page&_format=csv) · [UST Nominal CSV](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv) · [NY Fed Rates](https://markets.newyorkfed.org/api/rates/all/latest.json) · [NY Fed ON RRP](https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json?startDate=2026-11-20) · [Cboe VIX Product Page](https://www.cboe.com/tradable_products/vix/) · [Cboe VIX CSV](https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv) · [SSGA GLD History](https://www.ssga.com/us/en/intermediary/etfs/library-content/products/fund-data/etfs/us/navhist-us-en-gld.xlsx) · [COMEX Gold Settle](https://www.morningstar.com/news/dow-jones/202611256404/comex-gold-settles-071-lower-at-353470-data-talk) · [COMEX Copper Settle](https://www.morningstar.com/news/dow-jones/202611256406/comex-copper-settles-056-lower-at-53325-data-talk) · [EIA WPSR](https://ir.eia.gov/wpsr/table1.csv) · [Fed Calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)。
  - 待 `2026-11-26_1800` 晚报补核项：① Cboe `VIX_History.csv` `11/25` 完整 OHLC 行；② SPDR `GLD` `11/25` 持仓吨数；③ VanEck `GDX` `11/25` 官方 NAV；④ LBMA `11/25` AM/PM 金银定盘价；⑤ FRED `11/24–25` `HY/CCC OAS`；⑥ `11/26 09:00–10:00` 国内银行金条/品牌金店最新牌价与 `09:15` CFETS 汇率中间价。

---

## 2026-11-26 黄金晚刊与主报告勘误来源

- **波动与交易时点**：[Cboe 现货指数日线](https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv) 覆盖 11/11–11/24 十个完整交易日。11/20 同时是收盘峰值 35.89 和盘中高点 40.03；11/24 数据为收盘 26.36、日高 32.38。复算的 30.99 引用原刊 11/25 21:20 盘前观测，分钟原档待补。观察时点晚于当日 19:59 金价破位，不据此判断其原因。[Cboe 指数与期货规格](https://www.cboe.com/tradable_products/vix/vix_futures/specifications)
- **利率与期货**：[美国财政部实际收益率](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?field_tdr_date_value_month=202611&type=daily_treasury_real_yield_curve) 的 11/23、11/24 十年值同为 2.79%。[FRED 盈亏平衡通胀](https://fred.stlouisfed.org/series/T10YIE) 的 11/24 日期值为 2.12%。[CME 26-389 公告](https://www.cmegroup.com/content/dam/cmegroup/notices/clearing/2026/11/chadv26-389-1.pdf) 确认保证金新标准于 11/24 美国业务结束后生效。
- **研究证据**：主报告原刊公布的双因子样本内决定系数、回测及六家均价中位缺完整复算材料。勘误明确区分年末点位与 6–12 月目标，仅汇总可从仓库辨认的样本。公开记分卡纠正了两项过于宽松的评分。

## 2026-11-25 100% 单仓库收敛工程架构升级留痕（统一技能库、脱敏定时模板与旧目录清零）

- **全量技能与定时配置单仓收敛**：合并全部 3 套工作区 Skill 至根目录 `.agents/skills/`（零个人绝对路径 PII），新增脱敏模板 `automations/sidecars/*.template.json` 与原子安装/漂移校验脚本 `scripts/install_sidecars.py`，同步将 `.agents` 与 `automations` 纳入 `scripts/publish_site.py` 标准暂存清单。
- **外部副本与遗留目录清零**：经时间戳逐项核验无新增缺失文件后，彻底移除本机重复全局 Skill 与旧 `scratch/` 遗留目录，实现 100% 单仓库单一真相源收敛。

---

## 2026-11-25 单仓库一体化工程架构升级留痕（4→2 统一调度、共享 6+1 与顺序发布）

- **4→2 统一 `07:30`/`18:00` 定时调度**：彻底合并历史 4 套拆分定时任务（原黄金 07:30/18:00 与权益 07:55/18:25 错峰任务），收敛为 `daily-global-investment-research`（`07:30 CST`）与 `daily-global-investment-research-evening`（`18:00 CST`）2 个单会话一体化任务，由仓库顶层 `<REPO_ROOT>/AGENTS.md` 统一编排。
- **共享 6+1 跨轨调研与顺序串行发布**：单会话内按 `Step 0 → Step 1 → Step 2A（共享 6 路并发调研）→ Step 2B（1 路统一发前红队）→ Step 3（黄金 SSOT 先行落盘、编译与 7 门禁严检）→ Step 4（三地权益零延迟只读消费最新 gold/data_snapshot.json、串行编译与全量严检，杜绝 Chrome 并发）→ Step 5（1 路统一盲审 RSI 闭环 + 双轨复检全绿后单次运行 scripts/publish_site.py 发布静态门户与增量 Release）` 执行。
- **历史退役目录与契约清理**：物理删除已退役的历史合刊遗留目录 `equity/archive/legacy_combined/`，并同步收口跨轨日历（`market_calendar.json` 2026-12-28 仅 UK 补休、2027 春节港股口径）、内部工具词跨四脚本全量同步门禁及双轨 RSI 台账一致性。

---

## 一、三大信任资产全景汇总（累计 73 项红队审计记录 · 截至 2026-11-25 21:25 BJT）

> **最新累计同步提示（截至 2026-11-26 08:30 BJT）**：为遵循账本历史行不可删改审计铁律，上方及下列既有小节标题按原样留存；最新累计红队审计记录已增至 **78 项（34 拦谣 / 16 升级 / 28 校准，核心影响 0 / 28）**，新增明细 `#34`、`#16`、`#26–#28` 已追加于对应表格与列表末尾，最新 8 大类官方原始库索引见下方最新同步小节。
>
> **最新累计同步提示（截至 2026-11-26 18:30 BJT）**：累计红队审计记录增至 **82 项（35 拦谣 / 17 升级 / 30 校准，核心影响 0 / 30）**，新增明细 `#35`、`#17`、`#29–#30` 已追加于对应表格与列表末尾，最新 8 大类官方原始库索引见下方 `2026-11-26 18:30` 小节。
>
> **最新累计同步提示（截至 2026-11-28 12:00 BJT）**：累计红队审计记录已增至 **116 项（51 拦谣 / 18 升级 / 47 校准，核心影响 0 / 47）**，新增明细 `#36–#51`、`#18`、`#31–#47` 已严格按不可删改铁律完整追加于对应表格与列表末尾，最新 8 大类官方原始库索引见下方 `2026-11-28 12:00` 小节。

### 🛡️ 资产一：帮普通投资者拦下的 33 个全网流行误区、谣言与买金深坑

| 编号 | 流行误区 / 谣言 / 深坑 | 原始官方库核查真相 |
| :---: | :--- | :--- |
| **1** | “CME 突然紧急大幅上调保证金砸崩周五金价” | **11/20（周五）暴跌及截至 11/23 早盘** CME 确未发任何提保令（真实卖压来自美股追保与 Anthropic IPO 抽血，上金所 11/23 仅为常规风控提示）；**【时间线演进更新 · 11/25 核实】**随后 CME 于 **11/23（周一）盘后**按波动率复核正式发布 **`Clearing Advisory 26-389`**，自 **11/24 美盘收盘后生效**，将期金保证金由 `5% → 6%`（HRP `5.5%→6.6%`，+20% 现金）、期银由 `8% → 9%`，成为 11/24 午后二次跌破 `$3,600` 的真实机械推手（非此前网传“暴提至 40% 恶意狙击”）。 |
| **2** | “中国与全球央行秘密大抛黄金导致暴跌” | WGC 确认 Q3 全球央行净购金 **321.2 吨**（前三季 675.2 吨，+6%），中国央行 10 月买 25.8 吨连增 24 月至 2,435.4 吨；仅俄、哈局部净卖。 |
| **3** | “深圳水贝市场遭政策性大面积封杀/冻结交易” | 11/22–23 水贝客流创近数月新高；所谓冻卡系反电诈“断卡行动”下个别商户误收涉诈资金的依法冻结个案，非行业封杀。 |
| **4** | “霍尔木兹海峡即将全面重开、美伊达成协议” | 美方仍维持海上反封锁，海峡商业航运仍低战前 ~65%，预测市场定价年底复航仅 3.6%–4.5%。 |
| **5** | “美联储召开秘密紧急会议或 12 月暴力加息 50bp” | 无任何紧急会议；纽约联储 Williams 11/23 明确排除“戏剧性（50bp）”激进举措，主流稳锁 +25bp。 |
| **6** | “Tether 暴雷强平 XAUt 黄金代币砸盘” | 无任何审计或链上证据；Q3 BDO 鉴证整个 Tether 生态持金反净增 +0.33 吨至 **168.54 吨**。 |
| **7** | “美国将发生 90 天全国大停电（借此兜售末日金条）” | Snopes 与《华盛顿时报》正式辟谣，系 AI 深伪视频拼凑联邦应急警报测试画面。 |
| **8** | “关税引发美国滞胀推高商品通胀” | 美国最高法院 2026/02/20 判 IEEPA 紧急关税违宪 + 7/24 第 122 条款到期，实际有效关税腰斩至 **7.2%**，核心商品 CPI 仅 +0.7%。 |
| **9** | “40 万亿美债半年内压垮美联储迫使其立刻降息” | 存量美债平均久期 5–6 年，存量均息仅 ~3.5%–3.6%，真正的滚续大考在 2027 下半年–2028 年。 |
| **10** | “美联储 12 月是本轮首次加息” | 美联储主席沃什早在 2026 年 9 月 16 日已首次加息。 |
| **11** | “只有美联储在加息” | 2026 年 12 月 9–18 日美、欧、英、日四大央行罕见在 10 天内同步定价加息（76%–95%）。 |
| **12** | “明年 1 月大宗商品指数调仓会抛售黄金” | 恰好相反！因 2026 年原油大涨挤占权重，2027 年 1 月 8–15 日 BCOM 与 GSCI 将反向**强制净买入 33–48 亿美元黄金与 25 亿美元白银**。 |
| **13** | “矿企大规模远期套保将重演 1999 年 20 年大熊市” | 全球矿企套保残余连降 11 季仅剩 **92 吨**（仅为 1999 年的 3%），无套保砸盘基础。 |
| **14** | “印度和中国险资会在下跌中无条件托底买金” | 印度 5 月已将黄金关税由 6% 暴提至 15%（4–10 月进口额 -39.9%）；中国险资受 IFRS 9 季度损益约束只做右侧稳健吸筹。 |
| **15** | “深圳水贝直购投资金条比银行更省钱” | 未获进项抵扣的场外/非会员零售投资金条须承担 13% 增值税转嫁（买进即亏 ~13%）；含税零售首饰亦含 7% 增值税净差 + 5% 零售消费税与工费；国有四大行作为交易所会员享即征即退，溢价仅 ~2.5%–3.1%，且原塑封+证书+发票可回原行指定网点扣 2–4 元/克回购。 |
| **16** | “巴塞尔 III 将黄金列为顶级流动资产（HQLA） / 金砖推 40% 黄金货币” | 巴塞尔 III 至今未将黄金列为 HQLA；金砖亦无 40% 黄金锚定统一货币落地。 |
| **17** | “湖南万古特大金矿将砸垮全球金价” | 已探获储量 300.2 吨，折合年产不足全球供给 0.9%，对国际定价无实质冲击。 |
| **18** | “美国战略比特币储备将分流全球央行购金资金” | 美国 ARMA 法案已删除全部公开市场买入条款（0 美元主权公开买入），全球央行增配储备仍 100% 独属实物黄金。 |
| **19** | “COMEX 9 月库存掉 125 吨是实物挤兑” | 系 `4GC` 合约下架导致的统计口径剔除；当前 `GCG27−GCZ26` 正价差 +29.50 美元，实物配管完好。 |
| **20** | “老铺黄金与山东黄金跌深必大弹可盲目抄底” | 山东黄金前三季自产金降 30.6% 致 Q3 上市来首亏 -3.63 亿；花旗 11/23 二次砍老铺黄金目标价至 HK$310（下调 2026–28 净利预测 7%/22%/22%，下修后料 2027E 净利 31.1 亿较 2026E 55.4 亿同比 -44%）。 |
| **21** | “工行、建行、招行因金价剧震紧急暂停/叫停积存金业务” | 11/20–24 各大行仅发布例行贵金属波动风险提示，买卖、定投、赎回与提金均正常运作；工行主动积存买入 0 费率限时优惠仍持续至 11/28（赎回仍收 0.50%）。 |
| **22** | “日本国债今日（11/24）节后复牌崩盘、引爆抛售黄金潮” | 搬运年初旧闻博流量。11/24 日债节后复牌受国际油价走低带动大涨，10Y 日债收益率反降 7–9bp 至 **2.695%–2.715%**、2Y 降至 1.80%，与崩盘完全相反。 |
| **23** | “黄金避险永久失效、年底直接腰斩跌破 3,000 美元” | 本轮回调源于全球加息预期重定价与跨资产追保抽血，央行购金底逻辑未破；真金白银预测市场 Polymarket 给年底跌破 $3,000 定价仅约 **7%**。 |
| **24** | “深圳水贝又有十几家料商集体跑路、券商两融强制提保平仓” | 水贝跑路系拿年初违规预定价旧案翻炒，合规档口 11/24 正常营业；两融新规实为允许券商弹性沟通担保比例缓和强平，被小作文反向曲解。 |
| **25** | “周大福 FY27 中报净利暴增 98.7% + 门店破 1,103 元 = 抢金暴利、金价将大涨” | 港交所原始中报显示周大福毛利率骤降 4.9pct 至 25.6%、核心经营溢利反跌 **-18.2%**、内地净关店 498 家、对冲率由 55.4% 降至 39.0%；净利翻倍纯属 4–9 月金价下跌令黄金借贷空头重估由去年亏 31.43 亿反转为赚 13.36 亿（+44.79 亿港元会计差额），因果完全倒置。 |
| **26** | “WTI 跌破 80 美元 = 美伊秘密停火、霍尔木兹马上复航并触发深熊红线” | 跌破 $80 的是美国原油 WTI（$79.39–$79.97），国际基准布伦特原油仍在 **$88.89–$89.30**；伊朗议长提七项先决条件致谈判僵局，Polymarket 定价海峡年底复航仅 **3.5%–5%**（解除封锁 18.8%），深熊红线条件 0/2 满足。 |
| **27** | “沪金收红但金矿股大跌 4%–5%，说明外资提前拿到今晚 5Y 拍卖/明晚 PCE 内幕砸盘” | 明晨 02:00 5Y 拍卖与明晚 21:30 PCE 均未发生（警惕财经聚合站将上月 5Y 拍卖 4.708% 误标为今晚结果）；沪金近月 `au2612` 减仓 7,703 手/净流出 10.15 亿元实为临近交割换月与空头平仓，叠加资金撤出矿股切回科技板块。 |
| **28** | “摩根大通/汇丰落地伦敦数字黄金 PGI = 巴塞尔 III 批准黄金为 HQLA 顶级流动资产” | WGC（`gold.org`）与 LBMA 官方文件证实，11/24 落地的是伦敦批发市场民间电子金条抵押试点（Pooled Gold Interests，由 IBA 运营、Baton Systems 提供技术）；巴塞尔委员会（BCBS）至今未将实物黄金或 PGI 批准为 LCR 下 HQLA，NSFR 仍执行 85% 稳定资金系数。 |
| **29** | “美国连夜对中欧等 16 国生效惩罚性关税，推翻最高法院 2 月违宪判决” | USTR、WSJ 与 Reuters 11/24 证实，贸易代表推进的是 2026 年 3 月依据《1974 年贸易法》301 条款立案的“工业产能过剩”调查拟议建议（法定结案期至 2027 年 3 月），具体税率、商品清单、听证期与生效日均未落地，亦未推翻最高法院对 IEEPA 关税的裁决。 |
| **30** | “白宫已下令对伊朗高层实施定点斩首打击，中东全面大战一触即发” | 溯源 NBC News 11/24 原稿，仅系白宫幕僚内部讨论选项，美军及高层反对强烈、总统尚未作出任何决定；真金白银预测市场虽将年底解除封锁赔率调降至 12%–14%，但“14 天无空袭”赔率仍居 81.5%–82.5%。 |
| **31** | “菜百断货等于全球实物逼空 / PBOC 缩量 MLF 等于停买金 / 感恩节推迟 PCE 且 COMEX 全天休市” | 三处全误：① 菜百系周末散户集中抢购小克重导致的零售柜台补货瓶颈，而 COMEX 注册库存仍高达 1,430 万盎司（63%）且无现货挤仓；② PBOC 11/25 缩量续作 8,000 亿 MLF 同时投放 5,000 亿 7D 逆回购 + 6,170 亿隔夜逆回购，全口径净投放 **+3,210 亿**非收紧；③ 今晚 21:30 美国核心 PCE 准时发布，明日感恩节 CME 电子盘仅于周五 03:30–07:00 停盘 3.5 小时。 |
| **32** | “CME 提保至 6% 是在恶意砸盘掩盖 COMEX 金库实物违约逼空” | 核查 `cmegroup.com` 清算公告 **`#26-389`**，本次将黄金保证金从 5% 调至 6%、白银从 8% 调至 9% 系按 2026 年名义价值比例框架执行的常规高波动风控复核，双向适用于多空双方；COMEX 注册库存仍高居 1,430 万盎司（63%），上金所 11/23 亦仅为常规波动提示，无实物违约迹象。 |
| **33** | “中国央行秘密抛金、大行叫停实物金条，且周大福跌到 1,068 元已属原料抄底价” | 外汇局与央行 11/07 官方储备数据证实截至 10 月末中国黄金储备连增 24 月至 **7,830 万盎司（2,435.4 吨，单月增 +25.8 吨）**，零抛售；大行仅提示杠杆/延期交易风险，11/25 四大行实物金条正常销售且均价随大盘降至 **778.16 元/克**；品牌金饰虽破千一至 1,062–1,068 元，对比上金所 `Au99.99` 官收 757.35 元仍带 **+41%（~311 元/克）** 零售溢价，只适合婚庆佩戴不适合投资。 |
| **34** | “Tether 稳定币或中国央行暗中抛售黄金砸穿 3,500 美元（11/26 08:30 新增）” | 外汇局与央行 10 月官报证实中国连续 24 个月增持至 2,435.4 吨零抛售；链上 `PAXG`（`$3,566.74`）/ `XAUT`（`$3,568.35`）折价仅 `-0.22%` 至 `-0.25%` 零脱锚且 Q3 BDO 鉴证 Tether 持金反增至 168.54 吨；已证实官方净卖仅俄罗斯 Q3 约 18.66 吨与哈萨克斯坦表态。 |
| **35** | “伊朗超级油轮 Khat Shekan 突破封锁驶离霍尔木兹海峡、海峡即将松动（11/26 18:30 新增）” | 海事情报机构（TankerTrackers）与卫星影像证实完全系虚假 AIS 信号欺骗（拼凑无关利比里亚油轮呼号，卫星零轨迹）；海峡周度油轮通行量仍降逾 40%，预测市场定价年底前恢复正常航运仅 1%–4%。 |
| **36** | “518880 今日主力大举净流入 +3.54 亿元，机构已右侧抄底（11/26 23:55 新增）” | 上交所 11/26 官方 ETF 份额表证实系二级市场盘口大单误导，一级市场实际净赎回 `-2,560 万份`（`-1.86 亿元`，连流 10 日），连同 `159937`（`-1.25 亿`）与 `518660`（`-0.31 亿`）合计净赎回 `-3.42 亿元`。 |
| **37** | “沪银夜盘暴涨 +3.66%、沪金拉涨 +1.41% 假期逼空（11/26 23:55 新增）” | 上期所 `kx20261126.dat` 核实源于昨夜低位巨量拉低官方结算价（`au2702 756.32`、`ag2702 9,332`），23:55 沪金 `767.02` 较 15:00 收盘微跌 `-0.08%`，同刻溢价仅 `+2.43 元/克`。 |
| **38** | “布油突发暴跌 5% 跌回 91.6 美元，中东冲突缓和（11/27 07:55 新增）” | 11/26 ICE 布油 1 月近月合约（`BRNF27`）官结大涨 `+2.07%` 至 `$96.57/桶`，终端 `$91.58–$91.75` 系自动换月至 2 月次月合约（`BRNG27`）因现货升水产生的 ~$5 展期落差。 |
| **39** | “伦敦金基金 `IGLN.L` 暴涨 +3.34% 或 2 月期金破 $3,592 已提前过第 4 关（11/27 07:55 新增）” | `IGLN.L` `$69.24 (+3.34%)` 系补涨 11/25 伦敦收盘后美盘深 V（两日净变仅 `+0.09%`），`GCG27` 含高利率持仓升水 ~$25，现货金仍压在 `$3,589.85` 下方，买金维持红灯停。 |
| **40** | “现货金亚盘盘中破 $3,630 已提前闯过第 4 关（11/27 12:28 新增）” | 四步红绿灯第 4 关严格以纽约 17:00 官方日线收盘为准，亚盘盘中脉冲不作数且前两关美债实际利率与加息利差未松动。 |
| **41** | “沪银飙涨 10.75% 已填平国投白银 161226 场内溢价（11/27 12:28 新增）” | 实测 `161226` 午间实时溢价仍约 +9%（日终反扩至 +14.96%），且入围最晚 2027-12-31 强制退市 LOF 名单，严禁追高。 |
| **42** | “四大行投资金条半日跳涨 12.8 元系银行缺金断货恐慌（11/27 12:28 新增）” | 仅系银行跟随上金所午盘料价正常挂钩调价（均价 795.87 元/克），与缺金或实物挤兑无关。 |
| **43** | “欧盘冲 $3,671 已转黄灯、161226 溢价归零（11/27 18:30 新增）” | 欧盘盘中价非纽约官收，前两关利率双卡维持红灯停；按 `ag2702` 官结 9,971 估值 `161226` 真实溢价仍约 +14.9%。 |
| **44** | “银行投资金条紧缺断货需抓紧抢购（11/27 18:30 新增）” | 国有四大行标准金条常规渠道均正常报价销售，所谓断货系个别零售柜台小克重补货节奏误传。 |
| **45** | “欧盘破 $3,685 证明高美债利率已拦不住金价启动（11/27 23:55 新增）” | 美盘油价倒跌却推升 10Y 实际利率至 2.783%，现货金倒吐 61.77 美元且沪市 4 只金基单日净赎回 -3.25 亿元。 |
| **46** | “`Au(T+D)` 大涨代表国内现货实物逼空（11/27 23:55 新增）” | 上金所官方表证实 `Au(T+D)` 递延费已由空付多翻回多付空、15:30 仅微溢 +0.83 元且夜盘自 786.60 回吐至 778.03。 |
| **47** | “纽约金站稳 $3,652 闯过第 4 关升至 2/4 关已亮黄灯可买（11/28 07:55 新增）” | 买金须四关全过才可转黄；11/27 美国财政部官曲 10 年实际利率跳至 2.79%（超线 7bp）与 2 年利差 +81bp（超线 26bp）牢牢锁死前两关，严格维持红灯停新仓 0%。 |
| **48** | “纽约联储黑五常备回购激增 231.5 亿美元等于重启放水（11/28 07:55 新增）” | 常备回购（SRF）为 4.00% 惩罚性隔夜抵押融资窗口（全部集中 08:15 早场、13:30 午场归零且周一到期），反映银行准备金跌破 2.98 万亿后的短端资金偏紧而非量化宽松。 |
| **49** | “工行主动积存金 0 买入费今日到期，明起恢复 0.5% 须赶紧上车（11/28 12:00 新增）” | 工行官网已发布衔接公告，将个人主动积存 0 买入费优惠自 11 月 29 日起无缝顺延至 2027-03-31（定投延至 2027-12-31，赎回仍收 0.50%）；红灯期切勿借促销焦虑抢买。 |
| **50** | “品牌金店周六涨 25 元且水贝人挤人，周一国内金价将跳空逼空（11/28 12:00 新增）” | 品牌金店周六跳至 1,093 元系滞后补涨周五料价；周六午间 7×24 链上只读锚 XAUT 报 $3,649.55 对应平价约 781.3 元，与周六 02:30 上金夜盘 782.00 元几乎零缺口。 |
| **51** | “行情端布油跌破 91 美元等于通胀警报解除、黄金马上转黄灯（11/28 12:00 新增）” | 系布伦特 1 月合约（$95.44）11/30 到期切换至 2 月合约（$90.84）产生的 $4.60 天然换月贴水视觉陷阱，高油价警报未除且油价大跌反而可能推高实际利率。 |

*(注：另核实一条**非谣言**的链上与监管动态——WSJ 与 Bubblemaps 证实 16 个新注资 Polymarket 关联钱包在黄仁勋复职前数小时以 1.5%–3% 低赔率净赚 34–35 万美元，截至 11/24 午后尚无 CFTC/SEC 正式立案通报；但 SEC 已就英伟达自身信息披露与管理层沟通启动民事调查。)*

---

### 🧭 资产二：提升准确度与风控能力的 15 次核心模型与出版架构升级

1. **淘汰滞后旧铁律，升级“买金四步红绿灯（Tier 0/1/2/3）”**：日频回测暴露旧铁律 ① 在 2008–09 大牛市竟 0 次触发（踏空 266 天）且重复计分 VIX；新体系历史 6 次大底 6/6 有效、2022 上半年 0 误报，将入场中位滞后从 +70 天缩至 Tier 1 +9 天 / Tier 2 +30 天，配 60 日实际利率新高机械砍半硬止损。
2. **揭示“恐慌提款机”阶段双轨律**：核查 53 个 `VIX≥30 & 2Y−FF>+40bp` 历史交易日，推翻“必亏”一刀切结论，精准拆分为早中期加息期 64.2% 承压 vs 尾段冲击期 35.8% 大涨（2015.08 与 2022.09–10）。
3. **建立 2026 下半年“实际利率 + 美元”双因子强复耦模型（`R²=0.830`）**：测算美元弹性高达 `-4.59×`，11/23 实时测算公允值 `~$3,690` 与周一实际阻力 `$3,689.94` 高度吻合。
4. **修正三四阶段人民币金价的汇率虚高偏差**：改用人民币 `6.20–6.45` 联动换算，主动替国内读者挤出 `55–75 元/克` 的静态汇率虚高水分。
5. **补齐“18% 尾部深熊（$2,450–$2,850）”三大雷管**：油价大跌反推高实际利率（11/23 布油破 90 首次预演）、波兰 10 月达 700 吨目标停买悬崖 + `IMF Note 2026/007` 风险折价、美国 Q3 +3.6% AI 生产率。
6. **精确复算动态均线与 4 重共振熊底**：实算 200 周均线 `$3,040–$3,063`（中值约 `$3,052`，每周抬升 `+$7`，2027 Q1 升至 `$3,136`），放宽第一阶段区间至 `$3,250–$3,850`。
7. **严格配平四象限情景概率树**：修正为 `40% + 30% + 18% + 12% = 100%`。
8. **彻底重构全球 12 大投行 2027 目标价（图 6）**：严格区分“27 年末点位中位 `$5,000`”与“27 全年均价中位 `$4,719`”，剔除幻影伯恩斯坦换入法国兴业银行（Q4 27 `$5,000` / 均价 `$4,625`），修正摩根大通 7 月终修目标 `$5,000` 与花旗 6–12m 基准 `$5,000`。
9. **补齐 CME 百分比保证金与 GLD 负 Gamma 衍生品风控模块**：识别 2026 年 1 月 CME 改用 5% 百分比维持保证金后的薄量追保风险。
10. **精确校准近两年全球黄金 ETF 净持仓成本**：精算近两年净增 1,046.5 吨成本为 `$3,624`（非粗估 `$3,672`）。
11. **精准定位国内内盘抛压来源**：证伪 `au2612` 多头平砍误读，锁定机构在 `au2702` 净增空单及 `518880` vs `159937` 申赎分化。
12. **V7.0 体系瘦身与唯一数据源工程化**：建立 `data_snapshot.json` 与 `lint_readability.py`，统一废除正文 `六灯 X.X/6` 平行分制，彻底终结手工打补丁引发的跨节数字冲突。
13. **V2.2 / V7.2 全栈法证架构升级**：建立主报告独立快照 `master_snapshot.json` 与 `<!-- MASTER_BASELINE -->` 原子基线锁（根除跨日 `--strict` 死锁与主报告图数撕裂）；重塑 `docx_embed.py`（`settings.xml` 自动刷新页码、严格 ECMA-376 元素顺序、保留彩色矢量点与动态封面色）、`build_daily.py`（共享嵌套列表解析器、跨资产主角精准高亮、Chrome 超时护栏）、`build_report.py`（冻结历史案例图 3、顺排图 1–图 7、跨年蜡烛图支持）及 `lint_readability.py` 全覆盖校验。
14. **07:30 早报 + 18:00 晚报双定时调度与三层安全 RSI 递归自优化闭环**：拆分为两套独立定时任务精准覆盖隔夜美欧与日终清算/龙虎榜/欧洲数据窗口，并建立 `daily/RSI_PLAYBOOK.md`（≤180 行防膨胀门禁）+ `daily/rsi_metrics.json`（每刊独立盲审 6 维定量打分 + 上期预判回验）+ Tier A/B/C 分级安全自进化与强制回滚机制。
15. **2026-11-25 全栈治理与跨项目协同升级（Tier C #2 落地 + 外置日历 + 手机端 HTML + 公开记分卡 + 跨项目 SSOT）**：获用户审批正式结案 Tier C 提案 #2（官收白名单 `StockAnalysis`/`Investing`/`VanEck NAV`、禁用 `Barchart` 远月、`site:shfe.com.cn`/`site:lbma.org.uk` 定向补录与北美冬/夏令时硬校验）；新建 60+ 天跨市场外置日历 `market_calendar.json` 与面向读者零工程词的公开预测记分卡 `daily/SCORECARD.md`；在 `build_daily.py` 移植原子生成的响应式单文件手机端 HTML（`daily/latest_gold.html`）；在 `lint_readability.py` 加固外置日历、公开记分卡、手机端 HTML 及 SSOT `new_buy_allowed` 强校验；全量修复 68 禁词 / 四轨矩阵 / 排障节号 / Step 5 Tier B 文档滞后项，并确立黄金项目 `07:30`/`18:00` 先跑的跨项目 SSOT 唯一写入权与无人值守禁 `edit_file` / 惰性主报告加载 / 同场 `_r2` 防覆写护栏。（*注：`trust_assets.model_upgrades` 将于 2026-11-25 18:00 晚报同步由 14 刷新至 15。*）
16. **2026-11-26 非阻塞暂定官收与全缺口透明汇报升级（累计 16 项）**：获用户授权升级 `gold/edition_validation.py`、`gold/lint_readability.py`、`gold/AGENTS.md` 与双班次共享提示词，在 Cboe `VIX_History.csv` 07:30 批处理滞后时支持采信官方产品页 `16:15 EST` 官收标 `provisional_close` 或 `pending` 挂账、不阻塞早晚报准点刊发，并强制 18:00 晚报用官方 CSV 复核清零且在终报向用户逐项汇报全部未发布/暂不可取数据项。
17. **2026-11-26 18:00 收敛主刊架构与门户透明缺口系统全面落地（累计 17 项）**：正式启用 5–6 页收敛主刊、4 卡高密度 KPI 封面、理性知情三档词表（全篇零内部词与零说教口号）、`.sn-grid` 双栏防断句、图 1 胶囊 2D 防撞、图 2 动态刻度及 `data_caveats` 门户自动披露模块。
18. **2026-11-27 11:30 三时段一体化纯网页体系与多锚点精算升级（累计 18 项）**：新增每日 `11:30 CST` 一体化午报班次（精准锚定 11:30 上金/沪金早盘官收与同刻平价溢价），同步落地 `index_matrix` 多指数多锚点同步、480+ 交互 K 线静态分片与 `DAILY_VISUAL` 矢量信息图零碰撞体系。

---

### 🔍 资产三：公开透明的 25 项细节校准（对核心价格区间与买金建议的影响：**0 / 25**）

| 编号 | 原稿细节偏差 | 核验后的准确口径 | 是否改变核心买金结论 |
| :---: | :--- | :--- | :---: |
| **1** | V6.0 勘误 #31 误称 Daniel Ghali 属道明证券/非德银 | **Daniel Ghali 已于 2026 年 5 月自 TD 加盟德银任金属研究主管**；德银 25.11 `$5,150` 旧稿确由 Michael Hsueh 执笔（Hsueh 年中亦更新 Q4 26 至 `$4,800`）；麦格理 Marcus Garvey 已离职。 | **否 (0)** |
| **2** | V6.0 称周一上市 5 只 Anthropic 杠杆 ETF | 周一实盘上市约 **14 只 2X `ANT` 杠杆 ETF**。 | **否 (0)** |
| **3** | 原日历列“周一 22:30 欧央行 Lane PMI 讲话” | Lane 周一系在都柏林发表气候金融演讲，非 PMI 货币政策演讲。 | **否 (0)** |
| **4** | 11/23 16:15 日志误校印度溢价回归平水；跨时区误算沪溢价 | Reuters 确认**印度金商溢价翻倍飙至最高 `+$17/oz`**（中国金商 `+$9–$13/oz`）；上金所 02:30 夜盘对照同期伦敦金真实溢价仅 **`+¥2.34/g`**。 | **否 (0)** |
| **5** | 11/24 调研阶段 COMEX 结算价出现 `$3,615.60` vs `$3,649.20` 分歧 | 采纳 Morningstar/Dow Jones 官方 13:30 EST 近月 `GCX26 $3,649.20 (+3.90%)`（`$3,615.60` 系盘中旧快照）；NY 17:00 尾盘 `$3,634.40`。 | **否 (0)** |
| **6** | 现货收盘涨幅与布油结算的跨源口径差异 | 统一采纳 NY 17:00 EST 可复算单一源现货收盘 **`$3,534.64 → $3,635.24 (+2.85%)`**（部分终端以前收 `$3,536.91` 报 `+2.78%`，全系统统一可复算口径），同步采纳 Reuters 14:30 EST 布油官结 **`$89.37`** / WTI **`$80.17`**。 | **否 (0)** |
| **7** | WGC 2026 Q2 生产商套保旧填 `-22.8t`、表 5.2 漏列 OTC 项及税改消费税漏项 | 终修 Q2 套保 `-18.6t`、补齐 WGC 表 5.2 场外交易与库存变动（OTC `+53 / +449 / +331 / +3 / +697t`）实现 5 列 0 吨误差配平；更新中国 9 月进口 129t、10 月 155.85t (+174%)；明确《财政部 税务总局公告2025年第11号》系 2025/10/29 两部委联合发布，且金银首饰零售环节另须计入 5% 消费税。 | **否 (0)** |
| **8** | 衍生指标换价未重算（M2 比、险资吨数）、表 6.1 算错及场外 C 类赎回误标 | 全面接入 `data_snapshot.json` 与 7 门禁 Linter：地上黄金/M2 按 `$3,635.24` 重算为 **`111.9%`**、险资 1% 额度按 `786` 重算为 **`299–305 吨`**、表 6.1 `6.30×$4,500` 更正为 **`911 元/克`**、美元夏普提升更正为 **`+9.8%`**、工银/华安/博时 C 类赎回费更正为 **`<7天 1.50%、7–29天 0.10%、满 30 天免`**。 | **否 (0)** |
| **9** | 索引 #6 记 11/23 美股地区银行 ETF `KRE $69.34 (+1.49%)`（尾盘瞬时价），及调研中出现 11/20 旧价 `$68.32` 串位 | YCharts 官收铁证确认 **11/23 `KRE` 收 `$69.53 (+1.77%, +$1.21)`**（`$68.32` 系 11/20 周五收盘）。 | **否 (0)** |
| **10** | 11/24 早报 BoE 12/17 加息概率 `85%–90%` 与老铺黄金花旗研报双维口径需并账 | Morningstar 11/24 实时校准 BoE 12/17 OIS 概率至 **约 `80%`（`76%–81%`）**；老铺黄金 11/24 官收 **`HK$272.60 (+2.17%)`**（驳回盘中 `279.00`），并明确花旗“2026–28 净利预测砍 7%/22%/22%”与“下修后 2027E 31.1 亿较 2026E 55.4 亿同比 -44%”同属一稿两维。 | **否 (0)** |
| **11** | 11/29 第 42 届 OPEC+ 会议成员口径易误含阿联酋 | 核实**阿联酋已于 2026 年 5 月 1 日正式退出 OPEC 及 OPEC+**，周日 11/29 核心自愿减产组为 **7 国**（沙特、俄、伊拉克、科威特、哈萨克斯坦、阿尔及利亚、阿曼）。 | **否 (0)** |
| **12** | 感恩节周 3 处关键发布/停盘时刻及德国数据日期校准 | ① 美国 $440 亿 7Y 国债拍卖提前 1.5 小时至 **周四 11/26 00:30 BJT**；② 本周 CFTC COT 推迟至 **下周二 12/01 04:30 BJT**；③ CME 贵金属周五 `03:30–07:00` 停盘、黑五周六 `03:45` 提前收；④ 德国 Q3 GDP 终值在明日 11/25 15:00，今日 17:00 为德国 11 月 Ifo。 | **否 (0)** |
| **13** | 11/24 午报初版拿 14:15 上海金基准（777.76）对比 16:30 伦敦盘（$3,625）得 `+1.00 元/克`；沪金夜盘涨幅误写 `+2.22%` | 严格同时间戳复算：14:15 伦敦现货 `$3,613.63` 折 `774.32 元/克` → 真实 14:15 同时间戳溢价为 **`+3.44 元/克（+0.44%）`**（15:30 `Au99.99` `780.40` vs `$3,622` 折 `776.12` = `+4.28 元/克`）；`au2702` 夜盘 `786.00 / 769.30 - 1` 实为 **`+2.17%`**。 | **否 (0)** |
| **14** | `data_snapshot.json` 误将 11/23 COMEX 铜盘中峰值 `$5.77 (+5.25%)` 记为结算价，致日内跌幅错标 `-2.40%` | 核实 11/23 COMEX 期铜官方结算价 **`$5.6270 (+2.74%)`**，11/24 亚欧盘 `$5.53` 较昨结实为 **`-1.72%`**（LME 3 月铜 `-2.0%` 至 `$12,233.50`）。 | **否 (0)** |
| **15** | 主报告 V7.1 表五将 `008142/008143` 合并简写为 `0.20%`、5.1 节年份笔误“去年 1 月/今年 1 月”及图序乱序 | 明示 **`008142`（0.20%/年运营 + 1折申购 0.06%）** vs **`008143`（含 0.35%/年销售服务费合计 0.55%/年 + 满 30 天免赎回）**，精确匹配 167 天盈亏平衡点；5.1 节更正为“今年（2026）1 月…明年（2027）1 月”；全书 7 图顺排 `图 1`–`图 7` 并同步升级至 **V7.2**。 | **否 (0)** |
| **16** | 11/24 午报用 `Au99.99` 延时参考 `780.40` 算出 15:30 溢价 `+4.28 元/克` | SGE 11/24 官方日终表确认为 **`Au99.99` 官收 `777.72 元/克 (-0.47%)`**（加权均价 `781.97`），对照 15:30 现货 `$3,622` 折 `776.12` 严格同时间戳溢价精准校准为 **`+1.60 元/克 (+0.21%)`**（`Au(T+D) 777.25` 为 `+1.13 元/克`）。 | **否 (0)** |
| **17** | 11/24 午报将日盘 `778.38 (+1.18%)` 与主力持仓变动归于 `au2702` | 双源实锤 `778.38 (+1.18%)` 及减仓 7,703 手/净流出 10.15 亿元属临交割近月 **`au2612`**；远月接力主力 **`au2702`** 11/24 官收 **`780.42 (+1.05%)`**。 | **否 (0)** |
| **18** | 11/24 午报日历将英央行行长 Bailey 等 4 位高层议会作证笼统标于“明日白盘” | 经 UK Parliament & BoE 官网核实，作证时间为 **伦敦 11/25 14:15 GMT = 北京明晚 22:15 BJT**，紧接明晚 21:30 美国核心 PCE 仅 45 分钟后。 | **否 (0)** |
| **19** | 11/24 快照记 11/23 `GDX` 官收 `$73.16 (+7.00%)`，调研中误将 11/24 开盘价 `$71.90` 作收盘 | Investing.com 与 VanEck 官方 NAV (`$72.73`) 双源证实 11/23 `GDX` 官收为 **`$72.80 (+6.43%)`**（`GDX/GLD 0.2186`）；11/24 `$71.90` 系开盘价，暂采 `$71.42 (-1.90%)` 并诚实标注待 VanEck NAV 终盘复核，严禁跨时点误读矿股抗跌。 | **否 (0)** |
| **20** | 11/24 晚报将今晚 21:30 美国 Q3 GDP 二次修正一致预期标为 `+3.6%` | 经 `bea.gov` 核实，10/29 公布的 Q3 GDP 初值实为 **`+3.4%`**，市场主流一致预期为 **`+3.4%–+3.5%`**（`+3.6%` 仅为个别机构如 Continuum Economics 预估上限）。 | **否 (0)** |
| **21** | 11/25 调研初稿误拿 11/23 `SGE Au(T+D)` 收盘价 `780.24` 算隔夜跌幅 `-1.67%` 并混入周大福旧价 `1,091` | 上金所官网证实 `780.24` 系 11/23 收盘价，11/24 官收为 **`777.25`** → 11/25 02:30 夜盘 `767.18` 真实跌幅精准校准为 **`-1.30% (-10.07 元)`**；同步确认 11/24 周大福有效挂牌为 **`1,103 元/克`**（驳回 11/23 旧价 `1,091`）。 | **否 (0)** |
| **22** | 11/25 调研出现 `GLD $328.13/$326.45` 跨源冲突及感恩节 CME 复盘冬令时误算 `06:00 BJT` | StockAnalysis / Investing / MarketBeat 三源锁定 11/24 `GLD` 官收 **`$325.45 (-2.27%)`**（驳回午盘中途价 `$328.13` 与非官收 `$326.45`）；按 CME 冬令时 `17:00 CST + 14h` 锁定周五 **`07:00 BJT`** 复盘（驳回夏令时误算 `06:00`），并同步衔接 `AUDIT_LOG #1` 中 `CME 26-389` 提保生效时间线。 | **否 (0)** |
| **23** | 11/25 早报暂记 11/24 `GDX` 收盘 `$71.42 (-1.90%)` | StockAnalysis / FinanceCharts / 腾讯美股三源一致锁定 11/24 `GDX` 官收 **`$71.37 (-1.96%)`**，VanEck 官方 NAV **`$71.50`**（`GDX/GLD 0.2193`），完成终盘校准。 | **否 (0)** |
| **24** | 11/25 部分早间渠道仍沿用 11/24 四大行金条 `801–803` 旧价、及个别行情源报老铺 `266.40` | 实时核验确认 11/25 四大行金条均价大跌 `-24.09` 至 **`778.16 元/克`**（工行 `779.25` / 农行 `778.00` / 建行 `777.90` / 中行 `777.48`）；港交所与腾讯直采锁定老铺黄金 11/25 官收 **`HK$265.40 (-2.64%)`**。 | **否 (0)** |
| **25** | 11/25 调研出现商务部暂缓禁令公告号（58号 vs 59号）及 CME 提保编号（26-389 vs 26-388/378）冲突 | 一手核实商务部 11/24 暂缓 2024 年 46 号公告第二款（镓锗锑超硬/石墨，11/28–2027/01/27）确为 **2026 年第 59 号公告**（58 号系 11/09 稀土/锂电公告）；CME 清算提保令官方编号确为 **`#26-389`**。 | **否 (0)** |
| **26** | 11/25 晚报与第三方站点沿用 11/24 SPDR `GLD` 持仓 `1,031.30 吨（0.00 吨持平）` | 直查 SSGA 官方 `.xlsx`（`navhist-us-en-gld.xlsx`）确认 11/24 `GLD` 份额实为 `360.4M`（减 1.4M）、实物持仓实为 **`1,027.31 吨（-3.99 吨）`**，彻底纠偏第三方持平滞后假象。 | **否 (0)** |
| **27** | 11/26 调研中 StockAnalysis 报 11/25 `GLD` 为 `$325.70`（系 3:39 PM EST 盘中旧快照）及 `NEM` 除息口径差异 | Investing UK / Yahoo Finance / 腾讯美股三源一致锁定 11/25 `GLD` 官收 **`$327.45 (+0.61%)`**；核实 `NEM` 于 11/25 除息 `$0.260`（复权 `+2.02%` / 原始 `+1.76%` 收 `$101.44`）。 | **否 (0)** |
| **28** | 12 月美联储会议美东日期偶见误标 12/09–10，且第三方站点将 VIX 日内高低 `34.95 / 27.49` 混归 Cboe 官网 | 直查美联储官网日历确认美东议息日为 **`12/08–09`（北京 `12/10 03:00` 决议）**；核查 `cboe.com/tradable_products/vix/` 仅披露 16:15 EST 官收 **`28.29 (+7.32%)`** 而不含日高/日低，禁止将第三方区间归属 Cboe 官方。 | **否 (0)** |
| **29** | 11/26 晚报调研初稿将盘中高点 `770.00` 混充 `SGE Au99.99` 日盘收盘，并警惕周大福 `939` 投资金条混充足金饰品价 | 跨源核定 11/26 15:30 `SGE Au99.99` 官收 **`765.82 元/克 (+1.12%)`**（与上海金午盘 `765.96`、`Au(T+D) 765.78`、`SHFE au2702 767.62` 闭环）；周大福足金饰品维持 **`1,068 元/克`**（`939` 系投资金条）。 | **否 (0)** |
| **30** | 11/26 港股老铺黄金（`06181.HK`）公开源出现 `254.0 / 264.40 / 272.60 / 274.80` 严重撕裂，含误用 11/24 旧收 `272.60` 作分母 | 严格裁定 11/26 收盘挂账 `pending`、沿用 11/25 官收 **`HK$265.40`** 并提示明日除净 `RMB 18.02 / HK$21.05`；同步补齐 11/25 `LBMA AM $3,533.20 / PM $3,466.35`、`SPDR GLD 1,027.88t (+0.57t)`、`VanEck GDX NAV $73.70` 与 11/24 `HY/CCC OAS 372/1,405bp`。 | **否 (0)** |
| **31** | 11/26 晚报初版误留 `SHFE au2702` 昨结 `768.96` 与 `SGE Au99.99` 旧均价 `760.18` | 依 `kx20261126.dat` 与 SGE 日终表更正 `SHFE au2702` 今结为 **`756.32`**、`SGE Au99.99` 加权均价 **`767.39`** 与 `Ag(T+D)` 日收 `9,606`。 | **否 (0)** |
| **32** | 11/26 18:30 老铺黄金（`06181.HK`）多源报价冲突挂账 | 依港交所 `d261126e.htm` 终结多源冲突，铁锁 11/26 官收 **`266.80 港元`**（沽空暴增 112% 至 `27.48%`），并校准紫金 H `02899.HK` 官收 `23.22 港元 (+2.74%)`。 | **否 (0)** |
| **33** | 11/25 Cboe `VIX_History.csv` 原表待核销及 23:55 截点跨凌晨污染防控 | 直连 Cboe 原表核销 `2026-11-25` 终值（`28.29` / 高 `34.95`）解除 `provisional_close`，补齐 11/26 `LBMA AM $3,562.40 / PM $3,578.90 / Ag $41.54`，并严格拦截次日凌晨官收保截点纯度。 | **否 (0)** |
| **34** | 11/27 早报部分终端显示感恩节恐慌指数 `26.80` 盘外杂讯 | 07:34 直连 Cboe `VIX_History.csv` 确认 `2026-11-26` 当时无常规日线行（`no_row_confirmed`），拦截盘外杂讯并维持 `vix_live = null`。 | **否 (0)** |
| **35** | 第 8A 路调研滞后沿用 11/24 `IGLN.L $69.18` 与旧金油比 `37.93` | 校准伦交所 `IGLN.L` 11/26 官收为 **`$69.2375`（`$69.24`）**，并按 11/26 布油 1 月官结 `$96.57` 将 `gold_brent_ratio` 更新为 **`37.16`**。 | **否 (0)** |
| **36** | 11/27 午报核验日本统计局东京都 11 月通胀多口径与国家统计局 10 月工企利润结构 | 明确区分东京都 11 月总体 `2.8%` / 不含生鲜 `2.9%` / 日央行版核心 `2.5%` / 欧美口径 `2.3%`，精准核实中国 10 月规上工企利润同比 `+20.1%` 与午盘同刻溢价 `+1.48 元/克`。 | **否 (0)** |
| **37** | 11/27 午报滞后沿用 11/26 上海金早盘基准价 `768.24` | 18:00 晚报依上金所官方基准表纠偏 11/27 上海金早盘基准价为 **`775.47 元/克`**（午盘 `784.26`）。 | **否 (0)** |
| **38** | 11/27 黑五早盘窗口 VIX 实时值与 11/26 盘外报价混用风险 | 依黑五首发布窗（03:15–09:25 EST）精准记录 `18:20` 实盘恐慌 `24.82`，严守官收基线不被盘外杂讯篡改。 | **否 (0)** |
| **39** | 11/27 18:30 初版混用国内四大黄金 ETF 11/26 滞后净值 | 23:55 修订版全量核销 11/27 官方净值与份额流：`518880 7.4473 (-0.085% / -3.72 亿)`、`518800 7.8078 (+0.80 亿)`、`159934 7.7806`、`159937 7.4308`（沪 4 只合计 `-3.25 亿`）。 | **否 (0)** |
| **40** | 11/26 Cboe VIX、11/25 NY Fed SOFR 及 11/27 LBMA 早盘定盘滞后待补 | 23:55 修订版一次性补录 Cboe 11/26 官方收盘 **`26.80`**、NY Fed 11/25 `SOFR 3.95%`（`+5bp vs IORB`）及 11/27 `LBMA AM $3,672.10 / Ag $44.04`。 | **否 (0)** |
| **41** | 11/27 晚报修订初稿 23:55 夜盘 `Au(T+D)` 同刻溢价误沿用早先高位 `+0.07 元` 及婚庆文案重复笔误 | 按 23:55 同分钟 `$3,623.34 × 6.6552 ÷ 31.1034768 = 775.28` 精确校准 `Au(T+D) 778.03` 同刻价差为 **`+2.75 元/克`**，并修正重复笔误。 | **否 (0)** |
| **42** | 11/30 美债集中交割私营净抽水口径原简写“逾 580 亿” | 锁定美国财政部官方算式：`$218.00B` 私营发行 − `$136.49B` 私营到期（总到期 `$158.96B` 扣联储内部滚续 `$22.47B`）= **`$81.51B` 私营真实净抽水**。 | **否 (0)** |
| **43** | 国投白银 LOF（`161226`）11/27 净值估测与管理层变更口径 | 核销 11/27 正式官净 **`1.1213`**（静态溢价 **`+14.96%`**），明确公告系董事长曲刚变更而非基金经理变更。 | **否 (0)** |
| **44** | 海外低费黄金 ETF `IAUM` 规模滞后口径 | 校准贝莱德 `IAUM` 最新资产规模为 **`$7.25B`**，同步全站 ETF 数据库一致。 | **否 (0)** |
| **45** | 11/28 早报滞后沿用 11/26 `Ag(T+D)` 递延费空付多口径 | 直连上金所 11/27 官方逐日表将 `Ag(T+D)` 递延费方向纠偏为 **`多付空`**（交收量自 11/26 `256.92 吨`骤降 90.8% 至 **`23.76 吨`**）。 | **否 (0)** |
| **46** | 周六线下品牌金店随周五外盘提价后婚庆省钱账更新 | 三源核实周六早间周大福涨 25 元至 **`1,093 元/克`**（老凤祥/周生生 `1,092 元`），四大行金条周末锁 `795.87 元`（加打金 `814 元`），婚庆立省扩至 **`279 元/克`（50 克省 `13,950 元` / `25.5%`）**。 | **否 (0)** |
| **47** | 4 项 11/27 欧美官方终值挂账（Cboe VIX / GLD 官净 / GDX 官净 / LBMA PM）提前核销 | 周六午间直连一次清零：Cboe `VIX_History.csv` 11/27 行 **`23.81`**（解除暂定）、SSGA `GLD` 官净 **`$332.98`**（`$120.07B` / `0.00 吨` 零流）、VanEck `GDX` 官净 **`$78.89`**（`$24.77B`）与 LBMA 11/27 PM **`$3,634.50`**。 | **否 (0)** |

---

### 🧾 2026-11-27 11:30 午报核心官源快表

| 班次 | 一手官方核验清单 | 四关与灯号裁决 |
| :--- | :--- | :--- |
| 2026-11-27 11:30 午报 | 国家统计局 10 月工企利润 +20.1%（`stats.gov.cn`）、CFETS `6.7075` 与在岸现汇 `6.6647`（`chinamoney.com.cn`）、上金所午盘 `Au99.99 778.32`（`sge.com.cn`）、四大行 11:11 金条均价 `795.87` 与日本统计局东京 CPI 官方公报（`stat.go.jp`） | 四关官方基线沿用 11/25，亚盘美债反跳 4.910% 维持 1/4 红灯停 |

---

### 📌 最新 8 大类核心官方原始数据库铁证索引（截至 2026-11-28 12:00 BJT · 覆盖下方历史归档）

1. **历史峰值与回调水位**：2026.01.29 峰值 COMEX 期金 `$5,626.80` / 现货 `$5,595.62` / 上金所 `Au99.99 1,243.02 元/克`；11/27 纽约现货官收 **`$3,652.11 (+1.76% / 全周 +3.32%)`** 距峰回调 **`-34.73%`**（进度 76%），地上黄金总市值/美国 M2 为 **`112.4%`**。
2. **11/27 纽约官收、02:30 国内夜盘与周末链上只读锚**：纽约现货官收 **`$3,652.11`**（日内 `$3,558.05–$3,685.31`，下周一第 4 关新门槛上移至 `$3,685.31`）；COMEX 活跃 `GCG27` 官结 `$3,668.50 (+2.91%)`、近月 `GCZ26 $3,639.60`；LBMA 11/27 早/午金定盘 **`$3,672.10 / $3,634.50`**、银定盘 **`$44.04 (+6.02%)`**；周六 02:30 夜盘 `Au99.99 782.00`（同刻 `$3,641.13 × 6.6547 ÷ 31.1034768 = 779.03`，溢价 **`+2.97 元`**）、`Au(T+D) 780.14`（`+1.11 元`，多付空）、`au2702 781.36`（`+2.33 元`）、`ag2702 10,344`（`Ag(T+D)` 交收骤降九成至 `23.76 吨` 翻回多付空）；周六午间只读链上锚 `XAUT $3,649.55` / `PAXG $3,647.89` 紧贴周五收盘零缺口。
3. **美股黑五薄量早收、Cboe VIX 官方终表与矿饰股**：11/27 美股仅三成量收涨——标普 **`7,297.49 (+1.60%)`**、纳指 100 **`26,726.39 (+2.61%)`**、道指 **`50,774.94 (+1.18%)`**、费半 **`9,186.71 (+4.69%)`**；Cboe `VIX_History.csv` 正式发布 11/27 完整行（O `24.89` / H `27.52` / L `23.81` / C **`23.81 -11.16%`**，较十日峰 `35.89` 回落 `33.66%` 稳过第 3 关，解除暂定；期货 `UX1 22.8402 > UX2 22.7857` 倒挂，`SKEW 145.90`）；VanEck `GDX` 官收 `$79.18 (+7.16%)` / 官方 NAV **`$78.89`**（`$24.77B`），`GDX/GLD = 0.2368`。
4. **美债官方曲线、美联储周报与五大央行**：11/27 美国财政部官曲确认 **`US10Y 4.94% (+9bp)`**、**`DFII10 2.79% (+6bp，超 ≤2.72% 线 7bp)`**、**`T10YIE 2.15% (+3bp)`**、**`US2Y 4.69% (+8bp)`**（减 `EFFR 3.88%` = **`+81bp`** 超 `+55bp` 线 26bp）、**`US30Y 5.33%`**；美联储周报确认商业银行准备金跌破 2.98 万亿至 **`$2,928.66B`**、`TGA $923.56B`、`ON RRP $350M`、黑五纽约联储常备回购 **`$23.15B`** 全部集中 08:15 早场（13:30 午场归零）直撞周一 **`$81.51B`** 美债私营净抽水；12 月加息概率 Fed `94%–97.5%` / ECB `93%–94%` / BoE `80%–86%` / BOJ `76%–80%`；周六凌晨标普将法国展望调至负面，日央行行长植田和男确认周一 `09:05 CST` 名古屋演讲。
5. **汇率、原油换月与主权购金**：`DXY 104.014 (+0.33%)`、`USD/JPY 159.54`（直逼 160 红线）、11/27 CFETS 中间价 **`6.7075`**、在岸 CNY `16:30 6.6544` / 夜盘 **`6.6541`**、离岸 `CNH 6.6551`；布油 1 月 `BRNF27` 官结 **`$95.44 (-1.17%)`**（11/30 到期切换 2 月 `$90.84` 呈 `$4.60` 换月贴水）、WTI **`$83.08 (-0.72%)`**、COMEX 铜 `HGZ26 $5.517` / LME 3M 铜 `$12,262` / 沪铜夜盘 `92,590`；周日 `19:00` 第 42 届 OPEC+ 7 国线上会；主权端中波印新稳筑长底，土耳其央行 11/26 起暂停本土矿金优先购金权。
6. **信用利差、海内外黄金 ETF 与 COMEX 库存**：11/25 FRED `HY OAS 377bp`、`CCC OAS 1,417bp`、`SOFR 3.95%`、`CoreWeave CDS 1,314bp`；SSGA 官网核销 11/27 `GLD` 官净 **`$332.98 (+4.85%，AUM $120.07B)`**、总份额 `3.606 亿份`（**单日 `0.00 吨` 零净申赎，全周净流 `-6.56 吨`，持仓 `1,027.88 吨`**）；国内 6 大黄金 ETF 11/27 合计净赎回 **`-3.99 亿元`**（沪 4 只 `-3.25 亿` + 深 2 只 `-0.74 亿`，`518850` 官净 `7.5319`）；COMEX 黄金总库存 `2,272 万盎司`、白银回落至 `3.23 亿盎司`；`BTC $59,980 (-1.20%)` 仅作只读全球流动性温度计（依央行 `银发〔2026〕42号` 中国大陆 0% 严禁配仓）。
7. **周六线下七大渠道实测与婚庆剪刀差**：周六品牌金饰集体跳涨 20–25 元至周大福 **`1,093 元/克`**（老凤祥/周生生 `1,092 元`），国有四大行投资金条周末锁定周五均价 **`795.87 元/克`**（加 18 元工费 **`814 元/克`**），婚庆 50 克立省扩大至 **`279 元/克`（`13,950 元` / `25.5%`）**；水贝周末会员条 `817–818`、非会员含税条 `872–873`、含税饰 `918–934`；工行主动积存 0 买费延至 `2027-03-31`。
8. **机构目标中位、公允锚与双轨锁定**：7 家 2027 年末点位机构中位 **`$5,000`**（4 家全年均价中位 `$4,437.5`）；按 `DFII10 2.79% / DXY 104.014` 校准双因子公允锚 **`$3,740`（`800 元/克`）**；主报告 V7.2 5 大更新条件继续 **`0/5` 严格锁定**（`+0.46% < 3%`、60 日新高硬止损与尾部深熊 `0/2`），买金四步红绿灯严格维持 **`Tier 0 · 🔴 红灯停（2/4 关 · 新仓 0%）`**。

---

### 📌 最新 8 大类核心官方原始数据库铁证索引（截至 2026-11-26 18:30 BJT · 覆盖下方 08:30 与 11/25 归档）

1. **历史峰值（2026.01.29）**：COMEX 期金 `$5,626.80`（结 `$5,318.40`）/ 现货 `$5,595.62` / LBMA PM `$5,405.00` / 上金所 `Au99.99` `1,243.02 元/克`；沿用 11/25 NY 官收 `$3,588.78` 距峰回调 **`-35.86%`**，地上黄金总市值/美国 M2 维持 **`110.5%`**。
2. **11/26 国内官收、同刻溢价与 18:30 感恩节薄盘**：今日美国感恩节股债全休、无周四 COMEX 官结，CME 电子盘明晨 `03:30–07:00 BJT` 停盘 3.5 小时；国际现货金亚盘探高 `$3,607.12`、低探 `$3,551.57`，17:00–18:30 BJT 薄量整理于 **`$3,573.00 (-0.44%)`**，现货银 `$41.50 (+0.22%)`、铂金 `$1,301.33`；上金所上海金早盘基准 **`768.24`** / 午盘 **`765.96`**，`Au99.99` 15:30 官收 **`765.82 (+1.12% / +8.47 元)`**、`Au(T+D)` **`765.78 (+1.17% / +8.88 元)`**、`Ag(T+D) 9,605 (+0.41%)`，午后同刻溢价仅 **`+0.86 元/克`**；SHFE `au2702` 15:00 收 **`767.62 (-0.17%)`**、`ag2702 9,646 (-0.71%)`、沪铜 `cu2701` 收 **`89,300 (-0.51%)`**（仍破 9 万）；已补齐 11/25 `LBMA` AM **`$3,533.20`** / PM **`$3,466.35`** / 银 **`$39.40`**（11/26 AM 18:30 刚到点挂账）。
3. **亚欧股市、金矿股与 VIX 核销**：11/26 亚太与欧洲风险偏好反弹（日经 `+0.86%`、韩股 `+0.29%`、台股 `+2.50%`、上证 `+0.01%`、恒指 `+1.19%`、欧股 STOXX 600 `+1.4%–+1.6%` / DAX `+1.7%–+2.0%`）；A/H 金矿股反弹（紫金 A `23.75 +3.40%` 当日回购 80 万股、紫金 H `HK$23.40 +3.54%`、山东黄金 `23.30 +3.10%` 16:00 说明会实录待补、中金 `+3.64%`、赤峰 `+4.87%`、周大福 `HK$11.36 +2.07%`、老铺 `06181.HK` 11/26 收盘源冲突挂账 `pending` 沿用 `HK$265.40` 且明日除净 `HK$21.05`）；VIX 11/25 Cboe 官网页与 FRED `VIXCLS` 双锁 **`28.29 (+7.32%)`**（`vix_live=null`，`checked_at 18:25` 延续 `provisional_close`）。
4. **五大央行与韩国央行最新加息**：韩国央行 11/26 以 5–2 **加息 25bp 至 3.25%**（上调 2026 GDP 预期至 3.9%）；日央行田村直树 11/26 强鹰表态需尽快加息至 ~2% 中性利率；12 月加息概率 Fed `95%–98%` / ECB `91%–95%`（今晚 20:30 纪要）/ BoE `78%–80%` / BOJ `75%–80%`；美债休市沿用 11/25 官曲（`US2Y 4.61% / US10Y 4.85% / DFII10 2.73% / EFFR 3.88% / 2Y−FF +73bp`）；中国 10Y 国债 `1.5865%`、央行 5,715 亿 1.25% 隔夜逆回购净回笼 `-455 亿`。
5. **汇率、原油与 OPEC+ 博弈**：11/26 CFETS 中间价 **`6.7096 (+8bp)`**、在岸 CNY 16:30 官收大涨 `+136bp` 至 **`6.6600`**、离岸 CNH `6.6659`、`DXY 103.78`、`USD/JPY 159.15`（仍守 160 红线下方）；布油电子盘 **`$94.50`**（11/25 官结 `$94.61`）、WTI `$84.10`、欧洲 TTF 气 **`€88.90`**、欧盟储气率降新低至 **`67.8%`**；周日 11/29 OPEC+ 第 42 届会议前伊拉克拒绝 DeGolyer & MacNaughton 2027 产能审计，阿联酋已退出，核心 7 国博弈加剧。
6. **信用配管与海内外黄金 ETF**：11/24 FRED 信用利差走阔——**`HY OAS 372bp (+9bp)`**、**`CCC OAS 1,405bp (+18bp)`** 重破千四（11/25 因美假期顺延）；11/25 `ON RRP $3.00 亿`、`CoreWeave CDS 1,314bp`；11/25 **SPDR `GLD` 持仓增 `+0.57t` 至 `1,027.88 吨`**（精准衔接 11/24 `1,027.31t`）、**VanEck `GDX` 官方 NAV `$73.70 (+3.08%)`**；国内 `518880` 11/26 成交 `49.14 亿`（11/26 晚间净值与份额流待补）。
7. **11/26 国内线下零售全面封账**：国有四大行标准投资金条均价上调 `+4.91 元` 至 **`783.07 元/克`**（工 `783.94` / 建 `783.20` / 农 `781.01` / 中 `784.13`），加 18 元工费 `801 元`；周大福足金饰品持平 **`1,068 元/克`**（老凤祥 `1,065` / 周生生 `1,062`），50g 婚庆立省 **`267 元/克`（13,350 元 / 25.0%）**；水贝非会员金条 `865` / 含税首饰 `919` / 会员条 `811` / 回收 `753`；印度 MCX 期金弹至 `₹1,22,500–₹1,22,740/10g`。
8. **机构目标中位与主报告触发线**：7 家 2027 年末点位机构中位稳守 **`$5,000`**（4 家均价中位 `$4,437.5`）；主报告 V7.2「5 大实质更新触发条件」继续 **`0/5` 严格锁定**（NY 官收 `-1.28% < 3%`、国内 `765.82` 较 `778` 差 `-12.18 元 < 25 元`），买金四步红绿灯维持 **`Tier 0 · 🔴 红灯停（1/4 关 · 新仓 0%）`**。

---

### 📌 最新 8 大类核心官方原始数据库铁证索引（截至 2026-11-26 08:30 BJT · 覆盖下方 11/25 归档）

1. **历史峰值（2026.01.29）**：COMEX 期金 `$5,626.80`（结 `$5,318.40`）/ 现货 `$5,595.62` / LBMA PM `$5,405.00` / 上金所 `Au99.99` `1,243.02 元/克`；当前 11/25 NY 现货官收 `$3,588.78` 距峰回调 **`-35.86%`**，地上黄金总市值/美国 M2 按最新价校准为 **`110.5%`**。
2. **11/25 纽约官收、夜盘实盘与 08:30 亚盘**：现货金 11/25 盘中深探 **`$3,427.01`**（较 11/24 官收 `$3,554.77` 跌 `$128`）后深 V 反抽，NY 17:00 EST 官收 **`$3,588.78 (+0.96%)`**（亚盘 08:30 暂报 **`$3,578.00`**）；COMEX 近月 `GCX26` 13:30 EST 官结 **`$3,534.70 (-0.71%)`**（远月主力 `GCZ26` 结 `$3,540.90`）；现货银收 **`$41.61 (+1.74%)`**（金银比 **`86.25`**），COMEX 铜官结 **`$5.3325 (-0.56%)`**，沪铜夜盘续跌 **`-2.24%` 收 `87,130 元/吨`**；国内 02:30 夜盘 `SGE Au(T+D) 758.06 (+0.15%)`、`SHFE au2702 761.12 (+0.49%)`（早盘 09:00 存补涨空间）；11/25 `LBMA` AM/PM 待 18:00 晚报补录。
3. **美股深 V 反抽、恐慌官收与矿股**：11/25 美股道指盘中低见 `48,913`、日内最大振幅 `1,481` 点、自低点反弹 `1,270` 点官收 **`50,182.95 (+0.33%)`**，标普收 **`7,182.78 (-0.25%)`**（广度 370 涨 / 128 跌，等权 `RSP +0.83%`），纳指 `23,585.80 (-0.62%)`，费城半导体 `-0.65%`；Cboe 官网产品页 `16:15 EST` 官收 **`^VIX 28.29 (+7.32%)`**（标 `provisional_close`，`vix_live=null`，待 18:00 晚报用 `VIX_History.csv` 终表复核），较十日峰值 `35.89` 回落 **`21.18%`** 通过第 3 关；11/25 `GLD` 三源官收 **`$327.45 (+0.61%)`**、`GDX $73.89 (+3.53%)`（`GDX/GLD 0.2257`，VanEck 11/25 NAV 待 18:00 晚报补录）、`NEM $101.44`（除息 `$0.260`，复权 `+2.02%` / 原始 `+1.76%`）。
4. **美英四连考、美债官方曲线与央行加息定价**：11/25 21:30 美国 10 月核心 PCE 环比 `+0.3%` / 同比 **`+3.3%`**（整体 `3.8%`）、Q3 GDP 二修 **`+4.3%`**、初请 **`18.9 万`**、耐用品 `+1.2%`；00:30 `$440 亿` 7Y 美债拍卖中标 **`4.708%`**（尾差 `+1.0bp`、倍数 `2.43x`、外资 `58.2%`）；美国财政部官方曲线确认 11/25 **`DFII10 2.73% (-6bp)`**（差 `1bp` 未过第 1 关 `≤2.72%`）、**`US10Y 4.85% (-6bp)`**、**`US2Y 4.61% (-6bp)`**（减 NY Fed 11/24 `EFFR 3.88%` = **`+73bp`** 未过第 2 关）、**`US30Y 5.24%`**；美联储官网日历确认美东 **`12/08–09`** 议息（北京 `12/10 03:00` 决议），12 月加息概率 Fed `94%–98%` / ECB `91%–92%` / BoE `75%–80%` / BOJ `75%–84%`。
5. **汇率、原油飙升与地缘**：`DXY 103.71 (-0.11%)`、`USD/JPY 159.15`、在岸人民币 23:30 夜盘 **`6.6681`**、11/25 CFETS 中间价 **`6.7088`**（11/26 `09:15` 新中间价待 18:00 晚报封账）、`USD/HKD 7.8389`、金管局总结余 **`540.83 亿港元`**；霍尔木兹油轮再遇袭叠加 EIA 库欣降库 `-53.4 万桶` 推升布油 `BRNF27` 官结 **`$94.61 (+3.51%)`**、WTI **`$83.68 (+2.67%)`**，远离 `<$80` 尾部深熊红线。
6. **信用配管与中美黄金 ETF 持仓**：NY Fed 11/25 **`ON RRP $3.00 亿`**（缓冲几近枯竭，11/30 撞 `$2,180 亿` 美债集中交割）、11/24 `SOFR 3.94%`、11/23 `HY OAS 363bp / CCC OAS 1,387bp`（FRED 11/24–25 待晚报更新）；SSGA 官方 `.xlsx` 铁证校准 11/24 `GLD` 持仓实为 **`1,027.31 吨（-3.99 吨）`**（11/25 `GLD` 吨数待晚报补录）；`CoreWeave` 5Y CDS 仍高悬纪录 `1,314bp`。
7. **线下零售与感恩节休市安排**：截至 `08:30` 国内银行与金店尚未公布 `11/26` 新牌价，暂沿用 11/25 官价——四大行金条均价 **`778.16 元/克`**（加 18 元工费 `796.16`）、周大福 **`1,068 元/克`**（50g 婚庆省约 `272 元/克` / `13,592 元` / `25.5%`），`11/26 09:00–10:00` 新牌价待 18:00 晚报封账；**今晚 11/26 美国感恩节美股/美债全休，CME 贵金属仅明晨 `03:30–07:00 BJT` 停盘 3.5 小时**，今晚 `18:00` 与明早 `07:30` 切入感恩节 A 类局部休市模式。
8. **机构目标中位与主报告触发线**：7 家可独立溯源的 2027 年末点位机构中位稳守 **`$5,000`**（另有 3 家 2027 年均价、1 家 6–12 月目标及 1 家德银旧稿）；11/25 纽约现货官收 `$3,588.78` 较主报告 V7.2 基线 `$3,635.24` 仅差 **`-1.28%`（远未及 `-3%` / `$3,526` 触发线）**，主报告 V7.2「5 大实质更新触发条件」**`0/5`** 继续严格锁定，买金四步红绿灯维持 **`Tier 0 · 🔴 红灯停（1/4 关 · 新仓 0%）`**。

---

## 二、8 大类核心官方原始数据库铁证索引（截至 2026-11-25 21:25 BJT）

1. **历史峰值（2026.01.29）**：COMEX 期金 `$5,626.80`（结 `$5,318.40`）/ 现货 `$5,595.62` / LBMA PM `$5,405.00` / 上金所 `Au99.99` `1,243.02 元/克`。
2. **11/25 国内官收、同分钟溢价与 21:25 国际实盘**：现货金 11/24 NY 官收 `$3,554.77 (-2.21%)`，11/25 亚欧连破 `$3,550`（07:51）、`$3,526`（13:50）、`$3,500`（19:59 探低 **`$3,486.45`**），21:24 报 **`$3,506.12 (-1.37% vs NY 收)`**；现货银 **`$39.95 (-2.30%)`**、COMEX 近月 `GCZ26 $3,513.70`、`SIZ26 $39.70`、沪铜 `cu2701` 暴跌 **`-6.34%` 收 `87,950 元/吨`**（破 9 万）；SGE 11/25 `SHAU` 早/午盘 `764.67 / 755.85`，15:30 `Au99.99` 官收 **`757.35 (-20.37 / -2.62%，同刻溢价 +1.53 元)`**、`Au(T+D)` **`756.90 (-3.18%，空付多，溢价 +1.08 元)`**、`Ag(T+D) 9,381 (-7.82%)`（21:25 夜盘 `Au(T+D) 752.34` 平水 `+0.06 元`）；SHFE `au2702` 收 **`757.40`** / 结 **`768.96`**，`pm20261125.dat` 黄金主+近月前 20 净多缩 `-4,287` 手、`ag2702 -7,038` 手；11/24 `LBMA` 金定盘 `$3,622.55 / $3,623.50`（11/25 待公开）、`MCX` 11/25 探低 `₹1,20,575/10g`。
3. **美盘前避险急升温、全球股市与港 A 金股**：21:20 美股盘前 `ES -1.95%`、`NQ -2.88%`、`YM -1.27%`、`NVDA $147.23 (-5.25%)`、`DELL $278.56 (-5.66%)`、**`^VIX` 飙升 `+17.56%` 破 30 至 `30.99`（日高 `31.08`）**、`BTC $58,621 (-1.89%)`；11/25 亚太官收日经 `-2.78%`、韩股 `-6.16%`、台股 `-4.80%`、上证 `3,476.47 (-2.03%)`、恒指 `21,966.01 (-1.14%)`；11/24 `GLD $325.45 (-2.27%)`、`GDX` 校准 **`$71.37 (-1.96%) / NAV $71.50`**（`GDX/GLD 0.2193`）；港 A 金股赤峰 `+0.18%` 唯一收涨，紫金 A `22.97 (-1.03%)` / H `22.60 (-3.34%)`（披露 1.73 亿回购），老铺黄金 `06181` EGM `99.9954%` 通过 18.02 元中期息（11/27 除净）收 `265.40 (-2.64%)`，周大福 `11.13 (-3.05%)` 遭瑞银/花旗/美银/中金调降目标价。
4. **日债 40Y 拍卖、德国 GDP 下修、美债与五大央行**：日本 11:35 3,000 亿日元 40Y 拍卖得标 **`4.090%`** 但投标倍数仅 **`2.63x`** 偏弱（二级冲高 `4.194%`、21:23 `4.162%`，10Y 日债 `2.609%`），BOJ 10 月截尾均值核心通胀升至 **`2.63%`**；德国 Q3 GDP 终值下修至 **`+0.1%`**；21:20 避险压低 `US10Y 4.844% (-5.8bp)`、`US2Y 4.604% (-6.7bp，2Y−FF +72bp)`、`US30Y 5.256%`，11/24 官方 `DFII10 2.79%`；12 月加息概率 Fed `95%–98%`、ECB `91%–92%`、BoE `75%–80%`（22:15 议会作证）、BOJ `75%–84%`；PBOC 11/25 09:20 全口径净投放 **`+3,210 亿`**（8,000 MLF + 5,000 7D + 6,170 隔夜 1.25% − 15,960 到期），`DR007 1.3740%`。
5. **汇率、能源与地缘**：`DXY 103.97 (+0.15%)`、`USD/JPY 159.28`（日高 `159.50` 未破 `160`）、CFETS 中间价 **`6.7088 (+23bp)`**、在岸 CNY 16:30 官收 **`6.6736 (-88bp)`**、离岸 CNH `6.6730`、`USD/HKD 7.8380`；布油 `BRNF27` 11/24 官结 `$91.40`，11/25 21:13 升至 **`$92.47 (+1.17%)`**（1–2 月近远月强贴水 `+$3.24`），WTI `$82.50 (+0.55%)`，TTF 气 `€88.95 (-2.97%)`、欧盟储气 `68.4%`；伊朗革命卫队称两艘油轮霍尔木兹触雷、胡塞袭沙特拉斯坦努拉炼厂与利雅得、11/29 OPEC+ 会议前伊拉克产能审计分歧（4.9M vs 5.2–6.0M bpd）；中国商务部 `2026年第59号` 暂缓对美镓锗锑超硬/石墨出口禁令第二款（11/28–2027/01/27）。
6. **信用配管与中美黄金 ETF 持仓**：`11/24 SOFR 3.94% (+2bp)`、`11/24 ON RRP $3.01 亿`、`11/23 HY OAS 363bp / CCC OAS 1,387bp`、**`CoreWeave` 5Y CDS 飙至纪录 `1,314bp`**；11/24 SPDR `GLD` 持仓 **`1,031.299t`（0.00t 持平）**；国内黄金 ETF 11/24 份额流落盘：`518880` `-3,250 万份 / -2.41 亿`（连流 8 日）、`159937` `-5,190 万`，低费 `518660` 逆势 **`+240 万份 / +1,792 万`**（11/25 份额待披露）。
7. **衍生品与国内线下零售实盘**：`CME #26-389` 提保生效首日放大去杠杆；国内 11/25 实物渠道大降——四大行金条均价 **`778.16 元/克 (-24.09)`**（加 18 元工费 `796.16`），周大福 **`1,068 元/克 (-35)`** / 老凤祥 `1,065` / 周生生 `1,062`，50g 婚庆仍省 **约 272 元/克（精确 271.84 元 / 13,592 元 / 25.5%）**；水贝会员条 `803–811` / 散客 `856` / 回收 `742–747`。
8. **12 大投行中位、WGC 供需与主报告触发线**：8 家 2027 年末点位机构中位稳守 **`$5,000`**；主报告 V7.2 5 大官收触发条件暂 **`0/5`**（11/24 NY 收 `-2.21% < 3%`、SGE 15:30 `757.35` 差 `-20.65 元 < 25 元`），但 21:24 实时 `$3,506` 已跨 `$3,526` 线，明早 `11/26 07:30` 按纽约 11/25 官收正式裁定是否升级主报告。

---

## 三、2026-11-25 系统全栈架构升级留痕（已获用户审批落地）

| 升级模块 | 落地资产与核心改动 | 验收与长期护栏 |
| :--- | :--- | :--- |
| **1. Tier C 提案 #2 结案落地** | 在 `SKILL.md`、`5-plus-1-research-playbook.md` 与 `AGENTS.md` 固化：① 美股 `GLD`/`GDX` 官收白名单（`StockAnalysis`/`Investing`/`VanEck NAV`）；② 禁用 `Barchart` 远月滞后合约快照；③ `site:shfe.com.cn` / `site:lbma.org.uk` 定向补录词；④ 北美冬令时（`EST -13h`/`CST -14h`）硬校验与 `2027-03-14` 动态切夏令时。`RSI_PLAYBOOK.md` 第四节结案清零，总行数严守 `≤180` 行。 | 根治上游脏快照信噪比瓶颈 |
| **2. 外置 60+ 天跨市场日历** | 新建 `market_calendar.json`（覆盖 `2026-11-26` 至 `2027-03-14` 全部美/中/港/欧/英/日/印休市、半日市、四大央行议息、BCOM/GSCI 调仓、春节 10 天 B 类休市、北美夏令时切换及 `2027-Q1` 香港贵金属中央清算监测项）。 | 纳入 `lint_readability.py` 合法 JSON 与非空强校验 |
| **3. 响应式单文件手机端 HTML** | `build_daily.py` 新增 `build_gold_mobile_html()`，编译最新日报时原子写入（`.tmp` + `os.replace`）`daily/latest_gold.html`：含 `viewport-fit=cover`、吸顶快捷导航、自适应 KPI、640px SVG `.svg-scroll` 水平平滑滚动不缩字、表格横滑与 `@media (prefers-color-scheme: dark)` 护眼深色模式，零影响 PDF/DOCX 编译。 | 纳入 Gate 6（非 `--precheck` 日报校验 `≥5KB` + `viewport`） |
| **4. 公开可证伪预测记分卡** | 新建 `daily/SCORECARD.md`（零内部工程/RSI 词汇）：含累计命中率总览、表一已到期 4 项回验（3 兑现 + 1 部分兑现 + 0 证伪）、表二 5 项当前追踪预判及表三历史记录零篡改宣言。 | 纳入 `lint_readability.py` 存在性与内部工程词零泄露校验 |
| **5. 全量文档纠偏与防卡壳护栏** | 同步修复 `AGENTS.md`、`daily/AGENTS.md`、`DAILY_FORMAT_SPEC.md`、`SKILL.md` 及 3 份参考手册：68 禁词（47 ASCII + 21 中文/混合）、四轨矩阵、排障表第 3 节、Step 5 Tier B 对齐；新增无人值守禁 `edit_file`（一律 `write_file`）、惰性主报告加载（仅读 `master_snapshot.json`）与同场 `_r2` 防覆写锁。 | 消除全链路文档冲突与定时任务卡壳隐患 |
| **6. 跨项目单一权威源（SSOT）** | 在 `AGENTS.md`、`SKILL.md`、`directives-and-snapshot-schema.md` 及 `data_snapshot.json` 明确：黄金项目 `07:30`/`18:00` 先跑并拥有 `data_snapshot.json`（含 `tier_code` 与 `new_buy_allowed` 布尔开关）唯一写入权；股研模块（`global-investment-research/equity`）`07:55`/`18:25` 错峰只读校验，严禁与黄金红绿灯指令打架。 | `lint_readability.py` Gate 5 校验 `new_buy_allowed == (tier_code != "Tier 0")` |
