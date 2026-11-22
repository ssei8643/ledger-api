"""最初のテーブル（勘定科目・仕訳本体・仕訳明細）を作る

Revision ID: 0001
Revises:
Create Date: 2026-11-23 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("normal_side", sa.String(length=6), nullable=False),
        sa.CheckConstraint(
            "normal_side IN ('debit', 'credit')", name=op.f("ck_accounts_normal_side")
        ),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_accounts")),
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("reverses_id", sa.Integer(), nullable=True),
        sa.Column("import_key", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["reverses_id"],
            ["journal_entries.id"],
            name=op.f("fk_journal_entries_reverses_id_journal_entries"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entries")),
        sa.UniqueConstraint("import_key", name=op.f("uq_journal_entries_import_key")),
        sa.UniqueConstraint("reverses_id", name=op.f("uq_journal_entries_reverses_id")),
    )
    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("account", sa.String(length=50), nullable=False),
        sa.Column("side", sa.String(length=6), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_journal_lines_amount_positive")),
        sa.CheckConstraint("side IN ('debit', 'credit')", name=op.f("ck_journal_lines_side")),
        sa.ForeignKeyConstraint(
            ["account"], ["accounts.name"], name=op.f("fk_journal_lines_account_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_journal_lines_entry_id_journal_entries"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_lines")),
    )
    op.create_index(op.f("ix_journal_lines_account"), "journal_lines", ["account"], unique=False)
    op.create_index(op.f("ix_journal_lines_entry_id"), "journal_lines", ["entry_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_journal_lines_entry_id"), table_name="journal_lines")
    op.drop_index(op.f("ix_journal_lines_account"), table_name="journal_lines")
    op.drop_table("journal_lines")
    op.drop_table("journal_entries")
    op.drop_table("accounts")
