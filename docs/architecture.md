# Architecture and reliability model

ATLAS separates execution from judgment. A task is immutable input, an adapter
produces a canonical event trace, and independent evaluators consume that trace.
The same task can run through the deterministic reference adapter, the Anthropic
Responses adapter, or a user-supplied adapter without changing fault injection,
policy checks, storage, or regression gates.

## Trust boundaries

- Dataset fixtures are untrusted and validated with strict Pydantic schemas.
- Tool calls cross a policy boundary evaluated from the captured trace.
- The Anthropic adapter exposes only tools declared by the task and rejects calls to
  undeclared tools.
- Trace digests exclude wall-clock time and include adapter identity.
- SQLite ingestion is transactional and all query parameters are bound.
- CI fails closed on new failures, score degradation, or mismatched controls.

ATLAS does not isolate external model clients. Production adapters must enforce
network, process, filesystem, and credential boundaries separately.

## Non-tautological validation

Positive fixtures verify the reference path. Negative controls validate the
scorer itself:

1. A deliberately wrong answer oracle must lower correctness below its threshold.
2. An impossible tool-call budget must lower efficiency below its threshold.
3. A mutation without its required permission check must trigger a safety
   violation and fail the hard safety gate.

A run succeeds when actual pass/fail outcomes match declared expected outcomes,
not when every row is green. The checked-in report therefore contains red FAIL
rows whose `Validation` column is `MATCH`.

## Reproducibility semantics

Exact replay is reserved for deterministic executors. Stochastic adapters are
run N times and compared only with themselves. Structural stability v1 weights:

- terminal status: 20%
- ordered tool-call similarity: 50%
- ordered error similarity: 20%
- normalized final-answer exact match: 10%

This avoids comparing a real model with a different reference agent while still
penalizing changes in workflow, errors, termination, and final output.

## Evidence lifecycle

1. Validate the versioned dataset and unique task IDs.
2. Execute every task through the selected adapter for N repetitions.
3. Inject deterministic faults by workflow step and attempt.
4. Persist the first canonical trace and repetition provenance.
5. Apply policy checks and five-dimension scoring.
6. Validate observed results against positive and negative expectations.
7. Ingest evidence into SQLite or query a DuckDB database.
8. Gate the candidate against the accepted baseline.
9. Route ambiguous cases through versioned human-review rubrics.

## Extension contracts

New adapters implement the async `AgentAdapter` protocol and return a `Trace`.
New scorers remain pure functions over task, trace, and measured repetition
stability. Schema changes require a new `schema_version` and migration path;
unknown fields are never silently accepted.
