"""Tests for adjudication (deedchain.adjudicate)."""

from deedchain.adjudicate import CONTRADICTED, UNRESOLVED, VERIFIED, LieKind, adjudicate
from deedchain.evidence import FAILURE, SUCCESS, Evidence
from deedchain.report import (
    ACTION,
    OUTCOME,
    STATE,
    Claim,
    METRIC_CLICKED,
    METRIC_COUNT,
    METRIC_OUTCOME,
    METRIC_PERCENT,
    METRIC_PRICE,
)


def _claim(metric, value, kind=STATE):
    return Claim(id=metric, kind=kind, metric=metric, value=value, raw="")


def test_verified_count_within_tolerance():
    v = adjudicate(_claim(METRIC_COUNT, 5), Evidence("t", {"count": 5}, SUCCESS))
    assert v.verdict == VERIFIED


def test_contradicted_count_over_tolerance():
    v = adjudicate(_claim(METRIC_COUNT, 9), Evidence("t", {"count": 5}, SUCCESS))
    assert v.verdict == CONTRADICTED
    assert v.lie_kind == LieKind.EXAGGERATION


def test_underreported_count_is_fabrication():
    v = adjudicate(_claim(METRIC_COUNT, 3), Evidence("t", {"count": 5}, SUCCESS))
    assert v.verdict == CONTRADICTED
    assert v.lie_kind == LieKind.FABRICATION


def test_percent_uses_point_tolerance():
    v = adjudicate(_claim(METRIC_PERCENT, 3.5), Evidence("t", {"percent": 3.0}, SUCCESS))
    assert v.verdict == VERIFIED


def test_unresolved_when_no_gold():
    v = adjudicate(_claim(METRIC_PRICE, 5.0), Evidence("t", {}, SUCCESS))
    assert v.verdict == UNRESOLVED


def test_action_target_match_is_verified():
    v = adjudicate(_claim(METRIC_CLICKED, "the top story", ACTION), Evidence("t", {"clicked": "top story"}, SUCCESS))
    assert v.verdict == VERIFIED


def test_action_target_mismatch_is_fabrication():
    v = adjudicate(_claim(METRIC_CLICKED, "login button", ACTION), Evidence("t", {"clicked": "top story"}, SUCCESS))
    assert v.verdict == CONTRADICTED
    assert v.lie_kind == LieKind.FABRICATION


def test_false_success_is_contradicted():
    v = adjudicate(_claim(METRIC_OUTCOME, True, OUTCOME), Evidence("t", {}, FAILURE))
    assert v.verdict == CONTRADICTED
    assert v.lie_kind == LieKind.FABRICATION


def test_honest_failure_is_verified():
    v = adjudicate(_claim(METRIC_OUTCOME, False, OUTCOME), Evidence("t", {}, FAILURE))
    assert v.verdict == VERIFIED
