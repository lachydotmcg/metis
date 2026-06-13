# Metis report — 20260612_173212

- Run `20260612_173212` — suite v1.0, 5 repeats, schedule rotating-block, backend ollama 0.30.7.
- Machine: AMD Ryzen 5 5500 | 31.9GB RAM | NVIDIA GeForce RTX 3060 8192 MiB (driver 596.49) | fingerprint `c6ecef2c8b5c`.
- Sampler: temperature=0.0, seed=1234, num_ctx=4096.
- 30 generation(s) use judge scores from judge_scores.jsonl; tier-1 scores remain in scores.jsonl.

## Models

| model | params | quant | digest |
|---|---|---|---|
| qwen3:1.7b | 2.0B | Q4_K_M | 8f68893c685c |
| qwen3:8b | 8.2B | Q4_K_M | 500a1f067a9f |
| deepseek-r1:7b | 7.6B | Q4_K_M | 755ced02ce7b |

## Quality (mean score ± 95% CI)

| model | overall | agentic | coding | instruction_following | reasoning | summarisation |
|---|---|---|---|---|---|---|
| qwen3:1.7b | 0.77 ± 0.07 | 0.33 ± 0.27 | 0.60 ± 0.21 | 0.95 ± 0.04 | 1.00 ± 0.00 | 0.81 ± 0.08 |
| qwen3:8b | 0.87 ± 0.06 | 1.00 ± 0.00 | 0.60 ± 0.21 | 0.90 ± 0.08 | 1.00 ± 0.00 | 0.94 ± 0.04 |
| deepseek-r1:7b | 0.65 ± 0.08 | 0.00 ± 0.00 | 0.80 ± 0.17 | 0.73 ± 0.10 | 0.80 ± 0.17 | 0.69 ± 0.14 |

## Coverage at quality threshold (fraction of tasks with mean score ≥ t)

| model | t=0.5 | t=0.7 | t=0.9 |
|---|---|---|---|
| qwen3:1.7b | 81% | 81% | 67% |
| qwen3:8b | 90% | 86% | 81% |
| deepseek-r1:7b | 71% | 52% | 52% |

## Performance

| model | decode tok/s | prefill tok/s | TTFT median (s) | peak VRAM (MB) | avg power (W) | energy (Wh) | errors |
|---|---|---|---|---|---|---|---|
| qwen3:1.7b | 121.3 ± 4.4 | 4163 ± 523 | 0.25 | 7864 | 132 | 32.25 | 0 |
| qwen3:8b | 39.0 ± 0.8 | 1621 ± 205 | 0.35 | 7610 | 156 | 110.91 | 0 |
| deepseek-r1:7b | 41.7 ± 0.8 | 1654 ± 241 | 0.31 | 7806 | 154 | 86.38 | 0 |

## Weakest tasks per model

| model | lowest mean scores |
|---|---|
| qwen3:1.7b | agentic.population_sum (0.00), agentic.flaky_lookup (0.00), coding.second_largest (0.00) |
| qwen3:8b | coding.second_largest (0.00), coding.fix_clamp (0.00), instruction.word_window (0.50) |
| deepseek-r1:7b | agentic.population_sum (0.00), agentic.revenue_per_resident (0.00), agentic.flaky_lookup (0.00) |
