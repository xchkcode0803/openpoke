# Difficult agent-routing benchmark

This opt-in benchmark tests two different limits: processing larger rosters and selecting owners when names alone are insufficient. It changes no production routing, model, grader, or original benchmark expectation.

## Collections

- `routing_scale`: eight existing stress scenario seeds × 10, 100, 1,000, 10,000, 100,000, and 1,000,000 names (48 variants).
- `routing_challenge`: twelve authored ownership scenarios × 100, 10,000, and 1,000,000 names (36 variants).
- `routing_capacity`: offline process measurements for the 48 scale variants. Challenge preflight uses the same measurements before live execution.

The original full/standard/smoke/stress/inspection collections remain separate. Million-agent fixtures are generated one at a time inside a child process, never during test collection.

## Fixtures and fairness

`routing_population.py` combines clustered personal-assistant task families, varied naming styles, people, locations, dates, and distinct background account/reservation references. Half the population shares scenario attributes. Fixed seeds, an explicit generator version, and a roster SHA-256 identify the exact input. Smaller rosters remain subsets of larger ones, including the same critical owners.

`challenge_cases.py` authors ownership evidence and a feasible discovery sequence independently of the grader. Cases cover crowded references, older context, different wording, vague labels, intermediate assignments, worker responses, older history pages, handoffs, recurring work, multiple owners, query refinement, and new work among similar existing agents. Scripted real-runtime tests validate accessibility within the current discovery budget; live grading does not require that sequence.

Critical agents have coherent histories. Background agents may have no available log. This is synthetic roster scale, not one million simulated complete user histories or proof of production realism. Sampled names and highest-ranked candidates are reviewable in artifacts. Exact duplicate names remain unsupported by the production storage contract.

## Execution and resource limits

`routing_campaign.py` supervises one child per fixture, with a five-minute wall limit and 4 GiB sampled RSS ceiling. It uses the real roster loader, prompt builder, ranker, search, and isolated live harness. Process startup, generation, persistence, loading, ranking, prompt construction, and search have distinct measurements. Sampled peak RSS can miss brief spikes; the watchdog is not an OS allocation limit.

Artifacts go under `.deepeval/campaigns/difficult-routing-v1/{capacity,live}/{variant}/`. A completed outcome is not rerun automatically. A source manifest rejects fixture changes in an existing campaign. Deliberate fixture corrections must preserve the previous artifacts and record the revision while retaining the same spending ledger. Use another explicit `EVAL_CAMPAIGN_DIR` for a separate campaign; do not use it to bypass an approved spending cap. Live execution reuses completed preflight measurements and verifies the reconstructed roster fingerprint before running the real loop. Initial-owner coverage in live results is extracted from the actual model request. Full model/tool traces are retained, while million-name rosters are represented by reconstruction metadata rather than repeated in turn results.

The initial prompt-byte estimate excludes tool schemas and is labeled as a bytes/3 estimate. Live harness estimates include tools; provider token usage is authoritative. Main conversation length remains unbounded by the 20-candidate limit.

## Spending and commands

`campaign_budget.py` snapshots public OpenRouter endpoint pricing, reserves a conservative cost before every attempt, and settles against provider-reported charges. One file-locked ledger spans interaction, Jev, fallback, retries, and separate staged commands. Cross-process request pacing is persisted. Missing usage, interrupted requests, or unknown pricing stop further paid requests. Unresolved charges retain their reservation. No output-limit parameter is changed: the reservation uses the advertised provider maximum, and includes the highest published price tier.

```bash
.venv/bin/python -m pytest evals/agent_overload -m 'not live and not routing_capacity'

RUN_CAPACITY_EVALS=1 .venv/bin/python -m pytest \
  evals/agent_overload/test_routing_scale.py -m routing_capacity

.venv/bin/python -c 'from evals.agent_overload.campaign_budget import initialize_prices; from evals.agent_overload.routing_campaign import campaign_dir; initialize_prices(campaign_dir())'

RUN_LIVE_EVALS=1 EVAL_MAX_SPEND_USD=10 .venv/bin/deepeval test run \
  evals/agent_overload/test_routing_challenges.py -m routing_challenge -k '_100]'

RUN_LIVE_EVALS=1 EVAL_MAX_SPEND_USD=10 .venv/bin/deepeval test run \
  evals/agent_overload/test_routing_scale.py -m routing_scale

RUN_LIVE_EVALS=1 EVAL_MAX_SPEND_USD=10 .venv/bin/deepeval test run \
  evals/agent_overload/test_routing_challenges.py -m routing_challenge -k 'not _100]'
```

Load `OPENROUTER_API_KEY` into the process environment securely before live execution. All paid cases remain sequential. Local capacity measurement needs permission to inspect child-process RSS (`ps` on macOS/Linux). Do not run live tests with pytest parallelization.

## Interpretation

Report initial owner coverage, routing correctness, semantic fidelity, discovery recovery, model/discovery calls, tokens, charges, latency, pacing, and resource failures separately. Owner coverage is not applicable to new-agent tasks. A shortlist miss recovered by correct routing counts as recovery; traces establish whether recovery used discovery or directly reused a known name.

Do not compare totals across different case mixes. Compare the same scenario across sizes. Preserve small-roster failures as distinct from scale-induced failures. Capacity failures and budget/provider/judge failures are unavailable outcomes, not routing errors. No minimum failure rate is required. Measured findings belong in the separate results report.
