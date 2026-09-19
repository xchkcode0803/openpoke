# Overload Eval Design, Low Level

## Framework

Use DeepEval 4.2.3 with pytest. Native test cases, tool-call records, metrics, and tracing wrap the real OpenPoke interaction loop. Custom code handles application isolation, routing expectations, and Jev decisions.

Inspect AI was considered but its solver model requires more adaptation around the existing runtime. Promptfoo was considered but adds a Node-based runner and Python bridge. DeepEval fits this Python implementation directly.

## Organization

- `cases.py`: frozen case/turn/delegation dataclasses, authored cases, generators, and suite selection.
- `stress_cases.py`: explicit stress fixtures and deterministic nested roster generation.
- `harness.py`: temporary services, worker stub, real runtime execution, tool/model recording.
- `metrics.py`: deterministic matching and Jev/Sonnet semantic grading.
- `provider.py`: pinned eval model, scoped HTTP requests, pacing/retries, context metadata, and run artifacts.
- Repository-root `conftest.py`: session import-time service isolation and cleanup, loaded before collection for both root and explicit eval invocations.
- Test modules: one parametrized live routing entry point, offline harness/generator checks, and judge validation.

Suite membership is assigned from explicit suite collections, not inherited scenario tags. Shared scenarios run once when markers are combined; full contains exactly 99 scenarios.

## Isolation and execution

The pytest session sets a temporary data root before application imports and restores the previous environment at shutdown. Each scenario creates another disposable directory and patches the module-local getters used by the real interaction runtime and tools. Production defaults remain unchanged when OPENPOKE_DATA_DIR is absent.

Disable summarization scheduling and replace execution dispatch with a recording stub. No worker results are sent back automatically. Seeded worker messages are deliberate fixture inputs. Restore patches and remove temporary directories after execution.

A scenario has a DeepEval trace with model/tool spans. Saved per-turn records include system prompt, messages, responses, tool calls, token usage, reported cost, and runtime. Every turn is evaluated even if another turn fails.

## Grading and providers

Routing expectations match each actual delegation at most once. Exact groups expect one call; one optional flexible group supports related parallel work. Missing dynamic owners produce failed dependencies rather than exceptions.

Jev uses typesafe/jev-1.13 and falls back to the central Sonnet 4 model for uncertain answers. Retain original Jev probabilities and fallback verdicts. Log judge usage once per actual request, not once per question in a batch.

Interaction and judge calls share a 4.1-second request interval and up to three retries on HTTP 429, honoring Retry-After. Only eval calls use this transport; HTTP behavior is not globally patched. Execution is sequential, not parallel-safe.

For stress cases, fetch the configured model's context limit. Estimate serialized prompt input at three UTF-8 bytes per token with an 8,192-token reserve. This estimate is not an exact tokenizer count or a provider guarantee. Never truncate the roster. Record capacity/provider failures separately.

Each process writes to a unique directory under `.deepeval/runs/`: completed turns, unavailable turns, judge errors, and judge usage. DeepEval also maintains its own latest result. Preserve baseline artifacts before subsequent evaluations replace that latest file.

## Commands

Install: `.venv/bin/python -m pip install -r evals/requirements.txt`

Offline checks:
```bash
.venv/bin/python -m pytest evals/agent_overload -m "not live"
```

Live routing (replace full with smoke, standard, or stress):
```bash
RUN_LIVE_EVALS=1 .venv/bin/deepeval test run evals/agent_overload/test_routing.py -m full
```

Judge validation:
```bash
RUN_LIVE_EVALS=1 .venv/bin/deepeval test run evals/agent_overload/test_grader.py -m grader_live
```

Live runs cost money. No result caching or parallel execution is requested by these commands. An assertion failure can be a legitimate baseline result; inspect the per-turn outcome before treating it as a harness defect.
