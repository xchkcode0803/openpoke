"""Eval-only shared pacing and bounded rate-limit retries."""
import asyncio
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from pathlib import Path
from uuid import uuid4
import json

MODEL = "anthropic/claude-sonnet-4"
_next_request = 0.0
_post = httpx.AsyncClient.post
context_limits: dict[str, int] = {}
_artifact_dir: Path | None = None


def artifact_dir() -> Path:
    global _artifact_dir
    if _artifact_dir is None:
        _artifact_dir = Path(".deepeval/runs") / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
        _artifact_dir.mkdir(parents=True)
    return _artifact_dir


def save_result(filename: str, record: dict) -> None:
    with (artifact_dir() / filename).open("a") as stream:
        stream.write(json.dumps(record, default=str) + "\n")


async def interaction_completion(*, model, messages, system=None, api_key=None, tools=None, **kwargs):
    payload = {"model": model, "messages": ([{"role": "system", "content": system}] if system else []) + messages, "stream": False}
    if tools:
        payload["tools"] = tools
    async with httpx.AsyncClient(timeout=60) as client:
        response = await paced_post(client, "https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json=payload)
    if response.is_error:
        raise RuntimeError(f"OpenRouter request failed ({response.status_code}): {response.text}")
    return response.json()


def failure_kind(error: str | None) -> str | None:
    if not error:
        return None
    text = error.lower()
    if any(value in text for value in ("context length", "context_length", "context window", "capacity limit")):
        return "capacity"
    if any(value in text for value in ("openrouter", "429", "jev request", "fallback request")):
        return "provider"
    return "harness"


def retry_delay(value: str | None, attempt: int) -> float:
    try:
        return max(0, float(value))
    except (TypeError, ValueError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return 4 * (attempt + 1)


async def paced_post(client, url, **kwargs):
    global _next_request
    if not str(url).startswith("https://openrouter.ai/"):
        return await _post(client, url, **kwargs)
    for attempt in range(4):
        await asyncio.sleep(max(0, _next_request - time.monotonic()))
        _next_request = time.monotonic() + 4.1
        response = await _post(client, url, **kwargs)
        if response.status_code != 429 or attempt == 3:
            return response
        await asyncio.sleep(retry_delay(response.headers.get("Retry-After"), attempt))


async def verify_context_limit(model: str) -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        entry = next(item for item in response.json()["data"] if item["id"] == model)
        context_limits[model] = int(entry["context_length"])
