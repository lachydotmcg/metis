"""Extract summarisation generations into a to_label.jsonl for human scoring.

Usage (from repo root):
    python validation/extract_labels.py
    python validation/extract_labels.py --run results/20260612_173212 --out validation/to_label.jsonl

Reads records.jsonl + judge_scores.jsonl from the given run directory (default: the
main local study run). Outputs one JSONL line per summarisation generation with
an empty human_score field — Lachy fills these in and saves as
validation/human_labels.jsonl. The judge_score field is present for comparison but
should NOT be consulted until after the human score is assigned (to avoid anchoring).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _score_key(row: dict) -> tuple[str, str, int]:
    return row["task_id"], row["model"], int(row["repeat"])


def extract(run_dir: str, out_path: str, suite_version: str = "v1") -> int:
    """Write to_label.jsonl and return the count of lines written."""
    run = pathlib.Path(run_dir)
    out = pathlib.Path(out_path)

    # Load run artifacts.
    records = _load_jsonl(run / "records.jsonl")
    judge_path = run / "judge_scores.jsonl"
    judge_by_key: dict[tuple, dict] = {}
    if judge_path.exists():
        for row in _load_jsonl(judge_path):
            judge_by_key[_score_key(row)] = row

    # Load suite prompts + references.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from metis.suite.loader import load_suite
    suite = load_suite(suite_version)
    task_info = {t["id"]: t for t in suite["tasks"]}

    out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(out, "w", encoding="utf-8") as fh:
        for rec in records:
            if rec.get("category") != "summarisation":
                continue
            if rec.get("error"):
                continue
            tid = rec["task_id"]
            model = rec["model"]["name"] if isinstance(rec["model"], dict) else rec["model"]
            repeat = int(rec["repeat"])
            key = (tid, model, repeat)
            judge_row = judge_by_key.get(key)
            judge_score = judge_row.get("score") if judge_row else None

            output_text = rec.get("output") or ""
            if isinstance(output_text, dict):
                output_text = output_text.get("content", "")

            info = task_info.get(tid, {})
            row = {
                "id": f"{tid}:{model}:{repeat}",
                "task_id": tid,
                "model": model,
                "repeat": repeat,
                "prompt": info.get("prompt", ""),
                "reference": info.get("oracle_text", ""),
                "candidate_output": str(output_text)[:2000],
                "judge_score": judge_score,
                # Fill this in with a number 0.0..1.0 before running agreement.py.
                # 1.0 = fully faithful, on-target summary; 0.0 = completely wrong.
                "human_score": None,
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1

    return written


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Extract summarisation generations to label.")
    ap.add_argument("--run", default="results/20260612_173212",
                    help="Path to a Metis run directory (default: main local study).")
    ap.add_argument("--out", default="validation/to_label.jsonl",
                    help="Output path for the labelling template.")
    ap.add_argument("--suite", default="v1")
    args = ap.parse_args()

    count = extract(args.run, args.out, args.suite)
    print(f"Wrote {count} rows to {args.out}")
    print()
    print("Next step:")
    print("  Open validation/to_label.jsonl, set 'human_score' for each row,")
    print("  and save the result as validation/human_labels.jsonl.")
    print("  Then run:  python validation/agreement.py")


if __name__ == "__main__":
    main()
