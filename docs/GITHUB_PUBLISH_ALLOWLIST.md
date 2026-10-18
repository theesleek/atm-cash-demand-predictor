# GitHub Publish Allowlist

Prepared 2026-10-18. This is a review allowlist, not a staging or commit instruction.

## Include after review

Include the tracked application, test, configuration, documentation, workflow, and project files, except for the explicit exclusions below. The required deployment set is:

- `backend/Dockerfile`
- `frontend/Dockerfile`
- `frontend/package.json`
- `frontend/package-lock.json`
- `requirements.txt`
- `alembic.ini`
- `docker-compose.yml`
- `docker-compose.production.yml`
- `.github/workflows/ci.yml`
- `backend/alembic/env.py`
- `backend/alembic/versions/0001_initial_schema.py`
- `backend/alembic/versions/0002_model_registry.py`
- `backend/alembic/versions/0003_atm_onboarding_ingestion.py`
- `backend/alembic/versions/0004_align_unique_indexes.py`
- `backend/app/` source files
- `frontend/src/` source files
- `backend/app/ml/artifacts/README.md`
- `backend/app/ml/artifacts/linear_regression.joblib`
- `backend/app/ml/artifacts/model_config.json`
- `backend/app/ml/artifacts/random_forest.joblib`
- `data/synthetic/sample_atm_data.csv`

The safe templates `.env.example` and `.env.production.example` may be included after confirming placeholders remain unchanged. The production template requires operators to replace every placeholder before deployment.

## Exclude

- `.env` and any environment file containing real values
- `atm_cash.db` and `test_atm_cash.db`
- `data/raw/tinkoff/train_kaggle.csv`
- `data/raw/tinkoff/test_file.csv`
- `data/processed/atm_daily_history.csv`
- `ANTIGRAVITY_MASTER_INSTRUCTIONS.md`
- all of `tmp/`
- `.venv/`, `node_modules/`, build output, caches, and test artifacts

The processed CSV is tracked and must be removed from the publish set. The raw datasets and processed CSV, as well as prior `tmp` paths, appear in Git history; publishing the existing history would preserve those paths and requires history sanitization before any public push.

## Manual review before staging

Modified tracked files:

`.gitignore`, `README.md`, `backend/app/api/routes/atms.py`, `backend/app/api/routes/auth.py`, `backend/app/core/permissions.py`, `backend/app/data/tinkoff_history.py`, `backend/app/db/session.py`, `backend/app/features/engineering.py`, `backend/app/main.py`, `backend/app/models/__init__.py`, `backend/app/models/atm.py`, `backend/app/repositories/user_repository.py`, `backend/app/schemas/atm.py`, `backend/app/services/atm_service.py`, `backend/app/services/auth_service.py`, `backend/app/services/forecast_service.py`, `backend/app/services/model_evaluation_service.py`, `backend/tests/test_auth.py`, `frontend/nginx.conf`, `frontend/src/App.jsx`, `frontend/src/api.js`, `frontend/src/auth.jsx`, `frontend/src/components/Navigation.jsx`, `frontend/src/pages/ATMNetworkPage.jsx`, `frontend/src/pages/AboutPage.jsx`, `frontend/src/pages/AlertsPage.jsx`, `frontend/src/pages/DashboardPage.jsx`, `frontend/src/pages/ForecastPage.jsx`, `frontend/src/pages/HomePage.jsx`, `frontend/src/pages/MissionPage.jsx`, `frontend/src/pages/ProfilePage.jsx`, `frontend/src/realtime.js`, `frontend/src/styles.css`.

Untracked release files:

- `backend/alembic/versions/0003_atm_onboarding_ingestion.py`
- `backend/alembic/versions/0004_align_unique_indexes.py`
- `backend/app/api/routes/data_imports.py`
- `backend/app/models/ingestion.py`
- `backend/app/services/ingestion_service.py`
- `backend/tests/test_data_provenance.py`
- `backend/tests/test_ingestion.py`
- `docker-compose.production.yml`
- `docs/DEPLOYMENT.md`
- `docs/MODEL_EVALUATION.md`
- `docs/PROJECT_ROADMAP.md`
- `docs/PROJECT_STATUS.md`
- `docs/RAW_SOURCE_ACQUISITION.md`
- `experiments/evaluate_production_forecast.py`
- `frontend/src/pages/ATMOnboardingPage.jsx`
- `frontend/src/pages/DataImportPage.jsx`
- `docs/GITHUB_PUBLISH_ALLOWLIST.md`

Review these paths for intended release scope and secrets before staging. No secret values were printed during this audit.

## Verification

- No files under `tmp/` are tracked; `tmp/` is now ignored.
- Required source, model artifacts, migrations, dependency manifests, and deployment files exist.
- `git diff --check` passed; Git reported only line-ending normalization warnings.
