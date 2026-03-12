# ChaCC API

ChaCC API is a modular FastAPI application platform that allows you to build extensible APIs through pluggable modules.

## What is ChaCC API

ChaCC API provides a flexible foundation for building modular applications. Instead of building a monolithic API, you can create separate modules that can be installed, enabled, disabled, and updated independently.

### Key Features

- **Modular Architecture**: Build your API as independent modules that can be added or removed without modifying the core
- **Automatic Database Migrations**: Modules automatically create and update their database tables using the `@register_model` decorator
- **Dependency Management**: ChaCC resolves module dependencies automatically before loading modules using [Chacc Pip Acelerator Package](https://pypi.org/project/chacc-dependency-manager/)
- **Hot Reload Support**: Development mode supports automatic reloading when module files change
- **Module Packaging**: Build modules as `.chacc` files for easy distribution and deployment

### Use Cases

- Building extensible SaaS platforms
- Creating modular APIs with independently deployable components
- Developing reusable API modules that can be shared across projects
- Rapid prototyping with pluggable functionality

## Installation

### Prerequisites

- Python 3.10 or higher
- PostgreSQL (optional, SQLite works for development)
- Fast API understanding

### Install from PyPI

```bash
pip install chacc-api
```

### Install from Source

```bash
git clone https://github.com/jonas1015/chacc-api
cd chacc-api
pip install -e .
```

### Docker Installation

```bash
docker pull chacc-api:latest
docker run -d -p 8080:8080 chacc-api:latest
```

Or use Docker Compose:

```bash
docker-compose -f deployment/docker/docker-compose.yml up -d
```

## Command Line Interface

The `chacc` command provides tools for module development and deployment.

### Development Environment

```bash
# Create a new module
chacc create my_module

# Build a module into a .chacc package
chacc build plugins/my_module

# Deploy a module
chacc deploy mymodule.chacc

# Start development server with auto-reload
chacc run server --dev

# Start development server on custom port
chacc server --host 127.0.0.1 --port 3000
```

### Production Environment

```bash
# Start production server (runs tests first)
chacc run server
```

### Deployment Commands

```bash
# Deploy a module to a remote server
chacc deploy my_module.chacc
```

Requires environment variables:
- `CHACC_DEPLOY_URL` - URL of the remote ChaCC API server

Optional:
- `CHACC_DEPLOY_API_KEY` - API key for authentication
- `CHACC_DEPLOY_TIMEOUT` - Request timeout in seconds (default: 30)

## Learning More

### From Module Scaffolding

The easiest way to understand how modules work is to create one and explore the generated code:

```bash
chacc create my_module
ls -la plugins/my_module/
```

This creates a complete module with:
- `module_meta.json` - Module configuration
- `module/main.py` - Module entry point with `setup_plugin` function
- `module/models.py` - Database models using `@register_model`
- `module/routes.py` - API endpoints
- `module/tests/test_module.py` - Unit tests

### From Source Code

The source code is extensively documented. Key files to explore:

- `src/database.py` - Database models, `@register_model` decorator, automatic migrations
- `src/core_services.py` - BackboneContext class that provides services to modules
- `src/module_loader.py` - Module loading and lifecycle management
- `chacc_cli/commands.py` - CLI command implementations

### Authentication Module Example

For a complete example of a working module, see the authentication module in `.modules_loaded/authentication/`. It demonstrates:

- Database model definition
- API route creation
- Service registration
- Configuration handling
- Authentication utilities

## Environment Variables

### Required Variables

| Variable | Description |
|---------|-------------|
| `SECRET_KEY` | Secret key for JWT token signing. Required in production. Must be 32+ characters. |

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_ENGINE` | `sqlite` | Database type: `sqlite` or `postgresql` |
| `DATABASE_NAME` | `chaccapidb` | Database name |
| `DATABASE_USER` | `chacc` | Database username (PostgreSQL only) |
| `DATABASE_PASSWORD` | (empty) | Database password (PostgreSQL only) |
| `DATABASE_HOST` | `localhost` | Database host (PostgreSQL only) |
| `DATABASE_PORT` | `5432` | Database port (PostgreSQL only) |

### Module Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MODULES_INSTALLED_DIR` | `modules_installed` | Directory containing `.chacc` files |
| `MODULES_LOADED_DIR` | `.modules_loaded` | Directory for extracted modules |
| `PLUGINS_DIR` | `plugins` | Directory for development modules |

### Development Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVELOPMENT_MODE` | `False` | Enable development mode |
| `ENABLE_PLUGIN_HOT_RELOAD` | `True` | Auto-reload modules on file changes |
| `PLUGIN_AUTO_DISCOVERY` | `True` | Automatically discover plugins |
| `ENABLE_PLUGIN_DEPENDENCY_RESOLUTION` | `True` | Auto-resolve module dependencies |

### Migration Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MIGRATION_MODE` | `auto` | Migration mode: `auto`, `full`, or `preview` |
| `MIGRATION_BACKUP` | `False` | Create backup before migration |
| `MIGRATION_BACKUP_DIR` | `backups` | Directory for backups |
| `MIGRATION_AUTO_DROP` | `False` | Allow destructive operations |

### Redis Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_ENABLED` | `True` | Enable Redis |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database number |
| `REDIS_PASSWORD` | (none) | Redis password |

### Other Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level |

## Quick Start

### 1. Install and Run

```bash
pip install chacc-api
chacc run server --dev
```

### 2. Access the API

- API Documentation: http://localhost:8080/docs OR http://localhost:8080/redoc 
- Health Check: http://localhost:8080/health

### 3. Create a Module

```bash
chacc create my_module
```

This creates a new module in `plugins/my_module/`. Edit the files to add your functionality.

### 4. Build and Deploy

```bash
chacc build plugins/my_module
chacc deploy my_module.chacc
```

## License

Licensed under the Apache License, Version 2.0. See LICENSE file for details.
