# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.6.0] - 2026-07-30

### Added

- Anthropic Messages adapter: full `tool_use` / `tool_result` loop against the
  deterministic environment, bounded retries, refusal handling, and token usage
  capture (including cache-read/write token fields).
- `--effort` and `--max-tokens` run flags; `datasets/claude-smoke.jsonl` paid
  smoke suite carrying a negative control and the prompt-injection task.
- Agent-pinned scorer controls are refused for non-reference adapters instead of
  producing a misleading outcome mismatch.

### Changed

- Replaced the OpenAI Responses adapter with the Anthropic Messages adapter;
  `--adapter openai` is now `--adapter anthropic`, default model `claude-opus-5`.
- Dropped `--temperature` / `--top-p` / `--seed`: this model family rejects
  sampling parameters. Reasoning depth is set with `--effort`, and thinking is
  left at the model default so tool calls are never emitted as plain text.
- Optional extra renamed `openai` to `anthropic`.
- Real-model runs are documented against the smoke suite, not the full dataset.

### Removed

- `OpenAIResponsesAdapter` and the `openai` optional dependency.

## [0.6.0] - 2026-07-30

- Prevented reference runs from treating final evidence as a resumable cache; resume is explicit and isolated under `runs/`.
- Delivered injected instructions through tool output and added a naive-agent forbidden-tool negative control.
- Corrected per-key, per-repetition usage and cost aggregation.
- Rejected out-of-order calls to previously completed workflow steps.
- Marked concurrent checkpoints as incomplete artifacts and added a real transient fault to the four-step recovery case.
- Strengthened the paid smoke suite with a negative scorer control and an injected-instruction case.
## [0.5.0] - 2026-07-30

- Made correctness and tool-call budgets hard pass gates; controls use default thresholds.
- Removed correct-argument disclosure from model error responses.
- Added retry/backoff, bounded concurrency, checkpoints, resume, usage capture, and full sampling provenance.
- Added reachable forbidden-tool distractors, prompt-injection faults, and deeper workflows.
- Wired review labels into reports, SQLite ingestion, and regression gates.
- Removed UTF-8 BOMs from all GitHub configuration and documented honest real-model evidence requirements.
## [0.4.0] - 2026-07-30

### Added

- Three expected-failure controls for correctness, efficiency, and safety.
- OpenAI Responses adapter with a complete model/tool/result loop.
- Adapter-specific N-run structural stability scoring and provenance.
- Policy enforcement in the main scoring path.
- JSONL human-review CLI and a versioned five-criterion rubric.
- Ruff, mypy, cross-platform replay CI, package builds, and pinned actions.
- Dependabot, CODEOWNERS, issue forms, and pull-request template.

### Changed

- Evaluation success now means all observed pass/fail outcomes match expectations.
- Reproducibility no longer compares real adapters to the reference agent.
- Previously compressed modules are fully formatted and typed.
- Static success badges were removed in favor of live workflow status.

### Removed

- The optional React dashboard and all generated dashboard assets.

## [0.3.0] - 2026-07-30

### Added

- Regression comparison, trace analytics, fault campaigns, policy helpers, and
  human-review agreement analysis.

## [0.1.0] - 2026-07-30

### Added

- Initial deterministic simulator, 20 positive tasks, trace replay, five scoring
  dimensions, checked-in evidence, and Ubuntu CI.
