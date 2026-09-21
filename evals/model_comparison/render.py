"""Render collected measurements without reading artifacts or running models."""
from evals.shared.models import MODELS
from .collections import REPORT_COLLECTIONS as COLLECTIONS, EXPECTED


def money(value):
    return f'${value:.6f}' if value is not None else 'unknown'


def markdown(data):
    text = ['# Agent evaluation report', '',
        'Sonnet 4 is the baseline; Gemini Flash is the candidate. Gmail uses the completed 40-case Sonnet run; routing uses the published 95/99 Sonnet result in [committed routing baseline](../../../evals/model_comparison/baselines/sonnet_routing.json). '
        'Cases, expected outcomes, production prompts, tool schemas, and graders are unchanged between candidates.', '',
        '| Collection | Model | Pass / expected | Failed | Unavailable | Not run | Agent inference cost | Judge cost | Inference cost / success |',
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
    text += ['', 'Agent inference cost includes provider-reported BYOK upstream estimates. Gemini uses the configured BYOK credits; its OpenRouter agent charges are reported separately below. These estimates are not a new cash invoice.', '']
    if any(not data[m].get(c) or data[m][c].get('scenarios', 0) != EXPECTED[c] for m in MODELS for c in COLLECTIONS):
        text[2:2] = ['**Incomplete comparison.** Some collections have not finished. Production model defaults have not been switched.', '']
    for collection, pairs in data.get('paired', {}).items():
        text += ['', f"{collection}: {len(pairs['improvements'])} improvements, {len(pairs['regressions'])} regressions, {len(pairs['unavailable_pairs'])} unavailable pairs."]
    if all('families' in data[m].get('gmail', {}) for m in MODELS):
        text += ['', '## Gmail families', '', '| Family | Sonnet pass / total | Gemini pass / total | Gemini unavailable |', '|---|---:|---:|---:|']
        for family, left in sorted(data['sonnet']['gmail']['families'].items()):
            right = data['gemini']['gmail']['families'][family]
            text.append(f"| {family} | {left['pass']}/{sum(left.values())} | {right['pass']}/{sum(right.values())} | {right['unavailable']} |")
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
                     f"OpenRouter agent charges: {money(s.get('agent_openrouter_charges'))}; BYOK upstream estimate: {money(s.get('upstream_inference_estimate'))}.", '',
                     f'Returned models: `{s["returned_models"]}`. Timing totals: `{s["timing_totals"]}`.', '']
            if collection == 'gmail':
                text += [f'Known agent charges: {money(s["known_agent_cost"])}; known judge charges: {money(s["judge_known_cost"])}. Incomplete/unknown totals are not treated as zero.', '', f'Unauthorized sends: {s["unauthorized_sends"]}; target/content failures: {s["wrong_targets_or_content"]}; extra-transmission checks failed: {s["extra_transmissions"]}; reporting checks failed: {s["reporting_failures"]}.', '']
            if collection == 'gmail' and s.get('interrupted_agent_cost'):
                text += [f"Operational agent charges including provider-interrupted work: {money(s['operational_agent_cost'])}; interruption overhead: {money(s['interrupted_agent_cost'])}.", '']
            for case in s['cases']:
                if case['outcome'] != 'pass':
                    reasons = [f.get('name', f.get('reason', str(f))) for f in case['failures']]
                    reasons += sorted({f"semantic {a.get('category', 'check')}" for a in case.get('semantic_failures', [])})
                    text.append(f'- `{case["case"]}`: {case["outcome"]}; ' + ('; '.join(reasons) or 'see saved grading evidence'))
            text.append('')
    if data.get("historical_evidence"):
        text += [
            "## Baseline provenance", "",
            "The published Sonnet routing baseline was evaluated at `78bba2c`: "
            "95/99 scenarios and 98/102 turns passed. Its trace-derived snapshot "
            "retains all 99 initial prompt/schema fingerprints. The earlier flat-roster "
            "baseline scored 93/99 and is not the baseline used for this model comparison.", "",
            "[Historical measurements](../../../evals/model_comparison/baselines/routing_history.json) "
            "retain prior experiment tables, calibration costs, source revisions, and artifact "
            "references. They are separate from the primary comparison above. "
            "Original manifests retain paths as recorded at their evaluated revisions.", "",
        ]
    cleanup = data.get("cleanup_validation")
    if cleanup:
        text += [
            "## Cleanup verification", "",
            f"{cleanup['offline_tests_passed']} offline tests passed after reorganizing the eval layer. "
            f"All {cleanup['existing_test_cases_preserved']} existing test cases remain represented; "
            "paid evaluations and capacity checks require explicit collection paths.", "",
            f"Fixture and rubric contracts are unchanged. Replaying deterministic grading and "
            f"semantic evidence preparation for {cleanup['gmail_saved_records_checked']} saved Gmail records "
            "produced identical results. Comparison measurements and production files are unchanged. "
            "No new model or judge calls were made.", "",
            f"Current validation command: `{cleanup['command']}`.", "",
        ]
    validation = data.get('validation')
    if validation:
        text += ['## Validation at measurement time', '',
            f"Application defaults: `{validation['application_defaults']}` for all five roles. {validation['production_diff']}", '',
            f"**{validation['offline_tests_passed']} offline tests passed.** Command: `{validation['offline_command']}`.", '',
            'The three focused summarization/classification checks passed; the summary also passed manual approval-state review. These are limited sanity checks, not broad quality benchmarks.', '',
            f"Role-check inference estimate: {money(validation['role_sanity_inference_estimate'])}. Artifacts: `{validation['role_sanity_artifacts']}`.", '',
            f"All returned candidate model IDs were verified, and {validation['routing_first_turn_contracts_matched']} historical routing prompt/schema contracts matched.", '',
            f"Branch: `{validation['branch']}`, based on `{validation['base_main']}`.", '',
            '| Milestone | Commit |', '|---|---|']
        text += [f'| {name} | `{sha}` |' for name, sha in validation['milestones'].items()]
        text += ['', '[Setup and reproducible commands](../../../evals/README.md). ' + 'Local commits only; nothing pushed or submitted.', '']
    return '\n'.join(text).rstrip()
