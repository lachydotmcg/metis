from .base import Backend, GenResult
from .cloud import CloudBackend
from .mock import MockBackend
from .ollama import OllamaBackend


def get_backend(name: str, **kwargs) -> Backend:
    if name == "ollama":
        return OllamaBackend(**kwargs)
    if name == "mock":
        return MockBackend()
    if name == "cloud":
        return CloudBackend(**kwargs)
    raise ValueError(
        f"unknown backend: {name!r} (expected 'ollama', 'mock', or 'cloud')")
