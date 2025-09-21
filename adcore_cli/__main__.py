"""
AdCore CLI - Command Line Interface for AdCore API module management.
"""
import argparse

from .commands import create_module_scaffold, build_module_adcore, deploy_module


def main():
    """
    Main CLI entry point.
    """
    parser = argparse.ArgumentParser(
        prog="adcore",
        description="AdCore API CLI for module scaffolding, packaging, and deployment.\n\n"
                   "Deployment requires environment variables:\n"
                   "  ADCORE_DEPLOY_URL=http://your-api-server.com\n"
                   "  ADCORE_DEPLOY_API_KEY=optional-api-key\n"
                   "  ADCORE_DEPLOY_TIMEOUT=30"
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

    deploy_parser = subparsers.add_parser("deploy", help="Deploy an .adcore module to a remote AdCore API instance.")
    deploy_parser.add_argument("adcore_file", type=str, help="The path to the .adcore file to deploy (e.g., 'my_module.adcore').")
    deploy_parser.epilog = "Environment variables required:\n" \
                          "  ADCORE_DEPLOY_URL=http://your-api-server.com\n" \
                          "  ADCORE_DEPLOY_API_KEY=optional-api-key\n" \
                          "  ADCORE_DEPLOY_TIMEOUT=30"

    args = parser.parse_args()

    if args.command == "create":
        create_module_scaffold(args.module_name, args.output_dir)
    elif args.command == "build":
        build_module_adcore(args.module_source_dir, args.output_filename)
    elif args.command == "deploy":
        deploy_module(args.adcore_file)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

