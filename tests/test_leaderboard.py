"""Tests for the static leaderboard (deedchain.leaderboard)."""

import json

from deedchain.leaderboard import (
    build_entries,
    load_submissions,
    render_leaderboard,
    results_to_submission,
    write_leaderboard,
)


class _FakeResult:
    def __init__(self, task_id, success, truthfulness, hallucinated, quadrant, lie_profile):
        self.task_id = task_id
        self.success = success
        self.truthfulness = truthfulness
        self.hallucinated = hallucinated
        self.quadrant = quadrant
        self.lie_profile = lie_profile


class _Quadrant:
    def __init__(self, value):
        self.value = value


def _row(task_id, success, truthfulness, hallucinated, quadrant, lies):
    return _FakeResult(
        task_id, success, truthfulness, hallucinated, _Quadrant(quadrant), lies
    )


def test_results_to_submission_shape():
    r = _row("t1", True, 100.0, False, "honest_success", {"omission": 0, "fabrication": 0, "exaggeration": 0, "displacement": 0})
    sub = results_to_submission("agent", "model", [r], submitted_by="me", date="2026-09-04")
    assert sub["agent"] == "agent"
    assert sub["model"] == "model"
    assert sub["submitted_by"] == "me"
    assert sub["runs"][0]["task_id"] == "t1"
    assert sub["runs"][0]["quadrant"] == "honest_success"


def test_build_entries_ranks_by_honesty():
    submissions = [
        {
            "agent": "liar",
            "model": "m",
            "runs": [
                {"success": True, "truthfulness": 50, "hallucinated": True, "quadrant": "hallucinated_success",
                 "lie_profile": {"omission": 0, "fabrication": 0, "exaggeration": 1, "displacement": 0}},
                {"success": True, "truthfulness": 100, "hallucinated": False, "quadrant": "honest_success",
                 "lie_profile": {"omission": 0, "fabrication": 0, "exaggeration": 0, "displacement": 0}},
            ],
        },
        {
            "agent": "honest",
            "model": "m",
            "runs": [
                {"success": True, "truthfulness": 100, "hallucinated": False, "quadrant": "honest_success",
                 "lie_profile": {"omission": 0, "fabrication": 0, "exaggeration": 0, "displacement": 0}},
            ],
        },
    ]
    entries = build_entries(submissions)
    assert entries[0].agent == "honest"
    assert entries[0].hallucination_rate == 0.0
    assert entries[1].agent == "liar"
    assert entries[1].hallucination_rate == 0.5
    assert entries[1].lie_profile["exaggeration"] == 1


def test_honest_failure_rate():
    submissions = [
        {
            "agent": "a",
            "model": "m",
            "runs": [
                {"success": False, "truthfulness": 100, "hallucinated": False, "quadrant": "honest_failure",
                 "lie_profile": {"omission": 0, "fabrication": 0, "exaggeration": 0, "displacement": 0}},
                {"success": False, "truthfulness": 50, "hallucinated": True, "quadrant": "hallucinated_failure",
                 "lie_profile": {"omission": 0, "fabrication": 1, "exaggeration": 0, "displacement": 0}},
            ],
        }
    ]
    entries = build_entries(submissions)
    assert entries[0].honest_failure_rate == 0.5


def test_render_leaderboard_contains_rows():
    entries = build_entries([])
    text = render_leaderboard(entries)
    assert "report-fidelity leaderboard" in text


def test_write_leaderboard_roundtrip(tmp_path):
    submissions_dir = tmp_path / "submissions"
    submissions_dir.mkdir()
    (submissions_dir / "a.json").write_text(
        json.dumps(
            {
                "agent": "a",
                "model": "m",
                "runs": [
                    {"success": True, "truthfulness": 100, "hallucinated": False,
                     "quadrant": "honest_success",
                     "lie_profile": {"omission": 0, "fabrication": 0, "exaggeration": 0, "displacement": 0}},
                ],
            }
        ),
        encoding="utf-8",
    )
    out_md = tmp_path / "leaderboard.md"
    out_json = tmp_path / "leaderboard.json"
    entries = write_leaderboard(submissions_dir, out_md, out_json)
    assert len(entries) == 1
    assert "| a |" in out_md.read_text(encoding="utf-8")
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["entries"][0]["agent"] == "a"


def test_load_submissions_sorted_and_only_json(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "b.json").write_text('{"agent":"b","runs":[]}', encoding="utf-8")
    (d / "a.json").write_text('{"agent":"a","runs":[]}', encoding="utf-8")
    (d / "notes.txt").write_text("ignore me", encoding="utf-8")
    subs = load_submissions(d)
    assert [s["agent"] for s in subs] == ["a", "b"]
