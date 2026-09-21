"""Opt-in large-roster routing evaluation with a small process watchdog."""

import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from .routing_population import Variant, materialize


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def _artifact_directory(mode, variant):
    root = Path(os.getenv("EVAL_ARTIFACT_DIR", ".deepeval/runs"))
    run = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8]
    return root / f"routing-{run}" / mode / variant.key


def _memory_bytes(pid):
    result = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    return int(result.stdout.strip() or 0) * 1024


def supervise(command, destination, *, seconds=300, memory_limit=4 * 1024**3, new_session=True):
    """Run a large fixture with only wall-clock and memory protection."""
    started = time.monotonic()
    peak = 0
    reason = None
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "process.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=new_session)
        try:
            while process.poll() is None:
                peak = max(peak, _memory_bytes(process.pid))
                if peak > memory_limit:
                    reason = "memory_limit"
                elif time.monotonic() - started > seconds:
                    reason = "wall_clock_limit"
                if reason:
                    (os.killpg(process.pid, signal.SIGTERM) if new_session else process.terminate())
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        (os.killpg(process.pid, signal.SIGKILL) if new_session else process.kill())
                    break
                time.sleep(0.1)
        finally:
            if process.poll() is None:
                (os.killpg(process.pid, signal.SIGKILL) if new_session else process.kill())
            process.wait()
    measurement = {"returncode": process.returncode, "resource_failure": reason,
                   "sampled_peak_rss_bytes": peak, "wall_seconds": time.monotonic() - started}
    write_json(destination / "process.json", measurement)
    return measurement


def prepare(variant, directory):
    """Build the fixture and measure the catalog operations exercised by routing."""
    from .harness import _seed_case
    from evals.shared.state import create_stores
    from server.agents.interaction_agent import agent, discovery

    started = time.perf_counter()
    case, history, metadata = materialize(variant)
    generation = time.perf_counter() - started
    roster, conversation, memory, logs = create_stores(directory)
    started = time.perf_counter()
    _seed_case(case, roster, conversation, memory)
    for name, entries in history.items():
        for tag, text in entries:
            (logs.record_request if tag == "agent_request" else logs.record_agent_response)(name, text)
    persistence = time.perf_counter() - started
    started = time.perf_counter()
    roster.load()
    loading = time.perf_counter() - started
    transcript = conversation.load_transcript()

    ranking_time = []
    original = discovery.select_candidates

    def timed_candidates(*args, **kwargs):
        start = time.perf_counter()
        value = original(*args, **kwargs)
        ranking_time.append(time.perf_counter() - start)
        return value

    started = time.perf_counter()
    with patch.object(agent, "get_agent_roster", return_value=roster), patch.object(agent, "get_execution_agent_logs", return_value=logs), patch.object(agent, "select_candidates", timed_candidates):
        messages = agent.prepare_message_with_history(case.turns[0].message, transcript)
    construction = time.perf_counter() - started
    candidates = json.loads(re.search(r"<active_agents[^>]*>\s*(.*?)\s*</active_agents>", messages[0]["content"], re.S).group(1))

    started = time.perf_counter()
    search = discovery.search_names(roster.catalog, case.turns[0].message)
    search_time = time.perf_counter() - started
    feasibility = []
    if variant.kind == "challenge":
        from .challenge_cases import challenges
        for tool, arguments in challenges()[variant.index].discovery:
            value = (discovery.search_names(roster.catalog, **arguments) if tool == "search_agents"
                     else discovery.inspect_history(roster.catalog, logs=logs, **arguments))
            feasibility.append({"tool": tool, "arguments": arguments, "result": value})

    prompt = json.dumps({"system": agent.build_system_prompt(), "messages": messages}, ensure_ascii=False)
    owners = {item["name"] for item in candidates}
    coverage = {item.task_key: bool(owners.intersection(item.acceptable_agent_names))
                for item in case.turns[0].delegations if item.route == "reuse"}
    measurements = {**metadata, "generation_seconds": generation, "persistence_seconds": persistence,
        "roster_load_seconds": loading, "candidate_selection_seconds": sum(ranking_time),
        "prompt_construction_seconds": construction, "search_seconds": search_time,
        "initial_candidates": candidates, "initial_owner_coverage": coverage, "search": search,
        "feasible_discovery_path": feasibility, "prompt_bytes_without_tool_schemas": len(prompt.encode()),
        "estimated_input_tokens_without_tool_schemas": len(prompt.encode()) // 3 + 1,
        "estimate_method": "UTF-8 bytes / 3; not a tokenizer or provider measurement",
        "platform": platform.platform(), "python": platform.python_version(),
        "machine_memory_bytes": subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip() if sys.platform == "darwin" else None}
    return case, history, measurements


def child(variant, mode, destination, directory):
    destination = Path(destination)
    original_tempdir = tempfile.tempdir
    tempfile.tempdir = directory
    try:
        with patch.dict(os.environ, {"OPENPOKE_DATA_DIR": directory}):
            if mode == "capacity":
                try:
                    case, history, measurements = prepare(variant, Path(directory))
                    write_json(destination / "fixture.json", measurements)
                    result = {"variant": variant.key, "status": "completed"}
                    write_json(destination / "outcome.json", result)
                except Exception as exc:
                    write_json(destination / "outcome.json", {"variant": variant.key, "status": "harness_error", "details": str(exc)})
                    raise
            else:
                from .harness import evaluate_live_case
                from . import provider
                case, history, _ = materialize(variant)
                with patch.object(provider, "_artifact_dir", destination):
                    try:
                        evaluate_live_case(case, history)
                        result = {"variant": variant.key, "status": "passed"}
                    except AssertionError as exc:
                        result = {"variant": variant.key, "status": "failed", "details": str(exc)}
                errors = {}
                for filename in ("unavailable.jsonl", "judge_errors.jsonl"):
                    path = destination / filename
                    if path.exists():
                        errors[filename] = [json.loads(line) for line in path.read_text().splitlines()]
                if errors:
                    result.update(status="unavailable", errors=errors)
                write_json(destination / "outcome.json", result)
    except Exception as exc:
        write_json(destination / "outcome.json", {"variant": variant.key, "status": "harness_error", "details": str(exc)})
        raise
    finally:
        tempfile.tempdir = original_tempdir


def run_variant(variant, mode):
    if mode == "live" and os.getenv("RUN_LIVE_EVALS") != "1":
        raise RuntimeError("Set RUN_LIVE_EVALS=1 for paid execution")
    destination = _artifact_directory(mode, variant)
    command = [sys.executable, "-m", "evals.agent_overload.routing_campaign", mode, variant.kind,
               str(variant.index), str(variant.size), str(destination)]
    with tempfile.TemporaryDirectory(prefix="openpoke-routing-") as directory:
        command.append(directory)
        measurement = supervise(command, destination)
    outcome = destination / "outcome.json"
    if measurement["resource_failure"]:
        write_json(outcome, {"variant": variant.key, "status": "resource_limit", **measurement})
    elif not outcome.exists():
        write_json(outcome, {"variant": variant.key, "status": "harness_error", **measurement})
    return json.loads(outcome.read_text())


if __name__ == "__main__":
    child(Variant(sys.argv[2], int(sys.argv[3]), int(sys.argv[4])), sys.argv[1], sys.argv[5], sys.argv[6])
