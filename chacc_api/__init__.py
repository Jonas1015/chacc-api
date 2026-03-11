"""
ChaCC API - Python SDK for ChaCC API development.

This package provides the core APIs that developers should import from
when building modules for the ChaCC API backbone.

Usage:
    from chacc_api import BackboneContext, ChaCCBaseModel, RedisService
    from chacc_api.database import register_model, get_db
"""

# Re-export core services
from src.core_services import BackboneContext

# Re-export database models and utilities
from src.database import (
    ChaCCBaseModel,
    register_model,
    get_db,
    ModuleRecord,
    initialize_database_models,
    run_automatic_migration,
    metadata_obj,
    engine
)

# Re-export services
from src.redis_service import RedisService

__all__ = [
    # Core
    "BackboneContext",
    # Database
    "ChaCCBaseModel",
    "register_model",
    "get_db",
    "ModuleRecord",
    "initialize_database_models",
    "run_automatic_migration",
    "metadata_obj",
    "engine",
    # Services
    "RedisService",
]
