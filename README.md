# Adaptive AI

A staged, safety-first personal AI assistant project. The repository contains a FastAPI backend, an allowlisted calculator tool, automated tests, a Groq chat provider adapter, SQLite/PostgreSQL conversation history, and a shared bearer-token guard.

The chat API requires a Groq API key configured privately on the server. The Android client now includes a limited native action bridge for opening music, the dialer, an SMS draft, contacts, camera and video capture. These actions open Android/system UI and do not silently send messages or place calls. Full cross-app automation, safe plugin generation, self-updating code, and public multi-user hardening are not implemented.

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

The adapter uses Groq's OpenAI-compatible chat-completions endpoint. It sends the system instruction, the current message, and up to 20 prior user/assistant messages. Provider errors and credentials are not returned to API clients. Automated tests should not need a real API key or make paid model calls.

## Conversation memory
The store uses PostgreSQL when `DATABASE_URL` is set and SQLite for local development otherwise. PostgreSQL URLs beginning with `postgres://` or `postgresql://` are normalized to the psycopg v3 driver. For hosted deployment, configure `DATABASE_URL` to a dedicated Adaptive AI PostgreSQL database; do not reuse databases belonging to other applications. If no `DATABASE_URL` is set, SQLite defaults to `adaptive_ai.sqlite3` or the path in `ADAPTIVE_AI_DB_PATH`. Render's free filesystem is ephemeral, so SQLite there is not durable. Protect database access and backups because they contain conversation text.

Endpoints let the client create/list conversations, read message history, and delete a conversation. Chat requests can include `conversation_id` to continue a thread; omit it to start a new one.

## Production API protection
Production is the safe default when `APP_ENV` is omitted. When `APP_ENV=production`, every `/v1/*` route requires `Authorization: Bearer <ADAPTIVE_AI_API_TOKEN>`. Configure `ADAPTIVE_AI_API_TOKEN` as a long, random secret in the hosting provider's secret settings. If it is missing, API routes fail closed with HTTP 503. Invalid or absent bearer tokens receive HTTP 401. `/health` and the service landing page remain public.

This remains a controlled single-user deployment, not a public multi-user service. The API applies a shared bearer-token check, a basic in-process limit of 60 authenticated API requests per client per minute, a 64 KiB declared-body limit, and baseline security headers. The in-process limiter is not distributed across instances and depends on the client address exposed by the hosting proxy. **Account-level identity, per-user conversation ownership, a distributed edge rate limiter, monitoring/alerts, and recovery/backup drills remain pending. Do not distribute the shared token or advertise this version as safe for public multi-user use.**

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
- The native Android action bridge is intentionally allowlisted. Calling opens the dialer; messaging opens a draft; camera and video actions launch the system camera UI. It does not silently place calls, send messages, or capture media in the background.
- This native bridge is exposed as `window.AdaptiveDevice` in the Android WebView. The web app must explicitly map assistant intent to these methods; adding the bridge alone does not make the language model autonomously invoke actions.
- Cross-app automation, controlled code updates, sandboxed plugin activation, and account-level multi-user security are still pending.
- Generated functions will need sandboxing, tests, versioning, and rollback before any activation.

## Roadmap
1. Service skeleton, calculator allowlist, and tests.
2. Groq chat provider adapter and bounded chat endpoint (implemented; deployed chat returned HTTP 200 and persisted its user/assistant messages on 2026-10-24; re-verify after provider or credential changes).
3. SQLite/PostgreSQL conversation storage; hosted PostgreSQL must be configured for durable history.
4. Sandboxed plugin generation, validation, staged activation, and rollback.
5. Limited Android-native integrations with user-granted permissions.
6. Account-level identity and conversation ownership, distributed rate limiting, monitoring, backups, and recovery.


## Assistant productivity features
The authenticated `/v1/assistant` API provides user-scoped reminders, deterministic document-text operations, permission guidance, and reusable workflow drafts. Reminder records are persisted, and the Android client can schedule/cancel local notifications on the device when notification permission is granted. The browser-only web app saves reminders but cannot schedule Android notifications. Document text operations accept pasted text (up to 100,000 characters) and use deterministic server-side rules; PDF uploads are limited to 10 MB and 200 pages and extract selectable text only (scanned PDFs require OCR). Document processing does not call an external AI provider. Workflow steps are limited to summarization, message drafting, and reminder proposals; preview and approval do not execute actions, send messages, or schedule notifications.

The web interface includes PDF extraction and a permission guidance dashboard. It cannot directly determine Android runtime permission grants; verify those in Android Settings. A service worker caches only the app shell for offline opening and explicitly avoids caching API/authenticated data. Account data, chat, reminders, and workflows still require a network connection. No arbitrary plugin code executes and no self-deployment is enabled.
