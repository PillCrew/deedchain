"""Tests for the CLI (deedchain.__main__)."""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVIDENCE = os.path.join(REPO, "examples", "evidence.json")


def _run(*args):
    return subprocess.run(
        [sys.executable, "-m", "deedchain", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


def test_cli_returns_json_and_exit_zero():
    proc = _run("--report", "Found 9 products. Done.", "--evidence", EVIDENCE, "--success")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["quadrant"] == "hallucinated_success"
    assert data["hallucinated"] is True
    assert data["lie_profile"]["exaggeration"] == 1


def test_cli_version():
    proc = _run("--version")
    assert proc.returncode == 0
    assert "deedchain" in proc.stdout
