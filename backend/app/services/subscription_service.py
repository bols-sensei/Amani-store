"""Subscription service (prompt 5) — plan lifecycle per tenant.

Every tenant gets a subscription automatically (default FREE). Plan changes
are recorded in subscription_history and mirrored onto tenant.plan_name /
tenant.commission_rate so legacy code paths keep working. Events are emitted
by callers AFTER commit.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import events
from app.core.exceptions import NotFoundError, ValidationError_
from app.crud import business_rule as crud_rules
from app.db.base import new_uuid, utcnow
from app.models.finance import Plan, Subscription, SubscriptionHistory
from app.models.tenant import Tenant


def _period_end(start: datetime) -> datetime:
    """One calendar month after `start` (clamped to month end implicitly)."""
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1, day=1)
    return start.replace(month=start.month + 1, day=1)


async def get_current_plan(db: AsyncSession, tenant_id: str) -> Plan:
    sub = await get_or_create_subscription(db, tenant_id)
    plan = await db.get(Plan, sub.plan_id)
    if plan is None:
        raise NotFoundError("Plan de référence introuvable")
    return plan


async def get_or_create_subscription(
    db: AsyncSession, tenant_id: str, *, with_trial: bool = False
) -> Subscription:
    """Return the active subscription, creating a default FREE one if needed."""
    sub = (await db.execute(
        select(Subscription).where(
            Subscription.tenant_id == tenant_id,
            Subscription.status.in_(("active", "trialing", "past_due", "suspended")),
        ).order_by(Subscription.created_at.desc())
    )).scalars().first()
    if sub is not None:
        return sub

    free = (await db.execute(select(Plan).where(Plan.key == "free"))).scalars().first()
    if free is None:
        raise NotFoundError("Plan gratuit non configuré (seed manquant)")
    now = utcnow()
    trial_days = float(await crud_rules.get_rule_number(db, "billing.trial_days", 0))
    status = "active"
    trial_ends_at: Optional[datetime] = None
    if with_trial and trial_days > 0:
        status = "trialing"
        trial_ends_at = now + timedelta(days=trial_days)
    sub = Subscription(
        id=new_uuid(),
        tenant_id=tenant_id,
        plan_id=free.id,
        status=status,
        started_at=now,
        current_period_start=now,
        current_period_end=_period_end(now),
        trial_ends_at=trial_ends_at,
    )
    db.add(sub)
    await db.flush()
    return sub


async def change_plan(
    db: AsyncSession,
    tenant_id: str,
    new_plan_key: str,
    reason: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> Subscription:
    """Switch the tenant to another plan; mirror on Tenant; write history."""
    sub = await get_or_create_subscription(db, tenant_id)
    plan = (await db.execute(
        select(Plan).where(Plan.key == new_plan_key, Plan.is_active.is_(True))
    )).scalars().first()
    if plan is None:
        raise ValidationError_(f"Plan inconnu ou inactif : {new_plan_key}")
    if plan.id == sub.plan_id:
        return sub

    old_plan_id = sub.plan_id
    now = utcnow()
    sub.plan_id = plan.id
    sub.status = "active"
    sub.current_period_start = now
    sub.current_period_end = _period_end(now)
    sub.trial_ends_at = None

    db.add(SubscriptionHistory(
        id=new_uuid(), tenant_id=tenant_id, old_plan_id=old_plan_id,
        new_plan_id=plan.id, changed_by=changed_by, reason=reason, changed_at=now,
    ))

    tenant = await db.get(Tenant, tenant_id)
    if tenant is not None:
        tenant.plan_name = plan.key
        tenant.commission_rate = plan.commission_rate

    await db.flush()
    return sub


async def cancel_subscription(
    db: AsyncSession, tenant_id: str, reason: Optional[str] = None
) -> Subscription:
    sub = await get_or_create_subscription(db, tenant_id)
    if sub.status == "cancelled":
        return sub
    sub.status = "cancelled"
    sub.cancelled_at = utcnow()
    sub.cancel_reason = reason
    await db.flush()
    return sub


async def check_expired_trials(db: AsyncSession) -> int:
    """Downgrade trialing subscriptions whose trial ended back to FREE."""
    now = utcnow()
    rows = (await db.execute(
        select(Subscription).where(
            Subscription.status == "trialing",
            Subscription.trial_ends_at.is_not(None),
            Subscription.trial_ends_at < now,
        )
    )).scalars().all()
    for sub in rows:
        await change_plan(
            db, sub.tenant_id, "free",
            reason="Période d'essai expirée — retour automatique au plan gratuit",
        )
    return len(rows)


async def emit_subscription_event(name: str, sub: Subscription) -> None:
    """Emit a subscription.* event (call AFTER commit)."""
    await events.emit(name, {
        "subscription_id": sub.id,
        "tenant_id": sub.tenant_id,
        "plan_id": sub.plan_id,
        "status": sub.status,
    })
