"""
ChaCC CLI - Command Line Interface for ChaCC API module management.
"""

import argparse
import os
import subprocess
import sys

_RED = "\033[31m"
_YELLOW = "\033[33m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _color(text: str, ansi: str) -> str:
    return f"{ansi}{text}{_RESET}" if sys.stdout.isatty() else text


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
        "  CHACC_DEPLOY_TIMEOUT=30",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    scaffold_parser = subparsers.add_parser("create", help="Create a new ChaCC API module.")
    scaffold_parser.add_argument(
        "module_name",
        type=str,
        help="The name of the module to create (e.g., 'my_awesome_module').",
    )
    scaffold_parser.add_argument(
        "--output-dir",
        type=str,
        default="plugins",
        help="The directory where the new module will be created. Defaults to 'plugins/'.",
    )
    scaffold_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing module if it exists."
    )

    build_parser = subparsers.add_parser(
        "build", help="Build an ChaCC API module into an .chacc package."
    )
    build_parser.add_argument(
        "module_source_dir",
        type=str,
        help="The path to the module's source directory (e.g., 'plugins/my_awesome_module').",
    )
    build_parser.add_argument(
        "--output-filename",
        type=str,
        default=None,
        help="Optional: The name of the output .chacc file. Defaults to '<module_name>.chacc'.",
    )

    from .commands import build_install_parser

    build_install_parser(subparsers)

    deploy_parser = subparsers.add_parser(
        "deploy", help="Deploy an .chacc module to a remote ChaCC API instance."
    )
    deploy_parser.add_argument(
        "chacc_file",
        type=str,
        help="The path to the .chacc file to deploy (e.g., 'my_module.chacc').",
    )
    deploy_parser.epilog = (
        "Environment variables required:\n"
        "  CHACC_DEPLOY_URL=http://your-api-server.com\n"
        "  CHACC_DEPLOY_API_KEY=optional-api-key\n"
        "  CHACC_DEPLOY_TIMEOUT=30"
    )

    server_cmd_parser = subparsers.add_parser("server", help="Run the ChaCC development server.")
    server_cmd_parser.add_argument(
        "--modules-dir",
        type=str,
        default="plugins",
        help="Directory containing ChaCC modules. Defaults to 'plugins/'.",
    )
    server_cmd_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to. Defaults to '0.0.0.0'.",
    )
    server_cmd_parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind the server to. Defaults to 8000."
    )
    server_cmd_parser.add_argument("--debug", action="store_true", help="Enable debug mode.")
    server_cmd_parser.add_argument(
        "--auto-reload", action="store_true", help="Enable auto-reload for development."
    )

    run_parser = subparsers.add_parser("run", help="Run the ChaCC server.")
    run_subparsers = run_parser.add_subparsers(dest="run_subcommand", help="Run subcommands")

    run_server_parser = run_subparsers.add_parser("server", help="Run the ChaCC server.")
    run_server_parser.add_argument(
        "--dev",
        action="store_true",
        help="Run in development mode with auto-reload (uses uvicorn_config.py).",
    )
    run_server_parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the server to. Defaults to '0.0.0.0'.",
    )
    run_server_parser.add_argument(
        "--port", type=int, default=8085, help="Port to bind the server to. Defaults to 8085."
    )
    run_server_parser.add_argument("--debug", action="store_true", help="Enable debug mode.")

    run_server_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed logs (DEBUG level) for this invocation.",
    )

    args = parser.parse_args()

    from .commands import (
        build_install_parser,
        build_module_chacc,
        create_module_scaffold,
        deploy_module,
        install_module,
    )

    if args.command == "create":
        create_module_scaffold(args.module_name, args.output_dir, args.force)
    elif args.command == "install":
        from chacc_cli.installer.paths import PathError
        from chacc_cli.installer.source import SourceError
        from chacc_cli.installer.validate import ValidationError

        try:
            install_module(
                source=args.source,
                ref=args.ref,
                dev=args.dev,
                force=args.force,
                depth=args.depth,
                full=args.full,
                token_env=args.token_env,
                quiet=args.quiet,
            )
        except (SourceError, ValidationError, PathError) as exc:
            # The progress stepper has already printed [FAIL] with the message.
            msg = _color(f"\nInstall failed: {exc}", _BOLD + _RED)
            print(msg)
            sys.exit(1)
        else:
            sys.exit(0)
    elif args.command == "build":
        build_module_chacc(args.module_source_dir, args.output_filename)
    elif args.command == "deploy":
        deploy_module(args.chacc_file)

    elif args.command == "run":
        if args.run_subcommand == "server":
            from pathlib import Path

            cli_dir = Path(__file__).resolve().parent.parent
            project_root = cli_dir
            package_dir = cli_dir / "chacc_api" / "server"

            env = os.environ.copy()

            env["PYTHONPATH"] = str(str(project_root) + os.pathsep + env.get("PYTHONPATH", ""))

            env["CHACC_HOST"] = args.host
            env["CHACC_PORT"] = str(args.port)

            if args.verbose:
                env["CHACC_VERBOSE"] = "true"
            else:
                env.pop("CHACC_VERBOSE", None)

            if args.dev:
                env["CHACC_DEV_MODE"] = "true"

                if args.debug:
                    env["CHACC_DEBUG"] = "true"
                config_path = package_dir / "uvicorn_config.py"
                cmd = [sys.executable, str(config_path)]
            else:
                server_path = package_dir / "start_server.py"
                cmd = [sys.executable, str(server_path)]

            try:
                subprocess.run(cmd, env=env, cwd=os.getcwd(), check=False)
            except KeyboardInterrupt:
                msg = _color("\nShutting down ChaCC server...", _YELLOW)
                print(msg)
            sys.exit(0)
        elif args.run_subcommand is None:
            msg = _color("Error: 'run' command requires a subcommand. Use 'chacc run server'.", _YELLOW)
            print(msg)
            run_parser.print_help()
            sys.exit(1)
        else:
            run_parser.print_help()
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
