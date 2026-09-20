import asyncio
import json
from types import SimpleNamespace

import pytest

from .resume import resume_gmail


def test_resume_preserves_completed_agents_and_original_cap(tmp_path, monkeypatch):
    from evals.agent_gmail import run, reporting
    from evals.agent_gmail.cases import select_cases
    first = select_cases('full')[0].name
    source = tmp_path / 'gmail'
    source.mkdir()
    record = {'case': {'name': first}, 'provider_calls': [], 'judge_error': None}
    original = source / f'case-{first}-0.json'
    original.write_text(json.dumps(record))
    before = original.read_bytes()
    (source / 'summary.json').write_text(json.dumps({'known_agent_cost': 1, 'judge_known_cost': .1}))
    (tmp_path / 'comparison.json').write_text(json.dumps({'budget_usd': 10}))
    monkeypatch.setattr(reporting, 'summarize', lambda records: {'known_agent_cost': 1, 'judge_known_cost': .1})
    scheduled = []
    async def execute(args):
        scheduled.extend(args.case)
        assert args.budget == 8.9
        output = __import__('pathlib').Path(args.output)
        output.mkdir()
        (output / 'manifest.json').write_text(json.dumps({'status': 'complete'}))
        return 1  # genuine candidate failures do not trigger agent retries
    monkeypatch.setattr(run, 'run', execute)
    asyncio.run(resume_gmail(SimpleNamespace(budget=50), tmp_path, 'candidate', None))
    assert len(scheduled) == 39 and first not in scheduled
    assert original.read_bytes() == before


def test_uncertain_agent_charge_prevents_resume(tmp_path):
    source = tmp_path / 'gmail'
    source.mkdir()
    (tmp_path / 'comparison.json').write_text(json.dumps({'budget_usd': 10}))
    (source / 'case-test-0.json').write_text(json.dumps({'case': {'name': 'test'}, 'provider_calls': [{'error': 'read timeout'}]}))
    with pytest.raises(ValueError, match='manual reconciliation'):
        asyncio.run(resume_gmail(SimpleNamespace(budget=10), tmp_path, 'candidate', None))
