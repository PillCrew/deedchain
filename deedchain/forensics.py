"""Per-claim "truth diff" — the forensic report that makes deedchain debuggable.

Given a :class:`RunResult` and its :class:`Evidence`, this module rebuilds, for
every claim the agent made (and every gold metric it silently omitted), a single
line of truth: what was claimed, what the evidence shows, and the verdict. The
renderer marks lines ``[ok]`` (green) or ``[LIE]`` (red) so a developer can paste
it straight into a bug report.

This is rule-based and derives entirely from the adjudicator's output — it never
re-judges anything, it only *displays* what was already decided.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .adjudicate import CONTRADICTED, UNRESOLVED, VERIFIED, Verdict
from .evidence import Evidence
from .runner import RunResult

# A lie can also be an omission of a metric the agent observed but left out.
OMISSION = "OMISSION"


@dataclass(frozen=True)
class Finding:
    subject: str
    claimed: str
    truth: str
    verdict: str
    lie_kind: str = ""
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict in (VERIFIED, UNRESOLVED)


def _truth_text(verdict: Verdict) -> str:
    if verdict.verdict == UNRESOLVED:
        return "(no gold evidence)"
    if verdict.actual is None:
        return "(unknown)"
    if isinstance(verdict.actual, bool):
        return "success" if verdict.actual else "failure"
    return str(verdict.actual)


def build_findings(result: RunResult, evidence: Evidence) -> List[Finding]:
    """Reconstruct one :class:`Finding` per claim plus one per omission."""

    findings: List[Finding] = []

    for verdict in result.verdicts:
        claim = verdict.claim
        claimed = "{} {}".format(claim.metric, claim.value)
        if claim.kind == "outcome":
            claimed = "outcome = {}".format("success" if claim.value else "failure")
        lie = verdict.lie_kind.value if verdict.lie_kind is not None else ""
        findings.append(
            Finding(
                subject=claim.metric,
                claimed=claimed,
                truth=_truth_text(verdict),
                verdict=verdict.verdict,
                lie_kind=lie,
                note=verdict.note,
            )
        )

    # Omissions: gold metrics the report never claimed (and, for failed tasks,
    # the unmentioned outcome). These are scored as lies of omission.
    for metric in result.omissions:
        truth = evidence.gold_metrics.get(metric)
        truth_text = str(truth) if truth is not None else "(declared failure omitted)"
        findings.append(
            Finding(
                subject=metric,
                claimed="(omitted)",
                truth=truth_text,
                verdict=OMISSION,
                lie_kind="omission",
                note="observed but not reported",
            )
        )

    return findings


def render_findings(result: RunResult, evidence: Evidence) -> str:
    """Render the truth diff as human-readable, grep-able lines."""

    lines: List[str] = [
        "task {!r}  quadrant={}  truthfulness={:g}".format(
            result.task_id, result.quadrant.value, result.truthfulness
        )
    ]
    for f in build_findings(result, evidence):
        if f.verdict == VERIFIED:
            marker = "[ok]  "
        elif f.verdict == CONTRADICTED:
            marker = "[LIE] "
        elif f.verdict == OMISSION:
            marker = "[LIE] "
        else:
            marker = "[?]   "
        tail = ""
        if f.lie_kind:
            tail += "  ({})".format(f.lie_kind)
        if f.note:
            tail += "  {}".format(f.note)
        lines.append(
            "{}{:<10} claimed={!r} truth={!r}{}".format(
                marker, f.subject, f.claimed, f.truth, tail
            )
        )
    return "\n".join(lines)
