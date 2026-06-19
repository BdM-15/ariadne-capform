(function () {
  var drawer = function () {
    return document.getElementById("capture-fab-drawer");
  };
  var btn = function () {
    return document.getElementById("capture-fab-btn");
  };

  function readPulseWatchlistContext(params) {
    if (params.has("award_key") || params.has("opp_id") || params.has("entity")) return;
    var card = document.querySelector("[data-watchlist-award-key]");
    if (!card) return;
    if (card.dataset.watchlistAwardKey) params.set("award_key", card.dataset.watchlistAwardKey);
    if (card.dataset.watchlistTitle) params.set("signal_title", card.dataset.watchlistTitle);
    if (card.dataset.watchlistAgency) params.set("agency", card.dataset.watchlistAgency);
  }

  function captureFabQuery() {
    var body = document.body;
    var params = new URLSearchParams();
    if (body.dataset.captureOppId) params.set("opp_id", body.dataset.captureOppId);
    if (body.dataset.captureOppName) params.set("opp_name", body.dataset.captureOppName);
    if (body.dataset.captureAwardKey) params.set("award_key", body.dataset.captureAwardKey);
    if (body.dataset.captureSignalTitle) params.set("signal_title", body.dataset.captureSignalTitle);
    if (body.dataset.captureAgency) params.set("agency", body.dataset.captureAgency);
    if (body.dataset.captureEntity) params.set("entity", body.dataset.captureEntity);
    if (body.dataset.captureEntityTitle) params.set("entity_title", body.dataset.captureEntityTitle);
    readPulseWatchlistContext(params);
    return params.toString();
  }

  function setOpen(open) {
    var d = drawer();
    var b = btn();
    if (!d || !b) return;
    d.classList.toggle("capture-fab-hidden", !open);
    d.setAttribute("aria-hidden", open ? "false" : "true");
    b.setAttribute("aria-expanded", open ? "true" : "false");
    document.body.classList.toggle("capture-fab-open", open);
    if (open && window.lucide) window.lucide.createIcons();
  }

  function reloadDrawer() {
    var d = drawer();
    if (!d) return;
    var qs = captureFabQuery();
    var url = "/partials/capture/fab" + (qs ? "?" + qs : "");
    if (window.htmx) {
      window.htmx.ajax("GET", url, { target: "#capture-fab-drawer", swap: "innerHTML" });
      setOpen(true);
      return;
    }
    fetch(url, { headers: { Accept: "text/html" } })
      .then(function (res) {
        if (!res.ok) throw new Error("Failed to load capture drawer");
        return res.text();
      })
      .then(function (html) {
        d.innerHTML = html;
        setOpen(true);
        if (window.htmx) window.htmx.process(d);
        if (window.lucide) window.lucide.createIcons();
      });
  }

  function loadDrawer() {
    var d = drawer();
    if (!d) return;
    var qs = captureFabQuery();
    var url = "/partials/capture/fab" + (qs ? "?" + qs : "");
    fetch(url, { headers: { Accept: "text/html" } })
      .then(function (res) {
        if (!res.ok) throw new Error("Failed to load capture drawer");
        return res.text();
      })
      .then(function (html) {
        d.innerHTML = html;
        setOpen(true);
        if (window.htmx) window.htmx.process(d);
        if (window.lucide) window.lucide.createIcons();
      })
      .catch(function () {
        window.alert("Could not open quick capture.");
      });
  }

  function bindFab() {
    var b = btn();
    if (!b || b.dataset.captureFabBound) return;
    b.dataset.captureFabBound = "1";
    b.addEventListener("click", function () {
      var d = drawer();
      if (d && !d.classList.contains("capture-fab-hidden") && d.innerHTML.trim()) {
        setOpen(false);
        return;
      }
      loadDrawer();
    });
  }

  function bindClose() {
    document.addEventListener("click", function (event) {
      if (event.target.closest("[data-capture-fab-reload]")) {
        event.preventDefault();
        reloadDrawer();
        return;
      }
      if (event.target.closest("[data-capture-fab-close]")) {
        event.preventDefault();
        setOpen(false);
        return;
      }
      var root = document.getElementById("capture-fab-root");
      var b = btn();
      if (!root || !b) return;
      var d = drawer();
      if (!d || d.classList.contains("capture-fab-hidden")) return;
      if (root.contains(event.target)) return;
      setOpen(false);
    });
  }

  function bindCaptureFormEncoding() {
    document.body.addEventListener("htmx:configRequest", function (event) {
      var elt = event.detail && event.detail.elt;
      if (!elt || elt.id !== "capture-fab-form") return;
      var fileInput = document.getElementById("capture-fab-file");
      var hasFile =
        fileInput &&
        fileInput.files &&
        fileInput.files.length > 0 &&
        fileInput.files[0] &&
        fileInput.files[0].size > 0;
      if (hasFile) {
        event.detail.headers["Content-Type"] = undefined;
      }
    });

    document.body.addEventListener("htmx:beforeRequest", function (event) {
      var elt = event.detail && event.detail.elt;
      if (!elt || elt.id !== "capture-fab-form") return;
      var fileInput = document.getElementById("capture-fab-file");
      var hasFile =
        fileInput &&
        fileInput.files &&
        fileInput.files.length > 0 &&
        fileInput.files[0] &&
        fileInput.files[0].size > 0;
      if (hasFile) {
        elt.setAttribute("hx-encoding", "multipart/form-data");
        elt.setAttribute("enctype", "multipart/form-data");
      } else {
        elt.removeAttribute("hx-encoding");
        elt.removeAttribute("enctype");
      }
    });

    document.body.addEventListener("htmx:responseError", function (event) {
      var elt = event.detail && event.detail.elt;
      if (!elt || elt.id !== "capture-fab-form") return;
      var status = event.detail.xhr && event.detail.xhr.status;
      window.alert(
        "Quick capture failed" + (status ? " (HTTP " + status + ")" : "") + ". Check server logs.",
      );
    });
  }

  function init() {
    bindFab();
    bindClose();
    bindCaptureFormEncoding();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  function refreshVaultInboxFromFabLink() {
    var mount = document.getElementById("knowledge-capture-studio-mount");
    var link = document.querySelector(".capture-fab-studio-link");
    if (!mount || !link || !window.htmx || window.location.pathname !== "/knowledge") return;
    var href = link.getAttribute("href") || "";
    var inboxMatch = href.match(/[?&]inbox=([^&#]+)/);
    var url =
      "/partials/knowledge/capture-studio" + (inboxMatch ? "?inbox=" + inboxMatch[1] : "");
    window.htmx.ajax("GET", url, { target: "#knowledge-capture-studio-mount", swap: "innerHTML" });
  }

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail && event.detail.target && event.detail.target.id === "capture-fab-drawer") {
      if (window.lucide) window.lucide.createIcons();
      if (document.querySelector(".capture-fab-flash-kicker")) {
        refreshVaultInboxFromFabLink();
      }
    }
  });
})();