"""Scoring pass over a collected run. Separate from collection by design:
re-running this never re-runs inference."""

import json
import pathlib

from ..schema import SCHEMA_VERSION
from ..suite.loader import load_suite
from .programmatic import score_record


def score_run(run_dir, allow_code_exec: bool = True) -> dict:
    run = pathlib.Path(run_dir)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    suite = load_suite(manifest.get("suite_dir", "v1"))
    tasks = {t["id"]: t for t in suite["tasks"]}

    out_path = run / "scores.jsonl"
    n = errors = pending_judge = 0
    unknown: set[str] = set()
    with open(run / "records.jsonl", encoding="utf-8") as fin, \
         open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            rec = json.loads(line)
            task = tasks.get(rec["task_id"])
            if task is None:
                unknown.add(rec["task_id"])
                continue
            res = score_record(rec, task, allow_code_exec=allow_code_exec)
            row = {
                "schema_version": SCHEMA_VERSION,
                "task_id": rec["task_id"],
                "category": rec["category"],
                "model": rec["model"]["name"],
                "repeat": rec["repeat"],
                "score": res["score"],
                "needs_judge": res["needs_judge"],
                "details": res["details"],
            }
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
            errors += bool(rec.get("error"))
            pending_judge += res["needs_judge"]
    summary = {"scored": n, "generation_errors": errors,
               "pending_judge": pending_judge,
               "unknown_tasks": sorted(unknown), "out": str(out_path)}
    return summary
