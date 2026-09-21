# Agent roster search

The interaction agent receives a bounded candidate roster, then delegates through the existing exact-name create/reuse tool. Candidate selection uses only production roster names, the current message, and the main conversation. It has no dependency on evaluation cases or expected answers.

## Candidate roster

Show every owner when the roster contains at most 20 agents. For larger rosters, rank names and show at most 20 candidates. The prompt states the total roster size and whether the list is complete.

The ranking priorities, in order, are:

1. Exact normalized name match with the current message.
2. Name explicitly mentioned in the current message.
3. Name explicitly mentioned anywhere in the supplied conversation.
4. Keyword relevance.
5. Position of the latest conversation mention, then alphabetical tie-breaking.

Comparison uses Unicode NFKC normalization, case folding, punctuation separators, and simple plural handling. Keyword scoring gives each matching term weight `log(1 + roster_size / names_containing_term)`. Current-message matches count three times; recent-conversation matches count once. The score is divided by `1 + 0.15 × unique_name_terms` to avoid favoring long names through incidental words.

Keyword matching uses the latest 6,000 characters of conversation; explicit-name matching uses the full supplied history. Each normalized name and ranking score is computed once per ranking call. This local lexical ranker selects candidates only; the model still decides ownership and delegation.

After selection, each candidate includes its exact name and, when recorded, short verbatim excerpts from its initial and latest assignments. These excerpts do not affect name ranking. Identical initial and latest assignments are shown only once. Each excerpt is capped at 400 characters and truncation is explicit. These are ownership hints, not generated summaries or live task results. Empty history is unknown information and must not contradict the main conversation. JSON escaping preserves names without allowing them to break the surrounding message structure.

The 20-candidate limit bounds the number of displayed owners, not the entire prompt's token count. Main conversation length, name length, and execution-log storage are not bounded by that limit. Lexical retrieval can still miss synonyms and implicit relationships; candidates are not guaranteed exhaustive.

## Discovery tools

`search_agents(query, offset=0)` returns up to ten exact names ranked by keyword relevance, `total_matches`, and `next_offset`. Unlike automatic candidate selection, this tool ranks from its query alone, without conversation history. Words need not all match. Use the same query and next offset for another page. Ordering is stable for an unchanged roster; concurrent edits can shift pages. Search examines names, not historical text.

`inspect_agent(agent_name, offset=0)` requires an exact roster name. It returns six recorded assignments/responses, newest append first, with timestamps and pagination. Entries are capped at 1,000 characters with explicit truncation flags. Raw tool activity is excluded. This tool helps choose between owners; it does not perform their tasks or check live emails/status.

Search is advertised only when the roster is larger than the complete visible-list limit. Inspection is advertised when there are multiple owners and execution logs exist. Hiding an unhelpful tool reduces prompt overhead and discourages treating an empty log as a task result. The existing handlers remain available for compatible callers; runtime discovery budgets still guard invocations.

Offsets must be integers from zero through the result count, excluding booleans. An offset equal to the count returns an empty final page. Empty matches/history are valid results; unknown owners and invalid arguments are errors.

## Turn completion and budgets

The model-facing schemas for `send_message_to_agent` and `send_message_to_user` require an `end_turn` boolean. Python callers may omit it; their default remains false. True means the interaction agent has finished dispatching/responding, not that execution workers have finished their jobs.

The runtime executes every tool in a batch before honoring `end_turn`. It ends without another model request only when every tool succeeded, no discovery result still needs interpretation, and there is a user-visible response from a message tool or assistant text. This preserves all independent delegations and avoids a redundant final model call. Failed batches and discovery batches continue normally.

The overall eight-model-call limit remains. Search and inspection may execute at most six times combined during the first four model rounds. Malformed discovery invocations consume budget; rejected attempts are counted in traces. Discovery tools disappear from later requests, and the guard rejects calls after closure. Closing discovery does not automatically create an agent. Budgets reset each turn; concurrent turns on the same runtime instance are not supported.

## Code and tests

`discovery.py` owns ranking, pagination, history excerpts, and candidate selection. The prompt builder reads candidate ownership hints from the existing log store. Existing tool handlers load current stores and advertise useful tools. The runtime owns budgets and batch completion. No new retrieval dependency, generated summary, storage migration, or model change is required.

Deterministic tests cover ranking, Unicode, plurals, exact names, pagination, validation, bounded excerpts, initial/latest ownership, JSON round-tripping, and read-only history access. Scripted runtime tests execute real tools in temporary stores and cover selection paths, tool availability, all-call batch execution, terminal dispatch, user notification, failed/discovery batches, budgets, and per-turn resets. They make no model API calls.

The baseline case definitions and graders remain frozen. The six inspection cases use separately seeded execution histories and remain outside standard/full. Live grading and artifact orchestration are shared in the harness rather than imported between test modules. The harness patches both the prompt builder's and tool handlers' log-store getters so ownership hints are isolated too. Artifacts retain model requests, tool results, failed requests, semantic judgments, usage, and timing.

## Verification commands

```bash
# Offline tests and coverage
DEEPEVAL_TELEMETRY_OPT_OUT=YES .venv/bin/python -m pytest tests/unit tests/integration -q \
  --cov=server.agents.interaction_agent --cov-branch --cov-report=term-missing --cov-report=json

# Complete statement/branch coverage for discovery
DEEPEVAL_TELEMETRY_OPT_OUT=YES .venv/bin/python -m pytest tests/integration/agent_overload/test_discovery.py \
  --cov=server.agents.interaction_agent.discovery --cov-branch --cov-fail-under=100

# A targeted live case (keep the model and grading unchanged)
RUN_LIVE_EVALS=1 DEEPEVAL_TELEMETRY_OPT_OUT=YES .venv/bin/deepeval test run \
  evals/live/agent_overload/test_routing.py -m standard -k routes_existing_and_new_task

# Development verification after targeted gates
RUN_LIVE_EVALS=1 DEEPEVAL_TELEMETRY_OPT_OUT=YES .venv/bin/deepeval test run \
  evals/live/agent_overload/test_routing.py -m standard
```

Review all changed executable lines and branches, not just aggregate legacy-module coverage. Keep live execution sequential with existing shared provider pacing. Do not use result-cache or parallel flags. Compare costs and behavior on matched cases, including all model calls. Measured outcomes and unsuccessful experiments belong in separate iteration reports.
