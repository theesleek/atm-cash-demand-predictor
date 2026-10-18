"""Align unique model indexes with the existing PostgreSQL schema."""

from alembic import op
import sqlalchemy as sa


revision = "0004_align_unique_indexes"
down_revision = "0003_atm_onboarding_ingestion"
branch_labels = None
depends_on = None


def _sqlite_align_unique_object(
    table_name: str,
    column_name: str,
    index_name: str,
    *,
    unique_index: bool,
    unique_constraint: bool,
) -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=bind)

    for constraint in list(table.constraints):
        if isinstance(constraint, sa.UniqueConstraint) and [column.name for column in constraint.columns] == [column_name]:
            table.constraints.remove(constraint)
    for index in list(table.indexes):
        if index.name == index_name:
            table.indexes.remove(index)

    if unique_index:
        sa.Index(index_name, table.c[column_name], unique=True)
    if unique_constraint:
        sa.UniqueConstraint(table.c[column_name])

    with op.batch_alter_table(table_name, recreate="always", copy_from=table):
        pass


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for table_name, column_name, index_name in (
            ("atms", "atm_code", "ix_atms_atm_code"),
            ("roles", "name", "ix_roles_name"),
            ("users", "username", "ix_users_username"),
            ("telegram_link_tokens", "token_hash", "ix_telegram_link_tokens_token_hash"),
            ("atm_history_records", "record_fingerprint", "ix_atm_history_records_record_fingerprint"),
        ):
            _sqlite_align_unique_object(
                table_name,
                column_name,
                index_name,
                unique_index=True,
                unique_constraint=False,
            )
        return

    op.drop_constraint("atms_atm_code_key", "atms", type_="unique")
    op.create_index("ix_atms_atm_code", "atms", ["atm_code"], unique=True)

    op.drop_constraint("roles_name_key", "roles", type_="unique")
    op.drop_index("ix_roles_name", table_name="roles")
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.drop_constraint("users_username_key", "users", type_="unique")
    op.drop_index("ix_users_username", table_name="users")
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.drop_constraint("telegram_link_tokens_token_hash_key", "telegram_link_tokens", type_="unique")
    op.drop_index("ix_telegram_link_tokens_token_hash", table_name="telegram_link_tokens")
    op.create_index("ix_telegram_link_tokens_token_hash", "telegram_link_tokens", ["token_hash"], unique=True)

    op.drop_constraint("atm_history_records_record_fingerprint_key", "atm_history_records", type_="unique")
    op.drop_index("ix_atm_history_records_record_fingerprint", table_name="atm_history_records")
    op.create_index("ix_atm_history_records_record_fingerprint", "atm_history_records", ["record_fingerprint"], unique=True)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        for table_name, column_name, index_name, keep_index in (
            ("atm_history_records", "record_fingerprint", "ix_atm_history_records_record_fingerprint", True),
            ("telegram_link_tokens", "token_hash", "ix_telegram_link_tokens_token_hash", True),
            ("users", "username", "ix_users_username", True),
            ("roles", "name", "ix_roles_name", True),
            ("atms", "atm_code", "ix_atms_atm_code", False),
        ):
            _sqlite_align_unique_object(
                table_name,
                column_name,
                index_name,
                unique_index=keep_index,
                unique_constraint=True,
            )
        return

    op.drop_index("ix_atm_history_records_record_fingerprint", table_name="atm_history_records")
    op.create_index("ix_atm_history_records_record_fingerprint", "atm_history_records", ["record_fingerprint"])
    op.create_unique_constraint("atm_history_records_record_fingerprint_key", "atm_history_records", ["record_fingerprint"])

    op.drop_index("ix_telegram_link_tokens_token_hash", table_name="telegram_link_tokens")
    op.create_index("ix_telegram_link_tokens_token_hash", "telegram_link_tokens", ["token_hash"])
    op.create_unique_constraint("telegram_link_tokens_token_hash_key", "telegram_link_tokens", ["token_hash"])

    op.drop_index("ix_users_username", table_name="users")
    op.create_index("ix_users_username", "users", ["username"])
    op.create_unique_constraint("users_username_key", "users", ["username"])

    op.drop_index("ix_roles_name", table_name="roles")
    op.create_index("ix_roles_name", "roles", ["name"])
    op.create_unique_constraint("roles_name_key", "roles", ["name"])

    op.drop_index("ix_atms_atm_code", table_name="atms")
    op.create_unique_constraint("atms_atm_code_key", "atms", ["atm_code"])
