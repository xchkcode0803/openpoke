"""Harness checks and live routing evaluation entry point."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from deepeval import assert_test

from .cases import DEVELOPMENT_CASES, add_unrelated_agents, full_cases, smoke_cases, standard_cases
from .harness import run_case
from .metrics import InstructionFidelityMetric, RoutingCorrectnessMetric


def _tool_call(identifier: str, name: str, arguments: dict) -> dict:
    return {"id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


async def _scripted_completion(*args, **kwargs):
    messages = kwargs["messages"]
    tool_messages = [message for message in messages if message.get("role") == "tool"]
    if not tool_messages:
        return {"choices": [{"message": {"content": "", "tool_calls": [_tool_call("ack", "send_message_to_user", {"message": "I will look into that."})]}}]}
    if len(tool_messages) == 1:
        return {"choices": [{"message": {"content": "", "tool_calls": [_tool_call("route", "send_message_to_agent", {"agent_name": "Montreal Hotel Search", "instructions": "Find more Montreal hotels."})]}}]}
    return {"choices": [{"message": {"content": "I will update you when I have more options."}}]}


def test_harness_runs_real_reuse_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import server.agents.interaction_agent.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "request_chat_completion", _scripted_completion)
    case = next(item for item in DEVELOPMENT_CASES if item.name == "reuses_existing_hotel_search_agent")
    results = asyncio.run(run_case(case))
    assert len(results) == 1
    metric = RoutingCorrectnessMetric()
    assert metric.measure(results[0]) == 1.0
    assert_test(results[0], metrics=[RoutingCorrectnessMetric()], run_async=False)
    assert any(call.name == "send_message_to_agent" for call in results[0].tools_called)


def test_generated_roster_is_reproducible() -> None:
    case = next(item for item in DEVELOPMENT_CASES if item.name == "reuses_existing_hotel_search_agent")
    first = add_unrelated_agents(case, 20, 7)
    second = add_unrelated_agents(case, 20, 7)
    assert first.initial_agents == second.initial_agents
    assert "Montreal Hotel Search" in first.initial_agents


def test_harness_uses_evaluation_data_directory() -> None:
    from .harness import _EVAL_DATA_DIR, _reset_services

    roster, conversation, working_memory, execution_logs = _reset_services(_EVAL_DATA_DIR / "isolation-check")
    assert str(roster._roster_path).startswith(str(_EVAL_DATA_DIR))
    assert str(conversation._path).startswith(str(_EVAL_DATA_DIR))
    assert str(working_memory._path).startswith(str(_EVAL_DATA_DIR))
    assert str(execution_logs._base_dir).startswith(str(_EVAL_DATA_DIR))


def test_missing_created_agent_dependency_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    import server.agents.interaction_agent.runtime as runtime_module

    async def no_delegation(*args, **kwargs):
        return {"choices": [{"message": {"content": "I cannot start that task yet."}}]}

    monkeypatch.setattr(runtime_module, "request_chat_completion", no_delegation)
    case = next(
        item
        for item in DEVELOPMENT_CASES
        if item.name == "reuses_agent_created_earlier_in_conversation"
    )
    results = asyncio.run(run_case(case))
    assert len(results) == 2
    assert results[1].metadata["expected_delegations"][0]["missing_dependency"] == "maya_dinner"
    metric = RoutingCorrectnessMetric()
    assert metric.measure(results[1]) == 0.0
    assert "required prior agent was not created" in metric.reason


def _evaluate_live_case(case) -> None:
    results = asyncio.run(run_case(case))
    for result in results:
        metrics = [RoutingCorrectnessMetric()]
        if result.metadata.get("expected_delegations") or result.metadata.get("response_requirements"):
            metrics.append(InstructionFidelityMetric())
        assert_test(result, metrics=metrics, run_async=False)


@pytest.mark.live
@pytest.mark.smoke
@pytest.mark.parametrize("case", smoke_cases(), ids=lambda item: item.name)
def test_live_smoke_routing(case) -> None:
    if not os.getenv("RUN_LIVE_EVALS"):
        pytest.skip("set RUN_LIVE_EVALS=1 to call the interaction model")
    _evaluate_live_case(case)


@pytest.mark.live
@pytest.mark.standard
@pytest.mark.parametrize("case", standard_cases(), ids=lambda item: item.name)
def test_live_standard_routing(case) -> None:
    if not os.getenv("RUN_LIVE_EVALS"):
        pytest.skip("set RUN_LIVE_EVALS=1 to call the interaction model")
    _evaluate_live_case(case)


@pytest.mark.live
@pytest.mark.full
@pytest.mark.parametrize("case", full_cases(), ids=lambda item: item.name)
def test_live_full_routing(case) -> None:
    if not os.getenv("RUN_LIVE_EVALS"):
        pytest.skip("set RUN_LIVE_EVALS=1 to call the interaction model")
    _evaluate_live_case(case)
