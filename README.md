# OPENCLAW-ATLAS

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

## Roadmap

Next milestones will add model/prompt adapters, rubric-based human review and
disagreement analysis, SQLite/DuckDB trace queries, baseline comparison with
regression thresholds, and an optional React review dashboard.
