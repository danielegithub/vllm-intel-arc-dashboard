import os
import glob
import psutil
import re
from pathlib import Path
from typing import Optional
from app.logging_config import logger

# Default VRAM if auto-detection fails
DEFAULT_TOTAL_VRAM_MB = 16384.0  # Intel Arc B580 default 16GB VRAM

# Runtime VRAM (will be auto-detected)
TOTAL_VRAM_MB = DEFAULT_TOTAL_VRAM_MB


def detect_gpu_vram() -> int:
    """
    Auto-detect Intel Arc GPU VRAM using multiple methods.
    
    Returns:
        VRAM in MB. Returns DEFAULT_TOTAL_VRAM_MB if detection fails.
    """
    vram_mb = None
    
    # Method 1: Check lspci + grep for memory
    try:
        import subprocess
        result = subprocess.run(
            ["lspci", "-s", "0000:00:02.0", "-v"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Look for "Memory at" or "Prefetchable memory"
            for line in result.stdout.split('\n'):
                if "Memory" in line or "memory" in line:
                    # Try to extract size (e.g., "16384M", "16G")
                    match = re.search(r'(\d+)([GMK]?)', line)
                    if match:
                        size, unit = match.groups()
                        size = int(size)
                        if unit == 'G':
                            vram_mb = size * 1024
                        elif unit == 'M':
                            vram_mb = size
                        elif unit == 'K':
                            vram_mb = size // 1024
                        else:
                            vram_mb = size  # Assume MB
                        if vram_mb:
                            logger.info(f"GPU VRAM auto-detected (lspci): {vram_mb}MB")
                            return vram_mb
    except Exception as e:
        logger.debug(f"lspci method failed: {e}")
    
    # Method 2: Check /sys/kernel/debug/dri/0/gem_objects or similar
    try:
        for sysfs_path in glob.glob("/sys/kernel/debug/dri/*/gem_objects"):
            try:
                with open(sysfs_path, 'r') as f:
                    content = f.read()
                    # Try to find total memory info
                    match = re.search(r'total: (\d+)', content)
                    if match:
                        total_bytes = int(match.group(1))
                        vram_mb = total_bytes // (1024 * 1024)
                        logger.info(f"GPU VRAM auto-detected (sysfs): {vram_mb}MB")
                        return vram_mb
            except (PermissionError, FileNotFoundError):
                continue
    except Exception as e:
        logger.debug(f"sysfs method failed: {e}")
    
    # Method 3: Check drm modules info
    try:
        modinfo_result = subprocess.run(
            ["modinfo", "xe"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if modinfo_result.returncode == 0:
            for line in modinfo_result.stdout.split('\n'):
                if "vram" in line.lower() or "memory" in line.lower():
                    logger.debug(f"xe driver info: {line}")
    except Exception as e:
        logger.debug(f"modinfo method failed: {e}")
    
    # Fallback
    logger.warning(f"GPU VRAM auto-detection failed, using default: {DEFAULT_TOTAL_VRAM_MB}MB")
    return DEFAULT_TOTAL_VRAM_MB


from app.cache import cache

def set_gpu_vram(vram_mb: int):
    """Set the GPU VRAM value (for testing or manual override)."""
    global TOTAL_VRAM_MB
    TOTAL_VRAM_MB = vram_mb
    logger.info(f"GPU VRAM set to: {vram_mb}MB ({vram_mb/1024:.1f}GB)")


@cache(ttl_seconds=1.0)
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
