"""Commission service (prompt 5) — configurable commission rules.

Rule cascade (most specific wins, then highest priority):
    tenant-specific rule > category rule > global rule (tenant_id NULL).

Commission formula (principle P2 — everything is config-driven):
    amount = MAX(subtotal_usd * rate, min_amount_usd)
computed on the product subtotal ONLY (never delivery fees), using the
rate/rule snapshotted at order creation when available; otherwise the
currently applicable rule is resolved and snapshotted onto the record.

Records lifecycle: pending -> invoiced -> paid (or cancelled).
A small in-process TTL cache (5 min) avoids re-querying rules on every
delivery confirmation (Redis optional, same pattern as currency_service).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import events
from app.db.base import new_uuid, utcnow
from app.models.finance import CommissionRecord, CommissionRule
from app.models.order import OrderItem

logger = logging.getLogger("kimia.commissions")

TWO_PLACES = Decimal("0.01")
_RULE_CACHE: dict[str, tuple[float, Optional[dict[str, Any]]]] = {}
_RULE_CACHE_TTL_SECONDS = 300  # 5 minutes


def _quantize(amount: Decimal) -> Decimal:
    return Decimal(amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def clear_rule_cache() -> None:
    """Invalidate the rule cache (tests / superadmin edits)."""
    _RULE_CACHE.clear()


async def get_applicable_rule(
    db: AsyncSession,
    tenant_id: str,
    category_id: Optional[str] = None,
) -> Optional[CommissionRule]:
    """Resolve the commission rule for a tenant (cascade + priority).

    Specificity tiers: tenant+category > tenant > global+category > global.
    Within a tier, the highest `priority` wins, then the most recently
    updated rule. Result cached 5 minutes per (tenant, category).
    """
    cache_key = f"{tenant_id}:{category_id or '-'}"
    hit = _RULE_CACHE.get(cache_key)
    if hit is not None and hit[0] > utcnow().timestamp():
        data = hit[1]
        if data is None:
            return None
        row = await db.get(CommissionRule, data["id"])
        if row is not None and row.is_active:
            return row

    candidates = (await db.execute(
        select(CommissionRule).where(CommissionRule.is_active.is_(True))
    )).scalars().all()

    def specificity(rule: CommissionRule) -> int:
        tenant_match = rule.tenant_id == tenant_id
        cat_match = rule.category_id == category_id if category_id else rule.category_id is None
        if tenant_match and rule.category_id == category_id and category_id:
            return 4
        if tenant_match and rule.category_id is None:
            return 3
        if rule.tenant_id is None and cat_match and category_id:
            return 2
        if rule.tenant_id is None and rule.category_id is None:
            return 1
        return 0

    scored = [(specificity(r), r.priority, r.updated_at, r) for r in candidates]
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        _RULE_CACHE[cache_key] = (utcnow().timestamp() + _RULE_CACHE_TTL_SECONDS, None)
        return None
    scored.sort(key=lambda s: (s[0], s[1], s[2]), reverse=True)
    best = scored[0][3]
    _RULE_CACHE[cache_key] = (
        utcnow().timestamp() + _RULE_CACHE_TTL_SECONDS,
        {"id": best.id},
    )
    return best


async def calculate_commission(
    db: AsyncSession, order_item: OrderItem
) -> dict[str, Any]:
    """Compute commission for one delivered order item.

    Uses the snapshot rate on the item when present (rate frozen at order
    creation); falls back to the currently applicable rule otherwise.
    Returns {amount_usd, rate, rule_id}.
    """
    base = Decimal(str(order_item.subtotal_usd))
    rule = await get_applicable_rule(db, order_item.tenant_id)

    rate_snapshot = getattr(order_item, "commission_rate", None)
    if rate_snapshot is not None:
        rate = Decimal(str(rate_snapshot))
    elif rule is not None:
        rate = Decimal(str(rule.rate))
    else:
        rate = Decimal("0")

    minimum = Decimal(str(rule.min_amount_usd)) if rule is not None else Decimal("0")
    amount = _quantize(max(base * rate, minimum if base > 0 else Decimal("0")))
    return {
        "amount_usd": amount,
        "rate": rate,
        "rule_id": rule.id if rule is not None else None,
    }


async def record_commission(db: AsyncSession, order_item: OrderItem) -> CommissionRecord:
    """Persist a CommissionRecord (status pending) for a delivered item.

    Idempotent: one record per order_item. The event is emitted by the
    caller AFTER commit (see delivery_confirmation_service).
    """
    existing = (await db.execute(
        select(CommissionRecord).where(
            CommissionRecord.order_item_id == order_item.id
        )
    )).scalars().first()
    if existing is not None:
        return existing

    calc = await calculate_commission(db, order_item)
    record = CommissionRecord(
        id=new_uuid(),
        tenant_id=order_item.tenant_id,
        order_id=order_item.order_id,
        order_item_id=order_item.id,
        amount_usd=calc["amount_usd"],
        rate_used=calc["rate"],
        rule_id=calc["rule_id"],
        status="pending",
    )
    db.add(record)
    return record


async def mark_as_invoiced(
    db: AsyncSession, record_ids: list[str], invoice_id: str
) -> int:
    """Attach pending records to an invoice (pending -> invoiced)."""
    now = utcnow()
    count = 0
    rows = (await db.execute(
        select(CommissionRecord).where(
            CommissionRecord.id.in_(record_ids),
            CommissionRecord.status == "pending",
        )
    )).scalars().all()
    for rec in rows:
        rec.status = "invoiced"
        rec.invoice_id = invoice_id
        rec.invoiced_at = now
        count += 1
    return count


async def mark_as_paid(db: AsyncSession, record_ids: list[str]) -> int:
    """Mark invoiced records as paid (invoiced -> paid)."""
    now = utcnow()
    count = 0
    query = select(CommissionRecord).where(CommissionRecord.status == "invoiced")
    if record_ids:
        query = query.where(CommissionRecord.id.in_(record_ids))
    else:
        query = query.where(CommissionRecord.id.is_(None))
    rows = (await db.execute(query)).scalars().all()
    for rec in rows:
        rec.status = "paid"
        rec.paid_at = now
        count += 1
    return count


async def get_pending_commissions(
    db: AsyncSession,
    tenant_id: str,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
) -> list[CommissionRecord]:
    """Pending records of a tenant, optionally bounded by created_at."""
    query = select(CommissionRecord).where(
        CommissionRecord.tenant_id == tenant_id,
        CommissionRecord.status == "pending",
    )
    if period_start is not None:
        query = query.where(CommissionRecord.created_at >= period_start)
    if period_end is not None:
        query = query.where(CommissionRecord.created_at < period_end)
    rows = (await db.execute(query.order_by(CommissionRecord.created_at))).scalars().all()
    return list(rows)


async def emit_recorded_event(record: CommissionRecord) -> None:
    """Emit commission.recorded (call AFTER commit)."""
    await events.emit("commission.recorded", {
        "record_id": record.id,
        "tenant_id": record.tenant_id,
        "order_id": record.order_id,
        "order_item_id": record.order_item_id,
        "amount_usd": str(record.amount_usd),
        "rate_used": str(record.rate_used),
    })
