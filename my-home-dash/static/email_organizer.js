/* ── My Home Dash — Home Outlook folder organizer ────────────────────────────
 * Inbox/Junk folder switching + "check a sender, create a folder, move all
 * their mail into it" flow. Uses event delegation on document so it keeps
 * working after htmx swaps the whole Email card without any re-init step.
 */
(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function getConfirmBar() {
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

  function hideConfirm() {
    const bar = getConfirmBar();
    if (!bar) return;
    bar.classList.add("d-none");
    bar.innerHTML = "";
  }

  function loadFolder(folder) {
    const container = getMessagesContainer();
    if (!container) return;
    container.innerHTML = '<p class="text-muted small mb-0"><i class="bi bi-hourglass me-1"></i>Loading…</p>';
    hideConfirm();

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

  function showLoadingConfirm() {
    const bar = getConfirmBar();
    if (!bar) return;
    bar.classList.remove("d-none");
    bar.innerHTML = '<span class="text-muted"><i class="bi bi-hourglass me-1"></i>Checking how many emails are from this sender…</span>';
  }

  function renderConfirm(checkbox, count, suggestedName) {
    const bar = getConfirmBar();
    if (!bar) return;
    const createRule = checkbox.dataset.createRule === "1";
    const folder = checkbox.dataset.folder;
    const name = checkbox.dataset.name;

    bar.dataset.address = checkbox.dataset.address;
    bar.dataset.folder = folder;
    bar.dataset.name = name;
    bar.dataset.createRule = createRule ? "1" : "0";

    const actionText = createRule
      ? `Move <strong>${count}</strong> email${count === 1 ? "" : "s"} from <strong>${escapeHtml(name)}</strong> into a new folder, and automatically move all future emails from them too:`
      : `Move <strong>${count}</strong> email${count === 1 ? "" : "s"} from <strong>${escapeHtml(name)}</strong> into a new folder:`;

    const junkNote = createRule && folder === "junk"
      ? '<div class="text-warning small mb-2"><i class="bi bi-info-circle me-1"></i>Note: mail already caught by junk filtering runs before Inbox rules, so this may not intercept every future email from this sender.</div>'
      : "";

    bar.innerHTML = `
      <div class="mb-2">${actionText}</div>
      ${junkNote}
      <div class="input-group input-group-sm mb-2">
        <span class="input-group-text"><i class="bi bi-folder-plus"></i></span>
        <input type="text" class="form-control mhd-email-organize-name" value="${escapeHtml(suggestedName)}">
      </div>
      <div class="d-flex gap-2">
        <button type="button" class="btn ${createRule ? "btn-warning" : "btn-primary"} btn-sm mhd-email-organize-confirm-btn">Move${createRule ? " + Create Rule" : ""}</button>
        <button type="button" class="btn btn-outline-secondary btn-sm mhd-email-organize-cancel-btn">Cancel</button>
      </div>
    `;
  }

  document.addEventListener("DOMContentLoaded", initFolderPanel);
  document.body.addEventListener("htmx:afterSwap", initFolderPanel);

  document.addEventListener("click", function (event) {
    const folderBtn = event.target.closest(".mhd-email-folder-btn");
    if (folderBtn) {
      document.querySelectorAll(".mhd-email-folder-btn").forEach((b) => b.classList.remove("active"));
      folderBtn.classList.add("active");
      loadFolder(folderBtn.dataset.folder);
      return;
    }

    if (event.target.closest(".mhd-email-organize-cancel-btn")) {
      resetCheckboxes();
      hideConfirm();
      return;
    }

    const confirmBtn = event.target.closest(".mhd-email-organize-confirm-btn");
    if (confirmBtn) {
      const bar = getConfirmBar();
      const nameInput = bar.querySelector(".mhd-email-organize-name");
      const folderName = (nameInput.value || "").trim();
      if (!folderName) return;

      confirmBtn.disabled = true;
      confirmBtn.textContent = "Moving…";

      fetch("/api/email/home_outlook/organize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder: bar.dataset.folder,
          address: bar.dataset.address,
          folder_name: folderName,
          create_rule: bar.dataset.createRule === "1",
        }),
      })
        .then((r) => r.json())
        .then((payload) => {
          if (payload.error) {
            bar.innerHTML = `<span class="text-warning">${escapeHtml(payload.error)}</span>`;
            return;
          }
          const truncatedNote = payload.truncated
            ? ` (capped at ${payload.moved} for this action — check the sender again to move the rest)`
            : "";
          const ruleNote = payload.rule_created
            ? " and created a rule to auto-move their future emails"
            : payload.rule_already_existed
              ? " (a matching auto-move rule already existed)"
              : "";
          const ruleErrorNote = payload.rule_error
            ? `<div class="text-warning small mt-1"><i class="bi bi-exclamation-triangle me-1"></i>Move succeeded, but the auto-move rule could not be created: ${escapeHtml(payload.rule_error)}</div>`
            : "";
          bar.innerHTML = `<span class="text-success"><i class="bi bi-check2-circle me-1"></i>Moved ${payload.moved} email${payload.moved === 1 ? "" : "s"} to "${escapeHtml(payload.folder_name)}"${ruleNote}${truncatedNote}</span>${ruleErrorNote}`;
          resetCheckboxes();
          loadFolder(bar.dataset.folder);
          setTimeout(hideConfirm, 6000);
        })
        .catch(() => {
          bar.innerHTML = '<span class="text-warning">Move failed. Please try again.</span>';
        });
    }
  });

  document.addEventListener("change", function (event) {
    const checkbox = event.target.closest(".mhd-email-organize-checkbox");
    if (!checkbox) return;

    if (!checkbox.checked) {
      hideConfirm();
      return;
    }

    resetCheckboxes();
    checkbox.checked = true;
    showLoadingConfirm();

    const params = new URLSearchParams({
      folder: checkbox.dataset.folder,
      address: checkbox.dataset.address,
      name: checkbox.dataset.name,
    });

    fetch(`/api/email/home_outlook/sender-count?${params.toString()}`)
      .then((r) => r.json())
      .then((payload) => {
        if (payload.error) {
          const bar = getConfirmBar();
          if (bar) bar.innerHTML = `<span class="text-warning">${escapeHtml(payload.error)}</span>`;
          return;
        }
        renderConfirm(checkbox, payload.count, payload.suggested_name);
      })
      .catch(() => {
        const bar = getConfirmBar();
        if (bar) bar.innerHTML = '<span class="text-warning">Could not check sender count.</span>';
      });
  });
})();
