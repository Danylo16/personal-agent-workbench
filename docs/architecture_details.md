Native asyncio makes the three-stage dependency graph explicit and testable. A barrier test proves both proposal calls start before either completes; a sequential implementation fails that test. The Provider protocol separates orchestration from HTTP and permits later replacement with a graph framework without changing schemas.

Each agent has its own role and prompt. Proposal inputs are identical except for the system instruction and never contain peer output. The critic receives both completed validated proposals. The judge receives those plus the validated critique. All four stages are essential in this version; disabling a stage is an explicit configuration error.

Pydantic validates JSON against per-stage schemas. Markdown fences and surrounding prose are tolerated, but missing fields are never invented. Invalid or truncated output retains its raw response, blocks downstream synthesis and requires an intentional rerun. There is no automatic JSON repair call, which would consume additional quota.

An asyncio lock protects the shared request budget; each completion HTTP attempt counts, including retries and network failures whose provider processing cannot be determined. 429, 5xx and network failures retry at most twice with bounded exponential backoff. 400/401/403/404 do not retry. Retry-After values above 15 seconds are capped; this may be too early for a long provider cooldown, so use an intentional later rerun. Four calls normally complete a run; a budget of four leaves no additional allowance for recovery. Model-list refreshes are separate read requests shown explicitly by the control.

Streamlit uses one asyncio.run entry point inside an explicit form submission. A per-click token guards duplicate execution; completed results survive ordinary rerenders in session_state. Async clients and locks are created per run, not cached across event loops. The callback writes stage events from the same Streamlit script thread. Session state is temporary, not a database. Browser refresh can discard it: download results.

Credentials stay in server environment variables. Provider bodies, URLs and headers are not included in error messages. Exports remove configured secrets and common key patterns, including if pasted into task inputs. That is not a general personal-data anonymizer; inspect exports before sharing. All supplied task text and selected upstream responses go to the chosen external provider. Use no private client data in the recording.

OpenRouter accepts only openrouter/free or :free model IDs and imposes provider.max_price prompt/completion = 0. Catalog discovery filters zero-priced free variants. Requested and reported model IDs remain distinct; a router may choose the same model for several agents. Logical agent independence does not guarantee diverse model reasoning. Groq is a user-selected fallback and requires confirmation of the free account plan; catalogue presence alone cannot certify cost or quota. There is no silent paid or cross-provider fallback.

Manual mode emits the same staged schema prompts. Paste Architect and Alternative responses from separate fresh conversations before proceeding. It is sequential user input, not concurrent API execution. Model labels are user-reported and timing is not inference latency. Mock mode is permanently labelled and sends no API requests.

Cancellation propagates within the async layer and returns a cancelled result. There is no dedicated browser cancellation control in this minimal UI; Streamlit Stop is best effort and already transmitted requests may finish remotely. Essential failure blocks later calls. Completed upstream outputs remain inspectable; no final diagnosis is fabricated.

This is a fixed multi-agent reasoning workflow, not an autonomous tool-using agent. No repository reader, web browsing, shell execution or mutation tools are implemented. Hypotheses and suggested tests need human execution. Multiple agents can share the same error; critique and consensus do not prove correctness. Human approval records a disposition only and does not execute a fix.

## JSON output hardening

OpenRouter now receives a per-stage JSON Schema in response_format with strict=true and require_parameters=true. Select a free model whose endpoint advertises structured_outputs, such as the currently catalogued nvidia/nemotron-3-super-120b-a12b:free. Endpoints can still reject requests or return invalid/truncated output; Pydantic validation remains mandatory. See docs/json_output_fix.md.
