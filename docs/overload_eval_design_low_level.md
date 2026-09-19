# Overload Eval Design, Low Level

This document translates the high-level overload evaluation design into concrete technical decisions.

## Evaluation framework

### Decision

Use DeepEval as the evaluation framework, with its pytest integration as the underlying test runner.

### Justification

DeepEval fits OpenPoke's Python backend and can evaluate the existing interaction-agent runtime without replacing its routing loop. It supports complete agent trajectories, tool-call tracing, multi-turn cases, repeated trials, pytest markers, and local result inspection.

The evaluation requires mostly deterministic custom grading, with Jev and a stronger fallback model handling narrow semantic decisions. DeepEval supports custom metrics and custom evaluation models, allowing this grading stack to remain specific to OpenPoke rather than depending on generic built-in LLM metrics.

DeepEval will manage evaluation execution, tracing, repetitions, suite selection, and result presentation. OpenPoke's evaluation code will remain responsible for case definitions, isolated state, runtime invocation, routing expectations, deterministic grading, and the Jev grading workflow.

### Alternatives considered

Inspect AI was considered because it provides strong Python support for datasets, tools, multi-turn tasks, scorers, and reproducible model evaluations. Its task-and-solver abstraction is better suited to evaluating models directly and would require more adaptation around OpenPoke's existing application runtime.

Promptfoo was considered because it provides mature prompt comparison, Python providers, custom assertions, tracing, and a strong local interface. Its primary runtime is Node-based, and integrating OpenPoke would require a Python-provider and tracing bridge, making it less natural for this Python routing evaluation.

## Evaluation code structure

Keep the evaluation implementation small and centered around the real OpenPoke interaction runtime.

### Case definitions

Each routing case describes:

- The execution-agent names that exist before the case starts.
- The conversation history that exists before the next message.
- One or more incoming user or execution-agent messages.
- The routing behavior expected after each message.
- Any facts or constraints that must be preserved in delegated instructions.
- Tags identifying its suite and scenario group.

Each expected delegation also defines a permitted call range. Ordinary work expects exactly one matching call. Parallelizable work accepts one or more related calls and is graded on combined task coverage. Only one flexible delegation group is allowed in a turn so matching stays deterministic.

Single-turn and multi-turn cases use the same structure. Multi-turn cases simply contain more incoming messages.

Cases encode only behavior required by the current interaction prompt and tools. Unimplemented product policies are not executable eval expectations.

Normal semantic cases remain hand-written and readable. Separate helper functions create overload variants by adding unrelated agents, similar agents, changing roster order, or changing the target agent's position.

### Files

`cases.py` contains routing cases and overload-variant helpers.

`harness.py` resets the evaluation state, seeds the initial roster and conversation, runs each message through the real interaction runtime, captures the routing trace, and prevents execution agents from performing downstream work.

`metrics.py` contains the deterministic routing grader, the Jev semantic grader, and the low-confidence fallback logic.

`test_routing.py` is the thin pytest entry point. It selects cases, runs them through the harness, applies the graders, and asserts that they pass. It contains no routing or grading logic.

`test_grader.py` validates the evaluation system itself using known semantic examples. It verifies that Jev recognizes preserved meaning, catches changed or missing constraints, and invokes the fallback when confidence is low.

### DeepEval integration

DeepEval manages pytest execution, suite selection, repeated runs, trace recording, metric execution, and local result inspection.

The harness records each completed case as one DeepEval trace. Each turn, model call, and routing tool call is recorded inside that trace. OpenPoke-specific expectations are attached as trace metadata and evaluated by the custom metrics.

The evaluation does not create a separate trace representation or reimplement OpenPoke's routing loop.

### Execution flow

1. Select a routing case and optional overload variant.
2. Create isolated roster and conversation state.
3. Run the case through the real OpenPoke interaction runtime.
4. Record the complete run as a DeepEval trace.
5. Apply deterministic routing checks.
6. Apply Jev semantic checks where meaning must be evaluated.
7. Use the stronger fallback judge for low-confidence Jev results.
8. Return the final case result and retain the trace for debugging.

## Implemented commands

Install the evaluation dependencies:

```bash
.venv/bin/python -m pip install -r evals/requirements.txt
```

Run offline validation:

```bash
.venv/bin/python -m pytest evals/agent_overload -m "not live"
```

Run live semantic-grader validation:

```bash
RUN_LIVE_EVALS=1 .venv/bin/deepeval test run \
  evals/agent_overload/test_grader.py -m grader_live
```

Run the live smoke suite:

```bash
RUN_LIVE_EVALS=1 .venv/bin/deepeval test run \
  evals/agent_overload/test_routing.py -m smoke
```

DeepEval saves local artifacts under `.deepeval/`, which is ignored by Git. Current OpenRouter limits can interrupt a large live suite; the resulting trace records the provider error separately from routing behavior.
