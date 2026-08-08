import functools
import json
import time
import asyncio
from typing import Any, Callable, Optional, Union
from .redis import redis_client
import structlog

logger = structlog.get_logger()

# L1 Cache (In-Memory)
# Structure: { key: { "value": val, "expire": timestamp } }
_l1_cache = {}

class MultiLevelCache:
    @staticmethod
    async def get(key: str) -> Optional[Any]:
        # Check L1
        now = time.time()
        if key in _l1_cache:
            entry = _l1_cache[key]
            if entry["expire"] > now:
                logger.debug(f"Cache Hit (L1): {key}")
                return entry["value"]
            else:
                del _l1_cache[key]
        
        # Check L2 (Redis)
        try:
            val = await redis_client.get(key)
            if val:
                logger.debug(f"Cache Hit (L2): {key}")
                try:
                    # Try to parse as JSON
                    decoded = json.loads(val)
                    # Populate L1 (Default 60s for L1 to reduce Redis hits)
                    _l1_cache[key] = {
                        "value": decoded,
                        "expire": now + 60
                    }
                    return decoded
                except:
                    # Return as string if not JSON
                    _l1_cache[key] = {
                        "value": val,
                        "expire": now + 60
                    }
                    return val
        except Exception as e:
            logger.error(f"Cache Get Error: {e}")
            
        return None

    @staticmethod
    async def set(key: str, value: Any, ttl: int):
        now = time.time()
        # Set L1
        _l1_cache[key] = {
            "value": value,
            "expire": now + ttl
        }
        
        # Set L2
        try:
            # Check if value is primitive or dict/list
            if isinstance(value, (dict, list)):
                val_str = json.dumps(value)
            else:
                val_str = str(value)
                
            await redis_client.set(key, val_str, ttl=ttl)
        except Exception as e:
            logger.error(f"Cache Set Error: {e}")

def cache_node(key_prefix: str, ttl: int, key_builder: Callable = None):
    """
    Decorator for caching async node functions.
    
    Args:
        key_prefix: Prefix for cache key
        ttl: Time to live in seconds
        key_builder: Optional function(state) -> str suffix. Defaults to state['user_id']
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(state: dict, *args, **kwargs):
            # Determine cache key suffix
            if key_builder:
                try:
                    suffix = key_builder(state)
                except Exception as e:
                    logger.warning(f"Key builder failed for {func.__name__}: {e}")
                    suffix = state.get("user_id", "unknown")
            else:
                suffix = state.get("user_id", "global")
                
            cache_key = f"{key_prefix}:{suffix}"
            
            # Try get from cache
            cached = await MultiLevelCache.get(cache_key)
            if cached:
                logger.info(f"Skipping node {func.__name__} (Cache Hit: {cache_key})")
                
                # If cached result is a dict, we return it.
                # IMPORTANT: We need to handle 'workflow_trace' if the graph expects it.
                # If cached data doesn't have trace, we might want to add a mock trace to avoid breaking logs.
                if isinstance(cached, dict) and "workflow_trace" not in cached:
                     # Add a simple trace marker
                     cached["workflow_trace"] = {
                         "node_id": func.__name__,
                         "status": "cached",
                         "timestamp": time.time()
                     }
                return cached

            # Execute Node
            result = await func(state, *args, **kwargs)
            
            # Cache result logic
            # Only skip caching when an AgentState dict explicitly asks to bypass generation.
            if isinstance(result, dict) and result.get("_skip_generation") is True:
                return result

            if result is not None:
                await MultiLevelCache.set(cache_key, result, ttl=ttl)
            
            return result
        return wrapper
    return decorator
