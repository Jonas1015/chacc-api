"""
ChaCC CLI command implementations.
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
    Creates the basic folder structure and template files for a new ChaCC API module.
    Includes comprehensive testing architecture and development tools.
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

        # Create __init__.py files
        with open(os.path.join(module_code_dir, "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(module_tests_dir, "__init__.py"), "w") as f:
            f.write("")

        # Create models.py
        models_content = f"""
from src import ChaCCBaseModel, register_model
from sqlalchemy import Column, String
from pydantic import BaseModel


# @register_model
# class {module_name.title()}Item(ChaCCBaseModel):
#     __tablename__ = "{module_name}_items"
#     name = Column(String, index=True)


# Pydantic models for API
# class {module_name.title()}Create(BaseModel):
#     name: str

# class {module_name.title()}Response(BaseModel):
#     id: int
#     name: str
"""
        with open(os.path.join(module_code_dir, "models.py"), "w") as f:
            f.write(models_content)

        # Create routes.py
        routes_content = f"""
from fastapi import APIRouter, Request, Depends
from .models import {module_name.title()}Item, {module_name.title()}Create, {module_name.title()}Response

router = APIRouter()

@router.get("/hello")
async def hello_world(request: Request):
    return {{"message": "Hello from {module_name}!"}}

# Add your module endpoints here
# @router.post("/", response_model={module_name.title()}Response)
# async def create_item(item: {module_name.title()}Create):
#     # Implementation here
#     pass
"""
        with open(os.path.join(module_code_dir, "routes.py"), "w") as f:
            f.write(routes_content)

        # Create dev_context.py
        dev_context_content = f"""
\"\"\"
Development context provider for testing modules outside the backbone.
\"\"\"
import logging
from src.core_services import BackboneContext
from src.database import get_db


class DevBackboneContext(BackboneContext):
    \"\"\"Mock BackboneContext for development and testing.\"\"\"

    def __init__(self):
        # Mock logger
        self.logger = logging.getLogger("dev_{module_name}")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # Mock services registry
        self._services = {{}}
        self._event_listeners = {{}}

    def register_service(self, name, service):
        \"\"\"Register a service.\"\"\"
        self._services[name] = service
        self.logger.info(f"Registered service: {{name}}")

    def get_service(self, name):
        \"\"\"Get a registered service.\"\"\"
        return self._services.get(name)

    def emit_event(self, event_name, data=None):
        \"\"\"Emit an event to listeners.\"\"\"
        listeners = self._event_listeners.get(event_name, [])
        for listener in listeners:
            try:
                listener(data)
            except Exception as e:
                self.logger.error(f"Error in event listener for {{event_name}}: {{e}}")

    def on_event(self, event_name, callback):
        \"\"\"Register an event listener.\"\"\"
        if event_name not in self._event_listeners:
            self._event_listeners[event_name] = []
        self._event_listeners[event_name].append(callback)

    def get_db(self):
        \"\"\"Get database session (returns the real get_db).\"\"\"
        return get_db()


def get_dev_context():
    \"\"\"Get a development context instance.\"\"\"
    return DevBackboneContext()


def run_module_standalone():
    \"\"\"Run the module in standalone mode for development.\"\"\"
    from .main import setup_plugin
    from .routes import router
    from fastapi import FastAPI
    import uvicorn

    # Create dev context
    context = get_dev_context()

    # Setup the module
    module_router = setup_plugin(context)

    # Create standalone app
    app = FastAPI(title="{module_name.title()} Module - Standalone")

    # Mount the module router
    app.include_router(module_router, prefix="/{module_name}")

    # Add health check
    @app.get("/health")
    async def health():
        return {{"status": "healthy", "module": "{module_name}"}}

    print("Starting {module_name} module in standalone mode...")
    print("Access at: http://localhost:8001/{module_name}/")
    print("Health check: http://localhost:8001/health")

    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    run_module_standalone()
"""
        with open(os.path.join(module_code_dir, "dev_context.py"), "w") as f:
            f.write(dev_context_content)

        # Create context_factory.py
        context_factory_content = f"""
\"\"\"
Context factory for providing BackboneContext in different environments.
\"\"\"
import os
from typing import Optional
from src.core_services import BackboneContext


class ContextFactory:
    \"\"\"Factory for creating appropriate BackboneContext based on environment.\"\"\"

    @staticmethod
    def get_context(context: Optional[BackboneContext] = None) -> BackboneContext:
        \"\"\"
        Get the appropriate context for the current environment.

        Args:
            context: Provided context (when running in backbone)

        Returns:
            BackboneContext instance
        \"\"\"
        if context is not None:
            # Running within the backbone
            return context

        # Check environment
        env = os.getenv("CHACC_ENV", "development")

        if env == "production":
            # In production, we should have a context, but provide fallback
            from .dev_context import DevBackboneContext
            ctx = DevBackboneContext()
            ctx.logger.warning("No context provided in production environment")
            return ctx
        elif env == "testing":
            # For testing, use minimal context
            from .dev_context import DevBackboneContext
            return DevBackboneContext()
        else:
            # Development mode
            from .dev_context import get_dev_context
            return get_dev_context()

    @staticmethod
    def is_backbone_available() -> bool:
        \"\"\"Check if we're running within the ChaCC backbone.\"\"\"
        # Check for backbone-specific environment variables or markers
        return os.getenv("CHACC_BACKBONE") == "true"

    @staticmethod
    def require_backbone():
        \"\"\"Raise error if not running in backbone (for production modules).\"\"\"
        if not ContextFactory.is_backbone_available():
            raise RuntimeError(
                "This module requires the ChaCC backbone to be available. "
                "Use development context for testing: CHACC_ENV=development"
            )


# Convenience function
def get_context(context: Optional[BackboneContext] = None) -> BackboneContext:
    \"\"\"Get context using the factory.\"\"\"
    return ContextFactory.get_context(context)
"""
        with open(os.path.join(module_code_dir, "context_factory.py"), "w") as f:
            f.write(context_factory_content)

        # Create main.py
        main_content = f"""
from fastapi import APIRouter
from src.core_services import BackboneContext
from typing import Optional
from .routes import router as {module_name}_router
from .context_factory import get_context

_module_context: BackboneContext = None


# --- Module Setup ---
def setup_plugin(context: Optional[BackboneContext] = None):
    \"\"\"
    This function is called by the ChaCC API backbone to initialize your module.
    It can also be called in development mode without a context.
    \"\"\"
    global _module_context
    _module_context = get_context(context)

    _module_context.logger.info("{module_name}: Setup initiated!")

    # Register services (add your services here)
    # _module_context.register_service("your_service", your_service_function)

    return {module_name}_router


def get_plugin_info():
    \"\"\"
    Provides essential information about this module to the ChaCC API backbone.
    \"\"\"
    return {{
        "name": "{module_name}",
        "display_name": "{module_name.replace('_', ' ').title()} Module",
        "version": "0.1.0",
        "author": "Your Name/Organization",
        "description": "A new ChaCC API module for {module_name.replace('_', ' ')} functionality.",
        "status": "enabled"
    }}
"""
        with open(os.path.join(module_code_dir, "main.py"), "w") as f:
            f.write(main_content)

        # Create run_tests.py
        run_tests_content = f"""
#!/usr/bin/env python3
\"\"\"
Script to run tests and development tools for the {module_name} module.
\"\"\"
import subprocess
import sys
import os
import argparse


def setup_venv():
    \"\"\"Setup virtual environment if it doesn't exist.\"\"\"
    venv_path = "venv"
    if not os.path.exists(venv_path):
        print("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=True)

    # Activate and install dependencies
    activate_script = os.path.join(venv_path, "bin", "activate") if os.name != 'nt' else os.path.join(venv_path, "Scripts", "activate.bat")
    pip_path = os.path.join(venv_path, "bin", "pip") if os.name != 'nt' else os.path.join(venv_path, "Scripts", "pip.exe")

    print("Installing dependencies...")
    subprocess.run([pip_path, "install", "-r", "requirements.txt"], check=True)
    subprocess.run([pip_path, "install", "pytest", "fastapi", "uvicorn"], check=True)

    return venv_path


def run_tests(venv_path=None):
    \"\"\"Run the module tests.\"\"\"
    module_dir = os.path.dirname(__file__)
    tests_dir = os.path.join(module_dir, "tests")

    # Use venv python if available
    python_exe = sys.executable
    if venv_path:
        python_exe = os.path.join(venv_path, "bin", "python") if os.name != 'nt' else os.path.join(venv_path, "Scripts", "python.exe")

    try:
        # Run pytest
        result = subprocess.run([
            python_exe, "-m", "pytest",
            os.path.join(tests_dir, "test_module.py"),
            "-v", "--tb=short"
        ], cwd=module_dir)

        return result.returncode == 0

    except Exception as e:
        print(f"Error running tests: {{e}}")
        return False


def run_standalone(venv_path=None):
    \"\"\"Run the module in standalone mode.\"\"\"
    python_exe = sys.executable
    if venv_path:
        python_exe = os.path.join(venv_path, "bin", "python") if os.name != 'nt' else os.path.join(venv_path, "Scripts", "python.exe")

    try:
        subprocess.run([python_exe, "dev_context.py"], cwd=os.path.dirname(__file__))
    except KeyboardInterrupt:
        print("\\nShutting down standalone server...")


def main():
    parser = argparse.ArgumentParser(description="{module_name.title()} Module Development Tools")
    parser.add_argument("command", choices=["test", "standalone", "setup"], help="Command to run")
    parser.add_argument("--no-venv", action="store_true", help="Don't use virtual environment")

    args = parser.parse_args()

    venv_path = None
    if not args.no_venv:
        venv_path = setup_venv()

    if args.command == "test":
        success = run_tests(venv_path)
        sys.exit(0 if success else 1)
    elif args.command == "standalone":
        run_standalone(venv_path)
    elif args.command == "setup":
        print("Setup complete!")


if __name__ == "__main__":
    main()
"""
        with open(os.path.join(module_code_dir, "run_tests.py"), "w") as f:
            f.write(run_tests_content)

        test_content = f"""
\"\"\"
Unit tests for {module_name} module.
\"\"\"
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..models import {module_name.title()}Item


@pytest.fixture
def db_session():
    \"\"\"Database session fixture for testing.\"\"\"
    # Create in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:")
    # Create tables for our models
    {module_name.title()}Item.__table__.create(engine, checkfirst=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        {module_name.title()}Item.__table__.drop(engine, checkfirst=True)


def test_{module_name}_model():
    \"\"\"Test {module_name} model creation.\"\"\"
    item = {module_name.title()}Item(name="test")
    assert item.name == "test"


def test_{module_name}_module_info():
    \"\"\"Test module information retrieval.\"\"\"
    from ..main import get_plugin_info

    info = get_plugin_info()
    assert info["name"] == "{module_name}"
    assert info["version"] == "0.1.0"
    assert "status" in info


async def run_module_tests():
    \"\"\"
    Run all module tests.
    This function is called by the ChaCC backbone when the module is loaded.
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
            "description": f"A new ChaCC module providing {module_name.replace('_', ' ')} functionality.",
            "entry_point": "main:setup_plugin",
            "test_entry_point": "tests.test_module:run_module_tests",
            "base_path_prefix": f"/{module_name.replace('_', '-')}",
            "dependencies_file": "requirements.txt",
            "required_chacc_version": ">=1.0.0",
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

        # Create README.md
        readme_content = f"""# {module_name.title()} Module

A ChaCC API module providing {module_name.replace('_', ' ')} functionality.

## Features

- Basic {module_name} operations
- RESTful API endpoints
- Database integration with SQLAlchemy
- Comprehensive testing

## Development

### Environment Setup

```bash
cd {module_name}
python module/run_tests.py setup
```

This creates a virtual environment and installs dependencies.

### Running Tests

```bash
# With venv
python module/run_tests.py test

# Without venv
python module/run_tests.py test --no-venv
```

### Standalone Development

Run the module independently for development:

```bash
python module/run_tests.py standalone
```

The module will be available at `http://localhost:8001/{module_name}/`

### Environment Variables

- `CHACC_ENV`: Set to `development`, `testing`, or `production`
- `CHACC_BACKBONE`: Set to `true` when running in ChaCC backbone

## API Endpoints

### Basic Operations
- `GET /{module_name}/hello` - Health check endpoint

## Module Structure

```
module/
├── __init__.py
├── main.py          # Module setup
├── models.py        # Database models and schemas
├── routes.py        # API endpoints
├── dev_context.py   # Development context mock
├── context_factory.py # Context provider
├── tests/
│   └── test_module.py
└── run_tests.py     # Development tools
```

## Context Access

The module uses a context factory to work in different environments:

- **Production**: Uses provided BackboneContext
- **Development**: DevBackboneContext with mocked services
- **Testing**: Minimal context for isolated testing

## Dependencies

- fastapi
- sqlalchemy
- pydantic
"""
        with open(os.path.join(module_root_dir, "README.md"), "w") as f:
            f.write(readme_content)

        cli_logger.info(f"Successfully created module '{module_name}'.")
        cli_logger.info(f"Next steps: cd {module_root_dir} && python module/run_tests.py setup && python module/run_tests.py test")

    except Exception as e:
        cli_logger.error(f"Failed to create a module '{module_name}': {e}", exc_info=True)
        if os.path.exists(module_root_dir):
            shutil.rmtree(module_root_dir)


def build_module_chacc(module_source_dir: str, output_filename: str = None):
    """
    Builds an .chacc package from a module source directory.
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
        output_filename = f"{module_name}.chacc"
    elif not output_filename.endswith(".chacc"):
        output_filename += ".chacc"

    temp_zip_content_dir = f"{module_name}_chacc_temp"
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
        cli_logger.error(f"Error creating .chacc package: {e}", exc_info=True)
    finally:
        if os.path.exists(temp_zip_content_dir):
            shutil.rmtree(temp_zip_content_dir)


def deploy_module(chacc_file_path: str):
    """
    Deploys an .chacc module to a remote ChaCC API instance.
    Reads deployment configuration from environment variables.
    """
    if not os.path.exists(chacc_file_path):
        cli_logger.error(f"Error: ChaCC file '{chacc_file_path}' not found.")
        return

    try:
        deploy_url = config('CHACC_DEPLOY_URL', default=None)
        deploy_api_key = config('CHACC_DEPLOY_API_KEY', default=None)
        deploy_timeout = config('CHACC_DEPLOY_TIMEOUT', default=30, cast=int)

        if not deploy_url:
            cli_logger.error("Error: CHACC_DEPLOY_URL not set in environment variables.")
            cli_logger.info("Please set CHACC_DEPLOY_URL in your .env file (e.g., CHACC_DEPLOY_URL=http://your-api.com)")
            return

    except Exception as e:
        cli_logger.error(f"Error reading deployment configuration: {e}")
        return

    cli_logger.info(f"Deploying '{chacc_file_path}' to {deploy_url}...")

    try:
        with open(chacc_file_path, 'rb') as f:
            files = {'file': (os.path.basename(chacc_file_path), f, 'application/zip')}
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
                cli_logger.info("🔄 Please restart your remote ChaCC API server to activate the module.")
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
        cli_logger.info("💡 Check that your ChaCC API server is running and accessible")
    except Exception as e:
        cli_logger.error(f"❌ Deployment error: {e}")