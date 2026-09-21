"""Shared Jev decisions and structured Gemini fallback grading."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from .usage import effective_cost
from .models import GEMINI, JEV

from evals.shared.http import post_with_retry
from evals.agent_overload.runtime.provider import save_result

JEV_MODEL = JEV
FALLBACK_MODEL = GEMINI
JEV_YES_THRESHOLD = 0.90
JEV_NO_THRESHOLD = 0.10


class JudgeError(RuntimeError):
    """Raised when a semantic judge cannot return a valid verdict."""


@dataclass(frozen=True)
class JudgeAnswer:
    verdict: bool
    probability: float | None
    reason: str = ""
    fallback_used: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None
    latency_seconds: float | None = None


class JevJudge(Protocol):
    async def evaluate(self, state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> dict[str, JudgeAnswer]: ...


class FallbackJudge(Protocol):
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


class OpenRouterJevJudge:
    """Call Jev through OpenRouter's Decisions endpoint."""

    async def evaluate(self, state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> dict[str, JudgeAnswer]:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await post_with_retry(client,
                    "https://openrouter.ai/api/alpha/decisions",
                    headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"},
                    json={"model": JEV_MODEL, "state": state, "questions": questions},
                )
        except httpx.HTTPError as exc:
            raise JudgeError(f"Jev request failed: {exc}") from exc
        if response.is_error:
            raise JudgeError(f"Jev request failed ({response.status_code}): {response.text}")
        payload = response.json()
        input_tokens, output_tokens, cost = _usage(payload)
        save_result("judge_usage.jsonl", {"model": JEV_MODEL, "input_tokens": input_tokens, "output_tokens": output_tokens, "cost": cost, "latency_seconds": time.perf_counter() - started})
        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise JudgeError("Jev response did not contain answers")
        result: dict[str, JudgeAnswer] = {}
        for key in questions:
            answer = answers.get(key)
            probability = answer.get("noul") if isinstance(answer, dict) else None
            if not isinstance(probability, (int, float)):
                raise JudgeError(f"Jev answer for {key} did not contain a Noul probability")
            result[key] = JudgeAnswer(
                verdict=probability >= 0.5,
                probability=float(probability),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                latency_seconds=time.perf_counter() - started,
            )
        return result


class OpenRouterFallbackJudge:
    """Use Gemini tool calling for the few Jev judgments near the boundary."""

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
                        "model": FALLBACK_MODEL,
                        "messages": [{"role": "user", "content": json.dumps(prompt)}],
                        "tools": [schema],
                        "tool_choice": {"type": "function", "function": {"name": "submit_grade"}},
                        "stream": False,
                    },
                )
        except httpx.HTTPError as exc:
            raise JudgeError(f"Fallback request failed: {exc}") from exc
        if response.is_error:
            raise JudgeError(f"Fallback request failed ({response.status_code}): {response.text}")
        payload = response.json()
        message = ((payload.get("choices") or [{}])[0].get("message") or {})
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            raise JudgeError("Fallback judge did not call submit_grade")
        raw = ((tool_calls[0].get("function") or {}).get("arguments"))
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as exc:
            raise JudgeError("Fallback judge returned invalid grade JSON") from exc
        if not isinstance(parsed, dict) or not isinstance(parsed.get("verdict"), bool):
            raise JudgeError("Fallback judge returned an invalid verdict")
        input_tokens, output_tokens, cost = _usage(payload)
        save_result("judge_usage.jsonl", {"model": FALLBACK_MODEL, "input_tokens": input_tokens, "output_tokens": output_tokens, "cost": cost, "latency_seconds": time.perf_counter() - started})
        return JudgeAnswer(
            verdict=parsed["verdict"],
            probability=None,
            reason=str(parsed.get("reason", "")),
            fallback_used=True,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            latency_seconds=time.perf_counter() - started,
        )
