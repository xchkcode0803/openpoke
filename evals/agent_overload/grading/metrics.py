"""Deterministic and semantic graders for OpenPoke routing traces."""
from __future__ import annotations

import asyncio
from typing import Any
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase, ToolCall
from evals.shared.judges import (
    FALLBACK_MODEL, JEV_MODEL, JEV_YES_THRESHOLD, JEV_NO_THRESHOLD,
    JudgeError, JudgeAnswer, JevJudge, FallbackJudge,
    OpenRouterJevJudge, OpenRouterFallbackJudge,
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
    """Use Jev for narrow semantic requirements, with Gemini fallback."""

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
                "conversation_context": metadata.get("conversation_context", []),
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
                    "conversation_context": metadata.get("conversation_context", []),
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
        jev_probabilities = {}
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
            jev_probabilities[key] = answer.probability
            if answer.probability is not None and JEV_NO_THRESHOLD < answer.probability < JEV_YES_THRESHOLD:
                answer = await self.fallback.evaluate(states[key], question)
            answers[key] = answer
        failures = [key for key, answer in answers.items() if not answer.verdict]
        self.score = 0.0 if failures else 1.0
        self.success = not failures
        self.reason = "semantic requirements failed: " + ", ".join(failures) if failures else "semantic requirements preserved"
        self.score_breakdown = {
            key: {"verdict": answer.verdict, "probability": jev_probabilities[key], "fallback_used": answer.fallback_used, "reason": answer.reason}
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
