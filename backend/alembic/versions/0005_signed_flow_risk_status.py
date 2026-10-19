"""Persist signed forecasts separately from demand-risk fields."""

from alembic import op
import sqlalchemy as sa


revision = "0005_signed_flow_risk_status"
down_revision = "0004_align_unique_indexes"
branch_labels = None
depends_on = None


def _upgrade_in_place() -> None:
    op.alter_column("forecasts", "predicted_demand", existing_type=sa.Float(), nullable=True)
    op.alter_column("forecasts", "risk_level", existing_type=sa.String(length=32), nullable=True)
    op.alter_column("forecasts", "recommended_top_up", existing_type=sa.Float(), nullable=True)
    op.add_column("forecasts", sa.Column("predicted_signed_net_cash_flow", sa.Float(), nullable=True))
    op.add_column(
        "forecasts",
        sa.Column("risk_evaluation_status", sa.String(length=32), nullable=False, server_default="AVAILABLE"),
    )
    op.add_column("forecasts", sa.Column("risk_evaluation_reason", sa.String(length=255), nullable=True))
    op.drop_constraint("ck_forecasts_nonnegative_values", "forecasts", type_="check")
    op.create_check_constraint(
        "ck_forecasts_nonnegative_values",
        "forecasts",
        "(predicted_demand IS NULL OR predicted_demand >= 0) AND (recommended_top_up IS NULL OR recommended_top_up >= 0)",
    )


def _upgrade_sqlite() -> None:
    with op.batch_alter_table("forecasts", recreate="always") as batch:
        batch.alter_column("predicted_demand", existing_type=sa.Float(), nullable=True)
        batch.alter_column("risk_level", existing_type=sa.String(length=32), nullable=True)
        batch.alter_column("recommended_top_up", existing_type=sa.Float(), nullable=True)
        batch.add_column(sa.Column("predicted_signed_net_cash_flow", sa.Float(), nullable=True))
        batch.add_column(sa.Column("risk_evaluation_status", sa.String(length=32), nullable=False, server_default="AVAILABLE"))
        batch.add_column(sa.Column("risk_evaluation_reason", sa.String(length=255), nullable=True))
        batch.drop_constraint("ck_forecasts_nonnegative_values", type_="check")
        batch.create_check_constraint(
            "ck_forecasts_nonnegative_values",
            "(predicted_demand IS NULL OR predicted_demand >= 0) AND (recommended_top_up IS NULL OR recommended_top_up >= 0)",
        )


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        _upgrade_sqlite()
    else:
        _upgrade_in_place()


def _downgrade_in_place() -> None:
    op.drop_column("forecasts", "risk_evaluation_reason")
    op.drop_column("forecasts", "risk_evaluation_status")
    op.drop_column("forecasts", "predicted_signed_net_cash_flow")
    op.drop_constraint("ck_forecasts_nonnegative_values", "forecasts", type_="check")
    op.alter_column("forecasts", "predicted_demand", existing_type=sa.Float(), nullable=False)
    op.alter_column("forecasts", "risk_level", existing_type=sa.String(length=32), nullable=False)
    op.alter_column("forecasts", "recommended_top_up", existing_type=sa.Float(), nullable=False)
    op.create_check_constraint(
        "ck_forecasts_nonnegative_values",
        "forecasts",
        "predicted_demand >= 0 AND recommended_top_up >= 0",
    )


def _downgrade_sqlite() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM forecasts WHERE predicted_demand IS NULL OR recommended_top_up IS NULL OR risk_level IS NULL LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade while forecasts contain unavailable demand-risk fields")

    with op.batch_alter_table("forecasts", recreate="always") as batch:
        batch.drop_column("risk_evaluation_reason")
        batch.drop_column("risk_evaluation_status")
        batch.drop_column("predicted_signed_net_cash_flow")
        batch.drop_constraint("ck_forecasts_nonnegative_values", type_="check")
        batch.alter_column("predicted_demand", existing_type=sa.Float(), nullable=False)
        batch.alter_column("risk_level", existing_type=sa.String(length=32), nullable=False)
        batch.alter_column("recommended_top_up", existing_type=sa.Float(), nullable=False)
        batch.create_check_constraint("ck_forecasts_nonnegative_values", "predicted_demand >= 0 AND recommended_top_up >= 0")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(
        sa.text(
            "SELECT 1 FROM forecasts "
            "WHERE risk_evaluation_status IS NULL OR risk_evaluation_status <> 'AVAILABLE' "
            "OR predicted_demand IS NULL OR recommended_top_up IS NULL OR risk_level IS NULL LIMIT 1"
        )
    ).first():
        raise RuntimeError("Cannot downgrade while forecasts contain unavailable demand-risk fields")
    if bind.dialect.name == "sqlite":
        _downgrade_sqlite()
    else:
        _downgrade_in_place()
