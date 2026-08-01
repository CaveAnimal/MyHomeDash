# AI Operator Goal

## Primary Objective

Evolve the local Granite chat experience into an "operator" that can call real tools against
My Home Dash's own data and actions, instead of only producing text answers.

## Why This Matters

- The Local AI chat (`support/local_ai`) explicitly scoped out tool-calling and multi-step
  orchestration. This workstream is where that excluded work happens.
- The system capacity report already identified `granite3.3:8b` as a good local fit for
  function-calling agent loops on this hardware — this workstream puts that to use.
- A dashboard that can *act* (not just describe) is more useful day-to-day than one that only
  narrates status.

## Success Criteria

- [ ] The operator can call at least one real tool (`get_dashboard_status`) and use its result
      to answer a question truthfully instead of guessing.
- [ ] The tool-calling loop is bounded (max iterations) and fails visibly, never hangs, if
      Ollama or a tool errors.
- [ ] Every tool the operator can call is registered with an explicit `action: bool` flag
      distinguishing read-only tools from state-changing ones.
- [ ] The user can see which tools were called and with what result (transparency), not just
      the final answer.
- [ ] The existing `/api/chat` path (plain chat, no tools) is untouched — the operator lives on
      its own `/api/operator` path so the two concerns don't blend.

## In Scope

- A tool registry (name, JSON-schema parameters, Python handler, `action` flag).
- A bounded tool-calling loop in Flask that talks to Ollama's `tools` API and executes calls
  against the registry.
- A first read-only tool surfacing dashboard/module health so the operator can answer
  "is everything working?" truthfully.
- A dedicated Operator page/panel so this is testable as a real feature, not just an API.
- A safety pattern for future action tools: any tool with `action: true` must be confirmed
  before executing (see Decisions).

## Explicitly Out Of Scope (for this first pass)

- ❌ Actually wiring calendar/email/GitHub/Teams actions — those integrations are still
  disabled per `BACKLOG.md` and have no credentials yet. Action tools against them come later,
  once each integration is verified working on its own.
- ❌ Streaming responses (matches the existing non-streaming decision in `support/local_ai`).
- ❌ A general-purpose plugin system for arbitrary user-defined tools.
- ❌ Removing or weakening the plain `/api/chat` path.

## Non-Negotiable Constraints

- Model inference stays local through Ollama; no cloud LLM calls.
- Tool execution happens in backend Python, never in the browser.
- Any tool marked `action: true` requires explicit confirmation before it runs — the model
  proposing a call is not sufficient authorization by itself.
- The tool-calling loop must have a hard iteration cap so a confused model can't loop forever.
- Failures (Ollama down, tool exception, malformed tool call) must return a visible error, not
  a hang or a silent wrong answer.

## Target End State

The user's stated goal for this workstream is a **full action-taking operator** — eventually
able to do things like draft email replies, refresh sections, or act on calendar/Teams once
those integrations are live — not just report on them. This goal document tracks that
direction, but the first implementation slice is intentionally read-only (see
`decisions.md` Decision 1) so the tool-calling framework and safety gate exist and are proven
before any action tool is added.

## Definition Of Done (this phase)

This phase is complete when a user can ask the operator a status-style question, watch it call
`get_dashboard_status`, and get a truthful answer grounded in that tool's result — with the
tool call visible in the UI and the whole path failing gracefully if Ollama or the tool breaks.
