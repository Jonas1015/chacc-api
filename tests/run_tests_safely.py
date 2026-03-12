#!/usr/bin/env python3
"""
Safe test runner that avoids auto-reloader issues.

Usage:
    python tests/run_tests_safely.py                    # Run all tests
    python tests/run_tests_safely.py --backbone-only    # Run only backbone tests
    python tests/run_tests_safely.py --no-cleanup       # Don't clean up test modules
"""

import subprocess
import sys
import os
import shutil
import argparse


def cleanup_test_modules():
    """Clean up test modules created during testing."""
    test_module_path = ".modules_loaded/test_module"
    if os.path.exists(test_module_path):
        shutil.rmtree(test_module_path)
        print(f"✓ Cleaned up test module: {test_module_path}")


def run_tests(backbone_only=False, no_cleanup=False):
    """Run tests safely."""
    print("🧪 Running tests safely...")

    # Clean up any existing test modules first
    if not no_cleanup:
        cleanup_test_modules()

    try:
        if backbone_only:
            print("📋 Running backbone tests only...")
            cmd = [sys.executable, "-m", "pytest", "tests/test_backbone.py", "-v"]
        else:
            print("📋 Running all tests...")
            cmd = [sys.executable, "-m", "pytest", "tests/", "-v"]

        result = subprocess.run(cmd, cwd=".")

        if result.returncode == 0:
            print("✅ All tests passed!")
        else:
            print(f"❌ Tests failed with exit code: {result.returncode}")

        return result.returncode

    finally:
        # Clean up test modules after running tests
        if not no_cleanup:
            cleanup_test_modules()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Safe test runner")
    parser.add_argument("--backbone-only", action="store_true", help="Run only backbone tests")
    parser.add_argument(
        "--no-cleanup", action="store_true", help="Don't clean up test modules after running"
    )

    args = parser.parse_args()

    exit_code = run_tests(backbone_only=args.backbone_only, no_cleanup=args.no_cleanup)
    sys.exit(exit_code)
