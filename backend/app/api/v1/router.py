from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.agents import router as agents_router
from app.api.v1.chat import router as chat_router
from app.api.v1.documents import compat_router as documents_compat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.intelligence import router as intelligence_router
from app.api.v1.search import router as search_router
from app.api.v1.sources import router as sources_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(agents_router)
api_router.include_router(documents_router)
api_router.include_router(documents_compat_router)
api_router.include_router(search_router)
api_router.include_router(chat_router)
api_router.include_router(sources_router)
api_router.include_router(intelligence_router)
