"""Grant UPDATE(monthly_page_quota) on organizations to idms_platform_admin.

Migration 006 granted the BYPASSRLS idms_platform_admin role UPDATE on the
suspension/AI-toggle columns but not monthly_page_quota, so a super admin
could not yet change an organization's page quota from the platform-admin
panel.

Revision ID: 008
Revises: 007
Create Date: 2026-09-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "GRANT UPDATE (monthly_page_quota) ON organizations TO idms_platform_admin"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE UPDATE (monthly_page_quota) ON organizations FROM idms_platform_admin"
    )
