"""Run a fresh, opt-in Gmail evaluation."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch
from uuid import uuid4

from .runtime.config import EvalConfig, DEFAULT_MODEL, FIXTURE_VERSION, GRADER_VERSION
from .runtime.provider import Provider
from .grading.reporting import summarize, write_json


def load_credentials():
    from dotenv import load_dotenv
    load_dotenv(override=False)
    if not os.getenv("OPENROUTER_API_KEY"):
        common = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], text=True).strip()
        load_dotenv(Path(common).resolve().parent / ".env", override=False)


def classify(record):
    provider_error = any(call.get("error") for call in record.get("provider_calls", []))
    harness_error = any(turn.get("failure_kind") == "harness" for turn in record.get("turns", []))
    if provider_error or harness_error or record.get("unsupported") or record.get("harness_error"):
        return "unavailable"
    if not record["deterministic"]["passed"]:
        return "agent_failure"
    if record.get("judge_error"):
        return "unavailable"
    return "pass" if record.get("semantic", {}).get("passed") else "agent_failure"


async def grade(case, record):
    from deepeval.test_case import LLMTestCase
    from .grading.metrics import GmailStateMetric, deterministic, semantic

    test_case = LLMTestCase(
        input=json.dumps([turn.message for turn in case.turns]),
        actual_output=json.dumps(record.get("final")),
        metadata={"record": record},
    )
    GmailStateMetric(case).measure(test_case)
    record["deterministic"] = deterministic(case, record)
    try:
        record["semantic"] = await semantic(case, record)
    except Exception as exc:
        record["judge_error"] = str(exc)
    record["outcome"] = classify(record)


async def run(args):
    from .cases.definitions import select_cases
    from .runtime.harness import run_case
    from deepeval.tracing import trace
    import evals.shared.judges as shared_judges

    cases = select_cases(args.suite, args.case)
    config = EvalConfig(
        args.interaction_model,
        args.execution_model,
        args.search_model,
        turn_timeout=getattr(args, "turn_timeout", 180),
        repetitions=args.repetitions,
        worker_timeout=getattr(args, "worker_timeout", 90),
    )
    provider = Provider(config)
    await provider.verify()
    output = Path(args.output or f".deepeval/gmail/{time.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}")
    output.mkdir(parents=True, exist_ok=False)
    print(f"Artifacts: {output.resolve()}", flush=True)

    manifest = {
        "config": asdict(config), "suite": args.suite,
        "cases": [case.name for case in cases],
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "fixture_version": FIXTURE_VERSION, "grader_version": GRADER_VERSION,
        "models": provider.metadata, "status": "running",
    }
    write_json(output / "manifest.json", manifest)
    records, judge_usage = [], []

    def save_judge(filename, entry):
        judge_usage.append(entry)
        with (output / filename).open("a") as stream:
            stream.write(json.dumps(entry, default=str) + "\n")

    with patch.object(shared_judges, "save_result", save_judge):
        for repetition in range(config.repetitions):
            for case in cases:
                started = time.perf_counter()
                call_start, judge_start = len(provider.calls), len(judge_usage)
                print(f"Running {case.name} [{repetition + 1}]", flush=True)
                try:
                    with trace(name=f"gmail/{case.name}", metadata={"repetition": repetition, "suite": args.suite}):
                        record = await run_case(case, config, provider)
                except Exception as exc:
                    record = {"case": asdict(case), "turns": [], "events": [], "harness_error": str(exc)}
                record["seconds"] = time.perf_counter() - started
                record["provider_calls"] = provider.calls[call_start:]
                grading_started = time.perf_counter()
                await grade(case, record)
                record["judge_usage"] = judge_usage[judge_start:]
                record["grading_seconds"] = time.perf_counter() - grading_started
                record["measurement_seconds"] = time.perf_counter() - started
                record["repetition"] = repetition
                records.append(record)
                write_json(output / f"case-{case.name}-{repetition}.json", record)
                write_json(output / "summary.json", summarize(records))
                print(f"  {record['outcome']}: {len(record['deterministic']['failures'])} deterministic failures", flush=True)

    manifest.update(status="complete", completed_scenarios=len(records), expected_scenarios=len(cases) * config.repetitions)
    summary = summarize(records)
    write_json(output / "summary.json", summary)
    write_json(output / "manifest.json", manifest)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if all(record["outcome"] == "pass" for record in records) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("smoke", "development", "full"), default="smoke")
    parser.add_argument("--case", action="append", default=[])
    for role in ("interaction", "execution", "search"):
        parser.add_argument(f"--{role}-model", default=DEFAULT_MODEL)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("Repetitions must be positive")
    if os.getenv("RUN_LIVE_EVALS") != "1":
        parser.error("Set RUN_LIVE_EVALS=1 to permit paid model/judge calls")
    load_credentials()
    with tempfile.TemporaryDirectory(prefix="gmail-eval-session-") as root:
        with patch.dict(os.environ, {"OPENPOKE_DATA_DIR": root}):
            return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
