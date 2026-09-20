"""Exact-name roster backed by the local SQLite ownership catalog."""
import json
from pathlib import Path
from .catalog import Catalog
from ...data_paths import resolve_data_dir


class AgentRoster:
    def __init__(self, roster_path: Path):
        self._roster_path = roster_path  # Legacy import/export location.
        self.catalog = Catalog(roster_path.parent)

    def load(self):
        """Compatibility health check; membership is read directly from SQLite."""
        self.catalog.count()

    def add_agent(self, agent_name):
        return self.catalog.add(agent_name)

    def contains(self, agent_name):
        return self.catalog.contains(agent_name)

    def count(self):
        return self.catalog.count()

    def get_agents(self):
        """Explicit full export. Routing must use bounded catalog operations."""
        return self.catalog.names()

    def bulk_import(self, names):
        self.catalog.replace(names)

    def export_json(self, destination):
        Path(destination).write_text(json.dumps(self.get_agents(), ensure_ascii=False, indent=2))

    def clear(self):
        with self.catalog.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM agents')
            db.execute('DELETE FROM entries')
            db.execute("UPDATE metadata SET value='0' WHERE key='count'")


_DATA_DIR = resolve_data_dir(Path(__file__).resolve().parent.parent.parent / 'data')
_ROSTER_PATH = _DATA_DIR / 'execution_agents' / 'roster.json'
_agent_roster = None


def get_agent_roster():
    global _agent_roster
    path = resolve_data_dir(Path(__file__).resolve().parent.parent.parent / 'data') / 'execution_agents' / 'roster.json'
    if _agent_roster is None or _agent_roster._roster_path != path:
        _agent_roster = AgentRoster(path)
    return _agent_roster
