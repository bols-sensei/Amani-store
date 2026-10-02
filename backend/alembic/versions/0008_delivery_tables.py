"""Tables livraison (prompt 4) : shipments, delivery_tokens,
delivery_confirmations, delivery_disputes, delivery_reschedules,
documents, courier_profiles.

Ajoute aussi la FK order_items.shipment_id -> shipments.id
(PostgreSQL uniquement ; ignorée sur SQLite/tests).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_delivery_tables"
down_revision: Union[str, None] = "0007_cart_order_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = sa.Uuid(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "shipments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False, unique=True),
        sa.Column("order_id", UUID,
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("courier_id", UUID,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("delivery_zone_id", UUID,
                  sa.ForeignKey("delivery_zones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("estimated_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(300), nullable=True),
        sa.Column("proof_photo_url", sa.Text(), nullable=True),
        sa.Column("signature_url", sa.Text(), nullable=True),
        sa.Column("confirmed_by_qr", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confirmed_by_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confirmation_method", sa.String(30), nullable=True),
        sa.Column("receipt_number", sa.String(40), nullable=True, unique=True),
        sa.Column("receipt_pdf_url", sa.Text(), nullable=True),
        sa.Column("receipt_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_shipments_order_id", "shipments", ["order_id"])
    op.create_index("ix_shipments_tenant_status", "shipments", ["tenant_id", "status"])
    op.create_index("ix_shipments_courier_status", "shipments", ["courier_id", "status"])
    op.create_index("ix_shipments_reference", "shipments", ["reference"])

    # FK order_items.shipment_id (PostgreSQL seulement ; SQLite s'en passe).
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_order_items_shipment", "order_items", "shipments",
            ["shipment_id"], ["id"], ondelete="SET NULL",
        )

    op.create_table(
        "delivery_tokens",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("shipment_id", UUID,
                  sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("manual_code", sa.String(6), nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dt_shipment_status", "delivery_tokens", ["shipment_id", "status"])

    op.create_table(
        "delivery_confirmations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("shipment_id", UUID,
                  sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID,
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("method", sa.String(30), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dc_shipment_id", "delivery_confirmations", ["shipment_id"])

    op.create_table(
        "delivery_disputes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("shipment_id", UUID,
                  sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", UUID,
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", UUID,
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_urls", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by", UUID,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dd_shipment_status", "delivery_disputes", ["shipment_id", "status"])
    op.create_index("ix_dd_tenant_status", "delivery_disputes", ["tenant_id", "status"])

    op.create_table(
        "delivery_reschedules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("shipment_id", UUID,
                  sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by", UUID,
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_role", sa.String(20), nullable=False),
        sa.Column("old_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("approved_by", UUID,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dr_shipment_status", "delivery_reschedules", ["shipment_id", "status"])

    op.create_table(
        "documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("reference_type", sa.String(20), nullable=False),
        sa.Column("reference_id", UUID, nullable=False),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("owner_type", sa.String(20), nullable=False),
        sa.Column("owner_id", UUID, nullable=False),
        sa.Column("pdf_url", sa.Text(), nullable=False),
        sa.Column("public_url", sa.Text(), nullable=True),
        sa.Column("qr_code_url", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_number", "documents", ["number"])
    op.create_index("ix_documents_owner", "documents", ["owner_type", "owner_id"])
    op.create_index("ix_documents_reference", "documents", ["reference_type", "reference_id"])

    op.create_table(
        "courier_profiles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID,
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vehicle_type", sa.String(20), nullable=False, server_default="moto"),
        sa.Column("vehicle_plate", sa.String(40), nullable=True),
        sa.Column("phone_secondary", sa.String(30), nullable=True),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cp_tenant_available", "courier_profiles", ["tenant_id", "is_available"])


def downgrade() -> None:
    op.drop_table("courier_profiles")
    op.drop_table("documents")
    op.drop_table("delivery_reschedules")
    op.drop_table("delivery_disputes")
    op.drop_table("delivery_confirmations")
    op.drop_table("delivery_tokens")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("fk_order_items_shipment", "order_items", type_="foreignkey")
    op.drop_table("shipments")
