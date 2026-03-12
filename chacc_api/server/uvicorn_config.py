"""
Uvicorn configuration to prevent auto-reloader loops.
"""

import os
from decouple import config as env_config
from chacc_api.utils import (
    PLUGINS_DIR,
    MODULES_LOADED_DIR,
    MODULES_UPLOAD_DIR,
    MODULES_INSTALLED_DIR,
    DEVELOPMENT_MODE,
    DEPENDENCY_CACHE_DIR,
    BACKBONE_REQUIREMENTS_LOCK_FILE,
    DEPENDENCY_CACHE_FILE,
    ENABLE_PLUGIN_HOT_RELOAD,
    BASE_DIR,
)


# Get relative paths for uvicorn (it needs paths relative to cwd)
def get_relative_path(abs_path):
    """Convert absolute path to relative path from base directory."""
    if abs_path.startswith(BASE_DIR):
        return os.path.relpath(abs_path, BASE_DIR)
    return abs_path


config = {
    "app": "main:app",
    "host": "0.0.0.0",
    "port": 8080,
    "reload": True,
    "reload_dirs": ["src", "main.py"],
    "reload_excludes": [
        f"{get_relative_path(MODULES_LOADED_DIR)}/",
        f"{get_relative_path(MODULES_UPLOAD_DIR)}/",
        f"{get_relative_path(DEPENDENCY_CACHE_DIR)}/",
        get_relative_path(BACKBONE_REQUIREMENTS_LOCK_FILE),
        f"{get_relative_path(MODULES_INSTALLED_DIR)}/",
        get_relative_path(DEPENDENCY_CACHE_FILE),
        "*.chacc",
        "__pycache__",
        ".pytest_cache",
        "tests/",
        "*.pyc",
        "*.db",
        "*.log",
        ".env",
        (
            f"{get_relative_path(PLUGINS_DIR)}/"
            if "/" in get_relative_path(PLUGINS_DIR)
            else (
                get_relative_path(PLUGINS_DIR)
                if not DEVELOPMENT_MODE and ENABLE_PLUGIN_HOT_RELOAD
                else ""
            )
        ),
    ],
}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(**config)
