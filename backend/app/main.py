from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.capabilities import router as capabilities_router
from app.api.chat import router as chat_router
from app.config import get_settings
from app.security.auth import protect_api_routes

settings = get_settings()
app = FastAPI(
    title="Adaptive AI API",
    version="0.2.0",
    description="Milestone 2: bounded chat endpoint with an optional OpenAI-compatible provider and a production bearer-token guard. Rate limiting and user accounts are still pending.",
)
app.middleware("http")(protect_api_routes)
app.include_router(health_router)
app.include_router(capabilities_router)
app.include_router(chat_router)
