# Gmail behavior benchmark

This benchmark tests whether the application can use Gmail safely and accurately.
It runs real interaction, execution, and email-search agents through the existing
Gmail tool functions. An eval-only adapter replaces the Composio boundary with a
fresh, fictional Gmail mailbox in Vercel Emulate 0.11.2.

The application path is:

```text
Scripted user turns → interaction agent → delegation → execution and email search
→ existing Gmail tools → Emulate adapter → local mailbox → callbacks and grading
```

Each scenario retains its conversation, roster, worker history, and mailbox across
its turns. The harness waits for scenario-owned work to finish, records mutations,
and independently reads the mailbox before grading. It never supplies hidden draft
IDs, fabricates tool results, repairs model arguments, or blocks an incorrect send.

## Coverage and grading

The suite has eight smoke cases, 28 development cases, and 40 full cases. Full
coverage includes composition and previews, confirmation and revision, search and
read, search followed by action, replies and forwards, failures, and multiple
requests.

Deterministic checks inspect drafts, sent messages, recipients including CC/BCC,
threads, required and prohibited text, preview fidelity, approval order, deletion,
and retrieved evidence. Semantic judges evaluate flexible prose and user-visible
reporting. A scenario must pass every required turn. Unsupported adapter calls and
provider failures are unavailable measurements, not successful actions.

The adapter supports message search and retrieval, drafts, sends, replies,
forwards, MIME, recipients, and thread linkage. Contact lookup and uploaded
attachments are outside coverage and return explicit unsupported errors.

## Calibration qualifications

The pinned emulator requires valid raw MIME for structured seeds; independent
readback verifies seeded content. Adapter normalization handles Gmail's unpadded
base64 and RFC dates without changing production parsing. The launcher waits for an
authenticated local read after Emulate binds its OS-assigned loopback port.

Fixture and grader corrections were made before the authoritative full scores:
quoted exact-text boundaries replaced ambiguous wording; project-status claims now
require supporting evidence; reporting accepts truthful mixed success and failure
claims; and judge input removes duplicate read snapshots while retaining queries,
mutations, errors, source messages, and final state. The original agent traces and
earlier outcomes remain in local artifacts. The current report records audit
qualifications that still apply to frozen scores.

## Running it

Install Python dependencies from `evals/requirements.txt` and Emulate with:

```bash
npm ci --prefix evals/agent_gmail/emulate
```

Run offline Gmail tests with:

```bash
OPENROUTER_API_KEY=offline-placeholder python -m pytest tests/unit/agent_gmail tests/integration/agent_gmail -q
```

The placeholder does not make provider requests. Paid runs require an explicit
opt-in and run sequentially:

```bash
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite smoke
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite development
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite full
```

The standalone Gmail runner keeps Sonnet 4 as its baseline candidate. Use the
[comparison runner](../../evals/model_comparison/README.md) to run a named
candidate with its reproducible pacing profile. See the [current model comparison
report](reports/agent_eval_report.md) for the authoritative measured results.
