"""Tables panier + commandes : carts, cart_items, orders, order_items,
order_status_history, delivery_zones.

N'ajoute pas de FK vers shipments (table créée en 0008) : la colonne
order_items.shipment_id est prévue nullable et rattachée en 0008 via
ALTER (PostgreSQL uniquement, ignoré sur SQLite/tests).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_cart_order_tables"
down_revision: Union[str, None] = "0006_catalog_fts_gin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = sa.Uuid(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "carts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("customer_id", UUID,
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("currency_display", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("is_empty", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("customer_id", name="uq_carts_customer"),
    )

    op.create_table(
        "cart_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("cart_id", UUID,
                  sa.ForeignKey("carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID,
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("cart_id", "product_id", name="uq_cart_items_cart_product"),
    )
    op.create_index("ix_cart_items_cart_id", "cart_items", ["cart_id"])

    op.create_table(
        "delivery_zones",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("regions", sa.JSON(), nullable=False),
        sa.Column("base_fee_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("estimated_days_min", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("estimated_days_max", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dz_tenant_active", "delivery_zones", ["tenant_id", "is_active"])

    op.create_table(
        "orders",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False, unique=True),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_id", UUID,
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("subtotal_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("delivery_fee_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("currency_at_creation", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("exchange_rate_used", sa.Numeric(12, 4), nullable=True),
        sa.Column("delivery_address", sa.JSON(), nullable=False),
        sa.Column("delivery_zone_id", UUID,
                  sa.ForeignKey("delivery_zones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("delivery_notes", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preparing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(300), nullable=True),
        sa.Column("cancelled_by", UUID,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kimia_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kimia_sync_status", sa.String(20), nullable=True),
        sa.Column("kimia_sync_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kimia_last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_orders_tenant_status", "orders", ["tenant_id", "status"])
    op.create_index("ix_orders_customer_created", "orders", ["customer_id", "created_at"])
    op.create_index("ix_orders_status_created", "orders", ["status", "created_at"])
    op.create_index("ix_orders_reference", "orders", ["reference"])

    op.create_table(
        "order_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("order_id", UUID,
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID,
                  sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shipment_id", UUID, nullable=True),  # FK ajoutée en 0008 (PG only)
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("product_short_description", sa.String(200), nullable=True),
        sa.Column("product_image_url", sa.Text(), nullable=True),
        sa.Column("sku", sa.String(80), nullable=True),
        sa.Column("unit_price_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("subtotal_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("commission_amount_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_tenant_id", "order_items", ["tenant_id"])

    op.create_table(
        "order_status_history",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("order_id", UUID,
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_status", sa.String(30), nullable=True),
        sa.Column("new_status", sa.String(30), nullable=False),
        sa.Column("changed_by", UUID,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_by_role", sa.String(30), nullable=True),
        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_osh_order_created", "order_status_history", ["order_id", "created_at"])


def downgrade() -> None:
    op.drop_table("order_status_history")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("delivery_zones")
    op.drop_table("cart_items")
    op.drop_table("carts")
