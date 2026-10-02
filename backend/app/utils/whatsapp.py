"""Utilitaire WhatsApp MANUEL — aucun provider, aucune automatisation.

Décision MVP : pas d'intégration WhatsApp Business API ni SMS. On génère
seulement un lien "click-to-chat" wa.me que les frontends (prompt 8)
afficheront sur des boutons « Contacter sur WhatsApp ».
"""

from urllib.parse import quote

# Préfixe international RDC utilisé pour normaliser les numéros locaux
# commençant par 0 (ex. 0812345678 → +243812345678).
RDC_COUNTRY_CODE = "243"


def _normalize_digits(phone: str) -> str:
    """Garde uniquement les chiffres ; préfixe RDC (+243) si numéro local."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("0"):
        digits = RDC_COUNTRY_CODE + digits.lstrip("0")
    return digits


def whatsapp_link(phone: str, message: str | None = None) -> str:
    """Retourne l'URL cliquable https://wa.me/{digits}[?text=...] ."""
    digits = _normalize_digits(phone)
    if not digits:
        raise ValueError("Numéro de téléphone invalide")
    url = f"https://wa.me/{digits}"
    if message:
        url = f"{url}?text={quote(message, safe='')}"
    return url
