"""Run the deterministic benchmark and report pass rate + hallucination rate."""

from __future__ import annotations

from typing import Dict, List, Tuple

from deedchain.adjudicate import CONTRADICTED, UNRESOLVED, VERIFIED
from deedchain.runner import run_pipeline

from .cases import CASES


def _verdict_counts(result) -> Dict[str, int]:
    counts = {VERIFIED: 0, CONTRADICTED: 0, UNRESOLVED: 0}
    for v in result.verdicts:
        counts[v.verdict] += 1
    return counts


def evaluate() -> Tuple[int, int, List[dict], float]:
    """Return (passed, total, failures, hallucination_rate).

    ``failures`` is a list of dicts describing every mismatch, keyed by case id.
    ``hallucination_rate`` is the fraction of cases where the report contained
    at least one CONTRADICTED claim (the headline metric of the benchmark).
    """

    passed = 0
    failures: List[dict] = []
    hallucinated = 0
    for case in CASES:
        result = run_pipeline(case.report, case.evidence, case.success)
        counts = _verdict_counts(result)
        problems: List[str] = []

        if result.quadrant != case.expected_quadrant:
            problems.append("quadrant {} != {}".format(result.quadrant.value, case.expected_quadrant.value))
        if result.hallucinated != case.expected_hallucinated:
            problems.append("hallucinated {} != {}".format(result.hallucinated, case.expected_hallucinated))
        if counts != case.expected_counts:
            problems.append("counts {} != {}".format(counts, case.expected_counts))
        if len(result.omissions) != case.expected_omissions:
            problems.append("omissions {} != {}".format(len(result.omissions), case.expected_omissions))
        if result.lie_profile != case.expected_lie_profile:
            problems.append("lie_profile {} != {}".format(result.lie_profile, case.expected_lie_profile))

        if result.hallucinated:
            hallucinated += 1

        if problems:
            failures.append({"id": case.id, "problems": problems})
        else:
            passed += 1

    total = len(CASES)
    rate = hallucinated / total if total else 0.0
    return passed, total, failures, rate
