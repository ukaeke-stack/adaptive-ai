from pathlib import Path
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from app.api.health import router as health_router
from app.api.capabilities import router as capabilities_router
from app.api.chat import router as chat_router
from app.api.agent_runtime import router as agent_router
from app.api.vision import router as vision_router
from app.api.conversations import router as conversations_router
from app.api.plugins import router as plugins_router
from app.api.social import router as social_router
from app.api.updates import router as updates_router
from app.api.assistant_productivity import router as productivity_router
from app.api.document_ocr import router as document_ocr_router
from app.api.safe_plugins import router as safe_plugins_router
from app.api.research import router as research_router
from app.security.sessions import router as auth_router
from app.config import get_settings
from app.security.auth import protect_api_routes
from app.memory.store import initialize_store

settings = get_settings()
app = FastAPI(
    title="Adaptive AI API",
    version="0.3.2",
    description="Adaptive AI with secure sessions, persistent conversations, reminders, document tools, and safe workflow drafts.",
)
app.middleware("http")(protect_api_routes)
app.include_router(health_router)
app.include_router(capabilities_router)
app.include_router(chat_router)
app.include_router(agent_router)
app.include_router(vision_router)
app.include_router(conversations_router)
app.include_router(plugins_router)
app.include_router(social_router)
app.include_router(updates_router)
app.include_router(productivity_router)
app.include_router(document_ocr_router)
app.include_router(safe_plugins_router)
app.include_router(research_router)
app.include_router(auth_router)

# Serve the same-origin web interface. API secrets remain server-side.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/app", StaticFiles(directory=str(_STATIC_DIR), html=True), name="adaptive-ai-web")


def custom_openapi():
    """Expose the protected API authentication requirement in Swagger UI."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http", "scheme": "bearer", "bearerFormat": "token"
    }
    for path, path_item in schema.get("paths", {}).items():
        if path.startswith("/v1/") and not path.startswith("/v1/auth/"):
            for operation in path_item.values():
                if isinstance(operation, dict) and "responses" in operation:
                    operation["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.on_event("startup")
def initialize_persistent_storage() -> None:
    """Fail startup if the configured database is unavailable; ensure schema exists."""
    initialize_store()


@app.get("/")
def service_info():
    """Return a small public service landing response; protected API routes remain under /v1."""
    return {
        "service": "Adaptive AI API", "status": "online", "health": "/health",
        "docs": "/docs", "app": "/app/",
        "api_authentication_required": settings.app_env == "production",
    }
