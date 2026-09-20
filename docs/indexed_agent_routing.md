# Indexed agent routing: first implementation

The first indexed implementation uses SQLite FTS5/BM25 for both initial candidates and explicit search. It adds no embeddings, vector service, generated summaries, or model reranker. Sonnet 4 and the existing discovery limits remain unchanged.

## Storage and migration

`execution_agents/agents.sqlite3` is authoritative for exact-name roster membership. Names remain case-sensitive identities; normalized forms are indexed lookup aids. The catalog stores insertion IDs, cached first/latest assignment excerpts, eligible history records, source offsets, and synchronization state. SQLite uses WAL, a five-second busy timeout, and a bounded 32 MiB connection page cache.

On first access, a valid legacy `roster.json` is imported transactionally. Duplicate identical names retain their first position and are counted in migration metadata. The original file becomes `roster.legacy.json` after commit. Malformed input raises an error. Clearing membership does not remove the database or re-import the backup. A missing database beside a migration backup requires explicit recovery.

Use `count`, `contains`, and bounded discovery on routing paths. `get_agents`/JSON export intentionally enumerate the roster. `bulk_import` replaces membership transactionally and is intended for initialization and isolated fixtures. Bulk loading defers secondary-index construction and builds FTS in one statement. Normal additions are incremental and protected by SQLite uniqueness.

Execution logs remain authoritative history journals. New paths use a hash of the exact name. Legacy logs are associated only when their owner is unambiguous; collisions are preserved and reported rather than assigned arbitrarily. Existing hash-named journals can also be recovered during an explicit roster import. Tool logging obtains its store when called, not at module import.

Writes mark the journal dirty before appending, flush the record, then commit indexed updates and the new byte offset. Pending work is replayed before retrieval and on reopening. Eligible records are assignments and agent responses; raw tool activity is excluded. First/latest assignment caches update when assignments change. Incomplete or malformed records fail visibly and retain the journal for repair.

Normal retrieval does not scan all log files. Inspection can detect deletion, truncation, or atomic replacement of its particular journal. Out-of-band edits, including same-size rewrites, require an explicit rebuild. Stop application writers before maintenance:

```bash
.venv/bin/python -m server.services.execution.maintenance status
.venv/bin/python -m server.services.execution.maintenance rebuild
.venv/bin/python -m server.services.execution.maintenance export --destination /tmp/openpoke-legacy-export
```

For rollback, stop the backend, preserve the current database and journals, export current membership/history into a new directory, and use that export with the old version. Do not restore the stale migration backup as current data. Export refuses names whose slugs collide because the legacy format cannot represent them safely.

## Retrieval

Four bounded streams feed a small reciprocal-rank fusion step: current-message profile/history hits, weighted 3, and recent-conversation profile/history hits, weighted 1. Each stream returns at most 100 hits; repeated history hits for one owner contribute once per stream. The fusion constant is 60. Profile BM25 field weights are name 3, initial assignment 1, latest assignment 2.

Exact normalized matches and explicit current-message references precede other results; explicit conversation references are retained before lexical-only candidates. Name and ID tie-breaking is deterministic within the pool. Explicit-name detection performs text-driven indexed lookups rather than scanning every roster name. Lexical history uses the last 6,000 characters; explicit references use the supplied conversation. Queries use at most 64 distinct normalized tokens, quoted literally for FTS. BM25 scores are not confidence probabilities.

At most 20 owners enter the initial prompt. Small rosters stay complete. Profiles show first/latest assignments (400 characters each) and may add one nonduplicate matching historical excerpt (400 characters), with type, timestamp, and source position. Original history text is retained for evidence; a normalized companion field supports Unicode lookup. Historical matches may be superseded by a later assignment or handoff.

`search_agents(query, offset=0)` uses the same service with the query alone. It returns up to ten exact names and candidate evidence, `has_more`, and `next_offset`, within a 100-owner result window. This is not a global match count. Narrow or reformulate after that window.

`inspect_agent` reads six indexed eligible entries newest first, clipped to 1,000 characters each. Empty history is unavailable evidence, not proof that an owner has done no work.

## Delegation and runtime

`send_message_to_agent` now requires `action="reuse"` or `action="create"`. Reuse rejects unknown exact names; create rejects existing names. Invalid actions, names, and instructions are rejected before assignment logging or worker dispatch. No model-facing auto-create fallback remains.

The prompt asks the model to seek evidence before committing when ownership is missing or ambiguous. It permits direct reuse when evidence is already supplied. It does not demand a search every turn or impose a fabricated confidence threshold.

The existing six discovery calls, four discovery rounds, eight model rounds, batching, and `end_turn` guards remain. Strict grading still counts failed tool calls, including an invalid call followed by successful recovery.

## Verification and one-pass evaluation

Offline tests cover migration, recovery, Unicode, collisions, concurrency, bounded retrieval, explicit delegation, and real scripted runtime behavior. Retrieval and dispatch-decision coverage must reach 100% statements and branches. Original cases and graders are fingerprinted and unchanged.

Cold index construction is measured separately from fresh-process and warm lookups. Build processes have a 15-minute/4 GiB limit; routing has five minutes/4 GiB. Supervised temporary state belongs to the parent so a killed child cannot leave its database behind.

```bash
.venv/bin/python -m pytest evals/agent_overload -m 'not live and not routing_capacity and not indexed_capacity'

RUN_INDEX_CAPACITY=1 .venv/bin/python -m pytest evals/agent_overload/test_indexed_performance.py

RUN_LIVE_EVALS=1 EVAL_MAX_SPEND_USD=10 .venv/bin/deepeval test run \
  evals/agent_overload/test_indexed_comparison.py -m indexed_comparison
```

Before live execution, snapshot endpoint prices with the existing budget helper into `.deepeval/campaigns/indexed-routing-v1`, and freeze source/input hashes in `implementation_manifest.json`. The comparison runner refuses changed frozen inputs or implementation. Load the OpenRouter key into the environment without printing it.

The paid comparison runs 99 original full cases, 84 stress variants, and six inspection cases once, sequentially, using the same $10 ledger across interaction and judges. It adapts fixture storage through the public bulk-import API; it does not alter fixture expectations. Completed outcomes are not automatically rerun. Confirmed infrastructure corrections must be documented and limited to affected cases.

The report will separate behavioral changes, tool-error recoveries, cold-build cost, warm resource use, model charges, and unavailable outcomes. No tuning loop follows this first pass.
