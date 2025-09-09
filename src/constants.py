import os

MODULES_INSTALLED_DIR = "modules_installed"
MODULES_LOADED_DIR = ".modules_loaded"
MODULES_UPLOAD_DIR = ".modules_upload"
BACKBONE_REQUIREMENTS_LOCK_FILE = f"{MODULES_LOADED_DIR}/compiled_requirements.lock"

LOGGER_NAME = "open-tz-backbone"
# The format strings are modified to wrap only `%(levelname)s` with color tags.
# This ensures that only the level name is colored, and the rest remains in the
# default terminal color.

LOG_FORMAT_DEFAULT = "%(log_color)s%(levelname)s%(reset)s:     %(asctime)s - %(name)s - %(message)s"
LOG_FORMAT_DEBUG = "%(log_color)s%(levelname)s%(reset)s %(asctime)s:%(message)s:%(pathname)s:%(funcName)s:%(lineno)d"


os.makedirs(MODULES_INSTALLED_DIR, exist_ok=True)
os.makedirs(MODULES_LOADED_DIR, exist_ok=True)
os.makedirs(MODULES_UPLOAD_DIR, exist_ok=True)