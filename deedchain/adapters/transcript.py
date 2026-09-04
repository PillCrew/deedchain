"""Generic zero-lock-in adapter: adjudicate an ``AgentRun`` JSONL transcript.

This is the adapter every framework can use without touching its code: emit the
open format (see :mod:`deedchain.schema`), run it through here, and get a
deedchain :class:`RunResult`. It is also the adapter the other two adapters are
tested against, because its inputs are plain data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from ..evidence import Evidence
from ..runner import RunResult, run_pipeline
from ..schema import AgentRun, load_run, parse_run


def adjudicate_run(run: AgentRun, evidence: Evidence) -> RunResult:
    """Score an already-parsed :class:`AgentRun` against ``evidence``.

    ``run.success`` is treated as the objective outcome (recorded by the
    harness); ``run.self_report`` is the agent's own claim that gets scored.
    """

    success = bool(run.success) if run.success is not None else False
    return run_pipeline(run.self_report or "", evidence, success=success)


def adjudicate_path(path: Union[str, Path], evidence: Evidence) -> RunResult:
    """Load an AgentRun JSONL file and score it against ``evidence``."""

    return adjudicate_run(load_run(Path(path)), evidence)


def adjudicate_text(text: str, evidence: Evidence) -> RunResult:
    """Score an AgentRun JSONL document held in a string."""

    return adjudicate_run(parse_run(text), evidence)
