# Gmail evaluation package

This package runs the real interaction, execution, and email-search agents against
a disposable Vercel Emulate Gmail mailbox. `cases.py` defines immutable fixtures;
`adapter.py` translates the existing Gmail boundary; `harness.py` executes isolated
turns; and `metrics.py` grades mailbox state and visible behavior.

The runner supports smoke, development, and full suites, targeted cases, regrading,
paired comparison, model overrides, and a measured spending cap. It does not change
production prompts, tools, or runtime limits. The eval-only adapter returns explicit
errors for contacts and uploaded attachments rather than fabricating success.

For setup, commands, coverage, adapter limits, and calibration qualifications, read
the [Gmail benchmark guide](../../docs/evals/gmail.md). For the measured Sonnet and
Gemini comparison, read the [current report](../../docs/evals/reports/agent_eval_report.md).
