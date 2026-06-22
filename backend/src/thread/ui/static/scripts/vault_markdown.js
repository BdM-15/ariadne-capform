/**
 * Vault markdown renderer — marked + wikilink → /knowledge deep links (HTMX-safe).
 */
(function () {
  function wikiToHref(target) {
    var clean = String(target || "").trim();
    if (!clean) return "/knowledge";
    if (clean.indexOf("/") >= 0 || clean.indexOf(".") >= 0) {
      return "/knowledge?page=" + encodeURIComponent(clean);
    }
    return "/knowledge?page=" + encodeURIComponent(clean + ".md");
  }

  function postProcessWikilinks(html) {
    return html.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, function (_, page, label) {
      var text = (label || page).trim();
      var href = wikiToHref(page.trim());
      return (
        '<a href="' +
        href +
        '" class="vault-wikilink text-neon-cyan no-underline hover:underline">' +
        text +
        "</a>"
      );
    });
  }

  function renderHost(host) {
    if (!host || host.dataset.vaultRendered === "1") return;
    if (typeof marked === "undefined") return;
    var raw = host.textContent || "";
    marked.setOptions({ gfm: true, breaks: false });
    var html = marked.parse(raw);
    host.innerHTML = postProcessWikilinks(html);
    host.dataset.vaultRendered = "1";
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function renderAll(root) {
    var scope = root || document;
    scope.querySelectorAll("[data-vault-markdown]").forEach(renderHost);
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderAll(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (e) {
    var target = e.detail && e.detail.target;
    if (!target) return;
    if (
      target.id === "vault-page-panel" ||
      target.closest("#vault-page-panel") ||
      target.id === "education-lesson-panel" ||
      target.closest("#education-lesson-panel") ||
      target.id === "education-studio-mount" ||
      target.closest("#education-studio-mount") ||
      target.id === "knowledge-candidate-editor" ||
      target.closest("#knowledge-candidate-editor") ||
      target.id === "knowledge-capture-studio-mount" ||
      target.closest("#knowledge-capture-studio-mount")
    ) {
      renderAll(target);
    }
  });
})();