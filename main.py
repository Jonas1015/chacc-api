import asyncio
import subprocess
import sys
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from src.rate_limiter import limiter, rate_limit_exceeded_handler
from src.modules import modules_router
from src.health import health_router
from src.database import ModuleRecord, initialize_database_models, get_db
from src.logger import configure_logging, LogLevels
from src.chacc_api.core import BackboneContext
from src.constants import DEVELOPMENT_MODE, MODULES_LOADED_DIR, PLUGINS_DIR, ENABLE_PLUGIN_HOT_RELOAD
from src.env_validator import validate_environment, ValidationError

from src.migration.runner import run_migration
from src.chacc_api.services import RedisService

chacc_logger = configure_logging(log_level=LogLevels.DEBUG)


async def run_backbone_tests():
    """
    Run backbone unit tests on startup.
    Raises RuntimeError if tests fail to prevent app startup.
    """
    chacc_logger.info("Running backbone unit tests...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", "tests/test_backbone.py",
            "-v", "--tb=short", "--no-header"
        ], capture_output=True, text=True, cwd=".")

        passed_tests = []
        failed_tests = []

        if result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                line = line.strip()
                if 'PASSED' in line:
                    passed_tests.append(line)
                elif 'FAILED' in line or 'ERROR' in line:
                    failed_tests.append(line)

        if result.returncode == 0:
            chacc_logger.info(f"All backbone tests passed successfully ({len(passed_tests)} tests)")
            if passed_tests:
                chacc_logger.info("Passed tests:")
                for test in passed_tests:
                    chacc_logger.info(f"  ✓ {test}")
        else:
            chacc_logger.error(f"Backbone tests failed with return code {result.returncode}")

            if passed_tests:
                chacc_logger.info(f"Passed tests ({len(passed_tests)}):")
                for test in passed_tests:
                    chacc_logger.info(f"  ✓ {test}")

            if failed_tests:
                chacc_logger.error(f"Failed tests ({len(failed_tests)}):")
                for test in failed_tests:
                    chacc_logger.error(f"  ✗ {test}")
            else:
                chacc_logger.error("Test output:")
                if result.stdout:
                    chacc_logger.error(result.stdout)

            if result.stderr:
                chacc_logger.error(f"Test stderr: {result.stderr}")

            raise RuntimeError(f"Backbone tests failed ({len(failed_tests)} failed, {len(passed_tests)} passed). Application startup aborted.")

    except subprocess.CalledProcessError as e:
        chacc_logger.error(f"Error running backbone tests: {e}")
        raise RuntimeError(f"Backbone tests failed. Application startup aborted.")
    except Exception as e:
        chacc_logger.error(f"Unexpected error running backbone tests: {e}")
        raise RuntimeError(f"Backbone tests failed due to unexpected error: {e}")


@asynccontextmanager
async def onStartupLifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown events.
    """
    chacc_logger.info("Application startup initiated...")
    
    # Initialize Redis service
    redis_service = RedisService()
    
    try:
        validate_environment()
    except ValidationError as e:
        chacc_logger.critical(f"Environment validation failed: {e}")
        raise RuntimeError(f"Cannot start application: {e}")
    
    backbone_context = BackboneContext(
        app=app,
        limiter=app.state.limiter,
        logger=chacc_logger,
        db_session_factory=get_db
    )
    
    # Try to initialize Redis connection and register service
    try:
        redis_client = await redis_service.get_client()
        if redis_client:
            backbone_context.register_service("redis", redis_service)
            chacc_logger.info("Redis service registered in backbone context.")
        elif redis_service.connection_error:
            chacc_logger.warning(f"Redis connection failed: {redis_service.connection_error}. Continuing without Redis.")
        else:
            chacc_logger.info("Redis is disabled. Continuing without Redis.")
    except Exception as e:
        chacc_logger.warning(f"Failed to initialize Redis service: {e}. Continuing without Redis.")
    
    app.state.backbone_context = backbone_context

    initialize_database_models(backbone_context)
    
    session = await anext(get_db())
    modules_table_exists = False
    try:
        session.query(ModuleRecord).first()
        modules_table_exists = True
        chacc_logger.info("Modules table exists. Proceeding with regular startup sequence.")
    except Exception as e:
        chacc_logger.warning("Modules table does not exist. Running initial migration.")
        pass

    if not modules_table_exists:
        await run_migration()

        print("First migration completed. Running backbone tests before loading modules...")

    await run_backbone_tests()

    if DEVELOPMENT_MODE:
        chacc_logger.info("=" * 65)
        chacc_logger.info(f"DEVELOPMENT MODE: Loading plugins from {PLUGINS_DIR} directory")
        chacc_logger.info("=" * 65)
        from src.plugin_loader import load_dev_modules
        await load_dev_modules(app, backbone_context)
    else:
        from src.module_loader import load_modules
        chacc_logger.info("=" * 65)
        chacc_logger.info(f"PRODUCTION MODE: Loading modules from {MODULES_LOADED_DIR} directory")
        chacc_logger.info("=" * 65)
        await load_modules(app, backbone_context)
    
    await run_migration()
    
    yield
    
    # Shutdown: Close Redis connection gracefully
    try:
        redis_service = backbone_context.get_service("redis")
        if redis_service and redis_service.is_connected:
            await redis_service.close()
            chacc_logger.info("Redis connection closed gracefully.")
        else:
            chacc_logger.debug("Redis service not available or not connected. Skipping cleanup.")
    except Exception as e:
        chacc_logger.warning(f"Error during Redis shutdown: {e}")
    
    chacc_logger.info("Application shutting down.")
    
app = FastAPI(
    title="ChaCC API Backbone",
    description="A modular FastAPI application for extensible APIs.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=onStartupLifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.state.loaded_modules = {}
app.state.mounted_routers = {}

# Store reference to backbone context for authentication dependency
app.state.backbone_context = None

@app.get("/",
         summary="Root Endpoint",
         description="Welcome endpoint for the ChaCC API Backbone",
         response_description="Welcome message with documentation link",
         tags=["Core"])
async def read_root():
    """
    Root endpoint of the ChaCC API backbone.
    Returns a welcome message and directs users to the API documentation.
    """
    return {"message": "Welcome to the ChaCC API Backbone! Check /docs for API modules."}

app.include_router(modules_router)

# Health check endpoints - must be registered before modules
app.include_router(health_router)
