/* ── My Home Dash — Home Outlook folder organizer ────────────────────────────
 * Inbox "check senders, create folders, move all
 * their mail into it" flow. Multiple senders can be checked at once; they're
 * then processed one at a time with a self-calibrating countdown estimate.
 * Uses event delegation on document so it keeps working after htmx swaps the
 * whole Email card without any re-init step.
 */
(function () {
  "use strict";

  const AVG_MS_KEY = "mhdEmailOrganizeAvgMs";
  const DEFAULT_AVG_MS = 3000;
  const COUNTDOWN_TICK_MS = 250;

  // key -> { address, name, subject, folder, createRule, checkbox,
  //          count, suggestedName, folderName, loading, error }
  const pending = new Map();
  let countdownTimer = null;
  let remainingMs = 0;
  let batchRunning = false;

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function addressKey(address) {
    const trimmed = (address || "").trim().toLowerCase();
    return trimmed || "__no_address__";
  }

  function getPanel() {
    return document.querySelector(".mhd-email-organize-confirm");
  }

  function getMessagesContainer() {
    return document.getElementById("home-outlook-messages");
  }

  function resetCheckboxes() {
    document.querySelectorAll(".mhd-email-organize-checkbox").forEach((cb) => {
      cb.checked = false;
    });
  }

  function hidePanel() {
    const panel = getPanel();
    if (!panel) return;
    panel.classList.add("d-none");
    panel.innerHTML = "";
  }

  // ── Time estimate (learns from real elapsed time across sessions) ──────────

  function getAvgMs() {
    const stored = Number(localStorage.getItem(AVG_MS_KEY));
    return stored > 0 ? stored : DEFAULT_AVG_MS;
  }

  function updateAvgMs(actualMs) {
    const prev = getAvgMs();
    const next = prev * 0.7 + actualMs * 0.3; // exponential moving average
    localStorage.setItem(AVG_MS_KEY, String(Math.round(next)));
  }

  function formatDuration(ms) {
    const totalSec = Math.max(0, Math.ceil(ms / 1000));
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function renderCountdown() {
    const el = document.querySelector(".mhd-email-organize-countdown");
    if (!el) return;
    el.textContent = remainingMs > 0
      ? `Est. ${formatDuration(remainingMs)} remaining`
      : "Almost done…";
  }

  function startCountdown(initialMs) {
    stopCountdown();
    remainingMs = initialMs;
    renderCountdown();
    countdownTimer = setInterval(() => {
      remainingMs = Math.max(0, remainingMs - COUNTDOWN_TICK_MS);
      renderCountdown();
    }, COUNTDOWN_TICK_MS);
  }

  function stopCountdown() {
    if (countdownTimer) clearInterval(countdownTimer);
    countdownTimer = null;
  }

  // ── Folder loading ──────────────────────────────────────────────────────────

  function loadFolder(folder) {
    const container = getMessagesContainer();
    if (!container) return;
    container.innerHTML = '<p class="text-muted small mb-0"><i class="bi bi-hourglass me-1"></i>Loading…</p>';
    pending.clear();
    stopCountdown();
    hidePanel();

    fetch(`/api/email/home_outlook/messages?folder=${encodeURIComponent(folder)}`)
      .then((r) => r.text())
      .then((html) => {
        container.innerHTML = html;
      })
      .catch(() => {
        container.innerHTML = '<p class="text-warning small mb-0">Failed to load messages.</p>';
      });
  }

  function initFolderPanel() {
    const container = getMessagesContainer();
    if (container && !container.dataset.loaded) {
      container.dataset.loaded = "1";
      loadFolder("inbox");
    }
  }

  // ── Pending-selection panel (batch of senders, checked but not yet moved) ──

  function renderPanel() {
    const panel = getPanel();
    if (!panel) return;

    if (batchRunning) return; // panel is owned by runBatch() while it's active

    if (pending.size === 0) {
      hidePanel();
      return;
    }

    panel.classList.remove("d-none");

    const rows = Array.from(pending.entries()).map(([key, entry]) => {
      const modeLabel = entry.createRule
        ? '<i class="bi bi-arrow-repeat text-warning me-1" title="Move + create standing rule"></i>'
        : '<i class="bi bi-arrow-right text-muted me-1" title="Move existing only"></i>';
      const countLabel = entry.loading
        ? '<span class="text-muted"><i class="bi bi-hourglass me-1"></i>checking…</span>'
        : entry.error
          ? `<span class="text-warning">${escapeHtml(entry.error)}</span>`
          : `<span class="text-muted">${entry.count} email${entry.count === 1 ? "" : "s"}</span>`;

      return `
        <li class="d-flex align-items-center gap-2 mb-1" data-key="${escapeHtml(key)}">
          <span class="flex-grow-1 text-truncate">
            ${modeLabel}<strong>${escapeHtml(entry.name || "(no name)")}</strong> · ${countLabel}
          </span>
          <input type="text" class="form-control form-control-sm mhd-email-organize-pending-name"
                 style="max-width: 130px" value="${escapeHtml(entry.folderName)}"
                 ${entry.loading ? "disabled" : ""}>
          <button type="button" class="btn-close mhd-email-organize-pending-remove" aria-label="Remove"></button>
        </li>`;
    });

    const readyCount = Array.from(pending.values()).filter((e) => !e.loading && !e.error).length;

    panel.innerHTML = `
      <div class="mb-2 fw-semibold">${pending.size} sender${pending.size === 1 ? "" : "s"} selected</div>
      <ul class="list-unstyled mb-2 mhd-email-organize-pending-list">${rows.join("")}</ul>
      <div class="d-flex gap-2">
        <button type="button" class="btn btn-primary btn-sm mhd-email-organize-move-all-btn" ${readyCount === 0 ? "disabled" : ""}>
          Move All (${pending.size})
        </button>
        <button type="button" class="btn btn-outline-secondary btn-sm mhd-email-organize-cancel-btn">Cancel</button>
      </div>
    `;
  }

  function addPending(checkbox) {
    const key = addressKey(checkbox.dataset.address);
    const entry = {
      address: checkbox.dataset.address,
      name: checkbox.dataset.name,
      subject: checkbox.dataset.subject,
      folder: checkbox.dataset.folder,
      createRule: checkbox.dataset.createRule === "1",
      checkbox,
      count: 0,
      suggestedName: "",
      folderName: "",
      loading: true,
      error: "",
    };
    pending.set(key, entry);
    renderPanel();

    const params = new URLSearchParams({
      folder: entry.folder,
      address: entry.address,
      name: entry.name,
      subject: entry.subject,
    });

    fetch(`/api/email/home_outlook/sender-count?${params.toString()}`)
      .then((r) => r.json())
      .then((payload) => {
        const current = pending.get(key);
        if (!current) return; // removed while the request was in flight
        current.loading = false;
        if (payload.error) {
          current.error = payload.error;
        } else {
          current.count = payload.count;
          current.suggestedName = payload.suggested_name;
          current.folderName = payload.suggested_name;
        }
        renderPanel();
      })
      .catch(() => {
        const current = pending.get(key);
        if (!current) return;
        current.loading = false;
        current.error = "Could not check sender.";
        renderPanel();
      });
  }

  function removePending(key) {
    const entry = pending.get(key);
    if (entry && entry.checkbox) entry.checkbox.checked = false;
    pending.delete(key);
    renderPanel();
  }

  // ── Sequential batch processing ─────────────────────────────────────────────

  async function runBatch() {
    const panel = getPanel();
    if (!panel) return;

    const entries = Array.from(pending.entries()).filter(([, e]) => !e.loading && !e.error);
    if (entries.length === 0) return;

    batchRunning = true;
    const total = entries.length;
    let avgMs = getAvgMs();
    startCountdown(avgMs * total);

    panel.innerHTML = `
      <div class="mb-2 mhd-email-organize-progress">
        <i class="bi bi-hourglass-split me-1"></i>
        <span class="mhd-email-organize-progress-label">Starting…</span>
      </div>
      <div class="progress mb-2" style="height: 6px;">
        <div class="progress-bar mhd-email-organize-progress-bar" role="progressbar" style="width: 0%"></div>
      </div>
      <div class="small text-muted mhd-email-organize-countdown"></div>
      <ul class="list-unstyled mb-0 mt-2 mhd-email-organize-results"></ul>
    `;
    renderCountdown();

    const labelEl = panel.querySelector(".mhd-email-organize-progress-label");
    const barEl = panel.querySelector(".mhd-email-organize-progress-bar");
    const resultsEl = panel.querySelector(".mhd-email-organize-results");

    for (let i = 0; i < total; i++) {
      const [key, entry] = entries[i];
      if (labelEl) labelEl.textContent = `Processing ${i + 1} of ${total}: ${entry.name || "(no name)"}…`;
      if (barEl) barEl.style.width = `${Math.round((i / total) * 100)}%`;

      const t0 = performance.now();
      let payload;
      try {
        const resp = await fetch("/api/email/home_outlook/organize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            folder: entry.folder,
            address: entry.address,
            folder_name: entry.folderName,
            create_rule: entry.createRule,
          }),
        });
        payload = await resp.json();
      } catch (e) {
        payload = { error: "Move failed." };
      }
      const actualMs = performance.now() - t0;
      updateAvgMs(actualMs);
      avgMs = getAvgMs();

      const remainingItems = total - (i + 1);
      remainingMs = avgMs * remainingItems;
      renderCountdown();

      if (resultsEl) {
        let line;
        if (payload.error) {
          line = `<span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>${escapeHtml(entry.name || "(no name)")}: ${escapeHtml(payload.error)}</span>`;
        } else {
          const ruleNote = payload.rule_created
            ? " + rule"
            : payload.rule_already_existed
              ? " (rule existed)"
              : "";
          const truncatedNote = payload.truncated ? " (capped — recheck sender to move the rest)" : "";
          line = `<span class="text-success"><i class="bi bi-check2-circle me-1"></i>${escapeHtml(entry.name || "(no name)")}: moved ${payload.moved} to "${escapeHtml(payload.folder_name)}"${ruleNote}${truncatedNote}</span>`;
        }
        resultsEl.insertAdjacentHTML("beforeend", `<li class="small mb-1">${line}</li>`);
      }

      pending.delete(key);
    }

    if (barEl) barEl.style.width = "100%";
    if (labelEl) labelEl.textContent = `Done — processed ${total} sender${total === 1 ? "" : "s"}.`;
    stopCountdown();
    const countdownEl = panel.querySelector(".mhd-email-organize-countdown");
    if (countdownEl) countdownEl.textContent = "";

    batchRunning = false;
    resetCheckboxes();

    loadFolder("inbox");
    setTimeout(hidePanel, 8000);
  }

  document.addEventListener("DOMContentLoaded", initFolderPanel);
  document.body.addEventListener("htmx:afterSwap", initFolderPanel);

  document.addEventListener("click", function (event) {
    if (batchRunning) return; // ignore panel interactions while a batch is running

    if (event.target.closest(".mhd-email-organize-cancel-btn")) {
      resetCheckboxes();
      pending.clear();
      hidePanel();
      return;
    }

    const removeBtn = event.target.closest(".mhd-email-organize-pending-remove");
    if (removeBtn) {
      const li = removeBtn.closest("li[data-key]");
      if (li) removePending(li.dataset.key);
      return;
    }

    const moveAllBtn = event.target.closest(".mhd-email-organize-move-all-btn");
    if (moveAllBtn) {
      runBatch();
    }
  });

  document.addEventListener("input", function (event) {
    const nameInput = event.target.closest(".mhd-email-organize-pending-name");
    if (!nameInput || batchRunning) return;
    const li = nameInput.closest("li[data-key]");
    if (!li) return;
    const entry = pending.get(li.dataset.key);
    if (entry) entry.folderName = nameInput.value;
  });

  document.addEventListener("change", function (event) {
    const checkbox = event.target.closest(".mhd-email-organize-checkbox");
    if (!checkbox || batchRunning) return;

    const key = addressKey(checkbox.dataset.address);

    if (!checkbox.checked) {
      removePending(key);
      return;
    }

    // The two checkboxes on the same row (move vs. move + auto-rule) are
    // mutually exclusive with each other.
    const li = checkbox.closest("li");
    if (li) {
      li.querySelectorAll(".mhd-email-organize-checkbox").forEach((cb) => {
        if (cb !== checkbox) cb.checked = false;
      });
    }

    // The same sender may appear on multiple rows (multiple listed messages);
    // keep only the most recently checked selection for a given sender.
    document.querySelectorAll(".mhd-email-organize-checkbox:checked").forEach((cb) => {
      if (cb !== checkbox && addressKey(cb.dataset.address) === key) {
        cb.checked = false;
        pending.delete(key);
      }
    });

    addPending(checkbox);
  });
})();
