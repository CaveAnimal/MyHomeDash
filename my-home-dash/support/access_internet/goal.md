# Internet Access Goal

## Primary Objective

Enable the Local AI chat in My Home Dash to use internet-sourced information when Granite 3.3 needs current or external data to answer a user question, while keeping model inference local through Ollama.

## Why This Matters

- A local model without live external data is limited when users ask about recent events, changing websites, or current factual information.
- Internet-backed retrieval can make Granite 3.3 more useful without replacing the local model with a cloud-hosted LLM.
- Clear boundaries are required so internet access improves answers without turning the chat into an uncontrolled browsing agent.

## Success Criteria

- [ ] The Local AI chat can use internet-backed retrieval when a user question requires current or external information.
- [ ] Granite 3.3 continues to run locally through Ollama and does not depend on cloud-hosted inference.
- [ ] Internet access for AI responses is mediated by backend code rather than giving the browser or model an unrestricted direct network path.
- [ ] If internet retrieval fails, the chat returns a clear degraded response instead of hanging or crashing.
- [ ] The system can distinguish between local-model-only answers and answers augmented with fetched external information.

## In Scope

- Defining how Local AI chat requests can trigger controlled internet-backed retrieval.
- Documenting the intended backend-mediated access pattern for web lookups or selected external APIs.
- Clarifying how chat behavior should degrade when the machine is offline or when internet lookups fail.
- Defining the boundary between local model inference and internet-backed retrieval.
- Supporting future context, decisions, and TODO documents for the `support/access_internet` workstream.

## Explicitly Out Of Scope

- ❌ Replacing local execution with a cloud-hosted dashboard.
- ❌ Replacing Granite 3.3 with an external hosted LLM.
- ❌ Giving the browser a direct unrestricted path to arbitrary internet endpoints.
- ❌ Building a full network security or proxy management platform.
- ❌ Sending every chat request to the internet when no external lookup is needed.

## Non-Negotiable Constraints

- The dashboard continues to run locally on Windows.
- Granite 3.3 continues to run locally through Ollama.
- Internet access for AI responses must be mediated by backend code under project control.
- Internet access is used only when required by the user question or retrieval policy.
- Secrets, tokens, and API keys must stay out of committed source files.
- External-service failures must not crash the full dashboard process.
- Local AI remains a local-first feature, independent of cloud inference.

## Functional Intent

- When a user asks Granite 3.3 a question that needs current external information, the dashboard should be able to fetch that information and incorporate it into the response flow.
- When a question does not need outside information, the local model should answer without unnecessary network calls.
- When internet retrieval fails, the user should receive a clear response that the answer is limited by unavailable external access.
- When the machine is offline, the dashboard should still start locally and the chat should fall back to local-only behavior or an explicit limitation message.

## Technical Outcome Required

- A backend-controlled retrieval path exists or is planned for Local AI chat.
- The distinction is explicit between local model inference and internet-backed data retrieval.
- Allowed internet sources for AI responses are defined narrowly enough to be testable and supportable.
- Future implementation work in this folder can proceed from a clear statement that internet access augments Granite 3.3 responses rather than replacing local inference.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Internet outage or blocked access causes AI responses to fail unpredictably | High | Require explicit fallback behavior and clear user-visible error states |
| Internet-enabled chat grows into an uncontrolled browsing agent | High | Keep retrieval backend-mediated, scoped, and auditable |
| Local AI scope gets mixed with cloud AI assumptions | High | State explicitly that Granite inference remains local through Ollama |
| Firewall or proxy restrictions block external lookups | Medium | Document retrieval dependencies and expected troubleshooting checks |
| Missing API keys, source rules, or provider settings appear to be network failures | Medium | Document prerequisites separately and make retrieval errors clearer |

## Definition Of Done

This goal is complete when the `support/access_internet` workstream clearly defines how Granite 3.3 in My Home Dash can use controlled internet-backed retrieval during chat responses, what remains local-only, and how the system behaves when external access is unavailable.