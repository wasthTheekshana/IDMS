"""Platform admin: platform_admins table, organization suspend/AI-toggle
columns, and the idms_platform_admin BYPASSRLS role for cross-org reads.

Revision ID: 006
Revises: 005
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.config import settings

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_admins",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_platform_admins_email", "platform_admins", ["email"], unique=True
    )

    op.add_column(
        "organizations",
        sa.Column("is_suspended", sa.Boolean, server_default="false", nullable=False),
    )
    op.add_column(
        "organizations",
        sa.Column("ai_qa_enabled", sa.Boolean, server_default="true", nullable=False),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "ai_summarization_enabled",
            sa.Boolean,
            server_default="true",
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "ai_search_answer_enabled",
            sa.Boolean,
            server_default="true",
            nullable=False,
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "ai_extraction_enabled", sa.Boolean, server_default="false", nullable=False
        ),
    )

    # ── Platform-admin DB role ──────────────────────────────────────────────
    # BYPASSRLS lets this role read/write across every org — it's the ONLY
    # role that can; every other connection is still subject to FORCE RLS.
    # Roles are cluster-wide (not per-database), so creation must be
    # idempotent — this same migration also runs against idms_test, which
    # shares the Postgres cluster/role namespace with the main idms database.
    #
    # The password is trusted server-side config (not user input), so
    # interpolating it into DDL here follows the same pattern already used
    # for org_id in core/deps.py's SET LOCAL statement.
    password = settings.PLATFORM_ADMIN_DB_PASSWORD
    assert "'" not in password, "PLATFORM_ADMIN_DB_PASSWORD must not contain '"
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM pg_roles WHERE rolname = 'idms_platform_admin'
            ) THEN
                CREATE ROLE idms_platform_admin
                    WITH LOGIN PASSWORD '{password}' BYPASSRLS;
            END IF;
        END
        $$;
    """)  # nosec B608 - trusted server-side config value, not user input; quote injection ruled out by the assert above
    op.execute("GRANT SELECT ON organizations TO idms_platform_admin")
    op.execute(
        "GRANT UPDATE (is_suspended, ai_qa_enabled, ai_summarization_enabled, "
        "ai_search_answer_enabled, ai_extraction_enabled) ON organizations "
        "TO idms_platform_admin"
    )
    op.execute("GRANT SELECT ON users TO idms_platform_admin")
    op.execute("GRANT SELECT ON documents TO idms_platform_admin")
    op.execute("GRANT SELECT ON api_usage TO idms_platform_admin")


def downgrade() -> None:
    # Deliberately does NOT drop the idms_platform_admin role or its grants —
    # it's a cluster-wide principal that idms_test's copy of this migration
    # also depends on; dropping it here could break the other database.
    # Removing it for real is a manual DBA step: DROP ROLE idms_platform_admin;
    op.drop_column("organizations", "ai_extraction_enabled")
    op.drop_column("organizations", "ai_search_answer_enabled")
    op.drop_column("organizations", "ai_summarization_enabled")
    op.drop_column("organizations", "ai_qa_enabled")
    op.drop_column("organizations", "is_suspended")
    op.drop_index("ix_platform_admins_email", table_name="platform_admins")
    op.drop_table("platform_admins")
