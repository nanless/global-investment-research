/* ==========================================================================
   Global Investment Research Portal — Interactive K-Line & Indicators Engine
   Zero External Dependencies | Dual-Layer HiDPI Canvas2D | Light + Dark Sync
   ========================================================================== */
(function () {
  "use strict";

  const COLOR_STORAGE_KEY = "gir_kline_color";
  const GOLD_ASSET_RE =
    /(?:^cmd_(?:XAU|GC|AU0|Au9999|AuTD)$|^(?:etf|stk)_(?:518660|518880|518850|159934|159937|518800|517520|159562|02840(?:\.HK)?|03081(?:\.HK)?|09840(?:\.HK)?|01929(?:\.HK)?|06181(?:\.HK)?|02899(?:\.HK)?|601899|600547|600489|GLD|IAU|IAUM|GLDM|IGLN|GDX|GDXJ|SGOL|BAR|SGLN|NEM|FCX)$|黄金|金矿|沪金|现货金|期金|Au99|Au\(T\+D\))/i;

  const manifestCache = new Map();
  const shardCache = new Map();
  const activeInstances = new Set();

  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function isFiniteNum(v) {
    return typeof v === "number" && Number.isFinite(v);
  }

  function isGoldAsset(idOrCode, name) {
    const a = String(idOrCode || "").trim();
    const b = String(name || "").trim();
    return GOLD_ASSET_RE.test(a) || GOLD_ASSET_RE.test(b);
  }

  function isGlobalGoldRedLight() {
    return document.body && document.body.getAttribute("data-gold-red-light") === "1";
  }

  function getColorConvention() {
    try {
      const v = localStorage.getItem(COLOR_STORAGE_KEY);
      if (v === "us" || v === "cn") return v;
    } catch (_) {}
    return "cn";
  }

  function setColorConvention(mode) {
    const next = mode === "us" ? "us" : "cn";
    try {
      localStorage.setItem(COLOR_STORAGE_KEY, next);
    } catch (_) {}
    window.dispatchEvent(new CustomEvent("gir:kline-color", { detail: { mode: next } }));
  }

  function getBasePrefix(explicitBase) {
    if (typeof explicitBase === "string") return explicitBase;
    return (document.body && document.body.getAttribute("data-base-prefix")) || "";
  }

  function getThemePalette(colorConv) {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const red = isDark ? "#f87171" : "#c81e1e";
    const green = isDark ? "#2dd4bf" : "#0d7a5f";
    const redFade = isDark ? "rgba(248,113,113,0.42)" : "rgba(200,30,30,0.38)";
    const greenFade = isDark ? "rgba(45,212,191,0.42)" : "rgba(13,122,95,0.38)";
    const up = colorConv === "us" ? green : red;
    const down = colorConv === "us" ? red : green;
    const upFade = colorConv === "us" ? greenFade : redFade;
    const downFade = colorConv === "us" ? redFade : greenFade;

    return {
      isDark: isDark,
      bg: isDark ? "#161c26" : "#fffefb",
      grid: isDark ? "#253042" : "#ebe5d9",
      axisLine: isDark ? "#334155" : "#d9d1c2",
      axisText: isDark ? "#9aa5b4" : "#645f57",
      crosshair: isDark ? "#64748b" : "#8c857a",
      pillBg: isDark ? "#e2e8f0" : "#171716",
      pillText: isDark ? "#0f131a" : "#fffefb",
      up: up,
      down: down,
      upFade: upFade,
      downFade: downFade,
      ma5: isDark ? "#fbbf24" : "#b45309",
      ma10: isDark ? "#60a5fa" : "#1d4ed8",
      ma20: isDark ? "#c084fc" : "#7c3aed",
      ma60: isDark ? "#2dd4bf" : "#0d6963",
      ma120: isDark ? "#f472b6" : "#be185d",
      bollStroke: isDark ? "#60a5fa" : "#2563eb",
      bollFill: isDark ? "rgba(96,165,250,0.10)" : "rgba(37,99,235,0.07)",
      anchorFill: isDark ? "rgba(45,212,191,0.14)" : "rgba(4,120,87,0.11)",
      anchorStroke: isDark ? "#2dd4bf" : "#047857",
      anchorLockFill: isDark ? "rgba(251,191,36,0.13)" : "rgba(168,93,4,0.10)",
      anchorLockStroke: isDark ? "#fbbf24" : "#a85d04",
      zoneOver: isDark ? "rgba(248,113,113,0.08)" : "rgba(200,30,30,0.05)",
      zoneUnder: isDark ? "rgba(45,212,191,0.08)" : "rgba(13,122,95,0.05)",
    };
  }

  /* ------------------------------------------------------------------------
     1. Manifest & Sharded Static JSON Loader (Allowlist + Memory Cache)
     ------------------------------------------------------------------------ */
  function loadManifest(basePath) {
    const bp = getBasePrefix(basePath);
    const url = bp + "assets/klines/manifest.json";
    if (manifestCache.has(url)) return manifestCache.get(url);
    const p = fetch(url, { cache: "default" })
      .then(function (resp) {
        if (!resp.ok) return null;
        return resp.json();
      })
      .then(function (data) {
        if (!data || typeof data !== "object" || !Array.isArray(data.catalog)) return null;
        const byId = new Map();
        const byCode = new Map();
        const byDossier = new Map();
        data.catalog.forEach(function (item) {
          if (!item || typeof item !== "object" || !item.id) return;
          byId.set(String(item.id), item);
          if (item.code) byCode.set(String(item.code).toUpperCase(), item);
          if (item.dossier_key) byDossier.set(String(item.dossier_key), item);
        });
        data._byId = byId;
        data._byCode = byCode;
        data._byDossier = byDossier;
        return data;
      })
      .catch(function () {
        return null;
      });
    manifestCache.set(url, p);
    return p;
  }

  function resolveCatalogItem(manifest, symbolId) {
    if (!manifest || !symbolId) return null;
    const raw = String(symbolId).trim();
    if (!raw) return null;
    if (manifest._byId.has(raw)) return manifest._byId.get(raw);
    if (manifest._byDossier.has(raw)) return manifest._byDossier.get(raw);
    const up = raw.toUpperCase();
    if (manifest._byCode.has(up)) return manifest._byCode.get(up);
    if (manifest._byId.has("stk_" + raw)) return manifest._byId.get("stk_" + raw);
    if (manifest._byId.has("stk_" + up)) return manifest._byId.get("stk_" + up);
    if (manifest._byId.has("etf_" + raw)) return manifest._byId.get("etf_" + raw);
    if (manifest._byId.has("etf_" + up)) return manifest._byId.get("etf_" + up);
    // Strip prefix like "a-share:600036" -> "600036"
    const colonIdx = raw.indexOf(":");
    if (colonIdx > 0) {
      const bare = raw.slice(colonIdx + 1).trim();
      if (manifest._byId.has("stk_" + bare)) return manifest._byId.get("stk_" + bare);
      if (manifest._byCode.has(bare.toUpperCase())) return manifest._byCode.get(bare.toUpperCase());
    }
    return null;
  }

  function loadShardFile(shardFile, basePath) {
    if (typeof shardFile !== "string" || !/^[A-Za-z0-9_.-]+\.json$/.test(shardFile)) {
      return Promise.resolve(null);
    }
    const bp = getBasePrefix(basePath);
    const url = bp + "assets/klines/" + shardFile;
    if (shardCache.has(url)) return shardCache.get(url);
    const p = fetch(url, { cache: "default" })
      .then(function (resp) {
        if (!resp.ok) return null;
        return resp.json();
      })
      .then(function (data) {
        return data && typeof data === "object" && data.series ? data : null;
      })
      .catch(function () {
        return null;
      });
    shardCache.set(url, p);
    return p;
  }

  function sanitizeBars(rawBars) {
    if (!Array.isArray(rawBars)) return [];
    const out = [];
    for (let i = 0; i < rawBars.length; i++) {
      const b = rawBars[i];
      if (!Array.isArray(b) || b.length < 5) continue;
      const dt = String(b[0] || "").trim();
      const o = Number(b[1]);
      const h = Number(b[2]);
      const l = Number(b[3]);
      const c = Number(b[4]);
      const vRaw = b.length >= 6 && b[5] != null ? Number(b[5]) : null;
      const v = vRaw != null && Number.isFinite(vRaw) && vRaw >= 0 ? vRaw : null;
      if (!dt || !Number.isFinite(o) || !Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(c)) continue;
      if (c <= 0 || h < l) continue;
      out.push({ t: dt, o: o, h: h, l: l, c: c, v: v });
    }
    return out;
  }

  function loadSeries(symbolId, basePath) {
    return loadManifest(basePath).then(function (manifest) {
      if (!manifest) return { status: "no_manifest", meta: null, series: null, bars: [] };
      const item = resolveCatalogItem(manifest, symbolId);
      if (!item) return { status: "not_found", meta: null, series: null, bars: [] };
      const shardMap = manifest.shards || {};
      const shardKey = item.shard || "core";
      const shardEntry = shardMap[shardKey];
      const shardFile =
        typeof shardEntry === "string"
          ? shardEntry
          : shardEntry && typeof shardEntry === "object" && typeof shardEntry.file === "string"
          ? shardEntry.file
          : shardKey.endsWith(".json")
          ? shardKey
          : shardKey + ".json";
      return loadShardFile(shardFile, basePath).then(function (shardData) {
        if (!shardData || !shardData.series || !shardData.series[item.id]) {
          return { status: "missing_series", meta: item, series: null, bars: [] };
        }
        const ser = shardData.series[item.id];
        const bars = sanitizeBars(ser.bars);
        return {
          status: bars.length > 0 ? "ok" : "empty_bars",
          meta: item,
          series: ser,
          bars: bars,
          manifest: manifest,
        };
      });
    });
  }

  /* ------------------------------------------------------------------------
     2. Technical Indicators Engine (Computed Over Full bars[0..N-1])
     ------------------------------------------------------------------------ */
  function calcSMA(values, period) {
    const n = values.length;
    const out = new Array(n).fill(null);
    if (period <= 0 || n < period) return out;
    let sum = 0;
    let validCount = 0;
    for (let i = 0; i < n; i++) {
      const v = values[i];
      if (isFiniteNum(v)) {
        sum += v;
        validCount++;
      }
      if (i >= period) {
        const old = values[i - period];
        if (isFiniteNum(old)) {
          sum -= old;
          validCount--;
        }
      }
      if (i >= period - 1 && validCount === period) {
        const avg = sum / period;
        out[i] = Number.isFinite(avg) ? avg : null;
      }
    }
    return out;
  }

  function calcEMA(values, period) {
    const n = values.length;
    const out = new Array(n).fill(null);
    if (period <= 0 || n === 0) return out;
    const k = 2 / (period + 1);
    let ema = null;
    for (let i = 0; i < n; i++) {
      const v = values[i];
      if (!isFiniteNum(v)) continue;
      ema = ema === null ? v : v * k + ema * (1 - k);
      out[i] = Number.isFinite(ema) ? ema : null;
    }
    return out;
  }

  function calcBOLL(closes, period, mult) {
    const n = closes.length;
    const mid = calcSMA(closes, period);
    const upper = new Array(n).fill(null);
    const lower = new Array(n).fill(null);
    for (let i = period - 1; i < n; i++) {
      const m = mid[i];
      if (!isFiniteNum(m)) continue;
      let sq = 0;
      for (let j = i - period + 1; j <= i; j++) {
        const d = closes[j] - m;
        sq += d * d;
      }
      const sd = Math.sqrt(sq / period);
      if (Number.isFinite(sd)) {
        upper[i] = m + mult * sd;
        lower[i] = m - mult * sd;
      }
    }
    return { mid: mid, upper: upper, lower: lower };
  }

  function calcMACD(closes) {
    const n = closes.length;
    const ema12 = calcEMA(closes, 12);
    const ema26 = calcEMA(closes, 26);
    const dif = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
      if (isFiniteNum(ema12[i]) && isFiniteNum(ema26[i])) {
        dif[i] = ema12[i] - ema26[i];
      }
    }
    const dea = calcEMA(dif, 9);
    const hist = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
      if (isFiniteNum(dif[i]) && isFiniteNum(dea[i])) {
        hist[i] = 2 * (dif[i] - dea[i]);
      }
    }
    return { dif: dif, dea: dea, hist: hist, ema12: ema12, ema26: ema26 };
  }

  function calcRSI(closes, period) {
    const n = closes.length;
    const out = new Array(n).fill(null);
    if (n <= period) return out;
    let avgG = 0;
    let avgL = 0;
    for (let i = 1; i <= period; i++) {
      const diff = closes[i] - closes[i - 1];
      if (diff > 0) avgG += diff;
      else avgL += -diff;
    }
    avgG /= period;
    avgL /= period;
    out[period] = avgL === 0 ? (avgG === 0 ? 50 : 100) : 100 - 100 / (1 + avgG / avgL);
    for (let i = period + 1; i < n; i++) {
      const diff = closes[i] - closes[i - 1];
      const g = diff > 0 ? diff : 0;
      const l = diff < 0 ? -diff : 0;
      avgG = (avgG * (period - 1) + g) / period;
      avgL = (avgL * (period - 1) + l) / period;
      const rsi = avgL === 0 ? (avgG === 0 ? 50 : 100) : 100 - 100 / (1 + avgG / avgL);
      out[i] = Number.isFinite(rsi) ? rsi : null;
    }
    return out;
  }

  function calcKDJ(bars) {
    const n = bars.length;
    const kArr = new Array(n).fill(null);
    const dArr = new Array(n).fill(null);
    const jArr = new Array(n).fill(null);
    let kVal = 50;
    let dVal = 50;
    for (let i = 0; i < n; i++) {
      let hi = -Infinity;
      let lo = Infinity;
      const s = Math.max(0, i - 8);
      for (let j = s; j <= i; j++) {
        if (bars[j].h > hi) hi = bars[j].h;
        if (bars[j].l < lo) lo = bars[j].l;
      }
      const rsv = hi === lo ? 50 : ((bars[i].c - lo) / (hi - lo)) * 100;
      kVal = (2 / 3) * kVal + (1 / 3) * rsv;
      dVal = (2 / 3) * dVal + (1 / 3) * kVal;
      const jVal = 3 * kVal - 2 * dVal;
      kArr[i] = Number.isFinite(kVal) ? kVal : null;
      dArr[i] = Number.isFinite(dVal) ? dVal : null;
      jArr[i] = Number.isFinite(jVal) ? jVal : null;
    }
    return { k: kArr, d: dArr, j: jArr };
  }

  function calcATR(bars, period) {
    const n = bars.length;
    const tr = new Array(n).fill(null);
    const atr = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
      if (i === 0) {
        tr[i] = bars[i].h - bars[i].l;
      } else {
        const pc = bars[i - 1].c;
        tr[i] = Math.max(bars[i].h - bars[i].l, Math.abs(bars[i].h - pc), Math.abs(bars[i].l - pc));
      }
    }
    if (n >= period) {
      let sum = 0;
      for (let i = 0; i < period; i++) sum += tr[i];
      let prev = sum / period;
      atr[period - 1] = prev;
      for (let i = period; i < n; i++) {
        prev = (prev * (period - 1) + tr[i]) / period;
        atr[i] = Number.isFinite(prev) ? prev : null;
      }
    }
    return atr;
  }

  function calcBIAS(closes, ma20) {
    const n = closes.length;
    const out = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
      if (isFiniteNum(ma20[i]) && ma20[i] !== 0) {
        const b = ((closes[i] - ma20[i]) / ma20[i]) * 100;
        out[i] = Number.isFinite(b) ? b : null;
      }
    }
    return out;
  }

  function computeIndicators(bars) {
    const closes = bars.map(function (b) { return b.c; });
    const vols = bars.map(function (b) { return b.v; });
    const ma5 = calcSMA(closes, 5);
    const ma10 = calcSMA(closes, 10);
    const ma20 = calcSMA(closes, 20);
    const ma60 = calcSMA(closes, 60);
    const ma120 = calcSMA(closes, 120);
    const boll = calcBOLL(closes, 20, 2);
    const macd = calcMACD(closes);
    const rsi6 = calcRSI(closes, 6);
    const rsi12 = calcRSI(closes, 12);
    const rsi24 = calcRSI(closes, 24);
    const kdj = calcKDJ(bars);
    const atr14 = calcATR(bars, 14);
    const bias20 = calcBIAS(closes, ma20);
    const mavol5 = calcSMA(vols, 5);
    const mavol10 = calcSMA(vols, 10);
    const volNonZero = vols.filter(function (v) { return isFiniteNum(v) && v > 0; }).length;
    const hasVol = bars.length > 0 && volNonZero / bars.length >= 0.2;
    return {
      ma5: ma5,
      ma10: ma10,
      ma20: ma20,
      ma60: ma60,
      ma120: ma120,
      ema12: macd.ema12,
      ema26: macd.ema26,
      boll: boll,
      macd: macd,
      rsi6: rsi6,
      rsi12: rsi12,
      rsi24: rsi24,
      kdj: kdj,
      atr14: atr14,
      bias20: bias20,
      mavol5: mavol5,
      mavol10: mavol10,
      hasVol: hasVol,
    };
  }

  /* ------------------------------------------------------------------------
     3. Formatting & 10-Second Beginner Technical Diagnosis
     ------------------------------------------------------------------------ */
  function fmtPrice(v, unit) {
    if (!isFiniteNum(v)) return "—";
    const abs = Math.abs(v);
    let dp = 2;
    if (unit === "%" || unit === "pct") dp = 3;
    else if (abs < 2) dp = 4;
    else if (abs < 20) dp = 3;
    else if (abs >= 10000) dp = 1;
    return v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }

  function fmtNum(v, dp) {
    if (!isFiniteNum(v)) return "—";
    return v.toFixed(dp == null ? 2 : dp);
  }

  function fmtVol(v, market) {
    if (!isFiniteNum(v)) return "—";
    const isCN = market === "a-share" || market === "hk-stock" || market === "a_index" || market === "hk_index";
    if (isCN) {
      if (v >= 1e8) return (v / 1e8).toFixed(2) + "亿";
      if (v >= 1e4) return (v / 1e4).toFixed(1) + "万";
      return String(Math.round(v));
    }
    if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
    if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
    if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
    return String(Math.round(v));
  }

  function buildDiagnosis(bars, ind, opts) {
    const n = bars.length;
    if (n === 0) return null;
    const i = n - 1;
    const c = bars[i].c;
    const m5 = ind.ma5[i];
    const m20 = ind.ma20[i];
    const m60 = ind.ma60[i];

    // 1. Trend status
    let trendVal = "均线粘合震荡";
    let trendSub = "方向待进一步明朗";
    let trendTone = "neutral";
    if (isFiniteNum(m5) && isFiniteNum(m20) && isFiniteNum(m60)) {
      if (c > m5 && m5 > m20 && m20 > m60) {
        trendVal = "多头排列";
        trendSub = "站稳 5 / 20 / 60 日均线";
        trendTone = "up";
      } else if (c < m5 && m5 < m20 && m20 < m60) {
        trendVal = "空头承压";
        trendSub = "受压于 5 / 20 / 60 日均线";
        trendTone = "down";
      } else if (c > m60 && c <= m20) {
        trendVal = "季线上方休整";
        trendSub = "回踩 20 日线观察承接";
        trendTone = "warn";
      } else if (c <= m60 && c > m20) {
        trendVal = "弱势反抽";
        trendSub = "站上 20 日线仍受压季线";
        trendTone = "warn";
      } else {
        trendVal = "均线粘合震荡";
        trendSub = "均线交织等待区间突破";
        trendTone = "neutral";
      }
    } else if (isFiniteNum(m20)) {
      trendVal = c >= m20 ? "短期站上 20 日线" : "短期位于 20 日线下";
      trendSub = "样本少于 60 日，参考短期均线";
      trendTone = c >= m20 ? "up" : "down";
    }

    // 2. Strength & Position (RSI12 + BOLL %B + BIAS20)
    const r12 = ind.rsi12[i];
    const bu = ind.boll.upper[i];
    const bl = ind.boll.lower[i];
    const bias = ind.bias20[i];
    let strVal = "中性观察";
    let strTone = "neutral";
    if (isFiniteNum(r12)) {
      if (r12 > 70) {
        strVal = "RSI(12) " + r12.toFixed(1) + " · 超买偏热";
        strTone = "warn";
      } else if (r12 >= 55) {
        strVal = "RSI(12) " + r12.toFixed(1) + " · 中性偏强";
        strTone = "up";
      } else if (r12 >= 45) {
        strVal = "RSI(12) " + r12.toFixed(1) + " · 多空平衡";
        strTone = "neutral";
      } else if (r12 >= 30) {
        strVal = "RSI(12) " + r12.toFixed(1) + " · 中性偏弱";
        strTone = "down";
      } else {
        strVal = "RSI(12) " + r12.toFixed(1) + " · 超卖偏冷";
        strTone = "warn";
      }
    }
    let bollPos = "布林带待成形";
    if (isFiniteNum(bu) && isFiniteNum(bl) && bu > bl) {
      const pb = (c - bl) / (bu - bl);
      if (pb > 0.9) bollPos = "逼近布林上轨";
      else if (pb >= 0.5) bollPos = "布林中轨上方";
      else if (pb >= 0.1) bollPos = "布林中轨下方";
      else bollPos = "贴近布林下轨";
    }
    const biasTxt = isFiniteNum(bias) ? "20日乖离 " + (bias >= 0 ? "+" : "") + bias.toFixed(1) + "%" : "";
    const strSub = [bollPos, biasTxt].filter(Boolean).join(" · ");

    // 3. Momentum & Volume (MACD + Vol ratio)
    const dif = ind.macd.dif;
    const dea = ind.macd.dea;
    const hist = ind.macd.hist;
    let momVal = "动能平稳";
    let momTone = "neutral";
    let crossFound = "";
    for (let k = Math.max(1, i - 2); k <= i; k++) {
      if (isFiniteNum(dif[k]) && isFiniteNum(dea[k]) && isFiniteNum(dif[k - 1]) && isFiniteNum(dea[k - 1])) {
        if (dif[k - 1] <= dea[k - 1] && dif[k] > dea[k]) crossFound = "gold";
        else if (dif[k - 1] >= dea[k - 1] && dif[k] < dea[k]) crossFound = "death";
      }
    }
    if (crossFound === "gold") {
      momVal = "MACD 刚现金叉";
      momTone = "up";
    } else if (crossFound === "death") {
      momVal = "MACD 刚现死叉";
      momTone = "down";
    } else if (isFiniteNum(hist[i]) && i > 0 && isFiniteNum(hist[i - 1])) {
      const expanding = Math.abs(hist[i]) >= Math.abs(hist[i - 1]);
      if (hist[i] >= 0) {
        momVal = expanding ? "MACD 正柱放大" : "MACD 正柱收窄";
        momTone = expanding ? "up" : "neutral";
      } else {
        momVal = expanding ? "MACD 负柱放大" : "MACD 负柱收窄";
        momTone = expanding ? "down" : "warn";
      }
    }
    let volSub = "无量能序列（利率/汇率/现货类）";
    if (ind.hasVol && isFiniteNum(bars[i].v) && isFiniteNum(ind.mavol5[i]) && ind.mavol5[i] > 0) {
      const vr = bars[i].v / ind.mavol5[i];
      const vrLbl = vr >= 1.35 ? "明显放量" : vr <= 0.72 ? "缩量观望" : "量能平稳";
      volSub = "较 5 日均量 " + vr.toFixed(2) + "x（" + vrLbl + "）";
    }

    // 4. Risk / Safe Anchor Hint (STRICTLY objective — zero active buy verbs!)
    let riskVal = "节奏温和 · 严守纪律";
    let riskSub = "结合大盘红绿灯与仓位红线";
    let riskTone = "neutral";
    const goldLocked = !!opts.isGoldLockedEffective;
    const anchor = opts.safeAnchor;
    if (goldLocked) {
      riskVal = "黄金红灯观察期";
      riskSub = "仅供趋势跟踪与旧仓参考 · 暂不新买";
      riskTone = "warn";
    } else if (anchor && isFiniteNum(anchor.low) && isFiniteNum(anchor.high)) {
      const midA = (anchor.low + anchor.high) / 2;
      const gap = midA > 0 ? ((c - midA) / midA) * 100 : null;
      if (isFiniteNum(gap)) {
        if (gap <= 0) {
          riskVal = "现价低于基本面参考锚";
          riskSub = "距锚中值 " + gap.toFixed(1) + "% · 结合基本面与大盘水温审慎评估";
          riskTone = "up";
        } else if (gap <= 12) {
          riskVal = "接近参考锚 +" + gap.toFixed(1) + "%";
          riskSub = "估值带附近保持耐心观察";
          riskTone = "neutral";
        } else {
          riskVal = "高于参考锚 +" + gap.toFixed(1) + "%";
          riskSub = "远离安全锚，防范追高回撤";
          riskTone = "warn";
        }
      }
    } else if (isFiniteNum(r12) && r12 > 70) {
      riskVal = "超买偏热 · 注意回撤";
      riskSub = "短线波动风险升温，控制节奏";
      riskTone = "warn";
    } else if (isFiniteNum(r12) && r12 < 30) {
      riskVal = "超卖偏冷 · 耐心观望";
      riskSub = "等待右侧止跌与量能企稳确认";
      riskTone = "down";
    } else if (isFiniteNum(ind.atr14[i]) && c > 0) {
      const atrPct = (ind.atr14[i] / c) * 100;
      if (atrPct >= 3.0) {
        riskVal = "波动放大 · 严控仓位";
        riskSub = "14日均幅约 ±" + atrPct.toFixed(1) + "%";
        riskTone = "warn";
      } else {
        riskVal = "波动温和 · 趋势观察";
        riskSub = "14日均幅约 ±" + atrPct.toFixed(1) + "%";
        riskTone = "neutral";
      }
    }

    const disclaimer = goldLocked
      ? "⚠️ 当前黄金处于风控红灯观察期，本图仅供趋势跟踪与旧仓参考，不构成新买建议。"
      : "💡 技术指标仅反映历史价量与短期强弱，大方向以大盘红绿灯水温与基本面参考锚为准。";

    return {
      pills: [
        { label: "趋势状态", val: trendVal, sub: trendSub, tone: trendTone },
        { label: "强弱与位置", val: strVal, sub: strSub, tone: strTone },
        { label: "量价与动能", val: momVal, sub: volSub, tone: momTone },
        { label: "风控与位置提示", val: riskVal, sub: riskSub, tone: riskTone },
      ],
      disclaimer: disclaimer,
      goldLocked: goldLocked,
    };
  }

  /* ------------------------------------------------------------------------
     4. Dual-Layer HiDPI Canvas Chart Widget (`GIRKline.mount`)
     ------------------------------------------------------------------------ */
  function normalizeAnchor(opts) {
    if (!opts) return null;
    if (opts.safeAnchor && isFiniteNum(opts.safeAnchor.low)) {
      const lo = Number(opts.safeAnchor.low);
      const hi = isFiniteNum(opts.safeAnchor.high) ? Number(opts.safeAnchor.high) : lo;
      return { low: Math.min(lo, hi), high: Math.max(lo, hi) };
    }
    if (isFiniteNum(opts.anchorLow)) {
      const lo = Number(opts.anchorLow);
      const hi = isFiniteNum(opts.anchorHigh) ? Number(opts.anchorHigh) : lo;
      return { low: Math.min(lo, hi), high: Math.max(lo, hi) };
    }
    return null;
  }

  function mount(containerEl, options) {
    if (!containerEl) return null;
    const opts = Object.assign(
      {
        symbolId: "idx_sh000001",
        basePath: undefined,
        height: 390,
        defaultSub: "VOL",
        mode: "compact", // "full" | "compact" | "modal"
        safeAnchor: null,
        anchorLow: null,
        anchorHigh: null,
        goldRedLight: undefined,
        goldLocked: false,
        onSymbolChange: null,
      },
      options || {}
    );

    const state = {
      symbolId: opts.symbolId,
      meta: null,
      series: null,
      bars: [],
      ind: null,
      safeAnchor: normalizeAnchor(opts),
      goldLocked: !!opts.goldLocked,
      colorConv: getColorConvention(),
      overlays: { MA: true, BOLL: false, EMA: false, ANCHOR: true },
      sub: String(opts.defaultSub || "VOL").toUpperCase(),
      timeframe: 66, // 22 | 66 | 130 | 0 (all)
      viewStart: 0,
      viewCount: 66,
      hoverIdx: -1,
      hoverY: -1,
      hoverLocked: false,
      loading: false,
      errorMsg: "",
      destroyed: false,
      layout: null,
    };

    const heightPx = Math.max(290, Number(opts.height) || 390);
    containerEl.innerHTML =
      '<div class="kline-widget">' +
      '<div class="kline-diag-wrap" data-kl="diag"></div>' +
      '<div class="kline-toolbar">' +
      '<div class="kline-tb-group" data-kl="tf-group" role="group" aria-label="时间区间">' +
      '<button type="button" class="kline-chip" data-kl-tf="22">1M</button>' +
      '<button type="button" class="kline-chip active" data-kl-tf="66">3M</button>' +
      '<button type="button" class="kline-chip" data-kl-tf="130">6M</button>' +
      '<button type="button" class="kline-chip" data-kl-tf="0">全部</button>' +
      '<button type="button" class="kline-chip kline-chip-icon" data-kl-zoom="in" title="放大" aria-label="放大">＋</button>' +
      '<button type="button" class="kline-chip kline-chip-icon" data-kl-zoom="out" title="缩小" aria-label="缩小">−</button>' +
      '<button type="button" class="kline-chip kline-chip-icon" data-kl-zoom="reset" title="重置视角" aria-label="重置视角">↺</button>' +
      "</div>" +
      '<div class="kline-tb-group" data-kl="ov-group" role="group" aria-label="主图叠加">' +
      '<button type="button" class="kline-chip active" data-kl-ov="MA">MA均线</button>' +
      '<button type="button" class="kline-chip" data-kl-ov="BOLL">BOLL</button>' +
      '<button type="button" class="kline-chip" data-kl-ov="EMA">EMA</button>' +
      '<button type="button" class="kline-chip active" data-kl-ov="ANCHOR" hidden>安全锚</button>' +
      "</div>" +
      '<div class="kline-tb-group" data-kl="sub-group" role="group" aria-label="副图指标">' +
      '<button type="button" class="kline-chip active" data-kl-sub="VOL">VOL</button>' +
      '<button type="button" class="kline-chip" data-kl-sub="MACD">MACD</button>' +
      '<button type="button" class="kline-chip" data-kl-sub="RSI">RSI</button>' +
      '<button type="button" class="kline-chip" data-kl-sub="KDJ">KDJ</button>' +
      '<button type="button" class="kline-chip" data-kl-sub="ATR">ATR</button>' +
      '<button type="button" class="kline-chip" data-kl-sub="BIAS">BIAS</button>' +
      '<button type="button" class="kline-chip kline-color-toggle" data-kl-color="1" title="切换涨跌配色习惯">红涨绿跌</button>' +
      "</div>" +
      "</div>" +
      '<div class="kline-readout" data-kl="readout">加载 K 线行情中…</div>' +
      '<div class="kline-stage" data-kl="stage" style="height:' + heightPx + 'px;">' +
      '<canvas class="kline-canvas-base" data-kl="base"></canvas>' +
      '<canvas class="kline-canvas-overlay" data-kl="overlay"></canvas>' +
      '<div class="kline-empty-overlay" data-kl="empty" hidden></div>' +
      "</div>" +
      '<div class="kline-foot-note" data-kl="foot"></div>' +
      "</div>";

    const diagEl = containerEl.querySelector('[data-kl="diag"]');
    const readoutEl = containerEl.querySelector('[data-kl="readout"]');
    const stageEl = containerEl.querySelector('[data-kl="stage"]');
    const baseCanvas = containerEl.querySelector('[data-kl="base"]');
    const overlayCanvas = containerEl.querySelector('[data-kl="overlay"]');
    const emptyEl = containerEl.querySelector('[data-kl="empty"]');
    const footEl = containerEl.querySelector('[data-kl="foot"]');
    const anchorBtn = containerEl.querySelector('[data-kl-ov="ANCHOR"]');
    const volBtn = containerEl.querySelector('[data-kl-sub="VOL"]');
    const colorBtn = containerEl.querySelector('[data-kl-color="1"]');

    function isGoldLockedEffective() {
      const globalRed = opts.goldRedLight != null ? !!opts.goldRedLight : isGlobalGoldRedLight();
      if (!globalRed) return false;
      const metaName = state.meta ? state.meta.name : "";
      const serName = state.series ? state.series.name : "";
      return (
        state.goldLocked ||
        !!(state.meta && state.meta.gold_locked) ||
        isGoldAsset(state.symbolId, metaName || serName)
      );
    }

    function syncControlsUI() {
      containerEl.querySelectorAll("[data-kl-tf]").forEach(function (b) {
        const tf = Number(b.getAttribute("data-kl-tf"));
        b.classList.toggle("active", state.timeframe === tf);
      });
      containerEl.querySelectorAll("[data-kl-ov]").forEach(function (b) {
        const key = b.getAttribute("data-kl-ov");
        b.classList.toggle("active", !!state.overlays[key]);
      });
      if (anchorBtn) {
        const hasAnchor = !!(state.safeAnchor && isFiniteNum(state.safeAnchor.low));
        anchorBtn.hidden = !hasAnchor;
        anchorBtn.textContent = isGoldLockedEffective() ? "参考估值带" : "安全锚";
      }
      if (volBtn) {
        const canVol = !!(state.ind && state.ind.hasVol);
        volBtn.disabled = !canVol;
        volBtn.classList.toggle("kline-chip-disabled", !canVol);
      }
      containerEl.querySelectorAll("[data-kl-sub]").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-kl-sub") === state.sub);
      });
      if (colorBtn) {
        colorBtn.textContent = state.colorConv === "us" ? "绿涨红跌" : "红涨绿跌";
      }
    }

    function applyTimeframe(tf) {
      state.timeframe = tf;
      const n = state.bars.length;
      if (n === 0) return;
      const count = tf > 0 ? Math.min(n, tf) : n;
      state.viewCount = Math.max(Math.min(15, n), count);
      state.viewStart = Math.max(0, n - state.viewCount);
      state.hoverIdx = -1;
      state.hoverLocked = false;
      syncControlsUI();
      drawAll();
    }

    function zoomBy(factor, anchorRatio) {
      const n = state.bars.length;
      if (n <= 10) return;
      const ratio = isFiniteNum(anchorRatio) ? anchorRatio : 0.85;
      const oldCount = state.viewCount;
      const nextCount = Math.max(Math.min(15, n), Math.min(n, Math.round(oldCount * factor)));
      if (nextCount === oldCount) return;
      const anchorIdx = state.viewStart + oldCount * ratio;
      let nextStart = Math.round(anchorIdx - nextCount * ratio);
      nextStart = Math.max(0, Math.min(n - nextCount, nextStart));
      state.viewStart = nextStart;
      state.viewCount = nextCount;
      state.timeframe = -1;
      syncControlsUI();
      drawAll();
    }

    function panByBars(deltaBars) {
      const n = state.bars.length;
      if (n === 0 || deltaBars === 0) return;
      const nextStart = Math.max(0, Math.min(n - state.viewCount, state.viewStart + deltaBars));
      if (nextStart === state.viewStart) return;
      state.viewStart = nextStart;
      drawAll();
    }

    function renderDiagnosisBlock() {
      if (!diagEl) return;
      if (!state.bars.length || !state.ind) {
        diagEl.innerHTML = "";
        return;
      }
      const diag = buildDiagnosis(state.bars, state.ind, {
        safeAnchor: state.safeAnchor,
        isGoldLockedEffective: isGoldLockedEffective(),
      });
      if (!diag) {
        diagEl.innerHTML = "";
        return;
      }
      const pillsHtml = diag.pills
        .map(function (p) {
          return (
            '<div class="kline-diag-pill kline-tone-' + escHtml(p.tone) + '">' +
            '<div class="kline-diag-lbl">' + escHtml(p.label) + "</div>" +
            '<div class="kline-diag-val">' + escHtml(p.val) + "</div>" +
            '<div class="kline-diag-sub">' + escHtml(p.sub) + "</div>" +
            "</div>"
          );
        })
        .join("");
      diagEl.innerHTML =
        '<div class="kline-diag-head"><span>小白 10 秒看懂技术面</span>' +
        '<span class="kline-diag-tag">' + (diag.goldLocked ? "风控红灯观察" : "客观价量指标") + "</span></div>" +
        '<div class="kline-diag-grid">' + pillsHtml + "</div>" +
        '<div class="kline-diag-note' + (diag.goldLocked ? " kline-diag-note-warn" : "") + '">' +
        escHtml(diag.disclaimer) + "</div>";
    }

    function updateReadout(barIdx) {
      if (!readoutEl) return;
      if (!state.bars.length) {
        readoutEl.textContent = state.loading ? "加载 K 线行情中…" : (state.errorMsg || "暂无 K 线数据");
        return;
      }
      const idx = barIdx >= 0 && barIdx < state.bars.length ? barIdx : state.bars.length - 1;
      const b = state.bars[idx];
      const prevC = idx > 0 ? state.bars[idx - 1].c : b.o;
      const chgPct = prevC > 0 ? ((b.c - prevC) / prevC) * 100 : null;
      const unit = (state.series && state.series.unit) || (state.meta && state.meta.unit) || "";
      const mkt = (state.series && state.series.market) || (state.meta && state.meta.market) || "";
      const isUp = b.c >= prevC;
      const chgCls = state.colorConv === "us" ? (isUp ? "kl-green" : "kl-red") : (isUp ? "kl-red" : "kl-green");
      const chgStr = isFiniteNum(chgPct) ? (chgPct >= 0 ? "+" : "") + chgPct.toFixed(2) + "%" : "—";
      const nameStr = (state.series && state.series.name) || (state.meta && state.meta.name) || state.symbolId;
      const codeStr = (state.series && state.series.code) || (state.meta && state.meta.code) || "";

      const parts = [
        '<span class="kl-rd-title"><strong>' + escHtml(nameStr) + "</strong>" + (codeStr ? " " + escHtml(codeStr) : "") + "</span>",
        '<span class="kl-rd-date">' + escHtml(b.t) + "</span>",
        "<span>开 <strong>" + fmtPrice(b.o, unit) + "</strong></span>",
        "<span>高 <strong>" + fmtPrice(b.h, unit) + "</strong></span>",
        "<span>低 <strong>" + fmtPrice(b.l, unit) + "</strong></span>",
        '<span>收 <strong class="' + chgCls + '">' + fmtPrice(b.c, unit) + " (" + chgStr + ")</strong></span>",
      ];
      if (state.ind && state.ind.hasVol && isFiniteNum(b.v)) {
        parts.push("<span>量 <strong>" + fmtVol(b.v, mkt) + "</strong></span>");
      }

      const ovParts = [];
      if (state.ind) {
        if (state.overlays.MA) {
          if (isFiniteNum(state.ind.ma5[idx])) ovParts.push('<span class="kl-leg-ma5">MA5:' + fmtPrice(state.ind.ma5[idx], unit) + "</span>");
          if (isFiniteNum(state.ind.ma10[idx])) ovParts.push('<span class="kl-leg-ma10">MA10:' + fmtPrice(state.ind.ma10[idx], unit) + "</span>");
          if (isFiniteNum(state.ind.ma20[idx])) ovParts.push('<span class="kl-leg-ma20">MA20:' + fmtPrice(state.ind.ma20[idx], unit) + "</span>");
          if (isFiniteNum(state.ind.ma60[idx])) ovParts.push('<span class="kl-leg-ma60">MA60:' + fmtPrice(state.ind.ma60[idx], unit) + "</span>");
          if (isFiniteNum(state.ind.ma120[idx])) ovParts.push('<span class="kl-leg-ma120">MA120:' + fmtPrice(state.ind.ma120[idx], unit) + "</span>");
        }
        if (state.overlays.BOLL && isFiniteNum(state.ind.boll.mid[idx])) {
          ovParts.push(
            '<span class="kl-leg-boll">BOLL:' +
              fmtPrice(state.ind.boll.upper[idx], unit) + "/" +
              fmtPrice(state.ind.boll.mid[idx], unit) + "/" +
              fmtPrice(state.ind.boll.lower[idx], unit) + "</span>"
          );
        }
        if (state.overlays.EMA) {
          if (isFiniteNum(state.ind.ema12[idx])) ovParts.push('<span class="kl-leg-ma60">EMA12:' + fmtPrice(state.ind.ema12[idx], unit) + "</span>");
          if (isFiniteNum(state.ind.ema26[idx])) ovParts.push('<span class="kl-leg-ma120">EMA26:' + fmtPrice(state.ind.ema26[idx], unit) + "</span>");
        }
      }

      readoutEl.innerHTML =
        '<div class="kl-rd-row">' + parts.join(" ") + "</div>" +
        (ovParts.length ? '<div class="kl-rd-ov">' + ovParts.join(" ") + "</div>" : "");
    }

    function sizeCanvases() {
      const rect = stageEl.getBoundingClientRect();
      const w = Math.max(240, Math.floor(rect.width));
      const h = Math.max(240, Math.floor(rect.height));
      const dpr = Math.min(window.devicePixelRatio || 1, 3);
      [baseCanvas, overlayCanvas].forEach(function (cv) {
        if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
          cv.width = Math.round(w * dpr);
          cv.height = Math.round(h * dpr);
          cv.style.width = w + "px";
          cv.style.height = h + "px";
        }
      });
      return { w: w, h: h, dpr: dpr };
    }

    function drawLineSeries(ctx, arr, startIdx, endIdx, xFor, yFor, color, lineWidth, dashed) {
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth || 1.25;
      if (dashed) ctx.setLineDash(dashed);
      ctx.beginPath();
      let started = false;
      for (let i = startIdx; i <= endIdx; i++) {
        const v = arr[i];
        if (!isFiniteNum(v)) {
          started = false;
          continue;
        }
        const x = xFor(i);
        const y = yFor(v);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
      ctx.restore();
    }

    function drawBase() {
      if (state.destroyed) return;
      const dims = sizeCanvases();
      const w = dims.w;
      const h = dims.h;
      const dpr = dims.dpr;
      const ctx = baseCanvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const pal = getThemePalette(state.colorConv);
      ctx.fillStyle = pal.bg;
      ctx.fillRect(0, 0, w, h);

      if (!state.bars.length || !state.ind) {
        state.layout = null;
        return;
      }

      const n = state.bars.length;
      const startIdx = Math.max(0, Math.min(n - 1, state.viewStart));
      const endIdx = Math.min(n - 1, startIdx + state.viewCount - 1);
      const visCount = Math.max(1, endIdx - startIdx + 1);
      const unit = (state.series && state.series.unit) || (state.meta && state.meta.unit) || "";
      const mkt = (state.series && state.series.market) || (state.meta && state.meta.market) || "";

      const padL = 10;
      const padR = w < 440 ? 54 : 64;
      const padT = 14;
      const xAxisH = 22;
      const subGap = 14;
      const plotW = Math.max(80, w - padL - padR);
      const availH = h - padT - xAxisH - subGap;
      const mainH = Math.round(availH * 0.68);
      const subH = Math.max(54, availH - mainH);
      const mainTop = padT;
      const mainBot = mainTop + mainH;
      const subTop = mainBot + subGap;
      const subBot = subTop + subH;

      // Compute visible Y bounds for Main Pane
      let pMin = Infinity;
      let pMax = -Infinity;
      for (let i = startIdx; i <= endIdx; i++) {
        const b = state.bars[i];
        if (b.l < pMin) pMin = b.l;
        if (b.h > pMax) pMax = b.h;
        if (state.overlays.MA) {
          [state.ind.ma5[i], state.ind.ma10[i], state.ind.ma20[i], state.ind.ma60[i], state.ind.ma120[i]].forEach(function (v) {
            if (isFiniteNum(v)) {
              if (v < pMin) pMin = v;
              if (v > pMax) pMax = v;
            }
          });
        }
        if (state.overlays.BOLL) {
          if (isFiniteNum(state.ind.boll.upper[i]) && state.ind.boll.upper[i] > pMax) pMax = state.ind.boll.upper[i];
          if (isFiniteNum(state.ind.boll.lower[i]) && state.ind.boll.lower[i] < pMin) pMin = state.ind.boll.lower[i];
        }
        if (state.overlays.EMA) {
          [state.ind.ema12[i], state.ind.ema26[i]].forEach(function (v) {
            if (isFiniteNum(v)) {
              if (v < pMin) pMin = v;
              if (v > pMax) pMax = v;
            }
          });
        }
      }

      // Smart Y-axis clamping for Safe Anchor (include only if within ±35% of visible range)
      let anchorOffscreenHint = "";
      const hasAnchor = !!(state.overlays.ANCHOR && state.safeAnchor && isFiniteNum(state.safeAnchor.low));
      if (hasAnchor && isFiniteNum(pMin) && isFiniteNum(pMax)) {
        const loA = state.safeAnchor.low;
        const hiA = state.safeAnchor.high;
        const midP = (pMin + pMax) / 2;
        if (hiA >= pMin * 0.65 && loA <= pMax * 1.35) {
          pMin = Math.min(pMin, loA);
          pMax = Math.max(pMax, hiA);
        } else if (midP > 0) {
          const dirArrow = hiA < pMin ? "↓" : "↑";
          const aMid = (loA + hiA) / 2;
          const diffPct = ((state.bars[endIdx].c - aMid) / aMid) * 100;
          const rngTxt = loA === hiA ? fmtPrice(loA, unit) : fmtPrice(loA, unit) + "–" + fmtPrice(hiA, unit);
          const lblPref = isGoldLockedEffective() ? "参考估值带（黄金红灯锁·暂不新买）" : "基本面安全锚";
          anchorOffscreenHint = dirArrow + " " + lblPref + " " + rngTxt + "（现价 " + (diffPct >= 0 ? "+" : "") + diffPct.toFixed(1) + "%）";
        }
      }

      if (!Number.isFinite(pMin) || !Number.isFinite(pMax)) return;
      if (pMax === pMin) {
        pMax *= 1.02;
        pMin *= 0.98;
      }
      const pPad = (pMax - pMin) * 0.08;
      pMin -= pPad;
      pMax += pPad;

      const step = plotW / visCount;
      const barW = Math.max(1.5, Math.min(14, step * 0.68));
      const xFor = function (idx) {
        return padL + (idx - startIdx + 0.5) * step;
      };
      const yMain = function (val) {
        return mainTop + ((pMax - val) / (pMax - pMin)) * mainH;
      };

      // Gridlines & Y-Axis Labels (Main Pane)
      ctx.font = '10.5px -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", sans-serif';
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      const mainTicks = 4;
      for (let t = 0; t <= mainTicks; t++) {
        const ratio = t / mainTicks;
        const y = Math.floor(mainTop + ratio * mainH) + 0.5;
        const v = pMax - ratio * (pMax - pMin);
        ctx.strokeStyle = pal.grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(padL + plotW, y);
        ctx.stroke();
        ctx.fillStyle = pal.axisText;
        ctx.fillText(fmtPrice(v, unit), padL + plotW + 6, y);
      }

      // Vertical Gridlines & X-Axis Dates
      const maxXLabels = w < 440 ? 4 : 6;
      const xEvery = Math.max(1, Math.ceil(visCount / maxXLabels));
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      for (let i = startIdx; i <= endIdx; i += xEvery) {
        const x = Math.floor(xFor(i)) + 0.5;
        ctx.strokeStyle = pal.grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, mainTop);
        ctx.lineTo(x, mainBot);
        ctx.moveTo(x, subTop);
        ctx.lineTo(x, subBot);
        ctx.stroke();
        ctx.fillStyle = pal.axisText;
        const dtLbl = state.bars[i].t.slice(5);
        ctx.fillText(dtLbl, Math.max(padL + 18, Math.min(padL + plotW - 18, x)), subBot + 5);
      }

      // Safe Anchor Band Overlay
      if (hasAnchor && !anchorOffscreenHint) {
        const loA = state.safeAnchor.low;
        const hiA = state.safeAnchor.high;
        const goldLocked = isGoldLockedEffective();
        const yHi = Math.max(mainTop, Math.min(mainBot, yMain(hiA)));
        const yLo = Math.max(mainTop, Math.min(mainBot, yMain(loA)));
        const bandH = Math.max(4, Math.abs(yLo - yHi));
        const bandTop = loA === hiA ? yHi - 2 : Math.min(yHi, yLo);

        ctx.save();
        ctx.fillStyle = goldLocked ? pal.anchorLockFill : pal.anchorFill;
        ctx.fillRect(padL, bandTop, plotW, bandH);
        ctx.strokeStyle = goldLocked ? pal.anchorLockStroke : pal.anchorStroke;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(padL, Math.floor(yHi) + 0.5);
        ctx.lineTo(padL + plotW, Math.floor(yHi) + 0.5);
        if (loA !== hiA) {
          ctx.moveTo(padL, Math.floor(yLo) + 0.5);
          ctx.lineTo(padL + plotW, Math.floor(yLo) + 0.5);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        const rngTxt = loA === hiA ? fmtPrice(loA, unit) : fmtPrice(loA, unit) + "–" + fmtPrice(hiA, unit);
        const pillText = goldLocked
          ? "参考估值带（黄金红灯锁·暂不新买） " + rngTxt
          : "安全锚 " + rngTxt;
        ctx.font = '600 10px -apple-system, "PingFang SC", sans-serif';
        ctx.fillStyle = goldLocked ? pal.anchorLockStroke : pal.anchorStroke;
        ctx.textAlign = "left";
        ctx.textBaseline = "bottom";
        ctx.fillText(pillText, padL + 6, Math.max(mainTop + 13, bandTop - 2));
        ctx.restore();
      } else if (anchorOffscreenHint) {
        ctx.save();
        ctx.font = '600 10px -apple-system, "PingFang SC", sans-serif';
        ctx.fillStyle = isGoldLockedEffective() ? pal.anchorLockStroke : pal.anchorStroke;
        ctx.textAlign = "left";
        ctx.textBaseline = "bottom";
        ctx.fillText(anchorOffscreenHint, padL + 6, mainBot - 4);
        ctx.restore();
      }

      // BOLL Ribbon Fill & Lines
      if (state.overlays.BOLL) {
        const bu = state.ind.boll.upper;
        const bm = state.ind.boll.mid;
        const bl = state.ind.boll.lower;
        ctx.save();
        ctx.fillStyle = pal.bollFill;
        ctx.beginPath();
        let firstB = -1;
        let lastB = -1;
        for (let i = startIdx; i <= endIdx; i++) {
          if (isFiniteNum(bu[i]) && isFiniteNum(bl[i])) {
            if (firstB === -1) {
              firstB = i;
              ctx.moveTo(xFor(i), yMain(bu[i]));
            } else {
              ctx.lineTo(xFor(i), yMain(bu[i]));
            }
            lastB = i;
          }
        }
        if (firstB !== -1) {
          for (let i = lastB; i >= firstB; i--) {
            if (isFiniteNum(bl[i])) ctx.lineTo(xFor(i), yMain(bl[i]));
          }
          ctx.closePath();
          ctx.fill();
        }
        ctx.restore();
        drawLineSeries(ctx, bu, startIdx, endIdx, xFor, yMain, pal.bollStroke, 1, null);
        drawLineSeries(ctx, bm, startIdx, endIdx, xFor, yMain, pal.bollStroke, 1, [3, 3]);
        drawLineSeries(ctx, bl, startIdx, endIdx, xFor, yMain, pal.bollStroke, 1, null);
      }

      // Candlesticks
      for (let i = startIdx; i <= endIdx; i++) {
        const b = state.bars[i];
        const cx = Math.floor(xFor(i)) + 0.5;
        const isUp = b.c >= b.o;
        const col = isUp ? pal.up : pal.down;
        const yH = yMain(b.h);
        const yL = yMain(b.l);
        const yO = yMain(b.o);
        const yC = yMain(b.c);

        ctx.strokeStyle = col;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(cx, yH);
        ctx.lineTo(cx, yL);
        ctx.stroke();

        const topY = Math.min(yO, yC);
        const bodyH = Math.max(1.2, Math.abs(yC - yO));
        ctx.fillStyle = col;
        ctx.fillRect(cx - barW / 2, topY, barW, bodyH);
      }

      // Moving Averages & EMA
      if (state.overlays.MA) {
        drawLineSeries(ctx, state.ind.ma5, startIdx, endIdx, xFor, yMain, pal.ma5, 1.2);
        drawLineSeries(ctx, state.ind.ma10, startIdx, endIdx, xFor, yMain, pal.ma10, 1.2);
        drawLineSeries(ctx, state.ind.ma20, startIdx, endIdx, xFor, yMain, pal.ma20, 1.3);
        drawLineSeries(ctx, state.ind.ma60, startIdx, endIdx, xFor, yMain, pal.ma60, 1.3);
        drawLineSeries(ctx, state.ind.ma120, startIdx, endIdx, xFor, yMain, pal.ma120, 1.2);
      }
      if (state.overlays.EMA) {
        drawLineSeries(ctx, state.ind.ema12, startIdx, endIdx, xFor, yMain, pal.ma60, 1.25, [4, 2]);
        drawLineSeries(ctx, state.ind.ema26, startIdx, endIdx, xFor, yMain, pal.ma120, 1.25, [4, 2]);
      }

      // Last Price Dashed Reference Line + Right Pill
      const lastC = state.bars[endIdx].c;
      const lastPrev = endIdx > 0 ? state.bars[endIdx - 1].c : state.bars[endIdx].o;
      const lastCol = lastC >= lastPrev ? pal.up : pal.down;
      const yLast = Math.floor(yMain(lastC)) + 0.5;
      ctx.save();
      ctx.strokeStyle = lastCol;
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 3]);
      ctx.beginPath();
      ctx.moveTo(padL, yLast);
      ctx.lineTo(padL + plotW, yLast);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = lastCol;
      ctx.fillRect(padL + plotW + 2, yLast - 8, padR - 4, 16);
      ctx.fillStyle = "#ffffff";
      ctx.font = '600 10px -apple-system, "SF Pro Display", sans-serif';
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(fmtPrice(lastC, unit), padL + plotW + 5, yLast);
      ctx.restore();

      // Sub-Panel Frame & Divider
      ctx.strokeStyle = pal.axisLine;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padL, Math.floor(mainBot) + 0.5);
      ctx.lineTo(padL + plotW, Math.floor(mainBot) + 0.5);
      ctx.moveTo(padL, Math.floor(subTop) + 0.5);
      ctx.lineTo(padL + plotW, Math.floor(subTop) + 0.5);
      ctx.moveTo(padL, Math.floor(subBot) + 0.5);
      ctx.lineTo(padL + plotW, Math.floor(subBot) + 0.5);
      ctx.stroke();

      // Sub-Panel Drawing
      const sub = state.sub;
      let subLabel = sub;
      if (sub === "VOL" && state.ind.hasVol) {
        let vMax = 0;
        for (let i = startIdx; i <= endIdx; i++) {
          const v = state.bars[i].v;
          if (isFiniteNum(v) && v > vMax) vMax = v;
        }
        vMax = vMax > 0 ? vMax * 1.12 : 1;
        const yVol = function (v) {
          return subBot - (v / vMax) * subH;
        };
        for (let i = startIdx; i <= endIdx; i++) {
          const b = state.bars[i];
          if (!isFiniteNum(b.v)) continue;
          const cx = xFor(i);
          const vy = yVol(b.v);
          ctx.fillStyle = b.c >= b.o ? pal.upFade : pal.downFade;
          ctx.fillRect(cx - barW / 2, vy, barW, Math.max(1, subBot - vy));
        }
        drawLineSeries(ctx, state.ind.mavol5, startIdx, endIdx, xFor, yVol, pal.ma5, 1.1);
        drawLineSeries(ctx, state.ind.mavol10, startIdx, endIdx, xFor, yVol, pal.ma10, 1.1);
        ctx.fillStyle = pal.axisText;
        ctx.font = '10px -apple-system, "PingFang SC", sans-serif';
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText(fmtVol(vMax, mkt), padL + plotW + 6, subTop + 2);
        subLabel = "VOL(5,10) " + fmtVol(state.bars[endIdx].v, mkt);
      } else if (sub === "MACD") {
        let mAbs = 0.001;
        for (let i = startIdx; i <= endIdx; i++) {
          [state.ind.macd.dif[i], state.ind.macd.dea[i], state.ind.macd.hist[i]].forEach(function (v) {
            if (isFiniteNum(v) && Math.abs(v) > mAbs) mAbs = Math.abs(v);
          });
        }
        mAbs *= 1.15;
        const yM = function (v) {
          return subTop + ((mAbs - v) / (2 * mAbs)) * subH;
        };
        const yZero = Math.floor(yM(0)) + 0.5;
        ctx.strokeStyle = pal.grid;
        ctx.beginPath();
        ctx.moveTo(padL, yZero);
        ctx.lineTo(padL + plotW, yZero);
        ctx.stroke();

        for (let i = startIdx; i <= endIdx; i++) {
          const hv = state.ind.macd.hist[i];
          if (!isFiniteNum(hv)) continue;
          const prevHv = i > 0 ? state.ind.macd.hist[i - 1] : 0;
          const exp = !isFiniteNum(prevHv) || Math.abs(hv) >= Math.abs(prevHv);
          const col = hv >= 0 ? (exp ? pal.up : pal.upFade) : (exp ? pal.down : pal.downFade);
          const cx = xFor(i);
          const yh = yM(hv);
          ctx.fillStyle = col;
          ctx.fillRect(cx - barW * 0.38, Math.min(yZero, yh), Math.max(1.2, barW * 0.76), Math.max(1, Math.abs(yh - yZero)));
        }
        drawLineSeries(ctx, state.ind.macd.dif, startIdx, endIdx, xFor, yM, pal.ma10, 1.2);
        drawLineSeries(ctx, state.ind.macd.dea, startIdx, endIdx, xFor, yM, pal.ma20, 1.2);
        ctx.fillStyle = pal.axisText;
        ctx.font = '10px -apple-system, "PingFang SC", sans-serif';
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText(fmtNum(mAbs, 2), padL + plotW + 6, subTop + 2);
        ctx.textBaseline = "bottom";
        ctx.fillText(fmtNum(-mAbs, 2), padL + plotW + 6, subBot - 2);
        subLabel =
          "MACD(12,26,9) DIF:" + fmtNum(state.ind.macd.dif[endIdx], 2) +
          " DEA:" + fmtNum(state.ind.macd.dea[endIdx], 2) +
          " BAR:" + fmtNum(state.ind.macd.hist[endIdx], 2);
      } else if (sub === "RSI") {
        const yR = function (v) {
          return subTop + ((100 - v) / 100) * subH;
        };
        ctx.fillStyle = pal.zoneOver;
        ctx.fillRect(padL, yR(100), plotW, yR(70) - yR(100));
        ctx.fillStyle = pal.zoneUnder;
        ctx.fillRect(padL, yR(30), plotW, yR(0) - yR(30));
        [70, 50, 30].forEach(function (lv) {
          const y = Math.floor(yR(lv)) + 0.5;
          ctx.save();
          ctx.strokeStyle = pal.grid;
          ctx.setLineDash([3, 3]);
          ctx.beginPath();
          ctx.moveTo(padL, y);
          ctx.lineTo(padL + plotW, y);
          ctx.stroke();
          ctx.restore();
          ctx.fillStyle = pal.axisText;
          ctx.font = '10px -apple-system, sans-serif';
          ctx.textAlign = "left";
          ctx.textBaseline = "middle";
          ctx.fillText(String(lv), padL + plotW + 6, y);
        });
        drawLineSeries(ctx, state.ind.rsi6, startIdx, endIdx, xFor, yR, pal.ma5, 1.15);
        drawLineSeries(ctx, state.ind.rsi12, startIdx, endIdx, xFor, yR, pal.ma10, 1.25);
        drawLineSeries(ctx, state.ind.rsi24, startIdx, endIdx, xFor, yR, pal.ma20, 1.15);
        subLabel =
          "RSI(6,12,24) " + fmtNum(state.ind.rsi6[endIdx], 1) +
          " / " + fmtNum(state.ind.rsi12[endIdx], 1) +
          " / " + fmtNum(state.ind.rsi24[endIdx], 1);
      } else if (sub === "KDJ") {
        let kMin = 0;
        let kMax = 100;
        for (let i = startIdx; i <= endIdx; i++) {
          const jv = state.ind.kdj.j[i];
          if (isFiniteNum(jv)) {
            if (jv < kMin) kMin = jv;
            if (jv > kMax) kMax = jv;
          }
        }
        kMin = Math.floor(kMin - 5);
        kMax = Math.ceil(kMax + 5);
        const yK = function (v) {
          return subTop + ((kMax - v) / Math.max(1, kMax - kMin)) * subH;
        };
        [80, 20].forEach(function (lv) {
          const y = Math.floor(yK(lv)) + 0.5;
          ctx.save();
          ctx.strokeStyle = pal.grid;
          ctx.setLineDash([3, 3]);
          ctx.beginPath();
          ctx.moveTo(padL, y);
          ctx.lineTo(padL + plotW, y);
          ctx.stroke();
          ctx.restore();
          ctx.fillStyle = pal.axisText;
          ctx.font = '10px -apple-system, sans-serif';
          ctx.textAlign = "left";
          ctx.textBaseline = "middle";
          ctx.fillText(String(lv), padL + plotW + 6, y);
        });
        drawLineSeries(ctx, state.ind.kdj.k, startIdx, endIdx, xFor, yK, pal.ma5, 1.2);
        drawLineSeries(ctx, state.ind.kdj.d, startIdx, endIdx, xFor, yK, pal.ma10, 1.2);
        drawLineSeries(ctx, state.ind.kdj.j, startIdx, endIdx, xFor, yK, pal.ma20, 1.2);
        subLabel =
          "KDJ(9,3,3) K:" + fmtNum(state.ind.kdj.k[endIdx], 1) +
          " D:" + fmtNum(state.ind.kdj.d[endIdx], 1) +
          " J:" + fmtNum(state.ind.kdj.j[endIdx], 1);
      } else if (sub === "ATR") {
        let aMax = 0;
        let aMin = Infinity;
        for (let i = startIdx; i <= endIdx; i++) {
          const v = state.ind.atr14[i];
          if (isFiniteNum(v)) {
            if (v > aMax) aMax = v;
            if (v < aMin) aMin = v;
          }
        }
        if (!Number.isFinite(aMin) || aMax <= 0) {
          aMin = 0;
          aMax = 1;
        } else if (aMax === aMin) {
          aMax *= 1.1;
          aMin *= 0.9;
        }
        const yA = function (v) {
          return subTop + ((aMax - v) / (aMax - aMin)) * subH;
        };
        drawLineSeries(ctx, state.ind.atr14, startIdx, endIdx, xFor, yA, pal.ma60, 1.4);
        ctx.fillStyle = pal.axisText;
        ctx.font = '10px -apple-system, sans-serif';
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText(fmtPrice(aMax, unit), padL + plotW + 6, subTop + 2);
        const curA = state.ind.atr14[endIdx];
        const atrPct = isFiniteNum(curA) && lastC > 0 ? "（日均振幅 ±" + ((curA / lastC) * 100).toFixed(2) + "%）" : "";
        subLabel = "ATR(14) " + fmtPrice(curA, unit) + atrPct;
      } else if (sub === "BIAS") {
        let bAbs = 5;
        for (let i = startIdx; i <= endIdx; i++) {
          const v = state.ind.bias20[i];
          if (isFiniteNum(v) && Math.abs(v) > bAbs) bAbs = Math.abs(v);
        }
        bAbs = Math.ceil(bAbs * 1.15);
        const yB = function (v) {
          return subTop + ((bAbs - v) / (2 * bAbs)) * subH;
        };
        const yZ = Math.floor(yB(0)) + 0.5;
        ctx.strokeStyle = pal.grid;
        ctx.beginPath();
        ctx.moveTo(padL, yZ);
        ctx.lineTo(padL + plotW, yZ);
        ctx.stroke();
        drawLineSeries(ctx, state.ind.bias20, startIdx, endIdx, xFor, yB, pal.ma20, 1.35);
        ctx.fillStyle = pal.axisText;
        ctx.font = '10px -apple-system, sans-serif';
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText("+" + bAbs + "%", padL + plotW + 6, subTop + 2);
        ctx.textBaseline = "bottom";
        ctx.fillText("-" + bAbs + "%", padL + plotW + 6, subBot - 2);
        const curB = state.ind.bias20[endIdx];
        subLabel = "BIAS(20) " + (isFiniteNum(curB) ? (curB >= 0 ? "+" : "") + curB.toFixed(2) + "%" : "—");
      }

      // Sub-Panel Legend Badge
      ctx.fillStyle = pal.axisText;
      ctx.font = '600 10px -apple-system, "PingFang SC", sans-serif';
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(subLabel, padL + 4, subTop + 3);

      state.layout = {
        w: w,
        h: h,
        dpr: dpr,
        padL: padL,
        padR: padR,
        plotW: plotW,
        mainTop: mainTop,
        mainBot: mainBot,
        mainH: mainH,
        subTop: subTop,
        subBot: subBot,
        startIdx: startIdx,
        endIdx: endIdx,
        visCount: visCount,
        step: step,
        pMin: pMin,
        pMax: pMax,
        unit: unit,
      };
    }

    function drawOverlay() {
      if (state.destroyed) return;
      const ctx = overlayCanvas.getContext("2d");
      if (!ctx) return;
      const L = state.layout;
      if (!L) {
        ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
        return;
      }
      ctx.setTransform(L.dpr, 0, 0, L.dpr, 0, 0);
      ctx.clearRect(0, 0, L.w, L.h);

      if (state.hoverIdx < L.startIdx || state.hoverIdx > L.endIdx) return;
      const b = state.bars[state.hoverIdx];
      if (!b) return;
      const pal = getThemePalette(state.colorConv);
      const cx = Math.floor(L.padL + (state.hoverIdx - L.startIdx + 0.5) * L.step) + 0.5;
      const cy = state.hoverY >= L.mainTop && state.hoverY <= L.mainBot
        ? Math.floor(state.hoverY) + 0.5
        : Math.floor(L.mainTop + ((L.pMax - b.c) / (L.pMax - L.pMin)) * L.mainH) + 0.5;

      ctx.save();
      ctx.strokeStyle = pal.crosshair;
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(cx, L.mainTop);
      ctx.lineTo(cx, L.subBot);
      if (cy >= L.mainTop && cy <= L.mainBot) {
        ctx.moveTo(L.padL, cy);
        ctx.lineTo(L.padL + L.plotW, cy);
      }
      ctx.stroke();
      ctx.setLineDash([]);

      // Price Axis Pill
      if (cy >= L.mainTop && cy <= L.mainBot) {
        const hoverPrice = L.pMax - ((cy - L.mainTop) / L.mainH) * (L.pMax - L.pMin);
        ctx.fillStyle = pal.pillBg;
        ctx.fillRect(L.padL + L.plotW + 2, cy - 8, L.padR - 4, 16);
        ctx.fillStyle = pal.pillText;
        ctx.font = '600 10px -apple-system, "SF Pro Display", sans-serif';
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(fmtPrice(hoverPrice, L.unit), L.padL + L.plotW + 5, cy);
      }

      // Date Axis Pill
      const pillW = 74;
      const pillX = Math.max(L.padL, Math.min(L.padL + L.plotW - pillW, cx - pillW / 2));
      ctx.fillStyle = pal.pillBg;
      ctx.fillRect(pillX, L.subBot + 2, pillW, 17);
      ctx.fillStyle = pal.pillText;
      ctx.font = '600 10px -apple-system, "SF Pro Display", sans-serif';
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(b.t, pillX + pillW / 2, L.subBot + 10.5);
      ctx.restore();
    }

    function drawAll() {
      drawBase();
      drawOverlay();
      updateReadout(state.hoverIdx >= 0 ? state.hoverIdx : state.bars.length - 1);
    }

    function showEmpty(msg) {
      state.errorMsg = msg;
      if (emptyEl) {
        emptyEl.hidden = false;
        emptyEl.innerHTML =
          '<div class="kline-empty-title">暂未加载到该标的 K 线分片</div>' +
          '<div class="kline-empty-sub">' + escHtml(msg) + "</div>";
      }
      if (footEl) footEl.textContent = "";
      if (diagEl) diagEl.innerHTML = "";
      updateReadout(-1);
      drawBase();
    }

    function hideEmpty() {
      state.errorMsg = "";
      if (emptyEl) emptyEl.hidden = true;
    }

    function load(symbolId, extraMeta) {
      state.symbolId = String(symbolId || "").trim();
      if (extraMeta) {
        const nextAnchor = normalizeAnchor(extraMeta);
        state.safeAnchor = nextAnchor;
        if (typeof extraMeta.goldLocked === "boolean") state.goldLocked = extraMeta.goldLocked;
        else state.goldLocked = false;
      }
      state.loading = true;
      state.bars = [];
      state.ind = null;
      state.hoverIdx = -1;
      state.hoverLocked = false;
      hideEmpty();
      updateReadout(-1);

      const reqSym = state.symbolId;
      return loadSeries(reqSym, opts.basePath).then(function (res) {
        if (state.destroyed || state.symbolId !== reqSym) return;
        state.loading = false;
        if (res.status !== "ok" || !res.bars.length) {
          const reason =
            res.status === "no_manifest"
              ? "当前静态站点尚未包含 K 线行情分片文件，下个班次自动刷新后将即时展示交互 K 线。"
              : "该标的暂缺可用历史 K 线数据（可能受休市或跨源接口波动影响），文字档案与基本面数据不受影响。";
          showEmpty(reason);
          return;
        }
        state.meta = res.meta;
        state.series = res.series;
        state.bars = res.bars;
        state.ind = computeIndicators(res.bars);
        if (!state.ind.hasVol && state.sub === "VOL") {
          state.sub = "MACD";
        }
        hideEmpty();
        if (footEl) {
          const prov = (res.series && res.series.provider) || (res.meta && res.meta.provider) || "多源官库";
          const lastDt = res.bars[res.bars.length - 1].t;
          const hint = opts.mode === "compact"
            ? "拖拽平移 · Ctrl/⌘+滚轮或点击＋/−缩放 · 手机端长按查价"
            : "拖拽平移 · 滚轮/双指缩放 · 点击或长按查看逐日价量";
          footEl.textContent = "数据截止 " + lastDt + " · 共 " + res.bars.length + " 交易日（来源：" + prov + "）｜" + hint;
        }
        renderDiagnosisBlock();
        applyTimeframe(state.timeframe > 0 ? state.timeframe : 66);
        if (typeof opts.onSymbolChange === "function") {
          opts.onSymbolChange(res.meta, res.series);
        }
      });
    }

    // Toolbar Event Listeners
    containerEl.addEventListener("click", function (e) {
      const tfBtn = e.target.closest("[data-kl-tf]");
      if (tfBtn) {
        applyTimeframe(Number(tfBtn.getAttribute("data-kl-tf")));
        return;
      }
      const zBtn = e.target.closest("[data-kl-zoom]");
      if (zBtn) {
        const act = zBtn.getAttribute("data-kl-zoom");
        if (act === "in") zoomBy(0.75, 0.85);
        else if (act === "out") zoomBy(1.33, 0.85);
        else applyTimeframe(66);
        return;
      }
      const ovBtn = e.target.closest("[data-kl-ov]");
      if (ovBtn) {
        const key = ovBtn.getAttribute("data-kl-ov");
        state.overlays[key] = !state.overlays[key];
        syncControlsUI();
        drawAll();
        return;
      }
      const subBtn = e.target.closest("[data-kl-sub]");
      if (subBtn && !subBtn.disabled) {
        state.sub = subBtn.getAttribute("data-kl-sub");
        syncControlsUI();
        drawAll();
        return;
      }
      if (e.target.closest("[data-kl-color]")) {
        setColorConvention(state.colorConv === "cn" ? "us" : "cn");
      }
    });

    // Pointer / Mouse Crosshair, Drag Pan & Wheel Zoom
    let dragging = false;
    let dragStartX = 0;
    let dragOrigStart = 0;

    function idxFromClientX(clientX) {
      const L = state.layout;
      if (!L) return -1;
      const rect = baseCanvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const raw = Math.floor((x - L.padL) / L.step) + L.startIdx;
      return Math.max(L.startIdx, Math.min(L.endIdx, raw));
    }

    baseCanvas.addEventListener("mousedown", function (e) {
      if (!state.layout) return;
      dragging = true;
      dragStartX = e.clientX;
      dragOrigStart = state.viewStart;
    });
    window.addEventListener("mousemove", function (e) {
      if (state.destroyed || !dragging || !state.layout) return;
      const dx = e.clientX - dragStartX;
      const shift = Math.round(-dx / state.layout.step);
      const next = Math.max(0, Math.min(state.bars.length - state.viewCount, dragOrigStart + shift));
      if (next !== state.viewStart) {
        state.viewStart = next;
        drawAll();
      }
    });
    window.addEventListener("mouseup", function () {
      dragging = false;
    });

    baseCanvas.addEventListener("mousemove", function (e) {
      if (dragging || !state.layout) return;
      const rect = baseCanvas.getBoundingClientRect();
      state.hoverIdx = idxFromClientX(e.clientX);
      state.hoverY = e.clientY - rect.top;
      drawOverlay();
      updateReadout(state.hoverIdx);
    });
    baseCanvas.addEventListener("mouseleave", function () {
      if (state.hoverLocked) return;
      state.hoverIdx = -1;
      state.hoverY = -1;
      drawOverlay();
      updateReadout(state.bars.length - 1);
    });

    baseCanvas.addEventListener(
      "wheel",
      function (e) {
        if (!state.layout) return;
        const allowDirect = opts.mode === "full" || opts.mode === "modal";
        if (!allowDirect && !e.ctrlKey && !e.metaKey) return;
        e.preventDefault();
        const rect = baseCanvas.getBoundingClientRect();
        const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left - state.layout.padL) / state.layout.plotW));
        zoomBy(e.deltaY > 0 ? 1.18 : 0.84, ratio);
      },
      { passive: false }
    );

    // Mobile Touch: pan-y preserved; horizontal drag pans; pinch zooms; tap/hold scrubs top readout
    let touchMode = ""; // "pan" | "scrub" | "pinch"
    let touchStartX = 0;
    let touchStartY = 0;
    let touchOrigStart = 0;
    let pinchStartDist = 0;
    let holdTimer = 0;

    baseCanvas.addEventListener(
      "touchstart",
      function (e) {
        if (!state.layout) return;
        window.clearTimeout(holdTimer);
        if (e.touches.length === 2) {
          touchMode = "pinch";
          const dx = e.touches[0].clientX - e.touches[1].clientX;
          const dy = e.touches[0].clientY - e.touches[1].clientY;
          pinchStartDist = Math.hypot(dx, dy) || 1;
          return;
        }
        if (e.touches.length === 1) {
          touchMode = "";
          const t = e.touches[0];
          touchStartX = t.clientX;
          touchStartY = t.clientY;
          touchOrigStart = state.viewStart;
          holdTimer = window.setTimeout(function () {
            touchMode = "scrub";
            state.hoverLocked = true;
            const rect = baseCanvas.getBoundingClientRect();
            state.hoverIdx = idxFromClientX(t.clientX);
            state.hoverY = t.clientY - rect.top;
            drawOverlay();
            updateReadout(state.hoverIdx);
          }, 210);
        }
      },
      { passive: true }
    );

    baseCanvas.addEventListener(
      "touchmove",
      function (e) {
        if (!state.layout) return;
        if (touchMode === "pinch" && e.touches.length === 2) {
          const dx = e.touches[0].clientX - e.touches[1].clientX;
          const dy = e.touches[0].clientY - e.touches[1].clientY;
          const dist = Math.hypot(dx, dy) || 1;
          if (Math.abs(dist - pinchStartDist) > 12) {
            zoomBy(pinchStartDist / dist, 0.5);
            pinchStartDist = dist;
          }
          return;
        }
        if (e.touches.length === 1) {
          const t = e.touches[0];
          const dx = t.clientX - touchStartX;
          const dy = t.clientY - touchStartY;
          if (!touchMode && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
            window.clearTimeout(holdTimer);
            touchMode = Math.abs(dx) > Math.abs(dy) ? "pan" : "scroll";
          }
          if (touchMode === "scrub") {
            const rect = baseCanvas.getBoundingClientRect();
            state.hoverIdx = idxFromClientX(t.clientX);
            state.hoverY = t.clientY - rect.top;
            drawOverlay();
            updateReadout(state.hoverIdx);
          } else if (touchMode === "pan") {
            const shift = Math.round(-dx / state.layout.step);
            const next = Math.max(0, Math.min(state.bars.length - state.viewCount, touchOrigStart + shift));
            if (next !== state.viewStart) {
              state.viewStart = next;
              drawAll();
            }
          }
        }
      },
      { passive: true }
    );

    baseCanvas.addEventListener("touchend", function (e) {
      window.clearTimeout(holdTimer);
      if (touchMode === "" && e.changedTouches && e.changedTouches.length === 1 && state.layout) {
        const t = e.changedTouches[0];
        const rect = baseCanvas.getBoundingClientRect();
        state.hoverLocked = true;
        state.hoverIdx = idxFromClientX(t.clientX);
        state.hoverY = t.clientY - rect.top;
        drawOverlay();
        updateReadout(state.hoverIdx);
      }
      touchMode = "";
    });

    // ResizeObserver for instant reflow (including inside modals)
    let resizeRaf = 0;
    let ro = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(function () {
        if (state.destroyed) return;
        window.cancelAnimationFrame(resizeRaf);
        resizeRaf = window.requestAnimationFrame(function () {
          if (!state.destroyed && stageEl.offsetWidth > 0) drawAll();
        });
      });
      ro.observe(stageEl);
    }

    function onColorChange(e) {
      state.colorConv = (e.detail && e.detail.mode) || getColorConvention();
      syncControlsUI();
      drawAll();
    }
    window.addEventListener("gir:kline-color", onColorChange);

    const instance = {
      load: load,
      resize: function () {
        if (!state.destroyed && stageEl.offsetWidth > 0) drawAll();
      },
      repaint: function () {
        if (!state.destroyed && stageEl.offsetWidth > 0) drawAll();
      },
      getState: function () {
        return {
          symbolId: state.symbolId,
          barsCount: state.bars.length,
          sub: state.sub,
          colorConv: state.colorConv,
        };
      },
      destroy: function () {
        state.destroyed = true;
        activeInstances.delete(instance);
        if (ro) ro.disconnect();
        window.removeEventListener("gir:kline-color", onColorChange);
        containerEl.innerHTML = "";
      },
    };
    activeInstances.add(instance);
    syncControlsUI();
    if (opts.symbolId) {
      load(opts.symbolId, opts);
    }
    return instance;
  }

  // Global Theme MutationObserver -> instant repaint across all mounted charts
  const themeObserver = new MutationObserver(function () {
    activeInstances.forEach(function (inst) {
      inst.repaint();
    });
  });
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  /* ------------------------------------------------------------------------
     5. Full-Screen Charts Terminal (`charts.html`) & Deck Auto-Mount
     ------------------------------------------------------------------------ */
  function readMetaBridge() {
    const el = document.getElementById("kline-meta-bridge");
    if (!el) return {};
    try {
      const obj = JSON.parse(el.textContent || "{}");
      return obj && typeof obj === "object" ? obj : {};
    } catch (_) {
      return {};
    }
  }

  function initChartsTerminal(rootEl) {
    if (!rootEl) return;
    const searchInput = document.getElementById("kline-search");
    const clearBtn = document.getElementById("kline-search-clear");
    const listEl = document.getElementById("kline-symbol-list");
    const countEl = document.getElementById("kline-list-count");
    const mountEl = document.getElementById("kline-terminal-mount");
    const headTitle = document.getElementById("kline-term-title");
    const headSub = document.getElementById("kline-term-sub");
    const headStar = document.getElementById("kline-term-star");
    const groupBtns = Array.from(rootEl.querySelectorAll("[data-chart-group]"));
    const metaBridge = readMetaBridge();

    let catalog = [];
    let activeGroup = "a_index";
    let searchQ = "";
    let activeSym = "idx_sh000001";
    let chartInst = null;

    function getWatchSet() {
      if (window.GIRWatchlist && typeof window.GIRWatchlist.getAll === "function") {
        const set = new Set();
        window.GIRWatchlist.getAll().forEach(function (w) {
          if (w.klineId) set.add(w.klineId);
          if (w.id) set.add(w.id);
          if (w.code) {
            set.add("stk_" + w.code);
            set.add("etf_" + w.code);
          }
        });
        return set;
      }
      return new Set();
    }

    function groupMatches(item, grp, watchSet) {
      if (grp === "all") return true;
      if (grp === "watchlist") {
        return watchSet.has(item.id) || (item.dossier_key && watchSet.has(item.dossier_key)) || (item.code && (watchSet.has("stk_" + item.code) || watchSet.has("etf_" + item.code)));
      }
      if (grp === "gold_macro") return item.group === "gold_metal" || item.group === "macro_cmd";
      if (grp === "etfs") return String(item.id || "").startsWith("etf_") || String(item.group || "").indexOf("etf") !== -1;
      if (grp === "stocks") return String(item.id || "").startsWith("stk_") || String(item.group || "").indexOf("stock") !== -1;
      return item.group === grp;
    }

    function selectSymbol(symId, updateHash) {
      activeSym = symId;
      const item = catalog.find(function (c) { return c.id === symId; }) || null;
      const bridge = metaBridge[symId] || (item && item.dossier_key ? metaBridge[item.dossier_key] : null) || {};
      if (headTitle) {
        headTitle.textContent = item ? item.name + " (" + item.code + ")" : symId;
      }
      if (headSub) {
        const chg = item && isFiniteNum(item.change_pct)
          ? (item.change_pct >= 0 ? "+" : "") + item.change_pct.toFixed(2) + "%"
          : "";
        const price = item && isFiniteNum(item.latest_close) ? fmtPrice(item.latest_close, item.unit) : "";
        headSub.textContent = item
          ? [price, chg, item.latest_date ? "截止 " + item.latest_date : "", item.provider || ""].filter(Boolean).join(" · ")
          : "交互 K 线与技术指标";
      }
      if (headStar && window.GIRWatchlist) {
        const isStarred = getWatchSet().has(symId);
        headStar.textContent = isStarred ? "★ 已自选" : "☆ 加自选";
        headStar.classList.toggle("active", isStarred);
        headStar.setAttribute("data-star-kline", symId);
      }
      if (!chartInst) {
        chartInst = mount(mountEl, {
          symbolId: symId,
          height: window.innerWidth >= 960 ? 500 : 380,
          mode: "full",
          anchorLow: bridge.anchor_low,
          anchorHigh: bridge.anchor_high,
          goldLocked: !!bridge.gold_locked,
        });
      } else {
        chartInst.load(symId, {
          anchorLow: bridge.anchor_low,
          anchorHigh: bridge.anchor_high,
          goldLocked: !!bridge.gold_locked,
        });
      }
      if (listEl) {
        listEl.querySelectorAll(".kline-sym-row").forEach(function (r) {
          r.classList.toggle("active", r.getAttribute("data-sym-id") === symId);
        });
      }
      if (updateHash && history.replaceState) {
        try {
          history.replaceState(null, "", "#sym=" + encodeURIComponent(symId));
        } catch (_) {}
      }
    }

    function renderSidebar() {
      if (!listEl) return;
      const watchSet = getWatchSet();
      const tokens = searchQ.trim().toLowerCase().split(/\s+/).filter(Boolean);
      const filtered = catalog.filter(function (item) {
        if (tokens.length === 0 && !groupMatches(item, activeGroup, watchSet)) return false;
        if (tokens.length > 0) {
          const hay = (
            (item.name || "") + " " + (item.code || "") + " " + (item.id || "") + " " +
            (item.group || "") + " " + (item.market || "")
          ).toLowerCase();
          return tokens.every(function (tk) { return hay.indexOf(tk) !== -1; });
        }
        return true;
      });

      groupBtns.forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-chart-group") === activeGroup && tokens.length === 0);
      });
      if (countEl) {
        countEl.textContent = "共 " + filtered.length + " 项标的";
      }
      if (filtered.length === 0) {
        listEl.innerHTML =
          '<div class="kline-list-empty">' +
          (activeGroup === "watchlist"
            ? "自选清单为空：点击任意标的旁的 ☆ 即可加入自选"
            : "未找到匹配标的，试试输入「上证」「标普」「黄金」「510300」或「NVDA」") +
          "</div>";
        return;
      }
      const cap = filtered.slice(0, 120);
      listEl.innerHTML = cap
        .map(function (item) {
          const isAct = item.id === activeSym;
          const isStar = watchSet.has(item.id) || (item.dossier_key && watchSet.has(item.dossier_key));
          const chg = isFiniteNum(item.change_pct) ? item.change_pct : null;
          const chgCls = chg == null ? "" : chg >= 0 ? "chg-up" : "chg-dn";
          const chgTxt = chg == null ? "—" : (chg >= 0 ? "+" : "") + chg.toFixed(2) + "%";
          const pTxt = isFiniteNum(item.latest_close) ? fmtPrice(item.latest_close, item.unit) : "待核";
          return (
            '<div class="kline-sym-row' + (isAct ? " active" : "") + '" data-sym-id="' + escHtml(item.id) + '" role="button" tabindex="0">' +
            '<div class="kline-sym-main">' +
            '<div class="kline-sym-name">' + escHtml(item.name) + "</div>" +
            '<div class="kline-sym-code">' + escHtml(item.code) + "</div>" +
            "</div>" +
            '<div class="kline-sym-right">' +
            '<div class="kline-sym-price">' + escHtml(pTxt) + "</div>" +
            '<div class="kline-sym-chg ' + chgCls + '">' + escHtml(chgTxt) + "</div>" +
            "</div>" +
            '<button type="button" class="star-btn' + (isStar ? " active" : "") + '" data-watch-toggle="1" ' +
            'data-watch-kind="' + (String(item.id).startsWith("etf_") ? "etf" : String(item.id).startsWith("stk_") ? "stock" : "index") + '" ' +
            'data-watch-id="' + escHtml(item.dossier_key || item.code || item.id) + '" ' +
            'data-watch-kline="' + escHtml(item.id) + '" ' +
            'data-watch-name="' + escHtml(item.name) + '" ' +
            'data-watch-code="' + escHtml(item.code) + '" ' +
            'aria-label="切换自选">' + (isStar ? "★" : "☆") + "</button>" +
            "</div>"
          );
        })
        .join("");
    }

    function applyTerminalHash() {
      const raw = (window.location.hash || "").replace(/^#/, "").trim();
      if (!raw) return;
      raw.split("&").forEach(function (pair) {
        const eq = pair.indexOf("=");
        if (eq <= 0) return;
        const k = decodeURIComponent(pair.slice(0, eq));
        const v = decodeURIComponent(pair.slice(eq + 1));
        if (k === "sym" && v) {
          const found = catalog.find(function (c) { return c.id === v || c.code === v || c.dossier_key === v; });
          if (found) {
            activeSym = found.id;
            if (found.group === "gold_metal" || found.group === "macro_cmd") activeGroup = "gold_macro";
            else if (String(found.id).startsWith("etf_")) activeGroup = "etfs";
            else if (String(found.id).startsWith("stk_")) activeGroup = "stocks";
            else if (found.group) activeGroup = found.group;
          }
        } else if (k === "q" && v) {
          searchQ = v;
          if (searchInput) searchInput.value = v;
          if (clearBtn) clearBtn.hidden = false;
        }
      });
    }

    groupBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        activeGroup = btn.getAttribute("data-chart-group") || "a_index";
        searchQ = "";
        if (searchInput) searchInput.value = "";
        if (clearBtn) clearBtn.hidden = true;
        renderSidebar();
      });
    });

    if (searchInput) {
      searchInput.addEventListener("input", function () {
        searchQ = searchInput.value;
        if (clearBtn) clearBtn.hidden = !searchQ;
        renderSidebar();
      });
    }
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        searchQ = "";
        if (searchInput) {
          searchInput.value = "";
          searchInput.focus();
        }
        clearBtn.hidden = true;
        renderSidebar();
      });
    }

    if (listEl) {
      listEl.addEventListener("click", function (e) {
        if (e.target.closest("[data-watch-toggle]")) return;
        const row = e.target.closest(".kline-sym-row[data-sym-id]");
        if (row) selectSymbol(row.getAttribute("data-sym-id"), true);
      });
      listEl.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          const row = e.target.closest(".kline-sym-row[data-sym-id]");
          if (row) {
            e.preventDefault();
            selectSymbol(row.getAttribute("data-sym-id"), true);
          }
        }
      });
    }

    if (headStar) {
      headStar.addEventListener("click", function () {
        if (!window.GIRWatchlist) return;
        const item = catalog.find(function (c) { return c.id === activeSym; });
        if (!item) return;
        const kind = String(item.id).startsWith("etf_") ? "etf" : String(item.id).startsWith("stk_") ? "stock" : "index";
        window.GIRWatchlist.toggle({
          kind: kind,
          id: item.dossier_key || item.code || item.id,
          klineId: item.id,
          code: item.code,
          name: item.name,
        });
      });
    }

    window.addEventListener("gir:watchlist-change", function () {
      renderSidebar();
      if (headStar) {
        const isStarred = getWatchSet().has(activeSym);
        headStar.textContent = isStarred ? "★ 已自选" : "☆ 加自选";
        headStar.classList.toggle("active", isStarred);
      }
    });

    loadManifest().then(function (manifest) {
      if (manifest && Array.isArray(manifest.catalog) && manifest.catalog.length > 0) {
        catalog = manifest.catalog.map(function (c, idx) {
          return Object.assign({ _order: idx }, c);
        });
        const hasAnyPriority = catalog.some(function (c) { return isFiniteNum(c.priority); });
        if (hasAnyPriority) {
          catalog.sort(function (a, b) {
            const pa = isFiniteNum(a.priority) ? a.priority : 9999;
            const pb = isFiniteNum(b.priority) ? b.priority : 9999;
            if (pa !== pb) return pa - pb;
            return a._order - b._order;
          });
        }
      }
      applyTerminalHash();
      renderSidebar();
      selectSymbol(activeSym, false);
      window.addEventListener("hashchange", function () {
        applyTerminalHash();
        renderSidebar();
        selectSymbol(activeSym, false);
      });
    });
  }

  function initDeclarativeDecks() {
    // 1. Homepage 4-Tab K-Line Deck & Daily Report K-Line Strips
    document.querySelectorAll("[data-kline-deck]").forEach(function (deck) {
      const mountTarget = deck.querySelector("[data-kline-deck-mount]");
      if (!mountTarget) return;
      const tabBtns = Array.from(deck.querySelectorAll("[data-deck-tab]"));
      const panels = Array.from(deck.querySelectorAll("[data-deck-panel]"));
      const fullLink = deck.querySelector("[data-deck-full-link]");
      const basePrefix = getBasePrefix();
      const firstSymBtn = deck.querySelector("[data-deck-sym]");
      const initSym = (firstSymBtn && firstSymBtn.getAttribute("data-deck-sym")) || mountTarget.getAttribute("data-init-sym") || "idx_sh000001";
      const h = Number(mountTarget.getAttribute("data-kline-height")) || 370;

      const inst = mount(mountTarget, {
        symbolId: initSym,
        height: h,
        mode: "compact",
      });

      function activateSymbol(symId, targetTab) {
        if (targetTab) {
          tabBtns.forEach(function (b) {
            b.classList.toggle("active", b.getAttribute("data-deck-tab") === targetTab);
          });
          panels.forEach(function (p) {
            p.hidden = p.getAttribute("data-deck-panel") !== targetTab;
          });
        }
        deck.querySelectorAll("[data-deck-sym]").forEach(function (b) {
          b.classList.toggle("active", b.getAttribute("data-deck-sym") === symId);
        });
        if (fullLink) {
          fullLink.setAttribute("href", basePrefix + "charts.html#sym=" + encodeURIComponent(symId));
        }
        inst.load(symId);
      }

      tabBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          const tabKey = btn.getAttribute("data-deck-tab");
          const panel = deck.querySelector('[data-deck-panel="' + tabKey + '"]');
          const firstBtn = panel ? panel.querySelector("[data-deck-sym]") : null;
          activateSymbol(firstBtn ? firstBtn.getAttribute("data-deck-sym") : initSym, tabKey);
        });
      });

      deck.addEventListener("click", function (e) {
        const sBtn = e.target.closest("[data-deck-sym]");
        if (sBtn) {
          activateSymbol(sBtn.getAttribute("data-deck-sym"));
        }
      });

      deck._girActivateSym = activateSymbol;
    });

    // 2. Delegated [data-kline-jump] buttons (on homepage market cards & commodity chips)
    document.addEventListener("click", function (e) {
      const btn = e.target.closest("[data-kline-jump]");
      if (!btn) return;
      const symId = btn.getAttribute("data-kline-jump");
      const tabKey = btn.getAttribute("data-kline-tab") || "";
      const homeDeck = document.querySelector('[data-kline-deck="home"]');
      if (homeDeck && typeof homeDeck._girActivateSym === "function" && symId) {
        e.preventDefault();
        homeDeck._girActivateSym(symId, tabKey || undefined);
        const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        homeDeck.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      }
    });

    // 3. Full-screen Charts Terminal (charts.html)
    const termRoot = document.querySelector("[data-kline-terminal]");
    if (termRoot) {
      initChartsTerminal(termRoot);
    }
  }

  window.GIRKline = {
    mount: mount,
    loadManifest: loadManifest,
    loadSeries: loadSeries,
    isGoldAsset: isGoldAsset,
    getColorConvention: getColorConvention,
    setColorConvention: setColorConvention,
    initChartsTerminal: initChartsTerminal,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDeclarativeDecks);
  } else {
    initDeclarativeDecks();
  }
})();
