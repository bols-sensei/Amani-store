"""SaaS invoice PDF service (prompt 5).

Renders saas_invoice.html through the same pipeline as receipt_service
(WeasyPrint when available, minimal PDF writer fallback), stores the file on
the local document storage and registers a Document row (type="invoice",
reference_type="saas_invoice").
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.base import new_uuid, utcnow
from app.models.document import Document
from app.models.finance import SaasInvoice
from app.models.tenant import Tenant
from app.services import receipt_service
from app.services.document_storage import build_document_path, get_storage

logger = logging.getLogger("kimia.invoice_pdf")


async def generate_saas_invoice_pdf(db: AsyncSession, invoice_id: str) -> Document:
    """Generate (or reuse) the PDF of a SaaS invoice; link it back."""
    invoice = await db.get(SaasInvoice, invoice_id)
    if invoice is None:
        raise NotFoundError("Facture introuvable")

    existing = (await db.execute(
        select(Document).where(
            Document.reference_type == "saas_invoice",
            Document.reference_id == invoice.id,
        )
    )).scalars().first()
    if existing is not None:
        return existing

    tenant = await db.get(Tenant, invoice.tenant_id)
    items = invoice.items or []

    def money(value: Decimal | float | str) -> str:
        return f"${Decimal(str(value)).quantize(Decimal('0.01'))}"

    ctx: dict[str, Any] = {
        "title": f"Facture Kimia {invoice.number}",
        "doc_type_label": "Facture d'abonnement Kimia",
        "number": invoice.number,
        "generated_at": utcnow().strftime("%d/%m/%Y %H:%M"),
        "legal_note": (
            "Kimia ne collecte jamais l'argent des ventes : les commissions "
            "correspondent à une dette d'abonnement facturée au vendeur."
        ),
        "qr_data_url": None,
        "vendor": {"name": tenant.name if tenant else "—",
                   "email": getattr(tenant, "billing_email", None)},
        "period": f"{invoice.period_start:%d/%m/%Y} — {invoice.period_end:%d/%m/%Y}",
        "issued_at": invoice.issued_at.strftime("%d/%m/%Y") if invoice.issued_at else "—",
        "due_date": invoice.due_date.strftime("%d/%m/%Y"),
        "status_label": {
            "draft": "Brouillon", "sent": "Émise", "paid": "Payée",
            "overdue": "En retard", "cancelled": "Annulée",
        }.get(invoice.status, invoice.status),
        "items": [
            {"description": it.description, "amount": money(it.amount_usd)}
            for it in items
        ],
        "subscription_display": money(invoice.subscription_amount_usd),
        "commission_display": money(invoice.commission_amount_usd),
        "total_display": money(invoice.total_usd),
    }

    html = receipt_service._render_html("saas_invoice.html", ctx)
    plain = [f"Facture {invoice.number}", f"Vendeur: {ctx['vendor']['name']}",
             f"Période: {ctx['period']}", f"Échéance: {ctx['due_date']}"]
    plain += [f"- {it['description']} : {it['amount']}" for it in ctx["items"]]
    plain.append(f"Total: {ctx['total_display']}")
    pdf = receipt_service._to_pdf(html, f"Facture {invoice.number}", plain)

    now = datetime.now(timezone.utc)
    subpath = build_document_path("saas_invoices", f"{invoice.number}.pdf", now)
    url = get_storage().save(pdf, subpath)

    doc = Document(
        id=new_uuid(), type="invoice", number=invoice.number,
        reference_type="saas_invoice", reference_id=invoice.id,
        tenant_id=invoice.tenant_id, owner_type="tenant", owner_id=invoice.tenant_id,
        pdf_url=url, public_url=f"/api/v1/public/invoices/{invoice.number}",
        size_bytes=len(pdf), generated_at=now, expires_at=None,
    )
    db.add(doc)
    invoice.pdf_url = url
    invoice.public_url = doc.public_url
    await db.flush()
    return doc
