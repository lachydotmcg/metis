from dataclasses import dataclass


@dataclass
class GenResult:
    content: str = ""
    thinking: str = ""
    prompt_tokens: int = 0
    output_tokens: int = 0
    load_s: float = 0.0
    prompt_eval_s: float = 0.0
    eval_s: float = 0.0
    ttft_s: float = 0.0  # wall-clock to first streamed token, thinking included
    wall_s: float = 0.0
    error: str | None = None


class Backend:
    name = "base"

    def version(self) -> str:
        raise NotImplementedError

    def settings(self) -> dict:
        return {}

    def model_info(self, model: str) -> dict:
        raise NotImplementedError

    def preload(self, model: str, keep_alive="15m") -> None:
        pass

    def unload(self, model: str) -> None:
        pass

    def chat(self, model: str, messages: list[dict], options: dict,
             meta: dict | None = None) -> GenResult:
        raise NotImplementedError

    def generate(self, model: str, system: str | None, prompt: str,
                 options: dict, meta: dict | None = None) -> GenResult:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(model, messages, options, meta=meta)
