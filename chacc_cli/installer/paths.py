"""
Destination resolution and atomic filesystem operations for ``chacc install``.

We import :mod:`src.constants` lazily so the CLI runs even when the package
is not on ``sys.path``. The constants themselves are read via
``decouple.config`` against the same ``.env`` the server uses, so the CLI and
the server always agree on where to write.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from typing import Literal

Mode = Literal["dev", "prod"]


class PathError(Exception):
    """Raised for any user-facing filesystem problem."""


@dataclass
class Destinations:
    plugins_dir: str
    modules_installed_dir: str

    def resolve(self, mode: Mode, name: str) -> tuple[str, bool]:
        """
        Return ``(destination_path, is_archive)`` for the given module name.

        - dev -> ``<plugins_dir>/<name>`` (directory)
        - prod -> ``<modules_installed_dir>/<name>.chacc`` (file)
        """
        if mode == "dev":
            return os.path.join(self.plugins_dir, name), False
        return os.path.join(self.modules_installed_dir, f"{name}.chacc"), True


def _import_constants():
    """Best-effort import of src.constants; raise a clear error if unavailable."""
    try:
        from src import constants  # type: ignore

        return constants
    except ImportError as exc:
        raise PathError(
            "Cannot import src.constants. Make sure the chacc-api project root "
            "(the directory containing 'src/') is the current working directory "
            "or is on PYTHONPATH."
        ) from exc


def load_destinations() -> Destinations:
    constants = _import_constants()
    return Destinations(
        plugins_dir=constants.PLUGINS_DIR,
        modules_installed_dir=constants.MODULES_INSTALLED_DIR,
    )


def ensure_clean_destination(destination: str, is_archive: bool, force: bool) -> None:
    """Refuse to overwrite unless ``force`` is set; otherwise remove the existing entry."""
    if is_archive and os.path.isfile(destination):
        if not force:
            raise PathError(
                f"Module archive '{destination}' already exists. Use --force to overwrite."
            )
        os.remove(destination)
    elif not is_archive and os.path.isdir(destination):
        if not force:
            raise PathError(
                f"Module directory '{destination}' already exists. Use --force to overwrite."
            )
        shutil.rmtree(destination)


def copytree_dev(source: str, destination: str) -> None:
    """Dev install: copy the source tree, ignoring ``__pycache__``."""
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(source, destination, ignore=ignore)


def stage_for_archive(source: str) -> str:
    """
    Copy ``source`` into a fresh temp dir and return that path.

    Used for prod installs so the source directory is never mutated.
    """
    staging = tempfile.mkdtemp(prefix="chacc-install-build-")
    staging_name = os.path.join(staging, os.path.basename(source.rstrip("/")) or "module")
    shutil.copytree(source, staging_name)
    return staging_name


def atomic_replace(src_path: str, dest_path: str) -> None:
    """Move ``src_path`` to ``dest_path`` atomically (within the same filesystem)."""
    tmp_path = f"{dest_path}.tmp"
    shutil.move(src_path, tmp_path)
    os.replace(tmp_path, dest_path)


def strip_git(source: str) -> None:
    """Remove the ``.git`` directory from the staging tree before archiving."""
    git_dir = os.path.join(source, ".git")
    if os.path.isdir(git_dir):
        shutil.rmtree(git_dir, ignore_errors=True)


def stdlib_path() -> str | None:
    """Return the ``sys.path`` entry that lets ``import src.constants`` work, or None."""
    for entry in sys.path:
        if not entry:
            continue
        if os.path.isdir(os.path.join(entry, "src")):
            return entry
    cwd = os.getcwd()
    if os.path.isdir(os.path.join(cwd, "src")):
        return cwd
    return None
