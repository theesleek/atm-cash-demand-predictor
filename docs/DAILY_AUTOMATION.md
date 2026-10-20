# Daily intelligence automation

Daily automation is disabled by default. It does not create an actual-data
feed: approved operational CSV imports remain the only supported source of
new actual ATM history.

## Configuration

Set `DAILY_AUTOMATION_ENABLED=true` only after the worker and the reviewed
forecast schema migrations are deployed successfully. `DAILY_AUTOMATION_MAX_DATA_AGE_DAYS`
defaults to `2`; an ATM whose latest successfully ingested actual date is older
than that threshold is skipped with an explicit stale-data reason.

## Trigger and worker

The persistent worker now checks the UTC operational date once per process
poll-cycle, but attempts a database enqueue only once per date. Start the
worker process normally:

```text
PYTHONPATH=backend python -m app.jobs.worker
```

When enabled, the worker automatically enqueues one job per UTC operational
date. Multiple worker instances and worker restarts are safe because the
process-local day gate is backed by the database unique job key.

The CLI trigger remains available for manual testing or an external operator
schedule:

```text
PYTHONPATH=backend python -m app.jobs.daily_forecast
```

The worker and command only enqueue a job when automation is enabled. The queue key is
`daily-forecast:<UTC date>`, so multiple scheduler or worker instances cannot
create multiple logical daily jobs. The existing persistent worker executes the
job and records the run summary in the `BackgroundJob` payload.

The job processes only ATMs with at least 14 observed days and a compatible
model identity. Stale or insufficient history is reported as skipped; forecast
errors are reported per ATM. It produces one next-day forecast, labelled signed
net cash flow, and never treats forecasts as actual data.

## Status

Authenticated dashboard readers can query `GET /automation/status`. The
dashboard displays whether automation is enabled, the latest successfully
ingested actual date, the latest job status, target date, eligible ATM count,
created forecast count, skipped ATMs, and failures.

## Migration

Before enabling production automation, apply the complete reviewed Alembic
migration chain through `head`, including the latest release migration
`0009_forecast_type_identity`, through the normal release process. Migration
`0007_daily_forecast_uniqueness` classifies existing rows as
`withdrawal_demand` or `signed_flow` and fails closed if a row is ambiguous or
if duplicate `(atm_id, forecast_date, model_version, forecast_type)` rows are
found. Migration `0008_forecast_date_required` first checks for existing rows where
`forecasts.forecast_date` is `NULL`; it intentionally aborts if any are found.
Migration `0009_forecast_type_identity` converges databases that had already
applied the prior 0008 head to the explicit forecast-type identity schema.
Review those records and resolve them using authoritative data and an approved
data-maintenance procedure. Do not invent dates, forecast types, or predictions,
or delete records just to force the migration to succeed. Enable daily
automation only after the schema migration chain completes successfully. This
task does not apply migrations.
