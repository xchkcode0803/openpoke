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

## Models and artifacts

Live Gmail roles use `google/gemini-3.8-flash`. Flexible checks use
`typesafe/jev-1.13`, with `google/gemini-3.8-flash` as the fallback. The runner
records each model request, tool event, mailbox readback, judge decision, provider
usage, and cost in a fresh local artifact directory under `.deepeval/gmail/` unless
`--output` selects another location. Artifacts are not committed.

Each scenario receives isolated application storage and a disposable mailbox. A
turn has a 180-second deadline and each worker has a 90-second deadline. Provider
requests have a 60-second timeout. Only HTTP 429 responses are retried, with at
most three retries (four attempts total) and only the server's `Retry-After`
delay. There is no fixed pacing delay.

The pinned emulator requires valid raw MIME for structured seeds. Independent
readback verifies seeded content, and adapter normalization supports Gmail's
unpadded base64 and RFC dates without changing production parsing. The launcher
waits for an authenticated local read after Emulate binds its loopback port.

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
RUN_LIVE_EVALS=1 python -m evals.agent_gmail.run --suite development
```

The development suite has 28 scenarios. Each run is isolated and writes its own
trace, usage, and cost records; inspect that directory when comparing runs.
