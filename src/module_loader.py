"""
Module loading functionality for ChaCC API.

This module handles:
- Discovering modules from .chacc archives
- Extracting module names from module_meta.json
- Unzipping and managing module files
- Syncing database records with filesystem
- Loading modules into the FastAPI application
"""

import os
import importlib.util
import sys
import shutil
import json
import logging
import zipfile
import inspect
from typing import Dict, List, Tuple
from fastapi import FastAPI

from src.logger import LogLevels, configure_logging
from src.constants import MODULES_INSTALLED_DIR, MODULES_LOADED_DIR, DEPENDENCY_CACHE_DIR
from src.database import get_db, ModuleRecord
from src.core_services import BackboneContext

chacc_logger = configure_logging(log_level=LogLevels.INFO)


def discover_and_import_models(directory: str, base_module_path: str, logger: logging.Logger):
    """
    Recursively scans a directory for Python files and imports them.
    This is for automatic model discovery.
    """

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, directory)
                module_name = f"{base_module_path}.{relative_path[:-3].replace(os.sep, '.')}"

                if module_name in sys.modules:
                    logger.debug(f"Skipping import of {file_path} as it is already imported.")
                    continue

                try:
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    module = importlib.util.module_from_spec(spec)

                    module.__package__ = base_module_path

                    parent_package_name = base_module_path
                    if parent_package_name not in sys.modules:
                        parent_module = importlib.util.module_from_spec(
                            importlib.util.spec_from_loader(parent_package_name, loader=None)
                        )
                        sys.modules[parent_package_name] = parent_module
                        parent_module.__path__ = [os.path.dirname(file_path)]
                        parent_module.__package__ = parent_package_name

                    sys.modules[module_name] = module

                    spec.loader.exec_module(module)
                    chacc_logger.info(f"Dynamically imported models from: {module_name}")
                except ImportError as e:
                    if "already defined for this MetaData instance" in str(e):
                        logger.warning(
                            f"Skipping import of {file_path} as its table is already registered in metadata."
                        )
                        continue
                    logger.warning(f"Relative import issue in {file_path}: {e}")
                    logger.warning(f"Module name: {module_name}, Base path: {base_module_path}")
                    continue
                except Exception as e:
                    if "already defined for this MetaData instance" in str(e):
                        logger.warning(
                            f"Skipping import of {file_path} as its table is already registered in metadata."
                        )
                        continue
                    logger.error(f"Failed to import models from {file_path}: {e}", exc_info=True)


def extract_module_names_from_chacc_files(installed_chacc_files: List[str]) -> Dict[str, str]:
    """
    Extract module names from module_meta.json inside .chacc files.

    Args:
        installed_chacc_files: List of .chacc filenames

    Returns:
        Dict mapping .chacc filename -> module name
    """
    chacc_to_module_name = {}

    for chacc_filename in installed_chacc_files:
        chacc_filepath = os.path.join(MODULES_INSTALLED_DIR, chacc_filename)
        try:
            with zipfile.ZipFile(chacc_filepath, "r") as zip_ref:
                try:
                    with zip_ref.open("module_meta.json") as meta_file:
                        meta_data = json.load(meta_file)
                        module_name = meta_data.get("name")
                        if module_name:
                            chacc_to_module_name[chacc_filename] = module_name
                        else:
                            chacc_logger.warning(
                                f"module_meta.json in {chacc_filename} missing 'name' field, using filename"
                            )
                            chacc_to_module_name[chacc_filename] = chacc_filename.replace(
                                ".chacc", ""
                            )
                except KeyError:
                    chacc_logger.warning(
                        f"No module_meta.json found in {chacc_filename}, using filename as module name"
                    )
                    chacc_to_module_name[chacc_filename] = chacc_filename.replace(".chacc", "")
        except Exception as e:
            chacc_logger.warning(f"Could not read module_meta from {chacc_filename}: {e}")
            chacc_to_module_name[chacc_filename] = chacc_filename.replace(".chacc", "")

    return chacc_to_module_name


def get_chacc_filepath(module_name: str) -> str | None:
    """
    Find the .chacc file path for a given module name.

    Args:
        module_name: Name of the module to find

    Returns:
        Path to .chacc file if found, None otherwise
    """
    chacc_filepath = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.chacc")
    if os.path.exists(chacc_filepath):
        return chacc_filepath

    for f in os.listdir(MODULES_INSTALLED_DIR):
        if f.endswith(".chacc"):
            chacc_path = os.path.join(MODULES_INSTALLED_DIR, f)
            try:
                with zipfile.ZipFile(chacc_path, "r") as zip_ref:
                    with zip_ref.open("module_meta.json") as meta_file:
                        meta_data = json.load(meta_file)
                        if meta_data.get("name") == module_name:
                            chacc_logger.info(
                                f"Found matching .chacc file for module '{module_name}': {f}"
                            )
                            return chacc_path
            except Exception:
                continue

    return None


async def collect_module_requirements() -> Dict[str, str]:
    """
    Collect requirements from all .chacc files BEFORE unzipping.

    Returns:
        Dict mapping module_name -> requirements_content
    """
    modules_requirements = {}

    backbone_req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
    if os.path.exists(backbone_req_path):
        with open(backbone_req_path, "r") as f:
            modules_requirements["backbone"] = f.read()

    installed_chacc_files = {f for f in os.listdir(MODULES_INSTALLED_DIR) if f.endswith(".chacc")}

    for chacc_filename in installed_chacc_files:
        chacc_filepath = os.path.join(MODULES_INSTALLED_DIR, chacc_filename)

        try:
            with zipfile.ZipFile(chacc_filepath, "r") as zip_ref:
                module_name = chacc_filename.replace(".chacc", "")
                try:
                    with zip_ref.open("module_meta.json") as meta_file:
                        meta_data = json.load(meta_file)
                        module_name = meta_data.get("name", module_name)
                except KeyError:
                    chacc_logger.warning(
                        f"No module_meta.json found in {chacc_filename}, using filename as module name"
                    )

                try:
                    with zip_ref.open("requirements.txt") as req_file:
                        req_content = req_file.read().decode("utf-8")
                        modules_requirements[module_name] = req_content
                except KeyError:
                    chacc_logger.warning(
                        f"No requirements were specified for module {chacc_filename}"
                    )
        except Exception as e:
            chacc_logger.warning(f"Could not read requirements from {chacc_filename}: {e}")

    return modules_requirements


def process_module_archives(
    installed_chacc_files: List[str],
    chacc_to_module_name: Dict[str, str],
    existing_records: Dict[str, ModuleRecord],
    db,
) -> List[Tuple[str, str, float, bool]]:
    """
    Process (unzip) .chacc files that need updating.

    Args:
        installed_chacc_files: List of .chacc filenames
        chacc_to_module_name: Mapping of .chacc filename to module name
        existing_records: Dict of existing DB records
        db: Database session

    Returns:
        List of tuples: (module_name, chacc_filepath, chacc_mtime, is_new_module)
    """
    modules_to_process = []

    for chacc_filename in installed_chacc_files:
        module_name = chacc_to_module_name.get(chacc_filename, chacc_filename.replace(".chacc", ""))
        chacc_filepath = os.path.join(MODULES_INSTALLED_DIR, chacc_filename)
        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)

        chacc_mtime = os.path.getmtime(chacc_filepath)
        is_new_module = module_name not in existing_records

        should_unzip = False
        if not os.path.exists(loaded_module_dir):
            chacc_logger.info(f"Module detected on disk: '{module_name}'.")
            should_unzip = True
        else:
            loaded_mtime = os.path.getmtime(loaded_module_dir)
            if chacc_mtime > loaded_mtime:
                chacc_logger.info(
                    f"Module '{module_name}' archive is newer than loaded directory. Unzipping again."
                )
                shutil.rmtree(loaded_module_dir)
                should_unzip = True

        if should_unzip:
            modules_to_process.append((module_name, chacc_filepath, chacc_mtime, is_new_module))

        if is_new_module:
            meta_file_path = (
                os.path.join(loaded_module_dir, "module_meta.json")
                if os.path.exists(loaded_module_dir)
                else None
            )
            if meta_file_path and os.path.exists(meta_file_path):
                try:
                    with open(meta_file_path, "r") as f:
                        meta_data = json.load(f)

                    new_record = ModuleRecord(
                        name=module_name,
                        display_name=meta_data.get("display_name"),
                        version=meta_data.get("version"),
                        author=meta_data.get("author"),
                        description=meta_data.get("description"),
                        is_enabled=True,
                        base_path_prefix=meta_data.get("base_path_prefix", f"/{module_name}"),
                        meta_data=meta_data,
                    )
                    db.add(new_record)
                    chacc_logger.info(f"New module '{module_name}' found. Created new DB record.")
                except Exception as e:
                    chacc_logger.error(
                        f"Failed to create database record for module '{module_name}': {e}"
                    )

    return modules_to_process


def unzip_modules(
    modules_to_process: List[Tuple[str, str, float, bool]],
    existing_records: Dict[str, ModuleRecord],
    db,
):
    """
    Unzip modules and update/create DB records.

    Args:
        modules_to_process: List of tuples from process_module_archives()
        existing_records: Dict of existing DB records
        db: Database session
    """
    for module_name, chacc_filepath, chacc_mtime, is_new_module in modules_to_process:
        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)

        chacc_logger.info(f"Unzipping module '{module_name}' to '{loaded_module_dir}'...")
        with zipfile.ZipFile(chacc_filepath, "r") as zip_ref:
            os.makedirs(loaded_module_dir, exist_ok=True)
            zip_ref.extractall(loaded_module_dir)
            os.utime(loaded_module_dir, (chacc_mtime, chacc_mtime))
        chacc_logger.info(f"Unzipping for '{module_name}' completed.")

        meta_file_path = os.path.join(loaded_module_dir, "module_meta.json")
        if os.path.exists(meta_file_path):
            with open(meta_file_path, "r") as f:
                meta_data = json.load(f)

            if is_new_module:
                new_record = ModuleRecord(
                    name=module_name,
                    display_name=meta_data.get("display_name"),
                    version=meta_data.get("version"),
                    author=meta_data.get("author"),
                    description=meta_data.get("description"),
                    is_enabled=True,
                    base_path_prefix=meta_data.get("base_path_prefix", f"/{module_name}"),
                    meta_data=meta_data,
                )
                db.add(new_record)
                chacc_logger.info(f"New module '{module_name}' found. Created new DB record.")
            else:
                record = existing_records[module_name]

                current_meta_data = record.meta_data or {}
                meta_data_changed = (
                    record.display_name != meta_data.get("display_name", record.display_name)
                    or record.version != meta_data.get("version", record.version)
                    or record.author != meta_data.get("author", record.author)
                    or record.description != meta_data.get("description", record.description)
                    or record.base_path_prefix
                    != meta_data.get("base_path_prefix", record.base_path_prefix)
                    or current_meta_data != meta_data
                )

                if meta_data_changed:
                    record.display_name = meta_data.get("display_name", record.display_name)
                    record.version = meta_data.get("version", record.version)
                    record.author = meta_data.get("author", record.author)
                    record.description = meta_data.get("description", record.description)
                    record.base_path_prefix = meta_data.get(
                        "base_path_prefix", record.base_path_prefix
                    )
                    record.meta_data = meta_data
                    chacc_logger.info(f"Existing module '{module_name}' metadata updated.")


def sync_database_with_filesystem(
    chacc_to_module_name: Dict[str, str], existing_records: Dict[str, ModuleRecord], db
):
    """
    Remove DB records for modules that are no longer on disk.

    Args:
        chacc_to_module_name: Mapping of .chacc filename to module name
        existing_records: Dict of existing DB records
        db: Database session
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


async def load_single_module(
    module_name: str,
    module_path: str,
    module_metadata: dict,
    app: FastAPI,
    backbone_context: BackboneContext,
    base_path_prefix: str = None,
    tags: list = None,
) -> bool:
    """
    Load a single module into the application.

    This is an async function - no database records or file system operations.
    All required data is passed as parameters.
    Supports both sync and async setup functions.

    Args:
        module_name: Name of the module
        module_path: Path to the module directory
        module_metadata: Module metadata dict (from module_meta.json)
        app: FastAPI application
        backbone_context: BackboneContext for the module
        base_path_prefix: Override the base path prefix
        tags: Override the tags

    Returns:
        True if successful, False otherwise
    """
    from fastapi import APIRouter

    chacc_logger.info(f"Loading module '{module_name}' from path: {module_path}")

    if not os.path.isdir(module_path):
        chacc_logger.error(f"Module path does not exist: {module_path}")
        return False

    chacc_logger.info(f"Module path confirmed: {module_path}")

    models_dir = os.path.join(module_path, "models")
    if os.path.isdir(models_dir):
        init_file = os.path.join(models_dir, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w") as f:
                f.write("# Package initialization\n")

        parent_dir = os.path.dirname(models_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        try:
            discover_and_import_models(models_dir, f"{module_name}", backbone_context.logger)
        except Exception as e:
            chacc_logger.warning(f"Failed to discover models for module {module_name}: {e}")

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
        chacc_logger.info(f"Successfully imported module '{module_name}' via importlib")
    except ImportError as e:
        chacc_logger.error(f"Import error in module '{module_name}': {e}")
        chacc_logger.error(
            f"This often happens with relative imports. Ensure module uses proper import syntax."
        )
        chacc_logger.error(f"Module path: {module_path}")
        chacc_logger.error(f"Full module name: {full_module_name}")
        return False

    if full_module_name in sys.modules:
        module = sys.modules[full_module_name]
    else:
        chacc_logger.error(f"Module '{full_module_name}' not found in sys.modules after import")
        return False

    setup_func = getattr(module, func_name, None)
    if not setup_func or not callable(setup_func):
        chacc_logger.warning(
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
                chacc_logger.info(f"  - {route.path}: {', '.join(route.methods)}")
        else:
            chacc_logger.info(f"Module '{module_name}' has no routes")

        return True
    else:
        chacc_logger.warning(f"Plugin '{module_name}': Setup function did not return an APIRouter.")
        return False


async def run_module_tests(module_name: str, module_path: str, test_entry_point: str):
    """
    Run tests for a specific module.
    """
    chacc_logger.info(f"Running tests for module '{module_name}'...")
    try:
        module_relative_path, func_name = test_entry_point.split(":")
        test_code_dir = os.path.join(module_path, "module")
        test_main_file_path = os.path.join(test_code_dir, *module_relative_path.split(".")) + ".py"

        if not os.path.exists(test_main_file_path):
            chacc_logger.warning(
                f"Test entry point file '{test_main_file_path}' not found for module '{module_name}'."
            )
            return

        sys.path.insert(0, test_code_dir)

        spec = importlib.util.spec_from_file_location(module_relative_path, test_main_file_path)
        if spec is None:
            chacc_logger.error(f"Could not create spec for test module '{module_name}'.")
            return

        test_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(test_module)

        test_func = getattr(test_module, func_name, None)
        if not test_func or not callable(test_func):
            chacc_logger.warning(
                f"Test entry point function '{func_name}' not found or not callable for module '{module_name}'."
            )
            return

        await test_func()
        chacc_logger.info(f"Tests for module '{module_name}' passed successfully.")

    except Exception as e:
        chacc_logger.warning(f"Tests for module '{module_name}' failed: {str(e)}")
        import traceback

        chacc_logger.warning(f"Test failure details: {traceback.format_exc()}")
    finally:
        if test_code_dir in sys.path:
            sys.path.remove(test_code_dir)


async def load_modules(
    app: FastAPI,
    backbone_context: BackboneContext,
    only_modules: list = None,
    exclude_modules: list = None,
):
    """
    Main entry point for loading modules.
    Discovers modules from MODULES_INSTALLED_DIR, synchronizes the database,
    resolves dependencies, and loads enabled modules into the application.
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
            except Exception as e:
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

                await load_single_module(
                    module_name=record.name,
                    module_path=module_path,
                    module_metadata=metadata,
                    app=app,
                    backbone_context=backbone_context,
                    base_path_prefix=record.base_path_prefix,
                )
            except Exception as e:
                chacc_logger.error(f"Error loading module '{record.name}': {e}", exc_info=True)
                try:
                    record.is_enabled = False
                    db.commit()
                except Exception:
                    pass
    except Exception as e:
        chacc_logger.error(f"Unexpected error during module loading: {e}", exc_info=True)
        pass

    finally:
        db.close()
        chacc_logger.debug("Database session for module loading closed.")

    if MODULES_LOADED_DIR in sys.path:
        sys.path.remove(MODULES_LOADED_DIR)

    chacc_logger.info("Module loading completed.")
