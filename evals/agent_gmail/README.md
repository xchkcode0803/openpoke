# Gmail evaluation package

This package runs the real interaction, execution, and email-search agents against
a disposable Vercel Emulate Gmail mailbox. `cases.py` defines immutable fixtures;
`adapter.py` translates the existing Gmail boundary; `harness.py` executes isolated
turns; and `metrics.py` grades mailbox state and visible behavior.

The runner supports smoke, development, and full suites, targeted cases, and model
overrides. It does not change production prompts, tools, or runtime limits. The
eval-only adapter returns explicit errors for contacts and uploaded attachments
rather than fabricating success.

Live roles use `google/gemini-3.8-flash`; semantic grading uses
`google/gemini-3.8-flash`. A run writes isolated traces, usage, and
cost records under `.deepeval/gmail/` by default. For setup, commands, coverage,
and adapter limits, read the [Gmail benchmark guide](../../docs/evals/gmail.md).
