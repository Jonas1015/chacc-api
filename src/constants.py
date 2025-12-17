import os
from decouple import config

MODULES_INSTALLED_DIR = "modules_installed"
MODULES_LOADED_DIR = ".modules_loaded"
MODULES_UPLOAD_DIR = ".modules_upload"
DEPENDENCY_CACHE_DIR = ".chacc_cache"
BACKBONE_REQUIREMENTS_LOCK_FILE = f"{DEPENDENCY_CACHE_DIR}/compiled_requirements.lock"
DEPENDENCY_CACHE_FILE = f"{DEPENDENCY_CACHE_DIR}/dependency_cache.json"

DATABASE_ENGINE = config("DATABASE_ENGINE", default="sqlite", cast=str)
DATABASE_NAME = config("DATABASE_NAME", default="opentzdb")
DATABASE_USER = config("DATABASE_USER", default="opentz")
DATABASE_PASSWORD = config("DATABASE_PASSWORD", default="welcome2opentz")
DATABASE_HOST = config("DATABASE_HOST", default="localhost")
DATABASE_PORT = config("DATABASE_PORT", default="5432", cast=int)

LOGGER_NAME = "chacc-api"

# The format strings are modified to wrap only `%(levelname)s` with color tags.
# This ensures that only the level name is colored, and the rest remains in the
# default terminal color.
LOG_FORMAT_DEFAULT = "%(log_color)s%(levelname)s%(reset)s:     %(asctime)s - %(name)s - %(message)s"
LOG_FORMAT_DEBUG = "%(log_color)s%(levelname)s%(reset)s %(asctime)s - %(name)s - %(message)s"


os.makedirs(MODULES_INSTALLED_DIR, exist_ok=True)
os.makedirs(MODULES_LOADED_DIR, exist_ok=True)
os.makedirs(MODULES_UPLOAD_DIR, exist_ok=True)
os.makedirs(DEPENDENCY_CACHE_DIR, exist_ok=True)