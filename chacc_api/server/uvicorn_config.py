"""
Uvicorn configuration for development mode with auto-reload.
Reads host, port, and debug settings from environment variables.
"""

import os

from chacc_api.utils import (
    BACKBONE_REQUIREMENTS_LOCK_FILE,
    BASE_DIR,
    DEPENDENCY_CACHE_DIR,
    DEPENDENCY_CACHE_FILE,
    DEVELOPMENT_MODE,
    ENABLE_PLUGIN_HOT_RELOAD,
    MODULES_INSTALLED_DIR,
    MODULES_LOADED_DIR,
    MODULES_UPLOAD_DIR,
    PLUGINS_DIR,
)


def get_relative_path(abs_path):
    """Convert absolute path to relative path from base directory."""
    if abs_path.startswith(BASE_DIR):
        return os.path.relpath(abs_path, BASE_DIR)
    return abs_path


# Read host and port from environment variables (set by CLI --host / --port)
_host = os.environ.get("CHACC_HOST", "0.0.0.0")
_port = int(os.environ.get("CHACC_PORT", "8085"))

config = {
    "app": "main:app",
    "host": _host,
    "port": _port,
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
