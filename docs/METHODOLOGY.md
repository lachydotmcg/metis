# Methodology

What separates "research-grade" from "I benchmarked some models" is that every number comes with the conditions that produced it and an honest account of its error bars. These are the rules.

## 1. Reproducibility: pin everything

Recorded per run (in `manifest.json` / per-record):
- Model: name, **digest** (content hash from the registry), parameter size, quantization level, family
- Backend: name and version (Ollama silently changes behaviour across versions)
- Sampler: temperature (default 0), seed (default 1234), `num_ctx`, `num_predict` per task
- GPU offload: `num_gpu` if explicitly set; Ollama's automatic offload decision is otherwise in play and that fact is itself recorded
- `keep_alive` policy, `think` flag for reasoning models
- Hardware fingerprint: CPU model, core counts, RAM, GPU name/VRAM/driver, OS, Python, Metis version

## 2. Run protocol

- **Preflight quiesce check**: refuse to start if background CPU load >40% (override with `--force`, which is itself recorded).
- **Schedule: rotating block.** Full per-generation interleaving of models would be thermally fairest but pathological on consumer hardware: every generation would trigger a model load (30–60s on an 8GB card that fits one model at a time). Compromise: within each repeat round, run each model as a block over all tasks; rotate model order between rounds so no model always runs hottest. The trade-off is documented here precisely because it is a trade-off.
- **Repeats**: N≥5 for any number that gets published; report mean with 95% CI (t-distribution, small-n aware). Single-run numbers are for smoke tests only.
- **Warm/cold**: `load_duration` is captured per generation, so cold loads are identifiable (load_s > 0) and separable in analysis rather than averaged in silently.
- **Errors don't abort runs**: a failed generation is recorded with its error and scored 0; the run continues.

## 3. Metric definitions

| Metric | Definition | Caveat |
|---|---|---|
| TTFT | wall-clock from request to first streamed token (thinking tokens count: the user is waiting either way) | includes HTTP + runtime overhead; reported as user-experienced TTFT |
| Decode tok/s | `eval_count / eval_duration` from the runtime | runtime-reported; cross-check against wall time |
| Prefill tok/s | `prompt_eval_count / prompt_eval_duration` | matters for RAG/long-context; different bottleneck (compute) than decode (memory bandwidth) |
| Peak VRAM | max of ~500ms samples during generation | misses sub-interval spikes |
| Energy | ∑ power × Δt over samples, per generation | undercounts short generations; sampling resolution noted in reports |
| Output tokens | `eval_count` (thinking + visible) | thinking share also stored per record |

## 4. Quality scoring: programmatic first, judge last

**Tier 1 — programmatic ground truth (18 of 21 v1 tasks):**
- Reasoning: forced answer format ("Answer: <x>"), exact numeric/choice match
- Coding: extract fenced code, execute against test cases in an isolated subprocess (`python -I`, 20s timeout). Every coding task carries a reference solution (`oracle_code`) and the test suite is validated against it, so a broken test can't masquerade as a model failure.
- Instruction following: IFEval-style verifiable constraints (word counts, sentence counts, forbidden words, JSON schema, alphabetical ordering). Score = fraction of constraints passed.

**Tier 2 — LLM-as-judge (summarisation faithfulness):**
- Pinned cloud judge model + version, recorded like any other dependency
- Pairwise vs reference with **position swap** (judges have position bias) and a rubric, not a bare 1–10
- Validated against ~50 human-labeled items; judge–human agreement reported in the paper. This table is what separates "methodology" from "I asked a model to grade it."
- Judge config in `config/judge.yaml`; scoring is a re-runnable pass, so a judge upgrade never invalidates collected outputs.

**Reasoning-model handling**: `thinking` content is stored but stripped before scoring; only the visible answer is judged.

## 5. Contamination policy

All 21 tasks are original, written for this suite. Agentic tasks query a fictional corpus (Veldora, Marrowgate, Ostrel, the Calder Bridge) so correct answers cannot exist in any training set. Public benchmark items are never imported. Suite versions are frozen; a prompt edit is a new version.

## 6. Agentic protocol

Deterministic tool loop: the model gets `lookup(query)` and `calc(expression)` against a fixed corpus and a safe AST-based calculator. Strict JSON turn format. Captured per task: success, steps used vs budget, tool-call validity rate, invalid-JSON turns, and recovery behaviour (one task injects a transient tool failure on the first call and measures whether the model retries). Planned analysis: success rate vs required step depth.

## 7. Economics: honest or not at all

- Local inference is **not free**: measured energy × configurable tariff (+ optional hardware amortisation per hour). Defaults to a placeholder tariff that must be edited.
- A consumer subscription is **not a bag of API tokens**; comparisons run against per-token API rates, which live in `config/pricing.yaml` and default to zero so stale numbers can't silently masquerade as current ones. The tool refuses to print a break-even until rates are configured.
- Latency belongs in the value judgment: a local model that ties on quality but generates at 20 tok/s still loses on long outputs. Reports show quality and speed side by side; the routing interpretation is per-category.

## 8. Code execution caveat

Scoring coding tasks executes model-generated code on the host (isolated mode, 20s timeout, no sandbox beyond that). This is standard practice for code benchmarks but is a real risk surface; `--no-code-exec` skips these scorers and marks them unscored. A proper sandbox is on the roadmap.

## 9. Known limitations (v0.1)

- Judge tier is implemented, but the ~50-item human-validation set and judge-human agreement table are still pending
- No llama.cpp backend yet, so no controlled offload sweep (`num_gpu` passthrough works on Ollama as a partial substitute)
- WDDM silent-spill detection not implemented (design in RESEARCH.md)
- Energy/VRAM sampling at ~500ms resolution
- Windows-first; fingerprinting falls back gracefully but is untested on Linux/macOS
