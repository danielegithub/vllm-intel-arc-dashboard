"""
Centralized configuration management for vLLM Intel Arc Dashboard.
Loads configuration from environment variables, .env file, and YAML files.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import json
import logging

try:
    import yaml
except ImportError:
    yaml = None

from app.logging_config import logger


@dataclass
class GPUConfig:
    """GPU-specific configuration."""
    memory_utilization: float = 0.70
    dtype: str = "float16"
    max_model_len: int = 2048
    # Auto-detected at runtime
    total_vram_mb: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_utilization": self.memory_utilization,
            "dtype": self.dtype,
            "max_model_len": self.max_model_len,
            "total_vram_mb": self.total_vram_mb
        }


@dataclass
class ServerConfig:
    """Server-specific configuration."""
    host: str = "0.0.0.0"
    port: int = 5000
    reload: bool = False
    log_level: str = "INFO"
    timeout_graceful_shutdown: int = 2


@dataclass
class PodmanConfig:
    """Podman/Container configuration."""
    container_name: str = "vllm-intel-arc"
    image_name: str = "docker.io/intel/vllm:0.17.0-xpu"
    image_pull_timeout: int = 600  # 10 minutes
    container_start_timeout: int = 120  # 2 minutes
    container_stop_timeout: int = 30  # 30 seconds


@dataclass
class ModelConfig:
    """Model management configuration."""
    models_dir: Path = field(default_factory=lambda: Path.home() / "my_models")
    auto_load_default_model: bool = False
    default_model: Optional[str] = None


@dataclass
class SecurityConfig:
    """Security configuration."""
    api_key: str = ""
    enable_cors: bool = True
    cors_origins: list = field(default_factory=list)  # Auto-populated


@dataclass
class Config:
    """Main configuration object combining all sections."""
    
    server: ServerConfig = field(default_factory=ServerConfig)
    gpu: GPUConfig = field(default_factory=GPUConfig)
    podman: PodmanConfig = field(default_factory=PodmanConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    # Metadata
    _config_file: Optional[Path] = None
    _loaded_from_yaml: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "server": self.server.__dict__,
            "gpu": self.gpu.to_dict(),
            "podman": self.podman.__dict__,
            "model": {
                "models_dir": str(self.model.models_dir),
                "auto_load_default_model": self.model.auto_load_default_model,
                "default_model": self.model.default_model
            },
            "security": {
                "api_key_set": bool(self.security.api_key),
                "enable_cors": self.security.enable_cors,
                "cors_origins_count": len(self.security.cors_origins)
            },
            "_config_file": str(self._config_file) if self._config_file else None,
            "_loaded_from_yaml": self._loaded_from_yaml
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert config to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class ConfigLoader:
    """Loads configuration from various sources with proper precedence."""
    
    def __init__(self):
        self.config = Config()
    
    def load(self, config_file: Optional[Path] = None) -> Config:
        """
        Load configuration from all sources in order:
        1. Defaults (Config class defaults)
        2. YAML file (if exists and specified)
        3. Environment variables (override everything)
        
        Args:
            config_file: Path to YAML config file (defaults to ./vllm-dashboard.yaml)
            
        Returns:
            Loaded Config object
        """
        # Step 1: Load from YAML if available
        if config_file is None:
            config_file = Path("vllm-dashboard.yaml")
        
        if config_file.exists():
            self._load_yaml(config_file)
            logger.info(f"Loaded configuration from YAML: {config_file}")
        else:
            logger.debug(f"No YAML config file found at {config_file}")
        
        # Step 2: Override with environment variables
        self._load_env_vars()
        
        # Step 3: Validate and post-process
        self._post_process()
        
        logger.info(f"Configuration loaded successfully")
        return self.config
    
    def _load_yaml(self, config_file: Path):
        """Load configuration from YAML file."""
        if yaml is None:
            logger.warning("PyYAML not installed - skipping YAML config")
            return
        
        try:
            with open(config_file, 'r') as f:
                data = yaml.safe_load(f)
            
            if data is None:
                logger.warning(f"Empty YAML file: {config_file}")
                return
            
            # Load server config
            if "server" in data:
                for key, value in data["server"].items():
                    if hasattr(self.config.server, key):
                        setattr(self.config.server, key, value)
            
            # Load GPU config
            if "gpu" in data:
                for key, value in data["gpu"].items():
                    if hasattr(self.config.gpu, key):
                        setattr(self.config.gpu, key, value)
            
            # Load Podman config
            if "podman" in data:
                for key, value in data["podman"].items():
                    if hasattr(self.config.podman, key):
                        setattr(self.config.podman, key, value)
            
            # Load Model config
            if "model" in data:
                for key, value in data["model"].items():
                    if key == "models_dir":
                        value = Path(value).expanduser()
                    if hasattr(self.config.model, key):
                        setattr(self.config.model, key, value)
            
            # Load Security config
            if "security" in data:
                for key, value in data["security"].items():
                    if hasattr(self.config.security, key):
                        setattr(self.config.security, key, value)
            
            self.config._config_file = config_file
            self.config._loaded_from_yaml = True
            
        except Exception as e:
            logger.error(f"Error loading YAML config from {config_file}: {e}")
            raise
    
    def _load_env_vars(self):
        """Load configuration from environment variables."""
        # Server config
        if "SERVER_HOST" in os.environ:
            self.config.server.host = os.getenv("SERVER_HOST")
        if "SERVER_PORT" in os.environ:
            self.config.server.port = int(os.getenv("SERVER_PORT", "5000"))
        if "LOG_LEVEL" in os.environ:
            self.config.server.log_level = os.getenv("LOG_LEVEL")
        if "RELOAD" in os.environ:
            self.config.server.reload = os.getenv("RELOAD").lower() in ("true", "1", "yes")
        
        # GPU config
        if "GPU_MEMORY_UTILIZATION" in os.environ:
            self.config.gpu.memory_utilization = float(os.getenv("GPU_MEMORY_UTILIZATION"))
        if "DEFAULT_DTYPE" in os.environ:
            self.config.gpu.dtype = os.getenv("DEFAULT_DTYPE")
        if "MAX_MODEL_LEN" in os.environ:
            self.config.gpu.max_model_len = int(os.getenv("MAX_MODEL_LEN"))
        
        # Podman config
        if "CONTAINER_NAME" in os.environ:
            self.config.podman.container_name = os.getenv("CONTAINER_NAME")
        if "IMAGE_NAME" in os.environ:
            self.config.podman.image_name = os.getenv("IMAGE_NAME")
        if "IMAGE_PULL_TIMEOUT" in os.environ:
            self.config.podman.image_pull_timeout = int(os.getenv("IMAGE_PULL_TIMEOUT"))
        if "CONTAINER_START_TIMEOUT" in os.environ:
            self.config.podman.container_start_timeout = int(os.getenv("CONTAINER_START_TIMEOUT"))
        
        # Model config
        if "MODELS_DIR" in os.environ:
            self.config.model.models_dir = Path(os.getenv("MODELS_DIR")).expanduser()
        if "DEFAULT_MODEL" in os.environ:
            self.config.model.default_model = os.getenv("DEFAULT_MODEL")
        
        # Security config
        if "API_KEY" in os.environ:
            self.config.security.api_key = os.getenv("API_KEY")
    
    def _post_process(self):
        """Post-process and validate configuration."""
        # Ensure models directory exists
        self.config.model.models_dir.mkdir(parents=True, exist_ok=True)
        
        # Expand user paths
        if "~" in str(self.config.model.models_dir):
            self.config.model.models_dir = self.config.model.models_dir.expanduser()
        
        # Validate port range
        if not (1 <= self.config.server.port <= 65535):
            logger.warning(f"Invalid port {self.config.server.port}, using default 5000")
            self.config.server.port = 5000
        
        # Validate GPU settings
        if not (0.0 < self.config.gpu.memory_utilization <= 1.0):
            logger.warning(f"Invalid GPU memory utilization, using default 0.70")
            self.config.gpu.memory_utilization = 0.70
        
        if self.config.gpu.max_model_len < 128:
            logger.warning(f"max_model_len too small, using minimum 128")
            self.config.gpu.max_model_len = 128
        
        logger.debug(f"Configuration post-processing complete")


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get the global configuration instance.
    Loads it if not already loaded.
    """
    global _config
    
    if _config is None:
        loader = ConfigLoader()
        _config = loader.load()
    
    return _config


def reload_config(config_file: Optional[Path] = None) -> Config:
    """
    Reload configuration from scratch.
    Useful for testing or hot-reload scenarios.
    """
    global _config
    
    loader = ConfigLoader()
    _config = loader.load(config_file)
    
    return _config
