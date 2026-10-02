"""Générateur de références humaines uniques.

Formats :
  - commande : ORD-{YYYY}-{NNNNN}
  - colis    : SHP-{YYYY}-{NNNNN}-{S}   (S = numéro de colis dans la commande)
  - reçu     : REC-{YYYY}-{NNNNN}-{S}
  - facture  : FAC-{YYYY}-{NNNNN}

Sécurité multi-instance :
  1. incrément ATOMIQUE Redis (INCR, TTL 400 jours) si disponible ;
  2. sinon compteur DB séquentiel (table reference_counters) avec
     UPSERT ... RETURNING sur PostgreSQL ;
  3. repli SQLite/tests : SELECT+UPDATE dans la transaction appelante.

Le même `db` (transaction en cours) est réutilisé — jamais de session
interne cachée qui casserait l'atomicité.
"""

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


class ReferenceError(RuntimeError):
    """Impossible de générer une référence unique."""


async def _next_redis(prefix: str, year: int) -> int | None:
    """Incrément atomique via Redis ; None si Redis indisponible."""
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=1,
                              socket_timeout=1, decode_responses=True)
        try:
            key = f"kimia:ref:{prefix}:{year}"
            n = await r.incr(key)
            if int(n) == 1:
                await r.expire(key, 40_000_000)  # ~460 jours
            return int(n)
        finally:
            await r.aclose()
    except Exception:  # noqa: BLE001 — Redis optionnel (dev/tests)
        return None


async def next_sequence(db: AsyncSession, prefix: str, year: int) -> int:
    """Retourne le prochain compteur pour (prefix, année)."""
    n = await _next_redis(prefix, year)
    if n is not None:
        return n

    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        row = (await db.execute(
            text(
                "INSERT INTO reference_counters (prefix, year, value) "
                "VALUES (:p, :y, 1) "
                "ON CONFLICT (prefix, year) DO UPDATE SET value = reference_counters.value + 1 "
                "RETURNING value"
            ),
            {"p": prefix, "y": year},
        )).scalar_one()
        return int(row)

    # Repli SQLite (tests) : verrou applicatif léger dans la transaction.
    value = (await db.execute(
        text("SELECT value FROM reference_counters WHERE prefix=:p AND year=:y"),
        {"p": prefix, "y": year},
    )).scalar_one_or_none()
    nxt = (value or 0) + 1
    if value is None:
        await db.execute(
            text("INSERT INTO reference_counters (prefix, year, value) VALUES (:p, :y, 1)"),
            {"p": prefix, "y": year},
        )
    else:
        await db.execute(
            text("UPDATE reference_counters SET value=:v WHERE prefix=:p AND year=:y"),
            {"v": nxt, "p": prefix, "y": year},
        )
    return nxt


async def generate_order_reference(db: AsyncSession) -> str:
    """ORD-2026-00142"""
    year = datetime.now(timezone.utc).year
    n = await next_sequence(db, "ORD", year)
    return f"ORD-{year}-{n:05d}"


async def generate_shipment_reference(db: AsyncSession, order_reference: str, seq: int) -> str:
    """SHP-2026-00142-1 (reprrend le numéro de la commande parente)."""
    year = datetime.now(timezone.utc).year
    base = order_reference.replace("ORD-", "SHP-")
    return f"{base}-{seq}"


async def generate_receipt_number(db: AsyncSession, shipment_reference: str) -> str:
    """REC-2026-00142-1"""
    return shipment_reference.replace("SHP-", "REC-")


async def generate_invoice_number(db: AsyncSession, order_reference: str) -> str:
    """FAC-2026-00142"""
    return order_reference.replace("ORD-", "FAC-")
