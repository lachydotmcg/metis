# Research framing

## The gap

Tools that profile hardware (MLPerf Client, Geekbench AI) report tokens/sec and never ask whether the output was any good. Tools that evaluate quality (LMSYS Arena, DeepEval, Braintrust, Inspect AI) assume the model is an API endpoint and know nothing about the silicon underneath or the cost per answer. Metis sits in the intersection: **quality-adjusted performance per dollar on consumer hardware**, in one reproducible run.

## Research question

> How much frontier capability fits in 8GB? Quality-adjusted cost frontiers for consumer-hardware LLM inference.

Operationalised: for a fixed machine and a fixed task suite, what fraction of tasks can local models complete at acceptable quality, how fast, at what energy cost, and where is the break-even against cloud API pricing?

## Headline metric: coverage at a quality threshold

A leaderboard says "model X scored 0.68." The decision-grade version anchors quality to a reference (eventually a cloud baseline run on the same suite) and reports:

**coverage(t) = fraction of tasks where the model's mean score ≥ t**

Plotted as a curve over t (like recall@k), so no single arbitrary cutoff has to be defended. Two consequences:

1. The economics stop being vibes: "this machine covers 62% of the workload at the 0.9 quality bar, worth $X/month at current API rates."
2. The benchmark's output doubles as a **routing policy**: task category → cheapest local model that clears the bar, else escalate to the API.

## Signature experiments

1. **The 8GB frontier.** Sweep quant level × model size (8B Q6 vs 14B Q3 vs 7B Q8...) and find the best achievable quality inside the VRAM budget, per task category. This is the question every mid-GPU owner has and nobody answers rigorously.
2. **The offload cliff.** Map tokens/sec as GPU layers decrease and the model spills to CPU/RAM. Everyone knows it's bad; publish the curve.
3. **Windows silent spill.** WDDM overflows VRAM into shared system memory instead of erroring, so a model "fits" but runs at a third of the speed. Detect it (NVML shared-memory usage + a perf-cliff heuristic) and flag it in reports.
4. **Bandwidth efficiency.** Decode is memory-bandwidth-bound, so (model bytes × tokens/sec) ÷ card bandwidth gives % of theoretical. Motivating example: the 8GB RTX 3060 has a 128-bit bus (~240GB/s) vs the 12GB's 192-bit (~360GB/s). Same product name, different ceiling. This is why fingerprinting matters.
5. **Step-depth degradation.** Agentic success rate vs required step count (1, 2, 3, 5). Small models fall off a cliff; where, per model, is a publishable curve.
6. **Context-length scaling.** Quality and speed at 512/2k/8k/16k context. KV cache eats an 8GB card fast.
7. **Realistic-conditions mode.** Re-run the suite while a synthetic load occupies RAM (the "40 Chrome tabs" scenario). Every other benchmark assumes a pristine machine; nobody using local AI has one.

## Positioning vs existing tools

| Tool | Hardware-aware | Output quality | Economics | Consumer hardware |
|---|---|---|---|---|
| MLPerf Client | yes | no | no | yes |
| Geekbench AI | yes | no | no | yes |
| LMSYS Arena | no | yes (human pref) | no | no |
| DeepEval / Braintrust / Phoenix | no | yes (app evals) | partial | no |
| Inspect AI | no | yes (frontier/safety) | no | no |
| **Metis** | **yes** | **yes** | **yes** | **yes** |

## Paper skeleton

1. Introduction: the gap, the research question
2. Methodology: suite design, capture protocol, scoring tiers, judge validation (see METHODOLOGY.md)
3. Results: coverage curves, the 8GB frontier, offload cliff, performance tables, break-even analysis
4. Threats to validity (below)
5. Artifact: open-source engine + versioned suite + raw run data

## Threats to validity (name them before reviewers do)

- **Judge bias**: LLM judges have position and verbosity biases. Mitigation: programmatic ground truth for 18 of 21 tasks; pairwise judging with position swap; human-agreement validation set (~50 items) with reported agreement.
- **Contamination**: public benchmark items live in training data. Mitigation: every task is original; agentic tasks use fictional entities (Veldora, Marrowgate, Ostrel) so the answer cannot be in any training set.
- **Single machine**: results are per-fingerprint by design; the cross-machine claim needs the community dataset (opt-in uploads, versioned schema).
- **Sampling resolution**: VRAM/power sampled at ~500ms can miss brief spikes; energy is integrated from samples and undercounts short generations.
- **TTFT includes HTTP and runtime overhead**, not pure model latency. Reported as user-experienced TTFT, which is the honest framing.
