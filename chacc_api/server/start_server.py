#!/usr/bin/env python3
"""
Safe server startup script that prevents auto-reloader loops.
Must NOT be run in production with development-mode settings.
"""

import os
import sys

from chacc_api.utils import configure_logging

os.environ["CHACC_DEV_MODE"] = "false"


chacc_logger = configure_logging()


def start_server(_logger=None):
    """Start the server without auto-reload, honouring CLI flags via env vars."""
    _log = _logger
    host = os.environ.get("CHACC_HOST", "0.0.0.0")
    port = int(os.environ.get("CHACC_PORT", "8085"))

    if _log is None:
        _log = configure_logging()

    _log.info(f"Starting server at {host}:{port} (reload=False)")

    try:
        import uvicorn

        uvicorn.run("main:app", host=host, port=port, reload=False)
    except Exception as e:  # noqa: BLE001
        _log.error(f"❌ Error starting server: {e}")
        sys.exit(1)


def main():
    """Main startup sequence."""
    chacc_logger.info("=" * 60)
    chacc_logger.info("Starting ChaCC API Server (Production Mode)")
    chacc_logger.info("=" * 60)
    chacc_logger.info("🟢 Starting server...")
    start_server(chacc_logger)


if __name__ == "__main__":
    main()
