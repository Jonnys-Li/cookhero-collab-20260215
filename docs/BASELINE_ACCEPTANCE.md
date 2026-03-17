# Baseline Acceptance: Local + CI + Production

This document is the minimum "connectivity and runnable" gate before we start
implementing new features. The goal is that a teammate can copy/paste the
commands below and quickly verify:

- Local: backend + frontend run, proxy works, auth works, key endpoints respond.
- CI parity: `pytest` + `vitest` (optional Playwright E2E).
- Production: smoke scripts pass (demo-stable or strict).

## Prerequisites

- Python: repo target is 3.12+ (see `.python-version`). If you run into TLS/SSL
  weirdness on macOS, avoid Apple/Xcode Python and use a proper CPython build.
- Node: CI uses Node 20 (local can be newer, but parity is Node 20).
- Docker Desktop: required only for "full infra" mode (`deployments/docker-compose.yml`).
- `jq`: required for the MCP part of `scripts/smoke-prod.sh`.

Quick sanity checks:

```bash
python --version || true
python3 --version
node --version
npm --version
docker --version
docker compose version
jq --version
```

## Local (Fastest Path: SQLite Quick Mode)

This mode does not require Docker. It uses the default SQLite config from
`config.yml` (`database.postgres.host: "sqlite"` pointing to `cookhero.db`).

### 1) Backend

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215

# First time only:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Configure local env (never commit .env):
cp .env.example .env

# Run backend:
JWT_SECRET_KEY="local-dev-secret-at-least-32-chars-xxxxxxxx" \
DISABLE_BACKGROUND_STARTUP_TASKS=true \
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Notes:
- `DISABLE_BACKGROUND_STARTUP_TASKS=true` keeps startup deterministic (no MCP
  auto-register / metadata warmups in the background).
- `/api/v1/health` exists and is protected by the auth gateway. Unauthed calls
  should return 401, authed calls should return 200 with `{"ok": true, ...}`.

### 2) Frontend

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215/frontend

# CI-equivalent (slower but deterministic):
# npm ci

# Local (faster for iterative dev):
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Vite proxy is configured in `frontend/vite.config.ts`:
- `/api/*` -> `http://localhost:8000`

### 3) Local Acceptance Checks (Copy/Paste)

This verifies:
- Vite proxy to backend works
- register/login works and returns a JWT
- `/api/v1/health` works with auth
- diet + agent key endpoints respond

```bash
set -euo pipefail

BASE="http://127.0.0.1:5173/api/v1"
USER="smoke_$(date +%s)"
PASS="testpass123"

resp="$(curl -sS -X POST "${BASE}/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${USER}\",\"password\":\"${PASS}\"}")"

token="$(python3 - <<'PY'
import json, sys
print(json.load(sys.stdin)["access_token"])
PY
<<<"$resp")"

curl -sS -o /dev/null -w "proxy health (no auth) -> %{http_code}\n" "${BASE}/health"
curl -sS -o /dev/null -w "health (auth) -> %{http_code}\n" -H "Authorization: Bearer ${token}" "${BASE}/health"
curl -sS -o /dev/null -w "agent/tools -> %{http_code}\n" -H "Authorization: Bearer ${token}" "${BASE}/agent/tools"
curl -sS -o /dev/null -w "diet/enums -> %{http_code}\n" -H "Authorization: Bearer ${token}" "${BASE}/diet/enums"
curl -sS -o /dev/null -w "diet/preferences -> %{http_code}\n" -H "Authorization: Bearer ${token}" "${BASE}/diet/preferences"

TODAY="$(date +%F)"
curl -sS -o /dev/null -w "diet/logs?log_date=${TODAY} -> %{http_code}\n" \
  -H "Authorization: Bearer ${token}" "${BASE}/diet/logs?log_date=${TODAY}"
```

### 4) Streaming Checks (Conversation + Agent)

This is the "real" runnable gate for core UX, but it requires a valid LLM API key:
- at minimum `LLM_API_KEY` in `.env` (and a reachable provider per `config.yml`).

If the key is missing/invalid, you should still see SSE `data: ...` events and an
`error` event, but you will not get a full `text` + `done` sequence.

```bash
set -euo pipefail

BASE="http://127.0.0.1:5173/api/v1"
USER="stream_$(date +%s)"
PASS="testpass123"
resp="$(curl -sS -X POST "${BASE}/auth/register" -H 'Content-Type: application/json' -d "{\"username\":\"${USER}\",\"password\":\"${PASS}\"}")"
token="$(python3 - <<'PY'
import json, sys
print(json.load(sys.stdin)["access_token"])
PY
<<<"$resp")"

# Conversation SSE
curl -sS -N -X POST "${BASE}/conversation" \
  -H "Authorization: Bearer ${token}" \
  -H 'Content-Type: application/json' \
  --max-time 30 \
  -d '{"message":"给我一个番茄炒蛋的做法，简短点","stream":true}' \
  | sed -n '1,25p'

# Agent SSE
curl -sS -N -X POST "${BASE}/agent/chat" \
  -H "Authorization: Bearer ${token}" \
  -H 'Content-Type: application/json' \
  --max-time 30 \
  -d '{"message":"今天想吃清淡点，给我一个晚餐建议","agent_name":"default","stream":true}' \
  | sed -n '1,40p'
```

Pass criteria (streaming):
- You see multiple `data: {...}` events.
- With correct keys, you should see `type=text` events and a terminal `done`.

## Local (Full Infra Mode: Docker Compose)

This mode is needed for Redis/Milvus/MinIO/Postgres based flows.

1) Start Docker Desktop (must be running).

2) Start infra:

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215
docker compose -f deployments/docker-compose.yml up -d
docker compose -f deployments/docker-compose.yml ps
```

3) Point backend to Postgres (optional but recommended for parity):

```bash
export DATABASE_URL="postgresql://cookhero:cookhero_secret@localhost:5432/cookhero"
```

Then start backend as in SQLite mode.

## CI Parity (Run Locally)

Backend:

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215
source .venv/bin/activate

pytest -q
pytest --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=65
python scripts/check_coverage_thresholds.py --xml coverage.xml \
  --min app/services/auth_service.py=72 \
  --min app/diet=55 \
  --min app/agent=55 \
  --min app/rag=80 \
  --min app/security=60
```

Frontend:

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215/frontend
npm ci
npm run lint
npm run test:coverage
npm run build
```

Optional E2E (Playwright):

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215/frontend
npx playwright install chromium

export PLAYWRIGHT_BASE_URL="https://<your-frontend>"
export E2E_USERNAME="..."
export E2E_PASSWORD="..."
npm run test:e2e
```

## Production Acceptance

### 1) Connectivity script (register/login + CORS)

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215
bash scripts/test-connection.sh \
  "https://cookhero-collab-20260215.onrender.com" \
  "https://frontend-one-gray-39.vercel.app"
```

### 2) Smoke script (demo-stable default)

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215
FRONTEND_URL="https://frontend-one-gray-39.vercel.app" \
BACKEND_URL="https://cookhero-collab-20260215.onrender.com" \
./scripts/smoke-prod.sh
```

### 3) Smoke script (strict mode)

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215
FRONTEND_URL="https://frontend-one-gray-39.vercel.app" \
BACKEND_URL="https://cookhero-collab-20260215.onrender.com" \
SMOKE_USERNAME="<smoke_user>" \
SMOKE_PASSWORD="<smoke_password>" \
MCP_SERVICE_KEY="<mcp_diet_service_key>" \
SMOKE_STRICT="true" \
./scripts/smoke-prod.sh
```

## Required Secrets / Env (Minimum Set)

Local (to fully pass streaming gate):
- `JWT_SECRET_KEY` (stable, >= 32 chars)
- `LLM_API_KEY` (required for conversation/agent success path)
- Optional: `FAST_LLM_API_KEY`, `VISION_API_KEY`, `WEB_SEARCH_API_KEY`, `RERANKER_API_KEY`

Production (platform env):
- Render (backend): `JWT_SECRET_KEY`, `DATABASE_URL` (recommended), `CORS_ALLOW_ORIGINS`,
  `CORS_ALLOW_ORIGIN_REGEX`, plus optional LLM keys as above.
- Vercel (frontend): `VITE_API_BASE=/api/v1`

GitHub Actions (recommended secrets):
- `PROD_FRONTEND_URL`
- `PROD_BACKEND_URL`
- `SMOKE_USERNAME` / `SMOKE_PASSWORD` (required for strict auth checks)
- `MCP_DIET_SERVICE_KEY` (used as `MCP_SERVICE_KEY` in smoke job)
- `RENDER_API_KEY` + `RENDER_SERVICE_ID` or `RENDER_SERVICE_NAME` (for cloud-config-sync)

## Wave Acceptance Add-ons

- Wave 3 (photo-first diet logging): see `docs/WAVE3_PHOTO_FIRST_DIET_LOG_ACCEPTANCE.md`.
  - Optional smoke: set `SMOKE_DIET_PHOTO=true` when running `scripts/smoke-prod.sh` (recommend `REQUEST_TIMEOUT_SECONDS=90`).
  - Optional inputs: `SMOKE_PHOTO_IMAGE_B64`, `SMOKE_PHOTO_MIME_TYPE`, `SMOKE_PHOTO_CONTEXT_TEXT`.

## High Risk Items (Must Track)

- HIGH RISK: SSE queue growth on client disconnect.
  Conversation endpoint uses an unbounded `asyncio.Queue` while the background task keeps producing tokens.
  If clients disconnect frequently during long generations, memory can grow.

- HIGH RISK: Rate limiter can silently become a no-op if enabled without Redis wiring.
  `RateLimiter` allows all requests when Redis client is not set. Redis is currently injected only when
  `RAG_INIT_ON_STARTUP=true` during startup.

- RISK: Running on Apple/Xcode Python (LibreSSL) may cause TLS issues.
  Prefer Python 3.12+ with OpenSSL for parity with CI/cloud.
