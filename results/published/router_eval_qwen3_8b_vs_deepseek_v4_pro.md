# Phase 1 — Router Evaluation: qwen3:8b vs deepseek-v4-pro

**Generated:** 2026-06-13 (overnight agent)
**Local run:** `results/20260612_173212` (qwen3:8b, N=5)
**Cloud run:** `results/20260612_214955` (deepseek-v4-pro, N=5)
**Tasks:** 21 (shared by both runs)

---

## Headline: the keyword classifier achieves 100% accuracy on this suite

Every task's category was correctly predicted from prompt text alone with no access
to task IDs or labels. With the default min-confidence gate (0.34), zero backend
flips occurred at thresholds 0.85 and 0.90. At 0.95 the policy shifts (instruction
and summarisation move to cloud) but the classifier still routes perfectly.

---

## Threshold sweep (min_confidence = 0.34)

| threshold | policy (local categories) | clf accuracy | backend flips | clf success /21 | cost (AUD) | % of cloud success | % cost saved |
|---|---|---|---|---|---|---|---|
| 0.85 | agentic, instruction_following, reasoning, summarisation | 21/21 = 100% | 0 | 20.31 | 0.0074 | 100.4% | 47.9% |
| 0.90 | agentic, instruction_following, reasoning, summarisation | 21/21 = 100% | 0 | 20.31 | 0.0074 | 100.4% | 47.9% |
| 0.95 | agentic, reasoning | 21/21 = 100% | 0 | 20.23 | 0.0109 | 100.0% | 23.4% |

All-cloud baseline: 20.23 success, AUD 0.0142.
Oracle (Phase 0, known categories): 20.31 @ 0.85/0.90 threshold; 20.23 @ 0.95 threshold.

At 0.85 and 0.90 the classifier routing is **indistinguishable from the oracle**.
The policy map is stable between these thresholds because qwen3:8b's per-category
means already satisfy the 0.90 bar for agentic (1.00), instruction_following (0.90),
reasoning (1.00), and summarisation (0.94), but not coding (0.60).

---

## Min-confidence sensitivity (threshold = 0.90)

| min_confidence | backend flips | clf success /21 | cost (AUD) | % of cloud success | % cost saved |
|---|---|---|---|---|---|
| 0.34 (default) | 0 | 20.31 | 0.0074 | 100.4% | 47.9% |
| 0.50 | 0 | 20.31 | 0.0074 | 100.4% | 47.9% |
| 0.70 | 3 | 19.73 | 0.0088 | 97.5% | 37.9% |

With min_confidence ≥ 0.70, three tasks whose classifier scores fall below 0.70
(reasoning.sports conf=0.64, summarisation.actions conf=0.60, summarisation.changelog
conf=0.62) are redirected to cloud as a safety precaution — at the cost of 0.58
quality-points and an extra AUD 0.0014. This is the fail-safe gate working as
designed: it trades a small quality/cost penalty for routing conservatism on
ambiguous prompts. At the default gate of 0.34 all prompts clear it, so no penalty.

---

## Per-task detail (threshold=0.90, min_confidence=0.34)

| task | true | predicted | conf | oracle | routed |
|---|---|---|---|---|---|
| agentic.flaky_lookup | agentic | agentic | 1.00 | local | local |
| agentic.population_sum | agentic | agentic | 1.00 | local | local |
| agentic.revenue_per_resident | agentic | agentic | 0.88 | local | local |
| coding.balanced | coding | coding | 1.00 | cloud | cloud |
| coding.fix_clamp | coding | coding | 1.00 | cloud | cloud |
| coding.merge_intervals | coding | coding | 1.00 | cloud | cloud |
| coding.rle | coding | coding | 1.00 | cloud | cloud |
| coding.second_largest | coding | coding | 1.00 | cloud | cloud |
| instruction.capitals | instruction_following | instruction_following | 0.87 | local | local |
| instruction.json_meta | instruction_following | instruction_following | 1.00 | local | local |
| instruction.ocean_taboo | instruction_following | instruction_following | 1.00 | local | local |
| instruction.three_sentences | instruction_following | instruction_following | 1.00 | local | local |
| instruction.word_window | instruction_following | instruction_following | 1.00 | local | local |
| reasoning.calendar | reasoning | reasoning | 1.00 | local | local |
| reasoning.candles | reasoning | reasoning | 1.00 | local | local |
| reasoning.ladder | reasoning | reasoning | 1.00 | local | local |
| reasoning.sports | reasoning | reasoning | 0.64 | local | local |
| reasoning.tank | reasoning | reasoning | 1.00 | local | local |
| summarisation.actions | summarisation | summarisation | 0.60 | local | local |
| summarisation.changelog | summarisation | summarisation | 0.62 | local | local |
| summarisation.ferry | summarisation | summarisation | 1.00 | local | local |

---

## Outcome vs upper bound (threshold=0.90, min_confidence=0.34)

| routing | success /21 | cost (AUD) | cost/success |
|---|---|---|---|
| all-cloud | 20.23 | 0.0142 | 0.000703 |
| oracle (Phase 0) | 20.31 | 0.0074 | 0.000365 |
| classifier (Phase 1) | 20.31 | 0.0074 | 0.000365 |

- Quality lost to misclassification vs oracle: **0.00** task-points (0.0% of oracle success).
- Cost change from misclassification vs oracle: **+AUD 0.0000**.
- Classifier routing keeps **100.4%** of all-cloud quality at **47.9% lower cost**.

---

## Interpretation

The classifier closes the gap between Phase 0 (oracle routing) and Phase 1 (prompt-only
routing) completely on this suite. This is an upper-bound result on a 21-task suite
with discriminative prompts — each category is visually distinct enough that the
keyword rules fire cleanly. The real threat is out-of-distribution prompts (ambiguous
or mixed-category), which the min-confidence gate handles conservatively.

The research question is answered for this suite: a cheap keyword classifier can
predict task category with sufficient accuracy to realize the Phase-0 routing
economics with no quality loss. The remaining uncertainty is generalization to
prompts that don't look like the suite's training distribution.
