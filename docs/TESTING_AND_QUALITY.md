# Testing And Quality Gates

This doc is a quick reference for running CookHero's test suite locally and
understanding the CI gates used to protect `main`.

## Backend

Run unit/integration tests:

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215
source .venv/bin/activate
pytest -q
```

Run with coverage (matches CI):

```bash
pytest --cov=app --cov-report=term-missing --cov-report=xml
```

Key package thresholds (used by CI to prevent "edge-only coverage"):

```bash
python scripts/check_coverage_thresholds.py --xml coverage.xml \
  --min app/services/auth_service.py=... \
  --min app/diet=... \
  --min app/agent=... \
  --min app/rag=... \
  --min app/security=...
```

The authoritative thresholds are in `.github/workflows/ci.yml`.

## Frontend

```bash
cd frontend
npm ci
npm run lint
npm run test:coverage
npm run build
```

## E2E (Playwright)

We run E2E against a deployed environment by default (GitHub Actions provides the
`PROD_FRONTEND_URL` + smoke-user credentials). Locally you can also run against
any base URL that serves the Vite app.

```bash
cd frontend
npx playwright install chromium

export PLAYWRIGHT_BASE_URL="https://<your-frontend>"
export E2E_USERNAME="..."
export E2E_PASSWORD="..."

npm run test:e2e
```

Workflow: `.github/workflows/e2e.yml` (scheduled + manual).

## Diet Goal-Source Regression Focus

For the metabolic profile / BMR-TDEE rollout and follow-up acceptance, keep these
checks in the default regression pack:

```bash
cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215
source .venv/bin/activate
pytest -q tests/test_diet_metabolic_profile_unit.py \
  tests/test_diet_goal_context_unit.py \
  tests/test_emotion_support_agent.py \
  tests/test_emotion_budget_service.py \
  tests/test_diet_replan_budget_features_unit.py

cd /Users/zjs/Desktop/code/COOK/cookhero-collab-20260215/frontend
npm test -- src/components/diet/DietPreferencesForm.test.tsx \
  src/components/diet/CalorieGoalSourceCard.test.tsx
```

Acceptance focus:

- Budget / weekly summary / replan flows stay aligned after updating metabolic profile.
- `goal_source` remains correctly surfaced for `tdee_estimate`, `avg7d`,
  `default1800`, and `explicit`.
- Incomplete metabolic profiles fall back safely without breaking goal context.
- Existing emotion exemption, rolling replan, and low-confidence food confirmation
  flows do not regress.

## Performance (k6)

We keep k6 focused on non-LLM endpoints. LLM/chat latency is tracked separately.

```bash
export BACKEND_URL="https://<your-backend>"
export SMOKE_USERNAME="..."
export SMOKE_PASSWORD="..."

k6 run tests/performance/non_llm_smoke.js
```

Workflow: `.github/workflows/perf-k6.yml` (manual).

## CI Workflows (GitHub Actions)

- `.github/workflows/ci.yml`: required checks (backend coverage gate + frontend lint/tests/build).
- `.github/workflows/security.yml`: CodeQL scanning (SAST) + scheduled runs.
- `.github/workflows/prod-smoke.yml`: production smoke test (scheduled + push main).
- `.github/workflows/cloud-config-sync.yml`: Render env sync + optional deploy trigger.
- `.github/workflows/e2e.yml`: Playwright E2E smoke (scheduled + manual).
- `.github/workflows/perf-k6.yml`: k6 non-LLM performance smoke (manual).
