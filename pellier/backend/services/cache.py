"""
Valkey Cache Service — Distributed caching for embeddings and search results.

Uses Amazon ElastiCache for Valkey (Redis-compatible) when VALKEY_URL is configured.
Falls back to an in-memory TTL dict when Valkey is not available.
"""
import time
import logging
import json
import hashlib
from typing import Any, Optional

logger = logging.getLogger(__name__)

_hits = 0
_misses = 0
_sets = 0
_start_time = time.time()


class CacheService:
    """Unified cache backed by Valkey or an in-memory TTL dict."""

    def __init__(self, valkey_url: Optional[str], default_ttl: int = 300):
        self._default_ttl = default_ttl
        self._client = None
        self._fallback: dict[str, tuple[Any, float]] = {}
        self._mode = "memory"

        if valkey_url:
            try:
                import valkey
                self._client = valkey.from_url(
                    valkey_url, decode_responses=True, socket_connect_timeout=2
                )
                self._client.ping()
                self._mode = "valkey"
                logger.info(f"Valkey cache connected: {valkey_url.split('@')[-1]}")
            except Exception as e:
                logger.warning(f"Valkey unavailable ({e}) — using in-memory fallback")

    @property
    def mode(self) -> str:
        return self._mode

    @staticmethod
    def _make_key(namespace: str, raw: str) -> str:
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"pellier:{namespace}:{digest}"

    def get(self, namespace: str, raw_key: str) -> Optional[Any]:
        global _hits, _misses
        key = self._make_key(namespace, raw_key)
        try:
            if self._client:
                val = self._client.get(key)
                if val is not None:
                    _hits += 1
                    return json.loads(val)
            else:
                entry = self._fallback.get(key)
                if entry and time.time() < entry[1]:
                    _hits += 1
                    return entry[0]
                elif entry:
                    del self._fallback[key]
        except Exception as e:
            logger.debug(f"Cache get error: {e}")
        _misses += 1
        return None

    def set(self, namespace: str, raw_key: str, value: Any, ttl: Optional[int] = None) -> None:
        global _sets
        key = self._make_key(namespace, raw_key)
        ttl = ttl or self._default_ttl
        try:
            if self._client:
                self._client.setex(key, ttl, json.dumps(value))
            else:
                self._fallback[key] = (value, time.time() + ttl)
                if _sets % 500 == 0:
                    now = time.time()
                    self._fallback = {
                        k: v for k, v in self._fallback.items() if v[1] > now
                    }
            _sets += 1
        except Exception as e:
            logger.debug(f"Cache set error: {e}")

    def delete(self, namespace: str, raw_key: str) -> None:
        key = self._make_key(namespace, raw_key)
        try:
            if self._client:
                self._client.delete(key)
            else:
                self._fallback.pop(key, None)
        except Exception:
            pass

    def stats(self) -> dict:
        total = _hits + _misses
        base = {
            "mode": self._mode,
            "hits": _hits,
            "misses": _misses,
            "sets": _sets,
            "hit_rate": round(_hits / total, 4) if total > 0 else 0.0,
            "total_requests": total,
            "uptime_seconds": round(time.time() - _start_time),
        }
        if self._client:
            try:
                info = self._client.info("stats")
                keyspace = self._client.info("keyspace")
                base.update({
                    "valkey_hits": info.get("keyspace_hits", 0),
                    "valkey_misses": info.get("keyspace_misses", 0),
                    "total_keys": sum(
                        v.get("keys", 0) for v in keyspace.values()
                    ),
                    "used_memory_mb": round(
                        self._client.info("memory").get("used_memory", 0)
                        / 1024
                        / 1024,
                        2,
                    ),
                    "connected_clients": self._client.info("clients").get(
                        "connected_clients", 0
                    ),
                })
            except Exception:
                pass
        else:
            now = time.time()
            base["total_keys"] = sum(
                1 for _, (_, exp) in self._fallback.items() if exp > now
            )
        return base


_cache_service: Optional[CacheService] = None


def init_cache(valkey_url: Optional[str], default_ttl: int = 300) -> CacheService:
    global _cache_service
    _cache_service = CacheService(valkey_url, default_ttl)
    return _cache_service


def get_cache() -> Optional[CacheService]:
    return _cache_service
