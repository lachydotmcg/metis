# Changelog

## 2026-06-15 (overnight — OVERNIGHT_PLAN v2 tasks 1–6)

- **Frontier-headroom suite v3** (`metis/suite/v3/`, frozen): 18 harder,
  contamination-safe tasks across 5 categories (coding with hidden edge tests,
  deeper agentic with branching/recovery, long-context distant-fact, adversarial
  summarisation with conflicting claims, interacting instruction constraints).
  All programmatically scored (no judge dependency), selectable via `--suite v3`.
  `tests/test_v3_suite.py` scores every reference answer with the real scorers
  (1.0 required); design doc `docs/FRONTIER_HEADROOM.md`.
- **Automatic WDDM silent-spill detection** — `context_scale.detect_silent_spill`
  flags a fits-but-crawls decode collapse (≥50% one-step drop with zero errors)
  and the report now carries `silent_spill: true|false`. Eval-free; the published
  qwen3:8b 16k cliff was regenerated to carry the flag. Synthetic-sample tests.
- **Router OOD robustness** — `python router.py ood` classifies 22 hand-written
  out-of-distribution prompts (no model calls): accuracy 100% → 40.9%, fail-safe
  catches 12/13 misclassifications, 22.7% silent-misroute exposure. Replaced the
  prose "best-case caveat" in FINDINGS with the measured table; published
  `results/published/router_ood/report.md`.
- **llama.cpp server backend** (`metis/backends/llamacpp.py`, `--backend
  llamacpp`) — OpenAI-compatible, records `n_gpu_layers`, parses llama.cpp
  `timings`. Five mock tests (request/parse path) in `tests/test_judge.py`.
- **Offload-cliff sweep** (`offload_sweep.py`) — tok/s vs GPU layers via Ollama
  `num_gpu` or pre-launched llama-servers, with offload-knee detection. Mock-
  tested (`--selftest`).
- **Realistic-conditions mode** (`realistic_conditions.py`) — safety-capped
  synthetic RAM pressure, clean-vs-loaded delta report. Mock-tested (`--selftest`).
- No frontier or local models were run (Ollama unreachable; real GPU/credit runs
  remain gated). Full mandated test gate green throughout.

## 2026-06-14 (hardening pass)

- **Published to GitHub** at `github.com/lachydotmcg/metis`.
- **Saturation metric** (`metis/saturation.py`, `metis saturation` CLI command):
  derives reference-model ceiling metrics — mean score, fraction of tasks at the
  ceiling, categories saturated, headroom, and a `reference_saturated` flag —
  from already-scored artifacts (no model calls). Turns the ceiling-effect caveat
  into a reproducible number; on the Claude run it reports mean 0.976, 86% of
  tasks at the ceiling, `reference_saturated: true`. Hermetic tests added.
- **Bug fixes from a full code audit:**
  - Judge JSON extraction was a greedy `\{.*\}` that grabbed prose braces and
    could crash the entire judge pass; replaced with brace-balanced extraction
    that picks the final verdict object, and wrapped per-row judging in a
    try/except that falls back to the tier-1 score instead of aborting the run.
  - Numeric answer parsing treated any comma as a thousands separator, so "1,2"
    parsed to 12.0 and could silently mis-score; commas now count only in groups
    of three.
  - `compare.py` headline indexed models by list position (`rows[0]`/`rows[1]`),
    which mislabels or crashes for any model set other than the original two; now
    picks strongest/fastest by computed metric.
  - Cloud OpenAI backend now retries once without sampling params when a model
    rejects `temperature`/`seed` with a 400, instead of failing the generation.
  - Ollama `version()` retries once before aborting a run on a transient blip.
  - Fixed the `schema.py` agentic-fields docstring to match what `run_agentic`
    actually writes.
- Added `docs/FUTURE_EVALUATIONS.md`: a prioritised, budget-aware plan for which
  runs to do next and which questions are already answered from stored data.

## 2026-06-14

- Tightened the local-vs-Claude result language across README, FINDINGS, PAPER,
  and published artifacts so the 87% qwen3:8b result is framed as Metis v1
  suite coverage, not a general intelligence ratio. Added explicit ceiling/headroom
  caveats for Claude Sonnet 4.6 saturation.
- Added `docs/NEXT_AGENT_PLAN.md`, the current next-agent plan focused on the
  ceiling-effect/frontier-headroom problem and the possible subscription-backed
  Claude testing window.
- Updated `HANDOFF.md` so future agents do not follow the completed judge/cloud
  baseline tasks, and moved frontier headroom into the roadmap's next priority.
- Added `context_scale.py`, a self-contained context-length scaling experiment
  from `docs/RESEARCH.md` section 6: pads v1 reasoning tasks to
  512/2k/8k/16k context and measures decode speed plus answer quality on
  qwen3:8b. Includes a preflight quiesce check (CPU limit 40%, never `--force`)
  and a mock-backend selftest.
- Fixed the experiment's prior-attempt defects: a real-path `NameError`, a
  malformed report table, and a brittle answer scorer. It now strips `<think>`
  and parses markdown `**Answer:**` and LaTeX `\boxed{}` finals, with regression
  tests.
- Ran qwen3:8b N=3: decode collapses from about 40 tok/s at or below 8k to
  9.8 tok/s at 16k with zero errors, the Windows WDDM silent-spill / KV-cache
  cliff. Published the report and metrics under
  `results/published/context_scale_qwen3_8b/`, added a `docs/FINDINGS.md`
  section, and linked it from the README.
- Ignored the regenerable validation templates (`validation/to_label.jsonl`,
  `validation/human_labels.jsonl`) in `.gitignore`.

## 2026-06-12

- Implemented tier-2 judge scoring via `metis judge`: pinned config validation,
  rubric-based pairwise position-swap judging, atomic `judge_scores.jsonl`
  output, and report merging that preserves tier-1 `scores.jsonl`.
- Added a cloud API backend for OpenAI-compatible chat completions and Anthropic
  messages, with resolved provider/base URL/API-version settings recorded in run
  artifacts.
- Added summarisation judge rubric config, judge/backend tests, schema patch bump
  to `0.1.1`, and docs/roadmap updates for the new scoring and cloud-reference
  paths.
- Ran the first full local study at `results/20260612_173212`: qwen3:1.7b,
  qwen3:8b, and deepseek-r1:7b with `--repeats 5`, no forced preflight,
  315 generations, 0 errors, plus report and economics artifacts.
- Added project-root `.env` support for cloud API keys, with `.env` ignored and
  `.env.example` as the safe template.
- Ran the Claude Sonnet 4.6 cloud baseline at `results/20260612_201339`, applied
  judge scoring to local/cloud summarisation rows, and generated anchored
  comparison charts at `results/comparison_20260612_173212_vs_20260612_201339`.
- Added suite v2.0 with a four-task agentic step-depth ladder, ran it locally and
  against Claude Sonnet 4.6, and generated
  `results/step_depth_comparison_20260612_203254_vs_20260612_210103`.
- Added `memory_retrieval.py`, a stdlib-only wikilink graph retriever for atomic
  markdown memory notes, plus a read-only depth probe script and plain-assert
  tests.
