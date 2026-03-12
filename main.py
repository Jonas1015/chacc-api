"""
ChaCC API main entry point.
Delegates to the packaged version in chacc_api.server.main
"""

from chacc_api.server.main import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
