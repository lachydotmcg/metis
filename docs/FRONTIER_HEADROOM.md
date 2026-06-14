# Suite v3 — Frontier Headroom

## Why v3 exists

Claude Sonnet 4.6 nearly saturates Metis v1 (`metis saturation` reports mean
0.976, ~86% of tasks at the 1.0 ceiling, `reference_saturated: true`). A
saturated suite cannot *rank* strong models: if Sonnet, Opus, DeepSeek and GPT
all score ~100%, the number measures the suite's envelope, not the models'
relative capability. v1 and v2 stay frozen and remain the right tool for
measuring **practical local coverage**. v3 is a separate, harder suite whose only
job is to **restore measurement headroom** at the top end.

The goal is *not* to make local models look bad. It is to spread strong models
apart again so a difference between Sonnet and Opus (or between a local model and
a frontier one) shows up as a score gap instead of a shared ceiling.

## Design constraints

- **Frozen.** v1 and v2 are immutable; v3 is its own version directory. Editing a
  v3 task after release means a v4, never an in-place edit.
- **Programmatic scoring wherever possible.** Every v3 task is scored by the
  Tier-1 programmatic scorers (`numeric_exact`, `choice_exact`, `constraints`,
  `code_tests`, `agentic_final`). No task in v3 depends on the LLM judge, so the
  whole suite can be designed, validated, and scored with **zero model calls**.
- **Contamination-safe.** All entities, passages, and problems are original and
  fictional (see `docs/METHODOLOGY.md` §5), so answers cannot pre-exist in
  training data.
- **Self-validating.** Each task carries its own reference answer
  (`oracle_code` / `oracle_text` / `expected`). `tests/test_v3_suite.py` scores
  every reference with the real scorers and requires 1.0, so a broken task
  definition fails CI rather than silently mis-scoring a model.

## What's in it (18 tasks, 5 categories)

| File | Category | Tasks | What makes it hard |
|---|---|---|---|
| `coding.yaml` | `coding` | 5 | DP (`min_coins`), matrix spiral, Roman numerals, RPN eval, an off-by-one binary-search debug. The prompt shows one example; the scoring `tests` add **hidden edge cases** (empty, single element, impossible, boundary shapes) so happy-path-only code does not reach 1.0. |
| `agentic.yaml` | `agentic_deep` | 4 | More than five dependent tool calls; **conditional branching** (answer depends on a comparison of looked-up values); argmin/argmax over per-entity ratios; **recovery** from an injected tool failure (`fail_first_call`). |
| `long_context.yaml` | `long_context` | 3 | The two/three facts the answer needs sit **far apart** inside a long passage full of plausible distractor numbers and names, so "grab the last/biggest number" fails. |
| `adversarial_summarisation.yaml` | `adversarial_summary` | 3 | Each source contains **conflicting claims** (a retraction, an official-vs-unofficial figure, a disputed-vs-primary-source date). Scored by `regex_must` (correct figure present) + `regex_forbid` (superseded figure absent), so conflict resolution — not fluent prose — is what's measured. |
| `instruction_following.yaml` | `instruction_following` | 3 | Several **interacting constraints** that pull against each other (write about a topic without its obvious word; an ordered, punctuation-free, digit-free list; strict typed JSON with a bounded integer). |

## How to run it

v3 is selectable through the existing loader by version string — no code changes:

```powershell
# design/validation only, zero model calls
python tests\test_v3_suite.py

# a real run uses the normal pipeline (collection then scoring)
metis run --suite v3 --backend mock          # smoke the pipeline, no GPU/credits
metis run --suite v3 --backend ollama --model qwen3:8b --n 1   # GPU-gated, idle only
```

## Success criterion (validated later, with approval)

v3 is "working" when a near-frontier reference does **not** trivially max it —
i.e. running `metis saturation` on a v3 reference run reports
`reference_saturated: false`. That validation requires one small reference run
and is therefore **gated on explicit credit/GPU approval** (see
`docs/FUTURE_EVALUATIONS.md` E1). If a reference still saturates v3, the fix is to
make the tasks harder, **not** to run more models. No frontier models were run to
build or validate the suite definition.
