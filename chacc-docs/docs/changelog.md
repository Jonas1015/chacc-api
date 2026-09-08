# Changelog

## 1.0.0-b5


**Update now:**
> PyPi Package:
```bash
pip install --upgrade chacc-api
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-b5
```

### Added

- **`chacc install` command** – Install any ChaCC module from a Git repository or local folder in one step. You can use a full URL, an SSH address, or the short form like `TNet-Tech/chacc_outbound`. Use `--dev` to copy the module into the plugins directory for active development, or leave it off to build a production `.chacc` archive automatically. Supports `--ref` for branches, tags, and commits, `--force` to overwrite existing modules, and private repositories via `GITHUB_TOKEN`, `GITLAB_TOKEN`, `BITBUCKET_TOKEN`, or `CHACC_GIT_TOKEN`. Includes a friendly step-by-step progress display with colored status markers so you always know what is happening. See the [CLI install guide](cli.md#install-a-module) for the full reference.


- **Async database support for modules** – Modules can now connect to the database without blocking the server. When you create a new module with `chacc create`, the generated code includes everything needed to run database queries asynchronously.
- **Chacc Outbound module** – A new official module for sending emails, SMS, and other messages. It includes automatic retries, delivery status tracking, and a pluggable adapter system (SMTP and console adapters included out of the box). See the [Chacc Outbound docs](official-modules/outbound.md) for setup, REST API, and how to write custom adapters.

### Fixed

- **Database connections leaking in generated code** – The scaffolded `get_db` dependency now properly closes the database session after each request, preventing connection leaks over time.
- **Docker startup issues** – Fixed a problem where the database failed to migrate during startup in production mode.
- **Docker permission errors** – Fixed a permission issue that prevented the dependency resolver from writing its cache.
- **PostgreSQL enum migration crashes** – Fixed a crash when changing a column from one enum type to another. ChaCC now handles the conversion smoothly through an intermediate step, so enum migrations work without manual SQL.
- **Module loading crashes** – Fixed a crash that occurred when some plugins loaded their models in certain orders. The startup process is now more forgiving and handles edge cases gracefully.
- **Migration crashes** – Improved how ChaCC reads migration plans from Alembic, eliminating rare crashes during database updates.
- **Code cleanup** – Removed unreachable error handling code and eliminated an unnecessary global directory change during archive building, making the install flow easier to follow and safer in multi-threaded environments.

### Changed

- **Module name validation enforced in build path** – `chacc build` and the internal build step of `chacc install` now both normalize module names the same way. This ensures that module names behave consistently whether you are building a package or installing one.

---

## 1.0.0-b4.5


**Update now:**
> PyPi Package:
```bash
pip install chacc-api==1.0.0-b4.post3
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-b4.5
```

### Changed

- **Module naming convention** – Module directories now use underscores instead of hyphens (for example, `chacc_file_manager` instead of `chacc-file-manager`) to match Python naming standards. This makes the import system work consistently across the module loading pipeline. If you have existing modules, rename your module directories and update the `name` field in `module_meta.json`.
- **Code formatting tool** – Switched from Black to Ruff formatter. All code is now formatted using `ruff format` with the same 100-character line length. You can run `ruff format .` to auto-format and `ruff format --check .` to verify formatting.
- **Documentation workflow** – Documentation Docker images are now built and pushed automatically when a release is published. Manual documentation builds can be triggered by including "build docs" in a commit message on the develop or main branch, or via the workflow_dispatch workflow in GitHub Actions.
- **Changelog location** – The changelog has been moved to `chacc-docs/docs/changelog.md`. The root `CHANGELOG.md` file has been removed. See the [changelog on chacc.dev](https://chacc.dev/changelog) for the complete history.
- **ChaCC Theme Applied in Swagger UI and ReDoc** - Added custom ChaCC theme styling to Swagger UI and ReDoc interfaces for consistent branding.

### Added

- **Manual Docker workflows** – Added separate workflows for manual Docker builds:
  - `.github/workflows/docker-manual.yml` – Build and push main Docker image on demand
  - `.github/workflows/docker-docs-manual.yml` – Build and push documentation Docker image on demand


### Fixed

- **Module loading duplicate class registration** – Fixed "Multiple classes found for path" SQLAlchemy errors when loading modules by refactoring the discovery and setup phases to use a consistent import mechanism. Both phases now use the same module objects from `sys.modules`, eliminating duplicate SQLAlchemy declarative registry entries.

- **AutoIncrement Indexed ID** – Fixed auto-increment behavior for indexed primary keys from `ChaCCBaseModel`.

> **AutoIncrement Indexed ID** is a breaking change. Ensure to backup your database before upgrading.


---

## 1.0.0-b4.2

**Update now:**
> PyPi Package:
```bash
pip install chacc-api==1.0.0-b4.post2
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-b4.2
```

**Beta4.2 fixes a critical startup crash, resolves the audit-schema chicken-and-egg problem, and cleans up model discovery. We have brought you better landing page. If you've had issues with module loading or SQLite table detection, this release is for you.**

---

### Added

- **Smarter model discovery** – Modules now load their dependencies in the correct order automatically, even when imports are nested.
- **Better migration safety** – New dependency resolver and operation executor handle PostgreSQL enum conflicts and ensure migrations run correctly across SQLite and PostgreSQL.
- **Comprehensive test coverage** – Tests now cover migration ordering, safe operation filtering, schema reflection, and model discovery.
- **HTML welcome page** – Adds a dark-mode HTML welcome page with links to Swagger UI, ReDoc, and chacc.dev documentation, replacing the raw JSON root endpoint.


### Fixed

- **Startup crash** – Fixed "Multiple classes found for some modules" crash that occurred when plugin discovery was disabled in development mode.
- **Double model registration** – Removed the old `_model_registry` and now rely exclusively on SQLAlchemy's declarative metadata. No more duplicate table errors.
- **SQLite table detection** – Fixed a bug where `table_exists()` returned incorrect results for existing tables.
- **Audit schema chicken-and-egg** – Split schema initialization into two passes (before and after entry points) so audit fields are applied correctly even when the `enable_audit_fields` service is registered after startup.
- **Module load failure handling** – Failed modules are now properly disabled, preventing repeated crash loops on restart.
- **Logging crashes** – Fixed crashes when logging routes that had `None` paths or methods.

### Changed

- **Module loading sequence** – Both dev and prod modes now follow the same sequence: discover models → initialize database → run migrations → load entry points → apply deferred schema changes → optional follow-up migration.
- **Database initialization** – Now uses `ChaCCBaseModel` subclass enumeration instead of the removed `_model_registry`.

### Removed

- **Redundant startup schema pass** – Removed a duplicate migration run that caused unnecessary migrations in some environments.
- **`_model_registry`** – The old model registry has been removed in favor of SQLAlchemy's declarative metadata.

### Notes

- **Versioning**: The package metadata uses `1.0.0-b4.post2` for PyPI; the user-facing version is `1.0.0-b4.2`. Both refer to the same release.
- **Port default**: All references now consistently use port `8085` (previously some docs mentioned `8080`).
- **`.env` behavior**: The `.env.sample` file is copied from the package to your working directory if missing. This is intentional and unchanged from previous versions.

---

## 1.0.0-b4.1

**Update now:**
> PyPi Package:
```bash
pip install chacc-api==1.0.0-b4.post1
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-b4.1
```

### Added

- PostgreSQL enum migration support through `alembic-postgresql-enum`, including handling for `create_enum`, `sync_enum_values`, and `drop_enum` operations.
- Migration runner support for Alembic PostgreSQL enum operation objects generated by `alembic-postgresql-enum`.
- Automatic enum type creation before adding enum-backed columns or tables in PostgreSQL migrations to prevent `UndefinedObject` failures.
- `uuid7`-based default UUID generation for `ChaCCBaseModel`, using Python 3.12+ `uuid.uuid7` with `uuid-utils` fallback on older Python versions.
- `uuid-utils` runtime dependency for environments without native `uuid7` support.
- `SQLITE_DATABASE_NAME` and `SQLITE_DATABASE_PATH` environment variables for custom SQLite database names and storage locations.
- `CHACC_VERBOSE` and `CHACC_DEBUG` environment controls for runtime log level selection.
- CLI `chacc run server -v/--verbose` support that now propagates verbose logging into the server subprocess.
- Docker health checks and exposed ports updated to the current default server port.
- Production Docker Compose now uses the published Docker Hub image directly instead of local image build comments.

### Fixed

- PostgreSQL migration failures when Alembic detects enum changes by importing and enabling `alembic-postgresql-enum` hooks.
- PostgreSQL `UndefinedObject` crashes when adding enum-backed columns or tables by creating enum types before table/column operations.
- Migration operation ordering to apply enum creation before tables, columns, constraints, indexes, and enum synchronization.
- Migration descriptions for enum create, sync, and drop operations.
- CLI verbose flag propagation so `chacc run server -v` affects the child server process.
- Docker and Docker Compose default port mismatch by replacing stale `8080` references with `8085`.
- Alembic log noise by forcing the `alembic` logger to `WARNING`.
- Default logging behavior so normal server runs are quieter while `CHACC_VERBOSE` and `CHACC_DEBUG` still enable detailed logs.
- Repeated logger imports by centralizing default log level detection in `get_default_log_level()`.
- SQLite database path handling so `SQLITE_DATABASE_PATH` and `SQLITE_DATABASE_NAME` configuration takes effect.

### Removed

- Removed redundant `LogLevels.INFO` logger setup across server, database, migration, module loader, Redis, health, and environment validation modules.
- Removed stale Docker `8080` exposed port and health check references.
- Removed local-build instructions from the production Docker Compose file.

### Changed

- README file has been updated to focus on ChaCC brief intro and link the entire guidance to [chacc.dev](https://chacc.dev)

## 1.0.0-b4

**Update now:**
> PyPi Package:
```bash
pip install chacc-api==1.0.0-b4
```

> Docker
```bash
docker pull jonas1015/chacc-api:1.0.0-b4
```

### Added

- **Breaking**: GUID TypeDecorator for cross-database UUID support (PostgreSQL UUID type / SQLite TEXT storage)
- SQLite batch operation support for constraints, indexes, and columns via `batch_alter_table()`
- Automatic `.env` file creation from `.env.sample` on application startup if `.env` does not exist
- `.env.sample` included in package distribution for ready-to-use configuration reference
- Migration version counter suffix to prevent duplicate migration versions
- New database engine detection to distinguish PostgreSQL vs other databases

### Fixed

- **Breaking**: Migration tracker table `rollback_available` column conversion from BOOLEAN to INTEGER for PostgreSQL, and compatibility for SQLITE
- Migration runner now uses `run_in_executor()` for synchronous DB operations to prevent blocking async event loop
- Made tracker/backup lazy properties to defer DB initialization
- Catch ProgrammingError/OperationalError for already-existing resources to make migrations idempotent
- GUID TypeDecorator now returns UUID instances directly without unnecessary conversion
- Tracker table now filtered from migration detection to prevent accidental drops
- Resolved requirements.txt path issue for installed package layout

### Removed

- Removed redundant database type conversion in GUID TypeDecorator

> **Caution:** Users migrating to 1.0.0-b4 will need to drop their existing databases and start afresh. The `rollback_available` column type changed from BOOLEAN to INTEGER, and GUID column changes require a clean schema migration that cannot be automatically applied to existing data.
