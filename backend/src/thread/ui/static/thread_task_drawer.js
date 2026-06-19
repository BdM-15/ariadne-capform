(function () {
  var root = function () {
    return document.getElementById("task-drawer-root");
  };
  var body = function () {
    return document.getElementById("task-drawer-body");
  };

  window._openTaskDrawerId = null;

  function drawerOpen() {
    var r = root();
    return r && !r.classList.contains("task-drawer-hidden");
  }

  function drawerUrl(taskId) {
    var params = new URLSearchParams(window.location.search);
    var filter = params.get("filter") || "open";
    var view = params.get("view") || "board";
    return (
      "/partials/tasks/" +
      encodeURIComponent(taskId) +
      "/drawer?filter=" +
      encodeURIComponent(filter) +
      "&view=" +
      encodeURIComponent(view)
    );
  }

  function syncDrawerTitle() {
    var panel = document.getElementById("task-drawer-panel");
    var titleEl = document.getElementById("task-drawer-title");
    var heading = panel && panel.querySelector(".task-drawer-task-title");
    if (titleEl && heading) titleEl.textContent = heading.textContent.trim();
  }

  function loadDrawerContent(taskId) {
    var b = body();
    if (!b) return;
    b.innerHTML = '<p class="insights-idle-hint p-4">Loading task…</p>';
    fetch(drawerUrl(taskId), { headers: { Accept: "text/html" } })
      .then(function (res) {
        if (!res.ok) {
          throw new Error("HTTP " + res.status);
        }
        return res.text();
      })
      .then(function (html) {
        b.innerHTML = html;
        if (window.lucide) window.lucide.createIcons();
        syncDrawerTitle();
      })
      .catch(function () {
        b.innerHTML =
          '<div class="p-4 space-y-2">' +
          '<p class="text-neon-amber text-xs font-semibold">Could not load task workspace.</p>' +
          '<p class="text-[11px] text-slate-500">Restart <code class="font-mono">python app.py</code> after pull. If persists, check server log for migration errors (work_log column).</p>' +
          "</div>";
      });
  }

  window.openTaskDrawer = function (taskId) {
    if (!taskId) return;
    var r = root();
    if (!r) return;

    window._openTaskDrawerId = String(taskId);
    r.classList.remove("task-drawer-hidden");
    r.setAttribute("aria-hidden", "false");
    document.body.classList.add("task-drawer-open");
    loadDrawerContent(taskId);

    if (history.replaceState) {
      var next = new URL(window.location.href);
      next.searchParams.set("task", taskId);
      history.replaceState({}, "", next);
    }
  };

  window.closeTaskDrawer = function () {
    var r = root();
    if (!r) return;
    r.classList.add("task-drawer-hidden");
    r.setAttribute("aria-hidden", "true");
    document.body.classList.remove("task-drawer-open");
    window._openTaskDrawerId = null;

    if (history.replaceState) {
      var next = new URL(window.location.href);
      next.searchParams.delete("task");
      history.replaceState({}, "", next);
    }
  };

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && drawerOpen()) {
      closeTaskDrawer();
    }
  });

  document.body.addEventListener("htmx:afterSwap", function (evt) {
    if (!evt.detail || !evt.detail.target) return;
    if (evt.detail.target.id === "tasks-body" && window._openTaskDrawerId) {
      loadDrawerContent(window._openTaskDrawerId);
    }
    if (evt.detail.target.id === "task-drawer-body") {
      if (window.lucide) window.lucide.createIcons();
      syncDrawerTitle();
    }
  });
})();