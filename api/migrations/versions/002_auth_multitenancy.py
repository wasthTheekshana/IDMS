"""auth multitenancy: organizations, users, audit_logs + RLS

Revision ID: 002
Revises: 001
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: str | None = "001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("plan", sa.String(50), server_default="free", nullable=False),
        sa.Column(
            "monthly_page_quota", sa.Integer, server_default="500", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), server_default="member", nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("failed_login_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_secret", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_logs_org_id", "audit_logs", ["org_id"])

    # ── Row Level Security ────────────────────────────────────────────────────
    # SET LOCAL app.current_org_id is called by get_db() per transaction.
    # FORCE means the table owner (idms_app) is also filtered — no bypass.
    for table in ("organizations", "users", "audit_logs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # organizations: filter by id (the org IS the row)
    op.execute("""
        CREATE POLICY org_isolation ON organizations FOR ALL
          USING (id = current_setting('app.current_org_id', true)::uuid)
          WITH CHECK (id = current_setting('app.current_org_id', true)::uuid)
    """)

    # users + audit_logs: filter by org_id foreign key
    for table in ("users", "audit_logs"):
        op.execute(f"""
            CREATE POLICY org_isolation ON {table} FOR ALL
              USING (org_id = current_setting('app.current_org_id', true)::uuid)
              WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
        """)


def downgrade() -> None:
    for table in ("organizations", "users", "audit_logs"):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("audit_logs")
    op.drop_table("users")
    op.drop_table("organizations")
