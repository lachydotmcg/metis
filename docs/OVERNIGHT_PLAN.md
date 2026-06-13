# Overnight Agent Plan

This is the authoritative work plan for an autonomous agent working on Metis
overnight. Work the tasks in order. Each task is self-contained, CPU/data/docs
only (no human input, no uninstalled tools) unless explicitly marked OPTIONAL.

## Hard rules (never break these)

1. **Frozen suites.** `metis/suite/v1/` and `metis/suite/v2/` are immutable. New
   tasks mean a new suite version directory, never an edit to an existing one.
2. **Scoring is a separate, re-runnable pass.** Never fold scoring into
   collection. Never re-run inference to re-score.
3. **No prices in code.** Rates live in `config/pricing.yaml` and default to
   unconfigured. Never hardcode a price anywhere.
4. **Nothing visual ever measures.** Report/render code reads artifacts only.
5. **Never commit secrets.** `.env` stays git-ignored. Never print or commit a
   key. Confirm `git diff --cached --name-only` excludes `.env` before every
   commit.
6. **Tests gate every commit.** Run all of `python tests/test_scoring.py`,
   `python tests/test_judge.py`, `python tests/test_memory_retrieval.py`, and
   `python router.py --selftest` before AND after each task. If anything fails,
   do not commit — fix it or revert and write the blocker into PROGRESS.md.
7. **Small, frequent commits.** One commit per completed task, clear message,
   then push. Keep every change reversible.
8. **Stay in this repo.** Do not touch anything outside the Metis directory
   (especially not ai-command-center). Do not delete existing `results/`.
9. **When blocked, log and move on.** Append a dated note to PROGRESS.md
   describing the blocker and skip to the next task rather than improvising
   outside this plan.

## Tasks (in priority order)

### 1. Router evaluation artifact (highest value — the deliverable)
Run the Phase 1 router evaluation against the existing run pair and persist it:
`python router.py eval --local-run results/20260612_173212 --local-model qwen3:8b
--cloud-run results/20260612_214955 --cloud-model deepseek-v4-pro --threshold 0.9`
- Save the markdown output to `results/router_eval_qwen3_8b_vs_deepseek_v4_pro.md`.
- Sweep `--threshold` 0.85 / 0.9 / 0.95 and `--min-confidence` at two values;
  capture each. Add a short section to `docs/FINDINGS.md` summarising classifier
  accuracy, backend-flip rate, and the realized cost/quality vs the oracle
  (perfect-classifier) upper bound and all-cloud. State the honest result
  whatever it is.

### 2. Full coverage-curve rendering
`COVERAGE_THRESHOLDS` already exists; the data is collected. Render the full
coverage(t) curve over a fine threshold grid (e.g. 0.0..1.0 step 0.05) into the
HTML report (`metis/report.py`) as an inline SVG, plus a markdown table. No new
measurement — read existing scores only. Add a test that the curve is monotone
non-increasing in t.

### 3. Paper draft
Create `docs/PAPER.md` — a real draft (not a skeleton) following the paper
skeleton in `RESEARCH.md`: intro/gap, research question, methodology (cite
METHODOLOGY.md), results (pull real numbers from FINDINGS.md, the comparison
artifact, step-depth, and the router eval from task 1), threats to validity, and
an artifact/reproducibility section. Honest, scannable, no hype. Mark any number
you could not source with `[TODO: verify]` rather than inventing it.

### 4. Judge validation scaffolding (teed up for Lachy, no fake labels)
Do NOT fabricate human labels. Instead: create `validation/` with a script that
(a) extracts the summarisation generations needing judgement into a
`validation/to_label.jsonl` template with empty `human_score` fields for Lachy to
fill, and (b) `validation/agreement.py` that, once `human_labels.jsonl` exists,
computes judge–human agreement (correlation + mean abs error) and writes a
report. Add plain-assert tests using a tiny synthetic labeled set. Update
`docs/METHODOLOGY.md` §4 to point at this flow.

### 5. Publishable results subset + repo polish
The repo currently git-ignores all of `results/`, so GitHub shows code but no
evidence. Create `results/published/` containing a CURATED subset that tells the
story: the comparison report(s), `report.md`/`report.html`, the routing sim and
router eval markdown, and `scores.jsonl` for the headline runs — but NOT raw
model outputs or anything containing prompts that may be large. Adjust
`.gitignore` to track `results/published/` while still ignoring everything else
under `results/`. Update `README.md` with a short "Results" section linking the
published artifacts and a one-paragraph headline finding. Keep the README
quickstart accurate to the current CLI.

### OPTIONAL 6. Context-length scaling mode (only if Ollama is reachable)
First check `curl http://localhost:11434/api/tags` succeeds. If and only if it
does, implement a context-length scaling mode (suite tasks padded to
512/2k/8k/16k context) per `RESEARCH.md` §signature experiments, and run it for
qwen3:8b only, N=3, writing to `results/`. If Ollama is not reachable, SKIP and
note it in PROGRESS.md — do not block on it. Never pass `--force` to a real run;
if preflight fails, skip the run and just land the code + a mock-backend test.

## End-of-run deliverable

Append a dated summary to `PROGRESS.md`: tasks completed, tasks skipped and why,
test status, commits made, and a short "what Lachy should look at first" note.
Update `CHANGELOG.md` and tick the corresponding boxes in `ROADMAP.md`.
