(function () {
  var STORAGE_KEY = "thread-sidebar-collapsed";

  function initAppSidebar() {
    var sidebar = document.getElementById("app-sidebar");
    var toggle = document.getElementById("sidebar-collapse-toggle");
    if (!sidebar || !toggle) return;

    function apply(collapsed) {
      sidebar.classList.toggle("is-collapsed", collapsed);
      sidebar.setAttribute("aria-expanded", collapsed ? "false" : "true");
      toggle.setAttribute(
        "aria-label",
        collapsed ? "Expand application sidebar" : "Collapse application sidebar"
      );
      toggle.setAttribute("title", collapsed ? "Expand sidebar" : "Collapse sidebar");
      var icon = toggle.querySelector("[data-lucide]");
      if (icon) {
        icon.setAttribute("data-lucide", collapsed ? "panel-left-open" : "panel-left-close");
        if (window.lucide) window.lucide.createIcons();
      }
    }

    apply(localStorage.getItem(STORAGE_KEY) === "1");
    toggle.addEventListener("click", function () {
      var collapsed = !sidebar.classList.contains("is-collapsed");
      apply(collapsed);
      localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    });
  }

  function initVaultTreeNav() {
    var layout = document.getElementById("vault-browser-layout");
    var panel = document.getElementById("vault-tree-panel");
    var collapseBtn = document.getElementById("vault-tree-collapse-btn");
    var expandBtn = document.getElementById("vault-tree-expand-btn");
    if (!layout || !panel) return;

    var KEY = "thread-vault-tree-collapsed";

    function apply(collapsed) {
      layout.classList.toggle("is-tree-collapsed", collapsed);
      panel.setAttribute("aria-hidden", collapsed ? "true" : "false");
      if (collapseBtn) collapseBtn.hidden = collapsed;
      if (expandBtn) expandBtn.hidden = !collapsed;
    }

    apply(localStorage.getItem(KEY) === "1");
    if (collapseBtn) {
      collapseBtn.addEventListener("click", function () {
        apply(true);
        localStorage.setItem(KEY, "1");
      });
    }
    if (expandBtn) {
      expandBtn.addEventListener("click", function () {
        apply(false);
        localStorage.setItem(KEY, "0");
      });
    }
  }

  function init() {
    initAppSidebar();
    initVaultTreeNav();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  document.body.addEventListener("htmx:afterSwap", init);
})();