"""Harness checks and live routing evaluation entry point."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from deepeval import assert_test

from .cases import (
    DEVELOPMENT_CASES,
    add_similar_agents,
    full_cases,
    scale_roster_with_unrelated_agents,
    smoke_cases,
    standard_cases,
)
from .harness import run_case
from .metrics import InstructionFidelityMetric, RoutingCorrectnessMetric
from .stress_cases import stress_cases


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
    assert results[0].metadata["worker_dispatches"]
    assert results[0].metadata["model_calls"][0]["system"]


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
    assert digest == "f466df1ae88422eb3a2357d0cc6d913918e56c87128a4725aa31062cacac68fd"
    parameters = suite_parameters()
    assert len({parameter.id for parameter in parameters}) == len(parameters)
    assert sum(any(mark.name == "full" for mark in p.marks) for p in parameters) == 99
    assert sum(any(mark.name == "smoke" for mark in p.marks) for p in parameters) == 12
    assert sum(any(mark.name == "standard" for mark in p.marks) for p in parameters) == 29
    assert sum(any(mark.name == "stress" for mark in p.marks) for p in parameters) == 24


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
    from .harness import _reset_services

    roster, conversation, working_memory, execution_logs = _reset_services(tmp_path)
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


def _evaluate_live_case(case) -> None:
    from unittest.mock import patch
    from .provider import MODEL, context_limits, verify_context_limit, interaction_completion, save_result
    if "stress" in case.tags and MODEL not in context_limits:
        asyncio.run(verify_context_limit(MODEL))
    with patch("server.agents.interaction_agent.runtime.request_chat_completion", interaction_completion):
        results = asyncio.run(run_case(case))
    failures = []
    for result in results:
        if result.metadata.get("failure_kind"):
            save_result("unavailable.jsonl", result.model_dump(mode="json"))
            failures.append(f"{result.name}: unavailable ({result.metadata['failure_kind']})")
            continue
        metrics = [RoutingCorrectnessMetric()]
        if result.metadata.get("expected_delegations") or result.metadata.get("response_requirements"):
            metrics.append(InstructionFidelityMetric())
        try:
            assert_test(result, metrics=metrics, run_async=False)
        except Exception as exc:
            if not isinstance(exc, AssertionError):
                save_result("judge_errors.jsonl", {"case": result.name, "error": str(exc)})
            failures.append(f"{result.name}: {exc}")
        finally:
            save_result("turns.jsonl", {"result": result.model_dump(mode="json"), "metrics": [
                {"name": metric.__name__, "score": getattr(metric, "score", None),
                 "reason": getattr(metric, "reason", None)} for metric in metrics
            ]})
    assert not failures, "\n".join(failures)


def suite_parameters():
    full = {case.name for case in full_cases() + stress_cases()}
    smoke = {case.name for case in smoke_cases()}
    standard = {case.name for case in standard_cases()}
    cases = {case.name: case for case in full_cases() + stress_cases() + smoke_cases() + standard_cases()}
    return [
        pytest.param(case, id=case.name, marks=[
            getattr(pytest.mark, suite) for suite, included in (
                ("full", case.name in full), ("smoke", case.name in smoke),
                ("standard", case.name in standard), ("stress", "stress" in case.tags)
            ) if included
        ])
        for case in cases.values()
    ]


@pytest.mark.live
@pytest.mark.parametrize("case", suite_parameters())
def test_live_routing(case) -> None:
    if not os.getenv("RUN_LIVE_EVALS"):
        pytest.skip("set RUN_LIVE_EVALS=1 to call the interaction model")
    _evaluate_live_case(case)
