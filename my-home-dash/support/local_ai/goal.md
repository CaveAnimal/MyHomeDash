# Local AI Chat Goal

## Primary Objective

Add and complete a local AI chat experience on the My Home Dash home page, so the user can hold a live conversation with Bonsai 2 27B. The model is hosted locally by PrismML's llama.cpp server and loaded onto the NVIDIA GPU.

## Why This Matters

- The dashboard becomes an interactive assistant instead of a read-only information wall.
- The chat stays private and local instead of depending on a cloud LLM.
- A GPU-resident model keeps latency low enough for practical day-to-day use from the home page.

## Success Criteria

- [ ] The home page has a clearly visible Local AI chat window with message history, input, send, clear, and status feedback.
- [ ] A user can submit a message from the web page and get a reply from Bonsai in the same conversation thread.
- [ ] The web app exposes a stable backend chat path that accepts conversation history, forwards it to the local runtime, and returns the reply to the browser.
- [ ] The configured model is Bonsai 2 27B (`bonsai2-27b` at `http://127.0.0.1:1080`) unless the local configuration deliberately overrides it.
- [ ] Bonsai is loaded onto the GPU before or during dashboard use, and verification confirms GPU-backed execution rather than CPU-only fallback.
- [ ] If Bonsai is unavailable, the dashboard shows a clear failure state instead of hanging or crashing.
- [ ] The local AI chat does not break or regress the existing dashboard modules.

## In Scope

- Home page UI work needed to host a Local AI chat panel in the dashboard layout.
- Frontend JavaScript to capture input, maintain the thread, call the backend endpoint, and render replies.
- Backend Flask work to accept chat requests and proxy them to the local runtime's OpenAI-compatible API.
- Configuration for the runtime base URL, model alias, timeout, and prompt behavior.
- Startup automation (`start_or_restart_mhd.ps1`) that starts Bonsai when it is not already running.
- Health and error handling that tells a working model apart from an unavailable or CPU-fallback state.

## Explicitly Out Of Scope

- ❌ Adding cloud-hosted LLM providers for this feature.
- ❌ Building autonomous agent loops in this workstream (tool calling lives in `support/ai_operator`).
- ❌ Turning the local chat into a general RAG system with embeddings or vector databases.
- ❌ Reworking unrelated dashboard modules, auth flows, or scheduler behavior except where needed to avoid regression.
- ❌ Supporting multiple simultaneous users or a production-grade internet-facing chat service.
- ❌ Granite 3.3, which was retired on 2026-11-24 (see `decisions.md` Decision 9).

## Non-Negotiable Constraints

- Chat targets Bonsai 2 27B. Only if Bonsai's server is down does the app use a model that is already loaded in Ollama or LM Studio (see `decisions.md` Decisions 8 and 9). It never loads one itself.
- The chat path must stay local-first and must not need external SaaS inference to work.
- The implementation must run on Windows in the current My Home Dash environment.
- The dashboard must fail gracefully when the runtime is down, still loading, or unreachable.
- The integration must preserve existing dashboard behavior and page stability.

## Functional Intent

- The user opens the home page and sees a Local AI chat card.
- The user enters a prompt and submits it without leaving the page.
- The browser sends the current conversation to the Flask backend.
- Flask forwards the request to Bonsai's `/v1/chat/completions` endpoint.
- Bonsai returns the reply.
- The dashboard appends the reply to the thread and shows the current model and status.
- If the model is not reachable, the dashboard shows an actionable error message.

## Technical Outcome Required

- Bonsai's GGUF model and the `llama-server` binary must be installed under `E:\AI\models\Bonsai\Bonsai-demo`.
- Bonsai must be loadable onto the GPU at boot or by `start_or_restart_mhd.ps1`.
- GPU use must be verifiable with `/v1/models` (which answers only after the model loads) and `nvidia-smi`.
- The web app and the runtime must be wired together through a backend endpoint rather than direct browser-to-runtime calls.
- Conversation history must be sent in a bounded way so the UI stays responsive and requests stay practical.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Bonsai is not running when the dashboard loads | High | The start script and boot autostart launch it; the UI shows a clear error |
| Model falls back to CPU instead of GPU | High | Boot autostart waits for the NVIDIA driver; verify with `nvidia-smi` |
| Another runtime holds VRAM and Bonsai cannot fit | Medium | Unload Ollama/LM Studio models before starting Bonsai |
| Long prompts or too much history slow the dashboard | Medium | Cap retained message history and keep prompts concise |
| The chat feature destabilizes the dashboard UI | Medium | Isolate the chat panel and preserve existing module rendering |

## Definition Of Done

This goal is complete when the dashboard home page has a working Local AI chat panel, the backend can hold a conversation with Bonsai 2 27B through its local llama.cpp server, the model is verified to run from GPU memory on this machine, and failures are visible and manageable from the UI.
