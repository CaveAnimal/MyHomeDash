# Local AI Decisions

This document records the key implementation choices for the local AI chat capability and the rationale behind them.

## Decision 1: Use A Backend Proxy Instead Of Browser-To-Ollama Calls

- Status: accepted
- Decision: The browser sends chat requests to Flask at `/api/chat`, and Flask calls Ollama.
- Why: This keeps the runtime local but still centralizes request shaping, model configuration, history trimming, and error handling in one place.
- Alternatives considered:
  - Direct browser calls to Ollama: rejected because it would expose runtime assumptions to the frontend and reduce control over request validation.
  - Separate local AI microservice: rejected because it adds complexity without clear benefit for a single-user local dashboard.
- Consequences:
  - Backend owns the chat contract.
  - Frontend stays simpler.
  - Errors from Ollama can be normalized before reaching the browser.
- Rollback path: If this approach becomes too limiting, extract the proxy logic into a dedicated internal service without changing the browser contract first.

## Decision 2: Standardize On `granite3.3:8b` As The Default Model

- Status: accepted
- Decision: Default model configuration is `granite3.3:8b`.
- Why: The existing system capacity and benchmark work shows it fits the RTX 3060 12 GiB envelope well enough for practical local interaction while remaining strong enough for assistant-style tasks.
- Alternatives considered:
  - Larger models: rejected as the default because GPU spill or CPU fallback would increase latency too much for chat UX.
  - Smaller models: rejected as the primary default because they may reduce reasoning quality more than necessary on this hardware.
- Consequences:
  - Documentation, scripts, and config should use the same default unless intentionally overridden.
  - GPU verification remains important because incorrect runtime behavior can silently degrade responsiveness.
- Rollback path: Change only `config.yaml` and startup script defaults if a better local model is validated later.

## Decision 3: Keep Chat History Bounded

- Status: accepted
- Decision: Send only the most recent bounded message window to the backend and persist a limited thread in browser storage.
- Why: Local chat responsiveness matters more than unlimited history on this dashboard. Bounding the conversation reduces payload size, keeps UI behavior predictable, and avoids needless context bloat.
- Current implementation:
  - Frontend caps saved messages in `localStorage`.
  - Backend limits the number of history messages included in the Ollama payload.
- Alternatives considered:
  - Unlimited browser history: rejected because it grows payloads and makes failures harder to reason about.
  - Server-side session storage: rejected for now because this is a local single-user dashboard and client-side persistence is simpler.
- Consequences:
  - Very long conversations will lose older context.
  - Performance is more stable.
- Rollback path: Move to summarized history or server-managed sessions if longer context becomes a real requirement.

## Decision 4: Use Non-Streaming Responses First

- Status: accepted for current phase
- Decision: The backend calls Ollama with `stream: false` for the dashboard chat route.
- Why: Non-streaming is simpler to implement and reason about, especially while validating basic reliability and error handling.
- Alternatives considered:
  - Streaming token-by-token responses: deferred because it adds frontend and backend complexity that is not required to prove the base feature.
- Consequences:
  - Users wait for full response completion before text appears.
  - Simpler API handling and fewer UI edge cases.
- Rollback path: Introduce streaming later behind the same UI card if the current latency becomes the main UX complaint.

## Decision 5: Warm The Model Through Windows Startup Automation

- Status: accepted
- Decision: Use `start_granite3_3_8b.ps1` and its CMD wrapper to pull, warm, and verify the model on this machine.
- Why: The main operational risk is that Ollama is unavailable or the model is not GPU-resident when the dashboard is used. Startup automation reduces that risk.
- Alternatives considered:
  - Manual warmup only: rejected because it is easy to forget and creates inconsistent user experience.
  - Embedding warmup into Flask startup: rejected for now because app startup should remain light and not silently manage a full model lifecycle.
- Consequences:
  - Local AI readiness becomes an explicit operational step.
  - Task Scheduler can be used to prepare the model at logon.
- Rollback path: Remove scheduled startup and rely on on-demand warmup if background residency proves unnecessary.

## Decision 6: Surface Failures In The Chat Thread And Status Label

- Status: accepted
- Decision: When chat requests fail, the UI appends an assistant-style error message and updates the status text instead of failing silently.
- Why: This dashboard is user-facing, and local runtime failures are expected enough that they must be visible.
- Alternatives considered:
  - Silent logging only: rejected because the user would not know whether the model is unavailable or merely slow.
  - Modal-only errors: rejected because they interrupt the dashboard flow more than necessary.
- Consequences:
  - Users can see immediate failure feedback.
  - Some implementation details may still need refinement so the messaging is more operationally precise.
- Rollback path: Move error display to a dedicated status panel if inline thread errors become noisy.

## Decision 7: Keep Local AI Work In `support/local_ai`

- Status: accepted
- Decision: Operational scripts, machine reports, and planning documents for local AI stay grouped under `my-home-dash/support/local_ai/`.
- Why: This keeps experimental and operational support material out of the main application root while keeping it close to the project.
- Alternatives considered:
  - Put scripts at repository root: rejected because it would clutter the top-level project structure.
  - Store docs separately from scripts: rejected because the docs are tightly coupled to the runtime tooling in this folder.
- Consequences:
  - The folder acts as the working area for local AI enablement.
  - Documentation should stay synchronized with the scripts here.
- Rollback path: Split generated reports from hand-authored docs later if the folder becomes too crowded.