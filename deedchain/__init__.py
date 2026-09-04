"""deedchain - measure whether a browser agent's final report tells the truth.

This is a claim-level "report fidelity" checker for web agents. It extracts
every concrete assertion from an agent's final report (actions, page-state
numbers, outcome declaration), compares each against deterministic ground-truth
evidence, and adjudicates it as VERIFIED, CONTRADICTED, or UNRESOLVED - plus a
0-100 truthfulness score, a success x truthfulness quadrant, and a "lie
profile" (omission / fabrication / exaggeration).

Typical use::

    from deedchain import Evidence, run_pipeline

    evidence = Evidence(task_id="t1", gold_metrics={"count": 5}, gold_outcome="SUCCESS")
    result = run_pipeline("Found 9 products. Completed.", evidence, success=True)
    print(result.quadrant)      # hallucinated_success
    print(result.truthfulness)  # 0.0
"""

from __future__ import annotations

from ._version import __version__
from .adjudicate import CONTRADICTED, UNRESOLVED, VERIFIED, LieKind, Verdict, adjudicate
from .evidence import FAILURE, SUCCESS, Evidence
from .forensics import Finding, build_findings, render_findings
from .leaderboard import (
    Entry,
    LIE_KINDS,
    build_entries,
    load_submissions,
    render_leaderboard,
    results_to_submission,
    write_leaderboard,
)
from .report import Claim, extract_claims
from .runner import (
    Quadrant,
    RunResult,
    SuiteSummary,
    render_summary,
    run_pipeline,
    run_task,
    summarize,
)
from .schema import (
    AGENTRUN_VERSION,
    AgentRun,
    AgentRunError,
    load_run,
    parse_line,
    parse_run,
    write_run,
)
from .tasks import (
    CATEGORIES,
    NORMAL_CATEGORIES,
    Task,
    load_all_tasks,
    load_task,
    validate_tasks,
)

__all__ = [
    "VERIFIED",
    "CONTRADICTED",
    "UNRESOLVED",
    "SUCCESS",
    "FAILURE",
    "LieKind",
    "Claim",
    "Evidence",
    "Verdict",
    "Quadrant",
    "RunResult",
    "SuiteSummary",
    "Task",
    "Finding",
    "Entry",
    "LIE_KINDS",
    "AgentRun",
    "AgentRunError",
    "AGENTRUN_VERSION",
    "CATEGORIES",
    "NORMAL_CATEGORIES",
    "extract_claims",
    "adjudicate",
    "run_pipeline",
    "run_task",
    "summarize",
    "render_summary",
    "build_findings",
    "render_findings",
    "build_entries",
    "load_submissions",
    "render_leaderboard",
    "results_to_submission",
    "write_leaderboard",
    "parse_line",
    "parse_run",
    "load_run",
    "write_run",
    "load_task",
    "load_all_tasks",
    "validate_tasks",
    "__version__",
]
