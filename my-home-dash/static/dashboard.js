/* ── My Home Dash — Dashboard JS ─────────────────────────────────────────── */

/**
 * Live clock — updates every 30 seconds without a page reload.
 */
(function () {
  "use strict";

  function pad(n) { return String(n).padStart(2, "0"); }

  function formatTime(d) {
    let h = d.getHours();
    const m = pad(d.getMinutes());
    const ampm = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return `${h}:${m} ${ampm}`;
  }

  function tickClock() {
    const el = document.getElementById("live-clock");
    if (el) el.textContent = formatTime(new Date());
  }

  tickClock();
  setInterval(tickClock, 30_000);
})();

/**
 * Weather bar — predictive 12-hour temperature line chart.
 * Re-runs after every htmx swap so it re-initializes when the weather
 * section (or the whole page, via "Refresh All") is replaced.
 */
(function () {
  "use strict";

  const ICON_DRAWERS = {
    sun(ctx, size) {
      const cx = size / 2;
      const cy = size / 2;
      const r = size * 0.26;
      ctx.fillStyle = "#ffc107";
      ctx.strokeStyle = "#ffc107";
      ctx.lineWidth = Math.max(1, size * 0.07);
      ctx.lineCap = "round";
      for (let i = 0; i < 8; i++) {
        const angle = (Math.PI / 4) * i;
        const inner = r + size * 0.06;
        const outer = r + size * 0.2;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(angle) * inner, cy + Math.sin(angle) * inner);
        ctx.lineTo(cx + Math.cos(angle) * outer, cy + Math.sin(angle) * outer);
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
    },

    moon(ctx, size) {
      const cx = size / 2;
      const cy = size / 2;
      const r = size * 0.32;

      ctx.fillStyle = "#ffffff";
      ctx.strokeStyle = "#c3c9d1";
      ctx.lineWidth = Math.max(1, size * 0.05);
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Grey craters, clipped to the moon's disc so they never bleed past the edge.
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.clip();
      ctx.fillStyle = "#adb5bd";
      [
        { dx: -0.14, dy: -0.12, r: 0.075 },
        { dx: 0.13, dy: -0.16, r: 0.06 },
        { dx: 0.02, dy: 0.10, r: 0.095 },
        { dx: -0.15, dy: 0.15, r: 0.065 },
      ].forEach((spot) => {
        ctx.beginPath();
        ctx.arc(cx + spot.dx * size, cy + spot.dy * size, spot.r * size, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.restore();
    },

    cloud(ctx, size) {
      ctx.fillStyle = "#8a94a3";
      const cx = size / 2;
      const baseY = size * 0.6;
      [
        { dx: -0.22, dy: 0.05, r: 0.15 },
        { dx: -0.02, dy: -0.10, r: 0.19 },
        { dx: 0.20, dy: 0.03, r: 0.16 },
        { dx: 0.00, dy: 0.16, r: 0.21 },
      ].forEach((lobe) => {
        ctx.beginPath();
        ctx.arc(cx + lobe.dx * size, baseY + lobe.dy * size, lobe.r * size, 0, Math.PI * 2);
        ctx.fill();
      });
    },

    rain(ctx, size) {
      const cx = size / 2;
      const topY = size * 0.22;
      const bottomY = size * 0.8;
      const r = size * 0.22;
      ctx.fillStyle = "#0d6efd";
      ctx.beginPath();
      ctx.moveTo(cx, topY);
      ctx.quadraticCurveTo(cx + r * 1.3, bottomY - r * 0.7, cx, bottomY);
      ctx.quadraticCurveTo(cx - r * 1.3, bottomY - r * 0.7, cx, topY);
      ctx.closePath();
      ctx.fill();
    },
  };

  const iconCanvasCache = {};

  // Chart.js accepts an HTMLCanvasElement as a point's pointStyle, so each
  // sky icon is pre-rendered once onto its own tiny canvas and reused for
  // every matching data point rather than re-drawn per point.
  function iconCanvas(name) {
    if (iconCanvasCache[name]) return iconCanvasCache[name];
    const draw = ICON_DRAWERS[name];
    if (!draw) return null;

    const size = 32;
    const c = document.createElement("canvas");
    c.width = size;
    c.height = size;
    draw(c.getContext("2d"), size);

    iconCanvasCache[name] = c;
    return c;
  }

  // Positions the "Wed, Jul 29 | Thu, Jul 30" day-boundary label directly above
  // the chart's 12 AM point. Re-run on every Chart.js resize (via onResize)
  // since the point's pixel position shifts whenever the canvas width changes.
  function positionMidnightLabel(canvas, chart, points) {
    // Chart.js can call onResize while it's still constructing itself, before
    // chart.scales exists yet -- letting that throw here aborts the whole
    // `new Chart(...)` call and leaves the canvas blank, so bail out quietly.
    if (!chart.scales || !chart.scales.x) return;

    const idx = points.findIndex((p) => p.time === "12 AM");
    const topRow = canvas.closest(".card-body")?.querySelector(".mhd-weather-top-row");
    const label = topRow?.querySelector(".mhd-weather-midnight-label");
    if (!label) return;

    // No 12 AM point in this 24h window (only possible if the window starts
    // exactly at midnight), or no point before it to label -- nothing to show.
    if (idx <= 0) {
      label.classList.add("d-none");
      return;
    }

    label.querySelector(".mhd-weather-midnight-before").textContent = points[idx - 1].full_date || "";
    label.querySelector(".mhd-weather-midnight-after").textContent = points[idx].full_date || "";

    const anchorRect = topRow.getBoundingClientRect();
    const canvasRect = canvas.getBoundingClientRect();
    const pixelX = chart.scales.x.getPixelForValue(idx);

    label.style.left = `${canvasRect.left - anchorRect.left + pixelX}px`;
    label.classList.remove("d-none");
  }

  function initWeatherCharts() {
    if (typeof Chart === "undefined") return;

    document.querySelectorAll(".mhd-weather-hourly-canvas").forEach((canvas) => {
      if (canvas.dataset.chartInit === "1") return;

      let points;
      try {
        points = JSON.parse(canvas.dataset.hourly || "[]");
      } catch {
        points = [];
      }
      if (!Array.isArray(points) || !points.length) return;

      canvas.dataset.chartInit = "1";
      const units = canvas.dataset.units || "";
      const pointStyles = points.map((p) => iconCanvas(p.icon) || "circle");

      new Chart(canvas, {
        type: "line",
        data: {
          labels: points.map((p) => p.time),
          datasets: [{
            label: "Temp",
            data: points.map((p) => p.temp),
            borderColor: "#0dcaf0",
            backgroundColor: "rgba(13, 202, 240, 0.15)",
            fill: true,
            tension: 0.35,
            pointStyle: pointStyles,
            pointRadius: 8,
            pointHoverRadius: 9,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          layout: { padding: { top: 4 } },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.parsed.y}${units}`,
              },
            },
          },
          scales: {
            x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
            y: {
              ticks: {
                maxTicksLimit: 4,
                callback: (value) => `${value}${units}`,
              },
            },
          },
        },
        // afterRender (not onResize) -- onResize fires before Chart.js rebuilds
        // chart.scales for the new size, so getPixelForValue would read stale
        // (or briefly missing) scale data. afterRender fires once per render,
        // including resizes, after scales are fully rebuilt for the new size.
        plugins: [{
          id: "mhdMidnightLabel",
          afterRender: (c) => positionMidnightLabel(canvas, c, points),
        }],
      });
    });
  }

  document.addEventListener("DOMContentLoaded", initWeatherCharts);
  document.body.addEventListener("htmx:afterSwap", initWeatherCharts);
})();

/**
 * Local Ollama chat panel.
 */
(function () {
  "use strict";

  const storageKey = "mhdChatMessages";
  const maxMessages = 16;

  const threadEl = document.getElementById("chat-thread");
  const formEl = document.getElementById("chat-form");
  const inputEl = document.getElementById("chat-input");
  const sendEl = document.getElementById("chat-send");
  const clearEl = document.getElementById("chat-clear");
  const statusEl = document.getElementById("chat-status");

  if (!threadEl || !formEl || !inputEl || !sendEl || !clearEl || !statusEl) {
    return;
  }

  function loadMessages() {
    try {
      const raw = window.localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function saveMessages(messages) {
    window.localStorage.setItem(storageKey, JSON.stringify(messages.slice(-maxMessages)));
  }

  function escapeHtml(value) {
    return value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function renderMessages(messages) {
    if (!messages.length) {
      threadEl.innerHTML = "<div class=\"mhd-chat-empty text-body-secondary\">No messages yet. Start a conversation with your local model.</div>";
      return;
    }

    threadEl.innerHTML = messages
      .map((message) => {
        const role = message.role === "assistant" ? "assistant" : "user";
        const label = role === "assistant" ? "AI" : "You";
        const content = escapeHtml(String(message.content || "")).replaceAll("\n", "<br>");
        const retrieval = role === "assistant" && message.retrieval ? message.retrieval : null;
        const retrievalNote = retrieval
          ? buildRetrievalNote(retrieval)
          : "";
        return `
          <article class="mhd-chat-message mhd-chat-message-${role}">
            <div class="mhd-chat-meta">${label}</div>
            <div class="mhd-chat-bubble">${content}</div>
            ${retrievalNote}
          </article>
        `;
      })
      .join("");

    threadEl.scrollTop = threadEl.scrollHeight;
  }

  function setBusy(isBusy, label) {
    sendEl.disabled = isBusy;
    inputEl.disabled = isBusy;
    clearEl.disabled = isBusy;
    statusEl.textContent = label;
  }

  function buildRetrievalNote(retrieval) {
    if (retrieval.used) {
      const sources = Array.isArray(retrieval.sources) && retrieval.sources.length
        ? ` · source: ${escapeHtml(String(retrieval.sources[0]))}`
        : "";
      return `<div class="mhd-chat-meta text-body-secondary">Web-assisted${sources}</div>`;
    }

    if (retrieval.status === "error") {
      return "<div class=\"mhd-chat-meta text-warning\">Web retrieval unavailable for this response</div>";
    }

    return "";
  }

  function getStatusLabel(payload) {
    const modelLabel = payload.model ? `Ready · ${payload.model}` : "Ready";
    if (payload.retrieval && payload.retrieval.used) {
      return `${modelLabel} · web-assisted`;
    }
    if (payload.retrieval && payload.retrieval.status === "error") {
      return `${modelLabel} · retrieval unavailable`;
    }
    return modelLabel;
  }

  let messages = loadMessages();
  renderMessages(messages);

  clearEl.addEventListener("click", function () {
    messages = [];
    saveMessages(messages);
    renderMessages(messages);
    statusEl.textContent = "Cleared";
  });

  inputEl.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      formEl.requestSubmit();
    }
  });

  formEl.addEventListener("submit", async function (event) {
    event.preventDefault();
    const content = inputEl.value.trim();
    if (!content) {
      return;
    }

    messages = messages.concat([{ role: "user", content }]).slice(-maxMessages);
    saveMessages(messages);
    renderMessages(messages);
    inputEl.value = "";
    setBusy(true, "Thinking...");

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Chat request failed.");
      }

      messages = messages.concat([{
        role: "assistant",
        content: payload.content,
        retrieval: payload.retrieval || null,
      }]).slice(-maxMessages);
      saveMessages(messages);
      renderMessages(messages);
      statusEl.textContent = getStatusLabel(payload);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unexpected chat error.";
      messages = messages.concat([{ role: "assistant", content: `Error: ${message}` }]).slice(-maxMessages);
      saveMessages(messages);
      renderMessages(messages);
      statusEl.textContent = "Error";
    } finally {
      setBusy(false, statusEl.textContent === "Thinking..." ? "Ready" : statusEl.textContent);
      inputEl.focus();
    }
  });
})();

/**
 * AI Operator panel — same shape as the chat panel above, but the assistant
 * can call tools against real dashboard state, and each reply shows a trace
 * of which tools ran.
 */
(function () {
  "use strict";

  const storageKey = "mhdOperatorMessages";
  const maxMessages = 16;

  const threadEl = document.getElementById("operator-thread");
  const formEl = document.getElementById("operator-form");
  const inputEl = document.getElementById("operator-input");
  const sendEl = document.getElementById("operator-send");
  const clearEl = document.getElementById("operator-clear");
  const statusEl = document.getElementById("operator-status");

  if (!threadEl || !formEl || !inputEl || !sendEl || !clearEl || !statusEl) {
    return;
  }

  function loadMessages() {
    try {
      const raw = window.localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function saveMessages(messages) {
    window.localStorage.setItem(storageKey, JSON.stringify(messages.slice(-maxMessages)));
  }

  function escapeHtml(value) {
    return value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function buildToolTrace(toolCalls) {
    if (!Array.isArray(toolCalls) || !toolCalls.length) {
      return "";
    }
    const names = toolCalls.map((call) => escapeHtml(String(call.name || "unknown"))).join(", ");
    return `<div class="mhd-chat-meta text-body-secondary">Tools called: ${names}</div>`;
  }

  function renderMessages(messages) {
    if (!messages.length) {
      threadEl.innerHTML = "<div class=\"mhd-chat-empty text-body-secondary\">No messages yet. Ask the operator something it can check against real dashboard state.</div>";
      return;
    }

    threadEl.innerHTML = messages
      .map((message) => {
        const role = message.role === "assistant" ? "assistant" : "user";
        const label = role === "assistant" ? "Operator" : "You";
        const content = escapeHtml(String(message.content || "")).replaceAll("\n", "<br>");
        const toolTrace = role === "assistant" ? buildToolTrace(message.tool_calls) : "";
        return `
          <article class="mhd-chat-message mhd-chat-message-${role}">
            <div class="mhd-chat-meta">${label}</div>
            <div class="mhd-chat-bubble">${content}</div>
            ${toolTrace}
          </article>
        `;
      })
      .join("");

    threadEl.scrollTop = threadEl.scrollHeight;
  }

  function setBusy(isBusy, label) {
    sendEl.disabled = isBusy;
    inputEl.disabled = isBusy;
    clearEl.disabled = isBusy;
    statusEl.textContent = label;
  }

  let messages = loadMessages();
  renderMessages(messages);

  clearEl.addEventListener("click", function () {
    messages = [];
    saveMessages(messages);
    renderMessages(messages);
    statusEl.textContent = "Cleared";
  });

  inputEl.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      formEl.requestSubmit();
    }
  });

  formEl.addEventListener("submit", async function (event) {
    event.preventDefault();
    const content = inputEl.value.trim();
    if (!content) {
      return;
    }

    messages = messages.concat([{ role: "user", content }]).slice(-maxMessages);
    saveMessages(messages);
    renderMessages(messages);
    inputEl.value = "";
    setBusy(true, "Thinking...");

    try {
      const response = await fetch("/api/operator", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Operator request failed.");
      }

      messages = messages.concat([{
        role: "assistant",
        content: payload.content,
        tool_calls: payload.tool_calls || [],
      }]).slice(-maxMessages);
      saveMessages(messages);
      renderMessages(messages);
      statusEl.textContent = payload.model ? `Ready · ${payload.model}` : "Ready";
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unexpected operator error.";
      messages = messages.concat([{ role: "assistant", content: `Error: ${message}` }]).slice(-maxMessages);
      saveMessages(messages);
      renderMessages(messages);
      statusEl.textContent = "Error";
    } finally {
      setBusy(false, statusEl.textContent === "Thinking..." ? "Ready" : statusEl.textContent);
      inputEl.focus();
    }
  });
})();
