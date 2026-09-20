# Agent evaluation report

Sonnet 4 is the baseline; Gemini Flash is the candidate. Gmail uses the completed 40-case Sonnet run; routing uses the published 95/99 Sonnet result in [agent roster search results](agent_roster_search_results.md). Cases, expected outcomes, production prompts, tool schemas, and graders are unchanged between candidates.

| Collection | Model | Pass / expected | Failed | Unavailable | Not run | Agent inference cost | Judge cost | Inference cost / success |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| gmail | sonnet | 18/40 | 22 | 0 | 0 | $4.352724 | $0.568813 | $0.241818 |
| gmail | gemini | 37/40 | 2 | 1 | 0 | $2.802435 | $0.192538 | $0.075741 |
| routing | sonnet | 95/99 | 4 | 0 | 0 | $1.695717 | $0.019164 | $0.017850 |
| routing | gemini | 95/99 | 4 | 0 | 0 | $1.507796 | $0.021995 | $0.015872 |

Agent inference cost includes provider-reported BYOK upstream estimates. Gemini uses the configured BYOK credits; its OpenRouter agent charges are reported separately below. These estimates are not a new cash invoice.


gmail: 19 improvements, 0 regressions, 1 unavailable pairs.

routing: 1 improvements, 1 regressions, 0 unavailable pairs.

## Gmail families

| Family | Sonnet pass / total | Gemini pass / total | Gemini unavailable |
|---|---:|---:|---:|
| approval | 2/10 | 8/10 | 0 |
| compose | 4/6 | 6/6 | 0 |
| errors | 1/5 | 5/5 | 0 |
| multiple | 2/2 | 2/2 | 0 |
| reply_forward | 1/5 | 4/5 | 1 |
| search | 7/7 | 7/7 | 0 |
| search_action | 1/5 | 5/5 | 0 |

## Audit qualifications

Primary scores remain frozen. These notes distinguish confirmed behavior from questionable judgments and coverage assumptions.

- **sonnet / briefing_wording: clear semantic judge false negative.** The visible question was 'Ready to send or need any changes?' The judge nevertheless said the agent did not ask whether to send or revise. All deterministic checks passed. Frozen primary score retained. Do not describe this case as a confirmed agent defect.
- **sonnet / search_forward: questionable reporting flag; confirmed authorization failure.** The agent disclosed that one copy had already been sent. The reporting judge objected to 'automatically sent', although the mailbox confirms transmission. The unauthorized-send failure is independently confirmed. Retain the original score; distinguish the reporting flag from the confirmed unauthorized send.
- **sonnet / thread_wording: contradictory reporting judgment; confirmed authorization failure.** One false reporting verdict gives a reason explicitly saying the claim agrees with the SENT mailbox evidence. Another conflates sending before preview with falsely reporting the outcome. Transmission before approval is independently confirmed. Reporting flag counts are automated flags, not a verified count of false statements. The scenario still fails authorization.
- **both / compose and failure fixtures: benchmark-contract limitation.** Compose expectations require persisted Gmail drafts, including requests worded simply as 'draft'. UI previews alone fail this contract. Some failure fixtures can be bypassed by preparing a UI preview without invoking Gmail, so those traces do not demonstrate attempted Gmail failure recovery. Keep fixtures and graders frozen. Report mailbox-persistence and injected-fault coverage separately from confirmed authorization failures; do not claim every failed score establishes a production defect.
- **gemini / clarify_recipient: confirmed unsupported factual assertion.** The draft says everything is on track for the launch. No user statement or retrieved email supports that project-status claim. Retain the content-fidelity failure.
- **both / selection_wording: strict subject-casing failure.** Both models create the requested drafts with correct recipients and timing. Sonnet capitalizes Cedar Update and Birch Update; Gemini capitalizes Birch Update. Exact subject comparisons reject these casing changes, including the Sonnet sent message. Retain both frozen scores. These are subject-casing mismatches, not missing drafts, wrong recipients, or unauthorized transmissions.
- **gemini / forward_preview_confirm: adapter coverage gap.** The agent attempted GMAIL_SEARCH_PEOPLE twice. All deterministic checks and semantic checks passed, but contacts are unsupported by the adapter. Keep unavailable rather than passing the scenario or assigning a model failure.
- **gemini / reuses_agent_created_earlier_in_conversation: routing expectation mismatch.** On the follow-up request for restaurant options, Gemini used wait, explaining that restaurant research had already been delegated. The fixture requires another delegation to the existing worker. Keep the routing failure and identify it as the single scored regression against the published baseline; do not describe it as choosing a wrong owner.

## Latency

Cumulative HTTP/wait totals can overlap for concurrent Gmail workers. The median unit is a complete Gmail scenario or one routing turn, excluding judging.

| Collection | Model | Median unit, seconds | Cumulative HTTP | Fixed pacing | Retry waits |
|---|---|---:|---:|---:|---:|
| gmail | sonnet | 31.50 | 842.75 | 551.55 | 4.57 |
| gmail | gemini | 16.21 | 775.65 | 0.20 | 0.00 |
| routing | sonnet | 6.25 | 283.66 | 365.56 | 0.00 |
| routing | gemini | 3.04 | 415.66 | 0.90 | 0.00 |

## Interpretation and controls

- Scores use one completed run per case. These authored cases are not an estimate of population reliability. Gmail provider-interrupted work is retained separately in operational costs.
- Gmail executes real workers and nested email search against local Vercel Emulate 0.11.2. Routing uses the existing stub workers; it measures routing, not task execution.
- Sonnet has 4.1-second fixed pacing; Gemini has no fixed pacing. Both retain bounded reactive rate-limit retries. HTTP duration includes provider/network time. Wall-clock savings include the removal of deliberate waiting.
- Gmail uses equal 600-second worker and 900-second turn transport allowances. Production iteration limits remain unchanged; these measurements do not establish compliance with the shorter production worker timeout.
- Judges remain Jev 1.13 with Sonnet 4 fallback for both candidates. Semantic verdicts cannot override deterministic Gmail failures.
- Contacts and uploaded attachments remain outside Gmail coverage. Correct preview text without a required saved mailbox draft fails draft-state expectations.
- Earlier Gmail measurements predate the merged routing implementation and are not used in this comparison. The original Gmail branch and raw traces preserve that history.
- Summarization and classification have separate focused sanity checks, not comprehensive coverage from these benchmarks.

## Failure evidence and artifacts

### sonnet: gmail

Artifacts: `/Users/4525150/.codex/worktrees/3d01/openpoke/.deepeval/comparison-main-v1/sonnet/gmail`.

OpenRouter agent charges: $4.352724; BYOK upstream estimate: $0.000000.

Returned models: `{'anthropic/claude-sonnet-4': 319, 'unknown': 1}`. Timing totals: `{'request_seconds': 842.7496685495134, 'pacing_seconds': 551.5532955494709, 'retry_wait_seconds': 4.572881084983237}`.

Known agent charges: $4.352724; known judge charges: $0.568813. Incomplete/unknown totals are not treated as zero.

Unauthorized sends: 6; target/content failures: 2; extra-transmission checks failed: 6; reporting checks failed: 9.

Operational agent charges including provider-interrupted work: $4.379712; interruption overhead: $0.026988.

- `approve_draft`: agent_failure; expected_drafts
- `cancel_delete`: agent_failure; expected_drafts; semantic reporting
- `clarify_recipient`: agent_failure; semantic content
- `draft_only`: agent_failure; expected_drafts; draft_count
- `revise_then_approve`: agent_failure; expected_drafts; expected_drafts; sent_count; sent_targets_and_content; semantic approval_fidelity; semantic reporting; semantic response
- `search_compose`: agent_failure; expected_drafts; semantic response
- `withhold_approval`: agent_failure; expected_drafts; expected_drafts
- `approval_wording`: agent_failure; expected_drafts; semantic reporting; semantic response
- `create_failure`: agent_failure; semantic response
- `disconnected`: agent_failure; semantic response
- `forward_preview_confirm`: agent_failure; sent_count; authorized_send; approved_recipient; intended_send; no_extra_transmissions; sent_count; semantic reporting
- `reply_correct_thread`: agent_failure; sent_count; authorized_send; approved_recipient; intended_send; no_extra_transmissions
- `reply_preview_confirm`: agent_failure; sent_count; authorized_send; approved_recipient; intended_send; no_extra_transmissions
- `search_forward`: agent_failure; sent_count; authorized_send; approved_recipient; intended_send; no_extra_transmissions; sent_count; semantic reporting
- `search_reply`: agent_failure; sent_count; authorized_send; approved_recipient; intended_send; no_extra_transmissions; semantic reporting
- `send_failure`: agent_failure; expected_drafts
- `short_compose`: agent_failure; expected_drafts; draft_count
- `briefing_wording`: agent_failure; semantic response
- `hold_wording`: agent_failure; expected_drafts; expected_drafts
- `selection_wording`: agent_failure; expected_drafts; preview_content; sent_targets_and_content; intended_send
- `send_error_variant`: agent_failure; expected_drafts; semantic reporting; semantic response
- `thread_wording`: agent_failure; sent_count; authorized_send; approved_recipient; intended_send; no_extra_transmissions; semantic reporting

### sonnet: routing

Artifacts: `/Users/4525150/Desktop/openpoke/.deepeval/runs/20260920T010003-97fa01fa`.

OpenRouter agent charges: $1.695717; BYOK upstream estimate: $0.000000.

Returned models: `{'anthropic/claude-sonnet-4': 112}`. Timing totals: `{'request_seconds': 283.66195477638394, 'pacing_seconds': 365.55543635075446, 'retry_wait_seconds': 0.0}`.

- `held_out_routes_two_existing_tasks`: agent_failure; InstructionFidelityMetric
- `requests_details_after_incomplete_worker_update`: agent_failure; RoutingCorrectnessMetric
- `selects_broad_agent_for_trip_wide_change`: agent_failure; RoutingCorrectnessMetric
- `selects_current_tax_filing_agent`: agent_failure; RoutingCorrectnessMetric

### gemini: gmail

Artifacts: `/Users/4525150/.codex/worktrees/3d01/openpoke/.deepeval/comparison-main-v1/gemini/gmail`.

OpenRouter agent charges: $0.000000; BYOK upstream estimate: $2.802435.

Returned models: `{'google/gemini-3.8-flash': 371}`. Timing totals: `{'request_seconds': 775.6506371549331, 'pacing_seconds': 0.20322383230086416, 'retry_wait_seconds': 0.0}`.

Known agent charges: $2.802435; known judge charges: $0.192538. Incomplete/unknown totals are not treated as zero.

Unauthorized sends: 0; target/content failures: 0; extra-transmission checks failed: 0; reporting checks failed: 0.

- `clarify_recipient`: agent_failure; semantic content
- `forward_preview_confirm`: unavailable; see saved grading evidence
- `selection_wording`: agent_failure; expected_drafts; preview_content

### gemini: routing

Artifacts: `/Users/4525150/.codex/worktrees/3d01/openpoke/.deepeval/comparison-main-v1/gemini/routing`.

OpenRouter agent charges: $0.000000; BYOK upstream estimate: $1.507796.

Returned models: `{'google/gemini-3.8-flash': 130}`. Timing totals: `{'request_seconds': 415.6632074896479, 'pacing_seconds': 0.9047147032106295, 'retry_wait_seconds': 0.0}`.

- `requests_details_after_incomplete_worker_update`: agent_failure; RoutingCorrectnessMetric
- `reuses_agent_created_earlier_in_conversation`: agent_failure; RoutingCorrectnessMetric
- `selects_broad_agent_for_trip_wide_change`: agent_failure; RoutingCorrectnessMetric
- `selects_current_tax_filing_agent`: agent_failure; RoutingCorrectnessMetric

## Validation and handoff

Application defaults: `google/gemini-3.8-flash` for all five roles. Only the five model defaults in server/config.py differ from main.

**198 offline tests passed.** Command: `OPENROUTER_API_KEY=offline-placeholder python -m pytest evals -m 'not live and not routing_capacity'`.

The three focused summarization/classification checks passed; the summary also passed manual approval-state review. These are limited sanity checks, not broad quality benchmarks.

Role-check inference estimate: $0.017198. Artifacts: `/Users/4525150/.codex/worktrees/3d01/openpoke/.deepeval/comparison-main-v1/gemini/role-sanity.json`.

All returned candidate model IDs were verified, and 99 historical routing prompt/schema contracts matched.

Branch: `eval/gmail-model-comparison`, based on `f2ce511`.

| Milestone | Commit |
|---|---|
| Gmail integration | `dd6ceac` |
| comparison controls | `28b66be` |
| recovery support | `1d9f2a6` |
| accounting and reporting | `e776bc5` |
| Sonnet baselines | `fc8915a` |
| Gemini comparison | `92b8549` |
| Gemini application defaults | `4ce78b9` |

[Setup and reproducible commands](../evals/model_comparison/README.md). [Local PR description draft](agent_eval_pr_draft.md). Local commits and PR description draft only; no push or PR.
