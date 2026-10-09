import json
import re
from .schemas import WorkflowResult

SENSITIVE_KEY = re.compile(r"(?i)(?:sk-(?:or-v1-)?[a-zA-Z0-9_-]{10,}|gsk_[a-zA-Z0-9_-]{10,}|bearer\s+[^\s\"]+)")

def redact(text: str, secrets=()) -> str:
    for value in secrets:
        if value:
            text = text.replace(value, "[REDACTED]")
    return SENSITIVE_KEY.sub("[REDACTED]", text)

def export_json(result: WorkflowResult, secrets=()) -> str:
    return redact(result.model_dump_json(indent=2), secrets)

def export_markdown(result: WorkflowResult, secrets=()) -> str:
    parts = ["# Personal Agent Workbench", f"Source: **{result.source.upper()}** | Status: {result.status}",
             f"Run: {result.run_id} | API requests: {result.request_count}/{result.request_limit}",
             "## Task", result.task.problem, result.task.context, result.task.constraints]
    if result.error:
        parts += ["## Failure", result.error]
    for r in result.agents:
        parts += [f"## {r.agent.name} — {r.status}", f"Requested: {r.metadata.requested_model} | Reported: {r.metadata.reported_model or 'Not reported'}",
                  "```json\n" + (r.output.model_dump_json(indent=2) if r.output else '{}') + "\n```",
                  r.error or ""]
    parts += [f"Human decision: {result.approval}"]
    return redact("\n\n".join(parts), secrets)
