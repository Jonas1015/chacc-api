#!/usr/bin/env python3
"""
Safe server startup script that prevents auto-reloader loops.
"""

import sys
import os
import subprocess

from chacc_api.utils import LogLevels, configure_logging, BASE_DIR

logger = configure_logging(log_level=LogLevels.INFO)


def run_tests_safely():
    """Run tests in a way that doesn't trigger auto-reloader."""
    tests_path = os.path.join(BASE_DIR, "tests", "test_backbone.py")
    if not os.path.exists(tests_path):
        logger.info("No backbone tests found in CWD. Skipping tests (not a development install).")
        return True

    logger.info("Running backbone tests safely...")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", tests_path, "-v", "--tb=short", "--no-header"],
            capture_output=True,
            text=True,
            cwd=BASE_DIR,
        )

        if result.returncode == 0:
            logger.info("✅ All backbone tests passed!")
            return True
        else:
            logger.error("❌ Backbone tests failed!")
            if result.stdout:
                logger.error("Test output:")
                logger.error(result.stdout)
            if result.stderr:
                logger.error("Test errors:")
                logger.error(result.stderr)
            return False

    except Exception as e:
        logger.error(f"❌ Error running tests: {e}")
        return False


def start_server():
    """Start the server without auto-reload."""
    logger.info("Starting server without auto-reload...")

    try:
        import uvicorn

        uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
    except Exception as e:
        logger.error(f"❌ Error starting server: {e}")
        sys.exit(1)


def main():
    """Main startup sequence."""
    logger.info("=" * 60)
    logger.info("Starting ChaCC API Server (Safe Mode)")
    logger.info("=" * 60)

    if not run_tests_safely():
        logger.error("🔴 Tests failed. Server startup aborted.")
        sys.exit(1)

    logger.info("🟢 Tests passed. Starting server...")
    start_server()


if __name__ == "__main__":
    main()
