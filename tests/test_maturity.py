from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from openclaw_atlas.adapters import AnthropicMessagesAdapter, PromptRegistry
from openclaw_atlas.io import load_tasks
from openclaw_atlas.review import analyze, load_labels, load_rubric, write_template
from openclaw_atlas.runner import EvaluationRunner
from openclaw_atlas.stability import stability_score

DATASET = Path("datasets/milestone-1.jsonl")


class FakeMessages:
    """Protocol-compatible stand-in — never labelled as real-model evidence."""

    def __init__(
        self, arguments: dict | None = None, stop_reason: str = "tool_use"
    ) -> None:
        self.calls = 0
        self.arguments = {"id": "C-100"} if arguments is None else arguments
        self.stop_reason = stop_reason
        self.requests: list[dict] = []

    async def create(self, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        usage = SimpleNamespace(input_tokens=120, output_tokens=30)
        if self.stop_reason in {"refusal", "max_tokens"}:
            return SimpleNamespace(
                content=[], stop_reason=self.stop_reason, usage=usage
            )
        if self.calls == 1:
            block = SimpleNamespace(
                type="tool_use",
                id="toolu_1",
                name="crm.get_customer",
                input=self.arguments,
            )
            return SimpleNamespace(content=[block], stop_reason="tool_use", usage=usage)
        text = SimpleNamespace(type="text", text="customer=C-100, tier=gold")
        return SimpleNamespace(content=[text], stop_reason="end_turn", usage=usage)


class FakeClient:
    def __init__(self, arguments: dict | None = None, stop_reason: str = "tool_use"):
        self.messages = FakeMessages(arguments, stop_reason)


def _adapter(**kwargs) -> AnthropicMessagesAdapter:
    return AnthropicMessagesAdapter(model="fake-model", **kwargs)


def test_anthropic_adapter_executes_model_tool_call_against_fake_environment() -> None:
    task = load_tasks(DATASET)[0]
    prompt = PromptRegistry.from_json(Path("prompts.json")).get("tool-agent", "2")
    client = FakeClient()
    trace = asyncio.run(_adapter(client=client).run(task, prompt))
    assert trace.status == "completed"
    assert trace.adapter_id == "anthropic-messages:fake-model"
    assert [event.kind for event in trace.events] == [
        "tool_call",
        "tool_result",
        "final",
    ]
    assert trace.usage == {"input_tokens": 240, "output_tokens": 60}
    request = client.messages.requests[0]
    assert request["tools"][0]["input_schema"]["additionalProperties"] is False
    assert request["output_config"] == {"effort": "medium"}
    assert not {"temperature", "top_p", "top_k"} & request.keys()


def test_anthropic_adapter_records_refusal_as_a_failed_trace() -> None:
    task = load_tasks(DATASET)[0]
    prompt = PromptRegistry.from_json(Path("prompts.json")).get("tool-agent", "2")
    trace = asyncio.run(
        _adapter(client=FakeClient(stop_reason="refusal")).run(task, prompt)
    )
    assert trace.status == "failed"
    assert "refused" in trace.final_answer.lower()


def test_anthropic_adapter_names_token_truncation_instead_of_blaming_the_model() -> (
    None
):
    task = load_tasks(DATASET)[0]
    prompt = PromptRegistry.from_json(Path("prompts.json")).get("tool-agent", "2")
    trace = asyncio.run(
        _adapter(client=FakeClient(stop_reason="max_tokens"), max_tokens=64).run(
            task, prompt
        )
    )
    assert trace.status == "failed"
    assert "max_tokens=64" in trace.final_answer


def test_anthropic_adapter_rejects_invalid_effort() -> None:
    with pytest.raises(ValueError, match="effort"):
        _adapter(client=FakeClient(), effort="turbo")


def test_agent_pinned_controls_are_refused_for_non_reference_adapters() -> None:
    prompt = PromptRegistry.from_json(Path("prompts.json")).get("tool-agent", "2")
    with pytest.raises(ValueError, match="control-injection-following"):
        asyncio.run(
            EvaluationRunner().run_adapter(
                DATASET, Path("unused"), _adapter(client=FakeClient()), prompt
            )
        )


def test_negative_controls_produce_expected_red_rows(tmp_path: Path) -> None:
    report = EvaluationRunner().run(DATASET, tmp_path)
    controls = [result for result in report.results if not result.expected_pass]
    assert len(controls) == 4
    assert all(not result.passed and result.outcome_matched for result in controls)
    markdown = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert markdown.count("| FAIL | FAIL | MATCH |") == 4


def test_stochastic_wording_retains_structural_stability(tmp_path: Path) -> None:
    EvaluationRunner().run(DATASET, tmp_path)
    from openclaw_atlas.io import read_trace

    trace = read_trace(tmp_path / "traces" / "lookup-customer-tier.json")
    variant = trace.model_copy(update={"final_answer": "Tier gold for customer C-100."})
    assert stability_score([trace, variant]) == 0.8


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


def test_anthropic_adapter_rejects_wrong_tool_arguments() -> None:
    task = load_tasks(DATASET)[0]
    prompt = PromptRegistry.from_json(Path("prompts.json")).get("tool-agent", "2")
    client = FakeClient({"id": "WRONG"})
    trace = asyncio.run(_adapter(client=client).run(task, prompt))
    assert any(event.error == "argument_mismatch" for event in trace.events)
    assert not any(
        event.kind == "tool_result" and event.result == task.workflow[0].response
        for event in trace.events
    )
    # The mismatch must not hand the correct arguments back to the model.
    results = [
        block
        for message in client.messages.requests[-1]["messages"]
        if isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert results and all(block["is_error"] for block in results)
    returned = json.dumps(results)
    assert "argument_mismatch" in returned and "C-100" not in returned


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
    assert len(load_labels(output)) == 26

    monkeypatch.setattr(
        sys,
        "argv",
        ["atlas", "review", "analyze", "reviews/example-two-reviewers.jsonl"],
    )
    assert main() == 0
    assert "control-call-budget" in capsys.readouterr().out


def test_human_disagreement_is_load_bearing(tmp_path: Path) -> None:
    import sqlite3

    from openclaw_atlas.analytics import TraceStore
    from openclaw_atlas.regression import compare

    evidence = tmp_path / "evidence"
    baseline = EvaluationRunner().run(DATASET, evidence)
    candidate = baseline.model_copy(deep=True)
    candidate.human_review = {"scorer_disagreements": ["lookup-customer-tier"]}
    assert "human_disagreements:1" in compare(baseline, candidate).violations

    labels = load_labels(Path("reviews/example-two-reviewers.jsonl"))
    database = tmp_path / "atlas.db"
    TraceStore(database).ingest(baseline, evidence / "traces", labels)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM reviews").fetchone()[0] == 4


def test_reference_run_never_scores_final_trace_output_as_cache(tmp_path: Path) -> None:
    from openclaw_atlas.io import read_trace, write_trace

    runner = EvaluationRunner()
    runner.run(DATASET, tmp_path)
    path = tmp_path / "traces" / "lookup-customer-tier.json"
    original = read_trace(path)
    forged = original.model_copy(
        update={"events": original.events[:1], "final_answer": "forged"}
    )
    write_trace(path, forged)
    write_trace(tmp_path / "runs" / "lookup-customer-tier" / "1.json", forged)
    runner.run(DATASET, tmp_path)
    regenerated = read_trace(path)
    assert regenerated.final_answer != "forged"
    assert len(regenerated.events) == 3


def test_injection_is_delivered_and_naive_control_is_rejected(tmp_path: Path) -> None:
    from openclaw_atlas.io import read_trace

    report = EvaluationRunner().run(DATASET, tmp_path)
    safe = read_trace(tmp_path / "traces" / "injected-instruction-resistance.json")
    assert any(
        isinstance(event.result, dict) and "untrusted_instruction" in event.result
        for event in safe.events
    )
    control = next(
        item for item in report.results if item.task_id == "control-injection-following"
    )
    assert not control.passed and control.outcome_matched
    assert "forbidden_tool_called" in control.policy_violations


def test_usage_aggregation_preserves_token_dimensions(tmp_path: Path) -> None:
    import json

    from openclaw_atlas.io import write_trace
    from openclaw_atlas.models import Trace

    traces = tmp_path / "traces"
    for task_id, usage in (
        ("a", {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110}),
        ("b", {"input_tokens": 200, "output_tokens": 20, "total_tokens": 220}),
    ):
        write_trace(
            traces / f"{task_id}.json",
            Trace(
                task_id=task_id,
                events=[],
                final_answer="ok",
                status="completed",
                usage=usage,
            ),
        )
    EvaluationRunner._write_provenance(
        tmp_path,
        DATASET,
        {"pricing_usd_per_million_tokens": {"input": 1.0, "output": 2.0}},
        None,
        1,
        SimpleNamespace(
            results=[SimpleNamespace(task_id="a"), SimpleNamespace(task_id="b")],
            task_count=2,
        ),
    )
    provenance = json.loads((tmp_path / "provenance.json").read_text())
    assert provenance["usage"] == {
        "input_tokens": 300.0,
        "output_tokens": 30.0,
        "total_tokens": 330.0,
    }
    assert provenance["estimated_cost_usd"] == 0.00036


def test_checkpoint_is_marked_incomplete(tmp_path: Path) -> None:
    import json

    EvaluationRunner()._checkpoint(tmp_path, DATASET, [])
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert checkpoint["artifact_kind"] == "incomplete_checkpoint"
    assert checkpoint["completed_tasks"] == 0


def test_model_cannot_resatisfy_an_earlier_step_out_of_order() -> None:
    import pytest

    from openclaw_atlas.adapters import _find_step

    task = next(task for task in load_tasks(DATASET) if task.id == "two-source-summary")
    with pytest.raises(ValueError, match="undeclared tool"):
        _find_step(task, task.workflow[0].tool, 1)
