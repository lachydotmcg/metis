"""Phase 1 - runtime task router (classify -> policy -> dispatch).

Phase 0 (routing_sim.py) proved the *policy*: per-category, route to the local
model or the cloud model. It assumed a perfect classifier (it routed by the
task's known category). Phase 1 closes that gap: an incoming task arrives as
PROMPT TEXT ONLY, so we must guess its category cheaply, look up the Phase-0
policy, and dispatch. The open research question, stated plainly:

    How accurately can a cheap keyword classifier predict a task's category,
    and what does a misroute cost in quality and dollars?

`eval` answers it by classifying the real suite prompts (text only), comparing
to the true labels, and pricing the realized routing against the oracle (Phase-0
known-category) routing and against all-cloud.

Design rules carried from Phase 0: stdlib-lean (urllib, not requests), no
hardcoded prices (reuse pricing.yaml via routing_sim), plain-assert tests, type
hints, Windows-first paths. Phase 0 and Phase 1 stay in separate files; Phase 1
imports Phase 0 rather than copying it.

Usage (Windows):
    python router.py classify "Write a Python function that reverses a string"
    python router.py route "Summarise this article in 50 words" ^
        --local-run results\\20260612_173212 --cloud-run results\\20260612_214955
    python router.py eval --local-run results\\20260612_173212 ^
        --cloud-run results\\20260612_214955 --threshold 0.9
    python router.py --selftest
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request

from routing_sim import SimData  # Phase 0 policy + per-task scores/costs

CATEGORIES = ("agentic", "coding", "summarisation",
              "instruction_following", "reasoning")

# Cheap classifier: weighted keyword/phrase rules per category. The point is to
# be the cheapest thing that could work, not a trained model. Weights are tuned
# so the strongest discriminative phrase for a category dominates weak overlap
# (e.g. both summarisation and instruction tasks can say "JSON only", but only
# summarisation says "summarise the following").
Rule = tuple[str, float]
RULES: dict[str, list[Rule]] = {
    "agentic": [
        (r"\btools? available\b", 5.0),
        (r"\busing the tools\b", 5.0),
        (r"\bfinal answer\b", 2.0),
        (r"\blook ?up\b", 1.5),
    ],
    "coding": [
        (r"\bpython function\b", 5.0),
        (r"```", 4.0),
        (r"\bdef\s+\w+\s*\(", 4.0),
        (r"\bwrite a (python|function)\b", 3.0),
        (r"\b(returns?|list|str|int|bool)\b", 0.8),
        (r"\bbug\b", 2.0),
    ],
    "summarisation": [
        (r"\bsummaris[ez]e?\b", 5.0),
        (r"\bsummary\b", 4.0),
        (r"\bthe following (article|changelog|text|passage)\b", 4.0),
        (r"\bchangelog below\b", 4.0),
        (r"\bmeeting notes\b", 4.0),
        (r"\bextract the action items\b", 5.0),
    ],
    "instruction_following": [
        (r"\bexactly (one|two|three|four|five|\d)\b", 4.0),
        (r"\brespond with json only\b", 3.5),
        (r"\bjson only\b", 2.5),
        (r"\bwithout using the words?\b", 4.0),
        (r"\bone .* per line\b", 3.0),
        (r"\balphabetical order\b", 2.5),
        (r"\bbetween \d+ and \d+ words\b", 4.0),
        (r"\bno (numbering|extra text)\b", 3.0),
    ],
    "reasoning": [
        (r"\bhow many\b", 4.0),
        (r"\bwhat day\b", 4.0),
        (r"\bwho plays\b", 4.0),
        (r"\bnecessarily\b", 4.0),
        (r"\breason it out\b", 3.0),
        (r"\bbased only on these statements\b", 4.0),
        (r"\b(per week|per minute|per resident)\b", 2.0),
        (r"\d+\s*%/?", 1.5),
    ],
}

# When the top score is below this, we cannot trust the guess; the router then
# fails safe to cloud rather than risk a weak local model on a misread task.
DEFAULT_MIN_CONFIDENCE = 0.34


class ClassifyResult:
    def __init__(self, category: str, confidence: float, scores: dict[str, float]):
        self.category = category
        self.confidence = confidence
        self.scores = scores

    def __repr__(self) -> str:
        return f"ClassifyResult(category={self.category!r}, confidence={self.confidence:.2f})"


def classify(prompt: str, tools: dict | None = None) -> ClassifyResult:
    """Classify a task from its PROMPT TEXT (and optional runtime tools hint)
    into one of CATEGORIES. Never looks at any task id or category label."""
    text = (prompt or "").lower()
    scores = {c: 0.0 for c in CATEGORIES}
    for cat, rules in RULES.items():
        for pattern, weight in rules:
            if re.search(pattern, text):
                scores[cat] += weight
    # A declared, non-empty tools object at runtime is a legitimate agentic
    # signal independent of wording.
    if tools:
        scores["agentic"] += 3.0

    total = sum(scores.values())
    # Deterministic tie-break: this order favours the more specialised category
    # over the analytical catch-all (reasoning) when weights tie.
    order = {c: i for i, c in enumerate(CATEGORIES)}
    best = max(CATEGORIES, key=lambda c: (scores[c], -order[c]))
    confidence = (scores[best] / total) if total > 0 else 0.0
    if total == 0:
        # No signal at all: default to the analytical bucket, zero confidence,
        # so the router's min-confidence gate sends it to cloud.
        best = "reasoning"
    return ClassifyResult(best, confidence, scores)


class Policy:
    """Per-category routing decision: 'local' or 'cloud'."""

    def __init__(self, mapping: dict[str, str], meta: dict | None = None):
        self.mapping = mapping
        self.meta = meta or {}

    def backend_for(self, category: str) -> str:
        return self.mapping.get(category, "cloud")  # unknown category -> safe cloud

    @classmethod
    def from_results(cls, local_run: str, cloud_run: str, pricing_path: str,
                     threshold: float, local_model: str | None = None,
                     cloud_model: str | None = None) -> "Policy":
        """Build the policy from a Metis run pair, reusing the Phase-0 simulator
        so the policy and the proof come from one source."""
        data = SimData(local_run, cloud_run, pricing_path,
                       local_model=local_model, cloud_model=cloud_model)
        mapping = {
            c: ("local" if mean >= threshold else "cloud")
            for c, mean in data.local_cat_means.items()
        }
        # Categories with no data default to cloud (safe).
        for c in CATEGORIES:
            mapping.setdefault(c, "cloud")
        return cls(mapping, {"threshold": threshold, "local_cat_means": data.local_cat_means})

    @classmethod
    def from_file(cls, path: str) -> "Policy":
        import pathlib
        return cls(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))

    def to_json(self) -> str:
        return json.dumps(self.mapping, indent=2)


# ── Backends (optional, stdlib-only; tests use fakes) ─────────────────────────

def ollama_backend(prompt: str, model: str, base_url: str = "http://localhost:11434",
                   timeout_s: float = 120.0) -> dict:
    """Local dispatch. base_url is caller/config supplied; keep it loopback for
    privacy. Returns {ok, text, error}."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(f"{base_url.rstrip('/')}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            j = json.loads(r.read().decode("utf-8"))
        return {"ok": True, "text": (j.get("message") or {}).get("content")
                or j.get("response") or "", "error": None, "backend": "local"}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # Never silently fall back to cloud here: surface the local failure so
        # the caller decides. Mirrors the ACC's no-silent-fallback rule.
        return {"ok": False, "text": "", "error": f"ollama unreachable: {e}", "backend": "local"}


def deepseek_backend(prompt: str, model: str, api_key: str,
                     base_url: str = "https://api.deepseek.com",
                     timeout_s: float = 60.0) -> dict:
    """Cloud dispatch (OpenAI-compatible). Key from caller (read from env by the
    CLI), never hardcoded. Returns {ok, text, error}."""
    if not api_key:
        return {"ok": False, "text": "", "error": "DEEPSEEK_API_KEY not set", "backend": "cloud"}
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(f"{base_url.rstrip('/')}/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            j = json.loads(r.read().decode("utf-8"))
        return {"ok": True, "text": j["choices"][0]["message"]["content"],
                "error": None, "backend": "cloud"}
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError) as e:
        return {"ok": False, "text": "", "error": f"deepseek error: {e}", "backend": "cloud"}


class Router:
    """Classify -> policy -> dispatch. Backends is {'local': fn, 'cloud': fn},
    each fn(prompt) -> result dict. Low-confidence guesses fail safe to cloud."""

    def __init__(self, policy: Policy, backends: dict | None = None,
                 min_confidence: float = DEFAULT_MIN_CONFIDENCE):
        self.policy = policy
        self.backends = backends or {}
        self.min_confidence = min_confidence

    def route(self, prompt: str, tools: dict | None = None) -> dict:
        """Decide a backend WITHOUT dispatching. Returns the full decision so the
        caller can log misroute risk."""
        cr = classify(prompt, tools)
        low_conf = cr.confidence < self.min_confidence
        backend = "cloud" if low_conf else self.policy.backend_for(cr.category)
        return {
            "category": cr.category,
            "confidence": round(cr.confidence, 3),
            "low_confidence": low_conf,
            "backend": backend,
            "scores": cr.scores,
        }

    def dispatch(self, prompt: str, tools: dict | None = None) -> dict:
        decision = self.route(prompt, tools)
        fn = self.backends.get(decision["backend"])
        if fn is None:
            return {**decision, "ok": False, "error": f"no backend wired for {decision['backend']!r}"}
        result = fn(prompt)
        return {**decision, **result}


# ── Evaluation: the actual research deliverable ───────────────────────────────

def evaluate(local_run: str, cloud_run: str, pricing_path: str, threshold: float,
             min_confidence: float = DEFAULT_MIN_CONFIDENCE,
             suite_version: str = "v1", local_model: str | None = None,
             cloud_model: str | None = None) -> str:
    """Classify the real suite prompts (text only), then price the realized
    routing against the oracle (known-category) routing and all-cloud. Answers:
    classifier accuracy, backend-flip rate, and the quality/cost of misroutes."""
    from metis.suite.loader import load_suite

    data = SimData(local_run, cloud_run, pricing_path,
                   local_model=local_model, cloud_model=cloud_model)
    policy = Policy.from_results(local_run, cloud_run, pricing_path, threshold,
                                 local_model=local_model, cloud_model=cloud_model)
    have_cost = data.local_cost is not None and data.cloud_cost is not None
    suite = load_suite(suite_version)
    by_id = {t["id"]: t for t in suite["tasks"]}

    rows = []
    correct = 0
    backend_flips = 0
    oracle_success = clf_success = cloud_success = 0.0
    oracle_cost = clf_cost = cloud_cost = 0.0

    for tid in data.tasks:
        task = by_id.get(tid)
        if not task:
            continue
        true_cat = data.cat_by_task[tid]
        cr = classify(task["prompt"], task.get("tools"))
        low_conf = cr.confidence < min_confidence
        pred_cat = cr.category
        if pred_cat == true_cat:
            correct += 1

        be_oracle = policy.backend_for(true_cat)
        be_clf = "cloud" if low_conf else policy.backend_for(pred_cat)
        if be_clf != be_oracle:
            backend_flips += 1

        def succ(be: str) -> float:
            return data.local_score[tid] if be == "local" else data.cloud_score[tid]

        def cost(be: str) -> float:
            return (data.local_cost[tid] if be == "local" else data.cloud_cost[tid]) if have_cost else 0.0

        oracle_success += succ(be_oracle)
        clf_success += succ(be_clf)
        cloud_success += data.cloud_score[tid]
        oracle_cost += cost(be_oracle)
        clf_cost += cost(be_clf)
        cloud_cost += cost("cloud")

        rows.append((tid, true_cat, pred_cat, round(cr.confidence, 2),
                     be_oracle, be_clf, "MISCLASS" if pred_cat != true_cat else "",
                     "FLIP" if be_clf != be_oracle else ""))

    n = len(rows)
    lines = ["# Phase 1 - router evaluation (classify on prompt text only)", ""]
    lines.append(f"local run : {local_run}")
    lines.append(f"cloud run : {cloud_run}")
    lines.append(f"threshold : {threshold} | min_confidence : {min_confidence}")
    lines.append(f"tasks     : {n}")
    lines.append("")
    lines.append(f"policy: " + ", ".join(f"{c}->{policy.mapping[c]}" for c in CATEGORIES))
    lines.append("")
    lines.append(f"classification accuracy : {correct}/{n} = {correct / n * 100:.1f}%")
    lines.append(f"backend flips (misroutes that changed local/cloud) : {backend_flips}/{n}")
    lines.append("")

    lines.append("| task | true | predicted | conf | oracle | routed | class | route |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append("| " + " | ".join(str(x) for x in r) + " |")
    lines.append("")

    lines.append("## Outcome vs the perfect-classifier upper bound")
    lines.append("")
    if have_cost:
        lines.append(f"| routing | success /{n} | cost ({data.currency}) | cost/success |")
        lines.append("|---|---|---|---|")
        for name, s, c in (("all-cloud", cloud_success, cloud_cost),
                           ("oracle (Phase 0)", oracle_success, oracle_cost),
                           ("classifier (Phase 1)", clf_success, clf_cost)):
            cps = c / s if s else float("inf")
            lines.append(f"| {name} | {s:.2f} | {c:.4f} | {cps:.6f} |")
        lines.append("")
        quality_penalty = oracle_success - clf_success
        cost_penalty = clf_cost - oracle_cost
        lines.append("## Misroute cost (the research question)")
        lines.append("")
        lines.append(f"- Quality lost to misclassification vs oracle: {quality_penalty:.2f} task-points "
                     f"({quality_penalty / oracle_success * 100 if oracle_success else 0:.1f}% of oracle success).")
        lines.append(f"- Cost change from misclassification vs oracle: {cost_penalty:+.4f} {data.currency}.")
        lines.append(f"- Classifier routing keeps {clf_success / cloud_success * 100 if cloud_success else 0:.1f}% "
                     f"of all-cloud quality at {(1 - clf_cost / cloud_cost) * 100 if cloud_cost else 0:.1f}% lower cost.")
    else:
        lines.append("(pricing.yaml unpriced - success only)")
        for name, s in (("all-cloud", cloud_success), ("oracle", oracle_success),
                        ("classifier", clf_success)):
            lines.append(f"- {name}: {s:.2f}/{n}")
    return "\n".join(lines)


# ── Self-test ─────────────────────────────────────────────────────────────────

def _selftest() -> None:
    # Classifier hits the obvious cases.
    assert classify("Write a Python function `rle(s: str) -> str`").category == "coding"
    assert classify("Summarise the following article in at most 50 words").category == "summarisation"
    assert classify("Using the tools available, find the combined population").category == "agentic"
    assert classify("Write exactly three sentences about renewable energy").category == "instruction_following"
    assert classify("How many candles does she have left?").category == "reasoning"
    # tools hint pushes agentic even on bland text.
    assert classify("find the value", tools={"corpus": {}}).category == "agentic"
    # No signal -> reasoning, zero confidence.
    none_res = classify("hello there friend")
    assert none_res.confidence == 0.0, none_res

    # Policy + routing + fail-safe.
    pol = Policy({"reasoning": "local", "coding": "cloud", "summarisation": "cloud",
                  "instruction_following": "cloud", "agentic": "cloud"})
    assert pol.backend_for("reasoning") == "local"
    assert pol.backend_for("unknown_cat") == "cloud"

    calls = {"local": 0, "cloud": 0}
    backends = {
        "local": lambda p: (calls.__setitem__("local", calls["local"] + 1) or
                            {"ok": True, "text": "L", "error": None, "backend": "local"}),
        "cloud": lambda p: (calls.__setitem__("cloud", calls["cloud"] + 1) or
                            {"ok": True, "text": "C", "error": None, "backend": "cloud"}),
    }
    r = Router(pol, backends, min_confidence=0.0)
    # A clear reasoning task -> local backend.
    out = r.dispatch("How many candles does she have left after 5 weeks?")
    assert out["backend"] == "local" and out["text"] == "L", out
    # A coding task -> cloud backend.
    out = r.dispatch("Write a Python function to merge intervals")
    assert out["backend"] == "cloud" and out["text"] == "C", out

    # Low-confidence fail-safe: a min_confidence above the 0..1 range forces the
    # gate to trip for every task, proving low-confidence guesses go to cloud
    # rather than risking a weak local model.
    r_safe = Router(pol, backends, min_confidence=2.0)
    out = r_safe.dispatch("How many candles does she have left?")
    assert out["low_confidence"] and out["backend"] == "cloud", out

    # Backend returning failure is surfaced, not swallowed.
    fail_backends = {"local": lambda p: {"ok": False, "text": "", "error": "ollama unreachable", "backend": "local"},
                     "cloud": backends["cloud"]}
    r2 = Router(pol, fail_backends, min_confidence=0.0)
    out = r2.dispatch("How many candles?")
    assert out["ok"] is False and "unreachable" in out["error"], out

    print("selftest: all assertions passed")


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 1 task router.")
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("classify", help="classify a prompt")
    c.add_argument("prompt")

    rt = sub.add_parser("route", help="decide a backend without dispatching")
    rt.add_argument("prompt")
    rt.add_argument("--local-run", required=True)
    rt.add_argument("--cloud-run", required=True)
    rt.add_argument("--pricing", default="config/pricing.yaml")
    rt.add_argument("--threshold", type=float, default=0.9)
    rt.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE)
    rt.add_argument("--local-model", default=None)
    rt.add_argument("--cloud-model", default=None)

    ev = sub.add_parser("eval", help="evaluate the classifier router on the suite")
    ev.add_argument("--local-run", required=True)
    ev.add_argument("--cloud-run", required=True)
    ev.add_argument("--pricing", default="config/pricing.yaml")
    ev.add_argument("--threshold", type=float, default=0.9)
    ev.add_argument("--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE)
    ev.add_argument("--local-model", default=None)
    ev.add_argument("--cloud-model", default=None)

    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return
    if args.cmd == "classify":
        cr = classify(args.prompt)
        print(f"{cr.category}  (confidence {cr.confidence:.2f})")
        print("scores:", {k: round(v, 1) for k, v in cr.scores.items() if v})
    elif args.cmd == "route":
        pol = Policy.from_results(args.local_run, args.cloud_run, args.pricing,
                                  args.threshold, args.local_model, args.cloud_model)
        r = Router(pol, min_confidence=args.min_confidence)
        print(json.dumps(r.route(args.prompt), indent=2))
    elif args.cmd == "eval":
        print(evaluate(args.local_run, args.cloud_run, args.pricing,
                       args.threshold, args.min_confidence,
                       local_model=args.local_model, cloud_model=args.cloud_model))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
