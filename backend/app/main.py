from fastapi import FastAPI
from app.api.health import router as health_router
from app.api.capabilities import router as capabilities_router
from app.config import get_settings

settings = get_settings()
app = FastAPI(
    title="Adaptive AI API",
    version="0.1.0",
    description="Milestone 1 service skeleton. No model connection or dynamic code execution yet.",
)
app.include_router(health_router)
app.include_router(capabilities_router)
