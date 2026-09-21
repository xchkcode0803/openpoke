"""Explicitly invoked paid routing-grader checks."""

from __future__ import annotations

import asyncio

import pytest
from deepeval.test_case import LLMTestCase, ToolCall

from evals.agent_overload.grading.metrics import InstructionFidelityMetric


def _semantic_case(instruction: str) -> LLMTestCase:
    return LLMTestCase(
        input="Draft a follow-up about the repair date, but do not send it.",
        actual_output="I will draft it.",
        tools_called=[
            ToolCall(
                name="send_message_to_agent",
                input_parameters={"action": "reuse", "agent_name": "Email Landlord About Kitchen Leak", "instructions": instruction},
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
    score = asyncio.run(metric.a_measure(_semantic_case(instruction)))
    assert score == (1.0 if should_pass else 0.0), metric.score_breakdown


@pytest.mark.live
@pytest.mark.grader_live
def test_live_fallback_judge_returns_structured_verdict() -> None:
    if not __import__("os").getenv("RUN_LIVE_EVALS"):
        pytest.skip("set RUN_LIVE_EVALS=1 to call live judges")
    from evals.agent_overload.grading.metrics import OpenRouterFallbackJudge

    answer = asyncio.run(
        OpenRouterFallbackJudge().evaluate(
            {"delegated_instruction": "Draft the reply and wait for approval."},
            {"type": "noul", "instructions": "Does the instruction avoid sending the email?", "criteria": {"true": "wait for approval", "false": "send the email"}},
        )
    )
    assert answer.verdict is True
    assert answer.fallback_used is True
