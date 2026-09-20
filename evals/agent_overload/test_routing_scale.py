"""Large variants are descriptors until their test executes."""
import os
import pytest
from .routing_campaign import run_variant
from .routing_population import SCALE_VARIANTS


@pytest.mark.routing_capacity
@pytest.mark.parametrize('variant', SCALE_VARIANTS, ids=lambda item: item.key)
def test_local_capacity(variant):
    if os.getenv('RUN_CAPACITY_EVALS') != '1':
        pytest.skip('set RUN_CAPACITY_EVALS=1 for large local benchmarks')
    result = run_variant(variant, 'capacity')
    assert result['status'] == 'completed', result


@pytest.mark.live
@pytest.mark.routing_scale
@pytest.mark.parametrize('variant', SCALE_VARIANTS, ids=lambda item: item.key)
def test_live_scale(variant):
    if os.getenv('RUN_LIVE_EVALS') != '1':
        pytest.skip('set RUN_LIVE_EVALS=1 for paid evaluation')
    result = run_variant(variant, 'live')
    assert result['status'] == 'passed', result
