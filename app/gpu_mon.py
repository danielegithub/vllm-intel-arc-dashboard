import os
import glob
import psutil

TOTAL_VRAM_MB = 16384.0  # Intel Arc B580 default 16GB VRAM

def get_intel_gpu_vram() -> dict:
    """
    Scans Linux DRM fdinfo in /proc/*/fdinfo/* to sum VRAM allocations
    under the Xe kernel driver for Intel Arc GPUs.
    """
    total_resident_kib = 0
    xe_processes_count = 0
    
    try:
        # Search all process fdinfo files for drm-driver: xe entries
        for fdinfo_path in glob.glob("/proc/[0-9]*/fdinfo/[0-9]*"):
            try:
                with open(fdinfo_path, "r", errors="ignore") as f:
                    content = f.read()
                    if "drm-driver:\txe" in content or "drm-driver: xe" in content:
                        xe_processes_count += 1
                        for line in content.splitlines():
                            if line.startswith("drm-resident-vram0:") or line.startswith("drm-total-vram0:"):
                                parts = line.split(":")
                                if len(parts) >= 2:
                                    val_str = parts[1].strip().split()[0]
                                    try:
                                        total_resident_kib += int(val_str)
                                    except ValueError:
                                        pass
            except (PermissionError, FileNotFoundError, ProcessLookupError):
                continue
    except Exception:
        pass

    vram_used_mb = round(total_resident_kib / 1024.0, 2)
    vram_free_mb = round(max(0.0, TOTAL_VRAM_MB - vram_used_mb), 2)
    vram_percent = round(min(100.0, (vram_used_mb / TOTAL_VRAM_MB) * 100.0), 1)

    return {
        "vram_total_mb": TOTAL_VRAM_MB,
        "vram_used_mb": vram_used_mb,
        "vram_free_mb": vram_free_mb,
        "vram_used_gb": round(vram_used_mb / 1024.0, 2),
        "vram_total_gb": round(TOTAL_VRAM_MB / 1024.0, 2),
        "vram_percent": vram_percent,
        "active_xe_fds": xe_processes_count
    }

def get_system_telemetry() -> dict:
    """
    Combines Intel Arc VRAM status with host CPU and System RAM metrics.
    """
    vram_data = get_intel_gpu_vram()
    mem = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=None)

    return {
        "gpu_name": "Intel Arc B580 (Xe Driver)",
        "vram": vram_data,
        "system": {
            "cpu_percent": cpu_percent,
            "ram_total_gb": round(mem.total / (1024 ** 3), 2),
            "ram_used_gb": round(mem.used / (1024 ** 3), 2),
            "ram_percent": mem.percent
        }
    }

if __name__ == "__main__":
    import json
    print(json.dumps(get_system_telemetry(), indent=2))
