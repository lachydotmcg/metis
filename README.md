# Metis

Research-grade benchmarking for local LLMs: **quality × hardware × dollars**, measured on the machine you actually own.

Existing tools measure how fast hardware runs models (MLPerf Client, Geekbench AI) or how good model outputs are (LMSYS Arena, DeepEval, Braintrust), but never both at once, and never what the difference is worth in money. Metis runs a frozen, versioned task suite against local models, captures hardware behaviour while they run, scores output quality, and reports capability coverage and break-even economics.

Named for the Greek titaness of practical wisdom and cunning counsel. Fittingly for a tool about model capability, she was swallowed by something bigger and kept advising from the inside.

## What it does

- **Hardware fingerprinting** per run (CPU, RAM, GPU, VRAM, driver) so every result is machine-aware and comparable across machines
- **Frozen task suite v1.0** (21 original tasks): reasoning, coding, summarisation, instruction following, and multi-step agentic tool use
- **Full capture**: time-to-first-token (streamed, wall-clock), decode and prefill tokens/sec, load time, peak VRAM, GPU power and temperature, integrated energy per generation
- **Layered scoring**: programmatic ground truth first (code execution against tests, exact answers, verifiable constraints), LLM-as-judge reserved for what can't be checked mechanically
- **Reports** in markdown and HTML, plus break-even economics against configurable API pricing (local electricity cost included, because local is not free)

## Status

v0.1.1 — headless engine working end to end (run → score → judge → report → economics) against Ollama and cloud reference APIs. No GUI yet, by design: see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Roadmap in [docs/ROADMAP.md](docs/ROADMAP.md).

## Results

On a single **RTX 3060 8 GB** machine (AMD Ryzen 5 5500, 31.9 GB RAM):

**qwen3:8b reaches 87% of Claude Sonnet 4.6's mean per-task quality on Metis v1**,
clearing a 90%-of-Claude bar on 81% of tasks. This is a suite-coverage result,
not an intelligence-ratio claim: Claude is near the v1 ceiling, so stronger cloud
models could also score ~100% without being equivalent. Within this suite,
reasoning and summarisation are local strengths; coding remains the local weak
point (0.60 vs 1.00).

A per-category routing policy (local for reasoning, summarisation, agentic, and
instruction-following; cloud for coding) keeps **100.4% of all-cloud task success
at 47.9% lower cost** against a DeepSeek V4 Pro baseline. A keyword classifier
routing on prompt text alone reproduces the oracle routing with **100% accuracy** on
the v1 suite and zero backend flips.

The agentic step-depth ladder is the starkest finding: qwen3:1.7b and deepseek-r1:7b
handle a single tool-call, then break completely at depth 2. **qwen3:8b reaches the
same measured ceiling as Claude through depth 5** - the first local tier where
multi-step tool use is reliable on this protocol.

Context length has its own cliff: qwen3:8b decodes near 40 tok/s out to 8k context,
then **drops to ~10 tok/s at 16k with no error** — the KV cache spilling 8 GB of VRAM
into shared system memory (Windows WDDM silent spill). It still answers correctly, just
~4× slower.

Published artifacts in [`results/published/`](results/published/):
- [`routing_qwen3_8b_vs_deepseek_v4_pro.md`](results/published/routing_qwen3_8b_vs_deepseek_v4_pro.md) — Phase 0 routing simulation
- [`router_eval_qwen3_8b_vs_deepseek_v4_pro.md`](results/published/router_eval_qwen3_8b_vs_deepseek_v4_pro.md) — Phase 1 classifier eval
- [`comparison_local_vs_claude/findings.md`](results/published/comparison_local_vs_claude/findings.md) — local vs Claude quality comparison
- [`step_depth/step_depth_findings.md`](results/published/step_depth/step_depth_findings.md) — agentic step-depth degradation
- [`context_scale_qwen3_8b/report.md`](results/published/context_scale_qwen3_8b/report.md) — context-length scaling: the 16k KV-cache spill cliff
- [`headline_run_20260612_173212/report.md`](results/published/headline_run_20260612_173212/report.md) — headline run report (qwen3:1.7b, qwen3:8b, deepseek-r1:7b, N=5)

## Quickstart

```powershell
pip install -e .
Copy-Item .env.example .env           # then edit .env with API keys if needed
metis fingerprint                     # what machine am I?
metis suite                           # list the task suite
metis run --models qwen3:1.7b,qwen3:8b --repeats 5
metis score results\<run_dir>
metis judge results\<run_dir>          # optional; requires pinned config\judge.yaml
metis report results\<run_dir>
metis economics results\<run_dir>     # configure config\pricing.yaml first
```

`metis run --backend mock --models oracle --repeats 1` runs the whole pipeline with an oracle backend that returns known-good answers. Use it to verify the harness itself: the oracle should score ~1.0 everywhere.

`metis run --backend cloud --cloud-provider openai --models <pinned-model>` runs the same suite against a cloud reference model. Cloud API keys are read from environment variables and the resolved backend settings are recorded in the run manifest.

For Anthropic, put `ANTHROPIC_API_KEY=...` in `.env` at the project root or set it in your shell. The key name used by the judge is configured in `config\judge.yaml`.

## Layout

```
metis/            the engine (headless, importable, CLI via `metis`)
  backends/       Ollama, cloud API, mock; llama.cpp server planned
  suite/v1/       frozen task suite v1.0 (YAML)
  scoring/        programmatic scorers + tier-2 judge pass
docs/             research framing, architecture, methodology, roadmap
config/           pricing + judge configuration (edit these, never the code)
results/          run artifacts (gitignored): records.jsonl, scores.jsonl, reports
HANDOFF.md        continuation prompt for the next agent/model working on this
```

## Design rules (the short version)

1. The engine is headless. Anything visual reads JSON artifacts; nothing visual ever measures.
2. Collection and scoring are separate passes. Raw outputs are always stored, so scoring can be re-run without re-running inference.
3. Everything that could move a number gets recorded: model digest, quant level, backend version, sampler params, context size, GPU state.
4. Prices live in config files, never in code. Rates change; code shouldn't rot.
5. The task suite is versioned and frozen. Changing a prompt means a new suite version, not an edit.
