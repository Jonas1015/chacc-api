import io
import os
import importlib.util
import sys
import shutil
import json
import logging
import zipfile
from fastapi import Depends, Request, status, UploadFile, File, HTTPException, APIRouter, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.logger import LogLevels, configure_logging

from .constants import LOGGER_NAME, MODULES_INSTALLED_DIR, MODULES_LOADED_DIR, MODULES_UPLOAD_DIR
from .database import get_db, ModuleRecord
from .core_services import BackboneContext
from .dependency_manager import (
    invalidate_dependency_cache,
    invalidate_module_cache,
    re_resolve_dependencies
)
adcore_logger = configure_logging(log_level=LogLevels.INFO)


def _calculate_module_hash(module_name: str, requirements_content: str) -> str:
    """Calculate hash of a specific module's requirements."""
    content = f"{module_name}:{requirements_content}"
    return hashlib.sha256(content.encode()).hexdigest()


def _calculate_combined_requirements_hash(module_hashes: dict) -> str:
    """Calculate hash of all module requirement hashes combined."""
    sorted_hashes = sorted(module_hashes.items())
    combined = "|".join(f"{name}:{hash}" for name, hash in sorted_hashes)
    return hashlib.sha256(combined.encode()).hexdigest()


def _load_dependency_cache() -> dict:
    """Load dependency cache from file."""
    if os.path.exists(DEPENDENCY_CACHE_FILE):
        try:
            with open(DEPENDENCY_CACHE_FILE, 'r') as f:
                cache = json.load(f)
                # Ensure new structure exists
                if 'module_caches' not in cache:
                    cache['module_caches'] = {}
                if 'combined_hash' not in cache:
                    cache['combined_hash'] = None
                return cache
        except (json.JSONDecodeError, IOError) as e:
            adcore_logger.warning(f"Failed to load dependency cache: {e}")
    return {
        'module_caches': {},
        'combined_hash': None,
        'last_updated': None
    }


def _save_dependency_cache(cache_data: dict):
    """Save dependency cache to file."""
    try:
        os.makedirs(os.path.dirname(DEPENDENCY_CACHE_FILE), exist_ok=True)
        with open(DEPENDENCY_CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
    except IOError as e:
        adcore_logger.error(f"Failed to save dependency cache: {e}")


def _invalidate_dependency_cache():
    """Invalidate the dependency cache by clearing it."""
    try:
        # Instead of deleting, clear the cache to preserve structure
        cache_data = {
            'module_caches': {},
            'backbone_hash': None,
            'combined_hash': None,
            'resolved_packages': {},
            'last_updated': None
        }
        _save_dependency_cache(cache_data)
        adcore_logger.info("Dependency cache invalidated")
    except Exception as e:
        adcore_logger.warning(f"Failed to invalidate dependency cache: {e}")
        # Fallback: try to remove the file
        if os.path.exists(DEPENDENCY_CACHE_FILE):
            try:
                os.remove(DEPENDENCY_CACHE_FILE)
                adcore_logger.info("Dependency cache file removed")
            except IOError as e2:
                adcore_logger.error(f"Failed to remove dependency cache file: {e2}")


def _invalidate_module_cache(module_name: str):
    """Invalidate cache for a specific module."""
    try:
        cache = _load_dependency_cache()
        if module_name in cache.get('module_caches', {}):
            del cache['module_caches'][module_name]
            # Clear combined hash to force recalculation
            cache['combined_hash'] = None
            _save_dependency_cache(cache)
            adcore_logger.info(f"Cache invalidated for module: {module_name}")
    except Exception as e:
        adcore_logger.warning(f"Failed to invalidate cache for module {module_name}: {e}")


def _get_installed_packages() -> set:
    """Get set of currently installed packages."""
    try:
        result = subprocess.run([
            sys.executable, "-m", "pip", "list", "--format=freeze"
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            packages = set()
            for line in result.stdout.strip().split('\n'):
                if '==' in line:
                    package_name = line.split('==')[0].lower()
                    packages.add(package_name)
            return packages
        else:
            adcore_logger.warning(f"Failed to get installed packages: {result.stderr}")
            return set()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        adcore_logger.warning(f"Error getting installed packages: {e}")
        return set()


def _resolve_module_dependencies(module_name: str, requirements_content: str) -> dict:
    """Resolve dependencies for a specific module."""
    adcore_logger.info(f"Resolving dependencies for module: {module_name}")

    temp_req_file = os.path.join(MODULES_UPLOAD_DIR, f"temp_{module_name}_requirements.txt")

    try:
        with open(temp_req_file, "w") as f:
            f.write(requirements_content)

        # Compile dependencies for this module
        result = subprocess.run([
            sys.executable, "-m", "piptools", "compile",
            "--output-file", f"{temp_req_file}.lock",
            "--allow-unsafe",
            temp_req_file
        ], capture_output=True, text=True)

        if result.returncode != 0:
            adcore_logger.error(f"Failed to resolve dependencies for {module_name}: {result.stderr}")
            return {}

        # Parse the lock file
        resolved_packages = {}
        lock_file = f"{temp_req_file}.lock"
        if os.path.exists(lock_file):
            with open(lock_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '==' in line:
                        parts = line.split('==')
                        if len(parts) >= 2:
                            package_name = parts[0]
                            version = parts[1]
                            resolved_packages[package_name] = f"=={version}"

        adcore_logger.info(f"Resolved {len(resolved_packages)} packages for {module_name}")
        return resolved_packages

    except Exception as e:
        adcore_logger.error(f"Error resolving dependencies for {module_name}: {e}")
        return {}
    finally:
        # Clean up temporary files
        for file in [temp_req_file, f"{temp_req_file}.lock"]:
            if os.path.exists(file):
                os.remove(file)


def _merge_resolved_packages(*package_dicts: dict) -> dict:
    """Merge multiple resolved package dictionaries, resolving conflicts."""
    merged = {}

    for package_dict in package_dicts:
        for package_name, version_spec in package_dict.items():
            if package_name in merged:
                # If versions conflict, prefer the newer one (simple strategy)
                existing_version = merged[package_name]
                if version_spec != existing_version:
                    adcore_logger.warning(f"Version conflict for {package_name}: {existing_version} vs {version_spec}, using {version_spec}")
            merged[package_name] = version_spec

    return merged


def _install_missing_packages(resolved_packages: dict, installed_packages: set):
    """Install only packages that are not already installed."""
    packages_to_install = []

    for package_name, version_spec in resolved_packages.items():
        package_name_lower = package_name.lower()
        if package_name_lower not in installed_packages:
            packages_to_install.append(f"{package_name}{version_spec}")
        else:
            adcore_logger.debug(f"Package {package_name} already installed, skipping")

    if packages_to_install:
        adcore_logger.info(f"Installing {len(packages_to_install)} missing packages...")
        try:
            # Install packages in batches to avoid command line length limits
            batch_size = 50
            for i in range(0, len(packages_to_install), batch_size):
                batch = packages_to_install[i:i + batch_size]
                result = subprocess.run([
                    sys.executable, "-m", "pip", "install", "--quiet"
                ] + batch, capture_output=True, text=True, timeout=300)

                if result.returncode != 0:
                    adcore_logger.error(f"Failed to install package batch: {result.stderr}")
                    raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)

            adcore_logger.info("Package installation completed successfully")
        except subprocess.TimeoutExpired:
            adcore_logger.error("Package installation timed out")
            raise
    else:
        adcore_logger.info("All required packages are already installed")


async def _re_resolve_dependencies():
    """Re-resolve dependencies using the dependency manager."""
    await re_resolve_dependencies()


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
                    adcore_logger.info(f"Dynamically imported models from: {module_name}")
                except Exception as e:
                    adcore_logger.error(f"Failed to import models from {file_path}: {e}", exc_info=True)


async def run_module_tests(module_name: str, module_path: str, test_entry_point: str):
    """
    Run tests for a specific module.
    """
    adcore_logger.info(f"Running tests for module '{module_name}'...")
    try:
        module_relative_path, func_name = test_entry_point.split(":")
        test_code_dir = os.path.join(module_path, "module")
        test_main_file_path = os.path.join(test_code_dir, *module_relative_path.split('.')) + ".py"

        if not os.path.exists(test_main_file_path):
            adcore_logger.warning(f"Test entry point file '{test_main_file_path}' not found for module '{module_name}'.")
            return

        sys.path.insert(0, test_code_dir)

        spec = importlib.util.spec_from_file_location(module_relative_path, test_main_file_path)
        if spec is None:
            adcore_logger.error(f"Could not create spec for test module '{module_name}'.")
            return

        test_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(test_module)

        test_func = getattr(test_module, func_name, None)
        if not test_func or not callable(test_func):
            adcore_logger.warning(f"Test entry point function '{func_name}' not found or not callable for module '{module_name}'.")
            return

        await test_func()
        adcore_logger.info(f"Tests for module '{module_name}' passed successfully.")
        
    except Exception as e:
        adcore_logger.warning(f"Tests for module '{module_name}' failed: {str(e)}")
        import traceback
        adcore_logger.warning(f"Test failure details: {traceback.format_exc()}")
    finally:
        if test_code_dir in sys.path:
            sys.path.remove(test_code_dir)


async def load_modules(app: FastAPI, backbone_context: BackboneContext, only_modules: list = None, exclude_modules: list = None):
    """
    Discovers modules from the MODULES_INSTALLED_DIR, synchronizes the database,
    and then loads enabled modules into the application.
    """
    adcore_logger.info("Starting module discovery and database synchronization...")
    
    re_resolve_required = False
    db = await anext(get_db())
    
    try:
        if MODULES_LOADED_DIR not in sys.path:
            sys.path.append(MODULES_LOADED_DIR)

        installed_adcore_files = {f for f in os.listdir(MODULES_INSTALLED_DIR) if f.endswith('.adcore')}
        existing_records = {record.name: record for record in db.query(ModuleRecord).all()}
        
        for adcore_filename in installed_adcore_files:
            module_name = adcore_filename.replace('.adcore', '')
            adcore_filepath = os.path.join(MODULES_INSTALLED_DIR, adcore_filename)
            loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)

            adcore_mtime = os.path.getmtime(adcore_filepath)

            is_new_module = module_name not in existing_records
            
            should_unzip = False
            if not os.path.exists(loaded_module_dir):
                adcore_logger.info(f"New module detected on disk: '{module_name}'.")
                should_unzip = True
                re_resolve_required = True
            else:
                loaded_mtime = os.path.getmtime(loaded_module_dir)
                if adcore_mtime > loaded_mtime:
                    adcore_logger.info(f"Module '{module_name}' archive is newer than loaded directory. Unzipping again.")
                    shutil.rmtree(loaded_module_dir)
                    should_unzip = True
                    re_resolve_required = True
            
            if should_unzip:
                adcore_logger.info(f"Unzipping module '{module_name}' to '{loaded_module_dir}'...")
                with zipfile.ZipFile(adcore_filepath, 'r') as zip_ref:
                    os.makedirs(loaded_module_dir, exist_ok=True)
                    zip_ref.extractall(loaded_module_dir)
                    os.utime(loaded_module_dir, (adcore_mtime, adcore_mtime))
                adcore_logger.info(f"Unzipping for '{module_name}' completed.")

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
                    adcore_logger.info(f"New module '{module_name}' found. Created new DB record.")
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
                        adcore_logger.info(f"Existing module '{module_name}' metadata updated.")

        
        installed_module_names = {f.replace('.adcore', '') for f in installed_adcore_files}
        for module_name, record in list(existing_records.items()):
            if module_name not in installed_module_names:
                db.delete(record)
                adcore_logger.warning(f"Module '{module_name}' record found in DB but not on disk. Deleting record and its code.")
                loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
                if os.path.exists(loaded_module_dir):
                    shutil.rmtree(loaded_module_dir)
                re_resolve_required = True
        
        db.commit()

        module_found = db.query(ModuleRecord).first()
        if module_found:
            db.refresh(module_found)
        
        adcore_logger.info("Database synchronized with filesystem. Proceeding to load modules...")
        
        query = db.query(ModuleRecord).filter_by(is_enabled=True)
        if only_modules:
            query = query.filter(ModuleRecord.name.in_(only_modules))
        if exclude_modules:
            adcore_logger.info(f"Excluding modules from loading: {exclude_modules}")
            if "authentication" in exclude_modules:
                adcore_logger.warning("Skipping authentication module during initial module load.")
            query = query.filter(ModuleRecord.name.notin_(exclude_modules))
        
        updated_records = query.all()

        for record in updated_records:
            module_name = record.name
            module_path = os.path.join(MODULES_LOADED_DIR, module_name)
            
            if not record.is_enabled:
                adcore_logger.info(f"Skipping disabled module: {module_name}")
                continue
            
            if not os.path.isdir(module_path):
                adcore_logger.error(f"Module '{module_name}' marked as enabled in DB but its directory is missing: {module_path}. Setting it to disabled.")
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
                    adcore_logger.warning(f"Skipping '{module_name}': Invalid 'entry_point' in DB metadata.")
                    continue

                module_relative_path, func_name = entry_point_str.split(":")
                plugin_code_dir = os.path.join(module_path, "module")
                plugin_main_file_path = os.path.join(plugin_code_dir, *module_relative_path.split('.')) + ".py"

                if not os.path.exists(plugin_main_file_path):
                    adcore_logger.warning(f"Skipping '{module_name}': Entry point file '{plugin_main_file_path}' not found on disk. Setting module to disabled.")
                    record.is_enabled = False
                    db.commit()
                    continue

                sys.path.insert(0, plugin_code_dir)

                spec = importlib.util.spec_from_file_location(module_relative_path, plugin_main_file_path)
                if spec is None:
                    adcore_logger.error(f"Could not create spec for module '{module_name}'.")
                    continue
                
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                setup_func = getattr(module, func_name, None)
                if not setup_func or not callable(setup_func):
                    adcore_logger.warning(f"Plugin '{module_name}': Entry point function '{func_name}' not found or not callable after import.")
                    continue

                
                plugin_router = setup_func(backbone_context)

                if plugin_router and isinstance(plugin_router, APIRouter):
                    adcore_logger.info(f"Mounting router for module '{module_name}' at prefix: {record.base_path_prefix}")
                    app.include_router(plugin_router, prefix=record.base_path_prefix, tags=module_meta.get("tags", [record.display_name]))
                    adcore_logger.info(f"Module '{module_name}' loaded and enabled with prefix: {record.base_path_prefix}")

                    # Run module tests if test_entry_point is defined
                    test_entry_point = module_meta.get("test_entry_point")
                    if test_entry_point:
                        await run_module_tests(module_name, module_path, test_entry_point)
                else:
                    adcore_logger.warning(f"Plugin '{module_name}': Setup function did not return an APIRouter.")

            except Exception as e:
                adcore_logger.error(f"Error loading module '{module_name}': {e}", exc_info=True)
            finally:
                if plugin_code_dir in sys.path:
                    sys.path.remove(plugin_code_dir)

    finally:
        db.close()
        adcore_logger.debug("Database session for module loading closed.")
    
    if MODULES_LOADED_DIR in sys.path:
        sys.path.remove(MODULES_LOADED_DIR)

    if re_resolve_required:
        adcore_logger.info("Changes detected in module configuration. Re-resolving dependencies.")
        await _re_resolve_dependencies()
        adcore_logger.info("Dependencies resolved. A server restart is required to load the new modules.")
    else:
        adcore_logger.info("No changes in module configuration detected. Skipping dependency resolution.")

    adcore_logger.info("Module loading completed.")

modules_router = APIRouter()

@modules_router.post("/modules/")
async def install_adcore_module_endpoint(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Installs a new AdCore API module from an .adcore package.
    Requires server restart to activate/deactivate the new module.
    """
    if not file.filename.endswith(".adcore"):
        adcore_logger.error(f"Uploaded file '{file.filename}' is not a .adcore package.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .adcore module packages are allowed."
        )

    file_content = await file.read()
    
    try:
        with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zip_ref:
            try:
                with zip_ref.open('module_meta.json') as meta_file:
                    meta_data = json.load(meta_file)
            except KeyError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing 'module_meta.json' in the .adcore package.")
            
            module_name = meta_data.get("name")
            if not module_name:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'name' field is missing in 'module_meta.json'.")

            target_adcore_path = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.adcore")
            with open(target_adcore_path, "wb") as f:
                f.write(file_content)
            adcore_logger.info(f"Module archive '{module_name}.adcore' saved to '{target_adcore_path}'.")

        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
        if os.path.exists(loaded_module_dir):
            shutil.rmtree(loaded_module_dir)
        with zipfile.ZipFile(target_adcore_path, 'r') as zip_ref:
            os.makedirs(loaded_module_dir, exist_ok=True)
            zip_ref.extractall(loaded_module_dir)
            os.utime(loaded_module_dir, (os.path.getmtime(target_adcore_path), os.path.getmtime(target_adcore_path)))
        adcore_logger.info(f"Successfully unzipped module '{module_name}' to '{loaded_module_dir}'.")

        # Invalidate cache for the newly installed module
        _invalidate_module_cache(module_name)
        await _re_resolve_dependencies()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Module '{module_name}' installed/updated successfully. Please restart the API server to apply changes."}
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        adcore_logger.error(f"Error during module installation: {e}", exc_info=True)
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
        
    adcore_filepath = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.adcore")
    loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
    if os.path.exists(adcore_filepath):
        shutil.rmtree(loaded_module_dir, ignore_errors=True)
        with zipfile.ZipFile(adcore_filepath, 'r') as zip_ref:
            os.makedirs(loaded_module_dir, exist_ok=True)
            zip_ref.extractall(loaded_module_dir)
            os.utime(loaded_module_dir, (os.path.getmtime(adcore_filepath), os.path.getmtime(adcore_filepath)))

    module_record.is_enabled = True
    db.commit()
    db.refresh(module_record)
    adcore_logger.info(f"Module '{module_name}' marked as enabled in DB. Please restart the API server to activate.")

    # Invalidate cache for the enabled module
    _invalidate_module_cache(module_name)
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
        adcore_logger.info(f"Successfully deleted module code directory: {loaded_module_dir}")

    module_record.is_enabled = False
    db.commit()
    db.refresh(module_record)
    adcore_logger.info(f"Module '{module_name}' marked as disabled in DB. Please restart the API server to deactivate.")

    # Invalidate cache for the disabled module
    _invalidate_module_cache(module_name)
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
            adcore_logger.info(f"Successfully deleted module code directory: {loaded_module_dir}")
            
        archive_file_path = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.adcore")
        if os.path.exists(archive_file_path):
            os.remove(archive_file_path)
            adcore_logger.info(f"Successfully deleted module archive: {archive_file_path}")

        db.delete(module_record)
        db.commit()
        adcore_logger.info(f"Module '{module_name}' record deleted from database.")

        # Invalidate cache for the uninstalled module
        _invalidate_module_cache(module_name)
        await _re_resolve_dependencies()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Module '{module_name}' uninstalled. Please restart the API server to apply changes."}
        )

    except Exception as e:
        db.rollback()
        adcore_logger.exception(f"Error during module uninstall of '{module_name}'.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to uninstall module: {e}. Manual intervention may be required."
        )
