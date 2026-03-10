"""
Uvicorn configuration to prevent auto-reloader loops.
"""
import os
from decouple import config as env_config
from src.constants import PLUGINS_DIR, MODULES_LOADED_DIR, MODULES_UPLOAD_DIR, MODULES_INSTALLED_DIR, DEVELOPMENT_MODE, DEPENDENCY_CACHE_DIR, BACKBONE_REQUIREMENTS_LOCK_FILE, DEPENDENCY_CACHE_FILE, ENABLE_PLUGIN_HOT_RELOAD

config = {
    "app": "main:app",
    "host": "0.0.0.0",
    "port": 8080,
    "reload": True,
    "reload_dirs": ["src", "main.py"],
    "reload_excludes": [
        f"{MODULES_LOADED_DIR}/",
        f"{MODULES_UPLOAD_DIR}/",
        f"{DEPENDENCY_CACHE_DIR}/",
        BACKBONE_REQUIREMENTS_LOCK_FILE,
        f"{MODULES_INSTALLED_DIR}/",
        DEPENDENCY_CACHE_FILE,
        "*.chacc",
        "__pycache__",
        ".pytest_cache",
        "tests/",
        "*.pyc",
        "*.db",
        "*.log",
        ".env",
        f"{PLUGINS_DIR}/" if "/" in PLUGINS_DIR else PLUGINS_DIR if not DEVELOPMENT_MODE and ENABLE_PLUGIN_HOT_RELOAD else "",
    ]
}

config_no_reload = {
    "app": "main:app",
    "host": "0.0.0.0",
    "port": 8080,
    "reload": False
}

if __name__ == "__main__":
    import uvicorn
    if os.getenv("NO_RELOAD", "").lower() in ("true", "1", "yes"):
        print("Starting server WITHOUT auto-reload to prevent loops...")
        uvicorn.run(**config_no_reload)
    else:
        print("Starting server with selective auto-reload...")
        uvicorn.run(**config)