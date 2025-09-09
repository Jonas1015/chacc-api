import os

MODULES_INSTALLED_DIR = "modules_installed"
MODULES_LOADED_DIR = ".modules_loaded"
MODULES_UPLOAD_DIR = ".modules_upload"
BACKBONE_REQUIREMENTS_LOCK_FILE = f"{MODULES_LOADED_DIR}/compiled_requirements.lock"

os.makedirs(MODULES_INSTALLED_DIR, exist_ok=True)
os.makedirs(MODULES_LOADED_DIR, exist_ok=True)
os.makedirs(MODULES_UPLOAD_DIR, exist_ok=True)