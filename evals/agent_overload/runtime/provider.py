"""Eval-only provider helpers and per-run artifacts."""
import os
from datetime import datetime, timezone
import httpx
from pathlib import Path
from uuid import uuid4
import json

from evals.shared.http import post_with_retry
from evals.shared.models import GEMINI

MODEL = os.getenv("EVAL_CANDIDATE_MODEL", GEMINI)
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
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await post_with_retry(client, "https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json=payload)
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
    if "tool iteration limit" in text:
        return "agent_iteration_limit"
    if any(value in text for value in ("context length", "context_length", "context window", "capacity limit")):
        return "capacity"
    if any(value in text for value in ("openrouter", "429", "jev request", "fallback request")):
        return "provider"
    return "harness"


async def verify_context_limit(model: str) -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        entry = next(item for item in response.json()["data"] if item["id"] == model)
        context_limits[model] = int(entry["context_length"])
