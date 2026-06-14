# Handoff Prompt For The Next Agent

Paste everything below the line into a fresh capable model session, working in
`C:\Users\nirke\OneDrive\Documents\Metis`.

---

You are continuing work on **Metis**, a research-grade benchmark for local LLMs.
It measures quality x hardware x dollars in one reproducible run.

The old handoff tasks are complete. Do **not** start by implementing judge scoring,
cloud backends, or the first full local study; those already exist.

Before writing code, read these files:

1. `docs/ARCHITECTURE.md`
2. `docs/METHODOLOGY.md`
3. `docs/ROADMAP.md`
4. `README.md`
5. `docs/FINDINGS.md`
6. `docs/NEXT_AGENT_PLAN.md`

`docs/NEXT_AGENT_PLAN.md` is the current authoritative plan. The next research
issue is the ceiling effect: Claude Sonnet 4.6 nearly saturates Metis v1, so the
qwen3:8b result should be framed as practical suite coverage, not a general
intelligence ratio. Lachy may have a short Claude subscription-backed testing
window once usage resets; do not spend Anthropic API credits unless he explicitly
approves it.

Keep the invariants:

- `metis/suite/v1/` and `metis/suite/v2/` are frozen.
- Collection and scoring stay separate.
- Record every knob that can move a number.
- No prices in code.
- The engine stays headless.
- Errors are recorded and scored 0.
- Never commit `.env` or secrets.

When finishing a session, update `PROGRESS.md`, `CHANGELOG.md`, and
`docs/ROADMAP.md` as appropriate.
