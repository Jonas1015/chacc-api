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
    scaffold_parser.add_argument("--force", action="store_true",
                                 help="Overwrite existing module if it exists.")

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

    server_cmd_parser = subparsers.add_parser("server", help="Run the ChaCC development server.")
    server_cmd_parser.add_argument("--modules-dir", type=str, default="plugins",
                              help="Directory containing ChaCC modules. Defaults to 'plugins/'.")
    server_cmd_parser.add_argument("--host", type=str, default="0.0.0.0",
                              help="Host to bind the server to. Defaults to '0.0.0.0'.")
    server_cmd_parser.add_argument("--port", type=int, default=8000,
                              help="Port to bind the server to. Defaults to 8000.")
    server_cmd_parser.add_argument("--debug", action="store_true",
                              help="Enable debug mode.")
    server_cmd_parser.add_argument("--auto-reload", action="store_true",
                              help="Enable auto-reload for development.")

    run_parser = subparsers.add_parser("run", help="Run the ChaCC server.")
    run_subparsers = run_parser.add_subparsers(dest="run_subcommand", help="Run subcommands")

    run_server_parser = run_subparsers.add_parser("server", help="Run the ChaCC server.")
    run_server_parser.add_argument("--dev", action="store_true",
                          help="Run in development mode with auto-reload (uses uvicorn_config.py).")
    run_server_parser.add_argument("--debug", action="store_true",
                          help="Enable debug mode.")

    args = parser.parse_args()

    if args.command == "create":
        create_module_scaffold(args.module_name, args.output_dir, args.force)
    elif args.command == "build":
        build_module_chacc(args.module_source_dir, args.output_filename)
    elif args.command == "deploy":
        deploy_module(args.chacc_file)
    
    elif args.command == "run":
        if args.run_subcommand == "server":
            cli_dir = os.path.dirname(os.path.dirname(__file__))
            package_dir = os.path.join(cli_dir, "chacc_api", "server")
            
            if args.dev:
                env = os.environ.copy()
                if args.debug:
                    env["CHACC_DEBUG"] = "true"

                config_path = os.path.join(package_dir, "uvicorn_config.py")
                cmd = [sys.executable, config_path]
                try:
                    subprocess.run(cmd, env=env, cwd=os.getcwd())
                except KeyboardInterrupt:
                    print("\nShutting down ChaCC server...")
            else:
                server_path = os.path.join(package_dir, "start_server.py")
                cmd = [sys.executable, server_path]
                try:
                    subprocess.run(cmd, cwd=os.getcwd())
                except KeyboardInterrupt:
                    print("\nShutting down ChaCC server...")
        elif args.run_subcommand is None:
            print("Error: 'run' command requires a subcommand. Use 'chacc run server'.")
            run_parser.print_help()
            sys.exit(1)
        else:
            run_parser.print_help()
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
