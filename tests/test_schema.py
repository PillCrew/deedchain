"""Tests for the AgentRun JSONL interchange format (deedchain.schema)."""

import pytest

from deedchain.schema import (
    AGENTRUN_VERSION,
    AgentRunError,
    load_run,
    parse_line,
    parse_run,
    write_run,
)

DOC = """{"v":1,"type":"run_start","agent":"browser-use","model":"m","task_id":"t1","ts":1}
{"v":1,"type":"step","action":{"kind":"click"},"result":{"ok":true},"ts":2}
{"v":1,"type":"run_end","outcome":{"success":true,"self_report":"Done.","final_dom_hash":"abc"},"ts":3}
"""


def test_parse_run_extracts_fields():
    run = parse_run(DOC)
    assert run.task_id == "t1"
    assert run.agent == "browser-use"
    assert run.model == "m"
    assert len(run.steps) == 1
    assert run.steps[0].action == {"kind": "click"}
    assert run.success is True
    assert run.self_report == "Done."
    assert run.final_dom_hash == "abc"


def test_write_then_load_round_trips(tmp_path):
    p = tmp_path / "run.jsonl"
    write_run(
        p,
        task_id="t2",
        agent="a",
        model="m",
        steps=[{"action": {"kind": "click"}, "result": {"ok": True}}],
        success=False,
        self_report="Failed.",
        final_dom_hash="xyz",
    )
    run = load_run(p)
    assert run.task_id == "t2"
    assert run.success is False
    assert run.self_report == "Failed."
    assert run.steps[0].action == {"kind": "click"}


def test_parse_line_rejects_bad_version():
    with pytest.raises(AgentRunError):
        parse_line('{"v":999,"type":"run_start"}')


def test_parse_line_rejects_unknown_type():
    with pytest.raises(AgentRunError):
        parse_line('{"v":1,"type":"bogus"}')


def test_parse_line_rejects_non_object():
    with pytest.raises(AgentRunError):
        parse_line("[1,2,3]")


def test_parse_line_skips_blank():
    assert parse_line("   \n") == {}


def test_parse_run_ignores_blank_lines():
    run = parse_run("\n" + DOC + "\n")
    assert run.task_id == "t1"


def test_version_is_v1():
    assert AGENTRUN_VERSION == 1
