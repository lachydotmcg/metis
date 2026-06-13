"""Tier-1 scoring: programmatic ground truth. Every scorer takes the visible
output text (thinking stripped) plus the task's scoring spec and returns
(score 0..1, details). Judge-tier scoring lives in judge.py and is a separate,
re-runnable pass."""

import ast
import json as jsonlib
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
ANSWER_RE = re.compile(r"(?i)\banswer\s*[:\-]\s*(.+)")
NUM_RE = re.compile(r"-?\$?\d[\d,]*(?:\.\d+)?")
CODE_BLOCK_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)
_WORD_RE = re.compile(r"[A-Za-z0-9']+")


def strip_thinking(text: str) -> str:
    return THINK_RE.sub("", text or "").strip()


def _answer_line(text: str) -> str | None:
    matches = ANSWER_RE.findall(text)
    return matches[-1].strip() if matches else None


def _parse_num(s: str) -> float:
    return float(s.replace(",", "").replace("$", ""))


def extract_number(text: str) -> float | None:
    """Number from the (last) 'Answer:' line if present, else the last number
    anywhere in the text."""
    line = _answer_line(text)
    if line is not None:
        nums = NUM_RE.findall(line)
        return _parse_num(nums[0]) if nums else None
    nums = NUM_RE.findall(text)
    return _parse_num(nums[-1]) if nums else None


def score_numeric_exact(text: str, spec: dict):
    text = strip_thinking(text)
    val = extract_number(text)
    if val is None:
        return 0.0, {"reason": "no number found", "expected": spec["expected"]}
    ok = math.isclose(val, float(spec["expected"]), rel_tol=1e-6, abs_tol=1e-6)
    return (1.0 if ok else 0.0), {"extracted": val, "expected": spec["expected"]}


def score_choice_exact(text: str, spec: dict):
    text = strip_thinking(text)
    lines = [l for l in text.splitlines() if l.strip()]
    line = _answer_line(text) or (lines[-1] if lines else "")
    low = line.lower()
    expected = str(spec["expected"]).lower()
    options = [str(o).lower() for o in spec.get("options", [expected])]
    # earliest option mentioned on the answer line wins, so "Answer: Cal, not
    # Ari" still counts as Cal
    positions = []
    for o in options:
        m = re.search(rf"\b{re.escape(o)}\b", low)
        if m:
            positions.append((m.start(), o))
    found = min(positions)[1] if positions else None
    return (1.0 if found == expected else 0.0), {
        "answer_line": line[:200], "found": found, "expected": expected}


# ---------------------------------------------------------------- constraints

def _words(t):
    return _WORD_RE.findall(t)


def _sentences(t):
    parts = re.split(r"(?<=[.!?])\s+", t.strip())
    return [p for p in parts if p.strip()]


def _lines(t):
    return [l.strip() for l in t.strip().splitlines() if l.strip()]


def _bullets(t):
    return [re.sub(r"^[-*•]\s+", "", l) for l in _lines(t)
            if re.match(r"^[-*•]\s+", l)]


def _json_payload(text: str):
    """(parsed_json, leftover_text_outside_json) or (None, text)."""
    text = strip_thinking(text)
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return None, text
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    if end <= start:
        return None, text
    try:
        payload = jsonlib.loads(text[start:end + 1])
    except Exception:
        return None, text
    outside = (text[:start] + text[end + 1:]).strip()
    return payload, outside


_TYPES = {"str": str, "int": int, "float": (int, float), "list": list,
          "bool": bool, "dict": dict}


def _check(kind: str, value, text: str, payload, outside):
    if kind == "max_words":
        n = len(_words(text)); return n <= value, f"{n} words (max {value})"
    if kind == "min_words":
        n = len(_words(text)); return n >= value, f"{n} words (min {value})"
    if kind == "exact_sentences":
        n = len(_sentences(text)); return n == value, f"{n} sentences (want {value})"
    if kind == "min_sentences":
        n = len(_sentences(text)); return n >= value, f"{n} sentences (min {value})"
    if kind == "max_sentences":
        n = len(_sentences(text)); return n <= value, f"{n} sentences (max {value})"
    if kind == "exact_lines":
        n = len(_lines(text)); return n == value, f"{n} lines (want {value})"
    if kind == "exact_bullets":
        n = len(_bullets(text)); return n == value, f"{n} bullets (want {value})"
    if kind == "bullet_max_words":
        counts = [len(_words(b)) for b in _bullets(text)]
        return bool(counts) and all(c <= value for c in counts), f"bullet words {counts}"
    if kind == "forbidden_words":
        hits = [w for w in value
                if re.search(rf"\b{re.escape(str(w))}\b", text, re.IGNORECASE)]
        return not hits, f"forbidden present: {hits}" if hits else "none present"
    if kind == "required_words":
        missing = [w for w in value
                   if not re.search(rf"\b{re.escape(str(w))}\b", text, re.IGNORECASE)]
        return not missing, f"missing: {missing}" if missing else "all present"
    if kind == "distinct_first_words":
        firsts = [(_words(s) or ["?"])[0].casefold() for s in _sentences(text)]
        return len(firsts) == len(set(firsts)), f"first words {firsts}"
    if kind == "alphabetical_lines":
        lines = [l.casefold() for l in _lines(text)]
        return lines == sorted(lines), "sorted" if lines == sorted(lines) else f"unsorted: {lines}"
    if kind == "no_digits":
        return not re.search(r"\d", text), "digit check"
    if kind == "regex_must":
        return bool(re.search(value, text)), f"pattern {value!r}"
    if kind == "regex_forbid":
        return not re.search(value, text), f"pattern {value!r}"
    if kind == "json_only":
        return payload is not None and not outside, \
            "parses as bare JSON" if payload is not None and not outside else "not bare JSON"
    if kind == "json_keys":
        if not isinstance(payload, dict):
            return False, "no JSON object"
        bad = []
        for key, tname in value.items():
            v = payload.get(key)
            want = _TYPES[tname]
            ok = isinstance(v, want) and not (tname == "int" and isinstance(v, bool))
            if not ok:
                bad.append(key)
        return not bad, f"bad/missing keys: {bad}" if bad else "keys ok"
    if kind == "json_array_len":
        v = payload.get(value["key"]) if isinstance(payload, dict) else None
        ok = isinstance(v, list) and len(v) == value["len"]
        return ok, f"{value['key']} len {len(v) if isinstance(v, list) else 'n/a'}"
    if kind == "json_list_lowercase":
        v = payload.get(value["key"]) if isinstance(payload, dict) else None
        ok = isinstance(v, list) and all(isinstance(s, str) and s == s.lower() for s in v)
        return ok, f"{value['key']} lowercase strings"
    if kind == "json_int_range":
        v = payload.get(value["key"]) if isinstance(payload, dict) else None
        ok = isinstance(v, int) and not isinstance(v, bool) and value["min"] <= v <= value["max"]
        return ok, f"{value['key']}={v}"
    raise ValueError(f"unknown constraint kind: {kind!r}")


def score_constraints(text: str, spec: dict):
    text = strip_thinking(text)
    payload, outside = _json_payload(text)
    results = {}
    passed = 0
    for chk in spec["checks"]:
        kind, value = chk["kind"], chk.get("value")
        ok, detail = _check(kind, value, text, payload, outside)
        results[kind] = {"pass": ok, "detail": detail}
        passed += ok
    return passed / len(spec["checks"]), results


# ----------------------------------------------------------------- code tests

def extract_python(text: str, entry_point: str) -> str | None:
    blocks = CODE_BLOCK_RE.findall(text)
    defining = [b for b in blocks if f"def {entry_point}" in b]
    if defining:
        return defining[-1]
    if blocks:
        return blocks[-1]
    return text if f"def {entry_point}" in text else None


def score_code_tests(text: str, spec: dict, timeout_s: int = 20):
    code = extract_python(strip_thinking(text), spec["entry_point"])
    if not code:
        return 0.0, {"reason": "no python block defining entry point"}
    tests = [(t["call"], t["expected"]) for t in spec["tests"]]
    driver = (
        code
        + "\n\nimport json as _json, ast as _ast\n"
        + f"_tests = {tests!r}\n"
        + "_passed = 0\n"
        + "for _call, _exp in _tests:\n"
        + "    try:\n"
        + "        if eval(_call) == _ast.literal_eval(_exp):\n"
        + "            _passed += 1\n"
        + "    except Exception:\n"
        + "        pass\n"
        + "print(_json.dumps({'passed': _passed, 'total': len(_tests)}))\n"
    )
    with tempfile.TemporaryDirectory(prefix="metis_code_") as td:
        path = Path(td) / "candidate.py"
        path.write_text(driver, encoding="utf-8")
        try:
            # -I: isolated mode (no site-packages, no env vars, no cwd on path)
            proc = subprocess.run([sys.executable, "-I", str(path)],
                                  capture_output=True, text=True,
                                  timeout=timeout_s, cwd=td)
        except subprocess.TimeoutExpired:
            return 0.0, {"reason": f"timeout after {timeout_s}s"}
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    if not lines:
        return 0.0, {"reason": "no output from test driver",
                     "stderr": proc.stderr[-400:]}
    try:
        result = jsonlib.loads(lines[-1])
    except Exception:
        return 0.0, {"reason": "unparseable driver output",
                     "stdout": proc.stdout[-400:]}
    frac = result["passed"] / result["total"] if result["total"] else 0.0
    return frac, result


# -------------------------------------------------------------------- agentic

def score_agentic_final(record: dict, spec: dict):
    ag = record.get("agentic") or {}
    final = ag.get("final_answer")
    details = {
        "final_answer": final,
        "steps_used": ag.get("steps_used"),
        "tool_calls": ag.get("tool_calls"),
        "invalid_turns": ag.get("invalid_turns"),
        "error_injected": ag.get("error_injected", False),
    }
    if final is None:
        details["reason"] = "no final answer produced"
        return 0.0, details
    expected = spec["expected"]
    if spec.get("match") == "numeric":
        nums = NUM_RE.findall(str(final))
        ok = bool(nums) and math.isclose(
            _parse_num(nums[-1]), float(expected), rel_tol=1e-6, abs_tol=1e-6)
    else:
        ok = bool(re.search(rf"\b{re.escape(str(expected))}\b",
                            str(final), re.IGNORECASE))
    if ag.get("error_injected"):
        details["recovered"] = ok
    return (1.0 if ok else 0.0), details


# ------------------------------------------------------------------- dispatch

def score_record(record: dict, task: dict, allow_code_exec: bool = True) -> dict:
    spec = task["scoring"]
    needs_judge = bool(spec.get("needs_judge"))
    if record.get("error"):
        return {"score": 0.0, "needs_judge": needs_judge,
                "details": {"reason": f"generation error: {record['error']}"}}
    kind = spec["type"]
    text = (record.get("output") or {}).get("content", "")
    if kind == "numeric_exact":
        score, details = score_numeric_exact(text, spec)
    elif kind == "choice_exact":
        score, details = score_choice_exact(text, spec)
    elif kind == "constraints":
        score, details = score_constraints(text, spec)
    elif kind == "code_tests":
        if not allow_code_exec:
            return {"score": None, "needs_judge": needs_judge,
                    "details": {"reason": "code execution disabled"}}
        score, details = score_code_tests(text, spec)
    elif kind == "agentic_final":
        score, details = score_agentic_final(record, spec)
    else:
        raise ValueError(f"unknown scoring type {kind!r}")
    return {"score": score, "needs_judge": needs_judge, "details": details}
