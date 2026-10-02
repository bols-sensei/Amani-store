"""Séeding config-driven : devises, règles, permissions, templates de rôles.

Idempotent (upsert par clé). Appelé par la migration Alembic et par les tests.
Les seeds JSON sont externalisés dans app/seed_data.py pour rester lisibles.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_rule import BusinessRule
from app.models.currency import Currency
from app.models.exchange_rate import ExchangeRate
from app.models.permission import Permission
from app.models.role_template import RoleTemplate
from app.seed_data import BUSINESS_RULES, CURRENCIES, EXCHANGE_RATES, PERMISSIONS, ROLE_TEMPLATES


async def seed_config(db: AsyncSession) -> dict[str, int]:
    """Insère/met à jour toutes les données de référence. Retourne des compteurs."""
    counts = {"currencies": 0, "exchange_rates": 0, "business_rules": 0,
              "permissions": 0, "role_templates": 0}

    for cur in CURRENCIES:
        existing = (await db.execute(
            select(Currency).where(Currency.code == cur["code"])
        )).scalar_one_or_none()
        if existing is None:
            db.add(Currency(**cur))
            counts["currencies"] += 1

    for rate in EXCHANGE_RATES:
        existing = (await db.execute(
            select(ExchangeRate).where(
                ExchangeRate.from_currency == rate["from_currency"],
                ExchangeRate.to_currency == rate["to_currency"],
            )
        )).scalars().first()
        if existing is None:
            db.add(ExchangeRate(**rate))
            counts["exchange_rates"] += 1

    for rule in BUSINESS_RULES:
        existing = (await db.execute(
            select(BusinessRule).where(BusinessRule.key == rule["key"])
        )).scalar_one_or_none()
        if existing is None:
            db.add(BusinessRule(**rule))
            counts["business_rules"] += 1

    for perm in PERMISSIONS:
        existing = (await db.execute(
            select(Permission).where(Permission.key == perm["key"])
        )).scalar_one_or_none()
        if existing is None:
            db.add(Permission(**perm))
            counts["permissions"] += 1

    for tpl in ROLE_TEMPLATES:
        existing = (await db.execute(
            select(RoleTemplate).where(RoleTemplate.key == tpl["key"])
        )).scalar_one_or_none()
        if existing is None:
            db.add(RoleTemplate(**tpl))
            counts["role_templates"] += 1

    await db.flush()
    return counts
