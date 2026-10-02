"""Machine à états des commandes — transitions + droits par rôle.

Les statuts sont des String extensibles (jamais d'Enum Python figé), mais la
machine à états est STRICTE : toute transition hors table est refusée.

Rôles reconnus : vendor (couvre staff), courier, customer, superadmin, system.
"""

from typing import Optional

# Transitions autorisées entre statuts de commande.
TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"preparing", "cancelled"},
    "preparing": {"shipped", "cancelled"},
    "shipped": {"out_for_delivery", "cancelled"},
    "out_for_delivery": {"delivered", "rescheduled", "failed"},
    "rescheduled": {"out_for_delivery", "cancelled"},
    "failed": {"rescheduled", "returned", "cancelled"},
    "delivered": set(),  # terminal
    "returned": set(),   # terminal
    "cancelled": set(),  # terminal
}

ALL_STATUSES: set[str] = set(TRANSITIONS)

# Qui peut déclencher quoi : (from, to) -> rôles autorisés.
ACTOR_RULES: dict[tuple[str, str], set[str]] = {
    ("pending", "confirmed"): {"vendor", "superadmin"},
    ("confirmed", "preparing"): {"vendor", "superadmin"},
    ("preparing", "shipped"): {"vendor", "superadmin"},
    ("shipped", "out_for_delivery"): {"vendor", "superadmin"},
    ("out_for_delivery", "delivered"): {"courier", "superadmin"},
    ("out_for_delivery", "rescheduled"): {"customer", "courier", "vendor", "superadmin"},
    ("out_for_delivery", "failed"): {"courier", "vendor", "superadmin"},
    ("rescheduled", "out_for_delivery"): {"vendor", "courier", "superadmin"},
    ("rescheduled", "cancelled"): {"vendor", "customer", "superadmin", "system"},
    ("failed", "rescheduled"): {"vendor", "courier", "customer", "superadmin"},
    ("failed", "returned"): {"vendor", "courier", "superadmin"},
    ("failed", "cancelled"): {"vendor", "superadmin", "system"},
    ("pending", "cancelled"): {"customer", "vendor", "superadmin", "system"},
    ("confirmed", "cancelled"): {"customer", "vendor", "superadmin", "system"},
    ("preparing", "cancelled"): {"vendor", "superadmin"},
    ("shipped", "cancelled"): {"vendor", "superadmin"},
}

# Libellés français (affichage timeline / notifications).
STATUS_LABELS: dict[str, str] = {
    "pending": "En attente de confirmation",
    "confirmed": "Confirmée",
    "preparing": "En préparation",
    "shipped": "Expédiée",
    "out_for_delivery": "En cours de livraison",
    "delivered": "Livrée",
    "rescheduled": "Reportée",
    "failed": "Échec de livraison",
    "returned": "Retournée au vendeur",
    "cancelled": "Annulée",
}


def status_label(status: str) -> str:
    """Libellé lisible d'un statut (fallback : statut brut)."""
    return STATUS_LABELS.get(status, status)


def can_transition(
    from_status: str, to_status: str, actor_role: str
) -> tuple[bool, Optional[str]]:
    """Vérifie transition + droit rôle. Retourne (ok, raison_si_refus)."""
    if to_status not in TRANSITIONS:
        return False, f"Statut inconnu : {to_status}"
    if to_status not in TRANSITIONS.get(from_status, set()):
        return False, f"Transition interdite : {from_status} → {to_status}"
    if actor_role == "superadmin":  # override total
        return True, None
    allowed = ACTOR_RULES.get((from_status, to_status))
    if allowed is None or actor_role not in allowed:
        return False, f"Le rôle {actor_role} ne peut pas effectuer {from_status} → {to_status}"
    return True, None
