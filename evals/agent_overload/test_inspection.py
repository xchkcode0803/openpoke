"""Additional live history cases and offline fixture/harness checks."""
import asyncio
import os

import pytest

from .cases import DEVELOPMENT_CASES
from .harness import run_case
from .inspection_cases import INSPECTION_CASES, INSPECTION_HISTORY
from .metrics import RoutingCorrectnessMetric
from .test_routing import _evaluate_live_case, _tool_call


@pytest.mark.live
@pytest.mark.inspection
@pytest.mark.parametrize('case', INSPECTION_CASES, ids=lambda case: case.name)
def test_live_inspection(case):
    if not os.getenv('RUN_LIVE_EVALS'):
        pytest.skip('set RUN_LIVE_EVALS=1 to call the interaction model')
    _evaluate_live_case(case, INSPECTION_HISTORY[case.name])


def test_inspection_fixtures_are_separate_and_valid():
    assert len(INSPECTION_CASES) == len(INSPECTION_HISTORY) == 6
    assert not {case.name for case in INSPECTION_CASES} & {case.name for case in DEVELOPMENT_CASES}
    for case in INSPECTION_CASES:
        assert set(INSPECTION_HISTORY[case.name]) <= set(case.initial_agents)


def test_harness_records_discovery_history_and_usage(monkeypatch):
    import server.agents.interaction_agent.runtime as runtime_module
    case = INSPECTION_CASES[0]
    count = 0

    async def completion(**kwargs):
        nonlocal count
        count += 1
        steps = [
            [_tool_call('search', 'search_agents', {'query': 'Maya'})],
            [_tool_call('inspect', 'inspect_agent', {'agent_name': 'Maya Planning B'})],
            [_tool_call('route', 'send_message_to_agent', {'agent_name': 'Maya Planning B', 'instructions': 'Find a vegetarian dinner menu.'})],
            [],
        ]
        return {'choices': [{'message': {'content': 'On it', 'tool_calls': steps[count - 1]}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'cost': 0.01}}

    monkeypatch.setenv('OPENROUTER_API_KEY', 'offline')
    monkeypatch.setattr(runtime_module, 'request_chat_completion', completion)
    result = asyncio.run(run_case(case, INSPECTION_HISTORY[case.name]))[0]
    assert RoutingCorrectnessMetric().measure(result) == 1
    assert result.metadata['discovery_call_count'] == 2
    assert result.metadata['model_call_count'] == 4
    assert result.input_token_count == 400 and result.output_token_count == 40
    assert result.token_cost == 0.04
    assert len(result.metadata['worker_dispatches']) == 1
    assert 'birthday' in result.tools_called[1].output['payload']['entries'][0]['text']
    assert result.metadata['discovery_closed_reason'] is None


@pytest.mark.parametrize('history', [{'missing': ()}, {'Maya Planning A': (('bad_tag', 'text'),)}])
def test_bad_history_restores_environment(monkeypatch, history):
    original = os.environ.get('OPENPOKE_DATA_DIR')
    with pytest.raises(ValueError):
        asyncio.run(run_case(INSPECTION_CASES[0], history))
    assert os.environ.get('OPENPOKE_DATA_DIR') == original


def test_iteration_failure_is_graded_not_unavailable(monkeypatch):
    import server.agents.interaction_agent.runtime as runtime_module

    async def completion(**kwargs):
        return {'choices': [{'message': {'tool_calls': [_tool_call('wait', 'wait', {'reason': 'Waiting'})]}}]}

    monkeypatch.setenv('OPENROUTER_API_KEY', 'offline')
    monkeypatch.setattr(runtime_module, 'request_chat_completion', completion)
    result = asyncio.run(run_case(INSPECTION_CASES[0]))[0]
    assert result.metadata['failure_kind'] == 'agent_iteration_limit'
    assert RoutingCorrectnessMetric().measure(result) == 0
    assert result.metadata['model_call_count'] == 8


def test_failed_model_request_is_preserved(monkeypatch):
    import server.agents.interaction_agent.runtime as runtime_module

    async def completion(**kwargs):
        raise RuntimeError('OpenRouter request failed (429)')

    monkeypatch.setenv('OPENROUTER_API_KEY', 'offline')
    monkeypatch.setattr(runtime_module, 'request_chat_completion', completion)
    result = asyncio.run(run_case(INSPECTION_CASES[0]))[0]
    assert result.metadata['failure_kind'] == 'provider'
    assert result.metadata['model_call_count'] == 1
    request = result.metadata['model_calls'][0]
    assert request['system'] and request['tools'] and request['messages']
    assert '429' in request['error']
    assert result.token_cost is None


def test_provider_timing_includes_retries_and_pacing(monkeypatch):
    import httpx
    from . import provider
    clock = [0.0]
    attempts = []

    async def sleep(seconds):
        clock[0] += seconds

    async def post(*args, **kwargs):
        clock[0] += 1.0
        attempts.append(1)
        return httpx.Response(429 if len(attempts) == 1 else 200, headers={'Retry-After': '7'})

    monkeypatch.setattr(provider.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(provider.asyncio, 'sleep', sleep)
    monkeypatch.setattr(provider, '_post', post)
    monkeypatch.setattr(provider, '_next_request', 2.0)
    response = asyncio.run(provider.paced_post(None, 'https://openrouter.ai/api/v1/chat/completions'))
    assert response.extensions['eval_timing'] == {
        'request_seconds': 2.0, 'pacing_seconds': 2.0, 'retry_wait_seconds': 7.0, 'attempts': 2}
