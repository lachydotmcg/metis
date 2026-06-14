# Future Evaluations Plan

A benchmark's runs cost real resources: GPU time, electricity, API credits, and
your attention reading the output. This plan exists so evaluations are run
**deliberately**, not reflexively. It is the evaluation-specific companion to
`docs/ROADMAP.md` (which tracks code) and `docs/NEXT_AGENT_PLAN.md` (which tracks
the next work).

## Principles (read before running anything)

1. **Don't re-run what's already collected.** See the inventory below. Scoring,
   reports, comparisons, saturation, and router eval are all re-runnable from
   stored records *without* new inference — exhaust those first.
2. **Smallest meaningful N first.** Smoke at N=1 to prove the pipeline and prompts,
   inspect, then escalate to N=3/N=5 only if the smoke looks right.
3. **Budget gates are hard.** Anthropic API credits are constrained — never spend
   them without explicit approval. DeepSeek balance is ~a few dollars. GPU runs
   belong in idle windows (overnight). Never pass `--force` to a real run; if the
   preflight quiesce check trips, the machine is busy — wait.
4. **Every run records its knobs.** Model digest, quant, sampler, context, backend
   version, fingerprint. A run whose conditions aren't captured is not publishable.
5. **One fingerprint is a sample of one.** Cross-machine claims require the
   community-data path, not louder wording.

## Data already in hand (do NOT re-run to answer these)

| Question | Answered by |
|---|---|
| Local vs Claude quality, per category | `results/20260612_173212` + `results/20260612_201339` (+ comparison) |
| Where small models break on multi-step tool use | step-depth ladder (suite v2), depth 1/2/3/5 |
| Cost/quality of local vs cheap cloud routing | routing sim + `router.py eval` |
| Is the suite saturated by the reference model? | `metis saturation` (yes: Claude mean 0.976, 86% at ceiling) |
| Decode behaviour across context length | `context_scale.py` (16k cliff found) |

## Planned evaluations (priority order)

### E1 — Frontier-headroom suite (v3), reference smoke
**Question:** can a harder suite distinguish strong cloud models instead of letting
them all hit 100%? **Blocked on:** suite v3 designed and frozen first (see
`docs/NEXT_AGENT_PLAN.md` Priority 2 / a future `docs/FRONTIER_HEADROOM.md`). **Run:**
the reference model only, N=1, on v3. **Success criterion:** the reference does
**not** score ~100% (i.e. `metis saturation` reports `reference_saturated: false`).
If it still saturates, v3 isn't hard enough — iterate the tasks, don't run more
models. **Cost:** one small cloud run; gated on credit approval. **Output:** normal
run dir + a saturation report on v3.

### E2 — Judge–human agreement (no model calls)
**Question:** can the LLM judge's summarisation scores be trusted? **Run:** label
`validation/to_label.jsonl` by hand (~50 items, Lachy), save as
`validation/human_labels.jsonl`, then `python validation/agreement.py`. **No new
inference** — this scores already-collected judge output against human labels.
**Success criterion:** report correlation + mean-abs-error; only then cite judge
numbers as validated in `PAPER.md`. **Cost:** human time only.

### E3 — Offload-cliff sweep
**Question:** how does tok/s degrade as GPU layers decrease and the model spills to
CPU/RAM? **Blocked on:** llama.cpp server backend (controls `n_gpu_layers`; Ollama's
`num_gpu` is a partial substitute). **Run:** qwen3:8b, sweep layers, N=3, idle GPU
window. **Success criterion:** a published tok/s-vs-layers curve. **Cost:** GPU time;
no API.

### E4 — Realistic-conditions mode
**Question:** how much does a loaded machine (RAM pressure, the "40 Chrome tabs"
case) change local throughput and the local-vs-cloud break-even? **Run:** re-run the
v1 suite for qwen3:8b under synthetic RAM load, N=3, vs the clean baseline already in
hand. **Success criterion:** a delta table, clean vs loaded. **Cost:** GPU time.

### E5 — Router robustness on out-of-distribution prompts
**Question:** the keyword classifier hit 100% on the *discriminative* v1 prompts —
how does it do on prompts that straddle categories or use unusual phrasing? **Run:**
hand-write/collect ~20 OOD prompts with known categories, run `router.py classify`
on them (no model inference needed for accuracy), and report the confusion +
fail-safe rate. **Success criterion:** an honest accuracy-degradation number to
replace the "best-case" caveat in FINDINGS. **Cost:** near zero.

### E6 — Cross-machine / community data
**Question:** do the findings hold off this one RTX 3060? **Run:** the suite on other
hardware (opt-in uploads), aggregated by anonymised fingerprint. **Cost:** other
people's machines; lowest priority until the headline story is locked.

## When in doubt

If a question can be answered by re-scoring, re-reporting, or re-simulating existing
records, do that. Spend a model run only when the question genuinely requires new
generations, and then run the smallest one that could answer it.
