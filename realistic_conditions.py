"""Realistic-conditions mode: re-run the suite under synthetic RAM pressure and
compare to the clean baseline. Answers FUTURE_EVALUATIONS E4: how much does a
loaded machine (the "40 Chrome tabs" case) change local throughput and quality?

The pressure is synthetic and bounded: RamPressure allocates and touches a
target amount of RAM, but always leaves a safety headroom so it cannot OOM the
machine, and frees everything on exit. The experiment runs the suite twice (clean
then loaded) via the normal Metis runner, scores both, and prints a clean-vs-
loaded delta table.

Self-contained, like context_scale.py / offload_sweep.py: imports from metis but
does not change the engine. A real run is GPU-gated (overnight, idle); the
allocator, the comparison, and the report are pure and unit-tested so the code
lands and is verifiable without a GPU.

Design rules carried forward:
- Never pass --force to a real run; if preflight quiesce fails, skip.
- No prices in this script; this is a speed/quality experiment.
- Errors are recorded and scored 0, never dropped (the underlying runner/scorer
  already enforce this).

Usage (Windows):
    python realistic_conditions.py --model qwen3:8b --repeats 3 --ram-gb 6
    python realistic_conditions.py --selftest
"""

from __future__ import annotations

import argparse
import gc
import json
import pathlib
from datetime import datetime


class RamPressure:
    """Context manager that creates synthetic memory pressure by allocating and
    touching `target_gb` of RAM, capped so at least `headroom_gb` stays free.
    Pages are written so they are actually resident, not lazily reserved. Frees
    everything on exit. `allocated_bytes` reports what was really committed."""

    def __init__(self, target_gb: float, headroom_gb: float = 2.0,
                 chunk_mb: int = 128):
        self.target_gb = target_gb
        self.headroom_gb = headroom_gb
        self.chunk_mb = chunk_mb
        self._buffers: list[bytearray] = []
        self.allocated_bytes = 0

    def _capped_target(self) -> int:
        target = int(self.target_gb * 2**30)
        try:
            import psutil
            available = psutil.virtual_memory().available
            cap = max(0, available - int(self.headroom_gb * 2**30))
            target = min(target, cap)
        except Exception:
            pass
        return target

    def __enter__(self) -> "RamPressure":
        target = self._capped_target()
        chunk = self.chunk_mb * 2**20
        allocated = 0
        while allocated < target:
            size = min(chunk, target - allocated)
            buf = bytearray(size)
            # Touch one byte per 4 KiB page so the OS commits real memory.
            for i in range(0, size, 4096):
                buf[i] = 1
            self._buffers.append(buf)
            allocated += size
        self.allocated_bytes = allocated
        return self

    def __exit__(self, *exc) -> bool:
        self._buffers.clear()
        self.allocated_bytes = 0
        gc.collect()
        return False


def summarise_records(records: list[dict], by_id: dict) -> dict:
    """Aggregate scored records into overall + per-category means of score,
    decode tok/s and wall seconds. Pure: takes records and a task lookup, scores
    each with the real programmatic scorer. Errors score 0 (handled by
    score_record), never dropped."""
    from metis.scoring.programmatic import score_record

    overall = {"score": [], "decode_tps": [], "wall_s": []}
    per_cat: dict[str, dict] = {}
    for rec in records:
        task = by_id.get(rec.get("task_id"))
        if not task:
            continue
        cat = rec.get("category") or task.get("category", "?")
        scored = score_record(rec, task)
        score = scored.get("score")
        timings = rec.get("timings") or {}
        dtps = timings.get("decode_tps")
        wall = timings.get("wall_s")
        bucket = per_cat.setdefault(cat, {"score": [], "decode_tps": [],
                                          "wall_s": []})
        if score is not None:
            overall["score"].append(score)
            bucket["score"].append(score)
        if dtps is not None:
            overall["decode_tps"].append(dtps)
            bucket["decode_tps"].append(dtps)
        if wall is not None:
            overall["wall_s"].append(wall)
            bucket["wall_s"].append(wall)

    def _means(d: dict) -> dict:
        out = {"n": len(d["score"])}
        for k, vals in d.items():
            out[k] = round(sum(vals) / len(vals), 4) if vals else None
        return out

    return {"overall": _means(overall),
            "per_category": {c: _means(b) for c, b in per_cat.items()}}


def _delta(clean: dict, loaded: dict) -> dict:
    out: dict = {}
    for key in ("score", "decode_tps", "wall_s"):
        c, l = clean.get(key), loaded.get(key)
        if c is None or l is None:
            continue
        out[f"{key}_delta"] = round(l - c, 4)
        if key == "decode_tps" and c:
            out["decode_tps_pct"] = round((l - c) / c * 100, 1)
    return out


def compare_conditions(clean: dict, loaded: dict) -> dict:
    """Clean-vs-loaded deltas, overall and per category. Pure and testable."""
    res = {"overall": _delta(clean["overall"], loaded["overall"]),
           "per_category": {}}
    for cat in clean["per_category"]:
        if cat in loaded["per_category"]:
            res["per_category"][cat] = _delta(
                clean["per_category"][cat], loaded["per_category"][cat])
    return res


def format_report(clean: dict, loaded: dict, model: str,
                  ram_note: str = "", header_notes: list[str] | None = None) -> str:
    delta = compare_conditions(clean, loaded)
    lines = [f"# Realistic-conditions mode — {model}", ""]
    lines.append("v1 suite run clean vs under synthetic RAM pressure. Positive "
                 "decode_tps delta means faster under load (unexpected); negative "
                 "means the loaded machine slowed decode. Quality should be "
                 "stable — a score delta is itself a finding.")
    lines.append("")
    if ram_note:
        lines.append(f"- {ram_note}")
    for note in (header_notes or []):
        lines.append(f"- {note}")
    lines.append("")

    def _fmt(v, suffix=""):
        return f"{v}{suffix}" if v is not None else "—"

    co, lo, do = clean["overall"], loaded["overall"], delta["overall"]
    lines.append("## Overall")
    lines.append("")
    lines.append("| metric | clean | loaded | delta |")
    lines.append("|---|---|---|---|")
    lines.append(f"| mean score | {_fmt(co.get('score'))} | "
                 f"{_fmt(lo.get('score'))} | {_fmt(do.get('score_delta'))} |")
    pct = do.get("decode_tps_pct")
    pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
    lines.append(f"| decode tok/s | {_fmt(co.get('decode_tps'))} | "
                 f"{_fmt(lo.get('decode_tps'))} | "
                 f"{_fmt(do.get('decode_tps_delta'))}{pct_str} |")
    lines.append(f"| wall_s (mean) | {_fmt(co.get('wall_s'))} | "
                 f"{_fmt(lo.get('wall_s'))} | {_fmt(do.get('wall_s_delta'))} |")
    lines.append("")
    lines.append("## By category (decode tok/s)")
    lines.append("")
    lines.append("| category | clean | loaded | delta |")
    lines.append("|---|---|---|---|")
    for cat in sorted(clean["per_category"]):
        c = clean["per_category"][cat]
        l = loaded["per_category"].get(cat, {})
        d = delta["per_category"].get(cat, {})
        lines.append(f"| {cat} | {_fmt(c.get('decode_tps'))} | "
                     f"{_fmt(l.get('decode_tps'))} | "
                     f"{_fmt(d.get('decode_tps_delta'))} |")
    lines.append("")
    lines.append("Reading it: if decode tok/s falls materially under RAM "
                 "pressure while quality holds, the local-vs-cloud break-even "
                 "shifts toward cloud on a loaded machine — the 'clean benchmark "
                 "flatters local' caveat, quantified.")
    return "\n".join(lines)


# Mirror metis.runner.PREFLIGHT_CPU_LIMIT (real-run gate; never --force).
PREFLIGHT_CPU_LIMIT = 40.0


def _summarise_run(run_dir: str, suite_version: str) -> dict:
    """I/O wrapper: load a run's records.jsonl and summarise (real-run path)."""
    from metis.suite.loader import load_suite
    by_id = {t["id"]: t for t in load_suite(suite_version)["tasks"]}
    records = []
    rp = pathlib.Path(run_dir) / "records.jsonl"
    for line in rp.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return summarise_records(records, by_id)


def _run_condition(model: str, repeats: int, suite_version: str,
                   out_root: str) -> str:
    """Real-run path: drive the normal Metis runner once. GPU-gated by the
    runner's own preflight; --force is never passed."""
    from metis.runner import run
    options = {"temperature": 0.0, "seed": 1234, "num_ctx": 4096,
               "keep_alive": "5m"}
    run_dir = run(models=[model], backend_name="ollama", repeats=repeats,
                  suite_dir=suite_version, options=options, out_root=out_root,
                  force=False)
    return str(run_dir)


def _selftest() -> None:
    # RamPressure: a tiny target actually commits memory and frees it. headroom 0
    # so the cap does not zero out the 1 MiB request on a busy test machine.
    with RamPressure(target_gb=1 / 1024, headroom_gb=0.0, chunk_mb=1) as rp:
        assert rp.allocated_bytes > 0, rp.allocated_bytes
        held = rp.allocated_bytes
    assert rp.allocated_bytes == 0  # freed on exit
    assert held <= 2 * 2**20  # ~1 MiB, not runaway

    # The cap never lets a request exceed available-minus-headroom. A 10 TB
    # request with a huge headroom must clamp to 0.
    huge = RamPressure(target_gb=10000, headroom_gb=10**6)
    assert huge._capped_target() == 0

    # summarise_records uses the real scorer; build a 2-task fake suite + records.
    by_id = {
        "r.ok": {"id": "r.ok", "category": "reasoning",
                 "scoring": {"type": "numeric_exact", "expected": 7}},
        "r.bad": {"id": "r.bad", "category": "reasoning",
                  "scoring": {"type": "numeric_exact", "expected": 7}},
    }
    recs = [
        {"task_id": "r.ok", "category": "reasoning",
         "output": {"content": "Answer: 7"},
         "timings": {"decode_tps": 40.0, "wall_s": 10.0}},
        {"task_id": "r.bad", "category": "reasoning",
         "output": {"content": "Answer: 8"},
         "timings": {"decode_tps": 30.0, "wall_s": 12.0}},
    ]
    summ = summarise_records(recs, by_id)
    assert summ["overall"]["n"] == 2
    assert summ["overall"]["score"] == 0.5  # one right, one wrong
    assert summ["overall"]["decode_tps"] == 35.0
    assert summ["per_category"]["reasoning"]["wall_s"] == 11.0

    # compare_conditions: synthetic clean vs loaded summaries.
    clean = {"overall": {"score": 1.0, "decode_tps": 40.0, "wall_s": 10.0,
                         "n": 5},
             "per_category": {"reasoning": {"decode_tps": 40.0}}}
    loaded = {"overall": {"score": 1.0, "decode_tps": 30.0, "wall_s": 13.0,
                          "n": 5},
              "per_category": {"reasoning": {"decode_tps": 28.0}}}
    cmp = compare_conditions(clean, loaded)
    assert cmp["overall"]["decode_tps_delta"] == -10.0
    assert cmp["overall"]["decode_tps_pct"] == -25.0
    assert cmp["overall"]["score_delta"] == 0.0
    assert cmp["per_category"]["reasoning"]["decode_tps_delta"] == -12.0

    # Report renders and carries the headline rows.
    rep = format_report(clean, loaded, "qwen3:8b", ram_note="RAM held: 6.0 GB")
    assert "Realistic-conditions" in rep and "decode tok/s" in rep
    assert "-25.0%" in rep

    print("selftest: all assertions passed")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Realistic-conditions (RAM-pressure) mode for Metis.")
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--suite", default="v1")
    ap.add_argument("--ram-gb", type=float, default=6.0,
                    help="target synthetic RAM pressure (capped to leave "
                         "headroom)")
    ap.add_argument("--headroom-gb", type=float, default=3.0)
    ap.add_argument("--out", default="results")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return

    print(f"Realistic-conditions: {args.model}, suite {args.suite}, "
          f"repeats {args.repeats}. Clean baseline then loaded "
          f"(~{args.ram_gb} GB RAM pressure). Never passing --force.")
    print("\n[1/2] Clean baseline run ...")
    clean_dir = _run_condition(args.model, args.repeats, args.suite, args.out)
    clean = _summarise_run(clean_dir, args.suite)

    print(f"\n[2/2] Loaded run under ~{args.ram_gb} GB RAM pressure ...")
    with RamPressure(args.ram_gb, args.headroom_gb) as rp:
        ram_note = f"RAM pressure held: {rp.allocated_bytes / 2**30:.1f} GB"
        print(f"  ({ram_note})")
        loaded_dir = _run_condition(args.model, args.repeats, args.suite, args.out)
    loaded = _summarise_run(loaded_dir, args.suite)

    notes = [f"clean run: {clean_dir}", f"loaded run: {loaded_dir}",
             f"model: {args.model} | repeats: {args.repeats} | suite: {args.suite}"]
    report = format_report(clean, loaded, args.model, ram_note=ram_note,
                           header_notes=notes)
    print("\n" + report)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = pathlib.Path(f"results/realistic_conditions_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(report + "\n", encoding="utf-8")
    (out_dir / "summaries.json").write_text(
        json.dumps({"clean": clean, "loaded": loaded}, indent=2),
        encoding="utf-8")
    print(f"\nResults written to {out_dir}/")


if __name__ == "__main__":
    main()
