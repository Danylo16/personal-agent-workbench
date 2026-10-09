import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Protocol
import httpx
from .schemas import AgentConfig, Attempt, ExecutionMetadata, now
from .prompts import SCHEMAS

BASE_URLS = {"OpenRouter": "https://openrouter.ai/api/v1", "Groq": "https://api.groq.com/openai/v1"}

class ProviderError(Exception):
    pass

class RequestBudget:
    def __init__(self, limit: int = 4):
        if not 1 <= limit <= 20:
            raise ValueError("Request limit must be 1–20.")
        self.limit, self.used = limit, 0
        self._lock = asyncio.Lock()

    async def consume(self):
        async with self._lock:
            if self.used >= self.limit:
                raise ProviderError("Per-run request budget exhausted. Increase it only for an intentional rerun.")
            self.used += 1

@dataclass
class Completion:
    text: str
    reported_model: str | None = None
    usage: dict[str, int] | None = None
    finish_reason: str | None = None

class Provider(Protocol):
    source: str
    name: str
    async def complete(self, agent: AgentConfig, messages: list[dict[str, str]], budget: RequestBudget, metadata: ExecutionMetadata) -> Completion: ...

class APIProvider:
    source = "api"
    def __init__(self, name: str, key: str, client: httpx.AsyncClient, retries: int = 1, free_tier_confirmed: bool = False):
        if name not in BASE_URLS:
            raise ValueError("Unsupported provider")
        self.name, self._key, self.client = name, key, client
        self.retries = min(max(retries, 0), 2)
        self.free_tier_confirmed = free_tier_confirmed

    async def complete(self, agent, messages, budget, metadata):
        if not self._key:
            raise ProviderError(f"Missing {self.name} API key. Configure .env or use Manual mode.")
        if self.name == "OpenRouter" and agent.model != "openrouter/free" and not agent.model.endswith(":free"):
            raise ProviderError("Paid or unverified OpenRouter model blocked. Select openrouter/free or a :free model.")
        if self.name == "Groq" and not self.free_tier_confirmed:
            raise ProviderError("Groq calls blocked until you confirm a free-tier account; model IDs do not prove zero cost.")
        for retry in range(self.retries + 1):
            await budget.consume()
            attempt = Attempt(number=len(metadata.attempts) + 1)
            metadata.attempts.append(attempt)
            retryable, delay = False, min(2 ** retry, 8)
            try:
                payload = {"model": agent.model, "messages": messages, "max_tokens": agent.max_tokens, "stream": False}
                if self.name == "OpenRouter":
                    # Hard upper pricing cap; a :free slug alone is not the only safeguard.
                    payload["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": agent.id + "_output",
                            "strict": True,
                            "schema": SCHEMAS[agent.id].model_json_schema(),
                        },
                    }
                    payload["provider"] = {
                        "max_price": {"prompt": 0, "completion": 0},
                        "require_parameters": True,
                    }
                response = await self.client.post(BASE_URLS[self.name] + "/chat/completions",
                    headers={"Authorization": "Bearer " + self._key}, json=payload, timeout=agent.timeout)
                attempt.http_status = response.status_code
                if response.status_code in (401, 403):
                    raise ProviderError("Credentials invalid or account/model access denied (HTTP 401/403). Check the key and account permissions.")
                if response.status_code == 429 or response.status_code >= 500:
                    retryable = True
                    try:
                        delay = min(max(float(response.headers.get("Retry-After", delay)), delay), 15)
                    except ValueError:
                        pass
                    raise ProviderError(f"Provider unavailable or rate limited (HTTP {response.status_code}).")
                if response.status_code >= 400:
                    raise ProviderError(f"Provider rejected the request (HTTP {response.status_code}). Check model availability, JSON Schema support and account quota. For OpenRouter select a free model advertising structured_outputs.")
                try:
                    data = response.json()
                    msg = data["choices"][0]["message"]["content"]
                    if not isinstance(msg, str) or not msg.strip():
                        raise ValueError()
                    usage = data.get("usage")
                    usage = {k: v for k, v in usage.items() if isinstance(v, int) and not isinstance(v, bool)} if isinstance(usage, dict) else None
                    reported = data.get("model")
                    completion = Completion(msg, reported if isinstance(reported, str) else None, usage or None, data["choices"][0].get("finish_reason"))
                except (ValueError, KeyError, IndexError, TypeError):
                    raise ProviderError("Malformed provider response: missing completion content.") from None
                attempt.status = "success"
                return completion
            except asyncio.CancelledError:
                attempt.status = "cancelled"
                raise
            except (httpx.TimeoutException, httpx.TransportError):
                retryable = True
                attempt.error = "Provider network error or timeout. No response confirmed."
            except ProviderError as exc:
                attempt.error = str(exc)
            finally:
                attempt.finished_at = now()
            attempt.status = "failed"
            if not retryable or retry == self.retries:
                raise ProviderError(attempt.error) from None
            if budget.used >= budget.limit:
                raise ProviderError("Request budget exhausted after provider failure; no further retry sent.")
            attempt.backoff_seconds = delay
            await asyncio.sleep(delay)

async def discover_models(name: str, key: str = "") -> list[str]:
    if name not in BASE_URLS:
        raise ProviderError("Unsupported provider")
    headers = {"Authorization": "Bearer " + key} if key else {}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BASE_URLS[name] + "/models", headers=headers, timeout=15)
        if response.status_code != 200:
            raise ProviderError(f"Model discovery failed (HTTP {response.status_code}).")
        data = response.json()["data"]
        if name == "OpenRouter":
            models = [m["id"] for m in data if m["id"].endswith(":free") and
                      float(m.get("pricing", {}).get("prompt", "-1")) == 0 and
                      float(m.get("pricing", {}).get("completion", "-1")) == 0]
            return sorted(set(models + ["openrouter/free"]))
        return sorted(m["id"] for m in data if m.get("active", True))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise ProviderError("Model discovery unavailable or malformed. Consult provider console; no automatic paid fallback.") from None

class MockProvider:
    source = "mock"
    name = "Offline mock — NOT LIVE AI"
    def __init__(self, fail_agent: str | None = None):
        self.fail_agent = fail_agent

    async def complete(self, agent, messages, budget, metadata):
        await asyncio.sleep(0.04)
        if agent.id == self.fail_agent:
            raise ProviderError("Deliberately simulated failure (MOCK).")
        if agent.id == "reviewer":
            out = {"comparison": "MOCK: Neither hypothesis is established.", "unsupported_assumptions": ["No source code available"], "contradictions": [], "failure_cases": ["A 200 may contain an unexpected payload"], "distinguishing_tests": ["Inspect browser URL, response body and Next route files"]}
        elif agent.id == "judge":
            out = {"recommendation": "MOCK: Gather route and response evidence before editing.", "reasoning": ["HTTP status alone cannot establish a root cause"], "ranked_hypotheses": [{"hypothesis": "Missing frontend route", "evidence": ["Reported frontend 404; not repository-verified"], "validation": "Inspect the Next route tree"}], "verified_facts": [], "assumptions": ["The symptom description is accurate"], "unknowns": ["Actual source code and response payload"], "risks": ["Changing routing without regression checks"], "disagreements": ["Routing versus data contract remains unresolved"], "verification_steps": ["Collect route files and network response"], "human_review_required": True, "human_decisions": ["Approve a fix only after reproducing the cause"], "abstain": True, "abstention_reason": "MOCK output; cannot diagnose actual repository"}
        else:
            out = {"recommendation": "MOCK: Inspect " + ("frontend routing" if agent.id == "architect" else "API response contract"), "reasoning": ["Reported API 200 does not prove the frontend route exists"], "assumptions": ["Repository is not available"], "risks": ["Misdiagnosis"], "verification_steps": ["Capture the exact request URL and response"]}
        return Completion(json.dumps(out), "deterministic-fixture", None, "stop")
