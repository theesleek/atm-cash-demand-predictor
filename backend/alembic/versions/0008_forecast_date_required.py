"""Require a target date for every forecast."""

from alembic import op
import sqlalchemy as sa


revision = "0008_forecast_date_required"
down_revision = "0007_daily_forecast_uniqueness"
branch_labels = None
depends_on = None


def _assert_no_null_forecast_dates() -> None:
    null_count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM forecasts WHERE forecast_date IS NULL")
    ).scalar_one()
    if null_count:
        raise RuntimeError(
            "Cannot enforce forecasts.forecast_date NOT NULL: "
            f"{null_count} existing forecast row(s) have no date; review and resolve them before applying "
            "0008_forecast_date_required."
        )


def upgrade() -> None:
    _assert_no_null_forecast_dates()
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("forecasts", recreate="always") as batch:
            batch.alter_column(
                "forecast_date",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
            )
    else:
        op.alter_column(
            "forecasts",
            "forecast_date",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("forecasts", recreate="always") as batch:
            batch.alter_column(
                "forecast_date",
                existing_type=sa.DateTime(timezone=True),
                nullable=True,
            )
    else:
        op.alter_column(
            "forecasts",
            "forecast_date",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
