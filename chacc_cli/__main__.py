"""
ChaCC CLI - Command Line Interface for ChaCC API module management.
"""
import argparse

from .commands import create_module_scaffold, build_module_chacc, deploy_module
import subprocess
import sys
import os


def main():
    """
    Main CLI entry point.
    """
    parser = argparse.ArgumentParser(
        prog="chacc",
        description="ChaCC API CLI for module scaffolding, packaging, and deployment.\n\n"
                   "Deployment requires environment variables:\n"
                   "  CHACC_DEPLOY_URL=http://your-api-server.com\n"
                   "  CHACC_DEPLOY_API_KEY=optional-api-key\n"
                   "  CHACC_DEPLOY_TIMEOUT=30"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    scaffold_parser = subparsers.add_parser("create", help="Create a new ChaCC API module.")
    scaffold_parser.add_argument("module_name", type=str, help="The name of the module to create (e.g., 'my_awesome_module').")
    scaffold_parser.add_argument("--output-dir", type=str, default="plugins",
                                 help="The directory where the new module will be created. Defaults to 'plugins/'.")

    build_parser = subparsers.add_parser("build", help="Build an ChaCC API module into an .chacc package.")
    build_parser.add_argument("module_source_dir", type=str, help="The path to the module's source directory (e.g., 'plugins/my_awesome_module').")
    build_parser.add_argument("--output-filename", type=str, default=None,
                              help="Optional: The name of the output .chacc file. Defaults to '<module_name>.chacc'.")

    deploy_parser = subparsers.add_parser("deploy", help="Deploy an .chacc module to a remote ChaCC API instance.")
    deploy_parser.add_argument("chacc_file", type=str, help="The path to the .chacc file to deploy (e.g., 'my_module.chacc').")
    deploy_parser.epilog = "Environment variables required:\n" \
                          "  CHACC_DEPLOY_URL=http://your-api-server.com\n" \
                          "  CHACC_DEPLOY_API_KEY=optional-api-key\n" \
                          "  CHACC_DEPLOY_TIMEOUT=30"

    server_parser = subparsers.add_parser("server", help="Run the ChaCC development server.")
    server_parser.add_argument("--modules-dir", type=str, default="plugins",
                              help="Directory containing ChaCC modules. Defaults to 'plugins/'.")
    server_parser.add_argument("--host", type=str, default="0.0.0.0",
                              help="Host to bind the server to. Defaults to '0.0.0.0'.")
    server_parser.add_argument("--port", type=int, default=8000,
                              help="Port to bind the server to. Defaults to 8000.")
    server_parser.add_argument("--debug", action="store_true",
                              help="Enable debug mode.")
    server_parser.add_argument("--auto-reload", action="store_true",
                              help="Enable auto-reload for development.")

    args = parser.parse_args()

    if args.command == "create":
        create_module_scaffold(args.module_name, args.output_dir)
    elif args.command == "build":
        build_module_chacc(args.module_source_dir, args.output_filename)
    elif args.command == "deploy":
        deploy_module(args.chacc_file)
    elif args.command == "server":
        # Use the existing main.py with development settings
        env = os.environ.copy()
        if args.debug:
            env["CHACC_DEBUG"] = "true"

        cmd = [
            sys.executable, "-m", "uvicorn",
            "main:app",
            "--host", args.host,
            "--port", str(args.port),
        ]

        if args.auto_reload:
            cmd.extend(["--reload", "--reload-dir", args.modules_dir])

        if args.debug:
            cmd.append("--log-level")
            cmd.append("debug")

        try:
            subprocess.run(cmd, env=env)
        except KeyboardInterrupt:
            print("\nShutting down ChaCC server...")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

