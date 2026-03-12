"""
ChaCC CLI command implementations.
Separated from main CLI interface for better organization.
"""

from asyncio import subprocess
import os
import shutil
import json
import zipfile

from chacc_api.utils import configure_logging, LogLevels
import requests
from decouple import config

cli_logger = configure_logging(log_level=LogLevels.INFO)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def to_pascal_case(name: str) -> str:
    """Convert a name to PascalCase (e.g., 'test_module' -> 'TestModule')."""
    return name.replace("_", " ").replace("-", " ").title().replace(" ", "")


def validate_module_name(module_name: str) -> str:
    """
    Validate and clean module name.
    - Converts to lowercase
    - Replaces spaces and hyphens with underscores
    - Returns cleaned name
    Raises ValueError if name is invalid.
    """
    if not module_name:
        raise ValueError("Module name cannot be empty")

    cleaned = module_name.lower().replace(" ", "_").replace("-", "_")

    if not cleaned.replace("_", "").isalnum():
        raise ValueError(
            "Module name can only contain letters, numbers, underscores, hyphens, and spaces"
        )

    if cleaned[0].isdigit():
        raise ValueError("Module name cannot start with a number")

    return cleaned


def load_template(template_name: str, replacements: dict = None) -> str:
    """
    Load a template file and optionally replace placeholders.

    Args:
        template_name: Name of the template file (e.g., 'main.py.template')
        replacements: Dictionary of placeholder replacements

    Returns:
        Template content with replacements applied
    """
    template_path = os.path.join(TEMPLATES_DIR, template_name)

    if not os.path.exists(template_path):
        cli_logger.warning(f"Template {template_name} not found, using fallback")
        return ""

    with open(template_path, "r") as f:
        content = f.read()

    if replacements:
        for key, value in replacements.items():
            placeholder = "{{" + key + "}}"
            content = content.replace(placeholder, str(value))
            title_placeholder = "{{" + key + "_title}}"
            content = content.replace(title_placeholder, str(value).replace("_", " ").title())
            snake_placeholder = "{{" + key + "_snake}}"
            content = content.replace(snake_placeholder, str(value).replace("-", "_"))
            upper_placeholder = "{{" + key + "_upper}}"
            content = content.replace(upper_placeholder, str(value).upper())
            pascal_placeholder = "{{" + key + "_pascal}}"
            content = content.replace(pascal_placeholder, to_pascal_case(str(value)))

    return content


def create_module_scaffold(module_name: str, output_dir: str, force: bool = False):
    """
    Creates the basic folder structure and template files for a new ChaCC API module.
    Includes comprehensive testing architecture and development tools.

    Validates module name and converts to appropriate formats for different uses.

    Args:
        module_name: Name of the module to create
        output_dir: Directory where module will be created
        force: If True, overwrite existing directory without asking
    """
    try:
        clean_module_name = validate_module_name(module_name)
    except ValueError as e:
        cli_logger.error(f"Error: {e}")
        return

    module_name_pascal = to_pascal_case(clean_module_name)

    module_root_dir = os.path.join(output_dir, clean_module_name)
    module_code_dir = os.path.join(module_root_dir, f"{clean_module_name}_src")
    module_tests_dir = os.path.join(module_root_dir, f"{clean_module_name}_src", "tests")

    if os.path.exists(module_root_dir):
        if not force:
            response = input(
                f"Module directory '{module_root_dir}' already exists. Overwrite? [y/N]: "
            )
            if response.lower() not in ("y", "yes"):
                cli_logger.info("Aborted. Module was not created.")
                return
        cli_logger.info(f"Overwriting existing module '{clean_module_name}'...")
        shutil.rmtree(module_root_dir)

    cli_logger.info(f"Creating new module '{clean_module_name}' in '{module_root_dir}'...")

    replacements = {
        "module_name": clean_module_name,
        "module_name_pascal": module_name_pascal,
        "module_name_title": clean_module_name.replace("_", " ").title(),
        "module_name_upper": clean_module_name.upper(),
        "module_description": f"A new ChaCC API module providing {clean_module_name.replace('_', ' ')} functionality.",
        "module_configuration": "- `CHACC_ENV`: Set to `development`, `testing`, or `production`\n- `CHACC_BACKBONE`: Set to `true` when running in ChaCC backbone",
        "module_api_endpoints": f"- `GET /{clean_module_name}/hello` - Health check endpoint",
        "author_name": "Your Name/Organization",
    }

    try:
        os.makedirs(module_tests_dir, exist_ok=True)

        with open(os.path.join(module_code_dir, "__init__.py"), "w") as f:
            f.write("")

        with open(os.path.join(module_tests_dir, "__init__.py"), "w") as f:
            f.write("")

        models_content = load_template("models.py.template", replacements)
        with open(os.path.join(module_code_dir, "models.py"), "w") as f:
            f.write(models_content)

        routes_content = load_template("routes.py.template", replacements)
        with open(os.path.join(module_code_dir, "routes.py"), "w") as f:
            f.write(routes_content)

        dev_context_content = load_template("dev_context.py.template", replacements)
        with open(os.path.join(module_code_dir, "dev_context.py"), "w") as f:
            f.write(dev_context_content)

        context_factory_content = load_template("context_factory.py.template", replacements)
        with open(os.path.join(module_code_dir, "context_factory.py"), "w") as f:
            f.write(context_factory_content)

        main_content = load_template("main.py.template", replacements)
        with open(os.path.join(module_code_dir, "main.py"), "w") as f:
            f.write(main_content)

        run_tests_content = load_template("run_tests.py.template", replacements)
        with open(os.path.join(module_code_dir, "run_tests.py"), "w") as f:
            f.write(run_tests_content)

        test_content = load_template("test_module.py.template", replacements)
        with open(os.path.join(module_tests_dir, "test_module.py"), "w") as f:
            f.write(test_content)

        meta_content = {
            "name": clean_module_name,
            "display_name": f"{module_name_pascal} Module",
            "version": "0.1.0",
            "author": "Your Name/Organization",
            "description": f"A new ChaCC module providing {clean_module_name.replace('_', ' ')} functionality.",
            "entry_point": f"{clean_module_name}_src.main:setup_plugin",
            "test_entry_point": f"{clean_module_name}_src.tests.test_module:run_module_tests",
            "base_path_prefix": f"/{clean_module_name.replace('_', '-')}",
            "dependencies_file": "requirements.txt",
            "required_chacc_version": ">=1.0.0",
            "license": "MIT",
            "tags": ["testing"],
            "homepage": f"https://github.com/your-org/{clean_module_name}",
        }
        with open(os.path.join(module_root_dir, "module_meta.json"), "w") as f:
            json.dump(meta_content, f, indent=2)

        with open(os.path.join(module_root_dir, "requirements.txt"), "w") as f:
            f.write("# Add your module's specific Python dependencies here, one per line.\n")
            f.write("# Example: requests\n")
            f.write("# Example: pandas==1.5.0\n")

        readme_content = load_template("README.md.template", replacements)
        with open(os.path.join(module_root_dir, "README.md"), "w") as f:
            f.write(readme_content)

        gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
env/
.venv

# IDEs
.vscode/
.idea/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/

# Module specific
*.chacc
modules_installed/
.monitoring
"""
        with open(os.path.join(module_root_dir, ".gitignore"), "w") as f:
            f.write(gitignore_content)

        try:
            subprocess.run(["git", "init"], cwd=module_root_dir, capture_output=True)
            subprocess.run(["git", "add", "."], cwd=module_root_dir, capture_output=True)
            cli_logger.info("Initialized git repository.")
        except FileNotFoundError:
            cli_logger.warning("git not found. Skipping git initialization.")
        except Exception as e:
            cli_logger.warning(f"Could not initialize git: {e}")

        cli_logger.info(f"Successfully created module '{clean_module_name}'.")
        cli_logger.info(
            f"Next steps: cd {module_root_dir} && python {clean_module_name}_src/run_tests.py setup && python {clean_module_name}_src/run_tests.py test"
        )

    except Exception as e:
        cli_logger.error(f"Failed to create a module '{clean_module_name}': {e}", exc_info=True)
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
        cli_logger.error(
            f"Error: 'module_meta.json' not found in '{module_source_dir}'. This file is required for building."
        )
        return

    try:
        with open(meta_filepath, "r") as f:
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

        with zipfile.ZipFile(output_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
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
        deploy_url = config("CHACC_DEPLOY_URL", default=None)
        deploy_api_key = config("CHACC_DEPLOY_API_KEY", default=None)
        deploy_timeout = config("CHACC_DEPLOY_TIMEOUT", default=30, cast=int)

        if not deploy_url:
            cli_logger.error("Error: CHACC_DEPLOY_URL not set in environment variables.")
            cli_logger.info(
                "Please set CHACC_DEPLOY_URL in your .env file (e.g., CHACC_DEPLOY_URL=http://your-api.com)"
            )
            return

    except Exception as e:
        cli_logger.error(f"Error reading deployment configuration: {e}")
        return

    cli_logger.info(f"Deploying '{chacc_file_path}' to {deploy_url}...")

    try:
        with open(chacc_file_path, "rb") as f:
            files = {"file": (os.path.basename(chacc_file_path), f, "application/zip")}
            headers = {}
            if deploy_api_key:
                headers["Authorization"] = f"Bearer {deploy_api_key}"

            response = requests.post(
                f"{deploy_url}/modules/", files=files, headers=headers, timeout=deploy_timeout
            )

            if response.status_code == 200:
                cli_logger.info("=" * 60)
                cli_logger.info("🟢 Module deployed successfully!")
                cli_logger.info("🟢 Response: %s", response.json().get("message", "No message"))
                cli_logger.info(
                    "🟢 Please restart your remote ChaCC API server to activate the module."
                )
                cli_logger.info("=" * 60)
            else:
                cli_logger.error(f"🔴 Deployment failed with status code {response.status_code}")
                try:
                    error_data = response.json()
                    cli_logger.error(
                        f"Error details: {error_data.get('detail', 'No details available')}"
                    )
                except Exception:
                    cli_logger.error(f"Response: {response.text}")

    except requests.exceptions.Timeout:
        cli_logger.error(f"🔴 Deployment timed out after {deploy_timeout} seconds")
    except requests.exceptions.ConnectionError:
        cli_logger.error(f"🔴 Could not connect to {deploy_url}")
        cli_logger.info("💡 Check that your ChaCC API server is running and accessible")
    except Exception as e:
        cli_logger.error(f"🔴 Deployment error: {e}")
