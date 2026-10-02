"""Finance models (prompt 5): plans, subscriptions, commission rules/records,
SaaS invoices, payments and billing preferences.

Design notes:
- All extensible values (statuses, plan keys, payment methods) are plain
  String columns backed by reference data in DB — never frozen Python enums.
- Amounts are always stored in USD (reference currency). Display conversion
  happens through currency_service using the snapshot rate on each document.
- Commission is computed on product subtotal only (business rule
  ``commission.calculation_base``), never on delivery fees.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDType, new_uuid, utcnow


class Plan(Base, TimestampMixin):
    """Subscription plan definition (free / pro / business ...)."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    price_usd_monthly: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    commission_min_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    limits: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CommissionRule(Base, TimestampMixin):
    """Commission rule with cascade resolution.

    Specificity order (highest priority wins, then scope):
      tenant-specific rule > category rule > global rule (tenant_id NULL).
    """

    __tablename__ = "commission_rules"
    __table_args__ = (
        Index("ix_commission_rules_tenant_active", "tenant_id", "is_active"),
        Index("ix_commission_rules_active_priority", "is_active", "priority"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    tenant_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    category_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    applies_to: Mapped[str] = mapped_column(
        String(20), nullable=False, default="products"
    )  # products | delivery | both
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    min_amount_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Subscription(Base, TimestampMixin):
    """Current subscription of a tenant to a plan."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_tenant_status", "tenant_id", "status"),
        Index("ix_subscriptions_period_end", "current_period_end"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # active | past_due | cancelled | trialing | suspended
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    plan: Mapped[Plan] = relationship(lazy="selectin")


class SubscriptionHistory(Base):
    """Immutable audit trail of plan changes."""

    __tablename__ = "subscription_history"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    old_plan_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("plans.id", ondelete="SET NULL"), nullable=True
    )
    new_plan_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )
    changed_by: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class SaasInvoice(Base, TimestampMixin):
    """Monthly SaaS invoice: subscription fee + accumulated commissions.

    The platform never touches sale money (principle P1); this invoice is a
    debt owed by the vendor, settled via mobile money / bank / cash and
    recorded manually by a superadmin.
    """

    __tablename__ = "saas_invoices"
    __table_args__ = (
        Index("ix_saas_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_saas_invoices_status_due", "status", "due_date"),
        Index("ix_saas_invoices_number", "number"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subscription_amount_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    commission_amount_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    total_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    currency_display: Mapped[str] = mapped_column(
        String(8), nullable=False, default="USD"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft"
    )  # draft | sent | paid | overdue | cancelled
    issued_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_amount_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    payment_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    pdf_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    public_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    items: Mapped[list["SaasInvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin"
    )


class SaasInvoiceItem(Base):
    """Line item of a SaaS invoice (subscription or commission block)."""

    __tablename__ = "saas_invoice_items"
    __table_args__ = (Index("ix_saas_invoice_items_invoice", "invoice_id"),)

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    invoice_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("saas_invoices.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # subscription | commission
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    reference_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(UUIDType, nullable=True)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    invoice: Mapped[SaasInvoice] = relationship(back_populates="items")


class CommissionRecord(Base):
    """One commission per delivered order_item (financial truth point).

    Lifecycle: pending -> invoiced -> paid (or cancelled).
    """

    __tablename__ = "commission_records"
    __table_args__ = (
        Index("ix_commission_records_tenant_status", "tenant_id", "status"),
        Index("ix_commission_records_order", "order_id"),
        Index("ix_commission_records_invoice", "invoice_id"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    order_item_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    rate_used: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    rule_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("commission_rules.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | invoiced | paid | cancelled
    invoice_id: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("saas_invoices.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    invoiced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PaymentReceived(Base):
    """Manual record of a vendor payment received by the platform."""

    __tablename__ = "payments_received"
    __table_args__ = (
        Index("ix_payments_received_invoice", "invoice_id"),
        Index("ix_payments_received_tenant", "tenant_id"),
    )

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    invoice_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("saas_invoices.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # mobile_money | bank_transfer | cash | other
    reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    received_by: Mapped[Optional[str]] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class TenantBillingPreference(Base, TimestampMixin):
    """Per-tenant billing contact details and payment preferences."""

    __tablename__ = "tenant_billing_preferences"

    id: Mapped[str] = mapped_column(UUIDType, primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(
        UUIDType, ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    billing_email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    billing_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    billing_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    billing_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payment_method_preferred: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )
    payment_details: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    auto_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
