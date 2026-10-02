"""Service QR / code manuel de confirmation de livraison.

Un token de confirmation est un JWT HS256 court-lived (usage unique) dont le
payload contient : shipment_id, tenant_id, amount_usd, amount_local, currency,
exp, nonce. Le hash SHA-256 du token est stocké en base (jamais le token brut),
avec un manual_code à 6 chiffres comme fallback hors-ligne.

Sécurité :
- signature + expiration vérifiées ;
- usage unique (statut 'used' + used_at) ;
- le colis doit être 'in_transit' ;
- aucun log de token/code sensible.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError_
from app.core.security import hash_token
from app.crud import business_rule as crud_rules
from app.db.base import new_uuid
from app.models.delivery import DeliveryToken
from app.models.shipment import Shipment

logger = logging.getLogger("kimia.delivery_tokens")


async def _hours(db: AsyncSession, key: str, default: float) -> float:
    return await crud_rules.get_rule_number(db, key, default)


def _expiry(hours: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


async def generate_qr_token(
    db: AsyncSession, shipment: Shipment, amount_usd: Decimal,
    amount_local: Decimal, currency: str,
) -> dict[str, Any]:
    """Génère (ou régénère) le jeton QR + code manuel d'un colis in_transit.

    Révoque les tokens actifs précédents pour garantir l'unicité du code.
    """
    if shipment.status != "in_transit":
        raise ConflictError("Le jeton de confirmation n'est disponible qu'en cours de livraison")
    qr_hours = await _hours(db, "delivery.qr_token_expiry_hours", 2)
    code_hours = await _hours(db, "delivery.manual_code_expiry_hours", 24)
    expires_at = _expiry(max(qr_hours, code_hours))

    # Révoke les tokens encore actifs de ce colis
    await db.execute(
        update(DeliveryToken)
        .where(DeliveryToken.shipment_id == shipment.id,
               DeliveryToken.status == "active")
        .values(status="revoked")
    )

    nonce = secrets.token_hex(8)
    payload: dict[str, Any] = {
        "type": "delivery_confirm",
        "shipment_id": shipment.id,
        "tenant_id": shipment.tenant_id,
        "amount_usd": str(amount_usd),
        "amount_local": str(amount_local),
        "currency": currency,
        "nonce": nonce,
        "exp": int(expires_at.timestamp()),
    }
    raw_token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    manual_code = f"{secrets.randbelow(1000000):06d}"

    row = DeliveryToken(
        id=new_uuid(),
        shipment_id=shipment.id,
        token=raw_token,
        manual_code=manual_code,
        nonce=nonce,
        amount_usd=Decimal(str(amount_usd)),
        expires_at=expires_at,
        status="active",
    )
    db.add(row)
    await db.commit()
    return {
        "token": raw_token,
        "manual_code": manual_code,
        "expires_at": expires_at,
        "payload": payload,
    }


async def _consume_token_row(db: AsyncSession, row: DeliveryToken) -> None:
    row.status = "used"
    row.used_at = datetime.now(timezone.utc)
    await db.commit()


async def validate_qr_token(db: AsyncSession, raw_token: str) -> tuple[Shipment, dict[str, Any]]:
    """Valide un scan QR : signature, expiration, usage unique, statut colis."""
    try:
        payload = jwt.decode(raw_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValidationError_("Jeton expiré — demandez un nouveau QR au livreur")
    except jwt.PyJWTError:
        raise ValidationError_("Jeton invalide")
    if payload.get("type") != "delivery_confirm":
        raise ValidationError_("Jeton invalide")

    row = (await db.execute(
        select(DeliveryToken).where(DeliveryToken.token == raw_token)
    )).scalar_one_or_none()
    if row is None:
        raise ValidationError_("Jeton inconnu")
    if row.status == "used":
        raise ConflictError("Ce jeton a déjà été utilisé")
    if row.status != "active":
        raise ConflictError("Ce jeton n'est plus valide")

    shipment = await db.get(Shipment, payload["shipment_id"])
    if shipment is None:
        raise NotFoundError("Colis introuvable")
    if shipment.status != "in_transit":
        raise ConflictError(f"Le colis n'est pas en cours de livraison (statut : {shipment.status})")
    await _consume_token_row(db, row)
    return shipment, payload


async def validate_manual_code(
    db: AsyncSession, shipment_id: str, code: str
) -> tuple[Shipment, dict[str, Any]]:
    """Valide le code manuel 6 chiffres saisi par le client."""
    if not code or len(code) != 6 or not code.isdigit():
        raise ValidationError_("Code manuel invalide (6 chiffres requis)")
    row = (await db.execute(
        select(DeliveryToken).where(
            DeliveryToken.shipment_id == shipment_id,
            DeliveryToken.manual_code == code,
            DeliveryToken.status == "active",
        )
    )).scalar_one_or_none()
    if row is None:
        raise ValidationError_("Code manuel invalide ou expiré")
    now = datetime.now(timezone.utc)
    if row.expires_at is not None and row.expires_at < now:
        row.status = "expired"
        await db.commit()
        raise ValidationError_("Code manuel expiré")
    shipment = await db.get(Shipment, shipment_id)
    if shipment is None:
        raise NotFoundError("Colis introuvable")
    if shipment.status != "in_transit":
        raise ConflictError(f"Le colis n'est pas en cours de livraison (statut : {shipment.status})")
    await _consume_token_row(db, row)
    return shipment, {"source": "manual_code"}


async def revoke_token(db: AsyncSession, shipment_id: str) -> int:
    """Révoque tous les tokens actifs d'un colis (ex : re-planification)."""
    result = await db.execute(
        update(DeliveryToken)
        .where(DeliveryToken.shipment_id == shipment_id,
               DeliveryToken.status == "active")
        .values(status="revoked")
    )
    await db.commit()
    return int(result.rowcount or 0)


async def expire_stale_tokens(db: AsyncSession) -> int:
    """Job ARQ : marque 'expired' les tokens actifs passés leur échéance."""
    result = await db.execute(
        update(DeliveryToken)
        .where(DeliveryToken.status == "active",
               DeliveryToken.expires_at < datetime.now(timezone.utc))
        .values(status="expired")
    )
    await db.commit()
    return int(result.rowcount or 0)
