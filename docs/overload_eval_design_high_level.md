# Overload Eval Design, High Level

This document currently records only the high-level test-suite case groups.

Baseline cases use the inputs available today: execution-agent names, the main conversation history (raw or summarized), and the incoming user message or worker update. They do not require private execution-agent histories or additional agent metadata.

The current interaction prompt and tool behavior are the baseline contract. Product ideas that are not required by that contract, such as mandatory clarification or one persistent agent per broad goal, are excluded from scoring.

## Core routing cases

Normal routing behavior with a small, clear agent roster:

- Reuse the correct existing agent.
- Create an agent when no existing agent owns the task.
- Route multiple independent tasks to the appropriate agents.
- Avoid delegation when no execution work is needed.
- Preserve important user instructions when delegating.
- Avoid duplicate delegation and work beyond the user's request.

### conversation_context

- Resolve pronouns and omitted subjects from the visible conversation.
- Follow topic changes and explicit user corrections.
- Route with summarized conversation when it contains sufficient information.

### routing_across_turns

- Create an agent for a new task, then reuse it for a follow-up.
- Switch tasks and return to the original agent without creating a duplicate.

### execution_agent_updates

- Report completed work without delegating it again.
- Route an already-requested next step when a worker result makes it possible.
- Avoid renewed delegation or duplicate user messages when a result repeats information already delivered.

## Confusing-choice cases

Routing when several agents appear plausible:

- Same subject with different tasks.
- Same task for different subjects.
- Broad agent versus specialized agent.
- Existing task versus a new but related task.
- Several agents with very similar names.
- Several acceptable agents, where any suitable choice is valid.

## Overload cases

Repeat representative core and confusing-choice cases while increasing:

- Total number of agents.
- Number of irrelevant agents.
- Number of similar agents.

When adding distractors, the underlying request and correct routing decision stay unchanged.

Separately, increase the number of requested tasks and required agents to test complete routing under overload. These scenarios change both the request and the expected delegations.

### negative_decisions_under_overload

- Create an agent when a large roster contains plausible alternatives but no suitable owner.
- Avoid delegation when execution work is unnecessary, regardless of roster size.

## Stability cases

Repeat equivalent cases while changing details that should not affect routing:

- Roster ordering.
- Position of the correct agent.
- Minor request paraphrasing.
- Natural spelling mistakes.
- Repeated model runs.

## What each evaluation verifies

### Graded behavior

These determine whether a case passes:

- Make the correct routing decision: reuse, create, route to multiple agents, respond, wait, or avoid delegation.
- Cover every requested task.
- Avoid extra or incorrect delegations.
- Preserve important user instructions and constraints.
- Avoid duplicate agent creation and repeated assignment of the same work.

### Recorded trace

Preserve the complete interaction and tool-call trace for every run, including:

- User-facing responses.
- Delegation calls and selected agent names.
- Delegated instructions.
- Whether each selected agent was reused or created.
- Model-call count and repeated actions.

The trace supports automated grading and debugging. Failed or suspicious results retain the full trace for diagnosis.

### Recorded diagnostics

Record these separately from the initial pass/fail result:

- Input and output tokens.
- Cost.
- Latency.
- Number of model calls.
- Number of delegation calls.
- Judge model and pinned version.
- Semantic judgment probability.
- Whether judge fallback was triggered.
- Final semantic verdict and the judge that produced it.

### Evaluation boundary

This benchmark ends after the routing decision. It does not evaluate whether execution agents successfully complete Gmail, reminder, research, or other downstream work.

Grade that the user is acknowledged before delegation, as required by the current prompt. Do not grade exact acknowledgement wording, hidden reasoning, exact tool-call order among independent agent calls, the precise number of reasoning steps, or harmless wording differences in delegated instructions.

## Grading strategy

The benchmark uses an automated grading stack. Code combines the individual grading results into the final case result.

### Deterministic grader

Use deterministic checks wherever the expected behavior can be derived from the routing trace:

- Correct existing agents selected.
- Reuse and creation decisions.
- Missing, extra, or duplicate delegations.
- Task coverage when ownership is explicit.
- Response, wait, or no-delegation behavior.
- Routing loops and repeated assignment.

These checks are authoritative and do not use a model judge.

### Semantic grader

Use a pinned Jev model for narrow semantic decisions that deterministic code cannot grade reliably:

- Delegated instructions preserve the requested work.
- Important user constraints are preserved.
- Newly created agents receive the correct task.
- Delegations do not introduce unrequested work.

Related parallel workers are valid when their combined work covers the request. A delegation is extra only when it is unrelated, duplicates work, or exceeds an explicit case constraint.

Worker-result cases distinguish complete results, which should be reported, from incomplete results, which may require follow-up delegation.

Define each judgment as a focused yes-or-no or fixed-choice decision. Record Jev's answer and probability.

### Low-confidence fallback

When Jev's result does not meet the configured confidence threshold, send that individual judgment to a pinned stronger judge model.

The fallback model evaluates the same criterion and returns a structured decision. It does not regrade deterministic checks or the entire case.

Record which judge produced the final decision and whether fallback was required. Choose the confidence threshold and fallback model during detailed evaluation design.

### Grader validation

Maintain a small semantic grader-validation suite containing known positive, negative, and minimally changed examples. Use it to verify that:

- Jev recognizes preserved meaning across paraphrases.
- Jev detects missing or reversed constraints.
- Jev rejects additional work not requested by the user.
- Low-confidence results invoke the fallback correctly.
- The fallback returns the expected structured decisions.

A grader-validation failure indicates a problem with the evaluation system rather than the routing implementation.

## Suite execution levels

### Smoke

Run a small representative subset to confirm that the evaluation runner, trace capture, deterministic grader, and semantic grader work together. Use this level for quick checks while developing the evaluation.

### Standard

Run the normal routing, confusing-choice, conversation, multi-turn, negative-decision, and representative overload and stability cases. Use this level regularly while developing the routing fix.

### Full

Run every standard case together with all planned roster-size variations, similar-agent-density variations, stability repetitions, and the complete grader-validation suite. Use this level to establish the baseline and evaluate the completed overload fix.

## Result reporting

Report results separately by:

- Core routing, confusing choices, overload, and stability.
- Routing decision type.
- Roster size and similar-agent density.
- Deterministic and semantic grading.
- Correctness, cost, and latency.

Do not combine correctness and efficiency into a single score.

## Held-out cases

Held-out cases cover the same routing behaviors as the main suite, but use unseen scenarios, wording, and combinations. They are not used while developing the routing fix. Related cases and their variants stay together so the development set cannot leak into the held-out set.

## Regression cases

The regression group starts empty. When development or real usage reveals a routing failure, add the smallest case that reproduces it. The case remains permanently to prevent the same failure from returning.
