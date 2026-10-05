"""Ràng buộc: mỗi hồ sơ chỉ có tối đa một đề xuất đang chờ duyệt

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_decisions_one_pending_per_application ON decisions (organization_id, application_id) "
        "WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_decisions_one_pending_per_application")
