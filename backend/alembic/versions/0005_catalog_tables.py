"""Tables catalogue : categories, products, product_images, product_variants, search_queries.

Index GIN full-text (PostgreSQL uniquement) dans la migration 0006.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_catalog_tables"
down_revision: Union[str, None] = "0004_seed_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("parent_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(140), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon_url", sa.String(500), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_categories_tenant_slug"),
    )
    op.create_index("ix_categories_tenant_id", "categories", ["tenant_id"])
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(220), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("short_description", sa.String(200), nullable=True),
        sa.Column("price_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_input", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency_input", sa.String(8), nullable=False, server_default="CDF"),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sku", sa.String(80), nullable=True),
        sa.Column("weight_kg", sa.Numeric(8, 3), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("views_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sales_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_avg", sa.Numeric(3, 2), nullable=False, server_default="0"),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_products_tenant_slug"),
    )
    op.create_index("ix_products_tenant_id", "products", ["tenant_id"])
    op.create_index("ix_products_tenant_active_published", "products",
                    ["tenant_id", "is_active", "is_published"])
    op.create_index("ix_products_tenant_category", "products", ["tenant_id", "category_id"])

    op.create_table(
        "product_images",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("product_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("thumb_url", sa.Text(), nullable=True),
        sa.Column("medium_url", sa.Text(), nullable=True),
        sa.Column("alt_text", sa.String(250), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])

    op.create_table(
        "product_variants",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("product_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("value", sa.String(80), nullable=False),
        sa.Column("price_delta_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sku", sa.String(80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])

    op.create_table(
        "search_queries",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("query_text", sa.String(200), nullable=False),
        sa.Column("results_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicked_product_id", sa.Uuid(as_uuid=False),
                  sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_search_queries_tenant_created", "search_queries",
                    ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_table("search_queries")
    op.drop_table("product_variants")
    op.drop_table("product_images")
    op.drop_table("products")
    op.drop_table("categories")
