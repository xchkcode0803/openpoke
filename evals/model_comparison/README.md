# Current-main model comparison

Run from the repository root with dependencies from `evals/requirements.txt` and
`npm ci --prefix evals/agent_gmail/emulate`. The launcher reads the local `.env`
(or the primary checkout's `.env`) without printing credentials.

```bash
OPENROUTER_API_KEY=offline-placeholder python -m pytest evals -m 'not live and not routing_capacity'
python -m evals.model_comparison.run --model sonnet --collection scale --preflight
python -m evals.model_comparison.run --model sonnet --collection challenge --preflight
RUN_LIVE_EVALS=1 python -m evals.model_comparison.run --model sonnet --collection gmail
RUN_LIVE_EVALS=1 python -m evals.model_comparison.run --model sonnet --collection routing
RUN_LIVE_EVALS=1 python -m evals.model_comparison.run --model sonnet --collection inspection
RUN_LIVE_EVALS=1 python -m evals.model_comparison.run --model sonnet --collection scale
RUN_LIVE_EVALS=1 python -m evals.model_comparison.run --model sonnet --collection challenge
```

Repeat the five live commands with `--model gemini` once. Large collections perform
missing local capacity preflights before paid execution. Model IDs are explicit;
production defaults do not affect either baseline. Each collection runs in a fresh
process; do not parallelize paid commands. The default artifact root is
`.deepeval/comparison-main-v1`. Existing live manifests block accidental reruns.

Sonnet uses 4.1-second fixed request spacing; Gemini uses zero fixed spacing in
both the HTTP wrapper and persistent ledger. Four-attempt rate-limit handling
remains. All application roles participating in Gmail use the selected model.
Both models use the same Gmail 600-second worker and 900-second turn transport
allowances. Production iteration limits and the routing campaign's 300-second,
4-GiB process limits remain unchanged. Judges stay Jev 1.13 with Sonnet 4 fallback.

The default spending limit is $10 per collection, configurable downward with
`--budget`. Routing uses conservative persistent reservations for agent and judge
requests. Gmail uses its existing measured-charge cap, which can overshoot by
in-flight requests; missing charges stop subsequent work. These limits are not an
estimate or a target spend. Do not create a new directory to bypass a stopped cap.
Unavailable/provider/budget outcomes remain in the report.

Reports distinguish observed candidate failures from unavailable measurements.
HTTP duration includes provider/network latency, not pure inference time; report
fixed pacing and retries separately. Historical Gmail results predate current
routing and are not the primary paired comparison.
