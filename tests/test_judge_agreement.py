"""Tests for validation/agreement.py — synthetic labeled set, no real data needed.
Plain asserts, no pytest dependency.

Run: python tests/test_judge_agreement.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation.agreement import pearson, mean_abs_error, compute_agreement, format_report


def test_pearson_perfect_positive():
    xs = [0.0, 0.25, 0.5, 0.75, 1.0]
    ys = [0.0, 0.25, 0.5, 0.75, 1.0]
    assert abs(pearson(xs, ys) - 1.0) < 1e-9


def test_pearson_perfect_negative():
    xs = [0.0, 0.5, 1.0]
    ys = [1.0, 0.5, 0.0]
    assert abs(pearson(xs, ys) - (-1.0)) < 1e-9


def test_pearson_nan_when_too_few():
    import math
    assert math.isnan(pearson([], []))
    assert math.isnan(pearson([0.5], [0.5]))


def test_pearson_nan_when_constant():
    import math
    # All judge scores the same → zero variance → NaN.
    assert math.isnan(pearson([0.5, 0.5, 0.5], [0.3, 0.7, 0.5]))


def test_mae_zero_when_identical():
    xs = [0.2, 0.5, 0.9]
    assert mean_abs_error(xs, xs) == 0.0


def test_mae_correct():
    xs = [0.0, 1.0]
    ys = [0.5, 0.5]
    assert abs(mean_abs_error(xs, ys) - 0.5) < 1e-9


def test_compute_agreement_synthetic():
    # Perfect linear agreement (judge == human) -> r = 1.0, MAE = 0.
    labels_perfect = [
        {"task_id": "summarisation.ferry", "model": "qwen3:8b", "repeat": 1,
         "judge_score": 0.8, "human_score": 0.8},
        {"task_id": "summarisation.ferry", "model": "qwen3:8b", "repeat": 2,
         "judge_score": 0.6, "human_score": 0.6},
        {"task_id": "summarisation.changelog", "model": "qwen3:8b", "repeat": 1,
         "judge_score": 1.0, "human_score": 1.0},
        {"task_id": "summarisation.changelog", "model": "qwen3:8b", "repeat": 2,
         "judge_score": 0.4, "human_score": 0.4},
    ]
    stats = compute_agreement(labels_perfect)
    assert stats["n"] == 4
    assert stats["rows_skipped"] == 0
    assert abs(stats["pearson_r"] - 1.0) < 1e-6, stats
    assert abs(stats["mae"] - 0.0) < 1e-9, stats

    # Imperfect agreement: judge consistently over-scores by 0.1.
    labels_biased = [
        {"task_id": "summarisation.ferry", "judge_score": 0.8, "human_score": 0.7},
        {"task_id": "summarisation.ferry", "judge_score": 0.6, "human_score": 0.5},
        {"task_id": "summarisation.changelog", "judge_score": 1.0, "human_score": 0.9},
        {"task_id": "summarisation.changelog", "judge_score": 0.4, "human_score": 0.3},
    ]
    stats2 = compute_agreement(labels_biased)
    # Constant offset preserves perfect correlation.
    assert abs(stats2["pearson_r"] - 1.0) < 1e-6, stats2
    assert abs(stats2["mae"] - 0.1) < 1e-9, stats2


def test_compute_agreement_skips_missing():
    labels = [
        {"task_id": "summarisation.ferry", "judge_score": 0.8, "human_score": None},
        {"task_id": "summarisation.ferry", "judge_score": 0.6, "human_score": 0.5},
        {"task_id": "summarisation.ferry", "judge_score": None, "human_score": 0.9},
    ]
    stats = compute_agreement(labels)
    assert stats["n"] == 1
    assert stats["rows_skipped"] == 2


def test_format_report_smoke():
    labels = [
        {"task_id": "summarisation.ferry", "judge_score": 0.8, "human_score": 0.8},
        {"task_id": "summarisation.ferry", "judge_score": 0.6, "human_score": 0.6},
    ]
    stats = compute_agreement(labels)
    report = format_report(stats, "validation/human_labels.jsonl")
    assert "Pearson r" in report
    assert "Mean absolute error" in report
    assert "summarisation.ferry" in report


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok {fn.__name__}")
    print(f"OK - {len(fns)} test groups passed")
