# Adaptive AI

A staged, safety-first personal AI assistant project. The repository contains a FastAPI backend, an allowlisted calculator tool, automated tests, an optional OpenAI-compatible chat provider adapter, SQLite-backed conversation history, and a production bearer-token guard.

The chat API is not usable until a provider API key and model are configured. Android automation and safe plugin generation are not implemented yet.

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

## Conversation memory
Conversations are stored in SQLite. Set `ADAPTIVE_AI_DB_PATH` to choose the database file location; the default is `adaptive_ai.sqlite3` in the backend working directory. Keep this file on persistent storage for a hosted deployment and protect backups because it contains conversation text. Endpoints let the client create/list conversations, read message history, and delete a conversation. Chat requests can include `conversation_id` to continue a thread; omit it to start a new one. The model receives up to the 20 most recent prior messages.

## Production API protection
When `APP_ENV=production`, every `/v1/*` route requires `Authorization: Bearer <ADAPTIVE_AI_API_TOKEN>`. Configure `ADAPTIVE_AI_API_TOKEN` as a long, random secret in the hosting provider's secret settings. If it is missing, API routes fail closed. `/health` remains public for health checks.

This is a starter single-token guard, not full user authentication. **Rate limiting, account-level identity, and production abuse controls are still pending. Do not expose this prototype publicly until those controls are implemented.**

## API endpoints
- `GET /health` — health check.
- `GET /v1/capabilities` — registered tools.
- `POST /v1/tools/execute` — allowlisted calculator only.
- `POST /v1/chat` — request body `{"message":"Hello"}`; optionally include `conversation_id` to continue a conversation.
- `POST /v1/conversations` — create a conversation.
- `GET /v1/conversations` — list recent conversations.
- `GET /v1/conversations/{id}/messages` — read messages.
- `DELETE /v1/conversations/{id}` — delete a conversation and its messages.

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
2. Chat provider adapter and bounded chat endpoint (requires provider credentials).
3. SQLite conversation history (implemented for single-user MVP); then user-controlled long-term memory and stronger account authentication.
4. Sandboxed plugin generation, validation, staged activation, and rollback.
5. Limited Android-native integrations with user-granted permissions.
6. Deployment hardening, monitoring, backups, and recovery.
