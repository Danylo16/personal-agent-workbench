from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

AgentId = Literal["architect", "alternative", "reviewer", "judge"]
def now() -> datetime:
    return datetime.now(timezone.utc)

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class AgentConfig(StrictModel):
    id: AgentId
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=300)
    system_prompt: str = Field(min_length=1, max_length=20000)
    model: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    max_tokens: int = Field(default=1800, ge=200, le=8000)
    timeout: float = Field(default=90, ge=1, le=180)

class TaskInput(StrictModel):
    problem: str = Field(min_length=1, max_length=12000)
    context: str = Field(default="", max_length=24000)
    constraints: str = Field(default="", max_length=8000)

class Proposal(StrictModel):
    recommendation: str = Field(min_length=1)
    reasoning: list[str]
    assumptions: list[str]
    risks: list[str]
    verification_steps: list[str]

class ReviewOutput(StrictModel):
    comparison: str = Field(min_length=1)
    unsupported_assumptions: list[str]
    contradictions: list[str]
    failure_cases: list[str]
    distinguishing_tests: list[str]

class Hypothesis(StrictModel):
    hypothesis: str
    evidence: list[str]
    validation: str

class FinalSynthesis(StrictModel):
    recommendation: str = Field(min_length=1)
    reasoning: list[str]
    ranked_hypotheses: list[Hypothesis]
    verified_facts: list[str]
    assumptions: list[str]
    unknowns: list[str]
    risks: list[str]
    disagreements: list[str]
    verification_steps: list[str]
    human_review_required: bool
    human_decisions: list[str]
    abstain: bool
    abstention_reason: str

class Attempt(StrictModel):
    number: int
    started_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None
    status: str = "started"
    http_status: int | None = None
    error: str | None = None
    backoff_seconds: float = 0

class ExecutionMetadata(StrictModel):
    source: Literal["api", "manual", "mock"]
    provider: str
    requested_model: str
    reported_model: str | None = None
    started_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None
    latency_seconds: float = 0
    attempts: list[Attempt] = Field(default_factory=list)
    token_usage: dict[str, int] | None = None
    finish_reason: str | None = None

class AgentResult(StrictModel):
    agent: AgentConfig
    status: Literal["success", "invalid", "failed", "cancelled"]
    input_messages: list[dict[str, str]]
    raw_output: str = ""
    output: Proposal | ReviewOutput | FinalSynthesis | None = None
    error: str | None = None
    metadata: ExecutionMetadata

class WorkflowResult(StrictModel):
    run_id: str
    task: TaskInput
    source: Literal["api", "manual", "mock"]
    status: Literal["complete", "incomplete", "failed", "cancelled"] = "incomplete"
    started_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None
    agents: list[AgentResult] = Field(default_factory=list)
    request_count: int = 0
    request_limit: int = 4
    final: FinalSynthesis | None = None
    error: str | None = None
    approval: Literal["pending", "approved", "investigate"] = "pending"
