"""
Security configuration and middleware for vLLM Intel Arc Dashboard.
Handles CORS policy, API key verification, and network detection.
"""

import os
import socket
import logging
from typing import List
from ipaddress import ip_address, ip_network

logger = logging.getLogger(__name__)


def get_local_network_ips() -> List[str]:
    """
    Auto-detects local network IPs and builds CORS allowed origins.
    
    Includes:
    - localhost (127.0.0.1, ::1)
    - Local machine IP (detected via hostname)
    - Tailscale network (100.64.0.0/10)
    
    Returns:
        List of allowed CORS origins
    """
    origins = [
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    ]
    
    # Try to detect local machine IP
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        if local_ip and local_ip != "127.0.0.1":
            origins.append(f"http://{local_ip}:5000")
            logger.info(f"Auto-detected local IP: {local_ip}")
    except (socket.gaierror, OSError) as e:
        logger.warning(f"Could not auto-detect local IP: {e}")
    
    # Add Tailscale IP range (100.64.0.0/10)
    # Clients on Tailscale will connect from this range
    origins.append("http://100.*:5000")  # Wildcard pattern for Tailscale
    
    return origins


def verify_origin(origin: str, allowed_origins: List[str]) -> bool:
    """
    Verifies if an origin is in the allowed list.
    Supports wildcard patterns (e.g., 100.*).
    
    Args:
        origin: The origin to verify
        allowed_origins: List of allowed origins (may contain wildcards)
        
    Returns:
        True if origin is allowed
    """
    for allowed in allowed_origins:
        if "*" in allowed:
            # Wildcard pattern matching (e.g., "100.*")
            pattern = allowed.replace("*", ".*")
            import re
            if re.match(f"^{pattern}$", origin):
                return True
        elif origin == allowed:
            return True
    
    return False


class SecurityConfig:
    """
    Central security configuration for the application.
    """
    
    # CORS: Dashboard & web clients on local network + Tailscale
    DASHBOARD_ORIGINS = get_local_network_ips()
    
    # Endpoints that require API Key (protect server resources)
    PROTECTED_ENDPOINTS = {
        "/api/image/pull",      # Pulls Docker image (bandwidth)
        "/api/start",           # Starts container (CPU, VRAM)
        "/api/stop",            # Stops container
        "/api/rm-container",    # Removes container
        "/api/models/download", # Downloads model from HF (bandwidth, disk)
        "/api/models/delete",   # Deletes model from disk
    }
    
    # Endpoints that are public (inference is the product)
    PUBLIC_ENDPOINTS = {
        "/v1/chat/completions",
        "/v1/completions",
        "/v1/models",
        "/v1/embeddings",
        "/api/tags",            # Ollama compatibility
        "/api/ps",
        "/api/version",
        "/health",              # Health check endpoint
        "/",                    # Dashboard HTML
        "/docs",                # Swagger docs
        "/redoc",               # ReDoc docs
    }
    
    # Get API key from environment
    API_KEY = os.getenv("API_KEY", "")
    
    @classmethod
    def require_api_key_for_endpoint(cls, path: str, method: str) -> bool:
        """
        Determines if an endpoint requires API key authentication.
        
        Args:
            path: The request path
            method: The HTTP method
            
        Returns:
            True if API key is required
        """
        # Only POST/PUT/DELETE on protected endpoints
        if method not in {"POST", "PUT", "DELETE"}:
            return False
        
        # Check if path starts with any protected endpoint
        for endpoint in cls.PROTECTED_ENDPOINTS:
            if path.startswith(endpoint):
                return True
        
        return False
    
    @classmethod
    def verify_api_key(cls, provided_key: str) -> bool:
        """
        Verifies if the provided API key is correct.
        
        Args:
            provided_key: The API key from the request header
            
        Returns:
            True if key is valid (or no key is configured)
        """
        # If no API key is configured, all requests are allowed
        if not cls.API_KEY:
            logger.warning("No API_KEY configured in environment - protected endpoints are unprotected!")
            return True
        
        return provided_key == cls.API_KEY


def log_denied_request(path: str, method: str, reason: str, origin: str = None):
    """
    Logs denied security requests for audit purposes.
    
    Args:
        path: The requested path
        method: The HTTP method
        reason: Reason for denial
        origin: The request origin (if available)
    """
    logger.warning(
        f"Security denied - {method} {path} | Reason: {reason} | Origin: {origin or 'N/A'}"
    )
