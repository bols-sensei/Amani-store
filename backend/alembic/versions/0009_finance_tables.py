"""Finance tables (prompt 5): plans, commission_rules, subscriptions,
subscription_history, saas_invoices, saas_invoice_items, commission_records,
payments_received, tenant_billing_preferences.

Amounts stored in USD (reference currency). Extensible values are plain
String columns (no frozen Python enums), per project conventions.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_finance_tables"
down_revision: Union[str, None] = "0008_delivery_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = sa.Uuid(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("key", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("price_usd_monthly", sa.Numeric(12, 2), nullable=False,
                  server_default="0"),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("commission_min_usd", sa.Numeric(12, 2), nullable=False,
                  server_default="0"),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "commission_rules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("category_id", UUID,
                  sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("applies_to", sa.String(20), nullable=False,
                  server_default="products"),
        sa.Column("rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("min_amount_usd", sa.Numeric(12, 2), nullable=False,
                  server_default="0"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", UUID,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commission_rules_tenant_active", "commission_rules",
                    ["tenant_id", "is_active"])
    op.create_index("ix_commission_rules_active_priority", "commission_rules",
                    ["is_active", "priority"])

    op.create_table(
        "subscriptions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", UUID,
                  sa.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(300), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_subscriptions_tenant_status", "subscriptions",
                    ["tenant_id", "status"])
    op.create_index("ix_subscriptions_period_end", "subscriptions",
                    ["current_period_end"])

    op.create_table(
        "subscription_history",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_plan_id", UUID,
                  sa.ForeignKey("plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("new_plan_id", UUID,
                  sa.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("changed_by", UUID,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.String(300), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "saas_invoices",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", UUID,
                  sa.ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subscription_amount_usd", sa.Numeric(12, 2), nullable=False,
                  server_default="0"),
        sa.Column("commission_amount_usd", sa.Numeric(12, 2), nullable=False,
                  server_default="0"),
        sa.Column("total_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("currency_display", sa.String(8), nullable=False,
                  server_default="USD"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_amount_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("payment_method", sa.String(30), nullable=True),
        sa.Column("payment_reference", sa.String(120), nullable=True),
        sa.Column("pdf_url", sa.Text(), nullable=True),
        sa.Column("public_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_saas_invoices_tenant_status", "saas_invoices",
                    ["tenant_id", "status"])
    op.create_index("ix_saas_invoices_status_due", "saas_invoices",
                    ["status", "due_date"])
    op.create_index("ix_saas_invoices_number", "saas_invoices", ["number"])

    op.create_table(
        "saas_invoice_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("invoice_id", UUID,
                  sa.ForeignKey("saas_invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=True),
        sa.Column("reference_id", UUID, nullable=True),
        sa.Column("amount_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_saas_invoice_items_invoice", "saas_invoice_items",
                    ["invoice_id"])

    op.create_table(
        "commission_records",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", UUID,
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_item_id", UUID,
                  sa.ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("rate_used", sa.Numeric(5, 4), nullable=False),
        sa.Column("rule_id", UUID,
                  sa.ForeignKey("commission_rules.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("invoice_id", UUID,
                  sa.ForeignKey("saas_invoices.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invoiced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_commission_records_tenant_status", "commission_records",
                    ["tenant_id", "status"])
    op.create_index("ix_commission_records_order", "commission_records", ["order_id"])
    op.create_index("ix_commission_records_invoice", "commission_records",
                    ["invoice_id"])

    op.create_table(
        "payments_received",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("invoice_id", UUID,
                  sa.ForeignKey("saas_invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(30), nullable=False),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("received_by", UUID,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payments_received_invoice", "payments_received", ["invoice_id"])
    op.create_index("ix_payments_received_tenant", "payments_received", ["tenant_id"])

    op.create_table(
        "tenant_billing_preferences",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("tenant_id", UUID,
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
                  unique=True),
        sa.Column("billing_email", sa.String(254), nullable=True),
        sa.Column("billing_phone", sa.String(30), nullable=True),
        sa.Column("billing_name", sa.String(120), nullable=True),
        sa.Column("billing_address", sa.Text(), nullable=True),
        sa.Column("payment_method_preferred", sa.String(30), nullable=True),
        sa.Column("payment_details", sa.JSON(), nullable=True),
        sa.Column("auto_reminders", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "tenant_billing_preferences", "payments_received", "commission_records",
        "saas_invoice_items", "saas_invoices", "subscription_history",
        "subscriptions", "commission_rules", "plans",
    ):
        op.drop_table(table)
