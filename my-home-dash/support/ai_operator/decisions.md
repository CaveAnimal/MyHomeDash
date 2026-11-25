# AI Operator Decisions

## Decision 1: Ship Read-Only Tools First, Even Though The Target Is Action-Taking

- Status: accepted
- Decision: The target end state (per the user) is an operator that can take real actions.
  The first implementation slice ships only a read-only tool (`get_dashboard_status`).
- Why: Tool-calling itself (the loop, the registry, the failure handling) is new and unproven
  in this codebase. Proving it with a read-only tool means a bug can only produce a wrong
  answer, not a wrong action. Action tools are added once the loop is trusted.
- Alternatives considered:
  - Build an action tool immediately (e.g. draft-email): rejected because there is no verified
    tool-calling loop yet to safely carry it, and the target integrations (email, calendar)
    are not even enabled.
- Consequences:
  - Positive: low blast radius while the mechanism is new.
  - Negative: the "full action-taking operator" the user asked for isn't realized yet — this is
    step one of a sequence, not the whole thing.
- Rollback: N/A — this only adds capability, nothing to roll back.

## Decision 2: Separate `/api/operator` Endpoint Instead Of Extending `/api/chat`

- Status: accepted
- Decision: Tool-calling lives on a new `/api/operator` route. `/api/chat` is untouched.
- Why: `support/local_ai` deliberately kept `/api/chat` simple and scoped chat to no
  tool-calling. Bolting tool-calling onto that path would silently violate that decision and
  make plain chat slower/more complex for every request, even ones that don't need a tool.
- Alternatives considered:
  - Add an optional `tools: true` flag to `/api/chat`: rejected — same endpoint carrying two
    very different behaviors is harder to reason about and test.
- Consequences:
  - Two feature-level code paths exist (`_call_llm_chat` and the operator's loop). They now
    share a single backend-selecting low-level call (`_call_llm_raw`, added when GPU-model
    auto-detection landed — see `support/local_ai/decisions.md`), so the duplication that
    remains is at the feature layer, not the HTTP-call layer.
- Rollback: If the split proves artificial, merge behind a single endpoint later — the UI
  contract (`messages` in, `content` + trace out) is compatible either way.

## Decision 3: Action Tools Require A Confirmation Gate Before Execution

- Status: accepted (design now; no action tool exists yet to exercise it)
- Decision: Every tool in the registry carries an `action: bool` field. Tools with
  `action: True` are not executed automatically just because the model requested them — the
  planned mechanism is to return the proposed call to the user for confirmation before running
  it, rather than auto-executing.
- Why: A model choosing to call a tool is not the same as the user authorizing a side effect.
  Given the user wants this operator to eventually draft emails / touch calendar data, an
  unconfirmed auto-execute path is the single biggest risk in this workstream.
- Alternatives considered:
  - Auto-execute everything the model proposes: rejected outright — this is exactly the
    "uncontrolled agent" failure mode the local_ai and access_internet goal docs both warned
    against.
  - Per-tool allowlist configured in `config.yaml` with no runtime confirmation: deferred —
    still worth doing later as a second layer, but confirmation is the primary gate.
- Consequences:
  - Read-only tools run immediately; nothing changes for them.
  - When the first action tool is built, the operator loop must pause and surface the proposed
    call instead of executing it, and only proceed after explicit user confirmation.
- Rollback: If confirmation proves too heavy for a specific low-risk action (e.g. "refresh a
  section", which is already exposed unauthenticated via `/api/refresh/<section>`), that
  specific tool can be reclassified with a documented exception here — not by removing the gate
  globally.

## Decision 4: Bound The Tool-Calling Loop To A Fixed Iteration Cap

- Status: accepted
- Decision: The operator loop calls the model, executes any requested tools, and repeats up to a
  hard cap (planned: 4 rounds) before forcing a final answer or an explicit error.
- Why: Local models can loop on tool calls if a tool result doesn't satisfy them. An unbounded
  loop on a local GPU is a real resource/hang risk, not just a cost concern.
- Alternatives considered:
  - No cap, trust the model to stop: rejected — matches the same "must fail visibly, never
    hang" constraint already established for the chat and retrieval workstreams.
- Consequences: Very rarely, a legitimately multi-step question might get cut off at the cap.
  Acceptable for this phase; revisit the cap value with real usage data.
- Rollback: Adjust the constant in one place (`app.py`); no structural change needed.

## Decision 5: Reuse The Existing Chat UI Pattern For The Operator Panel

- Status: accepted
- Decision: The operator page is a new template + route following the same shape as
  `/ai-chat` (`partials/chat.html`, `dashboard.js` IIFE pattern), not a new UI framework or
  component system.
- Why: Consistency with the rest of the dashboard (Decision 4 in the top-level plan.md:
  Flask + Jinja2 + Bootstrap + vanilla JS, no build step) and less code to maintain.
- Alternatives considered:
  - A richer JS framework for the operator panel specifically: rejected — inconsistent with the
    whole project's "no npm, no bundler" decision.
- Consequences: The operator panel shows tool-call trace as simple text/badges appended to the
  assistant message, same as the retrieval note pattern already used in chat.
- Rollback: N/A.

## Decision 6: Withhold The System Message Until A Tool Result Exists

- Status: accepted; the Granite-specific reason no longer applies (see Decision 7), but the behavior is kept
- Decision: The operator loop does not send any `role: "system"` message on the first call to
  Ollama (the one offered `tools` with no prior tool result). A system message is only added
  once the transcript already contains a `role: "tool"` message.
- Why: Verified directly against Ollama 0.32.1 — `granite3.3:8b` reliably returns structured
  `message.tool_calls` when a request has `tools` and no system message. The moment a system
  message is added to that same request (tested with both a long instructive prompt and a
  one-line identity prompt), the model stops emitting structured tool calls and instead
  narrates a fake function call as plain text content, which the loop cannot execute. This was
  confirmed by comparing three otherwise-identical curl requests to Ollama directly.
- Alternatives considered:
  - Keep the system message and try to parse the model's narrated pseudo-JSON tool call out of
    `content`: rejected — fragile text-parsing of model output is exactly the kind of
    "hallucinated tool use" this workstream is trying to avoid.
  - Drop the system message permanently, even after tool results exist: rejected — once a tool
    result is already in the transcript, grounding guidance ("answer from the tool result,
    don't guess") measurably improves the final answer and no longer needs to compete with
    reliable tool selection.
- Consequences:
  - The first round of any operator request runs with no explicit guardrail prompt; tool
    descriptions alone must carry the guidance for that round.
  - If a later round asks the model to call a *second* different tool, structured calling could
    regress again in that round because a system message is now present. Acceptable for the
    current single-tool phase; revisit if/when multi-tool chains become common.
- Rollback: If future Ollama/Granite versions fix this interaction, the guard (`has_tool_result`
  check in `app.py::_run_operator`) can be removed and the system message restored to every
  round.

## Decision 7: Run The Operator On Bonsai 2 27B Via llama.cpp

- Status: accepted (2026-11-24)
- Decision: The operator loop now talks to Bonsai 2 27B through llama.cpp's OpenAI-compatible
  `/v1/chat/completions` API at `http://127.0.0.1:1080`. Granite 3.3 via Ollama is retired
  (see `support/local_ai/decisions.md` Decision 9). The Ollama code path stays only as a
  fallback for a model that is already loaded while Bonsai is down.
- Why: The user switched the dashboard's local model to Bonsai. Bonsai emits native
  `tool_calls`, including when a system message is present.
- Consequences:
  - Decision 6's workaround is no longer required. It is kept on every backend because it is
    harmless and keeps the first round focused on choosing a tool (see the `_run_operator`
    docstring in `app.py`).
  - Tool-call `arguments` now arrive as a JSON string rather than an object.
    `_parse_tool_arguments` normalizes them to a dict, and anything that is not a JSON object
    is returned to the model as an error result.
  - Tool result messages now carry `tool_call_id` when the call has an `id`.
  - Verified live on 2026-11-24 with a `get_current_datetime` round trip.
- Rollback path: Point `llm.bonsai_base_url` at another local OpenAI-compatible server. The
  loop does not depend on Bonsai specifically.