"""baseline

Revision ID: 001
Revises:
Create Date: 2026-06-15

"""

from collections.abc import Sequence

revision: str = "001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
