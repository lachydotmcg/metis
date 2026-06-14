"""Cloud API backend using the same interface as local runtimes.

The backend deliberately records resolved provider/base URL/API-version knobs
while reading credentials only from environment variables.
"""

import json
import os
import pathlib
import time

import requests

from .base import Backend, GenResult

DEFAULTS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "api_version": None,
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "api_version": "2023-06-01",
    },
}

_OPENAI_OPTS = ("temperature", "seed")


def _is_unsupported_param_error(msg: str) -> bool:
    """True when a cloud error looks like 'this model rejects temperature/seed'
    (some reasoning models 400 on sampling params). Requires BOTH a param
    mention and an unsupported/400 signal, so unrelated errors don't trigger a
    pointless retry."""
    m = (msg or "").lower()
    mentions_param = any(p in m for p in
                         ("temperature", "seed", "top_p", "top_k"))
    looks_unsupported = any(s in m for s in
                            ("unsupported", "not supported", "does not support",
                             "400", "bad request"))
    return mentions_param and looks_unsupported


def load_dotenv(path: str | pathlib.Path = ".env") -> None:
    env_path = pathlib.Path(path)
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


class CloudBackend(Backend):
    name = "cloud"

    def __init__(self, provider: str = "openai", base_url: str | None = None,
                 api_key_env: str | None = None,
                 api_version: str | None = None, timeout_s: int = 600):
        provider = (provider or "openai").lower()
        if provider not in DEFAULTS:
            raise ValueError(
                f"unknown cloud provider {provider!r}; expected "
                f"{', '.join(sorted(DEFAULTS))}")
        defaults = DEFAULTS[provider]
        self.provider = provider
        self.base_url = (base_url or defaults["base_url"]).rstrip("/")
        self.api_key_env = api_key_env or defaults["api_key_env"]
        self.api_version = api_version or defaults["api_version"]
        self.timeout = timeout_s
        self.s = requests.Session()

    def version(self) -> str:
        if self.provider == "openai":
            return "openai-chat-completions"
        if self.provider == "anthropic":
            return "anthropic-messages"
        return self.provider

    def settings(self) -> dict:
        d = {
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
        }
        if self.api_version:
            d["api_version"] = self.api_version
        return d

    def model_info(self, model: str) -> dict:
        return {
            "name": model,
            "family": self.provider,
            "parameter_size": "cloud",
            "quantization_level": "provider-managed",
            "digest": f"{self.provider}:{model}",
            "provider": self.provider,
            "api_base": self.base_url,
            "api_key_env": self.api_key_env,
            "api_version": self.api_version,
        }

    def chat(self, model: str, messages: list[dict], options: dict,
             meta: dict | None = None) -> GenResult:
        try:
            if self.provider == "openai":
                return self._chat_openai(model, messages, options)
            if self.provider == "anthropic":
                return self._chat_anthropic(model, messages, options)
            return GenResult(error=f"unsupported cloud provider: {self.provider}")
        except Exception as e:
            return GenResult(error=f"{type(e).__name__}: {e}")

    def _api_key(self) -> str:
        load_dotenv()
        key = os.environ.get(self.api_key_env)
        if not key:
            raise RuntimeError(f"{self.api_key_env} is not set")
        return key

    def _chat_openai(self, model: str, messages: list[dict],
                     options: dict) -> GenResult:
        body: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if options.get("num_predict") is not None:
            body["max_tokens"] = options["num_predict"]
        for k in _OPENAI_OPTS:
            if options.get(k) is not None:
                body[k] = options[k]

        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }
        res = self._post_openai_stream(body, headers)
        # Some reasoning models reject sampling params (temperature/seed) with a
        # 400. Retry once without them rather than failing the whole generation.
        if res.error and _is_unsupported_param_error(res.error):
            stripped = {k: v for k, v in body.items() if k not in _OPENAI_OPTS}
            if stripped != body:
                res = self._post_openai_stream(stripped, headers)
        return res

    def _post_openai_stream(self, body: dict, headers: dict) -> GenResult:
        res = GenResult()
        t0 = time.perf_counter()
        first: float | None = None
        try:
            with self.s.post(f"{self.base_url}/chat/completions", json=body,
                             headers=headers, stream=True,
                             timeout=self.timeout) as r:
                if r.status_code >= 400:
                    # Capture the body so the caller can detect unsupported-param
                    # errors; requests' HTTPError message omits it.
                    res.error = f"HTTP {r.status_code}: {(r.text or '')[:500]}"
                    res.wall_s = time.perf_counter() - t0
                    return res
                for raw in r.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    line = raw.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    usage = chunk.get("usage") or {}
                    if usage:
                        res.prompt_tokens = usage.get("prompt_tokens") or 0
                        res.output_tokens = usage.get("completion_tokens") or 0
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if piece:
                        if first is None:
                            first = time.perf_counter()
                        res.content += piece
        except Exception as e:
            res.error = f"{type(e).__name__}: {e}"
        res.wall_s = time.perf_counter() - t0
        res.ttft_s = (first - t0) if first is not None else 0.0
        res.eval_s = res.wall_s
        if not res.output_tokens:
            res.output_tokens = len(res.content.split())
        return res

    def _chat_anthropic(self, model: str, messages: list[dict],
                        options: dict) -> GenResult:
        system_parts = [m.get("content", "") for m in messages
                        if m.get("role") == "system"]
        api_messages = [m for m in messages if m.get("role") != "system"]
        body: dict = {
            "model": model,
            "max_tokens": int(options.get("num_predict") or 1024),
            "messages": api_messages,
            "stream": True,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        if options.get("temperature") is not None:
            body["temperature"] = options["temperature"]

        headers = {
            "x-api-key": self._api_key(),
            "anthropic-version": self.api_version or "2023-06-01",
            "Content-Type": "application/json",
        }
        res = GenResult()
        t0 = time.perf_counter()
        first: float | None = None
        try:
            with self.s.post(f"{self.base_url}/v1/messages", json=body,
                             headers=headers, stream=True,
                             timeout=self.timeout) as r:
                r.raise_for_status()
                for raw in r.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    line = raw.strip()
                    if not line.startswith("data:"):
                        continue
                    chunk = json.loads(line[5:].strip())
                    ctype = chunk.get("type")
                    if ctype == "message_start":
                        usage = (chunk.get("message") or {}).get("usage") or {}
                        res.prompt_tokens = usage.get("input_tokens") or 0
                    elif ctype == "content_block_delta":
                        delta = chunk.get("delta") or {}
                        piece = delta.get("text") or ""
                        if piece:
                            if first is None:
                                first = time.perf_counter()
                            res.content += piece
                    elif ctype == "message_delta":
                        usage = chunk.get("usage") or {}
                        res.output_tokens = usage.get("output_tokens") or 0
                    elif ctype == "error":
                        err = chunk.get("error") or {}
                        res.error = err.get("message") or str(err)
                        break
        except Exception as e:
            res.error = f"{type(e).__name__}: {e}"
        res.wall_s = time.perf_counter() - t0
        res.ttft_s = (first - t0) if first is not None else 0.0
        res.eval_s = res.wall_s
        if not res.output_tokens:
            res.output_tokens = len(res.content.split())
        return res
