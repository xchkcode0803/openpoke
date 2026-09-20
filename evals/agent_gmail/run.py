"""Run, regrade, or compare Gmail evaluations. See README for commands."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch
from uuid import uuid4

from .config import EvalConfig, DEFAULT_MODEL, FIXTURE_VERSION, GRADER_VERSION
from .provider import Provider
from .reporting import write_json, summarize, compare


def load_credentials():
    from dotenv import load_dotenv
    load_dotenv(override=False)
    # Linked worktrees may keep credentials only in the main checkout.
    if not os.getenv("OPENROUTER_API_KEY"):
        common = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], text=True).strip()
        load_dotenv(Path(common).resolve().parent / ".env", override=False)


def classify(record):
    # Agent failures cannot be hidden by a failed semantic judge.
    provider_error = any(c.get("error") for c in record.get("provider_calls", []))
    harness_error = any(t.get("failure_kind") == "harness" for t in record.get("turns", []))
    if provider_error or harness_error or record.get("unsupported") or record.get("harness_error") or record.get("budget_exhausted"):
        return "unavailable"
    if not record["deterministic"]["passed"]:
        return "agent_failure"
    if record.get("judge_error"):
        return "unavailable"
    return "pass" if record.get("semantic", {}).get("passed") else "agent_failure"


async def grade(case, record):
    from .metrics import GmailStateMetric, semantic
    from deepeval.test_case import LLMTestCase
    from .metrics import deterministic
    metric = GmailStateMetric(case)
    test_case = LLMTestCase(input=json.dumps([t.message for t in case.turns]), actual_output=json.dumps(record.get("final")), metadata={"record": record})
    metric.measure(test_case)
    record["deterministic"] = deterministic(case, record)
    try:
        record["semantic"] = await semantic(case, record)
    except Exception as exc:
        record["judge_error"] = str(exc)
    record["outcome"] = classify(record)


async def run(args):
    from .cases import select_cases
    from .harness import run_case
    from deepeval.tracing import trace
    import evals.agent_overload.metrics as shared_judges
    cases = select_cases(args.suite, args.case)
    config = EvalConfig(args.interaction_model, args.execution_model, args.search_model,
                        repetitions=args.repetitions, budget=args.budget)
    provider = Provider(config)
    await provider.verify()
    output = Path(args.output or f".deepeval/gmail/{time.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}")
    output.mkdir(parents=True, exist_ok=False)
    print(f"Artifacts: {output.resolve()}", flush=True)
    def hash_file(path):
        return sha256(Path(path).read_bytes()).hexdigest()
    manifest = {"config": asdict(config), "suite": args.suite, "cases": [c.name for c in cases],
                "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "fixture_version": FIXTURE_VERSION, "grader_version": GRADER_VERSION,
                "fixture_hash": hash_file(Path(__file__).with_name("cases.py")),
                "emulate_version": "0.11.2", "models": provider.metadata,
                "prompt_hashes": {str(p): hash_file(p) for p in Path("server/agents").rglob("system_prompt.*")},
                "tool_schema_hashes": {str(p): hash_file(p) for p in Path("server/agents").rglob("*.py") if "tools" in p.parts or p.name in {"tools.py", "schemas.py", "gmail_internal.py"}},
                "grader_hash": hash_file(Path(__file__).with_name("metrics.py")),
                "adapter_hash": hash_file(Path(__file__).with_name("adapter.py")),
                "harness_hash": hash_file(Path(__file__).with_name("harness.py")),
                "emulator_hash": hash_file(Path(__file__).with_name("emulator.py")),
                "emulate_launcher_hash": hash_file(Path(__file__).parent / "emulate" / "service.mjs"),
                "dependency_lock_hash": hash_file(Path(__file__).parent / "emulate" / "package-lock.json"),
                "eval_source_hashes": {p.name: hash_file(p) for p in Path(__file__).parent.glob("*.py")},
                "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain", "--", "evals/agent_gmail"], text=True).strip()),
                "status": "running"}
    write_json(output / "manifest.json", manifest)
    records, judge_usage = [], []
    def save_judge(filename, entry):
        judge_usage.append(entry)
        if isinstance(entry.get("cost"), (int, float)):
            provider.judge_cost += entry["cost"]
        else:
            provider.judge_cost_unknown = True
        with (output / filename).open("a") as stream:
            stream.write(json.dumps(entry, default=str) + "\n")
    judge_transport = shared_judges.paced_post
    async def budgeted_judge_post(*args, **kwargs):
        provider.check_budget()
        return await judge_transport(*args, **kwargs)
    with patch.object(shared_judges, "save_result", save_judge), patch.object(shared_judges, "paced_post", budgeted_judge_post):
        for repetition in range(config.repetitions):
            for case in cases:
                total_known = provider.known_cost + sum(j.get("cost") or 0 for j in judge_usage)
                if args.budget is not None and (total_known >= args.budget or provider.cost_unknown or provider.judge_cost_unknown):
                    manifest["status"] = "budget_stopped"
                    break
                start = time.perf_counter()
                call_start = len(provider.calls)
                judge_start = len(judge_usage)
                print(f"Running {case.name} [{repetition + 1}]", flush=True)
                try:
                    with trace(name=f"gmail/{case.name}", metadata={"repetition": repetition, "suite": args.suite}):
                        record = await run_case(case, config, provider)
                except Exception as exc:
                    record = {"case": asdict(case), "turns": [], "events": [], "harness_error": str(exc)}
                record["seconds"] = time.perf_counter() - start
                record["provider_calls"] = provider.calls[call_start:]
                grading_started = time.perf_counter()
                await grade(case, record)
                provider.judge_cost_unknown |= bool(record.get("judge_error"))
                record["budget_exhausted"] = provider.budget_stopped
                if provider.budget_stopped:
                    record["outcome"] = "unavailable"
                    manifest["status"] = "budget_stopped"
                record["judge_usage"] = judge_usage[judge_start:]
                record["grading_seconds"] = time.perf_counter() - grading_started
                record["measurement_seconds"] = time.perf_counter() - start
                record["repetition"] = repetition
                records.append(record)
                write_json(output / f"case-{case.name}-{repetition}.json", record)
                write_json(output / "summary.json", summarize(records))
                print(f"  {record['outcome']}: {len(record['deterministic']['failures'])} deterministic failures; agent cost ${provider.known_cost:.4f}", flush=True)
                if provider.budget_stopped:
                    break
            if manifest["status"] == "budget_stopped":
                break
    if manifest["status"] == "running":
        manifest["status"] = "complete"
    manifest["completed_scenarios"] = len(records)
    manifest["expected_scenarios"] = len(cases) * config.repetitions
    summary = summarize(records)
    summary["judge_known_cost"] = sum(j.get("cost") or 0 for j in judge_usage)
    summary["judge_cost_complete"] = not any(r.get("judge_error") for r in records) and all(isinstance(j.get("cost"), (int, float)) for j in judge_usage)
    if args.suite == "smoke" and records:
        summary["estimated_full_agent_cost"] = provider.known_cost / len(records) * 40
    write_json(output / "summary.json", summary)
    write_json(output / "manifest.json", manifest)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if manifest["status"] == "complete" and all(r["outcome"] == "pass" for r in records) else 1


async def regrade(args):
    from .cases import select_cases
    import evals.agent_overload.metrics as shared_judges
    cases = {c.name: c for c in select_cases("full")}
    source = Path(args.regrade)
    output = Path(args.output or str(source) + "-regrade-" + uuid4().hex[:6])
    output.mkdir(parents=True, exist_ok=False)
    regrade_usage = []
    accountant = Provider(EvalConfig(budget=args.budget))
    def save(filename, entry):
        regrade_usage.append(entry)
        if isinstance(entry.get("cost"), (int, float)):
            accountant.judge_cost += entry["cost"]
        else:
            accountant.judge_cost_unknown = True
        with (output / filename).open("a") as stream:
            stream.write(json.dumps(entry, default=str) + "\n")
    records = []
    judge_transport = shared_judges.paced_post
    async def budgeted_post(*args, **kwargs):
        accountant.check_budget()
        return await judge_transport(*args, **kwargs)
    with patch.object(shared_judges, "save_result", save), patch.object(shared_judges, "paced_post", budgeted_post):
        for path in sorted(source.glob("case-*.json")):
            record = json.loads(path.read_text())
            case = cases[record["case"]["name"]]
            if args.case and case.name not in args.case:
                continue
            if json.loads(json.dumps(asdict(case))) != record["case"]:
                raise ValueError("Fixtures changed; regrading cannot substitute a different case")
            for key in ("semantic", "judge_error", "judge_usage"):
                record.pop(key, None)
            judge_start = len(regrade_usage)
            grading_started = time.perf_counter()
            await grade(case, record)
            record["original_grading_seconds"] = record.get("grading_seconds")
            record["grading_seconds"] = time.perf_counter() - grading_started
            accountant.judge_cost_unknown |= bool(record.get("judge_error"))
            record["judge_usage"] = regrade_usage[judge_start:]
            write_json(output / path.name, record)
            records.append(record)
            if accountant.budget_stopped:
                break
    manifest = json.loads((source / "manifest.json").read_text())
    manifest["grader_git_sha"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    manifest.update(status="budget_stopped" if accountant.budget_stopped else "complete", cases=[r["case"]["name"] for r in records], completed_scenarios=len(records), expected_scenarios=len(records), regraded_from=str(source.resolve()), grader_version=GRADER_VERSION, grader_hash=sha256(Path(__file__).with_name("metrics.py").read_bytes()).hexdigest())
    write_json(output / "manifest.json", manifest)
    write_json(output / "summary.json", summarize(records))
    print(output.resolve())
    return 1 if accountant.budget_stopped else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("smoke", "development", "full"), default="smoke")
    parser.add_argument("--case", action="append", default=[])
    for role in ("interaction", "execution", "search"):
        parser.add_argument(f"--{role}-model", default=DEFAULT_MODEL)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--budget", type=float)
    parser.add_argument("--output")
    parser.add_argument("--regrade")
    parser.add_argument("--compare", nargs=2)
    args = parser.parse_args()
    if args.repetitions < 1 or (args.budget is not None and args.budget <= 0):
        parser.error("Repetitions and budget must be positive")
    if args.compare:
        print(json.dumps(compare(*args.compare), indent=2))
        return 0
    if os.getenv("RUN_LIVE_EVALS") != "1":
        parser.error("Set RUN_LIVE_EVALS=1 to permit paid model/judge calls")
    load_credentials()
    # Isolate imports before server/__init__ initializes application services.
    with tempfile.TemporaryDirectory(prefix="gmail-eval-session-") as root:
        with patch.dict(os.environ, {"OPENPOKE_DATA_DIR": root}):
            return asyncio.run(regrade(args) if args.regrade else run(args))


if __name__ == "__main__":
    raise SystemExit(main())
