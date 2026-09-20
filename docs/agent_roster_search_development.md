# Agent roster search: development evaluation

This report evaluates the first search-and-inspection implementation on Sonnet 4. It compares unchanged development cases with preserved flat-roster results and separately evaluates six new history-based scenarios. It is one run, not a reliability estimate.

## Implementation and validation

The interaction prompt contains the roster count instead of every name. Search matches all query words against names and returns ten candidates per page. Inspection returns six recorded assignments/responses per page. Discovery is limited to six invocations during the first four model rounds; the overall eight-model-call limit is unchanged.

Offline validation passed 79 tests. The discovery module and prompt builder reached 100% statement/branch coverage. All newly introduced runtime budget branches and changed executable lines in the production tool handlers were covered. Coverage including legacy code was 88% for the runtime and 86% for tool handlers. Remaining gaps belong to unchanged code. Only existing FastAPI lifespan deprecation warnings were emitted by the final offline run.

The 99-case full collection and 29-case standard collection retain their original inputs and expectations. Six inspection cases are separate. Scripted integration tests invoke no real model and disable execution workers.

## Inspection cases

The six inspection cases produced one routing pass and five routing failures. No provider or judge errors occurred. Sonnet made six search calls across the suite and **never called inspection**.

| Scenario | Result | Observed behavior |
| --- | --- | --- |
| Same person, different assignments | Fail | Searched for increasingly incomplete combinations of birthday/dinner terms, but never broadened to `Maya`; created a new dinner agent. |
| Similar names, different previous work | Fail | Skipped discovery and created a Montreal conference agent. |
| Relevant assignment on an older page | Fail | Searched names for balcony/private terms, did not broaden to apartment, and created a new agent. |
| Known owner without recorded history | Pass | Reused the exact dental owner established in the conversation. |
| Updated assignment scope | Fail | Searched for Lisbon flight terms that did not occur in the generic owner names, then created another flight agent. |
| Multiple owners | Fail | Skipped discovery and created separate hotel and restaurant agents. |

The traces confirm the discovery instructions and both tool schemas were supplied. These are behavioral failures of this first iteration; the fixtures and expectations were not weakened. The run does not demonstrate that the model can use inspection or older-history pagination successfully. Those mechanisms passed deterministic tests, but live use was absent.

Interaction usage: 102,890 input tokens, 1,795 output tokens, 25 model calls, and $0.335595 in reported interaction charges. One Jev request cost $0.000025158. Summed turn runtime was 99.65 seconds and includes request pacing.

The semantic metric returned its existing neutral score for the five cases without a matching expected delegation. Those are **not five successful semantic judgments**. Only the correctly routed dental case received semantic evaluation and passed.

## Historical comparison method

The preserved baseline is `.deepeval/baselines/sonnet4-full-20260919/results.json`, SHA-256 `5cb63ce449082513eae9a636b31940dea80536fc3d5be9664c9b23bc39feae17`.

Twenty-eight standard-suite turns have historical matches. Incoming messages, initial conversation content, initial rosters, actions, and frozen case definitions were checked. Runtime-generated timestamps differ between runs, and later turns may inherit different model-generated agent names.

Four 100-agent development variants have no exact historical match because their generated rosters use different seeds. Their results are reported separately; they cannot establish a measured paired cost reduction at 100 agents. No 1,000-agent live evaluation was run here.

Historical charges exclude judges. New judge charges are recorded separately. Historical turn durations include pacing, so they must not be compared directly with new HTTP-only timings. New HTTP durations include networking and retries, not just model computation.

## Standard development results

The complete standard run finished in 553.96 seconds (9 minutes 14 seconds). All 32 turns across 29 scenarios produced saved results. There were no provider errors, judge errors, or overall iteration-limit failures.

| Measure | Result |
| --- | ---: |
| Scenarios with every turn passing | 15 / 29 |
| Turns passing all required metrics | 18 / 32 |
| Routing correctness | 18 / 32 |
| Input tokens | 461,016 |
| Output tokens | 8,013 |
| Reported interaction charges | $1.503243 |
| Reported judge charges | $0.010860972 |
| Interaction model calls | 112 |
| Discovery calls | 22: 16 searches, 6 inspections |
| Summed turn runtime, including pacing | 473.53 seconds |
| HTTP request duration across interaction attempts | 212.65 seconds |
| Interaction pacing waits | 256.09 seconds |
| Retry waits | 0 seconds |

Nineteen Jev requests and three Sonnet fallback requests account for the 22 judge requests. All judge requests reported cost. Together, the inspection and standard runs cost **$1.849724130**, including reported interaction and judge charges.

The semantic metric recorded 29/30 passing scores, but eleven are its existing neutral result when no expected delegation could be matched. Only 19 turns received semantic judgments, of which 18 passed. The two remaining turns require no semantic metric. These different populations must not be interpreted as preserved overall instruction fidelity.

The one semantic failure occurred in `routes_existing_and_new_task`: both assignments were sent to newly created agents instead of reusing the existing dinner owner. The current grader matched the first creation to the expected coffee-grinder task and assessed it against that requirement. This overlaps with the routing error and is not independent evidence that the coffee-grinder instructions themselves lost meaning. No grader scores were changed.

### Matched development turns

These are the same 28 turns from 25 authored scenarios, all with small rosters. The four 100-agent variants are excluded from this comparison.

| Measure | Flat-roster baseline | Search iteration | Change |
| --- | ---: | ---: | ---: |
| Routing passes | 25 / 28 | 17 / 28 | 8 fewer |
| All-metric passes | 25 / 28 | 17 / 28 | 8 fewer |
| Input tokens | 282,685 | 390,319 | +38.08% |
| Output tokens | 5,557 | 6,708 | +20.71% |
| Interaction charges | $0.931410 | $1.271577 | +36.52% |
| Summed paced turn runtime | 339.55 s | 399.05 s | +17.52% |

This iteration did not improve the measured development baseline. Adding tool descriptions and discovery rounds can cost more than exposing a small roster. The run also shows that removing the roster makes correct ownership depend on searches the model does not reliably perform. Historical model-call counts and HTTP-only latency were not preserved and are not reconstructed from tool counts.

### Eight newly failing matched turns

| Case | What happened |
| --- | --- |
| `selects_agent_from_unrelated_roster` | Searched for `Maya dinner reservation`, got no match, and created `Maya Dinner Check` instead of broadening the query. |
| `routes_two_existing_tasks` | Reused the flight owner but skipped discovery and created a rent checker instead of using `Monthly Rent Reminder`. |
| `preserves_draft_only_restriction` | Asked the user for repair/recipient details instead of finding the existing landlord-email owner. No email was sent. |
| `routes_existing_and_new_task` | Created a new dinner agent alongside the grinder research instead of reusing the dinner owner. |
| `uses_latest_topic_after_user_correction` | Searched for hotels after the user switched to flights, then created a travel agent. |
| `reuses_agent_created_earlier_in_conversation`, turn 2 | Added Toronto to the search query, failed to find the agent created earlier, and created another dinner agent. |
| `selects_specialized_agent_over_broad_agent` | Skipped discovery and created `Old Montreal Hotel Search` rather than reusing `Montreal Hotel Search`. |
| `accepts_either_equivalent_agent` | Skipped discovery and created an electricity finder despite two acceptable existing owners. |

No previously failing matched turn became a pass. Three baseline failures persisted: the incomplete worker update, the broad trip-owner case, and the tax-year case. The broad-owner failure now involved no delegation after unsuccessful searches; historically it involved extra delegation. The original broad-owner and tax-year expectation ambiguities still apply and were not changed.

### Four unmatched 100-agent variants

| Case | Routing / overall result |
| --- | --- |
| Existing hotel search | Fail: created a different hotel agent without searching. |
| New work unrelated to existing travel agents | Pass. |
| Pronoun follow-up | Fail: found candidate owners, inspected empty histories, and created a new outbound-message task instead of checking the existing thread. |
| Two existing tasks | Fail: reused flights but created a rent checker. |

These four turns used 70,697 input tokens, 1,305 output tokens, 17 model calls, and $0.231666 in interaction charges. They passed 1/4 routing checks. There is no exact historical cost comparison for these seeds.

The pronoun case illustrates a limitation of adding inspection to the original fixtures: execution histories are empty unless explicitly seeded, even when the main conversation establishes previous work. Empty history should not be treated as proof that the conversation is false. Sonnet did so here and requested a new message without the required confirmation. Execution workers remained disabled, so no message was actually sent.

## Interpretation and remaining work

The dominant observed failures were skipped discovery, queries requiring too many name terms, and treating missing history as evidence that a new owner was needed. Five standard turns reached the end of the discovery window; no discovery call was rejected and no turn exhausted the overall loop. This run does not show the hard budget forcing incorrect routing.

The deterministic implementation is tested, but the first agent policy is not a successful replacement for the baseline. A subsequent iteration should address how the model searches before creating a new owner and how it interprets empty history, then repeat the same comparison. No automatic prompt tuning, expectation changes, or extra paid reruns were made here.

## Reproduction and artifacts

Commands are documented in `agent_roster_search.md`. Both live suites used Sonnet 4, sequential execution, no DeepEval cache flag, and the existing shared provider pacing.

- Inspection artifacts: `.deepeval/runs/20260919T234441-224af129/`.
- Standard artifacts: `.deepeval/runs/20260919T234725-dc8c30e1/`.
- Each directory retains turn results, full model/tool trajectories, semantic judgments, and per-request judge usage. Standard DeepEval latest-result files were archived before subsequent offline checks.
- The application data files matched their pre-run hashes. Worker dispatches were recorded by the stub; execution agents did not run downstream work.

These artifacts are local and Git-ignored. This report is committed; the historical baseline report and its preserved artifact remain unchanged.
