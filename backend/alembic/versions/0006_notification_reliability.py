"""Add durable notification dispatch and concurrency safeguards."""

from alembic import op
import sqlalchemy as sa


revision = "0006_notification_reliability"
down_revision = "0005_signed_flow_risk_status"
branch_labels = None
depends_on = None


ACTIVE_ALERT_DUPLICATES = sa.text(
    "SELECT atm_id, alert_type, severity, COUNT(*) AS duplicate_count "
    "FROM alerts "
    "WHERE status IN ('OPEN', 'ACKNOWLEDGED') "
    "GROUP BY atm_id, alert_type, severity "
    "HAVING COUNT(*) > 1 "
    "LIMIT 1"
)


def _assert_active_alerts_are_unique() -> None:
    duplicate = op.get_bind().execute(ACTIVE_ALERT_DUPLICATES).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot add active alert uniqueness while duplicate active risk alerts exist; "
            "resolve duplicates before applying 0006_notification_reliability"
        )


def _create_active_alert_index() -> None:
    where = sa.text("status IN ('OPEN', 'ACKNOWLEDGED')")
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.create_index(
            "ix_alerts_active_risk_unique",
            "alerts",
            ["atm_id", "alert_type", "severity"],
            unique=True,
            postgresql_where=where,
        )
    elif dialect == "sqlite":
        op.create_index(
            "ix_alerts_active_risk_unique",
            "alerts",
            ["atm_id", "alert_type", "severity"],
            unique=True,
            sqlite_where=where,
        )
    else:
        op.create_index(
            "ix_alerts_active_risk_unique",
            "alerts",
            ["atm_id", "alert_type", "severity"],
            unique=True,
        )


def upgrade() -> None:
    _assert_active_alerts_are_unique()

    op.add_column(
        "notification_deliveries",
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("claim_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("claim_token", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_notification_deliveries_idempotency_key",
        "notification_deliveries",
        ["idempotency_key"],
        unique=True,
    )

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key"),
    )
    op.create_index("ix_notification_outbox_id", "notification_outbox", ["id"], unique=False)
    op.create_index("ix_notification_outbox_status", "notification_outbox", ["status"], unique=False)
    op.create_index("ix_notification_outbox_available_at", "notification_outbox", ["available_at"], unique=False)
    op.create_index("ix_notification_outbox_created_at", "notification_outbox", ["created_at"], unique=False)
    op.create_index(
        "ix_notification_outbox_claim",
        "notification_outbox",
        ["status", "available_at"],
        unique=False,
    )

    _create_active_alert_index()


def downgrade() -> None:
    op.drop_index("ix_alerts_active_risk_unique", table_name="alerts")
    op.drop_index("ix_notification_outbox_claim", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_created_at", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_available_at", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_status", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_id", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index("ix_notification_deliveries_idempotency_key", table_name="notification_deliveries")

    op.drop_column("background_jobs", "claim_token")

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("notification_deliveries", recreate="always") as batch:
            batch.drop_column("locked_at")
            batch.drop_column("claim_token")
            batch.drop_column("attempts")
            batch.drop_column("idempotency_key")
    else:
        op.drop_column("notification_deliveries", "locked_at")
        op.drop_column("notification_deliveries", "claim_token")
        op.drop_column("notification_deliveries", "attempts")
        op.drop_column("notification_deliveries", "idempotency_key")
