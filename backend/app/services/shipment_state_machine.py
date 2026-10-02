"""Machine à états des COLIS (shipments) — stricte, config-free.

Transitions autorisées :

    pending      → in_transit | cancelled
    in_transit   → delivered | failed
    failed       → pending (nouvelle tentative via reschedule) | returned
    delivered    → (terminal)
    returned     → (terminal)

Règles métier :
- Un colis "pending" ne peut PAS être livré directement.
- Un colis "failed" ne peut PAS être livré (il faut repasser par pending).
- "delivered" et "returned" sont terminaux.

Autorisations par rôle :
- courier : start (pending→in_transit), confirm (in_transit→delivered),
  fail (in_transit→failed), reschedule (failed→pending)
- vendor/staff : assign, confirm-manuel (après délai), fail, reschedule
- superadmin : toutes les transitions (override)
"""

from typing import Optional

# Source de vérité des statuts (jamais d'enum Python figé côté API :
# les valeurs sont stockées en String et validées ici).
SHIPMENT_STATUSES: set[str] = {
    "pending",
    "in_transit",
    "delivered",
    "failed",
    "returned",
    "cancelled",
}

TERMINAL_STATUSES: frozenset[str] = frozenset({"delivered", "returned", "cancelled"})

TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_transit", "cancelled"},
    "in_transit": {"delivered", "failed"},
    "failed": {"pending", "returned"},
    "delivered": set(),
    "returned": set(),
    "cancelled": set(),
}

_LABELS: dict[str, str] = {
    "pending": "En attente",
    "in_transit": "En cours de livraison",
    "delivered": "Livré",
    "failed": "Échec de livraison",
    "returned": "Retourné au vendeur",
    "cancelled": "Annulé",
}

# Qui peut déclencher quelle transition (from -> to -> rôles autorisés)
_ALLOWED_ROLES: dict[tuple[str, str], set[str]] = {
    ("pending", "in_transit"): {"courier", "vendor", "staff", "superadmin"},
    ("pending", "cancelled"): {"vendor", "staff", "superadmin"},
    ("in_transit", "delivered"): {"courier", "customer", "vendor", "staff", "superadmin"},
    ("in_transit", "failed"): {"courier", "vendor", "staff", "superadmin"},
    ("failed", "pending"): {"courier", "vendor", "staff", "superadmin"},
    ("failed", "returned"): {"courier", "vendor", "staff", "superadmin"},
}


def status_label(status: str) -> str:
    """Libellé français d'un statut de colis."""
    return _LABELS.get(status, status.replace("_", " ").capitalize())


def can_transition(
    from_status: str, to_status: str, actor_role: Optional[str] = None
) -> tuple[bool, str]:
    """Vérifie la transition (statut) puis l'autorisation (rôle).

    Retourne (autorisé, raison si refus).
    """
    if from_status not in TRANSITIONS:
        return False, f"Statut source inconnu : {from_status}"
    if to_status not in SHIPMENT_STATUSES:
        return False, f"Statut cible inconnu : {to_status}"
    if to_status == from_status:
        return False, "Le colis est déjà dans ce statut"
    if to_status not in TRANSITIONS[from_status]:
        return False, f"Transition interdite : {from_status} → {to_status}"
    if actor_role is not None and actor_role != "superadmin":
        allowed = _ALLOWED_ROLES.get((from_status, to_status), set())
        if actor_role not in allowed:
            return False, f"Le rôle '{actor_role}' ne peut pas faire cette transition"
    return True, ""
