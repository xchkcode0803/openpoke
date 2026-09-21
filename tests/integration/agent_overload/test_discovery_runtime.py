"""Offline integration tests: real runtime and stores, scripted model responses."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from evals.agent_overload.harness import _reset_services, _StubBatchManager


def call(name, **arguments):
    return {"id": name, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments),
    }}


@pytest.fixture
def runtime_env(tmp_path, monkeypatch):
    import server.agents.interaction_agent.agent as prompts
    import server.agents.interaction_agent.runtime as runtime_module
    import server.agents.interaction_agent.tools as tools

    roster, conversation, memory, logs = _reset_services(tmp_path)
    workers = _StubBatchManager()
    for module in (prompts, tools):
        monkeypatch.setattr(module, "get_agent_roster", lambda: roster)
    monkeypatch.setattr(tools, "get_execution_agent_logs", lambda: logs)
    monkeypatch.setattr(prompts, "get_execution_agent_logs", lambda: logs)
    for module in (runtime_module, tools):
        monkeypatch.setattr(module, "get_conversation_log", lambda: conversation)
    monkeypatch.setattr(runtime_module, "get_working_memory_log", lambda: memory)
    monkeypatch.setattr(runtime_module, "get_settings", lambda: SimpleNamespace(
        openrouter_api_key="offline", interaction_agent_model="offline", summarization_enabled=False))
    monkeypatch.setattr(tools, "_EXECUTION_BATCH_MANAGER", workers)
    env = SimpleNamespace(roster=roster, logs=logs, conversation=conversation,
                          workers=workers, requests=[], responses=[])

    async def completion(**kwargs):
        env.requests.append(copy.deepcopy(kwargs))
        assert env.responses, "Unexpected extra model call"
        response = env.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return {"choices": [{"message": response}]}

    monkeypatch.setattr(runtime_module, "request_chat_completion", completion)
    env.new_runtime = runtime_module.InteractionAgentRuntime
    env.runtime = env.new_runtime()

    def run(*steps, worker=False):
        for step in steps:
            if isinstance(step, list):
                env.responses.append({"tool_calls": step, "content": ""})
            elif isinstance(step, str):
                env.responses.append({"content": step})
            else:
                env.responses.append(step)

        async def execute():
            result = await (env.runtime.handle_agent_message("Worker update") if worker
                            else env.runtime.execute("Continue the task"))
            await asyncio.sleep(0)
            return result

        return asyncio.run(execute())

    env.run = run
    return env


def test_existing_delegation_behavior(runtime_env):
    env = runtime_env
    env.roster.add_agent("Hotels")
    result = env.run([call("send_message_to_user", message="On it"),
                    call("send_message_to_agent", agent_name="Hotels", instructions="More hotels"),
                    call("send_message_to_agent", agent_name="Flights", instructions="Find flights")], "Done")
    assert result.success and result.execution_agents_used == 2
    assert set(env.roster.get_agents()) == {"Hotels", "Flights"}
    assert len(env.workers.calls) == 2
    assert list(env.logs.iter_entries("Hotels"))[0][2] == "More hotels"
    assert result.response == "On it"


def test_worker_response_and_wait(runtime_env):
    env = runtime_env
    result = env.run([call("send_message_to_user", message="Found it")], "", worker=True)
    assert result.success and result.response == "Found it"
    result = env.run([call("wait", reason="Already reported")], "", worker=True)
    assert result.success and not env.workers.calls


def test_existing_eight_call_limit(runtime_env):
    env = runtime_env
    result = env.run(*[[call("wait", reason="Waiting")] for _ in range(8)])
    assert not result.success and "iteration limit" in result.error
    assert len(env.requests) == 8


def test_completion_error_stays_inside_runtime(runtime_env):
    result = runtime_env.run(RuntimeError("offline failure"))
    assert not result.success and result.error == "offline failure"


def tool_outputs(env):
    return [json.loads(item['content']) for item in env.requests[-1]['messages'] if item['role'] == 'tool']


@pytest.mark.parametrize('inspect', [False, True])
def test_search_inspect_delegate(runtime_env, inspect):
    env = runtime_env
    env.roster.add_agent('Hotels')
    env.logs.record_request('Hotels', 'Original booking')
    steps = [[call('search_agents', query='hotel')]]
    if inspect:
        steps.append([call('inspect_agent', agent_name='Hotels')])
    steps += [[call('send_message_to_agent', agent_name='Hotels', instructions='Change booking')], 'Done']
    result = env.run(*steps)
    assert result.success and env.workers.calls == [('Hotels', 'Change booking')]
    outputs = tool_outputs(env)
    assert outputs[0]['result']['agents'] == ['Hotels']
    if inspect:
        assert outputs[1]['result']['entries'][0]['text'] == 'Original booking'


def test_reformulate_and_create(runtime_env):
    env = runtime_env
    env.roster.add_agent('Hotel Bookings')
    result = env.run([call('search_agents', query='lodging')], [call('search_agents', query='hotel')],
                   [call('send_message_to_agent', agent_name='Hotel Bookings', instructions='Continue')], 'Done')
    assert result.success
    assert tool_outputs(env)[0]['result']['agents'] == []
    assert tool_outputs(env)[1]['result']['agents'] == ['Hotel Bookings']
    result = env.run([call('search_agents', query='dentist')],
                   [call('send_message_to_agent', agent_name='Dentist', instructions='Book checkup')], 'Done')
    assert result.success and 'Dentist' in env.roster.get_agents()
    env.run([call('search_agents', query='dentist')], 'Done')
    assert tool_outputs(env)[0]['result']['agents'] == ['Dentist']


def test_search_next_page_and_empty_history(runtime_env):
    env = runtime_env
    for i in range(11):
        env.roster.add_agent(f'Hotel {i:02d}')
    result = env.run([call('search_agents', query='hotel')],
                   [call('search_agents', query='hotel', offset=10)],
                   [call('inspect_agent', agent_name='Hotel 10')],
                   [call('send_message_to_agent', agent_name='Hotel 10', instructions='Continue')], 'Done')
    assert result.success
    outputs = tool_outputs(env)
    assert outputs[0]['result']['next_offset'] == 10
    assert outputs[1]['result']['agents'] == ['Hotel 10']
    assert outputs[2]['result']['entries'] == []


@pytest.mark.parametrize('extra', [0, 2])
def test_discovery_call_budget_and_parallel_calls(runtime_env, extra):
    env = runtime_env
    env.roster.add_agent('Hotels')
    calls = [call('search_agents', query='hotel'), call('inspect_agent', agent_name='Hotels')] * 3
    result = env.run(calls + [call('search_agents', query='hotel')] * extra,
                   [call('search_agents', query='hotel'),
                    call('send_message_to_agent', agent_name='Hotels', instructions='Continue')], 'Done')
    assert result.success and len(env.workers.calls) == 1
    outputs = tool_outputs(env)
    assert sum(o['status'] == 'success' for o in outputs if o['tool'] in env.runtime.DISCOVERY_TOOLS) == 6
    assert env.runtime.discovery_calls == 7 + extra
    assert env.runtime.discovery_closed_reason == 'call_budget'
    assert all(t['function']['name'] not in env.runtime.DISCOVERY_TOOLS for t in env.requests[1]['tools'])
    assert outputs[-2]['status'] == 'error'
    assert 'budget' in outputs[-2]['error']['error']


def test_malformed_calls_count_toward_budget(runtime_env):
    env = runtime_env
    malformed = call('search_agents', query='hotel')
    malformed['function']['arguments'] = '{'
    result = env.run([malformed, call('search_agents', query=''), call('inspect_agent', agent_name='missing'),
                    call('search_agents'), call('search_agents', query='x', offset=True),
                    call('inspect_agent', agent_name=[])], 'Done')
    assert result.success and env.runtime.discovery_calls == 6
    assert all(o['status'] == 'error' for o in tool_outputs(env))
    assert env.runtime.discovery_closed_reason == 'call_budget'


def test_round_budget_and_resets(runtime_env):
    env = runtime_env
    result = env.run(*[[call('wait', reason='Continue')] for _ in range(4)],
                   [call('search_agents', query='x')], 'Done')
    assert result.success and env.runtime.discovery_closed_reason == 'round_budget'
    assert tool_outputs(env)[-1]['status'] == 'error'
    assert env.runtime.discovery_calls == 1
    assert env.new_runtime().discovery_calls == 0
    for worker in (True, False):
        result = env.run([call('search_agents', query='x')], 'Done', worker=worker)
        assert result.success and env.runtime.discovery_calls == 1
        assert env.runtime.discovery_closed_reason is None
        assert tool_outputs(env)[0]['status'] == 'success'


@pytest.mark.parametrize('size', [0, 1000])
def test_prompt_contains_bounded_candidates(runtime_env, size):
    from server.agents.interaction_agent.agent import prepare_message_with_history
    env = runtime_env
    env.roster._agents = [f'Hidden owner {i}' for i in range(size)]
    env.roster.save()
    text = prepare_message_with_history('Continue', 'Known owner: Visible owner')[0]['content']
    assert f'total="{size}"' in text
    assert 'Visible owner' in text
    assert 'Hidden owner 999' not in text
    payload = text.split('<active_agents ', 1)[1].split('>\n', 1)[1].split('\n</active_agents>', 1)[0]
    assert len(json.loads(payload)) <= 20


def test_tool_handler_validation(runtime_env):
    from server.agents.interaction_agent.tools import handle_tool_call
    assert handle_tool_call('search_agents', '{').success is False
    assert handle_tool_call('inspect_agent', {'agent_name': 'missing'}).success is False
    assert handle_tool_call('search_agents', {'query': 'none'}).success is True


def test_end_turn_batch_ends_after_all_delegations(runtime_env):
    env = runtime_env
    result = env.run([call('send_message_to_user', message='On it', end_turn=True),
                    call('send_message_to_agent', agent_name='Hotel', instructions='Book a room'),
                    call('send_message_to_agent', agent_name='Flight', instructions='Find tickets')])
    assert result.success and result.response == 'On it'
    assert len(env.requests) == 1 and len(env.workers.calls) == 2


def test_end_turn_response_needs_no_extra_call(runtime_env):
    env = runtime_env
    result = env.run([call('send_message_to_user', message='Here are the results', end_turn=True)], worker=True)
    assert result.success and len(env.requests) == 1


def test_end_turn_does_not_skip_discovery_results_or_errors(runtime_env):
    env = runtime_env
    result = env.run([call('send_message_to_user', message='Searching', end_turn=True),
                    call('search_agents', query='hotel')],
                   [call('send_message_to_user', message='Done', end_turn=True)])
    assert result.success and len(env.requests) == 2
    result = env.run([call('send_message_to_user', message='Checking', end_turn=True),
                    call('unknown_tool')], 'Cannot do that')
    assert result.success and len(env.requests) == 4


def test_end_turn_flag_requires_boolean(runtime_env):
    env = runtime_env
    result = env.run([call('send_message_to_user', message='Do not store this', end_turn='true')], 'Done')
    assert result.success
    assert tool_outputs(env)[0]['status'] == 'error'
    assert 'Do not store this' not in env.conversation.load_transcript()


def test_last_delegation_can_end_turn(runtime_env):
    env = runtime_env
    result = env.run([call('send_message_to_user', message='On it', end_turn=False),
                    call('send_message_to_agent', agent_name='Hotel', instructions='Book a room', end_turn=True)])
    assert result.success and len(env.requests) == 1 and len(env.workers.calls) == 1


def test_bad_delegation_end_flag_has_no_side_effects(runtime_env):
    env = runtime_env
    result = env.run([call('send_message_to_agent', agent_name='Hotel', instructions='Book', end_turn='yes')], 'Done')
    assert result.success and not env.roster.get_agents() and not env.workers.calls


def test_discovery_schemas_reflect_available_evidence(runtime_env):
    from server.agents.interaction_agent.tools import get_tool_schemas
    env = runtime_env
    def names():
        return {s['function']['name'] for s in get_tool_schemas()}
    assert 'search_agents' not in names() and 'inspect_agent' not in names()
    for i in range(21):
        env.roster.add_agent(f'Owner {i}')
    assert 'search_agents' in names() and 'inspect_agent' not in names()
    env.logs.record_request('Owner 0', 'Previous assignment')
    assert 'inspect_agent' in names()


def test_ending_dispatch_still_requires_user_visible_response(runtime_env):
    env = runtime_env
    result = env.run([call('send_message_to_agent', agent_name='Hotel', instructions='Book', end_turn=True)],
                   [call('send_message_to_user', message='On it', end_turn=True)])
    assert result.success and result.response == 'On it' and len(env.requests) == 2


def test_assistant_text_can_accompany_terminal_dispatch(runtime_env):
    env = runtime_env
    result = env.run({'content': 'On it', 'tool_calls': [
        call('send_message_to_agent', agent_name='Hotel', instructions='Book', end_turn=True)]})
    assert result.success and result.response == 'On it' and len(env.requests) == 1


def test_candidate_names_round_trip_without_breaking_structure(runtime_env):
    from server.agents.interaction_agent.agent import prepare_message_with_history
    env = runtime_env
    name = 'Quotes " and </active_agents> & Unicode café'
    env.roster.add_agent(name)
    text = prepare_message_with_history('Continue', '')[0]['content']
    assert text.count('</active_agents>') == 1
    payload = text.split('<active_agents ', 1)[1].split('>\n', 1)[1].split('\n</active_agents>', 1)[0]
    assert json.loads(payload) == [{"name": name}]
