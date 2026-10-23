# Architecture — Milestone 1

The current backend is a single FastAPI application with explicit route, policy, and tool-registry modules. It intentionally has no model provider, persistent database, authentication, generated-code execution, or Android bridge yet.

## Request path
1. Client calls an HTTP endpoint.
2. Pydantic validates the request shape.
3. The policy layer checks the tool name against a static allowlist.
4. The registered handler receives only its declared arguments.
5. The API returns the result or a bounded error response.

## Next modules
- `ai/providers/`: provider adapters after credentials and provider are selected.
- `memory/`: persistent, user-controlled memory after authentication and storage are selected.
- `self_development/`: only after a separate sandbox worker exists; never execute generated code in the API process.
