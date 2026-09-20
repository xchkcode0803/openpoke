"""Indexed discovery contracts using real SQLite and journal stores."""
import pytest
from server.agents.interaction_agent.discovery import search_names, select_candidates, inspect_history, ownership_profile
from server.services.execution.roster import AgentRoster
from server.services.execution.log_store import ExecutionAgentLogStore


@pytest.fixture
def stores(tmp_path):
    roster = AgentRoster(tmp_path / 'roster.json')
    logs = ExecutionAgentLogStore(tmp_path)
    return roster, logs


def test_unicode_exact_identity_and_literal_queries(stores):
    roster, logs = stores
    names = ['Z Montréal Hotel', 'Ｍｏｎｔｒéａｌ_Hotel', 'Montréal-Hotel', 'Montréal Hotel April', 'Flights', 'Straße 2026-04', 'STRASSE 2026_04']
    roster.bulk_import(names)
    assert search_names(roster.catalog, 'MONTRÉAL hotel')['agents'][:2] == ['Montréal-Hotel', 'Ｍｏｎｔｒéａｌ_Hotel']
    assert set(search_names(roster.catalog, 'strasse 04')['agents']) == set(names[-2:])
    assert search_names(roster.catalog, '"; DROP TABLE agents; --')['agents'] == []
    assert roster.count() == len(names)
    assert set(search_names(roster.catalog, 'hotel flights')['agents']) == set(names[:5])


@pytest.mark.parametrize('size', [0, 1, 10, 11, 37, 150])
def test_pages_are_bounded_and_deterministic(stores, size):
    roster, _ = stores
    names = [f'Hotel {i:05d}' for i in range(size)]
    roster.bulk_import(list(reversed(names)))
    found, offset = [], 0
    while True:
        page = search_names(roster.catalog, 'hotel', offset)
        assert len(page['agents']) <= 10 and 'total_matches' not in page
        assert page['has_more'] == (page['next_offset'] is not None)
        found.extend(page['agents'])
        offset = page['next_offset']
        if offset is None:
            break
    assert found == names[:100]
    assert search_names(roster.catalog, 'hotel', len(found))['agents'] == []


@pytest.mark.parametrize('query', ['', ' ', '---___', None, 3, [], True])
def test_invalid_search(stores, query):
    with pytest.raises(ValueError, match='query'):
        search_names(stores[0].catalog, query)


@pytest.mark.parametrize('offset', [-1, 2, .5, '0', None, True, False])
def test_invalid_offsets(stores, offset):
    roster, logs = stores
    roster.add_agent('Hotel')
    with pytest.raises(ValueError, match='offset'):
        search_names(roster.catalog, 'hotel', offset)
    with pytest.raises(ValueError, match='offset'):
        inspect_history(roster.catalog, 'Hotel', logs, offset)


def test_history_sources_profiles_and_inspection(stores):
    roster, logs = stores
    roster.add_agent('Desk')
    assert ownership_profile('Desk', logs) == {'name': 'Desk'}
    assert ownership_profile('Missing', logs) == {'name': 'Missing'}
    logs.record_request('Desk', 'First assignment')
    logs.record_request('Desk', 'Find the violet booking')
    logs.record_tool_response('Desk', 'email', 'rawsecret')
    logs.record_action('Desk', 'actionsecret')
    logs.record_agent_response('Desk', 'Booking ORCHID confirmed')
    logs.record_request('Desk', 'Latest assignment')
    assert search_names(roster.catalog, 'rawsecret actionsecret')['agents'] == []
    for query in ('violet', 'ORCHID'):
        result = search_names(roster.catalog, query)
        assert result['agents'] == ['Desk']
        assert query.lower() in result['candidates'][0]['matching_history']['text'].lower()
    profile = ownership_profile('Desk', logs)
    assert profile['initial_assignment'] == 'First assignment'
    assert profile['latest_assignment'] == 'Latest assignment'
    page = inspect_history(roster.catalog, 'Desk', logs)
    assert page['total_matches'] == 4
    assert page['entries'][0]['text'] == 'Latest assignment'
    assert not page['next_offset']
    assert inspect_history(roster.catalog, 'Desk', logs, 4)['entries'] == []


@pytest.mark.parametrize('length', [999, 1000, 1001])
def test_excerpt_limits(stores, length):
    roster, logs = stores
    roster.add_agent('Owner')
    logs.record_request('Owner', 'x' * length)
    row = inspect_history(roster.catalog, 'Owner', logs)['entries'][0]
    assert len(row['text']) == min(length,1000)
    assert row['truncated'] == (length > 1000)
    assert len(ownership_profile('Owner', logs)['initial_assignment']) == 400


@pytest.mark.parametrize('name', ['missing', 'OWNER', '', None, [], 42])
def test_unknown_owner(stores, name):
    stores[0].add_agent('Owner')
    with pytest.raises(ValueError, match='agent_name'):
        inspect_history(stores[0].catalog, name, stores[1])


def test_empty_history_and_pagination(stores):
    roster, logs = stores
    roster.add_agent('Owner')
    assert inspect_history(roster.catalog, 'Owner', logs)['entries'] == []
    for i in range(9):
        logs.record_agent_response('Owner', f'Update {i}')
    first = inspect_history(roster.catalog, 'Owner', logs)
    second = inspect_history(roster.catalog, 'Owner', logs, first['next_offset'])
    assert [r['text'] for r in first['entries']+second['entries']] == [f'Update {i}' for i in reversed(range(9))]
    assert ownership_profile('Owner', logs) == {'name':'Owner'}


def test_small_roster_complete_and_large_roster_bounded(stores):
    roster, logs = stores
    roster.bulk_import(['Tokyo Hotels', 'Tokyo Flights', 'Garden Maintenance'])
    assert [r['name'] for r in select_candidates(roster.catalog,'flights')] == roster.get_agents()
    roster.bulk_import(roster.get_agents()+[f'Library Renewal {i}' for i in range(100)])
    selected = select_candidates(roster.catalog,'cheap flights','Tokyo Hotels found the room')
    assert {'Tokyo Hotels','Tokyo Flights'} <= {r['name'] for r in selected}
    assert len(selected) <= 20
    assert select_candidates(roster.catalog,'unknownxyz') == []


def test_explicit_owner_and_profiles_do_not_repeat_evidence(stores):
    roster, logs = stores
    roster.bulk_import([f'Task {i}' for i in range(50)])
    logs.record_request('Task 0','Find the sapphire booking')
    result=select_candidates(roster.catalog,'Return to Task 0',' '.join(roster.get_agents()))
    assert result[0]['name']=='Task 0'
    profile=search_names(roster.catalog,'sapphire')['candidates'][0]
    assert 'matching_history' not in profile
    logs.record_request('Task 0','Now own flights only')
    assert ownership_profile('Task 0',logs)['latest_assignment']=='Now own flights only'
