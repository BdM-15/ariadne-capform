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
    el.classList.remove("is-error", "is-loading");
    if (kind === "error") el.classList.add("is-error");
    if (kind === "loading") el.classList.add("is-loading");
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
    var root = document.getElementById("insights-bookmarks-drawer-root");
    if (!root) return;
    root.classList.remove("insights-drawer-hidden");
    root.setAttribute("aria-hidden", "false");
    if (window.lucide) window.lucide.createIcons();
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
    var form = insightsForm();
    if (!form) return;
    var session = { run: 1, saved_at: Date.now() };
    new FormData(form).forEach(function (value, key) {
      if (value) session[key] = String(value);
    });
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
    ["entity_kind", "entity_value", "entity_scope"].forEach(function (key) {
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

  function mountOverlaysOnBody() {
    var r = awardRoot();
    if (r && r.parentElement !== document.body) document.body.appendChild(r);
    var bookmarks = document.getElementById("insights-bookmarks-drawer-root");
    if (bookmarks && bookmarks.parentElement !== document.body) document.body.appendChild(bookmarks);
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
      var btn = event.target.closest("button.insights-award-open[data-award-key]");
      var row = event.target.closest("li.insights-result-row.insights-award-open[data-award-key]");
      var key = "";
      if (btn) key = btn.getAttribute("data-award-key") || "";
      else if (row && !event.target.closest(".insights-result-actions")) key = row.getAttribute("data-award-key") || "";
      key = key.trim();
      if (!key) return;
      event.preventDefault();
      window.openInsightsAwardDrawer(key);
    }, true);

    document.body.addEventListener("htmx:beforeRequest", function (e) {
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
      clearLoadingStatus();
      var stage = document.getElementById("insights-stage-content");
      var lensInput = document.getElementById("insights-active-lens");
      if (lensInput && stage && stage.dataset.activeLens) lensInput.value = stage.dataset.activeLens;
      window.persistInsightsSession();
      initInsightsPage();
      if (t.id === "insights-body") bindClearButton();
    });

    document.body.addEventListener("htmx:responseError", function (e) {
      if (!isSliceRequest(e)) return;
      var status = e.detail.xhr && e.detail.xhr.status;
      setStageStatus("Slice request failed" + (status ? " (HTTP " + status + ")" : "") + ".", "error");
      clearLoadingStatus();
    });

    document.body.addEventListener("htmx:sendError", function (e) {
      if (!isSliceRequest(e)) return;
      setStageStatus("Network error — could not reach server.", "error");
    });

    document.addEventListener("keydown", function (e) {
      var r = awardRoot();
      if (e.key === "Escape" && r && !r.classList.contains("task-drawer-hidden")) {
        window.closeInsightsAwardDrawer();
      }
    });
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