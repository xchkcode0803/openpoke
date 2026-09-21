"""Storage behavior characterized before replacing JSON persistence."""
from server.services.execution.roster import AgentRoster


def test_roster_survives_reopen_and_preserves_exact_names(tmp_path):
    path = tmp_path / 'roster.json'
    roster = AgentRoster(path)
    for name in ('A B', 'A-B', 'a b', 'Ｃafé'):
        roster.add_agent(name)
    roster.add_agent('A B')
    assert AgentRoster(path).get_agents() == ['A B', 'A-B', 'a b', 'Ｃafé']
    roster.clear()
    assert AgentRoster(path).get_agents() == []
