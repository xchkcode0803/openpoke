import os
import pytest
from .indexed_performance import run_measurement
from .routing_population import SCALE_SIZES


@pytest.mark.indexed_capacity
@pytest.mark.parametrize('size',SCALE_SIZES)
def test_indexed_performance(size):
    if os.getenv('RUN_INDEX_CAPACITY')!='1':pytest.skip('set RUN_INDEX_CAPACITY=1 for cold/warm measurements')
    result=run_measurement(size)
    assert 'failure' not in result,result
