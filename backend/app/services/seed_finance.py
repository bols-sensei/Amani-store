"""Seed finance reference data (prompt 5).

Idempotent — safe to call from migration 0010 and from the test seed
pipeline. Inserts:
- 3 plans (free / pro / business) with prices, commission rates and limits;
- 1 global commission rule (tenant_id NULL, products, 5%, min $0.50);
- billing business_rules (only if key missing).

User-facing labels are in FRENCH per product language rules.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_rule import BusinessRule
from app.models.finance import CommissionRule, Plan

PLANS: list[dict[str, Any]] = [
    {
        "key": "free", "name": "FREE", "price_usd_monthly": Decimal("0"),
        "commission_rate": Decimal("0.05"), "commission_min_usd": Decimal("0.50"),
        "limits": {"max_products": 20, "max_staff": 0, "max_couriers": 0},
        "features": {"campaigns": False, "api_access": False},
        "display_order": 0,
    },
    {
        "key": "pro", "name": "PRO", "price_usd_monthly": Decimal("10"),
        "commission_rate": Decimal("0.02"), "commission_min_usd": Decimal("0.30"),
        "limits": {"max_products": 500, "max_staff": 3, "max_couriers": 3},
        "features": {"campaigns": False, "api_access": False},
        "display_order": 1,
    },
    {
        "key": "business", "name": "BUSINESS", "price_usd_monthly": Decimal("30"),
        "commission_rate": Decimal("0.01"), "commission_min_usd": Decimal("0.20"),
        "limits": {"max_products": -1, "max_staff": 15, "max_couriers": -1},
        "features": {"campaigns": True, "api_access": True},
        "display_order": 2,
    },
]

BILLING_RULES: list[dict[str, str]] = [
    {"key": "billing.invoice_generation_day", "value": "1"},
    {"key": "billing.payment_due_days", "value": "7"},
    {"key": "billing.reminder_days", "value": "[1, 7, 15]"},
    {"key": "billing.grace_period_days", "value": "15"},
    {"key": "billing.suspend_after_days", "value": "30"},
    {"key": "billing.auto_suspend", "value": "true"},
    {"key": "billing.trial_days", "value": "14"},
]


async def seed_finance(db: AsyncSession) -> dict[str, int]:
    """Insert plans + global commission rule + billing rules (idempotent)."""
    counts = {"plans": 0, "commission_rules": 0, "business_rules": 0}

    for plan in PLANS:
        existing = (await db.execute(
            select(Plan).where(Plan.key == plan["key"])
        )).scalar_one_or_none()
        if existing is None:
            db.add(Plan(**plan))
            counts["plans"] += 1

    global_rule_exists = (await db.execute(
        select(CommissionRule).where(
            CommissionRule.tenant_id.is_(None),
            CommissionRule.category_id.is_(None),
            CommissionRule.applies_to == "products",
        )
    )).scalars().first()
    if global_rule_exists is None:
        db.add(CommissionRule(
            tenant_id=None, category_id=None, applies_to="products",
            rate=Decimal("0.05"), min_amount_usd=Decimal("0.50"),
            priority=1, is_active=True,
            notes="Règle de commission globale par défaut (tous vendeurs)",
        ))
        counts["commission_rules"] += 1

    for rule in BILLING_RULES:
        existing = (await db.execute(
            select(BusinessRule).where(BusinessRule.key == rule["key"])
        )).scalar_one_or_none()
        if existing is None:
            db.add(BusinessRule(
                key=rule["key"], value=rule["value"],
                type="json" if rule["value"].startswith("[") else
                     ("boolean" if rule["value"] in ("true", "false") else "number"),
                category="billing",
                description="Règle de facturation SaaS",
                editable_by="superadmin",
            ))
            counts["business_rules"] += 1

    await db.flush()
    return counts
