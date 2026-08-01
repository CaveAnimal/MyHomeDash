# Local AI TODO

## Overall Status

- Goal document exists.
- Core local chat implementation exists.
- Local runtime startup and benchmark tooling exists.
- Context, decisions, and TODO tracking now exist in this folder.
- Remaining work is primarily verification, hardening, and documentation alignment.

## Completed

- [x] Add a Local AI chat panel to the dashboard UI.
- [x] Add frontend chat behavior for submit, clear, local history, and status text.
- [x] Add Flask backend proxy route at `/api/chat`.
- [x] Add configurable local LLM settings in `config.yaml`.
- [x] Create Windows startup automation for Granite 3.3 warmup.
- [x] Create system capacity and benchmark tooling for local model validation.
- [x] Verify that `granite3.3:8b` can be loaded locally on GPU on this workstation.
- [x] Create supporting planning documents in `support/local_ai/`.

## Active Work Queue

### 1. Verify End-To-End Chat Against The Live Local Runtime

- Status: next
- Why it matters: The code path exists, but the feature should be re-verified from browser to Flask to Ollama after any dashboard or runtime changes.
- Acceptance criteria:
  - Send a real prompt from the dashboard UI.
  - Confirm the reply renders in the same thread.
  - Confirm a temporary Ollama outage produces a visible failure state instead of a hang.
  - Confirm the configured model reported back by the API matches the expected runtime.

### 2. Align Top-Level Documentation With The Implemented Local AI Feature

- Status: next
- Why it matters: The README currently describes the dashboard broadly, but local AI setup and startup flow should be easy to find without digging through support notes.
- Acceptance criteria:
  - README includes the local AI prerequisites.
  - README explains where to configure model settings.
  - README links or points to the startup and benchmark scripts in `support/local_ai`.

### 3. Add A Dedicated Local AI Health Check Or Readiness Probe

- Status: candidate
- Why it matters: Right now readiness is inferred through chat or external commands. A dedicated health path would make diagnostics simpler.
- Acceptance criteria:
  - A lightweight endpoint reports whether Ollama is reachable.
  - Response includes the configured model and a clear readiness state.
  - UI can distinguish `ready`, `warming`, and `unavailable` more precisely if desired.

### 4. Tighten Request Validation And Failure Messaging

- Status: candidate
- Why it matters: The base error handling works, but it can still be made more explicit and operationally useful.
- Acceptance criteria:
  - Invalid or oversized requests are rejected cleanly.
  - Empty model responses are surfaced with a specific message.
  - Logs remain useful without leaking unnecessary details to the UI.

### 5. Decide Whether Streaming Responses Are Worth The Added Complexity

- Status: deferred
- Why it matters: Non-streaming is simpler, but streaming could improve perceived responsiveness for longer replies.
- Acceptance criteria:
  - Measure whether current latency is acceptable for real use.
  - If not acceptable, define the smallest viable streaming design.
  - Preserve existing error handling and UI stability if streaming is introduced.

## Working Notes

- Do not treat this feature as greenfield anymore.
- Preserve the existing backend proxy architecture unless there is a strong reason to change it.
- Re-run GPU verification with `ollama ps` and `nvidia-smi` after any runtime or model changes.
- Prefer small hardening steps over major refactors.