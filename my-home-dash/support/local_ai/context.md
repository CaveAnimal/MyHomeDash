# Local AI Context

> Scope: local AI chat support for My Home Dash, using Bonsai 2 27B hosted locally on this Windows workstation.

## Current Objective

The local_ai workstream supports a private, local-first chat experience inside My Home Dash. The model runtime is Bonsai 2 27B, served by PrismML's llama.cpp fork (`llama-server`) on the RTX 3060 GPU. The dashboard is the UI and Flask is the backend proxy. Granite 3.3 via Ollama was the original target and has been retired (see `decisions.md` Decision 9).

## Current System State

The core chat path is implemented and running against Bonsai.

### What Is Already Implemented

- `app.py` exposes `POST /api/chat`. It resolves the target model with `_resolve_llm_target` and forwards the request through the OpenAI-compatible `/v1/chat/completions` API.
- `app.py` trims conversation history, prepends a configurable system prompt, and returns one assistant reply to the browser.
- `templates/partials/chat.html` renders the Local AI Chat card and shows the active model name.
- `static/dashboard.js` keeps message history in `localStorage`, sends requests to `/api/chat`, renders replies, and shows error text in the thread.
- `config.yaml`'s `llm` section holds `bonsai_base_url`, `bonsai_model`, the fallback runtime URLs, `timeout_seconds`, `temperature`, `max_history_messages`, and `system_prompt`.
- `start_or_restart_mhd.ps1` (repo root) starts Bonsai if it is not already running, waits for the model to load, and then starts the dashboard.
- `system_capacity.md` documents machine capacity, the Ollama inventory, and historical Granite benchmark results.

## Relevant Files

| File | Purpose |
|------|---------|
| `my-home-dash/app.py` | Flask app, chat proxy route, model resolution, message shaping |
| `my-home-dash/config.yaml` | Local LLM settings (`llm` section) |
| `my-home-dash/static/dashboard.js` | Browser chat state, submit flow, rendering, clear/status UX |
| `my-home-dash/templates/partials/chat.html` | Dashboard chat panel markup |
| `start_or_restart_mhd.ps1` | Starts Bonsai if needed, then (re)starts the dashboard |
| `E:\AI\models\Bonsai\Bonsai-demo\scripts\start_llama_server.ps1` | Bonsai launcher (outside this repo; fixed port 1080) |
| `my-home-dash/support/local_ai/benchmark_ollama_model.py` | Benchmark runner against Ollama (not Bonsai; defaults to the retired Granite model) |
| `my-home-dash/support/local_ai/ollama_inventory.py` | Updates the Ollama inventory section in the capacity report |
| `my-home-dash/support/local_ai/system_capacity_report.py` | Collects hardware and runtime facts for local model planning |
| `my-home-dash/support/local_ai/system_capacity.md` | Generated hardware report plus model research and benchmark notes |

## Runtime Architecture

### Request Flow

1. The user types a message into the Local AI chat card on the dashboard home page.
2. `static/dashboard.js` appends the message to local browser history and POSTs `{ messages }` to `/api/chat`.
3. `app.py` validates the request and shapes the payload with a system prompt plus bounded recent history.
4. `app.py` resolves the target: Bonsai at `bonsai_base_url` if `/v1/models` answers. If Bonsai is down, a model that is already loaded in Ollama or LM Studio is used. Otherwise the request goes to Bonsai anyway, so the failure names the intended model.
5. The runtime returns one non-streaming assistant message.
6. Flask returns JSON containing the reply content and the name of the model that answered.
7. The browser appends the reply and updates the chat status text.

### Deployment Shape

- UI host: a local browser on the same machine as the Flask app.
- App server: a Flask process started from `my-home-dash/app.py` on port 1500.
- Model runtime: Bonsai's `llama-server` on `http://127.0.0.1:1080`, with an OpenAI-compatible API.
- Model: `Ternary-Bonsai-2-27B-PQ2_0.gguf`, exposed to the app under the alias `bonsai2-27b`.
- Operating environment: Windows 11, local workstation, RTX 3060 12 GiB GPU.
- At boot, `E:\MyProjects\autostart\start_all.ps1` starts Bonsai and then the dashboard (with `-SkipGranite`, which is now an alias for `-SkipBonsai`).

## Technical Stack

| Area | Technology | Notes |
|------|------------|-------|
| Backend web app | Flask | Handles dashboard rendering and chat proxying |
| Frontend behavior | Vanilla JavaScript | Maintains thread state and API calls |
| HTTP client | `requests` | Used by Flask to call the model runtime |
| Local model runtime | PrismML llama.cpp fork (`llama-server`) | Loads one model at startup and keeps it resident |
| Model | Bonsai 2 27B (ternary, PQ2_0) | Fits the 12 GiB RTX 3060; emits native `tool_calls` |
| Automation | PowerShell | `start_or_restart_mhd.ps1` plus the Bonsai launcher |

## Hard Constraints

- The chat path must stay local-first and must not depend on a cloud LLM.
- Bonsai 2 27B is the default model. Granite is no longer used.
- The app must never cause Ollama or LM Studio to load a model. They are used only if a model is already resident.
- The solution must work on this Windows machine and fit the current project layout.
- Existing dashboard modules must keep working.
- Failures must be visible and actionable instead of hanging silently.
- Browser code must not call the model runtime directly. All calls go through the backend.

## Operational Facts Already Verified

- 2026-11-22: `start_or_restart_mhd.ps1` started Bonsai from a cold state, and `/v1/models` answered within the wait window.
- 2026-11-22: a direct `/v1/chat/completions` request to Bonsai returned the expected reply with `finish_reason: stop`.
- Bonsai is a reasoning model. A very small `max_tokens` (for example 10) can use up the budget on reasoning and return empty content.

## Known Gaps Or Follow-Up Areas

- There is no dedicated local AI health endpoint separate from the main chat call.
- The chat path is non-streaming, so long responses render only after they finish.
- There is no explicit server-side request size guard beyond bounded history trimming.
- The status could distinguish `loading`, `unreachable`, and `empty response` more explicitly.
- There is no Bonsai benchmark yet. `benchmark_ollama_model.py` targets Ollama's API only.

## Guidance For Future Work

- Treat the current implementation as the baseline rather than re-planning the feature from scratch.
- Prefer incremental hardening over architectural churn.
- Keep this folder's docs aligned with `start_or_restart_mhd.ps1` and `config.yaml`.
- After any runtime change, re-verify with `Invoke-RestMethod http://127.0.0.1:1080/v1/models` and `nvidia-smi`. `llama-server.exe` should hold VRAM.
