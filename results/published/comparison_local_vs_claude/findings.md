# Metis Findings Draft

Local run: `20260612_173212`. Cloud reference: `20260612_201339` using `claude-sonnet-4-6`.

## Headline

`qwen3:8b` is the strongest local model on Metis v1: 87% of Claude's mean per-task quality and 81% of tasks at at least 90% of Claude's task score.
`qwen3:1.7b` is the speed play: 121.3 tok/s and 71% anchored coverage at the same 90%-of-Claude bar.

Important ceiling caveat: Claude Sonnet 4.6 is near the top of the Metis v1 score
scale. These anchored numbers measure local coverage of this suite envelope; they
do not mean qwen3:8b is only 13% below Claude's general intelligence, nor that a
stronger model also scoring 100% would be equivalent to Sonnet.

## Charts

![Coverage curve](coverage_curve.svg)

![Quality vs speed](quality_vs_speed.svg)

## Comparison Table

| model | mean quality | mean vs Claude | tasks >=90% of Claude | absolute coverage@0.9 | decode tok/s | peak VRAM MB |
|---|---:|---:|---:|---:|---:|---:|
| qwen3:1.7b | 0.77 | 78% | 71% | 67% | 121.3 | 7864 |
| qwen3:8b | 0.87 | 87% | 81% | 81% | 39.0 | 7610 |
| deepseek-r1:7b | 0.65 | 66% | 52% | 52% | 41.7 | 7806 |
| claude-sonnet-4-6 | 0.98 | 100% | 100% | 90% | 35.3 | n/a |

## Interpretation

The useful claim is no longer just an absolute benchmark score. It is an anchored
routing and coverage claim: on this RTX 3060 8GB machine, the best local model
clears a 90%-of-Claude bar on most of the frozen suite, while the small model
offers much higher local throughput for simpler work. Frontier-model ranking needs
harder tasks with more headroom.

## Caveats

- The judge tier is implemented and applied here, but the planned human-label validation set is still pending.
- Claude is near the v1 ceiling, so local-vs-Claude percentages should not be read
  as a general intelligence ratio.
- API speed includes network/provider latency; local speed is measured on this machine.
- API prices are not stored in these artifacts unless config/pricing.yaml is explicitly configured.
