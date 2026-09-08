"""Model discovery for ChaCC API modules.

This module handles dynamic imports of all .py files within a module
directory so that ChaCCBaseModel subclasses are automatically registered
in SQLAlchemy metadata used by the migration system.
"""

import ast
import graphlib
import importlib
import importlib.util
import logging
import os
import sys
from collections import defaultdict


def _dotted_name(prefix: str, rel_dir: str, file_stem: str) -> str:
    """Build the dotted module name for a file."""
    sd = "" if rel_dir in ("", ".") else rel_dir.replace(os.sep, ".")
    return f"{prefix}.{sd}.{file_stem}" if sd else f"{prefix}.{file_stem}"


def _enclosing(prefix: str, rel_dir: str) -> str:
    """Return the dotted name of the package owning a file in *rel_dir*."""
    parts = [] if rel_dir in ("", ".") else rel_dir.replace(os.sep, ".").split(".")
    return ".".join([prefix] + parts) if parts else prefix


def _is_in_scope(name: str, module_prefix: str) -> bool:
    """Check whether a dotted name belongs to the module prefix being discovered."""
    return name == module_prefix or name.startswith(module_prefix + ".")


def _parse_imports(file_path: str, module_prefix: str, enclosing: str) -> set[str]:
    """Parse a file and return the set of imported modules that are within our scope."""
    try:
        with open(file_path, "r") as f:
            tree = ast.parse(f.read(), filename=file_path)
    except (OSError, SyntaxError, ValueError):
        return set()

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_in_scope(alias.name, module_prefix):
                    imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            if node.level == 0 and node.module and _is_in_scope(node.module, module_prefix):
                imported.add(node.module)
            elif node.level > 0:
                parts = enclosing.split(".")
                base = ".".join(parts[: -node.level]) if node.level <= len(parts) else ""
                if node.module:
                    target = f"{base}.{node.module}" if base else node.module
                    if _is_in_scope(target, module_prefix):
                        imported.add(target)
                else:
                    for alias in node.names:
                        target = f"{base}.{alias.name}" if base else alias.name
                        if _is_in_scope(target, module_prefix):
                            imported.add(target)
    return imported


def _topological_sort(modules: list[str], graph: dict[str, set[str]]) -> list[str]:
    """Sort modules so that dependencies are imported first using graphlib."""
    ts = graphlib.TopologicalSorter(graph)
    try:
        return list(ts.static_order())
    except graphlib.CycleError:
        return sorted(modules)


def discover_and_import_models(
    module_directory_path: str, module_import_prefix: str, logger: logging.Logger
):
    """
    Recursively scans a directory for Python files and imports them.

    Enables automatic model discovery by importing all .py files within a module
    directory. Classes inheriting from ChaCCBaseModel are automatically registered
    in SQLAlchemy metadata used by the migration system.

    The parent of *module_directory_path* must already be on ``sys.path``
    (``loader.py`` ensures this by adding ``MODULES_LOADED_DIR``).

    Args:
        module_directory_path: Path to the module directory to scan.
        module_import_prefix: Python module prefix for constructing import names.
        logger: Logger instance for recording discovery progress and errors.
    """
    module_directory_path = os.path.abspath(module_directory_path)

    parent_dir = os.path.dirname(module_directory_path)
    _added_parent = parent_dir not in sys.path

    try:
        if _added_parent:
            sys.path.insert(0, parent_dir)

        depth_groups: dict[int, list[tuple[str, str, str]]] = {}

        for root, dirs, files in os.walk(module_directory_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            rel_root = os.path.relpath(root, module_directory_path)
            depth = 1 if rel_root == "." else rel_root.count(os.sep) + 1
            for file in files:
                if not file.endswith(".py"):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, module_directory_path)
                depth_groups.setdefault(depth, []).append((file_path, rel_path, file))

        all_info: dict[str, tuple[str, str, str, str]] = {}

        for depth, files in depth_groups.items():
            for file_path, rel_path, file in files:
                if file == "__init__.py":
                    rel_dir = os.path.dirname(rel_path)
                    module_name = _enclosing(module_import_prefix, rel_dir)
                else:
                    rel_dir = os.path.dirname(rel_path)
                    module_name = _dotted_name(module_import_prefix, rel_dir, file[:-3])
                enclosing = _enclosing(module_import_prefix, rel_dir)
                all_info[module_name] = (file_path, rel_path, file, enclosing)

        known = set(all_info.keys())
        dep_graph = defaultdict(set)
        for module_name, (file_path, _, _, enclosing) in all_info.items():
            imports = _parse_imports(file_path, module_import_prefix, enclosing)
            dep_graph[module_name] = imports & known

        for depth in sorted(depth_groups):
            depth_files = depth_groups[depth]

            regular = []
            inits = []
            for file_path, rel_path, file in depth_files:
                if file == "__init__.py":
                    rel_dir = os.path.dirname(rel_path)
                    module_name = _enclosing(module_import_prefix, rel_dir)
                    enclosing = _enclosing(module_import_prefix, rel_dir)
                    inits.append((file_path, rel_path, file, module_name, enclosing))
                else:
                    rel_dir = os.path.dirname(rel_path)
                    module_name = _dotted_name(module_import_prefix, rel_dir, file[:-3])
                    enclosing = _enclosing(module_import_prefix, rel_dir)
                    regular.append((file_path, rel_path, file, module_name, enclosing))

            all_depth = [r[3] for r in regular] + [i[3] for i in inits]
            depth_dep = {m: dep_graph.get(m, set()) & set(all_depth) for m in all_depth}
            sorted_depth = _topological_sort(all_depth, depth_dep)

            sorted_regular = [m for m in sorted_depth if m in {r[3] for r in regular}]
            sorted_inits = [m for m in sorted_depth if m in {i[3] for i in inits}]

            regular_map = {r[3]: r for r in regular}
            init_map = {i[3]: i for i in inits}

            for module_name in sorted_regular:
                file_path, rel_path, file, mod_name, enclosing = regular_map[module_name]

                if mod_name in sys.modules:
                    logger.debug(f"Skipping already imported: {mod_name}")
                    continue

                try:
                    spec = importlib.util.spec_from_file_location(mod_name, file_path)
                    if not spec or not spec.loader:
                        logger.warning(f"Could not create spec for {file_path}")
                        continue
                    mod = importlib.util.module_from_spec(spec)
                    mod.__package__ = enclosing
                    mod.__name__ = mod_name
                    sys.modules[mod_name] = mod
                    spec.loader.exec_module(mod)
                    logger.info(f"Scanned for models in: {mod_name}")

                except ImportError as e:
                    if "already defined for this MetaData instance" in str(e):
                        logger.warning(
                            f"Skipping {file_path}: its table is already registered in metadata."
                        )
                        continue
                    logger.error(f"Relative import issue in {file_path}: {e}")
                except SyntaxError as e:
                    logger.error(f"SyntaxError in {file_path} (line {e.lineno}): {e.msg}")
                except Exception as e:
                    if "already defined for this MetaData instance" in str(e):
                        logger.warning(
                            f"Skipping {file_path}: its table is already registered in metadata."
                        )
                        continue
                    logger.exception(f"Failed to import models from {file_path}")

            for module_name in sorted_inits:
                file_path, rel_path, file, mod_name, enclosing = init_map[module_name]

                if mod_name in sys.modules:
                    logger.debug(f"Skipping already imported: {mod_name}")
                    continue

                try:
                    spec = importlib.util.spec_from_file_location(mod_name, file_path)
                    if not spec or not spec.loader:
                        logger.warning(f"Could not create spec for {file_path}")
                        continue
                    mod = importlib.util.module_from_spec(spec)
                    mod.__package__ = mod_name
                    mod.__name__ = mod_name
                    sys.modules[mod_name] = mod
                    spec.loader.exec_module(mod)
                    logger.info(f"Scanned for models in: {mod_name}")

                except ImportError as e:
                    if "already defined for this MetaData instance" in str(e):
                        logger.warning(
                            f"Skipping {file_path}: its table is already registered in metadata."
                        )
                        continue
                    logger.warning(f"Relative import issue in {file_path}: {e}")
                except SyntaxError as e:
                    logger.warning(f"SyntaxError in {file_path} (line {e.lineno}): {e.msg}")
                except Exception as e:
                    if "already defined for this MetaData instance" in str(e):
                        logger.warning(
                            f"Skipping {file_path}: its table is already registered in metadata."
                        )
                        continue
                    logger.exception(f"Failed to import models from {file_path}")

    finally:
        if _added_parent and parent_dir in sys.path:
            sys.path.remove(parent_dir)
