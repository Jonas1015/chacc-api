import logging
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from src.rate_limiter import limiter, rate_limit_exceeded_handler
from src.modules import load_modules, modules_router
from src.database import OpenTzBaseModel, engine
from src.logger import configure_logging, LogLevels

# --- Initialization ---
opentz_logger = configure_logging(log_level=LogLevels.INFO)

@asynccontextmanager
async def onStartupLifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown events.
    """
    opentz_logger.info("Application startup initiated...")
    
    OpenTzBaseModel.metadata.create_all(bind=engine)
    opentz_logger.info("Database tables ensured for core models and ModuleRecord.")
    
    await load_modules(app)
    opentz_logger.info("All modules loaded and ready to serve requests.")
    
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