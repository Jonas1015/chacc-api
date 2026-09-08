# Contributing to ChaCC API

Thank you for your interest in contributing to **ChaCC API**! Every contribution —
no matter how small — helps make this project better for everyone.

This guide will walk you through the process, from setting up your development
environment to having your pull request merged.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [How We Work](#how-we-work)
3. [Getting Started](#getting-started)
4. [Project Layout](#project-layout)
5. [Development Workflow](#development-workflow)
6. [Writing Modules](#writing-modules)
7. [Running Tests](#running-tests)
8. [Formatting & Linting](#formatting--linting)
9. [Updating the Changelog](#updating-the-changelog)
10. [Submitting a Pull Request](#submitting-a-pull-request)
11. [Style Guides](#style-guides)
12. [Asking for Help](#asking-for-help)

---

## Code of Conduct

This project adheres to a simple rule: **be respectful, be constructive.**

Harassment, discrimination, or toxic behaviour of any kind will not be tolerated.
If you experience or witness anything that makes you uncomfortable, please open a
private issue or contact the maintainer directly.

---

## How We Work

ChaCC API keeps two long-lived branches:

| Branch   | Purpose                                                               |
|----------|-----------------------------------------------------------------------|
| `main`   | Stable, production-ready code. Only tagged releases land here.       |
| `develop` | Active development. All feature work, bug fixes, and PRs target this. |

All pull requests must target `develop`. The `develop` branch is promoted to `main`
and tagged during releases.

---

## Getting Started

### 1. Fork the repository

1. Visit [https://github.com/tnet-tech/chacc-api](https://github.com/tnet-tech/chacc-api).
2. Click the **Fork** button (top-right corner).
3. Clone your fork locally:

   ```bash
   git clone https://github.com/<your-username>/chacc-api.git
   cd chacc-api
   ```

### 2. Add the upstream remote

This lets you pull the latest changes from the original repository:

```bash
git remote add upstream https://github.com/tnet-tech/chacc-api.git
```

Keep your fork up to date with:

```bash
git fetch upstream
git checkout develop
git merge upstream/develop
```

### 3. Create a virtual environment

```bash
python -m venv .venv

#Activate your environment
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate.bat       # Windows
```

### 4. Install the project in editable mode

Choose **one** of the two approaches. They are equivalent — use whichever tool
you prefer.

**Using `pip`** (built-in, no extra tools required):

```bash
pip install -e .
pip install -e .[dev]
```

**Using `uv`** (faster, recommended by the CI):

```bash
uv pip install --system -e .
uv pip install --system -e .[dev]
```

Both commands install the `chacc` CLI, the backbone itself, and the development
dependencies (Ruff, MyPy, pytest).

### 5. Configure environment variables

Create a `.env` file at the root of the project. You can copy and adapt the
template below:

```bash
cp deployment/standalone/.env.example .env   # if a template exists, otherwise:
touch .env
```

Minimum required for local development:

```env
# ── Security
SECRET_KEY=dev-secret-key-change-in-production

# ── Database (SQLite works out of the box)
DATABASE_ENGINE=sqlite

# ── Development
ENABLE_PLUGIN_HOT_RELOAD=True
PLUGIN_AUTO_DISCOVERY=True
ENABLE_PLUGIN_DEPENDENCY_RESOLUTION=True

# ── Redis (optional; disabled by default)
REDIS_ENABLED=false

# ── CORS
CORS_ALLOWED_ORIGINS=*
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=*
CORS_ALLOW_HEADERS=*
```

> **Note:** Never commit `.env` to version control. It is already listed in
> `.gitignore`.

### 6. Verify your setup

```bash
# Run the CLI
chacc --help

# Run the linters (should report no issues on a fresh checkout)
ruff format --check .
ruff check .

# Run the test suite
pytest tests/ -v
```

If all of the above pass, you are ready to contribute.

---

## Project Layout

Here is a map of every significant directory and file so you can find your way
around quickly.

```
chacc-api/
├── main.py                    # Self-contained entry script (runs uvicorn on port 8085)
├── start_server.py            # Production entry script (no auto-reload)
│
├── src/                       # ═══ Core internal infrastructure ═══
│   ├── __init__.py
│   ├── constants.py           # All environment variables, paths, log-format strings
│   ├── logger.py              # Colored logging setup (LogLevels, configure_logging)
│   ├── database.py            # SQLAlchemy engine, BaseModel, register_model decorator, get_db
│   ├── core_services.py       # BackboneContext — shared services given to every module
│   ├── health.py              # /health, /health/ready, /health/live endpoints
│   ├── modules.py             # REST routes: install / list / enable / disable / uninstall modules
│   ├── rate_limiter.py        # SlowAPI rate-limiting setup
│   ├── redis_service.py       # Async Redis client wrapper
│   ├── chacc_dependency_manager.py  # ChaCC-specific integration with chacc-dependency-manager
│   │
│   ├── module_loader/         # Production module loading pipeline
│   │   ├── loader.py          # Orchestrates: scan → resolve deps → extract → migrate → mount
│   │   ├── discovery.py       # Recursive Python-file import for @register_model discovery
│   │   ├── archive.py         # .chacc file inspection, mtime-based re-unzip decisions
│   │   └── metadata.py        # DB↔filesystem sync: remove records for deleted modules
│   │
│   ├── migration/             # Database migration subsystem
│   │   ├── runner.py          # MigrationRunner — auto/full/preview modes, backup, rollback
│   │   ├── tracker.py         # chacc_migration_log table — applied-migration registry
│   │   └── backup.py          # pg_dump / SQLite-file copy — backup and restore
│   │
│   ├── plugin_loader.py       # Dev-mode module loader (plugins/ dir, two-phase load)
│   └── env_validator.py       # Startup environment checks (SECRET_KEY, DB, production guards)
│
├── chacc_cli/                 # ═══ The `chacc` CLI ═══
│   ├── __main__.py            # argparse wiring + subprocess server launch
│   ├── commands.py            # create / build / deploy implementations
│   └── templates/             # Module scaffolding templates (8 *.template files)
│
├── chacc_api/                 # ═══ Public SDK package for module developers ═══
│   ├── __init__.py            # Re-exports BackboneContext, RedisService, etc.
│   └── server/
│       ├── main.py            # FastAPI app, lifespan orchestrator, CORS, rate-limit middleware
│       ├── start_server.py    # Production uvicorn runner (reload=False)
│       └── uvicorn_config.py  # Dev-mode uvicorn runner (--dev flag, reload=True)
│
├── plugins/                   # ═══ Development plugins ═══
│   ├── authentication/        # Official Authentication module (reference implementation)
│   ├── menu/                  # Menu module example
│   └── sample/                # Minimal sample module
│
├── modules_installed/         # .chacc files land here (auto-created)
├── .modules_loaded/           # Extracted production modules (auto-created)
├── tests/                     # Backbone-level integration / unit tests
│
├── deployment/                # Docker Compose + standalone deployment scripts
├── plans/                     # Internal design documents
│
├── pyproject.toml             # Project metadata, dependencies, tool configs
├── requirements.txt           # Backbone dependencies
├── requirements-dev.txt       # Dev overlay: pytest, ruff, ...
├── MANIFEST.in
│
├── .github/workflows/
│   ├── ci.yml                 # CI: lint → typecheck → test → build
│   └── release.yml            # CD: PyPI publish + Docker Hub push on tag
│
└── CONTRIBUTING.md            # ← you are here
```

---

## Development Workflow

### Branch naming

Use one of these prefixes so reviewers know the intent:

| Prefix     | Example                               | When to use                          |
|------------|---------------------------------------|--------------------------------------|
| `feat/`    | `feat/module-search-api`              | A new feature                        |
| `fix/`     | `fix/migration-backup-permissions`    | A bug fix                            |
| `refactor/`| `refactor/simplify-module-loader`     | Code change that neither adds nor fixes |
| `docs/`    | `docs/update-readme-env-vars`         | Documentation only                   |
| `chore/`   | `chore/update-gitignore`              | Housekeeping (CI, deps, config…)     |

We allow the use of as well `git flow` which will do pretty much the same with different naming conventions for branches.

Always **branch from `develop`**:

```bash
git checkout develop
git pull upstream develop
git checkout -b fix/migration-backup-permissions
```

### Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Examples:

```
feat(modules): add enable/disable endpoint for module management
fix(migration): restore backup when schema migration fails
docs(readme): document REDIS_ENABLED default value
refactor(db): remove stale alembic imports from database.py
```

The `<type>` must be one of:

| Type     | Meaning                                                |
|----------|--------------------------------------------------------|
| `feat`   | A new feature (triggers a minor version bump on release) |
| `fix`    | A bug fix (triggers a patch version bump)              |
| `refactor`| Code change that fixes neither a bug nor a feature    |
| `docs`   | Documentation-only change                              |
| `test`   | Adding / updating tests                                |
| `chore`  | Build process, CI, dependency updates                  |
| `perf`   | Performance improvement                                |
| `style`  | Formatting, whitespace, no logic change                |
| `ci`     | CI / CD workflow changes                               |

---

## Writing Modules

ChaCC API's superpower is its module system. If your contribution involves a new
feature, you should consider packaging it as a module.

### Two module modes

| Mode        | Directory           | Use case                           |
|-------------|---------------------|------------------------------------|
| **Dev mode** | `plugins/`          | Iterative local development        |
| **Prod mode** | `.modules_loaded/`  | Deployed `.chacc` archives         |

> Note: These directories are configurable. Read the README.md file to change the default values.

For local development, simply create your module inside `plugins/` and turn on
`ENABLE_PLUGIN_HOT_RELOAD=true`. The backbone will re-discover and re-load it
automatically whenever a file changes.

### Scaffold a new module

```bash
chacc create my_module
# Creates: plugins/my_module/my_module_src/  +  module_meta.json  +  requirements.txt
```

### Module file structure

```
my_module/
├── module_meta.json          # Name, version, entry point, dependencies, route prefix
├── requirements.txt          # Module-specific Python deps (installed before load)
├── README.md
└── my_module_src/
    ├── __init__.py
    ├── main.py               # setup_plugin(backbone_context) → APIRouter (entry point)
    ├── models.py             # SQLAlchemy models decorated with @register_model
    ├── routes.py             # FastAPI route definitions
    ├── context_factory.py    # Optional: inject external services into BackboneContext
    └── tests/
        ├── __init__.py
        └── test_module.py    # Module self-tests
```

### Key module concepts

#### `@register_model`

Any SQLAlchemy model decorated with `@register_model` (from `chacc_api.database`)
is automatically discovered by the backbone at startup and included in the
migration pipeline. No manual table-creation code is required.

```python
from chacc_api.database import ChaCCBaseModel, register_model


@register_model
class Todo(ChaCCBaseModel):
    __tablename__ = "todos"

    title = Column(String, nullable=False)
    done = Column(Boolean, default=False, nullable=False)
```

#### `BackboneContext`

Every module's `setup_plugin(backbone_context)` function receives a
`BackboneContext` instance that gives you access to:

```python
# The FastAPI app (to register routes manually if needed)
backbone_context.app

# Rate limiter
backbone_context.limiter

# Logger
backbone_context.logger

# Database session factory (usable as FastAPI Depends)
from fastapi import Depends

db: Session = Depends(backbone_context.get_db)

# Register a named service for other modules to consume
backbone_context.register_service("my_service", my_callable)

# Retrieve a service registered by another module
service = backbone_context.get_service("auth_somewhere")
```

#### Module metadata (`module_meta.json`)

Fields checked by the backbone at load time:

```json
{
  "name":              "my_module",
  "display_name":      "My Awesome Module",
  "version":           "0.1.0",
  "author":            "Your Name",
  "description":       "Short description of what this module does.",
  "entry_point":       "my_module_src.main:setup_plugin",
  "test_entry_point":  "my_module_src.tests.test_module:run_module_tests",
  "base_path_prefix":  "/my-module",
  "dependencies_file": "requirements.txt",
  "required_chacc_version": ">=1.0.0",
  "license":           "MIT",
  "tags":              ["productivity"]
}
```

The `entry_point` field is **required** — the backbone uses it to locate and
call your `setup_plugin` function. The `chacc create` tool scaffolds it for you;
just make sure it matches your actual file layout.

#### Module loading order

The backbone loads modules in three deliberate phases to avoid race conditions:

```
Phase 1 — Model Discovery
  All Python files in the module are scanned first.
  @register_model-decorated classes add their tables to SQLAlchemy metadata.

Phase 2 — Migration
  Alembic compares metadata against the live database and applies any missing
  DDL.  Only safe (non-destructive) operations run in AUTO mode.

Phase 3 — Setup
  Each module's setup_plugin() is called.  This is where routes, services, and
  other runtime wiring happens.
```

## Running the Backbone

### Development mode (local module iteration)

Starts the server with `--dev`, which runs in development mode and uses the
`uvicorn_config.py` reload configuration. Hot-reload is active when
`ENABLE_PLUGIN_HOT_RELOAD=true`.

```bash
chacc run server --dev
# URL: http://localhost:8085
# Docs: http://localhost:8085/docs
# Health: http://localhost:8085/health
```

Custom host / port:

```bash
chacc run server --dev --host 127.0.0.1 --port 3000
```

### Production mode

Starts the server **without** auto-reload. Plugins are loaded from
`.modules_loaded/` (the extracted `.chacc` archives).

```bash
chacc run server
# URL: http://localhost:8085  (varies by deployment)
```

### Docker

```bash
docker-compose -f deployment/docker/docker-compose.yml up
```

Docker environment variables are defined in
`deployment/docker/.env.example` before you start the stack.

---

## Running Tests

### Backbone tests

```bash
pytest tests/ -v --tb=short
```

Run a single test file:

```bash
pytest tests/test_health.py -v
```

Run with coverage when `pytest-cov` is installed:

```bash
pytest tests/ --cov=src --cov=chacc_cli --cov-report=term-missing
```

### Module self-tests

Each scaffolded module ships with a `run_tests.py` runner:

```bash
cd plugins/my_module
python my_module_src/run_tests.py setup   # first run: creates temp DB
python my_module_src/run_tests.py test
```

---

## Formatting & Linting

CI runs three tools and will fail if any of them report issues. Fix them
**before** pushing:

```bash
# Auto-format source files
ruff format .

# Fix auto-fixable lint issues
ruff check --fix .

# Show remaining (non-auto-fixable) lint issues
ruff check .

# Type-check (CI runs with --ignore-missing-imports to tolerate optional deps)
mypy src chacc_api chacc_cli --ignore-missing-imports
```

> `mypy` and some `ruff` warnings are ignored in CI (`|| true`). They are still
> worth addressing but will not block your PR.

### Configuration

| Tool       | Config location                              | Line length |
|------------|----------------------------------------------|-------------|
| Ruff       | `pyproject.toml` → `[tool.ruff]`            | 100         |
| MyPy       | `pyproject.toml` → `[tool.mypy]`            | —           |

---

## Updating the Changelog

Every **user-facing** change must have a changelog entry.

1. Open `chacc-docs/docs/changelog.md`.
2. Add your entry under a new version heading, one of:

   - **`## [Unreleased]`** — for the next planned version.
   - **`## [patch] - YYYY-MM-DD`** — for a hotfix.
   - **`## [major.minor.patch] - YYYY-MM-DD`** — for a regular release.

3. Use the existing `### Added / Changed / Deprecated / Fixed / Removed`
   sections. Omit sections that are empty.
4. Write in the imperative mood, referencing the affected files when helpful:

   ```markdown
   ### Fixed

   - Fix race condition in `plugin_loader.py` where `setup_plugin()` was called
     before `run_migration()` completed.
   ```

Do **not** move existing entries around. Append new entries only.

---

## Submitting a Pull Request

### Before you push

```bash
# Update your branch from upstream
git fetch upstream
git merge upstream/develop

# Run all checks locally
ruff format --check .
ruff check .
mypy src chacc_api chacc_cli --ignore-missing-imports || true
pytest tests/ -v --tb=short

# Stage your changes
git add .

# Write a conventional-commit message
git commit -m "feat(modules): add bulk-enable endpoint for module management"

# Push to your fork
git push origin feat/module-bulk-enable
```

### Creating the PR

1. Open **https://github.com/tnet-tech/chacc-api/compare/develop…\<your-branch\>**
2. Confirm the **base branch** is `develop`.
3. Fill in the PR template:
   - **What does this change?** A clear, concise description of the problem solved
     or feature added.
   - **How has this been tested?** Steps to reproduce the scenario before and after
     the change.
   - **Breaking changes?** If yes, describe the migration path.
   - **Related issues / discussions:** Link them with keywords (`Closes #123`,
     `Fixes #45`, `See also #78`).
4. Enable **"Allow edits from maintainers"** so a reviewer can push quick fixes.
5. Open the PR.

### What happens next

1. **CI runs automatically** (lint, typecheck, tests, build).
   Fix any failures before responding to review comments.
2. A **maintainer will review** your code. Expect a review within a few days.
   Address every comment — even if you disagree, reply with your reasoning.
3. Once approved, a maintainer will **merge using "Squash and merge"**.
   The resulting commit message **must be a conventional-commit message**.

### Size guidelines

- Keep PRs focused. If your change touches more than ~3 files, consider splitting.
- Large refactors are welcome — open a [Discussion](https://github.com/tnet-tech/chacc-api/discussions)
  first so the community can weigh in before you invest time.

---

## Style Guides

### Python

- **Line length:** 100 characters (Ruff is configured for this).
- **Docstrings:** Google-style docstrings on every public function / class.
- **Type hints:** Required for all public signatures. Use `Optional[X]` instead
  of bare `None` or `Union[X, None]`.
- **Naming:**
  - `snake_case` for functions and variables.
  - `PascalCase` for classes.
  - `SCREAMING_SNAKE_CASE` for module-level constants.
- **Imports:** Standard library → third-party → local, one blank line between groups.
  No `from X import *` anywhere.
- **Strings:** Use double-quoted strings throughout (`"hello"`, not `'hello'`).

### Documentation and comments

- Keep explanations in the **README.md** or docstrings, not in code comments.
- Every `### Added` / `### Fixed` entry in the CHANGELOG must reference a PR.

### Module scaffolding templates

When you change how a newly scaffolded module looks, update the matching file
in `chacc_cli/templates/` — the old `.chacc` format won't upgrade automatically,
so a clean scaffold is the only way new projects get your changes.

---

## Asking for Help

We are happy to help! Choose the right channel:

| You want to…                                               | Go to…                                             |
|------------------------------------------------------------|----------------------------------------------------|
| Report a bug / unexpected behaviour                        | [Issues → Bug Report](https://github.com/tnet-tech/chacc-api/issues/new/choose) |
| Suggest a new feature                                      | [Issues → Feature Request](https://github.com/tnet-tech/chacc-api/issues/new/choose) |
| Ask a question or brainstorm an approach                   | [Discussions](https://github.com/tnet-tech/chacc-api/discussions) |
| Chat in real time                                          | Reach out to [**Jonas**](https://github.com/jonas1015) directly                    |

When opening an issue, use the templates provided. The more context you give
(OS, Python version, full error traceback, `.env` — redacted), the faster we
can help.

---

## Security

If you discover a security vulnerability, **do not open a public issue**. Please
contact the maintainer privately at [jonasgeorge1015@gmail.com](mailto:jonasgeorge1015@gmail.com).

In general:

- **Never** commit API keys, JWT secrets, database passwords, or any other
  credentials. Use `.env` and environment variables instead.
- The CI pipeline does **not** scan for secrets — you are responsible for
  catching them before you push.

---

## License

By contributing to ChaCC API you agree that your contributions will be
licensed under the **Apache License, Version 2.0**.

See [LICENSE](LICENSE) for full details.

---

Thank you again for contributing. Your time, ideas, and code make ChaCC API
better.
