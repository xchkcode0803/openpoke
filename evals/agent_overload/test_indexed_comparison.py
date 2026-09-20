"""Explicit opt-in: original full suite, stress suite, and inspection suite once."""
import os
import pytest
from .indexed_campaign import COMPARISONS,run_comparison


@pytest.mark.live
@pytest.mark.indexed_comparison
@pytest.mark.parametrize('spec',COMPARISONS,ids=lambda item:item.key)
def test_indexed_comparison(spec):
    if os.getenv('RUN_LIVE_EVALS')!='1':pytest.skip('set RUN_LIVE_EVALS=1 for paid comparison')
    result=run_comparison(spec)
    assert result['status']=='passed',result


def test_comparison_membership():
    assert len(COMPARISONS)==len({item.key for item in COMPARISONS})==189
    assert sum(item.kind=='baseline' for item in COMPARISONS)==99
    assert sum(item.kind=='inspection' for item in COMPARISONS)==6


def test_supervised_state_is_removed_after_resource_failure(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from . import indexed_campaign
    monkeypatch.setenv('INDEXED_CAMPAIGN_DIR',str(tmp_path))
    monkeypatch.setenv('RUN_LIVE_EVALS','1')
    (tmp_path/'implementation_manifest.json').write_text(json.dumps({'files':{}}))
    directories=[]
    def stopped(command,destination,**kwargs):
        directory=Path(command[-1]);directories.append(directory)
        (directory/'state').write_text('temporary')
        return {'resource_failure':'index_build_limit','returncode':-15}
    monkeypatch.setattr(indexed_campaign,'supervise',stopped)
    result=indexed_campaign.run_comparison(indexed_campaign.Comparison('baseline',0))
    assert result['status']=='resource_limit'
    assert directories and not directories[0].exists()
    indexed_campaign.run_comparison(indexed_campaign.Comparison('baseline',0))
    assert len(directories)==1


def test_frozen_sources_cannot_change_mid_campaign(tmp_path,monkeypatch):
    import json
    from . import indexed_campaign
    monkeypatch.setenv('INDEXED_CAMPAIGN_DIR',str(tmp_path));monkeypatch.setenv('RUN_LIVE_EVALS','1')
    source=tmp_path/'source.py';source.write_text('changed')
    (tmp_path/'implementation_manifest.json').write_text(json.dumps({'files':{str(source):'previous'}}))
    with pytest.raises(ValueError,match='Frozen'):indexed_campaign.run_comparison(indexed_campaign.Comparison('baseline',0))
