"""Break-even economics: measured local cost (energy x tariff, plus optional
hardware amortisation) vs API-equivalent cost at configured per-token rates.

Honesty rules (METHODOLOGY §7): local is not free, a subscription is not a bag
of API tokens, and rates default to zero so stale prices can never masquerade
as current ones — the module refuses to compare until pricing.yaml is edited.
"""

import json
import pathlib

import yaml


def _load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def compute(run_dir, pricing_path="config/pricing.yaml") -> str:
    run = pathlib.Path(run_dir)
    cfg = yaml.safe_load(pathlib.Path(pricing_path).read_text(encoding="utf-8"))
    currency = cfg.get("currency", "USD")
    tariff = float(cfg.get("electricity_per_kwh", 0))
    amort = float(cfg.get("hardware_amortisation_per_hour", 0))
    api = cfg.get("api_reference") or {}
    rate_in = float(api.get("usd_per_mtok_input", 0))
    rate_out = float(api.get("usd_per_mtok_output", 0))
    fx = float(api.get("usd_to_local", 1.0))
    rates_configured = rate_in > 0 or rate_out > 0

    records = _load_jsonl(run / "records.jsonl")
    per_model: dict[str, dict] = {}
    for r in records:
        m = r["model"]["name"]
        d = per_model.setdefault(m, {"in": 0, "out": 0, "kwh": 0.0, "h": 0.0})
        d["in"] += r["timings"]["prompt_tokens"]
        d["out"] += r["timings"]["output_tokens"]
        d["kwh"] += r["monitor"].get("energy_j", 0) / 3.6e6
        d["h"] += r["timings"]["wall_s"] / 3600

    lines = [f"# Economics — {run.name}", ""]
    if tariff == 0:
        lines.append("> electricity_per_kwh is 0 in config/pricing.yaml — "
                     "local cost shown as energy only. Set your tariff.")
    if not rates_configured:
        lines.append("> API rates are not configured in config/pricing.yaml. "
                     "Set current rates from your provider's pricing page; "
                     "Metis deliberately ships no default prices.")
    lines += ["",
              f"| model | tokens in | tokens out | energy kWh | wall h | "
              f"local cost ({currency}) | API-equivalent ({currency}) |",
              "|---|---|---|---|---|---|---|"]
    for m, d in per_model.items():
        local = d["kwh"] * tariff + d["h"] * amort
        api_cost = ((d["in"] * rate_in + d["out"] * rate_out) / 1e6 * fx
                    if rates_configured else None)
        lines.append(
            f"| {m} | {d['in']:,} | {d['out']:,} | {d['kwh']:.4f} | "
            f"{d['h']:.2f} | {local:.4f} | "
            f"{f'{api_cost:.4f}' if api_cost is not None else 'configure rates'} |")
    lines += ["",
              "Interpretation: the API-equivalent column prices this run's "
              "exact token volumes at the configured per-token rates. Combine "
              "with the report's coverage table for the routing view: tasks "
              "the local model covers at your quality bar are the tokens you "
              "stop paying for.", ""]
    text = "\n".join(lines)
    (run / "economics.md").write_text(text, encoding="utf-8")
    return text
