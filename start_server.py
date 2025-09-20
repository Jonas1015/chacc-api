#!/usr/bin/env python3
"""
Safe server startup script that prevents auto-reloader loops.
"""
import os
import sys
import subprocess
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(level)s - %(message)s')
logger = logging.getLogger(__name__)

def run_tests_safely():
    """Run tests in a way that doesn't trigger auto-reloader."""
    logger.info("Running backbone tests safely...")

    try:
        # Only run backbone tests automatically (exclude module management tests)
        result = subprocess.run([
            sys.executable, "-m", "pytest", "tests/test_backbone.py",
            "-v", "--tb=short", "--no-header"
        ], capture_output=True, text=True, cwd=".")

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
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8080,
            reload=False  # Explicitly disable reload
        )
    except Exception as e:
        logger.error(f"❌ Error starting server: {e}")
        sys.exit(1)

def main():
    """Main startup sequence."""
    logger.info("🚀 Starting AdCore API Server (Safe Mode)")

    # Step 1: Run tests
    if not run_tests_safely():
        logger.error("❌ Tests failed. Server startup aborted.")
        sys.exit(1)

    # Step 2: Start server
    logger.info("✅ Tests passed. Starting server...")
    start_server()

if __name__ == "__main__":
    main()