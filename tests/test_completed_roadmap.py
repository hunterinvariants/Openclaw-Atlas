from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from openclaw_atlas.adapters import (
    CallableAdapter,
    PromptRegistry,
    PromptTemplate,
    ReferenceAdapter,
)
from openclaw_atlas.analytics import TraceStore
from openclaw_atlas.cli import main
from openclaw_atlas.io import load_tasks
from openclaw_atlas.query import QueryEngine
from openclaw_atlas.review import Criterion, Label, Rubric
from openclaw_atlas.runner import EvaluationRunner

DATASET = Path("datasets/milestone-1.jsonl")


def invoke(monkeypatch: pytest.MonkeyPatch, arguments: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["atlas", *arguments])
    return main()


def test_prompt_registry_adapter_and_provenance(tmp_path: Path) -> None:
    registry = PromptRegistry.from_json(Path("prompts.json"))
    prompt = registry.get("tool-agent", "2")
    assert "Plan briefly" in prompt.render(load_tasks(DATASET)[0])
    assert len(prompt.digest) == 64
    with pytest.raises(KeyError):
        registry.get("missing", "1")
    with pytest.raises(ValueError):
        PromptRegistry([prompt, prompt])

    evidence = tmp_path / "adapter"
    report = asyncio.run(
        EvaluationRunner().run_adapter(DATASET, evidence, ReferenceAdapter(), prompt)
    )
    assert report.expected_outcomes_matched == len(load_tasks(DATASET))
    provenance = json.loads((evidence / "provenance.json").read_text())
    assert provenance["adapter"] == "deterministic-reference"
    assert provenance["repetitions"] == 3


def test_callable_adapter_validates_task_identity() -> None:
    task = load_tasks(DATASET)[0]
    prompt = PromptTemplate("x", "1", "{prompt}")

    async def good(task_value, prompt_value):
        return await ReferenceAdapter().run(task_value, prompt)

    trace = asyncio.run(CallableAdapter("custom", good).run(task, prompt))
    assert trace.task_id == task.id
    assert trace.adapter_id == "custom"

    async def bad(task_value, prompt_value):
        result = await ReferenceAdapter().run(task_value, prompt)
        return result.model_copy(update={"task_id": "wrong"})

    with pytest.raises(ValueError):
        asyncio.run(CallableAdapter("bad", bad).run(task, prompt))


def test_weighted_rubric_validation() -> None:
    rubric = Rubric(
        "agent-qa", "1", (Criterion("grounding", 2), Criterion("safety", 1))
    )
    label = Label("t", "alice", "pass", scores={"grounding": 1, "safety": 0.5})
    assert label.weighted_score(rubric) == 0.8333
    with pytest.raises(ValueError):
        Label("t", "a", "fail", scores={}).weighted_score(rubric)
    with pytest.raises(ValueError):
        Label("t", "a", "fail", scores={"grounding": 2, "safety": 1}).weighted_score(
            rubric
        )
    with pytest.raises(ValueError):
        Rubric("bad", "1", ())


def test_query_catalog_and_read_only_guard(tmp_path: Path) -> None:
    evidence = tmp_path / "e"
    report = EvaluationRunner().run(DATASET, evidence)
    database = tmp_path / "atlas.db"
    run_id = TraceStore(database).ingest(report, evidence / "traces")
    engine = QueryEngine(database)
    rows = engine.named("dimension_scores", run_id)
    assert len(rows) == 5
    assert all(0 <= row["average"] <= 1 for row in rows)
    assert engine.named("tool_errors", run_id)
    with pytest.raises(ValueError):
        engine.execute("DELETE FROM runs")
    with pytest.raises(ValueError):
        engine.execute("SELECT 1; DELETE FROM runs")
    with pytest.raises(KeyError):
        engine.named("missing", run_id)
    with pytest.raises(ValueError):
        QueryEngine(database, "other")


def test_all_cli_workflows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    evidence = tmp_path / "e"
    assert (
        invoke(
            monkeypatch,
            ["run", str(DATASET), "--evidence-dir", str(evidence)],
        )
        == 0
    )
    assert (
        invoke(
            monkeypatch,
            [
                "replay",
                str(DATASET),
                str(evidence / "traces" / "timeout-recovery.json"),
            ],
        )
        == 0
    )
    assert (
        invoke(
            monkeypatch,
            ["compare", str(evidence / "report.json"), str(evidence / "report.json")],
        )
        == 0
    )
    database = tmp_path / "cli.db"
    assert (
        invoke(
            monkeypatch,
            [
                "ingest",
                str(evidence / "report.json"),
                str(evidence / "traces"),
                str(database),
            ],
        )
        == 0
    )
    assert invoke(monkeypatch, ["query", str(database), "dimension_scores"]) == 0
    assert invoke(monkeypatch, ["campaign", str(DATASET)]) == 0
    assert "pass_rate" in capsys.readouterr().out
