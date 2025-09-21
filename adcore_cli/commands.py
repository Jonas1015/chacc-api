"""
AdCore CLI command implementations.
Separated from main CLI interface for better organization.
"""
import os
import shutil
import json
import zipfile

from src.logger import configure_logging, LogLevels
import requests
from decouple import config

cli_logger = configure_logging(log_level=LogLevels.INFO)


def create_module_scaffold(module_name: str, output_dir: str):
    """
    Creates the basic folder structure and template files for a new AdCore API module.
    Includes comprehensive testing architecture.
    """
    module_root_dir = os.path.join(output_dir, module_name)
    module_code_dir = os.path.join(module_root_dir, "module")
    module_tests_dir = os.path.join(module_root_dir, "module", "tests")

    if os.path.exists(module_root_dir):
        cli_logger.error(f"Error: Module directory '{module_root_dir}' already exists. Please choose a different name or remove it.")
        return

    cli_logger.info(f"Creating new module '{module_name}' in '{module_root_dir}'...")

    try:
        os.makedirs(module_tests_dir, exist_ok=True)

        with open(os.path.join(module_code_dir, "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(module_tests_dir, "__init__.py"), "w") as f:
            f.write("")

        main_py_content = f"""
from fastapi import APIRouter, Request, Depends, HTTPException, status
from src.core_services import BackboneContext
from src import AdCoreBaseModel, register_model
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String

router = APIRouter(
    tags=["{module_name.replace('_', ' ').title()} Module"],
)
_module_context: BackboneContext = None

# --- Models ---
# Decorate your models with @register_model to have them automatically included
# in the database schema management. They should inherit from AdCoreBaseModel
# to get UUID and audit fields (if the authentication module is active).

# @register_model
# class YourModel(AdCoreBaseModel):
#     __tablename__ = "{module_name}_items"
#     name = Column(String, index=True)


# --- Module Setup ---
def setup_plugin(context: BackboneContext):
    \"\"\"
    This function is called by the AdCore API backbone to initialize your module.
    It receives the BackboneContext, which provides access to shared services.
    \"\"\"
    global _module_context
    _module_context = context

    _module_context.logger.info("{module_name}: Setup initiated!")

    # --- Endpoints ---
    @router.get("/hello")
    @_module_context.limiter.limit("5/minute")
    async def hello_world(request: Request):
        _module_context.logger.info(f"Hello endpoint hit in {{module_name}}.")
        return {{"message": "Hello from {module_name}!"}}

    # Example of a secured endpoint that requires authentication
    # get_current_user = _module_context.get_service("get_current_user")
    # if get_current_user:
    #     @router.get("/protected")
    #     async def protected_route(current_user: dict = Depends(get_current_user)):
    #         return {{"message": f"Hello, {{current_user['username']}}! You are accessing a protected route."}}

    return router

def get_plugin_info():
    \"\"\"
    Provides essential information about this module to the AdCore API backbone.
    \"\"\"
    return {{
        "name": "{module_name}",
        "display_name": "{module_name.replace('_', ' ').title()} Module",
        "version": "0.1.0",
        "author": "Your Name/Organization",
        "description": "A new AdCore API module for {module_name.replace('_', ' ')} functionality.",
        "status": "enabled"
    }}
"""
        with open(os.path.join(module_code_dir, "main.py"), "w") as f:
            f.write(main_py_content)

        test_content = f"""
\"\"\"
Unit tests for {module_name} module.
\"\"\"
import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    \"\"\"Test client fixture.\"\"\"
    return TestClient(app)


@pytest.fixture
def module_context():
    \"\"\"Module context fixture.\"\"\"
    # This will be available when the module is loaded
    return None


def test_{module_name}_hello_endpoint(client):
    \"\"\"Test the hello endpoint.\"\"\"
    response = client.get(f"/{module_name.replace('_', '-')}/hello")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "{module_name}" in data["message"]


def test_{module_name}_module_info():
    \"\"\"Test module information retrieval.\"\"\"
    from .main import get_plugin_info

    info = get_plugin_info()
    assert info["name"] == "{module_name}"
    assert info["version"] == "0.1.0"
    assert "status" in info


# Add more specific tests for your module's functionality here
# def test_your_custom_functionality(client, module_context):
#     \"\"\"Test your custom module functionality.\"\"\"
#     # Your test logic here
#     pass


async def run_module_tests():
    \"\"\"
    Run all module tests.
    This function is called by the AdCore backbone when the module is loaded.
    \"\"\"
    import sys
    import os

    # Add the module directory to Python path for testing
    module_dir = os.path.dirname(os.path.dirname(__file__))
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    try:
        # Run pytest programmatically
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            __file__,  # Run this test file
            "-v", "--tb=short", "--no-header"
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))

        if result.returncode == 0:
            print(f"✓ All {module_name} tests passed")
            return {{"status": "passed", "message": f"All {module_name} tests passed"}}
        else:
            print(f"✗ {module_name} tests failed")
            if result.stdout:
                print("Test output:")
                print(result.stdout)
            if result.stderr:
                print("Errors:")
                print(result.stderr)
            return {{
                "status": "failed",
                "message": f"{module_name} tests failed",
                "details": result.stdout + result.stderr
            }}

    except Exception as e:
        print(f"✗ Error running {module_name} tests: {{e}}")
        return {{
            "status": "error",
            "message": f"Error running {module_name} tests: {{e}}"
        }}
"""
        with open(os.path.join(module_tests_dir, "test_module.py"), "w") as f:
            f.write(test_content)

        meta_content = {
            "name": module_name,
            "display_name": f"{module_name.replace('_', ' ').title()} Module",
            "version": "0.1.0",
            "author": "Your Name/Organization",
            "description": f"A new AdCore module providing {module_name.replace('_', ' ')} functionality.",
            "entry_point": "main:setup_plugin",
            "test_entry_point": "tests.test_module:run_module_tests",
            "base_path_prefix": f"/{module_name.replace('_', '-')}",
            "dependencies_file": "requirements.txt",
            "required_adcore_version": ">=1.0.0",
            "license": "MIT",
            "tags": ["testing"],
            "homepage": f"https://github.com/your-org/{module_name}"
        }
        with open(os.path.join(module_root_dir, "module_meta.json"), "w") as f:
            json.dump(meta_content, f, indent=2)

        with open(os.path.join(module_root_dir, "requirements.txt"), "w") as f:
            f.write("# Add your module's specific Python dependencies here, one per line.\n")
            f.write("# Example: requests\n")
            f.write("# Example: pandas==1.5.0\n")

        cli_logger.info(f"Successfully created module '{module_name}'.")
        cli_logger.info(f"Next steps: cd {module_root_dir} and start coding!")

    except Exception as e:
        cli_logger.error(f"Failed to create a module '{module_name}': {e}", exc_info=True)
        if os.path.exists(module_root_dir):
            shutil.rmtree(module_root_dir)


def build_module_adcore(module_source_dir: str, output_filename: str = None):
    """
    Builds an .adcore package from a module source directory.
    """
    if not os.path.isdir(module_source_dir):
        cli_logger.error(f"Error: Source directory '{module_source_dir}' not found.")
        return

    meta_filepath = os.path.join(module_source_dir, "module_meta.json")
    if not os.path.exists(meta_filepath):
        cli_logger.error(f"Error: 'module_meta.json' not found in '{module_source_dir}'. This file is required for building.")
        return

    try:
        with open(meta_filepath, 'r') as f:
            meta_data = json.load(f)
        module_name = meta_data.get("name", "untitled_module")
    except json.JSONDecodeError:
        cli_logger.error(f"Error: 'module_meta.json' in '{module_source_dir}' is not valid JSON.")
        return

    if not output_filename:
        output_filename = f"{module_name}.adcore"
    elif not output_filename.endswith(".adcore"):
        output_filename += ".adcore"

    temp_zip_content_dir = f"{module_name}_adcore_temp"
    if os.path.exists(temp_zip_content_dir):
        shutil.rmtree(temp_zip_content_dir)
    os.makedirs(temp_zip_content_dir)

    try:
        for item in os.listdir(module_source_dir):
            s = os.path.join(module_source_dir, item)
            d = os.path.join(temp_zip_content_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

        with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_zip_content_dir):
                for file in files:
                    filepath = os.path.join(root, file)
                    arcname = os.path.relpath(filepath, temp_zip_content_dir)
                    zipf.write(filepath, arcname)
        cli_logger.info(f"Successfully created {output_filename}")

    except Exception as e:
        cli_logger.error(f"Error creating .adcore package: {e}", exc_info=True)
    finally:
        if os.path.exists(temp_zip_content_dir):
            shutil.rmtree(temp_zip_content_dir)


def deploy_module(adcore_file_path: str):
    """
    Deploys an .adcore module to a remote AdCore API instance.
    Reads deployment configuration from environment variables.
    """
    if not os.path.exists(adcore_file_path):
        cli_logger.error(f"Error: AdCore file '{adcore_file_path}' not found.")
        return

    try:
        deploy_url = config('ADCORE_DEPLOY_URL', default=None)
        deploy_api_key = config('ADCORE_DEPLOY_API_KEY', default=None)
        deploy_timeout = config('ADCORE_DEPLOY_TIMEOUT', default=30, cast=int)

        if not deploy_url:
            cli_logger.error("Error: ADCORE_DEPLOY_URL not set in environment variables.")
            cli_logger.info("Please set ADCORE_DEPLOY_URL in your .env file (e.g., ADCORE_DEPLOY_URL=http://your-api.com)")
            return

    except Exception as e:
        cli_logger.error(f"Error reading deployment configuration: {e}")
        return

    cli_logger.info(f"Deploying '{adcore_file_path}' to {deploy_url}...")

    try:
        with open(adcore_file_path, 'rb') as f:
            files = {'file': (os.path.basename(adcore_file_path), f, 'application/zip')}
            headers = {}
            if deploy_api_key:
                headers['Authorization'] = f'Bearer {deploy_api_key}'

            response = requests.post(
                f"{deploy_url}/modules/",
                files=files,
                headers=headers,
                timeout=deploy_timeout
            )

            if response.status_code == 200:
                cli_logger.info("✅ Module deployed successfully!")
                cli_logger.info("📝 Response: %s", response.json().get('message', 'No message'))
                cli_logger.info("🔄 Please restart your remote AdCore API server to activate the module.")
            else:
                cli_logger.error(f"❌ Deployment failed with status code {response.status_code}")
                try:
                    error_data = response.json()
                    cli_logger.error(f"Error details: {error_data.get('detail', 'No details available')}")
                except:
                    cli_logger.error(f"Response: {response.text}")

    except requests.exceptions.Timeout:
        cli_logger.error(f"❌ Deployment timed out after {deploy_timeout} seconds")
    except requests.exceptions.ConnectionError:
        cli_logger.error(f"❌ Could not connect to {deploy_url}")
        cli_logger.info("💡 Check that your AdCore API server is running and accessible")
    except Exception as e:
        cli_logger.error(f"❌ Deployment error: {e}")