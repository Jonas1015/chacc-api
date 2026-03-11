"""
Backward compatibility re-exports for services.
"""

# Re-export from canonical location
from src.redis_service import RedisService

__all__ = ["RedisService"]
