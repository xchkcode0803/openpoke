"""Summarize preserved measurements without rerunning agents or judges."""
import argparse
from collections import Counter, defaultdict
import json
import hashlib
from pathlib import Path
import statistics

from .run import MODELS

COLLECTIONS = ("gmail", "routing")

EXPECTED = {'gmail': 40, 'routing': 99, 'inspection': 6, 'scale': 48, 'challenge': 36}


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def known_total(values):
    return sum(values) if all(isinstance(v, (int, float)) for v in values) else None


def routing(directory, collection):
    large = collection in {'scale', 'challenge'}
    folders = sorted((directory / 'live').glob('*')) if large else [directory]
    scenarios = defaultdict(list)
    unavailable, judge_usage, model_calls, timings, turns = set(), [], [], [], []
    outcomes = {}
    judge_unavailable = False
    for folder in folders:
        if large and (folder / 'outcome.json').exists():
            outcome = json.loads((folder / 'outcome.json').read_text())
            outcomes[folder.name] = outcome
        judge_usage.extend(rows(folder / 'judge_usage.jsonl'))
        for entry in rows(folder / 'unavailable.jsonl'):
            key = folder.name if large else entry['metadata']['case_name']
            unavailable.add(key)
            model_calls.extend(entry['metadata'].get('model_calls', []))
        judge_errors = rows(folder / 'judge_errors.jsonl')
        judge_unavailable |= bool(judge_errors)
        for item in rows(folder / 'turns.jsonl'):
            result = item['result']
            metadata = result['metadata']
            key = folder.name if large else metadata['case_name']
            turns.append(item)
            scenarios[key].append(item)
            model_calls.extend(metadata.get('model_calls', []))
            timings.extend(metadata.get('provider_timing', []))
            if any(error['case'] == result.get('name') for error in judge_errors):
                unavailable.add(key)
    details = []
    for key in sorted(set(scenarios) | unavailable | set(outcomes)):
        items = scenarios[key]
        failed = [m for item in items for m in item['metrics'] if m.get('score') != 1]
        external = outcomes.get(key, {})
        if key in unavailable or external.get('status') not in {None, 'passed', 'failed'}:
            status = 'unavailable'
        elif failed or external.get('status') == 'failed':
            status = 'agent_failure'
        else:
            status = 'pass'
        details.append({'case': key, 'outcome': status,
                        'failures': failed, 'external_outcome': external or None})
    charges = [c.get('response', {}).get('usage', {}).get('cost') for c in model_calls]
    judge_charges = [j.get('cost') for j in judge_usage]
    ledger = json.loads((directory / 'spend.json').read_text()) if (directory / 'spend.json').exists() else None
    summary = {
        'scenarios': len(details), 'expected_scenarios': EXPECTED[collection],
        'outcomes': dict(Counter(d['outcome'] for d in details)), 'turns': len(turns),
        'routing_passed_turns': sum(m['score'] == 1 for t in turns for m in t['metrics'] if m['name'] == 'RoutingCorrectnessMetric'),
        'metric_counts': {name: dict(Counter(str(m['score']) for t in turns for m in t['metrics'] if m['name'] == name))
                          for name in {m['name'] for t in turns for m in t['metrics']}},
        'agent_cost': known_total(charges), 'judge_cost': None if judge_unavailable else known_total(judge_charges),
        'model_calls': len(model_calls),
        'returned_models': dict(Counter(c.get('response', {}).get('model', 'unknown') for c in model_calls)),
        'input_tokens': known_total([c.get('response', {}).get('usage', {}).get('prompt_tokens') for c in model_calls]),
        'output_tokens': known_total([c.get('response', {}).get('usage', {}).get('completion_tokens') for c in model_calls]),
        'latency_median': statistics.median([t['result']['completion_time'] for t in turns]) if turns else None,
        'semantic_measured_turns': sum(m['name'] == 'InstructionFidelityMetric' and 'no semantic requirement' not in m.get('reason', '').lower() for t in turns for m in t['metrics']),
        'discovery_calls': sum(t['result']['metadata'].get('discovery_call_count', 0) for t in turns),
        'timing_totals': {k: sum(t.get(k, 0) for t in timings) for k in ('request_seconds', 'pacing_seconds', 'retry_wait_seconds')},
        'ledger_charges': sum(float(r['charged']) for r in ledger['requests']) if ledger else None,
        'unresolved_reservations': [r['id'] for r in ledger['requests'] if r['status'] in {'reserved', 'unresolved'}] if ledger else [],
        'cases': details,
        'initial_contracts': {t['result']['metadata']['case_name']: hashlib.sha256(json.dumps({k: t['result']['metadata']['model_calls'][0][k] for k in ('system', 'tools')}, sort_keys=True).encode()).hexdigest() for t in turns if t['result']['metadata'].get('turn_index') == 0 and t['result']['metadata'].get('model_calls')},
    }
    passed = summary['outcomes'].get('pass', 0)
    summary['cost_per_success'] = summary['agent_cost'] / passed if passed and summary['agent_cost'] is not None else None
    return summary


def gmail(directory):
    from evals.agent_gmail.reporting import summarize
    metadata = json.loads((directory / 'comparison.json').read_text())
    segments = metadata.get('gmail_segments', ['gmail'])
    indexed = {}
    superseded = {(r['segment'], r['case']) for r in metadata.get('superseded_agent_cases', [])}
    interrupted_calls = []
    judge_ledger = []
    for segment in segments:
        source = directory / segment
        judge_ledger.extend(rows(source / 'judge_usage.jsonl'))
        for path in sorted(source.glob('case-*.json')):
            record = json.loads(path.read_text())
            if (segment, record['case']['name']) in superseded:
                interrupted_calls.extend(record['provider_calls'])
                continue
            if record['case']['name'] in indexed:
                raise ValueError('Duplicate agent execution in Gmail cohort')
            indexed[record['case']['name']] = record
    for segment in metadata.get('gmail_regrades', []):
        source = directory / segment
        judge_ledger.extend(rows(source / 'judge_usage.jsonl'))
        for path in source.glob('case-*.json'):
            record = json.loads(path.read_text())
            original = indexed[record['case']['name']]
            assert original['provider_calls'] == record['provider_calls']
            indexed[record['case']['name']] = record
    records = list(indexed.values())
    summary = summarize(records)
    summary['judge_known_cost'] = sum(j.get('cost') or 0 for j in judge_ledger)
    summary['judge_cost_complete'] &= all(isinstance(j.get('cost'), (int, float)) for j in judge_ledger)
    calls = [c for r in records for c in r['provider_calls']]
    from evals.agent_gmail.usage import effective_cost
    overhead = sum(effective_cost(c.get('usage', {})) or 0 for c in interrupted_calls)
    summary['interrupted_agent_cost'] = overhead
    summary['operational_agent_cost'] = summary['agent_cost'] + overhead if summary['agent_cost'] is not None else None
    calls += interrupted_calls
    timings = [a for c in calls for a in c['attempts']]
    summary.update(expected_scenarios=40, judge_cost=summary['judge_known_cost'] if summary['judge_cost_complete'] else None,
        returned_models=dict(Counter(c.get('returned_model', 'unknown') for c in calls)),
        timing_totals={k: sum(t.get(k, 0) for t in timings) for k in ('request_seconds', 'pacing_seconds', 'retry_wait_seconds')},
        cases=[{'case': r['case']['name'], 'outcome': r['outcome'],
                'failures': r['deterministic']['failures'],
                'semantic_failures': [a for a in r.get('semantic', {}).get('answers', []) if not a['verdict']],
                'judge_error': r.get('judge_error'), 'unsupported': r.get('unsupported')} for r in records])
    return summary


def collect(root):
    result = {}
    for model in MODELS:
        result[model] = {}
        for collection in COLLECTIONS:
            if model == 'sonnet' and collection == 'routing':
                result[model][collection] = json.loads((Path(__file__).parent / 'baselines' / 'sonnet_routing.json').read_text())
                continue
            directory = root / model / collection
            manifest = directory / 'comparison.json'
            if not manifest.exists():
                continue
            metadata = json.loads(manifest.read_text())
            if metadata['status'] != 'finished':
                result[model][collection] = {'status': metadata['status'], 'manifest': {k: v for k, v in metadata.items() if k not in {'models', 'source_hashes'}}}
                continue
            summary = gmail(directory) if collection == 'gmail' else routing(directory, collection)
            compact = {k: v for k, v in metadata.items() if k not in {'models', 'source_hashes'}}
            compact['source_manifest_sha256'] = hashlib.sha256(json.dumps(metadata['source_hashes'], sort_keys=True).encode()).hexdigest()
            summary.update(manifest=compact, artifacts=str(directory.resolve()),
                           not_run=max(0, EXPECTED[collection] - summary['scenarios']))
            result[model][collection] = summary
    audit = root / 'audit_notes.json'
    result['audit_notes'] = json.loads(audit.read_text()) if audit.exists() else []
    result['paired'] = {}
    for collection in COLLECTIONS:
        left, right = result['sonnet'].get(collection), result['gemini'].get(collection)
        if not left or not right or 'cases' not in left or 'cases' not in right:
            continue
        if left['manifest'].get('historical'):
            if left['initial_contracts'] != right['initial_contracts']:
                raise ValueError('Published routing baseline prompt/schema contracts differ from candidate')
        elif left['manifest']['source_manifest_sha256'] != right['manifest']['source_manifest_sha256']:
            raise ValueError(f'Cannot compare changed production/eval sources: {collection}')
        baseline = {r['case']: r['outcome'] for r in left['cases']}
        candidate = {r['case']: r['outcome'] for r in right['cases']}
        common = sorted(baseline.keys() & candidate.keys())
        result['paired'][collection] = {
            'matched': len(common),
            'regressions': [k for k in common if baseline[k] == 'pass' and candidate[k] == 'agent_failure'],
            'improvements': [k for k in common if baseline[k] == 'agent_failure' and candidate[k] == 'pass'],
            'unavailable_pairs': [k for k in common if 'unavailable' in (baseline[k], candidate[k])],
            'unmatched': sorted(baseline.keys() ^ candidate.keys()),
        }
    return result


def money(value):
    return f'${value:.6f}' if value is not None else 'unknown'


def markdown(data):
    text = ['# Agent evaluation report', '',
        'Sonnet 4 is the baseline; Gemini Flash is the candidate. Gmail uses the completed 40-case Sonnet run; routing uses the published 95/99 Sonnet result in [agent roster search results](agent_roster_search_results.md). '
        'Cases, expected outcomes, production prompts, tool schemas, and graders are unchanged between candidates.', '',
        '| Collection | Model | Pass / expected | Failed | Unavailable | Not run | Agent cost | Judge cost | Agent cost / success |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for collection in COLLECTIONS:
        for model in MODELS:
            s = data[model].get(collection)
            if not s or 'outcomes' not in s:
                status = s.get('status', 'not run') if s else 'not run'
                text.append(f'| {collection} | {model} | {status} | — | — | — | — | — | — |')
                continue
            o = s['outcomes']
            text.append(f"| {collection} | {model} | {o.get('pass', 0)}/{s['expected_scenarios']} | {o.get('agent_failure', 0)} | {o.get('unavailable', 0)} | {s['not_run']} | {money(s['agent_cost'])} | {money(s['judge_cost'])} | {money(s['cost_per_success'])} |")
    if any(not data[m].get(c) or data[m][c].get('scenarios', 0) != EXPECTED[c] for m in MODELS for c in COLLECTIONS):
        text[2:2] = ['**Incomplete comparison.** Some collections have not finished. Production model defaults have not been switched.', '']
    for collection, pairs in data.get('paired', {}).items():
        text += ['', f"{collection}: {len(pairs['improvements'])} improvements, {len(pairs['regressions'])} regressions, {len(pairs['unavailable_pairs'])} unavailable pairs."]
    if data.get('audit_notes'):
        text += ['', '## Audit qualifications', '', 'Primary scores remain frozen. These notes distinguish confirmed behavior from questionable judgments and coverage assumptions.', '']
        for note in data['audit_notes']:
            text += [f"- **{note['model']} / {note['case']}: {note['classification']}.** {note['evidence']} {note['treatment']}"]
    text += ['', '## Latency', '',
        'Cumulative HTTP/wait totals can overlap for concurrent Gmail workers. The median unit is a complete Gmail scenario or one routing turn, excluding judging.', '',
        '| Collection | Model | Median unit, seconds | Cumulative HTTP | Fixed pacing | Retry waits |',
        '|---|---|---:|---:|---:|---:|']
    for collection in COLLECTIONS:
        for model in MODELS:
            s = data[model].get(collection)
            if not s or 'outcomes' not in s:
                continue
            t = s['timing_totals']
            median = 'unknown' if s.get('latency_median') is None else f"{s['latency_median']:.2f}"
            text.append(f"| {collection} | {model} | {median} | {t['request_seconds']:.2f} | {t['pacing_seconds']:.2f} | {t['retry_wait_seconds']:.2f} |")
    text += ['', '## Interpretation and controls', '',
        '- Scores use one completed run per case. These authored cases are not an estimate of population reliability. Gmail provider-interrupted work is retained separately in operational costs.',
        '- Gmail executes real workers and nested email search against local Vercel Emulate 0.11.2. Routing uses the existing stub workers; it measures routing, not task execution.',
        '- Sonnet has 4.1-second fixed pacing; Gemini has no fixed pacing. Both retain bounded reactive rate-limit retries. HTTP duration includes provider/network time. Wall-clock savings include the removal of deliberate waiting.',
        '- Gmail uses equal 600-second worker and 900-second turn transport allowances. Production iteration limits remain unchanged; these measurements do not establish compliance with the shorter production worker timeout.',
        '- Judges remain Jev 1.13 with Sonnet 4 fallback for both candidates. Semantic verdicts cannot override deterministic Gmail failures.',
        '- Contacts and uploaded attachments remain outside Gmail coverage. Correct preview text without a required saved mailbox draft fails draft-state expectations.',
        '- Earlier Gmail measurements predate the merged routing implementation and are not used in this comparison. The original Gmail branch and raw traces preserve that history.',
        '- Summarization and classification have separate focused sanity checks, not comprehensive coverage from these benchmarks.', '',
        '## Failure evidence and artifacts', '']
    for model in MODELS:
        for collection, s in data[model].items():
            if 'outcomes' not in s:
                text.append(f'- {model}/{collection}: measurement {s["status"]}.')
                continue
            text += [f'### {model}: {collection}', '', f'Artifacts: `{s["artifacts"]}`.', '',
                     f'Returned models: `{s["returned_models"]}`. Timing totals: `{s["timing_totals"]}`.', '']
            if collection == 'gmail':
                text += [f'Known agent charges: {money(s["known_agent_cost"])}; known judge charges: {money(s["judge_known_cost"])}. Incomplete/unknown totals are not treated as zero.', '', f'Unauthorized sends: {s["unauthorized_sends"]}; target/content failures: {s["wrong_targets_or_content"]}; extra-transmission checks failed: {s["extra_transmissions"]}; reporting checks failed: {s["reporting_failures"]}.', '']
            for case in s['cases']:
                if case['outcome'] != 'pass':
                    reasons = [f.get('name', f.get('reason', str(f))) for f in case['failures']]
                    reasons += sorted({f"semantic {a.get('category', 'check')}" for a in case.get('semantic_failures', [])})
                    text.append(f'- `{case["case"]}`: {case["outcome"]}; ' + ('; '.join(reasons) or 'see saved grading evidence'))
            text.append('')
    return '\n'.join(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.deepeval/comparison-main-v1'))
    parser.add_argument('--output', type=Path, default=Path('docs/agent_eval_report'))
    args = parser.parse_args()
    data = collect(args.root)
    args.output.with_suffix('.json').write_text(json.dumps(data, indent=2) + '\n')
    args.output.with_suffix('.md').write_text(markdown(data) + '\n')


if __name__ == '__main__':
    main()
