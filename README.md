# Adaptive AI

A staged, safety-first personal AI assistant project. The repository contains a FastAPI backend, an allowlisted calculator tool, automated tests, an optional OpenAI-compatible chat provider adapter, and a production bearer-token guard.

The chat API is not usable until a provider API key and model are configured. Android automation, persistent memory, and safe plugin generation are not implemented yet.

## Run locally
```bash
cd backend
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open `/docs` for the API explorer and `/health` for the health check.

## Configure chat provider
Set these in your local shell or private deployment settings:
- `AI_API_KEY`: provider API key; keep secret.
- `AI_MODEL`: model identifier supported by your provider.
- `AI_BASE_URL`: optional OpenAI-compatible API base URL; defaults to `https://api.openai.com/v1`.

Never commit real API keys. The server returns a configuration error if the key or model is missing. Provider errors are returned without exposing credentials or raw provider responses.

## Production API protection
When `APP_ENV=production`, every `/v1/*` route requires `Authorization: Bearer <ADAPTIVE_AI_API_TOKEN>`. Configure `ADAPTIVE_AI_API_TOKEN` as a long, random secret in the hosting provider's secret settings. If it is missing, API routes fail closed. `/health` remains public for health checks.

This is a starter single-token guard, not full user authentication. **Rate limiting, account-level identity, conversation storage, and production abuse controls are still pending. Do not expose this prototype publicly until those controls are implemented.**

## API endpoints
- `GET /health` — health check.
- `GET /v1/capabilities` — registered tools.
- `POST /v1/tools/execute` — allowlisted calculator only.
- `POST /v1/chat` — sends one message to the configured chat-completions provider. Request body: `{"message":"Hello"}`.

## Run tests
```bash
cd backend
pytest -q
```

## Safety limitations
- Tool execution is allowlist-only; arbitrary code, shell commands, and dynamic plugin execution are not supported.
- Android actions will require explicit device permissions and user-visible safeguards.
- Generated functions will need sandboxing, tests, versioning, and rollback before any activation.

## Roadmap
1. Service skeleton, calculator allowlist, and tests.
2. Chat provider adapter and bounded chat endpoint (scaffolded; requires provider credentials).
3. Authentication hardening, request limits, and user-controlled persistent memory.
4. Sandboxed plugin generation, validation, staged activation, and rollback.
5. Limited Android-native integrations with user-granted permissions.
6. Deployment hardening, monitoring, backups, and recovery.
