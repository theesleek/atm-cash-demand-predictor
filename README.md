# ATM Cash Intelligence & Automated Replenishment Platform

## Purpose

The ATM Cash Intelligence & Automated Replenishment Platform is a multi-ATM operational intelligence system that forecasts cash demand, monitors estimated cash availability, identifies possible cash depletion, recommends replenishment actions, and routes alerts to authorized personnel.

The platform is designed as a predictive decision-support layer that can work alongside existing ATM or banking operational systems. It does not attempt to replace production banking infrastructure.

## Core Objectives

- Forecast next-day signed net cash flow for multiple ATMs.
- Estimate when an ATM may fall below a configured safety threshold.
- Recommend replenishment quantity and priority.
- Support web notifications; Telegram and SMTP delivery remain optional and deployment-specific.
- Allow acknowledgement from Telegram while reserving final replenishment approval for the authenticated web application.
- Maintain centralized activity and audit logs.
- Support role-based access and secure authentication.
- Run as a zero-budget prototype using synthetic, public, or approved data.

## Technology Stack

### Backend

- Python 3.12.7
- FastAPI
- Pydantic
- SQLAlchemy
- Pytest / HTTPX

### Frontend

- React
- Vite
- JavaScript / HTML / CSS
- Recharts for dashboards and analytics
- Leaflet + OpenStreetMap for ATM maps
- WebSockets for real-time updates

### Database

- PostgreSQL
- PostgreSQL driver through SQLAlchemy

### Data and Machine Learning

- Pandas
- NumPy
- Scikit-learn 1.6.1 (required to load the trained model artifacts)
- XGBoost
- LightGBM
- Statsmodels for ARIMA/SARIMA
- Prophet where useful for benchmark experiments
- Optional LSTM experiment when justified by data and validation
- SHAP for model explainability where compatible
- Joblib for model artifact persistence

### Integrations and Infrastructure

- Telegram Bot API
- SMTP/email
- Docker / Docker Compose
- Git / GitHub
- GitHub Actions

AWS can be considered as an optional deployment target later; it is not required for the zero-budget prototype.

## High-Level Architecture

```text
ATM / BANK DATA
      |
      v
DATA INGESTION
      |
      v
VALIDATION / CLEANING
      |
      v
POSTGRESQL  <---->  REPOSITORY / DATA ACCESS
      |
      v
FEATURE ENGINEERING / EDA
      |
      v
FORECASTING SERVICE
      |
      v
RISK / DEPLETION ENGINE
      |
      v
ALERT SERVICE
      |
      +-------------------+------------------+
      |                   |                  |
      v                   v                  v
    WEB              TELEGRAM             EMAIL
      |
      v
FINAL REPLENISHMENT APPROVAL
         (WEB ONLY)
      |
      v
REPLENISHMENT WORKFLOW
      |
      v
AUDIT / ACTIVITY LOG
```

## Forecasting Approach

Initial target: **next-day signed net cash flow per ATM**. This is not a verified withdrawal-demand target.

Core features include historical demand lags, rolling statistics, transaction counts, average withdrawal amount, calendar effects, holidays, month-end effects, current cash, ATM capacity, replenishment history and operational status.

### Forecast History

Production forecasts use approved history uploaded through the application and stored in PostgreSQL. The excluded private processed CSV is not required at startup or during normal operation. Local evaluation may use an explicitly supplied history file with `experiments/evaluate_production_forecast.py --history <path>`.

The application-to-Tinkoff ID pairing in `backend/app/data/tinkoff_history.py` is **prototype-only** and must be replaced with an approved identity mapping before operational use. It can be overridden using `PROTOTYPE_ATM_ID_MAP` as a JSON object, for example `{"ATM-001":74}`.

Risk thresholds and the replenishment safety buffer are fractions of predicted daily demand. Configure them with `RISK_WARNING_THRESHOLD` (default `1.0`), `RISK_HIGH_THRESHOLD` (`0.5`), `RISK_CRITICAL_THRESHOLD` (`0.25`), and `RISK_SAFETY_BUFFER` (`0.25`).

Contextual features can be tested where data is available, including UPI/digital-payment activity, card/POS activity, payroll periods, local events or footfall, weather, nearby ATM density, service outages and relevant policy changes. These are candidate predictors to be evaluated rather than assumed causal factors.

The model evaluation path is:

```text
Naive baseline
    -> Linear Regression
    -> Random Forest
    -> XGBoost
    -> LightGBM
    -> ARIMA / SARIMA
    -> Prophet
    -> Optional LSTM
```

Forecasting uses chronological train/validation/test splits or walk-forward evaluation. Main metrics are MAE, RMSE and a justified percentage metric such as sMAPE, with under-forecasting bias/rate tracked where useful.

## Main Database Entities

- BANK
- REGION
- BRANCH
- LOCATION
- ATM
- TRANSACTION
- CASH_INVENTORY
- REPLENISHMENT
- CALENDAR_EVENT
- FEATURE_SET
- MODEL
- FORECAST
- ALERT
- NOTIFICATION
- USER
- ROLE
- AUDIT_LOG

## Application Workflow

1. Approved ATM and transaction data is ingested.
2. Data is validated, cleaned and transformed.
3. Daily ATM demand features are generated.
4. The forecasting service predicts future cash demand for each ATM.
5. The risk engine estimates possible cash depletion using forecast demand, current cash and configured thresholds.
6. Alerts and replenishment recommendations are created when required.
7. Alerts are persisted for the web application; Telegram/SMTP delivery requires separate live-service verification.
8. Users can acknowledge alerts through Telegram or the web application.
9. Final replenishment approval is performed only by an authorized web user.
10. The decision and subsequent status changes are written to the audit log and synchronized back to the dashboard.

## Security

- Authentication and role-based authorization.
- JWT/token-based API authorization for protected backend requests.
- Set `JWT_SECRET_KEY` to a secret of at least 32 characters and optionally set `JWT_EXPIRATION_MINUTES` (default: 30).
- Set `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` to create the initial `SUPER_ADMIN`; administer subsequent users through the authenticated user-management API.
- Logout increments the user's token version, invalidating all tokens issued before logout.
- Replenishment approval permission is reserved for `BANK_MANAGER` and `SUPER_ADMIN`; approval requires an authenticated token and `X-Action-Source: WEB`.
- `SUPER_ADMIN` manages users; `BANK_MANAGER` reviews, rejects, schedules, completes, and web-approves replenishments; `OPERATIONS_OFFICER` creates and manages own requests, schedules/completes them, and handles alerts; `ANALYST` and `VIEWER` have read-only dashboard/forecast/alert access.
- Replenishment requests link to an ATM and optional forecast, use persisted lifecycle states, and emit audit records for creation and transitions.
- Configure `JWT_SECRET_KEY` and, for initial administration, both `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` before startup. Bootstrap credentials are not written to source or returned by the API.
- Frontend is never allowed to connect directly to PostgreSQL.
- Telegram identity is linked to a web user through a controlled account-linking flow; Telegram usernames are not trusted as authoritative identity.
- State-changing actions pass through backend authorization checks.
- Secrets remain in environment/configuration, not source code.
- Prototype data must be synthetic, public or explicitly approved.

## Telegram local development

The Telegram webhook endpoint is `POST /notifications/telegram/webhook`. Telegram requires a public HTTPS URL, so a local server must be exposed through a free HTTPS tunnel such as `cloudflared tunnel --url http://127.0.0.1:8000` during development. Set `TELEGRAM_WEBHOOK_URL` to the tunnel URL plus `/notifications/telegram/webhook`, set `TELEGRAM_WEBHOOK_SECRET`, and restart the backend. When `TELEGRAM_WEBHOOK_URL` is configured, startup registers that endpoint with Telegram using the configured secret. Keep the tunnel limited to the backend port and do not expose `.env` or other unrelated services.

Set `TELEGRAM_BOT_USERNAME` to the non-secret bot username if the web Profile page should show a direct Telegram link. The bot token and webhook secret remain server-side only.

## Suggested Repository Structure

```text
atm-cash-intelligence/
|
+-- backend/
|   +-- app/
|   |   +-- api/
|   |   +-- core/
|   |   +-- models/
|   |   +-- schemas/
|   |   +-- services/
|   |   +-- repositories/
|   |   +-- security/
|   |   +-- integrations/
|   |   +-- ml/
|   |   +-- main.py
|   +-- tests/
|
+-- frontend/
|   +-- src/
|   |   +-- components/
|   |   +-- pages/
|   |   +-- services/
|   |   +-- hooks/
|   |   +-- charts/
|   |   +-- maps/
|   |   +-- App.jsx
|   |   +-- main.jsx
|
+-- data/
|   +-- raw/
|   +-- processed/
|   +-- synthetic/
|
+-- experiments/
|   +-- 01_baseline.py
|   +-- 02_linear_regression.py
|   +-- 03_random_forest.py
|   +-- 04_xgboost.py
|   +-- 05_lightgbm.py
|   +-- 06_arima.py
|   +-- 07_sarima.py
|   +-- 08_prophet.py
|   +-- 09_lstm.py
|   +-- compare_models.py
|
+-- docs/
+-- docker-compose.yml
+-- README.md
```

## Development Rules

- Build the prototype in phases and keep each layer separated.
- Use VS Code and normal Python scripts for model experiments; Jupyter is not required.
- Do not use random train/test splits as the main forecasting evaluation method.
- Do not fabricate metrics or claim target achievement before running experiments.
- Preserve a reproducible data pipeline from raw data to features to forecast.
- Keep final approval rules in the backend, not only in the UI.
- Record important state changes in the audit trail.

## Current Status

This publishing snapshot is an MVP candidate validated locally, not a claim of live deployment or production readiness. Local tests, Compose startup, PostgreSQL smoke coverage and signed-flow evaluation are documented; HTTPS deployment, broader end-to-end workflow checks, external notification delivery and withdrawal-demand validation remain outstanding.
## Current ML Status

The forecasting module uses a processed file attributed to the public Tinkoff ATM
Competition dataset from Kaggle. The repository does not include the authorized
raw training files or the transformation script, so the historical aggregation,
units, sign convention, and missing-row construction cannot currently be reproduced.
The checked-in model therefore forecasts signed `daily_cash_flow`, not a verified
withdrawal-demand target.

The local evaluation recorded metrics for the 50/50 ensemble on signed
`daily_cash_flow`. These results are not evidence of verified withdrawal-demand
accuracy or a live production deployment. Real trained model artifacts are
integrated into the FastAPI inference layer using Python 3.12.7 and
scikit-learn 1.6.1.

Detailed signed-flow evaluation, provenance limitations, and the next source-data
acceptance gate are documented in `docs/MODEL_EVALUATION.md`.

## Production hardening and operations

The application keeps a simple SQLite mode for local development and tests. Production-like deployments use PostgreSQL through SQLAlchemy. Set `ENVIRONMENT=production`, a PostgreSQL `DATABASE_URL`, a 32-character-or-longer `JWT_SECRET_KEY`, explicit `CORS_ORIGINS`, and the bootstrap administrator variables before starting.

### Database and migrations

Development startup may create the local SQLite schema and seed synthetic ATM/security data. Production startup does not call `create_all`; it expects an already migrated database.

```powershell
\.venv\Scripts\alembic.exe -c alembic.ini upgrade head
\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

The initial schema is in `backend/alembic/versions/0001_initial_schema.py`. Future schema changes must be added as reviewed Alembic revisions. Never run destructive migration commands against production without a backup and an approved rollback plan.

### Runtime checks and security controls

- `GET /health` reports process liveness; `GET /health/ready` verifies database connectivity.
- Responses include a request ID and baseline security headers. Request logs include method, endpoint, status, latency and request ID without credentials or tokens.
- Production CORS is allow-list based. Login failures are throttled per client and username using the PostgreSQL/SQLite `rate_limit_states` table, so replicas can share the limiter when they use the same database. The default is 5 failures per 60 seconds with a 300-second block; rejected requests return HTTP 429 and `Retry-After`.
- Collection endpoints cap `limit` at 500 and support `offset` where applicable.
- Alert and replenishment transitions use database row locks where supported, commit audit records with the state change, roll back failed transactions, and dispatch notifications after persistence.
- Replenishment approval remains web-only and all authorization is enforced server-side.

### Local production-like Docker stack

`docker compose up --build` starts PostgreSQL, the migrated backend, a persistent database-backed notification worker, and an Nginx-served frontend. Set `JWT_SECRET_KEY` and `BOOTSTRAP_ADMIN_PASSWORD` in the shell or an untracked `.env` file first. PostgreSQL data is stored in the `postgres_data` volume. The backend and database have health checks and restart policies. The worker is run with `python -m app.jobs.worker` and is enabled through `ASYNC_NOTIFICATIONS=true`.

For the simplest production shape, use one Linux VPS with the reviewed `docker-compose.production.yml` override and a TLS reverse proxy in front of `127.0.0.1:8080`. The override keeps PostgreSQL and FastAPI private, builds the frontend with same-origin `/api` and `/ws/events` proxy paths, and preserves the PostgreSQL volume. Copy `.env.production.example` to an untracked `.env.production`, replace every placeholder, then follow `docs/DEPLOYMENT.md`. Do not treat the deployment as released until the documented HTTPS workflow checks pass.

### Notifications, Telegram, and WebSocket

Telegram remains webhook-authenticated with `X-Telegram-Bot-Api-Secret-Token`; webhook setup requires a public HTTPS tunnel during local development. Delivery attempts are persisted as `SENT` or `FAILED` records. The authenticated WebSocket requires the `atm-events` and `bearer.<JWT>` subprotocols and removes disconnected clients. Replenishment approval is never available through Telegram.

### ML and ingestion lifecycle

`GET /forecast/model-metadata` exposes the active production model identity, safe artifact identifiers, checksums, feature/dataset versions, evaluation metrics and sample count. It never exposes filesystem paths. An unevaluated model is not selected automatically. The processed Tinkoff history quality report includes source, row counts, rejected rows, duplicate counts, missing observations, validation candidates, processing time and a SHA-256 dataset version.

Production model loading verifies the checksums recorded in `model_config.json` and fails safely on missing or corrupt artifacts. ATM onboarding accepts CSV history through a staged `Dataset`/`DatasetVersion` workflow: upload, validate, approve, and ingest. Validation reports rejected rows and duplicate/unknown-ATM issues before production history changes. Forecast readiness requires at least 14 observed days; a new ATM without sufficient history returns a controlled unavailable state rather than a fabricated forecast. Uploaded history uses the existing production feature/model pipeline, and an ATM whose identity is not compatible with the production artifact remains unavailable until a compatible model is trained and governed.

### Background jobs and recovery

Jobs are stored in PostgreSQL/SQLite in `background_jobs` with a unique `(job_type, dedupe_key)` guard, retry counts, exponential backoff, terminal failure state, and failure visibility. Notification jobs are dispatched only after the originating business transaction has committed. A worker can process one job for a smoke test with `python -m app.jobs.worker --once` or run continuously with `python -m app.jobs.worker`.

For PostgreSQL backup and recovery, create a disposable dump with `pg_dump -Fc -d "$DATABASE_URL" -f backup.dump`, restore into a separate empty database with `pg_restore --clean --if-exists -d "$RESTORE_DATABASE_URL" backup.dump`, then run `alembic upgrade head` and verify health/readiness before switching traffic. Never restore over the live database during a recovery rehearsal.

### Testing and CI

Run the backend suite and frontend build locally:

```powershell
\.venv\Scripts\python.exe -m pytest -q
$env:RUN_POSTGRES_INTEGRATION=1; \.venv\Scripts\python.exe -m pytest backend/tests/integration -m integration -q
npm.cmd --prefix frontend run build
git diff --check
```

The PostgreSQL integration test expects `DATABASE_URL` to point at the migrated PostgreSQL service and is intentionally skipped unless `RUN_POSTGRES_INTEGRATION=1` is set. Unit tests continue to use isolated SQLite fixtures for speed. Forecast output is signed `daily_cash_flow` in source units; it is not a verified withdrawal-demand target.

GitHub Actions runs the backend tests and frontend production build on pushes and pull requests. `GET /metrics` exposes non-secret process counters for requests, latency, model failures, notifications, and worker outcomes. The MVP Compose path has been exercised with PostgreSQL, migrations, shared database rate limiting, persistent jobs, bounded reads, safe errors, request observability, and transactional safeguards; full end-to-end HTTPS workflow validation, external notification delivery, and model retraining governance remain deployment-specific.
