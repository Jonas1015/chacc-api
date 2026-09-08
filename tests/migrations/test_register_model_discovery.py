"""Tests for model discovery functionality via metadata_obj."""

import logging
import os
import tempfile

import pytest

pytest.importorskip("sqlalchemy")

from src.database import ChaCCBaseModel, metadata_obj
from src.module_loader.discovery import discover_and_import_models


def _clear_test_models():
    for model_cls in list(ChaCCBaseModel.__subclasses__()):
        for sub in list(model_cls.__subclasses__()):
            if (
                sub.__name__.startswith("Test")
                or sub.__name__.startswith("Discovered")
                or sub.__name__.startswith("Meta")
            ):
                pass


def test_discover_and_import_adds_to_metadata():
    """Verify that discovered modules add their tables to metadata_obj."""
    with tempfile.TemporaryDirectory() as tmpdir:
        model_file = os.path.join(tmpdir, "test_models.py")
        model_content = """
from src.database import ChaCCBaseModel
from sqlalchemy import Column, String

class DiscoveredModel(ChaCCBaseModel):
    __tablename__ = "discovered_models"
    name = Column(String(50))
"""
        with open(model_file, "w") as f:
            f.write(model_content)

        discover_and_import_models(tmpdir, "discovered_test_module", logging.getLogger())

        assert "discovered_models" in metadata_obj.tables


def test_discover_and_import_adds_to_subclasses():
    """Verify that discovered modules add their classes to ChaCCBaseModel subclasses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        model_file = os.path.join(tmpdir, "test_models.py")
        model_content = """
from src.database import ChaCCBaseModel
from sqlalchemy import Column, String

class MetaTestModel(ChaCCBaseModel):
    __tablename__ = "meta_test_models"
    name = Column(String(50))
"""
        with open(model_file, "w") as f:
            f.write(model_content)

        discover_and_import_models(tmpdir, "meta_test_module", logging.getLogger())

        subclass_names = [cls.__name__ for cls in ChaCCBaseModel.__subclasses__()]
        for sub in list(ChaCCBaseModel.__subclasses__()):
            for inner in sub.__subclasses__():
                subclass_names.append(inner.__name__)

        assert "MetaTestModel" in subclass_names
        assert "meta_test_models" in metadata_obj.tables
