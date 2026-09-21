"""Explicitly invoked paid routing-history evaluations."""
import os

import pytest

from evals.agent_overload.runtime.harness import evaluate_live_case
from evals.agent_overload.cases.inspection import INSPECTION_CASES, INSPECTION_HISTORY


@pytest.mark.live
@pytest.mark.inspection
@pytest.mark.parametrize('case', INSPECTION_CASES, ids=lambda case: case.name)
def test_live_inspection(case):
    if not os.getenv('RUN_LIVE_EVALS'):
        pytest.skip('set RUN_LIVE_EVALS=1 to call the interaction model')
    evaluate_live_case(case, INSPECTION_HISTORY[case.name])
