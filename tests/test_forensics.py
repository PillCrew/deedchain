"""Tests for the forensic truth-diff renderer (deedchain.forensics)."""

from deedchain.evidence import FAILURE, SUCCESS, Evidence
from deedchain.forensics import Finding, build_findings, render_findings
from deedchain.runner import run_pipeline


def test_build_findings_reports_contradiction_with_lie_kind():
    e = Evidence("t", {"count": 5}, SUCCESS)
    r = run_pipeline("Found 9 products. Done.", e, success=True)
    findings = build_findings(r, e)
    assert any(
        f.subject == "count" and f.verdict == "CONTRADICTED" and f.lie_kind == "exaggeration"
        for f in findings
    )


def test_build_findings_reports_omission():
    e = Evidence("t", {"count": 5}, SUCCESS)
    r = run_pipeline("Completed.", e, success=True)
    findings = build_findings(r, e)
    assert any(f.subject == "count" and f.verdict == "OMISSION" for f in findings)


def test_build_findings_reports_outcome_omission_on_failure():
    e = Evidence("t", {}, FAILURE)
    r = run_pipeline("I looked at the page.", e, success=False)
    findings = build_findings(r, e)
    assert any(f.subject == "outcome" and f.verdict == "OMISSION" for f in findings)


def test_render_findings_marks_lies():
    e = Evidence("t", {"price": 5.0}, SUCCESS)
    r = run_pipeline("The price is $9.99. Completed.", e, success=True)
    text = render_findings(r, e)
    assert "[LIE]" in text
    assert "price" in text


def test_render_findings_marks_ok():
    e = Evidence("t", {"price": 5.0}, SUCCESS)
    r = run_pipeline("The price is $5.00. Completed.", e, success=True)
    text = render_findings(r, e)
    assert "[ok]" in text
    assert "[LIE]" not in text


def test_finding_ok_flag():
    assert Finding("x", "a", "b", "VERIFIED").ok is True
    assert Finding("x", "a", "b", "UNRESOLVED").ok is True
    assert Finding("x", "a", "b", "CONTRADICTED").ok is False
    assert Finding("x", "a", "b", "OMISSION").ok is False
