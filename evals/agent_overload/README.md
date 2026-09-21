# Routing evaluation package

This package contains routing benchmark fixtures, candidate discovery support, the
live harness, and deterministic and semantic graders. The standard benchmark tests
delegation and instruction fidelity with stubbed workers; it does not measure
downstream task execution.

`cases.py` owns the standard suites, `inspection_cases.py` adds ownership-history
scenarios, and `stress_cases.py` and `challenge_cases.py` define the large-roster
collections. Capacity checks remain opt-in and local; do not include the
one-million-agent variants in routine verification.

Live inference uses `google/gemini-3.8-flash`. Semantic grading uses
`typesafe/jev-1.13` with Gemini fallback. Run artifacts keep traces, usage, and
costs locally. Read the [routing guide](../../docs/evals/routing.md) for commands
and the [evaluation suite README](../README.md) for the test layout.
