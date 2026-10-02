"""Sécurité : hachage Argon2id + JWT (HS256).

Argon2id: memory_cost=65536, time_cost=3, parallelism=4.
Aucun secret codé en dur : tout vient de core.config.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import argon2
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import settings

# Hasher Argon2id conforme au cahier des charges.
ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    type=argon2.Type.ID,
)


def hash_password(password: str) -> str:
    """Hache un mot de passe avec Argon2id."""
    return ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Vérifie un mot de passe contre son hash (rehash transparent si besoin)."""
    try:
        return ph.verify(hashed, password)
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str) -> bool:
    """Indique si le hash doit être régénéré (paramètres modifiés)."""
    return ph.check_needs_rehash(hashed)


def create_access_token(
    subject: str,
    extra_claims: Optional[dict[str, Any]] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """Crée un JWT access token (HS256).

    `subject` est l'identifiant utilisateur (str). Les claims optionnels
    (role, tenant_id) sont inclus pour éviter des requêtes DB supplémentaires.
    """
    now = datetime.now(timezone.utc)
    minutes = expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "jti": secrets.token_hex(16),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token() -> str:
    """Crée un refresh token opaque (non-JWT), stocké haché en base."""
    return secrets.token_urlsafe(48)


def decode_token(token: str) -> dict[str, Any]:
    """Décode et valide un JWT. Lève JWTError si invalide/expiré."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def hash_token(token: str) -> str:
    """Hache SHA-256 un token opaque (refresh / blacklist / verification).

    On ne stocke jamais les tokens en clair.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_password_policy(password: str) -> list[str]:
    """Retourne la liste des violations de la politique de mot de passe.

    Politique : min 8 caractères (configurable via settings.PASSWORD_MIN_LENGTH),
    1 majuscule, 1 minuscule, 1 chiffre.
    """
    errors: list[str] = []
    min_length = settings.PASSWORD_MIN_LENGTH
    if len(password) < min_length:
        errors.append(f"Le mot de passe doit contenir au moins {min_length} caractères")
    if not any(c.isupper() for c in password):
        errors.append("Le mot de passe doit contenir au moins une majuscule")
    if not any(c.islower() for c in password):
        errors.append("Le mot de passe doit contenir au moins une minuscule")
    if not any(c.isdigit() for c in password):
        errors.append("Le mot de passe doit contenir au moins un chiffre")
    return errors
