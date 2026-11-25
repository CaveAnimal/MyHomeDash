# AI Operator Context

> Scope: turning the existing local chat into a tool-calling operator for My Home Dash.

## Runtime Today

- Since 2026-11-22 the operator runs on **Bonsai 2 27B**, served by PrismML's llama.cpp fork at
  `http://127.0.0.1:1080` through the OpenAI-compatible `/v1/chat/completions` API. Granite 3.3
  via Ollama is retired (see `support/local_ai/decisions.md` Decision 9).
- Verified live on 2026-11-24: asked for the current date and time, Bonsai returned a native
  `tool_calls` entry for `get_current_datetime`, the loop ran it, and the final answer matched
  the tool result.
- The section below describes the state when this workstream started, with Granite on Ollama.

## Current System State (before this workstream)

- `support/local_ai` shipped a working chat path: browser → `/api/chat` → Ollama
  (`granite3.3:8b`) → reply. No tool-calling; explicitly out of scope there.
- `support/access_internet` added a narrow, regex-triggered retrieval shortcut
  (`modules/web_retrieval.py`) that short-circuits certain questions (capability questions,
  AI headlines, URL fetch, DuckDuckGo instant answer) before or instead of calling Ollama.
  This is pattern-matching on the question text, not model-driven tool selection.
- Calendar, email, GitHub, and Teams are disabled in `config.yaml` (`dashboard.enabled_sections`
  only lists `weather` and `news`) pending real credentials — see `BACKLOG.md`.
- Ollama 0.32.1 is installed and running locally; `granite3.3:8b` has been pulled and verified
  100% GPU-resident on the RTX 3060 (`ollama ps`).

## What This Workstream Adds

- A real tool registry (`modules/operator_tools.py`) with JSON-schema tool definitions in the
  `tools` format both Ollama and OpenAI-compatible servers understand, plus Python handlers.
- A new Flask route `/api/operator` implementing the tool-calling loop: send messages + tools
  to the model, if it returns `tool_calls`, execute them against the registry, feed results
  back as `role: "tool"` messages, call the model again, repeat up to a small max, then return the
  final answer plus a trace of which tools ran.
- A dedicated `/operator` page reusing the existing chat UI pattern (`partials/chat.html`,
  `dashboard.js`) so the feature is actually usable, not just curl-testable.
- The first tool, `get_dashboard_status`, wraps the same cache/enabled-sections data that
  `/api/status` already exposes — no new data source, just exposing existing state to the model
  as a callable function instead of a fixed JSON endpoint.

## Relevant Files

| File | Purpose |
|------|---------|
| `my-home-dash/app.py` | Existing Flask app; gets a new `/api/operator` route and `/operator` page |
| `my-home-dash/modules/operator_tools.py` | New — tool registry and dispatcher |
| `my-home-dash/config_loader.py` | Existing — reused for enabled/disabled section lookups |
| `my-home-dash/templates/operator.html` | New — dedicated operator page |
| `my-home-dash/templates/partials/operator_chat.html` | New — operator chat panel markup |
| `my-home-dash/static/dashboard.js` | Gets a second chat-panel IIFE targeting the operator endpoint |
| `my-home-dash/support/local_ai/*.md` | Prior workstream this one builds on; do not contradict its decisions about `/api/chat` |

## Tool-Calling Contract (as used here)

`app.py::_call_llm_raw` speaks two dialects and normalizes both to `{"model", "message"}`.
Bonsai uses the OpenAI-compatible one. The Ollama one remains only for the fallback case where
Bonsai is down and Ollama already has a model loaded.

1. POST `/v1/chat/completions` to Bonsai with `messages`, `tools` (array of
   `{type: "function", function: {name, description, parameters}}`), `stream: false`.
2. If the model wants a tool, `choices[0].message.tool_calls` is a list of
   `{id, type, function: {name, arguments}}`.
3. For each call, the backend runs the matching registry handler and appends
   `{role: "tool", content: <json-encoded result>}` to the conversation.
4. The backend calls the model again with the extended message list. This repeats until the
   model returns a plain content reply or the 4-round cap is hit.

Two differences from the original Ollama contract are handled in `_run_operator`:

- **`arguments` is a JSON string** in the OpenAI format (Ollama returns an object).
  `_parse_tool_arguments` normalizes both to a dict before `operator_tools.dispatch`, so
  handlers always receive a dict. Arguments that are not a JSON object come back to the model
  as an error result, and the handler is not called.
- **Tool results carry `tool_call_id`** copied from the call's `id`, as the OpenAI format
  expects. Ollama calls have no `id`, so the field is omitted for them.

## Hard Constraints

- No tool executes in the browser — only backend Python calls the model and runs handlers.
- The tool-calling loop must cap iterations (planned: 4) to avoid runaway loops.
- Tools that are `action: true` are not yet implemented in this phase; when they are, they must
  require confirmation before executing (see `decisions.md` Decision 1 and 3).
- `/api/chat` (plain chat) must keep working exactly as before — this is additive, not a
  replacement.

## Known Gaps / Follow-Up Areas

- No action tools exist yet, so the confirmation-gate mechanism is designed but not yet
  exercised by a real state-changing tool. Build the first action tool carefully once needed
  (likely a safe one first, e.g. "refresh a section" wrapping the existing
  `/api/refresh/<section>` behavior) and confirm the gate actually blocks unconfirmed calls
  before adding anything that touches external accounts.
- Calendar/email/GitHub/Teams tools are blocked on those integrations being enabled first —
  see `BACKLOG.md`'s re-enable checklist.

## Guidance For Future Work

- Treat `get_dashboard_status` as the reference pattern for adding more read-only tools
  (weather, news, irrigation project) before attempting any action tool.
- Do not let the operator and the plain chat paths merge into one endpoint — keeping them
  separate preserves the local_ai workstream's decision to keep chat simple and non-streaming.
- Re-verify tool-calling behavior with a live operator request after any change to the Bonsai
  runtime or model file, since function-calling support can vary by runtime version.
