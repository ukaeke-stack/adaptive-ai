# Adaptive AI

A staged, safety-first AI assistant platform. This repository currently contains Milestone 1: a minimal FastAPI service, an explicit built-in tool registry, configuration checks, and automated tests. It is **not yet connected to an AI model** and does not perform Android automation or execute generated code.

## Requirements
- Python 3.11+
- pip

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

## Run tests
```bash
cd backend
pip install -r requirements.txt
pytest -q
```

## Safety scope for Milestone 1
- Only explicitly registered built-in tools can run.
- No arbitrary Python/code execution endpoint exists.
- No AI provider credentials are needed yet.
- Unknown tools and malformed inputs are rejected.
- Do not expose this prototype publicly until authentication, rate limiting, production configuration, and deployment security are added.

## Roadmap
1. Service skeleton and controlled tool registry (current milestone).
2. Model provider adapter and chat endpoint.
3. Persistent, user-controlled memory.
4. Sandboxed plugin generation, validation, and staged activation.
5. Limited Android integrations with user-granted permissions.
