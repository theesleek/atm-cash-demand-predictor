"""Converge databases that already applied the pre-forecast-type head."""

from alembic import op
import sqlalchemy as sa


revision = "0009_forecast_type_identity"
down_revision = "0008_forecast_date_required"
branch_labels = None
depends_on = None

FORECAST_TYPE_CHECK = "ck_forecasts_type"
FORECAST_IDENTITY_CONSTRAINT = "uq_forecasts_atm_date_model"


def _inspector():
    return sa.inspect(op.get_bind())


def _ensure_forecast_type_column() -> None:
    if "forecast_type" in {column["name"] for column in _inspector().get_columns("forecasts")}:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("forecasts", recreate="always") as batch:
            batch.add_column(sa.Column("forecast_type", sa.String(length=32), nullable=True))
    else:
        op.add_column("forecasts", sa.Column("forecast_type", sa.String(length=32), nullable=True))


def _backfill_forecast_types() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE forecasts SET forecast_type = CASE "
            "WHEN risk_evaluation_status = 'AVAILABLE' "
            "AND predicted_demand IS NOT NULL "
            "AND risk_level IS NOT NULL THEN 'withdrawal_demand' "
            "WHEN risk_evaluation_status = 'UNAVAILABLE' "
            "AND predicted_demand IS NULL "
            "AND predicted_signed_net_cash_flow IS NOT NULL "
            "AND risk_level IS NULL "
            "AND recommended_top_up IS NULL THEN 'signed_flow' "
            "ELSE forecast_type END WHERE forecast_type IS NULL"
        )
    )
    invalid_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM forecasts "
            "WHERE forecast_type IS NULL OR forecast_type NOT IN ('withdrawal_demand', 'signed_flow')"
        )
    ).scalar_one()
    if invalid_count:
        raise RuntimeError(
            "Cannot classify existing forecast rows as withdrawal_demand or signed_flow: "
            f"{invalid_count} row(s) are ambiguous or invalid. Review and classify them before applying "
            "0009_forecast_type_identity; no rows were deleted or backfilled with invented values."
        )


def _preflight_duplicates() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            "SELECT atm_id, forecast_date, model_version, forecast_type, COUNT(*) AS duplicate_count "
            "FROM forecasts GROUP BY atm_id, forecast_date, model_version, forecast_type "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot apply forecast type identity uniqueness: duplicate ATM/date/model/type rows exist "
            f"(atm_id={duplicate.atm_id}, forecast_date={duplicate.forecast_date}, "
            f"model_version={duplicate.model_version}, forecast_type={duplicate.forecast_type})."
        )


def _finalize_schema() -> None:
    inspector = _inspector()
    has_identity = any(
        constraint.get("name") == FORECAST_IDENTITY_CONSTRAINT
        for constraint in inspector.get_unique_constraints("forecasts")
    )
    has_type_check = any(
        constraint.get("name") == FORECAST_TYPE_CHECK
        for constraint in inspector.get_check_constraints("forecasts")
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("forecasts", recreate="always") as batch:
            if has_identity:
                batch.drop_constraint(FORECAST_IDENTITY_CONSTRAINT, type_="unique")
            batch.alter_column(
                "forecast_type",
                existing_type=sa.String(length=32),
                nullable=False,
            )
            if not has_type_check:
                batch.create_check_constraint(FORECAST_TYPE_CHECK, "forecast_type IN ('withdrawal_demand', 'signed_flow')")
            batch.create_unique_constraint(
                FORECAST_IDENTITY_CONSTRAINT,
                ["atm_id", "forecast_date", "model_version", "forecast_type"],
            )
        return

    if has_identity:
        op.drop_constraint(FORECAST_IDENTITY_CONSTRAINT, "forecasts", type_="unique")
    op.alter_column(
        "forecasts",
        "forecast_type",
        existing_type=sa.String(length=32),
        nullable=False,
    )
    if not has_type_check:
        op.create_check_constraint(FORECAST_TYPE_CHECK, "forecasts", "forecast_type IN ('withdrawal_demand', 'signed_flow')")
    op.create_unique_constraint(
        FORECAST_IDENTITY_CONSTRAINT,
        "forecasts",
        ["atm_id", "forecast_date", "model_version", "forecast_type"],
    )


def upgrade() -> None:
    _ensure_forecast_type_column()
    _backfill_forecast_types()
    _preflight_duplicates()
    _finalize_schema()


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("forecasts", recreate="always") as batch:
            batch.drop_constraint(FORECAST_IDENTITY_CONSTRAINT, type_="unique")
            batch.drop_constraint(FORECAST_TYPE_CHECK, type_="check")
            batch.drop_column("forecast_type")
            batch.create_unique_constraint(
                FORECAST_IDENTITY_CONSTRAINT,
                ["atm_id", "forecast_date", "model_version"],
            )
        return
    op.drop_constraint(FORECAST_IDENTITY_CONSTRAINT, "forecasts", type_="unique")
    op.drop_constraint(FORECAST_TYPE_CHECK, "forecasts", type_="check")
    op.drop_column("forecasts", "forecast_type")
    op.create_unique_constraint(
        FORECAST_IDENTITY_CONSTRAINT,
        "forecasts",
        ["atm_id", "forecast_date", "model_version"],
    )
