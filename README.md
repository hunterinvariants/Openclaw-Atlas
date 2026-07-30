# OPENCLAW-ATLAS

[![CI](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/ci.yml)
[![Quality](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/evaluation.yml/badge.svg?branch=main)](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/evaluation.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776AB)](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/hunterinvariants/Openclaw-Atlas)](LICENSE)

Deterministic evaluation and QA for tool-using AI agents. ATLAS captures model
and tool behavior as canonical traces, injects reproducible failures, enforces
policies, measures repeated-run stability, and gates changes against checked-in
evidence.

The baseline intentionally includes failures. Twenty-two positive tasks must pass;
three negative controls must fail for correctness, efficiency, and safety. A run
is valid only when all 25 observed outcomes match their declared expectations.

## What is demonstrated

- Strict, versioned Pydantic and JSONL contracts with unknown-field rejection
- A deterministic reference adapter and a real OpenAI Responses tool-call loop
- Canonical trace capture with adapter identity and cross-platform digest replay
- N-run structural stability for stochastic adapters
- Timeout, malformed-response, stale-data, permission, and injected-instruction fault injection
- Policy enforcement in scoring, including unauthorized mutation detection
- Five scoring dimensions with hard correctness, safety, and call-budget gates
- Regression gates, SQLite/DuckDB trace queries, and systematic fault campaigns
- Versioned human-review rubrics, JSONL labels, Cohen's kappa, and disagreement queues
- Ruff formatting/linting, mypy, coverage, package builds, and pinned GitHub Actions

## Quick start

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m pytest
atlas run datasets/milestone-1.jsonl --evidence-dir evidence/candidate
atlas compare evidence/latest/report.json evidence/candidate/report.json
```

A successful run reports `expected-outcomes=25/25`, not a misleading all-green
score. The generated report contains three visible expected FAIL rows.

## Run a real OpenAI adapter

The optional adapter sends the versioned prompt and tool schemas to the OpenAI
Responses API, executes returned function calls against the deterministic fake
environment, returns tool results to the model, and captures the complete trace.

```bash
python -m pip install -e ".[openai]"
# Set OPENAI_API_KEY in your environment.
atlas run datasets/milestone-1.jsonl \
  --adapter openai \
  --model gpt-5-mini \
  --prompt tool-agent@2 \
  --repetitions 3 \
  --concurrency 4 \
  --evidence-dir evidence/openai
```

Adapter runs write `provenance.json` with the adapter, prompt and dataset
digests, sampling parameters, retry/round limits, token usage, repetition count,
and the exact stability weights. Runs checkpoint per task and resume from per-repetition
traces after interruption. ATLAS does not compare a model
trace with the reference agent; it compares repeated runs from the producing
adapter.

### Real-model evidence policy

`datasets/openai-smoke.jsonl` is a five-task paid smoke suite. Real output belongs
under `evidence/openai-<model>/` and must include its generated report, traces,
and provenance. The repository never labels protocol-fake tests as real-model
evidence. A maintainer must supply `OPENAI_API_KEY`; no credential was available
for the v0.5.0 evidence refresh.

## Dataset and negative controls

Each JSONL record declares the prompt, tool workflow, fixture responses, answer
oracle, call budget, optional fault, policy, pass threshold, expected outcome,
and tags. `expected_pass: false` identifies a scorer control, not a tolerated
regression.

| Control | Deliberate defect | Dimension expected to fail |
|---|---|---|
| `control-wrong-expectation` | Fixture does not satisfy the answer oracle | correctness |
| `control-call-budget` | Workflow exceeds its declared budget | efficiency |
| `control-mutation-without-permission` | Mutation occurs before authorization | safety |

## Evidence and regression gates

- [Latest human-readable report](evidence/latest/report.md)
- [Machine-readable report](evidence/latest/report.json)
- [Canonical task traces](evidence/latest/traces)
- [CI and downloadable run artifacts](https://github.com/hunterinvariants/Openclaw-Atlas/actions/workflows/evaluation.yml)

```bash
atlas replay datasets/milestone-1.jsonl evidence/latest/traces/timeout-recovery.json
atlas campaign datasets/milestone-1.jsonl
atlas ingest evidence/latest/report.json evidence/latest/traces evidence/atlas.db
atlas query evidence/atlas.db tool_errors --run-id 1
```

The CI matrix executes tests, evaluation, and exact replay on Ubuntu, Windows,
and macOS. Quality CI separately enforces Ruff, mypy, at least 85% branch-aware
coverage, package construction, expected-control outcomes, and baseline deltas.

## Human review

```bash
atlas review template datasets/milestone-1.jsonl rubrics/agent-qa-v1.json \
  reviews/alice.jsonl --reviewer alice
atlas review analyze reviews/two-reviewers.jsonl --report evidence/latest/report.json
atlas ingest evidence/latest/report.json evidence/latest/traces evidence/atlas.db \
  --labels reviews/two-reviewers.jsonl
```

Review labels are line-delimited JSON with task ID, reviewer, verdict, rubric
version, criterion scores, and notes. Analysis requires exactly two reviewers
and reports agreement, Cohen's kappa, and the task-level disagreement queue.
With `--report`, human-vs-scorer disagreements become report and regression-gate
inputs; `ingest --labels` stores the underlying labels in SQLite.

## Architecture and scope

See [the architecture and reliability model](docs/architecture.md). ATLAS is an
evaluation harness, not a security sandbox; external adapters still require
independent process, network, filesystem, and credential isolation.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[CHANGELOG.md](CHANGELOG.md). Pull requests must include an oracle or negative
control showing that the relevant scorer can reject bad behavior.
