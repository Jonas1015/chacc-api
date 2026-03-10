# ChaCC API - Production Docker Image
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip wheel

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runner

RUN groupadd -r chacc && useradd -r -g chacc chacc

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY --chown=chacc:chacc . /app/

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

CMD ["python", "start_server.py"]
