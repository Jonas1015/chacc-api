"""
ChaCC Health Check Endpoint.

Provides health and readiness checks for container orchestration:
- /health - Basic liveness check
- /health/ready - Readiness check (includes database)
"""
import os
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.database import get_db, engine
from src.logger import configure_logging, LogLevels
from src.constants import DEVELOPMENT_MODE
from sqlalchemy import text

chacc_logger = configure_logging(log_level=LogLevels.INFO)

health_router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    mode: str
    checks: dict


@health_router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Basic liveness check.
    
    Returns 200 when the service is running.
    Used by Kubernetes for pod lifecycle management.
    """
    return HealthResponse(
        status="healthy",
        mode="development" if DEVELOPMENT_MODE else "production",
        checks={
            "api": "ok"
        }
    )


@health_router.get("/health/ready", response_model=HealthResponse)
async def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness check with database connectivity.
    
    Returns 200 when the service is ready to accept traffic.
    Includes database connectivity check.
    """
    checks = {
        "api": "ok",
        "database": "unknown"
    }
    
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        chacc_logger.error(f"Database health check failed: {e}")
        checks["database"] = "error"
    
    all_ok = all(v == "ok" for v in checks.values())
    overall_status = "healthy" if all_ok else "unhealthy"
    
    return HealthResponse(
        status=overall_status,
        mode="development" if DEVELOPMENT_MODE else "production",
        checks=checks
    )


@health_router.get("/health/live", response_model=HealthResponse)
async def liveness_check():
    """
    Liveness check - simplified version.
    
    Returns 200 if the process is running.
    No dependency checks (those are in /health/ready).
    """
    return HealthResponse(
        status="alive",
        mode="development" if DEVELOPMENT_MODE else "production",
        checks={
            "process": "running"
        }
    )
