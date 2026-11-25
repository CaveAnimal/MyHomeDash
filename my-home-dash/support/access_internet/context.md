# Internet Access Context

> Scope: controlled internet-backed retrieval for the Local AI chat in My Home Dash, while model inference stays local (Bonsai 2 27B via llama.cpp).

## Current Objective

The access_internet workstream lets the Local AI chat use external information when a question needs current facts, changing online content, or information the model alone is unlikely to have. The model always runs locally; retrieval only supplies context.

## Current System State

Backend-mediated retrieval is implemented and runs in front of the local model on every `/api/chat` request.

### What Is Already Implemented

- `modules/web_retrieval.py` provides `retrieve_chat_context(user_messages, llm_cfg)`. It looks at the latest user message and decides whether retrieval is needed.
- Retrieval triggers when a message:
  - starts with a manual prefix (`web:`, `search:`, `lookup:`),
  - contains a URL,
  - asks about the chat's own capabilities, or
  - matches the recency pattern (questions about current or recent things).
- Retrieval modes, checked in this order:
  1. `capability_info`: a canned description of what the chat can do.
  2. `ai_news_feeds`: AI headlines from the project's configured news feeds.
  3. `direct_url_fetch`: fetches the URL in the message and strips it to text.
  4. `duckduckgo_instant_answer`: DuckDuckGo's instant-answer API.
- `app.py`'s `_run_chat_with_optional_retrieval` answers `capability_info` and `ai_news_feeds` directly from the retrieved data without calling the model. Other modes add the retrieved context to the single system message and then call the model.
- The `/api/chat` response includes a `retrieval` object (`used`, `status`, `mode`, `sources`, `error`), and the chat UI shows the retrieval state.
- Settings are in `config.yaml` under `llm.internet_access` (`enabled`, `manual_prefixes`, `allow_duckduckgo`, `allow_direct_url_fetch`, `timeout_seconds`, `max_context_chars`, `max_related_topics`).

## Relevant Files

| File | Purpose |
|------|---------|
| `my-home-dash/modules/web_retrieval.py` | Retrieval trigger policy and retrieval modes |
| `my-home-dash/app.py` | Chat route, direct-reply short-circuit, system message assembly, model call |
| `my-home-dash/config.yaml` | `llm.internet_access` settings and the local model target |
| `my-home-dash/static/dashboard.js` | Browser chat flow and retrieval status display |
| `my-home-dash/templates/partials/chat.html` | Local AI chat UI container |
| `my-home-dash/modules/news_mod.py` | News feeds reused for AI headlines |
| `my-home-dash/support/local_ai/` | Local model runtime docs (Bonsai) |

## Current Chat Architecture

1. The user enters a prompt into the dashboard chat card.
2. `static/dashboard.js` sends the conversation to `POST /api/chat`.
3. `retrieve_chat_context` decides whether retrieval is needed and, if so, which mode to use.
4. For `capability_info` or `ai_news_feeds`, Flask builds the reply directly and skips the model.
5. Otherwise, `app.py` builds one system message (base prompt plus any retrieved context and sources) followed by bounded history. Bonsai's chat template rejects more than one system message.
6. `app.py` calls Bonsai's OpenAI-compatible `/v1/chat/completions` on `http://127.0.0.1:1080`.
7. Flask returns the reply, the model name, and the `retrieval` metadata to the browser.

## Technical Stack

| Area | Technology | Notes |
|------|------------|-------|
| Backend web app | Flask | Control point for retrieval policy |
| Frontend behavior | Vanilla JavaScript | Shows retrieval state in the chat card |
| Local model runtime | PrismML llama.cpp fork (`llama-server`) | Bonsai 2 27B, local only |
| HTTP access | `requests` | Same pattern as the other dashboard modules |
| External sources | DuckDuckGo instant answers, direct URL fetch, configured RSS news feeds | No API keys required |
| Operating environment | Windows 11 local workstation | Same environment as Local AI support |

## Hard Constraints

- Model inference must stay local (Bonsai via llama.cpp). Retrieval supplies context only.
- The browser must not get an unrestricted direct path to arbitrary internet endpoints for chat.
- Internet access for chat must be mediated and controlled by backend code.
- Existing dashboard modules must keep working without regression.
- Retrieval failures must degrade gracefully rather than break the chat.
- Secrets, tokens, and provider configuration must stay out of committed source files.

## Operational Facts Already Verified

- The first validation pass used Flask test-client scenarios for the local-only, retrieval-used, and retrieval-error paths.
- 2026-11-24, live against Bonsai:
  - `Can you access the internet?` returned the `capability_info` direct reply.
  - `web: Python programming language` hit DuckDuckGo, which returned no instant answer (`status: no-result`). Bonsai said no live result was retrieved and then answered from its own knowledge, which is the intended degraded behavior.

## Known Gaps And Open Questions

- DuckDuckGo's instant-answer API often returns nothing for general questions, so `no-result` is common. A fuller search source would make retrieval more useful.
- Bonsai's launcher starts a local SearXNG instance (port 1890) for its own web search. It could become a better search source for this chat, but the dashboard does not use it yet.
- Retrieval results are passed through in bounded form (`max_context_chars`) rather than summarized.

## Guidance For Future Work

- Treat the current retrieval layer as the baseline and extend it incrementally.
- Prefer backend-controlled retrieval helpers over free-form browsing behavior.
- Keep each new source narrow and testable.
- Keep retrieved context inside the single system message; do not add extra system-role messages.
