# Internet Access Decisions

This document records the key design choices for enabling internet-backed retrieval in the Local AI chat while keeping Granite 3.3 local.

## Decision 1: Keep Model Inference Local Through Ollama

- Status: accepted
- Decision: Granite 3.3 remains the answering model and continues to run through the local Ollama runtime.
- Why: The goal is to augment local inference with internet-sourced context, not replace local inference with a hosted LLM.
- Alternatives considered:
  - Hosted LLM with built-in browsing: rejected because it violates the local-first direction.
  - Full cloud retrieval-plus-inference stack: rejected because it changes the feature into a different architecture.
- Consequences:
  - The system must supply external context to the local model rather than outsourcing the answer.
  - Local runtime performance and reliability remain central.
- Rollback path: None needed unless the product direction changes away from local-first behavior.

## Decision 2: Mediate Internet Access In The Backend

- Status: accepted
- Decision: Any internet retrieval for chat responses will be performed by backend code, not directly by the browser and not by an unconstrained model runtime.
- Why: Backend mediation allows validation, allowlisting, logging, rate control, error handling, and clearer testing.
- Alternatives considered:
  - Browser-side fetches to arbitrary endpoints: rejected because it reduces control and expands attack surface.
  - Letting the model issue unrestricted network actions: rejected because it is difficult to constrain and support safely.
- Consequences:
  - Retrieval logic belongs near `app.py` or in dedicated helper modules.
  - The UI can stay simple and only consume structured chat responses.
- Rollback path: If needed, extract retrieval into a dedicated internal service later without changing the UI contract first.

## Decision 3: Use Retrieval Only When Needed

- Status: accepted
- Decision: Internet access should be conditional, based on the user question or retrieval policy, rather than applied to every chat request.
- Why: Most prompts do not need internet access, and unnecessary retrieval adds latency, complexity, and external dependencies.
- Alternatives considered:
  - Always retrieve before every answer: rejected because it is wasteful and broadens failure modes.
  - Never retrieve automatically: rejected because it defeats the purpose of internet-enabled responses.
- Consequences:
  - The system needs a clear retrieval trigger or routing rule.
  - The chat path will need to distinguish local-only and retrieval-augmented requests.
- Rollback path: A manual user-controlled toggle could be added later if automatic triggering proves unreliable.

## Decision 4: Start Narrow Rather Than Building A General Browser Agent

- Status: accepted
- Decision: The first implementation should use a narrow, testable retrieval approach instead of unrestricted browsing.
- Why: The main risk in this workstream is uncontrolled scope. A narrow retrieval layer is easier to support and reason about.
- Alternatives considered:
  - General browsing agent: rejected because it introduces too many policy and safety questions at once.
  - Full tool-using autonomous agent loop: rejected because it is outside current scope.
- Consequences:
  - An allowlist, specific search providers, or a constrained fetch set is preferred.
  - Source formatting and evidence handling should be explicit.
- Rollback path: Broaden retrieval scope later only after the narrow path works reliably.

## Decision 5: Make Retrieval Usage Visible In The Response Contract

- Status: accepted
- Decision: Chat responses should make it possible to indicate whether external data was used.
- Why: Users should know whether the answer is based only on the local model or on fetched external information.
- Alternatives considered:
  - Hide retrieval use entirely: rejected because it makes troubleshooting and trust harder.
  - Expose raw retrieval internals directly in the UI: rejected for now because it may be too noisy.
- Consequences:
  - The backend response format may need to include metadata such as retrieval status or source usage.
  - The frontend may eventually surface that state in the chat card.
- Rollback path: If the UI does not expose retrieval metadata initially, preserve it in the backend contract for future use.

## Decision 6: Graceful Degradation Is Required

- Status: accepted
- Decision: If retrieval fails, chat should continue with a limited response or a clear limitation message instead of failing hard.
- Why: External network access is inherently less reliable than local inference, so failure handling is part of the core design.
- Alternatives considered:
  - Hard fail when retrieval is unavailable: rejected because it makes chat brittle.
  - Silently ignore retrieval failures: rejected because the user would not understand degraded answer quality.
- Consequences:
  - Retrieval errors need explicit handling and messaging.
  - The model may need a fallback prompt path when external context is unavailable.
- Rollback path: Tighten or relax the fallback behavior later based on UX feedback.