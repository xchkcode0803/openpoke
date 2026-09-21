"""Continue interrupted Gmail cohorts without resampling completed agent cases."""
import json
from types import SimpleNamespace


def rejected(record):
    """402 is an explicit pre-generation credit rejection, not an unknown charge."""
    return any(c.get('error', '').startswith('OpenRouter HTTP 402:') for c in record['provider_calls'])


def dns_failure(record):
    return 'nodename nor servname provided' in (record.get('judge_error') or '')


async def resume_gmail(args, output, model, transport):
    from evals.agent_gmail.cases import select_cases
    from evals.agent_gmail.run import run, regrade
    from evals.agent_gmail.reporting import summarize
    metadata_path = output / 'comparison.json'
    metadata = json.loads(metadata_path.read_text())
    segments = metadata.get('gmail_segments', ['gmail'])
    records, source_for, all_records = {}, {}, []
    for segment in segments:
        for path in (output / segment).glob('case-*.json'):
            record = json.loads(path.read_text())
            name = record['case']['name']
            if name in records and not rejected(records[name]):
                raise ValueError('Duplicate completed agent execution in cohort')
            records[name], source_for[name] = record, segment
            all_records.append(record)
    for record in all_records:
        if any((c.get('error') and not c['error'].startswith('OpenRouter HTTP 402:')) or c.get('cancelled')
               for c in record['provider_calls']):
            raise ValueError('Agent request accounting needs manual reconciliation')
        if record.get('judge_error') and not (dns_failure(record) or rejected(record)):
            raise ValueError('Judge accounting needs manual reconciliation')
    old = summarize(all_records)
    spent = old['known_agent_cost'] + old['judge_known_cost']
    cap = min(args.budget, metadata['budget_usd'])
    spent += sum(json.loads((output / s / 'summary.json').read_text())['judge_known_cost'] for s in metadata.get('gmail_regrades', []))
    remaining = cap - spent
    if remaining <= 0:
        raise ValueError('Original cohort spending cap exhausted')
    retries = [name for name, r in records.items() if rejected(r)]
    missing = [c.name for c in select_cases('full') if c.name not in records or c.name in retries]
    if missing:
        segment = f'gmail-continuation-{len(segments):02d}'
        code = await run(SimpleNamespace(suite='full', case=missing, interaction_model=model,
            execution_model=model, search_model=model, repetitions=1, budget=remaining,
            output=str(output / segment), turn_timeout=900, worker_timeout=600, transport=transport))
        segments.append(segment)
        metadata['gmail_segments'] = segments
        metadata.setdefault('interruptions', []).append({
            'reason': 'Pre-connection DNS outage or explicit provider credit rejection',
            'preserved_completed_scenarios': len(records) - len(retries),
            'scheduled_scenarios': missing, 'provider_interrupted_cases_restarted': retries,
            'prior_known_cost': spent, 'remaining_cap': remaining,
            'accounting': 'DNS and HTTP 402 rejected requests did not generate; all earlier successful calls retained.'})
        for name in retries:
            metadata.setdefault('superseded_agent_cases', []).append({'case': name, 'segment': source_for[name],
                'reason': 'Provider HTTP 402 interrupted this case; earlier successful calls remain charged.'})
        metadata_path.write_text(json.dumps(metadata, indent=2))
        if json.loads((output / segment / 'manifest.json').read_text())['status'] != 'complete':
            return 1
    # Regrade DNS-interrupted judge evidence without replaying agents/mailboxes.
    already = set()
    for segment in metadata.get('gmail_regrades', []):
        already.update(json.loads(p.read_text())['case']['name'] for p in (output / segment).glob('case-*.json'))
    groups = {}
    for name, record in records.items():
        if dns_failure(record) and name not in already:
            groups.setdefault(source_for[name], []).append(name)
    for source, failures in groups.items():
        charged = sum(json.loads((output / s / 'summary.json').read_text()).get('known_agent_cost', 0)
                      + json.loads((output / s / 'summary.json').read_text()).get('judge_known_cost', 0)
                      for s in segments)
        charged += sum(json.loads((output / s / 'summary.json').read_text())['judge_known_cost'] for s in metadata.get('gmail_regrades', []))
        if charged >= cap:
            raise ValueError('Original cohort spending cap exhausted before regrading')
        target = output / f"gmail-regrade-{len(metadata.get('gmail_regrades', [])) + 1:02d}"
        await regrade(SimpleNamespace(regrade=str(output / source), output=str(target), case=failures, budget=cap - charged))
        metadata.setdefault('gmail_regrades', []).append(target.name)
        metadata_path.write_text(json.dumps(metadata, indent=2))
    return 0
