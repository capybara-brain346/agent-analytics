import json
import re

import httpx
from openrouter import OpenRouter
from openrouter.errors import NoResponseError, OpenRouterError
from openrouter.utils import RetryConfig

from src.config import Settings
from src.logger import get_logger
from src.services.recommendations.text import TEXT_FIELDS

log = get_logger(__name__)

SYSTEM_PROMPT = (
    "You write short text for a recommendation about AI-agent traffic on a website. "
    "Use ONLY the facts in the JSON fact bundle. Do not invent numbers, paths, or agent names. "
    "Use short, plain sentences. Return ONLY a JSON object with these string keys: "
    "reason (what the logs show), potential_issue (what may be wrong; this is an inference), "
    "suggested_validation (how to check), next_action (must state what is Unknown and why a "
    "simulation with a real agent is needed)."
)

NO_RETRY = RetryConfig("none", None, False)


class LLMError(Exception):
    pass


class OpenRouterClient:
    def __init__(self, settings: Settings, async_client: httpx.AsyncClient | None = None):
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.openrouter_api_key
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds
        self.async_client = async_client

    async def write_text(self, bundle: dict) -> dict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(bundle, default=str, sort_keys=True)},
        ]
        try:
            async with OpenRouter(
                api_key=self.api_key,
                server_url=self.base_url,
                async_client=self.async_client,
                retry_config=NO_RETRY,
                timeout_ms=int(self.timeout * 1000),
            ) as client:
                result = await client.chat.send_async(
                    model=self.model,
                    messages=messages,
                    max_tokens=1024,
                    response_format={"type": "json_object"},
                    stream=False,
                )
        except (OpenRouterError, NoResponseError, httpx.HTTPError) as exc:
            raise LLMError(f"LLM call failed: {exc}") from exc
        try:
            content = result.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            raise LLMError("LLM response has no choice") from exc
        return parse_text(content)


def parse_text(content) -> dict:
    if not isinstance(content, str):
        raise LLMError("LLM response has no text")
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise LLMError("LLM response has no JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMError("LLM response is not valid JSON") from exc
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) for k in TEXT_FIELDS):
        raise LLMError("LLM response misses a field")
    return {k: data[k] for k in TEXT_FIELDS}


def default_client(settings: Settings) -> OpenRouterClient | None:
    if not settings.openrouter_api_key:
        return None
    if not settings.llm_model:
        log.warning("OPENROUTER_API_KEY is set but LLM_MODEL is not; using template text")
        return None
    return OpenRouterClient(settings)
