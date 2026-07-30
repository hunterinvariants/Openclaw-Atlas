# OPENCLAW-ATLAS

[![CI](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/ci.yml)
[![Quality](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/evaluation.yml/badge.svg?branch=main)](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/evaluation.yml)
[![Coverage gate](https://img.shields.io/badge/coverage_gate-%E2%89%A585%25-brightgreen)](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/evaluation.yml)
[![Evaluation](https://img.shields.io/badge/evaluation-20%2F20_passing-brightgreen)](https://github.com/hunterinvariants/Openclaw-Atlas/blob/main/evidence/latest/report.md)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB)](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/hunterinvariants/Openclaw-Atlas)](https://github.com/hunterinvariants/Openclaw-Atlas/blob/main/LICENSE)

Deterministic evaluation and QA for tool-using AI agents. ATLAS makes agent
behavior inspectable: workflows run against a fake tool environment, every
call is captured in a canonical trace, faults are reproducible, and results are
scored with checked-in evidence.

The first milestone deliberately evaluates a deterministic reference agent.
That stable baseline makes it possible to distinguish harness regressions from
model variance before real model adapters are introduced.

## Milestone 1

- 20 representative JSONL tasks with strict, versioned Pydantic schemas
- deterministic fake tool environment and workflow simulator
- canonical trace capture and digest-based replay
- timeout, malformed-response, stale-data, and permission fault injection
- correctness, safety, efficiency, robustness, and reproducibility scoring
- Markdown/JSON reports plus one JSON trace per task
- pytest regression suite and Ubuntu GitHub Actions workflow

## Quick start

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
pytest
atlas run datasets/milestone-1.jsonl --evidence-dir evidence/latest
```

Replay a checked-in trace:

```bash
atlas replay datasets/milestone-1.jsonl evidence/latest/traces/timeout-recovery.json
```

## Dataset contract

Each JSONL record declares the prompt, deterministic tool workflow, fixture
responses, expected answer evidence, call budget, optional fault, and tags.
Unknown fields are rejected so schema drift fails early. Faults target a
zero-based workflow step and specify how many attempts should fail.

```json
{
  "schema_version": "1.0",
  "id": "timeout-recovery",
  "workflow": [{
    "tool": "health.get",
    "arguments": {"service": "api"},
    "response": {"service": "api", "state": "healthy"}
  }],
  "expected_answer_contains": ["service=api", "state=healthy"],
  "max_tool_calls": 2,
  "retry_limit": 1,
  "fault": {"step": 0, "kind": "timeout", "attempts": 1}
}
```

## Architecture

```text
JSONL task -> deterministic agent -> fake tool environment
                    |                       |
                    +---- canonical trace <-+
                              |
                   five-dimension scorer
                              |
                  JSON + Markdown evidence
```

Trace events contain monotonic sequence numbers but no wall-clock timestamps,
so the same task and harness version produce the same SHA-256 digest on every
platform. The report timestamp is intentionally outside the trace.

## Expert reliability capabilities

Version 0.3 includes production-shaped evaluation infrastructure:

- `openclaw_atlas.regression`: configurable quality gates for overall score, per-dimension degradation, newly failing tasks, and recovered tasks
- `openclaw_atlas.analytics.TraceStore`: transactional SQLite ingestion with normalized runs, tasks, dimension scores, and trace events
- `openclaw_atlas.campaign.run_campaign`: systematic step-by-step timeout, malformed-response, and stale-data campaigns
- `openclaw_atlas.policy.evaluate`: agent-independent checks for forbidden tools, call ceilings, and sensitive argument exposure
- `openclaw_atlas.review`: weighted, versioned human-review rubrics plus reviewer agreement, Cohen's kappa, and task-level disagreement queues
- strict pytest configuration, branch-aware coverage, an 85% coverage floor, and baseline comparison in Ubuntu CI

Run a regression gate directly:

```bash
python -m openclaw_atlas.regression evidence/latest/report.json evidence/candidate/report.json
```

See [the architecture and reliability model](docs/architecture.md) for trust boundaries, evidence lifecycle, extension contracts, and failure semantics.

## Model and prompt adapters

`AgentAdapter` is an async protocol that isolates ATLAS from model vendor SDKs. `ReferenceAdapter` provides the deterministic baseline and `CallableAdapter` wraps any async client. Prompts are independently versioned in `prompts.json`; adapter runs write `provenance.json` with adapter ID, prompt version and digest, and dataset digest.

```bash
atlas run datasets/milestone-1.jsonl --evidence-dir evidence/candidate \
  --prompt-registry prompts.json --prompt tool-agent@2
```

## Trace queries

Evaluation evidence can be ingested into SQLite and queried through a catalog of read-only analysis queries. `QueryEngine` supports SQLite by default and DuckDB through the optional `duckdb` package extra.

```bash
atlas ingest evidence/latest/report.json evidence/latest/traces evidence/atlas.db
atlas query evidence/atlas.db tool_errors --run-id 1
atlas compare evidence/latest/report.json evidence/candidate/report.json
atlas campaign datasets/milestone-1.jsonl
```

## Verifiable evidence

Every green status above resolves to inspectable evidence:

- **CI** runs the complete test suite on Python 3.11, 3.12, and 3.13.
- **Quality** enforces at least 85% branch-aware coverage, runs all 20 deterministic evaluations, verifies canonical trace replay, and compares the candidate report against the checked-in baseline.
- **Evaluation evidence** includes the generated Markdown/JSON report and one canonical trace per task in [`evidence/latest`](evidence/latest).
- GitHub Actions uploads the candidate report and traces from every quality run for independent inspection.
