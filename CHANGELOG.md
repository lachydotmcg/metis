# Changelog

## 2026-06-12

- Implemented tier-2 judge scoring via `metis judge`: pinned config validation, rubric-based pairwise position-swap judging, atomic `judge_scores.jsonl` output, and report merging that preserves tier-1 `scores.jsonl`.
- Added a cloud API backend for OpenAI-compatible chat completions and Anthropic messages, with resolved provider/base URL/API-version settings recorded in run artifacts.
- Added summarisation judge rubric config, judge/backend tests, schema patch bump to `0.1.1`, and docs/roadmap updates for the new scoring and cloud-reference paths.
- Ran the first full local study at `results/20260612_173212`: qwen3:1.7b, qwen3:8b, and deepseek-r1:7b with `--repeats 5`, no forced preflight, 315 generations, 0 errors, plus report and economics artifacts.
- Added project-root `.env` support for cloud API keys, with `.env` ignored and `.env.example` as the safe template.
- Ran the Claude Sonnet 4.6 cloud baseline at `results/20260612_201339`, applied judge scoring to local/cloud summarisation rows, and generated anchored comparison charts at `results/comparison_20260612_173212_vs_20260612_201339`.
- Added suite v2.0 with a four-task agentic step-depth ladder, ran it locally and against Claude Sonnet 4.6, and generated `results/step_depth_comparison_20260612_203254_vs_20260612_210103`.
- Added `memory_retrieval.py`, a stdlib-only wikilink graph retriever for atomic markdown memory notes, plus a read-only depth probe script and plain-assert tests.
