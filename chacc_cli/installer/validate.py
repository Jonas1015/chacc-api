"""
``module_meta.json`` validation for ``chacc install``.

Reuses :func:`chacc_cli.commands.validate_module_name` rather than re-implementing
name rules.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from chacc_cli.commands import validate_module_name


class ValidationError(Exception):
    """Raised for any user-facing module_meta.json problem."""


@dataclass
class ModuleMeta:
    name: str
    meta: dict
    has_requirements: bool
    has_git: bool
    module_dir: str


def load_and_validate(module_dir: str) -> ModuleMeta:
    meta_path = os.path.join(module_dir, "module_meta.json")
    if not os.path.isfile(meta_path):
        raise ValidationError(f"No module_meta.json found in '{module_dir}'. Not a ChaCC module?")

    try:
        with open(meta_path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"module_meta.json in '{module_dir}' is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValidationError("module_meta.json must contain a JSON object at the top level.")

    raw_name = data.get("name")
    if not raw_name or not isinstance(raw_name, str):
        raise ValidationError("module_meta.json 'name' is missing or not a string.")

    try:
        clean_name = validate_module_name(raw_name)
    except ValueError as exc:
        raise ValidationError(f"module_meta.json 'name' is invalid: {exc}") from exc

    entry_point = data.get("entry_point")
    if entry_point and isinstance(entry_point, str):
        # entry_point format: "<module_path>:<callable>"
        if ":" not in entry_point:
            raise ValidationError(
                f"entry_point '{entry_point}' must be of the form 'module.path:callable'."
            )
        module_path, _, _ = entry_point.partition(":")
        candidate = os.path.join(module_dir, *module_path.split(".")) + ".py"
        if not os.path.isfile(candidate):
            # we don't fail hard here - module_path may use __init__ layout - warn via meta
            pass

    has_requirements = os.path.isfile(os.path.join(module_dir, "requirements.txt"))
    has_git = os.path.isdir(os.path.join(module_dir, ".git"))

    return ModuleMeta(
        name=clean_name,
        meta=data,
        has_requirements=has_requirements,
        has_git=has_git,
        module_dir=module_dir,
    )
