# Security model — current scope

- Tool execution is allowlist-only.
- No `eval`, shell execution, arbitrary Python execution, or dynamic plugin loading is exposed.
- No API keys are required for this milestone.
- `.env` files are ignored by Git; `.env.example` contains placeholders only.
- This prototype has no authentication or rate limiting and must not be exposed as a public production API yet.
- Future generated code must run in an isolated worker with resource limits, minimal filesystem access, restricted networking, and no inherited secrets.
- Any new privilege requires explicit policy review; generated tools cannot grant themselves permissions.
