from fastapi import HTTPException, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func = get_remote_address)

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom handler for RateLimitExceeded errors.
    This allows you to customize the response when a rate limit is hit.
    """
    raise HTTPException(
        status_code=429,
        detail=f"Too many requests. You have exceeded the rate limit of {exc.detail}.",
        headers={"Retry-After": str(int(exc.detail.split(' ')[0]) / 60)} # Approximate seconds to wait
    )