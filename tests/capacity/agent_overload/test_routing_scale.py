"""Large variants are descriptors until their test executes."""
import os
import pytest
from evals.agent_overload.runtime.campaign import run_variant
from evals.agent_overload.cases.population import SCALE_VARIANTS


@pytest.mark.routing_capacity
@pytest.mark.parametrize('variant', SCALE_VARIANTS, ids=lambda item: item.key)
def test_local_capacity(variant):
    if os.getenv('RUN_CAPACITY_EVALS') != '1':
        pytest.skip('set RUN_CAPACITY_EVALS=1 for large local benchmarks')
    result = run_variant(variant, 'capacity')
    assert result['status'] == 'completed', result
