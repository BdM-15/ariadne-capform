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
    if (!d) return;
    var b = btn();
    d.classList.toggle("capture-fab-hidden", !open);
    d.setAttribute("aria-hidden", open ? "false" : "true");
    if (b) b.setAttribute("aria-expanded", open ? "true" : "false");
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

  function setHeaderMode(on) {
    var root = document.getElementById("capture-fab-root");
    var backdrop = document.getElementById("capture-fab-header-backdrop");
    if (!root) return;
    root.classList.toggle("capture-fab-header-mode", !!on);
    document.body.classList.toggle("capture-fab-header-mode", !!on);
    if (backdrop) {
      backdrop.classList.toggle("capture-fab-hidden", !on);
      backdrop.setAttribute("aria-hidden", on ? "false" : "true");
    }
  }

  function loadDrawer(opts) {
    var d = drawer();
    if (!d) {
      window.alert("Capture UI missing — hard refresh (Ctrl+Shift+R) and retry.");
      return;
    }
    var fromHeader = opts && opts.fromHeader;
    setHeaderMode(fromHeader);
    d.innerHTML =
      '<div class="capture-fab-drawer-inner p-4 text-xs text-slate-400 font-mono">Opening capture…</div>';
    setOpen(true);
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
        setHeaderMode(false);
        window.alert("Could not open quick capture.");
      });
  }

  window.openCaptureFab = function (fromHeader) {
    loadDrawer({ fromHeader: !!fromHeader });
  };

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
        setHeaderMode(false);
        setOpen(false);
        return;
      }
      if (event.target.id === "capture-fab-header-backdrop") {
        setHeaderMode(false);
        setOpen(false);
        return;
      }
      var root = document.getElementById("capture-fab-root");
      var b = btn();
      if (!root || !b) return;
      var d = drawer();
      if (!d || d.classList.contains("capture-fab-hidden")) return;
      if (root.contains(event.target)) return;
      if (event.target.closest("[data-capture-fab-open]")) return;
      if (event.target.closest("#capture-fab-btn")) return;
      setHeaderMode(false);
      setOpen(false);
    });
  }

  var CAPTURE_ACCEPT = /\.(pdf|png|jpe?g|bmp|tiff?|webp|docx?|pptx?|xlsx?|html?|epub|mobi|txt|md|markdown)$/i;

  function formatFileSize(bytes) {
    if (!bytes) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function setCaptureFileHint(message, visible) {
    var hint = document.getElementById("capture-fab-file-hint");
    if (!hint) return;
    hint.textContent = message || "";
    hint.classList.toggle("capture-fab-hidden", !visible);
  }

  var captureDragDepth = 0;

  function captureDropzoneEl() {
    return document.querySelector("[data-capture-dropzone]");
  }

  function updateStagedFilePreview(file) {
    var staged = document.getElementById("capture-fab-staged");
    var empty = document.getElementById("capture-fab-dropzone-empty");
    var nameEl = document.getElementById("capture-fab-staged-name");
    var sizeEl = document.getElementById("capture-fab-staged-size");
    var dropzone = captureDropzoneEl();
    if (!staged || !nameEl || !sizeEl || !empty) return;
    if (!file) {
      staged.classList.add("capture-fab-hidden");
      empty.classList.remove("capture-fab-hidden");
      if (dropzone) dropzone.classList.remove("has-file", "is-dragover");
      nameEl.textContent = "";
      sizeEl.textContent = "";
      setCaptureFileHint("", false);
      return;
    }
    staged.classList.remove("capture-fab-hidden");
    empty.classList.add("capture-fab-hidden");
    if (dropzone) dropzone.classList.add("has-file");
    nameEl.textContent = file.name;
    sizeEl.textContent = formatFileSize(file.size);
    setCaptureFileHint("", false);
    if (window.lucide) window.lucide.createIcons();
  }

  function assignCaptureFile(file) {
    var fileInput = document.getElementById("capture-fab-file");
    if (!fileInput || !file) return false;
    if (!CAPTURE_ACCEPT.test(file.name)) {
      setCaptureFileHint("Unsupported type — use PDF, Office, images, epub, or .txt/.md", true);
      return false;
    }
    try {
      var dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
    } catch (err) {
      setCaptureFileHint("Use “browse files” to pick this document.", true);
      return false;
    }
    updateStagedFilePreview(file);
    return true;
  }

  function clearCaptureFile() {
    var fileInput = document.getElementById("capture-fab-file");
    if (fileInput) fileInput.value = "";
    updateStagedFilePreview(null);
  }

  function openCaptureFilePicker() {
    var fileInput = document.getElementById("capture-fab-file");
    if (fileInput) fileInput.click();
  }

  function handleCaptureDrop(event) {
    var dropzone = captureDropzoneEl();
    if (!dropzone) return;
    captureDragDepth = 0;
    dropzone.classList.remove("is-dragover");
    var files = event.dataTransfer && event.dataTransfer.files;
    if (!files || !files.length) {
      setCaptureFileHint("Drop a file, not a folder.", true);
      return;
    }
    if (files.length > 1) {
      setCaptureFileHint("One file at a time — using the first.", true);
    }
    assignCaptureFile(files[0]);
  }

  function bindCaptureUploadDelegation() {
    if (document.body.dataset.captureUploadDelegate) return;
    document.body.dataset.captureUploadDelegate = "1";

    document.addEventListener(
      "dragenter",
      function (event) {
        if (!event.target.closest("[data-capture-dropzone]")) return;
        event.preventDefault();
        captureDragDepth += 1;
        var dropzone = captureDropzoneEl();
        if (dropzone) dropzone.classList.add("is-dragover");
      },
      false,
    );

    document.addEventListener(
      "dragover",
      function (event) {
        if (!event.target.closest("[data-capture-dropzone]")) return;
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      },
      false,
    );

    document.addEventListener(
      "dragleave",
      function (event) {
        if (!event.target.closest("[data-capture-dropzone]")) return;
        captureDragDepth = Math.max(0, captureDragDepth - 1);
        if (captureDragDepth === 0) {
          var dropzone = captureDropzoneEl();
          if (dropzone) dropzone.classList.remove("is-dragover");
        }
      },
      false,
    );

    document.addEventListener(
      "drop",
      function (event) {
        if (!event.target.closest("[data-capture-dropzone]")) return;
        event.preventDefault();
        event.stopPropagation();
        handleCaptureDrop(event);
      },
      false,
    );

    document.addEventListener("click", function (event) {
      if (event.target.closest("#capture-fab-clear-file")) {
        event.preventDefault();
        event.stopPropagation();
        clearCaptureFile();
        return;
      }
      if (event.target.closest("#capture-fab-browse")) {
        event.preventDefault();
        event.stopPropagation();
        openCaptureFilePicker();
        return;
      }
      var dropzone = event.target.closest("[data-capture-dropzone]");
      if (!dropzone || dropzone.classList.contains("has-file")) return;
      if (event.target.closest(".capture-fab-staged")) return;
      openCaptureFilePicker();
    });

    document.addEventListener("keydown", function (event) {
      if (event.target.id === "capture-fab-browse" && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        openCaptureFilePicker();
      }
      var dropzone = event.target.closest("[data-capture-dropzone]");
      if (dropzone && (event.key === "Enter" || event.key === " ") && !dropzone.classList.contains("has-file")) {
        event.preventDefault();
        openCaptureFilePicker();
      }
    });

    document.addEventListener("change", function (event) {
      if (!event.target || event.target.id !== "capture-fab-file") return;
      var file = event.target.files && event.target.files[0];
      if (file) assignCaptureFile(file);
      else updateStagedFilePreview(null);
    });
  }

  function bindCaptureFormValidation() {
    if (document.body.dataset.captureFabValidateBound) return;
    document.body.dataset.captureFabValidateBound = "1";
    document.body.addEventListener(
      "submit",
      function (event) {
        var form = event.target;
        if (!form || form.id !== "capture-fab-form") return;
        var fileInput = document.getElementById("capture-fab-file");
        var dump = form.querySelector('[name="dump"]');
        var hasFile =
          fileInput &&
          fileInput.files &&
          fileInput.files.length > 0 &&
          fileInput.files[0] &&
          fileInput.files[0].size > 0;
        var hasDump = dump && dump.value && dump.value.trim().length > 0;
        if (!hasFile && !hasDump) {
          event.preventDefault();
          setCaptureFileHint("Add a brain dump and/or drop a document file.", true);
        }
      },
      true,
    );
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
      var drawer = document.getElementById("capture-fab-drawer");
      if (drawer) {
        drawer.innerHTML =
          '<div class="capture-fab-drawer-inner capture-fab-error">' +
          '<p class="capture-fab-error-title">Capture failed</p>' +
          '<p class="capture-fab-flash is-warn">Server error' +
          (status ? " (HTTP " + status + ")" : "") +
          ". Try again or check server logs.</p>" +
          '<button type="button" class="btn btn-primary btn-compact text-xs" data-capture-fab-reload>Try again</button>' +
          "</div>";
      }
    });

    document.body.addEventListener("htmx:sendError", function (event) {
      var elt = event.detail && event.detail.elt;
      if (!elt || elt.id !== "capture-fab-form") return;
      var drawer = document.getElementById("capture-fab-drawer");
      if (drawer) {
        drawer.innerHTML =
          '<div class="capture-fab-drawer-inner capture-fab-error">' +
          '<p class="capture-fab-error-title">Request timed out</p>' +
          '<p class="capture-fab-flash is-warn">MinerU may still be parsing a large PDF. ' +
          "Wait a moment, then try again — or upload a smaller file.</p>" +
          '<button type="button" class="btn btn-primary btn-compact text-xs" data-capture-fab-reload>Try again</button>' +
          "</div>";
      }
    });
  }

  function bindOpenTriggers() {
    document.querySelectorAll("[data-capture-fab-open]").forEach(function (el) {
      if (el.dataset.captureFabOpenBound) return;
      el.dataset.captureFabOpenBound = "1";
      el.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        loadDrawer({ fromHeader: true });
      });
    });
  }

  function bindDelegatedOpenTriggers() {
    if (document.body.dataset.captureFabDelegateBound) return;
    document.body.dataset.captureFabDelegateBound = "1";
    document.addEventListener(
      "click",
      function (event) {
        var trigger = event.target.closest("[data-capture-fab-open]");
        if (!trigger) return;
        event.preventDefault();
        event.stopPropagation();
        loadDrawer({ fromHeader: true });
      },
      true,
    );
  }

  function init() {
    bindFab();
    bindOpenTriggers();
    bindDelegatedOpenTriggers();
    bindClose();
    bindCaptureFormEncoding();
    bindCaptureFormValidation();
    bindCaptureUploadDelegation();
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
    bindOpenTriggers();
    if (event.detail && event.detail.target && event.detail.target.id === "capture-fab-drawer") {
      captureDragDepth = 0;
      if (window.lucide) window.lucide.createIcons();
      var result = document.getElementById("capture-fab-result");
      if (result) result.scrollIntoView({ block: "nearest", behavior: "smooth" });
      if (document.querySelector(".capture-fab-flash-kicker")) {
        refreshVaultInboxFromFabLink();
      }
    }
  });
})();