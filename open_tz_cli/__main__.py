import argparse
import os
import shutil
import json
import zipfile

from src.logger import configure_logging, LogLevels

cli_logger = configure_logging(log_level=LogLevels.info)

def create_module_scaffold(module_name: str, output_dir: str):
    """
    Creates the basic folder structure and template files for a new Open-TZ module.
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
from src.core_services import BackboneContext # Import backbone context
from sqlalchemy.orm import Session # For type hinting database sessions
from sqlalchemy import Column, Integer, String # For defining SQLAlchemy models (if needed)
# from src.database import Base # Uncomment if this module defines its own DB models

router = APIRouter(
    tags = ["{module_name.replace('_', ' ').title()} Module"],
)
_module_context: BackboneContext = None

def setup_plugin(context: BackboneContext):
    \"\"\"
    This function is called by the Open-TZ backbone to initialize your module.
    It receives the BackboneContext, which provides access to shared services.
    \"\"\"
    global _module_context
    _module_context = context

    _module_context.logger.info("{module_name}: Setup initiated!")

    # Example endpoint using backbone's logger and limiter
    @router.get("/hello")
    @_module_context.limiter.limit("5/minute")
    async def hello_world(request: Request):
        _module_context.logger.info(f"Hello endpoint hit in {module_name}.")
        return {{"message": "Hello from {module_name}!"}}

    # Example endpoint using database access (uncomment if you define models and use DB)
    # @router.post("/items/", status_code=status.HTTP_201_CREATED)
    # async def create_item(name: str, db: Session = Depends(_module_context.get_db)):
    #     # Your module's item model (e.g., in module/models.py or here)
    #     # class MyModuleItem(Base):
    #     #     __tablename__ = "my_module_items"
    #     #     id = Column(Integer, primary_key=True, index=True)
    #     #     name = Column(String, index=True)
    #     # db_item = MyModuleItem(name=name)
    #     # db.add(db_item)
    #     # db.commit()
    #     # db.refresh(db_item)
    #     _module_context.logger.info(f"Item '{{name}}' created via {module_name} module.")
    #     return {{"message": f"Item '{{name}}' created successfully by {module_name}."}}

    return router

def get_plugin_info():
    \"\"\"
    Provides essential information about this module to the Open-TZ backbone.
    \"\"\"
    return {{
        "name": "{module_name}",
        "display_name": "{module_name.replace('_', ' ').title()} Module",
        "version": "0.1.0",
        "author": "Your Name/Organization",
        "description": "A new Open-TZ module for {module_name.replace('_', ' ')} functionality.",
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
            "description": f"A new Open-TZ module providing {module_name.replace('_', ' ')} functionality.",
            "entry_point": "main:setup_plugin",
            "base_path_prefix": f"/{module_name.replace('_', '-')}",
            "dependencies_file": "requirements.txt",
            "required_open_tz_version": ">=1.0.0",
            "license": "MIT",
            "tags": ["utility", "new-module"],
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

def build_module_otz(module_source_dir: str, output_filename: str = None):
    """
    Builds an .otz package from a module source directory.
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
        output_filename = f"{module_name}.otz"
    elif not output_filename.endswith(".otz"):
        output_filename += ".otz"

    temp_zip_content_dir = f"{module_name}_otz_temp"
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
        cli_logger.error(f"Error creating .otz package: {e}", exc_info=True)
    finally:
        if os.path.exists(temp_zip_content_dir):
            shutil.rmtree(temp_zip_content_dir)

def main():
    parser = argparse.ArgumentParser(
        prog="open-tz",
        description="Open-TZ CLI for module scaffolding and packaging."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    scaffold_parser = subparsers.add_parser("create", help="Create a new Open-TZ module.")
    scaffold_parser.add_argument("module_name", type=str, help="The name of the module to create (e.g., 'my_awesome_module').")
    scaffold_parser.add_argument("--output-dir", type=str, default="plugins",
                                 help="The directory where the new module will be created. Defaults to 'plugins/'.")
    
    build_parser = subparsers.add_parser("build", help="Build an Open-TZ module into an .otz package.")
    build_parser.add_argument("module_source_dir", type=str, help="The path to the module's source directory (e.g., 'plugins/my_awesome_module').")
    build_parser.add_argument("--output-filename", type=str, default=None,
                              help="Optional: The name of the output .otz file. Defaults to '<module_name>.otz'.")

    args = parser.parse_args()

    if args.command == "create":
        create_module_scaffold(args.module_name, args.output_dir)
    elif args.command == "build":
        build_module_otz(args.module_source_dir, args.output_filename)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

