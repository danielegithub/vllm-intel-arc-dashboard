import pytest
from app.gpu_mon import get_system_telemetry, get_intel_gpu_vram, set_gpu_vram

def test_intel_gpu_vram():
    set_gpu_vram(16384)
    vram = get_intel_gpu_vram()
    assert "vram_total_mb" in vram
    assert vram["vram_total_mb"] == 16384
    assert "vram_used_mb" in vram
    assert "vram_percent" in vram
    assert 0.0 <= vram["vram_percent"] <= 100.0

def test_system_telemetry():
    telemetry = get_system_telemetry()
    assert "gpu_name" in telemetry
    assert "vram" in telemetry
    assert "system" in telemetry
    assert "cpu_percent" in telemetry["system"]
    assert "ram_percent" in telemetry["system"]
