"""
ChaCC API Module Management Routes.

This module contains the FastAPI routes for managing ChaCC modules:
- install_chacc_module_endpoint: Install a new module from .chacc package
- get_modules_endpoint: Get list of all installed modules
- enable_module_endpoint: Enable a module
- disable_module_endpoint: Disable a module
- uninstall_module_endpoint: Uninstall a module

The actual module loading logic is in src/module_loader.py.
"""

import io
import os
import shutil
import json
import zipfile
from fastapi import Depends, status, UploadFile, File, HTTPException, APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional

from src.logger import LogLevels, configure_logging
from src.constants import MODULES_INSTALLED_DIR, MODULES_LOADED_DIR
from src.database import get_db, ModuleRecord
from src.chacc_dependency_manager import (
    invalidate_module_cache,
    resolve_chacc_dependencies as re_resolve_dependencies
)

from src.module_loader import (
    get_chacc_filepath,
)

chacc_logger = configure_logging(log_level=LogLevels.INFO)


modules_router = APIRouter()


async def get_current_user_optional(request: Request) -> Optional[object]:
    """
    Optional authentication dependency.
    
    If the authentication module is loaded and get_current_user is registered,
    it will require authentication. Otherwise, it returns None (allows access).
    
    This allows core APIs to be open when authentication is not present,
    but protected when the authentication module is loaded.
    """
    backbone_context = getattr(request.app.state, 'backbone_context', None)
    
    if backbone_context is None:
        chacc_logger.info("NO BACKBONE CONTEXT. ALLOW ACCESS TO CORE ROUTES")
        return None
    
    get_current_user = backbone_context.get_service('get_current_user')
    
    if get_current_user is None:
        chacc_logger.info("NO AUTHENTICATION MODULE, ALLOW ACCESS TO CORE ROUTES")
        return None
    
    from fastapi.security import HTTPAuthorizationCredentials
    
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        scheme, credentials = auth_header.split(" ")
        if scheme.lower() != 'bearer':
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        credentials_obj = HTTPAuthorizationCredentials(scheme='Bearer', credentials=credentials)
        return await get_current_user(credentials_obj)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


@modules_router.post("/modules/", dependencies=[])
async def install_chacc_module_endpoint(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: Optional[object] = Depends(get_current_user_optional)):
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
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing 'module_meta.json' in the .chacc package."
                )

            module_name = meta_data.get("name")
            if not module_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="'name' field is missing in 'module_meta.json'."
                )

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
            content={
                "message": f"Module '{module_name}' installed/updated successfully. "
                           f"Dependencies resolved. Please restart the API server to apply changes."
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        chacc_logger.error(f"Error during module installation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Installation failed: {e}"
        )


@modules_router.get("/modules/")
async def get_modules_endpoint(db: Session = Depends(get_db), current_user: Optional[object] = Depends(get_current_user_optional)):
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
async def enable_module_endpoint(module_name: str, db: Session = Depends(get_db), current_user: Optional[object] = Depends(get_current_user_optional)):
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

    chacc_filepath = get_chacc_filepath(module_name)
    if not chacc_filepath:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module archive not found.")

    # Get actual module name from module_meta.json
    actual_module_name = module_name
    try:
        with zipfile.ZipFile(chacc_filepath, 'r') as zip_ref:
            with zip_ref.open('module_meta.json') as meta_file:
                meta_data = json.load(meta_file)
                actual_module_name = meta_data.get('name', module_name)
    except Exception as e:
        chacc_logger.warning(f"Could not read module_meta.json from {chacc_filepath}: {e}")

    # Collect requirements
    module_requirements = {}
    try:
        with zipfile.ZipFile(chacc_filepath, 'r') as zip_ref:
            try:
                with zip_ref.open('requirements.txt') as req_file:
                    req_content = req_file.read().decode('utf-8')
                    module_requirements[actual_module_name] = req_content
            except KeyError:
                pass
    except Exception as e:
        chacc_logger.error(f"Could not read requirements from {module_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not read module requirements: {e}"
        )

    backbone_req_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
    if os.path.exists(backbone_req_path):
        with open(backbone_req_path, 'r') as f:
            module_requirements['backbone'] = f.read()

    if module_requirements:
        chacc_logger.info(f"Resolving dependencies for module '{actual_module_name}' before enabling...")
        try:
            from .chacc_dependency_manager import ChaCCDependencyManager
            dm = ChaCCDependencyManager(logger=chacc_logger)
            await dm.resolve_dependencies()
            chacc_logger.info("Dependencies resolved successfully.")
        except Exception as e:
            chacc_logger.error(f"Dependency resolution failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Dependency resolution failed: {e}"
            )

    # Extract module
    loaded_module_dir = os.path.join(MODULES_LOADED_DIR, actual_module_name)
    shutil.rmtree(loaded_module_dir, ignore_errors=True)
    with zipfile.ZipFile(chacc_filepath, 'r') as zip_ref:
        os.makedirs(loaded_module_dir, exist_ok=True)
        zip_ref.extractall(loaded_module_dir)
        os.utime(loaded_module_dir, (os.path.getmtime(chacc_filepath), os.path.getmtime(chacc_filepath)))

    module_record.is_enabled = True
    db.commit()
    db.refresh(module_record)
    chacc_logger.info(f"Module '{actual_module_name}' marked as enabled in DB. Please restart the API server to activate.")

    invalidate_module_cache(module_name)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": f"Module '{actual_module_name}' enabled. "
                       f"Dependencies resolved. Please restart the server for changes to take effect."
        }
    )


@modules_router.post("/modules/{module_name}/disable")
async def disable_module_endpoint(module_name: str, db: Session = Depends(get_db), current_user: Optional[object] = Depends(get_current_user_optional)):
    """
    Marks a module as disabled in the database. Requires server restart to take effect.
    """
    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database.")

    if not module_record.is_enabled:
        return JSONResponse(content={"message": f"Module '{module_name}' is already disabled."})

    actual_module_name = module_record.name
    loaded_module_dir = os.path.join(MODULES_LOADED_DIR, actual_module_name)
    if os.path.exists(loaded_module_dir):
        shutil.rmtree(loaded_module_dir)
        chacc_logger.info(f"Successfully deleted module code directory: {loaded_module_dir}")

    module_record.is_enabled = False
    db.commit()
    db.refresh(module_record)
    chacc_logger.info(f"Module '{actual_module_name}' marked as disabled in DB. Please restart the API server to deactivate.")

    invalidate_module_cache(module_name)
    await re_resolve_dependencies()
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Module '{actual_module_name}' disabled. Please restart the server for changes to take effect."}
    )


@modules_router.delete("/modules/{module_name}/uninstall")
async def uninstall_module_endpoint(module_name: str, db: Session = Depends(get_db), current_user: Optional[object] = Depends(get_current_user_optional)):
    """
    Uninstalls a module by removing its code from disk and its record from the database.
    Requires server restart to take full effect.
    """

    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database.")

    actual_module_name = module_record.name

    try:
        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, actual_module_name)
        if os.path.exists(loaded_module_dir):
            shutil.rmtree(loaded_module_dir)
            chacc_logger.info(f"Successfully deleted module code directory: {loaded_module_dir}")
        
        # Find and delete the .chacc file
        archive_file_path = get_chacc_filepath(module_name)
        
        if archive_file_path and os.path.exists(archive_file_path):
            os.remove(archive_file_path)
            chacc_logger.info(f"Successfully deleted module archive: {archive_file_path}")

        db.delete(module_record)
        db.commit()
        chacc_logger.info(f"Module '{actual_module_name}' record deleted from database.")

        invalidate_module_cache(module_name)
        await re_resolve_dependencies()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Module '{actual_module_name}' uninstalled. Please restart the API server to apply changes."}
        )

    except Exception as e:
        db.rollback()
        chacc_logger.exception(f"Error during module uninstall of '{module_name}'.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to uninstall module: {e}. Manual intervention may be required."
        )
