# ChaCC API - Production Docker Image
# Builds from PyPI - for release workflow (PyPI published first, then Docker)

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r chacc && useradd -r -g chacc chacc

RUN mkdir -p /app/plugins /app/.modules_loaded

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir chacc-api

RUN chown -R chacc:chacc /app

USER chacc

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEVELOPMENT_MODE=False \
    ENABLE_PLUGIN_HOT_RELOAD=False \
    PLUGIN_AUTO_DISCOVERY=False \
    ENABLE_PLUGIN_DEPENDENCY_RESOLUTION=False

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["chacc", "run", "server"]
