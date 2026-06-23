/**
 * Insights page chrome — loading status, facet helpers, HTMX reprocess.
 */
(function () {
  var SLICE_TARGET = "#insights-stage-content";

  function stageStatusEl() {
    return document.getElementById("insights-slice-loading");
  }

  function setStageStatus(message, kind) {
    var el = stageStatusEl();
    if (!el) return;
    el.textContent = message || "";
    el.classList.remove("is-error", "is-loading");
    if (kind === "error") el.classList.add("is-error");
    if (kind === "loading") el.classList.add("is-loading");
  }

  function setSliceLoading(active, message) {
    var banner = stageStatusEl();
    var stage = document.getElementById("insights-stage-content");
    if (banner) {
      banner.textContent = message || "";
      banner.classList.toggle("is-loading", !!active);
    }
    if (stage) stage.classList.toggle("is-loading", !!active);
  }

  window.showInsightsSliceLoading = function (message) {
    setSliceLoading(true, message || "Loading…");
  };

  window.clearInsightsSliceLoading = function () {
    setSliceLoading(false, "");
    document.querySelectorAll(".insights-drill-chip.is-loading").forEach(function (el) {
      el.classList.remove("is-loading");
    });
  };

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

  function bindClearSlice() {
    var btn = document.getElementById("insights-clear-btn");
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", function () {
      if (window.clearInsightsExplore) {
        window.clearInsightsExplore();
        return;
      }
      var form = document.getElementById("insights-radar-form");
      if (!form) return;
      form.querySelectorAll("input[type='text'], input:not([type='hidden'])").forEach(function (input) {
        if (input.name && input.name !== "run") input.value = "";
      });
      var lens = document.getElementById("insights-active-lens");
      if (lens) lens.value = "overview";
    });
  }

  function bindRunSliceReset() {
    var form = document.getElementById("insights-radar-form");
    if (!form || form.dataset.runResetBound) return;
    form.dataset.runResetBound = "1";
    form.addEventListener("submit", function () {
      var lens = document.getElementById("insights-active-lens");
      if (lens) lens.value = "overview";
      setStageStatus("Running slice… PostgreSQL query may take 30–90 seconds.", "loading");
      var body = document.getElementById("insights-lens-body");
      if (body) {
        body.innerHTML = '<p class="insights-lens-loading">Querying intel tables…</p>';
      }
    });
  }

  function processInsightsForm() {
    if (!window.htmx) return;
    var form = document.getElementById("insights-radar-form");
    if (form) window.htmx.process(form);
    var stage = document.getElementById("insights-stage-content");
    if (stage) window.htmx.process(stage);
  }

  function initInsightsPage() {
    bindNaicsChips();
    bindClearSlice();
    bindRunSliceReset();
    processInsightsForm();
    if (window.initClewCharts) window.initClewCharts();
    if (window.initInsightsHone) window.initInsightsHone();
    if (window.lucide) window.lucide.createIcons();
  }

  window.initInsightsPage = initInsightsPage;

  function isSliceRequest(e) {
    var cfg = e.detail && e.detail.requestConfig;
    var target = cfg && cfg.target;
    var elt = e.detail && e.detail.elt;
    return (
      target === SLICE_TARGET ||
      target === "insights-stage-content" ||
      (elt && elt.id === "insights-radar-form")
    );
  }

  document.body.addEventListener(
    "htmx:beforeRequest",
    function (e) {
      if (!isSliceRequest(e)) return;
      var elt = e.detail && e.detail.elt;
      if (elt && elt.id === "insights-radar-form") return;
      var msg = "Loading lens results…";
      if (elt && elt.classList && elt.classList.contains("insights-lens-tab")) {
        msg = "Switching to " + (elt.textContent || "lens").trim() + "…";
      } else if (elt && elt.classList && elt.classList.contains("insights-drill-chip")) {
        msg = "Opening profile…";
      }
      setStageStatus(msg, "loading");
    },
    true
  );

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (
      t.id === "insights-stage-content" ||
      t.id === "insights-body" ||
      (t.closest && t.closest("#insights-stage-content"))
    ) {
      setStageStatus("", "");
      var stage = document.getElementById("insights-stage-content");
      var lensInput = document.getElementById("insights-active-lens");
      if (lensInput && stage && stage.dataset.activeLens) {
        lensInput.value = stage.dataset.activeLens;
      }
      if (window.persistInsightsSession) window.persistInsightsSession();
      initInsightsPage();
    }
  });

  document.body.addEventListener("htmx:responseError", function (e) {
    if (!isSliceRequest(e)) return;
    var status = e.detail.xhr && e.detail.xhr.status;
    setStageStatus(
      "Slice request failed" + (status ? " (HTTP " + status + ")" : "") + ". Check server logs or retry.",
      "error"
    );
    var body = document.getElementById("insights-lens-body");
    if (body) {
      body.innerHTML =
        '<p class="insights-stage-status is-error">Slice failed' +
        (status ? " (HTTP " + status + ")" : "") +
        ". Server error — restart backend if this persists.</p>";
    }
    if (window.clearInsightsSliceLoading) window.clearInsightsSliceLoading();
  });

  document.body.addEventListener("htmx:sendError", function (e) {
    if (!isSliceRequest(e)) return;
    setStageStatus("Network error — could not reach server.", "error");
  });

  if (document.readyState !== "loading") initInsightsPage();
  else document.addEventListener("DOMContentLoaded", initInsightsPage);
})();