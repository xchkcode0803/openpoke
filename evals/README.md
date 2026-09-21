# Evaluation suite

The evaluation code is separate from production behavior. It uses real application
runtimes where the behavior under test requires them, and test doubles only where a
benchmark intentionally isolates a narrower concern.

| Path | Purpose |
|---|---|
| `agent_gmail/` | Gmail fixtures, Vercel Emulate adapter, orchestration, grading, and runner. |
| `agent_overload/` | Routing fixtures, candidate discovery, grading, and campaign support. |
| `model_comparison/` | Candidate selection, recovery, cost accounting, and comparison reporting. |
| `live/` | Explicitly invoked paid pytest collections for Gmail and routing. |
| `shared/` | Small utilities shared by benchmark packages. |

Engineering tests live outside this package:

| Path | Purpose |
|---|---|
| `tests/unit/` | Pure fixtures, graders, reporting, and accounting checks. |
| `tests/integration/` | Scripted application runtimes, subprocesses, and local Emulate checks. |
| `tests/capacity/` | Explicit opt-in process, memory, and timeout measurements for routing. |

Use Python 3.11 or newer (validated with Python 3.12 and Node 20.10).
Install dependencies from the repository root:

```bash
python -m pip install -r evals/requirements.txt
npm ci --prefix evals/agent_gmail/emulate
```

Run ordinary engineering checks without provider calls:

```bash
OPENROUTER_API_KEY=offline-placeholder python -m pytest -q
```

Paid collections are never included in that command. Invoke them explicitly:

```bash
RUN_LIVE_EVALS=1 python -m pytest evals/live/agent_gmail -m live
RUN_LIVE_EVALS=1 python -m pytest evals/live/agent_overload -m full
RUN_CAPACITY_EVALS=1 python -m pytest tests/capacity -m routing_capacity
```

For a named Sonnet or Gemini comparison, use
`python -m evals.model_comparison.run --help`. Read the [documentation index](../docs/README.md)
for benchmark design, results, and limitations.
