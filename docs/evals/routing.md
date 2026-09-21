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
| Full | 99 | The primary routing benchmark, with 102 evaluated turns. |
| Stress | 24 | Existing generated-roster cases. |
| Inspection | 6 | Ownership-history cases outside the standard and full suites. |

The separate difficult-routing collections add 48 scale variants and 36 ownership
challenges; see [their guide](difficult_routing.md).

## Grading and fixtures

Fixtures define expected worker reuse or creation, required instruction content,
and multi-turn conversation state. Deterministic checks evaluate routing decisions;
Jev with a Sonnet 4 fallback evaluates instruction fidelity where needed. The
benchmark accepts valid discovery sequences, but grades the selected existing owner
and instruction fidelity. It does not grade incidental query wording or stylistic
invented names.

The current published Sonnet baseline is 95/99 scenarios. Its trace-derived
snapshot is retained at `evals/model_comparison/baselines/sonnet_routing.json`.
The model comparison verifies all 99 first-turn prompt and tool-schema contracts
before comparing that historical result with a new candidate run.

## Running it

Run normal offline tests with:

```bash
OPENROUTER_API_KEY=offline-placeholder python -m pytest tests/unit tests/integration -q
```

Live routing tests require explicit opt-in:

```bash
RUN_LIVE_EVALS=1 python -m pytest evals/live/agent_overload -m full
```

Use the [comparison runner](../../evals/model_comparison/README.md) for a
reproducible Sonnet or Gemini collection and the [current report](reports/agent_eval_report.md)
for the measured comparison. The difficult-routing guide documents its own capacity
and campaign commands.
