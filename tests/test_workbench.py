import asyncio
import json
from pathlib import Path
import httpx
import pytest
from core.schemas import AgentConfig, TaskInput, ExecutionMetadata
from core.providers import APIProvider, MockProvider, RequestBudget, ProviderError, Completion
from core.orchestrator import run_workflow
from core.agents import parse_output, InvalidOutput
from core.prompts import messages_for
from core.manual import ManualConference
from core.exports import export_json, export_markdown
from core.session import run_once

@pytest.fixture
def configs():
    return [AgentConfig.model_validate(c) for c in json.loads((Path(__file__).parents[1] / 'config/agents.json').read_text())]

@pytest.fixture
def task():
    return TaskInput(problem='Frontend 404; backend 200', context='original shared context', constraints='Do not invent evidence')

async def test_concurrency_and_context_boundaries(configs, task):
    class BarrierProvider(MockProvider):
        def __init__(self):
            super().__init__()
            self.started = set()
            self.completed = set()
            self.inputs = {}
            self.barrier = asyncio.Event()
        async def complete(self, agent, messages, budget, metadata):
            self.inputs[agent.id] = json.loads(messages[1]['content'])
            if agent.id in ('architect', 'alternative'):
                self.started.add(agent.id)
                if len(self.started) == 2:
                    self.barrier.set()
                await asyncio.wait_for(self.barrier.wait(), 1)  # Sequential implementation fails.
                assert 'upstream_outputs' not in self.inputs[agent.id]
                assert self.inputs[agent.id]['original_task'] == task.model_dump()
            elif agent.id == 'reviewer':
                assert self.completed == {'architect', 'alternative'}
                assert set(self.inputs[agent.id]['upstream_outputs']) == {'architect', 'alternative'}
            else:
                assert set(self.inputs[agent.id]['upstream_outputs']) == {'architect', 'alternative', 'reviewer'}
                assert 'reviewer' in self.completed
            out = await super().complete(agent, messages, budget, metadata)
            self.completed.add(agent.id)
            return out
    provider = BarrierProvider()
    result = await run_workflow(task, configs, provider)
    assert result.status == 'complete'
    assert result.request_count == 0
    assert result.source == 'mock'
    assert result.final.abstain
    assert all(r.metadata.reported_model == 'deterministic-fixture' for r in result.agents)
    assert all(r.metadata.token_usage is None for r in result.agents)
    # Even accidental upstream injection is stripped from the first stage.
    assert 'upstream_outputs' not in json.loads(messages_for(configs[0], task, result.agents)[1]['content'])

async def test_failure_blocks_downstream(configs, task):
    result = await run_workflow(task, configs, MockProvider('alternative'))
    assert result.status == 'failed'
    assert [r.agent.id for r in result.agents] == ['architect', 'alternative']
    assert result.agents[0].status == 'success'
    assert result.final is None

async def test_invalid_review_does_not_reach_judge(configs, task):
    class Broken(MockProvider):
        async def complete(self, agent, messages, budget, metadata):
            if agent.id == 'reviewer':
                return Completion('This is NOT JSON')
            return await super().complete(agent, messages, budget, metadata)
    result = await run_workflow(task, configs, Broken())
    assert result.status == 'incomplete'
    assert result.agents[-1].status == 'invalid'
    assert result.agents[-1].raw_output == 'This is NOT JSON'
    assert len(result.agents) == 3

@pytest.mark.parametrize('bad', ['hello', '{}', '{"recommendation": "x"}', 'null'])
def test_invalid_output(bad):
    with pytest.raises(InvalidOutput):
        parse_output('judge', bad)

async def test_tolerant_json(configs, task):
    result = await run_workflow(task, configs, MockProvider())
    assert parse_output('architect', '```json\n' + result.agents[0].raw_output + '\n```').recommendation.startswith('MOCK')

async def test_rate_limit_budget(configs, monkeypatch):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(429, headers={'Retry-After': '0'}, json={'error': 'rate limited'})
    async def no_sleep(delay): pass
    monkeypatch.setattr('core.providers.asyncio.sleep', no_sleep)
    budget = RequestBudget(2)
    meta = ExecutionMetadata(source='api', provider='OpenRouter', requested_model=configs[0].model)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = APIProvider('OpenRouter', 'secret', client, retries=2)
        with pytest.raises(ProviderError, match='budget'):
            await provider.complete(configs[0], [], budget, meta)
    assert budget.used == len(calls) == len(meta.attempts) == 2
    assert all(a.http_status == 429 and a.status == 'failed' for a in meta.attempts)

async def test_budget_is_atomic():
    budget = RequestBudget(1)
    results = await asyncio.gather(budget.consume(), budget.consume(), return_exceptions=True)
    assert budget.used == 1
    assert sum(isinstance(r, ProviderError) for r in results) == 1

@pytest.mark.parametrize('status', [401,403,400,404,402])
async def test_credentials_and_nonretryable_http(configs, status):
    calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={'error': {'message': 'Never echo SECRET'}})
    meta = ExecutionMetadata(source='api', provider='OpenRouter', requested_model=configs[0].model)
    budget=RequestBudget(4)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as err:
            await APIProvider('OpenRouter','SECRET',client).complete(configs[0],[],budget,meta)
    assert len(calls)==budget.used==1
    assert 'SECRET' not in str(err.value)
    assert meta.attempts[0].http_status==status
    assert meta.attempts[0].finished_at is not None

async def test_real_http_adapter_metadata(configs, task):
    fixture = await run_workflow(task, configs, MockProvider())
    index = 0
    def handler(req):
        nonlocal index
        payload = json.loads(req.content)
        assert payload['provider']['max_price']=={'prompt':0,'completion':0}
        text=fixture.agents[index].raw_output
        index+=1
        return httpx.Response(200,json={'model':'actual-upstream-model','choices':[{'message':{'content':text},'finish_reason':'stop'}], 'usage':{'prompt_tokens':123,'completion_tokens':42}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result=await run_workflow(task,configs,APIProvider('OpenRouter','private-key',client))
    assert result.request_count==index==4
    assert result.status=='complete'
    assert all(r.metadata.requested_model=='openrouter/free' and r.metadata.reported_model=='actual-upstream-model' for r in result.agents)
    assert result.agents[0].metadata.token_usage=={'prompt_tokens':123,'completion_tokens':42}
    assert 'private-key' not in export_json(result)

async def test_timeout_and_network_budget(configs):
    def handler(req): raise httpx.ReadTimeout('SECRET URL',request=req)
    meta=ExecutionMetadata(source='api',provider='OpenRouter',requested_model=configs[0].model)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError,match='budget'):
            await APIProvider('OpenRouter','secret',client).complete(configs[0],[],RequestBudget(1),meta)
    assert meta.attempts[0].error=='Provider network error or timeout. No response confirmed.'

@pytest.mark.parametrize('payload',[{}, {'choices': []}, {'choices':[{'message':{'content':None}}]}])
async def test_malformed_http(configs,payload):
    meta=ExecutionMetadata(source='api',provider='OpenRouter',requested_model=configs[0].model)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=payload))) as client:
        with pytest.raises(ProviderError,match='Malformed'):
            await APIProvider('OpenRouter','secret',client).complete(configs[0],[],RequestBudget(4),meta)

async def test_paid_model_and_unconfirmed_groq_blocked(configs):
    def handler(req): pytest.fail('No request should be sent')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        c=configs[0].model_copy(update={'model':'paid/model'})
        for provider in [APIProvider('OpenRouter','secret',client), APIProvider('Groq','secret',client)]:
            with pytest.raises(ProviderError):
                await provider.complete(c,[],RequestBudget(),ExecutionMetadata(source='api',provider=provider.name,requested_model=c.model))

async def test_exports_redact_secrets(configs,task):
    secret='arbitrary-private-key'
    task.context+=' '+secret+' sk-or-v1-abcdefghijklmnop gsk_abcdefghijklmnop'
    result=await run_workflow(task,configs,MockProvider())
    for exported in [export_json(result,(secret,)),export_markdown(result,(secret,))]:
        assert secret not in exported and 'sk-or-v1-' not in exported and 'gsk_' not in exported
        assert 'MOCK' in exported
    json.loads(export_json(result,(secret,)))

def test_session_guard():
    state={};calls=[]
    def operation(): calls.append(1); return 'result'
    assert run_once(state,'click-1',operation)=='result'
    run_once(state,'click-1',operation)
    assert len(calls)==1
    run_once(state,'click-2',operation)
    assert len(calls)==2

async def test_manual_pipeline_is_labelled_and_validated(configs,task):
    conference=ManualConference(task,configs)
    fixture=await run_workflow(task,configs,MockProvider())
    with pytest.raises(InvalidOutput): conference.accept('bad','browser')
    assert conference.pending_id()=='architect'
    for r in fixture.agents:
        prompt=conference.prompt()
        if r.agent.id in ('architect','alternative'): assert 'upstream_outputs' not in prompt
        conference.accept(r.raw_output,'User reported browser model')
    assert conference.result.status=='complete'
    assert conference.result.source=='manual'
    assert conference.result.request_count==0
    assert all(r.metadata.source=='manual' for r in conference.result.agents)

async def test_disabled_stage(configs,task):
    configs[0].enabled=False
    with pytest.raises(ValueError,match='essential'): await run_workflow(task,configs,MockProvider())

async def test_truncated_valid_json_is_not_success(configs,task):
    class Truncated(MockProvider):
        async def complete(self,*args):
            out=await super().complete(*args)
            out.finish_reason='length'
            return out
    result=await run_workflow(task,configs,Truncated())
    assert result.status=='failed'
    assert result.agents[0].status=='invalid'
    assert result.agents[0].output is None

async def test_cancellation(configs,task):
    class Slow(MockProvider):
        async def complete(self,*args): await asyncio.sleep(100)
    running=asyncio.create_task(run_workflow(task,configs,Slow()))
    await asyncio.sleep(.01)
    running.cancel()
    result=await running
    assert result.status=='cancelled' and result.final is None
