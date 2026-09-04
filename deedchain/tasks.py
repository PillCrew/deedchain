"""Load and validate the frozen benchmark task suite.

The task suite is a set of frozen, committed fixtures: each task is a JSON
definition plus the exact HTML page the agent sees, pinned so that the gold
evidence can never drift. Definitions are JSON (not YAML) on purpose: the
package has a hard zero-runtime-dependency promise, and ``json`` is stdlib.

Gold evidence is anchored two ways so it cannot be quietly faked:

1. ``gold.dom_hash`` - the SHA-256 of the canonicalised fixture HTML. Any
   change to the fixture changes the hash, so the integrity test fails loudly.
2. ``gold.checks`` - optional machine-derivable facts (e.g. ``tag_count`` of
   ``<a>``) that the reference script recomputes from the fixture and compares
   against the declared metric. Count metrics declared this way are verified,
   not trusted.

The reference (non-LLM) script that writes/checks these anchors lives at
``benchmarks/make_gold.py`` and reuses the functions in this module.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .evidence import FAILURE, SUCCESS, Evidence

# The six task categories. The first four are "normal" (the task is doable on
# the fixture and a truthful report succeeds); the last two are the honesty
# stress-tests that make deedchain different from a success-rate benchmark.
CATEGORIES = ("nav", "form", "extract", "state", "failure", "temptation")
NORMAL_CATEGORIES = ("nav", "form", "extract", "state")

SUPPORTED_DERIVATIONS = ("tag_count",)


def tasks_dir() -> Path:
    """Absolute path to the benchmark task data directory.

    The data ships in the repo next to the package (``benchmarks/tasks``), not
    inside the installed wheel. The env var ``DEEDCHAIN_TASKS_DIR`` overrides
    the location for packagers and CI.
    """

    override = os.environ.get("DEEDCHAIN_TASKS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "benchmarks" / "tasks"


def canonicalize(text: str) -> str:
    """Canonicalise HTML for hashing: LF newlines, no trailing whitespace, one
    trailing newline. Deterministic across OSes and editors."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def compute_dom_hash(html: str) -> str:
    """SHA-256 of the canonicalised HTML (the integrity anchor for gold)."""

    return hashlib.sha256(canonicalize(html).encode("utf-8")).hexdigest()


class _TagCounter(HTMLParser):
    """Count start tags by name (stdlib, no DOM dependency)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.counts: Dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        self.counts[tag] = self.counts.get(tag, 0) + 1

    def handle_startendtag(self, tag: str, attrs: Any) -> None:
        # XHTML-style <x/> (not void elements; HTMLParser reports those as
        # handle_starttag). Counted too so both spellings agree.
        self.counts[tag] = self.counts.get(tag, 0) + 1


def count_tags(html: str, tag: str) -> int:
    """Return how many ``<tag>`` start tags appear in ``html`` (case-insensitive)."""

    parser = _TagCounter()
    parser.feed(html)
    parser.close()
    return parser.counts.get(tag.lower(), 0)


@dataclass(frozen=True)
class Task:
    """One frozen benchmark task: fixture + instruction + gold evidence."""

    id: str
    category: str
    instruction: str
    fixture: str
    gold_outcome: str
    gold_metrics: Dict[str, Any]
    report_template: str
    dom_hash: str
    checks: Tuple[Dict[str, Any], ...]
    path: Path

    def to_evidence(self) -> Evidence:
        return Evidence(
            task_id=self.id,
            gold_metrics=dict(self.gold_metrics),
            gold_outcome=self.gold_outcome,
            final_dom_hash=self.dom_hash,
        )


def _load_one(path: Path) -> Task:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    gold = data.get("gold", {})
    checks = tuple(gold.get("checks", ()))
    return Task(
        id=data["id"],
        category=data["category"],
        instruction=data["instruction"],
        fixture=data["fixture"],
        gold_outcome=gold.get("outcome", SUCCESS),
        gold_metrics=dict(gold.get("metrics", {})),
        report_template=data.get("report_template", ""),
        dom_hash=gold.get("dom_hash", ""),
        checks=checks,
        path=path,
    )


def load_task(task_id: str, root: Optional[Path] = None) -> Task:
    """Load a single task by id (``nav_click_details`` -> the nav task JSON)."""

    root = root or tasks_dir()
    path = root / task_id.split("__")[0] / "{}.json".format(task_id)
    if not path.is_file():
        path = _find_by_id(root, task_id)
    return _load_one(path)


def _find_by_id(root: Path, task_id: str) -> Path:
    for p in sorted(root.glob("**/*.json")):
        with open(p, "r", encoding="utf-8") as fh:
            if json.load(fh).get("id") == task_id:
                return p
    raise FileNotFoundError("no task with id {!r} under {}".format(task_id, root))


def load_all_tasks(root: Optional[Path] = None) -> Dict[str, Task]:
    """Load every task, keyed by id, in a stable (sorted) order."""

    root = root or tasks_dir()
    out: Dict[str, Task] = {}
    for p in sorted(root.glob("**/*.json")):
        task = _load_one(p)
        out[task.id] = task
    return out


def validate_tasks(root: Optional[Path] = None) -> Tuple[bool, List[str]]:
    """Validate the whole suite. Returns (ok, errors). ``ok`` is True only when
    every task is well-formed, its fixture exists, its dom_hash matches the
    committed fixture, and every declared check is satisfied."""

    root = root or tasks_dir()
    errors: List[str] = []
    seen: Dict[str, str] = {}
    try:
        tasks = load_all_tasks(root)
    except Exception as exc:  # noqa: BLE001 - report any loader failure as an error
        return False, ["failed to load task suite: {}".format(exc)]

    if not tasks:
        return False, ["no task definitions found under {}".format(root)]

    for task_id in sorted(tasks):
        task = tasks[task_id]
        prefix = task_id

        if task.id != task.path.stem:
            errors.append("{}: id does not match filename stem {!r}".format(prefix, task.path.stem))
        if task.category not in CATEGORIES:
            errors.append("{}: unknown category {!r}".format(prefix, task.category))
        if not isinstance(task.instruction, str) or not task.instruction.strip():
            errors.append("{}: instruction is empty".format(prefix))
        if not isinstance(task.fixture, str) or not task.fixture.endswith(".html"):
            errors.append("{}: fixture must be a .html filename".format(prefix))
        if task.gold_outcome not in (SUCCESS, FAILURE):
            errors.append("{}: gold.outcome must be SUCCESS or FAILURE".format(prefix))
        if not isinstance(task.gold_metrics, dict):
            errors.append("{}: gold.metrics must be an object".format(prefix))
        if task.category == "temptation" and not task.report_template.strip():
            errors.append("{}: temptation tasks require report_template".format(prefix))

        for m, value in task.gold_metrics.items():
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                errors.append("{}: metric {!r} has unsupported value {!r}".format(prefix, m, value))

        # Fixture + integrity anchors.
        fixture_path = root / task.category / task.fixture
        if not fixture_path.is_file():
            errors.append("{}: fixture {!r} missing".format(prefix, task.fixture))
            continue

        html = fixture_path.read_text(encoding="utf-8")
        if not html.strip():
            errors.append("{}: fixture is empty".format(prefix))
            continue

        actual_hash = compute_dom_hash(html)
        if not task.dom_hash:
            errors.append("{}: gold.dom_hash is not set (run benchmarks/make_gold.py --write)".format(prefix))
        elif task.dom_hash != actual_hash:
            errors.append("{}: dom_hash mismatch (declared {} != fixture {})".format(prefix, task.dom_hash[:12], actual_hash[:12]))

        for check in task.checks:
            derivation = check.get("derivation")
            if derivation != "tag_count":
                errors.append("{}: unsupported check derivation {!r}".format(prefix, derivation))
                continue
            tag = check.get("tag")
            metric = check.get("metric")
            if not tag or metric not in task.gold_metrics:
                errors.append("{}: malformed check {!r}".format(prefix, check))
                continue
            actual = count_tags(html, tag)
            declared = task.gold_metrics[metric]
            if float(declared) != float(actual):
                errors.append(
                    "{}: check {!r} fails (declared {} != fixture count {})".format(
                        prefix, metric, declared, actual
                    )
                )

        if task.id in seen:
            errors.append("{}: duplicate id (also in {})".format(prefix, seen[task.id]))
        seen[task.id] = task.path.as_posix()

    return (not errors), errors
