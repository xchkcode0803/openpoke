"""Construct isolated stores shared by Gmail and routing evaluations."""
from pathlib import Path
from typing import Any


def create_stores(root: Path) -> tuple[Any, Any, Any, Any]:
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
