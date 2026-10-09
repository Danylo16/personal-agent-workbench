# Verification — 2026-10-09

## Performed

- Python 3.12. Actual final command from project root: `python -m pytest -q`.
- **34 passed in 2.82 seconds.** All tests are deterministic; HTTP tests use HTTPX MockTransport, not real model completions.
- Barrier test proves proposal concurrency and absence of peer output. Reviewer/Judge dependencies and original task transfer checked.
- Failure tests: invalid JSON, truncated completion, malformed provider response, missing credentials, 400/401/402/403/404, 429 and 503 retry behavior, network timeout, atomic request budget, cancellation, disabled essential stage.
- Provider payload test checks actual adapter URL, assigned model, output token limit, timeout and zero-price OpenRouter caps. No live completion is implied by these tests.
- Three Streamlit AppTest checks: mock run survives rerenders and human disposition without another execution; saved configuration affects the actual agent prompt/model/name; missing credentials produce an explicit failed run with zero requests.
- Actual local Streamlit server started in a subprocess. `GET /_stcore/health` returned HTTP **200**, body **ok**. This proves server startup, not live inference.
- Actual public OpenRouter `GET /api/v1/models` returned HTTP **200**. Application discovery returned **16 IDs including openrouter/free**, filtering the free variants for zero prompt/completion pricing. Snapshot: `docs/model_catalog_verified.json`. The list is time-dependent and not proof of free-model capacity or distinct underlying models.
- PDF has three A4 pages. Every page was rendered with Poppler and visually inspected. Embedded fonts corrected the first render; final pages are legible without clipping. SVG/PDF/Mermaid share the same graph definition. PNG pages are also provided.
- No API keys in the environment. No live model completion was attempted or represented as successful. API adapters and their behavior were validated with mocked HTTP responses only.

## Not verified / requires user action

- Authenticated real OpenRouter/Groq completion, account quota and model capacity.
- Installation on the user's Windows computer (commands supplied; tested host is Linux).
- True root cause of the Article Platform bug; actual repository not supplied.
- Historical tool name, dates, frequency, original role instructions and transcripts.
- Actual Loom recording, current account limit, acceptance of a silent recording, public share-link permissions and recruiter submission.
- Real OMS/WMS/carrier integrations; the e-commerce diagram is a process design only.

No productivity statistic or historical usage claim has been fabricated.
