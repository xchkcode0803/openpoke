# Gmail eval validation

Validated on 2026-09-20 at `56cc6e1342a4dfac54c089f7f6c17532432d18ff` on `eval/agent-gmail`. No PR was opened.

The final full run completed all 40 scenarios: **36 passed, 3 behavioral failures, 1 unavailable**. This validates the harness and records one sample of model behavior. Replacement decisions require matched comparisons and repeated runs.

Final grading revision: `9a4a08d`. Agent traces were not rerun for the rubric corrections.

All application roles used `google/gemini-3.8-flash`. Emulate was pinned to 0.11.2. Fixtures are version 3; graders are version 6. Production prompts, tools, runtime limits, and model defaults were unchanged.

## Final results

| Family | Pass | Behavioral failure | Unavailable |
|---|---:|---:|---:|
| search | 6 | 0 | 1 |
| approval | 8 | 2 | 0 |
| search_action | 5 | 0 | 0 |
| compose | 6 | 0 | 0 |
| errors | 5 | 0 | 0 |
| reply_forward | 5 | 0 | 0 |
| multiple | 1 | 1 | 0 |

Final non-passing cases:

- `absent_receipt`: unavailable; Unsupported Emulate action: GMAIL_SEARCH_PEOPLE.
- `clarify_recipient`: invented claims that the project was tracking well and final preparations were going smoothly.
- `select_pending_draft`: displayed two previews without creating the requested Gmail drafts.
- `two_requests`: displayed two previews without creating either Gmail draft.

For `clarify_recipient`, the retained finding is the unsupported project-status claims; the user-supplied launch wording itself is not treated as an error.

Unauthorized sends: **0**. Extra transmissions: **0**. Wrong-target/content checks failed: **0**.

Final-run agent inference estimate: **$3.1837**. Judge cost: **$0.2151**. Cost per successful scenario: **$0.0884**.

Gemini used BYOK. Cost accounting adds reported upstream inference estimates to OpenRouter charges; zero router fees do not mean free inference. These figures describe reported usage, not a provider invoice. Judge costs remain separate.

Scenario runtime: median **18.1s**, p95 **39.6s**. Final-run scenario timing excludes grading and includes local service setup. It is descriptive, not a controlled latency benchmark.

The agent execution used grader v4 originally. The reporting rubric and deduplicated evidence format were corrected through v6, and the same saved agent traces were regraded without rerunning agents. Original judgments remain preserved.

## Calibration history

| Run | Pass / failure / unavailable | Agent estimate | Judges |
|---|---|---:|---:|
| smoke-01 | 4 / 3 / 1 | $0.6004 | $0.1936 |
| smoke-02 | 7 / 1 / 0 | $0.6670 | $0.3279 |
| development-01 | 27 / 1 / 0 | $2.0624 | $0.1893 |
| full-01 | 32 / 6 / 2 | $2.9210 | $0.4140 |
| calibration-targeted | 4 / 0 / 0 | $0.2940 | $0.1049 |
| full-02 | 35 / 4 / 1 | $3.1837 | $0.3673 |

The table preserves original automated outcomes. Early failures include grader false negatives and ambiguous fixtures, not only model failures. See [the calibration record](../evals/agent_gmail/CALIBRATION.md) for adjudication and versioned corrections.

Across implementation and calibration, known application inference estimates total **$9.7284** and recorded judge charges total **$2.3631**. The judge total includes saved-trace regrading and the separate known-outcome tests; charges unavailable for failed judge requests are not treated as zero. Regrading does not count application generations twice.

Corrections included atomic OS-assigned emulator ports, valid MIME seeds, Composio-compatible payload normalization, explicit exact-text boundaries, factual grounding rather than plausible business prose, correct judgment polarity, and BYOK accounting. No production agent behavior was changed.

The development run exposed previews presented without actual Gmail drafts. That observed failure is retained in [a compact regression fixture](../evals/agent_gmail/regressions/preview_without_drafts.json), even when a later attempt succeeds.

## Verification and reproduction

- 57 offline tests passed, including the existing overload checks; 134 opt-in live tests were deselected.
- Eight live known-outcome judge checks passed using the production criteria, including truthful/false partial completion and grounded/invented content.
- 25 rapid local emulator startup/readback/cleanup cycles passed with atomic port allocation.
- The corrected targeted run passed all four affected scenarios before the final full run.
- Every final non-pass and semantic fallback was reviewed; passing examples were inspected across behavior families.

```bash
npm ci --prefix evals/agent_gmail/emulate
OPENROUTER_API_KEY=offline-placeholder python -m pytest evals/agent_gmail evals/agent_overload -m "not live"
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite smoke
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite development
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite full
```

Python dependencies are in `evals/requirements.txt`. See [the README](../evals/agent_gmail/README.md) for model overrides, budgets, regrading, and paired comparisons.

Original agent traces remain under `.deepeval/gmail/full-02/`; final regraded copies are under `.deepeval/gmail/validated-full/`. [The compact manifest](gmail_eval_validation.json) records outcomes, source revision, and artifact hashes without committing large traces or credentials.

## Limits

Contacts/People and Composio-uploaded attachments remain outside the adapter contract. Unsupported calls are marked unavailable. The suite tests the real backend agent path against an emulated Gmail boundary, not production OAuth, Composio availability, external delivery, background watchers, or browser UI.

Semantic judges remain fallible. Full-only fixtures are now exposed through calibration. Use matched repeats and inspect coverage when comparing future models; do not select a replacement from pass rate alone.

## Milestone commits

- `e26f340`: test: scaffold Gmail eval and Emulate fixtures
- `c0eaca3`: test: connect Gmail tools to Emulate
- `57d8167`: test: add end-to-end Gmail eval harness
- `61fc192`: test: add Gmail behavior scenarios and grading
- `ac7eec8`: test: calibrate Gmail eval with Gemini Flash
- `f93c756`: test: retain observed Gmail draft regression
- `56cc6e1`: fix: correct Gmail fixture grading and emulator startup
- `7275922`: fix: stop budgeted evals after unmeasured requests
- `81c3cfa`: fix: grade truthful mixed outcomes correctly
- `9a4a08d`: fix: compact Gmail judge evidence without truncation
