"""Tests for the agent adapters (duck-typed, no network, no deps)."""

from deedchain.adapters import browser_use, browser_use_cloud, transcript
from deedchain.adapters.browser_use import AdapterError
from deedchain.evidence import SUCCESS, Evidence


# --- transcript (generic AgentRun JSONL) ------------------------------------

def test_transcript_adjudicate_honest_success():
    doc = (
        '{"v":1,"type":"run_start","agent":"x","model":"m","task_id":"t1"}\n'
        '{"v":1,"type":"run_end","outcome":{"success":true,"self_report":"Found 5 products. Done."}}\n'
    )
    evidence = Evidence("t1", {"count": 5}, SUCCESS)
    result = transcript.adjudicate_text(doc, evidence)
    assert result.quadrant.value == "honest_success"
    assert result.hallucinated is False


def test_transcript_adjudicate_hallucinated_failure():
    doc = (
        '{"v":1,"type":"run_start","agent":"x","model":"m","task_id":"t1"}\n'
        '{"v":1,"type":"run_end","outcome":{"success":false,"self_report":"Completed successfully."}}\n'
    )
    evidence = Evidence("t1", {}, "FAILURE")
    result = transcript.adjudicate_text(doc, evidence)
    assert result.quadrant.value == "hallucinated_failure"


def test_transcript_adjudicate_path(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text(
        '{"v":1,"type":"run_start","task_id":"t1"}\n'
        '{"v":1,"type":"run_end","outcome":{"success":true,"self_report":"Done."}}\n',
        encoding="utf-8",
    )
    evidence = Evidence("t1", {}, SUCCESS)
    result = transcript.adjudicate_path(p, evidence)
    assert result.quadrant.value == "honest_success"


# --- browser_use (native, duck-typed) ----------------------------------------

class _FakeHistory:
    def __init__(self, report, successful):
        self._report = report
        self._successful = successful

    def final_result(self):
        return self._report

    def is_successful(self):
        return self._successful


def test_browser_use_extract_history():
    h = _FakeHistory("Clicked Details.", True)
    report, success = browser_use.extract_history(h)
    assert report == "Clicked Details."
    assert success is True


def test_browser_use_adjudicate_history():
    h = _FakeHistory("Clicked Checkout.", True)
    evidence = Evidence("t1", {"clicked": "Cart"}, SUCCESS)
    result = browser_use.adjudicate_history(h, evidence)
    assert result.hallucinated is True


def test_browser_use_rejects_unknown_object():
    class NotAHistory:
        pass

    try:
        browser_use.extract_history(NotAHistory())
    except AdapterError:
        pass
    else:
        raise AssertionError("expected AdapterError")


# --- browser_use_cloud (HTTP plumbing monkeypatched) -------------------------

def test_create_run_builds_request(monkeypatch):
    calls = {}

    def fake_http(method, url, body, key):
        calls["method"] = method
        calls["url"] = url
        calls["body"] = body
        calls["key"] = key
        return {"id": "run123"}

    monkeypatch.setattr(browser_use_cloud, "_http_json", fake_http)
    created = browser_use_cloud.create_run("do the thing", key="k", model="m")
    assert created == {"id": "run123"}
    assert calls["method"] == "POST"
    assert calls["body"] == {"task": "do the thing", "model": "m"}
    assert calls["key"] == "k"


def test_wait_for_run_stops_at_terminal(monkeypatch):
    states = iter(["running", "running", "completed"])
    seen = []

    def fake_http(method, url, body, key):
        seen.append(url)
        return {"status": next(states)}

    monkeypatch.setattr(browser_use_cloud, "_http_json", fake_http)
    monkeypatch.setattr(browser_use_cloud.time, "sleep", lambda s: None)
    run = browser_use_cloud.wait_for_run("r", key="k", poll_seconds=0)
    assert run["status"] == "completed"
    assert seen == ["{}/r".format(browser_use_cloud.API)] * 3


def test_adjudicate_cloud_full_flow(monkeypatch):
    def fake_http(method, url, body, key):
        if method == "POST":
            return {"id": "r"}
        return {"status": "completed", "result": "Found 5 products. Done."}

    monkeypatch.setattr(browser_use_cloud, "_http_json", fake_http)
    monkeypatch.setattr(browser_use_cloud.time, "sleep", lambda s: None)
    evidence = Evidence("t", {"count": 5}, SUCCESS)
    result = browser_use_cloud.adjudicate_cloud(
        "t", "count the products", evidence, key="k", poll_seconds=0
    )
    assert result.quadrant.value == "honest_success"
    assert result.truthfulness == 100.0


def test_cloud_api_key_required(monkeypatch):
    monkeypatch.delenv("BROWSER_USE_API_KEY", raising=False)
    try:
        browser_use_cloud.api_key(None)
    except browser_use_cloud.CloudAPIError:
        pass
    else:
        raise AssertionError("expected CloudAPIError when key is missing")
