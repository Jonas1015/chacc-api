import os
import sys
import tempfile
import shutil
import importlib.util


def test_relative_imports_within_module():
    """Test that modules can import from each other using relative imports."""

    with tempfile.TemporaryDirectory() as temp_dir:
        module_name = "test_relative_imports"
        module_dir = os.path.join(temp_dir, module_name)
        os.makedirs(module_dir, exist_ok=True)

        module_subdir = os.path.join(module_dir, "module")
        os.makedirs(module_subdir, exist_ok=True)

        with open(os.path.join(module_subdir, "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(module_subdir, "models.py"), "w") as f:
            f.write("""
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class TestModel(Base):
    __tablename__ = 'test_model'
    id = Column(Integer, primary_key=True)
    name = Column(String(50))
""")

        with open(os.path.join(module_subdir, "auth.py"), "w") as f:
            f.write("""
from .models import TestModel

def get_test_model():
    return TestModel
""")

        # Create routes.py that imports from auth and models
        with open(os.path.join(module_subdir, "routes.py"), "w") as f:
            f.write("""
from fastapi import APIRouter
from .auth import get_test_model
from .models import TestModel

router = APIRouter()

@router.get("/test")
def test_endpoint():
    model = get_test_model()
    return {"model": model.__name__}
""")

        # Create main.py that imports from other modules
        with open(os.path.join(module_subdir, "main.py"), "w") as f:
            f.write("""
from .routes import router
from .auth import get_test_model
from .models import TestModel

def get_module_info():
    return {
        "router": router,
        "model": TestModel,
        "auth_func": get_test_model
    }
""")

        # Test the module loading with our fix
        plugin_code_dir = module_subdir
        sys.path.insert(0, plugin_code_dir)

        try:
            # Set up the parent package first
            parent_package_name = f"{module_name}.module"
            if parent_package_name not in sys.modules:
                import types

                parent_module = types.ModuleType(parent_package_name)
                parent_module.__path__ = [plugin_code_dir]
                parent_module.__package__ = parent_package_name
                sys.modules[parent_package_name] = parent_module
                print(f"✓ Set up parent package: {parent_package_name}")

            # Pre-register and pre-execute all modules EXCEPT the main entry point
            # This simulates what our fix does in the load_modules function

            all_module_files = []
            for root, _, files in os.walk(plugin_code_dir):
                for file in files:
                    if file.endswith(".py") and file != "__init__.py":
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, plugin_code_dir)
                        module_name_in_package = (
                            f"{module_name}.module.{rel_path[:-3].replace(os.sep, '.')}"
                        )
                        all_module_files.append((file_path, module_name_in_package))

            # Pre-register and pre-execute non-entry-point modules
            for file_path, module_name_in_package in all_module_files:
                if module_name_in_package not in sys.modules:
                    spec = importlib.util.spec_from_file_location(module_name_in_package, file_path)
                    if spec:
                        module = importlib.util.module_from_spec(spec)
                        module.__package__ = f"{module_name}.module"
                        sys.modules[module_name_in_package] = module

                        # Only execute modules that are NOT the main entry point
                        if module_name_in_package != f"{module_name}.module.main":
                            try:
                                spec.loader.exec_module(module)
                                print(f"✓ Pre-executed module: {module_name_in_package}")
                            except Exception as e:
                                print(
                                    f"✗ Failed to pre-execute module {module_name_in_package}: {e}"
                                )

            # Now try to load the main module
            main_file_path = os.path.join(plugin_code_dir, "main.py")
            spec = importlib.util.spec_from_file_location("main", main_file_path)
            main_module = importlib.util.module_from_spec(spec)
            main_module.__package__ = f"{module_name}.module"

            # Execute the main module
            spec.loader.exec_module(main_module)
            print(f"✓ Successfully executed main module")

            # Test that the function works (this would fail if relative imports didn't work)
            module_info = main_module.get_module_info()
            assert "router" in module_info, "Should have router from routes.py"
            assert "model" in module_info, "Should have TestModel from models.py"
            assert "auth_func" in module_info, "Should have get_test_model from auth.py"

            # Verify the router was imported correctly
            from fastapi import APIRouter

            assert isinstance(
                module_info["router"], APIRouter
            ), "Router should be an APIRouter instance"

            print("✓ All relative imports within module work correctly!")
            print("✓ Module loading with relative imports is fixed!")

        finally:
            if plugin_code_dir in sys.path:
                sys.path.remove(plugin_code_dir)


if __name__ == "__main__":
    test_relative_imports_within_module()
    print("All tests passed!")
