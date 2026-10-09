import json
from pathlib import Path
import httpx
import pytest
from core.providers import APIProvider, RequestBudget, discover_models, ProviderError
from core.schemas import AgentConfig, ExecutionMetadata

def config():
    return AgentConfig.model_validate(json.loads((Path(__file__).parents[1]/'config/agents.json').read_text())[0])

async def test_retry_recovers_without_exceeding_budget(monkeypatch):
    calls=[]
    waits=[]
    async def sleep(delay): waits.append(delay)
    monkeypatch.setattr('core.providers.asyncio.sleep',sleep)
    def handler(req):
        calls.append(req)
        return httpx.Response(503 if len(calls)==1 else 200,json={'model':'reported','choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]})
    meta=ExecutionMetadata(source='api',provider='OpenRouter',requested_model='openrouter/free')
    budget=RequestBudget(2)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out=await APIProvider('OpenRouter','key',client).complete(config(),[],budget,meta)
    assert out.reported_model=='reported' and out.usage is None
    assert budget.used==len(calls)==2 and waits==[1]
    assert [a.status for a in meta.attempts]==['failed','success']
    assert meta.attempts[0].backoff_seconds==1

async def test_groq_adapter_uses_assigned_model_and_limits():
    c=config().model_copy(update={'model':'openai/gpt-oss-20b','max_tokens':250,'timeout':17})
    def handler(req):
        assert str(req.url)=='https://api.groq.com/openai/v1/chat/completions'
        payload=json.loads(req.content)
        assert payload['model']==c.model and payload['max_tokens']==250
        assert 'provider' not in payload
        assert req.extensions['timeout']['read']==17
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    budget=RequestBudget()
    meta=ExecutionMetadata(source='api',provider='Groq',requested_model=c.model)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out=await APIProvider('Groq','key',client,free_tier_confirmed=True).complete(c,[],budget,meta)
    assert out.reported_model is None and budget.used==1

async def test_model_discovery_filters_free_zero_price(monkeypatch):
    fixture={'data':[{'id':'paid/model','pricing':{'prompt':'0.01','completion':'0.01'}},
                     {'id':'fake:free','pricing':{'prompt':'0.01','completion':'0'}},
                     {'id':'real:free','pricing':{'prompt':'0','completion':'0'}}]}
    real_client=httpx.AsyncClient
    monkeypatch.setattr('core.providers.httpx.AsyncClient',lambda:real_client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=fixture))))
    assert await discover_models('OpenRouter')==['openrouter/free','real:free']

async def test_missing_usage_and_reported_model_remain_unknown():
    def handler(req):return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out=await APIProvider('OpenRouter','key',client).complete(config(),[],RequestBudget(),ExecutionMetadata(source='api',provider='OpenRouter',requested_model='openrouter/free'))
    assert out.usage is None and out.reported_model is None

@pytest.mark.parametrize('agent_id', ['architect', 'alternative', 'reviewer', 'judge'])
async def test_openrouter_requests_native_stage_schema(agent_id):
    from core.prompts import SCHEMAS
    c=config().model_copy(update={'id':agent_id})
    def handler(req):
        payload=json.loads(req.content)
        fmt=payload['response_format']
        assert fmt['type']=='json_schema'
        assert fmt['json_schema']['strict'] is True
        assert fmt['json_schema']['name']==agent_id+'_output'
        assert fmt['json_schema']['schema']==SCHEMAS[agent_id].model_json_schema()
        assert payload['provider']['require_parameters'] is True
        assert payload['provider']['max_price']=={'prompt':0,'completion':0}
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await APIProvider('OpenRouter','key',client).complete(c,[],RequestBudget(),ExecutionMetadata(source='api',provider='OpenRouter',requested_model=c.model))
