"""documents + api_usage tables with RLS; org quota column

Revision ID: 003
Revises: 002
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: str | None = "002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "pages_used_this_month",
            sa.Integer,
            server_default="0",
            nullable=False,
        ),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("r2_key", sa.String(1000), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), server_default="uploaded", nullable=False),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("extracted_text", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("ocr_meta", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_org_id", "documents", ["org_id"])
    op.create_index("ix_documents_status", "documents", ["status"])

    op.create_table(
        "api_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service", sa.String(50), nullable=False),
        sa.Column("pages_used", sa.Integer, server_default="0", nullable=False),
        sa.Column("tokens_used", sa.Integer, server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Float, server_default="0.0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_api_usage_org_id", "api_usage", ["org_id"])

    for table in ("documents", "api_usage"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY org_isolation ON {table} FOR ALL
              USING (org_id = current_setting('app.current_org_id', true)::uuid)
              WITH CHECK (org_id = current_setting('app.current_org_id', true)::uuid)
            """
        )


def downgrade() -> None:
    for table in ("documents", "api_usage"):
        op.execute(f"DROP POLICY IF EXISTS org_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_api_usage_org_id", table_name="api_usage")
    op.drop_table("api_usage")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_org_id", table_name="documents")
    op.drop_table("documents")
    op.drop_column("organizations", "pages_used_this_month")
