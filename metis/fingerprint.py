"""Hardware identity for a run. The fingerprint_id hashes only fields that are
stable across reboots (CPU, RAM, GPUs, OS family) so the same box always maps
to the same id in aggregated datasets."""

import hashlib
import json
import platform
import subprocess

import psutil

from . import __version__


def _gpus() -> list[dict]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15,
        )
        gpus = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpus.append({"name": parts[0], "vram": parts[1], "driver": parts[2]})
        return gpus
    except Exception:
        return []


def _cpu_name() -> str:
    if platform.system() == "Windows":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Processor).Name"],
                capture_output=True, text=True, timeout=20,
            )
            name = out.stdout.strip()
            if name:
                return name
        except Exception:
            pass
    return platform.processor() or "unknown"


def collect(extra: dict | None = None) -> dict:
    fp = {
        "cpu": _cpu_name(),
        "cores_physical": psutil.cpu_count(logical=False),
        "cores_logical": psutil.cpu_count(logical=True),
        "ram_total_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "gpus": _gpus(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "metis": __version__,
    }
    stable = {k: fp[k] for k in ("cpu", "ram_total_gb", "gpus", "os")}
    fp["fingerprint_id"] = hashlib.sha256(
        json.dumps(stable, sort_keys=True).encode()
    ).hexdigest()[:12]
    if extra:
        fp.update(extra)
    return fp
