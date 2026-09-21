# Evaluation documentation

Start with the [model comparison report](evals/reports/agent_eval_report.md): it
records the evidence for changing the application defaults from Sonnet 4 to Gemini
Flash. The report includes the frozen scores, costs, known failures, and limits of
the comparison.

Read the benchmark guides next:

- [Gmail](evals/gmail.md) explains the end-to-end Emulate fixture, grading, and
  safe local commands.
- [Routing](evals/routing.md) explains candidate selection and the 99-case routing
  suite.
- [Difficult routing](evals/difficult_routing.md) covers the separate large-roster
  and ownership collections. Its results were not part of the Gemini comparison.

The [production routing reference](architecture/agent_roster_search.md) describes
the application behavior independently of the benchmarks. The [eval package
README](../evals/README.md) maps the implementation and test layout.
