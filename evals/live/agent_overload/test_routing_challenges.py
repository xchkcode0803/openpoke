"""Authored ownership challenges, separate from the frozen baseline."""
import os
import pytest
from evals.agent_overload.runtime.campaign import run_variant
from evals.agent_overload.cases.population import CHALLENGE_VARIANTS


@pytest.mark.live
@pytest.mark.routing_challenge
@pytest.mark.parametrize('variant', CHALLENGE_VARIANTS, ids=lambda item: item.key)
def test_live_challenge(variant):
    if os.getenv('RUN_LIVE_EVALS') != '1':
        pytest.skip('set RUN_LIVE_EVALS=1 for paid evaluation')
    result = run_variant(variant, 'live')
    assert result['status'] == 'passed', result
