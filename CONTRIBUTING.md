# Contributing

Use Python 3.11 or newer. Install with `python -m pip install -e ".[dev]"`, then run `pytest --cov`. Every behavior change needs a deterministic test and regenerated evidence. Dataset changes must preserve unique task IDs and strict schema validation.

Pull requests must pass the 85% branch-aware coverage gate, the 20-task deterministic suite, and baseline regression comparison. Never update baseline evidence merely to make a regression gate green; explain and review the behavioral change first.
