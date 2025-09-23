# ChaCC API 

This is a python open source API engine created using Fast API. It was first created in August 2025.


## Building with ChaCC API Platform
If as a developer you want to start development with ChaCC API Platform, here are things to consider:

Clone project from the repository:
```
git clone github.com/jonas1015/chacc-api
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

## Startup & Deployment Guide

ChaCC API provides multiple startup options optimized for different environments and use cases. Choose the right method based on your deployment scenario.

### 🚀 **Recommended Startup Methods**

#### **1. Safe Startup Script (Production & Development)**
```bash
python start_server.py
```

**✅ Perfect for:**
- Production deployments
- Development work
- CI/CD pipelines
- Docker containers
- First-time setup

**Features:**
- Runs backbone tests before starting server
- No auto-reload (prevents infinite loops)
- Graceful error handling
- Production-ready startup process

**Usage:**
```bash
# Development
python start_server.py

# Production (in Dockerfile)
CMD ["python", "start_server.py"]

# CI/CD
python start_server.py
```

#### **2. Configured Uvicorn (Development with Auto-Reload)**
```bash
python uvicorn_config.py
```

**✅ Perfect for:**
- Active development
- Fast iteration cycles
- When you need auto-reload

**Features:**
- Selective auto-reload (only safe directories)
- Prevents infinite loops
- Optimized for development workflow

#### **3. Standard Uvicorn (Not Recommended)**
```bash
uvicorn main:app --reload
```

**❌ Avoid this:**
- Likely to cause infinite restart loops
- Watches problematic directories
- Cache files trigger unwanted reloads

### 🐳 **Docker Deployment**

#### **Dockerfile Example**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements*.txt ./
RUN pip install -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p .chacc_cache .modules_loaded .modules_upload modules_installed

# Expose port
EXPOSE 8080

# Use safe startup script
CMD ["python", "start_server.py"]
```

#### **Docker Compose**
```yaml
version: '3.8'
services:
  chacc-api:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - .:/app
      - .chacc_cache:/app/.chacc_cache
    environment:
      - DATABASE_URL=postgresql://...
    command: python start_server.py
```

### 🔄 **CI/CD Integration**

#### **GitHub Actions Example**
```yaml
name: CI/CD Pipeline

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt

      - name: Run tests safely
        run: python tests/run_tests_safely.py

      - name: Build and test modules
        run: |
          # Build test module
          python -m chacc_cli build tests/test_module

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: |
          # Your deployment commands
          echo "Deploying ChaCC API..."
```

#### **GitLab CI Example**
```yaml
stages:
  - test
  - deploy

test:
  stage: test
  script:
    - python tests/run_tests_safely.py
    - python -m chacc_cli build tests/test_module

deploy:
  stage: deploy
  script:
    - echo "Deploying to production..."
    - python start_server.py
  only:
    - main
```

### 🛠️ **Environment-Specific Configuration**

#### **Development Environment**
```bash
# Use configured uvicorn for development
python uvicorn_config.py

# Or use safe startup
python start_server.py
```

#### **Production Environment**
```bash
# Always use safe startup script
python start_server.py

# With environment variables
DATABASE_URL=postgresql://... python start_server.py
```

#### **Testing Environment**
```bash
# Use safe test runner
python tests/run_tests_safely.py

# Or run specific test categories
pytest tests/test_backbone.py
pytest tests/test_module_management.py
```

### ⚙️ **Configuration Files**

#### **start_server.py**
- Production-ready startup script
- Runs tests before starting server
- No auto-reload for stability
- Graceful error handling

#### **uvicorn_config.py**
- Development-optimized configuration
- Selective auto-reload
- Prevents infinite loops
- VSCode-friendly

#### **tests/run_tests_safely.py**
- Safe test execution
- Prevents file conflicts
- Automatic cleanup
- CI/CD friendly

### 🚨 **Troubleshooting Startup Issues**

#### **Infinite Restart Loops**
```bash
# Solution 1: Use safe startup (recommended)
python start_server.py

# Solution 2: Disable auto-reload
NO_RELOAD=1 python uvicorn_config.py

# Solution 3: Clear cache
rm -rf .chacc_cache/
python start_server.py
```

#### **Test Failures on Startup**
```bash
# Run tests manually first
python tests/run_tests_safely.py --backbone-only

# Then start server
python start_server.py
```

#### **Module Loading Issues**
```bash
# Clear module cache
rm -rf .modules_loaded/
python start_server.py
```

#### **Permission Issues**
```bash
# Ensure proper permissions
chmod +x start_server.py
mkdir -p .chacc_cache .modules_loaded .modules_upload
```

### 📊 **Performance Comparison**

| Method | Auto-Reload | Test Execution | Production Ready | Development Speed |
|--------|-------------|----------------|------------------|-------------------|
| `start_server.py` | ❌ No | ✅ Yes | ✅ Yes | ⚡ Fast |
| `uvicorn_config.py` | ✅ Selective | ❌ No | ❌ No | 🚀 Fastest |
| `uvicorn main:app --reload` | ✅ Full | ❌ No | ❌ No | 🚀 Fastest |

### 🎯 **Quick Start Guide**

```bash
# 1. Setup
git clone <repository>
cd chacc-api
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
pip install -r requirements-dev.txt

# 2. Development
python start_server.py    # 🚀 Recommended
# or
python uvicorn_config.py   # Alternative

# 3. Production
python start_server.py    # Always use this

# 4. Testing
python tests/run_tests_safely.py
```

### 🔒 **Security Considerations**

- **Production**: Use `start_server.py` to ensure tests pass before startup
- **Environment Variables**: Never commit secrets to version control
- **File Permissions**: Ensure proper permissions on cache directories
- **Network Security**: Configure firewall rules appropriately

This comprehensive startup system ensures ChaCC API works reliably across all environments while providing the best developer experience possible! 🎉

### Automatic Database Migrations

This project features a fully automatic, on-the-fly database migration system. It is designed to be a "zero-touch" experience for developers creating and deploying modules.

**How it Works:**

On application startup, after all enabled modules are loaded, the system automatically compares the currently registered SQLAlchemy models against the live database schema. It then generates and executes the necessary SQL commands to bring the database schema up to date with the models.

**How to Use It (for Module Developers):**

As a module developer, you do not need to create or run manual migration scripts. Your only responsibility is to decorate your SQLAlchemy model classes with the `@register_model` decorator from `src.database`.

Here is an example:
```python
from src.database import ChaCCBaseModel, register_model

@register_model
class MyNewModel(ChaCCBaseModel):
    # ... your columns here
```

By adding this decorator, you are telling the ChaCC API platform to include your model in its schema management. When the application restarts, it will automatically add or update the table for `MyNewModel` in the database.

**Warning:**

This is a powerful feature that directly modifies the database based on the loaded code. The user deploying a module is fully responsible for any data loss that may occur as a result of model changes. The platform provides the capability, but the responsibility for the data lies with the user.

### Creating modules with ChaCC API Command Line Tool (chacc_cli)

The ChaCC CLI has been refactored for better maintainability. Commands are now organized in separate modules:

- **CLI Entry Point**: `chacc_cli/__main__.py` - Command argument parsing
- **Command Implementations**: `chacc_cli/commands.py` - Core functionality

To create a new module with ChaCC Command Line Tool you will need to run this command inside the project root folder:
```
python3 -m chacc_cli create module_name
```

This will be created inside `plugins/{module_name}` inside the project root folder with a complete testing architecture.

#### **Generated Module Structure**
```
plugins/your_module/
├── module_meta.json          # Module metadata with test_entry_point
├── requirements.txt          # Module dependencies
└── module/
    ├── __init__.py
    ├── main.py              # Main module code with router setup
    └── tests/
        ├── __init__.py
        └── test_module.py   # Comprehensive test suite
```

#### **Built-in Testing Features**
Every generated module includes:
- **Test Infrastructure**: Complete testing setup ready to use
- **Test Entry Point**: Configured in `module_meta.json` for manual testing
- **Test Fixtures**: Pre-configured client and context fixtures
- **Test Runner**: `run_module_tests()` function for developer-controlled testing
- **Test Templates**: Ready-to-use test examples and comprehensive test suite

#### **Module Test Configuration**
```json
{
  "name": "your_module",
  "entry_point": "main:setup_plugin",
  "test_entry_point": "tests.test_module:run_module_tests",
  "base_path_prefix": "/your-module"
}
```

#### **Running Module Tests**
```python
# Module tests are developer responsibility - run manually:
cd plugins/your_module
python -m pytest module/tests/

# Or use the module's test runner:
from module.tests.test_module import run_module_tests
import asyncio
asyncio.run(run_module_tests())
```

To build this module run:
```
python3 -m chacc_cli build path/to/module_name
```

for the case of default path it should be `plugins/{module_name}`

#### **Deploy a Module to Remote Server**
```bash
# Set deployment configuration in .env file
echo "CHACC_DEPLOY_URL=http://your-api-server.com" >> .env
echo "CHACC_DEPLOY_API_KEY=your-optional-api-key" >> .env

# Deploy the built module
python3 -m chacc_cli deploy your_module.chacc
```

**Deployment Configuration:**
- `CHACC_DEPLOY_URL`: URL of your remote ChaCC API server
- `CHACC_DEPLOY_API_KEY`: Optional API key for authentication
- `CHACC_DEPLOY_TIMEOUT`: Request timeout in seconds (default: 30)

**Deployment Process:**
1. CLI reads configuration from `.env` file
2. Uploads the `.chacc` file to remote `/modules/` endpoint
3. Remote server installs and enables the module
4. **Server restart required** to activate the module

**Example Workflow:**
```bash
# 1. Create and develop module
python -m chacc_cli create my_feature

# 2. Build the module
python -m chacc_cli build plugins/my_feature

# 3. Deploy to remote server
python -m chacc_cli deploy my_feature.chacc

# 4. Restart remote server
# (Server restart activates the new module)
```

**Complete Development Workflow:**
```bash
# Local development
python -m chacc_cli create authentication
# Edit plugins/authentication/module/main.py
python -m chacc_cli build plugins/authentication

# Remote deployment
python -m chacc_cli deploy authentication.chacc
# Restart remote server
```

### Dependency Management

The ChaCC API platform uses a centralized dependency management system to ensure a stable and consistent environment. When a module is installed, enabled, or disabled, the platform re-resolves all dependencies from the backbone and every enabled module to create a single, unified `compiled_requirements.lock` file. This file is then used to install all necessary packages into the environment.

**How it Works:**

1.  **Requirement Gathering:** The system collects the `requirements.txt` file from the backbone core and from each enabled module.
2.  **Dependency Resolution:** It uses `pip-tools` to compile all collected requirements into a single, deterministic `compiled_requirements.lock` file. This process identifies and resolves all transient dependencies, ensuring that a single, compatible version of each package is selected.
3.  **Installation:** The locked dependencies are then installed into the environment using `pip`.

**Best Practices for Module Developers:**

*   **Specify Dependencies:** Always declare your module's dependencies in its `requirements.txt` file.
*   **Be Flexible with Versions:** Whenever possible, avoid pinning exact dependency versions (e.g., `requests==2.25.1`). Instead, use flexible version specifiers (e.g., `requests>=2.25.0`) to allow the resolver to find a compatible version that satisfies all modules.
*   **Test for Conflicts:** Before releasing your module, test it with the ChaCC backbone to ensure that your dependencies do not conflict with the core dependencies or those of other common modules.

**Consequences of Version Conflicts:**

If your module requires a specific version of a dependency that conflicts with the version required by the backbone or another module, the dependency resolution process may fail. In such cases, the system will be unable to generate a valid `compiled_requirements.lock` file, and the application will fail to start. It is the responsibility of the module developer to ensure their module's dependencies are compatible with the broader ecosystem.

### Incremental Dependency Caching System

The ChaCC API platform implements an advanced **incremental dependency caching system** that resolves dependencies intelligently and efficiently.

**How It Works:**

1. **Module-Level Hashing:** Each module's requirements are hashed individually
2. **Change Detection:** Only modules with changed requirements are re-resolved
3. **Incremental Resolution:** New/changed dependencies are resolved while unchanged ones use cache
4. **Smart Merging:** Combines cached and newly-resolved dependencies
5. **Selective Installation:** Only installs packages not already present

**Performance Benefits:**

- **First-time Setup:** Full dependency resolution for all modules
- **Single Module Change:** Only resolves dependencies for that specific module (5-15 seconds)
- **No Changes:** Near-instantaneous cache retrieval (< 1 second)
- **Smart Installation:** Skips already-installed packages

**Cache Architecture:**

```
.chacc_cache/
├── dependency_cache.json          # Main dependency cache
├── compiled_requirements.lock     # Compiled requirements file
└── pytest/                        # Pytest cache directory

dependency_cache.json structure:
├── backbone_hash: SHA256 of backbone requirements
├── combined_hash: SHA256 of all module hashes combined
├── module_caches: {
│   ├── "authentication": {
│   │   ├── hash: Module requirements hash
│   │   ├── packages: {fastapi: "==0.116.1", ...}
│   │   └── last_updated: Timestamp
│   │   }
│   └── "other_module": {...}
│   }
└── resolved_packages: Merged final package list
```

**Incremental Resolution Examples:**

**Scenario 1: No Changes**
```
INFO: Using cached dependency resolution (no changes detected)
INFO: All required packages are already installed
⏱️ Total: < 1 second
```

**Scenario 2: One Module Changes Requirements**
```
INFO: Module 'authentication' requirements have changed
INFO: Resolving dependencies for 1 changed modules
INFO: Resolved 5 packages for authentication
INFO: Installing 2 missing packages
INFO: Dependency cache updated with incremental changes
⏱️ Total: 10-15 seconds (vs 60+ seconds for full resolution)
```

**Scenario 3: New Module Added**
```
INFO: Module 'new_feature' requirements have changed
INFO: Resolving dependencies for 1 changed modules
INFO: Resolved 8 packages for new_feature
INFO: Installing 3 missing packages
INFO: Dependency cache updated with incremental changes
⏱️ Total: 15-20 seconds
```

**Cache Invalidation Triggers:**

- **Module-Specific:** When a module's requirements file changes
- **Module Lifecycle:** When modules are installed/enabled/disabled/uninstalled
- **Backbone Changes:** When backbone requirements.txt changes

**Manual Cache Management:**

```bash
# Clear entire cache (forces full resolution)
rm -rf .chacc_cache/

# Clear only dependency cache (keeps pytest cache)
rm .chacc_cache/dependency_cache.json

# Clear specific module cache (forces re-resolution of that module)
# Edit the JSON file to remove specific module from module_caches

# View cache contents
cat .chacc_cache/dependency_cache.json | jq

# View cache directory structure
tree .chacc_cache/
```

**Benefits for Module Developers:**

- **🚀 Blazing Fast:** 10x faster for incremental changes
- **🎯 Precise:** Only resolves what's actually changed
- **💾 Memory Efficient:** Reuses cached resolutions
- **🔄 Reliable:** Consistent dependency resolution
- **⚡ Development Speed:** Quick iterations without bottlenecks

**Advanced Features:**

- **Conflict Resolution:** Handles version conflicts between modules
- **Dependency Merging:** Intelligently combines requirements
- **Error Recovery:** Graceful fallback if cache is corrupted
- **Logging:** Detailed logs for debugging resolution issues

This caching system ensures that ChaCC API maintains excellent performance while providing the reliability and consistency that enterprise applications require.

## Testing Architecture

The ChaCC API platform implements a comprehensive testing strategy with different types of tests that serve different purposes. Tests are automatically categorized and executed at appropriate times to ensure system stability and reliability.

### Test Categories

#### 1. **Startup Tests (Automatic)**
These tests run automatically every time the application starts up. They focus on core functionality that must work for the system to operate properly.

**What they test:**
- Backbone API endpoints (root, docs, health checks)
- Core module listing functionality
- Basic system integrity

**When they run:**
- Automatically during `uvicorn main:app --reload` startup
- Part of the FastAPI lifespan event
- Cannot be skipped

**Why automatic:**
- Ensures core functionality works before serving requests
- Catches critical issues immediately
- Prevents deployment of broken systems

#### 2. **Module Management Tests (Manual Only)**
These tests verify the complete module lifecycle but create files that could interfere with development workflow.

**What they test:**
- Module upload/installation process
- Module enable/disable operations
- Module uninstallation
- Error handling for invalid modules
- File validation and security

**When to run them:**
- During development/testing phases
- Before releasing new versions
- When modifying module management code
- **Must be run manually** - never automatically

**Why manual:**
- Create files in `.modules_loaded/` directory
- Could trigger FastAPI auto-reloader during development
- Require cleanup after execution
- **Excluded from automatic startup testing**

#### 3. **Module-Specific Tests (Developer Responsibility)**
Each module can define its own tests that developers run manually.

**What they test:**
- Module-specific functionality
- Integration with backbone services
- Module API endpoints
- Module business logic

**When they run:**
- Manually by module developers
- During development and testing phases
- Before deployment and releases
- Configured via `test_entry_point` in `module_meta.json` (for framework support)

### Running Tests

#### **Automatic Startup Testing (Backbone Only)**
```bash
# 🚀 RECOMMENDED: Safe startup script (no auto-reloader loops)
python start_server.py

# Alternative: Configured startup with selective auto-reload
python uvicorn_config.py

# Alternative: Disable auto-reload completely
NO_RELOAD=1 python uvicorn_config.py

# For debugging: Standard uvicorn command
uvicorn main:app --reload

# Emergency: No auto-reload at all
uvicorn main:app --reload=false
```

**Note:** Only backbone tests run automatically on startup. Module management tests must be run manually to avoid conflicts with the auto-reloader.

#### **Safe Manual Testing (Recommended)**
```bash
# Run all tests safely with automatic cleanup
python tests/run_tests_safely.py

# Run only backbone tests (no file creation)
python tests/run_tests_safely.py --backbone-only

# Run tests without automatic cleanup
python tests/run_tests_safely.py --no-cleanup
```

#### **Standard pytest Commands**
```bash
# Run all tests (may trigger auto-reloader)
pytest tests/

# Run only backbone tests (safe for auto-reload)
pytest tests/test_backbone.py

# Run only module management tests (manual only)
pytest tests/test_module_management.py

# Run with safe test runner (recommended for module tests)
python tests/run_tests_safely.py
```

#### **Development Testing (with auto-reload disabled)**
```bash
# Terminal 1: Start server without auto-reload
uvicorn main:app --reload=false

# Terminal 2: Run tests
pytest tests/
```

### Test Results and Logging

#### **Startup Test Results**
```
INFO: Running backbone unit tests...
INFO: All backbone tests passed successfully (3 tests)
INFO: Passed tests:
  ✓ tests/test_backbone.py::test_root_endpoint PASSED
  ✓ tests/test_backbone.py::test_docs_endpoint PASSED
  ✓ tests/test_backbone.py::test_get_modules_empty PASSED
```

#### **Module Test Results (Manual Only)**
```
# Module tests run manually by developers
$ cd plugins/authentication && python -m pytest module/tests/
================================ test session starts ================================
collected 5 items

module/tests/test_module.py::test_authentication_login PASSED
module/tests/test_module.py::test_authentication_logout PASSED
...
========================= 5 passed in 2.34s =========================
```

#### **Test Failure Handling**
- **Backbone test failures**: Abort application startup (critical safety check)
- **Module test failures**: Developer responsibility - run manually during development
- **Manual test failures**: Standard pytest output with detailed error information

### Writing Module Tests

Modules can include their own tests by adding a `test_entry_point` to `module_meta.json`:

```json
{
  "name": "my_module",
  "entry_point": "main:setup",
  "test_entry_point": "tests:run_module_tests",
  ...
}
```

The test function should be async and return test results:

```python
# module/tests.py
async def run_module_tests():
    """Run module-specific tests."""
    # Your test logic here
    assert some_condition, "Test failed"
    return {"status": "passed", "tests_run": 5}
```

### Best Practices

#### **For Backbone Tests**
- Keep them lightweight and fast
- Focus on critical functionality only
- Avoid file system operations
- Use in-memory operations when possible

#### **For Module Tests**
- Test all public APIs and functionality
- Include integration tests with backbone services
- Handle test failures gracefully
- Clean up test data after execution

#### **For Manual Testing**
- Use the safe test runner to avoid auto-reloader issues
- Run tests in a clean environment
- Review test output for failures and warnings
- Ensure all tests pass before deployment

### Troubleshooting

#### **Auto-Reloader Issues**
If tests cause infinite reloads:
```bash
# Use safe runner
python tests/run_tests_safely.py

# Or disable auto-reload
uvicorn main:app --reload=false
```

#### **Test Cleanup**
```bash
# Manual cleanup of test modules
rm -rf .modules_loaded/test_module*

# Clear test cache
rm -rf .chacc_cache/pytest/

# Clear all cache (nuclear option)
rm -rf .chacc_cache/

# Or use safe runner (automatic cleanup)
python tests/run_tests_safely.py
```

#### **Module Test Failures**
- Check module logs for detailed error information
- Verify `test_entry_point` is correctly configured
- Ensure test function is properly implemented
- Review module dependencies and imports

#### **Auto-Reloader Issues**
If you experience infinite restart loops:

**Solution 1: Use Configured Startup**
```bash
# Use the optimized configuration that excludes problematic directories
python uvicorn_config.py
```

**Solution 2: Disable Auto-Reload**
```bash
# Run without auto-reload
uvicorn main:app --reload=false
```

**Solution 3: Manual Testing**
```bash
# Run tests separately, then start server
python tests/run_tests_safely.py
uvicorn main:app --reload
```

**Why This Happens:**
- Cache files created in watched directories trigger reloads
- Module unzipping creates files that trigger reloads
- Test execution may create temporary files

**Prevention:**
- Use `python start_server.py` for the most reliable experience
- Use `python uvicorn_config.py` for development with selective auto-reload
- Cache files are stored in `.chacc_cache/` (excluded from watching)
- VSCode settings exclude problematic directories from file watching
- Only backbone tests run automatically (safe for auto-reload)

This testing architecture ensures that ChaCC API maintains high quality and reliability while providing flexibility for module developers to implement comprehensive testing for their components.

## Standalone Components

### Dependency Manager Module

The ChaCC API platform includes a sophisticated dependency management system that can be used as a standalone component. Located in `src/package/dependency_manager.py`, this module provides intelligent dependency resolution for modular Python applications.

**Key Features:**
- Incremental dependency resolution with caching
- Module-level granularity for change detection
- Smart package installation with duplicate detection
- Automatic cache invalidation and conflict resolution
- Comprehensive logging and error handling

**Usage as Standalone Component:**
```python
from src.package.dependency_manager import DependencyManager

dm = DependencyManager()
await dm.resolve_dependencies()
```

**Core Classes:**
- `DependencyManager`: Main class for dependency resolution and caching
- Helper functions: `calculate_module_hash()`, `load_dependency_cache()`, etc.

**Documentation:** See `src/package/README.md` for complete API documentation and usage examples.

**Architecture:** The dependency manager is designed with clean separation of concerns, making it suitable for extraction into a separate package if needed for other projects.

This modular architecture allows ChaCC API to provide enterprise-grade features while maintaining clean separation of concerns and reusability.
