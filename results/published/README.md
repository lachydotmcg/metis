# Published Results

Curated subset of Metis run artifacts that tell the headline story.
Raw model outputs (`records.jsonl`) are excluded — regenerate them with `metis run`.

## Contents

### Routing

- **`routing_qwen3_8b_vs_deepseek_v4_pro.md`** — Phase 0 routing simulation (oracle policy).
  qwen3:8b local tier vs DeepSeek V4 Pro cloud tier. Threshold sweep 0.85/0.90/0.95
  and comparative rule. Key result: 100.4% of cloud success at 47.9% lower cost at
  the 0.90 threshold.

- **`router_eval_qwen3_8b_vs_deepseek_v4_pro.md`** — Phase 1 router evaluation.
  Keyword classifier on prompt text only. 100% accuracy on 21 v1 tasks. Threshold
  and min-confidence sweep.

### Comparison: local vs Claude Sonnet 4.6

- **`comparison_local_vs_claude/findings.md`** — anchored quality comparison:
  qwen3:8b reaches 87% of Claude's mean per-task quality; 81% of tasks clear the
  90%-of-Claude bar.
- **`comparison_local_vs_claude/comparison.json`** — raw comparison data (per-model
  metrics, coverage at threshold, per-category breakdown).

### Step-Depth Degradation

- **`step_depth/step_depth_findings.md`** — four-task agentic ladder result.
  qwen3:1.7b and deepseek-r1:7b break at depth 2; qwen3:8b matches Claude through
  depth 5.
- **`step_depth/step_depth.json`** — raw step-depth data.

### Context-Length Scaling (qwen3:8b)

- **`context_scale_qwen3_8b/report.md`** — decode speed and answer quality for v1
  reasoning tasks padded to 512 / 2k / 8k / 16k context, qwen3:8b, N=3. Decode holds
  near 40 tok/s through 8k then collapses to **9.8 tok/s at 16k with zero errors** —
  the Windows WDDM / KV-cache silent-spill cliff (RESEARCH.md §3). Quality stays 1.00,
  so the model still answers correctly, just ~4× slower once the KV cache overflows
  8 GB into shared system memory.
- **`context_scale_qwen3_8b/results.jsonl`** — per-generation metrics (context size,
  decode tok/s, wall time, score; no prompt text).

### Headline Local Run (2026-06-12, run 20260612_173212)

Three models (qwen3:1.7b, qwen3:8b, deepseek-r1:7b), N=5, 315 generations, 0 errors.
Machine: AMD Ryzen 5 5500 + RTX 3060 8 GB.

- **`headline_run_20260612_173212/report.md`** — human-readable report.
- **`headline_run_20260612_173212/scores.jsonl`** — per-generation scores (no raw outputs).
- **`headline_run_20260612_173212/judge_scores.jsonl`** — LLM judge scores for summarisation tasks.
- **`headline_run_20260612_173212/manifest.json`** — run metadata (suite version, models, sampler params).
- **`headline_run_20260612_173212/fingerprint.json`** — hardware fingerprint.
