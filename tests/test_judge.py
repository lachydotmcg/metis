"""Plain-assert tests for tier-2 judge plumbing."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from metis.backends import get_backend
from metis.backends.base import GenResult
from metis.backends.cloud import CloudBackend, load_dotenv
from metis.backends.llamacpp import LlamaCppBackend, build_body, consume_stream
from metis.report import aggregate
from metis.scoring import judge as J


class FakeJudge:
    def __init__(self):
        self.calls = [
            '{"winner":"B","score_a":0.2,"score_b":1.0,"rationale":"A weak"}',
            '{"winner":"A","score_a":1.0,"score_b":0.8,"rationale":"B good"}',
        ]

    def generate(self, model, system, prompt, options):
        return GenResult(content=self.calls.pop(0), prompt_tokens=10,
                         output_tokens=5, wall_s=0.1, ttft_s=0.01)


def _write_json(path: Path, data: dict):
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]):
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8")


def test_extract_json_bounds_score():
    data = J._extract_json(
        'x {"winner":"tie","score_a":0.75,"score_b":1,"rationale":"ok"} y')
    assert data["winner"] == "tie"
    assert data["score_a"] == 0.75
    try:
        J._extract_json('{"winner":"A","score_a":2,"score_b":1}')
        raise AssertionError("accepted out-of-bounds judge score")
    except ValueError:
        pass


def test_position_swap_averages_candidate_positions():
    task = {
        "id": "summarisation.fake",
        "prompt": "Summarise this.",
        "oracle_text": "reference",
    }
    score, details = J._score_pair(
        FakeJudge(), "judge-model", task, "rubric", "candidate",
        max_tokens=128, temperature=0)
    assert score == 0.5
    assert details["position_swap"]["candidate_as_a"]["score_a"] == 0.2
    assert details["position_swap"]["candidate_as_b"]["score_b"] == 0.8


def test_report_prefers_judge_only_for_needs_judge():
    with tempfile.TemporaryDirectory(prefix="metis_judge_test_") as td:
        run = Path(td)
        _write_json(run / "manifest.json", {
            "run_id": "r1",
            "suite_version": "1.0",
            "suite_dir": "v1",
            "models": ["m"],
            "model_infos": {"m": {"digest": "d"}},
            "backend": {"name": "mock", "version": "mock-1"},
            "options": {"temperature": 0, "seed": 1234, "num_ctx": 4096},
            "repeats": 1,
            "schedule": "rotating-block",
        })
        _write_json(run / "fingerprint.json", {
            "cpu": "cpu",
            "ram_total_gb": 1,
            "gpus": [],
            "fingerprint_id": "fp",
        })
        rec = {
            "task_id": "summarisation.ferry",
            "category": "summarisation",
            "repeat": 0,
            "model": {"name": "m"},
            "timings": {"decode_tps": 1, "prefill_tps": 1, "ttft_s": 1,
                        "eval_s": 1, "prompt_eval_s": 1,
                        "output_tokens": 1, "prompt_tokens": 1,
                        "wall_s": 1},
            "monitor": {},
            "error": None,
        }
        _write_jsonl(run / "records.jsonl", [rec])
        _write_jsonl(run / "scores.jsonl", [{
            "task_id": "summarisation.ferry",
            "category": "summarisation",
            "model": "m",
            "repeat": 0,
            "score": 0.25,
            "needs_judge": True,
        }])
        _write_jsonl(run / "judge_scores.jsonl", [{
            "task_id": "summarisation.ferry",
            "category": "summarisation",
            "model": "m",
            "repeat": 0,
            "score": 0.9,
            "needs_judge": True,
            "judge_applied": True,
        }])
        data = aggregate(run)
        assert data["per_model"]["m"]["scores_all"] == [0.9]
        assert data["per_model"]["m"]["pending_judge"] == 0
        assert data["per_model"]["m"]["judge_applied"] == 1


def test_cloud_backend_missing_key_is_generation_error():
    backend = CloudBackend(provider="openai", api_key_env="METIS_NO_SUCH_KEY")
    res = backend.chat(
        "reference-model",
        [{"role": "user", "content": "hello"}],
        {"num_predict": 1},
    )
    assert res.error and "METIS_NO_SUCH_KEY" in res.error


def test_llamacpp_registered_and_records_gpu_layers():
    be = get_backend("llamacpp", base_url="http://localhost:8080/",
                     n_gpu_layers=20)
    assert isinstance(be, LlamaCppBackend)
    assert be.base == "http://localhost:8080"  # trailing slash stripped
    # settings() records the launch-time knob even with no server reachable.
    s = be.settings()
    assert s["base_url"] == "http://localhost:8080"
    assert s["n_gpu_layers"] == 20
    mi = be.model_info("qwen3-8b.gguf")
    assert mi["family"] == "llama.cpp" and mi["n_gpu_layers"] == 20


def test_llamacpp_build_body_maps_knobs():
    body = build_body("m", [{"role": "user", "content": "hi"}],
                      {"num_predict": 64, "temperature": 0.0, "seed": 7})
    assert body["model"] == "m"
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}
    assert body["max_tokens"] == 64
    assert body["temperature"] == 0.0 and body["seed"] == 7
    # Knobs that weren't supplied must not appear.
    body2 = build_body("m", [], {})
    assert "max_tokens" not in body2 and "temperature" not in body2


def test_llamacpp_consume_stream_parses_content_and_timings():
    # An OpenAI-style SSE with llama.cpp's timings block in the final chunk.
    lines = [
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        '',  # blank lines are skipped
        'data: {"choices":[{"delta":{}}],'
        '"usage":{"prompt_tokens":11,"completion_tokens":2},'
        '"timings":{"prompt_ms":500.0,"predicted_ms":2000.0,'
        '"prompt_n":11,"predicted_n":2}}',
        'data: [DONE]',
    ]
    res = GenResult()
    first = consume_stream(iter(lines), res)
    assert res.content == "Hello"
    assert res.prompt_tokens == 11 and res.output_tokens == 2
    assert res.prompt_eval_s == 0.5 and res.eval_s == 2.0
    assert first is not None  # a content token was seen


def test_llamacpp_chat_end_to_end_with_fake_session():
    # Drive chat() fully offline through a fake requests session, exercising
    # body-build -> POST -> stream-parse -> timing finalisation.
    class _FakeResp:
        def __init__(self, lines):
            self._lines = lines
            self.status_code = 200
            self.text = ""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self, decode_unicode=False):
            return iter(self._lines)

    class _FakeSession:
        def __init__(self, lines):
            self._lines = lines
            self.last = None

        def post(self, url, json=None, stream=None, timeout=None):
            self.last = {"url": url, "json": json}
            return _FakeResp(self._lines)

    lines = [
        'data: {"choices":[{"delta":{"content":"4"}}]}',
        'data: {"choices":[{"delta":{}}],'
        '"usage":{"prompt_tokens":5,"completion_tokens":1},'
        '"timings":{"predicted_ms":1000.0,"predicted_n":1}}',
        'data: [DONE]',
    ]
    be = LlamaCppBackend(n_gpu_layers=33)
    be.s = _FakeSession(lines)
    res = be.chat("m", [{"role": "user", "content": "2+2?"}],
                  {"num_predict": 16, "temperature": 0.0})
    assert res.error is None
    assert res.content == "4"
    assert res.output_tokens == 1 and res.eval_s == 1.0
    # The request hit the OpenAI-compatible path with the mapped body.
    assert be.s.last["url"].endswith("/v1/chat/completions")
    assert be.s.last["json"]["max_tokens"] == 16


def test_llamacpp_chat_http_error_is_recorded_not_raised():
    class _FakeResp:
        status_code = 503
        text = "model loading"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_lines(self, decode_unicode=False):
            return iter([])

    class _FakeSession:
        def post(self, *a, **k):
            return _FakeResp()

    be = LlamaCppBackend()
    be.s = _FakeSession()
    res = be.chat("m", [{"role": "user", "content": "x"}], {})
    assert res.error and "503" in res.error


def test_dotenv_loader_sets_missing_env_only():
    with tempfile.TemporaryDirectory(prefix="metis_env_test_") as td:
        path = Path(td) / ".env"
        path.write_text(
            "METIS_TEST_KEY=from_file\nMETIS_EXISTING_KEY=from_file\n",
            encoding="utf-8")
        import os
        os.environ["METIS_EXISTING_KEY"] = "from_env"
        os.environ.pop("METIS_TEST_KEY", None)
        load_dotenv(path)
        assert os.environ["METIS_TEST_KEY"] == "from_file"
        assert os.environ["METIS_EXISTING_KEY"] == "from_env"
        os.environ.pop("METIS_TEST_KEY", None)
        os.environ.pop("METIS_EXISTING_KEY", None)


def test_extract_json_ignores_prose_braces():
    # A judge that emits reasoning with braces before the verdict must not crash
    # the parse (the old greedy \{.*\} grabbed from the first brace to the last).
    text = ('Let me think {about this carefully}. The candidate is clearer.\n'
            '{"score_a": 0.8, "score_b": 0.6, "winner": "A"}')
    d = J._extract_json(text)
    assert d["score_a"] == 0.8 and d["score_b"] == 0.6 and d["winner"] == "a"


def test_extract_json_picks_last_valid_object():
    text = ('{"score_a": 0.1, "score_b": 0.1, "winner": "tie"} then revised: '
            '{"score_a": 0.9, "score_b": 0.2, "winner": "A"}')
    d = J._extract_json(text)
    assert d["score_a"] == 0.9  # the final verdict wins


def test_extract_json_unparseable_raises():
    try:
        J._extract_json("no json here at all")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_unsupported_param_error_detection():
    from metis.backends.cloud import _is_unsupported_param_error as f
    assert f("HTTP 400: Unsupported value: 'temperature' is not supported")
    assert f("HTTP 400: 'seed' is not supported with this model")
    assert not f("HTTP 400: model not found")          # 400 but no param
    assert not f("ConnectionError: timed out")          # param-free error
    assert not f("")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok {fn.__name__}")
    print(f"OK - {len(fns)} test groups passed")
