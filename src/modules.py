import io
import os
import importlib.util
import sys
import shutil
import json
import logging
import zipfile
from fastapi import Depends, status, UploadFile, File, HTTPException, APIRouter, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.logger import LogLevels, configure_logging

from .constants import MODULES_INSTALLED_DIR, MODULES_LOADED_DIR
from .database import get_db, ModuleRecord
from .core_services import BackboneContext
from .chacc_dependency_manager import (
    invalidate_module_cache,
    resolve_chacc_dependencies as re_resolve_dependencies
)

chacc_logger = configure_logging(log_level=LogLevels.INFO)




def _discover_and_import_models(directory: str, base_module_path: str, logger: logging.Logger):
    """
    Recursively scans a directory for Python files and imports them.
    This is for automatic model discovery.
    """
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py') and file != '__init__.py':
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, directory)
                module_name = f"{base_module_path}.{relative_path[:-3].replace(os.sep, '.')}"

                try:
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    chacc_logger.info(f"Dynamically imported models from: {module_name}")
                except Exception as e:
                    chacc_logger.error(f"Failed to import models from {file_path}: {e}", exc_info=True)


async def run_module_tests(module_name: str, module_path: str, test_entry_point: str):
    """
    Run tests for a specific module.
    """
    chacc_logger.info(f"Running tests for module '{module_name}'...")
    try:
        module_relative_path, func_name = test_entry_point.split(":")
        test_code_dir = os.path.join(module_path, "module")
        test_main_file_path = os.path.join(test_code_dir, *module_relative_path.split('.')) + ".py"

        if not os.path.exists(test_main_file_path):
            chacc_logger.warning(f"Test entry point file '{test_main_file_path}' not found for module '{module_name}'.")
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
            chacc_logger.warning(f"Test entry point function '{func_name}' not found or not callable for module '{module_name}'.")
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


async def collect_module_requirements():
    """
    Collect requirements from all .chacc files BEFORE unzipping.
    Returns a dict of module_name -> requirements_content
    """
    modules_requirements = {}

    backbone_req_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
    if os.path.exists(backbone_req_path):
        with open(backbone_req_path, 'r') as f:
            modules_requirements['backbone'] = f.read()

    installed_chacc_files = {f for f in os.listdir(MODULES_INSTALLED_DIR) if f.endswith('.chacc')}

    for chacc_filename in installed_chacc_files:
        module_name = chacc_filename.replace('.chacc', '')
        chacc_filepath = os.path.join(MODULES_INSTALLED_DIR, chacc_filename)

        try:
            with zipfile.ZipFile(chacc_filepath, 'r') as zip_ref:
                try:
                    with zip_ref.open('requirements.txt') as req_file:
                        req_content = req_file.read().decode('utf-8')
                        modules_requirements[module_name] = req_content
                except KeyError:
                    chacc_logger.warning(f"No requirements were specified for module {chacc_filename}")
                    pass
        except Exception as e:
            chacc_logger.warning(f"Could not read requirements from {chacc_filename}: {e}")

    return modules_requirements


async def load_modules(app: FastAPI, backbone_context: BackboneContext, only_modules: list = None, exclude_modules: list = None):
    """
    Discovers modules from the MODULES_INSTALLED_DIR, synchronizes the database,
    resolves dependencies BEFORE loading, and then loads enabled modules into the application.
    """
    chacc_logger.info("Starting module discovery and database synchronization...")

    db = await anext(get_db())

    try:
        if MODULES_LOADED_DIR not in sys.path:
            sys.path.append(MODULES_LOADED_DIR)

        installed_chacc_files = {f for f in os.listdir(MODULES_INSTALLED_DIR) if f.endswith('.chacc')}
        existing_records = {record.name: record for record in db.query(ModuleRecord).all()}

        modules_requirements = await collect_module_requirements()
        enabled_modules = [r.name for r in existing_records.values() if r.is_enabled]

        enabled_requirements = {}
        for module_name, reqs in modules_requirements.items():
            if module_name in enabled_modules or module_name == 'backbone':
                enabled_requirements[module_name] = reqs

        if enabled_requirements:
            chacc_logger.info("Ensuring dependencies are resolved for all enabled modules...")
            try:
                from chacc import DependencyManager
                from .constants import DEPENDENCY_CACHE_DIR
                dm = DependencyManager(cache_dir=DEPENDENCY_CACHE_DIR, logger=chacc_logger)
                await dm.resolve_dependencies(enabled_requirements)
            except Exception as e:
                chacc_logger.error(f"Dependency resolution failed: {e}")
                chacc_logger.error("Aborting module loading to prevent inconsistent state.")
                raise RuntimeError(f"Dependency resolution failed: {e}")

        modules_to_process = []

        for chacc_filename in installed_chacc_files:
            module_name = chacc_filename.replace('.chacc', '')
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
                    chacc_logger.info(f"Module '{module_name}' archive is newer than loaded directory. Unzipping again.")
                    shutil.rmtree(loaded_module_dir)
                    should_unzip = True

            if should_unzip:
                modules_to_process.append((module_name, chacc_filepath, chacc_mtime, is_new_module))
            
            if is_new_module:
                meta_file_path = os.path.join(loaded_module_dir, "module_meta.json") if os.path.exists(loaded_module_dir) else None
                if meta_file_path and os.path.exists(meta_file_path):
                    try:
                        with open(meta_file_path, 'r') as f:
                            meta_data = json.load(f)
                        
                        new_record = ModuleRecord(
                            name=module_name,
                            display_name=meta_data.get("display_name"),
                            version=meta_data.get("version"),
                            author=meta_data.get("author"),
                            description=meta_data.get("description"),
                            is_enabled=True,
                            base_path_prefix=meta_data.get("base_path_prefix", f'/{module_name}'),
                            meta_data=meta_data
                        )
                        db.add(new_record)
                        chacc_logger.info(f"New module '{module_name}' found. Created new DB record.")
                    except Exception as e:
                        chacc_logger.error(f"Failed to create database record for module '{module_name}': {e}")

        for module_name, chacc_filepath, chacc_mtime, is_new_module in modules_to_process:
            loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)

            chacc_logger.info(f"Unzipping module '{module_name}' to '{loaded_module_dir}'...")
            with zipfile.ZipFile(chacc_filepath, 'r') as zip_ref:
                os.makedirs(loaded_module_dir, exist_ok=True)
                zip_ref.extractall(loaded_module_dir)
                os.utime(loaded_module_dir, (chacc_mtime, chacc_mtime))
            chacc_logger.info(f"Unzipping for '{module_name}' completed.")

            meta_file_path = os.path.join(loaded_module_dir, "module_meta.json")
            if os.path.exists(meta_file_path):
                with open(meta_file_path, 'r') as f:
                    meta_data = json.load(f)

                if is_new_module:
                    new_record = ModuleRecord(
                        name=module_name,
                        display_name=meta_data.get("display_name"),
                        version=meta_data.get("version"),
                        author=meta_data.get("author"),
                        description=meta_data.get("description"),
                        is_enabled=True,
                        base_path_prefix=meta_data.get("base_path_prefix", f'/{module_name}'),
                        meta_data=meta_data
                    )
                    db.add(new_record)
                    chacc_logger.info(f"New module '{module_name}' found. Created new DB record.")
                else:
                    record = existing_records[module_name]
                    if record.display_name != meta_data.get("display_name", record.display_name) or \
                       record.version != meta_data.get("version", record.version) or \
                       record.author != meta_data.get("author", record.author) or \
                       record.description != meta_data.get("description", record.description) or \
                       record.base_path_prefix != meta_data.get("base_path_prefix", record.base_path_prefix):

                        record.display_name = meta_data.get("display_name", record.display_name)
                        record.version = meta_data.get("version", record.version)
                        record.author = meta_data.get("author", record.author)
                        record.description = meta_data.get("description", record.description)
                        record.base_path_prefix = meta_data.get("base_path_prefix", record.base_path_prefix)
                        record.meta_data = meta_data
                        chacc_logger.info(f"Existing module '{module_name}' metadata updated.")

        installed_module_names = {f.replace('.chacc', '') for f in installed_chacc_files}
        for module_name, record in list(existing_records.items()):
            if module_name not in installed_module_names:
                db.delete(record)
                chacc_logger.warning(f"Module '{module_name}' record found in DB but not on disk. Deleting record and its code.")
                loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
                if os.path.exists(loaded_module_dir):
                    shutil.rmtree(loaded_module_dir)

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
            if "authentication" in exclude_modules:
                chacc_logger.warning("Skipping authentication module during initial module load.")
            query = query.filter(ModuleRecord.name.notin_(exclude_modules))

        updated_records = query.all()

        for record in updated_records:
            module_name = record.name
            module_path = os.path.join(MODULES_LOADED_DIR, module_name)

            if not record.is_enabled:
                chacc_logger.info(f"Skipping disabled module: {module_name}")
                continue

            if not os.path.isdir(module_path):
                chacc_logger.error(f"Module '{module_name}' marked as enabled in DB but its directory is missing: {module_path}. Setting it to disabled.")
                record.is_enabled = False
                db.commit()
                continue

            try:
                chacc_logger.info(f"Starting to load module '{module_name}' from database")
                chacc_logger.info(f"Module path: {module_path}")
                
                chacc_file_path = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.chacc")
                if not os.path.exists(chacc_file_path):
                    chacc_logger.error(f"Module '{module_name}' .chacc file not found at {chacc_file_path}. Setting module to disabled.")
                    record.is_enabled = False
                    db.commit()
                    continue
                
                chacc_logger.info(f"Confirmed .chacc file exists: {chacc_file_path}")
                
                if not os.path.isdir(module_path):
                    # TODO: We will have to extract it if not inside loaded directory
                    chacc_logger.error(f"Module '{module_name}' directory not found at {module_path}. Setting module to disabled.")
                    record.is_enabled = False
                    db.commit()
                    continue
                
                chacc_logger.info(f"Confirmed module directory exists: {module_path}")
                
                models_directory = os.path.join(module_path, "module")
                if os.path.isdir(models_directory):
                    sys.path.insert(0, models_directory)
                    _discover_and_import_models(models_directory, f"{module_name}.module", backbone_context.logger)
                
                module_meta = record.meta_data if record.meta_data else {}
                entry_point_str = module_meta.get("entry_point")

                if not entry_point_str or ":" not in entry_point_str:
                    chacc_logger.warning(f"Skipping '{module_name}': Invalid 'entry_point' in DB metadata.")
                    continue

                module_relative_path, func_name = entry_point_str.split(":")
                plugin_code_dir = os.path.join(module_path, "module")
                plugin_main_file_path = os.path.join(plugin_code_dir, *module_relative_path.split('.')) + ".py"

                if not os.path.exists(plugin_main_file_path):
                    chacc_logger.warning(f"Skipping '{module_name}': Entry point file '{plugin_main_file_path}' not found on disk. Setting module to disabled.")
                    record.is_enabled = False
                    db.commit()
                    continue

                chacc_logger.info(f"Found entry point file: {plugin_main_file_path}")
                
                sys.path.insert(0, plugin_code_dir)

                spec = importlib.util.spec_from_file_location(module_relative_path, plugin_main_file_path)
                if spec is None:
                    chacc_logger.error(f"Could not create spec for module '{module_name}'.")
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                setup_func = getattr(module, func_name, None)
                if not setup_func or not callable(setup_func):
                    chacc_logger.warning(f"Plugin '{module_name}': Entry point function '{func_name}' not found or not callable after import.")
                    continue

                chacc_logger.info(f"Found setup function: {func_name}")

                plugin_router = setup_func(backbone_context)

                if plugin_router and isinstance(plugin_router, APIRouter):
                    chacc_logger.info(f"Mounting router for module '{module_name}' at prefix: {record.base_path_prefix}")
                    
                    # Configure router with proper OpenAPI metadata for documentation
                    module_tags = module_meta.get("tags", [record.display_name])
                    if not isinstance(module_tags, list):
                        module_tags = [module_tags]
                    
                    # Include router in app with proper configuration
                    app.include_router(
                        plugin_router,
                        prefix=record.base_path_prefix,
                        tags=module_tags
                    )
                    
                    chacc_logger.info(f"Module '{module_name}' loaded and enabled with prefix: {record.base_path_prefix}")
                    chacc_logger.info(f"Module '{module_name}' documentation tags: {module_tags}")
                    
                    # Log all routes that were mounted
                    if hasattr(plugin_router, 'routes'):
                        chacc_logger.info(f"Module '{module_name}' routes mounted:")
                        for route in plugin_router.routes:
                            chacc_logger.info(f"  - {route.path}: {', '.join(route.methods)}")
                    else:
                        chacc_logger.info(f"Module '{module_name}' has no routes")
                else:
                    chacc_logger.warning(f"Plugin '{module_name}': Setup function did not return an APIRouter.")

            except Exception as e:
                chacc_logger.error(f"Error loading module '{module_name}': {e}", exc_info=True)
            finally:
                if plugin_code_dir in sys.path:
                    sys.path.remove(plugin_code_dir)

    finally:
        db.close()
        chacc_logger.debug("Database session for module loading closed.")

    if MODULES_LOADED_DIR in sys.path:
        sys.path.remove(MODULES_LOADED_DIR)

    chacc_logger.info("Module loading completed.")

modules_router = APIRouter()

@modules_router.post("/modules/")
async def install_chacc_module_endpoint(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Installs a new ChaCC API module from an .chacc package.
    Resolves dependencies BEFORE unzipping to prevent inconsistent state.
    Requires server restart to activate/deactivate the new module.
    """
    if not file.filename.endswith(".chacc"):
        chacc_logger.error(f"Uploaded file '{file.filename}' is not a .chacc package.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .chacc module packages are allowed."
        )

    file_content = await file.read()

    try:
        with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zip_ref:
            try:
                with zip_ref.open('module_meta.json') as meta_file:
                    meta_data = json.load(meta_file)
            except KeyError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing 'module_meta.json' in the .chacc package.")

            module_name = meta_data.get("name")
            if not module_name:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'name' field is missing in 'module_meta.json'.")

            module_requirements = {}
            try:
                with zip_ref.open('requirements.txt') as req_file:
                    req_content = req_file.read().decode('utf-8')
                    module_requirements[module_name] = req_content
            except KeyError:
                pass

        backbone_req_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
        if os.path.exists(backbone_req_path):
            with open(backbone_req_path, 'r') as f:
                module_requirements['backbone'] = f.read()

        if module_requirements:
            chacc_logger.info(f"Resolving dependencies for module '{module_name}' before installation...")
            from .chacc_dependency_manager import ChaCCDependencyManager
            dm = ChaCCDependencyManager(logger=chacc_logger)
            await dm.dm.resolve_dependencies(module_requirements)
            chacc_logger.info("Dependencies resolved successfully.")

        target_chacc_path = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.chacc")
        with open(target_chacc_path, "wb") as f:
            f.write(file_content)
        chacc_logger.info(f"Module archive '{module_name}.chacc' saved to '{target_chacc_path}'.")

        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
        if os.path.exists(loaded_module_dir):
            shutil.rmtree(loaded_module_dir)
        with zipfile.ZipFile(target_chacc_path, 'r') as zip_ref:
            os.makedirs(loaded_module_dir, exist_ok=True)
            zip_ref.extractall(loaded_module_dir)
            os.utime(loaded_module_dir, (os.path.getmtime(target_chacc_path), os.path.getmtime(target_chacc_path)))
        chacc_logger.info(f"Successfully unzipped module '{module_name}' to '{loaded_module_dir}'.")

        invalidate_module_cache(module_name)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Module '{module_name}' installed/updated successfully. Dependencies resolved. Please restart the API server to apply changes."}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        chacc_logger.error(f"Error during module installation: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Installation failed: {e}")
            
@modules_router.get("/modules/")
async def get_modules_endpoint(db: Session = Depends(get_db)):
    """
    Retrieves a list of all installed modules and their current status from the database.
    """
    module_records = db.query(ModuleRecord).all()
    return {
        "modules": [
            {
                "name": record.name,
                "display_name": record.display_name,
                "version": record.version,
                "author": record.author,
                "description": record.description,
                "is_enabled": record.is_enabled,
                "base_path_prefix": record.base_path_prefix,
            }
            for record in module_records
        ]
    }

@modules_router.post("/modules/{module_name}/enable")
async def enable_module_endpoint(module_name: str, db: Session = Depends(get_db)):
    """
    Marks a module as enabled in the database.
    Resolves dependencies BEFORE unzipping to prevent inconsistent state.
    Requires server restart to take effect.
    """
    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database.")

    if module_record.is_enabled:
        return JSONResponse(content={"message": f"Module '{module_name}' is already enabled."})

    chacc_filepath = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.chacc")
    if not os.path.exists(chacc_filepath):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Module archive not found: {chacc_filepath}")

    module_requirements = {}
    try:
        with zipfile.ZipFile(chacc_filepath, 'r') as zip_ref:
            try:
                with zip_ref.open('requirements.txt') as req_file:
                    req_content = req_file.read().decode('utf-8')
                    module_requirements[module_name] = req_content
            except KeyError:
                pass
    except Exception as e:
        chacc_logger.error(f"Could not read requirements from {module_name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not read module requirements: {e}")

    backbone_req_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
    if os.path.exists(backbone_req_path):
        with open(backbone_req_path, 'r') as f:
            module_requirements['backbone'] = f.read()

    if module_requirements:
        chacc_logger.info(f"Resolving dependencies for module '{module_name}' before enabling...")
        try:
            from .chacc_dependency_manager import ChaCCDependencyManager
            dm = ChaCCDependencyManager(logger=chacc_logger)
            await dm.resolve_dependencies()
            chacc_logger.info("Dependencies resolved successfully.")
        except Exception as e:
            chacc_logger.error(f"Dependency resolution failed: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Dependency resolution failed: {e}")

    loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
    shutil.rmtree(loaded_module_dir, ignore_errors=True)
    with zipfile.ZipFile(chacc_filepath, 'r') as zip_ref:
        os.makedirs(loaded_module_dir, exist_ok=True)
        zip_ref.extractall(loaded_module_dir)
        os.utime(loaded_module_dir, (os.path.getmtime(chacc_filepath), os.path.getmtime(chacc_filepath)))

    module_record.is_enabled = True
    db.commit()
    db.refresh(module_record)
    chacc_logger.info(f"Module '{module_name}' marked as enabled in DB. Please restart the API server to activate.")

    invalidate_module_cache(module_name)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Module '{module_name}' enabled. Dependencies resolved. Please restart the server for changes to take effect."}
    )

@modules_router.post("/modules/{module_name}/disable")
async def disable_module_endpoint(module_name: str, db: Session = Depends(get_db)):
    """
    Marks a module as disabled in the database. Requires server restart to take effect.
    """
    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database.")

    if not module_record.is_enabled:
        return JSONResponse(content={"message": f"Module '{module_name}' is already disabled."})

    loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
    if os.path.exists(loaded_module_dir):
        shutil.rmtree(loaded_module_dir)
        chacc_logger.info(f"Successfully deleted module code directory: {loaded_module_dir}")

    module_record.is_enabled = False
    db.commit()
    db.refresh(module_record)
    chacc_logger.info(f"Module '{module_name}' marked as disabled in DB. Please restart the API server to deactivate.")

    invalidate_module_cache(module_name)
    await re_resolve_dependencies()
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Module '{module_name}' disabled. Please restart the server for changes to take effect."}
    )

@modules_router.delete("/modules/{module_name}/uninstall")
async def uninstall_module_endpoint(module_name: str, db: Session = Depends(get_db)):
    """
    Uninstalls a module by removing its code from disk and its record from the database.
    Requires server restart to take full effect.
    """

    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database.")

    try:
        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
        if os.path.exists(loaded_module_dir):
            shutil.rmtree(loaded_module_dir)
            chacc_logger.info(f"Successfully deleted module code directory: {loaded_module_dir}")
            
        archive_file_path = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.chacc")
        if os.path.exists(archive_file_path):
            os.remove(archive_file_path)
            chacc_logger.info(f"Successfully deleted module archive: {archive_file_path}")

        db.delete(module_record)
        db.commit()
        chacc_logger.info(f"Module '{module_name}' record deleted from database.")

        invalidate_module_cache(module_name)
        await re_resolve_dependencies()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Module '{module_name}' uninstalled. Please restart the API server to apply changes."}
        )

    except Exception as e:
        db.rollback()
        chacc_logger.exception(f"Error during module uninstall of '{module_name}'.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to uninstall module: {e}. Manual intervention may be required."
        )
