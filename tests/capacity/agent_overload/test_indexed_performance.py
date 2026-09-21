import os
from pathlib import Path
import pytest
from evals.agent_overload.indexed_performance import run_measurement
from evals.agent_overload.routing_population import SCALE_SIZES


@pytest.mark.indexed_capacity
@pytest.mark.parametrize('size',SCALE_SIZES)
def test_indexed_performance(size):
    if os.getenv('RUN_INDEX_CAPACITY')!='1':pytest.skip('set RUN_INDEX_CAPACITY=1 for cold/warm measurements')
    result=run_measurement(size)
    assert 'failure' not in result,result


def test_measurement_passes_the_artifact_destination_to_the_build_child(tmp_path, monkeypatch):
    from evals.agent_overload import indexed_performance

    monkeypatch.setenv('EVAL_ARTIFACT_DIR', str(tmp_path / 'artifacts'))
    monkeypatch.setattr(indexed_performance, '_run_root', None)
    observed = []

    def supervised(command, destination, **kwargs):
        destination = Path(destination)
        observed.append((command, destination, kwargs))
        assert Path(command[-1]) == destination
        destination.mkdir(parents=True, exist_ok=True)
        (destination / 'measurements.json').write_text('{"size": 10}')
        return {'resource_failure': None, 'returncode': 0}

    monkeypatch.setattr(indexed_performance, 'supervise', supervised)
    assert indexed_performance.run_measurement(10) == {'size': 10}
    assert len(observed) == 1
    command, destination, kwargs = observed[0]
    assert command[3] == 'build'
    assert kwargs['seconds'] == 900
    assert destination.is_relative_to(tmp_path / 'artifacts')
