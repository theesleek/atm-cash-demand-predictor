# MVP deployment

This document describes a deployment procedure; it is not evidence that this snapshot has been deployed. The release remains unverified until a real HTTPS deployment passes the checks below.

The simplest suitable hosting shape is one Linux VPS with Docker Compose and a TLS reverse proxy (for example, Caddy) in front of the frontend container. PostgreSQL stays on the private Compose network and persists in the `postgres_data` volume. Telegram and SMTP are intentionally deferred.

## Configure

1. Install Docker Engine and the Compose plugin on the VPS.
2. Copy `.env.production.example` to an untracked `.env.production` file.
3. Replace every placeholder, including the database password, JWT secret, bootstrap username/password, and deployment-specific CORS origin. Keep the file private. Do not commit it.
4. Point the TLS proxy at `127.0.0.1:8080`; the frontend proxies `/api/` and `/ws/events` to the private backend service.

## Start

```sh
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.production.yml \
  up -d --build
```

The backend applies reviewed Alembic migrations before serving traffic. Verify the deployment before calling it released:

```sh
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.production.yml ps
curl -fsS https://mvp.example.com/health/ready
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.production.yml logs --tail=100 backend worker frontend
```

The MVP workflow is: sign in with the bootstrap administrator, register an ATM, upload/validate CSV history, approve and ingest it, then open the forecast and dashboard. Forecasts are labelled signed net cash flow in the source dataset's unspecified units; they are not verified withdrawal-demand forecasts. A release still requires a real HTTPS check of login, ingestion, forecast display, and dashboard access with deployment credentials.

## Operate safely

Back up PostgreSQL before upgrades, keep ports `5432` and `8000` private, rotate bootstrap credentials after first login, and verify `/health/ready` after every restart. Do not enable Telegram or SMTP until their credentials, public webhook/delivery path, and retry behavior are separately verified.
