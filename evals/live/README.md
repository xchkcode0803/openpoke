# Paid evaluation collections

These pytest entry points make provider calls only when their explicit environment
opt-ins are set. They are excluded from ordinary engineering checks.

- `agent_gmail/` runs live Gmail and judge checks with `RUN_LIVE_EVALS=1`.
- `agent_overload/` runs live routing, inspection, scale, and challenge cases with
  `RUN_LIVE_EVALS=1`.

Use the package-specific guides for suite commands and budgets. Capacity checks
are separate in `tests/capacity/` and require `RUN_CAPACITY_EVALS=1`.
