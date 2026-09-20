# Add Gmail action evaluation and switch application models to Gemini Flash

## Motivation

The routing benchmark measures worker selection and delegation. It does not test
whether the application uses Gmail tools correctly, waits for send approval, or
reports actual mailbox outcomes.

This PR adds those end-to-end checks and compares Gemini Flash with Sonnet 4 on
Gmail and routing. Gemini improves the frozen Gmail score and matches the published
routing pass count, with lower nominal inference cost. All five application model
defaults now use `google/gemini-3.8-flash`.

## Evaluation design

The Gmail full suite contains 40 scenarios covering composition, approval and
revisions, search, search followed by action, replies and forwards, failures, and
multiple requests. Each scenario starts with a fresh fictional mailbox in pinned
Vercel Emulate 0.11.2; conversation and worker state persist between its turns.

The comparison also uses the existing 99 routing cases. Sonnet's routing baseline
is the published 95/99 result from the merged roster-search implementation. All 99
first-turn prompt/schema fingerprints match Gemini's run. Cases, expectations,
production prompts, tool schemas, and scoring rules remain fixed.

## How it works

```text
Scripted user turns
        ↓
Real interaction agent and delegation
        ↓
Real execution workers and nested email search
        ↓
Existing Gmail tools → eval-only adapter → Vercel Emulate
        ↓
Actual callbacks, conversation, and mailbox mutations
        ↓
Deterministic checks + fixed semantic judges
```

The harness uses main's candidate roster, ownership history, discovery tools, and
end-turn handling. It drains scenario-owned tasks before grading and independently
reads mailbox state. The adapter does not block incorrect sends; grading detects
them through mutation history. Routing retains its existing worker stubs.

Gemini has no fixed request delay. Reactive rate-limit retries and spending controls
remain. Sonnet's reproducible profile retains 4.1-second spacing. Jev 1.13 and the
Sonnet fallback judge stay fixed for both candidates.

## Results

| Benchmark | Sonnet 4 | Gemini Flash | Nominal agent inference cost |
|---|---:|---:|---:|
| Gmail | 18/40 passed | 37/40 passed; 1 unavailable | $4.35 → $2.80 |
| Routing | 95/99 passed | 95/99 passed | $1.70 → $1.51 |

Nominal inference cost decreased **35.6% for Gmail** and **11.1% for routing**.
Gemini's configured BYOK credits produce **$0 OpenRouter agent charges**; the table
uses provider-reported upstream estimates for a meaningful model-cost comparison.
Judge charges are separate: $0.192538 for Gemini Gmail and $0.021995 for Gemini routing.

### Behavior and remaining failures

- Gmail mutation history confirms **zero unauthorized sends for Gemini versus six
  for Sonnet**. No measured Gmail case regressed against the Sonnet result.
- Gemini still invented an unsupported “on track” project-status claim in one draft.
- The second Gmail failure is exact subject casing: `Birch Update` rather than
  `Birch update`. Both drafts existed with the correct recipients and timing.
- The unavailable Gmail case attempted contact lookup, which the adapter does not
  support. Its mailbox and semantic checks otherwise passed.
- Routing has one scored improvement and one regression. Gemini preserved the rent
  date lookup that Sonnet missed, but waited on already-delegated restaurant research
  instead of making the follow-up delegation required by the fixture.

Frozen scores include documented audit qualifications. One Sonnet judgment rejected
a valid send-or-revise question, and some reporting flags are questionable. Draft
persistence and exact subject matching are benchmark requirements; not every failed
score establishes a production defect. Confirmed unauthorized sends have separate
mailbox evidence.

Observed median latency fell from 31.50 to 16.21 seconds per Gmail scenario and from
6.25 to 3.04 seconds per routing turn. This includes removing deliberate pacing.
Gemini's cumulative routing HTTP time increased, so these results do not establish
that its underlying inference is faster.

## Model change

The only production-code changes are the defaults for interaction, execution,
email search, summarization, and email classification in `server/config.py`.
Production prompts, tools, routing logic, concurrency, timeouts, and iteration
limits are unchanged. Eval-only candidate selection preserves the Sonnet baseline.

## Validation and limitations

- **198 offline tests passed**, covering Emulate contracts, real orchestration,
  isolation, grading, candidate selection, accounting, retries, and default models.
- Three focused live checks passed: memory retains required facts and pending
  approval, OTP email is surfaced, and routine marketing is ignored. These do not
  provide broad summarization/classification coverage.
- Returned candidate model IDs were verified. The routing ledger has no unresolved
  reservations. Raw traces and full results remain local.
- Gmail tests local API behavior, not OAuth, delivery, or Composio reliability.
  Contacts and uploaded attachments remain outside coverage.
- Both Gmail candidates use equal extended eval transport deadlines. This does not
  establish compliance with the shorter production worker timeout.
- These are single completed results per case, not statistical reliability estimates.

See the [full report](agent_eval_report.md), [compact measurements](agent_eval_report.json),
and [setup/run commands](../evals/model_comparison/README.md). This is a local PR
text draft; nothing has been pushed or submitted.
