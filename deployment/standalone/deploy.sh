#!/bin/bash
set -e

# ChaCC API - Standalone Deployment Script
# This script installs chacc-api on a Linux server

# Configuration
APP_NAME="chacc-api"
APP_DIR="/opt/chacc-api"
APP_USER="chacc-api"
PORT=8080

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root"
    exit 1
fi

log_info "Starting $APP_NAME deployment..."

# Step 1: Create user
log_info "Creating user..."
id -u $APP_USER &>/dev/null || useradd -r -s /bin/false -d $APP_DIR $APP_USER

# Step 3: Install Python if needed
if ! command -v python3 &> /dev/null; then
    log_info "Installing Python..."
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y python3 python3-venv python3-pip curl openssl
    elif command -v yum &> /dev/null; then
        yum install -y python3 python3-venv python3-pip curl openssl
    elif command -v apk &> /dev/null; then
        apk add --no-cache python3 py3-venv py3-pip curl openssl
    else
        log_error "Cannot install Python. Please install Python 3.10+ manually."
        exit 1
    fi
fi

log_info "Setting up virtual environment..."
python3 -m venv $APP_DIR/.venv

log_info "Installing $APP_NAME from PyPI..."
$APP_DIR/.venv/bin/pip install --upgrade pip
$APP_DIR/.venv/bin/pip install chacc-api

log_info "Creating environment configuration..."
cat > $APP_DIR/.env <<EOF
DEVELOPMENT_MODE=False
DATABASE_ENGINE=postgresql
DATABASE_HOST=localhost
DATABASE_NAME=chacc
DATABASE_USER=chacc
DATABASE_PASSWORD=changeme
SECRET_KEY=$(openssl rand -hex 32)
ENABLE_PLUGIN_HOT_RELOAD=False
PLUGIN_AUTO_DISCOVERY=False
ENABLE_PLUGIN_DEPENDENCY_RESOLUTION=False
NO_RELOAD=True
LOG_LEVEL=INFO
EOF

chown -R $APP_USER:$APP_USER $APP_DIR
chmod 700 $APP_DIR/.env

log_info "Installing systemd service..."
cat > /etc/systemd/system/${APP_NAME}.service <<EOF
[Unit]
Description=ChaCC API - Modular FastAPI Platform
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
Environment=DEVELOPMENT_MODE=False
ExecStart=$APP_DIR/venv/bin/chacc server --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR/plugins $APP_DIR/.modules_loaded

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$APP_NAME

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $APP_NAME

log_info "Starting $APP_NAME..."
systemctl start $APP_NAME

if systemctl is-active --quiet $APP_NAME; then
    log_info "Installation complete!"
    log_info "Access the API at http://localhost:$PORT"
    log_info "Health check: http://localhost:$PORT/health"
else
    log_error "Service failed to start. Check logs with: journalctl -u $APP_NAME -f"
    exit 1
fi
