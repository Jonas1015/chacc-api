import logging
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from src.rate_limiter import limiter, rate_limit_exceeded_handler
from src.modules import load_modules, modules_router
from src.database import ModuleRecord, initialize_database_models, get_db, run_automatic_migration
from src.logger import configure_logging, LogLevels
from src.core_services import BackboneContext

opentz_logger = configure_logging(log_level=LogLevels.INFO)

@asynccontextmanager
async def onStartupLifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown events.
    """
    opentz_logger.info("Application startup initiated...")
    
    backbone_context = BackboneContext(
        app=app,
        limiter=app.state.limiter,
        logger=opentz_logger,
        db_session_factory=get_db
    )

    initialize_database_models(backbone_context)
    
    session = await anext(get_db())
    modules_table_exists = False
    try:
        session.query(ModuleRecord).first()
        modules_table_exists = True
        opentz_logger.info("Modules table exists. Proceeding with regular startup sequence.")
    except Exception as e:
        opentz_logger.warning("Modules table does not exist. Running initial migration.")
        pass

    if not modules_table_exists:
        await run_automatic_migration()

    await load_modules(app, backbone_context)
    
    await run_automatic_migration()
    
    opentz_logger.info("Application startup complete.")
    
    yield
    
    opentz_logger.info("Application shutting down.")
    
app = FastAPI(
    title="Open-TZ API Backbone",
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

@app.get("/")
async def read_root():
    """
    Root endpoint of the Open-TZ API backbone.
    """
    return {"message": "Welcome to the Open-TZ API Backbone! Check /docs for API modules."}

app.include_router(modules_router, tags=["Module Management"])