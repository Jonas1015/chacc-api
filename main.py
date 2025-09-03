# main.py
import io
import os
import importlib.util
import sys
import shutil
import json
import logging
import subprocess
import zipfile
from fastapi import Depends, FastAPI, Request, status, UploadFile, File, HTTPException
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.routing import APIRoute, APIRouter
from functools import wraps
from sqlalchemy.orm import Session

from src.rate_limiter import limiter, rate_limit_exceeded_handler
from src.core_services import BackboneContext
from src.logger import configure_logging, LogLevels
from src.database import get_db, OpenTzBaseModel, engine, ModuleRecord

MODULES_INSTALLED_DIR = ".modules_installed"
MODULES_UPLOAD_DIR = ".modules_upload"
MODULES_LOADED_DIR = ".modules_loaded"

os.makedirs(MODULES_INSTALLED_DIR, exist_ok=True)
os.makedirs(MODULES_UPLOAD_DIR, exist_ok=True)
os.makedirs(MODULES_LOADED_DIR, exist_ok=True)

opentz_logger = configure_logging(log_level=LogLevels.info)

@asynccontextmanager
async def onStartupLifespan(app: FastAPI):
    OpenTzBaseModel.metadata.create_all(bind=engine)
    opentz_logger.info("Database tables ensured for core models and ModuleRecord.")
    await load_modules()
    yield
    

app = FastAPI(
    title="Open-TZ API Backbone",
    description="A modular FastAPI application for extensible APIs.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=onStartupLifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


loaded_modules = {} # Examle { "module_name": {"enabled": True, "router": <FastAPI.APIRouter>, "info": {}, "meta": {}} }
mounted_routers = {}

async def _re_resolve_dependencies():
    """
    Re-resolves and reinstalls all dependencies based on current active modules and backbone.
    This should be called after module installation or uninstallation.
    Requires a server restart to take full effect.
    """
    opentz_logger.info("Starting dependency re-resolution process...")

    temp_req_file = os.path.join(MODULES_UPLOAD_DIR, "temp_combined_requirements.txt")
    new_lock_file = os.path.join(MODULES_UPLOAD_DIR, "re_resolved_requirements.lock")
    
    try:
        with open(temp_req_file, "w") as f:
            core_req_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
            if os.path.exists(core_req_path):
                f.write(f"-r {core_req_path}\n")
            else:
                opentz_logger.warning("No project-level requirements.txt found for backbone core.")

            db = await anext(get_db())
            try:
                installed_modules_records = db.query(ModuleRecord).all()
                for record in installed_modules_records:
                    module_name = record.name
                    module_meta = record.meta_data if record.meta_data else {} # Use meta_data from DB
                    
                    dependencies_file_name = module_meta.get("dependencies_file", "requirements.txt")
                    module_req_path = os.path.join(MODULES_INSTALLED_DIR, module_name, dependencies_file_name)

                    if os.path.exists(module_req_path):
                        f.write(f"-r {module_req_path}\n")
                        opentz_logger.info(f"Including dependencies from installed module: {module_name} ({module_req_path})")
                    else:
                        opentz_logger.warning(f"Module '{module_name}' has no '{dependencies_file_name}' file found.")
            finally:
                db.close()
        subprocess.check_call([
            sys.executable, "-m", "piptools", "compile",
            "--output-file", new_lock_file,
            "--allow-unsafe",
            temp_req_file
        ])
        opentz_logger.info(f"Generated new lock file: {new_lock_file}")

        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", new_lock_file,
            "--force-reinstall",
            "--no-deps"
        ])
        opentz_logger.info("Python environment updated successfully based on new lock file.")

    except subprocess.CalledProcessError as e:
        opentz_logger.error(f"Failed to manage dependencies: {e.stderr.decode() if e.stderr else e}", exc_info=True)
        raise RuntimeError(f"Dependency management failed. Check logs for details. Error: {e}")
    except Exception as e:
        opentz_logger.error(f"Unexpected error during dependency re-resolution: {e}", exc_info=True)
        raise RuntimeError(f"Dependency management failed due to an unexpected error: {e}")
    finally:
        if os.path.exists(temp_req_file):
            os.remove(temp_req_file)
        if os.path.exists(new_lock_file):
            os.remove(new_lock_file)
        opentz_logger.info("Dependency re-resolution process finished.")


def install_module_from_otz(otz_filepath: str, db: Session):
    """
    Installs a module from a .otz file.
    Unzips it into MODULES_INSTALLED_DIR and reads its metadata.
    Persists module metadata to the database.
    Does NOT activate or load routes into the running app.
    """
    if not os.path.exists(otz_filepath):
        raise FileNotFoundError(f".otz file not found: {otz_filepath}")

    temp_extract_dir = os.path.join(MODULES_UPLOAD_DIR, os.path.basename(otz_filepath).replace(".otz", "_temp_extract"))
    if os.path.exists(temp_extract_dir):
        shutil.rmtree(temp_extract_dir)
    os.makedirs(temp_extract_dir)

    module_meta = None
    module_name = None
    module_target_path = None

    try:
        with zipfile.ZipFile(otz_filepath, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_dir)

        meta_filepath = os.path.join(temp_extract_dir, "module_meta.json")
        if not os.path.exists(meta_filepath):
            raise ValueError("Invalid .otz package: module_meta.json not found.")

        with open(meta_filepath, 'r') as f:
            module_meta = json.load(f)

        module_name = module_meta.get("name")
        if not module_name:
            raise ValueError("module_meta.json must contain a 'name' field.")
        
        entry_point = module_meta.get("entry_point")
        if not entry_point or ":" not in entry_point:
            raise ValueError("Invalid module_meta.json: 'entry_point' field is missing or malformed (e.g., 'module.main:setup_plugin').")

        extracted_module_code_path = os.path.join(temp_extract_dir, "module")
        if not os.path.exists(extracted_module_code_path) or not os.path.isdir(extracted_module_code_path):
            raise ValueError("Invalid .otz package: 'module/' directory containing code not found inside.")

        module_target_path = os.path.join(MODULES_INSTALLED_DIR, module_name)
        if os.path.exists(module_target_path):
            opentz_logger.warning(f"Existing module '{module_name}' found. Overwriting code directory.")
            shutil.rmtree(module_target_path)
        
        shutil.copytree(extracted_module_code_path, module_target_path)
        shutil.copy(meta_filepath, os.path.join(module_target_path, "module_meta.json"))
        
        req_filepath_temp = os.path.join(temp_extract_dir, module_meta.get("dependencies_file", "requirements.txt"))
        if os.path.exists(req_filepath_temp):
            shutil.copy(req_filepath_temp, os.path.join(module_target_path, module_meta.get("dependencies_file", "requirements.txt")))

        opentz_logger.info(f"Module '{module_name}' extracted to {module_target_path}")

        module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
        
        existing_module_with_prefix = db.query(ModuleRecord).filter(ModuleRecord.base_path_prefix == module_meta.get("base_path_prefix"), ModuleRecord.name != module_name).first()
        if existing_module_with_prefix:
            raise ValueError(f"Base path prefix '{module_meta.get('base_path_prefix')}' is already in use by another module '{existing_module_with_prefix.name}'. Please choose a unique prefix.")
        
        if not module_record:
            module_record = ModuleRecord(name=module_name)
            db.add(module_record)
            opentz_logger.info(f"New database record created for module '{module_name}'.")
        else:
            opentz_logger.info(f"Existing database record found for module '{module_name}'. Updating.")
        
        module_record.display_name = module_meta.get("display_name", module_name)
        module_record.version = module_meta.get("version", "0.0.0")
        module_record.author = module_meta.get("author", "Unknown")
        module_record.description = module_meta.get("description", "No description provided.")
        if module_meta.get("status") is not None:
             module_record.is_enabled = module_meta.get("status").lower() == "enabled"
        else:
            if not module_record.id:
                 module_record.is_enabled = True

        module_record.base_path_prefix = module_meta.get("base_path_prefix", f"/{module_name}")
        module_record.meta_data = module_meta

        db.commit()
        db.refresh(module_record)
        opentz_logger.info(f"Module '{module_name}' details persisted to database.")

        return module_meta
    except Exception as e:
        opentz_logger.error(f"Failed to process .otz file {otz_filepath}: {e}", exc_info=True)
        db.rollback()
        if module_target_path and os.path.exists(module_target_path):
            shutil.rmtree(module_target_path)
        raise
    finally:
        db.close()
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir)
            

async def load_modules():
    """
    Discovers and loads modules from the MODULES_INSTALLED_DIR.
    Sets up routes for modules marked as enabled in the database.
    """
    opentz_logger.info(f"Loading modules from '{MODULES_INSTALLED_DIR}' based on database state...")
    if not os.path.exists(MODULES_INSTALLED_DIR):
        opentz_logger.warning(f"Installed modules directory '{MODULES_INSTALLED_DIR}' not found.")
        return

    if MODULES_INSTALLED_DIR not in sys.path:
        sys.path.insert(0, MODULES_INSTALLED_DIR)

    backbone_context = BackboneContext(
        app=app,
        limiter=app.state.limiter,
        logger=opentz_logger,
        db_session_factory=get_db
    )

    if MODULES_LOADED_DIR not in sys.path:
        sys.path.append(MODULES_LOADED_DIR)
    
    db = await anext(get_db())
    try:
        installed_modules = db.query(ModuleRecord).all()

        for record in installed_modules:
            module_name = record.name
            module_path = os.path.join(MODULES_INSTALLED_DIR, module_name)

            if not os.path.isdir(module_path):
                opentz_logger.warning(f"Module '{module_name}' found in DB but directory '{module_path}' is missing. Removing record from the database.")
                record_to_delete = db.query(ModuleRecord).filter_by(name=module_name).first()
                if record_to_delete:
                    db.delete(record_to_delete)
                    db.commit()
                continue

            try:
                module_meta = record.meta_data if record.meta_data else {}
                entry_point_str = module_meta.get("entry_point")
                
                if not entry_point_str or ":" not in entry_point_str:
                    opentz_logger.warning(f"Skipping '{module_name}': Invalid 'entry_point' in DB metadata.")
                    continue

                module_relative_path, func_name = entry_point_str.split(":")
                plugin_code_dir = os.path.join(module_path)
                plugin_main_file_path = os.path.join(plugin_code_dir, *module_relative_path.split('.')) + ".py"

                if not os.path.exists(plugin_main_file_path):
                    opentz_logger.warning(f"Skipping '{module_name}': Entry point file '{plugin_main_file_path}' not found on disk.")

                    if(record.is_enabled):
                        opentz_logger.error(f"Module '{module_name}' is marked as enabled in DB but entry point file is missing. Disabling module.")
                        record.is_enabled = False
                        db.commit()
                    continue

                unique_module_import_name = f"otz_module_{module_name.replace('-', '_')}_{module_relative_path.replace('.', '_')}"
                
                spec = importlib.util.spec_from_file_location(unique_module_import_name, plugin_main_file_path)
                if spec is None:
                    opentz_logger.error(f"Could not create spec for module '{module_name}'.")
                    continue
                
                module = importlib.util.module_from_spec(spec)
                sys.path.insert(0, plugin_code_dir)
                spec.loader.exec_module(module)
                sys.path.pop(0)

                setup_func = getattr(module, func_name, None)
                if not setup_func or not callable(setup_func):
                    opentz_logger.warning(f"Plugin '{module_name}': Entry point function '{func_name}' not found or not callable after import.")
                    continue

                get_info_func = getattr(module, 'get_plugin_info', None)
                plugin_info_for_display = get_info_func() if get_info_func else module_meta
                
                is_enabled = record.is_enabled

                plugin_router = setup_func(backbone_context)

                if plugin_router and isinstance(plugin_router, APIRouter):
                    mounted_routers[module_name] = {
                        "enabled": is_enabled,
                        "router": plugin_router,
                        "info": plugin_info_for_display,
                        "meta": module_meta
                    }
                    if is_enabled:
                        router_prefix = record.base_path_prefix
                        app.include_router(plugin_router, prefix=router_prefix)
                        opentz_logger.info(f"Module '{module_name}' loaded and enabled with prefix: {router_prefix}")
                    else:
                        opentz_logger.info(f"Module '{module_name}' discovered but currently disabled in DB.")
                else:
                    opentz_logger.warning(f"Plugin '{module_name}': Setup function did not return an APIRouter.")

            except Exception as e:
                opentz_logger.error(f"Error loading module '{module_name}': {e}", exc_info=True)
                if plugin_code_dir in sys.path:
                    sys.path.remove(plugin_code_dir)
    finally:
        db.close()
        opentz_logger.debug("Database session for module loading closed.")


    if MODULES_INSTALLED_DIR in sys.path:
        sys.path.remove(MODULES_INSTALLED_DIR)

    opentz_logger.info("Module loading completed.")



@app.get("/")
async def read_root(request: Request):
    """
    Root endpoint of the Open-TZ API backbone.
    """# Use prefix from DB
    return {"message": "Welcome to the Open-TZ API Backbone! Check /docs for API modules."}

@app.get("/core-data")
@limiter.limit("10/minute")
async def get_core_data(request: Request):
    """
    An example core endpoint of the backbone.
    """
    return {"data": "This is data from the core Open-TZ backbone."}


@app.post("/modules/")
async def install_otz_module_endpoint(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Installs a new Open-TZ module from an .otz package.
    The module is identified by the `name` field in its `module_meta.json`.
    If a module with the same name exists, it will be overwritten.
    Requires server restart to activate/deactivate the new module.
    """
    if not file.filename.endswith(".otz"):
        opentz_logger.error(f"Uploaded file '{file.filename}' is not a .otz package.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .otz module packages are allowed."
        )

    otz_filepath = os.path.join(MODULES_UPLOAD_DIR, file.filename)

    try:
        file_content = await file.read()
            
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
                opentz_logger.info(f"Removing old unzipped version from '{loaded_module_dir}'.")
                shutil.rmtree(loaded_module_dir)
            
            os.makedirs(loaded_module_dir, exist_ok=True)
            zip_ref.extractall(loaded_module_dir)
            opentz_logger.info(f"Module '{module_name}' successfully unzipped to '{loaded_module_dir}'.")

            record = db.query(ModuleRecord).filter_by(name=module_name).first()
            if record:
                record.display_name = meta_data.get("display_name", record.display_name)
                record.version = meta_data.get("version", record.version)
                record.author = meta_data.get("author", record.author)
                record.description = meta_data.get("description", record.description)
                record.base_path_prefix = meta_data.get("base_path_prefix", record.base_path_prefix)
                record.meta_data = meta_data
                record.is_enabled = True # Automatically enable on install/update
                db.commit()
                db.refresh(record)
                opentz_logger.info(f"Database record for '{module_name}' updated.")
            else:
                new_record = ModuleRecord(
                    name=module_name,
                    display_name=meta_data.get("display_name"),
                    version=meta_data.get("version"),
                    author=meta_data.get("author"),
                    description=meta_data.get("description"),
                    is_enabled=True,
                    base_path_prefix=meta_data.get("base_path_prefix"),
                    meta_data=meta_data
                )
                db.add(new_record)
                db.commit()
                db.refresh(new_record)
                opentz_logger.info(f"New database record for '{module_name}' created.")
    except HTTPException:
        raise
    except Exception as e:
        opentz_logger.error(f"Error during module installation: {e}", exc_info=True)
        if 'loaded_module_dir' in locals() and os.path.exists(loaded_module_dir):
            shutil.rmtree(loaded_module_dir)
        if 'target_otz_path' in locals() and os.path.exists(target_otz_path):
            os.remove(target_otz_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Installation failed: {e}")
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Module '{module_name}' installed/updated successfully. Restart the application to apply changes."}
    )


@app.get("/modules/")
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

@app.post("/modules/{module_name}/enable")
async def enable_module_endpoint(module_name: str, db: Session = Depends(get_db)):
    """
    Marks a module as enabled in the database. Requires server restart to take effect.
    """
    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database.")

    if module_record.is_enabled:
        return JSONResponse(content={"message": f"Module '{module_name}' is already enabled."})

    module_record.is_enabled = True
    db.commit()
    db.refresh(module_record)
    opentz_logger.info(f"Module '{module_name}' marked as enabled in DB. Please restart the API server to activate.")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Module '{module_name}' enabled. Please restart the server for changes to take effect."}
    )

@app.post("/modules/{module_name}/disable")
async def disable_module_endpoint(module_name: str, db: Session = Depends(get_db)):
    """
    Marks a module as disabled in the database. Requires server restart to take effect.
    """
    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first() # CHECK DB
    if not module_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database.")

    if not module_record.is_enabled:
        return JSONResponse(content={"message": f"Module '{module_name}' is already disabled."})

    module_record.is_enabled = False
    db.commit()
    db.refresh(module_record)
    opentz_logger.info(f"Module '{module_name}' marked as disabled in DB. Please restart the API server to deactivate.")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Module '{module_name}' disabled. Please restart the server for changes to take effect."}
    )

@app.delete("/modules/{module_name}/uninstall")
async def uninstall_module_endpoint(module_name: str, db: Session = Depends(get_db)):
    """
    Uninstalls a module by removing its code from disk and its record from the database.
    Re-resolves dependencies. Requires server restart to take full effect.
    """

    if not db:
        opentz_logger.error("Database session not available for uninstall operation.")

    module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
    if not module_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found in database.")

    try:
        archive_file_path = os.path.join(MODULES_INSTALLED_DIR, f"{module_name}.otz")
        if os.path.exists(archive_file_path):
            os.remove(archive_file_path)
            opentz_logger.info(f"Successfully deleted module archive: {archive_file_path}")
        else:
            opentz_logger.warning(f"Module code directory for '{module_name}' not found on modules archive.")

        loaded_module_dir = os.path.join(MODULES_LOADED_DIR, module_name)
        if os.path.exists(loaded_module_dir):
            shutil.rmtree(loaded_module_dir)
            opentz_logger.info(f"Successfully deleted module directory: {loaded_module_dir}")
        else:
            opentz_logger.warning(f"Module code directory for '{module_name}' not found on disk, but record exists in DB. Proceeding with DB record deletion.")

        db.delete(module_record)
        db.commit()
        opentz_logger.info(f"Module '{module_name}' record deleted from database.")

        await _re_resolve_dependencies()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Module '{module_name}' uninstalled. Python environment updated. Please restart the API server to apply changes."}
        )

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        opentz_logger.exception(f"Error during module uninstall of '{module_name}'.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to uninstall module: {e}. Manual intervention may be required."
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8800)