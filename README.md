# Adaptive AI

A staged, safety-first personal AI assistant project. The repository contains a FastAPI backend, an allowlisted calculator tool, automated tests, a Groq chat provider adapter, SQLite-backed conversation history, and a production bearer-token guard.

The chat API requires a Groq API key configured privately on the server. Android automation and safe plugin generation are not implemented yet.

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

## Configure Groq
Create a Groq API key in the [Groq Console](https://console.groq.com/keys). Store it only in your private local environment or your hosting provider's secret settings as `GROQ_API_KEY`. **Never paste it into source files, commit it to GitHub, or share it in chat.**

Supported environment settings:
- `GROQ_API_KEY`: required secret.
- `GROQ_MODEL`: optional; defaults to `openai/gpt-oss-20b`.
- `GROQ_BASE_URL`: optional; defaults to `https://api.groq.com/openai/v1`. The adapter accepts only the official Groq HTTPS API host.

The adapter uses Groq's OpenAI-compatible chat-completions endpoint. It sends the system instruction, the current message, and up to 20 prior user/assistant messages. The provider's raw errors and credentials are not returned to API clients. Tests mock the provider request; they do not need a real API key or make paid model calls.

## Conversation memory
Conversations are stored in SQLite. Set `ADAPTIVE_AI_DB_PATH` to choose the database file location; the default is `adaptive_ai.sqlite3` in the backend working directory. Keep this file on persistent storage for a hosted deployment and protect backups because it contains conversation text. Endpoints let the client create/list conversations, read message history, and delete a conversation. Chat requests can include `conversation_id` to continue a thread; omit it to start a new one.

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
2. Groq chat provider adapter and bounded chat endpoint (implemented; requires a privately configured Groq API key).
3. SQLite conversation history (implemented for single-user MVP); then user-controlled long-term memory and stronger account authentication.
4. Sandboxed plugin generation, validation, staged activation, and rollback.
5. Limited Android-native integrations with user-granted permissions.
6. Deployment hardening, monitoring, backups, rate limiting, and recovery.
