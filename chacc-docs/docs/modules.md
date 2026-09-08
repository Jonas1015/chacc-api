# Modules

Modules are the main extension mechanism in ChaCC API. A module contributes
models, routes, services, configuration, and tests while the backbone handles
startup, migration, dependency resolution, and mounting.

## Module layout

```text
my_module/
  module_meta.json
  requirements.txt
  my_module_src/
    __init__.py
    main.py
    models.py
    routes.py
    context_factory.py
    run_tests.py
    tests/
      __init__.py
      test_module.py
  README.md
  .gitignore
```

## `module_meta.json`

| Field | Required | Description |
| --- | --- | --- |
| `name` | Yes | Machine-readable module name. |
| `display_name` | No | Human-readable name shown in module records. |
| `version` | No | Module version. |
| `author` | No | Author or organization. |
| `description` | No | Module description. |
| `entry_point` | Yes | Python path to setup function, for example `my_module_src.main:setup_plugin`. |
| `base_path_prefix` | No | Default API prefix, for example `/billing`. |
| `tags` | No | FastAPI documentation tags. |
| `dependencies_file` | No | Requirements file name, usually `requirements.txt`. |
| `required_chacc_version` | No | Minimum ChaCC version. |
| `license` | No | Module license. |
| `homepage` | No | Module homepage. |

## Setup function

A module entry point must expose a callable setup function.

```python
from fastapi import APIRouter
from chacc_api import BackboneContext


def setup_plugin(context: BackboneContext):
    router = APIRouter(prefix="/items", tags=["Items"])

    @router.get("/")
    async def list_items():
        return {"items": []}

    return router
```

The setup function may be synchronous or asynchronous. It receives
`BackboneContext` and must return a FastAPI `APIRouter`.

## Models

Models should inherit from `ChaCCBaseModel`. The legacy `@register_model`
decorator is retained as a backward-compatible no-op and should not be used in
new code.

```python
from chacc_api import ChaCCBaseModel
from sqlalchemy import Column, String


class Item(ChaCCBaseModel):
    __tablename__ = "items"
    name = Column(String, nullable=False)
```

`ChaCCBaseModel` adds:

| Field | Type | Purpose |
| --- | --- | --- |
| `id` | `Integer` | Primary key. |
| `uuid` | `GUID` | Cross-database UUID value, defaults to `uuid7`. |
| `created_at` | `DateTime` | Creation timestamp. |
| `updated_at` | `DateTime` | Last update timestamp. |
| `deleted_at` | `DateTime` | Soft-delete timestamp. |

## Routes

Use a database dependency to work with the database in your routes. ChaCC
provides both a synchronous and an asynchronous session. For new modules,
prefer the **async** session (`AsyncSession`) because it does not block the
server while it waits for the database to respond.

Get the dependency from your module's `context_factory.py`, which the
`chacc create` command generates for you:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from .context_factory import get_async_db

router = APIRouter()


@router.get("/items")
async def list_items(db: AsyncSession = Depends(get_async_db)):
    # `db` is an async SQLAlchemy session.
    # Example: result = await db.execute(select(Item))
    return {"items": []}
```

If you need a traditional synchronous session, use `get_db` instead:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .context_factory import get_db

router = APIRouter()


@router.get("/ping")
async def ping(db: Session = Depends(get_db)):
    return {"ok": True}
```

## Services

Modules can share behavior through `BackboneContext`.

```python
def verify_token(token: str):
    return token == "example"


def setup_plugin(context):
    context.register_service("token_verifier", verify_token)
    return router
```

Another module can retrieve it:

```python
verifier = context.get_service("token_verifier")
```

## Dependencies

Put Python dependencies in `requirements.txt`. ChaCC resolves dependencies before
extracting or enabling modules.

```text
requests
pydantic==2.7.0
```

## Build and deploy

```bash
chacc create my_module
chacc run server --dev
chacc build plugins/my_module
chacc deploy my_module.chacc
```

The build command creates a ZIP archive named after the module unless an output
filename is provided.

## Development mode vs production mode

| Mode | Source directory | Behavior |
| --- | --- | --- |
| Development | `plugins/` | Loads modules from source directories with optional hot reload. |
| Production | `.modules_installed/` | Loads enabled modules from extracted archives. |

## Best practices

- Keep module names lowercase with underscores.
- Use one `APIRouter` per module.
- Put database models in importable Python files so model discovery can find
  `ChaCCBaseModel` subclasses.
- Avoid circular imports by using `context.get_service()` instead of direct
  module imports.
- Store module-specific secrets as `{MODULE_NAME}_{KEY}` in `.env`.
- Restart the backbone after installing, enabling, disabling, or uninstalling a
  module.
- Failed module loads are automatically disabled in the database to prevent
  repeated startup crashes.
