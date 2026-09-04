"""Adapter for the native ``browser_use`` Python library (duck-typed).

deedchain has a hard zero-runtime-dependency promise, so this module never
imports ``browser_use`` at module load. It accepts whatever object the library
returns from ``Agent.run()`` and pulls out the two fields adjudication needs:

* the final report  — ``history.final_result()`` (or ``.result()`` fallback)
* objective success — ``history.is_successful()``

Because it is duck-typed, it works with any object exposing those methods and
degrades to a clear error when it cannot find them.
"""

from __future__ import annotations

from typing import Any, Tuple

from ..evidence import Evidence
from ..runner import RunResult, run_pipeline


class AdapterError(TypeError):
    """Raised when the object passed in is not a recognisable browser-use history."""


def extract_history(history: Any) -> Tuple[str, bool]:
    """Return ``(final_report, objective_success)`` from a browser-use history.

    Tries the public API surface first (``final_result`` / ``is_successful``)
    and falls back to common aliases before giving up.
    """

    report = ""
    if hasattr(history, "final_result"):
        report = history.final_result() or ""
    elif hasattr(history, "result"):
        report = history.result() or ""

    success = False
    if hasattr(history, "is_successful"):
        success = bool(history.is_successful())
    elif hasattr(history, "is_done"):
        success = bool(history.is_done())
    else:
        raise AdapterError(
            "history object has neither is_successful() nor is_done(); "
            "expected a browser_use AgentHistoryList"
        )

    return str(report), success


def adjudicate_history(history: Any, evidence: Evidence) -> RunResult:
    """Score a native browser-use run history against ``evidence``."""

    report, success = extract_history(history)
    return run_pipeline(report, evidence, success=success)
