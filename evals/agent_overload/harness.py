"""Run and grade routing cases with isolated state and stub workers."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from deepeval.test_case import LLMTestCase, ToolCall
from deepeval.tracing import observe, trace, update_current_span, update_current_trace

from .cases import ExpectedDelegation, RoutingCase
from .provider import MODEL, context_limits, failure_kind


@dataclass
class _StubExecutionResult:
    success: bool = True
    response: str = "Evaluation worker stub completed."
    error: str | None = None


class _StubBatchManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def execute_agent(self, agent_name: str, instructions: str) -> _StubExecutionResult:
        self.calls.append((agent_name, instructions))
        return _StubExecutionResult()


def _usage(response: dict[str, Any]) -> tuple[int | None, int | None, float | None]:
    usage = response.get("usage") or {}
    input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
    output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
    cost = usage.get("cost") or response.get("cost")
    return (
        int(input_tokens) if isinstance(input_tokens, (int, float)) else None,
        int(output_tokens) if isinstance(output_tokens, (int, float)) else None,
        float(cost) if isinstance(cost, (int, float)) else None,
    )


class _TracingInteractionRuntime:
    """Record model and tool boundaries around an unchanged runtime instance."""

    def __init__(self, runtime_type: type[Any]) -> None:
        self._runtime = runtime_type()
        self.tool_calls: list[ToolCall] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = 0.0
        self.has_cost = False
        self.model_latency = 0.0
        self.prompt_estimates = []
        self.model_calls = []
        original_make_call = self._runtime._make_llm_call
        original_execute_tool = self._runtime._execute_tool

        @observe(type="llm")
        async def recorded_make_call(system_prompt: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
            if self._runtime.model in context_limits:
                prompt = json.dumps({"system": system_prompt, "messages": messages, "tools": self._runtime.tool_schemas}, ensure_ascii=False)
                estimate = len(prompt.encode("utf-8")) // 3 + 1
                limit = context_limits[self._runtime.model]
                self.prompt_estimates.append({"estimated_input_tokens": estimate, "context_limit": limit, "output_reserve": 8192})
                if estimate + 8192 > limit:
                    raise RuntimeError(f"capacity limit: estimated {estimate} input tokens plus 8192 reserve exceeds {limit}")
            started = time.perf_counter()
            request = {"system": system_prompt, "messages": json.loads(json.dumps(messages)),
                       "tools": json.loads(json.dumps(self._runtime.tool_schemas))}
            try:
                response = await original_make_call(system_prompt, messages)
            except Exception as exc:
                elapsed = time.perf_counter() - started
                self.model_latency += elapsed
                self.model_calls.append({**request, "response": {}, "error": str(exc), "elapsed_seconds": elapsed})
                raise
            elapsed = time.perf_counter() - started
            input_tokens, output_tokens, cost = _usage(response)
            self.input_tokens += input_tokens or 0
            self.output_tokens += output_tokens or 0
            if cost is not None:
                self.cost += cost
                self.has_cost = True
            self.model_latency += elapsed
            self.model_calls.append({**request, "response": response, "elapsed_seconds": elapsed})
            update_current_span(
                input=json.dumps({"system": system_prompt, "messages": messages, "tools": self._runtime.tool_schemas}, default=str),
                output=json.dumps(response, default=str),
                name="interaction_model_call",
            )
            return response

        @observe(type="tool")
        def recorded_execute_tool(tool_call: Any) -> Any:
            result = original_execute_tool(tool_call)
            arguments = {
                key: value
                for key, value in tool_call.arguments.items()
                if key != "__invalid_arguments__"
            }
            output = {
                "success": result.success,
                "payload": result.payload,
                "user_message": result.user_message,
            }
            captured = ToolCall(
                name=tool_call.name,
                description="OpenPoke interaction tool",
                input_parameters=arguments,
                output=output,
            )
            self.tool_calls.append(captured)
            update_current_span(
                input=json.dumps(arguments, default=str),
                output=json.dumps(output, default=str),
                name=tool_call.name,
            )
            return result

        self._runtime._make_llm_call = recorded_make_call
        self._runtime._execute_tool = recorded_execute_tool

    async def execute(self, message: str) -> Any:
        return await self._runtime.execute(message)

    async def handle_agent_message(self, message: str) -> Any:
        return await self._runtime.handle_agent_message(message)


def _expected_metadata(
    expected: ExpectedDelegation,
    created_agents: dict[str, str],
) -> dict[str, Any]:
    names = list(expected.acceptable_agent_names)
    missing_dependency = None
    if expected.agent_from_task:
        created_name = created_agents.get(expected.agent_from_task)
        if created_name:
            names.append(created_name)
        else:
            missing_dependency = expected.agent_from_task
    return {
        "task_key": expected.task_key,
        "route": expected.route,
        "acceptable_agent_names": names,
        "required_facts": list(expected.required_facts),
        "forbidden_facts": list(expected.forbidden_facts),
        "min_calls": expected.min_calls,
        "max_calls": expected.max_calls,
        "missing_dependency": missing_dependency,
    }


def _reset_services(root: Path) -> tuple[Any, Any, Any, Any]:
    from server.services.conversation.log import ConversationLog
    from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
    from server.services.execution.log_store import ExecutionAgentLogStore
    from server.services.execution.roster import AgentRoster

    working_memory = WorkingMemoryLog(root / "conversation" / "working_memory.log")
    conversation = ConversationLog(root / "conversation" / "conversation.log")
    conversation._working_memory_log = working_memory
    conversation._notify_summarization = lambda: None
    execution_logs = ExecutionAgentLogStore(root / "execution_agents")
    execution_logs.clear_all()
    return (
        AgentRoster(root / "execution_agents" / "roster.json"),
        conversation,
        working_memory,
        execution_logs,
    )


def _seed_case(case: RoutingCase, roster: Any, conversation: Any, working_memory: Any) -> None:
    roster.clear()
    # Avoid 10,000 full-file rewrites while constructing an isolated fixture.
    roster._agents = list(case.initial_agents)
    roster.save()
    conversation.clear()
    if case.initial_summary:
        state = working_memory.load_summary_state()
        state.summary_text = case.initial_summary
        working_memory.write_summary_state(state)
    for tag, content in case.initial_conversation:
        if tag == "user_message":
            conversation.record_user_message(content)
        elif tag == "poke_reply":
            conversation.record_reply(content)
        elif tag == "agent_message":
            conversation.record_agent_message(content)
        elif tag == "wait":
            conversation.record_wait(content)
        else:
            raise ValueError(f"Unsupported conversation tag: {tag}")


async def run_case(case: RoutingCase, history: dict[str, tuple[tuple[str, str], ...]] | None = None) -> list[LLMTestCase]:
    """Execute one case and return one DeepEval test case per routing turn."""
    from unittest.mock import patch
    with tempfile.TemporaryDirectory(prefix="openpoke-agent-overload-") as directory:
        with patch.dict(os.environ, {"OPENPOKE_DATA_DIR": directory}):
            return await _run_isolated_case(case, Path(directory), history)


async def _run_isolated_case(case: RoutingCase, root: Path, history=None) -> list[LLMTestCase]:

    from unittest.mock import patch

    import server.agents.interaction_agent.agent as agent_module
    import server.agents.interaction_agent.runtime as runtime_module
    import server.agents.interaction_agent.tools as tools_module

    roster, conversation, working_memory, execution_logs = _reset_services(root)
    _seed_case(case, roster, conversation, working_memory)
    for name, entries in (history or {}).items():
        if name not in case.initial_agents:
            raise ValueError(f"History owner is not in the roster: {name}")
        for tag, text in entries:
            if tag == "agent_request":
                execution_logs.record_request(name, text)
            elif tag == "agent_response":
                execution_logs.record_agent_response(name, text)
            else:
                raise ValueError(f"Unsupported history tag: {tag}")
    settings = SimpleNamespace(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        interaction_agent_model=MODEL,
        summarization_enabled=bool(case.initial_summary),
    )
    batch_manager = _StubBatchManager()
    created_agents: dict[str, str] = {}
    completed: list[LLMTestCase] = []

    patches = (
        patch.object(agent_module, "get_agent_roster", return_value=roster),
        patch.object(agent_module, "get_execution_agent_logs", return_value=execution_logs),
        patch.object(tools_module, "get_agent_roster", return_value=roster),
        patch.object(tools_module, "get_execution_agent_logs", return_value=execution_logs),
        patch.object(tools_module, "get_conversation_log", return_value=conversation),
        patch.object(tools_module, "_EXECUTION_BATCH_MANAGER", batch_manager),
        patch.object(runtime_module, "get_conversation_log", return_value=conversation),
        patch.object(runtime_module, "get_working_memory_log", return_value=working_memory),
        patch.object(runtime_module, "get_settings", return_value=settings),
    )

    with trace(name=case.name, tags=sorted(case.tags), metadata={"case": case.name}):
        with ExitStack() as stack:
            for service_patch in patches:
                stack.enter_context(service_patch)
            runtime = _TracingInteractionRuntime(runtime_module.InteractionAgentRuntime)
            for index, turn in enumerate(case.turns):
                roster_before = roster.get_agents()
                runtime.tool_calls = []
                runtime.input_tokens = 0
                runtime.output_tokens = 0
                runtime.cost = 0.0
                runtime.has_cost = False
                runtime.model_latency = 0.0
                started = time.perf_counter()
                runtime.prompt_estimates = []
                runtime.model_calls = []
                result = await (
                    runtime.execute(turn.message)
                    if turn.source == "user"
                    else runtime.handle_agent_message(turn.message)
                )
                await asyncio.sleep(0)
                elapsed = time.perf_counter() - started
                expected = [_expected_metadata(item, created_agents) for item in turn.delegations]
                created_now = [
                    call.input_parameters.get("agent_name")
                    for call in runtime.tool_calls
                    if call.name == "send_message_to_agent"
                    and isinstance(call.output, dict)
                    and bool((call.output.get("payload") or {}).get("new_agent_created"))
                ]
                exact_creates = [
                    item
                    for item in turn.delegations
                    if item.route == "create" and item.min_calls == 1 and item.max_calls == 1
                ]
                flexible_create = any(
                    item.route == "create" and item.max_calls != 1 for item in turn.delegations
                )
                if not flexible_create and len(created_now) == len(exact_creates):
                    for expected_item, actual_name in zip(exact_creates, created_now):
                        if isinstance(actual_name, str):
                            created_agents[expected_item.task_key] = actual_name
                metadata = {
                    "case_name": case.name,
                    "turn_index": index,
                    "turn_source": turn.source,
                    "expected_action": turn.expected_action,
                    "expected_delegations": expected,
                    "response_requirements": list(turn.response_requirements),
                    "roster_before": roster_before if not any(tag.startswith("routing_") for tag in case.tags) else None,
                    "roster_count": len(roster_before),
                    "actual_model": settings.interaction_agent_model,
                    "worker_dispatches": batch_manager.calls[:],
                    "runtime_success": result.success,
                    "runtime_error": result.error,
                    "failure_kind": failure_kind(result.error),
                    "prompt_estimates": runtime.prompt_estimates[:],
                    "model_calls": runtime.model_calls[:],
                    "model_call_count": len(runtime.model_calls),
                    "discovery_call_count": runtime._runtime.discovery_calls,
                    "discovery_closed_reason": runtime._runtime.discovery_closed_reason,
                    "provider_timing": [call["response"].get("_eval_timing", {}) for call in runtime.model_calls],
                    "model_call_seconds_including_pacing": runtime.model_latency,
                    "conversation_context": case.initial_conversation,
                }
                test_case = LLMTestCase(
                    name=f"{case.name}[{index}]",
                    input=turn.message,
                    actual_output=result.response,
                    tools_called=list(runtime.tool_calls),
                    token_cost=runtime.cost if runtime.has_cost else None,
                    input_token_count=runtime.input_tokens or None,
                    output_token_count=runtime.output_tokens or None,
                    completion_time=elapsed,
                    metadata=metadata,
                    tags=sorted(case.tags),
                )
                completed.append(test_case)
        update_current_trace(
            input=case.description,
            output=json.dumps([item.actual_output for item in completed]),
            metadata={"case": case.name, "turn_count": len(completed)},
        )
    return completed


def evaluate_live_case(case, history=None) -> None:
    """Run and grade a live case, preserving every turn even when grading fails."""
    from unittest.mock import patch
    from deepeval import assert_test
    from .metrics import InstructionFidelityMetric, RoutingCorrectnessMetric
    from .provider import (
        MODEL, context_limits, interaction_completion, save_result, verify_context_limit,
    )
    if "stress" in case.tags and MODEL not in context_limits:
        asyncio.run(verify_context_limit(MODEL))
    with patch("server.agents.interaction_agent.runtime.request_chat_completion", interaction_completion):
        results = asyncio.run(run_case(case, history))
    failures = []
    for result in results:
        if result.metadata.get("failure_kind") in {"provider", "capacity", "harness", "budget"}:
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


__all__ = ["run_case", "evaluate_live_case"]
