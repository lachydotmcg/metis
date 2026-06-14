# Router OOD robustness — out-of-distribution prompts

Hand-written prompts that straddle categories or use unusual phrasing (no suite prompts, no model inference). This measures honest degradation from the best-case 100% the classifier scores on the discriminative v1 prompts.

prompts            : 22
min_confidence     : 0.34
classification acc : 9/22 = 40.9%
fail-safe rate     : 12/22 = 54.5% (low-confidence guesses routed to cloud)
silent misroutes   : 5/22 = 22.7% (confident AND wrong — the gate cannot catch these)

## Accuracy by true category

| category | correct / n |
|---|---|
| agentic | 2/4 |
| coding | 1/4 |
| summarisation | 1/5 |
| instruction_following | 1/4 |
| reasoning | 4/5 |

| true | predicted | conf | fail-safe | result |
|---|---|---|---|---|
| reasoning | reasoning | 0.00 | yes | ok |
| reasoning | reasoning | 0.00 | yes | ok |
| reasoning | reasoning | 0.00 | yes | ok |
| reasoning | reasoning | 0.00 | yes | ok |
| coding | coding | 1.00 |  | ok |
| coding | reasoning | 0.00 | yes | caught (->cloud) |
| coding | reasoning | 0.00 | yes | caught (->cloud) |
| coding | reasoning | 0.00 | yes | caught (->cloud) |
| summarisation | reasoning | 0.00 | yes | caught (->cloud) |
| summarisation | summarisation | 1.00 |  | ok |
| summarisation | reasoning | 0.00 | yes | caught (->cloud) |
| summarisation | coding | 1.00 |  | SILENT MISROUTE |
| instruction_following | reasoning | 0.00 | yes | caught (->cloud) |
| instruction_following | coding | 1.00 |  | SILENT MISROUTE |
| instruction_following | coding | 1.00 |  | SILENT MISROUTE |
| instruction_following | instruction_following | 1.00 |  | ok |
| agentic | agentic | 1.00 |  | ok |
| agentic | reasoning | 0.00 | yes | caught (->cloud) |
| agentic | reasoning | 0.00 | yes | caught (->cloud) |
| agentic | agentic | 1.00 |  | ok |
| summarisation | coding | 0.50 |  | SILENT MISROUTE |
| reasoning | instruction_following | 0.50 |  | SILENT MISROUTE |

Reading it: the fail-safe converts most misclassifications into safe (cloud) routes at a small cost premium; the silent-misroute rate is the real exposure, since those are routed by a confident but wrong guess.
