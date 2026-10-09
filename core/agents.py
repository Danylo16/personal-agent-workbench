import json
import re
from pydantic import ValidationError
from .prompts import SCHEMAS
from .schemas import AgentId

class InvalidOutput(ValueError):
    pass

def parse_output(agent_id: AgentId, raw: str):
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        # Tolerate surrounding prose, but validate the complete object; no fabricated fields.
        start = text.find("{")
        if start < 0:
            raise ValueError("No JSON object")
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return SCHEMAS[agent_id].model_validate(obj)
    except (ValueError, ValidationError) as exc:
        # Do not echo validation input; it can contain sensitive user/provider data.
        raise InvalidOutput("Response does not match the required schema. Raw output retained; downstream stages blocked.") from None
