"""
Plugin loading functionality for ChaCC API in development mode.

Uses the pure load_single_module function from module_loader.py
for consistent behavior between development and production.
"""

import os
import sys
import json
import logging
import hashlib
import time
from typing import Dict, List, Any
from fastapi import FastAPI

from src.logger import configure_logging, LogLevels
from src.constants import (
    PLUGINS_DIR, 
    DEPENDENCY_CACHE_DIR, 
    DEVELOPMENT_MODE,
    ENABLE_PLUGIN_HOT_RELOAD,
    ENABLE_PLUGIN_DEPENDENCY_RESOLUTION,
    PLUGIN_AUTO_DISCOVERY
)
from src.module_loader import load_single_module

chacc_logger = configure_logging(log_level=LogLevels.INFO)


class PluginState:
    """
    Tracks the state of loaded plugins for hot reload functionality.
    """
    def __init__(self):
        self.plugin_file_hashes: Dict[str, str] = {}
        
    def get_plugin_hash(self, plugin_path: str) -> str:
        """Calculate a hash of all Python files in a plugin directory."""
        import hashlib
        hasher = hashlib.md5()
        
        for root, dirs, files in os.walk(plugin_path):
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
    
    def should_reload(self, plugin_name: str, plugin_path: str) -> bool:
        """Check if a plugin should be reloaded based on file changes."""
        if not ENABLE_PLUGIN_HOT_RELOAD:
            return False
            
        current_hash = self.get_plugin_hash(plugin_path)
        stored_hash = self.plugin_file_hashes.get(plugin_name)
        
        if stored_hash is None or current_hash != stored_hash:
            self.plugin_file_hashes[plugin_name] = current_hash
            return True
            
        return False


# Global plugin state
_plugin_state = PluginState()


def discover_plugins() -> Dict[str, Dict]:
    """
    Discover all plugins in the plugins directory.
    """
    plugins = {}
    
    if not os.path.isdir(PLUGINS_DIR):
        chacc_logger.warning(f"Plugins directory not found: {PLUGINS_DIR}")
        return plugins
    
    for entry in os.listdir(PLUGINS_DIR):
        plugin_path = os.path.join(PLUGINS_DIR, entry)
        
        if not os.path.isdir(plugin_path) or entry.startswith('.'):
            continue
        
        # Look for module_meta.json
        meta_path = os.path.join(plugin_path, "module_meta.json")
        if not os.path.exists(meta_path):
            chacc_logger.debug(f"Skipping {entry}: no module_meta.json")
            continue
            
        try:
            with open(meta_path, 'r') as f:
                meta_data = json.load(f)
                
            plugin_name = meta_data.get('name', entry)
            
            # Find the source directory
            source_dirs = [
                e for e in os.listdir(plugin_path) 
                if os.path.isdir(os.path.join(plugin_path, e)) and not e.startswith('.')
            ]
            
            if not source_dirs:
                continue
            
            # Use the first source directory as the module path
            module_path = os.path.join(plugin_path, source_dirs[0])
            
            plugins[plugin_name] = {
                'name': plugin_name,
                'plugin_path': plugin_path,
                'module_path': module_path,
                'meta': meta_data,
            }
            
            chacc_logger.info(f"Discovered plugin: {plugin_name}")
            
        except Exception as e:
            chacc_logger.warning(f"Failed to read module_meta.json for {entry}: {e}")
    
    return plugins


async def resolve_plugin_dependencies(plugins: Dict[str, Dict], enabled_plugins: List[str]):
    """Resolve dependencies for enabled plugins."""
    if not ENABLE_PLUGIN_DEPENDENCY_RESOLUTION:
        return
        
    requirements = {}
    
    backbone_req_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
    if os.path.exists(backbone_req_path):
        with open(backbone_req_path, 'r') as f:
            requirements['backbone'] = f.read()
    
    for plugin_name, plugin_info in plugins.items():
        req_path = os.path.join(plugin_info['plugin_path'], 'requirements.txt')
        if os.path.exists(req_path):
            with open(req_path, 'r') as f:
                requirements[plugin_name] = f.read()
    
    enabled_requirements = {k: v for k, v in requirements.items() 
                          if k in enabled_plugins or k == 'backbone'}
    
    if enabled_requirements:
        try:
            from chacc import DependencyManager
            dm = DependencyManager(cache_dir=DEPENDENCY_CACHE_DIR, logger=chacc_logger)
            await dm.resolve_dependencies(enabled_requirements)
            chacc_logger.info("Plugin dependencies resolved")
        except Exception as e:
            chacc_logger.warning(f"Dependency resolution failed: {e}")


async def load_plugins(
    app: FastAPI,
    backbone_context,
    only_plugins: List[str] = None,
    exclude_plugins: List[str] = None
):
    """
    Load plugins from the plugins directory using the pure load_single_module function.
    """
    if not DEVELOPMENT_MODE and not PLUGIN_AUTO_DISCOVERY:
        return
    
    chacc_logger.info("Discovering plugins...")
    
    plugins = discover_plugins()
    if not plugins:
        chacc_logger.info("No plugins found")
        return
    
    # Filter plugins
    plugins_to_load = []
    for name in plugins:
        if only_plugins and name not in only_plugins:
            continue
        if exclude_plugins and name in exclude_plugins:
            continue
        plugins_to_load.append(name)
    
    if not plugins_to_load:
        return
    
    chacc_logger.info(f"Loading plugins: {plugins_to_load}")
    
    # Resolve dependencies
    await resolve_plugin_dependencies(plugins, plugins_to_load)
    
    # Load each plugin using pure function
    for plugin_name in plugins_to_load:
        plugin_info = plugins[plugin_name]
        
        # Check for changes
        if not _plugin_state.should_reload(plugin_name, plugin_info['module_path']):
            chacc_logger.debug(f"Plugin '{plugin_name}' unchanged")
            continue
        
        chacc_logger.info(f"Loading plugin: {plugin_name}")
        
        try:
            # Use the pure function - pass all required data
            success = load_single_module(
                module_name=plugin_name,
                module_path=plugin_info['module_path'],
                module_metadata=plugin_info['meta'],
                app=app,
                backbone_context=backbone_context
            )
            
            if success:
                chacc_logger.info(f"Plugin '{plugin_name}' loaded successfully")
            else:
                chacc_logger.warning(f"Plugin '{plugin_name}' failed to load")
                
        except Exception as e:
            chacc_logger.error(f"Error loading plugin '{plugin_name}': {e}", exc_info=True)
    
    chacc_logger.info("Plugin loading completed")


async def hot_reload_plugins(app: FastAPI, backbone_context):
    """Check for and reload changed plugins."""
    if not ENABLE_PLUGIN_HOT_RELOAD:
        return
    
    plugins = discover_plugins()
    
    for plugin_name, plugin_info in plugins.items():
        if _plugin_state.should_reload(plugin_name, plugin_info['module_path']):
            chacc_logger.info(f"Hot reloading plugin: {plugin_name}")
            
            try:
                load_single_module(
                    module_name=plugin_name,
                    module_path=plugin_info['module_path'],
                    module_metadata=plugin_info['meta'],
                    app=app,
                    backbone_context=backbone_context
                )
            except Exception as e:
                chacc_logger.error(f"Error hot reloading plugin '{plugin_name}': {e}")


def is_development_mode() -> bool:
    """Check if running in development mode."""
    return DEVELOPMENT_MODE
