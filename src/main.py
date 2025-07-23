from fastapi import FastAPI, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from rate_limiter import limiter, rate_limit_exceeded_handler

app = FastAPI()

app.state.limiter = limiter

app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

@app.get("/limited-endpoint")
@limiter.limit("5/minute")
async def get_limited_data(request: Request):
    return {"message": "This is rate-limited data!"}

@app.get("/unlimited-looking-endpoint")
async def get_unlimited_data(request: Request): 
    return {"message": "This endpoint uses the default rate limit."}

@app.get("/relaxed-endpoint")
@limiter.limit("1000/hour")
async def get_relaxed_data(request: Request):
    return {"message": "This endpoint has a more relaxed rate limit."}

@app.post("/create-item")
@limiter.limit("10/hour", per_method=True)
async def create_item(request: Request):
    return {"message": "Item created."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)