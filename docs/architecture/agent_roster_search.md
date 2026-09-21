# Agent roster search

The interaction agent receives a bounded roster and delegates through the existing
exact-name create/reuse tool. Retrieval is local and deterministic: SQLite FTS5
with BM25 ranks candidates from roster profiles and recorded ownership history. It
does not use embeddings, a vector service, generated summaries, or a model
reranker.

## Storage and indexing

The roster is stored in `agents.sqlite3`. Each agent has an exact display name, a
normalized name, and first/latest recorded assignments. SQLite FTS indexes the
normalized profile fields and a separate index covers recorded assignment and
response text. Agent additions update the relevant indexes incrementally; bulk
imports build the profile index in one statement. Journals remain the authoritative
history. The index can be rebuilt from the roster and journals.

Names are normalized with Unicode NFKC, case folding, and punctuation separators.
The catalog preserves exact names for display and delegation. Journal files use a
hash of the exact name, which avoids collisions between similar legacy names.

## Candidate selection

For rosters of 20 agents or fewer, the prompt includes every owner. Larger rosters
include at most 20 ranked candidates and state that the list is incomplete.

Ranking combines these bounded retrieval streams:

1. An exact normalized match for the current message.
2. Exact name mentions in the current message.
3. Exact name mentions in the supplied conversation.
4. BM25 matches from roster profiles and ownership history.

Current-message matches receive more weight than the most recent 6,000 characters
of conversation. Explicit name references use the supplied conversation. Results
have deterministic normalized-name and exact-name tie breaks. Queries contain no
more than 64 distinct normalized terms and quote every FTS term literally, so
model-supplied text cannot introduce FTS syntax. BM25 is a rank, not a confidence
score.

Each candidate includes its exact name plus first/latest assignments, each capped
at 400 characters. A matching historical excerpt may be included when it is not a
duplicate. These excerpts are evidence only. Empty history means the information is
unavailable; it does not mean that work was completed or absent.

## Discovery tools

`search_agents(query, offset=0)` searches names, profiles, and recorded history
with the query alone. It returns up to ten candidates per page, including evidence,
`has_more`, and `next_offset`. A query exposes at most a 100-owner result window;
narrow or reformulate after that window. This is intentionally not a global match
count.

`inspect_agent(agent_name, offset=0)` requires an exact name. It synchronizes that
owner's journal, then returns six newest assignment/response excerpts per page,
including timestamp, source position, and truncation metadata. Entries are capped
at 1,000 characters. Raw tool activity is excluded.

Offsets must be integer values from zero through the available result count;
booleans are invalid. An offset at the count produces an empty final page. Unknown
owners, invalid offsets, and empty search queries are errors.

## Runtime limits

`send_message_to_agent` and `send_message_to_user` accept an `end_turn` boolean.
The runtime completes every tool call in a batch before honoring it. It finishes
without another model request only after successful calls, no unresolved discovery
result, and a user-visible response.

Each turn allows at most eight model rounds. Discovery can make at most six calls
across the first four model rounds. Invalid discovery calls consume that allowance;
calls after discovery closes are rejected and recorded in the trace. Limits reset
for each turn. Concurrent turns on one runtime instance are unsupported.

## Verification

Ordinary tests make no provider calls:

```bash
python -m pytest tests/unit tests/integration
```

The live routing development suite is explicit and sequential:

```bash
RUN_LIVE_EVALS=1 python -m pytest evals/live/agent_overload/test_routing.py -m standard
```

It runs 29 cases and 32 turns using `google/gemini-3.8-flash`. Provider failures
use the configured request timeout and retry only HTTP 429 responses, up to three
retries (four attempts total), following `Retry-After` when supplied. There is no
fixed pacing delay.
Local run artifacts contain the model/tool traces, provider usage, and costs; they
are ignored by Git.
