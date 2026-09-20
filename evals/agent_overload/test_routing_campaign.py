"""Offline contract checks for fixtures, supervision, isolation, and spending."""
import asyncio
import json
import sys
from dataclasses import asdict
import hashlib

import httpx
import pytest

from .campaign_budget import BudgetStopped, CampaignBudget
from .challenge_cases import challenges
from .routing_campaign import prepare, supervise
from .routing_population import CHALLENGE_VARIANTS, SCALE_VARIANTS, Variant, materialize


def test_collection_is_lightweight_and_baseline_unchanged():
    assert len(SCALE_VARIANTS) == 48
    assert len(CHALLENGE_VARIANTS) == 36
    assert all(not hasattr(item, 'initial_agents') for item in SCALE_VARIANTS + CHALLENGE_VARIANTS)
    from .cases import full_cases
    from .stress_cases import stress_cases
    cases = full_cases() + stress_cases()
    assert len(cases) == 99
    digest = hashlib.sha256(json.dumps([asdict(case) for case in cases], default=lambda value: sorted(value), sort_keys=True).encode()).hexdigest()
    assert digest == 'f466df1ae88422eb3a2357d0cc6d913918e56c87128a4725aa31062cacac68fd' 


@pytest.mark.parametrize('kind,index', [('scale', i) for i in range(8)] + [('challenge', i) for i in range(12)])
def test_nested_reproducible_populations(kind, index):
    first, _, manifest = materialize(Variant(kind, index, 100))
    second, _, repeated = materialize(Variant(kind, index, 100))
    larger, _, _ = materialize(Variant(kind, index, 1000))
    assert first == second and manifest == repeated
    assert len(set(first.initial_agents)) == 100
    assert len(set(larger.initial_agents)) == 1000
    assert set(first.initial_agents) <= set(larger.initial_agents)
    original = Variant(kind, index, 100).source()[0]
    assert first.turns == larger.turns == original.turns
    assert first.initial_conversation == larger.initial_conversation
    background = set(larger.initial_agents) - set(original.initial_agents)
    assert all('BG-' not in name for name in background)
    assert not any('correct owner' in name.lower() or 'distractor' in name.lower() for name in background)


@pytest.mark.parametrize('index', range(12))
def test_scripted_discovery_is_feasible_and_isolated(index, monkeypatch):
    from .harness import run_case
    from .metrics import RoutingCorrectnessMetric
    from server.agents.interaction_agent import runtime
    challenge = challenges()[index]
    case, history, _ = materialize(Variant('challenge', index, 100))
    sequence = list(challenge.discovery)
    observed = []
    call_count = 0

    def call(name, arguments):
        nonlocal call_count
        call_count += 1
        return {'id': str(call_count), 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}

    async def completion(**kwargs):
        observed.append(kwargs)
        round_index = len(observed) - 1
        if round_index < len(sequence):
            name, arguments = sequence[round_index]
            tools = [call(name, arguments)]
        else:
            tools = [call('send_message_to_user', {'message': 'I will follow up.', 'end_turn': False})]
            for expected in case.turns[0].delegations:
                name = expected.acceptable_agent_names[0] if expected.route == 'reuse' else 'Outage Complaint New Work'
                tools.append(call('send_message_to_agent', {'agent_name': name, 'instructions': ' '.join(expected.required_facts), 'end_turn': True}))
        return {'choices': [{'message': {'content': '', 'tool_calls': tools}}]}

    monkeypatch.setattr(runtime, 'request_chat_completion', completion)
    results = asyncio.run(run_case(case, history))
    assert RoutingCorrectnessMetric().measure(results[0]) == 1
    assert results[0].metadata['discovery_call_count'] <= 6
    assert len(observed) <= 4
    for tool in results[0].tools_called:
        assert tool.output['success'], tool
    # Discovery is an accessible path, not merely a script guessing a hidden name.
    returned = json.dumps([tool.output for tool in results[0].tools_called if tool.name in {'search_agents', 'inspect_agent'}])
    for expected in case.turns[0].delegations:
        if expected.route == 'reuse' and expected.task_key != 'owner':
            continue
        if expected.route == 'reuse':
            assert expected.acceptable_agent_names[0] in returned + json.dumps(case.initial_conversation)


def test_hidden_history_not_in_assignment_profiles(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENPOKE_DATA_DIR', str(tmp_path))
    for index in (4, 5, 6):
        _, _, measurements = prepare(Variant('challenge', index, 100), tmp_path / str(index))
        assert challenges()[index].evidence not in json.dumps(measurements['initial_candidates'])


def test_watchdog_timeout_and_memory(tmp_path):
    timeout = supervise([sys.executable, '-c', 'import time; time.sleep(5)'], tmp_path / 'timeout', seconds=.05)
    assert timeout['resource_failure'] == 'wall_clock_limit'
    memory = supervise([sys.executable, '-c', 'import time; time.sleep(5)'], tmp_path / 'memory', memory_limit=1)
    assert memory['resource_failure'] == 'memory_limit'
    assert (tmp_path / 'memory' / 'process.json').exists()


def ledger(tmp_path, cap=10):
    (tmp_path / 'prices.json').write_text(json.dumps({'test': {'prompt': .000003, 'completion': .000015, 'max_completion_tokens': 1000, 'context_length': 32000}}))
    return CampaignBudget(tmp_path, cap)


def response(cost):
    return httpx.Response(200, json={'usage': {'cost': cost, 'prompt_tokens': 10, 'completion_tokens': 3}})


def test_budget_persists_and_charges_once(tmp_path):
    budget = ledger(tmp_path)
    identifier = budget.reserve({'model': 'test', 'messages': []})
    budget.settle(identifier, response(.01))
    other = CampaignBudget(tmp_path)
    with other.ledger() as state:
        assert len(state['requests']) == 1
        assert float(state['requests'][0]['charged']) == .01


def test_budget_reservation_limit_and_missing_prices(tmp_path):
    budget = ledger(tmp_path, .001)
    with pytest.raises(BudgetStopped, match='Budget limit'):
        budget.reserve({'model': 'test'})
    with pytest.raises(BudgetStopped, match='Pricing unavailable'):
        budget.reserve({'model': 'unknown'})


def test_budget_unknown_usage_and_interrupted_request_stop(tmp_path):
    budget = ledger(tmp_path)
    identifier = budget.reserve({'model': 'test'})
    with pytest.raises(BudgetStopped, match='Unsettled'):
        budget.reserve({'model': 'test'})
    with pytest.raises(BudgetStopped):
        budget.settle(identifier, httpx.Response(200, json={}))
    with pytest.raises(BudgetStopped):
        CampaignBudget(tmp_path).reserve({'model': 'test'})


def test_rate_limit_releases_reservation_and_retry_reserves_again(tmp_path):
    budget = ledger(tmp_path)
    first = budget.reserve({'model': 'test'})
    budget.settle(first, httpx.Response(429))
    second = budget.reserve({'model': 'test'})
    budget.settle(second, response(0))
    with budget.ledger() as state:
        assert len(state['requests']) == 2
        assert all(float(row['charged']) == 0 for row in state['requests'])


def test_decision_questions_share_one_request_charge(tmp_path):
    budget = ledger(tmp_path)
    identifier = budget.reserve({'model': 'test', 'questions': {'a': {}, 'b': {}}})
    budget.settle(identifier, response(.001))
    with budget.ledger() as state:
        assert len(state['requests']) == 1
        assert float(state['requests'][0]['charged']) == .001


def test_budget_paces_across_restarts_and_rejects_double_settlement(tmp_path):
    budget = ledger(tmp_path)
    first = budget.reserve({'model': 'test'})
    budget.settle(first, response(.001))
    restarted = CampaignBudget(tmp_path)
    second = restarted.reserve({'model': 'test'})
    assert 0 < restarted.delay(second) <= 4.1
    with pytest.raises(BudgetStopped, match='already settled'):
        restarted.settle(first, response(.001))
    restarted.settle(second, response(.001))


def test_provider_budget_checked_before_every_attempt(tmp_path, monkeypatch):
    from . import provider
    budget = ledger(tmp_path)
    calls = []

    async def post(*args, **kwargs):
        calls.append(kwargs)
        return httpx.Response(429) if len(calls) == 1 else response(.001)

    async def sleep(*args):
        pass

    monkeypatch.setattr(provider, 'request_budget', budget)
    monkeypatch.setattr(provider, '_post', post)
    monkeypatch.setattr(provider.asyncio, 'sleep', sleep)
    asyncio.run(provider.paced_post(None, 'https://openrouter.ai/api/v1/chat/completions', json={'model': 'test'}))
    with budget.ledger() as state:
        assert [row['status'] for row in state['requests']] == ['rate_limited', 'settled']
