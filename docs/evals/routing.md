# Agent routing benchmark

The routing benchmark tests whether the interaction agent delegates a request to
the correct existing worker, creates a new worker only when appropriate, preserves
the user instruction, and ends the turn correctly. It uses real routing prompts,
candidate selection, roster search, ownership history, and delegation tools. Worker
execution is stubbed because this benchmark measures routing rather than downstream
task execution.

| Suite | Scenarios | Purpose |
|---|---:|---|
| Smoke | 12 | Fast representative routing checks. |
| Standard | 29 | Authored development cases. |
| Full | 99 | Extended routing coverage. |
| Stress | 24 | Existing generated-roster cases. |
| Inspection | 6 | Ownership-history cases outside the standard and full suites. |
| Scale | 48 | Eight scenarios from 10 through one million agents; opt-in. |
| Challenge | 36 | Twelve ownership scenarios at three sizes; opt-in. |

Large-roster capacity checks are separate and opt in explicitly. They include
synthetic rosters through one million agents; they are not part of ordinary tests
or routine live routing verification.

## Grading and fixtures

Fixtures define expected worker reuse or creation, required instruction content,
and multi-turn conversation state. Deterministic checks evaluate routing decisions;
Gemini evaluates instruction fidelity where needed. The
benchmark accepts valid discovery sequences, but grades the selected existing owner
and instruction fidelity. It does not grade incidental query wording or stylistic
invented names.

Live routing uses `google/gemini-3.8-flash`. It writes model/tool traces and
provider usage to a new local `.deepeval/runs/` directory. These artifacts are the
source of a run's cost and behavior details and are not committed.

## Running it

Run normal offline tests with:

```bash
OPENROUTER_API_KEY=offline-placeholder python -m pytest tests/unit tests/integration -q
```

Live routing tests require explicit opt-in:

```bash
RUN_LIVE_EVALS=1 python -m pytest evals/live/agent_overload/test_routing.py -m standard
```

The standard marker runs 29 cases and 32 turns. It is a paid, sequential run.

## Capacity checks

Capacity checks measure local roster creation, loading, candidate selection, and
search. They do not call a model. Run them only when investigating scale:

```bash
RUN_CAPACITY_EVALS=1 python -m pytest tests/capacity/agent_overload/test_routing_scale.py -m routing_capacity

# Cold and warm SQLite index measurements at the same opt-in sizes
RUN_INDEX_CAPACITY=1 python -m pytest tests/capacity/agent_overload/test_indexed_performance.py -m indexed_capacity
```

This includes the one-million-agent variants. Do not run it as part of routine
cleanup or ordinary test work. Indexed cold/warm measurements write
`.deepeval/runs/indexed-<timestamp>-<id>/performance/<size>/measurements.json`.
Fixture-scale runs write `.deepeval/runs/routing-<timestamp>-<id>/capacity/<variant>/`;
the corresponding opt-in live variants use the same layout under `live/` and retain
their fixture, process, outcome, and trace files locally.
