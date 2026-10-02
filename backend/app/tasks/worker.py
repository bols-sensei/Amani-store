"""ARQ worker — tâches planifiées du SaaS Kimia.

Conventions :
- chaque job ouvre SA propre session AsyncSessionLocal ;
- les règles métier sont lues depuis business_rules (config-driven) ;
- les événements sont émis APRÈS commit, via le bus existant.

Jobs prompt 3 : auto_cancel_pending_orders, cleanup_expired_carts.
Jobs prompt 4 : expire_qr_tokens, send_delivery_reminders,
                auto_confirm_delivered, cleanup_expired_documents.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.db import session as db_session

logger = logging.getLogger("kimia.worker")


def _session():
    """Nouvelle session async (le ctx ARQ ne porte pas de session FastAPI)."""
    return db_session.get_session_factory()()


async def startup(ctx: dict) -> None:
    """Init worker ARQ."""
    logger.info("worker started (env=%s)", settings.APP_ENV)


async def shutdown(ctx: dict) -> None:
    """Cleanup worker ARQ."""
    logger.info("worker stopped")


# ---------------------------------------------------------------------------
# Prompt 3 — commandes & panier
# ---------------------------------------------------------------------------

async def auto_cancel_pending_orders(ctx: dict) -> int:
    """Annule les commandes pending au-delà de order.auto_cancel_hours.

    Libère le reserved_stock et émet "order.cancelled" (géré dans le service).
    """
    from app.services import order_service

    async with _session() as db:
        count = await order_service.auto_cancel_expired_orders(db)
        await db.commit()
    if count:
        logger.info("auto-cancel: %d commande(s) annulée(s)", count)
    return count


async def cleanup_expired_carts(ctx: dict) -> int:
    """Supprime les paniers inactifs > order.cart_expiry_days (cron quotidien)."""
    from app.services import cart_service

    async with _session() as db:
        count = await cart_service.cleanup_expired_carts(db)
        await db.commit()
    if count:
        logger.info("cart cleanup: %d panier(s) expiré(s)", count)
    return count


# ---------------------------------------------------------------------------
# Prompt 4 — livraison / QR / documents
# ---------------------------------------------------------------------------

async def expire_qr_tokens(ctx: dict) -> int:
    """Marque les tokens QR échus comme 'expired' (toutes les heures)."""
    from app.services import delivery_token_service

    async with _session() as db:
        count = await delivery_token_service.expire_stale_tokens(db)
        await db.commit()
    if count:
        logger.info("qr tokens: %d expiré(s)", count)
    return count


async def send_delivery_reminders(ctx: dict) -> int:
    """Rappelle le client de confirmer (stub SMS — branché au prompt 6).

    Cible : colis delivered sans enregistrement dans delivery_confirmations
    depuis plus de delivery.confirm_reminder_hours. Le stub émet un
    événement ; aucun envoi réel n'est fait ici.
    """
    from sqlalchemy import select

    from app.core.events import events
    from app.crud import business_rule as crud_rules
    from app.db.base import utcnow
    from app.models.delivery import DeliveryConfirmation
    from app.models.shipment import Shipment

    async with _session() as db:
        hours = await crud_rules.get_rule_number(
            db, "delivery.confirm_reminder_hours", 24
        )
        cutoff = utcnow() - timedelta(hours=float(hours))
        confirmed_ids = select(DeliveryConfirmation.shipment_id)
        rows = (
            await db.execute(
                select(Shipment).where(
                    Shipment.status == "delivered",
                    Shipment.delivered_at.is_not(None),
                    Shipment.delivered_at < cutoff,
                    Shipment.id.not_in(confirmed_ids),
                )
            )
        ).scalars().all()
        for shp in rows:
            await events.emit("delivery.confirmation_reminder", shp)
    if rows:
        logger.info("reminders: %d rappel(s) à envoyer (stub)", len(rows))
    return len(rows)


async def auto_confirm_delivered(ctx: dict) -> int:
    """Alerte le vendeur sur les colis in_transit trop vieux.

    Politique : AUCUNE confirmation automatique (principe P1/P3 — seul le
    client confirme ; le vendeur peut confirmer manuellement après le délai).
    Ce job émet uniquement un événement d'alerte.
    """
    from sqlalchemy import select

    from app.core.events import events
    from app.crud import business_rule as crud_rules
    from app.db.base import utcnow
    from app.models.shipment import Shipment

    async with _session() as db:
        hours = await crud_rules.get_rule_number(
            db, "delivery.auto_confirm_after_hours", 48
        )
        cutoff = utcnow() - timedelta(hours=float(hours))
        rows = (
            await db.execute(
                select(Shipment).where(
                    Shipment.status == "in_transit",
                    Shipment.started_at.is_not(None),
                    Shipment.started_at < cutoff,
                )
            )
        ).scalars().all()
        for shp in rows:
            await events.emit("shipment.stale_in_transit", shp)
    if rows:
        logger.info("stale shipments: %d alerte(s) vendeur", len(rows))
    return len(rows)


async def cleanup_expired_documents(ctx: dict) -> int:
    """Révoque les URL publiques des documents dont l'accès a expiré.

    On ne supprime pas le PDF (obligation légale de rétention —
    delivery.receipt_retention_years), on vide seulement public_url.
    """
    from sqlalchemy import select, update

    from app.db.base import utcnow
    from app.models.document import Document

    async with _session() as db:
        ids = (
            await db.execute(
                select(Document.id).where(
                    Document.expires_at.is_not(None),
                    Document.expires_at < utcnow(),
                    Document.public_url.is_not(None),
                )
            )
        ).scalars().all()
        if ids:
            await db.execute(
                update(Document).where(Document.id.in_(ids)).values(public_url=None)
            )
            await db.commit()
    if ids:
        logger.info("documents: %d URL publique(s) révoquée(s)", len(ids))
    return len(ids)


class WorkerSettings:
    """Configuration ARQ (Redis)."""

    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown
    functions = [
        auto_cancel_pending_orders,
        cleanup_expired_carts,
        expire_qr_tokens,
        send_delivery_reminders,
        auto_confirm_delivered,
        cleanup_expired_documents,
    ]
    _every_hour = set(range(24))
    cron_jobs = [
        # toutes les heures
        cron(auto_cancel_pending_orders,
             hour=_every_hour, minute={5}),
        cron(expire_qr_tokens, minute={0}),
        # toutes les 6h
        cron(send_delivery_reminders,
             hour={0, 6, 12, 18}, minute={15}),
        # quotidien
        cron(cleanup_expired_carts, hour={3}, minute={0}),
        cron(auto_confirm_delivered, hour={4}, minute={0}),
        cron(cleanup_expired_documents, hour={5}, minute={0}),
    ]
