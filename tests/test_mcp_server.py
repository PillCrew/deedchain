import json

import pytest

from deedchain import mcp_server
from deedchain.mcp_server import handle_request


def call(method, params=None, _id=1):
    req = {"jsonrpc": "2.0", "id": _id, "method": method}
    if params is not None:
        req["params"] = params
    return handle_request(req)


def test_initialize_handshake():
    resp = call("initialize")
    assert resp["result"]["protocolVersion"] == mcp_server.PROTOCOL_VERSION
    assert resp["result"]["capabilities"] == {"tools": {}}
    assert resp["result"]["serverInfo"]["name"] == "deedchain"
    assert resp["result"]["serverInfo"]["version"]


def test_ping():
    assert call("ping")["result"] == {}


def test_tools_list():
    names = {t["name"] for t in call("tools/list")["result"]["tools"]}
    assert names == {"verify_report", "submit_run"}


def test_notification_gets_no_response():
    req = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert handle_request(req) is None


def test_unknown_method_returns_error():
    resp = call("nope")
    assert resp["error"]["code"] == mcp_server.METHOD_NOT_FOUND


def test_verify_report_adhoc_honest():
    report = "I clicked Cart. The cart shows 3 items. Total was $45.00."
    params = {
        "name": "verify_report",
        "arguments": {
            "report": report,
            "gold_metrics": {"count": 3, "price": 45.0, "clicked": "Cart"},
            "gold_outcome": "SUCCESS",
        },
    }
    resp = call("tools/call", params)
    text = resp["result"]["content"][0]["text"]
    data = json.loads(text)
    assert data["truthfulness"] == 100.0
    assert data["quadrant"] == "honest_success"
    assert data["hallucinated"] is False


def test_verify_report_adhoc_hallucinated():
    report = "I clicked Cart. The cart shows 99 items. Total was $9.00."
    params = {
        "name": "verify_report",
        "arguments": {
            "report": report,
            "gold_metrics": {"count": 3, "price": 45.0, "clicked": "Cart"},
            "gold_outcome": "SUCCESS",
        },
    }
    data = json.loads(call("tools/call", params)["result"]["content"][0]["text"])
    assert data["truthfulness"] < 100.0
    assert data["hallucinated"] is True
    assert data["quadrant"] == "hallucinated_success"


def test_verify_report_suite_task(tmp_path):
    # A suite task with a known gold count of 5.
    params = {
        "name": "verify_report",
        "arguments": {"report": "The list has 5 rows.", "task_id": "extract_count_items"},
    }
    data = json.loads(call("tools/call", params)["result"]["content"][0]["text"])
    assert data["task_id"] == "extract_count_items"
    assert data["truthfulness"] == 100.0


def test_verify_report_bad_outcome_enum():
    params = {
        "name": "verify_report",
        "arguments": {
            "report": "x",
            "gold_metrics": {},
            "gold_outcome": "NOPE",
        },
    }
    resp = call("tools/call", params)
    assert resp["error"]["code"] == mcp_server.INVALID_PARAMS


def test_submit_run_writes_file(tmp_path):
    params = {
        "name": "submit_run",
        "arguments": {
            "agent": "test-agent",
            "model": "m",
            "report": "The list has 5 rows.",
            "task_id": "extract_count_items",
        },
    }
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": params}
    resp = handle_request(req, submissions_dir=tmp_path)
    assert "error" not in resp
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["entry"]["runs"] == 1
    assert data["entry"]["mean_truthfulness"] == 100.0
    assert (tmp_path / "test-agent-m.json").is_file()


def test_submit_run_appends_to_existing_file(tmp_path):
    args = {
        "agent": "test-agent",
        "model": "m",
        "report": "The list has 5 rows.",
        "task_id": "extract_count_items",
    }
    mcp_server._submit(args, submissions_dir=tmp_path)
    out = mcp_server._submit(args, submissions_dir=tmp_path)
    assert out["entry"]["runs"] == 2
    assert (tmp_path / "test-agent-m.json").is_file()


def test_submit_run_requires_agent():
    params = {
        "name": "submit_run",
        "arguments": {"report": "The list has 5 rows."},
    }
    resp = call("tools/call", params)
    assert resp["error"]["code"] == mcp_server.INVALID_PARAMS
    assert "agent" in resp["error"]["message"]


def test_parse_error_is_reported():
    # Exercise serve()'s error path via a bad line, capturing stdout.
    import io

    buf = io.StringIO()
    out = io.StringIO()
    buf.write("not json\n")
    buf.seek(0)
    mcp_server.serve(stdin=buf, stdout=out)
    resp = json.loads(out.getvalue().strip())
    assert resp["error"]["code"] == mcp_server.PARSE_ERROR
