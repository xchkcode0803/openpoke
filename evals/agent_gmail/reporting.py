"""Stable JSON artifacts and comparable summaries; missing costs stay unknown."""
import json
from pathlib import Path
import statistics
import math
from evals.shared.usage import effective_cost


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=str) + "\n")


def summarize(records):
    outcomes = {"pass": 0, "agent_failure": 0, "unavailable": 0}
    families = {}
    for record in records:
        outcome = record["outcome"]
        outcomes[outcome] += 1
        family = record["case"]["family"]
        counts = families.setdefault(family, {"pass": 0, "agent_failure": 0, "unavailable": 0})
        counts[outcome] += 1
    calls = [call for r in records for call in r.get("provider_calls", [])]
    costs = [effective_cost(c.get("usage", {})) for c in calls]
    known_cost = sum(c for c in costs if isinstance(c, (int, float)))
    complete_cost = bool(costs) and all(isinstance(c, (int, float)) for c in costs)
    measured = outcomes["pass"] + outcomes["agent_failure"]
    failures = [f for r in records for f in r.get("deterministic", {}).get("failures", [])]
    latencies = sorted(r.get("seconds", 0) for r in records)
    roles = {}
    for role in ("interaction", "execution", "search"):
        selected = [c for c in calls if c["role"] == role]
        usage = [c.get("usage", {}) for c in selected]
        def total(field):
            values = [effective_cost(u) if field == "cost" else u.get(field) for u in usage]
            return sum(values) if values and all(isinstance(v, (int, float)) for v in values) else None
        roles[role] = {"calls": len(selected), "input_tokens": total("prompt_tokens"), "output_tokens": total("completion_tokens"), "cost": total("cost")}
    if measured:
        p = outcomes["pass"] / measured
        denominator = 1 + 1.96 ** 2 / measured
        center = (p + 1.96 ** 2 / (2 * measured)) / denominator
        radius = 1.96 * math.sqrt(p * (1 - p) / measured + 1.96 ** 2 / (4 * measured ** 2)) / denominator
        interval = [max(0, center - radius), min(1, center + radius)]
    else:
        interval = None
    judge_usage = [j for r in records for j in r.get("judge_usage", [])]
    return {"scenarios": len(records), "descriptive_pass_rate_wilson_95": interval,
            "uncertainty_note": "Descriptive only: authored cases and repetitions are not independent population samples.",
            "judge_known_cost": sum(j.get("cost") or 0 for j in judge_usage),
            "judge_cost_complete": not any(r.get("judge_error") for r in records) and all(isinstance(j.get("cost"), (int, float)) for j in judge_usage), "outcomes": outcomes, "families": families,
            "pass_rate_measured": outcomes["pass"] / measured if measured else None,
            "coverage": measured / len(records) if records else None,
            "cost_basis": "OpenRouter charges plus reported upstream inference estimates for BYOK calls",
            "agent_cost": known_cost if complete_cost else None, "known_agent_cost": known_cost,
            "cost_per_success": known_cost / outcomes["pass"] if complete_cost and outcomes["pass"] else None,
            "roles": roles, "unauthorized_sends": sum(f["name"] == "authorized_send" for f in failures),
            "wrong_targets_or_content": sum(f["name"] == "sent_targets_and_content" for f in failures),
            "extra_transmissions": sum(f["name"] == "no_extra_transmissions" for f in failures),
            "reporting_failures": sum(not a["verdict"] and a.get("category") == "reporting" for r in records for a in r.get("semantic", {}).get("answers", [])),
            "latency_median": statistics.median(latencies) if latencies else None,
            "latency_p95": latencies[min(len(latencies) - 1, int(len(latencies) * .95))] if latencies else None}


def compare(left, right):
    def index(path):
        manifest = json.loads((Path(path) / "manifest.json").read_text())
        records = {p.stem: json.loads(p.read_text()) for p in Path(path).glob("case-*.json")}
        return manifest, records
    lm, lr = index(left)
    rm, rr = index(right)
    for key in ("fixture_hash", "grader_version", "grader_hash", "prompt_hashes", "tool_schema_hashes", "adapter_hash", "harness_hash", "emulator_hash", "emulate_launcher_hash", "dependency_lock_hash", "emulate_version"):
        if lm.get(key) != rm.get(key):
            raise ValueError(f"Cannot pair different {key}")
    common = sorted(lr.keys() & rr.keys())
    regressions = [k for k in common if lr[k]["outcome"] == "pass" and rr[k]["outcome"] == "agent_failure"]
    improvements = [k for k in common if lr[k]["outcome"] == "agent_failure" and rr[k]["outcome"] == "pass"]
    return {"baseline_config": lm.get("config"), "candidate_config": rm.get("config"), "matched": len(common), "regressions": regressions, "improvements": improvements, "unmatched_left": sorted(lr.keys() - rr.keys()), "unmatched_right": sorted(rr.keys() - lr.keys()),
            "pairs": [{"case": k, "baseline": lr[k]["outcome"], "candidate": rr[k]["outcome"]} for k in common],
            "baseline": summarize([lr[k] for k in common]), "candidate": summarize([rr[k] for k in common])}
