"""Add controlled model lifecycle registry."""

from alembic import op
import sqlalchemy as sa


revision = "0002_model_registry"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_registry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=255), nullable=False),
        sa.Column("feature_version", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("artifact_checksums", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('TRAINED', 'EVALUATED', 'APPROVED', 'ACTIVE', 'RETIRED')", name="ck_model_registry_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target", "model_version", name="uq_model_registry_target_version"),
    )
    op.create_index("ix_model_registry_id", "model_registry", ["id"])
    op.create_index("ix_model_registry_target", "model_registry", ["target"])
    op.create_index("ix_model_registry_status", "model_registry", ["status"])
    op.create_index("ix_model_registry_target_status", "model_registry", ["target", "status"])
    op.create_index("uq_model_registry_active_target", "model_registry", ["target"], unique=True, postgresql_where=sa.text("status = 'ACTIVE'"))


def downgrade() -> None:
    op.drop_table("model_registry")
