"""Run orchestration: preflight, scheduling, capture, JSONL writing.

Schedule is "rotating block" (see METHODOLOGY §2): within each repeat round,
each model runs all tasks as a block; model order rotates between rounds so no
model always runs on the hottest GPU. Full per-generation interleaving would
thrash model loads on a single consumer GPU.
"""

import datetime as dt
import json
import pathlib
import time

import psutil

from . import fingerprint
from .agentic import run_agentic
from .backends import get_backend
from .monitor import Monitor
from .schema import SCHEMA_VERSION
from .suite.loader import load_suite

PREFLIGHT_CPU_LIMIT = 40.0


def _preflight(force: bool) -> dict:
    cpu = psutil.cpu_percent(interval=1.0)
    vm = psutil.virtual_memory()
    info = {"cpu_pct": cpu, "ram_available_gb": round(vm.available / 2**30, 1),
            "forced": False}
    if cpu > PREFLIGHT_CPU_LIMIT:
        if not force:
            raise SystemExit(
                f"Preflight: background CPU load is {cpu:.0f}% "
                f"(limit {PREFLIGHT_CPU_LIMIT:.0f}%). Close other work or "
                f"re-run with --force (which gets recorded).")
        info["forced"] = True
    return info


def run(models: list[str], backend_name: str = "ollama", repeats: int = 3,
        suite_dir: str = "v1", include: list[str] | None = None,
        options: dict | None = None, out_root: str = "results",
        force: bool = False, backend_kwargs: dict | None = None) -> pathlib.Path:
    options = dict(options or {})
    backend = get_backend(backend_name, **(backend_kwargs or {}))
    backend_version = backend.version()
    backend_settings = backend.settings()
    suite = load_suite(suite_dir, include)
    if not suite["tasks"]:
        raise SystemExit("no tasks matched the include filter")

    preflight = _preflight(force) if backend_name != "mock" else {"skipped": True}

    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = pathlib.Path(out_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    fp = fingerprint.collect()
    model_infos = {m: backend.model_info(m) for m in models}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "suite_dir": suite_dir,
        "suite_version": suite["version"],
        "models": models,
        "model_infos": model_infos,
        "backend": {"name": backend_name, "version": backend_version,
                    "settings": backend_settings},
        "options": options,
        "repeats": repeats,
        "include": include,
        "schedule": "rotating-block",
        "preflight": preflight,
        "started_at": dt.datetime.now().astimezone().isoformat(),
    }
    (run_dir / "fingerprint.json").write_text(
        json.dumps(fp, indent=2), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    total = repeats * len(models) * len(suite["tasks"])
    done = errors = 0
    records_path = run_dir / "records.jsonl"

    with open(records_path, "w", encoding="utf-8") as f:
        for r in range(repeats):
            shift = r % len(models)
            order = models[shift:] + models[:shift]
            for m in order:
                if backend_name != "mock":
                    print(f"-- loading {m} ...", flush=True)
                    backend.preload(m, options.get("keep_alive", "15m"))
                for task in suite["tasks"]:
                    opts = dict(options)
                    opts["num_predict"] = task.get(
                        "max_tokens", options.get("num_predict", 1024))
                    mon = Monitor().start()
                    if task["scoring"]["type"] == "agentic_final":
                        res, agentic = run_agentic(backend, m, task, opts)
                    else:
                        res = backend.generate(
                            m, task.get("system"), task["prompt"], opts,
                            meta=task)
                        agentic = None
                    msum = mon.stop()
                    decode_tps = res.output_tokens / res.eval_s if res.eval_s > 0 else 0.0
                    prefill_tps = res.prompt_tokens / res.prompt_eval_s if res.prompt_eval_s > 0 else 0.0
                    rec = {
                        "schema_version": SCHEMA_VERSION,
                        "run_id": run_id,
                        "ts": dt.datetime.now().astimezone().isoformat(),
                        "suite_version": suite["version"],
                        "task_id": task["id"],
                        "category": task["category"],
                        "repeat": r,
                        "model": model_infos[m],
                        "backend": {"name": backend_name,
                                    "version": backend_version,
                                    "settings": backend_settings,
                                    "options": opts},
                        "timings": {
                            "wall_s": round(res.wall_s, 3),
                            "ttft_s": round(res.ttft_s, 3),
                            "load_s": round(res.load_s, 3),
                            "prompt_tokens": res.prompt_tokens,
                            "prompt_eval_s": round(res.prompt_eval_s, 3),
                            "output_tokens": res.output_tokens,
                            "eval_s": round(res.eval_s, 3),
                            "decode_tps": round(decode_tps, 2),
                            "prefill_tps": round(prefill_tps, 2),
                        },
                        "monitor": msum,
                        "output": {"content": res.content,
                                   "thinking": res.thinking},
                        "agentic": agentic,
                        "error": res.error,
                    }
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    done += 1
                    errors += bool(res.error)
                    status = (f"ERROR {res.error}" if res.error else
                              f"{decode_tps:.1f} tok/s, ttft {res.ttft_s:.2f}s, "
                              f"{res.output_tokens} tok")
                    print(f"[{done}/{total}] r{r+1} {m} {task['id']}: {status}",
                          flush=True)

    manifest["finished_at"] = dt.datetime.now().astimezone().isoformat()
    manifest["generations"] = done
    manifest["generation_errors"] = errors
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nrun complete: {run_dir} ({done} generations, {errors} errors)")
    return run_dir
