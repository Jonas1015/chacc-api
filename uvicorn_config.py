"""
Uvicorn configuration to prevent auto-reloader loops.
"""
import os

config = {
    "app": "main:app",
    "host": "0.0.0.0",
    "port": 8080,
    "reload": True,
    "reload_dirs": ["src", "main.py"],
    "reload_excludes": [
        ".modules_loaded",
        ".modules_upload",
        ".chacc_cache",
        "modules_installed",
        "*.chacc",
        "__pycache__",
        ".pytest_cache",
        "tests/",
        "*.pyc",
        "*.db",
        "*.log",
        ".env",
        "plugins/"
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