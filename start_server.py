#!/usr/bin/env python3
"""
Server startup script.
Delegates to the packaged version in chacc_api.server.start_server
"""

from chacc_api.server.start_server import main

if __name__ == "__main__":
    main()
