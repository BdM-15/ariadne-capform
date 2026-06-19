(function () {
  const overlay = () => document.getElementById("thread-restart-overlay");
  const statusEl = () => document.getElementById("thread-restart-status");
  const stuckEl = () => document.getElementById("thread-restart-stuck");
  const pulseEl = () => document.getElementById("thread-restart-pulse");
  const hintEl = () => document.getElementById("thread-restart-hint");

  let restarting = false;
  let pollTimer = null;

  function setButtonsDisabled(disabled) {
    document.querySelectorAll(".thread-restart-btn").forEach((btn) => {
      btn.disabled = disabled;
      btn.classList.toggle("opacity-60", disabled);
      btn.classList.toggle("pointer-events-none", disabled);
      const label = btn.querySelector(".thread-restart-label");
      if (label) {
        label.textContent = disabled ? "Restarting…" : "Restart server";
      }
    });
  }

  function showOverlay() {
    const el = overlay();
    if (!el) return;
    el.classList.remove("hidden");
    el.setAttribute("aria-hidden", "false");
  }

  function hideOverlay() {
    const el = overlay();
    if (!el) return;
    el.classList.add("hidden");
    el.setAttribute("aria-hidden", "true");
    if (statusEl()) statusEl().textContent = "Restarting server…";
    if (stuckEl()) stuckEl().classList.add("hidden");
    if (pulseEl()) pulseEl().classList.remove("hidden");
    if (hintEl()) hintEl().classList.remove("hidden");
  }

  function pollHealth(startedAt) {
    const maxWaitMs = 60000;
    if (!restarting) return;
    if (Date.now() - startedAt > maxWaitMs) {
      if (statusEl()) statusEl().textContent = "Restart taking longer than expected";
      if (stuckEl()) stuckEl().classList.remove("hidden");
      if (pulseEl()) pulseEl().classList.add("hidden");
      if (hintEl()) hintEl().classList.add("hidden");
      return;
    }
    fetch("/api/health", { cache: "no-store" })
      .then((res) => {
        if (res.ok) {
          window.location.reload();
          return;
        }
        pollTimer = window.setTimeout(() => pollHealth(startedAt), 1000);
      })
      .catch(() => {
        pollTimer = window.setTimeout(() => pollHealth(startedAt), 1000);
      });
  }

  function beginRestart() {
    restarting = true;
    setButtonsDisabled(true);
    showOverlay();
    const startedAt = Date.now();
    pollTimer = window.setTimeout(() => pollHealth(startedAt), 1500);
  }

  window.threadDismissRestart = function threadDismissRestart() {
    restarting = false;
    if (pollTimer) window.clearTimeout(pollTimer);
    setButtonsDisabled(false);
    hideOverlay();
  };

  window.threadRestartServer = async function threadRestartServer(confirmFirst) {
    if (restarting) return;
    if (
      confirmFirst &&
      !window.confirm(
        "Restart the server now? Active uploads or in-flight queries will be interrupted.",
      )
    ) {
      return;
    }
    try {
      const res = await fetch("/system/restart", { method: "POST" });
      if (!res.ok) throw new Error("Restart request failed");
      beginRestart();
    } catch (err) {
      window.alert("Restart failed: " + (err && err.message ? err.message : err));
    }
  };

  document.addEventListener("click", (event) => {
    const btn = event.target.closest(".thread-restart-btn");
    if (!btn) return;
    event.preventDefault();
    const confirmFirst = btn.dataset.restartConfirm !== "0";
    window.threadRestartServer(confirmFirst);
  });
})();