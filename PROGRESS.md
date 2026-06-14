# Progress Log

## 2026-06-14 (hardening pass) - audit fixes, saturation metric, future-eval plan

Quality pass, no new model runs. Published the repo to `github.com/lachydotmcg/metis`.

Ran a full read-only code audit (subagent) and fixed the real findings, prioritising
the two that could silently corrupt published numbers:
- Judge JSON extraction (greedy regex -> brace-balanced + per-row fallback so one bad
  judge response can't abort the pass).
- Numeric parsing comma bug ("1,2" -> 12.0) -> commas only group in threes.
- `compare.py` positional model indexing -> pick by metric.
- Cloud backend retry-without-sampling-params on 400; Ollama `version()` retry.
- `schema.py` agentic docstring corrected to the real keys.

Added a saturation metric (`metis/saturation.py` + `metis saturation`) that makes the
ceiling effect a reproducible number rather than a prose caveat (Claude run: mean
0.976, 86% tasks at ceiling, `reference_saturated: true`), wired into FINDINGS.

Added `docs/FUTURE_EVALUATIONS.md` so future runs are deliberate and budget-aware.

All 40 test groups + the router and context_scale selftests pass. What Lachy should
look at first: `docs/FUTURE_EVALUATIONS.md` (what to run next) and `metis saturation
results/20260612_201339` (the ceiling, measured).

## 2026-06-14 (framing correction) - saturation caveat applied

Updated the public-facing result language after Lachy flagged the core issue:
Claude Sonnet 4.6 is near the Metis v1 ceiling, so qwen3:8b's 87% anchored score
must not read as "only 13% below Claude's intelligence." Patched README,
`docs/FINDINGS.md`, `docs/PAPER.md`, `results/published/README.md`,
`results/published/comparison_local_vs_claude/findings.md`, and
`results/published/step_depth/step_depth_findings.md` to frame the result as
suite coverage and to call out frontier headroom separately. No measured numbers
changed.

## 2026-06-14 (handoff planning) - frontier headroom next

Created `docs/NEXT_AGENT_PLAN.md` as the current authoritative plan for the next
agent. The plan centers the newly identified ceiling-effect problem: Claude Sonnet
4.6 nearly saturates Metis v1, so qwen3:8b's score should be framed as practical
suite coverage rather than a general intelligence ratio. It also records the
constraint that Lachy may need to wait for Claude subscription usage to reset and
that no Anthropic API credits should be spent without explicit approval.

Updated `HANDOFF.md` so future agents do not follow the completed judge/cloud/full
study tasks, refreshed `docs/ROADMAP.md` with frontier headroom as the next
priority, and added a changelog entry. No experiments or tests were run; this was
a docs-only planning change. `git diff --check` passed with only line-ending
warnings.

## 2026-06-14 (overnight, 08:02 AEST) — verification run #6

Re-invoked overnight with OVERNIGHT_PLAN.md tasks 1–6 already complete and pushed
(`e0b6b4d`). Per Hard Rule 9 I did **not** improvise work outside the plan; this
run only re-verified integrity:

- Git: working tree clean; local HEAD `e0b6b4d` == `origin/main`.
- All four mandated gates green: `test_scoring` (11), `test_judge` (5),
  `test_memory_retrieval` (4), `router.py --selftest`. Bonus gates also green:
  `context_scale.py --selftest` and `test_judge_agreement.py` (9).
- Confirmed artifacts still tracked: `docs/PAPER.md`, `docs/FINDINGS.md`,
  `validation/{extract_labels,agreement}.py`, and all **14** files under
  `results/published/` (incl. router eval + routing sim markdown).

**Nothing left in the plan that an autonomous run can do.** The only open item is
task 4's human-labeling step, correctly blocked on Lachy (labels must not be
fabricated). No code changed this run; this note is the only edit.

## 2026-06-14 (overnight, 07:02 AEST) — verification run #5

Re-invoked overnight with OVERNIGHT_PLAN.md tasks 1–6 already complete and pushed
(`b39585d`). Per Hard Rule 9 I did **not** improvise work outside the plan; this
run only re-verified integrity:

- Git: working tree clean; local HEAD `b39585d` == `origin/main`.
- All four mandated gates green: `test_scoring` (11), `test_judge` (5),
  `test_memory_retrieval` (4), `router.py --selftest`. Bonus gates also green:
  `context_scale.py --selftest` and `test_judge_agreement.py` (9).
- Confirmed artifacts still tracked: `docs/PAPER.md`, `docs/FINDINGS.md`,
  `validation/{extract_labels,agreement}.py`, and all **14** files under
  `results/published/` (incl. router eval + routing sim markdown).

**Nothing left in the plan that an autonomous run can do.** The only open item is
task 4's human-labeling step, correctly blocked on Lachy (labels must not be
fabricated). No code changed this run; this note is the only edit.

## 2026-06-14 (overnight, 06:02 AEST) — verification run #4

Re-invoked overnight with OVERNIGHT_PLAN.md tasks 1–6 already complete and pushed
(`b33b745`). Per Hard Rule 9 I did **not** improvise work outside the plan; this
run only re-verified integrity:

- Git: working tree clean; local HEAD `b33b745` == `origin/main`.
- All four mandated gates green: `test_scoring` (11), `test_judge` (5),
  `test_memory_retrieval` (4), `router.py --selftest`. Bonus gates also green:
  `context_scale.py --selftest` and `test_judge_agreement.py` (9).
- Confirmed artifacts still tracked: `docs/PAPER.md`, `docs/FINDINGS.md`,
  `validation/{extract_labels,agreement}.py`, and all **14** files under
  `results/published/` (incl. router eval + routing sim markdown).

**Nothing left in the plan that an autonomous run can do.** The only open item is
task 4's human-labeling step, correctly blocked on Lachy (labels must not be
fabricated). No code changed this run; this note is the only edit.

## 2026-06-14 (overnight, 05:02 AEST) — verification run #3

Re-invoked overnight with OVERNIGHT_PLAN.md tasks 1–6 already complete and pushed
(`44fb4ce`). Per Hard Rule 9 I did **not** improvise work outside the plan; this
run only re-verified integrity:

- Git: working tree clean; local HEAD `44fb4ce` == `origin/main`.
- All four mandated gates green: `test_scoring` (11), `test_judge` (5),
  `test_memory_retrieval` (4), `router.py --selftest`. Bonus gates also green:
  `context_scale.py --selftest` and `test_judge_agreement.py` (9).
- Confirmed artifacts still tracked: `docs/PAPER.md`, `docs/FINDINGS.md`,
  `validation/{extract_labels,agreement}.py`, and all **14** files under
  `results/published/` (incl. router eval + routing sim markdown).

**Nothing left in the plan that an autonomous run can do.** The only open item is
task 4's human-labeling step, correctly blocked on Lachy (labels must not be
fabricated). No code changed this run; this note is the only edit.

## 2026-06-14 (overnight, 02:02 AEST) — verification run #2

Re-invoked overnight with OVERNIGHT_PLAN.md tasks 1–6 already complete and pushed
(`c11e796`). Per Hard Rule 9 I did **not** improvise work outside the plan; this
run only re-verified integrity:

- Git: working tree clean; local HEAD `c11e796` == `origin/main`.
- All four mandated gates green: `test_scoring` (11), `test_judge` (5),
  `test_memory_retrieval` (4), `router.py --selftest`. Bonus gates also green:
  `context_scale.py --selftest` and `test_judge_agreement.py` (9).
- Confirmed artifacts still tracked: `docs/PAPER.md`, `docs/FINDINGS.md`,
  `validation/{extract_labels,agreement}.py`, and all **14** files under
  `results/published/` (incl. the router eval and routing sim markdown).

**Nothing left in the plan that an autonomous run can do.** The only open item is
task 4's human-labeling step, correctly blocked on Lachy (labels must not be
fabricated). No code changed this run; this note is the only edit.

## 2026-06-14 (later) — overnight verification run

Re-invoked overnight with OVERNIGHT_PLAN.md tasks 1–6 already complete and pushed
(`33361a1`). Per Hard Rule 9 I did **not** improvise work outside the plan; this
run only verified integrity:

- Git: working tree clean; local HEAD `33361a1` == `origin/main`.
- All four mandated gates green: `test_scoring` (11), `test_judge` (5),
  `test_memory_retrieval` (4), `router.py --selftest`. Also re-ran the bonus
  gates: `context_scale.py --selftest` and `test_judge_agreement.py` (9) — both pass.
- Confirmed every claimed artifact is tracked: router eval, the coverage-curve
  monotone test (`tests/test_scoring.py:118`), PAPER.md, judge-validation
  scaffolding, the 14 `results/published/` files, and the context-scale report +
  FINDINGS §Context-Length Scaling.

**Nothing left in the plan that an autonomous run can do.** The only open item is
task 4's human-labeling step, which is correctly blocked on Lachy (labels must not
be fabricated). No code changed this run; this note is the only edit.

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
