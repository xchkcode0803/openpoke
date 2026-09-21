"""Large variants are descriptors until their test executes."""
import os
import pytest
from evals.agent_overload.routing_campaign import run_variant
from evals.agent_overload.routing_population import SCALE_VARIANTS


@pytest.mark.live
@pytest.mark.routing_scale
@pytest.mark.parametrize('variant', SCALE_VARIANTS, ids=lambda item: item.key)
def test_live_scale(variant):
    if os.getenv('RUN_LIVE_EVALS') != '1':
        pytest.skip('set RUN_LIVE_EVALS=1 for paid evaluation')
    result = run_variant(variant, 'live')
    assert result['status'] == 'passed', result
