import time
import pytest
from app.cache import SimpleCache, cache, get_cache, CACHE_KEYS

def test_simple_cache_set_get():
    c = SimpleCache()
    c.set("foo", "bar", ttl_seconds=10)
    assert c.get("foo") == "bar"
    assert c.get("non_existent") is None

def test_simple_cache_expiration():
    c = SimpleCache()
    c.set("short_lived", 123, ttl_seconds=0.1)
    assert c.get("short_lived") == 123
    time.sleep(0.15)
    assert c.get("short_lived") is None

def test_simple_cache_invalidation():
    c = SimpleCache()
    c.set("key1", "val1", ttl_seconds=100)
    assert c.get("key1") == "val1"
    c.invalidate("key1")
    assert c.get("key1") is None

def test_cache_decorator():
    call_count = 0

    @cache(ttl_seconds=5)
    def compute_heavy(x):
        nonlocal call_count
        call_count += 1
        return x * 2

    # First call - MISS
    res1 = compute_heavy(10)
    assert res1 == 20
    assert call_count == 1

    # Second call - HIT
    res2 = compute_heavy(10)
    assert res2 == 20
    assert call_count == 1

def test_cache_keys_match_real_functions():
    from app.podman_cli import scan_models, get_container_status
    from app.gpu_mon import get_intel_gpu_vram

    # Run functions once to ensure cached
    scan_models()
    get_container_status()
    get_intel_gpu_vram()

    cache_inst = get_cache()
    stats = cache_inst.get_stats()

    # The actual keys cached must match CACHE_KEYS
    for name, key in CACHE_KEYS.items():
        assert key in stats["keys"], f"Key '{key}' for '{name}' not found in cache keys: {stats['keys']}"
