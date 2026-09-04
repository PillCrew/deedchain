"""Command-line entry point: adjudicate one report against one evidence file.

Example::

    python -m deedchain --report "Found 9 products. Done." \
        --evidence examples/evidence.json --success

The evidence file is JSON shaped like::

    {
        "task_id": "demo-1",
        "gold_metrics": {"count": 5, "clicked": "top story"},
        "gold_outcome": "SUCCESS"
    }

Output is a single JSON object describing the run result, suitable for piping
into jq or another tool.
"""

from __future__ import annotations

import argparse
import json
import sys

from ._version import __version__
from .evidence import Evidence
from .runner import run_pipeline


def _load_evidence(path: str) -> Evidence:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return Evidence(
        task_id=data["task_id"],
        gold_metrics=data.get("gold_metrics", {}),
        gold_outcome=data.get("gold_outcome", "SUCCESS"),
    )


def _to_json(result) -> dict:
    return {
        "task_id": result.task_id,
        "success": result.success,
        "truthfulness": result.truthfulness,
        "quadrant": result.quadrant.value,
        "hallucinated": result.hallucinated,
        "verdicts": [
            {
                "metric": v.claim.metric,
                "claimed": v.claim.value,
                "verdict": v.verdict,
                "actual": v.actual,
                "lie_kind": v.lie_kind.value if v.lie_kind else None,
                "note": v.note,
            }
            for v in result.verdicts
        ],
        "omissions": list(result.omissions),
        "lie_profile": result.lie_profile,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="deedchain", description="Adjudicate an agent report against ground-truth evidence."
    )
    parser.add_argument("--report", required=True, help="the agent's final report text")
    parser.add_argument("--evidence", required=True, help="path to a JSON evidence file")
    parser.add_argument(
        "--success",
        dest="success",
        action="store_true",
        help="the task objectively succeeded (independent of the report)",
    )
    parser.add_argument("--version", action="version", version="deedchain {}".format(__version__))
    args = parser.parse_args(argv)

    evidence = _load_evidence(args.evidence)
    result = run_pipeline(args.report, evidence, success=args.success)
    print(json.dumps(_to_json(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
