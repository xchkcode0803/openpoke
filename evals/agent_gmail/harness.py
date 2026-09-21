"""Run actual agent orchestration against an isolated Emulate mailbox."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from dataclasses import asdict
import importlib
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from .adapter import GmailAdapter
from .config import EvalConfig
from .emulator import Emulator
from .mailbox import USER
from .tracing import Recorder
from .types import Case


class ScenarioTasks:
    """Track workers and callbacks spawned while the scenario owns the loop."""

    def __init__(self, recorder):
        self.recorder = recorder
        self.tasks = set()
        self.original_create_task = asyncio.get_running_loop().create_task

    def create_task(self, coro, *args, **kwargs):
        task = self.original_create_task(coro, *args, **kwargs)
        self.tasks.add(task)
        return task

    def pending(self):
        return [task for task in self.tasks
                if not task.done() and task is not asyncio.current_task()]

    async def drain(self):
        while True:
            pending = self.pending()
            if not pending:
                await asyncio.sleep(0)
                pending = self.pending()
                if not pending:
                    break
            await asyncio.gather(*pending, return_exceptions=True)
        for task in self.tasks:
            if task.done() and not task.cancelled() and task.exception():
                self.recorder.emit("task_error", error=str(task.exception()))

    async def cancel(self):
        for task in self.tasks:
            if not task.done():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)


async def run_case(case: Case, config: EvalConfig, completion) -> dict:
    recorder = Recorder()
    record = {"case": asdict(case), "turns": [], "events": recorder.events}
    with tempfile.TemporaryDirectory(prefix="gmail-agent-") as directory:
        with patch.dict(os.environ, {"OPENPOKE_DATA_DIR": directory}):
            with Emulator(case.mail) as emulator:
                await _run(case, config, completion, Path(directory), emulator, recorder, record)
    return record


async def _run(case, config, completion, root, emulator, recorder, record):
    from evals.shared.state import create_stores
    from server.config import get_settings
    from server.agents.execution_agent.batch_manager import ExecutionBatchManager
    from server.services.triggers.service import TriggerService
    from server.services.triggers.store import TriggerStore

    ia = importlib.import_module("server.agents.interaction_agent.agent")
    ir = importlib.import_module("server.agents.interaction_agent.runtime")
    it = importlib.import_module("server.agents.interaction_agent.tools")
    ea = importlib.import_module("server.agents.execution_agent.agent")
    er = importlib.import_module("server.agents.execution_agent.runtime")
    gt = importlib.import_module("server.agents.execution_agent.tools.gmail")
    st = importlib.import_module("server.agents.execution_agent.tasks.search_email.tool")
    tt = importlib.import_module("server.agents.execution_agent.tools.triggers")
    gc = importlib.import_module("server.services.gmail.client")

    roster, conversation, memory, logs = create_stores(root)
    settings = get_settings().model_copy(update={
        "openrouter_api_key": "eval-key-from-provider",
        "interaction_agent_model": config.interaction_model,
        "execution_agent_model": config.execution_model,
        "execution_agent_search_model": config.search_model,
        "conversation_summary_threshold": 0,
    })
    manager = ExecutionBatchManager(timeout_seconds=config.worker_timeout)
    adapter = GmailAdapter(emulator, case.faults, recorder.emit)
    tasks = ScenarioTasks(recorder)
    loop = asyncio.get_running_loop()

    def model_call(role):
        async def call(**kwargs):
            safe = {k: v for k, v in kwargs.items() if k != "api_key"}
            with recorder.span("model", role=role, request=safe) as event:
                response = await completion(role=role, **safe)
                event["response"] = response
                return response
        return call

    original_handle = it.handle_tool_call
    def interaction_tool(name, arguments):
        with recorder.span("interaction_tool", name=name, arguments=arguments) as event:
            result = original_handle(name, arguments)
            event["result"] = asdict(result)
            return result

    original_execute_tool = er.ExecutionAgentRuntime._execute_tool
    async def execution_tool(self, name, arguments):
        with recorder.span("execution_tool", agent=self.agent.name, name=name, arguments=arguments) as event:
            result = await original_execute_tool(self, name, arguments)
            event["result"] = result
            return result

    original_callback = ir.InteractionAgentRuntime.handle_agent_message
    async def callback(self, message):
        with recorder.span("callback", message=message) as event:
            result = await original_callback(self, message)
            event["result"] = asdict(result)
            return result

    original_reply = conversation.record_reply
    def reply(content):
        recorder.emit("user_output", content=content)
        return original_reply(content)

    def no_real_composio(*args, **kwargs):
        raise RuntimeError("Production Composio access blocked in Gmail eval")

    patches = [
        patch.object(ia, "get_agent_roster", return_value=roster),
        patch.object(ia, "get_execution_agent_logs", return_value=logs),
        patch.object(it, "get_agent_roster", return_value=roster),
        patch.object(it, "get_execution_agent_logs", return_value=logs),
        patch.object(ea, "get_execution_agent_logs", return_value=logs),
        patch.object(it, "get_conversation_log", return_value=conversation),
        patch.object(ir, "get_conversation_log", return_value=conversation),
        patch.object(ir, "get_working_memory_log", return_value=memory),
        patch.object(it, "_EXECUTION_BATCH_MANAGER", manager),
        patch.object(tt, "_TRIGGER_SERVICE", TriggerService(TriggerStore(root / "triggers.db"))),
        patch.object(gc, "_get_composio_client", no_real_composio),
        patch.object(ir, "handle_tool_call", interaction_tool),
        patch.object(er.ExecutionAgentRuntime, "_execute_tool", execution_tool),
        patch.object(ir.InteractionAgentRuntime, "handle_agent_message", callback),
        patch.object(conversation, "record_reply", reply),
        patch.object(loop, "create_task", tasks.create_task),
    ]
    for module in (ir, er, st):
        patches.append(patch.object(module, "get_settings", return_value=settings))
    for module, role in ((ir, "interaction"), (er, "execution"), (st, "search")):
        patches.append(patch.object(module, "request_chat_completion", model_call(role)))
    for module in (gt, st):
        patches.extend([patch.object(module, "execute_gmail_tool", adapter),
                        patch.object(module, "get_active_gmail_user_id", return_value=USER if case.connected else None)])
    for module in (gt, st, tt):
        patches.append(patch.object(module, "get_execution_agent_logs", return_value=logs))

    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        try:
            await _run_turns(case, config, ir, conversation, emulator, recorder, record, tasks)
        finally:
            await tasks.cancel()
            await manager.shutdown()
    record["unsupported"] = adapter.unsupported
    record["final"] = emulator.snapshot()


async def _run_turns(case, config, runtime, conversation, emulator, recorder, record, tasks):
    """Advance scripted users only after scenario-owned callbacks finish."""
    for index, turn in enumerate(case.turns):
        recorder.turn = index
        before = emulator.snapshot()
        current = {"index": index, "before": before}
        record["turns"].append(current)
        # Approval may only follow an actual visible preview, never harness-invented state.
        previews = [e for e in recorder.events if e["kind"] == "interaction_tool" and e.get("name") == "send_draft"
                    and e.get("result", {}).get("success")]
        if turn.requires_preview and not previews:
            current.update(error="Missing prior preview", failure_kind="dependency", after=before)
            continue
        with recorder.span("user_turn", message=turn.message):
            try:
                async with asyncio.timeout(config.turn_timeout):
                    result = await runtime.InteractionAgentRuntime().execute(turn.message)
                    current["result"] = asdict(result)
                    await tasks.drain()
            except TimeoutError:
                current.update(error="Turn deadline exceeded", failure_kind="agent_timeout")
            except Exception as exc:
                current.update(error=str(exc), failure_kind="harness")
        current["after"] = emulator.snapshot()
        current["conversation"] = conversation.load_transcript()
        if current.get("error") and current.get("failure_kind") != "dependency":
            break
