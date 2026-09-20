from .reporting import summarize
from .run import classify


def test_missing_cost_not_zero_and_failure_classification():
    record = {"case": {"family": "compose"}, "outcome": "agent_failure", "provider_calls": [{"role": "execution", "usage": {}}], "deterministic": {"passed": False, "failures": []}}
    assert summarize([record])["agent_cost"] is None
    record["judge_error"] = "unavailable"
    assert classify(record) == "agent_failure"
    record["provider_calls"][0]["error"] = "provider outage"
    assert classify(record) == "unavailable"


def test_budget_counts_judges_and_unknown_cost():
    import pytest
    from .provider import Provider, BudgetExceeded
    from .config import EvalConfig
    provider = Provider(EvalConfig(budget=1))
    provider.known_cost = .4
    provider.judge_cost = .6
    with pytest.raises(BudgetExceeded):
        provider.check_budget()
    provider.judge_cost = 0
    provider.judge_cost_unknown = True
    with pytest.raises(BudgetExceeded):
        provider.check_budget()


def test_byok_zero_router_charge_is_not_free_inference():
    from .usage import effective_cost
    assert effective_cost({"cost": 0, "is_byok": True, "cost_details": {"upstream_inference_cost": .12}}) == .12
    assert effective_cost({"cost": 0, "is_byok": True}) is None
    assert effective_cost({"cost": .12, "is_byok": False, "cost_details": {"upstream_inference_cost": .12}}) == .12


def test_summary_keeps_unavailable_out_of_quality_denominator():
    base = {"case": {"family": "compose"}, "deterministic": {"failures": []}}
    result = summarize([{**base, "outcome": "pass"}, {**base, "outcome": "unavailable"}])
    assert result["pass_rate_measured"] == 1
    assert result["coverage"] == .5
    assert result["descriptive_pass_rate_wilson_95"][0] < 1


def test_budget_interruption_is_unavailable_not_model_failure():
    assert classify({"budget_exhausted": True, "deterministic": {"passed": False}}) == "unavailable"


def test_compare_rejects_changed_fixtures_and_pairs_regressions(tmp_path):
    import pytest
    from .reporting import compare, write_json
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    manifest = {"fixture_hash": "same", "grader_version": "3"}
    for root, outcome in ((left, "pass"), (right, "agent_failure")):
        write_json(root / "manifest.json", manifest)
        write_json(root / "case-test-0.json", {"case": {"family": "compose"}, "outcome": outcome})
    result = compare(left, right)
    assert result["regressions"] == ["case-test-0"]
    write_json(right / "manifest.json", {**manifest, "fixture_hash": "different"})
    with pytest.raises(ValueError, match="fixture_hash"):
        compare(left, right)


def test_judge_error_does_not_imply_complete_zero_judge_cost():
    result = summarize([{"case": {"family": "compose"}, "outcome": "unavailable", "judge_error": "timeout"}])
    assert result["judge_known_cost"] == 0
    assert result["judge_cost_complete"] is False
