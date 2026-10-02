"""Stub SMS — la double confirmation par lien est générée et loguée.

À remplacer par un vrai provider (Kimiya/SMS RDC) plus tard, sans toucher
aux appelants : même signature `send_verification_link`.
"""

import logging

logger = logging.getLogger("kimia.sms")


async def send_sms(phone: str, message: str) -> bool:
    """Stub : log le SMS au lieu de l'envoyer (aucune donnée sensible en clair)."""
    logger.info("[STUB SMS] -> %s : %s", phone[:5] + "***", message[:80])
    return True


async def send_verification_link(phone: str, link: str) -> bool:
    """Envoie (stub) le lien de double confirmation par SMS."""
    return await send_sms(phone, f"Kimia - Confirmez votre numero : {link}")
