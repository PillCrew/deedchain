"""Tests for the deterministic benchmark harness."""

from benchmarks.cases import CASES
from benchmarks.runner import evaluate


def test_all_cases_expected():
    assert len(CASES) == 11


def test_benchmark_passes_all_cases():
    passed, total, failures, rate = evaluate()
    assert passed == total, "failures: {}".format(failures)
    assert failures == []


def test_synthetic_hallucination_rate_is_meaningful():
    passed, total, failures, rate = evaluate()
    # 5 of 11 cases are expected to contain at least one contradicted claim.
    assert rate == 5 / 11
