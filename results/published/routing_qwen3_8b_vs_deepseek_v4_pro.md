# Phase 0 - threshold sweep

local run : results\20260612_173212
local model : qwen3:8b
cloud run : results\20260612_214955
cloud model : deepseek-v4-pro
tasks     : 21 (shared by both runs)

all-cloud: success 20.23/21, cost AUD 0.0142, cost/success 0.000703
all-local: success 18.31/21, cost AUD 0.0078, cost/success 0.000424

| threshold | local cats | success | cost | cost/success | % of cloud success | % cost saved |
|---|---|---|---|---|---|---|
| 0.85 | agentic,instruction_following,reasoning,summarisation | 20.31 | 0.0074 | 0.000365 | 100.4% | 47.9% |
| 0.9 | agentic,instruction_following,reasoning,summarisation | 20.31 | 0.0074 | 0.000365 | 100.4% | 47.9% |
| 0.95 | agentic,reasoning | 20.23 | 0.0109 | 0.000539 | 100.0% | 23.4% |

## Comparative rule: route local when local >= cloud

| local cats | success | cost | cost/success | % of cloud success | % cost saved |
|---|---:|---:|---:|---:|---:|
| agentic,reasoning,summarisation | 20.81 | 0.0090 | 0.000434 | 102.9% | 36.4% |

## Category means (local)
- agentic: local 1.000 | cloud 1.000
- coding: local 0.600 | cloud 1.000
- instruction_following: local 0.900 | cloud 1.000
- reasoning: local 1.000 | cloud 1.000
- summarisation: local 0.936 | cloud 0.743