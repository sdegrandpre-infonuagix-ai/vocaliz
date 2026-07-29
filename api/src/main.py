"""Salon API — FastAPI application entry point."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mangum import Mangum
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.routers import auth, sessions
from src.routers.invitations import me_router, router as invitations_router

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Salon API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(invitations_router)
app.include_router(me_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# AWS Lambda handler (Mangum adapts ASGI ↔ Lambda event)
handler = Mangum(app, lifespan="off")
