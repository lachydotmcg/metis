# Roadmap

Build order follows the principle: methodology first, GUI last. Status as of 2026-06-12.

## Done (v0.1.0)

- [x] **Task suite v1.0** — 21 original tasks, 5 categories, frozen, self-validating (coding reference solutions must pass their own tests)
- [x] **Programmatic scoring** — numeric/choice extraction, IFEval-style constraints, sandboxed code execution (`python -I`, timeout), agentic final-answer matching
- [x] **Measurement engine** — hardware fingerprinting, NVML/nvidia-smi monitor (VRAM, power, temp, energy), streamed Ollama backend (wall-clock TTFT, runtime timings, thinking capture), rotating-block scheduler, preflight quiesce check, JSONL records with versioned schema
- [x] **Agentic harness** — deterministic lookup/calc tool loop, fictional corpus, injected-failure recovery task
- [x] **Stats + reports** — mean ± 95% CI (t-distribution), coverage-at-threshold, markdown + HTML
- [x] **Economics module** — config-driven rates (deliberately no defaults), measured energy cost
- [x] **Oracle mock backend** — full-pipeline self-test (scores 1.00 across the board, verified)
- [x] **Live verification** — qwen3:1.7b smoke run on RTX 3060 8GB: 107 tok/s decode, TTFT 0.28s, peak VRAM 3717MB, and a genuine small-model agentic failure caught and scored

## Done (v0.1.1)

- [x] **Judge tier implementation** — `metis judge` reads stored records and tier-1 scores, requires a pinned judge model, performs rubric-based pairwise position-swap judging, writes `judge_scores.jsonl`, and reports merge judge scores only for `needs_judge` rows.
- [x] **Cloud API backend** — `--backend cloud` supports OpenAI-compatible chat completions and Anthropic messages through the shared backend interface, with provider/base URL/API-version knobs recorded in artifacts.
- [x] **Full first study** — run `results/20260612_173212`: qwen3:1.7b, qwen3:8b, and deepseek-r1:7b, N=5, no `--force`, 315 generations, 0 errors, report + economics generated.
- [x] **Cloud baseline collection** — run `results/20260612_201339`: Claude Sonnet 4.6, N=5, 105 generations, 0 errors; judge scores merged for summarisation rows.
- [x] **Readable comparison artifact** — `results/comparison_20260612_173212_vs_20260612_201339` contains anchored local-vs-Claude metrics, a coverage curve, quality-vs-speed chart, and a findings draft.
- [x] **Step-depth signature experiment** — suite v2.0 adds a four-task agentic ladder; local run `results/step_depth_local/20260612_203254` and cloud run `results/step_depth_cloud/20260612_210103` show qwen3:1.7b/deepseek-r1:7b breaking at depth 2 while qwen3:8b and Claude hold through depth 5.

## Next (priority order)

1. [ ] **Judge validation set** — collect the ~50 human-labeled items and report judge-human agreement before paper use.
2. [ ] **llama.cpp server backend** — needed for controlled `n_gpu_layers` sweeps.
3. [ ] **Offload-cliff sweep mode** — automate runs across `num_gpu` values, plot tok/s vs layers.
4. [ ] **WDDM silent-spill detection** — shared-GPU-memory sampling + perf-cliff heuristic, flagged in reports (design in RESEARCH.md).
5. [ ] **Context-length scaling mode** — same tasks padded to 512/2k/8k/16k context.
6. [ ] **Realistic-conditions mode** — synthetic RAM pressure during runs.
7. [ ] **Coverage curve rendering** — full curve over thresholds (data already collected), charts in HTML report.
8. [ ] **Tauri viewer** — read-only over run artifacts. Deliberately last.
9. [ ] **Paper draft** — skeleton in RESEARCH.md.

## Rules that survive any roadmap change

- Suite v1 never changes; new tasks mean suite v2.
- Scoring is always a separate, re-runnable pass over stored records.
- Nothing visual ever measures.
- No prices in code.
