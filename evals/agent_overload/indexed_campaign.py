"""One frozen indexed-routing comparison; shares the existing graders and budget."""
import asyncio
from dataclasses import asdict, dataclass
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

from .cases import full_cases
from .stress_cases import stress_cases
from .inspection_cases import INSPECTION_CASES, INSPECTION_HISTORY
from .routing_population import SCALE_VARIANTS, CHALLENGE_VARIANTS, Variant, materialize
from .routing_campaign import supervise, write_json

BASELINE = full_cases() + stress_cases()


@dataclass(frozen=True)
class Comparison:
    kind: str
    index: int
    size: int = 0

    @property
    def key(self):
        return f'{self.kind}_{self.index:03d}_{self.size}'

    def build(self):
        if self.kind in ('scale', 'challenge'):
            return materialize(Variant(self.kind,self.index,self.size))
        case = BASELINE[self.index] if self.kind == 'baseline' else INSPECTION_CASES[self.index]
        history = {} if self.kind == 'baseline' else INSPECTION_HISTORY[case.name]
        digest = hashlib.sha256(json.dumps(asdict(case), default=lambda x: sorted(x), sort_keys=True).encode()).hexdigest()
        return case, history, {'case_fingerprint':digest,'roster_size':len(case.initial_agents),'scenario':case.name}


COMPARISONS = tuple(Comparison('baseline',i) for i in range(99)) + tuple(
    Comparison(v.kind,v.index,v.size) for v in SCALE_VARIANTS+CHALLENGE_VARIANTS) + tuple(Comparison('inspection',i) for i in range(6))


def root_dir():
    return Path(os.getenv('INDEXED_CAMPAIGN_DIR','.deepeval/campaigns/indexed-routing-v1')).resolve()


class CampaignPaused(RuntimeError):
    """No further cases should start until spending uncertainty is resolved."""


def pause_reason(root):
    path = root / 'spend.json'
    if not path.exists():
        return None
    ledger = json.loads(path.read_text())
    if ledger.get('stopped'):
        return ledger['stopped']
    if any(row['status'] == 'reserved' for row in ledger['requests']):
        return 'An interrupted request has no recorded usage; campaign paused before further work'
    return None


def run_comparison(spec):
    if os.getenv('RUN_LIVE_EVALS') != '1':
        raise RuntimeError('Set RUN_LIVE_EVALS=1 for paid comparison')
    root=root_dir();destination=root/'live'/spec.key
    frozen=json.loads((root/'implementation_manifest.json').read_text())
    for filename,digest in frozen['files'].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=digest:
            raise ValueError(f'Frozen implementation or input changed: {filename}')
    outcome=destination/'outcome.json'
    if outcome.exists():return json.loads(outcome.read_text())
    reason = pause_reason(root)
    if reason:
        raise CampaignPaused(reason)
    phase=destination/'phase.json'
    if phase.exists():phase.unlink()
    with tempfile.TemporaryDirectory(prefix='openpoke-indexed-comparison-') as directory:
        state=supervise([sys.executable,'-m','evals.agent_overload.indexed_campaign',spec.kind,str(spec.index),str(spec.size),directory],
                        destination,build_seconds=900,ready_file=phase)
    if state['resource_failure'] or not outcome.exists():
        write_json(outcome,{'status':'resource_limit' if state['resource_failure'] else 'harness_error',**state})
    reason = pause_reason(root)
    if reason:
        raise CampaignPaused(reason)
    unavailable = destination / 'unavailable.jsonl'
    if unavailable.exists() and any(json.loads(line).get('metadata', {}).get('failure_kind') == 'budget' for line in unavailable.read_text().splitlines()):
        raise CampaignPaused('Spending guard stopped the campaign; completed artifacts are preserved')
    return json.loads(outcome.read_text())


def child(spec, directory=None):
    from . import provider
    from .campaign_budget import CampaignBudget
    from .harness import evaluate_live_case
    root=root_dir();destination=root/'live'/spec.key;destination.mkdir(parents=True,exist_ok=True)
    with (nullcontext(directory) if directory else tempfile.TemporaryDirectory(prefix='openpoke-indexed-comparison-')) as directory:
        with patch.dict(os.environ,{'OPENPOKE_DATA_DIR':directory,'EVAL_PHASE_FILE':str(destination/'phase.json')}), patch.object(tempfile, 'tempdir', directory):
            try:
                started=time.perf_counter();case,history,manifest=spec.build()
                manifest['generation_seconds']=time.perf_counter()-started
                write_json(destination/'fixture.json',manifest)
                budget=CampaignBudget(root,os.getenv('EVAL_MAX_SPEND_USD','10'),spec.key)
                with patch.object(provider,'_artifact_dir',destination),patch.object(provider,'request_budget',budget),patch.dict(provider.context_limits,{provider.MODEL:budget.prices[provider.MODEL]['context_length']}):
                    try:
                        evaluate_live_case(case,history)
                        result={'status':'passed'}
                    except AssertionError as exc:
                        result={'status':'failed','details':str(exc)}
                if (destination/'unavailable.jsonl').exists() or (destination/'judge_errors.jsonl').exists():
                    result['status']='unavailable'
                write_json(destination/'outcome.json',result)
            except Exception as exc:
                write_json(destination/'outcome.json',{'status':'harness_error','details':str(exc)})
                raise


if __name__ == '__main__':
    child(Comparison(sys.argv[1],int(sys.argv[2]),int(sys.argv[3])),sys.argv[4])
