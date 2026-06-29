"""
sysmon.py - lightweight live system-load readings for the on-screen meter.

Reports CPU %, RAM %, and GPU % (utilisation and memory) for a small fixed
overlay in the UI. Designed to be cheap and never raise: every reading is
best-effort and degrades gracefully if a tool isn't present.

- CPU / RAM: psutil if installed, else a /proc fallback on Linux, else None.
- GPU: nvidia-smi (present on any machine with NVIDIA drivers - no Python
  package needed). Reports device-wide numbers so they match Task Manager,
  which matters because the model runs inside Ollama, a separate process.

None for any field means "couldn't read it" and the UI hides that gauge.
"""

import shutil
import subprocess


def _cpu_ram():
    """(cpu_percent, ram_percent, ram_used_gb, ram_total_gb) - any may be None."""
    # Preferred: psutil (accurate, cross-platform).
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.0)  # non-blocking; uses delta since last call
        vm = psutil.virtual_memory()
        return (
            round(cpu, 1),
            round(vm.percent, 1),
            round(vm.used / 1073741824, 1),
            round(vm.total / 1073741824, 1),
        )
    except Exception:
        pass
    # Fallback: Linux /proc for RAM (CPU left None - a one-shot CPU% needs sampling).
    try:
        total = used = None
        with open("/proc/meminfo") as f:
            info = {}
            for line in f:
                k, _, v = line.partition(":")
                info[k.strip()] = v.strip()
        total_kb = int(info["MemTotal"].split()[0])
        avail_kb = int(info.get("MemAvailable", info["MemFree"]).split()[0])
        total = total_kb / 1048576
        used = (total_kb - avail_kb) / 1048576
        pct = round((used / total) * 100, 1) if total else None
        return (None, pct, round(used, 1), round(total, 1))
    except Exception:
        pass
    # Fallback: Windows via PowerShell (no Python package needed). This keeps the
    # CPU/RAM gauges working even when psutil wasn't installed, so the meter is
    # never half-blank on a stock install.
    try:
        return _windows_cpu_ram()
    except Exception:
        return (None, None, None, None)


def _windows_cpu_ram():
    """CPU % and RAM via PowerShell CIM. Windows-only; returns Nones elsewhere.

    PowerShell is comparatively expensive to spawn, so the result is cached for a
    few seconds. The meter polls ~every 1.5s; without caching that would launch a
    PowerShell process each time and add its own load. psutil (the preferred path)
    has no such cost - this only runs when psutil isn't installed.
    """
    import sys as _sys
    import time as _time
    if not _sys.platform.startswith("win"):
        return (None, None, None, None)
    now = _time.monotonic()
    cached = _WIN_CACHE.get("val")
    if cached is not None and (now - _WIN_CACHE.get("t", 0)) < 3.0:
        return cached
    ps = (
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "$tot=[double]$os.TotalVisibleMemorySize;"          # KB
        "$free=[double]$os.FreePhysicalMemory;"             # KB
        "$cpu=(Get-CimInstance Win32_Processor | "
        "Measure-Object -Property LoadPercentage -Average).Average;"
        "$usedKB=$tot-$free;"
        "Write-Output (\"{0};{1};{2}\" -f $cpu,$usedKB,$tot)"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, timeout=5,
    )
    if out.returncode != 0 or not out.stdout.strip():
        return (None, None, None, None)
    cpu_s, used_kb_s, tot_kb_s = out.stdout.strip().split(";")
    cpu = float(cpu_s) if cpu_s not in ("", "null") else None
    used_gb = float(used_kb_s) / 1048576
    total_gb = float(tot_kb_s) / 1048576
    ram_pct = round((used_gb / total_gb) * 100, 1) if total_gb else None
    val = (
        round(cpu, 1) if cpu is not None else None,
        ram_pct,
        round(used_gb, 1),
        round(total_gb, 1),
    )
    _WIN_CACHE["val"] = val
    _WIN_CACHE["t"] = now
    return val


_WIN_CACHE = {}


def _gpu():
    """(gpu_util_percent, gpu_mem_percent, mem_used_gb, mem_total_gb, name) via nvidia-smi.

    Device-wide (matches Task Manager). All None if nvidia-smi isn't available.
    """
    if not shutil.which("nvidia-smi"):
        return (None, None, None, None, None)
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return (None, None, None, None, None)
        # First GPU only.
        line = out.stdout.strip().splitlines()[0]
        util_s, used_s, total_s, name = [p.strip() for p in line.split(",")]
        util = float(util_s)
        used_mb = float(used_s)
        total_mb = float(total_s)
        mem_pct = round((used_mb / total_mb) * 100, 1) if total_mb else None
        return (
            round(util, 1),
            mem_pct,
            round(used_mb / 1024, 1),
            round(total_mb / 1024, 1),
            name,
        )
    except Exception:
        return (None, None, None, None, None)


def read():
    """Return a dict of current load. Always succeeds; missing values are None."""
    cpu, ram_pct, ram_used, ram_total = _cpu_ram()
    g_util, g_mem_pct, g_used, g_total, g_name = _gpu()
    return {
        "cpu_percent": cpu,
        "ram_percent": ram_pct,
        "ram_used_gb": ram_used,
        "ram_total_gb": ram_total,
        "gpu_available": g_util is not None or g_mem_pct is not None,
        "gpu_percent": g_util,
        "gpu_mem_percent": g_mem_pct,
        "gpu_mem_used_gb": g_used,
        "gpu_mem_total_gb": g_total,
        "gpu_name": g_name,
    }
