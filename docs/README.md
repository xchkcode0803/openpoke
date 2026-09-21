# Evaluation documentation

OpenPoke uses `google/gemini-3.8-flash` for production inference and live
evaluation runs. Semantic grading uses `typesafe/jev-1.13`; for low-confidence decisions, the fallback is `google/gemini-3.8-flash`.

- [Gmail](evals/gmail.md) covers the disposable Emulate mailbox, its safety
  checks, and the 28-scenario development run.
- [Routing](evals/routing.md) covers delegation, roster discovery, the 29-case
  standard live run, and opt-in capacity checks.
- [Agent roster search](architecture/agent_roster_search.md) is the production
  reference for SQLite/FTS retrieval and runtime discovery limits.

Live runs write a new local artifact directory containing request and tool traces,
usage, costs, timing, and a manifest. Those run-specific results are intentionally
ignored by Git. The [eval package README](../evals/README.md) maps the test layout.
