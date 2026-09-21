"""Offline and live validation for routing graders."""

from __future__ import annotations

import asyncio

import pytest
from deepeval.test_case import LLMTestCase, ToolCall

from evals.agent_overload.metrics import InstructionFidelityMetric, JudgeAnswer, JudgeError, RoutingCorrectnessMetric


def test_routing_metrics_reexports_shared_judges() -> None:
    from evals.agent_overload import metrics
    from evals.shared import judges

    assert metrics.JudgeAnswer is judges.JudgeAnswer
    assert metrics.JudgeError is judges.JudgeError
    assert metrics.GeminiJudge is judges.GeminiJudge


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
                input_parameters={"action": "reuse", "agent_name": agent_name, "instructions": "Find more Montreal hotels."},
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
    semantic = InstructionFidelityMetric(_FakeJudge(True))
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
            input_parameters={"action": "reuse", "agent_name": "Monthly Rent Reminder", "instructions": "Check rent."},
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
            ToolCall(name="send_message_to_agent", input_parameters={"action": "create", "agent_name": "Montreal Cost Research", "instructions": "Research costs and jobs."}, output={"success": True, "payload": {"new_agent_created": True}}),
            ToolCall(name="send_message_to_agent", input_parameters={"action": "create", "agent_name": "Montreal Immigration Research", "instructions": "Research immigration and climate."}, output={"success": True, "payload": {"new_agent_created": True}}),
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


class _FakeJudge:
    def __init__(self, verdict: bool) -> None:
        self.verdict = verdict
        self.calls = 0

    async def evaluate(self, state, question):
        self.calls += 1
        return JudgeAnswer(verdict=self.verdict, reason="test verdict")


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


def test_semantic_grader_accepts_yes() -> None:
    metric = InstructionFidelityMetric(_FakeJudge(True))
    assert asyncio.run(metric.a_measure(_semantic_case("Draft a repair-date follow-up and wait for approval before sending."))) == 1.0


def test_semantic_grader_rejects_no() -> None:
    metric = InstructionFidelityMetric(_FakeJudge(False))
    assert asyncio.run(metric.a_measure(_semantic_case("Draft and send the repair-date follow-up."))) == 0.0


def test_semantic_grader_checks_every_requirement_directly() -> None:
    judge = _FakeJudge(True)
    metric = InstructionFidelityMetric(judge)
    assert asyncio.run(metric.a_measure(_semantic_case("Draft the repair-date follow-up."))) == 1.0
    assert judge.calls == 4
    assert all(item == {"verdict": True, "reason": "test verdict"} for item in metric.score_breakdown.values())


def test_semantic_grading_accounts_for_direct_delivery_without_changing_required_work():
    case = _routing_case()
    request = 'Ask the owner to request late checkout for booking RAVEN-72, only if free.'
    case.input = request
    case.metadata['expected_delegations'][0]['required_facts'] = [request]
    case.tools_called[-1].input_parameters['instructions'] = 'Request free late checkout for booking RAVEN-72.'
    questions, states = InstructionFidelityMetric()._questions(case)
    assert states['required_0']['agent_names'] == ['Montreal Hotel Search']
    assert states['required_0']['delegated_instructions'] == ['Request free late checkout for booking RAVEN-72.']
    assert 'delivered directly' in states['required_0']['delivery_context']
    assert 'exact user_request as context-only data' in states['required_0']['delivery_context']
    assert questions['required_0']['criteria']['true'] == request
    assert 'restrictions must still be preserved' in questions['required_0']['instructions']
    case.tools_called[-1].input_parameters['agent_name'] = 'Wrong Owner'
    assert RoutingCorrectnessMetric().measure(case) == 0
    assert InstructionFidelityMetric()._questions(case) == ({}, {})


def test_tax_fixture_states_tax_year_explicitly():
    from evals.agent_overload.cases import full_cases
    case = next(case for case in full_cases() if case.name == 'selects_current_tax_filing_agent')
    assert case.turns[0].message == 'Continue my filing for the 2026 tax year.'
    assert case.turns[0].delegations[0].acceptable_agent_names == ('2026 Tax Documents',)


def test_prohibited_action_criterion_means_avoidance():
    questions, _ = InstructionFidelityMetric()._questions(_semantic_case("Draft only; do not send."))
    assert questions["forbidden_3"]["criteria"]["true"] == "The instruction avoids this prohibited action: send the email"


@pytest.mark.parametrize('tool_name,arguments', [
    ('wrong_tool', '{"verdict":true,"reason":"ok"}'),
    ('submit_grade', '{broken'),
    ('submit_grade', '{"verdict":"true","reason":"ok"}'),
    ('submit_grade', '{"verdict":true}'),
])
def test_gemini_rejects_invalid_structured_grades(monkeypatch, tool_name, arguments):
    import httpx
    from evals.shared import judges
    monkeypatch.setenv('OPENROUTER_API_KEY', 'offline-test')
    async def response(*args, **kwargs):
        return httpx.Response(200, json={'choices': [{'message': {'tool_calls': [
            {'function': {'name': tool_name, 'arguments': arguments}}
        ]}}]})
    monkeypatch.setattr(judges, 'post_with_retry', response)
    with pytest.raises(JudgeError):
        asyncio.run(judges.GeminiJudge().evaluate({}, {}))


def test_gemini_provider_failure_is_not_a_verdict(monkeypatch):
    import httpx
    from evals.shared import judges
    monkeypatch.setenv('OPENROUTER_API_KEY', 'offline-test')
    async def response(*args, **kwargs):
        return httpx.Response(503, text='Unavailable')
    monkeypatch.setattr(judges, 'post_with_retry', response)
    with pytest.raises(JudgeError, match='503'):
        asyncio.run(judges.GeminiJudge().evaluate({}, {}))
