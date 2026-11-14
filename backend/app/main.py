from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.metrics import router as metrics_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Optional rate limiting (slowapi)
    if settings.rate_limit_enabled:
        try:
            from slowapi import _rate_limit_exceeded_handler
            from slowapi.errors import RateLimitExceeded
            from slowapi.middleware import SlowAPIMiddleware
            from slowapi.util import get_remote_address
            from slowapi import Limiter

            limiter = Limiter(key_func=get_remote_address, default_limits=[])
            app.state.limiter = limiter
            app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
            app.add_middleware(SlowAPIMiddleware)
        except Exception:
            pass

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(metrics_router, tags=["monitoring"])

    @app.get("/")
    async def root() -> dict:
        return {"service": "nexus-ai-backend", "status": "running"}

    return app


app = create_app()
