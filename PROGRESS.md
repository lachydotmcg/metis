# Progress Log

## 2026-06-14 — overnight agent session (tasks 1–6 of OVERNIGHT_PLAN.md)

### State at start
- Tasks 1–5 were already committed and pushed by the previous overnight run
  (commits `acfed53`…`153b584`); local `main` matched `origin/main`.
- Two untracked leftovers from a partial task-6 attempt: `context_scale.py`
  (buggy, never committed) and a generated `validation/to_label.jsonl`.

### What this session did
- **Verified tasks 1–5** are intact and that all four test gates pass
  (`test_scoring`, `test_judge`, `test_memory_retrieval`, `router.py --selftest`).
- **Task 6 (context-length scaling) — completed, not skipped.** Ollama preflight
  (`curl /api/tags`) succeeded with `qwen3:8b` present, so the optional GPU task
  was gated in. Before running, fixed three real defects in the prior
  `context_scale.py`:
  1. real (non-mock) path called an undefined `_ollama_generate` → `NameError`;
     renamed to the actual `_ollama_chat`.
  2. `format_report` emitted a malformed double-header table.
  3. the answer scorer marked correct model answers as 0 — it didn't strip
     `<think>` and broke on markdown `**Answer:**` and LaTeX `\boxed{}` finals.
     Rewrote it to strip thinking and parse both forms; added regression tests.
  Also added a preflight quiesce check mirroring `metis.runner` (CPU limit 40%,
  **never** `--force`) and recorded model/sampler/preflight in the report.
  Ran `qwen3:8b`, N=3, sizes 512/2k/8k/16k (preflight CPU 12.4%, no force).
- **Result (the finding):** decode holds ~40 tok/s through 8k, then collapses to
  **9.8 tok/s at 16k with zero errors and quality still 1.00** — the Windows WDDM
  silent-spill / KV-cache cliff predicted in RESEARCH.md §3. Published the report
  + per-generation metrics, added a FINDINGS.md section, and linked it from README.
- **Repo hygiene:** `.gitignore` now ignores the regenerable
  `validation/to_label.jsonl` and `validation/human_labels.jsonl` (the committed
  `validation/extract_labels.py` recreates them).

### Tasks completed / skipped
- Completed this session: **task 6** (+ verification of 1–5, + wrap-up docs).
- Skipped: none. Task 6 was OPTIONAL and gated; the gate passed and it ran cleanly.

### Test status
All four gates green before **and** after task 6, and `context_scale.py --selftest`
passes. No commit was made on a failing test.

### Commits (this session)
- `053f23a` — task 6: context-length scaling mode + scorer fixes + published artifact.
- (this commit) — wrap-up: PROGRESS.md, CHANGELOG.md, ROADMAP.md ticks, .gitignore.

### Notes / left in place
- The stale `results/context_scale_20260613_202554/` dir (from the earlier aborted
  attempt, with the old buggy report) was **left untouched** per Hard Rule 8
  ("do not delete existing results/"). It is gitignored and does not affect the repo;
  the good run is `results/context_scale_20260614_004125/`.

### What Lachy should look at first
1. **The 16k context cliff** — `results/published/context_scale_qwen3_8b/report.md`
   and the new "Context-Length Scaling" section in `docs/FINDINGS.md`. This is a
   clean third signature finding alongside routing and step-depth.
2. **Judge validation is teed up and waiting on you** (task 4): run
   `python validation/extract_labels.py`, fill `human_score` in the generated
   `validation/to_label.jsonl`, save as `validation/human_labels.jsonl`, then
   `python validation/agreement.py`. Until those human labels exist, the
   judge–human agreement table in PAPER.md / METHODOLOGY.md §4 stays pending.
3. The 16k boundary is card- and quant-specific; the transferable claim is the
   *shape* (a cliff, not a slope), not the exact threshold.
