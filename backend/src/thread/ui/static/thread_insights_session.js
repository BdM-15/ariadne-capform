/**
 * Persist active Insights slice in localStorage; restore on /insights revisit.
 * Clew links from Insights save session + carry from=insights for back navigation.
 */
(function () {
  var SESSION_KEY = "insights-session-v1";

  function insightsForm() {
    return document.getElementById("insights-radar-form");
  }

  function entityState() {
    return document.getElementById("insights-entity-state");
  }

  window.persistInsightsSession = function () {
    var form = insightsForm();
    if (!form) return;
    var session = { run: 1, saved_at: Date.now() };
    new FormData(form).forEach(function (value, key) {
      if (value != null && String(value).length) session[key] = String(value);
    });
    var panel = document.getElementById("insights-slice-panel");
    if (panel && panel.getAttribute("data-active-lens")) {
      session.lens = panel.getAttribute("data-active-lens");
    }
    var lens = document.getElementById("insights-active-lens");
    if (lens && lens.value) session.lens = lens.value;
    var state = entityState();
    if (state) {
      new FormData(state).forEach(function (value, key) {
        if (value != null && String(value).length) session[key] = String(value);
      });
    }
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch (_) {}
  };

  function fillFormFromSession(session) {
    var form = insightsForm();
    if (!form || !session) return;
    Object.keys(session).forEach(function (key) {
      if (key === "lens" || key === "run" || key === "saved_at") return;
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
        if (value != null && String(value).length) params.append(key, String(value));
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
    var panel = document.getElementById("insights-slice-panel");
    if (panel && panel.getAttribute("data-has-slice") === "1") return;
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("run") === "1") return;

    var session = null;
    try {
      session = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
    } catch (_) {
      session = null;
    }
    if (!session || !session.run) return;

    window._insightsSessionRestored = true;
    fillFormFromSession(session);
    if (!window.htmx) return;

    window.htmx.ajax("GET", "/partials/insights/slice?" + sliceParamsFromSession(session).toString(), {
      target: "#insights-slice-panel",
      swap: "outerHTML",
    });
    var card = document.getElementById("insights-lenses-card");
    if (card) card.open = true;
  };

  function bindClewDepartLinks() {
    document.querySelectorAll("a.insights-clew-link, a[href*='/clew'][href*='from=insights']").forEach(function (anchor) {
      if (anchor.dataset.insightsClewBound) return;
      anchor.dataset.insightsClewBound = "1";
      anchor.addEventListener("click", function () {
        window.persistInsightsSession();
        var form = insightsForm();
        if (!form) return;
        try {
          var url = new URL(anchor.href, window.location.origin);
          new FormData(form).forEach(function (value, key) {
            if (value != null && String(value).length && !url.searchParams.has(key)) {
              url.searchParams.set(key, String(value));
            }
          });
          if (!url.searchParams.has("from")) url.searchParams.set("from", "insights");
          anchor.href = url.pathname + url.search;
        } catch (_) {}
      });
    });
  }

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (t.id === "insights-slice-panel" || (t.closest && t.closest("#insights-slice-panel"))) {
      window.persistInsightsSession();
    }
    bindClewDepartLinks();
  });

  document.addEventListener("DOMContentLoaded", function () {
    bindClewDepartLinks();
    window.restoreInsightsSessionIfIdle();
  });

  if (document.readyState !== "loading") {
    bindClewDepartLinks();
    window.restoreInsightsSessionIfIdle();
  }
})();