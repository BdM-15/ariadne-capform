(function () {
  function scrollToHighlight(root) {
    var scope = root || document;
    var inbox = scope.querySelector("#knowledge-vault-inbox[data-inbox-highlight]");
    if (!inbox) {
      inbox = scope.querySelector("#knowledge-vault-inbox");
    }
    if (!inbox) return;

    var highlightId = inbox.getAttribute("data-inbox-highlight");
    if (!highlightId) {
      highlightId = (scope.querySelector("#knowledge-capture-studio-mount") || {}).dataset;
      highlightId = highlightId && highlightId.inboxHighlight;
    }
    if (!highlightId) return;

    var card = scope.getElementById("vault-inbox-item-" + highlightId);
    if (!card) return;

    var details = inbox.querySelector("details.capture-studio-collapse");
    if (details) details.open = true;

    card.classList.add("vault-inbox-card--highlight");
    window.setTimeout(function () {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 80);
  }

  document.addEventListener("DOMContentLoaded", function () {
    scrollToHighlight(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (evt) {
    var target = evt.detail && evt.detail.target;
    if (!target) return;
    if (
      target.id === "knowledge-capture-studio-mount" ||
      target.querySelector("#knowledge-vault-inbox")
    ) {
      scrollToHighlight(target.id === "knowledge-capture-studio-mount" ? target : document);
    }
  });
})();