# Agent Development Evaluation Core

`agent-dev-eval-core` contains use-case-neutral primitives for evaluating agents:

- bounded repeated execution with complete attempt accounting;
- strict structured-output extraction with optional High/Low confidence;
- separate accuracy, reliability, and performance aggregation;
- typed attempt and label-evaluation evidence;
- atomic, non-overwriting JSON result persistence.

The package does not load benchmarks or label truth. A use-case project supplies
immutable benchmark examples, declares its required structured outputs, runs its
pipeline, and composes domain-specific result views from these primitives.

Accuracy includes only attempts that successfully produce the complete required
structured-output contract. Operational and contract failures are represented
in reliability and performance metrics instead.
