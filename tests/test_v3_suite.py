"""v3 frontier-headroom suite self-validation. Mirrors the v1 self-test idea:
the suite must validate itself with ZERO model calls. For every v3 task we score
its declared reference answer (oracle_code / oracle_text / expected) with the
real scorers and require 1.0 — so a broken task definition, an unreachable key,
or a self-contradicting constraint set fails here rather than silently
mis-scoring a model later. Plain asserts, no pytest dependency."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from metis.agentic import lookup
from metis.scoring import programmatic as P
from metis.suite.loader import load_suite

EXPECTED_CATEGORIES = {
    "coding", "agentic_deep", "long_context", "adversarial_summary",
    "instruction_following",
}


def _suite():
    return load_suite("v3")


def test_v3_loads_and_shape():
    suite = _suite()
    assert suite["version"] == "3.0", suite["version"]
    tasks = suite["tasks"]
    # The plan calls for 12-20 harder tasks.
    assert 12 <= len(tasks) <= 20, len(tasks)
    assert {t["category"] for t in tasks} == EXPECTED_CATEGORIES
    ids = [t["id"] for t in tasks]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for t in tasks:
        assert t.get("max_tokens"), f"{t['id']}: missing max_tokens"


def test_v3_code_oracles_pass():
    n = 0
    for t in _suite()["tasks"]:
        if t["scoring"]["type"] != "code_tests":
            continue
        n += 1
        block = f"```python\n{t['oracle_code']}\n```"
        s, d = P.score_code_tests(block, t["scoring"])
        assert s == 1.0, f"{t['id']}: reference solution fails! {d}"
    assert n >= 4, f"expected several coding tasks, got {n}"


def test_v3_numeric_and_choice_oracles_pass():
    seen = {"numeric_exact": 0, "choice_exact": 0}
    for t in _suite()["tasks"]:
        kind = t["scoring"]["type"]
        if kind not in seen:
            continue
        oracle = t.get("oracle_text")
        assert oracle, f"{t['id']}: needs oracle_text for self-validation"
        if kind == "numeric_exact":
            s, d = P.score_numeric_exact(oracle, t["scoring"])
        else:
            s, d = P.score_choice_exact(oracle, t["scoring"])
        assert s == 1.0, f"{t['id']}: oracle does not score 1.0: {d}"
        seen[kind] += 1
    assert seen["numeric_exact"] >= 1 and seen["choice_exact"] >= 1, seen


def test_v3_constraint_oracles_pass():
    n = 0
    for t in _suite()["tasks"]:
        if t["scoring"]["type"] != "constraints":
            continue
        n += 1
        oracle = t.get("oracle_text")
        assert oracle, f"{t['id']}: needs oracle_text for self-validation"
        s, d = P.score_constraints(oracle, t["scoring"])
        assert s == 1.0, f"{t['id']}: oracle fails its own constraints: {d}"
    assert n >= 4, f"expected several constraint tasks, got {n}"


def test_v3_agentic_oracles_and_corpus():
    n = 0
    for t in _suite()["tasks"]:
        if t["scoring"]["type"] != "agentic_final":
            continue
        n += 1
        spec = t["scoring"]
        # The declared expected answer must score 1.0 when produced.
        rec = {"agentic": {"final_answer": str(spec["expected"])}}
        s, d = P.score_agentic_final(rec, spec)
        assert s == 1.0, f"{t['id']}: expected answer does not score 1.0: {d}"
        # Every corpus entry must be retrievable by its own key (the model has
        # to be ABLE to look the facts up; an unreachable fact = a broken task).
        corpus = {k.lower(): v for k, v in
                  (t.get("tools", {}).get("corpus") or {}).items()}
        assert corpus, f"{t['id']}: agentic task with empty corpus"
        for key, val in corpus.items():
            assert lookup(corpus, key) == val, f"{t['id']}: '{key}' unreachable"
    assert n >= 3, f"expected several agentic tasks, got {n}"


def test_v3_does_not_disturb_v1():
    # Loading v3 must not change the frozen v1 suite.
    v1 = load_suite("v1")
    assert len(v1["tasks"]) == 21


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok {fn.__name__}")
    print(f"OK - {len(fns)} test groups passed")
