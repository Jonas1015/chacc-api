"""
ChaCC CLI command implementations.
Separated from main CLI interface for better organization.
"""

import json
import os
import shutil
import zipfile
from asyncio import subprocess

import requests
from decouple import config

from chacc_api.utils import configure_logging

cli_logger = configure_logging()

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


def load_template(template_name: str, replacements: dict | None = None) -> str:
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
        except (OSError, subprocess.CalledProcessError) as e:
            cli_logger.warning(f"Could not initialize git: {e}")

        cli_logger.info(f"Successfully created module '{clean_module_name}'.")
        cli_logger.info(
            f"Next steps: cd {module_root_dir} && python {clean_module_name}_src/run_tests.py setup && python {clean_module_name}_src/run_tests.py test"
        )

    except Exception:
        cli_logger.exception(f"Failed to create a module '{clean_module_name}'")
        if os.path.exists(module_root_dir):
            shutil.rmtree(module_root_dir)


def build_module_chacc(module_source_dir: str, output_filename: str | None = None):
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
        raw_name = meta_data.get("name", "untitled_module")
        module_name = validate_module_name(raw_name)
    except json.JSONDecodeError:
        cli_logger.error(f"Error: 'module_meta.json' in '{module_source_dir}' is not valid JSON.")
        return

    if not output_filename:
        output_filename = f"{module_name}.chacc"
    elif not output_filename.endswith(".chacc"):
        output_filename += ".chacc"

    temp_zip_content_dir = os.path.join(module_source_dir, f"{module_name}_chacc_temp")
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

    except Exception:
        cli_logger.exception("Error creating .chacc package")
    finally:
        if os.path.exists(temp_zip_content_dir):
            shutil.rmtree(temp_zip_content_dir)


def build_install_parser(subparsers):
    """
    Build the ``chacc install`` subparser.

    Defined here (rather than inline in ``__main__.py``) so it can be unit-tested.
    """
    install_parser = subparsers.add_parser(
        "install",
        help="Install a ChaCC module from a Git URL or local path.",
        description=(
            "Install a ChaCC module from a Git repository (public or private) "
            "or a local directory. In dev, the source is copied into the plugins "
            "directory (preserving the module's .git so you can develop and push "
            "from inside the plugin). In prod, a .chacc archive is built and placed "
            "in the modules install directory."
        ),
    )
    install_parser.add_argument(
        "source",
        help="Path, URL, or short form (owner/repo).",
    )
    install_parser.add_argument(
        "--ref",
        help="Git ref: branch, tag, or commit. Alternative to source@ref syntax.",
    )
    install_parser.add_argument(
        "--dev",
        action="store_true",
        help="Install into the plugins directory (development). Default: production (.chacc archive).",
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing module with the same name.",
    )
    install_parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="Git clone depth. Use 0 or --full for full history. Default: 1.",
    )
    install_parser.add_argument(
        "--full",
        action="store_true",
        help="Use a full git clone (equivalent to --depth 0).",
    )
    install_parser.add_argument(
        "--token-env",
        help="Override the env var name used for token lookup (e.g. MY_CI_TOKEN).",
    )
    install_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-step progress output. Only the final result is printed.",
    )
    return install_parser


def install_module(
    source: str,
    ref: str | None = None,
    dev: bool = False,
    force: bool = False,
    depth: int = 1,
    full: bool = False,
    token_env: str | None = None,
    quiet: bool = False,
):
    """
    Install a ChaCC module from a local path or Git repository.

    See :mod:`chacc_cli.installer` for the per-step implementation.
    """
    from chacc_cli.installer import paths as paths_mod
    from chacc_cli.installer import progress as progress_mod
    from chacc_cli.installer import source as source_mod
    from chacc_cli.installer import validate as validate_mod

    progress_mod.set_quiet(quiet)

    if full:
        depth = 0

    with progress_mod.step("Loading destinations"):
        destinations = paths_mod.load_destinations()

    # --dev flag is the single switch. No --dev means production.
    effective_mode = "dev" if dev else "prod"
    progress_mod.info(f"Mode: {effective_mode} ({'--dev flag' if dev else 'default'})")

    with progress_mod.step("Resolving source", detail=source):
        resolved = source_mod.resolve(source, ref, depth)

    try:
        with progress_mod.step("Validating module", detail=resolved.path):
            meta = validate_mod.load_and_validate(resolved.path)

        progress_mod.info(f"Module name: {meta.name}")
        destination, is_archive = destinations.resolve(effective_mode, meta.name)
        progress_mod.info(f"Destination: {destination}")

        with progress_mod.step("Preparing destination"):
            paths_mod.ensure_clean_destination(destination, is_archive, force)

        if effective_mode == "dev":
            with progress_mod.step("Copying files into plugins directory"):
                paths_mod.copytree_dev(resolved.path, destination)
        else:
            with progress_mod.step("Staging source for build"):
                staging = paths_mod.stage_for_archive(resolved.path)
            try:
                with progress_mod.step("Stripping .git from build staging"):
                    paths_mod.strip_git(staging)
                with progress_mod.step("Building .chacc archive"):
                    built_archive = os.path.join(staging, f"{meta.name}.chacc")
                    build_module_chacc(staging, output_filename=built_archive)
                if not os.path.isfile(built_archive):
                    raise RuntimeError(
                        f"archive '{built_archive}' was not produced by the build step."
                    )
                with progress_mod.step("Placing archive atomically", detail=destination):
                    paths_mod.atomic_replace(built_archive, destination)
            finally:
                shutil.rmtree(staging, ignore_errors=True)

        progress_mod.final(
            f"Module '{meta.name}' installed. Restart the ChaCC server to activate it.",
            success=True,
        )
        if meta.has_requirements:
            progress_mod.warn_always(
                f"Module '{meta.name}' ships requirements.txt. "
                "Dependencies will be installed on server startup; ensure your "
                "environment allows runtime pip installs and has internet access. "
                "If the module changes models, migrations will run automatically on restart."
            )
        return True
    finally:
        source_mod.cleanup(resolved)


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

    except (ValueError, TypeError) as e:
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
                cli_logger.info("SUCCESS: Module deployed successfully!")
                cli_logger.info(
                    "SUCCESS: Response: %s", response.json().get("message", "No message")
                )
                cli_logger.info(
                    "SUCCESS: Please restart your remote ChaCC API server to activate the module."
                )
                cli_logger.info("=" * 60)
            else:
                cli_logger.error(
                    f"FAILED: Deployment failed with status code {response.status_code}"
                )
                try:
                    error_data = response.json()
                    cli_logger.error(
                        f"FAILED: Error details: {error_data.get('detail', 'No details available')}"
                    )
                except (ValueError, AttributeError):
                    cli_logger.error(f"FAILED: Response: {response.text}")

    except requests.exceptions.Timeout:
        cli_logger.error(f"FAILED: Deployment timed out after {deploy_timeout} seconds")
    except requests.exceptions.ConnectionError:
        cli_logger.error(f"FAILED: Could not connect to {deploy_url}")
        cli_logger.info("NOTE: Check that your ChaCC API server is running and accessible")
    except Exception as e:  # noqa: BLE001
        cli_logger.error(f"FAILED: Deployment error: {e}")
