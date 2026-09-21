"""Shared structured Gemini grading."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from .usage import effective_cost
from .models import GEMINI

from evals.shared.http import post_with_retry
from evals.agent_overload.provider import save_result

JUDGE_MODEL = GEMINI

class JudgeError(RuntimeError):
    """Raised when a semantic judge cannot return a valid verdict."""


@dataclass(frozen=True)
class JudgeAnswer:
    verdict: bool
    reason: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None
    latency_seconds: float | None = None


class SemanticJudge(Protocol):
    async def evaluate(self, state: dict[str, Any], question: dict[str, Any]) -> JudgeAnswer: ...


def _api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise JudgeError("OPENROUTER_API_KEY is required for live semantic grading")
    return key


def _usage(payload: dict[str, Any]) -> tuple[int | None, int | None, float | None]:
    usage = payload.get("usage") or {}
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or usage.get("inputTokens")
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or usage.get("outputTokens")
    cost = effective_cost(usage) if "cost" in usage else payload.get("cost")
    return (
        int(input_tokens) if isinstance(input_tokens, (int, float)) else None,
        int(output_tokens) if isinstance(output_tokens, (int, float)) else None,
        float(cost) if isinstance(cost, (int, float)) else None,
    )


class GeminiJudge:
    """Return one structured verdict and reason for a semantic requirement."""

    async def evaluate(self, state: dict[str, Any], question: dict[str, Any]) -> JudgeAnswer:
        started = time.perf_counter()
        schema = {
            "type": "function",
            "function": {
                "name": "submit_grade",
                "description": "Return the semantic grading verdict.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "verdict": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                    "required": ["verdict", "reason"],
                    "additionalProperties": False,
                },
            },
        }
        prompt = {
            "state": state,
            "question": question,
            "instruction": "Apply the question exactly. Return only the grading tool call.",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await post_with_retry(client,
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"},
                    json={
                        "model": JUDGE_MODEL,
                        "messages": [{"role": "user", "content": json.dumps(prompt)}],
                        "tools": [schema],
                        "tool_choice": {"type": "function", "function": {"name": "submit_grade"}},
                        "stream": False,
                    },
                )
        except httpx.HTTPError as exc:
            raise JudgeError(f"Gemini judge request failed: {exc}") from exc
        if response.is_error:
            raise JudgeError(f"Gemini judge request failed ({response.status_code}): {response.text}")
        payload = response.json()
        message = ((payload.get("choices") or [{}])[0].get("message") or {})
        tool_calls = message.get("tool_calls") or []
        if len(tool_calls) != 1 or (tool_calls[0].get("function") or {}).get("name") != "submit_grade":
            raise JudgeError("Gemini judge must return exactly one submit_grade call")
        raw = ((tool_calls[0].get("function") or {}).get("arguments"))
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as exc:
            raise JudgeError("Gemini judge returned invalid grade JSON") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("verdict"), bool) or not isinstance(parsed.get("reason"), str):
            raise JudgeError("Gemini judge returned an invalid verdict")
        input_tokens, output_tokens, cost = _usage(payload)
        save_result("judge_usage.jsonl", {"model": JUDGE_MODEL, "input_tokens": input_tokens, "output_tokens": output_tokens, "cost": cost, "latency_seconds": time.perf_counter() - started})
        return JudgeAnswer(
            verdict=parsed["verdict"],
            reason=parsed["reason"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            latency_seconds=time.perf_counter() - started,
        )
