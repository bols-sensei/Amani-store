"""Billing service (prompt 5) — monthly SaaS invoices + overdue lifecycle.

A monthly invoice = subscription fee + all pending commission records of the
period. The platform never collects sale money (principle P1): commissions
are a debt invoiced to the vendor, paid off-platform (mobile money / bank /
cash) and recorded manually by a superadmin.

Statuses: draft -> sent -> paid | overdue -> (suspended after grace).
All delays come from business_rules (billing.*), nothing is hardcoded.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import events
from app.core.exceptions import ConflictError, NotFoundError, ValidationError_
from app.crud import business_rule as crud_rules
from app.db.base import new_uuid, utcnow
from app.models.finance import (
    CommissionRecord,
    PaymentReceived,
    Plan,
    SaasInvoice,
    SaasInvoiceItem,
    Subscription,
)
from app.models.tenant import Tenant
from app.services import commission_service, reference_generator

logger = logging.getLogger("kimia.billing")


async def generate_saas_invoice_number(db: AsyncSession) -> str:
    """INV-2026-00042 (shared yearly counter with other references)."""
    year = utcnow().year
    n = await reference_generator.next_sequence(db, "INV", year)
    return f"INV-{year}-{n:05d}"


async def generate_monthly_invoice(
    db: AsyncSession,
    tenant_id: str,
    period_start: datetime,
    period_end: datetime,
) -> Optional[SaasInvoice]:
    """Build one tenant's monthly SaaS invoice (idempotent per period).

    Returns None when there is nothing to bill (free plan, no commissions).
    """
    existing = (await db.execute(
        select(SaasInvoice).where(
            SaasInvoice.tenant_id == tenant_id,
            SaasInvoice.period_start == period_start,
            SaasInvoice.status != "cancelled",
        )
    )).scalars().first()
    if existing is not None:
        return existing

    from app.services import subscription_service

    sub = await subscription_service.get_or_create_subscription(db, tenant_id)
    plan = await db.get(Plan, sub.plan_id)
    if plan is None:
        raise NotFoundError("Plan introuvable pour l'abonnement")

    pending = await commission_service.get_pending_commissions(
        db, tenant_id, period_start, period_end
    )
    subscription_amount = Decimal(str(plan.price_usd_monthly))
    commission_total = sum((Decimal(str(r.amount_usd)) for r in pending), Decimal("0"))

    if subscription_amount <= 0 and commission_total <= 0:
        return None  # rien à facturer ce mois-ci

    due_days = float(await crud_rules.get_rule_number(db, "billing.payment_due_days", 7))
    now = utcnow()
    number = await generate_saas_invoice_number(db)
    tenant = await db.get(Tenant, tenant_id)

    invoice = SaasInvoice(
        id=new_uuid(),
        number=number,
        tenant_id=tenant_id,
        subscription_id=sub.id,
        period_start=period_start,
        period_end=period_end,
        subscription_amount_usd=subscription_amount,
        commission_amount_usd=commission_total,
        total_usd=subscription_amount + commission_total,
        currency_display="USD",  # invoices are issued in reference currency
        status="sent",
        issued_at=now,
        due_date=now + timedelta(days=due_days),
    )
    db.add(invoice)
    await db.flush()

    if subscription_amount > 0:
        db.add(SaasInvoiceItem(
            id=new_uuid(), invoice_id=invoice.id, type="subscription",
            description=f"Abonnement {plan.name} — période du "
                        f"{period_start:%d/%m/%Y} au {period_end:%d/%m/%Y}",
            amount_usd=subscription_amount,
            metadata_={"plan_key": plan.key},
        ))

    if pending:
        # One aggregated line + per-record linkage for traceability.
        db.add(SaasInvoiceItem(
            id=new_uuid(), invoice_id=invoice.id, type="commission",
            description=f"Commissions sur ventes livrées ({len(pending)} article(s))",
            amount_usd=commission_total,
            metadata_={"record_ids": [r.id for r in pending]},
        ))
        await commission_service.mark_as_invoiced(
            db, [r.id for r in pending], invoice.id
        )

    await db.flush()
    return invoice


async def generate_all_monthly_invoices(
    db: AsyncSession, period_start: datetime, period_end: datetime
) -> list[SaasInvoice]:
    """Generate invoices for every active tenant (cron: 1st of month)."""
    tenants = (await db.execute(
        select(Tenant).where(Tenant.status.in_(("active", "trial")))
    )).scalars().all()
    created: list[SaasInvoice] = []
    for tenant in tenants:
        inv = await generate_monthly_invoice(db, tenant.id, period_start, period_end)
        if inv is not None:
            created.append(inv)
    return created


async def mark_invoice_paid(
    db: AsyncSession,
    invoice_id: str,
    amount: Decimal,
    method: str,
    reference: Optional[str] = None,
    received_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> SaasInvoice:
    """Register a payment against an invoice (atomic: payment + records)."""
    invoice = await db.get(SaasInvoice, invoice_id)
    if invoice is None:
        raise NotFoundError("Facture introuvable")
    if invoice.status == "paid":
        raise ConflictError("Cette facture est déjà payée")
    if invoice.status == "cancelled":
        raise ConflictError("Une facture annulée ne peut pas être payée")
    if method not in ("mobile_money", "bank_transfer", "cash", "other"):
        raise ValidationError_("Méthode de paiement inconnue")

    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValidationError_("Le montant doit être positif")

    now = utcnow()
    db.add(PaymentReceived(
        id=new_uuid(), invoice_id=invoice.id, tenant_id=invoice.tenant_id,
        amount_usd=amount, method=method, reference=reference,
        received_by=received_by, received_at=now, notes=notes,
    ))
    invoice.paid_amount_usd = amount
    invoice.paid_at = now
    invoice.payment_method = method
    invoice.payment_reference = reference
    invoice.status = "paid"

    records = (await db.execute(
        select(CommissionRecord).where(
            CommissionRecord.invoice_id == invoice.id,
            CommissionRecord.status == "invoiced",
        )
    )).scalars().all()
    await commission_service.mark_as_paid(db, [r.id for r in records])
    await db.flush()
    return invoice


async def cancel_invoice(db: AsyncSession, invoice_id: str, reason: Optional[str] = None) -> SaasInvoice:
    invoice = await db.get(SaasInvoice, invoice_id)
    if invoice is None:
        raise NotFoundError("Facture introuvable")
    if invoice.status == "paid":
        raise ConflictError("Impossible d'annuler une facture payée")
    invoice.status = "cancelled"
    invoice.notes = reason or invoice.notes
    # Release linked commissions back to pending for the next cycle.
    rows = (await db.execute(
        select(CommissionRecord).where(
            CommissionRecord.invoice_id == invoice.id,
            CommissionRecord.status == "invoiced",
        )
    )).scalars().all()
    for rec in rows:
        rec.status = "pending"
        rec.invoice_id = None
        rec.invoiced_at = None
    await db.flush()
    return invoice


async def check_overdue_invoices(db: AsyncSession) -> int:
    """sent invoices past due_date -> overdue (+ event payload list)."""
    now = utcnow()
    rows = (await db.execute(
        select(SaasInvoice).where(
            SaasInvoice.status == "sent",
            SaasInvoice.due_date < now,
        )
    )).scalars().all()
    for inv in rows:
        inv.status = "overdue"
    await db.flush()
    return len(rows)


async def get_reminder_days(db: AsyncSession) -> list[int]:
    raw = await crud_rules.get_rule(db, "billing.reminder_days", "[1, 7, 15]")
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return [int(d) for d in value]
    except (TypeError, ValueError):
        return [1, 7, 15]


async def send_reminder(db: AsyncSession, invoice_id: str, day: int) -> bool:
    """Reminder stub — real dispatch wired in prompt 6 (notifications).

    Returns True when a reminder is due today for that invoice.
    """
    invoice = await db.get(SaasInvoice, invoice_id)
    if invoice is None:
        raise NotFoundError("Facture introuvable")
    if invoice.status not in ("sent", "overdue"):
        return False
    prefs = await get_billing_preferences(db, invoice.tenant_id)
    if prefs is not None and not prefs.auto_reminders:
        return False
    due = invoice.due_date
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    days_past = (utcnow() - due).days
    if days_past == int(day):
        await events.emit("invoice.reminder", {
            "invoice_id": invoice.id, "number": invoice.number,
            "tenant_id": invoice.tenant_id, "day": day,
        })
        return True
    return False


async def find_due_reminders(db: AsyncSession) -> list[tuple[SaasInvoice, int]]:
    """Invoices whose overdue age matches a configured reminder day."""
    days = await get_reminder_days(db)
    rows = (await db.execute(
        select(SaasInvoice).where(SaasInvoice.status.in_(("sent", "overdue")))
    )).scalars().all()
    out: list[tuple[SaasInvoice, int]] = []
    for inv in rows:
        due = inv.due_date
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        past = (utcnow() - due).days
        if past in days:
            out.append((inv, past))
    return out


async def auto_suspend_non_paying(db: AsyncSession) -> int:
    """Overdue beyond billing.suspend_after_days -> tenant suspended."""
    enabled = await crud_rules.get_rule(db, "billing.auto_suspend", "true")
    if str(enabled).lower() not in ("true", "1", "yes"):
        return 0
    limit = float(await crud_rules.get_rule_number(db, "billing.suspend_after_days", 30))
    cutoff = utcnow() - timedelta(days=limit)
    rows = (await db.execute(
        select(SaasInvoice).where(
            SaasInvoice.status == "overdue",
            SaasInvoice.due_date < cutoff,
        )
    )).scalars().all()
    suspended = 0
    seen: set[str] = set()
    for inv in rows:
        if inv.tenant_id in seen:
            continue
        seen.add(inv.tenant_id)
        tenant = await db.get(Tenant, inv.tenant_id)
        if tenant is not None and tenant.status == "active":
            tenant.status = "suspended"
            suspended += 1
            await events.emit("tenant.suspended", {
                "tenant_id": tenant.id, "reason": "facture SaaS impayée",
                "invoice_number": inv.number,
            })
    await db.flush()
    return suspended


async def get_billing_preferences(db: AsyncSession, tenant_id: str):
    from app.models.finance import TenantBillingPreference

    return (await db.execute(
        select(TenantBillingPreference).where(
            TenantBillingPreference.tenant_id == tenant_id
        )
    )).scalars().first()


async def finance_summary(db: AsyncSession, tenant_id: str) -> dict:
    """Vendor-facing financial summary (read-only aggregation)."""
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    from app.models.order import Order, OrderItem

    revenue_today = (await db.execute(
        select(func.coalesce(func.sum(OrderItem.subtotal_usd), 0)).join(
            Order, Order.id == OrderItem.order_id
        ).where(
            OrderItem.tenant_id == tenant_id,
            OrderItem.delivered_at.is_not(None),
            OrderItem.delivered_at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
        )
    )).scalar() or 0
    revenue_month = (await db.execute(
        select(func.coalesce(func.sum(OrderItem.subtotal_usd), 0)).join(
            Order, Order.id == OrderItem.order_id
        ).where(
            OrderItem.tenant_id == tenant_id,
            OrderItem.delivered_at.is_not(None),
            OrderItem.delivered_at >= month_start,
        )
    )).scalar() or 0

    async def _sum(statuses: tuple[str, ...]) -> Decimal:
        val = (await db.execute(
            select(func.coalesce(func.sum(CommissionRecord.amount_usd), 0)).where(
                CommissionRecord.tenant_id == tenant_id,
                CommissionRecord.status.in_(statuses),
            )
        )).scalar() or 0
        return Decimal(str(val))

    pending = await _sum(("pending", "invoiced"))
    paid = await _sum(("paid",))
    open_invoices = (await db.execute(
        select(func.count(SaasInvoice.id)).where(
            SaasInvoice.tenant_id == tenant_id,
            SaasInvoice.status.in_(("sent", "overdue")),
        )
    )).scalar() or 0

    return {
        "revenue_today_usd": Decimal(str(revenue_today)),
        "revenue_month_usd": Decimal(str(revenue_month)),
        "pending_commissions_usd": pending,
        "paid_commissions_usd": paid,
        "open_invoices": int(open_invoices),
    }


async def emit_invoice_event(name: str, invoice: SaasInvoice) -> None:
    """Emit invoice.* event (call AFTER commit)."""
    await events.emit(name, {
        "invoice_id": invoice.id, "number": invoice.number,
        "tenant_id": invoice.tenant_id, "status": invoice.status,
        "total_usd": str(invoice.total_usd),
    })
