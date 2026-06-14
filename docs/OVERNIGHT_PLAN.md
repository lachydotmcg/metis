# Overnight Agent Plan (v2 — 2026-06-14)

Authoritative work plan for the next autonomous overnight agent. The previous
overnight plan's tasks are all done (router eval, coverage curve, paper draft,
context-scaling, judge scaffolding, saturation metric). This supersedes it.
Read `docs/NEXT_AGENT_PLAN.md` and `docs/FUTURE_EVALUATIONS.md` alongside this —
they explain *why* these tasks matter.

## WORKING-HOURS CONSTRAINT (read first)

**Only do work while the local time is between 23:00 and 09:00 AEST.** The machine
is in use during the day and must stay free.

- Check the time at startup and again before starting each task:
  `powershell -Command "[System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow,'AUS Eastern Standard Time').ToString('HH:mm')"`
- If the AEST hour is >= 09 and < 23, **do not start new work**: commit anything
  in progress, append a PROGRESS.md note ("paused at <time> AEST — outside the
  23:00–09:00 window"), and STOP. Do not resume until the next overnight window.
- Aim to wrap up, commit, and stop by **08:45 AEST** so you finish cleanly before
  the cutoff rather than mid-task.

## Hard rules (never break these)

1. **Frozen suites.** `metis/suite/v1/` and `metis/suite/v2/` are immutable. New
   or harder tasks go in `metis/suite/v3/`, never as edits to v1/v2.
2. **No Anthropic API credits, and no cloud model calls, without explicit
   approval.** Build and test against local Ollama and the mock backend only.
   Designing v3 needs zero model calls.
3. **Scoring stays a separate, re-runnable pass.** No prices in code (use
   `config/pricing.yaml`). Engine stays headless. Errors are recorded and scored
   0, never dropped.
4. **Never commit secrets.** `.env` stays ignored; confirm `git diff --cached
   --name-only` excludes it before every commit.
5. **Tests gate every commit.** Before AND after each task run the full gate:
   `python tests/test_scoring.py`, `test_judge.py`, `test_memory_retrieval.py`,
   `test_judge_agreement.py`, `test_saturation.py`, `python router.py --selftest`,
   `python context_scale.py --selftest`. Never commit on a failing test.
6. **Small, frequent commits, then push.** One commit per completed task; verify
   `git ls-remote origin main` matches local HEAD after pushing (the push prints a
   benign credential-cacher warning but succeeds).
7. **Real GPU runs are overnight-and-idle only.** Check
   `curl http://localhost:11434/api/tags` first; never pass `--force` to a run; if
   the preflight quiesce check trips, skip the run and land code + a mock test.
8. **Stay in this repo.** Do not touch anything outside it.

## Tasks (priority order)

### 1. Design and build suite v3 — frontier headroom (highest value, zero credits)
The core research issue: Claude Sonnet 4.6 saturates v1 (`metis saturation` flags
`reference_saturated: true`), so the suite can't distinguish strong models. Build
`metis/suite/v3/` with **12–20 harder tasks**, programmatic scoring wherever
possible, original and contamination-safe (fictional entities):
- harder coding with hidden/edge-case tests (not just the happy path),
- agentic tasks deeper than depth 5, with branching and failure-recovery,
- long-context tasks where the answer depends on distant facts, not filler,
- adversarial summarisation with conflicting source claims,
- instruction-following with interacting/conflicting constraints.
Add a `test_v3_*` loader+self-validation test (mirror `test_v2_agentic_ladder_loads`
and the coding self-validation). **Do not run frontier models.** A single local
qwen3:8b smoke (N=1, overnight, Ollama-gated) is allowed only to confirm the suite
loads, scores, and is non-trivial for a local model. Success: a frozen v3 suite
that a near-frontier reference would *not* trivially max (validated later, with
approval).

### 2. WDDM silent-spill auto-detection in reports
The 16k context cliff is observed but only described. Make it automatic: sample
shared-GPU-memory via NVML in `metis/monitor.py` (or a decode-tok/s perf-cliff
heuristic vs context length), and surface a `silent_spill: true` flag + a note in
the report when a run "fits but crawls". Eval-free (uses existing data + a monitor
change). Add tests for the detection logic with synthetic samples.

### 3. Router robustness on out-of-distribution prompts (FUTURE_EVALUATIONS E5)
Hand-write ~20 OOD prompts with known categories (straddling categories, unusual
phrasing). Run `router.py classify` on them (no model inference) and report
classification accuracy + fail-safe rate. Replace the "best-case" caveat in
`docs/FINDINGS.md` with this real degradation number. Near-zero cost.

### 4. llama.cpp server backend
Implement a `llamacpp` backend (OpenAI-compatible endpoint) for controlled
`n_gpu_layers`, mirroring the cloud/ollama backend interface and recording all
knobs. Mock-test the request/parse path. A real run is GPU-gated and optional.

### 5. Offload-cliff sweep mode (depends on 4 or Ollama num_gpu)
Automate runs across GPU-layer counts and plot tok/s vs layers. Land the code +
mock test even if no real run happens; a real sweep is overnight/GPU-gated.

### OPTIONAL 6. Realistic-conditions mode
Re-run the v1 suite for qwen3:8b under synthetic RAM pressure vs the clean
baseline. Code + mock test always; real run overnight/GPU-gated only.

## End-of-run deliverable

Append a dated PROGRESS.md entry: tasks completed, tasks skipped and why (including
any paused for the working-hours window), test status, commits, and a one-line
"what Lachy should look at first". Update CHANGELOG.md and tick ROADMAP boxes.
