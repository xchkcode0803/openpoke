"""Continue a Gmail cohort after a verified pre-connection outage, without resampling."""
import json
from pathlib import Path
from types import SimpleNamespace


def dns_failure(record):
    return 'nodename nor servname provided' in record.get('judge_error', '')


async def resume_gmail(args, output, model, transport):
    from evals.agent_gmail.cases import select_cases
    from evals.agent_gmail.run import run, regrade
    from evals.agent_gmail.reporting import summarize
    metadata_path = output / 'comparison.json'
    metadata = json.loads(metadata_path.read_text())
    segments = metadata.get('gmail_segments', ['gmail'])
    records = {}
    for segment in segments:
        for path in (output / segment).glob('case-*.json'):
            record = json.loads(path.read_text())
            if record['case']['name'] in records:
                raise ValueError('Duplicate agent execution in cohort')
            records[record['case']['name']] = record
    # Only a diagnosed failure before DNS resolution may be reconciled as uncharged.
    for record in records.values():
        if any(c.get('error') or c.get('cancelled') for c in record['provider_calls']):
            raise ValueError('Agent request accounting needs manual reconciliation')
        if record.get('judge_error') and not dns_failure(record):
            raise ValueError('Judge accounting needs manual reconciliation')
    old = summarize(list(records.values()))
    spent = old['known_agent_cost'] + old['judge_known_cost']
    cap = min(args.budget, metadata['budget_usd'])
    spent += sum(json.loads((output / s / 'summary.json').read_text())['judge_known_cost'] for s in metadata.get('gmail_regrades', []))
    remaining = cap - spent
    if remaining <= 0:
        raise ValueError('Original cohort spending cap exhausted')
    missing = [c.name for c in select_cases('full') if c.name not in records]
    if missing:
        segment = f'gmail-continuation-{len(segments):02d}'
        code = await run(SimpleNamespace(suite='full', case=missing, interaction_model=model,
            execution_model=model, search_model=model, repetitions=1, budget=remaining,
            output=str(output / segment), turn_timeout=900, worker_timeout=600, transport=transport))
        segments.append(segment)
        metadata['gmail_segments'] = segments
        metadata.setdefault('interruptions', []).append({
            'reason': 'Laptop sleep caused DNS resolution failure before HTTP connection',
            'preserved_scenarios': len(records), 'new_agent_scenarios': len(missing),
            'prior_known_cost': spent, 'remaining_cap': remaining,
            'accounting': 'Failed DNS resolution did not reach provider; recorded successful judge calls retained.'})
        metadata_path.write_text(json.dumps(metadata, indent=2))
        if json.loads((output / segment / 'manifest.json').read_text())['status'] != 'complete':
            return 1
    # Regrade only the interrupted judge measurement; no agent or mailbox replay.
    failures = [name for name, r in records.items() if r.get('judge_error')]
    if failures and not metadata.get('gmail_regrades'):
        continuation_cost = sum(json.loads((output / s / 'summary.json').read_text()).get('known_agent_cost', 0)
                                + json.loads((output / s / 'summary.json').read_text()).get('judge_known_cost', 0)
                                for s in segments)
        target = output / 'gmail-regrade-01'
        await regrade(SimpleNamespace(regrade=str(output / 'gmail'), output=str(target),
                                     case=failures, budget=cap - continuation_cost))
        metadata['gmail_regrades'] = [target.name]
        metadata_path.write_text(json.dumps(metadata, indent=2))
    return 0
