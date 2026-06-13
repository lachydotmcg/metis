"""Loads a frozen suite version from YAML. Suites are immutable: editing a
prompt or scoring spec means creating a new version directory, never changing
an existing one."""

import pathlib

import yaml

SUITE_DIR = pathlib.Path(__file__).parent

KNOWN_SCORING_TYPES = {
    "numeric_exact", "choice_exact", "constraints", "code_tests",
    "agentic_final",
}


def load_suite(version: str = "v1", include: list[str] | None = None) -> dict:
    base = SUITE_DIR / version
    if not base.is_dir():
        raise FileNotFoundError(f"no suite at {base}")
    tasks: list[dict] = []
    suite_version = None
    for f in sorted(base.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        suite_version = doc.get("version", suite_version)
        for t in doc["tasks"]:
            t["category"] = doc["category"]
            kind = t.get("scoring", {}).get("type")
            if kind not in KNOWN_SCORING_TYPES:
                raise ValueError(f"{t.get('id')}: unknown scoring type {kind!r}")
            tasks.append(t)
    ids = [t["id"] for t in tasks]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"duplicate task ids: {dupes}")
    if include:
        tasks = [t for t in tasks if any(pat in t["id"] for pat in include)]
    return {"version": suite_version or "1.0", "tasks": tasks}
