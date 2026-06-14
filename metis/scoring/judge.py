"""Tier-2 scoring: LLM-as-judge.

This pass reads stored records and tier-1 scores, judges only rows whose
programmatic score says ``needs_judge``, and writes a separate
``judge_scores.jsonl``. It never mutates ``scores.jsonl``.
"""

import datetime as dt
import hashlib
import json
import pathlib
import re

import yaml

from ..backends.cloud import CloudBackend
from ..schema import SCHEMA_VERSION
from ..suite.loader import load_suite

JUDGE_SCORES = "judge_scores.jsonl"


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _key(row: dict) -> tuple[str, str, int]:
    return row["task_id"], row["model"], int(row["repeat"])


def _is_unpinned_model(model: str) -> bool:
    low = (model or "").strip().lower()
    return (
        not low
        or "edit me" in low
        or low in {"latest", "default"}
        or low.endswith(":latest")
    )


def _read_config(config_path: pathlib.Path) -> tuple[dict, str, str]:
    text = config_path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text) or {}
    model = str(cfg.get("model", ""))
    if _is_unpinned_model(model):
        raise SystemExit(
            f"{config_path}: judge model must be pinned before judging")
    protocol = cfg.get("protocol") or {}
    if protocol.get("mode") != "pairwise_position_swap":
        raise SystemExit(
            f"{config_path}: protocol.mode must be pairwise_position_swap")
    scale = protocol.get("scale", [0, 1])
    if scale != [0, 1]:
        raise SystemExit(f"{config_path}: protocol.scale must be [0, 1]")
    rubric_path = pathlib.Path(protocol.get("rubric", ""))
    if not rubric_path.is_absolute():
        rubric_path = config_path.parent / rubric_path
    if not rubric_path.exists():
        raise SystemExit(f"judge rubric not found: {rubric_path}")
    rubric = rubric_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return cfg, rubric, digest


def _last_json_object(text: str) -> dict | None:
    """Last well-formed top-level {...} object in text, or None.

    A greedy `\\{.*\\}` grabs from the first brace anywhere (e.g. in the judge's
    prose reasoning) to the last, which then fails to parse and — without this —
    aborts the whole judge pass. Brace-balanced scanning picks the final verdict
    object instead.
    """
    candidates = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start != -1:
                candidates.append(text[start:i + 1])
    for chunk in reversed(candidates):
        try:
            obj = json.loads(chunk)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _extract_json(text: str) -> dict:
    data = _last_json_object(text or "")
    if data is None:
        raise ValueError("judge returned no parseable JSON object")
    for key in ("score_a", "score_b"):
        val = data.get(key)
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise ValueError(f"judge JSON missing numeric {key}")
        if not 0 <= float(val) <= 1:
            raise ValueError(f"judge {key} outside [0, 1]: {val}")
        data[key] = float(val)
    winner = str(data.get("winner", "")).lower()
    if winner not in {"a", "b", "tie"}:
        raise ValueError("judge JSON winner must be A, B, or tie")
    data["winner"] = winner
    return data


def _judge_prompt(task: dict, rubric: str, cand_a: str, cand_b: str) -> str:
    return f"""Task id: {task["id"]}

Task prompt:
{task["prompt"]}

Reference output:
{task.get("oracle_text", "")}

Rubric:
{rubric}

Candidate A:
{cand_a}

Candidate B:
{cand_b}

Compare Candidate A and Candidate B as answers to the task. One candidate is
the reference answer, but do not award points for position. Grade both
candidates using the rubric against the task prompt and source material.

Return JSON only with this exact shape:
{{
  "winner": "A" | "B" | "tie",
  "score_a": 0.0,
  "score_b": 0.0,
  "rationale": "brief rubric-grounded reason"
}}
"""


def _call_judge(backend: CloudBackend, model: str, task: dict, rubric: str,
                cand_a: str, cand_b: str, max_tokens: int,
                temperature: float) -> dict:
    system = (
        "You are the Metis tier-2 benchmark judge. You must follow the rubric, "
        "avoid position bias, and return only valid JSON."
    )
    prompt = _judge_prompt(task, rubric, cand_a, cand_b)
    res = backend.generate(
        model, system, prompt,
        {"temperature": temperature, "num_predict": max_tokens})
    if res.error:
        raise RuntimeError(f"judge API error: {res.error}")
    data = _extract_json(res.content)
    data["usage"] = {
        "prompt_tokens": res.prompt_tokens,
        "output_tokens": res.output_tokens,
        "wall_s": round(res.wall_s, 3),
        "ttft_s": round(res.ttft_s, 3),
    }
    return data


def _score_pair(backend: CloudBackend, model: str, task: dict, rubric: str,
                candidate: str, max_tokens: int,
                temperature: float) -> tuple[float, dict]:
    reference = task.get("oracle_text")
    if not reference:
        raise ValueError(f"{task['id']}: needs_judge task lacks oracle_text")
    ab = _call_judge(backend, model, task, rubric, candidate, reference,
                     max_tokens, temperature)
    ba = _call_judge(backend, model, task, rubric, reference, candidate,
                     max_tokens, temperature)
    score = (ab["score_a"] + ba["score_b"]) / 2
    details = {
        "position_swap": {
            "candidate_as_a": ab,
            "candidate_as_b": ba,
        },
        "reference_scores": {
            "as_b": ab["score_b"],
            "as_a": ba["score_a"],
        },
    }
    return score, details


def _zero_row(rec: dict, tier1: dict, judge_meta: dict, reason: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": rec["task_id"],
        "category": rec["category"],
        "model": rec["model"]["name"],
        "repeat": rec["repeat"],
        "score": 0.0,
        "needs_judge": True,
        "judge_applied": True,
        "judge": judge_meta,
        "details": {
            "tier1_score": tier1.get("score"),
            "reason": reason,
        },
    }


def judge_run(run_dir, config_path="config/judge.yaml") -> dict:
    run = pathlib.Path(run_dir)
    cfg_path = pathlib.Path(config_path)
    cfg, rubric, cfg_hash = _read_config(cfg_path)
    provider = cfg.get("provider", "anthropic")
    model = cfg["model"]
    max_tokens = int(cfg.get("max_tokens", 768))
    temperature = float(cfg.get("temperature", 0))
    backend = CloudBackend(
        provider=provider,
        base_url=cfg.get("base_url"),
        api_key_env=cfg.get("api_key_env"),
        api_version=cfg.get("api_version"),
        timeout_s=int(cfg.get("timeout_s", 600)),
    )

    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    suite = load_suite(manifest.get("suite_dir", "v1"))
    tasks = {t["id"]: t for t in suite["tasks"]}
    records = _load_jsonl(run / "records.jsonl")
    scores = _load_jsonl(run / "scores.jsonl")
    score_map = {_key(s): s for s in scores}

    judge_meta = {
        "provider": provider,
        "model": model,
        "backend_version": backend.version(),
        "settings": backend.settings(),
        "options": {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout_s": int(cfg.get("timeout_s", 600)),
        },
        "protocol": cfg.get("protocol", {}),
        "config_path": str(cfg_path),
        "config_sha256": cfg_hash,
    }

    rows = []
    judged = skipped_errors = judge_errors = 0
    missing_tier1 = []
    for rec in records:
        key = (rec["task_id"], rec["model"]["name"], int(rec["repeat"]))
        tier1 = score_map.get(key)
        if tier1 is None:
            missing_tier1.append(key)
            continue
        if not tier1.get("needs_judge"):
            continue
        if rec.get("error"):
            rows.append(_zero_row(
                rec, tier1, judge_meta,
                f"generation error: {rec.get('error')}"))
            skipped_errors += 1
            continue
        task = tasks.get(rec["task_id"])
        if task is None:
            raise SystemExit(f"unknown task in records: {rec['task_id']}")
        candidate = (rec.get("output") or {}).get("content", "")
        try:
            score, details = _score_pair(
                backend, model, task, rubric, candidate, max_tokens, temperature)
        except Exception as e:
            # One judge failure must not abort the whole pass. Record a
            # null-score row so the report falls back to this row's tier-1 score.
            rows.append({
                "schema_version": SCHEMA_VERSION,
                "task_id": rec["task_id"],
                "category": rec["category"],
                "model": rec["model"]["name"],
                "repeat": rec["repeat"],
                "score": None,
                "needs_judge": True,
                "judge_applied": False,
                "judge": judge_meta,
                "details": {"tier1_score": tier1.get("score"),
                            "judge_error": f"{type(e).__name__}: {e}"},
            })
            judge_errors += 1
            continue
        row = {
            "schema_version": SCHEMA_VERSION,
            "task_id": rec["task_id"],
            "category": rec["category"],
            "model": rec["model"]["name"],
            "repeat": rec["repeat"],
            "score": score,
            "needs_judge": True,
            "judge_applied": True,
            "judge": judge_meta,
            "details": {"tier1_score": tier1.get("score"), **details},
        }
        rows.append(row)
        judged += 1

    out_path = run / JUDGE_SCORES
    tmp_path = run / f"{JUDGE_SCORES}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for row in rows:
            row["judged_at"] = dt.datetime.now().astimezone().isoformat()
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp_path.replace(out_path)
    return {
        "judge_rows": len(rows),
        "api_judged": judged,
        "generation_errors_scored_zero": skipped_errors,
        "judge_failures_fell_back_to_tier1": judge_errors,
        "missing_tier1_scores": [list(k) for k in missing_tier1],
        "out": str(out_path),
    }
