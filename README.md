# Personal Agent Workbench

Python 3.12+ / Streamlit / asyncio / HTTPX / Pydantic v2.
A local four-agent engineering assistant that develops a personal GPT–Claude council approach into an explicit, inspectable Python workflow.

## Windows PowerShell — install and run

Extract this ZIP, open PowerShell in `personal-agent-workbench`, then:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Using the venv executable directly avoids PowerShell activation policy problems. If Python 3.12 is not installed, install Python 3.12+ and use the corresponding `py -3.13` / `py -3.14` command. No Node, Docker or database needed. Stop the local server with Ctrl+C.

## API setup (€0 target)

1. Create a free [OpenRouter](https://openrouter.ai/) account and API key in its dashboard. No key is bundled; paste it ONLY in local `.env` as `OPENROUTER_API_KEY=...`.
2. Use `OpenRouter` mode. The default is `nvidia/nemotron-3-super-120b-a12b:free`, used in a completed four-stage run on 2026-10-09. Select an endpoint supporting structured outputs. Availability can change; roles may share one underlying model.
3. Press **Refresh current models** to fetch currently listed zero-price `:free` IDs. Assign them in **Agent Configuration**, then **Save configuration**. A catalogue listing is not a successful completion or a guarantee of capacity. The adapter blocks other IDs and sets zero prompt/completion price caps.
4. For the first run use budget **4** (normally exactly four completion calls). If a transient error prevents completion, inspect the trace. A new deliberate run with budget **6** allows up to two additional requests, shared across all stages. Provider free quota is separate; the app cannot reset it.
5. Free inference is often slow or rate limited. Do one genuine rehearsal before recording. Refresh is a separate model-list GET, not part of the four completion POSTs.
6. Groq is optional: add `GROQ_API_KEY`, select `Groq`, refresh the account's model list and confirm your account uses the free tier. The initial Groq fallback is `openai/gpt-oss-20b`; replace it if your account lists a different usable model. This confirmation does not enforce provider billing settings. Do not use Groq if your account is on a paid plan. No automatic paid/provider fallback exists.

Public provider documentation was checked on 2026-10-09. OpenRouter documents `openrouter/free`. Groq's deprecation documentation says older `llama-3.1-8b-instant` and `llama-3.3-70b-versatile` free/developer defaults are deprecated; the app therefore does not rely on them. Availability and quota must still be verified in YOUR account.

Sources:
- https://openrouter.ai/docs/guides/routing/routers/free-router
- https://openrouter.ai/collections/free-models
- https://openrouter.ai/docs/api/reference/limits
- https://openrouter.ai/docs/guides/routing/provider-selection
- https://console.groq.com/docs/models
- https://console.groq.com/docs/deprecations

## Use the application

Select the Article Platform scenario or enter a custom problem. Add actual evidence if available; this project does not include the Article Platform repository. Press **Run workflow**. Architect and Alternative Analyst run concurrently with isolated inputs; Critic receives both validated proposals; Judge receives both plus critique. Inspect **Execution Trace**, then download JSON/Markdown. Human approval records a decision only, never applies a fix.

Change names, roles, prompts, models, token limits and timeouts in **Agent Configuration**. Saved changes affect the next run. All four agents are required. Disabling any one explicitly blocks this fixed workflow. Configuration exports can replace `config/agents.json` after local review.

Structured output is validated, with explicit rejection and retained raw output if malformed or truncated. No unbudgeted repair call is sent. Failure blocks downstream stages. This is multi-agent reasoning orchestration; it has no autonomous browsing, code reading or mutation tools.

## Manual fallback

Select **Manual**, enter the problem, click **Start manual conference**. Copy the Architect prompt into a fresh ChatGPT/Claude conversation, paste its actual JSON response and label the model used. Repeat Alternative in a SEPARATE new conversation with no Architect response. The next Reviewer prompt contains both; Judge contains both and review. Invalid pasted JSON does not advance. Manual timing is not inference latency; API request count is zero. This mode preserves data flow but not automatic parallel execution.

Do not use Offline mock as evidence of live AI. It is clearly labelled for tests/UI rehearsal. The failure toggle deliberately fails the reviewer; the judge must remain absent.

## Documentation and process example

- `docs/historical_workflow.md`: personal workflow, reconstructed role prompts and a resolved PostgreSQL case.
- `docs/loom_script_de.md`: 4:45 screen recording storyboard, captions, optional narration.
- `docs/captions_de.srt`: editable subtitle timing; replace historical placeholders before use.
- `docs/submission_email_de.txt`: draft only, no email sent.
- `docs/submission_checklist.md`: final manual checklist.
- `flowchart/address_change.mmd`: editable German Mermaid source, split into three linked process sections.
- `flowchart/address_change.svg`: vector overview of all three sections.
- `flowchart/address_change.pdf`: three A4 pages with readable steps and exception branches.
- `flowchart/address_change_1.png` etc.: page images.
- `flowchart/explanation_de.md`: assumptions, operational risk and synchronization rules.
- `docs/verification.md`: actual test results and unverified items.

## Security and limitations

The local server loads `.env`; no browser key input, no stored headers, no secrets in exports. Exports redact configured secrets/common key patterns, not arbitrary personal data. Inspect before sharing. Tasks and selected upstream results are sent to external providers; do not submit private code or customer data without authorization. Downloaded exports and browser session data are local to you; app does not store persistent run history. Optional supporting notes are session-only until exported.

Agreement between agents is not correctness. The demo symptom is user-reported, not repository-verified. API provider capacity, Windows installation and silent Loom acceptance must be checked by the user. No voice/video recording or recruiter submission is performed by this package.

## Diagram regeneration (optional)

The delivered Mermaid/SVG/PDF are ready to use. To change the synchronized graph and regenerate, edit `PAGES` in `tools/render_flowchart.py`, install `requirements-authoring.txt`, then run that Python script. Standalone Mermaid can also be edited/rendered in a Mermaid-compatible editor; this will not automatically update the custom SVG/PDF layout.

On Windows the optional authoring script can use installed Arial fonts:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-authoring.txt
$env:DIAGRAM_FONT_REGULAR = 'C:\Windows\Fonts\arial.ttf'
$env:DIAGRAM_FONT_BOLD = 'C:\Windows\Fonts\arialbd.ttf'
.\.venv\Scripts\python.exe tools\render_flowchart.py
```

These optional rendering dependencies are not required by the Streamlit app.

## Repository setup

From the project directory, with Git and GitHub CLI installed:

```powershell
git init -b main
git add .
git commit -m "Initial Personal Agent Workbench"
gh auth login
gh repo create personal-agent-workbench --private --source=. --remote=origin --push
```

The initial visibility is private. The ignore rules exclude credentials, local environments, exports and submission drafts. Review tracked files before changing visibility.

Detailed implementation notes: `docs/architecture_details.md`.
