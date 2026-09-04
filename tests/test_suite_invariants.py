"""End-to-end suite invariants: the engine cannot flag honesty and cannot
miss a planted lie.

These two tests run the real scoring engine over the whole frozen 24-task
suite (no network, no API). They are the "zero-shame" gates: if either fails,
extraction or adjudication is broken against the project's own ground truth.
"""

from __future__ import annotations

import pytest

from deedchain.runner import run_task
from deedchain.tasks import load_all_tasks


@pytest.fixture(scope="module")
def tasks():
    return load_all_tasks()


def honest_report(task) -> str:
    """Render the task's own gold evidence as a plain-English truthful report.

    The point is not that a real agent would phrase it exactly this way; it is
    that this text is *semantically* honest and must therefore never be scored
    as hallucinated.
    """

    parts = []
    for metric, value in task.gold_metrics.items():
        if metric == "clicked":
            parts.append("I clicked {}.".format(value))
        elif metric == "opened":
            parts.append("I opened {}.".format(value))
        elif metric == "typed":
            parts.append("I typed {}.".format(value))
        elif metric == "count":
            parts.append("I found {:g} results.".format(value))
        elif metric == "price":
            parts.append("The price is ${:.2f}.".format(value))
        elif metric == "percent":
            parts.append("The discount is {:g}%.".format(value))
    if task.gold_outcome == "SUCCESS":
        parts.append("Completed successfully.")
    else:
        parts.append("I could not complete the task.")
    return " ".join(parts)


def test_honest_reports_are_never_hallucinated(tasks):
    for task in tasks.values():
        result = run_task(
            honest_report(task), task, success=(task.gold_outcome == "SUCCESS")
        )
        assert result.hallucinated is False, task.id
        assert result.truthfulness == 100.0, task.id
        expected = (
            "honest_success" if task.gold_outcome == "SUCCESS" else "honest_failure"
        )
        assert result.quadrant.value == expected, task.id


def test_temptation_templates_are_always_detected(tasks):
    temptation = [t for t in tasks.values() if t.category == "temptation"]
    assert len(temptation) == 7
    for task in temptation:
        result = run_task(
            task.report_template, task, success=(task.gold_outcome == "SUCCESS")
        )
        assert result.hallucinated is True, task.id
