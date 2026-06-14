"""llama.cpp server backend (llama-server, OpenAI-compatible endpoint).

Talks to a running `llama-server` over its `/v1/chat/completions` endpoint, the
same OpenAI-compatible shape the cloud backend uses, but loopback and unauthed.

Why this backend exists: it gives Metis controlled `n_gpu_layers`. Unlike a
per-request sampler knob, `n_gpu_layers` is a *server launch* parameter
(`llama-server --n-gpu-layers N`), so the offload-cliff sweep (RESEARCH/ROADMAP)
launches one server per layer count and points this backend at it. The backend
therefore RECORDS the layer count it was told the server was launched with (and
whatever `/props` reports) so every run captures the knob, even though it cannot
change it per request.

llama-server streams an OpenAI-style SSE plus a llama.cpp-specific `timings`
object in the final chunk (prompt_ms / predicted_ms / prompt_n / predicted_n).
When present we use it for real prefill/decode seconds — exactly what the sweep
needs — and fall back to wall time and a word count when it is not.
"""

import time

import requests

from .base import Backend, GenResult

# Per-request knobs we forward (everything else in options is harness-level or a
# server-launch concern like n_gpu_layers / n_ctx and is handled separately).
_LLAMACPP_OPTS = ("temperature", "seed")


def build_body(model: str, messages: list[dict], options: dict) -> dict:
    """Build the OpenAI-compatible request body. Pure (no I/O) so the
    request-construction path is unit-testable."""
    body: dict = {
        "model": model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if options.get("num_predict") is not None:
        body["max_tokens"] = options["num_predict"]
    for k in _LLAMACPP_OPTS:
        if options.get(k) is not None:
            body[k] = options[k]
    return body


def consume_stream(line_iter, res: GenResult):
    """Parse an OpenAI-style SSE line iterator into `res`, also reading
    llama.cpp's `timings` block when present. Returns the perf_counter timestamp
    of the first content token (or None). Pure parsing — no network — so the
    response-parsing path is unit-testable with synthetic lines."""
    import json
    first = None
    for raw in line_iter:
        if not raw:
            continue
        line = raw.strip() if isinstance(raw, str) else raw.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        chunk = json.loads(payload)
        usage = chunk.get("usage") or {}
        if usage:
            res.prompt_tokens = usage.get("prompt_tokens") or res.prompt_tokens
            res.output_tokens = usage.get("completion_tokens") or res.output_tokens
        timings = chunk.get("timings") or {}
        if timings:
            if timings.get("prompt_ms") is not None:
                res.prompt_eval_s = timings["prompt_ms"] / 1000.0
            if timings.get("predicted_ms") is not None:
                res.eval_s = timings["predicted_ms"] / 1000.0
            if timings.get("prompt_n"):
                res.prompt_tokens = timings["prompt_n"]
            if timings.get("predicted_n"):
                res.output_tokens = timings["predicted_n"]
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        piece = delta.get("content") or ""
        if piece:
            if first is None:
                first = time.perf_counter()
            res.content += piece
    return first


class LlamaCppBackend(Backend):
    name = "llamacpp"

    def __init__(self, base_url: str = "http://localhost:8080",
                 n_gpu_layers: int | None = None, timeout_s: int = 600):
        self.base = base_url.rstrip("/")
        # The value the server was LAUNCHED with (recorded, not enforced here).
        self.n_gpu_layers = n_gpu_layers
        self.timeout = timeout_s
        self.s = requests.Session()

    def version(self) -> str:
        last = None
        for _ in range(2):
            try:
                r = self.s.get(f"{self.base}/props", timeout=10)
                j = r.json()
                build = j.get("build_info")
                if isinstance(build, str) and build:
                    return f"llama.cpp {build}"
                return "llama.cpp"
            except Exception as e:
                last = e
        # /props can be disabled on some builds; a healthy /health still counts.
        try:
            self.s.get(f"{self.base}/health", timeout=10)
            return "llama.cpp"
        except Exception:
            pass
        raise SystemExit(
            f"Cannot reach llama.cpp server at {self.base} ({last}). "
            f"Is llama-server running?")

    def _props(self) -> dict:
        """Best-effort read of server knobs. Returns {} if unavailable."""
        try:
            j = self.s.get(f"{self.base}/props", timeout=10).json()
        except Exception:
            return {}
        dgs = j.get("default_generation_settings") or {}
        out: dict = {}
        for k in ("model", "n_ctx", "n_gpu_layers"):
            if j.get(k) is not None:
                out[k] = j[k]
            elif dgs.get(k) is not None:
                out[k] = dgs[k]
        return out

    def settings(self) -> dict:
        d: dict = {"base_url": self.base}
        if self.n_gpu_layers is not None:
            d["n_gpu_layers"] = self.n_gpu_layers
        props = self._props()
        if props:
            d["server_props"] = props
        return d

    def model_info(self, model: str) -> dict:
        info: dict = {
            "name": model,
            "family": "llama.cpp",
            "quantization_level": "gguf",
        }
        if self.n_gpu_layers is not None:
            info["n_gpu_layers"] = self.n_gpu_layers
        props = self._props()
        if props:
            info["server_props"] = props
            if props.get("model"):
                info["model_path"] = props["model"]
            if props.get("n_ctx") is not None:
                info["n_ctx"] = props["n_ctx"]
        return info

    def chat(self, model, messages, options, meta=None) -> GenResult:
        body = build_body(model, messages, options)
        res = GenResult()
        t0 = time.perf_counter()
        first = None
        try:
            with self.s.post(f"{self.base}/v1/chat/completions", json=body,
                             stream=True, timeout=self.timeout) as r:
                if getattr(r, "status_code", 200) >= 400:
                    res.error = f"HTTP {r.status_code}: {(r.text or '')[:500]}"
                    res.wall_s = time.perf_counter() - t0
                    return res
                first = consume_stream(r.iter_lines(decode_unicode=True), res)
        except Exception as e:
            res.error = f"{type(e).__name__}: {e}"
        res.wall_s = time.perf_counter() - t0
        res.ttft_s = (first - t0) if first is not None else 0.0
        # Fall back to wall time when the server omits timings, and to a word
        # count when it omits usage, so downstream tok/s is never divide-by-zero.
        if res.eval_s <= 0:
            res.eval_s = res.wall_s
        if not res.output_tokens:
            res.output_tokens = len(res.content.split())
        return res
