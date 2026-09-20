"""Run one candidate and collection, never resampling completed cases."""
import argparse
import asyncio
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

MODELS = {'sonnet': 'anthropic/claude-sonnet-4', 'gemini': 'google/gemini-3.8-flash'}
JUDGES = ('typesafe/jev-1.13', 'anthropic/claude-sonnet-4')
COLLECTIONS = ('gmail', 'routing', 'inspection', 'scale', 'challenge')


def fingerprint():
    paths = [*Path('server').rglob('*.py'), *Path('server').rglob('*.txt'),
             *Path('evals/agent_overload').glob('*.py'), *Path('evals/agent_gmail').glob('*.py')]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=MODELS, required=True)
    parser.add_argument('--collection', choices=COLLECTIONS, required=True)
    parser.add_argument('--root', default='.deepeval/comparison-main-v1')
    parser.add_argument('--budget', type=float, default=10)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Continue Gmail after a diagnosed DNS outage; never rerun agents')
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
                import pytest
                target = 'test_routing.py' if args.collection == 'routing' else 'test_inspection.py'
                marker = 'full' if args.collection == 'routing' else 'inspection'
                code = pytest.main([f'evals/agent_overload/{target}', '-m', f'live and {marker}',
                                    '-q', '--tb=short', '--junitxml', str(output / 'tests.xml')])
            manifest.update(status='finished', exit_code=int(code))
            return int(code)
        except BaseException as exc:
            manifest.update(status='interrupted', error=type(exc).__name__ + ': ' + str(exc))
            raise
        finally:
            manifest_path.write_text(json.dumps(manifest, indent=2))


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
        if result.get('reason') == 'budget' or 'Budget' in result.get('details', ''):
            break
    return int(len(outcomes) != len(variants) or any(r['status'] not in {'passed', 'completed'} for r in outcomes))


if __name__ == '__main__':
    raise SystemExit(main())
