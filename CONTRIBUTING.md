# Contributing

Use Python 3.11 or newer. Install with:

```bash
python -m pip install -e ".[dev]"
```

Before opening a pull request, run the same gates as CI:

```bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m mypy src/openclaw_atlas
python -m pytest --cov --cov-fail-under=85
python -m build
atlas run datasets/milestone-1.jsonl --evidence-dir evidence/candidate
atlas compare evidence/latest/report.json evidence/candidate/report.json
```

Every behavior change needs a deterministic test and a relevant negative case.
Dataset changes must preserve unique IDs and strict schema validation. Regenerate
checked-in evidence when task, trace, scoring, policy, or schema behavior changes.

Never update a baseline merely to make a regression gate green. Explain why the
behavior changed, show the oracle, and demonstrate that the relevant scorer
rejects a bad trace or task.