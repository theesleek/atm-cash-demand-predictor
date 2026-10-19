"""Persist signed forecasts separately from demand-risk fields."""

from alembic import op
import sqlalchemy as sa


revision = "0005_signed_flow_risk_status"
down_revision = "0004_align_unique_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
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
