import json

from .report import routing


def write(path, records):
    path.write_text(''.join(json.dumps(r) + '\n' for r in records))


def turn(case, score=1, cost=.1):
    return {'result': {'name': case + '[0]', 'completion_time': 2,
        'metadata': {'case_name': case, 'model_calls': [{'response': {'model': 'candidate',
            'usage': {'cost': cost, 'prompt_tokens': 10, 'completion_tokens': 5}}}],
            'provider_timing': [{'pacing_seconds': 1}] }},
        'metrics': [{'name': 'RoutingCorrectnessMetric', 'score': score, 'reason': 'test'}]}


def test_report_counts_scenarios_not_turns_and_preserves_missing_cost(tmp_path):
    write(tmp_path / 'turns.jsonl', [turn('first'), turn('first', 0), turn('second', cost=None)])
    result = routing(tmp_path, 'routing')
    assert result['scenarios'] == 2
    assert result['outcomes'] == {'agent_failure': 1, 'pass': 1}
    assert result['agent_cost'] is None
    assert result['cost_per_success'] is None
    assert result['routing_passed_turns'] == 2


def test_judge_outage_not_reported_as_candidate_failure(tmp_path):
    write(tmp_path / 'turns.jsonl', [turn('first', 0)])
    write(tmp_path / 'judge_errors.jsonl', [{'case': 'first[0]', 'error': 'outage'}])
    result = routing(tmp_path, 'inspection')
    assert result['outcomes'] == {'unavailable': 1}


def test_campaign_resource_failure_has_no_fake_pass(tmp_path):
    folder = tmp_path / 'live' / 'scale_00_1000000'
    folder.mkdir(parents=True)
    (folder / 'outcome.json').write_text(json.dumps({'status': 'resource_limit', 'reason': 'memory'}))
    result = routing(tmp_path, 'scale')
    assert result['scenarios'] == 1
    assert result['outcomes'] == {'unavailable': 1}
