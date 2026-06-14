"""Offload-cliff sweep: decode throughput vs the number of model layers kept on
the GPU. As fewer layers fit in VRAM, more compute spills to the CPU and decode
tok/s falls — often as a cliff rather than a slope. This automates a sweep across
GPU-layer counts and reports tok/s vs layers (RESEARCH/ROADMAP; FUTURE_EVALUATIONS
E3).

Two backends drive the sweep:
- ollama   : set Ollama's `num_gpu` option per point (the runtime reloads with
             that many layers offloaded). Fully automatable on one machine.
- llamacpp : n_gpu_layers is a llama-server LAUNCH flag, so the sweep talks to
             one already-running server per layer count via a layer->URL map
             (launch them with `llama-server --n-gpu-layers N --port P`).

Self-contained, like context_scale.py / routing_sim.py: imports from metis but
does not write to the main run pipeline. Results go to
results/offload_sweep_<timestamp>/ with a markdown report.

Design rules carried forward:
- Never pass --force to a real run; if preflight quiesce fails, skip the run.
- No prices in this script; this is a speed experiment.

Usage (Windows):
    python offload_sweep.py --backend ollama --model qwen3:8b ^
        --layers 0,8,16,24,33 --repeats 3
    python offload_sweep.py --backend llamacpp --model qwen3-8b ^
        --url-map "0=http://localhost:8081,16=http://localhost:8082"
    python offload_sweep.py --selftest
"""

from __future__ import annotations

import argparse
import json
import pathlib
from datetime import datetime

# Mirror metis.runner.PREFLIGHT_CPU_LIMIT: a real inference sweep on a busy
# machine produces unfair speed numbers, so when preflight fails we skip rather
# than override. There is deliberately no --force here.
PREFLIGHT_CPU_LIMIT = 40.0

# A short, fixed decode-bound prompt: we care about decode tok/s, not the answer.
SWEEP_PROMPT = (
    "Write a clear, detailed paragraph explaining how a bicycle gear system "
    "lets a rider climb hills more easily. Aim for about 150 words.")


def preflight_ok() -> tuple[bool, dict]:
    """Return (ok, info). ok is False when background CPU load is too high.
    Falls back to ok=True if psutil is unavailable, recording that fact."""
    try:
        import psutil
    except ImportError:
        return True, {"checked": False, "reason": "psutil not installed"}
    cpu = psutil.cpu_percent(interval=1.0)
    vm = psutil.virtual_memory()
    info = {"checked": True, "cpu_pct": cpu,
            "ram_available_gb": round(vm.available / 2**30, 1)}
    return cpu <= PREFLIGHT_CPU_LIMIT, info


def run_sweep(layers: list[int], gen_fn) -> list[dict]:
    """For each layer count call gen_fn(layer) -> result dict and collect.

    gen_fn returns {ok, decode_tps, wall_s, output_tokens, error}. Injectable so
    the sweep/aggregation logic is testable without a GPU.
    """
    results = []
    for layer in layers:
        gen = gen_fn(layer)
        results.append({"n_gpu_layers": layer, **gen})
    return results


def _by_layer(results: list[dict]) -> dict:
    from collections import defaultdict
    agg: dict[int, dict] = defaultdict(lambda: {"tps": [], "wall": [],
                                                 "errors": 0})
    for r in results:
        a = agg[r["n_gpu_layers"]]
        if r.get("ok") and r.get("decode_tps") is not None:
            a["tps"].append(r["decode_tps"])
            if r.get("wall_s") is not None:
                a["wall"].append(r["wall_s"])
        else:
            a["errors"] += 1
    return agg


def detect_offload_knee(results: list[dict]) -> dict:
    """Find the steepest *gain* step: the adjacent pair of (ascending) layer
    counts with the largest relative jump in mean decode tok/s. That boundary is
    where moving more layers onto the GPU stops the CPU spill — the offload knee.
    Computed from collected results alone (no model calls)."""
    agg = _by_layer(results)
    means = []
    for layer in sorted(agg):
        tps = agg[layer]["tps"]
        if tps:
            means.append((layer, sum(tps) / len(tps)))
    if len(means) < 2:
        return {"knee": None, "note": "need at least two layer points with data"}
    best = None
    for (lo_l, lo_t), (hi_l, hi_t) in zip(means, means[1:]):
        if lo_t <= 0:
            continue
        gain = hi_t / lo_t
        if best is None or gain > best[0]:
            best = (gain, lo_l, hi_l, lo_t, hi_t)
    if best is None:
        return {"knee": None, "note": "no positive baseline to compare"}
    gain, lo_l, hi_l, lo_t, hi_t = best
    return {
        "knee": hi_l,
        "from_layers": lo_l,
        "to_layers": hi_l,
        "from_tps": round(lo_t, 1),
        "to_tps": round(hi_t, 1),
        "gain_ratio": round(gain, 2),
        "note": (f"Steepest throughput gain between {lo_l} and {hi_l} GPU layers "
                 f"(~{lo_t:.0f} -> ~{hi_t:.0f} tok/s, {gain:.1f}x): below "
                 f"{hi_l} layers the model spills to CPU and decode collapses."),
    }


def format_report(results: list[dict], model: str, backend: str,
                  header_notes: list[str] | None = None) -> str:
    agg = _by_layer(results)

    def _mean(lst):
        return sum(lst) / len(lst) if lst else None

    layers = sorted(agg)
    tps_means = {l: _mean(agg[l]["tps"]) for l in layers}
    peak = max((v for v in tps_means.values() if v is not None), default=0.0) or 1.0

    lines = [f"# Offload-cliff sweep — {model} ({backend})", ""]
    lines.append("Decode throughput vs number of model layers kept on the GPU. "
                 "Fewer GPU layers spill more compute to the CPU; the point where "
                 "tok/s jumps is the offload knee.")
    lines.append("")
    for note in (header_notes or []):
        lines.append(f"- {note}")
    if header_notes:
        lines.append("")
    knee = detect_offload_knee(results)
    lines.append(f"**offload_knee: {knee['knee']}** — {knee['note']}")
    lines.append("")
    lines.append("| GPU layers | decode tok/s | wall_s (mean) | errors | |")
    lines.append("|---|---|---|---|---|")
    for l in layers:
        tp = tps_means[l]
        wl = _mean(agg[l]["wall"])
        bar = "#" * int(round((tp / peak) * 20)) if tp else ""
        tp_str = f"{tp:.1f}" if tp is not None else "—"
        wl_str = f"{wl:.1f}" if wl is not None else "—"
        lines.append(f"| {l} | {tp_str} | {wl_str} | {agg[l]['errors']} | {bar} |")
    lines.append("")
    lines.append("Reading it: tok/s should rise as more layers move onto the GPU "
                 "and plateau once the model is fully resident; a sharp step "
                 "(not a gentle ramp) marks the VRAM offload boundary for this "
                 "model and card.")
    return "\n".join(lines)


def ollama_gen_fn(model: str, num_ctx: int, num_predict: int,
                  base_url: str = "http://localhost:11434", prompt: str = SWEEP_PROMPT):
    """Build a gen_fn that sets Ollama's num_gpu per point. Unloads first so the
    runtime reloads with the new offload count."""
    from metis.backends.ollama import OllamaBackend
    be = OllamaBackend(base_url)

    def _gen(layer: int) -> dict:
        try:
            be.unload(model)
        except Exception:
            pass
        opts = {"temperature": 0, "seed": 1234, "num_ctx": num_ctx,
                "num_predict": num_predict, "num_gpu": layer,
                "keep_alive": "2m"}
        res = be.chat(model, [{"role": "user", "content": prompt}], opts)
        tps = (res.output_tokens / res.eval_s) if res.eval_s > 0 else None
        return {"ok": res.error is None, "decode_tps": round(tps, 1) if tps else None,
                "wall_s": round(res.wall_s, 3), "output_tokens": res.output_tokens,
                "error": res.error}
    return _gen


def llamacpp_gen_fn(model: str, num_predict: int, url_map: dict[int, str],
                    prompt: str = SWEEP_PROMPT):
    """Build a gen_fn that talks to one pre-launched llama-server per layer count
    (layer -> base_url). Launch each with `llama-server --n-gpu-layers N`."""
    from metis.backends.llamacpp import LlamaCppBackend

    def _gen(layer: int) -> dict:
        url = url_map.get(layer)
        if not url:
            return {"ok": False, "decode_tps": None, "wall_s": None,
                    "output_tokens": 0,
                    "error": f"no server URL mapped for {layer} layers"}
        be = LlamaCppBackend(url, n_gpu_layers=layer)
        res = be.chat(model, [{"role": "user", "content": prompt}],
                      {"temperature": 0, "seed": 1234, "num_predict": num_predict})
        tps = (res.output_tokens / res.eval_s) if res.eval_s > 0 else None
        return {"ok": res.error is None, "decode_tps": round(tps, 1) if tps else None,
                "wall_s": round(res.wall_s, 3), "output_tokens": res.output_tokens,
                "error": res.error}
    return _gen


def _selftest() -> None:
    # Synthetic tok/s-vs-layers with a clear cliff between 8 and 16 layers.
    profile = {0: 5.0, 8: 6.0, 16: 18.0, 24: 40.0, 33: 42.0}

    def mock_gen(layer: int) -> dict:
        return {"ok": True, "decode_tps": profile[layer], "wall_s": 10.0,
                "output_tokens": 200, "error": None}

    layers = [0, 8, 16, 24, 33]
    results = run_sweep(layers, mock_gen)
    assert len(results) == len(layers)
    assert {r["n_gpu_layers"] for r in results} == set(layers)

    knee = detect_offload_knee(results)
    # Biggest relative jump is 6 -> 18 (3.0x) between 8 and 16 layers.
    assert knee["knee"] == 16, knee
    assert knee["from_layers"] == 8 and knee["to_layers"] == 16, knee
    assert knee["gain_ratio"] == 3.0, knee

    # Multiple repeats per layer are averaged.
    rep = run_sweep([0, 0, 33, 33], lambda l: {
        "ok": True, "decode_tps": 4.0 if l == 0 else 40.0, "wall_s": 1.0,
        "output_tokens": 100, "error": None})
    agg = _by_layer(rep)
    assert len(agg[0]["tps"]) == 2 and len(agg[33]["tps"]) == 2

    # Errors are recorded, not dropped, and never crash the report.
    err_results = run_sweep([0, 16], lambda l: (
        {"ok": False, "decode_tps": None, "wall_s": None, "output_tokens": 0,
         "error": "OOM"} if l == 0 else
        {"ok": True, "decode_tps": 20.0, "wall_s": 5.0, "output_tokens": 100,
         "error": None}))
    assert _by_layer(err_results)[0]["errors"] == 1

    # Degenerate input: single point -> no knee, no crash.
    assert detect_offload_knee(run_sweep([16], mock_gen))["knee"] is None

    # Report renders and carries the knee flag and a row per layer.
    report = format_report(results, "qwen3:8b", "ollama")
    assert "offload_knee: 16" in report, report
    assert "GPU layers" in report and "| 33 |" in report

    print("selftest: all assertions passed")


def main() -> None:
    ap = argparse.ArgumentParser(description="Offload-cliff sweep for Metis.")
    ap.add_argument("--backend", choices=["ollama", "llamacpp"], default="ollama")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--layers", default="0,8,16,24,33",
                    help="comma-separated GPU-layer counts to sweep")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--num-ctx", type=int, default=4096)
    ap.add_argument("--num-predict", type=int, default=256)
    ap.add_argument("--base-url", default="http://localhost:11434",
                    help="Ollama base URL (ollama backend)")
    ap.add_argument("--url-map", default=None,
                    help="llamacpp: 'layers=url,...' map of pre-launched servers")
    ap.add_argument("--out", default=None, help="optional results JSON path")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return

    layers = [int(x) for x in args.layers.split(",") if x.strip()]
    sweep_layers = [l for l in layers for _ in range(args.repeats)]

    if args.backend == "ollama":
        ok, pf = preflight_ok()
        if not ok:
            print(f"Preflight: background CPU load is {pf.get('cpu_pct'):.0f}% "
                  f"(limit {PREFLIGHT_CPU_LIMIT:.0f}%). Skipping the real sweep "
                  f"rather than forcing it. No --force here.")
            return
        print(f"Preflight: {pf}")
        gen_fn = ollama_gen_fn(args.model, args.num_ctx, args.num_predict,
                               args.base_url)
        notes = [f"model: {args.model} | backend: ollama | repeats: "
                 f"{args.repeats} | num_ctx: {args.num_ctx} | "
                 f"num_predict: {args.num_predict}", f"preflight: {pf}"]
    else:
        if not args.url_map:
            raise SystemExit(
                "llamacpp sweep needs --url-map 'layers=url,...' pointing at one "
                "pre-launched llama-server per layer count.")
        url_map = {}
        for pair in args.url_map.split(","):
            k, _, v = pair.partition("=")
            url_map[int(k.strip())] = v.strip()
        gen_fn = llamacpp_gen_fn(args.model, args.num_predict, url_map)
        notes = [f"model: {args.model} | backend: llamacpp | repeats: "
                 f"{args.repeats} | num_predict: {args.num_predict}",
                 f"url_map: {url_map}"]

    print(f"Sweeping layers {layers} (x{args.repeats}) ...")
    results = run_sweep(sweep_layers, gen_fn)
    report = format_report(results, args.model, args.backend, header_notes=notes)
    print(report)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = pathlib.Path(f"results/offload_sweep_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(r) for r in results), encoding="utf-8")
    (out_dir / "report.md").write_text(report + "\n", encoding="utf-8")
    print(f"\nResults written to {out_dir}/")
    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
