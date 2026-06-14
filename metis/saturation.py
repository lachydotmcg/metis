"""Saturation / ceiling-effect metrics (NEXT_AGENT_PLAN priority 1).

Derived entirely from already-scored run artifacts — this module runs NO models
and makes NO network calls. It exists to keep Metis honest about a real trap:
when a strong reference (cloud) model nearly maxes out the suite, the
local-vs-reference score ratio measures *how much of this practical suite the
local model covers*, not a general intelligence gap. A stronger frontier model
also scoring ~100% would mean the suite is saturated, not that the two models
are equal.

These metrics surface that ceiling so the number can't be overread:
- mean_score        — reference quality on the suite
- frac_tasks_at_ceiling      — share of tasks essentially maxed (>= CEILING)
- frac_categories_saturated  — share of categories at/above CATEGORY_SATURATION
- headroom          — 1 - mean_score; how much room a harder model has to differ
- saturated         — boolean: the suite can no longer distinguish this model
                      from a hypothetically stronger one
"""

from __future__ import annotations

import json
import pathlib

from . import stats
from .report import aggregate

# A task counts as "at the ceiling" when its mean score is essentially perfect.
CEILING = 0.99
# A category is "saturated" when its mean score clears this.
CATEGORY_SATURATION = 0.95
# A model is flagged saturated when it scores very high overall AND tops out on
# at least half the tasks — i.e. the suite has run out of discriminating power
# for it.
SATURATED_MEAN = 0.90
SATURATED_CEILING_FRACTION = 0.5


def model_saturation(entry: dict, ceiling: float = CEILING,
                     cat_threshold: float = CATEGORY_SATURATION) -> dict:
    """Saturation metrics for one model's `aggregate()` per-model entry."""
    task_means = entry.get("task_means", {}) or {}
    by_cat = entry.get("scores_by_cat", {}) or {}
    n = len(task_means)
    mean_score = stats.mean(list(task_means.values())) if task_means else 0.0
    at_ceiling = sum(1 for m in task_means.values() if m >= ceiling)
    frac_ceiling = (at_ceiling / n) if n else 0.0
    cat_means = {c: stats.mean(v) for c, v in by_cat.items() if v}
    sat_cats = [c for c, m in cat_means.items() if m >= cat_threshold]
    frac_cats = (len(sat_cats) / len(cat_means)) if cat_means else 0.0
    saturated = (mean_score >= SATURATED_MEAN
                 and frac_ceiling >= SATURATED_CEILING_FRACTION)
    return {
        "mean_score": round(mean_score, 4),
        "tasks": n,
        "tasks_at_ceiling": at_ceiling,
        "frac_tasks_at_ceiling": round(frac_ceiling, 4),
        "categories_saturated": sorted(sat_cats),
        "frac_categories_saturated": round(frac_cats, 4),
        "headroom": round(1.0 - mean_score, 4),
        "saturated": saturated,
    }


def compute(run_dir, ceiling: float = CEILING,
            cat_threshold: float = CATEGORY_SATURATION) -> dict:
    """Saturation for every model in a scored run. The reference is the
    highest-mean model (normally the cloud/frontier model)."""
    data = aggregate(run_dir)
    per_model = {m: model_saturation(e, ceiling, cat_threshold)
                 for m, e in data["per_model"].items()}
    reference = (max(per_model, key=lambda m: per_model[m]["mean_score"])
                 if per_model else None)
    return {
        "run": str(run_dir),
        "ceiling": ceiling,
        "category_threshold": cat_threshold,
        "reference_model": reference,
        "reference_saturated": bool(reference and per_model[reference]["saturated"]),
        "per_model": per_model,
    }


def interpretation(result: dict) -> str:
    """The honest one-paragraph reading, conditioned on whether the suite is
    saturated by its strongest model."""
    ref = result.get("reference_model")
    if not ref:
        return "No scored models found in this run."
    rm = result["per_model"][ref]
    if result["reference_saturated"]:
        return (
            f"Suite saturated by {ref}: mean {rm['mean_score']:.2f}, "
            f"{rm['frac_tasks_at_ceiling']:.0%} of tasks at the ceiling, only "
            f"{rm['headroom']:.2f} headroom. Read local-vs-{ref} as **suite "
            f"coverage**, not a general-capability ratio. A stronger model also "
            f"scoring ~100% here would indicate the suite has run out of "
            f"discriminating power, not that the models are equivalent. To rank "
            f"frontier models against each other, a harder suite (frontier "
            f"headroom) is required."
        )
    return (
        f"{ref} is not saturated (mean {rm['mean_score']:.2f}, headroom "
        f"{rm['headroom']:.2f}): the suite still has room to distinguish stronger "
        f"models, so cross-model differences are meaningful here."
    )


def render_markdown(result: dict) -> str:
    lines = [f"# Saturation report — {result['run']}", ""]
    lines.append(f"reference model : {result['reference_model']}")
    lines.append(f"reference saturated : {result['reference_saturated']}")
    lines.append(f"ceiling : {result['ceiling']} | category threshold : "
                 f"{result['category_threshold']}")
    lines.append("")
    lines.append("| model | mean | tasks@ceiling | cats saturated | headroom | saturated |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for m, s in sorted(result["per_model"].items(),
                       key=lambda kv: -kv[1]["mean_score"]):
        lines.append(
            f"| {m} | {s['mean_score']:.3f} | "
            f"{s['tasks_at_ceiling']}/{s['tasks']} "
            f"({s['frac_tasks_at_ceiling']:.0%}) | "
            f"{len(s['categories_saturated'])} "
            f"({s['frac_categories_saturated']:.0%}) | "
            f"{s['headroom']:.3f} | {s['saturated']} |")
    lines += ["", "## Interpretation", "", interpretation(result)]
    return "\n".join(lines) + "\n"


def write_report(run_dir, out_path=None) -> pathlib.Path:
    result = compute(run_dir)
    run = pathlib.Path(run_dir)
    out = pathlib.Path(out_path) if out_path else run / "saturation.md"
    out.write_text(render_markdown(result), encoding="utf-8")
    (run / "saturation.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    return out
