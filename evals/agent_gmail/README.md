# Gmail behavior evaluation

Runs the real interaction, execution, and search agents against a disposable Vercel Emulate Gmail service. The contract comes from current application prompts and explicit case instructions: accurate actions, preview before transmission, user confirmation, correct recipients/thread, and truthful reporting. Production prompts and tools remain unchanged.

Emulate is pinned to 0.11.2. Its adapter substitutes only the Composio boundary; this is not a production OAuth or delivery test. Contacts and Composio attachment uploads are outside scored coverage. Unsupported calls are recorded, never fabricated.

Fixture construction supplies valid raw MIME because the pinned emulator's generated raw representation for structured seeds inserts an extra content header in the body. This is covered by independent readback tests.

Install the local service with `npm ci --prefix evals/agent_gmail/emulate`. Python dependencies come from `evals/requirements.txt`. Local tests require permission to listen on loopback.

## Commands

Run from the repository root. To prepare a new Python environment (Python 3.11+):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r evals/requirements.txt
npm ci --prefix evals/agent_gmail/emulate
```

With that environment active:

```bash
OPENROUTER_API_KEY=offline-placeholder python -m pytest evals/agent_gmail evals/agent_overload -m 'not live'
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite smoke
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite development
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite full
```

The CLI reads `.env`, or the main checkout's `.env` in a linked worktree, without printing credentials. Runs are sequential. Every scenario uses real application orchestration and a disposable local mailbox. The initial API key placeholder in offline checks is required by the older overload harness; it makes no live requests.

Use `--case NAME` (repeatable), `--repetitions N` (default: one), `--interaction-model ID`, `--execution-model ID`, and `--search-model ID` for experiments. Defaults for all three application roles are `anthropic/claude-sonnet-4`, the baseline. Gemini was used to develop the harness and remains the candidate replacement. `--budget USD` stops new work when measured spend reaches the cap; already in-flight requests can overshoot it. Missing usage prevents further requests under a cap. Judges use the existing pinned Jev/Sonnet fallback independently of the candidate models.

```bash
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --regrade .deepeval/gmail/RUN
python -m evals.agent_gmail.run --compare .deepeval/gmail/BASELINE .deepeval/gmail/CANDIDATE
RUN_LIVE_EVALS=1 GMAIL_EVAL_SUITE=smoke python -m pytest evals/agent_gmail/test_live.py -m live
```

The CLI is the canonical artifact-producing entrypoint. The pytest entrypoint integrates with DeepEval assertions. Live runs cost money; no model substitution occurs if the requested model is missing.

## Results

Each CLI run creates an immutable directory under `.deepeval/gmail/` with a manifest, per-scenario JSON traces, judge usage, and a summary. Exit code 1 can mean genuine agent failures or incomplete measurements; inspect the outcome classifications. Raw artifacts remain untracked. Regrading creates another directory and refuses changed fixtures. Comparison requires matching fixture, prompt, grader, and Emulate versions.

A passing scenario requires deterministic and semantic correctness. Unavailable judges cannot erase observed deterministic failures. Unsupported adapter calls and provider outages are marked unavailable. All attempts are retained; reruns are not silently substituted into prior summaries. See `CALIBRATION.md` for documented corrections and the final report for observed coverage.

BYOK accounting preserves router charges and adds the reported upstream inference estimate for cost comparisons and caps; this is not a claim about the final provider invoice. Semantic grading costs are separate. Comparisons include paired regressions/improvements and a descriptive Wilson interval; authored fixtures and repetitions are not independent population samples.

## Coverage and grading

| Family | Development | Full |
|---|---:|---:|
| Compose and preview | 4 | 6 |
| Confirmation and revisions | 6 | 10 |
| Search and read | 4 | 7 |
| Search followed by action | 4 | 5 |
| Reply and forward lifecycle | 4 | 5 |
| Failures and recovery | 4 | 5 |
| Multiple tasks and partial completion | 2 | 2 |
| Total | 28 | 40 |

Smoke selects eight cases from development. Full adds fixed wording and distractor variants; there is no stress tier. `cases.py` is the source of truth for exact membership. All cases run through the complete application path. Missing prerequisites fail dependencies; the harness never supplies a missing draft or hidden target ID.

The deterministic grade checks real drafts/sent messages, recipient sets (including CC/BCC), thread IDs, explicit text restrictions, preview fidelity, authorized transmission order, deletion, and retrieved evidence. State is inspected after every Gmail action, so later cleanup cannot conceal a premature send. Required emails match one-to-one. Valid alternative tool sequences are accepted.

Semantic questions cover flexible content and user-facing reporting, using Jev and a pinned stronger-model fallback for uncertain answers. Narrow questions, known-outcome live checks, and manual trace audits calibrate these judgments; they remain fallible. Scenario success requires every turn's deterministic and semantic requirements. Report genuine application failures separately from provider, adapter, harness, and judge unavailability.

## Organization

- `types.py`, `cases.py`: immutable fixture and expectation contracts.
- `emulator.py`, `emulate/`, `adapter.py`: local service lifecycle, MIME seeding, independent readback, and Composio translation.
- `harness.py`, `tracing.py`: isolated real runtimes, task draining, callbacks, model/tool/HTTP evidence.
- `metrics.py`: deterministic and independent semantic grading, plus the DeepEval metric.
- `provider.py`, `usage.py`, `run.py`, `reporting.py`: model verification, cost/budget accounting, execution, regrading, and paired comparison.
- `test_*.py`: local integration, harness, negative grader, provider, reporting, and opt-in live checks.

No production APIs, tool schemas, prompts, or model defaults are changed. The only emulated external boundary is Gmail/Composio. Periodic background watchers and the web UI are outside this backend agent evaluation.

Validated with Python 3.12 and Node 20.10. The harness uses `asyncio.timeout`, requiring Python 3.11 or newer. The current model comparison is in `docs/agent_eval_report.md`; its compact JSON manifest links the scored artifacts and evaluated revisions. Historical calibration traces remain local and on the original Gmail branch.
