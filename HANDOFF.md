# Handoff prompt for the next agent

Paste everything below the line into a fresh GPT 5.5 (or any capable model) session, working in this directory.

---

You are continuing work on **Metis**, a research-grade benchmark for local LLMs at `C:\Users\nirke\OneDrive\Documents\Metis`. It measures quality × hardware × dollars in one reproducible run: the gap none of the existing tools cover (MLPerf Client and Geekbench AI measure speed without quality; LMSYS/DeepEval/Braintrust measure quality without hardware or economics).

**Before writing any code, read these four files — they are the spec:**
1. `docs/ARCHITECTURE.md` — design principles and module map
2. `docs/METHODOLOGY.md` — the measurement rules; this is what makes the project publishable
3. `docs/ROADMAP.md` — what is done and what is next, in priority order
4. `README.md` — quickstart and layout

**Current state (verified working on this machine, 2026-06-12):** Python 3.14, Ollama 0.30.7 (models: qwen3:1.7b, qwen3:8b, deepseek-r1:7b), RTX 3060 8GB. Install is `pip install -e .`; CLI is `python -m metis.cli` (or `metis` if Scripts is on PATH). The full pipeline runs: `run → score → report → economics`. Self-tests pass (`python tests\test_scoring.py`, 9 groups). The oracle mock scores 1.00 across the board (that is the harness self-test: if it ever doesn't, the harness is broken). A live qwen3:1.7b smoke run produced sensible numbers (107 tok/s decode, TTFT 0.28s, 3717MB peak VRAM) and caught a real small-model agentic failure.

**Your task, in priority order (full list in ROADMAP.md):**
1. **Implement the judge tier** in `metis/scoring/judge.py`. The contract is documented in that file and `config/judge.yaml`: pinned judge model recorded in outputs, pairwise comparison with position swap, rubric-based, writes `judge_scores.jsonl` next to `scores.jsonl` without ever overwriting tier-1 scores, reports merge preferring judge scores only where `needs_judge` is true. Do not weaken any of this.
2. **Add a cloud-API backend** (same `Backend` interface in `metis/backends/base.py`) so the suite can be run against a reference model — that turns coverage-at-threshold from absolute into anchored, which is the headline metric (see `docs/RESEARCH.md`).
3. **Run the first full study**: all three installed models, `--repeats 5`, machine quiesced (do NOT pass `--force`; if preflight fails, wait). Then score, report, and sanity-check the numbers.

**Invariants you must not break:**
- Suite v1 (`metis/suite/v1/`) is FROZEN. New or changed tasks go in a new `v2/` directory.
- Collection and scoring stay separate passes; scoring must always be re-runnable from stored records without inference.
- Everything that can move a number gets recorded (model digest, backend version, sampler params, options). If you add a knob, record it.
- No prices or rates hardcoded anywhere; they live in `config/pricing.yaml` and default to zero on purpose.
- `records.jsonl`/`scores.jsonl` carry `schema_version` (`metis/schema.py`); additive field = patch bump, rename = minor, restructure = major.
- The engine stays headless. No GUI work until ROADMAP item 11.
- Errors during runs are recorded and scored 0, never silently dropped; honest numbers over pretty ones, always.

**Conventions:** Python 3.10+ type hints, stdlib-lean (deps: requests, psutil, PyYAML only; pynvml optional), tests are plain-assert files under `tests/` runnable with `python tests\test_X.py`, Windows-first paths. Match the existing code style; comments only where a constraint is not obvious from the code.

When you finish a work session, update `docs/ROADMAP.md` checkboxes and append a dated entry to a `CHANGELOG.md` (create it on first edit). If Lachy's Jarvis logging convention applies in your environment, log to `agent-memory` as usual.
