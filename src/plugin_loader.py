"""
Plugin loading functionality for ChaCC API.

Supports both:
- Development mode: Load from plugins/ directory with hot reload
- Production mode: Load from .modules_loaded with optional hot reload
"""

import os
import json
from typing import Dict, List
from fastapi import FastAPI

from src.logger import configure_logging, LogLevels
from src.constants import (
    PLUGINS_DIR, 
    MODULES_LOADED_DIR,
    DEPENDENCY_CACHE_DIR, 
    DEVELOPMENT_MODE,
    ENABLE_PLUGIN_HOT_RELOAD,
    ENABLE_PLUGIN_DEPENDENCY_RESOLUTION,
    PLUGIN_AUTO_DISCOVERY
)
from src.module_loader import load_single_module

chacc_logger = configure_logging(log_level=LogLevels.INFO)


class ModuleState:
    """
    Tracks the state of loaded modules for hot reload functionality.
    """
    def __init__(self):
        self.file_hashes: Dict[str, str] = {}
        
    def get_file_hash(self, module_path: str) -> str:
        """Calculate a hash of all Python files in a module directory."""
        import hashlib
        hasher = hashlib.md5()
        
        for root, dirs, files in os.walk(module_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            for file in sorted(files):
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'rb') as f:
                            hasher.update(f.read())
                    except Exception:
                        pass
        
        return hasher.hexdigest()
    
    def should_reload(self, module_name: str, module_path: str) -> bool:
        """Check if a module should be reloaded based on file changes."""
        if not ENABLE_PLUGIN_HOT_RELOAD:
            return False
            
        if not os.path.exists(module_path):
            return False
            
        current_hash = self.get_file_hash(module_path)
        stored_hash = self.file_hashes.get(module_name)
        
        if stored_hash is None or current_hash != stored_hash:
            self.file_hashes[module_name] = current_hash
            return True
            
        return False
    
    def track(self, module_name: str, module_path: str):
        """Track a module for change detection."""
        self.file_hashes[module_name] = self.get_file_hash(module_path)


_module_state = ModuleState()


def discover_modules_from_directory(directory: str) -> Dict[str, Dict]:
    """
    Discover all modules in a directory.
    
    Args:
        directory: Path to the modules directory (e.g., plugins/ or .modules_loaded/)
        
    Returns:
        Dict mapping module_name -> module_info
    """
    modules = {}
    
    if not os.path.isdir(directory):
        chacc_logger.warning(f"Modules directory not found: {directory}")
        return modules
    
    for entry in os.listdir(directory):
        module_path = os.path.join(directory, entry)
        
        if not os.path.isdir(module_path) or entry.startswith('.'):
            continue
        
        meta_path = os.path.join(module_path, "module_meta.json")
        if not os.path.exists(meta_path):
            for subentry in os.listdir(module_path):
                subpath = os.path.join(module_path, subentry)
                if os.path.isdir(subpath) and not subentry.startswith('.'):
                    meta_path = os.path.join(subpath, "module_meta.json")
                    if os.path.exists(meta_path):
                        module_path = subpath
                        break
        
        if not os.path.exists(meta_path):
            chacc_logger.debug(f"Skipping {entry}: no module_meta.json")
            continue
            
        try:
            with open(meta_path, 'r') as f:
                meta_data = json.load(f)
                
            module_name = meta_data.get('name', entry)
            
            modules[module_name] = {
                'name': module_name,
                'module_path': module_path,
                'meta': meta_data,
            }
            
            chacc_logger.debug(f"Discovered module: {module_name}")
            
        except Exception as e:
            chacc_logger.warning(f"Failed to read module_meta.json for {entry}: {e}")
    
    return modules


def discover_plugins() -> Dict[str, Dict]:
    """Discover plugins from plugins directory."""
    return discover_modules_from_directory(PLUGINS_DIR)


def discover_installed_modules() -> Dict[str, Dict]:
    """Discover installed modules from .modules_loaded directory."""
    return discover_modules_from_directory(MODULES_LOADED_DIR)


async def resolve_dependencies(modules: Dict[str, Dict], enabled_modules: List[str]):
    """Resolve dependencies for enabled modules."""
    if not ENABLE_PLUGIN_DEPENDENCY_RESOLUTION:
        return
        
    requirements = {}
    
    backbone_req_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
    if os.path.exists(backbone_req_path):
        with open(backbone_req_path, 'r') as f:
            requirements['backbone'] = f.read()
    
    for module_name, module_info in modules.items():
        module_path = module_info['module_path']
        module_root = os.path.dirname(module_path)
        req_path = os.path.join(module_root, 'requirements.txt')
        if os.path.exists(req_path):
            with open(req_path, 'r') as f:
                requirements[module_name] = f.read()
    
    enabled_requirements = {k: v for k, v in requirements.items() 
                          if k in enabled_modules or k == 'backbone'}
    
    if enabled_requirements:
        try:
            from chacc import DependencyManager
            dm = DependencyManager(cache_dir=DEPENDENCY_CACHE_DIR, logger=chacc_logger)
            await dm.resolve_dependencies(enabled_requirements)
            chacc_logger.info("Module dependencies resolved")
        except Exception as e:
            chacc_logger.warning(f"Dependency resolution failed: {e}")


async def load_plugins(
    app: FastAPI,
    backbone_context,
    only_modules: List[str] = None,
    exclude_modules: List[str] = None
):
    """
    Load plugins from the plugins directory.
    
    Called when DEVELOPMENT_MODE=True
    """
    if not DEVELOPMENT_MODE and not PLUGIN_AUTO_DISCOVERY:
        return
    
    chacc_logger.info("Discovering plugins from plugins directory...")
    
    modules = discover_plugins()
    if not modules:
        chacc_logger.info("No plugins found")
        return
    
    await _load_modules(
        app=app,
        backbone_context=backbone_context,
        modules=modules,
        only_modules=only_modules,
        exclude_modules=exclude_modules,
        source="plugins"
    )


async def load_installed_modules(
    app: FastAPI,
    backbone_context,
    only_modules: List[str] = None,
    exclude_modules: List[str] = None
):
    f"""
    Load installed modules from {MODULES_LOADED_DIR} directory.
    
    Called when DEVELOPMENT_MODE=False (production)
    """
    chacc_logger.info(f"Discovering installed modules from {MODULES_LOADED_DIR} directory...")
    
    modules = discover_installed_modules()
    if not modules:
        chacc_logger.info("No installed modules found")
        return
    
    await _load_modules(
        app=app,
        backbone_context=backbone_context,
        modules=modules,
        only_modules=only_modules,
        exclude_modules=exclude_modules,
        source=MODULES_LOADED_DIR
    )


async def _load_modules(
    app: FastAPI,
    backbone_context,
    modules: Dict[str, Dict],
    only_modules: List[str],
    exclude_modules: List[str],
    source: str
):
    """Internal function to load modules."""
    modules_to_load = []
    for name in modules:
        if only_modules and name not in only_modules:
            continue
        if exclude_modules and name in exclude_modules:
            continue
        modules_to_load.append(name)
    
    if not modules_to_load:
        return
    
    chacc_logger.info(f"Loading {len(modules_to_load)} modules from {source}: {modules_to_load}")
    
    await resolve_dependencies(modules, modules_to_load)
    
    for module_name in modules_to_load:
        module_info = modules[module_name]
        
        if not _module_state.should_reload(module_name, module_info['module_path']):
            chacc_logger.debug(f"Module '{module_name}' unchanged, skipping")
            continue
        
        chacc_logger.info(f"Loading module: {module_name} from {source}")
        
        try:
            success = await load_single_module(
                module_name=module_name,
                module_path=module_info['module_path'],
                module_metadata=module_info['meta'],
                app=app,
                backbone_context=backbone_context
            )
            
            if success:
                _module_state.track(module_name, module_info['module_path'])
                chacc_logger.info(f"Module '{module_name}' loaded successfully")
            else:
                chacc_logger.warning(f"Module '{module_name}' failed to load")
                
        except Exception as e:
            chacc_logger.error(f"Error loading module '{module_name}': {e}", exc_info=True)
    
    chacc_logger.info(f"Module loading from {source} completed")


async def hot_reload_modules(
    app: FastAPI,
    backbone_context,
    source: str = None
):
    """
    Check for and reload changed modules.
    
    Args:
        app: FastAPI application
        backbone_context: Backbone context
        source: Which source to check - "plugins", "modules_loaded", or None for both
    """
    if not ENABLE_PLUGIN_HOT_RELOAD:
        return
    
    if source == PLUGINS_DIR or source is None:
        if DEVELOPMENT_MODE or PLUGIN_AUTO_DISCOVERY:
            plugins = discover_plugins()
            for module_name, module_info in plugins.items():
                if _module_state.should_reload(module_name, module_info['module_path']):
                    chacc_logger.info(f"Hot reloading plugin: {module_name}")
                    try:
                        await load_single_module(
                            module_name=module_name,
                            module_path=module_info['module_path'],
                            module_metadata=module_info['meta'],
                            app=app,
                            backbone_context=backbone_context
                        )
                    except Exception as e:
                        chacc_logger.error(f"Error hot reloading plugin '{module_name}': {e}")
    
    if source == MODULES_LOADED_DIR or source is None:
        installed = discover_installed_modules()
        for module_name, module_info in installed.items():
            if _module_state.should_reload(module_name, module_info['module_path']):
                chacc_logger.info(f"Hot reloading module: {module_name}")
                try:
                    await load_single_module(
                        module_name=module_name,
                        module_path=module_info['module_path'],
                        module_metadata=module_info['meta'],
                        app=app,
                        backbone_context=backbone_context
                    )
                except Exception as e:
                    chacc_logger.error(f"Error hot reloading module '{module_name}': {e}")
