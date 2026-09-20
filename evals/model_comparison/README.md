# Gmail and routing model comparison

The report compares one 40-case Gmail run and one 99-case routing run per model.
Sonnet's routing result is the published 95/99 baseline from
`docs/agent_roster_search_results.md`; its compact trace-derived snapshot is in
`baselines/sonnet_routing.json`. Sonnet's Gmail result is the fresh 40-case run.

Run from the repository root with dependencies from `evals/requirements.txt` and
`npm ci --prefix evals/agent_gmail/emulate`. The launcher reads the local `.env`
(or the primary checkout's `.env`) without printing credentials.

```bash
OPENROUTER_API_KEY=offline-placeholder python -m pytest evals -m 'not live and not routing_capacity'
RUN_LIVE_EVALS=1 python -m evals.model_comparison.run --model gemini --collection gmail
RUN_LIVE_EVALS=1 python -m evals.model_comparison.run --model gemini --collection routing
python -m evals.model_comparison.report
```

Run paid commands sequentially. Existing live manifests prevent accidental
resampling. `--root` selects an explicit new experiment directory. The default is
`.deepeval/comparison-main-v1`. To reproduce Sonnet in a future experiment, use
`--model sonnet`; no new Sonnet routing run is needed for this report.

Gemini uses zero fixed spacing in both the HTTP wrapper and persistent ledger.
Sonnet's reproducible transport profile keeps 4.1-second spacing. Four-attempt
rate-limit handling remains. All three application roles participating in Gmail
use the selected candidate. Both candidates use the same Gmail 600-second worker
and 900-second turn transport allowances. Production iteration limits are unchanged.
Judges stay Jev 1.13 with Sonnet 4 fallback.

The default limit is $10 per collection, configurable downward with `--budget`.
Routing uses persistent conservative reservations for agent and judge calls.
Gmail uses its existing measured-charge cap, which can overshoot by in-flight
requests; missing charges stop subsequent work. Do not start a new directory to
bypass an exhausted cap. The routing launcher directly calls the existing evaluator
so its artifact and budget settings remain scoped to the same module instances.

## Recovery and reporting

After resolving a diagnosed external interruption, Gmail supports `--resume`.
It verifies model/source identity, retains completed cases, subtracts earlier
charges from the original cap, and regrades DNS-interrupted judge evidence without
agent replay. A case interrupted by HTTP 402 may restart, preserving its partial
trace and charges separately. Unknown in-flight charges require reconciliation.
Never lower output limits to bypass a provider credit reservation.

The report checks the historical routing baseline's first-turn prompt/schema
contracts against the candidate and keeps unavailable outcomes separate. Optional
manual audit notes under the artifact root are embedded in the report without
changing frozen scores. Reporting flags are not all confirmed false statements.
Mailbox authorization failures have independent mutation evidence.

HTTP durations include provider/network time; fixed pacing and retries are reported
separately. The published routing baseline was measured at a different time. These
are single-run observations, not reliability estimates or isolated latency trials.
