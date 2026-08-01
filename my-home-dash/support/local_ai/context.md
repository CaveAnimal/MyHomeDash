# Local AI Context

> Scope: local AI chat support for My Home Dash using a locally hosted Ollama model on this Windows workstation.

## Current Objective

The local_ai workstream exists to support a private, local-first chat experience inside My Home Dash. The target runtime is Ollama serving `granite3.3:8b` on the RTX 3060 GPU, with the dashboard acting as the UI and Flask acting as the backend proxy.

## Current System State

The project is no longer at a blank-slate stage. The core chat path already exists in the dashboard application.

### What Is Already Implemented

- `app.py` exposes `POST /api/chat` and forwards chat requests to Ollama using the Python `requests` library.
- `app.py` trims conversation history, prepends a configurable system prompt, and returns a single assistant reply to the browser.
- `templates/dashboard.html` includes a visible `Local AI Chat` card on the home page.
- `static/dashboard.js` manages message history in `localStorage`, sends requests to `/api/chat`, renders replies, and surfaces error text in the thread.
- `config.yaml` already contains an `llm` section with `base_url`, `model`, `timeout_seconds`, `keep_alive`, `temperature`, `max_history_messages`, and `system_prompt`.
- `start_granite3_3_8b.ps1` and `start_granite3_3_8b.cmd` automate model warmup and basic GPU verification.
- `benchmark_ollama_model.py` measures first-token latency and throughput for the target model.
- `system_capacity.md` documents machine capacity, Ollama inventory, and benchmark results.

### What This Means

- The main integration path is present.
- The remaining work is about hardening, verification, documentation alignment, and operational clarity rather than initial feature construction.

## Relevant Files

| File | Purpose |
|------|---------|
| `my-home-dash/app.py` | Flask app, chat proxy route, message shaping, Ollama call |
| `my-home-dash/config.yaml` | User-configurable local LLM settings |
| `my-home-dash/static/dashboard.js` | Browser chat state, submit flow, rendering, clear/status UX |
| `my-home-dash/templates/dashboard.html` | Dashboard chat panel markup |
| `my-home-dash/support/local_ai/start_granite3_3_8b.ps1` | Windows startup and warmup automation |
| `my-home-dash/support/local_ai/start_granite3_3_8b.cmd` | Wrapper for easier manual or scheduled launch |
| `my-home-dash/support/local_ai/benchmark_ollama_model.py` | Local benchmark runner against Ollama |
| `my-home-dash/support/local_ai/ollama_inventory.py` | Updates the Ollama inventory section in the capacity report |
| `my-home-dash/support/local_ai/system_capacity_report.py` | Collects hardware and runtime facts for local model planning |
| `my-home-dash/support/local_ai/system_capacity.md` | Generated operational report and benchmark notes |

## Runtime Architecture

### Request Flow

1. User types a message into the Local AI chat card on the dashboard home page.
2. `static/dashboard.js` appends the user message to local browser history and POSTs `{ messages }` to `/api/chat`.
3. `app.py` validates the request and shapes the payload with a system prompt plus bounded recent history.
4. `app.py` calls `Ollama /api/chat` at the configured base URL.
5. Ollama returns one non-streaming assistant message.
6. Flask returns JSON containing the reply content and model name.
7. The browser appends the assistant response and updates chat status text.

### Deployment Shape

- UI host: local browser on the same machine as the Flask app.
- App server: Flask process started from `my-home-dash/app.py`.
- Model runtime: local Ollama service on `http://127.0.0.1:11434`.
- Model target: `granite3.3:8b` by default.
- Operating environment: Windows 11, local workstation, RTX 3060 12 GiB GPU.

## Technical Stack

| Area | Technology | Notes |
|------|------------|-------|
| Backend web app | Flask | Handles dashboard rendering and chat proxying |
| Frontend behavior | Vanilla JavaScript | Maintains thread state and API calls |
| HTTP client | `requests` | Used by Flask to call Ollama |
| Local model runtime | Ollama | Expected to be reachable locally |
| Model | `granite3.3:8b` | Preferred fit for current GPU capacity |
| Automation | PowerShell + CMD wrapper | Startup warmup and verification on Windows |
| Benchmarking | Python | Measures latency and throughput |

## Hard Constraints

- The chat path must remain local-first and must not depend on a cloud LLM.
- The default model remains `granite3.3:8b` unless deliberately overridden in configuration.
- The solution must work on this Windows machine and align with the current project layout.
- Existing dashboard modules must continue to function.
- Failure behavior must be visible and actionable instead of hanging silently.
- Browser code must not call Ollama directly; backend mediation is the intended architecture.

## Operational Facts Already Verified

- Ollama is installed on this workstation.
- `granite3.3:8b` has already been downloaded.
- The startup script has successfully warmed the model.
- Prior verification captured `ollama ps` showing GPU residency.
- Benchmarks in `system_capacity.md` show practical local latency for the target model on this machine.

## Known Gaps Or Follow-Up Areas

- There is no dedicated local AI health endpoint separate from the main chat call.
- The current chat path is non-streaming, so long responses wait for completion before rendering.
- The dashboard README does not yet appear to explain the local AI setup path as thoroughly as the support docs do.
- There is no explicit server-side request size guard beyond bounded history trimming.
- Graceful handling exists, but status distinctions such as `warming`, `unreachable`, and `empty response` could still be made more explicit if needed.

## Guidance For Future Work

- Treat the current implementation as the baseline rather than re-planning the feature from scratch.
- Prefer incremental hardening over architectural churn.
- Keep documentation aligned with the real runtime scripts in this folder.
- Re-verify GPU use with `ollama ps` and `nvidia-smi` whenever model behavior changes.