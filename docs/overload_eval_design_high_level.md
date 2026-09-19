# Overload Eval Design, High Level

Measure how OpenPoke's existing interaction agent routes work as its roster grows. Compare routing quality and instruction fidelity alongside input tokens, reported cost, and runtime. The benchmark establishes a baseline for reducing roster-related context while preserving behavior.

## Scenarios

The full suite contains 99 scenarios: 25 development cases, six held-out cases, 44 generated overload variants, and 24 paired stress cases. Multi-turn scenarios retain state between turns.

Coverage includes creation and reuse, multiple tasks, conversation and summary context, follow-up ownership, execution-worker updates, similar names, and decisions requiring no delegation. Generated variants vary roster size, semantic-neighbor density, target position, and fixed-seed ordering. Eight stress seeds run at 10, 100, and 1,000 agents with nested rosters and unchanged requests.

Names are the production routing addresses. Exact duplicates cannot identify separate agents. Expected owners must be inferable from the visible roster and conversation; no Gmail integration or downstream work is required.

Held-out cases provide additional wording and combinations. They have been evaluated in the baseline and should not be described as permanently unseen. Regression cases initially remain empty and can later hold minimal reproductions.

## Verification

Deterministic checks evaluate reuse versus creation, acceptable owners, missing or extra delegations, duplicate assignment, required task coverage, earlier-created agents, runtime/tool failures, and respond/wait behavior. Independent delegations may occur in any order. Parallelizable groups permit multiple relevant calls.

Semantic checks evaluate preserved intent and restrictions in instructions and required user-facing responses. Jev answers narrow questions; probabilities between 0.10 and 0.90 use the pinned stronger judge. Confident boundary values do not use fallback. A semantic verdict cannot override a routing failure.

Retain model calls and tool results for diagnosis. Judge/provider failures are unavailable measurements, not evidence of poor routing. Score each turn and require all turns to pass for scenario success.

## Cost and scale

Report cumulative input/output tokens and interaction cost, with judge cost separately. Use matched stress seeds to compare scaling; aggregate size groups contain different tasks. Runtime includes pacing and differs from provider latency. Larger roster capacity limits remain unmeasured until tested.

A useful improvement preserves routing quality while reducing context and cost. Do not manufacture a lower baseline by weakening the model or tightening expectations after observing results. Preserve ambiguous fixture outcomes with explicit limitations.

## Execution levels

Smoke selects 12 scenarios; standard selects 29; full selects 99, including the 24 stress cases. Grader-live runs only judge validation. Live runs are explicitly enabled and sequential. Offline tests validate the harness and graders without provider calls. Recorded results belong in a separate baseline report.
