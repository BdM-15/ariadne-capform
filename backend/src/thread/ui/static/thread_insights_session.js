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

  function isInsightsClewLink(anchor) {
    if (!anchor || anchor.tagName !== "A") return false;
    if (anchor.classList.contains("insights-clew-link")) return true;
    try {
      var href = anchor.getAttribute("href") || "";
      return href.indexOf("/clew") >= 0 && href.indexOf("from=insights") >= 0;
    } catch (_) {
      return false;
    }
  }

  window.enhanceInsightsClewHref = function (anchor) {
    if (!isInsightsClewLink(anchor)) return;
    var form = insightsForm();
    if (!form) return;
    try {
      var url = new URL(anchor.href, window.location.origin);
      new FormData(form).forEach(function (value, key) {
        if (value != null && String(value).length && !url.searchParams.has(key)) {
          url.searchParams.set(key, String(value));
        }
      });
      var state = entityState();
      if (state) {
        new FormData(state).forEach(function (value, key) {
          if (value != null && String(value).length && !url.searchParams.has(key)) {
            url.searchParams.set(key, String(value));
          }
        });
      }
      if (!url.searchParams.has("from")) url.searchParams.set("from", "insights");
      anchor.href = url.pathname + url.search;
    } catch (_) {}
  };

  window.persistInsightsSession = function () {
    var form = insightsForm();
    if (!form) return;
    var session = { run: 1, saved_at: Date.now() };
    new FormData(form).forEach(function (value, key) {
      if (value != null && String(value).length) session[key] = String(value);
    });
    var stage = document.getElementById("insights-stage-content");
    if (stage && stage.getAttribute("data-active-lens")) {
      session.lens = stage.getAttribute("data-active-lens");
    }
    var lens = document.getElementById("insights-active-lens");
    if (lens && lens.value) session.lens = lens.value;
    var state = entityState();
    if (state) {
      new FormData(state).forEach(function (value, key) {
        if (value != null && String(value).length) session[key] = String(value);
      });
    }
    var drawer = document.getElementById("insights-award-panel");
    if (drawer && drawer.getAttribute("data-award-key")) {
      session.award_key = drawer.getAttribute("data-award-key");
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
    var stage = document.getElementById("insights-stage-content");
    if (stage && stage.getAttribute("data-has-slice") === "1") return;
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("run") === "1") return;

    var session = null;
    try {
      session = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
    } catch (_) {
      session = null;
    }
    if (!session || !session.run) return;
    if (!window.htmx) return;

    window._insightsSessionRestored = true;
    fillFormFromSession(session);
    window.htmx.ajax("GET", "/partials/insights/slice?" + sliceParamsFromSession(session).toString(), {
      target: "#insights-stage-content",
      swap: "outerHTML",
    });
    var card = document.getElementById("insights-lenses-card");
    if (card) card.open = true;
  };

  var FACET_FIELDS = [
    "agency",
    "sub_agency",
    "recipient",
    "naics_codes",
    "psc_codes",
    "awarding_office",
    "funding_office",
    "recipient_uei",
    "pop_state",
    "extent_competed",
    "type_of_set_aside",
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
        '<nav id="insights-lens-tabs" class="insights-lens-tabs insights-lens-tabs-hidden" role="tablist" aria-label="Insights lenses"></nav>' +
        '<div id="insights-slice-panel" class="insights-slice-panel">' +
        '<div id="insights-lens-body" class="insights-lens-body insights-lens-idle">' +
        '<p class="insights-idle-hint">Set facets in the slice navigator, then <strong>Run slice</strong>. Lens tabs activate after the first query.</p>' +
        "</div></div></div>";
    }
    var card = document.getElementById("insights-lenses-card");
    if (card) card.open = true;
  };

  function scheduleInsightsRestore() {
    var attempts = 0;
    function attempt() {
      if (window._insightsSessionRestored) return;
      if (window.location.pathname !== "/insights") return;
      if (window.htmx && window.initInsightsHone) {
        window.restoreInsightsSessionIfIdle();
        return;
      }
      attempts += 1;
      if (attempts < 40) window.setTimeout(attempt, 50);
    }
    attempt();
  }

  document.body.addEventListener(
    "click",
    function (event) {
      var anchor = event.target.closest("a");
      if (!isInsightsClewLink(anchor)) return;
      window.persistInsightsSession();
      window.enhanceInsightsClewHref(anchor);
    },
    true
  );

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (t.id === "insights-stage-content" || (t.closest && t.closest("#insights-stage-content"))) {
      window.persistInsightsSession();
    }
  });

  function bindClearButton() {
    var btn = document.getElementById("insights-clear-btn");
    if (!btn || btn.dataset.insightsClearBound) return;
    btn.dataset.insightsClearBound = "1";
    btn.addEventListener("click", function () {
      window.clearInsightsExplore();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    scheduleInsightsRestore();
    bindClearButton();
  });
  if (document.readyState !== "loading") {
    scheduleInsightsRestore();
    bindClearButton();
  }

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (t.id === "insights-body" || (t.closest && t.closest("#insights-body"))) {
      bindClearButton();
    }
  });
})();