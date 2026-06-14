# Next Agent Plan

Authoritative as of 2026-06-14. This file supersedes the older task list in
`HANDOFF.md` and `docs/OVERNIGHT_PLAN.md`. Work from this plan unless Lachy gives
newer instructions.

## Read First

Before writing code, read:

1. `docs/ARCHITECTURE.md`
2. `docs/METHODOLOGY.md`
3. `docs/ROADMAP.md`
4. `README.md`
5. `docs/FINDINGS.md`
6. This file

The current engine already runs end to end: local Ollama, cloud APIs, judge
scoring, reports, economics, routing simulations, router evaluation, step-depth,
and context scaling. Do not redo completed foundation work unless a test proves it
is broken.

## Why The Next Work Changed

The current research has a real ceiling-effect problem. Claude Sonnet 4.6 scores
near the top of Metis v1, so the local-vs-Claude ratio should not be read as a
general intelligence ratio.

Correct language:

> qwen3:8b reaches about 87% of Claude Sonnet 4.6's mean score on the current
> Metis v1 suite.

Incorrect language:

> qwen3:8b is only 13% less intelligent than Claude.

If Opus or a stronger frontier model also scores 100%, that does not mean it has
the same capability as Sonnet. It means the suite lacks frontier headroom. The next
research step is to separate these ideas:

- coverage: how much of this practical local workload a model can handle
- saturation: how often the reference model hits the ceiling
- headroom: whether harder tasks can distinguish strong cloud models from each other

## Current Constraints

- Lachy may not have enough Anthropic API credits for more Claude API testing.
- There may be a short window once Claude subscription usage resets where a
  subscription-backed Agent SDK route can be used instead.
- Do not spend Anthropic API credits without explicit confirmation.
- Do not print, commit, or inspect API keys beyond verifying that expected env var
  names exist.
- If a subscription-backed route is unavailable, defer that experiment and document
  the blocker. Do not silently fall back to paid API calls.
- Today is time-sensitive for Claude testing, but correctness beats rushing.

## Hard Rules

1. `metis/suite/v1/` and `metis/suite/v2/` are frozen. New or changed tasks go in a
   new suite version, likely `metis/suite/v3/`.
2. Collection and scoring remain separate passes.
3. Everything that can move a number must be recorded.
4. No prices or rates in code. Use `config/pricing.yaml`.
5. The engine stays headless. No GUI work.
6. Errors are recorded and scored 0, not dropped.
7. No router implementation work unless explicitly requested. Routing stays
   reporting/simulation for now.
8. No fabricated human labels for judge validation.

## Priority 1: Fix The Research Framing

Update the public-facing research language so it is honest about saturation.

Target files:

- `docs/FINDINGS.md`
- `docs/PAPER.md`
- `README.md` if the headline wording needs a caveat

Add a short "Ceiling and Headroom" note that says:

- v1 is useful for practical local coverage.
- v1 is not hard enough to rank frontier cloud models.
- Claude near-100 means local gaps are measured within this suite envelope, not
  across all possible intelligence.
- Stronger models also scoring 100% would indicate benchmark saturation, not
  equivalence.

If adding metrics, keep them derived from existing artifacts only:

- reference mean score
- fraction of tasks at 1.0
- fraction of categories at or near 1.0
- a boolean or warning like `reference_saturated: true`

Do not run new model calls for this step.

## Priority 2: Prepare A Frontier-Headroom Suite

Design a new suite version rather than modifying v1 or v2.

Recommended shape:

- `metis/suite/v3/` or a documented `docs/FRONTIER_HEADROOM.md` first
- 12 to 20 tasks, not huge
- programmatic scoring wherever possible
- harder coding tasks with hidden tests
- deeper agentic tasks beyond depth 5, with branching and recovery
- long-context comprehension where the answer depends on distant facts, not filler
- adversarial summarisation with conflicting source claims
- instruction-following tasks with interacting constraints

The goal is not to make local models look bad. The goal is to restore measurement
headroom so Sonnet, Opus, DeepSeek, GPT, and local models do not all collapse into
the same ceiling score.

Suggested success criterion:

- Sonnet should not trivially score 100%.
- Opus or a stronger model may outperform Sonnet if tested.
- qwen3:8b should still have identifiable wins or survivable categories if they
  exist.

## Priority 3: Claude Subscription Window, If Available

Only do this when Lachy says the subscription/usage window has reset or the current
agent environment clearly provides a subscription-backed route.

Safe procedure:

1. Confirm the route does not consume Anthropic API credits.
2. Run the smallest meaningful smoke first, ideally N=1 on the proposed headroom
   tasks.
3. Store outputs as normal run artifacts, with backend/source/model metadata.
4. Score as a separate pass.
5. Escalate to N=3 or N=5 only if Lachy approves the time/cost tradeoff.

If using the existing Metis cloud backend, assume it uses API billing unless proven
otherwise. If using an Agent SDK or subscription route, do not bolt it into the core
engine unless it can be made reproducible and records all model/source settings.

If reproducibility is not possible, save it as an exploratory artifact and label it
clearly as non-publishable.

## Priority 4: Judge Validation, If No Claude Window

If Claude testing is blocked, the best low-risk work is judge validation support.

Current state:

- `validation/extract_labels.py` exists.
- `validation/agreement.py` exists.
- Tests exist.
- The missing part is human labels.

Do not fabricate labels. If Lachy is available, ask him to label
`validation/to_label.jsonl` and save it as `validation/human_labels.jsonl`. Then run:

```powershell
python validation\agreement.py
```

Add the resulting agreement table to methodology/paper only after real labels exist.

## Priority 5: Hardware Signature Experiments

After the headroom issue is addressed, return to the roadmap:

1. `llama.cpp` server backend for controlled `n_gpu_layers`
2. offload-cliff sweep
3. automatic WDDM silent-spill detection in reports
4. realistic-conditions mode with RAM pressure

The existing context-scale result already found the 16k cliff for qwen3:8b on the
RTX 3060 8GB. The next hardware work should automate detection, not just describe
one observed run.

## Verification Gates

Before and after any code change, run:

```powershell
python tests\test_scoring.py
python tests\test_judge.py
python tests\test_memory_retrieval.py
python tests\test_judge_agreement.py
python tests\test_saturation.py
python router.py --selftest
python context_scale.py --selftest
```

For docs-only changes, at least run:

```powershell
git diff --check
```

## End-Of-Session Duties

When finishing a session:

- update `PROGRESS.md` with what changed, what was skipped, and why
- update `CHANGELOG.md`
- update `docs/ROADMAP.md` if priorities or checkboxes changed
- never commit `.env`
- if commits are made, keep them small and explainable

## What Lachy Should See First

Make the next visible artifact answer this question:

> Are we measuring local model usefulness, or are we accidentally claiming a
> frontier-intelligence comparison from a saturated suite?

The answer should be clear, honest, and immediately reusable in the paper/findings.
