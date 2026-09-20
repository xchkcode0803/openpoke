# Difficult agent-routing stress results

Sonnet 4, unchanged production routing and graders, on `eval/difficult-agent-routing`. This is one sequential live sample of each finalized variant, not a statistical reliability estimate. The original 99-case benchmark was preserved and was not rerun.

## Results

75/84 variants passed every check. All 48 scale variants and all 36 ownership variants have recorded outcomes. Total provider-reported campaign charges were **$1.627566**, below the $10 cap.

| Collection | Agents | All checks | Routing | Semantic* | Input tokens | Output tokens | Interaction cost | Model calls | Discovery calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| scale | 10 | 8/8 | 8/8 | 8/8 | 33,648 | 1,416 | $0.122184 | 8 | 0 |
| scale | 100 | 8/8 | 8/8 | 8/8 | 36,246 | 1,539 | $0.131823 | 8 | 0 |
| scale | 1,000 | 8/8 | 8/8 | 8/8 | 36,371 | 1,460 | $0.131013 | 8 | 0 |
| scale | 10,000 | 8/8 | 8/8 | 8/8 | 36,491 | 1,620 | $0.133773 | 8 | 0 |
| scale | 100,000 | 8/8 | 8/8 | 8/8 | 36,542 | 1,572 | $0.133206 | 8 | 0 |
| scale | 1,000,000 | 8/8 | 8/8 | 8/8 | 36,501 | 1,617 | $0.133758 | 8 | 0 |
| challenge | 100 | 9/12 | 9/12 | 10/10 | 68,668 | 2,258 | $0.239874 | 14 | 2 |
| challenge | 10,000 | 9/12 | 9/12 | 9/9 | 84,332 | 2,367 | $0.288501 | 17 | 4 |
| challenge | 1,000,000 | 9/12 | 9/12 | 9/9 | 79,142 | 2,199 | $0.270411 | 16 | 3 |

*Semantic checks only cover matched expected delegations. Wrong-owner cases with no matching delegation receive the existing neutral “no semantic requirement” result and are excluded from this denominator. Partial multi-task matches can receive semantic grades even when routing fails. End-to-end pass counts remain authoritative.

## Paired outcomes

Each row keeps the same request, ownership evidence, and expected decisions across sizes. Background populations are nested. These are different scenario mixes between scale and challenge groups; do not compare their aggregate totals as a scaling effect.

### Scale scenarios

| Scenario | 10 | 100 | 1,000 | 10,000 | 100,000 | 1,000,000 |
|---|---|---|---|---|---|---|
| `reuses_original_email_agent_despite_similar_names` | Pass | Pass | Pass | Pass | Pass | Pass |
| `selects_trip_agent_using_conversation_context` | Pass | Pass | Pass | Pass | Pass | Pass |
| `distinguishes_same_person_different_requests` | Pass | Pass | Pass | Pass | Pass | Pass |
| `distinguishes_same_task_different_dates` | Pass | Pass | Pass | Pass | Pass | Pass |
| `prefers_context_owner_over_keyword_match` | Pass | Pass | Pass | Pass | Pass | Pass |
| `returns_to_previous_task_after_topic_changes` | Pass | Pass | Pass | Pass | Pass | Pass |
| `routes_multiple_followups_to_their_existing_owners` | Pass | Pass | Pass | Pass | Pass | Pass |
| `creates_agent_when_similar_names_have_different_purposes` | Pass | Pass | Pass | Pass | Pass | Pass |

### Ownership challenges

| Scenario | 100 | 10,000 | 1,000,000 |
|---|---|---|---|
| `finds_owner_among_many_previously_mentioned_agents` | Pass | Pass | Pass |
| `recovers_owner_from_older_conversation_clues` | Pass | Pass | Pass |
| `finds_owner_when_request_uses_different_words` | Pass | Routing fail | Routing fail |
| `identifies_vaguely_named_owner_from_recorded_work` | Pass | Routing fail | Pass |
| `uses_intermediate_assignment_to_identify_owner` | Routing fail | Pass | Routing fail |
| `uses_worker_response_to_identify_owner` | Pass | Pass | Pass |
| `finds_ownership_evidence_on_older_history_page` | Routing fail | Routing fail | Routing fail |
| `follows_explicit_handoff_to_current_owner` | Pass | Pass | Pass |
| `distinguishes_recurring_tasks_by_specific_reference` | Pass | Pass | Pass |
| `discovers_missing_owner_for_second_followup` | Routing fail | Pass | Pass |
| `refines_search_after_plausible_wrong_matches` | Pass | Pass | Pass |
| `creates_agent_when_similar_agents_own_different_work` | Pass | Pass | Pass |

## Initial context and recovery

| Challenge size | Reuse tasks in initial shortlist | Missing-owner tasks routed correctly | Missing-owner tasks recovered in turns using discovery |
|---|---:|---:|---:|
| 100 | 9/12 | 2/3 | 2/3 |
| 10,000 | 6/12 | 4/6 | 2/6 |
| 1,000,000 | 7/12 | 4/5 | 4/5 |

Recovery counts are per task, not per scenario. A turn using discovery does not by itself prove that every recovered owner was found through that tool; inspect the trace. Coverage counts candidate entries, not names mentioned elsewhere. Direct reuse of a name supplied in conversation or assignment excerpts can be valid. Correct guesses also pass the existing outcome-based grader. Passing a hidden-history case without inspection therefore does not demonstrate reliable history retrieval.

Across the 36 challenge turns, there were seven search calls and two inspection calls. Both inspections occurred in the 10,000-agent intermediate-assignment case: the model inspected Amber and Indigo, then selected Indigo correctly. The older-conversation clue case recovered its owner through search at all three sizes. The older-history-page case never inspected and failed at all three sizes.

The missing-owner multi-task case created a duplicate at 100 agents, directly reused the correct names at 10,000, and used search at one million. Those different traces matter even though two of the three outcomes passed.

## Failure traces

### `challenge_02_10000`

Initial owner coverage: `{'owner': False}`.

- missing reuse delegation for owner: Westside Contract Termination; extra delegation: Westside Membership renewal — Maya, 2025-06, ref BKAM
- Trace: send_message_to_agent(Westside Membership renewal — Maya, 2025-06, ref BKAM)

### `challenge_02_1000000`

Initial owner coverage: `{'owner': False}`.

- missing reuse delegation for owner: Westside Contract Termination; extra delegation: 2030 records / Cancellation / Repair estimate / CLUB
- Trace: send_message_to_agent(2030 records / Cancellation / Repair estimate / CLUB)

### `challenge_03_10000`

Initial owner coverage: `{'owner': False}`.

- missing reuse delegation for owner: Notes Juniper; extra delegation: Apartment deposit dispute follow-up
- Trace: send_message_to_agent(Apartment deposit dispute follow-up)

### `challenge_04_100`

Initial owner coverage: `{'owner': True}`.

- missing reuse delegation for owner: Travel Desk Indigo; extra delegation: Travel Desk Amber
- Trace: send_message_to_agent(Travel Desk Amber)

### `challenge_04_1000000`

Initial owner coverage: `{'owner': True}`.

- missing reuse delegation for owner: Travel Desk Indigo; extra delegation: Travel Desk Amber
- Trace: send_message_to_agent(Travel Desk Amber)

### `challenge_06_100`

Initial owner coverage: `{'owner': True}`.

- missing reuse delegation for owner: Housing Desk Elm; extra delegation: Housing Desk Ash
- Trace: send_message_to_agent(Housing Desk Ash)

### `challenge_06_10000`

Initial owner coverage: `{'owner': True}`.

- missing reuse delegation for owner: Housing Desk Elm; extra delegation: Housing Desk Ash
- Trace: send_message_to_agent(Housing Desk Ash)

### `challenge_06_1000000`

Initial owner coverage: `{'owner': True}`.

- missing reuse delegation for owner: Housing Desk Elm; extra delegation: Housing Desk Ash
- Trace: send_message_to_agent(Housing Desk Ash)

### `challenge_09_100`

Initial owner coverage: `{'owner': True, 'parcel': False}`.

- missing reuse delegation for parcel: Northstar Parcel Claim; extra delegation: Northstar Damaged Parcel Claim
- Trace: send_message_to_agent(Oslo Hotel Booking) → send_message_to_agent(Northstar Damaged Parcel Claim)

## Resource and latency measurements

Offline capacity checks completed for all 48 scale variants and all 36 challenge preflights under the five-minute and 4 GiB limits. Peak memory is sampled process RSS, not an exact allocation peak. Fixtures are generated and loaded in separate child processes; their startup and fixture costs are not user-facing model latency. Live turn runtime includes production prompt construction, tools, HTTP requests, and deliberate pacing, but excludes fixture setup and semantic judging.

| Agents | Mean local ranking | Mean local search | Maximum sampled RSS | Mean live turn | Mean provider request time | Mean deliberate pacing |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.000s | 0.000s | 0.105 GiB | 3.183s | 2.669s | 0.430s |
| 100 | 0.002s | 0.001s | 0.105 GiB | 3.309s | 2.614s | 0.613s |
| 1,000 | 0.013s | 0.012s | 0.108 GiB | 3.993s | 3.206s | 0.694s |
| 10,000 | 0.140s | 0.131s | 0.121 GiB | 3.225s | 2.759s | 0.162s |
| 100,000 | 1.669s | 1.667s | 0.275 GiB | 4.859s | 2.979s | 0.004s |
| 1,000,000 | 18.502s | 17.088s | 1.862 GiB | 25.230s | 3.195s | 1.256s |

Environment: macOS-15.7.9-x86_64-i386-64bit; Python 3.12.8; reported machine memory 17179869184 bytes. HTTP durations are not pure model compute time.

## Cost and availability

- Finalized variants: $1.584543 interaction charges and $0.026752 judge charges.
- Superseded fixture run, preserved separately: $0.016271.
- Total: $1.627566; 180 recorded provider attempts; 1 rate-limit response retried.
- Outcome statuses: `{'passed': 75, 'failed': 9}`. No remaining reservations, budget-stop condition, unavailable cases, judge errors, or harness failures.

Current endpoint pricing was snapshotted before paid execution. Requests were sequential and used the existing shared pacing/retries. The ledger covers interaction, Jev, and Sonnet fallback requests. No paid reruns were performed to improve scores.

## Fixture correction and validation

One fixture defect was corrected after the first small run: the older-history case originally exposed a negative requirement in the other agent’s assignment profile, making the answer inferable without reading older history. That clue was moved to a recorded response, leaving both visible profiles generic. The expected owner and task were unchanged. Only that case was rerun. The original passing trace and its charges remain in `superseded/older_history_profile_hint/`; the finalized case failed at 100 agents. The source-manifest revision records the change.

**149 offline tests passed.** A separate audit regenerated all 20 million-agent populations and verified exact size, uniqueness, preserved owners, nested 10,000-agent membership, and fingerprints matching their preflights. Hash checks confirmed 77 protected production/data/baseline files were unchanged. All 95 recorded interaction responses identified `anthropic/claude-sonnet-4`. No discovery-budget or iteration-limit exhaustion occurred.

Offline checks cover frozen baseline membership, deterministic nested populations, scripted discovery feasibility, watchdog limits, process cleanup, scoped provider patches, persistent budget accounting, and retry handling. Production routing, prompts, model configuration, graders, and historical baseline artifacts are unchanged.

## Interpretation and next improvements

- The scale ladder measures synthetic name-population growth. Its successful routing does not establish production reliability or cheap local computation at one million agents.
- The ownership challenges reveal premature dispatch: selecting an ambiguous owner without consulting history, selecting a keyword match for different work, or creating a duplicate agent when an owner is missing from the shortlist.
- Discovery can recover missing or ambiguous ownership, but it is not used consistently. The paired outcomes are not monotonic with size; candidate changes and model sampling both vary. One run cannot separate those causes.
- Next improvements to investigate are evidence-sensitive routing before early completion, safer handling of unknown names when continuing existing work, and avoiding repeated full-roster normalization/scoring. No such changes were made in this benchmark branch.
- Generator choices are correlated: eight of the twelve catalogued people appear in rendered names, and references supply much of the million-name uniqueness. Population size is not equivalent to semantic diversity. The frozen generator was retained after this audit; future population changes need a new version and fresh measurements.
- Background agents mostly have no recorded histories. This does not measure a million populated history files, concurrent users, or storage contention. The naming population is synthetic; the ownership situations are authored. A more realistic production sample and counterbalanced/repeated ownership cases would strengthen generalization evidence.

## Artifacts

Campaign: `.deepeval/campaigns/difficult-routing-v1/`. Each variant has its roster fingerprint, reconstruction metadata, capacity/process measurements, live outcome, and full available model/tool traces. `spend.json` and `pricing_evidence.json` support the cost totals; `fixtures.json`, `source_manifest.json`, and `fixture_revision.json` identify the authored inputs and correction. Artifacts are local and Git-ignored; the fixture source and this report are committed. See [benchmark commands and implementation](difficult_agent_routing.md).

Per-case tokens, charges, latency, memory, coverage, and failure reasons are also committed in [the measurement summary](difficult_agent_routing_results.json). Full traces remain in the local campaign directory.
