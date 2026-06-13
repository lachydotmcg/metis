"""Compute judge–human agreement once human_labels.jsonl exists.

Usage (from repo root):
    python validation/agreement.py
    python validation/agreement.py --labels validation/human_labels.jsonl --out validation/agreement_report.md

Reads human_labels.jsonl (produced by editing to_label.jsonl from extract_labels.py),
computes Pearson correlation and mean absolute error between judge_score and
human_score, and writes a markdown report.

Plain-assert tests are in tests/test_judge_agreement.py — run them with:
    python tests/test_judge_agreement.py
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson r between two equal-length sequences. Returns NaN for n<2."""
    n = len(xs)
    if n < 2:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return float("nan")
    return num / (den_x * den_y)


def mean_abs_error(xs: list[float], ys: list[float]) -> float:
    """Mean absolute error between judge scores (xs) and human scores (ys)."""
    if not xs:
        return float("nan")
    return sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs)


def compute_agreement(labels: list[dict]) -> dict:
    """Compute agreement stats from a list of labeled rows.

    Each row must have numeric 'judge_score' and 'human_score'.
    Returns {n, pearson_r, mae, per_task, rows_skipped}.
    """
    paired: list[tuple[float, float, str]] = []
    skipped = 0
    for row in labels:
        j = row.get("judge_score")
        h = row.get("human_score")
        if j is None or h is None:
            skipped += 1
            continue
        try:
            paired.append((float(j), float(h), row.get("task_id", "")))
        except (TypeError, ValueError):
            skipped += 1

    judge_scores = [p[0] for p in paired]
    human_scores = [p[1] for p in paired]
    r = pearson(judge_scores, human_scores)
    mae = mean_abs_error(judge_scores, human_scores)

    # Per-task breakdown.
    by_task: dict[str, list[tuple[float, float]]] = {}
    for js, hs, tid in paired:
        by_task.setdefault(tid, []).append((js, hs))
    per_task = {
        tid: {
            "n": len(pairs),
            "judge_mean": sum(p[0] for p in pairs) / len(pairs),
            "human_mean": sum(p[1] for p in pairs) / len(pairs),
            "mae": mean_abs_error([p[0] for p in pairs], [p[1] for p in pairs]),
        }
        for tid, pairs in sorted(by_task.items())
    }

    return {
        "n": len(paired),
        "rows_skipped": skipped,
        "pearson_r": round(r, 4),
        "mae": round(mae, 4),
        "per_task": per_task,
    }


def format_report(stats: dict, labels_path: str) -> str:
    lines = ["# Judge–Human Agreement Report", ""]
    lines.append(f"Labels file : `{labels_path}`")
    lines.append(f"Pairs scored: {stats['n']}")
    if stats["rows_skipped"]:
        lines.append(f"Rows skipped (missing score): {stats['rows_skipped']}")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append(f"| metric | value |")
    lines.append(f"|---|---|")
    r = stats["pearson_r"]
    mae = stats["mae"]
    lines.append(f"| Pearson r (judge vs human) | {r:.4f} |")
    lines.append(f"| Mean absolute error        | {mae:.4f} |")
    lines.append("")
    if not math.isnan(r):
        if r >= 0.9:
            lines.append("Interpretation: strong agreement (r ≥ 0.9).")
        elif r >= 0.7:
            lines.append("Interpretation: moderate agreement (0.7 ≤ r < 0.9). "
                         "Review disagreements before paper use.")
        else:
            lines.append("Interpretation: weak agreement (r < 0.7). "
                         "Recalibrate judge rubric before paper use.")
    lines.append("")
    lines.append("## Per Task")
    lines.append("")
    lines.append("| task | n | judge mean | human mean | MAE |")
    lines.append("|---|---|---|---|---|")
    for tid, t in stats["per_task"].items():
        lines.append(f"| {tid} | {t['n']} | {t['judge_mean']:.3f} | "
                     f"{t['human_mean']:.3f} | {t['mae']:.3f} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Compute judge–human agreement from labeled JSONL.")
    ap.add_argument("--labels", default="validation/human_labels.jsonl",
                    help="Path to human_labels.jsonl (human_score fields filled).")
    ap.add_argument("--out", default=None,
                    help="Optional path for the markdown report.")
    args = ap.parse_args()

    path = pathlib.Path(args.labels)
    if not path.exists():
        print(f"ERROR: {args.labels} does not exist.")
        print("Run extract_labels.py first, fill in human_score, and save as human_labels.jsonl.")
        raise SystemExit(1)

    labels = _load_jsonl(path)
    stats = compute_agreement(labels)
    report = format_report(stats, args.labels)
    print(report)
    if args.out:
        pathlib.Path(args.out).write_text(report, encoding="utf-8")
        print(f"\nReport saved to {args.out}")


if __name__ == "__main__":
    main()
