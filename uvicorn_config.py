"""
Uvicorn configuration.
Delegates to the packaged version in chacc_api.server.uvicorn_config
"""

from chacc_api.server.uvicorn_config import config

if __name__ == "__main__":
    import uvicorn
    import os

    uvicorn.run(**config)
