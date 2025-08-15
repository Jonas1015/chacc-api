# main.py
import os
import importlib.util
import sys
import shutil
import json
import logging
import subprocess
import zipfile
from fastapi import FastAPI, Request, status, UploadFile, File, HTTPException
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.routing import APIRoute, APIRouter
from functools import wraps

from src.rate_limiter import limiter, rate_limit_exceeded_handler
from src.core_services import BackboneContext
from src.logger import configure_logging, LogLevels
from src.database import get_db, OpenTzBaseModel, engine, ModuleRecord

MODULES_INSTALLED_DIR = "modules_installed"
MODULES_UPLOAD_DIR = "modules_upload"

os.makedirs(MODULES_INSTALLED_DIR, exist_ok=True)
os.makedirs(MODULES_UPLOAD_DIR, exist_ok=True)

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

            await anext(get_db())
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


async def install_module_from_otz(otz_filepath: str):
    """
    Installs a module from a .otz file.
    Unzips it into MODULES_INSTALLED_DIR and reads its metadata.
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

    db = await anext(get_db())
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
            opentz_logger.warning(f"Existing module '{module_name}' found. Overwriting.")
            shutil.rmtree(module_target_path)
        
        shutil.copytree(extracted_module_code_path, module_target_path)
        shutil.copy(meta_filepath, os.path.join(module_target_path, "module_meta.json"))
        
        req_filepath_temp = os.path.join(temp_extract_dir, module_meta.get("dependencies_file", "requirements.txt"))
        if os.path.exists(req_filepath_temp):
            shutil.copy(req_filepath_temp, os.path.join(module_target_path, module_meta.get("dependencies_file", "requirements.txt")))


        opentz_logger.info(f"Module '{module_name}' extracted to {module_target_path}")

        module_record = db.query(ModuleRecord).filter(ModuleRecord.name == module_name).first()
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
        if os.path.exists(module_target_path):
            shutil.rmtree(module_target_path)
        raise
    finally:
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
    
    db = await anext(get_db())
    try: 
        
        all_module_records = db.query(ModuleRecord).all()

        for record in all_module_records:
            module_name = record.name
            module_path = os.path.join(MODULES_INSTALLED_DIR, module_name)

            if not os.path.isdir(module_path):
                opentz_logger.warning(f"Module '{module_name}' found in DB but directory '{module_path}' is missing. Skipping load.")
                continue

            try:
                module_meta = record.meta_data if record.meta_data else {}
                entry_point_str = module_meta.get("entry_point")
                
                if not entry_point_str or ":" not in entry_point_str:
                    opentz_logger.warning(f"Skipping '{module_name}': Invalid 'entry_point' in DB metadata.")
                    continue

                module_relative_path, func_name = entry_point_str.split(":")
                plugin_code_dir = os.path.join(module_path, "module")
                plugin_main_file_path = os.path.join(plugin_code_dir, *module_relative_path.split('.')) + ".py"

                if not os.path.exists(plugin_main_file_path):
                    opentz_logger.warning(f"Skipping '{module_name}': Entry point file '{plugin_main_file_path}' not found on disk.")
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
                        "enabled": is_enabled, # This reflects the DB state
                        "router": plugin_router,
                        "info": plugin_info_for_display,
                        "meta": module_meta
                    }
                    if is_enabled:
                        router_prefix = record.base_path_prefix # Use prefix from DB
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
    """
    return {"message": "Welcome to the Open-TZ API Backbone! Check /docs for API modules."}

@app.get("/core-data")
@limiter.limit("10/minute")
async def get_core_data(request: Request):
    """
    An example core endpoint of the backbone.
    """
    return {"data": "This is data from the core Open-TZ backbone."}


@app.post("/modules/install/")
async def install_otz_module_endpoint(file: UploadFile = File(...)):
    """
    Uploads and installs an .otz module package.
    Requires server restart to activate/deactivate changes.
    """
    if not file.filename.endswith(".otz"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .otz module packages are allowed."
        )

    otz_filepath = os.path.join(MODULES_UPLOAD_DIR, file.filename)
    try:
        with open(otz_filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        module_meta = install_module_from_otz(otz_filepath)
        module_name = module_meta.get("name")

        _re_resolve_dependencies()

        opentz_logger.info(f"Module '{module_name}' installed. Please restart the API server to activate.")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Module '{module_name}' installed successfully. Python environment updated. Please restart the API server to activate."}
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        opentz_logger.exception(f"Error during .otz module installation via API.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to install .otz module: {e}"
        )
    finally:
        if os.path.exists(otz_filepath):
            os.remove(otz_filepath)


@app.get("/modules/")
async def get_modules_endpoint():
    """
    Retrieves a list of all installed modules and their current status.
    """
    # In a real system, you'd load plugin_states from a database for persistence
    # Here, it's just what was loaded at startup.
    return {
        "modules": [
            {"name": name, "enabled": state["enabled"], "info": state["info"]}
            for name, state in loaded_modules.items()
        ]
    }

@app.post("/modules/{module_name}/enable")
async def enable_module_endpoint(module_name: str):
    """
    Marks a module as enabled. Requires server restart to take effect.
    """
    if module_name not in loaded_modules:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")

    if loaded_modules[module_name]["enabled"]:
        return JSONResponse(content={"message": f"Module '{module_name}' is already enabled."})

    # In a real system, persist this state change to a database
    loaded_modules[module_name]["enabled"] = True
    opentz_logger.info(f"Module '{module_name}' marked as enabled. Please restart the API server to activate.")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Module '{module_name}' enabled. Please restart the server for changes to take effect."}
    )

@app.post("/modules/{module_name}/disable")
async def disable_module_endpoint(module_name: str):
    """
    Marks a module as disabled. Requires server restart to take effect.
    """
    if module_name not in loaded_modules:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")

    if not loaded_modules[module_name]["enabled"]:
        return JSONResponse(content={"message": f"Module '{module_name}' is already disabled."})

    # In a real system, persist this state change to a database
    loaded_modules[module_name]["enabled"] = False
    opentz_logger.info(f"Module '{module_name}' marked as disabled. Please restart the API server to deactivate.")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": f"Module '{module_name}' disabled. Please restart the server for changes to take effect."}
    )

@app.delete("/modules/{module_name}/uninstall")
async def uninstall_module_endpoint(module_name: str):
    """
    Uninstalls a module by removing its code and re-resolving dependencies.
    Requires server restart to take full effect.
    """
    if module_name not in loaded_modules:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found.")

    module_path = os.path.join(MODULES_INSTALLED_DIR, module_name)
    if not os.path.exists(module_path):
        del loaded_modules[module_name] # Clean up state if directory somehow missing
        opentz_logger.warning(f"Module directory for '{module_name}' was missing, but module was in loaded state. Cleaned up state.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Module directory already missing. State cleaned up.")

    try:
        # 1. Remove module code directory
        shutil.rmtree(module_path)
        del loaded_modules[module_name] # Remove from in-memory state

        # 2. Re-resolve and reinstall dependencies for the remaining active modules
        _re_resolve_dependencies()

        opentz_logger.info(f"Module '{module_name}' uninstalled. Python environment updated. Please restart the API server to apply changes.")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": f"Module '{module_name}' uninstalled. Python environment updated. Please restart the API server to apply changes."}
        )

    except HTTPException as e:
        raise e # Re-raise FastAPI HTTP exceptions directly
    except Exception as e:
        opentz_logger.exception(f"Error during module uninstall of '{module_name}'.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to uninstall module: {e}. Manual intervention may be required."
        )

# --- Uvicorn Run Command ---
if __name__ == "__main__":
    import uvicorn
    # IMPORTANT: The reload flag below is great for development, but for production
    # you would manage restarts via your deployment system (e.g., Docker, Kubernetes).
    uvicorn.run(app, host="0.0.0.0", port=8000)