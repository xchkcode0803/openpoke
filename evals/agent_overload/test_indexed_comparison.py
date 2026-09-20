"""Explicit opt-in: original full suite, stress suite, and inspection suite once."""
import os
import pytest
from .indexed_campaign import COMPARISONS,run_comparison,CampaignPaused


@pytest.mark.live
@pytest.mark.indexed_comparison
@pytest.mark.parametrize('spec',COMPARISONS,ids=lambda item:item.key)
def test_indexed_comparison(spec):
    if os.getenv('RUN_LIVE_EVALS')!='1':pytest.skip('set RUN_LIVE_EVALS=1 for paid comparison')
    try:
        result=run_comparison(spec)
    except CampaignPaused as exc:
        pytest.exit(str(exc), returncode=2)
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


@pytest.mark.parametrize('stopped,status', [(None,'reserved'),('Usage unavailable','unresolved')])
def test_uncertain_spend_stops_before_build(tmp_path,monkeypatch,stopped,status):
    import json
    from . import indexed_campaign
    monkeypatch.setenv('INDEXED_CAMPAIGN_DIR',str(tmp_path));monkeypatch.setenv('RUN_LIVE_EVALS','1')
    (tmp_path/'implementation_manifest.json').write_text(json.dumps({'files':{}}))
    (tmp_path/'spend.json').write_text(json.dumps({'stopped':stopped,'requests':[{'status':status}]}))
    monkeypatch.setattr(indexed_campaign,'supervise',lambda *a,**k:pytest.fail('Must not build while spending is unresolved'))
    with pytest.raises(CampaignPaused):indexed_campaign.run_comparison(indexed_campaign.Comparison('baseline',0))


def test_harness_temporary_state_is_nested_under_supervised_directory(tmp_path,monkeypatch):
    import json,tempfile
    from pathlib import Path
    from . import indexed_campaign,harness,provider
    root=tmp_path/'campaign';root.mkdir();directory=tmp_path/'supervised';directory.mkdir()
    monkeypatch.setenv('INDEXED_CAMPAIGN_DIR',str(root))
    (root/'prices.json').write_text(json.dumps({provider.MODEL:{'context_length':200000}}))
    original=tempfile.tempdir;observed=[]
    def evaluate(case,history):
        with tempfile.TemporaryDirectory(prefix='openpoke-agent-overload-') as nested:
            observed.append(Path(nested))
            assert Path(nested).is_relative_to(directory)
    monkeypatch.setattr(harness,'evaluate_live_case',evaluate)
    indexed_campaign.child(indexed_campaign.Comparison('baseline',0),str(directory))
    assert observed and not observed[0].exists()
    assert tempfile.tempdir==original
