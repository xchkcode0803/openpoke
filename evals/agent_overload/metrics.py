"""Deterministic and semantic graders for OpenPoke routing traces."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase, ToolCall


JEV_MODEL = "typesafe/jev-1.13"
FALLBACK_MODEL = "anthropic/claude-sonnet-5"
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
    cost = usage.get("cost") or payload.get("cost")
    return (
        int(input_tokens) if isinstance(input_tokens, (int, float)) else None,
        int(output_tokens) if isinstance(output_tokens, (int, float)) else None,
        float(cost) if isinstance(cost, (int, float)) else None,
    )


class OpenRouterJevJudge:
    """Call Jev through OpenRouter's Decisions endpoint."""

    async def evaluate(self, state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> dict[str, JudgeAnswer]:
        started = time.perf_counter()
        response: httpx.Response | None = None
        error: httpx.HTTPError | None = None
        for _ in range(2):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        "https://openrouter.ai/api/alpha/decisions",
                        headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"},
                        json={"model": JEV_MODEL, "state": state, "questions": questions},
                    )
                break
            except httpx.HTTPError as exc:
                error = exc
        if response is None:
            raise JudgeError(f"Jev request failed after retry: {error}") from error
        if response.is_error:
            raise JudgeError(f"Jev request failed ({response.status_code}): {response.text}")
        payload = response.json()
        input_tokens, output_tokens, cost = _usage(payload)
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
    """Use Sonnet tool calling for the few Jev judgments near the boundary."""

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
        response: httpx.Response | None = None
        error: httpx.HTTPError | None = None
        for _ in range(2):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
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
                break
            except httpx.HTTPError as exc:
                error = exc
        if response is None:
            raise JudgeError(f"Fallback request failed after retry: {error}") from error
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


def _delegations(test_case: LLMTestCase) -> list[ToolCall]:
    return [call for call in test_case.tools_called or [] if call.name == "send_message_to_agent"]


def _tool_success(call: ToolCall) -> bool:
    return not isinstance(call.output, dict) or bool(call.output.get("success", True))


def _route(call: ToolCall) -> str:
    if isinstance(call.output, dict):
        payload = call.output.get("payload") or {}
        if isinstance(payload, dict) and payload.get("new_agent_created") is True:
            return "create"
    return "reuse"


def _agent_name(call: ToolCall) -> str:
    return str((call.input_parameters or {}).get("agent_name", ""))


class RoutingCorrectnessMetric(BaseMetric):
    """Strictly grade routing decisions from recorded tool calls."""

    def __init__(self) -> None:
        self.threshold = 1.0
        self.strict_mode = True
        self.async_mode = False
        self.include_reason = True
        self.error = None

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        metadata = test_case.metadata or {}
        expected_action = metadata.get("expected_action")
        expected = list(metadata.get("expected_delegations") or [])
        actual = _delegations(test_case)
        failures: list[str] = []
        if not metadata.get("runtime_success", True):
            failures.append(f"runtime failed: {metadata.get('runtime_error', 'unknown error')}")
        if any(not _tool_success(call) for call in test_case.tools_called or []):
            failures.append("a routing tool failed")

        if expected_action == "delegate":
            unmatched = list(actual)
            exact_expectations = [item for item in expected if item.get("max_calls", 1) == 1]
            flexible_expectations = [item for item in expected if item.get("max_calls", 1) != 1]
            for item in exact_expectations:
                if item.get("missing_dependency"):
                    failures.append(
                        f"required prior agent was not created: {item['missing_dependency']}"
                    )
                    continue
                route = item["route"]
                names = set(item.get("acceptable_agent_names") or [])
                match_index = next(
                    (
                        index
                        for index, call in enumerate(unmatched)
                        if _route(call) == route and (route == "create" or _agent_name(call) in names)
                    ),
                    None,
                )
                if match_index is None:
                    detail = ", ".join(sorted(names)) if names else "a new agent"
                    failures.append(f"missing {route} delegation for {item['task_key']}: {detail}")
                else:
                    unmatched.pop(match_index)
            for item in flexible_expectations:
                route = item["route"]
                names = set(item.get("acceptable_agent_names") or [])
                matching = [
                    call
                    for call in unmatched
                    if _route(call) == route and (route == "create" or _agent_name(call) in names)
                ]
                minimum = int(item.get("min_calls", 1))
                maximum = item.get("max_calls")
                if len(matching) < minimum:
                    failures.append(
                        f"missing {route} delegation for {item['task_key']}: expected at least {minimum}"
                    )
                if maximum is not None and len(matching) > int(maximum):
                    failures.append(
                        f"too many {route} delegations for {item['task_key']}: expected at most {maximum}"
                    )
                for call in matching:
                    unmatched.remove(call)
            if unmatched:
                failures.append("extra delegation: " + ", ".join(_agent_name(call) for call in unmatched))
            seen = [_agent_name(call) for call in actual]
            if len(seen) != len(set(seen)):
                failures.append("duplicate agent delegation")
            tool_names = [call.name for call in test_case.tools_called or []]
            first_agent = next(
                (index for index, name in enumerate(tool_names) if name == "send_message_to_agent"),
                None,
            )
            acknowledged = any(
                name == "send_message_to_user"
                for name in tool_names[:first_agent] if first_agent is not None
            )
            if first_agent is not None and not acknowledged:
                failures.append("delegation occurred before user acknowledgement")
        else:
            if actual:
                failures.append("delegated when no delegation was expected")
            tool_names = [call.name for call in test_case.tools_called or []]
            if expected_action == "wait" and "wait" not in tool_names:
                failures.append("expected wait tool")
            if expected_action == "respond":
                visible = test_case.actual_output or ""
                user_tool = any(call.name == "send_message_to_user" for call in test_case.tools_called or [])
                if not visible and not user_tool:
                    failures.append("expected user-visible response")

        self.score = 0.0 if failures else 1.0
        self.success = not failures
        self.reason = "; ".join(failures) if failures else "routing matched expectation"
        self.score_breakdown = {"failed_checks": failures}
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        return self.measure(test_case, *args, **kwargs)

    @property
    def __name__(self) -> str:
        return "RoutingCorrectnessMetric"


class InstructionFidelityMetric(BaseMetric):
    """Use Jev for narrow semantic requirements, with Sonnet fallback."""

    def __init__(self, jev: JevJudge | None = None, fallback: FallbackJudge | None = None) -> None:
        self.threshold = 1.0
        self.strict_mode = True
        self.async_mode = False
        self.include_reason = True
        self.error = None
        self.jev = jev or OpenRouterJevJudge()
        self.fallback = fallback or OpenRouterFallbackJudge()

    def _questions(self, test_case: LLMTestCase) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        metadata = test_case.metadata or {}
        expected = list(metadata.get("expected_delegations") or [])
        actual = _delegations(test_case)
        questions: dict[str, dict[str, Any]] = {}
        states: dict[str, dict[str, Any]] = {}
        remaining = list(actual)
        question_index = 0
        ordered_expected = sorted(
            expected,
            key=lambda item: item.get("max_calls", 1) != 1,
        )
        for item in ordered_expected:
            route = item["route"]
            names = set(item.get("acceptable_agent_names") or [])
            candidates = [
                call
                for call in remaining
                if _route(call) == route and (route == "create" or _agent_name(call) in names)
            ]
            maximum = item.get("max_calls", 1)
            matches = candidates if maximum is None else candidates[: int(maximum)]
            if not matches:
                continue
            for match in matches:
                remaining.remove(match)
            instructions = [
                str((match.input_parameters or {}).get("instructions", ""))
                for match in matches
            ]
            state = {
                "user_request": test_case.input,
                "delegated_instructions": instructions,
                "agent_names": [_agent_name(match) for match in matches],
            }
            for fact in item.get("required_facts") or []:
                key = f"required_{question_index}"
                question_index += 1
                questions[key] = {
                    "type": "noul",
                    "instructions": "Does the delegated instruction preserve this required user intent?",
                    "criteria": {"true": str(fact), "false": "The requirement is missing, changed, or contradicted."},
                }
                states[key] = state
            for match in matches:
                key = f"relevance_{question_index}"
                question_index += 1
                questions[key] = {
                    "type": "noul",
                    "instructions": "Is this delegated work directly relevant to the user's request?",
                    "criteria": {
                        "true": "The delegated work directly contributes to the requested goal.",
                        "false": "The delegated work is unrelated or adds an unrequested goal.",
                    },
                }
                states[key] = {
                    "user_request": test_case.input,
                    "delegated_instruction": str(
                        (match.input_parameters or {}).get("instructions", "")
                    ),
                    "agent_name": _agent_name(match),
                }
            for fact in item.get("forbidden_facts") or []:
                key = f"forbidden_{question_index}"
                question_index += 1
                questions[key] = {
                    "type": "noul",
                    "instructions": "Does the delegated instruction avoid this prohibited action?",
                    "criteria": {"true": str(fact), "false": "The instruction asks for, permits, or implies the prohibited action."},
                }
                states[key] = state
        for requirement in metadata.get("response_requirements") or []:
            key = f"response_{question_index}"
            question_index += 1
            questions[key] = {
                "type": "noul",
                "instructions": "Does the user-visible response satisfy this requirement?",
                "criteria": {"true": str(requirement), "false": "The response does not satisfy the requirement."},
            }
            states[key] = {"incoming_message": test_case.input, "user_visible_response": test_case.actual_output or ""}
        return questions, states

    async def a_measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        questions, states = self._questions(test_case)
        if not questions:
            self.score = 1.0
            self.success = True
            self.reason = "no semantic requirement"
            self.score_breakdown = {}
            return self.score
        answers: dict[str, JudgeAnswer] = {}
        batched_state = {"checks": states}
        batched_questions = {
            key: {
                **question,
                "instructions": f"Evaluate checks.{key}. {question['instructions']}",
            }
            for key, question in questions.items()
        }
        response = await self.jev.evaluate(batched_state, batched_questions)
        for key, question in questions.items():
            answer = response[key]
            if answer.probability is not None and JEV_NO_THRESHOLD < answer.probability < JEV_YES_THRESHOLD:
                answer = await self.fallback.evaluate(states[key], question)
            answers[key] = answer
        failures = [key for key, answer in answers.items() if not answer.verdict]
        self.score = 0.0 if failures else 1.0
        self.success = not failures
        self.reason = "semantic requirements failed: " + ", ".join(failures) if failures else "semantic requirements preserved"
        self.score_breakdown = {
            key: {"verdict": answer.verdict, "probability": answer.probability, "fallback_used": answer.fallback_used, "reason": answer.reason}
            for key, answer in answers.items()
        }
        metadata = test_case.metadata if test_case.metadata is not None else {}
        metadata["semantic_judgments"] = self.score_breakdown
        return self.score

    def measure(self, test_case: LLMTestCase, *args: Any, **kwargs: Any) -> float:
        return asyncio.run(self.a_measure(test_case, *args, **kwargs))

    @property
    def __name__(self) -> str:
        return "InstructionFidelityMetric"


__all__ = [
    "FALLBACK_MODEL",
    "InstructionFidelityMetric",
    "JEV_MODEL",
    "JudgeAnswer",
    "JudgeError",
    "OpenRouterFallbackJudge",
    "OpenRouterJevJudge",
    "RoutingCorrectnessMetric",
]
