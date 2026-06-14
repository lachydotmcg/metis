# Progress Log

## 2026-06-15 (overnight, ~03:0x AEST) — integrity re-verification (no new work)

Re-invoked overnight with all six OVERNIGHT_PLAN v2 tasks already complete and
pushed (`48e955b`). The committed plan has no remaining numbered tasks, and my
authority is bounded strictly by it, so I did **not** improvise work outside the
plan. This run re-verified integrity only:

- Git: working tree clean; local HEAD `48e955b` == `origin/main`.
- Full mandated gate green: `test_scoring` (12), `test_judge` (14),
  `test_memory_retrieval` (4), `test_judge_agreement` (9), `test_saturation` (6),
  `router --selftest`, `context_scale --selftest`.
- New-mode tests also green: `test_v3_suite` (6), `offload_sweep --selftest`,
  `realistic_conditions --selftest`.
- Ollama unreachable (`/api/tags`, exit 7), so the GPU-gated runs (v3 reference
  smoke, offload sweep, realistic conditions) remain correctly deferred.

What Lachy should look at first: nothing changed since the v2 wrap-up — the three
GPU-gated modes are still code-complete and waiting on an idle/approved GPU, and
suite v3 is ready for a reference smoke. See the v2 entry below for detail.

## 2026-06-15 (overnight, 02:0x–02:33 AEST) — OVERNIGHT_PLAN v2 tasks 1–6 complete

Worked the refreshed v2 plan (the earlier PROGRESS notes about "tasks 1–6
complete" referred to the *old* plan; the v2 plan committed in `6a932ce` had six
fresh tasks, none done). All six landed, one small commit each, pushed and
remote-verified. No frontier or local models were run — Ollama was unreachable
all session, and v3 design + every new mode is validated against mock/synthetic
data with zero inference. `.env` confirmed unstaged before every commit.

What shipped:
1. **Suite v3 (frontier headroom)** — `9611d5f`. Frozen `metis/suite/v3/`, 18
   programmatic, contamination-safe tasks (coding w/ hidden edge tests; deeper
   agentic w/ branching + injected-failure recovery; long-context distant-fact;
   adversarial summarisation w/ conflicting claims; interacting instruction
   constraints). `tests/test_v3_suite.py` scores every oracle to 1.0. Pipeline
   smoke on the mock backend: 18 collected, 18 scored, 0 errors, 0 pending judge.
   Design doc `docs/FRONTIER_HEADROOM.md`.
2. **WDDM silent-spill auto-detection** — `5abb667`. `detect_silent_spill` in
   context_scale.py flags a fits-but-crawls collapse (≥50% one-step decode drop,
   zero errors) and the report emits `silent_spill: true|false`. Regenerated the
   published 16k-cliff report from its stored JSONL (no inference) so the real
   finding carries the flag. Synthetic-sample tests in the selftest gate.
3. **Router OOD robustness (E5)** — `482be2e`. `python router.py ood` on 22
   hand-written OOD prompts: accuracy 100% → **40.9%**, fail-safe catches 12/13
   misclassifications, **22.7% silent-misroute** exposure. Replaced the prose
   best-case caveat in FINDINGS with the measured table; published
   `results/published/router_ood/report.md`.
4. **llama.cpp backend** — `c908add`. `metis/backends/llamacpp.py`
   (`--backend llamacpp`), OpenAI-compatible, records `n_gpu_layers`, parses
   llama.cpp `timings`. Five mock tests (request/parse path) in test_judge.py.
5. **Offload-cliff sweep** — `1160d19`. `offload_sweep.py`, tok/s vs GPU layers
   (Ollama num_gpu / pre-launched llama-servers) + offload-knee detection.
   Mock-tested via `--selftest`.
6. **Realistic-conditions mode (OPTIONAL)** — `a89d316`. `realistic_conditions.py`,
   safety-capped synthetic RAM pressure + clean-vs-loaded delta report.
   Mock-tested via `--selftest`.

### Test status
Full mandated gate green before and after every task (`test_scoring`,
`test_judge`, `test_memory_retrieval`, `test_judge_agreement`, `test_saturation`,
`router --selftest`, `context_scale --selftest`), plus the new
`tests/test_v3_suite.py`, `offload_sweep --selftest`, and
`realistic_conditions --selftest`. No commit on a failing test.

### Skipped / deferred (and why)
- No real model runs: Ollama unreachable (`/api/tags` empty) and the plan gates
  real GPU/credit runs. The v3 reference-smoke (E1), the offload sweep, and the
  realistic-conditions run are all teed up to run when a GPU is idle/approved.
- Judge human-labelling (separate roadmap item) still correctly blocked on Lachy.

### What Lachy should look at first
1. **Suite v3** — `docs/FRONTIER_HEADROOM.md` and `metis/suite/v3/`. This is the
   headroom fix: a frozen, harder suite ready for a reference smoke (E1) to prove
   it no longer saturates. Run with `metis run --suite v3 --backend mock` to see
   the pipeline, or gate a real reference run on credit approval.
2. **Router OOD number** — FINDINGS "Out-of-distribution robustness": accuracy
   falls to 40.9% on realistic phrasing; the fail-safe is load-bearing and the
   real exposure is the 22.7% silent-misroute rate.
3. The three new GPU-gated modes (silent-spill flag, offload sweep, realistic
   conditions) are code-complete and mock-tested — they just need an idle GPU.

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
