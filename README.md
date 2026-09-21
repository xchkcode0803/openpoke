# OpenPoke: Agent Routing at Scale

OpenPoke delegates personal-assistant tasks to specialized execution agents. As the roster grows, finding the right agent becomes expensive: the original implementation sent every agent name to the model on every request.

This implementation replaces the full roster with indexed search, a shortlist of likely owners, and additional search when the model needs more information.

## Results

**The latest recorded results pass all 189 routing scenarios, covering rosters up to one million agents.** At 1,000 agents, interaction-model cost fell by **91.7%**. Across the scale tests, model input stayed around **30,000–47,000 tokens per eight tasks**, even as the roster grew from 10 to one million agents.

| Roster size | Original interaction cost | Current interaction cost |
|---:|---:|---:|
| 1,000 agents | $1.557 | $0.129 |
| 10,000 agents | ~$13.22 estimated | $0.126 measured |
| 100,000 agents | ~$129.79 estimated | $0.121 measured |
| 1,000,000 agents | ~$1,295.51 estimated | $0.143 measured |

Costs cover eight routing tasks at each size and exclude grading. Original costs above 1,000 agents extrapolate measured growth; they are hypothetical because sufficiently large full-roster prompts would exceed the model’s context window.

| Coverage | Original benchmark | Latest recorded results |
|---|---:|---:|
| Original routing collection | 93/99 scenarios passed | 99/99 passed |
| Additional history-inspection scenarios | — | 6/6 passed |
| Additional scale scenarios | — | 48/48 passed |
| Additional ownership challenges | — | 36/36 passed |
| Largest tested roster | 1,000 agents | 1,000,000 agents |

The original baseline used Sonnet 4; the current application uses Gemini Flash. Results combine the full sweep with targeted reruns after fixes, rather than a single full run of the final revision. Some ambiguous fixtures and grading rules were corrected during development.

## Evaluation

### Agent routing

The routing benchmark runs the real interaction-agent loop with isolated storage and disabled downstream workers. Code checks whether the correct agent was reused or created; Gemini checks whether the delegated work preserves the user’s intent.

The basic cases establish the expected behavior:

- **Reuse an existing agent:** if an agent already handles the hotel search, send requests for more hotel options to that same agent.
- **Create an agent for new work:** if no existing agent handles the requested task, create one. An empty roster is the simplest example.
- **Handle separate tasks separately:** if the user asks about flights and rent, delegate each request to its relevant agent.
- **Avoid unnecessary delegation:** acknowledge a simple message or work already underway without starting another task.

The harder cases test whether those decisions still hold when ownership is less obvious:

- **Many similar agents:** several agents handle trips to Montreal. The user’s conversation identifies a particular booking, so the assistant must find that booking’s agent rather than choose any Montreal travel agent.
- **Different words for the same task:** the user asks about quitting “the place where I work out,” but the existing agent is named `Westside Contract Termination`. The assistant must connect the request to earlier conversation and search using the relevant clues.
- **Ownership visible only in history:** two agents have vague names and similar recent assignments. An older assignment or response identifies which one handled the booking.
- **A task has changed hands:** an earlier agent handled a flight booking, but a later record transfers responsibility. The assistant should follow up with the new owner.
- **The correct agent is missing from the shortlist:** the first 20 candidates do not include the owner. The assistant must search further instead of choosing an unrelated candidate or creating a replacement.

These scenarios are exercised with rosters ranging from **10 to one million agents**. Additional cases check incomplete worker results, duplicate updates, and preservation of user restrictions.

### Gmail behavior

The Gmail benchmark runs the interaction, execution, and email-search agents against a disposable mailbox provided by Vercel Emulate. It checks actual mailbox changes and tool actions, while Gemini evaluates flexible email content and user-visible reporting. Its 40 scenarios cover:

- Finding the correct email among unrelated messages.
- Reading information and using it in a draft.
- Creating drafts without sending them.
- Sending only after approval.
- Revising, cancelling, and selecting between drafts.
- Replying in the correct thread and forwarding to the correct recipient.
- Preserving recipients, content requirements, and restrictions.
- Handling tool failures and reporting partial completion accurately.

## How routing works

### 1. Retrieve likely owners

SQLite stores agent membership and provides a BM25 text index over agent names, first/latest assignments, and individual historical assignments and responses. Full execution journals remain the authoritative history.

Before Gemini receives a request, the system performs four searches:

- Current message against agent profiles.
- Current message against recorded history.
- Recent conversation against agent profiles.
- Recent conversation against recorded history.

The ranked lists are combined, with more weight given to the current message and priority given to explicit agent-name references. Gemini receives up to **20 candidates**, each with short excerpts showing its previous work.

### 2. Search or inspect when needed

The shortlist is a starting point. Gemini can use conversation clues to formulate a more specific search when an owner is missing.

For example:

- The user asks about quitting “the place where I work out.”
- Earlier conversation identifies the fitness club as Westside.
- Gemini searches for “Westside cancellation.”
- Search returns the existing `Westside Contract Termination` agent.

Gemini can also inspect an agent’s recorded assignments and responses to distinguish plausible owners. Discovery is bounded to six calls within the first four model rounds.

### 3. Delegate with the original context

Gemini explicitly chooses whether to **reuse** an exact existing agent or **create** a new one. An unknown reuse name returns an error instead of silently creating a duplicate.

The execution agent receives:

- **Assigned task:** Gemini’s concise instruction for that worker.
- **Source context:** the exact incoming request or update, attached automatically by the runtime.

The worker performs only its assigned task while using the source context to preserve relevant names, dates, quantities, restrictions, and success criteria. Only the concise assignment is indexed as ownership evidence, keeping unrelated parts of a multi-task request out of future retrieval.

## License

MIT — see [LICENSE](LICENSE).
