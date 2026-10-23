# API contract — Milestone 1

- `GET /health`: service status and milestone.
- `GET /v1/capabilities`: list registered tools.
- `POST /v1/tools/execute`: execute a registered tool. Example body:

```json
{"name":"calculator","arguments":{"operation":"add","a":2,"b":3}}
```

Unknown tools return 404. Invalid arguments or calculations return 422. This API has no authentication yet; keep it local during this milestone.
