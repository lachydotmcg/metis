"""Phase 0 routing simulation — prove the concept on existing Metis data.

No router code. This treats the per-category Metis scores as a hand-written
routing policy and simulates three strategies over the suite (all-cloud,
all-local, routed) to answer one question:

    Does a dumb per-category rule keep ~all the task success of all-cloud,
    at a fraction of the cost?

If yes, Phase 1 (a runtime router) is worth building. If no, we stop here.

Cost formulas are lifted verbatim from metis/economics.py so the numbers match
the rest of Metis:
    local  = energy_j / 3.6e6 * electricity_per_kwh  +  wall_s / 3600 * amort
    cloud  = (prompt_tokens * rate_in + output_tokens * rate_out) / 1e6 * fx

Honesty rule (METHODOLOGY §7, mirrored from economics.py): Metis ships no
default prices. If pricing.yaml is unconfigured, success still prints but cost
is withheld rather than shown as a misleading zero.

Usage (Windows):
    python routing_sim.py --local-run results\\20260612_173212 ^
                          --local-model qwen3:8b ^
                          --cloud-run results\\20260612_214955 ^
                          --cloud-model deepseek-v4-pro
    python routing_sim.py --local-run ... --local-model ... --cloud-run ... --sweep 0.85,0.9,0.95
    python routing_sim.py --selftest
"""

from __future__ import annotations

import argparse
import json
import pathlib
from collections import defaultdict

import yaml

# Categories are decided per-category; route to local when the local model's
# mean score in that category clears this bar, else cloud.
DEFAULT_THRESHOLD = 0.9


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _score_key(row: dict) -> tuple[str, str, int]:
    return row["task_id"], row["model"], int(row["repeat"])


def load_merged_scores(run_dir: pathlib.Path) -> list[dict]:
    """Final scores with tier-2 judge values overlaid, matching Metis's own
    report._merged_scores: judge_scores.jsonl never mutates scores.jsonl, so the
    overlay must happen at read time. Without this, needs_judge tasks
    (summarisation) would use tier-1 constraint-only placeholders."""
    scores = _load_jsonl(run_dir / "scores.jsonl")
    smap = {_score_key(s): dict(s) for s in scores}
    judge_path = run_dir / "judge_scores.jsonl"
    if judge_path.exists():
        for row in _load_jsonl(judge_path):
            key = _score_key(row)
            base = smap.get(key)
            if not base or not base.get("needs_judge") or row.get("score") is None:
                continue
            merged = dict(row)
            merged["tier1_score"] = base.get("score")
            merged["judge_applied"] = True
            smap[key] = merged
    return list(smap.values())


def per_task_mean_score(scores: list[dict]) -> dict[str, float]:
    """Mean score per task_id across repeats (so repeat counts that differ
    between runs do not distort the comparison)."""
    acc: dict[str, list[float]] = defaultdict(list)
    for s in scores:
        acc[s["task_id"]].append(float(s["score"]))
    return {t: sum(v) / len(v) for t, v in acc.items()}


def task_category(scores: list[dict]) -> dict[str, str]:
    return {s["task_id"]: s["category"] for s in scores}


def _score_model(row: dict) -> str:
    return str(row["model"])


def _record_model(row: dict) -> str:
    return str(row["model"]["name"])


def _filter_rows(rows: list[dict], model: str | None, label: str, getter) -> list[dict]:
    models = sorted({getter(row) for row in rows})
    if model is None:
        if len(models) == 1:
            model = models[0]
        else:
            raise SystemExit(
                f"{label} run contains multiple models; pass --{label}-model "
                f"(available: {', '.join(models)})")
    selected = [row for row in rows if getter(row) == model]
    if not selected:
        raise SystemExit(
            f"{label} model {model!r} not found "
            f"(available: {', '.join(models)})")
    return selected


def per_task_local_cost(records: list[dict], tariff: float, amort: float) -> dict[str, float]:
    """Mean measured local cost per task across repeats."""
    acc: dict[str, list[float]] = defaultdict(list)
    for r in records:
        kwh = r["monitor"].get("energy_j", 0) / 3.6e6
        hours = r["timings"]["wall_s"] / 3600
        acc[r["task_id"]].append(kwh * tariff + hours * amort)
    return {t: sum(v) / len(v) for t, v in acc.items()}


def per_task_cloud_cost(
    records: list[dict], rate_in: float, rate_out: float, fx: float
) -> dict[str, float]:
    """Mean API-equivalent cost per task across repeats, at configured rates."""
    acc: dict[str, list[float]] = defaultdict(list)
    for r in records:
        cost = (
            r["timings"]["prompt_tokens"] * rate_in
            + r["timings"]["output_tokens"] * rate_out
        ) / 1e6 * fx
        acc[r["task_id"]].append(cost)
    return {t: sum(v) / len(v) for t, v in acc.items()}


def category_means(
    score_by_task: dict[str, float], cat_by_task: dict[str, str]
) -> dict[str, float]:
    acc: dict[str, list[float]] = defaultdict(list)
    for task, score in score_by_task.items():
        acc[cat_by_task[task]].append(score)
    return {c: sum(v) / len(v) for c, v in acc.items()}


def build_policy(local_cat_means: dict[str, float], threshold: float) -> dict[str, str]:
    """The hand-written policy: local if the category clears the bar, else cloud."""
    return {
        c: ("local" if mean >= threshold else "cloud")
        for c, mean in local_cat_means.items()
    }


def build_comparative_policy(
    local_cat_means: dict[str, float], cloud_cat_means: dict[str, float]
) -> dict[str, str]:
    """Route local only when local category quality is at least cloud quality."""
    return {
        c: ("local" if local_cat_means[c] >= cloud_cat_means[c] else "cloud")
        for c in local_cat_means
    }


def simulate(
    tasks: list[str],
    cat_by_task: dict[str, str],
    local_score: dict[str, float],
    cloud_score: dict[str, float],
    local_cost: dict[str, float] | None,
    cloud_cost: dict[str, float] | None,
    policy: dict[str, str],
) -> dict[str, dict]:
    """Compute success and cost for all-cloud, all-local, and the routed policy
    over the shared task set. Cost is None when pricing is unconfigured."""
    have_cost = local_cost is not None and cloud_cost is not None

    def run(pick) -> dict:
        success = 0.0
        cost = 0.0
        for t in tasks:
            backend = pick(t)
            success += local_score[t] if backend == "local" else cloud_score[t]
            if have_cost:
                cost += local_cost[t] if backend == "local" else cloud_cost[t]
        return {"success": success, "cost": cost if have_cost else None}

    return {
        "all-cloud": run(lambda t: "cloud"),
        "all-local": run(lambda t: "local"),
        "routed": run(lambda t: policy[cat_by_task[t]]),
    }


def format_report(
    threshold: float,
    local_run: str,
    cloud_run: str,
    currency: str,
    local_cat_means: dict[str, float],
    cloud_cat_means: dict[str, float],
    policy: dict[str, str],
    results: dict[str, dict],
    n_tasks: int,
    pricing_notes: list[str],
) -> str:
    lines: list[str] = []
    lines.append("# Phase 0 - routing simulation")
    lines.append("")
    lines.append(f"local run : {local_run}")
    lines.append(f"cloud run : {cloud_run}")
    lines.append(f"tasks     : {n_tasks} (shared by both runs)")
    lines.append(f"threshold : {threshold} (route local if local category mean >= this)")
    lines.append("")

    lines.append("## Policy (per category)")
    lines.append("")
    lines.append("| category | local mean | cloud mean | -> routed to |")
    lines.append("|---|---|---|---|")
    for c in sorted(policy):
        lines.append(
            f"| {c} | {local_cat_means[c]:.3f} | {cloud_cat_means[c]:.3f} | {policy[c]} |"
        )
    lines.append("")

    have_cost = results["all-cloud"]["cost"] is not None
    lines.append("## Strategies")
    lines.append("")
    if have_cost:
        lines.append(f"| strategy | success (/{n_tasks}) | cost ({currency}) | cost / success |")
        lines.append("|---|---|---|---|")
        for name in ("all-cloud", "all-local", "routed"):
            r = results[name]
            cps = r["cost"] / r["success"] if r["success"] else float("inf")
            lines.append(
                f"| {name} | {r['success']:.2f} | {r['cost']:.4f} | {cps:.6f} |"
            )
        lines.append("")
        cloud = results["all-cloud"]
        routed = results["routed"]
        kept = routed["success"] / cloud["success"] if cloud["success"] else 0.0
        saved = (1 - routed["cost"] / cloud["cost"]) if cloud["cost"] else 0.0
        lines.append("## Verdict")
        lines.append("")
        lines.append(
            f"Routed keeps {kept * 100:.1f}% of all-cloud's task success "
            f"and costs {saved * 100:.1f}% less."
        )
        if kept >= 0.98 and saved > 0:
            lines.append("=> Concept holds: ~equal quality, lower cost. Phase 1 is worth building.")
        elif saved > 0:
            lines.append("=> Cheaper, but quality dropped. Worth revisiting the threshold before Phase 1.")
        else:
            lines.append("=> No cost win. Phase 1 is not justified on this data.")
    else:
        lines.append(f"| strategy | success (/{n_tasks}) | cost ({currency}) |")
        lines.append("|---|---|---|")
        for name in ("all-cloud", "all-local", "routed"):
            lines.append(f"| {name} | {results[name]['success']:.2f} | (set pricing) |")
        lines.append("")
        lines.append("## Verdict")
        lines.append("")
        lines.append(
            "Success computed, but cost is withheld because config/pricing.yaml "
            "is unconfigured. The cost-per-success proof needs real numbers."
        )

    if pricing_notes:
        lines.append("")
        for note in pricing_notes:
            lines.append(f"> {note}")
    return "\n".join(lines)


class SimData:
    """Everything that does NOT depend on the threshold, loaded once so a sweep
    only re-runs the cheap policy + simulate step per threshold."""

    def __init__(
        self,
        local_run: str,
        cloud_run: str,
        pricing_path: str,
        local_model: str | None = None,
        cloud_model: str | None = None,
    ):
        local = pathlib.Path(local_run)
        cloud = pathlib.Path(cloud_run)
        cfg = yaml.safe_load(pathlib.Path(pricing_path).read_text(encoding="utf-8"))

        self.local_run = local_run
        self.cloud_run = cloud_run
        self.local_model = local_model
        self.cloud_model = cloud_model
        self.currency = cfg.get("currency", "USD")
        tariff = float(cfg.get("electricity_per_kwh", 0))
        amort = float(cfg.get("hardware_amortisation_per_hour", 0))
        api = cfg.get("api_reference") or {}
        rate_in = float(api.get("usd_per_mtok_input", 0))
        rate_out = float(api.get("usd_per_mtok_output", 0))
        fx = float(api.get("usd_to_local", 1.0))

        rates_ok = rate_in > 0 or rate_out > 0
        tariff_ok = tariff > 0
        self.pricing_notes = []
        if not tariff_ok:
            self.pricing_notes.append(
                "electricity_per_kwh is 0 in pricing.yaml - local cost cannot be priced."
            )
        if not rates_ok:
            self.pricing_notes.append(
                "api_reference rates are 0 in pricing.yaml - cloud cost cannot be priced."
            )

        local_scores = _filter_rows(
            load_merged_scores(local), local_model, "local", _score_model)
        cloud_scores = _filter_rows(
            load_merged_scores(cloud), cloud_model, "cloud", _score_model)
        local_recs = _filter_rows(
            _load_jsonl(local / "records.jsonl"), local_model, "local",
            _record_model)
        cloud_recs = _filter_rows(
            _load_jsonl(cloud / "records.jsonl"), cloud_model, "cloud",
            _record_model)
        self.local_model = _score_model(local_scores[0])
        self.cloud_model = _score_model(cloud_scores[0])

        self.local_score = per_task_mean_score(local_scores)
        self.cloud_score = per_task_mean_score(cloud_scores)
        self.cat_by_task = {**task_category(cloud_scores), **task_category(local_scores)}

        # Fair comparison: only tasks present in both runs.
        self.tasks = sorted(set(self.local_score) & set(self.cloud_score))
        if not self.tasks:
            raise SystemExit("No shared task_ids between the two runs.")

        can_cost = tariff_ok and rates_ok
        self.local_cost = per_task_local_cost(local_recs, tariff, amort) if can_cost else None
        self.cloud_cost = per_task_cloud_cost(cloud_recs, rate_in, rate_out, fx) if can_cost else None

        self.local_cat_means = category_means(
            {t: self.local_score[t] for t in self.tasks}, self.cat_by_task
        )
        self.cloud_cat_means = category_means(
            {t: self.cloud_score[t] for t in self.tasks}, self.cat_by_task
        )

    def at_threshold(self, threshold: float) -> tuple[dict, dict]:
        """Return (policy, strategy_results) for one threshold."""
        policy = build_policy(self.local_cat_means, threshold)
        results = simulate(
            self.tasks, self.cat_by_task, self.local_score, self.cloud_score,
            self.local_cost, self.cloud_cost, policy,
        )
        return policy, results

    def comparative(self) -> tuple[dict, dict]:
        """Return (policy, strategy_results) for local >= cloud quality."""
        policy = build_comparative_policy(
            self.local_cat_means, self.cloud_cat_means)
        results = simulate(
            self.tasks, self.cat_by_task, self.local_score, self.cloud_score,
            self.local_cost, self.cloud_cost, policy,
        )
        return policy, results


def run_sim(
    local_run: str,
    cloud_run: str,
    pricing_path: str,
    threshold: float,
    local_model: str | None = None,
    cloud_model: str | None = None,
) -> str:
    data = SimData(local_run, cloud_run, pricing_path, local_model, cloud_model)
    policy, results = data.at_threshold(threshold)
    return format_report(
        threshold, local_run, cloud_run, data.currency,
        data.local_cat_means, data.cloud_cat_means, policy, results,
        len(data.tasks), data.pricing_notes,
    )


def run_sweep(local_run: str, cloud_run: str, pricing_path: str,
              thresholds: list[float], local_model: str | None = None,
              cloud_model: str | None = None) -> str:
    """Deliverable (a): one combined table across thresholds."""
    data = SimData(local_run, cloud_run, pricing_path, local_model, cloud_model)
    n = len(data.tasks)
    have_cost = data.local_cost is not None and data.cloud_cost is not None

    lines = ["# Phase 0 - threshold sweep", ""]
    lines.append(f"local run : {local_run}")
    lines.append(f"local model : {data.local_model}")
    lines.append(f"cloud run : {cloud_run}")
    lines.append(f"cloud model : {data.cloud_model}")
    lines.append(f"tasks     : {n} (shared by both runs)")
    lines.append("")

    # all-cloud / all-local are threshold-independent; compute once.
    _, base = data.at_threshold(0.0)
    if have_cost:
        for name in ("all-cloud", "all-local"):
            r = base[name]
            cps = r["cost"] / r["success"] if r["success"] else float("inf")
            lines.append(f"{name}: success {r['success']:.2f}/{n}, "
                         f"cost {data.currency} {r['cost']:.4f}, cost/success {cps:.6f}")
    else:
        for name in ("all-cloud", "all-local"):
            lines.append(f"{name}: success {base[name]['success']:.2f}/{n} (cost: set pricing)")
    lines.append("")

    if have_cost:
        lines.append("| threshold | local cats | success | cost | cost/success | "
                     "% of cloud success | % cost saved |")
        lines.append("|---|---|---|---|---|---|---|")
    else:
        lines.append("| threshold | local cats | routed success | % of cloud success |")
        lines.append("|---|---|---|---|")

    cloud = base["all-cloud"]
    policies: list[tuple[float, dict]] = []
    for th in thresholds:
        policy, results = data.at_threshold(th)
        policies.append((th, policy))
        r = results["routed"]
        local_cats = ",".join(c for c, b in sorted(policy.items()) if b == "local") or "(none)"
        kept = r["success"] / cloud["success"] * 100 if cloud["success"] else 0.0
        if have_cost:
            cps = r["cost"] / r["success"] if r["success"] else float("inf")
            saved = (1 - r["cost"] / cloud["cost"]) * 100 if cloud["cost"] else 0.0
            lines.append(f"| {th} | {local_cats} | {r['success']:.2f} | "
                         f"{r['cost']:.4f} | {cps:.6f} | {kept:.1f}% | {saved:.1f}% |")
        else:
            lines.append(f"| {th} | {local_cats} | {r['success']:.2f} | {kept:.1f}% |")
    lines.append("")

    lines.append("## Comparative rule: route local when local >= cloud")
    lines.append("")
    comp_policy, comp_results = data.comparative()
    if have_cost:
        lines.append("| local cats | success | cost | cost/success | % of cloud success | % cost saved |")
        lines.append("|---|---:|---:|---:|---:|---:|")
    else:
        lines.append("| local cats | routed success | % of cloud success |")
        lines.append("|---|---:|---:|")
    r = comp_results["routed"]
    local_cats = ",".join(
        c for c, b in sorted(comp_policy.items()) if b == "local") or "(none)"
    kept = r["success"] / cloud["success"] * 100 if cloud["success"] else 0.0
    if have_cost:
        cps = r["cost"] / r["success"] if r["success"] else float("inf")
        saved = (1 - r["cost"] / cloud["cost"]) * 100 if cloud["cost"] else 0.0
        lines.append(
            f"| {local_cats} | {r['success']:.2f} | {r['cost']:.4f} | "
            f"{cps:.6f} | {kept:.1f}% | {saved:.1f}% |")
    else:
        lines.append(f"| {local_cats} | {r['success']:.2f} | {kept:.1f}% |")
    lines.append("")

    lines.append("## Category means (local)")
    for c in sorted(data.local_cat_means):
        lines.append(f"- {c}: local {data.local_cat_means[c]:.3f} | "
                     f"cloud {data.cloud_cat_means[c]:.3f}")

    if data.pricing_notes:
        lines.append("")
        for note in data.pricing_notes:
            lines.append(f"> {note}")
    return "\n".join(lines)


def _selftest() -> None:
    """Plain-assert tests on synthetic in-memory data — no disk, no pricing file."""
    # Two categories: 'easy' local nails it (1.0), 'hard' local fails (0.0).
    scores_local = [
        {"task_id": "e1", "category": "easy", "score": 1.0},
        {"task_id": "e1", "category": "easy", "score": 1.0},  # repeat
        {"task_id": "h1", "category": "hard", "score": 0.0},
    ]
    scores_cloud = [
        {"task_id": "e1", "category": "easy", "score": 1.0},
        {"task_id": "h1", "category": "hard", "score": 1.0},
    ]
    ls = per_task_mean_score(scores_local)
    assert ls == {"e1": 1.0, "h1": 0.0}, ls
    cs = per_task_mean_score(scores_cloud)
    assert cs == {"e1": 1.0, "h1": 1.0}, cs

    cat = {**task_category(scores_cloud), **task_category(scores_local)}
    cmeans = category_means(ls, cat)
    assert cmeans == {"easy": 1.0, "hard": 0.0}, cmeans

    policy = build_policy(cmeans, 0.9)
    assert policy == {"easy": "local", "hard": "cloud"}, policy
    comp_policy = build_comparative_policy(cmeans, {"easy": 1.0, "hard": 1.0})
    assert comp_policy == {"easy": "local", "hard": "cloud"}, comp_policy

    # Cost: local cheap, cloud pricey.
    recs_local = [
        {"task_id": "e1", "monitor": {"energy_j": 3.6e6}, "timings": {"wall_s": 0}},  # 1 kWh
        {"task_id": "h1", "monitor": {"energy_j": 3.6e6}, "timings": {"wall_s": 0}},
    ]
    recs_cloud = [
        {"task_id": "e1", "timings": {"prompt_tokens": 1_000_000, "output_tokens": 0}},
        {"task_id": "h1", "timings": {"prompt_tokens": 1_000_000, "output_tokens": 0}},
    ]
    lc = per_task_local_cost(recs_local, tariff=0.30, amort=0.0)
    assert abs(lc["e1"] - 0.30) < 1e-9, lc  # 1 kWh * 0.30
    cc = per_task_cloud_cost(recs_cloud, rate_in=10.0, rate_out=0.0, fx=1.0)
    assert abs(cc["e1"] - 10.0) < 1e-9, cc  # 1 Mtok * 10.0

    tasks = ["e1", "h1"]
    res = simulate(tasks, cat, ls, cs, lc, cc, policy)
    # all-cloud: success 2.0 (both 1.0), cost 20.0
    assert abs(res["all-cloud"]["success"] - 2.0) < 1e-9, res
    assert abs(res["all-cloud"]["cost"] - 20.0) < 1e-9, res
    # all-local: success 1.0 (e1=1, h1=0), cost 0.60
    assert abs(res["all-local"]["success"] - 1.0) < 1e-9, res
    assert abs(res["all-local"]["cost"] - 0.60) < 1e-9, res
    # routed: e1 local (1.0, 0.30) + h1 cloud (1.0, 10.0) = success 2.0, cost 10.30
    assert abs(res["routed"]["success"] - 2.0) < 1e-9, res
    assert abs(res["routed"]["cost"] - 10.30) < 1e-9, res
    # The whole point: routed matches all-cloud success at lower cost.
    assert res["routed"]["success"] == res["all-cloud"]["success"]
    assert res["routed"]["cost"] < res["all-cloud"]["cost"]

    # Cost withheld when pricing missing.
    res_nocost = simulate(tasks, cat, ls, cs, None, None, policy)
    assert res_nocost["routed"]["cost"] is None
    print("selftest: all assertions passed")


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 0 routing simulation over Metis results.")
    ap.add_argument("--local-run", help="Path to the local-model Metis results dir.")
    ap.add_argument("--local-model", help="Local model name to use when the run has multiple models.")
    ap.add_argument("--cloud-run", help="Path to the cloud-baseline Metis results dir.")
    ap.add_argument("--cloud-model", help="Cloud model name to use when the run has multiple models.")
    ap.add_argument("--pricing", default="config/pricing.yaml", help="Path to pricing.yaml.")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help=f"Route-to-local category-mean bar (default {DEFAULT_THRESHOLD}).")
    ap.add_argument("--sweep", default=None,
                    help="Comma-separated thresholds for a combined sweep table, "
                         "e.g. 0.85,0.9,0.95")
    ap.add_argument("--out", default=None, help="Optional markdown output path.")
    ap.add_argument("--selftest", action="store_true", help="Run assert tests and exit.")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return
    if not args.local_run or not args.cloud_run:
        ap.error("--local-run and --cloud-run are required (or use --selftest).")

    if args.sweep:
        thresholds = [float(x) for x in args.sweep.split(",") if x.strip()]
        text = run_sweep(
            args.local_run, args.cloud_run, args.pricing, thresholds,
            args.local_model, args.cloud_model)
    else:
        text = run_sim(
            args.local_run, args.cloud_run, args.pricing, args.threshold,
            args.local_model, args.cloud_model)
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
