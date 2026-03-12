"""
Redis service for ChaCC backbone.
Provides Redis client to modules via context.
"""

import os
from typing import Optional
from redis.asyncio import Redis

from src.logger import configure_logging, LogLevels
from src.constants import REDIS_ENABLED, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD

chacc_logger = configure_logging(log_level=LogLevels.INFO)


class RedisService:
    """
    Async Redis service for the backbone.
    Exposed to modules via BackboneContext.
    """

    def __init__(self):
        self._redis: Optional[Redis] = None
        self._host = REDIS_HOST
        self._port = REDIS_PORT
        self._db = REDIS_DB
        self._password = REDIS_PASSWORD
        self._enabled = REDIS_ENABLED
        self._connection_attempted = False
        self._connection_error: Optional[str] = None

    @property
    def is_enabled(self) -> bool:
        """Check if Redis is enabled"""
        return self._enabled

    @property
    def is_connected(self) -> bool:
        """Check if Redis is currently connected"""
        return self._redis is not None and self._connection_error is None

    @property
    def connection_error(self) -> Optional[str]:
        """Get the last connection error message if any"""
        return self._connection_error

    async def get_client(self) -> Optional[Redis]:
        """
        Get Redis client. Returns None if Redis is disabled or connection failed.
        """
        if not self._enabled:
            chacc_logger.info("Redis is disabled. Service not available.")
            return None

        # Return existing connection if already established
        if self._redis is not None and self._connection_error is None:
            return self._redis

        # Attempt connection if not already attempted or previous attempt failed
        if not self._connection_attempted or self._connection_error is not None:
            self._connection_attempted = True
            try:
                self._redis = Redis(
                    host=self._host,
                    port=self._port,
                    db=self._db,
                    password=self._password,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                await self._redis.ping()
                self._connection_error = None
                chacc_logger.info(f"Redis connected: {self._host}:{self._port}/{self._db}")
            except Exception as e:
                self._connection_error = str(e)
                chacc_logger.error(f"Failed to connect to Redis: {e}")
                if self._redis:
                    await self._redis.close()
                    self._redis = None

        return self._redis

    async def close(self):
        """Close Redis connection"""
        if self._redis is not None:
            try:
                await self._redis.close()
                chacc_logger.info("Redis connection closed.")
            except Exception as e:
                chacc_logger.warning(f"Error closing Redis connection: {e}")
            finally:
                self._redis = None
                self._connection_attempted = False
                self._connection_error = None
        else:
            chacc_logger.debug("Redis was not connected. No action taken on close.")
