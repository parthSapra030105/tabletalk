"""
The one place that talks to the LLM.

The provider is configuration, not code: LLM_BASE_URL, LLM_API_KEY and LLM_MODEL
point the OpenAI SDK at any OpenAI-compatible endpoint. Every call goes through
`structured()`, which asks for JSON matching a schema and records token usage.
"""

import json
import os
import re
import time
from dataclasses import asdict, dataclass

from openai import APITimeoutError, InternalServerError, OpenAI, RateLimitError

_client = None
RATE_LIMIT_RETRIES = 2
RATE_LIMIT_MAX_WAIT = 60     # seconds; a per-minute limit is worth waiting out, a daily quota is not


@dataclass
class Usage:
    purpose: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int        # can exceed prompt + completion: reasoning ("thinking") tokens are billed too
    seconds: float

    def as_dict(self):
        return asdict(self)


def client():
    global _client
    if _client is None:
        # The SDK retries 429s and 5xx with exponential backoff; overloaded models are common enough to need it.
        _client = OpenAI(base_url=os.environ.get("LLM_BASE_URL") or None, api_key=os.environ["LLM_API_KEY"],
                         max_retries=2, timeout=45)
    return _client


def _create(model, request):
    """
    One completion. A per-minute rate limit says how long to wait (Gemini: "retryDelay": "34s");
    if that's short, wait and try again rather than fail. A daily quota asks for hours, so it
    raises at once and the caller can fall back.
    """
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return client().chat.completions.create(model=model, **request)
        except RateLimitError as exc:
            wait = _retry_delay(exc)
            if attempt == RATE_LIMIT_RETRIES or wait is None or wait > RATE_LIMIT_MAX_WAIT:
                raise
            time.sleep(wait + 1)


def _retry_delay(exc):
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s", str(exc))
    return float(m[1]) if m else None


def structured(purpose, messages, schema, schema_name):
    """
    Call the model with a strict JSON schema. Returns (parsed dict, Usage).
    If the model is still overloaded or timing out after the SDK's retries and LLM_FALLBACK_MODEL is set,
    the call is made once more on the fallback; Usage records which model answered.
    """
    model = os.environ["LLM_MODEL"]
    fallback = os.environ.get("LLM_FALLBACK_MODEL")
    request = dict(messages=messages, response_format={
        "type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}})
    start = time.perf_counter()
    try:
        response = _create(model, request)
    except (InternalServerError, RateLimitError, APITimeoutError):
        if not fallback:
            raise
        model = fallback
        response = _create(model, request)
    u = response.usage
    usage = Usage(purpose, model, u.prompt_tokens, u.completion_tokens, u.total_tokens,
                  round(time.perf_counter() - start, 2))
    return json.loads(response.choices[0].message.content), usage
