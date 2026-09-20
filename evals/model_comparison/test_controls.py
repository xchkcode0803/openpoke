"""Model/pacing changes must leave benchmark and judge semantics intact."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from evals.agent_overload import provider
from evals.agent_overload.campaign_budget import CampaignBudget
from .run import MODELS


@pytest.mark.parametrize('model', MODELS.values())
def test_candidate_reaches_new_process_and_judge_stays_fixed(model, tmp_path):
    code = '''
import json
from evals.agent_overload import provider, harness, metrics
print(json.dumps([provider.MODEL, harness.MODEL, metrics.FALLBACK_MODEL, provider.request_interval()]))
'''
    result = subprocess.check_output([sys.executable, '-c', code], text=True,
        env={**os.environ, 'EVAL_CANDIDATE_MODEL': model, 'OPENPOKE_DATA_DIR': str(tmp_path)})
    values = json.loads(result.strip().splitlines()[-1])
    assert values == [model, model, MODELS['sonnet'], 0 if model == MODELS['gemini'] else 4.1]


def test_gemini_removes_both_fixed_delays_but_retries(monkeypatch, tmp_path):
    monkeypatch.setattr(provider, 'MODEL', MODELS['gemini'])
    monkeypatch.setattr(provider, '_next_request', 0)
    prices = {MODELS['gemini']: {'prompt': '0.000001', 'completion': '0.000001',
              'max_completion_tokens': 20, 'context_length': 1000}}
    (tmp_path / 'prices.json').write_text(json.dumps(prices))
    budget = CampaignBudget(tmp_path)
    monkeypatch.setattr(provider, 'request_budget', budget)
    sleeps, statuses = [], iter([429, 200])
    async def sleep(seconds):
        sleeps.append(seconds)
    async def post(*args, **kwargs):
        return httpx.Response(next(statuses), headers={'Retry-After': '7'}, json={'usage': {'cost': .001}})
    monkeypatch.setattr(provider.asyncio, 'sleep', sleep)
    monkeypatch.setattr(provider, '_post', post)
    response = asyncio.run(provider.paced_post(None, 'https://openrouter.ai/api/v1/chat/completions',
                                              json={'model': MODELS['gemini'], 'messages': []}))
    assert response.status_code == 200
    assert sleeps.count(7) == 1
    assert all(s == 7 or s < .1 for s in sleeps)
    rows = json.loads((tmp_path / 'spend.json').read_text())['requests']
    assert [r['status'] for r in rows] == ['rate_limited', 'settled']
    assert sum(float(r['charged']) for r in rows) == .001


def test_gmail_shared_transport_does_not_multiply_retries(monkeypatch):
    from evals.agent_gmail.provider import Provider, ProviderFailure
    from evals.agent_gmail.config import EvalConfig
    monkeypatch.setenv('OPENROUTER_API_KEY', 'offline')
    calls = []
    async def transport(*args, **kwargs):
        calls.append(kwargs)
        return httpx.Response(429, extensions={'eval_timing': {'attempts': 4}}, text='limited')
    client = Provider(EvalConfig(), transport=transport)
    with pytest.raises(ProviderFailure):
        asyncio.run(client(role='execution', model=MODELS['sonnet'], messages=[]))
    assert len(calls) == 1
    assert client.calls[0]['attempts'][0]['attempts'] == 4
