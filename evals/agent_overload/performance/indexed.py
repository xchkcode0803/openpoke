"""Separate cold migration/build and fresh-process warm retrieval measurements."""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
from ..cases.population import Variant, materialize, SCALE_SIZES
from ..runtime.campaign import supervise, write_json


_run_root = None


def root_dir():
    """Give each cold/warm measurement an independent artifact directory."""
    global _run_root
    if _run_root is None:
        base = Path(os.getenv('EVAL_ARTIFACT_DIR', '.deepeval/runs')).resolve()
        _run_root = base / ('indexed-' + time.strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8])
    return _run_root


def fresh_lookup(directory,query,history):
    os.environ['OPENPOKE_DATA_DIR']=str(directory)
    from server.services.execution.roster import AgentRoster
    from server.agents.interaction_agent.discovery import select_candidates,search_names
    started=time.perf_counter();roster=AgentRoster(Path(directory)/'execution_agents'/'roster.json')
    opened=time.perf_counter()-started
    timings=[]
    for _ in range(3):
        started=time.perf_counter();candidates=select_candidates(roster.catalog,query,history)
        selection=time.perf_counter()-started
        started=time.perf_counter();search_names(roster.catalog,query)
        timings.append({'selection_seconds':selection,'search_seconds':time.perf_counter()-started})
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)
    return {'fresh_open_seconds':opened,'warm_queries':timings,'fresh_process_peak_rss_bytes':peak,'candidates':candidates}


def measure(size, directory, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='openpoke-index-child-', dir=directory) as child_directory:
        directory = child_directory
        os.environ['OPENPOKE_DATA_DIR']=directory
        from server.services.execution.roster import AgentRoster
        from server.services.execution.log_store import ExecutionAgentLogStore
        from server.agents.interaction_agent.discovery import inspect_history
        case,_,manifest=materialize(Variant('scale',0,size))
        path=Path(directory)/'execution_agents'/'roster.json';path.parent.mkdir()
        started=time.perf_counter()
        with path.open('w') as stream:json.dump(list(case.initial_agents),stream)
        serialized=time.perf_counter()-started
        started=time.perf_counter();roster=AgentRoster(path);build=time.perf_counter()-started
        database_bytes=roster.catalog.path.stat().st_size
        # Drop generated names before measuring warm work in a fresh process.
        query=case.turns[0].message;history='\n'.join(text for _,text in case.initial_conversation)
        fresh_directory=destination/'fresh'
        measured=fresh_directory/'measurements.json'
        state=supervise([sys.executable,'-m','evals.agent_overload.performance.indexed','lookup',directory,query,history,str(measured)],fresh_directory,seconds=300,new_session=False)
        if state['resource_failure'] or state['returncode']:
            raise RuntimeError(f'Fresh-process lookup failed: {state}')
        measurements=json.loads(measured.read_text())
        started=time.perf_counter();roster.add_agent('Performance measurement owner');insert=time.perf_counter()-started
        logs=ExecutionAgentLogStore(path.parent)
        started=time.perf_counter();logs.record_request('Performance measurement owner','Record an incremental assignment for measurement.');append=time.perf_counter()-started
        started=time.perf_counter();inspect_history(roster.catalog,'Performance measurement owner',logs);inspection=time.perf_counter()-started
        write_json(destination/'measurements.json',{**manifest,**measurements,'legacy_serialization_seconds':serialized,
            'migration_and_build_seconds':build,'index_bytes':database_bytes,'insert_seconds':insert,'append_seconds':append,'inspection_seconds':inspection})


def run_measurement(size):
    destination=root_dir()/'performance'/str(size)
    with tempfile.TemporaryDirectory(prefix='openpoke-index-build-') as directory:
        state=supervise([sys.executable,'-m','evals.agent_overload.performance.indexed','build',str(size),directory,str(destination)],destination,seconds=900)
    if state['resource_failure'] or not (destination/'measurements.json').exists():return {'failure':state}
    return json.loads((destination/'measurements.json').read_text())


if __name__=='__main__':
    if sys.argv[1]=='lookup':
        write_json(Path(sys.argv[5]),fresh_lookup(sys.argv[2],sys.argv[3],sys.argv[4]))
    else:
        measure(int(sys.argv[2]), sys.argv[3], sys.argv[4])
