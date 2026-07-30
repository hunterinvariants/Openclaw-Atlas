from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from openclaw_atlas.adapters import OpenAIResponsesAdapter, PromptRegistry
from openclaw_atlas.io import load_tasks
from openclaw_atlas.review import analyze, load_labels, load_rubric, write_template
from openclaw_atlas.runner import EvaluationRunner
from openclaw_atlas.stability import stability_score

DATASET = Path("datasets/milestone-1.jsonl")


class FakeResponses:
    def __init__(self, arguments: str = '{"id":"C-100"}') -> None:
        self.calls = 0
        self.arguments = arguments

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            call = SimpleNamespace(
                type="function_call",
                name="crm.get_customer",
                arguments=self.arguments,
                call_id="call-1",
            )
            return SimpleNamespace(output=[call], output_text="")
        return SimpleNamespace(output=[], output_text="customer=C-100, tier=gold")


class FakeClient:
    def __init__(self, arguments: str = '{"id":"C-100"}') -> None:
        self.responses = FakeResponses(arguments)


def test_openai_adapter_executes_model_tool_call_against_fake_environment() -> None:
    task = load_tasks(DATASET)[0]
    prompt = PromptRegistry.from_json(Path("prompts.json")).get("tool-agent", "2")
    adapter = OpenAIResponsesAdapter(client=FakeClient(), model="fake-model")
    trace = asyncio.run(adapter.run(task, prompt))
    assert trace.status == "completed"
    assert trace.adapter_id == "openai-responses:fake-model"
    assert [event.kind for event in trace.events] == [
        "tool_call",
        "tool_result",
        "final",
    ]


def test_negative_controls_produce_expected_red_rows(tmp_path: Path) -> None:
    report = EvaluationRunner().run(DATASET, tmp_path)
    controls = [result for result in report.results if not result.expected_pass]
    assert len(controls) == 3
    assert all(not result.passed and result.outcome_matched for result in controls)
    markdown = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert markdown.count("| FAIL | FAIL | MATCH |") == 3


def test_stochastic_wording_retains_structural_stability(tmp_path: Path) -> None:
    EvaluationRunner().run(DATASET, tmp_path)
    from openclaw_atlas.io import read_trace

    trace = read_trace(tmp_path / "traces" / "lookup-customer-tier.json")
    variant = trace.model_copy(update={"final_answer": "Tier gold for customer C-100."})
    assert stability_score([trace, variant]) == 0.9


def test_review_jsonl_round_trip_and_disagreement(tmp_path: Path) -> None:
    rubric = load_rubric(Path("rubrics/agent-qa-v1.json"))
    tasks = ["a", "b"]
    alice = tmp_path / "alice.jsonl"
    bob = tmp_path / "bob.jsonl"
    write_template(alice, tasks, "alice", rubric)
    write_template(bob, tasks, "bob", rubric)
    bob_text = bob.read_text(encoding="utf-8").replace(
        '"verdict": "pass"', '"verdict": "fail"', 1
    )
    bob.write_text(bob_text, encoding="utf-8")
    result = analyze(load_labels(alice) + load_labels(bob))
    assert result.shared_tasks == 2
    assert result.disagreements == ["a"]


def test_openai_adapter_rejects_wrong_tool_arguments() -> None:
    task = load_tasks(DATASET)[0]
    prompt = PromptRegistry.from_json(Path("prompts.json")).get("tool-agent", "2")
    adapter = OpenAIResponsesAdapter(
        client=FakeClient('{"id":"WRONG"}'), model="fake-model"
    )
    trace = asyncio.run(adapter.run(task, prompt))
    assert any(event.error == "argument_mismatch" for event in trace.events)
    assert not any(
        event.kind == "tool_result" and event.result == task.workflow[0].response
        for event in trace.events
    )


def test_regression_rejects_negative_control_that_unexpectedly_passes(
    tmp_path: Path,
) -> None:
    from openclaw_atlas.regression import compare

    baseline = EvaluationRunner().run(DATASET, tmp_path / "baseline")
    changed = baseline.model_copy(deep=True)
    control = next(result for result in changed.results if not result.expected_pass)
    control.passed = True
    control.outcome_matched = False
    result = compare(baseline, changed)
    assert not result.passed
    assert result.outcome_mismatches == [control.task_id]
    assert "outcome_mismatches:1" in result.violations


def test_review_cli_template_and_analysis(tmp_path: Path, monkeypatch, capsys) -> None:
    import sys

    from openclaw_atlas.cli import main

    output = tmp_path / "labels.jsonl"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "atlas",
            "review",
            "template",
            str(DATASET),
            "rubrics/agent-qa-v1.json",
            str(output),
            "--reviewer",
            "alice",
        ],
    )
    assert main() == 0
    assert len(load_labels(output)) == 23

    monkeypatch.setattr(
        sys,
        "argv",
        ["atlas", "review", "analyze", "reviews/example-two-reviewers.jsonl"],
    )
    assert main() == 0
    assert "control-call-budget" in capsys.readouterr().out
