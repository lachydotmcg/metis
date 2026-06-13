"""Deterministic agentic tool loop. The model gets lookup() over a fixed
fictional corpus and calc() over a safe AST evaluator; same inputs always
produce the same tool outputs, so runs are reproducible. Protocol: strict
JSON, one object per turn."""

import ast
import json
import operator
import re

from .backends.base import GenResult
from .scoring.programmatic import strip_thinking

SYSTEM_PROMPT = """You are completing a task using tools.

Available tools:
- lookup: look up a fact. Call as {"tool": "lookup", "args": {"query": "<what to look up>"}}
- calc: evaluate arithmetic. Call as {"tool": "calc", "args": {"expression": "<e.g. 48210 + 36795>"}}

Rules:
- Respond with ONLY one JSON object per turn. No other text.
- Tool results arrive in the next message as "TOOL_RESULT: ...".
- When you know the answer, respond with {"final_answer": "<answer>"}.
"""

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}

_STOPWORDS = {"of", "the", "a", "an", "in", "for", "to", "is", "what"}


def safe_calc(expr: str):
    expr = expr.replace(",", "").replace("$", "")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 16:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("unsupported expression")

    return ev(ast.parse(expr.strip(), mode="eval"))


def lookup(corpus: dict, query: str) -> str:
    q = query.lower().strip().strip("?.! ")
    if q in corpus:
        return corpus[q]
    for k, v in corpus.items():
        if k in q or q in k:
            return v
    qw = set(re.findall(r"[a-z0-9']+", q)) - _STOPWORDS
    best, best_overlap = None, 0
    for k, v in corpus.items():
        kw = set(re.findall(r"[a-z0-9']+", k)) - _STOPWORDS
        overlap = len(qw & kw)
        if overlap > best_overlap:
            best, best_overlap = v, overlap
    if best is not None and best_overlap >= 2:
        return best
    return "NOT FOUND: no entry matches that query."


def _first_json_obj(text: str):
    text = strip_thinking(text)
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        break
        start = text.find("{", start + 1)
    return None


def run_agentic(backend, model: str, task: dict, options: dict):
    """Returns (aggregate GenResult across turns, agentic metrics dict)."""
    corpus = {k.lower(): v for k, v in
              (task.get("tools", {}).get("corpus") or {}).items()}
    max_steps = task.get("max_steps", 8)
    inject_pending = bool(task.get("fail_first_call"))

    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task["prompt"]}]
    agg = GenResult()
    transcript = []
    tool_calls = invalid_turns = valid_json_turns = 0
    error_injected = False
    final_answer = None
    steps_used = 0

    for step in range(max_steps):
        steps_used = step + 1
        res = backend.chat(model, messages, options, meta=task)
        agg.prompt_tokens += res.prompt_tokens
        agg.output_tokens += res.output_tokens
        agg.prompt_eval_s += res.prompt_eval_s
        agg.eval_s += res.eval_s
        agg.wall_s += res.wall_s
        agg.thinking += res.thinking
        if step == 0:
            agg.ttft_s, agg.load_s = res.ttft_s, res.load_s
        if res.error:
            agg.error = res.error
            break
        agg.content = res.content
        messages.append({"role": "assistant", "content": res.content})

        obj = _first_json_obj(res.content)
        if obj is None:
            invalid_turns += 1
            messages.append({"role": "user", "content":
                "Your reply was not a single valid JSON object. Respond with "
                "ONLY one JSON object as instructed."})
            continue
        valid_json_turns += 1

        if "final_answer" in obj:
            final_answer = str(obj["final_answer"])
            break

        tool, args = obj.get("tool"), obj.get("args") or {}
        if tool == "lookup":
            tool_calls += 1
            if inject_pending:
                result = ("ERROR: lookup service temporarily unavailable. "
                          "Retry the same call.")
                inject_pending, error_injected = False, True
            else:
                result = lookup(corpus, str(args.get("query", "")))
        elif tool == "calc":
            tool_calls += 1
            try:
                result = str(safe_calc(str(args.get("expression", ""))))
            except Exception as e:
                result = f"ERROR: {e}"
        else:
            invalid_turns += 1
            result = ('ERROR: unknown tool. Use "lookup", "calc" or reply '
                      'with {"final_answer": ...}.')
        transcript.append({"step": step, "tool": tool, "args": args,
                           "result": str(result)[:300]})
        messages.append({"role": "user", "content": f"TOOL_RESULT: {result}"})

    metrics = {
        "final_answer": final_answer,
        "steps_used": steps_used,
        "max_steps": max_steps,
        "tool_calls": tool_calls,
        "valid_json_turns": valid_json_turns,
        "invalid_turns": invalid_turns,
        "error_injected": error_injected,
        "transcript": transcript,
    }
    return agg, metrics
