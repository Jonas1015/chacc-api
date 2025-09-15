import io
import os
import importlib.util
import sys
import shutil
import json
import logging
import subprocess
import zipfile
from fastapi import Depends, Request, status, UploadFile, File, HTTPException, APIRouter, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.logger import LogLevels, configure_logging

from .constants import LOGGER_NAME, MODULES_INSTALLED_DIR, MODULES_LOADED_DIR, MODULES_UPLOAD_DIR, BACKBONE_REQUIREMENTS_LOCK_FILE
from .database import get_db, ModuleRecord
from .core_services import BackboneContext

opentz_logger = configure_logging(log_level=LogLevels.INFO)

async def _re_resolve_dependencies():
    """
    Re-resolves and reinstalls all dependencies based on current active modules and backbone.
    This should be called after module installation or uninstallation.
    """
    opentz_logger.info("Starting dependency re-resolution process...")

    temp_req_file = os.path.join(MODULES_UPLOAD_DIR, "temp_combined_requirements.txt")
    
    db = await anext(get_db())
    try:
        with open(temp_req_file, "w") as f:
            core_req_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'requirements.txt')
            if os.path.exists(core_req_path):
                f.write(f"-r {core_req_path}\n")
            else:
                opentz_logger.warning("No project-level requirements.txt found for backbone core.")
            
            installed_modules_records = db.query(ModuleRecord).filter_by(is_enabled=True).all()
            for record in installed_modules_records:
                module_name = record.name
                module_meta = record.meta_data if record.meta_data else {}
                
                dependencies_file_name = module_meta.get("dependencies_file", "requirements.txt")
                module_req_path = os.path.join(MODULES_LOADED_DIR, module_name, dependencies_file_name)

                if os.path.exists(module_req_path):
                    f.write(f"-r {module_req_path}\n")
                    opentz_logger.info(f"Including dependencies from installed module: {module_name} ({module_req_path})")
                else:
                    opentz_logger.warning(f"Module '{module_name}' has no '{dependencies_file_name}' file found.")
        
        subprocess.check_call([
            sys.executable, "-m", "piptools", "compile",
            "--output-file", BACKBONE_REQUIREMENTS_LOCK_FILE,
            "--allow-unsafe",
            temp_req_file
        ])
        opentz_logger.info(f"Generated new lock file: {BACKBONE_REQUIREMENTS_LOCK_FILE}")

        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", BACKBONE_REQUIREMENTS_LOCK_FILE,
            "--force-reinstall"
        ])
        opentz_logger.info("Python environment updated successfully based on new lock file.")
    except subprocess.CalledProcessError as e:
        opentz_logger.error(f"Failed to manage dependencies: {e.stderr.decode() if e.stderr else e}", exc_info=True)
        raise RuntimeError(f"Dependency management failed. Check logs for details. Error: {e}")
    except Exception as e:
        opentz_logger.error(f"Unexpected error during dependency re-resolution: {e}", exc_info=True)
        raise RuntimeError(f"Dependency management failed due to an unexpected error: {e}")
    finally:
        db.close()
        if os.path.exists(temp_req_file):
            os.remove(temp_req_file)
        opentz_logger.info("Dependency re-resolution process finished.")


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
                    opentz_logger.info(f"Dynamically imported models from: {module_name}")
                except Exception as e:
                    opentz_logger.error(f"Failed to import models from {file_path}: {e}", exc_info=True)


async def load_modules(app: FastAPI, backbone_context: BackboneContext, only_modules: list = None, exclude_modules: list = None):
    """
    Discovers modules from the MODULES_INSTALLED_DIR, synchronizes the database,
    and then loads enabled modules into the application.
    """
    opentz_logger.info("Starting module discovery and database synchronization...")
    
    re_resolve_required = False
    db = await anext(get_db())
    
    try:
        if MODULES_LOADED_DIR not in sys.path:
            sys.path.append(MODULES_LOADED_DIR)

        installed_otz_files = {f for f in os.listdir(MODULES_INSTALLED_DIR) if f.endswith('.otz')}
        existing_records = {record.name: record for record in db.query(ModuleRecord).all()}
        
        for otz_filename in installed_otz_files:
            module_name = otz_filename.replace('.otz', '')
            otz_filepath = os.path.join(MODULES_INSTALLED_DIR, otz_filename)
            loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)

            otz_mtime = os.path.getmtime(otz_filepath)

            is_new_module = module_name not in existing_records
            
            should_unzip = False
            if not os.path.exists(loaded_module_dir):
                opentz_logger.info(f"New module detected on disk: '{module_name}'.")
                should_unzip = True
                re_resolve_required = True
            else:
                loaded_mtime = os.path.getmtime(loaded_module_dir)
                if otz_mtime > loaded_mtime:
                    opentz_logger.info(f"Module '{module_name}' archive is newer than loaded directory. Unzipping again.")
                    shutil.rmtree(loaded_module_dir)
                    should_unzip = True
                    re_resolve_required = True
            
            if should_unzip:
                opentz_logger.info(f"Unzipping module '{module_name}' to '{loaded_module_dir}'...")
                with zipfile.ZipFile(otz_filepath, 'r') as zip_ref:
                    os.makedirs(loaded_module_dir, exist_ok=True)
                    zip_ref.extractall(loaded_module_dir)
                    os.utime(loaded_module_dir, (otz_mtime, otz_mtime))
                opentz_logger.info(f"Unzipping for '{module_name}' completed.")

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
                    opentz_logger.info(f"New module '{module_name}' found. Created new DB record.")
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
                        opentz_logger.info(f"Existing module '{module_name}' metadata updated.")

        
        installed_module_names = {f.replace('.otz', '') for f in installed_otz_files}
        for module_name, record in list(existing_records.items()):
            if module_name not in installed_module_names:
                db.delete(record)
                opentz_logger.warning(f"Module '{module_name}' record found in DB but not on disk. Deleting record and its code.")
                loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
                if os.path.exists(loaded_module_dir):
                    shutil.rmtree(loaded_module_dir)
                re_resolve_required = True
        
        db.commit()

        module_found = db.query(ModuleRecord).first()
        if module_found:
            db.refresh(module_found)
        
        opentz_logger.info("Database synchronized with filesystem. Proceeding to load modules...")
        
        query = db.query(ModuleRecord).filter_by(is_enabled=True)
        if only_modules:
            query = query.filter(ModuleRecord.name.in_(only_modules))
        if exclude_modules:
            opentz_logger.info(f"Excluding modules from loading: {exclude_modules}")
            if "authentication" in exclude_modules:
                opentz_logger.warning("Skipping authentication module during initial module load.")
            query = query.filter(ModuleRecord.name.notin_(exclude_modules))
        
        updated_records = query.all()

        for record in updated_records:
            module_name = record.name
            module_path = os.path.join(MODULES_LOADED_DIR, module_name)
            
            if not record.is_enabled:
                opentz_logger.info(f"Skipping disabled module: {module_name}")
                continue
            
            if not os.path.isdir(module_path):
                opentz_logger.error(f"Module '{module_name}' marked as enabled in DB but its directory is missing: {module_path}. Setting it to disabled.")
                record.is_enabled = False
                db.commit()
                continue
            
            try:
                models_directory = os.path.join(module_path, "module")
                if os.path.isdir(models_directory):
                    sys.path.insert(0, models_directory)
                    _discover_and_import_models(models_directory, f"modules.{module_name}.module", backbone_context.logger)

                module_meta = record.meta_data if record.meta_data else {}
                entry_point_str = module_meta.get("entry_point")
                
                if not entry_point_str or ":" not in entry_point_str:
                    opentz_logger.warning(f"Skipping '{module_name}': Invalid 'entry_point' in DB metadata.")
                    continue

                module_relative_path, func_name = entry_point_str.split(":")
                plugin_code_dir = os.path.join(module_path, "module")
                plugin_main_file_path = os.path.join(plugin_code_dir, *module_relative_path.split('.')) + ".py"

                if not os.path.exists(plugin_main_file_path):
                    opentz_logger.warning(f"Skipping '{module_name}': Entry point file '{plugin_main_file_path}' not found on disk. Setting module to disabled.")
                    record.is_enabled = False
                    db.commit()
                    continue

                sys.path.insert(0, plugin_code_dir)

                spec = importlib.util.spec_from_file_location(module_relative_path, plugin_main_file_path)
                if spec is None:
                    opentz_logger.error(f"Could not create spec for module '{module_name}'.")
                    continue
                
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                setup_func = getattr(module, func_name, None)
                if not setup_func or not callable(setup_func):
                    opentz_logger.warning(f"Plugin '{module_name}': Entry point function '{func_name}' not found or not callable after import.")
                    continue

                
                plugin_router = setup_func(backbone_context)

                if plugin_router and isinstance(plugin_router, APIRouter):
                    opentz_logger.info(f"Mounting router for module '{module_name}' at prefix: {record.base_path_prefix}")
                    app.include_router(plugin_router, prefix=record.base_path_prefix, tags=module_meta.get("tags", [record.display_name]))
                    opentz_logger.info(f"Module '{module_name}' loaded and enabled with prefix: {record.base_path_prefix}")
                else:
                    opentz_logger.warning(f"Plugin '{module_name}': Setup function did not return an APIRouter.")

            except Exception as e:
                opentz_logger.error(f"Error loading module '{module_name}': {e}", exc_info=True)
            finally:
                if plugin_code_dir in sys.path:
                    sys.path.remove(plugin_code_dir)

    finally:
        db.close()
        opentz_logger.debug("Database session for module loading closed.")
    
    if MODULES_LOADED_DIR in sys.path:
        sys.path.remove(MODULES_LOADED_DIR)

    if re_resolve_required:
        opentz_logger.info("Changes detected in module configuration. Re-resolving dependencies.")
        await _re_resolve_dependencies()
        opentz_logger.info("Dependencies resolved. A server restart is required to load the new modules.")
    else:
        opentz_logger.info("No changes in module configuration detected. Skipping dependency resolution.")

    opentz_logger.info("Module loading completed.")

modules_router = APIRouter()

@modules_router.post("/modules/")
async def install_otz_module_endpoint(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Installs a new Open-TZ module from an .otz package.
    Requires server restart to activate/deactivate the new module.
    """
    if not file.filename.endswith(".otz"):
        opentz_logger.error(f"Uploaded file '{file.filename}' is not a .otz package.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .otz module packages are allowed."
        )

    file_content = await file.read()
    
    try:
        with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zip_ref:
            try:
                with zip_ref.open('module_meta.json') as meta_file:
                    meta_data = json.load(meta_file)
            except KeyError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing 'module_meta.json' in the .otz package.")
            
            module_name = meta_data.get("name")
            if not module_name:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'name' field is missing in 'module_meta.json'.")

            target_otz_path = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.otz")
            with open(target_otz_path, "wb") as f:
                f.write(file_content)
            opentz_logger.info(f"Module archive '{module_name}.otz' saved to '{target_otz_path}'.")

        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
        if os.path.exists(loaded_module_dir):
            shutil.rmtree(loaded_module_dir)
        with zipfile.ZipFile(target_otz_path, 'r') as zip_ref:
            os.makedirs(loaded_module_dir, exist_ok=True)
            zip_ref.extractall(loaded_module_dir)
            os.utime(loaded_module_dir, (os.path.getmtime(target_otz_path), os.path.getmtime(target_otz_path)))
        opentz_logger.info(f"Successfully unzipped module '{module_name}' to '{loaded_module_dir}'.")
        
        await _re_resolve_dependencies()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Module '{module_name}' installed/updated successfully. Please restart the API server to apply changes."}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        opentz_logger.error(f"Error during module installation: {e}", exc_info=True)
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
    Marks a module as enabled in the database. Requires server restart to take effect.
    """
    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database.")

    if module_record.is_enabled:
        return JSONResponse(content={"message": f"Module '{module_name}' is already enabled."})
        
    otz_filepath = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.otz")
    loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
    if os.path.exists(otz_filepath):
        shutil.rmtree(loaded_module_dir, ignore_errors=True)
        with zipfile.ZipFile(otz_filepath, 'r') as zip_ref:
            os.makedirs(loaded_module_dir, exist_ok=True)
            zip_ref.extractall(loaded_module_dir)
            os.utime(loaded_module_dir, (os.path.getmtime(otz_filepath), os.path.getmtime(otz_filepath)))

    module_record.is_enabled = True
    db.commit()
    db.refresh(module_record)
    opentz_logger.info(f"Module '{module_name}' marked as enabled in DB. Please restart the API server to activate.")
    
    await _re_resolve_dependencies()
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Module '{module_name}' enabled. Please restart the server for changes to take effect."}
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
        opentz_logger.info(f"Successfully deleted module code directory: {loaded_module_dir}")

    module_record.is_enabled = False
    db.commit()
    db.refresh(module_record)
    opentz_logger.info(f"Module '{module_name}' marked as disabled in DB. Please restart the API server to deactivate.")
    
    await _re_resolve_dependencies()
    
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
            opentz_logger.info(f"Successfully deleted module code directory: {loaded_module_dir}")
            
        archive_file_path = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.otz")
        if os.path.exists(archive_file_path):
            os.remove(archive_file_path)
            opentz_logger.info(f"Successfully deleted module archive: {archive_file_path}")

        db.delete(module_record)
        db.commit()
        opentz_logger.info(f"Module '{module_name}' record deleted from database.")

        await _re_resolve_dependencies()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Module '{module_name}' uninstalled. Please restart the API server to apply changes."}
        )

    except Exception as e:
        db.rollback()
        opentz_logger.exception(f"Error during module uninstall of '{module_name}'.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to uninstall module: {e}. Manual intervention may be required."
        )
