# Architecture and reliability model

ATLAS separates execution from judgment. A task is immutable input, the reference agent produces a canonical event trace, and independent evaluators consume that trace. This allows a real model adapter to replace the reference agent without changing fault injection, policy checks, storage, or regression gates.

## Trust boundaries

- Dataset fixtures are untrusted and validated with strict Pydantic schemas.
- Tool calls cross a policy boundary and are evaluated independently from agent claims.
- Trace digests exclude wall-clock time, making replay comparable across operating systems.
- SQLite ingestion is transactional and uses parameterized statements.
- CI compares candidate evidence against a checked-in baseline and fails closed on new task failures.

## Evidence lifecycle

1. Validate the versioned JSONL dataset.
2. Execute tasks in the isolated fake-tool environment.
3. Inject deterministic faults by workflow step and attempt.
4. Persist canonical traces before scoring.
5. Score correctness, safety, efficiency, robustness, and reproducibility.
6. Ingest results into the normalized trace warehouse for analysis.
7. Gate changes against the accepted baseline.
8. Route disagreements to two-reviewer analysis using Cohen's kappa.

## Extension contracts

New agents need only return the `Trace` model. New tools are fixture-defined workflow steps. New scorers should remain pure functions over task and trace. Schema changes require a new `schema_version` and a migration path; silently accepting unknown fields is prohibited.

## Failure semantics

Timeouts, malformed responses, and stale data are retryable within the declared budget. Permission failures are terminal and must block mutations. Fault campaigns test every workflow step against each retryable fault, preventing happy-path-only confidence.
