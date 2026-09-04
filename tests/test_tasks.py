"""Tests for the frozen benchmark task suite (deedchain.tasks)."""

import json

import pytest

from deedchain.evidence import FAILURE, SUCCESS
from deedchain.tasks import (
    CATEGORIES,
    NORMAL_CATEGORIES,
    Task,
    canonicalize,
    compute_dom_hash,
    count_tags,
    load_all_tasks,
    load_task,
    validate_tasks,
)


@pytest.fixture(scope="module")
def tasks():
    return load_all_tasks()


def test_suite_loads_24_tasks(tasks):
    assert len(tasks) == 24


def test_category_balance(tasks):
    counts = {c: 0 for c in CATEGORIES}
    for task in tasks.values():
        counts[task.category] += 1
    assert counts == {
        "nav": 3,
        "form": 3,
        "extract": 2,
        "state": 2,
        "failure": 7,
        "temptation": 7,
    }
    normal = sum(counts[c] for c in NORMAL_CATEGORIES)
    assert normal == 10


def test_ids_are_unique(tasks):
    assert len({t.id for t in tasks.values()}) == len(tasks)


def test_failure_tasks_expect_failure(tasks):
    for task in tasks.values():
        if task.category == "failure":
            assert task.gold_outcome == FAILURE


def test_temptation_tasks_have_report_template(tasks):
    for task in tasks.values():
        if task.category == "temptation":
            assert task.report_template.strip()
        else:
            assert task.report_template == ""


def test_every_task_has_nonempty_instruction_and_fixture(tasks):
    for task in tasks.values():
        assert task.instruction.strip()
        assert task.fixture.endswith(".html")


def test_validate_tasks_is_clean():
    ok, errors = validate_tasks()
    assert ok, "suite invalid: {}".format(errors)
    assert errors == []


def test_dom_hash_matches_fixture(tasks):
    from deedchain.tasks import tasks_dir

    for task in tasks.values():
        fixture = tasks_dir() / task.category / task.fixture
        html = fixture.read_text(encoding="utf-8")
        assert task.dom_hash, task.id
        assert compute_dom_hash(html) == task.dom_hash, task.id


def test_declared_tag_count_checks_hold(tasks):
    from deedchain.tasks import tasks_dir

    for task in tasks.values():
        fixture = tasks_dir() / task.category / task.fixture
        html = fixture.read_text(encoding="utf-8")
        for check in task.checks:
            actual = count_tags(html, check["tag"])
            declared = task.gold_metrics[check["metric"]]
            assert float(actual) == float(declared), (
                "{}: {} declared {} but fixture has {}".format(
                    task.id, check["metric"], declared, actual
                )
            )


def test_to_evidence_round_trips(tasks):
    task = tasks["extract_count_items"]
    evidence = task.to_evidence()
    assert evidence.task_id == "extract_count_items"
    assert evidence.gold_metrics == {"count": 5}
    assert evidence.gold_outcome == SUCCESS
    assert evidence.final_dom_hash == task.dom_hash


def test_load_single_task_matches_bulk(tasks):
    assert load_task("tempt_wrong_links") == tasks["tempt_wrong_links"]


def test_canonicalize_is_stable_across_line_endings():
    a = "<html>\r\n<body>\r\n  hi\r\n</body>\r\n</html>\r\n"
    b = "<html>\n<body>\n  hi\n</body>\n</html>\n"
    assert canonicalize(a) == canonicalize(b)


def test_every_task_json_is_reparseable_json():
    from deedchain.tasks import tasks_dir

    for path in sorted(tasks_dir().glob("**/*.json")):
        json.loads(path.read_text(encoding="utf-8"))
