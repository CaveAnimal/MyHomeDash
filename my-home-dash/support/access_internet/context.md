# Internet Access Context

> Scope: controlled internet-backed retrieval for the Local AI chat in My Home Dash while keeping Granite 3.3 inference local through Ollama.

## Current Objective

The access_internet workstream exists to define how My Home Dash can let the Local AI chat use external internet-sourced information when a question requires current facts, changing online content, or information not likely to be present in the model alone.

## Current System State

The dashboard already has a working Local AI chat path, but it does not yet include any internet retrieval layer.

### What Is Already Implemented

- `app.py` exposes `POST /api/chat`.
- `app.py` sends a bounded conversation history to Ollama using the configured local model.
- `templates/dashboard.html` includes a Local AI chat card.
- `static/dashboard.js` manages local chat history and renders responses from the backend.
- `config.yaml` already contains local LLM configuration such as model name, timeout, temperature, and history limits.
- The Local AI feature is documented and supported operationally in `support/local_ai/`.

### What Is Not Yet Implemented

- There is no backend retrieval step between the browser and Ollama.
- There is no policy for deciding when a user question should trigger internet access.
- There is no web-search or targeted external-fetch helper dedicated to chat responses.
- There is no response contract that distinguishes local-model-only answers from retrieval-augmented answers.
- There is no dedicated readiness or failure status for internet-backed retrieval in the chat UX.

### What This Means

- The current chat experience is local-only in practice.
- The access_internet workstream is planning and design oriented right now.
- Future implementation should augment the existing chat path rather than replace it.

## Relevant Files

| File | Purpose |
|------|---------|
| `my-home-dash/app.py` | Current Flask chat proxy and error handling |
| `my-home-dash/config.yaml` | Existing local LLM configuration and dashboard source settings |
| `my-home-dash/static/dashboard.js` | Current browser chat flow and status handling |
| `my-home-dash/templates/dashboard.html` | Local AI chat UI container |
| `my-home-dash/modules/weather_mod.py` | Example of existing outbound HTTP access using `requests` |
| `my-home-dash/modules/news_mod.py` | Example of current internet-backed RSS retrieval |
| `my-home-dash/modules/github_mod.py` | Example of authenticated external API access |
| `my-home-dash/auth/` | Existing credential and token patterns for external providers |
| `my-home-dash/support/local_ai/` | Existing Local AI runtime and planning documents |
| `my-home-dash/support/access_internet/goal.md` | Goal statement for internet-enabled chat responses |

## Current Chat Architecture

### Existing Request Flow

1. The user enters a prompt into the dashboard chat card.
2. `static/dashboard.js` sends the conversation to `POST /api/chat`.
3. `app.py` validates the request and builds the Ollama message payload.
4. `app.py` calls the local Ollama `/api/chat` endpoint.
5. Ollama returns a non-streaming reply.
6. Flask returns the reply to the browser.

### Missing Retrieval Layer

To satisfy the access_internet goal, a new controlled step would need to exist between request validation and the final Ollama call. That step would decide whether retrieval is needed, fetch external data from approved sources, and then provide that data to Granite 3.3 as context.

## Technical Stack

| Area | Technology | Notes |
|------|------------|-------|
| Backend web app | Flask | Natural control point for retrieval policy |
| Frontend behavior | Vanilla JavaScript | Current chat UX can be extended with retrieval status later |
| Local model runtime | Ollama | Granite 3.3 remains local |
| HTTP access | `requests` | Already used elsewhere in the project |
| Existing internet-backed modules | Microsoft Graph, GitHub, weather APIs, RSS, holidays | Useful reference patterns for external calls |
| Operating environment | Windows 11 local workstation | Same environment as Local AI support |

## Hard Constraints

- Granite 3.3 must remain locally hosted through Ollama.
- Browser code must not be given an unrestricted direct path to arbitrary internet endpoints for chat.
- Internet access for chat responses must be mediated and controlled by backend code.
- Existing dashboard modules must continue to work without regression.
- External retrieval failures must degrade gracefully rather than breaking the dashboard or chat flow.
- Secrets, tokens, and provider configuration must remain outside committed source files where applicable.

## Candidate Retrieval Shapes

- Narrow web search or page fetch for current factual questions.
- Allowed-source retrieval from specific domains or APIs.
- Reuse of existing dashboard data providers when the requested information overlaps current modules.

These are candidate approaches only. No implementation has been chosen yet.

## Known Gaps And Open Questions

- How should the system decide whether a chat question needs internet access?
- Which sources are allowed for retrieval, and how narrow should the allowlist be?
- Should the first implementation use general web fetches, provider-specific APIs, or reuse existing module data?
- How should the response indicate that external data was used?
- Should retrieval results be summarized before being passed to Granite, or passed through directly in bounded form?

## Guidance For Future Work

- Treat the existing Local AI path as the baseline and layer retrieval onto it incrementally.
- Prefer backend-controlled retrieval tools or helper functions over free-form browsing behavior.
- Keep the first implementation narrow and testable.
- Reuse existing patterns for HTTP calls, credential management, and graceful error handling where possible.