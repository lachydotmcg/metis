"""Ollama backend over the local HTTP API.

Streaming is used so TTFT is a real wall-clock measurement. The final chunk
carries the runtime's own timing fields (nanoseconds): load_duration,
prompt_eval_count/duration, eval_count/duration. Reasoning models (qwen3,
deepseek-r1) stream `thinking` separately; it is captured and counted, never
discarded.
"""

import json
import time

import requests

from .base import Backend, GenResult

_NS = 1e9
# Only these keys go into Ollama's "options"; everything else in the options
# dict is harness-level (keep_alive, think) and handled separately.
_OLLAMA_OPTS = ("temperature", "seed", "num_ctx", "num_predict", "num_gpu")


class OllamaBackend(Backend):
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434",
                 timeout_s: int = 600):
        self.base = base_url.rstrip("/")
        self.timeout = timeout_s
        self.s = requests.Session()

    def version(self) -> str:
        try:
            r = self.s.get(f"{self.base}/api/version", timeout=10)
            return r.json().get("version", "?")
        except Exception as e:
            raise SystemExit(
                f"Cannot reach Ollama at {self.base} ({e}). Is it running?")

    def model_info(self, model: str) -> dict:
        info: dict = {"name": model}
        try:
            show = self.s.post(f"{self.base}/api/show",
                               json={"model": model}, timeout=30).json()
            d = show.get("details", {})
            info.update({
                "family": d.get("family"),
                "parameter_size": d.get("parameter_size"),
                "quantization_level": d.get("quantization_level"),
                "format": d.get("format"),
            })
        except Exception as e:
            info["show_error"] = str(e)
        try:
            tags = self.s.get(f"{self.base}/api/tags",
                              timeout=30).json().get("models", [])
            for t in tags:
                if model in (t.get("name"), t.get("model")):
                    info["digest"] = t.get("digest")
                    info["size_bytes"] = t.get("size")
        except Exception:
            pass
        return info

    def preload(self, model: str, keep_alive="15m") -> None:
        self.s.post(f"{self.base}/api/generate",
                    json={"model": model, "keep_alive": keep_alive},
                    timeout=self.timeout)

    def unload(self, model: str) -> None:
        self.s.post(f"{self.base}/api/generate",
                    json={"model": model, "keep_alive": 0}, timeout=120)

    def chat(self, model, messages, options, meta=None) -> GenResult:
        body: dict = {"model": model, "messages": messages, "stream": True}
        opts = {k: options[k] for k in _OLLAMA_OPTS
                if options.get(k) is not None}
        if opts:
            body["options"] = opts
        if options.get("keep_alive") is not None:
            body["keep_alive"] = options["keep_alive"]
        if options.get("think") is not None:
            body["think"] = options["think"]

        res = GenResult()
        t0 = time.perf_counter()
        first: float | None = None
        try:
            with self.s.post(f"{self.base}/api/chat", json=body,
                             stream=True, timeout=self.timeout) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        res.error = str(chunk["error"])
                        break
                    msg = chunk.get("message") or {}
                    piece = msg.get("content") or ""
                    thought = msg.get("thinking") or ""
                    if first is None and (piece or thought):
                        first = time.perf_counter()
                    res.content += piece
                    res.thinking += thought
                    if chunk.get("done"):
                        res.prompt_tokens = chunk.get("prompt_eval_count") or 0
                        res.output_tokens = chunk.get("eval_count") or 0
                        res.load_s = (chunk.get("load_duration") or 0) / _NS
                        res.prompt_eval_s = (chunk.get("prompt_eval_duration") or 0) / _NS
                        res.eval_s = (chunk.get("eval_duration") or 0) / _NS
        except Exception as e:
            res.error = f"{type(e).__name__}: {e}"
        res.wall_s = time.perf_counter() - t0
        res.ttft_s = (first - t0) if first is not None else 0.0
        return res
