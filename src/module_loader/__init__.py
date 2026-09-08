"""Module loader package for ChaCC API.

This package provides modular loading, discovery, and management of ChaCC modules.
"""

from .archive import (
    collect_module_requirements,
    extract_module_names_from_chacc_files,
    get_chacc_filepath,
    process_module_archives,
    unzip_modules,
)
from .discovery import discover_and_import_models
from .loader import load_modules, load_single_module
from .metadata import sync_database_with_filesystem
from .testing import run_module_tests

__all__ = [
    "collect_module_requirements",
    "discover_and_import_models",
    "extract_module_names_from_chacc_files",
    "get_chacc_filepath",
    "load_modules",
    "load_single_module",
    "process_module_archives",
    "run_module_tests",
    "sync_database_with_filesystem",
    "unzip_modules",
]
