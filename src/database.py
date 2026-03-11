"""
Backward compatibility re-exports from chacc_api.
"""

# Re-export from new location for backward compatibility
from src.chacc_api.database import ChaCCBaseModel, register_model, get_db
from src.chacc_api.database.database import (
    ModuleRecord,
    initialize_database_models,
    run_automatic_migration,
    metadata_obj,
    engine
)

__all__ = [
    "ChaCCBaseModel",
    "register_model",
    "get_db",
    "ModuleRecord",
    "initialize_database_models",
    "run_automatic_migration",
    "metadata_obj",
    "engine"
]
