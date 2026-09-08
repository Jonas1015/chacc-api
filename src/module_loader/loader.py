"""Core module loading orchestration for ChaCC API.

Coordinates the full module loading pipeline: scanning .chacc archives,
validating and resolving Python dependencies, extracting archives,
synchronising the database, and mounting enabled modules into the FastAPI application.
"""

import importlib
import inspect
import json
import os
import sys

from fastapi import APIRouter, FastAPI

from src.constants import DEPENDENCY_CACHE_DIR, MODULES_INSTALLED_DIR, MODULES_LOADED_DIR
from src.core_services import BackboneContext
from src.database import (
    ModuleRecord,
    apply_deferred_schema_changes,
    get_db,
    initialize_database_models,
)
from src.logger import configure_logging, get_default_log_level

from .archive import (
    collect_module_requirements,
    extract_module_names_from_chacc_files,
    process_module_archives,
    unzip_modules,
)
from .discovery import discover_and_import_models
from .metadata import sync_database_with_filesystem

chacc_logger = configure_logging(log_level=get_default_log_level())


async def load_single_module(
    module_name: str,
    module_path: str,
    module_metadata: dict,
    app: FastAPI,
    backbone_context: BackboneContext,
    base_path_prefix: str | None = None,
    tags: list | None = None,
    discover_only: bool = False,
) -> bool:
    """Load a single module into the application.

    Handles async module loading — no database or filesystem operations.
    All required data is supplied via parameters. Supports sync and async
    entry-point setup functions.

    Args:
        module_name: Name of the module.
        module_path: Path to the module directory.
        module_metadata: Module metadata dict from module_meta.json.
        app: FastAPI application.
        backbone_context: BackboneContext for the module.
        base_path_prefix: Override the base path prefix.
        tags: Override the FastAPI route tags.
        discover_only: If True, only discover models without running setup.

    Returns:
        True if the module loaded successfully, False otherwise.
    """

    chacc_logger.info(f"Loading module '{module_name}' from path: {module_path}")

    if not os.path.isdir(module_path):
        chacc_logger.error(f"Module path does not exist: {module_path}")
        return False

    chacc_logger.info(f"Module path confirmed: {module_path}")

    try:
        discover_and_import_models(module_path, module_name, backbone_context.logger)
        chacc_logger.info(f"Auto-discovered models for module '{module_name}'")
    except (ImportError, RuntimeError) as e:
        chacc_logger.warning(f"Failed to discover models for module {module_name}: {e}")

    if discover_only:
        chacc_logger.info(
            f"Model discovery complete for module '{module_name}' (discover_only mode)"
        )
        return True

    entry_point_str = module_metadata.get("entry_point")
    if not entry_point_str or ":" not in entry_point_str:
        chacc_logger.warning(f"Skipping '{module_name}': Invalid 'entry_point' in metadata.")
        return False

    module_relative_path, func_name = entry_point_str.split(":")
    plugin_main_file_path = os.path.join(module_path, *module_relative_path.split(".")) + ".py"

    if not os.path.exists(plugin_main_file_path):
        chacc_logger.warning(
            f"Skipping '{module_name}': Entry point file not found: {plugin_main_file_path}"
        )
        return False

    chacc_logger.info(f"Found entry point file: {plugin_main_file_path}")

    parent_dir = os.path.dirname(module_path)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    chacc_logger.debug(f"Added parent directory to sys.path: {parent_dir}")

    full_module_name = f"{module_name}.{module_relative_path}"

    try:
        module = importlib.import_module(full_module_name)
        chacc_logger.info(f"Successfully imported module '{module_name}'")
    except ImportError as e:
        chacc_logger.error(f"Import error in module '{module_name}': {e}")
        chacc_logger.error(f"Module path: {module_path}")
        chacc_logger.error(f"Full module name: {full_module_name}")
        return False

    setup_func = getattr(module, func_name, None)
    if not setup_func or not callable(setup_func):
        chacc_logger.error(
            f"Plugin '{module_name}': Entry point function '{func_name}' not found or not callable after import."
        )
        return False

    chacc_logger.info(f"Found setup function: {func_name}")

    if inspect.iscoroutinefunction(setup_func):
        plugin_router = await setup_func(backbone_context)
    else:
        plugin_router = setup_func(backbone_context)

    if plugin_router and isinstance(plugin_router, APIRouter):
        prefix = base_path_prefix or module_metadata.get("base_path_prefix", f"/{module_name}")
        module_tags = tags or module_metadata.get(
            "tags", [module_metadata.get("display_name", module_name)]
        )
        if not isinstance(module_tags, list):
            module_tags = [module_tags]

        app.include_router(plugin_router, prefix=prefix, tags=module_tags)

        chacc_logger.info(f"Module '{module_name}' loaded and enabled with prefix: {prefix}")
        chacc_logger.info(f"Module '{module_name}' documentation tags: {module_tags}")

        if hasattr(plugin_router, "routes"):
            chacc_logger.info(f"Module '{module_name}' routes mounted:")
            for route in plugin_router.routes:
                route_path = getattr(route, "path", None)
                route_methods = getattr(route, "methods", None)
                if route_path and route_methods:
                    chacc_logger.info(f"  - {route_path}: {', '.join(route_methods)}")
        else:
            chacc_logger.info(f"Module '{module_name}' has no routes")

        return True
    else:
        chacc_logger.error(f"Plugin '{module_name}': Setup function did not return an APIRouter.")
        return False


async def load_modules(
    app: FastAPI,
    backbone_context: BackboneContext,
    only_modules: list | None = None,
    exclude_modules: list | None = None,
):
    """Main entry point for loading modules.

    Discovers modules from MODULES_INSTALLED_DIR, synchronises the database,
    resolves Python dependencies, extracts archives, and loads enabled modules
    into the FastAPI application.
    """
    chacc_logger.info("Starting module discovery and database synchronization...")

    db = await anext(get_db())

    try:
        if MODULES_LOADED_DIR not in sys.path:
            sys.path.append(MODULES_LOADED_DIR)

        chacc_logger.info(f"Scanning for modules in: {MODULES_INSTALLED_DIR}")

        if not os.path.isdir(MODULES_INSTALLED_DIR):
            chacc_logger.error(f"Modules installation directory not found: {MODULES_INSTALLED_DIR}")
            raise RuntimeError(f"Modules installation directory not found: {MODULES_INSTALLED_DIR}")

        installed_chacc_files = [
            f for f in os.listdir(MODULES_INSTALLED_DIR) if f.endswith(".chacc")
        ]
        chacc_logger.info(
            f"Found {len(installed_chacc_files)} .chacc files in modules_installed directory"
        )

        existing_records = {record.name: record for record in db.query(ModuleRecord).all()}

        modules_requirements = await collect_module_requirements()
        enabled_modules = [r.name for r in existing_records.values() if r.is_enabled]

        enabled_requirements = {}
        for mod_name, reqs in modules_requirements.items():
            if mod_name in enabled_modules or mod_name == "backbone":
                enabled_requirements[mod_name] = reqs

        if enabled_requirements:
            chacc_logger.info("Ensuring dependencies are resolved for all enabled modules...")
            try:
                from chacc import DependencyManager

                dm = DependencyManager(cache_dir=DEPENDENCY_CACHE_DIR, logger=chacc_logger)
                await dm.resolve_dependencies(enabled_requirements)
            except Exception as e:  # noqa: BLE001
                chacc_logger.error(f"Dependency resolution failed: {e}")
                chacc_logger.error("Aborting module loading to prevent inconsistent state.")
                raise RuntimeError(f"Dependency resolution failed: {e}")

        chacc_to_module_name = extract_module_names_from_chacc_files(installed_chacc_files)

        modules_to_process = process_module_archives(
            installed_chacc_files, chacc_to_module_name, existing_records, db
        )

        unzip_modules(modules_to_process, existing_records, db)

        sync_database_with_filesystem(chacc_to_module_name, existing_records, db)

        db.commit()

        module_found = db.query(ModuleRecord).first()
        if module_found:
            db.refresh(module_found)

        chacc_logger.info("Database synchronized with filesystem. Proceeding to load modules...")

        query = db.query(ModuleRecord).filter_by(is_enabled=True)
        if only_modules:
            query = query.filter(ModuleRecord.name.in_(only_modules))
        if exclude_modules:
            chacc_logger.info(f"Excluding modules from loading: {exclude_modules}")
            query = query.filter(ModuleRecord.name.notin_(exclude_modules))

        updated_records = query.all()

        for record in updated_records:
            try:
                module_path = os.path.join(MODULES_LOADED_DIR, record.name)

                meta_file_path = os.path.join(module_path, "module_meta.json")
                if os.path.exists(meta_file_path):
                    with open(meta_file_path, "r") as f:
                        metadata = json.load(f)
                else:
                    metadata = record.meta_data if record.meta_data else {}

                discovery_success = await load_single_module(
                    module_name=record.name,
                    module_path=module_path,
                    module_metadata=metadata,
                    app=app,
                    backbone_context=backbone_context,
                    base_path_prefix=record.base_path_prefix,
                    discover_only=True,
                )
                if not discovery_success:
                    chacc_logger.warning(f"Model discovery failed for module '{record.name}'")
            except Exception:
                chacc_logger.exception("Error discovering models for module '%s'", record.name)

        try:
            initialize_database_models(backbone_context)
            chacc_logger.info("initialize_database_models completed.")
        except Exception:
            chacc_logger.exception("initialize_database_models failed")

        try:
            from src.migration.runner import run_migration

            await run_migration()
        except Exception:
            chacc_logger.exception("Migration after model discovery failed")

        for record in updated_records:
            try:
                module_path = os.path.join(MODULES_LOADED_DIR, record.name)

                meta_file_path = os.path.join(module_path, "module_meta.json")
                if os.path.exists(meta_file_path):
                    with open(meta_file_path, "r") as f:
                        metadata = json.load(f)
                else:
                    metadata = record.meta_data if record.meta_data else {}

                success = await load_single_module(
                    module_name=record.name,
                    module_path=module_path,
                    module_metadata=metadata,
                    app=app,
                    backbone_context=backbone_context,
                    base_path_prefix=record.base_path_prefix,
                )
                if not success:
                    chacc_logger.warning(f"Module '{record.name}' failed to load")
                    try:
                        record.is_enabled = False
                        db.commit()
                    except Exception as e:  # noqa: BLE001
                        chacc_logger.warning(f"Failed to disable module '{record.name}': {e}")
            except Exception:
                chacc_logger.exception("Error loading module '%s'", record.name)
                try:
                    record.is_enabled = False
                    db.commit()
                except Exception as e:  # noqa: BLE001
                    chacc_logger.warning(f"Failed to disable module '{record.name}': {e}")

        try:
            if apply_deferred_schema_changes(backbone_context):
                chacc_logger.info("Deferred schema changes detected; running follow-up migration.")
                from src.migration.runner import run_migration

                await run_migration()
                chacc_logger.info("Deferred migration completed.")
        except Exception:
            chacc_logger.exception("Deferred schema migration failed")
    except Exception:
        chacc_logger.exception("Unexpected error during module loading")

    finally:
        db.close()
        chacc_logger.debug("Database session for module loading closed.")

    if MODULES_LOADED_DIR in sys.path:
        sys.path.remove(MODULES_LOADED_DIR)

    chacc_logger.info("Module loading completed.")
