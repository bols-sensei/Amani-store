"""Génération des documents : reçus de livraison + factures de commande.

Rendu HTML via Jinja2 (app/web/templates/documents/) puis conversion PDF via
WeasyPrint si disponible ; sinon un PDF minimal est produit par un writer
maison (valide, testable sans dépendances système). Chaque document porte un
QR de vérification pointant vers /api/v1/public/verify/{number}.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.crud import business_rule as crud_rules
from app.db.base import new_uuid
from app.models.document import Document
from app.models.order import Order
from app.models.shipment import Shipment
from app.models.tenant import Tenant
from app.models.user import User
from app.services import reference_generator
from app.services.document_storage import build_document_path, generate_qr_code, get_storage

logger = logging.getLogger("kimia.receipts")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "web" / "templates" / "documents"


def _render_html(template_name: str, context: dict[str, Any]) -> str:
    """Rend un template Jinja2 du dossier documents/."""
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined, autoescape=True,
    )
    return env.get_template(template_name).render(**context)


def _pdf_minimal(title: str, lines: list[str]) -> bytes:
    """PDF 1 page très simple (writer maison) — fallback sans WeasyPrint."""
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        pass
    content = ["BT /F1 16 Tf 50 780 Td (" + title.replace("(", "[").replace(")", "]") + ") Tj ET"]
    y = 750
    for line in lines:
        safe = line.replace("(", "[").replace(")", "]").replace("\u2013", "-").replace("\u2019", "'")
        content.append(f"BT /F1 10 Tf 50 {y} Td ({safe}) Tj ET")
        y -= 16
    stream = "\n".join(content).encode("latin-1", "replace")
    objs: list[bytes] = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
                b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>")
    objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    return bytes(out)


def _to_pdf(html: str, title: str, plain_lines: list[str]) -> bytes:
    """HTML → PDF via WeasyPrint si dispo, sinon writer minimal."""
    try:
        from weasyprint import HTML  # type: ignore[import-untyped]

        return HTML(string=html).write_pdf()
    except Exception:  # ImportError OU absence libpango en environnement réduit
        return _pdf_minimal(title, plain_lines)


async def _retention_years(db: AsyncSession) -> int:
    return int(await crud_rules.get_rule_number(db, "delivery.receipt_retention_years", 5))


async def generate_receipt(db: AsyncSession, shipment_id: str) -> Document:
    """Reçu de livraison d'un colis livré — numéro REC-…, QR de vérification."""
    shipment = (await db.execute(
        select(Shipment).where(Shipment.id == shipment_id).options(
            selectinload(Shipment.items), selectinload(Shipment.order)
        )
    )).scalar_one_or_none()
    if shipment is None:
        raise NotFoundError("Colis introuvable")
    if shipment.status != "delivered":
        raise ConflictError("Un reçu n'est généré que pour un colis livré")
    if shipment.receipt_number:
        existing = (await db.execute(
            select(Document).where(Document.number == shipment.receipt_number)
        )).scalar_one_or_none()
        if existing is not None:
            return existing

    order = shipment.order
    tenant = await db.get(Tenant, shipment.tenant_id)
    customer = await db.get(User, order.customer_id)
    courier = await db.get(User, shipment.courier_id) if shipment.courier_id else None

    currency_code = order.currency_at_creation or "USD"
    total_usd = sum((Decimal(str(i.subtotal_usd)) for i in shipment.items), Decimal("0"))
    from app.services import currency_service

    try:
        total_display = await currency_service.format_for_display(db, total_usd, currency_code)
    except ValueError:
        total_display = f"${total_usd.quantize(Decimal('0.01'))}"

    number = await reference_generator.generate_receipt_number(db, shipment.reference)
    verify_url = f"/api/v1/public/verify/{number}"
    qr = generate_qr_code(verify_url)

    ctx: dict[str, Any] = {
        "title": f"Reçu {number}",
        "doc_type_label": "Reçu de livraison",
        "number": number,
        "generated_at": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M"),
        "legal_note": "Le vendeur encaisse le paiement à la livraison (COD). Kimia ne manipule aucun fonds.",
        "qr_data_url": qr,
        "vendor": {"name": tenant.name if tenant else "—", "slug": tenant.slug if tenant else ""},
        "customer": {"name": (customer.full_name or customer.email) if customer else "—",
                     "phone": customer.phone if customer else None,
                     "email": customer.email if customer else None},
        "courier": {"name": courier.full_name if courier else None, "vehicle": ""},
        "shipment": {"reference": shipment.reference,
                     "confirmation_method": shipment.confirmation_method or "—"},
        "delivered_at": shipment.delivered_at.strftime("%d/%m/%Y %H:%M") if shipment.delivered_at else "—",
        "items": [
            {"name": i.product_name, "quantity": i.quantity,
             "unit_price": f"${Decimal(str(i.unit_price_usd)).quantize(Decimal('0.01'))}",
             "subtotal": f"${Decimal(str(i.subtotal_usd)).quantize(Decimal('0.01'))}"}
            for i in shipment.items
        ],
        "subtotal_display": total_display,
        "total_display": total_display,
    }
    html = _render_html("receipt.html", ctx)
    plain = [f"Colis {shipment.reference} — Commande {order.reference}",
             f"Vendeur: {ctx['vendor']['name']}", f"Client: {ctx['customer']['name']}"]
    plain += [f"- {it['name']} x{it['quantity']} : {it['subtotal']}" for it in ctx["items"]]
    plain += [f"Total COD: {total_display}", f"Verification: {verify_url}"]
    pdf = _to_pdf(html, f"Recu {number}", plain)

    now = datetime.now(timezone.utc)
    subpath = build_document_path("receipts", f"{number}.pdf", now)
    url = get_storage().save(pdf, subpath)
    retention = await _retention_years(db)

    doc = Document(
        id=new_uuid(), type="receipt", number=number,
        reference_type="shipment", reference_id=shipment.id,
        tenant_id=shipment.tenant_id, owner_type="customer", owner_id=order.customer_id,
        pdf_url=url, public_url=f"/api/v1/public/receipts/{number}",
        qr_code_url=verify_url, size_bytes=len(pdf), generated_at=now,
        expires_at=now + timedelta(days=365 * retention),
    )
    db.add(doc)
    shipment.receipt_number = number
    shipment.receipt_pdf_url = url
    shipment.receipt_generated_at = now
    await db.commit()
    return doc


async def generate_invoice(db: AsyncSession, order_id: str) -> Document:
    """Facture SaaS d'une commande livrée (tous colis delivered). FAC-…"""
    order = (await db.execute(
        select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    )).scalar_one_or_none()
    if order is None:
        raise NotFoundError("Commande introuvable")
    if order.status != "delivered":
        raise ConflictError("La facture est émise une fois la commande entièrement livrée")
    existing = (await db.execute(
        select(Document).where(
            Document.reference_type == "order",
            Document.reference_id == order.id,
            Document.type == "invoice",
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    tenant = await db.get(Tenant, order.tenant_id)
    customer = await db.get(User, order.customer_id)
    number = await reference_generator.generate_invoice_number(db, order.reference)
    verify_url = f"/api/v1/public/verify/{number}"
    qr = generate_qr_code(verify_url)
    addr = order.delivery_address or {}
    address_lines = [str(v) for v in [addr.get("name"), addr.get("phone"), addr.get("commune"),
                                      addr.get("city"), addr.get("details")] if v]

    ctx: dict[str, Any] = {
        "title": f"Facture {number}",
        "doc_type_label": "Facture",
        "number": number,
        "generated_at": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M"),
        "legal_note": f"Vendeur : {tenant.name if tenant else '—'} — Paiement cash à la livraison.",
        "qr_data_url": qr,
        "customer": {"name": (customer.full_name or customer.email) if customer else "—",
                     "email": customer.email if customer else None,
                     "phone": customer.phone if customer else None},
        "order": {"reference": order.reference, "address_lines": address_lines},
        "created_at": order.created_at.strftime("%d/%m/%Y"),
        "items": [
            {"name": i.product_name, "quantity": i.quantity,
             "unit_price_usd": f"{Decimal(str(i.unit_price_usd)).quantize(Decimal('0.01'))}",
             "subtotal_usd": f"{Decimal(str(i.subtotal_usd)).quantize(Decimal('0.01'))}"}
            for i in order.items
        ],
        "subtotal_usd": f"{Decimal(str(order.subtotal_usd)).quantize(Decimal('0.01'))}",
        "delivery_fee_usd": f"{Decimal(str(order.delivery_fee_usd)).quantize(Decimal('0.01'))}",
        "total_usd": f"{Decimal(str(order.total_usd)).quantize(Decimal('0.01'))}",
    }
    html = _render_html("invoice.html", ctx)
    plain = [f"Commande {order.reference}", f"Client: {ctx['customer']['name']}"]
    plain += [f"- {it['name']} x{it['quantity']} : {it['subtotal_usd']} USD" for it in ctx["items"]]
    plain += [f"Total: {ctx['total_usd']} USD", f"Verification: {verify_url}"]
    pdf = _to_pdf(html, f"Facture {number}", plain)

    now = datetime.now(timezone.utc)
    subpath = build_document_path("invoices", f"{number}.pdf", now)
    url = get_storage().save(pdf, subpath)
    retention = await _retention_years(db)

    doc = Document(
        id=new_uuid(), type="invoice", number=number,
        reference_type="order", reference_id=order.id,
        tenant_id=order.tenant_id, owner_type="vendor", owner_id=order.tenant_id,
        pdf_url=url, public_url=f"/api/v1/public/invoices/{number}",
        qr_code_url=verify_url, size_bytes=len(pdf), generated_at=now,
        expires_at=now + timedelta(days=365 * retention),
    )
    db.add(doc)
    await db.commit()
    return doc


async def get_public_url(db: AsyncSession, document_id: str) -> str:
    """URL publique partageable d'un document (404 si expirée)."""
    doc = await db.get(Document, document_id)
    if doc is None:
        raise NotFoundError("Document introuvable")
    if doc.expires_at is not None and doc.expires_at < datetime.now(timezone.utc):
        raise NotFoundError("Ce document a expiré")
    return doc.public_url or doc.pdf_url


async def find_by_number(db: AsyncSession, number: str) -> Optional[Document]:
    """Retourne le document correspondant à un numéro REC/FAC (vérification publique)."""
    return (await db.execute(
        select(Document).where(Document.number == number)
    )).scalar_one_or_none()
