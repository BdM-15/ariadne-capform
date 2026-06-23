(function () {
  function root() {
    return document.getElementById("insights-award-drawer-root");
  }
  function body() {
    return document.getElementById("insights-award-drawer-body");
  }

  function drawerOpen() {
    var r = root();
    return r && !r.classList.contains("task-drawer-hidden");
  }

  function syncTitle() {
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

  function showDrawerError(message) {
    var b = body();
    if (!b) return;
    b.innerHTML =
      '<div class="p-4 space-y-2">' +
      '<p class="text-neon-amber text-xs font-semibold">Could not load award profile.</p>' +
      '<p class="text-[11px] text-slate-500 font-mono">' +
      message +
      "</p>" +
      '<p class="text-[10px] text-slate-600">Restart <code class="font-mono">python app.py</code> after pull if you see HTTP 404.</p>' +
      "</div>";
  }

  function afterDrawerSwap() {
    if (window.initInsightsHone) window.initInsightsHone();
    if (window.lucide) window.lucide.createIcons();
    if (window.persistInsightsSession) window.persistInsightsSession();
    document.querySelectorAll("a.insights-clew-link").forEach(function (anchor) {
      if (window.enhanceInsightsClewHref) window.enhanceInsightsClewHref(anchor);
    });
    syncTitle();
  }

  window.openInsightsAwardDrawer = function (awardKey) {
    awardKey = (awardKey || "").trim();
    if (!awardKey) {
      showDrawerError("No award key on this row — run slice again to refresh cached expiring data.");
      var r0 = root();
      if (r0) {
        r0.classList.remove("task-drawer-hidden");
        r0.setAttribute("aria-hidden", "false");
        document.body.classList.add("task-drawer-open");
      }
      return;
    }
    var r = root();
    var b = body();
    if (!r || !b) {
      showDrawerError("Contract drawer shell missing — hard refresh /insights (Ctrl+Shift+R).");
      return;
    }
    if (window.persistInsightsSession) window.persistInsightsSession();
    r.classList.remove("task-drawer-hidden");
    r.setAttribute("aria-hidden", "false");
    document.body.classList.add("task-drawer-open");
    b.innerHTML = '<p class="insights-idle-hint p-4 text-neon-cyan">Loading contract profile…</p>';
    fetch("/partials/insights/award?award_key=" + encodeURIComponent(awardKey), {
      headers: { Accept: "text/html" },
      credentials: "same-origin",
    })
      .then(function (res) {
        return res.text().then(function (html) {
          if (!res.ok) {
            throw new Error("HTTP " + res.status + (html ? " — " + html.slice(0, 120) : ""));
          }
          return html;
        });
      })
      .then(function (html) {
        b.innerHTML = html;
        afterDrawerSwap();
      })
      .catch(function (err) {
        showDrawerError(err && err.message ? err.message : "Network error");
      });
  };

  window.closeInsightsAwardDrawer = function () {
    var r = root();
    if (!r) return;
    r.classList.add("task-drawer-hidden");
    r.setAttribute("aria-hidden", "true");
    document.body.classList.remove("task-drawer-open");
    if (window.persistInsightsSession) window.persistInsightsSession();
  };

  document.body.addEventListener("click", function (event) {
    var profileBtn = event.target.closest("[data-insights-award-key]");
    if (profileBtn) {
      event.preventDefault();
      event.stopPropagation();
      var profileKey = profileBtn.getAttribute("data-insights-award-key");
      if (profileKey) window.openInsightsAwardDrawer(profileKey);
      return;
    }
    var row = event.target.closest("[data-insights-award-open]");
    if (!row) return;
    if (event.target.closest("button, a, form")) return;
    var rowKey = row.getAttribute("data-award-key");
    if (rowKey) window.openInsightsAwardDrawer(rowKey);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && drawerOpen()) closeInsightsAwardDrawer();
  });
})();