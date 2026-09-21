"""Additional live history cases and offline fixture/harness checks."""
import asyncio
import json
import os

import pytest

from evals.agent_overload.cases import DEVELOPMENT_CASES
from evals.agent_overload.harness import run_case
from evals.agent_overload.inspection_cases import INSPECTION_CASES, INSPECTION_HISTORY
from evals.agent_overload.metrics import RoutingCorrectnessMetric


def _tool_call(identifier: str, name: str, arguments: dict) -> dict:
    if name == "send_message_to_agent":
        arguments = {"action": "reuse", **arguments}
    return {"id": identifier, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments),
    }}


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


def test_provider_timing_includes_only_request_and_retry_wait(monkeypatch):
    import httpx
    from evals.shared import http
    clock = [0.0]
    attempts = []

    async def sleep(seconds):
        clock[0] += seconds

    class Client:
        async def post(self, *args, **kwargs):
            clock[0] += 1.0
            attempts.append(1)
            return httpx.Response(429 if len(attempts) == 1 else 200, headers={'Retry-After': '7'})

    async def sleep(seconds):
        assert seconds == 7
        clock[0] += seconds

    monkeypatch.setattr(http.time, 'perf_counter', lambda: clock[0])
    monkeypatch.setattr(http.asyncio, 'sleep', sleep)
    response = asyncio.run(http.post_with_retry(Client(), 'https://openrouter.ai/api/v1/chat/completions'))
    assert response.extensions['eval_timing'] == {
        'request_seconds': 2.0, 'retry_wait_seconds': 7.0, 'attempts': 2}


@pytest.mark.parametrize('failure', ['routing', 'judge', 'provider', 'agent_iteration_limit'])
def test_evaluation_continues_after_a_failed_turn(monkeypatch, failure):
    import deepeval
    from deepeval.test_case import LLMTestCase
    from evals.agent_overload import harness, provider
    import server.agents.interaction_agent.runtime as runtime_module

    first = LLMTestCase(name='first', input='request', actual_output='reply', metadata={})
    second = LLMTestCase(name='second', input='request', actual_output='reply', metadata={})
    if failure in {'provider', 'agent_iteration_limit'}:
        first.metadata['failure_kind'] = failure
    graded, saved = [], []
    original_completion = runtime_module.request_chat_completion

    async def run_case(case, history):
        assert runtime_module.request_chat_completion is provider.interaction_completion
        return [first, second]

    def grade(result, **kwargs):
        assert kwargs['run_async'] is False
        graded.append(result.name)
        if result.name == 'first':
            if failure == 'judge':
                raise RuntimeError('Judge unavailable')
            raise AssertionError('Behavioral failure')

    monkeypatch.setattr(harness, 'run_case', run_case)
    monkeypatch.setattr(deepeval, 'assert_test', grade)
    monkeypatch.setattr(provider, 'save_result', lambda file, record: saved.append((file, record)))
    with pytest.raises(AssertionError, match='first'):
        harness.evaluate_live_case(INSPECTION_CASES[0])

    assert 'second' in graded
    assert ('first' in graded) is (failure != 'provider')
    assert [record['result']['name'] for file, record in saved if file == 'turns.jsonl'] == (
        ['second'] if failure == 'provider' else ['first', 'second'])
    assert sum(file == 'unavailable.jsonl' for file, _ in saved) == (failure == 'provider')
    assert sum(file == 'judge_errors.jsonl' for file, _ in saved) == (failure == 'judge')
    assert runtime_module.request_chat_completion is original_completion


def test_evaluation_verifies_stress_context_once(monkeypatch):
    from dataclasses import replace
    import deepeval
    from deepeval.test_case import LLMTestCase
    from evals.agent_overload import harness, provider

    case = replace(INSPECTION_CASES[0], tags=frozenset({'stress'}))
    history = INSPECTION_HISTORY[case.name]
    limits, verified, received, saved = {}, [], [], []

    async def verify(model):
        verified.append(model)
        limits[model] = 200000

    async def run_case(actual_case, actual_history):
        received.append((actual_case, actual_history))
        return [LLMTestCase(name='result', input='request', actual_output='reply', metadata={})]

    monkeypatch.setattr(provider, 'context_limits', limits)
    monkeypatch.setattr(provider, 'verify_context_limit', verify)
    monkeypatch.setattr(harness, 'run_case', run_case)
    monkeypatch.setattr(deepeval, 'assert_test', lambda *args, **kwargs: None)
    monkeypatch.setattr(provider, 'save_result', lambda file, record: saved.append(file))
    harness.evaluate_live_case(case, history)
    harness.evaluate_live_case(case, history)
    assert verified == [provider.MODEL]
    assert received == [(case, history), (case, history)]
    assert saved == ['turns.jsonl', 'turns.jsonl']
