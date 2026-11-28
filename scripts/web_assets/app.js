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

  function applyTheme(theme, persist) {
    const next = theme === "dark" ? "dark" : "light";
    root.setAttribute("data-theme", next);
    if (persist) {
      try {
        localStorage.setItem("gir_theme", next);
      } catch (_) {}
    }

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
    applyTheme(getTheme(), false);
    themeBtn.addEventListener("click", function () {
      applyTheme(getTheme() === "dark" ? "light" : "dark", true);
    });
  }
  if (window.matchMedia) {
    const colorSchemeMq = window.matchMedia("(prefers-color-scheme: dark)");
    const onSchemeChange = function (e) {
      let saved = null;
      try {
        saved = localStorage.getItem("gir_theme");
      } catch (_) {}
      if (!saved) {
        applyTheme(e.matches ? "dark" : "light", false);
      }
    };
    if (typeof colorSchemeMq.addEventListener === "function") {
      colorSchemeMq.addEventListener("change", onSchemeChange);
    } else if (typeof colorSchemeMq.addListener === "function") {
      colorSchemeMq.addListener(onSchemeChange);
    }
  }

  /* ------------------------------------------------------------------------
     2. Auto-Scroll Active Mobile Nav Pill, Subnav Pill & Sticky Scroll Offset
     ------------------------------------------------------------------------ */
  function getStickyOffset() {
    const hdr = document.querySelector(".site-header");
    const hdrH = (hdr && hdr.offsetHeight) || 60;
    const subnav = document.querySelector(".subnav-bar");
    const subH =
      subnav && window.getComputedStyle && window.getComputedStyle(subnav).position === "sticky"
        ? subnav.offsetHeight || 0
        : 0;
    return hdrH + subH + 12;
  }

  function centerActiveScrollPill(containerSel, pillSel) {
    const container = document.querySelector(containerSel);
    if (!container) return;
    const activePill = container.querySelector(pillSel);
    if (activePill && container.scrollWidth > container.clientWidth + 2) {
      const targetLeft = Math.max(0, activePill.offsetLeft - (container.clientWidth - activePill.offsetWidth) / 2);
      container.scrollLeft = targetLeft;
    }
  }
  /* Keep sticky table thead flush beneath .toolbar-sticky on wide desktop */
  const stickyToolbarEl = document.querySelector(".toolbar-sticky");
  if (stickyToolbarEl) {
    const syncStickyThTop = function () {
      const hdr = document.querySelector(".site-header");
      const hdrH = (hdr && hdr.offsetHeight) || 61;
      const tbH = stickyToolbarEl.offsetHeight || 96;
      document.documentElement.style.setProperty("--sticky-th-top", hdrH + tbH + 2 + "px");
    };
    syncStickyThTop();
    if (typeof ResizeObserver === "function") {
      try {
        new ResizeObserver(syncStickyThTop).observe(stickyToolbarEl);
      } catch (_) {}
    }
    window.addEventListener("resize", syncStickyThTop, { passive: true });
  }

  centerActiveScrollPill(".main-nav", ".nav-pill.active");
  centerActiveScrollPill(".subnav-inner", ".subnav-link.active");
  centerActiveScrollPill(".ch-switcher", ".ch-switch-pill.active");

  /* ------------------------------------------------------------------------
     2B. Grouped Desktop Nav Dropdowns (.nav-group / .nav-drop-btn / .nav-dropdown)
     ------------------------------------------------------------------------ */
  const navGroups = Array.from(document.querySelectorAll(".nav-group"));

  function closeAllNavDropdowns(exceptGroup) {
    let closedAny = false;
    navGroups.forEach(function (grp) {
      if (exceptGroup && grp === exceptGroup) return;
      const btn = grp.querySelector(".nav-drop-btn");
      const menu = grp.querySelector(".nav-dropdown");
      const wasOpen = (menu && !menu.hidden) || grp.classList.contains("open");
      if (wasOpen) closedAny = true;
      if (menu) menu.hidden = true;
      if (btn) btn.setAttribute("aria-expanded", "false");
      grp.classList.remove("open");
    });
    return closedAny;
  }

  if (navGroups.length > 0) {
    navGroups.forEach(function (grp) {
      const btn = grp.querySelector(".nav-drop-btn");
      const menu = grp.querySelector(".nav-dropdown");
      if (!btn || !menu) return;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        const willOpen = menu.hidden;
        closeAllNavDropdowns(willOpen ? grp : null);
        menu.hidden = !willOpen;
        btn.setAttribute("aria-expanded", willOpen ? "true" : "false");
        grp.classList.toggle("open", willOpen);
      });
    });

    document.addEventListener("click", function (e) {
      if (!e.target.closest(".nav-group")) {
        closeAllNavDropdowns(null);
      }
    });
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

  const decBtn = document.getElementById("font-dec");
  const incBtn = document.getElementById("font-inc");

  function applyScale(val) {
    readScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, Math.round(val * 100) / 100));
    root.style.setProperty("--read-scale", String(readScale));
    if (decBtn) decBtn.disabled = readScale <= MIN_SCALE + 0.001;
    if (incBtn) incBtn.disabled = readScale >= MAX_SCALE - 0.001;
    try {
      localStorage.setItem("gir_read_scale", String(readScale));
    } catch (_) {}
  }
  applyScale(readScale);

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
    const anchorTop = window.scrollY + targetEl.getBoundingClientRect().top - getStickyOffset();
    window.scrollTo({ top: Math.max(0, anchorTop), behavior: prefersReducedMotion ? "auto" : "smooth" });
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
      const offset = getStickyOffset() + 16;
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
  let cmdKlineItems = [];
  let cmdKlineLoaded = false;
  let cmdKlineLoading = false;
  let cmdFiltered = [];
  let cmdIndex = 0;
  let lastKeyNavTs = 0;

  if (cmdList && !cmdList.getAttribute("role")) {
    cmdList.setAttribute("role", "listbox");
  }

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
    cmdItems = Array.from(document.querySelectorAll(".main-nav .nav-pill, .main-nav .nav-dropdown a")).map(function (a) {
      return {
        title: (a.textContent || "").trim(),
        meta: "导航",
        href: a.getAttribute("href") || "#",
        keywords: a.getAttribute("data-nav") || "",
      };
    });
  }

  function ensureCmdKlineItems() {
    if (cmdKlineLoaded || cmdKlineLoading) return;
    cmdKlineLoading = true;
    const basePrefix = document.body.getAttribute("data-base-prefix") || "";
    const loader =
      window.GIRKline && typeof window.GIRKline.loadManifest === "function"
        ? window.GIRKline.loadManifest(basePrefix)
        : fetch(basePrefix + "assets/klines/manifest.json", { cache: "default" })
            .then(function (resp) { return resp.ok ? resp.json() : null; })
            .catch(function () { return null; });
    Promise.resolve(loader).then(function (manifest) {
      cmdKlineLoading = false;
      cmdKlineLoaded = true;
      if (!manifest || !Array.isArray(manifest.catalog)) return;
      cmdKlineItems = manifest.catalog
        .filter(function (c) { return c && c.id && c.name; })
        .map(function (c) {
          const idStr = String(c.id);
          const codeStr = String(c.code || "");
          const nameStr = String(c.name || "");
          const isEtf = idStr.startsWith("etf_");
          const isStk = idStr.startsWith("stk_");
          const kindLbl = isEtf ? "ETF K线" : isStk ? "个股 K线" : "指数/宏观 K线";
          const chgStr = isFiniteNum(c.change_pct)
            ? (c.change_pct >= 0 ? "+" : "") + c.change_pct.toFixed(2) + "%"
            : "";
          return {
            title: "📈 " + nameStr + (codeStr ? " (" + codeStr + ")" : ""),
            meta: [kindLbl, c.market || "", chgStr].filter(Boolean).join(" · "),
            href: basePrefix + "charts.html#sym=" + encodeURIComponent(idStr),
            keywords: [idStr, codeStr, nameStr, c.market || "", c.group || "", c.dossier_key || ""].join(" "),
            _idStr: idStr,
            _code: codeStr,
            _name: nameStr,
            _codeLow: codeStr.toLowerCase(),
            _nameLow: nameStr.toLowerCase(),
            _hayLow: [idStr, codeStr, nameStr, c.market || "", c.group || "", c.dossier_key || ""].join(" ").toLowerCase(),
            _priority: isFiniteNum(c.priority) ? c.priority : 9999,
            _isEtf: isEtf,
            _isStk: isStk,
          };
        });
      if (cmdPalette && cmdPalette.classList.contains("open") && cmdInput && cmdInput.value.trim()) {
        renderCmdList(cmdInput.value);
      }
    });
  }

  function matchCmdSymbols(rawQ, tokens, basePrefix) {
    if (tokens.length === 0 || cmdKlineItems.length === 0) return [];
    const rawLow = rawQ.toLowerCase();
    const scored = [];
    for (let i = 0; i < cmdKlineItems.length; i++) {
      const it = cmdKlineItems[i];
      if (!tokens.every(function (tk) { return it._hayLow.indexOf(tk) !== -1; })) continue;
      let rank = 3;
      if (it._codeLow === rawLow || it._nameLow === rawLow) rank = 0;
      else if (it._codeLow.startsWith(rawLow) || it._nameLow.startsWith(rawLow)) rank = 1;
      else if (it._nameLow.indexOf(rawLow) !== -1) rank = 2;
      scored.push({ item: it, rank: rank });
    }
    scored.sort(function (a, b) {
      if (a.rank !== b.rank) return a.rank - b.rank;
      if (a.item._priority !== b.item._priority) return a.item._priority - b.item._priority;
      return a.item._name.length - b.item._name.length;
    });
    const out = [];
    const top = scored.slice(0, 6);
    for (let i = 0; i < top.length && out.length < 6; i++) {
      const it = top[i].item;
      out.push({
        title: it.title,
        meta: it.meta,
        href: it.href,
        keywords: it.keywords,
      });
      if (i === 0 && top.length <= 4 && out.length < 6 && (it._isStk || it._isEtf)) {
        const qTerm = it._code || it._name;
        out.push({
          title: it._isEtf
            ? "📋 " + it._name + " (" + it._code + ") · ETF 7 维拆解"
            : "📋 " + it._name + " (" + it._code + ") · 7 维档案",
          meta: it._isEtf ? "直达 ETF 雷达" : "直达 231 股池",
          href: basePrefix + (it._isEtf ? "etfs.html#q=" : "screener.html#q=") + encodeURIComponent(qTerm),
          keywords: "",
        });
      }
    }
    return out;
  }

  function renderCmdList(query) {
    if (!cmdList) return;
    const rawQ = String(query || "").trim();
    const tokens = rawQ.toLowerCase().split(/\s+/).filter(Boolean);
    const staticMatches = cmdItems.filter(function (it) {
      if (tokens.length === 0) return true;
      const hay = (it.title + " " + it.meta + " " + it.keywords + " " + it.href).toLowerCase();
      return tokens.every(function (tk) { return hay.indexOf(tk) !== -1; });
    });
    const basePrefix = document.body.getAttribute("data-base-prefix") || "";
    const symbolMatches = matchCmdSymbols(rawQ, tokens, basePrefix);
    const jumpActions = rawQ.length >= 2
      ? [
          {
            title: "在 K 线图表终端查看「" + rawQ + "」→",
            meta: "直达全市场 K 线",
            href: basePrefix + "charts.html#q=" + encodeURIComponent(rawQ),
            keywords: "",
          },
          {
            title: "在 231 股池搜索「" + rawQ + "」→",
            meta: "直达筛选器",
            href: basePrefix + "screener.html#q=" + encodeURIComponent(rawQ),
            keywords: "",
          },
          {
            title: "在 ETF 雷达搜索「" + rawQ + "」→",
            meta: "直达 ETF 雷达",
            href: basePrefix + "etfs.html#q=" + encodeURIComponent(rawQ),
            keywords: "",
          },
          {
            title: "在新手词典搜索「" + rawQ + "」→",
            meta: "直达指南词条",
            href: basePrefix + "guide.html#q=" + encodeURIComponent(rawQ),
            keywords: "",
          },
        ]
      : [];
    cmdFiltered = staticMatches.concat(symbolMatches, jumpActions);
    cmdIndex = 0;

    if (cmdFiltered.length === 0) {
      cmdList.innerHTML = '<div class="cmd-empty">未找到匹配的页面或报告，试试输入「黄金」「A股」「新手」「筛选」</div>';
      return;
    }

    cmdList.innerHTML = cmdFiltered
      .map(function (it, idx) {
        return (
          '<a class="cmd-item' + (idx === 0 ? " active" : "") + '" role="option" aria-selected="' + (idx === 0 ? "true" : "false") + '" data-cmd-idx="' + idx + '" href="' + escHtml(it.href) + '">' +
          '<span class="cmd-item-title">' + escHtml(it.title) + "</span>" +
          (it.meta ? '<span class="cmd-item-meta">' + escHtml(it.meta) + "</span>" : "") +
          "</a>"
        );
      })
      .join("");
  }

  function syncCmdActive(fromMouse) {
    if (!cmdList) return;
    const els = cmdList.querySelectorAll(".cmd-item");
    els.forEach(function (el, idx) {
      const isAct = idx === cmdIndex;
      el.classList.toggle("active", isAct);
      el.setAttribute("aria-selected", isAct ? "true" : "false");
      if (isAct && !fromMouse && el.scrollIntoView) {
        el.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function openCmdPalette() {
    if (!cmdPalette) return;
    ensureCmdKlineItems();
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
          lastKeyNavTs = Date.now();
          cmdIndex = (cmdIndex + 1) % cmdFiltered.length;
          syncCmdActive(false);
        }
      } else if (e.key === "ArrowUp") {
        if (cmdFiltered.length > 0) {
          e.preventDefault();
          lastKeyNavTs = Date.now();
          cmdIndex = (cmdIndex - 1 + cmdFiltered.length) % cmdFiltered.length;
          syncCmdActive(false);
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
      if (Date.now() - lastKeyNavTs < 350) return;
      const item = e.target.closest(".cmd-item");
      if (!item) return;
      const idx = parseInt(item.getAttribute("data-cmd-idx") || "-1", 10);
      if (!isNaN(idx) && idx >= 0 && idx !== cmdIndex) {
        cmdIndex = idx;
        syncCmdActive(true);
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
    clone.removeAttribute("width");
    clone.removeAttribute("height");
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
      avoid: "避坑提醒：别只看表面便宜就换港股，用内地港股通买标准 H 股分红扣 20% 红利税（仅特定内地居民企业红筹股依发行人公告最高扣至约 28%），务必算税后净股息。",
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
      plain: "A 股持股超 1 年免红利税；港股通收标准 H 股息直扣 20%（仅特定内地居民企业红筹依公告最高约 28%）；个人直买交易所公司债付息扣 20%，交易所公司债/科创债 ETF（551500/159600）底层债券付息环节仍扣 20% 税（区别于银行间短融 ETF 511360 等银行间标的）。",
      avoid: "避坑提醒：买港股高股息前先按税后折算真实到手率，买交易所信用债 ETF 勿误当作免税债基；境外账户投资收益须依法履行年度全球纳税申报义务。",
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
    w8ben: {
      term: "非美居民税务表（W-8BEN）",
      plain: "中国大陆等非美国税务居民在合规离岸券商开户时签署的税务身份声明表，用于享受中美税收协定优惠，把美股股息预扣税从 30% 降至 10%。",
      avoid: "避坑提醒：W-8BEN 通常每 3 年过期，忘记及时续签会被自动按 30% 扣美股股息税；且美股直投仍须留意 6 万美元非美居民美国遗产税免税额上限。",
    },
    crs: {
      term: "金融账户涉税信息自动交换（CRS）",
      plain: "全球百余个税务管辖区（含中国大陆、香港、新加坡、英国等）之间自动交换非居民金融账户余额、股息与处置收益信息的国际透明机制。",
      avoid: "避坑提醒：离岸账户早已进入全球税务透明时代，中国税务居民个人境外投资收益须按 20% 依法自行年度汇算申报，切勿听信「离岸免查」误导。",
    },
    low_water: {
      term: "港股期指低水（贴水）",
      plain: "香港市场把期货价格低于现货指数叫做「低水」（A 股称贴水）。除息旺季分红扣点或避险对冲盘偏重时，恒指期货往往呈现明显低水。",
      avoid: "避坑提醒：看到期指大幅低水先区分是成分股集中除息扣点，还是机构集中做空避险，切忌仅凭盘前低水情绪化杀跌或盲目抄底。",
    },
    high_water: {
      term: "港股期指高水（升水）",
      plain: "香港市场把期货价格高于现货指数叫做「高水」（A 股称升水），通常反映市场做多情绪偏热、资金愿意加价提前锁筹或预期后续上行。",
      avoid: "避坑提醒：盘中情绪躁动拉出大幅高水后极易出现冲高回落，切忌在期指极端高水时追高进场。",
    },
    ex_div: {
      term: "除净（除权除息）",
      plain: "港股把上市公司分红或送股后、股价按派息金额等额下调的交易日称为「除净日」。除净当天买入不再享有本次分红，参考价会直接扣除每股派息额。",
      avoid: "避坑提醒：高额特别息或年度分红除净当日，软件显示的参考价低开并非暴跌打折，切勿把除净扣价误当抄底良机；内地港股通持仓收标准 H 股息须扣 20% 红利税（特定内地居民企业红筹依公告最高约 28%）。",
    },
    discount_ex_div: {
      term: "贴权（除净后走弱）",
      plain: "股票除权除息后，股价不仅没有涨回除息前的价格（填权），反而继续下跌，导致「赚了股息却亏了本金价差」的现象。",
      avoid: "避坑提醒：切忌在除净前一天冲着高股息去短线抢权分红，不仅容易遭遇除净后贴权亏损，还要白白缴纳红利税（A 股持股不满 1 个月补扣 20%）。",
    },
    margin_hk: {
      term: "孖展（港股保证金融资）",
      plain: "香港券商对「保证金融资借钱买股或打新」（英文 Margin 粤语音译）的统称，相当于把已有股票抵押给券商借钱加杠杆。",
      avoid: "避坑提醒：高波动市况下用孖展加杠杆，一旦股价跌破维持保证金比例会被券商强制平仓（斩仓）且利息高昂，普通投资者严禁借钱或开孖展买股打新。",
    },
    official_settle: {
      term: "官结（期货官方结算价）",
      plain: "交易所每日收市后按加权成交或收盘区间正式公布的官方结算基准价（有别于最后 1 秒撮合收盘价），用于期货盯市保证金清算与次日涨跌停基准。",
      avoid: "避坑提醒：核对原油、黄金、国债与股指期货涨跌幅时，务必分清「官方结算价」与「实时最新成交价」，避免误把跨口径差额当成大涨大跌。",
    },
    basis_spread: {
      term: "平水 / 升水 / 贴水",
      plain: "衡量期货价与现货价差别的标尺：期货高于现货叫「升水」，低于现货叫「贴水」，两者几乎相等叫「平水」。",
      avoid: "避坑提醒：商品期货长期大幅升水（如原油常见结构）在每次换月时都会持续磨损净值，切勿把带高升水磨损的品种当成长线躺赢标的。",
    },
    bps: {
      term: "基点（bp / bps）",
      plain: "金融市场计量利率与利差微小变动的最小常用单位：1 个基点 = 0.01%，100 个基点 = 1 个百分点（1%）。",
      avoid: "避坑提醒：别小看「几十个基点」——对 30 年超长国债而言，收益率上行 25 个基点就足以带来约 4%–5% 的债券价格回撤。",
    },
    limit_order: {
      term: "限价单（防滑点挂单）",
      plain: "下单时自己写死最高买入价或最低卖出价，只有市场成交价满足你设定的价格才成交，绝不按盘口高价盲扫。",
      avoid: "避坑提醒：买公募 REITs、冷门债券 ETF 或港股薄量中小盘时严禁市价一键扫单，否则瞬间吃掉 1%–3% 买卖价差滑点。",
    },
    discount_placement: {
      term: "折价配售（港股闪电配股）",
      plain: "港股上市公司向机构投资者以低于前一日市价（常见折价 5%–10%）发行新股快速募资，类似「打折批发增发」，短线常带来抛压与摊薄效应。",
      avoid: "避坑提醒：盘前突现大额折价配售公告时，切勿急着按前日高价追买或盲目接飞刀，应先等股价在配售价附近充分消化抛压并企稳后再评估。",
    },
    cbbc_zone: {
      term: "牛熊证重货区",
      plain: "香港衍生品市场中大量散户牛证或熊证集中扎堆的强制收回价格区间。大盘逼近该区间时，做市商对冲盘容易引发短线急杀或急拉（俗称「屠牛/屠熊」）。",
      avoid: "避坑提醒：普通投资者严禁直接买带强制收回机制的港股牛熊证；看盘时仅把它当短线波动预警信号，不在急杀扫损瞬间情绪化操作。",
    },
    hkd_weak_peg: {
      term: "联汇弱方保证（7.85 港元）",
      plain: "香港联系汇率制规定美元兑港元汇率波动区间为 7.75–7.85；一旦触及 7.85 弱方兑换保证线，金管局须被动买入港元回收流动性，令总结余下降、拆息跳涨。",
      avoid: "避坑提醒：美元兑港元贴近 7.85 且金管局总结余逼近低水位时，港股高估值成长股往往承压加大，切忌逆势加杠杆。",
    },
    closing_auction: {
      term: "收市竞价（港股 U 盘）",
      plain: "港股 16:00–16:10 的收市竞价时段（俗称 U 盘），专门承接指数基金调仓、北水尾盘成交与机构大宗定价，最后在 16:08–16:10 随机收市。",
      avoid: "避坑提醒：指数季检调仓日（如 MSCI/恒指生效日）尾盘竞价常现放量异动与瞬间跳价，普通散户无须在 U 盘跟风挂市价单凑热闹。",
    },
    margin_ratio: {
      term: "两融与降保（融资保证金比例）",
      plain: "「两融」指券商向投资者借钱买股（融资）或借股卖出（融券）；监管下调融资保证金比例（「降保」）可放大杠杆上限，但高企的两融余额也意味着市场筹码更脆弱。",
      avoid: "避坑提醒：两融余额高位且行情急跌时极易触发连锁平仓踩踏；普通投资者坚决坚持全额自有资金投资，严禁开通融资加杠杆。",
    },
    pboc_omo: {
      term: "央行逆回购（OMO 流动性操作）",
      plain: "中国人民银行每天上午 09:20 通过公开市场操作（OMO）向银行体系投放短期流动性的工具（与个人在券商借钱的国债逆回购方向相反），净投放代表补水、净回笼代表抽水。",
      avoid: "避坑提醒：月末、季末与税期紧盯央行净投放节奏，若资金面阶段性收敛，短端逆回购收益走高但股市短线波动也会放大。",
    },
    ann_basis: {
      term: "年化贴水与期指基差",
      plain: "把股指期货（如中证 500/1000 期货 IC/IM）低于现货指数的贴水幅度折算成年化百分比。贴水越深，说明机构对冲抛压或悲观预期越浓。",
      avoid: "避坑提醒：贴水扩大时用「贴水负号」读懂真实方向（负基差 = 贴水），切忌把深度贴水误读成升水看多信号。",
    },
    top20_short: {
      term: "前 20 席位净空（期指机构持仓）",
      plain: "中金所每日收盘后公布的前 20 家期货公司会员多单与空单净差额，常用来追踪量化对冲与大型机构在股指期货上的套保力度变化。",
      avoid: "避坑提醒：前 20 席位长期净空很大程度来自量化中性基金的现货套保，不能孤立当作单边看空信号，应重点看单日增减幅度与基差联动。",
    },
    ins_research_rate: {
      term: "保险预定利率研究值",
      plain: "中国保险行业协会按季度结合 5 年期以上 LPR、国债收益率与定存利率发布的行业基准参考值，用于动态约束新发传统险、分红险与万能险的预定利率上限。",
      avoid: "避坑提醒：切勿被营销员「最后一天炒停售」话术逼单；买储蓄险先核对合同保证现价 IRR，确认是 10 年以上绝对不用的闲钱再决策。",
    },
    cornerstone_mech_b: {
      term: "港股基石投资者与回拨机制 B",
      plain: "港股新股发行中，提前锁定 6 个月禁售期的大机构叫「基石投资者」；「机制 B」是 2025 年港交所新规下取消强制大幅回拨散户的分配模式，使机构筹码更集中、首日流通盘偏薄。",
      avoid: "避坑提醒：机制 B 新股首日易被资金炒高、6 个月基石解禁期抛压集中，普通人打新切忌借孖展重押，上市后也不宜高估值盲目追炒。",
    },
    creditwatch: {
      term: "信用观察（CreditWatch / 负面观察）",
      plain: "标普、穆迪、惠誉等权威评级机构把某公司或主权主体列入短期重点复核名单（通常 90 天内定夺），「负面信用观察」代表降级风险显著升温。",
      avoid: "避坑提醒：重仓高负债公司或可转债前务必核查近 24 小时评级观察公告，一旦被纳入负面观察，债务再融资成本跃升常先于股价暴雷。",
    },
    redemption_gate: {
      term: "赎回闸门（私募 / 半开放基金限赎）",
      plain: "部分私募、海外私募信贷或半开放基金在单季/单月净赎回超过约定比例（如 5%）时启动的暂停或按比例限制赎回条款。",
      avoid: "避坑提醒：高息宣传的私募信贷或非标类产品在市场恐慌时最易触发赎回闸门导致「看得见净值却取不出钱」，切勿拿短期周转钱去碰限赎产品。",
    },
    equal_weight: {
      term: "等权指数（如标普 500 等权 RSP）",
      plain: "给指数里每家成分股分配完全相同权重（例如 500 家各占 0.2%），而不按市值大小倾斜，用来分散少数超大科技巨头集中度过高的风险。",
      avoid: "避坑提醒：当市场宽度极端收窄、前十大科技股占市值比重过高时，可用等权指数对照观察真实市场健康度，但也要留意其换手率与费率略高于市值加权宽基。",
    },
  };

  let activeTermPop = null;
  let activeTermTrigger = null;
  let activeTermOpenY = 0;
  let activeTermOpenAt = 0;

  function closeTermPopover(restoreFocus) {
    const prevTrigger = activeTermTrigger;
    if (activeTermPop && activeTermPop.parentNode) {
      activeTermPop.parentNode.removeChild(activeTermPop);
    }
    if (prevTrigger) {
      prevTrigger.setAttribute("aria-expanded", "false");
    }
    activeTermPop = null;
    activeTermTrigger = null;
    if (restoreFocus && prevTrigger && prevTrigger.isConnected && typeof prevTrigger.focus === "function") {
      prevTrigger.focus();
    }
  }

  function positionTermPopover(pop, trigger) {
    const rect = trigger.getBoundingClientRect();
    const popW = pop.offsetWidth || 320;
    const popH = pop.offsetHeight || 180;
    const margin = 12;
    const hdr = document.querySelector(".site-header");
    const headerH = (hdr && hdr.offsetHeight) || 60;
    const topSafe = headerH + 8;
    const bottomSafe = window.innerWidth <= 768 ? 68 : 12;
    let left = rect.left + rect.width / 2 - popW / 2;
    left = Math.max(margin, Math.min(window.innerWidth - popW - margin, left));
    let top = rect.bottom + 8;
    if (top + popH > window.innerHeight - bottomSafe && rect.top - popH - 8 >= topSafe) {
      top = rect.top - popH - 8;
    } else {
      top = Math.max(topSafe, Math.min(window.innerHeight - popH - bottomSafe, top));
    }
    pop.style.left = Math.round(left) + "px";
    pop.style.top = Math.round(top) + "px";
  }

  function openTermPopover(trigger) {
    const key = trigger.getAttribute("data-term") || "";
    const entry = GLOSSARY_DICT[key];
    if (!entry) return;
    if (activeTermTrigger === trigger && activeTermPop) {
      closeTermPopover(true);
      return;
    }
    closeTermPopover(false);

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
    positionTermPopover(pop, trigger);

    const closeBtn = pop.querySelector(".term-pop-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        closeTermPopover(true);
      });
    }
    trigger.setAttribute("aria-expanded", "true");
    activeTermPop = pop;
    activeTermTrigger = trigger;
    activeTermOpenY = window.scrollY || window.pageYOffset || 0;
    activeTermOpenAt = Date.now();
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
      closeTermPopover(false);
    }
  });
  window.addEventListener("resize", function () { closeTermPopover(false); }, { passive: true });
  document.addEventListener(
    "scroll",
    function (e) {
      if (!activeTermPop) return;
      if (Date.now() - activeTermOpenAt < 250) return;
      if (e.target === document || e.target === document.documentElement || e.target === document.body) {
        const curY = window.scrollY || window.pageYOffset || 0;
        if (Math.abs(curY - activeTermOpenY) > 40) {
          closeTermPopover(false);
        }
      } else if (!activeTermPop.contains(e.target)) {
        closeTermPopover(false);
      }
    },
    { capture: true, passive: true }
  );

  /* Global Keyboard Dispatcher (Cmd/Ctrl+K, Chart Shortcuts, Modal Escape/Tab/Arrows) */
  function closeAllModalsAndDrawers() {
    closeAllNavDropdowns(null);
    closeTermPopover();
    closeCmdPalette();
    closeChartModal();
    setTocDrawer(false);
    if (typeof closeWatchDrawer === "function") closeWatchDrawer();
    const dModal = document.getElementById("dossier-modal");
    if (dModal) {
      if (typeof dModal._girClose === "function") dModal._girClose();
      else hideDialog(dModal);
    }
    const eModal = document.getElementById("etf-modal");
    if (eModal) {
      if (typeof eModal._girClose === "function") eModal._girClose();
      else hideDialog(eModal);
    }
  }

  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && cmdPalette) {
      e.preventDefault();
      if (cmdPalette.classList.contains("open")) {
        closeCmdPalette();
      } else {
        closeAllModalsAndDrawers();
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

    if (e.key === "Escape" && activeTermPop) {
      e.preventDefault();
      closeTermPopover(true);
      return;
    }

    const dialog = document.querySelector('[aria-modal="true"].open');
    if (dialog) {
      if (e.key === "Escape") {
        e.preventDefault();
        closeAllModalsAndDrawers();
      } else if (
        (e.key === "ArrowUp" || e.key === "ArrowDown") &&
        !e.metaKey && !e.ctrlKey && !e.altKey &&
        !isEditableElement(document.activeElement) &&
        typeof dialog._girStep === "function"
      ) {
        e.preventDefault();
        dialog._girStep(e.key === "ArrowDown" ? 1 : -1);
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

    const watchDrawerEl = document.getElementById("watch-drawer");
    if (e.key === "Escape" && watchDrawerEl && (!watchDrawerEl.hidden || watchDrawerEl.classList.contains("open"))) {
      e.preventDefault();
      if (typeof closeWatchDrawer === "function") closeWatchDrawer();
      return;
    }

    if (e.key === "Escape") {
      const openNavGrp = navGroups.find(function (g) {
        const m = g.querySelector(".nav-dropdown");
        return (m && !m.hidden) || g.classList.contains("open");
      });
      if (openNavGrp) {
        e.preventDefault();
        const focusedInside = openNavGrp.contains(document.activeElement);
        closeAllNavDropdowns(null);
        if (focusedInside) {
          const dropBtn = openNavGrp.querySelector(".nav-drop-btn");
          if (dropBtn) dropBtn.focus();
        }
        return;
      }
    }

    if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey && !isEditableElement(document.activeElement)) {
      const searchBox =
        document.getElementById("kline-search") ||
        document.getElementById("scr-search") ||
        document.getElementById("etf-search") ||
        document.getElementById("arc-search") ||
        document.getElementById("sc-search") ||
        document.getElementById("guide-term-search");
      if (searchBox) {
        e.preventDefault();
        if (searchBox.id === "guide-term-search") {
          const panel = searchBox.closest(".filter-panel") || searchBox;
          const rect = panel.getBoundingClientRect();
          const stickyOff = getStickyOffset();
          if (rect.top < stickyOff || rect.bottom > window.innerHeight - 140) {
            const top = window.scrollY + rect.top - stickyOff;
            window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
          }
        }
        searchBox.focus({ preventScroll: searchBox.id === "guide-term-search" });
        searchBox.select();
      }
    }
  });

  /* ------------------------------------------------------------------------
     9B. Universal Watchlist Store (`localStorage.gir_watchlist`)
     ------------------------------------------------------------------------ */
  const WATCH_STORAGE_KEY = "gir_watchlist";

  function readWatchlistRaw() {
    try {
      const raw = localStorage.getItem(WATCH_STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.filter(function (x) { return x && typeof x === "object" && (x.id || x.code || x.klineId); });
      }
    } catch (_) {}
    return [];
  }

  function writeWatchlistRaw(list) {
    try {
      localStorage.setItem(WATCH_STORAGE_KEY, JSON.stringify(list));
    } catch (_) {}
    window.dispatchEvent(new CustomEvent("gir:watchlist-change", { detail: { items: list } }));
  }

  const WatchlistStore = {
    getAll: function () {
      return readWatchlistRaw();
    },
    has: function (idOrKline) {
      const key = String(idOrKline || "").trim();
      if (!key) return false;
      return readWatchlistRaw().some(function (x) {
        return x.id === key || x.klineId === key || x.code === key;
      });
    },
    toggle: function (entry) {
      if (!entry || (!entry.id && !entry.code && !entry.klineId)) return false;
      const list = readWatchlistRaw();
      const targetId = String(entry.id || entry.klineId || entry.code).trim();
      const targetKline = String(entry.klineId || "").trim();
      const idx = list.findIndex(function (x) {
        return x.id === targetId || (targetKline && x.klineId === targetKline);
      });
      let added = false;
      if (idx >= 0) {
        list.splice(idx, 1);
      } else {
        list.push({
          kind: String(entry.kind || "stock"),
          id: targetId,
          klineId: targetKline || targetId,
          code: String(entry.code || "").trim(),
          name: String(entry.name || entry.code || targetId).trim(),
        });
        added = true;
      }
      writeWatchlistRaw(list);
      return added;
    },
    clear: function () {
      writeWatchlistRaw([]);
    },
    syncButtons: function () {
      const list = readWatchlistRaw();
      const set = new Set();
      list.forEach(function (x) {
        if (x.id) set.add(x.id);
        if (x.klineId) set.add(x.klineId);
        if (x.code) set.add(x.code);
      });
      document.querySelectorAll("[data-watch-toggle]").forEach(function (btn) {
        const id = btn.getAttribute("data-watch-id") || "";
        const kl = btn.getAttribute("data-watch-kline") || "";
        const on = set.has(id) || (kl && set.has(kl));
        btn.classList.toggle("active", on);
        btn.setAttribute("aria-pressed", on ? "true" : "false");
        btn.textContent = on ? "★" : "☆";
      });
      document.querySelectorAll("[data-watch-count]").forEach(function (el) {
        el.textContent = list.length > 0 ? " (" + list.length + ")" : "";
      });
    },
  };

  window.GIRWatchlist = WatchlistStore;

  document.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-watch-toggle]");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    WatchlistStore.toggle({
      kind: btn.getAttribute("data-watch-kind") || "stock",
      id: btn.getAttribute("data-watch-id") || "",
      klineId: btn.getAttribute("data-watch-kline") || "",
      code: btn.getAttribute("data-watch-code") || "",
      name: btn.getAttribute("data-watch-name") || "",
    });
  });

  let watchManifestData = null;
  let watchManifestPromise = null;

  function lookupWatchQuote(w) {
    if (!watchManifestData || !w) return null;
    const candidates = [
      w.klineId,
      w.id,
      w.code,
      w.kind === "etf" && w.code ? "etf_" + w.code : "",
      w.kind === "stock" && w.code ? "stk_" + w.code : "",
    ];
    for (let i = 0; i < candidates.length; i++) {
      const cand = String(candidates[i] || "").trim();
      if (!cand) continue;
      if (window.GIRKline && typeof window.GIRKline.resolveCatalogItem === "function") {
        const hit = window.GIRKline.resolveCatalogItem(watchManifestData, cand);
        if (hit) return hit;
      } else if (watchManifestData._byId && watchManifestData._byId.has(cand)) {
        return watchManifestData._byId.get(cand);
      } else if (watchManifestData._byCode && watchManifestData._byCode.has(cand.toUpperCase())) {
        return watchManifestData._byCode.get(cand.toUpperCase());
      }
    }
    return null;
  }

  function fmtWatchQuotePrice(item) {
    if (!item || !isFiniteNum(item.latest_close)) return "";
    if (window.GIRKline && typeof window.GIRKline.fmtPrice === "function") {
      return window.GIRKline.fmtPrice(item.latest_close, item.unit);
    }
    const abs = Math.abs(item.latest_close);
    const dp = abs < 2 ? 4 : abs < 20 ? 3 : abs > 100000 ? 1 : 2;
    return item.latest_close.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }

  function ensureWatchManifest() {
    if (watchManifestData || watchManifestPromise) return;
    const bp = document.body.getAttribute("data-base-prefix") || "";
    const loader =
      window.GIRKline && typeof window.GIRKline.loadManifest === "function"
        ? window.GIRKline.loadManifest(bp)
        : fetch(bp + "assets/klines/manifest.json", { cache: "default" })
            .then(function (resp) { return resp.ok ? resp.json() : null; })
            .then(function (data) {
              if (!data || !Array.isArray(data.catalog)) return null;
              const byId = new Map();
              const byCode = new Map();
              data.catalog.forEach(function (it) {
                if (it && it.id) byId.set(String(it.id), it);
                if (it && it.code) byCode.set(String(it.code).toUpperCase(), it);
              });
              data._byId = byId;
              data._byCode = byCode;
              return data;
            })
            .catch(function () { return null; });
    watchManifestPromise = Promise.resolve(loader).then(function (manifest) {
      if (!manifest) return;
      watchManifestData = manifest;
      renderHomeWatchlistBar();
      if (watchDrawer && !watchDrawer.hidden) {
        renderWatchDrawerBody();
      }
    });
  }

  function renderHomeWatchlistBar() {
    const bar = document.getElementById("home-watchlist-bar");
    const listWrap = document.getElementById("home-watchlist-items");
    const cntEl = document.getElementById("home-watchlist-cnt");
    if (!bar || !listWrap) return;
    const items = WatchlistStore.getAll();
    if (items.length === 0) {
      bar.hidden = true;
      return;
    }
    ensureWatchManifest();
    let idxMap = {};
    const idxEl = document.getElementById("home-watch-index");
    if (idxEl) {
      try {
        const parsed = JSON.parse(idxEl.textContent || "{}");
        if (parsed && typeof parsed === "object") idxMap = parsed;
      } catch (_) {}
    }
    bar.hidden = false;
    if (cntEl) cntEl.textContent = String(items.length);
    let pillsHtml = items
      .slice(0, 12)
      .map(function (w) {
        const meta = idxMap[w.id] || idxMap[w.code] || null;
        const quote = lookupWatchQuote(w);
        const name = (meta && meta.name) || (quote && quote.name) || w.name || w.code || w.id;
        const code = (meta && meta.code) || (quote && quote.code) || w.code || "";
        const livePrice = fmtWatchQuotePrice(quote);
        const price = livePrice || (meta && meta.price) || "";
        const chgHtml =
          quote && isFiniteNum(quote.change_pct)
            ? ' <span class="watch-pill-chg ' + (quote.change_pct >= 0 ? "chg-up" : "chg-dn") + '">' +
              (quote.change_pct >= 0 ? "+" : "") + quote.change_pct.toFixed(2) + "%</span>"
            : "";
        const role = (meta && meta.role) || "";
        const kHref = "charts.html#sym=" + encodeURIComponent(w.klineId || w.id);
        const detailHref = w.kind === "etf"
          ? "etfs.html#q=" + encodeURIComponent(code || name)
          : w.kind === "stock"
          ? "screener.html#q=" + encodeURIComponent(code || name)
          : kHref;
        return (
          '<div class="watch-pill">' +
          '<a class="watch-pill-main" href="' + escHtml(detailHref) + '">' +
          "<strong>" + escHtml(name) + "</strong>" +
          (code ? ' <span class="code-tag">' + escHtml(code) + "</span>" : "") +
          (price ? ' <span class="watch-pill-meta">' + escHtml(price) + "</span>" : "") +
          chgHtml +
          (role ? ' <span class="watch-pill-role">' + escHtml(role) + "</span>" : "") +
          "</a>" +
          '<a class="kline-quick-btn" href="' + escHtml(kHref) + '" title="查看交互 K 线">📈</a>' +
          '<button type="button" class="star-btn active" data-watch-toggle="1" data-watch-kind="' + escHtml(w.kind) +
          '" data-watch-id="' + escHtml(w.id) + '" data-watch-kline="' + escHtml(w.klineId) +
          '" data-watch-code="' + escHtml(code) + '" data-watch-name="' + escHtml(name) + '" aria-label="移出自选">★</button>' +
          "</div>"
        );
      })
      .join("");
    if (items.length > 12) {
      pillsHtml +=
        '<button type="button" class="watch-pill watch-pill-more" data-action="open-watch-drawer">+' +
        (items.length - 12) +
        " 查看全部</button>";
    }
    listWrap.innerHTML = pillsHtml;
  }

  function syncHeaderWatchCount() {
    const cnt = WatchlistStore.getAll().length;
    const badge = document.getElementById("hdr-watch-cnt");
    if (badge) {
      badge.textContent = String(cnt);
    }
    const openBtn = document.getElementById("watch-drawer-open");
    if (openBtn) {
      openBtn.classList.toggle("has-items", cnt > 0);
      openBtn.setAttribute("aria-label", cnt > 0 ? "打开我的自选（" + cnt + " 项）" : "打开我的自选");
    }
  }

  /* Global Right Slide-Over Watchlist Drawer (#watch-drawer) */
  const watchDrawer = document.getElementById("watch-drawer");
  const watchDrawerOpenBtn = document.getElementById("watch-drawer-open");
  const watchDrawerBody = document.getElementById("watch-drawer-body");

  function renderWatchDrawerBody() {
    if (!watchDrawerBody) return;
    const items = WatchlistStore.getAll();
    const basePrefix = document.body.getAttribute("data-base-prefix") || "";
    if (items.length === 0) {
      watchDrawerBody.innerHTML =
        '<div class="empty-state watch-drawer-empty" style="padding:28px 16px;">' +
        '<div class="empty-title">☆ 自选清单暂无标的</div>' +
        '<div class="empty-sub">在 231 股池、ETF 雷达或全屏 K 线终端点击任意标的旁的 <strong>☆</strong> 即可加入自选，跨页面自动同步（仅保存在本机浏览器）。</div>' +
        '<div style="display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:12px;">' +
        '<a class="btn btn-sm" href="' + escHtml(basePrefix + "screener.html") + '">浏览 231 股池 →</a>' +
        '<a class="btn btn-sm" href="' + escHtml(basePrefix + "etfs.html") + '">浏览 ETF 雷达 →</a>' +
        '<a class="btn btn-sm" href="' + escHtml(basePrefix + "charts.html") + '">K 线终端 →</a>' +
        "</div>" +
        "</div>";
      return;
    }
    ensureWatchManifest();

    const rowsHtml = items
      .map(function (w) {
        const quote = lookupWatchQuote(w);
        const name = (quote && quote.name) || w.name || w.code || w.id;
        const code = (quote && quote.code) || w.code || "";
        const livePrice = fmtWatchQuotePrice(quote);
        const chgHtml =
          quote && isFiniteNum(quote.change_pct)
            ? '<span class="watch-drawer-chg ' + (quote.change_pct >= 0 ? "chg-up" : "chg-dn") + '" style="font-weight:700;">' +
              (quote.change_pct >= 0 ? "+" : "") + quote.change_pct.toFixed(2) + "%</span>"
            : "";
        const quoteLineHtml = livePrice || chgHtml
          ? '<span class="watch-drawer-quote" style="display:inline-flex;align-items:center;gap:5px;font-size:12.5px;font-variant-numeric:tabular-nums;">' +
            (livePrice ? '<strong>' + escHtml(livePrice) + "</strong>" : "") +
            chgHtml +
            "</span>"
          : "";
        const kHref = basePrefix + "charts.html#sym=" + encodeURIComponent(w.klineId || w.id);
        const isEtf = w.kind === "etf";
        const isStock = w.kind === "stock";
        const detailHref = isEtf
          ? basePrefix + "etfs.html#q=" + encodeURIComponent(code || name)
          : isStock
          ? basePrefix + "screener.html#q=" + encodeURIComponent(code || name)
          : "";
        const detailLbl = isEtf ? "ETF 详情" : isStock ? "7 维档案" : "";
        const kindLbl = isEtf ? "ETF" : isStock ? "个股" : "基准";
        return (
          '<div class="watch-drawer-item" style="display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;border:1px solid var(--border);border-radius:10px;background:var(--surface-warm);">' +
          '<div style="min-width:0;display:flex;flex-direction:column;gap:5px;">' +
          '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;font-size:13.5px;color:var(--ink);">' +
          '<span class="etf-chan-tag">' + escHtml(kindLbl) + "</span>" +
          "<strong>" + escHtml(name) + "</strong>" +
          (code ? '<span class="code-tag">' + escHtml(code) + "</span>" : "") +
          quoteLineHtml +
          "</div>" +
          '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:8px;font-size:12px;">' +
          '<a class="kline-quick-btn" href="' + escHtml(kHref) + '">📈 K线</a>' +
          (detailHref
            ? '<a href="' + escHtml(detailHref) + '" style="font-weight:700;">' + escHtml(detailLbl) + " →</a>"
            : "") +
          "</div>" +
          "</div>" +
          '<button type="button" class="ctrl-btn watch-drawer-remove" data-watch-remove="1" ' +
          'data-watch-kind="' + escHtml(w.kind) + '" data-watch-id="' + escHtml(w.id) + '" ' +
          'data-watch-kline="' + escHtml(w.klineId) + '" data-watch-code="' + escHtml(code) + '" ' +
          'data-watch-name="' + escHtml(name) + '" aria-label="从自选移除 ' + escHtml(name) + '">移除</button>' +
          "</div>"
        );
      })
      .join("");

    watchDrawerBody.innerHTML =
      '<div class="watch-drawer-meta" style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;font-size:12.5px;color:var(--ink-3);padding-bottom:6px;border-bottom:1px solid var(--border);">' +
      '<span>已收藏 <strong style="color:var(--ink);">' + items.length + "</strong> 项标的</span>" +
      '<a href="' + escHtml(basePrefix + "charts.html#group=watchlist") + '" style="font-weight:700;">在 K 线终端全屏查看 →</a>' +
      "</div>" +
      '<div class="watch-drawer-list" style="display:flex;flex-direction:column;gap:8px;">' + rowsHtml + "</div>" +
      '<div class="watch-drawer-foot" style="display:flex;justify-content:flex-end;padding-top:8px;border-top:1px solid var(--border);">' +
      '<button type="button" class="btn btn-sm" data-watch-clear-all="1">清空全部自选</button>' +
      "</div>";
  }

  function openWatchDrawer() {
    if (!watchDrawer) return;
    closeAllNavDropdowns(null);
    closeTermPopover(false);
    renderWatchDrawerBody();
    watchDrawer.hidden = false;
    void watchDrawer.offsetWidth;
    showDialog(watchDrawer, watchDrawer.querySelector("[data-action='close-watch-drawer']"));
    if (watchDrawerOpenBtn) watchDrawerOpenBtn.setAttribute("aria-expanded", "true");
  }

  function closeWatchDrawer() {
    if (!watchDrawer) return;
    watchDrawer.hidden = true;
    hideDialog(watchDrawer);
    if (watchDrawerOpenBtn) watchDrawerOpenBtn.setAttribute("aria-expanded", "false");
  }

  if (watchDrawerOpenBtn && watchDrawer) {
    watchDrawerOpenBtn.addEventListener("click", function () {
      if (watchDrawer.hidden) openWatchDrawer();
      else closeWatchDrawer();
    });
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-action='open-watch-drawer']")) {
      e.preventDefault();
      openWatchDrawer();
    }
  });
  if (watchDrawer) {
    document.querySelectorAll("[data-action='close-watch-drawer']").forEach(function (b) {
      b.addEventListener("click", closeWatchDrawer);
    });
    watchDrawer.addEventListener("click", function (e) {
      if (e.target === watchDrawer || e.target.classList.contains("watch-drawer-backdrop")) {
        closeWatchDrawer();
        return;
      }
      if (e.target.closest("a[href]")) {
        closeWatchDrawer();
        return;
      }
      const rmBtn = e.target.closest("[data-watch-remove]");
      if (rmBtn) {
        e.preventDefault();
        WatchlistStore.toggle({
          kind: rmBtn.getAttribute("data-watch-kind") || "stock",
          id: rmBtn.getAttribute("data-watch-id") || "",
          klineId: rmBtn.getAttribute("data-watch-kline") || "",
          code: rmBtn.getAttribute("data-watch-code") || "",
          name: rmBtn.getAttribute("data-watch-name") || "",
        });
        return;
      }
      if (e.target.closest("[data-watch-clear-all]")) {
        e.preventDefault();
        WatchlistStore.clear();
      }
    });
  }

  window.addEventListener("gir:watchlist-change", function () {
    WatchlistStore.syncButtons();
    syncHeaderWatchCount();
    renderHomeWatchlistBar();
    if (watchDrawer && !watchDrawer.hidden) {
      renderWatchDrawerBody();
    }
  });
  window.addEventListener("storage", function (e) {
    if (e.key === WATCH_STORAGE_KEY) {
      window.dispatchEvent(new CustomEvent("gir:watchlist-change", { detail: { items: WatchlistStore.getAll() } }));
    }
  });
  WatchlistStore.syncButtons();
  syncHeaderWatchCount();
  renderHomeWatchlistBar();

  /* ------------------------------------------------------------------------
     9C. Collapsible Advanced Filter Tray ([data-toggle-adv-filter] / .filter-adv-tray)
     ------------------------------------------------------------------------ */
  function setAdvFilterTrayOpen(panel, open) {
    if (!panel) return;
    const tray = panel.querySelector(".filter-adv-tray");
    const btn = panel.querySelector("[data-toggle-adv-filter], .filter-adv-btn");
    if (!tray) return;
    tray.hidden = !open;
    if (btn) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.textContent = open ? "收起精细筛选 ▴" : "展开精细筛选 ▾";
      btn.classList.toggle("active", !!open);
    }
  }

  document.querySelectorAll("[data-toggle-adv-filter], .filter-adv-btn").forEach(function (btn) {
    if (btn.dataset.advBound) return;
    btn.dataset.advBound = "1";
    btn.addEventListener("click", function () {
      const panel = btn.closest(".filter-panel") || btn.parentElement;
      const tray = panel ? panel.querySelector(".filter-adv-tray") : null;
      if (!tray) return;
      setAdvFilterTrayOpen(panel, tray.hidden);
    });
  });

  /* ------------------------------------------------------------------------
     9D. Client-Side Table & Card Paginator (25 rows/page + 显示全部)
     ------------------------------------------------------------------------ */
  function createPaginator(opts) {
    const pageSize = opts.pageSize || 25;
    const barEl = document.getElementById(opts.barId);
    const tbodyEl = opts.tbodyEl;
    const cardsEl = opts.cardsEl;
    const cardSel = opts.cardSelector;
    const scrollTargetEl = opts.scrollTargetEl || null;
    const onPageChange = typeof opts.onPageChange === "function" ? opts.onPageChange : null;
    const st = { page: 1, showAll: false, total: 0 };

    function getBounds(total) {
      if (!barEl || st.showAll || total <= pageSize) {
        return { start: 0, end: total, totalPages: 1 };
      }
      const totalPages = Math.max(1, Math.ceil(total / pageSize));
      if (st.page > totalPages) st.page = totalPages;
      if (st.page < 1) st.page = 1;
      const start = (st.page - 1) * pageSize;
      const end = Math.min(total, start + pageSize);
      return { start: start, end: end, totalPages: totalPages };
    }

    function applyClasses(total) {
      const bounds = getBounds(total);
      if (tbodyEl && total > 0) {
        const trs = tbodyEl.querySelectorAll("tr");
        for (let i = 0; i < trs.length; i++) {
          trs[i].classList.toggle("pg-hidden", i < bounds.start || i >= bounds.end);
        }
      }
      if (cardsEl && total > 0) {
        const cards = cardsEl.querySelectorAll(cardSel);
        for (let i = 0; i < cards.length; i++) {
          cards[i].classList.toggle("pg-hidden", i < bounds.start || i >= bounds.end);
        }
      }
      return bounds;
    }

    function renderBar(total) {
      st.total = total;
      if (!barEl) return;
      if (total <= pageSize) {
        barEl.hidden = true;
        barEl.innerHTML = "";
        return;
      }
      const bounds = getBounds(total);
      barEl.hidden = false;
      const infoTxt = st.showAll
        ? "第 1–" + total + " / 共 " + total + " 项"
        : "第 " + (bounds.start + 1) + "–" + bounds.end + " / 共 " + total + " 项";
      const ctrlHtml = st.showAll
        ? '<button type="button" class="pg-btn pg-all-btn active" data-pg-act="collapse">恢复分页</button>'
        : '<button type="button" class="pg-btn" data-pg-act="prev"' +
          (st.page <= 1 ? " disabled" : "") +
          ">上一页</button>" +
          '<span class="pg-info" style="padding:0 4px;">' + st.page + " / " + bounds.totalPages + "</span>" +
          '<button type="button" class="pg-btn" data-pg-act="next"' +
          (st.page >= bounds.totalPages ? " disabled" : "") +
          ">下一页</button>" +
          '<button type="button" class="pg-btn pg-all-btn" data-pg-act="show-all">显示全部 (' +
          total +
          ")</button>";
      barEl.innerHTML =
        '<span class="pg-info">' + escHtml(infoTxt) + "</span>" +
        '<div class="pg-actions" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">' + ctrlHtml + "</div>";
    }

    function scrollToListTop() {
      const target = scrollTargetEl || (tbodyEl && tbodyEl.closest(".screener-table-wrap, .etf-table-wrap")) || barEl;
      if (!target) return;
      const rect = target.getBoundingClientRect();
      const offset = getStickyOffset();
      if (rect.top < offset) {
        const top = window.scrollY + rect.top - offset;
        window.scrollTo({ top: Math.max(0, top), behavior: prefersReducedMotion ? "auto" : "smooth" });
      }
    }

    function goToIndex(idx) {
      if (!isFiniteNum(idx) || idx < 0 || st.total <= 0) return;
      if (!barEl || st.showAll || st.total <= pageSize) return;
      const totalPages = Math.max(1, Math.ceil(st.total / pageSize));
      const targetPage = Math.max(1, Math.min(totalPages, Math.floor(idx / pageSize) + 1));
      if (targetPage !== st.page) {
        st.page = targetPage;
        const b = applyClasses(st.total);
        renderBar(st.total);
        if (onPageChange) onPageChange(b, st.total, st.showAll);
      }
    }

    if (barEl && !barEl.dataset.pgBound) {
      barEl.dataset.pgBound = "1";
      barEl.addEventListener("click", function (e) {
        const btn = e.target.closest("[data-pg-act]");
        if (!btn || btn.disabled) return;
        const act = btn.getAttribute("data-pg-act");
        const totalPages = Math.max(1, Math.ceil(st.total / pageSize));
        if (act === "prev" && st.page > 1) {
          st.page -= 1;
          const b = applyClasses(st.total);
          renderBar(st.total);
          if (onPageChange) onPageChange(b, st.total, st.showAll);
          scrollToListTop();
        } else if (act === "next" && st.page < totalPages) {
          st.page += 1;
          const b = applyClasses(st.total);
          renderBar(st.total);
          if (onPageChange) onPageChange(b, st.total, st.showAll);
          scrollToListTop();
        } else if (act === "show-all") {
          st.showAll = true;
          const b = applyClasses(st.total);
          renderBar(st.total);
          if (onPageChange) onPageChange(b, st.total, st.showAll);
        } else if (act === "collapse") {
          st.showAll = false;
          st.page = 1;
          const b = applyClasses(st.total);
          renderBar(st.total);
          if (onPageChange) onPageChange(b, st.total, st.showAll);
          scrollToListTop();
        }
      });
    }

    function formatCount(filteredLen, totalAll, unitLabel) {
      if (filteredLen <= 0) {
        return "显示 0 / " + totalAll + " " + unitLabel;
      }
      const b = getBounds(filteredLen);
      if (barEl && !st.showAll && filteredLen > pageSize) {
        if (filteredLen === totalAll) {
          return "显示第 " + (b.start + 1) + "–" + b.end + " / 共 " + totalAll + " " + unitLabel;
        }
        return "显示第 " + (b.start + 1) + "–" + b.end + " / 匹配 " + filteredLen + "（共 " + totalAll + " " + unitLabel + "）";
      }
      return "显示 " + filteredLen + " / " + totalAll + " " + unitLabel;
    }

    return {
      reset: function () {
        st.page = 1;
        st.showAll = false;
      },
      getBounds: getBounds,
      goToIndex: goToIndex,
      formatCount: formatCount,
      apply: function (total) {
        applyClasses(total);
        renderBar(total);
      },
      renderBar: renderBar,
    };
  }

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
    let currentFilteredStocks = allStocks.slice();
    const scrPager = createPaginator({
      barId: "scr-pg-bar",
      tbodyEl: tbody,
      cardsEl: cardsEl,
      cardSelector: ".scr-mcard, .stock-card",
      scrollTargetEl: document.querySelector("#scr-view-pool .screener-bar") || countEl,
      onPageChange: function () {
        if (countEl) {
          countEl.textContent = scrPager.formatCount(currentFilteredStocks.length, allStocks.length, "家龙头公司");
        }
      },
    });

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
      watchlist: "★ 我的自选",
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
      if (preset === "watchlist") {
        const dk = st.market + ":" + st.code;
        return WatchlistStore.has(dk) || WatchlistStore.has("stk_" + st.code) || WatchlistStore.has(st.code);
      }
      return true;
    }

    function formatValuationChips(st) {
      let parts = [];
      if (Array.isArray(st.val_chips) && st.val_chips.length > 0) {
        parts = st.val_chips
          .map(function (p) { return String(p || "").trim(); })
          .filter(function (p) {
            if (!p || p === "—" || p === "-") return false;
            if (/^(?:股息|分红|AH|A\s*折\s*H)/i.test(p)) return false;
            if (/^[+\-−]?\d+(?:\.\d+)?%$/.test(p)) return false;
            return true;
          })
          .slice(0, 2);
      } else {
        const raw = String(st.valuation || "").trim();
        if (raw) {
          if (raw.indexOf("/") !== -1) {
            const segs = raw.split(/\s*\/\s*/).map(function (s) { return s.trim(); });
            const peRaw = segs[0] || "";
            const pbRaw = st.market === "a-share" && segs.length >= 2 ? segs[1] || "" : "";
            if (peRaw && peRaw !== "—" && peRaw !== "-") {
              const hasLabel = /(?:PE|PB|PS|EV|P\/B|P\/S|P\/FFO|FFO|市盈|市净|亏损|负值|不适用|N\/A)/i.test(peRaw);
              parts.push(hasLabel ? peRaw : "PE " + peRaw);
            }
            if (pbRaw && pbRaw !== "—" && pbRaw !== "-" && !/%/.test(pbRaw) && !/AH/i.test(pbRaw)) {
              const hasPbLabel = /(?:PB|P\/B|PEV|市净|估值)/i.test(pbRaw);
              parts.push(hasPbLabel ? pbRaw : "PB " + pbRaw);
            }
            if (st.market !== "a-share") {
              for (let i = 1; i < segs.length; i++) {
                const seg = segs[i];
                if (!seg || seg === "—" || seg === "-") continue;
                if (/%/.test(seg) || /(?:股息|分红|AH|A\s*折\s*H)/i.test(seg)) continue;
                parts.push(seg);
              }
            }
          } else {
            const segs = raw
              .split(/\s*[·｜|;；]\s*/)
              .map(function (p) { return p.trim(); })
              .filter(function (p) {
                if (!p || p === "—" || p === "-") return false;
                if (/(?:股息|分红|AH\s*(?:溢价|折价|倒挂)?|A\s*折\s*H)/i.test(p)) return false;
                if (/^[+\-−]?\d+(?:\.\d+)?%$/.test(p)) return false;
                return true;
              });
            segs.forEach(function (seg, idx) {
              if (idx === 0 && /^[~≈<>≤≥]?\s*\d+(?:\.\d+)?(?:\s*[–—\-~]\s*\d+(?:\.\d+)?)?\s*x\+?$/i.test(seg)) {
                parts.push("PE " + seg);
              } else {
                parts.push(seg);
              }
            });
          }
        }
      }
      if (parts.length === 0) return "";
      return '<div class="val-chips"><span class="val-chip">' + escHtml(parts.slice(0, 2).join(" · ")) + "</span></div>";
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
        } else if (["base", "high-div", "near-anchor", "ah-inverted", "hide-red", "watchlist"].indexOf(token) !== -1) {
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
          } else if (k === "preset" && ["all", "base", "high-div", "near-anchor", "ah-inverted", "hide-red", "watchlist"].indexOf(v) !== -1) {
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
      const scrAdvPanel = document.querySelector("#scr-view-pool .filter-panel") || document.querySelector(".filter-panel");
      if (scrAdvPanel) {
        const advTray = scrAdvPanel.querySelector(".filter-adv-tray");
        if (advTray) {
          const hasAdvHash =
            state.sectors.size > 0 ||
            (state.color !== "all" && !!advTray.querySelector("[data-filter-color]")) ||
            (state.market !== "all" && !!advTray.querySelector("[data-filter-market]"));
          if (hasAdvHash) setAdvFilterTrayOpen(scrAdvPanel, true);
        }
      }
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

    function renderScreener(syncHash, keepPage) {
      if (!hasData) return;
      if (!keepPage) scrPager.reset();
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
      currentFilteredStocks = rows;
      syncSortHeaders();

      const pgBounds = scrPager.getBounds(rows.length);
      if (countEl) {
        countEl.textContent = scrPager.formatCount(rows.length, allStocks.length, "家龙头公司");
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
            .map(function (st, idx) {
              const pgCls = idx < pgBounds.start || idx >= pgBounds.end ? " pg-hidden" : "";
              const mark = COLOR_MARK[st.color] || "●";
              const dKey = st.market + ":" + st.code;
              const isStar = WatchlistStore.has(dKey) || WatchlistStore.has("stk_" + st.code);
              const starBtn =
                '<button type="button" class="star-btn' + (isStar ? " active" : "") + '" data-watch-toggle="1" data-watch-kind="stock" ' +
                'data-watch-id="' + escHtml(dKey) + '" data-watch-kline="' + escHtml("stk_" + st.code) + '" ' +
                'data-watch-code="' + escHtml(st.code) + '" data-watch-name="' + escHtml(st.name) + '" aria-label="切换自选">' +
                (isStar ? "★" : "☆") + "</button>";
              const dBtn = st.dossier
                ? ' <button type="button" class="dossier-btn" data-dossier-key="' + escHtml(dKey) + '">7维深研</button>' +
                  ' <button type="button" class="kline-quick-btn" data-dossier-key="' + escHtml(dKey) + '" data-open-tab="kline" title="查看交互 K 线">📈 K线</button>'
                : "";
              return (
                '<tr class="row-' + escHtml(st.color) + pgCls + '" data-market="' + escHtml(st.market) + '">' +
                '<td class="col-sticky"><span class="mkt-badge mkt-' + escHtml(st.market) + '">' + escHtml(st.market_label) + "</span></td>" +
                '<td>' + starBtn + ' <strong>' + escHtml(st.name) + '</strong> <span class="code-tag">' + escHtml(st.code) + "</span></td>" +
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
            .map(function (st, idx) {
              const pgCls = idx < pgBounds.start || idx >= pgBounds.end ? " pg-hidden" : "";
              const mark = COLOR_MARK[st.color] || "●";
              const divAh = formatDivAhCell(st);
              const hasDivAh = divAh.indexOf("val-chips") !== -1;
              const dKey = st.market + ":" + st.code;
              const isStar = WatchlistStore.has(dKey) || WatchlistStore.has("stk_" + st.code);
              const starBtn =
                '<button type="button" class="star-btn' + (isStar ? " active" : "") + '" data-watch-toggle="1" data-watch-kind="stock" ' +
                'data-watch-id="' + escHtml(dKey) + '" data-watch-kline="' + escHtml("stk_" + st.code) + '" ' +
                'data-watch-code="' + escHtml(st.code) + '" data-watch-name="' + escHtml(st.name) + '" aria-label="切换自选">' +
                (isStar ? "★" : "☆") + "</button>";
              return (
                '<div class="stock-card scr-mcard sc-' + escHtml(st.color) + pgCls + '">' +
                '<div class="sc-top">' +
                '<div class="sc-title">' +
                starBtn +
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
                '<div style="display:flex;gap:6px;flex-wrap:wrap;">' +
                (st.dossier
                  ? '<button type="button" class="dossier-btn" style="margin-left:0;" data-dossier-key="' + escHtml(dKey) + '">7 维档案</button>' +
                    '<button type="button" class="kline-quick-btn" data-dossier-key="' + escHtml(dKey) + '" data-open-tab="kline">📈 K线</button>'
                  : "") +
                "</div>" +
                '<a href="' + escHtml(st.report_url) + '" style="font-size:12.5px;font-weight:700;">全景手册 →</a>' +
                "</div>" +
                "</div>"
              );
            })
            .join("");
        }
      }
      scrPager.renderBar(rows.length);
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

    let activeDossierChart = null;
    let currentDossierKey = "";
    let currentDossierTab = "dossier";
    function destroyDossierChart() {
      if (activeDossierChart) {
        try { activeDossierChart.destroy(); } catch (_) {}
        activeDossierChart = null;
      }
    }

    function getStockNavList() {
      const filtered = currentFilteredStocks.filter(function (s) { return !!(s && s.dossier); });
      if (filtered.some(function (s) { return s.market + ":" + s.code === currentDossierKey; })) {
        return filtered;
      }
      return allStocks.filter(function (s) { return !!(s && s.dossier); });
    }

    function syncStockStepButtons() {
      if (!dossierModal) return;
      const navList = getStockNavList();
      const idx = navList.findIndex(function (s) { return s.market + ":" + s.code === currentDossierKey; });
      const prevBtn = dossierModal.querySelector('[data-drawer-step="-1"]');
      const nextBtn = dossierModal.querySelector('[data-drawer-step="1"]');
      const posEl = dossierModal.querySelector("[data-drawer-pos]");
      if (prevBtn) prevBtn.disabled = idx <= 0;
      if (nextBtn) nextBtn.disabled = idx < 0 || idx >= navList.length - 1;
      if (posEl) posEl.textContent = idx >= 0 ? (idx + 1) + " / " + navList.length : "";
    }

    function stepStockDossier(delta) {
      if (!dossierModal || !dossierModal.classList.contains("open")) return;
      const navList = getStockNavList();
      if (navList.length <= 1) return;
      const idx = navList.findIndex(function (s) { return s.market + ":" + s.code === currentDossierKey; });
      if (idx < 0) return;
      const nextIdx = idx + delta;
      if (nextIdx < 0 || nextIdx >= navList.length) return;
      const nextSt = navList[nextIdx];
      const nextKey = nextSt.market + ":" + nextSt.code;
      const listIdx = currentFilteredStocks.findIndex(function (s) { return s.market + ":" + s.code === nextKey; });
      scrPager.goToIndex(listIdx >= 0 ? listIdx : nextIdx);
      openStockDossier(nextKey, currentDossierTab, true);
    }

    function openStockDossier(key, initialTab, keepOpen) {
      const st = stockByKey.get(key);
      if (!st || !st.dossier || !dossierModal) return;
      destroyDossierChart();
      const d = st.dossier;
      const mark = COLOR_MARK[st.color] || "●";
      const dKey = st.market + ":" + st.code;
      currentDossierKey = dKey;
      const klineSym = "stk_" + st.code;
      const isStar = WatchlistStore.has(dKey) || WatchlistStore.has(klineSym);
      if (dossierTitle) dossierTitle.textContent = st.name + " (" + st.code + ")";
      if (dossierSub) {
        const bn = String(d.baseline_note || "").trim();
        const hasPriceInBaseline =
          !!bn &&
          /(?:参考价|日终收|收盘|官收|现价|收报|股价|\d+(?:\.\d+)?\s*(?:元|港元|美元|HK\$|\$|RMB))/.test(bn);
        dossierSub.textContent =
          (bn ? bn + " ｜ " : "") +
          "赛道：" + st.sector +
          (hasPriceInBaseline ? "" : " ｜ 现价：" + st.price);
      }
      if (dossierBadges) {
        const isCore = d.depth_tier === "core_deep";
        dossierBadges.innerHTML =
          '<span class="mkt-badge mkt-' + escHtml(st.market) + '">' + escHtml(st.market_label) + "</span>" +
          '<span class="act-pill act-' + escHtml(st.color) + '">' + mark + " " + escHtml(st.action_label) + "</span>" +
          '<span class="dossier-depth-badge ' + (isCore ? "depth-core" : "depth-std") + '">' +
          (isCore ? "核心旗舰 7 维全拆解" : "池内标准 7 维档案") + "</span>" +
          '<button type="button" class="star-btn' + (isStar ? " active" : "") + '" data-watch-toggle="1" data-watch-kind="stock" ' +
          'data-watch-id="' + escHtml(dKey) + '" data-watch-kline="' + escHtml(klineSym) + '" ' +
          'data-watch-code="' + escHtml(st.code) + '" data-watch-name="' + escHtml(st.name) + '" aria-label="切换自选">' +
          (isStar ? "★" : "☆") + "</button>";
      }
      const startTab = initialTab === "kline" ? "kline" : "dossier";
      currentDossierTab = startTab;
      if (dossierBody) {
        const dossierGridHtml =
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
        dossierBody.innerHTML =
          '<div class="modal-tab-bar">' +
          '<div class="modal-tab-group" role="tablist" style="display:flex;gap:6px;flex-wrap:wrap;">' +
          '<button type="button" role="tab" aria-selected="' + (startTab === "dossier" ? "true" : "false") + '" class="modal-tab-btn' + (startTab === "dossier" ? " active" : "") + '" data-modal-tab="dossier">📋 7 维机构深研</button>' +
          '<button type="button" role="tab" aria-selected="' + (startTab === "kline" ? "true" : "false") + '" class="modal-tab-btn' + (startTab === "kline" ? " active" : "") + '" data-modal-tab="kline">📈 互动 K 线与技术指标</button>' +
          "</div>" +
          '<a class="btn btn-sm modal-tab-ext" href="charts.html#sym=' + encodeURIComponent(klineSym) + '">全屏终端 ↗</a>' +
          "</div>" +
          '<div class="modal-tab-pane" data-modal-pane="dossier"' + (startTab === "kline" ? " hidden" : "") + ">" + dossierGridHtml + "</div>" +
          '<div class="modal-tab-pane" data-modal-pane="kline"' + (startTab !== "kline" ? " hidden" : "") + ">" +
          '<div class="kline-mount" id="dossier-kline-mount"></div></div>';
        dossierBody.scrollTop = 0;

        function mountDossierKline() {
          const mountEl = document.getElementById("dossier-kline-mount");
          if (!mountEl || !window.GIRKline) return;
          if (!activeDossierChart) {
            activeDossierChart = window.GIRKline.mount(mountEl, {
              symbolId: klineSym,
              height: 310,
              mode: "modal",
              anchorLow: st.anchor_low,
              anchorHigh: st.anchor_high,
              goldLocked: !!st.is_gold_locked,
            });
          } else {
            activeDossierChart.resize();
          }
        }

        dossierBody.querySelectorAll("[data-modal-tab]").forEach(function (tBtn) {
          tBtn.addEventListener("click", function () {
            const target = tBtn.getAttribute("data-modal-tab");
            currentDossierTab = target === "kline" ? "kline" : "dossier";
            dossierBody.querySelectorAll("[data-modal-tab]").forEach(function (b) {
              const isAct = b === tBtn;
              b.classList.toggle("active", isAct);
              b.setAttribute("aria-selected", isAct ? "true" : "false");
            });
            dossierBody.querySelectorAll("[data-modal-pane]").forEach(function (p) {
              p.hidden = p.getAttribute("data-modal-pane") !== target;
            });
            if (target === "kline") {
              window.requestAnimationFrame(mountDossierKline);
            }
          });
        });
        if (startTab === "kline") {
          window.requestAnimationFrame(mountDossierKline);
        }
      }
      if (dossierFootLink) dossierFootLink.setAttribute("href", st.report_url || "#");
      if (dossierFootDate) {
        const fallbackDate = dossierFootDate.getAttribute("data-default-date") || "最新班次";
        const bmPrefix = st.benchmark_time ? "主表基线（旗舰基准）：" + st.benchmark_time + " ｜ " : "";
        dossierFootDate.textContent = bmPrefix + "7 维档案刷新日：" + (d.updated_at || fallbackDate);
      }
      syncStockStepButtons();
      if (dossierBadges) dossierBadges.scrollLeft = 0;
      if (!keepOpen || !dossierModal.classList.contains("open")) {
        const closeBtn = dossierModal.querySelector("[data-action='close-dossier']");
        showDialog(dossierModal, closeBtn);
      }
    }

    if (dossierModal) {
      dossierModal._girStep = stepStockDossier;
      dossierModal._girClose = function () { destroyDossierChart(); hideDialog(dossierModal); };
      document.querySelectorAll("[data-action='close-dossier']").forEach(function (b) {
        b.addEventListener("click", dossierModal._girClose);
      });
      dossierModal.addEventListener("click", function (e) {
        const stepBtn = e.target.closest("[data-drawer-step]");
        if (stepBtn && !stepBtn.disabled) {
          e.preventDefault();
          const delta = parseInt(stepBtn.getAttribute("data-drawer-step") || "0", 10);
          if (delta) stepStockDossier(delta);
          return;
        }
        if (e.target === dossierModal) { dossierModal._girClose(); }
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
          openStockDossier(dBtn.getAttribute("data-dossier-key"), dBtn.getAttribute("data-open-tab") || "dossier");
          return;
        }
        if (container === tbody && !e.target.closest("button, a, input, select, label, .star-btn")) {
          if (window.getSelection && String(window.getSelection()).trim()) return;
          const tr = e.target.closest("tr");
          const rowBtn = tr ? tr.querySelector("[data-dossier-key]") : null;
          if (rowBtn) {
            openStockDossier(rowBtn.getAttribute("data-dossier-key"), "dossier");
          }
        }
      });
    });

    /* 10B. 27-Pair A/H After-Tax Dividend & Arbitrage Matrix View on screener.html */
    const scrViewBtns = Array.from(document.querySelectorAll("[data-scr-view]"));
    const scrSubnavLinks = Array.from(document.querySelectorAll('.subnav-bar a[href*="screener.html"]'));
    const scrPoolPane = document.getElementById("scr-view-pool");
    const scrAhPane = document.getElementById("scr-view-ah");
    const ahDataEl = document.getElementById("ah-matrix-data");
    const ahTbody = document.getElementById("ah-matrix-tbody");
    const ahCardsEl = document.getElementById("ah-matrix-cards");
    const ahCountEl = document.getElementById("ah-matrix-count");
    const ahFilterBtns = Array.from(document.querySelectorAll("[data-ah-filter]"));
    let ahRowsAll = [];
    let ahFilter = "all";
    let ahSortKey = "ah_premium_pct";
    let ahSortDir = -1;

    if (ahDataEl) {
      try {
        const parsedAh = JSON.parse(ahDataEl.textContent || "[]");
        if (Array.isArray(parsedAh)) ahRowsAll = parsedAh;
      } catch (_) {}
    }

    function renderAhMatrix() {
      if ((!ahTbody && !ahCardsEl) || ahRowsAll.length === 0) return;
      ahFilterBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-ah-filter") || "all") === ahFilter);
      });
      document.querySelectorAll("[data-ah-sort]").forEach(function (th) {
        const k = th.getAttribute("data-ah-sort");
        const isAct = k === ahSortKey;
        th.setAttribute("aria-sort", isAct ? (ahSortDir === 1 ? "ascending" : "descending") : "none");
        th.setAttribute("data-sort-dir", isAct ? (ahSortDir === 1 ? "asc" : "desc") : "");
        const btn = th.querySelector("button");
        if (btn) {
          const base = btn.textContent.replace(/\s*[⇅▲▼]\s*$/, "");
          btn.textContent = base + " " + (isAct ? (ahSortDir === 1 ? "▲" : "▼") : "⇅");
        }
      });
      let rows = ahRowsAll.filter(function (r) {
        if (ahFilter === "a-cheaper") return isFiniteNum(r.ah_premium_pct) && r.ah_premium_pct < 0;
        if (ahFilter === "hk-connect-wins") return isFiniteNum(r.net_div_spread) && r.net_div_spread > 0;
        if (ahFilter === "a-div-wins") return isFiniteNum(r.net_div_spread) && r.net_div_spread <= 0 && isFiniteNum(r.a_div_pct) && r.a_div_pct > 0;
        if (ahFilter === "high-prem") return isFiniteNum(r.ah_premium_pct) && r.ah_premium_pct >= 50;
        return true;
      });
      rows = rows.slice().sort(function (a, b) {
        const va = a[ahSortKey];
        const vb = b[ahSortKey];
        if (isFiniteNum(va) && isFiniteNum(vb)) return (va - vb) * ahSortDir;
        if (isFiniteNum(va)) return -1;
        if (isFiniteNum(vb)) return 1;
        return String(a.name || "").localeCompare(String(b.name || ""), "zh-Hans-CN") * ahSortDir;
      });
      if (ahCountEl) {
        ahCountEl.textContent = "显示 " + rows.length + " / " + ahRowsAll.length + " 对 A/H 孪生股";
      }
      const prepared = rows.map(function (r) {
        const prem = isFiniteNum(r.ah_premium_pct) ? r.ah_premium_pct : null;
        const premCls = prem != null && prem < 0 ? "ah-pill ah-disc" : "ah-pill ah-prem";
        const premTxt = prem != null ? (prem >= 0 ? "+" : "") + prem.toFixed(1) + "%" : "—";
        const barPct = prem != null ? Math.min(100, Math.round((Math.abs(prem) / 120) * 100)) : 0;
        const barHtml =
          prem == null
            ? "—"
            : prem < 0
            ? '<div class="ah-bi-track"><div class="ah-bi-left"><span class="ah-bi-fill ah-bi-disc" style="width:' + barPct + '%;"></span></div><div class="ah-bi-right"></div></div>'
            : '<div class="ah-bi-track"><div class="ah-bi-left"></div><div class="ah-bi-right"><span class="ah-bi-fill ah-bi-prem" style="width:' + barPct + '%;"></span></div></div>';
        const aDiv = isFiniteNum(r.a_div_pct) ? r.a_div_pct.toFixed(2) + "%" : "—";
        const hDivNet = isFiniteNum(r.h_connect_after_tax_div) ? r.h_connect_after_tax_div.toFixed(2) + "%" : "—";
        const taxTag = r.h_tax_rate_pct ? "（扣" + r.h_tax_rate_pct + "%税）" : "";
        const spreadTxt = isFiniteNum(r.net_div_spread)
          ? (r.net_div_spread > 0 ? "港通高 +" + r.net_div_spread.toFixed(2) + "pp" : "A股高 +" + Math.abs(r.net_div_spread).toFixed(2) + "pp")
          : "无股息差对比";
        const btns = [];
        if (r.a_key) btns.push('<button type="button" class="dossier-btn" style="margin-left:0;" data-dossier-key="' + escHtml(r.a_key) + '">A 7维</button>');
        if (r.h_key) btns.push('<button type="button" class="dossier-btn" style="margin-left:0;" data-dossier-key="' + escHtml(r.h_key) + '">H 7维</button>');
        if (r.a_key) {
          btns.push('<button type="button" class="kline-quick-btn" data-dossier-key="' + escHtml(r.a_key) + '" data-open-tab="kline">📈 A股K线</button>');
        } else if (r.a_sym_id) {
          btns.push('<a class="kline-quick-btn" href="charts.html#sym=' + encodeURIComponent(r.a_sym_id) + '">📈 A股K线</a>');
        }
        if (r.h_key) {
          btns.push('<button type="button" class="kline-quick-btn" data-dossier-key="' + escHtml(r.h_key) + '" data-open-tab="kline">📈 H股K线</button>');
        } else if (r.h_sym_id) {
          btns.push('<a class="kline-quick-btn" href="charts.html#sym=' + encodeURIComponent(r.h_sym_id) + '">📈 H股K线</a>');
        }
        if (btns.length === 0) {
          btns.push('<span class="sec-sub">—</span>');
        }
        return {
          r: r,
          premCls: premCls,
          premTxt: premTxt,
          barHtml: barHtml,
          aDiv: aDiv,
          hDivNet: hDivNet,
          taxTag: taxTag,
          spreadTxt: spreadTxt,
          btnsHtml: btns.join(""),
        };
      });

      if (ahTbody) {
        if (prepared.length === 0) {
          ahTbody.innerHTML =
            '<tr><td colspan="6"><div class="empty-state">' +
            '<div class="empty-title">当前筛选条件下暂无匹配 A/H 孪生股</div>' +
            '<div class="empty-sub">点击「全部」查看完整 A/H 比价矩阵</div>' +
            "</div></td></tr>";
        } else {
          ahTbody.innerHTML = prepared
            .map(function (x) {
              const r = x.r;
              return (
                "<tr>" +
                '<td><strong>' + escHtml(r.name) + '</strong><div class="sec-sub">' + escHtml(r.a_code) + " / " + escHtml(r.h_code) + "</div></td>" +
                '<td><div>A: ' + escHtml(r.a_price || "—") + '</div><div class="sec-sub">H: ' + escHtml(r.h_price || "—") + "</div></td>" +
                '<td><span class="' + x.premCls + '">' + escHtml(x.premTxt) + "</span>" + x.barHtml + "</td>" +
                '<td><div>A 持有>1年免税: <strong>' + escHtml(x.aDiv) + '</strong></div><div class="sec-sub">H 港股通税后: <strong>' + escHtml(x.hDivNet) + "</strong>" + escHtml(x.taxTag) + "</div></td>" +
                '<td><div><span class="ah-verdict-pill ah-v-' + escHtml(r.verdict_tone || "neutral") + '">' + escHtml(r.verdict_label || "均衡") + '</span></div><div class="sec-sub">' + escHtml(x.spreadTxt) + "</div></td>" +
                '<td><div style="display:flex;gap:5px;flex-wrap:wrap;">' + x.btnsHtml + "</div></td>" +
                "</tr>"
              );
            })
            .join("");
        }
      }

      if (ahCardsEl) {
        if (prepared.length === 0) {
          ahCardsEl.innerHTML =
            '<div class="panel-card empty-state">' +
            '<div class="empty-title">当前筛选条件下暂无匹配 A/H 孪生股</div>' +
            '<div class="empty-sub">点击「全部」查看完整 A/H 比价矩阵</div>' +
            "</div>";
        } else {
          ahCardsEl.innerHTML = prepared
            .map(function (x) {
              const r = x.r;
              return (
                '<article class="ah-mcard">' +
                '<div class="ah-mcard-head">' +
                '<div><strong>' + escHtml(r.name) + '</strong><div class="sec-sub">' + escHtml(r.a_code) + " / " + escHtml(r.h_code) + "</div></div>" +
                '<div style="text-align:right;"><span class="' + x.premCls + '">AH ' + escHtml(x.premTxt) + "</span>" + x.barHtml + "</div>" +
                "</div>" +
                '<div class="ah-mcard-grid">' +
                '<div><div>A 股参考：<strong>' + escHtml(r.a_price || "—") + '</strong></div><div>H 股参考：<strong>' + escHtml(r.h_price || "—") + "</strong></div></div>" +
                '<div><div>A 免税息：<strong>' + escHtml(x.aDiv) + '</strong></div><div>H 港通税后：<strong>' + escHtml(x.hDivNet) + "</strong>" + escHtml(x.taxTag) + "</div></div>" +
                "</div>" +
                '<div class="ah-mcard-actions">' +
                '<div><span class="ah-verdict-pill ah-v-' + escHtml(r.verdict_tone || "neutral") + '">' + escHtml(r.verdict_label || "均衡") + '</span> <span class="sec-sub">' + escHtml(x.spreadTxt) + "</span></div>" +
                '<div style="display:flex;gap:5px;flex-wrap:wrap;">' + x.btnsHtml + "</div>" +
                "</div>" +
                "</article>"
              );
            })
            .join("");
        }
      }
    }

    function setScreenerView(viewName, syncHash) {
      const isAh = viewName === "ah-matrix";
      scrViewBtns.forEach(function (b) {
        const isAct = (b.getAttribute("data-scr-view") || "pool") === (isAh ? "ah-matrix" : "pool");
        b.classList.toggle("active", isAct);
        b.setAttribute("aria-selected", isAct ? "true" : "false");
      });
      scrSubnavLinks.forEach(function (a) {
        const href = a.getAttribute("href") || "";
        const isAhLink = href.indexOf("view=ah-matrix") !== -1;
        a.classList.toggle("active", isAh ? isAhLink : !isAhLink);
      });
      if (scrPoolPane) scrPoolPane.hidden = isAh;
      if (scrAhPane) scrAhPane.hidden = !isAh;
      if (isAh) renderAhMatrix();
      if (syncHash && history.replaceState) {
        try {
          history.replaceState(null, "", isAh ? "#view=ah-matrix" : window.location.pathname + window.location.search);
        } catch (_) {}
      }
    }

    scrSubnavLinks.forEach(function (a) {
      a.addEventListener("click", function (e) {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        const href = a.getAttribute("href") || "";
        const targetIsAh = href.indexOf("view=ah-matrix") !== -1;
        e.preventDefault();
        setScreenerView(targetIsAh ? "ah-matrix" : "pool", true);
      });
    });

    scrViewBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        setScreenerView(b.getAttribute("data-scr-view") || "pool", true);
      });
    });
    ahFilterBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        ahFilter = b.getAttribute("data-ah-filter") || "all";
        renderAhMatrix();
      });
    });
    document.querySelectorAll("[data-ah-sort]").forEach(function (th) {
      const btn = th.querySelector("button") || th;
      btn.addEventListener("click", function () {
        const k = th.getAttribute("data-ah-sort");
        if (ahSortKey === k) ahSortDir *= -1;
        else { ahSortKey = k; ahSortDir = -1; }
        renderAhMatrix();
      });
    });
    [ahTbody, ahCardsEl].forEach(function (el) {
      if (!el) return;
      el.addEventListener("click", function (e) {
        const dBtn = e.target.closest("[data-dossier-key]");
        if (dBtn) {
          openStockDossier(dBtn.getAttribute("data-dossier-key"), dBtn.getAttribute("data-open-tab") || "dossier");
        }
      });
    });

    window.addEventListener("gir:watchlist-change", function () {
      if (state.preset === "watchlist") renderScreener(false, true);
    });

    window.addEventListener("hashchange", function () {
      if ((window.location.hash || "").indexOf("view=ah-matrix") !== -1) {
        setScreenerView("ah-matrix", false);
        return;
      }
      setScreenerView("pool", false);
      if (applyHashToState(true)) {
        renderSectorControls();
        renderScreener(false);
      }
    });

    if (hasData) {
      if ((window.location.hash || "").indexOf("view=ah-matrix") !== -1) {
        setScreenerView("ah-matrix", false);
      } else {
        applyHashToState();
      }
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
        const top = window.scrollY + tabBar.getBoundingClientRect().top - getStickyOffset();
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

    const scSearchInput = document.getElementById("sc-search");
    const scClearBtn = document.getElementById("sc-clear");
    const scStatusEl = document.getElementById("sc-filter-status");
    let scSearchTimer = 0;

    function resetPanelVisibility(body) {
      if (!body) return;
      body.querySelectorAll("[data-sc-hidden]").forEach(function (el) {
        el.removeAttribute("data-sc-hidden");
        el.style.display = "";
      });
    }

    function setScHidden(el, hide) {
      if (!el) return;
      if (hide) {
        el.setAttribute("data-sc-hidden", "1");
        el.style.display = "none";
      } else {
        el.removeAttribute("data-sc-hidden");
        el.style.display = "";
      }
    }

    function applyScorecardFilter() {
      const q = scSearchInput ? scSearchInput.value.trim() : "";
      if (scClearBtn) {
        scClearBtn.hidden = !q;
        scClearBtn.style.display = q ? "" : "none";
      }
      document.querySelectorAll(".tab-panel .article-body").forEach(resetPanelVisibility);
      const activePanel = document.querySelector(".tab-panel.active .article-body");
      if (!q || !activePanel) {
        if (scStatusEl) scStatusEl.textContent = "";
        return;
      }

      const tokens = q.toLowerCase().split(/\s+/).filter(Boolean);
      const matchText = function (txt) {
        const low = String(txt || "").toLowerCase();
        return tokens.every(function (tk) { return low.indexOf(tk) !== -1; });
      };

      const children = Array.from(activePanel.children);
      const sections = [];
      let curSec = { head: null, items: [] };
      children.forEach(function (ch) {
        if (ch.tagName === "H2") {
          if (curSec.head || curSec.items.length > 0) sections.push(curSec);
          curSec = { head: ch, items: [] };
        } else {
          curSec.items.push(ch);
        }
      });
      if (curSec.head || curSec.items.length > 0) sections.push(curSec);

      let matchedCount = 0;
      sections.forEach(function (sec) {
        if (sec.head && matchText(sec.head.textContent)) {
          matchedCount += 1;
          return;
        }
        let secHits = 0;
        let pendingSubHeads = [];
        const flushSubHeads = function (keep) {
          pendingSubHeads.forEach(function (h) { setScHidden(h, !keep); });
          pendingSubHeads = [];
        };

        sec.items.forEach(function (el) {
          const tag = el.tagName;
          if (tag === "H1") {
            return;
          }
          if (tag === "HR") {
            setScHidden(el, true);
            return;
          }
          if (tag === "H3" || tag === "H4") {
            flushSubHeads(false);
            if (matchText(el.textContent)) {
              secHits += 1;
              matchedCount += 1;
            } else {
              pendingSubHeads.push(el);
            }
            return;
          }
          const table = tag === "TABLE" ? el : (el.classList.contains("table-wrap") ? el.querySelector("table") : null);
          if (table) {
            const rows = Array.from(table.querySelectorAll("tbody tr"));
            let rowHits = 0;
            rows.forEach(function (tr) {
              const ok = matchText(tr.textContent);
              setScHidden(tr, !ok);
              if (ok) rowHits += 1;
            });
            setScHidden(el, rowHits === 0);
            if (rowHits > 0) {
              flushSubHeads(true);
              secHits += rowHits;
              matchedCount += rowHits;
            }
            return;
          }
          if (tag === "UL" || tag === "OL") {
            const lis = Array.from(el.children).filter(function (c) { return c.tagName === "LI"; });
            let liHits = 0;
            lis.forEach(function (li) {
              const ok = matchText(li.textContent);
              setScHidden(li, !ok);
              if (ok) liHits += 1;
            });
            setScHidden(el, liHits === 0);
            if (liHits > 0) {
              flushSubHeads(true);
              secHits += liHits;
              matchedCount += liHits;
            }
            return;
          }
          const ok = matchText(el.textContent);
          setScHidden(el, !ok);
          if (ok) {
            flushSubHeads(true);
            secHits += 1;
            matchedCount += 1;
          }
        });
        flushSubHeads(false);
        if (sec.head) {
          setScHidden(sec.head, secHits === 0);
        }
      });

      if (scStatusEl) {
        scStatusEl.textContent =
          matchedCount > 0
            ? "当前标签匹配 " + matchedCount + " 条记录"
            : "当前标签未找到匹配项（可切换上方其他标签试试）";
      }
    }

    tabBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        activateTab(btn.getAttribute("data-tab-target"), true);
        applyScorecardFilter();
      });
    });
    if (scSearchInput) {
      scSearchInput.addEventListener("input", function () {
        if (scClearBtn) {
          const hasQ = !!scSearchInput.value;
          scClearBtn.hidden = !hasQ;
          scClearBtn.style.display = hasQ ? "" : "none";
        }
        window.clearTimeout(scSearchTimer);
        scSearchTimer = window.setTimeout(applyScorecardFilter, 60);
      });
    }
    if (scClearBtn) {
      scClearBtn.addEventListener("click", function () {
        window.clearTimeout(scSearchTimer);
        if (scSearchInput) {
          scSearchInput.value = "";
          scSearchInput.focus();
        }
        applyScorecardFilter();
      });
    }
    const initHash = (window.location.hash || "").replace(/^#/, "");
    const matchedInit = activateTab(initHash || tabBtns[0].getAttribute("data-tab-target"), false);
    if (initHash && matchedInit) {
      keepTabBarVisible();
      window.addEventListener("load", keepTabBarVisible, { once: true });
    }
    window.addEventListener("hashchange", function () {
      const h = (window.location.hash || "").replace(/^#/, "");
      if (h && activateTab(h, false)) {
        applyScorecardFilter();
        keepTabBarVisible();
      }
    });
  }

  /* ------------------------------------------------------------------------
     12. Supercharged Archive Chronological Filters + URL Hash Sync
     ------------------------------------------------------------------------ */
  const arcItems = Array.from(document.querySelectorAll("[data-arc-item]"));
  if (arcItems.length > 0) {
    const arcState = { market: "all", session: "all", editionType: "all", q: "", showSuperseded: false };
    const arcMktBtns = Array.from(document.querySelectorAll("[data-arc-market]"));
    const arcSesBtns = Array.from(document.querySelectorAll("[data-arc-session]"));
    const arcTypeBtns = Array.from(document.querySelectorAll("[data-arc-type]"));
    const arcSearchInput = document.getElementById("arc-search");
    const arcClearBtn = document.getElementById("arc-clear-x");
    const arcShowSupInput = document.getElementById("arc-show-superseded");
    const arcCountEl = document.getElementById("arc-count");
    const arcEmptyEl = document.getElementById("arc-empty");
    const arcResetBtn = document.getElementById("arc-reset");
    const arcEmptyResetBtn = document.getElementById("arc-empty-reset");
    const arcActiveTotal = arcItems.filter(function (el) {
      return el.getAttribute("data-superseded") !== "1";
    }).length;

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
      if (arcShowSupInput) {
        arcShowSupInput.checked = !!arcState.showSuperseded;
      }
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
        const isSup = el.getAttribute("data-superseded") === "1";
        let ok =
          (!isSup || arcState.showSuperseded) &&
          (arcState.market === "all" || m === arcState.market) &&
          (arcState.session === "all" || s === arcState.session) &&
          (arcState.editionType === "all" || ed === arcState.editionType);

        if (ok && tokens.length > 0) {
          const hay = ((el.getAttribute("data-search") || "") + " " + (el.textContent || "")).toLowerCase();
          ok = tokens.every(function (tk) { return hay.indexOf(tk) !== -1; });
        }

        el.hidden = !ok;
        el.style.display = ok ? "" : "none";
        if (ok) shown++;
      });

      document.querySelectorAll(".archive-day").forEach(function (day) {
        const dayVis = Array.from(day.querySelectorAll("[data-arc-item]")).filter(function (el) {
          return el.style.display !== "none" && !el.hidden;
        }).length;
        day.style.display = dayVis > 0 ? "" : "none";
        const cntEl = day.querySelector(".arc-day-cnt");
        if (cntEl) {
          cntEl.textContent = "（共 " + dayVis + " 期）";
        }
      });

      const baseTotal = arcState.showSuperseded ? arcItems.length : arcActiveTotal;
      if (arcCountEl) {
        arcCountEl.textContent = "共展示 " + shown + " / " + baseTotal + " 期历史日报";
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
      arcState.showSuperseded = false;
      if (arcSearchInput) arcSearchInput.value = "";
      if (arcShowSupInput) arcShowSupInput.checked = false;
      syncArchiveUrlHash();
      applyArchiveFilter();
    }

    if (arcShowSupInput) {
      arcShowSupInput.addEventListener("change", function () {
        arcState.showSuperseded = !!arcShowSupInput.checked;
        applyArchiveFilter();
      });
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
  const chCountInitText = chCount ? chCount.textContent : "";
  let homeChActiveBar = document.getElementById("home-ch-active-bar");
  let chResetBtn = document.getElementById("ch-reset-empty");
  let chBucket = "all";
  let chCat = "all";
  const HOME_BUCKET_LABELS = {
    liquid: "💧 第一笔：活钱应急池（0–6 个月）",
    stable: "🛡️ 第二笔：稳钱压舱池（1–3 年）",
    growth: "🌱 第三笔：长钱复利池（3–5 年+）",
    protection: "🏥 第四笔：保障与超长锁息（10 年+）",
  };

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
    document.querySelectorAll("[data-jump-bucket]").forEach(function (b) {
      b.classList.toggle("active", chBucket !== "all" && b.getAttribute("data-jump-bucket") === chBucket);
    });
    chCards.forEach(function (c) {
      const okBucket = chBucket === "all" || c.getAttribute("data-channel-bucket") === chBucket;
      const okCat = chCat === "all" || c.getAttribute("data-channel-cat") === chCat;
      const ok = okBucket && okCat;
      c.style.display = ok ? "" : "none";
      if (ok) shown++;
    });
    document.querySelectorAll(".ch-role-group").forEach(function (grp) {
      const grpCards = grp.querySelectorAll(".ch-overview-card, .channel-card");
      let visCnt = 0;
      grpCards.forEach(function (card) {
        if (card.style.display !== "none") visCnt++;
      });
      grp.style.display = visCnt === 0 ? "none" : "";
      const cntEl = grp.querySelector(".ch-role-count");
      if (cntEl) cntEl.textContent = visCnt + " 大渠道";
    });
    if (chBucketBtns.length === 0) {
      if (!homeChActiveBar) {
        const secHead = document.getElementById("sec-multi-channels");
        if (secHead && secHead.parentNode) {
          homeChActiveBar = document.createElement("div");
          homeChActiveBar.id = "home-ch-active-bar";
          homeChActiveBar.className = "home-ch-active-bar";
          homeChActiveBar.hidden = true;
          secHead.insertAdjacentElement("afterend", homeChActiveBar);
        }
      }
      if (homeChActiveBar) {
        if (chBucket !== "all" || chCat !== "all") {
          const activeLabel = HOME_BUCKET_LABELS[chBucket] || (chBucket !== "all" ? chBucket : chCat);
          homeChActiveBar.hidden = false;
          homeChActiveBar.style.display = "";
          homeChActiveBar.innerHTML =
            '<span class="home-ch-active-label">当前筛选：<strong>' +
            escHtml(activeLabel) +
            "</strong>（显示 " +
            shown +
            " / " +
            chCards.length +
            ' 大渠道）</span><button type="button" class="home-ch-reset-btn" data-action="home-ch-reset">显示全部 12 大渠道 ✕</button>';
        } else {
          homeChActiveBar.hidden = true;
          homeChActiveBar.style.display = "none";
          homeChActiveBar.innerHTML = "";
        }
      }
    }
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
        if (chBucket === "all" && chCat === "all" && chCountInitText) {
          chCount.textContent = chCountInitText;
        } else {
          chCount.textContent = "显示 " + shown + " / " + chCards.length + " 大合规个人投资渠道";
        }
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
    document.addEventListener("click", function (e) {
      if (e.target.closest("[data-action='home-ch-reset']")) {
        chBucket = "all";
        chCat = "all";
        applyChFilter();
      }
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
        const top = window.scrollY + targetSec.getBoundingClientRect().top - getStickyOffset();
        window.scrollTo({ top: Math.max(0, top), behavior: prefersReducedMotion ? "auto" : "smooth" });
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
  const ETF_ASSET_CLASS_LABELS = {
    equity: "股票权益",
    fixed_income: "利率信用债",
    cash_mmf: "现金货币盾",
    gold: "黄金(红灯)",
    commodity: "非金商品",
    convertible_bond: "可转债",
    reits: "REITs",
    fixed_income_plus: "固收/现金/转债/REITs",
    gold_commodity: "黄金与商品",
  };
  const ETF_COMPOSITE_ASSET_CLASSES = {
    fixed_income_plus: ["fixed_income", "cash_mmf", "convertible_bond", "reits"],
    gold_commodity: ["gold", "commodity"],
  };
  const ETF_REGION_LABELS = {
    cn: "中国境内",
    hk: "中国香港",
    us: "美国",
    jp: "日本",
    eu: "欧洲",
    apac_em: "亚太新兴",
    global: "全球",
    non_us: "非美海外",
  };
  const VALID_ETF_ASSET_CLASSES = [
    "all",
    "equity",
    "fixed_income",
    "cash_mmf",
    "gold",
    "commodity",
    "convertible_bond",
    "reits",
    "fixed_income_plus",
    "gold_commodity",
  ];
  const VALID_ETF_REGIONS = ["all", "cn", "hk", "us", "jp", "eu", "apac_em", "global", "non_us"];
  const VALID_ETF_PRESETS = ["all", "qdii", "low-fee", "base", "cash-shield", "high-risk", "hide-gold", "watchlist"];

  function buildEtfOrthoTag(it) {
    if (!it) return "";
    const parts = [];
    if (it.asset_class) parts.push(ETF_ASSET_CLASS_LABELS[it.asset_class] || it.asset_class);
    if (it.region) parts.push(ETF_REGION_LABELS[it.region] || it.region);
    if (parts.length === 0) return "";
    return '<span class="etf-ortho-tag">' + escHtml(parts.join(" · ")) + "</span>";
  }

  function cleanEtfDisplayText(txt) {
    return String(txt || "").replace(/[（(]红灯锁[）)]\s*$/, "").trim();
  }

  function etfRoleClass(it) {
    if (it.gold_locked) return "role-lock";
    const r = String(it.action_role || "");
    if (r.indexOf("高危") !== -1 || r.indexOf("高费") !== -1) return "role-danger";
    if (r.indexOf("现金盾") !== -1) return "role-shield";
    if (r.indexOf("底座") !== -1 || r.indexOf("核心") !== -1 || r.indexOf("卫星") !== -1) return "role-base";
    return "role-watch";
  }

  function createEtfModalController(etfList, getNavList, onStep) {
    const etfModal = document.getElementById("etf-modal");
    const etfModalTitle = document.getElementById("etf-modal-title");
    const etfModalSub = document.getElementById("etf-modal-sub");
    const etfModalBadges = document.getElementById("etf-modal-badges");
    const etfModalBody = document.getElementById("etf-modal-body");
    const etfByCode = new Map();
    etfList.forEach(function (it) {
      if (it && it.code) etfByCode.set(String(it.code), it);
    });

    let activeEtfChart = null;
    let currentEtfCode = "";
    let currentEtfTab = "detail";
    function destroyEtfChart() {
      if (activeEtfChart) {
        try { activeEtfChart.destroy(); } catch (_) {}
        activeEtfChart = null;
      }
    }

    function resolveEtfNavList() {
      const candidate = typeof getNavList === "function" ? getNavList() : etfList;
      if (Array.isArray(candidate) && candidate.some(function (x) { return x && String(x.code) === currentEtfCode; })) {
        return candidate;
      }
      return etfList;
    }

    function syncEtfStepButtons() {
      if (!etfModal) return;
      const navList = resolveEtfNavList();
      const idx = navList.findIndex(function (x) { return x && String(x.code) === currentEtfCode; });
      const prevBtn = etfModal.querySelector('[data-drawer-step="-1"]');
      const nextBtn = etfModal.querySelector('[data-drawer-step="1"]');
      const posEl = etfModal.querySelector("[data-drawer-pos]");
      if (prevBtn) prevBtn.disabled = idx <= 0;
      if (nextBtn) nextBtn.disabled = idx < 0 || idx >= navList.length - 1;
      if (posEl) posEl.textContent = idx >= 0 ? (idx + 1) + " / " + navList.length : "";
    }

    function stepEtf(delta) {
      if (!etfModal || !etfModal.classList.contains("open")) return;
      const navList = resolveEtfNavList();
      if (navList.length <= 1) return;
      const idx = navList.findIndex(function (x) { return x && String(x.code) === currentEtfCode; });
      if (idx < 0) return;
      const nextIdx = idx + delta;
      if (nextIdx < 0 || nextIdx >= navList.length) return;
      if (typeof onStep === "function") onStep(nextIdx, navList[nextIdx]);
      openEtfModal(navList[nextIdx].code, currentEtfTab, true);
    }

    function openEtfModal(code, initialTab, keepOpen) {
      const it = etfByCode.get(String(code || ""));
      if (!it || !etfModal) return;
      destroyEtfChart();
      currentEtfCode = String(it.code);
      const basePrefix = document.body.getAttribute("data-base-prefix") || "";
      const klineSym = "etf_" + it.code;
      const isStar = WatchlistStore.has(it.code) || WatchlistStore.has(klineSym);
      if (etfModalTitle) etfModalTitle.textContent = cleanEtfDisplayText(it.name) + " (" + it.code + ")";
      if (etfModalSub) {
        etfModalSub.textContent =
          "跟踪指数：" + it.tracking_index + " ｜ 规模：" + it.aum + " ｜ 年费率：" + it.fee_total_pct;
      }
      if (etfModalBadges) {
        const modalOrtho = buildEtfOrthoTag(it);
        etfModalBadges.innerHTML =
          '<span class="mkt-badge mkt-' + escHtml(it.market) + '">' + escHtml(it.market_label) + "</span>" +
          '<span class="etf-chan-tag">' + escHtml(it.channel) + "</span>" +
          modalOrtho +
          '<span class="prem-pill prem-' + escHtml(it.premium_status) + '">' + escHtml(PREM_LABELS[it.premium_status] || it.premium_status) + "</span>" +
          '<span class="role-pill ' + etfRoleClass(it) + '">' + escHtml(it.action_role) + "</span>" +
          '<button type="button" class="star-btn' + (isStar ? " active" : "") + '" data-watch-toggle="1" data-watch-kind="etf" ' +
          'data-watch-id="' + escHtml(it.code) + '" data-watch-kline="' + escHtml(klineSym) + '" ' +
          'data-watch-code="' + escHtml(it.code) + '" data-watch-name="' + escHtml(cleanEtfDisplayText(it.name)) + '" aria-label="切换自选">' +
          (isStar ? "★" : "☆") + "</button>";
      }
      const startTab = initialTab === "kline" ? "kline" : "detail";
      currentEtfTab = startTab;
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
        const detailGridHtml =
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

        etfModalBody.innerHTML =
          '<div class="modal-tab-bar">' +
          '<div class="modal-tab-group" role="tablist" style="display:flex;gap:6px;flex-wrap:wrap;">' +
          '<button type="button" role="tab" aria-selected="' + (startTab === "detail" ? "true" : "false") + '" class="modal-tab-btn' + (startTab === "detail" ? " active" : "") + '" data-etf-modal-tab="detail">📋 详情与税费</button>' +
          '<button type="button" role="tab" aria-selected="' + (startTab === "kline" ? "true" : "false") + '" class="modal-tab-btn' + (startTab === "kline" ? " active" : "") + '" data-etf-modal-tab="kline">📈 互动 K 线与技术指标</button>' +
          "</div>" +
          '<a class="btn btn-sm modal-tab-ext" href="' + escHtml(basePrefix + "charts.html#sym=" + encodeURIComponent(klineSym)) + '">全屏终端 ↗</a>' +
          "</div>" +
          '<div class="modal-tab-pane" data-etf-modal-pane="detail"' + (startTab === "kline" ? " hidden" : "") + ">" + detailGridHtml + "</div>" +
          '<div class="modal-tab-pane" data-etf-modal-pane="kline"' + (startTab !== "kline" ? " hidden" : "") + ">" +
          '<div class="kline-mount" id="etf-kline-mount"></div></div>';
        etfModalBody.scrollTop = 0;

        function mountEtfKline() {
          const mountEl = document.getElementById("etf-kline-mount");
          if (!mountEl || !window.GIRKline) return;
          if (!activeEtfChart) {
            activeEtfChart = window.GIRKline.mount(mountEl, {
              symbolId: klineSym,
              height: 310,
              mode: "modal",
              goldLocked: !!it.gold_locked,
            });
          } else {
            activeEtfChart.resize();
          }
        }

        etfModalBody.querySelectorAll("[data-etf-modal-tab]").forEach(function (tBtn) {
          tBtn.addEventListener("click", function () {
            const target = tBtn.getAttribute("data-etf-modal-tab");
            currentEtfTab = target === "kline" ? "kline" : "detail";
            etfModalBody.querySelectorAll("[data-etf-modal-tab]").forEach(function (b) {
              const isAct = b === tBtn;
              b.classList.toggle("active", isAct);
              b.setAttribute("aria-selected", isAct ? "true" : "false");
            });
            etfModalBody.querySelectorAll("[data-etf-modal-pane]").forEach(function (p) {
              p.hidden = p.getAttribute("data-etf-modal-pane") !== target;
            });
            if (target === "kline") {
              window.requestAnimationFrame(mountEtfKline);
            }
          });
        });
        if (startTab === "kline") {
          window.requestAnimationFrame(mountEtfKline);
        }
      }
      etfModal._girStep = stepEtf;
      etfModal._girClose = function () { destroyEtfChart(); hideDialog(etfModal); };
      syncEtfStepButtons();
      if (etfModalBadges) etfModalBadges.scrollLeft = 0;
      if (!keepOpen || !etfModal.classList.contains("open")) {
        const closeBtn = etfModal.querySelector("[data-action='close-etf']");
        showDialog(etfModal, closeBtn);
      }
    }

    if (etfModal && !etfModal.dataset.boundClose) {
      etfModal.dataset.boundClose = "1";
      document.querySelectorAll("[data-action='close-etf']").forEach(function (b) {
        b.addEventListener("click", function () {
          if (typeof etfModal._girClose === "function") etfModal._girClose();
          else hideDialog(etfModal);
        });
      });
      etfModal.addEventListener("click", function (e) {
        const stepBtn = e.target.closest("[data-drawer-step]");
        if (stepBtn && !stepBtn.disabled) {
          e.preventDefault();
          const delta = parseInt(stepBtn.getAttribute("data-drawer-step") || "0", 10);
          if (delta && typeof etfModal._girStep === "function") etfModal._girStep(delta);
          return;
        }
        if (e.target === etfModal) {
          if (typeof etfModal._girClose === "function") etfModal._girClose();
          else hideDialog(etfModal);
        }
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
          if (btn) {
            openChEtfModal(btn.getAttribute("data-etf-code"), btn.getAttribute("data-open-tab") || "detail");
            return;
          }
          if (!e.target.closest("button, a, input, select, label, .star-btn")) {
            if (window.getSelection && String(window.getSelection()).trim()) return;
            const tr = e.target.closest("tbody tr");
            const rowBtn = tr ? tr.querySelector("[data-etf-code]") : null;
            if (rowBtn) {
              openChEtfModal(rowBtn.getAttribute("data-etf-code"), "detail");
            }
          }
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

    let currentFilteredEtfs = allEtfs.slice();
    let etfPager = null;
    const openEtfModal = createEtfModalController(
      allEtfs,
      function () { return currentFilteredEtfs; },
      function (nextIdx) { if (etfPager) etfPager.goToIndex(nextIdx); }
    );
    const etfState = {
      q: "",
      market: "all",
      assetClass: "all",
      region: "all",
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
    etfPager = createPaginator({
      barId: "etf-pg-bar",
      tbodyEl: etfTbody,
      cardsEl: etfCardsEl,
      cardSelector: ".etf-mcard, .etf-card",
      scrollTargetEl: document.querySelector(".screener-bar") || etfCount,
      onPageChange: function () {
        if (etfCount) {
          etfCount.textContent = etfPager.formatCount(currentFilteredEtfs.length, allEtfs.length, "只重点 ETF");
        }
      },
    });
    const etfStatOrthoTiles = Array.from(document.querySelectorAll("[data-etf-stat-ortho]"));
    const etfStatTiles = Array.from(document.querySelectorAll("[data-etf-stat-market]"));
    const etfMktBtns = Array.from(document.querySelectorAll("[data-etf-market]"));
    const etfAssetClassBtns = Array.from(document.querySelectorAll("[data-etf-asset-class]"));
    const etfRegionBtns = Array.from(document.querySelectorAll("[data-etf-region]"));
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
      if (p === "qdii") return it.channel === "境内QDII";
      if (p === "low-fee") return isFiniteNum(it.fee_num) && it.fee_num <= 0.20;
      if (p === "cash-shield") return String(it.action_role || "").indexOf("现金盾") !== -1 || it.asset_class === "cash_mmf";
      if (p === "base") return !it.gold_locked && String(it.action_role || "").indexOf("底座") !== -1;
      if (p === "high-risk") return it.premium_status === "high_risk" || String(it.action_role || "").indexOf("高危") !== -1;
      if (p === "hide-gold") return !it.gold_locked;
      if (p === "watchlist") return WatchlistStore.has(it.code) || WatchlistStore.has("etf_" + it.code);
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
      if (etfState.assetClass !== "all") params.push("asset_class=" + encodeURIComponent(etfState.assetClass));
      if (etfState.region !== "all") params.push("region=" + encodeURIComponent(etfState.region));
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
      etfState.assetClass = "all";
      etfState.region = "all";
      etfState.channel = "all";
      etfState.preset = "all";
      etfState.sortKey = "default";
      etfState.sortDir = 1;
      if (etfSearch) etfSearch.value = "";
      renderEtfs(true);
    }

    function renderEtfs(syncHash, keepPage) {
      if (!keepPage) etfPager.reset();
      if (syncHash !== false) syncEtfUrlHash();

      etfMktBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-etf-market") || "all") === etfState.market);
      });
      const activeCompositeAc = ETF_COMPOSITE_ASSET_CLASSES[etfState.assetClass] || null;
      const hasCompositeAcBtn = !!(
        activeCompositeAc &&
        etfAssetClassBtns.some(function (x) {
          return x.getAttribute("data-etf-asset-class") === etfState.assetClass;
        })
      );
      etfAssetClassBtns.forEach(function (b) {
        const val = b.getAttribute("data-etf-asset-class") || "all";
        const isAct =
          val === etfState.assetClass ||
          (!!activeCompositeAc && !hasCompositeAcBtn && activeCompositeAc.indexOf(val) !== -1);
        b.classList.toggle("active", isAct);
      });
      etfRegionBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-etf-region") || "all") === etfState.region);
      });
      etfStatOrthoTiles.forEach(function (t) {
        const so = t.getAttribute("data-etf-stat-ortho") || "all";
        let isAct = false;
        if (so === "all") {
          isAct =
            etfState.market === "all" &&
            etfState.assetClass === "all" &&
            etfState.region === "all" &&
            etfState.channel === "all" &&
            etfState.preset === "all";
        } else if (so === "qdii") {
          isAct = etfState.channel === "境内QDII";
        } else {
          isAct = etfState.assetClass === so;
        }
        t.classList.toggle("active", isAct);
        t.setAttribute("aria-pressed", isAct ? "true" : "false");
      });
      etfStatTiles.forEach(function (t) {
        const sm = t.getAttribute("data-etf-stat-market") || "all";
        const isAct =
          (sm === etfState.market ||
            (sm === "us-global" && (etfState.market === "us-global" || etfState.market === "us-stock" || etfState.market === "global"))) &&
          (sm !== "all" || (etfState.preset === "all" && etfState.assetClass === "all" && etfState.region === "all" && etfState.channel === "all"));
        t.classList.toggle("active", isAct);
        t.setAttribute("aria-pressed", isAct ? "true" : "false");
      });
      etfChanBtns.forEach(function (b) {
        b.classList.toggle("active", (b.getAttribute("data-etf-channel") || "all") === etfState.channel);
      });
      etfPresetBtns.forEach(function (b) {
        const p = b.getAttribute("data-etf-preset") || "all";
        let isAct = false;
        if (p === "qdii") {
          isAct = etfState.channel === "境内QDII";
        } else if (p === "all") {
          isAct = etfState.preset === "all" && etfState.channel !== "境内QDII";
        } else {
          isAct = etfState.preset === p;
        }
        b.classList.toggle("active", isAct);
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
        if (etfState.assetClass !== "all") {
          if (activeCompositeAc) {
            if (activeCompositeAc.indexOf(it.asset_class) === -1) return false;
          } else if (it.asset_class !== etfState.assetClass) {
            return false;
          }
        }
        if (etfState.region !== "all") {
          if (etfState.region === "non_us") {
            if (["jp", "eu", "apac_em", "global"].indexOf(it.region) === -1) return false;
          } else if (it.region !== etfState.region) {
            return false;
          }
        }
        if (etfState.channel !== "all" && it.channel !== etfState.channel) return false;
        if (!matchesEtfPreset(it, etfState.preset)) return false;
        if (tokens.length > 0) {
          const acTxt = it.asset_class ? (ETF_ASSET_CLASS_LABELS[it.asset_class] || it.asset_class) : "";
          const rgTxt = it.region ? (ETF_REGION_LABELS[it.region] || it.region) : "";
          const hay = (
            it.code + " " + it.name + " " + it.market_label + " " + it.channel + " " +
            it.category + " " + acTxt + " " + rgTxt + " " + it.tracking_index + " " + it.top_holdings + " " +
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
      currentFilteredEtfs = rows;
      syncEtfSortHeaders();

      const etfPgBounds = etfPager.getBounds(rows.length);
      if (etfCount) {
        etfCount.textContent = etfPager.formatCount(rows.length, allEtfs.length, "只重点 ETF");
      }
      const etfQdiiPanel = document.getElementById("etf-qdii-panel");
      if (etfQdiiPanel) {
        etfQdiiPanel.classList.toggle("qdii-panel-highlight", etfState.channel === "境内QDII" || etfState.preset === "qdii");
      }

      if (etfTbody) {
        if (rows.length === 0) {
          etfTbody.innerHTML =
            '<tr><td colspan="7"><div class="empty-state">' +
            '<div class="empty-title">未找到匹配的 ETF</div>' +
            '<div class="empty-sub">尝试清空搜索词或切换资产大类、区域与通道</div>' +
            '<button type="button" class="btn btn-sm" data-action="etf-reset-all">清空所有筛选条件</button>' +
            "</div></td></tr>";
        } else {
          etfTbody.innerHTML = rows.map(function (it, idx) {
            const pgCls = idx < etfPgBounds.start || idx >= etfPgBounds.end ? " pg-hidden" : "";
            const dispName = cleanEtfDisplayText(it.name);
            const dispCat = cleanEtfDisplayText(it.category);
            const kSym = "etf_" + it.code;
            const isStar = WatchlistStore.has(it.code) || WatchlistStore.has(kSym);
            const orthoTag = buildEtfOrthoTag(it);
            const starBtn =
              '<button type="button" class="star-btn' + (isStar ? " active" : "") + '" data-watch-toggle="1" data-watch-kind="etf" ' +
              'data-watch-id="' + escHtml(it.code) + '" data-watch-kline="' + escHtml(kSym) + '" ' +
              'data-watch-code="' + escHtml(it.code) + '" data-watch-name="' + escHtml(dispName) + '" aria-label="切换自选">' +
              (isStar ? "★" : "☆") + "</button>";
            return (
              "<tr" + (pgCls ? ' class="pg-hidden"' : "") + ">" +
              '<td><div>' + starBtn + ' <strong>' + escHtml(dispName) + '</strong></div><div><span class="code-tag">' + escHtml(it.code) + '</span> <span class="etf-chan-tag">' + escHtml(dispCat) + "</span></div></td>" +
              '<td><div><span class="mkt-badge mkt-' + escHtml(it.market) + '">' + escHtml(it.market_label) + '</span></div><div><span class="etf-chan-tag">' + escHtml(it.channel) + "</span>" + (orthoTag ? " " + orthoTag : "") + "</div></td>" +
              "<td><div>" + escHtml(it.tracking_index) + '</div><div class="sec-sub">' + escHtml(it.yield_or_pe) + "</div></td>" +
              '<td class="col-num"><strong>' + escHtml(it.fee_total_pct) + "</strong></td>" +
              "<td><div><strong>" + escHtml(it.aum) + '</strong></div><div class="sec-sub">' + escHtml(it.liquidity) + "</div></td>" +
              '<td><div><span class="prem-pill prem-' + escHtml(it.premium_status) + '">' + escHtml(PREM_LABELS[it.premium_status] || it.premium_status) + '</span></div><div class="sec-sub">' + escHtml(it.premium_note) + "</div></td>" +
              '<td><div><span class="role-pill ' + etfRoleClass(it) + '">' + escHtml(it.action_role) + '</span></div><div style="margin-top:5px;display:flex;gap:5px;flex-wrap:wrap;"><button type="button" class="dossier-btn" style="margin-left:0;" data-etf-code="' + escHtml(it.code) + '">深度拆解</button><button type="button" class="kline-quick-btn" data-etf-code="' + escHtml(it.code) + '" data-open-tab="kline">📈 K线</button></div></td>' +
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
            '<div class="empty-sub">尝试清空搜索词或切换资产大类、区域与通道</div>' +
            '<button type="button" class="btn btn-sm" data-action="etf-reset-all">清空所有筛选条件</button>' +
            "</div>";
        } else {
          etfCardsEl.innerHTML = rows.map(function (it, idx) {
            const pgCls = idx < etfPgBounds.start || idx >= etfPgBounds.end ? " pg-hidden" : "";
            const dispName = cleanEtfDisplayText(it.name);
            const kSym = "etf_" + it.code;
            const isStar = WatchlistStore.has(it.code) || WatchlistStore.has(kSym);
            const orthoTag = buildEtfOrthoTag(it);
            const starBtn =
              '<button type="button" class="star-btn' + (isStar ? " active" : "") + '" data-watch-toggle="1" data-watch-kind="etf" ' +
              'data-watch-id="' + escHtml(it.code) + '" data-watch-kline="' + escHtml(kSym) + '" ' +
              'data-watch-code="' + escHtml(it.code) + '" data-watch-name="' + escHtml(dispName) + '" aria-label="切换自选">' +
              (isStar ? "★" : "☆") + "</button>";
            return (
              '<div class="etf-card etf-mcard' + pgCls + '">' +
              '<div class="etf-card-top">' +
              '<div class="etf-card-head-row">' + starBtn + ' <span class="mkt-badge mkt-' + escHtml(it.market) + '">' + escHtml(it.market_label) + "</span></div>" +
              '<span class="role-pill ' + etfRoleClass(it) + '">' + escHtml(it.action_role) + "</span>" +
              "</div>" +
              '<div class="etf-card-title-row"><strong>' + escHtml(dispName) + '</strong> <span class="code-tag">' + escHtml(it.code) + "</span></div>" +
              '<div class="etf-card-meta"><span><strong>通道：</strong>' + escHtml(it.channel) + "</span><span><strong>费率：</strong>" + escHtml(it.fee_total_pct) + "</span><span><strong>规模：</strong>" + escHtml(it.aum) + "</span>" + orthoTag + "</div>" +
              '<div><span class="prem-pill prem-' + escHtml(it.premium_status) + '">' + escHtml(PREM_LABELS[it.premium_status] || it.premium_status) + '</span> <span class="sec-sub">' + escHtml(it.yield_or_pe) + "</span></div>" +
              '<div class="sc-summary">' + escHtml(it.thesis_deep) + "</div>" +
              '<div style="display:flex;gap:6px;flex-wrap:wrap;"><button type="button" class="dossier-btn" style="margin-left:0;" data-etf-code="' + escHtml(it.code) + '">ETF 7 维拆解</button><button type="button" class="kline-quick-btn" data-etf-code="' + escHtml(it.code) + '" data-open-tab="kline">📈 K线</button></div>' +
              "</div>"
            );
          }).join("");
        }
      }
      etfPager.renderBar(rows.length);
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
    etfStatOrthoTiles.forEach(function (tile) {
      function handleOrthoStatSelect() {
        const so = tile.getAttribute("data-etf-stat-ortho") || "all";
        etfState.market = "all";
        if (so === "all") {
          etfState.assetClass = "all";
          etfState.region = "all";
          etfState.channel = "all";
          etfState.preset = "all";
        } else if (so === "qdii") {
          const alreadyOnlyQdii =
            etfState.channel === "境内QDII" &&
            etfState.assetClass === "all" &&
            etfState.region === "all";
          etfState.channel = alreadyOnlyQdii ? "all" : "境内QDII";
          etfState.assetClass = "all";
          etfState.region = "all";
          if (etfState.preset === "qdii") etfState.preset = "all";
        } else {
          const alreadySame = etfState.assetClass === so && etfState.channel === "all";
          etfState.assetClass = alreadySame ? "all" : so;
          etfState.channel = "all";
          etfState.region = "all";
          if (etfState.preset === "qdii") etfState.preset = "all";
        }
        renderEtfs(true);
      }
      tile.addEventListener("click", handleOrthoStatSelect);
      tile.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleOrthoStatSelect();
        }
      });
    });
    etfStatTiles.forEach(function (tile) {
      function handleStatSelect() {
        const sm = tile.getAttribute("data-etf-stat-market") || "all";
        etfState.market = sm !== "all" && etfState.market === sm ? "all" : sm;
        etfState.assetClass = "all";
        etfState.region = "all";
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
        etfState.assetClass = "all";
        etfState.region = "all";
        renderEtfs(true);
      });
    });
    etfAssetClassBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        const ac = b.getAttribute("data-etf-asset-class") || "all";
        etfState.assetClass = etfState.assetClass === ac && ac !== "all" ? "all" : ac;
        etfState.market = "all";
        renderEtfs(true);
      });
    });
    etfRegionBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        const rg = b.getAttribute("data-etf-region") || "all";
        etfState.region = etfState.region === rg && rg !== "all" ? "all" : rg;
        etfState.market = "all";
        renderEtfs(true);
      });
    });
    etfChanBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        etfState.channel = b.getAttribute("data-etf-channel") || "all";
        if (etfState.preset === "qdii") etfState.preset = "all";
        renderEtfs(true);
      });
    });
    etfPresetBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        const p = b.getAttribute("data-etf-preset") || "all";
        if (p === "qdii") {
          etfState.channel = etfState.channel === "境内QDII" ? "all" : "境内QDII";
          if (etfState.preset === "qdii") etfState.preset = "all";
        } else if (p === "all") {
          etfState.preset = "all";
          if (etfState.channel === "境内QDII") etfState.channel = "all";
        } else {
          etfState.preset = etfState.preset === p ? "all" : p;
        }
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
        if (btn) {
          openEtfModal(btn.getAttribute("data-etf-code"), btn.getAttribute("data-open-tab") || "detail");
          return;
        }
        if (container === etfTbody && !e.target.closest("button, a, input, select, label, .star-btn")) {
          if (window.getSelection && String(window.getSelection()).trim()) return;
          const tr = e.target.closest("tr");
          const rowBtn = tr ? tr.querySelector("[data-etf-code]") : null;
          if (rowBtn) {
            openEtfModal(rowBtn.getAttribute("data-etf-code"), "detail");
          }
        }
      });
    });

    function applyEtfHash() {
      etfState.q = "";
      etfState.market = "all";
      etfState.assetClass = "all";
      etfState.region = "all";
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
        } else if (k === "asset_class" && VALID_ETF_ASSET_CLASSES.indexOf(v) !== -1) {
          etfState.assetClass = v;
        } else if (k === "region" && VALID_ETF_REGIONS.indexOf(v) !== -1) {
          etfState.region = v;
        } else if (k === "channel" && v) {
          etfState.channel = v;
        } else if (k === "preset" && VALID_ETF_PRESETS.indexOf(v) !== -1) {
          if (v === "qdii") {
            etfState.channel = "境内QDII";
          } else {
            etfState.preset = v;
          }
        } else if (k === "q") {
          etfState.q = v;
        }
      });
      if (etfSearch) etfSearch.value = etfState.q;
      const etfAdvPanel = (etfSearch && etfSearch.closest(".filter-panel")) || document.querySelector(".filter-panel");
      if (etfAdvPanel) {
        const advTray = etfAdvPanel.querySelector(".filter-adv-tray");
        if (advTray) {
          const hasAdvHash =
            etfState.assetClass !== "all" ||
            etfState.region !== "all" ||
            etfState.channel !== "all" ||
            (etfState.market !== "all" && !!advTray.querySelector("[data-etf-market]"));
          if (hasAdvHash) setAdvFilterTrayOpen(etfAdvPanel, true);
        }
      }
    }

    if (allEtfs.length > 0) {
      applyEtfHash();
      renderEtfs(false);
      root.classList.add("etf-enhanced");
      window.addEventListener("gir:watchlist-change", function () {
        if (etfState.preset === "watchlist") renderEtfs(false, true);
      });
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
    const gMoreBtn = document.getElementById("guide-term-more-btn");
    const gCatBtns = Array.from(document.querySelectorAll("[data-guide-cat]"));
    const gState = { cat: "all", q: "" };
    let gMoreExpanded = !gMoreBtn;
    let gTimer = 0;

    gCards.forEach(function (card) {
      if (card.classList.contains("guide-term-hidden")) {
        card.dataset.guideInitFold = "1";
      }
    });

    function revealAllGuideCards() {
      gMoreExpanded = true;
      gCards.forEach(function (card) {
        card.classList.remove("guide-term-hidden");
      });
      if (gMoreBtn) {
        gMoreBtn.hidden = true;
        gMoreBtn.style.display = "none";
      }
    }

    function ensureGuideSearchVisible() {
      if (!gSearch) return;
      const panel = gSearch.closest(".filter-panel") || gSearch;
      const rect = panel.getBoundingClientRect();
      const stickyOff = getStickyOffset();
      if (rect.top < stickyOff || rect.bottom > window.innerHeight - 140) {
        const top = window.scrollY + rect.top - stickyOff;
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
      const isFiltered = gState.cat !== "all" || tokens.length > 0;
      let shown = 0;
      let hasFolded = false;
      gCards.forEach(function (card) {
        const cat = card.getAttribute("data-guide-term-cat") || "";
        const hay = (card.getAttribute("data-guide-term-search") || card.textContent || "").toLowerCase();
        const okCat = gState.cat === "all" || cat === gState.cat;
        const okQ = tokens.length === 0 || tokens.every(function (tk) { return hay.indexOf(tk) !== -1; });
        const ok = okCat && okQ;
        const folded = !isFiltered && !gMoreExpanded && card.dataset.guideInitFold === "1";
        card.classList.toggle("guide-term-hidden", folded);
        card.style.display = ok && !folded ? "" : "none";
        if (folded) hasFolded = true;
        if (ok) shown++;
      });
      if (gMoreBtn) {
        const hideMore = gMoreExpanded || isFiltered || !hasFolded;
        gMoreBtn.hidden = hideMore;
        gMoreBtn.style.display = hideMore ? "none" : "";
        const wrap = gMoreBtn.closest(".guide-term-more-wrap");
        if (wrap) {
          wrap.hidden = hideMore;
          wrap.style.display = hideMore ? "none" : "";
        }
      }
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

    if (gMoreBtn) {
      gMoreBtn.addEventListener("click", function () {
        revealAllGuideCards();
        applyGuideFilter(false);
      });
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
    function applyGuideHash() {
      const raw = (window.location.hash || "").replace(/^#/, "").trim();
      if (/^term-/i.test(raw)) {
        revealAllGuideCards();
        return false;
      }
      if (!raw || raw.indexOf("=") === -1) return false;
      let matched = false;
      raw.split("&").forEach(function (pair) {
        const eq = pair.indexOf("=");
        if (eq <= 0) return;
        const k = safeDecode(pair.slice(0, eq));
        const v = safeDecode(pair.slice(eq + 1));
        if (k === "q") {
          gState.q = v;
          if (gSearch) gSearch.value = v;
          matched = true;
        } else if (k === "cat" && v) {
          gState.cat = v;
          matched = true;
        }
      });
      return matched;
    }

    function scrollToGuideTermHash() {
      const raw = (window.location.hash || "").replace(/^#/, "").trim();
      if (!/^term-/i.test(raw)) return;
      const target = document.getElementById(raw);
      if (target) {
        window.requestAnimationFrame(function () {
          if (typeof target.scrollIntoView === "function") {
            target.scrollIntoView({ behavior: prefersReducedMotion ? "auto" : "smooth", block: "center" });
          } else {
            const top = target.getBoundingClientRect().top + window.scrollY - getStickyOffset();
            window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
          }
        });
      }
    }

    const hadGuideHash = applyGuideHash();
    applyGuideFilter(hadGuideHash);
    scrollToGuideTermHash();
    window.addEventListener("hashchange", function () {
      if (applyGuideHash()) {
        applyGuideFilter(true);
      } else if (/^#term-/i.test(window.location.hash || "")) {
        revealAllGuideCards();
        applyGuideFilter(false);
        scrollToGuideTermHash();
      }
    });
  }

  /* ------------------------------------------------------------------------
     16. Interactive Personal Wallet Calculator (`#wallet-calc-data`)
     ------------------------------------------------------------------------ */
  const walletDataEl = document.getElementById("wallet-calc-data");
  const walletBox = document.querySelector("[data-wallet-calc]");
  if (walletDataEl && walletBox) {
    let wCfg = { gold_new_buy_allowed: false, eq_cap_pct: 35, gold_cap_pct: 10 };
    try {
      const parsed = JSON.parse(walletDataEl.textContent || "{}");
      if (parsed && typeof parsed === "object") wCfg = Object.assign(wCfg, parsed);
    } catch (_) {}

    const amountInput = walletBox.querySelector("[data-wcalc-amount]");
    const presetBtns = Array.from(walletBox.querySelectorAll("[data-wcalc-preset]"));
    const profileBtns = Array.from(walletBox.querySelectorAll("[data-wcalc-profile]"));
    const outBucketsEl = walletBox.querySelector("[data-wcalc-buckets]");
    const outRulesEl = walletBox.querySelector("[data-wcalc-rules]");
    const copyBtn = walletBox.querySelector("[data-wcalc-copy]");

    let curWan = 10;
    let curProfile = "balanced"; // conservative | balanced | aggressive
    try {
      const saved = JSON.parse(localStorage.getItem("gir_wallet_calc") || "null");
      if (saved && isFiniteNum(saved.wan) && saved.wan > 0) curWan = saved.wan;
      if (saved && ["conservative", "balanced", "aggressive"].indexOf(saved.profile) !== -1) curProfile = saved.profile;
    } catch (_) {}
    if (amountInput) amountInput.value = String(curWan);

    const PROFILES = {
      conservative: { label: "保守稳健", liquid: 25, stable: 50, equity: 18, multi: 7, goldSlot: 5 },
      balanced: { label: "均衡成长", liquid: 20, stable: 40, equity: 30, multi: 10, goldSlot: 8 },
      aggressive: { label: "积极进取", liquid: 15, stable: 28, equity: 42, multi: 15, goldSlot: 10 },
    };

    function fmtRmb(v) {
      return "¥" + Math.round(v).toLocaleString("en-US");
    }

    function computeWalletPlan() {
      const total = Math.max(1000, Math.round(curWan * 10000));
      const prof = PROFILES[curProfile] || PROFILES.balanced;
      const goldAllowed = !!wCfg.gold_new_buy_allowed;
      const eqCap = isFiniteNum(wCfg.eq_cap_pct) ? Math.max(15, Math.min(60, wCfg.eq_cap_pct)) : 35;

      // Respect live market equity cap: trim aggressive equity if market is red-light capped
      let eqPct = Math.min(prof.equity, eqCap);
      let overflowEq = prof.equity - eqPct;
      let liqPct = prof.liquid;
      let stabPct = prof.stable + overflowEq;
      let multiPct = prof.multi;
      const goldCap = isFiniteNum(wCfg.gold_cap_pct) ? Math.max(0, Math.min(15, wCfg.gold_cap_pct)) : 10;
      let goldPct = goldAllowed ? Math.min(prof.goldSlot, goldCap) : 0;

      if (goldAllowed) {
        stabPct = Math.max(10, stabPct - goldPct);
      }
      const sumPct = liqPct + stabPct + eqPct + multiPct + goldPct;
      if (sumPct !== 100) stabPct += 100 - sumPct;

      const liqAmt = Math.round((total * liqPct) / 100);
      const eqAmt = Math.round((total * eqPct) / 100);
      const multiAmt = Math.round((total * multiPct) / 100);
      const stabAmt = goldAllowed
        ? Math.round((total * stabPct) / 100)
        : total - (liqAmt + eqAmt + multiAmt);
      const goldAmt = goldAllowed ? total - liqAmt - stabAmt - eqAmt - multiAmt : 0;
      const singleStockCap = Math.round(total * 0.08);
      const cashPlusStable = liqAmt + stabAmt;

      const liqVehicle = liqAmt < 12000
        ? "货币基金 / 周四国债逆回购（1 元起投；活钱低于 1.2 万暂不配 511360）"
        : "短融 ETF（511360，约 1.14 万/手）+ 周四国债逆回购 + 货基";
      const stabVehicle = cashPlusStable > 500000
        ? "储蓄国债 / 政金债 ETF / 拆存 " + Math.ceil(cashPlusStable / 470000) + " 家银行存款（单行 ≤47万）"
        : "储蓄国债 / 债券 ETF（511260/511010）/ 单行 50 万内存款";
      const eqVehicle = singleStockCap < 15000
        ? "红利/宽基低费 ETF（510300 / 563360 / 515180，规避单股碎股摩擦）"
        : "红利低波 + 沪深300/A500 核心宽基 + 防弹衣龙头（单股严控 ≤" + fmtRmb(singleStockCap) + "）";
      const multiVehicle = "投资级转债 ETF（511180）/ 锁汇香港互认债基 / 场外低溢价 QDII 定投";

      return {
        total: total,
        prof: prof,
        goldAllowed: goldAllowed,
        liqPct: liqPct, stabPct: stabPct, eqPct: eqPct, multiPct: multiPct, goldPct: goldPct,
        liqAmt: liqAmt, stabAmt: stabAmt, eqAmt: eqAmt, multiAmt: multiAmt, goldAmt: goldAmt,
        singleStockCap: singleStockCap,
        cashPlusStable: cashPlusStable,
        liqVehicle: liqVehicle,
        stabVehicle: stabVehicle,
        eqVehicle: eqVehicle,
        multiVehicle: multiVehicle,
      };
    }

    function renderWallet() {
      presetBtns.forEach(function (b) {
        b.classList.toggle("active", Number(b.getAttribute("data-wcalc-preset")) === curWan);
      });
      profileBtns.forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-wcalc-profile") === curProfile);
      });
      try {
        localStorage.setItem("gir_wallet_calc", JSON.stringify({ wan: curWan, profile: curProfile }));
      } catch (_) {}

      const p = computeWalletPlan();
      if (outBucketsEl) {
        const cards = [
          { icon: "💧", name: "活钱应急", pct: p.liqPct, amt: p.liqAmt, tip: p.liqVehicle, cls: "wb-liquid" },
          { icon: "🛡️", name: "稳健压舱", pct: p.stabPct, amt: p.stabAmt, tip: p.stabVehicle, cls: "wb-stable" },
          { icon: "🌱", name: "权益定投", pct: p.eqPct, amt: p.eqAmt, tip: p.eqVehicle, cls: "wb-equity" },
          { icon: "🌐", name: "跨境与多元", pct: p.multiPct, amt: p.multiAmt, tip: p.multiVehicle, cls: "wb-multi" },
        ];
        if (p.goldAllowed) {
          cards.push({
            icon: "🥇",
            name: "黄金分批",
            pct: p.goldPct,
            amt: p.goldAmt,
            tip: "按家庭总资产 10%–15% 封顶分批配置，不加杠杆",
            cls: "wb-gold",
          });
        } else {
          cards.push({
            icon: "🛑",
            name: "黄金新仓锁",
            pct: 0,
            amt: 0,
            tip: "0 元（红灯观察期不新买，原黄金预算暂泊活钱/短债）",
            cls: "wb-gold-lock",
          });
        }
        outBucketsEl.innerHTML = cards
          .map(function (c) {
            return (
              '<div class="wcalc-bucket ' + c.cls + '">' +
              '<div class="wcalc-b-top"><span>' + c.icon + " " + escHtml(c.name) + '</span><strong>' + c.pct + "%</strong></div>" +
              '<div class="wcalc-b-amt">' + (c.cls === "wb-gold-lock" ? "0 元（红灯锁）" : fmtRmb(c.amt)) + "</div>" +
              '<div class="wcalc-b-tip">' + escHtml(c.tip) + "</div>" +
              "</div>"
            );
          })
          .join("");
      }

      if (outRulesEl) {
        const rules = [];
        if (!p.goldAllowed) {
          rules.push("🛑 黄金红灯观察锁：黄金新仓严格为 0 元（老持仓稳拿不乱割），原黄金预算已自动转泊活钱/短债池。");
        } else {
          rules.push("🥇 黄金上限纪律：任何情形下家庭黄金总占比严控 10%–15%，不加杠杆。");
        }
        if (p.liqAmt < 12000) {
          rules.push("💧 511360 门槛自动切换：当前活钱 " + fmtRmb(p.liqAmt) + " 低于 12,000 元（短融 ETF 100 份约 1.14 万元起步），已自动切换为 1 元起投的货币基金 / 1,000 元起投国债逆回购。");
        }
        if (p.cashPlusStable > 500000) {
          const banks = Math.ceil(p.cashPlusStable / 470000);
          rules.push("🏦 50 万存保分银行提醒：活钱 + 稳健合计 " + fmtRmb(p.cashPlusStable) + " 超过 50 万元，银行存款部分请拆分至至少 " + banks + " 家独立法人银行，单行本息严控 47 万元以内。");
        }
        rules.push("🎯 8% 单股上限红线：本次总资金单只个股最高严控 " + fmtRmb(p.singleStockCap) + "（绝不单吊押注" + (p.singleStockCap < 15000 ? "；资金体量优先使用低费率 ETF 分散" : "") + "）。");
        outRulesEl.innerHTML = rules.map(function (r) { return "<li>" + escHtml(r) + "</li>"; }).join("");
      }
    }

    presetBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        const v = Number(b.getAttribute("data-wcalc-preset"));
        if (isFiniteNum(v) && v > 0) {
          curWan = v;
          if (amountInput) amountInput.value = String(v);
          renderWallet();
        }
      });
    });
    profileBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        curProfile = b.getAttribute("data-wcalc-profile") || "balanced";
        renderWallet();
      });
    });
    if (amountInput) {
      amountInput.addEventListener("input", function () {
        const v = parseFloat(amountInput.value);
        if (isFiniteNum(v) && v >= 0.1 && v <= 10000) {
          curWan = v;
          renderWallet();
        }
      });
      amountInput.addEventListener("blur", function () {
        const raw = parseFloat(amountInput.value);
        const clamped = isFiniteNum(raw) ? Math.max(0.1, Math.min(10000, Math.round(raw * 100) / 100)) : curWan;
        curWan = Math.max(0.1, Math.min(10000, clamped));
        amountInput.value = String(curWan);
        renderWallet();
      });
    }
    if (copyBtn) {
      const origCopyLabel = copyBtn.textContent || "复制试算方案";
      let copyResetTimer = 0;
      function showCopyFeedback(ok) {
        window.clearTimeout(copyResetTimer);
        copyBtn.textContent = ok ? "已复制 ✓" : "复制失败，请手动选中";
        copyResetTimer = window.setTimeout(function () {
          copyBtn.textContent = origCopyLabel;
        }, 1800);
      }
      function fallbackCopyText(text) {
        try {
          const ta = document.createElement("textarea");
          ta.value = text;
          ta.setAttribute("readonly", "");
          ta.style.position = "fixed";
          ta.style.top = "-9999px";
          ta.style.left = "-9999px";
          ta.style.opacity = "0";
          document.body.appendChild(ta);
          ta.select();
          ta.setSelectionRange(0, text.length);
          const ok = !!(document.execCommand && document.execCommand("copy"));
          document.body.removeChild(ta);
          showCopyFeedback(ok);
        } catch (_) {
          showCopyFeedback(false);
        }
      }
      copyBtn.addEventListener("click", function () {
        const p = computeWalletPlan();
        const summary =
          "【全球投研 · 我的钱包试算（" + p.prof.label + " · 总计 " + fmtRmb(p.total) + "）】\n" +
          "1. 活钱应急 (" + p.liqPct + "%): " + fmtRmb(p.liqAmt) + "\n" +
          "2. 稳健压舱 (" + p.stabPct + "%): " + fmtRmb(p.stabAmt) + "\n" +
          "3. 权益定投 (" + p.eqPct + "%): " + fmtRmb(p.eqAmt) + "\n" +
          "4. 跨境与多元 (" + p.multiPct + "%): " + fmtRmb(p.multiAmt) + "\n" +
          "5. 黄金新仓: " + (p.goldAllowed ? fmtRmb(p.goldAmt) : "0 元（红灯观察期不新买）") + "\n" +
          "单股上限(8%): " + fmtRmb(p.singleStockCap);
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(summary).then(
            function () { showCopyFeedback(true); },
            function () { fallbackCopyText(summary); }
          );
        } else {
          fallbackCopyText(summary);
        }
      });
    }
    renderWallet();
  }

  /* ------------------------------------------------------------------------
     17. QDII On-Exchange Premium vs OTC Queue Breakeven Calculator
     ------------------------------------------------------------------------ */
  const qdiiCalc = document.querySelector("[data-qdii-calc]");
  if (qdiiCalc) {
    const premIn = qdiiCalc.querySelector("[data-qcalc-prem]");
    const amtIn = qdiiCalc.querySelector("[data-qcalc-amt]");
    const limIn = qdiiCalc.querySelector("[data-qcalc-lim]");
    const limPresets = Array.from(qdiiCalc.querySelectorAll("[data-qcalc-lim-preset]"));
    const outEl = qdiiCalc.querySelector("[data-qcalc-out]");

    function renderQdiiCalc() {
      const prem = Math.max(0, Math.min(80, parseFloat(premIn && premIn.value) || 0));
      const wan = Math.max(0.1, Math.min(5000, parseFloat(amtIn && amtIn.value) || 5));
      const dailyLim = Math.max(10, Math.min(1000000, parseFloat(limIn && limIn.value) || 1000));
      const totalRmb = Math.round(wan * 10000);
      const days = Math.ceil(totalRmb / dailyLim);
      const months = (days / 21).toFixed(1);
      const premCost = Math.round((totalRmb * prem) / (100 + prem));
      // Average capital enters midway through queue, so market must rally ~2x premium during queue to break even
      const breakevenRally = (prem * 2).toFixed(1);

      limPresets.forEach(function (b) {
        b.classList.toggle("active", Number(b.getAttribute("data-qcalc-lim-preset")) === dailyLim);
      });

      let verdictCls = "qcalc-ok";
      let verdictTxt = "溢价处于 1.5% 以内温和区间：可对比场内买卖价差与场外申购费，若急于一次性建仓成本可控。";
      if (prem > 3.0) {
        verdictCls = "qcalc-danger";
        verdictTxt = "高危溢价陷阱（> 3%）：场内硬买即刻多付 " + premCost.toLocaleString("en-US") + " 元溢价；除非底层在 " + days + " 个交易日内暴涨超 " + breakevenRally + "%，否则溢价回落将造成直接实亏！强烈建议改用官方直销 App 提高单日限额，或拆分多只同赛道场外联接按净值定投。";
      } else if (prem > 1.5) {
        verdictCls = "qcalc-warn";
        verdictTxt = "溢价偏高（1.5%–3.0%）：建议优先核查基金公司官方直销 App 是否给出更高限额（常为支付宝/三方的 5–10 倍），尽量按净值分批申购减少无谓磨损。";
      }

      if (outEl) {
        outEl.innerHTML =
          '<div class="qcalc-metrics">' +
          '<div class="qcalc-m"><div class="qcalc-m-lbl">场外排队所需交易日</div><div class="qcalc-m-val">' + days + ' 日（约 ' + months + ' 个月）</div></div>' +
          '<div class="qcalc-m"><div class="qcalc-m-lbl">场内硬追即刻溢价成本</div><div class="qcalc-m-val">¥' + premCost.toLocaleString("en-US") + '</div></div>' +
          '<div class="qcalc-m"><div class="qcalc-m-lbl">排队期打平需标的上涨</div><div class="qcalc-m-val">约 +' + breakevenRally + '%</div></div>' +
          "</div>" +
          '<div class="qcalc-verdict ' + verdictCls + '">' + escHtml(verdictTxt) + "</div>";
      }
    }

    [premIn, amtIn, limIn].forEach(function (inp) {
      if (inp) inp.addEventListener("input", renderQdiiCalc);
    });
    limPresets.forEach(function (b) {
      b.addEventListener("click", function () {
        const v = Number(b.getAttribute("data-qcalc-lim-preset"));
        if (limIn && isFiniteNum(v)) {
          limIn.value = String(v);
          renderQdiiCalc();
        }
      });
    });
    renderQdiiCalc();
  }

  /* ------------------------------------------------------------------------
     18. Core Policy & Upcoming 14–30d Financial Calendar (#sec-policy-calendar)
     ------------------------------------------------------------------------ */
  function initPolicyCalendar() {
    const sec = document.getElementById("sec-policy-calendar");
    if (!sec) return;
    const regionBtns = Array.from(sec.querySelectorAll(".pcal-filter-row [data-pcal-region]"));
    const tierBtn = sec.querySelector(".pcal-filter-row [data-pcal-tier]");
    const onlyMajorEl = document.getElementById("pcal-only-major");
    const isMajorCheckbox = !!(onlyMajorEl && onlyMajorEl.tagName === "INPUT" && onlyMajorEl.type === "checkbox");
    const isSameTierBtn = !!(tierBtn && onlyMajorEl && tierBtn === onlyMajorEl);
    const toggle30dBtn = document.getElementById("pcal-toggle-30d");
    const moreBtn = document.getElementById("pcal-more-btn");
    const items = Array.from(sec.querySelectorAll(".pcal-event-item"));
    const emptyEl = document.getElementById("pcal-empty");
    const countEl = document.getElementById("pcal-count-status");

    let activeRegion = "all";
    let onlyTopTier = isMajorCheckbox
      ? !!onlyMajorEl.checked
      : !!(
          (onlyMajorEl && (onlyMajorEl.classList.contains("active") || onlyMajorEl.getAttribute("aria-pressed") === "true")) ||
          (tierBtn && (tierBtn.classList.contains("active") || tierBtn.getAttribute("aria-pressed") === "true"))
        );
    let show30d = !toggle30dBtn || toggle30dBtn.getAttribute("data-expanded") === "1";
    let pcalMoreExpanded = false;

    function matchesRegion(itemReg, filterReg) {
      if (filterReg === "all") return true;
      const r = String(itemReg || "").trim().toUpperCase();
      if (filterReg === "GLOBAL_EX") {
        return r === "GLOBAL_EX" || r === "EU" || r === "JP" || r === "UK" || r === "GLOBAL" || (r !== "CN" && r !== "HK" && r !== "US");
      }
      return r === filterReg;
    }

    function applyFilter() {
      regionBtns.forEach(function (btn) {
        const isAct = (btn.getAttribute("data-pcal-region") || "all") === activeRegion;
        btn.classList.toggle("active", isAct);
        btn.setAttribute("aria-pressed", isAct ? "true" : "false");
      });
      if (tierBtn) {
        tierBtn.classList.toggle("active", onlyTopTier);
        tierBtn.setAttribute("aria-pressed", onlyTopTier ? "true" : "false");
      }
      if (onlyMajorEl && !isSameTierBtn) {
        if (isMajorCheckbox) {
          onlyMajorEl.checked = onlyTopTier;
        } else {
          onlyMajorEl.classList.toggle("active", onlyTopTier);
          onlyMajorEl.setAttribute("aria-pressed", onlyTopTier ? "true" : "false");
        }
      }

      const targetTier =
        (tierBtn && tierBtn.getAttribute("data-pcal-tier")) ||
        (onlyMajorEl && onlyMajorEl.getAttribute("data-pcal-tier")) ||
        "P0";
      const targetTierLow = String(targetTier).trim().toLowerCase();
      const isDefaultView = activeRegion === "all" && !onlyTopTier && (!toggle30dBtn || !show30d);
      let shown = 0;
      let totalVisBeforeFold = 0;
      let foldedCount = 0;
      let hidden30d = 0;

      items.forEach(function (el) {
        const reg = el.getAttribute("data-pcal-region") || "";
        const tier = el.getAttribute("data-pcal-tier") || "";
        const tierLow = tier.trim().toLowerCase();
        const horizon = el.getAttribute("data-pcal-horizon") || "14d";
        const okReg = matchesRegion(reg, activeRegion);
        const okTier =
          !onlyTopTier ||
          tier === targetTier ||
          (targetTierLow === "p0" && tierLow === "major") ||
          (targetTierLow === "major" && tierLow === "p0");
        const okBase = okReg && okTier;
        if (okBase && horizon === "30d" && !show30d) {
          hidden30d++;
        }
        const vis = okBase && (show30d || horizon !== "30d");
        let isFolded = false;
        if (vis) {
          totalVisBeforeFold++;
          if (moreBtn && isDefaultView && !pcalMoreExpanded && totalVisBeforeFold > 5) {
            isFolded = true;
            foldedCount++;
          }
        }
        el.classList.toggle("pcal-fold-hidden", isFolded);
        const finalVis = vis && !isFolded;
        el.hidden = !finalVis;
        el.style.display = finalVis ? "" : "none";
        if (finalVis) shown++;
      });

      if (moreBtn) {
        const hideMore = !isDefaultView || totalVisBeforeFold <= 5;
        const moreWrap = moreBtn.closest(".pcal-more-wrap");
        moreBtn.hidden = hideMore;
        moreBtn.style.display = hideMore ? "none" : "";
        if (moreWrap) {
          moreWrap.hidden = hideMore;
          moreWrap.style.display = hideMore ? "none" : "";
        }
        if (!hideMore) {
          moreBtn.setAttribute("aria-expanded", pcalMoreExpanded ? "true" : "false");
          moreBtn.textContent = pcalMoreExpanded
            ? "收起部分日程 ▴"
            : "展开其余 " + foldedCount + " 项近期日程 ▾";
        }
      }
      if (toggle30dBtn) {
        const hideToggle = !show30d && hidden30d === 0;
        toggle30dBtn.hidden = hideToggle;
        toggle30dBtn.style.display = hideToggle ? "none" : "";
        toggle30dBtn.setAttribute("data-expanded", show30d ? "1" : "0");
        toggle30dBtn.setAttribute("aria-expanded", show30d ? "true" : "false");
        if (show30d) {
          toggle30dBtn.textContent = "收起 15–30 天前瞻日程";
        } else if (hidden30d > 0) {
          toggle30dBtn.textContent = "展开 15–30 天前瞻日程（+" + hidden30d + " 项）";
        }
      }
      if (countEl) {
        countEl.textContent =
          "显示 " + shown + " / " + items.length + " 项日程" +
          (hidden30d > 0 ? "（另有 " + hidden30d + " 项 15–30 天）" : "");
      }
      if (emptyEl) {
        emptyEl.hidden = shown > 0;
        emptyEl.style.display = shown === 0 ? "" : "none";
        if (shown === 0) {
          emptyEl.textContent = hidden30d > 0
            ? "未来 14 天暂无匹配日程，15–30 天前瞻区有 " + hidden30d + " 项，可点击下方按钮展开。"
            : "当前筛选条件下暂无匹配日程，试试切换地区或取消「只看重磅」。";
        }
      }
    }

    if (moreBtn) {
      moreBtn.addEventListener("click", function () {
        pcalMoreExpanded = !pcalMoreExpanded;
        applyFilter();
      });
    }

    regionBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        activeRegion = btn.getAttribute("data-pcal-region") || "all";
        applyFilter();
      });
    });
    if (tierBtn) {
      tierBtn.addEventListener("click", function () {
        onlyTopTier = !onlyTopTier;
        applyFilter();
      });
    }
    if (onlyMajorEl && !isSameTierBtn) {
      if (isMajorCheckbox) {
        onlyMajorEl.addEventListener("change", function () {
          onlyTopTier = !!onlyMajorEl.checked;
          applyFilter();
        });
      } else {
        onlyMajorEl.addEventListener("click", function () {
          onlyTopTier = !onlyTopTier;
          applyFilter();
        });
      }
    }
    if (toggle30dBtn) {
      toggle30dBtn.addEventListener("click", function () {
        show30d = !show30d;
        applyFilter();
      });
    }
    applyFilter();
  }
  initPolicyCalendar();

  /* ------------------------------------------------------------------------
     19. Home Policy Briefs Region Filter & Single-Market Uncapped News Filter
     ------------------------------------------------------------------------ */
  function initPolicyBriefFilters() {
    const bar = document.getElementById("pcal-brief-filters");
    const grid = document.getElementById("pcal-briefs-row");
    if (!bar || !grid) return;
    const btns = Array.from(bar.querySelectorAll("[data-pcal-brief-filter]"));
    const cards = Array.from(grid.querySelectorAll(".pcal-brief-card"));
    let emptyHint = document.getElementById("pcal-brief-empty");
    if (!emptyHint) {
      emptyHint = document.createElement("p");
      emptyHint.id = "pcal-brief-empty";
      emptyHint.className = "pcal-empty";
      emptyHint.hidden = true;
      emptyHint.textContent = "当前地区筛选下暂无精选要闻，点击「精选全部」查看全部核心时政。";
      grid.insertAdjacentElement("afterend", emptyHint);
    }
    function apply(reg) {
      btns.forEach(function (b) {
        const act = (b.getAttribute("data-pcal-brief-filter") || "all") === reg;
        b.classList.toggle("active", act);
        b.setAttribute("aria-pressed", act ? "true" : "false");
      });
      let shown = 0;
      cards.forEach(function (c) {
        const cr = (c.getAttribute("data-pcal-brief-region") || "").toUpperCase();
        let ok = reg === "all";
        if (!ok && reg === "GLOBAL_EX") {
          ok = cr !== "CN" && cr !== "HK" && cr !== "US";
        } else if (!ok) {
          ok = cr === reg;
        }
        c.hidden = !ok;
        if (ok) shown += 1;
      });
      if (emptyHint) {
        emptyHint.hidden = shown > 0;
      }
    }
    btns.forEach(function (b) {
      b.addEventListener("click", function () {
        apply(b.getAttribute("data-pcal-brief-filter") || "all");
      });
    });
  }
  initPolicyBriefFilters();

  function initMarketNewsFilters() {
    const sec = document.getElementById("sec-market-news");
    if (!sec) return;
    const btns = Array.from(sec.querySelectorAll("[data-mnews-filter]"));
    const cards = Array.from(sec.querySelectorAll(".mnews-card"));
    const grid = sec.querySelector(".mnews-grid");
    const status = document.getElementById("mnews-count-status");
    let emptyHint = document.getElementById("mnews-empty");
    if (!emptyHint && grid) {
      emptyHint = document.createElement("p");
      emptyHint.id = "mnews-empty";
      emptyHint.className = "pcal-empty";
      emptyHint.hidden = true;
      emptyHint.textContent = "当前筛选条件下暂无匹配新闻，点击「全部」查看本市场全部重要动态。";
      grid.insertAdjacentElement("afterend", emptyHint);
    }
    function apply(f) {
      btns.forEach(function (b) {
        const act = (b.getAttribute("data-mnews-filter") || "all") === f;
        b.classList.toggle("active", act);
        b.setAttribute("aria-pressed", act ? "true" : "false");
      });
      let shown = 0;
      cards.forEach(function (c) {
        const cat = (c.getAttribute("data-mnews-cat") || "").toLowerCase();
        const tier = (c.getAttribute("data-mnews-tier") || "").toUpperCase();
        const ok = f === "all" || (f === "major" ? tier === "P0" : cat === f);
        c.hidden = !ok;
        if (ok) shown += 1;
      });
      if (status) {
        status.textContent = f === "all"
          ? "全量收录 " + cards.length + " 条 · 无上限"
          : "筛选显示 " + shown + " / " + cards.length + " 条";
      }
      if (emptyHint) {
        emptyHint.hidden = shown > 0;
      }
    }
    btns.forEach(function (b) {
      b.addEventListener("click", function () {
        apply(b.getAttribute("data-mnews-filter") || "all");
      });
    });
  }
  initMarketNewsFilters();
})();
