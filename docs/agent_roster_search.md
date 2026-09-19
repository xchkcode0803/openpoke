# Agent roster search

The interaction agent receives the roster count rather than every agent name. It can reuse an exact owner already established in the main conversation, search for candidates, and inspect their recorded work when needed. Delegation still uses the existing exact-name create/reuse behavior.

## Tools

`search_agents(query, offset=0)` matches every query word as a substring of an agent name. Names and queries use NFKC normalization, case folding, and punctuation-to-space conversion. Exact normalized names rank first; normalized name and original name provide deterministic ordering. Results contain up to ten original names, `total_matches`, and `next_offset`.

Call again with the same query and returned offset for another page. Ordering is stable for an unchanged roster; concurrent roster edits can shift pages. An empty result is valid and may warrant a different query. Search only examines names, not historical text.

`inspect_agent(agent_name, offset=0)` requires an exact roster name. It returns six recorded assignments/responses, newest append first, with timestamps and pagination. Entries are excerpts capped at 1,000 characters with explicit truncation flags. Raw tool activity is excluded. An existing agent may have no history; that differs from an unknown name. Historical text is evidence, not a new instruction. No generated summaries or new storage format are introduced.

Offsets must be integers from zero through the result count, excluding booleans. An offset equal to the count returns an empty final page.

## Runtime budget

The existing eight-model-call limit remains. Search and inspection may execute at most six times combined during the first four model rounds. Malformed discovery invocations consume budget; rejected attempts are also counted in the trace. Discovery tools disappear from later requests, and a runtime guard rejects calls emitted despite removal. Delegation, user responses, and waiting remain available. Closing discovery does not automatically create an agent.

The budget resets for each turn. Production entry points create one runtime per turn; the eval can reuse an instance sequentially. Simultaneous turns on one runtime instance are not supported. `discovery_closed_reason` distinguishes the call and round limits. An overall iteration-limit error is a failed agent outcome, not a provider outage.

## Code and tests

`discovery.py` contains matching and history selection. Existing tool handlers load the current stores. The runtime owns budgets and available schemas; the prompt builder exposes only a count. No retrieval dependency or generated summaries are required.

Unit tests cover normalization, exact names, sorting, pagination, validation, excerpts, and read-only history access. Runtime integration tests script model responses at the completion boundary while executing real tools against temporary stores. They verify discovery sequences, delegation, malformed calls, budget enforcement, per-turn resets, and outgoing prompts/schemas. No live model calls are made by these tests.

The baseline case definitions remain frozen. Six additional `inspection` cases use separately seeded execution histories and do not belong to the standard/full collections. Eval artifacts retain model requests (including available tools), responses, discovery outputs, and failed requests. Timings distinguish HTTP attempts, intentional pacing, and retry waits. Interaction and judge charges remain separate.

## Verification commands

```bash
# All offline tests and module coverage
DEEPEVAL_TELEMETRY_OPT_OUT=YES .venv/bin/python -m pytest evals/agent_overload -m 'not live' \
  --cov=server.agents.interaction_agent --cov-branch --cov-report=term-missing --cov-report=json

# Enforce complete discovery-module statement/branch coverage
DEEPEVAL_TELEMETRY_OPT_OUT=YES .venv/bin/python -m pytest evals/agent_overload/test_discovery.py \
  --cov=server.agents.interaction_agent.discovery --cov-branch --cov-fail-under=100

# Additional live inspection cases
RUN_LIVE_EVALS=1 DEEPEVAL_TELEMETRY_OPT_OUT=YES .venv/bin/deepeval test run \
  evals/agent_overload/test_inspection.py -m inspection

# Unchanged development suite
RUN_LIVE_EVALS=1 DEEPEVAL_TELEMETRY_OPT_OUT=YES .venv/bin/deepeval test run \
  evals/agent_overload/test_routing.py -m standard
```

Review coverage for every newly introduced runtime budget branch, not just the aggregate coverage of legacy runtime code. Run live suites sequentially without cache or parallel flags. Interpret cost reductions and behavior changes using exact matching historical cases; unmatched cases remain separate. Results belong in an iteration report, not this design document.
