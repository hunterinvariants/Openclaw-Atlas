# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.6.0] - 2026-07-31

### Added

- First committed real-model evidence: Claude Opus 5, `tool-agent@3`, effort
  `medium`, 3 repetitions, 4/5 passing with 5/5 declared outcomes matched, in
  `evidence/claude-opus-5` ($0.191). Prompt-injection resistance held across
  all three repetitions, and the reproducibility dimension returned a measured
  value rather than a deterministic 1.0 for the first time.
- Four harness defects surfaced by that run and fixed: dotted tool names
  rejected by the API, arguments unreachable in 12 of 26 tasks, out-of-order
  tool calls misread as undeclared, and an answer oracle that tested output
  formatting rather than grounding.
- `tools/replay_offline.py` re-checks fixes against recorded traces with no API
  calls; `datasets/claude-probe.jsonl` is a one-task probe for cheap
  verification.
- Three multi-step tasks (`five-step-incident-triage`, `five-step-order-recovery`,
  `authorized-refund-chain`) taking the suite to 29 tasks and a five-step
  maximum depth, with chained arguments, a mid-workflow stale read, and a
  permission-gated mutation.
- Forbidden-tool distractors on 19 of 29 tasks, so `policy.forbidden_tools` is
  exercised broadly rather than in two places. The reference agent ignores
  `tool_catalog`, so the baseline is unaffected.

### Changed

- Tests derive task counts from the dataset instead of hard-coding them, so
  adding tasks no longer breaks five unrelated assertions.

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
