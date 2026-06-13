"""Oracle mock backend: answers every task correctly with fake timings.

Dev tool only. It exercises the full pipeline (runner -> records -> scoring ->
report) without a model: the oracle should score ~1.0 everywhere, so anything
below that is a harness bug, not a model result.
"""

import json

from .base import Backend, GenResult


class MockBackend(Backend):
    name = "mock"

    def version(self) -> str:
        return "mock-1"

    def model_info(self, model: str) -> dict:
        return {"name": model, "family": "mock", "parameter_size": "0B",
                "quantization_level": "none", "digest": "mock"}

    def chat(self, model, messages, options, meta=None) -> GenResult:
        task = meta or {}
        spec = task.get("scoring", {})
        kind = spec.get("type")
        if kind in ("numeric_exact", "choice_exact"):
            content = f"Answer: {spec.get('expected')}"
        elif kind == "agentic_final":
            content = json.dumps({"final_answer": str(spec.get("expected"))})
        elif kind == "code_tests":
            content = "```python\n" + task.get("oracle_code", "pass") + "\n```"
        else:
            content = task.get("oracle_text", "Mock response with no oracle text.")
        n = max(1, len(content.split()))
        return GenResult(
            content=content, prompt_tokens=50, output_tokens=n,
            load_s=0.1, prompt_eval_s=0.05, eval_s=n / 100,
            ttft_s=0.15, wall_s=0.2 + n / 100,
        )
