/* ==========================================================================
   Global Investment Research Portal — Interactive Client Engine (Zero Deps)
   Features: Obsidian Dark Mode, Font Scaler, Reading Progress & Back-to-Top,
             TOC ScrollSpy (rAF) & Mobile Drawer, Command-K Quick Jump Palette,
             Chart Lightbox + Shortcuts, 231-Stock Screener, Scorecard Tabs,
             Multi-Facet Archive Search, Dual-Mode Channel Filter & Four-Bucket
             Jump, Global ETF Radar + Channel Detail ETF Modal, Glossary Popover
             & Beginner Guide Search
   ========================================================================== */
(function () {
  "use strict";

  const root = document.documentElement;
  const prefersReducedMotion =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function safeDecode(s) {
    try {
      return decodeURIComponent(s);
    } catch (_) {
      return s;
    }
  }

  function isEditableElement(el) {
    if (!el) return false;
    const tag = (el.tagName || "").toUpperCase();
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || !!el.isContentEditable;
  }

  function isFiniteNum(v) {
    return typeof v === "number" && isFinite(v);
  }

  /* ------------------------------------------------------------------------
     1. Theme Toggle (SVG-Aware — Preserves Inner <svg> Icons)
     ------------------------------------------------------------------------ */
  function getTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function applyTheme(theme) {
    const next = theme === "dark" ? "dark" : "light";
    root.setAttribute("data-theme", next);
    try {
      localStorage.setItem("gir_theme", next);
    } catch (_) {}

    const btn = document.getElementById("theme-toggle");
    if (btn) {
      const lbl = next === "dark" ? "切换浅色纸感模式" : "切换深色黑曜石模式";
      btn.setAttribute("aria-label", lbl);
      btn.setAttribute("aria-pressed", next === "dark" ? "true" : "false");
      btn.title = lbl;
    }

    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) {
      metaTheme.setAttribute("content", next === "dark" ? "#0f131a" : "#f6f3ec");
    }
  }

  const themeBtn = document.getElementById("theme-toggle");
  if (themeBtn) {
    applyTheme(getTheme());
    themeBtn.addEventListener("click", function () {
      applyTheme(getTheme() === "dark" ? "light" : "dark");
    });
  }

  /* ------------------------------------------------------------------------
     2. Auto-Scroll Active Mobile Nav Pill & Active Channel Switcher Pill
     ------------------------------------------------------------------------ */
  function centerActiveScrollPill(containerSel, pillSel) {
    const container = document.querySelector(containerSel);
    if (!container) return;
    const activePill = container.querySelector(pillSel);
    if (activePill && container.scrollWidth > container.clientWidth + 2) {
      try {
        activePill.scrollIntoView({ inline: "center", block: "nearest", behavior: "auto" });
      } catch (_) {
        activePill.scrollIntoView(false);
      }
    }
  }
  centerActiveScrollPill(".main-nav", ".nav-pill.active");
  centerActiveScrollPill(".ch-switcher", ".ch-switch-pill.active");

  /* ------------------------------------------------------------------------
     3. Font Size Scaler (A- / A+)
     ------------------------------------------------------------------------ */
  const MIN_SCALE = 0.88;
  const MAX_SCALE = 1.24;
  let readScale = 1.0;
  try {
    const saved = parseFloat(localStorage.getItem("gir_read_scale") || "1");
    if (!isNaN(saved) && saved >= MIN_SCALE && saved <= MAX_SCALE) {
      readScale = saved;
    }
  } catch (_) {}

  function applyScale(val) {
    readScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, Math.round(val * 100) / 100));
    root.style.setProperty("--read-scale", String(readScale));
    try {
      localStorage.setItem("gir_read_scale", String(readScale));
    } catch (_) {}
  }
  applyScale(readScale);

  const decBtn = document.getElementById("font-dec");
  const incBtn = document.getElementById("font-inc");
  if (decBtn) decBtn.addEventListener("click", function () { applyScale(readScale - 0.06); });
  if (incBtn) incBtn.addEventListener("click", function () { applyScale(readScale + 0.06); });

  /* ------------------------------------------------------------------------
     4. Reading Progress Bar, TOC % Readout & Back-to-Top Visibility
     ------------------------------------------------------------------------ */
  const progressBar = document.getElementById("reading-progress");
  const tocPctEl = document.getElementById("toc-pct");
  const backToTopBtn = document.getElementById("back-to-top");

  let progressRaf = 0;
  function updateScrollMetrics() {
    progressRaf = 0;
    const docH = document.documentElement.scrollHeight - window.innerHeight;
    const pct = docH > 0 ? Math.max(0, Math.min(100, (window.scrollY / docH) * 100)) : 0;
    if (progressBar) {
      progressBar.style.width = pct.toFixed(1) + "%";
    }
    if (tocPctEl) {
      tocPctEl.textContent = Math.round(pct) + "%";
    }
    if (backToTopBtn) {
      backToTopBtn.classList.toggle("visible", window.scrollY > 480);
    }
  }

  function scheduleScrollMetrics() {
    if (!progressRaf) {
      progressRaf = window.requestAnimationFrame(updateScrollMetrics);
    }
  }

  window.addEventListener("scroll", scheduleScrollMetrics, { passive: true });
  window.addEventListener("resize", scheduleScrollMetrics, { passive: true });
  updateScrollMetrics();

  function scrollPageTop() {
    window.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });
  }

  document.querySelectorAll("[data-action='scroll-top']").forEach(function (el) {
    el.addEventListener("click", scrollPageTop);
  });
  if (backToTopBtn && backToTopBtn.getAttribute("data-action") !== "scroll-top") {
    backToTopBtn.addEventListener("click", scrollPageTop);
  }

  /* Delegated Smooth Scroll for Same-Page Anchor Links (replaces global CSS scroll-behavior) */
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
      return;
    }
    const link = e.target.closest('a[href^="#"]');
    if (!link) return;
    const href = link.getAttribute("href") || "";
    if (href.length <= 1 || href.indexOf("=") !== -1) return;
    const targetId = safeDecode(href.slice(1));
    const targetEl = targetId ? document.getElementById(targetId) : null;
    if (!targetEl || targetEl.classList.contains("tab-panel")) return;
    e.preventDefault();
    targetEl.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", block: "start" });
    if (history.replaceState) {
      try {
        history.replaceState(null, "", "#" + encodeURIComponent(targetId));
      } catch (_) {}
    }
  });

  /* ------------------------------------------------------------------------
     5. Shared Accessible Modal / Dialog Focus Manager
     ------------------------------------------------------------------------ */
  let modalReturnFocus = null;
  const modalFocusable =
    "input:not([disabled]), button:not([disabled]), a[href], select:not([disabled]), [tabindex='0']";

  function showDialog(dialog, preferredFocus) {
    if (!dialog) return;
    if (!document.querySelector('[aria-modal="true"].open')) {
      modalReturnFocus = document.activeElement;
    }
    dialog.classList.add("open");
    document.body.style.overflow = "hidden";
    const target = preferredFocus || dialog.querySelector(modalFocusable);
    if (target) target.focus();
  }

  function hideDialog(dialog) {
    if (!dialog || !dialog.classList.contains("open")) return;
    dialog.classList.remove("open");
    if (!document.querySelector('[aria-modal="true"].open')) {
      document.body.style.overflow = "";
      if (modalReturnFocus && modalReturnFocus.isConnected) {
        modalReturnFocus.focus();
      }
      modalReturnFocus = null;
    }
  }

  /* ------------------------------------------------------------------------
     6. TOC ScrollSpy (rAF-Throttled Desktop Sidebar + Parent-H2 Mobile Strip)
     ------------------------------------------------------------------------ */
  const tocLinks = Array.from(document.querySelectorAll(".toc-sidebar .toc-link"));
  const mobileTocPills = Array.from(document.querySelectorAll(".mobile-toc-strip .mobile-toc-pill"));

  if (tocLinks.length > 0 || mobileTocPills.length > 0) {
    const sourceLinks = tocLinks.length > 0 ? tocLinks : mobileTocPills;
    let lastH2Id = "";
    const headings = sourceLinks
      .map(function (a) {
        const href = a.getAttribute("href") || "";
        const id = href.replace(/^#/, "");
        const el = document.getElementById(id);
        const isLvl3 = a.classList.contains("lvl-3");
        if (!isLvl3 && el) lastH2Id = id;
        return {
          id: id,
          el: el,
          parentH2Id: isLvl3 ? (lastH2Id || id) : id,
        };
      })
      .filter(function (x) { return !!x.el; });

    let activeId = "";
    let activeMobileId = "";
    let tocRaf = 0;

    function syncToc() {
      tocRaf = 0;
      if (headings.length === 0) return;
      const offset = 118;
      let current = headings[0];
      for (let i = 0; i < headings.length; i++) {
        if (headings[i].el.getBoundingClientRect().top <= offset) {
          current = headings[i];
        } else {
          break;
        }
      }
      if (!current) return;

      if (current.id !== activeId) {
        activeId = current.id;
        const sidebar = document.querySelector(".toc-sidebar");
        tocLinks.forEach(function (link) {
          const isAct = (link.getAttribute("href") || "") === "#" + activeId;
          link.classList.toggle("active", isAct);
          if (isAct && sidebar && sidebar.scrollHeight > sidebar.clientHeight) {
            const top = link.offsetTop - sidebar.clientHeight / 2;
            sidebar.scrollTo({ top: Math.max(0, top), behavior: "auto" });
          }
        });
      }

      const mobTargetId = current.parentH2Id || current.id;
      if (mobTargetId !== activeMobileId) {
        activeMobileId = mobTargetId;
        const mobileStrip = document.querySelector(".mobile-toc-strip");
        mobileTocPills.forEach(function (pill) {
          const isAct = (pill.getAttribute("href") || "") === "#" + activeMobileId;
          pill.classList.toggle("active", isAct);
          if (isAct && mobileStrip && mobileStrip.scrollWidth > mobileStrip.clientWidth + 2) {
            const left = pill.offsetLeft - mobileStrip.clientWidth / 2 + pill.clientWidth / 2;
            mobileStrip.scrollTo({ left: Math.max(0, left), behavior: "auto" });
          }
        });
      }
    }

    function scheduleSyncToc() {
      if (!tocRaf) {
        tocRaf = window.requestAnimationFrame(syncToc);
      }
    }

    window.addEventListener("scroll", scheduleSyncToc, { passive: true });
    syncToc();
  }

  const tocBackdrop = document.getElementById("toc-backdrop");
  function setTocDrawer(open) {
    if (!tocBackdrop) return;
    if (open) showDialog(tocBackdrop);
    else hideDialog(tocBackdrop);
  }
  document.querySelectorAll("[data-action='open-toc']").forEach(function (btn) {
    btn.addEventListener("click", function () { setTocDrawer(true); });
  });
  document.querySelectorAll("[data-action='close-toc']").forEach(function (btn) {
    btn.addEventListener("click", function () { setTocDrawer(false); });
  });
  if (tocBackdrop) {
    tocBackdrop.addEventListener("click", function (e) {
      if (e.target === tocBackdrop) setTocDrawer(false);
    });
    tocBackdrop.querySelectorAll("a.toc-link").forEach(function (a) {
      a.addEventListener("click", function () { setTocDrawer(false); });
    });
  }

  /* ------------------------------------------------------------------------
     7. Command-K Quick Jump Palette (#cmd-palette)
     ------------------------------------------------------------------------ */
  const cmdPalette = document.getElementById("cmd-palette");
  const cmdOpenBtn = document.getElementById("cmd-open");
  const cmdInput = document.getElementById("cmd-input");
  const cmdList = document.getElementById("cmd-list");
  const cmdDataEl = document.getElementById("cmd-nav-data");
  let cmdItems = [];
  let cmdFiltered = [];
  let cmdIndex = 0;

  if (cmdDataEl) {
    try {
      const raw = JSON.parse(cmdDataEl.textContent || "[]");
      if (Array.isArray(raw)) {
        cmdItems = raw.map(function (it) {
          return {
            title: String(it.title || it.label || it.name || "").trim(),
            meta: String(it.meta || it.sub || it.group || it.category || "").trim(),
            href: String(it.href || it.url || "#").trim(),
            keywords: String(it.keywords || it.tags || "").trim(),
          };
        }).filter(function (it) { return !!it.title; });
      }
    } catch (_) {
      cmdItems = [];
    }
  }
  if (cmdItems.length === 0) {
    cmdItems = Array.from(document.querySelectorAll(".main-nav .nav-pill")).map(function (a) {
      return {
        title: (a.textContent || "").trim(),
        meta: "导航",
        href: a.getAttribute("href") || "#",
        keywords: a.getAttribute("data-nav") || "",
      };
    });
  }

  function renderCmdList(query) {
    if (!cmdList) return;
    const tokens = String(query || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
    cmdFiltered = cmdItems.filter(function (it) {
      if (tokens.length === 0) return true;
      const hay = (it.title + " " + it.meta + " " + it.keywords + " " + it.href).toLowerCase();
      return tokens.every(function (tk) { return hay.indexOf(tk) !== -1; });
    });
    cmdIndex = 0;

    if (cmdFiltered.length === 0) {
      cmdList.innerHTML = '<div class="cmd-empty">未找到匹配的页面或报告，试试输入「黄金」「A股」「新手」「筛选」</div>';
      return;
    }

    cmdList.innerHTML = cmdFiltered
      .map(function (it, idx) {
        return (
          '<a class="cmd-item' + (idx === 0 ? " active" : "") + '" data-cmd-idx="' + idx + '" href="' + escHtml(it.href) + '">' +
          '<span class="cmd-item-title">' + escHtml(it.title) + "</span>" +
          (it.meta ? '<span class="cmd-item-meta">' + escHtml(it.meta) + "</span>" : "") +
          "</a>"
        );
      })
      .join("");
  }

  function syncCmdActive() {
    if (!cmdList) return;
    const els = cmdList.querySelectorAll(".cmd-item");
    els.forEach(function (el, idx) {
      const isAct = idx === cmdIndex;
      el.classList.toggle("active", isAct);
      if (isAct && el.scrollIntoView) {
        el.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function openCmdPalette() {
    if (!cmdPalette) return;
    if (cmdInput) cmdInput.value = "";
    renderCmdList("");
    showDialog(cmdPalette, cmdInput);
  }

  function closeCmdPalette() {
    if (!cmdPalette) return;
    hideDialog(cmdPalette);
  }

  if (cmdOpenBtn) {
    cmdOpenBtn.addEventListener("click", openCmdPalette);
  }
  document.querySelectorAll("[data-action='close-cmd']").forEach(function (btn) {
    btn.addEventListener("click", closeCmdPalette);
  });
  if (cmdPalette) {
    cmdPalette.addEventListener("click", function (e) {
      if (e.target === cmdPalette) closeCmdPalette();
    });
  }
  if (cmdInput) {
    cmdInput.addEventListener("input", function () {
      renderCmdList(cmdInput.value);
    });
    cmdInput.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") {
        if (cmdFiltered.length > 0) {
          e.preventDefault();
          cmdIndex = (cmdIndex + 1) % cmdFiltered.length;
          syncCmdActive();
        }
      } else if (e.key === "ArrowUp") {
        if (cmdFiltered.length > 0) {
          e.preventDefault();
          cmdIndex = (cmdIndex - 1 + cmdFiltered.length) % cmdFiltered.length;
          syncCmdActive();
        }
      } else if (e.key === "Enter") {
        const chosen = cmdFiltered[cmdIndex];
        if (chosen && chosen.href) {
          e.preventDefault();
          closeCmdPalette();
          window.location.href = chosen.href;
        }
      }
    });
  }
  if (cmdList) {
    cmdList.addEventListener("mousemove", function (e) {
      const item = e.target.closest(".cmd-item");
      if (!item) return;
      const idx = parseInt(item.getAttribute("data-cmd-idx") || "-1", 10);
      if (!isNaN(idx) && idx >= 0 && idx !== cmdIndex) {
        cmdIndex = idx;
        syncCmdActive();
      }
    });
    cmdList.addEventListener("click", function (e) {
      if (e.target.closest(".cmd-item")) {
        closeCmdPalette();
      }
    });
  }

  /* ------------------------------------------------------------------------
     8. Chart Lightbox Fullscreen Zoom Modal (Mobile Scroll-Safe 100% Default)
     ------------------------------------------------------------------------ */
  const chartModal = document.getElementById("chart-modal");
  const chartModalTitle = document.getElementById("chart-modal-title");
  const chartModalCanvas = document.getElementById("chart-modal-canvas");
  const chartModalStage = chartModal ? chartModal.querySelector(".chart-modal-stage") : null;
  let zoomPct = 100;

  function applyChartZoom(pct) {
    zoomPct = Math.max(70, Math.min(240, pct));
    if (chartModalCanvas) {
      if (zoomPct === 100) {
        chartModalCanvas.style.width = "min(1080px, 94vw)";
      } else {
        chartModalCanvas.style.width = Math.round(1080 * (zoomPct / 100)) + "px";
      }
    }
    const zLbl = document.getElementById("chart-zoom-readout");
    if (zLbl) zLbl.textContent = zoomPct + "%";
  }

  function getChartSvg(chartBox) {
    return (
      chartBox.querySelector(".svg-scroll svg, .chart-svg-stage svg") ||
      chartBox.querySelector("svg:not(.zoom-icon)")
    );
  }

  function openChartModal(chartBox) {
    if (!chartModal || !chartModalCanvas) return;
    const svg = getChartSvg(chartBox);
    if (!svg) return;
    const titleEl = chartBox.querySelector(".chart-title");
    if (chartModalTitle) {
      chartModalTitle.textContent = titleEl ? titleEl.textContent.trim() : "图表放大视图";
    }
    chartModalCanvas.innerHTML = "";
    const clone = svg.cloneNode(true);
    clone.removeAttribute("style");
    chartModalCanvas.appendChild(clone);
    applyChartZoom(100);
    if (chartModalStage) {
      chartModalStage.scrollLeft = 0;
      chartModalStage.scrollTop = 0;
    }
    showDialog(chartModal);
  }

  function closeChartModal() {
    if (!chartModal) return;
    hideDialog(chartModal);
  }

  const ZOOM_ICON_HTML =
    '<svg class="zoom-icon" viewBox="0 0 16 16" width="13" height="13" fill="none" ' +
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<circle cx="7" cy="7" r="4.6"></circle><path d="M10.5 10.5L14 14"></path></svg><span>放大</span>';

  document.querySelectorAll(".chart-box").forEach(function (box) {
    const svg = getChartSvg(box);
    if (!svg) return;
    if (!box.querySelector(".chart-zoom-btn")) {
      const zbtn = document.createElement("button");
      zbtn.type = "button";
      zbtn.className = "chart-zoom-btn";
      zbtn.innerHTML = ZOOM_ICON_HTML;
      zbtn.addEventListener("click", function () { openChartModal(box); });
      box.insertBefore(zbtn, box.firstChild);
    }
    svg.addEventListener("click", function () { openChartModal(box); });
  });

  if (chartModal) {
    document.querySelectorAll("[data-action='close-chart']").forEach(function (b) {
      b.addEventListener("click", closeChartModal);
    });
    document.querySelectorAll("[data-action='zoom-in']").forEach(function (b) {
      b.addEventListener("click", function () { applyChartZoom(zoomPct + 25); });
    });
    document.querySelectorAll("[data-action='zoom-out']").forEach(function (b) {
      b.addEventListener("click", function () { applyChartZoom(zoomPct - 25); });
    });
    document.querySelectorAll("[data-action='zoom-reset']").forEach(function (b) {
      b.addEventListener("click", function () {
        applyChartZoom(100);
        if (chartModalStage) {
          chartModalStage.scrollLeft = 0;
          chartModalStage.scrollTop = 0;
        }
      });
    });
    chartModal.addEventListener("click", function (e) {
      if (e.target === chartModal || e.target.classList.contains("chart-modal-stage")) {
        closeChartModal();
      }
    });
  }

  /* ------------------------------------------------------------------------
     9. Global Zero-Dependency Glossary Tooltip Popover (All Pages)
     ------------------------------------------------------------------------ */
  const GLOSSARY_DICT = {
    four_buckets: {
      term: "四笔钱规划（活钱 / 稳钱 / 长钱 / 保障）",
      plain: "按「什么时候要用这笔钱」把积蓄分成四份：0–6 个月活钱、1–3 年稳钱、3–5 年以上长钱，外加先兜底的基础保障。",
      avoid: "避坑提醒：最常见的亏损不是买错产品，而是把半年内要用的房租或首付拿去买股票（短钱长投）。",
    },
    traffic_light: {
      term: "红绿灯信号（红灯停 / 黄灯 / 绿灯）",
      plain: "红绿灯不是预测明天涨跌，而是仓位安全阀：绿灯代表赔率划算可分批，黄灯代表拉锯观望，红灯停代表风险收益比偏弱。",
      avoid: "避坑提醒：红灯停绝不等于恐慌清仓，而是老底仓稳拿不乱卖、新钱先放稳钱池暂不追高或暂不新买。",
    },
    dfii10: {
      term: "10 年美债真实利率（DFII10）",
      plain: "扣除美国未来通胀预期后，买 10 年期美国国债能拿到手的「真实利息」。黄金不生息，因此真实利率越高，黄金承压越重。",
      avoid: "避坑提醒：只要真实利率仍高悬在过关线之上，就别凭感觉猜底抢跑新买黄金。",
    },
    erp: {
      term: "股权风险溢价（ERP）",
      plain: "买一篮子股票的盈利收益率减去无风险国债利率的差值，可以理解为「冒风险买股票比买国债多拿的性价比补贴」，数值越高越划算。",
      avoid: "避坑提醒：高 ERP 代表长期赔率好，但不代表明天立刻大涨，仍需配合趋势与仓位上限分批进场。",
    },
    hibor: {
      term: "香港银行同业拆息（HIBOR）",
      plain: "香港各家银行之间互相借港元的批发利率。它走高说明香港资金变紧、股票估值承压；走低说明市场流动性偏宽松。",
      avoid: "避坑提醒：关注港股时要同时看 HIBOR 和美元兑港元汇率是否逼近 7.85 弱方保证线。",
    },
    hkma_bal: {
      term: "香港金管局总结余",
      plain: "香港银行体系放在金管局账户里的「港元总水池」。水位越浅，一旦外部抽水，港元利率越容易突然跳涨。",
      avoid: "避坑提醒：当总结余逼近低水位警戒线时，港股高估值板块容易放大波动，不宜加杠杆。",
    },
    vix: {
      term: "美股恐慌指数（VIX）",
      plain: "由标普 500 期权价格算出来的市场「紧张度温度计」。20 以下偏平静，超过 30 说明全球资金正剧烈避险。",
      avoid: "避坑提醒：VIX 急飙突破 30 时各类资产容易一起被抛售变现，切忌在高波动盘中盲目重仓抄底。",
    },
    us10y: {
      term: "10 年期美债收益率（US10Y）",
      plain: "全球资产定价的「无风险锚」。它飙升会直接抬高全球借贷成本，压制高估值科技股和新兴市场资产。",
      avoid: "避坑提醒：若 10 年美债持续高企甚至触发熔断线，科技成长股新增仓位应保持克制。",
    },
    ah_premium: {
      term: "A/H 溢价与倒挂",
      plain: "同一家公司在 A 股和港股同时上市时的价格差。正值代表 A 股比港股贵；负值（倒挂）代表 A 股反而比港股便宜。",
      avoid: "避坑提醒：别只看表面便宜就换港股，用内地港股通买 H 股分红要扣 20%–28% 红利税，务必算税后净股息。",
    },
    etf_vs_feeder: {
      term: "场内 ETF vs 场外联接基金",
      plain: "场内 ETF 在券商 App 像股票一样实时交易、费率极低；场外联接在支付宝或银行按收盘净值申购，无需股票账户且绝不买到场内溢价。",
      avoid: "避坑提醒：跨境美股 ETF 场内抢购溢价高时，优先用场外联接按净值分批定投，别在场内当高溢价接盘侠。",
    },
    class_a_c: {
      term: "基金 A 类 vs C 类（+7 天惩罚费）",
      plain: "A 类在买入时一次性交申购费，适合长期持有；C 类不收申购费但按天扣销售服务费，适合短期波段。",
      avoid: "避坑提醒：无论 A 类还是 C 类，持有不满 7 天卖出通常都要硬扣 1.5% 惩罚性赎回费，短钱别乱进出。",
    },
    premium_discount: {
      term: "场内折价与溢价（参考净值 IOPV）",
      plain: "基金真实价值叫参考净值（IOPV），场内买价高于真实价值就是溢价——相当于值 100 元的东西大家抢到 120 元卖给你。",
      avoid: "避坑提醒：跨境 QDII 或商品场内溢价超过 2%–3% 坚决不追高，情绪退潮后多花的那部分溢价会直接蒸发。",
    },
    duration: {
      term: "债券久期（Duration）",
      plain: "衡量债券对利率变化有多敏感的「暴脾气系数」。久期 1 年以下像平稳直线，30 年国债久期近 20 年，利率微涨就能跌 5% 以上。",
      avoid: "避坑提醒：千万别把 30 年超长国债 ETF 当成保本稳健存款重仓，它属于高波动波段与对冲工具。",
    },
    nav_break: {
      term: "银行理财破净与真净值化",
      plain: "资管新规后银行理财不再保本，每天按底层债券和股票市价算净值；「破净」就是净值跌破 1 元本金线。",
      avoid: "避坑提醒：「业绩比较基准」只是目标不是承诺保底，追求本金绝对安全应选储蓄国债或 50 万以内银行存款。",
    },
    t0_t1: {
      term: "T+0 / T+1 与「可用 / 可取」",
      plain: "T+0 当天买当天能卖（债券/跨境/转债/商品 ETF）；T+1 次交易日才能卖（A 股普通股与 A 股股票 ETF）。资金「可用」指能买证券，「可取」指能提现回银行卡。",
      avoid: "避坑提醒：做国债逆回购务必点「卖出（借钱）」；周四借 1 天期吃 3 天息，周五借 1 天期周末白闲置，且到期次日才可提现。",
    },
    deposit_insurance: {
      term: "50 万元存款保险与单法人上限",
      plain: "同一存款人在同一家独立法人银行的所有普通存款和大额存单，本金加利息合计 50 万元以内由存款保险全额保障。",
      avoid: "避坑提醒：同一家银行的不同支行合并计算，实操单行控制在 45–47 万以内留出利息缓冲；理财、基金和保险不在存保范围内。",
    },
    dividend_tax: {
      term: "红利税与通道税费差异",
      plain: "A 股持股超 1 年免红利税；港股通收息直扣 20%（红筹最高 28%）；个人直买交易所公司债付息扣 20%，银行间债券 ETF 底层则更具税负优势。",
      avoid: "避坑提醒：买港股高股息前先按税后打七到八折重算真实到手率；境外账户投资收益须依法履行年度全球纳税申报义务。",
    },
    mrf_hedged: {
      term: "香港互认基金（MRF）对冲累计份额",
      plain: "经两地监管批准在内地合法销售的香港公募基金。「人民币对冲」用于锁住汇率波动，「累计份额」把利息滚入净值。",
      avoid: "避坑提醒：MRF 现金派息强制代扣 20% 个税，买卖价差暂免个税，认准「对冲 + 累计」份额，并核实未暂停申购。",
    },
    lof_delist: {
      term: "QDII / 商品 LOF 退市回归净值",
      plain: "部分场内跨境和商品 LOF 按交易所新规面临限期终止上市，退市转场外后只能按真实净值赎回。",
      avoid: "避坑提醒：高溢价买进此类 LOF，一旦退市回归净值，多付的溢价将永久清零，切勿在两位数溢价时进场。",
    },
    cb_call: {
      term: "可转债强赎与「Z 标识」",
      plain: "正股大涨触发条款后，公司有权按约 100.5 元强行买回转债。临近强赎或到期停牌最后阶段，行情软件会亮出「Z」警示标识。",
      avoid: "避坑提醒：忘记卖出或转股会被低价强赎瞬间亏掉 25%–50%；而已到期停牌的转债切忌误点转股。新手可优先选投资级转债 ETF 自动分散排雷。",
    },
    reits_irr: {
      term: "公募 REITs 分派率 vs 中债真实 IRR",
      plain: "产权类 REITs（保租房/商场）像买房收租看分派率与出租率；特许经营权类（高速/能源）到期资产无偿移交，高分派里混有本金归还。",
      avoid: "避坑提醒：绝不能把高速 REITs 8%–12% 的表面分派率当成高股息，必须核对中债真实内部收益率（IRR）与薄量限价挂单。",
    },
    dxy: {
      term: "美元指数（DXY）",
      plain: "衡量美元相对欧元、日元、英镑等一篮子主要货币综合强弱的标尺。美元走强往往意味着全球流动性偏紧，压制黄金与非美股市；走弱则利于非美资产回暖。",
      avoid: "避坑提醒：美元指数偏强或汇兑价差较大时，切忌冲动新换汇做外币定存或重仓未锁汇的境外资产，务必把汇率波动算进总收益。",
    },
    cot: {
      term: "期货大资金持仓报告（COT）",
      plain: "美国商品期货交易委员会（CFTC）每周公布的机构与投机资金持仓明细，可用来观察黄金、原油和美债期货里的多空拥挤程度。",
      avoid: "避坑提醒：当投机多头净持仓极端拥挤时，哪怕基本面未变也很容易因获利回吐触发急跌，切忌在极端拥挤区追高。",
    },
    cds: {
      term: "债务违约保险费率（CDS）",
      plain: "给公司债或主权债买的「违约保险」年保费（通常按基点计）。费率越低说明市场认为还本付息越稳，飙升则预示信用违约风险快速升温。",
      avoid: "避坑提醒：当某发行主体或行业的信用违约保险费率急剧跳升时，切忌只盯着高票面利率去接盘高收益债或弱资质可转债。",
    },
  };

  let activeTermPop = null;
  let activeTermTrigger = null;

  function closeTermPopover() {
    if (activeTermPop && activeTermPop.parentNode) {
      activeTermPop.parentNode.removeChild(activeTermPop);
    }
    if (activeTermTrigger) {
      activeTermTrigger.setAttribute("aria-expanded", "false");
    }
    activeTermPop = null;
    activeTermTrigger = null;
  }

  function openTermPopover(trigger) {
    const key = trigger.getAttribute("data-term") || "";
    const entry = GLOSSARY_DICT[key];
    if (!entry) return;
    if (activeTermTrigger === trigger && activeTermPop) {
      closeTermPopover();
      return;
    }
    closeTermPopover();

    const basePrefix = document.body.getAttribute("data-base-prefix") || "";
    const pop = document.createElement("div");
    pop.className = "term-popover";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", entry.term);
    pop.innerHTML =
      '<div class="term-pop-head">' +
      '<div class="term-pop-title">' + escHtml(entry.term) + "</div>" +
      '<button type="button" class="term-pop-close" aria-label="关闭解释">×</button>' +
      "</div>" +
      '<p class="term-pop-plain">' + escHtml(entry.plain) + "</p>" +
      '<div class="term-pop-avoid">' + escHtml(entry.avoid) + "</div>" +
      '<div class="term-pop-foot"><a href="' + escHtml(basePrefix + "guide.html#term-" + key) + '">在《新手 3 分钟指南》查看全部术语 →</a></div>';

    document.body.appendChild(pop);
    const rect = trigger.getBoundingClientRect();
    const popW = pop.offsetWidth || 320;
    const popH = pop.offsetHeight || 180;
    const margin = 12;
    let left = rect.left + rect.width / 2 - popW / 2;
    left = Math.max(margin, Math.min(window.innerWidth - popW - margin, left));
    let top = rect.bottom + 8;
    if (top + popH > window.innerHeight - margin && rect.top - popH - 8 >= margin) {
      top = rect.top - popH - 8;
    } else {
      top = Math.max(margin, Math.min(window.innerHeight - popH - margin, top));
    }
    pop.style.left = Math.round(left) + "px";
    pop.style.top = Math.round(top) + "px";

    const closeBtn = pop.querySelector(".term-pop-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", closeTermPopover);
    }
    trigger.setAttribute("aria-expanded", "true");
    activeTermPop = pop;
    activeTermTrigger = trigger;
  }

  document.addEventListener("click", function (e) {
    const tip = e.target.closest(".term-tip[data-term]");
    if (tip) {
      e.preventDefault();
      e.stopPropagation();
      openTermPopover(tip);
      return;
    }
    if (activeTermPop && !activeTermPop.contains(e.target)) {
      closeTermPopover();
    }
  });
  window.addEventListener("resize", closeTermPopover, { passive: true });

  /* Global Keyboard Dispatcher (Cmd/Ctrl+K, Chart Shortcuts, Modal Escape/Tab) */
  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && cmdPalette) {
      e.preventDefault();
      if (cmdPalette.classList.contains("open")) {
        closeCmdPalette();
      } else {
        closeTermPopover();
        closeChartModal();
        setTocDrawer(false);
        hideDialog(document.getElementById("dossier-modal"));
        hideDialog(document.getElementById("etf-modal"));
        openCmdPalette();
      }
      return;
    }

    if (chartModal && chartModal.classList.contains("open")) {
      if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        applyChartZoom(zoomPct + 25);
        return;
      }
      if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        applyChartZoom(zoomPct - 25);
        return;
      }
      if (e.key === "0") {
        e.preventDefault();
        applyChartZoom(100);
        return;
      }
    }

    const dialog = document.querySelector('[aria-modal="true"].open');
    if (dialog) {
      if (e.key === "Escape") {
        e.preventDefault();
        closeTermPopover();
        closeCmdPalette();
        closeChartModal();
        setTocDrawer(false);
        hideDialog(document.getElementById("dossier-modal"));
        hideDialog(document.getElementById("etf-modal"));
      } else if (e.key === "Tab") {
        const targets = dialog.querySelectorAll(modalFocusable);
        const first = targets[0];
        const last = targets[targets.length - 1];
        if (!first) return;
        if (
          !dialog.contains(document.activeElement) ||
          (e.shiftKey && document.activeElement === first) ||
          (!e.shiftKey && document.activeElement === last)
        ) {
          e.preventDefault();
          (e.shiftKey ? last : first).focus();
        }
      }
      return;
    }

    if (e.key === "Escape" && activeTermPop) {
      e.preventDefault();
      closeTermPopover();
      return;
    }

    if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey && !isEditableElement(document.activeElement)) {
      const searchBox =
        document.getElementById("scr-search") ||
        document.getElementById("etf-search") ||
        document.getElementById("arc-search") ||
        document.getElementById("guide-term-search");
      if (searchBox) {
        e.preventDefault();
        if (searchBox.id === "guide-term-search") {
          const panel = searchBox.closest(".filter-panel") || searchBox;
          const rect = panel.getBoundingClientRect();
          const header = document.querySelector(".site-header");
          const headerH = header ? header.offsetHeight : 64;
          if (rect.top < headerH + 6 || rect.bottom > window.innerHeight - 140) {
            const top = window.scrollY + rect.top - headerH - 12;
            window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
          }
        }
        searchBox.focus({ preventScroll: searchBox.id === "guide-term-search" });
        searchBox.select();
      }
    }
  });

  /* ------------------------------------------------------------------------
     10. Supercharged 231-Stock Global Screener (#screener-data)
     ------------------------------------------------------------------------ */
  const screenerDataEl = document.getElementById("screener-data");
  if (screenerDataEl) {
    let allStocks = [];
    try {
      const parsed = JSON.parse(screenerDataEl.textContent || "[]");
      if (Array.isArray(parsed)) {
        allStocks = parsed;
      }
    } catch (_) {
      allStocks = [];
    }

    const state = {
      q: "",
      market: "all",
      color: "all",
      sectors: new Set(),
      preset: "all",
      sortKey: "default",
      sortDir: 1,
      sectorsExpanded: false,
    };

    const qInput = document.getElementById("scr-search");
    const clearBtn = document.getElementById("scr-clear");
    const sectorTray = document.getElementById("scr-sector-tray");
    const activeFiltersEl = document.getElementById("scr-active-filters");
    const mktBtns = Array.from(document.querySelectorAll("[data-filter-market]"));
    const colBtns = Array.from(document.querySelectorAll("[data-filter-color]"));
    const statTiles = Array.from(document.querySelectorAll("[data-stat-color]"));
    const presetBtns = Array.from(document.querySelectorAll("[data-preset]"));
    const countEl = document.getElementById("scr-count");
    const tbody = document.getElementById("scr-tbody");
    const cardsEl = document.getElementById("scr-cards");
    const resetBtn = document.getElementById("scr-reset");
    const hasData = allStocks.length > 0;

    const COLOR_ORDER = { g: 1, b: 2, y: 3, r: 4 };
    const COLOR_MARK = { g: "●", b: "◆", y: "▲", r: "×" };
    const COLOR_NAMES = { g: "当下底座", b: "未来主攻", y: "分歧观察", r: "高危回避" };
    const MARKET_NAMES = { "a-share": "A股", "hk-stock": "港股", "us-stock": "美股" };
    const PRESET_NAMES = {
      base: "当下底座",
      "high-div": "高股息 ≥4%",
      "near-anchor": "贴近安全锚 ≤12%",
      "ah-inverted": "AH 倒挂",
      "hide-red": "隐藏高危回避",
    };

    const sortHeaders = Array.from(document.querySelectorAll("table.screener-table th.sortable"));
    sortHeaders.forEach(function (th) {
      const btn = th.querySelector("button");
      if (btn) btn.disabled = !hasData;
      if (!th.dataset.baseLabel) {
        th.dataset.baseLabel = (th.textContent || "").replace(/\s*[⇅▲▼]\s*$/, "").trim();
      }
    });

    function matchesPreset(st, preset) {
      if (!preset || preset === "all") return true;
      if (preset === "base") return st.color === "g";
      if (preset === "high-div") return isFiniteNum(st.div_pct) && st.div_pct >= 4.0;
      if (preset === "near-anchor") return isFiniteNum(st.anchor_gap_pct) && st.anchor_gap_pct <= 12.0;
      if (preset === "ah-inverted") return isFiniteNum(st.ah_pct) && st.ah_pct < 0;
      if (preset === "hide-red") return st.color !== "r";
      return true;
    }

    function formatValuationChips(st) {
      let parts = [];
      if (Array.isArray(st.val_chips) && st.val_chips.length > 0) {
        parts = st.val_chips.map(function (p) { return String(p || "").trim(); }).filter(Boolean).slice(0, 4);
      } else {
        const raw = String(st.valuation || "").trim();
        if (raw) {
          parts = raw
            .split(/\s*[·｜|;；]\s*/)
            .map(function (p) { return p.trim(); })
            .filter(Boolean)
            .slice(0, 4);
        }
      }
      if (parts.length === 0) return "";
      return (
        '<div class="val-chips">' +
        parts.map(function (p) { return '<span class="val-chip">' + escHtml(p) + "</span>"; }).join("") +
        "</div>"
      );
    }

    function formatDivAhCell(st) {
      const chips = [];
      if (isFiniteNum(st.div_pct)) {
        chips.push('<span class="val-chip">股息 ' + st.div_pct.toFixed(1) + "%</span>");
      }
      if (isFiniteNum(st.ah_pct)) {
        const sign = st.ah_pct > 0 ? "+" : "";
        const cls = st.ah_pct < 0 ? "ah-pill ah-disc" : "ah-pill ah-prem";
        chips.push('<span class="' + cls + '">AH ' + sign + st.ah_pct.toFixed(1) + "%</span>");
      }
      if (chips.length === 0) {
        return '<span class="sec-sub">—</span>';
      }
      return '<div class="val-chips">' + chips.join("") + "</div>";
    }

    function formatAnchorBadge(st) {
      if (!isFiniteNum(st.anchor_gap_pct)) return "";
      const g = st.anchor_gap_pct;
      const customLbl = typeof st.anchor_label === "string" && st.anchor_label.trim() ? st.anchor_label.trim() : "";
      if (g <= 0) {
        const lbl = customLbl || (g < -0.5 ? "低于锚 " + Math.abs(g).toFixed(1) + "%" : "已触安全锚");
        return '<span class="anchor-badge anchor-in">' + escHtml(lbl) + "</span>";
      }
      if (g <= 12.0) {
        return '<span class="anchor-badge anchor-near">' + escHtml(customLbl || ("距锚 +" + g.toFixed(1) + "%")) + "</span>";
      }
      return '<span class="anchor-badge anchor-far">' + escHtml(customLbl || ("距锚 +" + g.toFixed(1) + "%")) + "</span>";
    }

    function syncSortHeaders() {
      sortHeaders.forEach(function (th) {
        const key = th.getAttribute("data-sort");
        const base = th.dataset.baseLabel || "";
        const target = th.querySelector("button") || th;
        if (state.sortKey === key) {
          const dirStr = state.sortDir === 1 ? "asc" : "desc";
          th.setAttribute("data-sort-dir", dirStr);
          th.setAttribute("aria-sort", state.sortDir === 1 ? "ascending" : "descending");
          target.textContent = base + (state.sortDir === 1 ? " ▲" : " ▼");
        } else {
          th.removeAttribute("data-sort-dir");
          th.removeAttribute("aria-sort");
          target.textContent = base + " ⇅";
        }
      });
    }

    function syncControlStates() {
      mktBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-filter-market") || "all") === state.market);
      });
      colBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-filter-color") || "all") === state.color);
      });
      statTiles.forEach(function (t) {
        const c = t.getAttribute("data-stat-color") || "all";
        const isAct = c === state.color && (c !== "all" || state.preset === "all");
        t.classList.toggle("active", isAct);
        t.setAttribute("aria-pressed", isAct ? "true" : "false");
      });
      presetBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-preset") || "all") === state.preset);
      });
      if (clearBtn) {
        const hasQ = !!state.q;
        clearBtn.hidden = !hasQ;
        clearBtn.style.display = hasQ ? "" : "none";
      }
    }

    function syncUrlHash() {
      if (!history.replaceState) return;
      const params = [];
      if (state.market !== "all") params.push("market=" + encodeURIComponent(state.market));
      if (state.color !== "all") params.push("color=" + encodeURIComponent(state.color));
      if (state.preset !== "all") params.push("preset=" + encodeURIComponent(state.preset));
      if (state.sectors.size > 0) {
        params.push("sectors=" + encodeURIComponent(Array.from(state.sectors).join(",")));
      }
      if (state.q.trim()) params.push("q=" + encodeURIComponent(state.q.trim()));
      const nextUrl = params.length > 0
        ? "#" + params.join("&")
        : window.location.pathname + window.location.search;
      try {
        history.replaceState(null, "", nextUrl);
      } catch (_) {}
    }

    function applyHashToState(resetOnEmpty) {
      const raw = (window.location.hash || "").replace(/^#/, "").trim();
      if (!raw) {
        if (!resetOnEmpty) return false;
        state.q = "";
        state.market = "all";
        state.color = "all";
        state.preset = "all";
        state.sectors.clear();
        if (qInput) qInput.value = "";
        return true;
      }
      state.q = "";
      state.market = "all";
      state.color = "all";
      state.preset = "all";
      state.sectors.clear();

      if (raw.indexOf("=") === -1) {
        const token = safeDecode(raw);
        if (["a-share", "hk-stock", "us-stock"].indexOf(token) !== -1) {
          state.market = token;
        } else if (["base", "high-div", "near-anchor", "ah-inverted", "hide-red"].indexOf(token) !== -1) {
          state.preset = token;
        }
      } else {
        raw.split("&").forEach(function (pair) {
          const eq = pair.indexOf("=");
          if (eq <= 0) return;
          const k = safeDecode(pair.slice(0, eq));
          const v = safeDecode(pair.slice(eq + 1));
          if (k === "market" && ["all", "a-share", "hk-stock", "us-stock"].indexOf(v) !== -1) {
            state.market = v;
          } else if (k === "color" && ["all", "g", "b", "y", "r"].indexOf(v) !== -1) {
            state.color = v;
          } else if (k === "preset" && ["all", "base", "high-div", "near-anchor", "ah-inverted", "hide-red"].indexOf(v) !== -1) {
            state.preset = v;
          } else if (k === "sectors" && v) {
            v.split(",").map(function (s) { return s.trim(); }).filter(Boolean).forEach(function (s) {
              state.sectors.add(s);
            });
          } else if (k === "q") {
            state.q = v;
          }
        });
      }
      if (state.preset === "hide-red" && state.color === "r") {
        state.preset = "all";
      }
      if (state.preset === "base" && state.color !== "all" && state.color !== "g") {
        state.preset = "all";
      }
      if (qInput) qInput.value = state.q;
      return true;
    }

    function renderSectorControls() {
      const counts = new Map();
      allStocks.forEach(function (st) {
        if (state.market !== "all" && st.market !== state.market) return;
        const sec = String(st.sector || "").trim();
        if (!sec) return;
        counts.set(sec, (counts.get(sec) || 0) + 1);
      });

      Array.from(state.sectors).forEach(function (sec) {
        if (!counts.has(sec)) state.sectors.delete(sec);
      });

      const list = Array.from(counts.entries()).sort(function (a, b) {
        if (b[1] !== a[1]) return b[1] - a[1];
        return a[0].localeCompare(b[0], "zh-Hans-CN");
      });

      if (sectorTray) {
        const limit = 14;
        const needToggle = list.length > limit;
        const visible = state.sectorsExpanded || !needToggle
          ? list
          : list.filter(function (entry, idx) {
              return idx < limit || state.sectors.has(entry[0]);
            });

        let html = visible
          .map(function (entry) {
            const sec = entry[0];
            const cnt = entry[1];
            const isAct = state.sectors.has(sec);
            return (
              '<button type="button" class="sector-chip' + (isAct ? " active" : "") + '" ' +
              'data-sector-chip="' + escHtml(sec) + '" aria-pressed="' + (isAct ? "true" : "false") + '">' +
              "<span>" + escHtml(sec) + '</span><span class="sector-cnt">' + cnt + "</span></button>"
            );
          })
          .join("");

        if (needToggle) {
          html +=
            '<button type="button" class="sector-chip" data-sector-toggle="1">' +
            (state.sectorsExpanded ? "收起赛道" : "展开全部 " + list.length + " 赛道") +
            "</button>";
        }
        sectorTray.innerHTML = html;
      }
    }

    function renderActiveFilters() {
      if (!activeFiltersEl) return;
      const chips = [];
      if (state.market !== "all") {
        chips.push(
          '<button type="button" class="active-chip" data-clear-filter="market">市场：' +
          escHtml(MARKET_NAMES[state.market] || state.market) + " ×</button>"
        );
      }
      if (state.color !== "all") {
        chips.push(
          '<button type="button" class="active-chip" data-clear-filter="color">阵营：' +
          escHtml(COLOR_NAMES[state.color] || state.color) + " ×</button>"
        );
      }
      if (state.preset !== "all") {
        chips.push(
          '<button type="button" class="active-chip" data-clear-filter="preset">快捷：' +
          escHtml(PRESET_NAMES[state.preset] || state.preset) + " ×</button>"
        );
      }
      state.sectors.forEach(function (sec) {
        chips.push(
          '<button type="button" class="active-chip" data-clear-sector="' + escHtml(sec) + '">赛道：' +
          escHtml(sec) + " ×</button>"
        );
      });
      if (state.q.trim()) {
        chips.push(
          '<button type="button" class="active-chip" data-clear-filter="q">搜索：“' +
          escHtml(state.q.trim()) + "” ×</button>"
        );
      }
      activeFiltersEl.innerHTML = chips.join("");
    }

    function resetScreener() {
      state.q = "";
      state.market = "all";
      state.color = "all";
      state.preset = "all";
      state.sectors.clear();
      state.sortKey = "default";
      state.sortDir = 1;
      if (qInput) qInput.value = "";
      renderSectorControls();
      renderScreener(true);
    }

    function renderScreener(syncHash) {
      if (!hasData) return;
      syncControlStates();
      renderActiveFilters();
      if (syncHash !== false) syncUrlHash();

      const tokens = state.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
      let rows = allStocks.filter(function (st) {
        if (state.market !== "all" && st.market !== state.market) return false;
        if (state.color !== "all" && st.color !== state.color) return false;
        if (!matchesPreset(st, state.preset)) return false;
        if (state.sectors.size > 0 && !state.sectors.has(st.sector)) return false;
        if (tokens.length > 0) {
          const d = st.dossier || {};
          const hay = (
            st.name + " " + st.code + " " + st.sector + " " + st.market_label + " " +
            st.summary + " " + st.action_label + " " + st.valuation + " " +
            (d.moat || "") + " " + (d.financials || "") + " " + (d.catalysts || "") + " " + (d.action_etf || "")
          ).toLowerCase();
          if (!tokens.every(function (tk) { return hay.indexOf(tk) !== -1; })) return false;
        }
        return true;
      });

      if (state.sortKey !== "default") {
        const key = state.sortKey;
        const dir = state.sortDir;
        rows = rows.slice().sort(function (a, b) {
          if (key === "pe_num" || key === "div_pct" || key === "anchor_gap_pct") {
            const va = a[key];
            const vb = b[key];
            const aOk = isFiniteNum(va);
            const bOk = isFiniteNum(vb);
            if (!aOk && !bOk) return 0;
            if (!aOk) return 1;
            if (!bOk) return -1;
            return (va - vb) * dir;
          }
          if (key === "color") {
            return ((COLOR_ORDER[a.color] || 9) - (COLOR_ORDER[b.color] || 9)) * dir;
          }
          const sa = String(a[key] || "");
          const sb = String(b[key] || "");
          return sa.localeCompare(sb, "zh-Hans-CN", { numeric: true }) * dir;
        });
      }
      syncSortHeaders();

      if (countEl) {
        countEl.textContent = "显示 " + rows.length + " / " + allStocks.length + " 家龙头公司";
      }

      if (tbody) {
        if (rows.length === 0) {
          tbody.innerHTML =
            '<tr><td colspan="7"><div class="empty-state">' +
            '<div class="empty-title">未找到匹配的龙头公司</div>' +
            '<div class="empty-sub">尝试放宽筛选组合、更换关键词或切换市场</div>' +
            '<button type="button" class="btn btn-sm" data-action="scr-reset-all">清空所有筛选条件</button>' +
            "</div></td></tr>";
        } else {
          tbody.innerHTML = rows
            .map(function (st) {
              const mark = COLOR_MARK[st.color] || "●";
              const dKey = st.market + ":" + st.code;
              const dBtn = st.dossier
                ? ' <button type="button" class="dossier-btn" data-dossier-key="' + escHtml(dKey) + '">7维深研</button>'
                : "";
              return (
                '<tr class="row-' + escHtml(st.color) + '" data-market="' + escHtml(st.market) + '">' +
                '<td class="col-sticky"><span class="mkt-badge mkt-' + escHtml(st.market) + '">' + escHtml(st.market_label) + "</span></td>" +
                '<td><strong>' + escHtml(st.name) + '</strong> <span class="code-tag">' + escHtml(st.code) + "</span></td>" +
                '<td class="nw">' + escHtml(st.sector) + "</td>" +
                '<td><div><strong>' + escHtml(st.price) + "</strong></div>" + formatValuationChips(st) + "</td>" +
                "<td>" + formatDivAhCell(st) + "</td>" +
                '<td><span class="act-pill act-' + escHtml(st.color) + '">' + mark + " " + escHtml(st.action_label) + "</span></td>" +
                "<td>" + formatAnchorBadge(st) + escHtml(st.summary) + dBtn + ' <a href="' + escHtml(st.report_url) + '" class="nw">手册 →</a></td>' +
                "</tr>"
              );
            })
            .join("");
        }
      }

      if (cardsEl) {
        if (rows.length === 0) {
          cardsEl.innerHTML =
            '<div class="panel-card empty-state">' +
            '<div class="empty-title">未找到匹配的龙头公司</div>' +
            '<div class="empty-sub">尝试放宽筛选组合、更换关键词或切换市场</div>' +
            '<button type="button" class="btn btn-sm" data-action="scr-reset-all">清空所有筛选条件</button>' +
            "</div>";
        } else {
          cardsEl.innerHTML = rows
            .map(function (st) {
              const mark = COLOR_MARK[st.color] || "●";
              const divAh = formatDivAhCell(st);
              const hasDivAh = divAh.indexOf("val-chips") !== -1;
              return (
                '<div class="stock-card sc-' + escHtml(st.color) + '">' +
                '<div class="sc-top">' +
                '<div class="sc-title">' +
                '<span class="mkt-badge mkt-' + escHtml(st.market) + '">' + escHtml(st.market_label) + "</span>" +
                "<span>" + escHtml(st.name) + "</span>" +
                '<span class="code-tag">' + escHtml(st.code) + "</span>" +
                "</div>" +
                '<span class="act-pill act-' + escHtml(st.color) + '">' + mark + " " + escHtml(st.action_label) + "</span>" +
                "</div>" +
                '<div class="sc-meta">' +
                "<span><strong>赛道：</strong>" + escHtml(st.sector) + "</span>" +
                "<span><strong>现价：</strong>" + escHtml(st.price) + "</span>" +
                formatAnchorBadge(st) +
                "</div>" +
                formatValuationChips(st) +
                (hasDivAh ? divAh : "") +
                '<div class="sc-summary">' + escHtml(st.summary) + "</div>" +
                '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">' +
                (st.dossier
                  ? '<button type="button" class="dossier-btn" style="margin-left:0;" data-dossier-key="' + escHtml(st.market + ":" + st.code) + '">查看 7 维深度档案</button>'
                  : "") +
                '<a href="' + escHtml(st.report_url) + '" style="font-size:12.5px;font-weight:700;">查看该市场全景手册 →</a>' +
                "</div>" +
                "</div>"
              );
            })
            .join("");
        }
      }
    }

    let searchTimer = 0;
    if (qInput) {
      qInput.addEventListener("input", function () {
        state.q = qInput.value;
        if (clearBtn) {
          clearBtn.hidden = !state.q;
          clearBtn.style.display = state.q ? "" : "none";
        }
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(function () {
          renderScreener(true);
        }, 60);
      });
    }
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        window.clearTimeout(searchTimer);
        state.q = "";
        if (qInput) {
          qInput.value = "";
          qInput.focus();
        }
        renderScreener(true);
      });
    }
    if (sectorTray) {
      sectorTray.addEventListener("click", function (e) {
        const toggleBtn = e.target.closest("[data-sector-toggle]");
        if (toggleBtn) {
          state.sectorsExpanded = !state.sectorsExpanded;
          renderSectorControls();
          return;
        }
        const chip = e.target.closest("[data-sector-chip]");
        if (!chip) return;
        const sec = chip.getAttribute("data-sector-chip");
        if (!sec) return;
        if (state.sectors.has(sec)) state.sectors.delete(sec);
        else state.sectors.add(sec);
        renderSectorControls();
        renderScreener(true);
      });
    }
    if (activeFiltersEl) {
      activeFiltersEl.addEventListener("click", function (e) {
        const secBtn = e.target.closest("[data-clear-sector]");
        if (secBtn) {
          state.sectors.delete(secBtn.getAttribute("data-clear-sector"));
          renderSectorControls();
          renderScreener(true);
          return;
        }
        const clrBtn = e.target.closest("[data-clear-filter]");
        if (!clrBtn) return;
        const field = clrBtn.getAttribute("data-clear-filter");
        if (field === "market") {
          state.market = "all";
          renderSectorControls();
        } else if (field === "color") {
          state.color = "all";
        } else if (field === "preset") {
          state.preset = "all";
        } else if (field === "q") {
          state.q = "";
          if (qInput) qInput.value = "";
        }
        renderScreener(true);
      });
    }
    mktBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.market = btn.getAttribute("data-filter-market") || "all";
        renderSectorControls();
        renderScreener(true);
      });
    });
    colBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        const col = btn.getAttribute("data-filter-color") || "all";
        state.color = col;
        if (state.preset === "base" && col !== "g") state.preset = "all";
        if (state.preset === "hide-red" && col === "r") state.preset = "all";
        renderScreener(true);
      });
    });
    statTiles.forEach(function (tile) {
      function handleScreenerStatSelect() {
        const col = tile.getAttribute("data-stat-color") || "all";
        state.color = col !== "all" && state.color === col ? "all" : col;
        if (col === "all") state.preset = "all";
        else if (state.preset === "base" && state.color !== "g") state.preset = "all";
        else if (state.preset === "hide-red" && state.color === "r") state.preset = "all";
        renderScreener(true);
      }
      tile.addEventListener("click", handleScreenerStatSelect);
      tile.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleScreenerStatSelect();
        }
      });
    });
    presetBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        const p = btn.getAttribute("data-preset") || "all";
        if (p === "all") {
          state.preset = "all";
          state.color = "all";
        } else {
          state.preset = state.preset === p ? "all" : p;
          if (state.preset === "base") state.color = "all";
          if (state.preset === "hide-red" && state.color === "r") state.color = "all";
        }
        renderScreener(true);
      });
    });
    sortHeaders.forEach(function (th) {
      const target = th.querySelector("button") || th;
      target.addEventListener("click", function () {
        const key = th.getAttribute("data-sort");
        if (state.sortKey === key) {
          state.sortDir *= -1;
        } else {
          state.sortKey = key;
          state.sortDir = key === "div_pct" ? -1 : 1;
        }
        renderScreener(false);
      });
    });
    if (resetBtn) {
      resetBtn.addEventListener("click", resetScreener);
    }

    const dossierModal = document.getElementById("dossier-modal");
    const dossierTitle = document.getElementById("dossier-modal-title");
    const dossierSub = document.getElementById("dossier-modal-sub");
    const dossierBadges = document.getElementById("dossier-modal-badges");
    const dossierBody = document.getElementById("dossier-modal-body");
    const dossierFootLink = document.getElementById("dossier-modal-link");
    const dossierFootDate = document.getElementById("dossier-modal-date");
    const stockByKey = new Map();
    allStocks.forEach(function (st) {
      stockByKey.set(st.market + ":" + st.code, st);
    });
    const DOSSIER_DIMS = [
      ["moat", "① 护城河与商业拆解"],
      ["financials", "② 财务质量、现金流与债墙"],
      ["valuation_anchor", "③ 估值分位、利率锚与税务/AH"],
      ["shareholder_flow", "④ 股东回报、回购与筹码微结构"],
      ["catalysts", "⑤ 核心催化与 90 天排雷日历"],
      ["bear_case", "⑥ 空头证伪与下行风险底线"],
      ["action_etf", "⑦ 操作边界（IF→THEN）与低费 ETF 替身"],
    ];

    function openStockDossier(key) {
      const st = stockByKey.get(key);
      if (!st || !st.dossier || !dossierModal) return;
      const d = st.dossier;
      const mark = COLOR_MARK[st.color] || "●";
      if (dossierTitle) dossierTitle.textContent = st.name + " (" + st.code + ")";
      if (dossierSub) {
        dossierSub.textContent =
          (d.baseline_note ? d.baseline_note + " ｜ " : "") +
          "赛道：" + st.sector + " ｜ 现价：" + st.price;
      }
      if (dossierBadges) {
        const isCore = d.depth_tier === "core_deep";
        dossierBadges.innerHTML =
          '<span class="mkt-badge mkt-' + escHtml(st.market) + '">' + escHtml(st.market_label) + "</span>" +
          '<span class="act-pill act-' + escHtml(st.color) + '">' + mark + " " + escHtml(st.action_label) + "</span>" +
          '<span class="dossier-depth-badge ' + (isCore ? "depth-core" : "depth-std") + '">' +
          (isCore ? "核心旗舰 7 维全拆解" : "池内标准 7 维档案") + "</span>";
      }
      if (dossierBody) {
        dossierBody.innerHTML =
          '<div class="dossier-grid">' +
          DOSSIER_DIMS.map(function (pair) {
            const val = d[pair[0]] || "暂无补充";
            return (
              '<div class="dossier-dim">' +
              '<div class="dossier-dim-lbl">' + escHtml(pair[1]) + "</div>" +
              '<div class="dossier-dim-txt">' + escHtml(val) + "</div>" +
              "</div>"
            );
          }).join("") +
          "</div>";
      }
      if (dossierFootLink) dossierFootLink.setAttribute("href", st.report_url || "#");
      if (dossierFootDate) {
        const fallbackDate = dossierFootDate.getAttribute("data-default-date") || "最新班次";
        dossierFootDate.textContent = "更新日期：" + (d.updated_at || fallbackDate);
      }
      showDialog(dossierModal);
    }

    if (dossierModal) {
      document.querySelectorAll("[data-action='close-dossier']").forEach(function (b) {
        b.addEventListener("click", function () { hideDialog(dossierModal); });
      });
      dossierModal.addEventListener("click", function (e) {
        if (e.target === dossierModal) hideDialog(dossierModal);
      });
    }

    [tbody, cardsEl].forEach(function (container) {
      if (!container) return;
      container.addEventListener("click", function (e) {
        if (e.target.closest("[data-action='scr-reset-all']")) {
          resetScreener();
          return;
        }
        const dBtn = e.target.closest("[data-dossier-key]");
        if (dBtn) {
          openStockDossier(dBtn.getAttribute("data-dossier-key"));
        }
      });
    });

    window.addEventListener("hashchange", function () {
      if (applyHashToState(true)) {
        renderSectorControls();
        renderScreener(false);
      }
    });

    if (hasData) {
      applyHashToState();
      renderSectorControls();
      renderScreener(false);
      root.classList.add("screener-enhanced");
    }
  }

  /* ------------------------------------------------------------------------
     11. Scorecard & Changelog Tabs (Scrolls Gently to .tab-bar, Not top:0)
     ------------------------------------------------------------------------ */
  const tabBtns = Array.from(document.querySelectorAll("[data-tab-target]"));
  if (tabBtns.length > 0) {
    function keepTabBarVisible() {
      window.requestAnimationFrame(function () {
        const tabBar = document.querySelector(".tab-bar");
        if (!tabBar) return;
        const header = document.querySelector(".site-header");
        const headerH = header ? header.offsetHeight : 64;
        const top = window.scrollY + tabBar.getBoundingClientRect().top - headerH - 12;
        window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
      });
    }

    function activateTab(tabId, updateHash) {
      if (tabId === "changelog") tabId = "equity-changelog";
      if (tabId === "audit-log") tabId = "gold-audit-log";
      const valid = tabBtns.some(function (b) { return b.getAttribute("data-tab-target") === tabId; });
      const targetId = valid ? tabId : tabBtns[0].getAttribute("data-tab-target");
      tabBtns.forEach(function (b) {
        const isAct = b.getAttribute("data-tab-target") === targetId;
        b.classList.toggle("active", isAct);
        b.setAttribute("aria-selected", isAct ? "true" : "false");
      });
      document.querySelectorAll(".tab-panel").forEach(function (p) {
        p.classList.toggle("active", p.id === targetId);
      });
      if (updateHash && history.replaceState) {
        try {
          history.replaceState(null, "", "#" + targetId);
        } catch (_) {}
      }
      return valid;
    }

    tabBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        activateTab(btn.getAttribute("data-tab-target"), true);
      });
    });
    const initHash = (window.location.hash || "").replace(/^#/, "");
    const matchedInit = activateTab(initHash || tabBtns[0].getAttribute("data-tab-target"), false);
    if (initHash && matchedInit) {
      keepTabBarVisible();
      window.addEventListener("load", keepTabBarVisible, { once: true });
    }
    window.addEventListener("hashchange", function () {
      const h = (window.location.hash || "").replace(/^#/, "");
      if (h && activateTab(h, false)) {
        keepTabBarVisible();
      }
    });
  }

  /* ------------------------------------------------------------------------
     12. Supercharged Archive Chronological Filters + URL Hash Sync
     ------------------------------------------------------------------------ */
  const arcItems = Array.from(document.querySelectorAll("[data-arc-item]"));
  if (arcItems.length > 0) {
    const arcState = { market: "all", session: "all", editionType: "all", q: "" };
    const arcMktBtns = Array.from(document.querySelectorAll("[data-arc-market]"));
    const arcSesBtns = Array.from(document.querySelectorAll("[data-arc-session]"));
    const arcTypeBtns = Array.from(document.querySelectorAll("[data-arc-type]"));
    const arcSearchInput = document.getElementById("arc-search");
    const arcClearBtn = document.getElementById("arc-clear-x");
    const arcCountEl = document.getElementById("arc-count");
    const arcEmptyEl = document.getElementById("arc-empty");
    const arcResetBtn = document.getElementById("arc-reset");
    const arcEmptyResetBtn = document.getElementById("arc-empty-reset");

    function normalizeEditionType(val) {
      const s = String(val || "main").trim().toLowerCase();
      if (s === "watch" || s === "holiday_watch" || s === "light") return "watch";
      return "main";
    }

    function syncArchiveUrlHash() {
      if (!history.replaceState) return;
      const nextUrl =
        arcState.market && arcState.market !== "all"
          ? "#" + encodeURIComponent(arcState.market)
          : window.location.pathname + window.location.search;
      try {
        history.replaceState(null, "", nextUrl);
      } catch (_) {}
    }

    function syncArchiveButtons() {
      arcMktBtns.forEach(function (x) {
        x.classList.toggle("active", (x.getAttribute("data-arc-market") || "all") === arcState.market);
      });
      arcSesBtns.forEach(function (x) {
        x.classList.toggle("active", (x.getAttribute("data-arc-session") || "all") === arcState.session);
      });
      arcTypeBtns.forEach(function (x) {
        x.classList.toggle("active", (x.getAttribute("data-arc-type") || "all") === arcState.editionType);
      });
    }

    function applyArchiveFilter() {
      syncArchiveButtons();
      if (arcClearBtn) {
        const hasQ = !!arcState.q;
        arcClearBtn.hidden = !hasQ;
        arcClearBtn.style.display = hasQ ? "" : "none";
      }
      const tokens = arcState.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
      let shown = 0;

      arcItems.forEach(function (el) {
        const m = el.getAttribute("data-market") || "";
        const s = el.getAttribute("data-session") || "";
        const ed = normalizeEditionType(el.getAttribute("data-edition-type"));
        let ok =
          (arcState.market === "all" || m === arcState.market) &&
          (arcState.session === "all" || s === arcState.session) &&
          (arcState.editionType === "all" || ed === arcState.editionType);

        if (ok && tokens.length > 0) {
          const hay = ((el.getAttribute("data-search") || "") + " " + (el.textContent || "")).toLowerCase();
          ok = tokens.every(function (tk) { return hay.indexOf(tk) !== -1; });
        }

        el.style.display = ok ? "" : "none";
        if (ok) shown++;
      });

      document.querySelectorAll(".archive-day").forEach(function (day) {
        const vis = Array.from(day.querySelectorAll("[data-arc-item]")).some(function (el) {
          return el.style.display !== "none";
        });
        day.style.display = vis ? "" : "none";
      });

      if (arcCountEl) {
        arcCountEl.textContent = "共展示 " + shown + " / " + arcItems.length + " 期历史日报";
      }
      if (arcEmptyEl) {
        arcEmptyEl.hidden = shown > 0;
        arcEmptyEl.style.display = shown === 0 ? "" : "none";
      }
    }

    function resetArchiveFilters() {
      arcState.market = "all";
      arcState.session = "all";
      arcState.editionType = "all";
      arcState.q = "";
      if (arcSearchInput) arcSearchInput.value = "";
      syncArchiveUrlHash();
      applyArchiveFilter();
    }

    arcMktBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        arcState.market = b.getAttribute("data-arc-market") || "all";
        syncArchiveUrlHash();
        applyArchiveFilter();
      });
    });
    arcSesBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        arcState.session = b.getAttribute("data-arc-session") || "all";
        applyArchiveFilter();
      });
    });
    arcTypeBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        arcState.editionType = b.getAttribute("data-arc-type") || "all";
        applyArchiveFilter();
      });
    });

    let arcSearchTimer = 0;
    if (arcSearchInput) {
      arcSearchInput.addEventListener("input", function () {
        arcState.q = arcSearchInput.value;
        if (arcClearBtn) {
          const hasQ = !!arcState.q;
          arcClearBtn.hidden = !hasQ;
          arcClearBtn.style.display = hasQ ? "" : "none";
        }
        window.clearTimeout(arcSearchTimer);
        arcSearchTimer = window.setTimeout(applyArchiveFilter, 60);
      });
    }
    if (arcClearBtn) {
      arcClearBtn.addEventListener("click", function () {
        window.clearTimeout(arcSearchTimer);
        arcState.q = "";
        if (arcSearchInput) {
          arcSearchInput.value = "";
          arcSearchInput.focus();
        }
        applyArchiveFilter();
      });
    }
    if (arcResetBtn) arcResetBtn.addEventListener("click", resetArchiveFilters);
    if (arcEmptyResetBtn) arcEmptyResetBtn.addEventListener("click", resetArchiveFilters);

    function applyArchiveHash() {
      const hashMkt = (window.location.hash || "").replace(/^#/, "");
      if (["gold", "a-share", "hk-stock", "us-stock"].indexOf(hashMkt) !== -1) {
        arcState.market = hashMkt;
        return true;
      }
      if (!hashMkt) {
        arcState.market = "all";
        return true;
      }
      return false;
    }

    applyArchiveHash();
    applyArchiveFilter();
    window.addEventListener("hashchange", function () {
      if (applyArchiveHash()) {
        applyArchiveFilter();
      }
    });
  }

  /* ------------------------------------------------------------------------
     13. Multi-Asset Channels Dual-Mode Filter + Four Buckets + Capital Tier
     ------------------------------------------------------------------------ */
  const chCards = Array.from(document.querySelectorAll(".ch-overview-card[data-channel-cat], .channel-card[data-channel-cat]"));
  const chBucketBtns = Array.from(document.querySelectorAll("[data-ch-bucket]"));
  const chCatBtns = Array.from(document.querySelectorAll("[data-ch-cat]"));
  const chCount = document.getElementById("ch-count");
  let chResetBtn = document.getElementById("ch-reset-empty");
  let chBucket = "all";
  let chCat = "all";

  function applyChFilter() {
    if (chCards.length === 0) return;
    let shown = 0;
    chBucketBtns.forEach(function (b) {
      const val = b.getAttribute("data-ch-bucket") || "all";
      b.classList.toggle("active", chCat === "all" && val === chBucket);
    });
    chCatBtns.forEach(function (b) {
      const val = b.getAttribute("data-ch-cat") || "all";
      b.classList.toggle("active", chBucket === "all" && val === chCat);
    });
    chCards.forEach(function (c) {
      const okBucket = chBucket === "all" || c.getAttribute("data-channel-bucket") === chBucket;
      const okCat = chCat === "all" || c.getAttribute("data-channel-cat") === chCat;
      const ok = okBucket && okCat;
      c.style.display = ok ? "" : "none";
      if (ok) shown++;
    });
    if (chCount) {
      if (shown === 0) {
        chCount.textContent = "未找到匹配渠道（0 / " + chCards.length + "）";
        if (!chResetBtn && chCount.parentNode) {
          chResetBtn = document.createElement("button");
          chResetBtn.type = "button";
          chResetBtn.id = "ch-reset-empty";
          chResetBtn.className = "btn btn-sm";
          chResetBtn.textContent = "重置筛选";
          chResetBtn.addEventListener("click", function () {
            chBucket = "all";
            chCat = "all";
            applyChFilter();
          });
          chCount.insertAdjacentElement("afterend", chResetBtn);
        }
        if (chResetBtn) {
          chResetBtn.hidden = false;
          chResetBtn.style.display = "";
        }
      } else {
        chCount.textContent = "显示 " + shown + " / " + chCards.length + " 大合规个人投资渠道";
        if (chResetBtn) {
          chResetBtn.hidden = true;
          chResetBtn.style.display = "none";
        }
      }
    }
  }

  if (chCards.length > 0) {
    chBucketBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        chBucket = b.getAttribute("data-ch-bucket") || "all";
        chCat = "all";
        applyChFilter();
      });
    });
    chCatBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        const nextCat = b.getAttribute("data-ch-cat") || "all";
        if (nextCat === "all") {
          chBucket = "all";
          chCat = "all";
        } else {
          chCat = chCat === nextCat ? "all" : nextCat;
          chBucket = "all";
        }
        applyChFilter();
      });
    });
    applyChFilter();
  }

  /* Four Buckets Quick Jump to Filtered Channels */
  document.querySelectorAll("[data-jump-bucket]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const targetBucket = btn.getAttribute("data-jump-bucket") || "all";
      chBucket = targetBucket;
      chCat = "all";
      applyChFilter();
      const targetSec = document.getElementById("sec-multi-channels");
      if (targetSec) {
        targetSec.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", block: "start" });
      }
    });
  });

  /* Capital Tier Selector (Softly Dims High-Threshold Channels like 20w CDs / 300w Private Funds) */
  const capTierBtns = Array.from(document.querySelectorAll("[data-cap-tier]"));
  const capTierHint = document.getElementById("cap-tier-hint");
  const CAP_TIER_HINTS = {
    all: "当前展示全部档位：建议先留足 3–6 个月活钱与基础保障，再按期限匹配稳钱与长钱。",
    "1-5w": "1–5 万刚起步档：优先 1 元起投的活钱工具、短融/债券 ETF 与低费场外定投；已为您柔和淡化 20 万起购大额存单及 300 万门槛渠道。",
    "10-20w": "10–20 万攒桶金档：可按四笔钱比例搭配活钱池 + 储蓄国债/债券 ETF/银行理财 + 低费宽基 ETF；已淡化 300 万合格投资者渠道。",
    "30-50w": "30–50 万家庭配档：可全盘组合活钱、50 万单行存保线内存款、债券与跨境锁汇工具；300 万专享私募信托仍为您标示淡化提醒。",
  };

  if (capTierBtns.length > 0) {
    capTierBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        const tier = btn.getAttribute("data-cap-tier") || "all";
        capTierBtns.forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        if (capTierHint && CAP_TIER_HINTS[tier]) {
          capTierHint.textContent = CAP_TIER_HINTS[tier];
        }
        chCards.forEach(function (card) {
          const minTier = card.getAttribute("data-min-tier") || "1w";
          let dim = false;
          if (tier === "1-5w") dim = minTier === "20w" || minTier === "300w";
          else if (tier === "10-20w" || tier === "30-50w") dim = minTier === "300w";
          card.classList.toggle("ch-dimmed", dim);
        });
      });
    });
  }

  /* ------------------------------------------------------------------------
     14. Shared ETF 7-Dim Modal + Interactive Global ETF Radar (etfs.html & channels/*.html)
     ------------------------------------------------------------------------ */
  const PREM_LABELS = { normal: "折溢价常规", watch: "买前核参考净值", high_risk: "高溢价/高危预警" };

  function etfRoleClass(it) {
    if (it.gold_locked) return "role-lock";
    const r = String(it.action_role || "");
    if (r.indexOf("高危") !== -1 || r.indexOf("高费") !== -1) return "role-danger";
    if (r.indexOf("现金盾") !== -1) return "role-shield";
    if (r.indexOf("底座") !== -1 || r.indexOf("核心") !== -1 || r.indexOf("卫星") !== -1) return "role-base";
    return "role-watch";
  }

  function createEtfModalController(etfList) {
    const etfModal = document.getElementById("etf-modal");
    const etfModalTitle = document.getElementById("etf-modal-title");
    const etfModalSub = document.getElementById("etf-modal-sub");
    const etfModalBadges = document.getElementById("etf-modal-badges");
    const etfModalBody = document.getElementById("etf-modal-body");
    const etfByCode = new Map();
    etfList.forEach(function (it) {
      if (it && it.code) etfByCode.set(String(it.code), it);
    });

    function openEtfModal(code) {
      const it = etfByCode.get(String(code || ""));
      if (!it || !etfModal) return;
      if (etfModalTitle) etfModalTitle.textContent = it.name + " (" + it.code + ")";
      if (etfModalSub) {
        etfModalSub.textContent =
          "跟踪指数：" + it.tracking_index + " ｜ 规模：" + it.aum + " ｜ 年费率：" + it.fee_total_pct;
      }
      if (etfModalBadges) {
        etfModalBadges.innerHTML =
          '<span class="mkt-badge mkt-' + escHtml(it.market) + '">' + escHtml(it.market_label) + "</span>" +
          '<span class="etf-chan-tag">' + escHtml(it.channel) + "</span>" +
          '<span class="prem-pill prem-' + escHtml(it.premium_status) + '">' + escHtml(PREM_LABELS[it.premium_status] || it.premium_status) + "</span>" +
          '<span class="role-pill ' + etfRoleClass(it) + '">' + escHtml(it.action_role) + "</span>";
      }
      if (etfModalBody) {
        const blocks = [
          ["① 核心投资逻辑与定位", it.thesis_deep],
          ["② 估值 / 股息 / 收益特征", it.yield_or_pe + " ｜ 流动性：" + it.liquidity],
          ["③ 核心前五大重仓 / 底层资产", it.top_holdings],
          ["④ 折溢价雷达与交易纪律", it.premium_note],
          ["⑤ 税费、门槛与制度细则", it.tax_and_rules],
          ["⑥ 核心风险与排雷边界", it.risk_boundary],
          ["⑦ 场外联接或低费替身对照", it.otc_feeder || "暂无场外联接补充，详见频道主表"],
        ];
        etfModalBody.innerHTML =
          '<div class="dossier-grid">' +
          blocks.map(function (b) {
            return (
              '<div class="dossier-dim">' +
              '<div class="dossier-dim-lbl">' + escHtml(b[0]) + "</div>" +
              '<div class="dossier-dim-txt">' + escHtml(b[1]) + "</div>" +
              "</div>"
            );
          }).join("") +
          "</div>";
      }
      showDialog(etfModal);
    }

    if (etfModal && !etfModal.dataset.boundClose) {
      etfModal.dataset.boundClose = "1";
      document.querySelectorAll("[data-action='close-etf']").forEach(function (b) {
        b.addEventListener("click", function () { hideDialog(etfModal); });
      });
      etfModal.addEventListener("click", function (e) {
        if (e.target === etfModal) hideDialog(etfModal);
      });
    }

    return openEtfModal;
  }

  /* 14A. Channel Detail Pages Related ETFs Interactive Modal (#ch-etf-data) */
  const chEtfDataEl = document.getElementById("ch-etf-data");
  if (chEtfDataEl) {
    let chEtfs = [];
    try {
      const parsed = JSON.parse(chEtfDataEl.textContent || "[]");
      if (Array.isArray(parsed)) chEtfs = parsed;
    } catch (_) {
      chEtfs = [];
    }
    if (chEtfs.length > 0) {
      const openChEtfModal = createEtfModalController(chEtfs);
      const chEtfTable = document.getElementById("ch-related-etf-table");
      if (chEtfTable) {
        chEtfTable.addEventListener("click", function (e) {
          const btn = e.target.closest("[data-etf-code]");
          if (btn) openChEtfModal(btn.getAttribute("data-etf-code"));
        });
      }
    }
  }

  /* 14B. Full Global ETF Radar Page (#etf-data) */
  const etfDataEl = document.getElementById("etf-data");
  if (etfDataEl) {
    let allEtfs = [];
    try {
      const parsed = JSON.parse(etfDataEl.textContent || "[]");
      if (Array.isArray(parsed)) allEtfs = parsed;
    } catch (_) {
      allEtfs = [];
    }

    const openEtfModal = createEtfModalController(allEtfs);
    const etfState = {
      q: "",
      market: "all",
      channel: "all",
      preset: "all",
      sortKey: "default",
      sortDir: 1,
    };

    const etfSearch = document.getElementById("etf-search");
    const etfClear = document.getElementById("etf-clear");
    const etfReset = document.getElementById("etf-reset");
    const etfCount = document.getElementById("etf-count");
    const etfTbody = document.getElementById("etf-tbody");
    const etfCardsEl = document.getElementById("etf-cards");
    const etfStatTiles = Array.from(document.querySelectorAll("[data-etf-stat-market]"));
    const etfMktBtns = Array.from(document.querySelectorAll("[data-etf-market]"));
    const etfChanBtns = Array.from(document.querySelectorAll("[data-etf-channel]"));
    const etfPresetBtns = Array.from(document.querySelectorAll("[data-etf-preset]"));
    const etfSortThs = Array.from(document.querySelectorAll("table.etf-table th.sortable"));

    etfSortThs.forEach(function (th) {
      const btn = th.querySelector("button");
      if (btn) btn.disabled = allEtfs.length === 0;
      if (!th.dataset.baseLabel) {
        th.dataset.baseLabel = (th.textContent || "").replace(/\s*[⇅▲▼]\s*$/, "").trim();
      }
    });

    function matchesEtfPreset(it, p) {
      if (!p || p === "all") return true;
      if (p === "low-fee") return isFiniteNum(it.fee_num) && it.fee_num <= 0.20;
      if (p === "cash-shield") return String(it.action_role || "").indexOf("现金盾") !== -1;
      if (p === "base") return !it.gold_locked && String(it.action_role || "").indexOf("底座") !== -1;
      if (p === "high-risk") return it.premium_status === "high_risk" || String(it.action_role || "").indexOf("高危") !== -1;
      if (p === "hide-gold") return !it.gold_locked;
      return true;
    }

    function syncEtfSortHeaders() {
      etfSortThs.forEach(function (th) {
        const key = th.getAttribute("data-sort");
        const base = th.dataset.baseLabel || "";
        const target = th.querySelector("button") || th;
        if (etfState.sortKey === key) {
          const dirStr = etfState.sortDir === 1 ? "asc" : "desc";
          th.setAttribute("data-sort-dir", dirStr);
          th.setAttribute("aria-sort", etfState.sortDir === 1 ? "ascending" : "descending");
          target.textContent = base + (etfState.sortDir === 1 ? " ▲" : " ▼");
        } else {
          th.removeAttribute("data-sort-dir");
          th.removeAttribute("aria-sort");
          target.textContent = base + " ⇅";
        }
      });
    }

    function syncEtfUrlHash() {
      if (!history.replaceState) return;
      const params = [];
      if (etfState.market !== "all") params.push("market=" + encodeURIComponent(etfState.market));
      if (etfState.channel !== "all") params.push("channel=" + encodeURIComponent(etfState.channel));
      if (etfState.preset !== "all") params.push("preset=" + encodeURIComponent(etfState.preset));
      if (etfState.q.trim()) params.push("q=" + encodeURIComponent(etfState.q.trim()));
      const nextUrl = params.length > 0
        ? "#" + params.join("&")
        : window.location.pathname + window.location.search;
      try {
        history.replaceState(null, "", nextUrl);
      } catch (_) {}
    }

    function resetAllEtfs() {
      window.clearTimeout(etfTimer);
      etfState.q = "";
      etfState.market = "all";
      etfState.channel = "all";
      etfState.preset = "all";
      etfState.sortKey = "default";
      etfState.sortDir = 1;
      if (etfSearch) etfSearch.value = "";
      renderEtfs(true);
    }

    function renderEtfs(syncHash) {
      if (syncHash !== false) syncEtfUrlHash();

      etfMktBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-etf-market") || "all") === etfState.market);
      });
      etfStatTiles.forEach(function (t) {
        const sm = t.getAttribute("data-etf-stat-market") || "all";
        const isAct =
          (sm === etfState.market ||
            (sm === "us-global" && (etfState.market === "us-global" || etfState.market === "us-stock" || etfState.market === "global"))) &&
          (sm !== "all" || etfState.preset === "all");
        t.classList.toggle("active", isAct);
        t.setAttribute("aria-pressed", isAct ? "true" : "false");
      });
      etfChanBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-etf-channel") || "all") === etfState.channel);
      });
      etfPresetBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-etf-preset") || "all") === etfState.preset);
      });
      if (etfClear) {
        etfClear.hidden = !etfState.q;
        etfClear.style.display = etfState.q ? "" : "none";
      }

      const tokens = etfState.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
      let rows = allEtfs.filter(function (it) {
        if (etfState.market === "us-global") {
          if (it.market !== "us-stock" && it.market !== "global") return false;
        } else if (etfState.market !== "all" && it.market !== etfState.market) {
          return false;
        }
        if (etfState.channel !== "all" && it.channel !== etfState.channel) return false;
        if (!matchesEtfPreset(it, etfState.preset)) return false;
        if (tokens.length > 0) {
          const hay = (
            it.code + " " + it.name + " " + it.market_label + " " + it.channel + " " +
            it.category + " " + it.tracking_index + " " + it.top_holdings + " " +
            it.thesis_deep + " " + it.action_role + " " + (it.otc_feeder || "")
          ).toLowerCase();
          if (!tokens.every(function (tk) { return hay.indexOf(tk) !== -1; })) return false;
        }
        return true;
      });

      if (etfState.sortKey !== "default") {
        const key = etfState.sortKey;
        const dir = etfState.sortDir;
        rows = rows.slice().sort(function (a, b) {
          if (key === "fee_num") {
            const va = isFiniteNum(a.fee_num) ? a.fee_num : 99;
            const vb = isFiniteNum(b.fee_num) ? b.fee_num : 99;
            return (va - vb) * dir;
          }
          return String(a[key] || "").localeCompare(String(b[key] || ""), "zh-Hans-CN", { numeric: true }) * dir;
        });
      }
      syncEtfSortHeaders();

      if (etfCount) {
        etfCount.textContent = "显示 " + rows.length + " / " + allEtfs.length + " 只重点 ETF";
      }

      if (etfTbody) {
        if (rows.length === 0) {
          etfTbody.innerHTML =
            '<tr><td colspan="7"><div class="empty-state">' +
            '<div class="empty-title">未找到匹配的 ETF</div>' +
            '<div class="empty-sub">尝试清空搜索词或切换市场与通道</div>' +
            '<button type="button" class="btn btn-sm" data-action="etf-reset-all">清空所有筛选条件</button>' +
            "</div></td></tr>";
        } else {
          etfTbody.innerHTML = rows.map(function (it) {
            return (
              "<tr>" +
              '<td><div><strong>' + escHtml(it.name) + '</strong></div><div><span class="code-tag">' + escHtml(it.code) + '</span> <span class="etf-chan-tag">' + escHtml(it.category) + "</span></div></td>" +
              '<td><div><span class="mkt-badge mkt-' + escHtml(it.market) + '">' + escHtml(it.market_label) + '</span></div><div><span class="etf-chan-tag">' + escHtml(it.channel) + "</span></div></td>" +
              "<td><div>" + escHtml(it.tracking_index) + '</div><div class="sec-sub">' + escHtml(it.yield_or_pe) + "</div></td>" +
              '<td class="col-num"><strong>' + escHtml(it.fee_total_pct) + "</strong></td>" +
              "<td><div><strong>" + escHtml(it.aum) + '</strong></div><div class="sec-sub">' + escHtml(it.liquidity) + "</div></td>" +
              '<td><div><span class="prem-pill prem-' + escHtml(it.premium_status) + '">' + escHtml(PREM_LABELS[it.premium_status] || it.premium_status) + '</span></div><div class="sec-sub">' + escHtml(it.premium_note) + "</div></td>" +
              '<td><div><span class="role-pill ' + etfRoleClass(it) + '">' + escHtml(it.action_role) + '</span></div><div style="margin-top:5px;"><button type="button" class="dossier-btn" style="margin-left:0;" data-etf-code="' + escHtml(it.code) + '">深度拆解</button></div></td>' +
              "</tr>"
            );
          }).join("");
        }
      }

      if (etfCardsEl) {
        if (rows.length === 0) {
          etfCardsEl.innerHTML =
            '<div class="panel-card empty-state">' +
            '<div class="empty-title">未找到匹配的 ETF</div>' +
            '<div class="empty-sub">尝试清空搜索词或切换市场与通道</div>' +
            '<button type="button" class="btn btn-sm" data-action="etf-reset-all">清空所有筛选条件</button>' +
            "</div>";
        } else {
          etfCardsEl.innerHTML = rows.map(function (it) {
            return (
              '<div class="etf-card">' +
              '<div class="etf-card-top">' +
              '<div><span class="mkt-badge mkt-' + escHtml(it.market) + '">' + escHtml(it.market_label) + "</span> <strong>" + escHtml(it.name) + '</strong> <span class="code-tag">' + escHtml(it.code) + "</span></div>" +
              '<span class="role-pill ' + etfRoleClass(it) + '">' + escHtml(it.action_role) + "</span>" +
              "</div>" +
              '<div class="etf-card-meta"><span><strong>通道：</strong>' + escHtml(it.channel) + "</span><span><strong>费率：</strong>" + escHtml(it.fee_total_pct) + "</span><span><strong>规模：</strong>" + escHtml(it.aum) + "</span></div>" +
              '<div><span class="prem-pill prem-' + escHtml(it.premium_status) + '">' + escHtml(PREM_LABELS[it.premium_status] || it.premium_status) + '</span> <span class="sec-sub">' + escHtml(it.yield_or_pe) + "</span></div>" +
              '<div class="sc-summary">' + escHtml(it.thesis_deep) + "</div>" +
              '<div><button type="button" class="dossier-btn" style="margin-left:0;" data-etf-code="' + escHtml(it.code) + '">查看 ETF 7 维深度拆解</button></div>' +
              "</div>"
            );
          }).join("");
        }
      }
    }

    let etfTimer = 0;
    if (etfSearch) {
      etfSearch.addEventListener("input", function () {
        etfState.q = etfSearch.value;
        if (etfClear) {
          etfClear.hidden = !etfState.q;
          etfClear.style.display = etfState.q ? "" : "none";
        }
        window.clearTimeout(etfTimer);
        etfTimer = window.setTimeout(function () { renderEtfs(true); }, 60);
      });
    }
    if (etfClear) {
      etfClear.addEventListener("click", function () {
        window.clearTimeout(etfTimer);
        etfState.q = "";
        if (etfSearch) { etfSearch.value = ""; etfSearch.focus(); }
        renderEtfs(true);
      });
    }
    if (etfReset) {
      etfReset.addEventListener("click", resetAllEtfs);
    }
    etfStatTiles.forEach(function (tile) {
      function handleStatSelect() {
        const sm = tile.getAttribute("data-etf-stat-market") || "all";
        etfState.market = sm !== "all" && etfState.market === sm ? "all" : sm;
        if (sm === "all") {
          etfState.channel = "all";
          etfState.preset = "all";
        }
        renderEtfs(true);
      }
      tile.addEventListener("click", handleStatSelect);
      tile.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleStatSelect();
        }
      });
    });
    etfMktBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        etfState.market = b.getAttribute("data-etf-market") || "all";
        renderEtfs(true);
      });
    });
    etfChanBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        etfState.channel = b.getAttribute("data-etf-channel") || "all";
        renderEtfs(true);
      });
    });
    etfPresetBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        const p = b.getAttribute("data-etf-preset") || "all";
        etfState.preset = etfState.preset === p && p !== "all" ? "all" : p;
        renderEtfs(true);
      });
    });
    etfSortThs.forEach(function (th) {
      const btn = th.querySelector("button") || th;
      btn.addEventListener("click", function () {
        const k = th.getAttribute("data-sort");
        if (etfState.sortKey === k) etfState.sortDir *= -1;
        else { etfState.sortKey = k; etfState.sortDir = 1; }
        renderEtfs(false);
      });
    });
    [etfTbody, etfCardsEl].forEach(function (container) {
      if (!container) return;
      container.addEventListener("click", function (e) {
        if (e.target.closest("[data-action='etf-reset-all']")) {
          resetAllEtfs();
          return;
        }
        const btn = e.target.closest("[data-etf-code]");
        if (btn) openEtfModal(btn.getAttribute("data-etf-code"));
      });
    });

    function applyEtfHash() {
      etfState.q = "";
      etfState.market = "all";
      etfState.channel = "all";
      etfState.preset = "all";
      const raw = (window.location.hash || "").replace(/^#/, "").trim();
      if (!raw) {
        if (etfSearch) etfSearch.value = "";
        return;
      }
      raw.split("&").forEach(function (pair) {
        const eq = pair.indexOf("=");
        if (eq <= 0) return;
        const k = safeDecode(pair.slice(0, eq));
        const v = safeDecode(pair.slice(eq + 1));
        if (k === "market" && ["all", "a-share", "hk-stock", "us-stock", "global", "us-global", "multi-asset"].indexOf(v) !== -1) {
          etfState.market = v;
        } else if (k === "channel" && v) {
          etfState.channel = v;
        } else if (k === "preset" && ["all", "low-fee", "base", "cash-shield", "high-risk", "hide-gold"].indexOf(v) !== -1) {
          etfState.preset = v;
        } else if (k === "q") {
          etfState.q = v;
        }
      });
      if (etfSearch) etfSearch.value = etfState.q;
    }

    if (allEtfs.length > 0) {
      applyEtfHash();
      renderEtfs(false);
      root.classList.add("etf-enhanced");
      window.addEventListener("hashchange", function () {
        applyEtfHash();
        renderEtfs(false);
      });
    }
  }

  /* ------------------------------------------------------------------------
     15. Beginner Guide Glossary Search & Category Filter (guide.html)
     ------------------------------------------------------------------------ */
  const guideTermGrid = document.getElementById("guide-term-grid");
  if (guideTermGrid) {
    const gCards = Array.from(guideTermGrid.querySelectorAll(".guide-term-card"));
    const gSearch = document.getElementById("guide-term-search");
    const gClear = document.getElementById("guide-term-clear");
    const gReset = document.getElementById("guide-term-reset");
    const gEmptyReset = document.getElementById("guide-empty-reset");
    const gCount = document.getElementById("guide-term-count");
    const gEmpty = document.getElementById("guide-term-empty");
    const gCatBtns = Array.from(document.querySelectorAll("[data-guide-cat]"));
    const gState = { cat: "all", q: "" };
    let gTimer = 0;

    function ensureGuideSearchVisible() {
      if (!gSearch) return;
      const panel = gSearch.closest(".filter-panel") || gSearch;
      const rect = panel.getBoundingClientRect();
      const header = document.querySelector(".site-header");
      const headerH = header ? header.offsetHeight : 64;
      if (rect.top < headerH + 6 || rect.bottom > window.innerHeight - 140) {
        const top = window.scrollY + rect.top - headerH - 12;
        window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
      }
    }

    function applyGuideFilter(ensureVisible) {
      gCatBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-guide-cat") || "all") === gState.cat);
      });
      if (gClear) {
        gClear.hidden = !gState.q;
        gClear.style.display = gState.q ? "" : "none";
      }
      const tokens = gState.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
      let shown = 0;
      gCards.forEach(function (card) {
        const cat = card.getAttribute("data-guide-term-cat") || "";
        const hay = (card.getAttribute("data-guide-term-search") || card.textContent || "").toLowerCase();
        const okCat = gState.cat === "all" || cat === gState.cat;
        const okQ = tokens.length === 0 || tokens.every(function (tk) { return hay.indexOf(tk) !== -1; });
        const ok = okCat && okQ;
        card.style.display = ok ? "" : "none";
        if (ok) shown++;
      });
      if (gCount) {
        gCount.textContent = "共收录 " + shown + " / " + gCards.length + " 条高频白话词条";
      }
      if (gEmpty) {
        gEmpty.hidden = shown > 0;
        gEmpty.style.display = shown === 0 ? "" : "none";
      }
      if (ensureVisible) {
        ensureGuideSearchVisible();
      }
    }

    function resetGuideFilter() {
      window.clearTimeout(gTimer);
      gState.cat = "all";
      gState.q = "";
      if (gSearch) gSearch.value = "";
      applyGuideFilter(true);
    }

    if (gSearch) {
      gSearch.addEventListener("input", function () {
        gState.q = gSearch.value;
        if (gClear) {
          gClear.hidden = !gState.q;
          gClear.style.display = gState.q ? "" : "none";
        }
        window.clearTimeout(gTimer);
        gTimer = window.setTimeout(function () { applyGuideFilter(true); }, 50);
      });
    }
    if (gClear) {
      gClear.addEventListener("click", function () {
        window.clearTimeout(gTimer);
        gState.q = "";
        if (gSearch) { gSearch.value = ""; gSearch.focus(); }
        applyGuideFilter(true);
      });
    }
    if (gReset) gReset.addEventListener("click", resetGuideFilter);
    if (gEmptyReset) gEmptyReset.addEventListener("click", resetGuideFilter);
    gCatBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        gState.cat = b.getAttribute("data-guide-cat") || "all";
        applyGuideFilter(true);
      });
    });
    applyGuideFilter(false);
  }
})();
