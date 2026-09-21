# Routing evaluation package

This package contains the routing benchmark fixtures, candidate discovery support,
live harness, deterministic and semantic graders, and difficult-routing campaign
utilities. The standard benchmark tests delegation and instruction fidelity with
stubbed workers; it does not measure downstream task execution.

`cases.py` owns the standard suites, `inspection_cases.py` adds ownership-history
scenarios, and `stress_cases.py` and `challenge_cases.py` define the separate
large-roster collections. `routing_campaign.py` and `campaign_budget.py` keep
capacity checks and paid campaigns isolated, sequential, and budgeted.

Read the [routing guide](../../docs/evals/routing.md) for benchmark meaning and
commands. Read the [difficult-routing guide](../../docs/evals/difficult_routing.md)
for scale and ownership campaigns, and the [evaluation suite README](../README.md)
for the test layout.
