"""Module test runner for ChaCC API.

Executes module-provided test suites by dynamically importing and
invoking the configured test entry point.
"""

import importlib.util
import os
import sys

from src.logger import configure_logging, get_default_log_level

chacc_logger = configure_logging(log_level=get_default_log_level())


async def run_module_tests(module_name: str, module_path: str, test_entry_point: str):
    """Run tests for a specific module."""
    chacc_logger.info(f"Running tests for module '{module_name}'...")
    try:
        module_relative_path, func_name = test_entry_point.split(":")
        test_code_dir = os.path.join(module_path, "module")
        test_main_file_path = os.path.join(test_code_dir, *module_relative_path.split(".")) + ".py"

        if not os.path.exists(test_main_file_path):
            chacc_logger.warning(
                f"Test entry point file '{test_main_file_path}' not found for module '{module_name}'."
            )
            return

        sys.path.insert(0, test_code_dir)

        spec = importlib.util.spec_from_file_location(module_relative_path, test_main_file_path)
        if spec is None:
            chacc_logger.error(f"Could not create spec for test module '{module_name}'.")
            return

        test_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(test_module)

        test_func = getattr(test_module, func_name, None)
        if not test_func or not callable(test_func):
            chacc_logger.warning(
                f"Test entry point function '{func_name}' not found or not callable for module '{module_name}'."
            )
            return

        await test_func()
        chacc_logger.info(f"Tests for module '{module_name}' passed successfully.")

    except Exception as e:  # noqa: BLE001
        chacc_logger.warning(f"Tests for module '{module_name}' failed: {e!s}")
        import traceback

        chacc_logger.warning(f"Test failure details: {traceback.format_exc()}")
    finally:
        if test_code_dir in sys.path:
            sys.path.remove(test_code_dir)
