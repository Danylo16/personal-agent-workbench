import asyncio
import time
from uuid import uuid4
from collections.abc import Callable
from .agents import parse_output, InvalidOutput
from .prompts import messages_for
from .providers import Provider, ProviderError, RequestBudget
from .schemas import AgentConfig, AgentResult, ExecutionMetadata, FinalSynthesis, TaskInput, WorkflowResult, now

AGENT_ORDER = ("architect", "alternative", "reviewer", "judge")

def validate_configs(configs: list[AgentConfig]):
    if len(configs) != 4 or {a.id for a in configs} != set(AGENT_ORDER):
        raise ValueError("Exactly one configuration for each of the four agents is required.")
    if not all(a.enabled for a in configs):
        raise ValueError("All four agents are essential. Re-enable disabled agents to run this workflow.")

async def execute_agent(agent: AgentConfig, task: TaskInput, prior: list[AgentResult],
                        provider: Provider, budget: RequestBudget, notify: Callable | None = None) -> AgentResult:
    messages = messages_for(agent, task, prior)
    meta = ExecutionMetadata(source=provider.source, provider=provider.name, requested_model=agent.model)
    result = AgentResult(agent=agent, status="failed", input_messages=messages, metadata=meta)
    started = time.monotonic()
    if notify:
        notify("started", result)
    try:
        completion = await provider.complete(agent, messages, budget, meta)
        result.raw_output = completion.text
        meta.reported_model, meta.token_usage, meta.finish_reason = completion.reported_model, completion.usage, completion.finish_reason
        if completion.finish_reason == "length":
            raise InvalidOutput("Provider reports output truncation (finish_reason=length). Increase the output token limit; the raw response is retained and downstream stages are blocked.")
        result.output = parse_output(agent.id, completion.text)
        result.status = "success"
    except InvalidOutput as exc:
        result.status, result.error = "invalid", str(exc)
        result.output = None
    except ProviderError as exc:
        result.error = str(exc)
    except asyncio.CancelledError:
        result.status, result.error = "cancelled", "Execution cancelled; no downstream synthesis performed."
        raise
    except Exception:
        result.error = "Unexpected provider failure. No downstream output fabricated."
    finally:
        meta.finished_at = now()
        meta.latency_seconds = round(time.monotonic() - started, 3)
        if notify:
            notify("finished", result)
    return result

async def run_workflow(task: TaskInput, configs: list[AgentConfig], provider: Provider, limit=4,
                       notify: Callable | None = None) -> WorkflowResult:
    validate_configs(configs)
    agents = {a.id: a for a in configs}
    budget = RequestBudget(limit)
    result = WorkflowResult(run_id=str(uuid4()), task=task, source=provider.source, request_limit=limit)
    try:
        result.agents = list(await asyncio.gather(*[
            execute_agent(agents[k], task, [], provider, budget, notify) for k in AGENT_ORDER[:2]]))
        if any(r.status != "success" for r in result.agents):
            result.status = "failed"
            result.error = "Independent proposal stage failed. Any successful proposal remains inspectable; reviewer and judge were not invoked."
            return result
        for k in AGENT_ORDER[2:]:
            out = await execute_agent(agents[k], task, result.agents, provider, budget, notify)
            result.agents.append(out)
            if out.status != "success":
                result.error = f"{out.agent.name} failed or returned invalid output. Completed upstream outputs remain available."
                return result
        result.final = FinalSynthesis.model_validate(result.agents[-1].output.model_dump())
        result.status = "complete"
        return result
    except asyncio.CancelledError:
        result.status = "cancelled"
        result.error = "Cancelled. Requests already sent may still consume provider quota."
        return result
    finally:
        result.request_count = budget.used
        result.finished_at = now()
