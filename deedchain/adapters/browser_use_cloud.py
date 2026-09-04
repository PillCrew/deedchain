"""Adapter for the browser-use **Cloud API** (``POST /api/v4/runs``).

This is the day-one adapter: it lets deedchain run the full suite against the
browser-use hosted agent with nothing but an API key and stdlib ``urllib``.

Usage::

    $env:BROWSER_USE_API_KEY = "..."
    from deedchain.adapters.browser_use_cloud import create_run, wait_for_run

    created = create_run("Go to example.com and report the title.")
    run = wait_for_run(created["id"])
    print(run["result"])   # the agent's final report

The API key is read from the environment only — it is never hardcoded and never
committed. The HTTP plumbing is isolated in :func:`_http_json` so tests can
monkeypatch it without touching the network.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from ..evidence import Evidence
from ..runner import RunResult, run_pipeline

API = "https://api.browser-use.com/api/v4/runs"
ENV_KEY = "BROWSER_USE_API_KEY"

# Terminal states the Cloud API reports.
TERMINAL = ("completed", "failed")


class CloudAPIError(RuntimeError):
    """Raised when the Cloud API call itself fails (HTTP or missing key)."""


def api_key(key: Optional[str] = None) -> str:
    """Resolve the API key: explicit argument first, then the environment."""

    if key:
        return key
    env = os.environ.get(ENV_KEY, "")
    if not env:
        raise CloudAPIError(
            "{} is not set; pass api_key= or export it".format(ENV_KEY)
        )
    return env


def _http_json(method: str, url: str, body: Optional[Dict[str, Any]], key: str) -> Dict[str, Any]:
    """Perform one JSON request. Split out for testability (monkeypatch me)."""

    req = urllib.request.Request(url, method=method)
    req.add_header("X-Browser-Use-API-Key", key)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def create_run(
    task: str,
    key: Optional[str] = None,
    *,
    model: Optional[str] = None,
    base_url: str = API,
) -> Dict[str, Any]:
    """Create a run. Returns the API's JSON response (contains ``id``)."""

    body: Dict[str, Any] = {"task": task}
    if model:
        body["model"] = model
    return _http_json("POST", base_url, body, api_key(key))


def get_run(run_id: str, key: Optional[str] = None, *, base_url: str = API) -> Dict[str, Any]:
    """Fetch one run by id."""

    return _http_json("GET", "{}/{}".format(base_url, run_id), None, api_key(key))


def wait_for_run(
    run_id: str,
    key: Optional[str] = None,
    *,
    base_url: str = API,
    poll_seconds: float = 5.0,
    timeout: float = 600.0,
) -> Dict[str, Any]:
    """Poll until the run reaches a terminal state (or ``timeout`` elapses)."""

    k = api_key(key)
    deadline = time.time() + timeout
    run: Dict[str, Any] = {}
    while time.time() < deadline:
        run = get_run(run_id, k, base_url=base_url)
        if run.get("status") in TERMINAL:
            return run
        time.sleep(poll_seconds)
    return run


def adjudicate_cloud(
    task_id: str,
    instruction: str,
    evidence: Evidence,
    *,
    key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: str = API,
    poll_seconds: float = 5.0,
    timeout: float = 600.0,
) -> RunResult:
    """Run one task on the Cloud API and score its final report.

    Convenience wrapper around create + wait + pipeline. The objective
    ``success`` is taken from the API's recorded outcome, not from the agent's
    words (exactly what the honesty matrix needs).

    For the frozen 24-task suite this wrapper's ``status == "completed"``
    approximation is *not* correct for the ``failure`` category (tasks that
    cannot succeed by construction). Use :mod:`benchmarks.run_suite`, which
    applies the documented objective-success policy.
    """

    created = create_run(instruction, key, model=model, base_url=base_url)
    run_id = created.get("id")
    if not run_id:
        raise CloudAPIError("create_run response had no id: {!r}".format(created))
    run = wait_for_run(
        run_id,
        key,
        base_url=base_url,
        poll_seconds=poll_seconds,
        timeout=timeout,
    )
    report = run.get("result") or ""
    success = run.get("status") == "completed"
    return run_pipeline(report, evidence, success=success)
