"""
Cache system with TTL support for FASE 3 - Performance Optimization

Provides:
- SimpleCache: Thread-safe cache with TTL and invalidation
- @cache decorator: Wrap functions to auto-cache their results
- Model metadata cache (30s)
- Health status cache (5s)
"""

import asyncio
import time
from typing import Any, Callable, Optional, TypeVar, Dict
from functools import wraps
from threading import Lock
import logging

logger = logging.getLogger("vllm_dashboard")

T = TypeVar('T')


class CacheEntry:
    """A single cache entry with TTL tracking"""
    def __init__(self, value: Any, ttl_seconds: float):
        self.value = value
        self.created_at = time.time()
        self.ttl_seconds = ttl_seconds
    
    def is_expired(self) -> bool:
        """Check if this entry has expired"""
        return (time.time() - self.created_at) > self.ttl_seconds
    
    def age_seconds(self) -> float:
        """Get age of this cache entry in seconds"""
        return time.time() - self.created_at


class SimpleCache:
    """Thread-safe cache with TTL support"""
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            if entry.is_expired():
                del self._cache[key]
                return None
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl_seconds: float = 300) -> None:
        """Set value in cache with TTL"""
        with self._lock:
            self._cache[key] = CacheEntry(value, ttl_seconds)
            logger.debug(f"Cache SET: {key} (TTL: {ttl_seconds}s)")
    
    def invalidate(self, key: str) -> None:
        """Manually invalidate a cache entry"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache INVALIDATE: {key}")
    
    def clear(self) -> None:
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()
            logger.info("Cache CLEARED")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total_entries = len(self._cache)
            expired = sum(1 for e in self._cache.values() if e.is_expired())
            valid = total_entries - expired
            
            return {
                "total_entries": total_entries,
                "valid_entries": valid,
                "expired_entries": expired,
                "keys": list(self._cache.keys())
            }


# Global cache instance
_global_cache = SimpleCache()


def cache(ttl_seconds: float = 300):
    """
    Decorator to cache function results with TTL
    
    Usage:
        @cache(ttl_seconds=30)
        def get_models():
            # Long operation...
            return [...]
    
    Args:
        ttl_seconds: Time to live for cached result
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache_key = f"{func.__module__}.{func.__name__}"
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Check cache first
            cached_value = _global_cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                return cached_value
            
            # Not cached, call function
            result = func(*args, **kwargs)
            
            # Cache the result
            _global_cache.set(cache_key, result, ttl_seconds)
            logger.debug(f"Cache MISS: {cache_key} (computed)")
            
            return result
        
        return wrapper
    
    return decorator


def async_cache(ttl_seconds: float = 300):
    """
    Decorator to cache async function results with TTL
    
    Usage:
        @async_cache(ttl_seconds=5)
        async def get_status():
            # Long async operation...
            return {...}
    
    Args:
        ttl_seconds: Time to live for cached result
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        cache_key = f"{func.__module__}.{func.__name__}"
        
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Check cache first
            cached_value = _global_cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Async Cache HIT: {cache_key}")
                return cached_value
            
            # Not cached, call async function
            result = await func(*args, **kwargs)
            
            # Cache the result
            _global_cache.set(cache_key, result, ttl_seconds)
            logger.debug(f"Async Cache MISS: {cache_key} (computed)")
            
            return result
        
        return wrapper
    
    return decorator


def get_cache() -> SimpleCache:
    """Get global cache instance"""
    return _global_cache


# Pre-defined cache keys for common operations
CACHE_KEYS = {
    "models": "app.podman_cli.scan_models",                  # scan_models() result
    "status": "app.podman_cli.get_container_status",        # container status
    "gpu_telemetry": "app.gpu_mon.get_intel_gpu_vram",      # GPU metrics
}
