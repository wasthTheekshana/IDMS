"""Grant SELECT on platform_admins to idms_platform_admin.

Migration 006 granted the BYPASSRLS idms_platform_admin role SELECT on
organizations/users/documents/api_usage, but missed platform_admins itself —
needed for the platform-admin "/me" profile endpoint (Task 7), which reads
the admin's own record via the same cross-org AdminSession.

Revision ID: 007
Revises: 006
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON platform_admins TO idms_platform_admin")


def downgrade() -> None:
    # Deliberately does not revoke — see 006's downgrade note on the
    # cluster-wide, cross-database nature of this role.
    pass
