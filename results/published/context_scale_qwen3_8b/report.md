# Context-length scaling — qwen3:8b

Quality and speed for v1 reasoning tasks padded to fill each context window size. Filler prepended before the actual task; fill fraction = 0.9.

- model: qwen3:8b | repeats: 3 | num_predict: 2048 | temperature: 0 | seed: 1234
- preflight: {'checked': True, 'cpu_pct': 12.4, 'ram_available_gb': 15.0}

| context | tasks | score (mean) | decode tok/s | wall_s (mean) | errors |
|---|---|---|---|---|---|
| 512 | 5 | 1.00 | 41.4 | 19.2 | 0 |
| 2048 | 5 | 1.00 | 40.0 | 13.7 | 0 |
| 8192 | 5 | 1.00 | 36.5 | 16.8 | 0 |
| 16384 | 5 | 1.00 | 9.8 | 53.3 | 0 |

Reading the curve: decode tok/s should fall as context grows (KV cache pressure on an 8GB card), and a sharp drop with no error is the Windows WDDM silent-spill signature (RESEARCH.md §3). Errors at the largest sizes are themselves a finding: the context did not fit. Quality is a secondary check that the padded task is still answered, not a coverage claim.