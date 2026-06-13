"""Report generation: markdown + self-contained HTML from records + scores.
Reads artifacts only; never measures anything."""

import json
import pathlib
from collections import defaultdict

from . import stats

COVERAGE_THRESHOLDS = (0.5, 0.7, 0.9)


def _load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _score_key(row: dict) -> tuple[str, str, int]:
    return row["task_id"], row["model"], int(row["repeat"])


def _merged_scores(run: pathlib.Path) -> tuple[dict, int, int]:
    scores = _load_jsonl(run / "scores.jsonl")
    smap = {_score_key(s): dict(s) for s in scores}
    judge_path = run / "judge_scores.jsonl"
    applied = 0
    if judge_path.exists():
        for row in _load_jsonl(judge_path):
            key = _score_key(row)
            base = smap.get(key)
            if not base or not base.get("needs_judge"):
                continue
            if row.get("score") is None:
                continue
            merged = dict(row)
            merged["tier1_score"] = base.get("score")
            merged["needs_judge"] = True
            merged["judge_applied"] = True
            smap[key] = merged
            applied += 1
    pending = sum(1 for s in smap.values()
                  if s.get("needs_judge") and not s.get("judge_applied"))
    return smap, applied, pending


def aggregate(run_dir) -> dict:
    run = pathlib.Path(run_dir)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    fp = json.loads((run / "fingerprint.json").read_text(encoding="utf-8"))
    records = _load_jsonl(run / "records.jsonl")
    smap, judge_applied, pending_judge = _merged_scores(run)

    per_model: dict[str, dict] = {}
    for model in manifest["models"]:
        recs = [r for r in records if r["model"]["name"] == model]
        rows = [smap.get((r["task_id"], model, r["repeat"])) for r in recs]
        scored = [(r, s) for r, s in zip(recs, rows)
                  if s is not None and s["score"] is not None]
        by_cat = defaultdict(list)
        by_task = defaultdict(list)
        for r, s in scored:
            by_cat[r["category"]].append(s["score"])
            by_task[r["task_id"]].append(s["score"])
        task_means = {t: stats.mean(v) for t, v in by_task.items()}
        ok = [r for r in recs if not r.get("error")]
        per_model[model] = {
            "info": manifest["model_infos"].get(model, {}),
            "generations": len(recs),
            "errors": sum(bool(r.get("error")) for r in recs),
            "scores_all": [s["score"] for _, s in scored],
            "scores_by_cat": dict(by_cat),
            "task_means": task_means,
            "coverage": {t: (sum(m >= t for m in task_means.values()) / len(task_means)
                             if task_means else 0.0)
                         for t in COVERAGE_THRESHOLDS},
            "decode_tps": [r["timings"]["decode_tps"] for r in ok
                           if r["timings"]["eval_s"] > 0],
            "prefill_tps": [r["timings"]["prefill_tps"] for r in ok
                            if r["timings"]["prompt_eval_s"] > 0],
            "ttft": [r["timings"]["ttft_s"] for r in ok
                     if r["timings"]["ttft_s"] > 0],
            "vram_peak": max((r["monitor"].get("vram_peak_mb", 0) for r in recs),
                             default=0),
            "power_avg": stats.mean([r["monitor"]["power_avg_w"] for r in recs
                                     if "power_avg_w" in r["monitor"]]),
            "energy_wh": sum(r["monitor"].get("energy_j", 0) for r in recs) / 3600,
            "output_tokens": sum(r["timings"]["output_tokens"] for r in recs),
            "prompt_tokens": sum(r["timings"]["prompt_tokens"] for r in recs),
            "pending_judge": sum(
                1 for _, s in scored
                if s.get("needs_judge") and not s.get("judge_applied")),
            "judge_applied": sum(
                1 for _, s in scored if s.get("judge_applied")),
        }
    categories = sorted({r["category"] for r in records})
    return {"manifest": manifest, "fingerprint": fp,
            "per_model": per_model, "categories": categories,
            "judge_applied": judge_applied,
            "pending_judge": pending_judge}


def _sections(data) -> list[tuple[str, list[str], list[list[str]]]]:
    """(title, headers, rows) tables shared by the md and html renderers."""
    pm = data["per_model"]
    cats = data["categories"]
    out = []

    out.append(("Models", ["model", "params", "quant", "digest"], [
        [m, str(v["info"].get("parameter_size", "?")),
         str(v["info"].get("quantization_level", "?")),
         str(v["info"].get("digest", "?"))[:12]]
        for m, v in pm.items()]))

    out.append((
        "Quality (mean score ± 95% CI)",
        ["model", "overall"] + cats,
        [[m, stats.fmt_mean_ci(v["scores_all"])] +
         [stats.fmt_mean_ci(v["scores_by_cat"].get(c, [])) for c in cats]
         for m, v in pm.items()]))

    out.append((
        "Coverage at quality threshold (fraction of tasks with mean score ≥ t)",
        ["model"] + [f"t={t}" for t in COVERAGE_THRESHOLDS],
        [[m] + [f"{v['coverage'][t]:.0%}" for t in COVERAGE_THRESHOLDS]
         for m, v in pm.items()]))

    out.append((
        "Performance",
        ["model", "decode tok/s", "prefill tok/s", "TTFT median (s)",
         "peak VRAM (MB)", "avg power (W)", "energy (Wh)", "errors"],
        [[m, stats.fmt_mean_ci(v["decode_tps"], 1),
          stats.fmt_mean_ci(v["prefill_tps"], 0),
          f"{stats.median(v['ttft']):.2f}" if v["ttft"] else "-",
          f"{v['vram_peak']:.0f}" if v["vram_peak"] else "-",
          f"{v['power_avg']:.0f}" if v["power_avg"] else "-",
          f"{v['energy_wh']:.2f}", str(v["errors"])]
         for m, v in pm.items()]))

    weakest = []
    for m, v in pm.items():
        worst = sorted(v["task_means"].items(), key=lambda kv: kv[1])[:3]
        weakest.append([m, ", ".join(f"{t} ({s:.2f})" for t, s in worst)])
    out.append(("Weakest tasks per model", ["model", "lowest mean scores"],
                weakest))
    return out


def _notes(data) -> list[str]:
    man = data["manifest"]
    fp = data["fingerprint"]
    gpus = "; ".join(f"{g['name']} {g['vram']} (driver {g['driver']})"
                     for g in fp.get("gpus", [])) or "no NVIDIA GPU detected"
    pending = sum(v["pending_judge"] for v in data["per_model"].values())
    judged = sum(v["judge_applied"] for v in data["per_model"].values())
    notes = [
        f"Run `{man['run_id']}` — suite v{man['suite_version']}, "
        f"{man['repeats']} repeats, schedule {man['schedule']}, "
        f"backend {man['backend']['name']} {man['backend']['version']}.",
        f"Machine: {fp.get('cpu')} | {fp.get('ram_total_gb')}GB RAM | {gpus} "
        f"| fingerprint `{fp.get('fingerprint_id')}`.",
        f"Sampler: temperature={man['options'].get('temperature')}, "
        f"seed={man['options'].get('seed')}, "
        f"num_ctx={man['options'].get('num_ctx')}.",
    ]
    if pending:
        notes.append(
            f"{pending} generation(s) carry needs_judge: their scores are "
            f"constraint-only until metis judge produces judge_scores.jsonl "
            f"(METHODOLOGY §4).")
    if judged:
        notes.append(
            f"{judged} generation(s) use judge scores from judge_scores.jsonl; "
            "tier-1 scores remain in scores.jsonl.")
    if man.get("generation_errors"):
        notes.append(f"{man['generation_errors']} generation error(s) were "
                     f"recorded and scored 0.")
    return notes


def render_markdown(data) -> str:
    lines = [f"# Metis report — {data['manifest']['run_id']}", ""]
    lines += [f"- {n}" for n in _notes(data)]
    for title, headers, rows in _sections(data):
        lines += ["", f"## {title}", ""]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "---|" * len(headers))
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    return "\n".join(lines)


_HTML_STYLE = """
body{font-family:system-ui,Segoe UI,sans-serif;max-width:960px;margin:2rem auto;
padding:0 1rem;color:#1a1a1a;background:#fafafa}
h1{border-bottom:3px solid #e8761a;padding-bottom:.3rem}
h2{margin-top:2rem;color:#333}
table{border-collapse:collapse;width:100%;margin:.5rem 0;font-size:.9rem}
th,td{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}
th{background:#f3e9df}
tr:nth-child(even){background:#f6f6f6}
ul{font-size:.9rem;color:#444}
code{background:#eee;padding:0 .2rem;border-radius:3px}
"""


def render_html(data) -> str:
    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))
    parts = [f"<style>{_HTML_STYLE}</style>",
             f"<h1>Metis report — {esc(data['manifest']['run_id'])}</h1>",
             "<ul>"]
    parts += [f"<li>{esc(n)}</li>" for n in _notes(data)]
    parts.append("</ul>")
    for title, headers, rows in _sections(data):
        parts.append(f"<h2>{esc(title)}</h2><table><tr>")
        parts += [f"<th>{esc(h)}</th>" for h in headers]
        parts.append("</tr>")
        for row in rows:
            parts.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row)
                         + "</tr>")
        parts.append("</table>")
    return "\n".join(parts)


def write_reports(run_dir) -> tuple[pathlib.Path, pathlib.Path]:
    run = pathlib.Path(run_dir)
    data = aggregate(run)
    md = run / "report.md"
    html = run / "report.html"
    md.write_text(render_markdown(data), encoding="utf-8")
    html.write_text(render_html(data), encoding="utf-8")
    return md, html
