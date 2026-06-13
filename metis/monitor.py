"""Background hardware sampling around one generation.

Reader preference: NVML (pynvml) > nvidia-smi polling > CPU/RAM only.
Energy is integrated from power samples, so it undercounts generations shorter
than a couple of sample intervals — this caveat is documented in METHODOLOGY.
"""

import subprocess
import threading
import time

import psutil


class _NvmlReader:
    def __init__(self):
        import pynvml  # optional dependency
        pynvml.nvmlInit()
        self._nv = pynvml
        self._h = pynvml.nvmlDeviceGetHandleByIndex(0)

    def read(self) -> dict:
        nv, h = self._nv, self._h
        mem = nv.nvmlDeviceGetMemoryInfo(h)
        out = {"vram_mb": mem.used / 2**20}
        try:
            out["power_w"] = nv.nvmlDeviceGetPowerUsage(h) / 1000.0
        except Exception:
            pass
        try:
            out["temp_c"] = nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU)
        except Exception:
            pass
        try:
            out["gpu_util"] = nv.nvmlDeviceGetUtilizationRates(h).gpu
        except Exception:
            pass
        return out


class _SmiReader:
    QUERY = "memory.used,power.draw,temperature.gpu,utilization.gpu"

    def __init__(self):
        self.read()  # raises if nvidia-smi unavailable

    def read(self) -> dict:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={self.QUERY}",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        parts = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",")]
        sample = {}
        keys = ("vram_mb", "power_w", "temp_c", "gpu_util")
        for k, v in zip(keys, parts):
            try:
                sample[k] = float(v)
            except ValueError:
                pass  # "[N/A]" on some cards/drivers
        return sample


def _make_gpu_reader():
    try:
        return _NvmlReader(), "nvml"
    except Exception:
        pass
    try:
        return _SmiReader(), "nvidia-smi"
    except Exception:
        return None, "none"


class Monitor:
    def __init__(self, interval_s: float = 0.5):
        self.interval = interval_s
        self._samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._gpu, self.gpu_source = _make_gpu_reader()
        self._t0 = 0.0

    def _loop(self):
        while not self._stop.is_set():
            s = {"t": time.perf_counter()}
            if self._gpu is not None:
                try:
                    s.update(self._gpu.read())
                except Exception:
                    pass
            vm = psutil.virtual_memory()
            s["ram_mb"] = (vm.total - vm.available) / 2**20
            s["cpu_pct"] = psutil.cpu_percent(interval=None)
            self._samples.append(s)
            self._stop.wait(self.interval)

    def start(self):
        psutil.cpu_percent(interval=None)  # prime the non-blocking counter
        self._t0 = time.perf_counter()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        dur = time.perf_counter() - self._t0
        return self._summarise(dur)

    def _series(self, key):
        return [s[key] for s in self._samples if key in s]

    def _summarise(self, duration_s: float) -> dict:
        out = {
            "samples": len(self._samples),
            "duration_s": round(duration_s, 3),
            "gpu_source": self.gpu_source,
        }
        for key, name in (("vram_mb", "vram"), ("ram_mb", "ram")):
            vals = self._series(key)
            if vals:
                out[f"{name}_peak_mb"] = round(max(vals), 1)
                out[f"{name}_avg_mb"] = round(sum(vals) / len(vals), 1)
        power = self._series("power_w")
        if power:
            out["power_avg_w"] = round(sum(power) / len(power), 1)
            out["power_max_w"] = round(max(power), 1)
            # trapezoidal-ish: avg power over the wall duration
            out["energy_j"] = round(sum(power) / len(power) * duration_s, 1)
        temps = self._series("temp_c")
        if temps:
            out["temp_max_c"] = max(temps)
        util = self._series("gpu_util")
        if util:
            out["gpu_util_avg"] = round(sum(util) / len(util), 1)
        cpu = self._series("cpu_pct")
        if cpu:
            out["cpu_avg_pct"] = round(sum(cpu) / len(cpu), 1)
        return out
