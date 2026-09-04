"""A stdio MCP server exposing deedchain's two core tools.

Tools:

* ``verify_report`` — score an agent's final report against gold evidence and
  return the quadrant, truthfulness, lie profile and per-claim findings.
* ``submit_run`` — score a report and record it as a leaderboard submission.

The server speaks Model Context Protocol over stdin/stdout (JSON-RPC 2.0,
newline-delimited) with **zero runtime dependencies** — just ``json`` and
``sys``. It is the "agent checks its own report before sending it" everyday
utility that keeps deedchain used outside of benchmark season.

Run it from any MCP host with:

    .venv\\Scripts\\python.exe -m deedchain.mcp_server
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._version import __version__
from .evidence import FAILURE, SUCCESS, Evidence
from .forensics import build_findings
from .leaderboard import build_entries
from .runner import run_pipeline
from .tasks import load_task

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "deedchain"
SERVER_VERSION = __version__

JSONRPC_VERSION = "2.0"

# JSON-RPC error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class MCPError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _evidence_from_args(args: Dict[str, Any]) -> Evidence:
    """Build Evidence from verify/submit arguments (adhoc or suite task)."""

    task_id = args.get("task_id") or "adhoc"
    gold_metrics = args.get("gold_metrics") or {}
    gold_outcome = args.get("gold_outcome") or SUCCESS

    if task_id != "adhoc":
        try:
            task = load_task(task_id)
        except FileNotFoundError:
            # Unknown id -> still honour any explicitly supplied gold evidence.
            return Evidence(
                task_id=task_id,
                gold_metrics=dict(gold_metrics),
                gold_outcome=gold_outcome,
            )
        return task.to_evidence()

    if gold_outcome not in (SUCCESS, FAILURE):
        raise MCPError(INVALID_PARAMS, "gold_outcome must be SUCCESS or FAILURE")
    return Evidence(
        task_id=task_id,
        gold_metrics={str(k): v for k, v in dict(gold_metrics).items()},
        gold_outcome=gold_outcome,
    )


def _score(args: Dict[str, Any]) -> Dict[str, Any]:
    report = args.get("report") or ""
    evidence = _evidence_from_args(args)

    if "success" in args:
        success = bool(args["success"])
    else:
        success = evidence.gold_outcome == SUCCESS

    result = run_pipeline(report, evidence, success=success)
    findings = [
        {
            "subject": f.subject,
            "claimed": f.claimed,
            "truth": f.truth,
            "verdict": f.verdict,
            "lie_kind": f.lie_kind,
            "note": f.note,
        }
        for f in build_findings(result, evidence)
    ]
    return {
        "task_id": result.task_id,
        "success": result.success,
        "truthfulness": result.truthfulness,
        "hallucinated": result.hallucinated,
        "quadrant": result.quadrant.value,
        "lie_profile": result.lie_profile,
        "omissions": list(result.omissions),
        "findings": findings,
    }


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", text.strip().lower()).strip("-")
    return slug or "unknown"


def _submit(args: Dict[str, Any], submissions_dir: Path) -> Dict[str, Any]:
    agent = args.get("agent") or "unknown"
    model = args.get("model") or ""
    report = args.get("report") or ""
    evidence = _evidence_from_args(args)
    success = bool(args["success"]) if "success" in args else evidence.gold_outcome == SUCCESS
    result = run_pipeline(report, evidence, success=success)

    submissions_dir.mkdir(parents=True, exist_ok=True)
    path = submissions_dir / "{}.json".format(_slug("{}-{}".format(agent, model) if model else agent))

    if path.is_file():
        with open(path, "r", encoding="utf-8") as fh:
            submission = json.load(fh)
    else:
        submission = {
            "agent": agent,
            "model": model,
            "submitted_by": args.get("submitted_by", ""),
            "date": time.strftime("%Y-%m-%d"),
            "runs": [],
        }

    submission["runs"].append(
        {
            "task_id": result.task_id,
            "success": result.success,
            "truthfulness": result.truthfulness,
            "hallucinated": result.hallucinated,
            "quadrant": result.quadrant.value,
            "lie_profile": result.lie_profile,
        }
    )
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(submission, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    entries = build_entries([submission])
    entry = entries[0]
    return {
        "written_to": str(path),
        "entry": {
            "agent": entry.agent,
            "model": entry.model,
            "runs": entry.runs,
            "hallucination_rate": entry.hallucination_rate,
            "mean_truthfulness": entry.mean_truthfulness,
        },
    }


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "verify_report",
        "description": (
            "Score a browser agent's final report for truthfulness against "
            "deterministic gold evidence. Returns the success x truthfulness "
            "quadrant, a 0-100 truthfulness score, the lie profile, and a "
            "per-claim truth diff."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "report": {"type": "string", "description": "The agent's final report text."},
                "task_id": {"type": "string", "description": "A deedchain suite task id (uses its frozen gold evidence) or 'adhoc'."},
                "gold_metrics": {"type": "object", "description": "Adhoc ground-truth metrics, e.g. {\"count\": 5, \"price\": 5.0, \"clicked\": \"Cart\"}."},
                "gold_outcome": {"type": "string", "enum": ["SUCCESS", "FAILURE"]},
                "success": {"type": "boolean", "description": "The objective task outcome recorded by the harness."},
            },
            "required": ["report"],
        },
    },
    {
        "name": "submit_run",
        "description": (
            "Score a report and record it as a leaderboard submission (appends "
            "to the agent's submission file). Returns the updated leaderboard "
            "entry for that agent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Agent / framework name."},
                "model": {"type": "string", "description": "Model identifier."},
                "report": {"type": "string"},
                "task_id": {"type": "string"},
                "gold_metrics": {"type": "object"},
                "gold_outcome": {"type": "string", "enum": ["SUCCESS", "FAILURE"]},
                "success": {"type": "boolean"},
                "submitted_by": {"type": "string"},
            },
            "required": ["agent", "report"],
        },
    },
]

_TOOL_BY_NAME = {t["name"]: t for t in TOOLS}


def handle_request(req: Dict[str, Any], submissions_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Handle one JSON-RPC request. Returns a response dict, or None for
    notifications (which get no reply). Raises MCPError on protocol errors."""

    method = req.get("method")
    req_id = req.get("id")

    # Notifications have no id -> no response.
    if req_id is None:
        return None

    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = req.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            tool = _TOOL_BY_NAME.get(name)
            if tool is None:
                raise MCPError(METHOD_NOT_FOUND, "unknown tool {!r}".format(name))
            missing = [k for k in tool["inputSchema"].get("required", []) if k not in arguments]
            if missing:
                raise MCPError(INVALID_PARAMS, "missing required argument(s): {}".format(", ".join(missing)))
            if name == "verify_report":
                text = json.dumps(_score(arguments), ensure_ascii=False, indent=2)
            elif name == "submit_run":
                text = json.dumps(_submit(arguments, submissions_dir or Path("submissions")), ensure_ascii=False, indent=2)
            else:  # pragma: no cover - guarded by _TOOL_BY_NAME
                raise MCPError(METHOD_NOT_FOUND, "unknown tool {!r}".format(name))
            result = {"content": [{"type": "text", "text": text}], "isError": False}
        else:
            raise MCPError(METHOD_NOT_FOUND, "unknown method {!r}".format(method))
    except MCPError as exc:
        return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "error": {"code": exc.code, "message": exc.message}}
    except Exception as exc:  # noqa: BLE001 - report any tool crash as internal error
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "error": {"code": INTERNAL_ERROR, "message": str(exc)},
        }

    return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": result}


def serve(stdin=sys.stdin, stdout=sys.stdout, submissions_dir: Optional[Path] = None) -> int:
    """Run the stdio loop until stdin closes. Returns a process exit code."""

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {
                "jsonrpc": JSONRPC_VERSION,
                "id": None,
                "error": {"code": PARSE_ERROR, "message": "parse error: {}".format(exc)},
            }
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
            continue

        try:
            if not isinstance(req, dict) or req.get("jsonrpc") != JSONRPC_VERSION:
                raise MCPError(INVALID_REQUEST, "invalid request: not a JSON-RPC 2.0 object")
            response = handle_request(req, submissions_dir=submissions_dir)
        except MCPError as exc:
            response = {
                "jsonrpc": JSONRPC_VERSION,
                "id": req.get("id"),
                "error": {"code": exc.code, "message": exc.message},
            }

        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()

    return 0


def main(argv=None) -> int:
    return serve()


if __name__ == "__main__":
    sys.exit(main())
