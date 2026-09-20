# Indexed agent routing: first-pass results

One comparison pass with Sonnet 4, frozen production implementation, original fixtures, and unchanged graders. This measures the combined effect of indexed retrieval, additional ownership evidence, prompt instructions, and explicit reuse/create validation. It is not an ablation or a tuning study.

## Outcome

179/189 scenarios and 182/192 turns passed every check. All planned cases produced scored results; none were left unrun.

The main gain is faster large-roster routing and better access to recorded ownership evidence. Ownership challenges improved from 27/36 to 30/36 overall, with eight newly passing and five newly failing cases. At one million agents, the matched scale cases averaged 6.61 seconds per turn versus 25.23 seconds previously, excluding index construction. The original benchmark retained 98/102 overall passing turns, but one routing regression offset a semantic improvement, and interaction charges increased 8.59%.

| Collection | Scenarios passing | Routing checks | All checks by turn | Applicable semantic checks | Interaction charges | Model calls | Discovery calls |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 95/99 | 98/102 | 98/102 | 97/97 | $1.841415 | 117 | 3 |
| scale | 48/48 | 48/48 | 48/48 | 48/48 | $0.809868 | 48 | 0 |
| challenge | 30/36 | 33/36 | 30/36 | 30/33 | $0.843141 | 47 | 9 |
| inspection | 6/6 | 6/6 | 6/6 | 6/6 | $0.093375 | 6 | 0 |

Semantic applicability depends on matching the expected delegation. Neutral “no semantic requirement” scores and absent semantic metrics are excluded from that column; wrong routing remains a failed overall result. Compare end-to-end outcomes first, not semantic percentages on changing subsets.

## Original 99-case comparison

The control is the final bounded-roster run from PR #2 (`20260920T010003-97fa01fa`), not the older flat-roster implementation. Case definitions and the full-collection fingerprint remain unchanged. Matching uses case name and turn index, verifies the incoming message, and relies on the frozen fixture sources for the remaining initial state.

| Measure | Previous bounded roster | Indexed implementation |
|---|---:|---:|
| Routing checks | 99/102 | 98/102 |
| All checks by turn | 98/102 | 98/102 |
| Raw semantic metric scores | 99/100 | 100/100 |
| Applicable semantic checks | 97/98 | 97/97 |
| Input tokens | 475,239 | 518,990 |
| Interaction charges | $1.695717 | $1.841415 |

The historical raw semantic metric includes neutral passes. The applicable count removes them. A routing regression can reduce the number of semantic checks; a higher percentage alone is not proof of better instruction preservation.

## Paired improvements and regressions

### baseline

One newly passing turn; one newly failing turn.

New passes:

- `held_out_routes_two_existing_tasks[0]`

New failures:

- `reuses_existing_hotel_search_agent__roster_500_similar_250_seed_450[0]`

### scale

0 newly passing turns; 0 newly failing turns.

### challenge

8 newly passing turns; 5 newly failing turns.

New passes:

- `finds_owner_when_request_uses_different_words__challenge_02_10000[0]`
- `identifies_vaguely_named_owner_from_recorded_work__challenge_03_10000[0]`
- `uses_intermediate_assignment_to_identify_owner__challenge_04_100[0]`
- `uses_intermediate_assignment_to_identify_owner__challenge_04_1000000[0]`
- `finds_ownership_evidence_on_older_history_page__challenge_06_100[0]`
- `finds_ownership_evidence_on_older_history_page__challenge_06_10000[0]`
- `finds_ownership_evidence_on_older_history_page__challenge_06_1000000[0]`
- `discovers_missing_owner_for_second_followup__challenge_09_100[0]`

New failures:

- `uses_worker_response_to_identify_owner__challenge_05_100[0]`
- `uses_worker_response_to_identify_owner__challenge_05_10000[0]`
- `uses_worker_response_to_identify_owner__challenge_05_1000000[0]`
- `refines_search_after_plausible_wrong_matches__challenge_10_10000[0]`
- `refines_search_after_plausible_wrong_matches__challenge_10_1000000[0]`

Inspection cases are reported separately: their earlier six-case gate preceded the exact predecessor implementation used for the full comparison. They are not treated as a matched before/after control.

## Ownership challenges by size

| Scenario | 100 agents | 10,000 agents | 1,000,000 agents |
|---|---|---|---|
| `finds_owner_among_many_previously_mentioned_agents` | pass → pass | pass → pass | pass → pass |
| `recovers_owner_from_older_conversation_clues` | pass → pass | pass → pass | pass → pass |
| `finds_owner_when_request_uses_different_words` | pass → pass | fail → pass | fail → fail |
| `identifies_vaguely_named_owner_from_recorded_work` | pass → pass | fail → pass | pass → pass |
| `uses_intermediate_assignment_to_identify_owner` | fail → pass | pass → pass | fail → pass |
| `uses_worker_response_to_identify_owner` | pass → fail | pass → fail | pass → fail |
| `finds_ownership_evidence_on_older_history_page` | fail → pass | fail → pass | fail → pass |
| `follows_explicit_handoff_to_current_owner` | pass → pass | pass → pass | pass → pass |
| `distinguishes_recurring_tasks_by_specific_reference` | pass → pass | pass → pass | pass → pass |
| `discovers_missing_owner_for_second_followup` | fail → pass | pass → pass | pass → pass |
| `refines_search_after_plausible_wrong_matches` | pass → pass | pass → fail | pass → fail |
| `creates_agent_when_similar_agents_own_different_work` | pass → pass | pass → pass | pass → pass |

These are single samples per size. Changes in candidate sets and model sampling both affect paired outcomes; no monotonic scaling claim is made.

## Routing traces and guard behavior

### `requests_details_after_incomplete_worker_update[0]`

Initial owner coverage: `{'hotel_details': True}`.

- missing reuse delegation for hotel_details: Montreal Hotel Search
- Calls: send_message_to_user()

### `selects_broad_agent_for_trip_wide_change[0]`

Initial owner coverage: `{'trip': True}`.

- extra delegation: Montreal Hotel Search, Montreal Restaurant Reservations
- Calls: send_message_to_agent(Montreal Trip Planning) → send_message_to_agent(Montreal Hotel Search) → send_message_to_agent(Montreal Restaurant Reservations)

### `selects_current_tax_filing_agent[0]`

Initial owner coverage: `{'taxes': True}`.

- missing reuse delegation for taxes: 2026 Tax Documents; extra delegation: 2025 Tax Documents
- Calls: send_message_to_agent(2025 Tax Documents)

### `reuses_existing_hotel_search_agent__roster_500_similar_250_seed_450[0]`

Initial owner coverage: `{'hotels': False}`.

- missing reuse delegation for hotels: Montreal Hotel Search; extra delegation: Hotel Search Near Old Montreal
- Calls: send_message_to_agent(Hotel Search Near Old Montreal)

### `finds_owner_when_request_uses_different_words__challenge_02_1000000[0]`

Initial owner coverage: `{'owner': False}`.

- missing reuse delegation for owner: Westside Contract Termination; extra delegation: Fitness stuff: repair estimate, reservation QUIT
- Calls: send_message_to_agent(Fitness stuff: repair estimate, reservation QUIT)

### `uses_worker_response_to_identify_owner__challenge_05_100[0]`

Initial owner coverage: `{'owner': True}`.

- semantic requirements failed: required_0
- Calls: send_message_to_agent(Reservation Desk Birch)

### `uses_worker_response_to_identify_owner__challenge_05_10000[0]`

Initial owner coverage: `{'owner': True}`.

- semantic requirements failed: required_0
- Calls: send_message_to_agent(Reservation Desk Birch)

### `uses_worker_response_to_identify_owner__challenge_05_1000000[0]`

Initial owner coverage: `{'owner': True}`.

- semantic requirements failed: required_0
- Calls: send_message_to_agent(Reservation Desk Birch)

### `refines_search_after_plausible_wrong_matches__challenge_10_10000[0]`

Initial owner coverage: `{'owner': False}`.

- missing reuse delegation for owner: Boxroom Subscription Closure; extra delegation: Boxroom subscription cancellation follow-up
- Calls: send_message_to_agent(Boxroom subscription cancellation follow-up)

### `refines_search_after_plausible_wrong_matches__challenge_10_1000000[0]`

Initial owner coverage: `{'owner': False}`.

- missing reuse delegation for owner: Boxroom Subscription Closure; extra delegation: Cancellation stuff: membership renewal, reservation UPED
- Calls: send_message_to_agent(Cancellation stuff: membership renewal, reservation UPED)

No tool-validation failures, rejected duplicate creations, or recovered invalid calls occurred in this live pass. Their prevention is covered by deterministic tests, not demonstrated by a live rejection. Explicit reuse/create validation prevents accidental creation from an invalid reuse name; it does not prevent a model from intentionally choosing the wrong create action.

## What the traces establish

The strongest gain is access to ownership evidence. Intermediate assignments and old worker responses can now be retrieved directly, instead of requiring the model to infer an owner's name from a short roster profile. Correct routing without an inspection call is legitimate when the indexed excerpt already supplies that evidence. It does not establish that the model reliably uses inspection or pagination when the evidence is absent.

The discovery loop also recovered the Fernhaven owner from an older conversation clue after it was missing from the initial shortlist. The model searched for the named retreat and reused `Fernhaven Lodging`. This is a demonstrated recovery, not just a shortlist hit.

A remaining failure is committing before investigating. In the 10,000-agent Boxroom case, the owner was absent and the model created `Boxroom subscription cancellation follow-up` without searching. In the million-agent fitness case, it reused `Fitness stuff: repair estimate, reservation QUIT` rather than searching for the missing `Westside Contract Termination`. At one million agents, the Boxroom case also reused an unrelated cancellation-labelled owner without searching. These decisions passed the new tool's identity validation: one was a valid new name, the others existing but irrelevant owners. The guard cannot determine semantic ownership.

The original-suite hotel regression shows the same limitation: with the correct hotel owner absent from a 500-agent, similar-name shortlist, the model created a replacement. The original suite's overall all-check result remained 98/102 because a previous rent-date semantic failure passed while that routing case regressed. Routing fell from 99/102 to 98/102, and interaction cost increased from $1.695717 to $1.841415. This is not a zero-regression or lower-API-cost result on the original suite.

### Qualifications on recorded failures

The three late-checkout failures deserve grader scrutiny. In each size, routing selected `Reservation Desk Birch`, and the delegated instruction explicitly requested late checkout for `RAVEN-72`. The semantic judge still rejected `required_0`; Jev was followed by Sonnet fallback. The visible instruction appears consistent with the request, so these are possible grader false negatives, not strong evidence of lost intent. Their scores remain unchanged. The per-case artifacts retain metric verdicts and request usage, but not the fallback's detailed per-question explanation, limiting diagnosis.

The inherited broad-trip-owner and tax-year failures retain their documented expectation ambiguities: the prompt permits parallel independent work, and the tax fixture does not explicitly distinguish filing year from tax period. These should not be presented as unambiguous overload failures. See the [historical baseline qualifications](sonnet_4_full_baseline.md#routing-failures). No fixture or grader was changed to improve this run's scores.

### Next improvements supported by this run

- Improve behavior when ownership evidence is weak or an established owner is missing, especially before replacement creation or reuse of an incidental keyword match.
- Investigate retrieval misses involving synonyms and misleading reference tokens; measure candidate recall separately from the model's routing decision.
- Validate the semantic grader on the late-checkout delegation and retain its detailed question-level verdicts before drawing conclusions from those failures.
- Continue reducing broad-query latency and cold index cost. Persistent indexing avoids rebuilding on every application turn, but the measured million-agent index still has a real build and disk footprint.

These are follow-up candidates only. No retrieval weights, prompts, cases, or grading rules were tuned in response to the live results.

## Local resource costs

Measurements were taken on macOS 15.7.9, x86_64, Python 3.12.8, with 16 GiB physical memory. The cold/warm probe uses one fixed scale scenario at each roster size. Cold build includes legacy import and index construction. A fresh lookup process opens the completed database and repeats the same lookup three times. Its RSS excludes fixture generation and the cold-build process. These are distinct measurements, not interchangeable memory figures.

| Agents | Cold migration/build | Index size | Build-process peak RSS | Fresh lookup peak RSS | Mean warm shortlist | Mean warm search |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.014s | 0.1 MiB | 50.1 MiB | 50.0 MiB | 0.007s | 0.003s |
| 100 | 0.021s | 0.2 MiB | 50.2 MiB | 50.0 MiB | 0.007s | 0.004s |
| 1,000 | 0.062s | 0.7 MiB | 50.9 MiB | 51.1 MiB | 0.010s | 0.005s |
| 10,000 | 0.589s | 5.6 MiB | 63.8 MiB | 56.5 MiB | 0.033s | 0.016s |
| 100,000 | 5.485s | 55.2 MiB | 159.9 MiB | 89.8 MiB | 0.255s | 0.120s |
| 1,000,000 | 73.853s | 558.2 MiB | 643.6 MiB | 102.9 MiB | 2.966s | 1.385s |

The previous implementation averaged 18.5 seconds of ranking in its eight million-agent scale preflights, with 1.86 GiB maximum sampled process RSS. That broader process measurement includes setup, so it should not be compared directly to fresh-process RSS alone. SQLite removes the per-request Python roster scan and normalization, but broad queries still scale with matching postings and ranking work. Disk and cold-build costs are real; they are not included in warm lookup latency.

### Matched scale turns

| Agents | Mean live turn | Mean provider request time | Mean deliberate pacing | Mean fixture/index setup | Interaction charges |
|---:|---:|---:|---:|---:|---:|
| 10 | 3.136s | 2.906s | 0.058s | 0.040s | $0.127134 |
| 100 | 3.499s | 3.153s | 0.223s | 0.041s | $0.134295 |
| 1,000 | 3.314s | 3.074s | 0.108s | 0.080s | $0.137208 |
| 10,000 | 3.060s | 2.905s | 0.010s | 0.543s | $0.135996 |
| 100,000 | 3.252s | 2.848s | 0.011s | 5.949s | $0.138207 |
| 1,000,000 | 6.609s | 3.090s | 0.012s | 80.599s | $0.137028 |

Live turn time excludes index setup and semantic judging; it includes routing tools and deliberate pacing. Provider request time is HTTP duration, not isolated model compute. Every isolated live fixture builds its own index, whereas a running application reuses its persistent index.

## Shortlist coverage and recovery

A recovery is counted only when at least one required reuse owner was absent initially. Discovery counts are diagnostic; they are not required for a pass.

| Collection | Covered reuse tasks | Turns with all reuse owners shown | Routing recovery on incomplete shortlists | All-check recovery |
|---|---:|---:|---:|---:|
| baseline | 87/88 | 82/83 | 0/1 | 0/1 |
| scale | 48/48 | 42/42 | 0/0 | 0/0 |
| challenge | 24/36 | 23/33 | 7/10 | 7/10 |
| inspection | 7/7 | 6/6 | 0/0 | 0/0 |

## Token and charge accounting

| Collection | Interaction input / output tokens | Judge input / output tokens | Judge charges | Judge requests |
|---|---:|---:|---:|---:|
| baseline | 518,990 / 18,963 | 63,626 / 4,896 | $0.018008 | 102 |
| scale | 223,581 / 9,275 | 34,424 / 2,354 | $0.004900 | 49 |
| challenge | 245,407 / 7,128 | 40,604 / 2,878 | $0.043339 | 44 |
| inspection | 25,760 / 1,073 | 4,193 / 387 | $0.003231 | 7 |

Judge requests are counted once per actual request, including Jev batches and Sonnet fallback calls. Token counts are cumulative across requests; they are not per-call context size.

- `anthropic/claude-sonnet-4`: 18 judge requests, $0.063939.
- `typesafe/jev-1.13`: 184 judge requests, $0.005539.

## Paired scale comparison

Each row contains the same eight scenarios at the same size. Turn runtime includes deliberate pacing and excludes fixture construction and semantic judging.

| Agents | Previous / indexed all-check passes | Previous / indexed interaction charges | Previous / indexed mean turn runtime |
|---:|---:|---:|---:|
| 10 | 8/8 / 8/8 | $0.122184 / $0.127134 | 3.183s / 3.136s |
| 100 | 8/8 / 8/8 | $0.131823 / $0.134295 | 3.309s / 3.499s |
| 1,000 | 8/8 / 8/8 | $0.131013 / $0.137208 | 3.993s / 3.314s |
| 10,000 | 8/8 / 8/8 | $0.133773 / $0.135996 | 3.225s / 3.060s |
| 100,000 | 8/8 / 8/8 | $0.133206 / $0.138207 | 4.859s / 3.252s |
| 1,000,000 | 8/8 / 8/8 | $0.133758 / $0.137028 | 25.230s / 6.609s |

## Charges and operational interruptions

Recorded provider charges: **$3.657277**. One interrupted request has no receipt; its entire **$1.565304** maximum reservation remains counted against the cap, as explicitly approved. The campaign charge is therefore bounded above by **$5.222581**, within the $10 limit.

Laptop sleep interrupted the first request before its response was recorded. The initial unavailable attempts were archived; no scored outcomes from them are included. The runner was corrected to pause immediately on unsettled spending. A later HTTP 402 was a pre-generation rejection caused by API-key spending capacity; its charge is zero, and only that rejected case was retried after the user adjusted the limit. A later laptop closure caused DNS resolution to fail before a connection could be made; that request was recorded as uncharged, archived separately, and retried after connectivity returned. Completed evaluated cases were retained through all resumptions.

Production retrieval, prompts, schemas, and grading inputs remained frozen. Supervision, cleanup, and billing-recovery changes did not alter model inputs. No behavioral failure was rerun to seek a better score.

## Validation and limitations

All 183 offline tests passed. The same run measured coverage: discovery and delegation decision code each reached 100% statements and branches; prompt construction reached 100%; touched runtime and tool modules were 88% and 90% respectively. Tests cover migration, interrupted updates, exact identities, legacy collisions, import isolation, concurrent creation, bounded queries, real scripted runtime flows, explicit delegation, and spending guards. Historical benchmark inputs and graders were preserved.

An import-isolation issue discovered before paid execution temporarily initialized the local roster catalog. The legacy JSON was restored byte-for-byte and journals were verified unchanged. Eager logging-store initialization was removed and a subprocess import test now guards against recurrence. Derived incident catalogs remain local and untracked.

The million-agent fixtures are synthetic name populations with sparse authored histories. They do not represent a million fully populated history journals or concurrent production traffic. A single run cannot separate the effects of retrieval, additional evidence, prompting, and the new tool contract. Correct outcomes without discovery do not prove reliable history inspection.

The final scored set had no provider-unavailable, context-capacity, resource-limit, judge-error, harness-error, discovery-budget, or overall-iteration failures. There were 12 search calls and zero inspection calls. Thus, the six inspection-labelled cases validate their routing outcomes, but do not demonstrate live inspection-tool use.

Validation commands:

```bash
DEEPEVAL_TELEMETRY_OPT_OUT=1 .venv/bin/python -m pytest evals/agent_overload \
  -m "not live and not routing_capacity and not indexed_capacity" \
  --cov=server.services.execution --cov=server.agents.interaction_agent --cov-branch
.venv/bin/python -m pytest evals/agent_overload/test_indexed_comparison.py \
  --collect-only -q -m indexed_comparison
git diff --check
```

Collection confirmed 189 live scenarios. Frozen-source verification checked 79 files, and protected-data verification checked 13 fixture/grader/data hashes, excluding volatile SQLite WAL/SHM files.

## Artifacts

Local artifacts: `.deepeval/campaigns/indexed-routing-v1/`. `implementation_manifest.json` freezes production/input hashes; `spend.json` retains every request and the unresolved reservation; `live/` contains per-case traces and metrics; `performance/` contains cold/warm measurements. Interrupted, payment-rejected, and DNS-rejected attempts are archived separately.

See [implementation and commands](indexed_agent_routing.md) and [per-case comparison measurements](indexed_agent_routing_results.json).
