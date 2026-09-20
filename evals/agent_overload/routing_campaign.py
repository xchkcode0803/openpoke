"""Opt-in child-process supervision and artifacts for large routing fixtures."""
import json
import hashlib
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from .routing_population import Variant, materialize


def campaign_dir():
    return Path(os.getenv('EVAL_CAMPAIGN_DIR', '.deepeval/campaigns/difficult-routing-v1')).resolve()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, default=str))
    temporary.replace(path)


def memory_bytes(pid):
    result = subprocess.run(['ps', '-o', 'rss=', '-p', str(pid)], capture_output=True, text=True)
    return int(result.stdout.strip() or 0) * 1024


def supervise(command, destination, *, seconds=300, memory_limit=4 * 1024**3):
    started = time.monotonic()
    peak = 0
    reason = None
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / 'process.log').open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                peak = max(peak, memory_bytes(process.pid))
                if peak > memory_limit:
                    reason = 'memory_limit'
                elif time.monotonic() - started > seconds:
                    reason = 'wall_clock_limit'
                if reason:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    break
                time.sleep(0.1)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    measurement = {'returncode': process.returncode, 'resource_failure': reason,
                   'sampled_peak_rss_bytes': peak, 'wall_seconds': time.monotonic() - started}
    write_json(destination / 'process.json', measurement)
    return measurement


def ensure_manifest(root):
    from . import routing_population, challenge_cases
    sources = {}
    for module in (routing_population, challenge_cases):
        path = Path(module.__file__)
        sources[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = root / 'source_manifest.json'
    if manifest.exists() and json.loads(manifest.read_text()) != sources:
        raise ValueError('Fixture source changed; do not mix results in an existing campaign')
    if not manifest.exists():
        write_json(manifest, sources)


def run_variant(variant, mode):
    root = campaign_dir()
    ensure_manifest(root)
    destination = root / mode / variant.key
    if (destination / 'outcome.json').exists():
        return json.loads((destination / 'outcome.json').read_text())
    if mode == 'live':
        if os.getenv('RUN_LIVE_EVALS') != '1':
            raise RuntimeError('Set RUN_LIVE_EVALS=1 for paid execution')
        preflight = root / 'capacity' / variant.key / 'outcome.json'
        if not preflight.exists():
            run_variant(variant, 'capacity')
        preflight_result = json.loads(preflight.read_text())
        if preflight_result['status'] != 'completed':
            result = {'variant': variant.key, 'status': 'not_run', 'reason': 'failed_preflight'}
            write_json(destination / 'outcome.json', result)
            return result
    command = [sys.executable, '-m', 'evals.agent_overload.routing_campaign', mode,
               variant.kind, str(variant.index), str(variant.size)]
    measurement = supervise(command, destination)
    outcome = destination / 'outcome.json'
    if measurement['resource_failure']:
        write_json(outcome, {'variant': variant.key, 'status': 'resource_limit', **measurement})
    elif not outcome.exists():
        write_json(outcome, {'variant': variant.key, 'status': 'harness_error', **measurement})
    return json.loads(outcome.read_text())


def prepare(variant, directory):
    from .harness import _reset_services, _seed_case
    from server.agents.interaction_agent import agent, discovery
    started = time.perf_counter()
    case, history, metadata = materialize(variant)
    generation = time.perf_counter() - started
    roster, conversation, memory, logs = _reset_services(directory)
    started = time.perf_counter()
    _seed_case(case, roster, conversation, memory)
    for name, entries in history.items():
        for tag, text in entries:
            if tag == 'agent_request':
                logs.record_request(name, text)
            else:
                logs.record_agent_response(name, text)
    persistence = time.perf_counter() - started
    started = time.perf_counter()
    roster.load()
    loading = time.perf_counter() - started
    transcript = conversation.load_transcript()
    ranking_time = []
    original = discovery.select_candidates

    def timed_candidates(*args, **kwargs):
        start = time.perf_counter()
        value = original(*args, **kwargs)
        ranking_time.append(time.perf_counter() - start)
        return value

    started = time.perf_counter()
    with patch.object(agent, 'get_agent_roster', return_value=roster), patch.object(agent, 'get_execution_agent_logs', return_value=logs), patch.object(agent, 'select_candidates', timed_candidates):
        messages = agent.prepare_message_with_history(case.turns[0].message, transcript)
    construction = time.perf_counter() - started
    candidates = json.loads(re.search(r'<active_agents[^>]*>\s*(.*?)\s*</active_agents>', messages[0]['content'], re.S).group(1))
    owners = {item['name'] for item in candidates}
    coverage = {item.task_key: bool(owners.intersection(item.acceptable_agent_names))
                for item in case.turns[0].delegations if item.route == 'reuse'}
    started = time.perf_counter()
    search = discovery.search_names(list(case.initial_agents), case.turns[0].message)
    search_time = time.perf_counter() - started
    feasibility = []
    if variant.kind == 'challenge':
        from .challenge_cases import challenges
        known = set(owners)
        known.update(name for name in case.initial_agents if name in transcript)
        for tool, arguments in challenges()[variant.index].discovery:
            if tool == 'search_agents':
                value = discovery.search_names(case.initial_agents, **arguments)
                known.update(value['agents'])
            else:
                if arguments['agent_name'] not in known:
                    raise ValueError('Fixture requires guessing an inaccessible owner name')
                value = discovery.inspect_history(case.initial_agents, logs=logs, **arguments)
                # Handoff references can introduce an exact owner name.
                historical_text = json.dumps(value)
                for name in case.initial_agents:
                    if name in historical_text:
                        known.add(name)
            feasibility.append({'tool': tool, 'arguments': arguments, 'result': value})
        for expected in case.turns[0].delegations:
            if expected.route == 'reuse' and not known.intersection(expected.acceptable_agent_names):
                raise ValueError('Fixture owner inaccessible within the scripted discovery path')
    prompt = json.dumps({'system': agent.build_system_prompt(), 'messages': messages}, ensure_ascii=False)
    measurements = {**metadata, 'generation_seconds': generation, 'persistence_seconds': persistence,
        'roster_load_seconds': loading, 'candidate_selection_seconds': sum(ranking_time),
        'prompt_construction_seconds': construction, 'search_seconds': search_time,
        'initial_candidates': candidates, 'initial_owner_coverage': coverage,
        'all_owners_present': all(coverage.values()) if coverage else None,
        'search': search, 'feasible_discovery_path': feasibility, 'prompt_bytes_without_tool_schemas': len(prompt.encode()),
        'estimated_input_tokens_without_tool_schemas': len(prompt.encode()) // 3 + 1,
        'estimate_method': 'UTF-8 bytes / 3; not a tokenizer or provider measurement',
        'platform': platform.platform(), 'python': platform.python_version(),
        'machine_memory_bytes': subprocess.run(['sysctl', '-n', 'hw.memsize'], capture_output=True, text=True).stdout.strip() if sys.platform == 'darwin' else None}
    return case, history, measurements


def child(variant, mode):
    root = campaign_dir()
    destination = root / mode / variant.key
    # Set isolation before importing production service modules.
    with tempfile.TemporaryDirectory(prefix='openpoke-routing-capacity-') as directory:
        with patch.dict(os.environ, {'OPENPOKE_DATA_DIR': directory}):
            try:
                if mode == 'capacity':
                    case, history, measurements = prepare(variant, Path(directory))
                    write_json(destination / 'fixture.json', measurements)
                    write_json(destination / 'outcome.json', {'variant': variant.key, 'status': 'completed'})
                    return
                # Preflight already exercised loading, ranking, search, and the
                # feasible discovery path. Do not repeat that offline work before
                # every paid run; the real runtime below still uses real stores.
                started = time.perf_counter()
                case, history, manifest = materialize(variant)
                measurements = json.loads((root / 'capacity' / variant.key / 'fixture.json').read_text())
                if any(measurements[key] != value for key, value in manifest.items()):
                    raise ValueError('Live fixture differs from its capacity preflight')
                measurements['live_generation_seconds'] = time.perf_counter() - started
                write_json(destination / 'fixture.json', measurements)
                from . import provider
                from .campaign_budget import CampaignBudget, BudgetStopped
                from .harness import evaluate_live_case
                budget = CampaignBudget(root, os.getenv('EVAL_MAX_SPEND_USD', '10'), variant.key)
                prices = budget.prices
                with patch.object(provider, '_artifact_dir', destination), patch.object(provider, 'request_budget', budget), patch.dict(provider.context_limits, {provider.MODEL: prices[provider.MODEL]['context_length']}):
                    try:
                        evaluate_live_case(case, history)
                        result = {'status': 'passed'}
                    except AssertionError as exc:
                        result = {'status': 'failed', 'details': str(exc)}
                    except BudgetStopped as exc:
                        result = {'status': 'not_run', 'reason': 'budget', 'details': str(exc)}
                errors = {}
                for filename in ('unavailable.jsonl', 'judge_errors.jsonl'):
                    path = destination / filename
                    if path.exists():
                        errors[filename] = [json.loads(line) for line in path.read_text().splitlines()]
                if errors:
                    result.update(status='unavailable', errors=errors)
                write_json(destination / 'outcome.json', {'variant': variant.key, **result})
            except Exception as exc:
                write_json(destination / 'outcome.json', {'variant': variant.key, 'status': 'harness_error', 'details': str(exc)})
                raise


if __name__ == '__main__':
    child(Variant(sys.argv[2], int(sys.argv[3]), int(sys.argv[4])), sys.argv[1])
