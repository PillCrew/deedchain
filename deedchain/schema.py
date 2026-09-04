"""The open ``AgentRun`` interchange format (JSONL) — deedchain's moat.

Any agent framework can emit a transcript in this versioned, self-describing
format, and deedchain can adjudicate it without knowing anything about the
framework. The format is deliberately minimal and line-delimited so a harness
can stream steps as they happen:

.. code-block:: jsonl

    {"v":1,"type":"run_start","agent":"browser-use","model":"bu-2-0-mini-preview","task_id":"hn_top_story","ts":1725000000}
    {"v":1,"type":"step","action":{"kind":"click","selector":"a.storylink"},"result":{"ok":true,"url":".../item?id=42"},"ts":1725000001}
    {"v":1,"type":"run_end","outcome":{"success":true,"self_report":"I clicked the top story.","final_dom_hash":"..."},"ts":1725000003}

Semantics that matter for adjudication:

* ``run_end.outcome.success`` is the **objective** success — recorded by the
  harness from the real DOM state, *not* what the agent claims. The agent's
  claim lives in ``run_end.outcome.self_report``, which is what gets scored for
  truthfulness. Keeping the two in the same object is what makes the honesty
  quadrant computable.
* ``run_end.outcome.final_dom_hash`` (optional) lets the harness pin the final
  page state, cross-checked against ``Evidence.final_dom_hash``.

This module is stdlib-only, like the rest of the package.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

AGENTRUN_VERSION = 1

RUN_START = "run_start"
RUN_STEP = "step"
RUN_END = "run_end"
EVENT_TYPES = (RUN_START, RUN_STEP, RUN_END)


@dataclass(frozen=True)
class Step:
    action: Dict[str, Any]
    result: Dict[str, Any]
    ts: float = 0.0


@dataclass(frozen=True)
class AgentRun:
    """A parsed AgentRun transcript.

    ``success`` is the objective outcome; ``self_report`` is the agent's own
    words; ``final_dom_hash`` (optional) pins the final page state.
    """

    task_id: str
    agent: str = ""
    model: str = ""
    steps: Tuple[Step, ...] = ()
    success: Optional[bool] = None
    self_report: str = ""
    final_dom_hash: str = ""


class AgentRunError(ValueError):
    """Raised when a transcript line does not conform to the AgentRun format."""


def _require_version(obj: Dict[str, Any]) -> None:
    if obj.get("v") != AGENTRUN_VERSION:
        raise AgentRunError(
            "unsupported AgentRun version {!r} (expected {})".format(
                obj.get("v"), AGENTRUN_VERSION
            )
        )


def parse_line(line: str) -> Dict[str, Any]:
    """Parse one AgentRun JSONL line, validating version and type.

    Raises :class:`AgentRunError` on malformed input. Blank lines are skipped
    by returning ``{}`` (callers may filter on ``type``).
    """

    line = line.strip()
    if not line:
        return {}
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as exc:
        raise AgentRunError("invalid JSON in AgentRun line: {}".format(exc)) from exc
    if not isinstance(obj, dict):
        raise AgentRunError("AgentRun line must be a JSON object, got {!r}".format(type(obj).__name__))
    _require_version(obj)
    etype = obj.get("type")
    if etype not in EVENT_TYPES:
        raise AgentRunError("unknown AgentRun event type {!r}".format(etype))
    return obj


def parse_run(text: str) -> AgentRun:
    """Parse a whole AgentRun JSONL document (text, not a file path)."""

    task_id = ""
    agent = ""
    model = ""
    steps: List[Step] = []
    success: Optional[bool] = None
    self_report = ""
    final_dom_hash = ""

    for line in text.splitlines():
        obj = parse_line(line)
        etype = obj.get("type")
        if etype == RUN_START:
            task_id = obj.get("task_id", task_id)
            agent = obj.get("agent", agent)
            model = obj.get("model", model)
        elif etype == RUN_STEP:
            steps.append(
                Step(
                    action=obj.get("action") or {},
                    result=obj.get("result") or {},
                    ts=float(obj.get("ts", 0.0)),
                )
            )
        elif etype == RUN_END:
            outcome = obj.get("outcome") or {}
            if "success" in outcome:
                success = bool(outcome["success"])
            self_report = outcome.get("self_report", self_report)
            final_dom_hash = outcome.get("final_dom_hash", final_dom_hash)

    return AgentRun(
        task_id=task_id,
        agent=agent,
        model=model,
        steps=tuple(steps),
        success=success,
        self_report=self_report,
        final_dom_hash=final_dom_hash,
    )


def load_run(path: Path) -> AgentRun:
    """Parse an AgentRun JSONL file from disk."""

    with open(path, "r", encoding="utf-8") as fh:
        return parse_run(fh.read())


def _line(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"


def write_run(
    path: Path,
    *,
    task_id: str,
    agent: str,
    model: str,
    steps: List[Dict[str, Any]] = (),
    success: Optional[bool] = None,
    self_report: str = "",
    final_dom_hash: str = "",
    ts: float = 0.0,
) -> None:
    """Write an AgentRun JSONL document to ``path``."""

    lines: List[str] = []
    lines.append(
        _line(
            {
                "v": AGENTRUN_VERSION,
                "type": RUN_START,
                "agent": agent,
                "model": model,
                "task_id": task_id,
                "ts": ts,
            }
        )
    )
    for step in steps:
        lines.append(
            _line(
                {
                    "v": AGENTRUN_VERSION,
                    "type": RUN_STEP,
                    "action": step.get("action") or {},
                    "result": step.get("result") or {},
                    "ts": step.get("ts", ts),
                }
            )
        )
    lines.append(
        _line(
            {
                "v": AGENTRUN_VERSION,
                "type": RUN_END,
                "outcome": {
                    "success": success,
                    "self_report": self_report,
                    "final_dom_hash": final_dom_hash,
                },
                "ts": ts,
            }
        )
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
