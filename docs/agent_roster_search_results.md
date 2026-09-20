# Agent roster search results

This report compares candidate-based routing with the preserved Sonnet 4 flat-roster baseline. The model, authored cases, generated rosters, expected decisions, and graders are unchanged. Results from unsuccessful experiments remain preserved; the final full-run score is not assembled from selectively rerun cases.

## Final full comparison

Same `anthropic/claude-sonnet-4`, unchanged provider sampling defaults, and all 99 scenarios / 102 turns. Every turn produced a saved result. There were no provider, judge, capacity, or iteration-limit failures.

| Measure | Preserved baseline | Final implementation |
| --- | ---: | ---: |
| Scenarios passing every turn | 93/99 | 95/99 |
| All-metric turn passes | 96/102 | 98/102 |
| Routing correctness | 99/102 | 99/102 |
| Instruction fidelity, reported metric | 97/100 | 99/100 |
| Input tokens | 2,391,805 | 475,239 |
| Output tokens | 20,527 | 18,000 |
| Interaction charges | $7.483320 | $1.695717 |
| Full run duration, including grading/pacing | 1,749.55 s | 943.00 s |

Interaction charges decreased **77.34%** and input consumption decreased **80.13%**. Every routing check that passed the baseline still passed. All three baseline semantic failures now pass, but one different semantic case fails; this is an aggregate improvement, not a claim of zero per-case regression.

The final run made 112 interaction-model calls: 93 turns used one call, eight used two, and one used three. Summed turn runtime was 657.74 seconds, including 365.56 seconds of pacing. HTTP request duration across interaction calls was 283.66 seconds. There were no discovery-budget closures.

Judge charges were $0.019163616 across 103 requests, making the reported total for this full run **$1.714880616**. Historical judge charges are unavailable and are not included in the savings comparison. The semantic metric includes two neutral results when there was no matching delegation to assess, as in the preserved baseline; those are not evidence of successful semantic checking.

### Matched roster scaling

Each row compares the same eight stress tasks at that roster size. No task mix changes between rows.

| Agents | All-metric passes, baseline → final | Input tokens, baseline → final | Interaction charges, baseline → final | Cost reduction |
| ---: | --- | ---: | ---: | ---: |
| 10 | 8/8 → 8/8 | 75,119 → 33,568 | $0.247017 → $0.120309 | 51.30% |
| 100 | 7/8 → 8/8 | 122,570 → 36,060 | $0.391710 → $0.130890 | 66.58% |
| 1,000 | 8/8 → 8/8 | 510,794 → 36,052 | $1.557432 → $0.130401 | 91.63% |

From 10 to 1,000 agents, final input consumption grew only 1.07× and charges grew 1.08×, versus 6.80× and 6.30× in the baseline. All 24 final stress cases passed. These are cumulative tokens and charges across eight tasks per row, not single-call context sizes. No live 10,000-agent claim is made.

### Remaining failures

| Case | Observed behavior | Baseline relationship |
| --- | --- | --- |
| `requests_details_after_incomplete_worker_update` | Reported the incomplete hotel update instead of requesting the missing details from its worker. | Same routing failure as baseline. It passed the first optimized full run but failed development and the final run, so it remains variable. |
| `selects_broad_agent_for_trip_wide_change` | Selected the broad trip owner plus hotel and restaurant owners; the fixture permits only the broad owner. | Same routing failure. The pre-existing tension with the prompt's parallelization rule remains. |
| `selects_current_tax_filing_agent` | Chose 2025 rather than the expected 2026 tax owner. | Same routing failure; tax period versus filing year remains ambiguous. |
| `held_out_routes_two_existing_tasks` | Selected both correct owners, but requested reminder setup rather than explicitly determining the rent due date. | Newly failing semantic check. “Remind me when rent is due” permits different interpretations, but the fixture requires the date lookup and the failed score is retained. |

The rent case is not excluded, regraded, or counted as a provider error. No scoring rules were changed to obtain these results.

## What changed

The interaction prompt now includes at most 20 candidate owners, selected from names and main conversation context. Small rosters remain fully visible. Candidates may include short verbatim initial/latest assignment excerpts from existing logs. Search and inspection remain available where useful, without a generated-summary pipeline or embedding service.

The model can explicitly end an interaction turn after dispatching work. All calls in the batch still execute, and the runtime requires successful tools, no outstanding discovery results, and a user-visible response before taking this shortcut. This avoids a redundant model call without waiting for execution workers to finish.

Savings therefore come from both less roster context and fewer interaction-model calls. This experiment does not isolate each contribution through a separate ablation run.

## Verification before the full run

The final implementation passed 95 offline tests. Discovery and prompt construction have 100% statement/branch coverage; new runtime and handler paths are exercised without imposing coverage requirements on unrelated legacy code. Scripted tests exercise actual tools and state isolation without model calls.

A read-only candidate-recall check retained an acceptable owner for all 86 named reuse expectations in the existing collection. That measures candidate availability, not model correctness. The production selector does not read expectations or case names.

Live verification proceeded through targeted gates before one development run and one full run:

| Experiment | All-metric passes | Interaction charges | Finding |
| --- | ---: | ---: | --- |
| Initial candidate list and optional completion flag: four development cases | 3/4 | $0.141114 | Empty-history inspection still displaced actual work; the model did not consistently end the turn. |
| Useful-tool visibility and explicit `end_turn`: two targeted cases | 2/2 | $0.028821 | Both completed in one model call, versus $0.071316 in their historical baseline. |
| Three matched 1,000-agent cases | 3/3 | $0.050346 | Baseline charges were $0.568839: 91.15% lower with the same routing and semantic outcomes. |
| Inspection cases before ownership excerpts | 3/6 | $0.098541 | The model sometimes delegated to multiple indistinguishable owners instead of inspecting. |
| The same inspection cases with ownership excerpts | 6/6 | $0.102975 | Recorded ownership evidence resolved the ambiguity without changing expectations. |
| Development gate before the final instruction-description refinement | 29/32 turns | $0.523989 | No new failures relative to matched historical cases. |
| First full verification | 97/102 turns | $1.689582 | Significant savings, but three hotel delegations omitted “more.” |
| Three hotel failures plus draft-only and multi-task controls after refining the instructions parameter | 5/5 | $0.076764 | Relevant task clauses retained their qualifiers and remained correctly scoped. |
| Final full verification | 98/102 turns | $1.695717 | Results reported above, from one complete run. |

These rows contain different case mixes and are an experiment ledger, not an aggregate performance trend. Judge charges are separate from the interaction charges shown here. The earlier search-only iteration and its failures remain documented in `agent_roster_search_development.md`.

### Development comparison

The development gate, before the final instruction-description refinement, passed 26/29 scenarios and 29/32 turns. The three failing turns were the same baseline failures: incomplete worker details, broad trip ownership, and tax year. On the 28 turns with exact historical case matches, routing and all-metric passes remained 25/28, while interaction charges fell from $0.931410 to $0.446262, a 52.09% reduction.

The four 100-agent development variants have different seeds from the preserved full baseline and are not treated as matched comparisons. All four passed in this run. Across the complete development suite, input was 141,638 tokens, output was 6,605 tokens, and 35 interaction-model calls were made. Judge charges were $0.017694714. Run duration was 280.73 seconds, including grading and pacing.

The final refinement changed only the production tool description: delegation instructions should copy the relevant user task clause and preserve quantities, qualifiers, and prohibitions verbatim. It did not append evaluator expectations or rewrite model outputs. Every hotel “more” case passed the final full run.

Total reported charges for the nine optimization-validation runs in the ledger were **$4.492041234**, including judges. This excludes the historical baseline and the preceding search-only implementation's validation. There was one development-suite run; the two full runs were each preceded by targeted evidence. Full scores are never combined with targeted rerun scores.

## Artifacts and integrity

- Preserved baseline: `.deepeval/baselines/sonnet4-full-20260919/results.json`.
- Baseline SHA-256: `5cb63ce449082513eae9a636b31940dea80536fc3d5be9664c9b23bc39feae17`.
- Development gate: `.deepeval/runs/20260920T002947-82d4be91/`.
- First full verification: `.deepeval/runs/20260920T003802-27232cb3/`.
- Targeted instruction-preservation check: `.deepeval/runs/20260920T005711-1ab671b4/`.
- Final full verification: `.deepeval/runs/20260920T010003-97fa01fa/`.

Per-run files retain model/tool trajectories, metrics, semantic judgments, provider usage and timing, and judge usage. Full DeepEval result files were archived before later offline checks. All final model responses identify `anthropic/claude-sonnet-4`. Case definitions and graders are unchanged from the previous feature milestone; baseline collection fingerprints remain intact. Execution workers stayed disabled and application data remained unchanged.

These artifacts are local and Git-ignored. The report is committed, and reproduction commands are in `agent_roster_search.md`.

## Interpretation limits

Lexical candidate selection may miss implicit relationships or synonyms. A shortlist is explicitly marked incomplete, and search remains available. Ownership excerpts can be truncated and are not live task results. They inherit the existing execution-log storage behavior; no storage migration was introduced.

The inspection cases demonstrate correct routing with recorded ownership evidence available. They do not establish that the model will always retrieve every needed older-history page. Pagination and inspection mechanics are covered deterministically.

Historical timing includes pacing. New HTTP timing includes transport and all attempts, not just model computation. Judge charges were not available for the historical full baseline and are excluded from interaction-cost comparisons. Recorded timestamps and model-generated intermediate conversation differ naturally between executions of the same authored scenarios.

A single full run is evidence for this fixed benchmark, not a guarantee of production reliability. Known ambiguous expectations remain scored rather than rewritten.
