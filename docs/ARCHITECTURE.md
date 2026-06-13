# Architecture

## Principles

1. **Headless engine, thin viewer.** The measurement engine is a Python package with a CLI. Any GUI (Tauri, planned last) is a viewer over JSON artifacts and never participates in measurement. Rationale: a desktop shell sitting in RAM pollutes the numbers on a 32GB machine where partially-offloaded models spill into system memory, and a CLI is what other people can run to contribute cross-machine data.
2. **Collection ≠ scoring.** Every raw model output is written to disk during the run. Scoring is a separate pass over stored records. Improving the judge or adding a metric means re-scoring, never re-running 40 hours of inference.
3. **Versioned schema.** Every artifact carries `schema_version`. Additive change = patch bump; rename/retype = minor; restructure = major. The future community dataset depends on this discipline starting now.
4. **Config over code.** API prices, electricity tariffs, judge settings live in `config/*.yaml`. Rates change; code shouldn't rot.
5. **Frozen suites.** `metis/suite/v1/` is suite version 1.0. Edits to prompts or scoring specs require a new suite directory (v2), MLPerf-round style, so results stay comparable.

## Data flow

```
                 ┌────────────┐
 suite/v1 ──────►│   runner    │◄────── fingerprint (CPU/RAM/GPU/driver)
 (frozen YAML)   │ (interleave,│◄────── monitor (VRAM/power/temp @500ms)
                 │  repeats)   │◄────── backend (Ollama HTTP, streamed)
                 └─────┬──────┘
                       ▼
        results/<run_id>/records.jsonl     ← raw outputs + timings + hw samples
                fingerprint.json
                manifest.json
                       │
                       ▼  (separate pass, re-runnable)
        scoring/ ──► scores.jsonl          ← programmatic tier-1
                 └─► judge_scores.jsonl    ← optional tier-2 judge pass
                       │
                       ▼
        report.md / report.html / economics.md
```

## Module map

| Module | Responsibility |
|---|---|
| `metis/cli.py` | argparse entry: fingerprint, suite, run, score, judge, report, economics |
| `metis/schema.py` | `SCHEMA_VERSION`, record field documentation |
| `metis/fingerprint.py` | hardware identity + stable `fingerprint_id` hash |
| `metis/monitor.py` | background sampler: NVML → nvidia-smi → CPU/RAM-only fallback |
| `metis/runner.py` | scheduling, preflight, capture, JSONL writing |
| `metis/agentic.py` | deterministic tool-loop harness (lookup + calc, fictional corpus) |
| `metis/backends/` | `base.py` interface, `ollama.py` (streamed /api/chat), `cloud.py` (reference APIs), `mock.py` (oracle) |
| `metis/suite/` | loader + frozen v1 YAML task files |
| `metis/scoring/` | `programmatic.py` scorers, `score_run.py` pass, `judge.py` tier-2 judge pass |
| `metis/stats.py` | mean, sample stdev, 95% CI (t-distribution) |
| `metis/economics.py` | energy cost + API-equivalent cost from config/pricing.yaml |
| `metis/report.py` | markdown + self-contained HTML reports |

## Run directory contents

- `manifest.json` — run id, suite version, models with digests/quant levels, backend version, sampler options, schedule mode, timestamps
- `fingerprint.json` — hardware identity for this run
- `records.jsonl` — one line per generation: full output (including thinking tokens), timings, monitor summary, agentic transcript if applicable, error if any
- `scores.jsonl` — one line per generation: tier-1 score 0..1, per-check details, `needs_judge` flag
- `judge_scores.jsonl` — optional tier-2 rows for `needs_judge` generations only; reports prefer these without rewriting `scores.jsonl`
- `report.md`, `report.html`, `economics.md` — generated artifacts

## Backends

- **Ollama** (implemented): streamed `/api/chat` for wall-clock TTFT; timing fields (`load_duration`, `prompt_eval_*`, `eval_*`) from the final chunk; model identity from `/api/show` + `/api/tags` (digest, parameter size, quant level). Reasoning models (qwen3, deepseek-r1) return `thinking` separately; it is stored, counted in token totals, and stripped before scoring.
- **Cloud API** (implemented): OpenAI-compatible chat completions or Anthropic messages, streamed for TTFT, configured through CLI/env and recorded in manifest backend settings. Used for reference-model runs and the tier-2 judge.
- **llama.cpp server** (planned): finer control (`n_gpu_layers` for the offload-cliff experiment, batch, threads) via the OpenAI-compatible endpoint.
- **Mock/oracle** (implemented): returns each task's expected answer with fake timings. Validates the harness end to end; the oracle scoring below ~1.0 means the harness is broken, not the model.

## Viewer (later, deliberately)

Tauri, not Electron (smaller resident footprint if anyone runs it alongside benchmarks, though the rule remains: never measure with the viewer open). Reads run directories, renders coverage curves, frontier charts, run comparisons. No measurement logic, ever.

## Community dataset (designed-for, not built)

Opt-in upload of `manifest.json` + `fingerprint.json` + `scores.jsonl` (no raw outputs, which may contain user-modified prompts). Anonymised fingerprint. The versioned schema is what makes aggregation possible later.
