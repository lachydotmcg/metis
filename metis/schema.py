"""Versioned schema for Metis run artifacts.

Every line in records.jsonl is one generation:

    schema_version, run_id, ts, suite_version, task_id, category, repeat,
    model:    {name, digest, parameter_size, quantization_level, family, ...}
    backend:  {name, version, options}
    timings:  {wall_s, ttft_s, load_s, prompt_tokens, prompt_eval_s,
               output_tokens, eval_s, decode_tps, prefill_tps}
    monitor:  {samples, vram_peak_mb, vram_avg_mb, power_avg_w, power_max_w,
               temp_max_c, gpu_util_avg, ram_peak_mb, ram_avg_mb, cpu_avg_pct,
               energy_j, duration_s, gpu_source}
    output:   {content, thinking}
    agentic:  null | {final_answer, steps_used, max_steps, tool_calls,
                      valid_json_turns, invalid_turns, error_injected, transcript}
    error:    null | str

Bump rules: additive field = patch, rename/retype = minor, restructure = major.
The community-dataset plan depends on this discipline.
"""

SCHEMA_VERSION = "0.1.1"

REQUIRED_RECORD_FIELDS = (
    "schema_version", "run_id", "ts", "suite_version", "task_id", "category",
    "repeat", "model", "backend", "timings", "monitor", "output", "agentic",
    "error",
)


def validate_record(rec: dict) -> list[str]:
    return [f for f in REQUIRED_RECORD_FIELDS if f not in rec]
