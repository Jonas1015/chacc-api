"""Metadata management for ChaCC API modules.

Synchronises database records with the filesystem state, removing
records for modules that are no longer present on disk.
"""

import os
import shutil

from src.constants import MODULES_LOADED_DIR
from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())


def sync_database_with_filesystem(chacc_to_module_name: dict[str, str], existing_records: dict, db):
    """Remove DB records for modules that are no longer on disk.

    Args:
        chacc_to_module_name: Mapping of .chacc filename to module name.
        existing_records: Dict of existing DB records.
        db: Database session.
    """
    installed_module_names = set(chacc_to_module_name.values())

    for module_name, record in list(existing_records.items()):
        if module_name not in installed_module_names:
            db.delete(record)
            chacc_logger.warning(
                f"Module '{module_name}' record found in DB but not on disk. "
                f"Deleting record and its code."
            )
            loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
            if os.path.exists(loaded_module_dir):
                shutil.rmtree(loaded_module_dir)
