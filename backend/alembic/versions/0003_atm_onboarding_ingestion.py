"""Add ATM onboarding metadata and controlled dataset ingestion records."""

from alembic import context, op
import sqlalchemy as sa


revision = "0003_atm_onboarding_ingestion"
down_revision = "0002_model_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status_constraint = "status IN ('active', 'inactive', 'maintenance', 'warning', 'critical', 'PENDING', 'ACTIVE', 'INACTIVE', 'RETIRED')"
    if context.get_context().dialect.name == "sqlite":
        with op.batch_alter_table("atms", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("location", sa.String(length=255), nullable=True))
            batch_op.add_column(sa.Column("activation_date", sa.Date(), nullable=True))
            batch_op.drop_constraint("ck_atms_status", type_="check")
            batch_op.create_check_constraint("ck_atms_status", status_constraint)
    else:
        op.add_column("atms", sa.Column("location", sa.String(length=255), nullable=True))
        op.add_column("atms", sa.Column("activation_date", sa.Date(), nullable=True))
        op.drop_constraint("ck_atms_status", "atms", type_="check")
        op.create_check_constraint("ck_atms_status", "atms", status_constraint)

    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_datasets_id", "datasets", ["id"])
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rows_received", sa.Integer(), nullable=False),
        sa.Column("rows_accepted", sa.Integer(), nullable=False),
        sa.Column("rows_rejected", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("atm_codes", sa.JSON(), nullable=False),
        sa.Column("validation_report", sa.JSON(), nullable=False),
        sa.Column("normalized_records", sa.JSON(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.CheckConstraint("status IN ('UPLOADED', 'VALIDATED', 'APPROVED', 'INGESTED', 'REJECTED', 'FAILED')", name="ck_dataset_versions_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "version", name="uq_dataset_versions_dataset_version"),
    )
    op.create_index("ix_dataset_versions_id", "dataset_versions", ["id"])
    op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])
    op.create_index("ix_dataset_versions_uploaded_by", "dataset_versions", ["uploaded_by"])
    op.create_index("ix_dataset_versions_status", "dataset_versions", ["status"])
    op.create_index("ix_dataset_versions_status_uploaded", "dataset_versions", ["status", "uploaded_at"])

    op.create_table(
        "atm_history_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("atm_id", sa.Integer(), nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Double(), nullable=False),
        sa.Column("record_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["atm_id"], ["atms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"]),
        sa.CheckConstraint("amount >= 0", name="ck_atm_history_records_amount_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("record_fingerprint"),
    )
    op.create_index("ix_atm_history_records_id", "atm_history_records", ["id"])
    op.create_index("ix_atm_history_records_atm_id", "atm_history_records", ["atm_id"])
    op.create_index("ix_atm_history_records_dataset_version_id", "atm_history_records", ["dataset_version_id"])
    op.create_index("ix_atm_history_records_observed_at", "atm_history_records", ["observed_at"])
    op.create_index("ix_atm_history_records_record_fingerprint", "atm_history_records", ["record_fingerprint"])
    op.create_index("ix_atm_history_records_atm_observed", "atm_history_records", ["atm_id", "observed_at"])


def downgrade() -> None:
    op.drop_table("atm_history_records")
    op.drop_table("dataset_versions")
    op.drop_table("datasets")
    status_constraint = "status IN ('active', 'inactive', 'maintenance', 'warning', 'critical')"
    if context.get_context().dialect.name == "sqlite":
        with op.batch_alter_table("atms", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_atms_status", type_="check")
            batch_op.create_check_constraint("ck_atms_status", status_constraint)
            batch_op.drop_column("activation_date")
            batch_op.drop_column("location")
    else:
        op.drop_constraint("ck_atms_status", "atms", type_="check")
        op.create_check_constraint("ck_atms_status", "atms", status_constraint)
        op.drop_column("atms", "activation_date")
        op.drop_column("atms", "location")
