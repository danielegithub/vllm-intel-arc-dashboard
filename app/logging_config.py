"""
Structured logging configuration for vLLM Intel Arc Dashboard.
Provides both file and console logging with proper formatting.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


def setup_logging(
    name: str = "vllm_dashboard",
    log_level: str = "INFO",
    log_dir: Optional[Path] = None
) -> logging.Logger:
    """
    Configures structured logging for the application.
    
    Creates both file and console handlers with proper formatting.
    Logs are rotated automatically (10MB per file, 5 backups).
    
    Args:
        name: Logger name
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files (defaults to ~/.vllm-dashboard/logs)
        
    Returns:
        Configured logger instance
    """
    if log_dir is None:
        log_dir = Path.home() / ".vllm-dashboard" / "logs"
    
    # Create log directory
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Avoid duplicate handlers if called multiple times
    if logger.handlers:
        return logger
    
    # File handler with rotation
    log_file = log_dir / "app.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"Logging configured - Level: {log_level}, Log dir: {log_dir}")
    
    return logger


# Get module-level logger
logger = setup_logging()
