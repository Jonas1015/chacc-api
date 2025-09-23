"""
ChaCC-specific wrapper for the Dependency Manager package.

This module provides ChaCC-specific functionality that integrates the
standalone dependency manager package with ChaCC's database and module system.
"""

import os
from typing import Dict, Optional
from chacc import DependencyManager


class ChaCCDependencyManager:
    """
    ChaCC-specific dependency manager that wraps the standalone package
    with database integration for module management.
    """

    def __init__(self, cache_dir: Optional[str] = None, logger=None):
        """Initialize with ChaCC-specific configuration."""
        # Use ChaCC's cache directory
        if cache_dir is None:
            from .constants import DEPENDENCY_CACHE_DIR
            cache_dir = DEPENDENCY_CACHE_DIR

        self.dm = DependencyManager(cache_dir=cache_dir, logger=logger)

    async def resolve_dependencies(self):
        """
        Resolve dependencies for all enabled ChaCC modules.

        This queries the database for enabled modules and their requirements,
        then uses the standalone dependency manager to resolve and install them.
        """
        from .database import get_db, ModuleRecord

        db = await anext(get_db())
        try:
            # Get all enabled modules from database
            enabled_modules = db.query(ModuleRecord).filter_by(is_enabled=True).all()

            # Build requirements dictionary
            modules_requirements = {}
            for module in enabled_modules:
                module_name = module.name
                module_meta = module.meta_data if module.meta_data else {}

                # Find requirements file for this module
                dependencies_file_name = module_meta.get("dependencies_file", "requirements.txt")
                from .constants import MODULES_LOADED_DIR
                module_req_path = os.path.join(MODULES_LOADED_DIR, module_name, dependencies_file_name)

                if os.path.exists(module_req_path):
                    with open(module_req_path, 'r') as f:
                        req_content = f.read()
                    modules_requirements[module_name] = req_content

            # Also include backbone requirements if they exist
            backbone_req_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
            if os.path.exists(backbone_req_path):
                with open(backbone_req_path, 'r') as f:
                    backbone_reqs = f.read()
                modules_requirements['backbone'] = backbone_reqs

            # Use the standalone dependency manager
            if modules_requirements:
                await self.dm.resolve_dependencies(modules_requirements)
            else:
                await self.dm.resolve_dependencies()  # Auto-discover

        finally:
            db.close()


# Convenience function for ChaCC
async def resolve_chacc_dependencies():
    """Resolve dependencies for all enabled ChaCC modules."""
    adm = ChaCCDependencyManager()
    await adm.resolve_dependencies()


# For backward compatibility - these functions now delegate to the package
invalidate_module_cache = DependencyManager().invalidate_module_cache
invalidate_dependency_cache = DependencyManager().invalidate_cache