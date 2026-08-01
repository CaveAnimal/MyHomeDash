# Local AI Chat Goal

## Primary Objective

Add and complete a local AI chat experience on the My Home Dash home page so the user can hold a live conversation with a locally hosted Granite 3.3 model that is loaded into the NVIDIA GPU through Ollama.

## Why This Matters

- The dashboard becomes an interactive assistant instead of a read-only information wall.
- The chat experience stays private and local instead of depending on a cloud LLM.
- Granite 3.3 running on the GPU keeps latency low enough for practical day-to-day use from the home page.

## Success Criteria

- [ ] The home page contains a clearly visible Local AI chat window with message history, input, send, clear, and status feedback.
- [ ] A user can submit a message from the web page and receive a response from the local Granite 3.3 model in the same conversation thread.
- [ ] The web application exposes a stable backend chat path that accepts conversation history, forwards it to Ollama, and returns the assistant reply to the browser.
- [ ] The configured model is `granite3.3:8b` unless a deliberate local configuration override is supplied.
- [ ] Granite 3.3 is warmed and loaded into GPU memory before or during dashboard use, and runtime verification confirms GPU-backed execution rather than CPU-only fallback.
- [ ] If Ollama or the model is unavailable, the dashboard shows a clear failure state instead of hanging or crashing.
- [ ] The local AI chat does not break or regress the existing dashboard modules.

## In Scope

- Home page UI work required to host a Local AI chat panel in the dashboard layout.
- Frontend JavaScript required to capture user input, maintain the conversation thread, call the backend endpoint, and render replies.
- Backend Flask work required to accept chat requests and proxy them to the local Ollama chat API.
- Configuration required to point the dashboard at the correct local Ollama base URL, model name, timeout, and prompt behavior.
- Local runtime setup required to pull, warm, and keep `granite3.3:8b` available for dashboard conversations.
- Startup automation or documented startup behavior required so the model can be loaded into the GPU reliably on this Windows machine.
- Health and error handling needed to distinguish a working local model from an unavailable or CPU-fallback state.

## Explicitly Out Of Scope

- ❌ Adding cloud-hosted LLM providers for this feature.
- ❌ Building tool-calling, autonomous agent loops, or multi-step task orchestration inside the chat experience.
- ❌ Turning the local chat into a general RAG system with embeddings or vector databases.
- ❌ Reworking unrelated dashboard modules, auth flows, or scheduler behavior except where required to avoid regression.
- ❌ Supporting multiple simultaneous users or a production-grade internet-facing chat service.

## Non-Negotiable Constraints

- The model target is Granite 3.3 through the local Ollama runtime on this workstation.
- The preferred model is `granite3.3:8b` because it fits the RTX 3060 12 GiB VRAM envelope well enough for responsive local use.
- The chat path must remain local-first and must not require external SaaS inference to function.
- The implementation must run on Windows in the current My Home Dash environment.
- The dashboard must fail gracefully when the local model runtime is down, warming up, or unreachable.
- The integration must preserve existing dashboard behavior and page stability.

## Functional Intent

- The user opens the home page and sees a Local AI chat card on the dashboard.
- The user enters a prompt and submits it without leaving the page.
- The browser sends the current conversation to the Flask backend.
- Flask forwards the request to Ollama using the configured Granite 3.3 model.
- Ollama returns the assistant response.
- The dashboard appends the reply to the conversation thread and shows the current model and status.
- If the model is not reachable, the dashboard surfaces an actionable error message.

## Technical Outcome Required

- Granite 3.3 must be present locally in Ollama.
- Granite 3.3 must be loadable into GPU memory on startup or first use.
- GPU usage must be verifiable with `ollama ps` and, when needed, `nvidia-smi`.
- The web app and the local model runtime must be wired together through a backend endpoint rather than direct browser-to-Ollama calls.
- Conversation history must be sent in a bounded way so the UI remains responsive and requests stay practical.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Ollama is not running when the dashboard loads | High | Provide startup automation and clear UI error messaging |
| Model falls back to CPU instead of GPU | High | Verify with `ollama ps`, warm the model early, and document GPU checks |
| Long prompts or too much retained history slow the dashboard | Medium | Cap retained message history and keep prompts concise |
| The chat feature destabilizes the dashboard UI | Medium | Isolate the chat panel and preserve existing module rendering behavior |

## Definition Of Done

This goal is complete when the dashboard home page includes a working Local AI chat panel, the backend can carry on a conversation with `granite3.3:8b` through Ollama, the model is verified to run from GPU memory on this machine, and failure modes are visible and manageable from the UI.
