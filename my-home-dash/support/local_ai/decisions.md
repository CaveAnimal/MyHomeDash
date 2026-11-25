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

- Status: superseded by Decision 9 (2026-11-24)
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

- Status: superseded by Decision 9 (2026-11-24)
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

## Decision 8: Auto-Detect Whichever Model Is Loaded In GPU VRAM, Fall Back To Granite

- Status: superseded by Decision 9 (2026-11-24)
- Decision: At chat request time, the backend queries Ollama's `/api/ps` and, if that reports
  nothing loaded, LM Studio's `/api/v0/models` (which exposes a `state: "loaded"` field per
  model). Whichever backend reports a resident model is used for that request. If neither
  reports a loaded model, the code falls back to `config.yaml`'s `llm.model`
  (`granite3.3:8b`) via Ollama, exactly as before.
- Why: This machine now also runs LM Studio, and only one runtime tends to hold the GPU at a
  time. Hardcoding Granite meant the dashboard could sit idle waiting on Ollama to cold-load a
  model while a different model was already warm in VRAM. Detecting the resident model lets the
  dashboard use whatever is already paid for in load time, without abandoning Granite as the
  documented default.
- Alternatives considered:
  - Add a config flag to pick Ollama vs. LM Studio: rejected because it requires the user to
    remember to flip it every time they switch runtimes; detection removes that step entirely.
  - Only support Ollama and require the user to load models exclusively through it: rejected
    because it would force LM Studio out of the workflow rather than working with it.
- Consequences:
  - `_call_llm_chat` and the operator loop's `_call_llm_raw` now branch on backend
    (`ollama`'s native `/api/chat` vs. LM Studio's OpenAI-compatible `/v1/chat/completions`)
    and normalize both response shapes to the same `{"model", "message"}` envelope.
  - Two local probe requests (short 2s timeout each) run before every chat call. Both are
    lightweight metadata endpoints, so this stays fast when either service is up, and fails
    closed to the Granite fallback quickly when neither is reachable.
  - The `model` field returned to the browser now reflects whatever actually answered, not the
    static config value.
  - `config.yaml` gained `llm.lm_studio_base_url` (defaults to `http://127.0.0.1:1234`).
- Rollback path: Remove `_detect_gpu_backend`/`_resolve_llm_target` and have `_call_llm_raw`
  always target `llm.base_url`/`llm.model` directly, restoring the original Granite-only path.

## Decision 9: Retire Granite; Bonsai 2 27B Is The Only Default Model

- Status: accepted (2026-11-24). Supersedes Decision 2, Decision 5's Granite startup scripts,
  and the Granite fallback in Decision 8.
- Decision: Chat targets Bonsai 2 27B, served by PrismML's llama.cpp fork on
  `http://127.0.0.1:1080`. `start_or_restart_mhd.ps1` starts Bonsai through
  `E:\AI\models\Bonsai\Bonsai-demo\scripts\start_llama_server.ps1` when it is not already
  running. `start_granite3_3_8b.ps1` and `start_granite3_3_8b.cmd` have been deleted, and
  `llm.model: granite3.3:8b` has been removed from `config.yaml`.
- Why: The user chose to stop using Granite. Bonsai already runs on this machine, and it emits
  native `tool_calls`.
- Consequences:
  - Ollama and LM Studio are still checked, but only when Bonsai is down and only for a model
    that is already loaded. Neither is ever asked to load a model.
  - `benchmark_ollama_model.py` still defaults to `--model granite3.3:8b`. Pass `--model`
    explicitly if you use it.
  - Earlier docs in this folder that mention Granite describe history, not current behavior.
- Rollback path: Restore the two scripts from git history and re-add `llm.model`.
