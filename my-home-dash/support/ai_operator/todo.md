# AI Operator TODO

## Overall Status

- Goal, context, and decisions documents created.
- First implementation slice shipped and verified end-to-end: `get_dashboard_status` tool,
  bounded tool-calling loop, dedicated `/operator` page, plain `/api/chat` unaffected.
- Discovered and worked around a real Granite 3.3 + Ollama 0.32.1 quirk: any system message
  alongside `tools` breaks structured `tool_calls` (see decisions.md, Decision 6).

## Completed

- [x] Verify the existing dashboard and Local AI chat actually work end-to-end before building
      on top of them (Ollama warmed + GPU-resident, Flask started clean, weather/news `ok`,
      `/api/chat` returned a real reply).
- [x] Scope this workstream with the user: target is a full action-taking operator; first tool
      is read-only `get_dashboard_status`; action tools require confirmation before executing.
- [x] Create `goal.md`, `context.md`, `decisions.md`, `todo.md` for `support/ai_operator`.

## Completed (This Slice)

### 1. Build The Tool Registry

- [x] Create `modules/operator_tools.py` with a tool registry (schema + handler + `action`
      flag per tool) and a `dispatch(name, arguments, cache)` function.
- [x] Implement `get_dashboard_status` (read-only): enabled sections, disabled sections with the
      reason from `BACKLOG.md` (credentials pending), and per-section cache status.

### 2. Build The Operator Endpoint

- [x] Add `/api/operator` POST route in `app.py`.
- [x] Implement the bounded tool-calling loop (cap: 4 rounds) against Ollama's `tools` API.
- [x] Return `{content, model, tool_calls: [{name, arguments, result}]}` so the UI can show the
      trace.
- [x] Fail visibly (never hang) on: Ollama unreachable (502), malformed request (400), unknown
      tool name (error result fed back to the model), tool exception (caught in `dispatch`),
      empty final content (502).
- [x] Discover and fix a real regression: system message + `tools` breaks structured
      `tool_calls` for `granite3.3:8b` on this Ollama version; withhold the system message until
      a tool result exists (Decision 6).

### 3. Build The Operator Page

- [x] Add `templates/partials/operator_chat.html` (same shape as `partials/chat.html`).
- [x] Add `templates/operator.html` (same shape as `templates/ai_chat.html`).
- [x] Add `/operator` route in `app.py`.
- [x] Add nav link and homepage link ("AI Operator").

### 4. Wire The Frontend

- [x] Add a second chat-panel IIFE in `dashboard.js` targeting `/api/operator` and rendering the
      tool-call trace under each assistant reply (mirroring the retrieval-note pattern already
      used for plain chat).

### 5. Verify End-To-End

- [x] Restart the dashboard — clean startup, no import/route errors.
- [x] Ask a status-style question via curl and confirm the model calls `get_dashboard_status`
      and answers using its real result: correctly named all 4 disabled sections and their
      reasons, matching `/api/status` exactly.
- [x] Confirm bad input (`{"messages": []}`) returns 400, not a hang.
- [x] Confirm `/api/chat` (plain chat) still works unchanged after the operator changes.
- [ ] Click through the actual `/operator` page in a browser (only the API path has been
      verified so far — the UI itself has not been visually exercised).

## Deferred (Next Phase — Action Tools)

- [ ] Design and implement the confirmation-gate mechanism for `action: true` tools (Decision 3
      in `decisions.md`) — not yet exercised by a real tool.
- [ ] Candidate first action tool: wrap the existing `/api/refresh/<section>` behavior as an
      operator tool, since it's already an unauthenticated, reversible, in-process action —
      good for proving the confirmation gate before anything touches external accounts.
- [ ] Once calendar/email/GitHub/Teams are enabled (see `BACKLOG.md`), add read-only tools for
      each, then consider action tools (draft reply, etc.) only after their read-only
      counterparts are verified.

## Working Notes

- Do not modify `/api/chat` or `modules/web_retrieval.py` while building this — they belong to
  prior, already-accepted workstreams.
- Keep the first pass narrow: one read-only tool, proven end-to-end, before adding more tools
  or any action tool.
