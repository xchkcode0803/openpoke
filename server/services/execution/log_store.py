"""Execution agent log management with structured XML-style tags."""

from __future__ import annotations

import re
import fcntl
import os
from .catalog import Catalog
import threading
from html import escape, unescape
from pathlib import Path
from typing import Dict, Iterator, List, Tuple, Optional

from ...logging_config import logger
from ...data_paths import resolve_data_dir
from ...utils.timezones import now_in_user_timezone




def _encode_payload(payload: str) -> str:
    """Encode payload for storage."""
    normalized = payload.replace("\r\n", "\n").replace("\r", "\n")
    collapsed = normalized.replace("\n", "\\n")
    return escape(collapsed, quote=False)


def _decode_payload(payload: str) -> str:
    """Decode payload from storage."""
    return unescape(payload).replace("\\n", "\n")


_ATTR_PATTERN = re.compile(r"(\w+)\s*=\s*\"([^\"]*)\"")


class ExecutionAgentLogStore:
    """Append-only journal for execution agents with XML-style tags."""

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._ensure_directory()
        self.catalog = Catalog(base_dir)
        self.catalog.bootstrap_logs()
        self.sync_pending()

    def _ensure_directory(self) -> None:
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning(f"Failed to create directory: {exc}")

    def _lock_for(self, agent_name: str) -> threading.Lock:
        """Get or create a lock for an agent."""
        with self._global_lock:
            if agent_name not in self._locks:
                self._locks[agent_name] = threading.RLock()
            return self._locks[agent_name]

    def _log_path(self, agent_name: str) -> Path:
        journal = self.catalog.register_journal(agent_name)
        if journal['ambiguous']:
            raise ValueError(f'Ambiguous legacy history for {agent_name}; reconcile the shared legacy file explicitly')
        return self._base_dir / journal['path']

    def _sync_handle(self, agent_name, handle):
        stat = os.fstat(handle.fileno())
        identity = f'{stat.st_dev}:{stat.st_ino}'
        with self.catalog.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM journals WHERE name=?', (agent_name,)).fetchone()
            offset = row['offset']
            if row['identity'] == identity and stat.st_size == offset and not row['dirty']:
                return
            refresh = row['identity'] != identity or stat.st_size < offset
            if refresh:
                db.execute('DELETE FROM entries WHERE name=?', (agent_name,))
                offset = 0
            handle.seek(offset)
            for line in handle:
                position = offset
                if not line.endswith(b'\n'):
                    raise ValueError(f'Incomplete history record for {agent_name}; preserve and repair the journal before retrying')
                offset += len(line)
                entry = self._parse_line(line.decode('utf-8'))
                if entry is None:
                    raise ValueError(f'Malformed history record for {agent_name} at byte {position}')
                tag, timestamp, text = entry
                refresh = refresh or tag == 'agent_request'
                if tag in {'agent_request', 'agent_response'}:
                    db.execute('INSERT OR IGNORE INTO entries(name,position,kind,timestamp,text) VALUES(?,?,?,?,?)',
                               (agent_name, position, tag, timestamp, text))
            if refresh:
                self.catalog.refresh_profile(db, agent_name)
            db.execute('UPDATE journals SET offset=?,identity=?,dirty=0 WHERE name=?', (offset, identity, agent_name))

    def sync_agent(self, agent_name):
        with self._lock_for(agent_name):
            path = self._log_path(agent_name)
            if not path.exists():
                with self.catalog.connect() as db:
                    db.execute('DELETE FROM entries WHERE name=?', (agent_name,))
                    db.execute('UPDATE journals SET offset=0,identity=NULL,dirty=0 WHERE name=?', (agent_name,))
                    self.catalog.refresh_profile(db, agent_name)
                return
            with path.open('r+b') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                self._sync_handle(agent_name, handle)

    def sync_pending(self):
        with self.catalog.connect() as db:
            names = [row[0] for row in db.execute('SELECT name FROM journals WHERE dirty=1')]
        for name in names:
            self.sync_agent(name)

    def rebuild_index(self):
        """Explicit repair after external edits; no per-request directory scan."""
        with self.catalog.connect() as db:
            db.execute('DELETE FROM entries')
            db.execute('UPDATE journals SET offset=0,identity=NULL,dirty=1 WHERE ambiguous=0')
            db.execute('UPDATE agents SET initial_assignment=NULL,latest_assignment=NULL,initial_truncated=0,latest_truncated=0')
        self.sync_pending()

    def _append(self, agent_name: str, tag: str, payload: str) -> None:
        encoded = _encode_payload(str(payload))
        timestamp = now_in_user_timezone('%Y-%m-%d %H:%M:%S')
        entry = f'<{tag} timestamp="{timestamp}">{encoded}</{tag}>\n'.encode('utf-8')
        with self._lock_for(agent_name):
            with self._log_path(agent_name).open('a+b') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                # Recover any completed append whose index transaction was interrupted.
                self._sync_handle(agent_name, handle)
                with self.catalog.connect() as db:
                    db.execute('UPDATE journals SET dirty=1 WHERE name=?', (agent_name,))
                handle.seek(0, os.SEEK_END)
                handle.write(entry)
                handle.flush()
                os.fsync(handle.fileno())
                self._sync_handle(agent_name, handle)

    def _parse_line(self, line: str) -> Optional[Tuple[str, str, str]]:
        """Parse a single log line."""
        stripped = line.strip()
        if not (stripped.startswith("<") and "</" in stripped):
            return None

        open_end = stripped.find(">")
        close_start = stripped.rfind("</")
        close_end = stripped.rfind(">")

        if open_end == -1 or close_start == -1 or close_end == -1:
            return None

        open_tag_content = stripped[1:open_end]
        if " " in open_tag_content:
            tag, attr_string = open_tag_content.split(" ", 1)
        else:
            tag, attr_string = open_tag_content, ""

        closing_tag = stripped[close_start + 2 : close_end]
        if closing_tag != tag:
            return None

        attributes: Dict[str, str] = {
            match.group(1): match.group(2) for match in _ATTR_PATTERN.finditer(attr_string)
        }
        timestamp = attributes.get("timestamp", "")
        payload = _decode_payload(stripped[open_end + 1 : close_start])
        return tag, timestamp, payload

    def record_request(self, agent_name: str, instructions: str) -> None:
        """Record an incoming request from the interaction agent."""
        self._append(agent_name, "agent_request", instructions)

    def record_action(self, agent_name: str, description: str) -> None:
        """Record an agent action (tool call)."""
        self._append(agent_name, "agent_action", description)

    def record_tool_response(self, agent_name: str, tool_name: str, response: str) -> None:
        """Record the response from a tool."""
        self._append(agent_name, "tool_response", f"{tool_name}: {response}")

    def record_agent_response(self, agent_name: str, response: str) -> None:
        """Record the agent's final response."""
        self._append(agent_name, "agent_response", response)

    def iter_entries(self, agent_name: str) -> Iterator[Tuple[str, str, str]]:
        """Iterate over all log entries for an agent."""
        path = self._log_path(agent_name)
        with self._lock_for(agent_name):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                lines = []
            except Exception as exc:
                logger.error(f"Failed to read log: {exc}")
                lines = []

        for line in lines:
            parsed = self._parse_line(line)
            if parsed is not None:
                yield parsed

    def load_transcript(self, agent_name: str) -> str:
        """Load the full transcript for inclusion in system prompt."""
        parts: List[str] = []
        for tag, timestamp, payload in self.iter_entries(agent_name):
            escaped = escape(payload, quote=False)
            if timestamp:
                parts.append(f"<{tag} timestamp=\"{timestamp}\">{escaped}</{tag}>")
            else:
                parts.append(f"<{tag}>{escaped}</{tag}>")
        return "\n".join(parts)

    def load_recent(self, agent_name: str, limit: int = 10) -> list[tuple[str, str, str]]:
        """Load recent log entries."""
        entries = list(self.iter_entries(agent_name))
        return entries[-limit:] if entries else []

    def list_agents(self) -> list[str]:
        with self.catalog.connect() as db:
            return [row[0] for row in db.execute('SELECT DISTINCT name FROM entries ORDER BY name')]

    def clear_all(self) -> None:
        # This explicit destructive operation is intentionally not on the read path.
        for log_file in self._base_dir.glob('*.log'):
            log_file.unlink()
        with self.catalog.connect() as db:
            db.execute('DELETE FROM entries')
            db.execute('DELETE FROM journals')
            db.execute('UPDATE agents SET initial_assignment=NULL,latest_assignment=NULL,initial_truncated=0,latest_truncated=0')


_execution_agent_logs = None


def get_execution_agent_logs():
    global _execution_agent_logs
    directory = resolve_data_dir(Path(__file__).resolve().parent.parent.parent / 'data') / 'execution_agents'
    if _execution_agent_logs is None or _execution_agent_logs._base_dir != directory:
        _execution_agent_logs = ExecutionAgentLogStore(directory)
    return _execution_agent_logs


__all__ = ['ExecutionAgentLogStore', 'get_execution_agent_logs']
