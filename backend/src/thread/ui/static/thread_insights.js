/** Insights — slice HTMX, session restore, award drawer. ponytail: one file for page chrome */
(function () {
  var SLICE_TARGET = "#insights-stage-content";
  var SESSION_KEY = "insights-session-v1";

  function stageStatusEl() {
    return document.getElementById("insights-slice-loading");
  }

  function sliceTargetId(target) {
    if (!target) return "";
    if (typeof target === "string") return target.replace(/^#/, "");
    if (target.id) return target.id;
    // ponytail: HTMX 2 passes Element, not "#insights-stage-content"
    if (target.nodeType === 1 && target.matches && target.matches(SLICE_TARGET)) {
      return "insights-stage-content";
    }
    return "";
  }

  function isSliceRequest(e) {
    var cfg = e.detail && e.detail.requestConfig;
    var targetId = sliceTargetId(cfg && cfg.target);
    if (targetId === "insights-stage-content") return true;
    var elt = e.detail && e.detail.elt;
    if (!elt) return false;
    if (elt.id === "insights-radar-form") return true;
    if (elt.closest && elt.closest("#insights-stage-content")) return true;
    if (elt.classList && (elt.classList.contains("insights-drill-chip") || elt.classList.contains("insights-lens-tab"))) {
      return true;
    }
    return false;
  }

  function isStageSwap(t) {
    if (!t) return false;
    return t.id === "insights-stage-content" || t.id === "insights-body" || !!(t.closest && t.closest("#insights-stage-content"));
  }

  function setStageStatus(message, kind) {
    var el = stageStatusEl();
    if (!el) return;
    el.textContent = message || "";
    el.classList.remove("is-error", "is-loading", "htmx-request");
    if (kind === "error") el.classList.add("is-error");
    if (kind === "loading") {
      el.classList.add("is-loading", "htmx-request");
    }
  }

  function clearLoadingStatus() {
    var el = stageStatusEl();
    var stage = document.getElementById("insights-stage-content");
    if (el) {
      el.textContent = "";
      el.classList.remove("htmx-request", "is-error", "is-loading");
    }
    if (stage) stage.classList.remove("is-loading");
    document.querySelectorAll(".insights-drill-chip.is-loading").forEach(function (chip) {
      chip.classList.remove("is-loading");
    });
  }

  window.showInsightsSliceLoading = function (message) {
    setStageStatus(message || "Loading…", "loading");
    var stage = document.getElementById("insights-stage-content");
    if (stage) stage.classList.add("is-loading");
  };
  window.clearInsightsSliceLoading = clearLoadingStatus;

  window.openInsightsBookmarksDrawer = function () {
    mountOverlaysOnBody();
    var root = document.getElementById("insights-bookmarks-drawer-root");
    if (!root) return;
    root.classList.remove("insights-drawer-hidden");
    root.setAttribute("aria-hidden", "false");
    if (window.lucide) window.lucide.createIcons();
  };

  window.openInsightsSaveBookmarkDrawer = function () {
    window.openInsightsBookmarksDrawer();
    var section = document.getElementById("insights-bookmark-save-section");
    var nameInput = document.getElementById("insights-bookmark-name-input");
    if (section) section.scrollIntoView({ block: "nearest", behavior: "smooth" });
    if (nameInput) {
      window.setTimeout(function () {
        nameInput.focus();
      }, 80);
    }
  };

  window.closeInsightsBookmarksDrawer = function () {
    var root = document.getElementById("insights-bookmarks-drawer-root");
    if (!root) return;
    root.classList.add("insights-drawer-hidden");
    root.setAttribute("aria-hidden", "true");
  };

  function insightsForm() {
    return document.getElementById("insights-radar-form");
  }

  function sliceFacetSnapshot() {
    return document.getElementById("insights-slice-facets");
  }

  function forEachFacetField(root, fn) {
    if (!root) return;
    root.querySelectorAll("input[name], select[name], textarea[name]").forEach(function (field) {
      if (field.name) fn(field.value, field.name);
    });
  }

  function buildSliceFormData(extra) {
    var fd = new FormData();
    forEachFacetField(sliceFacetSnapshot(), function (value, key) {
      if (value != null && String(value).length) fd.set(key, String(value));
    });
    try {
      var session = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
      if (session) {
        Object.keys(session).forEach(function (key) {
          if (key === "saved_at" || key === "award_key" || key === "lens") return;
          if (!fd.has(key) && session[key]) fd.set(key, String(session[key]));
        });
      }
    } catch (_) {}
    var form = insightsForm();
    if (form) {
      new FormData(form).forEach(function (value, key) {
        if (value != null && String(value).length) fd.set(key, String(value));
      });
    }
    forEachNamedField(entityState(), function (value, key) {
      if (value != null && String(value).length) fd.set(key, String(value));
    });
    fd.set("run", "1");
    Object.keys(extra || {}).forEach(function (key) {
      var val = extra[key];
      if (val != null && String(val).length) fd.set(key, String(val));
    });
    return fd;
  }

  function setLensEntity(lens, scope, value) {
    var root = entityState();
    if (!root) return;
    function setField(name, val) {
      var input = root.querySelector('[name="' + name + '"]');
      if (input) input.value = val || "";
    }
    if (lens === "competitor") {
      setField("competitor_entity_value", value);
      setField("competitor_entity_scope", scope || "recipient");
    } else {
      setField("agency_entity_value", value);
      setField("agency_entity_scope", scope || "agency");
    }
    setField("entity_kind", "");
    setField("entity_value", "");
    setField("entity_scope", "");
  }

  function syncSidebarFromSliceFacets() {
    var snap = sliceFacetSnapshot();
    var form = insightsForm();
    if (!snap || !form) return;
    forEachFacetField(snap, function (value, key) {
      var input = form.querySelector('[name="' + key + '"]');
      if (input) input.value = value;
    });
  }

  var traceAwardFocus = { fundingOffice: null, recipient: null };
  var spineBaselineHtml = null;
  var spineFocusToken = 0;
  var spineServerFocused = false;

  function normTraceLabel(value) {
    return (value || "").trim().toLowerCase();
  }

  function spineRows() {
    var panel = document.getElementById("insights-award-spine-scroll");
    return panel ? panel.querySelectorAll(".insights-result-row") : [];
  }

  function rowMatchesTraceFocus(row, focus) {
    if (!focus.fundingOffice && !focus.recipient) return true;
    var office = row.getAttribute("data-funding-office") || "";
    var recipient = row.getAttribute("data-recipient") || "";
    if (focus.fundingOffice && normTraceLabel(office) !== normTraceLabel(focus.fundingOffice)) return false;
    if (focus.recipient && normTraceLabel(recipient) !== normTraceLabel(focus.recipient)) return false;
    return true;
  }

  function restoreSpineBaseline() {
    var scroll = document.getElementById("insights-award-spine-scroll");
    if (scroll && spineBaselineHtml != null) scroll.innerHTML = spineBaselineHtml;
    spineServerFocused = false;
  }

  function updateSpineCaption(text, hasFocus) {
    var caption = document.getElementById("insights-award-spine-caption");
    var clearBtn = document.getElementById("insights-trace-focus-clear");
    if (clearBtn) clearBtn.classList.toggle("is-visible", hasFocus);
    if (!caption) return;
    var hintText = caption.getAttribute("data-focus-hint") || "";
    if (!hasFocus) {
      var base = caption.getAttribute("data-base-summary") || "";
      caption.textContent = "";
      if (base) caption.appendChild(document.createTextNode(base));
      if (hintText) {
        var hintEl = document.createElement("span");
        hintEl.className = "insights-trace-focus-hint text-slate-600";
        hintEl.textContent = hintText;
        caption.appendChild(hintEl);
      }
      return;
    }
    caption.textContent = text || "";
  }

  function applyTraceAwardFocus() {
    var focus = traceAwardFocus;
    var hasFocus = !!(focus.fundingOffice || focus.recipient);
    var rows = spineRows();
    var matchCount = 0;
    rows.forEach(function (row) {
      row.classList.remove("trace-focus-match", "trace-focus-dim");
      if (!hasFocus) return;
      if (spineServerFocused) {
        row.classList.add("trace-focus-match");
        matchCount += 1;
        return;
      }
      var match = rowMatchesTraceFocus(row, focus);
      row.classList.toggle("trace-focus-match", match);
      row.classList.toggle("trace-focus-dim", !match);
      if (match) matchCount += 1;
    });
    if (!hasFocus) {
      updateSpineCaption("", false);
      return;
    }
    if (spineServerFocused) return;
    var parts = [];
    if (focus.fundingOffice) parts.push(focus.fundingOffice);
    if (focus.recipient) parts.push(focus.recipient);
    updateSpineCaption(
      matchCount + " of " + rows.length + " loaded · " + parts.join(" × "),
      true
    );
  }

  function fetchTraceSpineRows(focus) {
    var scroll = document.getElementById("insights-award-spine-scroll");
    if (!scroll) return;
    if (!focus.fundingOffice && !focus.recipient) return;
    if (spineBaselineHtml == null) spineBaselineHtml = scroll.innerHTML;
    var token = ++spineFocusToken;
    scroll.classList.add("is-loading");
    updateSpineCaption("Loading contracts for trace…", true);
    var lensInput = document.getElementById("insights-active-lens");
    var fd = buildSliceFormData({
      trace_buyer_office: focus.fundingOffice,
      trace_recipient: focus.recipient,
      lens: lensInput && lensInput.value ? lensInput.value : "agency",
    });
    fetch("/partials/insights/award-spine-focus", { method: "POST", body: fd })
      .then(function (res) {
        if (!res.ok) throw new Error("spine focus " + res.status);
        return res.text();
      })
      .then(function (html) {
        if (token !== spineFocusToken) return;
        scroll.innerHTML = html;
        scroll.classList.remove("is-loading");
        spineServerFocused = true;
        var meta = scroll.querySelector("#insights-spine-focus-meta");
        var summary = meta ? meta.getAttribute("data-summary") : "";
        if (meta) meta.remove();
        updateSpineCaption(summary || "Trace-scoped contracts", true);
        applyTraceAwardFocus();
      })
      .catch(function () {
        if (token !== spineFocusToken) return;
        scroll.classList.remove("is-loading");
        spineServerFocused = false;
        applyTraceAwardFocus();
      });
  }

  window.clearTraceAwardFocus = function () {
    spineFocusToken += 1;
    traceAwardFocus = { fundingOffice: null, recipient: null };
    restoreSpineBaseline();
    spineBaselineHtml = null;
    applyTraceAwardFocus();
  };

  window.setTraceAwardFocus = function (patch, opts) {
    opts = opts || {};
    if (opts.clear) {
      window.clearTraceAwardFocus();
      return;
    }
    patch = patch || {};
    if (patch.fundingOffice !== undefined) {
      traceAwardFocus.fundingOffice = patch.fundingOffice || null;
      if (opts.resetRecipient) traceAwardFocus.recipient = null;
    }
    if (patch.recipient !== undefined) traceAwardFocus.recipient = patch.recipient || null;
    spineServerFocused = false;
    applyTraceAwardFocus();
    fetchTraceSpineRows(traceAwardFocus);
  };

  function afterInsightsStageSwap() {
    clearLoadingStatus();
    spineBaselineHtml = null;
    spineFocusToken += 1;
    window.clearTraceAwardFocus();
    var stage = document.getElementById("insights-stage-content");
    if (stage) stage.classList.remove("is-loading");
    var lensInput = document.getElementById("insights-active-lens");
    if (lensInput && stage && stage.dataset.activeLens) lensInput.value = stage.dataset.activeLens;
    syncSidebarFromSliceFacets();
    window.persistInsightsSession();
    if (window.initInsightsPage) window.initInsightsPage();
    if (window.htmx && stage) window.htmx.process(stage);
  }

  // ponytail: facet snapshot on #insights-stage-content — sidebar form is often empty after bookmark load
  window.setLensEntity = setLensEntity;

  window.postInsightsSlice = function (extra, loadingMsg) {
    var stage = document.getElementById("insights-stage-content");
    if (!stage || stage.getAttribute("data-has-slice") !== "1") {
      return Promise.reject(new Error("Run slice first"));
    }
    var fd = buildSliceFormData(extra);
    if (extra && extra.lens) {
      var lensInput = document.getElementById("insights-active-lens");
      if (lensInput) lensInput.value = extra.lens;
    }
    if (extra && extra.entity_value) {
      var drillLens =
        extra.lens || (extra.entity_kind === "competitor" ? "competitor" : "agency");
      setLensEntity(drillLens, extra.entity_scope, extra.entity_value);
    }
    if (window.showInsightsSliceLoading) window.showInsightsSliceLoading(loadingMsg || "Opening profile…");
    else if (loadingMsg) setStageStatus(loadingMsg, "loading");
    stage.classList.add("is-loading");
    return fetch("/partials/insights/slice", {
      method: "POST",
      body: fd,
      headers: { "HX-Request": "true" },
      credentials: "same-origin",
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.text();
      })
      .then(function (html) {
        var target = document.getElementById("insights-stage-content");
        if (!target) throw new Error("Stage missing");
        target.outerHTML = html;
        afterInsightsStageSwap();
      })
      .catch(function (err) {
        clearLoadingStatus();
        var stage = document.getElementById("insights-stage-content");
        if (stage) stage.classList.remove("is-loading");
        setStageStatus("Could not load lens — " + (err.message || "network error"), "error");
        throw err;
      });
  };

  function entityState() {
    return document.getElementById("insights-entity-state");
  }

  // ponytail: #insights-entity-state is a <div> of hidden inputs, not a <form>
  function forEachNamedField(root, fn) {
    if (!root) return;
    if (root.tagName === "FORM") {
      new FormData(root).forEach(fn);
      return;
    }
    root.querySelectorAll("input[name], select[name], textarea[name]").forEach(function (field) {
      if (field.name) fn(field.value, field.name);
    });
  }

  function isInsightsClewLink(anchor) {
    if (!anchor || anchor.tagName !== "A") return false;
    if (anchor.classList.contains("insights-clew-link")) return true;
    var href = anchor.getAttribute("href") || "";
    return href.indexOf("/clew") >= 0 && href.indexOf("from=insights") >= 0;
  }

  window.enhanceInsightsClewHref = function (anchor) {
    if (!isInsightsClewLink(anchor)) return;
    var form = insightsForm();
    if (!form) return;
    try {
      var url = new URL(anchor.href, window.location.origin);
      new FormData(form).forEach(function (value, key) {
        if (value && !url.searchParams.has(key)) url.searchParams.set(key, String(value));
      });
      forEachNamedField(entityState(), function (value, key) {
        if (value && !url.searchParams.has(key)) url.searchParams.set(key, String(value));
      });
      if (!url.searchParams.has("from")) url.searchParams.set("from", "insights");
      anchor.href = url.pathname + url.search;
    } catch (_) {}
  };

  window.persistInsightsSession = function () {
    var session = { run: 1, saved_at: Date.now() };
    forEachFacetField(sliceFacetSnapshot(), function (value, key) {
      if (value) session[key] = String(value);
    });
    var form = insightsForm();
    if (form) {
      new FormData(form).forEach(function (value, key) {
        if (value) session[key] = String(value);
      });
    }
    var stage = document.getElementById("insights-stage-content");
    if (stage && stage.dataset.activeLens) session.lens = stage.dataset.activeLens;
    var lens = document.getElementById("insights-active-lens");
    if (lens && lens.value) session.lens = lens.value;
    forEachNamedField(entityState(), function (value, key) {
      if (value) session[key] = String(value);
    });
    var panel = document.getElementById("insights-award-panel");
    if (panel && panel.getAttribute("data-award-key")) {
      session.award_key = panel.getAttribute("data-award-key");
    }
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch (_) {}
  };

  function fillFormFromSession(session) {
    var form = insightsForm();
    if (!form || !session) return;
    Object.keys(session).forEach(function (key) {
      if (key === "lens" || key === "run" || key === "saved_at" || key === "award_key") return;
      var input = form.querySelector('[name="' + key + '"]');
      if (input) input.value = session[key];
    });
    var lens = document.getElementById("insights-active-lens");
    if (lens && session.lens) lens.value = session.lens;
  }

  function sliceParamsFromSession(session) {
    var params = new URLSearchParams();
    params.set("run", "1");
    params.set("lens", session.lens || "overview");
    var form = insightsForm();
    if (form) {
      new FormData(form).forEach(function (value, key) {
        if (value) params.append(key, String(value));
      });
    }
    [
      "agency_entity_value",
      "agency_entity_scope",
      "competitor_entity_value",
      "competitor_entity_scope",
      "entity_kind",
      "entity_value",
      "entity_scope",
    ].forEach(function (key) {
      if (session[key] && !params.has(key)) params.set(key, session[key]);
    });
    return params;
  }

  window.restoreInsightsSessionIfIdle = function () {
    if (window._insightsSessionRestored) return;
    if (window.location.pathname !== "/insights") return;
    var stage = document.getElementById("insights-stage-content");
    if (stage && stage.getAttribute("data-has-slice") === "1") return;
    if (new URLSearchParams(window.location.search).get("run") === "1") return;
    var session = null;
    try {
      session = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
    } catch (_) {
      session = null;
    }
    if (!session || !session.run || !window.htmx) return;
    window._insightsSessionRestored = true;
    fillFormFromSession(session);
    window.htmx.ajax("GET", "/partials/insights/slice?" + sliceParamsFromSession(session).toString(), {
      target: SLICE_TARGET,
      swap: "outerHTML",
      indicator: "#insights-slice-loading",
    });
  };

  var FACET_FIELDS = [
    "agency", "sub_agency", "recipient", "naics_codes", "psc_codes",
    "awarding_office", "funding_office", "recipient_uei", "pop_state",
    "extent_competed", "type_of_set_aside",
  ];

  window.clearInsightsExplore = function () {
    try {
      localStorage.removeItem(SESSION_KEY);
    } catch (_) {}
    window._insightsSessionRestored = true;
    var form = insightsForm();
    if (form) {
      FACET_FIELDS.forEach(function (name) {
        var input = form.querySelector('[name="' + name + '"]');
        if (input) input.value = "";
      });
    }
    var lens = document.getElementById("insights-active-lens");
    if (lens) lens.value = "overview";
    if (window.closeInsightsAwardDrawer) window.closeInsightsAwardDrawer();
    var tabs = document.getElementById("insights-lens-tabs");
    if (tabs) tabs.classList.add("insights-lens-tabs-hidden");
    var stage = document.getElementById("insights-stage-content");
    if (stage) {
      stage.outerHTML =
        '<div id="insights-stage-content" class="insights-stage-content" data-active-lens="overview" data-has-slice="0">' +
        '<div class="insights-lens-banner" role="region" aria-label="Lens navigation">' +
        '<nav id="insights-lens-tabs" class="insights-lens-tabs insights-lens-tabs-hidden" role="tablist" aria-label="Insights lenses"></nav></div>' +
        '<div id="insights-slice-panel" class="insights-slice-panel">' +
        '<div id="insights-lens-body" class="insights-lens-body insights-lens-idle">' +
        '<p class="insights-idle-hint">Set facets in the slice navigator, then <strong>Run slice</strong>. Lens tabs activate after the first query.</p>' +
        "</div></div></div>";
    }
  };

  function awardRoot() {
    return document.getElementById("insights-award-drawer-root");
  }

  function awardBody() {
    var r = awardRoot();
    return r ? r.querySelector("#insights-award-drawer-body") : null;
  }

  var keepBookmarksDrawerOpen = false;

  function mountOverlaysOnBody() {
    var r = awardRoot();
    if (r && r.parentElement !== document.body) document.body.appendChild(r);
    var bookmarkRoots = document.querySelectorAll("#insights-bookmarks-drawer-root");
    var bookmarks =
      document.querySelector("#insights-body #insights-bookmarks-drawer-root") ||
      (bookmarkRoots.length ? bookmarkRoots[bookmarkRoots.length - 1] : null);
    bookmarkRoots.forEach(function (node) {
      if (node !== bookmarks) node.remove();
    });
    if (bookmarks && bookmarks.parentElement !== document.body) document.body.appendChild(bookmarks);
    if (bookmarks && window.htmx) window.htmx.process(bookmarks);
  }

  function refreshBookmarksChrome() {
    mountOverlaysOnBody();
    if (keepBookmarksDrawerOpen) window.openInsightsBookmarksDrawer();
    keepBookmarksDrawerOpen = false;
  }

  function syncAwardTitle() {
    var panel = document.getElementById("insights-award-panel");
    var titleEl = document.getElementById("insights-award-drawer-title");
    if (!titleEl || !panel) return;
    var piid = panel.querySelector(".text-neon-cyan");
    var recipient = panel.querySelector(".text-sm.font-semibold");
    if (piid && piid.textContent.indexOf("PIID") === 0) {
      titleEl.textContent = piid.textContent.replace("PIID ", "").trim();
    } else if (recipient) {
      titleEl.textContent = recipient.textContent.trim().slice(0, 48);
    }
  }

  function showAwardShellLoading() {
    mountOverlaysOnBody();
    var r = awardRoot();
    var b = awardBody();
    if (!r || !b) return false;
    r.classList.remove("task-drawer-hidden");
    r.setAttribute("aria-hidden", "false");
    document.body.classList.add("task-drawer-open");
    b.innerHTML = '<p class="insights-idle-hint p-4 text-neon-cyan">Loading contract profile…</p>';
    return true;
  }

  function showAwardError(message) {
    if (!showAwardShellLoading()) return;
    var b = awardBody();
    b.innerHTML =
      '<div class="p-4 space-y-2"><p class="text-neon-amber text-xs font-semibold">Could not load contract profile.</p>' +
      '<p class="text-[11px] text-slate-500 font-mono">' + message + "</p></div>";
  }

  function afterAwardDrawerSwap(target) {
    window.persistInsightsSession();
    if (window.htmx && target) {
      target.querySelectorAll("[hx-get],[hx-post],[hx-delete],[hx-put],[hx-patch]").forEach(function (el) {
        window.htmx.process(el);
      });
    }
    if (window.lucide) window.lucide.createIcons();
    document.querySelectorAll("#insights-award-drawer-body a.insights-clew-link").forEach(function (a) {
      window.enhanceInsightsClewHref(a);
    });
    syncAwardTitle();
  }

  function awardDrawerUrl(awardKey) {
    return "/partials/insights/award?award_key=" + encodeURIComponent(awardKey);
  }

  function loadAwardDrawerContent(awardKey) {
    fetch(awardDrawerUrl(awardKey), { headers: { Accept: "text/html" }, credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.text();
      })
      .then(function (html) {
        var b = awardBody();
        if (!b) throw new Error("Drawer body missing");
        if (!html || !html.trim()) throw new Error("Empty award response");
        b.innerHTML = html;
        afterAwardDrawerSwap(b);
      })
      .catch(function (err) {
        showAwardError((err && err.message) || "Could not load contract profile.");
      });
  }

  // ponytail: fetch + delegation — same pattern as thread_task_drawer.js (htmx.ajax into hidden shell was flaky)
  window.openInsightsAwardDrawer = function (awardKey) {
    awardKey = (awardKey || "").trim();
    if (!awardKey) {
      showAwardError("No award key on this row — run slice again to refresh expiring data.");
      return;
    }
    if (!showAwardShellLoading()) {
      showAwardError("Contract drawer shell missing — hard refresh /insights.");
      return;
    }
    loadAwardDrawerContent(awardKey);
  };

  window.closeInsightsAwardDrawer = function () {
    var r = awardRoot();
    if (!r) return;
    r.classList.add("task-drawer-hidden");
    r.setAttribute("aria-hidden", "true");
    document.body.classList.remove("task-drawer-open");
    window.persistInsightsSession();
  };

  function bindNaicsChips() {
    document.querySelectorAll(".insights-naics-chip").forEach(function (btn) {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", function () {
        var input = document.getElementById("insights-naics-input");
        if (!input) return;
        var code = btn.getAttribute("data-naics");
        var parts = input.value.split(/[,;\s]+/).map(function (s) { return s.trim(); }).filter(Boolean);
        if (parts.indexOf(code) < 0) parts.push(code);
        input.value = parts.join(", ");
      });
    });
  }

  function bindRunSliceReset() {
    var form = insightsForm();
    if (!form || form.dataset.runResetBound) return;
    form.dataset.runResetBound = "1";
    form.addEventListener("submit", function () {
      var lens = document.getElementById("insights-active-lens");
      if (lens) lens.value = "overview";
      setStageStatus("Running slice… PostgreSQL query may take 30–90 seconds.", "loading");
      var body = document.getElementById("insights-lens-body");
      if (body) body.innerHTML = '<p class="insights-lens-loading">Querying intel tables…</p>';
    });
  }

  function bindClearButton() {
    var btn = document.getElementById("insights-clear-btn");
    if (!btn || btn.dataset.insightsClearBound) return;
    btn.dataset.insightsClearBound = "1";
    btn.addEventListener("click", function () {
      window.clearInsightsExplore();
    });
  }

  function processInsightsForm() {
    if (!window.htmx) return;
    var form = insightsForm();
    if (form) window.htmx.process(form);
    var stage = document.getElementById("insights-stage-content");
    if (stage) window.htmx.process(stage);
  }

  function initInsightsPage() {
    bindNaicsChips();
    bindRunSliceReset();
    bindClearButton();
    processInsightsForm();
    if (window.initClewCharts) window.initClewCharts();
    if (window.initInsightsHone) window.initInsightsHone();
    if (window.lucide) window.lucide.createIcons();
  }

  window.initInsightsPage = initInsightsPage;

  function scheduleSessionRestore() {
    var attempts = 0;
    (function attempt() {
      if (window._insightsSessionRestored || window.location.pathname !== "/insights") return;
      if (window.htmx && window.initInsightsHone) {
        window.restoreInsightsSessionIfIdle();
        return;
      }
      if (++attempts < 40) window.setTimeout(attempt, 50);
    })();
  }

  function bindInsightsChrome() {
    if (window._insightsChromeBound) return;
    window._insightsChromeBound = true;

    document.body.addEventListener("click", function (event) {
      var anchor = event.target.closest("a");
      if (isInsightsClewLink(anchor)) {
        window.persistInsightsSession();
        window.enhanceInsightsClewHref(anchor);
      }
    }, true);

    document.body.addEventListener("click", function (event) {
      var drill = event.target.closest("[data-insights-drill]");
      if (drill) {
        event.preventDefault();
        if (window.releaseIntensityDrillLock) window.releaseIntensityDrillLock();
        window.postInsightsSlice(
          {
            lens: drill.getAttribute("data-lens") || "agency",
            entity_kind: drill.getAttribute("data-entity-kind") || "",
            entity_value: drill.getAttribute("data-entity-value") || "",
            entity_scope: drill.getAttribute("data-entity-scope") || "",
          },
          "Opening profile…"
        ).catch(function () {});
        return;
      }
      var opener = event.target.closest("li.insights-award-open[data-award-key]");
      if (!opener) return;
      var key = (opener.getAttribute("data-award-key") || "").trim();
      if (!key) return;
      event.preventDefault();
      event.stopPropagation();
      window.openInsightsAwardDrawer(key);
    }, true);

    document.body.addEventListener("htmx:beforeRequest", function (e) {
      var elt = e.detail && e.detail.elt;
      if (elt && elt.closest && (elt.closest(".insights-bookmark-save") || elt.closest(".insights-bookmark-delete"))) {
        var root = document.getElementById("insights-bookmarks-drawer-root");
        keepBookmarksDrawerOpen = !!(root && !root.classList.contains("insights-drawer-hidden"));
      }
      if (!isSliceRequest(e)) return;
      var elt = e.detail && e.detail.elt;
      if (elt && elt.id === "insights-radar-form") return;
      var msg = "Loading lens results…";
      if (elt && elt.classList) {
        if (elt.classList.contains("insights-lens-tab")) msg = "Switching to " + (elt.textContent || "lens").trim() + "…";
        else if (elt.classList.contains("insights-drill-chip")) msg = "Opening profile…";
      }
      setStageStatus(msg, "loading");
    }, true);

    document.body.addEventListener("htmx:afterSwap", function (e) {
      var t = e.detail && e.detail.target;
      if (!t || !isStageSwap(t)) return;
      if (window.releaseIntensityDrillLock) window.releaseIntensityDrillLock();
      afterInsightsStageSwap();
      if (t.id === "insights-body") {
        mountOverlaysOnBody();
        bindClearButton();
      }
    });

    document.body.addEventListener("htmx:responseError", function (e) {
      if (!isSliceRequest(e)) return;
      if (window.releaseIntensityDrillLock) window.releaseIntensityDrillLock();
      var status = e.detail.xhr && e.detail.xhr.status;
      setStageStatus("Slice request failed" + (status ? " (HTTP " + status + ")" : "") + ".", "error");
      clearLoadingStatus();
    });

    document.body.addEventListener("htmx:sendError", function (e) {
      if (!isSliceRequest(e)) return;
      if (window.releaseIntensityDrillLock) window.releaseIntensityDrillLock();
      setStageStatus("Network error — could not reach server.", "error");
      clearLoadingStatus();
    });

    document.body.addEventListener("htmx:timeout", function (e) {
      if (!isSliceRequest(e)) return;
      if (window.releaseIntensityDrillLock) window.releaseIntensityDrillLock();
      setStageStatus("Request timed out — server may be overloaded. Try again.", "error");
      clearLoadingStatus();
    });

    document.body.addEventListener("htmx:afterRequest", function (e) {
      var elt = e.detail && e.detail.elt;
      if (!elt || !elt.closest) return;
      if (!elt.closest(".insights-bookmark-save") && !elt.closest(".insights-bookmark-delete")) return;
      if (e.detail.successful) refreshBookmarksChrome();
      else keepBookmarksDrawerOpen = false;
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      var r = awardRoot();
      if (r && !r.classList.contains("task-drawer-hidden")) {
        window.closeInsightsAwardDrawer();
        return;
      }
      if (traceAwardFocus.fundingOffice || traceAwardFocus.recipient) {
        window.clearTraceAwardFocus();
      }
    });

    document.body.addEventListener("click", function (event) {
      var clearBtn = event.target.closest("#insights-trace-focus-clear");
      if (!clearBtn) return;
      event.preventDefault();
      window.clearTraceAwardFocus();
    }, true);
  }

  mountOverlaysOnBody();
  bindInsightsChrome();
  if (document.readyState !== "loading") {
    initInsightsPage();
    scheduleSessionRestore();
  } else {
    document.addEventListener("DOMContentLoaded", function () {
      initInsightsPage();
      scheduleSessionRestore();
    });
  }
})();