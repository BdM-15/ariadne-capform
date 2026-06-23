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

  function bindAwardRowClicks() {
    document.querySelectorAll("[data-insights-award-open]").forEach(function (el) {
      if (el.dataset.awardOpenBound) return;
      el.dataset.awardOpenBound = "1";
      el.addEventListener("click", function (event) {
        if (event.target.closest("button, a, form")) return;
        var key = el.getAttribute("data-award-key");
        if (key) window.openInsightsAwardDrawer(key);
      });
    });
    document.querySelectorAll("[data-insights-award-key]").forEach(function (btn) {
      if (btn.dataset.awardOpenBound) return;
      btn.dataset.awardOpenBound = "1";
      btn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        var key = btn.getAttribute("data-insights-award-key");
        if (key) window.openInsightsAwardDrawer(key);
      });
    });
  }

  function afterDrawerSwap() {
    if (window.initInsightsHone) window.initInsightsHone();
    if (window.lucide) window.lucide.createIcons();
    syncTitle();
  }

  window.openInsightsAwardDrawer = function (awardKey) {
    if (!awardKey) return;
    var r = root();
    var b = body();
    if (!r || !b) return;
    r.classList.remove("task-drawer-hidden");
    r.setAttribute("aria-hidden", "false");
    document.body.classList.add("task-drawer-open");
    b.innerHTML = '<p class="insights-idle-hint p-4 text-neon-cyan">Loading contract profile…</p>';
    fetch("/partials/insights/award?award_key=" + encodeURIComponent(awardKey), {
      headers: { Accept: "text/html" },
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.text();
      })
      .then(function (html) {
        b.innerHTML = html;
        afterDrawerSwap();
      })
      .catch(function () {
        b.innerHTML =
          '<div class="p-4 space-y-2"><p class="text-neon-amber text-xs font-semibold">Could not load award profile.</p></div>';
      });
  };

  window.closeInsightsAwardDrawer = function () {
    var r = root();
    if (!r) return;
    r.classList.add("task-drawer-hidden");
    r.setAttribute("aria-hidden", "true");
    document.body.classList.remove("task-drawer-open");
  };

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && drawerOpen()) closeInsightsAwardDrawer();
  });

  document.body.addEventListener("htmx:afterSwap", function () {
    bindAwardRowClicks();
  });

  bindAwardRowClicks();
})();