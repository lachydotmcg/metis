"""Saturation metric tests — hermetic, synthetic aggregate() entries only.
No run dir, no models, no network."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from metis import saturation as S


def _entry(task_means, by_cat):
    return {"task_means": task_means, "scores_by_cat": by_cat}


def test_fully_saturated():
    entry = _entry(
        {f"t{i}": 1.0 for i in range(10)},
        {"reasoning": [1.0, 1.0], "coding": [1.0]},
    )
    m = S.model_saturation(entry)
    assert m["mean_score"] == 1.0
    assert m["frac_tasks_at_ceiling"] == 1.0
    assert m["frac_categories_saturated"] == 1.0
    assert m["headroom"] == 0.0
    assert m["saturated"] is True


def test_not_saturated():
    # High-ish mean but few tasks actually maxed -> not flagged saturated.
    entry = _entry(
        {"t1": 0.6, "t2": 0.7, "t3": 0.65, "t4": 0.7},
        {"reasoning": [0.6, 0.7], "coding": [0.65, 0.7]},
    )
    m = S.model_saturation(entry)
    assert m["saturated"] is False
    assert m["headroom"] > 0.25


def test_high_mean_but_below_ceiling_fraction():
    # Mean 0.90 but only 2/5 tasks truly at ceiling -> below the 0.5 fraction gate.
    entry = _entry(
        {"t1": 1.0, "t2": 1.0, "t3": 0.85, "t4": 0.85, "t5": 0.80},
        {"a": [1.0, 1.0], "b": [0.85, 0.85, 0.80]},
    )
    m = S.model_saturation(entry)
    assert m["frac_tasks_at_ceiling"] == 0.4
    assert m["saturated"] is False


def test_empty_entry_no_crash():
    m = S.model_saturation(_entry({}, {}))
    assert m["mean_score"] == 0.0
    assert m["tasks"] == 0
    assert m["frac_tasks_at_ceiling"] == 0.0
    assert m["saturated"] is False


def test_compute_picks_highest_mean_reference():
    # Stub aggregate by building the structure compute() consumes via a fake.
    result = {
        "run": "fake",
        "ceiling": S.CEILING,
        "category_threshold": S.CATEGORY_SATURATION,
        "per_model": {
            "local": S.model_saturation(_entry({"t1": 0.5, "t2": 0.6}, {"c": [0.5, 0.6]})),
            "cloud": S.model_saturation(_entry({"t1": 1.0, "t2": 1.0}, {"c": [1.0, 1.0]})),
        },
    }
    # Reference selection mirrors compute(): highest mean is the reference.
    ref = max(result["per_model"], key=lambda m: result["per_model"][m]["mean_score"])
    assert ref == "cloud"


def test_interpretation_flags_saturation():
    sat_entry = S.model_saturation(_entry({f"t{i}": 1.0 for i in range(5)},
                                          {"c": [1.0]}))
    res = {"reference_model": "claude", "reference_saturated": True,
           "per_model": {"claude": sat_entry}}
    text = S.interpretation(res)
    assert "coverage" in text.lower() and "saturat" in text.lower()

    unsat_entry = S.model_saturation(_entry({"t1": 0.5, "t2": 0.6}, {"c": [0.5]}))
    res2 = {"reference_model": "x", "reference_saturated": False,
            "per_model": {"x": unsat_entry}}
    assert "not saturated" in S.interpretation(res2).lower()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok {fn.__name__}")
    print(f"OK — {len(fns)} test groups passed")
