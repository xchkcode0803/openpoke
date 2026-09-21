"""Harness checks and live routing evaluation entry point."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from deepeval import assert_test

from evals.agent_overload.cases import (
    DEVELOPMENT_CASES,
    add_similar_agents,
    full_cases,
    scale_roster_with_unrelated_agents,
    smoke_cases,
    standard_cases,
)
from evals.agent_overload.harness import run_case
from evals.agent_overload.metrics import RoutingCorrectnessMetric
from evals.agent_overload.stress_cases import stress_cases


def _tool_call(identifier: str, name: str, arguments: dict) -> dict:
    if name == "send_message_to_agent":
        arguments = {"action": "reuse", **arguments}
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
    assert results[0].metadata["worker_dispatches"]
    assert results[0].metadata["model_calls"][0]["system"]


def test_turn_cost_is_unknown_when_any_model_response_omits_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    import server.agents.interaction_agent.runtime as runtime_module

    calls = 0

    async def completion(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            message = {"content": "", "tool_calls": [_tool_call("ack", "send_message_to_user", {"message": "I will look into that."})]}
            return {"choices": [{"message": message}], "usage": {"prompt_tokens": 10, "completion_tokens": 1, "cost": 0.01}}
        if calls == 2:
            message = {"content": "", "tool_calls": [_tool_call("route", "send_message_to_agent", {"agent_name": "Montreal Hotel Search", "instructions": "Find more Montreal hotels."})]}
            return {"choices": [{"message": message}], "usage": {"prompt_tokens": 10, "completion_tokens": 1}}
        return {"choices": [{"message": {"content": "I will update you when I have more options."}}], "usage": {"prompt_tokens": 10, "completion_tokens": 1, "cost": 0}}

    monkeypatch.setattr(runtime_module, "request_chat_completion", completion)
    case = next(item for item in DEVELOPMENT_CASES if item.name == "reuses_existing_hotel_search_agent")
    result = asyncio.run(run_case(case))[0]
    assert result.token_cost is None
    assert result.input_token_count == 30
    assert result.output_token_count == 3


def test_environment_and_temporary_state_restored(monkeypatch):
    from pathlib import Path
    import server.agents.interaction_agent.runtime as runtime_module
    original = os.environ.get("OPENPOKE_DATA_DIR")
    directories = []

    async def completion(*args, **kwargs):
        directories.append(Path(os.environ["OPENPOKE_DATA_DIR"]))
        return await _scripted_completion(*args, **kwargs)

    monkeypatch.setattr(runtime_module, "request_chat_completion", completion)
    asyncio.run(run_case(DEVELOPMENT_CASES[1]))
    assert os.environ.get("OPENPOKE_DATA_DIR") == original
    assert directories and all(not path.exists() for path in directories)


def test_suite_membership_and_frozen_cases():
    import hashlib
    from dataclasses import asdict

    cases = full_cases() + stress_cases()
    digest = hashlib.sha256(json.dumps([asdict(case) for case in cases], default=lambda value: sorted(value), sort_keys=True).encode()).hexdigest()
    assert digest == "6ea01e5037747ac4ad5841339af4a257048b5bd393d09528fc258d2f217b5747"
    memberships = {
        "full": {case.name for case in full_cases() + stress_cases()},
        "smoke": {case.name for case in smoke_cases()},
        "standard": {case.name for case in standard_cases()},
        "stress": {case.name for case in full_cases() + stress_cases() if "stress" in case.tags},
    }
    assert len(memberships["full"]) == 99
    assert len(memberships["smoke"]) == 12
    assert len(memberships["standard"]) == 29
    assert len(memberships["stress"]) == 24


def test_generated_roster_is_reproducible() -> None:
    case = next(item for item in DEVELOPMENT_CASES if item.name == "reuses_existing_hotel_search_agent")
    first = scale_roster_with_unrelated_agents(case, 20, 7)
    second = scale_roster_with_unrelated_agents(case, 20, 7)
    assert first.initial_agents == second.initial_agents
    assert len(first.initial_agents) == 20
    assert "Montreal Hotel Search" in first.initial_agents
    assert not any("Related Thread" in name for name in first.initial_agents)


def test_similar_density_variant_is_fixed_size_and_realistic() -> None:
    case = next(item for item in DEVELOPMENT_CASES if item.name == "reuses_existing_hotel_search_agent")
    variant = add_similar_agents(case, "Montreal Hotel Search", 25, 17, total_size=100)
    assert len(variant.initial_agents) == 100
    assert "Montreal Hotel Search" in variant.initial_agents
    assert any("Montreal Hotel" in name and name != "Montreal Hotel Search" for name in variant.initial_agents)
    assert "similar_count_25" in variant.tags


def test_harness_uses_evaluation_data_directory(tmp_path) -> None:
    from evals.shared.state import create_stores

    roster, conversation, working_memory, execution_logs = create_stores(tmp_path)
    assert roster._roster_path.is_relative_to(tmp_path)
    assert conversation._path.is_relative_to(tmp_path)
    assert working_memory._path.is_relative_to(tmp_path)
    assert execution_logs._base_dir.is_relative_to(tmp_path)


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
