# Agent Development Evaluation Core

`agent-dev-eval-core` contains use-case-neutral primitives for evaluating agents:

- bounded repeated execution with complete attempt accounting;
- explicit durable work-item execution with terminal checkpoint callbacks;
- canonical run and logical repetition identities;
- schema-driven JSON scalar extraction with optional configured confidence;
- explicit deterministic graders for exact, normalized-string, and numeric
  evaluation;
- orthogonal execution, output-contract, and scoring states;
- separate accuracy, reliability, scoring-coverage, and performance aggregation;
- typed attempt and field-evaluation evidence;
- JSON round-trip serialization for immutable attempt generations;
- atomic, non-overwriting JSON result persistence.

The package does not load benchmarks or label truth. A use-case project supplies
immutable benchmark examples, resolves a versioned evaluation profile, runs its
pipeline, and composes project-specific result views from these primitives.

Accuracy includes only attempts with a valid configured output contract whose
deterministic graders complete. Operational, contract, and grader failures are
preserved in reliability, scoring coverage, and performance metrics instead.
