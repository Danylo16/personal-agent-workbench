### Execution rules

- **Independent inputs:** the first two agents do not see each other's answer.
- **Validated handoffs:** both proposals must pass validation before the critic runs; the review must pass before synthesis.
- **Visible failures:** failed or truncated answers stop downstream calls. Completed outputs remain in the trace.
- **Bounded requests:** each HTTP attempt, including retries, counts toward the shared budget. A successful run normally uses four calls.

### Components

| Component | Responsibility |
|---|---|
| Streamlit | Inputs, configuration, trace and result export |
| asyncio | Parallel proposals and ordered downstream stages |
| HTTPX / provider adapter | Model requests, timeouts and retries |
| Pydantic | Typed configuration and response validation |

### Human control

The models reason over supplied text. They do not browse, read repositories or execute code. Human review records a decision; I perform and verify any changes.

API keys remain on the server. The task and selected upstream responses are sent to the configured model provider.
