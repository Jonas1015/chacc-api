"""
ChaCC API - Python SDK for ChaCC API development.

This package provides the core APIs that developers should import from
when building modules for the ChaCC API backbone.

Usage:
    from chacc_api import BackboneContext, ChaCCBaseModel, RedisService
    from chacc_api.database import get_db
"""

from src.core_services import BackboneContext
from src.database import (
    ChaCCBaseModel,
    ModuleRecord,
    apply_deferred_schema_changes,
    engine,
    get_db,
    initialize_database_models,
    metadata_obj,
    register_model,
)
from src.redis_service import RedisService

__all__ = [
    "BackboneContext",
    "ChaCCBaseModel",
    "ModuleRecord",
    "RedisService",
    "apply_deferred_schema_changes",
    "engine",
    "get_db",
    "initialize_database_models",
    "metadata_obj",
    "register_model",
]
