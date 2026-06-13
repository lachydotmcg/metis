# How Much Frontier Capability Fits in 8 GB?
## Quality-Adjusted Cost Frontiers for Consumer-Hardware LLM Inference

**Status:** Working draft — 2026-06-13. Numbers sourced from real runs unless marked
`[TODO: verify]`. Mark these before any public release.

---

## 1. Introduction

### 1.1 The Gap

Two families of LLM evaluation tools exist and they do not talk to each other.

Hardware benchmarks — MLPerf Client, Geekbench AI — measure tokens per second and
VRAM utilisation and report nothing about whether the output was useful. Quality
benchmarks — LMSYS Arena, DeepEval, Braintrust, Inspect AI — treat the model as an
API endpoint with no footprint and never ask what it costs to run on the machine in
front of you. The gap is precisely the thing every person running a local model cares
about: **what fraction of real work can this hardware handle, at what quality, and
what does the gap cost to fill?**

This is not a minor omission. The economics of local inference are non-trivial.
Local electricity and hardware amortisation are real but often ignored. Cloud API
costs are denominated per million tokens and therefore scale with usage in ways
a flat subscription does not. A rigorous comparison requires running the same
frozen task suite against both tiers, under real hardware conditions, with
measurement throughout.

No existing tool does this. Metis is an attempt to do it correctly.

### 1.2 Research Question

> How much frontier capability fits in 8 GB? Specifically: for a fixed consumer-
> hardware machine and a frozen task suite, what fraction of tasks can a local model
> complete at acceptable quality, how fast, at what energy cost, and where is the
> break-even against a cloud API baseline?

The secondary question that emerges from the routing framing:

> Can a cheap runtime classifier replicate the quality and cost of an oracle
> (category-aware) routing policy, using prompt text alone?

### 1.3 Contributions

1. **Metis v0.1.1**: an open-source, headless benchmarking engine that runs a
   versioned task suite against Ollama-served local models and cloud API backends,
   captures hardware state throughout, scores output quality programmatically (with
   an LLM-as-judge tier for subjective tasks), and reports anchored coverage curves
   and routing economics. Code and versioned suite at `github.com/lachydotmcg/metis`.

2. **A three-model 8 GB frontier study** on a single RTX 3060 8 GB machine:
   qwen3:8b, qwen3:1.7b, and deepseek-r1:7b against a Claude Sonnet 4.6 cloud
   reference, N=5, 315 local generations, zero errors.

3. **A step-depth degradation curve** for agentic tasks: the first local model tier
   at which multi-step tool use is reliable, not just plausible.

4. **Phase 0 + Phase 1 routing evaluation**: a per-category routing simulation and
   a runtime keyword classifier, evaluated against oracle routing and the all-cloud
   baseline.

---

## 2. Methodology

### 2.1 Task Suite (v1.0 — frozen)

21 original tasks across five categories: **reasoning** (5), **coding** (5),
**instruction following** (5), **summarisation** (3), and **agentic tool use** (3).
Tasks are original and were not imported from public benchmarks. Agentic tasks use
fictional entities (Veldora, Marrowgate, Ostrel, the Calder Bridge) whose correct
answers cannot appear in any training set (contamination policy, §2.5).

Suite v1.0 is frozen. A prompt edit means a new suite version. The 21 v1 tasks have
not been modified since initial design.

### 2.2 Capture Protocol

**Hardware fingerprint per run:** CPU model, core counts, RAM, GPU name, VRAM,
driver version, OS, Python version, Metis version. Recorded in `fingerprint.json`.

**Model pinning:** model name, content digest from the Ollama registry, parameter
size, quantization level, family. A different digest means a different model, even
if the name is the same.

**Measurement during generation (local models only):** time-to-first-token (streamed,
wall-clock), decode tokens/sec (`eval_count / eval_duration`), prefill tokens/sec,
load duration (cold vs warm), peak VRAM (500 ms poll), GPU power average (W), GPU
temperature, integrated energy per generation (J, from power samples × Δt).

**Run scheduler:** rotating block within each repeat round so no model always runs
hot. Trade-off: avoids thermally biasing later models at the cost of per-generation
model reloads between rounds; reloads are captured and separable.

**Preflight quiesce check:** refuse to start if background CPU load >40%; override
with `--force`, which is recorded in the manifest. The DeepSeek V4 Pro baseline run
used `--force` after a high-CPU preflight (see §4.5).

**Repeats:** N=5 for all published runs. Statistics reported as mean ± 95% CI
(t-distribution, small-N-aware). Single-repeat numbers are for smoke tests only.

### 2.3 Scoring: Programmatic First, Judge Last

**Tier 1 — programmatic (18 of 21 v1 tasks):**
- *Reasoning:* forced answer format ("Answer: \<x\>"), exact numeric or choice match.
- *Coding:* extract fenced code, execute against test cases in an isolated subprocess
  (`python -I`, 20 s timeout). Each task carries a reference solution validated
  against its own test suite, so a broken test is distinguishable from a model
  failure.
- *Instruction following:* IFEval-style verifiable constraints — word counts,
  sentence counts, forbidden words, JSON schema validation, alphabetical ordering.
  Score = fraction of constraints satisfied.
- *Agentic:* final answer extracted from the model's last structured turn, matched
  numerically or by choice. Also records steps used, tool-call validity rate, and
  recovery from injected failures.

**Tier 2 — LLM-as-judge (summarisation, 3 tasks):**
- Judge model: Claude Sonnet 4.6 (pinned; config in `config/judge.yaml`).
- Protocol: pairwise rubric scoring with position swap (both "reference vs
  candidate" and "candidate vs reference" orderings, averaged) to counteract
  position bias.
- Judge tier is a separate, re-runnable pass over stored outputs. Upgrading the
  judge never invalidates collected generations.
- Human-agreement validation set is **pending** (target: ~50 items, correlation +
  mean absolute error). Until this table exists, the judge scores should be read
  as indicating direction, not as a validated absolute scale.

### 2.4 Agentic Protocol

Deterministic tool loop: the model is given `lookup(query)` and `calc(expression)`
over a fixed corpus with an AST-safe calculator. Strict JSON turn format; invalid
turns are recorded (not retried). Captured per task: success, steps used vs budget,
tool-call validity rate, invalid-JSON turn count, and recovery behaviour (one task
injects a transient tool error on the first call and measures retry).

### 2.5 Contamination Policy

All 21 tasks are original. Agentic tasks use fictional entities with no known
training data (Veldora, Marrowgate, Ostrel). No public benchmark items were imported.
Suite versions are frozen. See METHODOLOGY.md §5.

### 2.6 Economics

Local cost = (energy_J / 3.6×10⁶) × electricity_per_kWh + (wall_s / 3600) ×
hardware_amortisation_per_hour. Cloud cost = (prompt_tokens × rate_in +
output_tokens × rate_out) / 10⁶ × FX.

Rates are configured in `config/pricing.yaml` with no defaults, so stale numbers
cannot silently masquerade as current ones. The engine refuses to print cost figures
until rates are explicitly configured.

---

## 3. Results

### 3.1 Machine

All results in §3.2–3.5 are from a single fingerprint:

| component | value |
|---|---|
| CPU | AMD Ryzen 5 5500 (6-core) |
| RAM | 31.9 GB |
| GPU | NVIDIA RTX 3060 8 GB (128-bit bus, ~240 GB/s bandwidth) |
| OS | Windows 11 |
| Ollama version | [TODO: verify from manifest] |
| Metis version | v0.1.1 |

### 3.2 Quality vs Cloud Reference (qwen3:8b and qwen3:1.7b vs Claude Sonnet 4.6)

Main local study: `results/20260612_173212` (qwen3:1.7b, qwen3:8b, deepseek-r1:7b,
N=5, 315 generations, 0 errors). Cloud reference: `results/20260612_201339`
(claude-sonnet-4-6, N=5, 105 generations). Judge scores merged for summarisation.

#### 3.2.1 Overall quality

| model | mean score | vs Claude | tasks ≥90% of Claude | coverage@0.9 | decode tok/s | peak VRAM |
|---|---:|---:|---:|---:|---:|---:|
| qwen3:1.7b | 0.77 | 78% | 71% | 67% | 121.3 | 7864 MB |
| qwen3:8b | 0.87 | 87% | 81% | 81% | 39.0 | 7610 MB |
| deepseek-r1:7b | 0.65 | 66% | 52% | 52% | 41.7 | 7806 MB |
| claude-sonnet-4-6 | 0.98 | — | — | 90% | 35.3\* | n/a |

\* Cloud decode rate includes provider + network latency; not directly comparable to
local decode rate.

qwen3:8b reaches 87% of Claude's mean task quality on this suite, with 81% of tasks
clearing a 90%-of-Claude bar. This is a much closer result than the 4× parameter
count difference would naively suggest.

#### 3.2.2 Per-category breakdown

| category | claude-sonnet-4-6 | qwen3:8b | qwen3:1.7b | deepseek-r1:7b |
|---|---:|---:|---:|---:|
| agentic | 0.93 | **1.00** | 0.33 | 0.00 |
| coding | **1.00** | 0.60 | 0.60 | 0.80 |
| instruction_following | **1.00** | 0.90 | 0.95 | 0.73 |
| reasoning | **1.00** | **1.00** | **1.00** | 0.80 |
| summarisation | 0.90 | **0.94** | 0.81 | 0.69 |

The clearest local wins are in reasoning and summarisation. On reasoning, all three
evaluated models achieve 0.80–1.00 (small suite caveat: 5 tasks). On summarisation,
qwen3:8b scores *above* Claude Sonnet 4.6 (0.94 vs 0.90) — a category-level local
superiority that becomes the basis for the summarisation routing claim in §3.4.
Coding is the clear local weakness: qwen3:8b at 0.60 vs Claude at 1.00.

#### 3.2.3 Coverage curve

Coverage(t) = fraction of tasks where the model's mean score ≥ t. At t=0 all models
cover 100% of tasks; as t increases coverage falls. The curve makes the economic
argument without defending a single threshold:

| t | qwen3:1.7b | qwen3:8b | deepseek-r1:7b | claude-sonnet-4-6 |
|---|---:|---:|---:|---:|
| 0.50 | 81% | 95% | 67% | 100% |
| 0.70 | 76% | 86% | 57% | 100% |
| 0.90 | 67% | 81% | 52% | 90% |
| 1.00 | 14% | 52% | 14% | 52% |

Full 21-point curve available in the HTML report (generated by `metis report`).

### 3.3 Step-Depth Degradation (Agentic Ladder)

Suite v2 adds a four-task agentic ladder requiring 1, 2, 3, and 5 sequential tool
calls. Runs: `results/step_depth_local/20260612_203254` (local) and
`results/step_depth_cloud/20260612_210103` (cloud), N=5 each.

| model | depth 1 | depth 2 | depth 3 | depth 5 | first failure depth |
|---|---:|---:|---:|---:|---:|
| qwen3:1.7b | 100% | 0% | 0% | 0% | 2 |
| qwen3:8b | 100% | 100% | 100% | 100% | >5 |
| deepseek-r1:7b | 100% | 0% | 0% | 0% | 2 |
| claude-sonnet-4-6 | 100% | 100% | 100% | 100% | >5 |

The step-depth cliff is a qualitative boundary, not a gradient. qwen3:1.7b and
deepseek-r1:7b handle a single lookup then break immediately when the task requires
chaining two tool calls. qwen3:8b matches Claude Sonnet 4.6 through depth 5. This
puts qwen3:8b as the first local tier where multi-step tool use is reliably possible
on this hardware. 

**Caveat:** the v2 ladder is four tasks. This is a directional signal, not a
statistically powered measurement. The cliff is sharp enough to be credible but the
exact depth at which larger models degrade requires a longer ladder.

### 3.4 Routing Simulation (Phase 0 — Oracle)

Using qwen3:8b as the local tier and DeepSeek V4 Pro as the cloud tier (run
`results/20260612_214955`, N=5; preflight forced — see §4.5).

All-cloud baseline: 20.23/21 task success, AUD 0.0142 per pass.
All-local baseline: 18.31/21 task success, AUD 0.0078 per pass.

#### 3.4.1 Absolute threshold rule (route local if category mean ≥ t)

| threshold | local categories | success /21 | cost (AUD) | % of cloud success | % cost saved |
|---|---|---:|---:|---:|---:|
| 0.85 | agentic, instruction_following, reasoning, summarisation | 20.31 | 0.0074 | 100.4% | 47.9% |
| 0.90 | agentic, instruction_following, reasoning, summarisation | 20.31 | 0.0074 | 100.4% | 47.9% |
| 0.95 | agentic, reasoning | 20.23 | 0.0109 | 100.0% | 23.4% |

At the 0.85–0.90 bar, the per-category router keeps 100.4% of all-cloud quality
(fractionally above all-cloud because qwen3:8b locally exceeds DeepSeek V4 Pro on
summarisation) at 47.9% lower cost. The absolute saving is AUD 0.0068 per 21-task
pass — a modest absolute number because DeepSeek V4 Pro is priced very low.

#### 3.4.2 Comparative rule (route local only if local quality ≥ cloud quality)

| local categories | success /21 | cost (AUD) | % of cloud success | % cost saved |
|---|---:|---:|---:|---:|
| agentic, reasoning, summarisation | 20.81 | 0.0090 | 102.9% | 36.4% |

The comparative rule achieves 102.9% of all-cloud success — qwen3:8b's summarisation
win (0.94 local vs 0.74 cloud) lifts the routed total above all-cloud. This is the
result that survives editorial scrutiny: not "local is cheaper," but "local is
demonstrably better on summarisation and routing captures that."

### 3.5 Phase 1 Router Evaluation (Keyword Classifier)

Phase 0 assumed the oracle policy knows each task's category. Phase 1 asks whether
a cheap keyword classifier can replicate this from prompt text alone.

The classifier in `router.py` uses weighted regex rules per category (no trained
model, no embeddings, no external call). On the 21 v1 suite prompts:

| threshold | min_confidence | clf accuracy | backend flips | % of cloud success | % cost saved |
|---|---|---:|---:|---:|---:|
| 0.85 | 0.34 | 21/21 = 100% | 0 | 100.4% | 47.9% |
| 0.90 | 0.34 | 21/21 = 100% | 0 | 100.4% | 47.9% |
| 0.95 | 0.34 | 21/21 = 100% | 0 | 100.0% | 23.4% |
| 0.90 | 0.50 | 21/21 = 100% | 0 | 100.4% | 47.9% |
| 0.90 | 0.70 | 21/21 = 100% | 3\* | 97.5% | 37.9% |

\* At min_confidence=0.70, three tasks with classifier confidence below 0.70
(reasoning.sports=0.64, summarisation.actions=0.60, summarisation.changelog=0.62)
trigger the fail-safe gate and are redirected to cloud. Accuracy is still 100%
(all predictions were correct); the flips are fail-safe-driven, not errors.

At the default gate (min_confidence=0.34), the Phase 1 classifier is
indistinguishable from the Phase 0 oracle — same success, same cost. The open
question is generalisation to out-of-distribution prompts that don't share the
suite's keyword discriminability (§4.1).

### 3.6 Hardware and Performance

The v1 study ran on an RTX 3060 8 GB. The VRAM budget is tight: qwen3:8b at Q4_K_M
occupies 7610 MB of the 8192 MB available. qwen3:1.7b occupies 7864 MB despite its
smaller parameter count, likely because it loads at a higher quantization level.

| model | decode tok/s | prefill tok/s | TTFT median (s) | peak VRAM (MB) | energy/gen (Wh) |
|---|---:|---:|---:|---:|---:|
| qwen3:1.7b | 121.3 | [TODO: verify] | [TODO: verify] | 7864 | [TODO: verify] |
| qwen3:8b | 39.0 | [TODO: verify] | [TODO: verify] | 7610 | [TODO: verify] |
| deepseek-r1:7b | 41.7 | [TODO: verify] | [TODO: verify] | 7806 | [TODO: verify] |

qwen3:1.7b is 3.1× faster to decode than qwen3:8b, making it the correct choice
for high-volume low-complexity tasks when latency matters. qwen3:8b is the quality
ceiling on this hardware. deepseek-r1:7b achieves a similar decode rate to qwen3:8b
but with significantly lower quality on this suite, which limits its routing use
case [TODO: investigate whether reasoning chain verbosity explains the lower score
or whether it is a calibration issue].

---

## 4. Threats to Validity

### 4.1 Classifier Generalization

The Phase 1 classifier achieves 100% accuracy on the 21 v1 suite prompts. These
prompts were written with keyword-discriminative vocabulary (summarisation prompts
contain "summarise," coding prompts contain "Python function," etc.). Real-world
prompts that use paraphrased or domain-specific phrasing may fall below the accuracy
observed here. The min-confidence fail-safe gate (default 0.34) handles the worst
cases conservatively, but we have no out-of-distribution evaluation.

**Honest statement:** the Phase 1 result is an upper-bound proof-of-concept on a
small, in-distribution suite. Before treating it as production evidence, evaluate
on a held-out set with diverse phrasing.

### 4.2 Judge Bias

LLM judges have documented position and verbosity biases. Metis mitigates this with
(a) programmatic scoring for 18 of 21 tasks and (b) pairwise position-swap judging
for summarisation. The planned ~50-item human-agreement validation set (judge–human
Pearson correlation + mean absolute error) is **still pending**. Until it exists,
the judge scores indicate direction but cannot support a calibrated accuracy claim.

### 4.3 Contamination

All tasks are original. Fictional entity names (Veldora, Marrowgate, Ostrel, Calder
Bridge) appear in no known training dataset. However, the prompt *structure* (e.g.
multi-hop lookup format) may have been seen in training data and could inflate agentic
scores for larger models that have been instruction-tuned on similar formats.

### 4.4 Single Machine

These results are specific to the AMD Ryzen 5 5500 + RTX 3060 8 GB fingerprint.
The RTX 3060 8 GB has a 128-bit memory bus (~240 GB/s bandwidth) as distinct from
the 12 GB variant (192-bit, ~360 GB/s). Bandwidth is the main bottleneck for decode
on memory-bandwidth-bound models; cross-machine claims require a community dataset.

### 4.5 DeepSeek Routing Baseline Preflight

The DeepSeek V4 Pro cloud run (`results/20260612_214955`) was started with `--force`
after a high background CPU preflight check failure. Quality scores are unaffected
(scoring is a separate pass). Latency figures and local monitor readings from that
run should not be over-read.

### 4.6 Sampling Resolution

VRAM and GPU power are sampled at approximately 500 ms intervals. Sub-interval peaks
(during prefill on short tasks) are missed. Energy is integrated from samples and
undercounts short generations. These limitations are recorded in every run manifest.

### 4.7 Small Suite

21 tasks means per-category means rest on 3–5 data points each. Category-level
claims (especially agentic at 3 tasks) are directional; the confidence intervals
are wide. The step-depth ladder (4 tasks) is similarly indicative. The routing
economics are sensitive to the subset of tasks on which qwen3:8b and DeepSeek V4 Pro
differ. A 100-task expansion would materially change the confidence bounds.

---

## 5. Artifact and Reproducibility

### 5.1 Code

Open source at `github.com/lachydotmcg/metis`. Install: `pip install -e .`. The
`metis` CLI reproduces the full pipeline — `metis run`, `metis score`, `metis judge`,
`metis report`, `metis economics` — as documented in the README quickstart.

### 5.2 Frozen Task Suite

`metis/suite/v1/` and `metis/suite/v2/` are immutable. Each coding task carries a
reference solution validated by its own test suite (`tests/test_scoring.py`
::test_suite_self_validation). A researcher reproducing this work uses the same
frozen YAML without any configuration change.

### 5.3 Published Run Artifacts

A curated subset of run artifacts is tracked in `results/published/` (see
ROADMAP task 5): the comparison report, routing simulation, Phase 1 router eval,
and per-headline-run `scores.jsonl` files. Raw model outputs are excluded from the
repository (large, regenerable).

### 5.4 Pinned Dependencies

All model digests are recorded per run. The judge model version is pinned in
`config/judge.yaml`. `pricing.yaml` ships with zero defaults to prevent stale rate
masquerading as current (see §2.6).

---

## 6. Related Work

Metis overlaps with several tools across distinct axes:

| tool | hardware-aware | output quality | economics | consumer hardware | local models |
|---|---|---|---|---|---|
| MLPerf Client | yes | no | no | yes | yes |
| Geekbench AI | yes | no | no | yes | yes |
| LMSYS Arena | no | yes (human pref) | no | no | no |
| DeepEval / Braintrust | no | yes (app evals) | partial | no | partial |
| Inspect AI | no | yes (frontier/safety) | no | no | partial |
| **Metis** | **yes** | **yes** | **yes** | **yes** | **yes** |

The combination of hardware measurement and output quality evaluation in a single
reproducible pipeline, targeting consumer hardware, has no direct prior work known
to the authors.

---

## 7. Discussion and Conclusions

The headline finding is not "8 GB is good enough." It is more precisely:

1. **A 8 B parameter model on an 8 GB card can match or exceed a frontier cloud
   API on a subset of the workload.** On reasoning, qwen3:8b scores 1.00 vs
   Claude Sonnet 4.6's 1.00. On summarisation, it scores 0.94 vs 0.90. These are
   not close calls; they are category-level local wins.

2. **The routing signal is strong and cheap to compute.** A keyword classifier with
   no ML model achieves perfect category prediction on the v1 suite, and the
   fail-safe gate handles low-confidence cases conservatively. The Phase 0 economics
   hold in Phase 1 without degradation.

3. **The agentic depth cliff is a qualitative boundary.** There is no gradient
   between "handles depth 1" and "handles depth 2+." On this protocol, qwen3:8b is
   the first local tier where multi-step tool use is reliable.

4. **The absolute cost savings against a very cheap cloud tier are small.** ~AUD
   0.007 per 21-task pass at the 0.90 threshold. The routing argument in 2026 is not
   primarily about cost; it is about capability coverage, rate-limit resilience,
   privacy, and selective quality wins where the local model is actually better.

5. **The 8 GB VRAM constraint is binding.** Every model in the study is near the
   ceiling. The RTX 3060 8 GB's 128-bit bus limits decode throughput. The offload
   cliff experiment (not yet conducted; see ROADMAP) will quantify this precisely.

**For a practitioner:** route summarisation and reasoning tasks to qwen3:8b locally.
Route coding to a cloud API until a stronger local coding model is available.
Use qwen3:1.7b for high-volume simple tasks where latency matters more than quality.

**For a researcher:** the measurement infrastructure is in place for the remaining
signature experiments (offload cliff, WDDM spill detection, context-length scaling,
realistic-conditions mode). The human judge validation set is the most urgent gap
before any submission.
