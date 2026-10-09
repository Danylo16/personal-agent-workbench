import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4
import httpx
import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError
from core.schemas import AgentConfig, TaskInput
from core.orchestrator import run_workflow
from core.providers import APIProvider, MockProvider, ProviderError, discover_models
from core.manual import ManualConference
from core.agents import InvalidOutput
from core.exports import export_json, export_markdown, redact
from core.session import run_once

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
SECRETS = tuple(os.environ.get(k, '') for k in ('OPENROUTER_API_KEY', 'GROQ_API_KEY'))
st.set_page_config(page_title='Personal Agent Workbench', page_icon='◈', layout='wide')
st.markdown('''<style>.block-container{max-width:1250px;padding-top:2rem} [data-testid="stMetric"]{background:#f0f4f8;padding:14px;border-radius:10px} h1{letter-spacing:-.04em}</style>''', unsafe_allow_html=True)
st.title('Personal Agent Workbench')
st.caption('Multi-Agent Reasoning, Adversarial Review & Decision Support')
if 'configs' not in st.session_state:
    st.session_state.configs = [AgentConfig.model_validate(x) for x in json.loads((ROOT / 'config/agents.json').read_text())]
if 'history_original' not in st.session_state:
    st.session_state.history_original = ''
    st.session_state.history_german = ''

with st.sidebar:
    st.subheader('Execution controls')
    mode = st.selectbox('Provider / mode', ['OpenRouter', 'Groq', 'Manual', 'Offline mock'], key='provider_mode')
    is_api = mode in ('OpenRouter', 'Groq')
    key = os.environ.get('OPENROUTER_API_KEY' if mode == 'OpenRouter' else 'GROQ_API_KEY', '') if is_api else ''
    if is_api:
        st.caption('Key loaded from server .env: ' + ('configured' if key else 'missing'))
        st.caption('Models are configured per agent. Groq fallback: openai/gpt-oss-20b.')
        if st.button('Refresh current models'):
            try:
                st.session_state['models_' + mode] = asyncio.run(discover_models(mode, key))
            except ProviderError as e:
                st.error(str(e))
        discovered = st.session_state.get('models_' + mode, [])
        if discovered:
            st.write('Available IDs (catalogue, not a successful completion):')
            st.code('\n'.join(discovered))
    groq_confirm = False
    if mode == 'Groq':
        groq_confirm = st.checkbox('I verified this Groq account uses the free tier', value=os.environ.get('GROQ_FREE_TIER_CONFIRMED', '').lower() == 'true')
        st.caption('No automatic provider switching. Groq free quota is account dependent.')
    budget = st.number_input('Maximum completion HTTP requests per run', min_value=4, max_value=20, value=4)
    retries = st.slider('Retries per invocation', 0, 2, 1)
    st.caption('Four successful calls normally. Retries use the SAME budget. Model discovery is separate.')
    fail_mock = st.checkbox('Simulate reviewer failure', disabled=mode != 'Offline mock')
    st.divider()
    st.write('Independent → critique → synthesis → human decision')
    st.caption('No repository access, browsing or code execution by these agents. No automatic fixes.')

run_tab, trace_tab, config_tab, history_tab, architecture_tab = st.tabs(['Run Workflow', 'Execution Trace', 'Agent Configuration', 'Original Workflow', 'Architecture'])

def show_result(result):
    st.subheader('Run result')
    cols = st.columns(4)
    for col, label, value in zip(cols, ['Status', 'Source', 'API requests', 'Human decision'], [result.status, result.source.upper(), f'{result.request_count}/{result.request_limit}', result.approval]):
        col.metric(label, value)
    if result.source != 'api':
        st.warning('MANUAL browser responses — not API execution.' if result.source == 'manual' else 'OFFLINE MOCK — deterministic fixtures, not live AI.')
    if result.error:
        st.error(result.error)
    for r in result.agents:
        with st.expander(f'{r.agent.name} · {r.status}', expanded=False):
            if r.output:
                st.json(r.output.model_dump())
            else:
                st.error(r.error or 'No valid output')
                st.code(redact(r.raw_output, SECRETS), language=None)
    if result.final:
        st.subheader('Final recommendation')
        st.write(result.final.recommendation)
        if result.final.abstain:
            st.warning('Abstention: ' + result.final.abstention_reason)
        st.json(result.final.model_dump())
        decision = st.radio('Human disposition (does not execute a fix)', ['pending', 'approved', 'investigate'], index=['pending', 'approved', 'investigate'].index(result.approval), key='approval_' + result.run_id, horizontal=True)
        result.approval = decision
    a, b = st.columns(2)
    a.download_button('Download result JSON', export_json(result, SECRETS), f'run-{result.run_id}.json', 'application/json')
    b.download_button('Download result Markdown', export_markdown(result, SECRETS), f'run-{result.run_id}.md', 'text/markdown')

with run_tab:
    st.subheader('Investigate an engineering problem')
    scenario = st.selectbox('Example task', ['Article Platform: API 200 / frontend 404', 'Custom task'])
    with st.form('workflow_task'):
        problem = st.text_area('Problem', value='After a frontend migration from Vite to Next.js, the backend /locations endpoint returned HTTP 200, while the corresponding frontend page displayed HTTP 404.' if scenario.startswith('Article') else '', height=110)
        context = st.text_area('Context / evidence', value='Stack: Next.js, Fastify, Prisma, PostgreSQL, TypeScript. This is a user-reported symptom. No repository source or exact response payload is attached.', height=100)
        constraints = st.text_area('Constraints', value='Do not predeclare a root cause. Rank hypotheses, propose discriminating tests and regression criteria. Preserve the map design. No destructive database changes.')
        submitted = st.form_submit_button('Start manual conference' if mode == 'Manual' else 'Run workflow', type='primary')
    if submitted:
        try:
            task = TaskInput(problem=problem.strip(), context=context, constraints=constraints)
            configs = [c.model_copy(deep=True) for c in st.session_state.configs]
            if mode == 'Groq':
                # OpenRouter defaults are not valid Groq IDs. Custom Groq assignments remain respected.
                for c in configs:
                    if c.model == 'openrouter/free' or c.model.endswith(':free'):
                        c.model = 'openai/gpt-oss-20b'
            if mode == 'Manual':
                st.session_state.manual = ManualConference(task, configs)
                st.session_state.result = st.session_state.manual.result
            else:
                panel = st.status('Running independent proposals…', expanded=True)
                events = []
                def notify(event, result):
                    events.append({'event': event, 'agent': result.agent.id, 'at': (result.metadata.finished_at or result.metadata.started_at).isoformat()})
                    panel.write(f'{event.upper()} · {result.agent.name} · {result.metadata.requested_model} · {result.status if event == "finished" else "running"}')
                async def execute():
                    if not is_api:
                        return await run_workflow(task, configs, MockProvider('reviewer' if fail_mock else None), int(budget), notify)
                    async with httpx.AsyncClient() as client:
                        return await run_workflow(task, configs, APIProvider(mode, key, client, retries, groq_confirm), int(budget), notify)
                result = run_once(st.session_state, str(uuid4()), lambda: asyncio.run(execute()))
                st.session_state.events = events
                panel.update(label='Workflow ' + result.status, state='complete' if result.status == 'complete' else 'error', expanded=False)
        except (ValueError, ValidationError) as e:
            st.error(str(e))
    if mode == 'Manual' and 'manual' in st.session_state:
        conference = st.session_state.manual
        pending = conference.pending_id()
        if pending:
            st.info('Manual stage: ' + pending + '. Use a NEW browser conversation for each independent proposal; do not transfer the other proposal.')
            st.caption('The manual pipeline is sequential for pasting; independence is preserved by isolated prompts. It is not concurrent API execution.')
            st.code(conference.prompt(), language=None)
            st.download_button('Download current prompt', conference.prompt(), f'{pending}-prompt.txt')
            with st.form('paste_' + pending + '_' + conference.result.run_id):
                label = st.text_input('Model used (your label; not provider verified)', value='Browser model — specify actual model')
                raw = st.text_area('Paste the actual JSON response', height=180)
                accept = st.form_submit_button('Validate and advance')
            if accept:
                try:
                    conference.accept(raw, label)
                    st.session_state.result = conference.result
                    st.rerun()
                except InvalidOutput as e:
                    st.error(str(e))
    if st.session_state.get('result'):
        show_result(st.session_state.result)

with trace_tab:
    st.subheader('Execution Trace')
    result = st.session_state.get('result')
    if not result:
        st.info('Run a workflow to inspect the trace.')
    else:
        st.caption('UTC timestamps. Requested model and provider-reported model are separate. Manual timing measures paste acceptance, not model latency.')
        st.dataframe([{'agent': r.agent.name, 'source': r.metadata.source, 'status': r.status,
            'requested_model': r.metadata.requested_model, 'reported_model': r.metadata.reported_model or 'Not reported',
            'started_at': r.metadata.started_at.isoformat(), 'finished_at': r.metadata.finished_at.isoformat() if r.metadata.finished_at else '',
            'latency_seconds': r.metadata.latency_seconds if r.metadata.source != 'manual' else None,
            'HTTP_requests': len(r.metadata.attempts), 'tokens': json.dumps(r.metadata.token_usage) if r.metadata.token_usage is not None else 'Not reported'} for r in result.agents], width='stretch')
        for r in result.agents:
            with st.expander(r.agent.name + ' — input, output and attempts'):
                st.write('Exact input messages')
                st.json(json.loads(redact(json.dumps(r.input_messages), SECRETS)))
                st.write('Raw output (invalid output remains visible)')
                st.code(redact(r.raw_output, SECRETS), language=None)
                st.json(r.metadata.model_dump(mode='json'))
                if r.error:
                    st.error(r.error)

with config_tab:
    st.subheader('Actual execution configuration')
    st.caption('Saved changes affect the next intentional run. All four stages are essential; disabling one blocks execution.')
    with st.form('agent_config'):
        edited = []
        for c in st.session_state.configs:
            with st.expander(c.name, expanded=c.id == 'architect'):
                enabled = st.checkbox('Enabled', c.enabled, key='enabled_' + c.id)
                name = st.text_input('Name', c.name, key='name_' + c.id)
                role = st.text_input('Role', c.role, key='role_' + c.id)
                prompt = st.text_area('System prompt', c.system_prompt, key='prompt_' + c.id, height=150)
                model = st.text_input('Model ID', c.model, key='model_' + c.id)
                tokens = st.number_input('Maximum output tokens', 200, 8000, c.max_tokens, key='tokens_' + c.id)
                timeout = st.number_input('Timeout in seconds', 1.0, 180.0, c.timeout, key='timeout_' + c.id)
                edited.append(dict(id=c.id,name=name,role=role,system_prompt=prompt,model=model,enabled=enabled,max_tokens=tokens,timeout=timeout))
        if st.form_submit_button('Save configuration'):
            try:
                st.session_state.configs = [AgentConfig.model_validate(x) for x in edited]
                st.success('Configuration saved for the next run.')
            except ValidationError as e:
                st.error(str(e))
    st.download_button('Export agent configuration', redact(json.dumps([c.model_dump() for c in st.session_state.configs], indent=2), SECRETS), 'agents.json', 'application/json')

with history_tab:
    st.subheader('My Personal AI Workflow')
    st.markdown((ROOT / 'docs/historical_workflow.md').read_text(encoding='utf-8'))
    with st.expander('Add supporting material'):
        st.text_area('Saved notes or original excerpts', key='history_original', height=150)
        st.text_area('Translation', key='history_german', height=120)
        st.caption('Optional supporting material. Download to keep these session notes.')
        st.download_button('Download workflow notes', redact('# Supporting material\n' + st.session_state.history_original + '\n\n# Translation\n' + st.session_state.history_german, SECRETS), 'workflow-notes.md')

with architecture_tab:
    st.subheader('Explicit data flow')
    st.markdown('**Task → Architect ∥ Alternative Analyst → Critical Reviewer → Judge → Human review**')
    st.table([{'stage': '1 · Parallel analysis', 'receives': 'Task + context + constraints + own role', 'produces': 'Two independent proposals'},
              {'stage': '2 · Critical review', 'receives': 'Task + both validated proposals', 'produces': 'Gaps, contradictions, distinguishing tests'},
              {'stage': '3 · Synthesis', 'receives': 'Task + proposals + validated review', 'produces': 'Recommendation, unknowns, next checks'},
              {'stage': '4 · Human review', 'receives': 'Final recommendation + execution trace', 'produces': 'Accept or investigate; implementation stays manual'}])
    st.markdown((ROOT / 'docs/architecture.md').read_text(encoding='utf-8'))
