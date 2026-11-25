/* ==========================================================================
   Global Investment Research Portal — Interactive Client Engine (Zero Deps)
   Features: Dark Mode, Font Scaler, Reading Progress, TOC ScrollSpy & Drawer,
             Chart Lightbox Zoom, 135-Stock Screener, Scorecard Tabs, Archive
   ========================================================================== */
(function () {
  "use strict";

  const root = document.documentElement;

  /* ------------------------------------------------------------------------
     1. Dark Mode Toggle (persisted in localStorage)
     ------------------------------------------------------------------------ */
  function getTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("gir_theme", theme);
    } catch (_) {}
    const btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.textContent = theme === "dark" ? "☀️" : "🌙";
      btn.setAttribute("aria-label", theme === "dark" ? "切换浅色模式" : "切换深色模式");
      btn.title = theme === "dark" ? "切换浅色模式" : "切换深色模式";
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
     2. Font Size Scaler (A- / A+)
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
     3. Reading Progress Bar & Scroll-to-Top
     ------------------------------------------------------------------------ */
  const progressBar = document.getElementById("reading-progress");
  function updateProgress() {
    if (!progressBar) return;
    const docH = document.documentElement.scrollHeight - window.innerHeight;
    if (docH <= 0) {
      progressBar.style.width = "0%";
      return;
    }
    const pct = Math.max(0, Math.min(100, (window.scrollY / docH) * 100));
    progressBar.style.width = pct.toFixed(1) + "%";
  }
  window.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress, { passive: true });
  updateProgress();

  document.querySelectorAll("[data-action='scroll-top']").forEach(function (el) {
    el.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
  document.querySelectorAll("[data-action='print']").forEach(function (el) {
    el.addEventListener("click", function () {
      window.print();
    });
  });

  /* ------------------------------------------------------------------------
     4. TOC ScrollSpy (Desktop) & Bottom-Sheet TOC Drawer (Mobile)
     ------------------------------------------------------------------------ */
  const tocLinks = Array.from(document.querySelectorAll(".toc-sidebar .toc-link"));
  if (tocLinks.length > 0) {
    const headings = tocLinks
      .map(function (a) {
        const id = a.getAttribute("href").replace(/^#/, "");
        return { link: a, el: document.getElementById(id) };
      })
      .filter(function (x) { return !!x.el; });

    let activeLink = null;
    function syncToc() {
      const offset = 110;
      let current = headings[0];
      for (let i = 0; i < headings.length; i++) {
        if (headings[i].el.getBoundingClientRect().top <= offset) {
          current = headings[i];
        } else {
          break;
        }
      }
      if (current && current.link !== activeLink) {
        if (activeLink) activeLink.classList.remove("active");
        current.link.classList.add("active");
        activeLink = current.link;
        // Keep active TOC item visible inside scrollable sidebar
        const sidebar = document.querySelector(".toc-sidebar");
        if (sidebar && sidebar.scrollHeight > sidebar.clientHeight) {
          const top = current.link.offsetTop - sidebar.clientHeight / 2;
          sidebar.scrollTo({ top: Math.max(0, top), behavior: "auto" });
        }
      }
    }
    window.addEventListener("scroll", syncToc, { passive: true });
    syncToc();
  }

  const tocBackdrop = document.getElementById("toc-backdrop");
  let modalReturnFocus = null;
  const modalFocusable = "button:not([disabled]), a[href], [tabindex='0']";
  function showDialog(dialog) {
    modalReturnFocus = document.activeElement;
    dialog.classList.add("open");
    document.body.style.overflow = "hidden";
    const target = dialog.querySelector(modalFocusable);
    if (target) target.focus();
  }
  function hideDialog(dialog) {
    if (!dialog.classList.contains("open")) return;
    dialog.classList.remove("open");
    document.body.style.overflow = "";
    if (modalReturnFocus && modalReturnFocus.isConnected) modalReturnFocus.focus();
    modalReturnFocus = null;
  }
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
     5. Chart Lightbox Fullscreen Zoom Modal
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

  document.addEventListener("keydown", function (e) {
    const dialog = document.querySelector('[aria-modal="true"].open');
    if (!dialog) return;
    if (e.key === "Escape") {
      closeChartModal();
      setTocDrawer(false);
    } else if (e.key === "Tab") {
      const targets = dialog.querySelectorAll(modalFocusable);
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (!first) return;
      if (!dialog.contains(document.activeElement) || (e.shiftKey && document.activeElement === first)
          || (!e.shiftKey && document.activeElement === last)) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      }
    }
  });

  /* ------------------------------------------------------------------------
     6. Interactive 135-Company Global Stock Screener
     ------------------------------------------------------------------------ */
  const screenerDataEl = document.getElementById("screener-data");
  if (screenerDataEl) {
    let allStocks = [];
    try {
      allStocks = JSON.parse(screenerDataEl.textContent || "[]");
    } catch (_) {
      allStocks = [];
    }

    const state = {
      q: "",
      market: "all",
      color: "all",
      sector: "all",
      sortKey: "default",
      sortDir: 1,
    };

    const qInput = document.getElementById("scr-search");
    const sectorSel = document.getElementById("scr-sector");
    const mktBtns = Array.from(document.querySelectorAll("[data-filter-market]"));
    const colBtns = Array.from(document.querySelectorAll("[data-filter-color]"));
    const countEl = document.getElementById("scr-count");
    const tbody = document.getElementById("scr-tbody");
    const cardsEl = document.getElementById("scr-cards");
    const resetBtn = document.getElementById("scr-reset");
    const hasData = Array.isArray(allStocks) && allStocks.length > 0;

    const COLOR_ORDER = { g: 1, b: 2, y: 3, r: 4 };
    const COLOR_MARK = { g: "●", b: "◆", y: "▲", r: "×" };
    const sortHeaders = Array.from(document.querySelectorAll("table.screener-table th.sortable"));
    sortHeaders.forEach(function (th) {
      th.querySelector("button").disabled = !hasData;
      if (!th.dataset.baseLabel) {
        th.dataset.baseLabel = (th.textContent || "").replace(/\s*[⇅▲▼]\s*$/, "").trim();
      }
    });

    function syncSortHeaders() {
      sortHeaders.forEach(function (th) {
        const key = th.getAttribute("data-sort");
        const base = th.dataset.baseLabel || "";
        if (state.sortKey === key) {
          const dirStr = state.sortDir === 1 ? "asc" : "desc";
          th.setAttribute("data-sort-dir", dirStr);
          th.setAttribute("aria-sort", state.sortDir === 1 ? "ascending" : "descending");
          th.querySelector("button").textContent = base + (state.sortDir === 1 ? " ▲" : " ▼");
        } else {
          th.removeAttribute("data-sort-dir");
          th.removeAttribute("aria-sort");
          th.querySelector("button").textContent = base + " ⇅";
        }
      });
    }

    function escHtml(s) {
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function populateSectors() {
      if (!sectorSel) return;
      const cur = state.sector;
      const seen = new Set();
      const opts = [];
      allStocks.forEach(function (st) {
        if (state.market !== "all" && st.market !== state.market) return;
        const key = st.market_label + " · " + st.sector;
        if (!seen.has(key)) {
          seen.add(key);
          opts.push({ val: key, label: key });
        }
      });
      sectorSel.innerHTML = '<option value="all">全部赛道 (' + opts.length + ')</option>';
      opts.forEach(function (o) {
        const opt = document.createElement("option");
        opt.value = o.val;
        opt.textContent = o.label;
        sectorSel.appendChild(opt);
      });
      if (seen.has(cur)) {
        sectorSel.value = cur;
      } else {
        state.sector = "all";
        sectorSel.value = "all";
      }
    }

    function renderScreener() {
      if (!hasData) return;
      const q = state.q.trim().toLowerCase();
      let rows = allStocks.filter(function (st) {
        if (state.market !== "all" && st.market !== state.market) return false;
        if (state.color !== "all" && st.color !== state.color) return false;
        if (state.sector !== "all" && (st.market_label + " · " + st.sector) !== state.sector) return false;
        if (q) {
          const hay = (st.name + " " + st.code + " " + st.sector + " " + st.market_label + " " + st.summary + " " + st.action_label + " " + st.valuation).toLowerCase();
          if (hay.indexOf(q) === -1) return false;
        }
        return true;
      });

      if (state.sortKey !== "default") {
        rows = rows.slice().sort(function (a, b) {
          if (state.sortKey === "color") {
            const va = COLOR_ORDER[a.color] || 9;
            const vb = COLOR_ORDER[b.color] || 9;
            return (va - vb) * state.sortDir;
          }
          const va = String(a[state.sortKey] || "");
          const vb = String(b[state.sortKey] || "");
          return va.localeCompare(vb, "zh-Hans-CN", { numeric: true }) * state.sortDir;
        });
      }
      syncSortHeaders();

      if (countEl) {
        countEl.textContent = "显示 " + rows.length + " / " + allStocks.length + " 家龙头公司";
      }

      if (tbody) {
        if (rows.length === 0) {
          tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:28px;color:var(--ink-3);">未找到匹配的龙头公司，请尝试放宽筛选条件。</td></tr>';
        } else {
          tbody.innerHTML = rows
            .map(function (st) {
              const mark = COLOR_MARK[st.color] || "●";
              return (
                '<tr class="row-' + escHtml(st.color) + '">' +
                '<td><span class="mkt-badge mkt-' + escHtml(st.market) + '">' + escHtml(st.market_label) + "</span></td>" +
                '<td class="nw">' + escHtml(st.sector) + "</td>" +
                '<td><strong>' + escHtml(st.name) + '</strong> <span class="code-tag">' + escHtml(st.code) + "</span></td>" +
                '<td class="nw">' + escHtml(st.price) + "</td>" +
                "<td>" + escHtml(st.valuation) + "</td>" +
                '<td><span class="act-pill act-' + escHtml(st.color) + '">' + mark + " " + escHtml(st.action_label) + "</span></td>" +
                '<td>' + escHtml(st.summary) + ' <a href="' + escHtml(st.report_url) + '" class="nw">手册 →</a></td>' +
                "</tr>"
              );
            })
            .join("");
        }
      }

      if (cardsEl) {
        if (rows.length === 0) {
          cardsEl.innerHTML = '<div class="panel-card" style="text-align:center;color:var(--ink-3);">未找到匹配的龙头公司，请尝试放宽筛选条件。</div>';
        } else {
          cardsEl.innerHTML = rows
            .map(function (st) {
              const mark = COLOR_MARK[st.color] || "●";
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
                "<span><strong>价格：</strong>" + escHtml(st.price) + "</span>" +
                "<span><strong>估值：</strong>" + escHtml(st.valuation) + "</span>" +
                "</div>" +
                '<div class="sc-summary">' + escHtml(st.summary) + "</div>" +
                '<div><a href="' + escHtml(st.report_url) + '" style="font-size:12.5px;font-weight:700;">查看该市场全景手册 →</a></div>' +
                "</div>"
              );
            })
            .join("");
        }
      }
    }

    if (qInput) {
      qInput.addEventListener("input", function () {
        state.q = qInput.value;
        renderScreener();
      });
    }
    if (sectorSel) {
      sectorSel.addEventListener("change", function () {
        state.sector = sectorSel.value;
        renderScreener();
      });
    }
    mktBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.market = btn.getAttribute("data-filter-market") || "all";
        mktBtns.forEach(function (b) { b.classList.toggle("active", b === btn); });
        populateSectors();
        renderScreener();
      });
    });
    colBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.color = btn.getAttribute("data-filter-color") || "all";
        colBtns.forEach(function (b) { b.classList.toggle("active", b === btn); });
        renderScreener();
      });
    });
    document.querySelectorAll("[data-stat-color]").forEach(function (tile) {
      tile.addEventListener("click", function () {
        const col = tile.getAttribute("data-stat-color") || "all";
        state.color = col;
        colBtns.forEach(function (b) {
          b.classList.toggle("active", (b.getAttribute("data-filter-color") || "all") === col);
        });
        renderScreener();
      });
    });
    sortHeaders.forEach(function (th) {
      th.querySelector("button").addEventListener("click", function () {
        const key = th.getAttribute("data-sort");
        if (state.sortKey === key) {
          state.sortDir *= -1;
        } else {
          state.sortKey = key;
          state.sortDir = 1;
        }
        renderScreener();
      });
    });
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        state.q = "";
        state.market = "all";
        state.color = "all";
        state.sector = "all";
        state.sortKey = "default";
        state.sortDir = 1;
        if (qInput) qInput.value = "";
        mktBtns.forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-filter-market") === "all"); });
        colBtns.forEach(function (b) { b.classList.toggle("active", b.getAttribute("data-filter-color") === "all"); });
        populateSectors();
        renderScreener();
      });
    }

    if (hasData) {
      populateSectors();
      renderScreener();
      document.documentElement.classList.add("screener-enhanced");
    }
  }

  /* ------------------------------------------------------------------------
     7. Scorecard & Changelog Tabs (with URL Hash Sync)
     ------------------------------------------------------------------------ */
  const tabBtns = Array.from(document.querySelectorAll("[data-tab-target]"));
  if (tabBtns.length > 0) {
    function keepTabBarVisible() {
      requestAnimationFrame(function () {
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
        history.replaceState(null, "", "#" + targetId);
      }
      return valid;
    }

    tabBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        activateTab(btn.getAttribute("data-tab-target"), true);
      });
    });
    const initHash = (location.hash || "").replace(/^#/, "");
    const matchedInit = activateTab(initHash || tabBtns[0].getAttribute("data-tab-target"), false);
    if (initHash && matchedInit) {
      keepTabBarVisible();
      window.addEventListener("load", keepTabBarVisible, { once: true });
    }
    window.addEventListener("hashchange", function () {
      const h = (location.hash || "").replace(/^#/, "");
      if (h && activateTab(h, false)) {
        keepTabBarVisible();
      }
    });
  }

  /* ------------------------------------------------------------------------
     8. Archive Chronological Filters
     ------------------------------------------------------------------------ */
  const arcItems = Array.from(document.querySelectorAll("[data-arc-item]"));
  if (arcItems.length > 0) {
    const arcState = { market: "all", session: "all" };
    const arcMktBtns = Array.from(document.querySelectorAll("[data-arc-market]"));
    const arcSesBtns = Array.from(document.querySelectorAll("[data-arc-session]"));
    const arcCountEl = document.getElementById("arc-count");

    function applyArchiveFilter() {
      let shown = 0;
      arcItems.forEach(function (el) {
        const m = el.getAttribute("data-market");
        const s = el.getAttribute("data-session");
        const ok =
          (arcState.market === "all" || m === arcState.market) &&
          (arcState.session === "all" || s === arcState.session);
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
        arcCountEl.textContent = "共展示 " + shown + " 期历史日报";
      }
    }

    arcMktBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        arcState.market = b.getAttribute("data-arc-market") || "all";
        arcMktBtns.forEach(function (x) { x.classList.toggle("active", x === b); });
        applyArchiveFilter();
      });
    });
    arcSesBtns.forEach(function (b) {
      b.addEventListener("click", function () {
        arcState.session = b.getAttribute("data-arc-session") || "all";
        arcSesBtns.forEach(function (x) { x.classList.toggle("active", x === b); });
        applyArchiveFilter();
      });
    });

    const hashMkt = (location.hash || "").replace(/^#/, "");
    if (["gold", "a-share", "hk-stock", "us-stock"].indexOf(hashMkt) !== -1) {
      arcState.market = hashMkt;
      arcMktBtns.forEach(function (x) {
        x.classList.toggle("active", x.getAttribute("data-arc-market") === hashMkt);
      });
    }
    applyArchiveFilter();
  }
})();
