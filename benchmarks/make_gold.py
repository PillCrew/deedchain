"""Reference gold generator for the deedchain task suite (non-LLM, stdlib only).

This is the "reference script" promised by the methodology: it recomputes the
integrity anchors for every frozen fixture and writes or verifies them, so gold
evidence can never be declared by hand and left unchecked.

    python benchmarks/make_gold.py --write   # fill in gold.dom_hash for every task
    python benchmarks/make_gold.py --check   # verify hashes + checks; exit 1 on drift

``--check`` is what the integrity test and CI call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

from deedchain.tasks import (
    count_tags,
    load_all_tasks,
    tasks_dir,
    validate_tasks,
)

ROOT = Path(__file__).resolve().parent


def _fixture_path(task) -> Path:
    return tasks_dir() / task.category / task.fixture


def _report(name: str, ok: bool, detail: str = "") -> str:
    mark = "ok  " if ok else "FAIL"
    return "{}  {:<32} {}".format(mark, name, detail).rstrip()


def check() -> Tuple[bool, List[str]]:
    """Verify every integrity anchor. Returns (ok, lines)."""

    tasks = load_all_tasks()
    lines: List[str] = []
    ok = True

    for task_id in sorted(tasks):
        task = tasks[task_id]
        fp = _fixture_path(task)
        if not fp.is_file():
            ok = False
            lines.append(_report(task_id, False, "fixture missing"))
            continue

        html = fp.read_text(encoding="utf-8")
        hash_line = "dom_hash"
        hash_ok = task.dom_hash == _recompute(fp)
        if not hash_ok:
            ok = False
            hash_line = "dom_hash MISMATCH"
        lines.append(_report(task_id, hash_ok, hash_line))

        for c in task.checks:
            metric, tag = c.get("metric"), c.get("tag")
            actual = count_tags(html, tag)
            declared = task.gold_metrics[metric]
            check_ok = float(actual) == float(declared)
            if not check_ok:
                ok = False
            lines.append(
                _report(
                    task_id,
                    check_ok,
                    "check {metric}={declared} vs <{tag}>={actual}".format(
                        metric=metric, declared=declared, tag=tag, actual=actual
                    ),
                )
            )

    return ok, lines


def _recompute(fp: Path) -> str:
    from deedchain.tasks import compute_dom_hash

    return compute_dom_hash(fp.read_text(encoding="utf-8"))


def write() -> Tuple[bool, List[str]]:
    """Recompute and write gold.dom_hash into every task JSON (idempotent)."""

    tasks = load_all_tasks()
    lines: List[str] = []
    ok = True

    for task_id in sorted(tasks):
        task = tasks[task_id]
        fp = _fixture_path(task)
        html = fp.read_text(encoding="utf-8")
        from deedchain.tasks import compute_dom_hash

        new_hash = compute_dom_hash(html)

        with open(task.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        old_hash = data.get("gold", {}).get("dom_hash")
        data.setdefault("gold", {})["dom_hash"] = new_hash
        with open(task.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

        if old_hash and old_hash != new_hash:
            ok = False
            lines.append(_report(task_id, False, "hash drifted {} -> {}".format(old_hash[:12], new_hash[:12])))
        else:
            lines.append(_report(task_id, True, "dom_hash {}".format(new_hash[:12])))

    return ok, lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate/verify gold evidence for the deedchain task suite.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="write computed dom_hash into each task JSON")
    group.add_argument("--check", action="store_true", help="verify dom_hash + checks; exit 1 on any mismatch")
    args = parser.parse_args(argv)

    if args.write:
        ok, lines = write()
    else:
        ok, lines = check()

    for line in lines:
        print(line)

    suite_ok, errors = validate_tasks()
    if not suite_ok:
        print("suite validation errors:")
        for e in errors:
            print("  " + e)
        ok = False

    print("\n{} anchors verified, {}".format("all" if ok else "SOME", "pass" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
