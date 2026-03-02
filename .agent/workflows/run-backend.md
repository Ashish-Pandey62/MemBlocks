---
description: how to run the backend server
---

// turbo-all
1. Make sure Docker services are running (from project root):
```
docker compose up -d
```

2. Run the backend (from project root):
```
uv run uvicorn backend.src.api.main:app --host 0.0.0.0 --port 8001 --reload
```

Server: http://localhost:8001
Swagger docs: http://localhost:8001/docs
