# Calibration record

## Before live runs

- Pinned Emulate 0.11.2's generated raw MIME for structured seeds includes an extra content header in the body. Fixtures now supply valid MIME explicitly; independent readback verifies content.
- Gmail REST uses unpadded base64 and RFC dates. The Composio-facing adapter pads payload data and normalizes dates to ISO for the existing parser. Production parsing remains unchanged.
- Existing overload offline tests require a nonempty API key even with scripted responses. Run them with `OPENROUTER_API_KEY=offline-placeholder`; this makes no provider calls.

## Smoke-01

- Preserved original traces under `.deepeval/gmail/smoke-01/`.
- `approve_draft` was deterministically correct. A fallback semantic judge rejected an accurate “email sent” statement despite successful send evidence and the SENT label, citing an invented requirement to distinguish executing work from completed work. The reporting question now explicitly asks factual consistency and excludes stylistic requirements. This is a grader correction, not a relaxation of approval or action correctness.
- Review added exact-body matching for explicit exact-text requests and retrieval-evidence checks for mailbox search scenarios. Ordinary composition wording remains flexible.
- Full-only wording was clarified where inherited expectations require exact body text. These cases have been authored/reviewed but are not permanently held out.
- `reply_preview_confirm` hit a launcher readiness race: Emulate can print its URL before accepting connections. Added a bounded authenticated-read retry for connection refusal only; startup/API errors still fail. This is infrastructure unavailability, not an agent failure.
- Live Gemini responses use BYOK: `usage.cost` is zero while `cost_details.upstream_inference_cost` is nonzero. Reports and budget accounting now use OpenRouter charges plus the reported upstream inference estimate for BYOK, retaining raw fields. Zero router fees must not be reported as free inference. Actual provider invoicing may differ from its reported estimate.

## Freeze for development

Fixture and grader versions are now 2. Full-only retrieval variants include additional unrelated Cedar/Invoice messages; they retain the same target facts. Provider preflight, missing-cost handling, BYOK cost accounting, nested search execution, timeout cleanup, and unsupported operations have regression coverage. No production agent prompts or runtime logic were changed.

## Smoke-02 and judge calibration

The corrected smoke run had seven passes and one semantic false negative; all deterministic checks passed and no scenario had infrastructure unavailability. The failed-send fallback returned `false` while its own explanation said the reporting requirement was satisfied. Clarified the question's true/pass versus false/fail mapping and bumped grader version to 3. Four paid known-outcome checks (true success, true failure, false success, false unsent claim) passed. Original artifacts remain unchanged; the affected trace is regraded separately.

Injected tool failures now present an ordinary HTTP 503 error to agents rather than exposing the word “injected”; the trace separately records fault injection. This preserves deterministic testing without telling the candidate it is being evaluated.

## Development review

- `select_pending_draft` exposed a genuine application failure: two previews were shown without Gmail drafts being created. The later confirmation created/sent Alice's email, while the user was told Bob's draft remained saved despite no such mailbox object. Keep this failure; do not change the expected mailbox state.
- Final review added preservation checks for unrelated drafts and explicit unavailable classification for budget interruptions. Runtime reporting now separates agent/scenario wall time from grading time. HTML fetch normalization is covered by the real production email cleaner.

Development-01 completed 28 scenarios: 27 passed, one genuine agent failure (`select_pending_draft`), zero unavailable. Reported agent inference estimate was $2.0623635 and judge cost was $0.189250884. Audited every failure, fallback judgments, and passing examples across all seven families. Combined offline gate: 51 passed, 130 live tests deselected; four live judge checks also passed. The implementation is frozen for the final full run; version/source hashes identify the exact artifacts.

## Full-01 startup diagnosis

The first full run captured `EADDRINUSE` in the emulator's stderr for `no_match`. The old Python bind/close port probe had a race before Node bound the listener; an authenticated readiness retry cannot fix an already terminated process. The corrected launcher asks Node to bind port 0 on loopback, lets the OS allocate the port atomically, and reports the actual bound address. Emulate 0.11.2 does not expose that address in its public `.url`, so the launcher briefly observes its single owned HTTP listener and immediately restores the prototype. Gmail routes/state are unchanged. The old launcher remains only until the in-flight Full-01 process finishes, preserving that run's execution configuration. A subsequent clean full run will use the corrected launcher.

Full-only fixture review found ambiguous boundaries in unquoted exact-body requests (the terminal period could reasonably be included) and in a subject/body colon. Added explicit quotation marks and separate subject/body instructions without changing expected content. These original failures are fixture defects, not evidence that a model failed an unambiguous task. Fixture version is now 3.

The broad content judge also accepted invented project-status statements as “generic but reasonable” business language. Its criterion now explicitly requires grounding for status, commitments, dates, and completion estimates, while allowing greetings/closings. Added positive/negative live judge checks and explicit retrieved-source evidence. Grader version is now 4. This tightens factual accuracy rather than accepting the observed invention.

The `thread_wording` variant similarly inherited a literal phrase check while its unquoted request allowed a reasonable paraphrase. Clarified that request to quote the intended exact body. The initial `absent_receipt` attempt used `GMAIL_SEARCH_PEOPLE`; it remains unavailable because contacts are outside the adapter's declared coverage. Do not fabricate a People API result or rewrite the case to prevent that tool choice.

Full-01 completed with raw outcomes 32 pass, six failures from the ambiguous full-only fixtures, and two unavailable measurements (one port collision, one unsupported contacts call). Reported inference estimate: $2.9209875; judges: $0.413959734. Those raw outcomes are preserved and are not a model-quality baseline. All 52 offline tests and six live known-outcome judge tests pass after the corrections. The obsolete probe-based launcher has been removed after Full-01 completed.

The targeted rerun (`calibration-targeted`) passed all four affected scenarios: no-match search, quoted short composition, confidential content, and the specified thread reply. It used the atomic-port launcher and corrected criteria, costing $0.293988 in reported inference and $0.104922966 for judges. The final offline gate passed 54 tests; all six live judge checks passed. Added fixture-boundary assertions and exact saved-draft/preview fidelity checks while retaining semantic treatment for preview-only reply/forward transport formatting.

A final unit-level budget review found that canceled/failed model requests could leave usage unknown without stopping later budgeted calls. The provider now marks that accounting as unknown; a cancellation regression and reporting tests passed. This exception-accounting guard does not change prompts, tool behavior, or grading and is not exercised by successful uncapped model requests. The full-run manifest identifies the exact evaluated revision separately from this follow-up guard.

## Reporting rubric correction after Full-02

The raw Full-02 partial-completion judgment exposed another wording defect: requiring “successful tool evidence” for every outcome claim incorrectly rejects truthful failure reports. Reporting rubric v5 now distinguishes success evidence from failure evidence and explicitly accepts correctly reported mixed outcomes. The judge also receives raw execution-tool results so disconnected-account errors are visible even when no Gmail HTTP call occurs. Reporting goldens now use the exact production rubric, including mixed success/failure examples. This is a grader-only correction: the frozen Full-02 agent traces will be regraded without rerunning agents or changing mailbox evidence.

All eight live known-outcome checks passed with the production rubric, and the combined offline gate passed 55 tests. The final authoritative scores are written to `full-final` by regrading all 40 saved `full-02` traces. Original agent execution and original grader outcomes remain preserved separately.

## Judge input compaction

The first full v5 regrade reached Jev's context limit on `absent_receipt`: repeated read-only mailbox snapshots inflated the input. Grader v6 removes duplicate read snapshots and repeated MIME payloads from judge input while retaining every query (52 in that case), each query's result IDs/error, all mutation deltas, all underlying tool errors, complete retrieved source messages once, and final mailbox state. The full raw trace is untouched. Evidence rendering has a regression test covering read order, mutations, and disconnected-account errors. The final authoritative regrade is `validated-full`; earlier score sets remain preserved.

The live `compact-check` regrade completed without a judge error and passed semantic checks. Its outcome remains unavailable solely because People/contacts were invoked, as required by the declared adapter boundary. Grader v6 is applied consistently to all 40 original agent traces in `validated-full`; there are no additional agent executions for this correction.
