# Paid evaluation collections

These pytest entry points make provider calls only when their explicit environment
opt-ins are set. They are excluded from ordinary engineering checks.

- `agent_gmail/` holds live Gmail and judge checks.
- `agent_overload/` holds live routing, inspection, scale, and challenge cases.

Use `RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite development` for the
28-scenario Gmail development suite. Use
`RUN_LIVE_EVALS=1 python -m pytest evals/live/agent_overload/test_routing.py -m standard`
for the 29-case, 32-turn routing suite. Both use `google/gemini-3.8-flash`; semantic
grading uses Gemini. Capacity checks are separate in
`tests/capacity/` and require `RUN_CAPACITY_EVALS=1`.
