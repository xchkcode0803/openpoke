# Sonnet 4 Full Baseline

## Run

- Date: September 19, 2026
- Model: `anthropic/claude-sonnet-4` through OpenRouter
- Command: `RUN_LIVE_EVALS=1 .venv/bin/deepeval test run evals/agent_overload/test_routing.py -m full`
- Suite: 99 scenarios, 102 evaluated turns
- Runtime: 1,749.55 seconds (29 minutes 10 seconds)
- Completed turns: 102; provider and capacity failures: 0

## Results

| Measure | Result |
| --- | ---: |
| All required metrics pass | 96 / 102 (94.12%) |
| Scenarios with every turn passing | 93 / 99 (93.94%) |
| Deterministic routing correctness | 99 / 102 (97.06%) |
| Semantic fidelity | 97 / 100 (97.00%) |
| Reported interaction cost | $7.483320 |
| Input tokens | 2,391,805 |
| Output tokens | 20,527 |
| Mean turn runtime | 12.72 seconds |

Reported cost and tokens cover interaction-model calls. Semantic judge cost is not available in the saved DeepEval result and is excluded from the reported total.

The original artifact is preserved locally at `.deepeval/baselines/sonnet4-full-20260919/results.json`. These are the original scores; cleanup did not rerun the model or change expectations. This single run is not a statistical reliability estimate.

## Matched stress comparisons

Each row contains the same eight stress tasks, with only the roster scaled.

| Agents | Routing pass | All metrics pass | Cumulative input tokens | Output tokens | Interaction cost | Mean paced turn runtime |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 8/8 | 8/8 | 75,119 | 1,444 | $0.247017 | 10.60 s |
| 100 | 8/8 | 7/8 | 122,570 | 1,600 | $0.391710 | 11.87 s |
| 1,000 | 8/8 | 8/8 | 510,794 | 1,670 | $1.557432 | 12.49 s |

Across the matched tasks, input consumption grew 6.80 times and interaction cost 6.30 times from 10 to 1,000 agents while routing scores stayed constant. Tokens are summed across tasks and repeated model calls, not the size of a single prompt. Runtime includes request pacing; the historical result does not isolate pure provider latency. The larger aggregate table below mixes different tasks and should not be read as a controlled scaling comparison.

## Results by roster size

| Roster size | Turns | All metrics pass | Interaction cost | Mean turn runtime |
| ---: | ---: | ---: | ---: | ---: |
| Authored rosters (0–4 agents) | 34 | 31 / 34 | $1.130451 | 12.21 seconds |
| 10 | 12 | 12 / 12 | $0.394803 | 11.50 seconds |
| 50 | 4 | 4 / 4 | $0.170682 | 13.45 seconds |
| 100 | 12 | 11 / 12 | $0.574932 | 12.33 seconds |
| 250 | 4 | 4 / 4 | $0.288276 | 14.82 seconds |
| 500 | 24 | 22 / 24 | $2.636577 | 13.66 seconds |
| 1,000 | 12 | 12 / 12 | $2.287599 | 12.94 seconds |

The eight paired stress scenarios at 1,000 agents all passed. At 100 agents, one stress case failed semantic fidelity; at 500, two similar-roster variants failed semantic fidelity. Routing selection was correct in all three of those cases.

## Failures

### Routing failures

| Case | What happened |
| --- | --- |
| `requests_details_after_incomplete_worker_update` | Did not return the incomplete hotel-result update to `Montreal Hotel Search`. |
| `selects_broad_agent_for_trip_wide_change` | Selected the correct broad owner, `Montreal Trip Planning`, AND the hotel and restaurant workers. The extra delegations failed the fixture, but the prompt encourages parallel work; this is an expectation ambiguity, not a demonstrated inability to find the owner. |
| `selects_current_tax_filing_agent` | Reused `2025 Tax Documents` rather than expected `2026 Tax Documents`. The request says only “this year's tax filing.” Conversation timestamps supply the current year, but a filing performed this year may cover the previous tax year. The fixture does not explicitly establish the intended tax period. |

### Semantic-grader failures with correct routing

| Case | Grader result | Interpretation |
| --- | --- | --- |
| `reuses_existing_hotel_search_agent__roster_500_similar_100_seed_501__target_first` | Omitted “more” from delegated instructions | Correctly reused the hotel worker, but the instructions no longer explicitly require additional options. Downstream duplication was not tested. |
| `reuses_existing_hotel_search_agent__roster_500_similar_100_seed_501__shuffle_401` | Omitted “more” from delegated instructions | The user-facing reply preserved “more”; the worker instruction did not. Correct ownership does not prove preservation of this requirement. |
| `reuses_original_email_agent_despite_similar_names__roster_100` | Omitted explicit no-send phrase | Correctly reused the lease worker and requested a draft, but did not relay the explicit restriction. No actual send or downstream behavior was tested. |

Keep these semantic failures in the recorded score. They identify possible instruction loss, not wrong-agent selection, and the traces do not justify automatically dismissing them as grader mistakes.

## Observed trajectory

The run does not show monotonic routing degradation as roster size increases. The active 1,000-agent paired stress cases passed, and all generated unrelated-roster growth cases passed. The observed routing failures occur in authored small-roster scenarios involving incomplete worker updates, broad-versus-narrow task ownership, and year-specific document ownership.

The strongest measured opportunity is reducing roster-related input tokens and cost while preserving routing quality. The three deterministic failures are fixture failures with the qualifications above, not three proven overload-induced errors. This run did not test 10,000 or 20,000 agents or establish a context-window breaking point. Larger rosters create a capacity risk, but that limit remains unmeasured.
