# Project Status

## Verified snapshot

- **Audited:** 2026-10-18
- **Operating mode:** MVP RELEASE MODE
- **Branch:** `master`
- **Verified HEAD:** `77189fdf031cd55f4f0fe7de0c238b650a302031` (`Harden production runtime and model governance`)
- **Last known stable checkpoint:** `77189fd` is the latest committed hardening checkpoint. Earlier relevant commits are `1fa2001` (Phase 20 frontend polish/WebSocket support), `b4dc382` (auth/WebSocket integration), and `a9dab26` (responsive/accessibility audit).
- **Current phase:** Post-Phase-20 data onboarding, controlled history ingestion, forecast evaluation, and PostgreSQL migration validation. The implementation, migration fix, and evaluation artifacts are present as uncommitted work and require review/checkpoint approval.

## Executive state

**MVP RELEASE MODE — LOCALLY VALIDATED, NOT DEPLOYED.** The local suite, disposable SQLite migration sequence, disposable PostgreSQL migration sequence, schema checks, frontend production build, isolated Docker Compose startup, healthy-service checks, PostgreSQL smoke test, and time-safe signed-flow evaluation pass. Prior authorized local source evidence reproduced the historical signed-flow target, but that source data is excluded from this publishing snapshot; its units and operation-type semantics remain unverified, so withdrawal-demand or replenishment accuracy is not claimed. Full end-to-end HTTPS validation and external notification delivery remain unverified.

## Baseline evidence

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `.\\.venv\\Scripts\\python.exe -m pytest -q` | **97 passed, 1 skipped, 3 warnings** in 119.68s |
| Frontend build | `npm.cmd --prefix frontend run build` | **Passed**; Vite transformed 2725 modules |
| Python syntax/import compilation | `.\\.venv\\Scripts\\python.exe -m compileall -q backend/app backend/tests` | **Passed** |
| Whitespace/conflict check | `git diff --check` | **Passed**; line-ending warnings only |
| PostgreSQL integration | `RUN_POSTGRES_INTEGRATION=1 ... backend/tests/integration/test_postgres_smoke.py` | **Passed**; `1 passed` against the isolated migrated PostgreSQL service on host port `55433` |
| Disposable PostgreSQL migration sequence | PostgreSQL 16 volume-free container; readiness, `upgrade head`, repeat upgrade, `alembic check`, downgrade to `0002_model_registry`, re-upgrade | **Passed**; `0004_align_unique_indexes` corrected the confirmed unique-constraint/index mismatch |
| Docker Compose integration | Unique project, temporary `!override` port mappings, PostgreSQL `tmpfs`, `docker compose config`, no rebuild, bounded health check, service logs, PostgreSQL smoke test, labelled cleanup | **Passed**; backend, worker, frontend, and PostgreSQL started healthy on `58000`, `53000`, and `55433`; cleanup removed only this run's labelled containers/network and preserved images/volumes |
| Local migration state | `.\\.venv\\Scripts\\alembic.exe -c alembic.ini current` | Command exited successfully but reported no revision identifier; migration application is **not verified** |
| Disposable migration sequence | `alembic upgrade head`, `alembic check`, `downgrade 0002_model_registry`, re-upgrade | **Passed** on isolated SQLite; head/check/downgrade/re-upgrade sequence was consistent |
| Migrated schema comparison | Disposable SQLite upgrade plus SQLAlchemy metadata inspection | **Passed**; expected tables and model columns were present |

The PostgreSQL smoke test is opt-in and passed against the isolated Compose database after the temporary override was corrected to replace, rather than append to, the original host port mappings. The successful Compose run used a unique project, remapped ports, PostgreSQL `tmpfs`, existing images without rebuilding, a bounded health check, and verified labelled cleanup; no existing `atm-postgres` container, project volume, or image was modified. Full end-to-end validation, including broader application workflows and external notification delivery, remains outstanding. The three warnings are FastAPI/Starlette deprecations, including the legacy `on_event` startup hook.

### PostgreSQL migration evidence

The first disposable PostgreSQL run reached `alembic check` but detected five unique-constraint/index mismatches between migration history and SQLAlchemy metadata. The corrective uncommitted revision `backend/alembic/versions/0004_align_unique_indexes.py` converts those objects to the model-declared unique indexes and provides a reverse downgrade. The rerun passed readiness, both upgrades, `alembic check` (`No new upgrade operations detected.`), downgrade to `0002_model_registry`, and final upgrade. Run logs are under `tmp/postgres-20261018-124923-e024b352-*.log`.

The first disposable SQLite run confirmed that direct constraint alteration is unsupported by SQLite. Revision `0004` now uses batch table recreation for SQLite, and revision `0003` uses `sa.Double()` for `amount` so SQLite metadata matches the model. The final SQLite run passed upgrade, `alembic check`, downgrade to `0002_model_registry`, and re-upgrade; logs are under `tmp/sqlite-20261018-131914-8db57de8-*.log`.

## Forecast evaluation evidence

The corrected reproducible evaluator in `experiments/evaluate_production_forecast.py` measured 8,461 processed ATM-day rows across 20 ATMs and 479 dates. It excludes 109 source placeholders, 20 candidates without a next calendar-day record, and 69 candidates whose next day is a placeholder, leaving 8,263 valid exact-next-day targets. On the 1,840-row unique-date chronological holdout, the persisted ensemble scored MAE **252.53**, RMSE **350.72**, and WAPE **63.67%**; the retrained equivalent scored MAE **254.87**, RMSE **359.59**, and WAPE **64.26%**. The expanding historical mean scored 286.53 / 406.10 / 72.24%; the previous-week same-weekday baseline scored 332.72 / 451.96 / 83.89%. Earlier 1,920-row metrics are retained in `MODEL_EVALUATION.md` as results from the former next-available-row methodology.

Across five 14-day rolling-origin folds, the persisted ensemble and retrained equivalent both beat both baselines. This supports **PROMISING BUT NOT YET VALIDATED**, not pilot validation: the target is signed `daily_cash_flow` with 1,591 negative rows, the original artifact training procedure is not reproducible from the repository, and aligned shortage/inventory/replenishment outcomes are unavailable. Full methodology and per-ATM results are in `docs/MODEL_EVALUATION.md`.

### Target audit outcome

Prior authorized local evidence from `train_kaggle.csv` reproduced the raw-backed signed-flow records under the official ATM-day sum definition. The raw file and processed CSV are excluded from this publishing snapshot; the units, operation-type semantics, and missing-row construction remain unverified.

The six numeric operation-type codes lack a supplied official code dictionary, and multiple codes contain both positive and negative amounts. The source documentation calls `operation_value` a value but does not establish its unit locally. Negative values are therefore retained signed values with unverified business semantics; no clipping or synthetic demand target was introduced. The current forecast target remains **next-day signed net cash flow in unspecified source units**, not verified withdrawal demand.

The official Kaggle source page identifies `train_kaggle.csv`, `test_kaggle.csv`, and `kaggle_partners_2015_2016.csv`, with raw fields such as `atm_id`, `datetime`, `operation_type`, `operation_value`, `trxn_amt_rub`, and `trxn_cnt`. Prior authorized local evidence from `train_kaggle.csv` reproduced the signed processed target under the official ATM-day sum definition; the raw file is not included here. The source page and local evidence still do not resolve the monetary unit, operation-type semantics, missing-row construction, or governed ATM mapping; withdrawal-demand derivation remains blocked.

The evaluation and model-evaluation service now align targets only to the actual next calendar date within each ATM. They exclude absent next dates and missing placeholders; no later available observation is labelled one day ahead. The persisted artifact was not replaced because its original training procedure is unavailable.

Focused provenance tests now verify the processed schema, signed negative values, missing-row invariants, genuine observed zero rows, and the loader’s duplicate policy. They do not claim that the historical aggregation formula has been reproduced.

## Current uncommitted changes

The following files are changed or new and should be reviewed as one proposed checkpoint:

- README and backend changes for ATM metadata, lifecycle handling, readiness, uploaded history, and forecast integration.
- `backend/alembic/versions/0003_atm_onboarding_ingestion.py`
- `backend/alembic/versions/0004_align_unique_indexes.py`
- `backend/app/api/routes/data_imports.py`, `backend/app/models/ingestion.py`, and `backend/app/services/ingestion_service.py`
- `backend/tests/test_ingestion.py`
- `experiments/evaluate_production_forecast.py`
- `docs/MODEL_EVALUATION.md`
- `backend/alembic/versions/0003_atm_onboarding_ingestion.py` uses `sa.Double()` for the ingestion amount field, and `0004_align_unique_indexes.py` uses SQLite batch alteration while retaining direct PostgreSQL operations.
- `frontend/src/pages/ATMOnboardingPage.jsx`, `frontend/src/pages/DataImportPage.jsx`, plus route/API/navigation/network styling updates.

The ingestion test module now covers missing required columns, malformed and duplicate records, unauthorized upload/list access, successful approval/ingestion, repeated-import idempotency, audit events, readiness, and rollback after a simulated commit failure.

### Exact current working-tree scope

`README.md`; `backend/alembic/versions/0003_atm_onboarding_ingestion.py`; `backend/alembic/versions/0004_align_unique_indexes.py`; `backend/app/api/routes/atms.py`; `backend/app/api/routes/data_imports.py`; `backend/app/core/permissions.py`; `backend/app/data/tinkoff_history.py`; `backend/app/db/session.py`; `backend/app/main.py`; `backend/app/models/__init__.py`; `backend/app/models/atm.py`; `backend/app/models/ingestion.py`; `backend/app/schemas/atm.py`; `backend/app/services/atm_service.py`; `backend/app/services/forecast_service.py`; `backend/app/services/ingestion_service.py`; `backend/tests/test_ingestion.py`; `docs/MODEL_EVALUATION.md`; `docs/PROJECT_ROADMAP.md`; `docs/PROJECT_STATUS.md`; `experiments/evaluate_production_forecast.py`; `frontend/src/App.jsx`; `frontend/src/api.js`; `frontend/src/components/Navigation.jsx`; `frontend/src/pages/ATMNetworkPage.jsx`; `frontend/src/pages/ATMOnboardingPage.jsx`; `frontend/src/pages/DataImportPage.jsx`; `frontend/src/styles.css`.

No commit was created. No destructive Git operation was used. The local `.env`, SQLite databases, caches, and frontend build output were not added to the proposed scope.

## Architecture and key locations

- **Backend entry point:** `backend/app/main.py`
- **API routes:** `backend/app/api/routes/`
- **Authentication/RBAC:** `backend/app/core/security.py`, `backend/app/core/permissions.py`, `backend/app/api/routes/auth.py`
- **Forecasting and risk:** `backend/app/services/forecast_service.py`, `backend/app/services/risk_service.py`, `backend/app/ml/`
- **Replenishment workflow:** `backend/app/services/replenishment_service.py`, `backend/app/api/routes/replenishments.py`
- **Notifications:** `backend/app/services/notification_service.py`, `backend/app/api/routes/notifications.py`
- **Realtime:** `backend/app/realtime.py`, `backend/app/api/routes/websocket.py`, `frontend/src/realtime.js`
- **Persistence/migrations:** `backend/app/models/`, `backend/alembic/versions/`
- **Frontend entry point:** `frontend/src/App.jsx`; dashboard pages are under `frontend/src/pages/`

The application supports SQLite for local development/tests and PostgreSQL for production-like operation. Production startup expects an already migrated database and does not call `create_all`.

## Verified, partial, and missing capabilities

Verified complete or substantially implemented: multi-ATM entities and network views; per-ATM forecast/risk/replenishment workflow; authenticated JWT sessions and RBAC; audit records; protected WebSocket handshake and reconnect cleanup; alert and notification persistence; model metadata/checksum checks; bounded reads, health/readiness, request IDs, security headers, rate limiting, Docker/CI configuration, and responsive frontend foundations.

Partial or requiring deployment validation: operational CSV onboarding and validation (SQLite/API-tested; SQLite and PostgreSQL migration paths verified, full onboarding deployment unverified); forecasting pilot validation; future cash-balance projections; model explanation and confidence presentation; data lineage/freshness; full end-to-end Docker workflow validation; Telegram/SMTP delivery; and production identity mapping for uploaded ATM history.

Missing or planned: what-if simulation; route optimization; anomaly detection; model drift/retraining governance; reports/exports; coordinate-backed maps; external metrics storage; and optional deployment automation.

## Environment and commands

Required environment variable **names** are documented in `.env.example`; values must remain local. Important groups include `DATABASE_URL`, `JWT_SECRET_KEY`, bootstrap admin variables, `CORS_ORIGINS`, notification settings, and `ATM_DAILY_HISTORY_PATH`/risk configuration where applicable.

```powershell
.\.venv\Scripts\alembic.exe -c alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd --prefix frontend run build
```

Run PostgreSQL integration only with a disposable/migrated PostgreSQL service and `RUN_POSTGRES_INTEGRATION=1`.

## Next priorities

1. Complete full end-to-end Docker Compose workflow validation; acceptance: health/readiness, backend startup, worker recovery, frontend/API workflow coverage, and integration tests pass against the reviewed migration head.
2. Obtain authorized raw operation-level history and reproduce the processed target; acceptance: source files/version, formula, units, sign convention, missingness policy, ATM mapping, duplicate policy, and record-level comparison are documented and repeatable.
3. Align cash-on-hand, capacity, replenishment, and cash-out outcomes; acceptance: shortage, excess-cash, and replenishment-frequency consequences can be measured without synthetic substitution.
4. Replace prototype ATM identity mapping with governed model/data identity metadata; acceptance: compatible uploaded history becomes forecast-ready without hard-coded mapping.
5. Validate Telegram/SMTP delivery once configured; acceptance: external delivery and worker retry behavior are documented with real command output.

## Decisions to preserve

- Final replenishment approval remains backend-enforced and web-only.
- Do not fabricate forecast data or metrics when history/model compatibility is unavailable.
- Production startup must use reviewed Alembic migrations rather than `create_all`.
- Secrets belong in environment/configuration, never source or status documentation.
