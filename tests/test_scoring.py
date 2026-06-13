"""Harness self-tests: scorers, plus suite self-validation (every coding
task's reference solution must pass its own tests — a failing test here means
the SUITE is broken, not a model). Plain asserts, no pytest dependency."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from metis.scoring import programmatic as P
from metis.suite.loader import load_suite


def test_strip_thinking():
    assert P.strip_thinking("<think>hmm</think>yes") == "yes"
    assert P.strip_thinking("no tags") == "no tags"


def test_numeric():
    s, _ = P.score_numeric_exact("steps...\nAnswer: 7", {"expected": 7})
    assert s == 1.0
    s, _ = P.score_numeric_exact("Answer: 85,005", {"expected": 85005})
    assert s == 1.0
    s, _ = P.score_numeric_exact("the total is 12 candles", {"expected": 12})
    assert s == 1.0  # fallback: last number in text
    s, _ = P.score_numeric_exact("Answer: 8", {"expected": 7})
    assert s == 0.0


def test_choice():
    spec = {"expected": "Cal", "options": ["Ari", "Bec", "Cal"]}
    assert P.score_choice_exact("Answer: Cal.", spec)[0] == 1.0
    assert P.score_choice_exact("Answer: Cal, not Ari.", spec)[0] == 1.0
    assert P.score_choice_exact("Answer: Bec", spec)[0] == 0.0
    yn = {"expected": "no", "options": ["yes", "no"]}
    assert P.score_choice_exact("Answer: No, not necessarily.", yn)[0] == 1.0


def test_constraints():
    spec = {"checks": [
        {"kind": "exact_sentences", "value": 3},
        {"kind": "distinct_first_words"},
        {"kind": "forbidden_words", "value": ["power"]},
    ]}
    good = ("Solar panels convert sunlight into electricity. "
            "Wind turbines harvest moving air. Batteries store the surplus.")
    s, _ = P.score_constraints(good, spec)
    assert s == 1.0
    bad = "Power is great. Power is clean."
    s, d = P.score_constraints(bad, spec)
    assert s < 1.0 and not d["forbidden_words"]["pass"]


def test_json_constraints():
    spec = {"checks": [
        {"kind": "json_only"},
        {"kind": "json_keys", "value": {"title": "str", "tags": "list",
                                        "priority": "int"}},
        {"kind": "json_array_len", "value": {"key": "tags", "len": 4}},
        {"kind": "json_list_lowercase", "value": {"key": "tags"}},
        {"kind": "json_int_range", "value": {"key": "priority", "min": 1,
                                             "max": 5}},
    ]}
    good = ('{"title": "Composting at Home", "tags": ["compost", "garden", '
            '"waste", "soil"], "priority": 2}')
    s, d = P.score_constraints(good, spec)
    assert s == 1.0, d
    s, _ = P.score_constraints("Sure! " + good, spec)
    assert s < 1.0  # json_only fails with leading prose


def test_suite_self_validation():
    suite = load_suite("v1")
    assert len(suite["tasks"]) == 21, len(suite["tasks"])
    cats = {t["category"] for t in suite["tasks"]}
    assert cats == {"reasoning", "coding", "summarisation",
                    "instruction_following", "agentic"}
    for t in suite["tasks"]:
        if t["scoring"]["type"] == "code_tests":
            block = f"```python\n{t['oracle_code']}\n```"
            s, d = P.score_code_tests(block, t["scoring"])
            assert s == 1.0, f"{t['id']}: reference solution fails! {d}"


def test_v2_agentic_ladder_loads():
    suite = load_suite("v2")
    assert suite["version"] == "2.0"
    assert [t["id"] for t in suite["tasks"]] == [
        "agentic_ladder.depth1_fact",
        "agentic_ladder.depth2_sum",
        "agentic_ladder.depth3_argmax",
        "agentic_ladder.depth5_checksum",
    ]
    assert all(t["scoring"]["type"] == "agentic_final"
               for t in suite["tasks"])


def test_code_rejects_wrong_solution():
    suite = load_suite("v1", include=["coding.rle"])
    spec = suite["tasks"][0]["scoring"]
    wrong = "```python\ndef rle(s):\n    return s\n```"
    s, _ = P.score_code_tests(wrong, spec)
    assert s < 1.0


def test_agentic_scoring():
    spec = {"type": "agentic_final", "expected": 85005, "match": "numeric"}
    rec = {"agentic": {"final_answer": "85005", "steps_used": 3,
                       "tool_calls": 3, "invalid_turns": 0,
                       "error_injected": False}}
    s, _ = P.score_agentic_final(rec, spec)
    assert s == 1.0
    rec["agentic"]["final_answer"] = "I could not find it"
    s, _ = P.score_agentic_final(rec, spec)
    assert s == 0.0


def test_coverage_curve_monotone_nonincreasing():
    from metis.report import COVERAGE_CURVE_GRID, _curve
    # Arbitrary spread of task means.
    task_means = {"t1": 1.0, "t2": 0.85, "t3": 0.7, "t4": 0.55, "t5": 0.3}
    curve = _curve(task_means)
    assert len(curve) == len(COVERAGE_CURVE_GRID)
    for i in range(len(curve) - 1):
        assert curve[i] >= curve[i + 1], (
            f"curve not monotone non-increasing at t={COVERAGE_CURVE_GRID[i]:.2f}: "
            f"{curve[i]:.3f} > {curve[i+1]:.3f}")
    # Edge: curve starts at 1.0 when t=0 (all tasks score ≥ 0).
    assert curve[0] == 1.0
    # Edge: empty task_means -> all zeros.
    empty = _curve({})
    assert all(v == 0.0 for v in empty)


def test_agentic_tools():
    from metis.agentic import lookup, safe_calc
    corpus = {"population of veldora": "Veldora has a population of 48,210."}
    assert "48,210" in lookup(corpus, "population of veldora")
    assert "48,210" in lookup(corpus, "What is the population of Veldora?")
    assert lookup(corpus, "weather on mars").startswith("NOT FOUND")
    assert safe_calc("48210 + 36795") == 85005
    assert safe_calc("12,400,000 / 48210") > 257
    try:
        safe_calc("__import__('os')")
        raise AssertionError("safe_calc executed non-arithmetic input")
    except ValueError:
        pass


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok {fn.__name__}")
    print(f"OK — {len(fns)} test groups passed")
