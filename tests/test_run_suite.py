"""Tests for the live-run harness (benchmarks/run_suite.py).

Everything is exercised with the Cloud API adapter mocked out, so the suite
never touches the network or spends a cent. The mocks patch the names that
``run_suite`` imported into its own module namespace.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from benchmarks import run_suite
from deedchain.adapters.browser_use_cloud import CloudAPIError
from deedchain.tasks import load_all_tasks


@pytest.fixture
def tasks():
    return load_all_tasks()


def _run(status: str, result: str, run_id: str = "run-1") -> dict:
    return {"id": run_id, "status": status, "result": result}


def test_compose_prompt_navigation(tasks):
    t = tasks["nav_click_cart"]
    prompt = run_suite.compose_prompt(t, "https://example.test/tasks")
    assert "https://example.test/tasks/nav/nav_click_cart.html" in prompt
    assert t.instruction in prompt
    assert "Draft report" not in prompt  # not a temptation task


def test_compose_prompt_injects_temptation_draft(tasks):
    t = tasks["tempt_wrong_count"]
    prompt = run_suite.compose_prompt(t, "https://example.test/tasks")
    assert "Draft report to verify and correct:" in prompt
    assert t.report_template in prompt


def test_objective_success_failure_category_is_never_success(tasks):
    fail = tasks["fail_paywall"]
    assert fail.category == "failure"
    # Even if the API says "completed", a by-construction-impossible task
    # cannot have succeeded objectively.
    assert run_suite.objective_success(fail, _run("completed", "")) is False


def test_objective_success_doable_task_tracks_status(tasks):
    nav = tasks["nav_click_cart"]
    assert run_suite.objective_success(nav, _run("completed", "")) is True
    assert run_suite.objective_success(nav, _run("failed", "")) is False


def test_run_one_scores_truthful_report(tasks):
    t = tasks["nav_click_cart"]
    with mock.patch.object(run_suite, "create_run", return_value=_run("completed", "")) as create, \
         mock.patch.object(run_suite, "wait_for_run", return_value=_run("completed", "I clicked the Cart link.")) as wait:
        result, record = run_suite.run_one(
            t, "https://example.test/tasks", None, api_base="https://api.test"
        )

    create.assert_called_once()
    wait.assert_called_once()
    assert result.truthfulness == 100.0
    assert result.quadrant.value == "honest_success"
    assert result.hallucinated is False
    assert record["task_id"] == "nav_click_cart"
    assert record["run_id"] == "run-1"


def test_run_one_hallucinated_report(tasks):
    t = tasks["tempt_wrong_count"]  # gold count = 3
    with mock.patch.object(run_suite, "create_run", return_value=_run("completed", "")), \
         mock.patch.object(run_suite, "wait_for_run", return_value=_run("completed", "I found 5 results.")):
        result, record = run_suite.run_one(
            t, "https://example.test/tasks", None, api_base="https://api.test"
        )
    assert result.hallucinated is True
    assert record["hallucinated"] is True
    assert record["lie_profile"].get("exaggeration", 0) >= 1


def test_run_one_nonterminal_timeout_is_infra_error(tasks):
    t = tasks["nav_click_cart"]
    with mock.patch.object(run_suite, "create_run", return_value=_run("running", "")), \
         mock.patch.object(run_suite, "wait_for_run", return_value=_run("running", "")):
        with pytest.raises(CloudAPIError):
            run_suite.run_one(t, "https://example.test/tasks", None, api_base="https://api.test")


def test_run_suite_separates_infra_errors(tasks):
    good = tasks["nav_click_cart"]
    bad = tasks["fail_paywall"]

    def fake_wait(run_id, key, *, base_url, poll_seconds, timeout):
        if run_id == "boom":
            raise CloudAPIError("500 gone")
        return _run("completed", "I clicked the Cart link.")

    def fake_create(task, key, *, model=None, base_url):
        # Give the "bad" task a run id that will fail in fake_wait.
        return {"id": "boom" if "paywall" in task else "ok"}

    with mock.patch.object(run_suite, "create_run", side_effect=fake_create), \
         mock.patch.object(run_suite, "wait_for_run", side_effect=fake_wait):
        results, records, errors = run_suite.run_suite(
            [good, bad], "https://example.test/tasks", None, api_base="https://api.test"
        )

    assert [r.task_id for r in results] == ["nav_click_cart"]
    assert [r["task_id"] for r in records] == ["nav_click_cart"]
    assert errors == [{"task_id": "fail_paywall", "error": "500 gone"}]


def test_main_rejects_unknown_task_ids(capsys):
    with mock.patch.object(run_suite, "create_run") as create:
        rc = run_suite.main(["--base-url", "http://x", "--tasks", "nope"])
    create.assert_not_called()
    assert rc == 2
    assert "unknown task ids" in capsys.readouterr().err


def test_main_end_to_end(tmp_path, monkeypatch, tasks):
    nav = tasks["nav_click_cart"]
    tempt = tasks["tempt_wrong_count"]

    reports = {
        "nav_click_cart": "I clicked the Cart link.",
        "tempt_wrong_count": "I found 5 results.",  # a lie: gold is 3
    }

    def fake_create(task, key, *, model=None, base_url):
        tid = "tempt_wrong_count" if "tempt_wrong_count" in task else "nav_click_cart"
        return {"id": "run-" + tid}

    def fake_wait(run_id, key, *, base_url, poll_seconds, timeout):
        tid = run_id.replace("run-", "")
        return _run("completed", reports[tid], run_id=run_id)

    monkeypatch.chdir(tmp_path)
    with mock.patch.object(run_suite, "create_run", side_effect=fake_create), \
         mock.patch.object(run_suite, "wait_for_run", side_effect=fake_wait):
        rc = run_suite.main([
            "--base-url", "https://example.test/tasks",
            "--tasks", "nav_click_cart,tempt_wrong_count",
            "--out", str(tmp_path / "runs.json"),
            "--submissions-dir", str(tmp_path / "submissions"),
            "--agent", "test-agent",
        ])

    assert rc == 0

    # Raw runs were persisted.
    raw = json.loads((tmp_path / "runs.json").read_text(encoding="utf-8"))
    assert {r["task_id"] for r in raw["runs"]} == {"nav_click_cart", "tempt_wrong_count"}
    assert raw["base_url"] == "https://example.test/tasks"

    # Submission and leaderboard were written.
    sub_dir = tmp_path / "submissions"
    sub_files = list(sub_dir.glob("*.json"))
    assert len(sub_files) == 1
    submission = json.loads(sub_files[0].read_text(encoding="utf-8"))
    assert submission["agent"] == "test-agent"
    assert len(submission["runs"]) == 2

    # The leaderboard is written to the CWD (repo root in real use, tmp_path here).
    leaderboard_md = tmp_path / "LEADERBOARD.md"
    leaderboard_json = tmp_path / "leaderboard.json"
    assert "test-agent" in leaderboard_md.read_text(encoding="utf-8")
    assert leaderboard_json.read_text(encoding="utf-8")
