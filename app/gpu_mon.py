import os
import glob
import psutil
import re
import subprocess
from pathlib import Path
from typing import Optional
from app.logging_config import logger
from app.cache import cache

# Default VRAM if auto-detection fails
DEFAULT_TOTAL_VRAM_MB = 12288.0  # Intel Arc B580: 12GB GDDR6 (192-bit)

# Runtime VRAM (will be auto-detected)
TOTAL_VRAM_MB = DEFAULT_TOTAL_VRAM_MB


def detect_gpu_vram() -> int:
    """
    Auto-detect Intel Arc GPU VRAM using multiple methods without hardcoded PCI slots.
    
    Returns:
        VRAM in MB. Returns DEFAULT_TOTAL_VRAM_MB if detection fails.
    """
    from app.config import get_config
    config = get_config()
    if config.gpu.total_vram_mb:
        return config.gpu.total_vram_mb
        
    vram_mb = None
    
    PCI_ID_TO_VRAM = {
        "e20b": 12288,  # B580
        "e20c": 10240,  # B570
        "56a0": 16384,  # A770 16GB
        "56a1": 8192,   # A750 8GB
        "56a2": 8192,   # A580 8GB
        "56a5": 6144,   # A380 6GB
    }
    
    # Method 1: Check lspci for PCI IDs
    try:
        pci_devs = subprocess.run(
            ["lspci", "-nn", "-d", "8086:"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if pci_devs.returncode == 0:
            for line in pci_devs.stdout.splitlines():
                if "VGA" in line or "3D" in line or "Display" in line:
                    match = re.search(r'8086:([a-fA-F0-9]{4})', line)
                    if match:
                        dev_id = match.group(1).lower()
                        if dev_id in PCI_ID_TO_VRAM:
                            vram_mb = PCI_ID_TO_VRAM[dev_id]
                            logger.info(f"GPU VRAM auto-detected (PCI ID {dev_id}): {vram_mb}MB")
                            return vram_mb
    except Exception as e:
        logger.debug(f"lspci ID method failed: {e}")
        
    # Fallback
    logger.warning(f"GPU VRAM auto-detection failed, using default: {DEFAULT_TOTAL_VRAM_MB}MB")
    return int(DEFAULT_TOTAL_VRAM_MB)


def set_gpu_vram(vram_mb: int):
    """Set the GPU VRAM value (for testing or manual override)."""
    global TOTAL_VRAM_MB
    TOTAL_VRAM_MB = float(vram_mb)
    logger.info(f"GPU VRAM set to: {vram_mb}MB ({vram_mb/1024:.1f}GB)")


_last_energy_uj = None
_last_energy_time = None

@cache(ttl_seconds=1.0)
def get_intel_hwmon_metrics() -> dict:
    """
    Reads hardware sensor metrics (temperature, power draw, clock frequency)
    for Intel Arc GPU via sysfs and hwmon.
    """
    global _last_energy_uj, _last_energy_time
    import time
    
    temp_c = None
    power_w = None
    freq_mhz = None
    
    try:
        # Check hwmon devices under drm cards
        for hwmon_path in glob.glob("/sys/class/drm/card*/device/hwmon/hwmon*"):
            if temp_c is None:
                # Use label if possible or temp2_input for pkg
                for temp_file in ("temp2_input", "temp1_input"):
                    p = Path(hwmon_path) / temp_file
                    if p.exists():
                        try:
                            val = int(p.read_text().strip())
                            temp_c = round(val / 1000.0, 1)
                            break
                        except Exception:
                            pass

            if power_w is None:
                p_energy = Path(hwmon_path) / "energy1_input"
                if p_energy.exists():
                    try:
                        current_uj = int(p_energy.read_text().strip())
                        current_time = time.time()
                        if _last_energy_uj is not None and _last_energy_time is not None:
                            dt = current_time - _last_energy_time
                            if dt > 0:
                                duj = current_uj - _last_energy_uj
                                # delta microjoules / delta seconds = microwatts
                                power_w = round((duj / dt) / 1000000.0, 1)
                        _last_energy_uj = current_uj
                        _last_energy_time = current_time
                    except Exception:
                        pass
                else:
                    for power_file in ("power1_average", "power1_input"):
                        p = Path(hwmon_path) / power_file
                        if p.exists():
                            try:
                                val = int(p.read_text().strip())
                                power_w = round(val / 1000000.0, 1)
                                break
                            except Exception:
                                pass

        # Frequency from xe driver path: device/tile0/gt0/freq0/act_freq
        for gt_freq_path in glob.glob("/sys/class/drm/card*/device/tile0/gt0/freq0/act_freq"):
            try:
                val = int(Path(gt_freq_path).read_text().strip())
                freq_mhz = val
                break
            except Exception:
                pass
                
        if freq_mhz is None:
            # Fallback to older paths
            for gt_freq_path in glob.glob("/sys/class/drm/card*/gt/gt0/freq_cur"):
                try:
                    val = int(Path(gt_freq_path).read_text().strip())
                    freq_mhz = val
                    break
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Error reading hwmon metrics: {e}")

    return {
        "temperature_c": temp_c,
        "power_w": power_w,
        "frequency_mhz": freq_mhz
    }


@cache(ttl_seconds=1.0)
def get_intel_gpu_vram() -> dict:
    """
    Scans Linux DRM fdinfo in /proc/*/fdinfo/* to sum VRAM allocations
    under the Xe kernel driver for Intel Arc GPUs.
    """
    total_resident_kib = 0
    seen_clients = set()
    xe_processes_count = 0
    
    try:
        # Search all process fdinfo files for drm-driver: xe entries
        for fdinfo_path in glob.glob("/proc/[0-9]*/fdinfo/[0-9]*"):
            try:
                with open(fdinfo_path, "r", errors="ignore") as f:
                    content = f.read()
                    if "drm-driver:\txe" in content or "drm-driver: xe" in content:
                        client_id = None
                        client_vram = 0
                        is_xe = False
                        
                        for line in content.splitlines():
                            if line.startswith("drm-client-id:"):
                                client_id = line.split(":")[1].strip()
                            elif line.startswith("drm-resident-vram0:"):
                                parts = line.split(":")
                                if len(parts) >= 2:
                                    val_str = parts[1].strip().split()[0]
                                    try:
                                        client_vram = int(val_str)
                                    except ValueError:
                                        pass
                        
                        if client_id and client_vram > 0:
                            xe_processes_count += 1
                            if client_id not in seen_clients:
                                seen_clients.add(client_id)
                                total_resident_kib += client_vram
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
    Combines Intel Arc VRAM status, GPU hardware metrics (temp/power/clock),
    and host CPU / RAM metrics.
    """
    vram_data = get_intel_gpu_vram()
    hw_metrics = get_intel_hwmon_metrics()
    mem = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=None)

    return {
        "gpu_name": "Intel Arc B580 (Xe Driver)",
        "vram": vram_data,
        "hardware": hw_metrics,
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

