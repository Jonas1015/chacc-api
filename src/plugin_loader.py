"""
Plugin loading functionality for ChaCC API.

Supports both:
- Development mode: Load from plugins/ directory with hot reload
- Production mode: Load from .modules_loaded with optional hot reload
"""

import json
import os

from fastapi import FastAPI

from src.constants import (
    BASE_DIR,
    DEPENDENCY_CACHE_DIR,
    DEVELOPMENT_MODE,
    ENABLE_PLUGIN_DEPENDENCY_RESOLUTION,
    ENABLE_PLUGIN_HOT_RELOAD,
    MODULES_LOADED_DIR,
    PLUGIN_AUTO_DISCOVERY,
    PLUGINS_DIR,
)
from src.database import apply_deferred_schema_changes
from src.logger import configure_logging, get_default_log_level
from src.module_loader.loader import load_single_module

chacc_logger = configure_logging(log_level=get_default_log_level())


class ModuleState:
    """
    Tracks the state of loaded modules for hot reload functionality.
    """

    def __init__(self):
        self.file_hashes: dict[str, str] = {}

    def get_file_hash(self, module_path: str) -> str:
        """Calculate a hash of all Python files in a module directory."""
        import hashlib

        hasher = hashlib.md5()

        for root, dirs, files in os.walk(module_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]

            for file in sorted(files):
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "rb") as f:
                            hasher.update(f.read())
                    except (OSError, KeyError):
                        pass

        return hasher.hexdigest()

    def should_reload(self, module_name: str, module_path: str) -> bool:
        """Check if a module should be reloaded based on file changes."""
        if not ENABLE_PLUGIN_HOT_RELOAD:
            return False

        if not os.path.exists(module_path):
            return False

        current_hash = self.get_file_hash(module_path)
        stored_hash = self.file_hashes.get(module_name)

        if stored_hash is None or current_hash != stored_hash:
            self.file_hashes[module_name] = current_hash
            return True

        return False

    def track(self, module_name: str, module_path: str):
        """Track a module for change detection."""
        self.file_hashes[module_name] = self.get_file_hash(module_path)


_module_state = ModuleState()


def discover_modules_from_directory(directory: str) -> dict[str, dict]:
    """
    Discover all modules in a directory.

    Args:
        directory: Path to the modules directory (e.g., plugins/ or .modules_loaded/)

    Returns:
        Dict mapping module_name -> module_info
    """
    modules = {}

    if not os.path.isdir(directory):
        chacc_logger.warning(f"Modules directory not found: {directory}")
        return modules

    for entry in os.listdir(directory):
        module_path = os.path.join(directory, entry)

        if not os.path.isdir(module_path) or entry.startswith("."):
            continue

        meta_path = os.path.join(module_path, "module_meta.json")
        if not os.path.exists(meta_path):
            for subentry in os.listdir(module_path):
                subpath = os.path.join(module_path, subentry)
                if os.path.isdir(subpath) and not subentry.startswith("."):
                    meta_path = os.path.join(subpath, "module_meta.json")
                    if os.path.exists(meta_path):
                        module_path = subpath
                        break

        if not os.path.exists(meta_path):
            chacc_logger.debug(f"Skipping {entry}: no module_meta.json")
            continue

        try:
            with open(meta_path, "r") as f:
                meta_data = json.load(f)

            module_name = meta_data.get("name", entry)

            modules[module_name] = {
                "name": module_name,
                "module_path": module_path,
                "meta": meta_data,
            }

            chacc_logger.debug(f"Discovered module: {module_name}")
        except (OSError, KeyError) as e:
            chacc_logger.warning(f"Failed to read module_meta.json for {entry}: {e}")

    return modules


def discover_plugins() -> dict[str, dict]:
    """Discover plugins from plugins directory."""
    return discover_modules_from_directory(PLUGINS_DIR)


def discover_installed_modules() -> dict[str, dict]:
    """Discover installed modules from .modules_loaded directory."""
    return discover_modules_from_directory(MODULES_LOADED_DIR)


async def resolve_dependencies(modules: dict[str, dict], enabled_modules: list[str]):
    """Resolve dependencies for enabled modules."""
    if not ENABLE_PLUGIN_DEPENDENCY_RESOLUTION:
        return

    requirements = {}

    backbone_req_path = os.path.join(BASE_DIR, "requirements.txt")
    if os.path.exists(backbone_req_path):
        with open(backbone_req_path, "r") as f:
            requirements["backbone"] = f.read()

    for module_name, module_info in modules.items():
        module_path = module_info["module_path"]
        req_path = os.path.join(module_path, "requirements.txt")
        if os.path.exists(req_path):
            with open(req_path, "r") as f:
                requirements[module_name] = f.read()

    enabled_requirements = {
        k: v for k, v in requirements.items() if k in enabled_modules or k == "backbone"
    }

    if enabled_requirements:
        try:
            from chacc import DependencyManager

            dm = DependencyManager(cache_dir=DEPENDENCY_CACHE_DIR, logger=chacc_logger)
            await dm.resolve_dependencies(enabled_requirements)
            chacc_logger.info("Module dependencies resolved")
        except (ImportError, RuntimeError) as e:
            chacc_logger.warning(f"Dependency resolution failed: {e}")


async def load_dev_modules(
    app: FastAPI,
    backbone_context,
    only_modules: list[str] | None = None,
    exclude_modules: list[str] | None = None,
):
    """
    Load plugins from the plugins directory.

    Called when DEVELOPMENT_MODE=True
    """
    if not DEVELOPMENT_MODE and not PLUGIN_AUTO_DISCOVERY:
        return

    source = PLUGINS_DIR.split("/")[-1] if "/" in PLUGINS_DIR else PLUGINS_DIR

    chacc_logger.info(f"Discovering plugins from {source} directory...")

    modules = discover_plugins()
    if not modules:
        chacc_logger.info("No plugins found")
        return

    await _load_modules(
        app=app,
        backbone_context=backbone_context,
        modules=modules,
        only_modules=only_modules,
        exclude_modules=exclude_modules,
        source=source,
    )


async def _load_modules(
    app: FastAPI,
    backbone_context,
    modules: dict[str, dict],
    only_modules: list[str],
    exclude_modules: list[str],
    source: str,
):
    """Internal function to load modules."""
    modules_to_load = []
    for name in modules:
        if only_modules and name not in only_modules:
            continue
        if exclude_modules and name in exclude_modules:
            continue
        modules_to_load.append(name)

    if not modules_to_load:
        return

    chacc_logger.info(f"Loading {len(modules_to_load)} modules from {source}: {modules_to_load}")

    await resolve_dependencies(modules, modules_to_load)

    for module_name in modules_to_load:
        module_info = modules[module_name]

        if not _module_state.should_reload(module_name, module_info["module_path"]):
            chacc_logger.debug(f"Module '{module_name}' unchanged, skipping")
            continue

        chacc_logger.info(f"Discovering models for module: {module_name} from {source}")

        try:
            await load_single_module(
                module_name=module_name,
                module_path=module_info["module_path"],
                module_metadata=module_info["meta"],
                app=app,
                backbone_context=backbone_context,
                discover_only=True,
            )
            chacc_logger.info(f"Model discovery complete for module '{module_name}'")
        except Exception:
            chacc_logger.exception(f"Error discovering models for module '{module_name}'")

    try:
        from src.database import initialize_database_models

        initialize_database_models(backbone_context)
        chacc_logger.info("initialize_database_models completed.")
    except Exception:
        chacc_logger.exception("initialize_database_models failed")

    try:
        from src.migration.runner import run_migration

        chacc_logger.info("Running database migrations after model discovery...")
        await run_migration()
        chacc_logger.info("Database migrations completed.")
    except Exception:
        chacc_logger.exception("Migration failed")

    for module_name in modules_to_load:
        module_info = modules[module_name]

        chacc_logger.info(f"Loading module: {module_name} from {source}")

        try:
            success = await load_single_module(
                module_name=module_name,
                module_path=module_info["module_path"],
                module_metadata=module_info["meta"],
                app=app,
                backbone_context=backbone_context,
            )

            if success:
                _module_state.track(module_name, module_info["module_path"])
                chacc_logger.info(f"Module '{module_name}' loaded successfully")
            else:
                chacc_logger.error(f"Module '{module_name}' failed to load")

        except Exception:
            chacc_logger.exception(f"Error loading module '{module_name}'")

    try:
        if apply_deferred_schema_changes(backbone_context):
            chacc_logger.info("Deferred schema changes detected; running follow-up migration.")
            from src.migration.runner import run_migration

            await run_migration()
            chacc_logger.info("Deferred migration completed.")
    except Exception:
        chacc_logger.exception("Deferred schema migration failed")

    chacc_logger.info(f"Module loading from {source} completed")
