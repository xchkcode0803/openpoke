"""Migration, journaling recovery, concurrency, and safe delegation."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from server.services.execution.roster import AgentRoster
from server.services.execution.log_store import ExecutionAgentLogStore
from server.agents.interaction_agent.delegation import resolve_delegation
from server.agents.interaction_agent.discovery import inspect_history, search_names, select_candidates


def test_migration_backup_duplicates_and_restart(tmp_path):
    path=tmp_path/'roster.json'
    path.write_text(json.dumps(['B','a','A','a']))
    roster=AgentRoster(path)
    assert roster.get_agents()==['B','a','A']
    assert not path.exists() and (tmp_path/'roster.legacy.json').exists()
    with roster.catalog.connect() as db:
        assert db.execute("SELECT value FROM metadata WHERE key='migration_duplicates'").fetchone()[0]=='1'
    roster.clear()
    assert AgentRoster(path).count()==0
    roster.add_agent('New')
    roster.export_json(tmp_path/'export.json')
    assert json.loads((tmp_path/'export.json').read_text())==['New']


@pytest.mark.parametrize('text', ['{broken', '{}', '[3]', '[""]'])
def test_malformed_migration_never_becomes_empty_success(tmp_path,text):
    path=tmp_path/'roster.json';path.write_text(text)
    with pytest.raises(ValueError): AgentRoster(path)
    assert path.read_text()==text
    path.write_text('["Recovered"]')
    assert AgentRoster(path).get_agents()==['Recovered']


def test_missing_catalog_requires_explicit_restore(tmp_path):
    (tmp_path/'roster.legacy.json').write_text('["Owner"]')
    with pytest.raises(RuntimeError,match='restore explicitly'): AgentRoster(tmp_path/'roster.json')


def test_concurrent_add_and_transaction_rollback(tmp_path):
    roster=AgentRoster(tmp_path/'roster.json')
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(roster.add_agent,['Owner']*12))==1
    assert roster.count()==1
    with pytest.raises(RuntimeError):
        with roster.catalog.connect() as db:
            db.execute("UPDATE agents SET name='Incorrect'")
            raise RuntimeError('rollback')
    assert roster.contains('Owner') and not roster.contains('Incorrect')
    assert not roster.contains(None)


def test_legacy_log_import_and_ambiguous_slug(tmp_path):
    (tmp_path/'roster.json').write_text('["A B", "A-B", "Unique"]')
    (tmp_path/'a-b.log').write_text('<agent_request timestamp="x">Shared ambiguous work</agent_request>\n')
    (tmp_path/'unique.log').write_text('<agent_request timestamp="x">Violet booking</agent_request>\n')
    roster=AgentRoster(tmp_path/'roster.json');logs=ExecutionAgentLogStore(tmp_path)
    assert search_names(roster.catalog,'violet')['agents']==['Unique']
    assert search_names(roster.catalog,'ambiguous')['agents']==[]
    with pytest.raises(ValueError,match='Ambiguous'): inspect_history(roster.catalog,'A B',logs)
    assert (tmp_path/'a-b.log').exists()


def test_new_colliding_slugs_get_distinct_journals(tmp_path):
    roster=AgentRoster(tmp_path/'roster.json');roster.bulk_import(['A B','A-B'])
    logs=ExecutionAgentLogStore(tmp_path)
    logs.record_request('A B','violet');logs.record_request('A-B','orchid')
    assert logs._log_path('A B')!=logs._log_path('A-B')
    assert search_names(roster.catalog,'violet')['agents']==['A B']


def test_completed_append_recovers_after_index_failure(tmp_path,monkeypatch):
    roster=AgentRoster(tmp_path/'roster.json');roster.add_agent('Owner')
    logs=ExecutionAgentLogStore(tmp_path);original=logs._sync_handle;calls=0
    def fail_second(*args):
        nonlocal calls
        calls+=1
        if calls==2: raise RuntimeError('interrupted indexing')
        return original(*args)
    monkeypatch.setattr(logs,'_sync_handle',fail_second)
    with pytest.raises(RuntimeError): logs.record_request('Owner','Violet recovery')
    recovered=ExecutionAgentLogStore(tmp_path)
    assert search_names(roster.catalog,'violet')['agents']==['Owner']
    assert inspect_history(roster.catalog,'Owner',recovered)['total_matches']==1
    assert inspect_history(roster.catalog,'Owner',ExecutionAgentLogStore(tmp_path))['total_matches']==1


def test_replace_truncate_delete_and_explicit_rebuild(tmp_path):
    roster=AgentRoster(tmp_path/'roster.json');roster.add_agent('Owner')
    logs=ExecutionAgentLogStore(tmp_path);logs.record_request('Owner','Long original assignment')
    path=logs._log_path('Owner')
    path.write_text('<agent_response timestamp="x">New</agent_response>\n')
    assert inspect_history(roster.catalog,'Owner',logs)['entries'][0]['text']=='New'
    replacement=tmp_path/'replacement';replacement.write_text('<agent_request timestamp="x">Replacement</agent_request>\n');replacement.replace(path)
    assert inspect_history(roster.catalog,'Owner',logs)['entries'][0]['text']=='Replacement'
    path.write_text('<agent_request timestamp="x">Other scope</agent_request>\n')
    logs.rebuild_index()
    assert search_names(roster.catalog,'Other')['agents']==['Owner']
    path.unlink()
    assert inspect_history(roster.catalog,'Owner',logs)['entries']==[]
    logs.record_request('Owner','Restored')
    logs.clear_all()
    assert not list(tmp_path.glob('*.log')) and not roster.catalog.has_history()


@pytest.mark.parametrize('content',['partial','broken\n'])
def test_corrupt_history_fails_visibly(tmp_path,content):
    roster=AgentRoster(tmp_path/'roster.json');roster.add_agent('Owner')
    logs=ExecutionAgentLogStore(tmp_path)
    logs._log_path('Owner').write_text(content)
    with pytest.raises(ValueError): logs.sync_agent('Owner')


@pytest.mark.parametrize('name,instructions,action', [('A','Do it',None),('A','Do it','wrong'),('', 'Do it','create'),(None,'Do it','reuse'),('A','','create'),('A',None,'create')])
def test_invalid_dispatch_has_no_side_effects(tmp_path,name,instructions,action):
    roster=AgentRoster(tmp_path/'roster.json')
    with pytest.raises(ValueError): resolve_delegation(roster,name,instructions,action)
    assert roster.count()==0


def test_explicit_actions_reject_typo_and_duplicate(tmp_path):
    roster=AgentRoster(tmp_path/'roster.json')
    assert resolve_delegation(roster,'Owner','Do it','create') is True
    assert resolve_delegation(roster,'Owner','Continue','reuse') is False
    with pytest.raises(ValueError,match='Search'): resolve_delegation(roster,'owner','Continue','reuse')
    with pytest.raises(ValueError,match='already exists'): resolve_delegation(roster,'Owner','Continue','create')
    assert roster.get_agents()==['Owner']


def test_bounded_retrieval_deduplicates_history_and_mentions(tmp_path):
    roster=AgentRoster(tmp_path/'roster.json');roster.bulk_import([f'Task {i}' for i in range(300)])
    logs=ExecutionAgentLogStore(tmp_path)
    logs.record_request('Task 0','violet first');logs.record_agent_response('Task 0','violet second')
    assert search_names(roster.catalog,'violet')['agents']==['Task 0']
    result=select_candidates(roster.catalog,'Task 0',' '.join(roster.get_agents()))
    assert result[0]['name']=='Task 0' and len(result)<=20


def test_warm_prompt_and_tools_never_enumerate_roster_or_files(tmp_path,monkeypatch):
    from server.agents.interaction_agent import agent,tools
    roster=AgentRoster(tmp_path/'roster.json');roster.bulk_import([f'Hotel {i}' for i in range(100)])
    logs=ExecutionAgentLogStore(tmp_path);logs.record_request('Hotel 0','Violet booking')
    for module in (agent,tools):
        monkeypatch.setattr(module,'get_agent_roster',lambda:roster)
        monkeypatch.setattr(module,'get_execution_agent_logs',lambda:logs)
    def forbidden(*args,**kwargs): raise AssertionError('unbounded routing read')
    monkeypatch.setattr(roster,'get_agents',forbidden)
    monkeypatch.setattr(logs,'list_agents',forbidden)
    monkeypatch.setattr(Path,'glob',forbidden)
    assert 'Hotel 0' in agent.prepare_message_with_history('Violet','')[0]['content']
    assert tools.search_agents('violet').success
    assert tools.inspect_agent('Hotel 0').success
    assert tools.get_tool_schemas()


def test_normalized_history_query_returns_original_evidence(tmp_path):
    roster=AgentRoster(tmp_path/'roster.json');roster.add_agent('Owner')
    logs=ExecutionAgentLogStore(tmp_path)
    logs.record_agent_response('Owner','Ｂｏｏｋｉｎｇ confirmed at Straße Hotel')
    assert search_names(roster.catalog,'booking')['agents']==['Owner']
    assert 'Ｂｏｏｋｉｎｇ' in search_names(roster.catalog,'booking')['candidates'][0]['matching_history']['text']


def test_lazy_getters_follow_isolation_override(tmp_path,monkeypatch):
    from server.services.execution.roster import get_agent_roster
    from server.services.execution.log_store import get_execution_agent_logs
    for directory in (tmp_path/'one',tmp_path/'two'):
        monkeypatch.setenv('OPENPOKE_DATA_DIR',str(directory))
        assert get_agent_roster().catalog.path.is_relative_to(directory)
        assert get_execution_agent_logs().catalog.path.is_relative_to(directory)


def test_rollback_export_and_hashed_journal_recovery(tmp_path):
    from server.services.execution.maintenance import export_legacy
    root=tmp_path/'source';roster=AgentRoster(root/'roster.json');roster.add_agent('Owner')
    logs=ExecutionAgentLogStore(root);logs.record_request('Owner','Violet booking')
    export_legacy(roster,logs,tmp_path/'export')
    assert (tmp_path/'export'/'owner.log').read_bytes()==logs._log_path('Owner').read_bytes()
    with pytest.raises(ValueError):export_legacy(roster,logs,tmp_path/'export')
    roster.add_agent('A B');roster.add_agent('A-B')
    with pytest.raises(ValueError,match='colliding'):export_legacy(roster,logs,tmp_path/'collision')
    # An explicit recovery from exported membership can rediscover hash-named logs.
    roster.export_json(root/'roster.json')
    roster.catalog.path.unlink()
    restored=AgentRoster(root/'roster.json');ExecutionAgentLogStore(root)
    assert search_names(restored.catalog,'violet')['agents']==['Owner']


def test_unsupported_version_rejected(tmp_path):
    roster=AgentRoster(tmp_path/'roster.json')
    with roster.catalog.connect() as db:db.execute("UPDATE metadata SET value='future' WHERE key='version'")
    with pytest.raises(RuntimeError,match='version'):AgentRoster(tmp_path/'roster.json')


def test_bulk_replacement_preserves_eligible_history(tmp_path):
    roster=AgentRoster(tmp_path/'roster.json');roster.add_agent('Owner')
    logs=ExecutionAgentLogStore(tmp_path);logs.record_request('Owner','Violet booking')
    roster.bulk_import(['Other','Owner'])
    assert search_names(roster.catalog,'Violet')['agents']==['Owner']
    assert select_candidates(roster.catalog,'Violet')[1]['initial_assignment']=='Violet booking'


def test_imports_do_not_migrate_or_open_roster(tmp_path):
    import os,subprocess,sys
    directory=tmp_path/'execution_agents';directory.mkdir()
    path=directory/'roster.json';path.write_text('["Existing owner"]')
    environment={**os.environ,'OPENPOKE_DATA_DIR':str(tmp_path)}
    subprocess.run([sys.executable,'-c','import server.agents.interaction_agent.runtime; import server.services.execution.catalog'],env=environment,check=True,capture_output=True)
    assert path.read_text()=='["Existing owner"]'
    assert not (directory/'agents.sqlite3').exists()


def test_interrupted_bulk_import_rolls_back_indexes_and_membership(tmp_path,monkeypatch):
    roster=AgentRoster(tmp_path/'roster.json');roster.add_agent('Original')
    original=roster.catalog._insert
    def fail(db,names):
        original(db,['Partial'])
        raise RuntimeError('interrupted bulk import')
    monkeypatch.setattr(roster.catalog,'_insert',fail)
    with pytest.raises(RuntimeError):roster.bulk_import(['Replacement'])
    assert roster.get_agents()==['Original']
    assert search_names(roster.catalog,'Original')['agents']==['Original']
    with roster.catalog.connect() as db:
        assert not db.execute("SELECT 1 FROM metadata WHERE key='bulk_mode'").fetchone()
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='agent_normalized'").fetchone()


def test_completed_migration_survives_backup_rename_failure(tmp_path,monkeypatch):
    path=tmp_path/'roster.json';path.write_text('["Owner"]')
    rename=Path.rename
    with monkeypatch.context() as context:
        def fail_backup(source,destination):
            if source==path:raise OSError('interrupted backup rename')
            return rename(source,destination)
        context.setattr(Path,'rename',fail_backup)
        with pytest.raises(OSError):AgentRoster(path)
    assert AgentRoster(path).get_agents()==['Owner']
    assert (tmp_path/'roster.legacy.json').exists()
