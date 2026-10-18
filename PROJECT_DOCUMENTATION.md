# ATM Cash Intelligence & Automated Replenishment Platform

**Public technical documentation**

> Public MVP documentation. This is not an official bank, client, or vendor document.

| Field | Value |
|---|---|
| Document ID | ATM-CI-TDD-001 |
| Version | 1.0 |
| Status | Draft for Development / Review |
| Project Reference | P_136 |
| Domain | Banking / Data Analytics |
| Client Context | Generic ATM operations prototype |
| Primary Workstream | Aspirant 1 - Data Engineering |
| Date | 28 September 2026 |
| Classification | Internal Training / Prototype |

## 1. Executive Summary

The ATM Cash Intelligence & Automated Replenishment Platform is a multi-ATM operations prototype that ingests approved ATM history and inventory data, performs data quality and feature engineering, forecasts next-day signed net cash flow, estimates cash depletion risk, recommends replenishment, and presents alerts through a web dashboard. Telegram/email delivery and live bank integrations are deferred or deployment-specific. Final replenishment approval is web-authoritative and auditable.

The project brief specifies targets of **>=85% forecast accuracy** and **>=70% reduction in cash-outs/replenishment inefficiency**. These are target outcomes; the exact metric and baseline must be defined before claiming achievement.

## 2. Business Problem

ATM demand varies by time, location, ATM, customer activity and calendar effects. The project aims to reduce avoidable cash-outs and improve replenishment planning without making real cash movements in the prototype.

## 3. Scope

### In Scope
- Multi-ATM ingestion and data quality
- PostgreSQL persistence
- EDA and time-safe feature engineering
- Forecasting experiments and model evaluation
- Cash depletion risk
- Replenishment recommendation
- Web dashboard
- Telegram operations bot
- Email alerts
- RBAC/authentication
- Real-time web updates through WebSockets
- Final approval through web UI
- Audit logging
- Testing, Docker, Git, CI

### Out of Scope
- Direct production bank/ATM integration
- Real customer confidential data
- Real cash movement or financial transaction execution
- Mandatory paid services

## 4. Objectives
1. Forecast next-day signed net cash flow for multiple ATMs.
2. Build a reproducible data pipeline.
3. Detect projected cash depletion.
4. Recommend replenishment.
5. Notify authorized users.
6. Provide controlled web approval.
7. Keep optional notification integrations separate from the core web workflow.
8. Maintain auditability.
9. Operate with zero mandatory spend.

## 5. Architecture

```text
ATM / BANK DATA
      |
      v
DATA INGESTION -> VALIDATION -> CLEANING -> POSTGRESQL
                                           |
                                           v
                                   FEATURES / EDA
                                           |
                                           v
                                  FORECAST MODEL
                                           |
                                           v
                                     RISK ENGINE
                                           |
                                           v
                                  ALERT GENERATOR
                                     /    |    \
                                    /     |     \
                                 WEB  TELEGRAM  EMAIL
                                  |       |
                                  +---+---+
                                      |
                               FINAL APPROVAL
                                 (WEB ONLY)
                                      |
                              REPLENISHMENT
```

## 6. Technology Stack

| Area | Technology | Role |
|---|---|---|
| Language | Python 3.12.7 | Main implementation language and trained-artifact runtime |
| Data | NumPy, Pandas | Numerical and tabular processing |
| Database | PostgreSQL | Persistent operational data |
| DB layer | SQLAlchemy | Python/database integration |
| EDA | Matplotlib, Seaborn | Analytics and visualization |
| ML | Scikit-learn 1.6.1 | Trained pipelines, inference, metrics |
| Boosting | XGBoost, LightGBM | Tabular forecasting candidates |
| Time series | Statsmodels | ARIMA/SARIMA |
| Advanced ML | LSTM framework if justified | Optional sequence model |
| Explainability | SHAP | Model explanation where compatible |
| API | FastAPI, Pydantic | Backend services and validation |
| Auth | OAuth2/JWT approach | Authentication and token authorization |
| Frontend | React, Vite | Web dashboard |
| Charts | Recharts | Dashboard charts |
| Maps | Leaflet + OpenStreetMap | ATM map |
| Notifications | Telegram Bot API, SMTP/email | Alerts |
| Testing | Pytest, HTTPX | Automated tests |
| DevOps | Docker, Docker Compose | Reproducible runtime |
| Version control | Git/GitHub | Source management |
| CI | GitHub Actions | Automated checks |
| Enterprise target | AWS ECS | Optional deployment target |

## 7. Data Model

### Core Entities
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

### Key Relationships
```text
BANK 1:N REGION
REGION 1:N BRANCH
BRANCH 1:N ATM
LOCATION 1:N ATM
ATM 1:N TRANSACTION
ATM 1:N CASH_INVENTORY
ATM 1:N REPLENISHMENT
ATM 1:N FORECAST
MODEL 1:N FORECAST
FORECAST 1:N ALERT
ALERT 1:N NOTIFICATION
ROLE 1:N USER
USER 1:N AUDIT_LOG
```

## 8. Data Engineering

```text
Raw source -> schema validation -> data quality -> cleaning -> transformation -> daily ATM demand -> PostgreSQL -> feature generation
```

Validation must cover required fields, ATM IDs, timestamps, numeric amounts, duplicates and referential validity. Outliers must be investigated rather than blindly deleted.

## 9. EDA

Analyze: demand over time, demand by ATM, day-of-week effects, month/seasonality, holidays, transaction counts, average transaction amount, outliers and volatility.

## 10. Feature Engineering

Candidate features:
- Calendar: day_of_week, day_of_month, month, weekend, holiday, month_end.
- Lags: lag_1, lag_7, lag_14, optionally lag_28.
- Rolling: rolling_7, rolling_14, rolling_30.
- Transactions: transaction_count, average_transaction_amount.
- ATM context: historical mean/volatility and justified location/branch features.

Every feature must be available at prediction time.

## 11. ML Model Strategy

### Evaluation order
1. Naive baseline
2. Linear Regression
3. Random Forest
4. XGBoost
5. LightGBM
6. ARIMA
7. SARIMA
8. Prophet
9. LSTM (optional)

The final model is **not predetermined**. Use chronological validation and compare against the baseline using MAE, RMSE and a justified percentage metric such as sMAPE.

### Model roles
- **Linear Regression:** interpretable feature-based baseline.
- **Random Forest:** nonlinear tree benchmark.
- **XGBoost:** strong gradient-boosted tabular candidate.
- **LightGBM:** efficient boosted-tree candidate and likely practical production candidate if validated.
- **ARIMA:** single-series statistical benchmark.
- **SARIMA:** seasonal statistical benchmark.
- **Prophet:** trend/seasonality/holiday benchmark.
- **LSTM:** advanced sequence experiment only if data and validation justify it.

## 12. Forecasting and Risk

Initial target: **next-day cash demand per ATM**.

```text
projected_cash = current_cash - forecasted_demand
```

Suggested risk states: NORMAL, WARNING, HIGH, CRITICAL. Thresholds must be configurable.

Initial replenishment concept:

```text
required = forecast_demand + safety_buffer - current_cash
```

Apply ATM capacity and configurable operational rules.

## 13. Web + Telegram + Email

### Web
Dashboard, ATM details, forecasts, alerts, replenishment review/approval, analytics, model metrics, audit log, administration.

### Telegram
Use for alerts, status queries, ATM queries, forecast queries, acknowledgements and escalation. Telegram must not be final approval.

### Email
Use for critical/high alerts, approval reminders and delivery failures where configured.

### Real-time synchronization
Telegram action -> FastAPI -> PostgreSQL -> event -> WebSocket -> React update without manual refresh.

## 14. Authorization

Use role-based access control. Example roles: Super Admin, Bank Manager, Operations Officer, Analyst, Viewer. All Telegram actions must pass the same backend authorization checks as web actions. Telegram accounts must be linked to web users using a secure one-time token flow.

## 15. Approval Workflow

```text
Forecast -> Risk -> Alert -> Acknowledge -> Website Review -> Final Approval -> Replenishment Order -> Scheduled -> Completed -> Resolved
```

**Final approval is web-only and authorized.**

## 16. API

Initial endpoints can include:

```text
POST /auth/login
GET  /health
GET  /users/me
GET  /atms
GET  /atms/{atm_id}
GET  /forecasts/{atm_id}
POST /predict
GET  /alerts
GET  /alerts/{alert_id}
POST /alerts/{alert_id}/acknowledge
GET  /replenishments
POST /replenishments/{id}/approve
POST /replenishments/{id}/reject
GET  /activity
GET  /models
WS   /ws/events
```

## 17. Testing

Required layers: unit, data validation, ML, API, integration and end-to-end. Core E2E scenario:

```text
new data -> forecast -> critical risk -> alert -> Telegram/email/web -> Telegram acknowledgement -> web update -> web approval -> audit log -> resolution
```

## 18. Deployment

Develop locally first with VS Code, Python 3.12.7, scikit-learn 1.6.1, PostgreSQL and Docker Compose. The pinned scikit-learn version is required to load the supplied trained model artifacts. Kaggle can be used for dataset discovery and optional experiments, but is not a production dependency. AWS ECS is an optional enterprise target and not a zero-budget prerequisite.

## 19. APEX / EPIC Mapping

- **EPIC 1:** Data Collection & Data Engineering
- **EPIC 2:** Preprocessing, EDA & Modern Learning
- **EPIC 3:** Model & Pipeline Integration
- **Testing**
- **Use Cases**
- **Result & Presentation**

The exact meaning of APEX should follow the company's provided definition/template if one exists.

## 20. Key Risks

| Risk | Control |
|---|---|
| Poor data | Data-quality checks + public/synthetic fallback |
| Data leakage | Time-safe feature engineering and validation |
| Weak model | Baseline comparison + multiple candidates |
| Notification failure | Delivery status, retry/fallback where implemented |
| Unauthorized access | RBAC + backend authorization + audit |
| Secret exposure | .env + .gitignore + no real credentials |
| Cost | Local-first, zero-budget core |

## 21. Acceptance Criteria

The local MVP candidate is complete for the documented web, ingestion, PostgreSQL, forecasting, risk, authentication/RBAC, audit, automated-test, and Docker-startup paths. Live deployment, external Telegram/SMTP delivery, bank integration, and verified withdrawal-demand accuracy require separate evidence and are not claimed here.

## 22. Future Scope

Anomaly detection, SHAP explanations, what-if simulation, geospatial analytics, model drift, automated retraining, model registry, advanced replenishment optimization and bank-approved production integration.

## 23. Glossary

- **ATM:** Automated Teller Machine.
- **Signed net cash flow:** The next-day signed `daily_cash_flow` value forecast by this prototype; it is not a verified withdrawal-demand measure.
- **Cash-out:** ATM cannot satisfy withdrawals because available cash is insufficient.
- **Replenishment:** Loading cash into an ATM.
- **EDA:** Exploratory Data Analysis.
- **RBAC:** Role-Based Access Control.
- **MAE:** Mean Absolute Error.
- **RMSE:** Root Mean Squared Error.
- **Data Leakage:** Future/unavailable information incorrectly used during training.
- **Audit Log:** Record of important actions with actor, source and timestamp.

## 24. Development Rule for AI Agents

Antigravity and any additional coding agent must implement the project **phase-by-phase**. Before every major phase, the agent must explain objective, dependencies, expected files, tests and acceptance criteria. After implementation it must explain files changed, data/control flow, tests run and the next phase. It must not silently modify unrelated modules or invent results.
