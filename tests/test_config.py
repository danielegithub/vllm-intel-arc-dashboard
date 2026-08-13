import os
import pytest
from pathlib import Path
from app.config import ConfigLoader, get_config

def test_config_defaults():
    loader = ConfigLoader()
    config = loader.load(config_file=Path("non_existent_config.yaml"))
    
    assert config.server.port == 5000
    assert config.gpu.memory_utilization == 0.70
    assert config.podman.container_name == "vllm-intel-arc"

def test_config_env_overrides(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "6000")
    monkeypatch.setenv("GPU_MEMORY_UTILIZATION", "0.85")
    
    loader = ConfigLoader()
    config = loader.load(config_file=Path("non_existent_config.yaml"))
    
    assert config.server.port == 6000
    assert config.gpu.memory_utilization == 0.85
