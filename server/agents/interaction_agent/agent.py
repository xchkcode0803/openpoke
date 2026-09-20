"""Interaction agent helpers for prompt construction."""

import json
from pathlib import Path
from typing import Dict, List

from ...services.execution import get_agent_roster, get_execution_agent_logs
from .discovery import select_candidates, ownership_profile

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip()


# Load and return the pre-defined system prompt from markdown file
def build_system_prompt() -> str:
    """Return the static system prompt for the interaction agent."""
    return SYSTEM_PROMPT


# Build structured message with conversation history, candidate roster, and current turn
def prepare_message_with_history(
    latest_text: str,
    transcript: str,
    message_type: str = "user",
) -> List[Dict[str, str]]:
    """Compose a message with history, candidate roster, and the latest turn."""
    sections: List[str] = []

    sections.append(_render_conversation_history(transcript))
    sections.append(_render_candidates(latest_text, transcript))
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    return f"<conversation_history>\n{history}\n</conversation_history>"


def _render_candidates(latest_text: str, transcript: str) -> str:
    roster = get_agent_roster()
    roster.load()
    names = roster.get_agents()
    candidates = select_candidates(names, latest_text, transcript)
    complete = "true" if len(candidates) == len(names) else "false"
    logs = get_execution_agent_logs()
    encoded = json.dumps([ownership_profile(name, logs) for name in candidates], ensure_ascii=False)
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return (f'<active_agents total="{len(names)}" complete="{complete}">\n'
            f'{encoded}\n</active_agents>')


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"
