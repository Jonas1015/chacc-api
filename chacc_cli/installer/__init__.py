"""
chacc install: install a ChaCC module from a Git URL or local directory.

Public entry point: :func:`install_module` in :mod:`chacc_cli.commands`.
The sub-modules here are split for clarity and unit-testability:

- :mod:`chacc_cli.installer.credentials` - token lookup and redaction.
- :mod:`chacc_cli.installer.source` - URL classification and git fetch.
- :mod:`chacc_cli.installer.validate` - module_meta.json validation.
- :mod:`chacc_cli.installer.paths` - destination resolution and atomic rename.
"""
