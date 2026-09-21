"""Run one candidate and collection, never resampling completed cases."""
import argparse
import asyncio
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from evals.shared.models import MODELS, JUDGES
from evals.shared.provenance import eval_source_hashes
from .collections import COLLECTIONS


def fingerprint():
    paths = [*Path("server").rglob("*.py"), *Path("server").rglob("*.txt")]
    return {
        **{str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)},
        **eval_source_hashes(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=MODELS, required=True)
    parser.add_argument('--collection', choices=COLLECTIONS, required=True)
    parser.add_argument('--root', default='.deepeval/comparison-main-v1')
    parser.add_argument('--budget', type=float, default=10)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Continue Gmail after a diagnosed interruption; preserve completed agent cases')
    args = parser.parse_args()
    if not 0 < args.budget <= 10:
        parser.error('Budget must be greater than zero and at most $10 per collection')
    if not args.preflight and os.getenv('RUN_LIVE_EVALS') != '1':
        parser.error('Set RUN_LIVE_EVALS=1 to authorize paid calls')
    if args.preflight and args.collection not in {'scale', 'challenge'}:
        parser.error('Preflight applies only to scale and challenge')
    model = MODELS[args.model]
    output = Path(args.root).resolve() / args.model / args.collection
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / 'comparison.json'
    if args.resume and (args.collection != 'gmail' or not manifest_path.exists()):
        parser.error('Resume requires an existing Gmail comparison')
    if manifest_path.exists() and not args.preflight and not args.resume:
        parser.error('This collection already started; inspect its artifacts, do not silently rerun')
    from evals.agent_gmail.run import load_credentials
    load_credentials()
    with tempfile.TemporaryDirectory(prefix='comparison-session-') as directory, ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {
            'OPENPOKE_DATA_DIR': directory, 'EVAL_CANDIDATE_MODEL': model,
            'EVAL_CAMPAIGN_DIR': str(output), 'EVAL_MAX_SPEND_USD': str(args.budget),
            'CONFIDENT_TRACE_VERBOSE': '0',
        }))
        # Imports occur after environment selection. Children inherit it as well.
        from evals.agent_overload import provider, harness, metrics
        stack.enter_context(patch.object(provider, 'MODEL', model))
        stack.enter_context(patch.object(harness, 'MODEL', model))
        stack.enter_context(patch.object(provider, '_artifact_dir', output))
        assert metrics.FALLBACK_MODEL == JUDGES[1]
        if args.preflight:
            return campaign(args.collection, 'capacity')
        from evals.agent_gmail.config import EvalConfig
        from evals.agent_gmail.provider import Provider
        verified = Provider(EvalConfig(model, model, model))
        asyncio.run(verified.verify())
        if args.resume:
            old = json.loads(manifest_path.read_text())
            if old['model'] != model or old['source_hashes'] != fingerprint():
                parser.error('Cannot resume with changed model or benchmark sources')
            from .resume import resume_gmail
            old['status'] = 'running'
            manifest_path.write_text(json.dumps(old, indent=2))
            try:
                code = asyncio.run(resume_gmail(args, output, model, provider.paced_post))
            except BaseException as exc:
                old = json.loads(manifest_path.read_text())
                old.update(status='interrupted', error=type(exc).__name__ + ': ' + str(exc))
                manifest_path.write_text(json.dumps(old, indent=2))
                raise
            old = json.loads(manifest_path.read_text())
            old.update(status='finished', exit_code=code)
            manifest_path.write_text(json.dumps(old, indent=2))
            return code
        manifest = {'model': model, 'models': verified.metadata, 'collection': args.collection,
                    'git_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                    'source_hashes': fingerprint(), 'judges': JUDGES, 'repetitions': 1,
                    'fixed_pacing_seconds': provider.request_interval(), 'budget_usd': args.budget,
                    'gmail_turn_timeout': 900, 'gmail_worker_timeout': 600, 'status': 'running'}
        manifest_path.write_text(json.dumps(manifest, indent=2))
        try:
            if args.collection == 'gmail':
                from evals.agent_gmail.run import run
                code = asyncio.run(run(SimpleNamespace(
                    suite='full', case=[], interaction_model=model, execution_model=model,
                    search_model=model, repetitions=1, budget=args.budget,
                    output=str(output / 'gmail'), turn_timeout=900, worker_timeout=600,
                    transport=provider.paced_post)))
            elif args.collection in {'scale', 'challenge'}:
                from evals.agent_overload.campaign_budget import initialize_prices
                initialize_prices(output, (model, *JUDGES))
                code = campaign(args.collection, 'live')
            else:
                from evals.agent_overload.campaign_budget import initialize_prices, CampaignBudget
                initialize_prices(output, (model, *JUDGES))
                stack.enter_context(patch.object(provider, "request_budget", CampaignBudget(output, args.budget)))
                code = routing_collection(args.collection, output)
            manifest.update(status='finished', exit_code=int(code))
            return int(code)
        except BaseException as exc:
            manifest.update(status='interrupted', error=type(exc).__name__ + ': ' + str(exc))
            raise
        finally:
            manifest_path.write_text(json.dumps(manifest, indent=2))


def routing_collection(collection, output):
    """Call the exact existing test evaluator in the already-scoped module graph."""
    from evals.agent_overload.harness import evaluate_live_case
    from evals.agent_overload.cases import full_cases
    from evals.agent_overload.stress_cases import stress_cases
    from evals.agent_overload.inspection_cases import INSPECTION_CASES, INSPECTION_HISTORY
    cases = full_cases() + stress_cases() if collection == 'routing' else INSPECTION_CASES
    outcomes = []
    for case in cases:
        print(f'Running {case.name}', flush=True)
        try:
            evaluate_live_case(case, INSPECTION_HISTORY.get(case.name))
            outcome = {'case': case.name, 'status': 'passed'}
        except AssertionError as exc:
            outcome = {'case': case.name, 'status': 'failed', 'details': str(exc)}
        except Exception as exc:
            outcome = {'case': case.name, 'status': 'unavailable', 'details': str(exc)}
        outcomes.append(outcome)
        (output / 'outcomes.json').write_text(json.dumps(outcomes, indent=2))
        print(json.dumps(outcome), flush=True)
        # A stopped ledger must not schedule more cases. Preserve remaining cases as not run.
        ledger = output / 'spend.json'
        if ledger.exists():
            state = json.loads(ledger.read_text())
            if state['stopped'] or any(r['status'] in {'reserved', 'unresolved'} for r in state['requests']):
                break
        if 'unavailable (budget)' in outcome.get('details', '') or outcome.get('details', '').startswith('Budget limit:'):
            break
    return int(len(outcomes) != len(cases) or any(r['status'] != 'passed' for r in outcomes))


def campaign(collection, mode):
    from evals.agent_overload.routing_population import SCALE_VARIANTS, CHALLENGE_VARIANTS
    from evals.agent_overload.routing_campaign import run_variant
    variants = SCALE_VARIANTS if collection == 'scale' else CHALLENGE_VARIANTS
    outcomes = []
    for variant in variants:
        print(f'{mode}: {variant.key}', flush=True)
        result = run_variant(variant, mode)
        outcomes.append(result)
        print(json.dumps(result), flush=True)
        # Budget failures are unavailable, never a reason to use a fresh ledger.
        if result.get('reason') == 'budget' or 'unavailable (budget)' in result.get('details', ''):
            break
    return int(len(outcomes) != len(variants) or any(r['status'] not in {'passed', 'completed'} for r in outcomes))


if __name__ == '__main__':
    raise SystemExit(main())
