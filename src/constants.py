import os
from decouple import config

# Always use current working directory for all paths
# This ensures the package works correctly whether installed regularly or editable
BASE_DIR = os.getcwd()

MODULES_INSTALLED_DIR = os.path.join(
    BASE_DIR, config("MODULES_INSTALLED_DIR", default="modules_installed", cast=str)
)
MODULES_LOADED_DIR = os.path.join(
    BASE_DIR, config("MODULES_LOADED_DIR", default=".modules_loaded", cast=str)
)
MODULES_UPLOAD_DIR = os.path.join(
    BASE_DIR, config("MODULES_UPLOAD_DIR", default=".modules_upload", cast=str)
)
PLUGINS_DIR = os.path.join(BASE_DIR, config("PLUGINS_DIR", default="plugins", cast=str))
DEPENDENCY_CACHE_DIR = os.path.join(
    BASE_DIR, config("DEPENDENCY_CACHE_DIR", default=".chacc_cache", cast=str)
)
BACKBONE_REQUIREMENTS_LOCK_FILE = f"{DEPENDENCY_CACHE_DIR}/compiled_requirements.lock"
DEPENDENCY_CACHE_FILE = f"{DEPENDENCY_CACHE_DIR}/dependency_cache.json"

# Migration settings
MIGRATION_MODE = config("MIGRATION_MODE", default="auto", cast=str)
MIGRATION_BACKUP = config("MIGRATION_BACKUP", default=False, cast=bool)
MIGRATION_BACKUP_DIR = os.path.join(
    BASE_DIR, config("MIGRATION_BACKUP_DIR", default="backups", cast=str)
)
MIGRATION_AUTO_DROP = config("MIGRATION_AUTO_DROP", default=False, cast=bool)

# Development mode detection
DEVELOPMENT_MODE = config("DEVELOPMENT_MODE", default=False, cast=bool)
ENABLE_PLUGIN_HOT_RELOAD = config("ENABLE_PLUGIN_HOT_RELOAD", default=True, cast=bool)
ENABLE_PLUGIN_DEPENDENCY_RESOLUTION = config(
    "ENABLE_PLUGIN_DEPENDENCY_RESOLUTION", default=True, cast=bool
)
PLUGIN_AUTO_DISCOVERY = config("PLUGIN_AUTO_DISCOVERY", default=True, cast=bool)

# Redis Configuration
REDIS_ENABLED = config("REDIS_ENABLED", default=True, cast=bool)
REDIS_HOST = config("REDIS_HOST", default="localhost", cast=str)
REDIS_PORT = config("REDIS_PORT", default=6379, cast=int)
REDIS_DB = config("REDIS_DB", default=0, cast=int)
REDIS_PASSWORD = config("REDIS_PASSWORD", default=None, cast=str)

DATABASE_ENGINE = config("DATABASE_ENGINE", default="sqlite", cast=str)
DATABASE_NAME = config("DATABASE_NAME", default="chaccapidb")
DATABASE_USER = config("DATABASE_USER", default="chacc")
DATABASE_PASSWORD = config("DATABASE_PASSWORD", default="")
DATABASE_HOST = config("DATABASE_HOST", default="localhost")
DATABASE_PORT = config("DATABASE_PORT", default="5432", cast=int)

if DATABASE_ENGINE == "postgresql":
    DATABASE_URL = f"postgresql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
else:
    DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'chaccapi.db')}"

SQLITE_DB_PATH = os.path.join(BASE_DIR, "chaccapi.db")

LOGGER_NAME = "CHACC-API"

# The format strings are modified to wrap only `%(levelname)s` with color tags.
# This ensures that only the level name is colored, and the rest remains in the
# default terminal color.
LOG_FORMAT_DEFAULT = "%(log_color)s%(levelname)s%(reset)s:     %(asctime)s - %(name)s - %(message)s"
LOG_FORMAT_DEBUG = "%(log_color)s%(levelname)s%(reset)s %(asctime)s - %(name)s - %(message)s"


os.makedirs(MODULES_INSTALLED_DIR, exist_ok=True)
os.makedirs(MODULES_LOADED_DIR, exist_ok=True)
os.makedirs(MODULES_UPLOAD_DIR, exist_ok=True)
os.makedirs(DEPENDENCY_CACHE_DIR, exist_ok=True)
os.makedirs(PLUGINS_DIR, exist_ok=True)
os.makedirs(MIGRATION_BACKUP_DIR, exist_ok=True)
