"""Offline and live validation for routing graders."""

from __future__ import annotations

import asyncio

import pytest
from deepeval.test_case import LLMTestCase, ToolCall

from .metrics import InstructionFidelityMetric, JudgeAnswer, JudgeError, RoutingCorrectnessMetric


def _routing_case(
    *,
    route: str = "reuse",
    agent_name: str = "Montreal Hotel Search",
    expected_name: str = "Montreal Hotel Search",
) -> LLMTestCase:
    return LLMTestCase(
        input="Find more Montreal hotels.",
        actual_output="I am on it.",
        tools_called=[
            ToolCall(
                name="send_message_to_user",
                input_parameters={"message": "I will look into that."},
                output={"success": True, "payload": {"status": "delivered"}},
            ),
            ToolCall(
                name="send_message_to_agent",
                input_parameters={"agent_name": agent_name, "instructions": "Find more Montreal hotels."},
                output={"success": True, "payload": {"new_agent_created": route == "create"}},
            )
        ],
        metadata={
            "runtime_success": True,
            "expected_action": "delegate",
            "expected_delegations": [
                {"task_key": "hotels", "route": route, "acceptable_agent_names": [expected_name], "required_facts": [], "forbidden_facts": []}
            ],
        },
    )


def test_deterministic_grader_accepts_matching_reuse() -> None:
    metric = RoutingCorrectnessMetric()
    assert metric.measure(_routing_case()) == 1.0


@pytest.mark.parametrize("acknowledgement", ["before", "after", "absent"])
def test_grading_does_not_depend_on_acknowledgement(acknowledgement):
    case = _routing_case()
    if acknowledgement == "after":
        case.tools_called.reverse()
    elif acknowledgement == "absent":
        case.tools_called = [call for call in case.tools_called if call.name != "send_message_to_user"]
        case.actual_output = ""
    assert RoutingCorrectnessMetric().measure(case) == 1.0
    semantic = InstructionFidelityMetric(_FakeJev(0.95), _FakeFallback(False))
    assert semantic.measure(case) == 1.0
    case.tools_called = [call for call in case.tools_called if call.name != "send_message_to_agent"]
    assert RoutingCorrectnessMetric().measure(case) == 0.0


def test_response_case_still_requires_visible_response():
    case = LLMTestCase(input="Thanks", actual_output="", tools_called=[], metadata={"expected_action": "respond"})
    assert RoutingCorrectnessMetric().measure(case) == 0.0


def test_deterministic_grader_rejects_wrong_agent() -> None:
    metric = RoutingCorrectnessMetric()
    assert metric.measure(_routing_case(agent_name="Toronto Hotel Search")) == 0.0
    assert "missing reuse delegation" in metric.reason


def test_deterministic_grader_rejects_extra_delegation() -> None:
    test_case = _routing_case()
    test_case.tools_called.append(
        ToolCall(
            name="send_message_to_agent",
            input_parameters={"agent_name": "Monthly Rent Reminder", "instructions": "Check rent."},
            output={"success": True, "payload": {"new_agent_created": False}},
        )
    )
    metric = RoutingCorrectnessMetric()
    assert metric.measure(test_case) == 0.0
    assert "extra delegation" in metric.reason


def test_deterministic_grader_accepts_parallel_create_range() -> None:
    test_case = LLMTestCase(
        input="Research whether I should move to Montreal permanently.",
        actual_output="I will research that.",
        tools_called=[
            ToolCall(name="send_message_to_user", input_parameters={"message": "I will research that."}),
            ToolCall(name="send_message_to_agent", input_parameters={"agent_name": "Montreal Cost Research", "instructions": "Research costs and jobs."}, output={"success": True, "payload": {"new_agent_created": True}}),
            ToolCall(name="send_message_to_agent", input_parameters={"agent_name": "Montreal Immigration Research", "instructions": "Research immigration and climate."}, output={"success": True, "payload": {"new_agent_created": True}}),
        ],
        metadata={
            "runtime_success": True,
            "expected_action": "delegate",
            "expected_delegations": [
                {"task_key": "move", "route": "create", "acceptable_agent_names": [], "required_facts": [], "forbidden_facts": [], "min_calls": 1, "max_calls": None, "missing_dependency": None}
            ],
        },
    )
    assert RoutingCorrectnessMetric().measure(test_case) == 1.0


def test_deterministic_grader_records_missing_created_dependency() -> None:
    test_case = LLMTestCase(
        input="Continue the dinner planning.",
        actual_output="I will continue.",
        tools_called=[],
        metadata={
            "runtime_success": True,
            "expected_action": "delegate",
            "expected_delegations": [
                {"task_key": "dinner", "route": "reuse", "acceptable_agent_names": [], "required_facts": [], "forbidden_facts": [], "min_calls": 1, "max_calls": 1, "missing_dependency": "maya_dinner"}
            ],
        },
    )
    metric = RoutingCorrectnessMetric()
    assert metric.measure(test_case) == 0.0
    assert "required prior agent was not created" in metric.reason


class _FakeJev:
    def __init__(self, probability: float) -> None:
        self.probability = probability

    async def evaluate(self, state, questions):
        return {key: JudgeAnswer(verdict=self.probability >= 0.5, probability=self.probability) for key in questions}


class _FakeFallback:
    def __init__(self, verdict: bool) -> None:
        self.verdict = verdict
        self.calls = 0

    async def evaluate(self, state, question):
        self.calls += 1
        return JudgeAnswer(verdict=self.verdict, probability=None, fallback_used=True, reason="fake fallback")


def _semantic_case(instruction: str) -> LLMTestCase:
    return LLMTestCase(
        input="Draft a follow-up about the repair date, but do not send it.",
        actual_output="I will draft it.",
        tools_called=[
            ToolCall(
                name="send_message_to_agent",
                input_parameters={"agent_name": "Email Landlord About Kitchen Leak", "instructions": instruction},
                output={"success": True, "payload": {"new_agent_created": False}},
            )
        ],
        metadata={
            "expected_delegations": [
                {
                    "task_key": "landlord",
                    "route": "reuse",
                    "acceptable_agent_names": ["Email Landlord About Kitchen Leak"],
                    "required_facts": ["draft a follow-up about the repair date", "do not send"],
                    "forbidden_facts": ["send the email"],
                }
            ],
            "response_requirements": [],
        },
    )


def test_semantic_grader_accepts_confident_yes() -> None:
    metric = InstructionFidelityMetric(_FakeJev(0.95), _FakeFallback(False))
    assert asyncio.run(metric.a_measure(_semantic_case("Draft a repair-date follow-up and wait for approval before sending."))) == 1.0


def test_semantic_grader_rejects_confident_no() -> None:
    metric = InstructionFidelityMetric(_FakeJev(0.05), _FakeFallback(True))
    assert asyncio.run(metric.a_measure(_semantic_case("Draft and send the repair-date follow-up."))) == 0.0


def test_semantic_grader_uses_fallback_for_uncertain_answer() -> None:
    fallback = _FakeFallback(True)
    metric = InstructionFidelityMetric(_FakeJev(0.5), fallback)
    assert asyncio.run(metric.a_measure(_semantic_case("Draft the repair-date follow-up."))) == 1.0
    assert fallback.calls == 4
    assert all(item["probability"] == 0.5 and item["fallback_used"] for item in metric.score_breakdown.values())


@pytest.mark.live
@pytest.mark.grader_live
@pytest.mark.parametrize(
    ("instruction", "should_pass"),
    [
        ("Draft the repair-date follow-up and wait for approval before sending.", True),
        ("Prepare a reply about the repair date. Do not send it.", True),
        ("Write a repair-date follow-up for the user to review before any send.", True),
        ("Create a draft about the repair date and wait for confirmation.", True),
        ("Draft a reply about the repair date without sending anything.", True),
        ("Prepare the landlord follow-up, then ask the user whether to send it.", True),
        ("Draft and send the repair-date follow-up.", False),
        ("Email the landlord immediately about the repair date.", False),
        ("Ask the landlord to arrange a new unrelated inspection.", False),
        ("Draft a follow-up about an unrelated billing issue.", False),
        ("Buy a replacement appliance for the kitchen.", False),
        ("Ask the landlord to schedule a different issue.", False),
    ],
)
def test_live_semantic_grader(instruction: str, should_pass: bool) -> None:
    if not __import__("os").getenv("RUN_LIVE_EVALS"):
        pytest.skip("set RUN_LIVE_EVALS=1 to call live judges")
    metric = InstructionFidelityMetric()
    assert asyncio.run(metric.a_measure(_semantic_case(instruction))) == (1.0 if should_pass else 0.0)


@pytest.mark.live
@pytest.mark.grader_live
def test_live_fallback_judge_returns_structured_verdict() -> None:
    if not __import__("os").getenv("RUN_LIVE_EVALS"):
        pytest.skip("set RUN_LIVE_EVALS=1 to call live judges")
    from .metrics import OpenRouterFallbackJudge

    answer = asyncio.run(
        OpenRouterFallbackJudge().evaluate(
            {"delegated_instruction": "Draft the reply and wait for approval."},
            {"type": "noul", "instructions": "Does the instruction avoid sending the email?", "criteria": {"true": "wait for approval", "false": "send the email"}},
        )
    )
    assert answer.verdict is True
    assert answer.fallback_used is True
