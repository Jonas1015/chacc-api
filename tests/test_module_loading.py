#!/usr/bin/env python3
"""
Simple test script to verify module loading logic
"""

import os
import sys

sys.path.append("src")

from src.constants import MODULES_INSTALLED_DIR, MODULES_LOADED_DIR


def test_module_directory_structure():
    """Test that the module directory structure is correct"""
    print("Testing module directory structure...")
    print(f"MODULES_INSTALLED_DIR: {MODULES_INSTALLED_DIR}")
    print(f"MODULES_LOADED_DIR: {MODULES_LOADED_DIR}")

    if os.path.isdir(MODULES_INSTALLED_DIR):
        print("✓ modules_installed directory exists")
        chacc_files = [f for f in os.listdir(MODULES_INSTALLED_DIR) if f.endswith(".chacc")]
        print(f"Found {len(chacc_files)} .chacc files: {chacc_files}")
    else:
        print("✗ modules_installed directory does not exist")
        return False

    if os.path.isdir(MODULES_LOADED_DIR):
        print("✓ modules_loaded directory exists")
        loaded_modules = os.listdir(MODULES_LOADED_DIR)
        print(f"Found {len(loaded_modules)} loaded modules: {loaded_modules}")
    else:
        print("✗ modules_loaded directory does not exist")
        return False

    return True


def test_module_loading_logic():
    """Test the module loading logic"""
    print("\nTesting module loading logic...")

    try:
        from src.modules import load_modules

        print("✓ Successfully imported load_modules function")
    except Exception as e:
        print(f"✗ Failed to import load_modules function: {e}")
        return False

    if load_modules.__doc__ and "MODULES_INSTALLED_DIR" in load_modules.__doc__:
        print("✓ load_modules function has correct documentation")
    else:
        print("✗ load_modules function documentation is missing or incorrect")
        return False

    return True


if __name__ == "__main__":
    print("Running module loading tests...\n")

    success = True
    success &= test_module_directory_structure()
    success &= test_module_loading_logic()

    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)
