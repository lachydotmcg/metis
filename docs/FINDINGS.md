# Findings

This is the current human-readable results section for Metis. It consolidates
the full local study, Claude cloud baseline, DeepSeek V4 Pro routing baseline,
comparison artifact, step-depth ladder, and Phase 0 routing simulation.

## Run Ledger

| artifact | run / path | note |
|---|---|---|
| Full local study | `results/20260612_173212` | qwen3:1.7b, qwen3:8b, deepseek-r1:7b; N=5; 315 generations; 0 errors |
| Claude reference | `results/20260612_201339` | claude-sonnet-4-6; N=5; judge scores merged |
| DeepSeek routing baseline | `results/20260612_214955` | deepseek-v4-pro; N=5; judge scores merged; preflight was forced |
| Local vs Claude comparison | `results/comparison_20260612_173212_vs_20260612_201339` | coverage curve, quality-vs-speed chart, anchored metrics |
| Step-depth ladder | `results/step_depth_comparison_20260612_203254_vs_20260612_210103` | suite v2 agentic depth 1/2/3/5 |
| Routing sim table | `results/routing_qwen3_8b_vs_deepseek_v4_pro.md` | qwen3:8b local tier vs DeepSeek V4 Pro cloud tier |

All local/cloud quality numbers below use the merged score view: tier-1 scores
plus `judge_scores.jsonl` for `needs_judge` summarisation rows.

## Anchored Quality

Claude Sonnet 4.6 is the reference for the main benchmark, but it is also near the
ceiling of Metis v1. Against that bounded anchor, qwen3:8b reaches 87% of Claude's
mean per-task quality and clears a 90%-of-Claude bar on 81% of tasks. This should
be read as practical suite coverage, not as "qwen3:8b is 13% less intelligent than
Claude."

| model | mean quality | mean vs Claude | tasks >=90% of Claude | absolute coverage@0.9 | decode tok/s | peak VRAM MB |
|---|---:|---:|---:|---:|---:|---:|
| qwen3:1.7b | 0.77 | 78% | 71% | 67% | 121.3 | 7864 |
| qwen3:8b | 0.87 | 87% | 81% | 81% | 39.0 | 7610 |
| deepseek-r1:7b | 0.65 | 66% | 52% | 52% | 41.7 | 7806 |
| claude-sonnet-4-6 | 0.98 | 100% | 100% | 90% | 35.3 | n/a |

Per category, qwen3:8b reaches the same measured ceiling as Claude on agentic and
reasoning tasks, scores higher on the judged summarisation rows, and still loses
badly on coding. Because Claude is already at or near the top of the scale in
several categories, these category ties are saturation signals. They do not prove
that the local model has the same latent capability as Claude or a stronger cloud
model.

| category | Claude Sonnet 4.6 | qwen3:8b | qwen3:1.7b | deepseek-r1:7b |
|---|---:|---:|---:|---:|
| agentic | 0.93 | 1.00 | 0.33 | 0.00 |
| coding | 1.00 | 0.60 | 0.60 | 0.80 |
| instruction_following | 1.00 | 0.90 | 0.95 | 0.73 |
| reasoning | 1.00 | 1.00 | 1.00 | 0.80 |
| summarisation | 0.90 | 0.94 | 0.81 | 0.69 |

Interpretation: the local story is not "8GB replaces Claude." It is "an 8GB
card covers a surprisingly large and identifiable chunk of the workload, if
you route by task type."

## Ceiling And Headroom

The current benchmark is strongest as a local-coverage test, not as a frontier
model ranking test. Claude Sonnet 4.6's near-ceiling score means the suite has
limited headroom above it: if Opus or another stronger model also scored 100%, that
would show benchmark saturation, not equal intelligence between the cloud models.

This matters for the headline comparison. The 87% number is anchored to the
observable Metis v1 task envelope. It says qwen3:8b solves much of this suite on
this machine; it does not say the model is only 13% below Claude in general.
Future suites need harder tasks to measure frontier headroom separately from local
coverage.

Saturation is now a measured, reproducible fact, not just a caveat. Run
`metis saturation results/20260612_201339` (artifact: `saturation.md` /
`saturation.json` in that run). On the Claude reference run it reports
**mean 0.976, 18/21 tasks (86%) at the ceiling (≥0.99), 3/5 categories saturated,
headroom 0.024, `reference_saturated: true`** — so the suite has, by its own
metric, run out of room to distinguish Claude from a stronger model. Any future
"X% of Claude" headline should be read alongside this flag.

## Step-Depth Degradation

The v2 step-depth ladder is the cleanest signature result so far. It uses four
agentic tasks requiring 1, 2, 3, and 5 tool-depth steps.

| model | depth 1 | depth 2 | depth 3 | depth 5 | first depth below 90% |
|---|---:|---:|---:|---:|---:|
| qwen3:1.7b | 100% | 0% | 0% | 0% | 2 |
| qwen3:8b | 100% | 100% | 100% | 100% | >5 |
| deepseek-r1:7b | 100% | 0% | 0% | 0% | 2 |
| claude-sonnet-4-6 | 100% | 100% | 100% | 100% | >5 |

Small local models handled a single lookup, then broke immediately at depth 2.
qwen3:8b and Claude both reached the measured ceiling through depth 5. That is a
qualitative boundary for local usefulness, not proof that they would remain tied
on deeper or more adversarial agentic tasks.

## Routing Reality Check

The original cost-savings headline does not hold against a very cheap cloud
model. DeepSeek V4 Pro is inexpensive enough that the full 21-task suite costs
about AUD 0.0142 per pass, normalised from the N=5 run. That means even a large
percentage saving is a fraction of a cent in absolute terms.

With qwen3:8b as the local tier and DeepSeek V4 Pro as the cloud tier:

| strategy | success (/21) | cost (AUD) | cost / success |
|---|---:|---:|---:|
| all-cloud DeepSeek V4 Pro | 20.23 | 0.0142 | 0.000703 |
| all-local qwen3:8b | 18.31 | 0.0078 | 0.000424 |

Blanket local routing saves about AUD 0.0064 per suite pass, but loses nearly
two points of quality. That is not a compelling product thesis by itself.

### Absolute Threshold Rule

Route a category to local when the qwen3:8b category mean clears an absolute
quality threshold.

| threshold | local categories | success | cost (AUD) | cost / success | % of cloud success | % cost saved |
|---|---|---:|---:|---:|---:|---:|
| 0.85 | agentic, instruction_following, reasoning, summarisation | 20.31 | 0.0074 | 0.000365 | 100.4% | 47.9% |
| 0.90 | agentic, instruction_following, reasoning, summarisation | 20.31 | 0.0074 | 0.000365 | 100.4% | 47.9% |
| 0.95 | agentic, reasoning | 20.23 | 0.0109 | 0.000539 | 100.0% | 23.4% |

The percentage savings look good, but the absolute saving at the 0.90 threshold
is only about AUD 0.0068 per 21-task pass. This is useful as routing evidence,
not as a standalone cost-savings headline.

### Comparative Rule

Route a category to local only when local quality is at least the cloud
baseline quality for that category.

| local categories | success | cost (AUD) | cost / success | % of cloud success | % cost saved |
|---|---:|---:|---:|---:|---:|
| agentic, reasoning, summarisation | 20.81 | 0.0090 | 0.000434 | 102.9% | 36.4% |

This is the routing finding that survives. Summarisation is a local win on both
quality and cost: qwen3:8b scores 0.936 vs DeepSeek V4 Pro's 0.743, while local
energy cost is still tiny. An absolute threshold can miss this kind of result
because it asks "is local globally excellent?" instead of "is local better than
the actual cloud tier I would otherwise call?"

The second surviving finding is not in the cost table: local inference is
quota/rate-limit insurance. If the cloud API is unavailable, rate-limited,
privacy-constrained, or budget-capped, qwen3:8b is not a toy fallback. It is a
usable local tier for a meaningful subset of tasks.

## What This Means

The practical routing policy suggested by these runs is:

- Use qwen3:8b locally for reasoning, summarisation, and the measured agentic
  tasks when latency and local availability matter.
- Escalate coding to cloud until the local coding score improves.
- Treat qwen3:1.7b as a fast, cheap utility model for simple work, not as a
  robust agentic tier.
- Do not sell local routing as a blanket cost-saving story against low-cost
  APIs. Sell it as capability coverage, resilience, privacy, and selective
  quality wins.

## Threats To Validity

- **Judge bias:** LLM judges have position and verbosity biases. Metis mitigates
  this with programmatic scoring for most v1 tasks and pairwise position-swap
  judging for summarisation, but the planned ~50-item human-agreement validation
  set is still pending.
- **Contamination:** Public benchmark items can live in training data. Metis v1
  tasks are original, and agentic tasks use fictional entities, but this is
  still a small hand-written suite.
- **Single machine:** These results are for one fingerprint: AMD Ryzen 5 5500,
  31.9GB RAM, RTX 3060 8GB. Cross-machine claims require a community dataset.
- **Sampling resolution:** VRAM and power are sampled at roughly 500ms, so short
  spikes can be missed and energy can be undercounted for short generations.
- **Latency framing:** TTFT includes HTTP/runtime overhead. For cloud models it
  also includes network/provider latency; for local models it reflects Ollama
  on this Windows machine.
- **DeepSeek routing baseline preflight:** The DeepSeek V4 Pro run was executed
  with `--force` after a high CPU preflight. Quality scoring is unaffected, but
  latency and local monitor readings for that cloud run should not be overread.
- **Pricing drift:** API prices and FX rates change. The routing cost table uses
  the configured DeepSeek V4 Pro rates in `config/pricing.yaml`, not a timeless
  constant.

## Phase 1 Router Evaluation (2026-06-13)

Full artifact: `results/router_eval_qwen3_8b_vs_deepseek_v4_pro.md`

The keyword classifier in `router.py` achieves **100% category-prediction accuracy**
on all 21 v1 suite prompts at default settings (threshold 0.9, min_confidence 0.34).
Zero backend flips occur — the classifier routing is indistinguishable from the
oracle (Phase 0, known-category) routing.

### Classifier accuracy vs threshold

| threshold | clf accuracy | backend flips | % of cloud success | % cost saved |
|---|---|---|---|---|
| 0.85 | 100% | 0 | 100.4% | 47.9% |
| 0.90 | 100% | 0 | 100.4% | 47.9% |
| 0.95 | 100% | 0 | 100.0% | 23.4% |

At 0.85–0.90 the policy is stable (agentic, instruction_following, reasoning, and
summarisation route locally; coding routes to cloud). At 0.95 the bar moves
instruction_following and summarisation to cloud, costing about half the savings.

### Min-confidence sensitivity (threshold = 0.90)

| min_confidence | backend flips | % of cloud success | % cost saved |
|---|---|---|---|
| 0.34 (default) | 0 | 100.4% | 47.9% |
| 0.50 | 0 | 100.4% | 47.9% |
| 0.70 | 3 | 97.5% | 37.9% |

Raising min_confidence to 0.70 triggers the low-confidence fail-safe for three tasks
(reasoning.sports conf=0.64, summarisation.actions conf=0.60,
summarisation.changelog conf=0.62), redirecting them to cloud and costing 0.58
quality-points but adding AUD 0.0014 vs oracle. The fail-safe is working as designed.

### Out-of-distribution robustness (measured, 2026-06-15)

The 100% above is a **best case**: the v1 prompts were written with distinctive
vocabulary, so keyword rules fire cleanly. To measure honest degradation, 22
hand-written out-of-distribution prompts (straddling categories or using unusual
phrasing that avoids the discriminative keywords; no suite prompts, no model
inference) were classified against known labels with `python router.py ood`.
Full artifact: `results/published/router_ood/report.md`.

| metric | OOD prompts | discriminative v1 |
|---|---|---|
| classification accuracy | **40.9%** (9/22) | 100% |
| fail-safe rate (low-confidence → cloud) | 54.5% (12/22) | — |
| silent-misroute rate (confident **and** wrong) | **22.7%** (5/22) | 0% |

Accuracy falls from 100% to **40.9%** on realistic, non-discriminative prompts —
the keyword classifier is brittle, as expected. The min-confidence gate is the
load-bearing defence: it catches **12 of the 13** misclassifications (the
confidence is 0.00 when no rule fires) and reroutes them safely to cloud at a
small cost premium. The real exposure is the **22.7% silent-misroute rate** —
prompts the classifier is *confident* about but gets wrong (mostly
instruction/summary prompts misread as coding when they mention code, and a
genuine straddle like "summarise this Python function"). Those bypass the gate.
Per-category, reasoning is most robust (4/5, it is the zero-signal default) and
summarisation/coding/instruction degrade most. This replaces the earlier
"best-case caveat" with a number: the router is production-ready only behind the
fail-safe, and only where a ~23% silent-misroute exposure on novel phrasing is
acceptable.

## Context-Length Scaling (2026-06-14)

Full artifact: `results/published/context_scale_qwen3_8b/report.md`
(signature experiment §6 in `docs/RESEARCH.md`, run via `context_scale.py`).

The v1 reasoning tasks were padded with neutral filler to fill 512 / 2k / 8k / 16k of
context, then run on qwen3:8b at N=3. Decode speed is the headline; quality is a
secondary check that the padded task is still answered.

| context | tasks | score (mean) | decode tok/s | wall_s (mean) | errors |
|---|---:|---:|---:|---:|---:|
| 512 | 5 | 1.00 | 41.4 | 19.2 | 0 |
| 2048 | 5 | 1.00 | 40.0 | 13.7 | 0 |
| 8192 | 5 | 1.00 | 36.5 | 16.8 | 0 |
| 16384 | 5 | 1.00 | 9.8 | 53.3 | 0 |

Decode holds near 40 tok/s out to 8k, then **collapses to 9.8 tok/s at 16k — about a
4× slowdown — with zero errors**. That "fits but crawls" signature is the Windows WDDM
silent-spill the project predicted (RESEARCH.md §3): the KV cache for 16k tokens
overflows the 8 GB card into shared system memory instead of erroring, so the model
keeps answering correctly (quality stays 1.00) at a fraction of the speed. The cliff,
not a gentle slope, is the point — between 8k and 16k the card crosses from
VRAM-resident to spilled.

This is now detected automatically rather than described by eye:
`context_scale.detect_silent_spill` flags the first context size whose mean decode
throughput collapses to ≤50% of the previous size's while still recording zero errors,
and the report header now carries a machine-readable `silent_spill: true` line with the
boundary (here: 8192 → 16384, drop ratio 0.27). A drop that arrives *with* errors is an
out-of-memory failure and is deliberately **not** flagged as a silent spill — the two
regimes are distinct. The check is eval-free: it runs on already-collected results, so it
re-applies to any past or future context-scale run without new inference.

### Honest caveats

- Context length here is filler padding, not genuinely information-dense long input;
  it stresses the KV cache and prefill, which is what this experiment is about, but it
  is not a long-context *comprehension* test.
- The quality column uses a lightweight standalone scorer (`\boxed{}`/`Answer:` aware,
  thinking stripped), not the full `metis` scoring pass; it confirms the task is still
  answered, it is not a coverage claim.
- Decode tok/s is runtime-reported (`eval_count / eval_duration`). The 16k cliff is large
  enough to be unambiguous, but exact tok/s at the spill boundary is noisy.
- Single fingerprint (RTX 3060 8 GB). The 16k boundary is card- and quant-specific; the
  *shape* (cliff, not slope) is the transferable finding, the exact threshold is not.
