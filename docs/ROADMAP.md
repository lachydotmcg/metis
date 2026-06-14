# Roadmap

Build order follows the principle: methodology first, GUI last. Status as of
2026-06-14.

## Done (v0.1.0)

- [x] **Task suite v1.0** - 21 original tasks, 5 categories, frozen,
  self-validating; coding reference solutions must pass their own tests.
- [x] **Programmatic scoring** - numeric/choice extraction, IFEval-style
  constraints, sandboxed code execution (`python -I`, timeout), agentic
  final-answer matching.
- [x] **Measurement engine** - hardware fingerprinting, NVML/nvidia-smi monitor
  for VRAM, power, temp, energy; streamed Ollama backend; rotating-block
  scheduler; preflight quiesce check; JSONL records with versioned schema.
- [x] **Agentic harness** - deterministic lookup/calc tool loop, fictional
  corpus, injected-failure recovery task.
- [x] **Stats + reports** - mean with 95% CI, coverage-at-threshold, markdown and
  HTML reports.
- [x] **Economics module** - config-driven rates with deliberately no defaults,
  plus measured energy cost.
- [x] **Oracle mock backend** - full-pipeline self-test; oracle should score 1.00
  across the board.
- [x] **Live verification** - qwen3:1.7b smoke run on RTX 3060 8GB: 107 tok/s
  decode, TTFT 0.28s, peak VRAM 3717MB, and a genuine small-model agentic
  failure caught and scored.

## Done (v0.1.1)

- [x] **Judge tier implementation** - `metis judge` reads stored records and
  tier-1 scores, requires a pinned judge model, performs rubric-based pairwise
  position-swap judging, writes `judge_scores.jsonl`, and reports merge judge
  scores only for `needs_judge` rows.
- [x] **Cloud API backend** - `--backend cloud` supports OpenAI-compatible chat
  completions and Anthropic messages through the shared backend interface, with
  provider/base URL/API-version knobs recorded in artifacts.
- [x] **Full first study** - run `results/20260612_173212`: qwen3:1.7b,
  qwen3:8b, and deepseek-r1:7b, N=5, no `--force`, 315 generations, 0 errors,
  report and economics generated.
- [x] **Cloud baseline collection** - run `results/20260612_201339`:
  Claude Sonnet 4.6, N=5, 105 generations, 0 errors; judge scores merged for
  summarisation rows.
- [x] **Readable comparison artifact** -
  `results/comparison_20260612_173212_vs_20260612_201339` contains anchored
  local-vs-Claude metrics, a coverage curve, quality-vs-speed chart, and a
  findings draft.
- [x] **Step-depth signature experiment** - suite v2.0 adds a four-task agentic
  ladder; local run `results/step_depth_local/20260612_203254` and cloud run
  `results/step_depth_cloud/20260612_210103` show qwen3:1.7b/deepseek-r1:7b
  breaking at depth 2 while qwen3:8b and Claude hold through depth 5.
- [x] **Coverage curve rendering** - full curve over thresholds, with charting in
  generated reports.
- [x] **Paper draft** - `docs/PAPER.md` drafted from the skeleton in
  `docs/RESEARCH.md`.
- [x] **Context-length scaling mode** - same tasks padded to 512/2k/8k/16k
  context. `context_scale.py`; qwen3:8b shows a decode cliff from about
  40 tok/s to 9.8 tok/s at 16k from KV-cache spill.

## Next (priority order)

1. [x] **Frontier headroom / saturation handling** - ceiling-effect language
   (DONE: FINDINGS/PAPER/README) and a derived saturation metric (DONE:
   `metis/saturation.py` + `metis saturation`; Claude run flagged
   `reference_saturated: true`). Frozen frontier-headroom suite DONE:
   `metis/suite/v3/` (18 tasks, 5 categories, all programmatic, self-validating
   via `tests/test_v3_suite.py`); see `docs/FRONTIER_HEADROOM.md`. REMAINING: the
   reference-smoke validation run (`docs/FUTURE_EVALUATIONS.md` E1, credit-gated).
2. [ ] **Judge validation set** - collect the roughly 50 human-labeled items and
   report judge-human agreement before paper use. Scaffolding landed:
   `validation/extract_labels.py`, `validation/agreement.py`, and tests; waiting
   on human labels.
3. [x] **llama.cpp server backend** - `metis/backends/llamacpp.py`
   (`--backend llamacpp`); OpenAI-compatible, records `n_gpu_layers` and parses
   llama.cpp `timings`. Mock-tested in `tests/test_judge.py`.
4. [x] **Offload-cliff sweep mode** - `offload_sweep.py`: sweeps GPU-layer counts
   (Ollama `num_gpu` or pre-launched llama-servers), reports tok/s vs layers and
   the offload knee. Mock-tested (`--selftest`); real sweep GPU-gated.
5. [x] **WDDM silent-spill detection** - `context_scale.detect_silent_spill`
   flags a fits-but-crawls decode collapse (>=50% one-step drop, zero errors) and
   surfaces `silent_spill: true` in the report; the published 16k cliff now
   carries the flag. Eval-free, tested with synthetic samples.
6. [x] **Realistic-conditions mode** - `realistic_conditions.py`: safety-capped
   synthetic RAM pressure, clean-vs-loaded delta report. Mock-tested
   (`--selftest`); real run GPU-gated.
7. [ ] **Tauri viewer** - read-only over run artifacts. Deliberately last.

## Rules That Survive Any Roadmap Change

- Suite v1 and v2 never change; new tasks mean a new suite version.
- Scoring is always a separate, re-runnable pass over stored records.
- Nothing visual ever measures.
- No prices in code.
