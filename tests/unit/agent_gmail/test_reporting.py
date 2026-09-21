from evals.agent_gmail.reporting import summarize
from evals.agent_gmail.run import classify


def test_missing_cost_not_zero_and_failure_classification():
    record = {"case": {"family": "compose"}, "outcome": "agent_failure", "provider_calls": [{"role": "execution", "usage": {}}], "deterministic": {"passed": False, "failures": []}}
    assert summarize([record])["agent_cost"] is None
    record["judge_error"] = "unavailable"
    assert classify(record) == "agent_failure"
    record["provider_calls"][0]["error"] = "provider outage"
    assert classify(record) == "unavailable"


def test_byok_zero_router_charge_is_not_free_inference():
    from evals.shared.usage import effective_cost
    assert effective_cost({"cost": 0, "is_byok": True, "cost_details": {"upstream_inference_cost": .12}}) == .12
    assert effective_cost({"cost": 0, "is_byok": True}) is None
    assert effective_cost({"cost": .12, "is_byok": False, "cost_details": {"upstream_inference_cost": .12}}) == .12


def test_summary_keeps_unavailable_out_of_quality_denominator():
    base = {"case": {"family": "compose"}, "deterministic": {"failures": []}}
    result = summarize([{**base, "outcome": "pass"}, {**base, "outcome": "unavailable"}])
    assert result["pass_rate_measured"] == 1
    assert result["coverage"] == .5
    assert result["descriptive_pass_rate_wilson_95"][0] < 1


def test_judge_error_does_not_imply_complete_zero_judge_cost():
    result = summarize([{"case": {"family": "compose"}, "outcome": "unavailable", "judge_error": "timeout"}])
    assert result["judge_known_cost"] == 0
    assert result["judge_cost_complete"] is False
