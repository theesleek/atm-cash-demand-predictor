# ATM Cash Intelligence

ATM Cash Intelligence is a FastAPI and React decision-support platform for
multi-ATM cash operations. It combines approved operational history, next-day
forecasting, cash-risk evaluation, alerts, and a controlled replenishment
workflow in one authenticated dashboard.

This repository is an MVP/portfolio project, not a replacement for core
banking or ATM infrastructure. Production deployment, external notification
delivery, and verified withdrawal-demand accuracy remain deployment-specific
work.

## Live Demo & Links

- [Open the live frontend](https://atm-cash-demand-predictor.pages.dev/) —
  hosted on Cloudflare Pages. The repository does not independently verify
  that every backend feature is currently available in production.
- [GitHub repository](https://github.com/theesleek/atm-cash-demand-predictor) —
  source code, documentation, and verification history.
- **Backend API and deployed API docs:** the repository does not record a
  verified Render service URL, so the production API, Swagger UI, and OpenAPI
  JSON links are intentionally not guessed. Supply the real Render URL before
  publishing those deployment links.

The application uses React/Vite and FastAPI with PostgreSQL-oriented
deployment, durable background jobs, and notification integrations. SMTP is
the default email mechanism; Gmail API is an optional provider.

## What is implemented

- Authenticated JWT sessions with role-based access control and audit logging.
- ATM onboarding and staged CSV history ingestion: upload, validate, approve,
  and ingest.
- Per-ATM forecast, readiness, risk, alert, and replenishment views.
- Durable notification outbox and database-backed jobs with retries,
  idempotency keys, claim fencing, and stale-lease recovery.
- Optional Telegram linking/webhooks and persisted delivery state.
- Daily forecast automation, disabled by default, with UTC-date job
  deduplication and stale-data safeguards.
- React/Vite dashboard with charts, ATM network views, WebSocket updates,
  health/readiness endpoints, request IDs, security headers, and rate limits.

Final replenishment approval is enforced in the backend and remains a web-only
operation.

## Access and deployment status

The Cloudflare Pages frontend origin is present in the backend CORS allowlist,
but the repository does not independently verify that this deployment is
currently live. A Render backend/service URL is not recorded in the repository;
the deployed backend and its `/docs` and `/openapi.json` endpoints therefore
remain to be confirmed.

The project remains documented as locally validated rather than production
released. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the deployment
procedure and release checks.

## Representative workflow

1. An authorized operator uploads operational ATM history as CSV.
2. The backend validates the schema, rows, timestamps, ATM identities,
   operation types, amounts, and duplicate records.
3. The operator reviews and approves the validated dataset before ingestion
   changes production history.
4. The forecasting service builds the approved ATM history features and
   produces a next-day forecast.
5. The risk engine evaluates projected cash against configured thresholds and
   creates or updates alerts.
6. Operators review replenishment recommendations, acknowledge alerts, and
   complete approval through the authenticated web workflow.
7. Notifications are persisted and, when configured and separately verified,
   delivered through the selected provider.

## Forecasting target and limitations

The implemented production target is **next-day signed net cash flow per ATM**
in the source dataset's units. It is not a verified withdrawal-only demand
target. A signed cash-flow value can include both withdrawal and deposit
activity, and the repository does not contain the authorized raw training data
or its original transformation script needed to independently verify the
source units, sign convention, and missing-row construction.

Forecast readiness requires at least 14 observed history days and a compatible
ATM identity mapping. The checked-in Tinkoff ATM mapping is prototype-only and
must be replaced or explicitly approved before operational use. Forecasts are
created for the next calendar day derived from the uploaded history; the
application does not treat forecasts as actual observations.

Risk thresholds and the replenishment safety buffer are configurable through:

- `RISK_WARNING_THRESHOLD` (default `1.0`)
- `RISK_HIGH_THRESHOLD` (default `0.5`)
- `RISK_CRITICAL_THRESHOLD` (default `0.25`)
- `RISK_SAFETY_BUFFER` (default `0.25`)

The model-evaluation methodology and its signed-flow limitations are described
in [docs/MODEL_EVALUATION.md](docs/MODEL_EVALUATION.md).

## CSV ingestion contract

Operational uploads require these headers:

```text
atm_id,datetime,operation_type,amount
```

The parser expects UTF-8 CSV data. Supported operation types include
`withdrawal`, `cash_withdrawal`, `deposit`, and `cash_deposit`. Validation
rejects missing or duplicate headers, unsupported columns, malformed CSV,
invalid row widths, invalid timestamps, unknown ATM IDs, invalid amounts, and
duplicate records. Upload validation creates a dataset-version record and
does not write operational history; approval and ingestion are separate steps.

Sample fixtures are available in
[backend/tests/fixtures](backend/tests/fixtures).

## Notifications and email

Notification events are written to the durable outbox after the originating
business transaction is persisted. Workers claim jobs with database locks and
claim tokens, retry transient failures with bounded backoff, and retain
delivery state as `SENT`, `FAILED`, or an intermediate state.

Email supports two implemented providers:

- **SMTP is the default.** The implementation requires `smtp.gmail.com` on
  port `587`, uses STARTTLS, and reads `SMTP_USERNAME`, `SMTP_PASSWORD`,
  `SMTP_FROM_EMAIL`, and `NOTIFICATION_EMAIL_RECIPIENTS` from configuration.
- **Gmail API is optional.** Set `NOTIFICATION_EMAIL_PROVIDER=gmail_api` and
  configure the `GMAIL_API_CLIENT_ID`, `GMAIL_API_CLIENT_SECRET`,
  `GMAIL_API_REFRESH_TOKEN`, and `GMAIL_API_SENDER_EMAIL` variable names when
  that provider is intentionally selected.

Neither external email delivery nor Telegram delivery is claimed as verified
by this repository snapshot. See
[docs/NOTIFICATION_RELIABILITY.md](docs/NOTIFICATION_RELIABILITY.md) and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Architecture and technology

```text
React/Vite dashboard
        |
        v
FastAPI API ---- WebSocket events
        |
        +--> SQLAlchemy repositories/services --> PostgreSQL
        |
        +--> Forecast and risk services
        |
        +--> Durable background jobs and notification outbox
```

Primary technologies:

- Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic, and Pytest
- PostgreSQL for production-like operation; SQLite for local development and
  isolated unit tests
- React, Vite, JavaScript, Recharts, Leaflet/OpenStreetMap, and WebSockets
- Pandas, NumPy, scikit-learn, XGBoost, LightGBM, Statsmodels, and Joblib
- Docker Compose for local production-like orchestration

## Local development

Create an environment, install the repository requirements, and keep
configuration values in an untracked environment file:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

For local development, the default database is SQLite. Start the API with:

```powershell
$env:PYTHONPATH = "backend"
$env:PYTHON_DOTENV_DISABLED = "1"
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

For production-like operation, set `ENVIRONMENT=production`, use PostgreSQL,
configure an allow-listed `CORS_ORIGINS`, and provide the required JWT and
bootstrap administrator configuration names. Do not put values or credentials
in source control.

The local API runs at `http://127.0.0.1:8000`. Use [local Swagger UI](http://127.0.0.1:8000/docs)
or [local OpenAPI JSON](http://127.0.0.1:8000/openapi.json) for local API
exploration. These are development links, not production deployment claims.

### Database migrations

Production startup expects an already migrated database and does not call
`create_all`. The current Alembic head is
`0008_forecast_date_required`, following
`0007_daily_forecast_uniqueness`.

Apply the reviewed chain through `head`:

```powershell
$env:PYTHONPATH = "backend"
python -m alembic upgrade head
```

Migration 0007 fails closed when duplicate
`(atm_id, forecast_date, model_version)` identities exist. Migration 0008
checks for existing `forecasts.forecast_date IS NULL` rows before enforcing
`NOT NULL`; it intentionally aborts with an actionable error when any are
found. Review and resolve those rows using authoritative data and an approved
data-maintenance procedure. Do not invent dates or delete records merely to
force migration success. Enable daily automation only after the migration
chain completes successfully. Always back up production data and use an
approved rollback plan before applying schema changes.

## Testing and verification

Run the local backend tests and frontend build when the required dependencies
are installed:

```powershell
python -m pytest -q
npm.cmd --prefix frontend run build
git diff --check
```

PostgreSQL integration tests require an explicitly configured disposable or
otherwise approved test database and the repository's safety opt-in. They are
not intended to run against production:

```powershell
$env:RUN_POSTGRES_INTEGRATION = "1"
python -m pytest backend/tests/integration -m integration -q
```

The reported local verification includes focused CSV, daily-automation,
notification, migration, PostgreSQL integration, smoke, and forecast-date
checks. The full backend suite, production database migration, live HTTPS
workflow, and external notification delivery remain unverified in this
snapshot. See [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) and
[docs/PROJECT_ROADMAP.md](docs/PROJECT_ROADMAP.md) for the current scope and
limitations.

## Repository documentation

- [Deployment procedure](docs/DEPLOYMENT.md)
- [Daily automation](docs/DAILY_AUTOMATION.md)
- [Notification reliability](docs/NOTIFICATION_RELIABILITY.md)
- [Model evaluation and provenance](docs/MODEL_EVALUATION.md)
- [Project status](docs/PROJECT_STATUS.md)
- [Project roadmap](docs/PROJECT_ROADMAP.md)
- [Raw-source acquisition notes](docs/RAW_SOURCE_ACQUISITION.md)
