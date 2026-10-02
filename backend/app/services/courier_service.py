"""Service PROFIL LIVREUR — création (limite par plan), profil, stats.

Limites de livreurs par plan via business_rules courier.plan_min.{plan} :
- free     → 0    (aucun livreur)
- pro      → 3
- business → -1   (illimité)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.crud import business_rule as crud_rules
from app.db.base import new_uuid
from app.models.document import CourierProfile
from app.models.shipment import Shipment
from app.models.user import User

VEHICLE_TYPES = {"moto", "velo", "voiture", "pied", "autre"}


async def courier_limit_for_plan(db: AsyncSession, plan_name: str) -> int:
    """Nombre max de livreurs pour un plan (-1 = illimité)."""
    return int(await crud_rules.get_rule_number(db, f"courier.plan_min.{plan_name}", 0))


async def count_couriers(db: AsyncSession, tenant_id: str) -> int:
    return int((await db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == tenant_id, User.role == "courier", User.is_active.is_(True)
        )
    )).scalar_one() or 0)


async def create_courier(
    db: AsyncSession, *, tenant_id: str, plan_name: str,
    email: str, phone: str, password: str,
    first_name: Optional[str] = None, last_name: Optional[str] = None,
    vehicle_type: str = "moto", vehicle_plate: Optional[str] = None,
    phone_secondary: Optional[str] = None,
) -> tuple[User, CourierProfile]:
    """Crée user(role=courier) + CourierProfile, après contrôle de limite plan."""
    if vehicle_type not in VEHICLE_TYPES:
        raise ConflictError("Type de véhicule invalide")
    limit = await courier_limit_for_plan(db, plan_name)
    if limit >= 0 and await count_couriers(db, tenant_id) >= limit:
        raise PermissionDeniedError(
            f"Limite de {limit} livreur(s) atteinte pour le plan '{plan_name}'. "
            "Passez à un plan supérieur."
        )

    existing = (await db.execute(
        select(User).where((User.email == email) | (User.phone == phone))
    )).scalars().first()
    if existing is not None:
        raise ConflictError("Cet email ou ce numéro est déjà utilisé")

    from app.core.security import hash_password

    courier = User(
        id=new_uuid(), email=email.lower(), phone=phone,
        hashed_password=hash_password(password), role="courier",
        tenant_id=tenant_id, is_active=True, is_verified=True,
        first_name=first_name, last_name=last_name,
    )
    db.add(courier)
    profile = CourierProfile(
        id=new_uuid(), user_id=courier.id, tenant_id=tenant_id,
        vehicle_type=vehicle_type, vehicle_plate=vehicle_plate,
        phone_secondary=phone_secondary, is_available=True,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(courier)
    await db.refresh(profile)
    return courier, profile


async def get_profile(db: AsyncSession, courier_user_id: str) -> CourierProfile:
    profile = (await db.execute(
        select(CourierProfile).where(CourierProfile.user_id == courier_user_id)
    )).scalar_one_or_none()
    if profile is None:
        raise NotFoundError("Profil livreur introuvable")
    return profile


async def update_profile(db: AsyncSession, profile: CourierProfile, **fields: Any) -> CourierProfile:
    for key, value in fields.items():
        if value is None:
            continue
        if key == "vehicle_type" and value not in VEHICLE_TYPES:
            raise ConflictError("Type de véhicule invalide")
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return profile


async def courier_stats(db: AsyncSession, courier_id: str) -> dict[str, Any]:
    """Compteurs de livraison du jour / de la semaine / en cours."""
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=now.weekday())

    async def _count(since: Optional[datetime], statuses: tuple[str, ...]) -> int:
        q = select(func.count(Shipment.id)).where(
            Shipment.courier_id == courier_id, Shipment.status.in_(statuses)
        )
        if since is not None:
            q = q.where(Shipment.delivered_at >= since)
        return int((await db.execute(q)).scalar_one() or 0)

    return {
        "deliveries_today": await _count(day_start, ("delivered",)),
        "deliveries_this_week": await _count(week_start, ("delivered",)),
        "current_shipments_count": await _count(None, ("in_transit",)),
        "total_delivered": await _count(None, ("delivered",)),
        "total_failed": await _count(None, ("failed",)),
    }
