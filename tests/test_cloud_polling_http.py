"""Cloud polling uses real urllib and a local synthetic HTTP server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from benchmarks import run_suite
from deedchain.adapters import browser_use_cloud
from deedchain.tasks import load_all_tasks


@pytest.fixture
def cloud_server():
    state = {"status": "cancelled", "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["requests"].append(("GET", self.path))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": "local-run", "status": state["status"]}).encode())

        def do_POST(self):
            state["requests"].append(("POST", self.path))
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"id": "local-run"}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:{}/runs".format(server.server_port), state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_terminal_run_returns_after_one_http_request(cloud_server, status):
    url, state = cloud_server
    state["status"] = status
    result = browser_use_cloud.wait_for_run(
        "local-run", key="local-test-only", base_url=url, timeout=0.2, poll_seconds=0.01
    )
    assert result["status"] == status
    assert state["requests"] == [("GET", "/runs/local-run")]


def test_cancelled_benchmark_is_excluded_without_waiting(cloud_server):
    url, state = cloud_server
    task = next(iter(load_all_tasks().values()))
    with pytest.raises(browser_use_cloud.CloudAPIError, match="was cancelled"):
        run_suite.run_one(
            task, "https://example.com", "local-test-only",
            api_base=url, timeout=0.2, poll_seconds=0.01,
        )
    assert state["requests"] == [("POST", "/runs"), ("GET", "/runs/local-run")]
