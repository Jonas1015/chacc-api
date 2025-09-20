import argparse
import os
import shutil
import json
import zipfile

from src.logger import configure_logging, LogLevels

cli_logger = configure_logging(log_level=LogLevels.INFO)

def create_module_scaffold(module_name: str, output_dir: str):
    """
    Creates the basic folder structure and template files for a new AdCore API module.
    """
    module_root_dir = os.path.join(output_dir, module_name)
    module_code_dir = os.path.join(module_root_dir, "module")

    if os.path.exists(module_root_dir):
        cli_logger.error(f"Error: Module directory '{module_root_dir}' already exists. Please choose a different name or remove it.")
        return

    cli_logger.info(f"Creating new module '{module_name}' in '{module_root_dir}'...")

    try:
        os.makedirs(module_code_dir, exist_ok=True)

        with open(os.path.join(module_code_dir, "__init__.py"), "w") as f:
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
        _module_context.logger.info(f"Hello endpoint hit in {module_name}.")
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

        meta_content = {
            "name": module_name,
            "display_name": f"{module_name.replace('_', ' ').title()} Module",
            "version": "0.1.0",
            "author": "Your Name/Organization",
            "description": f"A new AdCore module providing {module_name.replace('_', ' ')} functionality.",
            "entry_point": "main:setup_plugin",
            "base_path_prefix": f"/{module_name.replace('_', '-')}",
            "dependencies_file": "requirements.txt",
            "required_adcore_version": ">=1.0.0",
            "license": "MIT",
            "tags": [],
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

def main():
    parser = argparse.ArgumentParser(
        prog="adcore",
        description="AdCore API CLI for module scaffolding and packaging."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    scaffold_parser = subparsers.add_parser("create", help="Create a new AdCore API module.")
    scaffold_parser.add_argument("module_name", type=str, help="The name of the module to create (e.g., 'my_awesome_module').")
    scaffold_parser.add_argument("--output-dir", type=str, default="plugins",
                                 help="The directory where the new module will be created. Defaults to 'plugins/'.")
    
    build_parser = subparsers.add_parser("build", help="Build an AdCore API module into an .adcore package.")
    build_parser.add_argument("module_source_dir", type=str, help="The path to the module's source directory (e.g., 'plugins/my_awesome_module').")
    build_parser.add_argument("--output-filename", type=str, default=None,
                              help="Optional: The name of the output .adcore file. Defaults to '<module_name>.adcore'.")

    args = parser.parse_args()

    if args.command == "create":
        create_module_scaffold(args.module_name, args.output_dir)
    elif args.command == "build":
        build_module_adcore(args.module_source_dir, args.output_filename)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

