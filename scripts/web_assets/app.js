/* ==========================================================================
   Global Investment Research Portal — Interactive Client Engine (Zero Deps)
   Features: Obsidian Dark Mode, Font Scaler, Reading Progress & Back-to-Top,
             TOC ScrollSpy & Mobile Drawer, Command-K Quick Jump Palette,
             Chart Lightbox + Shortcuts, 231-Stock Screener, Scorecard Tabs,
             Multi-Facet Archive Search
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
     2. Auto-Scroll Active Mobile Nav Pill into View
     ------------------------------------------------------------------------ */
  const mainNav = document.querySelector(".main-nav");
  if (mainNav) {
    const activePill = mainNav.querySelector(".nav-pill.active");
    if (activePill && mainNav.scrollWidth > mainNav.clientWidth + 2) {
      try {
        activePill.scrollIntoView({ inline: "center", block: "nearest", behavior: "auto" });
      } catch (_) {
        activePill.scrollIntoView(false);
      }
    }
  }

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
  document.querySelectorAll("[data-action='print']").forEach(function (el) {
    el.addEventListener("click", function () {
      window.print();
    });
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
     6. TOC ScrollSpy (Desktop Sidebar + Mobile TOC Strip) & Drawer
     ------------------------------------------------------------------------ */
  const tocLinks = Array.from(document.querySelectorAll(".toc-sidebar .toc-link"));
  const mobileTocPills = Array.from(document.querySelectorAll(".mobile-toc-strip .mobile-toc-pill"));

  if (tocLinks.length > 0 || mobileTocPills.length > 0) {
    const sourceLinks = tocLinks.length > 0 ? tocLinks : mobileTocPills;
    const headings = sourceLinks
      .map(function (a) {
        const href = a.getAttribute("href") || "";
        const id = href.replace(/^#/, "");
        return { id: id, el: document.getElementById(id) };
      })
      .filter(function (x) { return !!x.el; });

    let activeId = "";
    function syncToc() {
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
      if (!current || current.id === activeId) return;
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

      const mobileStrip = document.querySelector(".mobile-toc-strip");
      mobileTocPills.forEach(function (pill) {
        const isAct = (pill.getAttribute("href") || "") === "#" + activeId;
        pill.classList.toggle("active", isAct);
        if (isAct && mobileStrip && mobileStrip.scrollWidth > mobileStrip.clientWidth + 2) {
          const left = pill.offsetLeft - mobileStrip.clientWidth / 2 + pill.clientWidth / 2;
          mobileStrip.scrollTo({ left: Math.max(0, left), behavior: "auto" });
        }
      });
    }

    window.addEventListener("scroll", syncToc, { passive: true });
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
      cmdList.innerHTML = '<div class="cmd-empty">未找到匹配的页面或报告，试试输入「黄金」「A股」「记分卡」「筛选」</div>';
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
     8. Chart Lightbox Fullscreen Zoom Modal + Keyboard Shortcuts
     ------------------------------------------------------------------------ */
  const chartModal = document.getElementById("chart-modal");
  const chartModalTitle = document.getElementById("chart-modal-title");
  const chartModalCanvas = document.getElementById("chart-modal-canvas");
  let zoomPct = 100;

  function applyChartZoom(pct) {
    zoomPct = Math.max(70, Math.min(240, pct));
    if (chartModalCanvas) {
      if (zoomPct === 100) {
        chartModalCanvas.style.width = "min(1080px, 96vw)";
      } else {
        chartModalCanvas.style.width = Math.round(1080 * (zoomPct / 100)) + "px";
      }
    }
    const zLbl = document.getElementById("chart-zoom-readout");
    if (zLbl) zLbl.textContent = zoomPct + "%";
  }

  function openChartModal(chartBox) {
    if (!chartModal || !chartModalCanvas) return;
    const svg = chartBox.querySelector("svg");
    if (!svg) return;
    const titleEl = chartBox.querySelector(".chart-title");
    if (chartModalTitle) {
      chartModalTitle.textContent = titleEl ? titleEl.textContent.trim() : "图表放大视图";
    }
    chartModalCanvas.innerHTML = "";
    const clone = svg.cloneNode(true);
    clone.removeAttribute("style");
    chartModalCanvas.appendChild(clone);
    applyChartZoom(window.innerWidth < 720 ? 115 : 100);
    showDialog(chartModal);
  }

  function closeChartModal() {
    if (!chartModal) return;
    hideDialog(chartModal);
  }

  document.querySelectorAll(".chart-box").forEach(function (box) {
    const svg = box.querySelector("svg");
    if (!svg) return;
    if (!box.querySelector(".chart-zoom-btn")) {
      const zbtn = document.createElement("button");
      zbtn.type = "button";
      zbtn.className = "chart-zoom-btn";
      zbtn.textContent = "🔍 放大";
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
      b.addEventListener("click", function () { applyChartZoom(100); });
    });
    chartModal.addEventListener("click", function (e) {
      if (e.target === chartModal || e.target.classList.contains("chart-modal-stage")) {
        closeChartModal();
      }
    });
  }

  /* Global Keyboard Dispatcher (Cmd/Ctrl+K, Chart Shortcuts, Modal Escape/Tab) */
  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && cmdPalette) {
      e.preventDefault();
      if (cmdPalette.classList.contains("open")) {
        closeCmdPalette();
      } else {
        closeChartModal();
        setTocDrawer(false);
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

    if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey && !isEditableElement(document.activeElement)) {
      const scrSearch =
        document.getElementById("scr-search") ||
        document.getElementById("etf-search") ||
        document.getElementById("arc-search");
      if (scrSearch) {
        e.preventDefault();
        scrSearch.focus();
        scrSearch.select();
      }
    }
  });

  /* ------------------------------------------------------------------------
     9. Supercharged 231-Stock Global Screener (#screener-data)
     ------------------------------------------------------------------------ */
  const screenerDataEl = document.getElementById("screener-data");
  if (screenerDataEl) {
    let allStocks = [];
    try {
      const parsed = JSON.parse(screenerDataEl.textContent || "[]");
      if (Array.isArray(parsed)) {
        allStocks = parsed.map(function (st) {
          const item = Object.assign({}, st);
          if (item.div_pct === undefined && typeof item.valuation === "string") {
            const dm = item.valuation.match(/股息(?:率)?\s*([0-9]+(?:\.[0-9]+)?)%/);
            if (dm) item.div_pct = parseFloat(dm[1]);
          }
          if (item.ah_pct === undefined && typeof item.valuation === "string") {
            const am = item.valuation.match(/AH[^0-9+\-]*([+\-]?[0-9]+(?:\.[0-9]+)?)%/i);
            if (am) item.ah_pct = parseFloat(am[1]);
          }
          if (item.pe_num === undefined && typeof item.valuation === "string") {
            const pm = item.valuation.match(/PE(?:\([^)]*\))?\s*([0-9]+(?:\.[0-9]+)?)x/i);
            if (pm) item.pe_num = parseFloat(pm[1]);
          }
          return item;
        });
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
    const sectorSel = document.getElementById("scr-sector");
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

    function isFiniteNum(v) {
      return typeof v === "number" && isFinite(v);
    }

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
        t.classList.toggle("active", c === state.color && (c !== "all" || state.preset === "all"));
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

      // Prune selected sectors that do not exist under current market
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

      if (sectorSel) {
        sectorSel.innerHTML = '<option value="all">全部赛道 (' + list.length + ")</option>";
        list.forEach(function (entry) {
          const opt = document.createElement("option");
          opt.value = entry[0];
          opt.textContent = entry[0] + " (" + entry[1] + ")";
          sectorSel.appendChild(opt);
        });
        sectorSel.value = state.sectors.size === 1 ? Array.from(state.sectors)[0] : "all";
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
                '<td><span class="mkt-badge mkt-' + escHtml(st.market) + '">' + escHtml(st.market_label) + "</span></td>" +
                '<td class="col-sticky"><strong>' + escHtml(st.name) + '</strong> <span class="code-tag">' + escHtml(st.code) + "</span></td>" +
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

    /* Event Wiring for Screener */
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
    if (sectorSel) {
      sectorSel.addEventListener("change", function () {
        state.sectors.clear();
        if (sectorSel.value && sectorSel.value !== "all") {
          state.sectors.add(sectorSel.value);
        }
        renderSectorControls();
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
        renderScreener(true);
      });
    });
    statTiles.forEach(function (tile) {
      tile.addEventListener("click", function () {
        const col = tile.getAttribute("data-stat-color") || "all";
        state.color = col !== "all" && state.color === col ? "all" : col;
        if (col === "all") state.preset = "all";
        else if (state.preset === "base" && state.color !== "g") state.preset = "all";
        renderScreener(true);
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
      if (dossierFootDate) dossierFootDate.textContent = "更新日期：" + (d.updated_at || "2026-11-26");
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
     10. Scorecard & Changelog Tabs (with URL Hash Sync)
     ------------------------------------------------------------------------ */
  const tabBtns = Array.from(document.querySelectorAll("[data-tab-target]"));
  if (tabBtns.length > 0) {
    function keepTabBarVisible() {
      window.requestAnimationFrame(function () {
        window.scrollTo({ top: 0, behavior: "auto" });
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
     11. Supercharged Archive Chronological Filters + Instant Search
     ------------------------------------------------------------------------ */
  const arcItems = Array.from(document.querySelectorAll("[data-arc-item]"));
  if (arcItems.length > 0) {
    const arcState = { market: "all", session: "all", editionType: "all", q: "" };
    const arcMktBtns = Array.from(document.querySelectorAll("[data-arc-market]"));
    const arcSesBtns = Array.from(document.querySelectorAll("[data-arc-session]"));
    const arcTypeBtns = Array.from(document.querySelectorAll("[data-arc-type]"));
    const arcSearchInput = document.getElementById("arc-search");
    const arcCountEl = document.getElementById("arc-count");
    const arcEmptyEl = document.getElementById("arc-empty");
    const arcResetBtn = document.getElementById("arc-reset");
    const arcEmptyResetBtn = document.getElementById("arc-empty-reset");

    function normalizeEditionType(val) {
      const s = String(val || "main").trim().toLowerCase();
      if (s === "watch" || s === "holiday_watch" || s === "light") return "watch";
      return "main";
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
      applyArchiveFilter();
    }

    arcMktBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        arcState.market = b.getAttribute("data-arc-market") || "all";
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
        window.clearTimeout(arcSearchTimer);
        arcSearchTimer = window.setTimeout(applyArchiveFilter, 60);
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
     12. Multi-Asset Channels Category Filter (index.html & channels.html)
     ------------------------------------------------------------------------ */
  const chCards = Array.from(document.querySelectorAll(".ch-overview-card[data-channel-cat], .channel-card[data-channel-cat]"));
  if (chCards.length > 0) {
    const chBtns = Array.from(document.querySelectorAll("[data-ch-cat]"));
    const chCount = document.getElementById("ch-count");
    let chCat = "all";
    function applyChFilter() {
      let shown = 0;
      chBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-ch-cat") || "all") === chCat);
      });
      chCards.forEach(function (c) {
        const ok = chCat === "all" || c.getAttribute("data-channel-cat") === chCat;
        c.style.display = ok ? "" : "none";
        if (ok) shown++;
      });
      if (chCount) {
        chCount.textContent = "显示 " + shown + " / " + chCards.length + " 大合规个人投资渠道";
      }
    }
    chBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        chCat = b.getAttribute("data-ch-cat") || "all";
        applyChFilter();
      });
    });
    applyChFilter();
  }

  /* ------------------------------------------------------------------------
     13. Interactive 100+ Global ETF Radar & Deep Modal (etfs.html)
     ------------------------------------------------------------------------ */
  const etfDataEl = document.getElementById("etf-data");
  if (etfDataEl) {
    let allEtfs = [];
    try {
      const parsed = JSON.parse(etfDataEl.textContent || "[]");
      if (Array.isArray(parsed)) allEtfs = parsed;
    } catch (_) {
      allEtfs = [];
    }

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
    const etfMktBtns = Array.from(document.querySelectorAll("[data-etf-market]"));
    const etfChanBtns = Array.from(document.querySelectorAll("[data-etf-channel]"));
    const etfPresetBtns = Array.from(document.querySelectorAll("[data-etf-preset]"));
    const etfSortThs = Array.from(document.querySelectorAll("table.etf-table th.sortable"));

    const etfModal = document.getElementById("etf-modal");
    const etfModalTitle = document.getElementById("etf-modal-title");
    const etfModalSub = document.getElementById("etf-modal-sub");
    const etfModalBadges = document.getElementById("etf-modal-badges");
    const etfModalBody = document.getElementById("etf-modal-body");
    const etfByCode = new Map();
    allEtfs.forEach(function (it) { etfByCode.set(it.code, it); });

    const PREM_LABELS = { normal: "折溢价常规", watch: "买前核参考净值", high_risk: "高溢价/高危预警" };

    function etfRoleClass(it) {
      if (it.gold_locked) return "role-lock";
      const r = String(it.action_role || "");
      if (r.indexOf("高危") !== -1 || r.indexOf("高费") !== -1) return "role-danger";
      if (r.indexOf("现金盾") !== -1) return "role-shield";
      if (r.indexOf("底座") !== -1 || r.indexOf("核心") !== -1 || r.indexOf("卫星") !== -1) return "role-base";
      return "role-watch";
    }

    function openEtfModal(code) {
      const it = etfByCode.get(code);
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

    if (etfModal) {
      document.querySelectorAll("[data-action='close-etf']").forEach(function (b) {
        b.addEventListener("click", function () { hideDialog(etfModal); });
      });
      etfModal.addEventListener("click", function (e) {
        if (e.target === etfModal) hideDialog(etfModal);
      });
    }

    function matchesEtfPreset(it, p) {
      if (!p || p === "all") return true;
      if (p === "low-fee") return typeof it.fee_num === "number" && it.fee_num <= 0.20;
      if (p === "cash-shield") return String(it.action_role || "").indexOf("现金盾") !== -1;
      if (p === "base") return !it.gold_locked && String(it.action_role || "").indexOf("底座") !== -1;
      if (p === "high-risk") return it.premium_status === "high_risk" || String(it.action_role || "").indexOf("高危") !== -1;
      if (p === "hide-gold") return !it.gold_locked;
      return true;
    }

    function renderEtfs() {
      etfMktBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-etf-market") || "all") === etfState.market);
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
        if (etfState.market !== "all" && it.market !== etfState.market) return false;
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
            return ((a.fee_num || 99) - (b.fee_num || 99)) * dir;
          }
          return String(a[key] || "").localeCompare(String(b[key] || ""), "zh-Hans-CN", { numeric: true }) * dir;
        });
      }

      if (etfCount) {
        etfCount.textContent = "显示 " + rows.length + " / " + allEtfs.length + " 只重点 ETF";
      }

      if (etfTbody) {
        if (rows.length === 0) {
          etfTbody.innerHTML = '<tr><td colspan="7"><div class="empty-state"><div class="empty-title">未找到匹配的 ETF</div><div class="empty-sub">尝试清空搜索词或切换市场与通道</div></div></td></tr>';
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
          etfCardsEl.innerHTML = '<div class="panel-card empty-state"><div class="empty-title">未找到匹配的 ETF</div></div>';
        } else {
          etfCardsEl.innerHTML = rows.map(function (it) {
            return (
              '<div class="etf-card">' +
              '<div class="etf-card-top">' +
              '<div><span class="mkt-badge mkt-' + escHtml(it.market) + '">' + escHtml(it.market_label) + "</span> <strong>" + escHtml(it.name) + '</strong> <span class="code-tag">' + escHtml(it.code) + "</span></div>" +
              '<span class="role-pill ' + etfRoleClass(it) + '">' + escHtml(it.action_role) + "</span>" +
              "</div>" +
              '<div class="etf-card-meta"><span><strong>通道：</strong>' + escHtml(it.channel) + "</span><span><strong>费率：</strong>" + escHtml(it.fee_total_pct) + "</span><span><strong>规模：</strong>" + escHtml(it.aum) + "</span></div>" +
              '<div><span class="prem-pill prem-' + escHtml(it.premium_status) + '">' + escHtml(PREM_LABELS[it.premium_status] || it.premium_status) + "</span> <span class=\"sec-sub\">" + escHtml(it.yield_or_pe) + "</span></div>" +
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
        window.clearTimeout(etfTimer);
        etfTimer = window.setTimeout(renderEtfs, 60);
      });
    }
    if (etfClear) {
      etfClear.addEventListener("click", function () {
        etfState.q = "";
        if (etfSearch) { etfSearch.value = ""; etfSearch.focus(); }
        renderEtfs();
      });
    }
    if (etfReset) {
      etfReset.addEventListener("click", function () {
        etfState.q = "";
        etfState.market = "all";
        etfState.channel = "all";
        etfState.preset = "all";
        etfState.sortKey = "default";
        etfState.sortDir = 1;
        if (etfSearch) etfSearch.value = "";
        renderEtfs();
      });
    }
    etfMktBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        etfState.market = b.getAttribute("data-etf-market") || "all";
        renderEtfs();
      });
    });
    etfChanBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        etfState.channel = b.getAttribute("data-etf-channel") || "all";
        renderEtfs();
      });
    });
    etfPresetBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        const p = b.getAttribute("data-etf-preset") || "all";
        etfState.preset = etfState.preset === p && p !== "all" ? "all" : p;
        renderEtfs();
      });
    });
    etfSortThs.forEach(function (th) {
      const btn = th.querySelector("button") || th;
      if (btn.tagName === "BUTTON") btn.disabled = false;
      btn.addEventListener("click", function () {
        const k = th.getAttribute("data-sort");
        if (etfState.sortKey === k) etfState.sortDir *= -1;
        else { etfState.sortKey = k; etfState.sortDir = 1; }
        renderEtfs();
      });
    });
    [etfTbody, etfCardsEl].forEach(function (container) {
      if (!container) return;
      container.addEventListener("click", function (e) {
        const btn = e.target.closest("[data-etf-code]");
        if (btn) openEtfModal(btn.getAttribute("data-etf-code"));
      });
    });

    function applyEtfHash() {
      const raw = (window.location.hash || "").replace(/^#/, "").trim();
      if (!raw) return;
      raw.split("&").forEach(function (pair) {
        const eq = pair.indexOf("=");
        if (eq <= 0) return;
        const k = safeDecode(pair.slice(0, eq));
        const v = safeDecode(pair.slice(eq + 1));
        if (k === "market" && ["all", "a-share", "hk-stock", "us-stock", "global", "multi-asset"].indexOf(v) !== -1) {
          etfState.market = v;
        } else if (k === "preset" && ["all", "low-fee", "base", "cash-shield", "high-risk", "hide-gold"].indexOf(v) !== -1) {
          etfState.preset = v;
        }
      });
    }

    if (allEtfs.length > 0) {
      applyEtfHash();
      renderEtfs();
      root.classList.add("etf-enhanced");
      window.addEventListener("hashchange", function () {
        applyEtfHash();
        renderEtfs();
      });
    }
  }
})();
