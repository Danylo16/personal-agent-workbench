from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parents[1] / 'app.py')

@pytest.fixture(autouse=True)
def isolate_credentials(monkeypatch):
    # Existing empty values prevent load_dotenv from restoring real local keys.
    monkeypatch.setenv('OPENROUTER_API_KEY', '')
    monkeypatch.setenv('GROQ_API_KEY', '')

def test_ui_run_and_rerender_do_not_repeat_requests():
    at = AppTest.from_file(APP, default_timeout=15).run()
    assert not at.exception
    at.selectbox(key='provider_mode').select('Offline mock').run()
    at.button(key='FormSubmitter:workflow_task-Run workflow').click().run()
    assert not at.exception
    result=at.session_state['result']
    assert result.status=='complete' and result.source=='mock'
    run_id=result.run_id
    # Routine rerender and human approval must retain the same execution.
    at.run()
    assert not at.exception
    assert at.session_state['result'].run_id==run_id
    at.radio[0].set_value('investigate').run()
    assert at.session_state['result'].run_id==run_id
    assert at.session_state['result'].approval=='investigate'

def test_ui_config_changes_actual_execution():
    at=AppTest.from_file(APP,default_timeout=15).run()
    at.selectbox(key='provider_mode').select('Offline mock').run()
    at.text_input(key='name_architect').set_value('Changed Architect')
    at.text_area(key='prompt_architect').set_value('MY CUSTOM ROLE PROMPT')
    at.text_input(key='model_architect').set_value('changed-model-id')
    at.button(key='FormSubmitter:agent_config-Save configuration').click().run()
    at.button(key='FormSubmitter:workflow_task-Run workflow').click().run()
    assert not at.exception
    result=at.session_state['result']
    assert result.agents[0].agent.name=='Changed Architect'
    assert result.agents[0].metadata.requested_model=='changed-model-id'
    assert 'MY CUSTOM ROLE PROMPT' in result.agents[0].input_messages[0]['content']

def test_ui_missing_credentials_is_explicit(monkeypatch, tmp_path):
    import dotenv
    import httpx
    fake_env = tmp_path / 'test.env'
    fake_env.write_text('OPENROUTER_API_KEY=fake-key-that-must-not-be-used\n')
    original_load = dotenv.load_dotenv
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *_args, **_kwargs: original_load(fake_env))
    requests = []
    async def forbid_post(*args, **kwargs):
        requests.append(True)
        raise RuntimeError('Tests must not invoke external model APIs')
    monkeypatch.setattr(httpx.AsyncClient, 'post', forbid_post)
    at=AppTest.from_file(APP,default_timeout=15).run()
    at.button(key='FormSubmitter:workflow_task-Run workflow').click().run()
    assert not at.exception
    result=at.session_state['result']
    assert result.status=='failed' and result.request_count==0
    assert 'Missing OpenRouter API key' in result.agents[0].error
    assert requests == []
