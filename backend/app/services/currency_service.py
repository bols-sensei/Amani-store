"""Service devise — conversion USD ↔ affichage + formatage local.

Source de vérité : tables `currencies` (formats) et `exchange_rates`
(taux effectifs). Aucune valeur codée en dur. Cache TTL 5 min en mémoire
(process-local ; Redis sera branché au prompt notifications/analytics).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import Currency
from app.models.exchange_rate import ExchangeRate

_CACHE_TTL_SECONDS = 300
_rate_cache: dict[str, tuple[float, Decimal]] = {}


def _cache_key(from_code: str, to_code: str) -> str:
    return f"{from_code}->{to_code}"


async def get_current_rate(
    db: AsyncSession, from_code: str, to_code: str
) -> Decimal:
    """Dernier taux effectif (<= now) entre deux devises. 1 si même devise."""
    if from_code == to_code:
        return Decimal("1")
    key = _cache_key(from_code, to_code)
    hit = _rate_cache.get(key)
    if hit is not None and (datetime.now(timezone.utc) - datetime.fromtimestamp(hit[0], timezone.utc)).total_seconds() < _CACHE_TTL_SECONDS:
        return Decimal(str(hit[1]))
    now = datetime.now(timezone.utc)
    row = (await db.execute(
        select(ExchangeRate.rate)
        .where(
            ExchangeRate.from_currency == from_code,
            ExchangeRate.to_currency == to_code,
            ExchangeRate.effective_at <= now,
        )
        .order_by(ExchangeRate.effective_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        raise ValueError(f"Aucun taux de change {from_code}→{to_code} configuré")
    rate = Decimal(str(row))
    _rate_cache[key] = (datetime.now(timezone.utc).timestamp(), rate)
    return rate


async def get_rate_at(
    db: AsyncSession, from_code: str, to_code: str, when: datetime
) -> Decimal:
    """Taux effectif à un instant donné (pour reconstituer un snapshot)."""
    if from_code == to_code:
        return Decimal("1")
    row = (await db.execute(
        select(ExchangeRate.rate)
        .where(
            ExchangeRate.from_currency == from_code,
            ExchangeRate.to_currency == to_code,
            ExchangeRate.effective_at <= when,
        )
        .order_by(ExchangeRate.effective_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        raise ValueError(f"Aucun taux {from_code}→{to_code} à cette date")
    return Decimal(str(row))


def convert(amount_usd: Decimal, to_currency: str, rate: Optional[Decimal] = None) -> Decimal:
    """Convertit un montant USD vers `to_currency` (2 décimales arrondies)."""
    if to_currency == "USD":
        return amount_usd
    if rate is None:
        raise ValueError("Un taux est requis pour convertir hors USD")
    return (Decimal(str(amount_usd)) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def get_currency(db: AsyncSession, code: str) -> Optional[Currency]:
    """Métadonnées d'affichage d'une devise (symbole, positions, séparateurs)."""
    return (await db.execute(
        select(Currency).where(Currency.code == code)
    )).scalar_one_or_none()


def format_amount(amount: Decimal, currency: Currency) -> str:
    """Formate selon les règles de la devise : '$20.00' ou '50 000 FC'.

    Les règles (decimals, séparateurs, position du symbole) viennent de la
    table `currencies` — jamais codées ici.
    """
    value = Decimal(str(amount))
    quant = Decimal(1).scaleb(-currency.decimal_places) if currency.decimal_places > 0 else Decimal(1)
    value = value.quantize(quant)
    int_part, _, frac = str(abs(value)).partition(".")
    grouped = ""
    for i, ch in enumerate(reversed(int_part)):
        grouped = ch + grouped
        if (i + 1) % 3 == 0 and i + 1 < len(int_part):
            grouped = currency.thousands_sep + grouped
    body = grouped + (currency.decimal_sep + frac if frac else "")
    signed = ("-" if value < 0 else "") + body
    if currency.symbol_position == "before":
        return f"{currency.symbol}{signed}"
    return f"{signed} {currency.symbol}"


async def format_for_display(
    db: AsyncSession, amount_usd: Decimal, currency_code: str
) -> str:
    """Convertit + formate pour l'affichage utilisateur (raccourci)."""
    currency = await get_currency(db, currency_code)
    if currency is None:
        return f"${Decimal(str(amount_usd)).quantize(Decimal('0.01'))}"
    rate = await get_current_rate(db, "USD", currency_code)
    return format_amount(convert(Decimal(str(amount_usd)), currency_code, rate), currency)
