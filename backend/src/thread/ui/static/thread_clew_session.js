/**
 * Persist Clew facet form + last run in localStorage; restore on bare /clew revisit.
 */
(function () {
  var SESSION_KEY = "clew-session-v1";

  function clewForm() {
    return document.getElementById("clew-facet-form");
  }

  function clewMode() {
    return document.getElementById("clew-mode");
  }

  function clewMcpToggle() {
    return document.querySelector('#clew-mcp-toggle input[name="include_mcp"]');
  }

  function resultsIdle() {
    var panel = document.getElementById("clew-results-panel");
    if (!panel) return true;
    return panel.textContent.indexOf("Set search facets in the form above") >= 0;
  }

  window.persistClewSession = function () {
    var form = clewForm();
    if (!form) return;
    var session = { run: 1, saved_at: Date.now() };
    new FormData(form).forEach(function (value, key) {
      if (value != null && String(value).length) session[key] = String(value);
    });
    var mode = clewMode();
    if (mode && mode.value) session.mode = mode.value;
    var mcp = clewMcpToggle();
    if (mcp && mcp.checked) session.include_mcp = "1";
    try {
      localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch (_) {}
  };

  function fillFormFromSession(session) {
    var form = clewForm();
    if (!form || !session) return;
    Object.keys(session).forEach(function (key) {
      if (key === "run" || key === "saved_at" || key === "mode" || key === "include_mcp") return;
      var input = form.querySelector('[name="' + key + '"]');
      if (input) input.value = session[key];
    });
    var mode = clewMode();
    if (mode && session.mode) mode.value = session.mode;
    var mcp = clewMcpToggle();
    if (mcp) mcp.checked = session.include_mcp === "1";
  }

  function resultsParamsFromSession(session) {
    var params = new URLSearchParams();
    params.set("run", "1");
    var form = clewForm();
    if (form) {
      new FormData(form).forEach(function (value, key) {
        if (value != null && String(value).length) params.append(key, String(value));
      });
    }
    if (session.mode && !params.has("mode")) params.set("mode", session.mode);
    if (session.include_mcp === "1") params.set("include_mcp", "1");
    return params;
  }

  window.restoreClewSessionIfIdle = function () {
    if (window._clewSessionRestored) return;
    if (window.location.pathname !== "/clew") return;
    if (!resultsIdle()) return;

    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("run") === "1") return;
    var handoffKeys = ["recipient", "agency", "sub_agency", "naics_codes", "psc_codes", "mode", "path"];
    var hasHandoff = handoffKeys.some(function (key) {
      return (urlParams.get(key) || "").trim().length > 0;
    });
    if (hasHandoff) return;

    var session = null;
    try {
      session = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
    } catch (_) {
      session = null;
    }
    if (!session || !session.run) return;
    if (!window.htmx) return;

    window._clewSessionRestored = true;
    fillFormFromSession(session);
    window.htmx.ajax("GET", "/partials/clew/results?" + resultsParamsFromSession(session).toString(), {
      target: "#clew-results-panel",
      swap: "innerHTML",
    });
  };

  function scheduleClewRestore() {
    var attempts = 0;
    function attempt() {
      if (window._clewSessionRestored) return;
      if (window.location.pathname !== "/clew") return;
      if (window.htmx) {
        window.restoreClewSessionIfIdle();
        return;
      }
      attempts += 1;
      if (attempts < 40) window.setTimeout(attempt, 50);
    }
    attempt();
  }

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var t = e.detail && e.detail.target;
    if (!t) return;
    if (t.id === "clew-results-panel" || (t.closest && t.closest("#clew-results-panel"))) {
      window.persistClewSession();
    }
  });

  document.body.addEventListener(
    "click",
    function (event) {
      var anchor = event.target.closest("a");
      if (!anchor || !anchor.href) return;
      try {
        var url = new URL(anchor.href, window.location.origin);
        if (url.pathname === "/clew") return;
        if (window.location.pathname !== "/clew") return;
        window.persistClewSession();
      } catch (_) {}
    },
    true
  );

  var form = clewForm();
  if (form) {
    form.addEventListener("change", function () {
      window.persistClewSession();
    });
  }

  document.addEventListener("DOMContentLoaded", scheduleClewRestore);
  if (document.readyState !== "loading") scheduleClewRestore();
})();