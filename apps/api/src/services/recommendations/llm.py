import json
import re

import httpx

from src.config import Settings
from src.services.recommendations.text import TEXT_FIELDS

SYSTEM_PROMPT = (
    "You write short text for a recommendation about AI-agent traffic on a website. "
    "Use ONLY the facts in the JSON fact bundle. Do not invent numbers, paths, or agent names. "
    "Use short, plain sentences. Return ONLY a JSON object with these string keys: "
    "reason (what the logs show), potential_issue (what may be wrong; this is an inference), "
    "suggested_validation (how to check), next_action (must state what is Unknown and why a "
    "simulation with a real agent is needed)."
)


class LLMError(Exception):
    pass


class AnthropicClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds
        self.transport = transport

    async def write_text(self, bundle: dict) -> dict:
        body = {
            "model": self.model,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": json.dumps(bundle, default=str, sort_keys=True)}
            ],
        }
        headers = {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(f"{self.base_url}/v1/messages", json=body, headers=headers)
        if response.status_code != 200:
            raise LLMError(f"LLM returned status {response.status_code}")
        return parse_text(response.json())


def parse_text(payload: dict) -> dict:
    try:
        raw = "".join(b["text"] for b in payload["content"] if b.get("type") == "text")
    except (KeyError, TypeError) as exc:
        raise LLMError("LLM response has no text") from exc
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise LLMError("LLM response has no JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMError("LLM response is not valid JSON") from exc
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) for k in TEXT_FIELDS):
        raise LLMError("LLM response misses a field")
    return {k: data[k] for k in TEXT_FIELDS}


def default_client(settings: Settings) -> AnthropicClient | None:
    if not settings.llm_api_key:
        return None
    return AnthropicClient(settings)
