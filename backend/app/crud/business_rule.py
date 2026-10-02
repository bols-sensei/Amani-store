"""CRUD BusinessRule — lecture typée des règles métier (config-driven)."""

import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_rule import BusinessRule


def coerce(rule: BusinessRule) -> Any:
    """Convertit la valeur texte selon le type déclaré en base."""
    if rule.type == "number":
        try:
            return int(rule.value)
        except ValueError:
            return float(rule.value)
    if rule.type == "boolean":
        return rule.value.lower() in ("1", "true", "yes")
    if rule.type == "json":
        return json.loads(rule.value)
    return rule.value


async def get_rule(db: AsyncSession, key: str, default: Any = None) -> Any:
    """Retourne la valeur typée d'une règle, ou `default` si absente."""
    result = await db.execute(select(BusinessRule).where(BusinessRule.key == key))
    rule = result.scalar_one_or_none()
    return coerce(rule) if rule else default


async def get_rule_number(db: AsyncSession, key: str, default: float = 0) -> float:
    """Retourne une règle numérique (float), ou `default` si absente/non numérique."""
    val = await get_rule(db, key, None)
    if isinstance(val, (int, float)):
        return float(val)
    return float(default)


async def set_rule(db: AsyncSession, key: str, value: str, **fields) -> BusinessRule:
    rule = (await db.execute(select(BusinessRule).where(BusinessRule.key == key))).scalar_one_or_none()
    if rule is None:
        rule = BusinessRule(key=key, value=value, **fields)
        db.add(rule)
    else:
        rule.value = value
        for k, v in fields.items():
            setattr(rule, k, v)
    await db.flush()
    return rule
