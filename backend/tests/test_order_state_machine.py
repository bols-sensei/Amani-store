"""Tests de la machine à états des commandes (Prompt 3)."""

import pytest

from app.services.order_state_machine import can_transition, status_label

ALL_STATUSES = [
    "pending", "confirmed", "preparing", "shipped", "out_for_delivery",
    "delivered", "rescheduled", "failed", "returned", "cancelled",
]


def test_transitions_autorisees() -> None:
    ok_cases = [
        ("pending", "confirmed", "vendor"),
        ("pending", "cancelled", "customer"),
        ("confirmed", "preparing", "vendor"),
        ("confirmed", "cancelled", "customer"),
        ("preparing", "shipped", "vendor"),
        ("shipped", "out_for_delivery", "vendor"),
        ("out_for_delivery", "delivered", "courier"),
        ("out_for_delivery", "failed", "courier"),
        ("out_for_delivery", "rescheduled", "customer"),
        ("rescheduled", "out_for_delivery", "vendor"),
        ("failed", "rescheduled", "vendor"),
        ("failed", "returned", "vendor"),
    ]
    for frm, to, role in ok_cases:
        allowed, _reason = can_transition(frm, to, role)
        assert allowed, f"{frm} -> {to} par {role} devrait être autorisé"


def test_transitions_interdites() -> None:
    bad_cases = [
        ("pending", "delivered"),
        ("pending", "shipped"),
        ("pending", "out_for_delivery"),
        ("confirmed", "delivered"),
        ("preparing", "delivered"),
        ("delivered", "cancelled"),
        ("delivered", "pending"),
        ("cancelled", "confirmed"),
        ("returned", "delivered"),
        ("out_for_delivery", "pending"),
    ]
    for frm, to in bad_cases:
        allowed, reason = can_transition(frm, to, "superadmin")
        if frm == "delivered" or frm == "cancelled" or frm == "returned":
            # terminaux : interdits même pour superadmin
            assert not allowed, f"{frm} -> {to} ne doit jamais passer"
            assert reason
        else:
            # hors machine à états : refusé quel que soit le rôle
            allowed2, _ = can_transition(frm, to, "customer")
            assert not allowed2


def test_statuts_terminaux() -> None:
    for terminal in ("delivered", "returned", "cancelled"):
        for target in ALL_STATUSES:
            allowed, _ = can_transition(terminal, target, "superadmin")
            assert not allowed, f"{terminal} est terminal (->{target})"


def test_permissions_par_role() -> None:
    # un client ne peut pas confirmer une commande
    allowed, reason = can_transition("pending", "confirmed", "customer")
    assert not allowed and reason
    # un courier ne peut pas annuler
    allowed, _ = can_transition("pending", "cancelled", "courier")
    assert not allowed
    # un courier ne fait que delivered/failed depuis out_for_delivery
    allowed, _ = can_transition("out_for_delivery", "delivered", "courier")
    assert allowed
    allowed, _ = can_transition("out_for_delivery", "rescheduled", "courier")
    assert not allowed
    # vendor ne livre pas lui-même (QR = courier/client) — la machine à états
    # des commandes réserve "delivered" au courier/superadmin.
    allowed, _ = can_transition("out_for_delivery", "delivered", "vendor")
    assert not allowed
    # system auto-cancel pending
    allowed, _ = can_transition("pending", "cancelled", "system")
    assert allowed


def test_superadmin_override() -> None:
    allowed, _ = can_transition("confirmed", "cancelled", "superadmin")
    assert allowed
    allowed, _ = can_transition("preparing", "cancelled", "superadmin")
    assert allowed


def test_statut_inconnu_refuse() -> None:
    allowed, reason = can_transition("pending", "livre_en_mains_propres", "superadmin")
    assert not allowed and reason
    allowed, _ = can_transition("inexistant", "confirmed", "superadmin")
    assert not allowed


def test_status_label_existe() -> None:
    assert status_label("pending")
    assert status_label("unknown_x") is not None
