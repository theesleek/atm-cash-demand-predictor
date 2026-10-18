# Project Roadmap

Status is based on repository evidence audited 2026-10-18. The project is in MVP RELEASE MODE; this is not a claim of production readiness until the deployment gate is verified.

## Priority order

1. Protect and validate data onboarding and migrations.
2. Govern ATM identity/model compatibility and forecast readiness.
3. Validate deployment, worker recovery, and external notification integrations.
4. Improve decision support and operational reporting.
5. Add advanced forecasting governance and optimization.

## Capability roadmap

| Area | Capability | Status | Evidence / next acceptance criterion |
| --- | --- | --- | --- |
| Cash intelligence | Multiple ATM entities and network comparison | COMPLETE | ATM model, network API, seeded data, and frontend network page exist. |
| Cash intelligence | Per-ATM demand forecast and cash-risk assessment | COMPLETE | Forecast, risk, readiness, and dashboard services/routes are implemented and tested. |
| Cash intelligence | Future cash-balance projection and time-to-cash-out | PARTIAL | Current risk uses current cash and predicted demand; validate multi-day projection semantics. |
| Cash intelligence | Replenishment quantity and priority recommendation | COMPLETE | Risk/replenishment services and lifecycle API are implemented and tested. |
| Cash intelligence | Route and timing optimization | PLANNED | Add constrained optimization only after reliable multi-ATM operational inputs exist. |
| Cash intelligence | Inventory, anomaly, and spike monitoring | PARTIAL | Inventory and risk signals exist; anomaly detection and root-cause workflows remain. |
| Decision support | What-if demand/replenishment simulator | PLANNED | Define scenarios, constraints, and reproducible result storage. |
| Decision support | Calendar, holiday, and seasonal features | PARTIAL | Calendar-oriented features exist in the ML path; holiday source and validation are incomplete. |
| Decision support | Chronological model comparison and metrics | COMPLETE | Experiment scripts, persisted artifacts, and evaluation API/report are present. |
| Decision support | Time-safe baseline comparison and rolling-origin forecast evaluation | PARTIAL | Calendar-aligned evaluation excludes absent/placeholder next dates and shows the ensemble beating measured baselines on signed prototype flow; approved demand semantics and reproducible artifact training provenance remain. |
| Decision support | Prediction/recommendation explanation and confidence | PARTIAL | Risk reasons and model metadata exist; user-facing confidence/explanations need expansion. |
| Decision support | Model versioning, drift, and retraining workflow | PARTIAL | Model registry/checksum governance exists; automated drift detection/retraining is missing. |
| Data reliability | CSV upload, validation, approval, and ingestion workflow | PARTIAL | SQLite/API workflow tests pass, including rollback and idempotency; SQLite and PostgreSQL migration paths are verified, but full onboarding deployment remains. |
| Data reliability | Missing, duplicate, outlier, and schema checks | PARTIAL | Validation reports and duplicate/unknown-ATM checks exist; broader outlier policy needs implementation. |
| Data reliability | Lineage and freshness | PARTIAL | Dataset versions and quality reporting exist; operational freshness monitoring is incomplete. |
| Data reliability | Reproducible historical signed-flow pipeline and source distinction | COMPLETE | Prior authorized local evidence from `train_kaggle.csv` reproduced the raw-backed processed ATM-days by summing `operation_value` per ATM/date. Raw/private source files and the processed CSV are excluded from this publishing snapshot; source metadata remains governed outside Git. |
| Data reliability | Approved withdrawal-demand target and raw-data lineage | BLOCKED | Current training/evaluation target is signed `daily_cash_flow` with unspecified units. The raw operation-type codes have no verified dictionary/sign-direction semantics, and balances, capacity, replenishment and cash-out outcomes are absent. |
| Data reliability | Approved public/open data source process | PARTIAL | Tinkoff-derived prototype data is documented; governed identity/license/source approval remains. |
| Frontend/operations | React dashboard for multiple ATMs | COMPLETE | Protected dashboard, network, forecast, alerts, replenishment, and onboarding pages exist. |
| Frontend/operations | Filters, charts, and operational views | PARTIAL | Filters/charts and responsive states exist; maps require real coordinates and broader comparison views. |
| Frontend/operations | Reports and exports | PLANNED | Define supported report formats and authorization before implementation. |
| Frontend/operations | In-app, Telegram, and email notifications | PARTIAL | Backend persistence/integration paths exist; external delivery requires environment and live-service validation. |
| Frontend/operations | Health, freshness, and service status | PARTIAL | Health/readiness and data-quality APIs exist; frontend operational status coverage is incomplete. |
| Operations | Shortage, excess-cash, and replenishment consequence measurement | BLOCKED | No aligned historical cash-on-hand, capacity, replenishment, or cash-out outcome data is present. |
| Frontend/operations | Realtime updates | COMPLETE | Authenticated WebSocket, event publishing, reconnect, and cleanup are implemented and tested. |
| Security/governance | Authentication and RBAC | COMPLETE | JWT, role permissions, protected routes, logout invalidation, and user management are implemented/tested. |
| Security/governance | Audit trail | COMPLETE | State-changing workflows record audit events and expose protected activity/history views. |
| Security/governance | API/WebSocket authorization and safe errors | COMPLETE | Server-side permissions, web-only approval, validation, bounded reads, headers, and generic errors exist. |
| Delivery | Docker local setup | PARTIAL | The corrected temporary override replaces original host ports with `55433`, `58000`, and `53000`, keeps PostgreSQL volume-free via `tmpfs`, and uses a unique project. Existing images started the full Compose service set healthy without rebuilding; the PostgreSQL smoke test passed (`1 passed`) and labelled cleanup was verified. Full end-to-end workflow validation remains outstanding. |
| Delivery | Environment documentation | COMPLETE | README and `.env.example` document configuration names and operational constraints. |
| Delivery | Automated tests and CI | COMPLETE | Pytest suite and GitHub Actions configuration are present; isolated PostgreSQL Compose runtime smoke evidence is now recorded, while broader CI/runtime coverage remains deployment-specific. |
| Delivery | Optional deployment automation | PLANNED | Keep cloud deployment optional and add only after local production-like validation. |

## Immediate acceptance gates

- The current uncommitted ingestion files are reviewed together and checkpointed only with explicit approval.
- Alembic revisions through `0004_align_unique_indexes` apply, re-apply, pass `alembic check`, downgrade to `0002_model_registry`, and restore safely on disposable PostgreSQL 16 and SQLite databases. Revision `0004` uses PostgreSQL direct operations and SQLite batch recreation for equivalent unique-index semantics.
- Upload validation cannot change production history before approval and ingestion.
- Forecasts remain unavailable when history is insufficient or model identity is incompatible.
- Forecast evaluation must use an approved target definition, declared training cutoff, chronological/rolling-origin splits, and operational outcomes before pilot claims are made.
- The current evaluation is only for exact-next-calendar-day signed net cash flow; it excludes absent and placeholder targets. Do not clip negative values or call it withdrawal demand. Acceptance for a demand pilot requires raw-source lineage, units/sign convention, missingness policy, nonnegative withdrawal labels, and repeatable rolling-origin results.
- Source reconstruction acceptance requires authorized raw files, source/version metadata, exact aggregation and sign mapping, ATM identity mapping, timezone/date handling, missingness and duplicate rules, and a record-level comparison against `data/processed/atm_daily_history.csv`.
- No secret values, generated databases, build output, or unrelated edits enter a checkpoint.
