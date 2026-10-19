"""Prevent duplicate forecasts for an ATM target date and model identity."""

from alembic import op
import sqlalchemy as sa


revision = "0007_daily_forecast_uniqueness"
down_revision = "0006_notification_reliability"
branch_labels = None
depends_on = None


def _preflight() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            "SELECT atm_id, forecast_date, model_version, COUNT(*) AS duplicate_count "
            "FROM forecasts GROUP BY atm_id, forecast_date, model_version "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot apply daily forecast uniqueness: duplicate ATM/forecast_date/model rows exist "
            f"(atm_id={duplicate.atm_id}, forecast_date={duplicate.forecast_date}, model_version={duplicate.model_version})."
        )


def upgrade() -> None:
    _preflight()
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("forecasts", recreate="always") as batch:
            batch.create_unique_constraint("uq_forecasts_atm_date_model", ["atm_id", "forecast_date", "model_version"])
    else:
        op.create_unique_constraint("uq_forecasts_atm_date_model", "forecasts", ["atm_id", "forecast_date", "model_version"])


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("forecasts", recreate="always") as batch:
            batch.drop_constraint("uq_forecasts_atm_date_model", type_="unique")
    else:
        op.drop_constraint("uq_forecasts_atm_date_model", "forecasts", type_="unique")
