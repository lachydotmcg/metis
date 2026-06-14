"""Context-length scaling experiment: quality and speed vs context window size.

Pads reasoning tasks from the v1 suite with neutral filler to fill a target
context length, then runs qwen3:8b at each size and records decode speed, wall
time, and answer quality. This is signature experiment §6 from RESEARCH.md.
(Non-streamed /api/chat is used, so per-token TTFT is not captured here; the
main `metis run` pipeline is the place for streamed TTFT.)

The experiment is self-contained (like routing_sim.py): imports from metis but
does NOT write to the main run pipeline format. Results go to
results/context_scale_<timestamp>/ with a markdown report.

Design rules:
- Never pass --force to a real benchmark run.
- Padding is prepended before the prompt so the model reads through filler
  before seeing the actual task. The correct answer is independent of the filler.
- Token estimation: 1 token ≈ 4 characters (conservative; Qwen3 tokenizer is
  similar). Actual padding length is calibrated to fill ~90% of the target window
  to leave room for the response.
- If a run errors (e.g. OOM at high context), the error is recorded and the
  experiment continues at the next size.

Usage (Windows):
    python context_scale.py --model qwen3:8b --repeats 3 --sizes 512,2048,8192,16384
    python context_scale.py --sizes 512,2048 --out results/context_scale_test.json
    python context_scale.py --selftest

Hard rules carried forward:
    --force is never passed to a real run.
    No prices in this script; this is a quality/speed experiment.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import time
import urllib.error
import urllib.request
from datetime import datetime

# Token-to-character ratio (conservative; avoids truncation).
CHARS_PER_TOKEN = 4
# Fill to 90% of the target window so the response has headroom.
FILL_FRACTION = 0.90
# Default context sizes for the experiment.
DEFAULT_SIZES = (512, 2048, 8192, 16384)
# Neutral filler sentence repeated to fill context.
FILLER_SENTENCE = (
    "The background archive contains the following reference material. "
    "This text has been included for completeness and does not affect the task below. "
)


# Mirror metis.runner.PREFLIGHT_CPU_LIMIT so this experiment obeys the same
# quiesce rule as a real benchmark run. There is deliberately no --force here:
# a real inference run on a busy machine produces unfair speed numbers, so when
# preflight fails we skip the run rather than override it (per OVERNIGHT_PLAN).
PREFLIGHT_CPU_LIMIT = 40.0

# Silent-spill detection: a single-step drop in decode throughput to at or below
# this fraction of the previous (next-smaller) context size's throughput — with
# NO generation errors at the slower size — is the Windows WDDM "fits but crawls"
# signature (the KV cache spills from dedicated VRAM into shared system memory,
# so the run still completes but decode collapses). 0.5 = a >=50% one-step drop.
SILENT_SPILL_RATIO = 0.5


def preflight_ok() -> tuple[bool, dict]:
    """Return (ok, info). ok is False when background CPU load is above the
    limit. Falls back to ok=True if psutil is unavailable, recording that fact
    so the report is honest about what was (not) checked."""
    try:
        import psutil
    except ImportError:
        return True, {"checked": False, "reason": "psutil not installed"}
    cpu = psutil.cpu_percent(interval=1.0)
    vm = psutil.virtual_memory()
    info = {"checked": True, "cpu_pct": cpu,
            "ram_available_gb": round(vm.available / 2**30, 1)}
    return cpu <= PREFLIGHT_CPU_LIMIT, info


def pad_prompt(prompt: str, target_tokens: int) -> str:
    """Prepend neutral filler to fill approximately target_tokens of context.

    The actual task prompt is appended after the filler so the model must
    process the full context before reaching the question.
    """
    target_chars = int(target_tokens * CHARS_PER_TOKEN * FILL_FRACTION)
    overhead = len(prompt)
    filler_chars = max(0, target_chars - overhead)
    if filler_chars == 0:
        return prompt
    reps = filler_chars // len(FILLER_SENTENCE) + 1
    filler = (FILLER_SENTENCE * reps)[:filler_chars]
    return filler + "\n\n" + prompt


def _ollama_chat(prompt: str, model: str, num_ctx: int,
                 base_url: str = "http://localhost:11434",
                 timeout_s: float = 300.0) -> dict:
    """Call Ollama /api/chat for a single user turn. Returns timing + output.

    Uses the chat endpoint (consistent with metis/backends/ollama.py) and sets
    num_predict to 2048 so thinking models (qwen3) have enough tokens for both
    the think block and the visible response.
    """
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "num_ctx": num_ctx,
            "temperature": 0,
            "seed": 1234,
            "num_predict": 2048,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat", data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            raw = r.read().decode("utf-8")
        wall_s = time.perf_counter() - t0
        j = json.loads(raw)
        content = (j.get("message") or {}).get("content", "") or ""
        return {
            "ok": True,
            "output": content,
            "wall_s": wall_s,
            "eval_count": j.get("eval_count", 0),
            "eval_duration_ns": j.get("eval_duration", 0),
            "prompt_eval_count": j.get("prompt_eval_count", 0),
            "prompt_eval_duration_ns": j.get("prompt_eval_duration", 0),
            "total_duration_ns": j.get("total_duration", 0),
            "error": None,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "output": "", "wall_s": time.perf_counter() - t0,
                "error": str(e)}


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> spans before scoring, mirroring Metis's
    methodology (thinking is stored but never scored)."""
    return re.sub(r"<think>.*?</think>", " ", text, flags=re.DOTALL | re.IGNORECASE)


# Markers and wrappers qwen3-class models use for their final answer.
_BOXED = re.compile(r"\\boxed\{([^}]*)\}")
_MARKER = re.compile(r"(?:final\s+)?answer\W{0,3}[:\-]", re.IGNORECASE)
_TRIM = " *`_.:#$\n{}"


def _answer_blob(text: str) -> str:
    r"""Return the region most likely to hold the final answer: the last
    \boxed{} content, else everything after the last 'Answer' marker, else the
    whole thinking-stripped text. Scoring searches within this region so that
    in-reasoning numbers are not mistaken for the answer."""
    text = _strip_thinking(text)
    boxed = _BOXED.findall(text)
    if boxed:
        return boxed[-1]
    markers = list(_MARKER.finditer(text))
    if markers:
        return text[markers[-1].end():]
    return text


def _extract_answer(text: str) -> str | None:
    r"""Best-effort single-token answer for display/tests. Handles markdown and
    LaTeX the model wraps around the value (e.g. '**Answer:** 7',
    '$$\boxed{Saturday}$$'). Returns None when no marker or \boxed{} is found."""
    stripped = _strip_thinking(text)
    boxed = _BOXED.findall(stripped)
    if boxed:
        return boxed[-1].strip(_TRIM) or None
    markers = list(_MARKER.finditer(stripped))
    if not markers:
        return None
    tail = stripped[markers[-1].end():].strip(_TRIM)
    first = tail.splitlines()[0].strip(_TRIM) if tail else ""
    return first or None


def _score_reasoning(output: str, expected) -> float:
    r"""1.0 if the answer region matches expected. Numeric expected: any number
    in the region equals it. Choice expected: word-boundary, case-insensitive
    match. Robust to markdown bolding and \boxed{} LaTeX wrappers."""
    blob = _answer_blob(output)
    try:
        exp_num = float(str(expected).replace(",", ""))
        is_numeric = True
    except (ValueError, TypeError):
        is_numeric = False
    if is_numeric:
        nums = re.findall(r"-?\d+(?:\.\d+)?", blob.replace(",", ""))
        return 1.0 if any(float(n) == exp_num for n in nums) else 0.0
    return 1.0 if re.search(rf"\b{re.escape(str(expected))}\b", blob,
                            re.IGNORECASE) else 0.0


def run_experiment(model: str, sizes: tuple[int, ...], repeats: int,
                   base_url: str = "http://localhost:11434",
                   mock_fn=None) -> list[dict]:
    """Run the scaling experiment. Returns a list of result dicts.

    mock_fn: if provided, used instead of the real Ollama call (for testing).
    """
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from metis.suite.loader import load_suite

    suite = load_suite("v1")
    tasks = [t for t in suite["tasks"] if t["category"] == "reasoning"]

    results = []
    for size in sizes:
        for task in tasks:
            expected = task["scoring"]["expected"]
            padded = pad_prompt(task["prompt"], size)
            pad_tokens = len(padded) // CHARS_PER_TOKEN
            for rep in range(repeats):
                if mock_fn is not None:
                    gen = mock_fn(padded, model, size)
                else:
                    gen = _ollama_chat(padded, model, size, base_url)
                score = _score_reasoning(gen.get("output", ""), expected) \
                    if gen.get("ok") else None
                tok_s = None
                if gen.get("eval_count") and gen.get("eval_duration_ns"):
                    tok_s = gen["eval_count"] / (gen["eval_duration_ns"] / 1e9)
                results.append({
                    "context_size": size,
                    "task_id": task["id"],
                    "repeat": rep,
                    "prompt_len_chars": len(padded),
                    "prompt_est_tokens": pad_tokens,
                    "ok": gen.get("ok", False),
                    "score": score,
                    "decode_tps": round(tok_s, 1) if tok_s else None,
                    "wall_s": round(gen.get("wall_s", 0), 3),
                    "eval_count": gen.get("eval_count"),
                    "prompt_eval_count": gen.get("prompt_eval_count"),
                    "error": gen.get("error"),
                })
    return results


def _tps_by_size(results: list[dict]) -> dict:
    """Aggregate decode tok/s and error counts per context size."""
    from collections import defaultdict
    agg: dict[int, dict] = defaultdict(lambda: {"tps": [], "errors": 0})
    for r in results:
        a = agg[r["context_size"]]
        if r.get("ok") and r.get("decode_tps") is not None:
            a["tps"].append(r["decode_tps"])
        if not r.get("ok"):
            a["errors"] += 1
    return agg


def detect_silent_spill(results: list[dict],
                        ratio: float = SILENT_SPILL_RATIO) -> dict:
    """Detect a Windows WDDM silent-spill / KV-cache cliff from collected
    results alone — no model calls. Scanning context sizes from small to large,
    flag the first size whose mean decode throughput collapses to <= `ratio` of
    the previous (next-smaller) size's mean throughput while that size still has
    ZERO generation errors (it "fits but crawls"). A drop that comes WITH errors
    is an out-of-memory failure, not a silent spill, and is not flagged here.

    Returns a dict always carrying `silent_spill` (bool) and `note` (str); when
    True it also carries the boundary context size, the baseline/spill tok/s, and
    the drop ratio.
    """
    agg = _tps_by_size(results)
    prev_size = prev_tps = None
    for size in sorted(agg):
        a = agg[size]
        mean_tps = sum(a["tps"]) / len(a["tps"]) if a["tps"] else None
        if mean_tps is None:
            continue
        if (prev_tps is not None and a["errors"] == 0
                and mean_tps <= prev_tps * ratio):
            return {
                "silent_spill": True,
                "boundary_context": size,
                "baseline_context": prev_size,
                "baseline_tps": round(prev_tps, 1),
                "spill_tps": round(mean_tps, 1),
                "drop_ratio": round(mean_tps / prev_tps, 3),
                "ratio_threshold": ratio,
                "note": (
                    f"Decode throughput collapsed from ~{prev_tps:.0f} tok/s at "
                    f"context {prev_size} to ~{mean_tps:.0f} tok/s at context "
                    f"{size} with zero errors — the run 'fits but crawls' "
                    f"(WDDM silent-spill / KV-cache cliff, RESEARCH.md §3)."),
            }
        prev_size, prev_tps = size, mean_tps
    return {
        "silent_spill": False,
        "boundary_context": None,
        "note": ("No silent-spill cliff detected: decode throughput degrades "
                 "gradually with context (no single-step 'fits but crawls' "
                 "drop)."),
    }


def format_report(results: list[dict], model: str,
                  header_notes: list[str] | None = None) -> str:
    """Summarise results as a markdown report."""
    from collections import defaultdict
    by_size: dict[int, dict] = defaultdict(lambda: {
        "scores": [], "tps": [], "wall": [], "errors": 0, "tasks": set()})
    for r in results:
        s = by_size[r["context_size"]]
        s["tasks"].add(r["task_id"])
        if r["ok"]:
            if r["score"] is not None:
                s["scores"].append(r["score"])
            if r["decode_tps"] is not None:
                s["tps"].append(r["decode_tps"])
            s["wall"].append(r["wall_s"])
        else:
            s["errors"] += 1

    def _mean(lst):
        return sum(lst) / len(lst) if lst else None

    lines = [f"# Context-length scaling — {model}", ""]
    lines.append("Quality and speed for v1 reasoning tasks padded to fill "
                 "each context window size. Filler prepended before the "
                 f"actual task; fill fraction = {FILL_FRACTION}.")
    lines.append("")
    for note in (header_notes or []):
        lines.append(f"- {note}")
    if header_notes:
        lines.append("")
    spill = detect_silent_spill(results)
    lines.append(f"**silent_spill: {str(spill['silent_spill']).lower()}** — "
                 f"{spill['note']}")
    lines.append("")
    lines.append("| context | tasks | score (mean) | decode tok/s | wall_s (mean) | errors |")
    lines.append("|---|---|---|---|---|---|")
    for size in sorted(by_size):
        s = by_size[size]
        sc_val = _mean(s["scores"])
        tp_val = _mean(s["tps"])
        wl_val = _mean(s["wall"])
        sc_str = f"{sc_val:.2f}" if sc_val is not None else "—"
        tp_str = f"{tp_val:.1f}" if tp_val is not None else "—"
        wl_str = f"{wl_val:.1f}" if wl_val is not None else "—"
        lines.append(f"| {size} | {len(s['tasks'])} | {sc_str} | "
                     f"{tp_str} | {wl_str} | {s['errors']} |")
    lines.append("")
    lines.append("Reading the curve: decode tok/s should fall as context grows "
                 "(KV cache pressure on an 8GB card), and a sharp drop with no "
                 "error is the Windows WDDM silent-spill signature (RESEARCH.md "
                 "§3). Errors at the largest sizes are themselves a finding: the "
                 "context did not fit. Quality is a secondary check that the "
                 "padded task is still answered, not a coverage claim.")
    return "\n".join(lines)


def _selftest() -> None:
    """Plain-assert tests — no disk, no network."""
    # Padding length test.
    short = "How many?"
    padded = pad_prompt(short, 512)
    estimated_tokens = len(padded) // CHARS_PER_TOKEN
    # Should be close to but not exceed 512 * FILL_FRACTION.
    assert estimated_tokens <= 512, f"padding exceeded target: {estimated_tokens}"
    assert estimated_tokens >= int(512 * FILL_FRACTION * 0.8), \
        f"padding too short: {estimated_tokens}"
    # Prompt too long to pad: returned as-is.
    long_prompt = "x" * 10000
    not_padded = pad_prompt(long_prompt, 512)
    assert not_padded == long_prompt, "long prompt should not be padded"

    # Answer extraction, including markdown the model adds around the marker.
    assert _extract_answer("Answer: 7") == "7"
    assert _extract_answer("lots of text\nAnswer: 42\n") == "42"
    assert _extract_answer("**Answer:** 7") == "7"
    assert _extract_answer("reasoning...\n\n**Answer:** Cal") == "Cal"
    assert _extract_answer("no answer here") is None
    # Thinking is stripped, and the last marker wins over in-reasoning mentions.
    assert _extract_answer("<think>maybe Answer: 3</think>\nAnswer: 7") == "7"
    # LaTeX \boxed{} wrappers (qwen3's habit on harder reasoning).
    assert _extract_answer("### Final Answer:\n$$\\boxed{Saturday}$$") == "Saturday"
    assert _extract_answer("**Final Answer:**\n$$\\boxed{12}$$") == "12"

    # Scoring — numeric, markdown-bolded, boxed, and choice answers.
    assert _score_reasoning("Answer: 7", 7) == 1.0
    assert _score_reasoning("Answer: 8", 7) == 0.0
    assert _score_reasoning("48 - 35 - 6 = 7.\n\n**Answer:** 7", 7) == 1.0
    assert _score_reasoning("**Answer:** Cal", "Cal") == 1.0
    assert _score_reasoning("**Answer:** Saturday", "Cal") == 0.0
    assert _score_reasoning("<think>it is 7</think>\n**Answer:** no", "no") == 1.0
    # Boxed final answers must score correctly, and pick the boxed value over
    # the many intermediate numbers in the reasoning.
    assert _score_reasoning("18/7 = 2 weeks 4 days\n$$\\boxed{Saturday}$$", "Saturday") == 1.0
    assert _score_reasoning("240 - 60 = 180; 180/15 = 12\n$$\\boxed{12}$$", 12) == 1.0

    # Mock backend smoke test.
    def mock_fn(prompt, model, num_ctx):
        return {
            "ok": True, "output": "Answer: 42", "wall_s": 0.5,
            "eval_count": 10, "eval_duration_ns": int(1e9), "error": None,
            "prompt_eval_count": len(prompt) // CHARS_PER_TOKEN,
            "prompt_eval_duration_ns": int(1e8),
        }

    results = run_experiment("qwen3:8b", (512, 2048), repeats=1, mock_fn=mock_fn)
    assert len(results) > 0
    # All results should have ok=True.
    assert all(r["ok"] for r in results), results
    # Scores should all be 0 since mock returns "Answer: 42" and tasks expect different numbers.
    sizes_seen = {r["context_size"] for r in results}
    assert sizes_seen == {512, 2048}, sizes_seen

    # Silent-spill detection on synthetic samples (no model calls).
    def _mkres(rows):
        """rows: list of (context_size, decode_tps_or_None, n_errors)."""
        out = []
        for size, tps, errs in rows:
            if tps is not None:
                out.append({"context_size": size, "ok": True,
                            "decode_tps": tps})
            for _ in range(errs):
                out.append({"context_size": size, "ok": False,
                            "decode_tps": None})
        return out

    # A sharp one-step collapse with zero errors = silent spill (the real qwen3
    # 8k->16k cliff: ~40 -> ~10 tok/s, still fits).
    cliff = detect_silent_spill(_mkres(
        [(512, 40, 0), (2048, 38, 0), (8192, 37, 0), (16384, 9.8, 0)]))
    assert cliff["silent_spill"] is True, cliff
    assert cliff["boundary_context"] == 16384, cliff
    assert cliff["baseline_context"] == 8192, cliff

    # A gradual decline (each step > 50% of the last) is NOT a cliff.
    gradual = detect_silent_spill(_mkres(
        [(512, 40, 0), (2048, 30, 0), (8192, 22, 0), (16384, 15, 0)]))
    assert gradual["silent_spill"] is False, gradual

    # A drop that comes WITH generation errors is OOM (did not fit), not a
    # silent spill.
    oom = detect_silent_spill(_mkres(
        [(512, 40, 0), (2048, 38, 0), (8192, 9.0, 3)]))
    assert oom["silent_spill"] is False, oom

    # Multiple repeats at a size are averaged before comparison.
    multi = detect_silent_spill(_mkres(
        [(512, 42, 0), (512, 38, 0), (16384, 9, 0), (16384, 11, 0)]))
    assert multi["silent_spill"] is True and multi["boundary_context"] == 16384

    # Degenerate inputs never crash and report no spill.
    assert detect_silent_spill([])["silent_spill"] is False
    assert detect_silent_spill(_mkres([(512, 40, 0)]))["silent_spill"] is False

    # The flag surfaces in the rendered report.
    full_rows = [
        {"context_size": 512, "task_id": "t1", "ok": True, "score": 1.0,
         "decode_tps": 40.0, "wall_s": 10.0},
        {"context_size": 16384, "task_id": "t1", "ok": True, "score": 1.0,
         "decode_tps": 9.0, "wall_s": 44.0},
    ]
    rep = format_report(full_rows, "qwen3:8b")
    assert "silent_spill: true" in rep, rep
    print("selftest: all assertions passed")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Context-length scaling experiment for Metis.")
    ap.add_argument("--model", default="qwen3:8b",
                    help="Ollama model to test (default: qwen3:8b).")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--sizes", default=",".join(str(s) for s in DEFAULT_SIZES),
                    help="Comma-separated context window sizes.")
    ap.add_argument("--base-url", default="http://localhost:11434")
    ap.add_argument("--out", default=None,
                    help="Optional path to write results JSON.")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return

    sizes = tuple(int(x) for x in args.sizes.split(",") if x.strip())
    print(f"Running context-length scaling: model={args.model}, "
          f"repeats={args.repeats}, sizes={sizes}")
    print("(Never passing --force; if preflight fails, run will not start.)")

    ok, pf = preflight_ok()
    if not ok:
        print(f"Preflight: background CPU load is {pf.get('cpu_pct'):.0f}% "
              f"(limit {PREFLIGHT_CPU_LIMIT:.0f}%). Skipping the real run rather "
              f"than forcing it; close other work and re-run. No --force here.")
        return
    print(f"Preflight: {pf}")
    print()

    notes = [f"model: {args.model} | repeats: {args.repeats} | "
             f"num_predict: 2048 | temperature: 0 | seed: 1234",
             f"preflight: {pf}"]
    results = run_experiment(args.model, sizes, args.repeats, args.base_url)
    report = format_report(results, args.model, header_notes=notes)
    print(report)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = pathlib.Path(f"results/context_scale_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(r) for r in results), encoding="utf-8")
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    print(f"\nResults written to {out_dir}/")
    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
