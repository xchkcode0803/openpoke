"""Eval-only shared pacing and bounded rate-limit retries."""
import asyncio
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx
from pathlib import Path
from uuid import uuid4
import json

from evals.shared.models import SONNET, GEMINI

MODEL = os.getenv("EVAL_CANDIDATE_MODEL", SONNET)


def request_interval():
    """Only the Gemini comparison removes fixed pacing; retries remain bounded."""
    return 0.0 if MODEL == GEMINI else 4.1


_gate = None
_gate_loop = None
_next_request = 0.0
_post = httpx.AsyncClient.post
context_limits: dict[str, int] = {}
_artifact_dir: Path | None = None
request_budget = None  # Set only within the opt-in stress campaign lifecycle.


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
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await paced_post(client, "https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json=payload)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"OpenRouter transport error: {exc}") from exc
    if response.is_error:
        raise RuntimeError(f"OpenRouter request failed ({response.status_code}): {response.text}")
    result = response.json()
    result["_eval_timing"] = response.extensions["eval_timing"]
    return result


def failure_kind(error: str | None) -> str | None:
    if not error:
        return None
    text = error.lower()
    if any(value in text for value in ("budget limit", "pricing unavailable", "provider usage unavailable", "provider charge", "unsettled request", "missing or invalid provider charge")):
        return "budget"
    if "tool iteration limit" in text:
        return "agent_iteration_limit"
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
    global _next_request, _gate, _gate_loop
    if not str(url).startswith("https://openrouter.ai/"):
        return await _post(client, url, **kwargs)
    loop = asyncio.get_running_loop()
    if _gate_loop is not loop:
        _gate_loop, _gate = loop, asyncio.Lock()
    request_seconds = 0.0
    pacing_seconds = 0.0
    retry_wait_seconds = 0.0
    for attempt in range(4):
        before_wait = time.monotonic()
        async with _gate:
            await asyncio.sleep(max(0, _next_request - time.monotonic()))
            _next_request = time.monotonic() + request_interval()
        pacing_seconds += time.monotonic() - before_wait
        reservation = request_budget.reserve(kwargs["json"]) if request_budget else None
        if request_budget:
            budget_wait = time.monotonic()
            await asyncio.sleep(request_budget.delay(reservation))
            pacing_seconds += time.monotonic() - budget_wait
        started = time.monotonic()
        response = await _post(client, url, **kwargs)
        if request_budget:
            request_budget.settle(reservation, response)
        request_seconds += time.monotonic() - started
        response.extensions["eval_timing"] = {
            "request_seconds": request_seconds, "pacing_seconds": pacing_seconds,
            "retry_wait_seconds": retry_wait_seconds, "attempts": attempt + 1,
        }
        if response.status_code != 429 or attempt == 3:
            return response
        before_wait = time.monotonic()
        await asyncio.sleep(retry_delay(response.headers.get("Retry-After"), attempt))
        retry_wait_seconds += time.monotonic() - before_wait


async def verify_context_limit(model: str) -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        entry = next(item for item in response.json()["data"] if item["id"] == model)
        context_limits[model] = int(entry["context_length"])
