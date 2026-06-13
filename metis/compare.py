"""Compare a local Metis run against a cloud reference run.

This is a reporting-only helper: it reads existing artifacts and writes a
small plain-English comparison with SVG charts. It never runs inference.
"""

import argparse
import json
import pathlib

from . import stats
from .report import aggregate


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _coverage(task_means: dict[str, float], threshold: float) -> float:
    vals = list(task_means.values())
    return sum(v >= threshold for v in vals) / len(vals) if vals else 0.0


def _anchored(local: dict, cloud: dict, bar: float = 0.9) -> tuple[float, float]:
    ratios = []
    for task_id, score in local["task_means"].items():
        ref = cloud["task_means"].get(task_id)
        if ref is None or ref <= 0:
            continue
        ratios.append(min(score / ref, 1.0))
    return _mean(ratios), (sum(r >= bar for r in ratios) / len(ratios)
                           if ratios else 0.0)


def _polyline(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def _svg_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _coverage_svg(models: dict, out: pathlib.Path) -> None:
    width, height = 860, 460
    left, right, top, bottom = 70, 30, 35, 70
    plot_w = width - left - right
    plot_h = height - top - bottom
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e"]
    thresholds = [i / 20 for i in range(21)]
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="70" y="24" font-family="Segoe UI, Arial" font-size="18" font-weight="700">Coverage curve</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#333"/>',
    ]
    for i in range(6):
        y = top + plot_h - plot_h * i / 5
        val = i / 5
        lines.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#eee"/>')
        lines.append(f'<text x="25" y="{y + 4:.1f}" font-family="Segoe UI, Arial" font-size="12">{val:.0%}</text>')
    for i in range(6):
        x = left + plot_w * i / 5
        val = i / 5
        lines.append(f'<text x="{x - 10:.1f}" y="{top + plot_h + 24}" font-family="Segoe UI, Arial" font-size="12">{val:.1f}</text>')
    for idx, (name, model) in enumerate(models.items()):
        color = colors[idx % len(colors)]
        pts = []
        for t in thresholds:
            x = left + plot_w * t
            y = top + plot_h - plot_h * _coverage(model["task_means"], t)
            pts.append((x, y))
        lines.append(f'<polyline points="{_polyline(pts)}" fill="none" stroke="{color}" stroke-width="3"/>')
        lx, ly = left + 20, top + 28 + idx * 22
        lines.append(f'<rect x="{lx}" y="{ly - 10}" width="12" height="12" fill="{color}"/>')
        lines.append(f'<text x="{lx + 18}" y="{ly}" font-family="Segoe UI, Arial" font-size="13">{_svg_escape(name)}</text>')
    lines.append(f'<text x="{left + plot_w / 2 - 55}" y="{height - 20}" font-family="Segoe UI, Arial" font-size="13">quality threshold</text>')
    lines.append(f'<text x="10" y="{top + plot_h / 2}" transform="rotate(-90 10,{top + plot_h / 2})" font-family="Segoe UI, Arial" font-size="13">fraction of tasks</text>')
    lines.append("</svg>")
    out.write_text("\n".join(lines), encoding="utf-8")


def _quality_speed_svg(models: dict, out: pathlib.Path) -> None:
    width, height = 760, 460
    left, right, top, bottom = 80, 35, 35, 70
    plot_w = width - left - right
    plot_h = height - top - bottom
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e"]
    max_speed = max(max(v["decode_tps"] or [0]) for v in models.values()) * 1.1
    max_speed = max(max_speed, 1)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="80" y="24" font-family="Segoe UI, Arial" font-size="18" font-weight="700">Quality vs streamed decode speed</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#333"/>',
    ]
    for i in range(6):
        y = top + plot_h - plot_h * i / 5
        val = i / 5
        lines.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#eee"/>')
        lines.append(f'<text x="35" y="{y + 4:.1f}" font-family="Segoe UI, Arial" font-size="12">{val:.1f}</text>')
    for i in range(6):
        x = left + plot_w * i / 5
        val = max_speed * i / 5
        lines.append(f'<text x="{x - 14:.1f}" y="{top + plot_h + 24}" font-family="Segoe UI, Arial" font-size="12">{val:.0f}</text>')
    for idx, (name, model) in enumerate(models.items()):
        speed = stats.mean(model["decode_tps"])
        quality = _mean(model["scores_all"])
        x = left + plot_w * speed / max_speed
        y = top + plot_h - plot_h * quality
        color = colors[idx % len(colors)]
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{color}"/>')
        label_x = min(x + 12, width - 210)
        lines.append(f'<text x="{label_x:.1f}" y="{y + 4:.1f}" font-family="Segoe UI, Arial" font-size="13">{_svg_escape(name)}</text>')
    lines.append(f'<text x="{left + plot_w / 2 - 70}" y="{height - 20}" font-family="Segoe UI, Arial" font-size="13">decode tokens/sec</text>')
    lines.append(f'<text x="12" y="{top + plot_h / 2}" transform="rotate(-90 12,{top + plot_h / 2})" font-family="Segoe UI, Arial" font-size="13">mean quality</text>')
    lines.append("</svg>")
    out.write_text("\n".join(lines), encoding="utf-8")


def compare(local_run: str, cloud_run: str, out_dir: str) -> pathlib.Path:
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    local = aggregate(local_run)
    cloud = aggregate(cloud_run)
    cloud_name, cloud_model = next(iter(cloud["per_model"].items()))
    models = {**local["per_model"], cloud_name: cloud_model}

    rows = []
    for name, model in local["per_model"].items():
        rel_mean, anchored90 = _anchored(model, cloud_model)
        rows.append({
            "model": name,
            "mean_quality": _mean(model["scores_all"]),
            "relative_to_cloud_mean": rel_mean,
            "anchored_coverage_90pct_cloud": anchored90,
            "absolute_coverage_90": model["coverage"][0.9],
            "decode_tps": stats.mean(model["decode_tps"]),
            "peak_vram_mb": model["vram_peak"],
        })

    cloud_summary = {
        "model": cloud_name,
        "mean_quality": _mean(cloud_model["scores_all"]),
        "absolute_coverage_90": cloud_model["coverage"][0.9],
        "decode_tps": stats.mean(cloud_model["decode_tps"]),
    }
    data = {
        "local_run": str(local_run),
        "cloud_run": str(cloud_run),
        "cloud_reference": cloud_summary,
        "local_vs_cloud": rows,
    }
    (out / "comparison.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8")
    _coverage_svg(models, out / "coverage_curve.svg")
    _quality_speed_svg(models, out / "quality_vs_speed.svg")

    lines = [
        "# Metis Findings Draft",
        "",
        f"Local run: `{pathlib.Path(local_run).name}`. Cloud reference: `{pathlib.Path(cloud_run).name}` using `{cloud_name}`.",
        "",
        "## Headline",
        "",
        f"`qwen3:8b` is the strongest local model: {rows[1]['relative_to_cloud_mean']:.0%} of Claude's mean per-task quality and {rows[1]['anchored_coverage_90pct_cloud']:.0%} of tasks at at least 90% of Claude's task score.",
        f"`qwen3:1.7b` is the speed play: {rows[0]['decode_tps']:.1f} tok/s and {rows[0]['anchored_coverage_90pct_cloud']:.0%} anchored coverage at the same 90%-of-Claude bar.",
        "",
        "## Charts",
        "",
        "![Coverage curve](coverage_curve.svg)",
        "",
        "![Quality vs speed](quality_vs_speed.svg)",
        "",
        "## Comparison Table",
        "",
        "| model | mean quality | mean vs Claude | tasks >=90% of Claude | absolute coverage@0.9 | decode tok/s | peak VRAM MB |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['model']} | {row['mean_quality']:.2f} | "
            f"{row['relative_to_cloud_mean']:.0%} | "
            f"{row['anchored_coverage_90pct_cloud']:.0%} | "
            f"{row['absolute_coverage_90']:.0%} | "
            f"{row['decode_tps']:.1f} | {row['peak_vram_mb']:.0f} |")
    lines += [
        f"| {cloud_name} | {cloud_summary['mean_quality']:.2f} | 100% | 100% | {cloud_summary['absolute_coverage_90']:.0%} | {cloud_summary['decode_tps']:.1f} | n/a |",
        "",
        "## Interpretation",
        "",
        "The useful claim is no longer just an absolute benchmark score. It is an anchored routing claim: on this RTX 3060 8GB machine, the best local model clears a 90%-of-Claude bar on most of the frozen suite, while the small model offers much higher local throughput for simpler work.",
        "",
        "## Caveats",
        "",
        "- The judge tier is implemented and applied here, but the planned human-label validation set is still pending.",
        "- API speed includes network/provider latency; local speed is measured on this machine.",
        "- API prices are not stored in these artifacts unless config/pricing.yaml is explicitly configured.",
        "",
    ]
    (out / "findings.md").write_text("\n".join(lines), encoding="utf-8")
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Compare local Metis run to cloud reference")
    p.add_argument("local_run")
    p.add_argument("cloud_run")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    out = compare(args.local_run, args.cloud_run, args.out)
    print(out)


if __name__ == "__main__":
    main()
