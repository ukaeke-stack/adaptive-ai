from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from app.api.health import router as health_router
from app.api.capabilities import router as capabilities_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.config import get_settings
from app.security.auth import protect_api_routes
from app.memory.store import initialize_store

settings = get_settings()
app = FastAPI(
    title="Adaptive AI API",
    version="0.3.1",
    description="Milestone 3 foundation: bounded Groq chat, PostgreSQL conversation memory, and a production bearer-token guard. Rate limiting and multi-user accounts are still pending.",
)
app.middleware("http")(protect_api_routes)
app.include_router(health_router)
app.include_router(capabilities_router)
app.include_router(chat_router)
app.include_router(conversations_router)


def custom_openapi():
    """Expose the middleware's bearer-token requirement in Swagger UI."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})[
        "BearerAuth"
    ] = {"type": "http", "scheme": "bearer", "bearerFormat": "token"}
    for path, path_item in schema.get("paths", {}).items():
        if path.startswith("/v1/"):
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
        "service": "Adaptive AI API",
        "status": "online",
        "health": "/health",
        "docs": "/docs",
        "api_authentication_required": settings.app_env == "production",
    }
