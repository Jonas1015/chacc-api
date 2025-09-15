# OPEN TZ 

This is a python open source API engine created using Fast API. It was first created in August 2025.


## Building with Open TZ Platform
If as a developer you want to start development with Open-Tz Platform, here are things to consider:

Clone project from the repository:
```
git clone github.com/jonas1015/open-tz
```

create virtual environment:
```
python3 -m venv .venv
```

activate virtual environment
> Windows
> ```
> .\.venv\Scripts\activate
> ```

> Ubuntu
> ```
> source .venv/bin/activate
> ```

then install dependencies:
```
pip3 install -r requirements-dev.txt
```

Running a Open TZ web server 
```
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### Automatic Database Migrations

This project features a fully automatic, on-the-fly database migration system. It is designed to be a "zero-touch" experience for developers creating and deploying modules.

**How it Works:**

On application startup, after all enabled modules are loaded, the system automatically compares the currently registered SQLAlchemy models against the live database schema. It then generates and executes the necessary SQL commands to bring the database schema up to date with the models.

**How to Use It (for Module Developers):**

As a module developer, you do not need to create or run manual migration scripts. Your only responsibility is to decorate your SQLAlchemy model classes with the `@register_model` decorator from `src.database`.

Here is an example:
```python
from src.database import OpenTzBaseModel, register_model

@register_model
class MyNewModel(OpenTzBaseModel):
    # ... your columns here
```

By adding this decorator, you are telling the Open-TZ platform to include your model in its schema management. When the application restarts, it will automatically add or update the table for `MyNewModel` in the database.

**Warning:**

This is a powerful feature that directly modifies the database based on the loaded code. The user deploying a module is fully responsible for any data loss that may occur as a result of model changes. The platform provides the capability, but the responsibility for the data lies with the user.

### Creating modules with Open TZ Command Line Tool (open_tz_cli)

To create a new module with Open Tz Command Line Tool you will need to run this command inside the project root folder:
```
python3 -m open_tz_cli create module_name
```

This will be created inside `plugins/{module_name}` inside the project root folder

To build this module run:
```
python3 -m open_tz_cli build path/to/module_name
```

for the case of default path it should be `plugins/{module_name}`

Then deploy this module in POST `/module` API

### Dependency Management

The Open-TZ platform uses a centralized dependency management system to ensure a stable and consistent environment. When a module is installed, enabled, or disabled, the platform re-resolves all dependencies from the backbone and every enabled module to create a single, unified `compiled_requirements.lock` file. This file is then used to install all necessary packages into the environment.

**How it Works:**

1.  **Requirement Gathering:** The system collects the `requirements.txt` file from the backbone core and from each enabled module.
2.  **Dependency Resolution:** It uses `pip-tools` to compile all collected requirements into a single, deterministic `compiled_requirements.lock` file. This process identifies and resolves all transient dependencies, ensuring that a single, compatible version of each package is selected.
3.  **Installation:** The locked dependencies are then installed into the environment using `pip`.

**Best Practices for Module Developers:**

*   **Specify Dependencies:** Always declare your module's dependencies in its `requirements.txt` file.
*   **Be Flexible with Versions:** Whenever possible, avoid pinning exact dependency versions (e.g., `requests==2.25.1`). Instead, use flexible version specifiers (e.g., `requests>=2.25.0`) to allow the resolver to find a compatible version that satisfies all modules.
*   **Test for Conflicts:** Before releasing your module, test it with the Open-TZ backbone to ensure that your dependencies do not conflict with the core dependencies or those of other common modules.

**Consequences of Version Conflicts:**

If your module requires a specific version of a dependency that conflicts with the version required by the backbone or another module, the dependency resolution process may fail. In such cases, the system will be unable to generate a valid `compiled_requirements.lock` file, and the application will fail to start. It is the responsibility of the module developer to ensure their module's dependencies are compatible with the broader ecosystem.
