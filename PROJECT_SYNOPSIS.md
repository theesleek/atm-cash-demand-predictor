# ATM Cash Intelligence & Automated Replenishment Platform
## Corporate Synopsis Report

**Document ID:** ATM-CI-SYN-001
**Version:** 1.0
**Date:** 28 September 2026
**Domain:** Banking / Data Analytics / AI Forecasting
**Reference Requirement:** ATM Cash Demand Predictor; Generic ATM operations prototype
**Classification:** Public MVP Documentation

> This document follows a formal corporate documentation style. It is not an official HCL template or HCL internal document. The system is a prototype/training solution and is not connected to production banking infrastructure.

---

## 1. Purpose

The **ATM Cash Intelligence & Automated Replenishment Platform** is a multi-ATM system that forecasts future ATM cash demand, estimates cash depletion risk, recommends replenishment, and communicates alerts to authorized personnel.

### Objectives

- Forecast cash demand for multiple ATMs.
- Detect ATMs likely to fall below configured cash thresholds.
- Recommend replenishment quantity and priority.
- Notify authorized users through web, Telegram and email.
- Allow Telegram/web acknowledgement while reserving final approval for the authenticated website.
- Maintain auditable records of forecasts, alerts, approvals and operational actions.

### Scope

The prototype supports a multi-ATM data model and uses synthetic, public or company-approved data. It does not access production ATM systems or real customer banking data.

### Success Measurement

Measure forecasting with MAE, RMSE and a justified percentage-based metric such as sMAPE. The SRS target of >=85% forecast accuracy is only valid after defining the exact accuracy formula. Cash-out reduction is a target to be demonstrated through simulation/back-testing, not an assumed result.

---

## 2. Technology Stack

### 2.1 Backend, Data Engineering and ML

| Technology | Purpose | Project Area |
|---|---|---|
| Python 3.12.7 | Primary language and trained-artifact runtime | Backend, data and ML |
| NumPy | Numerical computation | Feature calculations |
| Pandas | Tabular data handling | Ingestion, cleaning, features |
| Matplotlib / Seaborn | Visualization | EDA |
| Scikit-learn 1.6.1 | ML, preprocessing, metrics | Trained pipelines and inference |
| XGBoost | Gradient-boosted trees | Forecast candidate |
| LightGBM | Efficient boosted trees | Primary tabular candidate |
| Statsmodels | Statistical forecasting | ARIMA/SARIMA |
| Prophet | Trend/seasonality benchmark | Optional |
| PyTorch/TensorFlow | Deep learning | Optional LSTM |
| SHAP | Explainability | Feature contribution |
| Joblib | Model serialization | Model artifacts |
| FastAPI | REST + WebSocket API | Controller/API layer |
| Uvicorn | ASGI server | FastAPI runtime |
| Pydantic | API validation | Schemas |
| SQLAlchemy | ORM/data access | Repository layer |
| psycopg | PostgreSQL driver | Database connection |
| python-dotenv | Environment config | Secrets/config |
| Pytest / HTTPX | Testing | QA |

### 2.2 Frontend

- React: web application
- Vite: build/dev tooling
- Recharts: charts
- Leaflet + OpenStreetMap: ATM map
- WebSocket client: live event updates

### 2.3 Database

- PostgreSQL: persistent relational source of truth
- SQLAlchemy: application-side database abstraction
- Alembic: recommended schema migration tool

### 2.4 Security, Integration and DevOps

- JWT / OAuth2-compatible authentication
- Password hashing
- RBAC
- Telegram Bot API
- SMTP/email
- WebSockets
- Docker / Docker Compose
- Git / GitHub
- GitHub Actions
- AWS ECS only as an optional/company-specified deployment target

---

## 3. System Architecture

The system uses a layered, service-oriented architecture. React and Telegram are clients of the same FastAPI backend; neither client accesses PostgreSQL directly. Business rules are kept in services, database access is isolated in repositories, and ML/forecasting is isolated from approval and notification logic.

### 3.1 System Architecture Flow

```text
CLIENT / PRESENTATION
  |
  +--> React Web Application
  |     -> Dashboard
  |     -> Forecasts
  |     -> Alerts
  |     -> Replenishment Review / Final Approval
  |     -> Analytics / Audit / Administration
  |
  +--> Telegram Bot
  |     -> Alerts
  |     -> Status / Forecast queries
  |     -> Alert acknowledgement
  |     -> Escalation
  |
  +--> Email Notification Channel

CONTROLLER / API
  |
  +--> FastAPI REST Controllers
  +--> Pydantic Request/Response Schemas
  +--> WebSocket Event Controller
  +--> Telegram Webhook/Bot Adapter

SECURITY
  |
  +--> Authentication
  +--> JWT / Session validation
  +--> Role-Based Access Control (RBAC)
  +--> Bank/Region/Branch/ATM scope authorization
  +--> Telegram account linking

SERVICE / APPLICATION
  |
  +--> Forecast Service
  +--> Risk / Cash Depletion Service
  +--> Replenishment Service
  +--> Alert Service
  +--> Notification Service
  +--> Bank / Branch / ATM / User Services
  +--> Analytics Service
  +--> Audit / Activity Service

DOMAIN / ENTITY
  |
  +--> Bank, Region, Branch
  +--> Location, ATM
  +--> Transaction, Cash Inventory, Replenishment
  +--> Calendar Event
  +--> Feature Set, Model, Forecast
  +--> Alert, Notification, User, Role, Audit Log

REPOSITORY / DATA ACCESS
  |
  +--> ATM Repository
  +--> Transaction Repository
  +--> Inventory Repository
  +--> Replenishment Repository
  +--> Forecast / Model Repository
  +--> Alert / Notification Repository
  +--> User / Role Repository
  +--> Audit Repository

ML / DATA PROCESSING
  |
  +--> Ingestion
  +--> Validation / Data Quality
  +--> Cleaning / Transformation
  +--> Feature Engineering
  +--> Model Training / Evaluation
  +--> Model Loading / Prediction
  +--> Explainability where applicable

PERSISTENCE / INFRASTRUCTURE
  |
  +--> PostgreSQL
  +--> SQLAlchemy / PostgreSQL Driver
  +--> Model Artifact Storage
  +--> Environment Configuration
  +--> Application Logging

CROSS-CUTTING
  |
  +--> Testing
  +--> Error Handling
  +--> Audit Trail
  +--> Health Checks
  +--> Docker / Deployment
```

### 3.2 Layer Structure and Responsibility

| Layer | Responsibility | Key Components | Must Not Do |
|---|---|---|---|
| Client / Presentation | User interaction and presentation | React, Telegram | Access DB directly or contain authoritative business rules |
| Controller / API | Request translation, validation and response handling | FastAPI, Pydantic, WebSockets | Perform complex business logic or direct DB queries |
| Security | Identity and permission enforcement | JWT/session, RBAC, scope checks | Rely only on frontend button hiding |
| Service / Application | Business workflows and decisions | Forecast, Risk, Replenishment, Alert, Notification, Audit services | Expose DB credentials or UI-specific logic |
| Domain / Entity | Business objects and relationships | ATM, Transaction, Forecast, Alert, User, etc. | Contain HTTP-specific behavior |
| Repository / Data Access | Persistence and database queries | SQLAlchemy repositories | Decide business approvals or model selection |
| ML / Data | Data preparation and forecasting | Pandas, scikit-learn, XGBoost, LightGBM, Statsmodels, etc. | Give final replenishment approval |
| Persistence / Infrastructure | Durable storage and runtime support | PostgreSQL, drivers, model artifacts, config | Store secrets in source code |
| Cross-Cutting | Concerns used across layers | Logging, testing, audit, health checks, Docker | Become a second business-rule engine |

### 3.3 Dependency Direction

```text
React / Telegram
      |
      v
Controller / API
      |
      v
Security
      |
      v
Service Layer
   |       \
   |        +--> ML / Forecast Service --> Model Artifact
   v
Repository Layer
      |
      v
PostgreSQL

Service Layer
      |
      +--> Notification Service --> Telegram / Email / WebSocket
      |
      +--> Audit Service --> Audit Repository --> PostgreSQL
```

Core rules:
- React never connects directly to PostgreSQL.
- Telegram never connects directly to PostgreSQL.
- Controllers translate requests; services execute business workflows.
- Repositories own database access.
- ML forecasts demand; deterministic risk logic evaluates cash depletion.
- Final replenishment approval is authorized and executed only through the authenticated web application.
- Telegram acknowledgement and other actions are stored centrally and pushed to the web UI through WebSocket events.

### 3.4 Core Service Dependencies

```text
Forecast Service
  -> Feature/Data Service
  -> Model Loader
  -> Forecast Repository

Risk Service
  -> Forecast Service
  -> Inventory Repository
  -> Threshold Configuration

Replenishment Service
  -> Risk Service
  -> ATM Repository
  -> Replenishment Repository

Alert Service
  -> Risk Service
  -> Alert Repository
  -> Notification Service
  -> Audit Service

Telegram Action
  -> Telegram Adapter
  -> Identity Link + RBAC
  -> Alert/Replenishment Service
  -> Audit Service
  -> WebSocket Event Publisher

React Action
  -> FastAPI Controller
  -> Security/RBAC
  -> Business Service
  -> Repository
```

### 3.5 System Interaction Sequence

1. A user acts from the website or Telegram, or a system job creates an event.
2. The controller/adapter validates the input.
3. Security checks identity, role and resource scope.
4. The service executes the business use case.
5. Repositories read/write PostgreSQL as required.
6. Forecast operations load time-safe features and the approved model.
7. Risk and replenishment logic calculate the operational result.
8. Alert and notification services deliver the event through the required channels.
9. WebSocket events update connected web clients without a page refresh.
10. The audit service records actor, action, source channel, entity and timestamp.

### 3.6 Dependency Ownership

- Controllers own HTTP/message translation.
- Security owns identity and permission checks.
- Services own business workflows.
- Repositories own persistence operations.
- Entities own business data representation.
- ML modules own data preparation and forecasting.
- Notification adapters own channel delivery.
- Frontend owns presentation and interaction.

---

---

## 4. Layman View: How the Project Works

### Main Frontend Pages

| Page | User sees |
|---|---|
| Login | Secure sign-in |
| Dashboard | ATM counts, risk, alerts, KPIs |
| ATM Details | Current cash, demand history, forecast, risk |
| Forecasts | Prediction charts and model information |
| Alerts | Critical/warning alerts and status |
| Replenishment Review | Recommended amount and evidence |
| Analytics | Demand trends, comparisons, anomalies |
| Activity/Audit | Who did what, when and through which channel |
| Models | Model version and metrics |
| Admin/Users | Users, roles and permissions |
| Bank/Branch Configuration | Controlled organization settings |

### User Journey

1. ATM data arrives.
2. The data pipeline validates and stores it.
3. Features are generated.
4. The model predicts future demand.
5. Risk logic compares predicted demand with current cash.
6. A critical alert is created when thresholds are crossed.
7. The alert appears on web and can be sent to Telegram/email.
8. A user can acknowledge the alert from Telegram.
9. The user reviews the forecast and recommendation on the website.
10. An authorized approver gives final approval on the website.
11. A replenishment order is created and tracked.
12. Every action is recorded in the audit trail.

---

## 5. Database Schema and Data Design

The relational design targets **Third Normal Form (3NF)** for transactional/master data.

### 5.1 Organization and Identity

| Entity | Main Attributes | Relationships |
|---|---|---|
| BANK | bank_id, bank_name, bank_code, status | 1:N REGION, 1:N USER |
| REGION | region_id, bank_id, name, status | N:1 BANK, 1:N BRANCH |
| BRANCH | branch_id, region_id, name, address/reference, status | N:1 REGION, 1:N ATM |
| ROLE | role_id, name, permissions | 1:N USER |
| USER | user_id, bank_id, role_id, name, email, password_hash, status | N:1 BANK/ROLE, 1:N AUDIT_LOG |

### 5.2 ATM and Operations

| Entity | Main Attributes | Relationships |
|---|---|---|
| LOCATION | location_id, city, area, latitude, longitude | 1:N ATM |
| ATM | atm_id, branch_id, location_id, status, cash_capacity, thresholds | N:1 BRANCH/LOCATION; 1:N operational records |
| TRANSACTION | transaction_id, atm_id, timestamp, type, amount, status | N:1 ATM |
| CASH_INVENTORY | inventory_id, atm_id, timestamp, opening/closing balance, loaded, dispensed | N:1 ATM |
| REPLENISHMENT | replenishment_id, atm_id, requested/approved amounts, status, users, timestamps | N:1 ATM; user actions |
| CALENDAR_EVENT | event_id, date, name, type, impact_category | Used by feature engineering |

### 5.3 ML and Alert

| Entity | Main Attributes | Relationships |
|---|---|---|
| FEATURE_SET | feature/version key, atm_id, date, lags, rolling values, calendar features | Derived from operational data |
| MODEL | model_id, name, version, algorithm, training date, dataset version, metrics | 1:N FORECAST |
| FORECAST | forecast_id, atm_id, model_id, date, horizon, demand, bounds | N:1 ATM/MODEL; 1:N ALERT |
| ALERT | alert_id, atm_id, forecast_id, type, severity, status, timestamps | N:1 ATM/FORECAST; 1:N NOTIFICATION |
| NOTIFICATION | notification_id, alert_id, recipient, channel, status, timestamps | N:1 ALERT |
| AUDIT_LOG | activity_id, user_id, action, entity type/id, source, metadata, timestamp | N:1 USER |

### 5.4 Relationships

```text
BANK 1 ---- N REGION
REGION 1 ---- N BRANCH
BRANCH 1 ---- N ATM
LOCATION 1 ---- N ATM
ATM 1 ---- N TRANSACTION
ATM 1 ---- N CASH_INVENTORY
ATM 1 ---- N REPLENISHMENT
ATM 1 ---- N FORECAST
MODEL 1 ---- N FORECAST
FORECAST 1 ---- N ALERT
ALERT 1 ---- N NOTIFICATION
ROLE 1 ---- N USER
USER 1 ---- N AUDIT_LOG
```

### 5.5 Normalization

- **1NF:** atomic attributes and no repeating groups.
- **2NF:** non-key attributes depend on the complete key.
- **3NF:** non-key attributes depend only on the key; branch/location data is not repeated in transactions.

### 5.6 Database Anomalies to Watch

| Anomaly | Example | Control |
|---|---|---|
| Insertion | Cannot create branch without fake ATM | Separate master tables |
| Update | Branch name repeated in transactions | Store branch once, use FK |
| Deletion | Deleting last ATM removes branch information | Separate entities |
| Duplication | Same ATM details on every row | Normalization/FKs |
| Referential | Transaction references missing ATM | FK + validation |
| Temporal leakage | Future demand enters historical features | Time-safe feature pipeline |

### 5.7 Constraints and Indexes

- Unique identifiers for ATM and user email where applicable.
- Foreign keys across master/transaction tables.
- Indexes on ATM + timestamp for time-series queries.
- Indexes on alert status/severity/created_at.
- Check constraints for non-negative amounts and valid statuses.

---

## 6. API Endpoints and Authentication

FastAPI is the controller/API layer. Pydantic validates data. Services contain business rules. Repositories access PostgreSQL.

### 6.1 Authentication

| Method | Endpoint | Purpose | Auth |
|---|---|---|---|
| POST | `/auth/login` | Sign in / issue token | Public |
| POST | `/auth/refresh` | Refresh token if used | Authenticated |
| GET | `/auth/me` | Current user and permissions | Authenticated |
| POST | `/auth/logout` | End session | Authenticated |

### 6.2 Core Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/atms` | List authorized ATMs |
| GET | `/atms/{atm_id}` | ATM details |
| POST | `/predict` | Generate/request forecast |
| GET | `/forecasts/{atm_id}` | Forecast history/current forecast |
| GET | `/alerts` | List alerts |
| GET | `/alerts/{alert_id}` | Alert details |
| POST | `/alerts/{alert_id}/acknowledge` | Acknowledge alert |
| GET | `/replenishments` | List replenishments |
| POST | `/replenishments/{id}/approve` | Final website approval |
| POST | `/replenishments/{id}/reject` | Reject recommendation |
| POST | `/replenishments/{id}/complete` | Mark simulated completion |
| GET | `/activity` | Audit/activity feed |
| GET | `/models` | Model metadata |
| GET | `/health` | Health check |
| WS | `/ws/events` | Real-time web events |

### 6.3 Telegram

- `POST /integrations/telegram/webhook` — receive Telegram updates in webhook mode.
- `POST /integrations/telegram/link` — account-linking flow.

### 6.4 Authorization

Authentication identifies the user. RBAC and resource scope determine what the user can see/do. The backend is authoritative. Telegram uses the same linked user identity and permissions as the web application. **Final replenishment approval is website-only.**

---

## 7. Connection Management

### 7.1 Frontend -> Backend

```text
React -> REST API -> FastAPI
React -> WebSocket -> FastAPI
```

The frontend never accesses PostgreSQL directly.

### 7.2 Backend -> Database

```text
FastAPI
  -> SQLAlchemy Engine
  -> Connection Pool
  -> psycopg
  -> PostgreSQL
```

Use environment-based `DATABASE_URL`. Sessions are scoped to a request/unit of work and are safely closed/returned to the pool.

### 7.3 Transactions

- Use explicit transactions for multi-table business operations.
- Commit after the complete operation succeeds.
- Roll back on exceptions.
- Final approval should atomically update the replenishment state and audit record.

### 7.4 Telegram

Use webhook for public deployment or polling for local development. Telegram messages pass through the same identity/RBAC/service layers as web requests.

### 7.5 Email

Use an SMTP-compatible connection configured from environment variables. Log sent/failed state for every notification.

### 7.6 Real-Time Synchronization

```text
Telegram action
 -> FastAPI
 -> PostgreSQL
 -> Event
 -> WebSocket
 -> React updates without refresh
```

### 7.7 Secrets

Use `.env` locally and `.env.example` without secrets. Never commit real credentials or tokens.

---

## 8. Conclusion / Summary

The proposed platform combines data engineering, multi-ATM forecasting, deterministic risk evaluation, replenishment recommendation, secure APIs, real-time web operations and multi-channel alerting in one layered system. The core architectural principle is separation of concerns: the ML model predicts demand, the risk engine evaluates operational exposure, the alert service communicates the event, and authorized personnel review and approve the final action through the website.

Telegram and email make the system operationally responsive, while PostgreSQL and the web dashboard provide centralized state, authorization and auditability. The system is intentionally designed to run locally with zero mandatory investment. Public/synthetic/company-approved data can be used for development, Kaggle can support experimentation where useful, and AWS deployment can remain optional until company infrastructure or approved credits are available.

The project should be considered complete only when the end-to-end workflow is reproducible, tested and supported by measured forecasting results and auditable approval behavior.

---

## Appendix A - Model Strategy

| Model | Role | Priority |
|---|---|---|
| Naive baseline | Reference forecast | Mandatory |
| Linear Regression | Interpretable baseline | Mandatory |
| Random Forest | Nonlinear benchmark | Recommended |
| XGBoost | Strong tabular candidate | Recommended |
| LightGBM | Efficient tabular candidate | Recommended |
| ARIMA | Classical benchmark | As suitable |
| SARIMA | Seasonal benchmark | As justified |
| Prophet | Trend/seasonality benchmark | Optional |
| LSTM | Deep-learning experiment | Optional |

Selection must be based on time-aware validation and measured performance.

## Appendix B - Zero-Budget Constraints

- Local VS Code + Python virtual environment.
- PostgreSQL locally, preferably via Docker Compose.
- GitHub and applicable free GitHub Actions usage.
- Telegram Bot API for prototype alerts.
- Email only as configured/available.
- Free hosting tiers only for demo, never as a hard dependency.
- AWS ECS optional/company-specified, not required for local operation.
- Kaggle for dataset discovery/experimentation, not as the production environment.
