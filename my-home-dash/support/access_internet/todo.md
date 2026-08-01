# Internet Access TODO

## Overall Status

- [x] Goal document exists.
- [x] Context document exists.
- [x] Decisions document exists.
- [x] TODO tracker exists.
- [x] Internet-backed retrieval for chat responses is implemented.
- [x] This workstream has moved from planning into execution and validation.

## Completed

- [x] Define the goal for internet-enabled Granite 3.3 responses.
- [x] Document the current system context and current gap.
- [x] Record the core architectural decisions for backend-mediated retrieval.
- [x] Create a task tracker for the access_internet workstream.

## Active Work Queue

### 1. Design The Retrieval Trigger Policy

- Why it matters: The system needs a clear rule for when a question should trigger internet access versus staying local-only.
- [x] Complete retrieval trigger policy design.
- [x] Define trigger conditions for retrieval.
- [x] Identify examples of prompts that should remain local-only.
- [x] Identify examples of prompts that should request external information.

### 2. Choose The First Retrieval Mechanism

- Why it matters: The initial implementation should stay narrow and supportable.
- [x] Choose the first retrieval mechanism.
- [x] Pick the first retrieval shape: targeted web fetch, selected search source, or reuse of existing project data providers.
- [x] Document allowed sources and any credentials required.
- [x] Keep the design testable and bounded.

### 3. Define The Backend Contract For Retrieval-Augmented Chat

- Why it matters: The current `/api/chat` contract only returns model content and model name.
- [x] Define the backend contract for retrieval-augmented chat.
- [x] Define how retrieval status is represented in the response.
- [x] Define how failures are reported to the UI.
- [x] Preserve backward-compatible behavior where practical.

### 4. Implement The Retrieval Layer In Backend Code

- Why it matters: The goal cannot be met until the Flask chat path can fetch and inject external context.
- [x] Implement the retrieval layer in backend code.
- [x] Add backend retrieval helpers or modules.
- [x] Route qualifying chat requests through retrieval before calling Ollama.
- [x] Keep model inference local through Ollama.
- [x] Fail gracefully when retrieval is unavailable.

### 5. Update The Chat UI To Surface Retrieval State

- Why it matters: Users should be able to tell when an answer used external data or when retrieval failed.
- [x] Update the chat UI to surface retrieval state.
- [x] Surface retrieval status in the chat UI.
- [x] Keep the interface simple and non-disruptive.
- [x] Avoid exposing noisy internal details unless they are useful.

### 6. Test Offline And Failure Scenarios

- Why it matters: Retrieval failures are expected and must be part of the design.
- [x] Test offline and failure scenarios.
- [x] Verify behavior when the machine is offline.
- [x] Verify behavior when the retrieval source is blocked or times out.
- [x] Verify that local-only chat still works when internet retrieval is unavailable.

## Update Rule

- [x] Use checkboxes for task tracking in this file.
- [x] Update each parent task checkbox when all of its subtasks are complete.
- [x] Update each subtask checkbox immediately when that subtask is completed.

## Working Notes

- Treat this as an augmentation of the existing Local AI path, not a separate AI subsystem.
- Keep the first retrieval implementation narrow.
- Prefer explicit source control and predictable backend behavior over autonomous browsing logic.
- Reuse existing project patterns for `requests`, config handling, and error responses where possible.
- Validation note: the first verification pass used Flask test-client scenarios for local-only, retrieval-used, and retrieval-error paths without requiring live Ollama or live internet access.
- [x] Fix chat claims about lacking internet access when backend retrieval is available.
- [x] Fix AI headline queries to use the project news feeds instead of falling back to generic no-internet answers.
- [x] Short-circuit capability and AI-headline answers in the backend when structured retrieval data is already available.