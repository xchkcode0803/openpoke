"""Offline contract checks for fixtures, supervision, and isolation."""
import asyncio
import json
import sys
from dataclasses import asdict
import hashlib
from pathlib import Path

import pytest

from evals.agent_overload.challenge_cases import challenges
from evals.agent_overload.routing_campaign import prepare, supervise
from evals.agent_overload.routing_population import CHALLENGE_VARIANTS, SCALE_VARIANTS, Variant, materialize


def test_collection_is_lightweight_and_baseline_unchanged():
    assert len(SCALE_VARIANTS) == 48
    assert len(CHALLENGE_VARIANTS) == 36
    assert all(not hasattr(item, 'initial_agents') for item in SCALE_VARIANTS + CHALLENGE_VARIANTS)
    from evals.agent_overload.cases import full_cases
    from evals.agent_overload.stress_cases import stress_cases
    cases = full_cases() + stress_cases()
    assert len(cases) == 99
    digest = hashlib.sha256(json.dumps([asdict(case) for case in cases], default=lambda value: sorted(value), sort_keys=True).encode()).hexdigest()
    assert digest == '37fb9ff607c8613d702ea5e66a5d514ba49250b64d2fb7f48c37dc69f78907b1'


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
    from evals.agent_overload.harness import run_case
    from evals.agent_overload.metrics import RoutingCorrectnessMetric
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
                tools.append(call('send_message_to_agent', {'action': expected.route, 'agent_name': name, 'instructions': ' '.join(expected.required_facts), 'end_turn': True}))
        return {'choices': [{'message': {'content': '', 'tool_calls': tools}}]}

    monkeypatch.setattr(runtime, 'request_chat_completion', completion)
    results = asyncio.run(run_case(case, history))
    assert RoutingCorrectnessMetric().measure(results[0]) == 1
    assert results[0].metadata['roster_before'] is None
    assert len(results[0].metadata['initial_candidates']) <= 20
    assert 'initial_owner_coverage' in results[0].metadata
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
        assert challenges()[index].evidence not in json.dumps([{key: value for key, value in item.items() if key != 'matching_history'} for item in measurements['initial_candidates']])
        if index == 6:
            profiles = {item['name']: item for item in measurements['initial_candidates']}
            assert profiles['Housing Desk Elm']['initial_assignment'] == profiles['Housing Desk Ash']['initial_assignment']


def test_watchdog_timeout_and_memory(tmp_path, monkeypatch):
    from evals.agent_overload import routing_campaign

    monkeypatch.setattr(routing_campaign, '_memory_bytes', lambda _pid: 0)
    timeout = supervise([sys.executable, '-c', 'import time; time.sleep(5)'], tmp_path / 'timeout', seconds=.05)
    assert timeout['resource_failure'] == 'wall_clock_limit'
    monkeypatch.setattr(routing_campaign, '_memory_bytes', lambda _pid: 2)
    memory = supervise([sys.executable, '-c', 'import time; time.sleep(5)'], tmp_path / 'memory', memory_limit=1)
    assert memory['resource_failure'] == 'memory_limit'
    assert (tmp_path / 'memory' / 'process.json').exists()


@pytest.mark.parametrize('raises', [False, True])
def test_run_variant_removes_supervised_temporary_state(tmp_path, monkeypatch, raises):
    from evals.agent_overload import routing_campaign

    monkeypatch.setenv('EVAL_ARTIFACT_DIR', str(tmp_path / 'artifacts'))
    directories = []

    def stopped(command, destination, **kwargs):
        directory = Path(command[-1])
        directories.append(directory)
        sqlite = directory / 'execution_agents' / 'agents.sqlite3'
        sqlite.parent.mkdir(parents=True)
        sqlite.write_text('temporary state')
        if raises:
            raise RuntimeError('supervisor failed')
        return {'resource_failure': 'wall_clock_limit', 'returncode': -15}

    monkeypatch.setattr(routing_campaign, 'supervise', stopped)
    variant = Variant('scale', 0, 10)
    if raises:
        with pytest.raises(RuntimeError, match='supervisor failed'):
            routing_campaign.run_variant(variant, 'capacity')
    else:
        result = routing_campaign.run_variant(variant, 'capacity')
        assert result['status'] == 'resource_limit'
    assert directories and all(not directory.exists() for directory in directories)


def test_population_covers_task_families_and_naming_styles():
    from evals.agent_overload.routing_population import background_name, FAMILIES
    text = '\n'.join(background_name(i, 9137, 'Montreal', ('Hotel', 'Flights')) for i in range(5000)).casefold()
    assert all(family.casefold() in text for family in FAMILIES)
    assert all(pattern in text for pattern in ('ref ', 'account ', 'reservation ', 'stuff:', 'follow-up', 'records /'))
