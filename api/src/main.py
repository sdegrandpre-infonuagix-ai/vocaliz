"""Salon API — FastAPI application entry point."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mangum import Mangum
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.config import settings
from src.rate_limit import limiter
from src.routers import auth, salons
from src.routers.admin import router as admin_router
from src.routers.guest_web import router as guest_web_router
from src.routers.sources import router as sources_router
from src.routers.invitations import guest_router, me_router, router as invitations_router
from src.routers.users import router as users_router

app = FastAPI(title="Salon API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth.router)
app.include_router(salons.router)
app.include_router(invitations_router)
app.include_router(guest_router)
app.include_router(me_router)
app.include_router(users_router)
app.include_router(guest_web_router)
app.include_router(sources_router)
app.include_router(admin_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def public_config():
    """What the clients need to know before anyone signs in.

    Deliberately unauthenticated and deliberately tiny: it decides what a page offers,
    not what it may do. Nothing here is a secret, and requiring a token would mean the
    sign-in screen could not read it.
    """
    return {
        "smsEnabled": settings.sms_enabled,
        # The address the front desk signs in with. Served rather than written into the page
        # so the two cannot disagree: the desk is a role, and the address changes when
        # somebody else is on shift. A page holding its own copy would send a code to the
        # previous occupant and show no reason why nobody received it.
        #
        # Not a secret. It is the published address of a front desk, and the code that reaches
        # it is what actually guards the desk.
        "frontDeskEmail": settings.front_desk_email,
    }


# AWS Lambda handler (Mangum adapts ASGI ↔ Lambda event)
handler = Mangum(app, lifespan="off")
