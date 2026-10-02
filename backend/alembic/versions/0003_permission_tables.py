"""Tables permissions : permissions, role_templates, user_permissions.

Groupe logique #3 — RBAC config-driven. Les clés de permissions et les
templates sont des données en base (seedées), jamais des enums Python.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_permission_tables"
down_revision: Union[str, None] = "0002_auth_tenant_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("key", sa.String(80), nullable=False, unique=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("plan_min", sa.String(20), nullable=False, server_default="free"),
    )
    op.create_index("ix_permissions_category", "permissions", ["category"])

    op.create_table(
        "role_templates",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("key", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "user_permissions",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "permission_key",
            sa.String(80),
            sa.ForeignKey("permissions.key", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_permissions_user_id", "user_permissions", ["user_id"])
    op.create_unique_constraint(
        "uq_user_permission", "user_permissions", ["user_id", "permission_key"]
    )


def downgrade() -> None:
    op.drop_table("user_permissions")
    op.drop_table("role_templates")
    op.drop_table("permissions")
