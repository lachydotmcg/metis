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

Claude Sonnet 4.6 is the frontier-ish reference for the main benchmark. Against
that anchor, qwen3:8b is much closer than the raw model-size intuition suggests:
it reaches 87% of Claude's mean per-task quality and clears a 90%-of-Claude bar
on 81% of tasks.

| model | mean quality | mean vs Claude | tasks >=90% of Claude | absolute coverage@0.9 | decode tok/s | peak VRAM MB |
|---|---:|---:|---:|---:|---:|---:|
| qwen3:1.7b | 0.77 | 78% | 71% | 67% | 121.3 | 7864 |
| qwen3:8b | 0.87 | 87% | 81% | 81% | 39.0 | 7610 |
| deepseek-r1:7b | 0.65 | 66% | 52% | 52% | 41.7 | 7806 |
| claude-sonnet-4-6 | 0.98 | 100% | 100% | 90% | 35.3 | n/a |

Per category, qwen3:8b matches or beats Claude on agentic, reasoning, and
summarisation in this small suite, but still loses badly on coding. qwen3:1.7b
is fast and useful, but not reliable once the task requires multi-step tool use
or coding correctness.

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
qwen3:8b matched Claude through depth 5. That is a qualitative boundary, not
just a few points on an average score: on this protocol, the 8B local model is
the first local tier that makes multi-step tool use reliable.

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

### Honest caveat

This is a best-case result on a small, discriminative suite. The tasks were written
with distinctive vocabulary, so keyword rules fire cleanly. Real-world prompts that
straddle categories or use unusual phrasing will degrade accuracy; the min-confidence
gate is the first defence. Robustness testing on out-of-distribution prompts is the
next step before claiming production readiness.
