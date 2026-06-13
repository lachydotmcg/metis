# Step-Depth Degradation

Local run: `20260612_203254`. Cloud run: `20260612_210103`.

![Step-depth curve](step_depth_curve.svg)

| model | depth 1 | depth 2 | depth 3 | depth 5 | first depth below 90% |
|---|---:|---:|---:|---:|---:|
| qwen3:1.7b | 100% | 0% | 0% | 0% | 2 |
| qwen3:8b | 100% | 100% | 100% | 100% | >5 |
| deepseek-r1:7b | 100% | 0% | 0% | 0% | 2 |
| claude-sonnet-4-6 | 100% | 100% | 100% | 100% | >5 |

## Finding

`qwen3:1.7b` and `deepseek-r1:7b` both solve the one-lookup task but fall below the 90% success bar at depth 2. `qwen3:8b` matches Claude through depth 5 on this ladder.

This is the first crisp degradation result: for this protocol, the local 8B model is not merely better on average; it crosses a qualitative boundary where multi-step tool use becomes reliable.
