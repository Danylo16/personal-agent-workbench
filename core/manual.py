from uuid import uuid4
from .agents import InvalidOutput, parse_output
from .orchestrator import AGENT_ORDER, validate_configs
from .prompts import messages_for
from .schemas import AgentResult, ExecutionMetadata, WorkflowResult, now

class ManualConference:
    def __init__(self, task, configs):
        validate_configs(configs)
        self.configs = {a.id: a for a in configs}
        self.result = WorkflowResult(run_id=str(uuid4()), task=task, source="manual", request_limit=4)

    def pending_id(self):
        return AGENT_ORDER[len(self.result.agents)] if len(self.result.agents) < 4 else None

    def prompt(self):
        k = self.pending_id()
        if k is None:
            return "Conference complete."
        messages = messages_for(self.configs[k], self.result.task, self.result.agents)
        return "\n\n".join(m["role"].upper() + "\n" + m["content"] for m in messages)

    def accept(self, raw: str, model_label: str):
        k = self.pending_id()
        if k is None:
            raise ValueError("Conference already complete")
        output = parse_output(k, raw)  # Invalid pastes never advance the stage.
        agent = self.configs[k]
        messages = messages_for(agent, self.result.task, self.result.agents)
        meta = ExecutionMetadata(source="manual", provider="User-pasted browser response",
            requested_model=agent.model, reported_model=model_label or "User did not specify", finished_at=now())
        self.result.agents.append(AgentResult(agent=agent, status="success", input_messages=messages,
            raw_output=raw, output=output, metadata=meta))
        if k == "judge":
            self.result.final = output
            self.result.status = "complete"
            self.result.finished_at = now()
