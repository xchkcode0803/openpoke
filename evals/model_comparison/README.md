# Model comparison package

This package runs a named candidate through Gmail or routing, preserves the
candidate-specific pacing profile, verifies provider/tool support, records separate
artifacts and costs, and renders the comparison report. It keeps the independent
Jev and Sonnet fallback judges fixed.

Run from the repository root after installing `evals/requirements.txt` and the
Gmail Emulate dependency:

```bash
RUN_LIVE_EVALS=1 python -m evals.model_comparison.run --model gemini --collection gmail
RUN_LIVE_EVALS=1 python -m evals.model_comparison.run --model gemini --collection routing
python -m evals.model_comparison.report
```

Live runs are sequential and existing manifests block accidental resampling. Use
`--root` for an explicit new experiment directory. Gmail recovery uses `--resume`
only after a diagnosed external interruption; it preserves completed cases and
partial charge evidence. Unknown in-flight charges require reconciliation.

Gemini has no fixed request spacing. Sonnet retains its reproducible 4.1-second
profile. Both retain bounded retries and collection budgets. The default budget is
$10 per collection; `--budget` can lower it. Do not use a new artifact directory
to bypass an exhausted spending cap. Gmail's cap includes
BYOK upstream estimates; routing settles OpenRouter charges and reports BYOK
estimates separately. See the [evaluation suite README](../README.md) for test
commands and the [comparison report](../../docs/evals/reports/agent_eval_report.md)
for interpretation, results, and limits.
