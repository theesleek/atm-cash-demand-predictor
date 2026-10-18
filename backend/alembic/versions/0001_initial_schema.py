"""Create the initial application schema.

Revision ID: 0001_initial_schema
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "atms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("atm_code", sa.String(length=64), nullable=False),
        sa.Column("branch_id", sa.String(length=64), nullable=False),
        sa.Column("region", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("capacity", sa.Float(), nullable=False),
        sa.Column("current_cash", sa.Float(), nullable=False),
        sa.Column("daily_demand", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'inactive', 'maintenance', 'warning', 'critical')", name="ck_atms_status"),
        sa.CheckConstraint("capacity >= 0 AND current_cash >= 0 AND daily_demand >= 0", name="ck_atms_nonnegative_values"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("atm_code"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("telegram_chat_id"),
    )
    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("atm_id", sa.Integer(), nullable=False),
        sa.Column("forecast_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("predicted_demand", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("recommended_top_up", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("predicted_demand >= 0 AND recommended_top_up >= 0", name="ck_forecasts_nonnegative_values"),
        sa.CheckConstraint("risk_level IN ('NORMAL', 'WARNING', 'HIGH', 'CRITICAL', 'normal', 'warning', 'high', 'critical')", name="ck_forecasts_risk_level"),
        sa.ForeignKeyConstraint(["atm_id"], ["atms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "cash_inventory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("atm_id", sa.Integer(), nullable=False),
        sa.Column("inventory_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cash_on_hand", sa.Float(), nullable=False),
        sa.Column("capacity", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cash_on_hand >= 0 AND capacity >= 0", name="ck_cash_inventory_nonnegative_values"),
        sa.CheckConstraint("status IN ('healthy', 'warning', 'critical')", name="ck_cash_inventory_status"),
        sa.ForeignKeyConstraint(["atm_id"], ["atms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("atm_id", sa.Integer(), nullable=False),
        sa.Column("forecast_id", sa.Integer(), nullable=True),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_by", sa.String(length=128), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=128), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action_source", sa.String(length=16), nullable=False, server_default="SYSTEM"),
        sa.CheckConstraint("severity IN ('WARNING', 'HIGH', 'CRITICAL')", name="ck_alerts_severity"),
        sa.CheckConstraint("status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')", name="ck_alerts_status"),
        sa.CheckConstraint("action_source IN ('SYSTEM', 'WEB', 'API', 'TELEGRAM')", name="ck_alerts_action_source"),
        sa.ForeignKeyConstraint(["atm_id"], ["atms.id"]),
        sa.ForeignKeyConstraint(["forecast_id"], ["forecasts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "replenishments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("atm_id", sa.Integer(), nullable=False),
        sa.Column("forecast_id", sa.Integer(), nullable=True),
        sa.Column("requested_amount", sa.Float(), nullable=False),
        sa.Column("approved_amount", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("requested_amount > 0", name="ck_replenishments_requested_amount_positive"),
        sa.CheckConstraint("approved_amount IS NULL OR approved_amount > 0", name="ck_replenishments_approved_amount_positive"),
        sa.CheckConstraint("status IN ('DRAFT', 'REQUESTED', 'APPROVED', 'REJECTED', 'SCHEDULED', 'COMPLETED', 'CANCELLED')", name="ck_replenishments_status"),
        sa.ForeignKeyConstraint(["atm_id"], ["atms.id"]),
        sa.ForeignKeyConstraint(["forecast_id"], ["forecasts.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("recipient", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "telegram_link_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_type", "dedupe_key", name="uq_background_jobs_type_dedupe"),
    )
    op.create_table(
        "rate_limit_states",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    for name, table, columns in (
        ("ix_roles_id", "roles", ["id"]), ("ix_roles_name", "roles", ["name"]),
        ("ix_atms_id", "atms", ["id"]), ("ix_atms_branch_id", "atms", ["branch_id"]), ("ix_atms_region", "atms", ["region"]), ("ix_atms_status", "atms", ["status"]), ("ix_atms_region_status", "atms", ["region", "status"]),
        ("ix_users_id", "users", ["id"]), ("ix_users_username", "users", ["username"]), ("ix_users_role_id", "users", ["role_id"]),
        ("ix_forecasts_id", "forecasts", ["id"]), ("ix_forecasts_atm_id", "forecasts", ["atm_id"]), ("ix_forecasts_forecast_date", "forecasts", ["forecast_date"]), ("ix_forecasts_risk_level", "forecasts", ["risk_level"]), ("ix_forecasts_model_version", "forecasts", ["model_version"]), ("ix_forecasts_atm_date", "forecasts", ["atm_id", "forecast_date"]),
        ("ix_cash_inventory_id", "cash_inventory", ["id"]), ("ix_cash_inventory_atm_id", "cash_inventory", ["atm_id"]), ("ix_cash_inventory_inventory_date", "cash_inventory", ["inventory_date"]), ("ix_cash_inventory_status", "cash_inventory", ["status"]), ("ix_cash_inventory_atm_date", "cash_inventory", ["atm_id", "inventory_date"]),
        ("ix_alerts_id", "alerts", ["id"]), ("ix_alerts_atm_id", "alerts", ["atm_id"]), ("ix_alerts_forecast_id", "alerts", ["forecast_id"]), ("ix_alerts_alert_type", "alerts", ["alert_type"]), ("ix_alerts_severity", "alerts", ["severity"]), ("ix_alerts_status", "alerts", ["status"]), ("ix_alerts_created_at", "alerts", ["created_at"]), ("ix_alerts_atm_status", "alerts", ["atm_id", "status"]),
        ("ix_audit_logs_id", "audit_logs", ["id"]), ("ix_audit_logs_user_id", "audit_logs", ["user_id"]), ("ix_audit_logs_action", "audit_logs", ["action"]), ("ix_audit_logs_entity_type", "audit_logs", ["entity_type"]), ("ix_audit_logs_entity_id", "audit_logs", ["entity_id"]), ("ix_audit_logs_timestamp", "audit_logs", ["timestamp"]),
        ("ix_replenishments_id", "replenishments", ["id"]), ("ix_replenishments_atm_id", "replenishments", ["atm_id"]), ("ix_replenishments_forecast_id", "replenishments", ["forecast_id"]), ("ix_replenishments_status", "replenishments", ["status"]), ("ix_replenishments_requested_by", "replenishments", ["requested_by"]), ("ix_replenishments_approved_by", "replenishments", ["approved_by"]), ("ix_replenishments_status_created", "replenishments", ["status", "created_at"]),
        ("ix_notification_deliveries_id", "notification_deliveries", ["id"]), ("ix_notification_deliveries_event_type", "notification_deliveries", ["event_type"]), ("ix_notification_deliveries_channel", "notification_deliveries", ["channel"]), ("ix_notification_deliveries_status", "notification_deliveries", ["status"]), ("ix_notification_deliveries_created_at", "notification_deliveries", ["created_at"]),
        ("ix_telegram_link_tokens_id", "telegram_link_tokens", ["id"]), ("ix_telegram_link_tokens_user_id", "telegram_link_tokens", ["user_id"]), ("ix_telegram_link_tokens_token_hash", "telegram_link_tokens", ["token_hash"]), ("ix_telegram_link_tokens_expires_at", "telegram_link_tokens", ["expires_at"]),
        ("ix_background_jobs_id", "background_jobs", ["id"]), ("ix_background_jobs_job_type", "background_jobs", ["job_type"]), ("ix_background_jobs_status", "background_jobs", ["status"]), ("ix_background_jobs_available_at", "background_jobs", ["available_at"]), ("ix_background_jobs_created_at", "background_jobs", ["created_at"]), ("ix_background_jobs_claim", "background_jobs", ["status", "available_at"]),
    ):
        op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    for table in ("rate_limit_states", "background_jobs", "telegram_link_tokens", "notification_deliveries", "replenishments", "audit_logs", "alerts", "cash_inventory", "forecasts", "users", "atms", "roles"):
        op.drop_table(table)
