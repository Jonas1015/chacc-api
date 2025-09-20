"""
Dependency Manager for AdCore API Platform

This module provides intelligent, incremental dependency resolution and caching
for Python packages in modular applications.

Features:
- Incremental dependency resolution (only resolve changed modules)
- Intelligent caching with module-level granularity
- Smart package installation (skip already installed)
- Automatic cache invalidation
- Conflict resolution between modules

Author: AdCore API Platform
"""

import os
import json
import hashlib
import subprocess
from typing import Dict, Set

from src.logger import LogLevels, configure_logging

from .constants import DEPENDENCY_CACHE_FILE, MODULES_LOADED_DIR, MODULES_UPLOAD_DIR
from .database import get_db, ModuleRecord

adcore_logger = configure_logging(log_level=LogLevels.INFO)


class DependencyManager:
    """
    Manages Python package dependencies for modular applications.

    Provides incremental dependency resolution, caching, and intelligent
    package installation to optimize performance in development and production.
    """

    def __init__(self):
        """Initialize the dependency manager."""
        self.cache_file = DEPENDENCY_CACHE_FILE
        self.modules_dir = MODULES_LOADED_DIR
        self.upload_dir = MODULES_UPLOAD_DIR

    def calculate_module_hash(self, module_name: str, requirements_content: str) -> str:
        """Calculate hash of a specific module's requirements."""
        content = f"{module_name}:{requirements_content}"
        return hashlib.sha256(content.encode()).hexdigest()

    def calculate_combined_requirements_hash(self, module_hashes: Dict[str, str]) -> str:
        """Calculate hash of all module requirement hashes combined."""
        sorted_hashes = sorted(module_hashes.items())
        combined = "|".join(f"{name}:{hash}" for name, hash in sorted_hashes)
        return hashlib.sha256(combined.encode()).hexdigest()

    def load_cache(self) -> Dict:
        """Load dependency cache from file."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    cache = json.load(f)
                    if 'module_caches' not in cache:
                        cache['module_caches'] = {}
                    if 'combined_hash' not in cache:
                        cache['combined_hash'] = None
                    return cache
            except (json.JSONDecodeError, IOError) as e:
                adcore_logger.warning(f"Failed to load dependency cache: {e}")
        return {
            'module_caches': {},
            'backbone_hash': None,
            'combined_hash': None,
            'resolved_packages': {},
            'last_updated': None
        }

    def save_cache(self, cache_data: Dict):
        """Save dependency cache to file."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except IOError as e:
            adcore_logger.error(f"Failed to save dependency cache: {e}")

    def get_installed_packages(self) -> Set[str]:
        """Get set of currently installed packages."""
        try:
            result = subprocess.run([
                'python', '-m', 'pip', 'list', '--format=freeze'
            ], capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                packages = set()
                for line in result.stdout.strip().split('\n'):
                    if '==' in line:
                        package_name = line.split('==')[0].lower()
                        packages.add(package_name)
                return packages
            else:
                adcore_logger.warning(f"Failed to get installed packages: {result.stderr}")
                return set()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            adcore_logger.warning(f"Error getting installed packages: {e}")
            return set()

    def resolve_module_dependencies(self, module_name: str, requirements_content: str) -> Dict[str, str]:
        """Resolve dependencies for a specific module."""
        adcore_logger.info(f"Resolving dependencies for module: {module_name}")

        temp_req_file = os.path.join(os.path.dirname(self.cache_file), f"temp_{module_name}_requirements.txt")

        try:
            with open(temp_req_file, "w") as f:
                f.write(requirements_content)

            result = subprocess.run([
                'python', '-m', 'piptools', 'compile',
                '--output-file', f"{temp_req_file}.lock",
                '--allow-unsafe',
                temp_req_file
            ], capture_output=True, text=True)

            if result.returncode != 0:
                adcore_logger.error(f"Failed to resolve dependencies for {module_name}: {result.stderr}")
                return {}

            resolved_packages = {}
            lock_file = f"{temp_req_file}.lock"
            if os.path.exists(lock_file):
                with open(lock_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '==' in line:
                            parts = line.split('==')
                            if len(parts) >= 2:
                                package_name = parts[0]
                                version = parts[1]
                                resolved_packages[package_name] = f"=={version}"

            adcore_logger.info(f"Resolved {len(resolved_packages)} packages for {module_name}")
            return resolved_packages

        except Exception as e:
            adcore_logger.error(f"Error resolving dependencies for {module_name}: {e}")
            return {}
        finally:
            for file in [temp_req_file, f"{temp_req_file}.lock"]:
                if os.path.exists(file):
                    os.remove(file)

    def merge_resolved_packages(self, *package_dicts: Dict[str, str]) -> Dict[str, str]:
        """Merge multiple resolved package dictionaries, resolving conflicts."""
        merged = {}

        for package_dict in package_dicts:
            for package_name, version_spec in package_dict.items():
                if package_name in merged:
                    existing_version = merged[package_name]
                    if version_spec != existing_version:
                        adcore_logger.warning(f"Version conflict for {package_name}: {existing_version} vs {version_spec}, using {version_spec}")
                merged[package_name] = version_spec

        return merged

    def install_missing_packages(self, resolved_packages: Dict[str, str], installed_packages: Set[str]):
        """Install only packages that are not already installed."""
        packages_to_install = []

        for package_name, version_spec in resolved_packages.items():
            package_name_lower = package_name.lower()
            if package_name_lower not in installed_packages:
                packages_to_install.append(f"{package_name}{version_spec}")
            else:
                adcore_logger.debug(f"Package {package_name} already installed, skipping")

        if packages_to_install:
            adcore_logger.info(f"Installing {len(packages_to_install)} missing packages...")
            try:
                batch_size = 50
                for i in range(0, len(packages_to_install), batch_size):
                    batch = packages_to_install[i:i + batch_size]
                    result = subprocess.run([
                        'python', '-m', 'pip', 'install', '--quiet'
                    ] + batch, capture_output=True, text=True, timeout=300)

                    if result.returncode != 0:
                        adcore_logger.error(f"Failed to install package batch: {result.stderr}")
                        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)

                adcore_logger.info("Package installation completed successfully")
            except subprocess.TimeoutExpired:
                adcore_logger.error("Package installation timed out")
                raise
        else:
            adcore_logger.info("All required packages are already installed")

    def invalidate_cache(self):
        """Invalidate the entire dependency cache."""
        try:
            cache_data = {
                'module_caches': {},
                'backbone_hash': None,
                'combined_hash': None,
                'resolved_packages': {},
                'last_updated': None
            }
            self.save_cache(cache_data)
            adcore_logger.info("Dependency cache invalidated")
        except Exception as e:
            adcore_logger.warning(f"Failed to invalidate dependency cache: {e}")
            if os.path.exists(self.cache_file):
                try:
                    os.remove(self.cache_file)
                    adcore_logger.info("Dependency cache file removed")
                except IOError as e2:
                    adcore_logger.error(f"Failed to remove dependency cache file: {e2}")

    def invalidate_module_cache(self, module_name: str):
        """Invalidate cache for a specific module."""
        try:
            cache = self.load_cache()
            if module_name in cache.get('module_caches', {}):
                del cache['module_caches'][module_name]
                cache['combined_hash'] = None
                self.save_cache(cache)
                adcore_logger.info(f"Cache invalidated for module: {module_name}")
        except Exception as e:
            adcore_logger.warning(f"Failed to invalidate cache for module {module_name}: {e}")

    async def resolve_dependencies(self):
        """
        Perform incremental dependency resolution for all enabled modules.

        This method:
        1. Checks which modules have changed requirements
        2. Only resolves dependencies for changed modules
        3. Merges results with cached dependencies
        4. Installs only missing packages
        """
        adcore_logger.info("Starting incremental dependency resolution...")

        db = await anext(get_db())
        try:
            installed_modules_records = db.query(ModuleRecord).filter_by(is_enabled=True).all()

            cache = self.load_cache()
            module_caches = cache.get('module_caches', {})

            current_module_hashes = {}
            modules_needing_resolution = []
            backbone_changed = False

            core_req_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'requirements.txt')
            if os.path.exists(core_req_path):
                with open(core_req_path, 'r') as f:
                    backbone_reqs = f.read()
                backbone_hash = self.calculate_module_hash('backbone', backbone_reqs)
                if backbone_hash != cache.get('backbone_hash'):
                    backbone_changed = True
                    adcore_logger.info("Backbone requirements have changed")
            else:
                backbone_hash = None

            for record in installed_modules_records:
                module_name = record.name
                module_meta = record.meta_data if record.meta_data else {}

                dependencies_file_name = module_meta.get("dependencies_file", "requirements.txt")
                module_req_path = os.path.abspath(os.path.join(self.modules_dir, module_name, dependencies_file_name))

                if os.path.exists(module_req_path):
                    with open(module_req_path, 'r') as f:
                        module_reqs = f.read()

                    module_hash = self.calculate_module_hash(module_name, module_reqs)
                    current_module_hashes[module_name] = module_hash

                    if module_name not in module_caches or module_caches[module_name].get('hash') != module_hash:
                        modules_needing_resolution.append((module_name, module_reqs))
                        adcore_logger.info(f"Module '{module_name}' requirements have changed")
                else:
                    adcore_logger.warning(f"Module '{module_name}' has no '{dependencies_file_name}' file found.")

            if not backbone_changed and not modules_needing_resolution:
                adcore_logger.info("Using cached dependency resolution (no changes detected)")
                cached_packages = cache.get('resolved_packages', {})
                if cached_packages:
                    installed_packages = self.get_installed_packages()
                    self.install_missing_packages(cached_packages, installed_packages)
                else:
                    adcore_logger.warning("Cache is empty, performing full resolution")
                    backbone_changed = True
                    modules_needing_resolution = [(record.name, "") for record in installed_modules_records]
            else:
                adcore_logger.info(f"Resolving dependencies for {len(modules_needing_resolution)} changed modules")

                resolved_packages = {}
                if backbone_changed and backbone_reqs:
                    backbone_packages = self.resolve_module_dependencies('backbone', backbone_reqs)
                    resolved_packages.update(backbone_packages)

                for module_name, module_reqs in modules_needing_resolution:
                    if module_reqs:
                        module_packages = self.resolve_module_dependencies(module_name, module_reqs)
                        resolved_packages.update(module_packages)

                    module_caches[module_name] = {
                        'hash': current_module_hashes.get(module_name),
                        'packages': module_packages if module_reqs else {},
                        'last_updated': str(os.path.getmtime(os.path.join(self.modules_dir, module_name))) if os.path.exists(os.path.join(self.modules_dir, module_name)) else None
                    }

                cached_packages = {}
                for module_name, module_cache in module_caches.items():
                    if module_name not in [m[0] for m in modules_needing_resolution]:
                        cached_packages.update(module_cache.get('packages', {}))

                all_resolved_packages = self.merge_resolved_packages(cached_packages, resolved_packages)

                installed_packages = self.get_installed_packages()
                self.install_missing_packages(all_resolved_packages, installed_packages)

                combined_hash = self.calculate_combined_requirements_hash(current_module_hashes)
                cache_data = {
                    'module_caches': module_caches,
                    'backbone_hash': backbone_hash,
                    'combined_hash': combined_hash,
                    'resolved_packages': all_resolved_packages,
                    'last_updated': str(os.path.getmtime(self.modules_dir)) if os.path.exists(self.modules_dir) else None
                }
                self.save_cache(cache_data)
                adcore_logger.info("Dependency cache updated with incremental changes")

            adcore_logger.info("Incremental dependency resolution completed successfully")

        except Exception as e:
            adcore_logger.error(f"Error during dependency resolution: {e}", exc_info=True)
            raise
        finally:
            db.close()


dependency_manager = DependencyManager()


def calculate_module_hash(module_name: str, requirements_content: str) -> str:
    """Calculate hash of a specific module's requirements."""
    return dependency_manager.calculate_module_hash(module_name, requirements_content)


def calculate_combined_requirements_hash(module_hashes: Dict[str, str]) -> str:
    """Calculate hash of all module requirement hashes combined."""
    return dependency_manager.calculate_combined_requirements_hash(module_hashes)


def load_dependency_cache() -> Dict:
    """Load dependency cache from file."""
    return dependency_manager.load_cache()


def save_dependency_cache(cache_data: Dict):
    """Save dependency cache to file."""
    dependency_manager.save_cache(cache_data)


def get_installed_packages() -> Set[str]:
    """Get set of currently installed packages."""
    return dependency_manager.get_installed_packages()


def resolve_module_dependencies(module_name: str, requirements_content: str) -> Dict[str, str]:
    """Resolve dependencies for a specific module."""
    return dependency_manager.resolve_module_dependencies(module_name, requirements_content)


def merge_resolved_packages(*package_dicts: Dict[str, str]) -> Dict[str, str]:
    """Merge multiple resolved package dictionaries, resolving conflicts."""
    return dependency_manager.merge_resolved_packages(*package_dicts)


def install_missing_packages(resolved_packages: Dict[str, str], installed_packages: Set[str]):
    """Install only packages that are not already installed."""
    dependency_manager.install_missing_packages(resolved_packages, installed_packages)


def invalidate_dependency_cache():
    """Invalidate the dependency cache."""
    dependency_manager.invalidate_cache()


def invalidate_module_cache(module_name: str):
    """Invalidate cache for a specific module."""
    dependency_manager.invalidate_module_cache(module_name)


async def re_resolve_dependencies():
    """Re-resolve and reinstall all dependencies (backward compatibility)."""
    await dependency_manager.resolve_dependencies()