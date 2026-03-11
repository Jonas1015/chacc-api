"""
Backward compatibility re-exports from chacc_api.
"""

# Re-export from new location for backward compatibility
from src.chacc_api.services import RedisService

__all__ = ["RedisService"]
